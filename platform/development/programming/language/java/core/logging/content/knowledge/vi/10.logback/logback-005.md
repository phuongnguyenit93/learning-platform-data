# Layout của Logback: định dạng bản ghi log bằng PatternLayout

## Mục tiêu học tập

Trong Logback, cùng một sự kiện có thể xuất thành dòng console ngắn gọn, dòng file có đủ timestamp và logger, hoặc một định dạng phục vụ công cụ thu thập log. Bài này giúp bạn hiểu **Layout làm gì, mối quan hệ giữa Layout và Encoder**, cách đọc và thiết kế **PatternLayout**, cấu hình bằng **logback.xml**, xử lý MDC, exception, thông tin caller, và kiểm tra tính dễ đọc, an toàn, ổn định của định dạng log.

Sau bài học, bạn có thể:
- Phân biệt **logging event, Layout, Encoder, Appender** và vị trí của mỗi thành phần trong pipeline.
- Sử dụng các conversion word thông dụng: **%d, %level, %thread, %logger, %msg, %n, %X, %ex**.
- Giải thích và sửa lỗi của các pattern có field thừa/thiếu, padding, timestamp không có timezone hoặc thông tin exception bị hiểu sai.
- Cấu hình một ví dụ **Java 17 + SLF4J + Logback Classic** với Maven và dự đoán đúng các dòng log.
- Điều chỉnh pattern theo local và production; cân nhắc cấu trúc dữ liệu, multiline, MDC, bảo mật, hiệu năng và hệ thống thu thập log.

Bài thuộc nhóm **Logback** của Java Core Logging. Nội dung tập trung vào **Layout của Logback**, không biến thành hướng dẫn chung về mọi framework logging.

## 1. Layout là gì?

**Layout** là thành phần chuyển **một logging event** thành **một chuỗi String** theo định dạng được quy định. Với Logback Classic, layout dùng nhiều nhất là **ch.qos.logback.classic.PatternLayout**. Nó đọc thông tin từ sự kiện và dùng một **conversion pattern** để xác định thứ tự, cách trình bày, độ rộng và các trường xuất hiện.

Ví dụ ứng dụng phát một sự kiện với:
- Level: INFO.
- Logger: com.example.checkout.OrderService.
- Thread: main.
- Message đã định dạng: order.created orderId=OD-42 items=2.
- MDC requestId: req-42.

Layout có pattern:

~~~text
%level | requestId=%X{requestId} | %msg%n
~~~

Có thể tạo ra dòng:

~~~text
INFO | requestId=req-42 | order.created orderId=OD-42 items=2
~~~

Phần chữ **requestId=**, dấu **|** và các khoảng trắng là **literal text** được viết trực tiếp trong pattern. **%level**, **%X{requestId}** và **%msg** lần lượt lấy level, giá trị MDC và message. **%n** thêm ký tự xuống dòng phù hợp nền tảng.

Layout **không quyết định sự kiện có xảy ra hay không, level có được phép xuất hay không, hoặc log phải ghi vào file nào**. Nó chỉ mô tả **cách biểu diễn** những thông tin đã có trong event. Logger, level/filter và Appender giải quyết các trách nhiệm khác.

## 2. Phân biệt Logging Event, Layout, Encoder và Appender

Pipeline khái niệm:

~~~mermaid
flowchart LR
    A["Mã Java gọi Logger"] --> B["Level / Filter"]
    B --> C["ILoggingEvent"]
    C --> D["Appender"]
    D --> E["Encoder dùng PatternLayout"]
    E --> F["Bytes"]
    F --> G["Console hoặc file"]
~~~

Sơ đồ tập trung vào trách nhiệm, không mô tả toàn bộ cơ chế bất đồng bộ và xử lý lỗi nội bộ của từng appender.

| Thành phần | Nhận | Tạo ra / trách nhiệm |
| --- | --- | --- |
| **Logger** | Lời gọi log từ code | Kiểm tra level và gửi sự kiện tới appender thích hợp |
| **ILoggingEvent** | Dữ liệu của lần ghi log | Giữ level, message, arguments, timestamp, logger, MDC, Throwable... |
| **Layout** | Logging event | Một **String** biểu diễn sự kiện |
| **Encoder** | Logging event, dùng layout/encoder logic | Chuỗi bytes để ghi ra OutputStream; xác định charset, header/footer nếu hỗ trợ |
| **Appender** | Logging event | Ghi sang đích như console/file/network và quản lý tài nguyên |
| **PatternLayout** | Logging event + pattern | Chuỗi tùy chỉnh theo các conversion word |
| **PatternLayoutEncoder** | Logging event | Sử dụng PatternLayout rồi mã hóa thành bytes |

