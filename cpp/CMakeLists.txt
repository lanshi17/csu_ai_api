cmake_minimum_required(VERSION 3.20)
project(csu_ai_cpp LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

# 依赖：libcurl
find_package(CURL REQUIRED)

# nlohmann/json（通过 FetchContent 下载）
include(FetchContent)
FetchContent_Declare(
    nlohmann_json
    URL https://github.com/nlohmann/json/releases/download/v3.11.3/json.tar.xz
    DOWNLOAD_EXTRACT_TIMESTAMP TRUE
)
FetchContent_MakeAvailable(nlohmann_json)

# 可执行文件
add_executable(csu_ai_test
    main.cpp
    config.cpp
    http_client.cpp
)

target_link_libraries(csu_ai_test
    PRIVATE CURL::libcurl
    PRIVATE nlohmann_json::nlohmann_json
)
