# Đóng file khi shutdown trong Java Logging

## 1. Tại sao cần đóng file logging đúng cách?

Một ứng dụng Java ghi log ra file có thể giữ **file descriptor**, **output stream**, **buffer**, **file lock** và đôi khi **queue logging bất đồng bộ**. Khi chương trình dừng, mục tiêu không chỉ là thoát khỏi JVM, mà còn hoàn tất những bản ghi quan trọng còn đang được xử lý, giải phóng tài nguyên và tránh đóng file trong lúc các luồng khác vẫn ghi log.

**Đóng file khi shutdown** là việc kết thúc vòng đời tài nguyên logging ở đúng thời điểm: dừng nguồn tạo log, xử lý dữ liệu đang chờ, ghi event kết thúc hợp lý, **flush và close** Handler/Appender do ứng dụng sở hữu. Nếu dừng đột ngột, các bước này có thể không kịp chạy.

Sau bài học, bạn sẽ biết:

- Phân biệt **publish**, **flush**, **close**, **stop logging context** và **shutdown hook**.
- Sử dụng **java.util.logging.FileHandler** đúng lifecycle, quản lý file lock và rotation.
- Dừng các worker trước khi đóng file logging, tránh race giữa producer và Handler.
- Viết chương trình Java 17 có hai cách đóng FileHandler: **try/finally** và **Runtime.addShutdownHook**.
- Chạy ví dụ và đối chiếu chính xác stdout, nội dung file log và sự tồn tại của file khóa.
- Hiểu trường hợp hook không thể hoạt động: **SIGKILL**, **Runtime.halt**, JVM crash, mất điện, deadline của container.
- Phân biệt shutdown JUL, Log4j2, Logback và pipeline logging bất đồng bộ.
- Hiểu vì sao **flush/close** không phải bằng chứng dữ liệu được lưu bền vững cho audit.

**Phạm vi:** Đây là bài thuộc nhóm **File logging** trong **Java Core Logging**. Ví dụ hoàn chỉnh dùng JUL tích hợp trong JDK; không cần Maven hoặc thư viện ngoài. Các logging backend khác được đề cập để giúp chọn đúng API lifecycle.

## 2. Một dòng log đi tới file bằng cách nào?

Đường đi đơn giản:

~~~text
Java business code
    |
    | logger.info("event=order.created")
    v
Logger -> LogRecord
    |
    v
Handler / Appender -> Formatter / Layout
    |
    v
File output stream / buffers
    |
    v
Operating system / filesystem
~~~

Với logging bất đồng bộ:

~~~text
Business thread
    |
    v
Async queue / ring buffer
    |
    v
Background logging consumer
    |
    v
File Appender -> stream -> filesystem
~~~

Trong trường hợp bất đồng bộ, lời gọi Logger có thể trả về khi record **mới được đưa vào queue**. Trong trường hợp đồng bộ, lời gọi có thể hoàn tất sau khi Handler xử lý record nhưng dữ liệu vẫn có thể nằm trong OS page cache.

**Đừng đồng nhất một lệnh logger.info trả về với dữ liệu đã được lưu bền vững.** Độ bền phụ thuộc queue, policy của logging backend, stream, hệ điều hành, filesystem và storage.

### 2.1. publish, flush và close

| Thao tác | Vai trò | Có đóng file? |
| --- | --- | --- |
| **publish(record)** | Nhận và xử lý một sự kiện | Không mặc định |
| **flush()** | Đẩy dữ liệu đang được Handler/stream buffer sang tầng tiếp theo | Không |
| **close()** | Kết thúc stream/handler và giải phóng tài nguyên | Có với FileHandler |
| **Stop logging context** | Dừng backend, có thể drain async queue và close nhiều Appender | Tùy backend |
| **fsync/force** | Yêu cầu đồng bộ dữ liệu ở tầng file/storage theo API cụ thể | Khác flush |

**flush không phải fsync.** Dù file được flush và close, dữ liệu vẫn có thể ở cache của OS hoặc tầng lưu trữ; không có lời hứa chống mất điện tuyệt đối. Bởi vậy, một file log thông thường không nên là nguồn dữ liệu duy nhất khi hệ thống cần bảo đảm audit.

## 3. FileHandler trong Java Util Logging

JDK có **java.util.logging.FileHandler**, kế thừa **StreamHandler**. Nó hỗ trợ ghi một file hoặc các file quay vòng theo pattern/limit/count.

