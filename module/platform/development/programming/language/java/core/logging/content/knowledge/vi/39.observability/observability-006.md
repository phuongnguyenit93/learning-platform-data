# Log parsing trong Java Logging và Observability

## 1. Log parsing là gì?

**Log parsing** là quá trình diễn giải một bản ghi log ở dạng text, JSON hoặc định dạng truyền dữ liệu khác thành các **trường có tên và kiểu rõ ràng**: thời gian, level, service, logger, thread, requestId, traceId, eventCode, message và thông tin lỗi. Đây là công đoạn quan trọng để biến log từ văn bản cho con người đọc thành dữ liệu có thể tìm kiếm, lọc, tổng hợp và cảnh báo trong nền tảng **Observability**.

Ví dụ một dòng text do ứng dụng Java ghi:

~~~text
2026-11-10T03:30:05Z INFO [http-4] com.example.OrderService - requestId=req-42 event=ORDER_CREATED orderId=42
~~~

Khi parse đúng theo định dạng đã thống nhất, hệ thống có thể thu:

~~~json
{
  "timestamp": "2026-11-10T03:30:05Z",
  "severityText": "INFO",
  "thread": "http-4",
  "logger": "com.example.OrderService",
  "requestId": "req-42",
  "eventCode": "ORDER_CREATED",
  "orderId": "42"
}
~~~

JSON ở đây là **kết quả kỳ vọng minh họa**, không phải thứ tự động có được chỉ bằng cách đọc text. Parser phải biết điểm bắt đầu và kết thúc các trường. Dữ liệu không có cấu trúc và không có contract có thể được regex khớp nhưng vẫn trích xuất **sai nghĩa**.

Lợi ích khi parse đúng:

- Tìm mọi ERROR của một service trong một khoảng thời gian, thay vì tìm kiếm chuỗi tự do.
- Correlation requestId/traceId giữa log và distributed trace.
- Đếm sự kiện theo eventCode hoặc errorCode mà không phụ thuộc message thay đổi.
- Truy vấn log theo thời gian, môi trường, service và outcome.
- Theo dõi parse failures để phát hiện schema drift và trục trặc pipeline.
- Hạn chế việc người điều tra phải đọc nguyên raw log chứa nhiều dữ liệu không cần thiết.

**Ghi nhớ:** parser không thể sửa một sự kiện đã bị mất, cũng không thể tạo chính xác requestId nếu nguồn không ghi nó.

## 2. Phân biệt các bước của log pipeline

~~~text
Java application
      |
      | SLF4J / JUL / Logback / Log4j 2
      v
LogEvent (timestamp, level, MDC, message, throwable)
      |
      v
Layout / encoder: text, JSON Lines, ...
      |
      v
Stdout / local file / socket
      |
      v
Shipper / agent (Filebeat, Fluent Bit, ...)
      |
      | framing, multiline, decode
      v
Parser / Collector / transform
      |
      | normalize time, severity, context, redact
      v
Index / storage / search
      |
      v
Query, dashboard, alert, tracing correlation
~~~

| Bước | Vai trò | Lỗi thường thấy |
| --- | --- | --- |
| Logging API | Tạo event và context | Thiếu MDC hoặc ghi nhầm dữ liệu cá nhân |
| Layout/encoder | Serialize sự kiện | Pattern thay đổi làm parser hỏng |
| Framing/multiline | Gom đúng ranh giới một event | Stack trace bị chia thành nhiều event |
| Parsing | Chuyển dữ liệu thành field có kiểu | Chuyển timestamp sai hoặc lệch field |
| Transform | Enrich, mask và normalize | Bỏ mất trường hoặc gán nhầm service |
| Indexing | Lưu theo schema để query | Mapping conflict hoặc ingest lag |
| Dashboard | Truy vấn/hiển thị | Đếm sai do parsing, retry hoặc duplicate |

**Parsing không đồng nghĩa shipping**: agent có thể chuyển nguyên một text blob tới collector mà chưa parse. **Parsing cũng không đồng nghĩa indexing**: collector có thể parse thành công nhưng backend từ chối document do mapping/quota.

Khi điều tra, cần biết log bị hỏng ở **nguồn**, **trong parser**, **trong biến đổi schema**, hay **khi index**. Chỉ nhìn dashboard trống không xác định được nguyên nhân.

## 3. Hai chiến lược: JSON có cấu trúc và legacy text

### 3.1. Structured logging tại nguồn

Nếu có quyền sửa logging configuration, ưu tiên xuất event theo schema có cấu trúc bằng JSON Lines: **một object JSON hoàn chỉnh cho mỗi dòng vật lý**, các ký tự newline trong message/exception được escape đúng.

~~~json
{"timestamp":"2026-11-10T03:30:05Z","level":"INFO","service":"order-service","eventCode":"ORDER_CREATED","requestId":"req-42","durationMs":17}
~~~

JSON decoder có thể giữ kiểu dữ liệu (durationMs là số, không phải chuỗi "17ms") và xử lý quote, backslash, Unicode, nested object. Nó ít phụ thuộc vị trí khoảng trắng hơn parser regex trên text. Nhưng JSON hợp lệ vẫn có thể sai schema, chứa PII, thiếu requestId hoặc có field sai kiểu; **vẫn cần validation**.

