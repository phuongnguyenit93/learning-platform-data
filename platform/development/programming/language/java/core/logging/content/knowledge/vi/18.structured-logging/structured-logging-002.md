# Key-value log trong Structured logging của Java

## 1. Key-value log là gì?

**Key-value log** là cách ghi một sự kiện dưới dạng **các trường có tên (key) và giá trị (value)**, thay vì chỉ diễn tả mọi thông tin trong một câu văn tự do. Trong nhóm **Structured logging** của Java Core Logging, đây là cách nền tảng để log có thể được máy tính **lọc, nhóm, thống kê, liên kết và tìm kiếm** một cách đáng tin cậy.

Ví dụ một sự kiện đơn hàng được chấp nhận:

~~~text
level=INFO event=order.accepted orderId=ORD-17 quantity=2 paid=true
~~~

Các cặp key–value là:

| Key | Value | Ý nghĩa |
| --- | --- | --- |
| level | INFO | Mức độ ghi log |
| event | order.accepted | Mã sự kiện ổn định |
| orderId | ORD-17 | Định danh đơn hàng |
| quantity | 2 | Số lượng mặt hàng |
| paid | true | Trạng thái thanh toán |

Dạng biểu diễn có thể là **text key=value**, **JSON object**, hoặc một event nội bộ giữ các trường riêng biệt trước khi encoder xuất ra byte. Điều đáng quan tâm không chỉ là có dấu **=**, mà là **logging API, backend, encoder và collector có giữ được ranh giới và kiểu dữ liệu của các trường hay không**.

Ví dụ biểu diễn JSON của cùng ý nghĩa:

~~~json
{"level":"INFO","event":"order.accepted","orderId":"ORD-17","quantity":2,"paid":true}
~~~

Trong JSON này, **quantity** là số và **paid** là boolean. Nếu chỉ viết chuỗi **quantity=2 paid=true** vào một message thông thường, backend/collector chưa chắc phân tích chúng thành số và boolean. **Key-value log có cấu trúc thật sự** cần chính sách tạo event và encoder/parser thống nhất.

## 2. Vì sao key-value log tốt hơn chuỗi log tự do?

Xem hai kiểu log cho cùng sự kiện:

**Chuỗi tự do:**

~~~text
Order ORD-17 was accepted. Quantity was 2 and payment succeeded.
~~~

**Key-value nhất quán:**

~~~text
event=order.accepted orderId=ORD-17 quantity=2 outcome=SUCCESS
~~~

Khi hệ thống có hàng triệu bản ghi, chuỗi tự do khó xử lý nếu câu chữ thay đổi theo lập trình viên, phiên bản sản phẩm hoặc ngôn ngữ. Với key-value, hệ thống tìm kiếm có thể đặt điều kiện có cấu trúc:

~~~text
event == "order.accepted"
AND outcome == "SUCCESS"
AND quantity >= 2
~~~

Đoạn trên là **pseudo query** thể hiện ý tưởng, không phải cú pháp chung của Elasticsearch, Loki, Cloud Logging hoặc một nền tảng log cụ thể.

**Lợi ích chính:**

1. **Tìm theo điều kiện chính xác:** lọc event, level, service, reasonCode mà không phải regex câu văn.
2. **Liên kết các sự kiện:** tìm tất cả log mang requestId hoặc jobId.
3. **Nhóm và đếm:** tính số lần retry theo dependency hoặc outcome từ tập log.
4. **Tách dữ liệu khỏi câu chữ:** message có thể thay đổi cho dễ đọc mà schema sự kiện vẫn ổn định.
5. **Tăng khả năng giám sát:** cấu hình dashboard và cảnh báo theo key đã biết.
6. **Hỗ trợ nhiều ngôn ngữ:** không cần parse câu mô tả tiếng Việt/tiếng Anh.
7. **Chống nhầm lẫn kiểu:** với encoder phù hợp, durationMs là số nguyên, success là boolean, không phải text.

**Key-value logging không thay thế hoàn toàn message.** Một event vẫn có thể có trường **message** ngắn giúp con người hiểu, nhưng thông tin cần truy vấn nên là các trường riêng.

## 3. Phân biệt key-value dạng text, JSON và event có cấu trúc

Có ba cấp độ phổ biến:

| Cách ghi | Ví dụ | Điều quan trọng |
| --- | --- | --- |
| Chuỗi message tự tạo | logger.info("orderId=" + id) | Có vẻ là key=value nhưng thường chỉ là một String |
| Event với các key-value riêng trong API | addKeyValue("orderId", id) | Backend có thể nhận metadata theo từng trường |
| Output JSON có schema | {"orderId":"ORD-17","quantity":2} | Collector có thể parse thành trường và kiểu dữ liệu |

Một chuỗi:

~~~text
event=order.accepted orderId=ORD-17 customer="Nguyễn An" quantity=2
~~~

không phải **JSON**. Nếu parser text được cấu hình rõ, nó vẫn có thể là key-value log hữu ích. Nhưng các giá trị chứa **dấu cách, dấu bằng, dấu ngoặc kép, xuống dòng hoặc ký tự điều khiển** cần quy tắc escape/quote thống nhất; nếu không, hệ thống parse có thể tách sai.

JSON cho phép quy định rõ:

~~~json
{
  "event": "order.accepted",
  "orderId": "ORD-17",
  "customer": "Nguyễn An",
  "quantity": 2,
  "success": true
}
~~~

**Không phải hễ in một dấu ngoặc nhọn là structured logging đúng.** JSON phải hợp lệ, mỗi trường có nghĩa nhất quán, và collector phải nhận được ranh giới từng event.

## 4. Event, message, context và metadata khác nhau như thế nào?

Một bản ghi chuẩn thường có ba nhóm thông tin:

**A. Metadata tự động của logging system**

- timestamp, level, loggerName
- threadName
- service, environment, instance, host
- thông tin lỗi hoặc Throwable

**B. Trường riêng của từng sự kiện**

- event, orderId, quantity
- outcome, reasonCode, durationMs
- retryAttempt, dependency

**C. Context đi theo nhiều event trong một request/job**

- requestId, traceId, spanId
- tenantId nếu được cho phép theo chính sách dữ liệu
- jobId hoặc workflowId

Ví dụ:

~~~json
{
  "timestamp": "2026-11-09T12:00:00Z",
  "level": "INFO",
  "service": "checkout",
  "event": "payment.authorized",
  "requestId": "req-42",
  "traceId": "trace-9a",
  "orderId": "ORD-17",
  "amountMinor": 159900,
  "currency": "VND",
  "outcome": "SUCCESS"
}
~~~

