#pragma once

#include "config.h"
#include <string>
#include <vector>

class HttpClient {
public:
    explicit HttpClient(const Config& config);

    bool test_models_list();
    bool test_non_stream();
    bool test_stream();

private:
    Config config_;

    std::string build_chat_payload(const std::string& content, bool stream);
    std::string http_get(const std::string& url, int& status_code);
    std::string http_post(const std::string& url, const std::string& body, int& status_code);
    std::string http_post_stream(const std::string& url, const std::string& body,
                                  double& first_token_time, double& total_time);
};
