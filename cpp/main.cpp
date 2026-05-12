#include "config.h"
#include "http_client.h"
#include <iostream>
#include <iomanip>
#include <vector>
#include <string>

struct TestResult {
    std::string name;
    bool success;
};

int main() {
    Config config = Config::load();

    std::cout << "SDK:      C++ (libcurl / nlohmann/json)" << std::endl;
    std::cout << "Base URL: " << config.base_url << std::endl;
    std::cout << "API Key:  " << config.api_key.substr(0, 12) << "..." << std::endl;
    std::cout << "Model:    " << config.model << std::endl;

    std::vector<TestResult> results;

    HttpClient http(config);

    // 原生 HTTP 测试
    results.push_back({"HTTP Models List", http.test_models_list()});
    results.push_back({"HTTP Chat (非流式)", http.test_non_stream()});
    results.push_back({"HTTP Chat (流式)", http.test_stream()});

    // 汇总
    std::cout << "\n==================================================" << std::endl;
    std::cout << "测试汇总:" << std::endl;

    bool all_passed = true;
    for (const auto& r : results) {
        std::cout << "  " << (r.success ? "✅" : "❌") << " " << r.name << std::endl;
        if (!r.success) all_passed = false;
    }

    return all_passed ? 0 : 1;
}
