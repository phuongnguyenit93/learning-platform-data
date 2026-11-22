# Kiểm thử cuối tháng, năm nhuận và chuyển giờ trong Java

**Chủ đề:** Khoảng thời gian (`java.time`, Java 8+). **Mục tiêu:** kiểm thử chính xác các phép tính ngày–tháng và khoảng thời gian khi đi qua **ngày cuối tháng**, **29/02 của năm nhuận** và **chuyển đổi offset/múi giờ**. Người học cần lựa chọn đúng giữa `Period` (khoảng theo lịch) và `Duration` (thời lượng theo giây), viết test dựa trên ngày cố định, nhận biết điều chỉnh ngày không hợp lệ và xác minh những kết quả có thể chênh một giờ do daylight saving time (DST).

Các kiểu `LocalDate`, `YearMonth`, `Period`, `Duration`, `ZonedDateTime`, `ZoneId` và `ZoneRules` đều là **API Java SE hiện hành**, không dựa vào cách xử lý ngày giờ cũ đã lỗi thời. Những chương trình bên dưới chạy với **Java 17+**. Ngày chuyển giờ dùng trong bài là các **mốc đã xảy ra tại Europe/Berlin năm 2024**; những quy tắc múi giờ tương lai có thể thay đổi theo bản cập nhật tzdb.

> **Điểm cần nhớ:** `Period.ofDays(1)` trên `ZonedDateTime` biểu diễn **một ngày lịch địa phương**, còn `Duration.ofDays(1)` là **đúng 86.400 giây (24 giờ)**. Qua một lần chuyển giờ, hai kết quả có thể khác nhau. Tương tự, `LocalDate.plusMonths` có thể điều chỉnh ngày 31 thành 28/29/30, và phép điều chỉnh này có thể làm lịch định kỳ “trôi” ngày nếu cứ cộng dồn từ kết quả trước.

## 1. Chọn đúng mô hình thời gian trước khi kiểm thử

Không phải mọi “khoảng thời gian” đều là một số giờ cố định.

| Kiểu / API | Biểu diễn | Ví dụ nhu cầu |
| --- | --- | --- |
| `LocalDate` | Ngày lịch ISO, **không giờ/zone** | Ngày phát hành hóa đơn, ngày hết hạn |
| `LocalDateTime` | Ngày + giờ cục bộ, **chưa có offset** | Người dùng nhập lịch hẹn ở văn phòng |
| `ZonedDateTime` | Ngày–giờ + `ZoneId` + offset được giải quyết | Lịch hẹn tại một thành phố |
| `Instant` | Điểm trên trục thời gian toàn cầu | Thời điểm sự kiện thực sự xảy ra |
| `YearMonth` | Một năm và một tháng | Kỳ thanh toán tháng |
| `MonthDay` | Một ngày trong năm **không kèm năm** | Sinh nhật, kỷ niệm |
| `Period` | Lượng năm–tháng–ngày **theo lịch ISO** | Gia hạn một tháng, hẹn sau một ngày lịch |
| `Duration` | Lượng giây/nanogiây **theo thời gian thực** | Timeout 24 giờ, đo thời gian chạy |
| `ChronoUnit.DAYS.between` | Đếm ngày theo loại Temporal được truyền | Số ngày giữa hai `LocalDate` |
| `TemporalAdjusters.lastDayOfMonth()` | Điều chỉnh tới ngày cuối tháng | Tính ngày chốt sổ |

**Quy tắc lựa chọn:** Khi có cụm “ngày 31, tháng sau, năm sau, ngày làm việc”, thường cần lịch với `LocalDate` / `YearMonth` / `Period`. Khi có cụm “sau đúng 24 giờ, thời lượng giao dịch, timeout”, thường cần `Instant` / `Duration`. Nếu muốn giữ “09:00 tại Berlin” qua nhiều tháng, phải giữ cả `ZoneId`; một offset cố định không thể thay thế các luật của vùng.

### 1.1. `Period` khác `Duration` ở đâu?

`Period.ofDays(1)` chứa thành phần **days=1**; nó mô tả một ngày theo lịch, không quy định rằng ngày này có 24 giờ ở một vùng DST. `Duration.ofDays(1)` tương đương chính xác `Duration.ofHours(24)`.

```java
Period calendarDay = Period.ofDays(1);
Duration elapsedDay = Duration.ofDays(1);
System.out.println(calendarDay);              // P1D
System.out.println(elapsedDay.toHours());       // 24
```

Đây là **đoạn mã trong phương thức**, cần import `java.time.Period` và `java.time.Duration`. Những dòng `//` là nhận xét kết quả, không phải log của chương trình mẫu độc lập.

`Period` thường hợp với `LocalDate.plus(period)` hoặc `ZonedDateTime.plus(period)`. `Duration` có thể cộng lên `Instant` hoặc `ZonedDateTime`; đừng dùng `Duration.between(LocalDate, LocalDate)` để cố tính số ngày trên lịch, bởi `LocalDate` không hỗ trợ các đơn vị giây cần thiết cho Duration. Dùng `ChronoUnit.DAYS.between` hoặc `Period.between` trên `LocalDate`.

## 2. Ma trận ca biên cần có

| Nhóm | Ví dụ | Điều nên kiểm tra |
| --- | --- | --- |
| Ngày cuối tháng 31 ngày | `2024-01-31 + 1 tháng` | `2024-02-29` |
| Ngày cuối tháng 30 ngày | `2024-04-30 + 1 tháng` | `2024-05-30` với phép cộng trực tiếp |
| Năm thường | `2023-01-31 + 1 tháng` | `2023-02-28` |
| Năm nhuận | `2024-02-29` | Ngày hợp lệ, `YearMonth.lengthOfMonth() == 29` |
| Ngày không hợp lệ | `2023-02-29` | API tạo `LocalDate` phải ném `DateTimeException` |
| Năm tròn thế kỷ | `1900`, `2000` | 1900 không nhuận, 2000 nhuận |
| Cộng tháng nhiều lần | `Jan31 + 1M + 1M` | Khác với `Jan31 + 2M` |
| `Period.between` | `Jan31 → Feb29` | Có thể là `P29D` chứ không phải `P1M` |
| Bắt đầu trong gap DST | Berlin `2024-03-31T02:30` | 0 offset hợp lệ, mặc định dịch lên |
| Bắt đầu trong overlap | Berlin `2024-10-27T02:30` | 2 offset hợp lệ, 2 Instant |
| Cộng ngày qua spring DST | `2024-03-30T12:00` + 1 ngày | 23 giờ thực tế nếu giữ 12:00 |
| Cộng ngày qua autumn DST | `2024-10-26T12:00` + 1 ngày | 25 giờ thực tế nếu giữ 12:00 |
| Đổi vùng | Berlin → vùng khác | Phân biệt giữ Instant và giữ local |
| Ngày đầu tháng bị bỏ qua | Ngày lịch tại vùng có chuyển đổi lớn | `atStartOfDay(zone)` trả mốc **hợp lệ sớm nhất**, không mặc định midnight |
| Ngày gần giới hạn Java | `LocalDate.MAX` / `MIN` | Không tự wrap; có thể có exception |
| Danh sách ngày định kỳ | 12 kỳ cuối tháng | Không trôi ngày sau 28/29 |

Các ví dụ **không nên chỉ kiểm tra hai phương thức có kết quả giống nhau**; cần kiểm tra với **expected cụ thể** để tránh hai thuật toán cùng mắc một lỗi.

## 3. Cuối tháng: `plusMonths` điều chỉnh ngày như thế nào?

`LocalDate.plusMonths(long)` cố giữ **day-of-month** nếu ngày đó tồn tại trong tháng đích. Nếu không, ngày được **điều chỉnh về ngày hợp lệ cuối cùng** của tháng đích.

Ví dụ:

```java
LocalDate jan31 = LocalDate.of(2024, 1, 31);
LocalDate feb29 = jan31.plusMonths(1); // 2024-02-29
LocalDate mar31 = jan31.plusMonths(2); // 2024-03-31
```

