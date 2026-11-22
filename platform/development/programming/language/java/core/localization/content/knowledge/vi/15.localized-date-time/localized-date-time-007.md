# withZone, withChronology và withDecimalStyle trong DateTimeFormatter (Java)

## 1. Ba lớp cấu hình khác nhau của ngày giờ bản địa

`java.time.format.DateTimeFormatter` là API định dạng/phân tích ngày giờ trong Java 8+ (bao gồm Java 17). Ngoài pattern và `Locale`, formatter còn có ba kiểu override quan trọng:

- **`withZone(ZoneId)`**: đặt **múi giờ ghi đè** để formatter xử lý một thời điểm hoặc cung cấp zone trong một số trường hợp format/parse. Nó không thay đổi `Instant` nguồn và không làm thay đổi múi giờ mặc định của JVM.
- **`withChronology(Chronology)`**: đặt **hệ lịch** dùng trong quá trình biểu diễn hoặc phân tích, ví dụ ISO/Gregorian kiểu ISO-8601, lịch Nhật, lịch Phật giáo Thái Lan. Nó không phải thao tác đổi múi giờ.
- **`withDecimalStyle(DecimalStyle)`**: đặt **cách biểu diễn chữ số và ký hiệu số** (zero digit, dấu cộng, dấu trừ, dấu phân tách phần thập phân) được formatter dùng. Nó không phải phép đổi lịch hoặc đơn vị thời gian.

Một thông điệp “cùng một ngày giờ” có ít nhất ba chiều cần xác định:

| Câu hỏi | Cơ chế | Ví dụ |
| --- | --- | --- |
| Tại thời điểm ấy, đồng hồ địa phương chỉ mấy giờ? | `ZoneId` / `withZone` | UTC `00:30`, TP.HCM `07:30` cùng một `Instant`. |
| Hệ lịch gọi năm, kỷ nguyên và ngày ấy thế nào? | `Chronology` / `withChronology` | ISO năm 2024, Phật giáo Thái năm 2567. |
| Các chữ số được viết bằng ký tự nào? | `DecimalStyle` / `withDecimalStyle` | `2024` hoặc `٢٠٢٤`. |

**Không nên đánh đồng `Locale` với zone, chronology hoặc decimal style.** Locale có thể cung cấp ngữ cảnh ngôn ngữ cho tên tháng/thứ và các format style, nhưng zone là ngữ nghĩa thời điểm; chronology là hệ lịch; decimal style là các ký hiệu biểu diễn. Tùy API và formatter, một số mặc định có thể dựa trên locale, nhưng nếu ứng dụng cần kết quả cụ thể, hãy cấu hình tường minh.

## 2. DateTimeFormatter bất biến: các phương thức with... trả formatter mới

`DateTimeFormatter` là **immutable** và an toàn để chia sẻ giữa các thread khi cấu hình không đổi. Các phương thức `withZone`, `withChronology`, `withDecimalStyle`, `withLocale`, `withResolverStyle` đều **trả về một đối tượng formatter mới** với override tương ứng; chúng không sửa formatter cũ.

```java
DateTimeFormatter base =
        DateTimeFormatter.ofPattern("uuuu-MM-dd HH:mm", Locale.US);
DateTimeFormatter inVietnam =
        base.withZone(ZoneId.of("Asia/Ho_Chi_Minh"));
```

Hai câu lệnh đặt trong phương thức Java, cần import `java.time.ZoneId`, `java.time.format.DateTimeFormatter` và `java.util.Locale`.

Trong ví dụ, `base` vẫn không có override zone; `inVietnam` có zone TP.HCM. Nếu bạn gọi `base.withZone(...)` mà **không nhận giá trị trả về**, biến `base` không thay đổi:

```java
base.withZone(ZoneId.of("UTC")); // Kết quả bị bỏ qua!
```

Với formatter bất biến, cách đúng là gán sang biến mới (hoặc gán lại nếu biến không phải `final`). Lợi ích: bạn có thể giữ một formatter gốc rồi tạo các phiên bản cho từng thị trường mà không làm thay đổi cấu hình dùng chung.

### Phân biệt những gì get... trả về

Các API getter giúp kiểm chứng trạng thái:

- `getZone()` trả `ZoneId` override hoặc `null` nếu chưa đặt.
- `getChronology()` trả `Chronology` override hoặc `null` nếu chưa đặt.
- `getDecimalStyle()` trả bộ ký hiệu đang dùng (thường mặc định là `DecimalStyle.STANDARD` trên formatter cơ bản).
- `getLocale()` trả locale của formatter, không phải bằng chứng rằng mọi cấu hình zone/chronology/decimal style đều được suy ra từ locale đó.

Nếu một formatter đã có override riêng, thay đổi một chiều bằng `withZone` không có nghĩa các chiều còn lại tự chuyển theo.

## 3. withZone(ZoneId): hiển thị thời điểm ở một múi giờ

### 3.1. Khi đối số là Instant

