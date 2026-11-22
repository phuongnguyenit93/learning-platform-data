
# Định dạng ngày giờ, số thập phân và bộ mã trong trao đổi dữ liệu

Trong quá trình nâng cấp Java, khả năng tương thích không chỉ liên quan đến method, bytecode hoặc dependency. Một ứng dụng có thể chạy bình thường nhưng trao đổi **sai thời điểm**, **sai số tiền**, **sai ký tự** với hệ thống khác vì format ngày giờ, quy tắc số thập phân và charset bị phụ thuộc ngầm vào JDK, locale hoặc môi trường triển khai.

Ví dụ, một dịch vụ tạo chuỗi `"01/02/2026 08:30"` mà không công bố múi giờ, định dạng ngày-tháng hay offset. Một dịch vụ khác đọc `"1.234,50"` như số 1.23450 thay vì 1234.50. Một tệp CSV tiếng Việt được ghi bằng charset mặc định của máy Windows rồi đọc như UTF-8 trên Linux sẽ xuất hiện ký tự lỗi. Các trường hợp này đều có thể xảy ra dù Java source vẫn biên dịch thành công.

Bài học thuộc chủ đề **Java Advance Compatibility Migration**, phần **Dữ liệu và giao thức**, trình bày cách thiết kế và kiểm chứng hợp đồng trao đổi dữ liệu có tính ổn định khi chuyển JDK, chuyển môi trường, thay thư viện hoặc triển khai nhiều phiên bản producer và consumer cùng lúc.

## 1. Hợp đồng trao đổi dữ liệu phải cụ thể đến mức nào?

Một giao thức dữ liệu cần trả lời những câu hỏi mà code Java thường để ngầm định:

- Ngày giờ là **thời điểm tuyệt đối** hay **thời gian địa phương**?
- Nếu là thời điểm tuyệt đối, offset hoặc múi giờ được truyền bằng cách nào?
- Format có chuẩn ISO 8601/RFC 3339 hay một pattern ứng dụng tự định nghĩa?
- Timestamp chính xác tới giây, mili giây, micro giây hay nano giây?
- Số thập phân dùng dấu chấm hay dấu phẩy; có cho phép exponent, dấu cộng và leading zero không?
- Số tiền được lưu dưới dạng decimal, integer minor units hay floating-point?
- Cần giữ nguyên scale như `1.20` so với `1.2` hay chỉ giữ giá trị số?
- Chuỗi được mã hóa bằng UTF-8, UTF-16 hay charset khác?
- Byte Order Mark (BOM), newline, Unicode normalization và ký tự lỗi được xử lý ra sao?
- Schema và version nào quyết định việc parse, validate, serialize?
- Consumer cũ sẽ xử lý dữ liệu do producer mới phát ra thế nào?

Một hợp đồng tốt không nói mơ hồ “ngày theo ISO”, “số theo locale mặc định” hay “text theo encoding của server”, mà ghi rõ representation trên **wire**, validation và chính sách migration.

### 1.1. Phân biệt giá trị, representation và encoding

Ví dụ một giao dịch diễn ra tại một thời điểm xác định, có tổng tiền 1234.50 USD và ghi chú tiếng Việt:

| Lớp | Ví dụ | Trách nhiệm |
|---|---|---|
| Giá trị thời gian | Một `Instant` trên timeline UTC | Thời điểm nghiệp vụ |
| Biểu diễn thời gian | `2026-11-12T09:30:00Z` | Text theo contract |
| Giá trị số | `BigDecimal("1234.50")` | Số thập phân chính xác |
| Biểu diễn số | `"1234.50"` | Chữ số/dấu thập phân theo contract |
| Đơn vị tiền | `USD` | Currency identifier riêng |
| Ký tự | `"Đã thanh toán"` | Dãy ký tự Unicode |
| Mã hóa byte | UTF-8 | Biến chuỗi thành bytes |
| Giao thức | JSON/CSV/XML/message | Cấu trúc trường, escape và schema |

Không nên lấy chuỗi hiển thị ở giao diện làm representation của giao thức chỉ vì nó “trông đúng” trên máy phát triển.

~~~mermaid
flowchart TD
    A["Dữ liệu nghiệp vụ có kiểu"] --> B["Quy tắc serialization rõ ràng"]
    B --> C["Representation text/schema"]
    C --> D["Charset và byte encoding"]
    D --> E["Bytes trên wire hoặc trong file"]
    E --> F["Decode bằng charset đã thống nhất"]
    F --> G["Parse và validate theo schema"]
    G --> H["Dữ liệu có kiểu ở consumer"]
~~~

## 2. Mô hình ngày giờ trong java.time

API `java.time` có nhiều kiểu, mỗi kiểu mô tả một thông tin khác nhau. Không thể hoán đổi chúng tùy tiện.

| Kiểu | Ý nghĩa | Khi nào phù hợp |
|---|---|---|
| `LocalDate` | Ngày lịch không có giờ/zone | Ngày sinh, ngày hạch toán theo quy tắc địa phương |
| `LocalTime` | Giờ trong ngày không có ngày/zone | Giờ mở cửa nếu có quy tắc zone đi kèm |
| `LocalDateTime` | Ngày + giờ địa phương, **không** có offset/zone | Lịch hẹn được giải thích theo vùng cụ thể |
| `OffsetDateTime` | Ngày giờ + offset như `+07:00` | Payload cần mang offset rõ ràng |
| `ZonedDateTime` | Ngày giờ + region `ZoneId` và quy tắc zone | Lịch trình phụ thuộc vùng như `Asia/Ho_Chi_Minh` |
| `Instant` | Thời điểm tuyệt đối trên timeline UTC | Event timestamp, audit log, created_at |
| `Duration` | Khoảng thời gian theo giây/nano giây | Timeout, độ dài tác vụ |
| `Period` | Khoảng năm/tháng/ngày theo lịch | Quy tắc định kỳ theo lịch |
| `ZoneId` | ID múi giờ hoặc offset | Chọn quy tắc diễn giải lịch |
| `ZoneOffset` | Offset cố định từ UTC | Thông tin lệch UTC của timestamp |

Một `LocalDateTime` như `2026-11-12T09:30:00` **không xác định một instant duy nhất**. Cùng giờ địa phương đó có thể tương ứng các thời điểm khác nhau ở Hà Nội và Tokyo. Trong các vùng có Daylight Saving Time (DST), thậm chí có giờ địa phương không tồn tại hoặc lặp lại.

### 2.1. Instant cho event đã xảy ra

~~~java
import java.time.Instant;

public final class EventTimestamp {
    public static void main(String[] args) {
        Instant eventTime = Instant.now();
        String wire = eventTime.toString();

        Instant recovered = Instant.parse(wire);
        System.out.println(wire);
        System.out.println(recovered.equals(eventTime));
    }
}
~~~

`Instant` thích hợp để ghi một sự kiện đã xảy ra mà các hệ thống tại nhiều múi giờ cần đối chiếu theo cùng timeline.

Nhưng producer và consumer vẫn phải thống nhất precision. Nếu một datastore chỉ giữ mili giây còn producer có nano giây, phép round-trip có thể mất phần precision thấp hơn.

### 2.2. OffsetDateTime cho timestamp có offset

~~~java
import java.time.OffsetDateTime;

OffsetDateTime created =
        OffsetDateTime.parse("2026-11-12T16:30:00+07:00");

System.out.println(created.toInstant());
~~~

Chuỗi mang offset `+07:00` đủ để suy ra instant. Offset **không phải** ID vùng. Nó không chứa đầy đủ quy tắc DST lịch sử và tương lai như `Asia/Ho_Chi_Minh` hoặc `Europe/Berlin`.

Hai payload có offset khác nhau vẫn có thể biểu diễn cùng instant. Nếu contract chỉ quan tâm timeline, hãy so sánh `toInstant()` chứ không giả định chuỗi hoặc local fields phải giống nhau.

