# Kiểm thử file output trong Java Logging

## 1. Vì sao phải kiểm thử file log thật?

Khi lập trình ứng dụng Java, một lời gọi logger.info hoặc logger.error không tự bảo đảm đã có bản ghi trong file. Sự kiện có thể bị chặn bởi level/filter, logger chưa gắn FileHandler/FileAppender, cấu hình trỏ sang stdout, appender chưa start, dữ liệu còn trong buffer/async queue, file được rotate sang archive, thư mục không writable hoặc logging provider thực tế khác provider mà test dự đoán.

Bài **Kiểm thử file output** thuộc nhóm **Testing logging** giúp xác nhận **kết quả cuối ở file sink**: file có tồn tại, chứa các event mong đợi, đúng encoding/format, không có log bị chặn hoặc bản sao ngoài ý muốn, và tài nguyên được đóng đúng. Kiểm thử lời gọi API và kiểm thử file đầu ra là hai việc khác nhau.

Ví dụ hợp đồng:

~~~text
Logger name: example.orders
Effective level: INFO
File: application.log
Encoding: UTF-8
Format: LEVEL|MESSAGE\n

Input:
  INFO  ĐƠN_HÀNG id=42
  WARN  RETRY attempt=2
  DEBUG DEBUG_IGNORED

Expected file contents (two physical lines):
  INFO|ĐƠN_HÀNG id=42
  WARNING|RETRY attempt=2
~~~

Ví dụ này dùng tên mức WARNING của JUL, thay vì WARN của nhiều backend khác. Nó không phải default output của mọi framework; test phải biết **backend và formatter thật**.

### Kết quả học tập

Sau bài học, bạn sẽ biết cách:

1. Phân biệt mock logger, capturing Handler/ListAppender và integration test file thật.
2. Thiết lập thư mục tạm, đường dẫn độc lập và cleanup an toàn.
3. Chạy một chương trình Java 17 dùng JUL FileHandler rồi đọc/đối chiếu UTF-8.
4. Chuyển cùng nguyên tắc sang JUnit 5 @TempDir.
5. Kiểm tra Logback FileAppender, Log4j 2 FileAppender và cấu hình Spring Boot.
6. Test level/filter, append/truncate, rolling/rotation, async flush và đa luồng.
7. Giảm flaky test do timestamps, sleep, file dùng chung và resource chưa close.
8. Thiết kế test lỗi filesystem, bảo mật, CI và end-to-end theo đúng loại sink.

## 2. Test ở lớp nào?

Pipeline logging đi qua nhiều thành phần:

~~~text
Java code
   |
   +--> Logger API (JUL / SLF4J / Log4j 2)
            |
            v
       Level / Filter / Logger hierarchy
            |
            v
       Log event / MDC
            |
            v
       Formatter / Encoder / Layout
            |
            v
       Handler / Appender
            |
            +--> File / Rolling file
            +--> Console stdout/stderr
            +--> Async queue -> worker -> file
            +--> Remote sink
            |
            v
       Filesystem / container runtime / collector
~~~

| Loại test | Kiểm được | Chưa kiểm được |
| --- | --- | --- |
| Mock logger | Code gọi đúng level và template | File đã được ghi |
| Capturing Handler của JUL | LogRecord thực đã tới handler | Encoding, file path, disk I/O |
| ListAppender của Logback | ILoggingEvent, marker, MDC, throwable | FileAppender và byte output |
| File integration test | File tồn tại, nội dung, charset, flush, close | Collector/cloud backend đã ingest |
| Rolling test | File active/archive, điều kiện rollover | Bản sao ở backend/backup hết hạn |
| Container end-to-end | Runtime/collector nhận log | Đảm bảo tuyệt đối không mất sự kiện khi crash |

Khi yêu cầu là **Kiểm thử file output**, một test chỉ assert mock hoặc ListAppender chưa đủ. Nó có giá trị cho logic logging, nhưng vẫn phải có một test đọc **file thực** từ sink đang cần kiểm chứng.

### Chọn điều kiện PASS rõ ràng

Hợp đồng test nên xác định:

- Đường dẫn file được resolve như thế nào.
- File mới hay append vào file có sẵn.
- Level và filters nào được bật.
- Layout/encoding cụ thể.
- Bao nhiêu event dự kiến và event nào không được ghi.
- Một event có được phép có stack trace nhiều dòng hay không.
- Thời điểm nào file được xem là hoàn tất để đọc (flush/close/drain).
- Có rollover hay async delivery hay không.
- Test có được phép xóa file/archives sau chạy hay không.

Đừng dùng assert files.exists đơn lẻ rồi gọi đó là bằng chứng logging hoạt động. File có thể đã được tạo nhưng rỗng, hoặc là file cũ từ một test trước.

## 3. Thiết kế test fixture an toàn

Một test tốt sử dụng đường dẫn tạm do chính test tạo:

~~~java
// Snippet Java 17, dùng trong phương thức test.
java.nio.file.Path directory =
        java.nio.file.Files.createTempDirectory("log-file-test-");
java.nio.file.Path file = directory.resolve("application.log");
~~~

### Vì sao không dùng file cố định trong source tree?

Nếu test ghi trực tiếp logs/application.log, có thể xảy ra:

