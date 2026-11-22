# Phân biệt mẫu SimpleDateFormat với DateTimeFormatter trong Java

Trong các ứng dụng bản địa hóa, một ngày có thể được hiển thị theo `28/10/2026`, `10/28/2026` hoặc tên tháng bằng ngôn ngữ người dùng. Hai API Java thường được gặp là **`java.text.SimpleDateFormat`** (API ngày giờ cũ) và **`java.time.format.DateTimeFormatter`** (API Java Time hiện đại). Chúng đều dùng **pattern gồm các chữ cái** như `y`, `M`, `d`, `H`, nhưng **không có cùng một ngôn ngữ pattern hoàn toàn**.

Điểm mấu chốt: **không thể coi việc đổi `new SimpleDateFormat(pattern)` thành `DateTimeFormatter.ofPattern(pattern)` là một phép thay thế an toàn trong mọi trường hợp.** Một số ký hiệu có ngữ nghĩa khác, chẳng hạn `S` là **milli giây** ở `SimpleDateFormat` nhưng là **chữ số phần thập phân của giây** ở `DateTimeFormatter`; cách xử lý năm, tuần-năm, múi giờ, parse nghiêm ngặt và đối tượng thời gian đầu vào cũng khác.

Bài này giải thích từng nhóm ký hiệu, trình bày những nơi có thể giữ pattern, những nơi phải chuyển đổi, và đưa ví dụ **Java 17+ chạy độc lập**. Mục tiêu là biết đọc, kiểm tra và di trú pattern chính xác, chứ không chỉ thuộc bảng chữ cái.

## 1. Hai API giải quyết vấn đề gì?

| Tiêu chí | `SimpleDateFormat` | `DateTimeFormatter` |
| --- | --- | --- |
| Package | `java.text` | `java.time.format` |
| Xuất hiện | Java đời cũ | Java 8+ (`java.time`) |
| Dữ liệu thường format | `java.util.Date`, thông qua `Calendar` và `TimeZone` | `LocalDate`, `LocalTime`, `LocalDateTime`, `Instant`, `OffsetDateTime`, `ZonedDateTime` khi đủ trường |
| Tạo pattern | `new SimpleDateFormat(pattern, locale)` | `DateTimeFormatter.ofPattern(pattern, locale)` |
| Chọn múi giờ | `setTimeZone(TimeZone)` trên formatter mutable | `withZone(ZoneId)` trả formatter **mới**, hoặc format một temporal đã có offset/zone |
| Chọn locale | Constructor, `DateFormatSymbols` | `ofPattern(..., locale)`, `withLocale(locale)` |
| Đối tượng formatter | **Mutable**, không thread-safe nếu chia sẻ không kiểm soát | **Immutable**, thread-safe |
| Parse kiểu thông dụng | `Date` với `parse(...)` | `LocalDate.parse(...)`, `OffsetDateTime.parse(...)`, v.v. với formatter phù hợp |
| Resolver | `setLenient(true/false)` thông qua `Calendar` | `ResolverStyle.SMART` (thường mặc định), `STRICT`, `LENIENT` |
| Mục đích khuyên dùng | Tương thích hệ thống/thư viện cũ | Mã mới sử dụng `java.time` |

**Không trộn lẫn kiểu dữ liệu:** `Date` về cơ bản biểu diễn một thời điểm; `LocalDate` biểu diễn **ngày lịch không có múi giờ hoặc giờ**, `LocalDateTime` không có offset và `Instant` là một thời điểm UTC. Chọn đúng kiểu trước khi định dạng; pattern chỉ quyết định cách trình bày các trường có sẵn.

## 2. Những ký hiệu có vẻ giống nhau

Với ngày thông thường, nhiều chữ cái gần như tương ứng:

| Ý nghĩa | `SimpleDateFormat` | `DateTimeFormatter` | Lưu ý |
| --- | --- | --- | --- |
| Năm theo kỷ nguyên | `y`, `yyyy` | `y`, `yyyy` | Java Time còn có `u` (proleptic year), quan trọng với parse STRICT |
| Năm theo **tuần** | `Y`, `YYYY` | `Y`, `YYYY` | Không phải năm lịch; phụ thuộc quy tắc tuần/locale |
| Tháng (dạng format) | `M`, `MM`, `MMM`, `MMMM` | Tương ứng | Tên tháng phụ thuộc locale |
| Ngày trong tháng | `d`, `dd` | Tương ứng | `dd` thường thêm số 0 nếu cần |
| Ngày trong năm | `D` | `D` | Khác hẳn `d` |
| Thứ trong tuần dạng chữ | `E`, `EEEE` | `E`, `EEEE` | Nội dung chữ phụ thuộc locale |
| Giờ 0–23 | `H`, `HH` | Tương ứng | Phân biệt với `h` |
| Giờ 1–12 | `h`, `hh` | Tương ứng | Thường cần `a` (AM/PM) |
| Phút | `m`, `mm` | Tương ứng | `MM` là **tháng**, không phải phút |
| Giây | `s`, `ss` | Tương ứng | Không bao gồm phần lẻ |
| AM/PM | `a` | `a` | Tên nhãn theo locale |
| Ký hiệu múi giờ ngắn/dài | `z` | `z` | Tên/viết tắt tùy vùng và locale |
| Offset kiểu ISO | `X`, `XX`, `XXX` | `X`, `XX`, `XXX` | Số lượng chữ `X` được hỗ trợ và cách parse không hoàn toàn giống |
| Milli giây so với phân số giây | `S` | `S` | **Khác ngữ nghĩa**, xem mục 5 |
| Năm thiên văn / proleptic year | Không có ký tự `u` tương đương Java Time | `u`, `uuuu` | `SimpleDateFormat` dùng `u` cho **thứ trong tuần** (1 = Monday) |

