# Kiểm tra thay đổi instrumentation của SDK và HTTP client

Sau khi nâng Spring AI, dashboard latency của model vẫn có dữ liệu nhưng trace không còn cây span như trước. Một số request OpenAI có `gen_ai.client.operation` và `okhttp.requests` tách rời; customizer `RestClient.Builder` không còn tác động đến Anthropic; retry làm số HTTP attempts tăng nhưng số model calls không tăng tương ứng. Đây là những thay đổi có thể xảy ra khi provider chuyển từ HTTP client do Spring quản lý sang Java SDK riêng.

Bài này hướng dẫn **kiểm tra thay đổi instrumentation của SDK và HTTP client khi nâng Spring AI**. Ta sẽ phân biệt model observation với HTTP attempt observation, đối chiếu OpenAI và Anthropic SDK transitions, kiểm tra `traceparent` và parent-child spans, cấu hình OkHttp customizers, phân biệt với `RestClient`/`WebClient` của Spring Boot, rồi xây dựng compatibility tests để phát hiện mất trace hoặc đếm trùng latency.

Bài thuộc chương **Nâng cấp** của mô-đun **SPRING_AI_EVALUATION_OBSERVABILITY**. Mô-đun đánh giá ứng dụng Spring AI bằng dataset, relevance, fact checking và kiểm thử RAG/tool workflow; đồng thời đo metrics, traces, chi phí và độ trễ qua các phiên bản prompt, model và pipeline. Instrumentation đúng tầng giúp phân biệt thời gian xử lý ở Spring AI, thời gian gửi HTTP, retry, network và thời gian provider xử lý.

> **Nguyên tắc:** một model call có thể tạo model observation và nhiều HTTP attempt observations. Hãy kiểm tra transport thực tế của provider trước khi cấu hình tracing hoặc thêm interceptor.

## 1. Kết quả học tập

Sau bài học, bạn có thể:

1. Phân biệt model-level observation, SDK HTTP observation và Spring HTTP client observation.
2. Nhận diện thay đổi transport khi OpenAI và Anthropic chuyển sang official Java SDK.
3. Hiểu vai trò của `gen_ai.client.operation`, `okhttp.requests` và `http.client.requests`.
4. Xác minh `traceparent` được truyền qua HTTP và span được gắn đúng parent.
5. Chọn đúng customizer cho OkHttp SDK client, `RestClient` hoặc `WebClient`.
6. Tránh tạo HTTP spans/metrics trùng với instrumentation đã có của Spring AI.
7. Đánh giá ảnh hưởng của streaming, async execution, retry, timeout và connection pool.
8. Kiểm tra các thay đổi dependency, constructor và property sau migration.
9. Viết integration tests cho model success/failure, HTTP attempts và trace propagation.
10. Lập checklist nâng cấp instrumentation trong CI/CD.

## 2. Kiến trúc instrumentation có nhiều lớp

Một lần gọi model có thể đi qua nhiều lớp:

~~~text
HTTP request vào ứng dụng
        |
        v
ChatClient / Advisor
        |
        v
gen_ai.client.operation
        |
        v
Provider Java SDK
        |
        v
okhttp.requests
        |
        v
AI provider / gateway / proxy
~~~

Trong sơ đồ này:

- `ChatClient` và `Advisor` đo thời gian ở tầng framework;
- `gen_ai.client.operation` đo một lần gọi `ChatModel.call()` hoặc `ChatModel.stream()`;
- `okhttp.requests` đo từng HTTP attempt của OpenAI/Anthropic SDK;
- HTTP server span ở provider hoặc gateway có thể nối vào trace nếu nhận `traceparent`.

Nếu ứng dụng còn gọi một REST service riêng bằng `RestClient` hoặc `WebClient`, request đó có thể tạo observation `http.client.requests` độc lập.

### 2.1. Model span và HTTP span trả lời hai câu hỏi khác nhau

| Observation | Phạm vi | Dùng để trả lời |
|---|---|---|
| `gen_ai.client.operation` | Toàn bộ lần gọi model | Một lần `ChatModel.call/stream` mất bao lâu? |
| `okhttp.requests` | Một HTTP request/attempt tới provider | Request HTTP nào chậm, lỗi hoặc bị retry? |
| `http.client.requests` | Một exchange qua Spring `RestClient`, `WebClient`, `RestTemplate` | REST call do ứng dụng thực hiện mất bao lâu? |
| `spring.ai.chat.client` | Pipeline `ChatClient` | Advisors, prompt preparation và các bước framework mất bao lâu? |

Model observation có thể bao gồm serialization, SDK processing, HTTP calls, retry/backoff và response mapping. HTTP observation đo request/response exchange ở transport. Không cộng hai timer thành một tổng latency vì chúng có thể bao phủ cùng khoảng thời gian.

### 2.2. Một model call có thể có nhiều HTTP attempts

Khi SDK retry một request, Spring AI vẫn chỉ thực hiện một lần gọi model ở tầng application, nhưng HTTP client có thể gửi nhiều attempts. Mỗi attempt được ghi nhận ở `okhttp.requests`.

Điều này có ích khi phân tích:

