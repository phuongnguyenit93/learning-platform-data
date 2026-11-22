# Thứ tự áp dụng `localizedBy`, `withChronology`, `withDecimalStyle` và `withZone`

**Chủ đề:** Locale trong ứng dụng — Java 10 trở lên.

Một đối tượng `DateTimeFormatter` có thể đồng thời mang **ngôn ngữ/vùng**, **hệ lịch**, **quy tắc chữ số** và **múi giờ**. Trong Java 10+, `DateTimeFormatter.localizedBy(Locale)` đọc thêm các Unicode locale extension như `ca`, `nu`, `tz` và `rg`. Vì vậy, **thứ tự gọi `localizedBy` và các phương thức `withChronology`, `withDecimalStyle`, `withZone` có thể thay đổi kết quả cuối cùng**. Đây không phải chỉ là khác biệt thẩm mỹ: năm hiển thị có thể đổi từ 2024 thành 2567, chữ số ASCII có thể thành chữ số Thái, và cùng một `Instant` có thể hiển thị theo Los Angeles hoặc UTC.

**Nguyên tắc dễ áp dụng:** nếu muốn **lựa chọn tường minh của ứng dụng luôn được ưu tiên**, thường hãy gọi `localizedBy(locale)` **trước**, rồi lần lượt cấu hình `withChronology(...)`, `withDecimalStyle(...)` và `withZone(...)`. Nếu muốn **Unicode locale extension chi phối cấu hình cuối cùng**, gọi `localizedBy(locale)` sau các override. Tuy nhiên, không được giản lược thành “lệnh cuối luôn ghi đè tất cả”: **mỗi phương thức chỉ thay đổi những thuộc tính thuộc trách nhiệm của nó**; locale không có khóa `tz` không nhất thiết làm mất zone đã thiết lập.

`localizedBy(Locale)` được giới thiệu ở **Java 10**, vẫn có trong Java hiện đại và được mô tả rõ ở Javadoc Java SE 26. Các chương trình độc lập trong bài đã biên dịch bằng `javac --release 10` và chạy trên **JDK 24.0.2**. Các tên ID múi giờ, mẫu định dạng bản địa hóa và dữ liệu lịch có thể phụ thuộc bộ dữ liệu CLDR/TZDB của runtime, vì thế bài phân biệt **hợp đồng API** với **stdout trong môi trường kiểm thử**.

## 1. Bốn thao tác, bốn phần trạng thái

`DateTimeFormatter` là đối tượng **immutable**: mỗi phương thức cấu hình trả về một formatter mới, không sửa formatter gốc. Những phần trạng thái cần theo dõi là:

| Thao tác | Thuộc tính trực tiếp | Getter kiểm tra | Tác động điển hình |
| --- | --- | --- | --- |
| `localizedBy(Locale)` | Locale và các giá trị bản địa hóa phù hợp, gồm lịch, hệ chữ số, vùng và múi giờ | `getLocale()`, `getChronology()`, `getDecimalStyle()`, `getZone()` | Có thể thay nhiều thuộc tính cùng lúc |
| `withChronology(Chronology)` | Override chronology | `getChronology()` | Chuyển hệ lịch khi định dạng/parsing ngày |
| `withDecimalStyle(DecimalStyle)` | Bộ ký hiệu số, dấu âm/dương, dấu phân cách thập phân | `getDecimalStyle()` | Thay cách trình bày và đọc các chữ số/số |
| `withZone(ZoneId)` | Override zone | `getZone()` | Chọn múi giờ khi định dạng `Instant`/parsing cần zone |

Phân biệt thêm `withLocale(Locale)`:

~~~java
DateTimeFormatter a = formatter.withLocale(locale);
DateTimeFormatter b = formatter.localizedBy(locale);
~~~

Đây là **hai dòng minh họa trong một phương thức** có biến `formatter` và `locale`. `withLocale` chủ yếu lưu locale cho việc tìm mẫu/văn bản bản địa hóa; **nó không tương đương với `localizedBy`** về áp dụng chronology, decimal style và time zone từ Unicode extension. Javadoc cũng nêu rõ `localizedBy` có thể cho kết quả khác tùy thứ tự gọi với các phương thức `withXXXX`.

### Ví dụ một Locale có cả ba tùy chọn

~~~java
Locale preferences = Locale.forLanguageTag(
        "en-US-u-ca-buddhist-nu-thai-tz-uslax");
~~~

Đây là đoạn minh họa trong method, cần import `java.util.Locale`.

- `en-US`: ngôn ngữ tiếng Anh, vùng Hoa Kỳ.
- `ca-buddhist`: ưu tiên lịch Phật giáo (**ThaiBuddhist** chronology trong Java).
- `nu-thai`: ưu tiên hệ chữ số Thái; chữ số 0 là `๐` (U+0E50), khác ASCII `0` (U+0030).
- `tz-uslax`: ưu tiên múi giờ Los Angeles qua **mã ngắn CLDR**; formatter kiểm thử giải ra `America/Los_Angeles`.
- Các lựa chọn này **độc lập** với nhau: tiếng Anh không bắt buộc phải dùng lịch ISO, chữ số Latin hoặc UTC.

Lưu ý: khóa `tz` chứa **CLDR short ID**, không phải nguyên chuỗi IANA `America/Los_Angeles`. Khi ứng dụng đã có `ZoneId` rõ ràng, `withZone(ZoneId.of("America/Los_Angeles"))` là cách cấu hình zone tường minh, không cần tự chuyển mã ngắn bằng `ZoneId.of("uslax")`.

## 2. Quy tắc ưu tiên khi thay đổi thứ tự

Xét hai chuỗi gọi với cùng formatter gốc:

~~~java
DateTimeFormatter localeLast = base
        .withChronology(IsoChronology.INSTANCE)
        .withDecimalStyle(DecimalStyle.STANDARD)
        .withZone(ZoneId.of("UTC"))
        .localizedBy(preferences);

DateTimeFormatter explicitLast = base
        .localizedBy(preferences)
        .withChronology(IsoChronology.INSTANCE)
        .withDecimalStyle(DecimalStyle.STANDARD)
        .withZone(ZoneId.of("UTC"));
~~~

Đây là **đoạn minh họa trong method**; `base` là `DateTimeFormatter` và `preferences` là Locale có `ca-buddhist`, `nu-thai`, `tz-uslax`. Cần import `DateTimeFormatter`, `IsoChronology`, `DecimalStyle` và `ZoneId`.

