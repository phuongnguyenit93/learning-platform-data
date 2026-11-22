# Tạo mẫu định dạng ngày giờ bằng `DateTimeFormatter.ofPattern()`

Một giá trị ngày giờ có thể được hiển thị thành nhiều kiểu chuỗi tùy mục đích: `2026-10-24T09:05:07` cho dữ liệu máy, `24/10/2026 09:05` cho biểu mẫu tiếng Việt, hoặc `Sat, 24 Oct 2026` cho giao diện tiếng Anh. Giá trị thời gian không đổi; **pattern** quyết định cách nó được biểu diễn.

Trong Java, `DateTimeFormatter.ofPattern(pattern)` tạo formatter từ chuỗi pattern. Bài học này giải thích cú pháp pattern, ký hiệu ngày và giờ, phần lẻ giây, Locale, offset và zone, cách parse ngược chuỗi và những lỗi thường gây sai dữ liệu. Ví dụ dùng Java 17+ và `java.time`.

## 1. Định dạng là chuyển giá trị thành chuỗi

~~~java
LocalDateTime value = LocalDateTime.of(2026, 10, 24, 9, 5, 7);
DateTimeFormatter fmt =
        DateTimeFormatter.ofPattern("dd/MM/uuuu HH:mm:ss");
String result = value.format(fmt);
System.out.println(result); // 24/10/2026 09:05:07
~~~

Pattern mô tả thứ tự và kiểu hiển thị của từng trường, chứ không phải một ngày giờ mẫu. Chữ cái Latin thường là ký hiệu định dạng; dấu gạch, dấu hai chấm, dấu cách và dấu phẩy thường được in nguyên văn. Nếu muốn in một chữ vốn là ký hiệu pattern, hãy đặt nó trong dấu nháy đơn, chẳng hạn `'T'`.

`DateTimeFormatter` bất biến và an toàn khi dùng từ nhiều thread. Khi pattern và Locale cố định, có thể tạo formatter một lần rồi tái sử dụng.

## 2. Pattern ngày, tháng và năm

| Ký hiệu | Ý nghĩa | Ví dụ hoặc lưu ý |
| --- | --- | --- |
| `u` / `uuuu` | Năm theo lịch ISO mở rộng | Thường dùng `uuuu-MM-dd` cho dữ liệu máy |
| `y` / `yyyy` | Năm trong era | Khác `u` ở một số trường hợp lịch đặc biệt |
| `Y` / `YYYY` | Năm theo tuần (week-based-year) | Không đồng nghĩa năm lịch |
| `M` / `MM` | Tháng dạng số | `M` có thể là 1; `MM` là 01 |
| `MMM` | Tên tháng ngắn | `Oct` với Locale tiếng Anh |
| `MMMM` | Tên tháng đầy đủ | `October` với Locale tiếng Anh |
| `L` | Tháng dạng độc lập | Hữu ích trong một số ngôn ngữ |
| `d` / `dd` | Ngày trong tháng | `4` hoặc `04` |
| `D` / `DDD` | Ngày thứ bao nhiêu trong năm | 1–365 hoặc 1–366 |
| `E` / `EEE` | Tên thứ dạng ngắn | Ví dụ `Sat` |
| `EEEE` | Tên thứ đầy đủ | Ví dụ `Saturday` |
| `e` / `c` | Thứ theo quy ước Locale | Cách hiển thị/phân giải phụ thuộc Locale |

Các ký hiệu chữ hoa/thường không thể hoán đổi tùy tiện:

- `MM` là **tháng**, còn `mm` là **phút**.
- `dd` là ngày trong tháng, còn `DD` là ngày thứ mấy trong năm.
- `uuuu` là năm theo lịch ISO mở rộng; `yyyy` là năm trong era.
- `YYYY` là năm theo tuần. Gần đầu hoặc cuối năm, năm theo tuần có thể khác năm lịch. Đừng dùng `YYYY-MM-dd` cho ngày lịch thông thường nếu mục tiêu thực sự là năm-tháng-ngày.

Ví dụ pattern:

~~~java
LocalDate date = LocalDate.of(2026, 10, 24);
System.out.println(date.format(
        DateTimeFormatter.ofPattern("uuuu-MM-dd"))); // 2026-10-24
System.out.println(date.format(
        DateTimeFormatter.ofPattern("dd/MM/uuuu"))); // 24/10/2026
~~~

## 3. Giờ, phút, giây và phần lẻ

| Ký hiệu | Ý nghĩa | Ghi chú |
| --- | --- | --- |
| `H` / `HH` | Giờ theo hệ 0–23 | `HH` thường đệm số 0 |
| `h` / `hh` | Giờ trong chu kỳ 1–12 | Nên kèm `a` để biết AM/PM |
| `k` | Giờ theo thang 1–24 | Có quy ước riêng cho nửa đêm |
| `K` | Giờ trong chu kỳ 0–11 | Một mình không phân biệt sáng/chiều |
| `m` / `mm` | Phút | Chữ thường |
| `s` / `ss` | Giây | Chữ thường |
| `S` | Chữ số của phần lẻ giây | `SSS` thường hiển thị mili giây |
| `n` | Nano giây trong giây, dạng số | Không giống ký hiệu phần lẻ `S` |
| `N` | Nano giây kể từ đầu ngày | Bộ đếm trong ngày |

~~~java
LocalTime time = LocalTime.of(9, 5, 7, 123_000_000);
System.out.println(time.format(
        DateTimeFormatter.ofPattern("HH:mm:ss")));
System.out.println(time.format(
        DateTimeFormatter.ofPattern("HH:mm:ss.SSS")));
System.out.println(time.format(
        DateTimeFormatter.ofPattern("hh:mm:ss a", Locale.US)));
~~~

Kết quả:

~~~text
09:05:07
09:05:07.123
09:05:07 AM
~~~

`S` là phần lẻ của giây, còn `s` là giây nguyên. Với `HH`, giờ chạy từ 00 đến 23; với `hh`, giờ chạy theo chu kỳ 12 tiếng, vì vậy nên dùng thêm `a` nếu cần phân biệt sáng và chiều. Ví dụ `hh:mm` một mình có thể không phân biệt 09:00 và 21:00.

Số chữ `S` quy định lượng chữ số phần giây được xuất ra. `SSS` chỉ hiển thị ba chữ số; nếu giá trị có nano giây với độ chính xác cao hơn, formatter này không thể thể hiện đầy đủ phần lẻ. Khi cần giữ chính xác dữ liệu máy-máy, hãy chọn định dạng có độ phân giải phù hợp.

## 4. Literal và ký tự đặc biệt

Muốn in ký tự mà pattern bình thường hiểu là ký hiệu, đặt nó trong dấu nháy đơn. ISO date-time thường dùng chữ `T` làm dấu phân cách:

~~~java
DateTimeFormatter isoLike =
        DateTimeFormatter.ofPattern("uuuu-MM-dd'T'HH:mm:ss");
System.out.println(LocalDateTime.of(2026, 10, 24, 9, 5, 7)
        .format(isoLike));
// 2026-10-24T09:05:07
~~~

Có thể đưa nhãn vào mẫu:

~~~java
DateTimeFormatter vietnameseLabel =
        DateTimeFormatter.ofPattern("'Ngày' dd 'tháng' MM 'năm' uuuu");
System.out.println(LocalDate.of(2026, 10, 24)
        .format(vietnameseLabel));
// Ngày 24 tháng 10 năm 2026
~~~

Hai dấu nháy đơn liên tiếp `''` biểu diễn một dấu nháy đơn literal. Nếu mở dấu nháy nhưng không đóng đúng cách, `ofPattern` có thể ném `IllegalArgumentException`. Hãy viết literal rõ ràng, đặc biệt khi pattern có cả chữ mô tả lẫn ký hiệu ngày giờ.

## 5. Locale quyết định tên tháng và thứ

Pattern `EEE, d MMM uuuu` không cố định tên tháng hoặc thứ bằng ngôn ngữ nào. `Locale` kiểm soát tên và một số quy ước trình bày.

