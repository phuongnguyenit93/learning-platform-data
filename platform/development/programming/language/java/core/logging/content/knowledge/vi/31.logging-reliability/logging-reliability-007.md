# Fallback appender trong Java Logging

## 1. Mục tiêu: khi đích log chính gặp sự cố

Một ứng dụng Java có thể ghi log ra file, console, syslog, dịch vụ thu thập log hoặc endpoint mạng. Nếu đích chính hết dung lượng, mất kết nối hay appender báo lỗi, một giải pháp thường gặp là **fallback appender**: chuyển những sự kiện chưa thể ghi thành công sang một **đích dự phòng**.

Trong phạm vi bài này, **appender** là thành phần xuất log của các backend như Logback/Log4j 2; với `java.util.logging` (JUL), khái niệm gần tương đương là `Handler`. **Fallback** là hành động xử lý theo nhánh dự phòng sau khi nhận biết lỗi của đích chính. Nó khác việc luôn ghi mọi log ra hai đích.

Sau bài học, bạn có thể:
- Mô tả đường đi của log khi primary appender thành công, báo lỗi, được thử lại hoặc được phục hồi.
- Phân biệt **failover**, **mirroring/dual-write**, **retry**, **buffering** và **durable spool**.
- Viết ví dụ Java 17 độc lập với JUL, chứng minh chuyển một event sang handler dự phòng.
- Cấu hình `FailoverAppender` của **Log4j 2**, hiểu yêu cầu truyền lỗi từ appender chính và giới hạn của phương án.
- Biết lý do **Logback không có một lời gọi fallback chung** cho mọi appender; lựa chọn custom wrapper hoặc kiến trúc xuất log phù hợp.
- Thiết kế kiểm thử sự cố, observability và chính sách bảo toàn log thay vì chỉ thấy “ứng dụng không crash”.

## 2. Fallback appender hoạt động như thế nào?

Đường đi khái niệm:

```text
                  Log event
                      |
                      v
           Logger / level / filter
                      |
                      v
             Fallback controller
                      |
               thử Primary
                 /       \
            thành công   phát hiện lỗi
                |             |
                v             v
           Primary sink   Fallback sink
           (file/mạng)    (console/file/...)
                              |
                         kết quả ghi
```

**Tình huống bình thường:** chỉ primary nhận log. Nếu primary **thông báo lỗi theo cách bộ failover có thể nhận biết**, bộ điều phối có thể đưa event sang appender dự phòng, tạm ngừng thử primary, và sau một khoảng thời gian thử lại. Chính sách chính xác phụ thuộc implementation.

**Điều kiện mấu chốt:** fallback appender **không tự biết mọi lỗi**. Nếu primary bắt exception rồi chỉ in cảnh báo nội bộ, hoặc network client nhận dữ liệu vào buffer nhưng phía sau không chuyển đi được, bộ failover có thể vẫn nhìn thấy một lần gọi “thành công”. Nếu process crash trước khi fallback kịp chạy, logic trong JVM không còn cơ hội cứu event.

**Không đồng nhất các khái niệm:**

| Cơ chế | Hành vi | Mục đích |
| --- | --- | --- |
| Fallback/failover | Chỉ chuyển sang đích dự phòng sau khi nhận biết primary lỗi | Duy trì khả năng xuất log khi một sink gặp sự cố |
| Dual-write/mirroring | Gửi cùng event tới cả hai đích trong điều kiện bình thường | Có thêm bản sao hoặc phục vụ hai hệ thống |
| Retry | Thử gửi lại một thao tác thất bại tới đích đã chọn | Khắc phục lỗi tạm thời, có thể tạo bản ghi trùng |
| Buffering/async queue | Giữ event trong bộ nhớ rồi ghi sau | Giảm blocking, hấp thụ burst; có nguy cơ mất khi process chết |
| Durable spool/queue | Lưu event vào nơi bền vững trước khi gửi tiếp | Giảm mất event qua lần restart theo hợp đồng triển khai |

Khi ghi log liên quan đến **audit/compliance** có yêu cầu không mất bản ghi, fallback đơn lẻ thường **không đủ**. Cần cơ chế ghi nhận bền vững có acknowledgement và quy tắc retry/idempotency.

## 3. Những kiểu sự cố mà fallback cần xét

