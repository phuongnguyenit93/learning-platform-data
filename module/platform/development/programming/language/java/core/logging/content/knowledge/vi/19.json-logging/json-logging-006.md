# Field timestamp trong JSON logging của Java

## 1. Timestamp trong bản ghi JSON là gì?

Trong chủ đề **JSON logging** của **Java Core Logging**, **field timestamp** là trường chỉ **thời điểm mà sự kiện log được ghi nhận**. Nó giúp người vận hành truy vấn theo thời gian, kết nối các sự kiện cùng một request, điều tra nguyên nhân sự cố và quan sát độ trễ giữa nguồn log với hệ thống thu thập.

Ví dụ:

~~~json
{
  "timestamp": "2026-11-09T08:15:30.125Z",
  "level": "INFO",
  "service": "catalog",
  "event": "order.accepted",
  "orderId": "ORD-17"
}
~~~

**timestamp** ở đây là một thời điểm ở **UTC**, biểu diễn đến **mili-giây**; **Z** cho biết UTC offset bằng 0. Những field khác giải thích sự kiện nào xảy ra, ở service nào, với mức độ gì. Timestamp giúp trả lời *khi nào*, nhưng không tự cho biết *tại sao*.

Nếu tất cả service cùng dùng một hợp đồng timestamp, dashboard và collector có thể:
- Lọc log trong một khoảng thời gian.
- Tạo timeline tương đối giữa các bản ghi.
- Xác định độ trễ ingest hoặc các sự kiện đến muộn.
- Phối hợp log với metric, trace và các mốc nghiệp vụ.
- Phát hiện một event quá xa trong tương lai/quá khứ do clock hoặc parser sai.

**Điểm cần nhớ:** timestamp phải thể hiện một **instant có nghĩa**, không chỉ một chuỗi ngày giờ dễ đọc. Một chuỗi thiếu offset như **2026-11-09 15:15:30** có thể bị hiểu khác nhau trên những máy có timezone khác nhau.

## 2. JSON không có kiểu thời gian riêng

JSON chỉ có các kiểu **string, number, boolean, null, array, object**, không có kiểu **Date/Instant** riêng. Vì vậy một trường timestamp trong log thường dùng:

**String có offset rõ ràng:**

~~~json
{"timestamp":"2026-11-09T08:15:30.125Z"}
~~~

**Number đếm Unix epoch milliseconds:**

~~~json
{"timestampEpochMs":1794212130125}
~~~

Chúng cùng biểu diễn **2026-11-09T08:15:30.125Z**, nhưng có **kiểu JSON và quy tắc parser khác nhau**.

Không có một tên key bắt buộc cho mọi log platform. Một số schema dùng **timestamp**, một số dùng **@timestamp**, **time**, **eventTime** hoặc trường khác. Việc chọn tên phải khớp với schema của ứng dụng, codec và hệ thống tìm kiếm.

**Không tự thay kiểu của cùng một key khi nâng phiên bản.** Ví dụ:

~~~json
{"timestamp":"2026-11-09T08:15:30.125Z"}
~~~

khác hẳn:

~~~json
{"timestamp":1794212130125}
~~~

Cả hai hợp lệ về JSON, nhưng một dashboard/index mapping đã được cấu hình theo string có thể không chấp nhận number. Nếu muốn xuất hai định dạng, dùng hai key có tên rõ, tính từ **cùng một Instant**, và kiểm thử tính nhất quán.

## 3. ISO 8601, RFC 3339 và UTC Z

Chuỗi:

~~~text
2026-11-09T08:15:30.125Z
~~~

có các thành phần:

~~~text
2026 - 11 - 09 T 08 : 15 : 30 . 125 Z
 year month day   hour minute sec millis UTC
~~~

Nó là dạng thời gian có offset được dùng phổ biến trong JSON, thuộc họ **ISO 8601** và phù hợp cách biểu diễn timestamp của **RFC 3339**.

Ví dụ cũng hợp lệ:

~~~text
2026-11-09T15:15:30.125+07:00
~~~

Hai chuỗi trên chỉ **cùng một thời điểm**, vì **15:15 ở offset +07:00** bằng **08:15 UTC**. Đổi offset không đổi instant.

| Chuỗi | Nhận xét |
| --- | --- |
| **2026-11-09T08:15:30Z** | Có UTC, không có giây lẻ |
| **2026-11-09T08:15:30.125Z** | UTC, ba chữ số phần giây |
| **2026-11-09T15:15:30.125+07:00** | Offset khác nhưng cùng instant |
| **2026-11-09T08:15:30** | Thiếu offset, không đủ để xác định instant |
| **2026-11-09 08:15:30** | Không phải timestamp RFC 3339 hoàn chỉnh |
| **11/09/2026 08:15:30** | Có thể nhầm cách đọc ngày/tháng và locale |

Một chính sách đơn giản cho hệ nhiều dịch vụ là **lưu thời điểm UTC với Z**, sau đó chuyển sang giờ địa phương khi hiển thị. Không cần đổi instant trên file để phù hợp timezone của người dùng.

### Không nhầm offset với ZoneId

- **Offset** như +07:00 là chênh lệch cụ thể so với UTC.
- **ZoneId** như Asia/Ho_Chi_Minh hoặc America/New_York bao gồm quy tắc lịch sử và thay đổi giờ mùa hè của vùng khi có.
- **Instant** là một điểm tuyệt đối trên timeline, không chứa ngữ cảnh lịch địa phương.

