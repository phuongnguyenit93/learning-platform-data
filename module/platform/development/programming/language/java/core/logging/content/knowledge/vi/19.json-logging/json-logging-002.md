# JSON encoder trong Java Logging: từ LoggingEvent đến JSON Lines

## 1. JSON encoder là gì?

**JSON encoder** là thành phần chuyển một **logging event** thành dữ liệu **JSON hợp lệ** để gửi tới console, file, socket hoặc bộ thu thập log. Trong hệ sinh thái **SLF4J + Logback**, encoder hoạt động ở tầng output của `Appender`: nó biến event có level, logger, timestamp, message, throwable và context thành những byte có cấu trúc, thay vì chỉ ghép một dòng văn bản bằng `PatternLayout`.

Ví dụ bản ghi text:

```text
2026-01-12 10:15:00 INFO checkout.OrderService - event=order.created orderId=ord-17
```

Một bản ghi JSON tương đương về ý nghĩa:

```json
{
  "timestamp": "2026-01-12T10:15:00Z",
  "level": "INFO",
  "logger": "checkout.OrderService",
  "service": "checkout",
  "event": "order.created",
  "orderId": "ord-17",
  "durationMs": 125,
  "success": true
}
```

Đây là **mẫu schema minh họa**, không phải toàn bộ trường mặc định do một encoder cụ thể sinh ra. Encoder khác nhau có tên trường và kiểu dữ liệu khác nhau. Ví dụ `timestamp` có thể là chuỗi ISO 8601 hoặc epoch milliseconds; `logger` có thể mang tên `loggerName` hoặc `logger_name`. **Không được giả định cấu hình encoder nào cũng phát đúng JSON minh họa trên.**

Lợi ích của JSON:

- Hệ thống thu thập có thể lọc theo `level`, `event`, `errorCode`, `traceId` mà không phải tách chuỗi bằng biểu thức chính quy phức tạp.
- Dữ liệu dạng **number**, **boolean**, **null**, **array** và **object** có thể giữ đúng kiểu nếu được đưa vào encoder theo API/serializer phù hợp.
- Dấu ngoặc kép, dấu gạch chéo ngược, ký tự xuống dòng và Unicode có thể được **escape đúng quy tắc JSON**.
- JSON Lines phù hợp với container stdout, file tail và các pipeline log tập trung nhận mỗi event một record.
- Schema nhất quán hỗ trợ dashboard, truy vấn, cảnh báo và tương quan log với distributed tracing.

**JSON encoder không làm thay Logger/Filter/Appender**: một lời gọi DEBUG bị Logger chặn sẽ không được “khôi phục” chỉ vì bật JSON. Và một JSON hợp lệ không tự có nghĩa dữ liệu trong đó an toàn hoặc được lưu bền vững.

## 2. Pipeline: sự kiện log được encode ở đâu?

```text
Mã Java:
  logger.atInfo()
        .addKeyValue("durationMs", 125)
        .log("event=order.created")
             |
             v
         SLF4J API
             |
             v
      Logback Logger
      kiểm tra level/filter
             |
             v
     ILoggingEvent
      - timestamp/level/logger/thread
      - message, parameters, throwable
      - MDC, markers, key-value pairs
             |
             v
        Appender
        Console / File / RollingFile / ...
             |
             v
        JSON Encoder
        lựa chọn field
        escape và serialize
        tạo byte + delimiter
             |
             v
    stdout / .jsonl file / collector
```

Các khái niệm:

| Thành phần | Nhiệm vụ |
| --- | --- |
| SLF4J `Logger` | API phát event, truyền message/arguments và throwable |
| Logback `Logger` | Kiểm tra level; tạo/đưa event tới Appender |
| `ILoggingEvent` | Đối tượng mang thuộc tính của event |
| `Appender` | Đích và đường xuất dữ liệu |
| `Filter` | Cho qua/chặn event theo điều kiện |
| `Layout` | Trình bày event thành một `String` |
| `Encoder<ILoggingEvent>` | Chuyển event thành bytes để ghi ra stream |
| JSON parser/collector | Giải mã JSON, map trường và lưu/truy vấn |

Theo API Logback, `Encoder<E>` có các phương thức tiêu biểu:

```java
byte[] headerBytes();
byte[] encode(E event);
byte[] footerBytes();
```

Đây là **chữ ký phương thức minh họa** bên trong interface tổng quát, không phải một file Java độc lập. Encoder có nhiệm vụ tạo bytes cho output; Layout chỉ tạo text. `LayoutWrappingEncoder` kết nối Layout với cơ chế encoder, còn JSON encoder thường serialize dữ liệu từ logging event trực tiếp.

**Tên file không quyết định tính JSON:** đổi `application.log` thành `application.json` mà vẫn dùng `PatternLayoutEncoder` text không biến output thành JSON. Ngược lại, JSON encoder có thể ghi vào stdout hoặc file `.jsonl`; nội dung thực mới là yếu tố quyết định.

## 3. JSON Lines: một event trên một dòng

Trong vận hành, định dạng thường dùng là **JSON Lines / NDJSON**: mỗi dòng vật lý chứa **một JSON value** — với logging thường là một object — và kết thúc bằng newline.

```text
{"level":"INFO","event":"order.created","orderId":"ord-17"}
{"level":"WARN","event":"inventory.low","sku":"sku-9"}
{"level":"ERROR","event":"payment.failed","errorCode":"TIMEOUT"}
```

Ví dụ có ba event, mỗi event một dòng. Đây **không phải** một mảng JSON lớn:

```json
[
  {"level":"INFO","event":"order.created"},
  {"level":"WARN","event":"inventory.low"}
]
```