- Provider trả `429` rồi request thành công ở attempt sau;
- Một request timeout hoặc lỗi kết nối;
- Backoff làm model operation kéo dài;
- SDK retry hoặc proxy retry làm tăng request count;
- Một model span có nhiều HTTP child spans.

Đừng dùng số `okhttp.requests` thay cho số model calls. Hãy giữ cả hai metric và đối chiếu chúng trong cùng khoảng thời gian.

## 3. Các mốc migration chính

| Mốc | Thay đổi | Ảnh hưởng instrumentation |
|---|---|---|
| Spring AI 2.0.0-M3 | `spring-ai-anthropic` chuyển sang official `anthropic-java` SDK, thay implementation `RestClient`/`WebClient` tự viết | HTTP transport chuyển sang OkHttp-backed SDK client và có observation riêng |
| Spring AI 2.0.0-M5 | `spring-ai-openai` chuyển sang official `openai-java` SDK cho Chat, Embeddings, Image, Audio Speech, Audio Transcription và Moderation | Spring AI dùng OkHttp-backed transport có Micrometer HTTP observation |
| Spring AI 2.0.x/2.1.x | Có `OpenAiHttpClientBuilderCustomizer` và `AnthropicHttpClientBuilderCustomizer` | Cấu hình interceptor/proxy/SSL/dispatcher tại SDK transport |
| Spring Boot 3.4.2 | Khi không có HTTP client library trên classpath, request factory mặc định có thể chuyển từ `SimpleClientHttpRequestFactory` sang `JdkClientHttpRequestFactory` | Customization hoặc giả định về HTTP implementation cũ cần được kiểm tra |
| Spring Boot 3.x/4.x | Actuator instrument `RestClient`, `WebClient`, `RestTemplate` qua builder được auto-configure | HTTP observation của Spring clients vẫn có thể chạy song song với SDK observations |

### 3.1. OpenAI: official SDK từ 2.0.0-M5

Từ Spring AI 2.0.0-M5, module `spring-ai-openai` dùng official `openai-java` SDK cho các OpenAI models. Với người dùng module `spring-ai-openai` thông thường, properties có prefix `spring.ai.openai.*`, builders và options được giữ lại.

Các module cũ `spring-ai-openai-sdk` và `spring-ai-azure-openai` đã bị loại bỏ. Migration cần:

- Dùng module `spring-ai-openai` và starter `spring-ai-starter-model-openai`;
- Chuyển class có hậu tố `Sdk` sang class tương ứng trong module OpenAI hiện hành;
- Với Azure OpenAI cũ, dùng module OpenAI hiện hành và điều chỉnh class/configuration tương ứng;
- Kiểm tra HTTP customizers vì transport hiện tại là SDK client dựa trên OkHttp.

### 3.2. Anthropic: official SDK từ 2.0.0-M3

`spring-ai-anthropic` chuyển từ implementation `RestClient`/`WebClient` tự viết sang `com.anthropic:anthropic-java`.

Các API cấp cao `ChatClient`, `ChatModel.call(Prompt)` và `ChatModel.stream(Prompt)` vẫn giữ chữ ký. Những phần cần chú ý:

- `AnthropicApi` và DTO lồng bên trong đã bị loại bỏ;
- Constructor public nhận `AnthropicApi` bị loại bỏ; dùng `AnthropicChatModel.builder()`;
- SDK mới đưa `okhttp` vào dependency graph;
- Với Anthropic Java SDK 3.x hiện tại, API key dùng `Authorization: Bearer` thay cho `X-Api-Key`; cập nhật proxy, interceptor và header allowlists phụ thuộc header cũ;
- Retry chuyển từ `RetryTemplate` sang SDK `maxRetries`;
- Custom HTTP transport được cấu hình qua `AnthropicHttpClientBuilderCustomizer`.

Ứng dụng chỉ dùng `ChatClient` hoặc `ChatModel` thường không cần đổi cách gọi. Tuy nhiên, customizer hoặc interceptor trước đây gắn vào `RestClient`/`WebClient` của Anthropic sẽ không tự động cấu hình SDK transport mới.

Chỉ gọi raw `AnthropicClient` trực tiếp khi cần endpoint mà `AnthropicChatModel` chưa hỗ trợ. Đường gọi raw SDK nằm ngoài framework Spring AI: không có `gen_ai.client.operation`, pipeline `ChatClient` hoặc tính provider-neutral của `ChatModel`. Nếu giữ đường gọi này, hãy tự cấu hình observation và HTTP tracing cho client đó.

### 3.3. Spring Boot 3.4.2 thay đổi HTTP request factory

Upgrade notes của Spring AI khi cập nhật dependency management lên Spring Boot 3.4.2 cảnh báo rằng nếu classpath không có HTTP client library, Boot có thể chọn `JdkClientHttpRequestFactory` thay cho `SimpleClientHttpRequestFactory`.

Nếu ứng dụng cần giữ implementation cũ, tài liệu nêu property:

~~~yaml
spring:
  http:
    client:
      factory: simple
~~~

Đừng áp dụng property này chỉ để làm tracing hoạt động. Trước tiên hãy kiểm tra request factory thực tế, dependency tree, timeout, TLS, proxy và observation của client đang dùng.

