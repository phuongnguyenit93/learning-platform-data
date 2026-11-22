# Field logger trong JSON logging: tên nguồn phát log và cách dùng đúng

## Mục tiêu học tập

Trong JSON logging, một record thường có các trường như **timestamp**, **level**, **message**, **logger**, **thread**, **service.name** và **traceId**. Trong số đó, **field logger** cho biết **tên logger được sử dụng để phát sự kiện**. Đây là trường quan trọng khi muốn tìm log theo package, class, module hoặc nhóm chức năng thay vì chỉ tìm theo từ khóa trong message.

Bài này thuộc nhóm **JSON logging** trong **Java Core Logging** và tập trung trực tiếp vào **“Field logger”**. Sau bài, bạn có thể:

- Giải thích chính xác ý nghĩa, nguồn gốc và kiểu dữ liệu của field **logger**.
- Phân biệt **logger name** với class thực sự gọi lệnh log, thread, service, level, message, MDC và đường dẫn file log.
- Biết cách tạo tên logger bằng **SLF4J**, **Logback**, **java.util.logging (JUL)** và cách tên đó đi vào JSON encoder/formatter.
- Hiểu vì sao backend có thể xuất trường dưới tên **logger**, **logger_name** hoặc **log.logger**, và cách chuẩn hóa schema khi ingest.
- Chạy hai ví dụ **Java 17+**: một ví dụ JUL chỉ dùng JDK với JSON Formatter minh họa; một ví dụ SLF4J + Logback + JSON encoder thực tế, có Maven và đọc lại JSON bằng Jackson.
- Kiểm tra trường logger bằng parser thay vì chỉ tìm chuỗi, xử lý trường thiếu/đổi tên/sai kiểu, tránh đụng độ với MDC và nguy cơ dữ liệu không tin cậy.
- Thiết kế một quy ước logger name ổn định, dễ truy vấn, có độ phân biệt hợp lý trong hệ thống nhiều service.

**Lưu ý thuật ngữ:** “field logger” trong bài này là **trường logger bên trong một JSON log event**. Nó không đồng nghĩa với **biến thành viên Java** thường được khai báo là **private static final Logger LOG**, mặc dù biến LOG là đối tượng tạo ra tên logger xuất hiện trong sự kiện.

## 1. Field logger là gì?

Ví dụ một log event JSON:

~~~json
{
  "@timestamp": "2026-11-09T13:20:30.123Z",
  "level": "INFO",
  "logger": "com.example.checkout.OrderService",
  "thread": "http-worker-4",
  "message": "event=order.created orderId=OD-42",
  "requestId": "req-17"
}
~~~

Trong sự kiện này:

- **logger** là một JSON string, có giá trị **com.example.checkout.OrderService**.
- Nó chỉ **định danh logger** mà code dùng để phát sự kiện.
- **level** cho biết mức độ của record (INFO).
- **message** mô tả sự kiện, không phải nguồn logger.
- **thread** cho biết tên thread liên quan tới sự kiện.
- **requestId** là thông tin ngữ cảnh của một request, thường lấy từ MDC hoặc cơ chế correlation.
- **@timestamp** là thời gian sự kiện theo quy ước encoder/backend.

JSON phía trên là **ví dụ schema minh họa**, không phải output mặc định cố định của mọi Java logger. Trong một số backend, tên trường thực tế là **logger_name**; trong một số schema, nó nằm trong object **log** dưới tên **log.logger**.

Điểm cốt lõi:

**Field logger = tên định danh của đối tượng logger dùng để ghi sự kiện; không phải tên file log, không phải thông điệp và cũng không mặc nhiên là tên class đang thực sự thực thi.**

Tại sao cần tên này? Khi hàng triệu dòng log từ nhiều package được gửi về một hệ thống tập trung, bạn có thể lọc:

~~~text
Tất cả record phát từ com.example.checkout.OrderService
Tất cả record thuộc nhánh com.example.checkout
Tất cả ERROR của com.example.payment.PaymentClient
~~~

Tên logger giúp **khoanh vùng code/module** liên quan trước khi đọc message và stack trace.

## 2. Tên logger được tạo ở đâu?

Tùy API logging, mã Java có thể lấy logger **theo lớp** hoặc **theo chuỗi tên**.

### SLF4J: lấy logger theo Class

~~~java
// Minh họa trong lớp com.example.checkout.OrderService.
private static final org.slf4j.Logger LOG =
        org.slf4j.LoggerFactory.getLogger(OrderService.class);
~~~

Trong SLF4J, **LoggerFactory.getLogger(Class)** tạo/lấy logger mang tên tương ứng **Class.getName()**. Nếu lớp là **com.example.checkout.OrderService**, tên logger thông dụng cũng là:

~~~text
com.example.checkout.OrderService
~~~

Vì vậy JSON encoder có thể ghi:

~~~json
{"logger":"com.example.checkout.OrderService"}
~~~

### SLF4J: lấy logger theo tên tùy chỉnh

~~~java
// Minh họa; LOG thuộc kiểu org.slf4j.Logger.
org.slf4j.Logger LOG =
        org.slf4j.LoggerFactory.getLogger("checkout.workflow");
~~~

Khi đó trường logger có thể là:

~~~json
{"logger":"checkout.workflow"}
~~~

**Đây là tên tùy chỉnh, không phải tên Java class.** Đừng xây dựng một parser cố gắng chuyển mọi giá trị logger thành class loadable. Tên logger có thể là một category, package, subsystem hoặc tên do framework quản lý.

### JUL: lấy logger theo tên

~~~java
// Minh họa; API java.util.logging có sẵn trong JDK.
java.util.logging.Logger LOG =
        java.util.logging.Logger.getLogger("com.example.checkout.OrderService");
~~~

Khi JUL tạo **LogRecord**, record có thể có **getLoggerName()** là tên tương ứng. Một Formatter tùy chỉnh hoặc JSON encoder cho JUL có thể đọc thông tin đó để tạo trường JSON.

### Log4j 2: cùng nguyên tắc về tên

Trong Log4j 2, cách lấy logger theo Class hoặc tên cũng cung cấp một **logger name** để backend xử lý và JSON serializer có thể xuất. Nhưng tên property, cấu hình encoder/layout và hành vi serialization là chi tiết riêng của implementation. Không đem file **logback.xml** sang Log4j 2 và giả định nó tự hiểu cùng cấu hình.

**Quy tắc thực hành:** mã nghiệp vụ nên dùng tên logger ổn định theo class hoặc module, còn backend/encoder chịu trách nhiệm xuất tên đó dưới key của schema đã được chọn.

