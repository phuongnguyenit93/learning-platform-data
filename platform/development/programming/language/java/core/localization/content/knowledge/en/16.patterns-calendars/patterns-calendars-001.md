# Phân biệt u, y và Y trong mẫu năm của Java DateTimeFormatter

## 1. Vì sao ba chữ cái này không thay thế cho nhau?

Khi làm việc với ngày tháng và bản địa hóa trong Java, một lỗi rất khó phát hiện là viết `YYYY-MM-dd` thay vì `uuuu-MM-dd` hoặc `yyyy-MM-dd`. Phần lớn các ngày trong năm có thể hiển thị giống nhau, nhưng **gần thời điểm chuyển năm**, `YYYY` có thể đưa ra **một năm khác hẳn năm dương lịch của ngày đó**.

Trong API `java.time.format.DateTimeFormatter`:

| Ký tự pattern | Tên trường | Ý nghĩa |
|---|---|---|
| `u` | *year* (proleptic year) | Năm liên tục của lịch, có năm 0 và có thể có năm âm |
| `y` | *year-of-era* | Số năm **trong kỷ nguyên** (ví dụ AD/BC với lịch ISO) |
| `Y` | *week-based-year* | Năm theo **hệ tuần** được xác định bởi locale |

Ba ký tự đều liên quan đến “năm”, nhưng chúng thuộc **ba mô hình lịch khác nhau**. Đặc biệt, `Y` là chữ **hoa**, không phải phiên bản viết hoa cho đẹp của `y`.

Ví dụ ngày **01/01/2021** thuộc:

- Năm dương lịch (proleptic year) **2021**: `u = 2021`.
- Năm trong kỷ nguyên Công nguyên **2021**: `y = 2021`, kỷ nguyên `AD`.
- Tuần-năm **2020** theo quy tắc tuần ISO (bắt đầu thứ Hai và tuần đầu phải có ít nhất 4 ngày thuộc năm mới): `Y = 2020`.

Nếu dùng `YYYY-MM-dd` với locale sử dụng quy tắc ISO để ghi ngày 01/01/2021, có thể nhận được chuỗi kiểu **`2020-01-01`** — một tổ hợp gây hiểu nhầm vì phần tháng/ngày vẫn là 01/01 trong khi năm được lấy từ hệ tuần.

**Quy tắc thực tế:** định dạng một ngày lịch thông thường theo ISO, ưu tiên `uuuu-MM-dd`; chỉ sử dụng `YYYY` khi bạn **thật sự muốn hiển thị số tuần và năm của tuần**, chẳng hạn `2020-W53`.

## 2. Khái niệm nền: năm dương lịch, kỷ nguyên và tuần-năm

### 2.1. Proleptic year — ký tự `u`

*Proleptic year* là một chuỗi số năm liên tục đi qua ranh giới trước và sau Công nguyên. Với `LocalDate` trong lịch ISO:

- `0001` là năm 1 CN.
- `0000` là năm 1 TCN.
- `-0001` là năm 2 TCN.

Mô hình này thuận tiện cho tính toán ngày tháng và kiểm tra tính hợp lệ mà **không phải ghép thêm một kỷ nguyên**. `LocalDate.getYear()` dùng cách biểu diễn năm như vậy.

Pattern:

```text
uuuu-MM-dd
```

biểu diễn proleptic year và tháng/ngày. Với các ngày Công nguyên thông thường, `uuuu` nhìn rất giống `yyyy`, nên sự khác biệt dễ bị bỏ qua.

### 2.2. Year-of-era — ký tự `y`

*Year-of-era* là **năm đếm bên trong một kỷ nguyên**. Trong lịch ISO có hai kỷ nguyên chính:

- `AD`/`CE`: các năm dương lịch từ 1 trở lên.
- `BC`/`BCE`: những năm trước 1 CN.

Năm trong kỷ nguyên **không có năm 0**. Ví dụ ngày thuộc proleptic year 0 có `year-of-era = 1` và kỷ nguyên BC. Ngày thuộc proleptic year -1 có `year-of-era = 2` và kỷ nguyên BC.

Chỉ mẫu `yyyy-MM-dd` không ghi rõ kỷ nguyên nên khi parse nghiêm ngặt, parser có thể không đủ dữ kiện để xây dựng một `LocalDate`. Khi thật sự xử lý era, thường cần ký tự `G`:

```text
G yyyy-MM-dd
```

`G` là tên kỷ nguyên; `yyyy` là năm trong kỷ nguyên. Nếu nội dung chỉ là ngày lịch ISO có thể tính toán được, `uuuu` thường dễ hiểu hơn.

### 2.3. Week-based-year — ký tự `Y`

Năm theo tuần không nhất thiết đổi vào ngày **1 tháng 1**. Một tuần có thể nằm vắt qua tháng 12 và tháng 1. Các hệ đếm tuần cần quyết định:

1. Ngày nào được xem là ngày đầu tuần? Thứ Hai hay Chủ nhật?
2. Một tuần phải có tối thiểu bao nhiêu ngày thuộc năm mới thì mới được tính là tuần đầu năm?

Do đó tuần cuối tháng 12 có thể là **tuần số 1 của năm sau**, còn tuần đầu tháng 1 có thể vẫn thuộc **tuần cuối của năm trước**.

Ký tự `Y` trong `DateTimeFormatter` sử dụng các quy tắc tuần mang tính **bản địa hóa theo Locale**, qua `WeekFields`. Vì thế cùng một `LocalDate` có thể có giá trị `Y` khác nhau khi format với `Locale.UK` và `Locale.US`.

## 3. Bộ ký tự mẫu liên quan đến tuần

Không nên dùng `Y` đơn độc rồi ghép với tháng/ngày như một mẫu lịch thông thường. Khi làm báo cáo tuần, các ký tự có ý nghĩa riêng:

| Ký tự | Trường | Ví dụ |
|---|---|---|
| `Y` | Năm theo tuần địa phương | `2020` |
| `w` | Tuần trong năm theo bộ quy tắc của locale | `53` |
| `W` | Tuần trong tháng theo bộ quy tắc của locale | `1` |
| `e` hoặc `c` | Thứ trong tuần theo thứ tự địa phương (dạng số/văn bản tùy độ dài) | UK: thứ Hai = `1`, US: Chủ nhật = `1` |
| `E` | Tên thứ trong tuần, ví dụ `Mon`/`Monday` theo locale | `Fri` |
| `M` | Tháng trong năm dương lịch | `01` |
| `d` | Ngày trong tháng | `01` |

Một mẫu biểu thị tuần có ngữ nghĩa phù hợp hơn:

```text
YYYY-'W'ww-e
```

Ví dụ với `Locale.UK`, ngày 01/01/2021 thuộc `2020-W53-5`: tuần-năm 2020, tuần 53, ngày thứ 5 theo thứ tự tuần bắt đầu từ thứ Hai.

**Phân biệt chữ hoa/thường:** `w` và `W` không giống nhau; `w` là week-of-week-based-year, `W` là week-of-month. `M` là tháng, `m` là phút. Các ký tự trong pattern Java **có phân biệt chữ hoa chữ thường** và không được đổi tùy ý.

Các chuỗi chữ cố định cần đặt trong dấu nháy đơn, ví dụ phần `'W'` nhằm in ra chữ `W` literal, không để parser hiểu `W` là trường tuần-trong-tháng.

## 4. Locale và quy tắc tuần quyết định kết quả của Y

Hai locale thường được dùng để thấy khác biệt:

- `Locale.UK` có quy tắc tuần giống ISO thông dụng: tuần bắt đầu vào **thứ Hai**, tuần đầu cần tối thiểu **4 ngày** trong năm mới.
- `Locale.US` thường bắt đầu tuần vào **Chủ nhật**, và tuần đầu cần tối thiểu **1 ngày** của năm mới.

`WeekFields.of(locale)` cho biết quy tắc được dùng. Đó là lý do **không thể nói đơn giản rằng mọi `YYYY` đều là “ISO week-year”**. `YYYY` trong `DateTimeFormatter.ofPattern(..., locale)` là **week-based-year phụ thuộc locale**.

Với một số ngày quanh năm 2020–2021:

| Ngày dương lịch | `u`/`y` với ISO AD | `Y` và tuần với UK | `Y` và tuần với US |
|---|---|---|---|
| 27/12/2020 | 2020 | `2020-W52` | `2021-W01` |
| 28/12/2020 | 2020 | `2020-W53` | `2021-W01` |
| 31/12/2020 | 2020 | `2020-W53` | `2021-W01` |
| 01/01/2021 | 2021 | `2020-W53` | `2021-W01` |
| 03/01/2021 | 2021 | `2020-W53` | `2021-W02` |
| 04/01/2021 | 2021 | `2021-W01` | `2021-W02` |

