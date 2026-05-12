use std::env;

#[derive(Clone)]
pub struct Config {
    pub api_key: String,
    pub base_url: String,
    pub model: String,
}

impl Config {
    pub fn load() -> Self {
        let _ = dotenvy::dotenv();

        let api_key = env::var("API_KEY").unwrap_or_else(|_| {
            eprintln!("错误: 请设置 API_KEY 环境变量");
            std::process::exit(1);
        });

        let base_url = env::var("API_BASE_URL")
            .unwrap_or_else(|_| "https://api.chat.csu.edu.cn/v1".to_string());

        let model = env::var("MODEL_NAME")
            .unwrap_or_else(|_| "DeepSeek-V4-Flash".to_string());

        Config {
            api_key,
            base_url,
            model,
        }
    }
}
