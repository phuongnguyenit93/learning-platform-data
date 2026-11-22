# Thiết kế telemetry cho luồng phân tán và bất đồng bộ

Trong một ứng dụng cloud, một yêu cầu của người dùng hiếm khi được xử lý trong một tiến trình duy nhất. API gateway có thể chuyển request tới nhiều service; một service ghi database rồi phát event; broker phân phối event tới consumer; consumer gọi dịch vụ thanh toán, gửi email hoặc cập nhật search index. Công việc có thể tiếp tục sau khi HTTP response đã trả về, được retry nhiều lần, chia thành nhiều nhánh hoặc chạy ở worker khác region. Khi một bước chậm hoặc thất bại, log riêng lẻ của từng service thường không trả lời được câu hỏi: request ban đầu đã đi đâu, bước nào mất thời gian, lỗi bắt đầu ở đâu và tác động tới nghiệp vụ nào?

**Telemetry cho luồng phân tán** phải giữ được mối liên hệ giữa các thao tác xuyên qua ranh giới process, service và thời gian. Trace/spans mô tả đường đi và quan hệ nhân quả; metrics thể hiện xu hướng và mức độ ảnh hưởng; logs cung cấp chi tiết sự kiện. Context propagation truyền trace context qua HTTP, RPC, message broker, job queue và các bước bất đồng bộ. Thiết kế tốt còn phải xử lý retry, fan-out/fan-in, batch, sampling, cardinality, privacy và chi phí lưu trữ.

Bài học thuộc chương **Khả năng quan sát** của module **CLOUD_ARCHITECTURE**. Mục tiêu là thiết kế telemetry từ yêu cầu vận hành và nghiệp vụ để hỗ trợ chẩn đoán, đo SLO, phản ứng sự cố và tối ưu hệ thống cloud theo tư duy Well-Architected.

## 1. Mục tiêu học tập

Sau bài này, người học có thể:

1. Giải thích vì sao log và metric đơn lẻ không đủ để theo dõi một workflow phân tán.
2. Mô hình hóa trace, span, parent-child relationship và link giữa các trace.
3. Truyền trace context qua HTTP/RPC, queue, event, retry, scheduler và batch.
4. Xử lý trace cho fan-out/fan-in, asynchronous continuation và long-running workflow.
5. Kết hợp trace, metrics và logs bằng trace ID, span ID và các thuộc tính có kiểm soát.
6. Chọn sampling strategy, instrumentation boundary và semantic attributes.
7. Thiết kế telemetry không làm lộ dữ liệu nhạy cảm hoặc tạo cardinality/chi phí không kiểm soát.
8. Kiểm thử context propagation và dùng telemetry để xác định bottleneck, lỗi và SLO.

## 2. Vì sao luồng phân tán khó quan sát?

### 2.1. Một request đi qua nhiều ranh giới

Ví dụ người dùng xác nhận booking:

~~~mermaid
flowchart LR
    WEB[Web / Mobile] --> GW[API Gateway]
    GW --> BOOK[Booking Service]
    BOOK --> DB[(Booking DB)]
    BOOK --> OUT[Outbox]
    OUT --> BUS[Message Broker]
    BUS --> PAY[Payment Consumer]
    BUS --> SEARCH[Search Consumer]
    PAY --> PSP[Payment Provider]
    PAY --> MAIL[Notification Service]
    SEARCH --> IDX[(Search Index)]
~~~

Một giao dịch nghiệp vụ có thể chạm nhiều service, database và provider. Mỗi service có process ID, host, log format và clock riêng. Event có thể được xử lý vài giây hoặc vài giờ sau request ban đầu. Chỉ dùng timestamp gần nhau hoặc grep theo user ID thường không đủ để tái dựng luồng.

### 2.2. Các dạng phân tán

- **Synchronous call chain:** HTTP/gRPC gọi nối tiếp; latency tích lũy và lỗi có thể lan truyền.
- **Fan-out/fan-in:** một request tạo nhiều nhánh song song rồi tổng hợp kết quả.
- **Asynchronous messaging:** producer phát event; consumer xử lý sau, không giữ HTTP connection.
- **Scheduled/batch work:** job được khởi động theo lịch và xử lý nhiều record.
- **Retry/redelivery:** cùng một message hoặc operation có thể chạy nhiều lần.
- **Long-running workflow:** một quy trình có thể kéo dài nhiều phút/ngày và chờ callback.
- **Cross-region/service provider:** request đi qua network và hệ thống ngoài quyền kiểm soát.

Mỗi dạng có quan hệ nhân quả khác nhau. Telemetry phải mô tả quan hệ đó thay vì giả định mọi thao tác là một cây gọi hàm đồng bộ.

### 2.3. Những câu hỏi vận hành cần trả lời