Đây là **bản ghi minh họa**, không phải kết quả chạy code. **amountMinor** là đơn vị tiền nhỏ nhất được hệ thống lựa chọn; đừng suy ra mọi loại tiền đều có hai chữ số thập phân. Đặt đơn vị trong tên trường hoặc trong schema để tránh hiểu nhầm.

**Event** là mã ổn định như payment.authorized. **Message** có thể là văn bản “Payment authorized”. **Context** giúp các log của cùng luồng xử lý được liên kết. Không dùng một trường duy nhất mang cả ba trách nhiệm.

## 5. Thiết kế schema key-value tốt

Một schema là thỏa thuận chung về **tên trường, kiểu giá trị, ý nghĩa và chính sách hiện diện**. Không nhất thiết phải có một file schema riêng trong bài học nhỏ, nhưng dự án nhiều service nên tài liệu hóa những trường trọng yếu.

Một tập tên gợi ý:

| Key | Kiểu dữ liệu | Quy ước |
| --- | --- | --- |
| timestamp | Chuỗi ngày giờ chuẩn hóa | ISO 8601/RFC 3339, ưu tiên UTC |
| level | Chuỗi enum | INFO, WARN, ERROR hoặc đúng mức backend |
| service | Chuỗi | Tên service ổn định |
| environment | Chuỗi enum | dev, staging, prod theo hệ thống |
| event | Chuỗi mã | order.accepted, inventory.retry |
| requestId | Chuỗi | Định danh một yêu cầu |
| traceId/spanId | Chuỗi | Định danh của hệ tracing nếu có |
| orderId | Chuỗi | Giữ số 0 đầu và format ID |
| quantity | Số nguyên | Không đổi sang chuỗi tùy ý |
| durationMs | Số | Thời gian, đơn vị milliseconds |
| attempt | Số nguyên | Lần thử thứ mấy |
| outcome | Chuỗi enum | SUCCESS, FAILURE, RETRY |
| reasonCode | Chuỗi mã | Mã lỗi ổn định, không phải stack trace |

### Một số nguyên tắc đặt tên

1. **Dùng một kiểu tên xuyên service**: camelCase hoặc snake_case, không thay đổi tùy nhóm.
2. **Tên trường nói rõ đơn vị**: durationMs, bytesSent, retryCount.
3. **Giữ ID dưới dạng chuỗi**, không ép sang number vì có thể mất số 0 đầu hoặc vượt giới hạn chính xác của parser.
4. **Không thay kiểu qua phiên bản**: attempt không hôm nay là 2 (number), ngày mai là "2" (string).
5. **Tránh key trùng** trong cùng một object JSON; quy tắc xử lý duplicate khác nhau giữa parser.
6. **Định nghĩa thiếu và null**: trường không hiện diện có khác trường hiện diện với value null không?
7. **Tránh key bất định**: tên key phải là một tập được kiểm soát. Không biến email hoặc orderId thành tên trường.
8. **Dùng event name có cấu trúc**, ví dụ noun.verb hoặc domain.action, và ghi rõ khi nào phát event.
9. **Chọn một ý nghĩa cho một key**. Không dùng field status lúc thì HTTP 200, lúc lại là trạng thái đơn hàng.
10. **Tách message cho con người và dữ liệu cho máy** để format/translation không phá query.

**Không cần nhồi mọi trường vào mọi event.** Chọn tập core ổn định và các trường có giá trị riêng cho từng loại sự kiện. Field nhiều nhưng không nhất quán sẽ làm pipeline khó dùng hơn.

## 6. Dùng đúng kiểu dữ liệu khi xuất JSON

JSON hỗ trợ **string, number, boolean, null, array và object**. Đừng chuyển mọi thứ thành String chỉ vì API log có thể nhận String.

Ví dụ nên ưu tiên:

~~~json
{"event":"inventory.retry","attempt":3,"success":false,"elapsedMs":850}
~~~

Thay vì:

~~~json
{"event":"inventory.retry","attempt":"3","success":"false","elapsedMs":"850"}
~~~

Bản thứ hai vẫn hợp lệ nhưng yêu cầu parser chuyển kiểu khi phân tích, và dễ làm sai điều kiện so sánh.

**Các lưu ý về kiểu:**

- **BigDecimal/tiền:** cần chính sách lưu kiểu và độ chính xác của JSON/collector. Có thể dùng số nguyên minor unit cộng currency.
- **Số quá lớn:** có collector/parsers dùng IEEE 754, không giữ chính xác mọi long 64-bit; cân nhắc string đối với ID và số đếm ngoài phạm vi an toàn.
- **NaN/Infinity:** không phải literal số hợp lệ trong JSON; encoder phải xử lý chúng có chủ đích.
- **Enum:** dùng code ổn định, tránh tự tạo value theo exception message.
- **Timestamp:** dùng định dạng rõ timezone; tránh trộn epoch seconds và epoch milliseconds.
- **Nested object:** hữu ích khi có nhóm dữ liệu, nhưng một số collector/index mapping có giới hạn độ sâu.
- **Array:** phù hợp một số thuộc tính; tránh lạm dụng array cực lớn trong một event.

Một key-value log tốt phải có cả **schema** và **encoder/parser** giữ được kiểu dữ liệu cần thiết.

## 7. Bài tập “trước và sau”: từ text sang key-value

Giả sử mã cũ:

~~~java
LOG.info("Accepted order " + orderId + " with quantity " + quantity);
~~~

Đây là snippet với biến đã khai báo. Câu này dễ đọc nhưng khó lọc số lượng sau này nếu câu chữ thay đổi.

Dạng trung gian bằng placeholder:

~~~java
LOG.info("Accepted orderId={} quantity={}", orderId, quantity);
~~~

Đây là cú pháp **SLF4J/Log4j 2**, không phải cú pháp mặc định của JUL. Nó tránh nối chuỗi trong nhiều tình huống, nhưng **chưa bảo đảm orderId và quantity là hai trường có cấu trúc**, vì backend có thể chỉ xuất một message đã format.

Với **SLF4J 2.x fluent logging**:

~~~java
LOG.atInfo()
        .addKeyValue("event", "order.accepted")
        .addKeyValue("orderId", orderId)
        .addKeyValue("quantity", quantity)
        .log("Order accepted");
~~~