Đây là **đoạn trong phương thức**, cần import `java.time.LocalDate`. Đây không phải “cộng đúng 30 ngày” hay “cộng đúng 31 ngày”: độ dài tháng tùy tháng và năm.

**Phân biệt hai lần cộng một tháng với một lần cộng hai tháng:**

```java
LocalDate chained = jan31.plusMonths(1).plusMonths(1);
LocalDate direct = jan31.plusMonths(2);
```

Kết quả **chained = 2024-03-29**, **direct = 2024-03-31**. Lần đầu đã điều chỉnh 31/01 thành 29/02, vì thế lần thứ hai từ **ngày 29** chuyển sang 29/03. Còn cộng thẳng hai tháng từ **ngày 31** cho 31/03.

**Không được suy luận** `date.plusMonths(a).plusMonths(b).equals(date.plusMonths(a+b))` trong mọi tình huống; phép điều chỉnh ngày cuối tháng có thể khiến biểu thức không tương đương. Đây là lý do một lịch chốt sổ “**luôn vào ngày cuối tháng**” không nên chỉ lặp `current = current.plusMonths(1)` từ kỳ trước.

### 3.1. Kỳ hạn lịch và ngày 31

Nếu điều khoản thực sự là “**sau đúng một tháng tính từ ngày ký**”, `plusMonths(1)` thường thể hiện mô hình lịch cơ bản, nhưng sản phẩm vẫn phải quy định cách xử lý ngày không tồn tại (28/29/30). Nếu điều khoản là “**ngày cuối mỗi tháng**”, hãy lấy `YearMonth.atEndOfMonth()` cho từng kỳ.

Một lưu ý quan trọng về quy tắc cộng vào ngày 30:

```java
LocalDate april30 = LocalDate.of(2024, 4, 30);
System.out.println(april30.plusMonths(1)); // 2024-05-30
```

Đây là đoạn mã trong phương thức. Tháng 5 có 31 ngày nhưng phép `plusMonths(1)` **giữ ngày 30**, không tự nhận ra “30/04 là ngày cuối tháng nên 31/05 cũng phải là cuối tháng”.

### 3.2. `YearMonth` cho quy tắc luôn là cuối tháng

```java
YearMonth month = YearMonth.of(2024, 1);
LocalDate janEnd = month.atEndOfMonth();              // 2024-01-31
LocalDate febEnd = month.plusMonths(1).atEndOfMonth(); // 2024-02-29
LocalDate marEnd = month.plusMonths(2).atEndOfMonth(); // 2024-03-31
```

Đây là đoạn trong phương thức, import `java.time.YearMonth` và `LocalDate`. `YearMonth` giữ năm/tháng mà không mang một ngày bị điều chỉnh ở kỳ trước, vì vậy **không tích lũy drift** khi sinh các kỳ cuối tháng.

Một cách khác là `date.with(TemporalAdjusters.lastDayOfMonth())`, nhưng nếu yêu cầu có danh sách các **kỳ tháng khác nhau**, `YearMonth` làm khóa kỳ rõ ràng hơn.

## 4. Ví dụ hoàn chỉnh: So sánh cộng tháng và lịch cuối tháng

Tạo file **`EndOfMonthDemo.java`**:

```java
import java.time.LocalDate;
import java.time.Period;
import java.time.YearMonth;

public class EndOfMonthDemo {
    public static void main(String[] args) {
        LocalDate jan31 = LocalDate.of(2024, 1, 31);

        System.out.println("Jan31 + 1 month: "
                + jan31.plusMonths(1));
        System.out.println("Jan31 + 2 months: "
                + jan31.plusMonths(2));
        System.out.println("Jan31 + 1m + 1m: "
                + jan31.plusMonths(1).plusMonths(1));
        System.out.println("Jan31 + Period(2m): "
                + jan31.plus(Period.ofMonths(2)));

        YearMonth january = YearMonth.of(2024, 1);
        for (int i = 0; i < 4; i++) {
            System.out.println("Billing " + i + ": "
                    + january.plusMonths(i).atEndOfMonth());
        }

        System.out.println("April30 + 1 month: "
                + LocalDate.of(2024, 4, 30).plusMonths(1));
    }
}
```

Biên dịch và chạy bằng JDK 17+:

```bash
javac --release 17 EndOfMonthDemo.java
java EndOfMonthDemo
```

**Stdout:**

```text
Jan31 + 1 month: 2024-02-29
Jan31 + 2 months: 2024-03-31
Jan31 + 1m + 1m: 2024-03-29
Jan31 + Period(2m): 2024-03-31
Billing 0: 2024-01-31
Billing 1: 2024-02-29
Billing 2: 2024-03-31
Billing 3: 2024-04-30
April30 + 1 month: 2024-05-30
```

**Đọc kết quả:** `Period.ofMonths(2)` trên `LocalDate` có cùng ý nghĩa cộng trực tiếp **hai tháng từ ngày nguồn**. Trong khi đó lặp `plusMonths(1)` qua các kết quả trung gian có thể làm mất day-of-month gốc. `YearMonth.plusMonths(i).atEndOfMonth()` tạo bốn kỳ độc lập, giữ đúng ranh giới tháng.

## 5. Năm nhuận: Test bằng `Year`, `YearMonth` và `MonthDay`

Java `java.time` sử dụng quy tắc ISO proleptic Gregorian. Trong phạm vi năm dương lịch thường gặp:

- Năm chia hết cho 4 là năm nhuận, **trừ** năm chia hết cho 100 nhưng **không** chia hết cho 400.
- `2024` nhuận, `2023` không nhuận.
- `1900` không nhuận; `2000` nhuận.
- `Year.isLeap(year)` là API chuẩn, không cần tự viết biểu thức boolean lặp lại ở nhiều nơi.

```java
boolean leap2024 = Year.isLeap(2024); // true
boolean leap2023 = Year.isLeap(2023); // false
boolean leap1900 = Year.isLeap(1900); // false
boolean leap2000 = Year.isLeap(2000); // true
```

Đây là đoạn mã trong phương thức, import `java.time.Year`. Với năm tháng cụ thể:

```java
int feb2024 = YearMonth.of(2024, 2).lengthOfMonth(); // 29
int feb2023 = YearMonth.of(2023, 2).lengthOfMonth(); // 28
```

Đây là đoạn trong phương thức, import `java.time.YearMonth`. `YearMonth.atEndOfMonth()` cho đúng ngày chốt tháng, và không phải tự suy đoán 28/29.

### 5.1. Tạo ngày 29/02: Có lỗi hay được điều chỉnh?

Phân biệt:

- `LocalDate.of(2024, 2, 29)` **hợp lệ**.
- `LocalDate.of(2023, 2, 29)` **ném `DateTimeException`**; tạo một ngày không hợp lệ không tự đổi thành 28/02.
- `LocalDate.of(2024, 2, 29).plusYears(1)` cho **2025-02-28** do phép cộng năm phải điều chỉnh thành ngày hợp lệ.
- `MonthDay.of(2, 29)` biểu diễn ngày–tháng lặp lại **không chứa năm**; `isValidYear(2023)` trả false.
- `MonthDay.of(2, 29).atYear(2023)` mặc định **điều chỉnh thành 2023-02-28** theo hợp đồng; không phải lỗi.

Đây là những API có **hợp đồng khác nhau**, không được dùng thay thế mà không hiểu ý nghĩa dữ liệu.

### 5.2. Cộng rồi trừ một năm không nhất thiết quay lại ngày ban đầu

```java
LocalDate leapDay = LocalDate.of(2024, 2, 29);
LocalDate nextYear = leapDay.plusYears(1); // 2025-02-28
LocalDate back = nextYear.minusYears(1);  // 2024-02-28
```

Đây là đoạn trong phương thức. Ngày gốc `2024-02-29` **không được khôi phục** vì sau bước đầu đã bị điều chỉnh thành ngày 28. Không viết test với giả định `date.plusYears(1).minusYears(1).equals(date)` đúng cho mọi ngày.

Nếu ứng dụng tổ chức kỷ niệm 29/02, cần **quy định**: vào năm không nhuận sẽ chọn 28/02, 01/03, bỏ qua hay thông báo không tồn tại. `MonthDay` giúp lưu ý định ngày–tháng, còn `isValidYear` giúp kiểm tra trước khi quyết định.