## 4. Ma trận provider SDK và HTTP transport

| Provider | Dòng cũ | Dòng mới đã đối chiếu | HTTP transport/observation |
|---|---|---|---|
| OpenAI | Implementation trước official SDK | `openai-java` từ 2.0.0-M5 | Spring AI OkHttp client, `okhttp.requests` |
| Anthropic | `RestClient`/`WebClient` tự viết | `anthropic-java` từ 2.0.0-M3 | Spring AI OkHttp client, `okhttp.requests` |
| Ứng dụng tự gọi REST | `RestClient`, `WebClient`, `RestTemplate` | Vẫn là Spring HTTP clients nếu ứng dụng tiếp tục dùng chúng | `http.client.requests` khi ObservationRegistry được cấu hình |
| SDK/client tự tạo bên ngoài Spring AI | Tùy SDK | Tùy cách tạo client | Không mặc định có Spring AI wrapper instrumentation; phải kiểm tra riêng |

Một điểm quan trọng: `RestClient.Builder` và `WebClient.Builder` của Spring Boot chỉ cấu hình những client được tạo từ các builder đó. Chúng không tự động can thiệp vào OkHttp client nằm bên trong OpenAI/Anthropic SDK.

## 5. Hai observation của OpenAI và Anthropic

Spring AI 2.1 reference mô tả hai tầng observation cho OpenAI và Anthropic chat models:

| Tầng | Observation name | Dữ liệu chính |
|---|---|---|
| Chat model | `gen_ai.client.operation` | Model operation, request parameters, response metadata và token usage |
| HTTP | `okhttp.requests` | HTTP method, URI, status code, exception và trace propagation |

Trong Spring Boot app có `spring-boot-starter-actuator` cùng tracing bridge OpenTelemetry hoặc Brave, hai tầng này được wiring tự động. Ứng dụng không cần tự gắn thêm OkHttp observation interceptor.

Với ứng dụng không dùng Spring Boot auto-configuration, truyền `ObservationRegistry` cho builder model:

~~~java
OpenAiChatModel openAiChatModel = OpenAiChatModel.builder()
        .options(openAiOptions)
        .observationRegistry(observationRegistry)
        .build();

AnthropicChatModel anthropicChatModel = AnthropicChatModel.builder()
        .options(anthropicOptions)
        .observationRegistry(observationRegistry)
        .build();
~~~

`ObservationRegistry` cần được cấu hình với các handlers phù hợp để xuất metrics/traces. Nếu dùng `ObservationRegistry.NOOP`, HTTP observation sẽ không ghi telemetry.

### 5.1. HTTP span chứa gì?

HTTP observation có thể cung cấp:

- Method và host/URI của request;
- HTTP status hoặc exception;
- Thời gian của từng HTTP attempt;
- Trace context được truyền ra ngoài qua `traceparent`.

Không nên đưa full URL có query string hoặc dữ liệu người dùng thành metric label. Hãy ưu tiên method, client name, status/outcome và URI template có cardinality hữu hạn.

### 5.2. Connection-pool metrics là tùy chọn

Spring AI có thể bind OkHttp connection-pool gauges:

- Metric: `okhttp.pool.connection.count`;
- `state=active|idle`;
- `client.kind=sync|async`.

Các gauges này phục vụ phân tích capacity và connection reuse, không cần thiết để có per-request spans.

Ví dụ bật cho chat models:

~~~yaml
spring:
  ai:
    openai:
      chat:
        connection-pool-metrics-enabled: true
    anthropic:
      chat:
        connection-pool-metrics-enabled: true
~~~

Mặc định các pool gauges tắt. Chỉ bật khi cần phân tích connection pool; kiểm tra cardinality và phân biệt sync/async client nếu có nhiều model.

## 6. Trace propagation và parent-child relation

### 6.1. Luồng bình thường

Với synchronous OpenAI calls và Anthropic calls dùng client mặc định, trace thường có cấu trúc:

~~~text
application request span
  └── gen_ai.client.operation
        └── okhttp.requests
              └── provider-side span (nếu provider hỗ trợ)
~~~

Spring AI gắn `traceparent` vào HTTP request để AI gateway, proxy hoặc provider có thể nối span ở phía server vào cùng trace.

### 6.2. OpenAI streaming có giới hạn parent linkage

Với OpenAI synchronous calls, `okhttp.requests` được lồng dưới `gen_ai.client.operation`.

Với OpenAI streaming calls, HTTP span vẫn được ghi và timer vẫn được xuất, đồng thời `traceparent` vẫn được gửi ra ngoài. Tuy nhiên, HTTP span không được parent dưới chat-model span vì SDK async streaming chuyển execution sang `ForkJoinPool.commonPool()` và làm mất observation context tại ranh giới thread.

Khi điều tra OpenAI streaming:

- Không kết luận HTTP instrumentation bị mất chỉ vì span không có parent như mong đợi;
- Tìm `okhttp.requests` theo host `api.openai.com`;
- Correlate với `gen_ai.client.operation` bằng trace ID hoặc timestamp;
- Kiểm tra lại khi nâng SDK vì upstream có thể thay đổi context propagation.