Trong ví dụ này, các thuộc tính có **xung đột tường minh**:

| Thuộc tính | Bước explicit chọn | Extension chọn | `localeLast` | `explicitLast` |
| --- | --- | --- | --- | --- |
| Chronology | `IsoChronology.INSTANCE` | `ca-buddhist` | ThaiBuddhist | ISO |
| Chữ số | `DecimalStyle.STANDARD` | `nu-thai` | Chữ số Thái | Chữ số Latin/ASCII |
| Múi giờ | `UTC` | `tz-uslax` | Los Angeles | UTC |

Không phải chỉ thay đổi tên đối tượng: khi định dạng `2024-01-15T12:00:00Z`, `localeLast` có thể cho năm Phật lịch **2567**, chữ số Thái và **04:00 -08:00**, còn `explicitLast` cho năm ISO **2024**, chữ số ASCII và **12:00 Z**.

**Giải thích cơ chế:**

1. `withChronology`, `withDecimalStyle`, `withZone` luôn trả một formatter mới với giá trị override được yêu cầu, giữ nguyên các cấu hình không liên quan.
2. `localizedBy` áp dụng thông tin bản địa hóa từ locale, bao gồm `ca`, `nu`, `tz` hợp lệ; vì vậy nó có thể **thay những override đã chọn ở bước trước**.
3. Khi các phương thức explicit được gọi **sau `localizedBy`**, chúng lại thay đúng thuộc tính của mình; Locale trong formatter vẫn có thể chứa các extension cũ.
4. **Không suy diễn** rằng mọi `localizedBy` luôn thay cả ba thuộc tính: kết quả còn tùy extension, locale và dữ liệu provider. Thứ tự quan trọng nhất khi **hai thao tác cùng muốn đặt một thuộc tính**.

### Chương trình chạy được 1 — Ma trận thứ tự tổng hợp

Lưu **`FormatterOrderMatrixDemo.java`**:

~~~java
import java.time.Instant;
import java.time.ZoneId;
import java.time.chrono.IsoChronology;
import java.time.format.DateTimeFormatter;
import java.time.format.DecimalStyle;
import java.util.Locale;

public class FormatterOrderMatrixDemo {
    static String details(DateTimeFormatter formatter) {
        String chronology = formatter.getChronology() == null
                ? "none" : formatter.getChronology().getId();
        String digits = formatter.getDecimalStyle().getZeroDigit() == '\u0E50'
                ? "thai" : "latin";
        String zone = formatter.getZone() == null
                ? "none" : formatter.getZone().getId();
        return chronology + "/" + digits + "/" + zone;
    }