## 3. Logger field khác những field khác như thế nào?

| Field | Giá trị ví dụ | Trả lời câu hỏi | Không nên nhầm với |
| --- | --- | --- | --- |
| **logger** | com.example.checkout.OrderService | Logger nào phát sự kiện? | Tên file hoặc source code line |
| **logger_name** | com.example.checkout.OrderService | Cùng ý nghĩa theo schema khác | Một logger khác |
| **log.logger** | com.example.checkout.OrderService | Logger name trong ECS | Chuỗi literal có dấu chấm trong mọi kiểu JSON |
| **level** | INFO | Mức severity nào? | Tên logger |
| **message** | event=order.created orderId=OD-42 | Chuyện gì được ghi nhận? | Tên logger hoặc dữ liệu có cấu trúc mặc định |
| **thread** | http-worker-4 | Thread nào tạo record? | Request ID hoặc logger |
| **service.name** | checkout-api | Dịch vụ nào chạy code? | Logger name |
| **traceId** | 2d3d... | Trace phân tán nào? | Logger name |
| **requestId** | req-17 | Request cụ thể nào? | Logger name |
| **class** hoặc **caller_class** | com.example.infrastructure.LoggingHelper | Caller thực tế được backend suy ra | Logger name nếu dùng tên custom |
| **file** / **log.file.path** | /var/log/app.jsonl | File nào lưu/thu thập record? | Logger name |
| **exception** | NumberFormatException | Lỗi nào đi kèm event? | Logger name |

Có một bẫy quan trọng: **logger name và caller class có thể giống nhau, nhưng không phải cùng một dữ liệu**.

Nếu class **PaymentService** gọi một helper dùng logger có tên **checkout.workflow**, JSON có thể có:

~~~json
{
  "logger": "checkout.workflow",
  "message": "event=payment.authorized"
}
~~~

Đừng suy ra Java source file đang thực thi là **checkout.workflow.java**. Đây chỉ là category do lập trình viên đặt.

**Tên logger cũng không phải ID của một instance object.** Một logger thường được giữ trong biến static final và dùng lại qua rất nhiều request. Hai sự kiện mang cùng logger có thể thuộc hai người dùng, hai thread hoặc hai giao dịch hoàn toàn khác nhau.

## 4. Logger field trong một pipeline JSON

Một pipeline khái niệm với SLF4J và Logback:

~~~mermaid
flowchart LR
    A["Code Java: LOG.info"] --> B["SLF4J API"]
    B --> C["Logback LoggingEvent"]
    C --> D["JSON encoder"]
    D --> E["JSON có logger/level/message"]
    E --> F["Console hoặc file"]
    F --> G["Collector / Search backend"]
~~~

Từng bước:

1. Code lấy Logger qua **LoggerFactory.getLogger(...)** và phát event.
2. SLF4J đưa yêu cầu đến provider/backend tương thích.
3. Logback nhận sự kiện với **logger name**, level, message, thời gian và các metadata khác.
4. JSON encoder chọn trường nào đưa vào JSON, dùng key gì và cách escape dữ liệu.
5. Appender ghi các bytes JSON ra file, stdout hoặc đích khác.
6. Collector hoặc ingest pipeline parse/index những trường đó.

Trong quá trình này, **tên logger** thường đã có ở logging event. Encoder **không cần suy đoán bằng regex trên message**. Nếu JSON đầu ra thiếu logger, nguyên nhân có thể là **encoder không xuất trường này, schema đã đổi tên, field bị loại, hoặc collector đã biến đổi/đánh rơi**; không nhất thiết code chưa tạo logger.

### Logger name và additivity/level

Trong nhiều framework, tên logger theo package/class cũng là **cơ sở áp level theo namespace**. Ví dụ bật DEBUG cho package checkout nhưng giữ root INFO.

Tuy nhiên, **field logger ở JSON chỉ là dữ liệu được xuất**. Nó không tự quyết định record nào được phát. Mức log, filter, appender và backend configuration đã tác động trước hoặc trong quá trình ghi. Bật/tắt field logger trong JSON **không đồng nghĩa** bật/tắt logging cho package đó.

## 5. Tên field: logger, logger_name và log.logger

Một lỗi tích hợp thường gặp là các service cùng ghi một ý nghĩa nhưng dùng các key khác nhau:

~~~json
{"logger":"com.example.checkout.OrderService","message":"event=order.created"}
~~~

~~~json
{"logger_name":"com.example.checkout.OrderService","message":"event=order.created"}
~~~

~~~json
{"log":{"logger":"com.example.checkout.OrderService"},"message":"event=order.created"}
~~~

Về mặt ý nghĩa, cả ba đều có thể chứa **logger name**. Nhưng JSON schema và truy vấn của chúng **khác nhau**. Không thể dùng cùng đường truy cập **.logger** để lấy hết cả ba khi parser không chuẩn hóa.

- **logger**: key top-level do team chọn, dùng trong ví dụ bài này.
- **logger_name**: key mặc định của **LogstashEncoder** thuộc thư viện logstash-logback-encoder cho Logback.
- **log.logger**: field được mô tả trong **Elastic Common Schema (ECS)**. Khi biểu diễn thành nested JSON, bạn có thể thấy **{"log":{"logger":"..."}}**; tùy ingest pipeline, cách map key dotted và nested cần được xác định cụ thể.

**Không có quy tắc mọi hệ Java JSON logging bắt buộc dùng đúng chữ logger.** Một hệ thống có thể tuân ECS hoặc một schema nội bộ. Quan trọng là **thống nhất key, kiểu dữ liệu và cách mapping trước khi dựa vào dashboard/alert**.

### Schema đề xuất cho ứng dụng nhỏ

~~~json
{
  "@timestamp": "2026-11-09T13:20:30.123Z",
  "level": "INFO",
  "logger": "com.example.checkout.OrderService",
  "service": "checkout-api",
  "message": "event=order.created orderId=OD-42",
  "requestId": "req-17"
}
~~~

**Đây là schema minh họa do đội ngũ lựa chọn**, không phải cấu trúc cố định của SLF4J. Nếu đơn vị dùng ECS, nên ưu tiên các field chuẩn như **log.logger**, **log.level** và **service.name** theo cách encoder/ingest đã hỗ trợ. Tránh cố xuất đồng thời **logger**, **logger_name**, **log.logger** chỉ để “cho chắc”: dữ liệu trùng có thể làm dashboard phức tạp và tăng chi phí.

## 6. Thực hành 1 — Java 17, JUL và JSON field logger

