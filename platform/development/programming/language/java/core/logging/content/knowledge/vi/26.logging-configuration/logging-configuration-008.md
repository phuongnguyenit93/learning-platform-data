# Reload cấu hình logging trong Java

## 1. Reload cấu hình là gì và khi nào cần?

**Reload cấu hình logging** là việc ứng dụng đang chạy **đọc lại và áp dụng cấu hình ghi log** mà không phải khởi động lại toàn bộ JVM, nếu logging framework và cách triển khai hỗ trợ. Ví dụ: đang chạy với mức `INFO`, người vận hành muốn bật `DEBUG` tạm thời cho `com.example.payment` để điều tra lỗi; hoặc cần thay đổi định dạng, bộ lọc, đường dẫn đích ghi log theo một quy trình có kiểm soát.

Cần phân biệt ba việc thường bị gọi chung là “reload”:

1. **Đổi mức log đang chạy**: thay `Logger` level thông qua API quản trị hoặc API của framework, có thể không cần đọc file.
2. **Nạp lại file logging**: theo dõi thay đổi `logback.xml`, `log4j2.xml` hoặc file cấu hình riêng, phân tích và áp dụng cấu hình mới.
3. **Khởi động lại ứng dụng**: khởi tạo lại toàn bộ logging và ứng dụng; đây là cách cần dùng với một số tham số không hỗ trợ cập nhật trực tiếp.

**Reload logging không có nghĩa reload mọi cấu hình ứng dụng.** Đổi `application.properties` hoặc biến môi trường sau khi JVM khởi động không tự bảo đảm các thuộc tính đó sẽ được đọc lại. Việc đọc lại chỉ xảy ra khi có cơ chế cụ thể xử lý nguồn cấu hình đã thay đổi.

Các mục tiêu thực tế gồm giảm thời gian khắc phục sự cố, kiểm soát dung lượng log, thay đổi đầu ra theo môi trường và phục hồi cấu hình khi một thay đổi vận hành không đạt yêu cầu. Mỗi mục tiêu đòi hỏi phạm vi reload và cách xác minh khác nhau.

## 2. Mô hình hoạt động: nguồn cấu hình, bộ theo dõi và cấu hình hiệu lực

```text
[File cấu hình / lệnh quản trị]
              │
              ▼
 [Phát hiện thay đổi hoặc nhận yêu cầu]
              │
              ▼
       [Đọc và phân tích]
              │
              ▼
       [Kiểm tra hợp lệ]
              │
       ┌──────┴────────┐
       ▼               ▼
 [Hợp lệ]         [Không hợp lệ]
       │               │
       ▼               ▼
 [Áp dụng cấu hình] [Báo lỗi; xử lý theo
       │             cơ chế của framework]
       ▼
 [Logger / filter / appender mới]
       │
       ▼
 [Quan sát log thực tế, kiểm tra hậu quả]
```

Các thành phần có vai trò khác nhau:

- **Nguồn cấu hình**: file XML/properties, Java API, môi trường ứng dụng hoặc API quản trị. Source phải là nguồn mà logging system thực sự sử dụng.
- **Cơ chế phát hiện**: quét định kỳ (*polling*), giám sát file (*watch*), nút/endpoint quản trị hoặc thao tác gọi API chủ động.
- **Parser và validator**: phát hiện cấu hình sai cú pháp, phần tử hoặc thuộc tính không được hỗ trợ, sai tên appender, thiếu tham số.
- **LoggerContext / configuration manager**: áp dụng mức log, filter, appender, encoder và các tài nguyên liên quan theo hợp đồng cụ thể của framework.
- **Appender/sink**: ghi ra console, file, socket, hệ thống log tập trung; tài nguyên này có vòng đời riêng.
- **Bước xác minh**: kiểm tra log sau reload, trạng thái nội bộ và số lỗi/mất log, thay vì chỉ xác nhận file đã thay đổi.

**Đổi file thành công ≠ reload thành công ≠ log đã đến backend.** File có thể được lưu đúng nhưng watcher không nhìn thấy; framework có thể báo lỗi cấu hình; appender có thể được áp dụng nhưng không có quyền ghi hoặc bị nghẽn.

## 3. Những phần nào của logging có thể đổi khi đang chạy?

