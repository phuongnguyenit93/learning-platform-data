# Định dạng level trong Java Logging: JUL, Logback và Log4j 2

## 1. Level là gì và vì sao phải định dạng?

Mỗi sự kiện log có một **level** biểu thị mức độ chi tiết hoặc mức độ nghiêm trọng. Trong console/file, formatter hoặc layout quyết định level sẽ được hiển thị thế nào: `INFO` hay `INFO `, `WARNING` hay `WARN`, có màu hay không, đứng trước hay sau logger name.

Ví dụ output text:

```text
INFO  | OrderService | event=order_accepted orderId=ORD-7
WARN  | PaymentClient | event=retry_scheduled attempt=2
ERROR | OrderService | event=order_save_failed orderId=ORD-8
```

Các dòng trên minh họa cách hiển thị; cú pháp gọi logger, tên level và pattern thực tế phụ thuộc logging API/backend.

Cần phân biệt ba việc:

1. **Gắn level cho event:** `logger.info(...)`, `logger.warn(...)`, `logger.error(...)` hay `java.util.logging.Logger.log(Level.WARNING, ...)`.
2. **Lọc theo level:** logger, filter, appender/handler quyết định event có được chuyển tới đích hay không.
3. **Định dạng level:** `Formatter`, `PatternLayout` hoặc encoder quyết định hiển thị nhãn, padding, màu, vị trí hoặc JSON field cho những event đã được chấp nhận.

**Đổi cách in `WARNING` thành `WARN` không đổi level gốc của event.** Và thay pattern `%level` không thể làm một event DEBUG đã bị filter xuất hiện trở lại. Đây là ranh giới quan trọng nhất của bài học.

## 2. So sánh các level thường gặp

| Ý nghĩa | SLF4J / Logback / Log4j 2 | JUL (`java.util.logging`) |
|---|---|---|
| Tracing rất chi tiết | `TRACE` | `FINER` hoặc `FINEST` có mục đích gần tương ứng |
| Thông tin debug | `DEBUG` | `FINE`; `CONFIG` là nhóm thông tin cấu hình |
| Hoạt động thông thường | `INFO` | `INFO` |
| Cảnh báo, suy giảm | `WARN` | `WARNING` |
| Lỗi nghiêm trọng | `ERROR` | `SEVERE` |

Bảng so sánh **ý nghĩa gần đúng**, không phải tiêu chuẩn ánh xạ bắt buộc. Log4j 2 còn có `FATAL`; JUL có thể có `Level` tùy chỉnh, ngoài ra `OFF`/`ALL` dùng cho cấu hình mức lọc. Những giá trị đặc thù phải được xử lý có chủ đích khi tích hợp nhiều backend.

Đặc biệt, không suy ra level chỉ từ trạng thái nghiệp vụ: một retry tạm thời có thể là WARN/DEBUG, còn thất bại cuối cùng của job có thể là ERROR. Format đẹp không thay thế quyết định level đúng.

## 3. Định dạng level dạng văn bản

Tên level có độ dài khác nhau:

```text
INFO     : 4 ký tự
WARN     : 4 ký tự
ERROR    : 5 ký tự
DEBUG    : 5 ký tự
TRACE    : 5 ký tự
SEVERE   : 6 ký tự
WARNING  : 7 ký tự
```

Nếu in ngay sát một ký tự phân tách, các cột có thể lệch. **Padding** làm level chiếm độ rộng tối thiểu thống nhất.

Ví dụ căn trái trong cột rộng 7:

```text
INFO    | OrderService | ...
WARNING | PaymentClient | ...
SEVERE  | OrderService | ...
```

Với `INFO`, formatter thêm ba dấu cách cho đủ độ rộng 7; pattern bên ngoài còn thêm một dấu cách trước `|`. Với `WARNING`, tên đã dài 7 nên không thêm padding.

### Căn trái, căn phải và cắt bớt

- **Căn trái**: `INFO␠␠␠` (ba khoảng trắng sau `INFO` nếu width=7).
- **Căn phải**: `␠␠␠INFO` (ba khoảng trắng trước `INFO`).
- **Độ rộng tối thiểu**: nếu nhãn dài hơn width, các formatter thông dụng vẫn xuất đủ, trừ khi có quy tắc precision/truncation khác.
- **Không nên cắt tên severity theo số ký tự** để biến `SEVERE` thành `SEVE` hoặc `WARNING` thành `WARNI`; đó không phải một cách mapping level có ý nghĩa.

