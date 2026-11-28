# Quan sát mô hình: Khác biệt instrumentation giữa call, stream và các nhà cung cấp

## 1. Vì sao cùng một prompt tạo ra trace khác nhau?

Spring AI cho phép gửi prompt theo hai cách chính: **call đồng bộ** trả về một phản hồi hoàn chỉnh, hoặc **stream** trả về một luồng các phần phản hồi. Hai cách có thể dùng cùng model và prompt, nhưng vòng đời observation, thời điểm nhận metadata và cấu trúc trace không nhất thiết giống nhau.

Provider cũng ảnh hưởng đến instrumentation. Một tích hợp có thể ghi cả model operation và HTTP request; tích hợp khác có model observation nhưng không cung cấp cùng HTTP span. Đường streaming còn có thể chuyển xử lý sang thread khác, làm mất quan hệ parent-child dù span vẫn được ghi.

Bài học thuộc chương **Quan sát mô hình** của module `SPRING_AI_EVALUATION_OBSERVABILITY`. Module kết hợp dataset, relevance, fact checking và kiểm thử RAG/tool calling với metrics, traces, chi phí và độ trễ để tìm nguyên nhân thay đổi qua các phiên bản prompt, model và pipeline.

Sau bài học, bạn có thể:

- Phân biệt observation ở tầng `ChatClient`, `ChatModel` và HTTP transport.
- Hiểu điều gì được đo khi gọi `call()` và khi subscribe `stream()`.
- Đọc cờ streaming và metadata ở model span/client span.
- So sánh OpenAI, Anthropic và các provider khác trong Spring AI 2.1.0.
- Hiểu vì sao OpenAI streaming có HTTP span nhưng thiếu parent link.
- Nhận diện khác biệt về usage, finish reason và retry.
- Phân tích tool loop mà không đếm nhầm số model calls, HTTP attempts và chunks.
- Thiết kế kiểm thử instrumentation theo provider và chế độ gọi.

## 2. Ba tầng quan sát

Một request thường đi qua ba tầng:

| Tầng | Observation/span | Phạm vi |
| --- | --- | --- |
| Framework | `spring.ai.chat.client` | Một lần sử dụng `ChatClient`, gồm advisors và các thao tác con |
| Model/provider | `gen_ai.client.operation` | Một lần gọi `ChatModel.call` hoặc `ChatModel.stream` |
| HTTP transport | Ví dụ `okhttp.requests` | Một HTTP attempt tới provider, nếu adapter instrument tầng này |

~~~mermaid
flowchart TD
    API["HTTP server / API request"] --> CC["spring.ai.chat.client"]
    CC --> ADV["spring.ai.advisor"]
    ADV --> MODEL["gen_ai.client.operation"]
    MODEL --> HTTP["HTTP observation nếu được hỗ trợ"]
    HTTP --> PROVIDER["Provider SDK / API"]
    PROVIDER --> RESP["ChatResponse hoặc stream chunks"]
    MODEL --> USAGE["Model metadata / token usage"]
    CC --> RESULT["Kết quả trả về ứng dụng"]
~~~

`ChatClient` đo trải nghiệm ở tầng framework. `ChatModel` đo thao tác model cụ thể. HTTP observation đo giao tiếp mạng. Một provider có thể hỗ trợ model observation mà không có cùng tên HTTP span hoặc cùng cấu trúc tracing như provider khác.

**Không cộng duration của các span lồng nhau.** Thời gian span con đã nằm trong khoảng thời gian span cha. Chọn tầng theo câu hỏi: endpoint latency, workflow latency, model latency hay HTTP attempt latency.

## 3. Khi gọi đồng bộ: `call()`

Với `ChatModel.call(Prompt)`, phương thức trả về `ChatResponse` sau khi lời gọi hoàn tất. Ở model adapter có hỗ trợ observability, Spring AI tạo observation `gen_ai.client.operation` bao quanh thao tác đó.

Ví dụ trace đồng bộ:

~~~text
POST /api/answer                         1.90 s
  spring.ai.chat.client                   1.72 s
    gen_ai.client.operation               1.48 s
      okhttp.requests                     1.39 s
~~~

Các con số chỉ để minh họa. Model observation có thể ghi:

- `gen_ai.system`: provider được instrumentation nhận diện.
- `gen_ai.request.model`: model được yêu cầu.
- `gen_ai.response.model`: model được response báo về, nếu có.
- `gen_ai.operation.name`: loại operation, thường là `chat`.
- Request options như temperature, top-p và giới hạn token.
- Response ID, finish reason và usage nếu provider cung cấp.
- Trạng thái lỗi nếu lời gọi ném exception.