Mảng JSON có thể hợp lệ khi xuất một tài liệu hoàn chỉnh, nhưng không phù hợp mặc định cho stream liên tục cần append từng event. Nếu appender bị dừng đột ngột, một tài liệu chứa mảng với dấu đóng chưa được ghi có thể không parse được. Với JSON Lines, các dòng đã được ghi hoàn chỉnh vẫn có thể được xử lý độc lập.

### 3.1. Dữ liệu chứa dấu xuống dòng

Giả sử giá trị người dùng là:

```text
hello
ERROR event=admin.login success=true
```

Một encoder JSON đúng chuẩn sẽ biểu diễn newline **bên trong chuỗi JSON** bằng escape, không đưa dòng ERROR giả làm một record mới:

```json
{"message":"hello\nERROR event=admin.login success=true"}
```

Khối JSON trên khi trình bày thô chứa các ký tự `\` và `n`, không phải một xuống dòng vật lý bên trong value. Dấu nháy kép trong dữ liệu cũng được escape bằng `\"`; backslash bằng `\\`. JSON Lines nhờ đó có thể giữ **một record/physical line** ngay cả khi message chứa newline logic.

**Cẩn thận:** JSON encoding làm dữ liệu **hợp lệ về cú pháp**, nhưng không chứng minh nội dung là sự kiện thật, không loại secret, không lọc giá trị nguy hiểm cho các hệ thống hạ nguồn. Parser hoặc UI hiển thị lại nội dung phải tiếp tục xử lý dữ liệu không tin cậy.

### 3.2. UTF-8 và delimiter

Nên thống nhất UTF-8 từ ứng dụng tới file/collector. Nếu collector yêu cầu NDJSON, mỗi event nên có một dấu newline cuối record. Không chèn một dòng tiêu đề text như `Starting application...` vào cùng stream JSON nếu collector dự kiến parse mọi dòng; cũng không trộn stack trace text nhiều dòng độc lập vào stream đó.

Các cảnh báo khởi tạo của framework/JVM có thể xuất ở stderr không qua JSON encoder, do đó pipeline cần phân biệt **stdout ứng dụng**, **stderr**, log từ launcher và dữ liệu do Appender phát.

## 4. Schema: JSON đúng cú pháp chưa chắc có ích để truy vấn

Một schema vận hành nên được thiết kế trước khi chọn encoder.

| Trường | Kiểu thường phù hợp | Mục đích |
| --- | --- | --- |
| `timestamp` | Chuỗi ISO 8601 UTC hoặc epoch milliseconds | Thời điểm event |
| `level` | String | Mức INFO/WARN/ERROR |
| `logger` hoặc `loggerName` | String | Nguồn theo package/class |
| `service` | String | Tên service ổn định |
| `environment` | String | dev/staging/prod theo cấu hình |
| `thread` | String | Thread phát event |
| `event` | String | Loại sự kiện, ví dụ `payment.retry` |
| `requestId`, `traceId`, `spanId` | String | Correlation/tracing |
| `errorCode` | String | Mã lỗi ổn định |
| `durationMs` | Number | Độ trễ đo bằng milliseconds |
| `attempt` | Number | Số lần thử |
| `success` | Boolean | Kết quả thành công/thất bại |
| `exception` | Object/string theo encoder | Thông tin Throwable để chẩn đoán |

Tên trường trên là **đề xuất schema**, không phải bảng các field mặc định trong mọi backend. JSON cho phép cả `null` và việc **không có field**; nên thống nhất hai trường hợp đó biểu đạt gì.

### 4.1. Đừng biến số thành chuỗi vô ý

Hai event sau khác kiểu dữ liệu:

```json
{"durationMs":"125"}
```

```json
{"durationMs":125}
```

Dòng đầu là **string**, dòng sau là **number**. Nếu `durationMs` là field dùng để tính percentile, nên giữ kiểu number ở lúc serialize. `MDC.put("durationMs","125")` thường mang string; encoder có thể xuất nó như string trừ khi có writer/serializer tùy chỉnh. Do đó **MDC không phải giải pháp mặc định để tạo mọi field số/boolean có kiểu**.

Tương tự, không tạo message `"durationMs=125"` rồi kỳ vọng encoder tự parse thành field số. Encoder chỉ nhìn thấy message được format (và các structured arguments/key-value/marker nếu backend hỗ trợ); không thể suy ra schema chính xác từ text tự do.

### 4.2. Định danh sự kiện và logger name

- `loggerName` cho biết lớp/module phát sự kiện.
- `event` cho biết loại hoạt động, ví dụ `order.created`.
- `traceId` liên kết đường đi của một request qua nhiều module/service.
- `errorCode` mô tả một nhóm lỗi ổn định.
- `message` vẫn hữu ích cho con người, nhưng không nên là khóa duy nhất để tạo alert.

Không thêm user ID hoặc request ID vào **tên Logger động**: logger name nên hữu hạn theo package/class; những ID biến động thuộc field context có chính sách lưu trữ rõ ràng.

## 5. Các JSON encoder trong hệ sinh thái Logback

Có ít nhất hai hướng thường gặp:

### 5.1. `ch.qos.logback.classic.encoder.JsonEncoder` — encoder JSON có sẵn

Logback cung cấp **`JsonEncoder` gốc** từ nhánh 1.3.8/1.4.8 trở đi. Encoder này ghi mỗi `ILoggingEvent` dưới dạng **một JSON object trên một dòng** và escape theo JSON. Với Logback 1.5.x, encoder có các cờ cấu hình cho phép bật/tắt từng field top-level.

