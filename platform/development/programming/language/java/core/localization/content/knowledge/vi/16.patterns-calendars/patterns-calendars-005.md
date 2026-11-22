# Năm theo tuần ở ranh giới cuối năm trong Java

## 1. Vấn đề: ngày 1 tháng 1 có thể thuộc “năm tuần” trước đó

Trong hệ thống báo cáo, lịch làm việc hoặc đặt lịch, bạn có thể thấy một ngày thuộc năm dương lịch 2021 nhưng lại được gắn nhãn **tuần 53 của năm 2020**. Đây không phải lỗi tính ngày:

- Ngày dương lịch **2021-01-01** có `YEAR = 2021`.
- Theo **tuần ISO 8601**, ngày đó thuộc **2020-W53**, tức tuần thứ 53 của **week-based-year 2020**.
- Tương tự, ngày **2018-12-31** thuộc năm dương lịch 2018 nhưng ở **ISO 2019-W01**.

Sự khác biệt này xảy ra vì **năm theo tuần (week-based-year)** được xác định từ những tuần nguyên vẹn hoặc tuần đầu năm theo quy tắc lịch, không trùng hoàn toàn với khoảng từ 1/1 đến 31/12.

Java cung cấp `LocalDate`, `WeekFields`, `IsoFields` và `DateTimeFormatter` để tính và trình bày ngày theo tuần. Trong Java Core localization, cần đặc biệt phân biệt **quy tắc ISO** với **quy tắc tuần theo Locale** và tránh lỗi phổ biến khi dùng `YYYY` thay cho `yyyy` hoặc `uuuu`.

## 2. Phân biệt ba khái niệm: năm lịch, tuần trong năm và năm theo tuần

| Khái niệm | Java API điển hình | Ý nghĩa |
| --- | --- | --- |
| Năm dương lịch (calendar year) | `LocalDate.getYear()`, `ChronoField.YEAR`, pattern `uuuu` | Năm chứa ngày đó theo lịch ISO/Gregorian proleptic |
| Tuần của năm lịch (week-of-year) | `WeekFields.weekOfYear()` | Đếm tuần **bên trong năm lịch**, có thể có **tuần 0**; không dùng để tạo mã tuần ISO |
| Năm theo tuần (week-based-year) | `WeekFields.weekBasedYear()` | Năm “sở hữu” tuần, có thể khác calendar year ở đầu/cuối năm |
| Tuần của năm theo tuần | `WeekFields.weekOfWeekBasedYear()` | Số tuần thường 1–52 hoặc 1–53 trong week-based-year |
| Ngày trong tuần | `DayOfWeek`, `WeekFields.dayOfWeek()` | Ngày theo thứ tự ISO hoặc thứ tự địa phương |

**Không ghép** `date.getYear()` với `date.get(WeekFields.ISO.weekOfWeekBasedYear())` rồi coi kết quả là mã tuần ISO. Nửa cuối tháng 12 đôi khi thuộc week-based-year kế tiếp, còn vài ngày đầu tháng 1 có thể thuộc week-based-year trước đó. Cặp đúng phải là:

```java
WeekFields iso = WeekFields.ISO;
int weekYear = date.get(iso.weekBasedYear());
int week = date.get(iso.weekOfWeekBasedYear());
```

Đây là snippet; biến `date` là một `LocalDate` đã tạo và cần `import java.time.temporal.WeekFields;`. Hai trường trên cùng dựa vào **một định nghĩa tuần thống nhất**.

### Vì sao week-of-year khác week-of-week-based-year?

`weekOfYear()` đếm theo ranh giới năm lịch, do đó phần đầu một năm chưa đủ ngày cho tuần 1 có thể được đánh **tuần 0**, và một tuần có thể bị chia tại thời điểm đổi năm. Ngược lại `weekOfWeekBasedYear()` đếm các tuần của một *week-based-year*: mỗi tuần hoàn chỉnh thuộc đúng một năm tuần, nên những ngày rơi sang năm lịch kề bên vẫn được gán cho tuần 1 hoặc tuần 52/53 của một năm tuần.

Nếu mục tiêu là mã tuần chuẩn như `2020-W53`, dùng **week-based-year + week-of-week-based-year**, không dùng year + week-of-year.

## 3. Quy tắc ISO 8601 cho năm theo tuần