    public static void main(String[] args) {
        Locale preferences = Locale.forLanguageTag(
                "en-US-u-ca-buddhist-nu-thai-tz-uslax");
        DateTimeFormatter base = DateTimeFormatter.ofPattern(
                "uuuu-MM-dd HH:mm XXX", Locale.US);
        Instant when = Instant.parse("2024-01-15T12:00:00Z");

        DateTimeFormatter explicitFirst = base
                .withChronology(IsoChronology.INSTANCE)
                .withDecimalStyle(DecimalStyle.STANDARD)
                .withZone(ZoneId.of("UTC"))
                .localizedBy(preferences);

        DateTimeFormatter explicitLast = base
                .localizedBy(preferences)
                .withChronology(IsoChronology.INSTANCE)
                .withDecimalStyle(DecimalStyle.STANDARD)
                .withZone(ZoneId.of("UTC"));

        System.out.println("explicit-first=" + details(explicitFirst));
        System.out.println("explicit-last=" + details(explicitLast));
        System.out.println("first-text=" + explicitFirst.format(when));
        System.out.println("last-text=" + explicitLast.format(when));
        System.out.println("base-unchanged=" + details(base));
        System.out.println("withLocale-only=" +
                details(base.withLocale(preferences)));
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac --release 10 FormatterOrderMatrixDemo.java
java FormatterOrderMatrixDemo
~~~

**Stdout đã kiểm tra trên JDK 24.0.2:**

~~~text
explicit-first=ThaiBuddhist/thai/America/Los_Angeles
explicit-last=ISO/latin/UTC
first-text=๒๕๖๗-๐๑-๑๕ ๐๔:๐๐ -08:00
last-text=2024-01-15 12:00 Z
base-unchanged=none/latin/none
withLocale-only=none/latin/none
~~~

Kết quả chứng minh rõ **thứ tự quan trọng**. Trong chuỗi thứ nhất, dữ liệu locale ghi đè các cấu hình explicit đặt trước. Trong chuỗi thứ hai, ba cấu hình explicit đặt sau cùng lại thắng. `base` không đổi vì `DateTimeFormatter` bất biến. `withLocale(preferences)` riêng lẻ không tạo override chronology/zone/chữ số như `localizedBy`.

Mẫu `uuuu-MM-dd HH:mm XXX` được chọn chủ ý: `uuuu` thể hiện năm proleptic theo chronology đang dùng, `HH:mm` là giờ/phút, `XXX` là offset. **Đừng dùng `yyyy` mà mặc nhiên nghĩ luôn tương đương `uuuu`**; `yyyy` là *year-of-era* và có quy tắc khác khi kỷ nguyên thay đổi.

## 3. `withChronology` trước hay sau `localizedBy`?

`withChronology(Chronology)` đặt **override chronology**. Khi định dạng một đối tượng có ngày (ví dụ `LocalDate`), formatter có thể chuyển ngày đó sang hệ lịch được chỉ định. Khi parse, chronology cũng ảnh hưởng cách giải quyết các trường ngày.

Ví dụ chọn `ca-buddhist` nhưng trong ứng dụng muốn giữ năm ISO:

~~~java
DateTimeFormatter buddhistWins = base
        .withChronology(IsoChronology.INSTANCE)
        .localizedBy(Locale.forLanguageTag("en-US-u-ca-buddhist"));

DateTimeFormatter isoWins = base
        .localizedBy(Locale.forLanguageTag("en-US-u-ca-buddhist"))
        .withChronology(IsoChronology.INSTANCE);
~~~

Đây là đoạn trong method với `base` là DateTimeFormatter và import thích hợp. Theo kết quả kiểm thử, `buddhistWins` có chronology `ThaiBuddhist`, còn `isoWins` có chronology `ISO`.

**Lưu ý về năm:** với ngày ISO `2024-01-15`, lịch Phật giáo được Java dùng trong ví dụ có năm 2567. Đây là **biểu diễn lịch khác của cùng một ngày**, không có nghĩa thời điểm vật lý tăng 543 năm. Nếu ứng dụng lưu giao dịch hoặc timestamp, cần phân biệt **lịch dùng hiển thị** với giá trị thời gian được lưu.

### Chương trình chạy được 2 — Thứ tự chronology và parsing

Lưu **`ChronologyOrderDemo.java`**:

~~~java
import java.time.LocalDate;
import java.time.chrono.IsoChronology;
import java.time.format.DateTimeFormatter;
import java.util.Locale;

public class ChronologyOrderDemo {
    public static void main(String[] args) {
        Locale buddhist = Locale.forLanguageTag("en-US-u-ca-buddhist");
        DateTimeFormatter base = DateTimeFormatter.ofPattern(
                "uuuu-MM-dd", Locale.US);

        DateTimeFormatter isoFirst = base
                .withChronology(IsoChronology.INSTANCE)
                .localizedBy(buddhist);
        DateTimeFormatter isoLast = base
                .localizedBy(buddhist)
                .withChronology(IsoChronology.INSTANCE);

        LocalDate date = LocalDate.of(2024, 1, 15);
        System.out.println("first-chronology=" +
                isoFirst.getChronology().getId());
        System.out.println("last-chronology=" +
                isoLast.getChronology().getId());
        System.out.println("first-year=" + isoFirst.format(date));
        System.out.println("last-year=" + isoLast.format(date));
        System.out.println("first-parse=" +
                LocalDate.parse(isoFirst.format(date), isoFirst));
        System.out.println("last-parse=" +
                LocalDate.parse(isoLast.format(date), isoLast));
    }
}
~~~

Chạy:

~~~bash
javac --release 10 ChronologyOrderDemo.java
java ChronologyOrderDemo
~~~

**Stdout đã kiểm tra:**

~~~text
first-chronology=ThaiBuddhist
last-chronology=ISO
first-year=2567-01-15
last-year=2024-01-15
first-parse=2024-01-15
last-parse=2024-01-15
~~~

Giải thích:

- `isoFirst`: `localizedBy` gọi sau đã áp dụng `ca-buddhist`, vì thế năm hiển thị là 2567.
- `isoLast`: `withChronology(IsoChronology.INSTANCE)` gọi sau nên năm hiển thị theo ISO là 2024.
- `LocalDate.parse(...)` ở cả hai nhánh cho **cùng ngày ISO `2024-01-15`** khi parse bằng đúng formatter đã dùng để tạo text. Đây không phải phép cộng/trừ năm tùy tiện: chronology giải quyết ngày lịch đúng rồi chuyển sang `LocalDate`.
- **Không parse một chuỗi 2567 bằng formatter ISO rồi cho rằng tương đương năm 2024**. Trong hệ thống trao đổi dữ liệu, phải thống nhất chronology và dạng text được chấp nhận.

Với định dạng ngày hiển thị cho người dùng, `ca` có thể là preference có ý nghĩa. Với dữ liệu lưu trữ chuẩn hóa hoặc API yêu cầu lịch ISO, explicit `withChronology(IsoChronology.INSTANCE)` nên được áp dụng **sau** `localizedBy`.

## 4. `withDecimalStyle` trước hay sau `localizedBy`?

`DecimalStyle` chứa những ký hiệu dùng khi xử lý số trong formatter: chữ số 0, dấu dương/âm và dấu phân cách thập phân. `DecimalStyle.STANDARD` dùng chữ số Latin/ASCII; một locale có `nu-thai` có thể chọn chữ số Thái:

~~~java
Locale thaiDigits = Locale.forLanguageTag("en-US-u-nu-thai");

DateTimeFormatter thaiWins = base
        .withDecimalStyle(DecimalStyle.STANDARD)
        .localizedBy(thaiDigits);

DateTimeFormatter latinWins = base
        .localizedBy(thaiDigits)
        .withDecimalStyle(DecimalStyle.STANDARD);
~~~

Đây là đoạn minh họa trong method với `base` là DateTimeFormatter. Hai formatter vẫn dùng cùng ngôn ngữ `en-US`, nhưng **các ký hiệu chữ số** được chọn khác nhau.

Lưu ý phân biệt:

- `getDecimalStyle().getZeroDigit()` trả ký tự 0 theo style, ví dụ `๐` hoặc `0`.
- `withDecimalStyle` thay **kiểu ký hiệu số**, không tự đổi hệ lịch hoặc múi giờ.
- `withChronology` quyết định **giá trị năm theo lịch**, còn `withDecimalStyle` quyết định **cách biểu diễn chữ số của năm đó**.
- Dấu offset trong mẫu `XXX` có thể vẫn thể hiện theo cú pháp offset ISO thông thường ngay khi các trường ngày/giờ dùng chữ số bản địa hóa; không dựa vào một hình thức chữ số duy nhất cho **mọi** thành phần text.
- Cả định dạng và **parsing** phải dùng đúng decimal style nếu văn bản chứa chữ số bản địa hóa. Đừng mặc định formatter đang nhận chữ số Latin có thể parse cùng một chuỗi chữ số Thái.

### Chương trình chạy được 3 — Thứ tự decimal style và parsing

Lưu **`DecimalStyleOrderDemo.java`**:

~~~java
import java.time.LocalDate;
import java.time.format.DateTimeFormatter;
import java.time.format.DecimalStyle;
import java.util.Locale;

public class DecimalStyleOrderDemo {
    public static void main(String[] args) {
        Locale thaiDigits = Locale.forLanguageTag("en-US-u-nu-thai");
        DateTimeFormatter base = DateTimeFormatter.ofPattern(
                "uuuu-MM-dd", Locale.US);

        DateTimeFormatter standardFirst = base
                .withDecimalStyle(DecimalStyle.STANDARD)
                .localizedBy(thaiDigits);
        DateTimeFormatter standardLast = base
                .localizedBy(thaiDigits)
                .withDecimalStyle(DecimalStyle.STANDARD);

        LocalDate date = LocalDate.of(2024, 1, 15);
        System.out.println("first-zero=" +
                Integer.toHexString(standardFirst.getDecimalStyle().getZeroDigit()));
        System.out.println("last-zero=" +
                Integer.toHexString(standardLast.getDecimalStyle().getZeroDigit()));
        System.out.println("first-text=" + standardFirst.format(date));
        System.out.println("last-text=" + standardLast.format(date));
        System.out.println("thai-parse=" +
                LocalDate.parse(standardFirst.format(date), standardFirst));
    }
}
~~~

Biên dịch/chạy:

~~~bash
javac --release 10 DecimalStyleOrderDemo.java
java DecimalStyleOrderDemo
~~~

**Stdout đã kiểm tra:**

~~~text
first-zero=e50
last-zero=30
first-text=๒๐๒๔-๐๑-๑๕
last-text=2024-01-15
thai-parse=2024-01-15
~~~

`Integer.toHexString` in giá trị code unit của ký tự zero digit: `e50` tương ứng U+0E50 (số 0 tiếng Thái), còn `30` tương ứng U+0030 (ASCII zero). Như vậy bài không chỉ suy luận từ hình dáng chữ số trên màn hình.

**Hai lựa chọn khác nhau:** nếu UI cần số theo sở thích của người dùng, dùng `localizedBy` sau `DecimalStyle.STANDARD` hoặc không đặt override tường minh khi không cần. Nếu dữ liệu xuất ra API bắt buộc ASCII, đặt `withDecimalStyle(DecimalStyle.STANDARD)` **sau** `localizedBy`.

## 5. `withZone` trước hay sau `localizedBy`?

`withZone(ZoneId)` đặt **override zone**. Khi định dạng một `Instant`, formatter chuyển thời điểm tuyệt đối sang giờ địa phương của zone đó. Java 10+ có thể nhận `tz` từ Locale qua `localizedBy`:

~~~java
Locale la = Locale.forLanguageTag("en-US-u-tz-uslax");

DateTimeFormatter localeZoneWins = base
        .withZone(ZoneId.of("UTC"))
        .localizedBy(la);

DateTimeFormatter utcWins = base
        .localizedBy(la)
        .withZone(ZoneId.of("UTC"));
~~~

Đây là đoạn trong method với formatter `base` dùng mẫu ngày–giờ phù hợp. Với `tz-uslax` được JDK hỗ trợ, `localeZoneWins.getZone()` trả Los Angeles, còn `utcWins.getZone()` trả UTC.

Thời điểm `2024-01-15T12:00:00Z` được hiển thị:

- Tại Los Angeles ngày 15/01/2024: **04:00 -08:00**.
- Tại UTC: **12:00 Z**.

Sang tháng 7 năm 2024, Los Angeles dùng **-07:00** do DST. Vì vậy `withZone(ZoneOffset.of("-08:00"))` **không tương đương lâu dài** với `withZone(ZoneId.of("America/Los_Angeles"))`. Dùng `ZoneId` cho quy tắc vùng, `Instant` cho sự kiện, và kiểm tra DST với ngày cố định.

### Chương trình chạy được 4 — Thứ tự zone, DST, `withLocale`

Lưu **`ZoneOrderDemo.java`**:

~~~java
import java.time.Instant;
import java.time.ZoneId;
import java.time.format.DateTimeFormatter;
import java.util.Locale;

public class ZoneOrderDemo {
    public static void main(String[] args) {
        Locale losAngeles = Locale.forLanguageTag("en-US-u-tz-uslax");
        DateTimeFormatter base = DateTimeFormatter.ofPattern(
                "uuuu-MM-dd HH:mm XXX", Locale.US);

        DateTimeFormatter utcFirst = base.withZone(ZoneId.of("UTC"))
                .localizedBy(losAngeles);
        DateTimeFormatter utcLast = base.localizedBy(losAngeles)
                .withZone(ZoneId.of("UTC"));

        Instant winter = Instant.parse("2024-01-15T12:00:00Z");
        Instant summer = Instant.parse("2024-07-15T12:00:00Z");

        System.out.println("first-zone=" + utcFirst.getZone());
        System.out.println("last-zone=" + utcLast.getZone());
        System.out.println("winter-first=" + utcFirst.format(winter));
        System.out.println("summer-first=" + utcFirst.format(summer));
        System.out.println("winter-last=" + utcLast.format(winter));
        System.out.println("withLocale-zone=" +
                base.withLocale(losAngeles).getZone());
    }
}
~~~

Chạy:

~~~bash
javac --release 10 ZoneOrderDemo.java
java ZoneOrderDemo
~~~

**Stdout đã kiểm tra:**

~~~text
first-zone=America/Los_Angeles
last-zone=UTC
winter-first=2024-01-15 04:00 -08:00
summer-first=2024-07-15 05:00 -07:00
winter-last=2024-01-15 12:00 Z
withLocale-zone=null
~~~

**Hai kết luận chính:** (1) `withZone(UTC)` đặt sau `localizedBy` sẽ thắng đối với override zone; (2) `withLocale(losAngeles)` đơn thuần không thiết lập override zone ở đây. Không nên dùng `Locale.getCountry()` để phỏng đoán vùng giờ của người dùng, vì nhiều quốc gia có nhiều múi giờ và các lựa chọn của người dùng có thể khác nơi họ đang ở.

## 6. Không có Unicode extension không đồng nghĩa “không có thay đổi nào”

Một bẫy khi khái quát hóa **“cái gọi cuối luôn thắng”**: `localizedBy(Locale)` lấy các giá trị **phù hợp với locale**. Một Locale **không** có `tz` không nhất thiết thay thế zone đang có; nhưng chronology và decimal style có thể được lấy lại từ cấu hình bản địa hóa mặc định.

Trong JDK 24.0.2 được kiểm tra, gọi `localizedBy(Locale.US)` trên formatter trước đó có **Japanese chronology**, **chữ số Ả Rập** và **UTC zone** cho kết quả:

- Chronology trở về **ISO**.
- Ký hiệu zero digit trở về **ASCII `0`**.
- Override zone **vẫn là UTC**, do Locale.US không đưa ra lựa chọn `tz` để thay thế.

Trong khi đó, `withLocale(Locale.US)` chỉ thay locale, giữ nguyên chronology, decimal style và zone của formatter ví dụ.

**Điểm rút ra:** không viết một hàm tự đoán “localizedBy luôn reset toàn bộ” hoặc “localizedBy không có extension chắc chắn là no-op”. Hãy dựa trên Javadoc và các giá trị thực tế của `getChronology()`, `getDecimalStyle()`, `getZone()`; với dữ liệu locale khác nhau, hành vi chi tiết có thể thay đổi theo provider/phiên bản JDK.

### Chương trình chạy được 5 — Locale không có `ca`, `nu`, `tz`

Lưu **`LocaleWithoutExtensionsDemo.java`**:

~~~java
import java.time.ZoneId;
import java.time.chrono.JapaneseChronology;
import java.time.format.DateTimeFormatter;
import java.time.format.DecimalStyle;
import java.util.Locale;

public class LocaleWithoutExtensionsDemo {
    public static void main(String[] args) {
        Locale english = Locale.US;
        DecimalStyle arabicDigits = DecimalStyle.STANDARD
                .withZeroDigit('\u0660');
        DateTimeFormatter base = DateTimeFormatter.ofPattern(
                "uuuu-MM-dd", Locale.US)
                .withChronology(JapaneseChronology.INSTANCE)
                .withDecimalStyle(arabicDigits)
                .withZone(ZoneId.of("UTC"));

        DateTimeFormatter localized = base.localizedBy(english);
        DateTimeFormatter onlyLocale = base.withLocale(english);

        System.out.println("localized-chronology=" +
                localized.getChronology().getId());
        System.out.println("localized-zero=" +
                Integer.toHexString(localized.getDecimalStyle().getZeroDigit()));
        System.out.println("localized-zone=" + localized.getZone());
        System.out.println("withLocale-chronology=" +
                onlyLocale.getChronology().getId());
        System.out.println("withLocale-zero=" +
                Integer.toHexString(onlyLocale.getDecimalStyle().getZeroDigit()));
        System.out.println("withLocale-zone=" + onlyLocale.getZone());
    }
}
~~~

Lệnh:

~~~bash
javac --release 10 LocaleWithoutExtensionsDemo.java
java LocaleWithoutExtensionsDemo
~~~

**Stdout trên JDK kiểm thử:**

~~~text
localized-chronology=ISO
localized-zero=30
localized-zone=UTC
withLocale-chronology=Japanese
withLocale-zero=660
withLocale-zone=UTC
~~~

`660` ở đây là biểu diễn hex của U+0660 (chữ số 0 kiểu Arabic-Indic), trong khi `30` là ASCII zero. Chương trình dùng `JapaneseChronology.INSTANCE` để làm rõ sự khác biệt về chronology; không khuyến nghị tùy tiện gắn lịch Nhật cho dữ liệu US.

**Vì sao không chỉ kiểm tra `getLocale()`?** Hai formatter có thể có cùng `getLocale()==Locale.US` mà mang chronology, decimal style hoặc zone khác nhau. Việc truy nguyên “locale hiện là gì” **không** thay thế kiểm tra các override thực tế.

## 7. Thiết kế một pipeline định dạng dùng trong ứng dụng

Trong ứng dụng thật, thường có **hai nguồn quyết định**:

1. **Sở thích bản địa hóa** từ người dùng: ngôn ngữ, calendar `ca`, numbering system `nu`, timezone `tz`.
2. **Hợp đồng của màn hình/API**: chẳng hạn luôn xuất năm ISO, chữ số Latin và giờ theo `ZoneId` IANA đã chọn tường minh.

Khi một màn hình/API có quy tắc **tường minh phải thắng các tùy chọn từ Locale**, cấu hình theo thứ tự:

~~~java
DateTimeFormatter formatter = DateTimeFormatter
        .ofPattern("uuuu-MM-dd HH:mm XXX", Locale.US)
        .localizedBy(userLocale)
        .withChronology(IsoChronology.INSTANCE)
        .withDecimalStyle(DecimalStyle.STANDARD)
        .withZone(userZone);
~~~

Đây là **đoạn mã trong một phương thức**, `userLocale` có kiểu `Locale` và `userZone` có kiểu `ZoneId`. Sau khi gọi `localizedBy`, đặt mỗi override explicit cần thiết. Nếu domain **muốn tôn trọng calendar/numbering/timezone từ Locale**, thì **đừng gọi override trái ngược sau đó**, hoặc hãy chỉ override những thuộc tính mà hợp đồng đòi hỏi.

Tránh gọi `localizedBy` lại ở một tầng sau khi đã quyết định explicit overrides mà không chủ định áp dụng lại locale preferences. Nếu cần cập nhật locale trong pipeline, hãy tạo một formatter mới từ một base được quản lý rõ, áp dụng locale trước rồi override theo chính sách cuối cùng.

### Chương trình chạy được 6 — Cấu hình cho hai người dùng

Lưu **`UserPreferenceFormatterDemo.java`**:

~~~java
import java.time.Instant;
import java.time.ZoneId;
import java.time.format.DateTimeFormatter;
import java.time.format.DecimalStyle;
import java.time.chrono.IsoChronology;
import java.util.Locale;

public class UserPreferenceFormatterDemo {
    static DateTimeFormatter build(Locale locale, ZoneId zone) {
        return DateTimeFormatter
                .ofPattern("uuuu-MM-dd HH:mm XXX", Locale.US)
                .localizedBy(locale)
                .withChronology(IsoChronology.INSTANCE)
                .withDecimalStyle(DecimalStyle.STANDARD)
                .withZone(zone);
    }

    public static void main(String[] args) {
        Locale locale = Locale.forLanguageTag(
                "vi-VN-u-ca-buddhist-nu-thai-tz-uslax");
        ZoneId before = ZoneId.systemDefault();
        Instant when = Instant.parse("2024-07-15T12:00:00Z");

        DateTimeFormatter forVietnam = build(
                locale, ZoneId.of("Asia/Ho_Chi_Minh"));
        DateTimeFormatter forLosAngeles = build(
                locale, ZoneId.of("America/Los_Angeles"));

        System.out.println("vietnam=" + forVietnam.format(when));
        System.out.println("los-angeles=" + forLosAngeles.format(when));
        System.out.println("iso-chronology=" +
                forVietnam.getChronology().getId());
        System.out.println("ascii-digits=" +
                (forVietnam.getDecimalStyle().getZeroDigit() == '0'));
        System.out.println("locale-has-tz=" +
                forVietnam.getLocale().getUnicodeLocaleType("tz"));
        System.out.println("system-default-unchanged=" +
                before.equals(ZoneId.systemDefault()));
        System.out.println("instant-roundtrip=" +
                Instant.from(forVietnam.parse(
                        forVietnam.format(when))).equals(when));
    }
}
~~~

Biên dịch/chạy:

~~~bash
javac --release 10 UserPreferenceFormatterDemo.java
java UserPreferenceFormatterDemo
~~~

**Stdout đã kiểm tra:**

~~~text
vietnam=2024-07-15 19:00 +07:00
los-angeles=2024-07-15 05:00 -07:00
iso-chronology=ISO
ascii-digits=true
locale-has-tz=uslax
system-default-unchanged=true
instant-roundtrip=true
~~~

Ở đây Locale vẫn chứa `tz=uslax`, `ca=buddhist` và `nu=thai`, nhưng **hợp đồng formatter sau cùng** là ISO, ASCII và `ZoneId` cụ thể vì các override được gọi **sau `localizedBy`**. Do đó `forVietnam.getLocale().getUnicodeLocaleType("tz")` vẫn in `uslax`, trong khi **zone thực tế của formatter Việt Nam là `Asia/Ho_Chi_Minh`**. Đọc mỗi tag Locale không đủ biết formatter cuối cùng đang dùng gì.

Bài kiểm tra roundtrip dùng một `Instant` với phút và giây bằng 0, tương thích độ chính xác của mẫu định dạng `uuuu-MM-dd HH:mm XXX`. Nếu định dạng bỏ phần giây nhưng input chứa giây/millisecond khác 0, parse lại sẽ không thể giữ nguyên toàn bộ độ chính xác. **Không suy ra “parse(format(x)) luôn bằng x” với mọi pattern và dữ liệu**.

## 8. `localizedBy` và việc parse: cùng thứ tự, nhưng ngữ nghĩa cần hiểu

Chủ đề này không chỉ ảnh hưởng `format`. `DateTimeFormatter` cũng được dùng để **parse** văn bản:

- **Override chronology** ảnh hưởng cách các trường năm–tháng–ngày được kết hợp thành một ngày. Ví dụ văn bản năm Phật lịch 2567 không được hiểu theo cùng nghĩa với năm ISO 2567.
- **Decimal style** ảnh hưởng khả năng đọc chữ số và ký hiệu số bản địa hóa. Văn bản có số Thái không nên parse bằng bộ quy tắc chỉ chấp nhận chữ số ASCII nếu bạn chưa chuyển đổi hợp lệ.
- **Override zone** được dùng trong quá trình parse nếu văn bản không chứa zone đầy đủ, hoặc để giải quyết một thời điểm theo quy tắc phù hợp. Nếu văn bản chứa zone được parse tường minh, Javadoc có quy tắc riêng về tác động của override zone; **không khẳng định `withZone` luôn ghi đè mọi zone đã có trong văn bản**.
- **Ngôn ngữ/locale** cũng có thể ảnh hưởng tên tháng, tên ngày, mẫu định dạng và các dữ liệu được bản địa hóa.

Một ví dụ hợp lệ:

~~~java
DateTimeFormatter th = DateTimeFormatter.ofPattern(
        "uuuu-MM-dd", Locale.US)
        .localizedBy(Locale.forLanguageTag("en-US-u-nu-thai"));

LocalDate parsed = LocalDate.parse("๒๐๒๔-๐๑-๑๕", th);
~~~

Đây là **đoạn mã trong method**, cần import `LocalDate`, `DateTimeFormatter` và `Locale`. Kết quả trong kiểm thử là `LocalDate.of(2024,1,15)`.

Khi dữ liệu trao đổi giữa các hệ thống, nên **quy định định dạng và chronology rõ ràng**, không cho locale preference ngẫu nhiên thay thế hợp đồng serialization. Với timestamp, ưu tiên một định dạng máy đọc chuẩn và múi giờ/offset được xác định thay vì dùng text bản địa hóa cho mục đích lưu trữ.

## 9. Kiểm tra đúng thuộc tính sau chuỗi cấu hình

Đừng chỉ nhìn chuỗi đã format rồi đoán vì sao nó khác. Các getter là công cụ kiểm tra nhanh:

~~~java
Locale locale = formatter.getLocale();
Chronology chronology = formatter.getChronology();
DecimalStyle style = formatter.getDecimalStyle();
ZoneId zone = formatter.getZone();
~~~

Đây là **đoạn trong method** với import phù hợp. Kết quả `getChronology()` hoặc `getZone()` có thể là `null` nếu formatter không đặt override. **`null` ở getter không có nghĩa Java không có chronology hay múi giờ mặc định**; nó chỉ có nghĩa không có override lưu ở formatter đó.

Với JUnit hoặc công cụ kiểm thử, có thể assert:

~~~java
assertEquals(IsoChronology.INSTANCE, formatter.getChronology());
assertEquals('0', formatter.getDecimalStyle().getZeroDigit());
assertEquals(ZoneId.of("UTC"), formatter.getZone());
~~~

Đây là **đoạn test minh họa**, `assertEquals` là hàm của thư viện kiểm thử; nó không thuộc Java standard library. Sáu chương trình đầy đủ trong bài đều dùng Java thuần và có lệnh `javac`/`java`.

**Nhớ ba cấp kiểm thử:** (1) trạng thái override qua getter; (2) format một `Instant` hoặc `LocalDate` cố định; (3) parse khi cần đối chiếu với định dạng văn bản đầu vào.

## 10. Cách tránh xung đột khi xây dựng formatter nhiều lớp

Một service có thể áp dụng cấu hình theo nhiều tầng:

~~~text
DateTimeFormatter gốc
  |
  | localizedBy(locale của người dùng)
  v
Formatter theo sở thích người dùng
  |
  | withChronology(ISO) — nếu API yêu cầu năm ISO
  | withDecimalStyle(STANDARD) — nếu API yêu cầu chữ số ASCII
  | withZone(zone đã được chọn trong nghiệp vụ)
  v
Formatter cuối cùng để format/parse
~~~

**Thiết kế khuyến nghị:**

1. **Định nghĩa thứ tự ưu tiên** bằng văn bản: locale preference hay cấu hình explicit của API thắng khi xung đột?
2. **Tạo formatter từ một base rõ ràng**, thay vì mỗi tầng gọi `localizedBy`/`withXXXX` ngẫu nhiên.
3. **Áp dụng locale trước** nếu ứng dụng muốn dùng nó làm nền nhưng vẫn có những override explicit cuối.
4. **Gọi `withChronology` chỉ khi cần**. Không tự đổi lịch của người dùng thành ISO ở màn hình vốn cần hiển thị lịch theo `ca`.
5. **Gọi `withDecimalStyle` đúng nhu cầu**. Chuẩn hóa chữ số ASCII phù hợp với giao thức máy, nhưng chưa chắc phù hợp với UI quốc tế hóa.
6. **Gọi `withZone` theo nguồn dữ liệu tin cậy**. Nếu dùng `tz` từ locale, hãy kiểm tra mã được hỗ trợ; nếu dùng IANA ZoneId do người dùng chọn, hãy validate ZoneId và dùng nó tường minh.
7. **Không sửa default JVM theo request**. `Locale.setDefault`/`TimeZone.setDefault` ảnh hưởng trạng thái dùng chung; thay vào đó tạo formatter riêng, bất biến.
8. **Ghi rõ version/data dependency** khi test chữ số, tên vùng, mẫu `ofLocalizedDateTime` hay alias CLDR/TZDB. Đừng khóa cứng văn bản tên tháng, giờ viết tắt hoặc zone alias không được hợp đồng bảo đảm.
9. **Đừng quên DST và offset**. Với lịch hẹn, `ZoneId` và `Instant` có ý nghĩa khác nhau; không thay ZoneId bằng offset cố định.
10. **Kiểm thử các đường xung đột**, không chỉ đường không có extension. Với `ca`, `nu`, `tz` có chủ ý khác override explicit mới chứng minh được thứ tự thực sự.

### Quyết định theo mục tiêu

| Mục tiêu | Thứ tự nên dùng | Vì sao |
| --- | --- | --- |
| Màn hình tôn trọng toàn bộ `ca`/`nu`/`tz` của người dùng | `base.localizedBy(userLocale)`, tránh override trái ngược sau đó | Unicode locale preferences điều khiển kết quả |
| API xuất năm ISO và chữ số ASCII, zone do domain chọn | `base.localizedBy(userLocale).withChronology(ISO).withDecimalStyle(STANDARD).withZone(domainZone)` | Hợp đồng API explicit thắng |
| Chỉ đổi ngôn ngữ/locale cho text, giữ các override đã chọn | `base.withLocale(userLocale)` | Không chủ động áp dụng các giá trị lịch/số/múi giờ từ extension |
| Muốn thời gian theo vùng IANA đã được người dùng chọn | `base.localizedBy(locale).withZone(zone)` | Zone explicit đặt cuối; không dựa vào `tz` trong locale |
| Muốn ưu tiên `tz` từ locale hơn UTC cài mặc định | `base.withZone(UTC).localizedBy(localeWithTz)` | Extension `tz` hợp lệ có thể thay UTC |
| Muốn cả ngôn ngữ địa phương và năm Phật lịch nhưng ASCII digits | `base.localizedBy(localeWithCaNu).withDecimalStyle(STANDARD)` | Giữ chronology do `ca`, chỉ ghi đè chữ số |

**Quan trọng:** `withLocale` không thay thế `localizedBy` khi cần thực sự áp dụng Unicode extension vào chronology, decimal style và zone. Ngược lại, `localizedBy` không phải phương thức nên gọi bừa sau khi đã hoàn thành mọi override, vì nó có thể khiến các ràng buộc explicit bị thay.

## 11. Những sai lầm thường gặp

| Sai lầm | Hậu quả | Hướng sửa |
| --- | --- | --- |
| “Thứ tự `localizedBy` và các `withXXXX` không ảnh hưởng” | Chronology, chữ số, múi giờ bị thay ngoài ý muốn | Quy định precedence, kiểm tra getter và output |
| “`withLocale` tương đương `localizedBy`” | `ca`/`nu`/`tz` không được áp dụng như dự kiến | Dùng đúng phương thức |
| “Đặt `withChronology(ISO)` trước `localizedBy(ca-buddhist)` thì chắc năm ISO” | Locale có thể đặt lại ThaiBuddhist | Nếu ISO là ràng buộc, gọi `withChronology(ISO)` **sau** |
| “Đặt `DecimalStyle.STANDARD` trước `localizedBy(nu-thai)` thì chắc ASCII” | Chữ số Thái có thể được chọn | Đặt `withDecimalStyle(STANDARD)` sau |
| “Đặt `withZone(UTC)` trước `localizedBy(tz-uslax)` thì chắc UTC” | Zone LA có thể ghi đè UTC | Đặt `withZone(UTC)` cuối nếu UTC phải thắng |
| “Mọi lần gọi `localizedBy` đều xóa zone cũ” | Locale không có `tz` có thể giữ zone đã chọn | Kiểm tra `getZone()` và tài liệu |
| “Locale không có extension chắc không đổi gì” | Chronology/decimal style có thể được bản địa hóa | Test với `Locale.US` và các override khác |
| “`getLocale()` cho biết mọi cấu hình của formatter” | Locale có thể còn `tz-uslax` nhưng formatter đã `withZone(UTC)` | Đọc cả `getChronology/getDecimalStyle/getZone` |
| “Ký tự số và giá trị lịch là một thứ” | Năm đổi 2024↔2567 bị nhầm với thay font | Tách `Chronology` và `DecimalStyle` |
| “Zone luôn là offset cố định” | Sai giờ khi chuyển DST | Dùng IANA `ZoneId` |
| “Có thể parse mọi output với một formatter ISO/ASCII” | Sai hoặc ném exception với lịch/chữ số khác | Parse bằng formatter đúng contract của dữ liệu |
| “Formatter mới sẽ sửa formatter gốc” | Hiểu sai trạng thái/ảnh hưởng request khác | `DateTimeFormatter` immutable; giữ kết quả mới |
| “Múi giờ của Locale thay mặc định JVM” | Thiết kế state toàn cục sai | Chỉ cấu hình formatter theo request |
| “`localizedBy` trả dữ liệu y hệt trên mọi JDK/provider” | Test brittle với CLDR/TZDB alias/mẫu text | Dùng mốc cố định, assert cấu hình thiết yếu và quản lý version |

## 12. Checklist QA cho một pull request

Một reviewer nên hỏi:

1. Locale có `ca`, `nu`, `tz` hoặc `rg` không? Nếu có, **giá trị nào có quyền ưu tiên**?
2. `localizedBy` được gọi trước hay sau các override? Có tầng nào gọi nó lại không?
3. Formatter cuối có `getChronology()`, `getDecimalStyle()`, `getZone()` đúng không?
4. Ký tự số có đúng dạng yêu cầu không? Thử cả năm 2024 theo ISO và 2567 theo ThaiBuddhist.
5. Múi giờ có đúng với `Instant` cố định không? Kiểm tra mùa đông/mùa hè với vùng có DST.
6. Văn bản có được parse bằng cùng quy tắc lịch/chữ số/vùng với lúc format không?
7. Có dùng `Locale` là nguồn ngôn ngữ nhưng `ZoneId` tường minh là nguồn múi giờ không? Điều này có được ghi rõ?
8. Code có dựa vào `Locale.US` hoặc ngôn ngữ để đoán time zone không? Nếu có cần sửa.
9. Có bất kỳ `Locale.setDefault`/`TimeZone.setDefault` trong đường request không?
10. Test có bị phụ thuộc `now()`, tên múi giờ đã dịch hoặc alias provider không?
11. Có bất kỳ mục tiêu “đầu ra API ASCII/ISO” bị phá bởi một `localizedBy` đặt ở cuối chuỗi?
12. Nếu locale có extension không được hỗ trợ, hệ thống xử lý fallback/validation thế nào thay vì âm thầm cho ra dữ liệu khác kỳ vọng?

Nếu code xây formatter trong nhiều tầng, ưu tiên hàm factory tập trung quyết định precedence. Kiểm tra kiểu và trạng thái rõ ràng tốt hơn chỉ đọc chuỗi chain rồi suy đoán.

## 13. Câu hỏi tự kiểm tra

1. Vì sao `localizedBy(Locale)` khác `withLocale(Locale)` khi Locale có `ca`, `nu`, `tz`?
2. Dùng `en-US-u-ca-buddhist-nu-thai-tz-uslax`, nếu muốn cuối cùng vẫn là lịch ISO, ASCII và UTC, gọi ba phương thức `withXXXX` trước hay sau `localizedBy`?
3. Trường hợp cần ưu tiên sở thích lịch Phật giáo từ Locale hơn `withChronology(ISO)`, thứ tự nào phù hợp?
4. `withDecimalStyle(STANDARD)` có thay chronology hoặc zone không?
5. `withZone(UTC)` có tự xóa khóa `tz-uslax` khỏi `getLocale()` không?
6. Nếu `getZone()==null`, có thể kết luận hệ thống không có múi giờ nào không?
7. `localizedBy(Locale.US)` không có `tz` có bắt buộc xóa zone override đang tồn tại không?
8. `LocalDate.of(2024,1,15)` định dạng dưới ThaiBuddhist chronology có thể hiển thị năm nào?
9. Vì sao cùng một `Instant` vào Los Angeles tháng 1 và tháng 7 năm 2024 cho offset khác nhau?
10. Tại sao test format/parse văn bản số Thái nên kiểm tra decimal style?
11. Có nên gọi `localizedBy` sau khi đã chốt hết policy explicit mà không có chủ đích không?
12. Khi một API phải xuất timestamp theo giờ Việt Nam nhưng Locale của người dùng vẫn chứa `tz-uslax`, cần tin `getLocale()` hay `getZone()` của formatter cuối?

**Đáp án:**

1. `withLocale` lưu Locale cho việc sử dụng về sau, còn `localizedBy` áp dụng thêm dữ liệu bản địa hóa từ Unicode extensions vào các override thích hợp.
2. **Sau** `localizedBy` để ISO/ASCII/UTC là policy cuối.
3. Gọi `withChronology(ISO)` trước `localizedBy(localeWithCaBuddhist)`, hoặc không đặt override ISO nếu không cần.
4. Không; chỉ thay decimal style.
5. Không. Locale vẫn có thể mang `tz` dù zone explicit đã khác.
6. Không; getter null chỉ có nghĩa formatter **không có override zone**.
7. Không. Hành vi tùy thuộc locale và giá trị được bản địa hóa; ví dụ JDK kiểm thử giữ UTC.
8. Năm **2567** cho cùng ngày ISO 2024-01-15.
9. Los Angeles có quy tắc DST, mùa đông `-08:00`, mùa hè `-07:00` ở hai thời điểm ví dụ.
10. Vì `nu-thai` có thể tạo chữ số Thái; parsing cần cùng quy tắc decimal style.
11. Không; có thể ghi đè chronology, digits hoặc zone đã quyết định.
12. Kiểm tra **`getZone()`** và trạng thái cuối; `getLocale()` không đủ xác định effective zone.

## 14. Tài liệu Java chính thức còn áp dụng

- **Oracle Javadoc — `DateTimeFormatter.localizedBy(Locale)`, `withLocale`, `withChronology`, `withDecimalStyle`, `withZone`, Java SE 26:** https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/time/format/DateTimeFormatter.html
- **Oracle Javadoc — `DateTimeFormatter`, Java SE 10 (mốc giới thiệu `localizedBy`):** https://docs.oracle.com/javase/10/docs/api/java/time/format/DateTimeFormatter.html
- **OpenJDK — JEP 314, Additional Unicode Language-Tag Extensions:** https://openjdk.org/jeps/314
- **Oracle Javadoc — `Locale` và Unicode locale extension:** https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/Locale.html
- **Oracle Javadoc — `DecimalStyle`:** https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/time/format/DecimalStyle.html
- **Oracle Javadoc — `Chronology`, `IsoChronology`, `ThaiBuddhistChronology`:** https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/time/chrono/Chronology.html
- **Oracle Javadoc — `ZoneId`:** https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/time/ZoneId.html
- **Oracle Javadoc — `Instant`:** https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/time/Instant.html
- **Unicode CLDR — Unicode Locale Identifiers và thời gian:** https://www.unicode.org/reports/tr35/

**Ghi nhớ:** `localizedBy(locale)` của Java 10+ có thể áp dụng **lịch, chữ số và múi giờ từ locale** vào một `DateTimeFormatter` bất biến. `withChronology`, `withDecimalStyle` và `withZone` đặt lại **từng override tường minh**, vì vậy **thứ tự gọi phải phản ánh chính sách ưu tiên**. Nếu ứng dụng cần giữ kết quả theo quy tắc ISO/ASCII/IANA ZoneId, hãy gọi `localizedBy` trước rồi áp dụng các override bắt buộc sau. Khi cần tôn trọng `ca`/`nu`/`tz` của người dùng, tránh ghi đè chúng ngoài ý muốn. Luôn kiểm tra formatter cuối bằng getter, ngày/giờ cố định, và parsing khi cần; không suy luận chỉ từ ngôn ngữ hoặc thẻ `Locale`.