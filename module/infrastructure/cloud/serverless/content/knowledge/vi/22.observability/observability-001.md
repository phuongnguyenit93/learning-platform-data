# Thiết kế log có cấu trúc cho function và workflow

Trong ứng dụng serverless, một request có thể đi qua API gateway, Java function, queue, nhiều worker và workflow kéo dài qua nhiều lần thực thi. Mỗi function thường chỉ sống trong một invocation; một workflow có thể tạm dừng, chờ event rồi tiếp tục ở một execution environment khác. Nếu log chỉ là những dòng text rời rạc như “started”, “failed” hoặc “done”, nhóm vận hành khó ghép các sự kiện thành một câu chuyện hoàn chỉnh.

Structured logging giải quyết vấn đề đó bằng cách ghi mỗi sự kiện dưới dạng các field có tên và kiểu dữ liệu ổn định, thường được xuất thành JSON. Log có thể được tìm kiếm theo service, function, invocation, trace, correlation ID, workflow run, step, event type và kết quả. Khi thiết kế đúng, nhóm có thể trả lời những câu hỏi quan trọng: request đi qua đâu, bước nào chậm, message đã retry bao nhiêu lần, workflow đang dừng ở đâu, function cold start hay dependency mới là nguyên nhân và phiên bản triển khai nào gây lỗi.

Trong module **CLOUD_SERVERLESS**, người học phát triển Java function kích hoạt bởi HTTP, message hoặc event, đồng thời xử lý trạng thái, quyền truy cập, retry, idempotency, cold start, mở rộng và chi phí. Bài này tập trung vào cách thiết kế schema log, ghi log trong Java function, truyền context qua queue và quan sát workflow nhiều bước.

## 1. Vì sao function và workflow cần log có cấu trúc?

Một function đơn lẻ có thể xử lý request trong vài chục mili giây. Nhưng một quy trình serverless có thể trải dài qua nhiều thành phần:

1. API gateway nhận request HTTP.
2. Function xác thực và ghi nhận yêu cầu.
3. Function gửi message vào queue.
4. Worker nhận message và gọi database.
5. Worker gọi dịch vụ bên ngoài.
6. Workflow chờ callback hoặc timer.
7. Một function khác tiếp tục và hoàn tất nghiệp vụ.

Mỗi bước có invocation ID, thời điểm, runtime và có thể cả Region riêng. Một dòng log chỉ có nội dung “payment failed” không đủ để xác định payment nào, workflow nào, retry lần mấy hoặc dependency nào gây lỗi.

Structured log giúp:

- Tìm tất cả sự kiện thuộc cùng request hoặc workflow.
- Phân biệt invocation mới với lần retry của cùng message.
- Đo duration theo function, step và dependency.
- Tạo dashboard và alert từ field ổn định.
- So sánh hành vi giữa deployment version hoặc Region.
- Điều tra lỗi mà không cần ghi toàn bộ request/event payload.
- Tổng hợp throughput, retry, failure và chi phí vận hành.

Log có cấu trúc không thay thế trace, metric, audit log hoặc business database. Mỗi loại telemetry phục vụ một mục đích khác nhau và cần được liên kết bằng các ID phù hợp.

## 2. Phân biệt log, metric, trace và audit event

| Loại dữ liệu | Trả lời câu hỏi | Ví dụ |
|---|---|---|
| Log | Điều gì đã xảy ra tại một thời điểm? | Function nhận message, bước workflow thất bại |
| Metric | Việc đó xảy ra thường xuyên hoặc kéo dài bao nhiêu? | Invocation count, p95 duration, retry rate |
| Trace | Một request đi qua những service/span nào? | API → function → queue producer → worker → database |
| Audit event | Ai đã thực hiện hành động quan trọng và hành động đó là gì? | Người dùng thay đổi quyền, quản trị viên xóa resource |

Một log event thường có timestamp, severity, service và event name. Metric tổng hợp nhiều lần thực thi thành một chuỗi số liệu. Trace mô tả quan hệ cha-con giữa các span. Audit event cần tính toàn vẹn, retention và quyền truy cập theo yêu cầu kiểm toán.

Không dùng log làm nguồn dữ liệu chuẩn để quyết định một đơn hàng đã thanh toán hay chưa. Log có thể đến trễ, bị sampling, bị giới hạn dung lượng hoặc không được chuyển đến sink khi runtime kết thúc. Trạng thái nghiệp vụ phải nằm trong database, event store hoặc workflow engine có durability phù hợp.

## 3. Thiết kế schema JSON nhất quán

Một log event nên là một object có field ổn định. Các field thường dùng:

| Field | Ý nghĩa | Ví dụ |
|---|---|---|
| timestamp | Thời điểm event xảy ra theo UTC | 2026-11-17T10:15:30.123Z |
| severity | Mức độ log | INFO, WARN, ERROR |
| service.name | Tên service | orders-service |
| service.version | Phiên bản triển khai | 2.4.1 |
| deployment.environment | Môi trường | production |
| cloud.region | Region thực thi | ap-southeast-1 |
| faas.name | Tên function | ProcessOrder |
| faas.invocation_id | ID của lần gọi function | inv-8f21 |
| event.name | Tên sự kiện log | order.processing.started |
| trace_id | ID trace phân tán | 4bf92f... |
| span_id | ID span hiện tại | 00f067... |
| correlation_id | ID liên kết một business flow | corr-72a1 |
| workflow.id | Định danh workflow | order-fulfillment |
| workflow.run_id | Một lần chạy workflow | run-9c12 |
| workflow.step | Tên bước | reserve-inventory |
| message.id | ID message của transport | msg-183 |
| event.id | ID nghiệp vụ ổn định | evt-720 |
| outcome | Kết quả bước xử lý | success, failure, retry |
| duration_ms | Thời gian xử lý | 84 |
| retry.attempt | Số lần thử | 2 |
| error.code | Mã lỗi ổn định | INVENTORY_TIMEOUT |