| Câu hỏi | Telemetry cần có |
|---|---|
| Request chậm ở đâu? | Span duration và dependency breakdown |
| Event nào sinh ra từ request nào? | Trace context hoặc causal link trong message |
| Message bị xử lý bao nhiêu lần? | Message ID, delivery/attempt metadata và span links |
| Consumer lag bắt đầu từ đâu? | Queue age/lag metrics, publish/consume timestamps |
| Nhánh nào làm workflow thất bại? | Parent-child spans hoặc linked traces, status/error |
| Retry có cải thiện hay khuếch đại sự cố? | Attempt count, retry delay, error rate và queue depth |
| Sự cố ảnh hưởng khách hàng nào? | Tenant-scoped attributes được kiểm soát, không dùng làm metric label vô hạn |
| Đội vận hành có tái dựng được sự kiện? | Structured logs, trace ID, event/job ID và audit |

## 3. Ba tín hiệu telemetry và vai trò của chúng

### 3.1. Traces

Trace mô tả một đơn vị công việc qua nhiều thành phần. Trace thường có trace ID duy nhất và nhiều span. Mỗi span biểu diễn một thao tác có thời gian bắt đầu/kết thúc, thuộc tính, event, status và quan hệ với span khác.

Trace trả lời: **đường đi của một thao tác là gì và nó tiêu tốn thời gian ở đâu?**

### 3.2. Metrics

Metrics là số liệu được tổng hợp theo thời gian, ví dụ request rate, error rate, latency histogram, queue depth, oldest-message age và consumer throughput. Metrics phù hợp để cảnh báo, dashboard và SLO vì có thể truy vấn hiệu quả theo time series.

Metrics trả lời: **hệ thống đang hoạt động ở mức nào, xu hướng ra sao và bao nhiêu người dùng bị ảnh hưởng?**

### 3.3. Logs

Logs là sự kiện hoặc thông điệp có cấu trúc, có timestamp và context. Log có thể ghi lý do validation fail, provider response code, state transition hoặc quyết định retry. Logs cung cấp chi tiết nhưng thường tốn storage và không nên dùng thay metric cho mọi phép tổng hợp.

Logs trả lời: **điều gì đã xảy ra và chi tiết nào giải thích kết quả?**

### 3.4. Kết hợp ba tín hiệu

~~~mermaid
flowchart TD
    APP[Instrumented services] --> TRACE[Traces]
    APP --> METRIC[Metrics]
    APP --> LOG[Structured logs]
    TRACE --> TQL[Trace backend]
    METRIC --> MQL[Metrics backend]
    LOG --> LQL[Log backend]
    TQL --> CORR[Correlation / investigation]
    MQL --> CORR
    LQL --> CORR
~~~

Khi log chứa trace ID và span ID, người vận hành có thể mở trace liên quan từ log. Khi trace có service, operation và status phù hợp, có thể liên hệ với metric theo service/environment. Correlation cần schema và ID thống nhất; chỉ ghi một chuỗi tự do trong log thì khó truy vấn ổn định.

## 4. Trace và span: mô hình cơ bản

### 4.1. Trace

Trace đại diện cho một đơn vị công việc có ý nghĩa, ví dụ xử lý HTTP request hoặc một workflow. Trace ID được truyền qua các thành phần tham gia cùng hoạt động hoặc liên kết với nó.

### 4.2. Span

Span đại diện cho một thao tác:

- Tên operation như POST /bookings hoặc payment.authorize.
- Trace ID và span ID.
- Parent span ID nếu có quan hệ cha-con.
- Thời điểm bắt đầu và thời lượng.
- Attributes như service, route template, dependency, status code.
- Events như retry scheduled hoặc validation completed.
- Status/error theo quy ước instrumentation.

Không nên tạo span cho mọi dòng code. Span cần phản ánh ranh giới có giá trị chẩn đoán: inbound request, outbound dependency call, database operation quan trọng, publish/consume message và workflow step.

### 4.3. Cây span cho request đồng bộ

~~~text
Trace: POST /bookings
  ├── API Gateway
  ├── Booking Service
  │    ├── validate request
  │    ├── SELECT inventory
  │    ├── INSERT booking
  │    └── publish BookingCreated
  └── response
~~~

Tổng thời gian trace giúp nhìn trải nghiệm request; span con giúp thấy phần nào chiếm thời gian. Không cộng duration của span cha với các span con để tính tổng latency vì span cha thường bao gồm thời gian chạy của con.

### 4.4. Status và error

Span nên phân biệt thành công; lỗi nghiệp vụ dự kiến như validation reject hoặc resource not found; lỗi dependency như timeout, throttling hoặc connection reset; lỗi hệ thống không xác định; cancelled/deadline exceeded.

Không đánh dấu mọi HTTP 4xx là lỗi hệ thống. Một request bị từ chối đúng policy có thể là kết quả nghiệp vụ bình thường; SLI cần phản ánh semantics của dịch vụ.

## 5. Context propagation qua HTTP và RPC

### 5.1. Trace context là gì?

Context propagation truyền thông tin định danh và quan hệ span từ caller sang callee. Với W3C Trace Context, header phổ biến là:

- traceparent: version, trace ID, parent span ID và trace flags.
- tracestate: vendor-specific tracing state có giới hạn.

Ví dụ minh họa:

~~~http
traceparent: 00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01
tracestate: vendor=value
~~~

Receiver trích context để tạo server span cùng trace, parent là span phía client theo propagation model. Instrumentation cần chuẩn hóa header; không tự ghép trace ID bằng cách parse chuỗi thủ công trong business code.

