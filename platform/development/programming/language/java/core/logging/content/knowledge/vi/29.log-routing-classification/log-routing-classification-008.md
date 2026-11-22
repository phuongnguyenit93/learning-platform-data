# Nhiều đích ghi trong Java Core Logging

## 1. Một log event có thể đi đến nhiều nơi

Trong ứng dụng Java, thông tin vận hành hiếm khi chỉ phục vụ một đối tượng đọc. Lập trình viên muốn nhìn log trên terminal, người trực hệ thống cần lọc sự cố từ file hoặc hệ thống tập trung, còn đội vận hành có thể cần một kênh riêng cho cảnh báo. **Nhiều đích ghi** (multiple logging destinations) là khả năng một logger chuyển log event đến **hơn một handler/appender**, theo chính sách phân loại khác nhau.

Ví dụ một đơn hàng được tạo thành công có thể ghi vào file để tra cứu, trong khi lỗi thanh toán vừa vào file vừa hiện trên console. Hai dòng ở hai đích có thể xuất phát từ **cùng một log event**, không phải hai lời gọi `logger.error(...)` khác nhau.

~~~text
                     Application code
                   logger.info/warn/error
                             |
                        Logger level
                             |
                       Log event chung
                             |
                   +---------+---------+
                   |                   |
             Console handler        File handler
             level = WARNING        level = INFO
                   |                   |
               stderr             logs/app.log
                   |
             Log collector
~~~

Trong sơ đồ, event `INFO` chỉ đi vào file; event `WARNING` hoặc `SEVERE` có thể xuất ở cả console và file. Điều quan trọng là **mỗi đích có thể tự quyết định có nhận một event hay không**.

Lợi ích thực tế gồm: theo dõi tương tác khi phát triển, lưu lịch sử xử lý, kết nối hệ thống thu thập tập trung, tạo kênh audit phù hợp và giảm nhiễu cho từng người đọc. Đổi lại, cần quản lý việc ghi trùng, I/O, độ trễ, dung lượng, bảo mật và chính sách lọc.

## 2. Phân biệt logger, handler, appender và formatter

Các thuật ngữ không hoàn toàn đồng nhất giữa thư viện:

| Thành phần | Vai trò | Ví dụ |
| --- | --- | --- |
| **Logger** | API/tên nguồn phát log và mức log hiệu lực | `java.util.logging.Logger`, logger qua SLF4J |
| **Log event / LogRecord** | Dữ liệu của một lần ghi log: level, message, timestamp, nguồn... | `java.util.logging.LogRecord` |
| **Handler** trong JUL | Nhận event và xử lý một đích xuất | `ConsoleHandler`, `FileHandler` |
| **Appender** trong Logback/Log4j 2 | Vai trò gần giống handler trong backend tương ứng | `ConsoleAppender`, `RollingFileAppender` |
| **Filter** | Quyết định event có được xử lý ở một vị trí cụ thể hay không | Logger filter, handler/appender filter |
| **Formatter/Layout/Encoder** | Biến event thành chuỗi hoặc byte phù hợp đích xuất | `SimpleFormatter`, pattern/JSON encoder |

Luồng điển hình của Java Util Logging (JUL):

1. **Logger nguồn** kiểm tra level và filter của chính nó. Event bị loại ở đây thường không đi tiếp đến các handler.
2. Event được chuyển đến các handler gắn với logger và, nếu `useParentHandlers=true`, đến handler của logger cha.
3. **Mỗi handler** áp dụng level/filter riêng, định dạng event được chấp nhận, rồi ghi ra đích của nó.
4. Nếu backend dùng buffer hoặc async queue, event có thể được xuất hoặc flush sau thời điểm gọi phương thức log.

**Hai mức lọc không thay thế nhau:** nếu logger nguồn đặt `WARNING`, event `INFO` không thể xuất ra file chỉ bằng cách đặt FileHandler ở `INFO` vì nó đã bị chặn từ đầu. Ngược lại, logger đặt `FINE` không buộc mọi handler phải ghi `FINE`; mỗi handler có thể từ chối.

Trong JUL, level của logger cha không nhất thiết được kiểm tra lại cho event do logger con đã tạo; **level/filter của các handler trên logger cha** mới quyết định việc xuất event qua các handler đó. Đây là điểm cần hiểu khi root logger có nhiều handler.

