# Operation context trong Java Logging

## 1. Operation context là gì?

**Operation context** (ngữ cảnh thao tác) là tập thông tin mô tả **thao tác nghiệp vụ hoặc kỹ thuật nào đang được thực hiện** khi một log event được phát ra. Khi đọc một dòng log, ta không chỉ muốn biết “đã có INFO/ERROR” mà còn muốn trả lời:

- Đang thực hiện thao tác gì: tạo đơn hàng, thanh toán, đồng bộ dữ liệu, xử lý thông điệp hay chạy batch job?
- Đây là lần thực hiện nào của thao tác đó?
- Thao tác này có phải bước con của một thao tác lớn hơn không?
- Nó thuộc request/job/workflow nào, và liên quan đến đối tượng nghiệp vụ nào?
- Bước nào đã bắt đầu, hoàn tất, thất bại hoặc được thử lại?
- Mất bao lâu, kết quả ra sao và có thể nối với trace/metrics tương ứng không?

Ví dụ log **chưa có operation context**:

```text
INFO  | started
INFO  | reserved stock
WARN  | payment retry
INFO  | completed
```

Nếu nhiều request chạy đồng thời, ta khó xác định bốn dòng này thuộc cùng một checkout hay bốn công việc khác nhau.

Ví dụ log **có operation context**:

```json
{"level":"INFO","operation":"checkout","operationId":"op-17","requestId":"req-42","event":"operation_started"}
{"level":"INFO","operation":"reserve_inventory","operationId":"op-18","parentOperationId":"op-17","requestId":"req-42","event":"stock_reserved"}
{"level":"WARN","operation":"checkout","operationId":"op-17","requestId":"req-42","event":"payment_retry","attempt":2}
{"level":"INFO","operation":"checkout","operationId":"op-17","requestId":"req-42","event":"operation_finished","outcome":"SUCCESS","durationMs":30}
```

Các dòng JSON này là **mẫu dữ liệu**, không phải đầu ra được JUL/Logback tự tạo. Chúng thể hiện ý tưởng: cùng `operationId` giúp liên kết các event của một thao tác; `parentOperationId` giúp biết bước reserve thuộc checkout; `requestId` liên kết với request ban đầu.

**Operation context không phải một class chuẩn duy nhất của Java.** Đó là mô hình dữ liệu và quy ước sử dụng của ứng dụng. Trong mã Java có thể biểu diễn bằng record bất biến, tham số truyền tường minh, SLF4J MDC, Log4j 2 Thread Context hoặc telemetry context, tùy kiến trúc.

## 2. Phân biệt các loại context thường bị nhầm

Một ứng dụng Java có thể có nhiều lớp định danh:

| Khái niệm | Câu hỏi cần trả lời | Ví dụ |
|---|---|---|
| **Operation name** | Chương trình đang làm loại việc gì? | `checkout`, `reserve_inventory` |
| **Operation ID** | Đây là lần thực thi cụ thể nào của operation? | `op-17` |
| **Parent operation ID** | Operation được sinh từ thao tác cha nào? | `op-17` là cha của `op-18` |
| **Request ID** | Dòng xử lý xuất phát từ request HTTP nào? | `req-42` |
| **Job/workflow ID** | Tác vụ nền nào đang được thực hiện? | `job-104` |
| **Business ID** | Đối tượng nghiệp vụ liên quan là gì? | `orderId=ORD-7` |
| **Trace ID** | Những span nào thuộc cùng một distributed trace? | Giá trị theo quy ước tracing |
| **Span ID** | Đây là span cụ thể nào trong trace? | Giá trị theo tracing SDK |
| **Attempt** | Đây là lần thử thứ mấy? | `attempt=2` |
| **Event name** | Điều gì vừa xảy ra trong operation? | `payment_retry` |
| **Outcome** | Thao tác thành công, thất bại hay hủy? | `SUCCESS`, `FAILED`, `CANCELLED` |

**Không dùng các ID này thay thế nhau mà không có thiết kế.**

- Một HTTP request có thể kích hoạt **nhiều operation**.
- Một operation có thể chạy **không có HTTP request**: cron job, message consumer, batch hoặc scheduled task.
- Một business order có thể trải qua **nhiều operation khác nhau** trong nhiều giờ.
- Một operation có thể tiếp tục qua nhiều service và nhiều message; `requestId` ban đầu có thể không còn.
- `traceId` là ID của trace; `operationId` là ID của một thao tác theo mô hình ứng dụng. Chúng có thể liên kết nhưng **không mặc nhiên giống nhau**.
- Một operation lồng nhau có thể có ID riêng và `parentOperationId` trỏ về thao tác cha.

Một schema tốt nên mô tả **ý nghĩa và vòng đời của từng ID**, không chỉ thống nhất tên khóa.

## 3. Operation context phục vụ điều gì?

### 3.1. Liên kết nhiều dòng log của một lần thực thi

Giả sử checkout có năm bước: kiểm tra dữ liệu, giữ hàng, xác thực thanh toán, lưu đơn, gửi xác nhận. Nếu log tất cả bằng `operationId=op-17` hoặc có quan hệ parent rõ, người vận hành có thể dựng lại quá trình mà không phải tìm message dựa trên thứ tự dòng.

### 3.2. Xác định ranh giới thao tác

Các event có tên rõ:

```text
operation_started
inventory_reserved
payment_authorized
order_persisted
operation_finished
```

cho thấy tiến trình ở đâu, bước nào đã hoàn thành. Nhưng **không nhất thiết mỗi bước phải log INFO** ở mọi hệ thống: tải cao có thể cần log DEBUG cho bước bình thường, INFO cho trạng thái quan trọng và ERROR tại boundary chịu trách nhiệm khi tác vụ thất bại.

### 3.3. Gắn thời lượng và kết quả

Một event kết thúc có thể chứa `outcome=SUCCESS`, `durationMs=30` và `operationId=op-17`. Thông tin này giúp điều tra tác vụ chậm, nhưng log event **không tự thay thế metric latency**. Nếu cần p95/p99 chính xác, hãy dùng histogram/metrics đúng đơn vị thao tác, vì log có thể bị lọc, lấy mẫu hoặc mất khi collector lỗi.

### 3.4. Phân tích lỗi trong hệ bất đồng bộ

Khi xử lý đi từ request thread sang `ExecutorService` hoặc message queue, context giúp biết các event ở worker vẫn thuộc thao tác nào. Tuy nhiên, **không có cách truyền context tự động dùng chung cho mọi API và backend**; cần cơ chế rõ ràng.