## 6. Ví dụ Java 17+: Năm nhuận và dữ liệu đầu vào không hợp lệ

Tạo file **`LeapYearEdgeDemo.java`**:

```java
import java.time.DateTimeException;
import java.time.LocalDate;
import java.time.MonthDay;
import java.time.Period;
import java.time.Year;
import java.time.YearMonth;
import java.time.temporal.ChronoUnit;

public class LeapYearEdgeDemo {
    public static void main(String[] args) {
        System.out.println("Leap 2024: " + Year.isLeap(2024));
        System.out.println("Leap 2023: " + Year.isLeap(2023));
        System.out.println("Leap 1900: " + Year.isLeap(1900));
        System.out.println("Leap 2000: " + Year.isLeap(2000));

        System.out.println("Feb 2024 days: "
                + YearMonth.of(2024, 2).lengthOfMonth());
        System.out.println("Feb 2023 days: "
                + YearMonth.of(2023, 2).lengthOfMonth());

        LocalDate leapDay = LocalDate.of(2024, 2, 29);
        System.out.println("Leap + 1y: "
                + leapDay.plusYears(1));
        System.out.println("Leap + 1y - 1y: "
                + leapDay.plusYears(1).minusYears(1));

        MonthDay feb29 = MonthDay.of(2, 29);
        System.out.println("Feb29 in 2023: "
                + feb29.isValidYear(2023));
        System.out.println("Feb29.atYear(2023): "
                + feb29.atYear(2023));

        LocalDate jan31 = LocalDate.of(2024, 1, 31);
        LocalDate febEnd = LocalDate.of(2024, 2, 29);
        System.out.println("Period Jan31-Feb29: "
                + Period.between(jan31, febEnd));
        System.out.println("Days Jan31-Feb29: "
                + ChronoUnit.DAYS.between(jan31, febEnd));

        try {
            LocalDate.of(2023, 2, 29);
            System.out.println("Invalid date rejected: false");
        } catch (DateTimeException ex) {
            System.out.println("Invalid date rejected: true");
        }
    }
}
```

Chạy:

```bash
javac --release 17 LeapYearEdgeDemo.java
java LeapYearEdgeDemo
```

**Stdout:**

```text
Leap 2024: true
Leap 2023: false
Leap 1900: false
Leap 2000: true
Feb 2024 days: 29
Feb 2023 days: 28
Leap + 1y: 2025-02-28
Leap + 1y - 1y: 2024-02-28
Feb29 in 2023: false
Feb29.atYear(2023): 2023-02-28
Period Jan31-Feb29: P29D
Days Jan31-Feb29: 29
Invalid date rejected: true
```

**Đáng chú ý:** `Period.between(2024-01-31, 2024-02-29)` trả `P29D` — không phải `P1M`. Vì 29/02 chưa đạt ngày 31 trong tháng đích, không có một tháng trọn theo quy tắc tính `Period.between`. Khi cần **số ngày thực tế**, dùng `ChronoUnit.DAYS.between` giữa hai `LocalDate`; nếu cần **thời lượng giây**, phải cung cấp thời điểm và timezone/offset phù hợp.

## 7. `Period.between`, `ChronoUnit` và `Duration.between` không đồng nghĩa

### 7.1. Period giữa hai LocalDate

`Period.between(startInclusive, endExclusive)` trả một `Period` gồm **năm, tháng, ngày**. Nó không phải `Duration` và không có phương thức “toDays chính xác” cho mọi Period có tháng/năm, bởi tháng có độ dài khác nhau.

Ví dụ kiểm chứng:

```java
LocalDate jan31 = LocalDate.of(2024, 1, 31);
LocalDate feb29 = LocalDate.of(2024, 2, 29);
LocalDate mar31 = LocalDate.of(2024, 3, 31);

Period shortPeriod = Period.between(jan31, feb29); // P29D
Period months = Period.between(jan31, mar31);     // P2M
```

Đây là đoạn trong phương thức. `Period.ofMonths(1).getDays() == 0` chứ không có nghĩa một tháng dài 0 ngày. `getDays()` chỉ là **thành phần ngày** của Period.

`Period.ofDays(30).getMonths() == 0`, không phải 1: Java không tự đổi 30 ngày lịch thành một tháng vì thiếu ngày bắt đầu và độ dài tháng khác nhau.

### 7.2. normalize không chuyển ngày thành tháng

```java
Period normalized = Period.ofMonths(15).normalized();
// P1Y3M
Period days = Period.ofDays(30).normalized();
// P30D
```

Đây là đoạn trong phương thức. `normalized()` xử lý việc quy đổi **tháng thành năm + tháng**, không biến mọi 30 ngày thành một tháng. `toTotalMonths()` cộng thành phần năm và tháng, **không** coi thành phần ngày như tháng.

### 7.3. Cần số ngày, số giờ, hay số tháng?

| Câu hỏi | Cách phù hợp |
| --- | --- |
| Có bao nhiêu ngày lịch từ 2024-02-28 tới 2024-03-01? | `ChronoUnit.DAYS.between(localStart, localEnd)` → 2 |
| Chênh lệch theo năm/tháng/ngày giữa hai LocalDate? | `Period.between(start, end)` |
| Có bao nhiêu tháng lịch trọn theo quy tắc Java? | `ChronoUnit.MONTHS.between(start, end)`, nắm rõ end-of-month |
| Có bao nhiêu giờ thực tế giữa hai sự kiện? | `Duration.between(startInstant, endInstant).toHours()` |
| Một tháng tính ra bao nhiêu giây? | **Không có một hằng chung**; cần ngày bắt đầu và zone/quy tắc |
| Cần đo timeout đúng 24 giờ | `Duration.ofHours(24)` và trục Instant |

**Tránh:** `Duration.between(LocalDateTime, LocalDateTime)` có thể cho khoảng trên **đồng hồ cục bộ** mà không phản ánh việc đổi offset. Nếu muốn đo elapsed time thật, hãy xác định mỗi thời điểm bằng `ZonedDateTime`/`Instant` trước.

### 7.4. End-exclusive và dấu của khoảng

`Period.between` và `ChronoUnit.DAYS.between` dùng mốc đầu **bao gồm**, mốc cuối **không bao gồm** cho ý nghĩa chênh lệch thời gian. Nếu bạn tính “số ngày có mặt trong phòng từ ngày A **đến hết** ngày B”, phép đếm có thể cần cộng thêm một đơn vị theo định nghĩa domain; đừng tự động cộng 1 trong mọi bài toán vì “đếm ngày” khác với “chênh lệch giữa hai mốc”.

Khi end trước start, kết quả có thể mang dấu âm. Đừng ép thành trị tuyệt đối nếu cần biết thứ tự thời gian. Với xử lý thời gian từ hệ thống thực, nên kiểm tra `end.isBefore(start)` và chọn chính sách có chấp nhận khoảng âm không.

## 8. Chuyển giờ DST: Cần cả local time và trục thời gian thực

Múi giờ như `Europe/Berlin` có thể đổi offset theo quy tắc lịch sử và pháp luật. Dữ liệu cho năm 2024:

- **Spring forward:** ngày **31/03/2024**, đồng hồ nhảy từ `02:00 +01:00` lên `03:00 +02:00`. Dải local 02:00–02:59 không tồn tại (gap).
- **Fall back:** ngày **27/10/2024**, đồng hồ lùi từ `03:00 +02:00` về `02:00 +01:00`. Dải 02:00–02:59 xảy ra hai lần (overlap).

Một `LocalDateTime` **không lưu ZoneId/offset**, vì vậy ngày–giờ này không luôn xác định đúng một `Instant`. `ZonedDateTime` có zone và offset đã được giải quyết.

### 8.1. Vì sao một ngày lịch có thể dài 23 hoặc 25 giờ?

Xét `2024-03-30T12:00` tại Berlin:

- `start.plus(Period.ofDays(1))` → **2024-03-31T12:00+02:00** (giữ 12:00 của **ngày kế**).
- `start.plus(Duration.ofDays(1))` → **2024-03-31T13:00+02:00** (cộng **đúng 24 giờ** trên Instant timeline).
- Chênh lệch thực giữa start và kết quả `Period.ofDays(1)` là **23 giờ**.

Xét `2024-10-26T12:00`:

- `plus(Period.ofDays(1))` → **2024-10-27T12:00+01:00** (một ngày lịch, **25 giờ** thực).
- `plus(Duration.ofDays(1))` → **2024-10-27T11:00+01:00** (24 giờ thực, đồng hồ địa phương sớm hơn một giờ).

**Không đồng nhất** “sau một ngày lịch” với “sau 86.400 giây”. Tương tự `ZonedDateTime.plusDays(1)` là thao tác theo local timeline, còn `plusHours(24)` là thao tác theo instant timeline.

### 8.2. Đừng dự đoán số giờ từ hai LocalDateTime

`Duration.between(start.toLocalDateTime(), end.toLocalDateTime())` so hai trường local, nên có thể cho **24 giờ** giữa hai mốc 12:00 cách nhau một ngày trên lịch, dù thực tế chỉ **23 giờ** qua spring DST. Dùng:

```java
long elapsedHours = Duration.between(
        start.toInstant(),
        end.toInstant()
).toHours();
```

Đây là đoạn trong phương thức, với `start/end` đã là `ZonedDateTime` hợp lệ. Khi yêu cầu đo thời gian đã trôi qua, làm việc trên `Instant` ngăn nhầm lẫn giờ cục bộ.

## 9. Chương trình hoàn chỉnh: `Period` và `Duration` qua spring/fall DST

Tạo file **`DstPeriodDurationDemo.java`**:

```java
import java.time.Duration;
import java.time.Period;
import java.time.ZoneId;
import java.time.ZonedDateTime;

public class DstPeriodDurationDemo {
    public static void main(String[] args) {
        ZoneId berlin = ZoneId.of("Europe/Berlin");

        ZonedDateTime spring = ZonedDateTime.of(
                2024, 3, 30, 12, 0, 0, 0, berlin);
        ZonedDateTime springCalendar =
                spring.plus(Period.ofDays(1));
        ZonedDateTime springElapsed =
                spring.plus(Duration.ofDays(1));

        System.out.println("Spring start: " + spring);
        System.out.println("Spring + Period: "
                + springCalendar);
        System.out.println("Spring + Duration: "
                + springElapsed);
        System.out.println("Spring elapsed hours: "
                + Duration.between(
                        spring.toInstant(),
                        springCalendar.toInstant()
                ).toHours());

        ZonedDateTime fall = ZonedDateTime.of(
                2024, 10, 26, 12, 0, 0, 0, berlin);
        ZonedDateTime fallCalendar =
                fall.plus(Period.ofDays(1));
        ZonedDateTime fallElapsed =
                fall.plus(Duration.ofDays(1));

        System.out.println("Fall start: " + fall);
        System.out.println("Fall + Period: " + fallCalendar);
        System.out.println("Fall + Duration: " + fallElapsed);
        System.out.println("Fall elapsed hours: "
                + Duration.between(
                        fall.toInstant(),
                        fallCalendar.toInstant()
                ).toHours());
        System.out.println("Duration one day hours: "
                + Duration.ofDays(1).toHours());
    }
}
```

Chạy:

```bash
javac --release 17 DstPeriodDurationDemo.java
java DstPeriodDurationDemo
```

**Stdout cho dữ liệu chuyển giờ Berlin năm 2024:**

```text
Spring start: 2024-03-30T12:00+01:00[Europe/Berlin]
Spring + Period: 2024-03-31T12:00+02:00[Europe/Berlin]
Spring + Duration: 2024-03-31T13:00+02:00[Europe/Berlin]
Spring elapsed hours: 23
Fall start: 2024-10-26T12:00+02:00[Europe/Berlin]
Fall + Period: 2024-10-27T12:00+01:00[Europe/Berlin]
Fall + Duration: 2024-10-27T11:00+01:00[Europe/Berlin]
Fall elapsed hours: 25
Duration one day hours: 24
```

**Bài học:** `Period.ofDays(1)` cố duy trì 12:00 trên lịch địa phương; `Duration.ofDays(1)` cộng đúng 24 giờ thực. Đây là hai phép tính **đều đúng theo hợp đồng khác nhau**. Test phải biết yêu cầu nghiệp vụ là lịch hay elapsed time trước khi viết expected.

Nếu lịch tổ chức yêu cầu “mỗi ngày lúc 12:00 tại Berlin”, thường chọn phép dựa trên lịch/zone. Nếu timeout bắt đầu từ một Instant và kết thúc sau 24 giờ, chọn Duration/Instant. Đừng dựa vào kết quả test chạy ở timezone mặc định; khai báo `ZoneId.of("Europe/Berlin")` rõ ràng.

## 10. Local time không tồn tại hoặc không duy nhất: Gap và overlap

Khi chuyển từ `LocalDateTime` sang `ZonedDateTime`, có ba trạng thái:

| Số offset hợp lệ trong `ZoneRules` | Trạng thái | Hệ quả |
| --- | --- | --- |
| **1** | Normal | Local time ứng với một instant |
| **0** | Gap | Local time không hề xảy ra |
| **2** | Overlap | Local time xảy ra hai lần, ứng với hai instants |

Ví dụ:

```java
ZoneId berlin = ZoneId.of("Europe/Berlin");
ZoneRules rules = berlin.getRules();

LocalDateTime gap = LocalDateTime.of(2024, 3, 31, 2, 30);
LocalDateTime overlap = LocalDateTime.of(2024, 10, 27, 2, 30);

List<ZoneOffset> a = rules.getValidOffsets(gap); // []
List<ZoneOffset> b = rules.getValidOffsets(overlap);
// [+02:00, +01:00]
```

Đây là **đoạn trong phương thức**, với import `java.time.`, `java.time.zone.ZoneRules` và `java.util.List`. Khi test, phải kiểm tra **số offset hợp lệ**, không chỉ việc `atZone` có trả kết quả hay không.

### 10.1. Gap: `atZone` tự điều chỉnh giờ

`LocalDateTime.of(2024,3,31,2,30).atZone(berlin)` trả:

```text
2024-03-31T03:30+02:00[Europe/Berlin]
```

Dù 02:30 không tồn tại, Java mặc định **dịch nó lên đúng độ dài gap (một giờ)**. Hành vi này khác với:

- **Reject:** từ chối giờ người dùng nhập vì không tồn tại.
- **Next valid:** chọn đầu khoảng hợp lệ kế tiếp, ở đây **03:00**.
- **Shift forward by gap:** chọn **03:30**.

Chính sách nào đúng tùy lịch đặt hẹn/nhắc việc. Nếu dùng `ZonedDateTime.ofStrict(local, offset, zone)` với gap, Java **ném `DateTimeException`** do offset đã chọn không hợp lệ. Không dùng `atZone` như một phương pháp validation strict.

### 10.2. Overlap: Hai lần 02:30 là hai instants

`2024-10-27T02:30` tại Berlin có offset `+02:00` và `+01:00`. Theo mặc định của `LocalDateTime.atZone`, Java chọn offset **earlier**:

```text
Lần đầu: 2024-10-27T02:30+02:00[Europe/Berlin]
Instant:  2024-10-27T00:30:00Z

Lần sau: 2024-10-27T02:30+01:00[Europe/Berlin]
Instant:  2024-10-27T01:30:00Z
```

Nếu muốn lần sau, dùng `withLaterOffsetAtOverlap()` hoặc chọn offset hợp lệ qua `ZonedDateTime.ofStrict`.

**Ngộ nhận quan trọng:** “Hai ZonedDateTime có cùng local date-time thì cùng thời điểm.” Sai khi offset khác nhau. Khi so **thời điểm thực**, so `toInstant()`; không dùng chỉ `toLocalDateTime()` để xác định sự kiện đã diễn ra.

### 10.3. Dữ liệu múi giờ do Java cung cấp có thể thay đổi

