package main

import (
	"context"
	"fmt"
	"time"

	"github.com/openai/openai-go"
	"github.com/openai/openai-go/option"
	"github.com/openai/openai-go/responses"
)

// TestResponses 使用 OpenAI Go SDK 测试 Responses API
type TestResponses struct {
	config *Config
	client openai.Client
}

// NewTestResponses 创建 Responses API 测试实例
func NewTestResponses(config *Config) *TestResponses {
	client := openai.NewClient(
		option.WithAPIKey(config.APIKey),
		option.WithBaseURL(config.BaseURL),
	)
	return &TestResponses{
		config: config,
		client: client,
	}
}

// TestInvoke 测试同步调用
func (t *TestResponses) TestInvoke() bool {
	fmt.Println("\n--- responses().create() 同步调用 ---")

	ctx := context.Background()
	start := time.Now()

	response, err := t.client.Responses.New(ctx, responses.ResponseNewParams{
		Input: responses.ResponseNewParamsInputUnion{
			OfString: openai.String("你好，请回复'连通成功'"),
		},
		Model:           t.config.Model,
		MaxOutputTokens: openai.Int(100),
		Temperature:     openai.Float(0.7),
	})
	if err != nil {
		fmt.Printf("❌ %v\n", err)
		return false
	}

	elapsed := time.Since(start)
	text := response.OutputText()
	if text != "" {
		fmt.Printf("回复: %s\n", text)
		fmt.Printf("✅ 成功 | 耗时: %.3fs\n", elapsed.Seconds())
		return true
	}

	fmt.Println("❌ 无响应内容")
	return false
}

// TestStream 测试流式调用
func (t *TestResponses) TestStream() bool {
	fmt.Println("\n--- responses().createStreaming() 流式调用 ---")

	ctx := context.Background()
	start := time.Now()

	stream := t.client.Responses.NewStreaming(ctx, responses.ResponseNewParams{
		Input: responses.ResponseNewParamsInputUnion{
			OfString: openai.String("你好，请回复'连通成功'"),
		},
		Model:           t.config.Model,
		MaxOutputTokens: openai.Int(100),
		Temperature:     openai.Float(0.7),
	})

	var firstTokenTime *float64
	var fullText string

	for stream.Next() {
		event := stream.Current()
		// 检查是否是 output_text.delta 事件
		if event.Type == "response.output_text.delta" {
			delta := event.AsResponseOutputTextDelta()
			if delta.Delta != "" {
				if firstTokenTime == nil {
					ttft := time.Since(start).Seconds()
					firstTokenTime = &ttft
				}
				fullText += delta.Delta
				fmt.Print(delta.Delta)
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
