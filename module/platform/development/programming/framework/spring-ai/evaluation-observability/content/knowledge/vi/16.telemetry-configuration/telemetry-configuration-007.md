# Xác minh một yêu cầu mẫu tạo đủ metric và trace

## 1. Mục tiêu: kiểm tra một request từ đầu đến nơi lưu telemetry

Một ứng dụng Spring AI có thể trả lời câu hỏi bằng RAG, gọi chat model, sử dụng advisor và gọi tool. Khi chạy thử một request, nhóm phát triển cần xác nhận rằng:

- HTTP request được ghi nhận ở tầng ứng dụng.
- Các operation Spring AI thực sự chạy được đo bằng Micrometer.
- Trace chứa những spans cần thiết để lần theo luồng xử lý.
- Trace được export, nhận và truy vấn được ở backend.
- Token usage xuất hiện khi model provider cung cấp metadata usage.
- Những bước RAG/tool chỉ được kỳ vọng xuất hiện khi request thực sự đi qua các bước đó.

Trong module `SPRING_AI_EVALUATION_OBSERVABILITY`, mục tiêu cuối cùng là dùng dữ liệu này để giải thích thay đổi relevance, factual correctness, độ đúng của retrieval/tool, chi phí và độ trễ giữa các phiên bản prompt, model và pipeline.

**Một endpoint trả HTTP 200 chưa chứng minh observability đã hoạt động.** Cần kiểm tra từng tầng từ instrumentation → registry/exporter → receiver → backend → truy vấn. Cũng không thể đòi một request không dùng vector store phải sinh vector-store metric, hoặc một request không gọi tool phải có tool span.

### Kết quả học tập

Sau bài này, người học có thể:

1. Xác định những metric và span dự kiến cho một luồng Spring AI cụ thể.
2. Tạo một request kiểm thử có thể tái hiện và có trace ID biết trước.
3. So sánh số liệu trước/sau request để xác nhận counter/timer tăng.
4. Xác nhận metric HTTP, ChatClient, ChatModel, token usage và VectorStore.
5. Tìm trace trong backend, kiểm tra quan hệ parent/child và các bước bị thiếu.
6. Phân biệt lỗi instrumentation, sampling, export, receiver, storage và query.
7. Xây smoke test có assertion hợp lý, không giả định số lần model call luôn bằng một.
8. Liên kết trace với kết quả evaluation mà không đưa dữ liệu nhạy cảm vào metric labels.

## 2. Kiến trúc kiểm thử và các điểm cần quan sát

Sơ đồ sau minh họa một request RAG có thể gọi tool. Đây là luồng tham chiếu; ứng dụng thực tế có thể bỏ một số bước hoặc gọi model nhiều lần.

~~~mermaid
sequenceDiagram
    participant C as Client / smoke test
    participant A as Spring Boot API
    participant CC as ChatClient / Advisor
    participant VS as VectorStore
    participant M as ChatModel
    participant T as Tool
    participant P as Prometheus
    participant O as OTel Collector
    participant B as Trace backend
    C->>A: POST /api/answers + traceparent
    A->>CC: call()
    CC->>VS: similarity query (nếu bật RAG)
    VS-->>CC: retrieved documents
    CC->>M: model request
    M-->>CC: tool call hoặc answer
    opt Model yêu cầu tool
        CC->>T: execute tool
        T-->>CC: tool result
        CC->>M: follow-up model call
        M-->>CC: final answer
    end
    CC-->>A: answer
    A-->>C: HTTP response
    P->>A: scrape /actuator/prometheus
    A->>O: OTLP spans (đường export độc lập)
    O->>B: export traces
    C->>B: tìm trace theo trace ID
~~~

Metrics và traces là hai đường dữ liệu khác nhau:

| Đường | Thành phần | Điều cần xác minh |
|---|---|---|
| Metrics | Micrometer Observation → MeterRegistry → Prometheus registry/Actuator | Counter/timer có tăng sau request |
| Traces | Observation/Tracing bridge → exporter → Collector → trace backend | Trace được lưu và có spans dự kiến |
| Evaluation | Runner → application → evaluator/result store | PASS/FAIL dựa trên reference, rubric và tool events |

**Prometheus scrape không tạo trace.** Sampling trace cũng không làm giảm counter metrics theo cùng tỷ lệ. Evaluation result phải được lưu độc lập với trace sampling.

## 3. Những tín hiệu Spring AI có thể tạo

Spring AI xây dựng observability trên Micrometer/Spring. Các thành phần cốt lõi có instrumentation gồm ChatClient, advisor, ChatModel, EmbeddingModel và VectorStore. Tool calling cũng tạo observations khi tool được thực thi.

| Thành phần | Metric/observation thường thấy | Span/trace mong đợi |
|---|---|---|
| Spring MVC/WebFlux | `http.server.requests` | HTTP server span hoặc observation tương ứng |
| ChatClient | `gen_ai.chat.client.operation` | ChatClient operation |
| Advisor | `spring.ai.advisor` | Advisor span; có thể bao gồm thời gian của advisor bên trong |
| ChatModel | `gen_ai.client.operation` | Model operation, có provider/model attributes |
| Token usage | `gen_ai.client.token.usage` | Token attributes trong model observation nếu provider trả usage |
| VectorStore | `db.vector.client.operation` | Vector query/add/upsert/delete operation |
| Tool calling | `spring.ai.tool` observation | Tool execution span khi tool thực sự chạy |
| HTTP client | `http.client.requests` hoặc provider-specific observation | HTTP span đến AI gateway/provider khi client được instrument |

