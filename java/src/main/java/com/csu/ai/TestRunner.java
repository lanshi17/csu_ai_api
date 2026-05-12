package com.csu.ai;

import java.util.LinkedHashMap;
import java.util.Map;

/**
 * 测试运行入口
 */
public class TestRunner {
    public static void main(String[] args) {
        Config config = Config.load();

        System.out.println("SDK:      Java (OpenAI SDK / OkHttp / LangChain4j)");
        System.out.println("Base URL: " + config.baseUrl);
        System.out.println("API Key:  " + config.apiKey.substring(0, 12) + "...");
        System.out.println("Model:    " + config.model);

        Map<String, Boolean> results = new LinkedHashMap<>();

        // OpenAI SDK 测试
        TestOpenAI testOpenAI = new TestOpenAI(config);
        results.put("OpenAI SDK Models List", testOpenAI.testModelsList());
        results.put("OpenAI SDK invoke()", testOpenAI.testInvoke());
        results.put("OpenAI SDK stream()", testOpenAI.testStream());

        // OpenAI SDK Responses API 测试
        TestResponses testResponses = new TestResponses(config);
        results.put("OpenAI SDK Responses invoke()", testResponses.testInvoke());
        results.put("OpenAI SDK Responses stream()", testResponses.testStream());

        // OkHttp 原生 HTTP 测试
        TestHttp testHttp = new TestHttp(config);
        results.put("OkHttp Models List", testHttp.testModelsList());
        results.put("OkHttp Chat (非流式)", testHttp.testNonStream());
        results.put("OkHttp Chat (流式)", testHttp.testStream());

        // LangChain4j 测试
        TestLangChain4j testLangChain4j = new TestLangChain4j(config);
        results.put("LangChain4j invoke()", testLangChain4j.testInvoke());
        results.put("LangChain4j stream()", testLangChain4j.testStream());

        // 汇总
        System.out.println("\n==================================================");
        System.out.println("测试汇总:");
        for (Map.Entry<String, Boolean> entry : results.entrySet()) {
            System.out.printf("  %s %s%n", entry.getValue() ? "✅" : "❌", entry.getKey());
        }

        boolean allPassed = results.values().stream().allMatch(Boolean::booleanValue);
        if (!allPassed) {
            System.exit(1);
        }
    }
}
