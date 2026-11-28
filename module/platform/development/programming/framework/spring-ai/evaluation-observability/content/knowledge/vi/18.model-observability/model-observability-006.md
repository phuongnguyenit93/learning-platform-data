# Quan sát mô hình: Tương tác giữa span mô hình và span HTTP phía dưới

## 1. Vì sao cần quan sát cả hai tầng?

Khi ứng dụng Spring AI gọi một nhà cung cấp mô hình, request có thể đi qua nhiều lớp: HTTP endpoint của ứng dụng, `ChatClient`, advisor/RAG, `ChatModel`, SDK và HTTP client của provider. Một span tổng cho biết thao tác mất bao lâu, nhưng chưa đủ để xác định thời gian nằm ở tầng model, SDK, mạng, gateway hay các bước khác trong pipeline.

Spring AI 2.1.0 cung cấp hai lớp quan sát quan trọng cho tích hợp OpenAI và Anthropic:

- **Span mô hình:** `gen_ai.client.operation`, bao quanh lời gọi `ChatModel.call(...)` hoặc `ChatModel.stream(...)`, mang request parameters, response metadata và token usage.
- **Span HTTP:** `okhttp.requests`, bao quanh từng HTTP attempt tới API provider, ghi nhận HTTP method, URI, status code và exception tags.

Với lời gọi đồng bộ, span HTTP được lồng dưới span model. Anthropic streaming cũng giữ quan hệ này khi dùng client mặc định do Spring AI tạo. OpenAI streaming có một giới hạn riêng: HTTP span vẫn được ghi nhưng không được parent trực tiếp dưới model span, vì đường async của SDK làm mất observation context khi chuyển thread.

Bài học thuộc chương **Quan sát mô hình** của module `SPRING_AI_EVALUATION_OBSERVABILITY`. Module kết hợp dataset, relevance, fact checking và kiểm thử RAG/tool calling với metrics, traces, chi phí và độ trễ. Hiểu quan hệ model/HTTP spans giúp xác định tầng gây chậm hoặc lỗi trước khi kết luận model hay prompt đã suy giảm chất lượng.

Sau bài học, bạn có thể:

1. Phân biệt `gen_ai.client.operation` với `okhttp.requests`.
2. Đọc quan hệ parent-child và ý nghĩa duration ở từng tầng.
3. Giải thích khác biệt giữa OpenAI sync, OpenAI streaming, Anthropic sync/streaming và custom async client.
4. Hiểu `traceparent` được truyền tới gateway/proxy như thế nào.
5. Phân tích retry, HTTP status, exception và model metadata trong cùng request.
6. Bật tracing bằng Spring Boot hoặc truyền `ObservationRegistry` khi cấu hình thủ công.
7. Điều tra trường hợp HTTP span không nằm dưới model span mà không kết luận sai rằng instrumentation đã hỏng.
8. Liên kết trace vận hành với chất lượng RAG, tool calling và bộ đánh giá.

## 2. Hai lớp quan sát nằm ở đâu trong luồng xử lý?

Một luồng điển hình:

~~~mermaid
flowchart TD
    API["HTTP request của ứng dụng"] --> CLIENT["spring.ai.chat.client"]
    CLIENT --> ADV["Advisor / RAG / memory"]
    ADV --> MODEL["gen_ai.client.operation"]
    MODEL --> HTTP["okhttp.requests"]
    HTTP --> SDK["Provider API / gateway"]
    SDK --> RESP["Response từ provider"]
    MODEL --> METRICS["Model metrics và token usage"]
    HTTP --> HTTPMETRICS["HTTP metrics / status / exception"]
    CLIENT --> RESULT["Kết quả trả về ứng dụng"]
~~~

Sơ đồ là cấu trúc khái niệm. Trong trace thật, span chỉ xuất hiện khi lớp tương ứng được instrument; vector store, tool và HTTP server có thể tạo nhánh riêng. Không phải mọi implementation `ChatModel` đều dùng OkHttp hoặc xuất `okhttp.requests`.