~~~java
LocalDate date = LocalDate.of(2026, 10, 24);
DateTimeFormatter english =
        DateTimeFormatter.ofPattern("EEE, d MMM uuuu", Locale.US);
DateTimeFormatter vietnamese =
        DateTimeFormatter.ofPattern("EEEE, d MMMM uuuu",
                Locale.forLanguageTag("vi-VN"));

System.out.println(date.format(english));
System.out.println(date.format(vietnamese));
~~~

Ví dụ đầu ra với dữ liệu Locale tương ứng:

~~~text
Sat, 24 Oct 2026
Thứ Bảy, 24 tháng 10 năm 2026
~~~

Tên có thể phụ thuộc dữ liệu CLDR và phiên bản JDK. Nếu đầu ra phải khớp tuyệt đối giữa các môi trường, hãy quy định JDK/Locale và viết test. Không dựa vào Locale mặc định của máy vì laptop dev và server có thể khác nhau.

Có thể chỉ định Locale ngay ở `ofPattern(pattern, locale)` hoặc gọi `formatter.withLocale(locale)`. Pattern điều khiển cấu trúc; Locale điều khiển ngôn ngữ và một số quy tắc địa phương. Hai quyết định này cần được kiểm soát riêng.

## 6. Offset và múi giờ trong pattern

| Ký hiệu | Vai trò thường gặp | Lưu ý |
| --- | --- | --- |
| `X`, `XX`, `XXX` | Offset theo dạng ISO | `XXX` thường cho `+07:00`; zero offset có thể hiện `Z` |
| `x`, `xx`, `xxx` | Dạng offset ISO với quy tắc zero khác `X` | Chọn theo format contract |
| `Z` | Offset theo quy tắc formatter | Không phải luôn là ký tự chữ Z |
| `O` / `OOOO` | Offset theo dạng localized | Ví dụ dạng GMT, tùy Locale |
| `z` / `zzzz` | Tên vùng dạng ngắn/dài | Có thể mơ hồ hoặc phụ thuộc ngôn ngữ |
| `V` | ID vùng | Dạng `VV` dùng để in zone ID |

Mẫu chỉ có thể in offset/zone nếu dữ liệu đầu vào có trường phù hợp. `LocalDateTime` không chứa offset hoặc zone; nếu pattern đòi `XXX` hoặc `VV`, formatter không thể tự đoán. Dùng `OffsetDateTime` hoặc `ZonedDateTime` khi dữ liệu thực sự mang các thông tin đó.

~~~java
ZonedDateTime meeting = LocalDateTime.of(2026, 10, 24, 9, 30)
        .atZone(ZoneId.of("Asia/Ho_Chi_Minh"));
DateTimeFormatter zonedFmt =
        DateTimeFormatter.ofPattern("uuuu-MM-dd HH:mm XXX '['VV']'");
System.out.println(meeting.format(zonedFmt));
~~~

Đầu ra:

~~~text
2026-10-24 09:30 +07:00 [Asia/Ho_Chi_Minh]
~~~

`X`, `x`, `Z` và `O` không có cùng quy tắc. Tên vùng `z` cũng không nên là định danh máy-máy duy nhất: các tên viết tắt có thể trùng giữa vùng. Với lịch tương lai, giữ `ZoneId` khu vực để dùng quy tắc offset theo ngày; một offset cố định không chứa lịch sử hoặc DST.

## 7. Dùng formatter dựng sẵn khi có thể

Nếu không cần pattern tùy chỉnh, Java cung cấp các formatter chuẩn:

| Hằng số | Dữ liệu phù hợp |
| --- | --- |
| `ISO_LOCAL_DATE` | Ngày ISO không có giờ/zone |
| `ISO_LOCAL_TIME` | Giờ địa phương |
| `ISO_LOCAL_DATE_TIME` | Ngày giờ địa phương, không offset |
| `ISO_OFFSET_DATE_TIME` | Ngày giờ có offset |
| `ISO_ZONED_DATE_TIME` | Ngày giờ có biểu diễn vùng |
| `ISO_INSTANT` | Instant theo ISO-8601 UTC |