Theo ISO 8601:

1. **Tuần bắt đầu vào thứ Hai**.
2. **Tuần 1 là tuần có ít nhất bốn ngày trong năm dương lịch mới**. Tương đương tuần chứa **ngày 4 tháng 1**, hoặc tuần chứa **thứ Năm đầu tiên của năm**.
3. Một week-based-year có **52 hoặc 53 tuần**.
4. Một tuần không bị chia đôi tại đêm giao thừa: tuần cuối có thể kết thúc trong tháng 1 của năm sau, hoặc tuần đầu có thể bắt đầu trong tháng 12 năm trước.

Java biểu diễn quy tắc này bằng:

```java
WeekFields iso = WeekFields.ISO;
System.out.println(iso.getFirstDayOfWeek());       // MONDAY
System.out.println(iso.getMinimalDaysInFirstWeek()); // 4
```

Đây là snippet thuộc một phương thức Java, với `import java.time.temporal.WeekFields;`.

Ví dụ, năm dương lịch 2021 bắt đầu vào thứ Sáu. Tuần từ thứ Hai 28/12/2020 đến Chủ nhật 03/01/2021 có **bốn ngày thuộc năm 2020** và chỉ **ba ngày thuộc năm 2021**, nên là **tuần 53 của năm tuần 2020**. Tuần 1 của năm tuần 2021 bắt đầu thứ Hai 04/01/2021.

### Bảng các ngày giáp ranh theo ISO

| Ngày lịch | Năm lịch | Week-based-year ISO | Tuần ISO | Ngày ISO trong tuần |
| --- | ---: | ---: | ---: | --- |
| `2014-12-29` | 2014 | 2015 | 01 | Thứ Hai (1) |
| `2018-12-31` | 2018 | 2019 | 01 | Thứ Hai (1) |
| `2020-12-27` | 2020 | 2020 | 52 | Chủ nhật (7) |
| `2020-12-31` | 2020 | 2020 | 53 | Thứ Năm (4) |
| `2021-01-01` | 2021 | 2020 | 53 | Thứ Sáu (5) |
| `2021-01-03` | 2021 | 2020 | 53 | Chủ nhật (7) |
| `2021-01-04` | 2021 | 2021 | 01 | Thứ Hai (1) |

Những dòng `2014-12-29` và `2018-12-31` thể hiện trường hợp ngược lại: một ngày ở **cuối tháng 12** lại đã thuộc **năm tuần kế tiếp**.

**Cảnh báo:** tuần 53 không tồn tại trong mọi năm tuần. Không thể giả định tuần cuối luôn là tuần 52 và cũng không được tự tăng tuần 52 lên 53 bằng phép cộng đơn giản; phải nhờ thuật toán lịch hoặc API chuẩn.

## 4. WeekFields.ISO so với WeekFields theo Locale

Không phải quốc gia/vùng nào cũng áp dụng quy tắc ISO. Một số hệ thống lấy **Chủ nhật** làm ngày đầu tuần và chỉ yêu cầu **một ngày** của năm mới để xác định tuần 1. Java hỗ trợ các quy tắc này:

```java
WeekFields iso = WeekFields.ISO;
WeekFields us = WeekFields.of(Locale.US);
WeekFields custom = WeekFields.of(DayOfWeek.SUNDAY, 1);
```

Trong cấu hình thông dụng của `Locale.US`, `us` và `custom` có cùng quy tắc: tuần bắt đầu Chủ nhật, tối thiểu một ngày thuộc năm để được coi là tuần 1. Theo quy tắc đó, tuần bắt đầu ngày **2020-12-27** đã được gán vào **tuần 1 của năm tuần 2021** vì nó chứa ngày 1/1/2021.

| Ngày | ISO (thứ Hai, min=4) | US (Chủ nhật, min=1) |
| --- | --- | --- |
| `2020-12-27` | `2020-W52` | `2021-W01` |
| `2020-12-31` | `2020-W53` | `2021-W01` |
| `2021-01-01` | `2020-W53` | `2021-W01` |
| `2021-01-03` | `2020-W53` | `2021-W02` |
| `2021-01-04` | `2021-W01` | `2021-W02` |