Các tên metric dưới đây là tên Prometheus thường thấy trong tài liệu Spring AI stable 1.x. Phiên bản Spring AI, Micrometer naming convention và registry có thể làm thay đổi tên hoặc tập tags; một số tài liệu snapshot đã thể hiện cách đặt tên ChatClient khác. Hãy xác minh trực tiếp trên endpoint /actuator/prometheus của ứng dụng và dùng đúng tài liệu của release đã khóa.

| Metric Prometheus | Loại | Dùng để kiểm tra |
|---|---|---|
| `http_server_requests_seconds_count` | Counter từ Timer | Số request HTTP đã hoàn tất |
| `gen_ai_chat_client_operation_seconds_count` | Counter từ Timer | Số ChatClient call/stream đã hoàn tất |
| `gen_ai_client_operation_seconds_count` | Counter từ Timer | Số operation ở ChatModel/EmbeddingModel |
| `gen_ai_client_token_usage_total` | Counter | Token usage, phân theo token type |
| `db_vector_client_operation_seconds_count` | Counter từ Timer | Số operation VectorStore đã hoàn tất |

Một Timer thường được export thành _seconds_count, _seconds_sum, _seconds_max và có thể có _active_count. Counter usage có thể mang hậu tố _total. Không suy ra p95 từ _seconds_max; muốn tính histogram quantile phải có bucket series và cấu hình histogram phù hợp.

### Metric và span không có quan hệ một-một

- Một HTTP request có thể tạo nhiều model calls do advisor, retry hoặc tool loop.
- Một ChatClient call có thể chứa nhiều advisor và nhiều lần gọi model.
- Một vector query có thể xảy ra trước một hoặc nhiều model calls.
- Token usage chỉ xuất hiện khi provider/client cung cấp metadata usage.
- Một trace có thể bị sampling loại trong khi metrics vẫn tăng.
- Một metric count tăng không đảm bảo trace đã được export thành công.

Vì vậy, smoke test nên xác nhận **có tín hiệu đúng loại và đúng xu hướng**, không hard-code mọi counter phải tăng chính xác một đơn vị.

## 4. Chuẩn bị dependency và cấu hình cho môi trường local

Ví dụ dưới đây dùng Spring Boot 3.5, Actuator, Prometheus registry và Micrometer Tracing bridge OpenTelemetry. Hãy dùng Spring Boot BOM để quản lý phiên bản tương thích. Với dòng Spring AI, ghép Spring Boot 3.5 cùng Spring AI 1.1.x; Spring AI 2.x đi cùng Spring Boot 4.x. Không ghép dependency chỉ vì API nhìn giống nhau.

Gradle:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-actuator'
    runtimeOnly 'io.micrometer:micrometer-registry-prometheus'
    implementation 'io.micrometer:micrometer-tracing-bridge-otel'
    runtimeOnly 'io.opentelemetry:opentelemetry-exporter-otlp'
}
~~~

Ví dụ application-local.yml:

~~~yaml
spring:
  application:
    name: spring-ai-quality-service
  ai:
    chat:
      client:
        observations:
          log-prompt: false
          log-completion: false
    tools:
      observations:
        include-content: false
    vectorstore:
      observations:
        log-query-response: false

management:
  endpoints:
    web:
      exposure:
        include: health,metrics,prometheus
  tracing:
    sampling:
      probability: 1.0
  otlp:
    tracing:
      endpoint: http://localhost:4318/v1/traces
  metrics:
    tags:
      application: spring-ai-quality-service
      environment: local
~~~

Sampling probability 1.0 giúp local dễ kiểm tra trace. Không dùng mặc định này cho production khi chưa tính lượng spans, dữ liệu nhạy cảm và chi phí. Các property log prompt/completion/tool/vector content cần đối chiếu theo phiên bản Spring AI đang chạy; để mặc định tắt khi kiểm thử bằng dữ liệu có thể nhạy cảm.

Nếu dùng Spring Boot 4.x, dependency starter và nhóm property OpenTelemetry khác Boot 3.5. Không copy nguyên cấu hình trên sang Boot 4.x; dùng đúng property metadata của version đang triển khai. Mục tiêu bài học là quy trình xác minh, không phải thay thế hướng dẫn cấu hình version ở bài trước.

## 5. Xác định trước request sẽ đi qua những component nào

Trước khi chạy, viết một expected path ngắn. Ví dụ:

~~~text
POST /api/answers
  -> ChatClient.call()
  -> QuestionAnswerAdvisor (RAG)
  -> VectorStore.query()
  -> ChatModel.call()
  -> optional Tool execution
  -> optional follow-up ChatModel.call()
  -> HTTP response
~~~

Nếu endpoint không dùng QuestionAnswerAdvisor, không được kỳ vọng có VectorStore query. Nếu model không quyết định gọi tool, không được kỳ vọng tool execution span. Nếu provider không trả token usage, thiếu token counter có thể là giới hạn usage metadata chứ không phải trace exporter lỗi.

Ghi lại các điều kiện:

| Điều kiện | Ví dụ |
|---|---|
| Endpoint | POST /api/answers |
| Operation | ChatClient call() |
| RAG | Có/không; vector store nào |
| Tool | Có/không; tool nào được phép |
| Model provider | Tên provider và model config |
| Streaming | false cho request đầu tiên để giảm biến số |
| Sampling | 100% local |
| Trace backend | Collector nhận OTLP, Tempo/Jaeger lưu trace |
| Dataset/fixture | Một case tổng hợp có expected evidence |