## 4. Thiết kế các field cho operation context

Một mẫu JSON log:

```json
{
  "timestamp": "2026-11-09T08:15:03.125Z",
  "level": "INFO",
  "service": "orders-api",
  "logger": "com.example.orders.CheckoutService",
  "event": "payment_authorized",
  "operation": {
    "name": "checkout",
    "id": "op-17",
    "parentId": null
  },
  "requestId": "req-42",
  "orderId": "ORD-7",
  "outcome": "SUCCESS",
  "durationMs": 18
}
```

Đây là **schema minh họa**, không phải schema bắt buộc. Hệ thống thật có thể dùng `operation.name`, `operation_id`, `operationId` hoặc cấu trúc object lồng, nhưng cần nhất quán và tương thích với collector.

Các field nên tuân theo quy tắc:

1. **Tên operation ổn định, ít giá trị khác nhau**: `checkout` thay vì `checkout_order_ORD-7`.
2. **Operation ID độc lập với message**: một giá trị rõ ràng, không cần regex trích từ text.
3. **Định danh cha có thể null** cho root operation; không tự bịa parent.
4. **Event name mô tả việc đã xảy ra**, ví dụ `payment_authorized`, không chỉ `"done"`.
5. **Outcome có danh mục thống nhất**: `SUCCESS`, `FAILED`, `CANCELLED`, `TIMEOUT`...; cần định nghĩa ý nghĩa từng giá trị.
6. **Đơn vị thời lượng tường minh** như `durationMs`; nên để kiểu number.
7. **Không chèn dynamic ID vào tên trường**; dùng field `operationId` với value thay vì key `op_17`.
8. **Không nhồi PII/secret** vào context chỉ vì nó tồn tại suốt operation.

Nếu một service có hoạt động qua nhiều API khác nhau, nên mô tả schema bằng tài liệu và test; không dựa vào quy ước truyền miệng.

## 5. Operation lifecycle: bắt đầu, bước trung gian, hoàn tất

Một operation thường có vòng đời:

```text
operation_started
       |
       v
  step_started?  ---> step_failed? ---> retry?
       |
       v
  step_completed
       |
       v
 operation_finished  [SUCCESS]
       |
       +---------- hoặc operation_failed [FAILED]
       +---------- hoặc operation_cancelled [CANCELLED]
```

Sơ đồ chỉ mang tính mô hình. Không phải mọi operation đều có cùng số bước và không cần phát một dòng cho từng transition trong một hệ thống lưu lượng rất cao.

### 5.1. Ghi sự kiện ở ranh giới rõ ràng

Khi bắt đầu:

```json
{"operation":"checkout","operationId":"op-17","event":"operation_started","outcome":"STARTED"}
```

Khi có một bước hoàn tất:

```json
{"operation":"reserve_inventory","operationId":"op-18","parentOperationId":"op-17","event":"inventory_reserved","outcome":"SUCCESS","durationMs":12}
```

Khi thao tác gốc kết thúc:

```json
{"operation":"checkout","operationId":"op-17","event":"operation_finished","outcome":"SUCCESS","durationMs":30}
```

**Không nên ghi `operation_finished SUCCESS` trong `finally` vô điều kiện.** Nếu có exception, cancellation hoặc timeout, outcome phải phản ánh đúng kết quả. Có thể ghi một event hoàn tất với `outcome=FAILED` và thông tin exception, hoặc dùng event `operation_failed` theo schema đã chọn.

### 5.2. Tránh log trùng ở nhiều tầng

Ví dụ lỗi database được log ERROR tại repository, service và controller, cùng `operationId`. Nếu ba tầng ghi cùng một exception, dashboard có thể đếm ba ERROR dù thực tế chỉ có một thao tác thất bại.

Nên phân định boundary chịu trách nhiệm:

- Các tầng thấp trả lỗi/giữ cause, thêm thông tin ngữ cảnh khi phù hợp.
- Tầng quyết định kết quả operation ghi log lỗi cuối cùng một lần, trừ khi có lý do theo dõi các bước retry riêng.
- Nếu ghi các lần thử, dùng `attempt`, `step` và event name phân biệt để người đọc không nhầm với lỗi cuối cùng.

## 6. Cách giữ operation context trong Java

Các chiến lược phổ biến:

| Chiến lược | Ưu điểm | Giới hạn |
|---|---|---|
| **Truyền tham số tường minh** | Dễ nhìn luồng dữ liệu, dễ test, không phụ thuộc thread | Thêm tham số qua nhiều lớp |
| **Immutable record/object** | Snapshot rõ ràng, tránh biến đổi ngầm | Vẫn cần phương án truyền tới chỗ ghi log |
| **`ThreadLocal` có scope** | Tiện cho code đồng bộ trên cùng thread | Không tự truyền sang thread pool hoặc task khác |
| **SLF4J MDC** | Tích hợp với nhiều pattern/encoder | Phụ thuộc backend/provider và cách propagate |
| **Log4j 2 Thread Context** | Tích hợp logging context của Log4j 2 | API và semantics riêng |
| **Tracing/telemetry context** | Liên kết trace/span theo instrumentation | Không tự chứa mọi business operation field |

**Lựa chọn tùy mục đích.** Với business logic quan trọng, context tường minh/immutable giúp giảm phụ thuộc vào thread; với logging nhiều tầng, MDC có thể là lớp tiện ích để hiển thị context mà không truyền thủ công vào từng lời gọi logger.

### 6.1. Vì sao immutable context thường an toàn hơn?

Nếu một map context mutable được chia sẻ cho các request hoặc giữa producer và async worker, một thread có thể sửa `orderId` sau khi event đã được enqueue. Backend có thể đọc giá trị khác với lúc event phát sinh.

Một Java `record` hoặc object immutable được tạo tại ranh giới operation giúp cố định các ID. Nhưng khi thêm field chứa object mutable (danh sách, map, entity), cần snapshot/copy phù hợp; bản thân `record` không biến mọi nested object thành immutable.

### 6.2. Ranh giới scope

Một scope phải có **điểm mở và đóng rõ ràng**:

```text
Nhận request / bắt đầu job
    |
    +-- Tạo operation context
    +-- Mở scope
    |       |
    |       +-- Ghi log các bước
    |       +-- Có thể mở scope con
    |       +-- Chuyển context tường minh tới worker
    |
    +-- Đóng scope trong finally/try-with-resources
    +-- Request thread trở về trạng thái trước đó
```

Nếu không đóng scope, thread pool có thể tái sử dụng thread chứa `operationId` của request cũ: log của request sau bị gắn nhầm ID. Đây là vấn đề **correctness và privacy**, không chỉ là log khó đọc.