Pattern có chữ cái **phân biệt hoa/thường**. Các ví dụ dễ sai: `MM` = tháng, `mm` = phút; `dd` = ngày trong tháng, `DD` = ngày trong năm; `yyyy` = năm theo kỷ nguyên, `YYYY` = năm của tuần. Ngay cả khi cùng một mẫu xuất ra chuỗi giống nhau với ngày hiện tại, điều đó không chứng minh pattern có ngữ nghĩa giống nhau ở mọi ngày.

## 3. Ví dụ nền tảng: format cùng một thời điểm bằng hai API

Tạo file **`BasicPatternDemo.java`**:

```java
import java.text.SimpleDateFormat;
import java.time.Instant;
import java.time.ZoneOffset;
import java.time.format.DateTimeFormatter;
import java.util.Date;
import java.util.Locale;
import java.util.TimeZone;

public class BasicPatternDemo {
    public static void main(String[] args) {
        Instant instant = Instant.parse("2026-10-28T10:07:06.123Z");

        SimpleDateFormat legacy = new SimpleDateFormat(
                "yyyy-MM-dd HH:mm:ss.SSS", Locale.ROOT);
        legacy.setTimeZone(TimeZone.getTimeZone("UTC"));

        DateTimeFormatter modern = DateTimeFormatter
                .ofPattern("uuuu-MM-dd HH:mm:ss.SSS", Locale.ROOT)
                .withZone(ZoneOffset.UTC);

        System.out.println("Legacy: "
                + legacy.format(Date.from(instant)));
        System.out.println("Modern: "
                + modern.format(instant));
    }
}
```

```bash
javac -encoding UTF-8 BasicPatternDemo.java
java BasicPatternDemo
```

Stdout:

```text
Legacy: 2026-10-28 10:07:06.123
Modern: 2026-10-28 10:07:06.123
```

**Vì sao hai dòng giống nhau?**

1. Cả hai nhận cùng một **`Instant`**, chuyển sang `Date` cho API cũ.
2. Cả hai đều dùng **UTC**, tránh ảnh hưởng múi giờ mặc định của máy.
3. Ngày năm 2026 thuộc Common Era, nên `yyyy` của `SimpleDateFormat` và `uuuu` của `DateTimeFormatter` đều hiển thị `2026`.
4. Có chính xác **123 milliseconds**; với pattern ba chữ số `SSS`, hai cách diễn giải cho ra cùng `123`. Khi đổi số chữ `S`, sự khác biệt lộ rõ ở mục 5.

**Không suy ra hai pattern nói chung tương đương:** ví dụ trên là **một trường hợp phù hợp**. Khi di trú, phải kiểm tra từng token, kiểu thời gian, múi giờ, locale và yêu cầu parse.

## 4. Năm `yyyy`, `uuuu` và tuần-năm `YYYY`

### `yyyy` và `uuuu` không phải ký tự thay thế vô điều kiện

Trong `SimpleDateFormat`, `y` biểu diễn **year** qua `Calendar`; khi dùng hệ Gregorian thường gặp, `yyyy` cho năm mà người dùng quen đọc. `SimpleDateFormat` không định nghĩa `u` là proleptic year: ký tự `u` trong API cũ có nghĩa **day number of week** (Monday = 1 ... Sunday = 7).

Trong `DateTimeFormatter`:

- `y` = **year-of-era**, một năm tính trong kỷ nguyên, cần biết era nếu phân tích **STRICT** ở một số tình huống.
- `u` = **proleptic year**, có thể đại diện cả năm 0 và năm trước Công nguyên theo hệ ISO.
- `Y` = **week-based-year**, xác định bởi quy tắc tuần của locale; nó có thể khác năm lịch quanh cuối/tháng đầu năm.

Để lưu ngày ISO dạng máy đọc và parse nghiêm ngặt, pattern `uuuu-MM-dd` là lựa chọn phù hợp. `DateTimeFormatter.ISO_LOCAL_DATE` là lựa chọn tốt hơn nếu ý định là ISO ngày tiêu chuẩn, vì không phải tự duy trì pattern cho định dạng này.

### Ví dụ parse STRICT bằng năm theo kỷ nguyên

File **`StrictYearPatternDemo.java`**:

```java
import java.time.LocalDate;
import java.time.format.DateTimeFormatter;
import java.time.format.DateTimeParseException;
import java.time.format.ResolverStyle;
import java.util.Locale;

public class StrictYearPatternDemo {
    public static void main(String[] args) {
        String text = "2026-10-28";

        DateTimeFormatter yearOfEra = DateTimeFormatter
                .ofPattern("yyyy-MM-dd", Locale.ROOT)
                .withResolverStyle(ResolverStyle.STRICT);
        DateTimeFormatter proleptic = DateTimeFormatter
                .ofPattern("uuuu-MM-dd", Locale.ROOT)
                .withResolverStyle(ResolverStyle.STRICT);

        try {
            LocalDate.parse(text, yearOfEra);
            System.out.println("yyyy STRICT: accepted");
        } catch (DateTimeParseException ex) {
            System.out.println("yyyy STRICT: rejected");
        }

        System.out.println("uuuu STRICT: "
                + LocalDate.parse(text, proleptic));
    }
}
```

```bash
javac -encoding UTF-8 StrictYearPatternDemo.java
java StrictYearPatternDemo
```

Stdout:

```text
yyyy STRICT: rejected
uuuu STRICT: 2026-10-28
```