Một số field hiện diện trong định dạng gốc có thể gồm `sequenceNumber`, `timestamp` (số epoch milliseconds), `nanoseconds`, `level`, `threadName`, `loggerName`, `context`, `mdc`, `kvpList`, `message`, `formattedMessage` và `throwable` tùy sự kiện và các cờ đang bật. Không nhầm kiểu/đường dẫn này với schema Logstash ở mục sau.

Ví dụ cấu hình tối thiểu:

```xml
<encoder class="ch.qos.logback.classic.encoder.JsonEncoder"/>
```

Đây là **mảnh bên trong một FileAppender/ConsoleAppender**, không phải file Logback độc lập. Encoder gốc phù hợp khi schema event do Logback cung cấp là đủ và bạn muốn ít dependency ngoài hơn.

**Chi tiết quan trọng trong Logback 1.5.x:** theo tài liệu, mặc định các field top-level được bật **trừ `formattedMessage`**. Nếu muốn hiển thị message đã thay placeholder SLF4J, có thể cấu hình:

```xml
<encoder class="ch.qos.logback.classic.encoder.JsonEncoder">
    <withFormattedMessage>true</withFormattedMessage>
    <withMessage>false</withMessage>
    <withArguments>false</withArguments>
</encoder>
```

Khi đó field `formattedMessage` được xuất, còn raw `message` và `arguments` bị tắt theo thiết lập. Đây là ví dụ có chủ ý: với mẫu `"orderId={}"` và tham số `"ord-17"`, formatted message là `"orderId=ord-17"`; raw message vẫn là `"orderId={}"`. Tùy pipeline, giữ cả hai hoặc chỉ một.

**Đừng khẳng định encoder gốc là encoder Logstash**: tên trường, cách trình bày MDC và KVP, timestamp và exception có thể khác. Nếu collector yêu cầu schema riêng, cần map schema hoặc chọn encoder phù hợp.

### 5.2. `net.logstash.logback.encoder.LogstashEncoder` — encoder ngoài với schema linh hoạt

Thư viện **logstash-logback-encoder** cung cấp `LogstashEncoder`, `LoggingEventCompositeJsonEncoder` và các thành phần khác. Các tính năng thường dùng:

- JSON có các field mặc định kiểu Logstash, ví dụ `@timestamp`, `message`, `logger_name`, `thread_name`, `level`.
- Cấu hình field chung của service (ví dụ `service`, `environment`).
- Lọc/đổi tên một số khóa MDC.
- Xuất key-value pairs của SLF4J 2 theo cách hỗ trợ structured fields.
- Composite JSON providers để định nghĩa schema cụ thể.
- Cấu hình stack trace, masking/escaping và giới hạn event theo khả năng phiên bản.

Ví dụ **mảnh cấu hình encoder trong Appender**:

```xml
<encoder class="net.logstash.logback.encoder.LogstashEncoder">
    <timeZone>UTC</timeZone>
    <customFields>{"service":"checkout","environment":"prod"}</customFields>
    <includeMdcKeyName>traceId</includeMdcKeyName>
    <includeMdcKeyName>requestId</includeMdcKeyName>
</encoder>
```

Đây là cấu hình dành cho thư viện bổ sung; nó **không chạy chỉ với JDK hoặc Logback gốc**. Cần dependency `net.logstash.logback:logstash-logback-encoder` tương thích, trong đó version **8.1** làm việc với Java 11+ và họ Logback 1.5.x, Jackson 2.x; 9.x chuyển sang Jackson 3 và đòi Java 17+. Khi nâng major cần đối chiếu ma trận tương thích, không chỉ đổi số phiên bản.

`includeMdcKeyName` là **allowlist các khóa MDC được xuất** trong LogstashEncoder; các khóa không liệt kê bị loại khỏi phần MDC output. Đây là kiểm soát hữu ích, nhưng không thay việc **không đưa secret vào message, throwable hoặc field khác**.

### 5.3. `LoggingEventCompositeJsonEncoder` khi cần schema tùy chỉnh

Composite encoder hoạt động với **JSON providers**. Có thể kết hợp `timestamp`, `logLevel`, `loggerName`, `message`, `mdc`, `arguments`, `keyValuePairs`, `stackTrace` hoặc provider tùy chỉnh theo khả năng phiên bản thư viện.

Cấu hình minh họa:

```xml
<encoder class="net.logstash.logback.encoder.LoggingEventCompositeJsonEncoder">
    <providers>
        <timestamp/>
        <logLevel/>
        <loggerName/>
        <threadName/>
        <mdc/>
        <message/>
    </providers>
</encoder>
```

Đây là **mảnh cấu hình** chứ không phải một `logback.xml` hoàn chỉnh. Composite encoder không nên được giả định tự thêm mọi field mặc định; bạn phải chủ động chọn providers cần thiết. Khi dùng provider pattern có nội dung JSON, cần tuân thủ cấu trúc JSON mà provider hỗ trợ và thử output, không tùy tiện nối `%msg` vào chuỗi JSON thủ công.

### 5.4. Bảng lựa chọn

| Nhu cầu | Lựa chọn đáng cân nhắc |
| --- | --- |
| Logback mới, cần JSON Lines hợp lệ và chấp nhận schema gốc | Logback `JsonEncoder` |
| Muốn fields mặc định kiểu Logstash và nhiều tùy chọn MDC/KVP | `LogstashEncoder` từ thư viện bổ sung |
| Muốn định nghĩa rõ từng field/provider và schema | `LoggingEventCompositeJsonEncoder` hoặc encoder chuyên dụng |
| Chỉ cần text dễ đọc | `PatternLayoutEncoder`, chưa nhất thiết cần JSON |
| Ứng dụng do framework quản lý logging/structured logging | Ưu tiên cơ chế framework hỗ trợ tương thích phiên bản |
| Ứng dụng chỉ dùng JUL và không thêm thư viện ngoài | Custom `Formatter` có JSON serializer đáng tin hoặc pipeline JUL phù hợp |

