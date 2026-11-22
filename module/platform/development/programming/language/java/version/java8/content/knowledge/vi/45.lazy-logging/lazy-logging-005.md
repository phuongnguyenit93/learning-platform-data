# Thông điệp, ngoại lệ và thông tin ngữ cảnh trong Java Logging

Một log event có ích phải trả lời được ba câu hỏi: **điều gì đã xảy ra, vì sao nó xảy ra và nó thuộc request/tác vụ nào**. Trong Java, message, exception và context là ba thành phần riêng biệt. Nếu nối tất cả thành một chuỗi dài, hệ thống khó tìm kiếm, khó phân loại lỗi và dễ làm lộ dữ liệu nhạy cảm.

Bài này tập trung vào cách viết message rõ ràng, gắn Throwable đúng cách và truyền context xuyên suốt một luồng xử lý. Ví dụ sử dụng **java.util.logging (JUL)** có sẵn trong JDK, cùng các mẫu hiện hành của **SLF4J 2.x**, **Logback** và **Log4j 2.x**. Không dùng API logging đã lỗi thời. Chương trình Java độc lập ở cuối tương thích Java 8 và có stdout xác định.

## 1. Một log event gồm những gì?

| Thành phần | Mục đích | Ví dụ |
|---|---|---|
| Level | Mức độ nghiêm trọng | INFO, WARN, ERROR |
| Logger name | Thành phần phát log | com.example.orders.PaymentService |
| Message | Mô tả sự kiện cho người đọc | Payment accepted |
| Arguments | Giá trị thay placeholder | orderId, amount |
| Throwable | Exception, stack trace và cause | IOException |
| Context fields | Request, trace, tenant, operation | requestId, traceId |
| Timestamp | Thời điểm event | 2026-11-06T02:30:45Z |
| Source/thread | Nguồn phát và luồng thực thi | class, method, thread |

Không phải API hay backend nào cũng tự động xuất mọi trường. JUL giữ Throwable trong `LogRecord.getThrown()`; handler/formatter quyết định cách hiển thị. Backend như Log4j Core có thể bổ sung timestamp, source location và thread data tùy cấu hình. Hãy phân biệt **dữ liệu code gửi vào logger** với **cách backend ghi hoặc hiển thị event**.

### 1.1. Message mô tả sự kiện, không phải tên hàm

~~~text
Tốt:
Payment declined for order ORD-42; retryable=false

Tốt:
Inventory reservation completed for sku=SKU-17 quantity=2

Yếu:
Something went wrong

Yếu:
Error in processOrder()
~~~

Tên class/method thường đã có trong metadata logger/source. Message nên nói điều có ý nghĩa nghiệp vụ hoặc vận hành mà stack trace không tự cho biết.

### 1.2. Message cần đủ ngữ cảnh để đọc độc lập

Một message tốt thường có hành động, đối tượng và kết quả:

- Hành động: tạo, đọc, xác thực, thanh toán, đồng bộ.
- Đối tượng: order ID, job ID, resource hoặc operation.
- Kết quả: thành công, từ chối, retry, timeout.
- Lý do đã biết: quota exceeded, provider unavailable, validation failed.
- Context cần thiết: request ID hoặc trace ID nếu backend chưa tự thêm.

Không đưa mọi biến local vào log. Chỉ chọn trường giúp điều tra một tình huống cụ thể.

## 2. Chọn level theo ý nghĩa vận hành

Tên level giữa các framework khác nhau. JUL dùng `SEVERE`, `WARNING`, `INFO`, `CONFIG`, `FINE`, `FINER` và `FINEST`. SLF4J thường dùng `ERROR`, `WARN`, `INFO`, `DEBUG` và `TRACE`. Không ánh xạ máy móc chỉ dựa vào tên.

| Ý nghĩa | SLF4J | JUL gần tương đương | Dùng khi |
|---|---|---|---|
| Lỗi làm thao tác thất bại | ERROR | SEVERE | Request/job không hoàn thành |
| Bất thường nhưng có thể tiếp tục | WARN | WARNING | Fallback, retry, dữ liệu thiếu có xử lý |
| Sự kiện vận hành quan trọng | INFO | INFO | Đơn hàng tạo xong, job hoàn tất |
| Chi tiết điều tra | DEBUG | FINE | Nhánh xử lý, tham số được phép ghi |
| Dấu vết rất chi tiết | TRACE | FINER/FINEST | Phân tích sâu, thường tắt ở production |

### 2.1. Không biến mọi exception thành ERROR

