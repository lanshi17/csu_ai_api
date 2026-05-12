package com.csu.ai;

import com.openai.client.OpenAIClient;
import com.openai.client.okhttp.OpenAIOkHttpClient;
import com.openai.core.http.StreamResponse;
import com.openai.models.ChatModel;
import com.openai.models.ResponsesModel;
import com.openai.models.responses.*;

/**
 * 使用 OpenAI Java SDK 测试 Responses API
 */
public class TestResponses {
    private final Config config;
    private final OpenAIClient client;

    public TestResponses(Config config) {
        this.config = config;
        this.client = OpenAIOkHttpClient.builder()
                .apiKey(config.apiKey)
                .baseUrl(config.baseUrl)
                .build();
    }

    /**
     * 测试同步调用
     */
    public boolean testInvoke() {
        System.out.println("\n--- responses().create() 同步调用 ---");
        try {
            ResponseCreateParams params = ResponseCreateParams.builder()
                    .input(ResponseCreateParams.Input.Companion.ofText("你好，请回复'连通成功'"))
                    .model(ResponsesModel.Companion.ofChat(ChatModel.of(config.model)))
                    .maxOutputTokens(100L)
                    .temperature(0.7)
                    .build();

            long start = System.currentTimeMillis();
            Response response = client.responses().create(params);
            long elapsed = System.currentTimeMillis() - start;

            // 提取文本内容
            String text = response.output().stream()
                    .flatMap(item -> item.message().stream())
                    .flatMap(msg -> msg.content().stream())
                    .flatMap(content -> content.outputText().stream())
                    .map(ResponseOutputText::text)
                    .reduce("", (a, b) -> a + b);

            System.out.println("回复: " + text);
            System.out.printf("✅ 成功 | 耗时: %.3fs%n", elapsed / 1000.0);
            return true;
        } catch (Exception e) {
            System.out.println("❌ " + e.getClass().getSimpleName() + ": " + e.getMessage());
            return false;
        }
    }

    /**
     * 测试流式调用
     */
    public boolean testStream() {
        System.out.println("\n--- responses().createStreaming() 流式调用 ---");
        try {
            ResponseCreateParams params = ResponseCreateParams.builder()
                    .input(ResponseCreateParams.Input.Companion.ofText("你好，请回复'连通成功'"))
                    .model(ResponsesModel.Companion.ofChat(ChatModel.of(config.model)))
                    .maxOutputTokens(100L)
                    .temperature(0.7)
                    .build();

            long start = System.currentTimeMillis();
            Double[] firstTokenTime = new Double[]{null};
            StringBuilder fullText = new StringBuilder();

            try (StreamResponse<ResponseStreamEvent> response = client.responses().createStreaming(params)) {
                var iterator = response.stream().iterator();

                while (iterator.hasNext()) {
                    ResponseStreamEvent event = iterator.next();
                    event.outputTextDelta().ifPresent(delta -> {
                        String text = delta.delta();
                        if (text != null && !text.isEmpty()) {
                            if (firstTokenTime[0] == null) {
                                firstTokenTime[0] = (System.currentTimeMillis() - start) / 1000.0;
                            }
                            fullText.append(text);
                            System.out.print(text);
                        }
                    });
                }
            }

            double elapsed = (System.currentTimeMillis() - start) / 1000.0;
            double ttft = firstTokenTime[0] != null ? firstTokenTime[0] : 0;
            System.out.printf("%n✅ 成功 | TTFT: %.3fs | 总耗时: %.3fs%n", ttft, elapsed);
            return true;
        } catch (Exception e) {
            System.out.println("❌ " + e.getClass().getSimpleName() + ": " + e.getMessage());
            return false;
        }
    }
}