Không dùng một offset cố định thay cho mọi thời điểm của vùng có DST. Log nên giữ instant làm sự thật, còn timezone vùng dùng cho giao diện hoặc báo cáo.

## 4. Event time và ingestion time là hai khái niệm khác nhau

Trong một pipeline logging:

~~~text
Mã Java phát LogEvent
    |
    | timestamp = thời điểm event được ghi nhận
    v
Logger / Formatter / Async queue
    |
    v
Console/File/Network Appender
    |
    v
Agent / Collector
    | observedAt = khi collector thấy event
    v
Parser / Queue / Storage
    | indexedAt = khi dữ liệu được ghi vào index
    v
Dashboard / Alert
~~~

Ví dụ:

~~~json
{
  "timestamp": "2026-11-09T08:15:30.125Z",
  "observedAt": "2026-11-09T08:15:31.000Z",
  "event": "order.accepted"
}
~~~

Ở đây **timestamp** là event time; **observedAt** là thời gian thu thập. Chênh lệch có thể do **I/O, buffering, mạng, queue hoặc collector bị chậm**.

**Không tự ghi timestamp bằng Instant.now() tại thời điểm format hoặc tại worker async** nếu muốn biết lúc event phát sinh. Một sự kiện được enqueue lúc 08:15:30 nhưng ghi ra lúc 08:15:35 sẽ bị sai 5 giây nếu Formatter bỏ thời gian của LogEvent và tự lấy đồng hồ mới.

Ngược lại, nếu log từ thiết bị gửi muộn hoặc đồng hồ thiết bị sai, **event time** có thể không hoàn toàn tin cậy. Có thể giữ thêm **ingestion/observed time** để điều tra. Phải đặt tên field rõ ràng, tránh dùng time1/time2.

## 5. Các độ chính xác: giây, milli, micro, nano

Cùng một giây:

~~~text
2026-11-09T08:15:30Z
2026-11-09T08:15:30.125Z
2026-11-09T08:15:30.125456Z
2026-11-09T08:15:30.125456789Z
~~~

| Độ phân giải biểu diễn | Chữ số giây lẻ | Trường hợp |
| --- | --- | --- |
| Giây | 0 | Job thưa, ứng dụng cơ bản |
| Mili-giây | 3 | Phần lớn log ứng dụng và dashboard |
| Micro-giây | 6 | Nhiều event diễn ra trong một mili-giây |
| Nano-giây | 9 | Khi nguồn timestamp và backend có hỗ trợ |

**Độ phân giải biểu diễn không bằng độ chính xác thực tế của đồng hồ.** Một timestamp có chín chữ số không chứng minh đồng hồ đúng tuyệt đối tới nano-giây.

Trong Java 17:

- **Instant** biểu diễn số giây cộng nanosecond adjustment.
- **java.util.logging.LogRecord.getInstant()** giữ timestamp ở dạng Instant.
- **LogRecord.getMillis()** chỉ lấy epoch milliseconds, không giữ phần dưới mili-giây.
- **DateTimeFormatterBuilder.appendInstant(3)** dùng để xuất UTC với ba chữ số phần giây.
- **DateTimeFormatter.ISO_INSTANT** biểu diễn theo UTC nhưng độ dài phần thập phân có thể thay đổi theo giá trị.

Hãy thống nhất precision ở **schema**, backend và collector. Không tự nâng precision chỉ vì muốn nhiều chữ số hơn nếu nguồn clock không cung cấp thông tin đó.

## 6. Unix epoch: đơn vị phải được xác định

**Unix epoch** bắt đầu từ **1970-01-01T00:00:00Z**. Cùng thời điểm ví dụ:

~~~text
UTC string:       2026-11-09T08:15:30.125Z
epoch seconds:    1794212130.125
epoch millis:     1794212130125
epoch micros:     1794212130125000
epoch nanos:      1794212130125000000
~~~

Các tên trường nên diễn đạt đơn vị:

| Tên trường | Kiểu/ý nghĩa |
| --- | --- |
| timestamp | String UTC ISO/RFC 3339 |
| timestampEpochSeconds | Number giây tính từ epoch |
| timestampEpochMs | Number mili-giây tính từ epoch |
| timestampEpochUs | Number micro-giây |
| timestampEpochNs | Number nano-giây hoặc String theo chính sách |

Nếu hệ nhận **1794212130125** mà tưởng là **seconds** thay vì **milliseconds**, thời gian sẽ bị hiểu lệch 1000 lần. Đây là lỗi tích hợp rất phổ biến.

**Cảnh báo về JavaScript/JSON number:** giá trị epoch nanoseconds hiện đại có 19 chữ số, vượt giới hạn số nguyên chính xác **2^53 - 1** của IEEE-754 double. Không giả định mọi parser JSON sẽ giữ nguyên integer 64-bit. Nếu cần nano-giây end-to-end, cân nhắc String, seconds + nanoseconds hoặc kiểu dữ liệu/log platform có hỗ trợ rõ.

Trong production không bắt buộc xuất cả string lẫn epoch. Nếu giữ cả hai để tiện truy vấn, tính từ **cùng một Instant** để không có sai lệch do hai lần gọi đồng hồ.

## 7. Java time API nên dùng cho timestamp

| Java type | Vai trò |
| --- | --- |
| **Instant** | Thời điểm tuyệt đối, phù hợp nhất cho event time |
| **OffsetDateTime** | Thời gian cùng offset, hữu ích khi parse nguồn có +07:00 |
| **ZonedDateTime** | Thời gian vùng có quy tắc DST, thích hợp hiển thị lịch |
| **LocalDateTime** | Ngày giờ không có offset/zone; không nên dùng một mình để tạo log timestamp xuyên máy |
| **Clock** | Nguồn đồng hồ có thể thay thế để test |
| **Duration** | Khoảng thời gian, không phải một timestamp |

