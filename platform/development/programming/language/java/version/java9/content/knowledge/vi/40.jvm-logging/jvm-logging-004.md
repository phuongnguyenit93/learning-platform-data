# Thông tin bổ sung về thời gian, luồng và tiến trình trong log JVM

Một log event như “request completed” thường chưa đủ để điều tra sự cố. Khi nhiều request chạy đồng thời, nhiều JVM cùng phục vụ một hệ thống hoặc log được xử lý bất đồng bộ, cần biết **sự kiện xảy ra lúc nào, trong process nào, trên thread nào và thuộc request/trace nào**.

Trong Java, `java.util.logging` (JUL) cung cấp `LogRecord` để mang metadata của log event. `ProcessHandle` cung cấp thông tin tiến trình hệ điều hành. Từ các API này, ứng dụng có thể xây dựng formatter hoặc structured log chứa timestamp, process ID, thread name, thread ID, logger, level, source và correlation ID.

Bài viết tập trung vào các API hiện hành trong Java 17+, đồng thời chỉ ra những method cũ đã deprecated để tránh đưa chúng vào code mới.

## 1. Những câu hỏi metadata cần trả lời

Một log event hữu ích thường có các nhóm thông tin sau:

| Nhóm | Trường thường ghi | Mục đích |
| --- | --- | --- |
| Thời gian | `timestamp` | Xác định thời điểm sự kiện được ghi nhận |
| Process | `pid` | Phân biệt các JVM/process trên cùng máy |
| Thread | `thread.name`, `thread.id` | Xác định luồng phát sinh log |
| Logger | `logger`, `level` | Xác định thành phần và mức độ |
| Source | `class`, `method` | Xác định vị trí phát sinh sự kiện |
| Request context | `requestId`, `traceId` | Liên kết nhiều log event thuộc cùng một request/trace |
| Event identity | `sequence` | Hỗ trợ phân biệt các record trong một JVM |

Không phải mọi ứng dụng đều cần mọi trường. Hãy chọn metadata theo cách vận hành và yêu cầu điều tra sự cố; tránh ghi dữ liệu nhạy cảm hoặc thông tin không phục vụ chẩn đoán.

## 2. Thời gian của một log event

### `LogRecord.getInstant()` 
Từ Java 9, `LogRecord` biểu diễn thời điểm sự kiện bằng `java.time.Instant`. Constructor của record tự khởi tạo instant hiện tại theo clock tốt nhất mà hệ thống cung cấp. Có thể đọc bằng:

~~~java
Instant eventTime = record.getInstant();
String timestamp = DateTimeFormatter.ISO_INSTANT.format(eventTime);
~~~

`Instant` biểu diễn một điểm trên timeline theo UTC và hỗ trợ độ phân giải nano giây. Độ phân giải biểu diễn không đồng nghĩa clock phần cứng luôn chính xác đến nano giây; độ chính xác thực tế phụ thuộc hệ điều hành và clock của máy.

Nên ghi timestamp ở dạng ISO-8601 UTC, ví dụ:

~~~text
2026-11-06T10:15:30.123456789Z
~~~

Dùng UTC giúp đối chiếu log từ các máy có timezone khác nhau. Nếu giao diện cần giờ địa phương, chuyển đổi khi hiển thị thay vì lưu timestamp không kèm timezone.

### Event time khác thời điểm formatter xử lý

Một handler có thể xử lý record muộn hơn thời điểm logger tạo record, nhất là khi ghi log bất đồng bộ. `getInstant()` là thời điểm gắn với record; formatter không nên thay nó bằng `Instant.now()` tại lúc format vì như vậy timestamp sẽ phản ánh thời gian xử lý log thay vì thời gian sự kiện.

### Đo thời lượng bằng `System.nanoTime()`

Timestamp lịch là clock thời gian thực và có thể được điều chỉnh. Không dùng phép trừ hai Instant hoặc hai giá trị epoch để đo timeout hay thời lượng chính xác trong cùng process.

Để đo elapsed time, dùng `System.nanoTime()`:

~~~java
long started = System.nanoTime();
performOperation();
long elapsedNanos = System.nanoTime() - started;
long elapsedMillis = TimeUnit.NANOSECONDS.toMillis(elapsedNanos);
~~~

`nanoTime()` là nguồn đo khoảng thời gian tương đối, không phải timestamp để đưa vào log như giờ/ngày. Có thể ghi cả `timestamp` và `durationNanos` nếu cần biết sự kiện xảy ra khi nào và thao tác kéo dài bao lâu.