### Lỗi có thể phát hiện tại thời điểm ghi

Ví dụ:
- Appender mở file nhưng gặp lỗi ghi.
- Kết nối đến máy chủ syslog bị từ chối hoặc network client ném exception.
- Một thành phần primary do ứng dụng sở hữu chủ động đánh dấu `UNHEALTHY` và từ chối nhận event.
- Đích ghi hết quota hoặc lỗi xác thực và lỗi đó **được truyền trở lại** cho cơ chế failover.

Đối với những trường hợp này, fallback có thể chạy nếu exception/trạng thái lỗi đến được bộ điều phối và secondary vẫn hoạt động.

### Lỗi không dễ phát hiện tức thì

Ví dụ:
- Appender ghi vào buffer trong bộ nhớ, trả về thành công nhưng worker mạng thất bại sau đó.
- OS nhận bytes vào page cache nhưng disk hoặc collector chưa xác nhận lưu.
- UDP gửi gói không nhận acknowledgement.
- Một `AsyncAppender` chấp nhận enqueue nhưng consumer bị tắc hoặc queue tự drop event.
- Appender ghi xong một phần rồi ném exception; không thể xác định event ở primary có đầy đủ hay chưa.

Đây là nguyên nhân fallback **không đồng nghĩa “giao hàng chính xác một lần”**. Có thể mất log hoặc ghi trùng khi primary ghi một phần nhưng controller lại thử backup.

## 4. Ví dụ Java 17 độc lập: fallback với JUL Handler

JUL không dùng tên `Appender` cho đích xuất mà dùng `Handler`. Ví dụ này tự tạo một `FallbackHandler` bao quanh hai handler:
- `PrimaryHandler` in ra `PRIMARY ...`, nhưng **cố ý ném exception** với message `primary-down`.
- `BackupHandler` in ra `FALLBACK ...`.
- Bộ điều phối bắt lỗi của primary và đưa **cùng LogRecord** sang backup.

Đây là mô phỏng lỗi xác định để học hành vi, không cần tạo lỗi hệ thống thật.

Tạo tệp `FallbackAppenderDemo.java`:

```java
import java.util.logging.Handler;
import java.util.logging.Level;
import java.util.logging.LogRecord;
import java.util.logging.Logger;

public final class FallbackAppenderDemo {
    private static final class PrimaryHandler extends Handler {
        @Override
        public void publish(LogRecord record) {
            if (!isLoggable(record)) {
                return;
            }
            if ("primary-down".equals(record.getMessage())) {
                throw new IllegalStateException("simulated primary failure");
            }
            System.out.printf("PRIMARY %s | %s%n",
                    record.getLevel().getName(), record.getMessage());
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

    private static final class BackupHandler extends Handler {
        @Override
        public void publish(LogRecord record) {
            if (!isLoggable(record)) {
                return;
            }
            System.out.printf("FALLBACK %s | %s%n",
                    record.getLevel().getName(), record.getMessage());
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

    private static final class FallbackHandler extends Handler {
        private final Handler primary;
        private final Handler backup;
        private int fallbackCount;

        FallbackHandler(Handler primary, Handler backup) {
            this.primary = primary;
            this.backup = backup;
        }

        @Override
        public void publish(LogRecord record) {
            if (!isLoggable(record)) {
                return;
            }
            try {
                primary.publish(record);
            } catch (RuntimeException failure) {
                fallbackCount++;
                backup.publish(record);
            }
        }

        int fallbackCount() {
            return fallbackCount;
        }

        @Override
        public void flush() {
            try {
                primary.flush();
            } finally {
                backup.flush();
            }
        }

        @Override
        public void close() {
            try {
                primary.close();
            } finally {
                backup.close();
            }
        }
    }

    public static void main(String[] args) {
        Logger logger = Logger.getLogger("lesson.fallback.demo");
        logger.setLevel(Level.ALL);
        logger.setUseParentHandlers(false);

        Handler primary = new PrimaryHandler();
        Handler backup = new BackupHandler();
        primary.setLevel(Level.ALL);
        backup.setLevel(Level.ALL);

        FallbackHandler fallback = new FallbackHandler(primary, backup);
        fallback.setLevel(Level.ALL);
        logger.addHandler(fallback);

        try {
            logger.info("primary-ok");
            logger.warning("primary-down");
            logger.info("primary-restored");
            System.out.println("fallbackCount=" + fallback.fallbackCount());
        } finally {
            logger.removeHandler(fallback);
            fallback.close();
        }
    }
}
```