Đổi offset sang UTC:

~~~java
Instant fromUtc = Instant.parse("2026-11-09T08:15:30.125Z");
Instant fromOffset =
        OffsetDateTime.parse("2026-11-09T15:15:30.125+07:00")
                .toInstant();
System.out.println(fromUtc.equals(fromOffset));
~~~

Đây là snippet, cần import **java.time.Instant** và **OffsetDateTime**. Kết quả là:

~~~text
true
~~~

### Clock.fixed để kiểm thử

~~~java
Clock fixed = Clock.fixed(
        Instant.parse("2026-11-09T08:15:30.125Z"),
        ZoneOffset.UTC);
Instant timestamp = Instant.now(fixed);
~~~

Đây là snippet, cần import **Clock**, **Instant** và **ZoneOffset**. Nó cho phép unit test tạo thời điểm cố định. Trong production, hệ thống nên dùng đồng hồ thực hoặc clock được inject theo kiến trúc, **không hard-code thời gian test**.

### Duration khác timestamp

~~~java
long start = System.nanoTime();
// Chạy một tác vụ cần đo.
long elapsedNs = System.nanoTime() - start;
~~~

**System.nanoTime()** được thiết kế để đo thời gian tương đối trong JVM. Giá trị trả về **không phải Unix epoch nanos**. Đừng ghi nó vào field timestamp. Khi đo thời lượng, xuất **durationMs/durationNs** có đơn vị rõ, không nhầm với thời điểm xảy ra event.

## 8. LogRecord.getInstant() và getMillis() của JUL

Với **java.util.logging (JUL)**, **LogRecord** chứa message, level, loggerName, Throwable và thời điểm xảy ra sự kiện.

- Khi tạo LogRecord, nó được gán một **Instant** theo clock hiện tại có sẵn.
- **getInstant()** trả về thời điểm dưới dạng java.time.Instant.
- **setInstant(Instant)** cho phép đặt thời điểm rõ ràng, phù hợp test.
- **getMillis()** trả mili-giây từ epoch, mất phần nano-giây dưới mili.
- **setMillis(long)** đã **deprecated**; nên dùng setInstant trong Java 17.
- Khi đã truyền LogRecord cho framework, code ứng dụng không nên tiếp tục sửa các trường của record.
- Formatter/Handler cần dùng **record.getInstant()** nếu muốn giữ event time thay vì ghi thời gian xử lý muộn.

JUL không tự xuất JSON; **ConsoleHandler** thường ghi ra **System.err**, còn **StreamHandler** có thể nhận OutputStream do bạn chọn, ví dụ System.out. Muốn cấu trúc JSON phải có Formatter, encoder hoặc hệ logging phù hợp.

Dòng format đơn giản:

~~~java
String utc = DateTimeFormatter.ISO_INSTANT
        .format(record.getInstant());
~~~

Đây là snippet có biến LogRecord record và import DateTimeFormatter. Với yêu cầu đúng ba chữ số phần giây, ví dụ đầy đủ dưới đây dùng **appendInstant(3)**.

## 9. Ví dụ Java 17+ độc lập: timestamp JSON chuẩn hóa UTC

Ví dụ dùng **chỉ JDK**; không cần Maven, Logback hay Log4j. Nó chủ động tạo LogRecord với instant cố định để kết quả không phụ thuộc đồng hồ máy.

Mục tiêu:

1. Dùng **OffsetDateTime** có offset +07:00 rồi chuyển sang Instant UTC.
2. Dùng **LogRecord.setInstant** để gắn event time.
3. Dùng **StreamHandler(System.out)** và Formatter tạo **mỗi dòng một JSON object**.
4. Xuất **timestamp** ISO UTC 3 chữ số mili-giây và **timestampEpochMs** từ cùng Instant.
5. Xuất thêm level, event và orderId dưới dạng String có escape JSON.
6. Logger level ALL; Handler level INFO, nên FINE không xuất.
7. Flush sau publish nhưng không đóng System.out.

Lưu toàn bộ mã dưới tên **TimestampJsonDemo.java**:

~~~java
import java.time.Instant;
import java.time.OffsetDateTime;
import java.time.format.DateTimeFormatter;
import java.time.format.DateTimeFormatterBuilder;
import java.util.logging.Formatter;
import java.util.logging.Level;
import java.util.logging.LogRecord;
import java.util.logging.Logger;
import java.util.logging.StreamHandler;

public final class TimestampJsonDemo {
    private static final Logger LOG =
            Logger.getLogger("examples.logging.timestamp");

    private static final DateTimeFormatter UTC_MILLIS =
            new DateTimeFormatterBuilder()
                    .appendInstant(3)
                    .toFormatter();

    private static final class JsonFormatter extends Formatter {
        @Override
        public String format(LogRecord record) {
            Instant timestamp = record.getInstant();
            Object[] parameters = record.getParameters();
            String orderId = (parameters != null
                    && parameters.length > 0)
                    ? String.valueOf(parameters[0]) : "";

            return "{\"timestamp\":"
                    + jsonString(UTC_MILLIS.format(timestamp))
                    + ",\"timestampEpochMs\":"
                    + timestamp.toEpochMilli()
                    + ",\"level\":"
                    + jsonString(record.getLevel().getName())
                    + ",\"event\":"
                    + jsonString(record.getMessage())
                    + ",\"orderId\":"
                    + jsonString(orderId)
                    + "}" + System.lineSeparator();
        }
    }

