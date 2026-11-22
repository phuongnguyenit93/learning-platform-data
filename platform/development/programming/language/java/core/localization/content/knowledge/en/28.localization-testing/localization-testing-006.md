# Kiểm thử ranh giới năm–tuần, lịch và múi giờ trong Java

Một tính năng ngày giờ có thể chạy đúng suốt phần lớn năm nhưng phát sinh lỗi đúng vào đêm 31/12, ngày 01/01, ngày nhuận 29/02 hoặc giờ hệ điều hành chuyển sang mùa hè (DST). Những lỗi này dễ bị bỏ sót vì bộ test chỉ dùng ngày bình thường, lấy `LocalDate.now()` và `ZoneId.systemDefault()`, hoặc nhầm **năm lịch** với **năm theo tuần**.

Bài Knowledge thuộc nhóm **Kiểm thử và lỗi** trong **Java core - localization**. Mục tiêu là xây một bộ kiểm thử Java 17+ phát hiện chính xác các lỗi ở ba ranh giới liên quan nhưng khác nhau:

1. **Năm lịch và năm theo tuần**: `2021-01-01` thuộc **năm lịch 2021** nhưng thuộc **tuần ISO 53 của năm-tuần 2020**.
2. **Ngày lịch và quy tắc tháng/năm nhuận**: `2024-02-29` hợp lệ, `2023-02-29` không hợp lệ; xử lý `STRICT` có thể khác `SMART`.
3. **Múi giờ, DST và thời điểm tuyệt đối**: một local time có thể **không tồn tại** hoặc **tồn tại hai lần**, và một ngày lịch không bắt buộc dài đúng 24 giờ.

Tất cả ví dụ sử dụng **Java 17+**. Các chương trình chỉ dùng thư viện chuẩn, không phụ thuộc JUnit hay mạng, có lệnh `javac`/`java` riêng. Với các trường hợp thay đổi theo tzdb hoặc dữ liệu locale, bài chỉ rõ chính sách kiểm thử phiên bản; không giả định một snapshot định dạng theo ngôn ngữ là vĩnh viễn.

## 1. Chọn đúng kiểu thời gian trước khi xây test

| Kiểu Java | Biểu diễn | Ví dụ nghiệp vụ | Có zone/offset? |
| --- | --- | --- | --- |
| `LocalDate` | Ngày lịch ISO | Ngày sinh, hạn nộp theo ngày | Không |
| `LocalTime` | Giờ địa phương không kèm ngày | Giờ mở cửa hằng ngày | Không |
| `LocalDateTime` | Ngày và giờ địa phương | Cuộc hẹn 09:00 theo lịch địa phương | Không |
| `Instant` | Một điểm trên trục thời gian UTC | Thời điểm thanh toán, audit timestamp | UTC timeline, không mang vùng người xem |
| `OffsetDateTime` | Ngày-giờ kèm offset cụ thể | Payload `2024-10-27T02:30+02:00` | Có offset, không có toàn bộ quy tắc vùng |
| `ZonedDateTime` | Ngày-giờ, vùng và offset được resolve | Lịch tại `Europe/Berlin` | Có `ZoneId` và offset |
| `YearWeek` | **Không phải kiểu built-in của Java SE 17** | Năm và số tuần theo ISO | Cần tự mô hình hóa hoặc lấy `WeekFields` |

Hai biến kiểu `LocalDate` ở hai máy có cùng năm-tháng-ngày nếu được tạo từ các thành phần giống nhau. Nhưng `LocalDate.now()` không có tham số sẽ dùng clock và zone mặc định, nên cùng **instant** trên hai máy có thể dẫn đến **ngày khác nhau**. Khi cần test deterministic, tránh `now()` trực tiếp hoặc cung cấp `Clock.fixed(...)`.

Không biến ngày không có múi giờ thành instant bằng cách tùy tiện chọn UTC lúc 00:00 nếu nghiệp vụ thực sự là ngày lịch trong một vùng khác. Ngược lại, không lưu chuỗi local datetime không có offset làm dấu thời gian audit toàn cầu.

## 2. Ba khái niệm thường bị nhầm ở ngày đầu và cuối năm

**Năm lịch** của `LocalDate` được lấy bằng `getYear()` hoặc trường `ChronoField.YEAR`.

**Năm theo tuần** (*week-based-year*) được xác định bằng hai quy tắc: **thứ đầu tuần** và **số ngày tối thiểu trong tuần đầu năm**. Theo ISO-8601:

- Tuần bắt đầu vào **thứ Hai**.
- Tuần đầu năm phải chứa **ít nhất bốn ngày của năm mới**.
- Một tuần luôn có **bảy ngày**.
- Tuần ISO có thể bắt đầu trong tháng 12 của năm trước hoặc kéo dài sang đầu tháng 1 của năm sau.
- Một năm-tuần có **52 hoặc 53 tuần**, không được tự áp dụng modulus 52.

**Số thứ tự tuần trong năm lịch** (`weekOfYear`) và **số tuần của năm-tuần** (`weekOfWeekBasedYear`) cũng không đồng nghĩa. Theo quy tắc WeekFields, `weekOfYear` có thể bằng **0** vào các ngày trước tuần đầu tiên của năm lịch; `weekOfWeekBasedYear` thuộc tuần của một week-based-year cụ thể. Với báo cáo ISO theo năm-tuần, nên dùng **cặp** `weekBasedYear` + `weekOfWeekBasedYear`, không ghép `date.getYear()` với số tuần của năm-tuần.

### Các mốc phải có trong test

| Ngày Gregorian/ISO | Năm lịch | Năm-tuần ISO | Tuần ISO | Thứ ISO |
| --- | ---: | ---: | ---: | --- |
| `2018-12-31` | 2018 | 2019 | 01 | 1 (thứ Hai) |
| `2020-12-31` | 2020 | 2020 | 53 | 4 (thứ Năm) |
| `2021-01-01` | 2021 | 2020 | 53 | 5 (thứ Sáu) |
| `2022-01-01` | 2022 | 2021 | 52 | 6 (thứ Bảy) |
| `2023-01-01` | 2023 | 2022 | 52 | 7 (Chủ nhật) |

Dữ liệu này là **quy tắc ISO**, không phải định dạng tuần theo mọi locale. Những locale có tuần bắt đầu Chủ nhật và tiêu chí tuần đầu khác sẽ cho kết quả khác ở ngày ranh giới. Trong bộ test, phải ghi chính xác bạn đang kiểm tra ISO hay quy tắc `WeekFields.of(locale)`.

## 3. Chương trình 1: kiểm thử tuần ISO tại ranh giới năm

Tạo file **`IsoWeekBoundaryDemo.java`**:

```java
import java.time.LocalDate;
import java.time.format.DateTimeFormatter;
import java.time.temporal.WeekFields;

public class IsoWeekBoundaryDemo {
    public static void main(String[] args) {
        LocalDate[] dates = {
                LocalDate.of(2018, 12, 31),
                LocalDate.of(2020, 12, 31),
                LocalDate.of(2021, 1, 1),
                LocalDate.of(2022, 1, 1)
        };

        for (LocalDate date : dates) {
            int year = date.get(WeekFields.ISO.weekBasedYear());
            int week = date.get(
                    WeekFields.ISO.weekOfWeekBasedYear());
            String isoWeekDate = DateTimeFormatter
                    .ISO_WEEK_DATE.format(date);

            System.out.println(date
                    + ": calendar=" + date.getYear()
                    + ", weekYear=" + year
                    + ", week=" + week
                    + ", ISO=" + isoWeekDate);
        }
    }
}
```