Ký hiệu `␠` ở đây chỉ được dùng để mô tả **một dấu cách**, không phải ký tự mà Java phải in.

Nếu output dùng cho máy đọc, định dạng cột cố định có thể làm parser phụ thuộc khoảng trắng và dễ vỡ khi thay pattern. Khi cần truy vấn theo severity, ưu tiên field có cấu trúc thay vì cắt chuỗi bằng vị trí cố định.

## 4. JUL: lấy level từ LogRecord

Trong JUL, khi gọi:

```java
LOG.log(Level.WARNING, "event=cache_degraded");
```

logger tạo hoặc xử lý một `LogRecord` mang `Level.WARNING`, rồi `Handler` và `Formatter` quyết định đầu ra. Trong phương thức `Formatter.format(LogRecord)`:

```java
Level level = record.getLevel();
String levelName = level.getName();
```

Hai dòng này chỉ là minh họa bên trong formatter, giả định biến `record` tồn tại. Với các level chuẩn:

- `Level.INFO.getName()` trả `INFO`.
- `Level.WARNING.getName()` trả `WARNING`.
- `Level.SEVERE.getName()` trả `SEVERE`.
- `Level.FINE.getName()` trả `FINE`.

`getLocalizedName()` có thể trả một nhãn cục bộ hóa tùy bundle/locale. Nếu level được dùng để tìm kiếm, lập alert hoặc tổng hợp liên dịch vụ, nên ưu tiên tên chuẩn/schema ổn định hơn tên dịch theo môi trường.

### 4.1. `SimpleFormatter` và định dạng theo tham số vị trí

JUL có `java.util.logging.SimpleFormatter`. Trong `logging.properties`, có thể tùy chỉnh chuỗi format:

```properties
handlers=java.util.logging.ConsoleHandler
.level=INFO
java.util.logging.ConsoleHandler.level=INFO
java.util.logging.ConsoleHandler.formatter=java.util.logging.SimpleFormatter
java.util.logging.SimpleFormatter.format=%4$-7s | %3$s | %5$s%6$s%n
```

Các tham số vị trí của `SimpleFormatter` gồm:

| Tham số | Nội dung |
|---|---|
| `%1$...` | Date/time của log record |
| `%2$s` | Source, ví dụ tên class/phương thức |
| `%3$s` | Logger name |
| `%4$s` | Level name |
| `%5$s` | Message đã format |
| `%6$s` | Throwable/stack trace đã format nếu có |
| `%n` | Ký tự xuống dòng theo hệ điều hành |

`%4$-7s` là cú pháp của **`java.util.Formatter`**: lấy đối số thứ tư, căn trái, rộng tối thiểu 7. Nó **không phải** cú pháp của Logback PatternLayout.

Ứng dụng có thể nạp file với JVM property:

```bash
java -Djava.util.logging.config.file=logging.properties com.example.Main
```

Đây là lệnh minh họa; cần có class `com.example.Main` đã biên dịch và đường dẫn file đúng. Framework hoặc container có thể quản lý `LogManager` khác. Chỉ đặt `logging.properties` trong project không bảo đảm nó tự được nạp.

### 4.2. Formatter tùy chỉnh

Có thể chủ động xây chuỗi bằng `String.format`:

```java
@Override
public String format(LogRecord record) {
    return String.format(
            java.util.Locale.ROOT,
            "%-7s | %s | %s%n",
            record.getLevel().getName(),
            record.getLoggerName(),
            formatMessage(record));
}
```

Đây là **method minh họa** trong một lớp con của `Formatter`, không phải tệp Java hoàn chỉnh. Dùng `formatMessage(record)` để thay parameters `{0}`, `{1}` theo quy tắc JUL; `record.getMessage()` chỉ trả về mẫu gốc.

**Quan trọng:** formatter trên không xuất stack trace. Khi cần chẩn đoán exception thật, phải xử lý `record.getThrown()` hoặc chọn formatter có hỗ trợ Throwable và cause chain đầy đủ. Việc định dạng level không được làm mất thông tin lỗi.

## 5. Java 17+ chạy độc lập: formatter level trong JUL

Ví dụ chỉ sử dụng JDK, không cần Maven và dependency ngoài.

