# DateTimeFormatter và phân tích dữ liệu thời gian chặt chẽ trong Java 27

Một chuỗi như `2026-02-30` có hình dạng giống ngày ISO, nhưng ngày 30 tháng 2 không tồn tại. Chuỗi `27/11/2026` có thể được hiểu đúng tại Việt Nam, nhưng một hệ thống khác lại mong định dạng tháng/ngày/năm. Thời điểm `2026-03-29 02:30` có thể không tồn tại tại một khu vực đang chuyển sang giờ mùa hè, trong khi tại khu vực khác nó hoàn toàn hợp lệ.

Để xử lý các trường hợp này, chương **Thời gian và số học chính xác** trong Java 27 sử dụng các kiểu của `java.time` và bộ định dạng/phân tích trong `java.time.format`. Trọng tâm bài học là **`DateTimeFormatter`**: cách xác định khuôn dạng, kiểm soát tính hợp lệ bằng **`ResolverStyle.STRICT`**, xử lý locale, offset và time zone, cũng như thiết kế API nhận dữ liệu thời gian từ bên ngoài một cách có thể kiểm thử.

Chỉ sử dụng các API **hiện hành** trong Java 27. `DateTimeFormatter` và các kiểu `java.time` đã ổn định qua nhiều phiên bản Java, bất biến theo thiết kế và thích hợp cho ứng dụng mới; không cần dựa vào các bộ phân tích ngày giờ kiểu cũ. Tài liệu chính thức: [DateTimeFormatter](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/time/format/DateTimeFormatter.html), [DateTimeFormatterBuilder](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/time/format/DateTimeFormatterBuilder.html), [ResolverStyle](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/time/format/ResolverStyle.html).

## 1. Chọn đúng kiểu thời gian trước khi phân tích

Một chuỗi ngày giờ không tự xác định đầy đủ ý nghĩa. Trước khi chọn formatter, phải hiểu người dùng muốn biểu diễn **ngày trên lịch**, **giờ trong ngày**, **giờ địa phương**, **thời điểm tuyệt đối** hay **giờ gắn với quy tắc múi giờ**.

| Kiểu Java | Đại diện cho | Ví dụ sử dụng |
| --- | --- | --- |
| `LocalDate` | Ngày trên lịch ISO, không có giờ/múi giờ | Ngày sinh, ngày thanh toán |
| `LocalTime` | Giờ trong ngày, không có ngày/múi giờ | Giờ mở cửa hằng ngày |
| `LocalDateTime` | Ngày và giờ địa phương, **chưa biết offset hay zone** | Lịch hẹn theo đồng hồ địa phương |
| `OffsetDateTime` | Ngày giờ và **UTC offset** như `+07:00` | Dấu thời gian trao đổi giữa hệ thống |
| `ZonedDateTime` | Ngày giờ với `ZoneId` và quy tắc vùng | Cuộc họp ở `Europe/Paris` |
| `Instant` | Một thời điểm trên trục UTC | Dấu thời gian sự kiện, log chuẩn hóa |
| `YearMonth` | Tháng và năm | Kỳ sao kê |
| `MonthDay` | Ngày và tháng không có năm | Ngày kỷ niệm |
| `Duration` | Khoảng thời gian dựa trên giây và nano | Timeout hoặc thời lượng xử lý |
| `Period` | Khoảng theo ngày/tháng/năm trên lịch | Chu kỳ cộng thêm tháng |

**Quy tắc thiết kế:** `LocalDateTime` **không đủ** để xác định một `Instant`. Cần thêm offset, `ZoneId` cùng quy tắc xử lý thời điểm mơ hồ hoặc thông tin khác do hợp đồng xác định. Không tự coi giờ địa phương là UTC.

## 2. `DateTimeFormatter`: format và parse

`DateTimeFormatter` là một class **bất biến (immutable), thread-safe**. Ta thường tạo formatter một lần và dùng lại cho nhiều lần format/parse, kể cả giữa các thread. Các phương thức như `withLocale`, `withZone`, `withResolverStyle` trả về **formatter mới**, không thay đổi đối tượng cũ.

### 2.1. Dùng định dạng ISO có sẵn

Với dữ liệu giữa các hệ thống, các định dạng ISO chuẩn thường dễ tích hợp hơn mẫu chuỗi tự thiết kế.

~~~~java
import java.time.LocalDate;
import java.time.format.DateTimeFormatter;

public class BasicDateExample {
    public static void main(String[] args) {
        LocalDate date = LocalDate.of(2026, 11, 27);

        String text = date.format(DateTimeFormatter.ISO_LOCAL_DATE);
        System.out.println(text); // 2026-11-27

        LocalDate parsed = LocalDate.parse(
                "2026-11-27", DateTimeFormatter.ISO_LOCAL_DATE);
        System.out.println(parsed.equals(date)); // true
    }
}
~~~~

Các formatter chuẩn thường dùng:

| Formatter | Mục tiêu | Ví dụ |
| --- | --- | --- |
| `ISO_LOCAL_DATE` | Ngày ISO | `2026-11-27` |
| `BASIC_ISO_DATE` | Ngày ISO không dấu phân cách | `20261127` |
| `ISO_LOCAL_TIME` | Giờ ISO không offset | `09:30:15` |
| `ISO_LOCAL_DATE_TIME` | Ngày giờ địa phương ISO | `2026-11-27T09:30:15` |
| `ISO_OFFSET_DATE_TIME` | Ngày giờ có offset | `2026-11-27T09:30:15+07:00` |
| `ISO_ZONED_DATE_TIME` | Ngày giờ có thông tin zone | `2026-11-27T09:30:15+07:00[Asia/Ho_Chi_Minh]` |
| `ISO_INSTANT` | Thời điểm tuyệt đối theo dạng UTC | `2026-11-27T02:30:15Z` |
| `RFC_1123_DATE_TIME` | Ngày giờ định dạng RFC 1123 | Thường gặp trong header giao thức |

Các formatter ISO được xác định sẵn có những quy tắc riêng về tính linh hoạt của cú pháp. Ví dụ, chúng có thể chấp nhận một số biến thể ISO hợp lệ rộng hơn một mẫu máy-máy tự thiết kế. **Đừng mặc định formatter ISO là bộ kiểm tra đúng 10 ký tự** cho mọi chính sách của sản phẩm; nếu hệ thống yêu cầu độ dài và tập ký tự chính xác, hãy nêu yêu cầu đó riêng.

### 2.2. Dùng `ofPattern` khi có khuôn dạng riêng

~~~~java
import java.time.LocalDate;
import java.time.format.DateTimeFormatter;
import java.util.Locale;

public class CustomFormatExample {
    private static final DateTimeFormatter DISPLAY =
            DateTimeFormatter.ofPattern("dd/MM/uuuu", Locale.ROOT);

    public static void main(String[] args) {
        LocalDate date = LocalDate.of(2026, 11, 27);
        System.out.println(DISPLAY.format(date)); // 27/11/2026

        LocalDate parsed = LocalDate.parse("27/11/2026", DISPLAY);
        System.out.println(parsed); // 2026-11-27
    }
}
~~~~

Đoạn trên minh họa cơ chế format và parse đối xứng, nhưng để nhận **dữ liệu không tin cậy**, còn phải đặt `ResolverStyle.STRICT`. Lý do: formatter tạo bằng `ofPattern` mặc định có **`ResolverStyle.SMART`**, có thể điều chỉnh một ngày sai lịch thành ngày hợp lệ.

## 3. Bảng ký hiệu pattern cần nhớ

Các ký hiệu phân biệt **chữ hoa/chữ thường**, độ dài ký hiệu và trường thời gian:

| Ký hiệu | Ý nghĩa | Ví dụ hoặc lưu ý |
| --- | --- | --- |
| `u` | Năm proleptic theo lịch ISO | `uuuu`: 2026 |
| `y` | Năm của một **era** (*year-of-era*) | `yyyy` cần chú ý khi parse nghiêm ngặt |
| `G` | Tên era | `AD`, `BC` tùy locale |
| `Y` | **Năm theo tuần** (*week-based-year*) | Có thể khác năm lịch gần giao thừa |
| `M` | Tháng dạng số/tên theo ngữ cảnh | `MM`: 11, `MMM`: Nov |
| `L` | Tháng ở dạng độc lập | Khác `M` ở một số ngôn ngữ |
| `d` | Ngày trong tháng | `dd`: 27 |
| `D` | Ngày thứ mấy trong năm | `DDD`: 331 trong năm không nhuận |
| `E` | Tên thứ trong tuần | `EEE`: Fri (tiếng Anh) |
| `e` / `c` | Thứ trong tuần theo locale / dạng độc lập | Phụ thuộc quy tắc tuần |
| `H` | Giờ kiểu 0–23 | `HH`: 09 |
| `h` | Giờ kiểu 1–12 | Thường dùng với `a` (AM/PM) |
| `a` | Dấu AM/PM | Phụ thuộc locale |
| `m` | Phút trong giờ | `mm`: 30 |
| `s` | Giây trong phút | `ss`: 15 |
| `S` | Phần thập phân của giây | `SSS`: mili giây dạng 3 chữ số |
| `n` | Nano giây trong giây | Giá trị từ 0 đến 999.999.999 |
| `X` / `x` | UTC offset theo các biến thể được quy định | `XXX`: `+07:00`; `X` có thể in `Z` ở UTC |
| `Z` / `O` | Offset theo dạng RFC hoặc dạng địa phương | Dùng đúng hợp đồng của đối tác |
| `V` | Mã `ZoneId` | `VV`: `Asia/Ho_Chi_Minh` |
| `z` | Tên zone theo locale | Có thể gây mơ hồ trong dữ liệu trao đổi |

Hai ký hiệu tưởng giống nhưng có ý nghĩa khác:

~~~~text
uuuu-MM-dd   -> năm lịch - tháng - ngày
YYYY-MM-dd   -> năm theo tuần - tháng - ngày (không phù hợp cho ngày ISO thông thường)

HH:mm        -> giờ (0..23) : phút (0..59)
hh:mm a      -> giờ (1..12) : phút AM/PM

MM           -> tháng
mm           -> phút
dd           -> ngày trong tháng
DD           -> ngày trong năm
~~~~

**Quan trọng:** khi cần ngày lịch ISO, ưu tiên `uuuu-MM-dd`, không dùng `YYYY-MM-dd`. `Y` phụ thuộc quy tắc tuần (*week fields*) và locale; tại ranh giới năm, nó có thể cho năm khác với năm trong `LocalDate`. Việc ghép năm theo tuần với tháng/ngày theo lịch còn có thể tạo một cấu trúc trường không có ý nghĩa hoặc không giải được thành ngày.

### 3.1. Dấu phân cách, literal và độ dài ký hiệu

Các ký tự ngoài nhóm pattern letters thường được coi là literal; phần literal có ký tự chữ cái cần đặt trong nháy đơn.

~~~~java
DateTimeFormatter dateTime = DateTimeFormatter.ofPattern(
        "uuuu-MM-dd'T'HH:mm:ss", Locale.ROOT);

String text = dateTime.format(
        java.time.LocalDateTime.of(2026, 11, 27, 9, 30, 15));
System.out.println(text); // 2026-11-27T09:30:15
~~~~

Khi cần in dấu nháy đơn literal, dùng hai nháy đơn liên tiếp trong pattern. Mẫu ký hiệu lạ hoặc đếm số lần lặp ký hiệu sai có thể khiến `DateTimeFormatter.ofPattern` ném `IllegalArgumentException` ngay khi khởi tạo formatter.

Các pattern có hai chữ số năm như `yy` hoặc `uu` thường dùng **reduced year** dựa trên mốc xác định, không chỉ đơn giản là “năm hiện tại rút gọn”. Đối với dữ liệu nghiệp vụ cần năm đầy đủ, tránh nhận năm hai chữ số nếu không có một quy ước mở rộng rõ ràng.

## 4. Hai giai đoạn của parsing và ý nghĩa `ResolverStyle`

Một lần parse qua `DateTimeFormatter` về bản chất gồm hai giai đoạn:

1. **Đọc cú pháp:** so khớp chữ, dấu phân cách và lấy những cặp `TemporalField → value` từ input.
2. **Giải quyết thành giá trị ngày giờ:** kết hợp năm, tháng, ngày, giờ, phút, offset, chronology... rồi xác minh xem chúng có tạo được một thời gian hợp lệ không.

`ResolverStyle` chủ yếu điều khiển **giai đoạn 2**. Nó không đồng nhất với việc parser có phân biệt hoa thường, cho phép độ rộng trường linh hoạt hay không; những đặc điểm thuộc giai đoạn 1 có API riêng của `DateTimeFormatterBuilder`.

| ResolverStyle | Ý nghĩa | Trường hợp ngày 31/02/2026 |
| --- | --- | --- |
| `STRICT` | Các trường và tổ hợp trường phải hợp lệ theo lịch | Bị từ chối |
| `SMART` | Có thể điều chỉnh một số tổ hợp vào giá trị hợp lệ | Có thể chuyển thành 28/02/2026 |
| `LENIENT` | Cho phép giải quyết tràn tháng/ngày bằng phép toán | Có thể đẩy sang tháng khác |

Mỗi chronology và từng trường có quy tắc riêng; bảng chỉ minh họa lịch ISO. Đừng sử dụng `SMART` hoặc `LENIENT` cho đầu vào buộc phải thể hiện **chính xác ngày được người dùng khai báo**.

### 4.1. `ofPattern` mặc định SMART — bẫy cần tránh

~~~~java
import java.time.LocalDate;
import java.time.format.DateTimeFormatter;
import java.time.format.ResolverStyle;
import java.util.Locale;

DateTimeFormatter smart = DateTimeFormatter.ofPattern(
        "dd/MM/uuuu", Locale.ROOT);

DateTimeFormatter strict = smart.withResolverStyle(ResolverStyle.STRICT);

System.out.println(LocalDate.parse("31/02/2026", smart));
// 2026-02-28: SMART điều chỉnh ngày vượt số ngày của tháng.

// LocalDate.parse("31/02/2026", strict);
// DateTimeParseException: ngày không tồn tại.
~~~~

`withResolverStyle(STRICT)` trả về một formatter khác; `smart` vẫn giữ nguyên chính sách SMART. Khi cung cấp API parse dữ liệu từ CSV, HTTP hoặc message queue, nên xây dựng formatter chặt chẽ ngay tại điểm khai báo thay vì dựa vào giá trị mặc định.

### 4.2. Vì sao `uuuu` thích hợp hơn `yyyy` khi STRICT?

`yyyy` là `YEAR_OF_ERA`: năm **trong một era**. Nó không tự chứa thông tin era. `uuuu` là `YEAR`: năm proleptic, đủ để cùng tháng và ngày giải thành một `LocalDate` ISO.

~~~~java
import java.time.LocalDate;
import java.time.format.DateTimeFormatter;
import java.time.format.ResolverStyle;
import java.util.Locale;

DateTimeFormatter yearOfEra = DateTimeFormatter
        .ofPattern("dd/MM/yyyy", Locale.ROOT)
        .withResolverStyle(ResolverStyle.STRICT);

DateTimeFormatter prolepticYear = DateTimeFormatter
        .ofPattern("dd/MM/uuuu", Locale.ROOT)
        .withResolverStyle(ResolverStyle.STRICT);

// LocalDate.parse("27/11/2026", yearOfEra);
// Có thể thất bại: chưa có ERA để kết hợp với YEAR_OF_ERA.

System.out.println(LocalDate.parse("27/11/2026", prolepticYear));
// 2026-11-27
~~~~

Nếu hợp đồng thực sự cần năm theo era, hãy cung cấp era hoặc quy tắc mặc định era một cách tường minh với `DateTimeFormatterBuilder.parseDefaulting`. Còn với hệ thống trao đổi ngày ISO hiện đại, `uuuu` thường rõ ràng hơn.

### 4.3. Dùng formatter ISO dựng sẵn nếu có thể

`DateTimeFormatter.ISO_LOCAL_DATE` và nhiều formatter ISO dựng sẵn sử dụng `ResolverStyle.STRICT`. Vì vậy:

~~~~java
import java.time.LocalDate;
import java.time.format.DateTimeFormatter;

System.out.println(LocalDate.parse(
        "2024-02-29", DateTimeFormatter.ISO_LOCAL_DATE));
// 2024-02-29 (năm nhuận hợp lệ)

// LocalDate.parse("2025-02-29", DateTimeFormatter.ISO_LOCAL_DATE);
// DateTimeParseException: ngày không tồn tại trong năm 2025.
~~~~

**STRICT không có nghĩa là tất cả ràng buộc nghiệp vụ đều đúng.** Ngày `1900-01-01` có thể là ngày lịch ISO hợp lệ nhưng không thuộc khoảng ngày đặt chỗ mà ứng dụng cho phép. Hãy kiểm tra **miền nghiệp vụ** sau khi parse.

## 5. Viết phương thức parse chặt chẽ, có thể dùng lại

Thay vì đặt pattern rải rác khắp code, hãy định nghĩa một formatter bất biến và một phương thức có hợp đồng rõ:

~~~~java
import java.time.LocalDate;
import java.time.format.DateTimeFormatter;
import java.time.format.ResolverStyle;
import java.util.Locale;
import java.util.Objects;

public final class BusinessDates {
    private BusinessDates() {
    }

    private static final DateTimeFormatter DATE_INPUT =
            DateTimeFormatter.ofPattern("dd/MM/uuuu", Locale.ROOT)
                    .withResolverStyle(ResolverStyle.STRICT);

    /**
     * Nhận ngày theo đúng thứ tự ngày/tháng/năm, ví dụ 27/11/2026.
     * Không tự chỉnh ngày không tồn tại sang ngày khác.
     */
    public static LocalDate parseDate(String input) {
        Objects.requireNonNull(input, "input");
        return LocalDate.parse(input, DATE_INPUT);
    }

    public static String formatDate(LocalDate date) {
        return DATE_INPUT.format(Objects.requireNonNull(date, "date"));
    }
}
~~~~

Điều gì được kiểm soát?

- Ngữ nghĩa **ngày/tháng/năm** và thứ tự dấu `/` là tường minh.
- Một ngày sai lịch, ví dụ `29/02/2025`, không được SMART tự sửa.
- Không chấp nhận input thừa ở cuối như `27/11/2026abc` trong phép `LocalDate.parse` đầy đủ.
- Formatter có thể được chia sẻ và tái sử dụng; không có state mutable bên trong.

**Giới hạn cần nói rõ:** cú pháp pattern và strict resolver vẫn không thay thế mọi quy tắc về chiều dài, bảng chữ số hay khoảng năm. Nếu hợp đồng yêu cầu **chính xác** 10 ký tự dạng ASCII `dd/MM/uuuu` với năm từ 0001 đến 9999, hãy thêm validation định dạng nguyên văn và kiểm tra khoảng năm:

~~~~java
private static final java.util.regex.Pattern EXACT_DATE =
        java.util.regex.Pattern.compile(
                "[0-9]{2}/[0-9]{2}/[0-9]{4}");

static LocalDate parseFixedDate(String input) {
    Objects.requireNonNull(input, "input");

    if (!EXACT_DATE.matcher(input).matches()) {
        throw new IllegalArgumentException(
                "Date must use dd/MM/yyyy with ASCII digits");
    }

    LocalDate date = LocalDate.parse(input, DATE_INPUT);
    if (date.getYear() < 1 || date.getYear() > 9999) {
        throw new IllegalArgumentException("Year is outside supported range");
    }
    return date;
}
~~~~

`EXACT_DATE` chỉ kiểm tra **hình dạng** và độ dài; `LocalDate.parse(..., DATE_INPUT)` mới kiểm tra tính hợp lệ trên lịch. Đặt `EXACT_DATE` và `parseFixedDate` trong cùng lớp `BusinessDates` ở ví dụ phía trên để dùng lại hằng `DATE_INPUT`. Trong thông báo lỗi có thể dùng dạng hiển thị `dd/MM/yyyy` như một cách nói thông thường, nhưng pattern Java thực tế vẫn dùng `dd/MM/uuuu` để parse nghiêm ngặt.

Khi gọi từ HTTP/CSV, không nên tự `strip()` hoặc bỏ ký tự thừa nếu hợp đồng không cho phép. Việc chuẩn hóa dữ liệu là **chính sách riêng**: nếu có, phải công bố rõ và áp dụng trước bước parse.

## 6. Ngày giờ, offset, zone và thời điểm tuyệt đối

Các giá trị `2026-11-27T09:30:15` và `2026-11-27T09:30:15+07:00` không mang cùng mức thông tin:

~~~~text
2026-11-27T09:30:15                   -> LocalDateTime
2026-11-27T09:30:15+07:00             -> OffsetDateTime
2026-11-27T09:30:15+07:00[Asia/Ho_Chi_Minh] -> ZonedDateTime
2026-11-27T02:30:15Z                  -> Instant (cùng thời điểm với +07:00 phía trên)
~~~~

### 6.1. Parse và chuẩn hóa thời điểm có offset

~~~~java
import java.time.Instant;
import java.time.OffsetDateTime;
import java.time.format.DateTimeFormatter;

OffsetDateTime received = OffsetDateTime.parse(
        "2026-11-27T09:30:15+07:00",
        DateTimeFormatter.ISO_OFFSET_DATE_TIME);

Instant instant = received.toInstant();
System.out.println(instant); // 2026-11-27T02:30:15Z
~~~~

`+07:00` là **offset**: một độ lệch so với UTC tại thời điểm đó. Nó **không phải** tên của một vùng `ZoneId` với lịch sử và quy tắc đổi giờ. Hai nơi có thể cùng offset tại một thời điểm nhưng có quy tắc khác nhau trong tương lai.

Nếu hệ thống chỉ lưu sự kiện đã xảy ra, `Instant` thường phù hợp. Nếu cần hiển thị lại theo vùng của người sử dụng:

~~~~java
import java.time.ZoneId;
import java.time.format.DateTimeFormatter;
import java.util.Locale;

ZoneId userZone = ZoneId.of("Asia/Ho_Chi_Minh");
DateTimeFormatter display = DateTimeFormatter
        .ofPattern("dd/MM/uuuu HH:mm:ss VV", Locale.ROOT)
        .withZone(userZone);

System.out.println(display.format(instant));
// 27/11/2026 09:30:15 Asia/Ho_Chi_Minh
~~~~

`withZone` tạo formatter mới có zone override khi cần. Nếu muốn hiển thị lại cùng một `Instant` theo một vùng khác, tạo formatter với `ZoneId` tương ứng; không thay `Instant` bằng `LocalDateTime` rồi đoán offset.

### 6.2. Parse ZonedDateTime có region ID

~~~~java
import java.time.ZonedDateTime;
import java.time.format.DateTimeFormatter;

ZonedDateTime zoned = ZonedDateTime.parse(
        "2026-11-27T09:30:15+07:00[Asia/Ho_Chi_Minh]",
        DateTimeFormatter.ISO_ZONED_DATE_TIME);

System.out.println(zoned.getZone()); // Asia/Ho_Chi_Minh
System.out.println(zoned.toInstant()); // 2026-11-27T02:30:15Z
~~~~

`ZoneId` chứa thông tin quy tắc vùng. Về lâu dài, các chính phủ có thể thay đổi luật múi giờ; ứng dụng cần sử dụng dữ liệu time zone cập nhật theo phiên bản môi trường đang chạy. Không mã hóa cứng `+07:00` thay cho mọi `ZoneId` trên thế giới.

### 6.3. Vì sao `LocalDateTime` không tự đủ để tạo `Instant`?

~~~~java
import java.time.LocalDateTime;
import java.time.ZoneId;

LocalDateTime local = LocalDateTime.parse("2026-11-27T09:30:15");
ZoneId zone = ZoneId.of("Asia/Ho_Chi_Minh");

System.out.println(local.atZone(zone).toInstant());
// 2026-11-27T02:30:15Z
~~~~

Đoạn này **chủ động cung cấp zone**. Nếu nguồn dữ liệu không cho biết zone, API phải có chính sách xác định zone từ cấu hình, người dùng hoặc trường dữ liệu khác. `ZoneId.systemDefault()` phụ thuộc máy đang chạy và có thể làm cùng input cho kết quả khác nhau giữa môi trường phát triển và production.

### 6.4. DST gap và overlap: cú pháp hợp lệ chưa đủ

Tại vùng có **Daylight Saving Time (DST)**, một giờ trên đồng hồ địa phương có thể:

- **Không tồn tại (gap):** đồng hồ nhảy từ 01:59 lên 03:00, nên 02:30 bị bỏ qua.
- **Xuất hiện hai lần (overlap):** đồng hồ lùi lại, nên 02:30 có thể ứng với hai thời điểm khác nhau.

Đối với `Europe/Paris` theo quy tắc DST hiện hành, ví dụ minh họa là ngày 29/03/2026 (gap) và 25/10/2026 (overlap). Dữ liệu vùng được vận hành theo phiên bản tzdb của JVM, do đó cần kiểm tra lại quy tắc thực tế khi dùng cho các ngày trong tương lai.

**Bẫy:** `LocalDateTime.atZone(zone)` được thiết kế để **giải quyết** gap/overlap theo quy tắc của API, không có nghĩa nó sẽ từ chối mọi thời điểm địa phương mơ hồ. Trong gap nó có thể đẩy giờ địa phương tiến lên; trong overlap nó chọn một offset mặc định, trừ khi được hướng dẫn khác.