```bash
javac -encoding UTF-8 IsoWeekBoundaryDemo.java
java IsoWeekBoundaryDemo
```

Stdout:

```text
2018-12-31: calendar=2018, weekYear=2019, week=1, ISO=2019-W01-1
2020-12-31: calendar=2020, weekYear=2020, week=53, ISO=2020-W53-4
2021-01-01: calendar=2021, weekYear=2020, week=53, ISO=2020-W53-5
2022-01-01: calendar=2022, weekYear=2021, week=52, ISO=2021-W52-6
```

**Những điều chương trình chứng minh:**

1. `date.getYear()` là năm theo lịch, còn `weekBasedYear()` có thể khác.
2. `ISO_WEEK_DATE` ghi rõ **năm-tuần, số tuần và thứ** theo chuẩn ISO, thay vì tự nối `getYear()` với số tuần.
3. Một tuần mang nhãn 2019-W01 đã bắt đầu từ 31/12/2018.
4. 01/01/2021 thuộc 2020-W53; code thống kê `getYear() + "-W" + week` sẽ ghi sai thành 2021-W53.

**Khi lưu dữ liệu:** nếu nghiệp vụ thật sự là kỳ ISO tuần, hãy lưu **(weekBasedYear, weekOfWeekBasedYear)** hoặc ISO week-date đã được parse/validate. Không lưu mỗi `weekNumber` vì nó không xác định một khoảng thời gian duy nhất.

## 4. WeekFields.ISO khác WeekFields theo Locale

`WeekFields.ISO` cố định thứ Hai và tối thiểu bốn ngày cho tuần đầu. `WeekFields.of(Locale.US)` có thể sử dụng Chủ nhật và một ngày tối thiểu theo dữ liệu locale của runtime; một số vùng sử dụng quy tắc khác.

`WeekFields.SUNDAY_START` là một tập quy tắc **cố định** (Chủ nhật, tối thiểu một ngày). Nó rất hữu ích để viết test minh họa mà không phụ thuộc dữ liệu locale của JDK.

**`WeekRuleComparisonDemo.java`**:

```java
import java.time.DayOfWeek;
import java.time.LocalDate;
import java.time.temporal.WeekFields;

public class WeekRuleComparisonDemo {
    public static void main(String[] args) {
        LocalDate date = LocalDate.of(2021, 1, 1);
        WeekFields iso = WeekFields.ISO;
        WeekFields sunday = WeekFields.SUNDAY_START;

        System.out.println("ISO start: "
                + iso.getFirstDayOfWeek());
        System.out.println("ISO minimal: "
                + iso.getMinimalDaysInFirstWeek());
        System.out.println("Sunday start: "
                + sunday.getFirstDayOfWeek());
        System.out.println("Sunday minimal: "
                + sunday.getMinimalDaysInFirstWeek());

        System.out.println("ISO year/week: "
                + date.get(iso.weekBasedYear()) + "/"
                + date.get(iso.weekOfWeekBasedYear()));
        System.out.println("Sunday year/week: "
                + date.get(sunday.weekBasedYear()) + "/"
                + date.get(sunday.weekOfWeekBasedYear()));
    }
}
```

```bash
javac -encoding UTF-8 WeekRuleComparisonDemo.java
java WeekRuleComparisonDemo
```

Stdout:

```text
ISO start: MONDAY
ISO minimal: 4
Sunday start: SUNDAY
Sunday minimal: 1
ISO year/week: 2020/53
Sunday year/week: 2021/1
```

Không có kết quả nào “sai” tự thân: chúng trả lời **hai định nghĩa tuần khác nhau**. Kết quả đúng phụ thuộc yêu cầu: báo cáo ISO dùng `WeekFields.ISO`, lịch vùng dùng `WeekFields.of(userLocale)` và cần test với dữ liệu provider/JDK mục tiêu.

Khi tạo cache key cho tuần, **không dùng locale mặc định server** để tính tuần nếu schema đã quy định ISO. Nếu doanh nghiệp dùng lịch tuần riêng (ví dụ tuần bắt đầu Chủ nhật nhưng tối thiểu bốn ngày), tạo `WeekFields.of(DayOfWeek.SUNDAY, 4)` rồi kiểm thử rõ.

## 5. Bẫy pattern: yyyy, uuuu và YYYY

Trong `DateTimeFormatter`:

| Pattern | Ý nghĩa | Tình huống |
| --- | --- | --- |
| `uuuu` | Proleptic calendar year | ISO LocalDate, parse STRICT |
| `yyyy` | Year-of-era | Năm theo kỷ nguyên; parse STRICT cần xử lý era |
| `YYYY` | Localized week-based-year | Tuần-năm theo quy tắc locale, có thể khác năm lịch |
| `MM` | Tháng | Không phải phút |
| `mm` | Phút | Không phải tháng |
| `dd` | Ngày trong tháng | Không phải ngày trong năm |
| `DD` | Ngày trong năm | Không phải ngày trong tháng |
| `ww` | Tuần của năm-tuần | Phải ghép đúng week-based-year và weekday |

**Lỗi thường gặp:** copy mẫu `YYYY-MM-dd` để lưu ngày ISO. Ở các mốc đầu/cuối năm, `YYYY` có thể mang năm của **tuần**, còn `MM-dd` lại là tháng/ngày lịch; một chuỗi như vậy dễ trở nên tự mâu thuẫn. Dùng `DateTimeFormatter.ISO_LOCAL_DATE` cho ngày ISO máy đọc hoặc `"uuuu-MM-dd"` với resolver phù hợp.

`DateTimeFormatter.ofPattern("YYYY", locale)` là pattern theo **localized week-based-year**, không đảm bảo cùng ISO ở mọi locale. Với các dữ liệu cần tuần ISO, ưu tiên `DateTimeFormatter.ISO_WEEK_DATE` hoặc trường `WeekFields.ISO`; với giao diện theo người dùng, có thể tạo formatter localized nhưng phải test locale/provider cụ thể.

### Chương trình 3: năm lịch khác năm-tuần

**`PatternYearBoundaryDemo.java`**:

```java
import java.time.LocalDate;
import java.time.format.DateTimeFormatter;
import java.util.Locale;

public class PatternYearBoundaryDemo {
    public static void main(String[] args) {
        LocalDate date = LocalDate.of(2021, 1, 1);
        DateTimeFormatter calendar = DateTimeFormatter
                .ofPattern("uuuu-MM-dd", Locale.ROOT);

        System.out.println("Calendar: "
                + calendar.format(date));
        System.out.println("ISO week: "
                + DateTimeFormatter.ISO_WEEK_DATE.format(date));

        System.out.println("yyyy year-of-era: "
                + DateTimeFormatter
                        .ofPattern("yyyy", Locale.ROOT)
                        .format(date));
    }
}
```

```bash
javac -encoding UTF-8 PatternYearBoundaryDemo.java
java PatternYearBoundaryDemo
```

Stdout:

```text
Calendar: 2021-01-01
ISO week: 2020-W53-5
yyyy year-of-era: 2021
```