**Tại sao `yyyy` bị từ chối?** Pattern chứa `YEAR_OF_ERA`, nhưng không cung cấp **era**. Khi resolver ở chế độ STRICT, Java Time không tự giả định một kỷ nguyên để tạo `LocalDate`. `uuuu` ghi trực tiếp `YEAR` (proleptic), nên ngày được resolve mà không thiếu era.

**Ngoại lệ quan trọng:** `yyyy-MM-dd` vẫn có thể format ngày dương bình thường, và khi parse với `ResolverStyle.SMART` mặc định của `ofPattern` thì có thể được xử lý khác. Không nói rằng `yyyy` “luôn sai” trong DateTimeFormatter; vấn đề là **ngữ nghĩa và độ nghiêm ngặt khi resolve**.

### Vì sao không dùng `YYYY-MM-dd` cho ngày lịch?

`YYYY` biểu diễn năm theo **tuần**, không phải năm lịch; ở vài ngày cuối tháng 12, nó có thể thuộc năm tuần kế tiếp. Với locale như `en-US`, tuần bắt đầu và tiêu chí tuần đầu năm có thể khác với tiêu chuẩn ISO. Hậu quả là format một ngày tháng 12 thành năm tuần của năm sau trong khi `MM-dd` vẫn là tháng/ngày của năm trước. Sự ghép này không có ý nghĩa như một ngày lịch ISO.

**Quy tắc:** dùng `yyyy` cho ngày theo kỷ nguyên trong giao diện, `uuuu` cho ISO proleptic year của Java Time khi cần; chỉ dùng `YYYY` cùng các trường **week-of-week-based-year** khi dữ liệu thực sự là lịch tuần. Đừng thay `yyyy` bằng `YYYY` vì tưởng chữ hoa đẹp hơn.

## 5. Khác biệt quan trọng nhất: ký hiệu `S`

Trong hai API, `S` trông giống nhau nhưng cách diễn giải khác:

| API | `S` nghĩa là | Pattern dài hơn |
| --- | --- | --- |
| `SimpleDateFormat` | **Millisecond**, một giá trị nguyên trong khoảng thường là 0–999 trong giây | Số lượng `S` quyết định **độ rộng tối thiểu** khi trình bày số milliseconds; không tăng độ chính xác vật lý vượt millisecond |
| `DateTimeFormatter` | **Fraction-of-second** (phần thập phân của giây) | Số chữ `S` quyết định **độ rộng phần phân số**, từ 1 đến 9 chữ số trong pattern; dùng nanosecond-of-second có độ chính xác phù hợp |

Với thời điểm có 123 milliseconds, pattern `SSS` in `123` ở cả hai API. Nhưng với pattern **`SSSSSS`**, API cũ có thể đệm số `123` thành `000123`, trong khi API mới in sáu chữ số phần giây `123000`. Đây không phải cùng một giá trị hiển thị, dù cùng thời điểm.

### Chương trình chứng minh — `FractionPatternDemo.java`

```java
import java.text.SimpleDateFormat;
import java.time.Instant;
import java.time.ZoneOffset;
import java.time.format.DateTimeFormatter;
import java.util.Date;
import java.util.Locale;
import java.util.TimeZone;

public class FractionPatternDemo {
    public static void main(String[] args) {
        Instant instant = Instant.parse("2026-10-28T10:07:06.123Z");

        SimpleDateFormat legacy = new SimpleDateFormat(
                "HH:mm:ss.SSSSSS", Locale.ROOT);
        legacy.setTimeZone(TimeZone.getTimeZone("UTC"));

        DateTimeFormatter modern = DateTimeFormatter
                .ofPattern("HH:mm:ss.SSSSSS", Locale.ROOT)
                .withZone(ZoneOffset.UTC);

        System.out.println("Legacy: "
                + legacy.format(Date.from(instant)));
        System.out.println("Modern: "
                + modern.format(instant));
    }
}
```

```bash
javac -encoding UTF-8 FractionPatternDemo.java
java FractionPatternDemo
```

Stdout (JDK 17 chuẩn):

```text
Legacy: 10:07:06.000123
Modern: 10:07:06.123000
```

**Phân tích:** `123 ms = 0,123 giây`, tức **123000 microseconds**. `DateTimeFormatter` với `SSSSSS` viết sáu chữ số phần giây `123000`. Trong `SimpleDateFormat`, `SSSSSS` không có nghĩa “microseconds”; nó chỉ đệm giá trị milliseconds `123` thành sáu chữ số `000123`.

Khi migrate code cũ có `SSSSSS` hoặc xử lý timestamps có microseconds/nanoseconds, **phải định nghĩa lại precision**. `java.util.Date` thông thường chỉ lưu thời điểm theo milliseconds; đổi formatter không thể tái tạo các nanoseconds đã không có trong nguồn. `Instant`, `LocalDateTime` và các kiểu `java.time` có thể mang độ chính xác nanosecond, nhưng độ chính xác thật vẫn phụ thuộc hệ thống cung cấp dữ liệu.

**Giới hạn ký hiệu:** `DateTimeFormatter` hỗ trợ tối đa 9 chữ `S` cho fraction-of-second; pattern vượt giới hạn có thể ném `IllegalArgumentException` khi tạo formatter. Không xem một chuỗi dài chữ `S` từ `SimpleDateFormat` là an toàn để sao chép sang formatter mới.

## 6. Các chữ cái có nghĩa khác hoặc không được hỗ trợ

Một số chữ cái mang ý nghĩa rất khác:

| Ký hiệu | SimpleDateFormat (Java 17) | DateTimeFormatter (Java 17) |
| --- | --- | --- |
| `u` | **Day number of week** (Monday = 1) | **Proleptic year** |
| `F` | **Day of week in month** (`Calendar.DAY_OF_WEEK_IN_MONTH`) | **Aligned day-of-week in month** (1–7 trong các khối 7 ngày) |
| `S` | Milliseconds dạng số | Fraction-of-second |
| `Y` | Week-year qua `Calendar` nếu calendar hỗ trợ | Localized week-based-year |
| `e` | Không phải pattern letter được định nghĩa ở `SimpleDateFormat` | Localized day-of-week (number/text theo độ dài) |
| `c` | Không phải pattern letter ở `SimpleDateFormat` | Stand-alone localized day-of-week |
| `n` | Không phải pattern letter ở `SimpleDateFormat` | Nano-of-second |
| `N` | Không phải pattern letter ở `SimpleDateFormat` | Nano-of-day |
| `V` | Không phải pattern letter ở `SimpleDateFormat` | Zone ID, thường dùng `VV` |
| `p` | Không phải pattern letter ở `SimpleDateFormat` | Padding modifier cho trường kế tiếp |
| `B` | Không phải pattern letter ở `SimpleDateFormat` | Period-of-day theo locale (sáng/trưa/chiều...) |

Ví dụ, một pattern cũ dùng `F` không thể đảm bảo giữ ý nghĩa khi chuyển thẳng sang DateTimeFormatter. Trước khi sửa, phải xác định dữ liệu mong muốn: *lần xuất hiện thứ mấy của một thứ trong tháng* không đồng nghĩa *ngày thứ mấy tính từ đầu mỗi khối bảy ngày của tháng*.

**Cần lưu ý ký hiệu `L`**: cả hai API có hỗ trợ stand-alone month trong các JDK hiện đại, nhưng sự khác nhau giữa tên tháng dùng độc lập và tên tháng trong câu còn phụ thuộc dữ liệu locale. Không nên giả định việc thay `MMMM` bằng `LLLL` luôn có hiệu quả giống nhau trong mọi ngôn ngữ.

### Các chữ thường trông vô hại nhưng gây lỗi

- `MM` là tháng, `mm` là phút.
- `D` là ngày thứ mấy của năm, `d` là ngày trong tháng.
- `H` là giờ 0–23; `h` là giờ 1–12, dùng với `a` để xác định AM/PM nếu cần.
- `k` là giờ 1–24; `K` là giờ 0–11. Chúng không thể thay tùy ý bằng `H`/`h`.
- `E` là thứ trong tuần, nhưng các phiên bản DateTimeFormatter còn có `e`/`c` theo quy tắc localized/stand-alone; code cũ có thể không hiểu.
- `z` là tên vùng hoặc ký hiệu giờ; `Z` và `X` xử lý offset theo quy tắc khác, không phải chỉ khác cách viết chữ.

Khi pattern chứa một chữ cái không được công nhận ở API đích, constructor hoặc `ofPattern` thường ném `IllegalArgumentException`; điều đó giúp phát hiện lỗi sớm. Nguy hiểm hơn là **những chữ có mặt ở cả hai API nhưng ý nghĩa khác**, vì code vẫn chạy mà kết quả không còn đúng.

## 7. Offset và múi giờ: `z`, `Z`, `X`, `x`, `VV`

### Chọn đúng ý nghĩa trước khi viết pattern

- **Offset** như `+07:00` nói thời gian địa phương chênh UTC bao nhiêu. Không chứa toàn bộ lịch sử quy tắc DST.
- **Zone ID** như `Asia/Ho_Chi_Minh` hoặc `Europe/Paris` chứa thông tin vùng và quy tắc tính offset theo thời điểm.
- **Tên vùng hiển thị** như `GMT+07:00`, `PDT` hay tên đầy đủ phụ thuộc locale và dữ liệu zone, có thể thay đổi.

Với `SimpleDateFormat`:

- `z`: tên/ký hiệu timezone.
- `Z`: RFC 822-style numeric offset, ví dụ `+0700`.
- `X`, `XX`, `XXX`: ISO 8601 offset (kiểu `+07`, `+0700`, `+07:00` tùy độ dài); tại UTC có thể in `Z`.

Với `DateTimeFormatter`:

- `X`: ISO 8601 offset, hỗ trợ nhiều độ dài; `XXX` thường biểu diễn `+07:00`.
- `x`: giống nhóm offset theo ISO nhưng **zero offset** không dùng chữ `Z` như `X`; lựa chọn thể hiện phụ thuộc độ dài.
- `Z`: offset theo các định dạng khác nhau tùy số lượng chữ `Z`.
- `O`: localized zone-offset, ví dụ `GMT+7`, tùy locale.
- `VV`: **zone ID**; yêu cầu temporal có vùng phù hợp.
- `z`: tên vùng dạng text, phụ thuộc locale và zone data.

**Không thể chỉ format một `LocalDateTime` bằng `XXX` rồi mong Java suy ra offset**. `LocalDateTime` không mang zone/offset. Muốn có offset, truyền `OffsetDateTime`/`ZonedDateTime` hoặc tạo từ instant cùng zone rõ ràng. Đối với `Instant`, dùng `DateTimeFormatter.withZone(zone)` khi pattern cần ngày/giờ địa phương.

### Ví dụ `XXX` — `OffsetPatternDemo.java`

```java
import java.time.OffsetDateTime;
import java.time.format.DateTimeFormatter;
import java.util.Locale;

public class OffsetPatternDemo {
    public static void main(String[] args) {
        OffsetDateTime date = OffsetDateTime.parse(
                "2026-10-28T17:30:00+07:00");

        DateTimeFormatter format = DateTimeFormatter.ofPattern(
                "uuuu-MM-dd HH:mm XXX", Locale.ROOT);

        System.out.println(format.format(date));
        System.out.println(date.toInstant());
    }
}
```