### 2.3. ZonedDateTime cho lịch trình theo vùng

~~~java
import java.time.LocalDateTime;
import java.time.ZoneId;
import java.time.ZonedDateTime;

LocalDateTime meeting =
        LocalDateTime.of(2026, 11, 12, 9, 30);

ZonedDateTime scheduled =
        meeting.atZone(ZoneId.of("Asia/Ho_Chi_Minh"));

System.out.println(scheduled);
~~~

Nếu sự kiện cần xảy ra lúc 9:30 sáng **theo giờ địa phương của một vùng**, phải lưu ý ID vùng và quy tắc múi giờ. Chỉ lưu một `Instant` có thể không đủ để tái lập lịch định kỳ vào các ngày khác; ngược lại chỉ lưu `LocalDateTime` lại không đủ để xác định event đã xảy ra.

### 2.4. Lưu UTC không có nghĩa bỏ thông tin zone trong mọi bài toán

Một quy tắc phổ biến là lưu event timestamp bằng UTC. Điều đó phù hợp cho audit, log và sự kiện đã xảy ra. Nhưng lịch hẹn, định kỳ ngày làm việc hoặc lịch mở cửa có thể cần **cả local time và region zone ID**.

Ví dụ sản phẩm yêu cầu thực hiện tác vụ lúc 08:00 theo giờ Paris mỗi ngày. Không nên tính một UTC offset tại thời điểm cấu hình rồi giữ offset cố định cho mọi ngày sau nếu vùng có DST.

## 3. Chuẩn định dạng trên wire: ISO 8601 và RFC 3339

ISO 8601 là họ quy tắc biểu diễn ngày giờ; RFC 3339 quy định một profile timestamp dùng phổ biến trong trao đổi Internet. Trong Java, nhiều formatter có sẵn thuộc `DateTimeFormatter` nhưng chúng không hoàn toàn thay thế nhau cho mọi loại temporal.

### 3.1. Ví dụ timestamp dễ hiểu

~~~text
2026-11-12T09:30:00Z
2026-11-12T16:30:00+07:00
2026-11-12T16:30:00.123+07:00
~~~

Các chuỗi này có thể mô tả cùng một instant nếu phần offset và giây được tính tương ứng; chuỗi thứ ba có thêm 123 mili giây nên mô tả instant khác với hai chuỗi đầu.

Một contract có thể yêu cầu:

- Timestamp phải có offset hoặc ký hiệu `Z`.
- Không cho phép thiếu offset.
- Chuẩn hóa output thành UTC `Z` hoặc giữ offset đầu vào.
- Fractional seconds có độ chính xác tối đa và quy tắc zero padding.
- Chỉ chấp nhận calendar date hợp lệ.
- Quy tắc xử lý leap second được công bố nếu hệ thống có yêu cầu đặc biệt.

Không nên viết “ISO 8601” rồi cho phép mọi biến thể được parser nào đó chấp nhận mà không có schema.

### 3.2. Format và parse timestamp

~~~java
import java.time.Instant;
import java.time.OffsetDateTime;
import java.time.format.DateTimeFormatter;

public class WireTime {
    public static void main(String[] args) {
        Instant time =
                Instant.parse("2026-11-12T09:30:00.123Z");

        String output =
                DateTimeFormatter.ISO_INSTANT.format(time);

        Instant decoded =
                Instant.parse(output);

        OffsetDateTime offsetTime =
                OffsetDateTime.parse(
                        "2026-11-12T16:30:00+07:00",
                        DateTimeFormatter.ISO_OFFSET_DATE_TIME);

        System.out.println(output);
        System.out.println(decoded.equals(time));
        System.out.println(offsetTime.toInstant());
    }
}
~~~

Dùng loại parse đúng với wire schema:

- Nếu payload là instant UTC, `Instant.parse` hoặc formatter tương thích.
- Nếu payload chứa offset, `OffsetDateTime.parse` có thể phù hợp.
- Nếu payload chỉ là ngày, `LocalDate.parse`.
- Nếu wire chứa region zone ID, cần định dạng và parser giữ được zone đó.

### 3.3. Không dùng format dành cho người đọc làm format API

Ví dụ dễ lỗi:

~~~java
// Không phù hợp làm hợp đồng máy đọc nếu không định nghĩa locale/zone.
String output = java.text.DateFormat.getDateTimeInstance().format(date);
~~~

Kết quả phụ thuộc locale và cấu hình, không phải representation ổn định cho các consumer trên nền tảng khác nhau.

Nếu cần hiển thị tại giao diện người dùng, có thể dùng formatter theo locale. Nhưng API và event bus cần chuỗi thời gian theo một contract cố định.

## 4. Pattern ngày giờ: ký tự gần giống nhưng ý nghĩa khác

`DateTimeFormatter` có nhiều pattern letter. Hai lỗi đặc biệt phổ biến:

- `yyyy`: year-of-era.
- `YYYY`: week-based-year theo quy tắc tuần; **không** đồng nghĩa năm dương lịch.
- `MM`: month-of-year.
- `mm`: minute-of-hour.
- `dd`: day-of-month.
- `DD`: day-of-year.

Ví dụ:

~~~java
import java.time.LocalDate;
import java.time.format.DateTimeFormatter;
import java.util.Locale;

LocalDate date = LocalDate.of(2020, 12, 31);

DateTimeFormatter calendar =
        DateTimeFormatter.ofPattern(
                "uuuu-MM-dd", Locale.ROOT);

DateTimeFormatter weekBased =
        DateTimeFormatter.ofPattern(
                "YYYY-MM-dd", Locale.US);

System.out.println(calendar.format(date));
System.out.println(weekBased.format(date));
~~~

Gần thời điểm chuyển năm, `YYYY` có thể khác năm lịch tùy week rules của locale. Nếu giao thức muốn ngày lịch, không dùng `YYYY` thay cho `uuuu` hoặc formatter ISO chỉ vì “chữ Y lớn trông hợp hơn”.

### 4.1. uuuu và yyyy trong strict parsing

`uuuu` mô tả proleptic year; `yyyy` là year-of-era, có thể tương tác khác với strict resolver và era. Với date format chuẩn cho giao thức, ưu tiên formatter có sẵn như `DateTimeFormatter.ISO_LOCAL_DATE` hoặc quy tắc tự định nghĩa đã kiểm thử.

### 4.2. Locale và ký hiệu tháng/ngày

Pattern có tên tháng/weekday như `MMM` hoặc `EEEE` tạo text phụ thuộc locale. Nó phù hợp để hiển thị, nhưng không nên xuất làm dữ liệu máy đọc nếu consumer không được cấu hình cùng locale và provider.

Ví dụ:

~~~java
import java.time.LocalDate;
import java.time.format.DateTimeFormatter;
import java.util.Locale;

LocalDate date = LocalDate.of(2026, 11, 12);
DateTimeFormatter view =
        DateTimeFormatter.ofPattern(
                "dd MMMM uuuu", Locale.forLanguageTag("vi-VN"));

System.out.println(view.format(date));
~~~

Output có thể phụ thuộc bản locale data của JDK. Để trao đổi dữ liệu, `2026-11-12` ổn định hơn một chuỗi tên tháng có ngôn ngữ.

### 4.3. Chế độ resolver khi parse

Một parser quá dễ dãi có thể biến input ngày không hợp lệ thành ngày khác, dẫn đến dữ liệu bị sửa âm thầm. Với input từ hợp đồng nghiêm ngặt, dùng `ResolverStyle.STRICT` khi tự xây formatter:

~~~java
import java.time.LocalDate;
import java.time.format.DateTimeFormatter;
import java.time.format.ResolverStyle;
import java.util.Locale;