Tạo tệp `LevelFormatDemo.java`:

```java
import java.util.Locale;
import java.util.logging.ConsoleHandler;
import java.util.logging.Formatter;
import java.util.logging.Level;
import java.util.logging.LogRecord;
import java.util.logging.Logger;

public final class LevelFormatDemo {
    private static final Logger LOG =
            Logger.getLogger(LevelFormatDemo.class.getName());

    public static void main(String[] args) {
        LOG.setUseParentHandlers(false);
        LOG.setLevel(Level.ALL);

        ConsoleHandler console = new ConsoleHandler();
        console.setLevel(Level.ALL);
        console.setFormatter(new Formatter() {
            @Override
            public String format(LogRecord record) {
                return String.format(
                        Locale.ROOT,
                        "%-7s | %s | %s%n",
                        record.getLevel().getName(),
                        record.getLoggerName(),
                        formatMessage(record));
            }
        });
        LOG.addHandler(console);

        LOG.info("event=app_started");
        LOG.warning("event=cache_degraded");
        LOG.log(Level.SEVERE,
                "event=order_save_failed orderId={0}",
                new Object[]{"ORD-7"});
        LOG.fine("event=debug_probe");

        console.flush();
    }
}
```

Biên dịch/chạy từ thư mục chứa tệp với JDK 17 trở lên:

```bash
javac -encoding UTF-8 LevelFormatDemo.java
java LevelFormatDemo
```

Nội dung hiển thị trên **stderr**:

```text
INFO    | LevelFormatDemo | event=app_started
WARNING | LevelFormatDemo | event=cache_degraded
SEVERE  | LevelFormatDemo | event=order_save_failed orderId=ORD-7
FINE    | LevelFormatDemo | event=debug_probe
```

`ConsoleHandler` của JUL mặc định ghi vào `System.err`; chương trình không ghi stdout. Đầu ra không có timestamp để dễ đối chiếu.

### Bóc tách code

1. `LOG.setLevel(Level.ALL)` cho phép logger phát các event từ FINE trở lên; `console.setLevel(Level.ALL)` giúp handler không loại FINE.
2. `setUseParentHandlers(false)` tránh gửi cùng event lên handler cha/root mặc định, nên output không bị lặp.
3. `record.getLevel().getName()` in tên JUL thật: `WARNING` và `SEVERE`, không tự đổi thành `WARN` hay `ERROR`.
4. `%-7s` căn trái: `INFO` được thêm ba khoảng trắng, `WARNING` không cần thêm; chuỗi định dạng bổ sung một dấu cách trước `|`.
5. `formatMessage(record)` thay `{0}` bằng `ORD-7`.
6. `console.flush()` yêu cầu handler đẩy output đã buffer; đây không phải cam kết lưu bền vững trong mọi hệ thống.

Nếu đổi `LOG.setLevel(Level.ALL)` thành `LOG.setLevel(Level.INFO)`, dòng FINE bị loại nhưng hình thức các level còn lại không thay đổi. **Level policy và level format là hai trách nhiệm riêng.**

### Map sang nhãn phổ biến mà không sửa Level gốc

Nếu cần trình bày `WARN/ERROR` trong một output text chung, có thể dùng một method:

```java
// Minh họa bên trong custom Formatter:
private static String displayLevel(Level level) {
    if (level == Level.WARNING) return "WARN";
    if (level == Level.SEVERE) return "ERROR";
    return level.getName();
}
```

Khi dùng `displayLevel(record.getLevel())` để format, event vẫn mang `Level.WARNING` hoặc `Level.SEVERE`. Các level tùy biến cần quy tắc riêng; đừng tự biến chúng thành ERROR nếu không rõ semantics. Nếu collector muốn giữ nguồn gốc, có thể lưu thêm `originalLevel`.

## 6. Logback PatternLayout: `%level`, `%p` và padding

Trong Logback Classic, pattern layout thường hỗ trợ:

- `%level`: tên level, ví dụ `INFO`, `WARN`, `ERROR`.
- `%p`: alias của conversion level.
- `%-5level` hoặc `%-5p`: căn trái, rộng tối thiểu 5 ký tự.
- `%5level` hoặc `%5p`: căn phải, rộng tối thiểu 5 ký tự.

Ví dụ:

```xml
<pattern>%-5level | %logger{0} | %msg%n</pattern>
```