Không phải log nào cũng cần tất cả field. Chỉ xuất field có ý nghĩa cho event đó; field không áp dụng có thể được bỏ qua thay vì tạo object chứa hàng chục giá trị null.

### Ví dụ JSON

~~~json
{
  "timestamp": "2026-11-17T10:15:30.123Z",
  "severity": "INFO",
  "schema_version": 1,
  "service": {
    "name": "orders-service",
    "version": "2.4.1"
  },
  "deployment": {
    "environment": "production"
  },
  "cloud": {
    "region": "ap-southeast-1"
  },
  "faas": {
    "name": "ProcessOrder",
    "invocation_id": "inv-8f21"
  },
  "event": {
    "name": "order.processing.started",
    "id": "evt-720"
  },
  "correlation_id": "corr-72a1",
  "trace_id": "4bf92f3577b34da6a3ce929d0e0e4736",
  "span_id": "00f067aa0ba902b7",
  "workflow": {
    "id": "order-fulfillment",
    "run_id": "run-9c12",
    "step": "reserve-inventory"
  },
  "retry": {
    "attempt": 2
  },
  "message": "Order processing started"
}
~~~

Schema có thể dùng nested object hoặc flat field. Điều quan trọng là thống nhất cách đặt tên và kiểu dữ liệu giữa các function để query không phải xử lý nhiều biến thể.

## 4. Đặt tên event có quy ước

Event name nên mô tả sự kiện đã xảy ra, không phải câu lệnh mơ hồ. Dùng quy ước nhất quán như domain.object.action hoặc domain.operation.outcome.

Ví dụ:

| Event name | Ý nghĩa |
|---|---|
| function.invocation.started | Một invocation bắt đầu |
| function.invocation.completed | Invocation hoàn tất |
| function.invocation.failed | Invocation thất bại |
| order.validation.completed | Kiểm tra đơn hàng hoàn tất |
| order.processing.started | Bắt đầu xử lý đơn hàng |
| inventory.reservation.failed | Giữ tồn kho thất bại |
| message.received | Consumer nhận message |
| message.retry.scheduled | Message sẽ được thử lại |
| workflow.started | Workflow bắt đầu |
| workflow.step.completed | Một step hoàn tất |
| workflow.waiting | Workflow đang chờ event/timer |
| workflow.completed | Workflow hoàn tất |
| workflow.failed | Workflow thất bại |

Không dùng tên event thay đổi theo dữ liệu như order.12345.created. Giá trị động thuộc field riêng, ví dụ order.id hoặc event.id. Nếu nhúng ID vào event name, query khó hơn và tạo nhiều loại event không cần thiết.

### Event name và message

Event name là mã máy đọc được, ổn định qua phiên bản. Message là câu mô tả dành cho người đọc. Ví dụ event.name có thể là inventory.reservation.failed trong khi message là “Inventory service did not respond before deadline”.

Không dùng message tự do làm tiêu chí alert chính vì nội dung có thể thay đổi theo code hoặc ngôn ngữ. Dùng event.name, error.code, outcome và severity.

## 5. Severity và quy tắc chọn log level

| Level | Dùng khi nào | Ví dụ |
|---|---|---|
| TRACE | Chi tiết rất nhỏ, chỉ bật khi chẩn đoán có kiểm soát | Một nhánh xử lý nội bộ |
| DEBUG | Thông tin phát triển hoặc chẩn đoán không cần ở production thường xuyên | Quyết định chọn cache key |
| INFO | Mốc vòng đời bình thường có giá trị vận hành | Invocation bắt đầu, workflow hoàn tất |
| WARN | Tình huống bất thường nhưng đã xử lý hoặc có thể phục hồi | Retry được lên lịch, fallback được dùng |
| ERROR | Một operation hoặc invocation không hoàn tất như yêu cầu | Database write thất bại, workflow step lỗi |
| FATAL (nếu nền tảng hỗ trợ) | Ứng dụng không thể tiếp tục khởi tạo hoặc phục vụ | Runtime bootstrap thất bại nghiêm trọng |

Không log mọi request thành ERROR chỉ vì status HTTP là 4xx. Một request sai định dạng có thể là hành vi client bình thường. Tương tự, một retry thành công sau lỗi tạm thời có thể được ghi WARN thay vì ERROR ở mức invocation, nhưng vẫn cần metric retry.

Chọn level theo tác động và khả năng hành động. Nếu mọi dòng đều là ERROR, alert sẽ mất ý nghĩa và chi phí log tăng.

SLF4J chuẩn có các level TRACE, DEBUG, INFO, WARN và ERROR; FATAL không phải level chuẩn của SLF4J. Nếu hệ thống cần phân biệt fatal, ghi ERROR kèm field như error.severity=fatal hoặc dùng quy ước riêng được backend hỗ trợ.

## 6. Java structured logging với SLF4J

SLF4J 2.x cung cấp fluent logging API cho phép thêm key-value vào một event. Logging backend và encoder phải được cấu hình để xuất các cặp đó thành JSON fields. Chỉ viết chuỗi có dấu bằng không tự biến log thành JSON có cấu trúc.

