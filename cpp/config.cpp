#include "config.h"
#include <cstdlib>
#include <iostream>
#include <fstream>
#include <sstream>
#include <string>

// 简单的 .env 文件解析
static void load_dotenv() {
    std::ifstream file(".env");
    if (!file.is_open()) return;

    std::string line;
    while (std::getline(file, line)) {
        // 跳过空行和注释
        if (line.empty() || line[0] == '#') continue;

        auto eq_pos = line.find('=');
        if (eq_pos == std::string::npos) continue;

        std::string key = line.substr(0, eq_pos);
        std::string value = line.substr(eq_pos + 1);

        // 去除引号
        if (value.size() >= 2 && value.front() == '"' && value.back() == '"') {
            value = value.substr(1, value.size() - 2);
        }

        // 只在环境变量不存在时设置
        if (!std::getenv(key.c_str())) {
            setenv(key.c_str(), value.c_str(), 0);
        }
    }
}

Config Config::load() {
    load_dotenv();

    const char* api_key = std::getenv("API_KEY");
    if (!api_key || std::string(api_key).empty()) {
        std::cerr << "错误: 请设置 API_KEY 环境变量" << std::endl;
        std::exit(1);
    }

    const char* base_url = std::getenv("API_BASE_URL");
    const char* model = std::getenv("MODEL_NAME");

    return Config{
        api_key,
        base_url ? base_url : "https://api.chat.csu.edu.cn/v1",
        model ? model : "DeepSeek-V4-Flash"
    };
}