- Test A để lại dòng có cùng nội dung nên test B pass giả.
- Hai test parallel cùng append, nội dung xen kẽ hoặc xóa dữ liệu của nhau.
- CI có working directory khác IDE.
- Windows khóa file còn mở nên cleanup thất bại.
- Test vô tình ghi vào log production hoặc xóa file không thuộc sở hữu.
- Test fail giữa chừng để lại file rác hoặc file lock.

Dùng Files.createTempDirectory hoặc JUnit @TempDir tạo đường dẫn riêng mỗi test. Nếu test cần nhiều process cùng ghi, thiết kế fixture và locking riêng; không mặc định đồng bộ trong một JVM có thể thay cho đồng bộ giữa nhiều JVM.

### File handle và cleanup

FileHandler, FileAppender và async appenders có vòng đời start/stop/flush/close. **Đọc sau khi đóng sink** giúp giảm nguy cơ đọc thiếu dữ liệu và giải phóng handle trên Windows. Khi muốn test hành vi stream liên tục mà appender vẫn mở, hãy dùng API flush được hỗ trợ và đồng bộ rõ ràng.

Nếu cleanup, chỉ xóa những file/path mà fixture thực sự tạo ra. Không dùng lệnh xóa đệ quy trên thư mục ứng dụng thật chỉ để dọn logs của test.

### Charset

Chỉ rõ UTF-8 tại encoder/handler và khi đọc:

~~~java
Files.readString(file, StandardCharsets.UTF_8);
Files.readAllLines(file, StandardCharsets.UTF_8);
~~~

Đây là snippet với imports phù hợp. Không dựa vào default charset của nền tảng, nhất là khi có tiếng Việt, dấu quote, escape hoặc ký tự Unicode.

## 4. Chương trình Java 17 độc lập: JUL FileHandler

Ví dụ sau **không cần Maven/Gradle hay thư viện ngoài JDK**. Nó tạo file thật, phát INFO/WARNING/FINE, flush và close FileHandler, đọc lại file UTF-8 và assert nội dung chính xác. Thư mục tạm dùng tên ngẫu nhiên nhưng output chỉ chứa các dòng PASS cố định.

**Tệp: FileOutputTestDemo.java**

~~~java
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;
import java.util.logging.FileHandler;
import java.util.logging.Formatter;
import java.util.logging.Level;
import java.util.logging.LogRecord;
import java.util.logging.Logger;

public final class FileOutputTestDemo {
    private static void require(boolean condition, String reason) {
        if (!condition) {
            throw new AssertionError(reason);
        }
    }

    public static void main(String[] args) throws Exception {
        Path dir = Files.createTempDirectory("jul-file-test-");
        Path file = dir.resolve("application.log");

        try {
            Logger logger =
                    Logger.getLogger("example.testing.fileoutput");
            logger.setUseParentHandlers(false);
            logger.setLevel(Level.INFO);

            FileHandler handler =
                    new FileHandler(file.toString(), false);
            handler.setEncoding(StandardCharsets.UTF_8.name());
            handler.setLevel(Level.ALL);
            handler.setFormatter(new Formatter() {
                @Override
                public String format(LogRecord r) {
                    return r.getLevel().getName() + "|"
                            + formatMessage(r) + "\n";
                }
            });

            logger.addHandler(handler);
            try {
                logger.info("ĐƠN_HÀNG id=42");
                logger.warning("RETRY attempt=2");
                logger.fine("DEBUG_IGNORED");
                handler.flush();
            } finally {
                logger.removeHandler(handler);
                handler.close();
            }

            require(Files.isRegularFile(file), "File not created");

            List<String> lines = Files.readAllLines(
                    file, StandardCharsets.UTF_8);
            List<String> expected = List.of(
                    "INFO|ĐƠN_HÀNG id=42",
                    "WARNING|RETRY attempt=2");

            require(lines.equals(expected),
                    "Wrong file content: " + lines);
            require(Files.size(file) > 0, "File is empty");

            System.out.println("PASS: file exists");
            System.out.println("PASS: UTF-8 content and order");
            System.out.println("PASS: FINE event filtered");
        } finally {
            Files.deleteIfExists(file);
            Files.deleteIfExists(dir);
        }
    }
}
~~~

**Biên dịch và chạy bằng JDK 17 trở lên:**

~~~bash
javac -encoding UTF-8 FileOutputTestDemo.java
java FileOutputTestDemo
~~~

**Stdout chính xác khi máy cho phép tạo file ở thư mục tạm:**

~~~text
PASS: file exists
PASS: UTF-8 content and order
PASS: FINE event filtered
~~~

Không có timestamp hoặc đường dẫn tạm trong stdout. Logger chỉ ghi vào FileHandler; setUseParentHandlers(false) ngăn nó tiếp tục lên root console handler.

### Đọc chi tiết cơ chế

1. **createTempDirectory** tạo một thư mục mới cho lượt chạy, giảm xung đột file cũ.
2. **FileHandler(file.toString(), false)** mở file với append=false. JUL có cơ chế lock và unique filename; vì mỗi lượt chạy có thư mục riêng nên trường hợp tranh lock hầu như được tránh trong demo.
3. **setEncoding(UTF-8)** quy định cách ghi. Cùng charset được dùng trong Files.readAllLines.
4. **Logger level=INFO** loại FINE từ call site. Handler level ALL cho phép hai event đã qua logger filter đi tới file.
5. **Formatter.format** cố định dạng LEVEL|MESSAGE và LF, không thêm timestamp/thread động.
6. **handler.flush** đẩy bộ đệm ở handler theo API; **handler.close** hoàn tất vòng đời trước khi test đọc.
7. **logger.removeHandler** tránh để logger giữ handler đã close.
8. **List.equals** xác nhận đúng hai dòng, thứ tự, dấu tiếng Việt, và không có FINE hoặc event thừa.
9. **Files.size > 0** là positive check bổ sung.
10. **finally cleanup** chỉ xóa file và thư mục do test tạo. Nếu FileHandler không đóng/lock còn giữ, việc xóa có thể thất bại và test không được báo PASS giả.