Theo tài liệu Java 17:
- FileHandler có phương thức **publish** và **close**, đồng thời kế thừa **flush**.
- Mỗi record hoàn thành được FileHandler flush theo hợp đồng của implementation, nhưng không tương đương fsync.
- Formatter mặc định là **XMLFormatter**, nếu cấu hình không thay đổi.
- Các cấu hình gồm pattern, append, limit, count, level, filter, encoding và formatter.
- FileHandler có cơ chế khóa file để phối hợp tài nguyên đang mở.
- **FileHandler.close()** đóng những file mà Handler quản lý.

Ví dụ mảnh code nằm trong một method:

~~~java
import java.util.logging.FileHandler;
import java.util.logging.Logger;

Logger logger = Logger.getLogger("demo.file");
FileHandler handler = new FileHandler("logs/app.log", true);
logger.addHandler(handler);
~~~

Đây **không phải chương trình độc lập**. Nó cần thư mục logs có quyền ghi. Tham số true của constructor yêu cầu append theo cơ chế FileHandler, không có nghĩa nhiều JVM có thể ghi chung một file một cách hoàn toàn an toàn mà không phối hợp.

### 3.1. Ai phải đóng FileHandler?

Cần phân biệt hai nguồn tạo Handler:

1. **Ứng dụng tự tạo** bằng new FileHandler và tự gắn Logger: owner của ứng dụng phải quản lý remove/flush/close.
2. **LogManager/framework tự tạo** qua logging.properties hoặc cấu hình runtime: lifecycle có thể do LogManager hoặc framework quản lý.

Đừng đóng Handler dùng chung ở cuối mỗi request hoặc trong một thư viện không sở hữu logging context.

### 3.2. Mẫu đóng Handler riêng

Khi ứng dụng tự sở hữu Handler, sau khi các luồng phát log đã dừng:

~~~java
logger.removeHandler(handler);
try {
    handler.flush();
} finally {
    handler.close();
}
~~~

Đây là mảnh code minh họa; giả định logger và handler đã được tạo. **removeHandler** ngăn Logger gửi thêm event tới Handler theo đường gắn trực tiếp, nhưng **không tự động đợi mọi producer đang publish**. Phải điều phối producer/consumer ở tầng application.

### 3.3. Logger OFF khác FileHandler.close

~~~java
logger.setLevel(java.util.logging.Level.OFF);
~~~

Đặt Logger OFF chỉ chặn những sự kiện thông thường theo level. Nó **không giải phóng file descriptor, không xóa file lock, không drain queue và không thay close()**. Để dừng tài nguyên, đóng Handler hoặc logging context đúng API.

## 4. Thứ tự dừng một service ghi log ra file

Một graceful shutdown có chủ đích thường diễn ra như sau:

~~~text
Stop signal / application lifecycle
             |
             v
Ngừng nhận request hoặc job mới
             |
             v
Ngừng scheduler và nguồn tạo tác vụ
             |
             v
Đợi request/worker đang chạy kết thúc trong deadline
             |
             v
Ghi event kết thúc có ý nghĩa
             |
             v
Drain hàng đợi logging async nếu có
             |
             v
Flush và close FileHandler / stop backend
             |
             v
Giải phóng các tài nguyên còn lại và thoát JVM
~~~

Trong một ứng dụng thực tế, thứ tự database/network/worker còn tùy dependency giữa các service. Nhưng **nếu component vẫn có thể phát log thì không nên đóng backend trước component đó**.

Ví dụ trường hợp sai:

~~~text
T0: Shutdown hook đóng FileHandler
T1: Worker chưa hoàn tất payment
T2: Worker log event=payment.failed
T3: FileHandler đã đóng; event không còn đích cũ
~~~

Thứ tự tốt hơn là:
- Ngừng tiếp nhận payment mới.
- Đợi các payment đang chạy hoàn tất hoặc bị hủy có kiểm soát.
- Ghi event tổng kết công việc.
- Đóng logging sau các event cần thiết.

### 4.1. Shutdown deadline

Graceful shutdown không có nghĩa chờ vô hạn. Nếu executor không dừng trước deadline, ứng dụng cần policy rõ ràng: báo tình trạng, yêu cầu hủy bằng interrupt, chờ tiếp có giới hạn hoặc chấp nhận rủi ro mất event.

Ví dụ minh họa với ExecutorService:

~~~java
executor.shutdown();
if (!executor.awaitTermination(10, java.util.concurrent.TimeUnit.SECONDS)) {
    executor.shutdownNow();
}
logger.info("event=executor.shutdown_requested");
~~~

Đoạn này không độc lập: cần executor, logger và xử lý InterruptedException. Quan trọng là **shutdownNow không bảo đảm mọi task đã dừng ngay**. Không suy ra an toàn để đóng file ngay sau shutdownNow khi vẫn còn worker có thể ghi log.

## 5. JVM shutdown hook hoạt động ra sao?

Java cung cấp **Runtime.addShutdownHook(Thread)** để đăng ký một thread chạy khi JVM bắt đầu shutdown bình thường.

Ví dụ minh họa:

~~~java
Runtime.getRuntime().addShutdownHook(
    new Thread(() -> cleanupResources(), "cleanup-hook"));
~~~

Đoạn code này cần một hàm cleanupResources hợp lệ; không phải chương trình độc lập.

Theo tài liệu Oracle Java 17:
- Các hook được chạy theo **thứ tự không được bảo đảm**.
- Chúng có thể chạy **đồng thời**.
- Hook nên ngắn, thread-safe và tránh deadlock.
- Không nên phụ thuộc mù quáng vào các service cũng có hook riêng.
- Khi JVM bắt đầu shutdown, không thể tùy tiện đăng ký hoặc gỡ thêm hooks.

**Shutdown hook không thay thế orderly shutdown.** Nó chỉ là lớp dọn dẹp dự phòng. Nếu framework đã sở hữu logging backend và có cơ chế shutdown riêng, việc thêm hook có thể khiến hai bên cùng đóng tài nguyên.

### 5.1. Các kiểu kết thúc JVM

| Tình huống | Điều cần lưu ý |
| --- | --- |
| main hoàn tất và không còn non-daemon threads | JVM có thể thực hiện shutdown sequence và hooks |
| System.exit(...) | Khởi động shutdown sequence |
| Ctrl+C / tín hiệu được JVM xử lý | Có thể kích hoạt hooks, tùy OS/JVM |
| Framework lifecycle stop | Có thể dừng backend qua lifecycle riêng |
| SIGTERM trong container | Có thể graceful nếu process nhận được và còn thời gian |
| SIGKILL / TerminateProcess | Không đảm bảo hook được chạy |
| Runtime.getRuntime().halt(...) | Bỏ qua shutdown thông thường |
| JVM crash / mất điện | Không đảm bảo cleanup |
| Container bị force kill sau grace period | Không đảm bảo queue hoặc hook hoàn tất |

Không nói “hook luôn chạy”. Với force termination hoặc JVM abort, Oracle nêu rõ **không có bảo đảm shutdown hooks được thực hiện**.

### 5.2. Có nên log từ shutdown hook?

Không nên dựa vào event log trong hook như bằng chứng ứng dụng đã dừng thành công. JUL LogManager, Log4j2 hoặc framework cũng có thể có shutdown hook đang đóng Handler/Appender cùng lúc. Vì thứ tự giữa các hook không được đảm bảo, câu logger.info cuối có thể mất.

Nên **phát event app.stopping trong graceful lifecycle** khi logging còn hoạt động; hook chỉ là phương án cleanup những tài nguyên chưa được đóng.

### 5.3. Idempotent close

Ứng dụng có thể đóng Handler trong finally, rồi hook vẫn được gọi khi JVM kết thúc. Một **AtomicBoolean** giúp nhánh đóng do ứng dụng điều khiển không tự thực hiện lại:

~~~java
if (!CLOSED.compareAndSet(false, true)) {
    return;
}
handler.flush();
handler.close();
~~~

Đây là đoạn minh họa trong phương thức đã có CLOSED/handler. AtomicBoolean **không thay cơ chế ngăn các thread khác đang ghi log**; nó chỉ tránh thực hiện logic đóng lặp từ hai đường cleanup của owner.

## 6. Ví dụ Java 17+ hoàn chỉnh

Chương trình này sử dụng JUL FileHandler và có hai chế độ:

1. Chế độ mặc định: ghi các event rồi đóng file trong finally.
2. Chế độ **--hook**: return khỏi main; JVM chạy shutdown hook dự phòng.
3. File log nằm trong **demo-logs/shutdown-demo.log**.
4. Đầu ra Formatter có dạng **LEVEL|message**, không phụ thuộc timestamp.