Một lỗi nhập liệu được dự kiến và trả về như kết quả nghiệp vụ không nhất thiết là lỗi hệ thống. Log ở INFO hoặc WARN tùy policy, hoặc chỉ ghi metric/audit event nếu log không đem lại giá trị. Một lỗi provider khiến thanh toán không thể hoàn thành thường cần ERROR tại nơi xử lý thất bại.

Đánh giá level theo **tác động và hành động cần thiết**, không theo việc code có đi vào catch block hay không.

### 2.2. Không ghi cùng một sự cố ở mọi tầng

Nếu DAO ghi ERROR, service ghi ERROR, controller ghi ERROR rồi request filter lại ghi ERROR cho cùng exception, một lỗi tạo ra nhiều stack trace giống nhau. Chọn tầng có đủ context và chịu trách nhiệm xử lý cuối cùng để ghi exception một lần. Tầng dưới có thể bổ sung thông tin bằng cách ném exception có cause hoặc trả kết quả lỗi có cấu trúc.

### 2.3. Retry cần log có chủ đích

Không ghi ERROR cho từng lần retry bình thường nếu retry là một phần thiết kế. Có thể ghi DEBUG cho lần thử, WARN khi gần chạm giới hạn và ERROR khi thao tác cuối cùng thất bại. Thêm số lần thử, deadline và trạng thái retryable để phân biệt lỗi tạm thời với lỗi cuối.

## 3. Viết message bằng tham số

### 3.1. Tránh nối chuỗi sớm

~~~java
// Không tốt: chuỗi được tạo trước khi logger kiểm tra level.
logger.debug("Loading order " + orderId + " from " + region);

// SLF4J: parameterized message.
logger.debug("Loading order {} from {}", orderId, region);
~~~

Parameterized logging giúp message dễ đọc và giảm tạo chuỗi khi level bị tắt. Tuy nhiên, **đối số vẫn được tính trước khi gọi logger**. Nếu `buildExpensiveDiagnostic()` tốn nhiều CPU, placeholder không tự trì hoãn method ấy.

~~~java
if (logger.isDebugEnabled()) {
    logger.debug("Diagnostic state: {}", buildExpensiveDiagnostic());
}
~~~

### 3.2. Placeholder của từng API khác nhau

| API | Mẫu placeholder | Ví dụ |
|---|---|---|
| SLF4J | `{}` | `log.info("Order {}", id)` |
| Log4j API | `{}` | `log.info("Order {}", id)` |
| JUL | `{0}`, `{1}` | `log.log(Level.INFO, "Order {0}", id)` |
| JUL Supplier | Supplier trả message | `log.fine(() -> buildMessage())` |

JUL dùng định dạng kiểu `MessageFormat`, khác với SLF4J. Đừng sao chép chuỗi `"Order {}"` sang JUL rồi mong tham số được thay thế đúng.

JUL có Supplier overload để chỉ tạo message khi level được bật:

~~~java
logger.fine(() -> buildDiagnosticMessage());
~~~

### 3.3. Không gọi toString() trước placeholder

~~~java
// Không cần thiết:
logger.info("Order {}", orderId.toString());

// Tốt:
logger.info("Order {}", orderId);
~~~

Backend xử lý đối tượng tham số. Gọi `toString()` sớm thường thừa và có thể khiến việc tạo nội dung xảy ra trước khi logger biết event có được ghi hay không.

### 3.4. Giữ message ổn định, đưa giá trị biến thiên vào field

~~~text
Message: "Payment attempt failed"
Fields:
  orderId=ORD-42
  provider=acme-pay
  attempt=2
  retryable=true
~~~

Cấu trúc này cho phép tìm tất cả sự kiện `Payment attempt failed` rồi lọc theo provider, order hoặc retry count. Không đưa mọi ID vào message làm cho mỗi dòng thành một câu hoàn toàn khác.

## 4. Ghi exception để giữ nguyên chẩn đoán

Exception có type, stack trace, cause và đôi khi suppressed exceptions. Hãy chuyển **đối tượng Throwable** vào logging API để backend có thể xử lý đầy đủ.

### 4.1. SLF4J và Log4j: truyền Throwable ở cuối

~~~java
try {
    paymentGateway.charge(order);
} catch (PaymentException ex) {
    logger.error("Payment failed for order {}", order.getId(), ex);
}
~~~

Với SLF4J và Log4j API, Throwable được truyền như đối số cuối. Backend có thể ghi type, message, stack trace và cause chain riêng với message chính.

Nếu chỉ ghi:

~~~java
logger.error("Payment failed: {}", ex.getMessage());
~~~

event không còn Throwable được gắn vào. Bạn mất stack trace và cause chain, vốn thường là dữ liệu quan trọng nhất để xác định vị trí phát sinh lỗi.