Biên dịch và chạy bằng JDK 17 trở lên:

```bash
javac FallbackAppenderDemo.java
java FallbackAppenderDemo
```

**Stdout chính xác** trong một JVM mới, không có cấu hình JUL ngoài thay đổi namespace `lesson.fallback.demo`:

```text
PRIMARY INFO | primary-ok
FALLBACK WARNING | primary-down
PRIMARY INFO | primary-restored
fallbackCount=1
```

### Giải thích kết quả

1. `logger.info("primary-ok")` được `PrimaryHandler` xử lý, nên không có fallback.
2. `logger.warning("primary-down")` khiến primary **ném `IllegalStateException` trước khi in**. `FallbackHandler` bắt lỗi, tăng bộ đếm và chuyển record sang backup.
3. `logger.info("primary-restored")` lại được thử primary và thành công, vì ví dụ này retry **ở từng event**; nó **không** có trạng thái circuit breaker hoặc khoảng chờ retry.
4. `fallbackCount=1` phản ánh **số lần nhánh dự phòng được gọi sau lỗi primary**, không bảo đảm một hệ thống log từ xa đã lưu bền vững record.
5. `Logger.setUseParentHandlers(false)` tránh xuất thêm log qua root handler mặc định; output handler dùng `System.out` và không thêm thời gian nên stdout cố định.

**Vì sao code chỉ bắt `RuntimeException`?** Đây là phạm vi đơn giản của ví dụ. Trong ứng dụng thực, lỗi I/O của handler có thể bị thư viện bắt và chỉ báo qua `ErrorManager`/status manager; lúc ấy wrapper không thấy exception và fallback không kích hoạt. Một appender có thể lỗi khi `flush()` hoặc `close()` chứ không phải khi `publish()`. Cơ chế failover production phải có contract nhận biết lỗi rõ ràng, xử lý lỗi cả secondary, timeout và lifecycle hợp lý.

**Giới hạn khác:** Nếu `BackupHandler.publish()` cũng ném exception, ví dụ sẽ để lỗi lan ra caller; đây không phải chính sách chịu lỗi tốt cho mọi ứng dụng. Nếu primary đã ghi được event rồi mới ném exception, backup có thể ghi thêm **bản sao**. Bộ đếm không đồng nghĩa “số log đã được cứu”. Mẫu code nhằm chứng minh *đường đi của điều kiện fallback*, không phải thư viện logging production.

## 5. Log4j 2: FailoverAppender có sẵn

Log4j 2 Core hỗ trợ `FailoverAppender`, cho phép khai báo **primary appender**, danh sách **failover appenders** và khoảng thời gian thử lại primary. Khi primary báo lỗi theo cơ chế của Log4j 2, failover có thể dùng secondary.

Đây là cấu hình **minh họa** cho dự án đã dùng Log4j 2 Core. Lưu thành `log4j2.xml` trên classpath phù hợp, với thư mục đích và quyền ghi được cấp theo môi trường:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<Configuration status="WARN">
    <Appenders>
        <File name="PRIMARY_FILE"
              fileName="logs/primary.log"
              ignoreExceptions="false">
            <PatternLayout pattern="%d{ISO8601} %-5p %c - %m%n"/>
        </File>

        <Console name="BACKUP_CONSOLE" target="SYSTEM_ERR">
            <PatternLayout pattern="FALLBACK %d{ISO8601} %-5p %c - %m%n"/>
        </Console>

        <Failover name="RESILIENT"
                  primary="PRIMARY_FILE"
                  retryIntervalSeconds="30">
            <Failovers>
                <AppenderRef ref="BACKUP_CONSOLE"/>
            </Failovers>
        </Failover>
    </Appenders>

    <Loggers>
        <Root level="info">
            <AppenderRef ref="RESILIENT"/>
        </Root>
    </Loggers>