| Thành phần | Mục đích thay đổi | Giới hạn cần chú ý |
| --- | --- | --- |
| `Logger` level | Bật `DEBUG` hoặc giảm từ `DEBUG` về `INFO` | Level có thể kế thừa theo cây tên logger; cần xem **effective level** |
| Filter | Chọn sự kiện theo mức hoặc thuộc tính | Thay đổi filter có thể loại bỏ log quan trọng |
| Pattern/layout/encoder | Thêm `trace_id`, timestamp, JSON fields | Collector/parser phía sau có thể không tương thích với định dạng mới |
| Appender/sink | Đổi file hoặc hướng xuất log | Cần mở/đóng tài nguyên; kiểm tra đường dẫn, quyền ghi và flush |
| Async logging queue | Điều chỉnh hành vi log bất đồng bộ | Không phải tham số nào cũng áp dụng được mà không tạo lại appender/worker |
| Rolling policy | Điều chỉnh quay vòng/lưu giữ file | Có thể ảnh hưởng tên file, lock, file đang mở hoặc dữ liệu lưu trữ |
| Logger riêng của một package | Khoanh vùng điều tra | Tránh bật DEBUG cho root logger trên toàn hệ thống khi không cần |

Phạm vi cập nhật phụ thuộc phiên bản Logback, Log4j2, JUL, ứng dụng và môi trường. Không suy đoán rằng **mọi thuộc tính** của appender đều thay đổi ngay sau một lần reload. Chẳng hạn, một số tài nguyên cần được mở lại; một số framework có thể giữ tài nguyên cũ hoặc bỏ qua thay đổi nếu việc thay nóng có nguy cơ làm mất sự kiện.

Khi mục tiêu chỉ là điều chỉnh mức log để điều tra, cập nhật logger cụ thể qua API có thể đơn giản hơn thay cả cây appender. Khi cần đổi sink hoặc cấu trúc JSON, mới cân nhắc reload cấu hình đầy đủ.

## 4. Cơ chế tự động reload file trong Logback

Logback-classic hỗ trợ quét thay đổi trong file cấu hình và tự tái cấu hình khi được bật. Với ứng dụng Java sử dụng **Logback trực tiếp**, có thể đặt file cấu hình ở đường dẫn ngoài JAR và khai báo:

```xml
<!-- /etc/myapp/logback.xml: ví dụ cho Logback thông thường -->
<configuration scan="true" scanPeriod="30 seconds">
    <appender name="CONSOLE" class="ch.qos.logback.core.ConsoleAppender">
        <encoder class="ch.qos.logback.classic.encoder.PatternLayoutEncoder">
            <pattern>%d{HH:mm:ss.SSS} %-5level %logger{36} - %msg%n</pattern>
        </encoder>
    </appender>

    <logger name="com.example.payment" level="INFO"/>

    <root level="WARN">
        <appender-ref ref="CONSOLE"/>
    </root>
</configuration>
```

Ở ví dụ này:

- `scan="true"` yêu cầu Logback theo dõi thay đổi cấu hình.
- `scanPeriod="30 seconds"` đặt khoảng quét. Nếu không cấu hình, tài liệu Logback nêu mặc định quét khoảng **một phút**.
- `com.example.payment` có mức `INFO` riêng; mức của root là `WARN`. Logger cùng nhánh có thể kế thừa level từ logger cha nếu không tự khai báo mức khác.
- Appender `CONSOLE` được gắn tại root; logger payment mặc định có tính kế thừa appender (*additivity*) nên sự kiện đủ điều kiện được xuất qua root.
- Khi sửa thành `level="DEBUG"` và lưu file, sau lần quét hợp lệ các dòng DEBUG của nhóm logger này có thể xuất hiện.
- Logback theo dõi các file được `include` theo cơ chế reconfiguration của nó; điều kiện phát hiện thực tế vẫn cần kiểm thử trên hệ thống file đang dùng.

Nếu dùng file ngoài classpath và muốn Logback tìm đúng file, thiết lập Java system property **trước khi logging khởi tạo**. Lệnh minh họa:

```bash
java -Dlogback.configurationFile=/etc/myapp/logback.xml -jar myapp.jar
```

Đây là mẫu lệnh cho **ứng dụng Logback độc lập** có JAR sẵn. Trong Spring Boot, việc nạp file còn chịu cơ chế cấu hình logging của Boot; không coi mẫu lệnh này là quy trình phổ quát cho mọi ứng dụng Boot.