`ChatResponse` trả về sau lời gọi đồng bộ cho phép ứng dụng đọc metadata ngay trong luồng xử lý. Tuy nhiên, **HTTP thành công không đồng nghĩa câu trả lời đúng**; relevance và fact checking vẫn là các phép đánh giá riêng.

### 3.1. Ví dụ Java

~~~java
import org.springframework.ai.chat.model.ChatModel;
import org.springframework.ai.chat.model.ChatResponse;
import org.springframework.ai.chat.prompt.Prompt;

public final class SyncChatService {

    private final ChatModel chatModel;

    public SyncChatService(ChatModel chatModel) {
        this.chatModel = chatModel;
    }

    public ChatResponse answer(String question) {
        return chatModel.call(new Prompt(question));
    }
}
~~~

Một lần gọi `call()` tương ứng một model operation trong adapter được instrument. Nếu ứng dụng tự retry bằng cách gọi lại method, mỗi lần gọi có thể tạo một model observation riêng. Nếu retry nằm bên trong SDK, một model observation có thể bao quanh nhiều HTTP attempts.

## 4. Khi gọi streaming: `stream()`

`ChatModel.stream(Prompt)` trả về `Flux<ChatResponse>`. Ứng dụng nhận các phần dữ liệu khi provider gửi chúng, thay vì chờ một response hoàn chỉnh.

Trong các adapter reactive, observation của stream thường gắn với **vòng đời subscription**: bắt đầu khi luồng được subscribe và kết thúc khi luồng hoàn tất, lỗi hoặc bị hủy. Chi tiết lifecycle có thể khác giữa adapter và version; khi cần xác định chính xác, hãy kiểm tra tài liệu của provider đang dùng.

~~~text
Subscribe
   |
   v
gen_ai.client.operation (stream=true)
   |
   +--> HTTP request / streaming response
   +--> chunk 1
   +--> chunk 2
   +--> chunk 3
   +--> final chunk / metadata (nếu có)
   |
   +--> onComplete / onError / cancel
   |
   v
Observation.stop()
~~~

Một stream invocation thường là **một model operation**, không phải một model span cho mỗi token hoặc chunk. Các chunk là phần của cùng response stream. Nếu provider retry hoặc phát nhiều HTTP requests, số HTTP attempts có thể lớn hơn một.

### 4.1. Ví dụ Java với Flux

~~~java
import org.springframework.ai.chat.model.ChatModel;
import org.springframework.ai.chat.model.ChatResponse;
import org.springframework.ai.chat.prompt.Prompt;
import reactor.core.publisher.Flux;

public final class StreamingChatService {

    private final ChatModel chatModel;

    public StreamingChatService(ChatModel chatModel) {
        this.chatModel = chatModel;
    }

    public Flux<ChatResponse> stream(String question) {
        return chatModel.stream(new Prompt(question));
    }
}
~~~

Với publisher reactive dạng lazy, request có thể chỉ bắt đầu khi có subscription. Nếu không subscribe hoặc subscriber hủy sớm, không thể mặc định coi đó là một lượt hoàn tất bình thường.

### 4.2. Duration của stream không phải TTFT

Một stream có thể trả chunk đầu sau 150 ms nhưng hoàn tất sau 2,5 giây. Duration của model operation phản ánh thời gian của thao tác stream theo lifecycle adapter; nó **không mặc nhiên là time to first token (TTFT)**.

Nếu cần TTFT, đo riêng thời điểm bắt đầu subscription và thời điểm chunk đầu tiên chứa text mà UI hiển thị. Đồng thời ghi thời điểm stream hoàn tất, lỗi hoặc bị hủy. Không dùng timestamp HTTP headers làm TTFT nếu text đầu tiên chỉ đến trong response body sau đó.

## 5. Cờ streaming khác nhau giữa ChatClient và ChatModel

Spring AI có hai thuộc tính quan sát hữu ích:

| Observation | Attribute | Cardinality | Ý nghĩa |
| --- | --- | --- | --- |
| `spring.ai.chat.client` | `spring.ai.chat.client.stream` | Low cardinality | `ChatClient` đang dùng call hay stream |
| `gen_ai.client.operation` | `gen_ai.request.stream` | High cardinality | Model request ở chế độ stream; chỉ xuất hiện khi `true` |

Điều này tạo ra khác biệt khi phân tích metrics và traces:

- `spring.ai.chat.client.stream` là low-cardinality key, phù hợp làm chiều phân nhóm metrics.
- `gen_ai.request.stream` là high-cardinality key, được ghi ở trace; không nên giả định nó có mặt như label của timer Prometheus.
- Gọi trực tiếp `ChatModel` không tạo observation `spring.ai.chat.client` bao ngoài; model observation vẫn có thể tồn tại nếu adapter hỗ trợ.
- Dùng `ChatClient` có thể tạo cả framework observation và model observation.

**Đừng lấy số stream của ChatClient làm số model streams** nếu một ChatClient invocation gọi model nhiều lần do tool loop, retry ở application layer hoặc evaluator.

## 6. Bảng so sánh call và stream

| Tiêu chí | `call()` | `stream()` |
| --- | --- | --- |
| Kiểu trả về | `ChatResponse` | `Flux<ChatResponse>` |
| Cách nhận dữ liệu | Một response hoàn chỉnh | Nhiều chunks theo thời gian |
| Thời điểm xử lý | Đồng bộ theo lời gọi | Reactive; thực thi khi subscribe trong adapter lazy |
| Model observation | Một operation cho model call | Một operation cho stream invocation được instrument |
| HTTP request | Một request hoặc nhiều attempt do retry | Một stream request hoặc nhiều attempt tùy retry/SDK |
| Metadata usage | Thường có trong response cuối nếu provider báo | Có thể chỉ có ở chunk cuối hoặc thiếu |
| Finish reason | Thường đọc từ generation metadata | Có thể chỉ có khi luồng kết thúc |
| Đo TTFT | Không áp dụng như stream TTFT | Cần đo riêng thời điểm chunk đầu |
| Hủy giữa chừng | Không có subscriber cancel theo cùng nghĩa | Có thể bị cancel; usage có thể không đầy đủ |
| Tool call | Model trả tool request; caller/ChatClient xử lý | Tool-call parts có thể đến qua chunks; vòng xử lý tùy orchestration |

Bảng mô tả hành vi API phổ biến; chi tiết usage, retry và tracing còn tùy provider adapter, SDK và version.

## 7. Provider support: “có observability” không đồng nghĩa “cùng loại span”

Bảng so sánh Chat Models của Spring AI 2.1.0 đánh dấu hỗ trợ observability cho các tích hợp như Anthropic, DeepSeek, Google GenAI, Groq, Mistral AI, MiniMax, NVIDIA, Ollama, OpenAI, OpenAI Responses API, Perplexity, Qxotic jinfer và Amazon Bedrock Converse.

Tuy nhiên, cột **Observability: Yes** không cam kết mọi provider có cùng HTTP instrumentation, cùng tên span, cùng cách nối parent-child hay cùng metadata. Phải phân biệt model-level observation và HTTP-layer observation.

| Tích hợp/provider | Model observation | HTTP-layer detail được tài liệu Spring AI mô tả | Khác biệt cần chú ý |
| --- | --- | --- | --- |
| OpenAI Chat | Có | `okhttp.requests` | Sync nested; streaming HTTP span không parent dưới model span |
| Anthropic | Có | `okhttp.requests` | Sync và stream mặc định nested; custom async client là ngoại lệ |
| Google GenAI | Có trong bảng so sánh 2.1.0 | Không suy ra cùng HTTP span của OpenAI | Kiểm tra metadata và stream lifecycle của adapter |
| Mistral AI | Có trong bảng so sánh 2.1.0 | Không suy ra `okhttp.requests` | Xem model observation và provider transport riêng |
| Ollama | Có trong bảng so sánh 2.1.0 | Không suy ra `okhttp.requests` | Có thể chạy local; endpoint/transport tùy cấu hình |
| DeepSeek | Có trong bảng so sánh 2.1.0 | Không suy ra `okhttp.requests` | Tích hợp OpenAI-compatible; semantics backend vẫn riêng |
| Amazon Bedrock Converse | Có trong bảng so sánh 2.1.0 | Không suy ra `okhttp.requests` | Dùng SDK/API Bedrock; kiểm tra spans từ AWS instrumentation |
| OpenAI-compatible proxy | Có khi dùng tích hợp OpenAI tương ứng | Có thể kế thừa transport của OpenAI module | Không bảo đảm proxy xuất server-side spans hoặc hiểu `traceparent` |

Bảng này phân biệt **khả năng observability chung** với **HTTP-layer detail được mô tả cụ thể**. Khi nâng Spring AI, kiểm tra lại Chat Models Comparison và trang observability của từng provider vì danh sách tích hợp có thể thay đổi.

## 8. OpenAI: call và stream có khác biệt rõ ở HTTP layer