Một hệ thống có thể có **hai Appender với hai encoder khác nhau**, ví dụ console text cho người phát triển và file JSONL cho collector. Cần quản lý việc **duplicate ingestion** nếu cả hai đích được collector đọc như nguồn sự kiện độc lập.

## 6. Ví dụ đầy đủ: Java 17 + Logback JsonEncoder + kiểm tra bằng Jackson

Bài thực hành sử dụng **Java 17**, Gradle, SLF4J 2.0.17, Logback Classic 1.5.18 và Jackson Databind 2.17.2 để **đọc kiểm tra** JSON đã xuất. JSON encoder là **thành phần gốc của Logback**; Jackson Databind trong dự án demo được dùng ở phía đọc/test, không phải yêu cầu bắt buộc của ví dụ XML để encode.

Mục tiêu:

1. Dùng Logback `JsonEncoder` ghi từng event vào `build/events.jsonl`.
2. Bật `formattedMessage`, tắt raw `message` và `arguments`.
3. Tạo event INFO với key-value pair số `durationMs=125` và MDC `requestId=req-42`.
4. Tạo WARN chứa dấu nháy kép và **newline thực** trong message để thử JSON escaping.
5. Tạo ERROR có `Throwable` để kiểm tra cấu trúc exception.
6. Đọc lại ba dòng bằng JSON parser, xác nhận fields và in **stdout xác định**, không phụ thuộc clock/sequence/stack trace.

### 6.1. Cấu trúc thư mục

```text
json-encoder-demo/
  settings.gradle
  build.gradle
  src/
    main/
      java/
        demo/
          JsonEncoderDemo.java
      resources/
        logback.xml
```

### 6.2. File `settings.gradle`

```groovy
rootProject.name = 'json-encoder-demo'
```

### 6.3. File `build.gradle` (Groovy DSL)

```groovy
plugins {
    id 'application'
}

repositories {
    mavenCentral()
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

dependencies {
    implementation 'org.slf4j:slf4j-api:2.0.17'
    runtimeOnly 'ch.qos.logback:logback-classic:1.5.18'

    // Chỉ dùng để parse và kiểm tra JSON trong chương trình demo.
    implementation 'com.fasterxml.jackson.core:jackson-databind:2.17.2'
}

application {
    mainClass = 'demo.JsonEncoderDemo'
}
```

Các phiên bản được **cố định cho bài thực hành**, không phải khẳng định phiên bản mới nhất. Ở dự án thật, sử dụng version management/BOM và bản cập nhật bảo mật phù hợp. Chỉ có **một SLF4J provider** tại runtime, ở đây là Logback.

### 6.4. File `src/main/resources/logback.xml`

```xml
<configuration>
    <appender name="JSON_FILE" class="ch.qos.logback.core.FileAppender">
        <file>build/events.jsonl</file>
        <append>false</append>
        <immediateFlush>true</immediateFlush>

        <encoder class="ch.qos.logback.classic.encoder.JsonEncoder">
            <withFormattedMessage>true</withFormattedMessage>
            <withMessage>false</withMessage>
            <withArguments>false</withArguments>
        </encoder>
    </appender>

    <root level="INFO">
        <appender-ref ref="JSON_FILE"/>
    </root>
</configuration>
```

Phân tích:

- `FileAppender` ghi vào `build/events.jsonl`, nằm trong thư mục build do Gradle sử dụng.
- `append=false` giúp lần chạy tiếp theo không cộng dồn dữ liệu từ lần trước.
- `immediateFlush=true` khiến mỗi event được flush ra stream trước khi chương trình đọc kiểm tra. Điều này **không** phải cam kết fsync/durability khi mất điện.
- `JsonEncoder` ghi event ở JSON Lines, một record mỗi dòng.
- Các thuộc tính `withFormattedMessage`, `withMessage`, `withArguments` làm rõ sự khác nhau giữa message template, arguments và message đã format.
- Root level INFO cho phép INFO/WARN/ERROR; DEBUG bị chặn.
- Appender không in log ứng dụng ra stdout, nên output console của demo chỉ chứa các dòng kiểm tra chủ động.

### 6.5. File `src/main/java/demo/JsonEncoderDemo.java`