## 3. Thread name và thread ID

### Tên thread

Tên thread lấy từ:

~~~java
String threadName = Thread.currentThread().getName();
~~~

Tên dễ đọc giúp nhận ra các nhóm công việc như `http-worker-3`, `scheduler-1` hoặc `request-worker-1`. Có thể đặt tên trong `ThreadFactory` khi tạo executor:

~~~java
ThreadFactory factory = task -> new Thread(task, "request-worker-1");
ExecutorService executor = Executors.newFixedThreadPool(4, factory);
~~~

Tên thread là nhãn phục vụ quan sát. Nó có thể bị thay đổi, trùng nhau hoặc được runtime đặt mặc định; không dùng tên thread làm định danh duy nhất cho request.

### Thread ID trong LogRecord

`LogRecord.getLongThreadID()` trả về thread ID dạng `long` của thread nơi log message phát sinh. API này có từ Java 16 và phù hợp hơn cho code hiện hành:

~~~java
long threadId = record.getLongThreadID();
~~~

Thread ID này thuộc JVM; nó không nhất thiết là native thread ID mà hệ điều hành hiển thị. ID cũng không thay thế request ID hoặc trace ID.

`LogRecord.getThreadID()` và `setThreadID(int)` đã deprecated từ Java 16. Giá trị `int` cũ có thể được tổng hợp và không nhất thiết tương ứng với ID thread thực; code mới nên dùng `getLongThreadID()` và `setLongThreadID(long)`.

### Thread ID trực tiếp từ Thread

Trên Java 17, `Thread.getId()` vẫn có thể gặp trong code cũ. Từ Java 19, API này deprecated và được thay bằng `Thread.threadId()`:

~~~java
// Java 19+
long id = Thread.currentThread().threadId();
~~~

Nếu đang format JUL record, `getLongThreadID()` là lựa chọn trực tiếp vì ID đã được record ghi nhận tại thời điểm tạo.

### Virtual threads

Trên Java 21+, virtual threads có thể được dùng cho nhiều tác vụ đồng thời. Không giả định một request luôn gắn với một platform thread cố định hoặc một thread name duy nhất. Hãy ghi request/trace ID như metadata riêng; thread name và thread ID chỉ bổ sung thông tin thực thi tại thời điểm log được tạo.

## 4. Process ID và thông tin tiến trình

`ProcessHandle` được bổ sung từ Java 9 để nhận diện và truy vấn native process. Lấy PID của JVM hiện tại bằng:

~~~java
long pid = ProcessHandle.current().pid();
~~~

PID là số do hệ điều hành cấp cho process. Đây là metadata hữu ích khi một máy chạy nhiều JVM, nhiều worker process hoặc nhiều instance của cùng một service.

PID có thể được hệ điều hành tái sử dụng sau khi process kết thúc. Nếu cần phân biệt một process qua nhiều lần khởi động, kết hợp PID với thời điểm khởi chạy khi thông tin đó có sẵn.

### ProcessHandle.Info

Có thể đọc snapshot thông tin tiến trình:

~~~java
ProcessHandle handle = ProcessHandle.current();
ProcessHandle.Info info = handle.info();

long pid = handle.pid();
Optional<Instant> startedAt = info.startInstant();
Optional<String> command = info.command();
Optional<String> user = info.user();
~~~

Các trường của `ProcessHandle.Info` trả về `Optional` vì hệ điều hành hoặc quyền truy cập có thể không cung cấp thông tin. Luôn xử lý trường hợp rỗng; không giả định mọi nền tảng đều trả được command, user, arguments hoặc start time.

Ví dụ format an toàn:

~~~java
String processStart = ProcessHandle.current().info()
        .startInstant()
        .map(DateTimeFormatter.ISO_INSTANT::format)
        .orElse("unavailable");
~~~

Không cần gọi `ProcessHandle.allProcesses()` để ghi PID của chính JVM. Phương thức đó tạo snapshot các process nhìn thấy được và có thể chịu giới hạn quyền của hệ điều hành.

### Thông tin process có thể nhạy cảm