| Tầng | Observation/span | Phạm vi đo |
| --- | --- | --- |
| HTTP server ứng dụng | Server request observation | Thời gian end-to-end của endpoint |
| `ChatClient` | `spring.ai.chat.client` | Thời gian thao tác client/framework |
| Advisor | `spring.ai.advisor` | Thời gian advisor và các bước lồng bên trong |
| `ChatModel` | `gen_ai.client.operation` | Thao tác model ở tầng Spring AI |
| HTTP client OpenAI/Anthropic | `okhttp.requests` | Từng HTTP attempt tới provider hoặc endpoint tương thích |
| Tool | `spring.ai.tool` | Thời gian thực thi tool callback |

Model span và HTTP span không phải hai tên cho cùng một phép đo. Model span phản ánh **một lần gọi model ở tầng Spring AI**; HTTP span phản ánh **một lần thử giao tiếp mạng**.

## 3. Model span `gen_ai.client.operation` ghi nhận gì?

Spring AI tạo observation này khi gọi `ChatModel.call(...)` hoặc `ChatModel.stream(...)` ở implementation được hỗ trợ. Span có thể chứa:

- Provider: `gen_ai.system`.
- Model được yêu cầu: `gen_ai.request.model`.
- Model được phản hồi báo về: `gen_ai.response.model`, nếu có.
- Operation name: `gen_ai.operation.name`.
- Request parameters như temperature, top-p hoặc giới hạn token.
- Response ID và finish reason khi provider cung cấp.
- Token usage đầu vào, đầu ra, tổng và cache khi có.
- Exception/error của thao tác model nếu lời gọi thất bại.

Model span trả lời câu hỏi: **“Lượt gọi model ở tầng Spring AI diễn ra thế nào?”**

Nó hữu ích để so sánh latency và token usage giữa model/provider. Tuy nhiên, model span không nhất thiết cho biết từng HTTP attempt mất bao lâu hoặc nhận status code nào. Đó là lý do cần quan sát thêm tầng HTTP.

## 4. HTTP span `okhttp.requests` ghi nhận gì?

Trong tích hợp OpenAI và Anthropic được Spring AI 2.1.0 mô tả, HTTP span bao quanh **mỗi HTTP attempt** của SDK. Nó có thể cung cấp:

| Thuộc tính | Ý nghĩa điều tra |
| --- | --- |
| HTTP method | Request dùng POST, GET hay method khác |
| URI/host | Endpoint provider, gateway hoặc proxy |
| HTTP status code | Kết quả HTTP của attempt |
| Exception tags | Lỗi transport/client phát sinh trong attempt |
| Trace context | Header `traceparent` được truyền trên request outbound |

HTTP span trả lời câu hỏi: **“Lần giao tiếp mạng cụ thể này diễn ra thế nào?”**

Ví dụ một model operation mất 2,4 giây, trong đó HTTP attempt mất 2,1 giây. Phần còn lại có thể gồm xử lý trước/sau HTTP, mapping request/response, SDK overhead, backoff hoặc công việc khác. Đây chỉ là cách đọc khái niệm; không được tự đặt tên hiệu số là “Spring AI overhead” nếu chưa instrument các thành phần đó.

### 4.1. Không dùng một tầng thay cho tầng còn lại

Nếu chỉ có HTTP span, bạn có thể xác định endpoint, status và exception nhưng khó biết lượt gọi thuộc model nào, vai trò answer hay judge, hoặc generation kết thúc ra sao.

Nếu chỉ có model span, bạn có thể biết provider/model và tổng thời lượng model operation nhưng khó phân tích chi tiết từng HTTP attempt.

Không suy ra HTTP status từ finish reason; cũng không suy ra chất lượng câu trả lời từ HTTP 200.

## 5. Quan hệ parent-child trong lời gọi đồng bộ

Với lời gọi đồng bộ OpenAI hoặc Anthropic, trace thường có dạng:

~~~text
POST /api/ask                         2.80 s
  spring.ai.chat.client               2.55 s
    gen_ai.client.operation           2.20 s
      okhttp.requests                 2.08 s
~~~

Các duration chỉ là số liệu giả định. Trong cấu trúc này:

- `gen_ai.client.operation` là parent của `okhttp.requests`.
- HTTP span bắt đầu và kết thúc trong phạm vi model operation.
- Trace UI có thể mở rộng model span để xem HTTP attempt bên dưới.
- `traceparent` được truyền qua HTTP để hệ thống downstream có thể tiếp tục trace.