```java
package demo;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.slf4j.MDC;

public final class JsonEncoderDemo {
    private static final Logger LOG =
            LoggerFactory.getLogger(JsonEncoderDemo.class);

    public static void main(String[] args) throws Exception {
        String previous = MDC.get("requestId");
        try {
            MDC.put("requestId", "req-42");

            LOG.atInfo()
                    .addKeyValue("durationMs", 125)
                    .log("event=order.created orderId={}", "ord-17");

            LOG.warn("event=client.input value={}",
                    "quote=\"A\"\nnext");

            LOG.error("event=payment.failed",
                    new IllegalStateException("upstream unavailable"));
        } finally {
            if (previous == null) {
                MDC.remove("requestId");
            } else {
                MDC.put("requestId", previous);
            }
        }

        Path file = Path.of("build/events.jsonl");
        List<String> lines = Files.readAllLines(
                file, StandardCharsets.UTF_8);

        if (lines.size() != 3) {
            throw new IllegalStateException(
                    "Expected 3 JSON lines, got " + lines.size());
        }

        ObjectMapper mapper = new ObjectMapper();
        JsonNode info = mapper.readTree(lines.get(0));
        JsonNode warning = mapper.readTree(lines.get(1));
        JsonNode failure = mapper.readTree(lines.get(2));

        if (!info.isObject() || !warning.isObject()
                || !failure.isObject()) {
            throw new IllegalStateException(
                    "Every line must contain a JSON object");
        }

        require("INFO".equals(info.path("level").asText()),
                "info.level");
        require("event=order.created orderId=ord-17".equals(
                info.path("formattedMessage").asText()),
                "info.formattedMessage");
        require("req-42".equals(
                info.path("mdc").path("requestId").asText()),
                "info.requestId");

        JsonNode pairs = info.path("kvpList");
        require(pairs.isArray() && pairs.size() == 1
                && pairs.get(0).path("durationMs").asInt() == 125,
                "info.durationMs");

        String expectedMessage =
                "event=client.input value=quote=\"A\"\nnext";
        require(expectedMessage.equals(
                warning.path("formattedMessage").asText()),
                "warning.escapedMessage");

        require("WARN".equals(warning.path("level").asText()),
                "warning.level");
        require("ERROR".equals(failure.path("level").asText()),
                "failure.level");
        require(failure.path("throwable").isObject(),
                "failure.throwable");

        System.out.println("records=3");
        System.out.println("first.level=INFO");
        System.out.println("first.requestId=req-42");
        System.out.println("first.durationMs=125");
        System.out.println("second.escapedMessageRoundTrip=true");
        System.out.println("third.hasThrowable=true");
    }

    private static void require(
            boolean condition,
            String label) {
        if (!condition) {
            throw new IllegalStateException(
                    "JSON validation failed: " + label);
        }
    }
}
```

Code trên chỉ import SLF4J ở phần logging; nó dùng Jackson để **kiểm tra dữ liệu đã được encode**. `LOG.atInfo().addKeyValue(...)` là API fluent của SLF4J 2. Trong cấu trúc gốc của `JsonEncoder`, các key-value pairs có thể xuất trong field `kvpList`; chương trình kiểm tra giá trị số mà event mang theo.

### 6.6. Biên dịch/chạy

Trong thư mục `json-encoder-demo`, dùng **JDK 17** và Gradle tương thích:

```bash
gradle run --quiet
```

Nếu dự án có Gradle Wrapper, dùng `./gradlew run --quiet` trên Linux/macOS hoặc `gradlew.bat run --quiet` trên Windows. Các file ở đây chưa kèm Wrapper, nên cần Gradle/JDK sẵn có và quyền tải thư viện Maven Central.

**stdout dự kiến của chương trình khi XML và dependency khớp:**

```text
records=3
first.level=INFO
first.requestId=req-42
first.durationMs=125
second.escapedMessageRoundTrip=true
third.hasThrowable=true
```

Tại sao stdout có thể xác định?

- Chương trình **không in JSON thô** chứa timestamp, sequence number, đường dẫn stack trace hay context biến đổi.
- Nó kiểm tra số physical lines, parse từng JSON object, so sánh các trường mang ý nghĩa với giá trị dự kiến, rồi in kết quả.
- Dòng WARN chứa ký tự nháy kép và newline trong Java String; sau encode → đọc JSON → parse, thông điệp vẫn **round-trip** chính xác.
- Event ERROR mang `Throwable`, encoder thể hiện ở cấu trúc JSON; chương trình chỉ kiểm tra sự hiện diện, không so sánh stack trace theo số dòng JVM.
- Đường dẫn output là `build/events.jsonl`, và `append=false` tránh tồn đọng event từ lần chạy trước.

Khi cấu hình sai hoặc JSON output không đúng yêu cầu, chương trình **ném exception thay vì in đủ sáu dòng như trên**. Đây là lợi ích của một bài kiểm chứng có assertions.

### 6.7. File JSON thực tế trông như thế nào?

Trong `build/events.jsonl`, mỗi dòng là **một JSON object dày đặc (compact)**. Minh họa **chỉ trích các trường quan trọng**, bỏ qua các field còn lại và giá trị timestamp động:

```json
{
  "level": "INFO",
  "loggerName": "demo.JsonEncoderDemo",
  "mdc": {"requestId": "req-42"},
  "formattedMessage": "event=order.created orderId=ord-17",
  "kvpList": [{"durationMs": 125}]
}
```

**Không dùng khối minh họa này để thay thế output nguyên văn**: JsonEncoder thật còn có các trường được bật mặc định như timestamp, context, sequence; output của nó được ghi gọn trên một dòng.

Với WARN có newline logic, file JSON chứa chuỗi escape `\n` thay vì xuống dòng vật lý ở giữa JSON object. Parser Jackson đọc lại và phục hồi newline đúng; vì vậy `Files.readAllLines` đếm **ba record**, không phải bốn.

### 6.8. Thử nghiệm bổ sung

- **Thử bỏ `withFormattedMessage=true`:** vì field này mặc định tắt ở Logback 1.5.x, các assertions dựa vào `formattedMessage` không còn pass.
- **Thử bật lại `withMessage=true`:** JSON có thêm raw message template, giúp phân biệt `"orderId={}"` với formatted string.
- **Thử đổi root từ INFO thành ERROR:** hai event INFO/WARN bị loại; chương trình kiểm tra số record thất bại. Đây là **filtering**, không phải lỗi encoder.
- **Thử bỏ MDC:** field `requestId` không còn mang giá trị mong đợi; chương trình chỉ ra kiểm tra context thất bại.
- **Thử đổi output từ FileAppender sang ConsoleAppender:** JSON được in stdout; khi đó output không còn sáu dòng kiểm chứng thuần và cần thay chiến lược xác minh.
- **Thử log object lớn:** đánh giá cách serialize, giới hạn kích thước event, khả năng lọt dữ liệu nhạy cảm và tác động lên hiệu năng.