Với `INFO`, `%-5level` xuất `INFO` kèm **một dấu cách padding**, sau đó pattern còn có `" | "`. Vì vậy có **hai dấu cách trước ký tự `|`**. Với `ERROR`, tên có đúng 5 ký tự, không cần padding.

### 6.1. `logback.xml` hoàn chỉnh

```xml
<configuration>
    <appender name="CONSOLE"
              class="ch.qos.logback.core.ConsoleAppender">
        <target>System.out</target>
        <encoder>
            <pattern>%-5level | %logger{0} | %msg%n</pattern>
        </encoder>
    </appender>

    <root level="TRACE">
        <appender-ref ref="CONSOLE"/>
    </root>
</configuration>
```

Root TRACE trong ví dụ nhằm cho cả năm mức xuất hiện. Trong production thường không nên bật TRACE toàn hệ thống, vì lượng log và nguy cơ lộ dữ liệu có thể tăng.

### 6.2. Chương trình Java 17+ dùng SLF4J/Logback qua Maven

Cấu trúc:

```text
logback-level-format/
├── pom.xml
└── src/
    └── main/
        ├── java/com/example/logging/LevelLogbackDemo.java
        └── resources/logback.xml
```

Tệp `pom.xml`:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>com.example</groupId>
    <artifactId>logback-level-format</artifactId>
    <version>1.0-SNAPSHOT</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>ch.qos.logback</groupId>
            <artifactId>logback-classic</artifactId>
            <version>1.5.12</version>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.13.0</version>
            </plugin>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.5.0</version>
                <configuration>
                    <mainClass>com.example.logging.LevelLogbackDemo</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
```

Tệp `src/main/java/com/example/logging/LevelLogbackDemo.java`:

```java
package com.example.logging;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

public final class LevelLogbackDemo {
    private static final Logger LOG =
            LoggerFactory.getLogger(LevelLogbackDemo.class);

    public static void main(String[] args) {
        LOG.trace("event=trace_probe");
        LOG.debug("event=debug_probe");
        LOG.info("event=app_started");
        LOG.warn("event=cache_degraded");
        LOG.error("event=save_failed");
    }
}
```

Tệp `src/main/resources/logback.xml` dùng đúng cấu hình mục 6.1. Với Maven, JDK 17+ và quyền tải dependency, chạy:

```bash
mvn -q compile exec:java
```

Các dòng **do Logback ghi vào stdout**:

```text
TRACE | LevelLogbackDemo | event=trace_probe
DEBUG | LevelLogbackDemo | event=debug_probe
INFO  | LevelLogbackDemo | event=app_started
WARN  | LevelLogbackDemo | event=cache_degraded
ERROR | LevelLogbackDemo | event=save_failed
```

Các dòng INFO/WARN có **hai dấu cách trước `|`**, gồm một dấu padding và một dấu thuộc pattern. Maven có thể phát thông báo build/tool riêng theo môi trường; đoạn này chỉ mô tả các dòng **của Logback appender**.

Phiên bản Logback trong `pom.xml` chỉ là giá trị cố định cho ví dụ, không phải khuyến cáo về bản phát hành mới nhất. Ứng dụng thật phải kiểm tra dependency management, JDK tương thích và các bản vá bảo mật.

### Căn trái so với căn phải

| Pattern Logback | Phần level tạo ra | Ý nghĩa |
|---|---|---|
| `%level` | `INFO` | Không padding |
| `%-5level` | `INFO␠` | Căn trái tới width 5 |
| `%5level` | `␠INFO` | Căn phải tới width 5 |
| `%-5p` | `INFO␠` | Alias level, căn trái |

Ký hiệu `␠` trong bảng là dấu cách minh họa. Nếu tên level dài hơn độ rộng tối thiểu thì thường vẫn in đủ, trừ khi thêm quy tắc truncation khác.

## 7. Log4j 2: Level converter trong PatternLayout

Log4j 2 hỗ trợ `%p`/`%level` trong `PatternLayout`. Một cấu hình Log4j 2 có thể viết:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<Configuration>
    <Appenders>
        <Console name="CONSOLE" target="SYSTEM_OUT">
            <PatternLayout pattern="%-5p | %c{1} | %m%n"/>
        </Console>
    </Appenders>

    <Loggers>
        <Root level="info">
            <AppenderRef ref="CONSOLE"/>
        </Root>
    </Loggers>
</Configuration>
```