**Không cộng duration parent và child.** Nếu model span là 2,20 giây và HTTP child là 2,08 giây, tổng không phải 4,28 giây. Thời gian child đã nằm trong khoảng thời gian của parent.

Chọn đúng span theo câu hỏi:

- End-to-end latency: span server/API.
- Client workflow latency: `spring.ai.chat.client`.
- Model operation latency: `gen_ai.client.operation`.
- HTTP attempt latency: `okhttp.requests`.

## 6. OpenAI và Anthropic: điểm chung và khác biệt

Spring AI 2.1.0 dùng SDK chính thức của từng provider và cấu hình OkHttp transport có instrumentation cho HTTP.

| Provider / chế độ | Model span | HTTP span | Quan hệ mặc định |
| --- | --- | --- | --- |
| OpenAI `call(...)` | Có | Có | HTTP span nằm dưới model span |
| OpenAI `stream(...)` | Có | Có | HTTP span được ghi nhưng không parented dưới model span |
| Anthropic `call(...)` | Có | Có | HTTP span nằm dưới model span |
| Anthropic `stream(...)` với async client mặc định | Có | Có | HTTP span nằm dưới model span |
| Anthropic streaming với custom async client | Có | Phụ thuộc client được cấu hình | Không nên giả định HTTP span nằm dưới model span |

Một cây span khác nhau không nhất thiết có nghĩa một provider thiếu telemetry. Có thể đó là giới hạn của đường async/SDK.

## 7. OpenAI streaming: HTTP span được ghi nhưng không là child của model span

Đây là ngoại lệ quan trọng trong Spring AI 2.1.0.

Với OpenAI streaming, SDK Java chuyển xử lý async sang `ForkJoinPool.commonPool()` trước khi gọi HTTP client của Spring AI. Tại ranh giới chuyển thread, observation context của thread gọi ban đầu bị mất. Vì vậy:

- `gen_ai.client.operation` vẫn được ghi.
- `okhttp.requests` vẫn được ghi trong registry.
- Timer/metrics vẫn được ghi.
- Header `traceparent` vẫn được truyền trên request outbound.
- Nhưng `okhttp.requests` **không được parent trực tiếp** dưới model span trong trace tree.

Sơ đồ minh họa:

~~~text
POST /api/stream
  spring.ai.chat.client
    gen_ai.client.operation
      (model stream lifecycle)

okhttp.requests
  HTTP attempt tới api.openai.com
  (được ghi nhưng không parented dưới model span)
~~~

Vị trí hiển thị thực tế phụ thuộc trace backend. Tài liệu OpenAI của Spring AI khuyến nghị tìm span `okhttp.requests` theo host `api.openai.com`, sau đó đối chiếu với `gen_ai.client.operation` tương ứng bằng **trace ID hoặc khoảng thời gian**.

### 7.1. Quy trình tìm HTTP span của OpenAI streaming

1. Tìm `gen_ai.client.operation` theo provider, model, operation và thời điểm.
2. Ghi lại trace ID, timestamp bắt đầu/kết thúc và model request.
3. Tìm `okhttp.requests` trên toàn trace backend theo host `api.openai.com`.
4. Đối chiếu trace ID nếu backend hiển thị cùng trace; nếu không, dùng timestamp và khoảng thời gian request.
5. Xem status code, exception tags và số HTTP attempts.
6. Đối chiếu token usage/finish reason ở model span hoặc response metadata.
7. Ghi rõ rằng HTTP span đã được ghi nhưng quan hệ parent không được thể hiện.

Không dùng truy vấn chỉ tìm child spans của `gen_ai.client.operation` để kết luận OpenAI streaming không phát HTTP observations. Cách lọc đó có thể bỏ qua chính HTTP spans cần điều tra.

## 8. Anthropic streaming và custom async client

Với client mặc định do Spring AI xây dựng, Anthropic streaming giữ HTTP span bên dưới `gen_ai.client.operation`. Tài liệu nêu một ngoại lệ: nếu tự truyền client async qua `AnthropicChatModel.builder().anthropicClientAsync(...)`, Spring AI tiếp tục sử dụng client đó, nhưng HTTP observations không được lồng dưới model observation theo cùng cách mặc định.

Khi tự cung cấp client, cần kiểm tra:

- Client có dùng HTTP transport được instrument bởi Spring AI không?
- Có `ObservationRegistry` hoặc interceptor tương ứng không?
- Có propagation `traceparent` trên request outbound không?
- SDK tracing có đang bật song song với Spring AI instrumentation không?
- Có tạo hai span cho cùng một HTTP attempt không?

Spring AI tắt OpenTelemetry spans của Anthropic SDK trong các client **do Spring AI tự tạo**, vì observations model và HTTP đã bao phủ các request. Nếu bạn tự tạo client và truyền vào builder, cấu hình tracing SDK của client đó được giữ nguyên. Nếu bật cả hai cơ chế, hãy kiểm tra trace tree để tránh spans trùng lặp hoặc hai hệ quy chiếu khó ghép.

## 9. `traceparent`: nối trace từ ứng dụng tới gateway/provider

W3C Trace Context dùng header `traceparent` để truyền ngữ cảnh trace giữa các dịch vụ. HTTP client instrumentation của Spring AI gửi header này trên request tới provider, AI gateway, proxy hoặc inference server tương thích.

~~~text
Ứng dụng Spring Boot
  |
  | traceparent: 00-<trace-id>-<parent-id>-<flags>
  v
OkHttp client (Spring AI)
  |
  | HTTP request + traceparent
  v
AI Gateway / Proxy / Inference server
  |
  v
Downstream service spans (nếu hệ thống nhận và xuất trace)
~~~

Việc gửi header **không đảm bảo** provider sẽ xuất span server-side hoặc hiển thị chúng trong cùng backend. Hệ thống đích cần hỗ trợ W3C propagation, xuất spans và gửi chúng về trace backend có thể liên kết.

### 9.1. Anthropic server-side spans

Claude API có thể xuất span phía server, ví dụ `anthropic.messages.create`. Theo tài liệu Spring AI, vì request có `traceparent`, các spans này có thể xuất hiện dưới `okhttp.requests` trong cùng trace nếu telemetry phía Anthropic và ứng dụng cùng gửi về một observability platform.

Một số điều kiện:

- Tổ chức cấu hình telemetry destination ở Claude Console.
- Ứng dụng và Anthropic xuất traces về cùng nền tảng.
- Tài liệu hướng dẫn lọc `service.name=claude-platform`.
- Claude API tuân theo sampled flag trong `traceparent`; request không được sample ở ứng dụng thì server-side span cũng không được xuất.
- Nếu dùng B3 propagation, cần bật thêm W3C propagation để Anthropic nhận `traceparent`.
- Claude Platform trên AWS chưa đọc `traceparent` theo tài liệu hiện hành được tham chiếu; spans của các request này có thể bắt đầu trace riêng.

Đây là telemetry phía provider, **không phải** HTTP span `okhttp.requests` do Spring AI tạo. Hai phía bổ sung cho nhau: một bên mô tả request rời ứng dụng, bên kia mô tả xử lý tại provider.

## 10. Retry: một model operation có thể có nhiều HTTP attempts

Một lời gọi model có thể phải thử HTTP nhiều lần do rate limit, lỗi tạm thời hoặc retry policy của SDK. HTTP observation được tạo cho **mỗi HTTP attempt**; model observation bao quanh thao tác model ở tầng Spring AI.

Ví dụ giả định:

~~~text
gen_ai.client.operation                3.4 s
  okhttp.requests                      0.4 s  HTTP 429
  (backoff)                            1.0 s
  okhttp.requests                      0.5 s  HTTP 503
  (backoff)                            0.5 s
  okhttp.requests                      0.8 s  HTTP 200
~~~

Cấu trúc thực tế phụ thuộc SDK, retry policy và provider adapter. Ví dụ minh họa rằng một model operation có thể liên quan nhiều HTTP attempts, còn thời gian chờ backoff không nhất thiết nằm trong HTTP span của một attempt.

Khi phân tích:

- Đếm `gen_ai.client.operation` để biết số thao tác model ở tầng Spring AI.
- Đếm `okhttp.requests` để biết số HTTP attempts được instrument.
- Đọc status/exception trên từng HTTP span.
- Kiểm tra retry policy ở cả Spring AI và SDK, tránh hai lớp retry nhân số attempt.
- Không xem HTTP 429/503 của attempt đầu là kết quả cuối nếu lần retry sau thành công.
- Không cộng thời lượng model và HTTP để ra latency tổng.