Như vậy, **ngày 31/12/2020** có thể đã mang tuần-năm 2021 trong US, còn **ngày 01/01/2021** vẫn thuộc tuần-năm 2020 trong UK/ISO.

Không nên sử dụng kết quả từ hệ tuần của quốc gia này để gán nhãn cho dữ liệu tuần của một quốc gia khác. Khi báo cáo tính theo ISO 8601, cần chọn rõ quy tắc ISO thay vì để default locale của JVM quyết định ngầm.

## 5. Ví dụ Java 17+ hoàn chỉnh: so sánh u, y, Y ở ranh giới năm

Tạo tệp `YearPatternDemo.java`:

```java
import java.time.LocalDate;
import java.time.format.DateTimeFormatter;
import java.util.List;
import java.util.Locale;

public class YearPatternDemo {
    public static void main(String[] args) {
        DateTimeFormatter uk = DateTimeFormatter.ofPattern(
                "uuuu yyyy YYYY-'W'ww-e", Locale.UK);
        DateTimeFormatter us = DateTimeFormatter.ofPattern(
                "uuuu yyyy YYYY-'W'ww-e", Locale.US);

        List<LocalDate> days = List.of(
                LocalDate.of(2020, 12, 27),
                LocalDate.of(2020, 12, 28),
                LocalDate.of(2020, 12, 31),
                LocalDate.of(2021, 1, 1),
                LocalDate.of(2021, 1, 3),
                LocalDate.of(2021, 1, 4));

        for (LocalDate day : days) {
            System.out.printf(
                    "%s UK=%s US=%s%n",
                    day, day.format(uk), day.format(us));
        }
    }
}
```

Biên dịch và chạy:

```bash
javac YearPatternDemo.java
java YearPatternDemo
```

Kết quả đã kiểm chứng bằng JDK:

```text
2020-12-27 UK=2020 2020 2020-W52-7 US=2020 2020 2021-W01-1
2020-12-28 UK=2020 2020 2020-W53-1 US=2020 2020 2021-W01-2
2020-12-31 UK=2020 2020 2020-W53-4 US=2020 2020 2021-W01-5
2021-01-01 UK=2021 2021 2020-W53-5 US=2021 2021 2021-W01-6
2021-01-03 UK=2021 2021 2020-W53-7 US=2021 2021 2021-W02-1
2021-01-04 UK=2021 2021 2021-W01-1 US=2021 2021 2021-W02-2
```

Đọc một dòng quan trọng:

```text
2021-01-01 UK=2021 2021 2020-W53-5 US=2021 2021 2021-W01-6
```

- `2021-01-01` ở đầu dòng là `LocalDate.toString()`, dùng năm lịch ISO.
- Hai số đầu trong cột `UK` tương ứng `uuuu` và `yyyy`: cả hai là 2021 vì đây là ngày AD.
- `2020-W53-5` là tuần-năm 2020 của UK/ISO.
- `2021-W01-6` là tuần-năm 2021 của US, ngày thứ 6 trong tuần bắt đầu Chủ nhật.

Điều này cho thấy `Y` thay đổi theo **quy tắc tuần**, không phải formatter bị sai hoặc `LocalDate` có hai ngày khác nhau.

## 6. Khi nào dùng u thay vì y?

Với `LocalDate` ISO và nhu cầu lưu/đọc ngày dương lịch:

```text
uuuu-MM-dd
```

là một lựa chọn vững chắc. `u` biểu thị trực tiếp năm liên tục, bao gồm cả năm 0 và năm âm nếu miền ứng dụng hỗ trợ.

`y` là đúng khi dữ liệu thực sự biểu diễn **năm trong một kỷ nguyên**. Với ngày hiện đại sau Công nguyên, hai ký tự trông giống nhau:

```text
Ngày 2024-02-29:
uuuu -> 2024
yyyy -> 2024
```

Nhưng điểm khác biệt lộ ra ở lịch sử trước Công nguyên. Trong lịch ISO proleptic:

| `LocalDate.getYear()` | Kỷ nguyên | `yyyy` | `uuuu` |
|---:|---|---|---|
| `1` | AD | `0001` | `0001` |
| `0` | BC | `0001` | `0000` |
| `-1` | BC | `0002` | `-0001` |

**Không có năm 0 trong year-of-era**, nhưng có năm 0 trong proleptic-year. Do đó `yyyy` không đủ để mô tả một ngày lịch sử nếu thiếu era.

### Ví dụ Java 17+ hoàn chỉnh về năm 0 và BC/AD

Tạo tệp `EraYearDemo.java`:

```java
import java.time.LocalDate;
import java.time.format.DateTimeFormatter;
import java.util.Locale;

public class EraYearDemo {
    public static void main(String[] args) {
        DateTimeFormatter formatter =
                DateTimeFormatter.ofPattern(
                        "G yyyy uuuu", Locale.US);

        int[] years = {1, 0, -1};

        for (int year : years) {
            LocalDate date = LocalDate.of(year, 1, 1);
            System.out.println(
                    "year=" + year + " -> " + date.format(formatter));
        }
    }
}
```

Biên dịch/chạy:

```bash
javac EraYearDemo.java
java EraYearDemo
```

Kết quả:

```text
year=1 -> AD 0001 0001
year=0 -> BC 0001 0000
year=-1 -> BC 0002 -0001
```

Ví dụ này nhấn mạnh **sự khác biệt trong ý nghĩa**, không chỉ khác về cách điền số 0. Nếu hệ thống của bạn cần trao đổi ngày lịch ISO, nên thống nhất proleptic year. Nếu cần hiển thị kỷ nguyên lịch sử, dùng `G` cùng `y` và locale thích hợp.

## 7. Rủi ro khi parse ngày với ResolverStyle.STRICT

`DateTimeFormatter` không chỉ format mà còn parse. Khi parse thành `LocalDate`, formatter phải **giải quyết các trường ngày tháng thành một ngày cụ thể**.

Với `ResolverStyle.STRICT`:

- `uuuu-MM-dd` có trường `YEAR` + tháng + ngày: đủ để tạo `LocalDate` và kiểm tra tính hợp lệ.
- `yyyy-MM-dd` có `YEAR_OF_ERA` + tháng + ngày nhưng **không có ERA**: thường không đủ thông tin cho ngày cụ thể dưới strict resolver.
- `YYYY-MM-dd` có `WEEK_BASED_YEAR` + tháng + ngày nhưng **không có week-of-year/day-of-week**: các trường không hợp thành một ngày duy nhất theo cách strict resolver cần.

Những mẫu dùng `yyyy` thường vẫn *có vẻ parse được* trong một số cấu hình mặc định vì `DateTimeFormatter` mặc định dùng `ResolverStyle.SMART`; Smart có thể giả định kỷ nguyên phù hợp để giải quyết year-of-era. **Đừng hiểu thành `y` và `u` hoàn toàn tương đương**.

### Chương trình Java 17+ chạy được

Tạo tệp `StrictYearParseDemo.java`:

```java
import java.time.LocalDate;
import java.time.format.DateTimeFormatter;
import java.time.format.DateTimeParseException;
import java.time.format.ResolverStyle;
import java.util.Locale;

public class StrictYearParseDemo {
    public static void main(String[] args) {
        String input = "2024-02-29";

        for (String pattern : new String[] {
                "yyyy-MM-dd",
                "uuuu-MM-dd",
                "YYYY-MM-dd"
        }) {
            DateTimeFormatter formatter =
                    DateTimeFormatter.ofPattern(
                            pattern, Locale.UK)
                            .withResolverStyle(ResolverStyle.STRICT);

            try {
                LocalDate date = LocalDate.parse(input, formatter);
                System.out.println(pattern + " -> " + date);
            } catch (DateTimeParseException exception) {
                System.out.println(
                        pattern + " -> DateTimeParseException");
            }
        }
    }
}
```

Chạy:

```bash
javac StrictYearParseDemo.java
java StrictYearParseDemo
```

Output:

```text
yyyy-MM-dd -> DateTimeParseException
uuuu-MM-dd -> 2024-02-29
YYYY-MM-dd -> DateTimeParseException
```