**Chú ý đơn vị thời gian:** `scanPeriod` của Logback hỗ trợ các đơn vị như `milliseconds`, `seconds`, `minutes`, `hours`. Nếu không ghi đơn vị, một số cấu hình được hiểu theo **mili giây**, dễ khiến ứng dụng quét quá dày. Luôn ghi tường minh, ví dụ `30 seconds`.

**Khi cấu hình mới sai:** tài liệu Logback mô tả cơ chế quay lại một cấu hình trước đó hợp lệ về **cú pháp XML** khi bản sửa gần nhất có lỗi cú pháp. Đừng mở rộng nhận định đó thành lời hứa rằng mọi lỗi tài nguyên, tên appender, ghi file, mạng hoặc cấu hình sai về ý nghĩa đều được khôi phục hoàn toàn. Cần theo dõi **internal status messages** và tự kiểm chứng dữ liệu đầu ra.

### Cách kiểm tra một thay đổi mức log của Logback

1. Xác nhận tiến trình đang dùng đúng file ngoài JAR đã khai báo; kiểm tra đường dẫn thực và quyền đọc.
2. Phát log `INFO` và `DEBUG` từ `com.example.payment` khi mức hiện tại là `INFO`; quan sát chỉ INFO xuất hiện (khi không có filter bổ sung làm khác).
3. Đổi `<logger name="com.example.payment" level="INFO"/>` thành `DEBUG` trong file và lưu.
4. Chờ qua khoảng quét; phát lại cùng sự kiện và quan sát DEBUG.
5. Xem trạng thái nội bộ của Logback nếu không thấy đổi, rồi trả mức INFO khi đã điều tra xong.

Khoảng `scanPeriod` là **chu kỳ kiểm tra**, không phải lời hứa thời gian áp dụng chính xác; thời điểm ghi file, độ trễ scheduler, I/O và cách mount dữ liệu có thể làm thời gian thực tế khác.

## 5. Reload file trong Log4j2

**Log4j2** có thuộc tính `monitorInterval` trên phần tử `Configuration` khi nguồn cấu hình cho phép theo dõi thay đổi. Trong Log4j2 2.x, đơn vị của giá trị này là **giây**; mặc định `0` nghĩa là tắt polling.

Ví dụ file **`log4j2.xml`** cho ứng dụng thực sự dùng Log4j2 Core:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<Configuration monitorInterval="30">
    <Appenders>
        <Console name="CONSOLE" target="SYSTEM_OUT">
            <PatternLayout pattern="%d{HH:mm:ss.SSS} %-5p %c - %m%n"/>
        </Console>
    </Appenders>

    <Loggers>
        <Logger name="com.example.payment" level="INFO"/>
        <Root level="WARN">
            <AppenderRef ref="CONSOLE"/>
        </Root>
    </Loggers>
</Configuration>
```

Sau khi đổi `level="INFO"` của `com.example.payment` thành `DEBUG` và Log4j2 phát hiện file đã đổi, hệ thống có thể tái cấu hình mà không khởi động lại ứng dụng.

Các điểm cần phân biệt với Logback:

- Tên tham số là `monitorInterval`, không phải `scanPeriod`.
- Cơ chế triển khai Log4j2 có các chiến lược tái cấu hình và tái sử dụng tài nguyên riêng; có trường hợp framework **bỏ qua thay đổi một thuộc tính appender** để tránh mất log khi đóng/mở tài nguyên.
- Chỉ chỉnh file hiệu quả khi đó là file được LoggerContext đang sử dụng và nguồn cho phép phát hiện thay đổi.
- Trong ứng dụng cấu hình qua API/nguồn tùy chỉnh, hành vi tự nạp lại phụ thuộc configuration source thực tế, không suy luận từ tên file.
- Các chi tiết xử lý file, resource và thời gian polling có thể khác theo phiên bản; khi triển khai thật cần đối chiếu tài liệu phiên bản đang dùng.

Nên kiểm tra **Log4j2 Status Logger**, log phát ra, nguồn và vị trí file sau reload. Không tuyên bố “không bao giờ mất log” cho toàn bộ pipeline: appender có thể phụ thuộc ổ đĩa, stdout collector, mạng, container hoặc backend nằm ngoài LoggerContext.

## 6. Trường hợp đặc biệt: Spring Boot và các cơ chế thay mức log

### 6.1. `logback-spring.xml` và xung đột với Logback scan

Spring Boot có các thẻ mở rộng như `<springProfile>` và `<springProperty>` cho Logback. Tài liệu Spring Boot xác nhận **các phần mở rộng này không dùng được với chế độ quét cấu hình của Logback**.

Ví dụ dưới đây **không phải cấu hình hợp lệ để kỳ vọng hot reload bằng scan**:

```xml
<!-- Ví dụ minh họa tổ hợp KHÔNG NÊN dùng cho hot reload -->
<configuration scan="true" scanPeriod="30 seconds">
    <springProfile name="dev">
        <!-- ... -->
    </springProfile>
