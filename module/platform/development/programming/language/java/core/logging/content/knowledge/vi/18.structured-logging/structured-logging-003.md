# Schema log — Hợp đồng dữ liệu cho Structured Logging trong Java

## 1. Schema log là gì?

**Schema log** là tập quy tắc mô tả **cấu trúc, kiểu dữ liệu và ngữ nghĩa** của một sự kiện log: field nào bắt buộc, field nào tùy chọn, tên và kiểu từng field, đơn vị đo, tập giá trị hợp lệ, cách biểu diễn timestamp, lỗi, ngữ cảnh và cách thay đổi qua các phiên bản.

Một log có thể phục vụ hai nhóm độc giả:

- **Con người:** đọc message, exception và ngữ cảnh để hiểu sự cố.
- **Máy xử lý:** parser, collector, truy vấn, dashboard, alert và hệ thống quan sát cần những trường có hợp đồng ổn định.

Ví dụ cùng loại sự kiện nhưng dữ liệu khác nhau:

~~~json
{"schemaVersion":1,"timestamp":"2026-11-09T10:15:00.125Z","level":"INFO","service":"checkout-api","event":"order.created","requestId":"req-001","durationMs":18,"message":"Order accepted"}
{"schemaVersion":1,"timestamp":"2026-11-09T10:15:02.500Z","level":"INFO","service":"checkout-api","event":"order.created","requestId":"req-002","durationMs":32,"message":"Order accepted"}
~~~

Hai dòng trên là **dữ liệu minh họa**. Giá trị thay đổi theo request, nhưng **field name, data type, unit và event semantics** không thay đổi. Đó là đặc tính của schema ổn định.

**Schema log không bắt buộc phải là JSON**, dù JSON Lines là một cách xuất thuận tiện. Có thể có một schema cho logfmt/key=value hoặc protocol khác; điều quan trọng là producer và consumer cùng hiểu một hợp đồng.

### Schema khác layout/formatter thế nào?

| Khái niệm | Chức năng | Ví dụ |
| --- | --- | --- |
| Log event/record | Dữ liệu sự kiện trong bộ nhớ trước khi xuất | Level, message, logger, timestamp, Throwable |
| Schema | Tên field, kiểu, ngữ nghĩa, đơn vị, bắt buộc/tùy chọn | durationMs là number; errorCode là string |
| Format/serialization | Cách biểu diễn thành chuỗi hoặc byte | JSON Lines, text pattern, logfmt |
| Formatter/Layout/Encoder | Thành phần phần mềm tạo output | JUL Formatter; Logback PatternLayoutEncoder |
| Handler/Appender | Ghi tới đích | Console, file, remote collector |
| Collector/parser | Nhận và hiểu bản ghi | JSON parser, index mapping, alert queries |

**Một dòng trông như JSON chưa chắc là structured log tốt:** nếu durationMs ở service A là số nhưng service B lại dùng chuỗi "18ms", hoặc service C gọi tên field khác, parser và aggregation vẫn gặp lỗi.

## 2. Vì sao nên thiết kế schema trước khi log nhiều?

Một dự án Java có thể bắt đầu với:

~~~text
Payment failed!
Could not pay for order ORD-42.
Timeout contacting gateway for order ORD-42.
~~~

Các message này có thể dễ đọc, nhưng rất khó xây dựng alert đáng tin dựa trên đúng câu chữ. Khi copy thay đổi theo framework, ngôn ngữ hoặc refactor, bộ lọc cũ có thể không nhận diện.

Schema giúp dùng một định danh ổn định:

~~~json
{"event":"payment.failed","errorCode":"UPSTREAM_TIMEOUT","orderId":"ORD-42","message":"Gateway did not respond"}
~~~

Lợi ích thực tế:

1. **Truy vấn chính xác:** lọc event=payment.failed và errorCode=UPSTREAM_TIMEOUT thay vì tìm câu message.
2. **Dashboard không phụ thuộc wording:** message có thể thay đổi mà số liệu không biến mất.
3. **Tương quan đa dịch vụ:** traceId, spanId và requestId có tên/kiểu nhất quán.
4. **Phân tích duration:** durationMs là số, có thể so sánh và tổng hợp.
5. **Quản lý schema evolution:** hai phiên bản ứng dụng phát log cùng lúc vẫn có chiến lược đọc.
6. **Bảo vệ dữ liệu:** định nghĩa allowlist và field nhạy cảm bị cấm ghi.
7. **Giảm chi phí parser:** ít định dạng tự chế, ít trường bất ngờ.
8. **Điều tra sự cố:** biết event nào xảy ra, khi nào, ở thành phần nào và kết quả ra sao.

Schema là **hợp đồng dữ liệu giữa ứng dụng phát log và các hệ thống tiêu thụ log**. Nó không tự bảo đảm sự kiện đã tới storage; level, appender, network và collector vẫn có thể mất bản ghi.

## 3. Đường đi của structured log

~~~text
Application code
       |
       v
SLF4J / JUL / Log4j 2 API
       |
       v
Log event + context + attributes
       |
       v
Backend: level / filters / appenders
       |
       v
Encoder / Formatter theo schema
       |
       v
JSON Lines / text / structured transport
       |
       v
stdout, stderr, file hoặc agent
       |
       v
Collector -> validation -> mapping
       |
       v
Search / Dashboard / Alert / Investigation
~~~

Có hai tầng cần kiểm soát:

**Producer:** ứng dụng và backend phải tạo trường đúng kiểu/ý nghĩa; encoder escape và biểu diễn event đúng.