Nếu hợp đồng yêu cầu **chỉ nhận giờ địa phương ánh xạ duy nhất tới một thời điểm**, hãy kiểm tra `ZoneRules.getValidOffsets`:

~~~~java
import java.time.LocalDateTime;
import java.time.ZoneId;
import java.time.ZoneOffset;
import java.time.ZonedDateTime;
import java.time.format.DateTimeFormatter;
import java.time.format.ResolverStyle;
import java.util.List;
import java.util.Locale;
import java.util.Objects;

public class UnambiguousTimeParser {
    private static final ZoneId ZONE = ZoneId.of("Europe/Paris");
    private static final DateTimeFormatter INPUT = DateTimeFormatter
            .ofPattern("uuuu-MM-dd'T'HH:mm", Locale.ROOT)
            .withResolverStyle(ResolverStyle.STRICT);

    static ZonedDateTime parse(String text) {
        LocalDateTime local = LocalDateTime.parse(
                Objects.requireNonNull(text, "text"), INPUT);

        List<ZoneOffset> offsets =
                ZONE.getRules().getValidOffsets(local);
        if (offsets.size() != 1) {
            throw new IllegalArgumentException(
                    "Local date-time is nonexistent or ambiguous in zone");
        }
        return ZonedDateTime.ofStrict(local, offsets.getFirst(), ZONE);
    }

    public static void main(String[] args) {
        System.out.println(parse("2026-11-27T09:30"));

        // parse("2026-03-29T02:30"); // Gap: bị từ chối
        // parse("2026-10-25T02:30"); // Overlap: bị từ chối
    }
}
~~~~

Ý nghĩa của kết quả `getValidOffsets(local)`:

| Số offset | Ý nghĩa | Chính sách nghiêm ngặt ví dụ |
| --- | --- | --- |
| 0 | Giờ địa phương **không tồn tại** trong vùng (gap) | Từ chối |
| 1 | Xác định được một offset duy nhất | Chấp nhận |
| 2 | Giờ địa phương **mơ hồ** do overlap | Từ chối hoặc yêu cầu caller chọn offset |

Một số ứng dụng cố ý chấp nhận overlap bằng cách lấy offset sớm hoặc muộn; điều đó cũng hợp lệ **nếu hợp đồng nói rõ**. Khi có offset từ người gọi, `ZonedDateTime.ofStrict(local, offset, zone)` giúp xác minh offset có hợp lệ với local time và zone hay không.

### 6.5. Đừng dùng tên rút gọn của múi giờ làm định danh kỹ thuật

Những chữ viết tắt như `CST` hoặc `IST` có thể được dùng cho nhiều vùng trên thế giới. Khi trao đổi dữ liệu, ưu tiên:

- `Instant` hoặc chuỗi ISO có offset để chỉ **thời điểm đã xảy ra**.
- ID vùng IANA như `Asia/Ho_Chi_Minh`, `Europe/Paris` khi cần lưu **quy tắc vùng** cho các cuộc hẹn tương lai.
- Giao diện hiển thị tên giờ địa phương theo locale nếu người dùng cần đọc dễ hiểu, nhưng không lấy tên hiển thị đó làm khóa lưu trữ.

## 7. Locale, chữ số địa phương và lịch (chronology)

### 7.1. Locale cho dữ liệu hiển thị

Locale ảnh hưởng cách ghi tên tháng, thứ và kiểu định dạng dài/ngắn:

~~~~java
import java.time.LocalDate;
import java.time.format.DateTimeFormatter;
import java.time.format.FormatStyle;
import java.util.Locale;

LocalDate date = LocalDate.of(2026, 11, 27);
Locale vietnamese = Locale.forLanguageTag("vi-VN");

DateTimeFormatter localized = DateTimeFormatter
        .ofLocalizedDate(FormatStyle.LONG)
        .withLocale(vietnamese);

System.out.println(localized.format(date));
// Kết quả hiển thị theo quy ước locale vi-VN của môi trường Java.
~~~~

Không hardcode một chuỗi kết quả chính xác trong kiểm thử dựa trên locale nếu ứng dụng chấp nhận việc cập nhật dữ liệu định dạng của JDK. Các mẫu từ `ofLocalizedDate` có thể thay đổi theo locale, dữ liệu CLDR hoặc bản cập nhật nền tảng.

Với **giao thức máy–máy**, dùng mẫu ISO tường minh hoặc `DateTimeFormatter.ISO_*` thay vì `ofLocalizedDate`, vì dữ liệu trao đổi không nên phụ thuộc thiết lập ngôn ngữ của máy.

### 7.2. Parsing tên tháng phải khớp locale

~~~~java
import java.time.LocalDate;
import java.time.format.DateTimeFormatter;
import java.time.format.ResolverStyle;
import java.util.Locale;

DateTimeFormatter english = DateTimeFormatter
        .ofPattern("d MMM uuuu", Locale.ENGLISH)
        .withResolverStyle(ResolverStyle.STRICT);

LocalDate parsed = LocalDate.parse("27 Nov 2026", english);
System.out.println(parsed); // 2026-11-27
~~~~

Nếu pattern dùng tên tháng (`MMM`/`MMMM`), việc parse phụ thuộc locale. Không giả định tên tháng tiếng Anh được hiểu bởi formatter cấu hình tiếng Việt hoặc ngược lại. Cần định nghĩa và truyền locale theo **hợp đồng input**, không dùng locale mặc định ngẫu nhiên.

### 7.3. DecimalStyle và hệ chữ số

`DateTimeFormatter` có `DecimalStyle`, quản lý ký tự số 0, dấu cộng/trừ và dấu phân cách dùng khi format/parse:

~~~~java
import java.time.format.DateTimeFormatter;
import java.time.format.DecimalStyle;
import java.util.Locale;

Locale locale = Locale.forLanguageTag("ar");
DateTimeFormatter formatter = DateTimeFormatter
        .ofPattern("uuuu-MM-dd", locale)
        .withDecimalStyle(DecimalStyle.of(locale));
~~~~

Ví dụ minh họa việc **cấu hình rõ ràng** hệ chữ số theo locale. Không dự đoán rằng mọi locale luôn dùng cùng một tập glyph cho chữ số. Nếu hệ thống chỉ nhận chữ số ASCII, hãy dùng formatter theo chính sách máy–máy và kiểm tra literal ASCII riêng ở ranh giới đầu vào.

### 7.4. Chronology không đồng nghĩa với locale

`Locale` và **chronology** là hai khái niệm khác nhau. Một ứng dụng có thể trình bày ngày theo tiếng Việt nhưng vẫn dùng lịch ISO. Nếu cần lịch khác ISO, `java.time.chrono` cung cấp các loại như `JapaneseChronology`, `ThaiBuddhistChronology`; không được tự coi thay locale là đã đổi hệ lịch.

`DateTimeFormatter.withChronology(...)` trả về formatter có chronology override; nó có thể chuyển đổi ngày khi format và ảnh hưởng quá trình giải quyết ngày lúc parse. Chỉ dùng khi hợp đồng thực sự cần lịch đó. Với dữ liệu backend ISO thông thường, `LocalDate` kết hợp ISO formatter và chronology ISO là lựa chọn dễ kiểm soát.

## 8. `DateTimeFormatterBuilder` cho định dạng có phần tùy chọn

Khi input có nhiều dạng được cho phép, `DateTimeFormatterBuilder` giúp mô tả rõ những thành phần bắt buộc và tùy chọn. Builder là **mutable và không thread-safe**; sau khi gọi `toFormatter()`, đối tượng `DateTimeFormatter` thu được **bất biến và thread-safe**.

### 8.1. Ngày giờ có giây tùy chọn

Giả sử hệ thống cho phép cả:

~~~~text
2026-11-27T09:30
2026-11-27T09:30:15
~~~~

Ta định nghĩa một formatter chung, phân tích nghiêm ngặt cả hai dạng:

~~~~java
import java.time.LocalDateTime;
import java.time.format.DateTimeFormatter;
import java.time.format.DateTimeFormatterBuilder;
import java.time.format.ResolverStyle;
import java.time.temporal.ChronoField;
import java.util.Locale;

public class OptionalSecondsDemo {
    private static final DateTimeFormatter FORMATTER =
            new DateTimeFormatterBuilder()
                    .appendPattern("uuuu-MM-dd'T'HH:mm")
                    .optionalStart()
                        .appendLiteral(':')
                        .appendValue(ChronoField.SECOND_OF_MINUTE, 2)
                    .optionalEnd()
                    .parseDefaulting(ChronoField.SECOND_OF_MINUTE, 0)
                    .toFormatter(Locale.ROOT)
                    .withResolverStyle(ResolverStyle.STRICT);

