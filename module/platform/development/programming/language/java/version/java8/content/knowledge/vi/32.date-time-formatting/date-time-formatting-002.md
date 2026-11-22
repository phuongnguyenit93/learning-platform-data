# ofPattern và thành phần pattern — DateTimeFormatter (Java 8+)

> **Chủ đề:** Định dạng ngày giờ. `DateTimeFormatter.ofPattern` thuộc `java.time.format`, xuất hiện trong Java 8 và vẫn là API hiện hành để định dạng/đọc ngày giờ theo cấu trúc xác định. Bài tập trung vào **pattern letters**, phân biệt năm/tháng/ngày với giờ/phút/giây, locale, offset/zone, phần optional, parsing strict và lỗi thực tế.

## 1. Học được gì?

Bạn sẽ biết đọc và viết các pattern như `dd/MM/uuuu`, `EEE, d MMM uuuu`, `hh:mm a`, `uuuu-MM-dd'T'HH:mm:ssXXX`; phân biệt `u/y/Y`, `M/m`, `d/D`, `H/h`, `s/S`; dùng `Locale` đúng chỗ; chọn `ResolverStyle.STRICT` để xác thực đầu vào; và chọn kiểu `LocalDate`, `LocalDateTime`, `OffsetDateTime`, `ZonedDateTime` phù hợp.

## 2. Formatter là một đối tượng hai chiều, immutable và thread-safe

```java
LocalDate date = LocalDate.of(2024, 2, 29);
DateTimeFormatter f = DateTimeFormatter.ofPattern("dd/MM/uuuu");

String text = date.format(f);            // "29/02/2024".
LocalDate parsed = LocalDate.parse(text, f); // 2024-02-29.
```

`date.format(f)` và `f.format(date)` đều format cùng temporal. `LocalDate.parse(text, f)` dùng formatter để đọc text thành ngày ISO. Một `DateTimeFormatter` immutable có thể tái sử dụng an toàn giữa threads; `withLocale`, `withZone`, `withResolverStyle` trả bản formatter khác, không sửa bản gốc.

**Không phải mọi temporal đều có mọi trường.** `LocalDate` không có giờ; `LocalDateTime` không có offset hay ZoneId. Nếu pattern cần `XXX`/`VV` thì cần temporal hoặc cấu hình zone/offset thích hợp. Pattern không tự suy ra timezone của một giờ địa phương.

## 3. Tạo formatter và cấu hình locale

```java
DateTimeFormatter numberDate =
        DateTimeFormatter.ofPattern("dd/MM/uuuu", Locale.ROOT);

DateTimeFormatter englishText =
        DateTimeFormatter.ofPattern(
                "EEE, d MMM uuuu", Locale.ENGLISH);

DateTimeFormatter strict = numberDate
        .withResolverStyle(ResolverStyle.STRICT);
```

`ofPattern(String)` dùng default FORMAT locale khi cần tên ngày, tháng, AM/PM; overload `ofPattern(String,Locale)` cho phép cố định ngôn ngữ. `Locale.ROOT` phù hợp khi pattern chỉ chứa số và dấu phân cách, `Locale.ENGLISH` hợp lý nếu giao thức quy định chữ như `Feb`. Locale **không phải múi giờ**; `Locale.ENGLISH` không chuyển timestamp sang London.

Pattern không hợp lệ (sai ký hiệu, độ rộng ký hiệu không cho phép, dấu nháy bị thiếu) có thể ném `IllegalArgumentException` khi tạo formatter. Dữ liệu không parse được hoặc không thể giải thành ngày giờ hợp lệ có thể ném `DateTimeParseException`. Hãy kiểm tra cả hai loại lỗi ở nơi thích hợp.

## 4. Thành phần ngày, tháng, năm và tuần