```bash
javac -encoding UTF-8 OffsetPatternDemo.java
java OffsetPatternDemo
```

Stdout:

```text
2026-10-28 17:30 +07:00
2026-10-28T10:30:00Z
```

`XXX` trong ví dụ hiện offset đúng như dữ liệu; `toInstant()` cho biết thời điểm UTC tương ứng. Nếu `date` là `LocalDateTime`, lời gọi format dùng `XXX` không có đủ thông tin và sẽ lỗi. **Không dùng timezone mặc định của máy** như một giải pháp ngầm, đặc biệt khi xử lý dữ liệu nhiều người dùng.

## 8. Parse khác nhau: lenient của SimpleDateFormat và ResolverStyle

### SimpleDateFormat mặc định khá dễ dãi

`SimpleDateFormat` sử dụng `Calendar`. Mặc định calendar thường **lenient = true**, cho phép chuẩn hóa ngày không hợp lệ như một ngày ngoài tháng thành một ngày khác. Gọi `setLenient(false)` sẽ từ chối các giá trị ngày/giờ vượt phạm vi hợp lệ theo calendar.

Tuy nhiên, `setLenient(false)` **không đồng nghĩa** parser yêu cầu tiêu thụ hết input. `DateFormat.parse(String)` có thể đọc prefix hợp lệ rồi bỏ các ký tự phía sau. Để kiểm tra toàn bộ chuỗi, dùng `ParsePosition`, kiểm tra chỉ số đã parse tới cuối và error index, cùng validation theo nghiệp vụ.

### DateTimeFormatter: lexical parse rồi resolve

`DateTimeFormatter.ofPattern(...)` thường có **ResolverStyle.SMART** mặc định, không phải STRICT. Khi resolve các trường ngày, SMART có thể điều chỉnh một số giá trị ngày trong tháng vượt quá cuối tháng về ngày cuối cùng hợp lệ. `ResolverStyle.STRICT` từ chối những trường hợp đó, `LENIENT` có quy tắc xử lý nới lỏng hơn.

Đối với ngày ISO máy đọc, dùng `DateTimeFormatter.ISO_LOCAL_DATE` hoặc formatter `"uuuu-MM-dd"` với `ResolverStyle.STRICT` khi muốn từ chối input không hợp lệ. Cần phân biệt **`parseCaseInsensitive`/`parseLenient`** của builder (cách đọc văn bản/độ rộng) với **resolver style** (kiểm tra tính hợp lệ của kết hợp các trường ngày).

### Ví dụ kiểm chứng — `ParseStrictnessDemo.java`

```java
import java.text.ParseException;
import java.text.SimpleDateFormat;
import java.time.LocalDate;
import java.time.format.DateTimeFormatter;
import java.time.format.DateTimeParseException;
import java.time.format.ResolverStyle;
import java.util.Locale;
import java.util.TimeZone;

public class ParseStrictnessDemo {
    public static void main(String[] args) {
        String text = "2026-02-30";

        SimpleDateFormat legacy = new SimpleDateFormat(
                "yyyy-MM-dd", Locale.ROOT);
        legacy.setTimeZone(TimeZone.getTimeZone("UTC"));
        legacy.setLenient(false);

        try {
            legacy.parse(text);
            System.out.println("Legacy strict: accepted");
        } catch (ParseException ex) {
            System.out.println("Legacy strict: rejected");
        }

        DateTimeFormatter smart = DateTimeFormatter.ofPattern(
                "uuuu-MM-dd", Locale.ROOT);
        System.out.println("Modern SMART: "
                + LocalDate.parse(text, smart));

        DateTimeFormatter strict = smart.withResolverStyle(
                ResolverStyle.STRICT);
        try {
            LocalDate.parse(text, strict);
            System.out.println("Modern STRICT: accepted");
        } catch (DateTimeParseException ex) {
            System.out.println("Modern STRICT: rejected");
        }
    }
}
```

```bash
javac -encoding UTF-8 ParseStrictnessDemo.java
java ParseStrictnessDemo
```

Stdout:

```text
Legacy strict: rejected
Modern SMART: 2026-02-28
Modern STRICT: rejected
```

Trong ví dụ trên:

1. `SimpleDateFormat.setLenient(false)` từ chối ngày 30/2/2026.
2. DateTimeFormatter `SMART` có thể điều chỉnh ngày 30 về cuối tháng 2, tức `2026-02-28`.
3. DateTimeFormatter `STRICT` từ chối cùng input.
4. Formatter mới được tạo qua `withResolverStyle(...)`; đối tượng `smart` ban đầu **không bị sửa**.

Đối với dữ liệu máy đọc/nguồn nghiệp vụ nhạy cảm, không nên âm thầm đổi ngày sai thành ngày hợp lệ. Hãy lựa chọn và kiểm thử strictness một cách tường minh.

## 9. Locale và dữ liệu bản địa hóa khi xuất tên tháng/ngày

Cả hai formatter đều có thể lấy tên tháng hoặc thứ theo locale:

```java
// Fragment, cần các import tương ứng.
SimpleDateFormat legacy =
        new SimpleDateFormat("dd MMMM yyyy", Locale.FRANCE);
DateTimeFormatter modern = DateTimeFormatter.ofPattern(
        "dd MMMM uuuu", Locale.FRANCE);
```

Chuỗi tên tháng có thể tương ứng tiếng Pháp khi runtime có dữ liệu hỗ trợ. **Không tự suy ra** việc đổi locale chỉ ảnh hưởng tên tháng: lịch, quy tắc tuần, chữ số, era và cách diễn đạt AM/PM cũng có thể khác.