    public static void main(String[] args) {
        System.out.println(
                LocalDateTime.parse("2026-11-27T09:30", FORMATTER));
        // 2026-11-27T09:30

        System.out.println(
                LocalDateTime.parse("2026-11-27T09:30:15", FORMATTER));
        // 2026-11-27T09:30:15

        // LocalDateTime.parse("2026-11-27T09:30:99", FORMATTER);
        // DateTimeParseException: giây ngoài miền hợp lệ.
    }
}
~~~~

Cấu trúc của formatter:

1. `appendPattern` đặt các trường bắt buộc.
2. `optionalStart()` và `optionalEnd()` bọc một đoạn có thể không xuất hiện.
3. `appendLiteral(':')` yêu cầu dấu hai chấm nếu đoạn giây xuất hiện.
4. `appendValue(SECOND_OF_MINUTE, 2)` yêu cầu đúng hai chữ số cho trường giây.
5. `parseDefaulting(SECOND_OF_MINUTE, 0)` đặt giây mặc định bằng 0 **nếu trường chưa được parse**.
6. `withResolverStyle(STRICT)` xác nhận giá trị thời gian sau khi parse.

Đây là ví dụ áp dụng “mềm về cấu trúc đã công bố, chặt về giá trị”. Hệ thống chấp nhận **hai dạng cụ thể**, không tự bỏ qua mọi trường còn thiếu hoặc mọi ký tự thừa.

### 8.2. `parseStrict()` của Builder khác `ResolverStyle.STRICT`

Hai API tên giống nhau nhưng kiểm soát **hai giai đoạn khác nhau**:

| API | Ảnh hưởng đến | Ví dụ |
| --- | --- | --- |
| `DateTimeFormatterBuilder.parseStrict()` | **Giai đoạn 1:** đọc ký tự, độ rộng trường, dấu và các quy tắc parsing thuộc builder | Yêu cầu đúng số chữ số của field |
| `DateTimeFormatter.withResolverStyle(STRICT)` | **Giai đoạn 2:** giải quyết và kiểm tra kết hợp các trường thời gian | Từ chối ngày 31/02 |
| `DateTimeFormatterBuilder.parseCaseSensitive()` | Giai đoạn 1, phân biệt hoa/thường | Chữ tháng và literal |
| `DateTimeFormatterBuilder.parseCaseInsensitive()` | Giai đoạn 1, bỏ qua hoa/thường khi parse | Tên tháng hoặc ký hiệu T được công bố |

Builder mặc định có **parse strict** và **case-sensitive** trong giai đoạn 1. Nhưng formatter tạo từ `ofPattern` thông thường vẫn dùng **SMART resolver** trong giai đoạn 2; không được đánh đồng hai thiết lập.

Nếu muốn cho phép tên tháng không phân biệt hoa thường, nhưng vẫn từ chối ngày không tồn tại:

~~~~java
import java.time.LocalDate;
import java.time.format.DateTimeFormatter;
import java.time.format.DateTimeFormatterBuilder;
import java.time.format.ResolverStyle;
import java.util.Locale;

DateTimeFormatter parser = new DateTimeFormatterBuilder()
        .parseCaseInsensitive()
        .appendPattern("d MMM uuuu")
        .toFormatter(Locale.ENGLISH)
        .withResolverStyle(ResolverStyle.STRICT);

System.out.println(LocalDate.parse("27 nOv 2026", parser));
// 2026-11-27

// LocalDate.parse("31 fEb 2026", parser);
// Vẫn lỗi lịch dù đã bỏ qua hoa/thường.
~~~~

`parseCaseInsensitive()` chỉ điều chỉnh **cách đọc cú pháp**, không bỏ qua các kiểm tra của STRICT resolver.

### 8.3. Sử dụng `parseBest` khi dữ liệu có nhiều mức thông tin

Ví dụ muốn nhận ngày đơn lẻ hoặc ngày kèm giờ, rồi xử lý thành **kiểu khác nhau**:

~~~~java
import java.time.LocalDate;
import java.time.LocalDateTime;
import java.time.format.DateTimeFormatter;
import java.time.format.DateTimeFormatterBuilder;
import java.time.format.ResolverStyle;
import java.time.temporal.TemporalAccessor;
import java.util.Locale;

public class ParseBestDemo {
    private static final DateTimeFormatter FORMAT = new DateTimeFormatterBuilder()
            .append(DateTimeFormatter.ISO_LOCAL_DATE)
            .optionalStart()
                .appendLiteral('T')
                .append(DateTimeFormatter.ISO_LOCAL_TIME)
            .optionalEnd()
            .toFormatter(Locale.ROOT)
            .withResolverStyle(ResolverStyle.STRICT);

    static TemporalAccessor parse(String text) {
        return FORMAT.parseBest(
                text, LocalDateTime::from, LocalDate::from);
    }

    public static void main(String[] args) {
        TemporalAccessor a = parse("2026-11-27");
        TemporalAccessor b = parse("2026-11-27T09:30:15");

        System.out.println(a instanceof LocalDate);     // true
        System.out.println(b instanceof LocalDateTime); // true
    }
}
~~~~

`parseBest` thử các truy vấn theo thứ tự từ **dạng có nhiều thông tin nhất** đến dạng tối thiểu. Với trường hợp trên, ưu tiên `LocalDateTime` rồi mới `LocalDate`. Đừng trả lời “tự động hiểu cả hai” bằng cách chỉ gọi `LocalDate.parse` nếu dữ liệu có thể bao gồm giờ; hãy xác định rõ kiểu kết quả cần trả.

### 8.4. `withResolverFields`: dùng cẩn trọng khi có trường thừa

Một formatter có thể parse cả ngày trong tháng, ngày trong năm và thứ trong tuần. Theo mặc định, Java có thể đối chiếu các trường được khai báo xem chúng có nhất quán không.

`withResolverFields(...)` cho phép **lọc tập trường đưa vào giai đoạn giải quyết**. Đây là công cụ nâng cao, hữu ích cho dữ liệu có nhiều cách biểu diễn ngày, nhưng nếu loại bỏ trường đang mâu thuẫn, bạn cũng có thể **vô tình bỏ qua lỗi**.

Không dùng `withResolverFields` như một cách “sửa” input sai. Hãy xác định rõ trường nào là nguồn sự thật, trường nào chỉ dùng để hiển thị hoặc kiểm tra chéo, rồi thiết kế hợp đồng parse nhất quán.

## 9. Parse ngày giờ không đầy đủ: `YearMonth`, `MonthDay` và các giá trị mặc định

Không phải mọi dữ liệu thời gian đều có đủ năm, tháng, ngày, giờ và giây. Ép dữ liệu không đủ thành một kiểu đầy đủ có thể tạo thông tin **không hề được người dùng cung cấp**.

### 9.1. Kỳ sao kê: `YearMonth`

~~~~java
import java.time.YearMonth;
import java.time.format.DateTimeFormatter;
import java.time.format.ResolverStyle;
import java.util.Locale;

DateTimeFormatter period = DateTimeFormatter
        .ofPattern("uuuu-MM", Locale.ROOT)
        .withResolverStyle(ResolverStyle.STRICT);

YearMonth billingPeriod = YearMonth.parse("2026-11", period);
System.out.println(billingPeriod); // 2026-11
System.out.println(billingPeriod.lengthOfMonth()); // 30
~~~~

Nếu user chỉ chọn **tháng/năm**, hãy giữ `YearMonth` thay vì tự gán ngày 01 ở ranh giới input. Khi ứng dụng thực sự cần một ngày bắt đầu kỳ, gọi `billingPeriod.atDay(1)` ở nơi có chính sách đó.

### 9.2. Ngày kỷ niệm không có năm: `MonthDay`

~~~~java
import java.time.MonthDay;

MonthDay anniversary = MonthDay.parse("--02-29");
System.out.println(anniversary); // --02-29
~~~~

`MonthDay` lưu ngày/tháng không có năm, kể cả ngày 29/02 có ý nghĩa trong năm nhuận. Khi cần chuyển thành `LocalDate`, caller phải cung cấp năm và quyết định xử lý trường hợp không hợp lệ trong năm đó. Việc chỉ chọn một năm tùy ý lúc parse là một chính sách ngầm dễ gây lỗi.

### 9.3. Thời gian không có giây và thời gian có mili giây

~~~~java
import java.time.LocalTime;
import java.time.format.DateTimeFormatter;
import java.time.format.ResolverStyle;
import java.util.Locale;

DateTimeFormatter minutes = DateTimeFormatter
        .ofPattern("HH:mm", Locale.ROOT)
        .withResolverStyle(ResolverStyle.STRICT);

