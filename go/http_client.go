package main

import (
	"bufio"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"strings"
	"time"
)

// TestHTTP 使用原生 HTTP 客户端测试（类似 Python requests / Java OkHttp）
type TestHTTP struct {
	config *Config
	client *http.Client
}

// NewTestHTTP 创建 HTTP 测试实例
func NewTestHTTP(config *Config) *TestHTTP {
	return &TestHTTP{
		config: config,
		client: &http.Client{
			Timeout: 60 * time.Second,
		},
	}
}

type chatRequest struct {
	Model    string    `json:"model"`
	Messages []message `json:"messages"`
	MaxTokens int      `json:"max_tokens"`
	Stream   bool      `json:"stream"`
}

type message struct {
	Role    string `json:"role"`
	Content string `json:"content"`
}

type chatResponse struct {
	Choices []struct {
		Message struct {
			Content string `json:"content"`
		} `json:"message"`
	} `json:"choices"`
}

type chatChunk struct {
	Choices []struct {
		Delta struct {
			Content string `json:"content"`
		} `json:"delta"`
	} `json:"choices"`
}

type modelsResponse struct {
	Data []struct {
		ID string `json:"id"`
	} `json:"data"`
}

// TestNonStream 测试非流式 Chat Completions
func (t *TestHTTP) TestNonStream() bool {
	fmt.Println("\n--- Chat Completions (非流式) ---")

	payload := chatRequest{
		Model: t.config.Model,
		Messages: []message{
			{Role: "user", Content: "你好，请回复'连通成功'"},
		},
		MaxTokens: 100,
		Stream:    false,
	}

	body, err := json.Marshal(payload)
	if err != nil {
		fmt.Printf("❌ JSON 编码失败: %v\n", err)
		return false
	}

	req, err := http.NewRequest("POST", t.config.BaseURL+"/chat/completions", strings.NewReader(string(body)))
	if err != nil {
		fmt.Printf("❌ 请求创建失败: %v\n", err)
		return false
	}
	req.Header.Set("Content-Type", "application/json")
	req.Header.Set("Authorization", "Bearer "+t.config.APIKey)

	start := time.Now()
	resp, err := t.client.Do(req)
	if err != nil {
		fmt.Printf("❌ 请求失败: %v\n", err)
		return false
	}
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusOK {
		respBody, _ := io.ReadAll(resp.Body)
		fmt.Printf("❌ HTTP %d: %s\n", resp.StatusCode, string(respBody))
		return false
	}

	var result chatResponse
	if err := json.NewDecoder(resp.Body).Decode(&result); err != nil {
		fmt.Printf("❌ JSON 解码失败: %v\n", err)
		return false
	}

	elapsed := time.Since(start)
	if len(result.Choices) > 0 {
		fmt.Printf("回复: %s\n", result.Choices[0].Message.Content)
		fmt.Printf("✅ 成功 | 耗时: %.3fs\n", elapsed.Seconds())
		return true
	}

	fmt.Println("❌ 无响应内容")
	return false
}

// TestStream 测试流式 Chat Completions
func (t *TestHTTP) TestStream() bool {
	fmt.Println("\n--- Chat Completions (流式) ---")

	payload := chatRequest{
		Model: t.config.Model,
		Messages: []message{
			{Role: "user", Content: "你好，请回复'连通成功'"},
		},
		MaxTokens: 100,
		Stream:    true,
	}

	body, err := json.Marshal(payload)
	if err != nil {
		fmt.Printf("❌ JSON 编码失败: %v\n", err)
		return false
	}

	req, err := http.NewRequest("POST", t.config.BaseURL+"/chat/completions", strings.NewReader(string(body)))
	if err != nil {
		fmt.Printf("❌ 请求创建失败: %v\n", err)
		return false
	}
	req.Header.Set("Content-Type", "application/json")
	req.Header.Set("Authorization", "Bearer "+t.config.APIKey)

	start := time.Now()
	resp, err := t.client.Do(req)
	if err != nil {
		fmt.Printf("❌ 请求失败: %v\n", err)
		return false
	}
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusOK {
		respBody, _ := io.ReadAll(resp.Body)
		fmt.Printf("❌ HTTP %d: %s\n", resp.StatusCode, string(respBody))
		return false
	}

	var firstTokenTime *float64
	var fullText strings.Builder
	scanner := bufio.NewScanner(resp.Body)

	for scanner.Scan() {
		line := scanner.Text()
		if !strings.HasPrefix(line, "data: ") {
			continue
		}
		data := strings.TrimPrefix(line, "data: ")
		if data == "[DONE]" {
			break
		}

		var chunk chatChunk
		if err := json.Unmarshal([]byte(data), &chunk); err != nil {
			continue
		}

		if len(chunk.Choices) > 0 {
			content := chunk.Choices[0].Delta.Content
			if content != "" {
				if firstTokenTime == nil {
					ttft := time.Since(start).Seconds()
					firstTokenTime = &ttft
				}
				fullText.WriteString(content)
				fmt.Print(content)
			}
		}
	}

	if fullText.Len() > 0 {
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
func (t *TestHTTP) TestModelsList() bool {
	fmt.Println("\n--- Models List ---")

	req, err := http.NewRequest("GET", t.config.BaseURL+"/models", nil)
	if err != nil {
		fmt.Printf("❌ 请求创建失败: %v\n", err)
		return false
	}
	req.Header.Set("Authorization", "Bearer "+t.config.APIKey)

	resp, err := t.client.Do(req)
	if err != nil {
		fmt.Printf("❌ 请求失败: %v\n", err)
		return false
	}
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusOK {
		respBody, _ := io.ReadAll(resp.Body)
		fmt.Printf("❌ HTTP %d: %s\n", resp.StatusCode, string(respBody))
		return false
	}

	var result modelsResponse
	if err := json.NewDecoder(resp.Body).Decode(&result); err != nil {
		fmt.Printf("❌ JSON 解码失败: %v\n", err)
		return false
	}

	fmt.Printf("可用模型 (%d 个):\n", len(result.Data))
	for _, m := range result.Data {
		fmt.Printf("  - %s\n", m.ID)
	}
	fmt.Println("✅ 成功")
	return true
}