### 4.2. JUL có overload nhận Throwable

~~~java
try {
    paymentGateway.charge(order);
} catch (PaymentException ex) {
    logger.log(Level.SEVERE,
            "Payment failed for order " + order.getId(), ex);
}
~~~

JUL có `log(Level, String, Throwable)`. Throwable được đặt trong trường thrown của LogRecord, không bị coi là tham số message thông thường.

Khi vừa cần tham số MessageFormat vừa cần Throwable, có thể tạo `LogRecord`, đặt `setParameters` và `setThrown` rồi gọi `logger.log(record)`. Chương trình đầy đủ phía dưới minh họa cách đó.

### 4.3. Giữ cause khi bọc exception

~~~java
try {
    remoteClient.send(command);
} catch (IOException cause) {
    throw new PaymentException(
            "Could not submit payment request", cause);
}
~~~

Constructor exception cần nhận cause để giữ chuỗi lỗi gốc. Nếu tạo exception mới chỉ bằng message, thông tin ban đầu bị mất và log ở tầng trên không thể lần theo lỗi từ network/database.

### 4.4. Đừng chỉ ghi getMessage() hoặc printStackTrace()

`ex.getMessage()` có thể null, quá ngắn, không duy nhất hoặc thiếu stack trace. Khi cần chẩn đoán, truyền Throwable. Không gọi `printStackTrace()` vì cách đó ghi trực tiếp ra stderr, bỏ qua level, context, cấu trúc, retention, routing và redaction của logging pipeline.

### 4.5. Log một lần ở nơi có trách nhiệm

Tầng dưới có thể bổ sung context rồi rethrow:

~~~java
catch (IOException cause) {
    throw new ReportExportException(
            "Export failed for report " + reportId, cause);
}
~~~

Tầng xử lý request cuối cùng có thể ghi:

~~~java
logger.error("Report export failed for report {}", reportId, ex);
~~~

Không log cùng Throwable ở mỗi tầng rồi tiếp tục ném lên. Nếu tầng dưới có thể khôi phục, ghi ở level phù hợp hoặc không ghi stack trace; nếu lỗi được xử lý và kết thúc ở đó, log với context đầy đủ.

## 5. Context liên kết nhiều log event

Trong một request, một dòng log riêng lẻ có thể không cho biết nó liên quan tới những dòng nào. Context bổ sung các trường dùng chung:

- `requestId`: định danh một request đến ứng dụng.
- `traceId` và `spanId`: liên kết log với distributed trace khi có tracing.
- `operation`: tên thao tác nghiệp vụ.
- `tenantRef` hoặc `actorRef`: định danh đã được phê duyệt, có thể pseudonym hóa.
- `jobId` hoặc `messageId`: liên kết các lần xử lý nền.

~~~text
requestId=req-7 traceId=tr-91
  INFO  Request accepted
  DEBUG Loading order ORD-42
  INFO  Payment authorized
  INFO  Response completed status=200
~~~

Một request ID ổn định giúp nối nhiều event. Không tạo ID mới ở từng method rồi gọi chúng cùng là requestId.

### 5.1. Context không thay thế message

Context cho biết event thuộc request nào, nhưng message vẫn cần mô tả hành động. Một log event chỉ có `requestId=req-7` không trả lời request đã làm gì. Kết hợp message rõ với context fields có cấu trúc.

### 5.2. MDC với SLF4J

MDC (Mapped Diagnostic Context) là map key-value do logging framework hỗ trợ. Với SLF4J API:

~~~java
MDC.put("requestId", requestId);
MDC.put("operation", "create-order");
try {
    orderService.create(command);
} finally {
    MDC.remove("operation");
    MDC.remove("requestId");
}
~~~

Layout của backend có thể thêm những key này vào log event. SLF4J chuyển MDC tới backend hỗ trợ, chẳng hạn Logback hoặc Log4j. Nếu provider không hỗ trợ MDC, không mặc định các giá trị sẽ xuất hiện trong output.

### 5.3. ThreadContext với Log4j

Log4j cung cấp Thread Context Map và Stack. Để tự động dọn context khi thoát scope, dùng `CloseableThreadContext`:

~~~java
try (CloseableThreadContext.Instance ignored =
        CloseableThreadContext.put("requestId", requestId)
                .put("operation", "create-order")) {
    orderService.create(command);
}
~~~

Try-with-resources giúp khôi phục context khi method kết thúc, kể cả khi có exception. Đây là cách tránh context cũ rò sang request khác trên thread pool.

### 5.4. Dọn context đúng phạm vi