LocalTime parsed = LocalTime.parse("09:30", minutes);
System.out.println(parsed); // 09:30
~~~~

Khi input có mili giây cố định, `HH:mm:ss.SSS` là một lựa chọn rõ ràng. Khi cần chính xác đến nano, cân nhắc `DateTimeFormatter.ISO_LOCAL_TIME` hoặc thiết kế pattern/builder theo độ chính xác được phép. Đừng nhầm `SSS` với mili giây như một **field độc lập**: nó là **3 chữ số đầu của phần thập phân giây**.

## 10. Quản lý lỗi với `DateTimeParseException`

`DateTimeParseException` (một loại `DateTimeException`) cung cấp:

- `getParsedString()`: chuỗi đã được truyền vào parse.
- `getErrorIndex()`: vị trí lỗi theo chỉ số của input (có thể là `-1` nếu không xác định được vị trí cụ thể).
- `getMessage()`: mô tả lỗi của thư viện.

Không nên ghi toàn bộ input nhạy cảm vào log hoặc phản hồi HTTP chỉ vì exception chứa thông tin đó. Chuỗi ngày giờ thường không nhạy cảm, nhưng bản ghi có thể chứa ID khách hàng, dữ liệu người dùng hoặc trường khác được ghép vào.

### 10.1. Thông báo lỗi thân thiện nhưng không nuốt lỗi

~~~~java
import java.time.LocalDate;
import java.time.format.DateTimeFormatter;
import java.time.format.DateTimeParseException;
import java.time.format.ResolverStyle;
import java.util.Locale;

public class DateInputValidationDemo {
    private static final DateTimeFormatter INPUT = DateTimeFormatter
            .ofPattern("dd/MM/uuuu", Locale.ROOT)
            .withResolverStyle(ResolverStyle.STRICT);

    static LocalDate parseRequiredDate(String raw) {
        if (raw == null) {
            throw new IllegalArgumentException("date is required");
        }
        if (raw.length() > 64) {
            throw new IllegalArgumentException("date input is too long");
        }

        try {
            return LocalDate.parse(raw, INPUT);
        } catch (DateTimeParseException exception) {
            throw new IllegalArgumentException(
                    "Invalid date; expected dd/MM/yyyy and a real calendar date",
                    exception);
        }
    }

    public static void main(String[] args) {
        System.out.println(parseRequiredDate("27/11/2026"));

        // parseRequiredDate("31/02/2026");
        // IllegalArgumentException được công bố ở ranh giới API.
    }
}
~~~~

Ở ví dụ này, API chọn `IllegalArgumentException` để công bố tiền điều kiện dữ liệu đầu vào và **giữ exception gốc làm cause**. Với UI hoặc API REST, tầng điều phối có thể chuyển nó thành lỗi validation có cấu trúc.

**Không trả giá trị “hợp lệ giả”** như ngày hiện tại, `1970-01-01` hoặc `null` khi parse thất bại nếu hợp đồng không nêu rõ. Làm vậy có thể khiến sự kiện bị lưu sai thời điểm.

### 10.2. Khi nào dùng `Optional` hoặc kiểu kết quả?

Nếu “không tìm thấy ngày” là trường hợp **bình thường và có ý nghĩa**, có thể dùng `Optional<LocalDate>`; nếu input **sai định dạng**, nên phân biệt rõ nó với input vắng mặt.

Ví dụ cách chia:

~~~~java
// API chỉ nhận chuỗi ngày hợp lệ; lỗi thì ném exception.
LocalDate parseRequired(String input);

// API có thể không có trường ngày trong dữ liệu, nhưng khi có
// thì ngày vẫn phải hợp lệ.
Optional<LocalDate> parseOptional(String inputOrNull);
~~~~

Đây là **chữ ký minh họa**, không phải khai báo đầy đủ có thể đặt trực tiếp ở cấp tệp Java. Trong triển khai, `parseOptional` cần quy định null, chuỗi rỗng và các kiểu input được phép vắng mặt; không tự động coi mọi lỗi parse là “không có dữ liệu”.

## 11. Ví dụ tổng hợp: nhận thời gian đặt lịch từ hệ thống bên ngoài

Giả sử một API đặt lịch nhận:

~~~~json
{
  "localDateTime": "2026-11-27T09:30",
  "zoneId": "Asia/Ho_Chi_Minh",
  "durationMinutes": 45
}
~~~~

Hợp đồng đầu vào:

1. `localDateTime` có đúng dạng `uuuu-MM-dd'T'HH:mm` với năm 0001–9999, số ASCII, không có khoảng trắng thừa.
2. Ngày và giờ phải tồn tại trên lịch ISO; không điều chỉnh `SMART`.
3. `zoneId` phải là tên vùng nằm trong tập vùng **hệ thống cho phép**.
4. Thời gian địa phương trong vùng phải ánh xạ đến **đúng một offset** (không gap, không overlap).
5. `durationMinutes` nằm trong khoảng 1–480.
6. Kết quả gồm thời điểm bắt đầu/kết thúc trên trục thời gian tuyệt đối.

Chương trình đầy đủ, lưu thành `AppointmentParserDemo.java`:

~~~~java
import java.time.Duration;
import java.time.Instant;
import java.time.LocalDateTime;
import java.time.ZoneId;
import java.time.ZoneOffset;
import java.time.ZonedDateTime;
import java.time.format.DateTimeFormatter;
import java.time.format.ResolverStyle;
import java.util.List;
import java.util.Locale;
import java.util.Objects;
import java.util.Set;
import java.util.regex.Pattern;

record AppointmentRequest(
        String localDateTime,
        String zoneId,
        int durationMinutes) {
}

record Appointment(
        Instant startsAt,
        Instant endsAt,
        ZoneId zone) {
}

public class AppointmentParserDemo {
    private static final Pattern EXACT_LOCAL_DATE_TIME =
            Pattern.compile(
                    "[0-9]{4}-[0-9]{2}-[0-9]{2}T"
                    + "[0-9]{2}:[0-9]{2}");

    private static final DateTimeFormatter LOCAL_FORMATTER =
            DateTimeFormatter.ofPattern(
                    "uuuu-MM-dd'T'HH:mm", Locale.ROOT)
                    .withResolverStyle(ResolverStyle.STRICT);

    private static final Set<String> ALLOWED_ZONES =
            Set.of("Asia/Ho_Chi_Minh", "Europe/Paris");

    static Appointment parse(AppointmentRequest request) {
        Objects.requireNonNull(request, "request");

        String text = Objects.requireNonNull(
                request.localDateTime(), "localDateTime");
        String zoneText = Objects.requireNonNull(
                request.zoneId(), "zoneId");

        if (!EXACT_LOCAL_DATE_TIME.matcher(text).matches()) {
            throw new IllegalArgumentException(
                    "Expected uuuu-MM-dd'T'HH:mm with ASCII digits");
        }
        if (!ALLOWED_ZONES.contains(zoneText)) {
            throw new IllegalArgumentException("Unsupported zoneId");
        }
        if (request.durationMinutes() < 1
                || request.durationMinutes() > 480) {
            throw new IllegalArgumentException(
                    "durationMinutes must be between 1 and 480");
        }

        LocalDateTime local = LocalDateTime.parse(
                text, LOCAL_FORMATTER);
        if (local.getYear() < 1 || local.getYear() > 9999) {
            throw new IllegalArgumentException("Unsupported year");
        }

        ZoneId zone = ZoneId.of(zoneText);
        List<ZoneOffset> offsets =
                zone.getRules().getValidOffsets(local);

        if (offsets.size() != 1) {
            throw new IllegalArgumentException(
                    "Local time must be valid and unambiguous in zone");
        }

        ZonedDateTime zoned = ZonedDateTime.ofStrict(
                local, offsets.getFirst(), zone);

        Instant startsAt = zoned.toInstant();
        Instant endsAt = startsAt.plus(
                Duration.ofMinutes(request.durationMinutes()));

        return new Appointment(startsAt, endsAt, zone);
    }

    public static void main(String[] args) {
        AppointmentRequest request = new AppointmentRequest(
                "2026-11-27T09:30",
                "Asia/Ho_Chi_Minh",
                45);

        Appointment parsed = parse(request);

        System.out.println(parsed.startsAt());
        // 2026-11-27T02:30:00Z
        System.out.println(parsed.endsAt());
        // 2026-11-27T03:15:00Z
        System.out.println(parsed.zone());
        // Asia/Ho_Chi_Minh
    }
}
~~~~

**Vì sao đoạn code tách các bước?**