`Instant` biểu diễn một điểm trên trục thời gian UTC, không gắn một múi giờ trình bày cụ thể. Để format một `Instant` thành các trường ngày/giờ địa phương, formatter cần biết `ZoneId`.

```java
Instant instant = Instant.parse("2024-01-02T00:30:00Z");
DateTimeFormatter base = DateTimeFormatter.ofPattern(
        "uuuu-MM-dd HH:mm VV", Locale.US);

DateTimeFormatter utc = base.withZone(ZoneId.of("UTC"));
DateTimeFormatter hcm =
        base.withZone(ZoneId.of("Asia/Ho_Chi_Minh"));

System.out.println(utc.format(instant));
// 2024-01-02 00:30 UTC

System.out.println(hcm.format(instant));
// 2024-01-02 07:30 Asia/Ho_Chi_Minh
```

Đây là đoạn trong phương thức Java; ví dụ chạy độc lập ở mục 7. Kết quả khác nhau vì TP.HCM có độ lệch UTC+07:00 vào thời điểm ví dụ. **`Instant` vẫn là cùng một thời điểm**, không bị cộng thêm bảy giờ trong dữ liệu nguồn.

Ý nghĩa của `VV` trong pattern: in **zone ID**, ví dụ `Asia/Ho_Chi_Minh`. Không nhầm với `XXX` (offset theo mẫu), `z` (tên zone hiển thị theo locale) hoặc `HH` (giờ). Chọn ký hiệu đúng nhu cầu hiển thị, và tránh nhầm offset cố định `+07:00` với một region zone có quy tắc lịch sử/chuyển giờ.

### 3.2. withZone không giống cộng/trừ giờ thủ công

Đừng chuyển một thời điểm sang địa phương bằng cách cộng 7 giờ vào epoch milliseconds hoặc đổi `Instant` thành một `LocalDateTime` mới không có zone rồi lưu như một thời điểm khác. Chính sách time zone có thể thay đổi theo thời kỳ và khu vực; `ZoneId` cùng quy tắc lịch sử từ cơ sở dữ liệu TZDB mới là nguồn cần dùng.

Một số cách đặt đúng ý nghĩa:

```java
Instant instant = Instant.parse("2024-01-02T00:30:00Z");
ZonedDateTime local = instant.atZone(
        ZoneId.of("Asia/Ho_Chi_Minh"));
```

Bây giờ `local` biểu diễn cùng thời điểm nhưng có zone. Khi cần nhiều cách hiển thị cùng một thời điểm, giữ `Instant` (hoặc kiểu có offset/zone thích hợp) ở domain, rồi áp formatter theo mục tiêu.

### 3.3. Khi dữ liệu là LocalDate hoặc LocalDateTime

`LocalDate` chỉ có ngày; `LocalDateTime` có ngày và giờ nhưng **không có zone hay offset**. `withZone(...)` không tự suy diễn rằng `LocalDateTime` là một thời điểm UTC rồi chuyển thành giờ địa phương.

Với pattern chỉ sử dụng trường địa phương:

```java
DateTimeFormatter formatter = DateTimeFormatter
        .ofPattern("uuuu-MM-dd HH:mm", Locale.US)
        .withZone(ZoneId.of("Asia/Ho_Chi_Minh"));

System.out.println(formatter.format(
        LocalDateTime.of(2024, 1, 2, 0, 30)));
// 2024-01-02 00:30
```

Đầu vào không có `Instant` hay offset để chuyển đổi, nên các trường ngày/giờ vẫn được lấy từ `LocalDateTime`. Ngược lại, format `Instant.parse("2024-01-02T00:30:00Z")` bằng chính formatter đó cho `2024-01-02 07:30`.

**Không lạm dụng kết quả này để kết luận mọi pattern đều format được mọi loại TemporalAccessor.** Nếu pattern đòi các trường không có ở dữ liệu (ví dụ `VV` khi không có zone phù hợp, `HH` trên `LocalDate`, hoặc offset trên dữ liệu thiếu offset), có thể gặp `UnsupportedTemporalTypeException`/`DateTimeException`. Cần chọn kiểu đầu vào đủ thông tin và test pattern được sử dụng.

### 3.4. withZone khi parse

`withZone` có thể cung cấp zone override để diễn giải một chuỗi **không chứa zone** thành một thời điểm khi đủ ngày và giờ:

```java
DateTimeFormatter formatter = DateTimeFormatter
        .ofPattern("uuuu-MM-dd HH:mm", Locale.US)
        .withZone(ZoneId.of("Asia/Ho_Chi_Minh"));

Instant parsed = Instant.from(
        formatter.parse("2024-01-02 07:30"));
// 2024-01-02T00:30:00Z
```

Nhưng **không phải mọi chuỗi không có offset đều được phép quy ra Instant**: nếu thiếu ngày hoặc giờ, hoặc biểu diễn thời gian không hợp lệ, resolver có thể không tạo đủ các trường. Khi input đã chứa offset hoặc zone, thứ tự ưu tiên giữa thông tin trong text và override phụ thuộc trường dữ liệu và cách tính `INSTANT_SECONDS`; cần test các trường hợp thực tế. Không dùng `withZone` như “ép múi giờ” không điều kiện cho mọi input.