**Consumer:** collector phải đọc đúng ranh giới event, mapping field đúng kiểu, chấp nhận version phù hợp và áp dụng retention, quyền truy cập.

Một schema đẹp trong tài liệu nhưng encoder thực tế không xuất các trường đó thì không có giá trị. Ngược lại, JSON hợp lệ mà collector chưa parse hoặc index vẫn có thể không được truy vấn theo field như kỳ vọng.

## 4. Event envelope — phần trường chung

Một schema thực tế thường chia thành:

- **Envelope chung:** các trường phục vụ mọi event, ví dụ schemaVersion, timestamp, level, service, event.
- **Trường theo loại event:** orderId, paymentMethod, durationMs, errorCode, retryable...
- **Ngữ cảnh tương quan:** requestId, traceId, spanId khi có.
- **Chi tiết chẩn đoán:** message và exception theo chính sách.

Bảng tham khảo:

| Field | Kiểu đề xuất | Bắt buộc? | Ý nghĩa |
| --- | --- | --- | --- |
| **schemaVersion** | integer | Có | Phiên bản hợp đồng log |
| **timestamp** | string RFC 3339 có timezone | Có | Thời điểm event được ghi nhận |
| **level** | string enum | Có | TRACE, DEBUG, INFO, WARN, ERROR theo quy ước normalize |
| **service** | string | Có | Tên ứng dụng/dịch vụ phát log |
| **event** | string | Có | Mã loại sự kiện ổn định |
| **message** | string | Theo hợp đồng | Mô tả cho con người |
| **logger** | string | Tùy chọn | Tên logger/class |
| **environment** | string | Tùy chọn | production, staging, development |
| **requestId** | string | Theo loại event | ID tương quan trong một yêu cầu |
| **traceId** | string | Khi có tracing | ID luồng xử lý phân tán |
| **spanId** | string | Khi có tracing | ID span của log event |
| **outcome** | string enum | Theo loại event | success, failure, retry, cancelled... |
| **errorCode** | string | Khi có mã lỗi | Mã lỗi ổn định, không phải exception message |
| **durationMs** | number | Event có thời lượng | Đơn vị millisecond |
| **retryable** | boolean | Event phù hợp | Có thể thử lại hay không |
| **exception** | object | Khi cần | Loại lỗi, cause, stack trace theo policy |

Đây là **đề xuất học tập**, không phải quy chuẩn duy nhất. Nếu tổ chức đã dùng tên trường từ nền tảng observability (ví dụ service.name hoặc trace_id), cần thống nhất theo hệ thống đó. Không tự tạo một bộ schema mới xung đột với chuẩn đã chọn.

### Bao nhiêu field là đủ?

**Không ép mọi event chứa mọi field.** Startup event có thể không có requestId, còn order.created nên có orderId. Event payment.failed có thể yêu cầu errorCode. Cần định nghĩa **required/optional theo event type**, không chỉ một bảng chung.

Một event bị lỗi không nên tạo hàng trăm field tùy hứng chỉ vì dữ liệu sẵn trong object. Nên ghi **trường có giá trị chẩn đoán** và đã được phép lưu.

## 5. Quy ước tên trường và cấu trúc

Chọn một kiểu đặt tên nhất quán:

- **camelCase:** requestId, errorCode, durationMs.
- **snake_case:** request_id, error_code, duration_ms.
- **Dotted names:** service.name, http.request.method, nếu chuẩn hiện có yêu cầu.

JSON có thể có key **"service.name"** dưới dạng một key chứa dấu chấm hoặc object lồng **{"service":{"name":"..."}}**; hai cấu trúc đó **không được tự coi là giống nhau**. Collector có thể có cách map khác nhau, cần đặc tả.

Tên trường phải phản ánh ý nghĩa:

- **durationMs** thay vì time, nếu đang đo millisecond.
- **httpStatusCode** thay vì status chung, nếu thực sự là HTTP status.
- **errorCode** thay vì error, nếu đó là mã nghiệp vụ.
- **requestId** khác customerId, transactionId hoặc traceId.
- **event** chứa mã loại sự kiện, không chứa ID động của từng request.

**Đừng đưa userId/orderId vào tên field**, như key user_123 hoặc event order.created.ORD-7, vì sẽ làm phình schema và mất khả năng nhóm đúng loại.

## 6. Kiểu dữ liệu, đơn vị và null semantics

### 6.1. Giữ kiểu nhất quán

~~~json
{"durationMs":18,"attempt":2,"retryable":true}
~~~

Khác hẳn về kiểu dữ liệu với:

~~~json
{"durationMs":"18ms","attempt":"2","retryable":"yes"}
~~~

Dòng thứ hai là JSON hợp lệ, nhưng có thể vi phạm schema đã quy định. Kiểu dữ liệu có ảnh hưởng đến so sánh, aggregation và validation.

| Field | Kiểu hợp đồng | Ví dụ hợp lệ | Ví dụ nên tránh |
| --- | --- | --- | --- |
| durationMs | number | 18, 18.5 | "18 ms" |
| sizeBytes | integer | 1048576 | "1MB" |
| attempt | integer | 2 | "second" |
| retryable | boolean | true | "true" |
| httpStatusCode | integer | 503 | "HTTP 503" |
| requestId | string | "req-0007" | 7 nếu làm mất số 0 đầu |
| outcome | string enum | "success" | "ok" nếu chưa định nghĩa |

