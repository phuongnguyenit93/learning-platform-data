# Tên file động trong Java Logging (Dynamic Log File Names)

## 1. Tên file động là gì?

**Tên file động** trong file logging là tên hoặc đường dẫn của file log được quyết định bởi một **giá trị thay đổi theo môi trường hoặc theo ngữ cảnh thực thi**, thay vì luôn cố định như `logs/application.log`. Giá trị đó có thể là tên dịch vụ, instance ID, môi trường triển khai, mã job/batch đã kiểm soát, kỳ thời gian hoặc một khóa định tuyến.

Ví dụ:

~~~text
Tên cố định:
logs/application.log

Tên xác định khi khởi động ứng dụng:
logs/application-node-02.log
logs/application-staging.log

Tên được chọn theo job đang xử lý:
logs/jobs/job-import-17.log
logs/jobs/job-export-04.log

Tên archive thay đổi khi rollover:
logs/archive/application.2026-11-09.0.log.gz
~~~

Những ví dụ trên mô tả **ba cơ chế khác nhau**. Không phải cứ đường dẫn có biến là appender sẽ tự thay file theo từng lời gọi logger.

- **Startup-time naming:** giá trị được thay khi tải cấu hình hoặc tạo appender. Ví dụ mỗi instance ghi một file.
- **Event-time routing:** một appender điều phối chọn appender/file tương ứng theo giá trị nằm trong ngữ cảnh **của từng event**. Ví dụ Logback `SiftingAppender` hoặc Log4j2 `RoutingAppender`.
- **Rolling/archiving:** tên file archive thay đổi theo ngày/giờ và chỉ số khi rollover. Đây là *đặt tên archive*, không nhất thiết tạo file khác cho từng tenant/job.

Bài học giải thích cách chọn đúng cơ chế, ví dụ Java 17 độc lập với JUL, cách cấu hình Logback/Log4j2, bảo vệ đường dẫn, giới hạn số file và kiểm tra khi log không xuất hiện đúng nơi.

## 2. Vì sao cần tên file động?

Một ứng dụng có thể cần phân biệt log giữa các nhóm xử lý:

| Mục tiêu | Ví dụ | Cơ chế thường phù hợp |
| --- | --- | --- |
| Mỗi instance một file | `service-node-a.log` | Property khi khởi động |
| Mỗi môi trường một file | `orders-staging.log` | Biến môi trường hoặc cấu hình deployment |
| Mỗi batch job một file | `job-reconcile-17.log` | Tạo handler theo job hoặc routing dựa trên MDC/ThreadContext |
| Archive theo ngày/size | `orders.2026-11-09.2.log.gz` | Rolling policy/strategy |
| Gửi một số loại sự kiện đến file riêng | `audit.log`, `error.log` | Logger/AppenderRef/filter/marker, không nhất thiết cần tên file động |
| Theo dõi request qua nhiều file | `requestId` như một trường của log | Thường **không** tạo một file cho mỗi request; dùng correlation ID + collector |

Lợi ích khi dùng đúng cách: tách log phù hợp yêu cầu, tránh nhiều instance tranh chấp một file, hỗ trợ tìm kiếm log của job và quản lý file theo vòng đời.

Nhược điểm: mỗi file có thể tạo file descriptor, buffer, appender hoặc worker riêng; nhiều tên file gây **cardinality cao**, tăng số file cần xoay vòng/dọn dẹp, khó thu thập và có thể mở ra lỗ hổng nếu tên file bắt nguồn từ dữ liệu không tin cậy.

**Quy tắc quan trọng:** nếu chỉ cần **tìm log theo requestId**, thường ghi `requestId` trong structured logging/MDC và dùng một luồng log chung hiệu quả hơn việc tạo hàng nghìn file riêng.

## 3. Phân biệt interpolation lúc khởi động và routing lúc phát sự kiện

Giả sử có cấu hình file:

~~~xml
<file>logs/app-${INSTANCE_ID}.log</file>
~~~

Trong XML của Logback, phần `${INSTANCE_ID}` (sau khi thay bằng đúng cú pháp property của framework) được xử lý khi cấu hình appender được tạo. Khi chương trình đã chạy, việc một thread đặt MDC `INSTANCE_ID` sang giá trị khác **không khiến FileAppender thông thường tự chuyển sang file mới**.

Ngược lại, với appender định tuyến theo event:

~~~text
Event A (jobKey=import-17) ---> Router ---> FileAppender A
Event B (jobKey=export-04) ---> Router ---> FileAppender B
Event C (jobKey=import-17) ---> Router ---> FileAppender A
~~~

Router đọc khóa của event, lấy hoặc tạo appender con phù hợp. Đây là cách sử dụng để có **tên file thay đổi theo ngữ cảnh runtime**.

### 3.1. Không đồng nhất tên file với tên logger

Logger `example.OrderService` xác định nguồn phát sự kiện; nó không nhất thiết tương ứng một file. Nhiều logger có thể ghi cùng file, và một logger có thể gửi event tới nhiều file tùy appender/filter. Đổi tên logger không tự tạo file mới nếu không có cấu hình định tuyến tương ứng.