Đây là snippet trong một lớp có **org.slf4j.Logger LOG**. Các key-value được cung cấp như metadata của event. **Cách chúng được hiển thị/lưu phụ thuộc backend**; muốn JSON field thực sự cần encoder/layout hỗ trợ.

**Không nhầm ba việc:** đặt tên biến trong câu văn, truyền argument cho template và thêm metadata key-value riêng qua logging API.

## 8. Ví dụ Java 17+ chạy độc lập: xuất JSON key-value bằng JUL

Để học cấu trúc dữ liệu **mà không cần dependency ngoài JDK**, ví dụ này dùng:

- **java.util.logging.Logger** để phát LogRecord.
- **ConsoleHandler** để xuất ra **System.err**.
- **LogRecord.setParameters(...)** để chuyển một Map chứa metadata của mỗi event.
- **Formatter tùy chỉnh** đọc Map và ghi **một JSON object mỗi dòng**.
- **LinkedHashMap** giữ thứ tự trường trong bài thực hành để có expected output xác định.
- Quy tắc escape tối thiểu với dấu ngoặc kép, backslash và control characters.
- **Level.INFO** ở Handler nên bản ghi FINE không xuất.

**Lưu ý phạm vi:** đây là một **quy ước riêng của demo**: JUL không tự biến Object[] parameters thành hệ thống structured key-value chuẩn có schema. Production thường nên dùng một encoder/JSON library đáng tin cậy và logging backend được quản lý tập trung; không sử dụng formatter tự viết này cho dữ liệu object tùy ý.

### File StructuredKvDemo.java

~~~java
import java.util.LinkedHashMap;
import java.util.Map;
import java.util.logging.ConsoleHandler;
import java.util.logging.Formatter;
import java.util.logging.Level;
import java.util.logging.LogRecord;
import java.util.logging.Logger;

public final class StructuredKvDemo {
    private static final Logger LOG =
            Logger.getLogger("examples.logging.keyvalue");

    public static void main(String[] args) {
        LOG.setUseParentHandlers(false);
        LOG.setLevel(Level.ALL);

        ConsoleHandler console = new ConsoleHandler();
        console.setLevel(Level.INFO);
        console.setFormatter(new JsonLineFormatter());
        LOG.addHandler(console);

        try {
            Map<String, Object> order = new LinkedHashMap<>();
            order.put("orderId", "ORD-17");
            order.put("quantity", 2);
            order.put("paid", true);
            emit(Level.INFO, "order.accepted", order);

            Map<String, Object> retry = new LinkedHashMap<>();
            retry.put("orderId", "ORD-17");
            retry.put("attempt", 2);
            retry.put("reason", "stock \"slow\"");
            emit(Level.WARNING, "inventory.retry", retry);

            Map<String, Object> detail = new LinkedHashMap<>();
            detail.put("key", "ORD-17");
            emit(Level.FINE, "cache.hit", detail);
        } finally {
            LOG.removeHandler(console);
            console.close();
        }
    }

    private static void emit(
            Level level, String event, Map<String, Object> fields) {
        if (fields.containsKey("event")
                || fields.containsKey("level")) {
            throw new IllegalArgumentException(
                    "Reserved field: event or level");
        }

        LogRecord record = new LogRecord(level, event);
        record.setParameters(
                new Object[] { new LinkedHashMap<>(fields) });
        LOG.log(record);
    }

    private static final class JsonLineFormatter extends Formatter {
        @Override
        public String format(LogRecord record) {
            StringBuilder out = new StringBuilder();
            out.append("{\"level\":\"")
                    .append(escape(record.getLevel().getName()))
                    .append("\",\"event\":\"")
                    .append(escape(record.getMessage()))
                    .append('"');

            Object[] parameters = record.getParameters();
            if (parameters != null && parameters.length == 1
                    && parameters[0] instanceof Map<?, ?> fields) {
                for (Map.Entry<?, ?> field : fields.entrySet()) {
                    out.append(",\"")
                            .append(escape(String.valueOf(field.getKey())))
                            .append("\":");
                    appendValue(out, field.getValue());
                }
            }
            return out.append('}')
                    .append(System.lineSeparator())
                    .toString();
        }

        private static void appendValue(
                StringBuilder out, Object value) {
            if (value == null) {
                out.append("null");
            } else if (value instanceof Boolean
                    || value instanceof Byte
                    || value instanceof Short
                    || value instanceof Integer
                    || value instanceof Long) {
                out.append(value);
            } else {
                out.append('"')
                        .append(escape(String.valueOf(value)))
                        .append('"');
            }
        }

        private static String escape(String value) {
            StringBuilder out = new StringBuilder();
            for (int i = 0; i < value.length(); i++) {
                char ch = value.charAt(i);
                switch (ch) {
                    case '"' -> out.append("\\\"");
                    case '\\' -> out.append("\\\\");
                    case '\n' -> out.append("\\n");
                    case '\r' -> out.append("\\r");
                    case '\t' -> out.append("\\t");
                    default -> {
                        if (ch < 0x20) {
                            out.append("\\u00")
                                    .append(Character.forDigit(
                                            (ch >>> 4) & 0xF, 16))
                                    .append(Character.forDigit(
                                            ch & 0xF, 16));
                        } else {
                            out.append(ch);
                        }
                    }
                }
            }
            return out.toString();
        }
    }
}
~~~

### Biên dịch và chạy

Với JDK 17 hoặc mới hơn:

~~~bash
javac StructuredKvDemo.java
java StructuredKvDemo
~~~

**Hai dòng stderr từ ConsoleHandler** (stdout không có dữ liệu do chương trình in):

~~~json
{"level":"INFO","event":"order.accepted","orderId":"ORD-17","quantity":2,"paid":true}
{"level":"WARNING","event":"inventory.retry","orderId":"ORD-17","attempt":2,"reason":"stock \"slow\""}
~~~

Đây là **NDJSON/JSON Lines** về mặt biểu diễn: mỗi dòng là một JSON object riêng, không phải một JSON array chứa cả hai dòng. Với hệ điều hành khác nhau ký tự xuống dòng vật lý có thể khác, nhưng nội dung logic của hai dòng là như trên.

### Giải thích vì sao ra đúng hai dòng

