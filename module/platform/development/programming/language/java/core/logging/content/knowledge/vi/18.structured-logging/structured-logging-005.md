# Timestamp chuẩn trong Structured Logging của Java

Một bản ghi **structured logging** chỉ hữu ích khi trường thời gian được ghi **rõ thời điểm, có múi giờ/offset, độ chính xác thống nhất và có thể parse bằng máy**. Nếu hai service dùng timestamp khác định dạng, một nơi ghi giờ địa phương không offset và nơi khác ghi epoch milliseconds dưới tên `timestamp`, việc sắp xếp sự kiện, tìm sự cố theo khoảng thời gian, tính độ trễ và liên kết trace dễ dẫn đến kết luận sai.

**Timestamp chuẩn** trong bài này là quy ước biểu diễn và xử lý **thời điểm của log event** bằng Java 17+, thường là chuỗi theo ISO 8601/RFC 3339, ưu tiên UTC và ký hiệu `Z`, cộng với các quy tắc cho `event_time`, `observed_at`, độ chính xác, parser, clock skew và bảo toàn thời gian khi ghi log bất đồng bộ.

Một schema đơn giản, nhất quán:

```json
{"timestamp":"2026-11-09T03:15:30.123Z","level":"INFO","service":"payment-service","event":"payment_authorized","requestId":"req-17"}
```

Dòng trên là **JSON minh họa**. `timestamp` là một **chuỗi thời điểm tuyệt đối**, có `Z` cho UTC; `level`, `service`, `event` và `requestId` là metadata riêng, không được nhét vào cùng một chuỗi thời gian.

## 1. Timestamp trả lời câu hỏi nào?

Timestamp của log thường trả lời **“Sự kiện được ghi nhận xảy ra lúc nào?”**. Đó không nhất thiết là lúc dữ liệu được collector nhận, lúc log được lưu vào storage, hay lúc người xem mở dashboard.

Các khái niệm cần phân biệt:

| Trường thời gian | Ý nghĩa | Ai nên gán? |
| --- | --- | --- |
| `timestamp` / `event_time` | Thời điểm ứng dụng tạo/phát event | Application hoặc logging backend tại thời điểm tạo log event |
| `observed_at` / `ingested_at` | Thời điểm agent/collector nhận được event | Collector/ingestion pipeline |
| `processed_at` | Thời điểm một bước trong pipeline xử lý record | Thành phần tương ứng |
| `duration_ms` | Khoảng thời gian một thao tác kéo dài | Ứng dụng đo riêng; **không phải timestamp** |
| `traceId` và `spanId` | Định danh liên kết sự kiện trong trace | Tracing/correlation system, **không phải thời gian** |

Ví dụ:

```json
{
  "timestamp": "2026-11-09T03:15:30.123Z",
  "observed_at": "2026-11-09T03:15:31.004Z",
  "level": "ERROR",
  "event": "upstream_timeout",
  "duration_ms": 820
}
```

Đây là **một record giả định** để giải thích schema. `observed_at` trễ hơn `timestamp` vì event cần đi qua queue, appender, transport hoặc collector. Khoảng chênh `881 ms` **không tự chứng minh** ingest pipeline mất chính xác 881 ms: hai đồng hồ có thể lệch, định nghĩa thời điểm có thể khác, và có thể có bước buffering hoặc truyền tải.

**Không dùng `observed_at` ghi đè lên `timestamp`** nếu mục tiêu là điều tra khi event thực sự được phát. Nếu cần cả hai, lưu hai field có tên, kiểu và ý nghĩa rõ ràng.

## 2. Quy ước đề xuất: ISO 8601/RFC 3339, UTC, 3 chữ số mili giây

Một chuẩn vận hành dễ đọc và dễ xử lý là:

```text
yyyy-MM-dd'T'HH:mm:ss.SSS'Z'
```

Ví dụ:

```text
2026-11-09T03:15:30.123Z
```

Đây là **mẫu hình dạng** biểu diễn timestamp UTC có đúng ba chữ số phần giây, không phải một `DateTimeFormatter` pattern Java nên sao chép máy móc; trong Java nên dùng formatter có semantics `Instant` như ở phần ví dụ. Chữ `T` phân cách ngày và giờ, `.123` biểu thị 123 mili giây, `Z` cho biết **offset UTC bằng 0**.

### Tại sao ưu tiên UTC?

- Một thời điểm tuyệt đối có thể được trình bày thống nhất giữa nhiều service chạy trên máy có timezone khác nhau.
- Ít nhầm lẫn khi tổng hợp log liên vùng, thay đổi giờ mùa hè (DST) hoặc khi dịch vụ được triển khai sang máy mới.
- Truy vấn theo khoảng thời gian và so sánh với trace/metrics thuận tiện hơn.
- Không phụ thuộc vào timezone mặc định của máy chạy JVM hoặc tài khoản vận hành.

UTC **không có nghĩa phải hiển thị UTC cho tất cả người đọc**. Dashboard có thể chuyển sang múi giờ người dùng; điều quan trọng là dữ liệu gốc vẫn mang một thời điểm tuyệt đối và có thể chuyển đổi chính xác.

### RFC 3339 có thể có offset khác `Z`

Những chuỗi sau biểu diễn **cùng một thời điểm**:

```text
2026-11-09T03:15:30.123Z
2026-11-09T10:15:30.123+07:00
```

