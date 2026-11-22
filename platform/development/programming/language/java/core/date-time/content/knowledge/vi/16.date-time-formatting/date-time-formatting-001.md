# `DateTimeFormatter` và vai trò tách dữ liệu khỏi cách hiển thị

Trong Java, **dữ liệu ngày giờ** và **chuỗi ngày giờ được hiển thị** là hai việc khác nhau. `LocalDate`, `LocalDateTime`, `OffsetDateTime`, `ZonedDateTime` và `Instant` biểu diễn các giá trị thời gian với ý nghĩa cụ thể; `DateTimeFormatter` dùng để **định dạng những giá trị ấy thành chuỗi** hoặc **phân tích chuỗi thành giá trị có kiểu**.

Ví dụ, một mốc sự kiện chính xác:

`2026-01-15T00:30:45.123456789Z`

có thể hiển thị cho người xem tại Việt Nam thành:

`15/01/2026 07:30`

Chuỗi thứ hai thân thiện với giao diện, nhưng nó **không còn chứa giây, nano giây, offset hay tên vùng múi giờ**. Nếu lấy chuỗi hiển thị làm dữ liệu gốc và parse ngược, chương trình không thể tự biết thông tin đã bị lược bỏ.

**Nguyên tắc chính:** giữ kiểu dữ liệu có ý nghĩa đầy đủ cho nghiệp vụ; chỉ định dạng ở ranh giới hiển thị; parse đầu vào với mẫu và quy tắc rõ ràng.

## 1. Formatter làm gì và không làm gì?

`DateTimeFormatter` là lớp bất biến, an toàn khi dùng đồng thời, dùng với các kiểu `java.time` để định dạng hoặc parse. Hai thao tác cơ bản:

~~~java
DateTimeFormatter formatter =
        DateTimeFormatter.ofPattern("dd/MM/uuuu HH:mm");

String label = formatter.format(localDateTime);
LocalDateTime parsed = LocalDateTime.parse(label, formatter);
~~~

Đây là ví dụ minh họa trong method, với `localDateTime` là biến đã có kiểu `LocalDateTime`.

- **Format:** lấy thông tin từ giá trị thời gian và tạo ra một `String`; không sửa đối tượng nguồn.
- **Parse:** đọc chuỗi theo formatter để tạo giá trị thời gian; nếu dữ liệu không hợp lệ hoặc không đủ trường theo kiểu đích, có thể ném `DateTimeParseException`.
- **Formatter không tự bổ sung ngữ cảnh bị thiếu:** mẫu `dd/MM/uuuu HH:mm` không ghi giây, nano giây hoặc zone thì chuỗi kết quả cũng không bảo tồn các trường đó.
- **Formatter không quyết định thay nghiệp vụ:** nó không tự biết chuỗi là ngày hóa đơn, giờ hẹn tại Paris hay thời điểm thanh toán toàn cầu. Chọn kiểu thời gian và zone trước khi format.

Ví dụ:

| Mục tiêu | Kiểu dữ liệu phù hợp | Formatter/biểu diễn |
| --- | --- | --- |
| Ngày sinh | `LocalDate` | `DateTimeFormatter.ISO_LOCAL_DATE` hoặc mẫu ngày đã thống nhất |
| Giờ mở cửa | `LocalTime` | Mẫu giờ địa phương như `HH:mm` |
| Giờ hẹn chưa gắn vùng | `LocalDateTime` | `ISO_LOCAL_DATE_TIME` |
| Thời điểm có offset | `OffsetDateTime` | `ISO_OFFSET_DATE_TIME` |
| Lịch hẹn ở một vùng có quy tắc DST | `ZonedDateTime` | `ISO_ZONED_DATE_TIME` hoặc mẫu chứa zone ID |
| Sự kiện tuyệt đối | `Instant` | `ISO_INSTANT` hoặc `Instant.toString()` |

Đừng chọn mẫu chỉ theo hình thức mong muốn. Trước tiên hãy tự hỏi chuỗi sẽ phục vụ **đọc trên giao diện**, **giao tiếp giữa hệ thống**, hay **lưu trữ để phục hồi chính xác**. Mỗi mục tiêu cần độ đầy đủ thông tin khác nhau.

## 2. Mẫu định dạng: ý nghĩa các chữ cái rất quan trọng