Thread pool tái sử dụng thread. Nếu request A đặt requestId rồi không xóa, request B chạy trên cùng worker có thể nhận nhầm context của A. Hãy dùng `finally` hoặc helper AutoCloseable để context có vòng đời rõ ràng.

Không gọi `MDC.clear()` bừa bãi nếu scope hiện tại đang kế thừa context do framework quản lý; hãy chỉ xóa key do chính scope thêm hoặc lưu/khôi phục context trước đó theo contract ứng dụng.

## 6. Context trong xử lý bất đồng bộ và thread pool

MDC/ThreadContext thường gắn với thread. Khi một request gửi công việc sang executor, context **không nên được giả định tự động truyền sang thread khác**.

~~~java
Map<String, String> captured = MDC.getCopyOfContextMap();

executor.submit(() -> {
    Map<String, String> previous = MDC.getCopyOfContextMap();
    try {
        if (captured == null) {
            MDC.clear();
        } else {
            MDC.setContextMap(captured);
        }
        backgroundService.run();
    } finally {
        if (previous == null) {
            MDC.clear();
        } else {
            MDC.setContextMap(previous);
        }
    }
});
~~~

Đây là **mảnh code dùng SLF4J MDC**, cần imports và executor đã cấu hình. Lưu context cũ trước khi chạy task giúp không làm bẩn worker đã được dùng cho công việc khác. Với hệ thống dùng context propagation do framework/telemetry cung cấp, ưu tiên cơ chế tích hợp được hỗ trợ thay vì tự viết wrapper trùng lặp.

Log4j cho phép lấy snapshot map/stack hiện tại, rồi khởi tạo context trong worker bằng `CloseableThreadContext.putAll` và `pushAll`. Đóng scope sau khi task hoàn tất để dọn context.

Không lưu toàn bộ request/session trong ThreadLocal/MDC. Chỉ giữ chuỗi ngắn, ổn định, đã được phép ghi log.

## 7. Structured logging: field thay vì nhồi chuỗi

~~~json
{
  "message": "Order accepted",
  "event": "order.accepted",
  "orderId": "ORD-42",
  "tenantRef": "T-9",
  "requestId": "req-7"
}
~~~

Với cấu trúc field, hệ thống tìm kiếm có thể lọc `event=order.accepted` hoặc `orderId=ORD-42` mà không phải phân tích câu văn tự do.

### 7.1. SLF4J 2 fluent API

SLF4J 2.0 cung cấp fluent API để gắn key-value:

~~~java
logger.atInfo()
        .addKeyValue("event", "order.accepted")
        .addKeyValue("orderId", orderId)
        .addKeyValue("requestId", requestId)
        .log("Order accepted");
~~~

API fluent cần `slf4j-api 2.0+`. Để field được xuất thành JSON hoặc cấu trúc có thể truy vấn, backend/layout phải được cấu hình hỗ trợ. Nếu layout chỉ in text thuần, không mặc định mọi field sẽ tự biến thành JSON.

### 7.2. Giữ schema field nhất quán

Dùng cùng tên key xuyên suốt dịch vụ: `requestId` không lúc là `request_id`, lúc là `rid`. Định nghĩa rõ ý nghĩa, kiểu dữ liệu, nguồn tạo và chính sách null. Với hệ thống nhiều service, thống nhất schema giúp truy vấn xuyên dịch vụ dễ hơn.

Không đưa toàn bộ object, danh sách lớn hoặc raw payload thành một field. ID request hữu ích trong log search nhưng không phải lúc nào cũng phù hợp làm label metric.

## 8. Bảo vệ dữ liệu và chống log injection

Log thường được lưu lâu và nhiều nhóm có thể truy cập. Cần coi log là một kênh dữ liệu có kiểm soát.

**Không ghi trực tiếp:**

- Password, access token, refresh token, API key, private key.
- Cookie, session secret, authorization header.
- Số thẻ thanh toán đầy đủ hoặc dữ liệu xác thực thanh toán.
- Toàn bộ request/response body nếu có thông tin cá nhân.
- Dữ liệu định danh cá nhân không cần thiết cho điều tra.
- SQL parameter chứa bí mật hoặc nội dung nhạy cảm.

Khi cần truy vết actor/customer, dùng ID nội bộ hoặc pseudonymous reference đã được policy phê duyệt. Không log một chuỗi chỉ vì nó có sẵn trong exception.

### 8.1. Log injection qua newline và ký tự điều khiển

Input không tin cậy có thể chứa newline, tab hoặc ký tự điều khiển làm giả nhiều dòng log hoặc phá cấu trúc parser. Dùng structured logging/layout có escaping; khi phải ghi text tự do, chuẩn hóa hoặc escape dữ liệu đầu vào theo quy định.