## 7. Dùng key-value fields thay vì nhét mọi thứ vào message

Hai cách sau có ý nghĩa khác nhau:

**Message tự do:**

```java
log.info("durationMs={} success={}", 125, true);
```

Đây là **mảnh mã minh họa**, giả sử `log` đã tồn tại. Backend có thể chỉ thấy formatted message `"durationMs=125 success=true"` và không tự tạo field số/boolean riêng.

**SLF4J 2 fluent key-values:**

```java
log.atInfo()
        .addKeyValue("durationMs", 125)
        .addKeyValue("success", true)
        .log("event=request.completed");
```

Các key-value pairs được gắn với event ở mức API. **Cách chúng xuất thành JSON phụ thuộc encoder**: Logback JsonEncoder gốc có thể đặt chúng trong `kvpList`, còn LogstashEncoder có thể viết các cặp trực tiếp như fields trên JSON object theo cấu hình.

Đừng chỉ dựa vào tên method `addKeyValue` để kết luận field chắc chắn nằm ở top-level. Cần đọc JSON thực và đối chiếu schema collector. Nếu muốn các field có kiểu `number`, `boolean`, `object`, nên kiểm thử kiểu trong parser giống ví dụ ở mục 6.

### 7.1. Tránh field collision

Một JSON object có thể vô tình nhận hai field cùng tên từ nhiều nguồn:

- Trường chuẩn `level`/`message` do encoder.
- Field tùy chỉnh từ `customFields`.
- MDC `level` hoặc `message` do mã ứng dụng đặt.
- SLF4J key-value pair trùng tên chuẩn.

JSON cho phép parser xử lý duplicate keys theo cách khác nhau; nhiều parser chọn giá trị cuối hoặc đầu, dẫn đến dữ liệu không thống nhất. **Đặt quy tắc phân quyền field names**, ví dụ prefixed context trong `labels`/`mdc` hoặc allowlist/rename keys khi dùng LogstashEncoder. Cần test duplicate keys và schema mapping của collector thực.

### 7.2. Field cardinality

`requestId`/`traceId` là field có nhiều giá trị khác nhau: hữu ích để tìm log riêng lẻ nhưng không phải một nhãn metric phù hợp để nhóm vô hạn. `event`, `service`, `environment` nên có danh mục tương đối ổn định để query và cảnh báo. Đừng biến mọi ID động thành tên field hoặc tên logger.

## 8. MDC và correlation ID

MDC thường được dùng để gắn context cho thread hiện tại:

```java
String previous = MDC.get("traceId");
try {
    MDC.put("traceId", "trace-abc");
    logger.info("event=payment.started");
} finally {
    if (previous == null) {
        MDC.remove("traceId");
    } else {
        MDC.put("traceId", previous);
    }
}
```

Đây là **mảnh code**, giả sử `logger` đã có và import `org.slf4j.MDC`. Với Logback JsonEncoder gốc, thông tin MDC có thể nằm ở object `mdc`; LogstashEncoder có thể xuất từng entry theo cách khác, tùy cấu hình. Không coi tất cả JSON encoder đều dùng cùng một đường dẫn `mdc.traceId`.

**Thread pool và async:** MDC không tự lan truyền qua mọi `ExecutorService`, `CompletableFuture` hoặc reactive pipeline. Nếu request chuyển thread, cần capture/propagate/restore context bằng cơ chế được hỗ trợ. Mỗi task cũng phải cleanup để request sau không kế thừa nhầm trace ID.

**Bảo mật:** ID lấy từ header ngoài cần giới hạn độ dài và ký tự, xác minh nguồn tạo và chỉ dùng như correlation data. Không đưa access token, session cookie, user profile hay toàn bộ HTTP header vào MDC chỉ vì encoder hỗ trợ xuất nó.

## 9. Throwable, stack trace và JSON

Một event ERROR có exception:

```java
try {
    gateway.call();
} catch (RuntimeException ex) {
    logger.error("event=payment.failed errorCode={}",
            "GATEWAY_TIMEOUT", ex);
}
```

Đây là mảnh mã minh họa với `gateway` và `logger` đã định nghĩa. Khi overload nhận Throwable đúng cách, backend có thể giữ exception trong logging event; JSON encoder sẽ quyết định biểu diễn thành:

- Object chứa class name, message và danh sách frame.
- Chuỗi stack trace đã escape newline.
- Trường giới hạn chiều sâu hoặc các thông tin gộp theo cấu hình encoder.

**Không giả định mọi encoder sinh field `stack_trace` hoặc `throwable` theo cùng kiểu.** Ví dụ Logback JsonEncoder gốc có cấu trúc `throwable`; LogstashEncoder mặc định có field `stack_trace` nếu có Throwable. Trước khi xây dashboard hoặc parser, hãy xem JSON thực tại phiên bản triển khai.

Với JSON Lines, ngay cả khi exception có nhiều stack frames, encoder cần bảo toàn **một JSON object trên một dòng vật lý** bằng escaping hoặc object/array nested. Không thêm raw `printStackTrace` vào stdout cùng luồng JSON Lines.

Một message exception có thể chứa URL, username hoặc payload nhạy cảm; encoder JSON **không tự bảo đảm dữ liệu đã được redaction**. Cần loại thông tin không được phép ngay lúc tạo event và kiểm tra chính sách masking ở backend.