Điểm quan trọng: lỗi của `yyyy` ở đây không phải vì ngày 29/02/2024 không hợp lệ. Ngày này có thật trong lịch ISO. Với `yyyy` parser có **YEAR_OF_ERA nhưng thiếu ERA** khi dùng strict resolution.

Cũng không được coi `YYYY-MM-dd` là giải pháp thay thế khi `yyyy-MM-dd` gặp lỗi. `Y` là tuần-năm, không thể kết hợp tùy tiện với `M`/`d` rồi mong giải quyết thành một ngày lịch bình thường.

### Parse year-of-era đúng cách với era tường minh

Nếu dữ liệu thực sự có kỷ nguyên, có thể dùng:

```text
G yyyy-MM-dd
```

Ví dụ:

```java
DateTimeFormatter formatter =
        DateTimeFormatter.ofPattern(
                "G yyyy-MM-dd", Locale.US)
                .withResolverStyle(ResolverStyle.STRICT);

LocalDate firstBce =
        LocalDate.parse("BC 0001-01-01", formatter);
// firstBce = 0000-01-01 trong proleptic ISO
```

Đây là **mảnh mã Java minh họa** với các import `LocalDate`, `DateTimeFormatter`, `ResolverStyle` và `Locale`; ví dụ đầy đủ ở trên có thể biên dịch độc lập. Khi dùng locale khác, biểu diễn của `AD`/`BC` có thể được bản địa hóa; hãy giữ formatter locale và dữ liệu đầu vào nhất quán.

### STRICT khác với pattern chữ năm

`ResolverStyle.STRICT` còn kiểm tra ngày hợp lệ theo tháng/năm, ví dụ không cho ngày 31/02 hoặc 29/02 của năm không nhuận. `u`/`y`/`Y` xác định *loại trường năm*, còn resolver style xác định *cách kiểm tra và kết hợp các trường*.

Với một ứng dụng yêu cầu ngày ISO chính xác, ví dụ rõ ràng là:

```java
DateTimeFormatter isoStrict =
        DateTimeFormatter.ofPattern("uuuu-MM-dd", Locale.ROOT)
                .withResolverStyle(ResolverStyle.STRICT);
```

Hoặc sử dụng formatter có sẵn `DateTimeFormatter.ISO_LOCAL_DATE` khi hợp đồng giao tiếp cần ngày ISO 8601. Đừng tự thêm `Y` vào định dạng ngày chỉ vì thấy chữ “year”.

## 8. Parsing tuần-năm đúng: kết hợp Y với w và e

Nếu dữ liệu thật sự được tổ chức theo **tuần**, pattern kết hợp `Y`, `w` và `e` có ý nghĩa:

```text
YYYY-'W'ww-e
```

Trong đó:

- `YYYY`: tuần-năm (localized week-based-year).
- `ww`: tuần thuộc tuần-năm đó.
- `e`: thứ trong tuần theo tuần bắt đầu của locale.

Ví dụ, ngày 01/01/2021 có thể được biểu diễn:

```text
UK: 2020-W53-5
US: 2021-W01-6
```

Và có thể parse các chuỗi này thành cùng ngày ISO bằng đúng locale tương ứng:

```java
DateTimeFormatter uk =
        DateTimeFormatter.ofPattern(
                "YYYY-'W'ww-e", Locale.UK)
                .withResolverStyle(ResolverStyle.STRICT);

DateTimeFormatter us =
        DateTimeFormatter.ofPattern(
                "YYYY-'W'ww-e", Locale.US)
                .withResolverStyle(ResolverStyle.STRICT);

LocalDate ukDate = LocalDate.parse("2020-W53-5", uk);
LocalDate usDate = LocalDate.parse("2021-W01-6", us);
// Cả hai là 2021-01-01
```

Đây là **mảnh mã minh họa**, dùng trong class có import thích hợp. Nó diễn giải một ngày duy nhất bằng hai hệ tuần, không phải hai ngày khác nhau.

**Cảnh báo:** khi dữ liệu tuần được lưu để trao đổi giữa các hệ thống, phải quy định rõ **WeekFields** (đầu tuần và số ngày tối thiểu của tuần đầu) trong giao thức. Chỉ lưu `2021-W01` mà không biết quy tắc US hay ISO có thể làm lệch báo cáo.

## 9. Muốn ISO week-year bất kể Locale: dùng WeekFields.ISO

`Y` là localized week-based-year, nên nếu yêu cầu là **ISO week numbering** thì không nên phụ thuộc vào default locale.