Dòng thứ hai có offset `+07:00`, nên trừ bảy giờ để quy về UTC. **Không cộng thêm bảy giờ lần nữa** nếu giá trị đã mang offset và parser đã tạo được `Instant`.

ISO 8601 là một họ định dạng rộng; **RFC 3339** quy định một profile của dạng ngày-giờ có offset, thường phù hợp log trao đổi giữa hệ thống. Cụm từ “ISO 8601” một mình **không đủ** để cố định fractional precision, offset, định dạng tuần/năm hoặc cách parse. Một logging contract nên nêu **format cụ thể**.

### Những ví dụ dễ gây nhầm lẫn

| Giá trị | Vấn đề hoặc đánh giá |
| --- | --- |
| `2026-11-09T03:15:30.123Z` | Đủ ngày, giờ, milliseconds và UTC; thích hợp |
| `2026-11-09T10:15:30.123+07:00` | Có offset, parse được cùng instant với dòng trên |
| `2026-11-09 10:15:30` | Không có offset/timezone; không biết đây là giờ địa phương nơi nào |
| `09/11/2026 10:15:30` | Dễ phụ thuộc locale/quy ước ngày-tháng |
| `2026-11-09T03:15:30.123` | Không có `Z` hay offset; không đủ thông tin cho instant toàn cục |
| `1794194130123` | Có thể là epoch milliseconds, **chỉ an toàn nếu schema ghi rõ đơn vị** |
| `1794194130` | Có thể là epoch seconds, cách hiểu khác hẳn milliseconds |
| `2026-11-09T03:15:30Z` | Hợp lệ khi schema cho phép không có phần giây; không đáp ứng quy ước **cố định ba chữ số** |

**Quy ước được đề xuất** cho một hệ thống cần timestamp chuẩn là: một trường `timestamp` kiểu JSON string, định dạng UTC, đúng ba chữ số mili giây và hậu tố `Z`. Những tổ chức cần độ chính xác microsecond/nanosecond có thể chọn độ chính xác khác nhưng phải **quy định đồng nhất trên toàn pipeline**, không cắt tùy hứng ở mỗi service.

## 3. Chọn thời điểm ghi timestamp và giữ nó xuyên pipeline

Một sự kiện đi qua logging có thể được xử lý như sau:

```text
Business operation
      |
      | logger.info(...) tại thời điểm t0
      v
Log event được tạo và chụp timestamp
      |
      v
Queue/Async appender
      |
      v
Formatter/encoder
      |
      v
File hoặc stdout/stderr
      |
      v
Collector gán observed_at tại t1
      |
      v
Log storage và dashboard
```

Với asynchronous logging, **timestamp của event phải phản ánh t0**, không phải thời điểm một worker trong queue format thành string. Nếu tự viết formatter, việc gọi `Instant.now()` tại thời điểm format có thể làm các event bị gán giờ đến muộn, thậm chí biến dạng thứ tự phát.

Khi dùng JUL, `java.util.logging.LogRecord` có `getInstant()` để đọc timestamp lưu trong record. Trong Logback/Log4j 2, event cũng có trường timestamp theo mô hình backend; pattern/encoder phù hợp nên dùng **field của event**, không tự gọi đồng hồ tùy ý trong một custom layout khi event đã được queue.

Thời điểm **đặt** timestamp trong ứng dụng tùy loại sự kiện:

- `event=request_received`: gần thời điểm ứng dụng tiếp nhận request.
- `event=business_state_changed`: tại thời điểm trạng thái thay đổi được xác nhận theo thiết kế.
- `event=http_request_failed`: tại thời điểm handler quyết định/thông báo lỗi.
- `event=batch_completed`: lúc xử lý xong, có thể đi kèm `duration_ms`.

Đừng đặt timestamp lúc khởi động ứng dụng rồi dùng lại cho mọi log event. Cũng đừng gán thời điểm hoàn thành cho một sự kiện xảy ra trước đó mà không nói rõ `occurred_at` hoặc `recorded_at`.

## 4. `java.time` trong Java 17: dùng `Instant`, `Clock`, `DateTimeFormatter`

Các kiểu quan trọng:

| API | Dùng cho | Lưu ý |
| --- | --- | --- |
| `Instant` | Một thời điểm trên timeline UTC | Phù hợp làm dữ liệu thời gian gốc của structured event |
| `Clock.systemUTC()` | Đọc đồng hồ wall-clock có timezone UTC | Có thể bị chỉnh đồng hồ; dùng để ghi thời điểm, không đo duration monotonic |
| `Clock.fixed(...)` | Tạo đồng hồ cố định trong test/demo | Không dùng để timestamp thật trong production |
| `OffsetDateTime` | Biểu diễn ngày-giờ kèm offset | Có thể đổi thành `Instant` |
| `ZonedDateTime` | Hiển thị theo region `ZoneId`, áp dụng quy tắc zone | Phù hợp cho giao diện/hiển thị theo địa phương |
| `DateTimeFormatter.ISO_INSTANT` | Format/parse timestamp instant dạng ISO | Độ dài fractional seconds có thể biến thiên |
| `DateTimeFormatterBuilder.appendInstant(3)` | Format UTC có **đúng ba** chữ số phần giây | Hữu ích khi schema yêu cầu milliseconds cố định |
| `Instant.toEpochMilli()` | Chuyển instant sang epoch milliseconds | Kiểu `long`; phải công bố đơn vị |
| `System.nanoTime()` | Đo khoảng thời gian trong một tiến trình | Không biến thành timestamp tuyệt đối |