### 6.3. Anthropic streaming và custom async client

Với Anthropic client mặc định, `okhttp.requests` được lồng dưới `gen_ai.client.operation` cho cả `call()` và `stream()`.

Nếu ứng dụng tự cung cấp async client qua `AnthropicChatModel.builder().anthropicClientAsync(...)`, Spring AI vẫn sử dụng client đó nhưng HTTP observations có thể không được lồng dưới chat-model observation. Khi thay client mặc định, cần kiểm tra cả observation registry và parent-child relation.

### 6.4. SDK-native spans của Anthropic

Anthropic Java SDK có thể phát OpenTelemetry spans riêng. Spring AI tắt SDK-native tracing trên các clients mà Spring AI tự tạo vì `gen_ai.client.operation` và `okhttp.requests` đã cung cấp hai tầng observation.

Nếu ứng dụng tự tạo Anthropic client rồi truyền vào model, SDK tracing settings của client đó vẫn được giữ. Kiểm tra trace backend để tránh ghi cùng một HTTP attempt qua cả SDK-native spans và Micrometer HTTP observations.

Anthropic API có thể phát server-side spans và nối chúng bằng `traceparent`. Điều này phụ thuộc backend/provider có hỗ trợ W3C trace context; Claude Platform trên AWS hiện chưa đọc `traceparent` theo reference đã đối chiếu.

Nếu không thấy server-side span, kiểm tra sampling trước khi kết luận propagation lỗi: Spring Boot mặc định sample 10% request và điều khiển bằng `management.tracing.sampling.probability`. Anthropic API tuân theo sampled flag trong `traceparent`; nếu ứng dụng chỉ phát B3, thêm W3C propagation, ví dụ `management.tracing.propagation.type=w3c,b3`.

## 7. Customizer đúng cho OkHttp SDK client

Sau khi provider chuyển sang official SDK, hãy dùng customizer của Spring AI để cấu hình HTTP transport.

### 7.1. OpenAI

Package:

~~~java
org.springframework.ai.openai.http.okhttp.OpenAiHttpClientBuilderCustomizer
~~~

Spring AI sử dụng một builder chung cho OpenAI models như chat, embedding, image, audio và moderation. Customizers được áp dụng theo `@Order`/`Ordered` sau defaults của Spring AI.

Ví dụ gắn một header phục vụ routing nội bộ:

~~~java
import okhttp3.Request;

import org.springframework.ai.openai.http.okhttp.OpenAiHttpClientBuilderCustomizer;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
class OpenAiHttpConfiguration {

    @Bean
    OpenAiHttpClientBuilderCustomizer openAiRequestHeaderCustomizer() {
        return builder -> builder.interceptor(chain -> {
            Request request = chain.request().newBuilder()
                    .header("X-Client-Source", "spring-ai")
                    .build();
            return chain.proceed(request);
        });
    }
}
~~~

Dùng hook này cho authentication, propagation header riêng, proxy, TLS, hostname verification, connection pool hoặc executor. Không ghi request body hoặc Authorization header vào log.

### 7.2. Anthropic

Package:

~~~java
org.springframework.ai.anthropic.http.okhttp.AnthropicHttpClientBuilderCustomizer
~~~

Ví dụ:

~~~java
import okhttp3.Request;

import org.springframework.ai.anthropic.http.okhttp.AnthropicHttpClientBuilderCustomizer;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
class AnthropicHttpConfiguration {

    @Bean
    AnthropicHttpClientBuilderCustomizer anthropicRequestHeaderCustomizer() {
        return builder -> builder.interceptor(chain -> {
            Request request = chain.request().newBuilder()
                    .header("X-Client-Source", "spring-ai")
                    .build();
            return chain.proceed(request);
        });
    }
}
~~~

Có hai khác biệt cần nhớ:

1. Anthropic customizer được gọi hai lần cho mỗi `AnthropicChatModel`: một lần cho sync client và một lần cho async client. Implementation phải idempotent; không tạo side effect chỉ được chạy một lần trong callback này.
2. Customizers trong Spring context được áp dụng theo `@Order`/`@Priority` sau defaults. Khi dùng model builder thủ công, thứ tự đăng ký được giữ và annotation của Spring không tự áp dụng.

### 7.3. Không gắn thêm một observation interceptor cho cùng request

Spring AI đã gắn `OkHttpObservationInterceptor` vào transport wrapper của OpenAI/Anthropic để phát HTTP observation, span, metric và `traceparent`.

Customizer ứng dụng chỉ nên bổ sung cross-cutting concern cần thiết như auth, routing, redaction hoặc logging metadata an toàn. Nếu tự thêm một interceptor khác cũng tạo observation cho cùng exchange, bạn có thể tạo hai HTTP spans/metrics cho một request.

## 8. Spring Boot RestClient, WebClient và RestTemplate

Spring Boot Actuator quản lý instrumentation cho:

- `RestTemplateBuilder`;
- `WebClient.Builder`;
- `RestClient.Builder`.

Observation mặc định có tên `http.client.requests`. Để có metrics/traces và trace propagation, hãy inject builder auto-configured rồi tạo client từ builder đó.

Ví dụ:

~~~java
@Configuration
class InternalHttpClientConfiguration {

    @Bean
    RestClient internalRestClient(RestClient.Builder builder) {
        return builder
                .baseUrl("https://inventory.internal")
                .build();
    }
}
~~~

Nếu gọi `RestClient.create()` hoặc `WebClient.create()` trực tiếp, bạn không nhận các customizations của builder auto-configured. Với client tạo thủ công, phải cấu hình `ObservationRegistry` và trace propagation phù hợp; nếu không, HTTP observations có thể là no-op hoặc trace không được truyền qua network.

### 8.1. Phân biệt ba tên observation

| Observation | Nơi tạo | Khi nào xuất hiện |
|---|---|---|
| `gen_ai.client.operation` | Spring AI model layer | Gọi ChatModel |
| `okhttp.requests` | Spring AI SDK HTTP wrapper | OpenAI/Anthropic SDK gửi từng HTTP attempt |
| `http.client.requests` | Spring Framework/Boot HTTP client | Ứng dụng dùng RestClient/WebClient/RestTemplate có ObservationRegistry |

Không đổi tên hoặc gộp ba observation chỉ vì chúng đều là outbound HTTP/model request. Chúng có boundary và mục tiêu đo khác nhau.

### 8.2. Cardinality của HTTP tags

Spring Framework HTTP client observation có low-cardinality keys như:

- `method`;
- `uri` template;
- `client.name`;
- `status`;
- `outcome`;
- `error`.

`http.url` là high-cardinality key. Tránh dùng full URL, query parameter, request ID hoặc user ID làm metric labels. Với trace, vẫn phải xem xét liệu URL có chứa token hoặc dữ liệu riêng tư hay không.

## 9. Retry, timeout và connection pool

Instrumentation cần phản ánh retry ở đúng tầng.

| Provider | Timeout mặc định được tài liệu hóa | Retry mặc định/điểm cấu hình |
|---|---|---|
| OpenAI | `spring.ai.openai.timeout`: 60 giây | `spring.ai.openai.max-retries`: 3; `spring.ai.retry.max-attempts`: 10 ở model retry layer |
| Anthropic | `spring.ai.anthropic.timeout`: 60 giây | `spring.ai.anthropic.max-retries`: 2; SDK xử lý retry thay `RetryTemplate` |

### 9.1. Anthropic: RetryTemplate chuyển sang SDK

Trước SDK migration, Anthropic module nhận `RetryTemplate` trong constructor. Sau migration, retry do SDK quản lý qua `maxRetries`; builder không còn nhận `retryTemplate`.

Property:

~~~yaml
spring:
  ai:
    anthropic:
      max-retries: 2
      timeout: 60s
~~~

Nếu ứng dụng có `RetryTemplate` bean chỉ dành cho Anthropic cũ, hãy kiểm tra và gỡ wiring đó. Không thêm retry wrapper mới trước khi biết SDK đã retry những lỗi nào.

### 9.2. OpenAI: kiểm tra hai cấu hình retry

OpenAI reference có cả `spring.ai.openai.max-retries` cho client SDK và `spring.ai.retry.*` cho retry ở Spring AI model layer.

Hai cấu hình nằm ở hai tầng khác nhau. Khi nâng cấp hoặc thay đổi retry policy:

- Kiểm tra effective configuration sau binding;
- Xác định tầng nào retry lỗi HTTP nào;
- Đo số `okhttp.requests` trên một `gen_ai.client.operation`;
- Đặt timeout tổng phù hợp với số attempts và backoff;
- Tránh retry đồng thời ở application, SDK, proxy và gateway mà không có giới hạn tổng.

Không suy ra số HTTP attempts chỉ từ một property `max-retries`; hãy quan sát requests thực tế trong test với lỗi 429, 5xx và timeout.

### 9.3. Connection-pool metrics và executor

OpenAI/Anthropic có thể bind connection-pool gauges khi cung cấp `MeterRegistry`. Các gauges active/idle giúp phân biệt model latency tăng do provider xử lý chậm hay do client pool bị nghẽn.

Nếu cung cấp custom `ExecutorService` cho OkHttp dispatcher, ứng dụng chịu trách nhiệm lifecycle và shutdown của executor đó. Không tạo executor mới cho từng request; quản lý theo vòng đời model/client.

## 10. Quy trình migration instrumentation

1. **Inventory provider:** liệt kê model, starter, SDK version, HTTP client implementation và nơi tạo client.
2. **Kiểm tra dependency tree:** tìm `openai-java`, `anthropic-java`, OkHttp, Spring Web/WebFlux, Micrometer và tracing bridge.
3. **Đối chiếu version:** xác định Spring AI trước/sau M3/M5 và Spring Boot version.
4. **Chuyển provider module:** dùng `spring-ai-openai` thay module OpenAI SDK/Azure cũ; chuyển Anthropic sang builder mới nếu tự khởi tạo.
5. **Chọn đúng customization hook:** OkHttp customizer cho SDK client; Boot builder/customizer cho RestClient/WebClient.
6. **Kiểm tra ObservationRegistry:** xác nhận Boot auto-configuration hoặc truyền registry khi tự tạo model.
7. **Kiểm tra trace tree:** xác nhận model span, HTTP span, trace ID và outbound `traceparent`.
8. **Kiểm tra streaming:** chạy riêng sync và streaming; ghi nhận caveat parent-child của OpenAI streaming.
9. **Kiểm tra retry/timeout:** đo HTTP attempts và tổng model latency với lỗi có thể retry.
10. **Kiểm tra connection pool:** chỉ bật gauges khi cần phân tích capacity.
11. **Loại bỏ instrumentation trùng:** không gắn thêm OkHttp observation interceptor khi wrapper đã có.
12. **Canary rollout:** so sánh model latency, HTTP latency, error rate, retry count và trace completeness trước khi rollout toàn bộ.