`java.time.temporal.WeekFields.ISO` quy định:

- Thứ Hai là ngày đầu tuần.
- Tuần đầu tiên cần có ít nhất 4 ngày của năm mới.

Bạn có thể lấy trường ISO tường minh:

```java
import java.time.LocalDate;
import java.time.temporal.WeekFields;
import java.time.temporal.IsoFields;

LocalDate date = LocalDate.of(2021, 1, 1);

int isoWeekYear = date.get(
        IsoFields.WEEK_BASED_YEAR);
int isoWeek = date.get(
        IsoFields.WEEK_OF_WEEK_BASED_YEAR);
int isoDayOfWeek = date.getDayOfWeek().getValue();

// isoWeekYear = 2020
// isoWeek     = 53
// isoDayOfWeek = 5
```

Đây là mảnh code minh họa (những dòng import, khai báo có thể được đặt trong một chương trình đầy đủ). `IsoFields` là API trực tiếp cho số tuần ISO. `WeekFields.ISO.weekBasedYear()` và `WeekFields.ISO.weekOfWeekBasedYear()` cũng là lựa chọn tường minh, đặc biệt khi dự án muốn cấu trúc code dựa trên `WeekFields`.

Với đầu vào do người dùng nhìn thấy, locale có thể quyết định tên tháng và cách hiển thị. Nhưng **quy tắc tuần dùng cho tính toán/tổng hợp dữ liệu** phải là lựa chọn nghiệp vụ rõ ràng, không nên thay đổi theo ngôn ngữ UI một cách vô thức.

## 10. Không nhầm DateTimeFormatter với SimpleDateFormat

Trong Java có **hai hệ API định dạng ngày** thường gặp:

1. `java.time.format.DateTimeFormatter` (API hiện đại từ Java 8).
2. `java.text.SimpleDateFormat` (API cũ, mutable và không thread-safe).

**Cùng ký tự có thể có ý nghĩa khác nhau giữa hai API.** Đặc biệt:

| Pattern | `DateTimeFormatter` | `SimpleDateFormat` |
|---|---|---|
| `u` | Proleptic year | **Số thứ trong tuần** với Thứ Hai = 1, Chủ nhật = 7 |
| `y` | Year-of-era | Year (năm) theo mô hình của `Calendar` |
| `Y` | Localized week-based-year | Week year theo `Calendar` và cấu hình tuần |
| `d` | Day-of-month | Day-of-month |
| `M` | Month-of-year | Month |

Vì thế **không thể di chuyển pattern `uuuu-MM-dd` từ DateTimeFormatter sang SimpleDateFormat rồi mong cùng nghĩa**: `u` ở `SimpleDateFormat` không phải năm. Trong dự án chuyển đổi từ `Date`/`Calendar` sang `java.time`, phải review lại mọi pattern thay vì dùng tìm-thay chuỗi mù quáng.

Ví dụ với ngày 01/01/2021 là thứ Sáu:

```text
DateTimeFormatter: uuuu = 2021
SimpleDateFormat: u = 5  (Thứ Sáu)
```

Với `SimpleDateFormat`, `Y` có thể là tuần-năm và `y` là năm lịch theo `Calendar`. Điều này vẫn khiến lỗi `YYYY` trong báo cáo ngày xảy ra, nhưng **đừng áp cơ chế strict parsing hoặc proleptic-year của java.time sang API cũ**.

Một chương trình mới nên ưu tiên `java.time` nếu không bị ràng buộc bởi API tương thích. `DateTimeFormatter` là immutable và thread-safe; `SimpleDateFormat` mutable, cần quản lý thread/concurrency cẩn thận.

## 11. Số lượng ký tự và các bẫy pattern

Số lần lặp ký tự trong `DateTimeFormatter` ảnh hưởng cách in và cách parse:

- `u` và `uuuu` cùng nhắc đến trường proleptic year, nhưng `uuuu` yêu cầu hiển thị tối thiểu bốn chữ số ở dạng thường thấy.
- `y` và `yyyy` cùng là year-of-era, khác padding/độ rộng.
- `Y` và `YYYY` cùng là localized week-based-year, khác độ rộng.
- `yy`, `uu`, `YY` thường liên quan đến reduced 2-digit year; chúng không tương đương mẫu bốn chữ số và cần chính sách rõ cho việc diễn giải thế kỷ.