`DateTimeFormatter.ofPattern(...)` cho phép định nghĩa mẫu. Các ký hiệu phổ biến:

| Ký hiệu | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| `u` | Năm theo hệ lịch ISO/proleptic year | `uuuu` → `2026` |
| `y` | Năm trong era | `yyyy` → `2026` ở CE; semantics khác `u` |
| `Y` | Năm theo tuần (week-based year) | Có thể khác năm lịch quanh đầu/cuối năm |
| `M` | Tháng; `MM` thường thêm số 0 | `01` |
| `d` | Ngày trong tháng | `15` |
| `D` | Ngày trong năm | Ví dụ ngày thứ 15 |
| `E` | Tên ngày trong tuần | `Thu` hoặc tên địa phương |
| `H` | Giờ 24 tiếng (0–23) | `07` |
| `h` | Giờ 12 tiếng (1–12) | Cần phân biệt AM/PM |
| `m` | Phút | `30` |
| `s` | Giây | `45` |
| `S` | Phần thập phân giây; số chữ cái chỉ số chữ số được in | `SSS` cho mili giây hiển thị |
| `n` | Nano giây trong giây | Giá trị số nano giây |
| `X`, `x`, `Z` | Dạng offset UTC | Tùy pattern |
| `V` | ID vùng múi giờ; thường dùng `VV` | `Asia/Ho_Chi_Minh` |
| `z` | Tên zone dạng văn bản | Có thể phụ thuộc locale và quy tắc |
| `a` | AM/PM marker | `AM`/`PM` tùy locale |

### Vì sao nên ưu tiên `uuuu` cho ngày lịch?

Trong các mẫu ngày ISO, **`uuuu-MM-dd`** thường là lựa chọn rõ ràng cho ngày lịch; `yyyy` biểu diễn year-of-era và có thể khác ý nghĩa trong các trường hợp era đặc biệt. Đặc biệt, không dùng `YYYY-MM-dd` thay `uuuu-MM-dd` cho ngày lịch thông thường: `Y` là **week-based year**, không phải năm lịch. Gần đầu tháng Một, `YYYY` có thể chỉ năm tuần liền trước.

Ví dụ Java:

~~~java
LocalDate date = LocalDate.of(2021, 1, 1);

System.out.println(date.format(
        DateTimeFormatter.ofPattern("uuuu-MM-dd")));
// 2021-01-01

System.out.println(date.format(
        DateTimeFormatter.ofPattern("YYYY-'W'ww-e")));
// Năm tuần có thể vẫn là năm 2020 tùy quy tắc week fields/locale.
~~~

Mẫu `YYYY-'W'ww-e` diễn tả **năm tuần**, tuần và ngày trong tuần. Quy tắc tuần phụ thuộc lịch tuần/locale của formatter; đừng sử dụng nó nếu ý định chỉ là ngày lịch ISO.

### Cố định locale khi dùng tên tháng/ngày

Nếu hiển thị tháng hay thứ bằng chữ, tên có thể phụ thuộc `Locale`. Dùng locale rõ ràng nếu chuỗi cần ổn định:

~~~java
DateTimeFormatter vietnamese =
        DateTimeFormatter.ofPattern(
                "EEEE, dd MMMM uuuu",
                Locale.forLanguageTag("vi-VN"));
~~~

Đây là formatter dùng cho hiển thị tiếng Việt. Locale ảnh hưởng tên tháng/ngày và một số kiểu văn bản; nó không thay thế `ZoneId`, không tự gắn offset cho `LocalDateTime` và không biến chuỗi ngày giờ thành một instant.

## 3. Những formatter ISO dựng sẵn đáng ưu tiên

Java đã cung cấp nhiều hằng formatter theo ISO để tránh phải tự tạo mẫu:

| Formatter | Kiểu thường dùng | Ví dụ |
| --- | --- | --- |
| `ISO_LOCAL_DATE` | `LocalDate` | `2026-01-15` |
| `ISO_LOCAL_TIME` | `LocalTime` | `07:30:45.123` |
| `ISO_LOCAL_DATE_TIME` | `LocalDateTime` | `2026-01-15T07:30:45` |
| `ISO_OFFSET_DATE_TIME` | `OffsetDateTime` | `2026-01-15T07:30:45+07:00` |
| `ISO_ZONED_DATE_TIME` | `ZonedDateTime` | Có offset và zone ID khi được biểu diễn |
| `ISO_INSTANT` | `Instant` | `2026-01-15T00:30:45Z` |