Kết quả này chứng minh semantics của chương trình mẫu trong môi trường bình thường, **không chứng minh fsync durability, power-loss safety, async delivery, multi-process locking hoặc collector**. Nếu I/O bị lỗi, bài test nên thất bại hoặc báo lỗi rõ; không nên nuốt lỗi rồi in PASS.

### Vì sao không kiểm thử bằng Thread.sleep?

Một số loggers có buffer hoặc async queue. Sleep(1000) có thể đủ trên một máy nhưng không tạo quan hệ đồng bộ giữa "event đã enqueue" và "file đã được ghi". Với JUL FileHandler đồng bộ trong ví dụ, explicit flush và close là điểm xác minh hợp lý. Với async appender, phải chờ drain/stop hoặc completion signal của backend đang dùng.

## 5. Viết lại thành JUnit 5 với @TempDir

Trong dự án có JUnit Jupiter 5, @TempDir giúp tạo thư mục tạm thuộc vòng đời test. Class sau là **integration test thật của JUL FileHandler**, nhưng cần JUnit 5 và test runner tương thích; không biên dịch độc lập bằng javac chỉ có JDK.

**Tệp: src/test/java/example/JulFileOutputTest.java**

~~~java
package example;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;
import java.util.UUID;
import java.util.logging.FileHandler;
import java.util.logging.Formatter;
import java.util.logging.Level;
import java.util.logging.LogRecord;
import java.util.logging.Logger;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

class JulFileOutputTest {
    @TempDir
    Path tempDir;

    @Test
    void writesExactUtf8LogFile() throws Exception {
        Path file = tempDir.resolve("events.log");

        Logger logger = Logger.getLogger(
                "example.filetest." + UUID.randomUUID());
        logger.setUseParentHandlers(false);
        logger.setLevel(Level.INFO);

        FileHandler handler = new FileHandler(
                file.toString(), false);
        handler.setEncoding(StandardCharsets.UTF_8.name());
        handler.setLevel(Level.ALL);
        handler.setFormatter(new Formatter() {
            @Override
            public String format(LogRecord r) {
                return r.getLevel().getName() + "|"
                        + formatMessage(r) + "\n";
            }
        });

        logger.addHandler(handler);
        try {
            logger.info("ĐÃ_GHI");
            logger.fine("NOT_WRITTEN");
            handler.flush();
        } finally {
            logger.removeHandler(handler);
            handler.close();
        }

        assertTrue(Files.isRegularFile(file));
        assertEquals(
                List.of("INFO|ĐÃ_GHI"),
                Files.readAllLines(file, StandardCharsets.UTF_8));
    }
}
~~~

### Điều gì khiến test này độc lập?

- @TempDir cấp đường dẫn mới cho fixture.
- UUID làm tên logger riêng cho test, giảm ảnh hưởng khi nhiều test cùng JVM.
- logger.setUseParentHandlers(false) ngăn event xuất ở root handler ngoài dự kiến.
- Dùng Formatter ngắn, không phụ thuộc timezone, PID, thread hoặc thời gian thực.
- Handler được đóng trước khi assert, quan trọng khi CI chạy trên Windows.
- Assert bằng equals toàn bộ list phát hiện dòng thiếu, thừa, bị đảo thứ tự trong case đồng bộ và lỗi encoding.
- JUnit dọn @TempDir theo lifecycle; FileHandler không còn giữ file lock khi dọn.

### Những điểm cần phân biệt

Nếu một unit test dùng Mockito verify(logger).info(...), nó không chứng minh logging backend đã ghi file. Nếu test dùng Logback ListAppender, nó chứng minh event được Logback tạo và giao tới appender trong bộ nhớ, **không phải FileAppender đã mở file**. Giữ cả hai loại test khi chúng bảo vệ hai hợp đồng khác nhau.

Với Maven/Gradle, cần cấu hình JUnit Jupiter và runner tương thích (Maven Surefire hoặc Gradle useJUnitPlatform). Dùng phiên bản do dự án/BOM quản lý; không bắt buộc thêm một phiên bản mới chỉ vì ví dụ minh họa.

## 6. Bài test nào nên có positive và negative checks?

Một file còn rỗng có thể khiến assert "không chứa DEBUG" pass, dù logger không hoạt động. Vì vậy mọi test negative quan trọng nên có **positive control**:

~~~text
Emit INFO READY
Emit DEBUG SHOULD_NOT_APPEAR

Expected:
  file contains READY
  file does not contain SHOULD_NOT_APPEAR
~~~

Những checks thường hữu ích:

| Điều kiện | Positive check | Negative check |
| --- | --- | --- |
| Level filter | INFO được ghi | DEBUG/FINE bị chặn |
| Business routing | BUSINESS vào business.log | TECHNICAL không lọt vào |
| Security redaction | Event đã sanitize xuất hiện | Token giả không xuất hiện |
| Logger hierarchy | Một record ở sink mong muốn | Không có duplicate từ parent |
| Async drain | Tất cả ID sau stop | Không thiếu ID do đọc quá sớm |
| Rotation | Có active + archive | Không ghi ngoài thư mục fixture |
| Append | Có event cũ và mới | Không truncate ngoài chính sách |
| Truncate | Chỉ event mới | Không giữ dữ liệu cũ |
| JSON Lines | Parse thành object hợp lệ | Không thêm dòng giả từ CR/LF |

Chỉ dùng assert contains("INFO") quá yếu: chuỗi INFO có thể nằm trong body hoặc một file cũ. Tốt hơn là assert định dạng, event identity và số event khi hợp đồng cho phép.

## 7. Logback: FileAppender thật và cấu hình test

Trong ứng dụng SLF4J + Logback, test ListAppender hữu ích để kiểm tra ILoggingEvent, marker, MDC hoặc throwable. Nhưng khi yêu cầu file output, cần FileAppender thật.

Ví dụ **src/test/resources/logback-test.xml**:

~~~xml
<configuration>
    <appender name="TEST_FILE"
              class="ch.qos.logback.core.FileAppender">
        <file>build/logging-test/application.log</file>
        <append>false</append>
        <encoder>
            <pattern>%level|%msg%n</pattern>
            <charset>UTF-8</charset>
        </encoder>
    </appender>

    <logger name="example.filetest"
            level="INFO" additivity="false">
        <appender-ref ref="TEST_FILE"/>
    </logger>

    <root level="WARN"/>
</configuration>
~~~

Đây là **mẫu cấu hình Logback**, không phải file JUnit tự động kiểm tra kết quả. Đường dẫn build/logging-test/application.log chỉ là minh họa; khi chạy các test đồng thời, một path cố định sẽ gây đụng nhau. Trong suite thật, nên cấu hình một **LoggerContext/FileAppender riêng với file từ @TempDir**, hoặc chạy test ở process có đường dẫn output riêng. Không lấy mẫu XML này làm cấu hình CI mặc định nếu suite có parallel execution.

### Cơ chế cần assert

- Logger example.filetest có level INFO và tham chiếu FileAppender đúng.
- additivity=false không cho event của logger test truyền thêm lên root; hữu ích nếu test muốn một sink độc lập.
- PatternLayoutEncoder định dạng từng event thành LEVEL|MESSAGE và newline.
- Charset được đặt UTF-8, tương ứng với FileReader của test.
- Appender phải start thành công. Nếu đường dẫn không ghi được, Logback có thể báo lỗi ở status manager mà lời gọi logger.info không ném lỗi.
- Sau appender.stop/context.stop, file được đọc để xác minh; không chỉ nhìn một trạng thái "logger enabled".
- Nếu test thay đổi cấu hình logger ở shared default context, phải restore hoặc dùng context riêng để không ảnh hưởng các test khác.

### Programmatic test với LoggerContext

Khi cần file path động từ @TempDir, một mẫu thao tác là:

~~~text
create isolated LoggerContext
create PatternLayoutEncoder with context and UTF-8
start encoder
create FileAppender with test file path and encoder
start appender
create test logger with additivity=false
log known marker event
stop appender and LoggerContext
read and assert test file
~~~

Đây là **workflow**, không phải đoạn Java standalone. API Logback và vòng đời context có chi tiết theo version; nên kiểm tra status và stop mọi resource trong finally. Việc dùng global LoggerFactory trong nhiều test song song có thể dẫn tới can thiệp logger hierarchy không mong muốn.

## 8. Log4j 2: FileAppender và Layout

Log4j 2 có FileAppender, RollingFileAppender, LoggerConfig, AppenderRef, filters và async mechanisms. Một fixture ví dụ **src/test/resources/log4j2-test.xml**:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<Configuration status="WARN">
    <Appenders>
        <File name="TEST_FILE"
              fileName="target/logging-test/application.log"
              append="false">
            <PatternLayout pattern="%level|%msg%n"
                           charset="UTF-8"/>
        </File>
    </Appenders>

    <Loggers>
        <Logger name="example.filetest"
                level="info" additivity="false">
            <AppenderRef ref="TEST_FILE"/>
        </Logger>
        <Root level="warn"/>
    </Loggers>
</Configuration>
~~~

Đây chỉ là fixture minh họa **dành cho Log4j 2 Core**, không dùng với Logback. Test phải xác minh config thực sự được nạp bởi logging provider đang chạy. Trong một project dùng SLF4J API, binding/provider quyết định backend cuối cùng; chỉ đặt log4j2-test.xml vào classpath không chắc có tác dụng nếu provider là Logback.

**Kiểm thử đúng:** tạo logging context riêng hoặc test process có file path tạm, phát event, stop appender/context, đọc lại file bằng UTF-8, kiểm tra nội dung và status error của backend.

Nếu dùng AsyncLogger/AsyncAppender, tránh đọc file ngay sau log.info. Đợi queue drain/stop theo API của backend/phiên bản, rồi assert. Một bài test chạy may mắn không chứng minh được queue không drop khi backend chậm.

## 9. Spring Boot: ghi file phải đi theo backend thật

