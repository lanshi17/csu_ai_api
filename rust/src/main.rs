mod config;
mod http_client;

use config::Config;
use http_client::HttpClient;

struct TestResult {
    name: String,
    success: bool,
}

#[tokio::main]
async fn main() {
    let config = Config::load();

    println!("SDK:      Rust (reqwest / serde_json)");
    println!("Base URL: {}", config.base_url);
    println!("API Key:  {}...", &config.api_key[..12]);
    println!("Model:    {}", config.model);

    let http = HttpClient::new(config.clone());
    let mut results: Vec<TestResult> = Vec::new();

    // HTTP 测试
    results.push(TestResult {
        name: "HTTP Models List".to_string(),
        success: http.test_models_list().await,
    });
    results.push(TestResult {
        name: "HTTP Chat (非流式)".to_string(),
        success: http.test_non_stream().await,
    });
    results.push(TestResult {
        name: "HTTP Chat (流式)".to_string(),
        success: http.test_stream().await,
    });

    // 汇总
    println!("\n==================================================");
    println!("测试汇总:");

    let mut all_passed = true;
    for r in &results {
        println!("  {} {}", if r.success { "✅" } else { "❌" }, r.name);
        if !r.success {
            all_passed = false;
        }
    }

    if !all_passed {
        std::process::exit(1);
    }
}