Ví dụ:

~~~java
Instant event = Instant.parse("2026-01-15T00:30:45.123456789Z");
ZonedDateTime local =
        event.atZone(ZoneId.of("Asia/Ho_Chi_Minh"));

System.out.println(DateTimeFormatter.ISO_INSTANT.format(event));
System.out.println(DateTimeFormatter.ISO_LOCAL_DATE_TIME.format(
        local.toLocalDateTime()));
System.out.println(DateTimeFormatter.ISO_OFFSET_DATE_TIME.format(
        local.toOffsetDateTime()));
System.out.println(DateTimeFormatter.ISO_ZONED_DATE_TIME.format(local));
~~~

Kết quả:

~~~text
2026-01-15T00:30:45.123456789Z
2026-01-15T07:30:45.123456789
2026-01-15T07:30:45.123456789+07:00
2026-01-15T07:30:45.123456789+07:00[Asia/Ho_Chi_Minh]
~~~

Chuỗi local date-time không bao gồm offset hay zone ID. Chuỗi offset date-time giữ offset nhưng không nhất thiết giữ tên vùng địa lý. Chuỗi zoned có thể ghi vùng. Khi trao đổi **mốc sự kiện** đơn thuần, `ISO_INSTANT` thường rõ ràng; khi trao đổi **lịch hẹn theo một địa điểm**, cần hợp đồng dữ liệu đủ để bảo toàn zone và quy tắc giải quyết DST.

## 4. Formatter có làm mất giây, nano giây hoặc zone không?

**Có, nếu mẫu không ghi các thành phần đó.** Format một `ZonedDateTime` bằng mẫu chỉ có ngày giờ đến phút không khiến đối tượng nguồn bị thay đổi; chỉ có chuỗi kết quả thiếu thông tin.

~~~java
Instant event =
        Instant.parse("2026-01-15T00:30:45.123456789Z");
ZonedDateTime local =
        event.atZone(ZoneId.of("Asia/Ho_Chi_Minh"));

DateTimeFormatter display =
        DateTimeFormatter.ofPattern("dd/MM/uuuu HH:mm");
String label = display.format(local);
// "15/01/2026 07:30"

LocalDateTime parsed = LocalDateTime.parse(label, display);
// 2026-01-15T07:30; giây/nano mặc định bằng 0.
~~~

Chuỗi `label` không ghi giây, phần nano giây, offset và zone ID. Sau parse, `parsed` là `LocalDateTime` chứ không phải `ZonedDateTime`; nó cũng không tự mang giá trị giây .45 hay .123456789 trước đó.

Nếu **chỉ là giao diện**, điều này thường hoàn toàn ổn. Nếu dùng để lưu thời điểm giao dịch và sau này tính thứ tự hoặc khoảng cách, không dùng nhãn hiển thị làm dữ liệu chuẩn. Hãy giữ `Instant event` và chỉ format khi cần hiển thị.

### Round-trip lossless phải đáp ứng điều gì?

Một chuỗi có thể phục hồi chính xác kiểu/ý nghĩa nguồn nếu giữ **đủ các trường cần thiết** và dùng parser tương ứng. Ví dụ:

- `Instant` ↔ `ISO_INSTANT`: có UTC và phần nano giây khi tồn tại.
- `OffsetDateTime` ↔ `ISO_OFFSET_DATE_TIME`: giữ local date-time và offset.
- `ZonedDateTime` ↔ `ISO_ZONED_DATE_TIME`: biểu diễn có offset và zone ID; phải lưu ý phiên bản quy tắc vùng ở hệ thống parse khi yêu cầu tái hiện lịch sử.
- `LocalDateTime` ↔ `ISO_LOCAL_DATE_TIME`: giữ trường local date-time, nhưng **không có zone/offset để suy ra instant**.

Ngay cả một phép format/parse ISO đầy đủ cũng không tự giải quyết các khác biệt về hợp đồng dữ liệu, precision của database, hay quy tắc zone được cập nhật sau này.

## 5. Parse đầu vào và giải quyết lỗi ngày không hợp lệ

Format thường xuất phát từ dữ liệu đã có kiểu. Parse lại là ranh giới tin cậy quan trọng: đầu vào có thể sai mẫu, ngày không tồn tại, giờ thiếu AM/PM hoặc mang offset không đúng.