    private static String jsonString(String value) {
        StringBuilder result = new StringBuilder("\"");

        for (int i = 0; i < value.length(); i++) {
            char ch = value.charAt(i);
            switch (ch) {
                case '"' -> result.append("\\\"");
                case '\\' -> result.append("\\\\");
                case '\n' -> result.append("\\n");
                case '\r' -> result.append("\\r");
                case '\t' -> result.append("\\t");
                default -> {
                    if (ch < 0x20) {
                        result.append("\\u");
                        for (int shift = 12; shift >= 0; shift -= 4) {
                            result.append(Character.forDigit(
                                    (ch >>> shift) & 0xF, 16));
                        }
                    } else {
                        result.append(ch);
                    }
                }
            }
        }
        return result.append('"').toString();
    }

    private static void emit(
            Level level, String event, String orderId, Instant at) {
        LogRecord record = new LogRecord(level, event);
        record.setInstant(at);
        record.setParameters(new Object[] { orderId });
        LOG.log(record);
    }

    public static void main(String[] args) {
        LOG.setUseParentHandlers(false);
        LOG.setLevel(Level.ALL);

        StreamHandler stdout =
                new StreamHandler(System.out, new JsonFormatter()) {
                    @Override
                    public synchronized void publish(LogRecord record) {
                        super.publish(record);
                        flush();
                    }
                };
        stdout.setLevel(Level.INFO);
        LOG.addHandler(stdout);

        try {
            Instant at = OffsetDateTime.parse(
                    "2026-11-09T15:15:30.125+07:00").toInstant();

            emit(Level.INFO, "order.accepted",
                    "ORD-17", at);
            emit(Level.WARNING, "inventory.retry",
                    "ORD-17", at.plusMillis(25));
            emit(Level.FINE, "cache.hit",
                    "ORD-17", at.plusMillis(30));
        } finally {
            LOG.removeHandler(stdout);
            stdout.flush();
        }
    }
}
~~~

### Chạy bằng JDK 17 trở lên

~~~bash
javac TimestampJsonDemo.java
java TimestampJsonDemo
~~~

**Stdout chính xác của demo**:

~~~text
{"timestamp":"2026-11-09T08:15:30.125Z","timestampEpochMs":1794212130125,"level":"INFO","event":"order.accepted","orderId":"ORD-17"}
{"timestamp":"2026-11-09T08:15:30.150Z","timestampEpochMs":1794212130150,"level":"WARNING","event":"inventory.retry","orderId":"ORD-17"}
~~~

Đây là **JSON Lines/NDJSON**: mỗi dòng là một JSON object, không phải một JSON array. Chương trình không tự ghi gì ra stderr. Line separator vật lý của môi trường có thể khác nhau, nhưng nội dung logic từng dòng như trên.

### Vì sao kết quả được xác định?

1. **OffsetDateTime.parse** lấy thời gian +07:00 và **toInstant()** đưa về 08:15:30.125 UTC.
2. **record.setInstant(at)** giữ event time cố định cho mục đích học tập.
3. **appendInstant(3)** tạo đúng ba chữ số phần giây và Z.
4. **toEpochMilli()** lấy **1794212130125** từ cùng Instant; cộng 25 ms thành **1794212130150**.
5. **Logger level ALL** không loại FINE tại nguồn; **StreamHandler level INFO** loại FINE tại đích.
6. **JsonFormatter** dựng trường theo thứ tự rõ, dùng **jsonString(...)** để escape quote, backslash và control chars.
7. **setUseParentHandlers(false)** ngăn các Handler trên Logger cha ghi thêm ra console.
8. Override **publish()** để gọi **flush()** sau khi Handler ghi, bảo đảm demo hiển thị kịp.
9. **Không gọi close() trên StreamHandler nhận System.out**: việc đóng có thể đóng luôn stream tiêu chuẩn của ứng dụng.
10. **WARNING** là tên level JUL; backend khác có thể dùng WARN, nhưng logic timestamp không thay đổi.

**Giới hạn:** Formatter này phục vụ minh họa field timestamp, chưa phải JSON encoder production với mọi kiểu object, Throwable, Unicode lỗi hoặc nested fields. Trong hệ thống thật nên dùng JSON encoder/layout đã được kiểm thử và thiết kế schema chuẩn.

## 10. Trong ứng dụng thật có nên tự setInstant cho từng event?

Thông thường **không cần**. Logging backend tạo timestamp khi log event được phát. Nếu bạn tự tạo domain event thì **Instant.now()** hoặc **Instant.now(clock)** phù hợp tùy kiến trúc, nhưng không nên tạo hai timestamp từ hai lần gọi đồng hồ rồi tuyên bố chúng cùng một lúc.

~~~java
Clock clock = Clock.systemUTC();
Instant eventTime = Instant.now(clock);
~~~

Đây là snippet; ứng dụng có thể inject Clock vào service để test với Clock.fixed.

Lưu ý:

- Đừng dùng **LocalDateTime.now()** không kèm offset làm trường chuẩn của log nhiều service.
- Đừng dùng giờ lúc Formatter format nếu bạn muốn event time ở nơi phát.
- Đừng set LogRecord timestamp theo dữ liệu client không tin cậy mà không nêu rõ nguồn và chính sách.
- Nếu cần một **business occurredAt** khác log timestamp, dùng field khác thay vì ghi đè.
- Với async logger, kiểm thử backend giữ timestamp lúc tạo event và encoder không tự làm mới thời gian.
- Với log được replay, thường giữ eventTime gốc và thêm processedAt/ingestedAt khi cần.