Một lỗi dễ mắc là tưởng `YYYY` được viết hoa để bắt buộc bốn chữ số trong khi `yyyy` viết thường không đủ. Trong thực tế, **chữ hoa đã đổi hẳn trường**, không chỉ đổi định dạng.

Không tự định nghĩa quy ước “mọi năm đều dùng YYYY” cho Java. Khi trao đổi ISO date với hệ thống khác, xác định chính xác cú pháp và sử dụng formatter phù hợp.

### Pattern "YYYY-MM-dd" gây sai ngay cả khi format chạy

`DateTimeFormatter.ofPattern("YYYY-MM-dd", Locale.UK)` vẫn có thể **format** một `LocalDate` vì object nguồn đã chứa mọi trường. Nhưng chuỗi output trộn **week-year** với **tháng/ngày theo năm lịch**; khi parse lại bằng strict resolver, dữ liệu không mô tả một ngày hợp lệ theo đúng tổ hợp trường. Ngay cả nếu có cấu hình parse khác “cho qua”, ý nghĩa cũng dễ sai.

Cần phân biệt:

- **Format:** lấy trường từ một đối tượng đã xác định ngày.
- **Parse:** dựng lại đối tượng ngày từ các trường trong chuỗi; các trường phải hợp thành một ngày nhất quán.

Do đó các bài test chỉ kiểm tra “formatter trả ra một string” là chưa đủ; cần có test round-trip theo dữ liệu thực tế (format rồi parse lại thành cùng `LocalDate`) với đúng parser/resolver style.

## 12. Quy tắc kiểm thử biên năm

Vì sự khác nhau giữa `u`/`y`/`Y` chủ yếu lộ ra ở những ca hiếm, hãy có bộ kiểm thử cố định:

| Trường hợp | Vì sao quan trọng |
|---|---|
| 27–31 tháng 12 | Có thể thuộc tuần-năm sau với một số locale |
| 1–4 tháng 1 | Có thể thuộc tuần-năm trước với ISO/UK |
| Năm có tuần 53 | Kiểm thử tuần cuối và ngày đầu năm sau |
| Năm nhuận, ví dụ `2024-02-29` | Kiểm tra calendar year và strict parsing |
| Năm 0 / năm âm nếu nghiệp vụ hỗ trợ | Phân biệt `u` và `y` |
| US so với UK/ISO | Chứng minh `Y` phụ thuộc quy tắc tuần |
| Format–parse round-trip | Phát hiện pattern không đủ trường hoặc trộn mô hình |
| Chuyển đổi SimpleDateFormat sang DateTimeFormatter | Phát hiện `u` đổi nghĩa |

Một test đáng có là: mọi ngày đầu/cuối năm phải được format bằng `uuuu-MM-dd` rồi parse lại bằng strict resolver và bằng đúng ngày gốc. Nếu report theo tuần ISO, test riêng `IsoFields.WEEK_BASED_YEAR` và `IsoFields.WEEK_OF_WEEK_BASED_YEAR`, không dùng năm từ `LocalDate.getYear()` để gán cho tuần một cách tùy tiện.

## 13. Các lỗi phổ biến và cách tránh

**Lỗi 1 — Dùng `YYYY-MM-dd` cho ngày lịch.** Tuần-năm có thể khác năm dương lịch. Dùng `uuuu-MM-dd` khi muốn ISO date.

**Lỗi 2 — Cho rằng `yyyy` luôn bằng `uuuu`.** Trong thời hiện đại AD chúng thường cho cùng số, nhưng mô hình năm khác nhau; trước CN, `yyyy` cần thông tin kỷ nguyên.

**Lỗi 3 — Parse `yyyy-MM-dd` với STRICT rồi nghĩ ngày hợp lệ nhưng bị Java lỗi.** Trường `YEAR_OF_ERA` có thể không giải quyết được nếu thiếu `ERA`; dùng `uuuu` khi cần ISO proleptic date hoặc thêm `G` khi mô hình là year-of-era.

**Lỗi 4 — Cho rằng `YYYY` là tuần-năm ISO trong mọi Locale.** `DateTimeFormatter` sử dụng localized week rules; muốn ISO tường minh, dùng `WeekFields.ISO` hoặc `IsoFields`.