Ví dụ:

~~~java
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

public final class OrderFunction {
    private static final Logger log =
            LoggerFactory.getLogger(OrderFunction.class);

    public void process(
            String invocationId,
            String correlationId,
            String eventId) {

        log.atInfo()
            .addKeyValue("event.name", "order.processing.started")
            .addKeyValue("faas.name", "ProcessOrder")
            .addKeyValue("faas.invocation_id", invocationId)
            .addKeyValue("correlation_id", correlationId)
            .addKeyValue("event.id", eventId)
            .log("Order processing started");
    }
}
~~~

Dùng API này với SLF4J 2.x và backend tương thích. Nếu project vẫn dùng SLF4J 1.x, chọn logging library hoặc adapter phù hợp thay vì copy nguyên ví dụ.

### Cấu hình JSON encoder

Một ứng dụng Java có thể dùng Logback cùng JSON encoder tương thích để xuất timestamp, level, logger, message và key-value fields thành JSON. Ví dụ cấu hình khái quát:

~~~xml
<configuration>
  <appender name="JSON_CONSOLE"
            class="ch.qos.logback.core.ConsoleAppender">
    <encoder class="net.logstash.logback.encoder.LogstashEncoder">
      <includeMdc>true</includeMdc>
    </encoder>
  </appender>

  <root level="INFO">
    <appender-ref ref="JSON_CONSOLE"/>
  </root>
</configuration>
~~~

Cần thêm dependency encoder tương thích với phiên bản Logback và kiểm tra output thực tế. Một số encoder đưa MDC vào JSON nhưng xử lý SLF4J fluent key-value theo cấu hình/phiên bản riêng. Hãy viết integration test cho định dạng output, không giả định XML trên tự động bao phủ mọi field.

### JSON output mong muốn

Kết quả nên là một object JSON trên mỗi dòng, ví dụ:

~~~json
{
  "@timestamp": "2026-11-17T10:15:30.123Z",
  "level": "INFO",
  "logger_name": "OrderFunction",
  "message": "Order processing started",
  "event.name": "order.processing.started",
  "faas.name": "ProcessOrder",
  "faas.invocation_id": "inv-8f21",
  "correlation_id": "corr-72a1",
  "event.id": "evt-720"
}
~~~

Không dùng pretty-printed multi-line JSON cho production console nếu collector kỳ vọng một event trên một dòng. Một record nhiều dòng có thể bị tách thành nhiều log event hoặc ghép sai khi thu thập.

## 7. Tạo log tại các mốc vòng đời function

Một invocation thường có các mốc:

1. Runtime nhận event và bắt đầu invocation.
2. Function parse và validate input.
3. Function thực hiện nghiệp vụ.
4. Function gọi dependency hoặc gửi message.
5. Function trả kết quả hoặc thất bại.
6. Runtime kết thúc invocation.

Không nhất thiết ghi một log cho mọi dòng code. Hãy chọn các mốc giúp vận hành hiểu tiến trình và đo duration. Một function ngắn có thể chỉ cần started/completed/failed và dependency failure; function phức tạp có thể cần event cho từng phase.

### Ví dụ function có duration

~~~java
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

public final class OrderHandler {
    private static final Logger log =
            LoggerFactory.getLogger(OrderHandler.class);

    public OrderResponse handle(
            OrderRequest request,
            String invocationId,
            String correlationId) {

        long startedAt = System.nanoTime();
        String outcome = "success";

        log.atInfo()
            .addKeyValue("event.name", "function.invocation.started")
            .addKeyValue("faas.name", "CreateOrder")
            .addKeyValue("faas.invocation_id", invocationId)
            .addKeyValue("correlation_id", correlationId)
            .log("Invocation started");

        try {
            validate(request);
            OrderResponse response = createOrder(request);

            log.atInfo()
                .addKeyValue("event.name", "order.created")
                .addKeyValue("faas.invocation_id", invocationId)
                .addKeyValue("correlation_id", correlationId)
                .addKeyValue("outcome", "success")
                .log("Order created");

            return response;
        } catch (RuntimeException ex) {
            outcome = "failure";

            log.atError()
                .setCause(ex)
                .addKeyValue("event.name", "function.invocation.failed")
                .addKeyValue("faas.invocation_id", invocationId)
                .addKeyValue("correlation_id", correlationId)
                .addKeyValue("error.type", ex.getClass().getSimpleName())
                .addKeyValue("error.code", "ORDER_PROCESSING_FAILED")
                .log("Invocation failed");

            throw ex;
        } finally {
            long durationMs =
                    (System.nanoTime() - startedAt) / 1_000_000;

            log.atInfo()
                .addKeyValue("event.name", "function.invocation.finished")
                .addKeyValue("faas.invocation_id", invocationId)
                .addKeyValue("outcome", outcome)
                .addKeyValue("duration_ms", durationMs)
                .log("Invocation finished");
        }
    }

    private void validate(OrderRequest request) {
        // Validate request.
    }

    private OrderResponse createOrder(OrderRequest request) {
        // Execute business operation.
        return new OrderResponse();
    }
}
~~~

Đây là ví dụ thiết kế log; request, response và các kiểu nghiệp vụ là lớp minh họa. Cấu hình exception cause phải tuân theo chính sách bảo vệ dữ liệu vì stack trace hoặc exception message có thể chứa thông tin nhạy cảm. Nếu không thể bảo đảm, chỉ ghi error type/code ở sink phổ thông và chuyển chi tiết đã lọc sang diagnostic sink riêng.