**Điểm đặc biệt của Logback hiện đại:** khi cấu hình **ConsoleAppender**, **FileAppender** hay **RollingFileAppender**, bạn thường cung cấp một **Encoder**, không gắn thẳng PatternLayout làm đầu ra byte. **PatternLayoutEncoder** là cách thuận tiện và phổ biến nhất để sử dụng PatternLayout.

Dễ nhớ:
- **Layout trả String**: sự kiện được trình bày thế nào?
- **Encoder trả bytes**: chuỗi được mã hóa thế nào để xuất?
- **Appender ghi bytes/đẩy sự kiện đến đích**: log đi đâu?

Trong cấu hình XML, phần tử **encoder** chứa **pattern** không có nghĩa Layout đã biến mất; PatternLayoutEncoder đã bao bọc cơ chế PatternLayout. Có thể dùng **LayoutWrappingEncoder** khi cần bọc một Layout tùy chỉnh, nhưng đa số ứng dụng chỉ cần PatternLayoutEncoder.

## 3. Conversion pattern được đọc như thế nào?

PatternLayout xử lý các ký hiệu **%** là điểm bắt đầu một *conversion specifier*. Một specifier có thể có:
- **Format modifier**: độ rộng và căn chỉnh như **%-5level**.
- **Conversion word**: tên trường như **level**, **logger**, **thread**, **msg**.
- **Option trong dấu ngoặc nhọn**: ví dụ **%logger{36}** hoặc **%d{HH:mm:ss.SSS}**.
- **Literal text**: những ký tự khác được giữ nguyên, ví dụ dấu cách, ngoặc vuông, dấu hai chấm, dấu gạch nối.

Ví dụ:

~~~text
%d{HH:mm:ss.SSS} [%thread] %-5level %logger{36} - %msg%n
~~~

Ý nghĩa theo thứ tự: thời gian; tên thread trong ngoặc vuông; level căn trái tối thiểu năm ký tự; tên logger được rút gọn theo quy tắc; dấu phân tách; message; xuống dòng.

Không nên đọc các tên **logger**, **thread**, **msg** như field của một JSON object. Đây là **conversion word** của pattern; output cuối vẫn là text trừ khi encoder được thiết kế để tạo định dạng có cấu trúc.

### Các conversion word thông dụng

| Pattern | Vai trò | Lưu ý |
| --- | --- | --- |
| **%d{HH:mm:ss.SSS}** | Thời điểm sự kiện theo pattern | Nên nêu timezone khi hợp nhất log nhiều hệ thống |
| **%level** / **%p** | INFO, DEBUG, WARN, ERROR... | Logback Classic dùng tên level của Logback |
| **%-5level** | Level căn trái trong vùng tối thiểu 5 ký tự | INFO có khoảng trắng đệm, ERROR thì không |
| **%thread** / **%t** | Tên thread nơi sự kiện được tạo | Không phải requestId; thread pool tái sử dụng thread |
| **%logger** / **%c** | Tên logger đầy đủ | Giúp truy nguồn module hoặc class |
| **%logger{36}** | Tên logger rút gọn theo độ dài mong muốn | Không bảo đảm chuỗi dài đúng 36 ký tự trong mọi trường hợp |
| **%msg** / **%message** / **%m** | Message đã được định dạng | Dữ liệu từ arguments có thể xuất hiện ở đây |
| **%n** | Dấu xuống dòng của nền tảng | Nên dùng thay vì cố định một chuỗi newline |
| **%X{requestId}** | Giá trị requestId trong MDC | Nếu thiếu key, thường ra chuỗi rỗng |
| **%X{requestId:-none}** | Lấy requestId hoặc giá trị thay thế khi thiếu | Chú ý key chính xác và cách truyền MDC |
| **%ex{short}** | Phần đầu stack trace của Throwable | Không thay thế toàn bộ cause chain |
| **%ex{full}** | Toàn bộ stack trace theo cơ chế formatter | Dòng log có thể trở thành multiline |
| **%caller{1}** | Một mức thông tin caller | Tốn chi phí tìm stack; chỉ bật khi cần |

Ví dụ pattern rút gọn:

~~~text
%-5level [%thread] %logger{36} requestId=%X{requestId:-none} - %msg%n
~~~