DateTimeFormatter strict = DateTimeFormatter
        .ofPattern("uuuu-MM-dd", Locale.ROOT)
        .withResolverStyle(ResolverStyle.STRICT);

LocalDate parsed =
        LocalDate.parse("2026-11-12", strict);
~~~

Một chuỗi như `2026-02-30` cần bị từ chối theo yêu cầu ngày hợp lệ, không tự động chuyển sang tháng 3.

## 5. DST, gap, overlap và dữ liệu lịch sử

Trong những múi giờ có chuyển DST, cùng local datetime có thể:

- Có đúng một offset hợp lệ.
- Không có offset hợp lệ vì đồng hồ nhảy qua một khoảng (gap).
- Có hai offset hợp lệ vì đồng hồ lùi lại (overlap).

Kiểm tra bằng `ZoneRules`:

~~~java
import java.time.LocalDateTime;
import java.time.ZoneId;
import java.time.ZoneOffset;
import java.util.List;

ZoneId zone = ZoneId.of("Europe/Berlin");

LocalDateTime localTime =
        LocalDateTime.of(2026, 10, 25, 2, 30);

List<ZoneOffset> offsets =
        zone.getRules().getValidOffsets(localTime);

System.out.println("Valid offsets: " + offsets);
~~~

Nếu có hai offset, một local datetime không đủ để chọn instant duy nhất. Nếu không có offset, thời gian địa phương đó không tồn tại theo quy tắc vùng tại ngày tương ứng.

Chính sách nghiệp vụ phải định nghĩa cách xử lý:

- Từ chối thời gian mơ hồ và yêu cầu người dùng chọn.
- Chọn offset trước hoặc sau theo quy tắc nghiệp vụ.
- Chuyển thời gian qua gap theo một rule được công bố.
- Lưu cả instant đã giải quyết và zone ID nếu cần audit.

Không nên chỉ gọi `atZone(...)` rồi coi default resolution của Java là đúng cho mọi nghiệp vụ.

### 5.1. TZDB có thể thay đổi qua JDK update

Các quy tắc múi giờ được duy trì trong cơ sở dữ liệu time zone (tzdb). Khi luật của quốc gia/vùng thay đổi, bản JDK cập nhật có thể đưa quy tắc khác.

Do đó:

- Một lịch sự kiện trong tương lai có thể được quy đổi sang UTC khác sau khi tzdb cập nhật.
- Một test hardcode offset cho ngày tương lai có thể không ổn định.
- Khi kiểm chứng lịch, ghi phiên bản JDK/tzdb và vùng dùng trong phép thử.
- Dịch vụ phân tán nên có chính sách cập nhật tzdb nhất quán khi cùng tính lịch.

Không xem offset hiện tại là offset vĩnh viễn của một region.

## 6. Unix epoch và đơn vị đo thời gian

Một lỗi dữ liệu phổ biến là nhầm **giây**, **mili giây**, **micro giây** và **nano giây** tính từ Unix epoch.

| Biểu diễn | Đơn vị | Ví dụ về chiều dài số thông thường trong thời hiện đại |
|---|---|---|
| Epoch seconds | Giây | Khoảng 10 chữ số |
| Epoch millis | Mili giây | Khoảng 13 chữ số |
| Epoch micros | Micro giây | Khoảng 16 chữ số |
| Epoch nanos | Nano giây | Có thể cần số nguyên 64-bit với giới hạn phạm vi rõ |

Độ dài chỉ là dấu hiệu nhận biết, **không phải quy tắc parse đáng tin**. Hợp đồng phải ghi tên trường và đơn vị rõ ràng, ví dụ `createdAtEpochMillis`.

~~~java
import java.time.Instant;

long millis = 1_800_000_000_000L;
Instant time = Instant.ofEpochMilli(millis);

long roundTrip = time.toEpochMilli();
System.out.println(roundTrip == millis);
~~~

Nếu consumer đọc milliseconds như seconds, dữ liệu thời gian sẽ bị sai nghiêm trọng hoặc vượt phạm vi hỗ trợ.

### 6.1. Timestamp precision phải có chính sách

Nhiều hệ thống lưu timestamp ở độ chính xác khác:

- Java `Instant` có khả năng biểu diễn nanosecond.
- Database column có thể giữ microsecond hoặc millisecond tùy kiểu và cấu hình.
- JSON client có thể làm tròn hoặc cắt phần fraction.
- Một thư viện serialize có thể ghi ba, sáu hoặc chín chữ số fraction.

Khi so sánh round-trip, xác định precision thực tế trước. Có thể chuẩn hóa theo milliseconds nếu contract chỉ yêu cầu mức đó:

~~~java
import java.time.Instant;
import java.time.temporal.ChronoUnit;

Instant source = Instant.now();
Instant normalized = source.truncatedTo(ChronoUnit.MILLIS);
~~~

Việc cắt precision phải được thiết kế và công bố, không phát sinh vô tình bởi mapper.

### 6.2. Không dùng local datetime làm event timestamp khi thiếu zone

Ví dụ JSON sau không tự xác định một instant:

~~~json
{
  "createdAt": "2026-11-12T16:30:00"
}
~~~

Nếu contract là event timestamp, tốt hơn:

~~~json
{
  "createdAt": "2026-11-12T09:30:00Z"
}
~~~

Nếu thực sự cần lưu local datetime của lịch hẹn, có thể mô hình hóa tường minh:

~~~json
{
  "appointmentLocalTime": "2026-11-12T16:30:00",
  "timeZone": "Asia/Ho_Chi_Minh"
}
~~~

Hai thiết kế phục vụ các bài toán khác nhau. Không nên ngầm gán server default zone cho mọi local datetime từ request.

## 7. Cẩn thận với java.util.Date, Calendar và JDBC

Các hệ thống Java lâu năm có thể dùng `java.util.Date`, `Calendar`, `java.sql.Date`, `java.sql.Timestamp` và những API định dạng cũ. Chúng có quy tắc chuyển đổi khác nhau và dễ bị nhầm với `java.time`.

### 7.1. Date không lưu timezone

`java.util.Date` đại diện một thời điểm, nhưng `Date.toString()` hiển thị dựa vào timezone mặc định của JVM. Vì vậy, không thể dùng `Date.toString()` làm giao thức timestamp ổn định.

Khi chuyển sang `Instant`:

~~~java
import java.time.Instant;
import java.util.Date;

Date legacy = new Date();
Instant instant = legacy.toInstant();
Date restored = Date.from(instant);
~~~

Chuyển đổi này diễn giải instant; không tự giữ zone hiển thị của một user.

### 7.2. SimpleDateFormat có trạng thái mutable

`java.text.SimpleDateFormat` có thể không thread-safe khi chia sẻ giữa các thread. Nếu migrate, ưu tiên `java.time.format.DateTimeFormatter` là immutable và có thể tái sử dụng an toàn theo hợp đồng formatter phù hợp.

Cần tránh thay đổi pattern mà chưa kiểm tra tương đương, bởi ký tự pattern giữa API cũ và mới có thể khác cách diễn giải trong những trường hợp đặc biệt.

### 7.3. JDBC và database timezone

Một trường SQL `TIMESTAMP` hoặc `TIMESTAMP WITH TIME ZONE` có semantics phụ thuộc database/vendor. Không nên suy ra mọi hệ quản trị sẽ lưu nguyên zone ID hoặc giữ offset theo cùng cách.

Cần định nghĩa:

- Column type và semantics.
- Conversion của JDBC driver.
- Session timezone của database.
- Precision (milli/micro/nano).
- Cách ORM ánh xạ `Instant`, `OffsetDateTime`, `LocalDateTime`.
- Migration và behavior khi driver/JDK nâng cấp.

Kiểm thử với **database thật và driver thực tế**, không chỉ H2 hoặc một mock khác production.

