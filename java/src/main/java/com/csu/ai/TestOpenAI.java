package com.csu.ai;

import com.openai.client.OpenAIClient;
import com.openai.client.okhttp.OpenAIOkHttpClient;
import com.openai.core.http.StreamResponse;
import com.openai.models.chat.completions.ChatCompletion;
import com.openai.models.chat.completions.ChatCompletionChunk;
import com.openai.models.chat.completions.ChatCompletionCreateParams;
import com.openai.models.ChatModel;
import com.openai.models.models.Model;

import java.util.List;
import java.util.stream.Stream;

/**
 * 使用 OpenAI Java SDK 测试（类似 Python openai 库）
 */
public class TestOpenAI {
    private final Config config;
    private final OpenAIClient client;

    public TestOpenAI(Config config) {
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
        System.out.println("\n--- chat().completions().create() 同步调用 ---");
        try {
            ChatCompletionCreateParams params = ChatCompletionCreateParams.builder()
                    .model(ChatModel.of(config.model))
                    .addUserMessage("你好，请回复'连通成功'")
                    .maxTokens(100L)
                    .temperature(0.7)
                    .build();

            long start = System.currentTimeMillis();
            ChatCompletion completion = client.chat().completions().create(params);
            long elapsed = System.currentTimeMillis() - start;

            String content = completion.choices().get(0).message().content().orElse("");
            System.out.println("回复: " + content);
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
        System.out.println("\n--- chat().completions().createStreaming() 流式调用 ---");
        try {
            ChatCompletionCreateParams params = ChatCompletionCreateParams.builder()
                    .model(ChatModel.of(config.model))
                    .addUserMessage("你好，请回复'连通成功'")
                    .maxTokens(100L)
                    .temperature(0.7)
                    .build();

            long start = System.currentTimeMillis();
            Double firstTokenTime = null;
            StringBuilder fullText = new StringBuilder();

            try (StreamResponse<ChatCompletionChunk> response = client.chat().completions().createStreaming(params)) {
                Stream<ChatCompletionChunk> stream = response.stream();
                var iterator = stream.iterator();

                while (iterator.hasNext()) {
                    ChatCompletionChunk chunk = iterator.next();
                    if (chunk.choices().isEmpty()) continue;
                    String content = chunk.choices().get(0).delta().content().orElse("");
                    if (content != null && !content.isEmpty()) {
                        if (firstTokenTime == null) {
                            firstTokenTime = (System.currentTimeMillis() - start) / 1000.0;
                        }
                        fullText.append(content);
                        System.out.print(content);
                    }
                }
            }

            double elapsed = (System.currentTimeMillis() - start) / 1000.0;
            double ttft = firstTokenTime != null ? firstTokenTime : 0;
            System.out.printf("%n✅ 成功 | TTFT: %.3fs | 总耗时: %.3fs%n", ttft, elapsed);
            return true;
        } catch (Exception e) {
            System.out.println("❌ " + e.getClass().getSimpleName() + ": " + e.getMessage());
            return false;
        }
    }

    /**
     * 测试 Models 列表
     */
    public boolean testModelsList() {
        System.out.println("\n--- models().list() ---");
        try {
            List<Model> models = client.models().list().data();
            System.out.println("可用模型 (" + models.size() + " 个):");
            models.stream().sorted((a, b) -> a.id().compareTo(b.id()))
                    .forEach(m -> System.out.println("  - " + m.id()));
            System.out.println("✅ 成功");
            return true;
        } catch (Exception e) {
            System.out.println("❌ " + e.getClass().getSimpleName() + ": " + e.getMessage());
            return false;
        }
    }
}
