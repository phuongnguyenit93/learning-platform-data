# Không giới hạn file log — anti-pattern trong Java Logging

## 1. Anti-pattern này là gì?

**Không giới hạn file log** là lỗi thiết kế/vận hành khiến ứng dụng liên tục ghi vào một file, hoặc tạo file archive mới không có chính sách giới hạn tổng dung lượng và tuổi dữ liệu. Trong môi trường production, file có thể tăng đến khi đầy filesystem, quota của container hoặc disk của node. Sự cố ban đầu có thể chỉ là thiếu dung lượng, nhưng cuối cùng có thể làm hỏng **logging, hiệu năng, khả năng ghi dữ liệu nghiệp vụ và khả năng điều tra**.

Ví dụ rất dễ tạo vấn đề:

```java
// Minh họa KHÔNG AN TOÀN khi dùng vô hạn trong production.
// JUL FileHandler(pattern, append) không đặt limit và count quay vòng.
java.util.logging.FileHandler handler =
        new java.util.logging.FileHandler("logs/application.log", true);
```

Hoặc với Logback, chỉ cấu hình `FileAppender` thông thường:

```xml
<!-- Anti-pattern: file không có rolling/retention policy -->
<appender name="FILE" class="ch.qos.logback.core.FileAppender">
    <file>logs/application.log</file>
    <append>true</append>
    <encoder>
        <pattern>%d{ISO8601} %-5level %logger - %msg%n</pattern>
    </encoder>
</appender>
```

Các đoạn này có thể hợp lệ về cú pháp nhưng **không giới hạn kích thước và vòng đời file**. Nếu service ghi nhiều và chạy lâu, file tiếp tục tăng. Việc JVM đã thoát không bảo đảm file tự bị xóa; lần khởi động sau với `append=true` có thể ghi tiếp vào file cũ.

**Lưu ý:** một file appender không tự động là anti-pattern nếu hệ thống đã có **cơ chế rotation và retention ở bên ngoài** được kiểm soát, kiểm thử và giám sát. Vấn đề là **không có chính sách giới hạn có hiệu lực trên đường ghi dữ liệu thực tế**.

## 2. Khi nào lỗi trở thành sự cố?

Ví dụ hệ thống ghi 250 log event/giây, mỗi event sau encoding khoảng 700 byte:

```text
bytes_per_second = 250 × 700 = 175.000 B/s
bytes_per_day    = 175.000 × 86.400 = 15.120.000.000 B/day
                ≈ 15,12 GB/ngày (GB thập phân)
```

Nếu filesystem chỉ còn khoảng 10 GiB (~10,74 tỷ byte), thì theo **tốc độ đều giả định**, phần dung lượng ấy có thể bị dùng hết trong khoảng **17 giờ**. Đây là phép tính minh họa, không thay cho đo thực tế: log rate thay đổi theo traffic, kích thước JSON, stack trace, compression, replica, dữ liệu khác trên ổ và chính sách disk cleanup.

Khi lượng ghi tăng đột biến do lỗi lặp, brute-force login, retry storm hay vô tình bật DEBUG, thời gian còn lại có thể ngắn hơn nhiều.

### Chuỗi hậu quả điển hình

```text
Không có rotation / retention hiệu lực
               │
               ▼
        File hoặc archive tăng
               │
               ▼
     Disk usage / inode usage cao
               │
       ┌───────┴────────┐
       ▼                ▼
Appender write      Filesystem đầy
error / log mất         │
       │                ▼
       │          Database/cache/tmp
       │          cũng có thể bị ảnh hưởng
       ▼                │
Observability mù ◄──────┘
       │
       ▼
Sự cố khó điều tra và có thể kéo dài
```

**Không chỉ “file lớn làm chậm tìm kiếm”.** File quá lớn còn gây khó copy, nén, truyền, tail, backup hoặc recovery; disk-full có thể tác động các thành phần khác dùng chung filesystem. Một appender chạy đồng bộ có thể tăng request latency nếu ghi file bị chậm hoặc lỗi liên tục. Hành vi cụ thể khi I/O lỗi **phụ thuộc backend và cấu hình**, không được mặc định mọi logger đều ném exception làm hỏng request.

## 3. Vì sao giới hạn theo một tham số chưa đủ?

Cần phân biệt ít nhất bốn lớp giới hạn:

| Lớp | Ví dụ | Giới hạn được gì? | Chưa giải quyết được gì? |
| --- | --- | --- | --- |
| **Kích thước từng event** | Giới hạn message/stack trace | Tránh một event chiếm MB | Không ngăn hàng triệu event nhỏ |
| **Tốc độ phát log** | Level/rate limit/sampling chọn lọc | Giảm bytes/giây | Không bảo đảm log bắt buộc được giữ |
| **Kích thước file active** | Rolling theo 50 MB | Không để file active tăng mãi | Archive có thể tăng vô hạn |
| **Số kỳ/tuổi/tổng archive** | 7 ngày, 1 GB archive | Dọn file cũ có điều kiện | Không phải hard quota filesystem |
| **Giới hạn dung lượng hạ tầng** | Volume quota, container node limit, alert | Bảo vệ phần tài nguyên chung | Không tự giữ được audit khi đầy |
| **Retention ở backend** | Index/object lifecycle | Giới hạn bản copy tập trung | Không xử lý file local/collector spool |

Ví dụ có `maxFileSize=50MB` nhưng **không có cleanup cho archive** vẫn có thể tạo hàng nghìn file nén. Có `maxHistory=7` nhưng không có size-based rollover thì trong một ngày bất thường file active có thể lớn hơn dự tính. Có cả `maxFileSize`, `maxHistory`, `totalSizeCap` nhưng app dùng một thư mục không có disk quota và nhiều service khác cũng ghi vào đó, thì hạ tầng vẫn có thể hết dung lượng.

**Nguyên tắc:** kiểm soát **kích thước từng event + phát sinh dữ liệu + rotation + retention + filesystem/backend capacity**. Tất cả phải có chủ sở hữu và giám sát.

## 4. Nhận diện nguyên nhân trong thực tế

Các dấu hiệu thường thấy:

- `df -h` báo filesystem chứa log gần đầy, nhưng application vẫn ghi INFO/DEBUG rất nhiều.
- `du` cho thấy một file `application.log` tăng liên tục, hoặc archive có rất nhiều file `application.2026-...log.gz`.
- Monitoring báo disk free giảm nhanh, `ENOSPC` / “No space left on device”.
- Backend không còn nhận đủ log vì appender hoặc node collector không đọc/ghi được.
- CPU/I/O cao khi rotate/compress, hoặc collector tụt phía sau vì file quá lớn.
- Sau deploy/restart, file chưa bị dọn vì policy không khởi tạo hoặc chỉ chạy cleanup lúc rollover.
- Một app log đã được rotate, nhưng file access log của Tomcat, gateway hay application server khác vẫn tăng.
- Một pod stdout được kubelet rotate, song ứng dụng lại ghi file phụ trong volume không do kubelet quản lý.