Nếu retry nằm bên trong SDK, một model observation có thể chứa nhiều HTTP attempts. Nếu ứng dụng gọi lại `ChatModel` ở tầng ngoài, có thể xuất hiện nhiều model observations. Cần xác định **retry ở tầng nào** trước khi tính error rate.

## 11. Cấu hình observability trong Spring Boot

Theo tài liệu Spring AI 2.1.0, trong Spring Boot, khi có `spring-boot-starter-actuator` và tracing bridge như `micrometer-tracing-bridge-otel` hoặc `micrometer-tracing-bridge-brave`, hai lớp observations của OpenAI/Anthropic được wiring tự động.

Ví dụ cấu hình ứng dụng:

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

`probability: 1.0` chỉ phù hợp cho demo hoặc tải thử có kiểm soát để quan sát toàn bộ traces. Production cần chọn sampling policy theo lưu lượng, chi phí lưu trữ và yêu cầu điều tra. Cấu hình này không tự tạo Prometheus server hoặc trace backend; exporter/collector phải được cấu hình theo nền tảng đang dùng.

Dependencies cụ thể phụ thuộc Spring Boot version và tracing bridge được quản lý qua BOM. Không trộn artifact names giữa các major version của Spring Boot.

### 11.1. Ứng dụng không dùng Spring Boot

Khi tự tạo model ngoài auto-configuration, truyền `ObservationRegistry` vào builder.

OpenAI:

~~~java
OpenAiChatModel chatModel = OpenAiChatModel.builder()
        .options(openAiOptions)
        .observationRegistry(observationRegistry)
        .build();
~~~

Anthropic:

~~~java
AnthropicChatModel chatModel = AnthropicChatModel.builder()
        .options(anthropicOptions)
        .observationRegistry(observationRegistry)
        .build();
~~~

`observationRegistry` phải được cấu hình cùng observation handlers/tracing bridge phù hợp. Chỉ truyền một registry không có tracing handler thì chưa chắc có trace spans được xuất đến backend. Cần phân biệt **observation được tạo** với **trace exporter nhận dữ liệu**.

### 11.2. Connection-pool metrics là phần bổ sung

Spring AI có thể bind OkHttp connection-pool gauges, ví dụ:

~~~text
okhttp.pool.connection.count
  state=active | idle
  client.kind=sync | async
~~~

Các gauges này hỗ trợ điều tra pool saturation, concurrency và tái sử dụng kết nối. Chúng không thay thế HTTP spans theo từng request và không bắt buộc để tạo parent-child tracing. Tài liệu OpenAI/Anthropic mô tả tùy chọn bật connection-pool metrics qua cấu hình model tương ứng; mặc định chúng tắt.

## 12. Đọc trace để xác định tầng chậm

Giả sử trace đồng bộ minh họa:

~~~text
POST /api/ask                                      2.90 s
  spring.ai.chat.client                            2.65 s
    spring.ai.advisor: retrieval                   0.38 s
      db.vector.client.operation                   0.30 s
    gen_ai.client.operation (openai)               2.10 s
      okhttp.requests (HTTP 200)                   1.95 s
    spring.ai.tool (lookupPolicy)                  0.12 s
~~~

Đây là số liệu giả định. Hãy đọc theo thứ tự:

1. **Endpoint:** tổng thời gian người dùng chờ.
2. **ChatClient:** thời gian ở tầng điều phối.
3. **Advisor/vector store:** thời gian lấy context.
4. **Model span:** thời gian thao tác model.
5. **HTTP child:** thời gian attempt tới provider.
6. **Tool span:** thời gian công cụ thực thi.

Nếu model span chậm và HTTP span chiếm phần lớn thời gian, điều tra network/provider, gateway, server latency và retry. Nếu model span chậm nhưng HTTP span ngắn, kiểm tra phần xử lý SDK, mapping, backoff hoặc các bước chưa được instrument. Nếu ChatClient chậm nhưng model span ngắn, kiểm tra advisor, retrieval, tool và post-processing.