| Ký hiệu | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| `u` / `uuuu` | Năm ISO kiểu proleptic year | 2024 |
| `y` / `yyyy` | Year-of-era, năm tính theo niên đại | 2024 (CE) |
| `G` | Era | AD tùy Locale |
| `Y` / `YYYY` | **Week-based-year**, không phải năm lịch | Có thể nhảy năm ở cuối tháng 12 |
| `M` | Tháng dạng số | 2 |
| `MM` | Tháng dạng số có zero-padding | 02 |
| `MMM` | Tên tháng viết tắt | Feb (English) |
| `MMMM` | Tên tháng đầy đủ | February (English) |
| `L` / `LLLL` | Tháng dạng stand-alone | Tùy Locale |
| `d` / `dd` | Ngày trong **tháng** | 9 / 09 |
| `D` / `DDD` | Ngày trong **năm** | 060 vào 29/2/2024 |
| `E` / `EEE` / `EEEE` | Thứ dạng chữ | Thu / Thursday |
| `e` / `c` | Thứ dạng số/chữ phụ thuộc Locale | Phụ thuộc ngày bắt đầu tuần |
| `w` / `W` | Tuần trong week-year / tháng | Phụ thuộc Locale |
| `Q` / `q` | Quý dạng số hoặc text | Q1 theo độ rộng |

**Độ rộng không chỉ để thêm số 0.** `M` có thể hiện 2, `MM` hiện 02, `MMM` thành tên ngắn, `MMMM` thành tên đầy đủ và `MMMMM` thường là tên cực ngắn. Nhiều pattern number dùng độ rộng để quy định số chữ số khi parse; hãy test input một/chẵn hai chữ số theo giao thức.

### 4.1. `uuuu` khác `yyyy` và `YYYY`

- `uuuu` biểu diễn **proleptic year** của lịch ISO; phù hợp với `LocalDate` và `ResolverStyle.STRICT`.
- `yyyy` biểu diễn **year-of-era**. Trong năm CE thường format giống `uuuu`, nhưng strict parsing một năm `yyyy` mà không có trường era có thể không đủ thông tin để tạo `LocalDate`.
- `YYYY` là **week-based-year**, liên quan quy tắc tuần/Locale. Không dùng nó để định dạng năm của ngày lịch thông thường.

```java
DateTimeFormatter strict = DateTimeFormatter
        .ofPattern("dd/MM/uuuu", Locale.ROOT)
        .withResolverStyle(ResolverStyle.STRICT);

LocalDate date = LocalDate.parse("29/02/2024", strict);
// 2024-02-29.
```

Ví dụ `Locale.US` cho ngày gần giao năm:

```java
LocalDate boundary = LocalDate.of(2021, 12, 26);

String normal = boundary.format(
        DateTimeFormatter.ofPattern("uuuu-MM-dd", Locale.US));
// 2021-12-26.

String week = boundary.format(
        DateTimeFormatter.ofPattern("YYYY-'W'ww-e", Locale.US));
// 2022-W01-1.
```

Ở đây 26/12/2021 thuộc tuần đầu của week-based-year **2022** theo quy tắc Locale.US. Nếu dùng `YYYY-MM-dd` cho ngày giao dịch, năm có thể sai. Muốn quy tắc tuần ISO (thứ Hai là đầu tuần, tối thiểu 4 ngày trong tuần đầu), dùng `WeekFields.ISO` hoặc formatter/locale được thiết kế và kiểm thử đúng yêu cầu.

### 4.2. `dd` khác `DD`; `MM` khác `mm`

`dd` là ngày trong tháng, `DDD` là ngày trong năm. `MM` là tháng, còn `mm` là phút. Pattern `dd/MM/uuuu` không thể đổi chữ hoa/thường thành `DD/mm/uuuu` mà giữ nguyên ý nghĩa.

### 4.3. Năm có hai chữ số

`yy` và `uu` thường dùng cơ chế *reduced-year* với dải mặc định liên quan thế kỷ 2000–2099. Dữ liệu dạng `24` không đủ chắc chắn cho các mốc lịch sử hay lịch kéo dài qua thế kỷ. Với dữ liệu trao đổi, ưu tiên năm đủ bốn chữ số `uuuu` và kiểm thử tại ranh giới năm.

## 5. Thành phần giờ, phút, giây và độ chính xác