### Đừng kết luận chỉ bằng một triệu chứng

| Triệu chứng | Có thể là | Cần kiểm tra |
| --- | --- | --- |
| Disk đầy | File log, DB, cache, image layer, inode cạn | Filesystem thực tế và top consumers |
| File active quá lớn | Không rollover hoặc policy startup fail | Effective appender config và status logs |
| Rất nhiều archive | Không retention hoặc glob không match | Thời điểm cleanup, policy và permissions |
| File xóa mà disk không tăng free | Process còn giữ file descriptor đã bị unlink | Handle/file descriptors của process |
| File dưới container nhỏ nhưng node đầy | Node stdout files, image layers hoặc log service khác | Node log directory và kubelet configuration |
| Search backend trống | Collector hỏng hoặc parser/query/permission sai | Source → collector → index → dashboard |
| Log vẫn đầy sau giảm INFO | ERROR storm hoặc file khác/collector spool | Event rate, size, sink ownership |

Cần biết **source file, bản archive, collector buffer, index và backup** là các bản sao khác nhau; dọn một lớp không đồng nghĩa đã dọn toàn bộ.

## 5. Cấu hình Logback sai và cách sửa bằng rolling policy

### Cách sai: chỉ có FileAppender

```xml
<appender name="APP" class="ch.qos.logback.core.FileAppender">
    <file>logs/app.log</file>
    <append>true</append>
    <encoder>
        <pattern>%d %-5level %logger - %msg%n</pattern>
    </encoder>
</appender>
```

Mẫu này không có triggering/rolling policy: **log active không có giới hạn vòng đời tại Logback**.

### Cách tốt hơn: SizeAndTimeBasedRollingPolicy

Ví dụ file `logback.xml` dùng Logback-classic (cần dependency đúng phiên bản của ứng dụng):

```xml
<configuration>
    <appender name="APP"
              class="ch.qos.logback.core.rolling.RollingFileAppender">
        <file>logs/app.log</file>

        <rollingPolicy
                class="ch.qos.logback.core.rolling.SizeAndTimeBasedRollingPolicy">
            <fileNamePattern>logs/archive/app.%d{yyyy-MM-dd}.%i.log.gz</fileNamePattern>
            <maxFileSize>50MB</maxFileSize>
            <maxHistory>7</maxHistory>
            <totalSizeCap>1GB</totalSizeCap>
            <cleanHistoryOnStart>true</cleanHistoryOnStart>
        </rollingPolicy>

        <encoder>
            <pattern>%d{ISO8601} %-5level [%thread] %logger - %msg%n</pattern>
        </encoder>
    </appender>

    <root level="INFO">
        <appender-ref ref="APP"/>
    </root>
</configuration>
```

**Giải thích chính xác từng tham số:**

- `RollingFileAppender` ghi vào file active `logs/app.log`, chuyển file cũ thành archive khi điều kiện rollover được đáp ứng.
- Trong `SizeAndTimeBasedRollingPolicy`, pattern cần **cả `%d` và `%i`** để phân biệt ngày và file index.
- `maxFileSize=50MB` là ngưỡng kích hoạt rollover theo kích thước của **file active**; không phải hard limit tổng filesystem và có thể vượt ngưỡng do timing/độ lớn event.
- `maxHistory=7` với pattern hằng ngày là **7 kỳ ngày archive**, **không phải 7 file**. Nếu một ngày có 40 file vì traffic cao, tổng archive có thể nhiều hơn 7 file.
- `totalSizeCap=1GB` giới hạn **tổng các archive** mà cleanup quản lý, sau khi áp dụng ràng buộc lịch sử; không bao gồm mọi file trên disk, không chắc bao gồm file active, và cleanup có thể chạy bất đồng bộ.
- `cleanHistoryOnStart=true` cho phép dọn archive lúc appender startup. Thông thường cleanup còn gắn với rollover, nên không bảo đảm mọi file hết hạn được dọn đúng mili giây.
- Đuôi `.gz` yêu cầu nén archive; compression tốn CPU và có thể thất bại. Giám sát lỗi nén/rename và disk temporary usage.
- `root level=INFO` chỉ quyết định mức log được phép phát, **không** bảo đảm appender không bao giờ ghi secret hoặc ERROR storm không vượt quota.

**Giới hạn quan trọng:** `maxHistory`/`totalSizeCap` không thay **filesystem quota, disk alert, retention của backend hoặc quản trị audit**. Với production, số `50MB`, `7` và `1GB` là **ví dụ**, cần tính toán bằng tốc độ log, kích thước và yêu cầu lưu giữ thật.

### Khi chỉ cần giới hạn tổng archive, không nhất thiết dùng size+time

Logback cũng có `TimeBasedRollingPolicy`:

```xml
<rollingPolicy class="ch.qos.logback.core.rolling.TimeBasedRollingPolicy">
    <fileNamePattern>logs/archive/app.%d{yyyy-MM-dd}.log.gz</fileNamePattern>
    <maxHistory>7</maxHistory>
    <totalSizeCap>1GB</totalSizeCap>
    <cleanHistoryOnStart>true</cleanHistoryOnStart>
</rollingPolicy>
```

Đây là đoạn **thay thế phần rollingPolicy** trong một `RollingFileAppender`, không phải một appender hoàn chỉnh. Nó giới hạn thời gian và tổng archive, **không đặt ngưỡng kích thước từng file active**. Theo hướng dẫn Logback, chỉ dùng `SizeAndTimeBasedRollingPolicy` khi thật sự cần file-size rollover, vì cấu trúc có thêm công việc rename và các trường hợp cần giám sát.

### Rollover theo ngày không nhất thiết chạy đúng 00:00

Trong Logback, rollover dựa trên **sự kiện log tới**. Nếu không có event sau nửa đêm, rollover có thể chờ đến event tiếp theo. Vì vậy đừng dùng Logback rolling policy như hệ thống scheduler chính xác từng giây để thực thi yêu cầu xóa dữ liệu có thời hạn chặt.

## 6. Log4j2 RollingFile: trigger riêng, retention riêng

Log4j2 Core cung cấp `RollingFileAppender` với **triggering policies** và **rollover strategy**. Một cấu hình mẫu có cả time-based và size-based rollover:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<Configuration status="WARN">
    <Appenders>
        <RollingFile name="APP"
                     fileName="logs/app.log"
                     filePattern="logs/archive/app-%d{yyyy-MM-dd}-%i.log.gz">
            <PatternLayout pattern="%d{ISO8601} %-5p %c - %m%n"/>
            <Policies>
                <TimeBasedTriggeringPolicy interval="1"/>
                <SizeBasedTriggeringPolicy size="50MB"/>
            </Policies>
            <DefaultRolloverStrategy max="20">
                <Delete basePath="logs/archive" maxDepth="1" testMode="true">
                    <IfFileName glob="app-*.log.gz"/>
                    <IfLastModified age="P7D"/>
                </Delete>
            </DefaultRolloverStrategy>
        </RollingFile>
    </Appenders>
    <Loggers>
        <Root level="info">
            <AppenderRef ref="APP"/>
        </Root>
    </Loggers>