**Không lấy model duration trừ HTTP duration rồi đặt tên “Spring AI overhead”** nếu có nhiều HTTP attempts, asynchronous work hoặc span chưa đầy đủ. Đó chỉ là phần thời gian chưa được giải thích bằng HTTP span đang xem.

## 13. Đọc lỗi ở hai tầng

| Tình huống | HTTP span | Model span | Diễn giải |
| --- | --- | --- | --- |
| HTTP 200 và model trả response | Có status 200 | Thường hoàn tất bình thường | API call thành công; nội dung vẫn cần đánh giá |
| HTTP 429 rồi retry thành công | Nhiều attempts, status khác nhau | Có thể kết thúc thành công | Điều tra quota/retry, không coi attempt đầu là kết quả cuối |
| Timeout/network error | Có thể có exception tag, không có status | Có thể kết thúc bằng exception | Lỗi transport hoặc deadline |
| Provider trả HTTP 400 | Có status 400 | Có thể có exception | Request/model options không hợp lệ hoặc bị từ chối |
| HTTP 200 nhưng response mapping lỗi | HTTP request thành công | Model layer có thể lỗi khi xử lý response | Kiểm tra SDK/adapter/deserialization |
| HTTP 200 và relevance fail | HTTP thành công | Model call có thể thành công | Vấn đề chất lượng nội dung/context/rubric |
| Model yêu cầu tool call | HTTP model call thành công | Có finish reason tool call | Tool execution được quan sát ở span khác |

HTTP status thành công không chứng minh câu trả lời đúng. Model exception cũng không phải lúc nào cung cấp đủ thông tin để biết HTTP attempt nào thất bại; hãy xem cả hai lớp spans và logs đã được bảo vệ.

## 14. Không nhầm latency HTTP với latency người dùng

Một request có thể có nhiều model calls do tool calling, evaluator hoặc retry:

~~~text
ChatClient request
  gen_ai.client.operation #1
    okhttp.requests #1
  spring.ai.tool
  gen_ai.client.operation #2
    okhttp.requests #2
  quality.evaluation
    gen_ai.client.operation #3
      okhttp.requests #3
~~~

Một user request không tương đương một HTTP request hay một model call. Khi tính latency:

- **End-to-end:** span server/API.
- **ChatClient workflow:** `spring.ai.chat.client`.
- **Mỗi model call:** `gen_ai.client.operation`.
- **Mỗi HTTP attempt:** `okhttp.requests`.
- **Tool execution:** `spring.ai.tool`.

Các span lồng nhau đo các phạm vi thời gian khác nhau. Không cộng duration parent-child; không lấy HTTP attempts làm mẫu số của user request rate.

### 14.1. Streaming và time to first token

Một stream có thể trả chunk đầu sớm nhưng tiếp tục chạy lâu. HTTP span không nhất thiết đo riêng **time to first token (TTFT)**; nó đo HTTP request/response theo vòng đời client. Model stream observation cũng không thay thế mốc thời gian chunk đầu được instrument riêng.

Nếu sản phẩm cần TTFT:

1. Ghi thời điểm bắt đầu subscribe.
2. Ghi thời điểm chunk đầu tiên chứa text hiển thị.
3. Ghi thời điểm stream hoàn tất hoặc bị hủy.
4. Tách `onComplete`, `onError` và `cancel`.
5. Không lấy timestamp HTTP response headers làm TTFT nếu text đầu tiên đến sau đó.

## 15. Tùy chỉnh HTTP client: giữ instrumentation khi thay đổi transport

Spring AI cho phép tùy chỉnh HTTP client builder của provider. OpenAI có `OpenAiHttpClientBuilderCustomizer`; Anthropic có `AnthropicHttpClientBuilderCustomizer`. Các hook này dùng để thêm interceptor, cấu hình proxy/SSL, pool hoặc dispatcher executor.

Khi tùy chỉnh:

- Bắt đầu từ builder do Spring AI cung cấp để giữ defaults và observation interceptor.
- Nếu thay transport/client hoàn toàn, xác minh lại HTTP observation và `traceparent` propagation.
- Không tạo interceptor ghi raw prompt hoặc authorization headers.
- Với Anthropic customizer, tài liệu nêu customizer được gọi hai lần cho mỗi model — một lần cho sync client và một lần cho async client. Code customizer cần idempotent.
- Nếu truyền custom Anthropic async client qua `anthropicClientAsync(...)`, kiểm tra riêng quan hệ span cho streaming.
- Nếu bật SDK OpenTelemetry spans song song với Spring AI observations, kiểm tra duplicate spans trước khi triển khai.

