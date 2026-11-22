# Context của log trong Java Logging

## 1. Context của log là gì?

**Logging context (ngữ cảnh log)** là tập thông tin giúp người đọc hiểu **một sự kiện log thuộc về yêu cầu nào, thao tác nào, thành phần nào và trạng thái xử lý nào**. Log level và message cho biết có chuyện gì xảy ra; context giúp xác định **chuyện đó xảy ra trong hoàn cảnh nào** để điều tra và liên kết các sự kiện.

Một dòng log thiếu context:

~~~text
WARN Payment provider timed out
~~~

Cùng sự kiện khi có context:

~~~text
2026-11-09T12:34:56.789Z WARN
service=checkout
logger=com.example.payment.PaymentClient
event_code=PAYMENT_ATTEMPT_TIMEOUT
request_id=req-42
trace_id=trace-abc
operation=authorize
attempt=2
provider=primary-gateway
outcome=retrying
message="Payment provider timed out"
~~~

Ví dụ thứ hai cho biết đây là lỗi **của một lần thử** đang được retry, thuộc request nào và xảy ra ở phần nào của hệ thống. Không nhất thiết cần mọi field cho mọi log, nhưng **những trường được chọn đúng** giúp phân biệt một sự kiện bình thường, một lần retry và một lỗi cuối cùng.

**Context không phải là bản thân Logger hay message.** Logger có tên như **com.example.payment.PaymentClient** thể hiện nguồn phát, còn context theo request có thể khác ở mỗi lần class đó xử lý yêu cầu. Một Logger dùng chung cho hàng triệu request vẫn có thể ghi các request_id khác nhau mà không cần tạo Logger mới.

### Mục tiêu thực tế

- Liên kết log thuộc cùng request, job hoặc giao dịch.
- Truy tìm hành trình xử lý qua nhiều lớp và dịch vụ.
- Biết thao tác hiện tại và dependency liên quan.
- Phân biệt từng lần thử lại với kết quả cuối.
- Tìm nguyên nhân exception mà không phải đoán từ message.
- Hỗ trợ truy vấn theo event_code, service, release hoặc trace.
- Bảo vệ dữ liệu nhạy cảm bằng cách chỉ chọn các field cần thiết.

**Nguyên tắc:** Context phải **đúng phạm vi**, **được gắn vào sự kiện**, **được dọn đúng vòng đời**, và **không chứa dữ liệu ngoài quyền được thu thập**.

## 2. Một sự kiện log có những loại context nào?

Có thể chia thành các nhóm sau:

| Nhóm | Ví dụ field | Nguồn |
| --- | --- | --- |
| **Event metadata** | timestamp, level, logger_name, event_code | Logger hoặc logging backend |
| **Application/resource** | service, environment, release, instance_id | Cấu hình triển khai |
| **Execution** | thread_name, operation, attempt | Code và runtime |
| **Request/correlation** | request_id, correlation_id, trace_id, span_id | Request middleware, tracing |
| **Business (được phép)** | order_id, payment_operation, outcome | Nghiệp vụ đã chọn lọc |
| **Error** | error_type, reason_code, cause, stack trace | Throwable và xử lý lỗi |
| **Performance** | duration_ms, size_bytes, retry_count | Đo lường tại nguồn |

### Context tĩnh

Một số field ít thay đổi trong vòng đời instance:

~~~json
{
  "service": "checkout",
  "environment": "production",
  "release": "2.4.1",
  "region": "ap-southeast-1"
}
~~~

Các field này thường được cấu hình ở **backend, JSON encoder hoặc collector**, thay vì truyền thủ công vào từng lời gọi log.

### Context động theo request

Một request cụ thể có thể có:

~~~json
{
  "request_id": "req-42",
  "trace_id": "trace-example",
  "operation": "createOrder"
}
~~~

Các field này phải thay đổi theo đúng request/job, và không được rò rỉ sang request khác trên cùng thread.

### Context riêng cho event

Một sự kiện PAYMENT_RETRY có thể thêm:

~~~json
{
  "event_code": "PAYMENT_RETRY",
  "attempt": 2,
  "reason_code": "GATEWAY_TIMEOUT",
  "outcome": "retrying"
}
~~~

Không cần gắn **attempt=2** lên mọi log của request, vì một số sự kiện không thuộc lần thử thứ hai. Context có phạm vi càng hẹp nên được khai báo càng gần nơi phát sự kiện.

## 3. Context khác message, Logger name và log level ra sao?

Giả sử mã Java viết:

~~~java
private static final Logger log =
        LoggerFactory.getLogger(OrderService.class);

log.info("Order created, orderId={}", orderId);
~~~

Đây là mã minh họa dùng **org.slf4j.Logger** và **LoggerFactory**, giả định đã import class, có biến orderId và nằm trong phạm vi class/method phù hợp.

Ba thành phần:

- **Logger name:** Thường là tên class **OrderService** hoặc package đầy đủ, giúp tìm nguồn phát.
- **Level INFO:** Mức ưu tiên của sự kiện.
- **Message:** Mô tả hành động, ở đây là việc tạo đơn.

Nếu cần truy vấn riêng **order_id** và **request_id**, việc nhúng tất cả vào message có thể khiến hệ thống phải parse chuỗi. Với backend hỗ trợ structured logging, nên thêm **trường có tên** thay vì chỉ nối vào một câu.

**Không tạo Logger mới cho mỗi request ID.** Tên logger là category tương đối ổn định; tạo hàng triệu logger tên theo request có thể làm tăng tài nguyên và làm cấu hình level theo package/class khó kiểm soát.

## 4. Logging context và structured logging liên quan thế nào?

**Logging context** là thông tin được gắn với sự kiện. **Structured logging** là cách biểu diễn thông tin thành field có kiểu, ví dụ JSON hoặc key-value.

Không phải mọi context đều bắt buộc nằm trong JSON. Ví dụ:

~~~text
INFO [request_id=req-42] Order created
~~~

đã có một context field theo người đọc, nhưng hệ thống tìm kiếm có thể vẫn phải parse text.

Một bản ghi JSON rõ hơn:

~~~json
{
  "timestamp": "2026-11-09T12:34:56.789Z",
  "level": "INFO",
  "service": "orders",
  "logger_name": "com.example.orders.OrderService",
  "event_code": "ORDER_CREATED",
  "request_id": "req-42",
  "order_id": "ORD-42",
  "outcome": "success",
  "message": "Order created"
}
~~~

Những field này cần được **encoder/layout và collector** thực sự giữ lại. Chỉ thêm context trong Java API không đồng nghĩa nó đã được đưa vào file hay hệ thống tìm kiếm.

**Một số context nên là string**, ví dụ request_id và trace_id; **một số nên là number/boolean**, ví dụ attempt, duration_ms, cache_hit. Không nên chuyển mọi giá trị thành String nếu cần lọc số hoặc tính toán. MDC truyền thống thường là map String–String, còn cơ chế key-value event của backend có thể giữ kiểu giàu hơn.

## 5. Context nên sống bao lâu?

Phạm vi sống quyết định giá trị nào cần được thiết lập và thời điểm phải xóa.

~~~text
Ứng dụng / instance
  └── service, environment, release
      |
      └── request / message / job
          └── request_id, trace_id
              |
              └── operation
                  └── operation=createOrder
                      |
                      └── attempt
                          └── attempt=2, reason_code=TIMEOUT
                              |
                              └── một sự kiện log cụ thể
                                  └── event_code, outcome, error_type
~~~

Ví dụ:
- **service** có thể gắn ở encoder/collector cho toàn bộ tiến trình.
- **request_id** được đặt ở đầu xử lý request và xóa khi request kết thúc.
- **operation** được đặt khi vào thao tác rồi được khôi phục về giá trị trước khi thao tác kết thúc.
- **attempt** được gắn vào sự kiện retry hoặc một scope hẹp.
- **error_type** phản ánh exception của đúng sự kiện.

**Không giữ context nghiệp vụ trong biến static mutable dùng chung giữa thread.** Nếu một request cập nhật biến static **currentRequestId**, request khác có thể ghi nhầm ID. Phần lớn giải pháp context logging dùng cơ chế gắn với luồng thực thi hoặc context propagation có kiểm soát.

## 6. MDC trong SLF4J là gì?

**MDC (Mapped Diagnostic Context)** là API của SLF4J dùng lưu các cặp **String key–String value** liên quan đến ngữ cảnh log, thường theo thread theo đặc tính backend. Ví dụ ở đầu request đặt request ID, sau đó các lời gọi log bên dưới có thể được layout ghi kèm request ID mà không truyền thủ công ID vào từng message.

Đoạn minh họa với SLF4J:

~~~java
import org.slf4j.MDC;

MDC.put("request_id", requestId);
try {
    processRequest();
} finally {
    MDC.remove("request_id");
}
~~~

Trong đoạn này, **requestId** và **processRequest()** đã được định nghĩa trong ứng dụng; đây chưa phải chương trình Java độc lập. **MDC.put** không tự làm console hiển thị request_id: backend phải cấu hình PatternLayout hoặc JSON encoder phù hợp.

### Vì sao phải dọn trong finally?

Một web server thường có thread pool:

~~~text
Thread worker-1:
   request A -> MDC request_id=A
   request A kết thúc
   request B -> dùng lại worker-1
~~~

Nếu request A quên xóa MDC, những log đầu request B có thể mang **request_id=A**, khiến điều tra sai và làm rò rỉ ngữ cảnh giữa người dùng.

**Luôn dọn hoặc khôi phục context trong finally.** Với trường hợp không có context cũ và chỉ đặt một key, MDC.remove(key) thường đủ. Nếu code lồng nhau có thể **ghi đè một key đã tồn tại**, nên lưu và khôi phục bản context trước đó, không chỉ remove.

Ví dụ khôi phục toàn bộ context SLF4J trong một scope:

~~~java
import java.util.Map;
import org.slf4j.MDC;

Map<String, String> previous = MDC.getCopyOfContextMap();
try {
    MDC.put("operation", "reserveStock");
    processStockReservation();
} finally {
    if (previous == null) {
        MDC.clear();
    } else {
        MDC.setContextMap(previous);
    }
}
~~~

Đây là đoạn minh họa, giả định **processStockReservation()** tồn tại. Mục đích là giữ nguyên request_id và trace_id của scope bên ngoài, đồng thời khôi phục **operation** sau khi xong. **getCopyOfContextMap** trả một bản sao context nếu có; **setContextMap** đặt lại các cặp đã lưu.

Cơ chế thực thi MDC và cách context được gắn với thread phụ thuộc provider/backend. Không xem MDC là kho lưu trạng thái nghiệp vụ bền vững.

## 7. Log4j 2 ThreadContext

Trong **Log4j 2**, **ThreadContext** cung cấp cơ chế đưa context vào logging event. Thông dụng là:
- **Context Map:** Các cặp key–value.
- **Context Stack:** Các giá trị theo ngăn xếp, khi cơ chế đó thực sự cần thiết.

Ví dụ minh họa:

~~~java
import org.apache.logging.log4j.ThreadContext;

ThreadContext.put("request_id", requestId);
try {
    processRequest();
} finally {
    ThreadContext.remove("request_id");
}
~~~

Giống MDC, code phải dọn context khi kết thúc request. Khi scope lồng nhau có thể ghi đè key cũ, nên thiết kế cơ chế snapshot/restore hoặc scope phù hợp, thay vì luôn remove và làm mất giá trị của scope cha.