1. **Logger Level.ALL** cho phép LogRecord mức INFO, WARNING và FINE đi qua nguồn.
2. **ConsoleHandler Level.INFO** bỏ FINE, giữ INFO và WARNING.
3. **setUseParentHandlers(false)** tránh Logger cha có Handler riêng ghi thêm bản sao.
4. **LinkedHashMap** lưu các key theo thứ tự put() được đưa vào, nên expected output có thứ tự ổn định.
5. **LogRecord.setParameters(...)** giữ một đối tượng Map trong tham số; đây là convention do demo định nghĩa.
6. **JsonLineFormatter** xuất level/event trước, rồi các trường trong Map.
7. **quantity=2 và paid=true** được xuất thành số và boolean JSON, không có dấu ngoặc kép.
8. **reason** chứa dấu ngoặc kép thực, vì vậy escape() biến chúng thành **\\"** trong biểu diễn JSON.
9. **ConsoleHandler** ghi vào **System.err** và flush theo cơ chế của nó. Chương trình không dùng println để giả lập output.
10. **console.close()** xả và kết thúc Handler, không đóng System.err của JVM.
11. **FINE cache.hit** không xuất dù đã gọi emit() vì Handler đặt ở INFO.

**Kiểm tra cẩn thận:** đoạn mô tả ở mục 8 về escape là quy tắc hiển thị của JSON; trong khối output, hai ký tự backslash-quote xuất hiện dưới dạng **\"**. Khi parse JSON, giá trị reason được khôi phục thành chuỗi có dấu ngoặc kép thực.

### Giới hạn của formatter tự viết

- Chỉ giữ các kiểu **Boolean, Byte, Short, Integer, Long** ở dạng literal số/boolean. Những kiểu khác được xuất thành chuỗi.
- Chưa xử lý nested object, array, BigDecimal theo schema, surrogate Unicode không hợp lệ hoặc Throwable.
- Nếu muốn xuất **timestamp**, cần định dạng time zone/precision ổn định; ví dụ cố ý bỏ để dễ kiểm chứng.
- Nếu muốn ghi **exception** và cause chain, cần thiết kế cách encode Throwable riêng thay vì chỉ dùng message.
- Không đưa key bất định hoặc PII vào Map không được kiểm soát.
- Không dùng **LogRecord parameters Map** như một standard interoperability contract của JUL; đây chỉ là một cách demo dữ liệu metadata.

Trong ứng dụng production, dùng **JSON encoder/layout có kiểm thử**, thay vì tự nối JSON bằng StringBuilder khi cần hỗ trợ mọi kiểu đối tượng.

## 9. SLF4J 2.x: addKeyValue() cho metadata từng event

**SLF4J** là facade logging thông dụng trong Java. Từ **SLF4J 2.0**, fluent API hỗ trợ **LoggingEventBuilder.addKeyValue(key, value)**.

Ví dụ:

~~~java
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

public class CheckoutService {
    private static final Logger LOG =
            LoggerFactory.getLogger(CheckoutService.class);

    public void accept(String orderId, int quantity) {
        LOG.atInfo()
                .addKeyValue("event", "order.accepted")
                .addKeyValue("orderId", orderId)
                .addKeyValue("quantity", quantity)
                .log("Order accepted");
    }
}
~~~

Đây là một **lớp component**, có thể biên dịch khi dự án có slf4j-api 2.x; nó không có main(), và ứng dụng cần **một provider tương thích** ở runtime để thực sự ghi log.

**Những điểm cần nhớ:**

- **atInfo()** bắt đầu một builder event INFO; addKeyValue(...) gắn trường riêng.
- **log(...)** là bước bắt buộc để phát sự kiện. Nếu quên gọi **log()**, builder không xuất log.
- Khi mức log tắt, API được thiết kế để hạn chế công việc không cần thiết.
- Java vẫn đánh giá các biểu thức đối số trước khi gọi method, trừ cách dùng lazy/supplier được API hỗ trợ rõ.
- **Thông tin key-value được giữ riêng ở API**; provider/backend có quyền chọn cách biểu diễn chúng.
- **Không tự có JSON** chỉ vì addKeyValue(). Muốn JSON, chọn encoder/layout và cấu hình phù hợp.
- Có thể dùng **addArgument(...)** cho placeholder {} và **addKeyValue(...)** cho trường có tên; chúng phục vụ mục đích khác nhau.
- Một phần mềm dùng SLF4J 1.7 không có các method atInfo()/addKeyValue() của API 2.x. Phải kiểm tra dependency/version thực tế.

Ví dụ kết hợp cả message và key–value:

~~~java
LOG.atWarn()
        .addKeyValue("event", "inventory.retry")
        .addKeyValue("orderId", orderId)
        .addKeyValue("attempt", attempt)
        .log("Dependency retry");
~~~

Đoạn là snippet cần biến đã khai báo. Cách hiển thị có thể là key=value trước message trong text layout, nhưng chỉ backend/encoder cấu hình mới quyết định chính xác output.

## 10. Logback: dùng %kvp để xem key–value

Nếu ứng dụng dùng **SLF4J 2.x + Logback phù hợp**, **PatternLayout** của Logback có conversion word **%kvp** cho những key–value được gắn với logging event.

Ví dụ **logback.xml**:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<configuration>
    <appender name="CONSOLE"
              class="ch.qos.logback.core.ConsoleAppender">
        <target>System.out</target>
        <encoder>
            <pattern>%d{yyyy-MM-dd HH:mm:ss.SSS} %-5level %logger %kvp - %msg%n</pattern>
            <charset>UTF-8</charset>
        </encoder>
    </appender>

    <root level="INFO">
        <appender-ref ref="CONSOLE"/>
    </root>
</configuration>
~~~

**Ý nghĩa:**

- **%kvp** hiển thị key-value pairs của event do API gắn vào.
- **%msg** là thông điệp con người đọc.
- **%logger** và **%level** là metadata cơ bản của log.
- **%n** là xuống dòng theo platform.
- **ConsoleAppender** ghi ra System.out vì target đã cấu hình.
- Cần Logback/provider tương thích API SLF4J 2.x, không chép XML này sang Log4j 2.
- Đầu ra thực tế chứa timestamp/tên Logger nên không phải chuỗi cố định của bài demo Java 17 ở mục 8.

Logback có lựa chọn quote trong conversion word, ví dụ **%kvp{NONE}**, **%kvp{SINGLE}**, **%kvp{DOUBLE}**. Dùng **NONE** có thể khiến text parser khó xử lý các giá trị chứa dấu cách hoặc ký tự đặc biệt.