**Locale chỉ quy định cách chia tuần/cách hiển thị trong ngữ cảnh này, không tự chuyển thời điểm hay múi giờ.** Khi cần tuần dùng cho báo cáo quốc tế chuẩn ISO, hãy chỉ định `WeekFields.ISO` dù giao diện người dùng đang là tiếng Anh Mỹ. Khi nghiệp vụ yêu cầu tuần của lịch công ty hay vùng cụ thể, hãy định nghĩa tường minh `firstDayOfWeek` và `minimalDaysInFirstWeek`.

### WeekFields.of(locale) không phải hợp đồng ISO

`WeekFields.of(Locale)` lấy quy ước tuần địa phương từ dữ liệu locale của runtime. Đừng dựa vào việc “locale nào nghe có vẻ châu Âu” để kết luận luôn là ISO trong mọi deployment. Nếu tiêu chuẩn dữ liệu là ISO 8601, **dùng `WeekFields.ISO` hoặc `IsoFields` tường minh**. Nếu cần quy tắc công ty, **dùng `WeekFields.of(firstDay, minimalDays)`** với giá trị đã được xác nhận.

`WeekFields` là immutable và thread-safe; có thể dùng lại cùng một instance. Các field trả về là `TemporalField`, có thể đọc qua `LocalDate.get(...)`.

## 5. Ví dụ Java 17+ chạy được: bảng năm và tuần ở ranh giới năm

Tạo file **`WeekBoundaryDemo.java`**:

```java
import java.time.LocalDate;
import java.time.temporal.WeekFields;
import java.util.List;
import java.util.Locale;

public class WeekBoundaryDemo {
    private static String yearWeek(LocalDate date, WeekFields rules) {
        int year = date.get(rules.weekBasedYear());
        int week = date.get(rules.weekOfWeekBasedYear());
        return String.format(Locale.ROOT, "%04d-W%02d", year, week);
    }

    public static void main(String[] args) {
        List<LocalDate> dates = List.of(
                LocalDate.of(2014, 12, 29),
                LocalDate.of(2018, 12, 31),
                LocalDate.of(2020, 12, 27),
                LocalDate.of(2020, 12, 31),
                LocalDate.of(2021, 1, 1),
                LocalDate.of(2021, 1, 3),
                LocalDate.of(2021, 1, 4)
        );

        WeekFields iso = WeekFields.ISO;
        WeekFields us = WeekFields.of(Locale.US);

        for (LocalDate date : dates) {
            System.out.println(date
                    + " | calendar=" + date.getYear()
                    + " | ISO=" + yearWeek(date, iso)
                    + " | US=" + yearWeek(date, us));
        }
    }
}
```

Biên dịch và chạy với JDK 17 trở lên:

```bash
javac -encoding UTF-8 WeekBoundaryDemo.java
java WeekBoundaryDemo
```

**Kết quả theo quy tắc ISO và US (week rules US như JDK hiện đại):**

```text
2014-12-29 | calendar=2014 | ISO=2015-W01 | US=2015-W01
2018-12-31 | calendar=2018 | ISO=2019-W01 | US=2019-W01
2020-12-27 | calendar=2020 | ISO=2020-W52 | US=2021-W01
2020-12-31 | calendar=2020 | ISO=2020-W53 | US=2021-W01
2021-01-01 | calendar=2021 | ISO=2020-W53 | US=2021-W01
2021-01-03 | calendar=2021 | ISO=2020-W53 | US=2021-W02
2021-01-04 | calendar=2021 | ISO=2021-W01 | US=2021-W02
```

Giải thích:

1. `date.getYear()` chỉ là năm lịch. Nó vẫn là **2021** vào 01/01/2021.
2. `yearWeek(date, iso)` đọc cả `weekBasedYear()` lẫn `weekOfWeekBasedYear()` từ **cùng `WeekFields.ISO`**, nên in `2020-W53` tại 01/01/2021.
3. `yearWeek(date, us)` dùng quy tắc đầu tuần Chủ nhật và tối thiểu một ngày; vì vậy 27/12/2020 đã thuộc `2021-W01`.
4. `String.format(Locale.ROOT, "%04d-W%02d", ...)` chỉ dùng để thêm số 0 bên trái cho nhãn báo cáo. Nó **không tự tính tuần**; hai trường thời gian đã được lấy từ Java API trước đó.
5. Các kết quả tuần ISO có tính quy chuẩn; quy ước tuần của `Locale.US` nên được coi là dữ liệu địa phương được xác nhận trong môi trường chạy khi nó ảnh hưởng hợp đồng nghiệp vụ.