Ở đây `yyyy` và `uuuu` đều in năm 2021 vì ngày thuộc kỷ nguyên hiện đại; chúng **không hoàn toàn tương đương** khi parse nghiêm ngặt hoặc với năm ngoài Common Era. Không thay `yyyy` bằng `YYYY` vì nhầm chữ hoa là “bốn chữ số năm”.

## 6. Test với nhiều năm thay vì chỉ một ngày 01/01

Không thể suy ra mọi năm đều có số tuần giống nhau. Một số năm ISO có 53 tuần, một số 52 tuần; cách tuần giao sang năm kế bên phải được kiểm tra theo hai hướng. Để phát hiện regression, xây bộ dữ liệu gồm:

- 28–31/12 năm trước.
- 01–04/01 năm sau.
- Ngày thứ Hai cuối/đầu năm.
- Năm nhuận và năm không nhuận.
- Các năm ISO có 53 tuần (ví dụ 2020) và 52 tuần (ví dụ 2021).
- Các quy tắc tuần khác nếu ứng dụng hỗ trợ locale riêng.

Trong test logic, không chỉ so chuỗi hiển thị. Hãy kiểm tra **bất biến**: các ngày liên tiếp trong một tuần chia sẻ cùng cặp `weekBasedYear` + `weekOfWeekBasedYear`; mỗi tuần có bảy ngày; `DateTimeFormatter.ISO_WEEK_DATE` parse/format round-trip đúng trong phạm vi được hỗ trợ.

### Kiểm thử round-trip không nhầm định dạng

Nếu nguồn đã là một ISO week-date, `LocalDate.parse(weekText, DateTimeFormatter.ISO_WEEK_DATE)` chuyển về ngày lịch ISO. Đừng parse `2020-W53-5` bằng `ISO_LOCAL_DATE` vì đó là **hai loại dữ liệu khác nhau**, không phải hai cách viết của cùng một chuỗi ngày mà parser có thể tự đoán.

## 7. Ngày nhuận, cuối tháng và năm lịch

Trong lịch ISO proleptic Gregorian, **năm nhuận** có tháng 2 ngày 29. Quy tắc cơ bản: năm chia hết cho 4, ngoại trừ năm chia hết 100 nhưng không chia hết 400.

| Trường hợp | Kết quả |
| --- | --- |
| `2024-02-29` | Hợp lệ |
| `2023-02-29` | Không hợp lệ |
| `2000-02-29` | Hợp lệ (chia hết cho 400) |
| `1900-02-29` | Không hợp lệ (chia hết cho 100 nhưng không chia hết cho 400) |
| `2024-04-31` | Không hợp lệ, tháng 4 có 30 ngày |
| `2024-12-31.plusDays(1)` | `2025-01-01` |

**`LocalDate.of(2023,2,29)` ném `DateTimeException`**, không trả null. Điều đó khác với việc parse văn bản theo một formatter dùng `ResolverStyle.SMART`, vốn có thể điều chỉnh một số ngày vượt cuối tháng về ngày cuối hợp lệ.

### Chương trình 4: ngày nhuận và bước sang năm

**`LeapBoundaryDemo.java`**:

```java
import java.time.DateTimeException;
import java.time.LocalDate;

public class LeapBoundaryDemo {
    public static void main(String[] args) {
        LocalDate leap = LocalDate.of(2024, 2, 29);

        System.out.println("Leap: " + leap);
        System.out.println("Next day: " + leap.plusDays(1));
        System.out.println("Year end: "
                + LocalDate.of(2024, 12, 31).plusDays(1));
        System.out.println("2024 leap: "
                + java.time.Year.isLeap(2024));
        System.out.println("1900 leap: "
                + java.time.Year.isLeap(1900));
        System.out.println("2000 leap: "
                + java.time.Year.isLeap(2000));

        try {
            LocalDate.of(2023, 2, 29);
            System.out.println("Unexpected acceptance");
        } catch (DateTimeException ex) {
            System.out.println("Invalid date rejected");
        }
    }
}
```

```bash
javac -encoding UTF-8 LeapBoundaryDemo.java
java LeapBoundaryDemo
```

Stdout:

```text
Leap: 2024-02-29
Next day: 2024-03-01
Year end: 2025-01-01
2024 leap: true
1900 leap: false
2000 leap: true
Invalid date rejected
```

Không dùng `new Date(year, month, day)` kiểu legacy (constructor cũ và index tháng khác) cho test mới. `java.time.LocalDate` thể hiện rõ ý nghĩa ngày lịch và fail sớm khi đầu vào không hợp lệ.

## 8. ResolverStyle: SMART không đồng nghĩa STRICT

Một lớp lỗi quan trọng là parser **chấp nhận chuỗi ngày không hợp lệ** rồi tự điều chỉnh mà caller không biết. `DateTimeFormatter.ofPattern(...)` thường dùng `ResolverStyle.SMART` mặc định; `DateTimeFormatter.ISO_LOCAL_DATE` dùng `STRICT`.

Với `2023-02-29`:

- `SMART` có thể resolve về `2023-02-28`.
- `STRICT` từ chối vì ngày 29/02 không tồn tại trong năm 2023.
- `LENIENT` có quy tắc cộng/trừ các trường theo cách nới lỏng hơn; không nên dùng cho hợp đồng machine-readable không cho phép điều chỉnh im lặng.

**Quan trọng về ký hiệu năm:** pattern `yyyy` là *year-of-era*, còn `uuuu` là proleptic year. Khi dùng `STRICT` và không cung cấp era, `"yyyy-MM-dd"` có thể không resolve thành `LocalDate` dù ngày hợp lệ. Do đó, với năm ISO kiểm thử nghiêm ngặt, chọn `uuuu-MM-dd` hoặc `ISO_LOCAL_DATE`.

### Chương trình 5: SMART vs STRICT

**`ResolverBoundaryDemo.java`**:

```java
import java.time.LocalDate;
import java.time.format.DateTimeFormatter;
import java.time.format.DateTimeParseException;
import java.time.format.ResolverStyle;
import java.util.Locale;

public class ResolverBoundaryDemo {
    public static void main(String[] args) {
        String invalid = "2023-02-29";

        DateTimeFormatter smart = DateTimeFormatter
                .ofPattern("uuuu-MM-dd", Locale.ROOT);
        DateTimeFormatter strict = smart.withResolverStyle(
                ResolverStyle.STRICT);

        System.out.println("SMART: "
                + LocalDate.parse(invalid, smart));

        try {
            LocalDate.parse(invalid, strict);
            System.out.println("Unexpected strict acceptance");
        } catch (DateTimeParseException ex) {
            System.out.println("STRICT: rejected");
        }

        System.out.println("Valid leap day: "
                + LocalDate.parse("2024-02-29", strict));
    }
}
```

```bash
javac -encoding UTF-8 ResolverBoundaryDemo.java
java ResolverBoundaryDemo
```

Stdout:

```text
SMART: 2023-02-28
STRICT: rejected
Valid leap day: 2024-02-29
```

**Kiểm thử an toàn:** Với dữ liệu API, lịch tài chính và thông tin cần chính xác, quyết định rõ có cho phép sửa ngày sai hay không. Thường nên **reject** input sai và báo lỗi xác thực thay vì im lặng điều chỉnh.

## 9. ZoneId, ZoneOffset, Instant và local datetime

Bốn khái niệm này phải có test tách biệt:

| Khái niệm | Ví dụ | Ý nghĩa |
| --- | --- | --- |
| `Instant` | `2024-01-01T00:30:00Z` | Một thời điểm tuyệt đối |
| `ZoneOffset` | `+07:00` | Chênh lệch so với UTC tại một thời điểm |
| `ZoneId` | `Europe/Berlin` | Quy tắc vùng, có thay đổi offset theo thời gian |
| `LocalDateTime` | `2024-10-27T02:30` | Giờ tường thuật địa phương, chưa rõ instant |

`ZoneId.of("Asia/Ho_Chi_Minh")` không đồng nghĩa với `ZoneOffset.ofHours(7)` cho **mọi thời điểm lịch sử**: ZoneId có quy tắc vùng theo tzdb, còn offset cố định không thể biểu diễn thay đổi lịch sử và DST của vùng khác.

**Một `Instant` có thể ứng với hai ngày lịch khác nhau ở hai vùng.** Vì vậy, nếu hệ thống lọc giao dịch “ngày hôm nay” cho người dùng, phải xác định ngày theo **userZone** rồi tính ranh giới thời điểm cho ngày đó; đừng lấy ngày UTC và cho rằng ở mọi quốc gia nó vẫn là ngày ấy.

### Chương trình 6: cùng instant, hai ngày lịch

**`ZoneCalendarBoundaryDemo.java`**:

```java
import java.time.Instant;
import java.time.ZoneId;
import java.time.ZoneOffset;

public class ZoneCalendarBoundaryDemo {
    public static void main(String[] args) {
        Instant instant = Instant.parse(
                "2024-01-01T00:30:00Z");
        ZoneId losAngeles = ZoneId.of("America/Los_Angeles");
        ZoneId tokyo = ZoneId.of("Asia/Tokyo");

        System.out.println("UTC date: "
                + instant.atZone(ZoneOffset.UTC).toLocalDate());
        System.out.println("LA date: "
                + instant.atZone(losAngeles).toLocalDate());
        System.out.println("Tokyo date: "
                + instant.atZone(tokyo).toLocalDate());
        System.out.println("Same instant: "
                + instant.equals(
                        instant.atZone(losAngeles).toInstant()));
    }
}
```

```bash
javac -encoding UTF-8 ZoneCalendarBoundaryDemo.java
java ZoneCalendarBoundaryDemo
```

Stdout theo tzdb thông dụng có quy tắc lịch sử tương ứng:

```text
UTC date: 2024-01-01
LA date: 2023-12-31
Tokyo date: 2024-01-01
Same instant: true
```

Bộ test này **không gọi `ZoneId.systemDefault()`** và không dùng thời điểm hiện tại; kết quả có thể tái lập giữa các máy cùng tzdb phù hợp. Với hệ thống yêu cầu tái lập tuyệt đối trên nhiều năm, ghi phiên bản tzdb trong môi trường CI và test integration.

## 10. DST gap: một local time không tồn tại

Tại `Europe/Berlin` vào **31/03/2024**, đồng hồ nhảy từ 02:00 sang 03:00. Vì vậy local time **2024-03-31T02:30** không có offset hợp lệ trong vùng này: đó là một **gap**.

`LocalDateTime.of(2024,3,31,2,30)` vẫn **tạo được**: đối tượng chỉ biết thành phần ngày-giờ, không có zone rules. Nhưng khi gọi `atZone(berlin)`, `ZonedDateTime` mặc định điều chỉnh local time qua gap để tạo thời điểm hợp lệ, từ 02:30 thành 03:30 với offset `+02:00`.

**Không được suy ra điều chỉnh mặc định là chính sách nghiệp vụ đúng.** Một hệ thống đặt lịch khám có thể cần **từ chối giờ không tồn tại** và yêu cầu người dùng chọn lại, thay vì tự dời cuộc hẹn một giờ.

### Chương trình 7: quan sát DST gap

File **`DstGapDemo.java`**:

```java
import java.time.LocalDateTime;
import java.time.ZoneId;
import java.time.ZonedDateTime;
import java.time.zone.ZoneRules;

public class DstGapDemo {
    public static void main(String[] args) {
        ZoneId berlin = ZoneId.of("Europe/Berlin");
        LocalDateTime input = LocalDateTime.of(
                2024, 3, 31, 2, 30);
        ZoneRules rules = berlin.getRules();

        System.out.println("Valid offsets: "
                + rules.getValidOffsets(input).size());
        System.out.println("Gap: "
                + rules.getTransition(input).isGap());

        ZonedDateTime resolved = input.atZone(berlin);
        System.out.println("Resolved local: "
                + resolved.toLocalDateTime());
        System.out.println("Resolved offset: "
                + resolved.getOffset());
    }
}
```

```bash
javac -encoding UTF-8 DstGapDemo.java
java DstGapDemo
```

Stdout theo dữ liệu tzdb về Berlin năm 2024:

```text
Valid offsets: 0
Gap: true
Resolved local: 2024-03-31T03:30
Resolved offset: +02:00
```

**Lý do:** `ZoneRules.getValidOffsets(localDateTime)` cho một danh sách có thể chứa **0**, **1** hoặc **2** offset. Trong gap, kết quả có 0 offset; `getTransition` cung cấp chuyển tiếp khi có. Nếu input là một ngày thường không chuyển giờ, `getTransition(...)` thường trả `null` — không gọi `isGap()` khi chưa kiểm tra null trong code dùng cho mọi input.

### Định nghĩa chính sách xử lý gap

Chọn một trong các quy tắc được sản phẩm công bố:

- **Reject:** từ chối local time không tồn tại.
- **Shift forward:** chuyển sang thời điểm hợp lệ sau gap theo quy tắc rõ, ví dụ hành vi mặc định `atZone`.
- **Use explicit instant/offset:** chỉ khi nguồn thực sự đã xác định một thời điểm; không tự gán offset cho dữ liệu mơ hồ.

Với lịch hẹn người dùng tự chọn, reject thường dễ giải thích hơn shift âm thầm. Với lịch chạy tác vụ lặp, cần định nghĩa rõ khi một lần chạy rơi vào gap: bỏ qua, dời đi, hay chạy theo elapsed time.

## 11. DST overlap: một local time có hai thời điểm

Tại `Europe/Berlin` vào **27/10/2024**, đồng hồ lùi từ 03:00 mùa hè về 02:00 mùa đông. Local time **2024-10-27T02:30** xảy ra **hai lần**:

- Với offset `+02:00`, tương ứng instant `2024-10-27T00:30:00Z`.
- Với offset `+01:00`, tương ứng instant `2024-10-27T01:30:00Z`.

Chỉ lưu `LocalDateTime` sẽ **không thể phân biệt** hai lần 02:30. `ZonedDateTime.ofLocal` hoặc `LocalDateTime.atZone` theo mặc định chọn **offset sớm hơn theo chuyển tiếp** khi có overlap (ở ví dụ là `+02:00`); `withLaterOffsetAtOverlap()` cho phép chọn offset còn lại.

### Chương trình 8: hai instant trong overlap

File **`DstOverlapDemo.java`**:

```java
import java.time.Duration;
import java.time.LocalDateTime;
import java.time.ZoneId;
import java.time.ZonedDateTime;

public class DstOverlapDemo {
    public static void main(String[] args) {
        ZoneId berlin = ZoneId.of("Europe/Berlin");
        LocalDateTime input = LocalDateTime.of(
                2024, 10, 27, 2, 30);

        System.out.println("Valid offsets: "
                + berlin.getRules().getValidOffsets(input).size());

        ZonedDateTime earlier = input.atZone(berlin);
        ZonedDateTime later = earlier.withLaterOffsetAtOverlap();

        System.out.println("Earlier offset: "
                + earlier.getOffset());
        System.out.println("Later offset: "
                + later.getOffset());
        System.out.println("Same local time: "
                + earlier.toLocalDateTime().equals(
                        later.toLocalDateTime()));
        System.out.println("Instant difference (min): "
                + Duration.between(
                        earlier.toInstant(),
                        later.toInstant()).toMinutes());
    }
}
```

```bash
javac -encoding UTF-8 DstOverlapDemo.java
java DstOverlapDemo
```

Stdout theo tzdb Berlin năm 2024:

```text
Valid offsets: 2
Earlier offset: +02:00
Later offset: +01:00
Same local time: true
Instant difference (min): 60
```

**Bẫy kiểm thử:** nếu hai cuộc hẹn có cùng `LocalDateTime` tại overlap, chúng có thể là hai thời điểm khác nhau. Cần lưu offset/zone và chính sách resolve hoặc instant đã xác nhận. `ZoneOffset` đơn lẻ xác định chênh lệch tại thời điểm nhưng không ghi toàn bộ vùng/quy tắc lâu dài.

## 12. API kiểm tra giờ hợp lệ theo ZoneRules

Một hàm validation hữu ích có thể phân loại **NORMAL**, **GAP**, **OVERLAP** thay vì chỉ trả true/false. Dưới đây là chương trình Java 17 độc lập.

**`LocalTimeClassificationDemo.java`**:

```java
import java.time.LocalDateTime;
import java.time.ZoneId;
import java.util.List;
import java.time.ZoneOffset;

public class LocalTimeClassificationDemo {
    static String classify(
            LocalDateTime local, ZoneId zone) {
        List<ZoneOffset> offsets =
                zone.getRules().getValidOffsets(local);
        return switch (offsets.size()) {
            case 0 -> "GAP";
            case 1 -> "NORMAL";
            case 2 -> "OVERLAP";
            default -> throw new IllegalStateException(
                    "Unexpected number of offsets");
        };
    }

    public static void main(String[] args) {
        ZoneId zone = ZoneId.of("Europe/Berlin");
        System.out.println(classify(
                LocalDateTime.of(2024, 3, 31, 2, 30), zone));
        System.out.println(classify(
                LocalDateTime.of(2024, 7, 15, 12, 0), zone));
        System.out.println(classify(
                LocalDateTime.of(2024, 10, 27, 2, 30), zone));
    }
}
```

```bash
javac -encoding UTF-8 LocalTimeClassificationDemo.java
java LocalTimeClassificationDemo
```

Stdout theo tzdb Berlin năm 2024:

```text
GAP
NORMAL
OVERLAP
```

Khi xây API đặt lịch, cần thêm **chính sách cho overlap**: cho người dùng chọn offset, chọn sớm/muộn theo hợp đồng, hoặc yêu cầu timestamp có offset rõ. Chỉ kiểm tra `getValidOffsets.size() >= 1` rồi luôn chọn phần tử 0 là một chính sách **chọn thời điểm sớm** chưa chắc được người dùng đồng ý.

**Đừng gọi `rules.getOffset(localDateTime)` rồi tin đó là kiểm tra duy nhất:** method này trả một offset “phù hợp” ngay cả trong gap/overlap theo hợp đồng, nên nó không tự báo rằng local time là duy nhất. Dùng `getValidOffsets` để phân loại.

## 13. Ngày đổi giờ không nhất thiết dài 24 giờ

Nếu business yêu cầu “mọi giao dịch trong ngày 31/03/2024 tại Berlin”, khoảng đúng là:

```text
start = 2024-03-31 atStartOfDay(Europe/Berlin)
end   = 2024-04-01 atStartOfDay(Europe/Berlin)
Interval = [start.toInstant(), end.toInstant())
```

Khoảng này chỉ dài **23 giờ** vì DST gap. Ngày 27/10/2024 tại Berlin lại dài **25 giờ** vì overlap.

**Không dùng `startInstant.plus(24, HOURS)` làm “ngày mai” theo lịch địa phương** trong mọi vùng, vì đó là 24 giờ elapsed time chứ không phải điểm đầu ngày sau của một ngày có DST.

### Chương trình 10: 23 giờ và 25 giờ

**`DstDayLengthDemo.java`**:

```java
import java.time.Duration;
import java.time.LocalDate;
import java.time.ZoneId;
import java.time.ZonedDateTime;

public class DstDayLengthDemo {
    private static long hours(
            LocalDate day, ZoneId zone) {
        ZonedDateTime start = day.atStartOfDay(zone);
        ZonedDateTime end = day.plusDays(1)
                .atStartOfDay(zone);
        return Duration.between(
                start.toInstant(),
                end.toInstant()).toHours();
    }

    public static void main(String[] args) {
        ZoneId berlin = ZoneId.of("Europe/Berlin");

        System.out.println("Spring hours: "
                + hours(LocalDate.of(2024, 3, 31), berlin));
        System.out.println("Autumn hours: "
                + hours(LocalDate.of(2024, 10, 27), berlin));

        ZonedDateTime springStart =
                LocalDate.of(2024, 3, 31)
                        .atStartOfDay(berlin);
        System.out.println("Spring +24h local: "
                + springStart.plusHours(24).toLocalTime());
    }
}
```

```bash
javac -encoding UTF-8 DstDayLengthDemo.java
java DstDayLengthDemo
```

Stdout theo tzdb Berlin năm 2024:

```text
Spring hours: 23
Autumn hours: 25
Spring +24h local: 01:00
```

**Phân biệt:**

- `plusDays(1)` trên `LocalDate` là một bước theo **lịch**.
- `Instant.plus(Duration.ofDays(1))` là **24 giờ tuyệt đối**.
- `ZonedDateTime.plusDays(1)` là thao tác theo **local timeline** và resolve zone; `plusHours(24)` tính theo **instant timeline**.
- Với báo cáo theo ngày, phải tạo hai mốc **start-of-day cho hai ngày lịch** rồi đổi sang instant, thay vì cộng 86.400 giây mặc định.

**Một số vùng có chuyển tiếp ngay lúc nửa đêm:** `LocalDate.atStartOfDay(zone)` trả thời điểm hợp lệ đầu tiên của ngày theo zone, có thể không phải 00:00 nếu có gap. Một số vùng còn từng bỏ hẳn một ngày lịch khi thay đổi đường đổi ngày; không giả định mọi vùng có đầy đủ ngày giờ lịch sử.

## 14. Khoảng thời gian đúng cho truy vấn database

Giả sử user muốn lọc các bản ghi của một `LocalDate` tại một `ZoneId`. Phương pháp chuẩn là khoảng **nửa mở**:

```text
Instant startInclusive = day.atStartOfDay(zone).toInstant();
Instant endExclusive =
    day.plusDays(1).atStartOfDay(zone).toInstant();

Filter: instant >= startInclusive AND instant < endExclusive
```

