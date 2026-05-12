package com.csu.ai;

import com.google.gson.Gson;
import com.google.gson.JsonArray;
import com.google.gson.JsonObject;
import okhttp3.*;
import okhttp3.sse.EventSource;
import okhttp3.sse.EventSourceListener;
import okhttp3.sse.EventSources;

import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.concurrent.atomic.AtomicReference;

/**
 * 使用 OkHttp 测试 HTTP API（类似 Python requests）
 */
public class TestHttp {
    private static final Gson gson = new Gson();
    private final Config config;
    private final OkHttpClient client;

    public TestHttp(Config config) {
        this.config = config;
        this.client = new OkHttpClient.Builder()
                .connectTimeout(30, TimeUnit.SECONDS)
                .readTimeout(60, TimeUnit.SECONDS)
                .build();
    }

    private String buildChatPayload(String content, boolean stream) {
        JsonObject body = new JsonObject();
        body.addProperty("model", config.model);
        body.addProperty("max_tokens", 100);
        body.addProperty("stream", stream);

        JsonArray messages = new JsonArray();
        JsonObject msg = new JsonObject();
        msg.addProperty("role", "user");
        msg.addProperty("content", content);
        messages.add(msg);
        body.add("messages", messages);

        return gson.toJson(body);
    }

    /**
     * 测试非流式 Chat Completions
     */
    public boolean testNonStream() {
        System.out.println("\n--- Chat Completions (非流式) ---");
        try {
            String url = config.baseUrl + "/chat/completions";
            String body = buildChatPayload("你好，请回复'连通成功'", false);

            Request request = new Request.Builder()
                    .url(url)
                    .header("Authorization", "Bearer " + config.apiKey)
                    .post(RequestBody.create(body, MediaType.parse("application/json")))
                    .build();

            long start = System.currentTimeMillis();
            try (Response response = client.newCall(request).execute()) {
                if (!response.isSuccessful()) {
                    System.out.printf("❌ HTTP %d: %s%n", response.code(), response.body().string());
                    return false;
                }

                JsonObject data = gson.fromJson(response.body().string(), JsonObject.class);
                String content = data.getAsJsonArray("choices")
                        .get(0).getAsJsonObject()
                        .getAsJsonObject("message")
                        .get("content").getAsString();

                long elapsed = System.currentTimeMillis() - start;
                System.out.println("回复: " + content);
                System.out.printf("✅ 成功 | 耗时: %.3fs%n", elapsed / 1000.0);
                return true;
            }
        } catch (Exception e) {
            System.out.println("❌ " + e.getClass().getSimpleName() + ": " + e.getMessage());
            return false;
        }
    }

    /**
     * 测试流式 Chat Completions
     */
    public boolean testStream() {
        System.out.println("\n--- Chat Completions (流式) ---");
        try {
            String url = config.baseUrl + "/chat/completions";
            String body = buildChatPayload("你好，请回复'连通成功'", true);

            Request request = new Request.Builder()
                    .url(url)
                    .header("Authorization", "Bearer " + config.apiKey)
                    .post(RequestBody.create(body, MediaType.parse("application/json")))
                    .build();

            CountDownLatch latch = new CountDownLatch(1);
            AtomicReference<Double> firstTokenTime = new AtomicReference<>();
            long start = System.currentTimeMillis();
            StringBuilder fullText = new StringBuilder();

            EventSourceListener listener = new EventSourceListener() {
                @Override
                public void onEvent(EventSource eventSource, String id, String type, String data) {
                    if ("[DONE]".equals(data)) {
                        eventSource.cancel();
                        latch.countDown();
                        return;
                    }
                    try {
                        JsonObject chunk = gson.fromJson(data, JsonObject.class);
                        String content = chunk.getAsJsonArray("choices")
                                .get(0).getAsJsonObject()
                                .getAsJsonObject("delta")
                                .get("content").getAsString();

                        if (content != null && !content.isEmpty()) {
                            if (firstTokenTime.get() == null) {
                                firstTokenTime.set((System.currentTimeMillis() - start) / 1000.0);
                            }
                            fullText.append(content);
                            System.out.print(content);
                        }
                    } catch (Exception ignored) {
                    }
                }

                @Override
                public void onFailure(EventSource eventSource, Throwable t, Response response) {
                    if (t != null) {
                        System.out.println("\n❌ " + t.getMessage());
                    }
                    eventSource.cancel();
                    latch.countDown();
                }
            };

            EventSources.createFactory(client).newEventSource(request, listener);
            latch.await(30, TimeUnit.SECONDS);

            if (!fullText.isEmpty()) {
                double elapsed = (System.currentTimeMillis() - start) / 1000.0;
                double ttft = firstTokenTime.get() != null ? firstTokenTime.get() : 0;
                System.out.printf("%n✅ 成功 | TTFT: %.3fs | 总耗时: %.3fs%n", ttft, elapsed);
                return true;
            }
            return false;
        } catch (Exception e) {
            System.out.println("❌ " + e.getClass().getSimpleName() + ": " + e.getMessage());
            return false;
        }
    }

    /**
     * 测试 Models 列表
     */
    public boolean testModelsList() {
        System.out.println("\n--- Models List ---");
        try {
            Request request = new Request.Builder()
                    .url(config.baseUrl + "/models")
                    .header("Authorization", "Bearer " + config.apiKey)
                    .get()
                    .build();

            try (Response response = client.newCall(request).execute()) {
                if (!response.isSuccessful()) {
                    System.out.printf("❌ HTTP %d: %s%n", response.code(), response.body().string());
                    return false;
                }

                JsonObject data = gson.fromJson(response.body().string(), JsonObject.class);
                var models = data.getAsJsonArray("data");
                System.out.println("可用模型 (" + models.size() + " 个):");
                for (var model : models) {
                    System.out.println("  - " + model.getAsJsonObject().get("id").getAsString());
                }
                System.out.println("✅ 成功");
                return true;
            }
        } catch (Exception e) {
            System.out.println("❌ " + e.getClass().getSimpleName() + ": " + e.getMessage());
            return false;
        }
    }
}