</Configuration>
```

**Cấu hình trên cố ý để `testMode="true"`: không xóa file, chỉ kiểm thử danh sách ứng viên** theo cơ chế Status Logger. Nó là bản khởi đầu để quan sát hành vi; muốn có retention thực sự phải kiểm tra glob, tên file, đường dẫn, quyền, thời hạn, pháp lý rồi **chủ động kích hoạt delete qua thay đổi có phê duyệt** (ví dụ điều chỉnh `testMode` theo tài liệu phiên bản đang dùng). Đừng sao chép và tưởng archive đã tự hết hạn khi vẫn ở test mode.

Các điểm dễ nhầm:

- `SizeBasedTriggeringPolicy` quyết định **khi nào rollover**; `TimeBasedTriggeringPolicy` quyết định rollover theo kỳ thời gian từ pattern.
- Kết hợp time và size cần **`%d` và `%i`** trong `filePattern`; nếu chỉ có ngày, các lần rollover trong cùng ngày dễ đụng tên file.
- `DefaultRolloverStrategy max="20"` là giới hạn **chỉ số vòng quay archive theo chiến lược**, không tương đương hard quota “tổng tối đa 20 file cho mọi ngày” hoặc retention 20 ngày.
- `Delete` dùng đường dẫn và các `PathCondition` để nhận diện file archive đủ điều kiện; trong ví dụ còn yêu cầu tên match và `lastModified >= 7 ngày`.
- `IfLastModified` đo **file modification time**, không nhất thiết là timestamp của từng event bên trong file.
- Delete action được thực thi theo **rollover mechanism**, không chạy độc lập như cron mỗi mili giây.
- Nếu dùng namespace, multi-tenant hoặc nhiều dịch vụ cùng thư mục, một glob quá rộng có thể xóa nhầm file không liên quan.

**Đừng coi `testMode="false"` là một chỉ thị chung có thể áp dụng bất cứ đâu.** Đây là property cụ thể của Log4j2 Delete action; trước khi bật xóa thật phải kiểm tra tài liệu và test với **phiên bản ứng dụng đang triển khai**.

## 7. JUL: `FileHandler` với `limit` và `count`

Không phải ứng dụng Java nào cũng dùng Logback/Log4j2. `java.util.logging.FileHandler` (JUL) của JDK hỗ trợ xoay vòng một tập file theo dung lượng.

Ví dụ:

```java
// Trích đoạn áp dụng trong ứng dụng đã có logger + lifecycle quản lý.
java.util.logging.FileHandler bounded =
        new java.util.logging.FileHandler(
                "logs/app-%g.log", 10_000_000, 5, true);
bounded.setLevel(java.util.logging.Level.ALL);
bounded.setFormatter(new java.util.logging.SimpleFormatter());

logger.addHandler(bounded);
// Khi shutdown, detach và close handler ở thời điểm thích hợp.
```

Giải thích:

- `limit=10_000_000` là **giới hạn xấp xỉ theo byte cho từng file**, không phải 10 MiB chính xác.
- `count=5` là số file trong vòng quay, file cũ có thể bị thay thế khi tiếp tục ghi.
- `%g` là generation index; pattern còn có `%u` để tránh xung đột tên file giữa những FileHandler khi phù hợp.
- `append=true` quyết định cách xử lý file tồn tại, không thay việc giới hạn số generation.
- JUL `FileHandler` không tự cung cấp chính sách archive theo ngày hoặc yêu cầu pháp lý: nếu cần lưu lâu, phải thiết kế pipeline riêng.

**Anti-pattern thường gặp trong JUL:** constructor `new FileHandler("logs/app.log", true)` tạo file với **limit=0 (không giới hạn) và count=1** theo mô tả JDK. Khả năng tạo handler thành công không có nghĩa đã có bảo vệ dung lượng.

Một ví dụ khác trong `logging.properties`:

```properties
handlers=java.util.logging.FileHandler
.level=INFO

java.util.logging.FileHandler.pattern=logs/app-%g.log
java.util.logging.FileHandler.limit=10000000
java.util.logging.FileHandler.count=5
java.util.logging.FileHandler.append=true
java.util.logging.FileHandler.level=INFO
java.util.logging.FileHandler.formatter=java.util.logging.SimpleFormatter
```

Cần kiểm tra file config có thực sự được `LogManager` của JVM load và handler được gắn đúng vào logger/hierarchy. Đặt properties nhưng ứng dụng dùng backend Logback (không nối JUL tương ứng) có thể không cho kết quả như mong muốn.

## 8. Java 17 runnable: kiểm chứng xoay file bằng JUL

Ví dụ dưới dùng **JDK 17 thuần**, không cần thư viện ngoài. Nó:

1. Tạo **thư mục tạm riêng** bằng `Files.createTempDirectory`.
2. Gắn `FileHandler` với giới hạn **1.024 byte/file** và **3 generation**.
3. Phát 150 record ngắn để thực sự kích hoạt rollover.
4. Đóng handler, đếm file `event-*.log` và xác minh chỉ có 3 file có dữ liệu.
5. Xóa **đúng các file trong thư mục tạm do demo tạo** rồi in kết quả cố định.

Bài demo chỉ chứng minh **tập file quay vòng có giới hạn số lượng**, không chứng minh hard disk quota, an toàn audit hay retention theo thời gian. Dữ liệu cũ sẽ **bị thay thế** khi file quay vòng: điều này đúng với cơ chế bounded rotation, nhưng cần xem yêu cầu bảo toàn event của hệ thống thật.

Tạo file **`BoundedJulLogDemo.java`**:

```java
import java.nio.file.DirectoryStream;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Locale;
import java.util.logging.FileHandler;
import java.util.logging.Formatter;
import java.util.logging.Level;
import java.util.logging.LogRecord;
import java.util.logging.Logger;

public final class BoundedJulLogDemo {
    private static int exercise(Path directory) throws Exception {
        Logger logger = Logger.getLogger("demo.bounded.rotation");
        logger.setUseParentHandlers(false);
        logger.setLevel(Level.INFO);

        Path pattern = directory.resolve("event-%g.log");
        FileHandler handler =
                new FileHandler(pattern.toString(), 1024, 3, false);
        handler.setLevel(Level.ALL);
        handler.setFormatter(new Formatter() {
            @Override
            public String format(LogRecord record) {
                return record.getLevel().getName() + " "
                        + record.getMessage() + "\n";
            }
        });

        logger.addHandler(handler);
        try {
            for (int i = 0; i < 150; i++) {
                String id = String.format(Locale.ROOT, "%03d", i);
                logger.info("event=processed request_id=req_" + id);
            }
            handler.flush();
        } finally {
            logger.removeHandler(handler);
            handler.close();
        }

        int files = 0;
        try (DirectoryStream<Path> stream =
                     Files.newDirectoryStream(directory, "event-*.log")) {
            for (Path path : stream) {
                files++;
                if (Files.size(path) <= 0L) {
                    throw new AssertionError("Empty log generation");
                }
            }
        }
        if (files != 3) {
            throw new AssertionError("Expected three log generations");
        }
        return files;
    }