**Đây là mã chạy được trên Java 17+, không cần Maven, Gradle hoặc thư viện ngoài.**

### 6.1. ShutdownFileLoggingDemo.java

~~~java
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.logging.FileHandler;
import java.util.logging.Formatter;
import java.util.logging.Level;
import java.util.logging.LogRecord;
import java.util.logging.Logger;

public final class ShutdownFileLoggingDemo {
    private static final Logger LOG = Logger.getLogger("demo.file.shutdown");
    private static final AtomicBoolean CLOSED = new AtomicBoolean();

    public static void main(String[] args) throws Exception {
        Path logPath = Path.of("demo-logs", "shutdown-demo.log");
        Files.createDirectories(logPath.getParent());

        FileHandler file = new FileHandler(logPath.toString(), false);
        file.setEncoding(StandardCharsets.UTF_8.name());
        file.setLevel(Level.INFO);
        file.setFormatter(new Formatter() {
            @Override
            public String format(LogRecord record) {
                return record.getLevel().getName() + "|" + formatMessage(record)
                        + System.lineSeparator();
            }
        });

        LOG.setUseParentHandlers(false);
        LOG.setLevel(Level.INFO);
        LOG.addHandler(file);

        Runtime.getRuntime().addShutdownHook(new Thread(() -> {
            closeOnce(file);
            System.out.println("hook=completed");
        }, "file-log-shutdown"));

        if (args.length > 0 && "--hook".equals(args[0])) {
            LOG.info("event=app.started");
            LOG.warning("event=app.hook_mode");
            System.out.println("mode=hook");
            return;
        }

        try {
            LOG.info("event=app.started");
            LOG.info("event=task.completed");
            LOG.info("event=app.stopping");
        } finally {
            closeOnce(file);
        }
        System.out.println("mode=explicit;handlerClosed=" + CLOSED.get());
    }

    private static void closeOnce(FileHandler file) {
        if (!CLOSED.compareAndSet(false, true)) {
            return;
        }
        LOG.removeHandler(file);
        try {
            file.flush();
        } finally {
            file.close();
        }
    }
}
~~~

### 6.2. Biên dịch và chạy

~~~bash
javac --release 17 -encoding UTF-8 ShutdownFileLoggingDemo.java
java ShutdownFileLoggingDemo
~~~

**stdout thực tế của chế độ mặc định, đã kiểm chứng:**

~~~text
mode=explicit;handlerClosed=true
hook=completed
~~~

**Nội dung file demo-logs/shutdown-demo.log:**

~~~text
INFO|event=app.started
INFO|event=task.completed
INFO|event=app.stopping
~~~

Giải thích:
- FileHandler mở một file trong demo-logs.
- Logger phát ba event.
- Khối finally gọi closeOnce, tháo Handler, flush và close trước khi main kết thúc.
- Dòng handlerClosed=true thể hiện nhánh cleanup của ứng dụng đã chạy.
- Khi JVM shutdown, hook vẫn được gọi, nhưng AtomicBoolean giúp không thực hiện lại closeOnce.
- Dòng hook=completed dùng **System.out.println** để chứng minh hook chạy trong ví dụ, **không phải nội dung file logging**.

### 6.3. Chạy chế độ hook

~~~bash
java ShutdownFileLoggingDemo --hook
~~~

**stdout đã kiểm chứng:**

~~~text
mode=hook
hook=completed
~~~

**File log sau khi tiến trình thoát:**

~~~text
INFO|event=app.started
WARNING|event=app.hook_mode
~~~

Ở chế độ này main return mà không gọi closeOnce tường minh. Hook được JVM gọi trong shutdown bình thường. Tuy nhiên **JUL LogManager cũng có cơ chế dọn Handler khi JVM shutdown**; việc quan sát file đã đóng không phải bằng chứng rằng hook do ứng dụng viết là thành phần duy nhất đóng file trong mọi môi trường.

### 6.4. Kiểm tra file khóa

Trong lần chạy kiểm thử, sau khi Java process kết thúc, **shutdown-demo.log.lck** không còn ở cả hai chế độ. Điều đó phù hợp với việc FileHandler không còn giữ lock của phiên chạy trong môi trường thử nghiệm. Không suy rộng rằng mọi OS và filesystem đều luôn tạo/xóa cùng loại file khóa.

**Windows PowerShell:**

