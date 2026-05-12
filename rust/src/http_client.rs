use crate::config::Config;
use reqwest::Client;
use serde::{Deserialize, Serialize};
use std::time::Instant;

type BoxError = Box<dyn std::error::Error + Send + Sync>;

#[derive(Serialize)]
struct ChatRequest {
    model: String,
    messages: Vec<Message>,
    max_tokens: u32,
    #[serde(skip_serializing_if = "std::ops::Not::not")]
    stream: bool,
}

#[derive(Serialize)]
struct Message {
    role: String,
    content: String,
}

#[derive(Deserialize)]
struct ChatResponse {
    choices: Vec<Choice>,
}

#[derive(Deserialize)]
struct Choice {
    message: ResponseMessage,
}

#[derive(Deserialize)]
struct ResponseMessage {
    content: String,
}

#[derive(Deserialize)]
struct ChatChunk {
    choices: Vec<ChunkChoice>,
}

#[derive(Deserialize)]
struct ChunkChoice {
    delta: Delta,
}

#[derive(Deserialize)]
struct Delta {
    content: Option<String>,
}

#[derive(Deserialize)]
struct ModelsResponse {
    data: Vec<ModelInfo>,
}

#[derive(Deserialize)]
struct ModelInfo {
    id: String,
}

pub struct HttpClient {
    config: Config,
    client: Client,
}

impl HttpClient {
    pub fn new(config: Config) -> Self {
        let client = Client::builder()
            .timeout(std::time::Duration::from_secs(60))
            .build()
            .expect("Failed to build HTTP client");

        HttpClient { config, client }
    }

    fn build_chat_payload(&self, content: &str, stream: bool) -> ChatRequest {
        ChatRequest {
            model: self.config.model.clone(),
            messages: vec![Message {
                role: "user".to_string(),
                content: content.to_string(),
            }],
            max_tokens: 100,
            stream,
        }
    }

    pub async fn test_models_list(&self) -> bool {
        println!("\n--- Models List ---");

        let result: Result<(), BoxError> = async {
            let resp = self
                .client
                .get(format!("{}/models", self.config.base_url))
                .bearer_auth(&self.config.api_key)
                .send()
                .await?;

            if !resp.status().is_success() {
                let status = resp.status();
                let body = resp.text().await?;
                return Err(format!("HTTP {}: {}", status, body).into());
            }

            let models: ModelsResponse = resp.json().await?;
            println!("可用模型 ({} 个):", models.data.len());
            for m in &models.data {
                println!("  - {}", m.id);
            }
            println!("✅ 成功");
            Ok(())
        }
        .await;

        match result {
            Ok(()) => true,
            Err(e) => {
                println!("❌ {}", e);
                false
            }
        }
    }

    pub async fn test_non_stream(&self) -> bool {
        println!("\n--- Chat Completions (非流式) ---");

        let result: Result<(), BoxError> = async {
            let body = self.build_chat_payload("你好，请回复'连通成功'", false);
            let start = Instant::now();

            let resp = self
                .client
                .post(format!("{}/chat/completions", self.config.base_url))
                .bearer_auth(&self.config.api_key)
                .json(&body)
                .send()
                .await?;

            if !resp.status().is_success() {
                let status = resp.status();
                let body_text = resp.text().await?;
                return Err(format!("HTTP {}: {}", status, body_text).into());
            }

            let data: ChatResponse = resp.json().await?;
            let elapsed = start.elapsed();

            if let Some(choice) = data.choices.first() {
                println!("回复: {}", choice.message.content);
                println!("✅ 成功 | 耗时: {:.3}s", elapsed.as_secs_f64());
                Ok(())
            } else {
                Err("无响应内容".into())
            }
        }
        .await;

        match result {
            Ok(()) => true,
            Err(e) => {
                println!("❌ {}", e);
                false
            }
        }
    }

    pub async fn test_stream(&self) -> bool {
        println!("\n--- Chat Completions (流式) ---");

        let result: Result<(), BoxError> = async {
            let body = self.build_chat_payload("你好，请回复'连通成功'", true);
            let start = Instant::now();

            let resp = self
                .client
                .post(format!("{}/chat/completions", self.config.base_url))
                .bearer_auth(&self.config.api_key)
                .json(&body)
                .send()
                .await?;

            if !resp.status().is_success() {
                let status = resp.status();
                let body_text = resp.text().await?;
                return Err(format!("HTTP {}: {}", status, body_text).into());
            }

            let mut first_token_time: Option<f64> = None;
            let mut full_text = String::new();
            let mut stream = resp.bytes_stream();

            use futures::StreamExt;
            let mut buf = String::new();

            while let Some(chunk) = stream.next().await {
                let bytes = chunk?;
                buf.push_str(&String::from_utf8_lossy(&bytes));

                // 按行处理 SSE
                while let Some(newline_pos) = buf.find('\n') {
                    let line = buf[..newline_pos].trim().to_string();
                    buf = buf[newline_pos + 1..].to_string();

                    if !line.starts_with("data: ") {
                        continue;
                    }
                    let data = &line[6..];
                    if data == "[DONE]" {
                        break;
                    }

                    if let Ok(chunk) = serde_json::from_str::<ChatChunk>(data) {
                        if let Some(choice) = chunk.choices.first() {
                            if let Some(content) = &choice.delta.content {
                                if !content.is_empty() {
                                    if first_token_time.is_none() {
                                        first_token_time = Some(start.elapsed().as_secs_f64());
                                    }
                                    full_text.push_str(content);
                                    print!("{}", content);
                                    use std::io::Write;
                                    std::io::stdout().flush().ok();
                                }
                            }
                        }
                    }
                }
            }

            if !full_text.is_empty() {
                let elapsed = start.elapsed().as_secs_f64();
                let ttft = first_token_time.unwrap_or(0.0);
                println!("\n✅ 成功 | TTFT: {:.3}s | 总耗时: {:.3}s", ttft, elapsed);
                Ok(())
            } else {
                Err("无响应内容".into())
            }
        }
        .await;

        match result {
            Ok(()) => true,
            Err(e) => {
                println!("❌ {}", e);
                false
            }
        }
    }
}