## 8. Số thập phân: giá trị và chuỗi biểu diễn

Số `1234.50` có thể biểu diễn bằng:

~~~text
1234.50
1,234.50
1.234,50
1 234,50
1.2345E3
~~~

Những chuỗi này không tương đương đối với mọi parser. Trong giao thức, phải quy định cú pháp: dấu thập phân, grouping có được phép không, exponent, dấu âm, giới hạn precision và scale.

**Giao thức máy đọc không nên lấy trực tiếp output của `NumberFormat` theo locale người dùng.**

### 8.1. BigDecimal cho giá trị thập phân chính xác

~~~java
import java.math.BigDecimal;

BigDecimal amount = new BigDecimal("1234.50");

System.out.println(amount.toPlainString());
System.out.println(amount.scale());
~~~

`BigDecimal` giúp giữ số thập phân chính xác theo decimal representation. Tránh tạo từ literal `double` nếu cần bảo toàn đúng số do người dùng hoặc giao thức cung cấp:

~~~java
BigDecimal problematic = new BigDecimal(0.1);
BigDecimal exact = new BigDecimal("0.1");
~~~

`new BigDecimal(0.1)` nhận giá trị nhị phân thực của double, không phải chính xác decimal literal “0.1”.

### 8.2. BigDecimal: compareTo và equals

~~~java
import java.math.BigDecimal;

BigDecimal a = new BigDecimal("1.20");
BigDecimal b = new BigDecimal("1.2");

System.out.println(a.compareTo(b) == 0); // true
System.out.println(a.equals(b));          // false
~~~

`compareTo` xem chúng có cùng giá trị số; `equals` còn xét scale. Vì vậy, nếu payload cần giữ scale (ví dụ số chữ số thập phân khai báo trên chứng từ), đừng vô tình normalize bỏ trailing zeros. Ngược lại, nếu hợp đồng chỉ yêu cầu giá trị số, test không nên đánh đồng khác biệt scale với lỗi tính toán.

### 8.3. toString và toPlainString

`BigDecimal.toString()` có thể xuất dạng exponent trong một số tình huống. `toPlainString()` luôn xuất dạng decimal plain text, không dùng exponent, nhưng có thể có độ dài lớn khi scale rất lớn.

~~~java
BigDecimal value = new BigDecimal("1E+6");

System.out.println(value.toString());      // 1E+6
System.out.println(value.toPlainString()); // 1000000
~~~

Khi chọn contract decimal string, phải quy định có cho phép exponent hay không, scale/precision tối đa và giới hạn kích thước input để tránh payload bất thường.

### 8.4. Tiền tệ cần currency riêng

Một số tiền là ít nhất một cặp `amount + currency code`:

~~~json
{
  "amount": "1234.50",
  "currency": "USD"
}
~~~

Không nên truyền:

~~~json
{
  "amount": "$1,234.50"
}
~~~

như một giá trị máy đọc nếu không có schema riêng; dấu `$` không xác định đơn vị tiền duy nhất và format phụ thuộc locale. Mã currency và quy tắc rounding/scale cần được quy định trong hợp đồng nghiệp vụ.

## 9. Rounding, precision và giới hạn dữ liệu

Số thập phân chính xác không đồng nghĩa với mọi phép toán đều có thể trả kết quả hữu hạn ở scale được yêu cầu.

~~~java
import java.math.BigDecimal;
import java.math.RoundingMode;

BigDecimal amount = new BigDecimal("12.345");
BigDecimal rounded =
        amount.setScale(2, RoundingMode.HALF_UP);

System.out.println(rounded.toPlainString());
~~~

Output `12.35` trong ví dụ là quyết định rounding. `HALF_UP` chỉ minh họa; lĩnh vực tài chính, kế toán, thuế có thể dùng policy khác.

### 9.1. Phép chia phải có quy tắc

~~~java
import java.math.BigDecimal;
import java.math.RoundingMode;

BigDecimal one = BigDecimal.ONE;
BigDecimal three = new BigDecimal("3");

BigDecimal quotient =
        one.divide(three, 6, RoundingMode.HALF_EVEN);
~~~

Nếu gọi một phép chia không có biểu diễn decimal hữu hạn mà không chỉ định cách xử lý, `BigDecimal.divide(...)` có thể ném `ArithmeticException`.

### 9.2. Ràng buộc contract số

Ghi rõ:

- Precision tối đa.
- Scale cho phép, có cho phép scale âm không.
- Dải min/max và cách xử lý overflow.
- Dấu âm, số 0, negative zero nếu consumer dùng floating-point.
- Có chấp nhận exponent không.
- Có chấp nhận leading `+` hoặc leading zeros không.
- Cách rounding và thời điểm rounding.
- Chính sách với `NaN`/`Infinity` khi nguồn dữ liệu là double/float; `BigDecimal` không biểu diễn các giá trị này.

Không nên chỉ nói “decimal” rồi để từng thư viện tự chọn quy tắc parse/serialize.

### 9.3. Minor units phải đi kèm scale/currency

Một số hệ thống lưu amount bằng integer minor units:

~~~json
{
  "minorUnits": 123450,
  "currency": "USD"
}
~~~

Điều này có thể tương ứng 1234.50 USD nếu contract quy định scale 2. Nhưng không phải mọi currency mặc định có hai chữ số fraction; cũng có chính sách riêng theo nghiệp vụ. Consumer cần biết chính xác scale gắn với giá trị. Không suy luận từ một quy tắc duy nhất cho mọi token hoặc đơn vị tiền.

## 10. NumberFormat và Locale: phù hợp cho UI, không mặc định cho wire

`NumberFormat` và `DecimalFormat` có thể tạo chuỗi theo locale:

~~~java
import java.math.BigDecimal;
import java.text.NumberFormat;
import java.util.Locale;

BigDecimal amount = new BigDecimal("1234.50");

NumberFormat en =
        NumberFormat.getNumberInstance(Locale.US);

NumberFormat de =
        NumberFormat.getNumberInstance(Locale.GERMANY);

System.out.println(en.format(amount));
System.out.println(de.format(amount));
~~~

Các khác biệt về dấu chấm, dấu phẩy, grouping và chữ số là **hành vi mong đợi khi trình bày theo locale**, nhưng không nên đưa thẳng vào JSON field hoặc CSV trao đổi máy đọc.

### 10.1. Locale mặc định có thể đổi sau nâng JDK hoặc container

~~~java
NumberFormat format = NumberFormat.getNumberInstance();
~~~

Code trên phụ thuộc default formatting locale. Nếu server đổi locale, kết quả thay đổi mà source không sửa.

Trong Java, dữ liệu locale cũng có thể được cập nhật qua JDK, bao gồm các quy tắc CLDR. Một số locale dùng Unicode spaces đặc biệt làm grouping. Với giao thức, tránh phụ thuộc vào việc một dấu phân cách cụ thể sẽ bất biến qua mọi JDK update.

### 10.2. Không parse số bằng String.replace tùy tiện

Mã như:

~~~java
String normalized =
        input.replace(".", "").replace(",", ".");
~~~

chỉ phù hợp nếu đã kiểm tra chính xác format đầu vào, và rất dễ sai khi input chứa dấu phân cách không như giả định.

Đối với input giao diện, hãy chọn locale của người dùng, dùng parser tương ứng và xác minh toàn bộ chuỗi đã được parse. Đối với giao thức máy đọc, đặt cú pháp canonical và parser nghiêm ngặt.

### 10.3. ParsePosition giúp phát hiện ký tự thừa

~~~java
import java.text.NumberFormat;
import java.text.ParsePosition;
import java.util.Locale;

NumberFormat parser =
        NumberFormat.getNumberInstance(Locale.GERMANY);

String input = "1.234,50";
ParsePosition pos = new ParsePosition(0);