Với identifier dài, nên xem xét biểu diễn dạng **string** để tránh mất độ chính xác ở hệ thống dùng number độ chính xác hữu hạn.

### 6.2. Missing, null và empty là ba trạng thái khác

~~~json
{"event":"order.created"}
{"event":"order.created","requestId":null}
{"event":"order.created","requestId":""}
~~~

Có thể quy định:

- **Thiếu field:** không áp dụng hoặc không có trong loại event này.
- **null:** field được định nghĩa nhưng giá trị chưa biết.
- **"" (chuỗi rỗng):** giá trị rỗng; với ID thường không hợp lệ.

Không có quy tắc bắt buộc cho mọi hệ thống; nhưng **producer và consumer phải đồng ý**. Không ghi chuỗi "null" khi muốn một JSON null thật.

### 6.3. Đơn vị nằm trong tên trường

**durationMs** là milliseconds; **sizeBytes** là bytes; **timeoutMs** là milliseconds. Không đổi durationMs từ 18 millisecond thành 18 second mà vẫn giữ tên field, vì đó là thay đổi ngữ nghĩa nghiêm trọng.

Khi cần timestamp có độ chính xác microsecond, hãy mô tả và kiểm tra rõ độ chính xác; không giả định mọi logger/backend hỗ trợ cùng precision.

## 7. Timestamp chuẩn và thứ tự sự kiện

Timestamp là trường quan trọng nhưng dễ gây lỗi khi nhiều JVM chạy ở các múi giờ khác nhau.

Nên dùng thời điểm có offset tường minh; **UTC với hậu tố Z** là lựa chọn phổ biến:

~~~json
{"timestamp":"2026-11-09T10:15:00.125Z"}
~~~

Quy định rõ:

1. **Event time hay ingestion time?** Thời điểm Java phát log khác thời điểm collector nhận bản ghi.
2. **Timezone:** UTC/Z hay offset cụ thể; tránh local time mơ hồ.
3. **Precision:** seconds, milliseconds, microseconds hay nanoseconds.
4. **Clock:** thời điểm do Java tạo, upstream gửi hay collector gắn.
5. **Thứ tự:** timestamps của hai host có thể không đủ xác định thứ tự tuyệt đối khi clock lệch.

Trong Java:

~~~java
String timestamp = java.time.Instant.now().toString();
~~~

Đây là **mảnh Java minh họa**. Instant.now() cho thời điểm trên thang UTC, nhưng định dạng phần giây có thể thay đổi theo precision; muốn chính xác ba chữ số milliseconds cần định dạng đã chọn và test. Đừng coi **LocalDateTime.now()** không có timezone là đủ cho log phân tán.

## 8. Event code và taxonomy

Nên dùng event code mô tả loại hành động/sự kiện, ví dụ domain.action:

~~~text
order.created
order.cancelled
payment.retry
payment.failed
job.started
job.completed
cache.miss
~~~

**Event code không phải giá trị duy nhất cho mỗi bản ghi.** Không dùng payment.failed.req-42; dùng:

~~~json
{"event":"payment.failed","requestId":"req-42"}
~~~

Nên mô tả ý nghĩa chính xác:

- **order.created:** đơn hàng đã được tạo theo hợp đồng nghiệp vụ (phân biệt tiếp nhận yêu cầu với commit thành công).
- **payment.retry:** có thao tác thử lại, chưa nhất thiết là thất bại cuối cùng.
- **payment.failed:** thao tác được coi là thất bại tại một ranh giới xác định.
- **job.completed:** job hoàn tất theo định nghĩa, có thể kèm outcome.

Dùng **message** để diễn giải cho con người, nhưng xây dựng query/alert trên event code, errorCode và field có nghĩa rõ ràng. Nếu đổi event semantics, cần đánh giá versioning thay vì giữ tên cũ để consumer hiểu sai.

## 9. ERROR, exception và stack trace

Một event lỗi có thể bao gồm **errorCode** ổn định và dữ liệu exception dành cho điều tra:

~~~json
{
  "schemaVersion": 1,
  "level": "ERROR",
  "service": "checkout-api",
  "event": "payment.failed",
  "errorCode": "UPSTREAM_TIMEOUT",
  "exception": {
    "type": "java.net.SocketTimeoutException",
    "message": "Gateway did not respond",
    "stackTrace": "java.net.SocketTimeoutException: Gateway did not respond\n    at demo.PaymentClient.call(PaymentClient.java:42)"
  }
}
~~~

Đây là **dữ liệu minh họa**. Trong JSON, newline bên trong string stackTrace đã được escape thành **\n**; không phải một dòng log text mới.

Một số quyết định cần thống nhất:

- errorCode dùng enum nghiệp vụ hay mã kỹ thuật?
- exception là object lồng hay các key phẳng như exception.type và exception.stacktrace?
- stackTrace có giới hạn kích thước không?
- có lưu cause chain không và xử lý lộ dữ liệu nhạy cảm thế nào?
- collector phải parse JSON Lines hay multiline text?

**Không dùng nội dung exception.message làm errorCode**: message có thể thay đổi theo thư viện, locale và chứa path/dữ liệu người dùng. Không ghi cùng Throwable ở mọi tầng nếu chỉ tạo stack trace trùng mà không thêm thông tin điều tra.

## 10. JSON Lines và ranh giới bản ghi

**JSON Lines** biểu diễn **mỗi log event thành một object JSON trên một dòng vật lý**, giúp collector xử lý stream tốt hơn text tự do:

~~~json
{"schemaVersion":1,"event":"order.created","message":"Order accepted"}
{"schemaVersion":1,"event":"payment.failed","message":"Gateway unavailable"}
~~~

Nếu một message chứa ký tự xuống dòng và dấu nháy:

~~~text
Gateway replied: "retry"
Check gateway
~~~

Thì encoder JSON phù hợp phải xuất thành:

~~~json
{"schemaVersion":1,"event":"payment.failed","message":"Gateway replied: \"retry\"\nCheck gateway"}
~~~

Ký hiệu **\n** ở trong JSON là escape cho newline thuộc giá trị message; object vẫn là **một dòng vật lý**. Dữ liệu do người dùng nhập có thể chứa quote, backslash, control characters và Unicode, nên **không tự ghép JSON bằng string concatenation mà không escape**.

Bên cạnh JSON hợp lệ còn cần:

- **Giới hạn kích thước event:** collector/driver có thể cắt record quá dài.
- **Đúng encoding:** thường UTF-8, từ encoder tới storage.
- **Ranh giới exception:** structured exception field hoặc multiline policy phải nhất quán.
- **Trường có kiểu:** JSON number, boolean, null phải đúng hợp đồng.
- **Parser ở collector:** không phải chỉ in JSON là mọi field tự được index.
- **Không dựa vào thứ tự key:** JSON object không quy định key order là ngữ nghĩa; consumer đọc theo tên.

JSON schema giúp tổ chức dữ liệu; nó **không tự cung cấp durability**. Một event được Logger gọi có thể bị level/filter loại, bị queue drop hoặc mất khi collector gặp lỗi.

## 11. Ví dụ Java 17 chạy được — SLF4J + Logback + Jackson

Ta tạo hai sự kiện JSON Lines có **schemaVersion, timestamp, level, service, logger, event, requestId, message**, và một số field đặc thù. Mã Java phát log bằng **SLF4J**, Logback ghi stdout, còn Jackson đảm nhận serialization/escaping.

**Giới hạn có chủ ý:** Đây là demo để học schema và output xác định, dùng Java tạo JSON trước khi gọi logger. Trong hệ thống production, nên ưu tiên **typed structured logging API và JSON encoder tích hợp ở backend** để lấy timestamp, level, Throwable và MDC tự động, thay vì yêu cầu mọi service tự dựng JSON bằng tay.

### 11.1. Cấu trúc dự án

~~~text
schema-log-demo/
├── pom.xml
└── src/
    └── main/
        ├── java/
        │   └── demo/
        │       └── SchemaLogDemo.java
        └── resources/
            └── logback.xml
~~~

### 11.2. pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>demo</groupId>
    <artifactId>schema-log-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.slf4j</groupId>
            <artifactId>slf4j-api</artifactId>
            <version>2.0.17</version>
        </dependency>
        <dependency>
            <groupId>ch.qos.logback</groupId>
            <artifactId>logback-classic</artifactId>
            <version>1.5.18</version>
        </dependency>
        <dependency>
            <groupId>com.fasterxml.jackson.core</groupId>
            <artifactId>jackson-databind</artifactId>
            <version>2.18.3</version>
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
                    <mainClass>demo.SchemaLogDemo</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
~~~

Các phiên bản ở trên chỉ là bộ phiên bản minh họa cụ thể, **không phải khẳng định mới nhất**. Với dự án thật, cần dependency management và kiểm tra bản vá bảo mật.

### 11.3. src/main/resources/logback.xml

~~~xml
<configuration>
    <appender name="STDOUT"
              class="ch.qos.logback.core.ConsoleAppender">
        <target>System.out</target>
        <encoder>
            <charset>UTF-8</charset>
            <pattern>%msg%n</pattern>
        </encoder>
    </appender>

    <root level="INFO">
        <appender-ref ref="STDOUT"/>
    </root>
</configuration>
~~~

Logback dùng **%msg%n** để in message và newline, không tự thêm level/timestamp ở ngoài JSON. Trong demo, field level/timestamp được đưa vào JSON để có output cố định. **Không coi đây là encoder JSON production toàn diện**.

### 11.4. src/main/java/demo/SchemaLogDemo.java

~~~java
package demo;

import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

import java.util.LinkedHashMap;
import java.util.Map;

public final class SchemaLogDemo {
    private static final Logger LOG =
            LoggerFactory.getLogger(SchemaLogDemo.class);
    private static final ObjectMapper JSON = new ObjectMapper();

    public static void main(String[] args)
            throws JsonProcessingException {
        Map<String, Object> created = event(
                "2026-11-09T10:15:00.125Z",
                "INFO", "order.created", "req-7",
                "Order accepted");

        created.put("orderId", "ORD-7");
        created.put("durationMs", 18);
        LOG.info("{}", JSON.writeValueAsString(created));

        Map<String, Object> failed = event(
                "2026-11-09T10:15:02.100Z",
                "ERROR", "payment.failed", "req-7",
                "Gateway replied: \"retry\"\nCheck gateway");

        failed.put("errorCode", "PAYMENT_TIMEOUT");
        failed.put("retryable", true);
        LOG.error("{}", JSON.writeValueAsString(failed));
    }

    private static Map<String, Object> event(
            String timestamp, String level, String event,
            String requestId, String message) {

        Map<String, Object> fields = new LinkedHashMap<>();
        fields.put("schemaVersion", 1);
        fields.put("timestamp", timestamp);
        fields.put("level", level);
        fields.put("service", "checkout-api");
        fields.put("logger", LOG.getName());
        fields.put("event", event);
        fields.put("requestId", requestId);
        fields.put("message", message);
        return fields;
    }
}
~~~