| Ký hiệu | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| `H` / `HH` | Giờ dạng 24h, 0–23 | 9 / 09 |
| `h` / `hh` | Giờ dạng 12h, 1–12 | 3 / 03 |
| `K` | Hour-of-AMPM, 0–11 | 0 |
| `k` | Clock-hour-of-day, 1–24 | 24 có thể biểu diễn nửa đêm |
| `a` | AM/PM (text theo Locale) | PM |
| `m` / `mm` | Phút trong giờ, 0–59 | 5 / 05 |
| `s` / `ss` | Giây trong phút, 0–59 | 7 / 07 |
| `S` / `SSS` | Phần thập phân của giây | 1–9 chữ số |
| `n` | Nano-of-second | 123456789 |
| `N` | Nano-of-day | Số nano từ đầu ngày |
| `A` | Milli-of-day | Số mili-giây từ đầu ngày |

```java
LocalTime time = LocalTime.of(15, 7);

String h24 = time.format(
        DateTimeFormatter.ofPattern("HH:mm", Locale.ENGLISH));
// "15:07".

String h12 = time.format(
        DateTimeFormatter.ofPattern("hh:mm a", Locale.ENGLISH));
// "03:07 PM".
```

Không dùng `hh:mm` mà bỏ `a` nếu muốn biểu diễn thời điểm đủ thông tin: 03:07 sáng và chiều sẽ không phân biệt. `H` và `h`, `k` và `K` có phạm vi khác nhau, không thay thế tùy ý.

### 5.1. `SSS` là ba chữ số phần giây, không phải ba chữ số “milli bất kỳ”

```java
LocalTime t = LocalTime.of(9, 5, 7, 123_456_789);
String result = t.format(
        DateTimeFormatter.ofPattern("HH:mm:ss.SSS", Locale.ROOT));
// "09:05:07.123".
```

`SSS` chỉ in ba chữ số đầu của phần giây, **không làm tròn thành 124**. Nếu parse lại text `.123`, phần nano thường thành `123000000`; các chữ số thấp hơn bị mất. Pattern phải chọn precision theo yêu cầu log/storage.


## 6. Offset, ZoneId và pattern timezone

| Ký hiệu | Ý nghĩa | Ghi nhớ |
| --- | --- | --- |
| `X` / `XX` / `XXX` | UTC offset theo ISO | `XXX` thường biểu diễn `+07:00`, zero offset là `Z` |
| `x` / `xx` / `xxx` | ISO offset variant | Zero offset không in `Z`, dùng dạng `+00...` |
| `Z` | UTC offset theo các biến thể RFC/ISO | Cách in phụ thuộc số `Z` |
| `O` | Localized offset có tiền tố GMT | Ví dụ GMT+... |
| `VV` | **Zone ID** | `Asia/Ho_Chi_Minh` |
| `z` / `zzzz` | Tên múi giờ theo Locale | Có thể thay đổi theo DST/Locale |
| `v` | Tên generic zone | Tùy Locale/zone rules |

```java
OffsetDateTime odt = OffsetDateTime.parse(
        "2024-02-29T09:05:07+07:00");

ZonedDateTime zdt = ZonedDateTime.parse(
        "2024-02-29T09:05:07+07:00[Asia/Ho_Chi_Minh]");
```

`XXX` chỉ in **con số UTC offset**; `VV` chỉ in **zone identifier**. Cùng offset `+07:00` không chứng minh vùng là Việt Nam, vì nhiều vùng có thể chia sẻ offset ở một thời điểm.

### 6.1. Format `XXX VV` từ `LocalDateTime` sẽ không có đủ dữ liệu

```java
LocalDateTime local = LocalDateTime.of(2024, 2, 29, 9, 5);
DateTimeFormatter withZone = DateTimeFormatter.ofPattern(
        "uuuu-MM-dd HH:mm XXX VV");

// local.format(withZone) sẽ thất bại do thiếu offset/ZoneId.
```

`LocalDateTime` không có zone, nên không tự biết `XXX` và `VV`. Nếu nguồn có offset thì dùng `OffsetDateTime`, nếu có region ZoneId thì dùng `ZonedDateTime`. Khi đã có `Instant`, có thể dùng `formatter.withZone(ZoneId.of(...))` để hiển thị tại vùng mong muốn.

### 6.2. ISO chuẩn thường tốt hơn pattern tự thiết kế