Logback mới cũng cung cấp **%maskedKvp** trong những phiên bản được hỗ trợ, nhưng **mask ở encoder không thay thế việc tránh tạo/log dữ liệu bí mật ngay từ nguồn**. Không dựa vào một filter/mask ở một Appender để kết luận những Appender khác, queue, tracing hoặc debug dump không bao giờ thấy dữ liệu nhạy cảm.

**Lưu ý quan trọng:** **%kvp là text pattern**, không đồng nghĩa JSON có typed fields. Nếu muốn ingest từng key như object JSON có kiểu đúng, phải chọn JSON encoder thích hợp và kiểm thử trên collector. Một giá trị Java số có thể bị format thành text trong pattern, nên không suy ra parser tự hiểu nó là number.

## 11. Log4j 2: MapMessage, ThreadContext và JSON Template Layout

Log4j 2 có **Message** implementations và **ThreadContext** để mang dữ liệu có cấu trúc.

### MapMessage / StringMapMessage

Ví dụ **StringMapMessage** của Log4j API:

~~~java
import org.apache.logging.log4j.LogManager;
import org.apache.logging.log4j.Logger;
import org.apache.logging.log4j.message.StringMapMessage;

public class InventoryService {
    private static final Logger LOG =
            LogManager.getLogger(InventoryService.class);

    public void retry(String orderId, int attempt) {
        StringMapMessage event = new StringMapMessage()
                .with("event", "inventory.retry")
                .with("orderId", orderId)
                .with("attempt", String.valueOf(attempt));
        LOG.warn(event);
    }
}
~~~

Đây là lớp component, cần dependency Log4j API và backend khi thực thi. **StringMapMessage** mô hình hóa Map với giá trị kiểu String; ví dụ đã chuyển attempt sang String. **Không đồng nghĩa attempt chắc chắn được output dưới dạng số JSON**; cần thiết kế schema và layout phù hợp. Log4j 2 có những biến thể MapMessage với khả năng format khác; kiểm tra API/backend đang dùng.

**MapMessage không phải ThreadContext.** MapMessage mô tả dữ liệu **của một message/event**, còn ThreadContext Map thường mang những trường của **ngữ cảnh xử lý hiện tại**, ví dụ requestId.

### ThreadContext cho requestId

~~~java
import org.apache.logging.log4j.CloseableThreadContext;

try (CloseableThreadContext.Instance ignored =
        CloseableThreadContext.put("requestId", requestId)) {
    LOG.info("event=inventory.retry");
}
~~~

Đây là snippet trong phương thức đã có LOG/requestId và dependency Log4j API. Context chỉ có ích khi backend/layout lấy các trường này vào output.

Trong **PatternLayout** của Log4j 2:

- **%X{requestId}** truy cập Thread Context Map/MDC.
- **%K{orderId}** truy cập key của MapMessage khi message là dạng map phù hợp.
- **%msg** hiển thị message theo formatter được chọn.

Không nhầm **%X** và **%K**: chúng đọc từ **hai nguồn dữ liệu khác nhau**.

### JSON Template Layout

Log4j 2 cung cấp **JsonTemplateLayout** để mã hóa LogEvent thành JSON theo template. Cần thêm module **log4j-layout-template-json** tương thích backend; module này không tự có chỉ vì ứng dụng dùng log4j-api.

Ví dụ cấu hình **log4j2.xml** tối giản:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<Configuration>
    <Appenders>
        <Console name="JSON" target="SYSTEM_OUT">
            <JsonTemplateLayout/>
        </Console>
    </Appenders>
    <Loggers>
        <Root level="info">
            <AppenderRef ref="JSON"/>
        </Root>
    </Loggers>
</Configuration>
~~~

Khi được cung cấp module và backend tương thích, JsonTemplateLayout dùng template mặc định của Log4j (thường mô hình ECS theo tài liệu Log4j 2.x hiện hành). **Hình dạng JSON thực tế không phải khối output ở mục 8**; muốn kiểm soát schema, dùng **eventTemplate/eventTemplateUri** và các resolver cần thiết.

**Tách bạch:** MapMessage là **nguồn dữ liệu message**, ThreadContext là **ngữ cảnh**, còn JSON Template Layout là **encoder output**. Muốn field end-to-end, phải kiểm tra template lấy đúng thông tin ở cả ba nơi.

## 12. Key-value của một event và MDC đi theo request

Một yêu cầu HTTP có thể phát các event:

~~~text
requestId=req-42 event=order.validation.started
requestId=req-42 event=inventory.lookup attempt=1
requestId=req-42 event=order.accepted orderId=ORD-17
~~~

**requestId** là context chung. **event, attempt và orderId** thay đổi theo từng event. Trong SLF4J có **MDC** (Mapped Diagnostic Context):

~~~java
import org.slf4j.MDC;

try (MDC.MDCCloseable ignored =
        MDC.putCloseable("requestId", requestId)) {
    LOG.atInfo()
            .addKeyValue("event", "order.accepted")
            .addKeyValue("orderId", orderId)
            .log("Order accepted");
}
~~~

Đây là snippet cần SLF4J 2.x và các biến đã có.

**Lưu ý về thread pool:** MDC thường gắn với context của thread; **không tự động lan qua mọi Executor, CompletableFuture, virtual thread hoặc dịch vụ bên ngoài**. Nếu request A để lại requestId trên một thread được tái sử dụng cho B, log B có thể bị gắn ID sai.

Quy tắc:

1. Đặt MDC ở ranh giới bắt đầu request/job khi có đủ context.
2. Dọn MDC trong finally hoặc scope closeable.
3. Khi chuyển thread, dùng cơ chế propagation rõ ràng và đảm bảo dọn ở thread đích.
4. Nếu log bất đồng bộ, đảm bảo context được **snapshot** vào event ở thời điểm phát, không đọc ThreadLocal của writer thread rồi tưởng đó là context của producer.
5. Nếu có traceId/spanId, tích hợp đúng propagation của tracing system, không tự chọn ID tùy ý mỗi bước.
6. Kiểm tra encoder thực sự xuất MDC; chỉ gọi MDC.put không đủ.

## 13. Ghi key-value cho exception

Một log lỗi cần **event/metadata có cấu trúc** nhưng cũng phải giữ **Throwable**.

Ví dụ SLF4J 2.x:

~~~java
LOG.atError()
        .addKeyValue("event", "order.persist.failed")
        .addKeyValue("orderId", orderId)
        .addKeyValue("reasonCode", "STORAGE_UNAVAILABLE")
        .setCause(exception)
        .log("Order persistence failed");
~~~