### 3.5. Zone, Offset và DST

Một region zone như `America/New_York` có thể chuyển sang/ra khỏi daylight saving time. Với `LocalDateTime` nằm trong **gap** (giờ không tồn tại) hoặc **overlap** (giờ lặp), ánh xạ từ local time sang thời điểm tuyệt đối cần quy tắc riêng. Việc chọn `ZoneId` chưa thay thế quyết định nghiệp vụ về gap/overlap, đặc biệt trong đặt lịch, thanh toán, nhật ký kiểm toán.

Với một `Instant` đã biết, chuyển sang địa phương là duy nhất tại thời điểm ấy. Với một giờ đồng hồ địa phương chưa có offset, phải xác định cách giải quyết ambiguity.

## 4. withChronology(Chronology): thay hệ lịch khi hiển thị/parse

### 4.1. Chronology là gì?

`Chronology` (thuộc `java.time.chrono`) mô tả cách một hệ lịch tổ chức năm, tháng, ngày và kỷ nguyên. Các chronology có sẵn trong Java gồm:

- `IsoChronology.INSTANCE`: hệ ISO-8601, mặc định của `LocalDate`.
- `JapaneseChronology.INSTANCE`: hệ lịch Nhật với các era tương ứng.
- `ThaiBuddhistChronology.INSTANCE`: hệ Phật giáo Thái Lan.
- `MinguoChronology.INSTANCE`: hệ Dân Quốc.
- `HijrahChronology.INSTANCE`: một hệ lịch Hijrah với dữ liệu/ràng buộc riêng.

**Không coi chronology là múi giờ hoặc ngôn ngữ.** Một người có thể đọc tiếng Anh về một ngày theo lịch Phật giáo Thái Lan; việc chọn chronology chỉ định cách hệ lịch diễn đạt các trường ngày tháng, còn tên era/tháng cần locale phù hợp.

### 4.2. Ví dụ ISO so với Thai Buddhist

```java
LocalDate isoDate = LocalDate.of(2024, 1, 2);
DateTimeFormatter calendar = DateTimeFormatter.ofPattern(
        "G uuuu-MM-dd", Locale.ENGLISH);

System.out.println(calendar.format(isoDate));
// AD 2024-01-02

System.out.println(calendar
        .withChronology(ThaiBuddhistChronology.INSTANCE)
        .format(isoDate));
// BE 2567-01-02
```

Hai dòng nói về **cùng ngày thực tế theo cách ánh xạ hệ lịch**, nhưng số năm và era khác. `withChronology` chuyển dữ liệu date sang chronology được chọn để hiển thị; nó không làm `isoDate` thay đổi thành ngày 2567 trong hệ ISO, cũng không dịch chuyển thời điểm theo time zone.

Trong pattern:

- `G`: era.
- `uuuu`: proleptic year của chronology đang được dùng.
- `MM`: tháng dưới dạng chữ số.
- `dd`: ngày trong tháng.

Ví dụ dùng `Locale.ENGLISH` để tên era/chuỗi `AD` và `BE` có output có thể kiểm tra. Với locale khác, tên era có thể khác vì dữ liệu localization.

### 4.3. Parse với chronology override

Khi formatter có `withChronology(ThaiBuddhistChronology.INSTANCE)`, nó có thể đọc ngày theo lịch Thái. Bạn có thể lấy ra:

```java
DateTimeFormatter thai = DateTimeFormatter
        .ofPattern("G uuuu-MM-dd", Locale.ENGLISH)
        .withChronology(ThaiBuddhistChronology.INSTANCE);

String view = thai.format(LocalDate.of(2024, 1, 2));
// "BE 2567-01-02"

ThaiBuddhistDate thaiDate =
        ThaiBuddhistDate.from(thai.parse(view));
// ThaiBuddhist BE 2567-01-02

LocalDate backToIso = LocalDate.from(thai.parse(view));
// 2024-01-02
```

Đây là đoạn Java trong phương thức với import `LocalDate`, `ThaiBuddhistDate`, `ThaiBuddhistChronology` và `DateTimeFormatter`; chương trình đầy đủ ở mục 7. Việc parse và chuyển kết quả về `LocalDate` cho phép dùng dữ liệu domain ISO một cách nhất quán, nhưng hãy chỉ định chronology tường minh khi input thuộc hệ lịch khác.

### 4.4. Chronology không chỉ là cộng số năm

Đừng viết một thuật toán kiểu “năm Thái = năm ISO + 543” để thay `Chronology` cho mọi ngôn ngữ/hệ lịch. Mỗi calendar có quy tắc era, độ dài tháng/năm, niên hiệu, dữ liệu lịch sử hoặc phạm vi hỗ trợ khác nhau; không thể áp dụng một phép cộng số học cho lịch Nhật hay Hijrah.