Một record có thể trở thành:

~~~text
INFO  [main] c.e.checkout.OrderService requestId=req-42 - order.created orderId=OD-42
~~~

Đây là **minh họa**: độ dài/rút gọn tên logger và thread phụ thuộc record thực tế. Khi cần đầu ra cố định để test, nên loại timestamp, caller và việc rút gọn tên biến thiên.

### Format modifier và literal text

**%-5level** nghĩa là độ rộng **tối thiểu** năm ký tự, căn trái. **%5level** nghĩa là căn phải trong vùng tối thiểu năm ký tự. Đây không phải giới hạn tối đa hoặc đảm bảo cắt chuỗi.

Bạn có thể đặt chữ **level=**, **service=checkout**, ngoặc, dấu phân tách tùy ý vào pattern. Tuy nhiên, nếu đặt một chuỗi chữ ngay sát sau conversion word mà không có dấu phân tách, parser có thể hiểu nhầm thành tên converter dài hơn. Dùng dấu cách, ký tự phân tách hoặc cú pháp được tài liệu hóa để tránh lỗi như **%PARSER_ERROR[...]**.

Dấu **%** có ý nghĩa đặc biệt. Nếu thật sự cần ký hiệu phần trăm literal, phải escape theo quy tắc pattern của Logback; trong file XML còn phải phân biệt escaping của XML và escaping của pattern.

## 4. PatternLayout và PatternLayoutEncoder

**PatternLayout** thuộc Logback Classic và xử lý event để tạo String. **PatternLayoutEncoder** được thiết kế để sử dụng PatternLayout rồi chuyển kết quả thành bytes theo charset, ví dụ UTF-8.

Cấu hình console tiêu biểu:

~~~xml
<configuration>
  <appender name="CONSOLE" class="ch.qos.logback.core.ConsoleAppender">
    <encoder class="ch.qos.logback.classic.encoder.PatternLayoutEncoder">
      <charset>UTF-8</charset>
      <pattern>%level | requestId=%X{requestId} | %msg%n</pattern>
    </encoder>
  </appender>

  <root level="DEBUG">
    <appender-ref ref="CONSOLE"/>
  </root>
</configuration>
~~~

Các thẻ trong cấu hình có chức năng riêng:

1. **configuration** là phần tử gốc của cấu hình Logback.
2. **appender CONSOLE** ghi ra console; không cần FileAppender nếu chỉ muốn xem terminal.
3. **encoder** dùng PatternLayoutEncoder để tạo bytes. **charset UTF-8** giúp dữ liệu tiếng Việt có cách mã hóa rõ ràng.
4. **pattern** quy định dòng log. **%X{requestId}** lấy giá trị MDC nếu ứng dụng đã cung cấp.
5. **root level=DEBUG** cho phép DEBUG, INFO, WARN và ERROR theo thứ tự ngưỡng của Logback.
6. **appender-ref** nối appender với root logger.

Logback thường tìm file **logback-test.xml** hoặc **logback.xml** trên classpath, theo cơ chế cấu hình của nó. Trong Maven project thông thường, đặt **logback.xml** vào **src/main/resources** để resource này được đưa lên classpath khi chạy ứng dụng.

**Lưu ý:** Không nhầm tên file **logback.xml** của Logback với **logging.properties** của java.util.logging. Hai hệ thống có cú pháp và cách điều khiển khác nhau. Cũng không nhầm **Logger của SLF4J** với **java.util.logging.Logger**.

## 5. Thực hành Java 17: chương trình Logback có Layout rõ ràng

Thực hành này tạo ba dòng log với một **requestId** chung qua **MDC**. Pattern chỉ dùng các trường ổn định để dễ đối chiếu. Bạn cần JDK 17 trở lên, Maven và khả năng tải dependency từ Maven Central hoặc kho Maven của môi trường học.

### Cấu trúc dự án

~~~text
logback-layout-demo/
├── pom.xml
└── src/
    └── main/
        ├── java/
        │   └── com/
        │       └── example/
        │           └── logging/
        │               └── LayoutDemo.java
        └── resources/
            └── logback.xml
~~~

### File pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
  <modelVersion>4.0.0</modelVersion>
  <groupId>com.example</groupId>
  <artifactId>logback-layout-demo</artifactId>
  <version>1.0-SNAPSHOT</version>

  <properties>
    <maven.compiler.release>17</maven.compiler.release>
    <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
  </properties>

  <dependencies>
    <dependency>
      <groupId>ch.qos.logback</groupId>
      <artifactId>logback-classic</artifactId>
      <version>1.5.18</version>
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
        <version>3.3.0</version>
      </plugin>
    </plugins>
  </build>