Đây là snippet, giả định LOG là SLF4J 2.x Logger, orderId và exception đã có.

**setCause(exception)** gắn Throwable vào logging event; backend/encoder phải được cấu hình để ghi exception type/stack trace/cause chain theo chính sách. Chỉ ghép **exception.getMessage()** vào value như reason="..." thường làm mất stack trace và nguyên nhân gốc.

Một bản ghi JSON production có thể chứa:

~~~json
{
  "level": "ERROR",
  "event": "order.persist.failed",
  "orderId": "ORD-17",
  "reasonCode": "STORAGE_UNAVAILABLE",
  "exception": {
    "type": "java.lang.IllegalStateException",
    "message": "Storage unavailable"
  }
}
~~~

Đây là **schema ví dụ**, không phải output tự động của mọi backend. Phần stack trace và cause chain có thể được lưu dưới trường khác theo encoder.

**Tránh log cùng một lỗi ở mọi tầng:** repository ghi ERROR, service rethrow rồi ghi ERROR, controller lại ghi ERROR sẽ tạo nhiều event từ một sự cố. Hãy chọn một **ranh giới xử lý hiểu kết quả cuối cùng** để ghi lỗi chính, các tầng khác giữ cause và chỉ bổ sung sự kiện khi thực sự có retry/fallback quan trọng.

**Không biến message ngoại lệ thành reasonCode.** Error message có thể thay đổi và chứa dữ liệu nhạy cảm. Nên dùng mã lỗi ổn định riêng.

## 14. Logging key-value không phải là metric

Có thể tìm/đếm từ log:

~~~text
event=inventory.retry dependency=stock attempt=2
~~~

Nhưng không nên dùng log chi tiết cực lớn làm phương án duy nhất để đo traffic hoặc latency.

**Log** phù hợp để trả lời “sự kiện cụ thể nào đã xảy ra với request/job này?”. **Metric** phù hợp đo phân phối, tỷ lệ lỗi, throughput hoặc latency aggregate. **Trace** phù hợp theo dõi đường đi qua nhiều dịch vụ.

Bẫy phổ biến:

- Gắn **orderId, userId, requestId** thành **metric label** gây **high cardinality** và quá nhiều time-series.
- Cho mọi giá trị ID vào field log có thể hữu ích để tìm kiếm, nhưng vẫn phải quản lý **index cardinality, chi phí ingest và retention**.
- Biến **giá trị của người dùng thành key name**, ví dụ có một trường mới cho từng userId. Điều này khiến schema phát triển không kiểm soát.
- Ghi hàng nghìn event INFO trong vòng lặp để đếm số lượng, thay vì metric/batch summary phù hợp.

**Phân biệt key cardinality và value cardinality:** key nên nằm trong một tập trường ổn định; value như requestId có thể rất nhiều giá trị duy nhất nhưng cần chọn những field thực sự đáng index hoặc truy vấn theo chính sách của log platform.

## 15. Schema evolution: khi thay đổi key hoặc kiểu

Khi ứng dụng phát hành phiên bản mới, logging schema cũng là một giao diện được dashboard, alert và truy vấn sử dụng.

Ví dụ ban đầu:

~~~json
{"event":"request.completed","durationMs":120}
~~~

Nếu phiên bản mới đổi thành:

~~~json
{"event":"request.completed","duration":"120ms"}
~~~

dashboard đang so sánh **durationMs > 500** có thể không còn đúng. Cách tốt hơn là giữ key/kiểu ổn định hoặc có kế hoạch migration rõ.

Những quy tắc hữu ích:

1. **Thêm trường tùy chọn** thường dễ tương thích hơn đổi tên một field cốt lõi.
2. **Không thay đổi kiểu** mà không cập nhật parser/index mapping.
3. **Không tái sử dụng một tên key cho ý nghĩa khác**.
4. **Đặt schemaVersion** khi event format có thay đổi không tương thích đáng kể.
5. **Tài liệu hóa event name và field bắt buộc**, không chỉ “logger sẽ in gì”.
6. **Có test snapshot/schema** cho những event quan trọng; xác minh cả phiên bản cũ và mới trong giai đoạn rollout.
7. **Chú ý null/absence** khi chuyển đổi: một số hệ thống tự bỏ field null, một số giữ.
8. **Thống nhất đơn vị thời gian/tiền/dung lượng** và cách tạo timestamp.
9. **Không để localization** thay đổi event name hoặc reasonCode. Ngôn ngữ hiển thị có thể để ở message riêng.
10. Nếu muốn loại field, cập nhật dashboard, alert, pipeline ETL và tài liệu trong cùng quy trình.

Log schema nên được quản lý gần giống API dữ liệu: cần tính tương thích, kiểm thử và người chịu trách nhiệm.

## 16. Bảo mật, dữ liệu cá nhân và log injection

Structured logging không có nghĩa an toàn mặc định. Thực tế key-value khiến dữ liệu **dễ truy vấn hơn**, vì vậy sai sót khi ghi secret có thể nguy hiểm hơn log text khó parse.

**Những dữ liệu nên tránh ghi:**

- Password, token, API key, cookie, authorization header.
- Số thẻ, dữ liệu tài chính cá nhân, tài liệu định danh.
- Nội dung nguyên vẹn của request/response nhạy cảm.
- PII không cần cho chẩn đoán.
- SQL parameter hoặc exception message chứa secret.

**Một số nguyên tắc:**

1. **Data minimization:** chỉ ghi field cần thiết; không ghi cả object rồi hy vọng encoder tự che.
2. **Redaction/masking có kiểm thử:** nếu phải che, bảo vệ mọi đích (console/file/network), không chỉ một PatternLayout.
3. **Escape dữ liệu không tin cậy:** newline/control characters có thể tạo log giả hoặc phá định dạng key=value. JSON encoder chuẩn giúp escaping nhưng vẫn cần chính sách schema.
4. **Không dùng input người dùng làm key**: tránh tạo cấu trúc field bất định hoặc chiếm key đặc biệt của hệ thống.
5. **Hạn chế độ dài value** với payload không tin cậy, ngăn log amplification và tiêu thụ storage không cần thiết.
6. **Thống nhất quyền truy cập** cho collector, dashboard, archive và backup.
7. **Đặt retention** cho từng loại log theo chính sách và khả năng truy vấn cần thiết.
8. **Đảm bảo audit log cần thiết** không bị filter/sampling vô tình bỏ.
9. Nếu có dữ liệu multi-tenant, chính sách phân vùng/truy cập cần tránh rò thông tin giữa các tenant.
10. Không coi mọi UUID/ID là vô hại; một số ID vẫn liên kết được với người dùng.