Ví dụ:

~~~java
Instant instant = Instant.parse("2026-10-24T02:30:00Z");
System.out.println(DateTimeFormatter.ISO_INSTANT.format(instant));
// 2026-10-24T02:30:00Z
~~~

`ofPattern` phù hợp cho định dạng giao diện theo yêu cầu. ISO formatter dựng sẵn thường phù hợp hơn cho trao đổi dữ liệu có hợp đồng rõ. Đừng dùng `dd/MM/uuuu HH:mm` làm giao thức giữa các dịch vụ nếu chưa thống nhất Locale, zone và cách parse.

## 8. Parse chuỗi bằng cùng pattern

Có thể dùng một formatter để parse chuỗi vào kiểu tương ứng:

~~~java
DateTimeFormatter parser =
        DateTimeFormatter.ofPattern("dd/MM/uuuu HH:mm");
LocalDateTime parsed = LocalDateTime.parse(
        "24/10/2026 09:30", parser);
System.out.println(parsed);
// 2026-10-24T09:30
~~~

Chuỗi này chỉ chứa ngày và giờ nên kết quả là `LocalDateTime`; nó không tự có zone hay offset. Nếu chuỗi có offset, dùng kiểu `OffsetDateTime` và một pattern cung cấp offset. Nếu cần một instant, phải có offset hoặc zone phù hợp để xác định mốc trên dòng thời gian.

Format và parse nên được xem là hai hợp đồng liên quan nhưng khác nhau. Đầu ra của formatter có thể bị mất thông tin nếu pattern bỏ giây, phần nano, offset hoặc zone. Không thể khôi phục dữ liệu đã bị lược khỏi chuỗi.

## 9. ResolverStyle: STRICT, SMART và LENIENT

Parse gồm bước đọc trường và bước giải quyết những trường đó thành một giá trị ngày giờ. `ResolverStyle` quyết định mức độ nghiêm ngặt:

- `STRICT`: từ chối tổ hợp trường không hợp lệ.
- `SMART`: chế độ mặc định phổ biến của `ofPattern`; xử lý một số trường hợp theo quy tắc lịch thông minh, ví dụ có thể điều chỉnh ngày vượt cuối tháng trong ngữ cảnh được hỗ trợ.
- `LENIENT`: cho phép chuẩn hóa giá trị vượt phạm vi theo quy tắc lenient, chẳng hạn trường tháng/ngày có thể tràn sang kỳ khác.

Đối với biểu mẫu nhập ngày cần xác thực chặt, có thể xây formatter với `DateTimeFormatterBuilder`:

~~~java
DateTimeFormatter strict = new DateTimeFormatterBuilder()
        .appendPattern("uuuu-MM-dd")
        .toFormatter(Locale.ROOT)
        .withResolverStyle(ResolverStyle.STRICT);
~~~

Đoạn này cần import `DateTimeFormatterBuilder` và `ResolverStyle` cùng các kiểu đã dùng. Dùng `uuuu` giúp diễn giải năm ISO trực tiếp; khi dùng `yyyy` trong STRICT, trường year-of-era có thể cần thêm era để giải quyết hoàn chỉnh.

Nếu đầu vào có ngày sai như `2025-02-30`, phải quyết định rõ nên từ chối hay áp dụng chính sách điều chỉnh. Với dữ liệu tài chính, hợp đồng hoặc hồ sơ, tự sửa đầu vào có thể che giấu lỗi nghiệp vụ. Hãy viết test cho chế độ resolver đã chọn và bắt `DateTimeParseException` tại ranh giới nhập liệu.

## 10. Các lỗi pattern thường gặp