Ví dụ này có thể dùng để kiểm thử năm 52/53 tuần, ranh giới tháng 12/1 và việc thay đổi quy tắc tuần theo locale.

## 6. Lỗi rất dễ gặp: YYYY khác yyyy và uuuu

Trong `DateTimeFormatter.ofPattern(...)`:

| Ký hiệu | Trường | Ý nghĩa |
| --- | --- | --- |
| `Y`, `YYYY` | Week-based-year (localized) | Năm theo tuần; có thể khác năm lịch |
| `w`, `ww` | Week of week-based-year | Số tuần trong năm theo tuần |
| `W` | Week of month (localized) | Tuần trong tháng, **không phải** tuần trong năm |
| `e`, `ee` | Localized day-of-week | Số ngày theo quy tắc đầu tuần của locale |
| `E`, `EEE`, `EEEE` | Tên thứ | Dùng tên thứ thay vì số ngày |
| `y`, `yyyy` | Year-of-era | Năm trong kỷ nguyên (đối với CE thường giống số năm lịch) |
| `u`, `uuuu` | Proleptic year | Năm lịch liên tục, gồm năm 0 và năm âm trong lịch ISO |
| `M` | Month of year | Tháng trong năm |
| `d` | Day of month | Ngày trong tháng |

Một bug kinh điển:

```java
LocalDate date = LocalDate.of(2020, 12, 31);

DateTimeFormatter calendar = DateTimeFormatter
        .ofPattern("uuuu-MM-dd", Locale.US);
DateTimeFormatter dangerous = DateTimeFormatter
        .ofPattern("YYYY-MM-dd", Locale.US);

System.out.println(date.format(calendar));  // 2020-12-31
System.out.println(date.format(dangerous)); // 2021-12-31
```

Đây là **snippet**: yêu cầu `import java.time.LocalDate;`, `java.time.format.DateTimeFormatter;` và `java.util.Locale;`. Với quy tắc tuần US, tháng/ngày vẫn là 12/31 nhưng `YYYY` thuộc **năm tuần 2021**, tạo ra một chuỗi **trông như ngày 31/12/2021 dù dữ liệu gốc là 31/12/2020**. Đó là lý do **không bao giờ dùng `YYYY-MM-dd` chỉ vì muốn in ngày dương lịch**.

Nếu muốn ngày lịch dạng năm-tháng-ngày, ưu tiên `DateTimeFormatter.ISO_LOCAL_DATE` hoặc `uuuu-MM-dd`. Với ngày CE thông thường, `yyyy-MM-dd` cũng thường in cùng năm, nhưng `yyyy` là year-of-era và có quy tắc khác `uuuu` khi xử lý BC/năm 0 hoặc parse nghiêm ngặt.

### Vì sao YYYY không nhất thiết là ISO week-based-year?

Trong `DateTimeFormatter`, các ký hiệu `Y`, `w` và `e` được bản địa hóa theo `Locale` của formatter. Cùng một ngày:

```java
LocalDate date = LocalDate.of(2020, 12, 31);

System.out.println(date.format(
        DateTimeFormatter.ofPattern("YYYY-'W'ww-e", Locale.US)));
System.out.println(date.format(
        DateTimeFormatter.ofPattern("YYYY-'W'ww-e", Locale.UK)));
```

Kết quả theo dữ liệu locale của JDK 24:

```text
2021-W01-5
2020-W53-4
```

Trong ví dụ này:
- `Locale.US` lấy Chủ nhật làm ngày đầu tuần nên thứ Năm là ngày thứ **5** trong tuần và năm tuần đã là **2021**.
- `Locale.UK` áp dụng quy tắc giống ISO, nên thứ Năm là ngày thứ **4**, thuộc **2020-W53**.

**Đừng ép nghĩa “`YYYY` luôn bằng ISO week-based-year”.** Nếu mục tiêu là ISO, dùng `DateTimeFormatter.ISO_WEEK_DATE` hoặc `WeekFields.ISO`; nếu mục tiêu là tuần địa phương, phải chỉ rõ locale và quy tắc ứng với sản phẩm.

## 7. Dùng DateTimeFormatter.ISO_WEEK_DATE để trao đổi tuần ISO