- Với `SimpleDateFormat`, truyền `Locale` trong constructor. Sử dụng `setTimeZone` hoặc `Calendar` phù hợp khi đang format `Date`. Nếu bỏ timezone, kết quả có thể phụ thuộc default JVM.
- Với `DateTimeFormatter`, truyền locale vào `ofPattern(pattern, locale)` hoặc dùng `withLocale(locale)`; khi format `LocalDate` không cần timezone, nhưng với `Instant` và pattern ngày/giờ địa phương cần zone.
- Khi định dạng cho UI theo người dùng, truyền **locale tường minh**. Không gọi `Locale.setDefault(...)` trên từng HTTP request vì nó tác động tới toàn JVM.

### Tại sao tên tháng có thể không trùng dù pattern giống?

`SimpleDateFormat` sử dụng `DateFormatSymbols` và lịch cũ, còn `DateTimeFormatter` dựa vào dữ liệu locale và các trường `java.time`. Khi sử dụng JDK/provider hoặc chronology khác, cách viết tháng, hình thức độc lập `L` so với dạng ngữ cảnh `M`, era hoặc tuần có thể khác. Trong test, nên kiểm tra đúng locale và semantically correct output; nếu snapshot chuỗi là yêu cầu sản phẩm, cố định phiên bản JDK/provider/locale data.

Đối với text từ `ResourceBundle`, đừng đặt pattern `"YYYY-MM-dd"` chỉ vì copy từ dữ liệu trước đây. Pattern là một ngôn ngữ mini; người viết bản dịch có thể thay đổi thứ tự và ký tự ngăn cách, nhưng các chữ token phải được review như code.

## 10. Trình tự chuyển một SimpleDateFormat cũ sang DateTimeFormatter

Ví dụ mã cũ:

```java
SimpleDateFormat format = new SimpleDateFormat(
        "yyyy-MM-dd HH:mm:ss.SSS", Locale.US);
format.setTimeZone(TimeZone.getTimeZone("UTC"));
String text = format.format(date);
```

Đây là **fragment** có biến `date` kiểu `java.util.Date` đã được khai báo. Muốn chuyển:

1. **Ghi lại ý nghĩa dữ liệu đầu vào**: `Date` (instant), ngày lịch, local datetime hay thời gian có offset.
2. **Đọc kỹ toàn bộ pattern**, xác định `yyyy`/`YYYY`, `S`, `F`, `u`, `X`, tên zone và những ký hiệu có thể thay nghĩa.
3. **Chọn kiểu Java Time phù hợp**: `Instant` cho thời điểm, `LocalDate` cho ngày lịch, `OffsetDateTime`/`ZonedDateTime` khi có offset/zone.
4. **Chọn locale tường minh** và **zone tường minh** nếu format thời điểm thành ngày giờ địa phương.
5. **Chuyển pattern dựa trên ý nghĩa**, ví dụ `yyyy` → `uuuu` khi muốn proleptic year và parse ngày nghiêm ngặt; `SSS` có thể giữ trong trường hợp milliseconds, nhưng pattern `SSSSSS` phải được thiết kế lại theo precision thật.
6. **Chọn resolver style khi parse**, không mặc định `ofPattern` là STRICT.
7. **Chạy test trên dữ liệu biên**: năm mới/tuần-năm, năm nhuận/ngày sai, tháng 1/12, ngày đổi múi giờ/DST, UTC offset, thời gian có milliseconds/microseconds/nanoseconds, nhiều locale.
8. **Đổi vòng đời formatter**: DateTimeFormatter immutable nên có thể chia sẻ theo cấu hình cố định; tránh tái sử dụng `SimpleDateFormat` mutable giữa nhiều thread.

### Ví dụ Java 17+ chuyển Date thành Instant

Lưu **`MigrationDemo.java`**:

```java
import java.text.SimpleDateFormat;
import java.time.Instant;
import java.time.ZoneOffset;
import java.time.format.DateTimeFormatter;
import java.util.Date;
import java.util.Locale;
import java.util.TimeZone;

public class MigrationDemo {
    public static void main(String[] args) {
        Date date = Date.from(Instant.parse(
                "2026-10-28T10:07:06Z"));

        SimpleDateFormat legacy = new SimpleDateFormat(
                "yyyy-MM-dd HH:mm:ss", Locale.ROOT);
        legacy.setTimeZone(TimeZone.getTimeZone("UTC"));

        DateTimeFormatter modern = DateTimeFormatter
                .ofPattern("uuuu-MM-dd HH:mm:ss", Locale.ROOT)
                .withZone(ZoneOffset.UTC);

        String first = legacy.format(date);
        String second = modern.format(date.toInstant());

        System.out.println("Legacy: " + first);
        System.out.println("Modern: " + second);
        System.out.println("Same text: " + first.equals(second));
    }
}
```

```bash
javac -encoding UTF-8 MigrationDemo.java
java MigrationDemo
```

Stdout:

```text
Legacy: 2026-10-28 10:07:06
Modern: 2026-10-28 10:07:06
Same text: true
```

Đây là phép di trú **có điều kiện rõ**: cùng instant, cùng timezone UTC, cùng trường ngày/giờ và cùng độ chính xác giây. Ở code mới, nếu yêu cầu máy đọc chuẩn quốc tế, cân nhắc dùng `Instant.toString()`/`DateTimeFormatter.ISO_INSTANT` hoặc `ISO_LOCAL_DATE` thay vì phát minh chuỗi date-time riêng khi không cần.

## 11. Thread safety: lý do nên ưu tiên DateTimeFormatter