Nên bắt đầu bằng request không streaming, không retry và không có tool nếu mục tiêu đầu tiên chỉ là xác minh ChatClient/ChatModel. Sau khi baseline đạt, thêm RAG, rồi tool calling để mỗi lần chỉ thêm một nhóm observation.

## 6. Endpoint mẫu để tạo một ChatClient operation

Nếu ứng dụng chưa có endpoint kiểm thử, đoạn tối giản dưới đây minh họa cách expose một ChatClient call. Nó chỉ tạo model operation; để kiểm tra RAG hoặc tool, hãy gọi endpoint hiện có đã cấu hình advisor/tool tương ứng.

~~~java
import org.springframework.ai.chat.client.ChatClient;
import org.springframework.web.bind.annotation.*;

@RestController
@RequestMapping("/api")
class AnswerController {

    private final ChatClient chatClient;

    AnswerController(ChatClient.Builder builder) {
        this.chatClient = builder.build();
    }

    @PostMapping("/answers")
    AnswerResponse answer(@RequestBody AskRequest request) {
        String content = chatClient.prompt()
                .user(request.question())
                .call()
                .content();
        return new AnswerResponse(content);
    }

    record AskRequest(String question) {}
    record AnswerResponse(String answer) {}
}
~~~

Spring AI tự instrument ChatClient và ChatModel ở các phiên bản có observability support. Không cần tự tạo meter trùng tên để ép metric xuất hiện. Nếu cần theo dõi một bước nghiệp vụ riêng mà framework không instrument, hãy tạo custom Observation với tên/low-cardinality tags do ứng dụng quản lý.

## 7. Bật RAG và tool theo cách có thể kiểm chứng

Để xác minh vector store, request phải thực sự đi qua cấu hình RAG đã instrument. Một flow RAG điển hình:

1. Endpoint nhận câu hỏi.
2. Advisor hoặc retrieval service tạo truy vấn tìm kiếm.
3. VectorStore thực hiện query.
4. Context được đưa vào model prompt.
5. ChatModel tạo câu trả lời dựa trên context.

Để xác minh tool calling:

1. Request/fixture khiến model cần gọi đúng tool đã khai báo.
2. Model trả về tool call.
3. Spring AI thực thi tool.
4. Tool trả kết quả.
5. Model có thể được gọi tiếp để tạo câu trả lời cuối.

**Không gọi tool ghi hoặc thay đổi dữ liệu thật trong smoke test.** Dùng fake service, sandbox hoặc fixture read-only. Để xác minh một tool span, phải xác nhận tool thực sự được thực thi, không chỉ được khai báo trong danh sách tool.

Nếu vector store/tool không có span:

- Kiểm tra request đã đi qua advisor/tool path chưa.
- Kiểm tra component/provider version có hỗ trợ observability không.
- Kiểm tra observation/tracing registry có được kết nối không.
- Kiểm tra trace sampling và exporter.
- Nếu đây là business step tự viết, thêm custom Observation phù hợp thay vì tạo meter giả.

## 8. Tạo một trace ID có thể tìm lại

Khi ứng dụng dùng W3C Trace Context, client có thể gửi traceparent để tạo một trace ID biết trước trong local test. Ví dụ:

~~~text
traceparent: 00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01
~~~

Trong header này:

- 00 là version của Trace Context.
- Chuỗi 32 ký tự hex là trace ID.
- Chuỗi 16 ký tự hex là parent span ID.
- 01 đặt sampled flag.

Trace ID chỉ dùng để tương quan và tìm trace, **không phải credential hoặc bằng chứng quyền truy cập**. Chỉ sử dụng giá trị cố định trong local test; production client phải tạo trace context hợp lệ theo quy trình của mình.

Nếu hệ thống dùng propagation format khác hoặc gateway loại bỏ header, trace ID có thể được tạo mới. Khi đó tìm theo service name và khoảng thời gian, sau đó xác nhận root span của request.

## 9. Gửi request mẫu

Dùng câu hỏi tổng hợp khớp với fixture knowledge base. Không đưa tên khách hàng, mã đơn thật hoặc thông tin cá nhân vào request kiểm thử.

Ví dụ PowerShell:

~~~powershell
$headers = @{
  traceparent = "00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01"
}
$body = @{
  question = "Tóm tắt điều kiện hoàn trả cho sản phẩm chưa sử dụng."
} | ConvertTo-Json
Invoke-RestMethod -Method Post -Uri "http://localhost:8080/api/answers" -Headers $headers -ContentType "application/json" -Body $body
~~~

Ví dụ curl:

~~~bash
curl -i -X POST http://localhost:8080/api/answers \
  -H 'Content-Type: application/json' \
  -H 'traceparent: 00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01' \
  --data '{"question":"Tóm tắt điều kiện hoàn trả cho sản phẩm chưa sử dụng."}'
~~~

Ghi lại thời điểm chạy, HTTP status, trace ID đã gửi và response. Response body không cần được sao chép vào metrics hoặc span attributes. Nếu cần lưu output để chấm evaluation, lưu trong result store được phân quyền.

## 10. Kiểm tra Actuator trước và sau request

Trước request, lấy baseline. Sau request, đợi ít nhất một chu kỳ scrape Prometheus rồi lấy snapshot lần hai.

Endpoint local:

~~~text
GET http://localhost:8080/actuator/health
GET http://localhost:8080/actuator/metrics
GET http://localhost:8080/actuator/prometheus
~~~

PowerShell:

~~~powershell
(Invoke-WebRequest "http://localhost:8080/actuator/prometheus").Content |
  Select-String "http_server_requests|gen_ai_|db_vector"
~~~

Linux/macOS:

~~~bash
curl -s http://localhost:8080/actuator/prometheus \
  | grep -E 'http_server_requests|gen_ai_|db_vector'
~~~

Nếu endpoint /actuator/prometheus trả 404, kiểm tra Prometheus registry dependency và exposure config. Nếu trả 401/403, dùng danh tính được cấp cho smoke test. Không mở rộng toàn bộ Actuator chỉ để vượt qua bước này.

### Snapshot trước/sau quan trọng hơn giá trị tuyệt đối

Nếu ứng dụng đã xử lý traffic khác, giá trị counter tuyệt đối không cho biết request vừa chạy có tạo meter hay không. So sánh:

delta = counter_after - counter_before

Với một request ChatClient call thông thường, kỳ vọng gen_ai_chat_client_operation_seconds_count tăng. ChatModel operation count thường tăng ít nhất một; nếu tool loop/retry có nhiều lần model call, mức tăng có thể lớn hơn một.

## 11. Các metric cần thấy sau request

Tên sau là dạng Prometheus exposition phổ biến từ Spring AI/Spring Boot. Kiểm tra đúng tên trên version thực tế trước khi viết alert hoặc test tự động.

| Metric | Kỳ vọng sau request | Điều kiện |
|---|---|---|
| http_server_requests_seconds_count | Tăng | Endpoint được instrument bởi Spring MVC/WebFlux |
| gen_ai_chat_client_operation_seconds_count | Tăng | ChatClient call()/stream() thực sự chạy |
| gen_ai_client_operation_seconds_count | Tăng | ChatModel operation thực sự chạy |
| gen_ai_client_token_usage_total | Có thể tăng | Provider/client trả usage metadata |
| db_vector_client_operation_seconds_count | Tăng | Request đi qua VectorStore operation |
| JVM/process meters | Đã tồn tại và thay đổi theo runtime | Actuator/Micrometer auto-configuration |

Token usage counter thường có label phân biệt input, output và total qua gen_ai_token_type. Vector store operation thường có tags như db_operation_name, db_system và spring_ai_kind.

### Không hard-code chính xác số lần model call

| Kịch bản | ChatClient count | ChatModel count |
|---|---:|---:|
| Một call đơn giản | Thường tăng 1 | Thường tăng 1 |
| Advisor gọi model thêm | Thường tăng 1 | Có thể tăng nhiều hơn 1 |
| Tool calling và follow-up model | Có thể tăng 1 | Có thể tăng ít nhất 2 |
| Retry | Tùy nơi retry được đặt | Có thể tăng theo số lần thử |
| Streaming | Một operation cho stream | Một operation theo stream completion |

Timer _seconds_count phản ánh operation đã hoàn tất. Gauge _active_count có thể trở về 0 khi scrape sau khi request kết thúc; không dùng nó làm điều kiện bắt buộc của smoke test đã chạy xong.

## 12. Kiểm tra metric bằng PromQL

Trước tiên xác nhận Prometheus đã scrape target:

~~~promql
up{job="spring-ai"}
~~~

Giá trị 1 nghĩa là scrape thành công tại thời điểm đó. Sau đó tìm counter:

~~~promql
gen_ai_chat_client_operation_seconds_count
~~~

~~~promql
gen_ai_client_operation_seconds_count
~~~

~~~promql
gen_ai_client_token_usage_total
~~~

~~~promql
db_vector_client_operation_seconds_count
~~~

Để quan sát thay đổi theo thời gian khi có đủ samples:

~~~promql
increase(gen_ai_chat_client_operation_seconds_count[10m])
~~~

~~~promql
increase(gen_ai_client_operation_seconds_count[10m])
~~~

increase() cần các samples trong time window. Ngay sau lần scrape đầu tiên hoặc khi chỉ có một sample, kết quả có thể trống hoặc chưa ổn định. Trong smoke test đơn lẻ, snapshot Actuator trước/sau thường dễ kiểm chứng hơn.

### p95 không phải điều kiện mặc định của smoke test

Timer _seconds_sum và _seconds_count cho phép tính average duration:

~~~promql
sum(rate(gen_ai_client_operation_seconds_sum[5m]))
/
sum(rate(gen_ai_client_operation_seconds_count[5m]))
~~~

Muốn tính p95 phải có histogram buckets được export. Ví dụ biểu thức nếu metric có _bucket:

~~~promql
histogram_quantile(
  0.95,
  sum by (le) (
    rate(gen_ai_client_operation_seconds_bucket[5m])
  )
)
~~~

Nếu không có _bucket, không được kết luận histogram đang hoạt động chỉ vì _seconds_sum và _seconds_count xuất hiện. Hãy bật cấu hình histogram đúng meter, kiểm tra cardinality và xác nhận bucket series trước khi dùng p95 trong dashboard.

## 13. Kiểm tra trace trong Collector và backend

Sau khi request kết thúc, xác minh theo từng chặng:

1. App có tracing bridge và exporter tương thích.
2. Sampler chọn trace (local có thể đặt xác suất 1.0).
3. Exporter gửi OTLP đúng protocol, endpoint và path.
4. Collector receiver nhận spans.
5. Collector traces pipeline có processor/exporter đang hoạt động.
6. Trace backend nhận và lưu trace.
7. Query API tìm thấy trace theo trace ID hoặc service/time.