</configuration>
```

Nếu scanner nạp lại file có các thẻ trên, có thể gặp lỗi parser kiểu `no applicable action for [springProfile]` hoặc `[springProperty]`.

Trong ứng dụng Boot sử dụng `logback-spring.xml` và các thẻ mở rộng, nên chọn một cơ chế quản trị do ứng dụng/Boot hỗ trợ, hoặc triển khai quy trình restart được kiểm soát khi cần thay toàn bộ cấu hình. Đừng bật `scan="true"` rồi mặc định rằng tính năng của Spring Boot vẫn áp dụng bình thường sau mỗi lần reload.

### 6.2. Chỉ đổi mức log: Spring Boot Actuator Loggers

Nếu có dependency Actuator và endpoint `loggers` đã được **cấp phép, mở ra và bảo vệ phù hợp**, có thể đọc/đổi mức log trong lúc ứng dụng chạy. Ví dụ request cho môi trường quản trị đã xác thực:

```http
GET /actuator/loggers/com.example.payment
```

Thông tin trả về có thể phân biệt:

- `configuredLevel`: mức được đặt trực tiếp cho logger; có thể `null` nếu kế thừa.
- `effectiveLevel`: mức thực sự có hiệu lực sau khi tính kế thừa.

Đổi sang DEBUG:

```http
POST /actuator/loggers/com.example.payment
Content-Type: application/json

{"configuredLevel":"DEBUG"}
```

Khi điều tra xong, có thể gửi `{"configuredLevel":null}` để xóa mức đặt trực tiếp, cho phép logger trở về cơ chế kế thừa/cấu hình mặc định theo hợp đồng endpoint.

Điểm cần nhớ:

- Cập nhật bằng Actuator là thay đổi **trạng thái mức log lúc chạy**; không mặc nhiên cập nhật file nguồn hay bảo đảm tồn tại sau restart.
- Nếu có một nguồn cấu hình khác tự reload, nó có thể ghi đè mức log đã đặt qua endpoint; cần làm rõ nguồn nào có quyền quyết định mức cuối cùng.
- Không đưa endpoint quản trị ghi thay đổi mức log ra Internet công khai; yêu cầu xác thực, phân quyền, ghi nhận ai đã đổi, giá trị trước/sau và khoảng thời gian bật DEBUG.
- Bật DEBUG toàn ứng dụng có thể tạo lượng log lớn và vô tình làm lộ dữ liệu trong message; ưu tiên chỉ logger/package cần điều tra.
- Không giả định cứ thay `logging.level.*` trong `application.yml` trên đĩa là Boot tự động áp dụng. Muốn có reload phải dùng một cơ chế thực sự hỗ trợ.

### 6.3. Điều gì cần restart?

Một thay đổi liên quan tới thư viện logging trên classpath, cách bootstrap logging, khởi tạo hệ thống với các Spring extension hoặc cấu hình tài nguyên không thể thay an toàn có thể cần restart. Hãy phân biệt **mức logger** với **cấu trúc appender** và **cấu hình ứng dụng ngoài logging** trước khi lựa chọn cách cập nhật.

## 7. Ví dụ Java 17 tự chạy: đọc lại mức log từ file

Để hiểu nguyên tắc trước khi dùng framework, ví dụ này dùng **`java.util.logging` (JUL)** có sẵn trong JDK. Ứng dụng ghi cấu hình vào một file `.properties` tạm, gọi hàm `reload` để đọc/kiểm tra mức mới rồi đặt `Logger#setLevel`. Sau đó thử một cấu hình không hợp lệ để chứng minh **không thay mức cũ khi parse thất bại**.

Đây là **reload được gọi chủ động**, không phải file watcher tự động. Chương trình chỉ đổi **mức logger**, không thay handler/formatter phức tạp.

Lưu thành **`LoggingConfigReloadDemo.java`**:

```java
import java.io.IOException;
import java.io.Reader;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Locale;
import java.util.Properties;
import java.util.logging.Handler;
import java.util.logging.Level;
import java.util.logging.LogRecord;
import java.util.logging.Logger;

public class LoggingConfigReloadDemo {
    private static final Logger LOGGER =
            Logger.getLogger("demo.payment");

    private static final Handler OUTPUT = new Handler() {
        {
            setLevel(Level.ALL);
        }

        @Override
        public void publish(LogRecord record) {
            if (isLoggable(record)) {
                System.out.println(
                    record.getLevel().getName() + " | "
                    + record.getMessage());
            }
        }

        @Override
        public void flush() {
            // Không có buffer riêng trong handler minh họa này.
        }

        @Override
        public void close() {
            // Không sở hữu tài nguyên cần đóng.
        }
    };

    private static void reload(Path file) throws IOException {
        Properties properties = new Properties();

        try (Reader reader =
                Files.newBufferedReader(file, StandardCharsets.UTF_8)) {
            properties.load(reader);
        }

        String raw = properties.getProperty("log.level");
        if (raw == null || raw.isBlank()) {
            throw new IllegalArgumentException("Missing log.level");
        }

        // Kiểm tra hoàn toàn trước khi thay đổi logger đang chạy.
        Level next = Level.parse(raw.trim().toUpperCase(Locale.ROOT));
        LOGGER.setLevel(next);
        System.out.println("RELOAD OK: " + next.getName());
    }

    public static void main(String[] args) throws Exception {
        LOGGER.setUseParentHandlers(false);
        LOGGER.addHandler(OUTPUT);

        Path file = Files.createTempFile("logging-reload-", ".properties");
        try {
            Files.writeString(file, "log.level=INFO\n",
                    StandardCharsets.UTF_8);
            reload(file);
            LOGGER.info("application started");
            LOGGER.fine("query parameters"); // Chưa được in.

            Files.writeString(file, "log.level=FINE\n",
                    StandardCharsets.UTF_8);
            reload(file);
            LOGGER.fine("query parameters");

            Files.writeString(file, "log.level=INVALID\n",
                    StandardCharsets.UTF_8);
            try {
                reload(file);
            } catch (IllegalArgumentException ex) {
                System.out.println("RELOAD FAILED, keeping FINE");
            }

            LOGGER.fine("still visible");
        } finally {
            LOGGER.removeHandler(OUTPUT);
            OUTPUT.close();
            Files.deleteIfExists(file);
        }
    }
}
```

Biên dịch và chạy bằng JDK 17 trở lên:

```bash
javac --release 17 LoggingConfigReloadDemo.java
java LoggingConfigReloadDemo
```

Đầu ra chuẩn (không chứa timestamp ngẫu nhiên):

```text
RELOAD OK: INFO
INFO | application started
RELOAD OK: FINE
FINE | query parameters
RELOAD FAILED, keeping FINE
FINE | still visible
```

Tại sao output này xác định?

1. Chương trình chạy tuần tự trong một luồng; cập nhật file trước, `reload` đọc file sau.
2. Logger bắt đầu ở `INFO` nên `FINE` đầu tiên bị lọc; handler đặt mức `ALL` và không có handler cha ghi lặp.
3. Sau `reload` thứ hai, `LOGGER.setLevel(FINE)` làm thông điệp FINE hiển thị.
4. `Level.parse("INVALID")` ném `IllegalArgumentException` **trước** câu lệnh `setLevel`; vì thế mức FINE trước đó vẫn có hiệu lực.
5. Handler tự định dạng ra stdout nên không có timestamp, thread name hay vị trí file phụ thuộc môi trường.

Cần hiểu đúng giới hạn: ví dụ có rollback hợp lệ vì chỉ cập nhật **một trường mức log** sau khi parse xong. Với cấu hình đầy đủ gồm nhiều appender, encoder và tài nguyên mạng, cần cơ chế áp dụng có quản lý vòng đời; không suy rộng rằng mọi hệ thống có thao tác reload nguyên tử như ví dụ.

## 8. Tự động phát hiện thay đổi bằng WatchService hoặc polling

Nếu ứng dụng tự quản lý file ngoài framework, Java NIO có `WatchService` để đăng ký các sự kiện như `ENTRY_CREATE`, `ENTRY_MODIFY` và `ENTRY_DELETE` trên **thư mục chứa file**. Sau khi nhận tín hiệu, ứng dụng kiểm tra tên file, đọc lại cấu hình, validate rồi áp dụng.