### 5.2. W3C Trace Context và OpenTelemetry

OpenTelemetry (OTel) cung cấp API/SDK và instrumentation để tạo, propagate và export telemetry. W3C Trace Context là một chuẩn propagation được hỗ trợ rộng. Cấu hình propagator cần thống nhất giữa các service; nếu một service chỉ hiểu định dạng riêng, trace có thể bị đứt.

### 5.3. Inbound và outbound instrumentation

Một service thường cần:

1. Extract context từ request inbound.
2. Tạo server span với route template và attributes phù hợp.
3. Đặt context hiện hành trong execution scope.
4. Khi gọi service khác, tạo client span và inject context vào outbound request.
5. Kết thúc span trong mọi nhánh success/error/cancel.

Không đưa full URL có query chứa token hoặc dữ liệu người dùng vào span name/attribute. Dùng route template như /customers/{customerId} thay vì path cụ thể để tránh PII và cardinality cao.

### 5.4. Ví dụ instrumentation khái niệm

~~~typescript
import { trace, SpanStatusCode } from "@opentelemetry/api";

const tracer = trace.getTracer("booking-service");

async function loadBooking(bookingId: string) {
  return tracer.startActiveSpan("booking.load", async (span) => {
    try {
      span.setAttribute("app.operation", "booking.load");
      const booking = await repository.findById(bookingId);
      if (!booking) {
        span.setAttribute("app.result", "not_found");
        return null;
      }
      return booking;
    } catch (error) {
      span.recordException(error as Error);
      span.setStatus({ code: SpanStatusCode.ERROR });
      throw error;
    } finally {
      span.end();
    }
  });
}
~~~

Ví dụ chỉ minh họa API. Production cần kiểm soát loại attribute, exception redaction, semantic conventions, async context manager và việc không ghi ID nhạy cảm nếu không có lý do rõ.

## 6. Propagation qua message broker và event

### 6.1. HTTP response kết thúc nhưng workflow vẫn tiếp tục

Khi producer publish message, HTTP request có thể kết thúc trước khi consumer bắt đầu xử lý. Context phải được đưa vào message metadata/header để consumer có thể nối quan hệ nhân quả với producer.

~~~mermaid
sequenceDiagram
    participant API as Booking API
    participant DB as Booking DB
    participant Q as Message Broker
    participant C as Payment Consumer
    participant PSP as Payment Provider
    API->>DB: Commit booking and outbox
    API->>Q: Publish event + trace context
    API-->>API: HTTP response completed
    Q->>C: Deliver event + context
    C->>PSP: Authorize payment
    PSP-->>C: Authorization result
~~~

### 6.2. Gắn context vào message

Với broker hỗ trợ headers/metadata, producer inject propagation fields vào message. Consumer extract context khi nhận. Không cần đưa context vào business payload nếu broker có metadata riêng; nếu event format yêu cầu envelope, phân biệt rõ application schema với tracing metadata.

Ví dụ cấu trúc message:

~~~json
{
  "eventId": "evt_913",
  "eventType": "BookingCreated",
  "tenantId": "tenant_7f31",
  "bookingId": "booking_42",
  "occurredAt": "2026-11-18T09:00:00Z",
  "traceContext": {
    "traceparent": "00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01"
  }
}
~~~

Nếu dùng broker metadata, traceContext ở body chỉ là minh họa cho envelope. Không để downstream tin trace context do tenant/client tự gửi nếu producer chưa xác thực hoặc sanitize.

### 6.3. Consumer span

Consumer thường tạo span đại diện cho xử lý message, ghi attributes như messaging system, destination, operation, message ID đã được bảo vệ, delivery attempt và processing result. Cần ghi cả thời gian xử lý và queue age/lag; hai đại lượng khác nhau:

- Processing duration: thời gian consumer dành để xử lý message.
- Queue age: thời gian từ lúc message được tạo/publish tới lúc bắt đầu xử lý.

Một consumer xử lý trong 20 ms nhưng message đã đợi 30 phút vẫn là vấn đề độ trễ nghiệp vụ.

### 6.4. Acknowledge và span lifetime

Span xử lý message thường kết thúc khi consumer hoàn tất xử lý và ack/nack theo semantics ứng dụng. Nếu công việc tiếp tục sang một worker khác, tạo span cho bước mới và truyền/link context tiếp theo. Không giữ span mở hàng giờ khi job chờ lịch; lưu correlation metadata và tạo span mới khi resume.

## 7. Parent-child hay span link trong bất đồng bộ?

### 7.1. Quan hệ nhân quả khác quan hệ gọi đồng bộ

Parent-child thể hiện span con được tạo trong phạm vi thao tác cha. Với message queue, có thể tạo consumer span là child của producer span nếu semantics và thời gian trace phù hợp. Tuy nhiên, trong nhiều hệ thống event, một event được xử lý độc lập, được gom từ nhiều nguồn hoặc tạo ra nhiều consumer. Span link có thể mô tả quan hệ nhân quả mà không ép tất cả thành một cây duy nhất.

### 7.2. Khi dùng span link?