- Regex có nhiệm vụ kiểm tra **cú pháp và độ dài** đầu vào.
- `LocalDateTime.parse` với STRICT kiểm tra **ngày giờ thực sự hợp lệ**.
- Danh sách zone cho phép ngăn API nhận mã vùng tùy ý không có trong chính sách ứng dụng.
- `getValidOffsets` kiểm tra thời gian có **ánh xạ duy nhất** trong zone.
- `ZonedDateTime.ofStrict` xác minh cặp local + offset + zone.
- `Instant` giữ kết quả trên **trục thời gian tuyệt đối**, thuận tiện cho lưu trữ, so sánh và thời lượng.
- `Duration.ofMinutes` thể hiện khoảng phút thật trên dòng thời gian, không giả định mọi giờ đồng hồ địa phương đều kéo dài như nhau khi có chuyển DST.

Tùy sản phẩm, thời gian đặt lịch có thể muốn “45 phút thực” hoặc “hết lúc 10:15 theo giờ địa phương”; đây là hai chính sách khác nhau gần ranh giới DST. Ví dụ chọn **thời lượng thực** vì thực hiện cộng trên `Instant`.

**Về exception:** ví dụ để `DateTimeParseException` đi lên trực tiếp nếu ngày giờ sai. Trong dịch vụ HTTP, tầng giao diện nên bắt `DateTimeException` hoặc các exception miền đã công bố, rồi trả phản hồi validation nhất quán. Không trả stack trace hay nội dung nội bộ của exception cho người dùng cuối.

## 12. Các trường hợp biên thường bị bỏ qua

### 12.1. Năm nhuận và ngày cuối tháng

Quy tắc lịch ISO khác với việc chỉ kiểm tra `1 <= day <= 31`. Tháng 4 có 30 ngày; tháng 2 có 28 ngày trong năm thường, 29 ngày trong năm nhuận. Năm chia hết cho 100 không phải năm nhuận trừ khi chia hết cho 400.

Ví dụ với `ResolverStyle.STRICT`:

| Input | Kết quả |
| --- | --- |
| `2024-02-29` | Hợp lệ |
| `2025-02-29` | Bị từ chối |
| `2026-04-31` | Bị từ chối |
| `2000-02-29` | Hợp lệ (chia hết cho 400) |
| `1900-02-29` | Bị từ chối |
| `2026-13-01` | Bị từ chối |
| `2026-00-10` | Bị từ chối |
| `2026-11-00` | Bị từ chối |

Không dùng `DateTimeFormatter.ofPattern("uuuu-MM-dd")` với resolver mặc định SMART nếu nghiệp vụ cần từ chối mọi tổ hợp sai. Cũng không tự viết toàn bộ luật năm nhuận nếu Java đã có `LocalDate` giải quyết.

### 12.2. Giờ 24:00, giây 60 và leap second

Giờ trong ngày theo `HH` thường từ 00 đến 23. Một số chuẩn văn bản có quy tắc riêng cho **24:00** hoặc **leap second**. Không tự giả định formatter tùy chỉnh `HH:mm:ss` sẽ nhận tất cả các biến thể ấy dưới `STRICT`.

Một ví dụ về sự khác nhau giữa chính sách:

~~~~java
import java.time.LocalDateTime;
import java.time.format.DateTimeFormatter;
import java.time.format.ResolverStyle;
import java.util.Locale;

DateTimeFormatter strict = DateTimeFormatter
        .ofPattern("uuuu-MM-dd HH:mm", Locale.ROOT)
        .withResolverStyle(ResolverStyle.STRICT);

// LocalDateTime.parse("2026-11-27 24:00", strict);
// STRICT từ chối giờ 24.

System.out.println(LocalDateTime.parse(
        "2026-11-27 23:59", strict));
// 2026-11-27T23:59
~~~~

`ISO_INSTANT` có quy tắc riêng cho văn bản leap second và có thể cung cấp thông tin qua `DateTimeFormatter.parsedLeapSecond()`. Đây là tình huống chuyên biệt của một chuẩn thời gian, không phải lý do để mở rộng tất cả formatter đầu vào thành lenient.

### 12.3. Số chữ số của nano giây

Nếu một hệ thống truyền mili giây đúng ba chữ số, mẫu `.SSS` có ý nghĩa tương ứng. Nếu nhận thời gian ISO có độ chính xác biến đổi (ví dụ ba, sáu hoặc chín chữ số thập phân), hãy dùng formatter ISO phù hợp hoặc `DateTimeFormatterBuilder.appendFraction` với phạm vi được công bố.

~~~~java
import java.time.LocalTime;
import java.time.format.DateTimeFormatter;

LocalTime time = LocalTime.parse(
        "09:30:15.123456789",
        DateTimeFormatter.ISO_LOCAL_TIME);

System.out.println(time.getNano()); // 123456789
~~~~

Không dùng `double` để biểu diễn số nano giây khi cần chính xác tuyệt đối: `LocalTime` và `Instant` có các trường số nguyên dành cho đơn vị này.

### 12.4. Dữ liệu time zone có thể được cập nhật

`ZoneId` và `ZoneRules` phụ thuộc bộ dữ liệu quy tắc time zone của runtime. Một vùng có thể thay đổi chính sách DST hoặc offset trong tương lai. Nếu hệ thống phải tính lịch hẹn tháng tới, hãy sử dụng một vùng IANA có tên và có chính sách rõ ràng khi quy tắc thay đổi; không thay nó bằng offset cố định chỉ vì hôm nay cả hai cho kết quả giống nhau.

### 12.5. Kiểm tra ngày làm việc và giới hạn nghiệp vụ

STRICT xác nhận **ngày tồn tại**, không tự kiểm tra:

- Ngày không được trước hôm nay (và “hôm nay” của múi giờ nào).
- Lịch hẹn không trùng ngày nghỉ.
- Ngày kết thúc phải sau ngày bắt đầu.
- Giờ đặt lịch phải nằm trong thời gian mở cửa.
- Thời gian vượt hạn mức của tổ chức hay không.

Những điều kiện này nên nằm ở **lớp nghiệp vụ** sau parsing. Đối với quy tắc dựa trên “hiện tại”, nên truyền `Clock` hoặc lấy thời gian từ một nguồn rõ ràng để có thể kiểm thử; không hardcode `LocalDate.now()` ở sâu trong mọi phương thức.

## 13. Kiểm thử formatter và hợp đồng đầu vào

### 13.1. Bảng kiểm thử trường hợp hợp lệ và sai

Ví dụ với một API nhận chuỗi `dd/MM/uuuu` và `ResolverStyle.STRICT`:

| Loại kiểm thử | Input | Kỳ vọng |
| --- | --- | --- |
| Hợp lệ thông thường | `27/11/2026` | Trả `LocalDate.of(2026,11,27)` |
| Ngày nhuận hợp lệ | `29/02/2024` | Được chấp nhận |
| Ngày nhuận không hợp lệ | `29/02/2025` | Bị từ chối |
| Ngày 31 ở tháng 4 | `31/04/2026` | Bị từ chối |
| Tháng 13 | `01/13/2026` | Bị từ chối |
| Thiếu thành phần | `11/2026` | Bị từ chối |
| Dư văn bản | `27/11/2026ABC` | Bị từ chối |
| Thứ tự khác | `2026/11/27` | Bị từ chối |
| Khoảng trắng thừa | ` 27/11/2026 ` | Bị từ chối nếu hợp đồng không cho trim |
| Null | `null` | Exception hoặc kết quả đã công bố |
| Năm ngoài phạm vi nghiệp vụ | `27/11/0000` | Bị từ chối nếu hợp đồng chỉ nhận năm từ 1 |
| Ngày ngoài khoảng đặt chỗ | `01/01/1900` | Được parse nhưng bị từ chối ở bước nghiệp vụ |

Với formatter chỉ dùng STRICT nhưng không yêu cầu chính xác ASCII, một số trường hợp về chiều dài hoặc tập ký tự cần kiểm thử theo pattern cụ thể. Không áp đặt kỳ vọng ASCII lên một formatter đã cấu hình dùng `DecimalStyle` với hệ chữ số khác.

### 13.2. Kiểm thử parsing và formatting đối xứng

Một phép kiểm thử hữu ích là **round-trip**:

~~~~java
LocalDate original = LocalDate.of(2026, 11, 27);
String formatted = BusinessDates.formatDate(original);
LocalDate reparsed = BusinessDates.parseDate(formatted);

System.out.println(original.equals(reparsed)); // true
~~~~

Round-trip chỉ kiểm tra rằng một giá trị có thể format và parse lại với cùng formatter; **không** chứng minh formatter từ chối mọi giá trị sai. Phải có kiểm thử âm (invalid input) riêng.