Dùng System.nanoTime() để đo duration vì đây là đồng hồ monotonic. Không lấy hiệu hai giá trị wall-clock nếu hệ thống có thể đồng bộ hoặc điều chỉnh clock trong lúc invocation chạy.

## 8. Invocation ID, correlation ID và trace ID khác nhau

Ba ID này giải quyết ba bài toán khác nhau:

| ID | Phạm vi | Dùng để |
|---|---|---|
| Invocation ID | Một lần thực thi function | Tìm log của đúng một invocation |
| Correlation ID | Một business request/flow xuyên nhiều service | Gom sự kiện thuộc cùng nghiệp vụ |
| Trace ID | Một distributed trace | Liên kết spans theo quan hệ tracing |

Một HTTP request có thể tạo invocation ID cho API function, sau đó enqueue message. Worker nhận message sẽ có invocation ID khác. Correlation ID có thể được giữ xuyên suốt để nối business flow. Trace ID thường được propagate theo W3C Trace Context hoặc cơ chế tracing của nền tảng; một workflow kéo dài nhiều giờ/ngày có thể có nhiều trace hoặc trace segment liên kết với cùng workflow run.

Không dùng invocation ID thay correlation ID vì mỗi lần retry là invocation mới. Không tự tạo trace ID bằng cách lấy order ID; trace ID phải tuân theo định dạng tracing và không mang ý nghĩa nghiệp vụ.

### Correlation ID nên được tạo ở đâu?

Ưu tiên gateway hoặc service đầu tiên tạo một ID ngẫu nhiên nếu request chưa có ID tin cậy. Nếu client gửi correlation ID, validate định dạng/độ dài và áp dụng chính sách để tránh client cố tình làm nhiễu log. Correlation ID không phải credential và không chứng minh danh tính người dùng.

### W3C Trace Context

W3C Trace Context dùng các header như traceparent và tracestate để truyền thông tin trace giữa các service hỗ trợ chuẩn. Instrumentation OpenTelemetry có thể tự inject/extract context. Với queue, context có thể được truyền qua message attributes hoặc cơ chế propagation của SDK.

Không đưa access token, email hoặc payload vào trace baggage. Trace context giúp liên kết telemetry; authorization vẫn phải dựa trên credential và policy riêng.

## 9. Truyền context qua queue và event

HTTP request và queue consumer không chạy trong cùng một call stack. Producer cần chuyển những metadata cần thiết vào message attributes hoặc envelope để consumer có thể liên kết log.

Một message envelope có thể có:

~~~json
{
  "event_id": "evt-720",
  "event_type": "OrderCreated",
  "schema_version": 2,
  "correlation_id": "corr-72a1",
  "traceparent": "00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01",
  "occurred_at": "2026-11-17T10:15:30Z",
  "data": {
    "order_ref": "order-42"
  }
}
~~~

Envelope chỉ minh họa metadata và một reference nghiệp vụ. Không nhúng credential hoặc toàn bộ dữ liệu khách hàng vào log. Nếu dùng message attributes riêng, giữ cùng tên field và quy ước qua producer/consumer.

Consumer nên ghi:

- message.id của transport.
- event.id của business event.
- correlation_id.
- trace_id/span_id nếu context hợp lệ.
- retry attempt hoặc receive count nếu source cung cấp.
- event.name, outcome và duration.

Nếu message được gửi lại, message ID có thể giữ nguyên trong redelivery của queue nhưng event ID vẫn là khóa ổn định để nhận diện business event qua nhiều transport message khác nhau.

## 10. Quản lý MDC và thread reuse

MDC của SLF4J/Logback cho phép gắn các field như invocation ID, correlation ID và function name vào nhiều log statement. Nhưng trong môi trường serverless, thread có thể được tái sử dụng cho invocation tiếp theo. Nếu không dọn context, log của invocation mới có thể mang ID của invocation trước.

Ví dụ quản lý context:

~~~java
import org.slf4j.MDC;

public final class InvocationLogging {

public Response handle(Request request, String invocationId) {
    String previousInvocation = MDC.get("faas.invocation_id");
    String previousCorrelation = MDC.get("correlation_id");

    try {
        MDC.put("faas.invocation_id", invocationId);
        MDC.put("correlation_id", request.correlationId());

        return process(request);
    } finally {
        restoreMdc("faas.invocation_id", previousInvocation);
        restoreMdc("correlation_id", previousCorrelation);
    }
}

private static void restoreMdc(String key, String previousValue) {
    if (previousValue == null) {
        MDC.remove(key);
    } else {
        MDC.put(key, previousValue);
    }
}
}
~~~

Lưu và khôi phục giá trị cũ phù hợp khi code được gọi bên trong context đã tồn tại. Nếu framework cung cấp request-scoped context hoặc logging context riêng, ưu tiên cơ chế chính thức của framework.

### Async execution

MDC thường gắn với thread. Khi chuyển công việc sang executor khác, context có thể không tự truyền. Dùng executor có context propagation hoặc capture/restore MDC quanh task. Với OpenTelemetry, dùng Context propagation API hoặc instrumentation tương ứng.

Không copy toàn bộ context không kiểm soát sang thread khác. Chỉ propagate field cần thiết và bảo đảm cleanup trong finally để tránh rò context giữa các task.

## 11. Structured log cho workflow nhiều bước

Workflow có thể chạy lâu hơn tuổi thọ của một function invocation. Nó có thể tạm dừng chờ timer, callback hoặc message rồi resume ở một function khác. Vì vậy, invocation ID không đủ để liên kết toàn bộ workflow.