Spring AI 2.1.0 dùng OpenAI Java SDK và phát hai lớp Micrometer observations cho OpenAI:

1. `gen_ai.client.operation` bao quanh `OpenAiChatModel.call(...)` hoặc `stream(...)`.
2. `okhttp.requests` bao quanh từng HTTP attempt, có method, URI, status code và exception tags.

### 8.1. OpenAI synchronous call

Với `call()`, HTTP span được lồng dưới model span:

~~~text
gen_ai.client.operation (OpenAI call)
  └── okhttp.requests
        ├── HTTP method
        ├── URI / host
        ├── status code
        └── exception tags
~~~

`traceparent` cũng được truyền trên request outbound tới gateway, proxy hoặc inference server có hỗ trợ W3C Trace Context.

### 8.2. OpenAI streaming

Với `stream()`, HTTP span vẫn được ghi và timer vẫn được cập nhật, nhưng span HTTP **không được parent trực tiếp** dưới `gen_ai.client.operation`. SDK streaming async chuyển xử lý sang `ForkJoinPool.commonPool()` trước khi gọi HTTP client; observation context của thread gọi bị mất tại ranh giới này.

Điều quan trọng:

- Không có parent-child link **không có nghĩa HTTP observation không được tạo**.
- `traceparent` vẫn được gửi trên request outbound.
- Có thể tìm `okhttp.requests` theo host `api.openai.com` và đối chiếu model span bằng trace ID hoặc khoảng thời gian.
- Không chỉ lọc child spans của model span khi điều tra streaming.

### 8.3. OpenAI streaming usage là tùy chọn

Với OpenAI Chat Completions API, thuộc tính `spring.ai.openai.chat.stream-usage` mặc định là `false`. Khi bật:

~~~properties
spring.ai.openai.chat.stream-usage=true
~~~

SDK yêu cầu thêm một chunk cuối chứa usage cho toàn request. Chunk này có `choices` rỗng; các chunks khác có trường usage bằng `null`.

Hệ quả:

- Nếu không bật, stream có thể không cung cấp token usage cuối như mong đợi.
- Nếu bật, consumer cần nhận cả chunk cuối không có choice để đọc usage.
- Không cộng usage từ từng chunk nếu các chunk không chứa usage độc lập.
- Đây là hành vi được tài liệu OpenAI Chat Completions mô tả; không tự suy rộng sang mọi API/provider.

OpenAI Responses API có contract riêng; hãy kiểm tra tài liệu tương ứng trước khi áp dụng thuộc tính của Chat Completions.

## 9. Anthropic: streaming mặc định giữ quan hệ model/HTTP

Spring AI 2.1.0 dùng Anthropic Java SDK và phát:

- `gen_ai.client.operation` cho mỗi `AnthropicChatModel.call(...)` hoặc `stream(...)`.
- `okhttp.requests` cho mỗi HTTP attempt tới Anthropic API.

Với cả call và stream, HTTP observation mặc định được lồng dưới model observation. Điều này khác OpenAI streaming.

### 9.1. Ngoại lệ khi truyền custom async client

Nếu ứng dụng tự tạo async client và truyền qua:

~~~java
AnthropicChatModel chatModel = AnthropicChatModel.builder()
        .options(anthropicOptions)
        .anthropicClientAsync(customAsyncClient)
        .observationRegistry(observationRegistry)
        .build();
~~~

Spring AI tiếp tục dùng client đó, nhưng HTTP observations của client tùy chỉnh không được lồng dưới model observation theo cơ chế mặc định. Cần kiểm tra client transport, interceptor và context propagation riêng.

### 9.2. Tránh duplicate SDK spans

Anthropic SDK có thể phát OpenTelemetry spans. Spring AI tắt SDK spans trong những client do Spring AI tự tạo vì model observation và HTTP observation đã bao phủ các request.

Nếu bạn tự tạo client và truyền vào builder, cấu hình tracing SDK của client được giữ nguyên. Khi đó cần kiểm tra xem SDK spans và Spring AI observations có ghi trùng cùng một request không.

Anthropic còn có thể xuất server-side spans như `anthropic.messages.create`. Để chúng nối vào trace ứng dụng, cần `traceparent`, cấu hình telemetry phía Claude Console và cùng observability backend. Đây là telemetry phía provider, không phải span do Spring AI tạo.

## 10. Các provider khác: đọc đúng mức hỗ trợ

Với Google GenAI, Mistral, Ollama, Bedrock Converse và các adapter khác, bắt đầu bằng việc kiểm tra `gen_ai.client.operation` có xuất hay không. Sau đó kiểm tra riêng:

- `call()` và `stream()` có cùng observation convention không?
- Stream observation có bắt đầu khi subscribe và dừng khi terminal signal không?
- Provider có trả response ID, finish reason và token usage không?
- Có HTTP client instrumentation riêng không?
- SDK có retry nội bộ hay Spring AI retry template?
- Client có thể được thay thế bằng custom transport không?
- Context propagation có hoạt động qua executor/thread/reactive boundary không?

Không dùng tên `okhttp.requests` làm tiêu chí bắt buộc cho mọi adapter. Tên đó là chi tiết của transport tích hợp OpenAI/Anthropic được Spring AI mô tả; provider khác có thể dùng SDK, HTTP client và span naming khác.

### 10.1. OpenAI-compatible endpoint

DeepSeek, Groq, NVIDIA hoặc Perplexity có thể được truy cập qua OpenAI module theo cấu hình endpoint tương thích. Khi dùng cùng `OpenAiChatModel`, model/HTTP instrumentation của OpenAI module là điểm xuất phát để kiểm tra.

Tuy nhiên, API-compatible chỉ nói về contract giao tiếp. Backend có thể không hỗ trợ đầy đủ headers, usage, finish reasons hoặc server-side tracing như OpenAI thật. Hãy kiểm tra response metadata và trace thực tế thay vì suy ra từ tên provider.

## 11. Tool calling làm thay đổi số model operations

Từ Spring AI 2.0, `ChatModel.call(prompt)` và `ChatModel.stream(prompt)` trả về response của model, bao gồm yêu cầu gọi tool; bản thân low-level `ChatModel` không tự chạy tool loop nội bộ.

Với `ChatClient`, `ToolCallingAdvisor` có thể điều phối vòng lặp:

~~~mermaid
sequenceDiagram
    participant U as User
    participant CC as ChatClient
    participant M as ChatModel
    participant T as Tool
    U->>CC: Question
    CC->>M: Model call #1
    M-->>CC: Tool call request
    CC->>T: Execute tool
    T-->>CC: Tool result
    CC->>M: Model call #2
    M-->>CC: Final response
    CC-->>U: Answer
~~~

Trong trace, một ChatClient operation có thể chứa:

- Nhiều `gen_ai.client.operation` spans.
- Một hoặc nhiều `spring.ai.tool` spans.
- Advisor spans, retrieval spans và các bước khác.

Streaming cũng có thể tương tác với tool calling; provider có thể phát tool-call arguments thành từng phần. Không xem một user request bằng một model call.

### 11.1. Đếm đúng khi so call và stream

| Đại lượng | Đếm ở đâu |
| --- | --- |
| Số user-facing workflows | `spring.ai.chat.client` |
| Số model invocations | `gen_ai.client.operation` |
| Số HTTP attempts | HTTP observation của provider/SDK |
| Số tool executions | `spring.ai.tool` |
| Số stream chunks | Publisher/application instrumentation riêng |

Không lấy số chunks làm số model calls. Không lấy số HTTP attempts làm số user requests. Nếu tool loop gọi model hai lần, đó là hai model operations trong một workflow.

## 12. Metrics: phân biệt ChatClient với ChatModel

Spring AI dùng Micrometer Observation. Với Prometheus, các series quan trọng gồm:

| Metric | Ý nghĩa |
| --- | --- |
| `spring_ai_chat_client_seconds_count` | Số ChatClient operations đã hoàn tất |
| `spring_ai_chat_client_seconds_sum` | Tổng thời gian ChatClient operations |
| `spring_ai_chat_client_active_seconds_count` | Số ChatClient operations đang chạy |
| `gen_ai_client_operation_seconds_count` | Số model operations đã hoàn tất |
| `gen_ai_client_operation_seconds_sum` | Tổng thời gian model operations |
| `gen_ai_client_operation_active_seconds_count` | Số model operations đang chạy |
| `gen_ai_client_token_usage_total` | Counter token usage khi provider báo |

Tên series phụ thuộc registry; hãy xác nhận ở `/actuator/prometheus`. Metric ChatClient có label `spring_ai_chat_client_stream` để phân biệt call/stream ở tầng framework. Trong khi đó `gen_ai.request.stream` của model là high-cardinality trace attribute, không nên mặc định có mặt trong labels của timer.

### 12.1. Tốc độ model calls theo provider

~~~promql
sum by (gen_ai_system) (
  rate(gen_ai_client_operation_seconds_count{
    gen_ai_operation_name="chat"
  }[5m])
)
~~~

Query này đếm model operations hoàn tất, không đếm chunks và không đếm HTTP attempts.