Java cung cấp sẵn formatter cho dạng ngày theo tuần chuẩn ISO:

```java
DateTimeFormatter.ISO_WEEK_DATE
```

Ví dụ:

```java
LocalDate date = LocalDate.of(2021, 1, 1);
String weekDate = date.format(DateTimeFormatter.ISO_WEEK_DATE);
// "2020-W53-5"

LocalDate parsed = LocalDate.parse(
        "2020-W53-5", DateTimeFormatter.ISO_WEEK_DATE);
// 2021-01-01
```

Thành phần của `2020-W53-5`:

- `2020` — **week-based-year**, không phải year dương lịch của ngày.
- `W53` — tuần thứ 53 của năm tuần.
- `5` — thứ Sáu theo ISO (thứ Hai = 1, Chủ nhật = 7).

Khác với chuỗi chỉ có dạng `2020-W53`, `ISO_WEEK_DATE` bao gồm cả **ngày trong tuần** để xác định duy nhất một `LocalDate`. Nếu chỉ lưu cặp week-year + week-number cho lịch báo cáo, đó là **một khoảng tuần**, không phải một ngày cụ thể. Muốn tìm đầu tuần, có thể đặt ngày thứ Hai theo ISO với API temporal phù hợp.

### Ví dụ độc lập: round-trip an toàn cho tuần ISO

Tạo file **`IsoWeekDateDemo.java`**:

```java
import java.time.LocalDate;
import java.time.format.DateTimeFormatter;
import java.time.format.DateTimeParseException;

public class IsoWeekDateDemo {
    public static void main(String[] args) {
        LocalDate source = LocalDate.of(2021, 1, 1);
        String encoded = source.format(DateTimeFormatter.ISO_WEEK_DATE);
        LocalDate decoded = LocalDate.parse(
                encoded, DateTimeFormatter.ISO_WEEK_DATE);

        System.out.println("Date: " + source);
        System.out.println("ISO week date: " + encoded);
        System.out.println("Decoded: " + decoded);
        System.out.println("Same date: " + source.equals(decoded));

        try {
            LocalDate.parse("2021-W53-1", DateTimeFormatter.ISO_WEEK_DATE);
        } catch (DateTimeParseException e) {
            System.out.println("Invalid week: "
                    + e.getClass().getSimpleName());
        }
    }
}
```

Chạy bằng Java 17+:

```bash
javac -encoding UTF-8 IsoWeekDateDemo.java
java IsoWeekDateDemo
```

Stdout:

```text
Date: 2021-01-01
ISO week date: 2020-W53-5
Decoded: 2021-01-01
Same date: true
Invalid week: DateTimeParseException
```

Ví dụ kiểm tra cả trường hợp năm tuần **2021 không có tuần 53 ISO**. `ISO_WEEK_DATE` dùng quy tắc chuẩn với resolver nghiêm ngặt; không tự xem `2021-W53-1` là một ngày hợp lệ. Với chuỗi do người dùng nhập, cần bắt lỗi parse và đưa ra thông báo phù hợp, không tự giảm tuần 53 thành tuần 52.

## 8. WeekFields và IsoFields: chọn công cụ phù hợp

Bên cạnh `WeekFields.ISO`, Java có `java.time.temporal.IsoFields`:

```java
import java.time.LocalDate;
import java.time.temporal.IsoFields;

LocalDate d = LocalDate.of(2021, 1, 1);

int year = d.get(IsoFields.WEEK_BASED_YEAR); // 2020
int week = d.get(IsoFields.WEEK_OF_WEEK_BASED_YEAR); // 53
```

Điểm khác nhau:

| API | Đặc điểm | Dùng khi |
| --- | --- | --- |
| `WeekFields.ISO` | WeekFields cấu hình sẵn theo ISO, có year/week/day fields | Muốn một bộ trường tuần ISO đầy đủ |
| `WeekFields.of(locale)` | Quy tắc đầu tuần và số ngày tối thiểu theo locale | Lịch địa phương/UI |
| `WeekFields.of(firstDay, minDays)` | Quy tắc tuần tùy chỉnh tường minh | Lịch nghiệp vụ/doanh nghiệp |
| `IsoFields.WEEK_BASED_YEAR` | Trường năm tuần ISO | Logic chỉ theo ISO |
| `IsoFields.WEEK_OF_WEEK_BASED_YEAR` | Trường số tuần ISO | Logic chỉ theo ISO |
| `DateTimeFormatter.ISO_WEEK_DATE` | Formatter/parser ngày ISO theo tuần | Trao đổi `yyyy-Www-d` theo nghĩa **năm tuần**, có đủ ngày trong tuần |

