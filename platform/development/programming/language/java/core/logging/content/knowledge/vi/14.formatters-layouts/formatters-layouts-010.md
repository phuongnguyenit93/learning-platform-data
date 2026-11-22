# Ổn định format log — Formatter, Layout và hợp đồng dữ liệu log trong Java

## 1. Khái niệm

**Ổn định format log** nghĩa là giữ cách biểu diễn một sự kiện log **nhất quán và có hợp đồng rõ ràng**: tên trường, kiểu dữ liệu, đơn vị, định dạng thời gian, level, cách biểu diễn lỗi, cách escape ký tự và quy ước version. Mục đích là giúp người đọc, bộ thu thập, công cụ tìm kiếm, dashboard và cảnh báo hiểu log đúng qua nhiều phiên bản ứng dụng.

Một log message có thể thay đổi giá trị theo mỗi request nhưng vẫn có format ổn định. Ví dụ minh họa:

~~~text
2026-11-09T10:15:00.125Z INFO service=order-api event=order.created requestId=req-17 outcome=success durationMs=18
2026-11-09T10:15:01.750Z WARN service=order-api event=payment.retry requestId=req-18 reason=timeout attempt=2
~~~

Các dòng trên là **dữ liệu minh họa**, không phải output mặc định của thư viện Java. Điều ổn định là các trường **service, event, requestId, outcome, durationMs**, còn giá trị và timestamp là dữ liệu động.

Một format log không ổn định có thể thay đổi theo cảm hứng:

~~~text
Payment error!
Thanh toán thất bại do timeout
Could not pay. Will retry.
~~~

Ba thông điệp có thể đề cập cùng một loại vấn đề nhưng rất khó tìm hoặc thống kê bằng một bộ lọc nhất quán. Dùng **event code** và **error code** ổn định giúp giảm phụ thuộc vào câu chữ:

~~~text
event=payment.failed errorCode=PAYMENT_TIMEOUT outcome=failure
~~~

**Ổn định không có nghĩa mọi byte luôn giống nhau.** Dữ liệu request, thời điểm, Thread, ID và lỗi thực tế luôn có thể đổi. Hợp đồng phải ổn định ở **schema và ngữ nghĩa**, không phải ở toàn bộ giá trị.

## 2. Tại sao format ổn định là yêu cầu vận hành?

Log không chỉ được đọc trong IDE. Trong production, log thường đi qua nhiều thành phần:

~~~text
Java application
      |
      v
Logger + LogRecord / LoggingEvent
      |
      v
Formatter / Layout / Encoder
      |
      v
Console / File / Stream
      |
      v
Collector / Parser / Indexer
      |
      v
Search / Dashboard / Alert / Investigation
~~~

Một thay đổi ở producer có thể ảnh hưởng các consumer ở cuối tuyến:

1. **Tìm kiếm:** truy vấn event=payment.failed không còn khớp khi producer tự đổi tên thành event=payment.error.
2. **Dashboard:** trường durationMs đổi thành latency hoặc đổi từ số sang chuỗi; biểu đồ mất dữ liệu mới.
3. **Alert:** bộ lọc chỉ hiểu ERROR, nhưng một nhóm service đổi trường level hoặc gửi chuỗi khác.
4. **Tương quan:** các service không thống nhất requestId/traceId nên không truy ra được toàn bộ hành trình request.
5. **So sánh lịch sử:** dữ liệu trước và sau triển khai có schema khác nhau, phải viết nhiều parser.
6. **Bảo mật:** việc tự ý in object hoặc thêm field mới có thể khiến dữ liệu cá nhân/bí mật được thu thập ngoài dự kiến.
7. **Chi phí:** log dài bất thường, stack trace multiline và payload lớn gây tăng I/O, lưu trữ và thời gian truy vấn.

Do đó, format log nên được coi là **hợp đồng dữ liệu có kiểm thử**, đặc biệt khi dashboard, cảnh báo hoặc các ứng dụng bên ngoài phụ thuộc vào nó.

## 3. Message, log record, formatter, layout, encoder khác nhau thế nào?

| Thành phần | Vai trò | Ví dụ |
| --- | --- | --- |
| **Log message** | Mô tả một sự kiện cho con người | Order accepted |
| **Log record/event** | Dữ liệu sự kiện trước khi xuất | Level, logger, message, thời gian, Throwable, MDC |
| **Schema/format** | Quy ước trường, kiểu, đơn vị và mã sự kiện | schemaVersion, event, durationMs |
| **Formatter** | Chuyển LogRecord thành chuỗi | java.util.logging.Formatter của JUL |
| **Layout** | Trình bày một sự kiện theo dạng text | PatternLayout của Logback/Log4j 2 |
| **Encoder** | Biến dữ liệu layout/sự kiện thành byte gửi đến đích | PatternLayoutEncoder hoặc JSON encoder |
| **Handler/Appender** | Ghi tới console, file hoặc đích khác | JUL StreamHandler, Logback ConsoleAppender |
| **Collector/parser** | Đọc, phân tách và hiểu log | Pipeline nhận JSON Lines hoặc text |