</Configuration>
```

### Vì sao đặt `ignoreExceptions="false"`?

Cơ chế failover cần **nhận được tín hiệu lỗi** từ primary. Với Log4j 2, appender thường có khả năng bắt và báo lỗi nội bộ; để `FailoverAppender` phát hiện một số lỗi từ primary, primary phải cấu hình `ignoreExceptions="false"`. Nếu primary nuốt lỗi, controller có thể tưởng là ghi thành công và không chạy backup.

**Không đặt backup như một appender thứ hai trực tiếp dưới root** nếu mục tiêu là *chỉ ghi backup lúc primary lỗi*. Khi root tham chiếu cả PRIMARY_FILE và BACKUP_CONSOLE, đó là **dual-write**, không phải conditional failover. Trong XML ví dụ, root chỉ tham chiếu `RESILIENT`.

### Giải thích các thành phần

- `PRIMARY_FILE`: đích chính là tệp `logs/primary.log`.
- `BACKUP_CONSOLE`: khi có lỗi mà bộ failover nhận được, event chuyển sang `System.err`. Đây là lựa chọn minh họa tương đối độc lập với file đích chính, nhưng **không phải lưu trữ bền vững** nếu stderr không được collector lấy và giữ.
- `RESILIENT`: tên appender điều phối, phải được gắn vào logger/root để event đi qua nó.
- `primary="PRIMARY_FILE"`: tên appender chính; phải trỏ tới appender đã khai báo và khởi tạo hợp lệ.
- `<Failovers>`: danh sách fallback targets theo cơ chế Log4j 2. Có thể cấu hình nhiều backup, nhưng cần kiểm tra chính sách lỗi và thứ tự ưu tiên của phiên bản đang dùng.
- `retryIntervalSeconds="30"`: thiết lập thời gian chờ giữa những lần thử primary sau lỗi. Đây không phải cam kết primary phục hồi sau đúng 30 giây, cũng không phải cơ chế phát lại toàn bộ log đã đi qua backup.
- `Root level="info"`: chỉ sự kiện vượt qua điều kiện logging của root hoặc logger tương ứng mới đến appender. Failover không khôi phục event bị chặn trước đó.

### Điều kiện và giới hạn

1. Cơ chế chỉ có thể fallback khi primary **báo lỗi được quan sát**. Remote appender đưa bytes vào network buffer rồi báo thành công có thể gặp lỗi ở phía sau mà FailoverAppender không biết.
2. Lỗi **khởi tạo** khác lỗi **khi đang chạy**. Nếu file, appender hoặc cấu hình không khởi tạo được từ đầu, log startup/status diagnostics của Log4j 2 cần được kiểm tra. Đừng giả định mọi lỗi bootstrap đều tự kích hoạt cùng đường fallback như lỗi runtime.
3. `retryIntervalSeconds` không tạo durable queue và không replay các sự kiện đã ghi ở fallback về primary khi primary phục hồi.
4. Nếu stdout/stderr của container không được thu thập hoặc bị truncate, backup cũng có thể mất.
5. Nếu primary đã ghi **một phần** trước khi báo lỗi, gửi lại event sang backup có thể tạo bản ghi trùng. Cần event ID/sequence và cơ chế downstream phù hợp nếu phải phát hiện duplicate.
6. Nếu `AsyncAppender` hoặc async logger nằm trước failover controller, chú ý chính sách queue, drop và vị trí phát hiện lỗi. Enqueue thành công không bảo đảm đích cuối đã nhận event.

Không nên thử lỗi thực tế bằng cách tự thay quyền/xóa file log đang hoạt động ở production. Dùng môi trường test, filesystem giả lập hoặc appender có thể chủ động phát tín hiệu lỗi; xác nhận bằng status logs và event IDs.

## 6. Logback: không giả định có FailoverAppender giống Log4j 2

Trong Logback Classic/Core, các thành phần phổ biến gồm `ConsoleAppender`, `FileAppender`, `RollingFileAppender`, `AsyncAppender` và filter. Tuy nhiên, **đừng giả định Logback có sẵn một FailoverAppender tương đương Log4j 2 với cùng tên tag/XML** trên mọi phiên bản.

Những lựa chọn phổ biến:

- **Custom wrapper appender** quản lý primary và backup, có kiểm tra trạng thái/lỗi, retry/backoff, counters, flush/stop và failover. Cần hiểu API/lifecycle và chiến lược báo lỗi của Logback; nhiều appender xử lý exception qua status manager thay vì ném ra caller.
- **Ghi ra console và để collector bên ngoài quản lý dự phòng**. Với container, xuất ra stdout/stderr và có agent/collector bền vững thường đơn giản hơn cố xử lý mọi lỗi mạng trong JVM.
- **Dual-write có kiểm soát** tới hai appender độc lập: không phải fallback, nhưng có thể phù hợp nếu chấp nhận chi phí/duplicate và biết rõ failure domains.
- **Spool/queue bền vững ngoài logging pipeline** cho các sự kiện có yêu cầu độ tin cậy cao; phù hợp khi cần retry qua restart.

### Ví dụ Logback dual-write, không phải failover

```xml
<configuration>
    <appender name="CONSOLE"
              class="ch.qos.logback.core.ConsoleAppender">
        <encoder>
            <pattern>%level %logger - %msg%n</pattern>
        </encoder>
    </appender>

    <appender name="FILE"
              class="ch.qos.logback.core.FileAppender">
        <file>logs/app.log</file>
        <encoder>
            <pattern>%d{HH:mm:ss.SSS} %level %logger - %msg%n</pattern>
        </encoder>
    </appender>

    <root level="INFO">
        <appender-ref ref="CONSOLE"/>
        <appender-ref ref="FILE"/>
    </root>