## 11. Log4j 2: JsonTemplateLayout và timestamp resolver

**Apache Log4j 2** có **JsonTemplateLayout** để xuất LogEvent theo một template JSON. Nó thuộc module **log4j-layout-template-json**, cần phiên bản tương thích với **log4j-core**.

Một file **EventTemplate.json** có thể gồm:

~~~json
{
  "timestamp": {
    "$resolver": "timestamp",
    "pattern": {
      "format": "yyyy-MM-dd'T'HH:mm:ss.SSS'Z'",
      "timeZone": "UTC"
    }
  },
  "level": {
    "$resolver": "level",
    "field": "name"
  },
  "message": {
    "$resolver": "message",
    "stringified": true
  }
}
~~~

Đây là **template** quy định field, không phải log output. **$resolver=timestamp** lấy timestamp từ LogEvent; **timeZone=UTC** thiết lập vùng khi format; pattern quyết định độ chính xác biểu diễn.

**Chú ý literal Z:** **'Z'** trong pattern là ký tự cố định. Chỉ được in Z như vậy nếu thực tế đã format **UTC**. Đổi timezone mà vẫn in Z sẽ làm bản ghi **tự nhận sai offset**.

Đoạn Appender trong **log4j2.xml**:

~~~xml
<Console name="JSON" target="SYSTEM_OUT">
    <JsonTemplateLayout eventTemplateUri="classpath:EventTemplate.json"/>
</Console>
~~~

Đặt trong **Configuration/Appenders**, gắn AppenderRef ở phần Loggers, và đưa EventTemplate.json vào classpath. Cần đúng backend Log4j 2; việc ứng dụng chỉ thêm log4j-api hoặc dùng SLF4J với Logback không làm cấu hình này hoạt động.

Log4j 2 còn hỗ trợ **epoch timestamp resolver**, ví dụ:

~~~json
{
  "$resolver": "timestamp",
  "epoch": {
    "unit": "millis",
    "rounded": true
  }
}
~~~

Đây là **một resolver expression**, không phải một event hoàn chỉnh. **unit=millis** và **rounded=true** cho giá trị epoch milliseconds nguyên theo quy tắc của layout. Nếu dùng secs/nanos phải kiểm tra đơn vị và khả năng của JSON consumer.

**PatternLayout %d không đồng nghĩa JSON timestamp có schema.** Nó thường xuất text và timezone mặc định có thể không theo UTC. Khi cần typed field, dùng JSON Template Layout hoặc encoder tương thích và kiểm tra output thực tế.

## 12. Logback: %date/%d và timezone trong pattern

**Logback** thường chạy sau **SLF4J**. Với PatternLayout, **%date** hoặc **%d** lấy thời gian LogEvent.

Một pattern text được cấu hình UTC rõ:

~~~text
%d{yyyy-MM-dd'T'HH:mm:ss.SSS'Z', UTC} %-5level %logger - %msg%n
~~~

Đây là **pattern text**, không phải JSON. Literal **'Z'** chỉ đúng vì đã đặt **UTC**. Không dùng pattern này với một timezone khác rồi vẫn giữ Z.

**Bẫy ISO8601:** trong các phiên bản Logback, **%date{ISO8601}** truyền thống có thể dùng dấu cách giữa ngày và giờ, dấu phẩy cho phần milli, nên **không nhất thiết là timestamp RFC 3339 chặt chẽ**. Hãy đọc tài liệu của phiên bản Logback đang dùng và đặt pattern/encoder rõ ràng.

Để có **JSON logging đúng**, ứng dụng cần **JSON encoder tương thích**, chứ không tự ghép JSON bằng text PatternLayout như:

~~~text
{"timestamp":"%d","message":"%msg"}
~~~

Nếu %msg chứa dấu nháy, newline hoặc backslash, output tự ghép này có thể hỏng JSON. Với JSON encoder đúng, timestamp phải được xuất từ event time, có timezone, precision và field name nhất quán.

**SLF4J facade không tự định nghĩa field timestamp**. Backend và encoder quyết định cách serialize timestamp, vì vậy việc đổi backend phải kèm kiểm thử hợp đồng field.

## 13. Timestamp log và timestamp nghiệp vụ

Một sự kiện **order.completed** có thể mang các mốc:

~~~json
{
  "timestamp": "2026-11-09T08:15:30.125Z",
  "event": "order.completed",
  "orderId": "ORD-17",
  "orderCreatedAt": "2026-11-08T16:00:00Z",
  "paymentAuthorizedAt": "2026-11-09T08:14:50Z"
}
~~~

**timestamp** là thời điểm logging của event; **orderCreatedAt** và **paymentAuthorizedAt** là các mốc nghiệp vụ. Chúng không được thay thế lẫn nhau chỉ vì cùng là giá trị ngày giờ.

Một số tên khác có ngữ nghĩa riêng:

- **occurredAt**: thời điểm business event xảy ra tại nguồn.
- **recordedAt**: lúc ứng dụng hoặc database ghi nhận event.
- **publishedAt**: lúc event được đẩy lên broker.
- **processedAt**: lúc consumer xử lý.
- **observedAt**: lúc hệ quan sát thu thập.

Ví dụ một thiết bị offline phát sự kiện lúc 08:00 rồi đồng bộ với server lúc 11:00. Business occurredAt và log timestamp trên server có thể cách nhau nhiều giờ mà **không có mâu thuẫn**. Hãy dùng tên trường và documentation để tránh khiến dashboard cộng trừ sai.