## 7. Ví dụ Java 17+ độc lập: operation context có scope và async propagation

Ví dụ sau chỉ dùng **JDK 17**, không cần Maven hoặc thư viện ngoài. Nó minh họa:

1. Mô hình `OperationContext` bất biến dưới dạng `record`.
2. Scope dùng `ThreadLocal`, tự **khôi phục context trước** bằng `try-with-resources`, kể cả khi có thao tác lồng.
3. Một bước con có `operationId` riêng và `parentOperationId` trỏ về thao tác cha.
4. Truyền **snapshot context tường minh** sang `ExecutorService`.
5. Gắn snapshot vào từng `LogRecord` trước khi formatter xuất log, tránh formatter đọc nhầm context của thread ghi.
6. Output ổn định không có timestamp động; thời lượng được cố định **để minh họa**, không phải đo thực tế.

Với hệ thống thật, SLF4J MDC hoặc tracing SDK có thể được dùng thay cho custom JUL event; ví dụ tự viết này nhằm giải thích nguyên tắc.

### 7.1. Tạo tệp `OperationContextDemo.java`

```java
import java.util.Objects;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.logging.ConsoleHandler;
import java.util.logging.Formatter;
import java.util.logging.Level;
import java.util.logging.LogRecord;
import java.util.logging.Logger;

public final class OperationContextDemo {
    private static final Logger LOG =
            Logger.getLogger("demo.OrderService");

    private static final ThreadLocal<OperationContext> CURRENT =
            new ThreadLocal<>();

    private record OperationContext(
            String name,
            String operationId,
            String parentOperationId,
            String requestId,
            String orderId) {
    }

    private static final class Scope implements AutoCloseable {
        private final OperationContext previous;
        private boolean closed;

        private Scope(OperationContext next) {
            previous = CURRENT.get();
            CURRENT.set(Objects.requireNonNull(next));
        }

        static Scope open(OperationContext context) {
            return new Scope(context);
        }

        @Override
        public void close() {
            if (closed) {
                return;
            }
            if (previous == null) {
                CURRENT.remove();
            } else {
                CURRENT.set(previous);
            }
            closed = true;
        }
    }

    private static final class EventRecord extends LogRecord {
        private static final long serialVersionUID = 1L;

        private final OperationContext snapshot;
        private final String outcome;
        private final long durationMs;

        EventRecord(
                Level level,
                String event,
                OperationContext snapshot,
                String outcome,
                long durationMs) {
            super(level, event);
            this.snapshot = snapshot;
            this.outcome = outcome;
            this.durationMs = durationMs;
        }
    }

    private static final class EventFormatter extends Formatter {
        @Override
        public String format(LogRecord record) {
            if (!(record instanceof EventRecord event)) {
                return record.getLevel().getName()
                        + " event=" + formatMessage(record) + "\n";
            }

            OperationContext context = event.snapshot;
            return record.getLevel().getName()
                    + " operation="
                    + (context == null ? "none" : context.name())
                    + " operationId="
                    + (context == null ? "-" : context.operationId())
                    + " parentOperationId="
                    + (context == null ? "-"
                                       : context.parentOperationId())
                    + " requestId="
                    + (context == null ? "-" : context.requestId())
                    + " orderId="
                    + (context == null ? "-" : context.orderId())
                    + " event=" + formatMessage(record)
                    + " outcome=" + event.outcome
                    + " durationMs=" + event.durationMs
                    + "\n";
        }
    }

    private static void emit(
            String eventName, String outcome, long durationMs) {
        EventRecord event = new EventRecord(
                Level.INFO,
                eventName,
                CURRENT.get(),
                outcome,
                durationMs);
        event.setLoggerName(LOG.getName());
        LOG.log(event);
    }

    public static void main(String[] args) throws Exception {
        LOG.setUseParentHandlers(false);
        LOG.setLevel(Level.INFO);

        ConsoleHandler handler = new ConsoleHandler();
        handler.setLevel(Level.ALL);
        handler.setFormatter(new EventFormatter());
        LOG.addHandler(handler);

        ExecutorService executor =
                Executors.newSingleThreadExecutor();

        try {
            OperationContext checkout = new OperationContext(
                    "checkout", "op-17", "-", "req-42", "ORD-7");

            try (Scope rootScope = Scope.open(checkout)) {
                emit("operation_started", "STARTED", 0);

                OperationContext inventory = new OperationContext(
                        "reserve_inventory",
                        "op-18",
                        checkout.operationId(),
                        checkout.requestId(),
                        checkout.orderId());

                try (Scope childScope = Scope.open(inventory)) {
                    emit("stock_reserved", "SUCCESS", 12);
                }

                // Child scope đã đóng: CURRENT được khôi phục về checkout.
                OperationContext snapshot = CURRENT.get();

                Future<?> paymentTask = executor.submit(() -> {
                    // Thread pool không tự nhận ThreadLocal của caller.
                    try (Scope workerScope = Scope.open(snapshot)) {
                        emit("payment_authorized", "SUCCESS", 18);
                    }
                });
                paymentTask.get();

                emit("operation_finished", "SUCCESS", 30);
            }

            // Root scope đã đóng: không còn operation context.
            emit("after_scope", "NONE", 0);
        } finally {
            executor.shutdown();
            LOG.removeHandler(handler);
            handler.flush();
            handler.close();
        }
    }
}
```

### 7.2. Biên dịch và chạy

Từ thư mục chứa `OperationContextDemo.java`, sử dụng JDK 17 trở lên:

```bash
javac -encoding UTF-8 OperationContextDemo.java
java OperationContextDemo
```

**Nội dung stderr do JUL `ConsoleHandler` xuất:**

```text
INFO operation=checkout operationId=op-17 parentOperationId=- requestId=req-42 orderId=ORD-7 event=operation_started outcome=STARTED durationMs=0
INFO operation=reserve_inventory operationId=op-18 parentOperationId=op-17 requestId=req-42 orderId=ORD-7 event=stock_reserved outcome=SUCCESS durationMs=12
INFO operation=checkout operationId=op-17 parentOperationId=- requestId=req-42 orderId=ORD-7 event=payment_authorized outcome=SUCCESS durationMs=18
INFO operation=checkout operationId=op-17 parentOperationId=- requestId=req-42 orderId=ORD-7 event=operation_finished outcome=SUCCESS durationMs=30
INFO operation=none operationId=- parentOperationId=- requestId=- orderId=- event=after_scope outcome=NONE durationMs=0
```