</project>
~~~

Ví dụ cố định **Logback Classic 1.5.18** để các bước được thống nhất; đây là phiên bản dùng trong bài học, không phải tuyên bố về bản mới nhất. Logback Classic kéo theo các dependency phù hợp, trong đó có API SLF4J. Trong dự án thực, hãy tuân theo BOM/quản lý phiên bản và quy định bảo mật của dự án, tránh khai báo nhiều provider SLF4J cùng lúc.

### File src/main/resources/logback.xml

~~~xml
<configuration>
  <appender name="CONSOLE" class="ch.qos.logback.core.ConsoleAppender">
    <encoder class="ch.qos.logback.classic.encoder.PatternLayoutEncoder">
      <charset>UTF-8</charset>
      <pattern>%level | requestId=%X{requestId} | %msg%n</pattern>
    </encoder>
  </appender>

  <root level="DEBUG">
    <appender-ref ref="CONSOLE"/>
  </root>
</configuration>
~~~

### File src/main/java/com/example/logging/LayoutDemo.java

~~~java
package com.example.logging;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.slf4j.MDC;

public class LayoutDemo {
    private static final Logger LOG =
            LoggerFactory.getLogger(LayoutDemo.class);

    public static void main(String[] args) {
        MDC.put("requestId", "req-42");
        try {
            LOG.info("order.created orderId={} items={}", "OD-42", 2);
            LOG.debug("cache.lookup result={}", "miss");
            LOG.warn("payment.retry attempt={}", 2);
        } finally {
            MDC.remove("requestId");
        }
    }
}
~~~

### Biên dịch và chạy

Tại thư mục chứa **pom.xml**, dùng:

~~~bash
mvn -q compile exec:java -Dexec.mainClass=com.example.logging.LayoutDemo
~~~

Các dòng log từ chương trình có nội dung **chính xác** như sau (không tính bất kỳ thông báo riêng của Maven hoặc môi trường):

~~~text
INFO | requestId=req-42 | order.created orderId=OD-42 items=2
DEBUG | requestId=req-42 | cache.lookup result=miss
WARN | requestId=req-42 | payment.retry attempt=2
~~~

Giải thích:

- **LoggerFactory.getLogger(LayoutDemo.class)** lấy logger SLF4J cho lớp. Backend Logback xử lý sự kiện khi được gắn làm provider.
- **MDC.put(...)** gắn requestId với ngữ cảnh logging hiện tại. **%X{requestId}** làm cho mỗi dòng được in ra với cùng giá trị req-42.
- **LOG.info(..., arguments)** và **LOG.debug(...)** dùng placeholder **{} của SLF4J**, được thay theo thứ tự tham số; đây **không phải** cú pháp **{0}, {1}** của java.util.logging.
- **root DEBUG** cho phép DEBUG được xuất. Nếu đổi root thành INFO và không có logger con override, dòng DEBUG sẽ bị loại; hai dòng INFO/WARN vẫn xuất.
- **%level** không thêm padding nên đầu ra có INFO, DEBUG, WARN đúng như ví dụ. **%msg** lấy message đã định dạng; **%n** xuống dòng.
- **finally** gọi **MDC.remove** để không giữ requestId sau khi xử lý. Trong ứng dụng thật có thread pool, việc dọn context còn quan trọng hơn vì thread được tái sử dụng.

Chương trình **không cố ý ném exception** và không có timestamp trong pattern, nên các dòng của bài thực hành không phụ thuộc vào ngày/giờ chạy. Dữ liệu thực tế của Maven hoặc cảnh báo nếu môi trường cấu hình sai không được xem là nội dung output cố định của demo.

## 6. Thiết kế pattern cho môi trường phát triển và vận hành

**Local/development** thường ưu tiên ngắn, dễ đọc và có thông tin quan trọng để debug:

~~~text
%-5level [%thread] %logger{36} requestId=%X{requestId:-none} - %msg%n
~~~

Định dạng này cho thấy level, thread, logger, requestId nếu có và message. Không nhất thiết phải in từng thuộc tính của event khi đọc trong IDE.

**File hoặc backend thu thập nhiều service** cần timestamp rõ ràng, identity của service và correlation ID. Pattern minh họa:

~~~text
%d{yyyy-MM-dd'T'HH:mm:ss.SSS,UTC} %-5level [%thread] %logger{36} traceId=%X{traceId:-none} - %msg%n
~~~

Thông tin cần cân nhắc:

- **Timestamp:** có timezone rõ ràng khi ghép nhiều máy. Với quy ước UTC, có thể đặt timezone trong option của %d. Không mặc định mọi đồng hồ hệ thống đã đồng bộ hoàn hảo.
- **Logger:** tên logger giúp định vị code; độ dài rút gọn vừa đủ để giảm tràn màn hình nhưng vẫn phân biệt các lớp.
- **Level:** hỗ trợ tìm bất thường, nhưng INFO có thể chứa một event hoàn thành HTTP 503; mức level không thay thế việc kiểm tra kết quả nghiệp vụ.
- **Thread:** giúp debug đồng thời, nhưng thread pool có thể dùng lại thread nên cần requestId/traceId để liên kết theo request.
- **MDC:** cung cấp requestId, traceId hoặc tenant ID đã được phép ghi; thiếu context phải xử lý rõ ràng.
- **Message:** nên có event name và giá trị có đơn vị như durationMs, attempt, items; đừng dump nguyên request object.
- **Exception:** cần bảo toàn ngữ cảnh và Throwable khi thực sự cần điều tra.
- **Charset:** dùng UTF-8 để tránh ký tự bị sai khi chuyển bytes, gửi qua collector hoặc đọc tại hệ điều hành khác.

**Layout dạng text chỉ là một phương án.** Nếu hệ thống cần lọc chính xác theo trường, tính tổng hợp và correlation bằng JSON, một **JSON encoder có cấu trúc** thích hợp hơn việc ghép JSON thủ công bằng PatternLayout. Pattern text chứa dấu phân tách trong dữ liệu người dùng có thể khiến parser tách sai; với JSON encoder, các trường phải được escape và serialize đúng kiểu.

## 7. MDC trong Layout: đưa requestId/traceId vào mọi dòng

**MDC (Mapped Diagnostic Context)** cho phép gắn dữ liệu ngữ cảnh theo execution context của logging để pattern có thể lấy ra bằng **%X{key}**. Với Logback Classic, MDC thường gắn với thread; không nên giả định nó tự đi theo mọi công việc bất đồng bộ.

Ví dụ:

~~~java
// Đoạn minh họa; LOG là SLF4J Logger đã khai báo.
MDC.put("requestId", "req-92");
try {
    LOG.info("event=payment.started");
    LOG.info("event=payment.completed status=success");
} finally {
    MDC.remove("requestId");
}
~~~

Nếu pattern chứa **requestId=%X{requestId}**, cả hai dòng có thể hiển thị cùng requestId. Nếu key không có, **%X{requestId}** in chuỗi rỗng; muốn có thông báo thay thế, dùng **%X{requestId:-none}** theo cú pháp Logback.

Không nên ghi tràn lan toàn bộ MDC khi nó có thể chứa các field nội bộ/nhạy cảm. Thay vì dùng converter không chọn key, hãy liệt kê những key được phép và có giá trị chẩn đoán.

**Cẩn thận với thread pool và async:** khi tác vụ A đặt requestId rồi không xóa, tác vụ B chạy lại trên cùng thread có thể đọc nhầm context. Nếu công việc đi sang Executor/CompletableFuture/message consumer, phải truyền context theo cơ chế của dự án và dọn sau khi kết thúc. MDC không tự đảm bảo truyền đúng ở mọi thread, và một pattern đẹp không thể sửa dữ liệu ngữ cảnh vốn đã sai.

## 8. Exception và stack trace: tránh hiểu nhầm một dòng là một record

Khi gọi:

~~~java
// Minh họa; giả sử LOG và Throwable ex đã tồn tại.
LOG.error("payment.failed orderId={}", "OD-42", ex);
~~~

Logback có thể gắn Throwable proxy vào sự kiện. Khi PatternLayout có conversion word xử lý exception, chẳng hạn **%ex{short}** hoặc **%ex{full}**, layout có thể thêm stack trace theo cấu hình.

Ví dụ pattern có chủ đích:

~~~text
%level %logger{36} - %msg%n%ex{full}
~~~

Với Throwable, một event có thể tạo **nhiều dòng text**. Đừng đếm mỗi dòng stack trace thành một sự kiện độc lập khi phân tích. Nếu hệ thống thu thập theo từng dòng, cần cấu hình multiline hoặc tốt hơn là sử dụng encoder có cấu trúc cho trường exception.