### `Instant` không tự chứa timezone của người dùng

`Instant` lưu một thời điểm tuyệt đối. Khi chuyển `Instant` thành giờ địa phương, phải chọn `ZoneId` hoặc `ZoneOffset`. Một timestamp có offset `+07:00` không tự cho biết đầy đủ **region timezone** như `Asia/Ho_Chi_Minh`; nhiều vùng có thể có cùng offset tại một thời điểm, và quy tắc lịch sử/DST của từng vùng có thể khác.

Không dùng `LocalDateTime.now()` rồi append chữ `Z` thủ công. `LocalDateTime` **không có offset hoặc timezone**, nên biểu diễn của nó chưa phải một `Instant`. Nếu chương trình thực chạy ở một zone khác UTC, việc gắn `Z` giả như vậy làm sai thời điểm.

### `ISO_INSTANT` và độ chính xác cố định

`DateTimeFormatter.ISO_INSTANT` là lựa chọn chuẩn để format `Instant`. Nhưng khi phần giây là 0 hoặc có số chữ số khác nhau, output có thể có **0, 3, 6 hoặc 9 chữ số fractional** theo giá trị. Nếu hệ thống yêu cầu timestamp được canh đều với chính xác 3 chữ số:

```java
java.time.format.DateTimeFormatter fixedMillis =
        new java.time.format.DateTimeFormatterBuilder()
                .appendInstant(3)
                .toFormatter();

String timestamp = fixedMillis.format(java.time.Instant.now());
```

Đây là **fragment** trong một method hoặc class, chạy được nếu có Java 17. Formatter được tạo từ `appendInstant(3)`, nên format `Instant` theo UTC với **đúng ba chữ số phần giây**; nó biểu diễn thời gian đến mili giây, không giữ độ chính xác nano. Khi yêu cầu làm tròn hoặc truncate, phải định nghĩa rõ chính sách, tránh âm thầm làm lệch kết quả.

Không viết `DateTimeFormatter.ofPattern("yyyy-MM-dd'T'HH:mm:ss.SSS'Z'")` rồi format `LocalDateTime` từ zone hệ thống: `'Z'` lúc đó chỉ là **chữ Z literal**, không chứng minh thời điểm đã được chuyển về UTC.

## 5. Ví dụ Java 17 chạy độc lập: timestamp UTC chuẩn, offset và epoch

Ví dụ sử dụng **chỉ JDK 17**, không cần SLF4J/Logback/Log4j hoặc dependency ngoài. Để stdout có thể kiểm chứng chính xác, chương trình sử dụng `Clock.fixed` với một `Instant` mẫu có độ chính xác nano và minh họa rõ việc quy về mili giây.

Lưu file **`TimestampStructuredDemo.java`**:

```java
import java.time.Clock;
import java.time.Instant;
import java.time.OffsetDateTime;
import java.time.ZoneOffset;
import java.time.format.DateTimeFormatter;
import java.time.format.DateTimeFormatterBuilder;
import java.time.temporal.ChronoUnit;

public final class TimestampStructuredDemo {
    private static final DateTimeFormatter FIXED_MILLIS =
            new DateTimeFormatterBuilder()
                    .appendInstant(3)
                    .toFormatter();

    private TimestampStructuredDemo() {
    }

    public static void main(String[] args) {
        Instant fullPrecision =
                Instant.parse("2026-11-09T03:15:30.123456789Z");

        Clock testClock = Clock.fixed(fullPrecision, ZoneOffset.UTC);
        Instant eventInstant = Instant.now(testClock);
        Instant millisecondInstant =
                eventInstant.truncatedTo(ChronoUnit.MILLIS);

        String canonicalUtc = FIXED_MILLIS.format(millisecondInstant);

        OffsetDateTime localView = millisecondInstant.atOffset(
                ZoneOffset.ofHours(7));

        String offsetText =
                localView.format(DateTimeFormatter.ISO_OFFSET_DATE_TIME);

        Instant parsedOffset = OffsetDateTime.parse(offsetText).toInstant();
        Instant parsedUtc = Instant.parse(canonicalUtc);

        System.out.println("utc=" + canonicalUtc);
        System.out.println("offset=" + offsetText);
        System.out.println("sameInstant="
                + parsedUtc.equals(parsedOffset));
        System.out.println("epochMillis="
                + millisecondInstant.toEpochMilli());
        System.out.println("epochSeconds="
                + millisecondInstant.getEpochSecond());

        // Các giá trị JSON đều là hằng/giá trị kiểm soát trong demo.
        System.out.println("{\"timestamp\":\"" + canonicalUtc
                + "\",\"level\":\"INFO\","
                + "\"event\":\"payment_authorized\"}");
    }
}
```

Biên dịch và chạy:

```bash
javac -encoding UTF-8 TimestampStructuredDemo.java
java TimestampStructuredDemo
```

**Stdout chính xác:**

```text
utc=2026-11-09T03:15:30.123Z
offset=2026-11-09T10:15:30.123+07:00
sameInstant=true
epochMillis=1794194130123
epochSeconds=1794194130
{"timestamp":"2026-11-09T03:15:30.123Z","level":"INFO","event":"payment_authorized"}
```

