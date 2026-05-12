package com.csu.ai;

import io.github.cdimascio.dotenv.Dotenv;

/**
 * 从 .env 文件加载配置
 */
public class Config {
    public final String apiKey;
    public final String baseUrl;
    public final String model;

    private Config(String apiKey, String baseUrl, String model) {
        this.apiKey = apiKey;
        this.baseUrl = baseUrl;
        this.model = model;
    }

    public static Config load() {
        Dotenv dotenv = Dotenv.configure()
                .directory(System.getProperty("user.dir"))
                .ignoreIfMissing()
                .load();

        String apiKey = dotenv.get("API_KEY");
        if (apiKey == null || apiKey.isEmpty()) {
            System.err.println("错误: 请设置 API_KEY 环境变量");
            System.exit(1);
        }

        return new Config(
                apiKey,
                dotenv.get("API_BASE_URL", "https://api.chat.csu.edu.cn/v1"),
                dotenv.get("MODEL_NAME", "DeepSeek-V4-Flash")
        );
    }
}