    public static void main(String[] args) throws Exception {
        Path directory =
                Files.createTempDirectory("jul-rotation-demo-");
        int files;
        try {
            files = exercise(directory);
        } finally {
            // Xóa chỉ thư mục tạm riêng do chương trình vừa tạo.
            try (DirectoryStream<Path> stream =
                         Files.newDirectoryStream(directory)) {
                for (Path path : stream) {
                    Files.deleteIfExists(path);
                }
            }
            Files.deleteIfExists(directory);
        }

        System.out.println("records_emitted=150");
        System.out.println("configured_limit_bytes=1024");
        System.out.println("configured_generations=3");
        System.out.println("rotated_files=" + files);
        System.out.println("verification=PASS");
    }
}
```

Biên dịch/chạy:

```bash
javac --release 17 BoundedJulLogDemo.java
java BoundedJulLogDemo
```

**Stdout khi chạy thành công:**

```text
records_emitted=150
configured_limit_bytes=1024
configured_generations=3
rotated_files=3
verification=PASS
```

**Điều cần hiểu về kiểm thử này:**

- `logger.setUseParentHandlers(false)` ngăn nhân đôi log ra console từ parent handler.
- Handler in file dưới dạng hai thành phần `INFO` và message; không phụ thuộc locale/timestamp của `SimpleFormatter`.
- Với 150 bản ghi có kích thước đã biết, chương trình tạo đủ dữ liệu để file vượt ngưỡng nhiều lần và dùng cả ba generation.
- `FileHandler` có thể ghi hơi vượt `limit` do kiểm tra theo record/điểm rollover; test **không** khẳng định một hard cap chính xác 1.024 byte.
- `FileHandler` sẽ ghi đè một số log cũ khi số generation đã đủ, do vậy số file có giới hạn **không** đồng nghĩa giữ mọi event.
- Thư mục tạm được dọn sau khi handler đã đóng. Chạy trong môi trường có quyền tạo/xóa file tạm; đừng chạy bằng quyền administrator/root nếu không cần.
- Đừng thay `directory` bằng thư mục production hay thêm code xóa file log thật để học về rotation.

## 9. Giới hạn file không giải quyết mọi bản sao log

Một service có thể ghi:

```text
Application logger
      │
      ├── local rolling file  ──────────────► filesystem quota
      │           │
      │           └── file tailer/collector ─► central backend/index
      │                                         │
      │                                         └── archive / backup / export
      └── stdout/stderr ────────────────────► container/node log
                                                │
                                                └── collector