### 12.2. Latency trung bình của model calls

~~~promql
sum by (gen_ai_system) (
  rate(gen_ai_client_operation_seconds_sum{
    gen_ai_operation_name="chat"
  }[5m])
)
/
sum by (gen_ai_system) (
  rate(gen_ai_client_operation_seconds_count{
    gen_ai_operation_name="chat"
  }[5m])
)
~~~

Đây là mean duration. Muốn P95/P99 phải bật histogram buckets; Spring Boot không xuất buckets mặc định cho mọi timer.

### 12.3. Stream và call ở tầng ChatClient

~~~promql
sum by (spring_ai_chat_client_stream) (
  rate(spring_ai_chat_client_seconds_count[5m])
)
~~~

Giá trị stream tag là boolean đã được chuẩn hóa thành label. Query này cho biết số ChatClient call/stream hoàn tất theo chế độ. Nó không chứng minh mọi provider có cùng latency hoặc cùng số model operations bên trong mỗi workflow.

### 12.4. Token usage có thể thiếu ở stream

`gen_ai_client_token_usage_total` chỉ tăng theo token usage mà provider báo. Nếu stream không gửi usage cuối, timer vẫn có thể ghi model operation nhưng token counter không tăng.

Vì vậy:

- Không diễn giải token counter không tăng là model không dùng token.
- So sánh coverage usage giữa provider và call/stream.
- Dùng metadata response hoặc provider billing khi cần kiểm toán.
- Không cộng `input`, `output` và `total` cùng lúc.

## 13. Bật observability

Trong Spring Boot, tài liệu Spring AI 2.1.0 nêu các dependency nền tảng:

- `spring-boot-starter-actuator`.
- Một tracing bridge như `micrometer-tracing-bridge-otel` hoặc `micrometer-tracing-bridge-brave`.
- Exporter/collector tương ứng với trace backend và registry metrics.

Ví dụ cấu hình sampling để thử nghiệm:

~~~yaml
management:
  endpoints:
    web:
      exposure:
        include: health,info,metrics,prometheus
  tracing:
    sampling:
      probability: 1.0
~~~

`probability: 1.0` phù hợp cho demo hoặc test có kiểm soát; production cần cân nhắc lưu lượng, chi phí và chính sách sampling. Cấu hình Actuator không tự tạo trace backend.

Với ứng dụng không dùng Spring Boot, truyền `ObservationRegistry` vào builder của model provider khi builder hỗ trợ. Registry cần có handlers/tracing bridge phù hợp; chỉ truyền một registry rỗng không đảm bảo spans được export.

## 14. Kiểm thử khác biệt call, stream và provider

Không nên chỉ xác minh rằng “có một span”. Một bộ integration test hữu ích cần kiểm tra cả cấu trúc và dữ liệu.

| Test case | Điều cần xác minh |
| --- | --- |
| OpenAI `call()` | Có model observation và HTTP observation; HTTP span nested |
| OpenAI `stream()` | Có model observation; HTTP observation vẫn ghi; parent link có thể vắng |
| Anthropic `call()` | Có model observation và HTTP span nested |
| Anthropic `stream()` mặc định | HTTP span nested dưới model span |
| Anthropic custom async client | Kiểm tra transport instrumentation và parent relation riêng |
| Provider khác `call()` | Model observation, provider tag, response metadata |
| Provider khác `stream()` | Observation lifecycle, cancellation, metadata usage |
| Stream bị cancel | Observation kết thúc; trạng thái không bị ghi nhầm thành success |
| Stream có tool call | Phân biệt model operations, tool execution và chunks |
| Provider thiếu token usage | Timer vẫn có thể ghi; token counter không tăng |
| Retry nội bộ SDK | Một model operation có thể liên quan nhiều HTTP attempts |

### 14.1. Integration test với ObservationRegistry

Có thể dùng `TestObservationRegistry` trong test để thu observations mà không cần gửi trace đến backend ngoài. Cấu trúc test khái niệm:

~~~java
// Pseudocode: tên helper và assertion tùy phiên bản test setup.
TestObservationRegistry registry = TestObservationRegistry.create();

// Tạo ChatModel test double hoặc provider model
// đã được cấu hình dùng registry này.
ChatResponse response = chatModel.call(prompt);

// Kiểm tra observation có tên gen_ai.client.operation
// và các low-cardinality keys như gen_ai.system/model.
~~~

Với stream, phải subscribe và chờ terminal signal trước khi assert observation đã dừng. Chỉ tạo `Flux` rồi kiểm tra ngay có thể dẫn tới kết quả sai vì publisher chưa thực thi.