Các chuyển đổi Berlin năm 2024 ở đây là **lịch sử**; lịch tương lai có thể bị quốc gia thay đổi và được cập nhật trong tzdb. Không hard-code rằng mọi DST gap chỉ một giờ; có vùng có thay đổi offset nửa giờ hoặc bỏ qua hẳn một ngày. Với ứng dụng đặt lịch tương lai, hãy lưu `ZoneId` vùng và quy tắc xử lý gap/overlap; khi tzdb được cập nhật, phải xác định có tái tính Instant của lịch tương lai không.

## 11. Chương trình Java 17+: Kiểm tra gap, overlap và offset

Tạo file **`DstGapOverlapDemo.java`**:

```java
import java.time.DateTimeException;
import java.time.LocalDateTime;
import java.time.ZoneId;
import java.time.ZoneOffset;
import java.time.ZonedDateTime;
import java.time.zone.ZoneRules;
import java.util.List;

public class DstGapOverlapDemo {
    public static void main(String[] args) {
        ZoneId berlin = ZoneId.of("Europe/Berlin");
        ZoneRules rules = berlin.getRules();
        LocalDateTime gap = LocalDateTime.of(
                2024, 3, 31, 2, 30);
        LocalDateTime overlap = LocalDateTime.of(
                2024, 10, 27, 2, 30);

        List<ZoneOffset> gapOffsets =
                rules.getValidOffsets(gap);
        List<ZoneOffset> overlapOffsets =
                rules.getValidOffsets(overlap);

        System.out.println("Gap offsets: " + gapOffsets);
        System.out.println("Gap atZone: "
                + gap.atZone(berlin));
        System.out.println("Overlap offsets: "
                + overlapOffsets);

        ZonedDateTime first = overlap.atZone(berlin);
        ZonedDateTime second =
                first.withLaterOffsetAtOverlap();

        System.out.println("First: " + first);
        System.out.println("Second: " + second);
        System.out.println("First instant: "
                + first.toInstant());
        System.out.println("Second instant: "
                + second.toInstant());

        boolean rejectedGap = false;
        try {
            ZonedDateTime.ofStrict(
                    gap, ZoneOffset.ofHours(1), berlin);
        } catch (DateTimeException ex) {
            rejectedGap = true;
        }
        System.out.println("Strict gap rejected: "
                + rejectedGap);
    }
}
```

Chạy:

```bash
javac --release 17 DstGapOverlapDemo.java
java DstGapOverlapDemo
```

**Stdout:**

```text
Gap offsets: []
Gap atZone: 2024-03-31T03:30+02:00[Europe/Berlin]
Overlap offsets: [+02:00, +01:00]
First: 2024-10-27T02:30+02:00[Europe/Berlin]
Second: 2024-10-27T02:30+01:00[Europe/Berlin]
First instant: 2024-10-27T00:30:00Z
Second instant: 2024-10-27T01:30:00Z
Strict gap rejected: true
```

**Giải thích:** Với gap, `getValidOffsets` rỗng và `atZone` dịch lên 03:30. Với overlap, `getValidOffsets` có hai phần tử; hai cách giải quyết có Instant khác nhau đúng một giờ. `ofStrict` được dùng để xác nhận cặp local/offset/zone theo quy tắc vùng, không âm thầm dịch giờ.

Nếu cần chọn **03:00** là đầu thời gian hợp lệ sau gap, dùng `rules.getTransition(gap).getDateTimeAfter()` (sau khi xác minh đây là gap và transition khác null), rồi tạo `ZonedDateTime` cho local mới. Không lấy `atZone` làm đại diện cho mọi chính sách.

## 12. Chuyển giờ ngay đầu ngày: atStartOfDay có nghĩa “giờ hợp lệ sớm nhất”

`LocalDate.atStartOfDay(ZoneId)` được thiết kế trả về **thời gian sớm nhất hợp lệ** trong zone cho ngày đó. Nó **không bảo đảm trả 00:00 của chính ngày input** nếu vùng có chuyển đổi múi giờ khiến nửa đêm không tồn tại hoặc một ngày lịch bị bỏ qua.

Ví dụ lịch sử ở `Pacific/Apia`: vùng này đã bỏ qua ngày địa phương **2011-12-30** khi đổi múi giờ, nên:

```java
LocalDate requested = LocalDate.of(2011, 12, 30);
ZonedDateTime resolved = requested.atStartOfDay(
        ZoneId.of("Pacific/Apia"));
```

Đây là đoạn trong phương thức; với tzdb hỗ trợ chuyển đổi lịch sử này, kết quả là:

```text
2011-12-31T00:00+14:00[Pacific/Apia]
```

**Tại sao quan trọng?** Nếu dữ liệu người dùng yêu cầu **một ngày riêng biệt** theo lịch địa phương, đừng mặc định `atStartOfDay(zone)` luôn nằm trong ngày đó. Với lịch đặt chỗ và ngày giao hàng, phải có lựa chọn domain khi ngày bị bỏ qua.

Đây là một ca biên hiếm nhưng hữu ích để chứng minh **không thể suy luận timezone bằng cách cộng 24 giờ hoặc giả định mọi local date luôn có midnight**. Nó không có nghĩa ngày nay Samoa vẫn bỏ qua ngày 30/12 mỗi năm.

## 13. Cách thiết kế lịch cuối tháng, lịch lặp và timeout

Một số yêu cầu trông tương tự nhưng cách tính khác nhau:

### 13.1. “Tạo hóa đơn cuối mỗi tháng”

Chọn một **kỳ gốc** `YearMonth`, và cho mỗi `i`:

```java
LocalDate dueDate = baseMonth
        .plusMonths(i)
        .atEndOfMonth();
```

Đây là đoạn trong phương thức với `baseMonth` là `YearMonth` và `i` là số tháng tính từ kỳ gốc. **Không** chạy `current = current.plusMonths(1)` từ ngày cuối tháng trước vì sẽ drift sau tháng 2.

### 13.2. “Hết hạn sau một tháng kể từ ngày ký”

`start.plusMonths(1)` là quy tắc lịch trực tiếp thường thích hợp nếu hợp đồng cho phép **điều chỉnh ngày không tồn tại**. Nhưng phải chốt rõ cách tính “hết hạn” theo ngày bắt đầu/kết thúc có bao gồm ngày đầu/ cuối không, và thời điểm nào trong ngày là mốc cutoff.

### 13.3. “Một sự kiện lặp hằng ngày lúc 09:00 ở địa điểm cụ thể”

Giữ **local recurrence + ZoneId vùng**, chuyển sang ZonedDateTime cho từng ngày theo chính sách gap/overlap. `Duration.ofDays(1)` từ một Instant sẽ giữ khoảng cách 24 giờ nhưng **không bảo đảm 09:00 địa phương** sau đợt DST.

### 13.4. “Token hết hạn đúng 24 giờ sau khi phát hành”

Chọn `Instant issuedAt` và `issuedAt.plus(Duration.ofHours(24))`. Không dùng `Period.ofDays(1)` và timezone của máy nếu yêu cầu là 86.400 giây chính xác.

### 13.5. “Khoảng cách giữa hai giao dịch đã xảy ra”

Chọn `Duration.between(startInstant, endInstant)`, không lấy số giờ trên mặt đồng hồ. Trong overlap, cùng local 02:30 vẫn có thể có hai instants cách nhau một giờ.

### 13.6. “Ngày cuối tháng tại một vùng đang bị chuyển giờ”

Có thể tính `YearMonth.atEndOfMonth()` để lấy **ngày**, rồi dùng `LocalDate.atTime(...)` kết hợp `ZoneRules` để giải quyết **giờ**. Không giả định `LocalTime.MAX` hay 23:59:59 luôn tồn tại ở mọi vùng/ngày khi timezone rules có transition; với khoảng thời gian sử dụng DB, cách mô hình thường rõ hơn là **[startOfDay, startOfNextDay)** được giải quyết theo zone, nhưng phải kiểm tra trường hợp ngày bị bỏ qua.

## 14. Test một khoảng ngày như [start, end) thay vì dùng 23:59:59

Với dữ liệu có timestamp, thiết kế khoảng **nửa mở** là lựa chọn thực dụng:

```text
[startInclusive, endExclusive)
```

Ví dụ lấy toàn bộ giao dịch của ngày 31/03/2024 tại Berlin:

```java
ZoneId zone = ZoneId.of("Europe/Berlin");
LocalDate day = LocalDate.of(2024, 3, 31);

Instant start = day.atStartOfDay(zone).toInstant();
Instant end = day.plusDays(1)
        .atStartOfDay(zone)
        .toInstant();
```

Đây là đoạn trong phương thức với import `LocalDate`, `ZoneId`, `Instant`. Vì hôm đó có spring DST, khoảng `[start,end)` **dài 23 giờ thực**, không phải 24 giờ, nhưng vẫn khớp ranh giới của **ngày lịch địa phương** theo zone.

**Đừng tạo end bằng `start.plus(Duration.ofDays(1))`** khi mục tiêu là toàn bộ *ngày địa phương* qua DST. Cách đó sẽ kéo ranh giới sang một giờ của ngày kế tiếp hoặc bỏ sót một giờ tùy transition. Với ngày bị bỏ qua như `Pacific/Apia` năm 2011, cần xử lý trường hợp khoảng có thể rỗng và hiểu đúng ý nghĩa yêu cầu.

Mẫu query khoảng nửa mở cũng tránh các giả định về độ chính xác nano/millisecond ở “23:59:59.999…”, và dễ dùng hơn với chỉ mục timestamp:

```text
timestamp >= startInstant
AND timestamp < endInstant
```

Đây là **mã truy vấn dạng minh họa**, không phải Java độc lập hay cú pháp SQL hoàn chỉnh nếu thiếu tên bảng/parameter binding. Nó diễn tả rõ ranh giới dữ liệu.

## 15. Test không phụ thuộc giờ thực và timezone mặc định

**Không nên:** trong unit test, lấy `LocalDate.now()` rồi mong một output cố định. Ngày hiện tại phụ thuộc `Clock` và zone mặc định của hệ thống. Tương tự, dùng `ZoneId.systemDefault()` rồi assert Berlin DST sẽ fail trên máy có timezone khác.

**Nên:**

```java
LocalDate fixedDate = LocalDate.of(2024, 2, 29);
ZoneId fixedZone = ZoneId.of("Europe/Berlin");
```

Đây là đoạn trong phương thức. Với logic thật cần “hôm nay” nhưng muốn dễ test, inject `Clock`:

```java
Clock fixedClock = Clock.fixed(
        Instant.parse("2024-03-30T11:00:00Z"),
        ZoneId.of("Europe/Berlin"));

LocalDate testToday = LocalDate.now(fixedClock);
```

Đây là đoạn trong phương thức với import `Clock`, `Instant`, `ZoneId`, `LocalDate`. Giờ này ứng với Berlin 12:00 ngày 30/03/2024; kết quả `testToday` là `2024-03-30`. Nhưng **test về DST phải kiểm tra cả zone rules và ngày chuyển đổi đã chọn**, không chỉ cố định Instant ở một giờ ngẫu nhiên.

Trong code sản phẩm, nếu phải chạy qua nhiều phiên bản tzdb, nên kiểm tra version môi trường hoặc thiết kế khả năng tái tính các lịch tương lai. Với mốc Berlin 2024 đã diễn ra, kết quả tại những bản tzdb hiện hành là điểm tựa tốt cho bài tập.

## 16. Bộ kiểm thử tự động Java 17+: Cuối tháng, năm nhuận và DST

Tạo file **`DateTimeBoundaryChecks.java`**. Hàm `check` ném `AssertionError` trực tiếp nên không phụ thuộc việc JVM có bật `-ea` hay không:

```java
import java.time.DateTimeException;
import java.time.Duration;
import java.time.Instant;
import java.time.LocalDate;
import java.time.LocalDateTime;
import java.time.MonthDay;
import java.time.Period;
import java.time.Year;
import java.time.YearMonth;
import java.time.ZoneId;
import java.time.ZonedDateTime;
import java.time.zone.ZoneRules;
import java.time.temporal.ChronoUnit;

public class DateTimeBoundaryChecks {
    static void check(boolean condition, String message) {
        if (!condition) {
            throw new AssertionError(message);
        }
    }

    public static void main(String[] args) {
        LocalDate jan31 = LocalDate.of(2024, 1, 31);

        check(jan31.plusMonths(1)
                .equals(LocalDate.of(2024, 2, 29)),
                "Jan31 -> Feb29");
        check(jan31.plusMonths(2)
                .equals(LocalDate.of(2024, 3, 31)),
                "Jan31 -> Mar31");
        check(jan31.plusMonths(1).plusMonths(1)
                .equals(LocalDate.of(2024, 3, 29)),
                "chained month rollover");
        check(YearMonth.of(2024, 2)
                .atEndOfMonth()
                .equals(LocalDate.of(2024, 2, 29)),
                "end of leap February");
        System.out.println("Month ends: PASS");

        check(Year.isLeap(2024) && !Year.isLeap(2023),
                "ordinary leap years");
        check(Year.isLeap(2000) && !Year.isLeap(1900),
                "century leap years");
        check(!MonthDay.of(2, 29).isValidYear(2023),
                "invalid anniversary year");

        boolean invalidDayRejected = false;
        try {
            LocalDate.of(2023, 2, 29);
        } catch (DateTimeException ex) {
            invalidDayRejected = true;
        }
        check(invalidDayRejected, "invalid day accepted");
        System.out.println("Leap years: PASS");

        LocalDate feb29 = LocalDate.of(2024, 2, 29);
        check(Period.between(jan31, feb29)
                .equals(Period.ofDays(29)),
                "Period.between end-of-month");
        check(ChronoUnit.DAYS.between(jan31, feb29)
                == 29, "calendar day distance");
        System.out.println("Period vs days: PASS");

        ZoneId berlin = ZoneId.of("Europe/Berlin");
        ZonedDateTime spring = ZonedDateTime.of(
                2024, 3, 30, 12, 0, 0, 0, berlin);
        ZonedDateTime springTomorrow =
                spring.plus(Period.ofDays(1));
        check(Duration.between(
                spring.toInstant(),
                springTomorrow.toInstant()
        ).toHours() == 23, "spring elapsed hours");
        check(spring.plus(Duration.ofDays(1))
                .getHour() == 13, "spring + exact 24h");

        ZonedDateTime fall = ZonedDateTime.of(
                2024, 10, 26, 12, 0, 0, 0, berlin);
        ZonedDateTime fallTomorrow =
                fall.plus(Period.ofDays(1));
        check(Duration.between(
                fall.toInstant(),
                fallTomorrow.toInstant()
        ).toHours() == 25, "fall elapsed hours");
        check(fall.plus(Duration.ofDays(1))
                .getHour() == 11, "fall + exact 24h");
        System.out.println("23h/25h DST: PASS");

        ZoneRules rules = berlin.getRules();
        LocalDateTime gap = LocalDateTime.of(
                2024, 3, 31, 2, 30);
        LocalDateTime overlap = LocalDateTime.of(
                2024, 10, 27, 2, 30);

        check(rules.getValidOffsets(gap).isEmpty(),
                "gap not recognized");
        check(rules.getValidOffsets(overlap).size() == 2,
                "overlap not recognized");
        check(gap.atZone(berlin).getHour() == 3,
                "gap not shifted");
        ZonedDateTime first = overlap.atZone(berlin);
        ZonedDateTime second =
                first.withLaterOffsetAtOverlap();
        check(Duration.between(
                first.toInstant(),
                second.toInstant()
        ).toHours() == 1, "overlap instants differ");
        System.out.println("Gap/overlap: PASS");

        LocalDate day = LocalDate.of(2024, 3, 31);
        Instant start = day.atStartOfDay(berlin)
                .toInstant();
        Instant end = day.plusDays(1)
                .atStartOfDay(berlin).toInstant();
        check(Duration.between(start, end).toHours()
                == 23, "spring day bounds");
        System.out.println("Local day bounds: PASS");

        System.out.println("All checks: PASS");
    }
}
```

Chạy:

```bash
javac --release 17 DateTimeBoundaryChecks.java
java DateTimeBoundaryChecks
```