Đừng tự ghép JSON bằng nối chuỗi khi message đến từ user input, vì quote, newline và backslash có thể làm payload hỏng hoặc bị chèn field giả.

### 3.2. Parse log text legacy

Ví dụ output từ PatternLayout:

~~~text
2026-11-10T03:30:05Z INFO [main] com.example.App - Application started
2026-11-10T03:30:06Z ERROR [worker-2] com.example.DB - Query failed
~~~

Có thể parse bằng template delimiter cố định (Dissect) hoặc regex/Grok. Phải biết định dạng thực tế: timestamp có khoảng trắng không, level có padding không, thread có ngoặc vuông không, logger có độ dài biến đổi không, message có dấu gạch ngang hay newline không.

Một câu log như "Order accepted user=alice|admin" không an toàn nếu parser tự split theo dấu "|" trong khi message cho phép chứa "|". Với log tự do, **format chính là contract kỹ thuật**, không chỉ chi tiết trình bày.

### 3.3. So sánh

| Đặc tính | JSON Lines | Text + parser |
| --- | --- | --- |
| Khả năng giữ kiểu | Trực tiếp nếu schema đúng | Phải parse thêm số/ngày/boolean |
| Xử lý dấu quote/newline | Serializer hỗ trợ escaping | Cần tự định nghĩa delimiter/escaping |
| Chịu thay đổi message | Tốt hơn nếu schema không đổi | Dễ hỏng khi đổi pattern |
| Java stack trace | Có thể nằm trong field JSON đã escape | Thường phải gom multiline |
| Legacy system | Có thể cần thay appender/config | Dễ bổ sung ở collector |
| Vấn đề thường gặp | Schema drift, nested fields, PII | False match, multiline, regex cost |

Không nhất thiết đổi mọi ứng dụng cũ ngay lập tức. Nhưng khi có khả năng thiết kế mới, dùng schema rõ ràng ở nguồn thường giảm chi phí bảo trì parser về dài hạn.

## 4. Schema log nên chuẩn hóa những trường nào?

| Field | Kiểu gợi ý | Mục đích |
| --- | --- | --- |
| timestamp | Thời điểm chuẩn UTC/offset | Khi event được tạo |
| observedTimestamp | Thời điểm quan sát/ingest | Đo lag giữa nguồn và collector |
| severityText | Chuỗi | Level gốc như INFO, WARN, SEVERE |
| severityNumber | Số theo convention | So sánh mức độ xuyên framework |
| service.name | Chuỗi | Dịch vụ phát sự kiện |
| logger.name | Chuỗi | Logger/class phát log |
| thread.name | Chuỗi | Thread thực thi, hữu ích cho Java |
| requestId, traceId, spanId | Chuỗi được validate | Truy vết và liên kết sự kiện |
| eventCode, outcome | Mã có tập giá trị rõ | Query/alert ổn định |
| body/message | Text hoặc cấu trúc | Mô tả sự kiện |
| exception.type | Chuỗi | Nhóm loại lỗi |
| exception.stacktrace | Text được bảo vệ | Điều tra nguyên nhân |
| parser.version, parse.status | Chuỗi | Truy vết việc diễn giải log |

Từng trường có thể **optional** theo loại event. Log startup không nhất thiết có requestId; scheduled job có thể có jobId thay thế. Đừng tự điền ID giả để làm đầy schema.

**OpenTelemetry Logs Data Model** có các trường top-level như Timestamp, ObservedTimestamp, SeverityText, SeverityNumber, Body, TraceId, SpanId, Resource, Attributes và InstrumentationScope. Trong đó service.name thường thuộc metadata Resource, còn requestId có thể nằm trong Attributes. Khi map sang nền tảng khác như Elastic Common Schema, phải định nghĩa tương ứng field/kiểu, không sao chép tên tùy tiện.

Một số convention còn yêu cầu timestamp có độ chính xác đến nano giây; điều đó không có nghĩa chuỗi timestamp của mọi hệ thống Java thực tế đã chính xác tới nano giây. Không thêm độ chính xác giả.

## 5. Phân biệt timestamp của event và thời điểm ingest

Xem các chuỗi:

~~~text
2026-11-10T03:30:05.123Z
2026-11-10T10:30:05.123+07:00
2026-11-10 10:30:05,123
1762745405123
~~~

Hai dòng đầu có thông tin offset nên có thể chuẩn hóa về cùng một UTC instant khi biểu diễn cùng mốc. Dòng thứ ba **không có timezone**, nên parser phải biết timezone của ứng dụng nguồn, không đoán theo nơi collector chạy. Dòng cuối có thể là epoch milliseconds nhưng cần contract xác nhận đơn vị; epoch seconds, milliseconds và nanoseconds khác nhau rất nhiều.

Trong Java:

~~~java
// Fragment; cần import java.time.Instant và OffsetDateTime.
Instant a = Instant.parse("2026-11-10T03:30:05Z");
Instant b = OffsetDateTime
        .parse("2026-11-10T10:30:05+07:00")
        .toInstant();