~~~java
DateTimeFormatter strictDate =
        DateTimeFormatter.ofPattern("dd/MM/uuuu")
                .withResolverStyle(ResolverStyle.STRICT);

LocalDate leapDay = LocalDate.parse("29/02/2024", strictDate);
// Hợp lệ

LocalDate.parse("29/02/2025", strictDate);
// Ném DateTimeParseException vì năm 2025 không nhuận.
~~~

`ResolverStyle.STRICT` yêu cầu ngày tháng giải quyết thành ngày hợp lệ. Dùng `uuuu` thay vì `yyyy` trong mẫu nghiêm ngặt giúp năm được hiểu trực tiếp; với `yyyy`, year-of-era trong lịch ISO có thể cần era để giải quyết nghiêm ngặt đầy đủ.

Có ba resolver style:

| Kiểu | Ý nghĩa | Khi dùng |
| --- | --- | --- |
| `STRICT` | Đòi ngày giờ hợp lệ theo quy tắc trường | Input nghiệp vụ, API cần kiểm tra chặt |
| `SMART` | Giải quyết một số tổ hợp theo quy tắc thông minh của formatter | Khi muốn hành vi tiện dụng được xác định |
| `LENIENT` | Chấp nhận giá trị rộng hơn và chuẩn hóa khi có thể | Chỉ dùng nếu chuẩn hóa đầu vào thực sự là ý định |

Đừng giả định `SMART` và `LENIENT` luôn từ chối hay điều chỉnh theo cùng cách. Nếu ngày/giờ không hợp lệ phải được trả lỗi, cấu hình `STRICT` và kiểm thử trường hợp biên.

### Parse chuỗi có 12 giờ

Mẫu `hh:mm` dùng đồng hồ 12 giờ, nên cần AM/PM hoặc quy tắc tương ứng. Nếu input là `07:30 PM`, định nghĩa mẫu như `hh:mm a` với locale đúng. Nếu nghiệp vụ dùng đồng hồ 24 giờ, `HH:mm` tránh mơ hồ AM/PM.

Không parse ngày tự do như `01/02/2026` khi chưa biết quy ước; đó có thể là ngày 1 tháng 2 hoặc 2 tháng 1. Định dạng UI và hợp đồng API phải được thống nhất rõ.

## 6. `Locale`, `ZoneId` và `Chronology` giải quyết những việc khác nhau

Ba thứ này không nên đánh đồng:

- **`Locale`** ảnh hưởng ngôn ngữ/tên tháng, tên thứ, dấu phân cách hoặc một số quy ước định dạng văn bản.
- **`ZoneId`** xác định vùng múi giờ để chuyển instant thành ngày giờ địa phương theo `ZoneRules`, chẳng hạn `Asia/Ho_Chi_Minh` hoặc `Europe/Paris`.
- **`Chronology`** mô tả hệ lịch; các kiểu `LocalDate` tiêu chuẩn dùng lịch ISO proleptic Gregorian.

Một `DateTimeFormatter` có thể được cấu hình để định dạng/phân tích với locale, zone hoặc chronology; nhưng ý nghĩa của chúng khác nhau. Cấu hình locale tiếng Việt không có nghĩa timestamp tự được chuyển sang giờ Việt Nam. Và zone `Asia/Ho_Chi_Minh` không có nghĩa tên tháng sẽ tự hiển thị bằng tiếng Việt nếu formatter không dùng locale tương ứng.

Ví dụ chuyển một instant trước khi format:

~~~java
Instant event = Instant.parse("2026-01-15T00:30:45Z");
DateTimeFormatter formatter =
        DateTimeFormatter.ofPattern(
                "EEEE, dd MMMM uuuu HH:mm XXX",
                Locale.forLanguageTag("vi-VN"));

String label = event.atZone(
        ZoneId.of("Asia/Ho_Chi_Minh")).format(formatter);
~~~

Cách làm rõ ràng là **chuyển instant sang zone đích trước**, sau đó dùng locale và formatter cho giao diện. Nếu chỉ gọi `event.atZone(...)` rồi bỏ kết quả, hoặc chỉ đổi locale mà không đổi zone, kết quả sẽ không như mong đợi.

## 7. Offset và zone trong mẫu formatter