`IsoFields` không tự chọn quy tắc của `Locale.US` và là cách rõ để diễn tả **ISO**. `WeekFields.ISO.weekBasedYear()` và `IsoFields.WEEK_BASED_YEAR` cho cùng giá trị đối với `LocalDate` ISO, nhưng không nên trộn các trường lấy từ các **quy tắc tuần khác nhau** trong cùng một mã tuần.

**Lưu ý về chữ `yyyy` trong tài liệu**: khi mô tả một week date ISO, nhóm chữ năm mang ý nghĩa **week-based-year**; trong **pattern Java**, ký tự `yyyy` lại có nghĩa **year-of-era**. Tránh mô tả mập mờ bằng “yyyy-Www”; tốt hơn viết ví dụ cụ thể `2020-W53-5` và dùng `DateTimeFormatter.ISO_WEEK_DATE`.

## 9. Quy tắc tính tuần 53

Theo ISO, phần lớn năm tuần có 52 tuần, nhưng một số năm có 53 tuần. Có thể hiểu trực giác như sau:

- Một năm thường có 365 ngày = 52 tuần + 1 ngày.
- Một năm nhuận có 366 ngày = 52 tuần + 2 ngày.
- Do tuần ISO bắt đầu thứ Hai và tuần 1 có ít nhất bốn ngày trong năm, khi những ngày dư và vị trí thứ trong tuần xếp đúng chỗ sẽ xuất hiện tuần 53.

Một quy tắc thường dùng: **năm lịch bắt đầu vào thứ Năm, hoặc năm nhuận bắt đầu vào thứ Tư**, sẽ có **53 tuần ISO**. Ví dụ năm 2020 nhuận bắt đầu vào thứ Tư, nên có `2020-W53`. Năm 2021 bắt đầu vào thứ Sáu, nên chỉ có 52 tuần ISO.

Tuy nhiên, **đừng tự hardcode** số tuần theo công thức thủ công trong ứng dụng cần nhiều năm, nhiều lịch hoặc quy tắc tuần địa phương. Có thể dùng Java để xác định tuần của ngày 28/12: theo ISO, **ngày 28/12 luôn nằm trong tuần cuối cùng của week-based-year tương ứng với năm lịch đó**.

```java
LocalDate lastWeekAnchor = LocalDate.of(2020, 12, 28);
int lastIsoWeek = lastWeekAnchor.get(
        WeekFields.ISO.weekOfWeekBasedYear()); // 53
```

Đoạn này là snippet với `import java.time.LocalDate;`, `java.time.temporal.WeekFields;`. Đây là một mẹo đơn giản để kiểm tra 52/53 tuần ISO, không phải quy tắc cho mọi hệ tuần địa phương.

## 10. Những lỗi thực tế ở báo cáo, logging và định danh

### 10.1. Dùng YYYY cho ngày lịch

Một formatter `"YYYY-MM-dd"` có thể in ra năm khác vào tháng 12 hoặc đầu tháng 1; mã ngày bị sai một năm dù `LocalDate` vẫn đúng. Nếu chuỗi đó được lưu làm khóa dữ liệu, lỗi có thể lan sang tìm kiếm, đối soát hoặc lập lịch.

**Cách sửa:** dùng `DateTimeFormatter.ISO_LOCAL_DATE`/`"uuuu-MM-dd"` cho ngày, và chỉ dùng week-based-year khi thật sự diễn tả tuần.

### 10.2. Tạo mã tuần từ year lịch và week ISO

Ví dụ sai:

```java
int wrongYear = date.getYear();
int isoWeek = date.get(WeekFields.ISO.weekOfWeekBasedYear());
// ghép wrongYear + "-W" + isoWeek là sai ở ngày giáp ranh.
```

Với 01/01/2021, code trên sẽ tạo **2021-W53**, một tuần ISO **không tồn tại**. Cách đúng là lấy `WeekFields.ISO.weekBasedYear()` cho phần năm.