Giải thích:

- `%-5p` hiển thị level căn trái với độ rộng tối thiểu 5.
- `%c{1}` rút gọn tên logger cho mục đích hiển thị.
- `%m%n` xuất message và newline.
- `Root level="info"` là **ngưỡng lọc**, không phải độ rộng của cột level.
- File `log4j2.xml` dùng định dạng cấu hình của Log4j 2, **không phải** `logback.xml` hoặc JUL `logging.properties`.

Muốn chạy thực tế cần Log4j 2 API/Core và tích hợp provider đúng với API ứng dụng gọi. Không thêm Logback và provider Log4j 2 cùng lúc nếu ứng dụng đang chọn một backend qua SLF4J, và không ghép bridge ngược chiều gây vòng lặp.

### So sánh cú pháp

| Ý định | JUL | Logback | Log4j 2 |
|---|---|---|---|
| Hiển thị tên level | `record.getLevel().getName()` hoặc `%4$s` của SimpleFormatter | `%level` / `%p` | `%level` / `%p` |
| Căn trái tối thiểu 5 | `String.format("%-5s", name)` hoặc `%4$-5s` | `%-5level` | `%-5p` |
| Tên cảnh báo chuẩn | `WARNING` | `WARN` | `WARN` |
| Tên lỗi thông thường | `SEVERE` | `ERROR` | `ERROR` |
| File cấu hình | `logging.properties` | `logback.xml` | `log4j2.xml` |

Cú pháp một vài token Logback và Log4j 2 nhìn giống nhau, nhưng cấu hình appender, layout, routing và conversion nâng cao không mặc nhiên tương thích.

## 8. Tô màu level bằng ANSI: chỉ dành cho output người đọc

Màu giúp nhận biết WARN/ERROR nhanh khi quan sát console. Với Logback, một pattern minh họa:

```xml
<pattern>%highlight(%-5level) | %logger{0} | %msg%n</pattern>
```

Với Log4j 2 PatternLayout:

```xml
<PatternLayout pattern="%highlight{%-5p} | %c{1} | %m%n"/>
```

Đây là **fragment** phụ thuộc backend/version và terminal hỗ trợ. Màu thường được mã hóa bằng **ANSI escape sequences**. Khi ghi log vào file, collector hoặc hệ thống không hỗ trợ màu, mã ANSI có thể tạo ký tự lạ, ảnh hưởng regex parser hoặc làm sai giá trị severity.

Quy tắc thực hành:

- Chỉ tô màu cho console tương tác nếu môi trường hỗ trợ.
- Không lưu mã ANSI trong trường JSON `level`.
- Không dựa hoàn toàn vào màu để biểu thị mức độ; người đọc có thể không phân biệt màu.
- Đổi màu không thay đổi ngưỡng log và không làm sự kiện DEBUG bị filter xuất hiện.
- Nếu thu cả stdout và stderr, kiểm tra đích của appender riêng; layout màu không quyết định stderr/stdout.

## 9. Định dạng level trong structured logging và JSON

Trong hệ thống tập trung, level nên là **trường có cấu trúc ổn định**:

```json
{
  "timestamp": "2026-11-09T08:15:03.125Z",
  "logger": "com.example.orders.OrderService",
  "level": "WARN",
  "event": "dependency_degraded",
  "message": "inventory lookup slow",
  "requestId": "req-42"
}
```

JSON là **mẫu schema**, không phải output của hai chương trình Java bên trên. Để tạo JSON thật, cần encoder/layout/serializer hỗ trợ JSON, và ứng dụng phải cung cấp event/context thực sự.

**Không đưa padding vào dữ liệu severity**:

```json
{"level":"WARN","message":"dependency degraded"}
```

Tránh:

```json
{"level":"WARN ","message":"dependency degraded"}
```

Trường có một dấu cách thừa thường không khớp với bộ lọc `level == "WARN"`. Padding là dành cho bản trình bày text, không phải giá trị máy đọc.

### 9.1. Chuẩn hóa giữa JUL và các backend khác

Nếu collector dùng nhãn `WARN` và `ERROR`, còn JUL phát `WARNING` và `SEVERE`, có thể định nghĩa mapping. Có thể giữ cả thông tin gốc:

```json
{
  "level": "WARN",
  "originalLevel": "WARNING",
  "loggingSystem": "JUL"
}
```

Đây là lựa chọn schema, không phải quy định bắt buộc. Với level `CONFIG`, `FATAL` hoặc tùy chỉnh, chính sách mapping phải ghi rõ; không tự đoán bằng độ dài tên hoặc sắp xếp chữ cái.

Một số chuẩn observability dùng `severityText` và `severityNumber`; nếu áp dụng, phải theo định nghĩa severity của chuẩn và quy tắc mapping đã chốt. Không so sánh `"WARN"` và `"ERROR"` như hai chuỗi từ điển để quyết định mức nào nghiêm trọng hơn.

### 9.2. MDC/context không phải level

Một event có thể có `level=INFO` đồng thời mang `traceId`, `requestId` hoặc `userId` (nếu được phép ghi). Với SLF4J/Logback, **MDC** thường cung cấp các trường ngữ cảnh như `requestId`, còn level do logger event quyết định. Đừng nhét request ID vào chuỗi level như `"INFO_req-42"`; điều đó phá khả năng lọc và tổng hợp severity.

MDC cũng không tự chuyển giữa các thread nghiệp vụ; cần truyền và dọn đúng khi dùng thread pool. Layout JSON không thể khôi phục request ID chưa hề được gắn vào event.

## 10. Level trong filter, alert và dashboard

Pipeline vận hành có thể như sau:

```text
Ứng dụng phát JUL Level.WARNING
      |
      v
Logger/Handler áp dụng level/filter
      |
      v
Formatter xuất "WARNING"
      |
      v
Collector chuẩn hóa thành "WARN"
      |
      v
Alert theo severity chuẩn hóa
```

Các khâu này có vai trò khác nhau:

- Nếu event bị **lọc từ đầu**, không còn gì để format.
- Nếu formatter ghi sai alias `WARNING` → `ERROR`, dashboard có thể báo sai mức độ.
- Nếu collector parser chỉ hiểu `WARN`, event JUL `WARNING` có thể bị bỏ sót.
- Nếu pattern text đổi từ `%level - %msg` sang `%level | %logger | %msg`, parser cũ có thể không trích xuất level đúng.
- Nếu một exception được log nhiều tầng, số dòng ERROR có thể vượt số request thất bại thật; đây là vấn đề chiến lược logging, không chỉ level format.

**Đừng lấy số dòng ERROR làm error rate chính xác** khi không kiểm soát việc ghi trùng, sampling và mất sự kiện. Metrics nên đếm theo đơn vị công việc rõ ràng, còn logs dùng để điều tra ngữ cảnh.

### Ngưỡng lọc khác độ rộng cột

- `<root level="INFO">` trong Logback: điều kiện phát event.
- `%-5level` trong PatternLayout: trình bày event đã được chấp nhận.

Tăng width không bật DEBUG. Hạ ngưỡng từ INFO xuống DEBUG không bắt buộc thay đổi format. Việc theo dõi hiệu lực phải nhìn cả logger level, appender/filter và pipeline đích.

## 11. Hiệu năng và độ an toàn

Định dạng một nhãn level ngắn thường rẻ hơn render exception stack trace hoặc serialize JSON lớn, nhưng có những điểm cần cân nhắc:

1. `String.format(...)` phân tích format và cấp phát đối tượng; nếu lượng event rất lớn, có thể đánh giá `StringBuilder`/padding đơn giản sau khi profiling.
2. Pattern chứa caller class/method/line có thể phát sinh chi phí lấy stack/caller data; không nên quy toàn bộ overhead cho `%level`.
3. ANSI color thêm escape sequences và công xử lý, không hữu ích với collector nếu output máy đọc.
4. JSON encoder có chi phí serialization/escaping riêng; chọn schema đủ dùng.
5. Log message chứa dữ liệu người dùng phải có chính sách escaping/giới hạn kích thước. `%level` không tự bảo vệ chống log injection từ message.
6. Không ghi password, token, session cookie hoặc thông tin nhạy cảm vào message/context chỉ vì muốn debug. Level cao hay thấp không phải cơ chế masking.
7. Với async appender, một số bước format được chuyển sang worker tùy implementation; điều đó không khiến mọi biểu thức đối số của Java trở thành lazy.

Thêm một trường severity có cấu trúc ổn định thường hữu ích hơn việc tạo pattern text quá cầu kỳ.