## 3. Ví dụ Java 17: console chỉ nhận cảnh báo, file nhận INFO trở lên

Ví dụ sử dụng `java.util.logging`, có sẵn trong JDK 17, không cần thêm dependency. Ta tạo **một logger dùng chung**, gắn hai handler:

- `ConsoleHandler`: in `WARNING` và `SEVERE` ra **stderr**.
- `FileHandler`: ghi `INFO`, `WARNING`, `SEVERE` vào file trong thư mục `logs`.
- Logger nguồn: cho phép từ `FINE` trở lên, để thấy rõ quyết định còn phụ thuộc các handler.

Tạo tệp **`MultiDestinationLoggingDemo.java`**:

~~~java
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.logging.ConsoleHandler;
import java.util.logging.FileHandler;
import java.util.logging.Formatter;
import java.util.logging.Level;
import java.util.logging.LogRecord;
import java.util.logging.Logger;

public class MultiDestinationLoggingDemo {
    private static final class PlainFormatter extends Formatter {
        @Override
        public String format(LogRecord record) {
            return record.getLevel().getName() + ": "
                    + formatMessage(record)
                    + System.lineSeparator();
        }
    }

    public static void main(String[] args) throws IOException {
        Files.createDirectories(Path.of("logs"));

        Logger logger = Logger.getLogger("demo.routing.multi");
        logger.setLevel(Level.FINE);
        logger.setUseParentHandlers(false);

        ConsoleHandler console = new ConsoleHandler();
        console.setLevel(Level.WARNING);
        console.setFormatter(new PlainFormatter());

        FileHandler file = new FileHandler(
                "logs/application-%g.log", 1_048_576, 2, false);
        file.setLevel(Level.INFO);
        file.setFormatter(new PlainFormatter());

        logger.addHandler(console);
        logger.addHandler(file);
        try {
            logger.fine("cache hit");
            logger.info("order created");
            logger.warning("retry scheduled");
            logger.severe("payment failed");
        } finally {
            logger.removeHandler(console);
            logger.removeHandler(file);
            console.flush();
            file.flush();
            console.close();
            file.close();
        }
    }
}
~~~

Chạy từ một thư mục có quyền tạo `logs`, không có tiến trình khác đang khóa cùng file:

~~~bash
javac MultiDestinationLoggingDemo.java
java MultiDestinationLoggingDemo
~~~

**Stdout:** không có dòng nào, vì chương trình không gọi `System.out` và `ConsoleHandler` mặc định xuất ra stderr.

**Stderr:**

~~~text
WARNING: retry scheduled
SEVERE: payment failed
~~~

**Nội dung `logs/application-0.log` sau khi chương trình kết thúc trong lần chạy đơn tiến trình:**

~~~text
INFO: order created
WARNING: retry scheduled
SEVERE: payment failed
~~~

Tệp `logs/application-0.log` do `FileHandler` sinh từ pattern `application-%g.log`, với generation đầu là `0`. Nếu chạy đồng thời nhiều JVM dùng cùng pattern và có file lock, tên thực tế có thể được thay đổi để tránh xung đột (ví dụ thêm số unique); đừng dựa vào một tên duy nhất trong cấu hình multi-process. Kết quả mỗi dòng không có timestamp vì ta dùng `PlainFormatter`; ký tự kết thúc dòng phụ thuộc hệ điều hành.

**Giải thích bảng định tuyến:**

| Event phát từ logger | Mức logger `FINE` | Console `WARNING` | File `INFO` |
| --- | --- | --- | --- |
| `FINE cache hit` | Chấp nhận | Bỏ | Bỏ |
| `INFO order created` | Chấp nhận | Bỏ | Ghi |
| `WARNING retry scheduled` | Chấp nhận | Ghi | Ghi |
| `SEVERE payment failed` | Chấp nhận | Ghi | Ghi |

Bảng cho thấy không cần gọi `logger.warning(...)` hai lần để ghi vào hai đích. Một event được phát một lần và **fan-out** đến các handler phù hợp.

`setUseParentHandlers(false)` rất quan trọng trong ví dụ: nếu logger còn chuyển event đến các handler của logger cha, console có thể nhận thêm một bản log, tạo cảm giác bị ghi lặp. Trong chương trình production, cấu hình kế thừa handler có thể là chủ đích; cần hiểu nơi nào đã gắn handler trước khi tắt nó.