```

**Một sự kiện có thể có nhiều bản sao.** Local file được giới hạn 1 GB, nhưng backend giữ 90 ngày và có backup khác; tổng dung lượng lưu vẫn tăng theo policy riêng. Hoặc application đồng thời ghi stdout và file, collector lại thu cả hai khiến duplicate và gấp đôi ingest.

Retention cần nêu rõ:

- **Local active + archives:** ai rotation và cleanup?
- **Node/container runtime:** stdout/stderr giữ bao nhiêu file?
- **Collector buffer/spool:** khi backend mất kết nối, log tạm ở đâu và bao lâu?
- **Search index/data stream:** index lifecycle dựa trên index age/rollover hay event timestamp?
- **Object archive:** expire, versioning, legal hold, snapshots, restore policy?
- **Exports:** CSV, notebook, ticket attachment và backup có thời hạn riêng không?

**Không nhầm “đã xóa file tại nguồn” với “đã xóa dữ liệu nhạy cảm khỏi toàn bộ hệ thống”.** Nếu vô tình ghi token, cần xử lý rò rỉ/rotate credential và tìm các bản sao chứ không chỉ giảm `maxHistory`.

## 10. Kubernetes và container: stdout không có nghĩa vô hạn

Trong Kubernetes, cách phổ biến là ứng dụng ghi `stdout/stderr`, container runtime chuyển thành log file trên node và **kubelet quản lý rotation**. Các tham số cấu hình node là:

```yaml
# Trích đoạn tham số cấu hình kubelet minh họa;
# không phải Pod manifest hoặc Java config.
containerLogMaxSize: 10Mi
containerLogMaxFiles: 5
```

Tài liệu Kubernetes mô tả giá trị mặc định thường là **10Mi** và **5 file**, nhưng cấu hình thực của cluster có thể khác. Đây là chính sách **node-local log rotation**, không phải thời gian lưu search backend.

Điểm vận hành:

1. `kubectl logs` có thể chỉ đọc file log hiện hành/gần nhất; đừng dùng nó làm nguồn lịch sử dài hạn.
2. Pod bị xóa/evict hoặc node mất có thể làm mất log cục bộ; nếu cần giữ dài, dùng collector và backend tập trung.
3. Log riêng được ứng dụng ghi vào volume không tự được kubelet rotate chỉ vì stdout có rotation.
4. Tốc độ log có thể vượt tốc độ kubelet/collector xử lý, dẫn đến node disk pressure hoặc mất phần log chưa ingest.
5. Nếu dùng sidecar “tail file rồi in stdout”, có thể tạo **hai bản sao** trên node. Phải xác định chính sách rõ.
6. Đừng thay node-wide quota để chữa một ứng dụng spam ERROR mà không điều tra nguồn phát.

**Kubernetes rotation và Java rolling file giải quyết hai nơi khác nhau.** Đặc biệt nếu ứng dụng tự cấu hình `RollingFileAppender` ghi tới `/app/logs` trên persistent volume, chính sách kubelet container logs không quản lý volume đó.

## 11. logrotate bên ngoài: tránh xung đột với appender

Trên Linux VM, đôi khi có `logrotate` của hệ điều hành. Nếu Java đã dùng RollingFileAppender riêng, **không nên để hai bộ rotation tranh quyền quản lý cùng một file** nếu chưa thiết kế và kiểm thử.

Hai cơ chế hay gặp:

- **rename + reopen:** công cụ ngoài đổi tên file và yêu cầu process mở lại file mới. Java logger không tự hiểu signal như mọi daemon Linux; nếu không reopen, process có thể tiếp tục ghi vào file descriptor cũ.
- **copytruncate:** công cụ ngoài copy file rồi truncate file gốc để process tiếp tục ghi. Giữa copy và truncate có một khoảng race có thể **mất log events**. Không dùng cho kênh audit yêu cầu bảo toàn mà không đánh giá rủi ro.

Nếu dùng logrotate cho Java, cần xác minh backend hỗ trợ kiểu rotation đó, log shipper phát hiện inode/file changes, permission sau rotation và khả năng mất/trùng. **Ưu tiên một chủ thể chịu trách nhiệm rotation cho mỗi source file**.

Không dùng `rm` hoặc `truncate` trên file active để “xử lý nhanh” khi thiếu disk: ngoài việc mất bằng chứng, một file đã unlink có thể vẫn chiếm dung lượng đến khi process đóng descriptor.

## 12. File growth, inode và disk quota

Disk đầy không chỉ do dung lượng byte:

- **File lớn:** một `app.log` chiếm nhiều GB.
- **File count quá cao:** một ngày tạo hàng trăm nghìn file nhỏ có thể hết inode.
- **Shared filesystem:** ứng dụng log, database, temp, heap dump và crash files cùng tranh tài nguyên.
- **Hidden copies:** container layers, snapshots, collector spool, file đã bị unlink nhưng process còn mở.
- **Compression:** cần CPU/I/O và đôi khi chỗ tạm; chưa chắc giải phóng disk ngay.
- **Replica:** central backend có thể nhân dung lượng index; local quota không ảnh hưởng replica.

**Quan sát an toàn bằng lệnh read-only** (Linux/VM; sửa đường dẫn theo môi trường, cần quyền phù hợp):

```bash
df -h
df -i
du -sh /var/log/myapp
find /var/log/myapp -maxdepth 1 -type f -printf '%s %p\n'
# Nếu được phép chẩn đoán descriptor trên Linux:
lsof +L1
```

Lệnh trên chỉ là **gợi ý kiểm tra**, không cung cấp bằng chứng hoàn chỉnh khi filesystem mount/overlay khác nhau hoặc container bị cô lập. `lsof +L1` có thể hiển thị file đã unlink nhưng còn mở; không được mặc định process nào cũng có quyền chạy.

Đối với Kubernetes:

```bash
kubectl -n prod get pods -l app=myapp -o wide
kubectl -n prod describe pod myapp-0
kubectl -n prod logs deployment/myapp --since=10m --tail=100
```

Tên namespace, pod, labels là **placeholder minh họa cho lệnh vận hành**, không phải đối tượng hiện có trên cluster. `kubectl logs deployment/myapp` có thể không lấy toàn bộ log của mọi replica; cần kiểm theo pod/container cụ thể.

Không dùng các lệnh **xóa/chỉnh** trực tiếp trong bước đầu; ưu tiên xác định file, owner, pattern, lifecycle và quyền giữ dữ liệu trước.

## 13. Khi đã gần đầy disk: playbook xử lý an toàn

**Mục tiêu:** khôi phục khả năng ghi và bảo vệ dịch vụ mà **không xóa nhầm log còn cần cho điều tra/audit**.

### Giai đoạn 1 — Khoanh vùng

1. Xác định filesystem/mount nào đầy, process nào đang ghi, volume còn bao nhiêu byte/inode.
2. Kiểm log growth: một file active, archive, stdout/node, collector spool hay index/backend?
3. Kiểm appender startup/status errors, effective logger level, các thay đổi cấu hình/deploy gần đây.
4. Xác định sự cố nghiệp vụ tạo WARN/ERROR storm, brute-force hoặc retry loops; đây có thể là **nguyên nhân cần sửa**, không chỉ là volume vấn đề.
5. Xác định loại log có yêu cầu retention/audit/legal hold để tránh mất chứng cứ.

### Giai đoạn 2 — Giảm rủi ro mà không phá bằng chứng

- Nếu DEBUG/TRACE không cần thiết vừa bật, cân nhắc hoàn nguyên **đúng logger/package** theo change record đã phê duyệt.
- Sửa code spam lặp hoặc thay event bằng aggregate/metric có nghĩa, không bỏ security/audit event bắt buộc.
- Nếu cần thêm dung lượng/volume hoặc tách filesystem, làm theo quy trình infra có quota/giám sát và kế hoạch quay lại.
- Dùng công cụ retention **chính chủ** của file/index/archive; có dry-run, phạm vi glob rõ, phê duyệt khi liên quan audit.
- Nếu phải xóa dữ liệu, xác minh archive/backup, legal hold, quyền và tác động đến collector tail offset **trước** khi thay đổi.
- Tránh restart hàng loạt khi chưa biết khởi động lại có làm queue in-memory mất log hay không.

### Giai đoạn 3 — Khôi phục và xác minh

- Xác minh filesystem free bytes/inodes trở lại vùng an toàn và không còn tăng đến ngưỡng nguy hiểm.
- Kiểm event mới xuất hiện ở local source, collector và backend dự kiến; queue lag/drops giảm.
- Đo p95/p99, CPU, GC, I/O và throughput của nghiệp vụ.
- Kiểm security/audit event quan trọng còn đầy đủ theo mức có thể đối soát.
- Kiểm retention policy thực thi qua rollover/startup, không chỉ “đã sửa XML”.
- Ghi rõ có dữ liệu nào đã mất hoặc chưa xác nhận được; tránh hứa không mất nếu chỉ kiểm event mới.

**Đặc biệt:** file đã bị xóa nhưng process còn giữ descriptor có thể tiếp tục chiếm disk. Chẩn đoán bằng công cụ phù hợp và chỉ restart/reopen khi được phép, đã tính ảnh hưởng shutdown và backlog.

## 14. Retention và audit: giới hạn không có nghĩa được phép mất mọi log cũ

Một hệ thống quản lý thay đổi vai trò, đăng nhập hoặc giao dịch có thể cần audit trail lâu hơn debug log. Một cấu hình file quay vòng 3 generation **không phù hợp** nếu nó làm mất các sự kiện bắt buộc trước khi được lưu bền vững.

| Loại dữ liệu | Mục tiêu | Policy mẫu cần phê duyệt |
| --- | --- | --- |
| DEBUG/TRACE | Chẩn đoán gần đây | Có thể ngắn, có sampling/rotation |
| APPLICATION/ERROR | Điều tra vận hành | Rolling local + backend đủ ngày |
| HTTP_ACCESS | Phân tích request/latency | Metadata an toàn, retention phù hợp |
| SECURITY_EVENT | Phát hiện hành vi xấu | Kênh bảo vệ, giám sát mất log |
| AUDIT | Trách nhiệm/đối soát | Lưu bền, phân quyền riêng, khả năng giữ chứng cứ |

**Không có số ngày mặc định hợp lệ cho mọi tổ chức**; tuân thủ yêu cầu nghiệp vụ, hợp đồng, ngành và pháp luật liên quan. Nếu có legal hold, không được tự xóa dữ liệu chỉ vì đến `maxHistory`. Thường cần tách audit khỏi appender file ngắn hạn và ghi vào pipeline có quy tắc lưu giữ phù hợp.

Một số thiết kế dùng **transactional outbox** hoặc audit store chuyên dụng để ghi trạng thái nghiệp vụ cùng event trong một transaction. Điều đó giải quyết bài toán bền vững ở một ranh giới, nhưng vẫn cần retry/duplicate handling, access control, retention và monitoring downstream.

## 15. Nên giới hạn **số lượng event** nhưng phải giữ đúng tín hiệu

Dù file rotation đã bật, một lỗi lặp hàng nghìn lần/giây vẫn làm CPU, I/O, disk, collector và phí ingest tăng.

Những cách giảm volume:

- Đặt logger level hợp lý; không để DEBUG toàn root trên production lâu dài.
- Không log raw request/response body, token, headers hoặc DTO `toString()` chứa PII.
- Dùng **structured fields ngắn**, event ID, outcome, mã lỗi và route template.
- Gộp log lặp có kiểm soát: ví dụ báo `retry_failed_count=100` mỗi một khoảng thời gian, đồng thời giữ sample đại diện.
- Với thông tin diagnostic tần suất cao, dùng metrics/histograms thay vì mỗi lần ghi log.
- Sampling theo event class có thể phù hợp với debug traffic nhưng **không nên tùy tiện sampling security/audit events bắt buộc**.
- Khi async logging queue đầy, phải biết appender sẽ **block, discard hay spool**; không xem mất log là giảm dung lượng miễn phí.

**Đừng dùng rate limit để che lỗi nghiệp vụ.** Nếu WARN tăng đột biến vì database không trả lời, xử lý root cause đồng thời giảm noise một cách có chủ đích.

## 16. Async appender và tác động của disk-full

Synchronous file appender có thể làm request thread chậm vì ghi file. Async appender giảm một số chi phí ở producer nhưng **không làm disk vô hạn biến mất**:

```text
Producer ──► Bounded queue ──► Consumer ──► File appender
                 │               │              │
                 │               │          disk / quota
                 │               │              │
              full queue ◄──── sink slow/error ─┘
                 │
           block / discard / fallback