</configuration>
```

Trong cấu hình này, **hai appender đều nhận log theo đường root trong điều kiện bình thường**. Nó giúp giảm phụ thuộc vào một đích đơn lẻ nhưng không thực hiện chuyển đổi có điều kiện khi FILE lỗi. Nếu yêu cầu thật sự là “chỉ console khi file hỏng”, cần thành phần failover phù hợp, không thể gọi hai `<appender-ref>` là fallback.

**Lưu ý quan trọng:** `AsyncAppender` là hàng đợi bất đồng bộ, **không** phải appender dự phòng. Cấu hình async có thể giúp producer không chờ I/O nhưng có queue overflow, giới hạn flush và trường hợp mất event khi shutdown. `RollingFileAppender` đổi file theo chính sách rotation, **không** tự động chuyển sang sink độc lập lúc file system bị lỗi.

## 7. Kiến trúc fallback đáng tin cậy: trạng thái và deadline

Một custom failover thường cần trạng thái thay vì “thử primary ở mọi event” như demo:

```text
HEALTHY
  | primary error (được báo rõ)
  v
DEGRADED / FALLBACK_ACTIVE
  | log mới -> backup
  | đo lỗi, giới hạn dung lượng, lên lịch kiểm tra primary
  v
PROBING_PRIMARY
  |-- probe thất bại --> FALLBACK_ACTIVE (backoff)
  |-- probe thành công -> HEALTHY