Không có output stdout do chính chương trình tạo. Các số `0`, `12`, `18`, `30` là **dữ liệu cố định phục vụ bài học**, không phải thời gian đo trên máy. Formatter cố ý bỏ timestamp, tên thread và chi tiết hệ thống để output có thể kiểm chứng chính xác; production cần bổ sung metadata chuẩn và escaping.

### 7.3. Vì sao ví dụ cho kết quả này?

- `Scope.open(checkout)` gắn context root `op-17` vào thread main.
- Scope con `reserve_inventory` gắn `op-18` có parent `op-17`. Khi scope con đóng, `Scope.close()` khôi phục checkout, **không xóa context root**.
- Trước khi submit task, ứng dụng giữ `snapshot = CURRENT.get()`. Worker thread mở **scope riêng** với snapshot đó, rồi dọn sau khi phát event.
- `paymentTask.get()` đợi task hoàn tất trước khi phát `operation_finished`; vì vậy năm dòng trong demo có thứ tự dự kiến. Với nhiều task chạy song song, **không có một thứ tự toàn cục tương đương**.
- `emit(...)` tạo `EventRecord` chứa **snapshot bất biến** tại thời điểm phát. Formatter đọc snapshot của record, không truy cập `ThreadLocal` của worker ghi log.
- Sau khi root scope đóng, `CURRENT.get()` là null; event `after_scope` xuất `operation=none` và các ID bằng `-`.
- `LOG.setUseParentHandlers(false)` tránh nhân đôi log qua handler cha; `ConsoleHandler` mặc định ghi stderr.
- `ExecutorService.shutdown()` yêu cầu kết thúc worker pool của demo. Nó không phải điều kiện bảo đảm log được vận chuyển tới collector production.
- `Formatter` trong bài chỉ trình bày ID tĩnh an toàn; với chuỗi do người dùng nhập, phải escaping hoặc dùng structured encoder để tránh log injection.

### 7.4. Vì sao không dùng context mutable toàn cục?

Giả sử một static map được cập nhật `operationId` cho mỗi request. Khi hai request chạy đồng thời, request A có thể ghi log bằng ID của B. `ThreadLocal` tránh chia sẻ như vậy khi xử lý đồng bộ trong cùng thread; immutable record tránh sửa nội dung snapshot.

Tuy nhiên, `ThreadLocal` không tự truyền sang worker/task và không thay thế việc gắn context tường minh ở ranh giới message queue. Ví dụ vừa minh họa cách **capture trước, install trong worker, restore trong finally**.

### 7.5. Đây là ví dụ về cơ chế, chưa phải encoder production

Output text ở mục 7 có cặp `key=value` nhưng chưa phải JSON với field chuẩn. `EventRecord` là lớp tùy biến của ví dụ; JUL chuẩn không tự tạo operation context map. Trong production nên tận dụng:

- API logging/backend có hỗ trợ structured arguments, MDC/Thread Context.
- JSON encoder/layout có schema rõ.
- Tracing SDK với context propagation chính thức cho trace/span.
- Framework lifecycle/middleware/interceptor để mở và đóng scope nhất quán.

Đừng tự viết một hệ thống logging phức tạp nếu backend và framework hiện tại đã giải quyết an toàn các phần này.

## 8. Operation context trong SLF4J MDC

**SLF4J MDC** (Mapped Diagnostic Context) cho phép đặt các cặp key/value vào logging context của thread theo cơ chế provider/backend. Ví dụ Logback có thể đọc những giá trị này trong pattern hoặc JSON encoder.

Đoạn minh họa trong một method có biến `LOG` là `org.slf4j.Logger`:

```java
import java.util.Map;
import org.slf4j.MDC;

Map<String, String> previous = MDC.getCopyOfContextMap();
try {
    MDC.put("operation", "checkout");
    MDC.put("operationId", "op-17");
    MDC.put("requestId", "req-42");

    LOG.info("event=operation_started");
    LOG.info("event=order_accepted orderId={}", "ORD-7");
} finally {
    if (previous == null) {
        MDC.clear();
    } else {
        MDC.setContextMap(previous);
    }
}
```

Đây là **snippet minh họa**, không phải chương trình Java độc lập. Đoạn này lưu context trước, đặt các key rồi **khôi phục toàn bộ map trước** trong `finally`. Cách khôi phục hữu ích khi thao tác lồng vào một scope có MDC của parent: chỉ gọi `MDC.clear()` vô điều kiện có thể xóa luôn context mà tầng ngoài vẫn cần.

### 8.1. Logback PatternLayout đọc MDC

Ví dụ một `logback.xml` đơn giản:

```xml
<configuration>
    <appender name="CONSOLE"
              class="ch.qos.logback.core.ConsoleAppender">
        <target>System.out</target>
        <encoder>
            <pattern>%-5level op=%X{operation} operationId=%X{operationId} requestId=%X{requestId} %logger{0} - %msg%n</pattern>
        </encoder>
    </appender>

    <root level="INFO">
        <appender-ref ref="CONSOLE"/>
    </root>
</configuration>
```

Ở đây `%X{operationId}` đọc key `operationId` từ MDC nếu event/backend có dữ liệu đó. **Cấu hình không tự tạo operationId** và việc gọi `MDC.put` không bảo đảm mọi JSON encoder tự đưa MDC ra trường JSON; phải kiểm tra encoder và schema thực tế.

**Phân biệt:** ví dụ JUL ở mục 7 ghi một `LogRecord` chứa record riêng. `SLF4J MDC` là một API khác; không lấy nguyên `%X{operationId}` để đặt vào JUL `SimpleFormatter` rồi kỳ vọng JUL hiểu.

### 8.2. Nested MDC scope cần khôi phục đúng

Nếu scope root có `operationId=op-17` và scope con tạm đặt `operationId=op-18`, khi scope con đóng, root **phải nhận lại `op-17`**. Xóa key đơn thuần có thể làm mất liên kết root. Lưu và phục hồi snapshot theo ranh giới là một cách thực hiện.

Với API như `MDC.putCloseable`, cần kiểm tra semantics của phiên bản và cách vận hành scope lồng: **đóng một key không mặc nhiên khôi phục giá trị cũ đã bị ghi đè**. Khi cần chính sách nested context phức tạp, dùng scope helper được kiểm thử, có khả năng restore đầy đủ.

### 8.3. MDC adapter phụ thuộc provider