Đây là **pseudocode dạng Java fragment**, cần khai báo `day` kiểu `LocalDate` và `zone` kiểu `ZoneId`. Khoảng nửa mở không chồng lấn ranh giới giữa các ngày và không cần suy đoán nanosecond cuối ngày.

**Không dùng** `BETWEEN start AND end` nếu ý định là kết thúc exclusive, vì `BETWEEN` thường nhận cả hai đầu. Dùng điều kiện riêng `>=` và `<`; trong SQL phải parameterize các instant bằng driver/type tương ứng, không nối chuỗi format theo locale.

Nếu một hệ quản trị lưu timestamp không có zone, hợp đồng mapping sang instant phải được định nghĩa rõ: không tự cho rằng một `TIMESTAMP WITHOUT TIME ZONE` là UTC hoặc giờ địa phương của server. Việc lưu `Instant`, UTC hoặc timezone ID cần được thống nhất từ đầu.

## 15. Đừng phụ thuộc đồng hồ thật hoặc timezone mặc định của CI

Một unit test nguy hiểm:

```java
// Anti-pattern: kết quả đổi theo giờ máy test chạy.
LocalDate today = LocalDate.now();
ZoneId zone = ZoneId.systemDefault();
```

Đây là fragment minh họa anti-pattern. Khi CI chạy vào cuối năm, ở container UTC hay khi máy đổi timezone, kết quả biến động ngoài ý muốn.

**Clock** có thể được inject để kiểm soát thời điểm, và **ZoneId** phải được chọn tường minh theo nghiệp vụ. `Clock.fixed(...)` giúp test một thời điểm giống nhau trên mọi máy.

### Chương trình 11: cùng Instant nhưng ngày khác ở hai zone

**`FixedClockBoundaryDemo.java`**:

```java
import java.time.Clock;
import java.time.Instant;
import java.time.LocalDate;
import java.time.ZoneId;
import java.time.ZoneOffset;

public class FixedClockBoundaryDemo {
    public static void main(String[] args) {
        Instant fixed = Instant.parse(
                "2020-12-31T23:30:00Z");
        Clock utc = Clock.fixed(fixed, ZoneOffset.UTC);
        Clock tokyo = utc.withZone(ZoneId.of("Asia/Tokyo"));

        System.out.println("UTC today: "
                + LocalDate.now(utc));
        System.out.println("Tokyo today: "
                + LocalDate.now(tokyo));
        System.out.println("Same instant: "
                + utc.instant().equals(tokyo.instant()));
    }
}
```

```bash
javac -encoding UTF-8 FixedClockBoundaryDemo.java
java FixedClockBoundaryDemo
```

Stdout:

```text
UTC today: 2020-12-31
Tokyo today: 2021-01-01
Same instant: true
```

Nó chứng minh một hệ thống có thể đồng thời cần **Instant cố định** và **ngày lịch theo vùng người dùng**. Nếu business báo cáo theo ngày Việt Nam, lựa chọn timezone phải là thông tin của contract, không được suy từ `Locale` hoặc từ host của backend.

## 16. Unit test không cần thư viện ngoài: kiểm tra điều kiện tự động

Một chương trình test nên **fail có chủ đích** khi quy tắc sai, không chỉ in output để người lập trình quan sát. Java có `assert` nhưng assertion Java **mặc định có thể bị tắt nếu không bật `-ea`**. Để ví dụ luôn kiểm tra, ta dùng helper ném `AssertionError`.

**`CalendarRegressionTest.java`**:

```java
import java.time.Duration;
import java.time.LocalDate;
import java.time.LocalDateTime;
import java.time.ZoneId;
import java.time.temporal.WeekFields;

public class CalendarRegressionTest {
    private static void check(
            boolean condition, String message) {
        if (!condition) {
            throw new AssertionError(message);
        }
    }

    public static void main(String[] args) {
        LocalDate newYear = LocalDate.of(2021, 1, 1);
        check(newYear.getYear() == 2021,
                "calendar year");
        check(newYear.get(
                WeekFields.ISO.weekBasedYear()) == 2020,
                "ISO week-year");
        check(newYear.get(
                WeekFields.ISO.weekOfWeekBasedYear()) == 53,
                "ISO week 53");

        check(LocalDate.of(2024, 2, 29)
                .plusDays(1)
                .equals(LocalDate.of(2024, 3, 1)),
                "leap day rollover");

        ZoneId berlin = ZoneId.of("Europe/Berlin");
        check(berlin.getRules().getValidOffsets(
                LocalDateTime.of(2024, 3, 31, 2, 30))
                .size() == 0, "spring gap");
        check(berlin.getRules().getValidOffsets(
                LocalDateTime.of(2024, 10, 27, 2, 30))
                .size() == 2, "autumn overlap");

        long springHours = Duration.between(
                LocalDate.of(2024, 3, 31)
                        .atStartOfDay(berlin).toInstant(),
                LocalDate.of(2024, 4, 1)
                        .atStartOfDay(berlin).toInstant())
                .toHours();
        check(springHours == 23, "DST day duration");

        System.out.println("All calendar checks passed");
    }
}
```

```bash
javac -encoding UTF-8 CalendarRegressionTest.java
java CalendarRegressionTest
```

Stdout nếu dữ liệu tzdb hỗ trợ các quy tắc Berlin 2024:

```text
All calendar checks passed
```

Nếu một assertion thất bại, chương trình ném `AssertionError` và dừng với exit status không thành công; đây là đặc điểm mong muốn của kiểm thử. Trong dự án có JUnit 5, có thể viết các test case tương ứng bằng `@ParameterizedTest`/`@MethodSource`, nhưng cần dependency JUnit và runner riêng. Bài này chọn Java SE thuần để mọi ví dụ có thể chạy với JDK 17.

## 17. Property-based và metamorphic tests cho lịch

Ngoài các mốc cố định, có thể kiểm thử những **bất biến tổng quát** cho nhiều ngày sinh ngẫu nhiên (với seed xác định):

- **Round-trip date:** `LocalDate.parse(date.toString())` bằng `date` khi dùng ISO.
- **Ngày liên tiếp:** `date.plusDays(1).minusDays(1).equals(date)` trong phạm vi hợp lệ.
- **ISO week-date:** `LocalDate.parse(ISO_WEEK_DATE.format(date), ISO_WEEK_DATE).equals(date)`.
- **Năm lịch không thay tùy formatter UI:** dữ liệu `LocalDate` ban đầu giữ nguyên sau format.
- **Đổi instant theo zone:** `instant.atZone(zone).toInstant().equals(instant)` với vùng hợp lệ.
- **Overlap:** hai offset hợp lệ khác nhau phải cho hai instant riêng, nhưng cùng local datetime.
- **Gap:** danh sách offset hợp lệ có độ dài 0, và mọi cách resolve đều phải có chính sách nghiệp vụ rõ.
- **Ngày theo region:** khoảng `[startOfDay, nextStartOfDay)` không chồng với khoảng ngày kề bên, ngay cả ngày dài 23/25 giờ.
- **Thời gian hiển thị:** format/parse phải dùng cùng zone/offset/locale/resolver và precision nếu hợp đồng cho phép round-trip.

Không tạo nhiều ngày ngẫu nhiên với seed thay đổi liên tục để rồi test thất bại không thể tái hiện. Chọn seed cố định, log seed và dữ liệu đầu vào khi fail (không có PII). Với ngày lịch xa và các vùng có quy tắc lịch sử phức tạp, không kỳ vọng mọi property đều hợp lệ ngoài phạm vi đối tượng đã định nghĩa.