~~~powershell
Get-Content .\demo-logs\shutdown-demo.log -Encoding UTF8
Get-ChildItem .\demo-logs
~~~

**Linux/macOS:**

~~~bash
cat demo-logs/shutdown-demo.log
ls -la demo-logs/
~~~

**Lưu ý về append=false:** Bài demo dùng new FileHandler(path, false) để file có nội dung xác định, nên lần chạy tiếp theo có thể thay nội dung của lần trước. Không sử dụng chính sách này cho file production cần giữ lịch sử.

### 6.5. Vì sao demo không giải quyết tất cả vấn đề production?

Đây là ví dụ đơn luồng. Trong server đa luồng, phải dừng producer trước khi đóng. Ngoài ra, hook chỉ là fallback. Nếu JVM bị force kill, việc JVM chưa hoàn tất close hoặc stdout không kịp được thu thập là điều có thể xảy ra.

## 7. Đóng file trong ứng dụng đa luồng

Giả sử có một ExecutorService cùng ghi qua Logger đã gắn FileHandler. Nếu gọi close trong lúc executor còn tác vụ, worker có thể tiếp tục phát log.

Thứ tự thực dụng:

1. Đánh dấu service ở trạng thái stopping và ngừng nhận công việc mới.
2. Dừng scheduler, subscription hoặc nguồn tạo task mới.
3. Gọi shutdown cho executor.
4. Chờ những task quan trọng hoàn tất trong khoảng thời gian được phép.
5. Nếu deadline gần hết, quyết định cancel, ghi trạng thái hoặc escalations theo policy.
6. Chỉ khi những producer cần log đã dừng, phát event kết thúc.
7. Stop async logging consumer nếu có, rồi close file sink.
8. Kết thúc tiến trình.

### 7.1. Race check-then-act

Sai lầm:

~~~java
if (!closed) {
    logger.info("event=task.done");
}
~~~

Đây là đoạn code minh họa trong một phương thức có biến. Giữa lúc thread A kiểm tra closed và gọi Logger, thread B có thể đã đóng Handler. Vì vậy, chỉ một boolean không đảm bảo cuộc ghi log an toàn.

**Giải pháp ở mức kiến trúc** là điều phối lifecycle của task producers, không phải rải các câu kiểm tra closed vào hàng nghìn nơi phát log.

### 7.2. Async pipeline

Nếu ứng dụng dùng Log4j2 AsyncLogger/AsyncAppender hoặc backend async khác:

~~~text
Producer -> Queue -> Background consumer -> File appender
~~~

Thứ tự shutdown phải cho consumer có cơ hội xử lý queue trước khi đóng File Appender. Cần test cả lúc queue đầy, sink chậm, timeout, drop policy và network/disk lỗi.

Không tự đóng file appender ở tầng thấp trước khi backend async hoàn tất stop theo hợp đồng. Và không khẳng định async sẽ giữ mọi log khi process bị SIGKILL hoặc đang overload.

## 8. File rotation và lock trong shutdown

JUL FileHandler có thể được cấu hình qua **logging.properties**:

~~~properties
handlers = java.util.logging.FileHandler
.level = INFO
java.util.logging.FileHandler.level = INFO
java.util.logging.FileHandler.pattern = logs/service-%u-%g.log
java.util.logging.FileHandler.limit = 1048576
java.util.logging.FileHandler.count = 5
java.util.logging.FileHandler.append = true
java.util.logging.FileHandler.formatter = java.util.logging.SimpleFormatter
~~~

Đây là ví dụ cấu hình, không phải code Java. Cần đảm bảo logs/ có quyền ghi và JUL thực sự nạp properties.

**FileHandler.close không thay thế retention.** Rotation tạo các generation theo pattern/count; việc đóng Handler không có nghĩa xóa toàn bộ file cũ. Cần chính sách dung lượng, thời gian lưu và quyền truy cập riêng.

### 8.1. Tại sao có .lck?

FileHandler có cơ chế lock để tránh sử dụng xung đột tài nguyên file. Nếu còn process đang chạy, **không xóa tệp .lck thủ công chỉ vì thấy nó**. Trước khi dọn lock sót sau crash, kiểm tra process, file pattern, quyền ghi và môi trường triển khai.

Một ứng dụng có nhiều replica hoặc nhiều JVM dùng chung filesystem cần path/lock/rotation riêng hoặc kiến trúc thu thập log phù hợp. Không mặc định cùng một file log có thể ghi an toàn từ mọi tiến trình.