**Chi tiết dễ bỏ qua:** trong Logback PatternLayout, nếu pattern không chứa conversion word xử lý Throwable, Logback Classic thường tự thêm cơ chế xuất stack trace để không làm mất thông tin lỗi. Vì vậy, chỉ viết **%msg%n** không phải cách đảm bảo exception sẽ bị ẩn. Conversion word **%nopex** có thể tắt phần xuất exception tự động, nhưng không nên dùng để che lỗi chỉ vì log dài; ưu tiên điều chỉnh chính sách và nơi ghi log.

**Thông tin caller** như **%class**, **%method**, **%file**, **%line** hoặc **%caller{1}** có thể hữu ích khi điều tra một điểm gọi khó tìm. Tuy nhiên, việc thu caller data có thể cần phân tích stack và **tốn chi phí**. Chỉ thêm khi có ích, nhất là trong hệ thống tải cao. Đừng nhầm **%logger** (tên logger) với **%class** (caller class).

## 9. Layout trong FileAppender và RollingFileAppender

FileAppender vẫn dùng Encoder như console. Một cấu hình riêng cho file:

~~~xml
<configuration>
  <appender name="FILE" class="ch.qos.logback.core.FileAppender">
    <file>application.log</file>
    <append>true</append>
    <encoder class="ch.qos.logback.classic.encoder.PatternLayoutEncoder">
      <charset>UTF-8</charset>
      <pattern>%d{yyyy-MM-dd HH:mm:ss.SSS,UTC} %-5level %logger{36} - %msg%n</pattern>
    </encoder>
  </appender>

  <root level="INFO">
    <appender-ref ref="FILE"/>
  </root>
</configuration>
~~~

Đây là **cấu hình thay thế độc lập** cho file log, không dán cùng lúc vào file ví dụ console mà không chủ động ghép các phần tử. Ứng dụng phải có quyền ghi tại thư mục đang chạy. Khi dùng FileAppender hoặc RollingFileAppender, **Encoder quyết định nội dung bytes của mỗi record**, còn **Appender/rolling policy** quyết định file, rotation và cách quản lý dữ liệu.

**RollingFileAppender** bổ sung khả năng chuyển file theo thời gian hoặc kích thước, tùy rolling policy. Những thông số như fileNamePattern của rolling policy phục vụ **đặt tên file archive**, khác với pattern của **PatternLayout** phục vụ **nội dung record**. Đừng nhầm hai loại pattern khi sửa cấu hình.

Trong production, còn phải xét quyền đọc file, retention, backup, dung lượng ổ đĩa, rủi ro log bị giữ quá lâu và cơ chế thu thập/ingestion. Đẹp trên console không có nghĩa định dạng đã phù hợp backend.

## 10. Tùy biến Layout và conversion word

**PatternLayout** cho phép thay đổi thứ tự các field, thêm literal text, độ rộng và formatter mà không cần tự viết code Java. Phần lớn bài toán trình bày log text nên bắt đầu bằng cách chỉnh pattern.

Với yêu cầu riêng, Logback hỗ trợ **custom converter** để tính giá trị mới từ ILoggingEvent rồi dùng conversion word riêng trong pattern. Cách này thường gọn hơn việc thay toàn bộ Layout chỉ để thêm một trường. Tuy nhiên, cần đăng ký converter trong cấu hình và quản lý tương thích phiên bản.

Nếu định dạng hoàn toàn khác (ví dụ giao thức nhị phân hoặc JSON có schema), cần xem xét **Encoder phù hợp** hơn là tự ghép chuỗi JSON trong PatternLayout. LayoutWrappingEncoder có thể dùng để tích hợp một Layout đặc biệt khi Appender yêu cầu Encoder.

Một số converter bổ trợ:
- **%highlight(...)** dùng màu theo level, hữu ích trong terminal có hỗ trợ ANSI; không nên mặc định mọi file/collector hiểu mã màu.
- **%replace(...)** có thể thay một phần message theo regex để trình bày hoặc che dữ liệu; cần kiểm soát chi phí và không coi regex là biện pháp bảo mật hoàn chỉnh.
- **%caller{1}** giúp truy điểm gọi nhưng tốn tài nguyên hơn các trường có sẵn như %logger.
- **%X{key:-default}** giúp đặt giá trị fallback khi MDC thiếu key, tránh hàng loạt chuỗi rỗng khó phân tích.