Có sẵn `DateTimeFormatter.ISO_LOCAL_DATE`, `ISO_LOCAL_TIME`, `ISO_LOCAL_DATE_TIME`, `ISO_OFFSET_DATE_TIME`, `ISO_ZONED_DATE_TIME`, `ISO_INSTANT` và `RFC_1123_DATE_TIME`. Với API hoặc lưu trữ, ưu tiên một format chuẩn được quy định rõ. `ofLocalizedDate(...)` thích hợp UI theo Locale nhưng không nên được dùng làm giao thức văn bản byte-stable giữa các hệ thống.

## 7. Literal, escape và optional sections

Chữ cái Latin trong pattern có thể là ký hiệu trường hoặc là ký tự sai pattern. Muốn in text cố định, hãy bao nó bằng dấu nháy đơn:

```java
DateTimeFormatter isoLike =
        DateTimeFormatter.ofPattern("uuuu-MM-dd'T'HH:mm:ss");

DateTimeFormatter labelled =
        DateTimeFormatter.ofPattern("'Date:' dd/MM/uuuu", Locale.ROOT);
```

`'T'` là một ký tự T nguyên văn; `'Date:'` in nguyên văn `Date:`. Muốn in dấu apostrophe trong literal, dùng hai dấu nháy đơn liên tiếp `''`. Các dấu phân cách như `-`, `/`, `:` thường là literal, nhưng không coi mọi ký hiệu dấu câu đều luôn có thể dùng tự do; dấu `[ ]` có nghĩa đặc biệt.

**`[ ... ]` định nghĩa đoạn tùy chọn:**

```java
DateTimeFormatter optional =
        DateTimeFormatter.ofPattern("uuuu-MM-dd['T'HH:mm]");

LocalDate day = LocalDate.parse("2024-02-29", optional);
LocalDateTime dateTime =
        LocalDateTime.parse("2024-02-29T09:05", optional);
```

Đoạn `'T'HH:mm` có thể được đọc hoặc bỏ qua. Nhưng `LocalDateTime.parse("2024-02-29",optional)` vẫn không đủ giờ/phút để tạo LocalDateTime; optional **không tự cấp giá trị mặc định**. Nếu cần nhận cả hai kiểu, có thể dùng `parseBest(text, LocalDateTime::from, LocalDate::from)` rồi xử lý theo kiểu thực tế.

## 8. SMART và STRICT là khác nhau

Parse diễn ra theo hai giai đoạn: (1) phân tích text thành field-value, rồi (2) **resolve** các field thành ngày/giờ hợp lệ. `DateTimeFormatter.ofPattern` có resolver style mặc định **SMART**.

```java
DateTimeFormatter smart = DateTimeFormatter.ofPattern(
        "dd/MM/uuuu", Locale.ROOT);

LocalDate adjusted = LocalDate.parse("31/04/2024", smart);
// SMART trả 2024-04-30.
```

Nếu nghiệp vụ cần **từ chối ngày sai** thay vì điều chỉnh thành cuối tháng:

```java
DateTimeFormatter strict = DateTimeFormatter
        .ofPattern("dd/MM/uuuu", Locale.ROOT)
        .withResolverStyle(ResolverStyle.STRICT);

LocalDate valid = LocalDate.parse("29/02/2024", strict);

try {
    LocalDate.parse("31/04/2024", strict);
    throw new AssertionError("Ngày không hợp lệ phải bị từ chối");
} catch (DateTimeParseException expected) {
    // Đúng: 31/4 không tồn tại.
}
```

`ResolverStyle.LENIENT` có quy tắc giải trường lỏng hơn; không nên chọn cho validation dữ liệu chính thức trừ khi giao thức thật sự cho phép normalize ngày tràn. `ResolverStyle` không phải chính sách case-sensitive: nếu cần parse text không phân biệt hoa/thường, dùng `DateTimeFormatterBuilder.parseCaseInsensitive` theo thiết kế.

**Bẫy `yyyy`:** `DateTimeFormatter.ofPattern("dd/MM/yyyy", Locale.ROOT).withResolverStyle(STRICT)` có thể thất bại khi parse LocalDate vì `yyyy` đưa ra YEAR_OF_ERA nhưng không có ERA. `uuuu` là lựa chọn thuận tiện cho ngày ISO strict.