## 11. Compatibility test matrix

Tạo fixture dùng mock server hoặc provider-compatible test server. Không gọi endpoint production để kiểm tra việc tạo span.

| Test | Tình huống | Kỳ vọng |
|---|---|---|
| **TC01 — Model observation** | Gọi OpenAI ChatModel | Có `gen_ai.client.operation` |
| **TC02 — HTTP observation** | OpenAI sync call | Có `okhttp.requests` |
| **TC03 — Anthropic model observation** | Gọi Anthropic ChatModel | Có `gen_ai.client.operation` |
| **TC04 — Anthropic HTTP observation** | Anthropic sync call | Có `okhttp.requests` |
| **TC05 — Parent-child OpenAI sync** | OpenAI synchronous call | HTTP span là child của model span |
| **TC06 — OpenAI streaming** | OpenAI stream call | HTTP span tồn tại; kiểm tra parent-link caveat và trace ID |
| **TC07 — Anthropic streaming** | Anthropic stream bằng default client | HTTP span nằm dưới model span |
| **TC08 — Custom Anthropic async** | Inject custom async client | Xác minh observation và parent linkage của client thay thế |
| **TC09 — Trace propagation** | Gửi request qua mock gateway | Có `traceparent` hợp lệ |
| **TC10 — SDK OTel spans** | Dùng default Anthropic client | Không có SDK-native duplicate spans ngoài Spring AI observations |
| **TC11 — Custom SDK client** | Inject client có SDK tracing bật | Nhận diện và xử lý span duplication |
| **TC12 — Boot RestClient** | Tạo client từ `RestClient.Builder` bean | Có `http.client.requests` và trace propagation |
| **TC13 — Boot WebClient** | Tạo client từ `WebClient.Builder` bean | Có `http.client.requests` và trace propagation |
| **TC14 — Direct create** | Dùng `RestClient.create()` hoặc `WebClient.create()` | Xác minh customizers/observation không tự được áp dụng |
| **TC15 — Non-Boot registry** | Tự tạo model với `ObservationRegistry` | Có model và HTTP observations |
| **TC16 — Retry 429** | Provider trả 429 rồi thành công | HTTP attempts được ghi riêng; model operation vẫn được nhận diện |
| **TC17 — Retry 5xx** | Provider trả 503 | Retry đúng policy và có error tags |
| **TC18 — Timeout** | Mock server không trả lời | Timeout/error xuất hiện ở đúng tầng |
| **TC19 — Connection pool** | Bật pool metrics | Có active/idle gauges và client kind |
| **TC20 — Customizer order** | Nhiều customizers | Thứ tự áp dụng đúng `@Order`/registration |
| **TC21 — Anthropic idempotence** | Một model tạo sync và async client | Customizer chịu được hai lần gọi |
| **TC22 — Interceptor duplication** | Gắn interceptor tùy chỉnh | Không phát sinh HTTP observation thứ hai |
| **TC23 — HTTP tag cardinality** | Request có query parameters khác nhau | Không tạo metric label high-cardinality |
| **TC24 — Dependency migration** | Build với Spring AI BOM mới | Không còn module `spring-ai-openai-sdk`/`spring-ai-azure-openai` cũ |
| **TC25 — Boot request factory** | Nâng Spring Boot 3.4.2 | Request factory thực tế và timeout/TLS được xác nhận |
| **TC26 — End-to-end trace** | Một request qua ChatClient, model, HTTP client và gateway | Trace ID, parent-child và số attempts phù hợp |

### 11.1. Assertion nên có trong CI

- Một model call có một model-level observation;
- Mỗi HTTP attempt được ghi đúng một lần;
- `traceparent` có mặt trên outbound request;
- OpenAI streaming caveat được ghi nhận trong expected trace topology;
- Không có metric labels chứa full URL hoặc request identifiers;
- Retry/timeout behavior không thay đổi âm thầm sau khi nâng SDK;
- Customizers không thêm instrumentation trùng;
- Dependency tree không còn SDK module cũ bị loại bỏ.

## 12. Sai lầm thường gặp