Không phải mọi backend/provider SLF4J triển khai MDC và async propagation theo cùng cách. Có nơi adapter có chức năng đầy đủ, có nơi các thao tác không hỗ trợ hoặc không được đưa vào output. Kiểm tra provider thật ở runtime, dependency tree và appender/encoder đang chạy trước khi kết luận operation context “bị mất do MDC”.

## 9. Truyền context sang ExecutorService, CompletableFuture và message queue

### 9.1. Không dựa vào ThreadLocal tự di chuyển

Với:

```java
// Minh họa sai kỳ vọng; biến CURRENT/executor cần được khai báo.
CURRENT.set(context);
executor.submit(() -> {
    // Đừng mặc định CURRENT.get() == context ở thread này.
    doWork();
});
```

`ThreadLocal` là dữ liệu gắn với **thread hiện tại**, không phải tự động gắn với mọi task. Thread pool có thể dùng một thread khác, một thread tái sử dụng hoặc cùng thread trong trường hợp executor đặc biệt; không nên dựa vào sự ngẫu nhiên đó.

### 9.2. Capture → install → execute → restore

Đối với MDC, nguyên tắc tương tự:

```java
// Snippet: executor và LOG đã tồn tại, cùng SLF4J MDC.
Map<String, String> captured = MDC.getCopyOfContextMap();

executor.submit(() -> {
    Map<String, String> previous = MDC.getCopyOfContextMap();
    try {
        if (captured == null) {
            MDC.clear();
        } else {
            MDC.setContextMap(captured);
        }

        LOG.info("event=worker_step_finished");
    } finally {
        if (previous == null) {
            MDC.clear();
        } else {
            MDC.setContextMap(previous);
        }
    }
});
```

**Tại sao phải lưu `previous` trong worker?** Vì một thread trong pool có thể đã mang context do task khác để lại hoặc framework đặt. Helper phải tránh làm bẩn trạng thái cũ và không để request sau dùng nhầm `operationId`. Tuy nhiên, nếu phát hiện context lạ ở worker, cũng nên điều tra chính sách propagation/lifecycle, không coi restore là phép chữa mọi leak.

Với `CompletableFuture.supplyAsync`, `@Async`, reactive streams hoặc callbacks, context có thể chạy ở các thread khác tại từng stage. Cần tích hợp theo framework/context propagation API thích hợp; một wrapper cho `ExecutorService` không tự giải quyết mọi loại scheduler.

### 9.3. Qua ranh giới service hoặc message broker

`ThreadLocal` và MDC là cơ chế **bên trong process**, không đi qua HTTP/gRPC/message broker một cách tự nhiên. Khi operation đi sang service khác, phải truyền **metadata được phép và có giới hạn** trong header/envelope hoặc bằng cơ chế tracing chuẩn.

Ví dụ một message envelope minh họa:

```json
{
  "messageType": "PaymentRequested",
  "operationId": "op-17",
  "requestId": "req-42",
  "orderId": "ORD-7",
  "attempt": 1
}
```

Consumer có thể lấy các field đã validate, tạo scope mới cho bước của mình và gắn `parentOperationId` hoặc correlation relationship phù hợp. **Không tin tuyệt đối ID/context do client ngoài hệ thống gửi**: phải xác thực, giới hạn kích thước/ký tự và không cho user tự quyết định security authorization dựa trên operationId.

Với distributed tracing, ưu tiên cơ chế propagation được framework/SDK hỗ trợ (chẳng hạn trace context) thay vì tự nhét trace ID vào chuỗi text. Context nghiệp vụ như `orderId` là dữ liệu riêng và không nên được gửi đi mọi nơi nếu không cần.

### 9.4. Retry và Idempotency

Một retry có thể giữ cùng **business operationId** để liên kết các lần thử, nhưng thêm `attempt=1/2/3` để phân biệt. Trong kiến trúc khác, mỗi attempt là một operation con với ID riêng và parent chung. Cả hai đều có thể hợp lý; điều quan trọng là tài liệu hóa **độ hạt của operation**.

**Operation ID không tự là idempotency key.** Nếu API phải chống xử lý trùng giao dịch, cần quy tắc idempotency, nơi lưu trạng thái và kiểm chứng riêng. Log correlation không đảm bảo exactly-once processing.

## 10. Đo thời lượng operation đúng cách

Để đo duration trong cùng JVM, dùng thời gian đơn điệu tương đối như `System.nanoTime()`, không lấy chênh lệch `System.currentTimeMillis()` cho thao tác ngắn nếu cần chống ảnh hưởng điều chỉnh đồng hồ.

Ví dụ snippet:

```java
long startedNanos = System.nanoTime();
try {
    performOperation();
} finally {
    long elapsedNanos = System.nanoTime() - startedNanos;
    long durationMs =
            java.util.concurrent.TimeUnit.NANOSECONDS
                    .toMillis(elapsedNanos);
    // Ghi event có durationMs và outcome đã được xác định đúng.
}
```

`performOperation()` ở đây là hàm minh họa chưa được định nghĩa nên không phải chương trình độc lập. `System.nanoTime()` phù hợp để đo khoảng thời gian trong một process, **không phải timestamp tuyệt đối để gửi qua mạng**. Nếu operation chạy qua nhiều service, cần telemetry/tracing và đo ở các boundary phù hợp.

### 10.1. Mã hóa kết quả tường minh

Không nên làm:

```java
// Sai nếu không có xử lý trạng thái lỗi:
try {
    performOperation();
} finally {
    LOG.info("event=operation_finished outcome=SUCCESS");
}
```

Nếu `performOperation()` ném exception, dòng đó vẫn ghi SUCCESS. Nên theo dõi trạng thái:

```java
String outcome = "FAILED";
long started = System.nanoTime();
try {
    performOperation();
    outcome = "SUCCESS";
} finally {
    long durationMs =
            java.util.concurrent.TimeUnit.NANOSECONDS.toMillis(
                    System.nanoTime() - started);
    // Ghi outcome và durationMs bằng event/schema phù hợp.
}
```

Đoạn thứ hai vẫn là snippet chưa độc lập và cần chính sách riêng cho cancellation/timeout. Nếu method có thể trả về một kết quả thất bại **không ném exception**, outcome cũng phải được xác định từ kết quả đó, không mặc định gọi xong là SUCCESS.

### 10.2. Không đo bằng thứ tự dòng log

Một async appender hoặc collector có thể ghi log muộn hơn lúc event xảy ra. Nếu lấy timestamp ở collector để tính duration, kết quả có thể lẫn độ trễ queue/network. Ghi duration tại boundary operation hoặc dùng span/metric đo khoảng thời gian đúng ngữ nghĩa.

