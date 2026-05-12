package main

import (
	"context"
	"fmt"
	"time"

	"github.com/openai/openai-go"
	"github.com/openai/openai-go/option"
)

// TestOpenAI 使用 OpenAI Go SDK 测试
type TestOpenAI struct {
	config *Config
	client openai.Client
}

// NewTestOpenAI 创建 OpenAI SDK 测试实例
func NewTestOpenAI(config *Config) *TestOpenAI {
	client := openai.NewClient(
		option.WithAPIKey(config.APIKey),
		option.WithBaseURL(config.BaseURL),
	)
	return &TestOpenAI{
		config: config,
		client: client,
	}
}

// TestInvoke 测试同步调用
func (t *TestOpenAI) TestInvoke() bool {
	fmt.Println("\n--- chat().completions().create() 同步调用 ---")

	ctx := context.Background()
	start := time.Now()

	completion, err := t.client.Chat.Completions.New(ctx, openai.ChatCompletionNewParams{
		Model: openai.ChatModel(t.config.Model),
		Messages: []openai.ChatCompletionMessageParamUnion{
			openai.UserMessage("你好，请回复'连通成功'"),
		},
		MaxTokens:   openai.Int(100),
		Temperature: openai.Float(0.7),
	})
	if err != nil {
		fmt.Printf("❌ %v\n", err)
		return false
	}

	elapsed := time.Since(start)
	if len(completion.Choices) > 0 {
		fmt.Printf("回复: %s\n", completion.Choices[0].Message.Content)
		fmt.Printf("✅ 成功 | 耗时: %.3fs\n", elapsed.Seconds())
		return true
	}

	fmt.Println("❌ 无响应内容")
	return false
}

// TestStream 测试流式调用
func (t *TestOpenAI) TestStream() bool {
	fmt.Println("\n--- chat().completions().createStreaming() 流式调用 ---")

	ctx := context.Background()
	start := time.Now()

	stream := t.client.Chat.Completions.NewStreaming(ctx, openai.ChatCompletionNewParams{
		Model: openai.ChatModel(t.config.Model),
		Messages: []openai.ChatCompletionMessageParamUnion{
			openai.UserMessage("你好，请回复'连通成功'"),
		},
		MaxTokens:   openai.Int(100),
		Temperature: openai.Float(0.7),
	})

	var firstTokenTime *float64
	var fullText string

	for stream.Next() {
		chunk := stream.Current()
		if len(chunk.Choices) > 0 {
			content := chunk.Choices[0].Delta.Content
			if content != "" {
				if firstTokenTime == nil {
					ttft := time.Since(start).Seconds()
					firstTokenTime = &ttft
				}
				fullText += content
				fmt.Print(content)
			}
		}
	}

	if err := stream.Err(); err != nil {
		fmt.Printf("\n❌ %v\n", err)
		return false
	}

	if fullText != "" {
		elapsed := time.Since(start).Seconds()
		ttft := 0.0
		if firstTokenTime != nil {
			ttft = *firstTokenTime
		}
		fmt.Printf("\n✅ 成功 | TTFT: %.3fs | 总耗时: %.3fs\n", ttft, elapsed)
		return true
	}

	fmt.Println("\n❌ 无响应内容")
	return false
}

// TestModelsList 测试 Models 列表
func (t *TestOpenAI) TestModelsList() bool {
	fmt.Println("\n--- models().list() ---")

	ctx := context.Background()
	models, err := t.client.Models.List(ctx)
	if err != nil {
		fmt.Printf("❌ %v\n", err)
		return false
	}

	fmt.Printf("可用模型 (%d 个):\n", len(models.Data))
	for _, m := range models.Data {
		fmt.Printf("  - %s\n", m.ID)
	}
	fmt.Println("✅ 成功")
	return true
}