Tuy nhiên đây là nền tảng xây cơ chế reload, không phải lệnh “bật hot reload” cho Logback/Log4j2. Khi sử dụng `WatchService` cần xử lý:

- Một lần lưu file có thể phát nhiều sự kiện; nên **gộp/debounce** và bảo đảm chỉ có một lần apply tại một thời điểm.
- Trình soạn thảo hoặc hệ thống triển khai có thể ghi file tạm rồi rename; chỉ nghe `ENTRY_MODIFY` của một file cũ có thể bỏ sót cập nhật.
- Khi file được ghi chưa xong, scanner có thể đọc bản **dở dang**. Có thể validate trước và xuất bản file bằng rename nguyên tử khi hệ thống file hỗ trợ; kiểm tra thực tế thay vì mặc định mọi filesystem/mount đều hỗ trợ.
- Watcher ở container, network filesystem hoặc mount cấu hình có hành vi khác nhau; cần kiểm thử đúng hạ tầng. Polling có thể phù hợp hơn trong một số môi trường.
- Nếu file bị xóa, không nên tự áp dụng “cấu hình rỗng” khi chưa có chính sách; có thể giữ last-known-good và phát cảnh báo.
- Lỗi đọc file, invalid XML, quyền truy cập và retry phải được xử lý có giới hạn, tránh vòng lặp reload và spam log.

Nếu đã dùng cơ chế scanner được framework hỗ trợ, thường nên cấu hình scanner đó thay vì viết thêm một watcher chồng chéo cho cùng nguồn.

## 9. Quy trình đổi cấu hình an toàn trong môi trường đang chạy

### Bước 1 — Xác nhận trạng thái ban đầu

Ghi nhận phiên bản thư viện logging, file thực sự được nạp, nguồn đích, mức logger hiệu lực và số appender. Chụp ảnh trạng thái theo cách **không chứa secret**. Kiểm tra ứng dụng có dùng Logback, Log4j2, JUL hay bridge qua SLF4J, vì cấu hình của framework không hoạt động chỉ nhờ tên file.

### Bước 2 — Chọn phạm vi nhỏ nhất

Muốn điều tra một package? Đổi level package đó. Muốn đổi toàn bộ định dạng JSON? Cần xem lại collector/schema. Muốn chuyển từ file sang stdout? Cần kiểm tra cơ chế đóng file, container log pipeline và quyền ghi. Đừng dùng một reload lớn để giải quyết vấn đề chỉ cần một logger đổi mức.

### Bước 3 — Chuẩn bị cấu hình hợp lệ

Kiểm tra cú pháp XML/properties, tên logger, tham chiếu appender, đường dẫn/permission, format và tiêu chí giữ dữ liệu. Đối với file bên ngoài JAR, ưu tiên viết file tạm rồi thay thế theo cách hạ tầng hỗ trợ để giảm nguy cơ scanner đọc cấu hình đang được ghi dở.

Không đưa mật khẩu, token, cookie hoặc dữ liệu cá nhân vào cấu hình debug/log chỉ để tiện điều tra.

### Bước 4 — Áp dụng và quan sát

Lưu cấu hình hoặc gọi API quản trị đúng nơi. Kiểm tra phản hồi/reload status, sau đó phát **sự kiện thử** có ID riêng ở các level quan trọng. Xác nhận sự kiện xuất đúng sink và đúng định dạng. Xem queue backlog/drop khi logging bất đồng bộ và tài nguyên file/socket nếu đổi appender.

### Bước 5 — Giám sát và hoàn nguyên

Theo dõi độ trễ request, CPU, I/O, file size, queue depth, lỗi appender và tỷ lệ mất log. Nếu không đạt, trả lại cấu hình đã được kiểm chứng qua chính cơ chế áp dụng hiện hành. Nếu bật DEBUG tạm thời, xác định trước thời điểm và người chịu trách nhiệm đưa về INFO.

**Rollback file nguồn** cũng phải được phát hiện và áp dụng; chỉ copy file cũ lại không đủ nếu scanner không thấy thay đổi.

## 10. Sự nhất quán và rủi ro khi reload

### Thời điểm chuyển trạng thái

Trong lúc hệ thống đang chạy, các thread có thể phát log trước, trong và sau lần thay cấu hình. Vì vậy:

- Không mặc định mọi sự kiện có timestamp sau lúc lưu file đều dùng cấu hình mới.
- Có thể có một khoảng chuyển tiếp tùy cơ chế quản lý LoggerContext/appender.
- Mỗi sink và queue có bộ đệm riêng; event được enqueue trước khi reload có thể được ghi ra muộn.
- Nếu đổi pattern ở giữa một luồng log, có thể xuất hiện **hai dạng dòng log** trong cùng khoảng thời gian; collector phải có khả năng xử lý giai đoạn chuyển tiếp.
- Log đã ghi **không được chuyển lại định dạng cũ/mới** chỉ vì framework reload.

### Appender và mất hoặc trùng log

Với file appender, thay đường dẫn/rolling policy có thể tạo file mới hoặc tác động đến file đang mở. Với network appender, kết nối mới và retry có thể sinh lỗi hoặc duplicate. Với async appender, shutdown/recreate và queue chưa drain có thể khiến mất sự kiện nếu framework hoặc ứng dụng không xử lý đầy đủ.

Không dựa vào câu “reload thành công” để kết luận bảo đảm delivery. Nếu logging là nguồn audit bắt buộc, cần một đường ghi có bảo đảm bền vững riêng, không dùng logging in-memory như giao dịch exactly-once.

### Nhiều instance / Kubernetes

Sửa file bên trong một container chỉ ảnh hưởng container đó. Nếu chạy nhiều pod, cùng một thay đổi cấu hình có thể được áp dụng ở các thời điểm khác nhau. Volume, file mount và ConfigMap có cách cập nhật khác nhau; **giá trị cấu hình mới không mặc định kích hoạt reload** ở JVM. Cần thiết kế cách phát hành, kiểm tra trạng thái từng instance, bảo đảm quyền và phương án rollback. Mọi trường hợp nên quan sát version/config checksum (không chứa secret) trên từng instance.

## 11. Những lỗi phổ biến và cách tìm nguyên nhân

| Hiện tượng | Nguyên nhân có thể | Cách kiểm tra và xử lý |
| --- | --- | --- |
| Sửa file nhưng level không đổi | Ứng dụng đang dùng file khác hoặc scanner chưa bật | Xác định source configuration thực tế, tham số JVM, status log |
| Đã bật scan nhưng reload rất chậm | Chu kỳ polling, scheduler hoặc filesystem delay | Kiểm tra `scanPeriod`/`monitorInterval` và thời gian phát sự kiện thử |
| Không reload sau khi đổi ConfigMap | Mount/đường dẫn/tín hiệu file không như dự kiến | Kiểm tra kiểu volume/mount, inode/rename, log scanner trên pod |
| Boot báo lỗi `springProfile` khi scan | Dùng Spring Boot extension với Logback scan | Bỏ tổ hợp không được hỗ trợ; chọn cách thay mức hoặc restart phù hợp |
| Không thấy DEBUG sau reload | Logger vẫn kế thừa level khác, filter/appender chặn, sai tên package | Kiểm tra effective level, filter, appender threshold và sample logger |
| DEBUG xuất hiện quá nhiều | Đã bật ở root hoặc package quá rộng | Thu hẹp logger và đặt thời hạn tự hoàn nguyên theo quy trình |
| Log đổi pattern nhưng backend không parse | Collector/parser kỳ vọng schema cũ | Kiểm thử cấu hình parser và giai đoạn đồng tồn tại hai định dạng |
| Sau reload không ghi được file | Quyền/thư mục, disk full, file handle, sai path | Xem status appender, filesystem và kiểm tra có event thật |
| Có log trùng hoặc mất quanh reload | Appender cũ/mới, async queue, retry hoặc sink thay đổi | Đối chiếu event ID/count, dropped metric và trạng thái appender |
| File XML sai nhưng ứng dụng vẫn chạy | Framework giữ cấu hình cũ hoặc áp dụng một phần theo hợp đồng | Đọc status, xác minh mức/sink hiệu lực thay vì đoán |
| Đổi level qua Actuator rồi mất sau một lúc | Một nguồn cấu hình khác reload và ghi đè | Xác định thứ tự ưu tiên và nguồn cuối cùng quản lý logger |
| Sau restart các mức trở lại như cũ | Thay đổi runtime không được lưu vào nguồn startup | Ghi nhận thay đổi chính thức nếu cần duy trì |

## 12. Kiểm thử chức năng reload

Một bài kiểm thử có ý nghĩa phải có **trước/sau** và cả nhánh thất bại:

1. **Đổi INFO → DEBUG → INFO:** phát log ở hai mức và đếm kết quả. Chứng minh cấu hình có hiệu lực, không chỉ file đã đổi.
2. **Đúng phạm vi:** tăng mức cho `com.example.payment` nhưng logger không liên quan vẫn theo mức cũ.
3. **Lỗi cú pháp hoặc giá trị level:** thử cấu hình không hợp lệ trong môi trường thử nghiệm, quan sát status và chính sách giữ cấu hình cũ.
4. **Tải đồng thời:** nhiều request phát log khi reload; kiểm tra crash, exception, deadlock, đếm sự kiện/drop và độ trễ.
5. **Appender thay đổi:** nếu đổi sink, xác minh file/collector mới nhận event, sink cũ được xử lý theo hợp đồng và không bị rò rỉ tài nguyên.
6. **Nhiều instance:** kiểm tra mọi instance trong phạm vi phát hành đều nhận phiên bản cấu hình kỳ vọng.
7. **Khởi động lại:** xác minh hành vi sau restart là đúng ý định; thay đổi tạm thời phải biến mất hoặc cấu hình lâu dài phải tồn tại theo quyết định.
8. **Quan sát độc lập:** khi cấu hình log hỏng, vẫn có kênh status/metric/alarm đủ để biết reload đã thất bại.

Tránh dựa vào thứ tự vài dòng log khi thử đồng thời: log có thể được buffer, ghi bất đồng bộ hoặc chuyển qua collector. Định nghĩa rõ mốc nào được gọi là “đã ghi” trước khi khẳng định mất log.

## 13. Phân biệt reload, rotate và thay mức log

| Hoạt động | Mục đích | Có cần thay cấu hình? |
| --- | --- | --- |
| **Reload cấu hình** | Nạp lại nguồn để thay logger/filter/appender theo hỗ trợ | Có nguồn/trigger cấu hình rõ ràng |
| **Đổi level runtime** | Bật/tắt mức log của logger khi chạy | Có thể chỉ dùng API, không đọc file |
| **Log rotation** | Đóng/chuyển file log theo dung lượng/thời gian | Có thể chạy theo rolling policy hiện tại, không cần reload |
| **Restart** | Khởi tạo lại toàn JVM và logging | Dùng khi thay đổi không hỗ trợ áp dụng trực tiếp hoặc quy trình vận hành yêu cầu |

Không coi việc file `app.log` được rotate là cấu hình logging vừa reload. Tương tự, một lệnh gọi `setLevel` không chứng minh thay đổi đã được ghi lại vào `logback.xml`.

## 14. Checklist trước khi kết luận reload thành công

- Đã xác định chính xác framework, phiên bản, tên và vị trí file/nguồn cấu hình.
- Đã chọn cơ chế được hỗ trợ: Logback scan, Log4j2 monitor, API quản trị hoặc restart.
- Đã xác minh **không kết hợp Spring Boot extensions với Logback configuration scanning**.
- Đã kiểm tra cú pháp, appender references, quyền ghi và khả năng tương thích collector.
- Đã thay đổi đúng logger/sink cần thiết và giữ cách hoàn nguyên rõ ràng.
- Đã xem status/error từ framework; không dừng ở việc file có timestamp mới.
- Đã phát log thử và xác minh mức, định dạng, trace context và đích ghi thực tế.
- Đã kiểm tra queue/drop/retry khi logging bất đồng bộ, đặc biệt nếu thay appender.
- Đã xác nhận trạng thái hiệu lực trên các instance cần thiết và sau restart nếu yêu cầu.
- Đã giới hạn thời gian và quyền bật DEBUG, không log secret hoặc dữ liệu nhạy cảm.

**Ghi nhớ:** reload là **quá trình áp dụng trạng thái logging mới vào ứng dụng đang chạy**, không đơn thuần là lưu một file. Hãy kiểm tra ba khâu riêng: **nguồn cấu hình đã đổi → framework đã áp dụng → log thực tế đã ghi đúng**.

### Tài liệu chính thức để đối chiếu theo phiên bản

- [Logback: Configuration, automatic reloading](https://logback.qos.ch/manual/configuration.html)
- [Apache Log4j2: Configuration và monitorInterval](https://logging.apache.org/log4j/2.x/manual/configuration.html)
- [Spring Boot: Logging và Logback extensions](https://docs.spring.io/spring-boot/reference/features/logging.html)
- [Spring Boot Actuator: Loggers endpoint](https://docs.spring.io/spring-boot/reference/actuator/loggers.html)