- Một batch consumer xử lý nhiều message đến từ nhiều trace.
- Một job được kích hoạt bởi nhiều event.
- Fan-in tổng hợp kết quả từ nhiều workflow.
- Một scheduled job tiếp tục công việc đã ghi correlation ID từ trước.
- Trace mới được tạo cho long-running process nhưng cần liên hệ với trace gốc.

### 7.3. Ví dụ fan-out/fan-in

~~~mermaid
flowchart TD
    ROOT[Order accepted trace] --> A[Inventory event]
    ROOT --> B[Payment event]
    ROOT --> C[Notification event]
    A --> D[Inventory consumer trace]
    B --> E[Payment consumer trace]
    C --> F[Notification consumer trace]
    D --> G[Order completion workflow]
    E --> G
    F --> G
~~~

Trong thực tế, mỗi nhánh có thể là trace riêng với link về event/trace nguồn; completion workflow link tới các nhánh đã hoàn thành. Điều này tránh một trace duy nhất kéo dài quá lâu hoặc chứa số lượng span không giới hạn.

### 7.4. Chọn mô hình nhất quán

Quy định cho từng loại message: consumer có kế thừa parent trace hay bắt đầu trace mới; khi xử lý batch, có link tới tất cả producer span hay chỉ một correlation object; retry có thuộc cùng trace, trace mới hay span mới liên kết với attempt trước; workflow continuation lưu trace context gốc bao lâu; khi event được phát lại thủ công, có trace mới và link tới event gốc không.

Không có một cách duy nhất tối ưu. Mục tiêu là giữ causal relationship có ý nghĩa mà vẫn giới hạn kích thước, tuổi thọ và chi phí trace.

## 8. Retry, redelivery và idempotency

### 8.1. Mỗi lần thử là một span có ý nghĩa

Retry có thể xảy ra ở SDK, service, broker hoặc workflow engine. Telemetry nên thể hiện attempt number, delay, nguyên nhân retry và kết quả. Nếu cùng một message được giao lại nhiều lần, log/trace cần phân biệt delivery attempt với business operation ID.

~~~text
Trace / linked operation: payment.authorize
  ├── attempt 1: timeout
  ├── retry delay: 2s
  ├── attempt 2: provider 503
  └── attempt 3: success
~~~

Không tạo vòng lặp vô hạn span con trong một trace cho retry kéo dài nhiều giờ. Có thể tạo trace mới cho mỗi delivery/attempt và link về operation gốc; lưu operation ID ổn định để điều tra.

### 8.2. Phân biệt request ID, message ID và idempotency key

- Request ID: định danh một lần nhận request ở edge/service.
- Message/event ID: định danh một message cụ thể trong broker/event stream.
- Business operation ID: định danh ý định nghiệp vụ qua nhiều lần thử.
- Idempotency key: giúp consumer/provider nhận biết thao tác trùng và tránh side effect lặp.
- Trace ID: định danh đơn vị telemetry; không nên dùng làm business primary key.

Các ID phục vụ mục đích khác nhau. Không thay thế idempotency key bằng trace ID vì retry có thể tạo trace mới nhưng vẫn phải là cùng một business operation.

### 8.3. DLQ và replay

Khi message vượt retry policy, có thể đưa vào dead-letter queue. Cần trace/log ghi lý do, attempt count, original topic, age và operation ID. Replay nên được đánh dấu là thao tác vận hành riêng, tạo telemetry mới và liên kết với message/trace gốc.

Tránh ghi toàn bộ payload nhạy cảm của message vào span hoặc log. Dùng message ID, schema version và field đã redacted.

## 9. Fan-out, fan-in và batch processing

### 9.1. Fan-out

Một service tạo nhiều task song song. Có thể tạo child span cho từng dependency nếu số nhánh hữu hạn và có giá trị chẩn đoán. Nếu có hàng nghìn item, không nên tạo hàng nghìn span chi tiết trong mọi trace production; cân nhắc aggregate attributes, event counts, sampling hoặc trace cho từng nhóm.

### 9.2. Fan-in

Một bước tổng hợp đợi nhiều kết quả. Span aggregator nên ghi số nhánh dự kiến/hoàn tất/thất bại; thời gian đợi lâu nhất; timeout/cancelled branch; kết quả tổng hợp và policy partial success. Dùng span links để nối nhiều nguồn nếu các nhánh là trace độc lập.

### 9.3. Batch consumer

Một consumer có thể lấy một batch gồm message từ nhiều trace. Không nên gán parent của message đầu tiên cho toàn batch vì sẽ làm sai quan hệ nhân quả. Tạo batch processing span và link tới các producer contexts được chọn; nếu số link rất lớn, giữ correlation ở batch manifest/log có kiểm soát và giới hạn sampling.

### 9.4. Scheduled job

Job chạy định kỳ có thể không có request cha. Tạo root span cho lần chạy, ghi schedule name, run ID, scheduled time, start delay, batch size và result. Nếu job tiếp tục workflow cũ, thêm link tới operation/event nguồn. Không dùng tên job làm ID duy nhất vì mỗi lần chạy cần phân biệt.

## 10. Long-running workflow và context persistence