### 10.3. Dùng “tuần bắt đầu thứ Hai” nhưng quên minimalDays

Chỉ biết tuần bắt đầu thứ Hai **chưa đủ** để xác định week-based-year. Nếu quy tắc ngày tối thiểu là 1 thay vì 4, tuần cuối/đầu năm có thể mang nhãn khác. Bất kỳ hợp đồng báo cáo tuần nào cũng phải nêu **ngày bắt đầu tuần** và **số ngày tối thiểu của tuần đầu năm**.

### 10.4. Nhầm tuần địa phương với ISO

Nếu bộ phận kế toán chốt theo chuẩn ISO còn dashboard dùng `WeekFields.of(Locale.US)`, một sự kiện 31/12/2020 có thể bị gán vào tuần/năm khác. Không nên lấy locale của người đang xem dashboard làm quy tắc phân kỳ kế toán trừ khi sản phẩm chủ động cho phép điều đó.

### 10.5. Nhầm week-of-month với week-of-week-based-year

Pattern chữ hoa `W` (tuần trong tháng) khác chữ thường `w` (tuần trong năm theo tuần), còn `Y` khác `y`. Sai một chữ hoa/thường có thể đổi **ý nghĩa dữ liệu**, không đơn thuần thay cách viết.

### 10.6. Lưu "W53" không kèm week-based-year

Nhãn tuần 53 không xác định tuần ở năm nào. Dùng ít nhất cặp **week-based-year + week**, và nếu cần xác định ngày cụ thể thì thêm **day-of-week**, hoặc lưu ngày bắt đầu/kết thúc tuần theo chính sách đã định.

### 10.7. Dùng LocalDateTime hiện tại mà không xác định múi giờ

Ngày theo tuần được tính trên **ngày lịch**. Cùng một `Instant` có thể là ngày 31/12 ở múi giờ này nhưng đã sang 01/01 ở múi giờ khác. Nếu ứng dụng nhóm sự kiện theo tuần, trước hết phải xác định **ZoneId dùng cho nghiệp vụ**, sau đó chuyển `Instant` sang `LocalDate` trong zone đó rồi mới tính week-based-year. `Locale` không tự quyết định múi giờ.

### 10.8. Dựa vào ngày cuối năm để kiểm thử toàn bộ

Chỉ thử `31/12` chưa đủ. Cần thử cả `29–31/12`, `01–04/01` và các năm đặc biệt có ISO tuần 53. Lỗi xảy ra ở cả hai phía giao thừa.

## 11. Kiểm thử ranh giới và bất biến

Một bộ test tốt nên bao gồm:

| Ca kiểm thử | Kết quả mong đợi theo ISO |
| --- | --- |
| `2014-12-29` | `2015-W01` |
| `2018-12-31` | `2019-W01` |
| `2020-12-31` | `2020-W53` |
| `2021-01-01` | `2020-W53` |
| `2021-01-03` | `2020-W53` |
| `2021-01-04` | `2021-W01` |
| `2021-12-31` | Tuần 52 của năm tuần 2021 |
| `2020-W53-5` qua ISO_WEEK_DATE | Parse thành `2021-01-01` |
| `2021-W53-1` qua ISO_WEEK_DATE | Ném `DateTimeParseException` |

Ngoài bảng ca chuẩn, có thể kiểm thử **bất biến** trong toàn bộ dải ngày:

1. Với mỗi ngày, tính `year = get(weekBasedYear())` và `week = get(weekOfWeekBasedYear())` từ cùng `WeekFields.ISO`.
2. `week` phải nằm trong khoảng `1..53`.
3. Hai ngày cách nhau 7 ngày và có cùng thứ sẽ có mã tuần ISO liên tiếp (có thể sang năm tuần mới).
4. Với từng ngày, `date.format(DateTimeFormatter.ISO_WEEK_DATE)` rồi `LocalDate.parse(..., ISO_WEEK_DATE)` phải trả đúng ngày ban đầu.
5. Với ứng dụng dùng tuần địa phương, chạy lại bộ test sau khi thay đổi locale/provider hoặc quy tắc tuần nghiệp vụ.

Nếu cần kiểm thử theo thời điểm thực (timestamp), hãy cố định **múi giờ** trước khi lấy `LocalDate`. Nếu cần so sánh chuỗi đầu ra, hãy cố định cả quy tắc tuần và định dạng, không phụ thuộc locale mặc định của JVM.