## 9. Thực hành: code Java 8 chạy được

Tạo file **`PatternFormatterDemo.java`**. Chương trình kiểm tra format/parse round-trip, literal, locale, giờ 12h, nano, zone, optional, SMART/STRICT, year-of-era và week-based-year, dùng dữ liệu cố định để stdout có thể lặp lại.

```java
import java.time.DateTimeException;
import java.time.LocalDate;
import java.time.LocalDateTime;
import java.time.LocalTime;
import java.time.OffsetDateTime;
import java.time.ZoneId;
import java.time.ZonedDateTime;
import java.time.format.DateTimeFormatter;
import java.time.format.DateTimeParseException;
import java.time.format.ResolverStyle;
import java.util.Locale;

public class PatternFormatterDemo {
    public static void main(String[] args) {
        LocalDate leap = LocalDate.of(2024, 2, 29);
        DateTimeFormatter strictDate =
                DateTimeFormatter.ofPattern("dd/MM/uuuu", Locale.ROOT)
                        .withResolverStyle(ResolverStyle.STRICT);
        String dateText = leap.format(strictDate);
        LocalDate roundTrip = LocalDate.parse(dateText, strictDate);

        String english = leap.format(
                DateTimeFormatter.ofPattern("EEE, d MMM uuuu", Locale.ENGLISH));
        String twelveHour = LocalTime.of(15, 7).format(
                DateTimeFormatter.ofPattern("hh:mm a", Locale.ENGLISH));
        String literal = leap.format(
                DateTimeFormatter.ofPattern("'Date:' dd/MM/uuuu", Locale.ROOT));

        ZonedDateTime zoned = ZonedDateTime.of(
                2024, 2, 29, 9, 5, 7, 123_456_789,
                ZoneId.of("Asia/Ho_Chi_Minh"));
        DateTimeFormatter zonedPattern = DateTimeFormatter.ofPattern(
                "uuuu-MM-dd HH:mm:ss.SSS XXX 'at' VV", Locale.ENGLISH);
        String zonedText = zoned.format(zonedPattern);
        ZonedDateTime zonedParsed =
                ZonedDateTime.parse(zonedText, zonedPattern);

        DateTimeFormatter offsetPattern =
                DateTimeFormatter.ofPattern("uuuu-MM-dd'T'HH:mm:ssXXX",
                        Locale.ROOT);
        OffsetDateTime parsedOffset = OffsetDateTime.parse(
                "2024-02-29T09:05:07+07:00", offsetPattern);

        DateTimeFormatter optional = DateTimeFormatter.ofPattern(
                "uuuu-MM-dd['T'HH:mm]", Locale.ROOT);
        LocalDate dateOnly = LocalDate.parse("2024-02-29", optional);
        LocalDateTime withTime =
                LocalDateTime.parse("2024-02-29T09:05", optional);

        DateTimeFormatter smartDate =
                DateTimeFormatter.ofPattern("dd/MM/uuuu", Locale.ROOT);
        LocalDate smartAdjusted =
                LocalDate.parse("31/04/2024", smartDate);

        boolean strictRejected = false;
        try {
            LocalDate.parse("31/04/2024", strictDate);
        } catch (DateTimeParseException expected) {
            strictRejected = true;
        }

        boolean yearOfEraRejected = false;
        try {
            LocalDate.parse("29/02/2024",
                    DateTimeFormatter.ofPattern("dd/MM/yyyy", Locale.ROOT)
                            .withResolverStyle(ResolverStyle.STRICT));
        } catch (DateTimeParseException expected) {
            yearOfEraRejected = true;
        }

        boolean noOffsetRejected = false;
        try {
            LocalDateTime.of(2024, 2, 29, 9, 5)
                    .format(zonedPattern);
        } catch (DateTimeException expected) {
            noOffsetRejected = true;
        }

        LocalDate yearBoundary = LocalDate.of(2021, 12, 26);
        String usWeek = yearBoundary.format(
                DateTimeFormatter.ofPattern("YYYY-'W'ww-e", Locale.US));

        String fraction = LocalTime.of(9, 5, 7, 123_456_789).format(
                DateTimeFormatter.ofPattern("HH:mm:ss.SSS", Locale.ROOT));

        System.out.println("Strict round-trip: " + dateText
                + " -> " + roundTrip);
        System.out.println("English weekday/month: " + english);
        System.out.println("12-hour time: " + twelveHour);
        System.out.println("Quoted literal: " + literal);
        System.out.println("Region/offset pattern: " + zonedText);
        System.out.println("Parsed ZonedDateTime: " + zonedParsed);
        System.out.println("Parsed OffsetDateTime: " + parsedOffset);
        System.out.println("Optional date: " + dateOnly);
        System.out.println("Optional date-time: " + withTime);
        System.out.println("SMART 31/04: " + smartAdjusted);
        System.out.println("STRICT invalid rejected: " + strictRejected);
        System.out.println("STRICT yyyy without era rejected: "
                + yearOfEraRejected);
        System.out.println("Missing zone/offset rejected: " + noOffsetRejected);
        System.out.println("US week-year boundary: " + usWeek);
        System.out.println("Fraction SSS: " + fraction);

        if (!roundTrip.equals(leap)
                || !english.equals("Thu, 29 Feb 2024")
                || !twelveHour.equals("03:07 PM")
                || !literal.equals("Date: 29/02/2024")
                || !zonedText.equals(
                    "2024-02-29 09:05:07.123 +07:00 at Asia/Ho_Chi_Minh")
                || !zonedParsed.equals(zoned.withNano(123_000_000))
                || !parsedOffset.toString().equals(
                    "2024-02-29T09:05:07+07:00")
                || !dateOnly.equals(leap)
                || !withTime.equals(LocalDateTime.of(2024,2,29,9,5))
                || !smartAdjusted.equals(LocalDate.of(2024,4,30))
                || !strictRejected || !yearOfEraRejected
                || !noOffsetRejected
                || !usWeek.equals("2022-W01-1")
                || !fraction.equals("09:05:07.123")) {
            throw new AssertionError("Pattern example failed");
        }
        System.out.println("Checks passed.");
    }
}
```