`SimpleDateFormat` kế thừa `DateFormat` và có trạng thái mutable như `Calendar`, `NumberFormat`, `TimeZone` và cấu hình leniency. Một instance **không được bảo đảm an toàn** khi nhiều luồng gọi `format`/`parse` đồng thời mà không đồng bộ. Các hiện tượng lỗi có thể thay đổi theo tải và khó tái hiện.

`DateTimeFormatter` là immutable và thread-safe. Các phương thức như `withLocale(...)`, `withZone(...)`, `withResolverStyle(...)` trả về formatter mới (hoặc hiệu lực tương đương) mà không biến đổi đối tượng gốc. Nhờ đó có thể dùng `static final DateTimeFormatter` cho một cấu hình bất biến, hoặc tạo formatter theo request khi cần locale.

**Cách thiết kế đúng:**

```java
// Fragment trong một class Java:
private static final DateTimeFormatter WIRE_DAY =
        DateTimeFormatter.ISO_LOCAL_DATE;

static String formatDay(java.time.LocalDate day) {
    return WIRE_DAY.format(day);
}
```

Đối với locale người dùng, không nên lấy một formatter chia sẻ rồi đổi `Locale.setDefault`; dùng `BASE.withLocale(uiLocale)` hoặc tạo formatter theo locale, và giữ các formatter tách biệt nếu zone khác.

Nếu phải giữ `SimpleDateFormat` cho API legacy, hãy tạo instance cho mỗi thao tác/request, hoặc dùng đồng bộ và chiến lược quản lý state phù hợp. `ThreadLocal<SimpleDateFormat>` có thể giải quyết một số trường hợp nhưng tăng công sức quản lý lifecycle; không cần ưu tiên nó nếu có thể chuyển sang java.time.

## 12. Literal trong pattern: dấu nháy đơn và văn bản cố định

Hai API sử dụng dấu nháy đơn để **quote literal**, nhưng vẫn phải đọc tài liệu từng API khi gặp pattern phức tạp. Ký tự `'` thường mở/đóng chuỗi literal; muốn có dấu nháy đơn thật trong output, dùng `''` trong pattern.

Ví dụ:

```java
DateTimeFormatter format = DateTimeFormatter.ofPattern(
        "uuuu-MM-dd 'at' HH:mm", Locale.ROOT);
```

Đây là **fragment**; nếu format một `LocalDateTime` của ngày 28/10/2026 lúc 10:30, đầu ra là `2026-10-28 at 10:30`.

**Không chèn tên tháng/trường giờ như text chưa quote**. Chữ `T` giữa ngày và giờ là một literal trong ISO datetime, nhưng pattern tự viết kiểu `uuuu-MM-ddTHH:mm` sẽ khiến DateTimeFormatter coi `T` như pattern letter chưa hợp lệ. Viết `"uuuu-MM-dd'T'HH:mm"` nếu muốn ký tự `T` thật; tốt hơn, dùng các predefined ISO formatters khi phù hợp.

**Lưu ý:** các chuỗi date-time từ người dùng hoặc bundle có thể chứa dấu `'` cho ngôn ngữ tự nhiên. Nếu nội dung là dữ liệu literal chứ không phải pattern, đừng đưa thẳng vào `ofPattern`. Hãy tách *pattern đáng tin cậy* khỏi *text untrusted* để tránh lỗi cú pháp và nguy cơ làm hỏng đầu ra.

## 13. Những lỗi phổ biến khi copy pattern từ API cũ

| Sai lầm | Hậu quả | Cách xử lý |
| --- | --- | --- |
| Sao chép `yyyy-MM-dd` rồi dùng parse STRICT ở DateTimeFormatter | Thiếu era, không resolve được `LocalDate` | Dùng `uuuu-MM-dd` hoặc ISO predefined |
| Dùng `YYYY-MM-dd` cho ngày lịch | Sai năm gần ranh giới tuần-năm | Dùng năm lịch; tránh `Y` trừ khi biểu diễn lịch tuần |
| Sao chép `SSSSSS` | Milli giây đệm số khác sáu chữ số phần giây | Định nghĩa lại precision và chuyển đúng trường |
| Đổi `SimpleDateFormat("u")` sang `ofPattern("u")` | Từ **thứ trong tuần** thành **proleptic year** | Chuyển theo ngữ nghĩa, không theo ký tự |
| Giữ `F` không xem lại nghĩa | Hai API diễn giải khác | Chọn trường thời gian đúng nghiệp vụ |
| Dùng `mm` để in tháng | Thực tế là phút | Dùng `MM` |
| Dùng `DD` thay cho `dd` | Ngày thứ N trong năm thay vì ngày trong tháng | Dùng `dd` |
| Coi `DateTimeFormatter.ofPattern` mặc định STRICT | SMART có thể điều chỉnh ngày sai | Dùng `withResolverStyle(STRICT)` khi cần |
| Format `LocalDateTime` bằng `XXX` | Không có offset để xuất | Chọn `OffsetDateTime`/zone rõ |
| Format `Instant` bằng pattern local mà không có zone | Thiếu trường lịch địa phương | `withZone(ZoneId)` |
| Không chỉ định TimeZone cho SimpleDateFormat | Kết quả phụ thuộc default JVM | `setTimeZone` rõ |
| Tạo static SimpleDateFormat dùng cho nhiều request | Không thread-safe | Formatter riêng hoặc chuyển sang immutable DateTimeFormatter |
| Dùng `parse(String)` của DateFormat để xác nhận toàn bộ input | Có thể bỏ đuôi thừa | ParsePosition + validation |
| Quên quote literal `T` | Lỗi pattern không hợp lệ | `'T'` trong pattern hoặc ISO formatter |
| Dùng tên timezone rút gọn làm khóa lưu trữ | Mơ hồ/locale-dependent | Lưu ZoneId/offset/Instant theo schema |
| Tin ngày lịch bằng midnight UTC | Có thể sai nghĩa khi đổi timezone | Dùng LocalDate cho ngày thuần |