## 11. Structured logging, JSON và operation context

Khi collector hỗ trợ JSON, context nên là các field độc lập:

```json
{
  "timestamp": "2026-11-09T08:15:03.125Z",
  "level": "ERROR",
  "service": "orders-api",
  "event": "payment_authorization_failed",
  "operation": "checkout",
  "operationId": "op-17",
  "requestId": "req-42",
  "orderId": "ORD-7",
  "outcome": "FAILED",
  "attempt": 3,
  "error": {
    "type": "java.io.IOException",
    "message": "gateway unavailable"
  }
}
```

Đây là JSON **minh họa**. Nó không được tạo tự động chỉ vì code dùng `MDC.put` hoặc `LOG.info`.

### 11.1. Field có cấu trúc khác text chứa cặp key=value

Một message như:

```text
operationId=op-17 event=payment_failed orderId=ORD-7
```

giúp người đọc tìm kiếm thô, nhưng collector có thể chỉ biết đây là **một chuỗi message**. Nếu muốn truy vấn theo `operationId` dưới dạng field, encoder/logger API phải đưa nó thành JSON field, hoặc collector phải parse text bằng quy tắc rõ.

Ví dụ:

```json
{"message":"operationId=op-17 event=payment_failed orderId=ORD-7"}
```

khác:

```json
{"operationId":"op-17","event":"payment_failed","orderId":"ORD-7"}
```

**Đừng mặc định JSON encoder tự tách chuỗi message thành fields.** Phải chủ động xác định nguồn structured attributes, MDC, SLF4J fluent key–value API hoặc backend-specific event model.

### 11.2. Không ép toàn bộ operation context vào tên logger

Không nên:

```java
// Chống ví dụ: tạo tên logger theo ID từng operation.
Logger logger = Logger.getLogger("checkout." + operationId);
```

`operationId` là dữ liệu động của event, còn tên logger thường là package/class/category ổn định. Đưa ID vào tên logger khiến số lượng logger/name tăng, khó cấu hình level và có thể gây tốn bộ nhớ.

Thay vào đó, dùng:

```java
// Minh họa tên logger ổn định:
Logger logger =
        Logger.getLogger("com.example.orders.CheckoutService");
```

rồi đặt `operationId` vào event/context riêng.

## 12. Operation context và distributed tracing: liên quan nhưng khác nhau

Một **trace** mô tả đường đi của một thao tác qua các component với các **span** biểu thị từng công việc, quan hệ cha–con và duration. Operation context có thể bổ sung dữ liệu nghiệp vụ vào log và liên kết với trace.

Ví dụ:

```text
HTTP request: req-42
    |
    +-- traceId = trace-...
    |
    +-- Operation checkout / op-17
           |
           +-- Span HTTP controller
           +-- Operation reserve_inventory / op-18
           |      +-- Span database query
           |
           +-- Span call payment service
           +-- Operation finalize_order / op-19
```

Một operation không bắt buộc trùng một span: một operation có thể bao gồm nhiều spans, hoặc một span bao gồm nhiều bước ứng dụng, tùy cách instrument.

**Không tự tạo trace ID bằng cách đặt một chuỗi tùy ý rồi tuyên bố đã có distributed tracing.** Tracing cần context propagation, span lifecycle, sampling, timing và backend đủ khả năng liên kết dữ liệu. OperationId chỉ là một chiều của correlation.

Trong hệ observability, thường có thể:

- Tìm log theo `operationId` để xem toàn bộ sự kiện nghiệp vụ.
- Tìm trace theo `traceId` để xem latency/quan hệ spans.
- Liên kết log với span khi có `traceId` và `spanId` hợp lệ.
- Dùng metrics theo `operation.name` và `outcome` để đo tỷ lệ lỗi/latency.

Đừng đưa `operationId` **giá trị riêng cho từng request** thành nhãn (label) cho metrics với cardinality rất lớn. Với metrics, dùng tên thao tác và tập nhãn ít giá trị; với logs/traces, ID chi tiết có thể được giữ theo chính sách truy vấn/lưu trữ.

## 13. Scope lồng nhau, concurrency và các bẫy tinh vi

### 13.1. Operation con không nên xóa context của operation cha

Ví dụ checkout mở scope, inventory mở scope con, rồi inventory đóng. Nếu hàm đóng inventory chỉ gọi `CURRENT.remove()`, root checkout mất ngữ cảnh. Trong ví dụ Java 17, `Scope.close()` khôi phục `previous`, nên root vẫn còn.

Điều này cũng áp dụng với MDC: khi override các key, phải có chính sách restore giá trị cũ.

### 13.2. Context có thể bị rò trên thread pool

Mọi đường đi phải dọn scope, bao gồm exception và return sớm. Dùng `try-with-resources` hoặc `try/finally`; không để code set context ở đầu method nhưng chỉ clear ở cuối đoạn thành công.

### 13.3. Không chia sẻ map mutable qua nhiều task

Một context map mutable được truyền nguyên object sang worker có thể bị đổi trong lúc một task khác vẫn đang sử dụng. Copy/snapshot giá trị cần thiết trước khi submit; phân biệt capture (copy) và reference sharing. Một immutable record với các trường String giúp minh họa lựa chọn an toàn.

### 13.4. Operation ID có thể bị mất tại boundary

Khi event được đưa vào Kafka/RabbitMQ hay HTTP request sang service khác, `ThreadLocal` của producer vẫn ở JVM cũ. Consumer phải nhận context qua message headers/envelope theo contract, xác thực và thiết lập scope mới, rồi dọn.

### 13.5. Virtual threads không làm mọi context tự lan truyền

Java có virtual threads ở JDK 21, nhưng không vì vậy mọi context và MDC tự truyền qua các async boundaries. Cơ chế propagation phụ thuộc kiểu thread, framework và API. Bài demo dùng Java 17 và thread pool thường; khi nâng JDK hoặc chuyển framework, hãy kiểm tra chính sách context propagation được hỗ trợ thay vì giả định.

### 13.6. Operation context không được phụ thuộc vào thứ tự log

Nhiều producer/consumer, async appender hoặc collector có thể thay đổi thứ tự xuất hiện của dòng log. Thứ tự nghiệp vụ cần dùng operation/step ID, timestamp, sequence/attempt khi phù hợp; không suy quan hệ nhân quả chỉ từ dòng nào xuất hiện trước trong file.

## 14. Exception, retry và cancellation

Khi thao tác thất bại, context vẫn phải gắn với event lỗi:

```json
{
  "level": "ERROR",
  "event": "operation_failed",
  "operation": "checkout",
  "operationId": "op-17",
  "requestId": "req-42",
  "outcome": "FAILED",
  "attempt": 3,
  "error.type": "java.net.SocketTimeoutException"
}
```

Đây là mẫu, không phải output của `OperationContextDemo`.

Nguyên tắc:

- Truyền `Throwable` cho logger bằng overload phù hợp để encoder giữ stack trace/cause.
- Nếu retry được chấp nhận, ghi event `retry_scheduled` hoặc `attempt_failed` theo level phù hợp; đừng tuyên bố cả operation đã FAILED khi vẫn tiếp tục retry.
- Khi retry hết lần, event kết thúc phản ánh **outcome cuối**.
- Khi bị hủy hoặc timeout, phân biệt `CANCELLED`/`TIMEOUT` nếu hệ thống cần đo riêng.
- Nếu exception được log nhiều tầng, người vận hành dễ nhầm một lỗi thành nhiều lỗi; chọn boundary ghi lỗi cuối cùng.
- Tránh log toàn bộ request body/response và dữ liệu xác thực vào context trong nhánh lỗi.

Ví dụ SLF4J:

```java
// Snippet: LOG là SLF4J Logger, error là Throwable thực.
LOG.error("event=operation_failed operationId={}", operationId, error);
```

Code trên chỉ là **minh họa API**; khi cần structured `operationId` phải dùng MDC/key–value arguments/backend encoder phù hợp, không tự cho rằng placeholder sẽ thành JSON field. Với JUL, dùng overload `LOG.log(Level.SEVERE, "...", error)` để giữ Throwable trong `LogRecord`.

## 15. Bảo mật và giới hạn dữ liệu trong operation context

Context có xu hướng được gắn vào **mọi event trong một operation**. Nếu chứa bí mật, bí mật đó có thể xuất hiện hàng trăm lần trong log file, queue, collector và backup.

**Không nên đưa vào operation context:**

- Password, API key, bearer token, session cookie hoặc header `Authorization`.
- Số thẻ, thông tin xác thực, secrets từ configuration.
- Request/response payload đầy đủ khi không có nhu cầu rõ.
- Dữ liệu cá nhân không cần cho chẩn đoán và không phù hợp chính sách.

**Nên ưu tiên:** operation name, ID ngẫu nhiên/opaque đủ truy vết, status, loại kết quả, step, attempt, thời lượng, error code, mã nghiệp vụ đã được cho phép.

Cần cân nhắc:

- `operationId` nếu sinh từ giá trị user nhập có thể chứa newline/control characters; dùng ID do server tạo/validate và escape bằng serializer.
- JSON encoder giúp escape cú pháp nhưng **không tự masking PII hoặc secrets**.
- Context headers đến từ network phải được kiểm tra độ dài, cấu trúc và độ tin cậy.
- Việc người dùng biết `operationId` không nên cho phép họ truy cập log/operation của người khác; authorization là cơ chế riêng.
- Retention/log access policy phải phù hợp với loại định danh nghiệp vụ.
- Không để context của request A rò sang log request B do quên clear thread pool.

## 16. Vận hành: nên log gì, nên đo gì?

Một operation scope có thể xuất nhiều log, nhưng không nên ghi mọi trạng thái ở INFO theo thói quen. Bảng gợi ý:

| Tình huống | Hướng ghi log/telemetry | Lưu ý |
|---|---|---|
| Operation bắt đầu | INFO hoặc DEBUG tùy lưu lượng | Có operation name/id và thời điểm |
| Một bước bình thường | DEBUG nếu quá nhiều, INFO nếu quan trọng | Không ghi payload lớn vô ích |
| Bước chậm bất thường | WARN khi có ngưỡng đáng chú ý | Dùng `durationMs` và operation name |
| Retry hợp lệ | WARN/INFO/DEBUG theo mức ảnh hưởng | Gắn attempt và nguyên nhân |
| Operation thất bại cuối cùng | ERROR ở boundary chịu trách nhiệm | Giữ Throwable và outcome |
| Operation hoàn thành | INFO nếu cần truy vết toàn bộ workflow | Có duration và outcome |
| Tỷ lệ lỗi/latency tổng hợp | Metrics histogram/counters | Tránh operationId làm metric label |
| Quan hệ calls xuyên dịch vụ | Distributed tracing | Cần trace/span context chính thức |
| Audit bắt buộc | Audit/event store bền vững | Log có thể bị drop/rotate/xóa |

Nếu muốn **mỗi operation có đúng một bản ghi tổng kết**, có thể dùng event `operation_completed` chứa outcome, duration, số attempts và error code. Nhưng khi lỗi có nhiều tầng hoặc một request có nhiều operation, cần định nghĩa mức độ hạt rõ.

### 16.1. Sampling và logging volume

Ở traffic lớn, tất cả `operation_started` và `operation_finished` cho mọi request có thể tạo lưu lượng khổng lồ. Có thể:

- Giữ event ERROR/WARN cần thiết theo chính sách.
- Lấy mẫu các event thành công có tần suất cao khi được phép.
- Dùng metrics để tổng hợp throughput/latency.
- Khi điều tra, bật chi tiết cho một operation/service trong khoảng kiểm soát.

Sampling phải được thiết kế để không làm mất chứng cứ audit bắt buộc; cũng cần ghi nhận việc dữ liệu bị lấy mẫu khi dùng log để suy luận số lượng sự kiện.

### 16.2. Structured log ở collector

Khi xuất JSON Lines, mỗi log event nên là một JSON object trên một dòng vật lý, với operationId là field chứ không phải chuỗi ẩn trong `message`. Collector cần parse đúng và có chiến lược index/cost. Dù event được serialize đúng, queue async/shipper có thể làm trễ hoặc bỏ log, nên việc có context không tạo ra bảo đảm delivery.

## 17. Các lỗi phổ biến và cách chẩn đoán