**Stderr:** không có output khi chương trình chạy thành công.

Giải thích cơ chế:

1. `Instant.parse(...123456789Z)` giữ độ chính xác nanosecond của thời điểm mẫu.
2. `Clock.fixed` cung cấp cùng `Instant` mỗi lần đọc, nên kết quả không phụ thuộc thời gian chạy máy thật.
3. `truncatedTo(ChronoUnit.MILLIS)` cắt phần nhỏ hơn mili giây trước khi format; chính sách này là **truncate**, không phải làm tròn tới mili giây gần nhất.
4. `DateTimeFormatterBuilder().appendInstant(3)` tạo chuỗi UTC với ba chữ số `.123` và hậu tố `Z`.
5. `ZoneOffset.ofHours(7)` chỉ thay đổi **cách biểu diễn** cùng instant: 03:15:30Z = 10:15:30+07:00.
6. `OffsetDateTime.parse(...).toInstant()` và `Instant.parse(...)` cùng trỏ tới một thời điểm, nên `sameInstant=true`.
7. `toEpochMilli()` cho `1794194130123` **milliseconds since Unix epoch**; `getEpochSecond()` cho `1794194130` **seconds since Unix epoch**.
8. JSON được tạo bằng nối chuỗi **chỉ để minh họa những giá trị đã biết và an toàn**. Với dữ liệu log thật, **không tự nối JSON từ input không tin cậy**; hãy dùng JSON serializer/structured logging encoder để escape, kiểm tra type và xử lý dữ liệu nhạy cảm.

**Chuyển thành code production:** thay `Clock.fixed(...)` bằng clock do ứng dụng nhận qua dependency injection hoặc `Clock.systemUTC()`; tạo `eventInstant = Instant.now(clock)` tại thời điểm event cần được ghi nhận; để logging framework capture một lần rồi encoder xuất timestamp. Không tạo một timestamp mới mỗi khi cùng event được đưa qua nhiều stage.

## 6. Epoch timestamp: seconds, milliseconds, microseconds và nanoseconds

Một số hệ thống truyền thời gian bằng số nguyên **Unix epoch**: số đơn vị thời gian kể từ `1970-01-01T00:00:00Z` (theo quy ước Unix). Có thể chọn numeric timestamp, nhưng schema **phải ghi rõ đơn vị**.

| Field rõ nghĩa | Ví dụ cùng một instant đến milliseconds | Đơn vị |
| --- | --- | --- |
| `epoch_seconds` | `1794194130` | Giây |
| `epoch_millis` | `1794194130123` | Mili giây |
| `epoch_micros` | `1794194130123000` | Micro giây |
| `epoch_nanos` | `1794194130123000000` | Nano giây |
| `timestamp` | `2026-11-09T03:15:30.123Z` | Chuỗi thời điểm UTC |

Những số trên dựa trên thời điểm **đã truncate đến milliseconds** của ví dụ Java, không phải nanosecond `.123456789` ban đầu. Nếu dữ liệu nguồn thật mang micro/nanosecond chính xác hơn, một trường epoch micros/nanos có thể giữ độ chính xác đó theo contract — **không tự lấy số milliseconds rồi nhân lên để coi như có thêm độ chính xác đo đạc**.

### Các lỗi đơn vị thường gặp

- Lấy `System.currentTimeMillis()` rồi coi là **epoch seconds** → năm sai rất xa.
- Lấy `Instant.getEpochSecond()` rồi gán vào field `timestamp_ms` → dữ liệu sai hệ số 1000.
- Gọi `Instant.ofEpochMilli(n)` với giá trị thực ra là seconds → thời điểm sai.
- Lưu epoch nanoseconds trong định dạng số mà client chỉ hỗ trợ integer chính xác đến **53 bits** (ví dụ một số môi trường JavaScript) → có thể mất độ chính xác.
- Dùng tên chung `timestamp` nhưng không mô tả type/units trong JSON schema → downstream tự đoán dựa vào độ dài số.

Nếu dùng epoch integer, nên đặt tên field kèm hậu tố đơn vị; hoặc định nghĩa schema `timestamp` rõ dạng RFC 3339 và chỉ đưa epoch vào field phụ nếu cần. Với dữ liệu ở gần giới hạn `long` hoặc yêu cầu nanoseconds cực lớn, phải kiểm tra overflow và khả năng represent của hệ thống đích.

### Lưu ý về Unix time và leap seconds

Time API và epoch trong Java dựa trên quy ước timeline của `Instant`. Không nên tự tính lịch/leap seconds bằng công thức cộng trừ đơn giản rồi xem đó là một thước đo duration tuyệt đối ở mọi hoàn cảnh. Thực tế đồng hồ hệ điều hành có thể được đồng bộ/smear/điều chỉnh theo chính sách, còn logger/collector hiển thị theo time scale đã chọn.

Mục tiêu của log nghiệp vụ thông thường là **nhất quán và có thể parse**, không tự giải quyết các vấn đề timekeeping cấp hệ điều hành. Khi ứng dụng đòi hỏi thời gian chính xác cao hoặc có yêu cầu kiểm toán chuyên biệt, cần hợp đồng về nguồn đồng hồ, sai số và chuẩn đồng bộ riêng.