**Stdout:**

```text
Month ends: PASS
Leap years: PASS
Period vs days: PASS
23h/25h DST: PASS
Gap/overlap: PASS
Local day bounds: PASS
All checks: PASS
```

Bộ kiểm thử chủ động bao gồm **cuối tháng 31 ngày**, **năm nhuận thế kỷ**, **P29D thay vì P1M**, **ngày DST 23/25 giờ**, **gap/overlap** và **ranh giới ngày địa phương**. Nó không cố đo tốc độ hay dựa vào lịch thực tại ngày chạy.

**Giới hạn:** Bộ ca cố định không chứng minh mọi input lịch đều đúng. Cần bổ sung test cho từng zone, phiên bản tzdb, yêu cầu lịch lặp, quy tắc ngày lễ và chính sách xử lý dữ liệu người dùng mà sản phẩm thật sự hỗ trợ.

## 17. Chiến lược kiểm thử mở rộng: Properties và bảng trường hợp

Ngoài test ví dụ, hãy thiết kế **bất biến (invariants)** và thử trên danh sách dữ liệu:

### 17.1. Kiểm tra đúng ngày cuối tháng

Với nhiều năm và đủ 12 tháng, `YearMonth.atEndOfMonth()` phải:

- Có `getDayOfMonth() == yearMonth.lengthOfMonth()`.
- Có `getMonthValue() == yearMonth.getMonthValue()`.
- Có `getYear() == yearMonth.getYear()`.
- Cộng một ngày sẽ vào **ngày 1 tháng tiếp theo** nếu còn trong miền hỗ trợ.

Test các năm `1899, 1900, 1999, 2000, 2023, 2024, 2100, 2400` để bao phủ cả năm thế kỷ nhuận/không nhuận. Tránh thử tự động qua `YearMonth.MAX` rồi cộng ngày vì vượt phạm vi có thể ném exception.

### 17.2. Kiểm tra round-trip nhưng không giả định quá mạnh

Với ngày ở giữa tháng không bị điều chỉnh, `plusMonths(1).minusMonths(1)` thường khôi phục ngày; với ngày 29/30/31 ở cuối tháng, **không** bảo đảm. Test phải phản ánh giới hạn đó, không biến một giả định sai thành property chung.

Tương tự `plusYears(1).minusYears(1)` không khôi phục 29/02 khi bước trung gian không có ngày nhuận. Nếu domain cần giữ “ngày cuối tháng” qua mỗi năm, nên lưu chính **quy tắc end-of-month**, không cố lấy lại ngày bị mất.

### 17.3. Kiểm tra DST qua cả hai chiều

Với spring và autumn, test:

- `getValidOffsets` có 0/1/2 kết quả đúng với normal/gap/overlap.
- `atZone` dịch gap theo hợp đồng; có thể dùng `ofStrict` để từ chối giờ không tồn tại.
- Ở overlap, hai valid offsets tạo hai `Instant` khác nhau; policy cho phép chọn sớm/muộn/đòi lựa chọn.
- `Duration.between(instants)` phản ánh **thời lượng thực**.
- `Period.ofDays(1)` và `Duration.ofDays(1)` có thể ra khác local time.
- Bắt đầu/kết thúc ngày theo zone không luôn cách nhau 24 giờ.
- Chuyển zone để hiển thị một event nên dùng `withZoneSameInstant`, không phải `withZoneSameLocal`.

### 17.4. Test không phụ thuộc clock mặc định

Dùng `Clock.fixed` hoặc `LocalDate.of` trong unit test; đưa `ZoneId` vào tham số. Không để test phụ thuộc `ZoneId.systemDefault()` và ngày chạy. Khi tạo dữ liệu thử ngẫu nhiên, dùng seed có thể tái hiện và bổ sung có chủ ý các trường hợp hiếm (29/02, 30/31, ngày đổi giờ).

### 17.5. Test ngoại lệ

- `LocalDate.of(2023,2,29)` phải bị từ chối.
- `MonthDay.of(2,30)` không hợp lệ (không có năm nào tháng 2 có ngày 30).
- `YearMonth.of(2024,13)` phải bị từ chối.
- Nếu `ZonedDateTime.ofStrict` nhận một offset không hợp lệ cho local/zone, phải bị từ chối.
- Nếu phép cộng vượt miền hỗ trợ của `LocalDate`/`Instant`, API có thể ném exception; không kỳ vọng wrap.
- Nếu một khoảng kết thúc trước lúc bắt đầu, cần kiểm tra domain cho phép/không cho phép thời lượng âm.

Đừng “chữa” dữ liệu không hợp lệ bằng cách âm thầm chọn ngày gần nhất trừ khi **quy tắc nghiệp vụ** cho phép.

## 18. Các lỗi phổ biến cần tránh

1. **Nhầm `Period.ofDays(1)` với `Duration.ofDays(1)`:** cái đầu theo ngày lịch, cái sau đúng 24 giờ.
2. **Dùng `Duration.ofDays(30)` như một tháng:** độ dài tháng có thể 28, 29, 30, 31 ngày.
3. **Dùng `Period.ofMonths(1).getDays()` để suy ra số ngày của tháng:** getDays là thành phần days, không phải tổng ngày.
4. **Tưởng `Period.normalized` đổi 30 ngày thành một tháng:** normalized chỉ chuẩn hóa phần năm/tháng.
5. **Tưởng `Jan31.plusMonths(1).plusMonths(1)` luôn bằng `Jan31.plusMonths(2)`:** điều chỉnh cuối tháng gây khác biệt.
6. **Cộng dồn từ ngày chốt kỳ trước để tạo lịch luôn cuối tháng:** ngày có thể bị drift về 28/29.
7. **Tưởng `April30.plusMonths(1)` tự sang May31:** nó giữ ngày 30 nếu hợp lệ.
8. **Nhầm `MonthDay.atYear` với `LocalDate.of` khi ngày 29/02 không hợp lệ:** một API điều chỉnh, một API từ chối.
9. **Nghĩ năm chia hết 100 chắc chắn nhuận:** 1900 không nhuận, 2000 nhuận.
10. **Cộng một năm rồi trừ lại sẽ luôn về ngày ban đầu:** 29/02 có thể bị điều chỉnh thành 28/02.
11. **Dùng `Period.between` rồi tưởng có số giây cố định:** tháng/năm không có độ dài giây chung.
12. **Dùng `Duration.between(LocalDateTime, LocalDateTime)` để đo elapsed time qua DST:** local time không có offset.
13. **Dùng `Duration.between` với hai LocalDate rồi kỳ vọng đo ngày lịch:** chọn `ChronoUnit.DAYS.between`.
14. **Lấy `ZonedDateTime.plusDays(1)` là đúng 24 giờ:** có thể là 23/25 qua DST.
15. **Lấy `Instant.plus(Duration.ofDays(1))` làm lịch “cùng giờ địa phương ngày mai”:** có thể chênh một giờ.
16. **Nghĩ `LocalDateTime.atZone` ném lỗi khi gap:** mặc định dịch giờ lên.
17. **Nghĩ overlap chỉ có một instant vì đồng hồ hiển thị cùng 02:30:** có hai offset.
18. **Dùng `ZoneRules.getOffset(local)` để kiểm tra thời gian duy nhất:** hãy dùng `getValidOffsets(local)`.
19. **Hard-code gap một giờ:** độ dài transition phụ thuộc zone và thời điểm.
20. **Chỉ lưu giờ local mà không có zone/offset cho audit:** không phân biệt được hai lần xuất hiện của cùng giờ trong overlap.
21. **Lấy 23:59:59 làm điểm cuối tất cả giao dịch ngày:** mất dữ liệu có phần giây chính xác hơn; dùng khoảng nửa mở theo start-of-next-day.
22. **Dùng `atStartOfDay(zone)` và khẳng định kết quả nhất thiết là midnight của ngày đã nhập:** giờ đầu ngày có thể không tồn tại.
23. **Đọc timezone mặc định của server vào unit test có expected cố định:** test sẽ không portable.
24. **Thay `ZoneId` vùng bằng một `ZoneOffset` cố định cho lịch lặp:** không mô tả quy tắc chuyển giờ tương lai.
25. **Chỉ kiểm tra hai kết quả tuần tự/song song hay hai đường tính bằng nhau:** cả hai có thể cùng sai nếu expected và domain chưa xác định.
26. **Giả định mọi quy tắc chuyển giờ lịch sử vẫn đúng mãi:** tzdb có thể thay đổi khi luật quốc gia thay đổi.
27. **Dùng `LocalDateTime.now()` để sinh case chuyển giờ:** không chủ động kiểm thử đúng gap/overlap cần thiết.
28. **Biến exception date-invalid thành ngày tự sửa mà không báo người dùng:** có thể mất ý định ban đầu.
29. **Coi mọi ngày theo lịch địa phương đều dài 86.400 giây:** sai tại chuyển giờ và ngày bị bỏ qua.
30. **Nhầm ngày lịch và thời điểm UTC khi lưu DB/query:** cần xác định rõ boundary bằng zone.