Spring Boot có thể sử dụng Logback hoặc Log4j 2 tùy dependencies; Spring Boot thường bootstrap logging khá sớm. Snippet cấu hình:

~~~properties
logging.level.root=INFO
logging.file.name=build/logging-test/boot.log
~~~

Thuộc tính logging.file.name yêu cầu cơ chế Boot tương ứng ghi file, **không tự làm file cho mỗi logger category**. Path trên chỉ là ví dụ, không an toàn khi nhiều test cùng ghi.

Trong integration test Spring Boot, cần cân nhắc:

- Cấu hình logging được nạp trước hay sau khi test set property?
- Spring Test có cache ApplicationContext giữa các test không?
- Backend có sẵn file appender và quyền ghi?
- Có async appender phải stop/drain trước khi test kết thúc?
- Test này cần kiểm tra Spring Boot startup/config thật hay chỉ muốn kiểm tra một event?
- Có nhiều test class chạy song song cùng sử dụng một file không?

@SpringBootTest phù hợp để smoke-test integration khi muốn kiểm tra Boot logging runtime. Với logic nhỏ, dùng test logger/backend riêng tránh chi phí và side effect của whole application context. Khi thay đổi global system property, nhớ restore và cô lập process nếu logging config đã được cache.

## 10. Append và truncate

Một vấn đề file output quan trọng là file được mở ở chế độ append hay bắt đầu mới.

| Kịch bản | Thiết lập | Kết quả cần kiểm |
| --- | --- | --- |
| File mới | Chưa tồn tại | File tạo và có event |
| Append | File có dòng cũ, append=true | Cũ + mới, phân tách đúng |
| Truncate | File có dòng cũ, append=false | Chỉ còn nội dung mới |
| Logger restart | Appender bị stop/start | Dữ liệu giữ theo hợp đồng |
| Nhiều process cùng path | Cần xác định policy locking | Không suy tính an toàn từ test một JVM |

Trong JUL:

~~~java
// Snippet; target là Path hợp lệ do test tạo.
FileHandler appendHandler =
        new FileHandler(target.toString(), true);
~~~

Nếu muốn test append, viết fixture dòng cũ trước, mở handler ở chế độ append, ghi record mới, close rồi đọc. Nhưng **FileHandler có cơ chế pattern và lock**; nếu file đã được handler khác giữ, tên thực có thể nhận thêm unique suffix. Vì vậy không đọc một path phỏng đoán khi có tranh lock.

Đừng để test ghi vào application.log của người dùng hoặc pipeline production. Việc overwrite/truncate trong một test có thể gây mất thông tin nếu dùng nhầm path.

## 11. RollingFile và rotation

Trong production, log có thể được xoay theo ngày/kích thước:

~~~text
application.log
application.2026-11-09.log.gz
application.2026-11-08.log.gz
~~~

Tên trên chỉ minh họa. **File active** và **archive** là các tập dữ liệu khác nhau. Một test đọc mỗi application.log có thể kết luận thiếu event dù event đã được chuyển sang file nén theo rolling policy.

Các điều kiện kiểm thử quan trọng:

1. Ngưỡng rollover thực sự được kích hoạt theo policy cấu hình.
2. File active tiếp tục nhận event mới.
3. Có archive với pattern đúng.
4. Archive nén mở được và nội dung đúng nếu policy yêu cầu.
5. Không mất/nhân đôi event trong phạm vi những bảo đảm test được.
6. maxHistory/totalSizeCap/retention được hiểu đúng theo backend.
7. Sau restart hoặc reload, appender không xóa/ghi đè sai archive.
8. Cleanup các file phát sinh chỉ trong temp directory.

### Tránh flaky vì clock

Nếu chờ chuyển sang ngày mới để rollover, test phụ thuộc timezone, daylight saving, lịch chạy và tốc độ CI. Tốt hơn là dùng triggering policy có thể kích hoạt có chủ đích hoặc cấu hình size-based rotation trong một fixture nhỏ, sau đó stop appender và kiểm tra kết quả.

Không assert đúng tên ngày archive nếu backend dùng timezone khác hoặc period chưa được mock. Đừng nhầm maxHistory với TTL theo từng LogRecord: rotation của file và retention của bản sao trong collector/index/backup là những chuyện khác nhau.

## 12. Async logging: đợi drain, không dùng sleep cố định

Với async logging:

~~~text
Application thread
   |
   +---> log event created
              |
              v
         bounded queue
              |
              v
         logging worker
              |
              v
         file sink
~~~

Khi logger.info trả về, có thể event vẫn ở queue. Đọc file ngay sau đó không chắc đã thấy dữ liệu; Thread.sleep(1000) chỉ trì hoãn, không xác nhận queue hoàn tất.

Kế hoạch test:

1. Cấu hình async backend với queue capacity/overflow policy rõ.
2. Emit các event ID xác định.
3. Chờ completion/drain/stop bằng cơ chế được backend hỗ trợ.
4. Đóng sink an toàn.
5. Đọc file và đối chiếu tập event, số lượng, dropped count.
6. Với test overflow, dùng sink chậm được kiểm soát để tái hiện block/drop thay vì dựa vào timing may rủi.
7. Tách requirement: log INFO có thể bị discard theo chính sách, log ERROR có thể có policy riêng; assert đúng hợp đồng.