Dùng các field riêng:

- workflow.id: loại workflow hoặc định danh definition.
- workflow.run_id: một execution cụ thể.
- workflow.step: tên bước hiện tại.
- workflow.state: trạng thái trước/sau nếu phù hợp.
- workflow.attempt: lần thử của step.
- workflow.correlation_id: ID business flow.
- workflow.parent_run_id: run cha nếu có subworkflow.
- workflow.event_id: event làm workflow tiếp tục.

Các event name thường gặp:

| Event | Field bổ sung | Mục đích |
|---|---|---|
| workflow.started | input_ref, definition_version | Bắt đầu execution |
| workflow.step.started | step, attempt | Bắt đầu một bước |
| workflow.step.completed | step, duration_ms, outcome | Bước hoàn tất |
| workflow.step.failed | step, error.code, retryable | Bước thất bại |
| workflow.retry.scheduled | step, attempt, next_attempt_at | Lên lịch retry |
| workflow.waiting | wait_type, deadline | Chờ timer/callback/event |
| workflow.resumed | resume_event_id | Tiếp tục sau khi chờ |
| workflow.compensation.started | compensation_step | Bắt đầu bù trừ |
| workflow.completed | duration_ms, outcome | Workflow kết thúc |
| workflow.failed | failed_step, error.code | Workflow thất bại |

### Ví dụ state transition

~~~json
{
  "timestamp": "2026-11-17T10:16:02.400Z",
  "severity": "INFO",
  "event.name": "workflow.step.completed",
  "workflow.id": "order-fulfillment",
  "workflow.run_id": "run-9c12",
  "workflow.step": "reserve-inventory",
  "workflow.state.from": "RESERVING",
  "workflow.state.to": "INVENTORY_RESERVED",
  "workflow.attempt": 1,
  "correlation_id": "corr-72a1",
  "duration_ms": 126,
  "outcome": "success"
}
~~~

State transition log nên phản ánh kết quả đã được workflow engine hoặc state store commit. Không ghi “completed” trước khi state transition bền vững được xác nhận. Nếu ghi log trước transaction rồi transaction rollback, telemetry sẽ mô tả một trạng thái chưa từng tồn tại.

## 12. Workflow log và workflow execution history

Nhiều workflow engine có execution history hoặc event history riêng. Ví dụ, engine có thể ghi nhận state entered, task scheduled, task succeeded, retry và execution failed. Những dữ liệu đó hữu ích để xem orchestration đã đi qua đâu.

Application log vẫn cần thiết để ghi chi tiết nghiệp vụ mà workflow engine không biết, ví dụ validation rule, dependency operation, error category và business outcome. Hai nguồn nên được liên kết bằng workflow run ID, step name, correlation ID và trace context nếu có.

Không duplicate toàn bộ execution history vào application log. Chọn event nghiệp vụ cần tìm kiếm hoặc alert; dùng workflow engine history để xem diễn tiến điều phối chi tiết.

### Log không phải workflow state

Không dùng dòng log cuối cùng để xác định workflow có hoàn tất hay không. Log có thể bị trễ hoặc thiếu. Dùng execution status hoặc state store làm nguồn chuẩn. Log phục vụ quan sát và điều tra.

## 13. Logging retry, timeout và idempotency

Một message hoặc workflow step có thể được thực hiện nhiều lần. Log cần thể hiện lần thử nào, lỗi nào có thể retry và kết quả cuối cùng ra sao.

Ví dụ:

~~~json
{
  "timestamp": "2026-11-17T10:17:11.200Z",
  "severity": "WARN",
  "event.name": "message.retry.scheduled",
  "service.name": "orders-worker",
  "faas.invocation_id": "inv-b190",
  "message.id": "msg-183",
  "event.id": "evt-720",
  "correlation_id": "corr-72a1",
  "retry.attempt": 3,
  "retry.max_attempts": 5,
  "retry.delay_ms": 4000,
  "error.code": "PAYMENT_PROVIDER_TIMEOUT",
  "outcome": "retry"
}
~~~

Các field quan trọng:

- retry.attempt: số lần thử theo định nghĩa rõ ràng, ví dụ attempt hiện tại bắt đầu từ 1.
- retry.max_attempts: giới hạn được cấu hình.
- error.code: mã lỗi ổn định, không phải exception message.
- retry.delay_ms hoặc next_attempt_at: thời điểm thử lại.
- event.id/idempotency reference: liên kết cùng business operation.
- outcome: retry, success, quarantined hoặc terminal_failure.

Đừng ghi idempotency key nếu nó chứa dữ liệu định danh. Dùng reference đã được chuẩn hóa hoặc pseudonymous key. Log duplicate detected khi consumer nhận lại event đã hoàn tất; phân biệt với business event mới có cùng aggregate.

## 14. Batch logging: một log cho batch, một log cho record lỗi

Batch consumer có thể xử lý hàng nghìn record. Ghi INFO cho mọi record thành công sẽ tạo log volume lớn và làm tăng chi phí. Một chiến lược thực tế:

- Một log INFO khi batch bắt đầu, gồm batch size và source.
- Một log INFO khi batch hoàn tất, gồm success count, failure count và duration.
- Một log WARN/ERROR cho từng record thất bại cần điều tra, có message reference, event type và error code.
- Một log cho duplicate detection nếu cần đo tỷ lệ.
- Metric riêng cho số record thành công/thất bại, không dùng log làm counter chính.

Ví dụ batch summary:

~~~json
{
  "event.name": "batch.processing.completed",
  "faas.name": "ProcessOrders",
  "faas.invocation_id": "inv-8f21",
  "batch.size": 100,
  "batch.succeeded": 97,
  "batch.failed": 3,
  "batch.duplicate": 2,
  "duration_ms": 1840,
  "outcome": "partial_failure"
}
~~~

Record failure:

~~~json
{
  "event.name": "message.processing.failed",
  "message.id": "msg-183",
  "event.id": "evt-720",
  "error.code": "INVENTORY_TIMEOUT",
  "retry.attempt": 2,
  "outcome": "retry"
}
~~~

Không ghi message body. Với partial batch response, invocation có thể được xem là thành công dù một số record được yêu cầu retry; custom record-level metrics là cần thiết.

## 15. Cold start và startup logging

Cold start là thời gian khởi tạo runtime, class loading, dependency injection, SDK client và application context trước khi xử lý invocation đầu tiên của execution environment. Nếu chỉ log invocation duration, có thể khó phân biệt startup latency với thời gian xử lý nghiệp vụ.

Có thể ghi riêng các mốc:

- runtime.initialization.started
- application.bootstrap.completed
- dependency.client.initialized
- function.invocation.started
- function.invocation.finished

Nếu nền tảng cung cấp metric hoặc log init/cold start, dùng nguồn đó. Không tự suy ra cold start chỉ từ duration cao vì dependency chậm hoặc network cũng có thể tạo latency tương tự. Nếu dùng cờ static để nhận biết lần gọi đầu tiên trong environment, ghi rõ đây chỉ là heuristic theo lifecycle của runtime và phải được kiểm chứng với platform.

Ví dụ startup event:

~~~json
{
  "event.name": "application.bootstrap.completed",
  "service.name": "orders-function",
  "service.version": "2.4.1",
  "duration_ms": 420,
  "outcome": "success"
}
~~~

Không log mọi chi tiết khởi tạo client chứa endpoint/credential. Startup log nên giúp xác định phần khởi tạo chậm và phiên bản ứng dụng.

## 16. Correlate log với OpenTelemetry trace và metrics

Structured log có thể chứa trace_id và span_id để người vận hành mở trace tương ứng. Trace hiển thị quan hệ giữa service; log cung cấp chi tiết event; metrics cho thấy xu hướng và mức độ ảnh hưởng.

Một flow điển hình:

~~~mermaid
flowchart LR
    A[HTTP Gateway] --> B[Java Function]
    B --> C[Queue]
    C --> D[Worker Function]
    D --> E[Database]
    D --> F[External API]
    B -. log + trace IDs .-> L[Log platform]
    D -. log + trace IDs .-> L
    B -. spans .-> T[Trace backend]
    D -. spans .-> T
    B -. metrics .-> M[Metrics backend]
    D -. metrics .-> M
~~~

Khi điều tra latency, dùng metric để tìm thời điểm p95 tăng, trace để tìm span chậm và log để đọc error code hoặc trạng thái workflow. Giữ trace ID/span ID trong log nếu instrumentation cung cấp context hợp lệ.

Không tạo trace ID bằng tay nếu OpenTelemetry SDK đã quản lý context. Không đặt user ID hoặc order ID vào metric labels chỉ để tìm log; dùng trace/log search hoặc field được bảo vệ.

## 17. Schema evolution và tính tương thích

Schema log thay đổi theo thời gian khi team thêm field, đổi tên hoặc đổi kiểu. Nếu dashboard phụ thuộc field cũ, một thay đổi nhỏ có thể làm query hỏng.

Nguyên tắc:

- Dùng schema_version hoặc quy ước version cho event quan trọng.
- Không đổi kiểu field âm thầm, ví dụ duration_ms từ number thành string.
- Ưu tiên thêm field optional thay vì đổi tên field hiện có.
- Giữ event.name ổn định và không nhúng giá trị động vào tên.
- Document ý nghĩa của retry.attempt, duration_ms và outcome.
- Có test kiểm tra schema output.
- Khi deprecate field, duy trì giai đoạn tương thích để dashboard và consumer cập nhật.

Ví dụ duration luôn là số nguyên mili giây; timestamp luôn UTC ISO-8601; severity dùng một tập giá trị cố định. Những quy ước đơn giản này giúp query và alert bền vững.

## 18. Log pipeline trong serverless

Trong môi trường serverless, ứng dụng thường ghi ra stdout/stderr hoặc logging API của provider. Runtime/agent thu thập log rồi gửi đến log service. Từ đó, log có thể được filter, enrich, index, archive hoặc chuyển sang SIEM.

~~~mermaid
flowchart TD
    A[Java function / workflow step] --> B[Structured JSON]
    B --> C[Runtime log capture]
    C --> D[Cloud log service]
    D --> E[Parse / enrich / redact]
    E --> F[Search and dashboard]
    E --> G[Alerting]
    E --> H[Archive / SIEM]
~~~

Các điểm cần kiểm tra:

- Mỗi invocation có thể tạo nhiều log record; tránh log quá nhiều trong hot path.
- Log delivery và ingestion có thể bất đồng bộ; không giả định record xuất hiện ngay lập tức.
- Runtime có thể giới hạn kích thước event hoặc truncate log dài.
- Log aggregator có thể parse JSON khác nhau tùy format và multiline handling.
- Structured output nên là một JSON object trên mỗi dòng.
- Sampling hoặc filter cần giữ lại lỗi quan trọng và workflow terminal events.
- Có thể cần enrich service/version/region từ runtime metadata thay vì tự hardcode.