Đối với domain ngày giờ, thường nên lưu `LocalDate`/`Instant` theo ngữ nghĩa ổn định, rồi định dạng theo chronology/locale cho người dùng khi cần. Một số ứng dụng cần lưu `ChronoLocalDate` nếu nghiệp vụ thực sự hoạt động bằng hệ lịch cụ thể; khi đó cần làm rõ quy tắc chuyển đổi và so sánh trước khi lưu dữ liệu.

### 4.5. ResolverStyle và dữ liệu lịch không hợp lệ

Khi parse, `withChronology` không phải kiểm tra tất cả quy tắc hợp lệ của ứng dụng. Nó kết hợp cùng `ResolverStyle` (ví dụ `STRICT`) để xử lý ngày, era và các trường lịch. Với dữ liệu quan trọng, chọn pattern đủ trường, test ngày nhuận, era boundary và giới hạn hệ lịch. Đặc biệt, ký hiệu `yyyy` (year of era) khác `uuuu` (proleptic year); trong strict parsing đôi khi cần era `G` hoặc cấu hình resolver phù hợp.

## 5. withDecimalStyle(DecimalStyle): chữ số và dấu số

### 5.1. Bốn thành phần của DecimalStyle

`java.time.format.DecimalStyle` lưu các ký tự được `DateTimeFormatter` dùng cho biểu diễn chữ số và dấu số:

| API | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| `getZeroDigit()` | Ký tự cho chữ số 0, các chữ số kế tiếp được suy ra từ đó. | `'0'` hoặc `'٠'` |
| `getPositiveSign()` | Ký hiệu dấu cộng. | `'+'` |
| `getNegativeSign()` | Ký hiệu dấu trừ. | `'-'` |
| `getDecimalSeparator()` | Ký hiệu phân tách phần thập phân khi formatter dùng decimal separator. | `'.'` hoặc `'٫'` |

`DecimalStyle.STANDARD` dùng chữ số Latin `0–9`, dấu `+`, `-` và dấu chấm `.`. Các phương thức `withZeroDigit(char)`, `withPositiveSign(char)`, `withNegativeSign(char)` và `withDecimalSeparator(char)` trả đối tượng `DecimalStyle` mới; không sửa bản gốc.

`DecimalStyle.of(locale)` tạo DecimalStyle theo dữ liệu locale được JDK hỗ trợ. **Đừng tự giả định** một locale luôn dùng một hệ chữ số nhất định: người dùng có thể đặt numbering system khác; dữ liệu locale/JDK và extension có thể ảnh hưởng. Nếu cần ký tự chính xác, hãy kiểm tra `DecimalStyle` được tạo ra hoặc cung cấp explicit style.

### 5.2. Đổi chữ số không đổi giá trị ngày

Ví dụ một ngày theo ISO vẫn là ngày 02/01/2024 dù chữ số được in theo hệ Arabic-Indic:

```java
DecimalStyle arabicDigits = DecimalStyle.STANDARD
        .withZeroDigit('\u0660');

DateTimeFormatter formatter = DateTimeFormatter
        .ofPattern("uuuu-MM-dd", Locale.US)
        .withDecimalStyle(arabicDigits);

String view = formatter.format(LocalDate.of(2024, 1, 2));
// "٢٠٢٤-٠١-٠٢"

LocalDate date = LocalDate.parse(view, formatter);
// 2024-01-02
```

`withDecimalStyle` chỉ đổi **cách đọc/ghi ký tự số**; nó không đổi chronology sang lịch Hijrah, không chuyển giờ, không tự đổi văn bản tên tháng hay nội dung chuỗi literal trong pattern. Dấu `-` giữa năm/tháng/ngày ở pattern `"uuuu-MM-dd"` là **literal text**, nên vẫn hiển thị dấu ASCII `-`, dù DecimalStyle có thể đổi negative sign cho một số field có dấu.

### 5.3. Dấu phân cách thập phân: chỉ ảnh hưởng khi phần định dạng dùng nó

Không phải mọi dấu chấm `.` trong pattern đều được thay bởi `DecimalStyle.getDecimalSeparator()`. Nếu bạn viết literal `"."` trong pattern, nó vẫn là dấu chấm literal. Decimal separator của DecimalStyle được dùng khi formatter xây bằng thao tác có ngữ nghĩa phần thập phân, ví dụ `DateTimeFormatterBuilder.appendFraction(..., true)`.

```java
DecimalStyle style = DecimalStyle.STANDARD
        .withZeroDigit('\u0660')
        .withDecimalSeparator('\u066B');

DateTimeFormatter fractional = new DateTimeFormatterBuilder()
        .appendPattern("uuuu-MM-dd HH:mm:ss")
        .appendFraction(ChronoField.NANO_OF_SECOND, 3, 3, true)
        .toFormatter(Locale.US)
        .withDecimalStyle(style);

LocalDateTime t = LocalDateTime.of(
        2024, 1, 2, 3, 4, 5, 123_000_000);
String text = fractional.format(t);
// "٢٠٢٤-٠١-٠٢ ٠٣:٠٤:٠٥٫١٢٣"
```