Number number = parser.parse(input, pos);

if (number == null || pos.getIndex() != input.length()) {
    throw new IllegalArgumentException("Invalid numeric input");
}

System.out.println(number);
~~~

Kết quả `Number` có thể không phải `BigDecimal`. Nếu cần giữ độ chính xác thập phân, xem xét `DecimalFormat.setParseBigDecimal(true)` khi implementation hỗ trợ và vẫn validate schema của input.

## 11. JSON và độ chính xác số

JSON có cú pháp số riêng; nó không dùng grouping theo locale. Nhưng một JSON number không bắt buộc được mọi ngôn ngữ parse bằng cùng kiểu số.

Ví dụ:

~~~json
{
  "amount": 1234.50,
  "currency": "USD"
}
~~~

Trong Java, thư viện JSON có thể parse sang `BigDecimal` nếu được cấu hình; trong JavaScript, JSON number thường là IEEE 754 double. Điều đó có thể làm mất precision của một số giá trị lớn hoặc có nhiều chữ số thập phân.

Nếu contract cần bảo toàn decimal chính xác ở mọi client, một lựa chọn là decimal string:

~~~json
{
  "amount": "1234.50",
  "currency": "USD"
}
~~~

Đây là **quyết định schema**: consumer phải parse field chuỗi theo decimal grammar quy định, không tự động coi nó là number. Lựa chọn khác là integer minor units với giới hạn rõ ràng.

### 11.1. Không đánh đồng JSON number với double của Java

Một số thư viện Java hỗ trợ deserialize JSON number sang `BigDecimal`; một số mặc định dùng `Double` hoặc `Long` theo cấu hình. Kết quả phụ thuộc type của field và mapper configuration.

Cần test:

- Giá trị lớn hơn phạm vi số nguyên an toàn của client JavaScript, nếu liên quan.
- Decimal có nhiều chữ số fractional.
- Số âm và số 0.
- Ký hiệu exponent nếu contract cho phép.
- Scale/trailing zeros nếu cần giữ.
- Round-trip qua producer/consumer thuộc các ngôn ngữ khác nhau.

### 11.2. Schema phải xác định cấu trúc và validation

Một schema có thể mô tả:

- `timestamp` là RFC 3339 date-time string có offset.
- `amount` là decimal string với pattern hoặc constraint.
- `currency` là mã đơn vị tiền.
- `note` là Unicode string được encode UTF-8 trên wire.

Nếu producer đổi từ `"amount": "12.30"` sang `"amount": 12.30`, đây là thay đổi **kiểu dữ liệu JSON**, không phải chỉ là tối ưu định dạng. Cần đánh giá backward compatibility của mọi consumer.

## 12. Bộ mã ký tự và Unicode không phải cùng một khái niệm

Java `String` chứa văn bản theo mô hình Unicode, trong khi tệp và network transport lưu **bytes**. Charset quyết định cách chuyển đổi.

Một chuỗi tiếng Việt:

~~~text
Đơn hàng đã xác nhận
~~~

có thể được encode thành bytes UTF-8, UTF-16 hoặc charset khác. Nếu bên nhận decode sai charset, chữ có dấu có thể bị lỗi (mojibake) hoặc thành ký tự thay thế.

### 12.1. Encode và decode bằng UTF-8 tường minh

~~~java
import java.nio.charset.StandardCharsets;
import java.util.Arrays;

public class TextEncoding {
    public static void main(String[] args) {
        String text = "Đơn hàng đã xác nhận";

        byte[] bytes =
                text.getBytes(StandardCharsets.UTF_8);

        String recovered =
                new String(bytes, StandardCharsets.UTF_8);

        System.out.println(Arrays.toString(bytes));
        System.out.println(text.equals(recovered));
    }
}
~~~

Nếu cả producer và consumer đều dùng UTF-8 theo contract, chuỗi có thể round-trip chính xác với input hợp lệ.

### 12.2. Tránh charset mặc định trong giao thức

Những lời gọi sau phụ thuộc default charset hoặc quy ước implicit của API:

~~~java
byte[] data = text.getBytes();
String decoded = new String(data);
~~~

Để trao đổi dữ liệu, nên viết:

~~~java
byte[] data =
        text.getBytes(java.nio.charset.StandardCharsets.UTF_8);

String decoded =
        new String(data, java.nio.charset.StandardCharsets.UTF_8);
~~~

Cùng charset phải được áp dụng ở hai đầu, kể cả khi hệ thống chỉ có một service Java tại thời điểm đầu.

### 12.3. JDK 18 và thay đổi default charset

Từ JDK 18, JEP 400 đưa UTF-8 thành default charset trong hầu hết các cấu hình tiêu chuẩn, thay vì phụ thuộc phổ biến vào charset mặc định của hệ điều hành như trước. Nhưng **không có lý do để dựa vào default charset** khi thiết kế giao thức.

Một ứng dụng cũ từng ghi file bằng charset legacy trên Windows rồi chuyển sang JDK mới có thể gặp khác biệt khi:

- Ghi file mới dưới UTF-8.
- Đọc file cũ bằng charset mặc định mới.
- Dùng thư viện tự đọc file theo hệ điều hành.
- Chuyển file giữa Windows, Linux và container image.

Cần đánh giá migration dữ liệu đã lưu, không chỉ thay JDK. Với file legacy, xác định charset thật của file bằng metadata/hợp đồng, không tự giả định file cũ là UTF-8 rồi decode sai.

### 12.4. Dùng API Files với charset rõ ràng

~~~java
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

Path path = Path.of("orders.csv");

Files.writeString(
        path,
        "id,description\n1,Đã thanh toán\n",
        StandardCharsets.UTF_8);

String content =
        Files.readString(path, StandardCharsets.UTF_8);
~~~

Ngay cả khi một overload hiện đại dùng UTF-8 mặc định, truyền charset rõ giúp người bảo trì thấy contract ngay tại call site và dễ đối chiếu với consumer.

## 13. CharsetDecoder và dữ liệu byte không hợp lệ

Không phải mọi dãy byte đều hợp lệ trong UTF-8. Cách xử lý malformed input là một phần của hợp đồng dữ liệu:

- **REPORT**: từ chối dữ liệu lỗi.
- **REPLACE**: chèn ký tự thay thế.
- **IGNORE**: bỏ qua bytes không hợp lệ.

Với dữ liệu tài chính hoặc định danh quan trọng, im lặng thay thế/bỏ bytes có thể làm hỏng dữ liệu mà không ai nhận ra. Nên cân nhắc từ chối và ghi lỗi có kiểm soát.

~~~java
import java.nio.ByteBuffer;
import java.nio.CharBuffer;
import java.nio.charset.CharacterCodingException;
import java.nio.charset.CodingErrorAction;
import java.nio.charset.StandardCharsets;

public class StrictUtf8 {
    public static String decode(byte[] bytes)
            throws CharacterCodingException {

        var decoder = StandardCharsets.UTF_8.newDecoder()
                .onMalformedInput(CodingErrorAction.REPORT)
                .onUnmappableCharacter(CodingErrorAction.REPORT);

        CharBuffer result =
                decoder.decode(ByteBuffer.wrap(bytes));

        return result.toString();
    }
}
~~~

Khi encode Java string thành UTF-8, cũng cần hiểu cách encoder xử lý chuỗi có surrogate không ghép đôi. Với dữ liệu yêu cầu tính toàn vẹn, kiểm tra đầu vào hợp lệ thay vì để quá trình chuyển đổi âm thầm tạo replacement.

### 13.1. Không đo độ dài wire bằng String.length()

`String.length()` trả về số UTF-16 code units, không phải số Unicode code points và cũng không phải số bytes UTF-8.

~~~java
import java.nio.charset.StandardCharsets;

String value = "Tiếng Việt 😊";