Async giảm chờ I/O trong điều kiện thường nhưng **không đồng nghĩa luôn không chặn, không mất log hoặc đã lưu bền vững**. Nếu một event quan trọng bắt buộc được bảo đảm, cần kiến trúc lưu bền vững riêng thay vì chỉ một file/async queue.

## 13. Kiểm thử ghi file đa luồng

Nếu tám worker cùng ghi log, test không nên đòi thứ tự toàn cục:

~~~text
worker-A: event-A1 event-A2
worker-B: event-B1 event-B2
worker-C: event-C1 event-C2
~~~

Tùy scheduling, thứ tự A1/B1/C1 có thể khác nhau ở mỗi lượt chạy. Với backend bảo đảm mỗi event không bị hỏng/ghép trong điều kiện test, nên assert:

- Mỗi event có event_id duy nhất.
- Tổng số event và số ID duy nhất đúng với hợp đồng no-drop.
- Không có record bị ghép dính/truncated bất ngờ.
- Từng event được parse đúng format.
- MDC/correlation_id không lẫn giữa threads.
- Thứ tự nội bộ của một producer được kiểm tra chỉ khi backend thực sự bảo đảm.
- Sau khi workers hoàn thành, stop/close appender trước khi đọc file.

Ví dụ thử nghiệm: 4 tasks × 50 events, kỳ vọng 200 unique IDs sau stop nếu sink không drop. Con số này là dữ liệu test minh họa, không phải thông số mặc định. Khi có sampling hay drop policy được phép, điều kiện assert phải theo chính sách đó.

Một appender thread-safe trong một JVM không đương nhiên an toàn cho **nhiều JVM ghi chung một file**. Test nhiều process cần fixture riêng và kết quả locking tương ứng.

## 14. JSON Lines: parse thay vì chỉ contains

Trong structured logging, một event có thể là một JSON line:

~~~json
{"timestamp":"2026-11-10T03:00:00Z","level":"INFO","event_type":"ORDER_ACCEPTED","order_id":"O-42"}
~~~

Khi output contract là một JSON object mỗi dòng, test nên:

- Parse từng dòng bằng JSON parser chuẩn.
- Assert mỗi object có event_type/level và các field cần thiết.
- Kiểm tra type: status là số, duration_ms là số, timestamp hợp lệ.
- Dữ liệu chứa quote, backslash, CR/LF, Unicode được escape đúng.
- Không có dòng JSON giả do log injection.
- Không có password, token hoặc payload nhạy cảm.
- Không có duplicate event trái hợp đồng.

Đoạn snippet sau cần Jackson, không phải code Java JDK độc lập:

~~~java
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;

// outputFile là Path được fixture cấp.
ObjectMapper mapper = new ObjectMapper();
for (String line : Files.readAllLines(
        outputFile, StandardCharsets.UTF_8)) {
    JsonNode value = mapper.readTree(line);
    if (!value.isObject() || !value.hasNonNull("event_type")) {
        throw new AssertionError("Invalid event schema");
    }
}
~~~

Không parse JSON bằng split(",") vì giá trị string có thể chứa dấu phẩy, quote hoặc escape. Nếu test chỉ assert file contains "ORDER_ACCEPTED", một JSON bị hỏng vẫn có thể pass. Hãy kiểm tra cấu trúc đầu ra thực.

## 15. Exception và stack trace: một event có thể nhiều dòng

Khi code ghi:

~~~java
// Snippet SLF4J, cần logger và exception thật.
log.error("Order failed id={}", orderId, exception);
~~~

Text layout có thể xuất stack trace trên nhiều dòng vật lý. Lúc này Files.readAllLines(...).size không bằng số event; đó không nhất thiết là lỗi.

Chọn assertion theo format:

- Text layout: kiểm tra prefix, exception class và các phần có ý nghĩa, tránh hardcode line number.
- JSON layout: một JSON line chứa stack_trace được escape đúng, parse rồi assert.
- Đầu ra có multiline aggregation ở collector: test cấu hình collector riêng.
- Exception message từ user input: kiểm tra redaction và log injection.
- Không dùng một stack trace động để so sánh toàn bộ file byte-for-byte nếu code có thể được refactor.

Một text formatter được thiết kế cố định như ví dụ JUL ở mục 4 phù hợp cho test exact content; nhưng production formatter vẫn phải được test theo schema và behavior riêng của nó.

## 16. Failure scenarios: lỗi ghi file

Không thể kết luận logging thành công chỉ vì API không ném exception. Nhiều backend ghi lỗi nội bộ qua status manager hoặc error handler, thay vì throw tại mỗi logger.info.

| Sự cố | Điều cần quan sát |
| --- | --- |
| Thư mục không tồn tại | Appender tự tạo path hay báo lỗi? |
| Không có quyền ghi | Appender start thất bại hay error status? |
| Disk/quota đầy | Log bị drop, backend report lỗi, app bị block? |
| File bị giữ bởi process khác | Lock hoặc unique file suffix hoạt động thế nào? |
| File bị rename/xóa khi đang mở | Sink tiếp tục ghi vào handle nào? |
| Rotation không thể rename/nén | Có error status và cách phục hồi? |
| Async queue đầy | Block/drop/fallback theo policy nào? |
| Process restart giữa event | Buffer/log file còn những gì? |

Không thực hiện test disk-full bằng cách lấp đầy ổ đĩa của máy developer hay shared CI runner. Dùng volume/sandbox có quota và cleanup an toàn. Không thay permission của thư mục thật chỉ để gây lỗi.