## 7. Timestamp và duration: `System.nanoTime()` không phải thời gian UTC

Timestamp dùng để gắn **thời điểm**; duration dùng để đo **khoảng thời gian trôi qua**. Hai bài toán có đặc tính đồng hồ khác nhau.

- `Instant.now(clock)` hoặc `System.currentTimeMillis()` dùng **wall clock**. Đồng hồ có thể bị điều chỉnh bởi hệ thống đồng bộ thời gian, người quản trị hoặc máy ảo.
- `System.nanoTime()` dùng nguồn đồng hồ phù hợp cho **so sánh khoảng thời gian trong cùng tiến trình JVM**. Giá trị trả về có mốc tùy ý, **không thể format thành UTC timestamp** bằng cách áp epoch trực tiếp.
- `Duration.between(startInstant, endInstant)` tính hiệu hai thời điểm wall-clock. Nếu wall-clock bị chỉnh, giá trị có thể không phản ánh sát duration đã trôi qua khi thực thi.

Đo thời gian trong Java 17:

```java
// Fragment: processRequest() là logic do ứng dụng cung cấp.
long startNanos = System.nanoTime();
try {
    processRequest();
} finally {
    long elapsedNanos = System.nanoTime() - startNanos;
    long durationMs =
            java.util.concurrent.TimeUnit.NANOSECONDS.toMillis(elapsedNanos);
    // Đưa durationMs vào event tổng kết request; không dùng nó như epoch time.
}
```

Đoạn trên là **fragment**, không chạy độc lập vì `processRequest()` do ứng dụng cung cấp. Timestamp có thể được capture tại thời điểm bắt đầu/kết thúc để gắn mốc trên timeline, còn duration lấy từ monotonic clock. Không nói `System.nanoTime()` “là UTC nanoseconds từ năm 1970”.

### Thứ tự event trong hệ phân tán

Hai log có timestamp gần nhau từ hai máy khác nhau **không bảo đảm** thứ tự nghiệp vụ chính xác. Nguyên nhân có thể gồm:

- Clock skew giữa node A và node B.
- Appender bất đồng bộ làm event đến storage theo thứ tự khác.
- Buffering, retry hoặc mạng làm ingestion chậm.
- Timestamp gán tại những điểm khác nhau trong pipeline.
- Độ chính xác milliseconds khiến nhiều event có cùng timestamp.

Để tái dựng quan hệ nhân quả, cần xem **`traceId`/`spanId`**, parent-child spans, request ID, attempt/sequence, message offsets và logic giao dịch. Timestamps là một trục thời gian quan trọng nhưng không phải bằng chứng thứ tự tuyệt đối cho mọi môi trường.

## 8. Lọc và parse timestamp trong ứng dụng/collector

Khi nhận một structured event bên ngoài, hãy áp dụng schema validation:

1. Kiểm tra trường `timestamp` **có mặt** và đúng kiểu JSON string nếu schema yêu cầu string.
2. Parse bằng formatter phù hợp với contract. Với UTC/offset RFC 3339, có thể parse `OffsetDateTime` rồi `toInstant()`.
3. Từ chối timestamp **không có timezone/offset** nếu dùng làm thời điểm tuyệt đối và hợp đồng không định nghĩa timezone mặc định.
4. Kiểm tra range hợp lý cho nghiệp vụ (quá xa quá khứ/tương lai), nhưng tránh loại nhầm dữ liệu legitimate như backfill hoặc delayed events.
5. Chuẩn hóa về `Instant` để so sánh hoặc truy vấn.
6. Nếu cần canonical output, format lại theo đúng UTC/precision đã thống nhất.
7. Ghi nhận lỗi parse như một record lỗi có mã/metadata an toàn, không vô điều kiện log nguyên payload có thể chứa secret.

Một fragment Java 17 parse offset:

```java
java.time.OffsetDateTime withOffset =
        java.time.OffsetDateTime.parse(
                "2026-11-09T10:15:30.123+07:00");

java.time.Instant canonicalInstant = withOffset.toInstant();
System.out.println(canonicalInstant);
// 2026-11-09T03:15:30.123Z
```

Fragment này có thể đặt trong `main` hoặc một method. Dòng `System.out.println` in UTC instant với độ chính xác theo phần thập phân đã cho.

### Khi nào dùng `Instant.parse` và khi nào dùng `OffsetDateTime.parse`?

- `Instant.parse("2026-11-09T03:15:30.123Z")` phù hợp cho timestamp UTC dạng instant.
- `OffsetDateTime.parse("2026-11-09T10:15:30.123+07:00").toInstant()` cho chuỗi có offset địa phương.
- `LocalDateTime.parse("2026-11-09T10:15:30")` chỉ đọc **giờ lịch không offset**; nó không tự biết đây là instant nào.
- Một parser được đưa vào production phải tuân theo **contract chấp nhận đầu vào**. Không dựa vào việc một thư viện parser “có thể đoán” timezone khi dữ liệu thiếu.

Nếu hệ thống cũ chỉ lưu local timestamp, migration cần biết **timezone lịch sử thực tế** của nguồn, bao gồm quy tắc DST nếu có. **Gắn UTC cho mọi giá trị thiếu timezone** mà không kiểm tra là cách tạo dữ liệu sai có hệ thống.