Trong **JUL** (java.util.logging), thường gặp Logger → Handler → Formatter. Trong **SLF4J + Logback**, thường gặp Logger → Appender → Encoder/Layout. Chúng là API khác nhau; không chép nguyên cấu hình giữa hai hệ.

**Formatter quyết định hình thức biểu diễn; schema quyết định ý nghĩa của dữ liệu.** Pattern nhìn đẹp nhưng field name thay đổi tùy module vẫn là một hệ thống thiếu ổn định.

## 4. Những yếu tố cần cố định trong một schema log

### 4.1. Tên trường và ý nghĩa

Một bộ trường tham khảo:

| Tên | Ví dụ | Hợp đồng đề xuất |
| --- | --- | --- |
| schemaVersion | 1 | Phiên bản schema, dạng số nguyên |
| timestamp | 2026-11-09T10:15:00.125Z | Thời điểm event, có timezone |
| level | INFO | Mức log theo quy ước chuẩn hóa |
| service | order-api | Tên dịch vụ phát event |
| logger | demo.order.OrderService | Tên logger |
| event | order.created | Mã loại sự kiện ổn định |
| requestId | req-17 | ID tương quan nếu có |
| traceId | 0123abcd... | ID trace khi hệ thống tracing hỗ trợ |
| outcome | success | Tập giá trị được quy định |
| errorCode | PAYMENT_TIMEOUT | Mã lỗi ổn định |
| durationMs | 18 | Số thời lượng, đơn vị millisecond |
| message | Order accepted | Mô tả tự nhiên |
| exception | object/string có quy tắc | Thông tin loại lỗi, cause, stack trace |

Đây **không phải schema bắt buộc**. Tổ chức có thể dùng cách đặt tên khác như service.name, trace_id; quan trọng là **không trộn nhiều quy ước mà không có mapping**.

Một số trường có thể tùy chọn theo loại event. Ví dụ startup event không cần requestId, còn request event thường cần. Quy định rõ trường **bắt buộc**, **tùy chọn** và cách diễn giải dữ liệu thiếu.

### 4.2. Kiểu dữ liệu

- **durationMs** nên là một số, không lúc là 18, lúc là "18ms".
- **attempt** là số nguyên trong tình huống đếm lần thử.
- **outcome** là chuỗi thuộc một bộ giá trị có tài liệu, ví dụ success/failure.
- **requestId** là chuỗi và có thể có số 0 ở đầu; không ép thành số.
- **statusCode** nếu biểu diễn HTTP status có thể là số; không lúc là 503 lúc là "HTTP 503".

Nếu một giá trị không tồn tại, phân biệt rõ **trường bị thiếu**, **null** và **chuỗi rỗng**. Chúng có thể được consumer diễn giải khác nhau. Không thay đổi ý nghĩa của cùng một trường qua các phiên bản.

### 4.3. Đơn vị, số và locale

Nên ghi đơn vị vào tên trường: **durationMs**, **sizeBytes**, **timeoutMs**. Việc đổi đơn vị của trường mà giữ nguyên tên là thay đổi ngữ nghĩa nguy hiểm.

Với số thập phân, tránh định dạng theo locale làm **1.5** thành **1,5** trong trường mà parser kỳ vọng dấu chấm. Với máy cần xử lý kiểu số, nên dùng JSON number và schema rõ ràng thay vì ghép số vào thông điệp tự do.

### 4.4. Timestamp và timezone

Với log từ nhiều máy, nên thống nhất một profile thời gian có múi giờ rõ, ví dụ UTC:

~~~text
2026-11-09T10:15:00.125Z
~~~

Đây là một dạng thuộc họ **ISO-8601/RFC 3339**. Chỉ nói "ISO-8601" vẫn chưa đủ: cần xác định timezone, độ chính xác, trường timestamp là **thời điểm phát event** hay **thời điểm collector nhận**.

Không mặc định ngày **11/09/2026** là ngày 11 tháng 9 hay 9 tháng 11; định dạng này phụ thuộc locale. Không coi thứ tự nhận log giữa các host là thứ tự toàn cục tuyệt đối vì có thể có clock skew, buffering và network delay.

### 4.5. Mã sự kiện ổn định

Ví dụ:

~~~text
event=order.created
event=payment.retry
event=payment.failed
event=job.completed
~~~

Không đưa orderId/requestId riêng lẻ vào **tên event** như payment.failed.req-42. Giữ tên event cho **loại sự kiện** và đặt ID ở trường riêng.

Một thay đổi từ **payment.retry** sang **payment.failed** không chỉ là sửa câu chữ: chúng mô tả hai loại sự kiện khác nhau. Nếu ý nghĩa event thay đổi thật, cần cân nhắc mã mới hoặc nâng version schema.

### 4.6. Level nhất quán

SLF4J/Logback thường dùng **TRACE, DEBUG, INFO, WARN, ERROR**; JUL dùng **FINEST, FINER, FINE, CONFIG, INFO, WARNING, SEVERE**. Nếu nhiều backend gửi vào một hệ thống, có thể cần **quy tắc normalize level** ở producer hoặc collector.