Nếu dùng Collector debug exporter trong local, output của Collector có thể cho biết receiver đã nhận spans. Tuy nhiên, điều đó chưa chứng minh trace đã được lưu ở Tempo/Jaeger. Bước cuối vẫn phải query backend.

### Cây trace tham chiếu

Với request ChatClient có RAG và tool, một trace có thể trông như sau:

~~~text
HTTP POST /api/answers
  └── spring.ai.chat.client
      ├── spring.ai.advisor (RAG advisor)
      │   └── db.vector.client.operation (query)
      ├── gen_ai.client.operation (ChatModel)
      ├── spring.ai.tool (nếu model gọi tool)
      └── gen_ai.client.operation (follow-up model, nếu có)
~~~

Tên span hiển thị có thể được chuẩn hóa theo version/provider. Cần xác minh semantics và parent/child relationship, không chỉ so chuỗi tên chính xác.

### Đối chiếu trace ID

Nếu đã gửi W3C traceparent và propagation được bật, tìm trace ID đã biết trong Tempo/Jaeger. Nếu backend không hỗ trợ tìm trực tiếp theo trace ID, tìm service spring-ai-quality-service trong khoảng thời gian request rồi mở trace tương ứng.

Trong trace, kiểm tra:

- Root span đại diện HTTP request.
- ChatClient operation tồn tại.
- Model operation có duration và model/provider metadata phù hợp.
- VectorStore query tồn tại khi RAG được thực thi.
- Tool span tồn tại khi tool thực sự chạy.
- Các spans có cùng trace ID và quan hệ cha/con hợp lý.
- Span status/error attributes phản ánh lỗi thực tế.

Không kỳ vọng mỗi span có cùng duration. Span cha thường bao trùm các span con; không cộng durations của các span lồng nhau để suy ra latency end-to-end.

## 14. Kiểm tra token usage và chi phí

Token usage không phải lúc nào cũng có. Nguồn dữ liệu thường là usage metadata do model provider trả về. Để xác minh:

1. Chạy request với provider/model hỗ trợ usage reporting.
2. Kiểm tra span model có gen_ai.usage.input_tokens, gen_ai.usage.output_tokens hoặc gen_ai.usage.total_tokens khi provider trả.
3. Kiểm tra metric gen_ai_client_token_usage_total và label gen_ai_token_type.
4. Đối chiếu token usage với response metadata của provider nếu có.
5. Tính chi phí bằng bảng giá đúng model, thời điểm và loại token.

Nếu không có usage:

- Kiểm tra provider có trả usage trong response không.
- Kiểm tra streaming mode có yêu cầu bật usage reporting riêng không.
- Kiểm tra adapter/version có chuyển usage metadata sang Spring AI không.
- Ghi null/unavailable trong kết quả kiểm thử, không ước tính token từ số ký tự rồi gọi đó là số đo.

**Chi phí không tự xuất hiện chỉ vì có trace.** Trace có thể chứa usage attributes; để tính tiền cần pricing source có hiệu lực và quy tắc tính input/output/cache token tương ứng.

## 15. Kiểm tra RAG: metric và trace của VectorStore

Một request chỉ được coi là đã kiểm tra RAG khi bằng chứng cho thấy request thực sự truy vấn VectorStore và context được sử dụng trong luồng xử lý.

| Bằng chứng | Nơi kiểm tra |
|---|---|
| VectorStore query counter tăng | Actuator/Prometheus |
| Operation query và DB/provider tag | Metric labels |
| VectorStore span có trong trace | Tempo/Jaeger |
| Số chunk và source IDs hợp lệ | Evaluation runner/result store hoặc trace metadata đã được lọc |
| Câu trả lời grounded vào source | Evaluator đối chiếu reference/rubric |

Không bật xuất toàn bộ query text hoặc retrieved document response chỉ để chứng minh retrieval hoạt động. Spring AI mặc định không export vector query response content vì có thể nhạy cảm; giữ mặc định an toàn và xác nhận bằng metadata tối thiểu.

### Một metric tăng không chứng minh relevance tốt

VectorStore query thành công chỉ chứng minh operation đã chạy. Cần đánh giá relevance/recall/grounding bằng dataset có nhãn hoặc evidence references. Nếu metric tăng nhưng factual correctness giảm, có thể retriever lấy sai tài liệu, prompt không dùng context hoặc model suy diễn ngoài evidence.

## 16. Kiểm tra tool calling

Tool observations được ghi khi thực hiện tool call trong tương tác với chat model. Để xác minh:

1. Tạo fixture khiến model có lý do gọi đúng tool.
2. Xác nhận tool được gọi và trả kết quả.
3. Kiểm tra trace có tool span.
4. Nếu flow có follow-up model call, kiểm tra model operation bổ sung.
5. Đối chiếu tool arguments/result với fixture ở evaluator, không cần export payload thô.

Tool arguments và kết quả có thể chứa thông tin nhạy cảm; Spring AI không export content đó mặc định. Không bật spring.ai.tools.observations.include-content chỉ để smoke test trong môi trường có dữ liệu thật.

**Không có tool span chưa chắc là lỗi** nếu model quyết định trả lời trực tiếp. Ngược lại, có tool span cũng không chứng minh tool trả dữ liệu đúng hoặc hành động được phép; cần kiểm tra tool event/state và hard gates.