## 9. Timestamp trong Logback, Log4j 2 và JUL

Structured logging thường đi qua backend, nơi timestamp có thể được đưa vào layout/encoder. Tên conversion word phụ thuộc framework; điều quan trọng là **định dạng field từ event timestamp**, không tạo string thời gian rời rạc trong business code cho từng lời gọi log.

### Logback và SLF4J

Một đoạn pattern Logback thường có:

```xml
<!-- Fragment bên trong <encoder> của Logback -->
<pattern>%d{yyyy-MM-dd'T'HH:mm:ss.SSS,UTC} %-5level %logger{36} - %msg%n</pattern>
```

Mục đích là timestamp đến milliseconds theo UTC, kết hợp level/logger/message. **Lưu ý:** pattern text là một phần cấu hình Logback; không phải RFC 3339 JSON string canonical vì mẫu này không ghi hậu tố `Z`. Nếu muốn đúng contract chuỗi JSON có `Z`, nên dùng **encoder/JSON timestamp converter đã được kiểm thử với backend và phiên bản**, hoặc formatter riêng đúng ngữ nghĩa timezone. Đừng coi một pattern chỉ có ngày giờ là thời điểm tuyệt đối nếu không ghi rõ timezone trong schema.

Khi dùng Logback/SLF4J structured encoder, cần xác định:

- Field timestamp phát ra là ISO 8601 string hay epoch milliseconds?
- Tên field là `timestamp`, `@timestamp` hay theo schema khác?
- Fractional precision do encoder quyết định là bao nhiêu?
- Backend có dùng UTC hay default system zone?
- Exception, MDC, request ID và timestamp có được serialize trong **cùng một JSON event** không?

### Log4j 2

Log4j 2 có `%d` trong PatternLayout và các JSON/structured layouts theo phiên bản:

```xml
<!-- Fragment PatternLayout trong appender Log4j 2 -->
<PatternLayout pattern="%d{yyyy-MM-dd'T'HH:mm:ss.SSS}{UTC} %-5p %c - %m%n"/>
```

Đây là **fragment Log4j 2**, không phải `log4j2.xml` hoàn chỉnh. Token `%d` lấy event timestamp, `{UTC}` chỉ rõ timezone được pattern sử dụng; format text mẫu cố tình không thêm `Z` để tránh hiểu nhầm chuỗi chưa được kiểm thử như RFC 3339 chuẩn. Nếu cần output JSON canonical, dùng layout/template có field timestamp phù hợp chuẩn và xác minh bằng test thực tế.

**Không sao chép nguyên cú pháp Logback sang Log4j 2**: dù đều có `%d`, cú pháp timezone và component XML có khác biệt. Các framework có thể thay đổi default timezone/precision qua phiên bản.

### Java Util Logging (JUL)

Trong JUL, `LogRecord.getInstant()` trả timestamp gắn với record. Custom formatter có thể dùng:

```java
// Fragment trong java.util.logging.Formatter.format(LogRecord record).
java.time.format.DateTimeFormatter timestampFormatter =
        new java.time.format.DateTimeFormatterBuilder()
                .appendInstant(3)
                .toFormatter();

String eventTimestamp = timestampFormatter.format(record.getInstant());
```

Việc lấy từ `record.getInstant()` đúng hơn việc gọi `Instant.now()` trong formatter nếu record bị queue rồi format muộn. `SimpleFormatter` của JUL có cơ chế format riêng, không hiểu XML của Logback hoặc Log4j 2.

**Quan trọng:** `java.util.logging.ConsoleHandler` ghi ra stderr theo thiết kế. Backend và appender có thể ghi file hoặc stdout/stderr tùy cấu hình; `timestamp` không bị ràng buộc vào một stream cụ thể.

## 10. Timestamp với JSON schema, OpenTelemetry và hệ quan sát

Nếu nhiều nhóm hoặc service cùng ghi structured log, nên có **schema bằng văn bản và test** thay vì chỉ nói “timestamp chuẩn”.

Ví dụ schema đề xuất nội bộ:

```json
{
  "timestamp": "2026-11-09T03:15:30.123Z",
  "observed_at": "2026-11-09T03:15:31.004Z",
  "level": "ERROR",
  "service": "payment-service",
  "event": "upstream_timeout",
  "errorCode": "UPSTREAM_TIMEOUT",
  "traceId": "trace-17",
  "requestId": "req-17",
  "duration_ms": 820
}
```

**Các trường trên minh họa contract**, không phải schema bắt buộc của một chuẩn telemetry cụ thể. Trong OpenTelemetry Logs, các khái niệm như **Timestamp** và **ObservedTimestamp** phân biệt thời điểm event và thời điểm hệ thống quan sát, và hệ thống có thể truyền **epoch nanoseconds** trong data model/giao thức. Một file JSON do ứng dụng tự phát có thể chọn chuỗi RFC 3339, nhưng collector cần **mapping chính xác** sang model/field nó sử dụng. Không gắn nhãn “OpenTelemetry chuẩn” chỉ vì file có tên field `timestamp`.

Một số hệ đích dùng `@timestamp`, `time` hoặc `event.timestamp`, có schema type là date/date_nanos hoặc epoch. Cần biết:

- Field nào được hệ đích dùng để **sắp xếp và lọc theo thời gian**.
- Parser mặc định nhận dạng RFC 3339 string hay numeric epoch.
- Fractional precision và range của index type.
- Timezone và cách dashboard chuyển sang timezone người dùng.
- Thời gian ingestion có bị hiển thị như event time không.

**Đừng copy hai timestamp** vào storage với hai ý nghĩa khác nhau nhưng cùng tên field. Trong migration, nên đặt alias/version schema rõ, viết test để đảm bảo dữ liệu cũ và mới được parse theo quy tắc tương ứng.

## 11. Kịch bản thực tế: sự cố xảy ra lúc 10:15 tại Việt Nam

Giả sử hệ thống tại một địa điểm có offset `+07:00` nhận một request lúc:

```text
2026-11-09T10:15:30.123+07:00
```

Trong file structured log được chuẩn hóa UTC, event xuất hiện:

```text
2026-11-09T03:15:30.123Z
```

Đây là **cùng một instant**. Nếu một dashboard hiển thị theo timezone `Asia/Ho_Chi_Minh`, nó có thể hiện giờ khoảng `10:15:30`. Người điều tra phải kiểm tra **timezone thiết lập của dashboard**, không kết luận hệ thống lệch bảy tiếng chỉ vì file và giao diện có chuỗi giờ khác nhau.

Nếu một downstream service dùng UTC nhưng một ứng dụng khác log local time thiếu offset:

```text
2026-11-09 10:15:30
```

thì việc ghép sự kiện trở nên mơ hồ. Phải biết zone mà ứng dụng nguồn đã dùng **ở thời điểm lịch sử đó**. Không sửa bằng cách gán `Z` trực tiếp vào cuối chuỗi local.

### Sự kiện cùng timestamp milliseconds

Hai event phát cách nhau vài microsecond có thể cùng được format thành `.123Z` nếu contract chỉ lưu milliseconds. **Có cùng timestamp không chứng minh hai event xảy ra đồng thời.** Nếu cần giữ thứ tự chi tiết, thêm sequence/correlation hoặc giữ độ chính xác micro/nano phù hợp, tùy hệ thống đo có thực sự hỗ trợ.

### Sự kiện đến collector muộn

Một event có `timestamp=03:15:30.123Z` nhưng collector nhận vào `03:16:10.000Z` có thể do buffer/retry/queue. Khi tìm sự cố theo **event time**, không chỉ lọc log theo ingestion time. Một số dashboard có cửa sổ thời gian mặc định lấy từ `@timestamp`/field đã map: cần xác minh field nào đang được truy vấn.

## 12. Lỗi phổ biến khi chuẩn hóa timestamp

| Triệu chứng | Nguyên nhân khả dĩ | Cách khắc phục |
| --- | --- | --- |
| Log lệch đúng vài giờ giữa hai hệ thống | Một bên dùng local timezone, bên kia dùng UTC | Chuẩn hóa `Instant`, format có `Z`/offset; kiểm tra zone của dashboard |
| `2026-11-09T10:15:30` không parse thành instant | Không có offset/timezone | Yêu cầu offset hoặc quy tắc migration rõ ràng |
| `timestamp` khi là số 10 chữ số, khi 13 chữ số | Epoch seconds lẫn milliseconds | Dùng schema và field name có đơn vị |
| `Instant.ofEpochMilli` cho thời điểm quá xa quá khứ | Đang truyền epoch seconds | Chuyển đổi units đúng |
| Mất nanoseconds khi xuất JSON | Encoder/schema chỉ giữ millis | Chọn precision phù hợp; ghi rõ chính sách truncate/round |
| Timestamp có `.1Z` ở event này và `.100Z` ở event khác | Formatter/serializer precision không cố định | Dùng canonical formatter có policy xác định |
| Timestamp bị ghi lúc collector nhận thay vì lúc event phát | Overwrite `event_time` bằng ingestion time | Lưu riêng `timestamp` và `observed_at` |
| Log async có thời gian muộn | Formatter tự gọi `Instant.now()` | Dùng timestamp đã capture trong log event |
| Chuỗi UTC `Z` nhưng giá trị giờ sai | Gắn `Z` vào `LocalDateTime` không chuyển offset | Convert từ `ZonedDateTime`/`OffsetDateTime` thành `Instant` |
| Sắp xếp log giữa nhiều node ra thứ tự kỳ lạ | Clock skew hoặc buffering | Đồng bộ đồng hồ, dùng trace/sequence, không tin tuyệt đối timestamp |
| Tìm sự cố trên dashboard không thấy event | Query dùng ingestion timestamp hoặc timezone khác | Kiểm tra field được index, timezone và window tìm kiếm |
| Một timestamp epoch nano bị làm tròn trong JavaScript | Giới hạn chính xác của số | Dùng biểu diễn string/int64 tùy giao thức, không ép qua floating number thiếu chính xác |
| Ngày-giờ đúng nhưng duration âm | Lấy hiệu wall-clock bị chỉnh | Đo duration bằng monotonic `System.nanoTime()` |
| Dữ liệu JSON không parse được | Tự nối JSON chưa escape | Dùng structured logging encoder/serializer |
| `LocalDateTime.now()` bị ảnh hưởng múi giờ máy | Không định nghĩa zone/clock cho formatter | Capture `Instant` từ clock rõ ràng |

### Chẩn đoán theo tầng