Không chờ log export hoàn tất trước khi trả response HTTP nếu điều đó làm tăng latency. Logging path nên không chặn nghiệp vụ trong điều kiện bình thường, nhưng cần hiểu chính sách buffer/flush của runtime để tránh mất log khi process kết thúc đột ngột.

## 19. Sampling, volume và chi phí

Serverless tính phí theo invocation, duration và các dịch vụ quan sát có thể tính theo ingestion, retention, query hoặc trace volume. Log quá chi tiết vừa làm tăng chi phí vừa khiến tín hiệu quan trọng khó tìm.

Biện pháp kiểm soát:

- INFO cho các mốc có giá trị vận hành.
- DEBUG chỉ bật tạm thời hoặc theo scope nhỏ.
- Batch summary thay cho log thành công từng record.
- Không log polling heartbeat quá thường xuyên nếu không cần.
- Giới hạn kích thước field và exception detail.
- Dùng sampling có chủ đích cho sự kiện lặp lại tần suất cao.
- Giữ lại toàn bộ terminal failure, security-relevant event và workflow state transition quan trọng theo policy.
- Theo dõi bytes ingested, retention và query cost.

Sampling log không giống sampling trace. Nếu drop ngẫu nhiên mọi event, có thể mất chuỗi workflow cần điều tra. Nên ưu tiên giữ event bắt đầu/kết thúc, failure, retry và state transition quan trọng; giảm chi tiết lặp lại ở các event thành công khối lượng lớn.

## 20. Bảo đảm log không cản trở function

Logging là một dependency vận hành. Nếu log appender đồng bộ chờ network hoặc backend chậm, function có thể tăng latency hoặc timeout. Nếu async appender dùng buffer nhỏ, log có thể bị drop khi burst; nếu buffer quá lớn, memory pressure tăng.

Cần đánh giá:

- Console logging và platform collector có phải đường được khuyến nghị không?
- Encoder có tạo JSON đồng bộ với chi phí đáng kể không?
- Async appender có queue limit và drop policy nào?
- Khi buffer đầy, log bị drop hay thread bị block?
- Process shutdown có flush buffer trong giới hạn runtime không?
- Log exception lớn có làm tăng memory/serialization time không?

Không ghi log trong vòng lặp nóng với payload lớn. Không dùng network call đồng bộ đến log service trong mỗi invocation trừ khi kiến trúc và latency budget cho phép.

## 21. Kiểm thử structured log

Unit test nên kiểm tra event name và field quan trọng; integration test nên kiểm tra JSON output thực tế của logging backend và runtime collector.

Ví dụ test ở mức logger/appender:

~~~java
@Test
void writesStructuredInvocationFields() {
    handler.handle(testRequest, "inv-test-1", "corr-test-1");

    String output = testAppender.lastJsonEvent();

    assertJsonField(output, "event.name", "function.invocation.started");
    assertJsonField(output, "faas.invocation_id", "inv-test-1");
    assertJsonField(output, "correlation_id", "corr-test-1");
}
~~~

Đây là pseudocode cho test appender của project. Nên kiểm tra:

- Output là JSON hợp lệ.
- Mỗi event là một dòng riêng.
- Timestamp UTC và severity đúng schema.
- Invocation ID và correlation ID không bị lẫn giữa hai request.
- MDC được cleanup sau success và exception.
- Async task nhận đúng context.
- Workflow run ID và step name được ghi đúng.
- Retry attempt tăng đúng.
- Batch summary khớp số record thực tế.
- Error log có error code/type và không lộ dữ liệu nhạy cảm.
- Schema version và kiểu field không thay đổi ngoài dự kiến.

### Kiểm thử thread/context reuse

Chạy hai invocation liên tiếp trên cùng thread trong test hoặc môi trường runtime phù hợp. Invocation thứ hai không được chứa correlation ID, workflow ID hoặc request ID của invocation đầu. Test thêm cả nhánh exception để xác nhận cleanup luôn chạy.

### Kiểm thử workflow

Chạy workflow qua nhiều step, retry và wait/resume. Xác nhận mọi event có cùng workflow.run_id và correlation_id; invocation ID thay đổi đúng theo lần gọi function; trace ID/span ID theo đúng propagation strategy; state transition log phản ánh trạng thái đã commit.

## 22. Dashboard và alert từ structured fields

Một dashboard có thể nhóm theo:

- service.name và service.version.
- faas.name và cloud.region.
- event.name và severity.
- outcome và error.code.
- workflow.id, workflow.step và workflow.run_id.
- retry.attempt và message source.
- duration_ms và dependency name.

Alert nên dựa trên điều kiện có thể hành động:

| Tín hiệu | Ví dụ điều kiện | Hành động |
|---|---|---|
| Function failure rate | Tỷ lệ invocation failed vượt ngưỡng | Kiểm tra version, dependency và runtime |
| Workflow terminal failure | Có workflow.failed mới | Mở execution history và trace |
| Retry tăng | retry rate tăng liên tục | Kiểm tra downstream và poison message |
| Step latency | p95 của một workflow step tăng | Kiểm tra dependency của step |
| Queue backlog | Oldest message age vượt SLA | Kiểm tra consumer capacity |
| Cold start/init | Init duration tăng sau deploy | Kiểm tra artifact và initialization |
| Log ingestion drop | Collector báo drop hoặc quota | Giảm volume hoặc tăng capacity |

Alert không nên gửi toàn bộ log message hoặc payload vào chat/email. Gửi event name, error code, service, Region, timestamp và link đến log/trace có kiểm soát.