## 14. Timestamp không phải thứ tự tuyệt đối của hệ phân tán

Các timestamp rất có ích khi xây timeline, nhưng không tự bảo đảm **total order** chính xác:

1. Clock của hai host có thể lệch (**clock skew**).
2. NTP/PTP có thể điều chỉnh đồng hồ.
3. Hai event có thể nằm trong cùng một mili-giây.
4. Async queue, collector và network làm log đến muộn hoặc đổi thứ tự quan sát.
5. Event time có thể đến từ client hoặc thiết bị có đồng hồ sai.
6. Nguồn clock wall-time có thể nhảy; nó không phải nguồn đo Duration monotonic.
7. Timestamp chính xác tới nano-giây về biểu diễn không chứng minh clock đúng tới nano-giây.
8. Một request có thể chạy qua nhiều thread/process, không có một sequence toàn cục.

Muốn tái dựng quan hệ nhân quả, kết hợp **timestamp với requestId, traceId/spanId, service/instance và sequence number theo phạm vi rõ ràng**. Nếu nghiệp vụ yêu cầu xác định thứ tự commit, dùng transaction, broker offset hoặc protocol tương ứng, không dựa vào thứ tự log do console hay collector hiển thị.

**Duration** nên đo bằng nguồn monotonic phù hợp; phép trừ hai wall-clock timestamp chịu ảnh hưởng clock adjustment. Trường durationMs có ý nghĩa khác timestampEpochMs.

## 15. Query theo khoảng thời gian

Log platform thường parse timestamp thành kiểu date/time nội bộ. Ví dụ điều kiện truy vấn giả lập:

~~~text
timestamp >= "2026-11-09T08:00:00Z"
AND timestamp < "2026-11-09T09:00:00Z"
AND service == "catalog"
AND level == "ERROR"
~~~

Đây là **pseudo query**, không phải syntax chung cho Elasticsearch, Loki hay các hệ khác.

Các lưu ý:

- Ưu tiên khoảng nửa mở **[start, end)** để không đếm trùng sự kiện ở ranh giới cửa sổ.
- Nếu log hiển thị giờ địa phương, chuyển ngưỡng truy vấn về cùng timeline/offset trước khi lọc.
- Tránh so sánh chuỗi từ nhiều timezone/precision không nhất quán theo lexical order.
- Nếu log đến muộn, truy vấn theo event time và ingestion time có thể trả tập khác nhau.
- Collector cần parse field thành date, không chỉ giữ nó trong message text.
- Nếu hệ thống lưu epoch number, phải biết rõ **unit, signed range và precision**.
- Dashboard có thể hiển thị theo timezone người dùng trong khi storage vẫn giữ UTC.
- Khi thay đổi field name hoặc type, phải cập nhật index mapping/dashboard/alerts tương ứng.

Không kết luận rằng thấy timestamp trong JSON nghĩa là log platform đã hiểu đúng **trường thời gian có thể index/query**.

## 16. Clock skew, late events và alerting

Trong hệ nhiều service, timestamp có thể khác thực tế quan sát do đồng hồ sai, mạng chậm hoặc dữ liệu bị replay.

**Ví dụ:**

~~~json
{
  "timestamp": "2026-11-09T08:15:30.125Z",
  "observedAt": "2026-11-09T08:17:10Z",
  "event": "payment.authorized"
}
~~~

Ở đây observedAt muộn khoảng hơn một phút; điều đó có thể do pipeline chậm, không nhất thiết nghiệp vụ diễn ra muộn. Nếu log được gửi trễ, dashboard có thể đặt event vào một khoảng thời gian trước đó.

Các chiến lược:

1. Giữ **event timestamp** từ nguồn khi thích hợp.
2. Lưu **observedAt** ở collector để đo ingest lag.
3. Theo dõi **clock skew** và đồng bộ đồng hồ trên host/VM.
4. Cảnh báo event ở tương lai bất thường hoặc quá cũ theo chính sách.
5. Không mặc định loại bỏ mọi late event; xét mục tiêu phân tích và thời hạn lưu.
6. Với audit, lưu cả thời gian nguồn và thời gian hệ thống nhận nếu cần truy xuất.
7. Đối chiếu traceId/requestId khi hai timestamp không giải thích được thứ tự.
8. Kiểm thử alert windows có tính đến độ trễ ingest.

Timestamp không thay thế tính toàn vẹn của audit trail hoặc cơ chế giao dịch bảo đảm thứ tự.

## 17. Schema evolution: đổi timestamp phải có migration

Schema timestamp là **hợp đồng dữ liệu**, tương tự một phần API được dashboard và alert sử dụng.

| Hạng mục | Quy ước nên xác định |
| --- | --- |
| Tên field | timestamp, @timestamp hoặc tên duy nhất |
| Kiểu | String ISO/RFC 3339 hoặc Number epoch có đơn vị |
| Timezone | UTC Z hoặc offset đầy đủ |
| Precision | Giây/milli/micro/nano |
| Ngữ nghĩa | Event time, observed time hay processed time |
| Missing | Bỏ event, default, quarantine hay báo lỗi? |
| Invalid format | Không chấp nhận, fallback hay dead-letter? |
| Out-of-range | Xử lý timestamp quá xa quá khứ/tương lai |
| Late arrival | Có giữ event timestamp gốc hay không? |
| Version | Thử tương thích giữa producer và consumer |