## 14. Kiểm thử pattern khi di trú

Một test suite đủ tốt nên có:

1. **Ngày bình thường:** so cùng instant, cùng zone, cùng locale và precision giữa hai formatter.
2. **Ngày cuối năm/đầu năm:** kiểm tra `yyyy`/`YYYY`/`uuuu`; thử locale có quy tắc tuần khác nhau.
3. **Ngày không hợp lệ:** 30/2, 31/4, năm nhuận và parsing STRICT vs SMART vs lenient.
4. **Fractions:** 000 ms, 007 ms, 123 ms, 999 ms, và thời điểm có micro/nanoseconds. So `SSS` và `SSSSSS`.
5. **Time zone/offset:** UTC `Z`, `+07:00`, vùng có DST; format và parse offset theo pattern tương ứng.
6. **Locale:** tên tháng đầy đủ và viết tắt; AM/PM; lịch tuần; test trên dữ liệu locale/provider mục tiêu.
7. **Input dài/bất thường:** extra trailing chars, thiếu trường, giá trị ngoài phạm vi, literal trong pattern.
8. **Đa luồng:** chỉ chia sẻ DateTimeFormatter immutable; không dùng cùng SimpleDateFormat mutable nếu thiếu đồng bộ.
9. **Nguồn legacy:** các cấu hình calendar (Gregorian cutover, calendar khác) và timezone trong chương trình cũ có thể khác chronology ISO của `java.time`. Với ngày lịch sử trước khoảng chuyển đổi Gregorian/Julian hoặc lịch không theo ISO, không kỳ vọng kết quả giống nhau mà không chuyển đổi rõ hệ lịch.
10. **Contract dữ liệu:** với file/API, ưu tiên ISO formatters ổn định, dùng strict parsing cho trường ngày, không để default locale/timezone quyết định cách hiểu dữ liệu.

### Bài tập 1 — Xác định token sai

Cho các pattern `"YYYY-MM-dd"`, `"yyyy-MM-DD"`, `"yyyy-mm-dd"`, `"uuuu-MM-dd"`. Hãy nêu ký tự nào là năm lịch, năm tuần, tháng, phút, ngày trong tháng và ngày trong năm. Với DateTimeFormatter, pattern nào phù hợp hơn để parse ISO LocalDate STRICT?

### Bài tập 2 — Phần lẻ của giây

Cho `Instant.parse("2026-10-28T10:07:06.123Z")`. Dự đoán kết quả `SSS` và `SSSSSS` khi format bằng SimpleDateFormat UTC/Date và DateTimeFormatter UTC/Instant. Đổi đầu vào sang một Instant có `123456789` nanoseconds rồi giải thích vì sao `Date` không thể giữ nguyên toàn bộ độ chính xác nano.

### Bài tập 3 — Parse ngày sai

Với `"2026-02-30"`, dùng `SimpleDateFormat.setLenient(false)`, `DateTimeFormatter.ofPattern("uuuu-MM-dd")` mặc định, và formatter đó với `ResolverStyle.STRICT`. So sánh hành vi, xác định chế độ phù hợp cho dữ liệu máy đọc.

### Bài tập 4 — Zone và Locale

Định dạng một instant giống nhau theo UTC và `+07:00`, với mẫu có offset `XXX`. Giải thích vì sao `LocalDateTime` không thể tự cung cấp offset. Sau đó dùng locale `en-US` và `fr-FR` khi in tên tháng, kiểm tra output với JDK đang dùng.

## 15. Tài liệu chính thức

- [Java SE 21 — SimpleDateFormat](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/text/SimpleDateFormat.html): pattern letters, `S`, `u`, `F`, timezone và tính không đồng bộ.
- [Java SE 21 — DateTimeFormatter](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/format/DateTimeFormatter.html): pattern letters, `S`, `u`, `Y`, `X`, resolver style, `ofPattern`, `withZone`.
- [Java SE 21 — ResolverStyle](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/format/ResolverStyle.html): `STRICT`, `SMART`, `LENIENT`.
- [Java SE 21 — LocalDate](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/LocalDate.html): ngày lịch và parsing.
- [Java SE 21 — Instant](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/Instant.html): thời điểm UTC.

## 16. Ghi nhớ

- Pattern `SimpleDateFormat` và `DateTimeFormatter` **giống một phần, không tương đương 1–1**.
- `yyyy` trong DateTimeFormatter là **year-of-era**; `uuuu` là **proleptic year**; `YYYY` là **week-based-year**. `SimpleDateFormat` lại dùng `u` cho **thứ trong tuần**.
- `S` trong SimpleDateFormat là **milliseconds**; trong DateTimeFormatter là **fraction-of-second**. `SSS` có thể giống nhau, nhưng `SSSSSS` cho hai cách biểu diễn khác.
- `SimpleDateFormat` mutable và không thread-safe; `DateTimeFormatter` immutable và thread-safe.
- Parse `SimpleDateFormat` và `DateTimeFormatter` có chính sách khác: `setLenient(false)`, `ResolverStyle.SMART`, `ResolverStyle.STRICT` không phải những nút thay thế trực tiếp.
- Offset và zone không phải một thứ. `XXX` cần dữ liệu offset; `Instant` cần một zone để format các thành phần ngày/giờ địa phương.
- Khi di trú, **xác định ngữ nghĩa dữ liệu và từng token**, chọn locale/zone rõ, dùng các ISO formatter có sẵn khi trao đổi máy-máy và kiểm thử nhiều ngày/locale/timezone, nhất là vùng biên.