Ở đây ký tự `٫` (U+066B) là dấu phân tách phần thập phân của formatter; các dấu `-` và `:` trong pattern là literal, không bị chuyển. Nếu dùng `DateTimeFormatter.ofPattern("HH:mm:ss.SSS")`, dấu chấm trong pattern là literal và **không bảo đảm** được thay bằng dấu tùy biến của DecimalStyle.

### 5.4. DecimalStyle có thể ảnh hưởng parsing

Khi formatter đã được cấu hình Arabic-Indic digits, chuỗi ISO với chữ số ASCII có thể bị từ chối:

```java
DateTimeFormatter formatter = DateTimeFormatter
        .ofPattern("uuuu-MM-dd", Locale.US)
        .withDecimalStyle(
                DecimalStyle.STANDARD.withZeroDigit('\u0660'));

LocalDate.parse("٢٠٢٤-٠١-٠٢", formatter); // Thành công.
LocalDate.parse("2024-01-02", formatter); // Có thể ném DateTimeParseException.
```

Điểm quan trọng: parser bị ảnh hưởng bởi **ký tự số được cấu hình**, không chỉ bởi `ResolverStyle`. Vì vậy, khi UI cho phép nhiều numbering systems, cần thiết kế lựa chọn/chính sách chuẩn hóa rõ ràng; đừng cho rằng mọi loại chữ số đều được parser chấp nhận tự động.

Không nên thay thế mọi ký tự số Unicode thành ASCII một cách âm thầm ở input quan trọng. Nếu sản phẩm cho phép chuẩn hóa, hãy kiểm thử những hệ chữ số được hỗ trợ và xử lý dữ liệu không hợp lệ minh bạch.

## 6. Đặt các override cùng nhau

Ba phương thức có thể được kết hợp thành một formatter:

```java
DateTimeFormatter formatter = DateTimeFormatter
        .ofPattern("G uuuu-MM-dd HH:mm VV", Locale.ENGLISH)
        .withZone(ZoneId.of("Asia/Ho_Chi_Minh"))
        .withChronology(ThaiBuddhistChronology.INSTANCE)
        .withDecimalStyle(
                DecimalStyle.STANDARD.withZeroDigit('\u0660'));
```

Đoạn này nằm trong phương thức Java; cần import các class liên quan. Ý nghĩa từng override:

1. `withZone`: chọn local time của một `Instant` theo TP.HCM.
2. `withChronology`: hiển thị ngày theo lịch Phật giáo Thái Lan khi có dữ liệu ngày tương thích.
3. `withDecimalStyle`: in các chữ số theo hệ được chỉ định.
4. `Locale.ENGLISH` trong `ofPattern`: bối cảnh cho tên era và các ký tự văn bản localization của pattern.

Khi chuỗi hiển thị có year-of-era/era, timezone và hệ số đặc thù, parser phải dùng các override tương ứng (hoặc nhập explicit zone/chronology phù hợp) để diễn giải đúng. **Không trông chờ một chuỗi chỉ chứa ngày và giờ, không chứa zone hoặc era, luôn cho phép khôi phục đầy đủ mọi thông tin ban đầu.**

Nếu yêu cầu chỉ là ngày sinh (không phải timestamp), `LocalDate` + chronology mong muốn thường phù hợp hơn `Instant` + zone, vì ngày sinh không nhất thiết gắn với một thời điểm UTC. Ngược lại, log sự kiện/timestamp nên có `Instant` cùng zone hiển thị khi cần.

## 7. Ví dụ Java 17+ độc lập: so sánh zone, chronology và decimal style

Tạo tệp **`DateTimeFormatterOverridesDemo.java`** sau đây. Ví dụ cố định dữ liệu đầu vào, locale và các override nên đầu ra có thể kiểm chứng. Không đổi `Locale.setDefault(...)` hoặc `TimeZone.setDefault(...)` của JVM.