**Đừng đổi timestamp từ String sang Number trong một release mà không cập nhật parser/index mapping.** Hệ thống có thể nhận log nhưng không còn query đúng. Việc thay đổi từ UTC Z sang chuỗi không có timezone cũng là breaking change về ngữ nghĩa, ngay cả khi JSON vẫn hợp lệ.

Nếu phải chuyển schema, cân nhắc giai đoạn song song có field mới rõ tên, contract tests và migration dashboard/alert. Không đổi ngẫu nhiên timestamp sau khi đã indexing.

## 18. Hiệu năng khi format timestamp

Ngày giờ có thể được format trên lượng log rất lớn. Cần thiết kế hợp lý mà không làm mất tính đúng đắn.

- **DateTimeFormatter immutable và thread-safe**; dùng lại qua **static final** được.
- **SimpleDateFormat** có mutable state, không thread-safe nếu dùng chung thiếu đồng bộ.
- Một event chỉ cần **một Instant gốc**, rồi chuyển ra ISO và epoch khi thật cần.
- Đừng tạo một DateTimeFormatter mới cho từng lần ghi nếu không có lý do.
- JSON layout/encoder do backend cung cấp thường phù hợp hơn tự format mọi event ở mã nghiệp vụ.
- Chọn milliseconds khi đủ; xuất nano làm chuỗi dài hơn và index có thể tốn thêm tài nguyên.
- Async logging giảm một số I/O nhưng queue có thể đầy và gây mất log theo policy.
- Đừng bỏ timestamp của event quan trọng chỉ để tối ưu: hãy giảm log thừa, chọn level và encoder thích hợp.
- Kiểm thử hot path có nhiều event; đo CPU/allocations, không dựa vào giả định chủ quan.
- Nếu cần log sau crash, hiểu rằng **flush không đồng nghĩa dữ liệu đã được collector lưu bền**.

## 19. Bảo mật và rủi ro liên quan thời gian

Mặc dù timestamp ít nhạy cảm hơn token hoặc password, nó vẫn tác động đến hệ thống:

1. **Client-controlled timestamp:** input người dùng có thể được đặt thành thời gian giả, vì vậy không tin vô điều kiện.
2. **Log injection:** nếu tự nối JSON không escape, input có thể tạo bản ghi giả chứa một timestamp khác.
3. **Audit trail:** cần phân biệt lúc nguồn phát và lúc server nhận; không coi một timestamp là bằng chứng chống sửa.
4. **Clock drift/spoofing:** có thể làm thứ tự điều tra sai.
5. **Timestamp quá xa:** có thể phá retention hoặc lọc sai nếu storage tin mọi event time.
6. **Timezone của người dùng:** có thể làm lộ quy luật hoạt động khi ghép với nhiều field; áp dụng quyền truy cập phù hợp.
7. **Retention:** thời hạn lưu có thể tính theo event time hoặc ingestion time, gây khác biệt cho event đến trễ.
8. **Numeric overflow:** epoch nanos có thể bị làm tròn/lỗi qua nhiều parser.
9. **PII đi kèm timestamp:** correlation với userId/tenantId có thể trở thành dữ liệu cá nhân cần giảm thiểu.
10. **Backups/collector:** quyền đọc và thời gian lưu cần áp dụng cả dữ liệu đã được sao chép.

Timestamp đúng giúp điều tra, nhưng **tính toàn vẹn và độ tin cậy của toàn pipeline** cần thiết kế và giám sát riêng.

## 20. Các lỗi hay gặp và cách khắc phục

| Triệu chứng | Nguyên nhân có thể | Cách kiểm tra |
| --- | --- | --- |
| Log có giờ nhưng thiếu timezone | Dùng LocalDateTime hoặc pattern không offset | Chuyển từ Instant, xuất UTC Z/offset |
| Log hiển thị Z nhưng thực ra là giờ local | Literal 'Z' nhưng không thiết lập UTC | Kiểm tra timezone trong Layout/Formatter |
| Event lệch 7 giờ | Xem +07:00 như UTC hoặc convert hai lần | Parse về Instant rồi đối chiếu |
| Có epoch 13 chữ số nhưng parser coi seconds | Nhầm milliseconds/seconds | Đặt field EpochMs, kiểm tra unit |
| Timestamp nano bị sai vài chữ số | JSON parser dùng double và mất integer precision | Dùng representation phù hợp |
| Các event cùng timestamp | Precision chỉ tới giây/mili-giây | Chọn precision đủ, thêm sequence nếu cần |
| Event nằm tương lai | Host clock sai hoặc parse offset nhầm | Kiểm tra NTP/timezone/parser |
| Timestamp phản ánh lúc ghi ra file | Formatter gọi Instant.now sau async queue | Lấy timestamp từ LogEvent |
| Logback ISO8601 không đúng RFC 3339 | Pattern mặc định dạng dấu cách/dấu phẩy | Chọn pattern strict + timezone |
| Log4j2 JSON thiếu timestamp | Template không có timestamp resolver | Kiểm tra EventTemplate.json/layout |
| Log có timestamp nhưng không filter theo date | Collector lưu dưới String message hoặc mapping sai | Kiểm tra parse và kiểu index |
| Query theo khoảng thiếu late event | Dựa chỉ vào ingestion time hoặc time windows quá hẹp | Phân biệt event vs observedAt |
| Timezone UI khác file | Viewer chuyển timezone khi hiển thị | So sánh Instant, không chỉ chuỗi UI |
| Unit test đôi khi sai | Test dùng Instant.now thật | Dùng Clock.fixed/setInstant |
| Ghi sai phần giây | Pattern không có hoặc trộn nano/milli | Test .000/.125/.999 và precision |
| Một log thiếu record ở async | Queue/drop policy hoặc flush chưa xong | Test shutdown, collector và metrics |