int utf16Units = value.length();
int codePoints = value.codePointCount(0, value.length());
int utf8Bytes =
        value.getBytes(StandardCharsets.UTF_8).length;

System.out.println(utf16Units);
System.out.println(codePoints);
System.out.println(utf8Bytes);
~~~

Nếu một giao thức có trường length hoặc giới hạn kích thước payload, phải quy định length được tính theo bytes, code points, grapheme clusters hay ký tự theo nghĩa của người dùng. Không trộn các đơn vị.

### 13.2. Cắt chuỗi theo byte có thể làm hỏng UTF-8

Nếu cắt `byte[]` giữa một chuỗi UTF-8 multibyte, consumer có thể nhận dữ liệu malformed. Nếu giới hạn là bytes, cần cắt tại ranh giới code point hoặc dùng cơ chế encode/stream đã kiểm soát; nếu giới hạn là số ký tự hiển thị, phải cân nhắc Unicode grapheme clusters.

## 14. BOM, newline và chuẩn hóa Unicode

### 14.1. UTF-8 BOM

UTF-8 có thể xuất hiện với prefix byte BOM `EF BB BF` trong một số file, dù BOM không cần thiết để xác định endianness của UTF-8.

Một số phần mềm spreadsheet chấp nhận hoặc mong chờ BOM trong file CSV; nhiều parser khác coi nó là ký tự `U+FEFF` ở đầu nội dung và làm sai tên header đầu tiên.

Với mỗi định dạng file, phải quy định:

- Có cho phép BOM không?
- Nếu có, parser loại bỏ BOM ở đâu?
- Có ghi BOM khi xuất file hay không?
- Test với cả trường hợp được phép và không được phép.

Không tự xóa mọi ký tự `U+FEFF` ở bất kỳ vị trí nào nếu chưa biết semantics; xử lý BOM đầu file là một quyết định ở tầng encoding/file format.

### 14.2. Newline

Các môi trường dùng convention khác nhau:

- LF: `\n`.
- CRLF: `\r\n`.
- CR: `\r`, ít gặp hơn trong file hiện đại.

Với CSV hoặc text protocol, ghi rõ newline output; khi parse, quyết định có chấp nhận nhiều kiểu newline không. Tránh nối `System.lineSeparator()` vào giao thức yêu cầu LF cố định, vì nó phụ thuộc hệ điều hành.

### 14.3. Unicode normalization

Hai chuỗi nhìn giống nhau có thể dùng dãy code point khác nhau. Ví dụ ký tự có dấu có thể xuất hiện ở dạng composed hoặc decomposed.

~~~java
import java.text.Normalizer;

String input = "Tiếng Việt";

String normalized =
        Normalizer.normalize(input, Normalizer.Form.NFC);

System.out.println(normalized);
~~~

Cần xác định có normalize hay không ở ranh giới nào. Việc normalize có thể phù hợp cho tìm kiếm, so sánh hoặc ID theo thiết kế, nhưng không nên áp dụng bừa bãi cho:

- Văn bản phải giữ nguyên bytes để kiểm tra chữ ký số.
- Payload đã ký hoặc hash.
- Dữ liệu mà byte-level equality là yêu cầu.
- Một số định danh có quy tắc riêng.

Đặc biệt, nếu ký số trên JSON/XML/text, hai chuỗi cùng nội dung nhìn thấy nhưng khác whitespace hoặc normalization có thể cho chữ ký khác. Cần quy định canonicalization ở tầng giao thức hoặc ký đúng bytes được truyền.

## 15. HTTP, JSON, CSV và XML có quy tắc encoding khác nhau

### 15.1. HTTP và Content-Type

Với giao thức HTTP truyền text, cách diễn giải bytes phụ thuộc media type và quy tắc của format đó. Một số định dạng có charset parameter, một số có quy tắc riêng.

Đối với JSON interoperable giữa các hệ thống mở, UTF-8 là lựa chọn tiêu chuẩn theo quy tắc JSON hiện đại. Không nên giả định một chuỗi ký tự Java khi gửi HTTP sẽ tự động được encode đúng nếu HTTP client hoặc framework đặt charset khác.

Kiểm tra:

- Media type thực tế.
- Body bytes được encode bằng gì.
- Consumer decode bằng gì.
- Có double-encode hoặc URL/form encoding nhầm lẫn không.
- Content-Length nếu có được tính theo bytes, không phải ký tự.

### 15.2. JSON escaping không phải charset encoding

Một chuỗi JSON có thể xuất:

~~~json
{
  "message": "Đã xử lý"
}
~~~

hoặc dùng Unicode escape cho một số ký tự. Sau JSON serialization, toàn body vẫn cần được encode thành bytes theo charset của transport. Dấu backslash escape trong JSON và UTF-8 là hai tầng khác nhau.

Đừng “sửa lỗi dấu tiếng Việt” bằng cách tự thay ký tự thành escape string không đúng JSON context.

### 15.3. CSV cần schema ngoài dấu phân cách

CSV không tự mang đủ thông tin về:

- Kiểu dữ liệu cột.
- Định dạng ngày giờ.
- Locale của số.
- Currency.
- Charset.
- Header.
- Newline và quoting behavior.

Ví dụ canonical CSV:

~~~csv
order_id,created_at,amount,currency,note
A-100,2026-11-12T09:30:00Z,1234.50,USD,Da thanh toan
~~~

Nếu cần tiếng Việt, encode toàn file UTF-8 và ghi rõ policy BOM. Khi cột chứa dấu phẩy, dấu nháy hoặc newline, phải dùng CSV writer/parser tuân thủ quy tắc escape/quote thay vì ghép chuỗi thủ công.

### 15.4. Cẩn thận khi người dùng mở CSV bằng spreadsheet

Spreadsheet có thể tự đoán kiểu ngày, số thập phân hoặc bỏ leading zeros theo locale máy. Một mã khách hàng `"00123"` có thể bị hiểu thành số 123. Điều này không có nghĩa backend CSV mất bytes, mà consumer spreadsheet đã áp dụng kiểu suy luận.

Với dữ liệu nhạy về định dạng, dùng import schema cố định hoặc file format có kiểu dữ liệu rõ. Nếu xuất CSV dành cho người dùng, ghi hướng dẫn import và cân nhắc rủi ro công thức spreadsheet từ ô bắt đầu bằng ký tự đặc biệt theo chính sách bảo mật xuất dữ liệu.

### 15.5. XML encoding declaration phải khớp bytes

Ví dụ XML:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<order>
  <createdAt>2026-11-12T09:30:00Z</createdAt>
  <amount currency="USD">1234.50</amount>
</order>
~~~

Khai báo `encoding="UTF-8"` chỉ đúng nếu bytes thực sự được ghi bằng UTF-8. Một serializer dùng charset mặc định khác nhưng vẫn ghi declaration UTF-8 sẽ tạo file không nhất quán.

XML còn có quy tắc namespace, schema, entity và canonicalization; nếu ký XML, whitespace và canonicalization phải được kiểm soát theo chuẩn chữ ký áp dụng.

## 16. Serializer và framework là một phần của hợp đồng

Ứng dụng có thể không tự gọi `DateTimeFormatter` hay `BigDecimal.toPlainString()` vì framework JSON/XML/JDBC đảm nhiệm.

Khi nâng dependency hoặc JDK cần kiểm tra:

- Serializer dùng `java.util.Date`, `Instant` hay `LocalDateTime`?
- Timestamp được ghi thành text hay numeric epoch?
- Numeric epoch là seconds hay millis?
- Formatter dùng offset UTC, local zone hay default JVM timezone?
- BigDecimal được serialize thành JSON number, string hay exponent notation?
- Parser đọc số thành `Double` hay `BigDecimal`?
- Encoding HTTP body/file có được chỉ định không?
- Có module/plugin cho `java.time` và có cấu hình mặc định mới không?
- Có thay đổi trong cách escape Unicode, null field, property name hoặc schema không?