```

**Các chính sách có đánh đổi:**

- **Block:** bảo toàn nhiều event hơn trong một số tình huống nhưng có thể khiến request p99 tăng hoặc service không sẵn sàng.
- **Discard:** giúp request tiếp tục nhưng event bị mất; không phù hợp cho audit bắt buộc nếu không có cơ chế khác.
- **Spool disk:** đệm được khi network hỏng, nhưng càng cần quota và cleanup độc lập.
- **Sync fallback:** có thể làm latency bùng nổ đúng lúc sink đang chậm.

Khi JVM bị kill, queue in-memory có thể mất dữ liệu chưa flush. Một file rotation “đẹp” không chứng minh event end-to-end được bảo toàn.

## 17. Các thước đo và cảnh báo cần đặt

Các metric bên dưới là **đề xuất instrumentation**, không phải tên mặc định của mọi logger:

| Tín hiệu | Cảnh báo khi |
| --- | --- |
| `log_file_active_bytes` | File active lớn bất thường so với policy |
| `log_archive_total_bytes` | Archive gần cap hoặc cleanup không giảm |
| `log_archive_file_count` | Số file tăng không có giới hạn |
| `filesystem_free_bytes` | Free space dưới ngưỡng an toàn |
| `filesystem_free_inodes` | Inode thấp dù disk bytes còn |
| `log_bytes_written_rate` | Tốc độ tăng đột ngột sau deploy |
| `logging_events_dropped_total` | Event bị mất vì policy hoặc lỗi |
| `logging_queue_depth` | Queue tăng lâu dài |
| `logging_sink_write_errors_total` | Appender gặp permission/ENOSPC/I/O error |
| `collector_ingest_lag_seconds` | Source có event nhưng backend chậm |
| `collector_spool_bytes` | Spool tăng đe dọa node disk |
| `archive_cleanup_errors_total` | Rollover/delete/permission thất bại |
| `last_successful_rollover_timestamp` | Không rollover như kỳ vọng |
| `audit_event_gap_count` | Có lỗ hổng nếu hệ thống định nghĩa sequence đáng tin |

Đối với disk, **dùng cả tỷ lệ phần trăm và số byte còn lại**, vì filesystem rất nhỏ/ rất lớn có ngưỡng thực tế khác nhau. Có thể đặt forecast “time to full” dựa trên tốc độ tăng gần đây, nhưng chỉ dùng như ước lượng vì traffic thay đổi.

Không cho request ID, trace ID, filename tùy ý hoặc user ID thành metric label cardinality vô hạn.

### SLO và policy enforcement

Một số kiểm tra có thể có dạng:

- File active không tăng mãi qua nhiều kỳ rollover.
- Sau archive cleanup, số byte archive nằm trong policy đã công bố ở trạng thái ổn định.
- Không có file hết hạn **quá lâu** mà chưa xử lý, ngoại trừ legal hold hợp lệ.
- Log ingestion và audit có độ trễ trong ngưỡng đã đồng ý.
- Không có tình huống disk-full khiến application database/temporary storage bị hỏng do tranh filesystem.
- Mỗi thay đổi retention và quyền delete có change record hoặc audit.

**Không hứa “maxFileSize=50MB nên file không bao giờ vượt 50MB đúng một byte”.** Cần đo theo ngưỡng thích hợp, accounting toàn bộ active+archive+temp+other writers và cleanup latency.

## 18. Kiểm thử regression: chứng minh có rotation và retention

### Kiểm thử Logback/Log4j2 trên filesystem tạm

1. Chạy service/fixture với **đúng phiên bản backend thực tế** và một directory test riêng, không dùng production.
2. Đặt threshold nhỏ để phát vài trăm event **không chứa secret**; kiểm rollover được kích hoạt.
3. Kiểm file active và archive pattern, file index, compression, encoding và event ID.
4. Tạo nhiều kỳ thời gian trong fixture bằng cơ chế phù hợp, không cần đợi nhiều ngày; xác minh policy cleanup khi rollover hoặc startup.
5. Kiểm `maxHistory` theo **kỳ thời gian**, không mặc định số file.
6. Kiểm `totalSizeCap` trên **archive**; tính cả file active và temporary files trong capacity test riêng.
7. Xác minh archive không chứa event trùng/thiếu ngoài semantics đã định; khi xoay file nhanh, collector không bỏ sót tail offset.
8. Đặt file ngoài glob và khẳng định cleanup **không xóa nhầm**.
9. Thử permission denied, rename/compress failure và disk pressure trong môi trường cô lập.
10. Đối chiếu event ở nguồn với backend (ingest) nếu hệ thống có collector.
11. Kiểm cảnh báo khi appender không khởi tạo hoặc rotation policy không có hiệu lực.
12. Kiểm khi application restart/deploy rollout, vì cleanup có thể chỉ diễn ra sau rollover/startup.

### Boundary và negative tests

| Case | Kết quả cần chứng minh |
| --- | --- |
| Chỉ có FileAppender, không rolling | Test preflight/config linter đánh dấu anti-pattern |
| `maxFileSize` có nhưng không retention | Archive tăng → test policy FAIL |
| `maxHistory=0` của Logback | Không tự xóa archive theo tuổi, cần policy khác |
| Kết hợp daily + size rollover | Có `%d` và `%i`, nhiều file trong một ngày không đè nhầm |
| Đúng lúc rollover | Không hỏng file active hoặc mất event ngoài policy |
| Một event cực dài | Rollover có thể vượt ngưỡng xấp xỉ, event size cap hoạt động |
| Disk đầy | Có cảnh báo, ứng dụng theo failure policy đã test |
| Không có log trong nhiều giờ | Cleanup đúng semantics, không giả định cron chính xác |
| Collector bị chặn | Node/app archive có đủ spool, biết lúc nào mất event |
| Multiple process cùng file | Không vô tình cùng ghi không có cơ chế hỗ trợ |
| Legal hold/audit | Không xóa dữ liệu bắt buộc theo policy debug |
| Restore từ backup | Retention được kiểm tra lại, không hồi sinh dữ liệu quá hạn ngoài policy |
| File cũ không match glob | Được báo/điều tra, không xóa bừa toàn directory |
| JVM chết lúc compression | Có khả năng phát hiện lỗi/giữ bản copy phù hợp |
| Release thay backend version | Config rolling và retention vẫn hợp lệ |

### Bài thử dữ liệu bằng canary

Chỉ dùng chuỗi **giả** như `FAKE_SECRET_CANARY_479` trong fixture. Mục tiêu là chắc không ai dùng việc “dọn log” để thay thế **không ghi secret từ đầu**. Trước khi đi vào sink, loại những field nhạy cảm ở nguồn. Không dùng token thật để thử.

## 19. Chống xóa nhầm khi dùng glob hoặc retention job

Một tác vụ cleanup không có scope tốt nguy hiểm không kém thiếu cleanup:

```text
/var/log/apps/
   checkout/
       checkout.2026-11-10.0.log.gz
   identity/
       audit.2026-11-10.log.gz