`FileHandler` dùng `limit=1_048_576` byte và `count=2`, nghĩa là ví dụ thiết lập giới hạn cỡ 1 MiB và hai thế hệ file trong cơ chế quay vòng của JUL. Với chỉ ba dòng, không có chuyện quay vòng. `append=false` cho phép khởi tạo lại file đang được chọn khi chương trình bắt đầu; đừng dùng cách này cho dữ liệu cần giữ mãi mà chưa có chính sách rotation/retention phù hợp.

## 4. Khi muốn chia log thành các kênh loại trừ nhau

**Gửi trùng có chủ đích** và **phân loại loại trừ nhau** là hai yêu cầu khác nhau.

- **Fan-out:** `WARNING` xuất ở cả console và file, như ví dụ ở trên.
- **Partition:** `INFO` đi kênh thông thường; `WARNING`/`SEVERE` đi kênh cảnh báo; mỗi event chỉ vào một nhóm đích.

Nếu dùng JUL và muốn kênh chỉ nhận `INFO` đúng nghĩa, đặt `handler.setLevel(Level.INFO)` là **chưa đủ**, vì nó cũng nhận `WARNING` và `SEVERE`. Phải thêm filter nhận **đúng mức**:

~~~java
// Đoạn tích hợp: hai Handler đã được tạo và quản lý vòng đời.
infoHandler.setLevel(Level.INFO);
infoHandler.setFilter(record -> record.getLevel() == Level.INFO);

alertHandler.setLevel(Level.WARNING);
~~~

Đây là đoạn mã minh họa cần các biến `infoHandler` và `alertHandler` đã có sẵn, không phải một chương trình độc lập. Nó giả định chỉ xét các mức JUL chuẩn. Trong hệ thống thực tế có các level tự định nghĩa hoặc phân loại theo nghiệp vụ, nên chọn filter theo các trường phù hợp hơn.

**Không được nhầm mức độ (severity) với loại dữ liệu (category).** Ví dụ `AUDIT`, `SECURITY`, `BUSINESS` không nhất thiết đồng nghĩa với `WARNING` hay `ERROR`; việc gửi audit đến một đích riêng thường nên dựa vào logger name, marker hoặc metadata có cấu trúc, tùy backend.

| Mục đích | Gợi ý routing | Điều cần quyết định |
| --- | --- | --- |
| Dev console | Mức phù hợp để đọc trực tiếp | Có cần `DEBUG`/`FINE` không? |
| Production stdout/stderr | Event hữu ích cho hệ thống giám sát | Log collector thu thập luồng nào? |
| File lịch sử | Event phục vụ tra cứu | Rotation, retention, quyền truy cập |
| Audit trail | Sự kiện nghiệp vụ cần truy vết | Dữ liệu bắt buộc, kiểm soát truy cập, độ bền |
| Alert/error channel | Lỗi hoặc cảnh báo hành động được | Chống spam/deduplication, tỷ lệ cảnh báo |
| Remote collector | Event đã chuẩn hóa, có trace/request ID | Mạng, queue, retry, backpressure |

Một event có thể được gửi đến nhiều đích nếu cần hai mục đích độc lập. Nhưng nếu hệ thống thu thập đã đọc stdout và đẩy vào kho trung tâm, đồng thời ứng dụng lại gửi thẳng cùng event đến kho đó, bạn có thể tạo **bản ghi trùng ở cấp pipeline**.

## 5. Cấu hình nhiều đích bằng `logging.properties` của JUL

Thay vì tự gắn handler bằng Java code, JUL hỗ trợ cấu hình từ file. Ví dụ sau là cấu hình **riêng cho ứng dụng sử dụng JUL**, không dùng đồng thời với phần chương trình tự gắn handler ở mục 3:

~~~properties
# Logger root duoc gan hai handler.
handlers = java.util.logging.ConsoleHandler, java.util.logging.FileHandler
.level = INFO

# Console chi hien canh bao va loi.
java.util.logging.ConsoleHandler.level = WARNING
java.util.logging.ConsoleHandler.formatter = java.util.logging.SimpleFormatter

# File nhan INFO tro len.
java.util.logging.FileHandler.level = INFO
java.util.logging.FileHandler.formatter = java.util.logging.SimpleFormatter
java.util.logging.FileHandler.pattern = logs/application-%g.log
java.util.logging.FileHandler.limit = 1048576
java.util.logging.FileHandler.count = 2
java.util.logging.FileHandler.append = true