Ví dụ đầu tiên chỉ cần JDK 17. Nó sử dụng **java.util.logging.Logger** và **LogRecord.getLoggerName()**, gắn một **StreamHandler** tới buffer trong bộ nhớ và một Formatter tùy chỉnh để hiện ba field: logger, level, message.

**Cảnh báo phạm vi:** Formatter này là **mô hình học tập** cho thấy logger name đến từ LogRecord như thế nào. Nó có hàm escape cho JSON string thông thường; **không nên tự xây serializer JSON production** khi đã có Jackson hoặc JSON encoder chính thức. Một serializer tổng quát còn cần xử lý mọi loại dữ liệu, Unicode lỗi, arrays/objects, cấu trúc exception và schema nhất quán.

Tạo tệp **LoggerFieldDemo.java**:

~~~java
import java.io.ByteArrayOutputStream;
import java.nio.charset.StandardCharsets;
import java.util.logging.Formatter;
import java.util.logging.Level;
import java.util.logging.LogRecord;
import java.util.logging.Logger;
import java.util.logging.StreamHandler;

public class LoggerFieldDemo {
    private static final Logger LOG =
            Logger.getLogger("com.example.checkout.OrderService");

    private static String jsonString(String source) {
        StringBuilder result = new StringBuilder("\"");
        for (int i = 0; i < source.length(); i++) {
            char c = source.charAt(i);
            switch (c) {
                case '"' -> result.append("\\\"");
                case '\\' -> result.append("\\\\");
                case '\n' -> result.append("\\n");
                case '\r' -> result.append("\\r");
                case '\t' -> result.append("\\t");
                default -> {
                    if (c < 0x20) {
                        result.append(String.format("\\u%04x", (int) c));
                    } else {
                        result.append(c);
                    }
                }
            }
        }
        return result.append('"').toString();
    }