Một mẫu hiển thị có thể cần ghi cả offset và zone ID để tránh nhầm:

~~~java
DateTimeFormatter full =
        DateTimeFormatter.ofPattern(
                "uuuu-MM-dd HH:mm XXX '['VV']'");

ZonedDateTime value = Instant
        .parse("2026-01-15T00:30:45Z")
        .atZone(ZoneId.of("Asia/Ho_Chi_Minh"));

System.out.println(full.format(value));
// 2026-01-15 07:30 +07:00 [Asia/Ho_Chi_Minh]
~~~

Ở đây `XXX` in offset kiểu `+07:00`, còn `VV` in ID vùng. Đây là thông tin hữu ích cho log kỹ thuật, hỗ trợ vận hành hoặc giao diện cần hiển thị ngữ cảnh múi giờ. Nếu người dùng chỉ cần đọc giờ ngắn gọn, một nhãn không có zone có thể hợp lý, nhưng **không thay nhãn đó vào trường timestamp gốc**.

Đối với `Instant`, một formatter có thể được gắn zone thông qua `withZone(zone)` để thay đổi cách hiển thị khi format. Điều đó **không thay đổi Instant nguồn**:

~~~java
DateTimeFormatter localDisplay =
        DateTimeFormatter.ofPattern("uuuu-MM-dd HH:mm XXX")
                .withZone(ZoneId.of("Asia/Ho_Chi_Minh"));

String localLabel = localDisplay.format(
        Instant.parse("2026-01-15T00:30:45Z"));
// 2026-01-15 07:30 +07:00
~~~

Mẫu có zone giúp định dạng `Instant`, nhưng đừng nghĩ rằng parse chính chuỗi thiếu zone sẽ tự phục hồi zone gốc. Một chuỗi chỉ gồm `2026-01-15 07:30 +07:00` có offset nhưng vẫn chưa cho biết region ID là gì.

## 8. Chương trình Java 17+ chạy được: tách giá trị khỏi nhãn hiển thị

Tạo tệp **`FormatterSeparationDemo.java`**:

~~~java
import java.time.Instant;
import java.time.LocalDate;
import java.time.LocalDateTime;
import java.time.ZoneId;
import java.time.ZonedDateTime;
import java.time.format.DateTimeFormatter;
import java.time.format.DateTimeParseException;
import java.time.format.ResolverStyle;
import java.util.Locale;