Biên dịch/chạy trên JDK 17+ và kiểm tra tương thích ngôn ngữ/API Java 8:

```bash
javac --release 8 PatternFormatterDemo.java
java PatternFormatterDemo
```

**Stdout đã kiểm chứng trên OpenJDK 24:**

```text
Strict round-trip: 29/02/2024 -> 2024-02-29
English weekday/month: Thu, 29 Feb 2024
12-hour time: 03:07 PM
Quoted literal: Date: 29/02/2024
Region/offset pattern: 2024-02-29 09:05:07.123 +07:00 at Asia/Ho_Chi_Minh
Parsed ZonedDateTime: 2024-02-29T09:05:07.123+07:00[Asia/Ho_Chi_Minh]
Parsed OffsetDateTime: 2024-02-29T09:05:07+07:00
Optional date: 2024-02-29
Optional date-time: 2024-02-29T09:05
SMART 31/04: 2024-04-30
STRICT invalid rejected: true
STRICT yyyy without era rejected: true
Missing zone/offset rejected: true
US week-year boundary: 2022-W01-1
Fraction SSS: 09:05:07.123
Checks passed.
```

**Diễn giải:** `Strict round-trip` chứng minh dữ liệu ngày hợp lệ được format và đọc ngược chính xác. `Region/offset pattern` có `XXX` in `+07:00` và `VV` in ID vùng. `SSS` giữ ba chữ số nano đầu, nên parse lại có nano `123000000`, thấp hơn precision của giá trị gốc. `SMART` nhận 31/4 rồi điều chỉnh 30/4, còn `STRICT` từ chối. `YYYY` cho week-year 2022 trong khi ngày lịch vẫn thuộc 2021. `LocalDateTime` không có offset/zone nên không thể format pattern yêu cầu cả hai.

## 10. Lỗi thường gặp và cách sửa