```

Nếu đặt `Delete basePath="/var/log/apps"` cùng glob `*.log.gz` quá rộng, có thể xóa audit của service khác. **Tách thư mục/namespace theo owner và retention class**, áp quyền xóa tối thiểu, giới hạn `maxDepth`/pattern, kiểm tra symbolic links và dùng dry-run trước khi bật.

Không tùy tiện chạy shell scripts như `find /var/log -type f -mtime +7 -delete` trên server production. Một lệnh rộng có thể xóa sai thời hạn, sai owner, sai timezone/mtime và sai dữ liệu có legal hold.

Nếu cần điều chỉnh retention, thực hiện theo change process:

1. Inventory file/index/owner, policy hiện tại.
2. Chạy **dry-run**, liệt kê candidates, tổng byte và legal hold exceptions.
3. Xác nhận dữ liệu còn cần cho incident/audit đã lưu ở nơi đúng.
4. Phê duyệt phạm vi và điều kiện rollback/escalation.
5. Triển khai ít một, kiểm count/size trước và sau.
6. Audit ai đổi và theo dõi bất thường.
7. Đối soát source/archive/backend và kế hoạch phục hồi.

## 20. Anti-pattern liên quan cần tránh

| Anti-pattern | Vì sao nguy hiểm? | Thay bằng |
| --- | --- | --- |
| `FileAppender` duy nhất, không rolling | Active file tăng mãi | RollingFileAppender hoặc host rotation rõ |
| Chỉ giới hạn từng file | Archive vẫn có thể không giới hạn | maxHistory/size cap/retention |
| `maxHistory` theo ngày nhưng traffic một ngày rất lớn | Active/archives một kỳ có thể quá lớn | Thêm size-based rolling nếu có nhu cầu |
| Tăng DEBUG toàn root vô thời hạn | Volume, CPU, PII rủi ro tăng | Scope package, duration/rollback, safe fields |
| Log full request/response ở production | Event lớn, rò bí mật | Structured allowlist fields |
| Rotate cả ứng dụng và logrotate cùng file | Race, FD sai, mất/trùng dữ liệu | Một owner rotation |
| `copytruncate` cho audit bắt buộc | Có khoảng race làm mất dòng | Audit sink bền vững, thiết kế reopen đúng |
| Chỉ kiểm `kubectl logs` | Lịch sử node hạn chế, không đủ backend | Central ingestion + retention |
| Xóa file active để giải phóng disk | Mất chứng cứ, có thể không giải phóng byte | Playbook disk-full có kiểm soát |
| Tin file cap là disk quota | Active/temp/other apps vẫn chiếm disk | Quota và disk alerts riêng |
| Sampling toàn bộ log kể cả audit | Mất event có nghĩa vụ giữ | Chính sách khác nhau theo event kind |
| Bỏ cleanup vì “storage rẻ” | Rủi ro privacy/retention, chi phí tăng | Data lifecycle policy |
| Chỉ dọn index, không dọn snapshots | Bản sao dữ liệu vẫn tồn tại | Inventory retention end-to-end |
| Test quota bằng file production | Có thể gây outage | Test temp/namespace cô lập |
| Dùng tên file từ client input | Path injection hoặc vượt quyền | Static directory/pattern, validated IDs |

## 21. Thiết kế khuyến nghị theo môi trường

### Java chạy trên VM

Có thể dùng RollingFileAppender/FileHandler được cấu hình, thư mục lưu riêng hoặc quota filesystem, cảnh báo free space/inodes và collector tail file. Phải xác định **ai là owner của rotation** (Java appender hay logrotate). Nếu có audit bắt buộc, thiết kế kênh riêng không phụ thuộc chỉ vào file debug ngắn hạn.

### Java trong Docker/Kubernetes

Thường ưu tiên stdout/stderr cùng node-level rotation và ship log tập trung; nếu ứng dụng vẫn ghi local file, phải có rolling/cleanup và volume policy riêng. Đánh giá việc ghi hai nơi có gây duplicate không. Backend logging có thời hạn retention độc lập với kubelet.

### Hệ thống có logging tập trung

Collector/index/object storage phải có lifecycle, quota, retention class và metrics lag/drop. Một file appender giới hạn tốt không bảo vệ được backend nếu ingest rate/retention tăng vô hạn. Dùng structured log với schema ổn định và hạn chế PII ngay tại nguồn.

### Hệ thống audit hoặc yêu cầu bằng chứng

Không lấy số file rolling làm cam kết lưu chứng cứ. Cần event ID, actor/outcome đáng tin, transactional semantics khi cần, lưu bền vững, tách quyền và legal hold/retention theo nghiệp vụ. Xóa/archive phải có chứng cứ và được phê duyệt.

## 22. Quy trình rollout từ file vô hạn sang file có giới hạn

Không thay cấu hình trực tiếp rồi tin mọi dữ liệu sẽ tự an toàn. Quy trình:

1. **Đo hiện trạng:** byte/s, event/s, disk free, archives, backend retention và rủi ro dữ liệu nhạy cảm.
2. **Phân loại:** application/debug/access/security/audit logs; chọn thời hạn và mức ưu tiên từng lớp.
3. **Chọn owner:** appender, runtime, logrotate hay collector chịu rotation; tránh hai nơi cùng chỉnh một file.
4. **Thiết kế cấu hình:** rolling theo size/time, retention/total archive cap, quota và alert.
5. **Test config trong staging:** startup status, rollover, compression, cleanup, permission, log shipper.
6. **Đánh giá thay đổi về audit/retention:** không đè log cần giữ, xác định legal hold và bản sao.
7. **Rollout ít instance trước:** so disk usage, event rate, collector lag và request latency.
8. **Kiểm tra active file + archive + tmp + deleted-open files:** đừng chỉ xem kích thước một file.
9. **Xác minh backend có event mới:** không mất dữ liệu do file tail rotation/inode changes.
10. **Bật alert và tài liệu vận hành:** ai nhận cảnh báo, threshold, playbook disk full, rollback owner.
11. **Kiểm lại sau ngày rollover đầu tiên và một chu kỳ retention:** cleanup có diễn ra như dự kiến?
12. **Lưu change record:** ai sửa config, vì sao, cách rollback và rủi ro còn lại.

Một migration có thể cần giữ file lịch sử cũ trước khi áp policy mới. Không xóa các file cũ không match pattern mới một cách tự phát; phải xác định owner và yêu cầu lưu giữ.

## 23. Câu hỏi tự kiểm tra

**1. Cấu hình `maxFileSize=50MB` đủ để đảm bảo disk không đầy không?**

Không. Nó chỉ kích hoạt rollover theo kích thước file active. Archive, file khác, temporary files, node stdout logs và backend copies vẫn có thể tăng. Cần retention, quota và monitoring.

**2. `maxHistory=7` của Logback nghĩa là giữ đúng 7 file không?**

Không. Với date pattern theo ngày, đó là 7 **kỳ ngày archive**. Một ngày có thể có nhiều file nếu kết hợp size-based rolling.

**3. File `app.log` đang ghi có thể bị xóa bằng shell để tăng dung lượng ngay không?**

Không nên. Hành động có thể mất log và chưa chắc thu hồi disk nếu file descriptor còn mở. Trước hết chẩn đoán, đánh giá nhu cầu giữ chứng cứ và dùng playbook có chủ sở hữu.

**4. Tại sao chỉ giới hạn file local không bảo đảm retention toàn hệ thống?**

Vì collector, backend index, archive, snapshot, backup, export và container stdout có **vòng đời riêng**.

**5. Bật DEBUG ngắn hạn có nguy hiểm nếu file đã rotate?**

Có. DEBUG có thể tăng I/O, queue lag, log ingest cost và vô tình lộ token/PII. Rotation không xử lý tính bí mật của từng event.

**6. Một file lớn có thể là đúng trong hệ thống nào?**

Có thể, nếu app cố ý ghi vào file và host/collector chịu rotation, retention đã được kiểm thử, có quota, giám sát và policy nghiệp vụ phù hợp. **Anti-pattern là thiếu bảo vệ hiệu lực**, không phải việc API dùng `FileAppender` trong mọi tình huống.

## 24. Checklist code review và vận hành

- [ ] Không có file log active tăng vô hạn mà không có rotation owner.
- [ ] Có policy cho **file size** và **số kỳ/tuổi/tổng archive** phù hợp.
- [ ] Biết `maxFileSize` là ngưỡng rollover, không phải filesystem quota.
- [ ] Hiểu `maxHistory` theo kỳ ngày khi dùng date pattern, không nhầm số file.
- [ ] Hiểu cleanup được chạy khi rollover/startup hoặc cơ chế được thiết kế, không hứa xóa đúng giây.
- [ ] Có disk/volume quota hoặc cảnh báo free bytes, inode và time-to-full.
- [ ] Không cho nhiều process/pod vô tình ghi chung một file không hỗ trợ.
- [ ] Không đồng thời dùng appender rolling và logrotate tranh quyền trên cùng file.
- [ ] Nếu dùng Kubernetes, đã tách node stdout rotation và file riêng trong pod/volume.
- [ ] Đã kiểm tra collector tail offset sau rollover, không để mất/trùng event.
- [ ] Có policy khác nhau cho DEBUG, application, security và audit log.
- [ ] Không dùng rotation/retention thay cho loại bỏ password, token và PII ở nguồn.
- [ ] Có runbook disk full, lỗi compression/rename, collector lag và sink error.
- [ ] Đã test rollover, nhiều archive trong một ngày, restart, failure và retention.
- [ ] Xóa archive có glob/path hạn chế, quyền tối thiểu và dry-run trước khi bật.
- [ ] Có owner, change record, monitoring, rollback và kiểm tra sau rollout.
- [ ] Bản lưu ở backend, archive, snapshot và export có vòng đời riêng.
- [ ] Audit và legal hold không bị xóa theo policy ngắn hạn của debug log.

**Ghi nhớ:** file log không giới hạn là một **anti-pattern về tài nguyên và độ tin cậy**, không chỉ về dung lượng. Để sửa đúng phải giới hạn **file đang ghi, số lượng/tổng archive, tốc độ dữ liệu, dung lượng hạ tầng và vòng đời ở backend**, đồng thời bảo vệ security/audit event. Rotation là một cơ chế, còn **retention + quota + monitoring + kiểm thử** mới tạo thành biện pháp vận hành đủ tin cậy.

### Tài liệu tham khảo

- [Logback — RollingFileAppender, TimeBasedRollingPolicy, SizeAndTimeBasedRollingPolicy](https://logback.qos.ch/manual/appenders-rolling.html)
- [Logback — Appenders, lifecycle và error status](https://logback.qos.ch/manual/appenders.html)
- [Apache Log4j2 — Rolling file appenders, triggering policies, Delete action](https://logging.apache.org/log4j/2.x/manual/appenders/rolling-file.html)
- [Oracle Java 17 — java.util.logging.FileHandler](https://docs.oracle.com/en/java/javase/17/docs/api/java.logging/java/util/logging/FileHandler.html)
- [Kubernetes — Logging architecture và container log rotation](https://kubernetes.io/docs/concepts/cluster-administration/logging/)
- [OWASP — Logging Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html)
- [NIST SP 800-92 — Guide to Computer Security Log Management](https://csrc.nist.gov/pubs/sp/800/92/final)