Nếu pattern in lại thông tin nhiều lần, ví dụ vừa ghi requestId trong MDC vừa nối requestId trong message, hãy cân nhắc chọn một quy ước nhất quán để tránh trùng dữ liệu và tăng chi phí lưu trữ.

## 11. Những lỗi phổ biến khi cấu hình Layout

| Hiện tượng | Nguyên nhân thường gặp | Hướng kiểm tra/sửa |
| --- | --- | --- |
| Có log nhưng không đúng định dạng | Chạy sai logback.xml hoặc config bị framework thay thế | Xác nhận file cấu hình được nạp và appender/encoder đang hoạt động |
| Chỉ hiện %PARSER_ERROR[...] | Conversion word không hợp lệ, text nối sát converter, cú pháp pattern sai | Kiểm tra pattern và escape, tham khảo conversion words được hỗ trợ |
| Không thấy requestId | MDC chưa đặt, sai key hoặc context không được truyền qua async | Kiểm tra MDC.put, key và vòng đời xử lý |
| INFO hiển thị nhưng DEBUG không thấy | Root/logger level đang INFO | Kiểm tra effective level; Layout không tự bật DEBUG |
| Exception in thành nhiều dòng | Stack trace được formatter xuất ra | Dùng multiline parsing hoặc structured encoder, không đếm mỗi dòng là event |
| Không có stack trace | Throwable chưa được truyền, custom encoder/formatter loại nó | Kiểm tra lời gọi LOG.error có Throwable và converter phù hợp |
| Log thành dòng dài khó đọc | In quá nhiều field hoặc object lớn | Chọn field quan trọng, giới hạn kích thước và dùng structured logging khi cần |
| Log trùng | Appender được gắn ở logger con và parent, additivity chưa phù hợp | Kiểm tra cấu hình logger và appender-ref; không chỉ sửa pattern |
| File có ký tự tiếng Việt lỗi | Charset/đầu đọc file không khớp | Cấu hình UTF-8 và kiểm tra charset ở mọi bước |
| Mã màu xuất ra file thô | Dùng converter màu cho đầu ra không hỗ trợ ANSI | Giữ pattern màu cho terminal, pattern text sạch cho file |
| Dòng log không có timezone | Pattern date không chỉ rõ zone hoặc dữ liệu nhiều máy bị trộn | Dùng quy ước UTC/zone rõ ràng và xác nhận clock |
| Thống kê sai do regex/split | Message chứa delimiter, dấu cách, newline | Dùng schema và encoder/parser có cấu trúc |

**Bảo mật:** Pattern chỉ là cách hiển thị; nó không bảo đảm dữ liệu đầu vào an toàn. Không đưa password, token, API key, cookie, thông tin thanh toán hoặc payload riêng tư vào MDC/message. Dữ liệu không tin cậy có thể chứa newline hoặc control characters gây **log injection**. Việc dùng %replace có thể hỗ trợ masking nhưng không thay được chính sách lọc/ẩn dữ liệu từ nguồn.

**Hiệu năng:** Timestamp, level, logger và message cơ bản thường rẻ hơn lấy caller stack. Regex replace và formatter phức tạp có thể tăng chi phí CPU; xuất quá nhiều log vẫn gây I/O, disk và ingestion costs. Chọn pattern theo nhu cầu người đọc và lưu trữ, thay vì thêm tất cả converter có sẵn.

## 12. Quy trình thiết kế và kiểm tra Layout

Khi tạo một pattern mới, làm theo các bước:

1. **Xác định nơi đọc**: terminal của developer, file trên host, công cụ tập trung hay pipeline audit. Mỗi nơi có nhu cầu khác nhau.
2. **Xác định trường bắt buộc**: timestamp có timezone, level, service/logger, event, requestId/traceId, message; chọn tối thiểu nhưng đủ trả lời câu hỏi.
3. **Xác nhận nguồn của từng trường**: level/logger có sẵn trong event; requestId từ MDC cần code hoặc framework đưa vào.
4. **Chọn Encoder**: PatternLayoutEncoder cho text theo pattern; encoder có cấu trúc nếu cần JSON thật sự.
5. **Viết pattern nhỏ trước**: level, MDC, message và newline. Chạy một ca có output dễ đoán trước khi thêm timestamp hoặc caller.
6. **Kiểm tra level**: cùng một pattern, DEBUG có bị loại khi logger/root INFO không? Layout không thể phục hồi record đã bị lọc.
7. **Kiểm tra thiếu MDC**: khi không đặt requestId, chọn default và xác nhận parser/back-end hiểu được.
8. **Kiểm tra Throwable**: xem stack trace được hiển thị thế nào, có multiline không, và collector đang tách record theo quy tắc nào.
9. **Kiểm tra charset và nhiều môi trường**: tiếng Việt, Windows/Linux newline, timezone, ANSI color, rolling file.
10. **Kiểm tra chi phí và dữ liệu nhạy cảm**: tránh caller data và regex nặng nếu không có giá trị; không xuất secrets hay dữ liệu cá nhân.
11. **Ghi lại quy ước schema**: nếu tên field cần truy vấn dài hạn, thay đổi pattern phải được phối hợp với dashboard/parser/alert phụ thuộc.
12. **Tái kiểm tra sau thay đổi**: một ca bình thường, một ca lỗi, một ca không có MDC; tránh log trùng/mất ở nhiều appender.

## 13. Câu hỏi tự kiểm tra

**Câu 1.** PatternLayout và PatternLayoutEncoder khác nhau ở đâu?

**Đáp án:** PatternLayout biến một logging event thành String. PatternLayoutEncoder dùng PatternLayout để tạo nội dung rồi mã hóa thành bytes cho appender ghi ra stream/file.

**Câu 2.** Có thể đặt pattern %msg%n trực tiếp dưới mọi FileAppender thay cho encoder không?

**Đáp án:** Không nên. Với Logback hiện đại, appender kiểu file/console thường yêu cầu Encoder; dùng PatternLayoutEncoder và khai báo pattern trong encoder.

**Câu 3.** Vì sao %X{requestId} có lúc trống?

**Đáp án:** MDC không có key requestId tại execution context của record, key khác tên, hoặc context không được truyền đúng qua thread/async. Có thể dùng %X{requestId:-none} để hiện fallback, đồng thời sửa nguồn cấp MDC nếu thiếu ngoài ý muốn.

**Câu 4.** Đổi pattern có giúp record DEBUG xuất ra khi effective level đang INFO không?

**Đáp án:** Không. Logger/filter quyết định record nào được chấp nhận trước khi Layout trình bày.

**Câu 5.** Vì sao %caller có thể gây chậm?

**Đáp án:** Nó phải thu thông tin vị trí lời gọi từ stack, chi phí cao hơn việc lấy những field đã có trong event. Chỉ bật khi cần.

**Câu 6.** Nếu một Throwable tạo năm dòng stack trace, có phải năm logging event?

**Đáp án:** Không. Một event có thể được trình bày trên nhiều dòng. Parser/collector cần nhận diện đúng ranh giới record.

**Câu 7.** Muốn backend tìm durationMs theo kiểu số, có nên ghép một chuỗi JSON bằng PatternLayout rồi cho rằng đã an toàn?

**Đáp án:** Không. Khi cần JSON có schema và kiểu dữ liệu, dùng encoder có cấu trúc với escaping/serialization đúng; nối thủ công dễ sai khi message chứa ký tự đặc biệt.

**Câu 8.** Vì sao log có thể bị trùng dù pattern chỉ có một %msg?

**Đáp án:** Logger có thể chuyển cùng event tới nhiều appender, kể cả appender ở logger cha nếu additivity được bật. Trùng record không nhất thiết do Layout.

## 14. Nguồn tham khảo kỹ thuật

- [Logback Manual — Layouts](https://logback.qos.ch/manual/layouts.html): PatternLayout, conversion words, MDC, Throwable, custom converters.
- [Logback Manual — Encoders](https://logback.qos.ch/manual/encoders.html): ranh giới Layout/Encoder và PatternLayoutEncoder.
- [Logback Manual — Configuration](https://logback.qos.ch/manual/configuration.html): cấu hình logback.xml, appender, encoder và root logger.
- [Logback Manual — MDC](https://logback.qos.ch/manual/mdc.html): sử dụng ngữ cảnh và conversion word %X.

**Ghi nhớ:** **Layout quyết định logging event được trình bày như thế nào; Encoder chuyển biểu diễn thành bytes; Appender quyết định đích xuất.** Với Logback Classic, PatternLayoutEncoder là lựa chọn phổ biến cho text log. Một pattern tốt cần vừa đủ thông tin để truy vết, tương thích với parser/collector, dễ điều tra lỗi và không làm lộ dữ liệu hay tăng chi phí một cách không cần thiết.