    public static void main(String[] args) throws Exception {
        ByteArrayOutputStream buffer = new ByteArrayOutputStream();
        StreamHandler handler = new StreamHandler(buffer, new Formatter() {
            @Override
            public String format(LogRecord record) {
                return "{\"logger\":" + jsonString(record.getLoggerName())
                        + ",\"level\":" + jsonString(record.getLevel().getName())
                        + ",\"message\":" + jsonString(formatMessage(record))
                        + "}\n";
            }
        });
        handler.setEncoding(StandardCharsets.UTF_8.name());
        handler.setLevel(Level.INFO);

        LOG.setUseParentHandlers(false);
        LOG.setLevel(Level.INFO);
        LOG.addHandler(handler);
        try {
            LOG.log(Level.INFO, "event=order.created orderId={0}", "OD-42");
            LOG.warning("event=payment.retry attempt=2");
        } finally {
            LOG.removeHandler(handler);
            handler.close();
        }

        System.out.print(buffer.toString(StandardCharsets.UTF_8));
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac LoggerFieldDemo.java
java LoggerFieldDemo
~~~

**Stdout chính xác của chương trình đã chạy thử trên JDK 17+:**

~~~json
{"logger":"com.example.checkout.OrderService","level":"INFO","message":"event=order.created orderId=OD-42"}
{"logger":"com.example.checkout.OrderService","level":"WARNING","message":"event=payment.retry attempt=2"}
~~~

Đây là định dạng **JSON Lines / NDJSON**: mỗi dòng độc lập là một JSON object. Không đặt hai object liền nhau thành một JSON document duy nhất; công cụ đọc cần parse **từng dòng** hoặc dùng NDJSON parser.

### Phân tích ví dụ JUL

1. Logger lấy từ **Logger.getLogger("com.example.checkout.OrderService")**, nên **record.getLoggerName()** mang tên đó trong các lời gọi được phát.
2. **Formatter.format(LogRecord)** nhận record và tạo JSON với key **logger**, **level** và **message**. Với JUL, **getLevel().getName()** trả tên như INFO/WARNING.
3. **formatMessage(record)** giải quyết mẫu tham số JUL, trong ví dụ **{0}** được thay thành **OD-42**. Đừng nhầm placeholder này với **{}** của SLF4J.
4. **jsonString(...)** escape dấu nháy, backslash, newline, carriage return, tab và các control character thấp, tránh phá cú pháp JSON khi message chứa ký tự đó. Nó không phải serializer tổng quát.
5. **StreamHandler** ghi vào ByteArrayOutputStream, không ghi trực tiếp vào file/console. Sau khi **handler.close()**, chương trình đọc buffer rồi in stdout.
6. **setUseParentHandlers(false)** ngăn bản ghi truyền tới handler cha và xuất trùng. Logger/Handler được đặt INFO để cả hai event đều được chấp nhận.
7. Không in timestamp để output không phụ thuộc thời gian. Trong hệ thống thật, một JSON record thường cần timestamp/trace/service theo schema thống nhất.

**Giới hạn:** ví dụ minh họa **cách sinh field logger từ logging event**, không chứng minh mọi backend đều dùng cùng schema. Khi chuyển sang Logback, nên chọn JSON encoder đã hỗ trợ escaping/serialization và quản lý cấu hình.

## 7. Thực hành 2 — SLF4J + Logback + JSON encoder

Ví dụ tiếp theo gần với cách dùng production hơn: code Java chỉ gọi **SLF4J API**, Logback làm backend và **logstash-logback-encoder** tạo JSON. Trường mặc định **logger_name** được **đổi tên thành logger** qua cấu hình **fieldNames** của LogstashEncoder.

Bộ ví dụ được kiểm thử với **Java 17, Logback Classic 1.5.18 và logstash-logback-encoder 8.0**. Version là bộ cố định cho bài học, không phải thông tin bản mới nhất; dự án thực cần kiểm tra BOM, tương thích và chính sách cập nhật. Có thêm **Jackson** qua dependency của encoder để parser của ví dụ đọc JSON.

### Cấu trúc dự án

~~~text
logger-field-demo/
├── pom.xml
└── src/
    └── main/
        ├── java/
        │   └── com/
        │       └── example/
        │           └── logging/
        │               └── LogbackLoggerFieldDemo.java
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
  <artifactId>logger-field-demo</artifactId>
  <version>1.0</version>

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
    <dependency>
      <groupId>net.logstash.logback</groupId>
      <artifactId>logstash-logback-encoder</artifactId>
      <version>8.0</version>
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

### File src/main/resources/logback.xml

~~~xml
<configuration>
  <appender name="JSON" class="ch.qos.logback.core.FileAppender">
    <file>target/logger-field.jsonl</file>
    <append>false</append>

    <encoder class="net.logstash.logback.encoder.LogstashEncoder">
      <fieldNames>
        <logger>logger</logger>
      </fieldNames>
    </encoder>
  </appender>

  <root level="INFO">
    <appender-ref ref="JSON"/>
  </root>
</configuration>
~~~

Giải thích:

- **FileAppender** ghi JSON Lines vào **target/logger-field.jsonl**. Thư mục target sẽ có sau bước Maven compile.
- **LogstashEncoder** tạo record JSON đúng cú pháp và cung cấp các field thông dụng.
- **fieldNames / logger** là phần **đổi tên output field** từ mặc định **logger_name** sang **logger**. Nó không đổi tên Logger object trong ứng dụng.
- **append=false** giúp bài test chỉ có một record, không trộn các lần chạy. Trong production, phải có chính sách append/rolling/retention phù hợp.
- **root INFO** cho phép INFO và những mức nghiêm trọng hơn qua appender; backend có thể có filter khác trong hệ thống thực.

**Nếu bỏ phần fieldNames trên**, LogstashEncoder thường xuất **logger_name** theo schema mặc định, không phải **logger**. Đây là khác biệt quan trọng khi dashboard mong đợi một key cụ thể.

### File src/main/java/com/example/logging/LogbackLoggerFieldDemo.java

~~~java
package com.example.logging;

import ch.qos.logback.classic.LoggerContext;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.slf4j.MDC;

public class LogbackLoggerFieldDemo {
    private static final Logger LOG =
            LoggerFactory.getLogger("com.example.checkout.OrderService");

    public static void main(String[] args) throws Exception {
        LoggerContext context =
                (LoggerContext) LoggerFactory.getILoggerFactory();
        MDC.put("requestId", "req-17");
        try {
            LOG.info("event=order.created orderId={}", "OD-42");
        } finally {
            MDC.remove("requestId");
            context.stop();
        }

        List<String> lines = Files.readAllLines(
                Path.of("target", "logger-field.jsonl"), StandardCharsets.UTF_8);
        JsonNode event = new ObjectMapper().readTree(lines.get(0));

        System.out.println("records=" + lines.size());
        System.out.println("logger=" + event.path("logger").asText());
        System.out.println("level=" + event.path("level").asText());
        System.out.println("message=" + event.path("message").asText());
        System.out.println("requestId=" + event.path("requestId").asText());
        System.out.println("hasLoggerName=" + event.has("logger_name"));
        System.out.println("loggerIsText=" + event.path("logger").isTextual());
    }
}
~~~

### Lệnh chạy Maven

Tại thư mục chứa pom.xml:

~~~bash
mvn -q compile exec:exec "-Dexec.executable=java" "-Dexec.args=-classpath %classpath com.example.logging.LogbackLoggerFieldDemo"
~~~

Maven Exec Plugin khởi chạy một **JVM con** và cung cấp classpath của dự án. Điều này giúp tách backend logging của chương trình khỏi logging của chính Maven. Lệnh cần Maven và các dependency đã được tải/cache hợp lệ.

**Stdout chính xác đã kiểm thử của chương trình:**

~~~text
records=1
logger=com.example.checkout.OrderService
level=INFO
message=event=order.created orderId=OD-42
requestId=req-17
hasLoggerName=false
loggerIsText=true
~~~

Các dòng là **stdout do chương trình kiểm tra JSON in ra**, không phải toàn bộ JSON được viết ra file. Trong file thực tế còn có thể có **@timestamp, @version, thread_name** và những field khác do LogstashEncoder hỗ trợ. Những giá trị như timestamp không được hardcode vào expected output vì phụ thuộc thời gian chạy.

### Tại sao kết quả đáng tin cậy?

1. **LOG** có tên **com.example.checkout.OrderService**, dù class main chạy ví dụ mang tên **LogbackLoggerFieldDemo**. Điều này chứng minh logger field **không bắt buộc là tên caller class**.
2. **LogstashEncoder** đưa tên logger vào output JSON. **fieldNames** đổi key thành **logger**.
3. **Jackson ObjectMapper.readTree** parse record thành JsonNode; việc **loggerIsText=true** chứng minh field có kiểu JSON string, không chỉ là chuỗi được grep.
4. **hasLoggerName=false** cho thấy khi đổi tên chuẩn, field mặc định **logger_name** không cùng lúc tồn tại trong record của demo.
5. **requestId=req-17** đến từ MDC; nó khác logger name và có vòng đời theo request.
6. **level=INFO** là severity của sự kiện; **message** là nội dung do SLF4J giải quyết placeholder **{}**.
7. **context.stop()** đóng logging context trước khi file được đọc, giảm khả năng đọc dữ liệu chưa hoàn tất. Việc stop vẫn không tự bảo đảm fsync/durable ingestion qua hệ thống ngoài.
8. Ví dụ dùng **JSON parser**, không dùng phép split theo dấu phẩy hoặc dấu hai chấm, vì JSON string hợp lệ có thể chứa những dấu đó.

**Cảnh báo lifecycle:** cast ILoggerFactory sang Logback LoggerContext chỉ hợp lệ khi backend thực sự là Logback Classic. Nếu ứng dụng dùng provider SLF4J khác, code phải dùng lifecycle phù hợp hoặc framework quản lý logging. Trong ứng dụng thật, không stop global logging context sau mỗi request; chỉ dừng tại shutdown toàn ứng dụng.

## 8. Logger field mặc định trong LogstashEncoder

Tài liệu chính thức của **logstash-logback-encoder** liệt kê những field chuẩn của LogstashEncoder, gồm:

| Tên mặc định | Ý nghĩa |
| --- | --- |
| **@timestamp** | Thời điểm của logging event |
| **@version** | Phiên bản format Logstash |
| **message** | Message sau khi format tham số |
| **logger_name** | Tên logger phát event |
| **thread_name** | Thread liên quan đến event |
| **level** | Level dưới dạng text |
| **level_value** | Giá trị severity dạng số nếu output cấu hình tương ứng |

Bạn có thể dùng **fieldNames** để đổi tên các field chuẩn. Phần tử XML **logger** là tên thuộc tính cấu hình cho logger name, **không phải logger_name**:

~~~xml
<encoder class="net.logstash.logback.encoder.LogstashEncoder">
  <fieldNames>
    <logger>logger</logger>
  </fieldNames>
</encoder>
~~~

Đây là **fragment cấu hình**, cần được đặt trong appender thích hợp. Một số phiên bản thư viện có cấu hình khác nhau; hãy kiểm tra tài liệu khớp dependency thực tế.

Ngoài LogstashEncoder, hệ **LoggingEventCompositeJsonEncoder** cho phép chọn các provider riêng. Khi sử dụng composite encoder, danh sách field phụ thuộc providers đã khai báo; **không giả định logger_name luôn tự có**.

Một ý tưởng cấu hình composite minh họa:

~~~xml
<encoder class="net.logstash.logback.encoder.LoggingEventCompositeJsonEncoder">
  <providers>
    <timestamp/>
    <loggerName>
      <fieldName>logger</fieldName>
    </loggerName>
    <logLevel/>
    <message/>
  </providers>
</encoder>
~~~

Khối này mô tả việc chọn providers cho timestamp, loggerName, level và message. **Không đặt đồng thời LogstashEncoder và composite encoder trong cùng một appender** chỉ để tạo hai key tên logger; hãy chọn một chiến lược output schema rõ ràng.

**Mẹo nhận diện:** trong logback PatternLayout dạng text, converter **%logger** có thể xuất cùng logger name; khi cần **JSON field**, nên dùng encoder/provider JSON đúng cách thay vì ghép thủ công các dấu nháy quanh **%logger**.

## 9. Có nên rút ngắn tên logger trong JSON?

Tên logger theo lớp đầy đủ như:

~~~text
com.example.checkout.internal.service.OrderValidationService
~~~

có thể dài nhưng giàu thông tin. Một số encoder cho phép rút gọn, ví dụ **shortenedLoggerNameLength** của logstash-logback-encoder. Tuy nhiên, việc rút gọn phải được cân nhắc.

**Ưu điểm:**
- Ít byte hơn trong log ở hệ thống có khối lượng lớn.
- Dễ đọc khi hiển thị trong terminal hoặc bảng có cột hẹp.

**Rủi ro:**
- Hai class khác nhau có thể có dạng rút gọn khó phân biệt.
- Dashboard đang lọc theo full logger name có thể không còn match.
- Khi đổi thuật toán/version, giá trị field biến động dù code không đổi.
- Truy vết từ logger về source class có thể khó hơn.

Nếu hệ thống log tập trung lưu theo dung lượng, bạn có thể cân nhắc rút gọn để tiết kiệm chi phí, nhưng trước tiên hãy quyết định **có thật sự cần tên class đầy đủ để truy vấn không**. Với hoạt động debug và điều tra sự cố, full logger name thường có giá trị.

**Không dùng tên logger chứa requestId hay userId** chỉ để tránh khai báo field riêng. Ví dụ **checkout.req-17.user-42** tạo số lượng giá trị logger rất lớn và khiến cấu hình level theo logger khó quản lý. RequestId/traceId thuộc nhóm **context fields**, không thuộc định danh logger lâu dài.

## 10. Field logger theo ECS, và các trường phân biệt

Elastic Common Schema có field **log.logger** để chỉ tên logger bên trong application, thường là class tạo logger hoặc một custom name.

Một object JSON theo tinh thần ECS có thể được biểu diễn:

~~~json
{
  "@timestamp": "2026-11-09T13:20:30.123Z",
  "log": {
    "level": "INFO",
    "logger": "com.example.checkout.OrderService"
  },
  "service": {
    "name": "checkout-api"
  },
  "message": "event=order.created"
}
~~~

Cần phân biệt với các ECS fields:

- **log.logger**: tên logger của ứng dụng.
- **log.level**: textual severity.
- **log.file.path**: đường dẫn file mà sự kiện được đọc từ đó; không phải tên logger. Nếu sự kiện không đến từ file, không nên tự tạo giá trị giả.
- **log.origin.file.name / log.origin.file.line**: thông tin nguồn code có thể được thu ở mức mở rộng; khác tên logger.
- **service.name**: danh tính service chạy ứng dụng.
- **process.thread.name**: thread, nếu pipeline đưa dữ liệu theo schema tương ứng.

**Không lấy logger name làm service.name**: một service có thể có hàng trăm logger. Ngược lại, nhiều service có thể dùng thư viện cùng logger name; muốn phân biệt nguồn phải kết hợp **service.name, deployment environment, pod/host/instance và timestamp** theo schema đã chọn.

Nếu hệ thống dùng **OpenTelemetry**, cần hiểu logger name có thể được ánh xạ qua **InstrumentationScope** trong data model, không phải lúc nào cũng xuất dưới key top-level **logger**. Cần xác định pipeline ingest/OTLP exporter và schema đích trước khi đối chiếu.

## 11. Tìm kiếm và thống kê theo logger field

Sau khi dữ liệu đã là **JSON Lines hợp lệ**, có thể dùng một JSON parser để truy xuất field.

### Ví dụ với jq

Giả sử file **application.jsonl** chứa các object JSON có field top-level logger:

~~~bash
jq -r '.logger' application.jsonl
~~~

Lệnh trên in giá trị logger của từng record. Nếu một record thiếu field, jq thường in **null**, vì vậy không được coi null là một logger thật.

Lọc chính xác một class:

~~~bash
jq -c 'select(.logger == "com.example.checkout.OrderService")' application.jsonl
~~~

Lọc một nhóm package:

~~~bash
jq -c 'select((.logger // "") | startswith("com.example.checkout."))' application.jsonl
~~~

Đoạn **(.logger // "")** tránh lỗi khi field vắng mặt hoặc null trong những record đơn giản. Nếu dữ liệu có thể chứa logger không phải string (object/số), cần kiểm tra type trước khi dùng startswith hoặc chuẩn hóa schema tại ingest.

**Lưu ý:** jq là công cụ ngoài JDK, ví dụ chỉ chạy nếu đã cài jq. JSONL phải có mỗi dòng một object hoàn chỉnh; file chứa cả stack trace text multiline hoặc dữ liệu bị nối hỏng sẽ không parse đúng.

### Với JSON field nested

Nếu schema là:

~~~json
{"log":{"logger":"com.example.checkout.OrderService"}}
~~~

thì đường dẫn truy vấn jq là:

~~~bash
jq -r '.log.logger' application.jsonl
~~~

Nếu JSON có key literal tên **"log.logger"** ở top-level, cú pháp phải khác:

~~~bash
jq -r '.["log.logger"]' application.jsonl
~~~

Đây là một chi tiết nhỏ nhưng dễ gây kết luận sai. Một document có **{"log":{"logger":...}}** không đồng nhất về cấu trúc với **{"log.logger":...}**; cách search backend xử lý dotted fields còn tùy mapping/ingest.

### Trong hệ thống tập trung

Có thể dựng dashboard:

- Số event theo logger name và level.
- Top logger có nhiều WARN/ERROR trong một service.
- Tốc độ tăng lỗi ở package checkout.
- Log của một logger trước/sau triển khai.
- Nhóm logger phát nhiều DEBUG nhất để tối ưu chi phí.

Nhưng **logger đơn lẻ không đủ** cho một sự cố đa service. Kết hợp service.name, traceId/requestId, timestamp và environment. Cũng cần lưu ý **logger** là giá trị chuỗi phân loại (keyword/category), không phải đại lượng số để cộng hoặc lấy trung bình.

## 12. Field logger và MDC: tránh ghi đè, trùng key

MDC dùng để gắn ngữ cảnh theo xử lý, thường là **requestId**, **traceId**, **tenantId** đã được phép ghi. Logger name được lấy từ **Logger object**; hai nguồn này có nhiệm vụ khác nhau.

Ví dụ:

~~~java
// Minh họa trong Java dùng SLF4J.
org.slf4j.MDC.put("requestId", "req-17");
try {
    LOG.info("event=order.created");
} finally {
    org.slf4j.MDC.remove("requestId");
}
~~~

Một encoder JSON có thể xuất:

~~~json
{
  "logger": "com.example.checkout.OrderService",
  "requestId": "req-17",
  "message": "event=order.created"
}
~~~

**Không làm điều này chỉ để đổi tên logger:**

~~~java
// Ví dụ về cách dùng sai vì gây đụng độ schema.
org.slf4j.MDC.put("logger", "special-value");
~~~

Trong một số JSON encoder, MDC được xuất thành các field top-level. Nếu một MDC key cũng tên **logger**, có thể sinh **hai JSON property cùng tên**, giá trị ghi đè hoặc hành vi phụ thuộc parser/serializer. JSON object có duplicate keys là tình trạng nên tránh; các hệ thống downstream có thể giữ giá trị đầu, giá trị cuối hoặc báo lỗi.

**Cách làm đúng:** dùng field logger do encoder lấy từ logging event, dùng MDC cho correlation/metadata, và đặt tên field không va chạm. Nếu cần đổi field logger, thực hiện qua **fieldNames/provider configuration**, không qua MDC tùy tiện.

Trong hệ thống thread pool, hãy dọn MDC đúng lúc; một request mới có thể kế thừa giá trị cũ nếu thread được tái sử dụng và context không được clear. Nhưng **logger name** được gắn với Logger và thường không thay theo request. Đừng dùng trường logger để thay thế việc truyền context qua async.

## 13. Tính ổn định của tên logger và mức độ phân biệt

Một thiết kế tốt thường có những đặc điểm:

| Quy tắc | Vì sao hữu ích | Ví dụ |
| --- | --- | --- |
| **Tên theo package/class** khi phù hợp | Dễ truy về source và phân cấp logger | com.example.checkout.OrderService |
| **Tên tùy chỉnh có chủ đích** | Thể hiện subsystem vượt ranh giới class | checkout.workflow |
| **Không có ID động** | Hạn chế cardinality và rối config | Không dùng checkout.user-12345 |
| **Không chứa secrets/PII** | Tránh lộ dữ liệu trong field thường được index | Không dùng email/token làm tên logger |
| **Ổn định giữa môi trường** | Query/dev/prod dùng được cấu hình giống nhau | Giữ logger name khi deploy |
| **Thống nhất kiểu JSON string** | Parser và indexer không phải xử lý hỗn hợp type | logger luôn string |
| **Có quy ước fallback** | Hạn chế field null/missing không giải thích được | Theo policy encoder/ingest |
| **Có service identity riêng** | Phân biệt hai service dùng chung thư viện | service.name độc lập logger |

Trong ứng dụng nhiều module, cấu trúc tên **com.example.feature.Component** có thể giúp bật DEBUG chọn lọc ở backend. Nếu mọi class đều dùng chung logger name **app**, bộ lọc theo package/class mất tác dụng và điều tra sự cố khó hơn.

Nhưng cũng không nên cố biến mọi lời gọi log thành một logger mới. Số lượng logger names động tăng tài nguyên và làm namespace khó quản lý. Chọn class name ổn định hoặc số lượng category hữu hạn, mô tả đúng ý nghĩa.

## 14. Khi field logger có giá trị bất ngờ

Một vài trường hợp thực tế:

**Trường hợp A: logger có tên của helper, không phải class nghiệp vụ**

~~~java
// Minh họa: LoggingHelper nắm giữ logger và nhiều service dùng chung.
private static final org.slf4j.Logger LOG =
        org.slf4j.LoggerFactory.getLogger(LoggingHelper.class);
~~~

Nếu mã trong helper phát event cho mọi service, tên logger có thể luôn là **LoggingHelper**. Nếu cần truy nguồn service, phải thiết kế logger per class hoặc truyền category rõ ràng; đừng dùng caller data như một phép sửa tự động không xem chi phí.

**Trường hợp B: logger là một tên tùy chỉnh**

~~~java
org.slf4j.Logger LOG =
        org.slf4j.LoggerFactory.getLogger("payment.events");
~~~

Đây là tên hợp lệ. Không nên báo “sai tên class” chỉ vì không tìm thấy Java class payment.events.

**Trường hợp C: toàn bộ record hiển thị ROOT**

Một số record có thể dùng root logger. Điều này không tự động là lỗi JSON encoder. Nhưng nếu mọi module đều phát log bằng root, bạn mất khả năng tách nhóm theo nguồn; nên xem lại cách lấy Logger.

**Trường hợp D: class được rename/refactor**

Khi code dùng **LoggerFactory.getLogger(MyClass.class)**, tên logger có thể thay theo tên Class sau refactor. Dashboard đang lọc class cũ sẽ không còn match. Với những event quan trọng lâu dài, có thể dùng **event.name** hoặc một business category ổn định riêng để không phụ thuộc hoàn toàn vào tên class.

**Trường hợp E: library dùng logger name khác app**

Một thư viện bên thứ ba thường dùng namespace riêng, ví dụ **org.some.library.Component**. Điều này hợp lý; khi tìm log nên lọc theo service.name cùng logger để biết thư viện đó đang chạy trong service nào.

**Trường hợp F: bridge từ JUL hoặc Log4j API**

Khi log được chuyển từ API khác sang SLF4J/backend, tên logger thường được giữ hoặc ánh xạ qua adapter, nhưng chi tiết còn tùy cấu hình bridge/provider. Cần xác minh giá trị thực của một record qua pipeline, không suy diễn bridge luôn giống nhau ở mọi version.

## 15. Kiểm thử trường logger trong JSON logging

Một bài QA nên có dữ liệu thật được parser đọc, không chỉ kiểm tra log trên màn hình bằng mắt.

**Các bước đề xuất:**

1. Chọn một logger có **tên cố định dễ đối chiếu**, chẳng hạn com.example.checkout.OrderService.
2. Phát một INFO với message và một requestId riêng.
3. Đảm bảo backend thực sự nhận event: kiểm tra root/logger level, filter và appender.
4. Ghi **JSON Lines** vào một file test riêng hoặc thu console bằng cách phù hợp.
5. Dùng JSON parser đọc từng record; kiểm tra **một record là một JSON object hợp lệ**.
6. Xác nhận field đúng **tên key** đã cam kết: logger, logger_name hoặc log.logger.
7. Xác nhận **kiểu field là string**; không phải number, array hoặc object.
8. Xác nhận **giá trị bằng tên logger đã chọn**, không phải tên class main hoặc thread nếu không trùng.
9. Xác nhận có **level/message** đúng; requestId là một field khác, không thay thế logger.
10. Phát một event với logger khác để xem việc phân nhóm có thực sự đổi theo nguồn.
11. Thử message có dấu nháy, backslash, newline và tiếng Việt; JSON encoder vẫn phải tạo JSON hợp lệ.
12. Nếu dùng schema ECS, kiểm tra **log.logger** và mapping index; không chỉ key top-level.
13. Kiểm tra record có exception và multiline stack trace vẫn parse đúng.
14. Xác nhận collector/indexer không đổi tên hoặc xóa logger field.
15. Kiểm tra dashboard/alert phụ thuộc tên field sau khi deploy hoặc đổi encoder version.

Một số assertion minh họa theo ý tưởng Java/Jackson:

~~~java
// Đoạn minh họa, event là Jackson JsonNode đã parse.
if (!event.path("logger").isTextual()) {
    throw new IllegalStateException("logger must be a JSON string");
}
if (!"com.example.checkout.OrderService"
        .equals(event.path("logger").asText())) {
    throw new IllegalStateException("unexpected logger name");
}
~~~

Đây là **đoạn kiểm tra**, không phải một chương trình độc lập. Trong ví dụ Maven ở mục 7, những điều kiện tương tự đã được kiểm tra qua kết quả parser.

### Trường hợp test phải xử lý thiếu field

Một event có thể không có logger vì:
- Encoder/provider không được bật.
- Schema được đổi sang logger_name hoặc log.logger.
- Field bị exclusion filter của encoder loại.
- Pipeline ingest chuyển/rename key.
- Một record được tạo thủ công mà không có logger name.
- Dữ liệu không phải logging event cùng loại (access log, audit event, metric...).

Không lấp logger thiếu bằng một chuỗi tùy ý mà không có chính sách. Nếu thực sự không biết nguồn, hệ thống có thể đánh dấu một giá trị “unknown” theo schema để quan sát và báo lỗi; đừng đánh tráo bằng một class name đoán ra từ message.

## 16. Lỗi phổ biến và cách khắc phục

| Triệu chứng | Nguyên nhân thường gặp | Cách xử lý |
| --- | --- | --- |
| JSON có **logger_name** nhưng dashboard truy vấn **logger** | Encoder dùng tên mặc định khác schema | Chuẩn hóa key bằng fieldNames/ingest |
| Không có trường logger | Encoder không include hoặc field bị drop | Kiểm tra provider, encoder, exclude và collector |
| logger luôn cùng một tên helper | Dùng một Logger chung trong utility | Tổ chức logger theo class/subsystem phù hợp |
| logger trông như package, không có class thật | Logger được tạo bằng string custom | Chấp nhận category; đừng mặc định phải load Class |
| logger sai sau refactor | getLogger(Class) đổi theo Class.getName | Cập nhật query, dùng event name ổn định |
| logger chứa userId hoặc email | Logger name tạo động từ input | Bỏ dữ liệu request, dùng MDC/field riêng và không ghi PII |
| JSON có hai key logger | MDC hoặc custom fields trùng key do encoder cũng xuất | Loại đụng độ tên, kiểm tra output parser |
| logger là object thay vì string | Schema không nhất quán hoặc ingest mapping sai | Sửa producer/transform, kiểm tra type |
| Lọc theo logger không thấy log | Log chỉ có ở tên field khác hoặc filter level | Xác minh JSON raw, schema và backend |
| logger và caller_class khác nhau | Category logger tùy chỉnh hoặc helper | Hiểu ý nghĩa khác nhau, bổ sung caller khi thực sự cần |
| Record không parse vì message có quote/newline | Ghép JSON bằng string thủ công thiếu escaping | Dùng JSON encoder/serializer chuẩn |
| Missing requestId bị hiểu thành missing logger | Nhầm MDC field với logger name | Kiểm tra hai trường độc lập |
| Tìm theo logger của thư viện trả dữ liệu nhiều service | Chưa lọc service.name | Kết hợp service, environment và logger |
| Tên logger bị rút gọn | Encoder cấu hình shortened name | Khôi phục full name hoặc sửa quy ước query |
| Log qua OpenTelemetry không có field logger top-level | Dùng data model/instrumentation scope khác | Xác nhận ánh xạ export/ingest phù hợp |

**Không dùng regex để thay đổi nguyên văn một JSON event** nếu có thể xử lý bằng parser/transformer theo cấu trúc. Regex có thể sai khi message chứa escape, object lồng nhau hoặc trường có thứ tự khác dự kiến.

## 17. Bảo mật, hiệu năng và observability

### Bảo mật

Không ghi **password, token, API key, email cá nhân, số điện thoại hoặc payload nhạy cảm** vào logger name. Logger name thường xuất trong tất cả record, được index lâu dài và hiển thị trong dashboard. Nếu tạo logger theo input không tin cậy, ngoài rò rỉ dữ liệu còn có rủi ro tạo hàng nghìn category và gây tốn tài nguyên.

**JSON string escaping** là yêu cầu cần thiết: dấu nháy, backslash, control character không được phép làm vỡ JSON. Trong production, hãy sử dụng encoder/serializer đáng tin cậy, không tự nối chuỗi theo template cho message không tin cậy.

**Log injection** vẫn có thể tồn tại nếu downstream render dữ liệu sai hoặc lưu cùng pipeline dạng text. JSON đúng cú pháp giúp parser có ranh giới trường tốt hơn, nhưng không thay thế kiểm soát dữ liệu nhập và quyền truy cập.

### Hiệu năng/cardinality

Field logger thường có số giá trị **hữu hạn theo số class/category**, nhỏ hơn requestId vốn thay đổi liên tục. Nếu tạo logger name chứa UUID/requestId, cardinality tăng mạnh, làm tốn bộ nhớ của backend, index và dashboard. Nên dùng tên class/subsystem ổn định.

**Caller class/method/line** có thể tốn chi phí vì cần phân tích stack; **logger name** đã được gắn với logger và thường rẻ hơn việc thu caller data. Không bật thu caller cho mọi record chỉ để có một trường mà Logger đã cung cấp.

### Quan sát đa service

Khi cùng thư viện xuất logger name **org.apache.http...** ở nhiều service, cần thêm service.name hoặc thông tin deployment để biết nguồn. Trong hệ tracing, traceId/requestId bổ sung bối cảnh sự kiện. Field logger trả lời **ai phát record trong không gian tên logger**, còn traceId trả lời **record thuộc giao dịch/trace nào**.

### Dữ liệu dùng làm nguồn sự thật

Tương tự các field log khác, logger name **không chứng minh** nghiệp vụ đã hoàn tất; đó là metadata của một lần ghi log. Thông điệp event=order.completed có thể được phát trước commit hoặc bị mất khi appender/collector lỗi. Hãy xác minh kết quả nghiệp vụ ở hệ thống dữ liệu thích hợp.

## 18. Câu hỏi tự kiểm tra

**Câu 1.** Trong JSON **{"logger":"com.example.checkout.OrderService"}**, logger là gì?

**Đáp án:** Tên logger phát logging event, có kiểu JSON string. Nó không nhất thiết là tên class đang thực thi.

**Câu 2.** Với SLF4J **LoggerFactory.getLogger(MyClass.class)**, tên logger thường từ đâu?

**Đáp án:** Từ **MyClass.class.getName()** theo API SLF4J.

**Câu 3.** Khi LogstashEncoder mặc định xuất logger_name, đổi thành logger bằng cách nào?

**Đáp án:** Cấu hình **fieldNames** với phần tử **logger** trong LogstashEncoder, hoặc chuẩn hóa schema qua ingest phù hợp.

**Câu 4.** logger và service.name có giống nhau không?

**Đáp án:** Không. Logger name thường là class/category; service.name là ứng dụng/dịch vụ. Một service có nhiều logger, một library logger có thể xuất ở nhiều service.

**Câu 5.** Tại sao **getLogger("payment.events")** hợp lệ dù không có Java class payment.events?

**Đáp án:** Vì logger có thể được đặt tên tùy chỉnh theo category/subsystem, không bắt buộc là Class name.

**Câu 6.** Có nên dùng MDC.put("logger", requestId) để đưa ID request vào field logger?

**Đáp án:** Không. Điều này có thể gây đụng key, sai ý nghĩa và tăng cardinality. Dùng requestId/traceId làm field riêng.

**Câu 7.** Vì sao **log.logger** của ECS không đương nhiên tương đương một key literal **"log.logger"** trong JSON?

**Đáp án:** Dotted field là tên đường dẫn field trong schema; biểu diễn JSON nested **{"log":{"logger":"..."}}** và key literal top-level có cấu trúc khác nhau, cần mapping nhất quán.

**Câu 8.** Nếu Logger name và caller class khác nhau, JSON chắc chắn sai?

**Đáp án:** Không. Code có thể dùng logger category tùy chỉnh hoặc helper, nên hai nguồn thông tin không bắt buộc giống nhau.

**Câu 9.** Có thể grep chuỗi logger trong text và kết luận trường JSON có kiểu string không?

**Đáp án:** Không. Phải parse JSON và kiểm tra field type; grep có thể match message hoặc một trường khác.

**Câu 10.** Vì sao JSON encoder tốt hơn cách ghép JSON thủ công cho production?

**Đáp án:** Encoder/serializer chuyên dụng xử lý escaping, kiểu dữ liệu, schema, exception và khả năng tích hợp. Tự ghép string dễ làm JSON không hợp lệ hoặc tạo duplicate keys.

**Câu 11.** Nếu chỉ có logger field thì có thể xác định request cụ thể không?

**Đáp án:** Không. Cần requestId/traceId hoặc ngữ cảnh khác vì một logger thường dùng chung cho nhiều request.

**Câu 12.** Vì sao cần kiểm tra logger field sau khi đổi backend/encoder?

**Đáp án:** Backend và encoder có thể đổi tên key, rút ngắn logger name, thay cấu trúc hoặc không xuất field. Parser/dashboard có thể ngừng match dù code LOG.info không đổi.

## 19. Tài liệu tham khảo kỹ thuật

- [SLF4J Logger API](https://slf4j.org/apidocs/org/slf4j/Logger.html): **getName()** và vai trò của SLF4J Logger.
- [SLF4J LoggerFactory API](https://slf4j.org/apidocs/org/slf4j/LoggerFactory.html): **getLogger(Class)** và **getLogger(String)**.
- [logstash-logback-encoder — README](https://github.com/logfellow/logstash-logback-encoder/blob/main/README.md): mặc định **logger_name**, cấu hình **fieldNames**, JSON encoder và provider loggerName.
- [Logback Manual — Layouts](https://logback.qos.ch/manual/layouts.html): cách **%logger** xuất tên logger trong PatternLayout.
- [Oracle Java SE 17 — LogRecord](https://docs.oracle.com/en/java/javase/17/docs/api/java.logging/java/util/logging/LogRecord.html): **getLoggerName()** và metadata record của JUL.
- [Elastic Common Schema — Log fields](https://www.elastic.co/docs/reference/ecs/ecs-log): định nghĩa **log.logger**, **log.level**, **log.file.path** và các trường khác.
- [OpenTelemetry — Instrumentation scope](https://opentelemetry.io/docs/concepts/instrumentation-scope/): ngữ nghĩa instrumentation scope khi log đi qua telemetry pipeline.

## Ghi nhớ

**Field logger là tên logger phát ra log event, thường ở dạng JSON string.** Nó hữu ích để lọc theo class, package hoặc subsystem, nhưng không đồng nghĩa caller class, thread, service, requestId hay file path. SLF4J/JUL cung cấp tên logger qua API; encoder quyết định key JSON thực tế (**logger**, **logger_name**, **log.logger** theo schema). Trong production, hãy chọn một schema ổn định, dùng JSON serializer/encoder đúng cách, kiểm tra bằng parser, tránh trùng key với MDC và không dùng dữ liệu request làm logger name. **Tên logger là metadata về nguồn phát log, không phải toàn bộ bối cảnh của một sự kiện.**