## 19. Checklist trước khi hoàn thành tính năng thời gian

Hãy trả lời lần lượt:

1. Domain cần một **ngày lịch**, một **kỳ tháng**, hay một **thời lượng đúng số giây**?
2. Nếu cộng một tháng vào ngày 29/30/31, chính sách điều chỉnh cuối tháng là gì?
3. Nếu lịch “luôn cuối tháng”, đã dùng `YearMonth.atEndOfMonth()` hoặc một rule tương đương, thay vì cộng dồn từ ngày trước?
4. Nếu có sinh nhật/kỷ niệm 29/02, xử lý năm không nhuận ra sao?
5. Bộ test đã có 1900, 2000, 2023, 2024 để kiểm tra quy tắc nhuận?
6. Có dùng `Period.between` như thể đó là một Duration cố định không?
7. Khi đo elapsed time, các thời điểm đã được chuyển thành `Instant` chưa?
8. Đã kiểm tra `Duration.ofDays(1)` và `Period.ofDays(1)` trên ngày DST 23/25 giờ?
9. Với local time nhập từ người dùng, có xét gap/overlap và chính sách của sản phẩm?
10. Có lưu `ZoneId` vùng cho lịch hẹn/lịch lặp thay vì chỉ offset hiện tại?
11. Có xác định rõ khoảng ngày `[start,end)` để tránh bug 23:59:59?
12. Test có ngày cố định, timezone tường minh, không đọc máy chủ mặc định?
13. Nếu tzdb cập nhật, lịch đặt trước trong tương lai có được tính lại và thông báo thích hợp?
14. Các giá trị trả về được so bằng `equals`/`toInstant()` theo đúng ý nghĩa calendar/instant?
15. Đã test exception cho ngày không hợp lệ và xử lý các giới hạn miền dữ liệu?

## 20. Câu hỏi ôn tập

1. Tại sao `Period.ofDays(1)` và `Duration.ofDays(1)` có thể cho hai giờ khác nhau khi áp vào `ZonedDateTime`?
2. `2024-01-31.plusMonths(1)` ra ngày nào? `plusMonths(1).plusMonths(1)` ra gì? Vì sao `plusMonths(2)` khác?
3. Nếu muốn tạo hóa đơn vào **ngày cuối của mọi tháng**, nên lấy ngày từ `YearMonth` hay cộng vào `LocalDate` kỳ trước?
4. `Year.isLeap(1900)` và `Year.isLeap(2000)` lần lượt là gì?
5. `LocalDate.of(2023,2,29)` và `MonthDay.of(2,29).atYear(2023)` hành xử giống nhau không?
6. `Period.between(2024-01-31,2024-02-29)` trả gì? Có phải P1M không?
7. `Duration.between` của hai `LocalDateTime` cách nhau một ngày địa phương có đo được 23/25 giờ qua DST không?
8. Với Berlin spring 2024, `ZonedDateTime.plus(Period.ofDays(1))` cách Instant gốc bao nhiêu giờ khi bắt đầu 30/03 12:00?
9. Với Berlin autumn 2024, cùng phép tính cách Instant gốc bao nhiêu giờ?
10. `LocalDateTime.of(2024,3,31,2,30).atZone(Berlin)` chọn giờ nào? Tại sao?
11. Tại sao local `2024-10-27T02:30` ở Berlin tương ứng hai Instants?
12. Khi lọc dữ liệu cho toàn bộ ngày 31/03/2024 tại Berlin, vì sao [startOfDay, startOfNextDay) tốt hơn “end = start + 24h”?
13. `LocalDate.of(2011,12,30).atStartOfDay(Pacific/Apia)` có đảm bảo vẫn nằm trong ngày 30 không?
14. Dữ liệu cho lịch lặp 09:00 ở một thành phố nên giữ `ZoneId` vùng hay chỉ một offset?
15. Để xác minh dữ liệu đầu vào sai như 2023-02-29, nên mong `LocalDate.of` ném lỗi hay tự điều chỉnh?

**Đáp án gợi ý:** (1) Period đi theo lịch địa phương còn Duration là chính xác 24 giờ. (2) 2024-02-29; 2024-03-29; cộng trực tiếp hai tháng là 2024-03-31 do không mất ngày 31 ở bước giữa. (3) `YearMonth.atEndOfMonth`. (4) false và true. (5) Không: LocalDate.of ném lỗi, MonthDay.atYear điều chỉnh về 28/02. (6) P29D, không phải P1M. (7) Không phản ánh offset; phải dùng Instant. (8) 23 giờ. (9) 25 giờ. (10) 03:30 vì giờ 02:30 nằm trong gap và được dịch lên một giờ. (11) Có offset +02 và +01, tương ứng hai Instants khác nhau. (12) Ngày địa phương dài 23 giờ trong ví dụ; start + 24h lệch ranh giới. (13) Không; ngày đó bị bỏ qua, earliest valid time là 31/12. (14) ZoneId vùng để có quy tắc theo thời gian. (15) Ném `DateTimeException`.

**Kết luận:** Kiểm thử khoảng thời gian đúng phải kiểm tra **cả calendar semantics và elapsed-time semantics**, không chỉ các output ngày bình thường. Với **cuối tháng**, hãy thử phép cộng tháng có điều chỉnh và chống drift khi lập lịch định kỳ; với **năm nhuận**, kiểm tra 29/02, các năm thế kỷ và hành vi của create/adjust; với **chuyển giờ**, kiểm tra ngày 23/25 giờ, gap/overlap, offset/Instant, chính sách lịch và ranh giới ngày theo zone. `Period`, `Duration`, `LocalDate`, `YearMonth` và `ZonedDateTime` đều còn là API Java hiện hành — chọn theo ý nghĩa nghiệp vụ trước, rồi dùng expected độc lập và test biên để bảo vệ tính đúng đắn.

## Tài liệu chính thức Java — API hiện hành

- `Period` — khoảng theo năm/tháng/ngày, khác Duration qua DST: https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/time/Period.html
- `Duration` — khoảng theo giây/nanogiây, 1 day đúng 24 giờ: https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/time/Duration.html
- `LocalDate` — `plusMonths`, `plusYears`, `atStartOfDay(zone)` và phép tính theo lịch: https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/time/LocalDate.html
- `YearMonth` — `lengthOfMonth`, `atEndOfMonth` và tạo kỳ theo tháng: https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/time/YearMonth.html
- `Year` và `MonthDay` — tính nhuận, `isValidYear`, `atYear`: https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/time/Year.html và https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/time/MonthDay.html
- `ZonedDateTime` — thời gian theo vùng, cộng ngày/hours và xử lý DST: https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/time/ZonedDateTime.html
- `ZoneRules` — kiểm tra offset hợp lệ, gap và overlap: https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/time/zone/ZoneRules.html
- `Instant` và `ZoneId` — thời điểm thực và ID vùng: https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/time/Instant.html và https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/time/ZoneId.html
- `ChronoUnit` và `TemporalAdjusters` — tính ngày, tháng và điều chỉnh cuối tháng: https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/time/temporal/ChronoUnit.html và https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/time/temporal/TemporalAdjusters.html