| Dấu hiệu | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| Log ở worker thiếu `operationId` | `ThreadLocal`/MDC không tự truyền sang thread pool | Capture, install và restore context ở task |
| Request B xuất operationId của A | Không dọn context khi thread tái sử dụng | Dùng try/finally, kiểm tra middleware |
| Khi đóng operation con, root mất ID | Chỉ clear mà không restore context trước | Dùng nested scope có previous snapshot |
| Nhiều bước khác nhau dùng cùng tên logger động | Đưa ID vào logger name thay vì field | Giữ tên logger theo class, context theo event |
| JSON có operationId nhưng query không thấy | ID nằm trong chuỗi message | Dùng structured field/JSON encoder đúng |
| Có `MDC.put` nhưng output trống | Pattern/encoder không đọc key hoặc provider không hỗ trợ | Kiểm tra MDC adapter/backend thật |
| Operation bị log hoàn tất SUCCESS dù ném lỗi | `finally` luôn ghi success | Theo dõi outcome trong try/catch/finally |
| Retry bị tính là nhiều operation thất bại | Không phân biệt attempt và outcome cuối | Gắn `attempt`, `event` và quy tắc đếm |
| Mất context khi qua message broker | Không propagate ID qua envelope/header | Dùng contract metadata an toàn |
| Context đúng nhưng trace không nối được | OperationId không phải trace/span ID | Dùng tracing context chuẩn và correlation |
| Tính duration âm/lạ khi đồng hồ chỉnh | Dùng clock wall time cho elapsed time | Dùng `System.nanoTime()` trong cùng process |
| Có duplicate ERROR | Log cùng exception ở nhiều tầng | Chọn boundary chịu trách nhiệm |
| OperationId làm metrics quá nhiều series | Dùng ID động làm label | Chỉ dùng operation name/outcome ít giá trị |
| Context chứa token/PII | Gắn mọi request field vào MDC | Giới hạn field, redaction và retention |
| Log hiển thị thứ tự khác nghiệp vụ | Async queue, nhiều threads/collectors | Dùng timestamps, step IDs và quan hệ parent |

### 17.1. Quy trình debug có hệ thống

1. Xác định thao tác cần tìm và tên `operation` đã quy ước.
2. Kiểm tra **một event raw** ở nguồn phát (trước collector) có `operationId` không.
3. Kiểm tra scope được mở ở đâu, đóng ở đâu và có nhánh lỗi/return sớm không.
4. Nếu lỗi xảy ra ở worker, kiểm tra capture/propagate/restore.
5. Kiểm tra dữ liệu đã được gắn vào `LogRecord`/MDC hay chỉ nằm trong biến cục bộ.
6. Kiểm tra formatter/encoder có đưa context thành field thật không.
7. So raw event với dữ liệu collector parse/index, xét rotation, async và schema.
8. Kiểm tra operationId có phù hợp root/child relationship, requestId và traceId.
9. Kiểm tra có lộ dữ liệu nhạy cảm hoặc context bị trộn giữa request khác không.

## 18. Bài tập tự kiểm tra

### Bài A — Request và operation không giống nhau

Một request `req-42` kích hoạt `checkout` và `send_confirmation`. Nên dùng chung một operationId hay hai ID?

**Gợi ý:** nếu đây là hai operation có vòng đời/kết quả độc lập, có thể dùng `op-17` và `op-19`, cùng `requestId=req-42` hoặc relation/workflow ID để liên kết. Không dùng request ID làm operation ID cho mọi bước nếu điều đó làm mất khả năng phân biệt thao tác.

### Bài B — Scope lồng nhau

Root `checkout/op-17` mở bước `inventory/op-18`; khi bước con kết thúc, MDC `operationId` biến mất.

**Nguyên nhân:** scope con clear key mà không khôi phục root. Sửa bằng helper lưu/restore previous MDC map hoặc context bất biến theo scope.

### Bài C — ExecutorService

Một task chạy trong thread pool in log `operation=none` dù caller đã set `ThreadLocal`.

**Nguyên nhân:** ThreadLocal chỉ gắn với thread caller. Cần capture context rồi mở/đóng scope trong task; không dùng shared mutable map không kiểm soát.

### Bài D — Kết quả cuối cùng và retry

Operation thanh toán thử ba lần: hai lần đầu timeout, lần ba thành công. Nên ghi operation FAILED sau lần thử đầu tiên?

**Gợi ý:** không, nếu operation vẫn tiếp tục. Ghi các event attempt với `attempt=1,2,3` và outcome cuối của operation là SUCCESS, đồng thời quyết định level của các lỗi tạm thời theo chính sách.

### Bài E — Bảo mật context

Một middleware thêm nguyên object request, gồm Authorization header, vào MDC.

**Nguy cơ:** token có thể xuất ở nhiều log, lưu trong file/collector/backups. Nên thay bằng allowlist field an toàn và xác nhận encoder thực sự chỉ xuất các trường được phép.

## 19. Checklist triển khai operation context

- [ ] Đã định nghĩa `operation.name`, `operationId`, `parentOperationId`, `requestId` và `traceId` theo mục đích khác nhau.
- [ ] Operation name ổn định, còn ID dành cho từng lần thực thi.
- [ ] Mỗi operation có lifecycle/outcome/attempt rõ nếu nghiệp vụ cần.
- [ ] Scope mở tại boundary đúng và luôn restore trong `finally`/try-with-resources.
- [ ] Operation con không xóa nhầm context root.
- [ ] Context bất biến hoặc snapshot trước khi enqueue/submit task.
- [ ] Async/task executor truyền context tường minh và dọn ở worker.
- [ ] Qua HTTP/message queue dùng contract propagation an toàn, không dựa vào ThreadLocal.
- [ ] Formatter/encoder xuất operation context thành field thật khi cần tìm kiếm.
- [ ] MDC/Thread Context được backend/provider thực tế hỗ trợ và cấu hình đúng.
- [ ] Throwable, error code, outcome và duration được ghi ở đúng boundary.
- [ ] Duration được đo bằng đồng hồ elapsed time phù hợp; không suy từ log arrival.
- [ ] Không tạo dynamic logger name hoặc metric labels chứa ID từng request.
- [ ] Không ghi password, token, payload nhạy cảm hoặc ID không được phép.
- [ ] Đã kiểm tra log trùng, operation leak, cross-thread propagation và schema.
- [ ] Đã phân biệt log correlation với metrics, tracing và audit durability.
- [ ] Có test bình thường, nested operation, failure, retry, cancellation và worker reuse.

**Kết luận:** operation context làm cho log trả lời câu hỏi **“sự kiện này thuộc thao tác nào, lần thực hiện nào, quan hệ với bước cha ra sao và kết quả thế nào?”**. Trong Java, có thể dùng immutable context object, scoped `ThreadLocal`, MDC hoặc tracing integration, nhưng phải quản lý **vòng đời, propagation và restoration** thật rõ. Khi output là structured JSON, context cần được đưa thành field được parse đúng; khi xử lý bất đồng bộ, snapshot/restore là bắt buộc để tránh mất hoặc trộn context. Operation context cải thiện khả năng chẩn đoán, nhưng không tự biến log thành distributed trace, metric chính xác hoặc audit store bền vững.