## 23. Những lỗi thiết kế thường gặp

| Lỗi | Hậu quả | Cách khắc phục |
|---|---|---|
| Chỉ log text tự do | Khó filter và tổng hợp | Dùng schema JSON ổn định |
| Dùng invocation ID cho cả workflow | Không nối được các lần retry/resume | Tách invocation, correlation và workflow run ID |
| Nhúng order ID vào event name | Tạo event type động và query khó | Đưa ID vào field riêng |
| Ghi toàn bộ request/event | Log volume lớn và tăng rủi ro dữ liệu | Allowlist metadata |
| Ghi INFO cho mọi record | Tăng chi phí và noise | Batch summary và record-level failure |
| Không log retry attempt | Khó phân biệt duplicate và operation mới | Ghi attempt, event ID và message reference |
| Không dọn MDC | Context cũ rò sang invocation khác | Restore/clear trong finally |
| Giả định MDC tự truyền qua executor | Log async thiếu hoặc sai correlation | Dùng context propagation |
| Giữ một trace span suốt workflow nhiều ngày | Span dài, khó quản lý và phụ thuộc runtime | Span theo step, liên kết bằng workflow run ID |
| Log completed trước khi commit | Telemetry báo trạng thái chưa bền vững | Log sau khi transition được xác nhận |
| Dùng log làm nguồn truth | Sai trạng thái khi log trễ hoặc bị drop | Database/workflow engine là nguồn chuẩn |
| Không version schema | Dashboard hỏng khi field đổi | Schema version và compatibility test |
| Log quá nhiều trong hot path | Tăng latency và chi phí | Giảm volume, sampling có chủ đích |
| Chỉ theo dõi invocation Errors | Bỏ sót partial batch record failures | Custom record-level metrics |

## 24. Quy trình thiết kế structured logging

Khi thiết kế log cho một Java function hoặc workflow:

1. **Xác định mục tiêu vận hành:** cần điều tra request, đo latency, theo dõi retry hay state transition?
2. **Chọn schema chung:** timestamp, severity, service, environment, Region, event name và version.
3. **Định nghĩa ID:** invocation ID, correlation ID, trace ID, workflow run ID, event/message ID.
4. **Đặt event name ổn định:** dùng tên event mô tả hành động/kết quả, giữ ID ở field riêng.
5. **Chọn level:** INFO cho mốc quan trọng, WARN cho retry/fallback, ERROR cho failure.
6. **Thiết lập JSON encoder:** xác nhận key-value thực sự được xuất thành JSON.
7. **Propagate context:** qua HTTP, queue, event và workflow resume.
8. **Quản lý MDC:** cleanup/restore và truyền context qua async executor.
9. **Thiết kế workflow events:** started, step transition, waiting, resumed, retry, completed/failed.
10. **Giới hạn volume:** batch summary, sampling và retention theo mục đích.
11. **Kiểm thử schema:** JSON, field type, context isolation, retry và workflow correlation.
12. **Thiết lập dashboard/alert:** dùng field ổn định và tín hiệu có thể hành động.

## 25. Checklist production

- **Schema:** có timestamp UTC, severity, service, version, environment, Region và event name.
- **Naming:** event name ổn định; ID động nằm trong field riêng.
- **Invocation:** mỗi log event liên quan invocation có invocation ID chính xác.
- **Correlation:** business flow giữ correlation ID xuyên function, queue và workflow.
- **Tracing:** trace ID/span ID được propagate theo W3C/OpenTelemetry hoặc cơ chế provider.
- **Workflow:** có workflow run ID, step, attempt và state transition.
- **Retry:** có retry attempt, error code, outcome và message/event reference.
- **Batch:** có batch summary và record-level failure metric.
- **Java:** SLF4J/backend/JSON encoder tương thích; fluent key-value thực sự thành JSON fields.
- **MDC:** context được cleanup/restore sau success và failure; async propagation được kiểm tra.
- **Cold start:** startup/init telemetry tách khỏi business duration.
- **Privacy:** không log token, secret, raw payload hoặc PII ngoài policy.
- **Delivery:** hiểu buffering, flush, truncation và log collector behavior.
- **Cost:** volume, sampling, retention và ingestion được giám sát.
- **Testing:** có schema test, context reuse test, async test và workflow resume test.
- **Operations:** dashboard và alert dùng field ổn định, không gửi payload vào notification.

## 26. Kết luận

Structured logging giúp Java function và workflow serverless tạo ra dữ liệu vận hành có thể tìm kiếm, liên kết và tổng hợp. Một schema ổn định cần phân biệt invocation ID, correlation ID, trace ID, message/event ID và workflow run ID; event name mô tả sự kiện, còn ID động nằm trong field riêng.

Trong function, hãy ghi các mốc invocation, nghiệp vụ và dependency với duration/outcome phù hợp. Trong workflow dài hạn, ghi state transition theo workflow run và step; không phụ thuộc invocation ID để liên kết các lần resume. Truyền context qua queue/event, quản lý MDC khi thread được tái sử dụng và dùng OpenTelemetry để liên kết log với trace.

Log phải hỗ trợ quan sát chứ không thay thế trạng thái nghiệp vụ. Kết hợp structured logs với metrics, traces, execution history và audit store; kiểm thử schema, context propagation, retry và workflow resume trước production. Khi field ổn định, volume được kiểm soát và mỗi event có đủ correlation context, nhóm có thể tìm nguyên nhân cold start, lỗi dependency, duplicate và workflow failure mà vẫn giữ log dễ đọc và chi phí hợp lý.