## 10. Kiểm soát field và schema trong production

### 10.1. Giữ version/schema rõ ràng

Nếu hệ thống downstream sử dụng JSON fields để tạo alert, việc đổi encoder hoặc sửa tên field có thể khiến query trống dù ứng dụng vẫn chạy. Ví dụ khi chuyển:

```text
Logback JsonEncoder: loggerName, timestamp (numeric), mdc {...}
LogstashEncoder:     logger_name, @timestamp (string), MDC theo cấu hình
```

Đây là **minh họa hai family schema**, không mô tả toàn bộ tùy chọn. Khi đổi, cần đồng thời xem:

1. Thời điểm và timezone có cùng cách biểu diễn?
2. Tên level có giữ cùng giá trị?
3. `requestId` được chuyển từ object nested sang top-level không?
4. Field chứa formatted message còn hay đổi tên?
5. Throwable chuyển thành object/array hay string?
6. Các key-value numbers/booleans có còn đúng kiểu?
7. Collector có mapping theo schema mới và xử lý dữ liệu cũ không?

Nên đưa các thay đổi schema qua kiểm thử tích hợp rồi rollout có kiểm soát. Một trường `schemaVersion` có thể hữu ích khi pipeline thay đổi nhiều lần.

### 10.2. Dùng allowlist thay vì dump mọi thứ

Không nên serialize toàn bộ domain entity bằng `toString()` hay object-to-JSON khi entity có nhiều field không kiểm soát. Ưu tiên các trường rõ mục đích như `event`, `errorCode`, `durationMs`, `attempt`, `requestId` và metadata hệ thống.

JSON encoder có thể hoạt động với rất nhiều loại object, nhưng **khả năng serialize không phải quyền được ghi**. Dữ liệu sensitive có thể xuất từ MDC, throwable, SLF4J key-value, marker hoặc customFields; che một nguồn không xử lý mọi nguồn.

### 10.3. Dung lượng và tốc độ

JSON có thêm tên trường lặp lại mỗi event nên có thể tốn nhiều byte hơn log text ngắn. Encoding cũng có chi phí CPU và allocation. Trong production cần cân nhắc:

- Chỉ log các field phục vụ truy vấn/chẩn đoán.
- Hạn chế caller class/method/line vì có thể cần đi qua stack và khá tốn.
- Giới hạn kích thước message, payload và stack trace.
- Không serialise object mutable/phức tạp khi không cần.
- Đo throughput với Appender/encoder/collector thực tế.
- Dùng async có kiểm soát queue, discard, blocking và shutdown.
- Xem lại chi phí index và retention của collector.

**JSON encoder không làm logging “bất đồng bộ” tự động.** Việc ghi sync hay async phụ thuộc Appender/transport. Một event được chấp nhận/encode cũng chưa chắc đã được fsync hoặc collector xác nhận lưu bền vững.

## 11. JSON encoder và môi trường container

Trong Docker/Kubernetes, một mô hình thường hiệu quả:

```text
Application (SLF4J + Logback)
    -> ConsoleAppender + JSON encoder
    -> stdout: JSON Lines
    -> container runtime / log agent
    -> collector/parser
    -> search, dashboard, alert
```

Ưu điểm là không phải quản lý `RollingFileAppender` ở từng pod; platform có thể gắn metadata như instance/pod/namespace. Nhưng vẫn cần:

- Đảm bảo collector biết line format (NDJSON/JSONL).
- Tách stdout của ứng dụng khỏi text warning khởi tạo/launcher nếu parser nghiêm ngặt.
- Không in banner, debug `System.out.println` hoặc stack trace text lên cùng stream JSON.
- Tránh double-ingest khi đồng thời ghi file JSON và console JSON.
- Kiểm soát rotation/retention ở collector và storage, không kỳ vọng encoder tự làm nhiệm vụ này.
- Giám sát khi output backpressure, queue đầy, network lỗi hoặc pod bị terminate trước khi flush.

Nếu một môi trường khác cần file, có thể sử dụng **cùng JSON encoder trong FileAppender hoặc RollingFileAppender**. Chức năng rotation/retention thuộc Appender/RollingPolicy, không thuộc encoder.

## 12. Lỗi phổ biến và cách chẩn đoán