Các đối tượng **LinkedHashMap** giữ thứ tự chèn field, và Jackson với cấu hình trên xuất map theo thứ tự đó. Điều này chỉ nhằm dễ đọc/diff; **thứ tự key không phải một phần ngữ nghĩa của JSON schema**.

### 11.5. Biên dịch và chạy

Cần **JDK 17+**, Maven và các dependency có sẵn hoặc tải được:

~~~bash
mvn -q compile exec:java
~~~

Với đúng các file trên, **stdout do chương trình Java phát ra** (không tính thông tin riêng của Maven/runtime):

~~~json
{"schemaVersion":1,"timestamp":"2026-11-09T10:15:00.125Z","level":"INFO","service":"checkout-api","logger":"demo.SchemaLogDemo","event":"order.created","requestId":"req-7","message":"Order accepted","orderId":"ORD-7","durationMs":18}
{"schemaVersion":1,"timestamp":"2026-11-09T10:15:02.100Z","level":"ERROR","service":"checkout-api","logger":"demo.SchemaLogDemo","event":"payment.failed","requestId":"req-7","message":"Gateway replied: \"retry\"\nCheck gateway","errorCode":"PAYMENT_TIMEOUT","retryable":true}
~~~

Có **chính xác hai dòng vật lý**: Jackson đã escape quote và newline trong message lỗi. Nếu Maven hoặc terminal có output riêng, hãy phân biệt với hai dòng log nghiệp vụ dự kiến.

### 11.6. Giải thích

1. Hàm **event(...)** đặt các field envelope dùng chung.
2. **orderId/durationMs** chỉ thuộc event order.created; **errorCode/retryable** thuộc event payment.failed.
3. **durationMs=18** là số và **retryable=true** là boolean JSON thật, không phải string.
4. **ObjectMapper** serialize/escape đúng ký tự đặc biệt.
5. **LOG.info/LOG.error** quyết định level phát, trong khi field level được code demo nhập bằng tay; production nên để backend/encoder lấy level thực nhằm tránh bất nhất.
6. **ConsoleAppender** ghi stdout, phù hợp với collector chấp nhận JSON Lines khi được cấu hình.
7. **Timestamp cố định** chỉ để ví dụ có output tái lập. Production cần thời gian thực có timezone theo schema.
8. Mã không cung cấp bảo đảm audit/durability. Một lời gọi log vẫn có thể bị lọc, drop hoặc I/O fail.

### 11.7. Tại sao production nên dùng structured encoder?

Nếu mỗi service tự tạo JSON như demo, dễ có chỗ quên field, thêm field sai kiểu, nhập level khác backend, không xuất MDC/Throwable, hoặc tạo duplicate field. Cách quản lý tốt hơn là **shared typed event contract + structured logging API/encoder** đã thống nhất và có kiểm thử.

SLF4J 2.x hỗ trợ fluent key-value logging:

~~~java
// Mảnh minh họa bên trong lớp có LOG và biến orderId.
LOG.atInfo()
        .addKeyValue("event", "order.created")
        .addKeyValue("orderId", orderId)
        .addKeyValue("durationMs", 18)
        .log("Order accepted");
~~~

**Đây không phải chương trình độc lập.** API cung cấp key-value nhưng **không tự bảo đảm mọi backend/encoder sẽ xuất thành JSON hoặc collector đã index các trường**. Cần đúng provider, encoder và output validation.

## 12. JSON Schema để mô tả envelope

Một cách viết hợp đồng cho máy là **JSON Schema**. Ví dụ sau dùng cú pháp Draft 2020-12 để mô tả envelope chung; field nghiệp vụ cụ thể cần có schema bổ sung.

~~~json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "title": "ApplicationLogV1",
  "type": "object",
  "required": [
    "schemaVersion",
    "timestamp",
    "level",
    "service",
    "event",
    "message"
  ],
  "properties": {
    "schemaVersion": {
      "type": "integer",
      "const": 1
    },
    "timestamp": {
      "type": "string",
      "format": "date-time"
    },
    "level": {
      "type": "string",
      "enum": ["TRACE", "DEBUG", "INFO", "WARN", "ERROR"]
    },
    "service": {
      "type": "string",
      "minLength": 1
    },
    "event": {
      "type": "string",
      "minLength": 1
    },
    "message": {
      "type": "string"
    },
    "requestId": {
      "type": "string",
      "minLength": 1
    },
    "durationMs": {
      "type": "number",
      "minimum": 0
    },
    "retryable": {
      "type": "boolean"
    }
  },
  "additionalProperties": true
}
~~~

Một số lưu ý:

- **additionalProperties=true** cho phép field riêng theo event. Nếu muốn chỉ cho phép một bộ trường, cần thiết kế event-specific schemas hoặc quy tắc kết hợp phù hợp.
- **format=date-time** có thể chỉ là annotation ở một số JSON Schema validators; nếu cần bắt lỗi timestamp thật, phải bật kiểm tra format hoặc bổ sung phép parse riêng.
- **required** kiểm tra sự hiện diện field, không tự bảo đảm event semantics đúng.
- **level enum** ở đây theo quy ước SLF4J/Logback; JUL có WARNING, SEVERE... nên cần normalize hoặc có schema khác khi thu từ JUL.
- Schema chưa kiểm tra **payment.failed bắt buộc errorCode**, loại dữ liệu PII, chiều dài trường hoặc propagation. Cần rule và test theo event.
- Giữ **schemaVersion** đúng với hợp đồng đang triển khai; đừng chỉ tăng số mà không chuyển consumer.