# Format ngan gon, dung chung cho hai handler.
java.util.logging.SimpleFormatter.format = %4$s: %5$s%n
~~~

Giả sử tệp đặt tại `config/logging.properties`, thư mục `logs` đã tồn tại và có một class `MyApplication` thực sự dùng JUL:

~~~bash
java -Djava.util.logging.config.file=config/logging.properties MyApplication
~~~

Lệnh trên là ví dụ cách nạp cấu hình vào một ứng dụng đã tồn tại; **không phải** lệnh chạy file demo mục 3. Tham số `-D...` phải nằm trước tên main class hoặc `-jar`. FileHandler không tự tạo mọi thư mục cha bị thiếu; cần chuẩn bị thư mục và quyền ghi trước.

Vì `.level=INFO`, logger kế thừa mức mặc định này thường không tạo event `FINE`. ConsoleHandler `WARNING` lọc những event đã được tạo từ mức thấp hơn; FileHandler `INFO` nhận phần tương ứng. Nếu một logger con cấu hình `FINE`, event `FINE` của nó vẫn có thể bị hai handler hiện tại bỏ.

**Lưu ý về tên logger và hệ thống chạy:** file `logging.properties` của JUL không tự cấu hình Logback hay Log4j 2. Khi ứng dụng gọi API SLF4J, phải xác định provider/backend hoạt động trước khi chọn tệp cấu hình.

## 6. Hai appender trong Logback (SLF4J)

Với ứng dụng dùng SLF4J và backend **Logback Classic**, tệp `logback.xml` tối giản sau gửi cùng event `INFO` trở lên tới console và file:

~~~xml
<configuration>
    <appender name="STDOUT" class="ch.qos.logback.core.ConsoleAppender">
        <encoder>
            <pattern>%d{HH:mm:ss.SSS} %-5level [%thread] %logger - %msg%n</pattern>
        </encoder>
    </appender>

    <appender name="FILE" class="ch.qos.logback.core.FileAppender">
        <file>logs/application.log</file>
        <append>true</append>
        <encoder>
            <pattern>%d{yyyy-MM-dd HH:mm:ss.SSS} %-5level %logger - %msg%n</pattern>
        </encoder>
    </appender>

    <root level="INFO">
        <appender-ref ref="STDOUT"/>
        <appender-ref ref="FILE"/>
    </root>
</configuration>
~~~

Đây là XML của **Logback**, đặt trên classpath (thường `src/main/resources/logback.xml` trong dự án Maven/Gradle) hoặc vị trí được backend hỗ trợ. Ứng dụng phải có SLF4J và Logback phù hợp để ví dụ có hiệu lực. `FileAppender` đơn giản **chưa cung cấp rotation/retention**; khi chạy lâu hoặc khối lượng lớn, nên sử dụng `RollingFileAppender` và rolling policy phù hợp.

Muốn console chỉ hiện `WARN` trở lên nhưng file giữ `INFO`, có thể thêm filter sau **bên trong appender STDOUT**:

~~~xml
<filter class="ch.qos.logback.classic.filter.ThresholdFilter">
    <level>WARN</level>
</filter>
~~~

Đây là một **đoạn XML tích hợp** cần đặt trong `<appender name="STDOUT"> ... </appender>`, không phải tệp `logback.xml` độc lập. Khi root level `INFO`, event `DEBUG` vẫn bị root chặn; event `INFO` vào file nhưng bị console filter từ chối; event `WARN` và `ERROR` xuất cả hai.

Cẩn trọng với **additivity**: khi logger con gắn một appender và vẫn chuyển event lên root, cùng một appender có thể bị tham chiếu qua nhiều đường khiến output trùng. Cần hiểu cấu trúc logger hierarchy và chỉ dùng `additivity="false"` khi thực sự muốn cắt đường truyền lên logger cha; vì làm vậy cũng có thể khiến event không đến đích mong muốn.

## 7. Hai appender trong Log4j 2

Với ứng dụng dùng **Log4j 2**, ví dụ `log4j2.xml`:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<Configuration>
    <Appenders>
        <Console name="CONSOLE" target="SYSTEM_OUT">
            <PatternLayout pattern="%d{HH:mm:ss.SSS} %-5p %c - %m%n"/>
        </Console>
        <File name="FILE" fileName="logs/application.log" append="true">
            <PatternLayout pattern="%d{yyyy-MM-dd HH:mm:ss.SSS} %-5p %c - %m%n"/>
        </File>
    </Appenders>
    <Loggers>
        <Root level="info">
            <AppenderRef ref="CONSOLE"/>
            <AppenderRef ref="FILE"/>
        </Root>
    </Loggers>