## 18. Thứ tự test: unit, integration và snapshot locale

**Unit tests deterministic** nên dùng:

- `LocalDate.of(...)` / `Instant.parse(...)` cố định.
- `WeekFields.ISO` hoặc `WeekFields.of(firstDay,minimalDays)` cố định.
- `ZoneId` cụ thể và các mốc tzdb đã biết.
- `ResolverStyle.STRICT` cho grammar API cần hợp đồng rõ.
- `Clock.fixed` thay vì đồng hồ hệ thống.

**Integration tests** nên kiểm tra:

- Tzdb mà runtime production thực sự dùng.
- Locale data/CLDR và formatter localized theo các `Locale` sản phẩm hỗ trợ.
- Mapping database/JDBC của `Instant`/timestamp.
- Serialization JSON/CSV và timezone metadata.
- Runtime trên Windows/Linux/container hoặc JDK vendor khác nếu đó là nền tảng được hỗ trợ.
- Hành vi lịch cũ `java.util.Calendar`/`SimpleDateFormat` nếu đang migrate.

**Snapshot string** của `DateTimeFormatter.ofLocalizedDate(...)`, tên tháng, zone name hay `WeekFields.of(Locale)` có thể thay khi nâng cấp dữ liệu CLDR/JDK. Snapshot nên khóa môi trường hoặc so các invariants ý nghĩa thay vì dùng giá trị copy từ một máy như chuẩn vĩnh viễn.

Đừng trộn test “format số theo locale” với test “thời điểm là đúng instant”. Locale ảnh hưởng trình bày, **không** tự xác định vùng thời gian và không tự biến năm lịch thành năm-tuần.

## 19. Lỗi di trú từ Date, Calendar và SimpleDateFormat

Trong code Java cũ, các yếu tố sau dễ tạo regression:

| Legacy API/thói quen | Rủi ro khi di trú | Test cần thêm |
| --- | --- | --- |
| `SimpleDateFormat("YYYY-MM-dd")` | Week-year khác calendar year quanh 01/01 | 31/12, 01/01, locale khác |
| `SimpleDateFormat("yyyy-MM-dd")` | Calendar/leniency/timezone của formatter cũ | Ngày sai, zone cụ thể |
| `Calendar.WEEK_OF_YEAR` | Phụ thuộc ngày đầu tuần/minimal days và `Calendar.getWeekYear()` | Năm ISO 53 tuần và đầu năm |
| `new Date(...)` constructor deprecated | Tháng đếm từ 0, năm có offset lịch sử | Chọn `LocalDate.of` thay |
| `DateFormat.parse` | Có thể đọc prefix, lenient normalization | Validate full input và strict |
| `Calendar.add(DATE, 1)` | Local date và instant elapsed khác nhau ở DST | 23/25 giờ quanh transition |
| `Date.getTime()` | Millisecond epoch, không mang zone hiển thị | Convert `Instant` và `ZoneId` rõ |
| `TimeZone.getDefault()` | Phụ thuộc JVM/host | Test với zone được inject |
| `SimpleDateFormat` dùng static cho multi-thread | Mutable, không thread-safe | Không chia sẻ hoặc dùng java.time |
| Calendar của locale không ISO | Quy tắc lịch/era có thể khác | Chọn Chronology rõ cho nghiệp vụ |

**Gregorian cutover:** `GregorianCalendar` legacy mặc định dùng một điểm chuyển đổi Julian/Gregorian, còn `LocalDate` dùng proleptic Gregorian theo ISO. Với dữ liệu lịch sử xa, hai API không nhất thiết cho cùng ngày trong mọi khoảng thời gian. Không dùng vài test năm hiện đại để kết luận phép di trú đúng cho toàn bộ dữ liệu lịch sử.

### Năm theo tuần của SimpleDateFormat

Trong `SimpleDateFormat`, `Y` cũng mang nghĩa *week-year* trong calendar có hỗ trợ. Nhưng cơ chế `Calendar` và quy tắc tuần locale có thể khác JDK provider/chronology, nên không đổi ký tự `Y`/`y` trong một pattern rồi coi là xử lý xong. Nếu dữ liệu nghiệp vụ là ISO, hãy định nghĩa ISO từ đầu ở cả hai phía khi migrate và đối chiếu các ngày biên.

## 20. Test ma trận ưu tiên

Một ma trận nhỏ vẫn bao phủ nhiều lỗi nếu chọn đúng dữ liệu:

| Nhóm | Đầu vào | Kết quả cần kiểm tra |
| --- | --- | --- |
| ISO năm-tuần | 2018-12-31 | 2019-W01-1 |
| ISO năm-tuần | 2020-12-31 | 2020-W53-4 |
| ISO năm-tuần | 2021-01-01 | 2020-W53-5 |
| ISO năm-tuần | 2022-01-01 | 2021-W52-6 |
| Khác quy tắc tuần | 2021-01-01 | ISO 2020/53, SUNDAY_START 2021/1 |
| Năm nhuận | 2024-02-29 | Hợp lệ |
| Năm không nhuận | 2023-02-29 | STRICT từ chối |
| Tháng không có ngày 31 | 2024-04-31 | STRICT từ chối |
| SMART parser | 2023-02-29 | Có thể thành 2023-02-28 |
| DST gap Berlin | 2024-03-31 02:30 | 0 offset hợp lệ |
| DST overlap Berlin | 2024-10-27 02:30 | 2 offset hợp lệ |
| Ngày DST gap | 2024-03-31 | Khoảng giữa hai midnight dài 23 giờ |
| Ngày DST overlap | 2024-10-27 | Khoảng giữa hai midnight dài 25 giờ |
| Ranh giới ngày theo zone | 2024-01-01T00:30Z | Ngày LA = 2023-12-31 |
| Clock fixed | 2020-12-31T23:30Z | UTC ngày 31/12, Tokyo ngày 01/01 |
| Query interval | Berlin 2024-03-31 | Khoảng `[start,end)` tính theo zone, không cộng 24h |
| Format ISO | `2021-01-01` | `ISO_LOCAL_DATE`; không nhầm `YYYY` |
| Legacy compatibility | Date/Calendar | Test timezone, leniency, lịch sử |

Khi báo lỗi production, ghi lại **instant/LocalDateTime đầu vào, zone ID, offset nếu có, phiên bản tzdb/JDK và locale/rule tuần**. Nếu không có dữ liệu này, hai người ở hai môi trường có thể tái hiện hai kết quả khác nhau mà không biết nguyên nhân.

## 21. Tình huống kiểm thử thực tế

### Tình huống A — Báo cáo tuần cuối năm

Yêu cầu: doanh nghiệp tính doanh thu tuần ISO. Dữ liệu phát sinh ngày 01/01/2021. Nếu code ghi `getYear()=2021` và `week=53`, báo cáo bị nhóm vào kỳ **2021-W53** không tồn tại theo ISO. Sửa bằng cách lấy **cặp** `WeekFields.ISO.weekBasedYear()` và `weekOfWeekBasedYear()`, rồi test các ngày đầu/cuối năm.

### Tình huống B — Lịch hẹn 02:30 bị mất