**Lưu ý về format:** đối với text dạng key=value, phải có quy tắc quote/escape rõ ràng. Ví dụ value **Nguyễn An** có dấu cách cần được bao đúng định dạng parser; value chứa **dấu ngoặc kép** cũng phải escape. Không tự nối bằng dấu cách rồi khẳng định parser sẽ nhận chính xác.

## 17. Hiệu năng và độ tin cậy

Ghi thêm metadata tạo công việc bổ sung cho ứng dụng, nhưng có thể giảm chi phí phân tích về sau. Những điểm cần đánh giá:

- **Disabled level:** SLF4J fluent API hạn chế làm việc khi mức tắt; nhưng các biểu thức đối số tốn kém vẫn được Java đánh giá nếu bạn tự gọi trước.
- **Allocation:** tạo Map mới cho mỗi sự kiện rất thường xuyên có thể tốn bộ nhớ/GC. Dùng khả năng structured logging của backend và benchmark ở hot path.
- **Serialization:** encoder JSON thực thi escaping/format/nhận kiểu; performance phụ thuộc backend và schema.
- **Async logging:** có thể giảm thời gian thread nghiệp vụ chờ I/O nhưng thêm queue, overflow policy và shutdown/drain.
- **Log volume:** ghi mỗi bước DEBUG vào production có thể tăng chi phí ingest/index; dùng level và sampling phù hợp với loại event.
- **Buffer/flush:** ghi JSON ra console thành công chưa đồng nghĩa log được collector lưu bền.
- **Thứ tự event:** nhiều producer có thể tạo log xen kẽ; dùng requestId/traceId, không suy ra toàn bộ causal order từ vị trí dòng.
- **Mutable data:** đừng truyền Map mutable rồi thay đổi sau khi enqueue đến async backend; nên snapshot giá trị khi phát event.
- **Nhiều Appender/Handler:** cùng event có thể bị ghi hai lần; cần kiểm tra additivity và routing.

**Nếu event thuộc audit hoặc giao dịch không được phép mất**, cần đánh giá riêng chính sách delivery/durability. Console/logging backend thông thường không thay thế transaction log hoặc cơ chế lưu audit có tính toàn vẹn.

## 18. Kiểm thử structured key-value logging

### A. Unit test cho schema

- Event **order.accepted** phải có **event, orderId, quantity, paid**.
- **quantity** là number, **paid** là boolean sau khi parse JSON.
- **orderId** giữ nguyên kiểu String và không mất số 0 đầu.
- Các field bắt buộc không bị null nếu schema không cho phép.
- Không có **duplicate keys** và key dựa vào input người dùng.
- Khi value có quote, backslash, newline, Unicode, JSON phải hợp lệ và parse lại được chính xác.
- Không có password/token/payload nhạy cảm.
- Event name/reasonCode không bị thay đổi bởi ngôn ngữ UI.

### B. Integration test qua backend thực

- SLF4J 2.x có **một provider** tương thích ở runtime.
- Logback PatternLayout thực sự xuất **%kvp** nếu đang chọn text KV.
- Với JSON encoder, key-value được map vào **các trường JSON đúng kiểu**, không chỉ thành chuỗi message.
- Với Log4j 2, kiểm tra **MapMessage/ThreadContext** có được JSON Template Layout lấy vào template như dự kiến.
- Timestamp, level, Throwable và correlation IDs đúng.
- Có log ERROR chứa stack trace/cause, nhưng không lộ secret.
- Khi logger level bị chặn, event không xuất; khi được bật lại, event đầy đủ.
- Collector nhận được một JSON object/event, không phân tách sai bởi newline.
- Không xuất trùng do nhiều appender/bridge.

### C. Test concurrency và async

- Nhiều request cùng lúc không bị lẫn requestId.
- MDC/ThreadContext được làm sạch sau khi xử lý.
- Sau khi chuyển Executor/CompletableFuture, context propagation hoạt động theo thiết kế.
- Khi queue đầy hoặc writer chậm, overflow policy có thể quan sát được.
- Shutdown đúng cách để drain những event cần giữ.

Với ví dụ Java 17 ở mục 8, có thể chuyển **stderr** sang file rồi dùng một JSON parser chuẩn để kiểm tra mỗi dòng. Không chỉ so chuỗi nếu yêu cầu là **schema/kiểu dữ liệu**: parse JSON thực sẽ phát hiện key trùng, số bị biến thành chuỗi và JSON escape sai.

## 19. Troubleshooting: vì sao key-value không thành field?

| Hiện tượng | Nguyên nhân thường gặp | Cách xử lý |
| --- | --- | --- |
| Log hiển thị **orderId=...** nhưng không tìm được field orderId | Đó chỉ là message String hoặc collector không parse | Dùng structured event API và JSON encoder/parser phù hợp |
| SLF4J addKeyValue không xuất | Backend/layout bỏ key-value hoặc provider không tương thích | Kiểm tra provider, PatternLayout/JSON encoder |
| Quên gọi .log() sau builder | Fluent event chưa được phát | Luôn kết thúc bằng log() |
| Logback chỉ có %msg | Pattern không chứa %kvp | Cấu hình %kvp hoặc JSON encoder hỗ trợ |
| JSON có "quantity":"2" | Giá trị bị stringify | Giữ number trong event/encoder, kiểm tra mapping |
| Một key có nhiều giá trị bất thường | Trùng tên hoặc schema không ổn định | Thiết kế quy tắc duplicate key rõ |
| MDC requestId không hiện | Backend layout chưa lấy MDC hoặc thiếu context | Cấu hình %X/encoder và scope MDC |
| requestId từ request A xuất ở B | Thread pool tái sử dụng, không dọn MDC | Close/clear ở finally và propagate đúng |
| Log4j MapMessage không có field mong đợi | Template/layout không đọc MapMessage theo kỳ vọng | Kiểm tra message resolver và template |
| Output JSON không hợp lệ | Tự nối chuỗi sai escape/control chars | Sử dụng JSON encoder/serializer chuẩn |
| Tiếng Việt lỗi dấu | Charset writer/collector/viewer không khớp | Dùng UTF-8 end-to-end |
| Dashboard lỗi sau deploy | Key hoặc kiểu bị đổi | Quản lý schema evolution, test contract |
| Index chi phí tăng mạnh | Nhiều field hoặc giá trị cardinality cao | Kiểm soát schema, indexing và retention |
| Exception thiếu stack trace | Chỉ log exception message hoặc encoder bỏ Throwable | Truyền Throwable, test cause chain |
| Log lộ token | Ghi raw payload/secret | Giảm dữ liệu tại nguồn, redaction và kiểm soát quyền |
| Một event xuất hai lần | Nhiều AppenderRef/provider/collector source | Kiểm tra routing/additivity |
| Không thấy log trên platform | stdout/stderr chưa được thu thập hoặc collector lỗi | Xác minh pipeline end-to-end |