System.out.println(a.equals(b)); // true
~~~

Nếu parse local datetime bằng ZoneId.systemDefault() trên máy collector, kết quả có thể thay đổi khi deploy sang container/region khác. Hãy dùng **timezone của nguồn được công bố trong schema**.

Một pipeline nên giữ **event timestamp** và **observed timestamp**. Chênh lệch giữa chúng giúp thấy queue lag, network delay, đồng hồ nguồn bị lệch hoặc sự cố shipper. Không được đổi timestamp nguồn thành thời điểm ingest rồi coi các event đều xảy ra đúng lúc collector nhận.

## 6. Ví dụ Java 17+ chạy độc lập: parser có contract và validation

Bài thử mô phỏng log legacy gồm đúng **5 trường** phân tách bằng ký tự "|" theo cấu trúc:

~~~text
occurredAt|level|service|requestId|eventCode
~~~

Quy định:

- occurredAt: ISO-8601 UTC có thể parse bằng Instant.parse.
- level: một trong DEBUG, INFO, WARN, ERROR.
- service: chữ thường/số/dấu gạch nối, gạch dưới, chấm; giới hạn 64 ký tự.
- requestId: chuỗi opaque có ký tự cho phép; giới hạn 64 ký tự.
- eventCode: chữ hoa/số/dấu gạch dưới; giới hạn 64 ký tự.
- Không field nào chứa "|" hoặc xuống dòng; tổng dòng không vượt 512 Java UTF-16 code units.

Đây là **định dạng demo**, không phải quy chuẩn phổ quát cho log. Thực tế nếu cần message tự do, hãy dùng JSON hoặc một protocol escaping được định nghĩa rõ.

Tạo file **LogParserDemo.java**:

~~~java
import java.time.Instant;
import java.time.format.DateTimeParseException;
import java.util.List;
import java.util.Set;

public class LogParserDemo {
    record Event(Instant occurredAt, String level, String service,
                 String requestId, String eventCode) {}

    static final class ParseProblem extends RuntimeException {
        final String code;

        ParseProblem(String code) {
            this.code = code;
        }
    }

    static Event parse(String line) {
        if (line == null || line.length() > 512
                || line.indexOf('\r') >= 0
                || line.indexOf('\n') >= 0) {
            throw new ParseProblem("INVALID_RECORD_SIZE_OR_LINEBREAK");
        }

        // String.split dùng regex; -1 giữ cả trường rỗng.
        String[] parts = line.split("\\|", -1);
        if (parts.length != 5) {
            throw new ParseProblem("INVALID_FIELD_COUNT");
        }

        Instant occurredAt;
        try {
            occurredAt = Instant.parse(parts[0]);
        } catch (DateTimeParseException ex) {
            throw new ParseProblem("INVALID_TIMESTAMP");
        }

        if (!Set.of("DEBUG", "INFO", "WARN", "ERROR")
                .contains(parts[1])) {
            throw new ParseProblem("INVALID_LEVEL");
        }

        if (!parts[2].matches("[a-z0-9][a-z0-9._-]{0,63}")
                || !parts[3].matches("[A-Za-z0-9][A-Za-z0-9_-]{0,63}")
                || !parts[4].matches("[A-Z][A-Z0-9_]{0,63}")) {
            throw new ParseProblem("INVALID_IDENTIFIER");
        }

        return new Event(occurredAt, parts[1],
                parts[2], parts[3], parts[4]);
    }

    public static void main(String[] args) {
        List<String> lines = List.of(
            "2026-11-10T03:30:05Z|INFO|order-service|req-42|ORDER_CREATED",
            "2026-11-10T03:30:06Z|ERROR|payment-service|req-42|PAYMENT_TIMEOUT",
            "2026-11-10Tbad|INFO|order-service|req-42|ORDER_CREATED",
            "2026-11-10T03:30:07Z|INFO|order-service|req-42",
            "2026-11-10T03:30:08Z|TRACE|order-service|req-42|ORDER_READ"
        );

        int accepted = 0;
        int rejected = 0;

        for (String line : lines) {
            try {
                Event e = parse(line);
                accepted++;
                System.out.println("parsed level=" + e.level()
                    + " service=" + e.service()
                    + " requestId=" + e.requestId()
                    + " event=" + e.eventCode());
            } catch (ParseProblem ex) {
                rejected++;
                System.out.println("rejected code=" + ex.code);
            }
        }

        System.out.println("accepted=" + accepted
                + " rejected=" + rejected);
    }
}
~~~

Biên dịch/chạy bằng JDK 17+:

~~~bash
javac LogParserDemo.java
java LogParserDemo
~~~

**Stdout chính xác:**

~~~text
parsed level=INFO service=order-service requestId=req-42 event=ORDER_CREATED
parsed level=ERROR service=payment-service requestId=req-42 event=PAYMENT_TIMEOUT
rejected code=INVALID_TIMESTAMP
rejected code=INVALID_FIELD_COUNT
rejected code=INVALID_LEVEL
accepted=2 rejected=3
~~~

Phân tích:

1. Hai dòng đầu hợp lệ và được chuyển thành Event chứa Instant và các field đã validate.
2. Dòng ba có timestamp không đúng nên INVALID_TIMESTAMP.
3. Dòng bốn chỉ có 4 trường nên INVALID_FIELD_COUNT.
4. Dòng năm dùng TRACE, không có trong whitelist **của demo**, nên INVALID_LEVEL. TRACE vẫn là level hợp lệ của Logback/Log4j 2; parser production phải dựa vào contract của backend.
5. Counter accepted/rejected giúp biết tỷ lệ hợp lệ; không ghi nguyên raw input của lỗi vì có thể chứa dữ liệu nhạy cảm.

**Giới hạn:** Đây là parser một record trên một dòng, không hỗ trợ stack trace multiline, message có delimiter, đọc stream, schema registry, retry hoặc dead-letter queue. Kiểm tra length của String là đơn vị UTF-16 trong JVM; hệ thống production cũng cần giới hạn **byte UTF-8** và kích thước object thực tế. Không dùng split để parse JSON.

## 7. Legacy parser: Dissect, Grok và regex

Giả sử pattern hiển thị là:

~~~text
2026-11-10T03:30:05Z INFO [worker-2] com.example.OrderService - Order created
~~~

Một regex anchored có tên group là:

~~~regex
^(?<timestamp>\S+) (?<level>TRACE|DEBUG|INFO|WARN|ERROR) \[(?<thread>[^\]]{1,80})\] (?<logger>[A-Za-z0-9_.$-]{1,160}) - (?<message>.*)$
~~~

Đây là **pattern minh họa**, chỉ đúng khi timestamp không có khoảng trắng, dấu phân cách cố định, thread trong ngoặc vuông và message nằm trên một dòng. Với Java Pattern.compile(...), backslash trong regex phải escape thêm nếu viết dưới dạng Java string literal.

**Dissect** của Elastic thích hợp khi các vị trí delimiter rất ổn định; **Grok** dựa trên pattern và hữu ích hơn khi định dạng biến thiên. Không nhất thiết dùng regex nếu một split/decoder có contract đã đủ. Tuy nhiên split theo dấu cách thường không an toàn khi message hoặc timestamp chứa khoảng trắng.

Khi thiết kế regex:

- Neo đầu/cuối nếu đang parse toàn record.
- Giới hạn chiều dài input và độ dài các nhóm.
- Không dùng một nhóm tham lam bao tất cả rồi hy vọng nó dừng đúng ở delimiter cuối.
- Kiểm tra trường bắt buộc, thời điểm, level và schema sau khi match.
- Thử input có quote, dấu gạch ngang, Unicode, control character và dấu phân cách trong message.
- Tránh regex với nested quantifier có thể gây catastrophic backtracking (ReDoS).

Một regex match thành công **không đảm bảo các field chính xác**. Cần golden test với các giá trị kỳ vọng đã biết.

## 8. Java stack trace nhiều dòng và multiline framing

Một Java exception thường có nhiều dòng:

~~~text
2026-11-10T03:30:06Z ERROR [worker-2] com.example.DB - Query failed
java.sql.SQLException: Connection refused
    at com.example.DB.execute(DB.java:42)
    at com.example.OrderService.save(OrderService.java:88)
Caused by: java.net.ConnectException: Connection refused
    at java.base/sun.nio.ch.Net.connect0(Native Method)
    ... 3 more
~~~

Đây thường là **một** logging event có Throwable, dù text có nhiều dòng. Nếu file shipper đọc từng dòng như một event, hệ thống sẽ tạo ra các record chỉ có "at..." hoặc "Caused by..." không có timestamp, level và requestId.

Hai cách xử lý:

- **Ưu tiên có thể kiểm soát nguồn:** encode một event thành một JSON object trên một dòng, escape newline trong exception field.
- **Với text legacy:** dùng multiline ở shipper gần nguồn, dựa vào quy tắc nhận biết **bắt đầu event mới**, rồi mới parse trường header.

Ví dụ Filebeat với **filestream** (chỉ phù hợp nếu mọi event mới bắt đầu bằng timestamp yyyy-MM-ddTHH:mm:ss):