| Sai lầm | Hậu quả | Cách sửa |
| --- | --- | --- |
| Dùng `YYYY-MM-dd` cho ngày lịch | Năm có thể sai ở tuần cuối năm | `uuuu-MM-dd` |
| `yyyy` + STRICT không có era | Không giải được YEAR_OF_ERA | `uuuu` hoặc xử lý `G` |
| `mm` thay `MM` | Biến tháng thành phút | `MM` tháng, `mm` phút |
| `DD` thay `dd` | Ngày trong năm thay ngày tháng | `dd` cho day-of-month |
| `hh:mm` không có `a` | Mất sáng/chiều | `HH:mm` hoặc `hh:mm a` |
| `SSS` nhưng mong giữ 9 chữ số nano | Mất precision thấp hơn milli-giây | Độ rộng phù hợp hoặc ISO format |
| Text có tháng tiếng Anh nhưng Locale khác | Parse sai | `Locale.ENGLISH` |
| Coi `XXX` là ID vùng | Chỉ in offset | `VV` in ZoneId |
| `XXX VV` từ `LocalDateTime` | Thiếu offset/zone | `ZonedDateTime` phù hợp |
| SMART được coi là strict input validation | 31/4 có thể thành 30/4 | `ResolverStyle.STRICT` |
| Optional `[HH:mm]` tự tạo giờ mặc định | Thiếu trường vẫn thiếu | Dùng kiểu parse phù hợp |
| Dùng `SimpleDateFormat` mutable chung threads | Không thread-safe | `DateTimeFormatter` |
| Localized UI format làm protocol ổn định | Text đổi theo Locale/runtime | ISO formatter và hợp đồng rõ |

## 11. Bài tập có đáp án

**1.** Đọc `"31/12/2024"` và từ chối 31/4? — `DateTimeFormatter.ofPattern("dd/MM/uuuu",Locale.ROOT).withResolverStyle(STRICT)`.

**2.** In 29/2/2024 thành `"Thu, 29 Feb 2024"`? — `ofPattern("EEE, d MMM uuuu",Locale.ENGLISH)`.

**3.** In 15:07 thành `03:07 PM`? — `ofPattern("hh:mm a", Locale.ENGLISH)`.

**4.** Tại sao `YYYY` khác `uuuu`? — `YYYY` là week-based-year theo quy tắc đánh số tuần/Locale.

**5.** Dùng gì để in offset `+07:00`? — `XXX`, nhưng temporal phải có offset.

**6.** Dùng gì để in `Asia/Ho_Chi_Minh`? — `VV` trên temporal có ZoneId.

**7.** Có parse date-only thành LocalDateTime bằng optional time mà không mặc định giờ không? — Không, thiếu dữ liệu giờ/phút vẫn thiếu.

**8.** `SSS` cho nano `123456789` hiển thị gì? — `123`, không làm tròn.

**9.** Một formatter STRICT được tạo với `dd/MM/yyyy` có thể thiếu gì? — ERA, vì `y` là year-of-era; dùng `uuuu` khi parse năm ISO.

## 12. Tài liệu chính thống còn áp dụng

- [Oracle Java SE 25 — DateTimeFormatter](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/time/format/DateTimeFormatter.html): pattern letters, ISO formatters, locale và resolver style.
- [Oracle Java SE 25 — DateTimeFormatterBuilder](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/time/format/DateTimeFormatterBuilder.html): literals, optional sections, parseCaseInsensitive và parse strict.
- [Oracle Java SE 25 — ResolverStyle](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/time/format/ResolverStyle.html): STRICT, SMART và LENIENT.
- [Oracle Java SE 25 — LocalDate](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/time/LocalDate.html), [ZonedDateTime](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/time/ZonedDateTime.html): kiểu nguồn dữ liệu tương ứng.
- [Oracle Java SE 8 — DateTimeFormatter](https://docs.oracle.com/javase/8/docs/api/java/time/format/DateTimeFormatter.html): đối chiếu API nền tảng từ Java 8.

**Ghi nhớ:** Pattern là **ngôn ngữ định nghĩa các trường ngày giờ**, không chỉ mẫu text. `uuuu` biểu diễn năm ISO, `MM` là tháng, `mm` là phút, `HH` là giờ 24h, `XXX` là offset và `VV` là ZoneId. Luôn xem kiểu temporal, Locale, quy tắc parsing và precision trước khi đưa pattern vào API production.