```java
import java.time.Instant;
import java.time.LocalDate;
import java.time.LocalDateTime;
import java.time.ZoneId;
import java.time.chrono.ThaiBuddhistChronology;
import java.time.chrono.ThaiBuddhistDate;
import java.time.format.DateTimeFormatter;
import java.time.format.DateTimeFormatterBuilder;
import java.time.format.DateTimeParseException;
import java.time.format.DecimalStyle;
import java.time.temporal.ChronoField;
import java.util.Locale;

public class DateTimeFormatterOverridesDemo {

    public static void main(String[] args) {
        Instant instant = Instant.parse("2024-01-02T00:30:00Z");

        DateTimeFormatter zoned = DateTimeFormatter
                .ofPattern("uuuu-MM-dd HH:mm VV", Locale.US);

        System.out.println("utc=" + zoned
                .withZone(ZoneId.of("UTC")).format(instant));
        System.out.println("hcm=" + zoned
                .withZone(ZoneId.of("Asia/Ho_Chi_Minh"))
                .format(instant));

        LocalDate date = LocalDate.of(2024, 1, 2);
        DateTimeFormatter calendar = DateTimeFormatter
                .ofPattern("G uuuu-MM-dd", Locale.ENGLISH);
        System.out.println("iso=" + calendar.format(date));

        DateTimeFormatter thai = calendar
                .withChronology(ThaiBuddhistChronology.INSTANCE);
        String thaiText = thai.format(date);
        System.out.println("thai=" + thaiText);
        System.out.println("thaiParsed="
                + ThaiBuddhistDate.from(thai.parse(thaiText)));
        System.out.println("isoParsed="
                + LocalDate.from(thai.parse(thaiText)));

        DecimalStyle arabicDigits = DecimalStyle.STANDARD
                .withZeroDigit('\u0660');
        DateTimeFormatter numbers = DateTimeFormatter
                .ofPattern("uuuu-MM-dd", Locale.US)
                .withDecimalStyle(arabicDigits);
        String text = numbers.format(date);
        System.out.println("digits=" + text);
        System.out.println("parsed=" + LocalDate.parse(text, numbers));

        try {
            LocalDate.parse("2024-01-02", numbers);
            System.out.println("ascii=accepted");
        } catch (DateTimeParseException ex) {
            System.out.println("ascii=rejected");
        }

        DateTimeFormatter clock = DateTimeFormatter
                .ofPattern("uuuu-MM-dd HH:mm", Locale.US)
                .withZone(ZoneId.of("Asia/Ho_Chi_Minh"));
        System.out.println("local="
                + clock.format(LocalDateTime.of(2024, 1, 2, 0, 30)));
        System.out.println("instant=" + clock.format(instant));

        DecimalStyle fractionalStyle = DecimalStyle.STANDARD
                .withZeroDigit('\u0660')
                .withDecimalSeparator('\u066B');
        DateTimeFormatter fraction = new DateTimeFormatterBuilder()
                .appendPattern("uuuu-MM-dd HH:mm:ss")
                .appendFraction(ChronoField.NANO_OF_SECOND, 3, 3, true)
                .toFormatter(Locale.US)
                .withDecimalStyle(fractionalStyle);
        String fractionalText = fraction.format(LocalDateTime.of(
                2024, 1, 2, 3, 4, 5, 123_000_000));
        System.out.println("fraction=" + fractionalText);
        System.out.println("fractionParsed="
                + LocalDateTime.parse(fractionalText, fraction));
    }
}
```

Biên dịch và chạy bằng JDK 17 hoặc mới hơn trong thư mục chứa tệp:

```bash
javac -encoding UTF-8 DateTimeFormatterOverridesDemo.java
java DateTimeFormatterOverridesDemo
```

**Stdout chính xác:**

```text
utc=2024-01-02 00:30 UTC
hcm=2024-01-02 07:30 Asia/Ho_Chi_Minh
iso=AD 2024-01-02
thai=BE 2567-01-02
thaiParsed=ThaiBuddhist BE 2567-01-02
isoParsed=2024-01-02
digits=٢٠٢٤-٠١-٠٢
parsed=2024-01-02
ascii=rejected
local=2024-01-02 00:30
instant=2024-01-02 07:30
fraction=٢٠٢٤-٠١-٠٢ ٠٣:٠٤:٠٥٫١٢٣
fractionParsed=2024-01-02T03:04:05.123
```

### Đọc kết quả đúng cách

- Hai dòng `utc`/`hcm` phản ánh **zone khác nhau của cùng một Instant**, không phải hai sự kiện khác nhau.
- `iso` và `thai` dùng cùng `LocalDate` nhưng chronology khác, nên số năm và era khác.
- `thaiParsed` là kiểu ngày thuộc hệ Phật giáo Thái Lan; `isoParsed` chuyển cùng ngày đó về `LocalDate` ISO.
- `digits` in chữ số Arabic-Indic, nhưng dấu gạch trong pattern vẫn là dấu literal ASCII.
- `parsed` nhận lại `LocalDate` ban đầu khi dùng cùng formatter; `ascii=rejected` cho thấy cần lưu ý ký tự số của parser.
- `local` và `instant` minh họa `LocalDateTime` không tự chuyển giờ chỉ vì formatter có zone, trong khi `Instant` được chuyển theo zone.
- `fraction` và `fractionParsed` chứng minh dấu phân tách phần thập phân thuộc `DecimalStyle` khi formatter được xây bằng `appendFraction(..., true)`.

## 8. Những lỗi thường gặp