### 3.2. Rolling filename không phải per-request filename

Một `RollingFileAppender` có `fileNamePattern` chứa `%d{yyyy-MM-dd}` và `%i` chỉ tự đổi tên **archive khi rollover**. Nó không có nghĩa mỗi event INFO sẽ mở một file mang requestId mới. Muốn kết hợp per-job filename với rolling, cần đặt RollingFileAppender trong cơ chế routing/sifting phù hợp và kiểm soát số appender được tạo.

## 4. Nguyên tắc an toàn với giá trị đặt tên file

Tên file động thường nhận giá trị từ biến môi trường, đối số lệnh, message queue hoặc một HTTP request. **Đây là đầu vào có thể không đáng tin**. Không nên làm:

~~~java
// Sai: rawJobId có thể chứa dấu /, .., ký tự điều khiển, tên quá dài.
Path file = Path.of("logs", rawJobId + ".log");
~~~

Giá trị `../secrets`, `C:\...`, dấu `/`, `\`, `:`, ký tự Unicode không mong đợi hoặc dấu `%` (có ý nghĩa đặc biệt với JUL FileHandler) có thể làm đường dẫn lệch mục tiêu, gây lỗi runtime hoặc tạo cấu trúc file ngoài dự kiến.

### 4.1. Dùng khóa nội bộ đã kiểm tra

Một chính sách ví dụ cho mã job:

~~~text
Chỉ cho phép A-Z, a-z, 0-9, "_" và "-"
Độ dài từ 1 đến 32 ký tự
Không có dấu "." hoặc ký tự phân cách đường dẫn
Không chứa email, token, mã xác thực, tên người dùng đầy đủ
~~~

Mã kiểm tra trong Java:

~~~java
// Minh họa trong lớp có biến rawKey.
if (!rawKey.matches("[A-Za-z0-9_-]{1,32}")) {
    throw new IllegalArgumentException("Invalid job key");
}
~~~

Nếu yêu cầu hỗ trợ tên hiển thị có dấu hoặc ký tự đặc biệt, nên tạo **mã nội bộ an toàn** riêng để đặt tên file, còn nhãn gốc được xử lý theo chính sách dữ liệu và lưu thành trường log nếu thực sự cần.

### 4.2. Giữ thư mục đích cố định và có quyền truy cập phù hợp

Dùng thư mục cấu hình của ứng dụng như `logs/jobs`. Khi xây đường dẫn, có thể chuẩn hóa bằng `Path.normalize()` và xác minh đường dẫn ở trong thư mục gốc cho phép. Nhưng kiểm tra chuỗi/normalize **không tự bảo vệ khỏi symbolic link, mount hoặc race ở filesystem không tin cậy**. Thư mục ghi phải được kiểm soát quyền, không cho người dùng ngoài thay thế file hoặc symlink.

### 4.3. Giới hạn cardinality

Khóa có thể hợp lệ về ký tự nhưng vẫn tạo hàng triệu giá trị khác nhau. Ví dụ `requestId=req-unique-...` là dữ liệu thích hợp để **tìm kiếm log**, nhưng thường không phải lựa chọn tốt để **tạo một file/appender riêng cho mỗi request**.

Giới hạn số job hoạt động, số appender con, timeout của appender, tổng dung lượng lưu và retention. Tách biệt **file mở đang hoạt động** với **file archive cũ**: đóng appender không đồng nghĩa tự xóa file.

## 5. Ví dụ Java 17 chạy độc lập: JUL FileHandler và jobKey động

`java.util.logging` (JUL) có sẵn trong JDK, nên có thể dùng `FileHandler` tạo file theo một khóa đã xác thực **lúc khởi tạo handler**. Ví dụ này không cần Maven hay SLF4J/Logback/Log4j2.

Tạo tệp **DynamicFileNameDemo.java**:

~~~java
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.logging.FileHandler;
import java.util.logging.Formatter;
import java.util.logging.Level;
import java.util.logging.LogRecord;
import java.util.logging.Logger;

public final class DynamicFileNameDemo {
    private static final Logger LOG =
            Logger.getLogger(DynamicFileNameDemo.class.getName());

    private DynamicFileNameDemo() {
    }

    private static String validatedJobKey(String raw) {
        if (!raw.matches("[A-Za-z0-9_-]{1,32}")) {
            throw new IllegalArgumentException("Invalid job key");
        }
        return raw;
    }

    public static void main(String[] args) throws IOException {
        String raw = args.length == 0 ? "batch-17" : args[0];
        String jobKey = validatedJobKey(raw);

        Path directory = Path.of("target", "logs");
        Files.createDirectories(directory);
        Path file = directory.resolve("job-" + jobKey + ".log");

        LOG.setUseParentHandlers(false);
        LOG.setLevel(Level.INFO);

        FileHandler handler = new FileHandler(file.toString(), true);
        handler.setLevel(Level.INFO);
        handler.setFormatter(new Formatter() {
            @Override
            public String format(LogRecord record) {
                return record.getLevel().getName() + " "
                        + formatMessage(record)
                        + System.lineSeparator();
            }
        });
        LOG.addHandler(handler);

        try {
            LOG.log(Level.INFO, "jobKey={0} phase={1}",
                    new Object[] {jobKey, "started"});
            LOG.log(Level.INFO, "jobKey={0} processed={1}",
                    new Object[] {jobKey, 3});
        } finally {
            LOG.removeHandler(handler);
            handler.close();
        }

        System.out.println("logFile=target/logs/job-" + jobKey + ".log");
        System.out.println("events=2");
    }
}
~~~

Biên dịch và chạy trong thư mục muốn tạo `target/logs`:

~~~bash
javac -encoding UTF-8 DynamicFileNameDemo.java
java DynamicFileNameDemo
~~~

**Stdout của một lần chạy thành công với khóa mặc định:**

~~~text
logFile=target/logs/job-batch-17.log
events=2
~~~

File `target/logs/job-batch-17.log` trong lần chạy đầu với một file mới, không bị tiến trình khác giữ, chứa:

~~~text
INFO jobKey=batch-17 phase=started
INFO jobKey=batch-17 processed=3
~~~

Ví dụ đặt formatter JUL riêng với `formatMessage(record)`, vì JUL dùng `{0}`/`{1}` để parameter hóa message. Hai dòng INFO đi tới file chứ không tới console: chương trình đã gọi `LOG.setUseParentHandlers(false)` và chỉ gắn FileHandler.

Chạy lại cùng khóa khi file tồn tại: do `append=true`, có thể có thêm hai dòng được nối vào file. **Không khẳng định file luôn có đúng hai dòng** sau nhiều lần chạy. Ngoài ra JUL FileHandler dùng cơ chế lock và có thể sinh hậu tố `%u` để tránh xung đột nếu file đang bị tiến trình khác sử dụng; trong tình huống đồng thời, đường dẫn thực tế có thể khác đường mong đợi. Demo giả định một tiến trình ghi trong thư mục thuộc quyền ứng dụng.

### 5.1. Chọn một tên khác lúc chạy

~~~bash
java DynamicFileNameDemo import-42
~~~

**Stdout**:

~~~text
logFile=target/logs/job-import-42.log
events=2
~~~

File tương ứng được chọn lúc handler khởi tạo, không theo từng event. Lệnh này **không tạo hoặc xóa file cũ** của `batch-17`.

Thử khóa không hợp lệ:

~~~bash
java DynamicFileNameDemo ../unsafe
~~~

Chương trình ném `IllegalArgumentException("Invalid job key")` trước khi tạo FileHandler; stack trace và exit code của lệnh này phụ thuộc cách JVM hiển thị uncaught exception. Không dùng một transcript stack trace cố định để làm expected output.

### 5.2. Vì sao dùng try/finally, không dùng try-with-resources?

`java.util.logging.FileHandler`/`Handler` ở Java 17 **không triển khai `AutoCloseable`**, dù có phương thức `close()`. Vì vậy một cấu trúc `try (FileHandler handler = ...)` **không biên dịch** như một resource trong try-with-resources. Demo dùng `try/finally` để chắc chắn tháo handler khỏi logger và đóng handle/file lock.

Cách đóng là quan trọng khi một tiến trình tạo handler cho nhiều job theo thời gian. Không để tất cả handler tồn tại mãi trong logger hoặc bỏ quên lock file.

### 5.3. Các mẫu đặc biệt trong JUL FileHandler

FileHandler hiểu một số ký hiệu **trong pattern tên file**:

| Ký hiệu | Ý nghĩa |
| --- | --- |
| `%t` | Thư mục tạm của hệ thống |
| `%h` | Home directory theo cấu hình hệ thống |
| `%g` | Generation index khi rotation |
| `%u` | Unique index để xử lý file đang bị khóa/xung đột |
| `%%` | Dấu phần trăm nguyên văn |

Ví dụ:

~~~java
// Minh họa: tối đa 3 file generation, gần 1 MiB mỗi file.
FileHandler rotation = new FileHandler(
        "target/logs/job-" + jobKey + "-%u.%g.log",
        1_048_576, 3, true);
~~~

Dòng trên là snippet trong phương thức có `jobKey` đã validate và thư mục đã tạo. Sau khi sử dụng phải tháo khỏi logger và gọi `rotation.close()` trong `finally`. `%g` và `%u` không phải cú pháp thời gian/ngày; JUL FileHandler không có cùng chính sách `fileNamePattern`/`maxHistory` như Logback.

## 6. Logback: đặt tên file động theo biến khi khởi động

Với **SLF4J + Logback**, một `FileAppender` hoặc `RollingFileAppender` có thể dùng property substitution lúc Logback đọc `logback.xml`.

Ví dụ `logback.xml` đơn giản:

~~~xml
<configuration>
    <appender name="INSTANCE_FILE"
              class="ch.qos.logback.core.FileAppender">
        <file>logs/service-${INSTANCE_ID:-local}.log</file>
        <append>true</append>
        <encoder>
            <pattern>%d{yyyy-MM-dd HH:mm:ss.SSS} %-5level %logger - %msg%n</pattern>
            <charset>UTF-8</charset>
        </encoder>
    </appender>

    <root level="INFO">
        <appender-ref ref="INSTANCE_FILE"/>
    </root>
</configuration>
~~~

Dấu `${INSTANCE_ID:-local}` là cú pháp **Logback property substitution** với giá trị dự phòng `local` khi property không được đặt. Sau khi biến được thay, appender ghi vào một đường dẫn xác định. Ví dụ:

~~~bash
java -DINSTANCE_ID=node-02 -cp "..." example.Main
~~~

Đây chỉ là **lệnh minh họa tham số JVM**, không phải lệnh chạy độc lập vì classpath `...` và `example.Main` phụ thuộc dự án. Với property `INSTANCE_ID=node-02`, tên file dự kiến là `logs/service-node-02.log`. Không có property, tên dự kiến là `logs/service-local.log`.

**Giới hạn quan trọng:** Logback FileAppender thông thường không tự thay `INSTANCE_ID` theo MDC của mỗi log event. Nó nhận tên file khi appender được tạo; việc đổi MDC trong thread sau đó không chuyển file. Giá trị property do môi trường triển khai cấp cần được kiểm soát/chuẩn hóa trước khi dùng để đặt đường dẫn.

Cách này phù hợp để tách file **theo pod/instance**, môi trường hoặc job mà mỗi tiến trình chỉ xử lý một khóa trong cả vòng đời ứng dụng.

### 6.1. Property từ nguồn nào?

Logback hỗ trợ những nguồn property/configuration như thuộc tính JVM `-D...`, biến môi trường và properties được khai báo trong cấu hình, với quy tắc tra cứu cụ thể. Không đồng nhất với `System.getenv` của Java; người vận hành phải kiểm tra thực tế tên biến, giá trị mặc định và phạm vi.

Khi cấu hình có thể reload, việc thay property có thể dẫn tới appender mới được tạo; tuy nhiên **không nên dùng reload liên tục như một cơ chế routing cho từng request**. Định tuyến theo event có công cụ riêng.

### 6.2. RollingFileAppender với tên file theo instance

Có thể kết hợp property startup trong cả active file và archive:

~~~xml
<!-- Minh họa đặt bên trong <configuration>. -->
<appender name="ROLLING"
          class="ch.qos.logback.core.rolling.RollingFileAppender">
    <file>logs/service-${INSTANCE_ID:-local}.log</file>

    <rollingPolicy
        class="ch.qos.logback.core.rolling.TimeBasedRollingPolicy">
        <fileNamePattern>logs/archive/service-${INSTANCE_ID:-local}.%d{yyyy-MM-dd}.log.gz</fileNamePattern>
        <maxHistory>7</maxHistory>
        <totalSizeCap>200MB</totalSizeCap>
    </rollingPolicy>

    <encoder>
        <pattern>%d %-5level %logger - %msg%n</pattern>
    </encoder>
</appender>
~~~

Archive đổi theo ngày và instance, nhưng **không theo requestId**. `maxHistory=7` giới hạn số kỳ lịch sử tính theo độ hạt của `%d`, không có nghĩa luôn đúng bảy file; `totalSizeCap` giới hạn archive thuộc policy, không bao gồm mọi file trên volume. Cần cấu hình `appender-ref` ở logger/root để sự kiện đến appender này.

## 7. Logback: SiftingAppender đặt file theo từng job

Để tạo file theo một khóa runtime như `jobKey`, Logback Classic cung cấp **SiftingAppender**. Nó đọc giá trị thông qua **discriminator**, chọn appender con đã tồn tại hoặc tạo mới theo template trong `<sift>`.

Ví dụ `logback.xml` dành cho các **jobKey đã được chuẩn hóa**:

~~~xml
<configuration>
    <appender name="JOB_SIFT"
              class="ch.qos.logback.classic.sift.SiftingAppender">
        <timeout>15 minutes</timeout>
        <maxAppenderCount>64</maxAppenderCount>

        <discriminator>
            <key>jobKey</key>
            <defaultValue>unassigned</defaultValue>
        </discriminator>

        <sift>
            <appender name="FILE-${jobKey}"
                      class="ch.qos.logback.core.FileAppender">
                <file>logs/jobs/job-${jobKey}.log</file>
                <append>true</append>
                <encoder>
                    <pattern>%d{HH:mm:ss.SSS} %-5level jobKey=%X{jobKey} %msg%n</pattern>
                    <charset>UTF-8</charset>
                </encoder>
            </appender>
        </sift>
    </appender>

    <root level="INFO">
        <appender-ref ref="JOB_SIFT"/>
    </root>
</configuration>
~~~

Trong Logback Classic, discriminator mặc định của `SiftingAppender` là `MDCBasedDiscriminator` khi không ghi rõ class. Nó sử dụng `jobKey` từ MDC; nếu thiếu thì dùng `defaultValue=unassigned`, nhờ đó tránh xuất một đường dẫn rỗng.

Mã Java đặt scope (snippet trong service có logger SLF4J `LOG` và hàm `validatedJobKey`):

~~~java
// Cần org.slf4j.MDC và logger SLF4J hợp lệ.
String key = validatedJobKey(rawJobKey);
org.slf4j.MDC.put("jobKey", key);
try {
    LOG.info("job started");
    executeJob();
    LOG.info("job completed");
} finally {
    org.slf4j.MDC.remove("jobKey");
}
~~~

Nếu `key=import-42`, các event trong scope thông thường đi tới `logs/jobs/job-import-42.log`; khi key đổi thành `export-04` ở một scope khác, SiftingAppender chọn một appender con khác.

Đây là **routing theo event**, khác với cách thay property `INSTANCE_ID` lúc khởi động ở mục 6. Việc khóa đã được validate và có vòng đời scope rõ ràng là thiết yếu.

### 7.1. Không dùng raw request ID, username hay tenant ID tùy ý

Ví dụ chỉ thích hợp với tập khóa tương đối nhỏ và có quản lý. Nếu một hệ thống có một triệu request/ngày và mỗi request mang `jobKey` riêng, SiftingAppender có thể tạo rất nhiều appender/file. Không nên mở riêng file cho từng request chỉ vì có thể làm được.

Thông số `timeout` giúp appender con không được dùng trong một thời gian được đóng/gỡ khỏi bộ nhớ; `maxAppenderCount` (trong những phiên bản Logback hỗ trợ) đặt giới hạn số appender con được quản lý. **Chúng không phải chính sách xóa file đã tạo trên đĩa**. Cần retention và dọn dẹp storage riêng.

Một appender con có thể đóng rồi được tạo lại khi khóa xuất hiện lần sau; với `append=true`, file cũ có thể được nối tiếp. Kiểm tra chính sách concurrency và thread-safety, đặc biệt nếu nhiều instance cùng ghi một đường dẫn.

### 7.2. Scope MDC và thread pool

MDC thường gắn với thread. Nếu một worker thread được tái sử dụng cho job khác mà không gọi `MDC.remove("jobKey")`, log của job sau có thể đi nhầm file của job trước. `finally` là yêu cầu quan trọng.

Khi một job chuyển qua `CompletableFuture`, executor hay thread khác, ngữ cảnh không mặc định tự được truyền. Cần cơ chế context propagation do framework cung cấp hoặc tự bao nhiệm vụ truyền/khôi phục context phù hợp, rồi dọn thread context. Đừng chỉ đặt MDC ở thread nhận request và giả định mọi thread khác đều thấy cùng giá trị.

### 7.3. Kết hợp SiftingAppender với rolling

Thay `FileAppender` con trong `<sift>` bằng `RollingFileAppender` có thể đặt file active và archive riêng từng job. Khi đó `fileNamePattern` cần phân biệt được job và các kỳ rollover, ví dụ `logs/jobs/archive/job-${jobKey}.%d{yyyy-MM-dd}.%i.log.gz` nếu dùng size-and-time policy.

Tuy nhiên **mỗi job có một rolling appender riêng** có nghĩa mỗi job cũng mang chi phí file active, archive và retention. Với cardinality lớn, console + structured logging có trường jobKey và collector thường dễ vận hành hơn.

## 8. Log4j2: RoutingAppender theo ThreadContext

**Apache Log4j 2** có **RoutingAppender**, lựa chọn một route/appender theo khóa được tính từ log event. Với ứng dụng dùng Log4j API trực tiếp, `ThreadContext` cung cấp các trường được ghi cùng event.

Mã sử dụng (snippet trong service đã có Log4j2 `LOG` và key đã validate):

~~~java
// Cần log4j-api, LOG và validatedJobKey(...).
String key = validatedJobKey(rawJobKey);
org.apache.logging.log4j.ThreadContext.put("jobKey", key);
try {
    LOG.info("job started");
    executeJob();
    LOG.info("job completed");
} finally {
    org.apache.logging.log4j.ThreadContext.remove("jobKey");
}
~~~

Cấu hình `log4j2.xml` ví dụ:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<Configuration status="WARN">
    <Appenders>
        <Routing name="JOB_ROUTER">
            <Routes pattern="$${ctx:jobKey}">
                <Route>
                    <File name="JOB-${ctx:jobKey}"
                          fileName="logs/jobs/job-${ctx:jobKey}.log"
                          append="true">
                        <PatternLayout pattern="%d{HH:mm:ss.SSS} %-5p jobKey=%X{jobKey} %m%n"/>
                    </File>
                </Route>
            </Routes>
        </Routing>
    </Appenders>

    <Loggers>
        <Root level="INFO">
            <AppenderRef ref="JOB_ROUTER"/>
        </Root>
    </Loggers>
</Configuration>
~~~

**Cú pháp lookup trong RoutingAppender rất quan trọng:**

- `<Routes pattern="$${ctx:jobKey}">` dùng **hai dấu `$`** trong cấu hình Log4j2 để trì hoãn lookup route key cho tới lúc xử lý event.
- Bên trong `<Route>`, thuộc tính appender con dùng **một dấu `$`**, ví dụ `fileName="logs/jobs/job-${ctx:jobKey}.log"`, vì chúng được đánh giá khi appender con động được tạo cho route đó.
- Route không có `key` là default route: trong kiểu cấu hình trên nó có thể tạo một appender con cho từng giá trị route key.

**Phạm vi ví dụ:** chỉ dùng khi code đã đặt `jobKey` hợp lệ trong ThreadContext trước mỗi event tới router. Trong ứng dụng thực tế phải thiết kế **fallback cho event không có khóa** (ví dụ một appender chung được tham chiếu bằng một route phù hợp) và cách kiểm soát khóa để tránh file có tên không hợp lệ. Không cho giá trị từ HTTP/request được dùng trực tiếp trong tên file mà không kiểm tra.

Không viết `${ctx:jobKey}` vào thuộc tính `fileName` của một `File`/`RollingFile` thông thường đặt ngoài `RoutingAppender` rồi giả định tên file đổi theo từng event. Ở appender thông thường, các thuộc tính khởi tạo file không nhất thiết được đánh giá lại khi mỗi log event tới.

### 8.1. Quản lý vòng đời các route

RoutingAppender có thể tạo appender động theo nhiều khóa. Với Log4j2 phù hợp, `IdlePurgePolicy` giúp đóng các route đã không được sử dụng trong thời gian nhất định. Điều này giúp giảm số appender còn mở nhưng **không phải tự xóa file trên đĩa**.

Khi dùng RoutingAppender theo tenant/job, cần xem:

- Số route đang hoạt động và số appender/file descriptor.
- Hành vi khi một khóa không còn phát sự kiện.
- Số file đã tạo và chiến lược dọn dẹp archive.
- Các event ghi vào ThreadContext, async context propagation và việc làm sạch.
- Thao tác rollover, xóa file và collector khi appender đóng/mở lại.

### 8.2. RoutingAppender kết hợp RollingFile

Nếu mỗi job cần archive theo ngày và kích thước, có thể thay appender `File` bên trong `<Route>` bằng `RollingFile` cùng `<Policies>`. Ví dụ **phần appender con để thay thế**, không phải một file XML độc lập:

~~~xml
<RollingFile name="JOB-${ctx:jobKey}"
             fileName="logs/jobs/job-${ctx:jobKey}.log"
             filePattern="logs/jobs/archive/job-${ctx:jobKey}.%d{yyyy-MM-dd}.%i.log.gz">
    <PatternLayout pattern="%d %-5p %m%n"/>
    <Policies>
        <TimeBasedTriggeringPolicy interval="1"/>
        <SizeBasedTriggeringPolicy size="10MB"/>
    </Policies>
    <DefaultRolloverStrategy max="10"/>
</RollingFile>
~~~

`%d` biểu thị kỳ thời gian và `%i` phân biệt archive cùng kỳ khi đạt size threshold. Trong Log4j2, `DefaultRolloverStrategy max="10"` liên quan cửa sổ chỉ số archive theo strategy, **không đơn giản có nghĩa giữ 10 ngày**. Nếu cần xóa archive theo tuổi hay tổng dung lượng, phải cấu hình hành động dọn file phù hợp và kiểm tra trong môi trường thử nghiệm.

## 9. Phương án đơn giản hơn khi chỉ cần lọc/tìm theo job

Không phải mọi yêu cầu “động” đều thực sự yêu cầu **file vật lý riêng**. Nếu cần tìm những event thuộc một job, thường có thể giữ **một file hoặc một luồng JSON chung**, nhưng đính kèm trường `jobKey`:

~~~text
2026-11-09T10:00:00Z INFO jobKey=import-42 operation=read count=150
2026-11-09T10:00:01Z INFO jobKey=export-04 operation=write count=50
2026-11-09T10:00:02Z WARN jobKey=import-42 operation=read retry=1
~~~

Đây là dữ liệu minh họa. Một log collector/engine tìm kiếm có thể lọc theo field `jobKey` mà không cần hàng nghìn file khác nhau, **nếu encoder và pipeline thực sự giữ jobKey như field có cấu trúc**. Một message `jobKey=...` chỉ là text nếu hệ thống không parse thành field.

Khi cần file riêng vì quy định tổ chức, phân quyền hoặc workflow batch offline, routing vẫn phù hợp. Nhưng nên xác định rõ ai sở hữu file, khi nào file đóng, bao lâu được giữ và nó được thu thập ra sao.

## 10. Đặt tên file an toàn trong hệ thống nhiều instance

Giả sử ba instance cùng tạo `logs/jobs/job-import-42.log` trên một network filesystem. Cùng tên job là chưa đủ để tránh va chạm. Nhiều tiến trình có thể ghi đồng thời, gây vấn đề file lock, reorder, corruption hoặc xung đột rollover. Vì thế thiết kế nên có khóa **instance** trong đường dẫn:

~~~text
logs/node-01/jobs/job-import-42.log
logs/node-02/jobs/job-import-42.log
logs/node-03/jobs/job-import-42.log
~~~

Tên instance cần được chuẩn hóa theo cùng tiêu chí an toàn. Nếu hạ tầng dùng container, xem xét việc ghi stdout và gom log tập trung theo các trường service, pod, job thay vì cố tạo/mount một cấu trúc file chia sẻ trên nhiều node.

**Không coi tên file động là bảo đảm cô lập bảo mật.** Nếu tất cả file trong một volume có cùng quyền đọc, việc tách file theo tenant không tự ngăn truy cập chéo. Cần filesystem permissions, ownership và chính sách collector, không dựa vào tên file.

### 10.1. Tên archive và retention

Khi dùng rolling:

~~~text
Active:  logs/node-01/jobs/job-import-42.log
Archive: logs/node-01/jobs/archive/job-import-42.2026-11-09.0.log.gz
~~~

Rollover không nhất thiết xảy ra ngay theo đồng hồ nếu không có event mới; retention có thể được thực thi khi rollover/khởi động hoặc theo chính sách cụ thể. Giới hạn tổng dung lượng archive của một rolling policy không có nghĩa giới hạn mọi file trong volume, đặc biệt khi có **nhiều policy/appender con**.

### 10.2. Không tạo tên file từ timestamp độ phân giải quá cao cho từng event

Một kiểu thiết kế nguy hiểm:

~~~text
logs/app-20261109T104201001.log
logs/app-20261109T104201002.log
logs/app-20261109T104201003.log
...
~~~

Nếu mỗi event lại có tên riêng, hệ thống có thể tạo hàng nghìn file nhỏ mỗi giây. Đó không phải cách thay thế thích hợp cho việc ghi log event liên tục. Timestamp chỉ nên dùng trong phạm vi **chu kỳ file** được định nghĩa bằng rolling policy hoặc một batch có vòng đời rõ ràng.

## 11. Hiệu năng và vận hành

| Rủi ro | Vì sao xảy ra | Hướng xử lý |
| --- | --- | --- |
| Quá nhiều file descriptor | Mỗi route/job mở một appender/file | Giới hạn route đang hoạt động; đóng appender idle |
| Nhiều file nhỏ | Khóa job/request có cardinality cao | Gộp vào structured log chung, không tách per request |
| Log đi sai file | MDC/ThreadContext còn dữ liệu từ tác vụ cũ | Dùng `finally` và context propagation đúng |
| File không được mở | Permission, path sai, không có thư mục | Kiểm tra startup status và đường dẫn thực |
| Dữ liệu bị phân tán | Tên file thay đổi không được agent phát hiện | Cấu hình collector nhận diện pattern và rollover |
| Va chạm giữa instance | Nhiều tiến trình ghi cùng đường dẫn | Mỗi instance một đường riêng hoặc stdout + collector |
| Không thấy log trong file mong đợi | Handler bị khóa, JUL thêm unique index; router chọn fallback | Kiểm tra lock, route key, appender status |
| Không xóa được file cũ | Thiếu retention hoặc cleanup chỉ chạy lúc rollover | Chính sách lifecycle, giám sát volume |
| Chi phí I/O/CPU cao | Tạo appender, mở file, sync flush, nén archive | Đo p95/p99, bytes/s, allocations và số appender |
| Lộ thông tin nhạy cảm | User input/ID nhạy cảm xuất hiện trong tên file | Dùng khóa nội bộ an toàn, phân quyền và retention |

Khi dùng appender bất đồng bộ, event có thể nằm trong queue trước khi ghi. Thời điểm xuất ra và việc MDC được chụp/truyền phụ thuộc backend/version; phải kiểm tra thực tế. Không mặc định appender async bảo đảm mọi event bền vững khi crash hoặc khi hàng đợi đầy.

## 12. Cách kiểm tra một cấu hình tên file động

1. **Xác định kiểu động:** property lúc startup, routing theo event hay rolling archive? Ghi rõ điểm phát sinh/đánh giá giá trị.
2. **Xác minh nguồn khóa:** là mã job đã validate, instance ID được cấp tin cậy hay raw request input? Không dùng chuỗi chưa chuẩn hóa để tạo path.
3. **Kiểm tra runtime dependencies:** JUL có sẵn trong JDK; Logback và Log4j2 cần đúng dependencies/provider/backend.
4. **Kiểm tra file config:** `logback.xml`, `log4j2.xml` được tải đúng; appender có được gắn vào logger/root không?
5. **Thử hai khóa khác nhau:** ví dụ `import-42` và `export-04`, xác nhận mỗi event tới file đúng; không nhầm file active/archived.
6. **Thử thiếu khóa:** Logback defaultValue có hoạt động không? Với Log4j2 Routing, route fallback có hướng về file chung an toàn không?
7. **Thử khóa không hợp lệ:** chuỗi chứa slash, `..`, ký tự điều khiển hoặc quá dài phải bị từ chối/chuyển thành key nội bộ an toàn.
8. **Thử thread reuse:** kết thúc một job rồi chạy job khác trên cùng executor thread; phải không có event rơi nhầm file.
9. **Thử concurrent instances:** mỗi instance có ownership file, xung đột lock/rollover hoặc suffix `%u` có được xử lý không?
10. **Thử volume lớn và lifecycle:** tạo nhiều khóa hợp lệ trong môi trường test, đo số file mở, queue, rollover, cleanup và dung lượng thực tế.
11. **Kiểm tra collector:** agent có thu thập file mới sinh ra sau startup, rename khi rollover và archive khi nén không?
12. **Kiểm tra bảo mật:** file permission, symlink, đường dẫn, retention và dữ liệu nằm trong cả tên file lẫn nội dung log.

Thay vì kiểm tra duy nhất “file có tồn tại”, cần chắc chắn **đúng sự kiện xuất vào đúng file, không trùng, không thiếu và không để lại tài nguyên không kiểm soát**.

## 13. Các lỗi phổ biến khi dùng tên file động

| Lỗi | Hậu quả | Cách sửa |
| --- | --- | --- |
| Đặt `${jobKey}` vào FileAppender thường rồi đổi MDC | Tên file không đổi theo từng event | Dùng SiftingAppender/RoutingAppender |
| Dùng requestId làm tên file | Vô số appender/file nhỏ | Giữ requestId như field trong log |
| Không sanitize key | Path traversal, ký tự/path không hợp lệ | Whitelist và tạo khóa nội bộ |
| Quên `finally` dọn context | Thread mới ghi log vào file của job cũ | Remove/restore MDC/ThreadContext |
| Không có giá trị fallback | Event thiếu khóa tạo tên file bất thường | Thiết kế route/defaultValue an toàn |
| Tên archive không có `%i` khi cần size+time rolling | Xung đột tên archive cùng kỳ | Dùng pattern thích hợp cho policy |
| Tin rằng `maxHistory` giới hạn mọi file | Volume vẫn phình to do active/khóa khác | Quan sát tất cả file và retention toàn hệ thống |
| Hai JVM ghi chung file | Xung đột lock/rollover | Mỗi instance một file hoặc collector |
| Trông chờ JUL `%u` tạo đúng tên đã chỉ định | Khi file bị lock có thể có suffix | Kiểm tra đường đích và mô hình process |
| Trùng tham chiếu direct + routed appender | Một event có thể được ghi hai lần | Xác định một đường routing tới mỗi đích |
| Tưởng đóng appender là xóa file | File cũ vẫn nằm trên disk | Đặt cleanup/retention riêng |
| Không cho agent biết pattern mới | Log đúng file nhưng không vào hệ thống tìm kiếm | Cấu hình thu thập/detect file động |

## 14. Bài tập thực hành

1. **Phân loại:** `service-node-02.log`, `job-import-42.log` và `service.2026-11-09.log.gz` thuộc loại startup naming, event routing hay archive rolling? Giải thích ranh giới.
2. **Chạy JDK17:** tạo `DynamicFileNameDemo.java`, chạy với mặc định và với đối số `export-04`. Xác nhận stdout và file `target/logs/job-export-04.log`.
3. **Khóa không hợp lệ:** thử `../unsafe`, `a/b`, chuỗi dài hơn 32 ký tự và dấu `%`. Vì sao chương trình phải từ chối?
4. **JUL:** thay constructor FileHandler không xoay thành `new FileHandler(pattern, limit, count, true)` với `%g`, `%u`. Tên file generation và unique index có ý nghĩa gì?
5. **Logback:** giải thích vì sao `${INSTANCE_ID}` trong một FileAppender thông thường không thay đổi khi MDC `jobKey` đổi. Khi nào cần SiftingAppender?
6. **Sifting:** tạo một job với `jobKey=import-42`, một job với `jobKey=export-04`, rồi kiểm tra có hai file riêng. Xác nhận MDC luôn được remove ở `finally`.
7. **Log4j2:** từ RoutingAppender ví dụ, giải thích hai dấu `$` trong `$${ctx:jobKey}` của `Routes pattern` và một dấu `$` ở tên file của appender con.
8. **Cardinality:** một API có 5.000 request/s và mỗi request sinh một tên file. Có thể tạo bao nhiêu file mới trong một phút? Vì sao nên dùng structured log thay thế?
9. **Đa instance:** đề xuất cách đặt file theo cả instance ID và jobKey; nêu rủi ro khi hai JVM cùng ghi một file trên network filesystem.
10. **Production:** thiết kế checklist giám sát file descriptor, file count, disk free, rolling, context leak và collector lag cho hệ thống có tên file động.

## 15. Tài liệu chính thức

- Java SE 17 — `java.util.logging.FileHandler`: https://docs.oracle.com/en/java/javase/17/docs/api/java.logging/java/util/logging/FileHandler.html
- Logback Manual — SiftingAppender: https://logback.qos.ch/manual/appenders-async-sift.html
- Apache Log4j 2 — RoutingAppender: https://logging.apache.org/log4j/2.x/manual/appenders/delegating.html
- Apache Log4j 2 — Configuration/property substitution: https://logging.apache.org/log4j/2.x/manual/configuration.html

**Ghi nhớ:** tên file động có thể được **chốt khi khởi tạo appender**, được **định tuyến theo từng log event**, hoặc được thay đổi chỉ khi **rolling archive**. Trong JUL, khởi tạo FileHandler với khóa an toàn và nhớ đóng handler; trong Logback, dùng property cho file per-instance và SiftingAppender cho per-job; trong Log4j2, dùng RoutingAppender cùng ThreadContext. Trước khi tạo một file mới cho mỗi khóa, hãy kiểm soát **đầu vào, số lượng file, thread context, quyền ghi, retention và thu thập log**.