### 8.2. Reset JUL có nguy hiểm không?

**java.util.logging.LogManager.getLogManager().reset()** reset cấu hình JUL trên phạm vi JVM, có thể tháo/đóng các Handler ở nhiều Logger. Không dùng reset để dọn một file của một module đang chạy trong khi các component khác vẫn cần logging.

Nếu Handler được tạo từ JUL logging.properties, LogManager có cơ chế quản lý vòng đời và các tùy chọn như **<logger>.handlers.ensureCloseOnReset**. Trừ khi có yêu cầu rất cụ thể, không nên tắt các cơ chế đóng Handler mặc định rồi bỏ mặc trách nhiệm cleanup.

## 9. Khác biệt với Log4j2 và Logback

### 9.1. Log4j2

Log4j2 có LoggerContext, File/RollingFile Appender và cơ chế shutdown của riêng nó. Theo tài liệu Log4j2, nhiều ứng dụng có shutdown hook được backend quản lý; môi trường web/framework có thể thay cơ chế đó bằng lifecycle tích hợp.

Khi ứng dụng thực sự **sở hữu LoggerContext** và cần đóng thủ công, Log4j API có phương thức:

~~~java
org.apache.logging.log4j.LogManager.shutdown();
~~~

Đây là **mảnh code phụ thuộc Log4j2**, không biên dịch bằng JDK thuần. Các overload có thể chọn một context nhất định; không tự giả định sẽ đóng mọi LoggerContext trong một JVM nhiều classloader.

Trong Spring Boot hoặc application server, thường để framework sở hữu lifecycle. Một thư viện không nên tự gọi shutdown làm các thành phần khác mất log.

### 9.2. Logback

Logback có LoggerContext và Appenders riêng. Khi chính ứng dụng tạo và sở hữu context, có thể stop bằng lifecycle API thích hợp, thường là **LoggerContext.stop()**. Khi framework sở hữu, để framework thực hiện.

Không gọi JUL FileHandler.close để đóng một Logback RollingFileAppender; chúng là những tài nguyên của hai hệ logging khác nhau.

### 9.3. Có cần đăng ký shutdown hook thứ hai?

Không mặc định. Nếu JUL hoặc backend đã có logic cleanup, một hook khác có thể chạy đồng thời và tranh chấp thứ tự dừng. Cần một lifecycle owner rõ ràng; hook ứng dụng nên là fallback khi thực sự cần, ngắn và idempotent.

## 10. Production, container và độ bền

### 10.1. Graceful termination của container

Khi một container chuẩn bị dừng, ứng dụng thường có một khoảng thời gian để giải quyết request in-flight, stop worker và shutdown logging. Nếu vượt quá thời gian đó, runtime có thể force kill và không đảm bảo hooks được chạy.

Nên:
- Đảm bảo tiến trình Java thực sự nhận được tín hiệu.
- Ngừng nhận traffic mới trước khi đóng log.
- Chờ workers có giới hạn.
- Để logging context stop trong khoảng thời gian còn lại.
- Đo thời gian thực tế khi hệ thống có tải.
- Định nghĩa policy khi không thể drain mọi record.

### 10.2. Console logging không loại bỏ shutdown

Trong container, nhiều hệ thống ghi stdout/stderr và để runtime/collector thu nhận. Đây có thể là lựa chọn hợp lý, nhưng appender, async queue, container log driver và collector vẫn có thể buffer hoặc fail. Dù dùng file hay console, cần kiểm tra end-to-end việc nhận event cuối.

### 10.3. Vì sao logging file không thay audit storage?

Một event chẩn đoán như **event=payment.completed** hữu ích khi điều tra nhưng không tự chứng minh một giao dịch đã được ghi nhận bền vững. Khi có yêu cầu audit, cần mô hình storage/transaction/outbox hoặc kênh ghi nhận có acknowledgment, retry, retention, integrity và kiểm soát truy cập.

**close/flush giúp cleanup, không tạo guarantee exactly-once hoặc chống mọi kiểu crash.**

## 11. Các lỗi phổ biến

### 11.1. Đóng quá sớm

FileHandler đã đóng trước khi worker log error cuối. Hãy dừng producer rồi mới đóng sink.

### 11.2. Dựa hoàn toàn vào shutdown hook

SIGKILL, halt, crash hoặc mất điện có thể bỏ qua hooks. Hook chỉ là fallback.