Không tự cho rằng tên **WARNING** của JUL và **WARN** của Logback hoàn toàn tương đồng về tất cả semantics. Chúng gần nhau về mục đích, nhưng mapping cần được quy định và kiểm thử.


## 5. Chọn cách biểu diễn: text, key=value và JSON Lines

### 5.1. Text bằng pattern

~~~text
2026-11-09T10:15:00.125Z INFO demo.OrderService - Order accepted
~~~

Dễ đọc và phù hợp cho console, bài tập hoặc ứng dụng nhỏ. Nhưng parser thường phải dựa vào dấu phân cách, vị trí và mẫu chuỗi; tên logger hoặc message chứa ký tự bất ngờ có thể làm parser hiểu sai.

### 5.2. key=value

~~~text
level=INFO service=order-api event=order.created requestId=req-17 durationMs=18 message="Order accepted"
~~~

Có thể tìm chuỗi và parse nếu thống nhất quy tắc quote/escape. Nhưng nếu message chứa dấu cách, dấu bằng hoặc xuống dòng, tự ghép chuỗi tùy ý sẽ làm bản ghi khó phân tích.

**Một định dạng key=value có thể ổn định**, nhưng cần đặc tả ranh giới giữa các cặp, cách mã hóa dấu nháy/backslash, kiểu dữ liệu và cách biểu diễn giá trị thiếu.

### 5.3. JSON Lines

Mỗi sự kiện được viết thành **một object JSON trên một dòng vật lý**:

~~~json
{"schemaVersion":1,"level":"INFO","service":"order-api","event":"order.created","requestId":"req-17","durationMs":18,"message":"Order accepted"}
~~~

JSON có lợi ích:

- Trường được nhận diện bằng tên thay vì cắt chuỗi message.
- Giá trị có thể là số, chuỗi, boolean, null hoặc object.
- Encoder phù hợp escape ký tự đặc biệt để có thể đọc từng dòng.
- Dễ kiểm thử theo schema và parse trong hệ thống thu thập tập trung.

Nhưng **JSON không tự bảo đảm dữ liệu được index hoặc truy vấn theo field**. Bộ thu thập phải parse, lưu và cấu hình mapping đúng. **Thứ tự key của JSON object không phải hợp đồng ngữ nghĩa**; consumer nên truy vấn theo tên key.

### 5.4. Newline, dấu nháy và Unicode

Giả sử message thật chứa hai dòng và dấu nháy:

~~~text
Timeout: retry "later"
Check gateway
~~~

Nếu chèn raw newline vào một bản ghi dự định chỉ có một dòng, collector có thể hiểu nhầm thành **hai event**. JSON Lines cần escape chuỗi để trở thành một dòng vật lý:

~~~json
{"event":"payment.failed","message":"Timeout: retry \"later\"\nCheck gateway"}
~~~

Trong dữ liệu JSON này, phần **\n** là hai ký tự escape biểu diễn newline bên trong giá trị message, không phải ký tự xuống dòng phân tách record.

Ngoài dấu nháy, encoder phải xử lý **backslash, control characters, Unicode và escape** đúng. Với exception/stack trace, có thể:

1. Dùng **multiline text**, đồng thời cấu hình collector ghép các dòng stack trace vào một event.
2. Dùng **single-line structured JSON**, lưu exception thành trường có escape newline bên trong.

Chọn một cách rõ ràng, không để lúc là JSON một dòng, lúc là text nhiều dòng mà collector vẫn dùng một parser duy nhất.

**Không nên tự nối string tạo JSON trong production.** Dùng encoder/serializer đã được kiểm thử, đặc biệt khi dữ liệu đến từ người dùng không tin cậy, có null hoặc ký tự Unicode bất thường.

## 6. Ví dụ Java 17+ chạy được: JUL Formatter tạo JSON Lines ổn định

Ví dụ này dùng **java.util.logging** của JDK, không cần dependency ngoài. Nó giải thích **Formatter** biến **LogRecord** thành bản ghi có trường cố định.

Schema demo có các trường: **schemaVersion, level, logger, event, requestId, outcome, durationMs, message**. durationMs là số; event và requestId tách khỏi message. Để output xác định hoàn toàn, demo **không in timestamp**; ứng dụng thật nên có timestamp chuẩn.

Tạo tệp **StableLogFormatDemo.java**:

~~~java
import java.util.Locale;
import java.util.logging.Formatter;
import java.util.logging.Handler;
import java.util.logging.Level;
import java.util.logging.LogRecord;
import java.util.logging.Logger;
import java.util.logging.StreamHandler;

public class StableLogFormatDemo {
    private static final Logger LOGGER =
            Logger.getLogger("demo.order");

    public static void main(String[] args) {
        LOGGER.setUseParentHandlers(false);
        LOGGER.setLevel(Level.INFO);

        Handler stdout = new StreamHandler(
                System.out, new StableJsonFormatter());
        stdout.setLevel(Level.INFO);
        LOGGER.addHandler(stdout);

        logEvent(Level.INFO, "order.created", "req-001",
                "success", 18L, "Order accepted");

        logEvent(Level.WARNING, "payment.failed", "req-002",
                "failure", 2500L,
                "Timeout: retry \"later\"\nCheck gateway");

        stdout.flush();
    }