Log4j 2 có API hỗ trợ scope như **ThreadContext.putCloseable** trong các phiên bản phù hợp; cần kiểm tra hành vi cleanup/restore khi lồng nhau trước khi dùng ở middleware phức tạp.

Ví dụ pattern text trong Log4j 2 có thể truy cập Context Map bằng conversion tương ứng như **%X{request_id}**, tùy layout. Muốn structured JSON cần Layout như JSON layout được hỗ trợ và cấu hình export các trường.

**SLF4J MDC và Log4j ThreadContext tương tự về mục đích, nhưng không phải hai API có thể hoán đổi tùy ý.** Khi ứng dụng dùng SLF4J với provider Log4j2, phải kiểm thử context đi qua bridge/provider thật.

## 8. Context đi đâu khi chạy bất đồng bộ?

Đây là một vấn đề quan trọng nhất của logging context.

Trong Java, một tác vụ có thể chạy qua:
- **ExecutorService**.
- **CompletableFuture.supplyAsync/runAsync**.
- Thread pool của web server.
- Scheduled job, queue consumer.
- Framework reactive/non-blocking.
- Các ranh giới dịch vụ qua HTTP, gRPC hoặc message broker.

**Không mặc định MDC/ThreadContext tự được truyền qua các boundary này.** Một ThreadLocal chỉ thuộc thread hiện tại theo mô hình cơ bản, trong khi tác vụ async có thể chạy trên thread khác. Cả Java virtual threads và các framework có cơ chế context riêng đều cần xem xét semantics cụ thể.

Ví dụ thiếu propagation:

~~~text
Request thread:
   MDC request_id=req-42
   log: REQUEST_RECEIVED request_id=req-42

Executor thread:
   MDC chưa được thiết lập
   log: INVENTORY_RESERVED request_id=(missing)
~~~

Nếu logger ở worker thread đọc MDC hiện tại, nó không tìm thấy request_id dù công việc thuộc cùng request.

### Capture, install và restore

Ý tưởng thường dùng:

1. **Capture** một bản sao context khi chuẩn bị giao tác vụ.
2. **Install** context đó trong thread thực thi tác vụ.
3. Thực hiện công việc và ghi log.
4. **Restore hoặc clear** context cũ trong finally.
5. Không truyền những field không được phép đi tới ranh giới mới.

Ví dụ minh họa với SLF4J MDC và Executor:

~~~java
Map<String, String> captured = MDC.getCopyOfContextMap();

executor.submit(() -> {
    Map<String, String> old = MDC.getCopyOfContextMap();
    try {
        if (captured == null) {
            MDC.clear();
        } else {
            MDC.setContextMap(captured);
        }

        performTask();
    } finally {
        if (old == null) {
            MDC.clear();
        } else {
            MDC.setContextMap(old);
        }
    }
});
~~~

Đây là đoạn code minh họa, giả định các biến, imports và hàm đã tồn tại. Đối với framework production, nên dùng cơ chế **context propagation chính thức** hoặc wrapper cho executor/task để tránh lặp lại logic không an toàn ở nhiều nơi.

**Không truyền toàn bộ ThreadLocal tùy ý giữa request.** Chỉ truyền những field correlation và metadata thực sự cần, có chính sách bảo mật rõ ràng.

## 9. Ví dụ Java 17 chạy độc lập: context theo request và propagation

Ví dụ sau sử dụng **java.util.logging** có sẵn trong JDK 17, không cần SLF4J/Logback. Mục tiêu là minh họa các ý tưởng:
- Một Logger dùng chung cho toàn bộ chương trình.
- Context request gồm request_id, trace_id và operation.
- Context theo thread được giữ trong một **ThreadLocal** đơn giản.
- Mở một **scope** để thêm hoặc ghi đè context và **khôi phục giá trị cũ** khi đóng.
- Gửi tác vụ sang **ExecutorService**, chuyển bản sao context rõ ràng.
- Tạo **LogRecord chứa snapshot của context** ngay lúc phát event.
- Handler xuất stdout ổn định, không phụ thuộc timestamp/thread name.
- Xác nhận context của main thread đã được dọn.

**Chú ý:** ThreadLocal và Handler tự viết này là **mô hình giáo dục**, không phải MDC production hay tracing chuẩn. Trong ứng dụng thực tế nên dùng SLF4J MDC, Log4j ThreadContext, OpenTelemetry context hoặc cơ chế được framework hỗ trợ. Giá trị **trace-demo** bên dưới chỉ là nhãn minh họa, không phải một trace ID theo chuẩn truyền tải distributed tracing.

Tạo file **LoggingContextDemo.java**:

~~~java
import java.util.LinkedHashMap;
import java.util.Map;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.logging.Handler;
import java.util.logging.Level;
import java.util.logging.LogRecord;
import java.util.logging.Logger;

public final class LoggingContextDemo {
    private static final Logger LOG =
            Logger.getLogger("demo.orders.OrderService");

    private static final ThreadLocal<Map<String, String>> CONTEXT =
            ThreadLocal.withInitial(LinkedHashMap::new);

    private static final class Scope implements AutoCloseable {
        private final Map<String, String> before;

        private Scope(Map<String, String> before) {
            this.before = before;
        }

        @Override
        public void close() {
            if (before.isEmpty()) {
                CONTEXT.remove();
            } else {
                CONTEXT.set(before);
            }
        }
    }

    private static Scope withContext(Map<String, String> additions) {
        Map<String, String> before =
                new LinkedHashMap<>(CONTEXT.get());
        Map<String, String> next =
                new LinkedHashMap<>(before);
        next.putAll(additions);
        CONTEXT.set(next);
        return new Scope(before);
    }

    private static Map<String, String> snapshot() {
        return new LinkedHashMap<>(CONTEXT.get());
    }

    private static void logEvent(String code) {
        LogRecord record = new LogRecord(Level.INFO, code);
        record.setLoggerName(LOG.getName());

        // Ban sao tai thoi diem tao event:
        record.setParameters(new Object[] {snapshot()});
        LOG.log(record);
    }

