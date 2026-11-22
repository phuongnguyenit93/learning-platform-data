# Message có ngữ cảnh trong Java Logging

## 1. Vì sao log message cần ngữ cảnh?

Trong một ứng dụng Java chạy nhiều request và tác vụ đồng thời, thông báo như `ERROR Failed` hoặc `INFO Done` không đủ để xác định **thao tác nào**, **request nào** và **nguyên nhân nào** đang được nói tới. **Message có ngữ cảnh (contextual log message)** là bản ghi log kết hợp sự kiện với các thuộc tính cần thiết để người đọc hoặc hệ thống quan sát có thể truy lại nguồn, phạm vi xử lý và kết quả.

So sánh:

```text
ERROR Timeout
```

và:

```text
WARN event=payment.authorize.timeout service=checkout requestId=req-42 orderId=ord-81 dependency=payment-gateway errorCode=UPSTREAM_TIMEOUT
```

Dòng thứ hai giúp lọc theo mã sự kiện, đối chiếu log của cùng `requestId` và tìm tác động của phụ thuộc. Những ID và thông tin này chỉ là ví dụ. Mục tiêu không phải ghi càng nhiều dữ liệu càng tốt: message phải **đủ ngữ cảnh để chẩn đoán, nhất quán để truy vấn và an toàn đối với dữ liệu nhạy cảm**.

Một bản ghi tốt thường trả lời được bốn câu hỏi: điều gì xảy ra, ở thành phần nào, thuộc công việc nào và có kết quả gì.

## 2. Phân lớp các trường ngữ cảnh

Ngữ cảnh được gắn với log từ nhiều phạm vi khác nhau. Không phải mọi event cần tất cả các trường.

| Phạm vi | Ví dụ trường | Mục đích |
| --- | --- | --- |
| Ứng dụng/instance | `service`, `version`, `environment`, `instanceId` | Biết ứng dụng/phiên bản phát log |
| Request hoặc luồng phân tán | `requestId`, `traceId`, `spanId` | Nối các event thuộc cùng lần xử lý |
| Tác vụ nền | `jobId`, `batchId`, `taskType` | Truy vết công việc không nằm trong HTTP request |
| Thao tác | `operation`, `dependency`, `retryAttempt` | Biết bước hoặc phụ thuộc cụ thể |
| Kết quả | `event`, `outcome`, `durationMs`, `errorCode` | Tìm được sự kiện, kết quả và chi phí |
| Lỗi | `errorType`, ngoại lệ/stack trace khi phù hợp | Chẩn đoán thất bại |

Các ID cần ổn định trong **đúng phạm vi**: `requestId` thường giữ nguyên khi xử lý một request, `jobId` giữ nguyên trong một job, còn `spanId` thay đổi giữa các span trong cùng trace. Đừng dùng tên thread hoặc tên lớp làm khóa duy nhất cho một request; thread pool có thể tái sử dụng thread và một request có thể đi qua nhiều thread.

Nên chọn các trường an toàn và có thể kiểm soát. Tên operation, mã lỗi, kết quả và ID kỹ thuật phù hợp thường hữu ích hơn việc đưa toàn bộ HTTP body, cookie, token hoặc `toString()` của một đối tượng vào log.

### 2.1. Ba lớp message

Một cách thiết kế rõ ràng:

- **Sự kiện ổn định**: `event=order.created`, `event=payment.authorize.failed`, `event=cache.refresh.completed`. Dùng tên phân loại nhất quán, không ghép ID động vào tên event.
- **Thông điệp cho con người**: `"Payment provider timed out"` mô tả tình huống, không phải nguồn duy nhất để hệ thống nhóm lỗi.
- **Trường cho máy truy vấn**: `requestId`, `errorCode`, `durationMs`, `outcome` và các thuộc tính khác được mã hóa tách biệt.

Ví dụ dạng JSON:

```json
{
  "timestamp": "2026-01-12T09:15:30.125Z",
  "level": "WARN",
  "service": "checkout",
  "event": "payment.authorize.timeout",
  "message": "Payment provider timed out",
  "requestId": "req-42",
  "traceId": "4e9c3ab82fbb4dce8e5be54b2a778d21",
  "dependency": "payment-gateway",
  "errorCode": "UPSTREAM_TIMEOUT",
  "durationMs": 1200
}
```

Đây là **mẫu cấu trúc**, không phải một output tự động của JDK. Muốn phát JSON thực tế cần encoder/formatter được cấu hình phù hợp. Chọn một quy tắc tên trường (`requestId` hay `request_id`) và kiểu dữ liệu (`durationMs` là số) rồi áp dụng nhất quán; JSON cho phép truy vấn theo field mà không phụ thuộc regex trên message.

## 3. Ngữ cảnh đi cùng vòng đời request/job

Một request có thể qua HTTP controller, service, repository rồi gọi API khác. Nếu mỗi tầng đều ghi `Started` hoặc `Done`, nhiều request đồng thời sẽ trộn lẫn. Hãy lưu ID tương quan trong các event quan trọng:

```text
INFO event=request.received  requestId=req-42 operation=checkout
INFO event=inventory.locked  requestId=req-42 orderId=ord-81
INFO event=payment.accepted  requestId=req-42 orderId=ord-81
INFO event=request.completed requestId=req-42 outcome=success durationMs=38
```

Khi `req-42` bị lỗi, lọc theo ID này giúp tìm toàn bộ mốc đã ghi; khi hệ thống có distributed tracing, các `traceId`/`spanId` giúp nối tiếp giữa các service.

### 3.1. Phân biệt ba loại định danh

**Request ID** là định danh một lần xử lý request theo quy ước gateway/ứng dụng; một request từ client có thể làm phát sinh nhiều lời gọi nội bộ. **Trace ID** nhận diện chuỗi công việc phân tán, thường được truyền bằng cơ chế tracing thống nhất. **Span ID** nhận diện từng đơn vị công việc bên trong trace; nhiều span có thể chung trace ID.

Một minh họa logic:

```text
Gateway:  requestId=R, traceId=T, spanId=S1
Checkout: requestId=R, traceId=T, spanId=S2
Payment:  requestId=R, traceId=T, spanId=S3
```

`R/T/S1` chỉ là ký hiệu giải thích, không phải định dạng trace ID hợp lệ. Khi dùng OpenTelemetry hoặc thư viện tracing khác, hãy dùng context và propagator mà thư viện cung cấp, ví dụ W3C Trace Context; không tự phát sinh một trace ID mới cho mỗi service rồi mất khả năng đối chiếu.

ID từ header client cần chính sách tin cậy và kiểm tra độ dài, bộ ký tự, định dạng. Không dùng trực tiếp một giá trị có ký tự điều khiển hoặc cực dài để tạo tên field, tên logger hay đầu ra log.

### 3.2. Xác định phạm vi rõ ràng

Một workflow tốt gồm: tạo hoặc nhận correlation ID ở ingress; truyền context tới các bước; ghi kết quả ở ranh giới chịu trách nhiệm; rồi dọn hoặc khôi phục ngữ cảnh khi request kết thúc. Với job bất đồng bộ tiếp tục sau request, có thể tạo `jobId` mới và giữ khóa liên kết về request tạo job nếu thực sự hữu ích.

Ngữ cảnh được giữ trong một `Map` toàn cục có thể sửa bởi nhiều thread sẽ bị ghi đè giữa các request. Nên truyền context bất biến hoặc dùng cơ chế context theo phạm vi phù hợp. Trên đường ghi log, chụp snapshot nếu backend có thể xử lý sự kiện sau thời điểm lời gọi trả về.

## 4. Truyền ngữ cảnh trong Java

### 4.1. Truyền qua đối số và đối tượng bất biến

Cách dễ kiểm soát nhất là cung cấp context rõ ràng cho phương thức cần log:

```java
record RequestContext(String requestId, String traceId) {}

void execute(RequestContext context) {
    // Mã nghiệp vụ dùng context.requestId() khi tạo log event.
}
```