    private static void logEvent(
            Level level, String event, String requestId,
            String outcome, long durationMs, String message) {

        LogRecord record = new LogRecord(level, message);
        record.setLoggerName(LOGGER.getName());
        record.setParameters(new Object[]{
                event, requestId, outcome, durationMs
        });
        LOGGER.log(record);
    }

    private static final class StableJsonFormatter extends Formatter {
        @Override
        public String format(LogRecord record) {
            Object[] fields = record.getParameters();

            return "{"
                    + "\"schemaVersion\":1"
                    + ",\"level\":" + quote(record.getLevel().getName())
                    + ",\"logger\":" + quote(record.getLoggerName())
                    + ",\"event\":" + quote((String) fields[0])
                    + ",\"requestId\":" + quote((String) fields[1])
                    + ",\"outcome\":" + quote((String) fields[2])
                    + ",\"durationMs\":" + fields[3]
                    + ",\"message\":" + quote(record.getMessage())
                    + "}" + System.lineSeparator();
        }

        private static String quote(String value) {
            StringBuilder result =
                    new StringBuilder(value.length() + 2).append('"');

            for (int i = 0; i < value.length(); i++) {
                char c = value.charAt(i);
                switch (c) {
                    case '"' -> result.append("\\\"");
                    case '\\' -> result.append("\\\\");
                    case '\b' -> result.append("\\b");
                    case '\f' -> result.append("\\f");
                    case '\n' -> result.append("\\n");
                    case '\r' -> result.append("\\r");
                    case '\t' -> result.append("\\t");
                    default -> {
                        if (c < 0x20) {
                            result.append(String.format(
                                    Locale.ROOT, "\\u%04x", (int) c));
                        } else {
                            result.append(c);
                        }
                    }
                }
            }
            return result.append('"').toString();
        }
    }
}
~~~

Biên dịch và chạy bằng **JDK 17 trở lên**:

~~~bash
javac -encoding UTF-8 StableLogFormatDemo.java
java StableLogFormatDemo
~~~

**Stdout của chương trình gồm chính xác hai dòng JSON** sau (mỗi dòng kết thúc bằng newline của hệ điều hành):

~~~json
{"schemaVersion":1,"level":"INFO","logger":"demo.order","event":"order.created","requestId":"req-001","outcome":"success","durationMs":18,"message":"Order accepted"}
{"schemaVersion":1,"level":"WARNING","logger":"demo.order","event":"payment.failed","requestId":"req-002","outcome":"failure","durationMs":2500,"message":"Timeout: retry \"later\"\nCheck gateway"}
~~~

Thông điệp thứ hai có một newline **trong giá trị Java String**, nhưng formatter escape thành **\n**, nên JSON vẫn là **một dòng vật lý** cho một sự kiện.

### Vì sao output như vậy?

1. **LOGGER.setLevel(Level.INFO)** cho phép INFO và WARNING; handler cũng chấp nhận hai mức này.
2. **logEvent(...)** tạo LogRecord, đặt logger name và các giá trị nghiệp vụ theo một hợp đồng tham số **chỉ của demo**.
3. **StableJsonFormatter** truy cập field và dựng object có tên trường cố định.
4. **quote(...)** escape dấu nháy, backslash, newline và control character phổ biến.
5. **setUseParentHandlers(false)** tránh handler của logger cha in thêm bản ghi với format khác.
6. **StreamHandler(System.out, ...)** ghi stdout; **JUL ConsoleHandler mặc định ghi stderr**, nên không nhầm hai handler.
7. **stdout.flush()** đẩy dữ liệu trong buffer ra stdout trước khi main kết thúc.

### Phạm vi của ví dụ

Đây là **formatter phục vụ minh họa**, không phải JSON encoder production:

- Cách lấy field từ **LogRecord.parameters** theo vị trí cố định chỉ đúng với các record do chính phương thức logEvent tạo. Không áp dụng tùy tiện cho LogRecord được tạo bởi thư viện khác.
- Các giá trị mẫu đã được kiểm soát, không phải bộ test đầy đủ về null, Unicode surrogate lỗi, kiểu dữ liệu xấu hoặc dữ liệu từ nguồn không tin cậy.
- Formatter demo không xử lý **Throwable**, timestamp hoặc context nâng cao. Production cần quy tắc bổ sung, đặc biệt với stack trace.
- Gọi String.format cho control character là cách minh họa dễ hiểu; hệ thống lưu lượng cao nên dùng JSON encoder/serializer đã kiểm thử.
- Chương trình dùng JUL để minh họa Formatter; **SLF4J/Logback** có API và level tên khác, không thể sao chép nguyên lớp Formatter vào Logback.

### Kiểm tra JSON Lines

Trên máy có Python 3, có thể chạy:

~~~bash
java StableLogFormatDemo > events.jsonl
python3 -c 'import json; [json.loads(line) for line in open("events.jsonl", encoding="utf-8")]'
~~~

Lệnh Python không in gì nếu mọi dòng parse JSON thành công, ngược lại sẽ báo lỗi. Đây chỉ là **công cụ kiểm tra file JSONL**, không phải dependency của ứng dụng Java.