~~~yaml
filebeat.inputs:
  - type: filestream
    id: java-application
    paths:
      - /var/log/my-service/*.log
    parsers:
      - multiline:
          type: pattern
          pattern: '^[0-9]{4}-[0-9]{2}-[0-9]{2}T'
          negate: true
          match: after
          max_lines: 200
          timeout: 5s
~~~

Giải thích: các dòng **không bắt đầu** bằng timestamp theo pattern được nối vào event trước. max_lines và timeout giới hạn lượng dòng và thời gian chờ, tránh giữ dữ liệu mãi trong buffer. Nếu output timestamp của bạn có khoảng trắng thay chữ T, regex trên không phù hợp; phải thay theo pattern thật.

Các trường hợp cần test:

- Caused by, Suppressed và các dòng "... more".
- Event có message tự chứa dòng giống timestamp mới.
- Stack trace dài hơn max_lines.
- File rotate hoặc process restart giữa stack trace.
- File chứa nhiều nguồn/thread xen kẽ khó xác định ranh giới.
- Flush theo timeout khi không có dòng tiếp theo.
- Collector và shipper cùng bật multiline dẫn đến gộp sai.

Elastic khuyến nghị xử lý multiline ở Filebeat trước khi đưa sang Logstash khi phù hợp để tránh trộn các luồng từ nhiều nguồn. Không có một regex multiline duy nhất đảm bảo đúng với mọi Java logging pattern.

## 9. Parse JSON: đúng cú pháp chưa đủ đúng semantics

Một appender Java có thể xuất:

~~~json
{"timestamp":"2026-11-10T03:30:05Z","level":"INFO","logger":"com.example.OrderService","service":"order-service","requestId":"req-42","message":"Order accepted","durationMs":17}
~~~

Parser JSON phải giữ nguyên **key, kiểu, escaping, null và nested fields**. Sau khi decode, cần validate:

- timestamp đúng kiểu, format, offset và giới hạn hợp lý;
- level/severity đúng với backend đang xuất;
- durationMs là số (không khi là string, khi là object);
- requestId và traceId đúng kiểu/độ dài;
- JSON Lines có thật sự mỗi dòng một JSON document không;
- exception field có thể chứa newline đã escape;
- field lạ, thiếu, null hoặc schemaVersion mới được xử lý có chủ đích;
- không đưa toàn bộ nested payload chứa dữ liệu cá nhân vào index rộng quyền.

**Java standard library không cung cấp một JSON parser tổng quát tích hợp cho mọi JSON đầu vào.** Trong ứng dụng thực có thể dùng Jackson hoặc parser của collector/backend, với dependency/version thích hợp và schema rõ ràng.

Fragment minh họa với Jackson (cần jackson-databind và DTO do ứng dụng định nghĩa):

~~~java
ObjectMapper mapper = new ObjectMapper();
LogDto dto = mapper.readValue(jsonLine, LogDto.class);
validate(dto); // validation theo schema của ứng dụng
~~~

Đây không phải chương trình độc lập: LogDto, validate(...) và jsonLine là thành phần của ứng dụng. Không dùng String.split(",") để parse JSON; dấu phẩy có thể nằm trong string và nested array/object. Với nguồn không tin cậy, giới hạn kích thước, độ sâu JSON và không bật polymorphic deserialization rộng tùy ý.

## 10. Nguồn Java: Logback và Log4j 2 định hình parser

**SLF4J là API**, Logback hoặc Log4j 2 thường thực hiện format và xuất log. Parser nhận **đầu ra của encoder/layout**, chứ không đọc lời gọi logger.info(...) trực tiếp.

### Logback PatternLayout

Ví dụ trong logback.xml:

~~~xml
<configuration>
  <appender name="CONSOLE"
            class="ch.qos.logback.core.ConsoleAppender">
    <encoder>
      <charset>UTF-8</charset>
      <pattern>%d{ISO8601} %-5level [%thread] %logger - %msg%n%ex{full}</pattern>
    </encoder>
  </appender>
  <root level="INFO">
    <appender-ref ref="CONSOLE"/>
  </root>
</configuration>
~~~

Một stack trace ở output text có thể kéo dài nhiều dòng, nên cần multiline ở shipper. Pattern %X{requestId} giúp xuất context từ MDC nếu ứng dụng đã set requestId. Không có MDC, parser không tự tạo ID chính xác.

### Log4j 2 PatternLayout

Ví dụ fragment:

~~~xml
<PatternLayout pattern="%d{ISO8601} %-5p [%t] %c - %m%n%throwable"/>
~~~

Tên conversion pattern tương tự nhưng không nên copy XML/class giữa Logback và Log4j 2. Nếu đổi encoder từ text sang JSON, **parser contract phía collector cũng phải được thay và kiểm thử**.

### Khi nên chọn JSON encoder

Nếu có quyền kiểm soát nguồn, dùng JSON serializer/encoder có cấu trúc giảm sự lệ thuộc vào regex. Trong Log4j 2 có những layout/template JSON theo phiên bản và dependency; Logback thường cần JSON encoder tương thích nếu muốn schema mở rộng. Cần xem tài liệu đúng phiên bản, kiểm tra exception, MDC, Unicode và nested fields. Đừng giả định pretty-printed JSON phù hợp với shipper cấu hình mỗi dòng một event.

## 11. Chuẩn hóa severity giữa framework

Các backend Java không có cùng tên level:

~~~text
JUL:     SEVERE / WARNING / INFO / CONFIG / FINE / FINER / FINEST
Logback: ERROR / WARN / INFO / DEBUG / TRACE
Log4j 2:  FATAL / ERROR / WARN / INFO / DEBUG / TRACE
~~~

Nếu rule alert chỉ tìm level="ERROR", record từ JUL có level SEVERE có thể bị bỏ sót. Cần map level gốc sang severity chuẩn đã chọn, đồng thời giữ **severityText gốc** để điều tra.

Không chuyển ordinal hoặc số thứ tự enum Java trực tiếp thành OpenTelemetry SeverityNumber. SeverityNumber trong OTel có quy tắc riêng; chẳng hạn nhóm WARN và ERROR nằm trong các khoảng được định nghĩa bởi mô hình dữ liệu, không phụ thuộc số nguyên nội bộ của JUL/Logback.

Không gán ERROR chỉ vì message chứa từ "error". Ngược lại, một HTTP 500 có thể được ghi qua nhiều event INFO và một ERROR; không thay đổi severity của toàn bộ chuỗi chỉ dựa trên status cuối.

## 12. Parse requestId/traceId để tương quan log và trace

Các field context phục vụ Observability:

~~~text
timestamp=2026-11-10T03:30:05Z
level=ERROR
service=payment-service
requestId=req-42
traceId=4bf92f3577b34da6a3ce929d0e0e4736
eventCode=PAYMENT_TIMEOUT
~~~

Sau khi parse, có thể truy vấn logic:

~~~text
service = "payment-service"
AND requestId = "req-42"
~~~

Cú pháp cụ thể phụ thuộc backend (Elastic, Loki, Cloud Logging...). **TraceId** theo chuẩn W3C có format khác ID tùy chỉnh do gateway phát. **SpanId** đại diện cho một span và thường khác ở từng hop.

Nếu worker async không mang theo MDC hoặc trace context, parser không thể đoán requestId từ timestamp gần nhất mà không tạo false correlation. Phải sửa **context propagation tại nguồn**. Với định danh có cardinality cao, lưu nó như log attribute có kiểm soát; không dùng requestId/userId làm metric label không giới hạn.

## 13. Bảo mật: log injection, PII và dữ liệu không tin cậy

Raw log có thể chứa:

~~~text
username="alice|admin"
message="OK\nERROR fake event"
path="/api/search?q=email%40example.test"
Authorization="Bearer secret"
~~~

Vấn đề thường gặp:

- **Delimiter collision:** ký tự phân cách trong input phá thứ tự field.
- **Log injection:** newline hoặc ký tự điều khiển giả làm event mới.
- **PII/secret leakage:** parse thành field càng dễ truy vấn không có nghĩa dữ liệu an toàn.
- **Tấn công tiêu tốn tài nguyên:** regex phức tạp, JSON sâu, message cực lớn, stack trace rất dài.
- **Attribute poisoning:** caller giả mạo key service.name, tenantId hoặc traceId trong input.

Cách phòng vệ:

1. Ưu tiên serializer chuẩn và schema có validation.
2. Giới hạn size bằng byte và số phần tử/depth phù hợp.
3. Không tin các field security/tenant/service do request client tự cung cấp mà chưa được xác thực.
4. Chuẩn hóa ký tự điều khiển khi chuyển text đến logger, tránh tạo log line giả.
5. Làm data minimization tại ứng dụng, masking/redaction có policy ở pipeline.
6. Không log toàn bộ raw payload khi parser thất bại; có thể chứa token/email.
7. Tách quyền truy cập, retention và encryption của raw/quarantine sink.
8. Test negative input, malformed UTF-8, duplicate keys và các dấu phân cách bất thường.

**Redaction tại collector không xóa được bản sao đã ghi ra file hoặc stdout trước đó**. Vì vậy bảo vệ hiệu quả bắt đầu từ nơi tạo sự kiện.

## 14. Lỗi parsing phải có đường xử lý rõ ràng

Parser không nên nuốt mọi input sai rồi tăng mỗi success counter. Một policy có thể gồm:

| Tình huống | Xử lý |
| --- | --- |
| Sai định dạng timestamp | parse.error_code=INVALID_TIMESTAMP |
| Thiếu field bắt buộc | Reject/quarantine theo chính sách |
| Level không nhận biết | Giữ giá trị nguồn và map UNKNOWN hoặc reject có chủ đích |
| JSON sai cú pháp | Tăng metric; không “đoán” field bằng regex dự phòng |
| Mapping conflict ở index | Báo lỗi ingest/schema, không coi parse thành công là lưu thành công |
| Record quá dài | Giới hạn, xử lý theo policy và cảnh báo |
| Collector unavailable | Retry/backpressure; đây là lỗi pipeline, không phải nội dung |
| Raw log chứa secret | Chặn/che theo policy và sửa nguồn |

Nếu là log audit hoặc security bắt buộc, chỉ drop khi policy cho phép; có thể cần **durable quarantine**, retry và cảnh báo. Nhưng kho quarantine cũng phải có quyền truy cập/retention, không phải “đổ nguyên raw line lỗi vào log khác mở quyền hơn”.

Một bẫy nguy hiểm: log chính raw input bị lỗi parse vào cùng stream đang được parser theo dõi, tạo vòng lặp **parse error → ghi log lỗi → parser lại nhận lỗi**. Dùng metric và sự kiện báo lỗi đã tối thiểu hóa thông tin.

## 15. Đo chất lượng parser

Các chỉ số hữu ích:

~~~text
logs_received_total{source,parser_version}
logs_parsed_total{source,parser_version}
logs_rejected_total{source,parser_version,error_code}
logs_quarantined_total{source,parser_version}
logs_indexed_total{source}
parse_duration_seconds{source,parser_version}
pipeline_backlog_events{source}
ingest_lag_seconds{source}
~~~

Label chỉ nên dùng các giá trị **có số lượng hữu hạn**: source, parser_version, error_code. Không gắn message, requestId, userId hoặc email vào metric label.

Một công thức minh họa:

~~~text
parse_success_ratio =
  delta(logs_parsed_total) / delta(logs_received_total)
~~~

Hai counter phải cùng nguồn, cửa sổ, đơn vị event và xử lý retry đúng. Nếu producer/collector restart thì counter tích lũy có thể reset, phải dùng công cụ rate/increase phù hợp.

**Success rate 100% chưa chắc parser đúng**, vì regex có thể match sai nhóm. Kết hợp metric với golden fixtures, các truy vấn end-to-end, phát hiện timestamp bất thường và sample các field có ý nghĩa.

Theo dõi thêm **multiline split/merge errors**, output bytes/s, queue depth, ingest lag, backend rejects, schema mapping conflicts, CPU/GC và các event bị truncate. Khi parser throughput cao mà index throughput thấp, backlog vẫn tăng.

## 16. Kiểm thử parsing: từ unit tới end-to-end

| Test case | Input | Kỳ vọng |
| --- | --- | --- |
| Happy path | Dòng đúng contract | Tách đúng field và kiểu |
| Thiếu field | 4 thay vì 5 trường | Reject đúng errorCode |
| Trường rỗng | Có delimiter liên tiếp | Không shift field âm thầm |
| Timestamp sai | Chuỗi ngày không hợp lệ | Reject, không dùng giờ máy collector đoán |
| Timezone | UTC và offset tương đương | Normalize cùng mốc |
| Level lạ | TRACE khi chỉ cho phép INFO/WARN/ERROR | Reject/map theo policy |
| Ký tự đặc biệt | Dấu quote, pipe, slash, Unicode | Escape hoặc reject chính xác |
| Java stack trace | at/Caused by/Suppressed | Gom đúng một event |
| JSON nested | Comma/quote trong body | Parse đúng, không split thủ công |
| Data rất lớn | Vượt size limit | Không gây OOM hoặc CPU storm |
| Schema version mới | Thêm/đổi field | Migration/backward compatibility có kiểm tra |
| Collector restart | Queue đang chờ, multiline đang gom | Không mất dữ liệu ngoài semantics đã chấp nhận |
| Two tenants | Dữ liệu cùng eventCode | Không route hoặc gắn tenant nhầm |
| End-to-end | Java → agent → index → UI | Truy vấn đúng record, field và thời gian |

### Golden fixtures

Chuẩn bị cặp **input fixture và expected structured output** dưới dạng dữ liệu giả lập, version hóa cùng parser. Có cả positive và negative tests. Khi thay Logback PatternLayout, Log4j 2 layout, Java version hoặc quy tắc shipper, chạy lại fixtures trước khi deploy.

Không dùng một parser “try A, nếu sai dùng B, nếu sai thì lấy phần sau dấu cuối” rồi coi mọi trường hợp là success. Nhiều format không tương thích có thể match nhầm nhưng rất khó phát hiện. Dùng schemaVersion, source type hoặc routing rõ ràng.

### Thử nghiệm end-to-end

1. Tạo một nhóm event với testRunId và requestId giả lập.
2. Quan sát raw output thực tế của encoder.
3. Kiểm tra framing/multiline tại shipper.
4. Kiểm tra structured record ở collector trước khi index.
5. Kiểm tra mapping, số event được indexed và lỗi nếu có.
6. Query theo requestId/eventCode/testRunId, đối chiếu từng field với nguồn.
7. Thử rotate file, async queue, collector timeout và retry.
8. So timestamp nguồn với observedTimestamp và đánh giá ingest lag.

Không kết luận đã hoàn tất chỉ vì HTTP 200 của job ingest: backend có thể đang xử lý hoặc index lag. Cần biết đúng điểm xác nhận của từng hệ thống.

## 17. Throughput, batching và giới hạn của parser

Khi lượng log lớn, parser có thể trở thành bottleneck:

- Regex với backtracking tốn CPU, nhất là input dài.
- JSON nested và exception field lớn tăng allocation/GC.
- Multiline buffer tăng memory và độ trễ flush.
- Lookup để enrich field có thể phụ thuộc network/cache.
- Redaction dùng regex trên raw message lớn có thể rất tốn tài nguyên.
- Index có quá nhiều dynamic fields/nested properties làm tăng chi phí.
- Reject/quarantine/retry tạo backlog khi sự cố kéo dài.

Cần đo **records/s và bytes/s** ở từng chặng: log được nhận, được parse, đã gửi và đã index; p95 parse latency, queue occupancy và error rate. Không coi parser nhanh hơn vì nó tách một stack trace thành hàng trăm dòng: throughput tăng trên giấy trong khi **mỗi event thật bị parse sai**.

Kiểm thử với payload đại diện: INFO ngắn, ERROR stack trace dài, JSON nhiều context, Unicode, nhiều service và trạng thái tăng tải. Nếu rate producer lớn hơn năng lực parse/index trong thời gian dài, tăng queue chỉ kéo dài thời gian tới khi đầy; phải tìm bottleneck thực.

## 18. Những nhầm lẫn dễ gặp

**“Regex match nghĩa là log hợp lệ.”** Regex có thể gán nhầm trường; phải validate schema và so expected output.

**“JSON là đủ, không cần kiểm tra.”** JSON hợp lệ vẫn có thể sai kiểu, thiếu field, có PII hoặc là pretty JSON nhiều dòng.

**“Một dòng là một log event.”** Stack trace có nhiều dòng và cần framing đúng.

**“Chỉ split theo dấu cách là parse được mọi PatternLayout.”** Timestamp, logger padding và free-text message có thể chứa khoảng trắng.

**“Tất cả timestamp đều UTC.”** Nhiều ứng dụng xuất giờ địa phương không có offset; chuyển sai làm chênh thời gian sự cố.

**“JUL và Log4j có level giống nhau.”** JUL có SEVERE/WARNING/FINE; cần severity mapping.

**“Không thấy requestId thì lấy của event gần nhất.”** Tạo correlation sai khi nhiều request đồng thời; sửa MDC/context propagation ở nguồn.

**“Parse lỗi thì in raw message ra log để debug.”** Có thể lộ secret và gây vòng lặp pipeline lỗi. Cần quarantine được bảo vệ và metric.

**“Đã gửi cho collector là đã index thành công.”** Vẫn có schema conflict, quota, backlog, retry hoặc lag.

**“Tăng max_lines và queue vô hạn giúp gom tốt hơn.”** Có thể làm tăng memory và latency, vẫn không xử lý được framing sai.

**“Càng nhiều field index càng tốt.”** Dynamic fields/cardinality cao tốn chi phí và có thể tạo rủi ro dữ liệu cá nhân.

## 19. Checklist triển khai Log parsing

- [ ] Biết định dạng thực tế ở nguồn (JSON Lines hoặc PatternLayout cụ thể).
- [ ] Có schema cho timestamp/timezone, level, service, eventCode và correlation IDs.
- [ ] Framing/multiline đúng với stack trace Java và text/JSON thực tế.
- [ ] Dùng JSON parser cho JSON; regex/Dissect/Grok phù hợp cho legacy text.
- [ ] Input có giới hạn size/độ sâu/trường và quy tắc escaping rõ.
- [ ] Time normalization phân biệt event timestamp với observed timestamp.
- [ ] Severity mapping giữa JUL/Logback/Log4j 2 theo quy ước rõ.
- [ ] Không bịa requestId/traceId nếu không có nguồn đáng tin.
- [ ] Có validation schema, schemaVersion và chủ sở hữu thay đổi.
- [ ] Không ingest PII/secret không cần thiết hoặc raw lỗi ra nơi rộng quyền.
- [ ] Có metric parse success/reject/quarantine và giám sát backlog.
- [ ] Có golden/negative tests và kiểm thử log injection, Unicode, multiline.
- [ ] Đã xác minh end-to-end raw event → parsed fields → index → query.
- [ ] Đánh giá CPU, GC, throughput, ingest lag và dữ liệu bị mất/trùng.
- [ ] Có quy trình rollback parser khi thay encoder hoặc backend.

**Kết luận:** Log parsing làm cho log của ứng dụng Java trở thành dữ liệu Observability **có thể truy vấn và liên kết đáng tin cậy**. Chất lượng phụ thuộc vào hợp đồng dữ liệu, cách đóng khung event, timestamp, severity, schema, an toàn thông tin và kiểm chứng đầu cuối. **Ưu tiên structured logging tại nguồn; với text legacy, parse có validation và multiline đúng chỗ** thay vì chỉ dựa vào regex match.

## 20. Tài liệu tham khảo

- [OpenTelemetry Logs Data Model](https://opentelemetry.io/docs/specs/otel/logs/data-model/): timestamp, observed timestamp, severity, body, resource, attributes và trace context.
- [OpenTelemetry Logs Concepts](https://opentelemetry.io/docs/concepts/signals/logs/): nguồn, logger, log records và exporters.
- [Elastic Filebeat — Manage multiline messages](https://www.elastic.co/docs/reference/beats/filebeat/multiline-examples): gom Java stack traces theo input stream.
- [Elastic — Grok processor](https://www.elastic.co/docs/reference/enrich-processor/grok-processor): parse named fields bằng pattern.
- [Elastic — Dissect processor](https://www.elastic.co/docs/reference/enrich-processor/dissect-processor): parse dữ liệu theo delimiter cố định.
- [Logback Manual — Layouts](https://logback.qos.ch/manual/layouts.html): cấu hình PatternLayout.
- [Apache Log4j 2 — Pattern Layout](https://logging.apache.org/log4j/2.x/manual/pattern-layout.html): pattern và exception conversion.
- [Apache Log4j 2 — JSON Template Layout](https://logging.apache.org/log4j/2.x/manual/json-template-layout.html): structured JSON output theo template.
- [Oracle Java SE 17 — java.time.Instant](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/Instant.html): xử lý timestamp UTC.
- [Oracle Java SE 17 — java.util.regex.Pattern](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/regex/Pattern.html): regex trong Java, named groups và escaping.