Đây là **đoạn khai báo minh họa**, chưa phải một chương trình Java độc lập. Lợi ích là context đi theo luồng dữ liệu, không phụ thuộc thread và ít có nguy cơ rò rỉ khi xử lý bất đồng bộ. Hạn chế là phải truyền qua các lớp hoặc thiết kế wrapper hợp lý.

### 4.2. MDC của SLF4J và backend hỗ trợ

**Mapped Diagnostic Context (MDC)** thường dùng với `org.slf4j.MDC`, để các event do logger trong thread hiện tại phát ra có thể được backend gắn cùng `requestId`. Pattern hoặc encoder của backend phải được cấu hình lấy các trường MDC; lời gọi `MDC.put` tự nó không bảo đảm output nào cũng có field đó.

Đoạn dưới đây dùng SLF4J và `processRequest()`/`logger` đã tồn tại; **không chạy độc lập bằng JDK** vì cần dependency và backend tương ứng:

```java
import org.slf4j.MDC;

String previous = MDC.get("requestId");
try {
    MDC.put("requestId", requestId);
    logger.info("event=request.received");
    processRequest();
} finally {
    if (previous == null) {
        MDC.remove("requestId");
    } else {
        MDC.put("requestId", previous);
    }
}
```

Khôi phục giá trị trước đó quan trọng khi phạm vi lồng nhau; chỉ xóa mù `requestId` có thể làm mất context của tầng gọi bên ngoài.

**JUL (`java.util.logging`) không có MDC API mặc định giống SLF4J.** Với JUL thuần, có thể truyền context trong message, gắn metadata với `LogRecord` và sử dụng Formatter/Handler tùy chỉnh. Một ứng dụng có bridge sang backend khác phải hiểu backend và cấu hình thực tế, không mặc định đặt MDC cho SLF4J thì mọi JUL logger đều tự xuất context đó.

### 4.3. Thread pool, CompletableFuture và async

MDC/ThreadLocal không tự động đi cùng một công việc khi công việc được chạy trên thread của executor. Nếu không truyền context, log ở worker thread thiếu `requestId`; nếu không dọn context ở cuối, thread pool có thể giữ `requestId` của request trước và gán nhầm cho request sau.

Đây là **đoạn minh họa** dùng SLF4J MDC với `executor` và `runJob()` đã tồn tại:

```java
Map<String, String> captured = MDC.getCopyOfContextMap();

executor.execute(() -> {
    Map<String, String> previous = MDC.getCopyOfContextMap();
    try {
        if (captured == null) {
            MDC.clear();
        } else {
            MDC.setContextMap(captured);
        }
        runJob();
    } finally {
        if (previous == null) {
            MDC.clear();
        } else {
            MDC.setContextMap(previous);
        }
    }
});
```

Cần import `java.util.Map` và `org.slf4j.MDC` trong dự án. `captured` là snapshot khi submit task, còn `previous` là context vốn có trên worker thread. `finally` phục hồi giá trị cũ. Với reactive pipeline, tracing, virtual threads hoặc framework có context propagation riêng, dùng cơ chế mà hệ thống đó hỗ trợ; không coi ThreadLocal là nơi tự động theo mọi bước async.

## 5. Chọn cách mã hóa message

Với text log, cách gọn là `key=value`; với hệ thống thu thập lớn, JSON hoặc một cấu trúc sự kiện có kiểu dữ liệu rõ thường dễ truy vấn hơn. Dù chọn cách nào:

1. **Tên field phải nhất quán:** chọn `requestId` hoặc `request_id`, không mỗi module một cách.
2. **Giữ kiểu dữ liệu:** trong JSON, `durationMs` nên là số, `outcome`/mã lỗi nên dùng bộ giá trị ổn định.
3. **Escape dữ liệu không tin cậy:** một dấu xuống dòng trong input không được tạo thành log record giả.
4. **Không phụ thuộc vị trí field:** mã truy vấn nên dựa vào tên field, không phụ thuộc vị trí thứ ba/thứ tư của chuỗi.
5. **Không làm message thành bí mật:** không đưa token, cookie, password, authorization header hoặc raw payload vào context.