`commandLine()`, `arguments()`, đường dẫn executable và tên user có thể chứa dữ liệu nhạy cảm. Không đưa toàn bộ command line vào log mặc định; tham số khởi chạy đôi khi chứa token, mật khẩu hoặc thông tin môi trường. Chỉ thu thập khi có nhu cầu vận hành rõ ràng, có kiểm soát quyền truy cập và chính sách lưu giữ phù hợp.

## 5. Metadata có sẵn trong JUL LogRecord

`java.util.logging.LogRecord` mang nhiều trường hữu ích:

| API | Thông tin |
| --- | --- |
| `getInstant()` | Thời điểm event |
| `getLongThreadID()` | Thread ID dạng long |
| `getSequenceNumber()` | Sequence number được cấp trong JVM |
| `getLoggerName()` | Tên logger |
| `getLevel()` | Mức log |
| `getSourceClassName()` | Tên class nguồn |
| `getSourceMethodName()` | Tên method nguồn |
| `getMessage()`, `getParameters()` | Message và tham số |
| `getThrown()` | Exception/Throwable đi kèm |

Sequence number thường tăng khi các `LogRecord` được tạo trong cùng một VM. Nó hữu ích để phân biệt record, nhưng không phải sequence toàn cục, không thể so sánh trực tiếp giữa nhiều process và không bảo đảm thứ tự handler ghi ra khi xử lý bất đồng bộ.

`getMillis()` chỉ trả timestamp đã cắt xuống mili giây; khi cần đầy đủ độ phân giải hãy dùng `getInstant()`. `setMillis(long)` đã deprecated; dùng `setInstant(Instant)` khi cần gán thời điểm cho record.

Nếu không đặt source class/method tường minh, `LogRecord` có thể suy ra chúng bằng cách phân tích call stack khi getter được gọi lần đầu. Với handler chuyển record sang thread khác, nên thiết lập source trước khi chuyển giao nếu cần giữ chính xác vị trí phát sinh.

Sau khi đưa record vào logging framework, record thuộc quyền quản lý của framework; không tiếp tục sửa record từ code ứng dụng.

## 6. Chụp metadata tại nơi phát sinh event

Một lỗi thường gặp trong logging bất đồng bộ là lấy thread name bằng `Thread.currentThread()` bên trong formatter chạy ở handler thread. Khi đó log hiển thị thread ghi log, không phải thread phát sinh event.

Hãy chụp context ngay khi tạo record:

- Timestamp từ `LogRecord` hoặc `Instant.now()`.
- Thread ID từ `LogRecord.getLongThreadID()`.
- Thread name từ `Thread.currentThread().getName()`.
- PID từ `ProcessHandle.current().pid()`.
- Request/trace ID từ context nghiệp vụ đã được truyền tới điểm log.

Có thể dùng subclass của `LogRecord` hoặc một structured event object để mang các trường bổ sung. Ví dụ dưới đây dùng subclass để lưu PID, thread name và request ID tại thời điểm tạo record.

## 7. Request ID và trace ID không phải thread ID

Một request có thể đi qua nhiều thread và nhiều process. Một thread có thể xử lý nhiều request theo thời gian. Vì vậy:

- `pid` trả lời log đến từ process nào.
- `thread.id` và `thread.name` trả lời log được phát sinh trên thread nào.
- `requestId` liên kết các event của cùng một request.
- `traceId` liên kết các span hoặc service call trong một distributed trace.

Nếu dùng `ThreadLocal` hoặc MDC của logging framework để lưu context, phải xác định cách context được truyền qua executor, callback và async stage. Context không tự động được bảo đảm truyền qua mọi ranh giới bất đồng bộ. Dùng wrapper/decorator hoặc cơ chế context propagation của framework; luôn xóa context ở nơi tái sử dụng thread để tránh request sau nhận nhầm dữ liệu request trước.

Với virtual threads, `ThreadLocal` có vòng đời gắn với từng thread, nhưng request/trace identity vẫn nên được mô hình hóa tường minh. Không dùng thread ID làm khóa thay thế cho correlation ID.

## 8. Ví dụ hoàn chỉnh: JUL formatter có thời gian, thread và process

Chương trình sau tạo một JUL `LogRecord` trong thread tên `request-worker-1`. Subclass của record chụp PID và thread name ngay tại constructor; `LogRecord` tự lưu thread ID dài. Formatter xuất timestamp, PID, thread, level, logger, request ID và source. Sau đó chương trình in thời điểm khởi chạy process nếu hệ điều hành cung cấp.