public class FormatterSeparationDemo {
    public static void main(String[] args) {
        Instant event =
                Instant.parse("2026-01-15T00:30:45.123456789Z");
        ZoneId vietnam = ZoneId.of("Asia/Ho_Chi_Minh");
        ZonedDateTime local = event.atZone(vietnam);

        DateTimeFormatter display = DateTimeFormatter.ofPattern(
                "dd/MM/uuuu HH:mm", Locale.forLanguageTag("vi-VN"));
        String label = display.format(local);

        System.out.println("instant = " + event);
        System.out.println("local = " + local);
        System.out.println("label = " + label);

        LocalDateTime parsed = LocalDateTime.parse(label, display);
        System.out.println("parsed = " + parsed);
        System.out.println("secondsLost = "
                + (parsed.getSecond() != local.getSecond()
                    || parsed.getNano() != local.getNano()));

        DateTimeFormatter strict = DateTimeFormatter
                .ofPattern("dd/MM/uuuu")
                .withResolverStyle(ResolverStyle.STRICT);

        System.out.println("validDate = "
                + LocalDate.parse("29/02/2024", strict));
        try {
            LocalDate.parse("29/02/2025", strict);
        } catch (DateTimeParseException ex) {
            System.out.println("invalidDate = DateTimeParseException");
        }

        System.out.println("isoInstant = "
                + DateTimeFormatter.ISO_INSTANT.format(event));
        System.out.println("localIso = "
                + DateTimeFormatter.ISO_LOCAL_DATE_TIME.format(
                    local.toLocalDateTime()));
        System.out.println("offsetIso = "
                + DateTimeFormatter.ISO_OFFSET_DATE_TIME.format(
                    local.toOffsetDateTime()));
        System.out.println("zonedIso = "
                + DateTimeFormatter.ISO_ZONED_DATE_TIME.format(local));

        DateTimeFormatter withZone = DateTimeFormatter.ofPattern(
                "uuuu-MM-dd HH:mm XXX '['VV']'");
        System.out.println("withZone = " + withZone.format(local));
        System.out.println("yearWeek = "
                + LocalDate.of(2021, 1, 1).format(
                    DateTimeFormatter.ofPattern("YYYY-'W'ww-e")));
        System.out.println("calendarYear = "
                + LocalDate.of(2021, 1, 1).format(
                    DateTimeFormatter.ofPattern("uuuu-MM-dd")));
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac FormatterSeparationDemo.java
java FormatterSeparationDemo
~~~

Đầu ra trong runtime Java đã kiểm tra:

~~~text
instant = 2026-01-15T00:30:45.123456789Z
local = 2026-01-15T07:30:45.123456789+07:00[Asia/Ho_Chi_Minh]
label = 15/01/2026 07:30
parsed = 2026-01-15T07:30
secondsLost = true
validDate = 2024-02-29
invalidDate = DateTimeParseException
isoInstant = 2026-01-15T00:30:45.123456789Z
localIso = 2026-01-15T07:30:45.123456789
offsetIso = 2026-01-15T07:30:45.123456789+07:00
zonedIso = 2026-01-15T07:30:45.123456789+07:00[Asia/Ho_Chi_Minh]
withZone = 2026-01-15 07:30 +07:00 [Asia/Ho_Chi_Minh]
yearWeek = 2021-W01-6
calendarYear = 2021-01-01
~~~

Kết quả cho thấy `label` tiện đọc nhưng parse ngược không thể phục hồi giây/nano giây; formatter ISO giữ trường ngày giờ nhiều hơn, và `ISO_INSTANT` giữ mốc UTC. Đầu ra `yearWeek` phụ thuộc quy tắc week fields/locale của runtime; hãy dùng `YYYY` cho năm tuần và `uuuu` cho năm lịch.

## 9. Cách thiết kế ranh giới dữ liệu/hiển thị

Một cách tổ chức dễ bảo trì:

1. **Trong domain/service:** truyền `Instant` cho sự kiện toàn cầu, `LocalDate` cho ngày lịch, hoặc `ZonedDateTime` khi cần giữ biểu diễn vùng đã giải quyết. Không dùng chuỗi giao diện làm kiểu nội bộ mặc định.
2. **Ở ranh giới API:** dùng dạng chuẩn đã công bố. Timestamp nên có `Z` hoặc offset; ngày lịch nên có mẫu ISO ngày. Với lịch địa phương trong tương lai, giữ zone ID và quy tắc lựa chọn DST khi cần.
3. **Ở giao diện:** chọn `DateTimeFormatter`, locale và zone theo người xem. Có thể bỏ giây hoặc zone để dễ đọc, miễn đó là nhãn hiển thị.
4. **Khi nhận input:** dùng formatter cụ thể, resolver phù hợp và kiểm tra lỗi. Đừng nhận một chuỗi mơ hồ rồi để cấu hình mặc định tự diễn giải.
5. **Khi lưu dữ liệu:** xác nhận database/driver có giữ offset và precision đến mức nào; formatter chính xác không bảo đảm bước lưu sau đó không cắt dữ liệu.

### Các ví dụ hợp đồng dữ liệu

Ngày hóa đơn là ngày lịch:

~~~json
{
  "invoiceDate": "2026-01-15"
}
~~~

Thời điểm sự kiện tuyệt đối:

~~~json
{
  "occurredAt": "2026-01-15T00:30:45.123456789Z"
}
~~~

Lịch địa phương cần vùng để giải nghĩa:

~~~json
{
  "scheduledLocalDateTime": "2024-10-27T02:30:00",
  "zoneId": "Europe/Paris",
  "selectedOffset": "+01:00"
}
~~~

Ba trường hợp có **ý nghĩa khác nhau**; không ép mọi thứ vào cùng một mẫu chuỗi chỉ vì muốn dùng chung một formatter. Ngày lịch không cần gắn `Z`; timestamp tuyệt đối cần offset hoặc UTC; lịch địa phương cần zone và chính sách nếu DST khiến giờ bị thiếu hoặc lặp.

## 10. Lỗi thường gặp khi sử dụng formatter

| Lỗi | Vì sao sai? | Cách xử lý |
| --- | --- | --- |
| Dùng `YYYY-MM-dd` cho ngày lịch | `Y` là năm tuần, có thể khác năm lịch | Dùng `uuuu-MM-dd` cho ISO calendar date |
| Dùng `hh:mm` mà quên AM/PM | Giờ 12 tiếng không phân biệt sáng/chiều | Dùng `HH:mm` hoặc thêm `a` với locale thích hợp |
| Format đến phút rồi parse thành timestamp | Đã mất giây/nano giây và zone/offset nếu không có trong chuỗi | Giữ giá trị nguồn, format chỉ để hiển thị |
| Dùng `LocalDateTime` cho sự kiện cần instant | Không có offset/zone nên chưa xác định UTC | Dùng `Instant`/`OffsetDateTime`, hoặc local date-time cộng zone và chính sách |
| Tin rằng locale sẽ chuyển múi giờ | Locale điều chỉnh ngôn ngữ hiển thị, không thay zone | Chọn `ZoneId` riêng |
| Tin rằng formatter luôn từ chối ngày sai | Resolver style có thể SMART/LENIENT | Dùng `STRICT` khi cần kiểm tra chặt |
| Dùng `DateTimeFormatter` để sửa nguồn | Format trả chuỗi; không sửa đối tượng thời gian | Giữ domain value và nhận/parse kết quả theo kiểu |
| Coi `+07:00` là ID vùng | Offset không chứa quy tắc địa lý | Dùng `ZoneId` khi cần quy tắc vùng |
| Nghĩ chuỗi ISO local có thể phục hồi zone gốc | Local ISO không chứa zone ID | Lưu zone riêng hoặc dùng biểu diễn có thông tin phù hợp |

## 11. Checklist trước khi format hoặc parse

1. Mục tiêu là **hiển thị** hay **trao đổi/lưu trữ chính xác**?
2. Kiểu dữ liệu nguồn có đủ thông tin cho mục đích đó chưa?
3. Pattern đã ghi đủ trường phải bảo toàn chưa — ngày, giờ, giây, nano giây, offset và zone ID?
4. Có dùng đúng `uuuu` cho năm lịch và `YYYY` chỉ khi thực sự muốn năm tuần không?
5. Locale, zone và hệ lịch có được chọn tường minh khi cần không?
6. Parse có dùng mẫu đúng với input, có chính sách nghiêm ngặt cho ngày sai và giờ 12 tiếng không?
7. Sau round-trip, đã kiểm tra đúng thuộc tính cần giữ (giá trị local, instant, zone hoặc precision) thay vì chỉ so sánh chuỗi chưa?
8. Database hoặc API downstream có thể hạ precision hay bỏ offset/zone không?
9. Chuỗi hiển thị thiếu trường có bị dùng nhầm làm dữ liệu nguồn không?

### Tự kiểm tra

- `DateTimeFormatter` có sửa đối tượng `ZonedDateTime` nguồn không? **Không**; nó tạo chuỗi từ giá trị đó.
- Nếu format `07:30:45.123456789+07:00` bằng mẫu `HH:mm`, có phục hồi đầy đủ instant từ chuỗi đó không? **Không**; thiếu giây, nano, ngày và offset.
- Khi nào dùng `ISO_INSTANT`? **Khi trao đổi một instant UTC**, nhất là log và timestamp sự kiện.
- Khi nào dùng `ISO_LOCAL_DATE`? **Khi trao đổi ngày lịch** mà không có ý nghĩa giờ hay zone.
- `Locale.forLanguageTag("vi-VN")` có tự đổi UTC sang giờ Việt Nam không? **Không**; phải chuyển giá trị sang `Asia/Ho_Chi_Minh`.
- Vì sao `ResolverStyle.STRICT` hữu ích? **Để từ chối ngày lịch không hợp lệ thay vì tự điều chỉnh theo resolver khác.**
- `Y` và `u` khác gì? **`Y` là năm theo tuần; `u` là năm lịch/proleptic year.**

**Ghi nhớ:** `DateTimeFormatter` là cầu nối giữa **giá trị thời gian có kiểu** và **chuỗi**. Hãy chọn kiểu temporal đúng trước, xác định zone/locale riêng, sử dụng mẫu rõ nghĩa và kiểm soát parse. Chuỗi ngắn gọn có thể phù hợp cho giao diện, nhưng dữ liệu chuẩn phải giữ những trường cần thiết để phục hồi ngày giờ, mốc UTC và độ chính xác theo hợp đồng nghiệp vụ.