## 17. Smoke test tự động: assertion theo điều kiện

Một smoke test tốt xác nhận các điều kiện bắt buộc mà không giả định provider luôn có cùng số model calls.

### Ma trận assertion

| Assertion | Bắt buộc? | Ghi chú |
|---|---|---|
| HTTP response hợp lệ | Có | Kiểm tra status và schema |
| HTTP server metric count tăng | Có nếu HTTP instrumentation bật | So sánh baseline và after |
| ChatClient operation count tăng | Có khi endpoint dùng ChatClient | call()/stream() đã hoàn tất |
| ChatModel operation count tăng | Có khi model được gọi | Có thể lớn hơn 1 |
| Trace query được ở backend | Có nếu tracing/export/backend được cấu hình | Sampling phải giữ trace |
| VectorStore query metric/span | Chỉ khi request đi qua RAG | Không áp dụng cho direct model call |
| Tool span | Chỉ khi tool thực sự được gọi | Không ép model phải gọi tool trong mọi test |
| Token usage metric | Có điều kiện | Phụ thuộc provider usage metadata |
| p95 histogram | Có điều kiện | Chỉ nếu histogram bucket được bật |

### Pseudocode kiểm thử

~~~java
// Pseudocode: thay tên endpoint, DTO và meter theo ứng dụng thực tế.
long httpBefore = readCounter("http.server.requests");
long chatClientBefore = readCounter("gen_ai.chat.client.operation");
long modelBefore = readCounter("gen_ai.client.operation");

Response response = postAnswerWithTraceparent(testQuestion, knownTraceparent);
assertThat(response.status()).isEqualTo(200);

awaitMetricsScrape();

long httpAfter = readCounter("http.server.requests");
long chatClientAfter = readCounter("gen_ai.chat.client.operation");
long modelAfter = readCounter("gen_ai.client.operation");

assertThat(httpAfter).isGreaterThan(httpBefore);
assertThat(chatClientAfter).isGreaterThan(chatClientBefore);
assertThat(modelAfter).isGreaterThan(modelBefore);
assertTraceExists(knownTraceId);
~~~

Đây là pseudocode minh họa, không phải class test có thể biên dịch nguyên trạng. readCounter có thể đọc qua Actuator Metrics API, Prometheus exposition hoặc query backend. Nếu dùng Prometheus scrape, đợi đủ chu kỳ scrape trước khi đọc.

### Không test counter qua rate() ngay sau một request

rate() và increase() cần đủ samples trong time window. Một test chạy ngay sau startup có thể chưa có hai samples để tính rate. Để smoke test một request, dùng meter snapshot trước/sau hoặc query raw counter sau khi scrape.

## 18. Negative controls: chứng minh từng pipeline độc lập

Ngoài happy path, nên có một vài kiểm thử đối chứng trong local/staging:

| Thử nghiệm | Kết quả mong đợi |
|---|---|
| Tắt trace sampling cho một test riêng | Metrics vẫn tăng; trace có thể không được lưu |
| Collector dừng tạm thời | App vẫn phục vụ theo thiết kế; exporter báo lỗi/drop/queue |
| Endpoint OTLP sai | Metrics vẫn có; trace không tới backend |
| Prometheus scrape target DOWN | Trace pipeline có thể vẫn hoạt động |
| Request không dùng RAG | Không kỳ vọng vector query meter/span |
| Request không gọi tool | Không kỳ vọng tool span |
| Provider không trả usage | Token metric có thể vắng mặt |

Khi test parent-based sampling, lưu ý remote traceparent có sampled flag có thể ảnh hưởng quyết định của child. Nếu muốn kiểm tra xác suất root, dùng request không mang parent context hoặc cấu hình flags đúng với mục tiêu test.

Negative control giúp xác định metrics và traces có hai pipeline độc lập, và ngăn đội ngũ hiểu nhầm dashboard trống là model không chạy.

## 19. Những nguyên nhân khiến metric hoặc trace không xuất hiện

| Triệu chứng | Nguyên nhân thường gặp | Kiểm tra tiếp theo |
|---|---|---|
| Actuator có jvm.* nhưng không có HTTP metric | Request chưa chạy hoặc web instrumentation bị tắt | Gọi endpoint, kiểm tra Spring MVC/WebFlux và meter registry |
| HTTP metric có nhưng ChatClient metric không tăng | Endpoint không dùng ChatClient hoặc call chưa hoàn tất | Xác minh code path và operation |
| ChatClient metric có nhưng ChatModel metric không có | ChatClient chưa gọi model, mock/stub bypass instrumentation hoặc lỗi sớm | Kiểm tra model call thực tế |
| Model metric có nhưng token usage thiếu | Provider không trả usage hoặc adapter không map | Kiểm tra response usage metadata |
| Không có vector metric | Request không qua VectorStore hoặc provider/version chưa instrument | Kiểm tra advisor/retriever path |
| Không có tool span | Model không gọi tool hoặc tool instrumentation không được bật | Xác minh tool event |
| Metrics có nhưng không có trace | Thiếu tracing bridge/exporter, sampling loại hoặc export lỗi | Kiểm tra sampler → exporter → Collector |
| Collector nhận nhưng backend không tìm thấy | Exporter/pipeline/storage/query lỗi | Kiểm tra collector exporter và trace backend |
| Trace có root nhưng thiếu span con | Instrumentation không bao phủ bước hoặc context bị đứt | Kiểm tra advisor/client/async propagation |
| Trace ID khác ID test | Gateway bỏ traceparent hoặc propagation format không khớp | Kiểm tra header và propagator |
| Prometheus target DOWN | Sai host/port/path/auth/TLS | Kiểm tra từ network của Prometheus |
| Counter không tăng ngay | Chưa scrape hoặc timer chưa hoàn tất | Chờ scrape, lấy snapshot sau response |
| p95 query trống | Không có histogram buckets hoặc thiếu samples | Kiểm tra _bucket series và histogram config |