```

Điều này gần với circuit breaker, nhưng cần cân nhắc:
- **Không spam primary lỗi:** thử mỗi event trong thời gian primary down có thể làm tăng latency/CPU và tạo hàng loạt exception. Nên có backoff, retry interval hoặc circuit-breaker phù hợp.
- **Không dùng probe như cam kết vận chuyển event:** probe thành công không có nghĩa collector đã lưu toàn bộ những event trước đó.
- **Concurrency:** nhiều thread có thể phát log đồng thời. Chuyển trạng thái phải thread-safe và tránh tự tạo lock hoặc thao tác blocking trong logging hot path.
- **Timeout:** network sink bị treo thường nguy hiểm không kém việc ném exception. Nếu primary chặn vô hạn, fallback sẽ không được thử. Cần timeout hữu hạn ở client/transport theo công nghệ đang dùng.
- **Fallback capacity:** file dự phòng có thể đầy; stdout pipe có thể block; memory queue có thể tràn. Phải đo backlog, dropped events và deadline.
- **Recovery semantics:** khi primary trở lại, log mới có thể đi về primary nhưng log đã gửi backup không tự chuyển theo. Muốn hợp nhất, phải có quy trình đọc/replay và xử lý duplicate ở downstream.
- **Shutdown:** khi appender/queue còn event, cần drain, flush và đóng primary/backup đúng lifecycle. Trong container, deadline shutdown phải nằm trong termination grace period.

Một controller tốt nên định nghĩa rõ event được coi là **accepted**, **emitted**, **persisted** hoặc **acknowledged** tại thời điểm nào. Không dùng một tên chung `success` cho mọi trạng thái.

## 8. Chọn fallback đích nào?

Không có một phương án phù hợp mọi môi trường. Hãy so sánh failure domain:

| Primary | Backup khả dĩ | Ưu điểm | Rủi ro chính |
| --- | --- | --- | --- |
| Remote TCP/HTTP appender | Local rolling file | Có thể giữ log khi mạng bị đứt | Disk đầy, không tự replay sau restart, quyền/rotation |
| Local file | Console stderr | Không cùng file path; dễ được container runtime thu thập | Console không bền vững nếu không có log collector |
| Remote collector A | Collector B độc lập | Dự phòng ngoài ứng dụng | Chi phí, retry, quota, xác thực và cả hai cùng lỗi |
| Log exporter/agent | Durable local spool | Có thể hỗ trợ gửi lại | Phức tạp vận hành, disk capacity, deduplication |
| Shared network storage | File trên cùng mount | Cấu hình đơn giản | **Không có** failure isolation nếu mount lỗi |

**Failure domain** rất quan trọng: nếu primary và backup cùng dùng một ổ đĩa đã đầy, cấu hình có hai file không giúp tiếp tục ghi. Hai collector dùng cùng credentials/token hoặc cùng gateway cũng có thể cùng thất bại.

Trong container, gửi log ứng dụng ra stdout/stderr và để platform thu thập thường hợp lý, nhưng phải kiểm tra retention, backpressure và độ bền cụ thể. Backup không an toàn chỉ vì tên chứa “backup”.

**Bảo mật:** dữ liệu ở backup cần cùng mức bảo vệ với primary: tránh ghi token, password, thông tin cá nhân, connection string hoặc payload nhạy cảm. Fallback qua stdout có thể đưa dữ liệu tới nơi có quyền truy cập khác với file chính.

## 9. Fallback, thứ tự sự kiện và tính toàn vẹn

Trong khi primary lỗi, một số event vào backup; sau khi primary phục hồi, event mới lại vào primary:

```text
T1: order-created      -> PRIMARY
T2: order-paid         -> BACKUP
T3: order-confirmed    -> BACKUP
T4: order-completed    -> PRIMARY
```

Nếu chỉ xem primary, chuỗi sự kiện nghiệp vụ bị đứt đoạn. Cần hợp nhất/tra cứu **cả hai đích** để theo dõi đầy đủ. Timestamp và `event_id`/`trace_id` giúp đối chiếu, nhưng timestamp không nhất thiết bảo đảm thứ tự tuyệt đối giữa thread hoặc các máy.

Các vấn đề quan trọng:

1. **Ordering:** event đi qua hai sink độc lập có thể xuất/thu thập khác thứ tự; async queue càng làm phức tạp thứ tự quan sát.
2. **Duplicate:** primary đã ghi event rồi exception xảy ra ở bước sau; backup ghi thêm bản sao.
3. **Loss:** cả primary và backup có thể lỗi, queue overflow hoặc process chết trước khi flush.
4. **Replay:** muốn chuyển dữ liệu backup về primary khi hồi phục cần công cụ hoặc spool/replay riêng; FailoverAppender thông thường không phải message broker.
5. **Durability:** flush file hoặc socket write thành công không tương đương collector đã ack lưu bền vững.

Nếu cần log có tính chất bằng chứng/audit, thiết kế cần contract rõ ràng về at-least-once, deduplication, ordering và idempotency. Với giao dịch quan trọng, event nên được ghi trong cơ chế lưu trữ bền vững phù hợp.

## 10. Phát hiện sự cố và tránh logging vòng lặp

Một lỗi thiết kế là trong handler xử lý lỗi logging lại gọi **chính logger đang gặp lỗi**:

```text
Primary appender lỗi
      |
      v
Error handler gọi logger.error(...)
      |
      v
Cùng primary appender lại lỗi
      |
      +----> đệ quy/stack overflow/log storm