**Không nên dùng mặc định python3 -m json.tool events.jsonl để giả định mọi phiên bản đều xử lý nhiều JSON object rời nhau trong một file**; đối với JSON Lines, nên parse từng dòng hoặc dùng công cụ hỗ trợ JSONL. Ngoài cú pháp JSON, còn cần test kiểu durationMs, event/schemaVersion và quy tắc dữ liệu thiếu.


## 7. Ổn định layout với Logback PatternLayoutEncoder

Trong ứng dụng dùng **SLF4J + Logback Classic**, dạng log văn bản thường được cấu hình qua **logback.xml**:

~~~xml
<configuration>
    <appender name="CONSOLE"
              class="ch.qos.logback.core.ConsoleAppender">
        <target>System.out</target>
        <encoder>
            <charset>UTF-8</charset>
            <pattern>level=%level logger=%logger thread=%thread message=%msg%n</pattern>
        </encoder>
    </appender>

    <root level="INFO">
        <appender-ref ref="CONSOLE"/>
    </root>
</configuration>
~~~

Đây là cấu hình Logback minh họa, **không phải cấu hình cho chương trình JUL ở mục 6**.

Một số conversion word thường gặp:

| Pattern | Ý nghĩa |
| --- | --- |
| %level | Level của event, ví dụ INFO/WARN/ERROR |
| %logger | Tên logger phát event |
| %thread | Tên thread |
| %msg | Message đã được định dạng tham số |
| %n | Ký tự xuống dòng |
| %d{...} | Timestamp theo pattern |
| %X{requestId} | Trường requestId của MDC nếu có |
| %ex / %throwable | Biểu diễn exception/stack trace tùy encoder |

Không phải cứ in **message=%msg** thì đã có structured logging. Nếu message chứa dấu cách, dấu bằng, newline hay chuỗi không tin cậy, parser key=value đơn giản có thể bị sai. Với schema có kiểu, nên dùng **JSON encoder** thực sự và thống nhất với bộ thu thập thay vì dựng chuỗi trông giống JSON bằng PatternLayout.

### SLF4J 2 và key-value logging

Mảnh code minh họa với SLF4J 2.x:

~~~java
// Đặt trong lớp đã khai báo LOG và có biến orderId.
LOG.atInfo()
        .addKeyValue("event", "order.created")
        .addKeyValue("orderId", orderId)
        .addKeyValue("outcome", "success")
        .log("Order accepted");
~~~

Phương thức addKeyValue biểu diễn các cặp thông tin có cấu trúc ở API, nhưng **không tự bảo đảm backend/encoder đã xuất chúng thành JSON hoặc collector đã lập chỉ mục**. Cần một cấu hình encoder phù hợp. Đoạn trên **không phải chương trình Java độc lập**, vì thiếu khai báo LOG và orderId.

Khi thay đổi layout, giữ nguyên tên và ngữ nghĩa các field có người tiêu thụ. Chỉ thay format hiển thị cho con người chưa chắc vô hại nếu backend trước đây đã được parse theo pattern.

## 8. Ổn định formatter trong JUL

JUL dùng **Formatter** ở phía Handler. Một lựa chọn sẵn có là **java.util.logging.SimpleFormatter**, hỗ trợ property định dạng:

~~~properties
java.util.logging.SimpleFormatter.format = %1$tFT%1$tT %4$s %3$s - %5$s%6$s%n
~~~

Trong SimpleFormatter, các đối số format tương ứng với thông tin như thời gian, nguồn phát, logger name, level, message và phần Throwable. Đây là **cú pháp java.util.Formatter trong JUL**, khác cú pháp %level/%logger của Logback.

Cần lưu ý:

- Property trên **không tự bảo đảm UTC**, vì timezone có thể phụ thuộc môi trường.
- Muốn tiếng Việt ổn định, kiểm tra encoding của ConsoleHandler/FileHandler và nơi nhận; có thể cấu hình UTF-8 phù hợp.
- Nếu chỉ in message mà không giữ phần Throwable, thông tin exception/stack trace có thể bị mất trong đầu ra.
- Logger/handler có level và filter; **formatter không thể phục hồi event đã bị lọc trước đó**.
- Khi tự viết Formatter, phải quy định rõ null, exception, newline, timezone, charset và schema version.

JUL và Logback đều có cơ chế định dạng nhưng không có nghĩa file logging.properties sẽ được Logback hiểu hoặc logback.xml sẽ cấu hình JUL thuần.

## 9. Versioning và khả năng tương thích của schema

Một format ổn định **vẫn có thể phát triển**. Điều quan trọng là thay đổi có chủ đích và không làm hỏng consumer đang chạy.

### Thay đổi thường dễ tương thích hơn

- Thêm một **trường tùy chọn** với tên/kiểu rõ ràng, consumer cũ bỏ qua được.
- Thêm một **event code mới** mang ý nghĩa riêng.
- Bổ sung metadata không làm đổi ý nghĩa các trường cũ.
- Sửa wording của message cho con người trong khi giữ event/error code ổn định và consumer không dựa vào literal message.