## 12. Lỗi thường gặp và xử lý

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| Log JUL hiện `WARNING`, dashboard chỉ nhận `WARN` | Chưa chuẩn hóa level | Mapping alias chính xác ở collector/formatter |
| Log JUL hiện `SEVERE`, alert đếm `ERROR` thiếu | Khác tên level | Chuẩn hóa schema severity hoặc hỗ trợ cả nhãn gốc |
| Cột level bị lệch | Các nhãn dài ngắn khác nhau | Thêm width/padding trong text layout |
| JUL hiện nguyên `%-5level` | Dùng pattern Logback trong SimpleFormatter | Dùng `%4$-5s` hoặc custom Formatter |
| Logback hiện nguyên `%4$s` | Dùng cú pháp JUL trong PatternLayout | Dùng `%level`/`%-5level` |
| Không thấy DEBUG | Bị logger/filter/appender chặn trước formatter | Kiểm tra effective level và đích |
| Field JSON là `"WARN "` | Mang padding text vào raw value | Lưu `"WARN"` không khoảng trắng |
| Mã màu ANSI xuất trong file | Bật highlight khi collector không hỗ trợ | Bỏ color cho output máy đọc |
| Severity bị dịch khác theo máy | Dùng localized label làm khóa | Dùng tên chuẩn/JSON schema ổn định |
| Alert phát sai sau khi đổi format | Parser hoặc mapping không đồng bộ | Test cả raw event và field sau collector |
| Stack trace biến mất | Formatter chỉ ghi level và message | Ghi Throwable/cause chain đúng |
| Log trùng sau thay layout | Handler cha/appenders/additivity | Kiểm tra đường đi record, không nhầm với format |
| Mất request ID | Không có MDC/context hoặc context không chuyển thread | Truyền định danh riêng, không gộp vào level |

### Quy trình debug có hệ thống

1. Xác định **API phát log** và **backend nhận log** (JUL, Logback, Log4j 2, bridge).
2. Xem level thật của event trước khi format, nếu có thể.
3. Kiểm tra logger level/filter và handler/appender level/filter.
4. Xác định formatter/layout/encoder và file cấu hình đang được nạp.
5. Kiểm tra đúng cú pháp: JUL `%4$s`, Logback `%-5level`, Log4j 2 `%-5p`.
6. Ghi event mẫu ở INFO, WARN/WARNING, ERROR/SEVERE và so output sau collector.
7. Kiểm tra alert, dashboard, log search và parser có dùng schema cuối cùng đúng không.

## 13. Checklist thực hành

- [ ] Chọn level dựa trên ý nghĩa của event, không dựa vào hình thức message.
- [ ] Phân biệt rõ **level filtering** và **level formatting**.
- [ ] Dùng đúng API/pattern của backend đang chạy.
- [ ] Căn lề text bằng width tối thiểu, không cắt cụt tên severity.
- [ ] Không mang padding hoặc ANSI vào JSON field `level`.
- [ ] Có mapping có chủ đích `WARNING↔WARN`, `SEVERE↔ERROR` nếu gom nhiều hệ logging.
- [ ] Level đặc thù như `CONFIG`, `FATAL` hoặc level tự định nghĩa có chính sách riêng.
- [ ] Dùng severity field ổn định cho máy đọc; tránh localized text làm khóa tìm kiếm.
- [ ] Formatter không làm mất parameters, Throwable/stack trace cần thiết.
- [ ] Alert/metrics không dựa vào so sánh từ điển của chữ `WARN/ERROR`.
- [ ] Có kiểm thử với runtime thật, output text/JSON và collector thật.
- [ ] Không lộ dữ liệu nhạy cảm trong message, context hoặc exception.

**Kết luận:** định dạng level là trách nhiệm của **formatter/layout/encoder**. Với JUL dùng `LogRecord.getLevel()` và `SimpleFormatter` hoặc custom `Formatter`; với Logback và Log4j 2 dùng `%level`/`%p` cùng width khi cần. Lọc event theo level là trách nhiệm riêng của logger/filter/handler/appender. Khi logs được tập trung, nên dùng severity field có cấu trúc, chuẩn hóa và không chứa padding/ANSI, để vừa dễ đọc vừa bảo toàn ý nghĩa cho tìm kiếm, giám sát và cảnh báo.