## 12. Các câu hỏi ôn tập

**Câu 1.** Tại sao `LocalDate.of(2021, 1, 1)` có năm lịch 2021 nhưng lại là tuần ISO `2020-W53`?

**Đáp án:** Tuần ISO bắt đầu thứ Hai và tuần 1 phải có ít nhất bốn ngày của năm mới. Tuần 28/12/2020–03/01/2021 chỉ có ba ngày của năm 2021 nên thuộc năm tuần 2020.

**Câu 2.** `DateTimeFormatter.ofPattern("YYYY-MM-dd")` có phải cách đúng để lưu ngày Gregorian?

**Đáp án:** Không. `Y` là năm theo tuần, có thể đổi sớm hoặc muộn hơn năm dương lịch. Dùng `DateTimeFormatter.ISO_LOCAL_DATE` hoặc `"uuuu-MM-dd"`.

**Câu 3.** Hệ thống cần ISO week; có nên dùng `WeekFields.of(Locale.US)`?

**Đáp án:** Không. `WeekFields.of(Locale.US)` sử dụng định nghĩa tuần địa phương, thường Chủ nhật và min 1. Dùng `WeekFields.ISO` hoặc `IsoFields` khi dữ liệu phải theo ISO.

**Câu 4.** Muốn đọc một ngày ISO từ `"2020-W53-5"`, dùng gì?

**Đáp án:** `LocalDate.parse(value, DateTimeFormatter.ISO_WEEK_DATE)`. Kết quả là `2021-01-01`.

**Câu 5.** Vì sao `2021-W53-1` là mã ISO không hợp lệ?

**Đáp án:** Week-based-year 2021 chỉ có 52 tuần ISO; `ISO_WEEK_DATE` với resolver nghiêm ngặt sẽ từ chối chuỗi có tuần 53.

**Câu 6.** Khi chỉ báo cáo tổng theo tuần, dữ liệu có cần ngày trong tuần không?

**Đáp án:** Nếu mỗi dòng đại diện cho một **khoảng tuần**, cặp `week-based-year + week` đủ để nhận diện khoảng đó khi cùng một quy tắc tuần đã được thống nhất. Nếu phải nhận diện một ngày cụ thể, cần thêm thứ trong tuần hoặc ngày lịch.

**Câu 7.** Cùng một sự kiện được hiển thị ở Tokyo và New York nhưng thuộc hai ngày khác nhau. Năm tuần phải theo ngày nào?

**Đáp án:** Theo **múi giờ nghiệp vụ đã được định nghĩa** (ví dụ múi giờ người dùng, địa điểm sự kiện hoặc UTC theo hợp đồng). Chuyển `Instant` sang `LocalDate` của zone đó rồi mới tính tuần; không chọn tùy tiện từ locale.

## 13. Ghi nhớ

- **Năm lịch** và **năm theo tuần** là hai hệ đánh số khác nhau ở ranh giới năm. `2021-01-01` là **2020-W53** theo ISO.
- ISO 8601 quy định **thứ Hai** là đầu tuần và **ít nhất 4 ngày** của năm trong tuần 1.
- Trong Java, lấy **cùng lúc** `WeekFields.ISO.weekBasedYear()` và `WeekFields.ISO.weekOfWeekBasedYear()` để tạo mã tuần ISO.
- `Y`/`YYYY` là **week-based-year theo locale**, khác `y` và `u`. Không dùng `"YYYY-MM-dd"` cho ngày dương lịch.
- `WeekFields.of(Locale)` có thể khác `WeekFields.ISO`. Phân tích, lưu trữ và báo cáo cần thống nhất **quy tắc tuần và múi giờ**.
- `DateTimeFormatter.ISO_WEEK_DATE` là lựa chọn rõ nghĩa để format/parse **ngày theo tuần ISO**, bao gồm cả thứ trong tuần.

Tài liệu tham khảo chính thức:

- [Java SE 21 — WeekFields](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/temporal/WeekFields.html)
- [Java SE 21 — IsoFields](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/temporal/IsoFields.html)
- [Java SE 21 — DateTimeFormatter](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/format/DateTimeFormatter.html)
- [ISO 8601 — Date and time representations](https://www.iso.org/iso-8601-date-and-time-format.html)
