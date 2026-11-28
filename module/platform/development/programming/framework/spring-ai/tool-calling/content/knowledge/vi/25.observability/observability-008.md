# Thiết kế bảng theo dõi và cảnh báo gắn với tác vụ nghiệp vụ

Trong **SPRING_AI_TOOL_CALLING**, mô hình ngôn ngữ có thể yêu cầu chạy `@Tool`, `ToolCallback`, dùng `ToolContext` và đi qua nhiều vòng gọi model trước khi trả lời người dùng. Vì vậy, một dashboard chỉ hiển thị “model còn hoạt động”, số token hoặc số lần gọi tool **không đủ** để biết sản phẩm có giúp người dùng hoàn thành công việc hay không.

Một hệ thống có thể có độ trễ model thấp nhưng liên tục chọn sai công cụ; một tool trả HTTP 200 nhưng dữ liệu sai; một request có token rẻ nhưng khiến người dùng phải thử lại ba lần. Thiết kế quan sát tốt phải đi từ **tác vụ nghiệp vụ**, xuống vòng `ChatClient`, lần gọi `ChatModel`, tool execution và dịch vụ được tool gọi. Cảnh báo phải nói rõ **tác động tới người dùng**, ai chịu trách nhiệm và hành động xử lý nào là an toàn.

Bài học sử dụng tác vụ ví dụ: *người dùng hỏi trạng thái giao hàng của đơn ORD-8F31A2*. Ứng dụng gọi model, dùng tool tra cứu đơn và vận chuyển, rồi tạo câu trả lời. Các ví dụ dựa trên Spring AI 2.1.x, Micrometer, Spring Boot Actuator và Prometheus/Grafana. Tên metric tự định nghĩa trong bài là **ví dụ thiết kế**, không phải metric mặc định của Spring AI.

## 1. Bắt đầu từ câu hỏi nghiệp vụ

Hãy hình dung có ba câu hỏi khác nhau:

1. **Sản phẩm:** “Bao nhiêu người dùng tra cứu được trạng thái đơn hàng trong lần hỏi này?”
2. **Kỹ thuật:** “Tool nào chậm hoặc lỗi khiến việc tra cứu thất bại?”
3. **Chi phí:** “Mỗi lần tra cứu thành công tốn bao nhiêu token, tiền mô hình và phí API vận chuyển?”

Dashboard cần trả lời cả ba; một biểu đồ token không trả lời được câu hỏi thứ nhất.

Định nghĩa một **business task** là nỗ lực hoàn thành mục tiêu cụ thể của người dùng, có `turnId` do server tạo và một kết quả nghiệp vụ được ghi lại ở application boundary. Một tác vụ có thể bao gồm:

- Một request `ChatClient.call()` hoặc `ChatClient.stream()`.
- Một hoặc nhiều lần gọi `ChatModel`.
- Không, một hoặc nhiều tool calls; cùng tool có thể được gọi lại.
- Một hoặc nhiều REST/SDK/database attempts trong một tool.
- Một câu trả lời cuối, từ chối hợp lệ, kết quả một phần hoặc lỗi.

**Không mặc định một `ChatClient` request bằng một model call hay một tool call.** Nếu quy trình gồm hai `ChatClient` độc lập (ví dụ router và assistant chính), cả hai phải được gắn cùng business `turnId` nếu sản phẩm muốn đo chung một tác vụ.

## 2. Mô hình tầng quan sát