**Trình tự chẩn đoán:** xác định API phát log → provider/backend → layout/encoder → stdout/stderr/file → collector/parser → schema/index/search query. Đừng chỉ nhìn dấu bằng trong message và kết luận đã có structured log.

## 20. Lỗi thiết kế thường gặp

**Lỗi 1 — Tự ghép key=value rồi nghĩ rằng log có metadata riêng.** Nếu backend chỉ thấy một String, collector phải parse text. Dùng logging event metadata và encoder phù hợp khi cần typed fields.

**Lỗi 2 — Dùng mỗi lần một tên key khác nhau.** order_id, orderId, orderID khiến dashboard khó duy trì. Chọn schema thống nhất.

**Lỗi 3 — Dùng value động làm key.** Mỗi requestId thành tên một field gây bùng nổ schema và index mapping. Đặt requestId ở **giá trị** của một key cố định.

**Lỗi 4 — Đổi number thành string.** Điều kiện quantity > 10 không đáng tin nếu parser xem nó là text. Giữ kiểu dữ liệu đến đầu ra cuối.

**Lỗi 5 — Đặt mọi dữ liệu trong MDC.** MDC phù hợp cho context của request; quantity, attempt và outcome riêng của event nên gắn theo event.

**Lỗi 6 — Không dọn MDC khi dùng thread pool.** Dữ liệu request có thể bị gắn nhầm sang request khác.

**Lỗi 7 — Dùng message tự do thay event code.** Message đổi theo ngôn ngữ và bản phát hành; event code nên ổn định.

**Lỗi 8 — Log toàn bộ object.** ToString() có thể tốn CPU, xuất dữ liệu nhạy cảm và phá định dạng/kiểu dữ liệu.

**Lỗi 9 — Quên Throwable.** Chỉ lưu exception message làm mất stack trace và cause chain, gây khó điều tra.

**Lỗi 10 — Nghĩ JSON nào cũng có cấu trúc giống nhau.** JSON hợp lệ không đồng nghĩa schema phù hợp hay template lấy đúng metadata.

**Lỗi 11 — Không kiểm tra collector.** Backend tạo key-value đúng nhưng collector có thể lưu cả dòng thành một message string.

**Lỗi 12 — Không quản lý retention và quyền đọc.** Structured fields dễ truy vấn, vì vậy lộ secret/PII có thể lan rộng hơn.

## 21. Checklist áp dụng key-value log cho ứng dụng Java

1. **Xác định mục tiêu:** muốn đọc tại terminal, tìm theo field, thống kê, alert hay correlation?
2. **Định nghĩa schema** gồm event, timestamp, level, service và trường nghiệp vụ quan trọng.
3. **Quy định tên và kiểu dữ liệu** nhất quán, có đơn vị cho durationMs, bytes và tiền.
4. **Chọn logging API phù hợp:** SLF4J 2.x addKeyValue, Log4j MapMessage/ThreadContext, hoặc cơ chế custom/JUL khi có lý do.
5. **Chọn một backend/provider thực sự** và encoder/layout giữ được metadata theo yêu cầu.
6. **Chọn format output**: text key=value có parser rõ hoặc JSON/NDJSON có schema.
7. **Tách event fields khỏi request context** như requestId/traceId, quản lý MDC đúng vòng đời.
8. **Giữ Throwable và cause chain** cho lỗi, tránh log trùng ở nhiều tầng.
9. **Tránh secret và dữ liệu nhạy cảm**, escape input và giới hạn kích thước field.
10. **Kiểm soát cardinality và log volume**; không dùng userId/orderId làm key name hay metric label tùy tiện.
11. **Test kiểu dữ liệu sau parse**, không chỉ nhìn text log.
12. **Test toàn pipeline** từ Logger đến collector, dashboard và alert.
13. **Quản lý schema evolution** khi đổi tên, kiểu hoặc semantics.
14. **Đánh giá throughput, async, queue và retention** theo tải production.
15. **Ghi tài liệu event catalog** để người phát triển và vận hành dùng cùng quy ước.

**Kết luận:** **Key-value log** biến một bản ghi từ câu văn khó xử lý thành tập trường có tên và kiểu rõ ràng. Giá trị lớn nhất không nằm ở việc thêm dấu **=**, mà ở việc **đưa dữ liệu vào logging event đúng cách, giữ schema nhất quán, encode an toàn và xác minh collector parse thành các field thật sự**.

## 22. Tài liệu tham khảo chính thức

- [SLF4J User Manual — Fluent Logging API](https://www.slf4j.org/manual.html): atInfo(), addKeyValue(), addArgument() và provider.
- [Logback — Layouts](https://logback.qos.ch/manual/layouts.html): %kvp, %maskedKvp và MDC trong PatternLayout.
- [Apache Log4j 2 — Messages](https://logging.apache.org/log4j/2.x/manual/messages.html): MapMessage, StringMapMessage và StructuredDataMessage.
- [Apache Log4j 2 — Thread Context](https://logging.apache.org/log4j/2.x/manual/thread-context.html): ThreadContext Map, CloseableThreadContext và propagation.
- [Apache Log4j 2 — JSON Template Layout](https://logging.apache.org/log4j/2.x/manual/json-template-layout.html): JSON encoding theo template, resolver và module bổ sung.
- [Oracle Java 17 — Logger](https://docs.oracle.com/en/java/javase/17/docs/api/java.logging/java/util/logging/Logger.html): phát LogRecord, tham số và Throwable.
- [Oracle Java 17 — LogRecord](https://docs.oracle.com/en/java/javase/17/docs/api/java.logging/java/util/logging/LogRecord.html): metadata của log event trong JUL.
- [Oracle Java 17 — ConsoleHandler](https://docs.oracle.com/en/java/javase/17/docs/api/java.logging/java/util/logging/ConsoleHandler.html): ghi log ra System.err và vòng đời Handler.