| Sai lầm | Hậu quả | Cách sửa |
|---|---|---|
| Dùng `RestClientCustomizer` để cấu hình Anthropic sau migration | Không tác động tới OkHttp trong SDK | Dùng `AnthropicHttpClientBuilderCustomizer` |
| Dùng `WebClient.Builder` để cấu hình OpenAI SDK | Không tác động tới OpenAI OkHttp transport | Dùng `OpenAiHttpClientBuilderCustomizer` |
| Nghĩ không có `http.client.requests` nghĩa là model không được instrument | Bỏ sót `okhttp.requests` | Kiểm tra observation theo transport |
| Cộng model timer với HTTP timer | Đếm trùng latency | Phân biệt boundary model và từng HTTP attempt |
| Tự thêm `OkHttpObservationInterceptor` | Span/metric trùng | Dùng instrumentation có sẵn của Spring AI |
| Nghĩ mọi streaming span có parent | Trace tree bị hiểu sai | Kiểm tra async context propagation theo provider |
| Bỏ `ObservationRegistry` khi tự tạo model | Không có telemetry | Truyền registry trong builder |
| Dùng `RestClient.create()` nhưng kỳ vọng Boot propagation | Trace không được truyền tự động | Inject auto-configured builder |
| Gỡ retry cũ mà không kiểm tra SDK retry | Thay đổi số attempts và latency | Test 429/5xx/timeout sau migration |
| Gắn executor tự tạo nhưng không quản lý lifecycle | Thread leak hoặc shutdown lỗi | Quản lý executor theo vòng đời client |
| Bật debug logging SDK rộng trong production | Có thể lộ request metadata/content | Giới hạn scope, redact và tắt sau điều tra |

## 13. Checklist trước khi merge

- [ ] Đã xác định transport thật của từng provider.
- [ ] OpenAI module dùng official `openai-java` theo release line mục tiêu.
- [ ] Anthropic module dùng official `anthropic-java` và builder mới.
- [ ] Không còn import `AnthropicApi` hoặc constructor đã bị loại bỏ.
- [ ] Không còn module `spring-ai-openai-sdk` và `spring-ai-azure-openai` cũ.
- [ ] OkHttp customizer được dùng cho OpenAI/Anthropic SDK transport.
- [ ] RestClient/WebClient customizer chỉ dùng cho Spring HTTP clients tương ứng.
- [ ] ObservationRegistry được wiring ở cả model và HTTP layer.
- [ ] Không thêm HTTP observation interceptor trùng với Spring AI.
- [ ] Trace propagation được kiểm tra bằng `traceparent`.
- [ ] Streaming spans được kiểm tra riêng cho từng provider.
- [ ] Retry, timeout và số HTTP attempts đã được xác minh.
- [ ] Connection-pool metrics chỉ bật khi cần.
- [ ] Customizers Anthropic idempotent.
- [ ] Dependency tree và HTTP request factory được kiểm tra sau nâng Boot.

## 14. Bài luyện tập

### Bài 1 — Không còn http.client.requests

Sau khi nâng Spring AI, dashboard không còn thấy `http.client.requests` cho OpenAI. Bạn cần tìm observation nào và vì sao?

### Bài 2 — Customizer không có tác dụng

Một bean `RestClientCustomizer` thêm header vào mọi REST request, nhưng header không xuất hiện trong Anthropic API calls sau nâng cấp. Hãy xác định transport và customizer phù hợp.

### Bài 3 — Đếm latency

Một `gen_ai.client.operation` có ba `okhttp.requests` spans. Có nên cộng ba HTTP durations với model duration để tính end-to-end latency không? Giải thích.

### Bài 4 — Streaming OpenAI

HTTP span được ghi và `traceparent` được gửi, nhưng HTTP span không có parent là model span. Đây có phải lỗi mất HTTP instrumentation không? Hãy nêu nguyên nhân.

### Bài 5 — Anthropic SDK tracing

Spring AI đã có `okhttp.requests`, nhưng trace còn có span từ Anthropic SDK. Hãy kiểm tra cách tạo client và SDK tracing settings.

### Bài 6 — Retry sau migration

Trước đây ứng dụng truyền `RetryTemplate` vào AnthropicChatModel. Sau nâng cấp builder không còn method đó. Bạn cấu hình retry ở đâu?

### Bài 7 — RestClient không có trace

Một `RestClient` tự tạo bằng static factory không truyền trace ID. Vì sao Boot auto-config không áp dụng? Sửa thế nào?

### Bài 8 — Connection pool

Bạn thấy model latency tăng nhưng HTTP status vẫn 200 và provider processing time ổn định. Các connection-pool gauges có thể giúp điều tra điều gì?

### Bài 9 — Customizer Anthropic chạy hai lần

Một customizer đăng ký external listener hoặc tạo state mỗi lần callback được gọi. Vì sao có thể gây duplicate side effects? Cách thiết kế lại?

### Bài 10 — SDK module bị loại bỏ

Dự án dùng `spring-ai-starter-model-openai-sdk` và `spring-ai-starter-model-azure-openai`. Hãy mô tả hướng migration và các điểm cần kiểm tra trong dependency tree.

### Gợi ý đáp án

