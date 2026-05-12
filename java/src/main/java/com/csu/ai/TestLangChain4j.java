package com.csu.ai;

import dev.langchain4j.data.message.AiMessage;
import dev.langchain4j.data.message.ChatMessage;
import dev.langchain4j.data.message.SystemMessage;
import dev.langchain4j.data.message.UserMessage;
import dev.langchain4j.model.chat.ChatLanguageModel;
import dev.langchain4j.model.chat.StreamingChatLanguageModel;
import dev.langchain4j.model.chat.response.ChatResponse;
import dev.langchain4j.model.chat.response.StreamingChatResponseHandler;
import dev.langchain4j.model.openai.OpenAiChatModel;
import dev.langchain4j.model.openai.OpenAiStreamingChatModel;

import java.util.Arrays;
import java.util.List;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicReference;

/**
 * 使用 LangChain4j 测试（Java 版的 LangChain）
 */
public class TestLangChain4j {
    private final Config config;

    public TestLangChain4j(Config config) {
        this.config = config;
    }

    /**
     * 测试同步调用
     */
    public boolean testInvoke() {
        System.out.println("\n--- ChatLanguageModel.chat() 同步调用 ---");
        try {
            ChatLanguageModel model = OpenAiChatModel.builder()
                    .apiKey(config.apiKey)
                    .baseUrl(config.baseUrl)
                    .modelName(config.model)
                    .temperature(0.7)
                    .maxTokens(100)
                    .build();

            long start = System.currentTimeMillis();
            List<ChatMessage> messages = Arrays.asList(
                    new SystemMessage("你是一个有问必答的AI助手。"),
                    new UserMessage("你好，请回复'连通成功'")
            );
            ChatResponse response = model.chat(messages);
            long elapsed = System.currentTimeMillis() - start;

            System.out.println("回复: " + response.aiMessage().text());
            System.out.printf("✅ 成功 | 耗时: %.3fs | Tokens: %s%n",
                    elapsed / 1000.0, response.tokenUsage());
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
        System.out.println("\n--- StreamingChatLanguageModel.chat() 流式调用 ---");
        try {
            StreamingChatLanguageModel model = OpenAiStreamingChatModel.builder()
                    .apiKey(config.apiKey)
                    .baseUrl(config.baseUrl)
                    .modelName(config.model)
                    .temperature(0.7)
                    .maxTokens(100)
                    .build();

            long start = System.currentTimeMillis();
            AtomicReference<Double> firstTokenTime = new AtomicReference<>();
            StringBuilder fullText = new StringBuilder();
            CountDownLatch latch = new CountDownLatch(1);

            List<ChatMessage> messages = Arrays.asList(
                    new SystemMessage("你是一个有问必答的AI助手。"),
                    new UserMessage("你好，请回复'连通成功'")
            );

            model.chat(messages, new StreamingChatResponseHandler() {
                        @Override
                        public void onPartialResponse(String token) {
                            if (firstTokenTime.get() == null) {
                                firstTokenTime.set((System.currentTimeMillis() - start) / 1000.0);
                            }
                            fullText.append(token);
                            System.out.print(token);
                        }

                        @Override
                        public void onCompleteResponse(ChatResponse response) {
                            double elapsed = (System.currentTimeMillis() - start) / 1000.0;
                            double ttft = firstTokenTime.get() != null ? firstTokenTime.get() : 0;
                            System.out.printf("%n✅ 成功 | TTFT: %.3fs | 总耗时: %.3fs%n", ttft, elapsed);
                            latch.countDown();
                        }

                        @Override
                        public void onError(Throwable error) {
                            System.out.println("\n❌ " + error.getMessage());
                            latch.countDown();
                        }
                    }
            );

            latch.await(30, TimeUnit.SECONDS);
            return !fullText.isEmpty();
        } catch (Exception e) {
            System.out.println("❌ " + e.getClass().getSimpleName() + ": " + e.getMessage());
            return false;
        }
    }
}
