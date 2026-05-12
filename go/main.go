package main

import (
	"fmt"
	"os"
)

// TestResult 测试结果
type TestResult struct {
	Name    string
	Success bool
}

func main() {
	config := LoadConfig()

	fmt.Println("SDK:      Go (OpenAI SDK / net/http / Responses API)")
	fmt.Printf("Base URL: %s\n", config.BaseURL)
	fmt.Printf("API Key:  %s...\n", config.APIKey[:12])
	fmt.Printf("Model:    %s\n", config.Model)

	var results []TestResult

	// OpenAI SDK 测试
	testOpenAI := NewTestOpenAI(config)
	results = append(results, TestResult{"OpenAI SDK Models List", testOpenAI.TestModelsList()})
	results = append(results, TestResult{"OpenAI SDK invoke()", testOpenAI.TestInvoke()})
	results = append(results, TestResult{"OpenAI SDK stream()", testOpenAI.TestStream()})

	// OpenAI SDK Responses API 测试
	testResponses := NewTestResponses(config)
	results = append(results, TestResult{"OpenAI SDK Responses invoke()", testResponses.TestInvoke()})
	results = append(results, TestResult{"OpenAI SDK Responses stream()", testResponses.TestStream()})

	// 原生 HTTP 测试
	testHTTP := NewTestHTTP(config)
	results = append(results, TestResult{"HTTP Models List", testHTTP.TestModelsList()})
	results = append(results, TestResult{"HTTP Chat (非流式)", testHTTP.TestNonStream()})
	results = append(results, TestResult{"HTTP Chat (流式)", testHTTP.TestStream()})

	// 汇总
	fmt.Println("\n==================================================")
	fmt.Println("测试汇总:")
	allPassed := true
	for _, r := range results {
		status := "✅"
		if !r.Success {
			status = "❌"
			allPassed = false
		}
		fmt.Printf("  %s %s\n", status, r.Name)
	}

	if !allPassed {
		os.Exit(1)
	}
}