1. Tìm `okhttp.requests`; OpenAI SDK transport dùng OkHttp wrapper riêng, còn `http.client.requests` dành cho Spring `RestClient`/`WebClient`/`RestTemplate`.
2. Anthropic SDK dùng OkHttp từ 2.0.0-M3. Dùng `AnthropicHttpClientBuilderCustomizer`.
3. Không. Model observation bao phủ toàn bộ model call; HTTP observations là các attempt nằm trong khoảng đó. Cộng chúng sẽ double-count.
4. Không nhất thiết. OpenAI async streaming nhảy sang `ForkJoinPool.commonPool()` làm mất observation context cho parent link, nhưng HTTP span và `traceparent` vẫn tồn tại.
5. Kiểm tra custom client được inject vào model. Spring AI tắt SDK-native spans trên client do nó tạo, nhưng giữ settings của client tùy chỉnh.
6. Dùng `spring.ai.anthropic.max-retries`/SDK `maxRetries`; default được tài liệu hóa là 2.
7. Static factory không dùng auto-configured builder nên không nhận ObservationRegistry/customizers/trace propagation. Inject `RestClient.Builder` bean và build client từ đó.
8. Active/idle connections, connection reuse, pool saturation và khác biệt sync/async client.
9. Anthropic customizer được gọi một lần cho sync và một lần cho async client. Tách side effect một lần khỏi callback hoặc dùng guard idempotent.
10. Chuyển sang `spring-ai-starter-model-openai` và `spring-ai-openai`; điều chỉnh class names/configuration Azure và xóa starter/module đã bị loại bỏ.

## Tài liệu tham khảo

- [Spring AI 2.1.0 — Observability](https://docs.spring.io/spring-ai/reference/observability/index.html): model-level và HTTP-layer observations, span hierarchy, `traceparent` và streaming caveat.
- [Spring AI 2.1.0 — Upgrade Notes](https://docs.spring.io/spring-ai/reference/upgrade-notes.html): OpenAI SDK transition, module removals, Anthropic SDK transition và Spring Boot 3.4.2 request factory note.
- [Spring AI 2.1.0 — OpenAI Chat](https://docs.spring.io/spring-ai/reference/api/chat/openai-chat.html): `openai-java`, `okhttp.requests`, connection-pool metrics và `OpenAiHttpClientBuilderCustomizer`.
- [Spring AI 2.1.0 — Anthropic Chat](https://docs.spring.io/spring-ai/reference/api/chat/anthropic-chat.html): `anthropic-java`, HTTP observations, SDK spans, custom async client và `AnthropicHttpClientBuilderCustomizer`.
- [Spring AI 2.1.0 — Anthropic SDK Migration](https://docs.spring.io/spring-ai/reference/api/chat/anthropic-migration.html): chuyển `RestClient`/`WebClient` sang SDK, constructor/builder và retry migration.
- [Spring AI — OpenAI HTTP Client Customizer Javadocs](https://docs.spring.io/spring-ai/docs/2.1.x/api/org/springframework/ai/openai/http/okhttp/OpenAiHttpClientBuilderCustomizer.html): customizer của OkHttp client.
- [Spring AI — OpenAI HTTP Client Builder Javadocs](https://docs.spring.io/spring-ai/docs/2.1.x/api/org/springframework/ai/openai/http/okhttp/SpringAiOpenAiHttpClient.Builder.html): interceptor, observation registry, meter registry và pool gauges.
- [Spring AI — Anthropic HTTP Client Customizer Javadocs](https://docs.spring.io/spring-ai/docs/2.1.x/api/org/springframework/ai/anthropic/http/okhttp/AnthropicHttpClientBuilderCustomizer.html): callback và yêu cầu idempotence.
- [Spring Boot 3.5 — Metrics](https://docs.spring.io/spring-boot/3.5/reference/actuator/metrics.html): instrumentation `RestClient`, `WebClient`, `RestTemplate` và metric `http.client.requests`.
- [Spring Boot 4.2 — Tracing](https://docs.spring.io/spring-boot/reference/actuator/tracing.html): trace propagation, auto-configured builders, sampling và span limits.
- [Spring Framework — HTTP Client Observability](https://docs.spring.io/spring-framework/reference/integration/observability.html): observation `http.client.requests`, registry và low/high-cardinality keys.
- [Micrometer — OkHttp Instrumentation](https://docs.micrometer.io/micrometer/reference/reference/okhttpclient.html): cách instrument OkHttp bằng Observation.
- [Micrometer — Apache HttpComponents Client Instrumentation](https://docs.micrometer.io/micrometer/reference/reference/httpcomponents.html): minh họa cách vị trí observation trước/sau retry handler ảnh hưởng việc đo từng attempt; đây là ví dụ cho Apache HttpComponents, không phải cấu hình cho OkHttp.

**Kết luận:** Sau khi OpenAI và Anthropic chuyển sang official Java SDK, HTTP transport của hai provider được Spring AI instrument qua OkHttp wrapper. Một model call có `gen_ai.client.operation`, còn mỗi HTTP attempt có `okhttp.requests`; `http.client.requests` vẫn dành cho Spring `RestClient`, `WebClient` và `RestTemplate`. Khi nâng cấp, hãy dùng đúng customizer theo transport, giữ `ObservationRegistry` và `traceparent`, kiểm tra streaming/async parent linkage, phân biệt retry ở SDK với retry ở model layer và tránh thêm instrumentation trùng. Những bước đó giúp trace thể hiện đúng model latency, HTTP attempts và lỗi transport qua từng phiên bản Spring AI.