Timestamp của record được đặt cố định trong demo để dễ kiểm tra định dạng. Trong ứng dụng thật, có thể giữ instant mặc định do constructor tạo ra.

Tạo tệp `JvmLogContextDemo.java`:

~~~java
import java.lang.ProcessHandle;
import java.time.Instant;
import java.time.format.DateTimeFormatter;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;
import java.util.logging.Formatter;
import java.util.logging.Handler;
import java.util.logging.Level;
import java.util.logging.LogRecord;
import java.util.logging.Logger;

public class JvmLogContextDemo {
    private static final class ContextLogRecord extends LogRecord {
        private static final long serialVersionUID = 1L;

        private final long processId;
        private final String threadName;
        private final String requestId;

        ContextLogRecord(Level level, String message, String requestId) {
            super(level, message);
            this.processId = ProcessHandle.current().pid();
            this.threadName = Thread.currentThread().getName();
            this.requestId = requestId;
            setLoggerName("demo.request");
            setSourceClassName(JvmLogContextDemo.class.getName());
            setSourceMethodName("handleRequest");
        }

        long processId() {
            return processId;
        }

        String threadName() {
            return threadName;
        }

        String requestId() {
            return requestId;
        }
    }

    private static final class MetadataFormatter extends Formatter {
        @Override
        public String format(LogRecord record) {
            ContextLogRecord context = (ContextLogRecord) record;
            return DateTimeFormatter.ISO_INSTANT.format(record.getInstant())
                    + " pid=" + context.processId()
                    + " thread=" + context.threadName()
                    + "[" + record.getLongThreadID() + "]"
                    + " level=" + record.getLevel().getName()
                    + " logger=" + record.getLoggerName()
                    + " requestId=" + context.requestId()
                    + " source=" + record.getSourceClassName()
                    + "#" + record.getSourceMethodName()
                    + " message=" + formatMessage(record)
                    + System.lineSeparator();
        }
    }