Không dùng test double để kết luận HTTP span của SDK thật được tạo. Muốn xác minh HTTP transport, cần integration test dùng HTTP server giả (mock web server) hoặc môi trường test provider-compatible và kiểm tra HTTP observation riêng.

### 14.2. Kiểm thử stream lifecycle

Một bài test stream nên kiểm tra ba đường kết thúc:

- `onComplete`: stream hoàn tất bình thường.
- `onError`: provider/transport phát lỗi.
- `cancel`: subscriber hủy trước khi hoàn tất.

Cả ba cần kết thúc observation để không để active timer tăng mãi. Nhưng trạng thái nghiệp vụ phải khác nhau: complete, failed và cancelled. Không biến cancel thành success chỉ vì publisher đã dừng.

## 15. Chẩn đoán khi call và stream có số liệu khác nhau

| Triệu chứng | Nguyên nhân khả dĩ | Cách điều tra |
| --- | --- | --- |
| Call có usage, stream không có | Provider không gửi usage chunk cuối hoặc chưa bật tùy chọn | Kiểm tra stream usage contract |
| Model span có, HTTP span không có | Adapter không instrument HTTP layer hoặc custom client | Kiểm tra provider docs/transport |
| OpenAI stream có HTTP span rời | Async SDK mất observation context | Tìm `okhttp.requests` toàn backend |
| Anthropic stream có child span | Hành vi mặc định được tài liệu hỗ trợ | Xác minh không dùng custom async client |
| Model timer tăng nhưng token counter không tăng | Provider không báo usage | Kiểm tra response metadata/billing |
| ChatClient count thấp hơn model operation count | Một workflow có nhiều model calls | Kiểm tra tool loops/evaluator |
| Model operation count thấp hơn HTTP attempts | SDK retry bên trong một model call | Kiểm tra retry policy và HTTP spans |
| Stream latency rất cao dù chunk đầu nhanh | Đo full stream duration | Đo TTFT riêng |
| Active operation không giảm | Stream chưa kết thúc, subscriber treo hoặc lifecycle không được dọn | Kiểm tra cancel/error và adapter |
| Provider proxy không có server-side spans | Backend không nhận `traceparent` hoặc không export trace | Kiểm tra W3C propagation và telemetry backend |

### 15.1. Quy trình điều tra

1. Xác định dùng `ChatClient` hay gọi trực tiếp `ChatModel`.
2. Xác định mode call hay stream và provider adapter/version.
3. Tìm `spring.ai.chat.client` và `gen_ai.client.operation`.
4. Xem model span có `gen_ai.request.stream` trong trace hay không.
5. Kiểm tra HTTP observations theo provider docs, không chỉ tìm child span.
6. Đọc status, exception, retry và response metadata.
7. Kiểm tra usage/finish reason có được provider gửi không.
8. Với stream, xác định terminal signal và TTFT.
9. Nếu có tool calling, tách từng model operation khỏi tool span.
10. Ghi kết luận về thiếu span, thiếu parent link, thiếu export hay thiếu metadata thành các trường hợp riêng.

## 16. Bảo vệ dữ liệu và tránh cardinality bùng nổ

Spring AI không xuất prompt/completion mặc định vì chúng có thể chứa dữ liệu nhạy cảm. Các cờ liên quan:

~~~properties
spring.ai.chat.client.observations.log-prompt=false
spring.ai.chat.client.observations.log-completion=false
spring.ai.chat.observations.log-prompt=false
spring.ai.chat.observations.log-completion=false
spring.ai.chat.observations.include-error-logging=false
~~~

Không bật log prompt, completion hoặc tool arguments chỉ để phân biệt call/stream. Thường chỉ cần model, provider, stream flag, latency, status và usage.

Không dùng các giá trị có cardinality cao làm metric labels:

- User ID, email, số điện thoại, order ID.
- Request UUID hoặc case ID duy nhất.
- Raw prompt, response, RAG context hoặc tool arguments.
- API key, bearer token hoặc URI chứa secret.

`spring.ai.tools.observations.include-content` mặc định là `false`. Nếu bật để điều tra tool, cần redaction, phân quyền và retention policy.

## 17. Bài tập thực hành

### Bài 1. Cùng prompt, hai chế độ

Gửi cùng một prompt qua `ChatModel.call()` và `ChatModel.stream()`. So sánh số model observations, duration, usage, finish reason và HTTP spans. Giải thích vì sao stream có nhiều chunks nhưng không nhất thiết có nhiều model operations.

### Bài 2. So sánh OpenAI

