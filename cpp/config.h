#pragma once

#include <string>

struct Config {
    std::string api_key;
    std::string base_url;
    std::string model;

    static Config load();
};