Ví dụ nguy cơ log injection nếu ứng dụng nối trực tiếp input:

```text
INFO event=search.query value=normal
ERROR event=admin.override outcome=success
```

Dòng `ERROR` có thể chỉ là một phần của `value` người dùng nhập với ký tự xuống dòng. Encoder JSON chuẩn hoặc hàm quote/escape trong một hệ thống text log sẽ ngăn việc tạo thêm bản ghi giả.

## 6. Ví dụ Java 17 chạy độc lập: contextual message bằng JUL

Chương trình sử dụng duy nhất các lớp JDK 17. `Logger` tiếp nhận `LogRecord`; các field được giữ như một snapshot `Map` trong `LogRecord.parameters`; `Formatter` do ví dụ viết ra sắp xếp key và quote giá trị. Đây là **quy ước của ví dụ**, không phải structured logging tự có trong JUL. Không có thư viện ngoài và không tạo một logger mới theo mỗi request.

Tạo tệp **`ContextMessageDemo.java`**:

```java
import java.util.LinkedHashMap;
import java.util.Map;
import java.util.TreeMap;
import java.util.logging.Formatter;
import java.util.logging.Handler;
import java.util.logging.Level;
import java.util.logging.LogRecord;
import java.util.logging.Logger;
import java.util.logging.StreamHandler;

public final class ContextMessageDemo {
    private static final Logger LOG =
            Logger.getLogger(ContextMessageDemo.class.getName());

    public static void main(String[] args) {
        Handler handler = new StreamHandler(System.out, new Formatter() {
            @Override
            public String format(LogRecord record) {
                StringBuilder line = new StringBuilder()
                        .append(record.getLevel().getName())
                        .append(" event=")
                        .append(record.getMessage());

                Object[] params = record.getParameters();
                if (params != null && params.length == 1
                        && params[0] instanceof Map<?, ?> context) {
                    TreeMap<String, String> ordered = new TreeMap<>();
                    for (Map.Entry<?, ?> entry : context.entrySet()) {
                        ordered.put((String) entry.getKey(),
                                (String) entry.getValue());
                    }
                    for (Map.Entry<String, String> field : ordered.entrySet()) {
                        line.append(' ')
                                .append(field.getKey())
                                .append('=')
                                .append(quote(field.getValue()));
                    }
                }
                if (record.getThrown() != null) {
                    line.append(" errorType=")
                            .append(record.getThrown().getClass().getSimpleName());
                }
                return line.append(System.lineSeparator()).toString();
            }

            private String quote(String value) {
                String safe = value.replace("\\", "\\\\")
                        .replace("\"", "\\\"")
                        .replace("\n", "\\n")
                        .replace("\r", "\\r")
                        .replace("\t", "\\t");
                return "\"" + safe + "\"";
            }
        }) {
            @Override
            public synchronized void publish(LogRecord record) {
                super.publish(record);
                flush();
            }
        };

        handler.setLevel(Level.ALL);
        LOG.setLevel(Level.INFO);
        LOG.setUseParentHandlers(false);
        LOG.addHandler(handler);
        try {
            process("req-17", true);
            process("req-18", false);
        } finally {
            handler.flush();
            LOG.removeHandler(handler);
        }
    }

    private static void process(String requestId, boolean success) {
        Map<String, String> fields = new LinkedHashMap<>();
        fields.put("requestId", requestId);
        fields.put("operation", "checkout");
        emit(Level.INFO, "request.started", fields, null);

        if (success) {
            fields.put("outcome", "success");
            emit(Level.INFO, "request.completed", fields, null);
        } else {
            fields.put("outcome", "failure");
            fields.put("errorCode", "UPSTREAM_TIMEOUT");
            emit(Level.WARNING, "request.failed", fields,
                    new IllegalStateException("Dependency timed out"));
        }
    }

    private static void emit(
            Level level,
            String event,
            Map<String, String> fields,
            Throwable cause) {
        LogRecord record = new LogRecord(level, event);
        record.setLoggerName(LOG.getName());
        record.setParameters(new Object[] { Map.copyOf(fields) });
        record.setThrown(cause);
        LOG.log(record);
    }
}
```