| Lỗi | Vì sao sai | Cách làm đúng |
| --- | --- | --- |
| Gọi `formatter.withZone(zone)` rồi bỏ kết quả | `DateTimeFormatter` immutable. | Gán formatter mới. |
| Đổi locale và giả định timezone cũng đổi | Locale và zone là hai khái niệm khác. | Chọn `ZoneId` riêng từ ngữ cảnh. |
| Dùng `LocalDateTime` như một Instant có sẵn UTC | LocalDateTime không có zone/offset. | Xác định vùng/time zone trước khi ánh xạ sang Instant. |
| Tự cộng số giờ khi “đổi zone” | DST và quy tắc lịch sử có thể phức tạp. | Dùng `ZoneId`/`ZonedDateTime`. |
| Coi `withChronology` là cộng 543 vào năm ISO | Mỗi hệ lịch có quy tắc riêng. | Dùng `Chronology`/`ChronoLocalDate`. |
| Nghĩ `ThaiBuddhistDate` là dữ liệu lưu năm ISO đã đổi vĩnh viễn | Đây là cách biểu diễn date trong chronology riêng. | Quy định rõ dạng lưu và conversion. |
| Dùng `yyyy` trong strict parsing mà không có era | Year-of-era khác proleptic year. | Dùng `uuuu` nếu thích hợp hoặc cung cấp era. |
| Nghĩ `withDecimalStyle` đổi mọi ký tự literal `.` | DecimalStyle chỉ áp cho các ký hiệu số mà formatter xử lý. | Dùng `appendFraction(..., true)` khi cần decimal separator style. |
| Nghĩ `DecimalStyle` tự đổi calendar sang lịch Arabic/Hijrah | DecimalStyle chỉ là ký hiệu chữ số/dấu. | Chọn `Chronology` độc lập. |
| Định dạng bằng chữ số Arabic-Indic nhưng parse bằng formatter ASCII | Hai formatter có input grammar khác nhau. | Dùng cùng style/locale phù hợp; test số Unicode. |
| Đổi `TimeZone.setDefault` hoặc `Locale.setDefault` trên từng request | Trạng thái chung JVM, có thể tác động thread khác. | Truyền formatter/zone/locale tường minh. |
| Dùng một pattern trên mọi TemporalAccessor | Không phải type nào cũng có đủ trường. | Chọn type đúng và test tất cả field trong pattern. |

## 9. Chọn kiểu dữ liệu phù hợp trước khi định dạng

| Dữ liệu trong ứng dụng | Kiểu Java thường dùng | Khi cần override |
| --- | --- | --- |
| Ngày không có giờ/múi giờ, ví dụ ngày sinh | `LocalDate` | `withChronology`/`withDecimalStyle` nếu UI cần lịch/chữ số khác. |
| Giờ hẹn địa phương chưa gắn zone | `LocalDateTime` + `ZoneId` được lưu/giải quyết riêng | `withZone` không đủ để làm rõ gap/overlap; cần quy tắc chuyển sang `ZonedDateTime`. |
| Thời điểm sự kiện tuyệt đối | `Instant` | `withZone` để hiển thị local date/time, kết hợp chronology/decimal style khi cần. |
| Ngày giờ có timezone region | `ZonedDateTime` | Formatter có thể giữ zone trong dữ liệu hoặc override; cần xác định chủ đích. |
| Ngày theo lịch ngoài ISO | `ChronoLocalDate`/kiểu chronology cụ thể | Chọn chronology rõ ràng và kiểm soát conversion sang ISO nếu cần. |
| Input ngày/giờ bản địa hóa | `String` + formatter cấu hình rõ | Parse đúng zone, chronology, decimal style, resolver style và domain constraints. |

Không dùng `Instant` cho một ngày thuần túy nếu không có thời điểm; không dùng `LocalDateTime` làm timestamp toàn cục. Quyết định kiểu dữ liệu là trách nhiệm domain trước khi nghĩ tới pattern định dạng.

## 10. Validation và kiểm thử các override

Khi parse hoặc nhận input từ UI:

1. **Kiểm tra cú pháp và locale:** string có phù hợp pattern, chữ số và dấu của `DecimalStyle` đã chọn không? Có text dư không?
2. **Kiểm tra chronology:** ngày/era có hợp lệ trong lịch người dùng chọn không, có nằm trong phạm vi được hỗ trợ không?
3. **Kiểm tra zone và nghĩa thời điểm:** nếu input là ngày-giờ địa phương, có DST gap/overlap không và chọn chính sách gì? Đừng tự giả định input có UTC.
4. **Kiểm tra domain:** ngày có trong khoảng cho phép không, deadline đã qua chưa, số năm/era có ý nghĩa nghiệp vụ không?
5. **Kiểm tra tính tái lập:** cố định `Instant`, `ZoneId`, `Locale`, `Chronology`, `DecimalStyle`, phiên bản Java và dữ liệu TZDB nếu output chính xác tuyệt đối quan trọng.

`DateTimeFormatter.parse` có thể ném `DateTimeParseException` khi chuỗi không khớp pattern hoặc không thể resolve, nhưng parse thành công không có nghĩa mọi chính sách nghiệp vụ đã được đáp ứng. Với pattern không chứa đủ dữ liệu cho kiểu đầu ra mong muốn, thao tác `Instant.from(...)`/`LocalDate.from(...)` vẫn có thể thất bại.

### Ma trận kiểm thử ngắn