Ngay cả thêm trường tùy chọn cũng cần test: parser quá cứng có thể từ chối trường lạ.

### Thay đổi phá vỡ hợp đồng

| Thay đổi | Rủi ro |
| --- | --- |
| durationMs từ 18 thành "18ms" | Từ số sang chuỗi, query so sánh số hỏng |
| outcome=success thành outcome=ok | Giá trị enum cũ không còn khớp |
| event=payment.failed đổi tên | Alert theo event cũ không tìm được |
| timestamp từ UTC sang local time không offset | Consumer có thể hiểu sai thời gian |
| JSON Lines đổi thành multiline text | Parser một dòng/một object không nhận đúng |
| Bỏ requestId khỏi sự kiện request | Không còn liên kết được các log |
| errorCode chuyển từ trường riêng vào message | Không còn query chính xác theo field |

### Quy trình nâng schema

1. **Ghi rõ schema hiện tại**: tên trường, kiểu, đơn vị, enum, bắt buộc/tùy chọn và ví dụ.
2. **Phân loại thay đổi**: có tương thích với consumer cũ không?
3. **Gắn schemaVersion** hoặc cơ chế version được tổ chức thống nhất.
4. **Có kế hoạch migration**: ví dụ producer ghi đồng thời field cũ và mới trong một giai đoạn hoặc collector nhận hai version.
5. **Kiểm tra consumer**: dashboard, alert, parser, query, vận hành và công cụ kiểm toán.
6. **Triển khai có giám sát**: theo dõi parse error, số log bị drop, số event theo version.
7. **Loại định dạng cũ có kiểm soát** sau khi consumer đã sẵn sàng.
8. **Cập nhật test và tài liệu** để không tái tạo thay đổi không tương thích.

**schemaVersion không tự bảo đảm backward compatibility**. Nó chỉ đánh dấu hợp đồng nào được dùng; consumer vẫn phải biết cách đọc hoặc chuyển đổi từng version.

## 10. Những dữ liệu không nên biến thành khóa hợp đồng

Một vài thông tin có thể có ích cho debug nhưng thường thay đổi qua các bản build/runtime:

- **Source file/line number**: refactor làm số dòng thay đổi.
- **Tên method/class**: thay đổi khi tái cấu trúc hoặc chuyển module.
- **Thread name**: thread pool hoặc framework có thể thay đổi quy ước đặt tên.
- **Thứ tự dòng log giữa nhiều host**: collector và network có thể chuyển/nhận bất đồng bộ.
- **Thứ tự key trong JSON**: consumer nên lấy trường theo tên.
- **Lời mô tả tự nhiên**: bản dịch hoặc cách viết có thể thay đổi; dùng event/error code cho truy vấn ổn định.
- **Giá trị theo locale**: các ký tự phân tách thời gian/số có thể thay đổi theo máy.
- **Stack trace nguyên văn**: thay đổi khi code refactor, có thể chứa thông tin nhạy cảm.

Nên thiết kế **event code**, **errorCode**, **service/component**, **traceId/requestId**, **schemaVersion** và các trường có nghĩa cụ thể làm cơ sở truy vấn.

## 11. Correlation ID và ngữ cảnh đa luồng

Để nối các sự kiện cùng request chạy qua nhiều service, cần field tương quan nhất quán:

~~~json
{"schemaVersion":1,"level":"INFO","service":"checkout","event":"checkout.started","requestId":"req-42"}
{"schemaVersion":1,"level":"INFO","service":"pricing","event":"price.calculated","requestId":"req-42"}
{"schemaVersion":1,"level":"ERROR","service":"payment","event":"payment.failed","requestId":"req-42","errorCode":"PAYMENT_TIMEOUT"}
~~~

Đây là dữ liệu minh họa. Khi dùng SLF4J/Logback, MDC có thể giúp đưa requestId vào event:

~~~java
// Đoạn minh họa trong lớp đã có LOG:
try (org.slf4j.MDC.MDCCloseable ignored =
        org.slf4j.MDC.putCloseable("requestId", "req-42")) {
    LOG.info("event=checkout.started");
}
~~~

**MDC không tự truyền qua mọi CompletableFuture/thread pool/reactive task**. Phải propagate và dọn context đúng; nếu không request ID có thể bị mất hoặc lẫn giữa các request. Encoder và collector cũng phải thực sự xuất/parse trường đó.

Đừng dùng requestId/traceId duy nhất làm **metric label không giới hạn**, vì gây cardinality cao. Chúng thường phù hợp với log và trace; metrics nên dùng tập nhãn hữu hạn.


## 12. Bảo mật và dữ liệu nhạy cảm

Format ổn định giúp dữ liệu dễ được thu thập và tìm kiếm, nhưng có thể khiến thông tin nhạy cảm được index và lưu lâu hơn. Các nguyên tắc bắt buộc:

- Không ghi **password, access token, API key, private key, session cookie, dữ liệu thẻ thanh toán** dạng thô.
- Không mặc định ghi toàn bộ HTTP request/response body hoặc object.toString().
- Chọn **mã sự kiện, errorCode và correlation ID an toàn** thay cho payload lớn hoặc thông tin người dùng trực tiếp.
- Dùng encoder có **escaping** để phòng log injection: dữ liệu đầu vào có thể chứa newline hoặc ký tự điều khiển tạo dòng giả.
- Throwable/stack trace có thể chứa path, tham số và thông tin nội bộ; cần chính sách hạn chế/che và quyền truy cập phù hợp.
- Cấu hình retention/quyền truy cập cho console, file và nơi lưu tập trung.
- Theo dõi kích thước record, số event/giây và chi phí của trường mới khi thay schema.

**Chuyển text sang JSON không làm log tự động an toàn.** Bảo mật phụ thuộc dữ liệu được chọn để ghi, encoder, quyền truy cập và thời gian lưu.

## 13. Kiểm thử format như hợp đồng dữ liệu

Đừng chỉ test rằng logger có phát một chuỗi. Nên kiểm tra theo lớp:

1. **Tính parse được:** mỗi event JSON Lines tạo một object JSON hợp lệ.
2. **Escaping:** quote, backslash, newline, control char và dữ liệu Unicode được xử lý theo schema.
3. **Trường bắt buộc:** schemaVersion, timestamp, level, service/event khi hợp đồng yêu cầu.
4. **Kiểu dữ liệu:** durationMs là số, attempt là số nguyên, outcome thuộc enum hợp lệ.
5. **Timestamp:** timezone/precision đúng quy tắc, không phụ thuộc locale.
6. **Exception:** có thể lưu cause/stack trace đúng mà không phá ranh giới event.
7. **Correlation:** requestId xuất đúng, được propagate qua async và dọn context sau request.
8. **Level/filter:** DEBUG bị loại khi INFO, ERROR vẫn được ghi ở appender phù hợp.
9. **Collector:** truy vấn theo field có kiểu, không bỏ record, có chiến lược đọc nhiều schema version khi migration.
10. **Bảo mật:** không lộ token/secret và raw payload bị cấm.
11. **Truyền/độ bền:** biết log có thể bị trễ/drop; không dùng nó làm kho giao dịch có cam kết bền vững.
12. **Giới hạn chi phí:** log volume, file rotation và retention phù hợp.

### Golden test và dữ liệu động

**Golden-file test** có thể so sánh bản ghi mẫu để phát hiện thay đổi formatter. Nhưng timestamp, thread ID, requestId ngẫu nhiên sẽ khiến snapshot không ổn định nếu không kiểm soát. Có thể inject **Clock cố định**, normalize trường động hoặc parse và so object theo schema thay vì so nguyên văn toàn bộ JSON.

Ví dụ Java ở mục 6 cố ý không ghi timestamp để đầu ra xác định. **Production không nên bỏ timestamp chỉ vì muốn test dễ**; kiểm thử schema phải chấp nhận trường thời gian động trong giới hạn hợp đồng.

Với JSON, **thứ tự field không mang ngữ nghĩa**, vì vậy so object đã parse thường bền hơn so chuỗi byte; với text pattern dùng parser đặc thù, cần test ranh giới giữa các field.

## 14. Quy trình kiểm tra khi log bỗng khó tìm hoặc parse lỗi

1. Xác định **producer/service và bản triển khai** bắt đầu phát log khác.
2. So sánh một event tốt và một event lỗi: tên field, kiểu, thiếu null, message có newline hoặc quote không?
3. Xem schemaVersion và lịch sử thay đổi encoder/formatter.
4. Kiểm tra backend đang hoạt động: JUL Formatter, Logback PatternLayoutEncoder hay JSON encoder?
5. Kiểm tra charset, timezone và precision.
6. Kiểm tra additivity/handler/appender: cùng event có đi qua hai tuyến formatter khác nhau không?
7. Kiểm tra parser phía collector đang chờ JSON Lines hay pattern text nào.
8. Kiểm tra truncation, buffer, sampling và log bị drop hoặc quá thời gian lưu.
9. Đối chiếu dashboard/alert/query để biết consumer nào bị ảnh hưởng.
10. Khắc phục theo hợp đồng schema và migration; tránh chỉ sửa tạm truy vấn rồi bỏ qua producer.

**Không tìm được một dòng log không đủ chứng minh code chưa chạy**, vì sự kiện còn có thể bị chặn bởi level/filter, lỗi I/O hoặc không được collector lưu.

## 15. Lỗi thường gặp