Chạy OpenAI call và stream. Xác nhận HTTP span của call nested dưới model span; tìm HTTP span stream trên toàn backend. Thử `spring.ai.openai.chat.stream-usage=true` và quan sát chunk usage cuối.

### Bài 3. So sánh Anthropic

Chạy Anthropic sync và streaming bằng client mặc định. Xác nhận quan hệ parent-child. Trong test riêng, thử custom async client và quan sát thay đổi.

### Bài 4. Provider matrix

Chạy tối thiểu hai provider khác nhau, ví dụ Ollama và Google GenAI hoặc Bedrock. Ghi lại model observation, response metadata và transport spans thực tế. Không mặc định cả hai phải có `okhttp.requests`.

### Bài 5. Tool calling

Thực hiện một ChatClient request cần hai vòng model và một tool. Đếm ChatClient operation, model operations và tool observations. So sánh với gọi trực tiếp ChatModel để thấy low-level API trả tool request cho caller xử lý.

### Bài 6. Streaming cancel

Subscribe một stream, nhận một vài chunks rồi cancel. Kiểm tra observation đã stop, active timer giảm và usage được ghi là missing/partial nếu không có metadata cuối.

### Bài 7. Dashboard

Tạo dashboard có:
- ChatClient call/stream counts.
- Model operation rate theo provider.
- Mean/P95 model duration.
- Active model operations.
- Token usage và usage coverage.
- HTTP attempts/status nếu provider hỗ trợ.

Đặt tên và mẫu số đúng tầng; không gọi model operation count là user request count.

## 18. Tổng kết

Instrumentation của Spring AI có nhiều lớp và khác biệt giữa call, stream và provider:

- `spring.ai.chat.client` quan sát thao tác ở tầng framework và có cờ `spring.ai.chat.client.stream`.
- `gen_ai.client.operation` quan sát từng model invocation; `gen_ai.request.stream` là trace attribute cho request stream.
- `stream()` trả một Flux gồm nhiều chunks; chunks không tự động tương ứng với nhiều model spans. Duration của stream không phải TTFT.
- OpenAI và Anthropic có thêm HTTP observation `okhttp.requests`. OpenAI streaming ghi HTTP span nhưng thiếu parent link do async SDK; Anthropic streaming mặc định nested trừ custom async client.
- Các provider khác có hỗ trợ observability theo bảng so sánh 2.1.0, nhưng không thể suy ra cùng HTTP span, cùng metadata hay cùng semantics stream.
- Tool loop, retry và evaluator có thể tạo nhiều model operations bên trong một user workflow.
- Usage, finish reason và trace metadata phụ thuộc provider; streaming có thể thiếu usage nếu không có final usage event.

Hãy xây kiểm thử theo ma trận **provider × call/stream × success/error/cancel × tool/retry**, rồi ghép traces với dataset, relevance, fact checking, RAG context và prompt/model versions. Nhờ đó, nhóm phát triển có thể phân biệt lỗi instrumentation, khác biệt SDK/transport và suy giảm chất lượng thực sự.

## Tài liệu tham khảo

- [Spring AI 2.1.0 Reference — Observability](https://docs.spring.io/spring-ai/reference/observability/): ChatClient, Advisor, ChatModel observations, stream attributes, token metrics và privacy defaults.
- [Spring AI 2.1.0 — Chat Models Comparison](https://docs.spring.io/spring-ai/reference/api/chat/comparison.html): provider capabilities và cột Observability.
- [Spring AI 2.1.0 — OpenAI Chat](https://docs.spring.io/spring-ai/reference/api/chat/openai-chat.html): OpenAI model/HTTP observations, streaming parent limitation, stream usage, connection pool và custom HTTP client.
- [Spring AI 2.1.0 — Anthropic Chat](https://docs.spring.io/spring-ai/reference/api/chat/anthropic-chat.html): Anthropic sync/streaming observations, custom async client, SDK spans và server-side tracing.
- [Spring AI 2.1.0 — Metrics and Observability](https://docs.spring.io/spring-ai/reference/observability/index.html): timer, active timer, token counter và metric keys.
- [Spring AI 2.1.0 — Upgrade Notes](https://docs.spring.io/spring-ai/reference/upgrade-notes.html): thay đổi tool execution loop trong ChatModel ở Spring AI 2.0.
- [Spring Boot Reference — Tracing](https://docs.spring.io/spring-boot/reference/actuator/tracing.html): tracing bridge, sampling và context propagation.
- [W3C Trace Context](https://www.w3.org/TR/trace-context/): header traceparent và distributed tracing propagation.