Với ngày giờ có offset, round-trip có thể giữ cùng một `Instant` nhưng không nhất thiết tái hiện mọi thông tin bản gốc nếu formatter bỏ bớt zone, giây hay phân số giây. Hãy so sánh đúng trường nào nằm trong hợp đồng.

### 13.3. Cố định đồng hồ và vùng trong kiểm thử

~~~~java
import java.time.Clock;
import java.time.Instant;
import java.time.LocalDate;
import java.time.ZoneId;

ZoneId zone = ZoneId.of("Asia/Ho_Chi_Minh");
Clock fixed = Clock.fixed(
        Instant.parse("2026-11-27T02:30:00Z"), zone);

System.out.println(LocalDate.now(fixed)); // 2026-11-27
~~~~

`Clock.fixed` bảo đảm kiểm thử không phụ thuộc ngày hệ thống. Nên truyền `Clock` vào dịch vụ có logic dựa trên thời điểm hiện tại; không thay `Clock` bằng một ngày giờ cố định trong mã production.

### 13.4. Với DST, phải kiểm tra cả gap và overlap

Một bộ kiểm thử cho API lịch hẹn theo vùng nên có:

- Một local time thông thường, có đúng một offset.
- Một local time thuộc **gap**, bị từ chối nếu chính sách yêu cầu tồn tại chính xác.
- Một local time thuộc **overlap**, bị từ chối hoặc yêu cầu offset theo chính sách.
- Một UTC offset do caller cung cấp nhưng **không phù hợp với zone**.
- Một thời điểm vào khoảng cuối năm hoặc ngày nhuận.

Không chỉ kiểm thử một vùng luôn có offset cố định; điều đó bỏ sót rất nhiều lỗi về phân biệt `LocalDateTime` và `Instant`.

## 14. Những lỗi hay gặp khi parse thời gian trong Java

| Sai lầm | Hậu quả | Cách cải thiện |
| --- | --- | --- |
| Dùng `ofPattern` rồi mặc định là nghiêm ngặt | Resolver mặc định SMART có thể chỉnh ngày không tồn tại | `withResolverStyle(STRICT)` |
| Dùng `yyyy` với STRICT nhưng không cung cấp era | Không giải được `YEAR_OF_ERA` thành ngày ISO | Dùng `uuuu` hoặc bổ sung ERA |
| Dùng `YYYY` cho năm lịch | Năm có thể khác gần thời điểm giao thừa | Dùng `uuuu` cho ngày lịch |
| Nhầm `MM` với `mm` | Tháng/phút bị parse sai | Kiểm tra bảng ký hiệu |
| Nhầm `HH` và `hh` | Không phân biệt được giờ 24h và 12h | Với 12h, dùng AM/PM theo hợp đồng |
| Coi `LocalDateTime` là UTC | Thời điểm tuyệt đối bị lệch | Cung cấp offset/zone rõ ràng trước khi tạo Instant |
| Coi offset và `ZoneId` là một | Không xử lý đúng DST hoặc lịch tương lai | Lưu zone IANA khi cần quy tắc vùng |
| Chỉ parse cú pháp mà không kiểm tra gap/overlap | Lịch hẹn bị dời giờ hoặc mơ hồ | Kiểm tra `getValidOffsets`, xác định chính sách |
| Dùng `ZoneId.systemDefault()` tùy tiện | Kết quả khác nhau giữa môi trường | Truyền `ZoneId` qua cấu hình hoặc input có kiểm soát |
| Sử dụng locale mặc định khi parse tên tháng | Input không ổn định giữa máy/ngôn ngữ | Khai báo `Locale` tường minh |
| Tưởng `parseStrict()` của Builder là STRICT resolver | Vẫn cho phép SMART điều chỉnh ngày | Dùng `withResolverStyle(STRICT)` cho phase 2 |
| Tự đổi input sai thành ngày mặc định | Che giấu lỗi và làm sai nghiệp vụ | Trả exception hoặc kiểu kết quả lỗi rõ ràng |
| Trả nguyên văn stack trace và input cho người dùng | Có thể lộ dữ liệu và chi tiết nội bộ | Chuẩn hóa lỗi ở boundary |
| Dùng `LocalDate.now()` trực tiếp trong mọi test | Kiểm thử thay đổi theo ngày hoặc timezone | Truyền `Clock` cố định |
| Ép mọi tháng/năm thành ngày đầu tháng ngay lúc parse | Tạo dữ liệu không được cung cấp | Dùng `YearMonth`, chuyển kiểu ở nơi có chính sách |
| Dùng formatter localized cho giao thức máy–máy | Output không ổn định theo locale/dữ liệu JDK | Dùng định dạng ISO tường minh |

## 15. Checklist thiết kế API nhận thời gian

- [ ] Đã xác định rõ đầu vào đại diện cho `LocalDate`, `LocalDateTime`, `OffsetDateTime`, `ZonedDateTime` hay `Instant`.
- [ ] Đã chọn formatter ISO chuẩn khi phù hợp, hoặc pattern rõ ràng nếu có yêu cầu định dạng riêng.
- [ ] Đã phân biệt `u` / `y` / `Y`, `M` / `m` và `H` / `h`.
- [ ] Dữ liệu lịch phải đúng chính xác có `ResolverStyle.STRICT`.
- [ ] Nếu input cần chiều dài/tập ký tự cố định, đã kiểm tra chúng riêng ngoài resolver.
- [ ] Locale và `DecimalStyle` được lựa chọn theo hợp đồng, không phụ thuộc môi trường.
- [ ] Mọi dữ liệu mang time zone đều có quy tắc về offset, `ZoneId` và DST.
- [ ] Đã xử lý gap/overlap khi chuyển ngày giờ địa phương thành thời điểm tuyệt đối.
- [ ] Các trường tùy chọn được mô tả tường minh bằng `DateTimeFormatterBuilder` và giá trị mặc định nếu cần.
- [ ] Không im lặng thay ngày giờ sai bằng giá trị giả hoặc bỏ qua exception.
- [ ] Đã kiểm tra miền nghiệp vụ, không dừng ở tính hợp lệ trên lịch.
- [ ] Có kiểm thử năm nhuận, ký tự dư, null, locale, vùng giờ, gap và overlap.
- [ ] Đã giới hạn kích thước dữ liệu đầu vào nếu đến từ nguồn không tin cậy.
- [ ] Đã xác định cách ghi log lỗi mà không tiết lộ dữ liệu nhạy cảm.
- [ ] Đã dùng `Clock` cho những quy tắc phụ thuộc “hiện tại” để dễ kiểm thử.

## Tài liệu tham khảo chính thức

- [Java SE 27 – DateTimeFormatter](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/time/format/DateTimeFormatter.html): formatter ISO, ký hiệu pattern, `ofPattern`, `withLocale`, `withZone`, `withResolverStyle`, `parseBest`.
- [Java SE 27 – ResolverStyle](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/time/format/ResolverStyle.html): hai giai đoạn parse, STRICT/SMART/LENIENT.
- [Java SE 27 – DateTimeFormatterBuilder](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/time/format/DateTimeFormatterBuilder.html): `optionalStart`/`optionalEnd`, `parseDefaulting`, `parseStrict`, `parseCaseInsensitive`.
- [Java SE 27 – DateTimeParseException](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/time/format/DateTimeParseException.html): quản lý thông tin lỗi và vị trí.
- [Java SE 27 – ChronoField](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/time/temporal/ChronoField.html): `YEAR` và `YEAR_OF_ERA`.
- [Java SE 27 – ZoneRules](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/time/zone/ZoneRules.html): `getValidOffsets` và các trường hợp DST.
- [Java SE 27 – ZonedDateTime](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/time/ZonedDateTime.html): chuyển đổi giữa local time, offset và region ID.
- [Java SE 27 – Clock](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/time/Clock.html): đồng hồ có thể cấu hình và cố định để kiểm thử.

**Kết luận:** `DateTimeFormatter` không chỉ là công cụ biến một ngày giờ thành chuỗi. Nó là một phần của **hợp đồng dữ liệu thời gian**: kiểm soát cú pháp, lịch, locale, độ chính xác và thông tin time zone. Để parse một cách chặt chẽ trong Java 27, hãy chọn kiểu thời gian đúng, dùng formatter ISO hoặc pattern tường minh với **`ResolverStyle.STRICT`**, kiểm tra các giới hạn nghiệp vụ và xử lý rõ các giờ không tồn tại/mơ hồ tại vùng DST. Nhờ đó, một input trông giống ngày giờ nhưng sai ý nghĩa không bị âm thầm biến thành sự kiện khác.