## 13. Kiểm thử JSON Lines và hợp đồng

Với ví dụ Maven, redirect stdout:

~~~bash
mvn -q compile exec:java > events.jsonl
~~~

Nếu Maven in output khác lên stdout, file có thể bị lẫn nội dung ngoài hai dòng JSON; cần kiểm tra log/console và cách chạy của môi trường. Trong production, ứng dụng thường xuất stream riêng theo cấu hình hạ tầng.

Có thể dùng Python 3 để parse từng dòng JSONL:

~~~bash
python3 -c 'import json; [json.loads(line) for line in open("events.jsonl", encoding="utf-8")]'
~~~

Lệnh không in gì nếu mọi dòng parse được; **đó chỉ là kiểm tra cú pháp JSON**, không phải kiểm tra mọi quy tắc schema.

Một script kiểm tra kiểu và tương quan:

~~~python
import json

with open("events.jsonl", encoding="utf-8") as stream:
    events = [json.loads(line) for line in stream if line.strip()]

assert len(events) == 2
assert all(event["schemaVersion"] == 1 for event in events)
assert all(isinstance(event["event"], str) for event in events)
assert all(event["level"] in {"TRACE", "DEBUG", "INFO", "WARN", "ERROR"}
           for event in events)
assert isinstance(events[0]["durationMs"], int)
assert isinstance(events[1]["retryable"], bool)
assert events[0]["requestId"] == events[1]["requestId"]
print("SCHEMA_CHECK_PASS")
~~~

Lưu thành **check_schema.py**, chạy:

~~~bash
python3 check_schema.py
~~~

Với file events.jsonl chứa đúng hai log của demo, **stdout**:

~~~text
SCHEMA_CHECK_PASS
~~~

Đoạn Python chỉ là **công cụ kiểm tra phụ trợ**, không phải dependency của Java. Trong một dự án Java có thể viết JUnit/Jackson validation tương tự. Nếu yêu cầu nhiều event và schema phức tạp, nên dùng JSON Schema validator có cấu hình thống nhất.

### Các loại kiểm thử nên có

- **Schema và kiểu:** required, null/missing, number, boolean, enum.
- **Timestamp:** UTC/offset, precision, parse đúng dưới các locale.
- **Escaping:** quote, newline, backslash, ký tự điều khiển và Unicode.
- **Exception:** stack trace không phá ranh giới một event JSONL.
- **MDC/correlation:** requestId/traceId được truyền/clear đúng scope.
- **Routing:** log không bị nhân đôi do additivity/handler và không bị lọc ngoài ý muốn.
- **Collector thực:** parser/indexer đọc đúng các trường và alert không mất dữ liệu khi deploy.
- **Versioning:** cả schema cũ và mới đều có đường xử lý phù hợp.
- **Bảo mật:** không đưa token, password hoặc raw request nhạy cảm vào field.
- **Kích thước:** record quá lớn được xử lý theo chính sách đã định.

**Golden test** hữu ích nhưng timestamp/threadId động phải được chuẩn hóa hoặc dùng Clock cố định; không bỏ timestamp production chỉ để test dễ. Với JSON, so object đã parse theo field thường bền hơn so thứ tự key.

## 14. Schema versioning và compatibility

Schema có thể thay đổi theo thời gian, nhưng nên phân loại rõ.

### Thay đổi thường dễ tương thích hơn

- Thêm field **tùy chọn** có kiểu và ý nghĩa đã mô tả.
- Thêm **event code mới** không đổi nghĩa event cũ.
- Thêm metadata mà consumer cũ được thiết kế để bỏ qua.
- Sửa wording của message khi query/alert không dựa vào literal text đó.

Ngay cả thay đổi additive cũng cần kiểm tra parser và mapping, vì một collector cũ có thể không chấp nhận field lạ hoặc field mới xung đột.

### Breaking changes

| Thay đổi | Hậu quả tiềm ẩn |
| --- | --- |
| durationMs=18 đổi thành "18ms" | Numeric aggregation hỏng |
| retryable=true đổi thành "yes" | Boolean query hỏng |
| requestId đổi thành request_id | Consumer cũ tìm sai field |
| outcome=success đổi thành ok | Enum/count sai |
| timestamp UTC chuyển local không offset | Truy vấn thời gian sai |
| JSONL một dòng chuyển multiline text | Parser hiểu sai ranh giới event |
| Bỏ field bắt buộc | Dashboard/validator lỗi |
| Đổi nghĩa payment.failed | Alert đếm sai loại sự kiện |
| Đổi field mà giữ schemaVersion=1 | Consumer không biết có breaking change |

### Quy trình migration an toàn

1. **Tài liệu hóa schema cũ và consumer đang dùng**: search, alert, dashboard, dữ liệu lưu lâu.
2. **Đánh giá thay đổi**: additive hay breaking; tên/kiểu/đơn vị/semantics đổi gì?
3. **Thiết kế schemaVersion và hợp đồng mới** nếu cần.
4. **Đảm bảo đường chuyển đổi**: ghi cả field cũ/mới tạm thời, collector normalize hoặc nhận hai version.
5. **Triển khai theo giai đoạn**: chuẩn bị consumer rồi mới loại producer cũ khi phù hợp.
6. **Theo dõi chất lượng**: parse error, missing field, unknown version, ingestion drop.
7. **Cập nhật test, documentation và query/alert**.
8. **Ngừng phiên bản cũ có kiểm soát**, không phá dữ liệu lịch sử.