### 10.1. Không giữ execution context qua thời gian dài

Một workflow có thể chờ phê duyệt, callback hoặc đối tác phản hồi nhiều giờ. Giữ thread-local/async context hoặc span mở trong thời gian này có thể gây rò rỉ tài nguyên và trace quá dài.

Thay vào đó:

1. Lúc bắt đầu, ghi operation ID và trace context cần thiết vào workflow state theo schema rõ.
2. Kết thúc span hiện tại khi bước đó xong.
3. Khi workflow resume, tạo trace/span mới.
4. Thêm span link về context đã lưu nếu còn phù hợp.
5. Ghi workflow execution ID, step name và attempt number.

### 10.2. Lưu context có chọn lọc

Chỉ lưu field cần thiết để liên kết telemetry, thường là traceparent/tracestate hoặc trace ID/span ID đã chuẩn hóa cùng expiry. Không lưu toàn bộ request headers vì có thể chứa cookie, token và PII.

### 10.3. Context hết hạn

Nếu trace gốc đã qua retention hoặc không còn được backend giữ, operation vẫn cần log/metrics của lần chạy mới. Correlation ID nghiệp vụ ổn định giúp liên kết các lần thực thi dù trace backend không còn trace cũ.

## 11. Correlation giữa trace, logs và metrics

### 11.1. Structured log

~~~json
{
  "timestamp": "2026-11-18T09:00:02.120Z",
  "severity": "ERROR",
  "service.name": "payment-consumer",
  "message": "payment authorization timed out",
  "trace_id": "4bf92f3577b34da6a3ce929d0e0e4736",
  "span_id": "00f067aa0ba902b7",
  "operation_id": "payop_913",
  "event_id": "evt_913",
  "attempt": 2,
  "error.type": "TimeoutError"
}
~~~

Ví dụ chỉ chứa ID giả lập. Không ghi payment instrument, access token hoặc payload đầy đủ. Trường trace ID/span ID nên lấy từ active context bằng logging instrumentation để giảm sai lệch.

### 11.2. Metrics và trace exemplars

Metrics histogram có thể liên kết một số observation với trace exemplar. Khi thấy latency bucket bất thường, người vận hành có thể mở trace đại diện để xem span chi tiết. Exemplar cần sampling và label policy phù hợp; không nên gắn trace ID thành metric label cho mọi measurement vì cardinality tăng không giới hạn.

### 11.3. Correlation ID không thay trace

Business correlation ID có thể tồn tại lâu và liên kết nhiều trace, ví dụ booking ID hoặc workflow ID. Trace ID phù hợp cho telemetry trace cụ thể. Cần kiểm soát business ID nhạy cảm và tránh đưa nó vào label metric.

## 12. Semantic conventions và thuộc tính span

### 12.1. Dùng tên và attribute nhất quán

OpenTelemetry semantic conventions định nghĩa các tên attribute/operation phổ biến cho HTTP, RPC, database, messaging và runtime. Dùng convention giúp query và dashboard hoạt động giữa nhiều ngôn ngữ, SDK và backend.

### 12.2. Ưu tiên low-cardinality attributes

Attributes phù hợp thường gồm service.name, service.version, deployment.environment, HTTP method, route template, response status code, messaging system, destination name và operation, database system và operation, error type và outcome.

Tránh dùng raw URL, user email, request ID, message ID, arbitrary tenant ID hoặc SQL literal làm metric dimensions. Một số ID có thể hữu ích trong trace/log nhưng cần sampling, redaction và access control.

### 12.3. Không ghi payload tùy tiện

Message body, HTTP headers, SQL statement và exception message có thể chứa PII, token, payment data hoặc secret. Chỉ capture field cần thiết; redact header; dùng allowlist attributes; giới hạn kích thước; phân quyền truy cập telemetry và đặt retention.

## 13. Sampling cho distributed traces

### 13.1. Head sampling

Head sampler quyết định lấy trace từ đầu, trước khi biết toàn bộ kết quả. Nó rẻ và giảm tải export/storage, nhưng có thể bỏ qua trace lỗi nếu quyết định lấy/không lấy đã được đưa ra ở root.

### 13.2. Parent-based sampling

Parent-based sampler thường kế thừa sampling decision từ parent để các service cùng trace có quyết định nhất quán. Cấu hình không thống nhất có thể tạo trace đứt đoạn: service A export nhưng service B không export, hoặc ngược lại.

### 13.3. Tail sampling

Tail sampler quyết định sau khi nhận các span của trace, có thể giữ trace lỗi, chậm hoặc có thuộc tính đáng quan tâm. Nó cần collector giữ trace data trong bộ nhớ/buffer đủ lâu, nên tăng yêu cầu về capacity, network và vận hành. Trong môi trường phân tán, cần routing span theo trace ID tới cùng tail-sampling decision point hoặc cơ chế tương đương.

### 13.4. Sampling policy gợi ý

| Loại trace | Chính sách có thể xem xét |
|---|---|
| Request bình thường, lưu lượng lớn | Head sampling theo tỷ lệ |
| Error/exception | Tail sampling ưu tiên giữ |
| Latency vượt ngưỡng | Tail sampling hoặc latency-aware policy |
| Security-sensitive operation | Sampling/audit theo policy, không thay audit log bắt buộc |
| Debug tenant/operation cụ thể | Temporary targeted sampling có approval và expiry |