```

Không log lại lỗi appender qua chính đường appender lỗi. Hướng phù hợp:
- Metrics `primary_write_failures_total`, `failover_events_total`, `fallback_write_failures_total`.
- Status logger/internal diagnostics **độc lập** của logging backend.
- Kênh báo lỗi tối giản như `System.err` khi thích hợp, có **rate limit** và không quay lại cùng pipeline.
- Health status và alert khi fallback hoạt động lâu hoặc gần hết dung lượng.

Metrics nên trả lời: primary hỏng từ lúc nào, có bao nhiêu event qua fallback, backup còn ghi được không, có log bị drop không, và đã phục hồi chưa?

“Không có exception trong business code” **không chứng minh** pipeline khỏe. Một số appender cố ý bắt lỗi để không làm hỏng luồng nghiệp vụ. Hãy quan sát status/error counters và sink cuối.

## 11. Kiểm thử có chủ đích

| Tình huống | Kỳ vọng cần đối chiếu |
| --- | --- |
| Primary khỏe | Event đi primary; fallback không nhận nếu đang dùng conditional failover |
| Primary ném exception trước khi ghi | Event thử chuyển backup; counter failover tăng |
| Primary ghi một phần rồi ném exception | Kiểm tra duplicate; không khẳng định exactly-once |
| Primary timeout/block | Có deadline; fallback chỉ chạy nếu cơ chế báo lỗi/timeout hoạt động |
| Primary báo lỗi nội bộ nhưng không ném | Xác minh failover controller có **thật sự** nhận tín hiệu lỗi |
| Primary mất ngay khi khởi động | Xem diagnostics và appender initialization; không giả định hành vi runtime failover |
| Backup cũng lỗi | Có chính sách drop/alert/dừng phù hợp, không đệ quy logging |
| Primary hồi phục | Log mới chuyển lại theo retry policy; log cũ ở backup không tự replay |
| Nhiều producer đồng thời | Không race trạng thái failover, không deadlock, có số đo event |
| Queue đầy / async | Backpressure/drop có thể xảy ra trước controller; đo accepted và emitted |
| JVM shutdown / SIGTERM | Drain/flush trong deadline; forced kill không được bảo đảm |
| Fallback disk đầy | Có cảnh báo capacity, rotation/retention và chính sách phù hợp |

### Quy trình thử tích hợp Log4j 2

1. Xác minh process dùng Log4j 2 Core thực sự, đọc đúng `log4j2.xml`, và `RESILIENT` được root/logger tham chiếu.
2. Ghi log probe có ID duy nhất, ví dụ `FALLBACK_PROBE_001`, khi primary hoạt động. Xác minh nó chỉ ở primary (nếu cấu hình conditional failover).
3. Trong môi trường test, mô phỏng primary appender **ném lỗi mà FailoverAppender quan sát được**; không cần phá filesystem production. Ghi event thử khác, ví dụ `FALLBACK_PROBE_002`.
4. Kiểm tra backup stderr/collector có event `002`. Xem diagnostics và metrics, xác nhận không gây exception ngoài ý muốn trên luồng nghiệp vụ.
5. Phục hồi primary, đợi cơ chế retry theo cấu hình và ghi `FALLBACK_PROBE_003`. Xác minh event mới đi primary; quan sát nơi `002` còn được lưu.
6. Thử cả trường hợp backup lỗi và shutdown. Đối chiếu số event emitted/dropped, không chỉ xem “application vẫn chạy”.

Tùy appender, lỗi có thể xuất hiện ở startup, lúc `append`, flush, close hoặc background worker. Kết luận kiểm thử phải nêu rõ **loại lỗi đã giả lập** và phiên bản backend. Thử “file chưa có thư mục” không tự chứng minh failover khi ghi runtime.

## 12. Những sai lầm thường gặp

| Sai lầm | Tại sao nguy hiểm | Hướng khắc phục |
| --- | --- | --- |
| Gắn PRIMARY và BACKUP trực tiếp vào root rồi gọi là fallback | Hai appender có thể ghi mọi event | Dùng controller failover hoặc gọi đúng là dual-write |
| Primary nuốt lỗi | Bộ failover không nhận biết sự cố | Cấu hình propagation/status đúng với backend; với Log4j 2 kiểm tra `ignoreExceptions` |
| Chỉ quan tâm exception ở caller | Appender có thể báo lỗi nội bộ/bất đồng bộ | Kiểm tra internal status, metrics và sink cuối |
| Dùng cùng ổ đĩa cho hai file | Disk full làm cả primary và backup cùng lỗi | Chọn failure domain khác |
| Giả định backup console bền vững | Container/logging agent có thể drop | Kiểm tra retention/collector hoặc chọn durable spool |
| Retry mọi event khi primary hỏng | Log storm, CPU/latency lớn | Backoff và giới hạn retry/circuit breaker |
| Tự log lỗi vào cùng pipeline | Đệ quy và deadlock | Dùng status channel độc lập, rate limit |
| Chuyển sang backup nhưng quên đọc backup | Mất khả năng tra cứu chuỗi sự kiện | Thu thập cả hai sink và gắn event ID |
| Coi fallback là exactly-once | Có thể duplicate hoặc loss | Xác định delivery semantics và idempotency |
| Xem enqueue thành công là ghi thành công | Queue/worker có thể lỗi sau đó | Theo dõi emitted/ack, flush/shutdown |
| Dùng Logback như thể có XML `<Failover>` mặc định | Config có thể không hợp lệ hoặc bị bỏ qua | Dùng API/extension phù hợp backend |
| Thử lỗi bằng xóa file production | Có thể phá luồng log và dữ liệu hiện có | Fault injection có kiểm soát ở staging |

## 13. Lựa chọn theo yêu cầu độ tin cậy

**Nếu mục tiêu là “dịch vụ không bị chậm/hỏng khi log backend gián đoạn”:** cân nhắc appender bất đồng bộ có deadline, fallback local/console, metrics và chính sách drop rõ ràng. Chấp nhận một số log có thể mất khi quá tải hoặc crash.

**Nếu mục tiêu là “log lỗi luôn có lối quan sát tối thiểu”:** fallback `stderr` có thể hữu ích khi file/remote sink hỏng, nhưng cần chắc runtime/container vẫn thu thập stderr và dữ liệu không nhạy cảm.

**Nếu mục tiêu là “không mất sự kiện nghiệp vụ quan trọng”:** nên dùng durable queue/outbox/transactional storage và cơ chế ack/replay riêng. Logging là kênh quan sát, không mặc định là cơ sở dữ liệu giao dịch.

**Nếu ứng dụng dùng Log4j 2:** xem xét `FailoverAppender`, cấu hình `ignoreExceptions="false"` cho primary và thử fault injection thực tế.

**Nếu ứng dụng dùng Logback hoặc JUL:** dùng API/kiến trúc phù hợp thay vì giả định tên appender giữa các backend có thể hoán đổi. Nếu tự viết wrapper, phải xử lý đồng bộ, lỗi primary/secondary, shutdown, retry, telemetry, giới hạn payload và tài nguyên.

## 14. Checklist trước production

1. Đã xác định logging backend và phiên bản **đang thực sự chạy**.
2. Đã xác định primary, backup và **failure domain** của từng đích.
3. Đã kiểm tra **tín hiệu lỗi** từ primary có đi đến controller failover không.
4. Đã mô tả điều kiện kích hoạt fallback, khoảng retry và tiêu chí phục hồi.
5. Đã kiểm thử lỗi runtime, lỗi khởi tạo, timeout và secondary cũng hỏng.
6. Có metrics/alert cho primary failure, fallback active, dropped events và backup capacity.
7. Có thời hạn shutdown, flush/close và kế hoạch khi process bị force kill.
8. Có cách truy vấn log ở cả primary và backup, tránh mất chuỗi sự kiện.
9. Đã phân loại dữ liệu nhạy cảm và áp cùng chính sách bảo mật/retention ở backup.
10. Đã thống nhất yêu cầu durability: best-effort, at-least-once có duplicate, hay sự kiện phải được lưu bền vững bằng hệ thống khác.

**Kết luận:** Fallback appender làm tăng **khả năng duy trì đường xuất log** khi primary báo lỗi, nhưng không bảo đảm tuyệt đối “mọi log sẽ được lưu”. Thiết kế đúng cần nhận biết lỗi thực sự, dự phòng ở failure domain khác, quan sát hoạt động failover, xử lý timeout/retry và kiểm thử đủ các nhánh lỗi. Khi cần độ tin cậy cao hơn best-effort, phải bổ sung cơ chế lưu hàng đợi bền vững và xác nhận ở phía đích.