**Chỉ có schemaVersion không tự chuyển dữ liệu.** Consumer phải biết đọc hoặc chuyển version tương ứng.

## 15. Correlation, MDC và tracing

Một request qua nhiều service có thể có:

~~~json
{"schemaVersion":1,"level":"INFO","service":"gateway","event":"request.accepted","requestId":"req-42"}
{"schemaVersion":1,"level":"INFO","service":"pricing","event":"price.calculated","requestId":"req-42"}
{"schemaVersion":1,"level":"ERROR","service":"payment","event":"payment.failed","requestId":"req-42","errorCode":"UPSTREAM_TIMEOUT"}
~~~

Đây là dữ liệu minh họa. Giữ cùng **field name/type** của requestId giúp điều tra theo yêu cầu; traceId và spanId nên theo chuẩn của tracing system đang chạy.

Với SLF4J/Logback, có thể dùng MDC:

~~~java
// Mảnh mã bên trong lớp đã có LOG:
try (org.slf4j.MDC.MDCCloseable ignored =
        org.slf4j.MDC.putCloseable("requestId", "req-42")) {
    LOG.info("event=order.created");
}
~~~

**MDC không tự động đi qua mọi thread pool, CompletableFuture hoặc reactive pipeline**. Cần context propagation và dọn đúng scope, tránh lẫn request ID giữa các tác vụ. **MDC cũng không tự bảo đảm field được encoder xuất ra JSON**; phải cấu hình backend thích hợp.

Đừng dùng requestId/traceId riêng lẻ làm metric label không giới hạn vì cardinality; chúng phù hợp hơn cho log và trace.

## 16. Schema phải tính đến kích thước, bảo mật và chi phí

### 16.1. Kích thước event

Một log có thể hợp lệ theo schema nhưng vẫn quá lớn để truyền/lưu, nhất là với stackTrace, payload và danh sách dữ liệu. Cần quy định:

- Giới hạn kích thước record/message và một số field có thể lớn.
- Chính sách truncate có tín hiệu (ví dụ truncated=true), tránh cắt mất event/errorCode/requestId.
- Cách xử lý exception dài hoặc nested object.
- Giới hạn cụ thể của runtime, agent, collector và log storage.
- Giám sát event bị reject, cắt hoặc drop.

Không có một con số byte phù hợp mọi tổ chức; giới hạn phải theo pipeline và tải thực tế.

### 16.2. Field explosion và cardinality

Không tạo key JSON động như:

~~~json
{"user_123":true,"user_124":false,"user_125":true}
~~~

Thay vào đó, nếu thật sự cần thông tin theo một đối tượng:

~~~json
{"event":"feature.checked","subjectId":"user-123","enabled":true}
~~~

Tuy nhiên, subjectId có thể vẫn là giá trị nhạy cảm/cardinality cao. Cần phân quyền, retention và cân nhắc có cần lập chỉ mục không. **Số lượng tên field phát sinh vô hạn** và **số giá trị khác nhau của một field** là hai vấn đề khác nhau; cả hai đều có thể gây chi phí.

### 16.3. Bảo mật

Không ghi **password, access token, API key, private key, cookie phiên, dữ liệu thẻ thanh toán hoặc thông tin cá nhân nhạy cảm** vào JSON log thô. Không mặc định ghi toàn bộ HTTP request/response hoặc object.toString().

- Xây dựng allowlist trường được phép xuất.
- Masking/redaction theo chính sách, kiểm thử ngay tại producer và trước nơi lưu.
- Escape dữ liệu không tin cậy chống phá cấu trúc/log injection.
- Hạn chế quyền đọc, thời gian lưu và luồng chia sẻ.
- Rà soát exception.message và stackTrace vì chúng có thể chứa thông tin nội bộ.

**JSON serializer chỉ giúp chuỗi hợp lệ, không tự che dữ liệu nhạy cảm.** Level DEBUG cũng không phải ranh giới bảo mật, vì có thể được bật bất ngờ trong sự cố.

### 16.4. Observability khác kho audit

Một lời gọi LOG.info(...) có thể bị lọc ở logger, appender, bị queue drop hoặc storage lỗi. Schema không tạo bảo đảm lưu bền vững. Nếu một sự kiện cần **được lưu như điều kiện của giao dịch**, hãy chọn hệ lưu trữ/audit có hợp đồng độ bền phù hợp; không dựa duy nhất vào pipeline log chẩn đoán.

## 17. Những lỗi thường gặp

| Sai lầm | Hậu quả | Cách tránh |
| --- | --- | --- |
| Không có event code | Query phụ thuộc câu message | Dùng event ổn định |
| durationMs lúc số lúc string | Aggregation sai | Giữ kiểu và đơn vị |
| requestId lúc camelCase lúc snake_case | Truy vấn phân mảnh | Có naming convention |
| Timestamp thiếu offset | Nhập nhằng giữa các máy | UTC/RFC3339 |
| ID dài xuất number | Có thể mất độ chính xác | Dùng string khi phù hợp |
| Trộn null, thiếu field và "" | Consumer hiểu sai | Quy định missing/null semantics |
| Event name chứa ID động | Không phân nhóm được | Tách event và requestId |
| Ghép JSON bằng string không escape | JSON hỏng hoặc log injection | Dùng serializer/encoder |
| Stack trace text multiline trong JSONL | Event bị tách | Structured exception hoặc multiline policy |
| Field level tự nhập khác level logger | Sai severity trong JSON | Backend sinh từ event |
| Thêm field động liên tục | Index mapping phình to | Allowlist/typed fields |
| Không dọn MDC | Lẫn requestId | Context propagation và cleanup |
| Schema không version | Breaking change khó phát hiện | Versioning/migration |
| Alert dựa vào câu message | Đổi wording làm alert hỏng | Dựa vào event/errorCode |
| Log token/payload nhạy cảm | Lộ dữ liệu trong collector | Data minimization và masking |
| Tưởng JSONL tự có index | Query field không chạy | Cấu hình collector/storage |