Sampling không phải kiểm soát bảo mật hoặc audit completeness. Sự kiện bắt buộc phục vụ compliance cần cơ chế log/audit riêng có bảo đảm retention.

## 14. Telemetry pipeline và OpenTelemetry Collector

### 14.1. Tách instrumentation khỏi backend

Ứng dụng instrument bằng OTel API/SDK và export qua OTLP tới Collector hoặc backend. Collector có thể nhận, batch, enrich, filter, redact, sample và route telemetry.

~~~mermaid
flowchart LR
    S1[Service A] --> OTEL[OTel Collector]
    S2[Service B] --> OTEL
    W[Async Worker] --> OTEL
    OTEL --> PROC[Batch / filter / redact / sample]
    PROC --> TR[Trace backend]
    PROC --> ME[Metrics backend]
    PROC --> LO[Log backend]
~~~

### 14.2. Collector deployment

- Agent/sidecar hoặc daemonset phù hợp thu telemetry gần workload.
- Gateway collector có thể batch, tail sample và route tập trung.
- Multi-tenant environment cần auth, tenant isolation và quota ở collector.
- Collector cần resource limits, queue/buffer và retry export.
- Telemetry pipeline cần quan sát chính nó: dropped spans, queue size, exporter errors và memory pressure.

### 14.3. Backpressure và mất telemetry

Khi backend chậm, collector queue có thể tăng và đầy. Cần quyết định queue memory hay persistent queue; retry và exponential backoff; batch size và timeout; drop policy khi quá tải; priority cho telemetry quan trọng; alert về span/log/metric dropped.

Không để telemetry làm sập ứng dụng nghiệp vụ. Export nên non-blocking và có giới hạn tài nguyên; telemetry có thể giảm chất lượng trong khủng hoảng nhưng phải phát metric cho biết dữ liệu đang bị drop.

## 15. Bảo mật và quyền riêng tư trong propagation

### 15.1. Trace context là metadata, không phải credential

Traceparent không chứng minh danh tính caller và không cấp quyền truy cập. Không dùng trace ID như access token, authorization key hoặc bằng chứng user identity.

### 15.2. Baggage

Baggage có thể truyền key-value context qua service, ví dụ tenant tier hoặc workflow class. Baggage có thể lan rộng tới nhiều dependency và external service, làm tăng kích thước header và rủi ro lộ dữ liệu. Chỉ truyền field allowlisted, ít nhạy cảm, có giới hạn size và expiry. Không đưa email, access token, payment ID hoặc dữ liệu PII vào baggage.

### 15.3. Boundary với bên ngoài

Khi gọi payment provider hoặc webhook bên thứ ba, cân nhắc không truyền context nội bộ hoặc baggage nhạy cảm. Có thể tạo outbound span nội bộ, chỉ gửi correlation header được thỏa thuận và dùng trace link khi phản hồi quay lại. Sanitize context inbound từ bên ngoài và không để caller tự quyết định sampling priority/trust flag.

### 15.4. Multi-tenant telemetry

Trong SaaS, telemetry có thể chứa tenant metadata. Phải xác định ai được xem trace/log, có thể truy vấn tenant khác không, retention theo plan ra sao và tenant có được export telemetry hay không. Dùng tenant attribute trong trace khi cần điều tra, nhưng tránh tạo metric series cho từng tenant nếu số tenant lớn.

## 16. Kiểm thử context propagation

### 16.1. Test theo giao thức

- HTTP inbound/outbound có extract/inject traceparent đúng.
- RPC metadata mang context đúng qua client/server.
- Message producer ghi context vào header/metadata.
- Consumer extract context và tạo span/link.
- Retry có attempt và parent/link semantics đã định nghĩa.
- Batch/fan-in không gán sai parent.
- Scheduled job tạo root span hoặc link đúng operation trước.
- Context không rò qua request đồng thời trong cùng process.

### 16.2. Integration test

Tạo một workflow test xuyên API, broker và consumer. Kiểm tra trace ID có thể được nối theo policy; message ID và operation ID khớp; span end/status đúng; retry được biểu diễn; không có secret/PII trong attributes.

### 16.3. Load test và failure test

Kiểm tra collector bị chậm, broker redelivery, consumer restart, message batch lớn, trace sampling cao, network partition và export backend down. Đo overhead CPU/memory/network, dropped telemetry và latency của request nghiệp vụ.

## 17. Ví dụ end-to-end: Booking tạo thanh toán bất đồng bộ

### 17.1. Luồng nghiệp vụ

1. Booking API nhận yêu cầu và tạo root/server span.
2. API commit booking cùng outbox event.
3. Publisher đọc outbox, tạo publish span và inject trace context.
4. Broker lưu message; HTTP request có thể đã kết thúc.
5. Payment consumer nhận message, extract context và tạo consumer span.
6. Consumer gọi payment provider, ghi child span và kết quả.
7. Nếu lỗi tạm thời, retry được ghi nhận theo attempt; operation ID ổn định qua lần thử.
8. Khi hoàn tất, consumer phát PaymentAuthorized/PaymentFailed event.
9. Notification worker nhận event và gửi thông báo; trace link thể hiện quan hệ với payment operation.