Không bỏ instrumentation mặc định chỉ để đổi timeout hoặc proxy nếu builder customizer đã hỗ trợ các cấu hình đó.

## 16. Bảo vệ dữ liệu trong HTTP spans và traces

HTTP span cần host, method, status và exception để điều tra. Nhưng URI, headers hoặc exception message có thể chứa dữ liệu nhạy cảm tùy cấu hình gateway.

Nguyên tắc:

- Không ghi API key, bearer token hoặc authorization headers.
- Không ghi raw prompt, response, tài liệu RAG hay tool arguments chỉ để nối spans.
- Kiểm tra URI và custom headers trước khi xuất telemetry.
- Dùng trace ID để nối logs đã redaction; không dùng user ID làm metric label.
- Giới hạn quyền truy cập trace backend và thời hạn lưu.
- Giữ prompt/completion logging tắt nếu không có nhu cầu debug được phê duyệt.

Spring AI không xuất prompt/completion mặc định vì chúng có thể lớn và nhạy cảm. Bật nội dung chỉ khi có mục đích cụ thể, redaction, phân quyền và chính sách lưu giữ.

## 17. Quy trình điều tra khi không thấy HTTP span dưới model span

1. Xác định provider và phiên bản Spring AI/SDK.
2. Kiểm tra model span `gen_ai.client.operation` có được ghi không.
3. Tìm `okhttp.requests` trên toàn trace backend, không chỉ lọc child spans.
4. Kiểm tra request là sync hay streaming.
5. Với OpenAI streaming, tìm host `api.openai.com` và tương quan bằng trace ID/timestamp.
6. Với Anthropic, kiểm tra có truyền custom async client qua builder hay không.
7. Kiểm tra custom HTTP client có giữ Spring AI instrumentation không.
8. Kiểm tra tracing bridge, `ObservationRegistry`, sampling và exporter.
9. Kiểm tra downstream `traceparent` propagation và backend có gộp spans không.
10. Kết luận riêng: span không được tạo, span không được export, hay span được ghi nhưng parent relation bị mất.

Ba trường hợp này cần cách xử lý khác nhau. **Không thấy child span trong UI chưa chứng minh HTTP request không diễn ra.**

### 17.1. Ma trận triệu chứng

| Triệu chứng | Nguyên nhân có thể | Hướng xác minh |
| --- | --- | --- |
| Có model span, không thấy HTTP span | Provider/transport không được instrument hoặc trace bị filter | Tìm `okhttp.requests` toàn backend, kiểm tra custom client |
| OpenAI sync có child, streaming không có | Giới hạn async context propagation | Tương quan HTTP span bằng host, trace ID hoặc timestamp |
| Anthropic streaming custom async bị tách | Client async do ứng dụng cung cấp | Kiểm tra `anthropicClientAsync(...)` và instrumentation |
| Có HTTP span nhưng không có model span | HTTP client được gọi ngoài ChatModel hoặc model span bị filter | Kiểm tra trace context và code path |
| Có hai HTTP spans giống nhau cho một request | Retry, duplicate instrumentation hoặc SDK spans | So timestamp, attributes và cấu hình tracing |
| Model span lâu hơn HTTP span nhiều | Backoff, xử lý SDK/response, async work hoặc span chưa đầy đủ | Xem retries và các span liên quan |
| Không có server-side spans | Provider không hỗ trợ hoặc chưa cấu hình telemetry | Kiểm tra provider console và W3C propagation |
| HTTP 200 nhưng evaluation fail | API thành công nhưng nội dung không đạt | Xem answer, context, relevance và fact-check verdict |
| Span không cùng trace ID | Context propagation, sampling hoặc backend khác nhau | Kiểm tra `traceparent`, W3C/B3 và collector |

## 18. Bài tập thực hành

### Bài 1. Quan sát lời gọi đồng bộ

Bật Actuator và tracing bridge trong Spring Boot. Gọi OpenAI `ChatModel.call(...)`, tìm `gen_ai.client.operation` và `okhttp.requests`. Ghi provider, model, HTTP status và duration của từng span. Xác nhận HTTP span là child của model span.