Parameterized logging giúp định dạng và hiệu năng nhưng **không tự làm sạch dữ liệu độc hại**. Field value vẫn có thể chứa chuỗi không mong muốn; output encoder phải xử lý đúng.

### 8.2. Tách log vận hành và audit

Log vận hành phục vụ debug/health; audit log phục vụ ghi nhận hành động cần kiểm chứng. Audit thường cần schema, quyền ghi, retention và integrity riêng. Không mặc định một dòng DEBUG có thể thay thế audit event có yêu cầu nghiệp vụ/pháp lý.

### 8.3. Kiểm soát quyền và thời gian lưu

Giới hạn người có thể đọc log, thời gian lưu, export và quyền sửa/xóa. Không thêm secret vào MDC rồi giả định formatter sẽ tự redaction. Tốt nhất **không đưa secret vào context ngay từ đầu**.

## 9. Phân biệt logging API và backend

Một ứng dụng có thể viết code qua API facade, còn backend chịu trách nhiệm ghi file, console, JSON, async appenders và rotation.

| Thành phần | Ví dụ hiện hành | Vai trò |
|---|---|---|
| JDK logging | `java.util.logging` | API và implementation có sẵn trong JDK |
| Facade/API | `SLF4J 2.x` | API chung để code không phụ thuộc backend |
| Backend | `Logback`, `Log4j 2 Core` | Filter, format và gửi event |
| Context API | `SLF4J MDC`, `Log4j ThreadContext` | Gắn thông tin theo execution context |

### 9.1. Chọn provider tương thích

Với ứng dụng dùng SLF4J, dependency runtime cần có **một provider phù hợp**. SLF4J 2.x dùng cơ chế provider discovery; provider phải tương thích cùng major/minor với API. Nếu thiếu provider, log có thể không được ghi như mong đợi. Kiểm tra warning khi khởi động và dependency tree.

Không kéo nhiều backend/provider xung đột vào cùng ứng dụng. Không tạo vòng bridge khiến routing đệ quy. Với code thư viện, tránh ép consumer phải dùng backend cụ thể nếu chỉ cần API facade.

### 9.2. JUL khi không cần thư viện ngoài

`java.util.logging` phù hợp cho ví dụ nhỏ, ứng dụng muốn dùng logging tích hợp trong JDK hoặc thư viện không muốn thêm dependency. JUL hỗ trợ level, parameterized messages, Supplier để tạo message lười và gắn Throwable vào LogRecord.

### 9.3. Cấu hình output là một phần của chất lượng

Code có thể gửi đúng message/exception/context nhưng cấu hình backend có thể lọc sai level, bỏ stack trace, không xuất MDC hoặc ghi duplicate do handler/additivity. Khi triển khai, kiểm tra output thực tế của console/file/collector, không chỉ kiểm tra lời gọi logger.

## 10. Chương trình Java độc lập: message, Throwable và context

File **`LoggingContextDemo.java`** dưới đây chỉ dùng JDK, không cần Maven dependency. Nó dùng một Handler thu thập LogRecord để minh họa:

1. Message có nhiều tham số JUL `{0}`, `{1}`, `{2}`.
2. Request ID, route và status được đưa vào message như dữ liệu context.
3. Exception được đặt vào `LogRecord.setThrown`, giữ cause chain.
4. Handler đọc record để in message và type/cause một cách xác định.
5. Không phụ thuộc timestamp, màu terminal hoặc định dạng stack trace của môi trường.

~~~java
import java.io.IOException;
import java.text.MessageFormat;
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;
import java.util.logging.Handler;
import java.util.logging.Level;
import java.util.logging.LogRecord;
import java.util.logging.Logger;

public class LoggingContextDemo {
    static final class CaptureHandler extends Handler {
        private final List<LogRecord> records = new ArrayList<>();

        @Override
        public void publish(LogRecord record) {
            if (isLoggable(record)) {
                records.add(record);
            }
        }

        @Override
        public void flush() {
        }

        @Override
        public void close() {
        }

        List<LogRecord> records() {
            return Collections.unmodifiableList(
                    new ArrayList<>(records));
        }
    }

    static String format(LogRecord record) {
        Object[] parameters = record.getParameters();
        if (parameters == null || parameters.length == 0) {
            return record.getMessage();
        }
        return new MessageFormat(record.getMessage()).format(parameters);
    }