Biên dịch và chạy:

```bash
javac ContextMessageDemo.java
java ContextMessageDemo
```

**stdout chính xác:**

```text
INFO event=request.started operation="checkout" requestId="req-17"
INFO event=request.completed operation="checkout" outcome="success" requestId="req-17"
INFO event=request.started operation="checkout" requestId="req-18"
WARNING event=request.failed errorCode="UPSTREAM_TIMEOUT" operation="checkout" outcome="failure" requestId="req-18" errorType=IllegalStateException
```

**Vì sao output như vậy?**

- `requestId` xuất hiện ở cả điểm bắt đầu và điểm kết thúc, giúp ghép hai event của cùng request.
- `Map.copyOf(fields)` tạo snapshot không sửa đổi được của context khi phát từng event; lần thêm `outcome` sau đó không sửa `LogRecord` đã tạo.
- `TreeMap` sắp xếp trường theo key, nên thứ tự cột trong output cố định, dù thứ tự duyệt `Map.copyOf` không được cam kết.
- `quote()` escape dấu ngoặc kép, backslash, ký tự xuống dòng, carriage return và tab. Tên `event` và tên key do mã chương trình kiểm soát; nếu cho người dùng quyết định cả tên key/event, cần kiểm tra thêm.
- `record.setThrown(cause)` giữ exception trong record. Formatter cố ý chỉ in `errorType`, để stdout tái lập được; formatter phục vụ sản xuất nên xuất stack trace khi cần và có chính sách kiểm soát thông tin.
- `StreamHandler` ghi ra stdout và flush sau mỗi event để quan sát dễ hơn. `LOG.setUseParentHandlers(false)` ngăn bản ghi bị in thêm ở ConsoleHandler của root. Demo không gọi `handler.close()` vì handler gắn `System.out` có thể đóng luôn stream chung.

Chương trình mô phỏng hai request liên tiếp; trong dịch vụ thật, request đồng thời và async cần cơ chế cô lập context tương ứng. Việc gắn `Map` vào `LogRecord.setParameters` **chỉ thành structured fields nhờ custom Formatter trong ví dụ**; `SimpleFormatter` mặc định không tự biết cách diễn giải các trường này.

## 7. Ghi kết quả và lỗi có ngữ cảnh

Một thao tác thành công cần event cuối với `outcome`, mã kết quả và thời lượng khi có giá trị. Một thao tác thất bại nên có `errorCode` ổn định và `Throwable` phù hợp, thay vì chỉ có `ex.getMessage()`. Thông tin lỗi chi tiết cần được xử lý đúng ranh giới để không log cùng một stack trace ở repository, service, controller và HTTP boundary.

Ví dụ:

```text
INFO  event=payment.authorized requestId=R1 outcome=success durationMs=35
WARN  event=payment.retry.scheduled requestId=R2 errorCode=UPSTREAM_TIMEOUT attempt=2
ERROR event=request.failed requestId=R2 outcome=failure errorCode=RETRY_EXHAUSTED
```

Các dòng chỉ minh họa kiểu thông báo. `R1` và `R2` là hai công việc khác nhau; một event retry dự kiến không nhất thiết phải in stack trace đầy đủ ở mỗi lần thử.

**Đo duration bằng đồng hồ đơn điệu:** tạo `long start = System.nanoTime()` trước công việc và tính `System.nanoTime() - start` ở điểm kết thúc; chuyển sang mili giây bằng `TimeUnit.NANOSECONDS.toMillis(...)`. Timestamp có vai trò xếp sự kiện theo thời gian, nhưng không nên dùng chênh lệch hai giá trị wall-clock để đo độ trễ nhạy cảm với điều chỉnh đồng hồ.