</Configuration>
~~~

Cấu hình này phân phối event qua hai appender, nhưng **không có chính sách rolling** cho `File` appender; ở production có thể cần `RollingFile` kết hợp `Policies` và chiến lược retention. Đây là tệp của Log4j 2, không thể áp dụng nguyên cú pháp cho JUL hoặc Logback.

Log4j 2 hỗ trợ filter tại nhiều vị trí, như logger, appender reference hoặc appender. Muốn phân loại theo severity, marker hoặc dữ liệu khác cần đặt filter **đúng vị trí** theo mục tiêu và kiểm tra hiệu quả thực tế. Khi dùng async logging, thời điểm tạo event và thời điểm ghi file/network có thể khác nhau.

## 8. Tương tác giữa nhiều đích và hệ thống thu thập log

Trên máy cá nhân, ghi file trực tiếp có thể tiện. Trên container hoặc hệ thống điều phối, một phương án phổ biến là:

~~~text
Java application
      |
      +--> stdout / stderr --> container runtime --> log collector
      |                                        |
      |                                        +--> search / archive / alerts
      |
      +--> file (chi khi co yeu cau va volume phu hop)
~~~

Hệ thống thu thập có thể đã nhân bản log đến các đích tìm kiếm, lưu trữ và cảnh báo. Trường hợp này, việc cấu hình thêm remote appender trong ứng dụng cho **cùng luồng sự kiện** dễ làm tăng băng thông hoặc phát sinh bản ghi trùng.

Nếu dùng file trong container, hãy kiểm tra volume, vòng đời container, quyền ghi, dung lượng và cơ chế rotation. Một file bên trong filesystem tạm của container có thể mất khi container bị thay thế. Với nhiều replica, mỗi tiến trình có thể cần file riêng hoặc tốt hơn là luồng stdout/stderr để collector gắn metadata (service, pod, host, environment).

**Ghi log có cấu trúc** giúp nhiều đích sử dụng chung event gốc nhưng format riêng:

- Console cho developer: pattern dễ đọc.
- File/collector: JSON có `timestamp`, `level`, `logger`, `message`, `traceId`, `spanId` khi có.
- Audit: schema và chính sách quyền truy cập rõ ràng, không chỉ “copy mọi log thông thường”.

Một event có thể được định dạng **khác nhau ở từng appender**. Điều đó không làm thay đổi nội dung nghiệp vụ gốc, nhưng các trường có mặt trong mỗi output phụ thuộc layout/encoder, MDC/tracing integration và filter.

## 9. Hiệu năng, độ tin cậy và vòng đời của nhiều đích ghi

**Chi phí nhân lên theo đích.** Nếu một event được xuất đồng thời ra console, file và mạng, ứng dụng có thể phải chạy nhiều formatter/encoder, thực hiện nhiều I/O hoặc enqueue nhiều lần. Logging đồng bộ có thể làm chậm request nếu một đích chậm. Với async appender/handler, chi phí có thể chuyển sang queue/worker, nhưng cần định rõ chính sách khi hàng đợi đầy.

**Một đích lỗi không mặc nhiên bảo đảm đích khác vẫn thành công.** Tùy backend, lỗi I/O có thể được báo qua status/error manager, bị bỏ qua, làm block, hoặc khiến một đường ghi thất bại. Không nên coi log ở console là bằng chứng event chắc chắn đã được lưu file hay đã tới hệ thống tập trung.

**Flush và shutdown:** dữ liệu trong buffer/queue chưa chắc đã được ghi bền vững. Khi ứng dụng dừng, backend cần thời gian/đường đóng phù hợp để flush và giải phóng file handle, socket hoặc worker. Trong ví dụ JUL, gọi `flush`/`close` nhằm bảo đảm file được đóng trước khi kiểm tra nội dung. Khi dùng framework, ưu tiên vòng đời logging do framework quản lý.