### 17.2. Trace model minh họa

~~~text
Trace A: POST /bookings
  ├── booking.create
  ├── db.transaction
  └── outbox.publish
       +--> message trace context

Trace B: payment.consume (linked to Trace A)
  ├── payment.authorize attempt=1 [timeout]
  └── payment.authorize attempt=2 [success]

Trace C: notification.consume (linked to PaymentAuthorized)
  └── email.send
~~~

Các trace độc lập giúp giới hạn tuổi thọ và kích thước. Business operation ID và event ID kết nối workflow; span link ghi quan hệ nhân quả. Nếu hệ thống chọn parent-child xuyên broker cho workflow ngắn, vẫn cần định nghĩa giới hạn trace và xử lý redelivery.

### 17.3. Metrics đi kèm

- booking_create_duration và booking_create_errors.
- outbox_publish_lag.
- payment_queue_oldest_message_age.
- payment_consumer_processing_duration.
- payment_retry_total theo reason class.
- payment_authorization_success_rate.
- notification_delivery_failures.
- Collector dropped spans/export failures.

Metric labels nên là service, operation, region, status class hoặc topic cố định. Không thêm bookingId/messageId làm label.

### 17.4. Khi xảy ra sự cố

Nếu khách hàng báo booking đã tạo nhưng không nhận xác nhận thanh toán:

1. Tìm theo booking/workflow correlation ID được phép.
2. Mở trace tạo booking để xác định outbox publish.
3. Kiểm tra queue age/lag và consumer health.
4. Mở trace payment consume và attempt.
5. Tra structured log theo trace/span/event ID.
6. Xác định lỗi provider, retry, DLQ hay notification.
7. Đối soát trạng thái nghiệp vụ trong system of record; không suy ra payment state chỉ từ trace.

Telemetry hỗ trợ điều tra; database/ledger vẫn là nguồn chuẩn cho trạng thái giao dịch.

## 18. Sai lầm thường gặp

| Sai lầm | Hệ quả | Cách cải thiện |
|---|---|---|
| Chỉ dựa vào timestamp để nối log | Clock skew và lưu lượng đồng thời làm kết luận sai | Trace context và correlation ID |
| Không inject context vào message | Trace bị đứt ở broker | Propagation qua headers/metadata |
| Gán consumer batch cho producer đầu tiên | Quan hệ nhân quả sai | Batch span với span links |
| Một trace kéo dài nhiều ngày | Trace lớn, tốn bộ nhớ và khó query | Trace mới theo execution, link với workflow gốc |
| Dùng trace ID làm idempotency key | Retry có thể tạo operation mới hoặc sai semantics | Business operation ID/idempotency key riêng |
| Ghi toàn bộ headers/message payload | Lộ token, PII và secret | Allowlist, redaction và giới hạn kích thước |
| Dùng tenant/user ID làm metric label | Cardinality tăng không giới hạn | Aggregate metric; ID chi tiết ở trace/log có kiểm soát |
| Head sample bỏ qua trace lỗi | Không có bằng chứng cho sự cố hiếm | Tail sampling hoặc error-aware sampling |
| Các service cấu hình sampler khác nhau | Trace thiếu span hoặc không nhất quán | Parent-based policy và cấu hình chung |
| Collector export blocking | Telemetry gây tăng latency hoặc làm sập app | Async export, queue, backpressure và resource limit |
| Không đo dropped spans | Dashboard thiếu dữ liệu mà không ai biết | Collector self-observability và alert |
| Dùng tracing thay audit | Sự kiện quan trọng bị sampling/drop | Audit log riêng với completeness/retention policy |

## 19. Đánh giá theo Well-Architected

| Trụ cột | Câu hỏi | Biện pháp và đánh đổi |
|---|---|---|
| **Operational Excellence** | Có truy vết request/event qua service, retry và workflow không? | OTel conventions, trace/log correlation, runbook; cần duy trì propagation contract |
| **Security** | Telemetry có mang secret, PII hoặc context từ caller không tin cậy? | Allowlist, redaction, access control, baggage policy và retention |
| **Reliability** | Collector/backend down có ảnh hưởng ứng dụng không? | Async export, buffer có giới hạn, retry và drop alert |
| **Performance Efficiency** | Instrumentation và sampling có overhead phù hợp không? | Span có ý nghĩa, sampling, batch export và cardinality control |
| **Cost Optimization** | Trace/log có bị lưu quá nhiều hoặc chứa thuộc tính cardinality cao? | Tail/head sampling có chủ đích, retention tiers và aggregation |
| **Sustainability** | Có phát telemetry dư thừa và truyền payload lớn không cần thiết? | Instrumentation chọn lọc, compact attributes và sampling |

Thiết kế telemetry phải cân bằng mức độ quan sát với tài nguyên và quyền riêng tư. Mất trace không được làm mất khả năng xử lý nghiệp vụ; ngược lại, telemetry bị drop cần được phát hiện để đội vận hành không tin nhầm vào dashboard thiếu dữ liệu.