~~~mermaid
flowchart TB
    U[HTTP/SSE request từ người dùng] --> B[Business task: order_status_lookup]
    B --> CC[ChatClient + Advisor chain]
    CC --> M1[ChatModel call #1]
    M1 --> T1[Tool call: get_order_status]
    T1 --> O[Order API / Database]
    O --> T1
    T1 --> M2[ChatModel call #2]
    M2 --> T2[Tool call: get_shipment_tracking]
    T2 --> S[Shipping REST / SDK]
    S --> T2
    T2 --> M3[ChatModel call #3]
    M3 --> B
    B --> R[Outcome và chi phí theo task]
    B -. event .-> LEDGER[Ledger / event store]
    CC -. spans, metrics .-> OTEL[Micrometer / OpenTelemetry]
    T1 -. metrics .-> OTEL
    T2 -. metrics .-> OTEL
    OTEL --> DASH[Prometheus / Grafana / Tracing]
    LEDGER --> DASH
    DASH --> ALERT[Alerting + Runbook]
~~~

Mỗi tầng phục vụ một mục đích:

| Tầng | Đơn vị đo | Câu hỏi |
|---|---|---|
| Business task | `turnId` | Người dùng có hoàn thành mục tiêu không? |
| ChatClient | `call()` / `stream()` | Toàn bộ hành trình chat mất bao lâu? |
| ChatModel | Model request | Model nào chậm, lỗi hoặc tiêu nhiều token? |
| Tool callback | Tool execution | Tool nào được đề xuất, chạy, từ chối hoặc trả lỗi? |
| REST/SDK/database | Request attempt | Dịch vụ phụ trợ nào gây lỗi, retry hay chi phí? |
| Ledger/billing | Cost event | Model + dịch vụ ngoài + hạ tầng tốn bao nhiêu? |

Một dashboard chỉ thấy `ChatModel` không thể kết luận nguyên nhân ở tool; dashboard chỉ thấy HTTP client không biết người dùng cuối đã được giải quyết hay chưa.

## 3. Chuẩn hóa tên workflow và kết quả nghiệp vụ

Đặt mã workflow ổn định và do server quyết định, ví dụ:

~~~text
order_status_lookup
shipping_quote
support_ticket_create
payment_status_lookup
~~~

Đừng dùng nguyên prompt người dùng để tạo tên workflow: hàng triệu prompt khác nhau sẽ làm nổ cardinality và có nguy cơ lộ nội dung nhạy cảm.

Nên định nghĩa trạng thái terminal rõ ràng:

| Outcome | Ý nghĩa | Đánh giá tác vụ |
|---|---|---|
| `success` | Đủ dữ liệu, đáp ứng mục tiêu | Thành công |
| `expected_not_found` | Không tìm thấy tài nguyên nhưng trả lời đúng policy | Trường hợp hợp lệ, phân loại riêng |
| `expected_denied` | Từ chối vì quyền; không có truy cập trái phép | Policy hoạt động đúng, không phải lỗi phụ thuộc |
| `partial` | Có một phần dữ liệu; thiếu bước quan trọng | Suy giảm chất lượng |
| `failed` | Lỗi bất ngờ khiến không hoàn tất | Thất bại |
| `cancelled` | Client ngắt, người dùng hủy hoặc timeout | Cần phân loại theo nguyên nhân |
| `unknown` | Không đủ bằng chứng xác định outcome | Không tự xem là thành công |

Một response HTTP 200 hoặc model gửi câu trả lời cuối **không có nghĩa** business task thành công. Với `order_status_lookup`, ứng dụng có thể xác minh rằng nguồn trạng thái hợp lệ đã được tra, tool result đã được đưa vào hội thoại và response không vi phạm quyền. Nếu không có oracle đáng tin để biết câu trả lời hoàn toàn chính xác, phải ghi nhận độ chắc chắn hoặc trạng thái `unknown`, không tạo KPI thành công giả.

### Chọn mẫu số của tỷ lệ thành công

Có hai góc nhìn:

- **Business-resolution rate:** trong số những yêu cầu đủ điều kiện, bao nhiêu tác vụ được giải quyết đúng, kể cả trường hợp “không tìm thấy” hoặc từ chối hợp lệ?
- **Happy-path success rate:** trong số tác vụ có dữ liệu/quyền hợp lệ, bao nhiêu tác vụ nhận kết quả đúng và đủ?

Cần quyết định trước cách xếp `expected_not_found` và `expected_denied` vào mẫu số. Không trộn các trường hợp đó với `failed`: tỷ lệ “lỗi” sẽ bị bóp méo khi lưu lượng yêu cầu trái quyền tăng.

## 4. Định nghĩa SLI, SLO và ngân sách lỗi

**SLI** (Service Level Indicator) là phép đo; **SLO** (Service Level Objective) là mức mục tiêu đặt cho phép đo trong một khoảng thời gian.

Ví dụ một bộ mục tiêu **minh họa**, không phải khuyến cáo phổ quát:

| SLI | Công thức/định nghĩa | SLO minh họa |
|---|---|---|
| Tỷ lệ hoàn thành tác vụ đủ điều kiện | Tác vụ `success` / (`success` + `failed` + `partial`) | ≥ 99% trong 28 ngày |
| Thời gian hoàn tất | End-to-end từ khi nhận đến terminal outcome | p95 ≤ 8 giây |
| Tỷ lệ tool backend lỗi | Tool attempts lỗi hoặc timeout / attempts có kết quả | `<` 1% |
| Tỷ lệ usage thiếu | Tác vụ không có đủ model-usage metadata / tác vụ cần đo | `<` 2% |
| Phí ước tính trên lần thành công | Model + API ngoài + chi phí phân bổ / số tác vụ thành công | Theo ngân sách sản phẩm |
| Unauthorized execution | Số lần tool thực thi ngoài quyền | **0** |

Ở đây “tác vụ đủ điều kiện” cần quy ước rõ khi người dùng tự hủy, app không có quyền xem tài nguyên hay yêu cầu nằm ngoài chức năng sản phẩm. SLO là hợp đồng đo lường, không phải một con số p95 đặt tùy ý trên biểu đồ.

Với mục tiêu availability 99% trong 28 ngày, phần lỗi cho phép là 1% của lượng tác vụ đủ điều kiện trong khoảng đó. Ví dụ 100.000 tác vụ thì ngân sách lỗi là khoảng 1.000 lỗi. Một đợt lỗi nhỏ nhưng kéo dài có thể tiêu hết ngân sách; vì vậy alert nên dùng **tốc độ tiêu ngân sách lỗi** (burn rate), không chỉ nhìn lỗi tức thời.

## 5. Spring AI cung cấp những tín hiệu gì?

Spring AI tích hợp Micrometer Observation cho các bước AI:

| Observation / metric | Tầng | Ý nghĩa |
|---|---|---|
| `spring.ai.chat.client` | ChatClient | Một lần chạy `call()` hoặc `stream()` |
| `spring.ai.advisor` | Advisor | Thời gian thực thi advisor chain |
| `gen_ai.client.operation` | ChatModel | Thời gian, trạng thái và metadata mỗi model call |
| `gen_ai.client.token.usage` | Model usage | Token input/output/total theo model call |
| `spring.ai.tool` | Tool calling | Quan sát việc thực thi tool |
| HTTP/DB observations | REST/SDK/database | Attempts, status, độ trễ phụ thuộc |

Tên Prometheus đã được chuẩn hóa có thể khác tên Observation API. Theo Spring AI observability reference, ví dụ phổ biến là:

~~~text
gen_ai_chat_client_operation_seconds_count
gen_ai_client_operation_seconds_count
gen_ai_client_token_usage_total{gen_ai_token_type="input"}
gen_ai_client_token_usage_total{gen_ai_token_type="output"}
gen_ai_client_token_usage_total{gen_ai_token_type="total"}
~~~

Hãy xác minh tên và labels bằng endpoint metrics thực tế của phiên bản Spring AI/Micrometer đang chạy; không giả định tất cả exporter hay model provider có cùng bộ thông tin.

**Phân biệt hai lớp token:**

- `gen_ai.client.token.usage` cho biết mức dùng **mỗi lần gọi model** khi provider/instrumentation hỗ trợ.
- `ChatClient.call().chatResponse().getMetadata().getUsage()` sau vòng `ToolCallingAdvisor` có thể mang usage **cộng dồn qua các lần gọi model của exchange** trong Spring AI 2.1.x.

Nếu dùng cả hai để lập báo cáo theo turn, không được cộng phần cộng dồn vào những model usage events đã ghi; đó là đếm trùng. Một workflow có nhiều `ChatClient` cũng cần aggregate qua tất cả exchanges đúng `turnId`.

## 6. Cần bổ sung sự kiện nghiệp vụ vào observability

Các metric mặc định không biết “đơn giao hàng đã được trả lời đúng chưa”. Ứng dụng phải chủ động ghi sự kiện kết quả ở tầng nghiệp vụ.

Một bản ghi gợi ý:

~~~json
{
  "schemaVersion": 1,
  "turnId": "t-5f81",
  "workflow": "order_status_lookup",
  "outcome": "success",
  "reasonCode": "DATA_READY",
  "elapsedMs": 2320,
  "modelCallCount": 3,
  "toolCallCount": 2,
  "toolAttempts": 2,
  "modelTokensTotal": 8200,
  "estimatedModelUsd": "0.0125",
  "estimatedExternalUsd": "0.0030",
  "costQuality": "estimated",
  "traceId": "trace-opaque",
  "completedAt": "2026-11-27T07:15:00Z"
}
~~~

Đây là ví dụ sự kiện, **không phải cấu trúc tự sinh của Spring AI**. Trong thực tế nên chia event model/tool/cost riêng để tránh một object gom mọi chi tiết và làm khó idempotency; một summary có thể được tổng hợp từ ledger.

### Khóa và quy tắc đếm

- `turnId`: một nỗ lực của người dùng do server định danh.
- `modelCallId` hoặc `providerRequestId`: từng lần gọi model, phân biệt retry thật với telemetry replay.
- `toolCallId`: ID do model trả; không dùng làm khóa duy nhất toàn hệ thống nếu nó chỉ duy nhất trong phạm vi request/provider.
- `attemptId`: một HTTP/SDK attempt phía sau tool.
- `traceId`: nối chuỗi sự kiện để điều tra, lưu trong traces/logs, không làm Prometheus metric label.

Ghi **một outcome cuối cho một turn**; nếu outbox/message bị gửi lại, hệ thống ingest cần deduplicate bằng khóa phù hợp. Thao tác ghi metric một lần không thay thế được event ledger đáng tin cậy khi cần audit/billing.

## 7. Ví dụ mã đo một tác vụ nghiệp vụ bằng Micrometer

Định nghĩa workflow và outcome thành enum, tránh lấy label từ lời người dùng:

~~~java
public enum WorkflowKey {
    ORDER_STATUS_LOOKUP,
    SHIPPING_QUOTE,
    SUPPORT_TICKET_CREATE
}

public enum TaskOutcome {
    SUCCESS,
    EXPECTED_NOT_FOUND,
    EXPECTED_DENIED,
    PARTIAL,
    FAILED,
    CANCELLED,
    UNKNOWN
}

public record TaskFinished(
    String turnId,
    WorkflowKey workflow,
    TaskOutcome outcome,
    Duration duration,
    BigDecimal estimatedCostUsd,
    boolean costKnown
) {}
~~~

Một recorder tối giản:

~~~java
@Component
public class BusinessTaskMetrics {

    private final MeterRegistry registry;

    public BusinessTaskMetrics(MeterRegistry registry) {
        this.registry = registry;
    }

    public void record(TaskFinished event) {
        String workflow = event.workflow()
            .name().toLowerCase(Locale.ROOT);
        String outcome = event.outcome()
            .name().toLowerCase(Locale.ROOT);

        Tags tags = Tags.of(
            "workflow", workflow,
            "outcome", outcome
        );

        Counter.builder("assistant.task.completed")
            .tags(tags)
            .description("Completed business tasks by outcome")
            .register(registry)
            .increment();

        Timer.builder("assistant.task.duration")
            .tags(tags)
            .publishPercentileHistogram()
            .serviceLevelObjectives(
                Duration.ofSeconds(3),
                Duration.ofSeconds(8)
            )
            .register(registry)
            .record(event.duration());

        if (event.costKnown()
                && event.estimatedCostUsd() != null
                && event.estimatedCostUsd().signum() >= 0) {

            Counter.builder("assistant.task.cost.known")
                .tag("workflow", workflow)
                .register(registry)
                .increment();

            Counter.builder("assistant.task.estimated.cost.usd")
                .tag("workflow", workflow)
                .register(registry)
                .increment(
                    event.estimatedCostUsd().doubleValue()
                );
        }
    }
}
~~~

Đây là **ví dụ instrument**, không phải một hệ thống billing. Những lưu ý:

1. Chỉ gọi `record(...)` khi task đã có terminal outcome; không gọi lại ở từng vòng tool calling.
2. Phải có bước idempotency/dedup trong event processor nếu dùng queue/retry, vì Counter tăng không thể tự phát hiện event lặp.
3. `costKnown=false` không được coi là chi phí 0; cần theo dõi coverage.
4. Không đưa `turnId`, tên khách hàng, `orderNumber`, raw prompt hoặc tenant ID vào metric tags.
5. Histogram tạo nhiều time series; chỉ bật cho bộ label có cardinality thấp.
6. Số tiền có thể cần độ chính xác cao, điều chỉnh hóa đơn hoặc ghi giảm; lưu `BigDecimal` trong ledger. Counter chỉ dùng theo dõi **ước lượng không âm** trên dashboard.

Khi instrumentation đã dùng metrics mặc định của Spring AI, không cần tự ghi lại model tokens vào Counter khác trừ khi có lý do cụ thể và cách chống đếm trùng.

## 8. Thu thập tín hiệu bên trong tool loop nhưng không phá nghiệp vụ

Với một request có hai tool calls, cần tách:

~~~text
Business task bắt đầu
  ChatClient exchange bắt đầu
    ChatModel #1 -> yêu cầu get_order_status
    ToolCallingManager -> get_order_status -> Order API
    ChatModel #2 -> yêu cầu get_shipment_tracking
    ToolCallingManager -> get_shipment_tracking -> Shipping SDK
    ChatModel #3 -> trả lời cuối
  ChatClient exchange kết thúc
Business task hoàn tất, đánh giá outcome
~~~

Những số liệu cần lưu:

- `modelCallCount`: tăng khi bắt đầu một model call mới, không phải khi nhận mỗi response chunk.
- `toolCallCount`: tăng theo lời gọi tool được thực thi, gắn đúng ID.
- `toolAttemptCount`: tăng theo request thực tế ở backend adapter; một tool call có thể retry nhiều lần.
- `toolDeniedCount`: số lần tool bị từ chối bởi policy; không đánh đồng với truy cập trái phép thành công.
- `modelTokenUsage`: ghi theo model request khi provider báo, không giả định luôn có.
- `businessOutcome`: phát một lần ở application boundary sau khi xác định kết quả.

Đối với trace, một `span` model nằm dưới `ChatClient`, tool execution và HTTP calls có thể thành những spans con. Traces giúp trả lời “vì sao task 12 giây?” chứ không chỉ thấy p95 tăng. Chỉ số thời gian advisor lồng nhau có thể bao gồm thời gian của các bước sâu hơn; **không cộng mọi duration span** để tính end-to-end latency, vì chúng có thể chồng lấp.

## 9. Thiết kế dashboard theo ba tầng sử dụng

Một bảng điều khiển tốt không cần nhét mọi metric lên một màn hình. Nên tách màn hình dành cho vận hành theo ba tầng.

### Tầng A — Tổng quan sản phẩm (Product/Business health)

| Panel | Câu hỏi | Trực quan gợi ý |
|---|---|---|
| Task attempts theo workflow | Người dùng đang dùng chức năng nào? | Time series hoặc bar |
| Business resolution rate | Bao nhiêu tác vụ được giải quyết? | Tỷ lệ theo thời gian |
| Expected denial/not found | Bao nhiêu yêu cầu bị từ chối hợp lệ? | Stacked outcome chart |
| Failure/partial rate | Mức suy giảm chất lượng có tăng? | Tỷ lệ theo workflow |
| End-to-end p50/p95/p99 | Người dùng chờ bao lâu? | Time series |
| Cost trên tác vụ thành công | Hiệu quả kinh tế có thay đổi? | USD/task cùng coverage |
| Budget consume | Tác vụ có đốt quá ngân sách? | Burn-up theo ngày |
| Manual handoff rate | Bao nhiêu tác vụ cần con người? | Tỷ lệ theo ngày |

Đặt **outcome và độ trễ** ở đầu bảng, token/cost phía dưới. Người vận hành không nên phải suy luận lỗi sản phẩm từ một biểu đồ CPU hoặc model token.

### Tầng B — AI và tool execution (Engineering)

| Panel | Câu hỏi |
|---|---|
| ChatClient latency và active_count | Có tắc ở toàn flow chat? |
| Model call latency/error rate theo provider/model | Vấn đề ở model hay adapter? |
| Input/output/total tokens theo model | Có phình prompt/tool schema/history? |
| Model calls per business task | Có vòng tool loop dài bất thường? |
| Tool selection breakdown | Tool nào được chọn, từ chối hay không tìm thấy? |
| Tool success/error/timeout theo tool | Callback nào gây suy giảm? |
| Tool attempts per call | Có retry hoặc fan-out tăng? |
| Streaming cancel/TTFT | Người dùng có bỏ chờ trước khi hoàn tất? |

### Tầng C — Phụ thuộc và điều tra (Operations)

| Panel | Câu hỏi |
|---|---|
| REST/SDK status theo dependency | Inventory/Shipping API nào lỗi? |
| p95 backend latency theo endpoint **template** | Bước nào chậm? |
| Rate limit 429 và retry count | Có bị throttling hay retry storm? |
| DB connection pool/query latency | Nút thắt tại database? |
| Traces theo error exemplar | Request mẫu đã qua những bước nào? |
| Incident events/deployment markers | Lỗi bắt đầu sau thay đổi nào? |
| Audit decision summaries | Chính sách có từ chối nhiều hơn bình thường? |

Không hiển thị một danh sách “mọi khách hàng bị lỗi” trên dashboard công khai; dữ liệu mức user/tenant phải tra từ hệ thống audit có kiểm soát quyền.

## 10. Layout bảng theo dõi cho order-status workflow

Một bố cục có thể triển khai trong Grafana:

~~~text
┌─────────────────────────────────────────────────────────────┐
│ Bộ lọc: environment | workflow | release | provider/model   │
├─────────────────────────────────────────────────────────────┤
│ Task attempts  │ Resolution rate  │ p95 latency │ $/success │
├─────────────────────────────────────────────────────────────┤
│ Outcome theo thời gian     │ Error budget burn              │
├─────────────────────────────────────────────────────────────┤
│ Model calls / task         │ Tool attempts / task           │
├─────────────────────────────────────────────────────────────┤
│ Model errors & tokens      │ Tool errors / dependency p95   │
├─────────────────────────────────────────────────────────────┤
│ Unknown usage / coverage   │ Alert history / runbook link   │
└─────────────────────────────────────────────────────────────┘
~~~

Đây là sơ đồ chức năng, không phải yêu cầu cố định về UI. Khi thêm mới `shipping_quote`, có thể tái sử dụng panel bằng label `workflow` cố định mà không tạo một dashboard hoàn toàn khác.

## 11. Từ Micrometer sang Prometheus/Grafana

Spring Boot Actuator và Prometheus registry là một cách phổ biến:

~~~gradle
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-actuator'
    runtimeOnly 'io.micrometer:micrometer-registry-prometheus'
}
~~~

~~~properties
management.endpoints.web.exposure.include=health,info,prometheus
management.metrics.tags.application=order-assistant
~~~

Prometheus scrape endpoint `/actuator/prometheus` qua mạng quản trị được bảo vệ; Grafana đọc từ Prometheus. Nếu dùng hệ thống quan sát qua OTLP/OpenTelemetry, bạn có thể xuất traces/metrics tới collector tương ứng; không nhất thiết dùng Prometheus ở mọi môi trường.

Tên metric do `BusinessTaskMetrics` tạo có thể được Prometheus biểu diễn như:

~~~text
assistant_task_completed_total
assistant_task_duration_seconds_count
assistant_task_duration_seconds_sum
assistant_task_duration_seconds_bucket
assistant_task_cost_known_total
assistant_task_estimated_cost_usd_total
~~~

Tên cuối cùng phụ thuộc naming convention và registry: **kiểm tra endpoint đã export** trước khi sao chép PromQL, đặc biệt với metric có đơn vị, suffix `_total` và histogram.

## 12. PromQL: tỷ lệ thành công nghiệp vụ

Giả sử quy ước eligible tasks gồm `success`, `failed` và `partial`; còn `expected_denied`, `expected_not_found`, `cancelled` và `unknown` được báo riêng cho dashboard.

~~~promql
sum(
  increase(assistant_task_completed_total{
    workflow="order_status_lookup",
    outcome="success"
  }[15m])
)
/
clamp_min(
  sum(
    increase(assistant_task_completed_total{
      workflow="order_status_lookup",
      outcome=~"success|failed|partial"
    }[15m])
  ),
  1
)
~~~

Kết quả gần 1 nghĩa là tỷ lệ tác vụ đủ điều kiện được hoàn tất cao. `clamp_min(..., 1)` chỉ tránh chia 0; **không có lưu lượng không có nghĩa tỷ lệ thành công bằng 0**. Dashboard nên trả `No data` hoặc hiển thị volume cạnh tỷ lệ, tránh làm người xem hiểu sai.

Để đếm số tác vụ thất bại:

~~~promql
sum by (workflow) (
  increase(assistant_task_completed_total{
    outcome=~"failed|partial"
  }[1h])
)
~~~

Cần giữ định nghĩa “partial” nhất quán. Nếu tác vụ chỉ được xem là thành công khi model đã tạo câu trả lời cuối, hãy ghi sự kiện domain ở điểm đó; đừng tự đánh dấu success tại HTTP 200 của tool.

## 13. PromQL: độ trễ p95 của cả tác vụ

`Timer.publishPercentileHistogram()` tạo histogram để dùng `histogram_quantile` trong Prometheus:

~~~promql
histogram_quantile(
  0.95,
  sum by (le) (
    rate(assistant_task_duration_seconds_bucket{
      workflow="order_status_lookup"
    }[15m])
  )
)
~~~

Kết quả là **giây**, có thể đặt ngưỡng ví dụ 8 s. Đừng cộng p95 của ChatModel với p95 của tool để ra p95 của task: các phần có thể chồng lấn, có nhiều lần chạy và phép cộng percentile không hợp lệ.

Lưu ý:

- Chỉ so sánh p95 khi số mẫu đủ đại diện.
- Nhãn `workflow` cần ít giá trị, không phải URL hoặc câu người dùng tự do.
- Histogram có nhiều buckets và làm tăng số series; cấu hình bucket phù hợp SLO.
- Với streaming, định nghĩa latency theo **lúc stream hoàn tất**; nếu chỉ đo HTTP header/time-to-first-byte, bạn sẽ đo một thứ khác.

Có thể thêm metric `assistant.task.first_content_seconds` (timer custom) để đo time-to-first-user-visible-content và tách khỏi full completion latency.

## 14. PromQL: token, model calls và phát hiện vòng lặp

Spring AI metrics có thể dùng:

~~~promql
sum by (gen_ai_request_model) (
  rate(gen_ai_client_token_usage_total{
    gen_ai_token_type="total"
  }[10m])
)
~~~

Đây là **token/giây** theo model trên cửa sổ 10 phút, không phải USD/giây. Không cộng `gen_ai_token_type="total"` với `input` và `output` vì total đã gồm các thành phần tương ứng.

Số lần gọi model của một task không được suy ra chính xác bằng `ChatClient` counter riêng lẻ khi một exchange có nhiều model iterations. Ứng dụng cần ghi `modelCallCount` vào summary hoặc metric histogram theo workflow.

Ví dụ custom metric (khái niệm):

~~~text
assistant_task_model_calls_count
assistant_task_model_calls_sum
assistant_task_tool_calls_count
assistant_task_tool_calls_sum
~~~

Những tên trên tương ứng với `DistributionSummary` custom, **không phải metric có sẵn** của Spring AI. Để vẽ model calls per task:

~~~promql
sum(rate(assistant_task_model_calls_sum[30m]))
/
clamp_min(sum(rate(assistant_task_model_calls_count[30m])), 1)
~~~

Nếu giá trị trung bình tăng từ 2 lên 6 sau release, hãy kiểm tra tool choice, schema, retry, prompt và tool loop limits. Tăng model calls **không tự chứng minh lỗi**: một workflow được mở rộng nghiệp vụ cũng có thể cần thêm lượt hợp lệ.

## 15. PromQL: chi phí ước tính và độ bao phủ dữ liệu

Giả sử recorder ghi:

- `assistant.task.estimated.cost.usd`: Counter USD ước tính của các task đã biết chi phí.
- `assistant.task.cost.known`: Counter số task có tính được chi phí.

Mức phí ước tính bình quân cho task có dữ liệu:

~~~promql
sum(
  increase(assistant_task_estimated_cost_usd_total{
    workflow="order_status_lookup"
  }[1h])
)
/
clamp_min(
  sum(
    increase(assistant_task_cost_known_total{
      workflow="order_status_lookup"
    }[1h])
  ),
  1
)
~~~

Để đánh giá tỷ lệ tác vụ có đủ dữ liệu cost:

~~~promql
sum(increase(assistant_task_cost_known_total{
  workflow="order_status_lookup"
}[1h]))
/
clamp_min(
  sum(increase(assistant_task_completed_total{
    workflow="order_status_lookup"
  }[1h])),
  1
)
~~~

Nếu coverage chỉ 60%, số phí trung bình từ 60% đó **không đại diện chắc chắn cho 40% còn lại**. Dashboard phải hiển thị coverage, price version và ghi rõ `estimated`, không đặt tên panel là “tiền bị thu thực tế”.

Cost model có thể khác với chi phí tool gọi REST/SDK hoặc chi phí hạ tầng; cần ledger tách `modelUsd`, `externalApiUsd`, `infrastructureAllocatedUsd`, `billedUsd`. Nếu source metric có chi phí ước tính và hóa đơn tháng, không cộng hai nguồn đó vào cùng một tổng.

## 16. Thiết kế cảnh báo dựa trên tác động nghiệp vụ

Một cảnh báo hữu ích gồm:

| Thành phần | Ý nghĩa |
|---|---|
| **Signal** | Mức lỗi, độ trễ, tiêu ngân sách hay vi phạm quyền |
| **Population** | Workflow/tenant tier/environment nào bị ảnh hưởng? |
| **Threshold + window** | Ngưỡng và khoảng đo |
| **Minimum traffic** | Số mẫu tối thiểu để giảm nhiễu |
| **Severity** | Page ngay, ticket hoặc chỉ dashboard |
| **Owner** | Nhóm chịu trách nhiệm |
| **Runbook** | Bước kiểm chứng và giảm tác động |
| **Recovery** | Khi nào alert tự hết và ai đóng incident |

Ví dụ ma trận alert:

| Cảnh báo | Điều kiện minh họa | Mức | Hành động |
|---|---|---|---|
| Business task failure | Failure+partial `>` 5%/15m, ít nhất 50 tasks | Page | Xem traces và các tool lỗi nhiều nhất |
| Task p95 latency | p95 `>` 8 s trong 15m, đủ lưu lượng | Page/Ticket | Phân tách model/tool/backend latency |
| Provider 429/5xx | Tỷ lệ lỗi model tăng kéo dài | Ticket/Page | Kiểm tra quota, model/provider, backoff |
| Tool timeout | Dependency timeout tăng và ảnh hưởng success | Page | Kiểm tra API downstream, circuit breaker |
| Tool loop tăng | Model calls/task vượt baseline hoặc > policy | Ticket | Kiểm tra schema, prompt, tool selection |
| Cost per task tăng | USD/task > baseline trong 1h, coverage cao | Ticket | So sánh tokens, giá, retry, external API |
| Budget sắp cạn | 80% rồi 95% ngân sách ngày/tháng | Ticket/Page | Giảm workload không thiết yếu theo policy |
| Usage thiếu | Unknown usage > 5% trong 30m | Ticket | Kiểm tra provider metadata và exporter |
| Unauthorized tool execution | **Có ít nhất một lần thực thi ngoài quyền** | **P1** | Khóa đường thực thi rủi ro, điều tra sự cố |
| Denial spike | Policy denies tăng đột biến | Security triage | Xem dấu hiệu abuse, tránh nhầm với successful breach |
| Mất telemetry | Expected service không còn heartbeat | Ticket | Kiểm tra collector/scrape trước khi kết luận app hỏng |

Các ngưỡng là **ví dụ giáo dục**, phải được điều chỉnh bằng traffic, mức rủi ro và SLO thật của sản phẩm. Không dựa vào model text để tự suy ra hành động an toàn trong alert automation.

## 17. Ví dụ Prometheus alert rules

Giả sử workflow `order_status_lookup` có đủ số mẫu và metric được export theo tên minh họa:

~~~yaml
groups:
  - name: assistant-business-task-alerts
    rules:
      - alert: OrderLookupFailureRatioHigh
        expr: |
          (
            sum(increase(assistant_task_completed_total{
              workflow="order_status_lookup",
              outcome=~"failed|partial"
            }[15m]))
            /
            clamp_min(
              sum(increase(assistant_task_completed_total{
                workflow="order_status_lookup",
                outcome=~"success|failed|partial"
              }[15m])),
              1
            )
          ) > 0.05
          and
          sum(increase(assistant_task_completed_total{
            workflow="order_status_lookup",
            outcome=~"success|failed|partial"
          }[15m])) >= 50
        for: 10m
        labels:
          severity: page
          team: order-assistant
        annotations:
          summary: "Tra cứu đơn hàng lỗi vượt 5%"
          description: "Kiểm tra các tool và downstream API liên quan."
          runbook_url: "https://example.invalid/runbooks/order-lookup"

      - alert: OrderLookupLatencyHigh
        expr: |
          histogram_quantile(
            0.95,
            sum by (le) (
              rate(assistant_task_duration_seconds_bucket{
                workflow="order_status_lookup"
              }[15m])
            )
          ) > 8
          and
          sum(increase(assistant_task_completed_total{
            workflow="order_status_lookup"
          }[15m])) >= 50
        for: 10m
        labels:
          severity: ticket
          team: order-assistant
        annotations:
          summary: "p95 tra cứu đơn hàng vượt 8 giây"
          runbook_url: "https://example.invalid/runbooks/order-latency"
~~~

`example.invalid` là địa chỉ minh họa, phải thay bằng URL runbook thật. Các rule cần được kiểm thử với dữ liệu giả và Prometheus engine trước khi dùng trong production. Đặc biệt, nếu không có lưu lượng, histogram hoặc mẫu số có thể không có series; hãy cấu hình `no data`/missing telemetry riêng, không suy diễn thành 100% thành công.

## 18. Dùng error budget burn rate thay vì chỉ một ngưỡng lỗi

Giả sử SLO resolution rate là 99% trong 28 ngày. Error budget tương ứng 1%. **Burn rate** có thể định nghĩa:

~~~text
ObservedFailureRate = FailedEligibleTasks / AllEligibleTasks

AllowedFailureRate = 1 - SLO

BurnRate = ObservedFailureRate / AllowedFailureRate
~~~

Ví dụ failure rate 5% khi SLO là 99%:

~~~text
BurnRate = 0,05 / 0,01 = 5
~~~

Tức là lỗi đang tiêu ngân sách nhanh hơn 5 lần so với tốc độ bền vững cho kỳ SLO đó.

Có thể dùng alert nhiều cửa sổ: một cửa sổ ngắn để phát hiện sự cố đột ngột, một cửa sổ dài để giảm báo động do biến động nhất thời. Ví dụ:

- Cảnh báo nhanh khi tỷ lệ lỗi cao ở cả 5 phút và 1 giờ, với lưu lượng đủ.
- Cảnh báo chậm khi tỷ lệ lỗi tăng ổn định ở 30 phút và 6 giờ.
- Không page on-call chỉ vì một tác vụ đơn lẻ thất bại nếu không có dấu hiệu rủi ro đặc biệt.

Ngược lại, **unauthorized execution** là sự kiện an ninh nghiêm trọng: không chờ đủ 50 mẫu hay 15 phút nếu có bằng chứng thực thi ngoài quyền. Chỉ dấu `denied` tăng khác với `executed_without_authorization`; cần đo tách hai loại.

## 19. Bảo mật metrics, traces và logs

Quan sát tốt không đồng nghĩa thu thập mọi nội dung. Prompt, JSON arguments, response và tool result có thể chứa dữ liệu cá nhân, bí mật kinh doanh hoặc credential.

**Metric tags nên có cardinality thấp:**

~~~text
workflow=order_status_lookup
environment=production
provider=example-provider
model=model-family
tool=get_shipment_tracking
outcome=timeout
tenant_tier=enterprise
~~~

Không đặt các giá trị sau làm Prometheus label:

~~~text
userId, tenantId thật, turnId, conversationId,
orderNumber, rawPrompt, rawToolArguments,
rawToolResult, email, paymentReference
~~~

`tenant_tier` chỉ nên dùng khi nhóm tier được định nghĩa rõ và không làm lộ định danh người dùng; quyền xem dashboard phải phù hợp. Nếu sản phẩm cần báo cáo riêng theo tenant, sử dụng ledger được phân quyền hoặc hệ thống phân tích dữ liệu có kiểm soát, không làm bùng nổ time series.

Theo tài liệu Spring AI, nội dung prompt/completion **không được log mặc định** vì có thể nhạy cảm. Không bật các property log-prompt/log-completion ở production chỉ để tăng khả năng debug. Khi cần điều tra, ưu tiên IDs tương quan và trường dữ liệu đã redaction, với retention và audit riêng.

### Không nhầm tool denial với xâm nhập thành công

Ba event khác nhau:

1. Model **đề xuất** tool trái quyền.
2. Authorization **từ chối** tool trái quyền.
3. Tool **thực thi trái quyền** do lỗi chính sách/implementation.

Chỉ event thứ ba chứng minh một vi phạm đã xảy ra. Event thứ nhất và thứ hai quan trọng để quan sát khả năng bị tấn công, nhưng không nên gắn nhãn “rò rỉ” nếu backend đã chặn và không trả dữ liệu.

## 20. Streaming, cancellation và đo độ trễ đúng nghĩa

Với `ChatClient.stream()`, request có thể hoàn tất tại các thời điểm khác nhau:

- **TTFT / first useful content**: người dùng nhìn thấy ký tự đầu tiên có ý nghĩa.
- **First tool activity**: model đề xuất tool đầu tiên hoặc tool bắt đầu chạy.
- **Final complete**: stream trả hết nội dung và kết thúc.
- **Cancelled**: client rời trang, ngắt SSE hoặc hủy subscription.
- **Failed**: stream kết thúc bằng lỗi.

Đừng đánh dấu business `success` chỉ vì Flux phát một chunk. Khi tool có side effect, client cancel không đảm bảo hành động đã thực hiện được rollback.

Ví dụ một tầng observer ở application boundary:

~~~java
public Flux<String> streamTask(
        String turnId,
        String question,
        ToolContext context) {

    long started = System.nanoTime();

    return chatClient.prompt()
        .user(question)
        .toolContext(context.getContext())
        .stream()
        .content()
        .doOnComplete(() ->
            taskEvents.markTransportComplete(turnId)
        )
        .doOnError(error ->
            taskEvents.markTransportFailed(
                turnId,
                error.getClass().getSimpleName()
            )
        )
        .doFinally(signal ->
            taskEvents.recordTermination(
                turnId,
                signal.name(),
                Duration.ofNanos(
                    System.nanoTime() - started
                )
            )
        );
}
~~~

`taskEvents` là service minh họa. `markTransportComplete` chỉ nói **stream transport kết thúc**, không chứng minh task trả thông tin chính xác. Để ghi `TaskFinished(SUCCESS)`, ứng dụng còn cần oracle nghiệp vụ và xử lý trạng thái terminal **đúng một lần**. Đoạn ví dụ cũng cần cơ chế riêng cho resubscription/retry, vì một publisher có thể được subscribe nhiều lần; trong production nên khởi tạo timer per subscription với `Flux.defer(...)` và bảo đảm identity không bị tái sử dụng sai.

Nếu tool chạy blocking, phải quản lý timeout tại chính tool/HTTP client; không dùng `collectList().block()` để gom tất cả stream chỉ phục vụ metrics.

## 21. Chi phí và ngân sách phải được đo theo tác vụ

Chi phí của một task có thể bao gồm:

~~~text
TaskEstimatedCost =
    ModelProviderCost
  + ExternalApiVendorFee
  + AllocatedInfrastructureCost
~~~

**Token count không phải tiền.** Giá model phụ thuộc provider/model, input/output/cache, modality và rate card; tool có thể gọi API trả phí không sử dụng LLM. Một tool call có thể phát nhiều remote attempts và được vendor tính phí theo hợp đồng riêng.

Để theo dõi ngân sách:

1. Lưu model usage theo từng model call, không cộng lặp cumulative `ChatClient` usage.
2. Lưu tool call và remote attempts riêng, có `toolCallId`/`attemptId`.
3. Gắn cost với `priceVersion`, currency và trạng thái `estimated/observed/reconciled`.
4. Tính trung bình USD trên **tác vụ đủ điều kiện thành công** với coverage rõ.
5. Thiết kế budget reservation trước model/tool calls nếu cần giới hạn chi tiêu.
6. Alert gần đạt ngân sách kỳ hoặc USD/task vượt baseline; không dùng ước lượng như hóa đơn đã xác nhận.

Một cảnh báo cost chỉ có ý nghĩa khi quantity và coverage đáng tin. Ví dụ “USD/task tăng 2 lần” cần xem model/token price, số vòng tool, số lần retry, sự thay đổi ở backend và mix workflow; không mặc định model đắt hơn là nguyên nhân.

## 22. Runbook: mỗi cảnh báo phải giúp hành động đúng

Ví dụ runbook cho `OrderLookupFailureRatioHigh`:

1. **Xác minh:** tỷ lệ lỗi và số request có vượt ngưỡng/traffic tối thiểu không? Có phải telemetry bị mất hoặc thay đổi định nghĩa outcome?
2. **Phạm vi:** chỉ `order_status_lookup` hay nhiều workflow? Chỉ một provider/model, release hoặc region?
3. **Phân tách tầng:** lỗi model, tool callback, REST/SDK, database hay lỗi policy?
4. **Bằng chứng:** mở exemplar trace hoặc ledger event theo `turnId` với quyền phù hợp; không tìm nguyên prompt trên metric label.
5. **Giảm tác động:** áp dụng fallback read-only, cảnh báo degraded service, chuyển traffic đúng policy, rollback release nếu liên quan.
6. **Bảo vệ:** không tự tắt authorization, confirmation hoặc tenant filter để làm tỷ lệ lỗi giảm.
7. **Xác nhận hồi phục:** error rate, task success và latency quay về mục tiêu; test tác vụ hợp lệ vẫn thành công.
8. **Hậu kiểm:** cập nhật test/alert, phân loại nguyên nhân, ước lượng ảnh hưởng người dùng.

Ví dụ runbook cho cost spike:

1. Kiểm tra cost data coverage và price table.
2. So model calls/turn và token per model call trước/sau thay đổi.
3. Kiểm tra catalog schema dài, history phình, tool outputs lớn, retry và tool loop.
4. Kiểm tra phí vendor external và infra allocation.
5. Giảm quota hoặc chuyển workflow không thiết yếu theo chính sách; không cắt tool cần thiết nếu làm giảm chất lượng/gián đoạn nghiệp vụ mà chưa đánh giá.
6. Đối soát hóa đơn thực trước khi báo cáo tác động tài chính cuối kỳ.

### Severity và người nhận

Một bảng mapping hữu ích:

| Severity | Tình huống | Người nhận |
|---|---|---|
| P1 / Page | Unauthorized execution, sự cố dữ liệu xuyên tenant, mất khả năng thực hiện tác vụ trọng yếu | Incident commander + security/service owner |
| P2 / Page | Lỗi tác vụ lớn hoặc SLO burn kéo dài, không có fallback | On-call của workflow |
| P3 / Ticket | Tăng chi phí, công cụ chậm nhẹ, thiếu usage, chỉ số quality xuống dưới baseline | Chủ sở hữu sản phẩm + engineering |
| Info | Deploy marker, traffic mix thay đổi, thử nghiệm mới | Dashboard/change log |

Không page on-call theo mọi `ToolExecutionException` đơn lẻ. Một lời gọi API thất bại có thể đã được retry an toàn và task vẫn hoàn thành; alert phải dựa trên tác động thực sự hoặc SLO.

## 23. Kiểm thử instrumentation và alert trước production

Các phép kiểm thử có thể chạy với fake `ChatModel`, fake tool service và `SimpleMeterRegistry`:

| Test | Mong đợi |
|---|---|
| Một task thành công | `assistant.task.completed` tăng đúng một |
| ChatClient có ba model calls | Business task counter tăng một; model counter tăng ba |
| Một tool retry ba HTTP requests | Một tool call ID, ba attempt records |
| `expected_denied` | Không bị tính nhầm là dependency failure |
| `partial` | Tỷ lệ completion phản ánh suy giảm |
| Streaming complete | Transport complete và task outcome được phân biệt |
| Streaming cancel | Không đánh dấu success giả; side effect audit không bị bỏ |
| Provider không trả usage | Cost coverage giảm, không xem unknown như $0 |
| Cost event bị replay | Ledger/dedupe không cộng gấp đôi |
| Concurrent requests | Metric tags ổn định, không trộn actor/tenant |
| Prompt chứa PII | Không xuất PII trong metric label/log |
| Low traffic | Alert failure ratio không page chỉ vì 1 case |
| Outage tool API | Failure ratio/SLO burn và alert xuất hiện sau đúng cửa sổ |
| Recovery | Alert kết thúc sau ngưỡng hồi phục |
| Missing scrape | Có alert mất telemetry riêng, không “green” giả |

Ví dụ unit test recorder:

~~~java
@Test
void recordsOneBusinessOutcome() {
    SimpleMeterRegistry registry =
        new SimpleMeterRegistry();

    BusinessTaskMetrics telemetry =
        new BusinessTaskMetrics(registry);

    telemetry.record(new TaskFinished(
        "turn-123",
        WorkflowKey.ORDER_STATUS_LOOKUP,
        TaskOutcome.SUCCESS,
        Duration.ofMillis(1200),
        new BigDecimal("0.0042"),
        true
    ));

    double count = registry
        .get("assistant.task.completed")
        .tag("workflow", "order_status_lookup")
        .tag("outcome", "success")
        .counter()
        .count();

    assertThat(count).isEqualTo(1.0);
}
~~~

Test này chỉ kiểm tra recorder khi được gọi **một lần**; không chứng minh idempotency. Nếu yêu cầu idempotency, test thêm event handler với `eventId`/`turnId` được deduplicate atomically trước khi gọi recorder.

### Kiểm thử alert rule

Dùng dữ liệu giả với nhiều cửa sổ:

- 0 lỗi trên 100 tác vụ → không alert.
- 1 lỗi trên 2 tác vụ → traffic guard ngăn page sai.
- 20 lỗi trên 200 tác vụ trong 15 phút → alert sau `for` duration.
- Lỗi giảm về bình thường → alert tự resolve theo policy.
- Không có metrics do exporter ngừng hoạt động → alert `no data` riêng.
- Một sự kiện unauthorized execution có bằng chứng → escalates ngay, không chờ ngưỡng traffic.

Với Prometheus, dùng test rule ở công cụ phù hợp như `promtool test rules` trong pipeline CI, nhưng việc viết bài STEP 4 **không thực thi** bộ kiểm thử này. Khi thay đổi instrumentation hoặc metric names cần chạy lại kiểm thử ở bước chuyên trách.

## 24. Những sai lầm thường gặp

| Sai lầm | Vì sao sai | Cách khắc phục |
|---|---|---|
| Dùng HTTP 200 làm task success | Model có thể trả sai hoặc tool thiếu dữ liệu | Ghi outcome ở application boundary |
| Đếm một model call = một user turn | Tool loop có nhiều model calls | Gắn `turnId` và phân biệt các tầng |
| Cộng mọi span durations | Các spans lồng nhau/chồng lấp | Đo end-to-end timer riêng |
| Cộng usage cumulative và per-model-call | Double counting token/cost | Chọn nguồn ledger chuẩn |
| Đặt `orderNumber`/`userId` vào labels | Cardinality và rò dữ liệu | Dùng enum workflow/outcome, IDs trong traces có quyền |
| Ghi một event cho mỗi streamed chunk | Inflates volume và task count | Chỉ ghi terminal outcome một lần |
| Xem `cancelled` là `failed` mặc định | Hủy hợp lệ bị tính thành outage | Phân loại và xác định eligibility |
| Không có minimum traffic | Một lỗi trên hai requests gây page | Thêm traffic guard và multi-window |
| Alert chỉ có tên metric | On-call không biết làm gì | Có business impact, owner và runbook |
| Dùng unknown cost như $0 | Tính chi phí trung bình thấp giả | Hiển thị coverage và reconciled state |
| Xem policy deny là security breach | Deny có thể là hệ thống đang bảo vệ đúng | Tách deny và unauthorized execution |
| Tắt quyền/tenant filter để giảm lỗi | Lợi dụng telemetry làm yếu an toàn | Giữ policy; sửa nguyên nhân thật |
| Dùng model answer làm oracle duy nhất | Model có thể tự tin nhưng sai | Kiểm tra trạng thái nguồn và kết quả nghiệp vụ |
| Không test khi đổi phiên bản exporter | PromQL mất dữ liệu không báo | Kiểm tra metric names/labels và absent-series rules |

## 25. Checklist triển khai

- [ ] Xác định workflow bằng mã server-side, không suy từ raw prompt.
- [ ] Business task có `turnId` và outcome terminal rõ ràng.
- [ ] Phân loại `success`, `expected_not_found`, `expected_denied`, `partial`, `failed`, `cancelled` và `unknown`.
- [ ] SLI/SLO và population/denominator được tài liệu hóa.
- [ ] Tách ChatClient, model calls, tool calls, backend attempts và cost ledger.
- [ ] Ghi business outcome một lần, có chống duplicate từ queue/retry.
- [ ] Có p50/p95 end-to-end latency, TTFT/complete khi streaming nếu cần.
- [ ] Có token input/output/total và không cộng trùng `total` với thành phần.
- [ ] Có cost coverage và price/version; không coi estimate là hóa đơn.
- [ ] Có biểu đồ success, failures, tool errors, model latency và dependency latency.
- [ ] Có phân biệt policy denial với vi phạm quyền thành công.
- [ ] Metric labels là các giá trị ít biến thiên, không chứa PII hoặc secrets.
- [ ] Traces/logs gắn correlation ID nhưng có giới hạn quyền và retention.
- [ ] Alert có threshold, window, minimum traffic, severity, owner, runbook.
- [ ] Có cơ chế phát hiện mất telemetry và false green.
- [ ] Có kiểm thử PromQL/rules cùng synthetic metrics trong pipeline.
- [ ] Có runbook cho business failure, dependency outage, budget spike và security incidents.
- [ ] Đã thử nghiệm một workflow thực tế, đo độ nhiễu alert và điều chỉnh theo baseline.

## Tài liệu tham khảo

- [Spring AI — Observability](https://docs.spring.io/spring-ai/reference/observability/): các observation ChatClient, ChatModel, Advisor, Tool và token usage.
- [Spring AI — Tool Calling](https://docs.spring.io/spring-ai/reference/api/tools.html): vòng tool calling, `ToolCallingManager`, `ToolContext`, kết quả và xử lý lỗi.
- [Spring AI — ToolCallingAdvisor](https://docs.spring.io/spring-ai/reference/api/tools/tool-calling-advisor.html): advisor điều phối nhiều lượt và phân biệt đường call/stream.
- [Spring Boot — Metrics](https://docs.spring.io/spring-boot/reference/actuator/metrics.html): Actuator, meter registry và tích hợp exporter.
- [Micrometer — Histograms and Percentiles](https://docs.micrometer.io/micrometer/reference/concepts/histogram-quantiles.html): `publishPercentileHistogram`, SLO buckets và histogram aggregation.
- [Prometheus — Alerting Rules](https://prometheus.io/docs/prometheus/latest/configuration/alerting_rules/): cú pháp alerting, `for`, labels và annotations.
- [Prometheus — Histograms and Summaries](https://prometheus.io/docs/practices/histograms/): cách tính quantiles từ histogram.
- [Google SRE Workbook — Alerting on SLOs](https://sre.google/workbook/alerting-on-slos/): error budget, burn-rate và multi-window alerts.

**Điểm cần nhớ:** dashboard cho Spring AI Tool Calling phải bắt đầu từ **người dùng có hoàn thành tác vụ nghiệp vụ hay không**, rồi mới đi sâu vào model, tool, backend và chi phí. Metric cho biết triệu chứng; trace/ledger giúp xác định nguyên nhân; alert chỉ có ích khi gắn với tác động, owner và runbook. Đừng đánh đổi quyền truy cập hoặc dữ liệu riêng tư để lấy biểu đồ đẹp: authorization và tenant isolation luôn được thực thi ở ứng dụng, không phụ thuộc model hay dashboard.

