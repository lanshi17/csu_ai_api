#include "http_client.h"
#include <curl/curl.h>
#include <nlohmann/json.hpp>
#include <chrono>
#include <iostream>
#include <sstream>
#include <iomanip>

using json = nlohmann::json;

static size_t write_callback(void* contents, size_t size, size_t nmemb, std::string* s) {
    size_t total = size * nmemb;
    s->append(static_cast<char*>(contents), total);
    return total;
}

// SSE 流式回调上下文
struct StreamContext {
    std::string full_text;
    double first_token_time = 0.0;
    std::chrono::steady_clock::time_point start;
    bool first_token_recorded = false;
};

static size_t stream_write_callback(void* contents, size_t size, size_t nmemb, StreamContext* ctx) {
    size_t total = size * nmemb;
    std::string chunk(static_cast<char*>(contents), total);

    // 按行解析 SSE
    std::istringstream stream(chunk);
    std::string line;
    while (std::getline(stream, line)) {
        if (line.rfind("data: ", 0) != 0) continue;
        std::string data = line.substr(6);
        if (data == "[DONE]") break;

        try {
            auto j = json::parse(data);
            if (j.contains("choices") && !j["choices"].empty()) {
                auto& delta = j["choices"][0]["delta"];
                if (delta.contains("content")) {
                    std::string content = delta["content"];
                    if (!content.empty()) {
                        if (!ctx->first_token_recorded) {
                            auto now = std::chrono::steady_clock::now();
                            ctx->first_token_time =
                                std::chrono::duration<double>(now - ctx->start).count();
                            ctx->first_token_recorded = true;
                        }
                        ctx->full_text += content;
                        std::cout << content << std::flush;
                    }
                }
            }
        } catch (...) {
            // 忽略解析错误
        }
    }
    return total;
}

HttpClient::HttpClient(const Config& config) : config_(config) {}

std::string HttpClient::build_chat_payload(const std::string& content, bool stream) {
    json body;
    body["model"] = config_.model;
    body["max_tokens"] = 100;
    body["stream"] = stream;
    body["messages"] = json::array({
        {{"role", "user"}, {"content", content}}
    });
    return body.dump();
}

std::string HttpClient::http_get(const std::string& url, int& status_code) {
    CURL* curl = curl_easy_init();
    std::string response;

    struct curl_slist* headers = nullptr;
    headers = curl_slist_append(headers, ("Authorization: Bearer " + config_.api_key).c_str());

    curl_easy_setopt(curl, CURLOPT_URL, url.c_str());
    curl_easy_setopt(curl, CURLOPT_HTTPHEADER, headers);
    curl_easy_setopt(curl, CURLOPT_WRITEFUNCTION, write_callback);
    curl_easy_setopt(curl, CURLOPT_WRITEDATA, &response);
    curl_easy_setopt(curl, CURLOPT_TIMEOUT, 30L);

    CURLcode res = curl_easy_perform(curl);
    curl_easy_getinfo(curl, CURLINFO_RESPONSE_CODE, &status_code);

    curl_slist_free_all(headers);
    curl_easy_cleanup(curl);

    if (res != CURLE_OK) {
        throw std::runtime_error(curl_easy_strerror(res));
    }
    return response;
}

std::string HttpClient::http_post(const std::string& url, const std::string& body, int& status_code) {
    CURL* curl = curl_easy_init();
    std::string response;

    struct curl_slist* headers = nullptr;
    headers = curl_slist_append(headers, "Content-Type: application/json");
    headers = curl_slist_append(headers, ("Authorization: Bearer " + config_.api_key).c_str());

    curl_easy_setopt(curl, CURLOPT_URL, url.c_str());
    curl_easy_setopt(curl, CURLOPT_HTTPHEADER, headers);
    curl_easy_setopt(curl, CURLOPT_POSTFIELDS, body.c_str());
    curl_easy_setopt(curl, CURLOPT_WRITEFUNCTION, write_callback);
    curl_easy_setopt(curl, CURLOPT_WRITEDATA, &response);
    curl_easy_setopt(curl, CURLOPT_TIMEOUT, 60L);

    CURLcode res = curl_easy_perform(curl);
    curl_easy_getinfo(curl, CURLINFO_RESPONSE_CODE, &status_code);

    curl_slist_free_all(headers);
    curl_easy_cleanup(curl);

    if (res != CURLE_OK) {
        throw std::runtime_error(curl_easy_strerror(res));
    }
    return response;
}