**Lỗi 5 — Dùng `YYYY` với tháng và ngày.** Đó là trộn mô hình tuần với mô hình lịch; nếu muốn tuần dùng `Y` + `w` + ngày thứ trong tuần phù hợp.

**Lỗi 6 — Thấy ngày 01/01 mà tuần-năm còn ở năm cũ rồi sửa dữ liệu.** Đây có thể là hành vi đúng của ISO week-year. Kiểm tra quy tắc nghiệp vụ trước khi thay đổi.

**Lỗi 7 — Sao chép `uuuu` sang `SimpleDateFormat`.** `u` ở SimpleDateFormat là ngày thứ trong tuần; kiểm tra lại pattern khi đổi API.

**Lỗi 8 — Quên Locale khi sử dụng `Y`/`w`/`e`.** Cùng ngày có thể được gán nhãn tuần khác nhau nếu thay locale.

**Lỗi 9 — Chỉ test giữa năm.** Tháng 6 hiếm khi làm lộ lỗi `Y`; cần test cả cuối tháng 12 và đầu tháng 1.

**Lỗi 10 — Dùng dữ liệu tuần để đánh chỉ số báo cáo năm lịch mà không làm rõ quy tắc.** Tuần cuối năm và tuần đầu năm có thể vắt qua năm khác; cần định nghĩa rõ "năm" là calendar year hay week-based-year.

## 14. Hỏi đáp tự kiểm tra

**Câu 1.** Mẫu `uuuu-MM-dd` lấy loại năm nào?  
**Đáp án:** Proleptic year; với lịch ISO có năm 0 và năm âm.

**Câu 2.** Mẫu `yyyy-MM-dd` khác `uuuu-MM-dd` ở đâu?  
**Đáp án:** `yyyy` là year-of-era, trong khi `uuuu` là proleptic year. Với strict parser, `yyyy` có thể cần thêm era (`G`).

**Câu 3.** Tại sao ngày 01/01/2021 có thể hiển thị `2020-W53`?  
**Đáp án:** Theo quy tắc tuần ISO, ngày đó nằm trong tuần 53 thuộc tuần-năm 2020.

**Câu 4.** `YYYY` với `Locale.US` và `Locale.UK` có luôn giống nhau không?  
**Đáp án:** Không. Locale quy định ngày đầu tuần và số ngày tối thiểu của tuần đầu.

**Câu 5.** Muốn in ngày lịch chuẩn `2021-01-01`, nên dùng `YYYY-MM-dd` không?  
**Đáp án:** Không. Dùng `uuuu-MM-dd` hoặc `DateTimeFormatter.ISO_LOCAL_DATE`.

**Câu 6.** `u` trong `SimpleDateFormat` có phải proleptic year không?  
**Đáp án:** Không. Ở API cũ, `u` là thứ trong tuần, 1 là Thứ Hai.

**Câu 7.** Năm 0 của `LocalDate` tương ứng year-of-era nào?  
**Đáp án:** Kỷ nguyên BC, year-of-era 1.

**Câu 8.** Muốn báo cáo tuần ISO mà UI có thể thay đổi ngôn ngữ, nên dùng gì?  
**Đáp án:** `IsoFields` hoặc `WeekFields.ISO` cho tính toán, tránh dựa vào default locale.

## 15. Ghi nhớ và tài liệu

**`u` = năm liên tục, `y` = năm trong kỷ nguyên, `Y` = năm theo tuần được bản địa hóa.** Với ngày lịch thông thường và strict parsing, `uuuu-MM-dd` là lựa chọn rõ ràng; nếu phải hiển thị kỷ nguyên lịch sử, dùng `G` cùng `y`; nếu báo cáo theo tuần, ghép `Y` với `w` và `e` theo quy tắc tuần đã chọn.

Đừng coi `YYYY` chỉ là một cách viết hoa của `yyyy`: khác biệt này có thể làm sai dữ liệu vào những ngày quan trọng nhất của báo cáo năm.

**Tham khảo:** [Java SE 17 — DateTimeFormatter](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/format/DateTimeFormatter.html) · [Java SE 17 — WeekFields](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/temporal/WeekFields.html) · [Java SE 17 — IsoFields](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/temporal/IsoFields.html) · [Java SE 17 — SimpleDateFormat](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/text/SimpleDateFormat.html).
