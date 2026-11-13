package main

import (
	"fmt"
	"os"

	"github.com/joho/godotenv"
)

// Config 从 .env 文件加载配置
type Config struct {
	APIKey  string
	BaseURL string
	Model   string
}

// LoadConfig 加载配置
func LoadConfig() *Config {
	if err := godotenv.Load(); err != nil {
		_ = godotenv.Load("../.env") // 回退到仓库根目录统一配置
	}

	apiKey := os.Getenv("API_KEY")
	if apiKey == "" {
		fmt.Println("错误: 请设置 API_KEY 环境变量")
		os.Exit(1)
	}

	baseURL := os.Getenv("API_BASE_URL")
	if baseURL == "" {
		baseURL = "https://api.chat.csu.edu.cn/v1"
	}

	model := os.Getenv("MODEL_NAME")
	if model == "" {
		model = "DeepSeek"
	}

	return &Config{
		APIKey:  apiKey,
		BaseURL: baseURL,
		Model:   model,
	}
}