## 20. Bài tập áp dụng

### Bài tập A — Trace đứt ở queue

Booking API có trace đầy đủ, nhưng Payment Consumer luôn tạo trace mới không liên hệ được với request ban đầu.

**Câu hỏi:** Thiếu thành phần nào?

**Gợi ý:** Producer chưa inject trace context vào message metadata hoặc consumer không extract. Xác định propagation contract cho broker và kiểm tra bằng integration test.

### Bài tập B — Batch nhiều nguồn

Một worker gom 500 event từ nhiều trace vào một batch và xử lý cùng lúc.

**Câu hỏi:** Có nên đặt producer span của event đầu tiên làm parent cho batch span?

**Gợi ý:** Không, vì các event có nhiều nguồn nhân quả. Tạo batch processing span và link tới producer contexts phù hợp; giới hạn số link và giữ batch manifest nếu cần.

### Bài tập C — Retry nhiều giờ

Payment message được retry trong 12 giờ, mỗi attempt tạo thêm nhiều span trong cùng một trace.

**Câu hỏi:** Tác động và thiết kế khác?

**Gợi ý:** Trace quá dài/lớn, khó giữ và query. Tạo trace theo delivery/workflow step, link operation gốc, giữ business operation ID và attempt metadata.

### Bài tập D — Metric cardinality

Dashboard tạo metric label theo bookingId và tenantId cho mọi request.

**Câu hỏi:** Vấn đề và cách thay thế?

**Gợi ý:** Cardinality và chi phí tăng mạnh. Dùng label cố định như service, route, region, status class; điều tra ID cụ thể qua trace/log được phân quyền.

### Bài tập E — Collector outage

Collector gateway đầy queue và export chậm; application latency bắt đầu tăng.

**Câu hỏi:** Cần kiểm tra và thay đổi gì?

**Gợi ý:** Export có blocking hay không, queue limit/backoff, memory pressure và dropped telemetry. Chuyển export non-blocking, giới hạn tài nguyên, batch và cảnh báo drop.

### Bài tập F — Trace bị lộ dữ liệu

Span HTTP ghi toàn bộ URL query string, trong đó có email và access token.

**Câu hỏi:** Khắc phục ở lớp nào?

**Gợi ý:** Chặn capture raw URL/query/header, dùng route template, redaction ở instrumentation và collector, review retention/access; rotate token nếu credential đã bị lộ.

## 21. Checklist trước khi đưa distributed telemetry vào production

- [ ] Đã mô hình hóa các flow đồng bộ, message, retry, batch, fan-out và long-running workflow.
- [ ] Có instrumentation boundary rõ cho inbound/outbound request, database, publish/consume và job.
- [ ] Context propagation thống nhất giữa service theo W3C Trace Context hoặc contract được công bố.
- [ ] Producer inject và consumer extract context qua header/metadata; không tin context caller tùy tiện.
- [ ] Đã quy định parent-child và span link cho event, fan-in, batch và workflow continuation.
- [ ] Request ID, trace ID, span ID, message ID và business operation ID có vai trò tách biệt.
- [ ] Retry/redelivery có attempt, reason, delay và trace relationship rõ.
- [ ] Long-running workflow lưu context tối thiểu, có expiry và tạo trace mới khi resume.
- [ ] Logs có structured fields và trace/span correlation; payload/secret được redacted.
- [ ] Metrics dùng low-cardinality labels và có queue age/lag, throughput, error, retry.
- [ ] Sampling policy nhất quán; trace lỗi/chậm được giữ theo mục tiêu.
- [ ] Collector có batch, queue, retry, backpressure, resource limit và self-observability.
- [ ] Telemetry export không block critical path hoặc làm sập ứng dụng.
- [ ] Baggage và external boundary có allowlist, size limit và privacy review.
- [ ] Multi-tenant trace/log access, retention và tenant metadata được kiểm soát.
- [ ] Có test propagation HTTP/RPC/broker, fan-out/fan-in, batch và retry.
- [ ] Có failure/load test cho collector/backend outage và đo overhead.
- [ ] Có dashboard nối trace, metrics và logs; alert phát hiện dropped telemetry.
- [ ] Audit/compliance event dùng cơ chế riêng khi yêu cầu completeness.
- [ ] Runbook hướng dẫn điều tra theo operation ID, event ID, trace ID và nguồn chuẩn nghiệp vụ.

**Điểm cốt lõi:** telemetry cho hệ thống phân tán cần giữ được quan hệ nhân quả khi công việc rời khỏi process ban đầu. Trace context nối các thao tác; span links biểu diễn quan hệ bất đồng bộ và fan-in; operation/message ID theo dõi nghiệp vụ và delivery; metrics đo sức khỏe; logs giải thích chi tiết. Khi propagation, sampling, privacy và collector được thiết kế có chủ đích, đội vận hành có thể tìm ra bottleneck và lỗi xuyên service mà không làm telemetry trở thành rủi ro về hiệu năng, chi phí hoặc dữ liệu nhạy cảm.