    public static void main(String[] args) {
        Logger logger = Logger.getLogger("com.example.orders");
        logger.setUseParentHandlers(false);
        logger.setLevel(Level.ALL);

        CaptureHandler capture = new CaptureHandler();
        capture.setLevel(Level.ALL);
        logger.addHandler(capture);

        logger.log(Level.INFO,
                "Request {0} completed route={1} status={2}",
                new Object[]{"req-7", "/orders", 200});

        try {
            throw new IOException("connection reset");
        } catch (IOException cause) {
            IllegalStateException failure =
                    new IllegalStateException(
                            "Payment provider unavailable", cause);
            LogRecord record = new LogRecord(
                    Level.SEVERE,
                    "Payment attempt failed for order {0}");
            record.setLoggerName(logger.getName());
            record.setSourceClassName(LoggingContextDemo.class.getName());
            record.setSourceMethodName("main");
            record.setParameters(new Object[]{"ORD-42"});
            record.setThrown(failure);
            logger.log(record);
        }

        for (LogRecord record : capture.records()) {
            System.out.println(record.getLevel() + " | " + format(record));
            Throwable thrown = record.getThrown();
            if (thrown != null) {
                System.out.println("Exception: "
                        + thrown.getClass().getSimpleName()
                        + " | cause="
                        + thrown.getCause().getClass().getSimpleName());
            }
        }

        logger.removeHandler(capture);
        capture.close();
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac -encoding UTF-8 LoggingContextDemo.java
java LoggingContextDemo
~~~

Stdout đã được chạy kiểm chứng:

~~~text
INFO | Request req-7 completed route=/orders status=200
SEVERE | Payment attempt failed for order ORD-42
Exception: IllegalStateException | cause=IOException
~~~

**Lưu ý:** CaptureHandler chỉ trình bày các thành phần LogRecord để stdout ổn định. Trong ứng dụng thật, handler/formatter của JUL hoặc backend SLF4J/Log4j quyết định cách render stack trace đầy đủ. Ví dụ không giả lập MDC của framework; request/route/status được truyền tường minh như tham số message.

## 11. Kiểm thử log event

Đừng chỉ test rằng method không ném exception. Log cũng là output có thể kiểm thử.

| Điều cần kiểm | Cách kiểm |
|---|---|
| Level | INFO/WARNING/SEVERE đúng tình huống |
| Message template | Có event name/hành động rõ |
| Arguments | ID, status, attempt đúng |
| Throwable | LogRecord/LoggingEvent chứa đúng exception |
| Cause chain | Exception gốc được giữ |
| Context | requestId/traceId có mặt khi cần |
| Cleanup | Context không rò sang task kế tiếp |
| Privacy | Không có token/password/PII bị cấm |
| Noise | Không có duplicate stack trace không cần thiết |
| Structured fields | Key names và types ổn định |

### 11.1. Test JUL bằng Handler

Có thể gắn một Handler trong unit test, gọi method, rồi kiểm tra `LogRecord` đã nhận: level, message, parameters, `getThrown()`, logger name. Sau test, gỡ handler và khôi phục logger level/useParentHandlers để không ảnh hưởng test khác.

### 11.2. Test SLF4J/Logback hoặc Log4j

Dùng appender/recorder test phù hợp backend để kiểm event, không so nguyên văn stack trace nếu format phụ thuộc JDK. Nên assert exception type, cause, event fields và level. Với structured logging, kiểm JSON parse thành object và field type/value, không chỉ kiểm chuỗi có chứa tên key.

### 11.3. Test MDC cleanup với thread pool

Chạy hai task liên tiếp trên cùng một worker: task đầu đặt requestId rồi hoàn tất; task sau không đặt context. Assert log của task sau không mang requestId cũ. Đây là cách bắt context leak mà test chỉ chạy một thread mới thường bỏ sót.

## 12. Quy trình triển khai logging cho service

1. Chọn API code dựa trên runtime và tiêu chuẩn dự án: JUL tích hợp sẵn hoặc facade SLF4J 2.x nếu cần tách code khỏi backend.
2. Chọn đúng một backend/provider tương thích với API và JDK mục tiêu; xác minh dependency tree và cảnh báo khi khởi động.
3. Định nghĩa level policy: event nào là INFO, cảnh báo nào là WARN và failure nào cần ERROR.
4. Đặt message template ổn định; xác định argument/field cần thiết để điều tra.
5. Chuẩn hóa context keys như requestId, traceId, operation, jobId; quy định nơi tạo, nơi truyền và nơi dọn.
6. Xác định exception boundary: tầng nào chịu trách nhiệm ghi stack trace, tầng nào chỉ bọc và rethrow cause.
7. Chọn layout text hoặc structured JSON, rồi kiểm tra backend thực sự xuất Throwable và context.
8. Đặt chính sách dữ liệu: field nào được log, field nào phải bỏ/che, retention và quyền truy cập.
9. Viết test cho message, level, exception, context cleanup và log injection.
10. Đo lượng log dưới workload thực; hạ các event quá dày hoặc chuyển chi tiết sang DEBUG/TRACE.

### 12.1. Một event contract mẫu

| Field | Kiểu | Bắt buộc | Ý nghĩa |
|---|---|---|---|
| `event` | String | Có | `payment.attempt.failed` |
| `orderId` | String | Nếu được phép | ID đơn hàng |
| `requestId` | String | Khi thuộc request | Liên kết request |
| `provider` | String | Có | Nhà cung cấp |
| `attempt` | Integer | Có | Số lần thử |
| `retryable` | Boolean | Có | Có thể retry không |
| `error.type` | String | Khi có exception | Loại exception |
| `traceId` | String | Khi có tracing | Liên kết distributed trace |

Không đưa `cardNumber`, `authorizationHeader` hay raw payment token vào contract. Nếu field không có giá trị, thống nhất cách bỏ field hoặc biểu diễn null; đừng dùng nhiều chuỗi thay thế như `unknown`, `n/a` và chuỗi rỗng lẫn lộn.

## 13. Các lỗi thường gặp

**1. Message chung chung:** “Error occurred”. Ghi rõ operation, object và outcome.

**2. Nối chuỗi trước khi biết level có bật:** dùng placeholder hoặc Supplier.

**3. Dùng sai placeholder:** SLF4J dùng `{}`; JUL dùng `{0}`.

**4. Ghi exception.getMessage() thay Throwable:** mất stack trace/cause.

**5. Gọi printStackTrace():** bỏ qua logging pipeline.

**6. Bọc exception nhưng bỏ cause:** mất gốc lỗi.

**7. Log cùng exception ở mọi tầng:** tạo nhiều stack trace trùng nhau.

**8. Ghi ERROR cho mọi validation failure:** làm nhiễu tín hiệu vận hành.

**9. Ghi WARN cho mọi retry bình thường:** khiến cảnh báo khó phân biệt.

**10. Đặt MDC nhưng không remove:** context rò qua thread pool.

**11. Giả định MDC tự truyền sang executor:** capture/restore hoặc dùng context propagation được hỗ trợ.

**12. Dùng ThreadLocal lưu toàn bộ request:** tăng rủi ro memory và lộ dữ liệu.

**13. Dùng tên field không nhất quán:** chuẩn hóa schema.

**14. Nhét JSON bằng string concatenation:** dùng structured logging và layout phù hợp.

**15. Tin parameterized logging tự chống log injection:** cần escaping/sanitization theo output format.

**16. Ghi password/token/header bí mật:** loại bỏ hoặc pseudonymize trước khi log.

**17. Ghi toàn bộ exception message không kiểm soát:** có thể chứa dữ liệu nhạy cảm.

**18. Log và swallow exception:** caller tưởng thao tác thành công; phải trả lỗi hoặc xử lý rõ.

**19. Không kiểm provider/backend khi dùng SLF4J:** API compile nhưng không có nơi ghi log.

**20. Kéo nhiều provider vào classpath:** có thể gây xung đột hoặc routing sai.

**21. Chỉ kiểm console:** production appender có thể format/filter khác.

**22. Log từng vòng lặp lớn:** tăng chi phí, dung lượng và làm mất tín hiệu.

**23. Dùng request ID làm metric label không giới hạn:** log search và metric cardinality có yêu cầu khác nhau.

## 14. Checklist trước production

1. Message mô tả sự kiện và kết quả cụ thể chưa?
2. Level có đúng tác động vận hành không?
3. Giá trị biến thiên có được truyền dạng parameter/field không?
4. Exception có được gắn dạng Throwable và giữ cause không?
5. Có ghi cùng stack trace nhiều tầng không?
6. requestId/traceId có thống nhất xuyên các event liên quan không?
7. MDC/ThreadContext có được dọn trong mọi đường success/error không?
8. Async task có context propagation và cleanup không?
9. Không có password, token, cookie hoặc dữ liệu cá nhân bị cấm?
10. Untrusted text đã được escape/sanitize để tránh log injection?
11. Field names/types có schema ổn định?
12. Backend có thật sự xuất exception và context fields?
13. Level filter, rotation, retention và quyền truy cập phù hợp?
14. Có test event, exception, context cleanup và dữ liệu nhạy cảm?
15. Log có đủ giá trị điều tra mà không tạo noise không cần thiết?

## 15. Bài tập tự luyện

1. Một message log tốt cần trả lời những câu hỏi nào?
2. Vì sao không nên ghi tên method đơn thuần làm message?
3. Khi nào dùng INFO, WARN và ERROR?
4. Vì sao lỗi validation được dự kiến không nhất thiết là ERROR?
5. SLF4J placeholder khác JUL placeholder thế nào?
6. Parameterized logging có trì hoãn việc tính mọi đối số không?
7. Vì sao nên truyền Throwable thay vì exception.getMessage()?
8. JUL lưu Throwable ở đâu trong LogRecord?
9. Tại sao không gọi printStackTrace() trong ứng dụng?
10. Khi bọc exception mới, vì sao phải truyền cause?
11. Log cùng exception ở DAO, service và controller gây vấn đề gì?
12. MDC dùng để làm gì?
13. Vì sao phải remove context khi thread pool tái sử dụng worker?
14. Context có tự truyền sang executor task không?
15. Log4j ThreadContext có thể dùng scope tự đóng nào?
16. Structured logging khác nhồi key-value vào một chuỗi thế nào?
17. SLF4J fluent key-value API cần phiên bản nào?
18. Vì sao parameterized logging không tự chống log injection?
19. Những dữ liệu nào không nên ghi log?
20. Vì sao log vận hành không thay thế audit log?
21. Cần test những trường nào của LogRecord?
22. Nếu không có SLF4J provider thì ứng dụng có thể gặp vấn đề gì?
23. Tại sao không nên thêm nhiều provider xung đột?
24. Khi nào nên log exception một lần ở tầng boundary?

**Gợi ý đáp án:** (1) Điều gì xảy ra, vì sao và thuộc request/task nào. (2) Không mô tả kết quả nghiệp vụ. (3) Theo tác động và khả năng tiếp tục. (4) Vì đó là kết quả nghiệp vụ bình thường. (5) SLF4J dùng `{}`, JUL dùng `{0}` kiểu MessageFormat. (6) Không, biểu thức đối số vẫn tính trước; Supplier/guard có thể trì hoãn. (7) Giữ stack trace/cause. (8) `LogRecord.getThrown()`. (9) Nó bỏ qua pipeline. (10) Bảo toàn chuỗi nguyên nhân. (11) Duplicate noise. (12) Liên kết log bằng key-value theo execution context. (13) Tránh rò context cũ. (14) Không nên giả định. (15) CloseableThreadContext. (16) Field có thể query/filter độc lập. (17) SLF4J 2.0+. (18) Giá trị đầu vào vẫn có thể chứa newline/ký tự độc hại. (19) Credentials, token, cookie, PII không cần thiết. (20) Audit có yêu cầu integrity/retention riêng. (21) Level, message, params, thrown, logger/source. (22) Log có thể rơi vào NOP/no output hoặc warning. (23) Conflict/routing không rõ. (24) Ở nơi xử lý cuối cùng có đủ context và chịu trách nhiệm phản hồi.

## Tổng kết

Một log event tốt kết hợp **message mô tả sự kiện**, **Throwable giữ stack trace/cause** và **context fields liên kết request/tác vụ**. Dùng placeholder theo đúng API, chọn level theo tác động, log exception ở tầng chịu trách nhiệm xử lý và dọn MDC/ThreadContext sau mỗi scope. Khi chuyển sang thread pool, truyền context có chủ đích. Dùng structured fields khi cần truy vấn, bảo vệ dữ liệu nhạy cảm và kiểm thử log như một phần output của ứng dụng. JUL có sẵn trong JDK; SLF4J 2.x, Logback và Log4j 2.x là các lựa chọn hiện hành cần cấu hình backend/provider phù hợp.

### Tài liệu chính thức hiện hành

- [Oracle Java SE 26 — java.util.logging.Logger](https://docs.oracle.com/en/java/javase/26/docs/api/java.logging/java/util/logging/Logger.html)
- [Oracle Java SE 26 — LogRecord](https://docs.oracle.com/en/java/javase/26/docs/api/java.logging/java/util/logging/LogRecord.html)
- [SLF4J 2.x Manual](https://www.slf4j.org/manual.html)
- [SLF4J FAQ — Provider and Fluent API](https://www.slf4j.org/faq.html)
- [Apache Log4j 2 — API and best practices](https://logging.apache.org/log4j/2.x/manual/api.html)
- [Apache Log4j 2 — Thread Context](https://logging.apache.org/log4j/2.x/manual/thread-context.html)
- [Apache Log4j 2 — Structured Messages](https://logging.apache.org/log4j/2.x/manual/messages.html)
- [Logback — Current Manual](https://logback.qos.ch/manual/)