| Hiện tượng | Nguyên nhân có thể | Hướng kiểm tra |
| --- | --- | --- |
| Tên file là `.json` nhưng nội dung chỉ là text | Appender vẫn dùng `PatternLayoutEncoder` | Gắn JSON encoder đúng class |
| Collector báo JSON parse error | Nhiều dòng text trộn với JSON hoặc output tự nối không escape | Xem raw bytes, một object/line và nguồn stdout/stderr |
| Message có `{ }` nguyên mẫu | Đang xem raw `message` thay vì `formattedMessage` | Bật field phù hợp, kiểm tra overload và arguments |
| `formattedMessage` không có trong JSON gốc | Logback 1.5 mặc định không bật field này | Cấu hình `withFormattedMessage=true` |
| Field `durationMs` bị string | Đưa số vào MDC hoặc message text | Dùng typed key-value/provider và kiểm tra JSON types |
| Không thấy `requestId` | MDC chưa được gắn, mất khi đổi thread hoặc encoder không xuất key | Kiểm tra context propagation và cấu hình MDC |
| `WARN`/`DEBUG` không xuất | Logger/Appender level hoặc filter loại event | Kiểm tra logging pipeline trước encoder |
| Có field `level` lặp | Collision giữa chuẩn và custom/MDC/KVP | Đổi tên, nested context, allowlist |
| Cấu hình LogstashEncoder nhưng class not found | Thiếu artifact hoặc phiên bản không tương thích | Kiểm tra dependency/version và runtimeClasspath |
| Sau khi nâng 9.x gặp lỗi Jackson | Thay đổi major Jackson 2 → 3 | Xem compatibility notes và quản lý dependency |
| Stack trace bị tách thành nhiều record | In text `printStackTrace` ngoài stream JSON | Dùng JSON throwable fields hoặc collector multiline hợp lệ |
| Logback config không có tác dụng | Runtime backend không phải Logback | Xác định SLF4J provider và file config thực sự nạp |
| JSON có timestamp khác mong đợi | Encoder dùng epoch ms thay ISO, timezone khác | Chuẩn hóa schema và unit thời gian |
| Log bị lặp ở collector | Hai Appender/bridge/additivity hoặc ingest cả file + stdout | Xem đường đi event và nguồn ingest |
| JSON xuất đúng nhưng mất log lúc tải cao | Appender async/drop hoặc collector bị nghẽn | Kiểm tra queue, policy discard, shutdown/flush |
| Secret có trong file JSON | Serialize quá nhiều dữ liệu/MDC/Throwable | Giảm dữ liệu ngay ở nguồn, masking và quyền đọc |

### Quy trình điều tra theo thứ tự

1. Xác định runtime đang dùng **JUL, Logback, Log4j 2** hay backend khác; không áp nhầm config.
2. Kiểm tra Logger level/filter và Appender thực sự nhận event.
3. Xác nhận **encoder class** được cấu hình, không chỉ nhìn extension của file.
4. Kiểm tra mỗi physical line parse thành một JSON object bằng JSON parser chuẩn.
5. Kiểm tra tên field và **kiểu dữ liệu** trên event INFO/WARN/ERROR thật.
6. Thử message chứa dấu quote, backslash, Unicode và newline; kiểm tra round-trip sau parse.
7. Thử Throwable và MDC/trace ID; xác minh không mất context khi qua async.
8. Kiểm tra cấu hình schema/collector/mapping, khả năng duplicate ingestion và retention.
9. Test tải cao, restart và shutdown để hiểu buffering/flush/durability.

## 13. Checklist triển khai JSON encoder

- [ ] Xác định mục tiêu là text dễ đọc hay **JSON Lines dành cho máy parse**.
- [ ] Chọn backend/provider đúng và một encoder phù hợp với phiên bản thực tế.
- [ ] Phân biệt Logback JsonEncoder gốc, LogstashEncoder và Composite JSON encoder.
- [ ] Chỉ rõ message template/raw vs formatted message; không suy từ tên field.
- [ ] Có schema field tên/kiểu ổn định cho timestamp, level, logger, event, service, requestId/traceId, errorCode.
- [ ] Giữ number/boolean đúng kiểu; không đưa dữ liệu có kiểu vào message hoặc MDC rồi mong tự chuyển.
- [ ] Thử newline, quote, backslash và Unicode; mỗi event vẫn là một JSON object/line.
- [ ] MDC được khôi phục/cleanup và được propagate đúng qua executor/async.
- [ ] Exception được encode theo trường có thể parse; không in stack trace text vào stream JSON.
- [ ] Không đưa password/token/cookie hoặc payload nhạy cảm vào log.
- [ ] Có giới hạn event size, policy sampling, retention, masking và quyền đọc.
- [ ] Có validation parser thực tế và kiểm thử schema trước khi rollout.
- [ ] Phân biệt output encoder với vấn đề Appender buffering, network/backpressure và durability.
- [ ] Không double-ingest cùng event từ nhiều Appender hoặc file/console.
- [ ] Có giám sát parser errors, lost logs và disk/collector capacity.

### Nguồn tham khảo kỹ thuật

- [Logback Manual — Encoders](https://logback.qos.ch/manual/encoders.html): `Encoder<E>`, `JsonEncoder`, JSON Lines, `withFormattedMessage` và những field gốc.
- [Logback Manual — Appenders](https://logback.qos.ch/manual/appenders.html): ConsoleAppender, FileAppender và quá trình ghi output.
- [SLF4J Manual](https://www.slf4j.org/manual.html): logging facade, fluent API, key-value pairs và parameterized messages.
- [logstash-logback-encoder documentation](https://github.com/logfellow/logstash-logback-encoder): LogstashEncoder, Composite JSON providers, MDC allowlist và typed key-value fields.
- [Maven Central — logstash-logback-encoder 8.1](https://central.sonatype.com/artifact/net.logstash.logback/logstash-logback-encoder/8.1): ví dụ artifact thuộc nhánh Jackson 2/Logback 1.5.
- [RFC 8259 — The JSON Data Interchange Format](https://www.rfc-editor.org/rfc/rfc8259): cú pháp JSON, chuỗi và escape.
- [JSON Lines](https://jsonlines.org/): một JSON value trên mỗi dòng và UTF-8.

**Kết luận:** **JSON encoder** trong Java Logging chuyển event thành dữ liệu JSON/JSON Lines có cấu trúc để truy vấn và giám sát. Với Logback mới, `JsonEncoder` gốc đã hỗ trợ JSON Lines và có thể cấu hình các field như `formattedMessage`; với nhu cầu schema phong phú hơn, cân nhắc `LogstashEncoder` hoặc composite providers. Giá trị thật đến từ **schema ổn định, field đúng kiểu, context/exception rõ ràng, escaping an toàn và kiểm chứng parser**, không chỉ từ việc đặt đuôi file `.json`.