**Trình tự chẩn đoán:** xác định field schema → xác định nguồn event time → parse bằng Instant → kiểm tra timezone/offset → kiểm tra precision/unit → kiểm tra layout/encoder → kiểm tra collector/index → so sánh với observedAt và clock source.

## 21. Kiểm thử timestamp end-to-end

**Unit tests:**

- Một Instant phải round-trip qua format/parse không thay đổi trong precision đã chọn.
- **2026-11-09T15:15:30.125+07:00** phải bằng **2026-11-09T08:15:30.125Z**.
- Test phần mili **.000**, **.125**, **.999**.
- Test ngày chuyển năm, năm nhuận, thời điểm trước Unix epoch nếu ứng dụng có dữ liệu lịch sử.
- Với ZoneId có DST, test ngày chuyển giờ và thời gian ambiguous.
- Dùng **Clock.fixed** hoặc **LogRecord.setInstant**, không dùng Thread.sleep để cố định expected stdout.

**Integration tests:**

- Bật backend đúng phiên bản, kiểm tra field timestamp được xuất thật.
- JSON cần parse được thành object; timestamp parse thành Instant đúng.
- Thử thay JVM timezone: trường canonical UTC không bị đổi instant.
- Nếu output có epoch millis, đối chiếu **toEpochMilli()**.
- Thử async queue bị chậm, đảm bảo event timestamp không bị thay bằng output time.
- Thử message chứa Unicode, quote, newline để kiểm tra encoder không phá JSON.
- Collector phải tạo trường date dùng được cho query, không chỉ một String vô nghĩa.
- Kiểm tra Log4j2 JsonTemplateLayout có module/resolver đúng.
- Kiểm tra dashboard/alert có chọn đúng field event time hoặc ingestion time.
- Kiểm tra dữ liệu đến muộn, tương lai bất thường và failure policy.

**Không chỉ assert chuỗi có key "timestamp".** Parse lại và kiểm chứng thời điểm, timezone, unit, precision, schema và đường ingest.

## 22. Checklist vận dụng

1. Chọn một **field timestamp chuẩn** và tài liệu hóa ngữ nghĩa.
2. Chọn **UTC ISO/RFC 3339 string** hoặc epoch number có **unit rõ**.
3. Trong Java, ưu tiên **Instant** và **Clock** để kiểm thử.
4. Không dùng **LocalDateTime** thiếu offset làm timestamp tuyệt đối.
5. Đừng hard-code **'Z'** nếu không thực sự format UTC.
6. Chọn precision phù hợp với clock/backend/collector.
7. Tạo ISO và epoch từ **một Instant**, không từ hai lần đọc đồng hồ.
8. Nếu có async logging, lấy **event time** từ LogEvent/LogRecord.
9. Dùng **DateTimeFormatter** thread-safe; tránh singleton SimpleDateFormat thiếu lock.
10. Kiểm tra Logback/Log4j2/JUL có format và timezone khác nhau.
11. Tách **observedAt/ingestedAt/processedAt** nếu có nhu cầu phân tích độ trễ.
12. Không coi timestamp là total order của hệ phân tán.
13. Kiểm tra collector parse thành field date đúng type, mapping và timezone.
14. Quản lý contract/migration khi đổi key, type, precision hay semantics.
15. Kiểm tra clock skew, replay, late events và retention.
16. Kiểm soát input không tin cậy, JSON escaping, quyền đọc và audit.
17. Test bằng thời gian cố định, dữ liệu biên và pipeline thật.

**Kết luận:** **Field timestamp** trong JSON logging phải chỉ rõ **thời điểm gì, lấy ở đâu, offset nào, độ chính xác bao nhiêu và schema nào**. Với Java 17, **Instant** và **LogRecord.getInstant()** là nền tảng tin cậy cho event time; hãy xuất **UTC Z** hoặc epoch có đơn vị, rồi xác minh JSON encoder và collector hiểu đúng.

## 23. Tài liệu chính thức

- [Oracle Java 17 — LogRecord](https://docs.oracle.com/en/java/javase/17/docs/api/java.logging/java/util/logging/LogRecord.html): getInstant, getMillis và setInstant.
- [Oracle Java 17 — Instant](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/Instant.html): timeline, epoch milliseconds, Instant.now.
- [Oracle Java 17 — DateTimeFormatter](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/format/DateTimeFormatter.html): ISO_INSTANT và thread-safety.
- [Oracle Java 17 — DateTimeFormatterBuilder](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/format/DateTimeFormatterBuilder.html): appendInstant(3).
- [Oracle Java 17 — Clock](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/Clock.html): Clock.systemUTC và Clock.fixed.
- [Apache Log4j 2 — JSON Template Layout](https://logging.apache.org/log4j/2.x/manual/json-template-layout.html): timestamp resolver, epoch và timeZone.
- [Apache Log4j 2 — Pattern Layout](https://logging.apache.org/log4j/2.x/manual/pattern-layout.html): %d và tùy chọn timezone.
- [Logback — Layouts](https://logback.qos.ch/manual/layouts.html): %date và ISO8601/UTC.
- [RFC 3339 — Date and Time on the Internet](https://www.rfc-editor.org/rfc/rfc3339): biểu diễn thời gian khi trao đổi dữ liệu.