| Lỗi | Hậu quả | Cách tránh |
| --- | --- | --- |
| Dùng message tự nhiên làm khóa sự kiện | Đổi câu chữ làm alert mất dữ liệu | Dùng event/error code ổn định |
| durationMs có lúc số, lúc "18ms" | Query số hoạt động sai | Cố định đơn vị và kiểu |
| Timestamp không rõ timezone | Không xác định chính xác lúc xảy ra | Dùng UTC/offset tường minh |
| Đổi userId thành user_id không migration | Consumer cũ không thấy trường | Schema versioning và rollout |
| In raw newline vào JSON Lines | Một event thành nhiều dòng vật lý | Dùng escaping/JSON encoder |
| Chỉ dùng text pattern nhưng tưởng có field JSON | Collector không parse field chính xác | Structured encoder và parser |
| Đổi formatter nhưng bỏ Throwable | Không thấy stack trace | Kiểm thử exception representation |
| So sánh vị trí field trong JSON | Hỏng khi thứ tự key đổi | Truy vấn theo tên field |
| Lấy ThreadLocal/MDC qua async không propagate | Mất hoặc sai requestId | Truyền và dọn context |
| Hai appender xuất hai format khác nhau | Dashboard khó parse, log trùng | Quản lý tuyến appender/additivity |
| Snapshot test chứa thời điểm hiện tại | Test lỗi không ổn định | Cố định clock/normalize |
| Log raw token hoặc request body | Dữ liệu nhạy cảm bị index | Data minimization và masking |
| Bật DEBUG rộng, log lớn | Chi phí I/O và lưu trữ tăng | Bật chọn lọc, đo hiệu năng |

## 16. Bài tập và câu hỏi tự kiểm tra

**Câu 1.** Ổn định format có yêu cầu hai lần chạy cho cùng timestamp và requestId không?

**Đáp án:** Không. Dữ liệu động có thể thay đổi; schema, tên trường, kiểu, đơn vị, cách encode và ý nghĩa phải nhất quán.

**Câu 2.** Vì sao durationMs=18 dễ xử lý hơn duration="18ms"?

**Đáp án:** Tên trường nêu đơn vị và giá trị số cho phép so sánh khi collector parse đúng kiểu; chuỗi "18ms" cần tách đơn vị và dễ thay đổi.

**Câu 3.** Một message có newline có thể nằm trong JSON Lines không?

**Đáp án:** Có, nếu newline trong giá trị đã được escape thành \n để bản ghi vẫn là một dòng vật lý.

**Câu 4.** Bổ sung một trường tùy chọn vào JSON có luôn tương thích không?

**Đáp án:** Không tuyệt đối. Consumer linh hoạt có thể bỏ qua, nhưng parser cũ quá nghiêm ngặt có thể từ chối trường lạ; vẫn cần kiểm thử.

**Câu 5.** Có nên dựng alert bằng cách tìm đúng câu “Payment failed” không?

**Đáp án:** Thường không. Message dành cho con người có thể đổi; nên dùng event code và errorCode ổn định.

**Câu 6.** JUL Formatter khác Logback PatternLayoutEncoder thế nào?

**Đáp án:** JUL Formatter chuyển LogRecord thành chuỗi; Logback dùng layout/encoder để biểu diễn event. Hai API không có cấu hình tương thích trực tiếp.

**Câu 7.** Đổi timestamp từ UTC sang local time không offset nhưng giữ tên timestamp có thể gây vấn đề gì?

**Đáp án:** Consumer có thể hiểu sai thời điểm và so các service không chính xác; đó là thay đổi ngữ nghĩa có thể phá hợp đồng.

**Câu 8.** Chỉ thêm schemaVersion có giúp mọi hệ thống tự hiểu format mới không?

**Đáp án:** Không. Consumer phải hỗ trợ hoặc chuyển đổi version; cần chiến lược migration.

**Câu 9.** Nếu hai object JSON có cùng key/value nhưng thứ tự key khác nhau thì có khác về ngữ nghĩa không?

**Đáp án:** Thông thường không. JSON object không định nghĩa thứ tự key là ngữ nghĩa; truy vấn theo tên trường.

**Câu 10.** Tại sao không nên dùng tên thread làm event code?

**Đáp án:** Tên thread phụ thuộc runtime và có thể đổi, trong khi event code cần biểu diễn loại sự kiện ổn định.

**Câu 11.** Vì sao ví dụ demo bỏ timestamp, còn production không nên làm thế?

**Đáp án:** Demo muốn stdout tái lập chính xác; log vận hành cần mốc thời gian để điều tra. Nên dùng clock cố định hoặc schema test, không bỏ timestamp thật.

**Câu 12.** Có nên ghi toàn bộ HTTP request để “đảm bảo đủ thông tin cho mọi truy vấn tương lai” không?

**Đáp án:** Không. Chỉ ghi trường tối thiểu, tuân thủ chính sách bảo mật và retention; raw payload có thể chứa token hoặc dữ liệu cá nhân.

## 17. Tổng kết

**Ổn định format log là duy trì hợp đồng dữ liệu giữa mã phát log và mọi hệ thống tiêu thụ log.** Trọng tâm gồm:

- **Event code, tên trường và ngữ nghĩa ổn định** thay vì phụ thuộc câu chữ tự nhiên.
- **Kiểu dữ liệu, đơn vị, timezone và null semantics rõ ràng.**
- **Formatter/Layout/Encoder phù hợp**, escape ký tự và xử lý Throwable đúng.
- **Versioning, migration và kiểm thử từ producer tới collector.**
- **Bảo mật, retention và hiệu năng** khi log được thu thập, lập chỉ mục và truy vấn.

Logger phát sự kiện chỉ là điểm bắt đầu; **format ổn định giúp sự kiện tiếp tục có giá trị chẩn đoán** sau khi mã Java, backend hoặc hạ tầng logging thay đổi.