**Rotation và retention:** file tăng liên tục sẽ đầy đĩa nếu thiếu chính sách quay vòng/xóa. Cấu hình theo kích thước, thời gian và thời gian giữ lại tùy backend; cần giám sát dung lượng thực tế. Một handler trong một JVM có thể an toàn cho nhiều thread nhưng không có nghĩa **nhiều JVM khác nhau có thể cùng ghi một file bất kỳ** mà không có rủi ro.

**Bảo mật theo từng đích:** console được xem qua log platform, file được đọc bởi tài khoản hệ điều hành, remote collector có thể lưu ở hệ thống khác. Mỗi đích cần mức log, masking/redaction, quyền truy cập và retention tương ứng. Không nhân bản password, token hoặc dữ liệu cá nhân nhạy cảm chỉ để “đủ log ở mọi nơi”.

## 10. Các lỗi thường gặp và cách xử lý

| Hiện tượng | Nguyên nhân cần kiểm tra | Hướng xử lý |
| --- | --- | --- |
| Một event xuất hai lần trên console | Logger con và root cùng có console handler/appender; additivity | Kiểm tra cây logger, handler cha và appender-ref |
| Có INFO trong file nhưng không trên console | Console có ngưỡng WARNING, file có ngưỡng INFO | Đây có thể là chính sách đúng, không phải lỗi |
| Không có INFO ở bất kỳ đâu | Logger nguồn đang ở WARNING hoặc filter từ chối | Kiểm tra level/filter nguồn trước khi xét đích |
| File log không xuất hiện | Thư mục thiếu, không có quyền ghi, working directory sai | Kiểm tra đường dẫn thực và lỗi lúc mở handler |
| Log có trên console nhưng vắng trong collector | Pipeline thu thập lỗi, bỏ event hoặc chỉ đọc một luồng | Kiểm tra collector, stdout/stderr, queue, filter, export |
| Một event có nhiều bản trong hệ thống tập trung | Vừa đọc stdout vừa gửi remote trực tiếp, hoặc nhiều pipeline thu cùng nguồn | Xác định một đường thu thập chính, thêm dedup nếu cần |
| File tăng không giới hạn | FileAppender không có rolling/retention | Cấu hình rolling policy và giám sát dung lượng |
| Tác vụ chậm khi log nhiều | I/O đồng bộ, format nặng, nhiều đích hoặc queue đầy | Đo chi phí, giảm verbosity, cân nhắc async có kiểm soát |
| Log thiếu request/trace ID | MDC/tracing context chưa được đưa vào event/encoder | Gắn context đúng request và kiểm tra từng layout |
| Mất log lúc shutdown | Buffer/queue chưa flush hoặc tiến trình bị dừng gấp | Dùng shutdown hook/lifecycle và chính sách thoát phù hợp |

## 11. Tự kiểm tra

Với chương trình `MultiDestinationLoggingDemo`:

1. Vì sao `FINE cache hit` không xuất hiện? → Logger nhận `FINE`, nhưng **cả hai handler** đều có ngưỡng cao hơn.
2. Vì sao `INFO order created` chỉ có trong file? → FileHandler chấp nhận từ `INFO`; ConsoleHandler chỉ nhận từ `WARNING`.
3. Nếu đổi `logger.setLevel(Level.WARNING)`, log `INFO` còn vào file không? → Không, logger nguồn đã lọc bỏ trước.
4. Nếu đổi `console.setLevel(Level.INFO)`, điều gì thay đổi? → Console cũng in `INFO: order created`, nhưng `FINE` vẫn bị hai handler bỏ.
5. Nếu bỏ `logger.setUseParentHandlers(false)` trong ứng dụng có handler ở root, điều gì có thể xảy ra? → Event có thể đi thêm tới handler cha, tạo output bổ sung hoặc trùng.
6. Nếu cùng event được file và console nhận, có phải ứng dụng đã gọi logger hai lần? → Không; một event có thể được fan-out đến hai handler.
7. Nếu file log tồn tại, có chắc dữ liệu đã được gửi đến collector từ xa không? → Không; cần xác minh đường thu thập riêng.

**Ghi nhớ:** Nhiều đích ghi cho phép phân phối **một log event** tới các handler/appender có level, filter, format và chính sách lưu trữ riêng. Hãy đặt logger level đủ để tạo những event cần thiết, cấu hình từng đích theo mục đích sử dụng, tránh ghi trùng không mong muốn và kiểm tra đầy đủ hiệu năng, quyền truy cập, rotation cùng đường thu thập thực tế.