std::string HttpClient::http_post_stream(const std::string& url, const std::string& body,
                                          double& first_token_time, double& total_time) {
    CURL* curl = curl_easy_init();

    struct curl_slist* headers = nullptr;
    headers = curl_slist_append(headers, "Content-Type: application/json");
    headers = curl_slist_append(headers, ("Authorization: Bearer " + config_.api_key).c_str());

    StreamContext ctx;
    ctx.start = std::chrono::steady_clock::now();

    curl_easy_setopt(curl, CURLOPT_URL, url.c_str());
    curl_easy_setopt(curl, CURLOPT_HTTPHEADER, headers);
    curl_easy_setopt(curl, CURLOPT_POSTFIELDS, body.c_str());
    curl_easy_setopt(curl, CURLOPT_WRITEFUNCTION, stream_write_callback);
    curl_easy_setopt(curl, CURLOPT_WRITEDATA, &ctx);
    curl_easy_setopt(curl, CURLOPT_TIMEOUT, 60L);

    CURLcode res = curl_easy_perform(curl);
    auto now = std::chrono::steady_clock::now();
    total_time = std::chrono::duration<double>(now - ctx.start).count();
    first_token_time = ctx.first_token_time;

    curl_slist_free_all(headers);
    curl_easy_cleanup(curl);

    if (res != CURLE_OK) {
        throw std::runtime_error(curl_easy_strerror(res));
    }
    return ctx.full_text;
}

bool HttpClient::test_models_list() {
    std::cout << "\n--- Models List ---" << std::endl;
    try {
        int status = 0;
        std::string resp = http_get(config_.base_url + "/models", status);
        if (status != 200) {
            std::cout << "❌ HTTP " << status << ": " << resp << std::endl;
            return false;
        }

        auto j = json::parse(resp);
        auto& models = j["data"];
        std::cout << "可用模型 (" << models.size() << " 个):" << std::endl;
        for (auto& m : models) {
            std::cout << "  - " << m["id"].get<std::string>() << std::endl;
        }
        std::cout << "✅ 成功" << std::endl;
        return true;
    } catch (const std::exception& e) {
        std::cout << "❌ " << e.what() << std::endl;
        return false;
    }
}

bool HttpClient::test_non_stream() {
    std::cout << "\n--- Chat Completions (非流式) ---" << std::endl;
    try {
        std::string body = build_chat_payload("你好，请回复'连通成功'", false);
        auto start = std::chrono::steady_clock::now();

        int status = 0;
        std::string resp = http_post(config_.base_url + "/chat/completions", body, status);
        if (status != 200) {
            std::cout << "❌ HTTP " << status << ": " << resp << std::endl;
            return false;
        }

        auto j = json::parse(resp);
        std::string content = j["choices"][0]["message"]["content"];
        double elapsed = std::chrono::duration<double>(
            std::chrono::steady_clock::now() - start).count();

        std::cout << "回复: " << content << std::endl;
        std::cout << std::fixed << std::setprecision(3)
                  << "✅ 成功 | 耗时: " << elapsed << "s" << std::endl;
        return true;
    } catch (const std::exception& e) {
        std::cout << "❌ " << e.what() << std::endl;
        return false;
    }
}

bool HttpClient::test_stream() {
    std::cout << "\n--- Chat Completions (流式) ---" << std::endl;
    try {
        std::string body = build_chat_payload("你好，请回复'连通成功'", true);
        double first_token = 0.0, total = 0.0;

        std::string text = http_post_stream(config_.base_url + "/chat/completions", body,
                                             first_token, total);

        if (!text.empty()) {
            std::cout << std::endl << std::fixed << std::setprecision(3)
                      << "✅ 成功 | TTFT: " << first_token << "s | 总耗时: " << total << "s"
                      << std::endl;
            return true;
        }
        std::cout << "\n❌ 无响应内容" << std::endl;
        return false;
    } catch (const std::exception& e) {
        std::cout << "❌ " << e.what() << std::endl;
        return false;
    }
}