### Những điểm quan trọng khi test lỗi

- Phải phân biệt logger API accepted với file sink write succeeded.
- Nếu backend có status manager/error callback, assert error signal.
- Nếu muốn test khôi phục, xác minh appender có thể ghi lại vào file mới sau khi lỗi được xử lý, theo contract.
- Không im lặng chuyển mọi lỗi I/O thành PASS; chỉ bỏ qua nếu có chính sách kiểm soát rõ.
- Với audit/business-critical event cần đảm bảo giao dịch, file logging thường không đủ; cân nhắc outbox hoặc durable event store.

## 17. Container và collector: file output có thể không phải mục tiêu

Ứng dụng Spring Boot trong Docker/Kubernetes thường ghi stdout/stderr để runtime/collector thu thập. Trong kiến trúc đó, test “phải có application.log trên local filesystem” **sai mục tiêu**.

| Sink thật | Cách xác minh |
| --- | --- |
| JUL FileHandler/FileAppender | Đọc file trong temp directory hoặc volume |
| ConsoleAppender | Capture stdout/stderr hoặc container logs ở tầng phù hợp |
| Docker runtime logging | Kiểm tra container driver/runtime log theo môi trường test |
| Kubernetes | Quan sát container log và collector |
| Centralized backend | Query event theo ID test có kiểm soát |
| Remote appender | Kiểm tra acknowledgment/record ở đích theo API |

Với log trong container, phân biệt file cục bộ của container (ephemeral), file log của container runtime trên node và backend lưu tập trung. Một test chỉ xem docker logs không chứng minh collector đã ingest; một test query index không chứng minh mọi event được giữ bền vững khi outage.

Một end-to-end test có thể phát event với test ID riêng, xác minh output tại Java, tại container runtime, rồi tại collector/backend. Hãy giới hạn tài nguyên, tránh đưa dữ liệu cá nhân và cleanup test artifacts theo retention riêng.

## 18. CI và chống flaky test

Những nguyên nhân phổ biến:

1. Test A/B ghi cùng một file path.
2. Test đọc file cũ hoặc nội dung còn lại do append=true.
3. Logger context global bị một test khác thay đổi.
4. Test dùng Thread.sleep để chờ async flush.
5. FileHandler/Appender chưa close gây lỗi xóa trên Windows.
6. Test so sánh timestamp hoặc thread name thực.
7. Platform charset khác UTF-8.
8. Test assert thứ tự toàn cục của concurrent events.
9. Rolling đã chuyển event sang archive nhưng test chỉ đọc file active.
10. Đường dẫn tương đối resolve khác giữa IDE/Maven/Gradle/CI.
11. Backend thực tế khác backend mà test cấu hình.
12. Lỗi sink chỉ nằm trong backend status, không xuất thành exception.

**Checklist CI trước khi gộp test:**

- Mỗi test có temp dir/file riêng.
- Positive control event xác nhận sink hoạt động.
- Có negative check cho level/filter/redaction quan trọng.
- Đồng bộ bằng lifecycle API thay vì delay đoán trước.
- Stop/close trong finally.
- Đọc UTF-8 hoặc parse JSON theo schema.
- Không dùng raw PII/credential trong fixture.
- Test đủ nhanh, không cần chờ rollover theo đồng hồ thật.
- Khi fail, hiển thị diff/metadata giúp debug nhưng không làm lộ secret.
- Có kiểm soát nếu chạy parallel.
- Không thay đổi file/config của production.
- Kiểm tra lại sau khi nâng JDK, logging backend hoặc build/test runner.

## 19. Troubleshooting file output

| Triệu chứng | Nguyên nhân khả dĩ | Kiểm tra |
| --- | --- | --- |
| File không xuất hiện | Sai backend/config, path resolve khác, appender không start | Runtime provider, LoggerContext, path và status |
| File rỗng | Level/filter, chưa flush/close | Positive control, effective level, lifecycle |
| Có log nhưng test fail vì chữ Việt | Charset khác nhau | Encoder/file reader UTF-8 |
| Dòng thừa | Additivity, parent handler hoặc file cũ | Disable parent, temp dir, exact count |
| Dòng thiếu | Async chưa drain, rolling, drop | Queue, file archive, errors |
| File .0 hoặc .1 | JUL pattern generation hoặc unique lock | FileHandler %g/%u, tranh file |
| JUnit @TempDir không dọn | Handler chưa close | finally, context stop |
| Test pass local nhưng fail CI | Permission/working directory/OS | Temp dir, path riêng, charset |
| Logback XML không hoạt động | Provider khác hoặc config không được nạp | Runtime logging dependency |
| Log4j 2 test không tạo file | Logger chưa ref appender hoặc appender start fail | Configuration status |
| Stack trace làm line count tăng | Multi-line text layout | Assert event schema thay vì số line |
| JSON test contains pass nhưng parse lỗi | Custom string concatenation/escaping sai | Dùng JSON encoder chuẩn và parser |
| Async test lúc pass lúc fail | Sleep/đọc trước flush | Await/stop/drain theo API |
| File đã bị xóa nhưng không giảm disk | Process còn giữ inode/handle | Kiểm tra process handle và filesystem |

Một trình tự chẩn đoán đáng tin là: xác định provider → nạp config → effective logger level → appender start → sink path → emit positive control → stop/flush → đọc đúng file + archive → so sánh schema, charset và event IDs.