    private static final class ContextOutputHandler extends Handler {
        @Override
        public void publish(LogRecord record) {
            if (!isLoggable(record)) {
                return;
            }

            @SuppressWarnings("unchecked")
            Map<String, String> context =
                    (Map<String, String>) record.getParameters()[0];

            System.out.println(
                    record.getLevel().getName()
                    + " | request_id="
                    + context.getOrDefault("request_id", "-")
                    + " | trace_id="
                    + context.getOrDefault("trace_id", "-")
                    + " | operation="
                    + context.getOrDefault("operation", "-")
                    + " | " + record.getMessage());
        }

        @Override
        public void flush() {
            System.out.flush();
        }

        @Override
        public void close() {
            flush();
        }
    }

    public static void main(String[] args) throws Exception {
        Handler output = new ContextOutputHandler();
        output.setLevel(Level.INFO);

        LOG.setLevel(Level.INFO);
        LOG.setUseParentHandlers(false);
        LOG.addHandler(output);

        ExecutorService executor =
                Executors.newSingleThreadExecutor();

        try {
            try (Scope request = withContext(Map.of(
                    "request_id", "req-42",
                    "trace_id", "trace-demo",
                    "operation", "createOrder"))) {

                logEvent("REQUEST_RECEIVED");

                Map<String, String> captured = snapshot();

                Future<?> task = executor.submit(() -> {
                    try (Scope requestInWorker =
                            withContext(captured);
                         Scope operation =
                            withContext(Map.of(
                                    "operation", "reserveStock"))) {
                        logEvent("INVENTORY_RESERVED");
                    }
                });

                task.get();
                logEvent("REQUEST_COMPLETED");
            }

            System.out.println(
                    "CONTEXT_CLEARED=" + CONTEXT.get().isEmpty());
        } finally {
            executor.shutdown();
            CONTEXT.remove();
            LOG.removeHandler(output);
            output.close();
        }
    }
}
~~~

Biên dịch/chạy bằng **JDK 17 trở lên**:

~~~bash
javac -encoding UTF-8 LoggingContextDemo.java
java LoggingContextDemo
~~~

**Stdout chính xác của demo:**

~~~text
INFO | request_id=req-42 | trace_id=trace-demo | operation=createOrder | REQUEST_RECEIVED
INFO | request_id=req-42 | trace_id=trace-demo | operation=reserveStock | INVENTORY_RESERVED
INFO | request_id=req-42 | trace_id=trace-demo | operation=createOrder | REQUEST_COMPLETED
CONTEXT_CLEARED=true
~~~

### Vì sao ba dòng context đúng?

1. **withContext(...)** sao chép context hiện tại rồi thêm field; nó không sửa Map của scope cha.
2. Main thread mở scope với request_id, trace_id và operation=createOrder, sau đó ghi REQUEST_RECEIVED.
3. **snapshot()** tạo bản sao trước khi gửi việc sang executor, tránh phụ thuộc vào việc worker có cùng ThreadLocal hay không.
4. Worker thread mở requestInWorker với bản sao đã truyền, rồi mở scope nhỏ hơn ghi đè operation thành **reserveStock**.
5. Khi worker kết thúc, hai scope đóng theo thứ tự ngược lại; context được khôi phục hoặc xóa khỏi worker thread.
6. **task.get()** bảo đảm task đã hoàn tất trước khi main phát REQUEST_COMPLETED, làm thứ tự đầu ra có thể kiểm chứng.
7. Main vẫn giữ operation=createOrder; context trong worker không làm thay đổi context của main.
8. Khi request scope đóng, context ban đầu của main là map rỗng, nên ThreadLocal được remove và kiểm tra in **CONTEXT_CLEARED=true**.
9. **LogRecord.setParameters** chứa bản sao context tại thời điểm tạo sự kiện. Handler đọc bản sao đó, không đọc ThreadLocal của thread đang publish; đây là nguyên tắc quan trọng với asynchronous logging.
10. **setUseParentHandlers(false)** ngăn JUL Handler ở cha in dòng log ngoài mong muốn, và custom Handler không thêm timestamp để demo có stdout cố định.

### Những giới hạn của ví dụ

- **Trace ID** là dữ liệu giả lập, không thực hiện distributed tracing.
- **ThreadLocal** chỉ mô phỏng một phần chức năng MDC; thiếu tính năng tích hợp backend, structured encoder và propagation của framework.
- **Handler** chỉ in ba field cố định; một backend production có thể xuất JSON, timestamp, exception và nhiều field theo schema.
- Không nên copy toàn bộ request object hoặc payload vào Map context, vì rủi ro bảo mật và tăng chi phí.
- Khi có nhiều tác vụ song song, thứ tự log giữa các task không nhất thiết xác định. Ví dụ dùng single-thread executor và task.get chỉ để kiểm chứng cách context được truyền/khôi phục.
- Ngoài cleanup context, production cần xử lý shutdown, interruption, timeout và các lỗi của task theo yêu cầu nghiệp vụ.

**Bài học quan trọng:** Context cần được **capture tại ranh giới**, **thiết lập trong scope thực thi**, **đính kèm vào event** và **dọn/khôi phục sau khi dùng**. Không dựa vào một biến global mutable như currentRequestId.

## 10. Context trong SLF4J 2.x: MDC và key-value event

SLF4J 2.x có hai nhóm kỹ thuật bổ trợ nhau.

### MDC: thông tin chung trong scope

~~~java
MDC.put("request_id", requestId);
try {
    log.info("Validating order");
    validateOrder();
    log.info("Order validation completed");
} finally {
    MDC.remove("request_id");
}
~~~

Đoạn minh họa này giả định đã có logger **log**, requestId, validateOrder và import MDC. Nếu backend layout xuất MDC, **cả hai log** đều có request_id mà code không cần truyền ID vào từng lời gọi.