| Lỗi | Hậu quả | Cách tránh |
| --- | --- | --- |
| Dùng `MM` thay cho `mm` | In tháng thay vì phút | Kiểm tra chữ hoa/thường |
| Dùng `DD` thay `dd` | In thứ tự ngày trong năm | Kiểm tra ý nghĩa trường |
| Dùng `YYYY` làm năm lịch | Năm có thể lệch ở ranh giới tuần/năm | Dùng `uuuu` khi cần năm ISO lịch thông thường |
| Dùng `hh` mà không có `a` | Mất thông tin sáng/chiều | Dùng `HH` hoặc thêm AM/PM |
| Dùng `SSS` khi cần toàn bộ nano giây | Mất phần lẻ nhỏ hơn mili giây | Chọn độ chính xác phù hợp |
| Format `LocalDateTime` bằng pattern offset | Không có dữ liệu offset để in | Chọn kiểu có offset hoặc zone |
| Dựa vào Locale hệ thống | Output khác giữa máy | Chỉ định Locale rõ ràng |
| Định dạng giao diện làm API | Parse không ổn định hoặc mơ hồ | Chọn ISO/contract có quy tắc rõ |
| Không phân biệt format và parse | Dữ liệu lược mất không khôi phục được | Kiểm tra trường có được giữ không |
| Để literal không escape | Ký tự bị hiểu là pattern hoặc lỗi tạo formatter | Dùng dấu nháy đơn cho literal |

## 11. Ví dụ Java 17+ chạy độc lập

Chương trình minh họa pattern số, phần mili giây, Locale tiếng Anh/Việt, parse ngược và định dạng offset/zone. Các giá trị đầu vào đều cố định.

~~~java
import java.time.LocalDate;
import java.time.LocalDateTime;
import java.time.LocalTime;
import java.time.ZoneId;
import java.time.ZonedDateTime;
import java.time.format.DateTimeFormatter;
import java.util.Locale;

public class OfPatternDemo {
    public static void main(String[] args) {
        LocalDate date = LocalDate.of(2026, 10, 24);
        LocalTime time = LocalTime.of(9, 5, 7, 123_000_000);
        LocalDateTime local = LocalDateTime.of(date, time);

        DateTimeFormatter numeric =
                DateTimeFormatter.ofPattern("dd/MM/uuuu HH:mm:ss");
        DateTimeFormatter fraction =
                DateTimeFormatter.ofPattern("HH:mm:ss.SSS");
        DateTimeFormatter english =
                DateTimeFormatter.ofPattern("EEE, d MMM uuuu", Locale.US);
        DateTimeFormatter vietnamese =
                DateTimeFormatter.ofPattern("EEEE, d MMMM uuuu",
                        Locale.forLanguageTag("vi-VN"));

        System.out.println("numeric=" + local.format(numeric));
        System.out.println("fraction=" + time.format(fraction));
        System.out.println("english=" + date.format(english));
        System.out.println("vietnamese=" + date.format(vietnamese));

        DateTimeFormatter parser =
                DateTimeFormatter.ofPattern("dd/MM/uuuu HH:mm");
        LocalDateTime parsed =
                LocalDateTime.parse("24/10/2026 09:30", parser);
        System.out.println("parsed=" + parsed);

        ZonedDateTime meeting = local.atZone(
                ZoneId.of("Asia/Ho_Chi_Minh"));
        DateTimeFormatter zonedPattern =
                DateTimeFormatter.ofPattern("uuuu-MM-dd HH:mm XXX '['VV']'");
        System.out.println("zoned=" + meeting.format(zonedPattern));
    }
}
~~~

Lưu thành `OfPatternDemo.java`, rồi biên dịch và chạy với JDK 17+:

~~~bash
javac OfPatternDemo.java
java OfPatternDemo
~~~

Đầu ra điển hình với dữ liệu Locale tương ứng:

~~~text
numeric=24/10/2026 09:05:07
fraction=09:05:07.123
english=Sat, 24 Oct 2026
vietnamese=Thứ Bảy, 24 tháng 10 năm 2026
parsed=2026-10-24T09:30
zoned=2026-10-24 09:05 +07:00 [Asia/Ho_Chi_Minh]
~~~

Giải thích:

1. Pattern số điều khiển zero-padding và thứ tự ngày/giờ.
2. `SSS` in ba chữ số phần lẻ; `123_000_000` nano tương ứng `123` mili giây.
3. Hai formatter tên ngày dùng Locale rõ ràng nên không phụ thuộc Locale mặc định của máy.
4. `parsed` là `LocalDateTime` do chuỗi đầu vào không chứa offset.
5. `zoned` có cả offset và zone vì giá trị đã gắn `Asia/Ho_Chi_Minh`.

Tên tháng/thứ có thể phụ thuộc dữ liệu Locale của phiên bản JDK; nếu cần stdout đồng nhất tuyệt đối, hãy cố định môi trường test hoặc dùng format số ổn định cho phần dữ liệu quan trọng.

## 12. Tái sử dụng formatter và checklist

Khi pattern/Locale cố định, đặt formatter thành hằng số dùng chung:

~~~java
private static final DateTimeFormatter LOG_FORMAT =
        DateTimeFormatter.ofPattern("uuuu-MM-dd HH:mm:ss");
~~~

Điều này tránh tạo lại formatter liên tục. Nếu pattern do người dùng cấu hình, hãy xác thực khi nạp cấu hình; mẫu không hợp lệ có thể ném ngoại lệ ngay lúc tạo formatter.

Trước khi đưa pattern vào sản phẩm, kiểm tra:

1. **Kiểu nguồn:** giá trị có đúng trường ngày/giờ/offset/zone mà mẫu cần không?
2. **Ký hiệu:** tháng `MM` hay phút `mm`; ngày `dd` hay ngày trong năm `DD`; năm lịch `uuuu` hay năm tuần `YYYY`?
3. **Giờ:** dùng hệ 24 tiếng `HH` hay 12 tiếng `hh` + `a`?
4. **Độ chính xác:** mẫu có bỏ phần nano/milli cần bảo toàn không?
5. **Locale:** tên tháng/thứ có cần ngôn ngữ cố định không?
6. **Offset/zone:** cần offset số, zone ID hay chỉ giờ địa phương?
7. **Parse:** resolver style đã phù hợp chưa? Dữ liệu sai được từ chối hay điều chỉnh?
8. **Hợp đồng:** đây là chuỗi giao diện hay định dạng trao đổi giữa dịch vụ?
9. **Biên:** test cuối tháng, năm nhuận, đầu/cuối năm, offset zero và thời gian DST khi có zone.

## 13. Bài tập tự kiểm tra

1. Tạo pattern cho `24/10/2026 09:05:07` từ `LocalDateTime`.
2. Dùng `HH:mm` và `hh:mm a` để hiển thị 09:00 và 21:00. Vì sao kết quả khác?
3. Vì sao `YYYY-MM-dd` có thể cho năm khác `uuuu-MM-dd` ở thời điểm gần ranh giới năm?
4. Tạo formatter tiếng Việt và tiếng Anh cho cùng ngày; giải thích vai trò của Locale.
5. Vì sao `LocalDateTime` không format được offset/zone thật chỉ bằng cách thêm `XXX` hay `VV` vào pattern?
6. Parse `2025-02-30` bằng formatter SMART và STRICT; xác định chính sách đúng cho biểu mẫu của bạn.
7. Tạo mẫu có chữ literal `T` và nhãn `'Ngày'`. Vì sao cần escape chữ vốn là ký hiệu pattern?
8. Thiết kế định dạng cho timestamp API cần bảo toàn instant, offset và vùng; chọn formatter ISO dựng sẵn hay pattern riêng và giải thích.

**Ghi nhớ:** `DateTimeFormatter.ofPattern()` biến chuỗi pattern thành quy tắc định dạng/parse. Hiểu chính xác các ký hiệu chữ hoa/thường, chọn Locale rõ ràng, không dùng năm tuần thay cho năm lịch, và chỉ yêu cầu offset/zone khi kiểu nguồn thực sự có thông tin đó. Với dữ liệu trao đổi giữa máy, hãy ưu tiên một hợp đồng ISO rõ nghĩa; với giao diện, chọn pattern theo ngôn ngữ và mục đích hiển thị.