Đặc biệt, thay một serializer có thể thay representation dù DTO giữ nguyên field type.

### 16.1. DTO nên có semantics rõ

~~~java
import java.math.BigDecimal;
import java.time.Instant;

public record PaymentEvent(
        String id,
        Instant occurredAt,
        BigDecimal amount,
        String currency,
        String note) {
}
~~~

DTO biểu thị kiểu dữ liệu trong Java; nó **không tự chứng minh** JSON output có đúng timestamp string, decimal format và encoding mong đợi. Cần thiết lập mapper và test wire representation thực tế.

### 16.2. Đừng coi annotation là kiểm chứng đủ

Một annotation trên DTO có thể điều khiển serializer của một framework, nhưng không áp dụng nếu producer khác không dùng framework đó, hoặc nếu phiên bản dependency thay đổi cách diễn giải annotation.

Hợp đồng cần được mô tả trong schema và **kiểm thử tại ranh giới thực tế**, không chỉ nhìn source.

## 17. Kiểm thử tương thích hai chiều producer và consumer

Khi nâng cấp Java, nhiều hệ thống không thể triển khai đồng thời. Một thời gian sẽ có:

- Producer cũ → Consumer cũ.
- Producer mới → Consumer cũ.
- Producer cũ → Consumer mới.
- Producer mới → Consumer mới.

Ma trận kiểm thử:

| Producer | Consumer | Kiểm chứng quan trọng |
|---|---|---|
| Cũ | Cũ | Baseline dữ liệu đã vận hành |
| Mới | Mới | Contract mới và chức năng mới hoạt động |
| Mới | Cũ | Consumer cũ hiểu date/decimal/charset mới hay không? |
| Cũ | Mới | Consumer mới đọc được dữ liệu/tệp/event cũ? |

Ví dụ một producer mới bắt đầu xuất timestamp có nano seconds, trong khi consumer cũ chỉ parse đúng ba chữ số millisecond. Dù mỗi bên chạy tốt độc lập, chúng có thể không tương thích.

Cần ghi version contract và lựa chọn một trong các cách:

- Giữ output nằm trong phạm vi được cả hai bên hỗ trợ.
- Nâng consumer trước khi producer phát format mới.
- Chấp nhận nhiều dạng input có kiểm soát nhưng phát một dạng canonical.
- Version hóa endpoint, event schema hoặc file format nếu thay đổi breaking.
- Cung cấp adapter trong giai đoạn chuyển tiếp.

Không nên “fix” bằng cách parser tự đoán mọi format nếu việc đoán có thể làm sai thời gian hoặc tiền.

## 18. Xây dựng bộ dữ liệu regression

### 18.1. Bộ case ngày giờ

Chọn các trường hợp đại diện:

- Timestamp UTC có `Z`.
- Timestamp có offset dương và âm.
- Timestamp có/không có fraction.
- Giá trị sát ngày đổi năm.
- Ngày 29/02 hợp lệ và ngày không hợp lệ.
- DST gap và overlap ở các vùng được hỗ trợ.
- Ngày lịch không có timezone.
- Epoch seconds/millis với đơn vị tường minh.
- Chuyển đổi DB timestamp với precision thấp hơn.
- Dữ liệu lịch tương lai khi tzdb cập nhật.

Không chỉ test “bây giờ” hoặc một ngày cố định không có DST.

### 18.2. Bộ case số thập phân

- `0` và `0.00`.
- Số âm, kể cả `-0.0` nếu nguồn có floating-point.
- Giá trị nhỏ hơn 1 và số rất lớn.
- Số có nhiều chữ số thập phân.
- `1.20` và `1.2` để kiểm tra scale.
- Số theo exponent nếu contract cho phép.
- Số gần ngưỡng rounding.
- Chuỗi chứa grouping separator để xác nhận parser từ chối nếu format canonical.
- Dữ liệu vượt precision/scale đã công bố.
- Currency có quy tắc fraction digits khác nhau.

### 18.3. Bộ case text/encoding

- ASCII.
- Tiếng Việt có dấu.
- Emoji và ký tự ngoài Basic Multilingual Plane.
- Combining marks và Unicode NFC/NFD.
- Byte sequence UTF-8 malformed.
- BOM đầu file.
- LF và CRLF.
- Chuỗi có dấu nháy, dấu phẩy và newline trong CSV.
- JSON escapes.
- Leading/trailing whitespace có ý nghĩa.

### 18.4. Golden test và giá trị normalized

Với hợp đồng yêu cầu exact wire bytes, dùng **golden bytes** và checksum. Với hợp đồng chỉ yêu cầu timestamp instant, so sánh giá trị `Instant` đã parse. Với decimal, so sánh theo numeric value hoặc scale tùy schema. Với Unicode, so sánh exact code points nếu đó là contract; chỉ normalize khi có quy tắc.

Không ép mọi test thành so sánh chuỗi exact hoặc ngược lại ép mọi test bỏ qua khác biệt. Cách so sánh phải tương ứng với **ý nghĩa nghiệp vụ**.

## 19. Quy trình migration từng bước

~~~mermaid
flowchart TD
    A["Lập danh mục date/number/text fields"] --> B["Định nghĩa wire schema"]
    B --> C["Chụp dữ liệu thực tế của phiên bản cũ"]
    C --> D["Chạy producer và consumer trên JDK đích"]
    D --> E{"Representation và semantics có đổi?"}
    E -->|Không| F["Lưu bằng chứng tương thích"]
    E -->|Có| G["Xác định nguồn: JDK, tzdb, locale, charset, mapper"]
    G --> H["Sửa code hoặc version hóa contract"]
    H --> I["Kiểm thử dữ liệu cũ/mới hai chiều"]
    F --> I
    I --> J["Rollout theo thứ tự, theo dõi, rollback"]
~~~

### Bước 1: Tìm điểm chuyển đổi dữ liệu

Một số mẫu tìm kiếm trong dự án:

~~~bash
rg -n "DateTimeFormatter|SimpleDateFormat|Instant|OffsetDateTime|ZonedDateTime" src
rg -n "LocalDateTime|ZoneId|ZoneOffset|toEpochMilli|ofEpochSecond" src
rg -n "NumberFormat|DecimalFormat|BigDecimal|RoundingMode" src
rg -n "getBytes\\(|new String\\(|InputStreamReader|OutputStreamWriter" src
rg -n "Charset.defaultCharset|file.encoding|StandardCharsets" src
~~~

Các ví dụ dùng `rg` để hỗ trợ tìm kiếm. Cần xem thêm serializer, schema, database migration, integration code, job xuất CSV, shell scripts và framework configuration.

### Bước 2: Lập sổ hợp đồng trường dữ liệu

| Field | Java type | Wire type | Format/encoding | Precision | Phạm vi |
|---|---|---|---|---|---|
| `occurredAt` | `Instant` | JSON string | RFC 3339 UTC/offset | Millisecond | Event API |
| `businessDate` | `LocalDate` | JSON string | `uuuu-MM-dd` | Day | Accounting |
| `amount` | `BigDecimal` | Decimal string | Dấu chấm, không grouping | Scale theo schema | Payment |
| `currency` | `String` | JSON string | Currency code | Không áp dụng | Payment |
| `description` | `String` | UTF-8 JSON text | Unicode | Không áp dụng | Event API |

Bảng là một ví dụ contract; giá trị thực tế phải do hệ thống quyết định.

### Bước 3: Cố định baseline thực tế

Ghi:

- Artifact và checksum.
- JDK source version/vendor.
- JDK target version/vendor.
- OS/container image.
- Default locale, timezone và charset.
- tzdb/rules khi liên quan.
- Serializer/library/driver versions.
- Những dữ liệu byte thực tế đã được trao đổi.