### Fluent key-value: thông tin của đúng sự kiện

~~~java
log.atInfo()
        .addKeyValue("event_code", "ORDER_CREATED")
        .addKeyValue("order_id", orderId)
        .addKeyValue("amount_minor", amountMinor)
        .addKeyValue("currency", "VND")
        .log("Order created");
~~~

Đây là API **SLF4J 2.x**, không phải SLF4J 1.7. Các biến thuộc method của ứng dụng. Fluent API có thể gắn các field của **một event**, còn MDC dùng cho context nhiều event trong cùng scope.

**Không mặc định addKeyValue tự làm log trở thành JSON.** Provider/backend và encoder/layout phải được cấu hình để xuất các key-value pairs. Những giá trị số thường nên giữ dạng number ở structured event nếu encoder hỗ trợ, không ép thành string không có lý do.

Khi có exception:

~~~java
log.atError()
        .addKeyValue("event_code", "ORDER_SAVE_FAILED")
        .addKeyValue("order_id", orderId)
        .addKeyValue("outcome", "failed")
        .setCause(exception)
        .log("Cannot persist order");
~~~

**setCause** giúp backend nhận Throwable và có thể xuất cause chain, stack trace. Context không thay thế nhu cầu giữ exception đúng API.

## 11. Cách hiển thị context trong Logback

Với **SLF4J + Logback**, PatternLayout có thể đưa MDC vào text bằng conversion **%X{key}**. Ví dụ **logback.xml**:

~~~xml
<configuration>
    <appender name="CONSOLE"
              class="ch.qos.logback.core.ConsoleAppender">
        <target>System.out</target>
        <encoder>
            <charset>UTF-8</charset>
            <pattern>%d{yyyy-MM-dd HH:mm:ss.SSS,UTC} %-5level %logger{36} req=%X{request_id} trace=%X{trace_id} - %msg%n</pattern>
        </encoder>
    </appender>

    <root level="INFO">
        <appender-ref ref="CONSOLE"/>
    </root>
</configuration>
~~~

Đây là một **file text logging**, không phải JSON. Khi code đã đặt **MDC request_id/trace_id**, pattern mới có thể xuất giá trị ở vị trí tương ứng.

Muốn **structured JSON** thực sự, cần encoder/layout JSON tương thích với phiên bản Logback và bảo đảm MDC/SLF4J key-value pairs được serialize thành field theo schema. Không chỉ đặt ký tự ngoặc nhọn quanh %msg rồi coi đó là JSON đúng chuẩn.

### Kiểm tra khi context không xuất hiện

- Code đã đặt MDC ở đúng thread chưa?
- Field có bị remove quá sớm không?
- Một thao tác async có bị thiếu propagation không?
- Logback có thực sự là provider SLF4J đang chạy không?
- Pattern hoặc JSON encoder có xuất MDC field đó không?
- Collector có giữ field hoặc đổi tên/loại bỏ nó không?

**Một context có trong MDC nhưng bị encoder bỏ qua không giúp dashboard truy vấn được.** Luôn kiểm tra output thật.

## 12. Context trong Log4j 2 và Layout

Trong Log4j 2, **ThreadContext** thường được truy cập từ Layout bằng pattern tương ứng như **%X{request_id}** hoặc đưa vào JSON template tùy backend.

Ví dụ minh họa cấu hình **log4j2.xml** chỉ xuất text:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<Configuration>
    <Appenders>
        <Console name="OUT" target="SYSTEM_OUT">
            <PatternLayout
                pattern="%d{ISO8601} %-5p req=%X{request_id} trace=%X{trace_id} %c - %m%n"/>
        </Console>
    </Appenders>

    <Loggers>
        <Root level="info">
            <AppenderRef ref="OUT"/>
        </Root>
    </Loggers>
</Configuration>
~~~

Cấu hình trên cần các dependency Log4j 2 phù hợp; nó **không** hoạt động như file logback.xml hoặc JUL logging.properties.

Với JSON layout, có thể thiết kế field từ ThreadContext. Phải kiểm thử tên field, dữ liệu bị bỏ hoặc đổi type và khả năng xử lý Throwable khi chuyển backend hoặc nâng phiên bản.

**ThreadContext Map thường mang giá trị string.** Nếu cần duration_ms thực sự là number trong JSON, hãy dùng một cơ chế field event có type và encoder phù hợp, không mặc định mọi string number trong MDC được collector chuyển thành number đúng.

## 13. Java Util Logging có MDC sẵn không?

**java.util.logging (JUL)** cung cấp **Logger, LogRecord, Handler, Formatter và Filter**, nhưng không có một API MDC dạng map key–value được chuẩn hóa tương tự **org.slf4j.MDC**.

Một ứng dụng JUL có thể:
- Truyền các tham số vào LogRecord.
- Tạo Formatter/Handler tùy biến.
- Dùng một context holder riêng và capture snapshot khi tạo LogRecord.
- Dùng bridge hoặc adapter đã được kiểm thử để đưa log sang một backend thống nhất.

Ví dụ Java 17 ở trên minh họa context bằng **ThreadLocal + Map + LogRecord.parameters**. Đây là một cách dạy nguyên lý, không phải API structured logging mặc định của JUL. Không đưa **LogRecord.parameters** thẳng vào một Formatter thông thường rồi kỳ vọng nó tự hiểu các key request_id, trace_id hoặc operation.

**Không trộn ngẫu nhiên JUL Handler với Logback Appender hay Log4j2 Appender.** Mỗi backend có hệ cấu hình riêng. Nếu dùng bridge, phải kiểm tra pipeline và chọn đúng hướng, tránh log trùng hoặc vòng chuyển tiếp.

## 14. Logging context và distributed tracing

**Tracing context** dùng để nối span xuyên các ranh giới. Các trường quan trọng:

| Trường | Vai trò |
| --- | --- |
| **trace_id** | Nhận diện toàn bộ trace |
| **span_id** | Nhận diện một span riêng |
| **trace flags** | Thông tin sampling hoặc trạng thái tracing theo quy ước |
| **request_id** | ID của yêu cầu trong ứng dụng |
| **correlation_id** | ID dùng để liên kết các bước theo hợp đồng nghiệp vụ |

Một **request ID** không tự động là trace ID chuẩn. Khi ứng dụng dùng OpenTelemetry hoặc một tracing framework, nên lấy trace_id/span_id từ **span context hiện tại**, thay vì tạo các chuỗi ID tự do mà không được truyền qua dịch vụ.

### Truyền context giữa các service

Ví dụ về ý tưởng:

~~~text
Gateway:
   request_id=req-42, trace_id=t123, event=REQUEST_RECEIVED
      |
      v
Order Service:
   request_id=req-42, trace_id=t123, event=ORDER_VALIDATED
      |
      v
Payment Service:
   request_id=req-42, trace_id=t123, event=PAYMENT_RETRY
~~~

Các giá trị **t123** ở đây chỉ là nhãn minh họa, không phải mã trace_id đáp ứng format của mọi giao thức.

Ở production, context thường truyền qua các **header/tracing protocol** hoặc metadata message, chẳng hạn quy ước **W3C Trace Context** cho HTTP khi được các framework hỗ trợ. Các middleware phải nhận, kiểm tra và truyền context đúng; không tự tin bất kỳ header correlation nào do client gửi nếu nó có thể gây injection, tiết lộ dữ liệu hoặc vượt ranh giới tin cậy.

**Logging context không tự đảm bảo causal ordering.** Dù nhiều service có cùng trace_id, timestamp giữa host có thể bị lệch clock. Kết hợp trace, sequence, event type và telemetry để hiểu trình tự.

## 15. MDC và scope lồng nhau: lỗi dễ gặp

Giả sử service đang đặt:

~~~text
request_id=req-42
operation=createOrder
~~~

Bên trong phương thức reserveStock, ta ghi đè:

~~~text
operation=reserveStock
~~~

Sau khi reserveStock kết thúc, **operation phải trở về createOrder**. Nếu scope nhỏ chỉ gọi remove("operation"), context cha mất operation. Đó là lý do cần **snapshot và restore** khi key có thể bị ghi đè.

Một lỗi khác: một middleware đặt request_id rồi code ở tầng dưới gọi **MDC.clear()** trong finally, làm mất luôn trace_id và các field do tầng trên quản lý. Nếu cần xóa hết context ở ranh giới request, điều đó phải là chính sách rõ ràng; trong scope con, chỉ dọn phần mình sở hữu hoặc khôi phục snapshot.

### Scope ownership

- Middleware request thường sở hữu request_id và context cơ bản.
- Tracing middleware/instrumentation sở hữu trace_id và span_id.
- Service operation có thể sở hữu operation và event-specific field.
- Một thư viện bên dưới không nên xóa tất cả context của caller tùy tiện.

**Ownership của context quan trọng không kém ownership của tài nguyên I/O.** Khi không biết ai đặt field, dễ xóa quá rộng, ghi đè hoặc giữ giá trị quá lâu.

## 16. Dữ liệu nào nên hoặc không nên đặt trong context?

### Nên cân nhắc

- service, environment, release, instance_id.
- request_id, trace_id, span_id đúng định dạng và nguồn.
- operation, event_code, outcome.
- error_type, reason_code.
- order_id hoặc transaction_id nếu chính sách cho phép.
- attempt, duration_ms, size_bytes ở event phù hợp.

### Không nên

- Password, access/refresh token, API key, private key.
- Authorization header, cookie đăng nhập, session secret.
- Toàn bộ request/response body.
- Số thẻ thanh toán, dữ liệu tài khoản nhạy cảm hoặc PII không cần thiết.
- Object domain lớn hoặc tham chiếu đến object mutable.
- URL nguyên query chứa token hoặc dữ liệu cá nhân.
- Field có thể bị client thao túng mà không được kiểm tra.

**Structured context có thể khiến dữ liệu nhạy cảm xuất hiện ở mọi dòng log của request.** Nếu lưu token trong MDC, không chỉ một log có nguy cơ lộ; mọi layout xuất MDC có thể lặp lại token trong hàng chục hoặc hàng trăm event.

### Dữ liệu do client cung cấp

Request ID từ header của client không luôn đáng tin. Hệ thống có thể cần:
- Validate độ dài và định dạng.
- Sinh ID nội bộ khi client không cung cấp hoặc giá trị không hợp lệ.
- Tránh log injection qua ký tự điều khiển.
- Không dùng client-provided ID làm quyền truy cập hay định danh bảo mật.
- Tách external_correlation_id khỏi internal_request_id khi hợp đồng yêu cầu.

## 17. Context và cardinality

**Cardinality** là số giá trị khác nhau của field. Một số field có cardinality thấp: level, service, environment, event_code, outcome. Một số field có cardinality cao: request_id, trace_id, order_id.

**Field cardinality cao không có nghĩa phải bỏ khỏi log.** Request ID rất hữu ích để tìm đúng request. Nhưng đưa request_id thành metric label có thể tạo số lượng time series quá lớn.

Phân biệt:
1. **Field lưu trong log** để điều tra.
2. **Field được index** để truy vấn nhanh.
3. **Metric label** để nhóm số liệu.

Không index mọi field chỉ vì chúng có trong context. Đặt chính sách theo tần suất truy vấn, retention, độ phân biệt và chi phí. Những field dùng để nhóm dashboard nên có miền giá trị ổn định; tránh tạo event_code chứa ID động.

### Log volume

Giả sử một service phát **1.000 log/giây**, mỗi bản ghi sau khi thêm context có **600 byte**:

~~~text
1.000 × 600 = 600.000 byte/giây
600.000 × 86.400 = 51,84 GB/ngày dữ liệu thô
~~~

Đây là ước tính, chưa tính nén, index, replication hoặc retention. Thêm context làm sự kiện hữu ích hơn, nhưng cũng có chi phí ghi, encode, truyền và lưu. Không copy nguyên cả request body vào context để “có đủ thông tin” khi phần lớn dữ liệu không được dùng để điều tra.

## 18. Snapshot của context khi logging bất đồng bộ

Một chi tiết thường bị bỏ qua: **event đã được tạo** có thể được xử lý bởi Handler/Appender ở một thread khác về sau.

Nếu Formatter chỉ đọc MDC/ThreadLocal **của thread đang ghi file**, thay vì context được capture tại thời điểm tạo sự kiện, nó có thể lấy nhầm context của worker logging hoặc không lấy được context nào.

Ví dụ khái quát:

~~~text
T0: Request thread tạo event E với request_id=req-42
T1: E nằm trong queue của async appender
T2: Request scope kết thúc và clear context
T3: Worker log ghi E ra file
~~~

**Đúng:** Sự kiện E giữ context **req-42** đã được snapshot tại T0.

**Sai:** Worker ở T3 mới lấy MDC hiện tại của chính nó rồi ghi thông tin thiếu hoặc sai request.

Các backend hỗ trợ asynchronous logging thường có cơ chế chuẩn bị/capture event context. Nếu tự viết Handler hoặc queue, phải thiết kế snapshot rõ ràng. Java demo dùng **new LinkedHashMap<>(CONTEXT.get())** khi tạo LogRecord để minh họa điều đó.

Đồng thời, snapshot không nên giữ tham chiếu đến một object mutable lớn rồi để nó bị thay đổi sau khi event đã được xếp hàng.

## 19. Lỗi exception và context có liên hệ thế nào?

Với exception, context cần trả lời:
- **operation** nào thất bại?
- **request_id/trace_id** nào?
- **event_code/reason_code** nào?
- **outcome** là failed hay retrying?
- **error_type** là gì?
- **Throwable/cause** có được giữ không?

Ví dụ SLF4J 2.x:

~~~java
log.atError()
        .addKeyValue("event_code", "PAYMENT_AUTHORIZATION_FAILED")
        .addKeyValue("operation", "authorize")
        .addKeyValue("reason_code", "PROVIDER_TIMEOUT")
        .addKeyValue("outcome", "failed")
        .setCause(exception)
        .log("Payment authorization failed");
~~~

MDC có thể đã mang request_id và trace_id từ middleware. Các field của sự kiện bổ sung outcome và reason_code; **setCause** giữ Throwable.

**Không dùng context như lý do để log cùng stack trace ở mọi tầng.** Nếu Repository, Service và Controller đều ghi ERROR rồi rethrow, số dòng log bị phóng đại. Chọn ranh giới chịu trách nhiệm lỗi cuối, đồng thời ghi các event thấp hơn khi mang ngữ cảnh có giá trị khác biệt.

Không đưa exception.getMessage() vào context thường trực của cả request nếu nó có thể chứa thông tin nhạy cảm và chỉ liên quan một event.

## 20. Context khi dùng Spring Boot và các framework khác

Trong ứng dụng Spring Boot, request filters, interceptors hoặc observability instrumentation thường là nơi phù hợp để:
- Thiết lập request ID và correlation ID.
- Gắn/đọc tracing context.
- Đảm bảo cleanup khi request kết thúc, kể cả có exception.
- Chọn JSON encoder hoặc pattern trong cấu hình backend.
- Truyền context qua các task executor được framework quản lý nếu có hỗ trợ.

Tuy nhiên, **cơ chế cụ thể khác nhau theo version Spring Boot, SLF4J, Logback/Log4j2 và tracing framework**. Không nên khẳng định mọi Executor hoặc reactive pipeline tự truyền MDC chỉ vì project đã bật tracing.

Một checklist kiểm thử thực tế:

1. Request A có request_id=A.
2. Request B có request_id=B.
3. A và B chạy cùng lúc hoặc tái sử dụng cùng một worker thread.
4. Mọi log của A/B phải có context đúng.
5. Sau khi request xong, log của tác vụ khác không còn ID của request cũ.
6. Một CompletableFuture được submit từ A giữ correlation khi framework được cấu hình propagation.
7. Exception vẫn mang trace_id và không làm mất context trong finally.

Với hệ thống reactive, không dùng ThreadLocal như một giả định toàn cục; xem cơ chế context của Reactor hoặc framework tương ứng và cách adapter đưa context đến logging event.

## 21. Context trong file, console và collector

Có context trong Java chưa đủ; cần kiểm tra nó thật sự xuất hiện ở output.

Ví dụ pipeline:

~~~text
Request middleware
    |
    | request_id, trace_id, operation
    v
SLF4J MDC / Log4j ThreadContext
    |
    v
Logger phát event
    |
    v
Backend: Layout / Encoder
    |
    +--> Console text pattern
    +--> File JSON lines
    |
    v
Collector -> parser -> index/storage -> dashboard
~~~

Một số sự cố:
- Pattern không có **%X{request_id}**, nên console thiếu request ID.
- JSON encoder không export MDC/key-value pairs.
- Field được xuất dưới tên khác với schema collector đang tìm.
- Collector bỏ field vì kích thước hoặc schema whitelist.
- Timestamp nguồn bị ghi đè bởi ingestion timestamp.
- Request ID có kiểu string nhưng parser map sang kiểu khác.
- Log bị cắt giữa dòng khi file rotation hoặc quá tải.

**Cần integration test qua toàn pipeline**. Một event JSON có field trong file có thể vẫn bị collector bỏ mất; kết quả tìm kiếm mới là bằng chứng người vận hành thực sự sử dụng được context.