## 18. Checklist trước khi triển khai một schema mới

1. Tên và ý nghĩa **event** đã ổn định chưa?
2. Envelope chung có **schemaVersion, timestamp, level, service** đúng quy ước chưa?
3. Field nào bắt buộc/tùy chọn theo event?
4. Kiểu dữ liệu và đơn vị có rõ, không phụ thuộc locale?
5. Timestamp có offset/precision và phân biệt event time với ingestion time?
6. Missing/null/empty có được giải thích?
7. JSONL có một event trên một dòng, escape được quote/newline/Unicode?
8. Error/Throwable có schema, kích thước và chính sách masking?
9. Request/trace ID có propagate qua async và được encoder xuất thật?
10. Tên field có hạn chế tự phát sinh không? Record size có giới hạn?
11. Collector parse/map đúng field, query/alert thấy các event mẫu?
12. Có contract test và kiểm tra schema cũ/mới?
13. Có quy trình migration nếu phải đổi tên/kiểu/semantics?
14. Có review dữ liệu nhạy cảm và retention?
15. Có giám sát parse error/drop và người chịu trách nhiệm schema?

## 19. Tự kiểm tra kiến thức

**Câu 1.** Schema log khác với một chuỗi JSON hợp lệ thế nào?

**Đáp án:** JSON là cách serialize; schema định nghĩa tên, kiểu và ý nghĩa các trường cùng quy tắc tương thích. JSON hợp lệ vẫn có thể chứa field sai kiểu hoặc đổi tên ngoài hợp đồng.

**Câu 2.** durationMs=18 và durationMs="18ms" có giống nhau không?

**Đáp án:** Không. Một bên là số, một bên là string; numeric aggregation/query có thể hoạt động sai nếu trộn.

**Câu 3.** Vì sao alert nên tìm event=payment.failed thay vì đúng câu "Payment failed"?

**Đáp án:** Event code giữ ngữ nghĩa ổn định; message có thể đổi câu chữ, ngôn ngữ hoặc chi tiết kỹ thuật.

**Câu 4.** requestId không tồn tại, requestId=null và requestId="" có tự động giống nhau không?

**Đáp án:** Không. Cần định nghĩa missing/null/empty; ID rỗng có thể là dữ liệu không hợp lệ.

**Câu 5.** Có được ghi message chứa newline trong JSON Lines không?

**Đáp án:** Có, nếu encoder escape newline bên trong giá trị, vẫn đảm bảo một object trên một dòng vật lý.

**Câu 6.** Jackson serialize Map thành JSON có tự làm collector index các field không?

**Đáp án:** Không. Collector/storage cần được cấu hình parse và mapping; JSON hợp lệ chỉ là một bước.

**Câu 7.** Viết thủ công level="INFO" trong JSON nhưng gọi LOG.error có rủi ro gì?

**Đáp án:** Level trong payload và event thực mâu thuẫn. Nên dùng encoder lấy level từ logging event.

**Câu 8.** SchemaVersion=2 có làm mọi dashboard hiểu bản mới không?

**Đáp án:** Không. Consumer phải hỗ trợ hoặc chuyển đổi version; cần migration và test.

**Câu 9.** MDC có tự đi qua mọi CompletableFuture/thread pool không?

**Đáp án:** Không. Cần propagation/cleanup theo runtime và encoder phải xuất nó.

**Câu 10.** Có nên dùng JSON key user_123, user_124 cho từng người dùng không?

**Đáp án:** Không nên. Key động làm phình schema/index; dùng tên field ổn định, giảm dữ liệu và quản lý privacy.

**Câu 11.** JSON Schema format=date-time có luôn được validator enforce không?

**Đáp án:** Không. Tùy implementation có thể là annotation; cần bật assertion/parse validation khi hợp đồng yêu cầu.

**Câu 12.** Vì sao không thể dùng log console làm audit storage bền vững chỉ vì record có schemaVersion?

**Đáp án:** Schema không đảm bảo ghi thành công, thứ tự, lưu bền vững hay tính toàn vẹn. Cần cơ chế audit/storage riêng nếu nghiệp vụ yêu cầu.

## 20. Kết luận

**Schema log là hợp đồng dữ liệu của structured logging.** Để nó có giá trị lâu dài:

- Giữ **event code, tên trường và ngữ nghĩa ổn định**.
- Giữ **kiểu dữ liệu, đơn vị, timestamp có timezone, quy ước null** rõ ràng.
- Chọn **encoder/serializer an toàn** và ranh giới một event phù hợp với collector.
- **Kiểm thử schema từ producer tới query**, quản lý versioning và breaking changes.
- Bảo vệ **dữ liệu nhạy cảm, chi phí và kích thước event**.

In được JSON mới chỉ là bước đầu. Một schema được quản lý và thực thi nhất quán giúp log Java dễ truy vấn, liên kết, cảnh báo và điều tra qua nhiều lần triển khai.