    private static final class StdoutHandler extends Handler {
        @Override
        public void publish(LogRecord record) {
            if (isLoggable(record)) {
                System.out.print(getFormatter().format(record));
            }
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
        Logger logger = Logger.getLogger("demo.request");
        logger.setUseParentHandlers(false);
        logger.setLevel(Level.INFO);

        StdoutHandler handler = new StdoutHandler();
        handler.setLevel(Level.ALL);
        handler.setFormatter(new MetadataFormatter());
        logger.addHandler(handler);

        ExecutorService executor = Executors.newSingleThreadExecutor(task -> {
            Thread thread = new Thread(task, "request-worker-1");
            thread.setDaemon(false);
            return thread;
        });

        try {
            Future<?> logged = executor.submit(() -> {
                ContextLogRecord record = new ContextLogRecord(
                        Level.INFO, "request completed", "req-42");
                record.setInstant(
                        Instant.parse("2026-11-06T10:15:30.123456789Z"));
                logger.log(record);
            });
            logged.get(5, TimeUnit.SECONDS);
        } finally {
            executor.shutdown();
            if (!executor.awaitTermination(5, TimeUnit.SECONDS)) {
                executor.shutdownNow();
            }
            logger.removeHandler(handler);
            handler.close();
        }

        ProcessHandle.Info processInfo = ProcessHandle.current().info();
        String processStart = processInfo.startInstant()
                .map(DateTimeFormatter.ISO_INSTANT::format)
                .orElse("unavailable");
        System.out.println("process-start=" + processStart);
    }
}
~~~

Biên dịch và chạy bằng JDK 17 trở lên:

~~~bash
javac --release 17 -Xlint:all JvmLogContextDemo.java
java JvmLogContextDemo
~~~

Kết quả của lần chạy kiểm thử:

~~~text
2026-11-06T10:15:30.123456789Z pid=3520 thread=request-worker-1[36] level=INFO logger=demo.request requestId=req-42 source=JvmLogContextDemo#handleRequest message=request completed
process-start=2026-11-06T16:47:25.651Z
~~~

PID, thread ID và process start time phụ thuộc lần chạy và hệ điều hành; chúng sẽ khác trên máy khác. Timestamp đầu tiên được cố định trong demo. Các trường còn lại được lấy tại runtime.

Điểm quan trọng của ví dụ là thread name và PID được chụp trong constructor `ContextLogRecord`. Nếu thay handler bằng một handler bất đồng bộ, formatter vẫn in context của thread phát sinh event thay vì thread xử lý queue.

## 9. Structured logging

Trong production, nên cân nhắc log dạng structured data, thường là JSON hoặc định dạng key-value ổn định, thay vì chỉ nối chuỗi tự do.

Một event có thể có schema như sau:

~~~json
{
  "timestamp": "2026-11-06T10:15:30.123456789Z",
  "level": "INFO",
  "logger": "demo.request",
  "pid": 3520,
  "thread": {
    "name": "request-worker-1",
    "id": 36
  },
  "requestId": "req-42",
  "message": "request completed"
}
~~~

Ví dụ chỉ minh họa cấu trúc. Trong ứng dụng thật, dùng JSON encoder hoặc logging appender đã được kiểm chứng để escape ký tự, serialize exception và xử lý kiểu dữ liệu đúng chuẩn. Không tự nối chuỗi JSON vì dấu nháy, newline hoặc dữ liệu đầu vào có thể làm hỏng định dạng.

Tên field nên ổn định giữa các service. Ví dụ, thống nhất `timestamp`, `pid`, `thread.name`, `thread.id`, `request.id` và `trace.id` giúp hệ thống log dễ lọc và truy vấn hơn.

## 10. Những lỗi thường gặp

- **Dùng `LogRecord.getThreadID()`**: method đã deprecated từ Java 16; dùng `getLongThreadID()`.
- **Dùng `LogRecord.setMillis(long)`**: đã deprecated; dùng `setInstant(Instant)`.
- **Chỉ ghi millisecond khi cần độ phân giải cao:** dùng `getInstant()` thay cho timestamp đã bị cắt bởi `getMillis()`.
- **Lấy thread name trong async formatter:** có thể ghi nhầm handler thread; chụp tên thread lúc tạo event.
- **Coi thread ID là OS thread ID:** ID trong `LogRecord` thuộc JVM và có thể không ánh xạ trực tiếp tới native thread.
- **Dùng thread ID làm request ID:** một thread có thể xử lý nhiều request; dùng correlation ID riêng.
- **Coi PID là định danh process vĩnh viễn:** hệ điều hành có thể tái sử dụng PID; kết hợp start time khi cần.
- **Giả định `ProcessHandle.Info` luôn có dữ liệu:** các trường là Optional và phụ thuộc nền tảng/quyền truy cập.
- **Ghi toàn bộ command line hoặc arguments:** có thể làm lộ token, mật khẩu hoặc dữ liệu nhạy cảm.
- **Dùng timestamp để đo thời lượng:** dùng `System.nanoTime()` cho elapsed time.
- **Giả định sequence number tạo thứ tự toàn hệ thống:** sequence chỉ có ý nghĩa trong phạm vi VM; distributed tracing cần trace/span ID.
- **Không truyền context qua async boundary:** request ID có thể mất hoặc bị dùng nhầm; thiết kế context propagation rõ ràng.

## 11. Checklist triển khai

1. Ghi event time bằng `Instant`; xuất ISO-8601 UTC.
2. Dùng `System.nanoTime()` cho thời lượng, timeout và latency.
3. Ghi PID bằng `ProcessHandle.current().pid()` khi cần phân biệt JVM.
4. Ghi thread name và `LogRecord.getLongThreadID()` tại nơi phát sinh event.
5. Ghi logger, level, source và exception khi có ích cho chẩn đoán.
6. Thêm request ID/trace ID độc lập với process ID và thread ID.
7. Truyền context rõ ràng qua executor và async stage; không giả định ThreadLocal tự động được truyền.
8. Xử lý `Optional` từ `ProcessHandle.Info` và chấp nhận dữ liệu không có sẵn.
9. Không log command line, credentials hoặc thông tin cá nhân nếu không có mục đích và quyền phù hợp.
10. Dùng formatter hoặc structured encoder nhất quán; giữ nguyên event metadata khi log được xử lý bất đồng bộ.

Thông tin thời gian, thread và process giúp đặt một log event vào đúng bối cảnh thực thi. `LogRecord` cung cấp timestamp và thread ID; `ProcessHandle` cung cấp PID và snapshot thông tin process; ứng dụng bổ sung thread name cùng request/trace context tại nơi phát sinh. Khi phân biệt đúng event time với processing time, thread identity với request identity và PID với process lifetime, log JVM sẽ hữu ích hơn cho việc điều tra lỗi và theo dõi hệ thống nhiều luồng, nhiều process.