## 20. Đọc trace của request và xác định bước chậm

Khi đã tìm được trace:

1. Bắt đầu ở root HTTP server span để biết tổng thời gian request.
2. Tìm ChatClient span để xác định thời gian xử lý orchestration.
3. Xem advisor/RAG span và VectorStore query span.
4. Xem model operation span và HTTP client span đến provider nếu có.
5. Xem tool span và thời gian gọi hệ thống ngoài nếu tool được chạy.
6. So sánh start/end và quan hệ cha/con để tìm phần chiếm nhiều thời gian.

Ví dụ:

| Operation | Duration giả định | Nhận định cần kiểm chứng |
|---|---:|---|
| HTTP request | 2.8 s | Tổng thời gian người dùng chờ |
| RAG advisor | 0.35 s | Bao gồm truy xuất và xử lý advisor bên trong |
| VectorStore query | 0.22 s | Có thể là phần chính của retrieval |
| ChatModel call 1 | 1.1 s | Model tạo tool call hoặc câu trả lời trung gian |
| Tool call | 0.65 s | Gọi service nghiệp vụ |
| ChatModel call 2 | 0.55 s | Model tổng hợp kết quả tool |

Các con số trên chỉ là minh họa. Span lồng nhau có thể chồng thời gian; không cộng duration của mọi hàng để tính tổng request. Dùng waterfall và parent-child relationship để phân tích.

### Lưu ý provider và streaming

Việc một span HTTP của provider được lồng dưới span model có thể phụ thuộc SDK và streaming implementation. Tài liệu Spring AI hiện hành có ghi nhận khác biệt ở OpenAI streaming so với synchronous calls và Anthropic streaming. Nếu trace thiếu quan hệ cha/con ở một provider path, kiểm tra giới hạn SDK/version trước khi kết luận toàn bộ instrumentation bị hỏng.

## 21. Liên kết trace với evaluation result

Smoke test kỹ thuật xác nhận telemetry được tạo. Đánh giá chất lượng vẫn phải do evaluator đảm nhiệm.

Ví dụ result record:

~~~yaml
evaluationResult:
  runId: telemetry-smoke-local-001
  caseId: rag-policy-return-001
  attemptId: 1
  datasetVersion: "1.0.0"
  rubricVersion: "rubric-v1"
  candidate:
    promptVersion: prompt-smoke
    modelConfigVersion: model-local
    retrievalIndexVersion: policy-fixture-v1
  quality:
    relevance: 1.0
    factualCorrectness: 1.0
    passed: true
  observability:
    traceId: "4bf92f3577b34da6a3ce929d0e0e4736"
    httpStatus: 200
    latencyMs: 2800
    inputTokens: null
    outputTokens: null
    estimatedCost: null
~~~

Đây là schema minh họa, không phải output mặc định của Spring AI. Giá trị token/cost là null vì chưa chỉ ra nguồn usage và pricing. Không ghi trace ID, run ID hoặc case ID làm Prometheus labels nếu mỗi giá trị là duy nhất; lưu quan hệ này trong result store có quyền truy cập.

Khi trace bị sampling loại, result record vẫn phải tồn tại. Nếu trace được lưu, traceId cho phép evaluator hoặc người vận hành mở đúng request để xem retrieval/model/tool path.

## 22. Bảo vệ dữ liệu khi xác minh telemetry

Một request smoke test có thể vô tình tạo trace chứa prompt, completion, vector query, retrieved documents, tool arguments hoặc kết quả. Các nội dung này thường lớn và có thể chứa PII hoặc thông tin nội bộ.

Nguyên tắc:

- Dùng fixture tổng hợp và dữ liệu giả.
- Giữ prompt/completion logging tắt theo mặc định.
- Không bật tool content hoặc vector response export chỉ để kiểm tra span.
- Không ghi Authorization, Cookie, API key hoặc secret vào span/log.
- Chỉ lưu model/provider, operation, duration và metadata ít nhạy cảm cần cho điều tra.
- Dùng low-cardinality tags cho metrics; không dùng raw question, user ID hoặc case ID duy nhất.
- Giới hạn quyền truy cập trace backend và retention.
- Xóa dữ liệu test theo chính sách môi trường nếu có raw content được lưu ngoài dự kiến.

**Có trace không đồng nghĩa được phép lưu mọi nội dung của request.** Việc xác minh đủ metric/trace nên dựa trên sự tồn tại và quan hệ của spans, không phụ thuộc vào việc export toàn bộ payload.

## 23. Bài thực hành: kiểm chứng một luồng RAG có tool

Một ứng dụng trả lời câu hỏi về chính sách hoàn trả bằng RAG và có tool đọc trạng thái đơn. Hãy thực hiện:

1. Dùng Spring Boot/Spring AI version đã cố định; ghi rõ provider, model, vector store và tool fixture.
2. Bật Actuator metrics, Prometheus registry và tracing exporter phù hợp.
3. Đặt sampling 100% ở local, dùng Collector và trace backend có thể truy vấn.
4. Chụp baseline của http.server.requests, gen_ai.chat.client.operation, gen_ai.client.operation và db.vector.client.operation.
5. Gửi request với traceparent đã biết và fixture có evidence phù hợp.
6. Chụp metric sau request; xác nhận HTTP, ChatClient, ChatModel và VectorStore counters tăng.
7. Tìm trace theo trace ID; kiểm tra root, advisor, vector query và model spans.
8. Gửi ca thứ hai buộc phải gọi tool read-only; xác nhận tool span và tool event.
9. So sánh token usage trong metric/span với usage metadata của provider nếu có.
10. Chấm câu trả lời bằng relevance/factual correctness và reference; không dùng sự tồn tại của trace làm điểm chất lượng.
11. Tắt tracing trong một test riêng và xác nhận metrics/evaluation vẫn được ghi.
12. Dừng Collector hoặc làm sai endpoint trong local; xác nhận exporter báo lỗi mà app không bị treo vô hạn.
13. Kiểm tra trace không có raw prompt, retrieved document, tool payload hoặc credential ngoài phạm vi được phép.
14. Lưu report gồm version, config, expected path, metric delta, trace ID, quality score và các tín hiệu chưa có nguồn đo.

### Câu hỏi tự kiểm

**Câu 1:** Một request ChatClient gọi tool hai lần và gọi model ba lần. Có phải metric model operation tăng đúng một không?

**Không.** Mỗi model operation hoàn tất có thể tạo một lần ghi timer; số lần tăng phụ thuộc tool loop, advisor và retry.

**Câu 2:** Có gen_ai_client_operation_seconds_count nhưng không có gen_ai_client_token_usage_total. Có thể kết luận tracing hỏng không?

**Không.** Operation timer và token usage là các tín hiệu khác nhau; provider có thể không cung cấp usage metadata.

**Câu 3:** Prometheus target UP nhưng trace backend trống. Cần kiểm tra đâu?

**Tracing pipeline riêng:** sampler, bridge, exporter, Collector receiver/exporter và trace storage/query.

**Câu 4:** Request không dùng VectorStore nhưng không có db_vector_client_operation_seconds_count. Đây có phải lỗi không?

**Không.** Không có operation thì không có vector metric cần tăng.

**Câu 5:** Trace có model span nhưng factual correctness bằng 0. Điều đó nói lên điều gì?

Trace chứng minh model operation đã chạy; evaluator mới xác định nội dung có đúng evidence/reference hay không.

## 24. Checklist nghiệm thu một request mẫu

- [ ] Đã ghi rõ expected request path: HTTP → ChatClient → model và các bước RAG/tool nếu có.
- [ ] Dependency Actuator, Prometheus registry và tracing bridge/exporter phù hợp version.
- [ ] Actuator expose đúng metrics endpoint và được bảo vệ.
- [ ] Trace sampling đủ cho smoke test local.
- [ ] OTLP exporter trỏ đúng Collector receiver, protocol, path và port.
- [ ] Collector traces pipeline được bật và export tới backend.
- [ ] Prometheus scrape target UP và đọc được /actuator/prometheus.
- [ ] HTTP server metric tăng sau request.
- [ ] ChatClient metric tăng khi call()/stream() hoàn tất.
- [ ] ChatModel metric tăng; không hard-code số lần call bằng một.
- [ ] Token usage có nguồn provider; nếu thiếu được ghi nhận là unavailable.
- [ ] VectorStore metric/span chỉ được kỳ vọng khi request thực sự query vector store.
- [ ] Tool span chỉ được kỳ vọng khi tool thực sự chạy.
- [ ] Trace tìm được theo trace ID hoặc service/time và có quan hệ spans hợp lý.
- [ ] Không dùng rate()/increase() trước khi có đủ scrape samples.
- [ ] Không dùng _seconds_max thay p95 hoặc giả định histogram buckets luôn tồn tại.
- [ ] Evaluation result được lưu độc lập với trace sampling.
- [ ] Không đưa PII, prompt, completion, raw retrieval/tool content hoặc secrets vào telemetry ngoài phạm vi được phép.
- [ ] Có negative control cho sampling/export/scrape và ghi lại kết quả.
- [ ] Có báo cáo phiên bản, config, metric deltas, trace ID và quality scores.

### Tài liệu chính thức

- Spring AI Observability: https://docs.spring.io/spring-ai/reference/observability/
- Spring AI version compatibility: https://github.com/spring-projects/spring-ai#readme
- Spring Boot 3.5 Metrics: https://docs.spring.io/spring-boot/3.5/reference/actuator/metrics.html
- Spring Boot 3.5 Tracing: https://docs.spring.io/spring-boot/3.5/reference/actuator/tracing.html
- Spring Boot 4.0 Metrics: https://docs.spring.io/spring-boot/4.0/reference/actuator/metrics.html
- Spring Framework Observability: https://docs.spring.io/spring-framework/reference/integration/observability.html

**Kết luận:** xác minh một request mẫu cần chứng minh cả metrics và traces đã đi qua đúng pipeline. Metric counter/timer cho biết operation đã chạy và đo thời gian; trace cho biết các bước liên kết trong request; evaluator mới xác định câu trả lời và hành vi tool có đúng hay không. Khi kiểm tra theo baseline/delta, điều kiện thực thi và trace ID có thể tìm lại, nhóm có thể phát hiện thiếu instrumentation, sampling hoặc export trước khi dùng telemetry để phân tích regression của Spring AI.