```text
Lúc sự kiện được ghi nhận: Clock/Instant đúng?
         |
         v
Backend capture event_time đúng lúc?
         |
         v
Formatter xuất UTC + precision đúng?
         |
         v
Encoder giữ type/schema và escaping đúng?
         |
         v
Collector giữ timestamp, không overwrite ngoài ý muốn?
         |
         v
Storage index đúng field và format?
         |
         v
Dashboard dùng timezone/cửa sổ truy vấn phù hợp?
```

Trình tự này giúp tránh tình huống “sửa formatter” trong khi lỗi thực tế chỉ là dashboard đang hiển thị local timezone, hoặc log đã đúng UTC nhưng bị collector parse lại thành giờ địa phương.

## 13. Kiểm thử contract timestamp

Một bộ test tối thiểu cho structured logging nên có:

1. **UTC chuẩn:** kiểm tra `timestamp` theo mẫu có `T`, `.SSS`, `Z` và parse thành `Instant`.
2. **Offset tương đương:** `2026-11-09T10:15:30.123+07:00` và `2026-11-09T03:15:30.123Z` phải cho cùng instant.
3. **Mất timezone:** chuỗi không `Z`/offset bị từ chối nếu schema yêu cầu instant tuyệt đối.
4. **Precision:** đầu vào nanoseconds được truncate/round theo quy tắc đã định; không ngẫu nhiên thay đổi số chữ số fractional.
5. **Epoch units:** kiểm tra milliseconds `1794194130123` và seconds `1794194130` không bị nhầm.
6. **Async pipeline:** timestamp event giữ nguyên khi chuyển qua queue và ghi sau.
7. **Timezones:** chạy test ở JVM có system default zone khác nhau nhưng output canonical UTC vẫn đồng nhất.
8. **Clock injection:** `Clock.fixed` giúp test không flake do phụ thuộc giờ hệ thống.
9. **DST/region:** nếu chuyển sang zone người dùng, kiểm tra thời điểm DST ambiguous/nonexistent theo quy tắc region, không chỉ dùng offset hằng.
10. **JSON schema:** `timestamp` có type string hoặc numeric rõ, field mapping ổn định, serializer escape đúng.
11. **Collector:** timestamp ingest không ghi đè event time; dashboard query đúng field.
12. **Phân tán:** cùng một request qua nhiều node có trace ID và metadata để liên kết khi clock skew.

Không cần chạy mọi test trên dữ liệu production thật. Có thể dùng fixture thời gian cố định và integration test qua encoder/collector trong staging; chỉ cần chắc rằng kết quả được tạo từ **cùng một contract**.

## 14. Checklist áp dụng trong production

- **Một chuẩn thống nhất:** chọn UTC RFC 3339/ISO-like có offset rõ, quy định fractional precision và kiểu dữ liệu.
- **Một nghĩa của field:** `timestamp` là thời điểm event; `observed_at` là lúc collector nhận, không trộn.
- **Một API thời gian phù hợp:** ưu tiên `Instant`, `Clock`, `java.time` trên Java 17+; không format `LocalDateTime` rồi gắn `Z` giả.
- **Độ chính xác có thật:** không nhân `epochMillis` thành `epochNanos` rồi coi đó là đo nano chính xác.
- **Duration riêng:** dùng `System.nanoTime()` cho elapsed duration, không dùng epoch timestamp để thay thế mặc định.
- **Format từ event:** encoder/layout lấy timestamp đã capture; giữ nguyên qua async logging.
- **Đồng bộ hạ tầng:** giám sát NTP/time synchronization, drift và pipeline delay nếu hệ thống phân tán.
- **Schema/serialization đúng:** JSON writer có escaping, timezone rõ, field names/units nhất quán.
- **Bảo mật:** không gắn dữ liệu cá nhân hoặc bí mật vào timestamp; tránh tự log payload thô để “debug giờ”.
- **Khả năng truy vấn:** storage/dashboard mapping, timezone hiển thị, retention và window tìm kiếm đã được thử.
- **Kiểm chứng end-to-end:** từ lời gọi logger đến JSON/file/collector/dashboard có cùng instant theo contract.

**Kết luận:** Timestamp chuẩn không chỉ là chuỗi ngày giờ trông đẹp mắt. Với structured logging, đó là một **hợp đồng dữ liệu**: thời điểm event được capture đúng lúc, biểu diễn UTC có offset và độ chính xác thống nhất, parse bằng `java.time`, giữ nguyên qua backend/collector và không bị nhầm với `duration_ms` hoặc ingestion time. Khi tuân thủ hợp đồng này, nhiều dịch vụ có thể được phân tích trên cùng một timeline mà không bị những sai số do format hoặc timezone tự tạo ra.

## Tài liệu tham khảo chính thức

- Oracle Java 17, `Instant`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/Instant.html
- Oracle Java 17, `Clock`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/Clock.html
- Oracle Java 17, `DateTimeFormatterBuilder`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/format/DateTimeFormatterBuilder.html
- Oracle Java 17, `LogRecord.getInstant()`: https://docs.oracle.com/en/java/javase/17/docs/api/java.logging/java/util/logging/LogRecord.html
- IETF, RFC 3339 Date and Time on the Internet: https://www.rfc-editor.org/rfc/rfc3339
- OpenTelemetry Logs Data Model: https://opentelemetry.io/docs/specs/otel/logs/data-model/