### 11.3. Ghi log trong shutdown hook

Một hook khác có thể đã đóng backend. Phát event cuối trong graceful lifecycle, rồi mới stop logging.

### 11.4. Gọi LogManager.reset tùy tiện

Reset JUL ảnh hưởng nhiều Logger/Handler, không chỉ một file. Đóng resource đúng owner.

### 11.5. Tin AtomicBoolean giải quyết concurrency

AtomicBoolean làm closeOnce idempotent, không dừng thread đang publish.

### 11.6. Đóng Appender trước async consumer

Queue còn event có thể bị mất. Stop backend theo API có hỗ trợ drain/shutdown.

### 11.7. Nghĩ flush là fsync

Flush không đảm bảo OS/storage đã ghi bền vững khi mất điện.

### 11.8. Mở nhiều FileHandler vào cùng path

Có thể gây lock hoặc file naming ngoài dự kiến. Quản lý một owner hoặc dùng kiến trúc multi-instance thích hợp.

### 11.9. Xóa .lck trong lúc app đang chạy

Có thể gây mất cơ chế coordination file. Kiểm tra process và lock trước.

### 11.10. Không xét append, rotation và restart

File có thể bị ghi đè hoặc tăng mãi; cần policy về append/rotation/retention và test restart.

### 11.11. Tắt backend từ thư viện nhỏ

Backend có thể là tài nguyên chung của cả app. Chỉ owner/framework mới nên stop.

### 11.12. Chờ vô hạn trong shutdown hook

Có thể vượt deadline của container và bị kill. Hook ngắn, tránh deadlock, dùng timeout hợp lý.

## 12. Checklist kiểm thử

| Tình huống | Điều cần kiểm tra |
| --- | --- |
| Đóng bình thường | Event app.stopping xuất trước close |
| Hook fallback | Chạy khi JVM shutdown bình thường |
| Close hai lần | closeOnce idempotent |
| Worker còn chạy | Không đóng file khi producer chưa dừng |
| Async queue | Drain theo hợp đồng và giới hạn thời gian |
| File lock | Không còn bị process đã thoát giữ |
| File rotation | Generation và retention đúng cấu hình |
| Append/restart | Không ghi đè lịch sử ngoài ý muốn |
| Disk full/permission denied | Có đường xử lý lỗi phù hợp |
| SIGTERM | Có thời gian shutdown hợp lý |
| SIGKILL | Không hứa giữ log cuối |
| Unicode | UTF-8 được bảo toàn |
| Nhiều process | Không tranh chấp file sai cách |
| Framework | LoggerContext được stop bởi đúng owner |

### 12.1. Thử trên Windows PowerShell

~~~powershell
javac --release 17 -encoding UTF-8 ShutdownFileLoggingDemo.java
java ShutdownFileLoggingDemo
Get-Content .\demo-logs\shutdown-demo.log -Encoding UTF8
Get-ChildItem .\demo-logs
java ShutdownFileLoggingDemo --hook
Get-Content .\demo-logs\shutdown-demo.log -Encoding UTF8
Get-ChildItem .\demo-logs
~~~

### 12.2. Thử trên Linux/macOS

~~~bash
javac --release 17 -encoding UTF-8 ShutdownFileLoggingDemo.java
java ShutdownFileLoggingDemo
cat demo-logs/shutdown-demo.log
ls -la demo-logs
java ShutdownFileLoggingDemo --hook
cat demo-logs/shutdown-demo.log
ls -la demo-logs
~~~

**Lưu ý:** demo dùng append=false, nên chế độ thứ hai có thể ghi đè file của lần trước. Không dùng đường dẫn demo để thực hành với log production cần lưu lịch sử.

## 13. Bài tập mở rộng

**Bài 1 — Shutdown một worker pool.** Tạo nhiều task cùng phát log qua FileHandler, dừng nhận task mới, chờ executor hoàn tất rồi đóng Handler. Giải thích trường hợp task không phản hồi interrupt.

**Bài 2 — Append và rotation.** Đổi FileHandler sang append=true và thêm limit/count. Chạy nhiều lần, quan sát file generation và lock sau shutdown.

**Bài 3 — Event lỗi cuối.** Thêm try/catch có Throwable rồi ghi log trước khi đóng; kiểm tra stack trace bằng Formatter phù hợp.

**Bài 4 — So sánh Log4j2.** Vẽ luồng AsyncLogger → queue → File Appender; giải thích tại sao không được đóng file trực tiếp trước khi context stop.