Nếu chuyển cả JDK và dependency cùng lúc, nên tách test để biết thay đổi đến từ runtime hay từ framework.

### Bước 4: Kiểm tra dữ liệu từ phiên bản cũ

Giữ các payload và file cũ làm fixture:

- JSON events đã phát hành.
- CSV/Excel import files từ đối tác.
- Bản ghi DB ở các thời điểm khác nhau.
- Message trong queue có khả năng còn tồn đọng.
- Chứng từ hoặc file được ký số nếu signature dựa trên bytes.

Consumer mới phải được kiểm tra trên **dữ liệu lịch sử**, không chỉ dữ liệu do phiên bản mới tạo.

### Bước 5: Chạy test đa JDK và đa môi trường

Một ma trận thực tế:

| Runtime | Producer | Consumer | Mục tiêu |
|---|---|---|---|
| JDK cũ | Cũ | Cũ | Baseline |
| JDK mới | Mới | Mới | Functionality |
| JDK mới/cũ hỗn hợp | Mới | Cũ | Backward compatibility |
| JDK mới/cũ hỗn hợp | Cũ | Mới | Forward reading |
| Container production target | Mới | Đối tác | Network/file integration |

Cần test cả **byte representation** và **giá trị sau khi parse**, nhất là các trường monetary amount và timezone.

### Bước 6: Triển khai migration có khả năng rollback

Ví dụ nếu consumer cũ không đọc fractional seconds sáu chữ số:

1. Nâng consumer hoặc đưa vào parser chấp nhận format đã quy định.
2. Kiểm tra consumer mới đọc được payload cũ.
3. Kiểm tra producer vẫn phát format cũ trong giai đoạn hỗn hợp.
4. Sau khi các consumer đã hỗ trợ, mới mở rộng precision nếu cần.
5. Theo dõi lỗi parse và cho phép rollback đúng version contract.

Với charset file legacy, có thể cần job chuyển đổi dữ liệu có checksum và audit trail. Không thay đổi bytes lịch sử đã được ký số mà không có quy trình riêng.

## 20. Chẩn đoán lỗi thường gặp

| Triệu chứng | Nguyên nhân có thể | Hướng kiểm tra |
|---|---|---|
| `DateTimeParseException` | Pattern/offset/locale/precision không khớp | Payload nguyên văn, formatter và schema |
| Timestamp lệch vài giờ | Nhầm zone/offset hoặc dùng default timezone | `Instant`, `ZoneId` và nơi convert |
| Timestamp sai hàng nghìn năm | Nhầm epoch seconds với millis | Field units, parser conversion |
| Lịch bị dịch một giờ | DST/tzdb hoặc local time mơ hồ | Valid offsets, JDK rules |
| `ArithmeticException` khi chia decimal | Chưa định nghĩa rounding cho phép chia vô hạn | `BigDecimal.divide` và policy |
| Số tiền thay đổi khi qua JSON | Double/float làm mất precision | Mapper config và client numeric type |
| Số `1,234` parse khác dự kiến | Locale/grouping sai | Contract canonical vs UI parser |
| Ký tự tiếng Việt bị lỗi | Encode/decode khác charset | Raw bytes, `Content-Type`, UTF-8 |
| Có ký tự lạ đầu CSV header | UTF-8 BOM bị coi là text | Ba byte đầu file |
| JSON chữ ký số không hợp lệ | Whitespace/encoding/canonicalization khác | Bytes trước/sau serialize |
| CSV tách sai cột | Không quote/escape dấu phẩy/newline | CSV writer/parser |
| Text dài hơn giới hạn | Nhầm `String.length()` với số byte UTF-8 | Đo code points và encoded bytes |
| Snapshot khác sau nâng JDK | Locale/CLDR/tzdb/formatter thay đổi | Version runtime, locale và code points |

Chỉ từ thông điệp lỗi chưa thể khẳng định nguyên nhân cuối cùng; cần thu thập **raw payload/bytes**, artifact versions và config thực tế. Khi ghi log dữ liệu nghiệp vụ, phải ẩn thông tin cá nhân, mã bí mật và nội dung nhạy cảm theo quy định.

## 21. Checklist thiết kế và kiểm chứng

### Ngày giờ

- [ ] Mỗi field được xác định là instant, local date, local time hay lịch theo zone.
- [ ] Timestamp trên wire có offset/UTC khi contract yêu cầu một instant.
- [ ] Pattern và precision được công bố rõ.
- [ ] Không dùng `LocalDateTime` mà thiếu zone để đại diện event timestamp.
- [ ] Đã kiểm tra epoch units.
- [ ] Đã kiểm tra DST gap/overlap và zone rules.
- [ ] Đã kiểm tra JDBC/ORM/database conversion.
- [ ] Đã xử lý input ngày không hợp lệ bằng parse policy phù hợp.

### Số thập phân và tiền tệ

- [ ] Dữ liệu máy đọc không phụ thuộc `NumberFormat` mặc định.
- [ ] Decimal grammar, scale và precision đã được quy định.
- [ ] Dùng `BigDecimal` hoặc representation được duyệt khi cần chính xác.
- [ ] Có chính sách rounding riêng.
- [ ] Currency được truyền bằng identifier riêng.
- [ ] Đã kiểm tra client có dùng IEEE 754 double hay không.
- [ ] Đã kiểm tra exponent, trailing zeros và giá trị lớn.
- [ ] Không dùng ký hiệu tiền trong chuỗi hiển thị như ID giao dịch.

### Bộ mã và Unicode

- [ ] Charset được ghi tường minh ở ranh giới.
- [ ] Đã kiểm tra default charset khi nâng qua các phiên bản JDK.
- [ ] Đã xác định cách đọc file legacy.
- [ ] Đã kiểm tra BOM, newline và UTF-8 malformed input.
- [ ] Đã kiểm tra các chuỗi Unicode tiếng Việt, combining marks và emoji.
- [ ] Đã phân biệt số ký tự với byte length.
- [ ] Đã xác định có chuẩn hóa Unicode không và ở bước nào.
- [ ] Đã kiểm tra escaping của JSON/CSV/XML và raw transport bytes.

### Migration

- [ ] Đã ghi hợp đồng cho từng field quan trọng.
- [ ] Đã lưu baseline từ JDK/producer/consumer cũ.
- [ ] Đã chạy test trên JDK và container mục tiêu.
- [ ] Đã test consumer cũ với producer mới và chiều ngược lại.
- [ ] Đã test dữ liệu lịch sử và payload mới.
- [ ] Đã xác định thay đổi breaking và chiến lược version hóa.
- [ ] Đã có monitoring lỗi parse, sai số, lệch giờ và encoding.
- [ ] Đã có rollback khi thay đổi format ảnh hưởng giao dịch.

## Kết luận

Trong trao đổi dữ liệu, **ngày giờ, số thập phân và bộ mã** là những phần của hợp đồng giữa các hệ thống. Java cung cấp `java.time` để mô hình hóa thời gian, `BigDecimal` cho decimal chính xác, cùng `Charset`/`StandardCharsets` để kiểm soát text-to-bytes. Nhưng các API đó chỉ tạo ra tính tương thích khi ứng dụng **quy định rõ representation, precision, offset/zone, rounding và charset**.

Khi nâng JDK hoặc dependency, hãy tránh default locale/timezone/charset ở ranh giới giao tiếp, không dùng chuỗi trình bày như dữ liệu máy, và không để parser tự đoán các trường mơ hồ. Thu thập dữ liệu cũ, kiểm tra raw bytes và giá trị đã parse qua cả hai chiều producer–consumer, rồi triển khai thay đổi theo version contract. Đó là cách giữ **tính chính xác và tương thích dữ liệu** ngay cả khi nền tảng Java tiếp tục thay đổi.