Khách đặt lịch lúc 02:30 ngày 31/03/2024 ở Berlin. `LocalDateTime` nhận giá trị, nhưng giờ đó không tồn tại khi đổi DST. Nếu hệ thống âm thầm gọi `atZone`, lịch được dời thành 03:30. Thay vì dựa vào điều chỉnh ngầm, hãy dùng `ZoneRules.getValidOffsets`, báo giờ không hợp lệ và yêu cầu chọn lại, hoặc áp dụng chính sách dịch giờ đã công bố.

### Tình huống C — Hai tác vụ cùng xuất hiện lúc 02:30

Ngày 27/10/2024 tại Berlin có hai lần 02:30. Nếu log chỉ lưu `"2024-10-27 02:30"` mà không có offset, sau này không thể xác định thứ tự thực tế giữa hai tác vụ. Lưu `Instant` để audit, cộng `ZoneId` hoặc offset nếu cần tái dựng thông tin người dùng nhìn thấy.

### Tình huống D — Báo cáo theo ngày bị thiếu một giờ

Report chạy với tiêu chí local date 31/03/2024 Berlin. Nếu query lấy `startInstant` rồi cộng 24 giờ, nó kéo thêm thời gian của ngày 01/04. Nếu date rơi vào DST overlap, cộng 24 giờ lại bỏ sót giờ cuối của ngày. Cần dùng `day.atStartOfDay(zone)` và `day.plusDays(1).atStartOfDay(zone)`.

### Tình huống E — CI chỉ fail khi chạy ở Nhật

Test dùng `LocalDate.now()` và máy development ở UTC, trong khi CI chạy ở timezone Asia/Tokyo. Ở ranh giới ngày, cùng instant cho ngày khác. Sửa bằng cách inject `Clock.fixed` và zone tường minh; tách test “ngày theo zone user” khỏi test “thời điểm UTC”.

## 22. Bài tập

**Bài 1 — Năm-tuần:** viết bảng ISO week-date cho 2018-12-31, 2020-12-31, 2021-01-01, 2022-01-01 bằng `ISO_WEEK_DATE`. So với `getYear()` và giải thích hai mốc có weekBasedYear khác calendar year.

**Bài 2 — Quy tắc tuần:** tạo `WeekFields.of(DayOfWeek.SUNDAY, 1)` và `WeekFields.ISO`. Kiểm tra 2021-01-01; đổi minimalDaysInFirstWeek thành 4 và quan sát thay đổi.

**Bài 3 — Strict parser:** thử parse `2023-02-29`, `2024-02-29` và `2024-04-31` bằng `ISO_LOCAL_DATE`. So với `DateTimeFormatter.ofPattern("uuuu-MM-dd")` SMART; viết assertion rằng chỉ những ngày hợp lệ được nhận theo hợp đồng.

**Bài 4 — Gap/overlap:** dùng `Europe/Berlin` để kiểm tra `getValidOffsets` tại 2024-03-31 02:30 và 2024-10-27 02:30. Trong overlap, dùng `withLaterOffsetAtOverlap()` và so hai instant.

**Bài 5 — Số giờ trong ngày:** tính `Duration` giữa hai `atStartOfDay(zone)` liên tiếp cho 31/03 và 27/10/2024. Vì sao kết quả không phải 24h? Viết query interval half-open.

**Bài 6 — Clock cố định:** tạo `Clock.fixed(Instant.parse("2020-12-31T23:30:00Z"), ZoneOffset.UTC)`. Chuyển Clock sang `Asia/Tokyo` và so `LocalDate.now(clock)`; không dùng giờ máy đang chạy.

**Bài 7 — Hệ thống nhiều vùng:** thiết kế hợp đồng lưu cho event giao dịch và cuộc hẹn: trường nào là `Instant`, `LocalDate`, `LocalDateTime`, `ZoneId`, `ZoneOffset`? Xử lý gap/overlap thế nào?

**Bài 8 — Legacy:** lập bảng chuyển từ `Calendar.getWeekYear`/`SimpleDateFormat` sang `WeekFields.ISO` và `DateTimeFormatter.ISO_WEEK_DATE`; chọn ca test cho vùng dữ liệu lịch sử nếu hệ thống có dùng Julian/Gregorian cutover.

## 23. Tài liệu chính thức và kiểm chứng

- [Java SE 17 — WeekFields](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/temporal/WeekFields.html): ISO và localized week rules, `weekBasedYear`, `weekOfWeekBasedYear`, week 0.
- [Java SE 17 — DateTimeFormatter](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/format/DateTimeFormatter.html): `uuuu`/`yyyy`/`YYYY`, `ISO_WEEK_DATE`, `ISO_LOCAL_DATE` và resolver styles.
- [Java SE 17 — ZonedDateTime](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/ZonedDateTime.html): xử lý gap/overlap, `withLaterOffsetAtOverlap`, calendar vs instant timeline.
- [Java SE 17 — ZoneRules](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/zone/ZoneRules.html): `getValidOffsets`, `getTransition` và timezone rules.
- [Java SE 17 — LocalDate](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/LocalDate.html): ngày ISO, leap days, `atStartOfDay(zone)`.
- [Java SE 17 — Clock](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/Clock.html): `Clock.fixed` và thử nghiệm không phụ thuộc thời gian thực.
- [Java SE 17 — ResolverStyle](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/format/ResolverStyle.html): `STRICT`, `SMART`, `LENIENT`.
- [IANA Time Zone Database](https://www.iana.org/time-zones): dữ liệu quy tắc timezone mà JDK/tzdb provider dùng; cập nhật có thể thay đổi khi chính sách quốc gia đổi.

## 24. Ghi nhớ

- **Năm lịch ≠ năm-tuần.** ISO week-year có thể lệch so với calendar year ở đầu/cuối năm; tính `weekBasedYear` và `weekOfWeekBasedYear` như một cặp.
- **`yyyy`, `uuuu` và `YYYY` không hoán đổi.** Tránh `YYYY-MM-dd` cho ngày ISO; dùng `ISO_LOCAL_DATE` hoặc `uuuu-MM-dd` với strict parsing.
- **Ngày lịch có quy tắc nhuận.** Kiểm tra 29/02, ngày cuối tháng và parser `STRICT`; `SMART` có thể điều chỉnh ngày sai.
- **Một local datetime có thể không tồn tại hoặc tồn tại hai lần trong DST.** Dùng `ZoneRules.getValidOffsets` để phân biệt 0/1/2 offset.
- **Ngày địa phương không nhất thiết 24 giờ.** Tính ranh giới `[startOfDay(day), startOfDay(day+1))` bằng `ZoneId`, không cộng cố định 24 giờ cho báo cáo theo ngày.
- **Không dùng default timezone và `now()` trong unit test định lượng.** Inject `Clock.fixed`, zone và locale/rule tuần cụ thể; ghi nhận tzdb/JDK khi dùng những mốc lịch sử.
- **Unit test phải tự fail khi sai.** Dùng assertion helper/JUnit cùng dữ liệu biên; đừng chỉ chạy và nhìn một ngày bình thường.

Một bộ kiểm thử ranh giới đáng tin không cần rất nhiều ngày ngẫu nhiên; nó cần **đúng các mốc khiến những khái niệm dễ nhầm trở nên khác nhau**, rồi xác nhận hợp đồng nghiệp vụ đúng trên cả lịch, năm-tuần và trục thời gian.