## 22. Các lỗi thường gặp

| Sai lầm | Hậu quả | Cách xử lý |
| --- | --- | --- |
| Chỉ có message không có correlation | Khó tìm các sự kiện của một request | Gắn request_id/trace_id đúng phạm vi |
| Tạo Logger theo request ID | Nhiều logger/category không cần thiết | Logger theo class/package |
| Dùng biến static currentRequestId | Race condition, nhầm request | Dùng context theo scope và propagation |
| Không dọn MDC trong thread pool | Rò rỉ ngữ cảnh giữa request | finally, scope và restore |
| Scope con xóa field của scope cha | Thiếu context sau khi return | Snapshot và restore giá trị cũ |
| Tin MDC tự đi qua Executor | Worker thiếu ID | Capture/install/restore |
| Formatter đọc ThreadLocal lúc ghi async | Event bị sai ID | Capture context vào event khi tạo |
| Chỉ gắn MDC, không cấu hình layout | Log output thiếu field | Kiểm tra encoder/PatternLayout |
| Dùng event_code chứa order ID động | Cardinality cao | event_code ổn định, order_id riêng |
| Đưa token hoặc payload vào MDC | Rò rỉ trên nhiều dòng | Allowlist field, redaction |
| Dùng trace_id tùy ý không từ tracing | Truy vấn phân tán không liên kết thật | Lấy ID từ tracing context |
| Đổi type request_id/attempt tùy service | Schema conflict | Quy ước kiểu dữ liệu |
| Lặp ERROR ở mọi tầng | Phóng đại số sự cố | Chọn điểm ghi lỗi cuối |
| Không kiểm tra collector | Field mất sau ingest | End-to-end test |
| Index mọi field có cardinality cao | Tăng chi phí | Chính sách index có chọn lọc |
| Coi JSON là encryption | Dữ liệu vẫn đọc được | Access control, retention, redaction |

## 23. Checklist áp dụng logging context trong Java

1. **Phân loại context:** Tĩnh theo service, động theo request, operation và event.
2. **Logger name:** Giữ ổn định theo class/package, không tạo Logger cho mỗi request.
3. **Schema:** Dùng field names nhất quán và có đơn vị rõ ràng khi cần.
4. **ID tương quan:** Truyền request_id, trace_id, span_id đúng nguồn và phạm vi.
5. **Scope:** Đặt context ở ranh giới phù hợp; cleanup/restore trong finally.
6. **Async:** Capture và truyền context qua task/executor/queue theo cơ chế đáng tin.
7. **Snapshot:** Event phải giữ context của thời điểm phát sinh, không đọc nhầm sau khi scope đã hết.
8. **Backend:** Cấu hình MDC/ThreadContext trong Logback/Log4j2 hoặc phương án JUL tương ứng.
9. **Output:** Kiểm tra text pattern hoặc JSON encoder thực sự xuất context.
10. **Throwable:** Gắn cause vào lỗi phù hợp, không làm mất stack trace.
11. **Bảo mật:** Không log token/password/cookie, hạn chế dữ liệu cá nhân và payload.
12. **Chi phí:** Kiểm tra cardinality, index, log volume và retention.
13. **Thử nghiệm:** Có request đồng thời, reused thread, async task, exception và cleanup.
14. **Collector:** Kiểm tra field/type sau ingest và khả năng tìm theo request_id/trace_id.

## 24. Câu hỏi tự kiểm tra

**1. Context của log khác message thế nào?**  
Message mô tả sự kiện; context đưa ra thông tin như request ID, operation, service và kết quả để hiểu sự kiện đó thuộc về đâu.

**2. Vì sao không tạo Logger theo request ID?**  
Logger name nên là category ổn định theo class/package. Request ID là context động theo từng yêu cầu.

**3. Vì sao phải xóa/khôi phục MDC trong finally?**  
Thread có thể được tái sử dụng; thiếu cleanup sẽ làm log request sau mang ID cũ.

**4. MDC có tự truyền qua ExecutorService không?**  
Không nên giả định. Phải capture, install và restore context hoặc dùng framework propagation hỗ trợ.

**5. Vì sao scope lồng nhau cần khôi phục context trước đó?**  
Vì scope con có thể ghi đè operation của scope cha; chỉ remove sẽ làm mất giá trị cũ.

**6. Context của một event async nên được lấy lúc nào?**  
Nên snapshot tại thời điểm tạo event để backend worker xử lý sau vẫn giữ đúng context nguồn.

**7. SLF4J 2.x addKeyValue khác MDC ra sao?**  
MDC thường là context nhiều sự kiện trong scope; addKeyValue gắn field vào một event cụ thể.

**8. Vì sao context trong MDC vẫn có thể không xuất hiện trong dashboard?**  
Vì layout, encoder hoặc collector có thể không xuất/lưu field đó.

**9. Nên đặt token trong request MDC để dễ điều tra không?**  
Không. Token nhạy cảm có thể bị lặp vào nhiều dòng log. Dùng ID kỹ thuật đã được cho phép.

**10. Logging context có tự tạo tracing chuẩn không?**  
Không. Muốn trace_id/span_id hữu ích xuyên dịch vụ, cần tracing context và propagation phù hợp.

**Ghi nhớ:** **Context của log là thông tin gắn với sự kiện để trả lời “điều gì xảy ra, ở đâu, thuộc request và thao tác nào”.** Trong Java, có thể dùng SLF4J MDC, Log4j2 ThreadContext hoặc cơ chế JUL tùy biến. Hãy giữ context có phạm vi rõ ràng, truyền qua async boundary đúng cách, snapshot vào event, dọn/khôi phục khi scope kết thúc và chỉ xuất những field hữu ích, an toàn. Context đúng giúp logs liên kết với traces và metrics mà không làm rò rỉ thông tin giữa các request.