### Bài 2. So sánh OpenAI streaming

Thực hiện cùng prompt qua `ChatModel.stream(...)`. Tìm HTTP spans trên toàn backend, kể cả spans không nằm dưới model span. So sánh sync và streaming; giải thích vai trò của `ForkJoinPool.commonPool()` trong việc mất observation context.

### Bài 3. Anthropic streaming

Thực hiện Anthropic streaming với client mặc định Spring AI. Xác nhận HTTP span nằm dưới model span. Nếu thử custom async client trong môi trường riêng, ghi lại sự khác nhau và không giả định parent relation mặc định còn nguyên.

### Bài 4. Kiểm tra traceparent

Gọi một AI gateway do bạn kiểm soát. Xác nhận request mang W3C `traceparent`, sau đó cấu hình gateway xuất server-side span vào cùng trace backend. So sánh trace trước và sau khi gateway hỗ trợ propagation.

### Bài 5. Mô phỏng retry

Tạo một test endpoint trả lỗi tạm thời rồi thành công. Quan sát số HTTP attempts và số model operations. Xác định retry nằm trong SDK, Spring AI hay application layer. Không kết luận số HTTP spans luôn bằng số model spans.

### Bài 6. Phân tích một request RAG

Tạo một request gồm retrieval, model call và tool callback. Đọc span API, ChatClient, advisor, vector store, model, HTTP và tool. Xác định tầng chiếm nhiều thời gian nhất mà không cộng trùng parent/child durations.

### Bài 7. Điều tra trace thiếu child span

Cho một trace có `gen_ai.client.operation` nhưng không thấy `okhttp.requests` bên dưới. Thực hiện quy trình chẩn đoán phần 17: kiểm tra provider, streaming, custom client, sampling, registry và trace backend. Viết kết luận phân biệt “không có span” với “không có parent link”.

## 19. Tổng kết

Trong Spring AI 2.1.0, `gen_ai.client.operation` và `okhttp.requests` quan sát hai tầng khác nhau:

- **Model span** đo thao tác `ChatModel` ở tầng Spring AI và mang model metadata/token usage.
- **HTTP span** đo từng HTTP attempt tới OpenAI/Anthropic, gồm method, URI, status và exception tags.
- Với sync calls, HTTP span được lồng dưới model span. Anthropic streaming mặc định cũng giữ quan hệ này.
- OpenAI streaming ghi HTTP span nhưng không parented dưới model span do async SDK chuyển thread và làm mất observation context. Anthropic streaming dùng custom async client cũng có ngoại lệ.
- `traceparent` cho phép downstream gateway/provider tiếp tục trace nếu họ hỗ trợ W3C propagation và xuất dữ liệu vào backend tương thích.

Chọn đúng tầng span để đọc latency, retry và lỗi; giữ nguyên khác biệt giữa model operation, HTTP attempt và request người dùng. Khi ghép traces với retrieval, tool execution, dataset và kết quả relevance/fact checking, bạn có thể xác định sự cố nằm ở hạ tầng HTTP, SDK/provider, orchestration hay chất lượng nội dung.

## Tài liệu tham khảo

- [Spring AI 2.1.0 Reference — Observability](https://docs.spring.io/spring-ai/reference/observability/index.html): `gen_ai.client.operation`, HTTP observations, parent-child limitation của OpenAI streaming, trace attributes.
- [Spring AI 2.1.0 Reference — OpenAI Chat](https://docs.spring.io/spring-ai/reference/api/chat/openai-chat.html): `okhttp.requests`, `traceparent`, OpenAI streaming async context, connection pool metrics và HTTP client customizer.
- [Spring AI 2.1.0 Reference — Anthropic Chat](https://docs.spring.io/spring-ai/reference/api/chat/anthropic-chat.html): sync/streaming parent-child, custom async client, server-side spans, W3C propagation và HTTP client customizer.
- [Spring Boot Reference — Tracing](https://docs.spring.io/spring-boot/reference/actuator/tracing.html): Micrometer Tracing, propagation và sampling.
- [W3C Trace Context](https://www.w3.org/TR/trace-context/): định dạng header `traceparent` và quy tắc truyền trace context.