## 20. Bảo mật và quyền riêng tư trong test log

File test cũng có thể bị thu thập vào CI artifacts, backup hoặc dashboard. Vì vậy:

- Dùng dữ liệu giả, không lấy production HTTP body/headers để test.
- Assert token/password giả không có mặt trong output; không ghi secret thật.
- Nếu test log injection, chỉ dùng môi trường kiểm thử và xác nhận input CR/LF không tạo dòng event giả.
- Placeholder logging không phải sanitizer; output formatter/JSON encoder mới quyết định escaping.
- Ghi request_id/trace_id trong fixture có kiểm soát, không dùng thông tin định danh khách hàng thật.
- Nếu test tạo archive hoặc file lỗi, cleanup và đặt retention.
- Phân quyền đọc artifacts CI phù hợp, không xuất file log nhạy cảm vào báo cáo công khai.
- Không chmod/thay ACL thư mục production để tạo failure scenario.
- Không dùng logger output thành bằng chứng transaction exactly-once. File test không thay thế durable audit.

## 21. Bài tập thực hành

**Bài 1 – Level filtering.** Chạy FileOutputTestDemo.java, đổi logger level từ INFO sang FINE, cập nhật expected list để thêm FINE|DEBUG_IGNORED. Xác minh level và số dòng đúng; chuyển lại INFO.

**Bài 2 – Append/truncate.** Tạo một file tạm có dòng cũ rồi mở FileHandler append=true và ghi sự kiện mới. Assert giữ cả hai. Chạy lại với append=false và assert dòng cũ không còn.

**Bài 3 – JUnit @TempDir.** Chạy class JulFileOutputTest với ít nhất hai test methods có file/loggers riêng. Kiểm tra test không phụ thuộc thứ tự và dọn file lock.

**Bài 4 – Logback FileAppender.** Trong project dùng Logback, tạo LoggerContext riêng với path trong @TempDir, set additivity=false, ghi INFO, stop appender rồi đọc file. So sánh với test ListAppender.

**Bài 5 – Log4j 2 RollingFile.** Tạo fixture rollover kích thước nhỏ, emit events, stop context, kiểm tra active file và archives sau khi giải nén.

**Bài 6 – Async logging.** Dùng async appender và sink chậm có kiểm soát. Phát events có ID, thử phương án sleep cố định và phương án drain/stop chính thức; giải thích vì sao kết quả khác nhau.

**Bài 7 – Concurrency.** Cho nhiều threads ghi event IDs riêng. Sau stop assert tổng số IDs unique và không có dòng bị ghép/hỏng; không assert thứ tự toàn cục.

**Bài 8 – JSON/redaction.** Dùng một JSON encoder thật, log giá trị có dấu quote, Unicode, CR/LF và token giả. Parse mỗi JSON line; assert event hợp lệ và token không lộ.

**Bài 9 – Container.** Nếu service production ghi console chứ không tạo file, thiết kế lại test theo stdout/runtime/collector. Giải thích vì sao không nên thêm FileAppender chỉ để test generic pass.

## 22. Tổng kết

**Kiểm thử file output trong Java phải chạm tới file thật**, chứ không chỉ xác nhận một lời gọi logger. Dùng đường dẫn test riêng, một event có thể đối chiếu, UTF-8 rõ ràng, flush/close đúng lifecycle, assert nội dung cả positive/negative và cleanup an toàn. Chương trình Java 17 JUL cho thấy cách thực hiện độc lập; JUnit 5 @TempDir hỗ trợ fixture ổn định trong dự án thật.

Với Logback và Log4j 2, kiểm thử đúng FileAppender/LoggerContext thay vì chỉ ListAppender. Với rolling file, kiểm tra archive; với async logging, đợi drain/stop; với multithreading, xác nhận tập event thay vì thứ tự ngẫu nhiên; với Spring Boot/container, test đích log thực mà ứng dụng dùng. Cần giữ kết quả CI ổn định đồng thời không ghi dữ liệu nhạy cảm hoặc phá file ngoài phạm vi test.

### Tài liệu tham khảo

- Oracle Java 17 FileHandler: https://docs.oracle.com/en/java/javase/17/docs/api/java.logging/java/util/logging/FileHandler.html
- Oracle Java 17 Logger: https://docs.oracle.com/en/java/javase/17/docs/api/java.logging/java/util/logging/Logger.html
- Oracle Java 17 Formatter: https://docs.oracle.com/en/java/javase/17/docs/api/java.logging/java/util/logging/Formatter.html
- Oracle Java 17 Files: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/Files.html
- JUnit 5 @TempDir: https://docs.junit.org/5.11.4/user-guide/index.html#writing-tests-built-in-extensions-TempDirectory
- Logback Appenders: https://logback.qos.ch/manual/appenders.html
- Logback Configuration: https://logback.qos.ch/manual/configuration.html
- Apache Log4j 2 File Appenders: https://logging.apache.org/log4j/2.x/manual/appenders/file.html
- Apache Log4j 2 Rolling File: https://logging.apache.org/log4j/2.x/manual/appenders/rolling-file.html
- Apache Log4j 2 Async Logging: https://logging.apache.org/log4j/2.x/manual/async.html
- Spring Boot Logging: https://docs.spring.io/spring-boot/reference/features/logging.html
- OWASP Logging Cheat Sheet: https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html