| Tình huống | Kỳ vọng |
| --- | --- |
| Một Instant với UTC và Asia/Ho_Chi_Minh | Cùng thời điểm, giờ địa phương khác nhau. |
| LocalDateTime format bằng formatter có zone | Không suy diễn chuyển đổi từ UTC nếu không có instant/offset. |
| ThaiBuddhistChronology và ISO | Cùng ngày, year/era hiển thị khác. |
| Parse ThaiBuddhist text thành ISO LocalDate | Chuyển đổi về đúng ngày ISO nếu dữ liệu đầy đủ. |
| Arabic-Indic digits + DecimalStyle tương ứng | Format/parse khớp khi dùng cùng style. |
| ASCII digits với formatter yêu cầu Arabic-Indic | Bị từ chối hoặc xử lý theo chính sách đã xác định. |
| Decimal separator qua appendFraction(..., true) | Sử dụng dấu của DecimalStyle, không phải literal `.`. |
| Ngày 29/02 hợp lệ và ngày không tồn tại | ResolverStyle được cấu hình để kiểm tra đúng. |
| DST overlap/gap ở zone có chuyển giờ | Áp dụng chính sách giải quyết thời gian địa phương rõ ràng. |

## 11. Bài tập thực hành

**Bài 1 — Giờ địa phương:** format `Instant.parse("2024-01-02T00:30:00Z")` bằng formatter `uuuu-MM-dd HH:mm VV` với `UTC` và `Asia/Ho_Chi_Minh`. Thử thay `Instant` bằng `LocalDateTime`. Giải thích vì sao không thể lấy mọi LocalDateTime và coi nó là UTC để đổi giờ.

**Bài 2 — Lịch ngoài ISO:** format `LocalDate.of(2024, 1, 2)` theo `ThaiBuddhistChronology` với pattern `G uuuu-MM-dd`, parse ngược về `ThaiBuddhistDate` và `LocalDate`. Thử đổi `Locale.ENGLISH` sang locale khác rồi kiểm tra chữ era thay đổi ra sao.

**Bài 3 — Chữ số:** tạo `DecimalStyle` bắt đầu từ `'٠'` và format `LocalDate.of(2024, 1, 2)`. Thử parse bằng formatter dùng chữ số Arabic-Indic và formatter tiêu chuẩn. Nêu quy tắc input của form nên là gì nếu cần hỗ trợ cả hai hệ chữ số.

**Bài 4 — Phần giây:** dùng `DateTimeFormatterBuilder.appendFraction(NANO_OF_SECOND, 3, 3, true)` rồi đặt `withDecimalStyle` với U+066B. So sánh kết quả với pattern có dấu chấm literal; giải thích vì sao không phải mọi dấu `.` đều được đổi.

**Bài 5 — Cấu hình kết hợp:** tạo một formatter với `withZone` TP.HCM, `withChronology` Thai Buddhist và `withDecimalStyle` Arabic-Indic. Cho cùng `Instant`, thử đổi riêng từng override và xác định trường nào của output bị ảnh hưởng.

**Bài 6 — Parse có zone:** phân tích chuỗi `"2024-01-02 07:30"` bằng formatter có `withZone(Asia/Ho_Chi_Minh)` và chuyển thành `Instant`. Kiểm tra kết quả kỳ vọng `2024-01-02T00:30:00Z`. Sau đó xem xét một giờ địa phương thuộc DST overlap/gap trong zone phù hợp và thiết kế cách phát hiện tình huống không đơn trị.

## 12. Checklist hoàn thành

- [ ] Phân biệt rõ `ZoneId`, `Chronology` và `DecimalStyle`.
- [ ] Biết rằng `withZone`, `withChronology`, `withDecimalStyle` trả formatter mới, không sửa bản cũ.
- [ ] Biết lúc nào `withZone` chuyển thời điểm (có `Instant`/offset) và lúc nào không có đủ ngữ nghĩa để chuyển (chỉ `LocalDateTime`).
- [ ] Hiểu chronology có thể thay era/year mà không làm thay đổi chính ngày thực tế.
- [ ] Biết chữ số và decimal separator của formatter có thể do `DecimalStyle` quyết định, khác các ký tự literal của pattern.
- [ ] Chọn đúng kiểu dữ liệu `Instant`/`LocalDate`/`LocalDateTime`/`ChronoLocalDate` trước khi format.
- [ ] Có thể format/parse với locale, chronology, decimal style và zone tường minh; kiểm tra thêm resolver/domain.
- [ ] Có test cho chữ số Unicode, ngày lịch ngoài ISO, UTC vs local time, và DST nếu domain cần.

**Kết luận:** `withZone` quyết định **múi giờ biểu diễn thời điểm**, `withChronology` quyết định **hệ lịch**, và `withDecimalStyle` quyết định **ký hiệu số**. Chúng có thể kết hợp, nhưng không thay thế nhau; formatter không sửa dữ liệu gốc hoặc cấu hình toàn JVM. Phần cốt lõi của localization là chọn đúng **kiểu dữ liệu thời gian** và truyền đầy đủ ngữ cảnh trước khi render/parse.