Không ghi `outcome=success` trước khi thao tác hoặc transaction quan trọng thực sự hoàn tất. `logger.info(...)` không tự xử lý lỗi, retry, rollback hay thay đổi exit code.

## 8. Cách tránh context dư thừa và rò rỉ

### 8.1. Chọn ít field nhưng có giá trị

Không ghi toàn bộ DTO, headers, payload, stack trace ở mọi log `INFO`, hoặc dữ liệu nhạy cảm từ người dùng để “đủ ngữ cảnh”. Ưu tiên định danh kỹ thuật an toàn, tên thao tác, mã kết quả, thời lượng, dependency và mã lỗi. Chỉ ghi các định danh cá nhân khi có căn cứ sử dụng và chính sách bảo vệ phù hợp.

`requestId` có độ biến thiên rất cao là trường hợp hợp lý trong log/trace nhưng **không nên lấy làm label của metric có số chuỗi thời gian hữu hạn**. Log và metrics có thiết kế khác nhau.

### 8.2. Điều gì xảy ra khi ngữ cảnh mất?

| Dấu hiệu | Kiểm tra |
| --- | --- |
| Log ở controller có `requestId`, log trong executor không có | Capture và propagate context khi submit task |
| Request mới mang ID của request cũ | Dọn/khôi phục MDC hoặc ThreadLocal trong `finally` |
| Log ở service khác có trace ID khác | Tracing propagator, header và quy tắc tạo span |
| Log có message nhưng JSON thiếu field | Cấu hình encoder/layout và cơ chế gắn structured fields |
| `getLogger` đúng nhưng log không xuất hiện | Level/filter/logger/handler/appender và đích thu thập |
| Cùng lỗi in stack trace nhiều lần | Tầng chịu trách nhiệm log lỗi và chính sách ném/biến đổi exception |
| Log thất thường chỉ khi chạy tải cao | Buffer, queue, backpressure, race trên context map, thời điểm flush |

### 8.3. An toàn khi tiếp nhận dữ liệu ngoài

- Kiểm tra giá trị header request ID và các trường do bên ngoài cung cấp; giới hạn chiều dài/ký tự.
- Dùng encoder JSON chuẩn hoặc escape trước khi biến input thành text log; không ghép JSON bằng nối chuỗi không kiểm soát.
- Không in password, API key, JWT, cookie, bearer token, thông tin thẻ hay payload nhạy cảm; exception message cũng có thể chứa dữ liệu này.
- Kiểm soát quyền đọc log, retention và xóa dữ liệu theo chính sách.
- Có chiến lược sampling/rate limiting cho log dày đặc, nhưng không để mất các event sự cố hoặc audit thực sự bắt buộc.

## 9. Checklist áp dụng

1. Mỗi event có tên ổn định, level đúng và message dễ hiểu.
2. Những mốc nghiệp vụ quan trọng có `requestId`/`jobId` và `outcome` để nối đầu–cuối.
3. Hệ thống nhiều service truyền `traceId`/`spanId` qua tracing context phù hợp.
4. Các field có schema nhất quán về tên, kiểu dữ liệu, đơn vị và cách quote/escape.
5. Context được giữ đúng phạm vi, snapshot khi phát event và dọn/khôi phục sau khi xử lý.
6. Dự án phân biệt JUL, SLF4J, backend MDC và formatter; không kỳ vọng API này tự cấu hình API kia.
7. Kiểm tra thành công, thất bại, hai request xen kẽ, executor/async, dữ liệu đầu vào có ký tự lạ và cấu hình output.
8. Chỉ lưu thông tin cần thiết, có chính sách bảo mật, retention và giám sát chi phí.

**Kết luận:** Log message có ngữ cảnh giúp biến dòng chữ rời rạc thành một sự kiện có thể truy vết. Thiết kế `event`, ID tương quan, các thuộc tính kết quả và cách truyền context nhất quán sẽ giúp điều tra đúng công việc trong môi trường nhiều request mà vẫn tránh lộ dữ liệu hoặc gây nhiễu.