**Bài 5 — Container.** Lập thứ tự dừng HTTP listener, scheduler, worker, logger context và process trong một grace period cụ thể. Nêu cách đo sự kiện bị mất.

**Bài 6 — Audit.** Thiết kế một kênh lưu audit với acknowledgment và retry; so sánh với FileHandler.flush và close.

## 14. Câu hỏi tự đánh giá

**1. FileHandler.flush khác close như thế nào?**  
Flush đẩy dữ liệu buffer theo API; close kết thúc Handler và giải phóng file handle/lock.

**2. Shutdown hook luôn chạy khi SIGKILL không?**  
Không.

**3. Các shutdown hooks có chạy tuần tự theo thứ tự đăng ký không?**  
Không. Chúng có thể chạy đồng thời, thứ tự không xác định.

**4. Có nên đóng file đầu tiên khi nhận yêu cầu shutdown?**  
Không nếu worker còn phát log. Dừng producer trước.

**5. AtomicBoolean CLOSED trong demo giải quyết vấn đề gì?**  
Tránh nhánh owner closeOnce thực hiện cleanup nhiều lần, không phải dừng producer.

**6. FileHandler.close có xóa file cũ?**  
Không. Retention là chính sách riêng.

**7. Đóng file xong có đảm bảo dữ liệu chống mất điện không?**  
Không. Flush/close không tương đương durability transaction.

**8. LogManager.reset() có chỉ đóng một Handler không?**  
Không. Nó reset hệ JUL của JVM và có thể đóng nhiều Handler.

**9. Với Log4j2, dùng API nào để stop khi ứng dụng sở hữu context?**  
Dùng lifecycle Log4j2, chẳng hạn LogManager.shutdown với phạm vi phù hợp.

**10. Nếu async queue còn event, nên làm gì trước close?**  
Dừng producer, cho consumer drain theo hợp đồng backend và deadline.

**11. Có thể chỉ cần một file lock chung cho mọi replica?**  
Không nên mặc định. Cần chính sách tách file hoặc collection phù hợp, kiểm tra lock/rotation.

**12. Vì sao không đặt log cuối trong shutdown hook?**  
Backend có thể đã đóng bởi hook khác; thứ tự hooks không được đảm bảo.

## 15. Nguồn tham khảo chính thức

- Oracle JDK 17 FileHandler: https://docs.oracle.com/en/java/javase/17/docs/api/java.logging/java/util/logging/FileHandler.html
- Oracle JDK 17 Handler: https://docs.oracle.com/en/java/javase/17/docs/api/java.logging/java/util/logging/Handler.html
- Oracle JDK 17 LogManager: https://docs.oracle.com/en/java/javase/17/docs/api/java.logging/java/util/logging/LogManager.html
- Oracle JDK 17 Runtime và shutdown hooks: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Runtime.html
- Apache Log4j 2 FAQ về shutdown: https://logging.apache.org/log4j/2.x/faq.html
- Apache Log4j 2 Async logging: https://logging.apache.org/log4j/2.x/manual/async.html

Hãy đối chiếu tài liệu với JDK, OS, framework và backend mà ứng dụng thực tế sử dụng. Hành vi signal, file lock, async buffering và shutdown timeout có thể thay đổi theo runtime.

## 16. Ghi nhớ cốt lõi

**Đóng file logging đúng khi shutdown là quản lý cả một quá trình, không đơn thuần gọi close().** Với JUL FileHandler do ứng dụng sở hữu, cần dừng nguồn phát record, ghi event cuối, tháo Handler rồi flush/close. Shutdown hook giúp dọn dự phòng khi JVM shutdown bình thường, nhưng không đảm bảo xử lý mọi kiểu force kill, crash hoặc mất điện.

Trong framework và hệ logging bất đồng bộ, phải stop đúng logging context để queue và Appender được xử lý theo hợp đồng. Nếu event có nghĩa vụ lưu trữ bền vững, cần cơ chế audit/storage có xác nhận riêng thay vì tin vào file log text.

Ví dụ Java 17 đã được biên dịch và chạy trong cả hai chế độ; stdout, nội dung file và file lock đều đã được kiểm chứng trong môi trường thử nghiệm. Kết quả đó là cơ sở để xây dựng quy trình shutdown rõ ràng, có kiểm thử và phù hợp nhu cầu vận hành.
