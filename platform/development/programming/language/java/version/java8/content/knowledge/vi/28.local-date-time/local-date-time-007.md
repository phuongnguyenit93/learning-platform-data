# with, plus, minus và đối tượng mới trong Java Local Date/Time

Trong `java.time` của Java 8, các lớp ngày giờ cục bộ như `LocalDate`, `LocalTime` và `LocalDateTime` là **đối tượng bất biến (immutable)**. Các phương thức `with(...)`, `plus(...)` và `minus(...)` **không chỉnh sửa đối tượng đang có**, mà trả về **một giá trị ngày giờ được điều chỉnh hoặc tính toán**. Để sử dụng giá trị mới, ta phải gán kết quả cho biến, trả nó từ hàm, truyền sang bước tiếp theo hoặc tiếp tục gọi phương thức trên kết quả.

~~~java
LocalDate original = LocalDate.of(2024, 2, 28);
LocalDate next = original.plusDays(1);

System.out.println(original); // 2024-02-28
System.out.println(next);     // 2024-02-29
~~~

Đoạn mã minh họa này cần `import java.time.LocalDate;` trong một lớp Java. `original` vẫn là ngày 28/2; `next` biểu diễn ngày 29/2 của năm nhuận 2024.

**Ba nhóm thao tác có ý nghĩa khác nhau:**

- `with(...)`: điều chỉnh **một trường hoặc theo một quy tắc lịch** (ví dụ đặt tháng thành 2, đặt giờ thành 9, tìm ngày cuối tháng).
- `plus(...)`: **cộng một lượng thời gian/lịch** (ví dụ cộng 7 ngày, 1 tháng, 90 phút).
- `minus(...)`: **trừ một lượng thời gian/lịch** (ví dụ lùi 2 tuần, 3 giờ).

Các API này **vẫn được hỗ trợ và áp dụng trong Java hiện đại**. Bài tập trung vào đúng chủ đề **Ngày giờ cục bộ**: `LocalDate`, `LocalTime`, `LocalDateTime`, `Period`, `Duration`, `ChronoUnit`, `ChronoField` và `TemporalAdjusters`. Ví dụ đầy đủ chỉ dùng API có từ Java 8, chạy được trên JDK 17+.

## 1. Mô hình tư duy: giá trị bất biến, biến tham chiếu có thể gán lại

Với một kiểu mutable như `StringBuilder`, phương thức có thể thay đổi nội dung trên chính đối tượng. Với `LocalDate`, `LocalTime` và `LocalDateTime`, các phép biến đổi không sửa trạng thái của đối tượng gốc:

~~~java
LocalDate start = LocalDate.of(2024, 1, 31);
start.plusDays(1); // Kết quả bị bỏ đi.

System.out.println(start); // VẪN 2024-01-31
~~~

Muốn chuyển biến `start` sang ngày tiếp theo:

~~~java
start = start.plusDays(1);
System.out.println(start); // 2024-02-01
~~~

Trong dòng gán trên, **reference của biến `start` đổi sang kết quả**, không phải đối tượng cũ bị sửa. Nếu nơi khác vẫn giữ reference đến giá trị ngày cũ, nơi đó tiếp tục nhìn thấy ngày cũ.

**Không nên diễn giải “trả đối tượng mới” thành “luôn có một instance khác về identity”.** Khi thay đổi không làm khác giá trị, API có thể trả lại chính instance cũ, ví dụ `date.plusDays(0)` hoặc `date.withYear(date.getYear())`. Hợp đồng quan trọng là **kết quả về mặt giá trị** và **đối tượng ban đầu không bị thay đổi**; không dựa vào `a == b` hoặc địa chỉ bộ nhớ.

### So sánh giá trị đúng cách

~~~java
LocalDate a = LocalDate.of(2024, 2, 29);
LocalDate b = LocalDate.parse("2024-02-29");

System.out.println(a.equals(b)); // true
~~~

Các lớp ngày giờ chuẩn thuộc nhóm **value-based classes**. Dùng `equals` để so sánh giá trị; dùng `isBefore` / `isAfter` khi cần quan hệ thời gian. Không lấy reference identity (`==`) làm quy tắc nghiệp vụ, cũng không đồng bộ bằng `synchronized(date)` trên đối tượng value-based.

## 2. Ba lớp cục bộ: cùng bất biến, nhưng phạm vi thời gian khác nhau

| Lớp | Chứa gì? | Phương thức tiêu biểu | Điều không có |
| --- | --- | --- | --- |
| `LocalDate` | Năm, tháng, ngày ISO | `withYear`, `withMonth`, `plusDays`, `minusMonths` | Giờ, phút, giây, zone, offset |
| `LocalTime` | Giờ, phút, giây, nano trong một ngày | `withHour`, `withMinute`, `plusMinutes`, `minusHours` | Ngày và múi giờ |
| `LocalDateTime` | `LocalDate` + `LocalTime` | `withDayOfMonth`, `withHour`, `plusDays`, `plusHours` | Zone, UTC offset |
| `Period` | Số năm/tháng/ngày theo lịch | `Period.ofMonths(1)` | Không phải một số giây cố định |
| `Duration` | Thời lượng theo giây/nanosecond | `Duration.ofMinutes(90)` | Không phải quy tắc thay tháng/ngày lịch |

**Local** ở đây có nghĩa **không gắn múi giờ**. `LocalDateTime.of(2024, 3, 1, 9, 0)` thể hiện 09:00 ngày 1/3, nhưng chưa nói 09:00 của Hà Nội, Paris hay UTC. Tính bất biến không tự giải quyết việc diễn giải múi giờ; khi cần một instant tuyệt đối, phải bổ sung `ZoneId`/`ZoneOffset` theo nghiệp vụ hoặc chọn kiểu `Instant`/`ZonedDateTime`.

### Khác nhau khi vượt qua nửa đêm

~~~java
LocalTime clockTime = LocalTime.of(23, 45);
System.out.println(clockTime.plusMinutes(30)); // 00:15

LocalDateTime atNight =
    LocalDateTime.of(2024, 2, 28, 23, 45);
System.out.println(atNight.plusMinutes(30)); // 2024-02-29T00:15
~~~

`LocalTime` quay vòng trong 24 giờ và **không có thông tin rằng ngày mới đã bắt đầu**. `LocalDateTime` gồm cả ngày nên mang việc vượt nửa đêm sang ngày kế tiếp. Cả hai vẫn giữ nguyên instance nguồn.

## 3. `with(...)`: đặt một trường hoặc điều chỉnh theo quy tắc

`with` mô tả kiểu thao tác “cho tôi ngày giờ **với trường X bằng giá trị Y**”, không phải “cộng thêm Y đơn vị”.

### 3.1. Các phương thức thuận tiện theo loại

~~~java
LocalDate date = LocalDate.of(2024, 5, 20);

LocalDate january = date.withMonth(1);
LocalDate first = date.withDayOfMonth(1);
LocalDate newYear = date.withYear(2025);

// date     = 2024-05-20
// january  = 2024-01-20
// first    = 2024-05-01
// newYear  = 2025-05-20
~~~

`withMonth(1)` dùng **tháng số 1 = January**, không phải “cộng một tháng”. `withDayOfMonth(1)` đặt ngày của tháng là 1; nó không tương đương `plusDays(1)`.

Với giờ:

~~~java
LocalTime time = LocalTime.of(16, 45, 30);

LocalTime opening = time.withHour(9);
LocalTime rounded = time.withMinute(0);

// opening = 09:45:30
// rounded = 16:00:30
~~~

Chú ý `withMinute(0)` **không tự xóa giây/nano**. Nếu cần “đầu giờ” tại `09:00:00`, có thể dùng chuỗi `withHour(9).withMinute(0).withSecond(0).withNano(0)` hoặc `truncatedTo(ChronoUnit.HOURS)` theo mục đích.

Với `LocalDateTime`, cùng một đối tượng có cả phần ngày và giờ:

~~~java
LocalDateTime meeting =
    LocalDateTime.of(2024, 5, 20, 16, 45);

LocalDateTime moved =
    meeting.withDayOfMonth(1).withHour(9);

// meeting = 2024-05-20T16:45
// moved   = 2024-05-01T09:45
~~~

### 3.2. Dạng tổng quát `with(TemporalField, long)`

Các kiểu java.time triển khai giao diện `Temporal` theo những phạm vi field hỗ trợ:

~~~java
LocalDate base = LocalDate.of(2024, 2, 15);

LocalDate first = base.with(ChronoField.DAY_OF_MONTH, 1);
// 2024-02-01

LocalDateTime dateTime =
    LocalDateTime.of(2024, 2, 15, 14, 20);

LocalDateTime morning =
    dateTime.with(ChronoField.HOUR_OF_DAY, 9);
// 2024-02-15T09:20
~~~

Đoạn này cần import `java.time.temporal.ChronoField` nếu đặt trong chương trình. `ChronoField.DAY_OF_MONTH` là **trường lịch**, không phải đơn vị cộng trừ. Viết `LocalDate.with(ChronoField.HOUR_OF_DAY, 9)` là không phù hợp vì `LocalDate` không có giờ, thường dẫn đến `UnsupportedTemporalTypeException`.

**Nên ưu tiên** `withDayOfMonth(1)` hoặc `withHour(9)` khi có phương thức rõ nghĩa. Dùng `with(ChronoField, value)` khi field cần được chọn tổng quát hoặc khi đang viết logic chung cho Temporal.

### 3.3. `with(TemporalAdjuster)`: chiến lược điều chỉnh lịch

`TemporalAdjusters` cung cấp nhiều quy tắc rất hữu ích:

~~~java
LocalDate date = LocalDate.of(2024, 2, 15);

LocalDate lastDay =
    date.with(TemporalAdjusters.lastDayOfMonth());
// 2024-02-29

LocalDate nextMonday =
    date.with(TemporalAdjusters.next(DayOfWeek.MONDAY));
// 2024-02-19
~~~

`lastDayOfMonth()` tìm ngày cuối tháng, có xét năm nhuận. `next(MONDAY)` luôn tìm một thứ Hai **sau** ngày hiện tại; `nextOrSame(MONDAY)` cho phép dùng chính ngày hiện tại nếu đã là thứ Hai. Tương tự có `firstDayOfMonth`, `lastDayOfYear`, `previous`, `previousOrSame`, `firstInMonth`.

Khi làm lịch công việc, `with(TemporalAdjusters.nextOrSame(DayOfWeek.MONDAY))` nói rõ “vào thứ Hai sắp tới hoặc hôm nay” hơn là tự tính số ngày bằng `DayOfWeek.getValue()` rồi sửa các trường thủ công.

**Giới hạn của adjuster tự viết:** `TemporalAdjuster` là interface cho phép triển khai tùy biến. Đừng suy rằng mọi lambda/implementation tùy biến đều thuần hoặc thread-safe; khi dùng trong nhiều thread, implementer phải tuân thủ hợp đồng, không sửa input và trả kết quả đúng loại.

## 4. `plus(...)`: cộng một lượng, có thể vượt ranh giới ngày/tháng/năm

### 4.1. `LocalDate`

Các phương thức quen thuộc:

~~~java
LocalDate date = LocalDate.of(2024, 2, 28);

LocalDate nextDay = date.plusDays(1);     // 2024-02-29
LocalDate nextWeek = date.plusWeeks(1);   // 2024-03-06
LocalDate nextMonth = date.plusMonths(1); // 2024-03-28
LocalDate nextYear = date.plusYears(1);   // 2025-02-28
~~~

`plusDays` tính tiến qua các ngày thực của lịch ISO, có tự xử lý số ngày trong tháng và năm nhuận. `plusWeeks(1)` tương đương cộng bảy ngày cho `LocalDate`. `plusMonths` và `plusYears` cộng theo **tháng/năm lịch**, nên có quy tắc đặc biệt khi ngày của tháng không hợp lệ trong kết quả.

### 4.2. `LocalTime`

~~~java
LocalTime time = LocalTime.of(23, 40);

LocalTime later = time.plusMinutes(30); // 00:10
LocalTime earlier = time.minusHours(2); // 21:40
~~~

`LocalTime` thực hiện toán giờ, phút, giây, nano và quay vòng sau `23:59:59...`. Nó không đưa ra thông tin “hôm qua/hôm sau”, vì thiếu ngày. Nếu cần thời điểm gồm ngày và giờ, dùng `LocalDateTime` hoặc kiểu có zone phù hợp.

### 4.3. `LocalDateTime`

~~~java
LocalDateTime late =
    LocalDateTime.of(2024, 2, 28, 23, 30);

LocalDateTime twoHoursLater = late.plusHours(2);
// 2024-02-29T01:30

LocalDateTime dayLater = late.plusDays(1);
// 2024-02-29T23:30

LocalDateTime monthLater = late.plusMonths(1);
// 2024-03-28T23:30
~~~

`LocalDateTime.plusHours(2)` chuyển cả phần ngày khi qua nửa đêm. Nhưng nó vẫn là **toán trên lịch/đồng hồ địa phương, không có múi giờ**: bản thân đối tượng không tự giải quyết DST hay quy tắc zone.

### 4.4. Dạng tổng quát `plus(long, TemporalUnit)`

~~~java
LocalDate start = LocalDate.of(2024, 2, 15);

LocalDate afterTwoWeeks =
    start.plus(2, ChronoUnit.WEEKS);
// 2024-02-29
~~~

`ChronoUnit` xác định **đơn vị lượng thời gian**, ví dụ `DAYS`, `WEEKS`, `MONTHS`, `YEARS`, `HOURS`, `MINUTES`. Chọn đơn vị đúng với kiểu:

- `LocalDate` hỗ trợ đơn vị ngày/lớn hơn như `DAYS`/`MONTHS`/`YEARS`, không hỗ trợ `HOURS`.
- `LocalTime` hỗ trợ đơn vị giờ/phút/giây/nano, không có số ngày lịch hay số tháng.
- `LocalDateTime` hỗ trợ cả các đơn vị ngày lịch và giờ/phút/giây phù hợp.

Dùng `date.plusDays(2)` khi bài toán nói rõ “hai ngày”; dùng dạng tổng quát khi unit đến từ một cấu hình có kiểm soát. Không truyền unit tùy ý mà chưa kiểm tra `isSupported(...)` nếu dữ liệu cấu hình có thể sai.

## 5. `minus(...)`: trừ lượng thời gian, không phải sửa trực tiếp

`minus` đối xứng về ý tưởng với `plus`:

~~~java
LocalDate date = LocalDate.of(2024, 3, 2);

LocalDate yesterday = date.minusDays(1);
// 2024-03-01

LocalDate threeDaysAgo = date.minusDays(3);
// 2024-02-28

LocalDate previousMonth = date.minusMonths(1);
// 2024-02-02
~~~

Các overload khác gồm `minusWeeks`, `minusYears`, `minus(long, ChronoUnit)`, `minus(TemporalAmount)`; với `LocalTime` có `minusHours`, `minusMinutes`, `minusSeconds`. Tương tự `plus`, **giá trị nguồn vẫn không đổi**.

Ví dụ:

~~~java
LocalDateTime due =
    LocalDateTime.of(2024, 3, 1, 8, 0);

LocalDateTime reminder = due.minusHours(12);
// 2024-02-29T20:00
~~~

### Số âm và biểu thức tương đương

Trong phạm vi giá trị hợp lệ, `date.plusDays(-3)` có cùng ý nghĩa về kết quả với `date.minusDays(3)`; `date.minusMonths(-1)` tương đương `date.plusMonths(1)`. Tuy nhiên, vì các phương thức có kiểm tra phạm vi và các giá trị long cực biên, **không tự viết** `minusDays(x)` thành `plusDays(-x)` bằng phép đổi dấu thủ công với `x == Long.MIN_VALUE` — `-Long.MIN_VALUE` tràn `long`. Hãy dùng API có sẵn để nó áp dụng quy tắc chính xác và ném lỗi khi ngoài phạm vi.

## 6. So sánh `with` với `plus`/`minus` bằng cùng một dữ liệu

| Yêu cầu nghiệp vụ | Ví dụ | Ý nghĩa |
| --- | --- | --- |
| Đặt tháng thành tháng Hai trong cùng năm | `date.withMonth(2)` | Đặt **MONTH_OF_YEAR = 2** |
| Cộng hai tháng lịch | `date.plusMonths(2)` | Dịch chuyển qua tháng và có thể qua năm |
| Đặt ngày trong tháng thành mùng 1 | `date.withDayOfMonth(1)` | Chọn đầu tháng hiện có |
| Đến ngày hôm sau | `date.plusDays(1)` | Tiến một ngày |
| Lùi một tuần | `date.minusWeeks(1)` | Lùi bảy ngày theo lịch |
| Đặt giờ thành 9 giờ | `time.withHour(9)` | Thay trường giờ, giữ phần phút/giây phù hợp |
| Đi tiếp 9 giờ | `time.plusHours(9)` | Cộng giờ vào giờ hiện tại, có thể qua nửa đêm |
| Lấy ngày cuối tháng | `date.with(lastDayOfMonth())` | Dùng quy tắc lịch |
| Trừ 90 phút khỏi ngày-giờ | `dateTime.minusMinutes(90)` | Dịch chuyển 90 phút trong LocalDateTime |

**Ví dụ dễ nhầm:**

~~~java
LocalDate date = LocalDate.of(2024, 12, 15);

System.out.println(date.withMonth(1));
// 2024-01-15 (vẫn năm 2024)

System.out.println(date.plusMonths(1));
// 2025-01-15 (đã sang năm 2025)
~~~

`withMonth(1)` không phải “tháng sau”, và `plusMonths(1)` không phải “đặt tháng thành 1”. Để code tự mô tả ý định, ưu tiên các tên phương thức rõ ràng thay vì dùng chung `with(ChronoField.MONTH_OF_YEAR,...)` cho mọi việc.

## 7. Ranh giới tháng, năm nhuận và quy tắc *clamp*

Các tháng có 28, 29, 30 hoặc 31 ngày. Khi cộng tháng/năm hoặc **thay tháng/năm**, ngày trong tháng của kết quả có thể không hợp lệ.

### 7.1. `plusMonths` và `withMonth` có thể chọn ngày cuối tháng hợp lệ

~~~java
LocalDate jan31 = LocalDate.of(2024, 1, 31);

LocalDate plusFebruary = jan31.plusMonths(1);
// 2024-02-29

LocalDate setFebruary = jan31.withMonth(2);
// 2024-02-29
~~~

Các thao tác trên không tạo ngày `2024-02-31`; chúng giữ ngày trong tháng nếu hợp lệ, nếu không thì đưa về **ngày cuối hợp lệ** của tháng đích. Năm 2024 nhuận nên là 29/2; năm 2025 không nhuận thì 28/2.

`plusYears` và `withYear` cũng có thể điều chỉnh ngày nhuận:

~~~java
LocalDate leapDay = LocalDate.of(2024, 2, 29);

System.out.println(leapDay.plusYears(1));
// 2025-02-28

System.out.println(leapDay.withYear(2025));
// 2025-02-28
~~~

Đây là **quy tắc đặc biệt của những thao tác có khả năng tạo ngày không hợp lệ khi đổi tháng/năm**, không phải mọi phương thức `with` đều âm thầm sửa một yêu cầu không hợp lệ.

### 7.2. `withDayOfMonth` khi được yêu cầu một ngày không tồn tại sẽ ném lỗi

~~~java
LocalDate feb = LocalDate.of(2024, 2, 29);

// feb.withDayOfMonth(31); // DateTimeException
~~~

`withDayOfMonth(31)` yêu cầu **ngày 31 trong tháng Hai**. Nó sẽ ném `DateTimeException`, không tự biến thành 29/2. Tương tự `LocalDate.of(2023, 2, 29)` không hợp lệ và ném `DateTimeException` ngay khi tạo.

**Quy tắc cần nhớ:**

- `plusMonths`, `minusMonths`, `plusYears`, `minusYears`, `withMonth`, `withYear` có thể điều chỉnh ngày cuối tháng khi cần.
- `withDayOfMonth`, `withDayOfYear` yêu cầu trường ngày hợp lệ đối với ngày/tháng/năm kết quả; nếu không thì ném lỗi.
- Không suy rộng từ trường hợp cụ thể của một method sang tất cả overload `with/plus/minus` hoặc mọi triển khai `TemporalField` tùy chỉnh.

### 7.3. Cộng một tháng hai lần có thể khác cộng hai tháng một lần

Một trường hợp có ảnh hưởng trực tiếp đến lịch thanh toán:

~~~java
LocalDate anchor = LocalDate.of(2024, 1, 31);

LocalDate step1 = anchor.plusMonths(1); // 2024-02-29
LocalDate step2 = step1.plusMonths(1);  // 2024-03-29

LocalDate direct = anchor.plusMonths(2); // 2024-03-31
~~~

**`anchor.plusMonths(1).plusMonths(1) != anchor.plusMonths(2)` về mặt giá trị** trong ví dụ này. Lý do là sau bước đầu, ngày gốc 31 đã được **clamp** thành 29, rồi bước sau tiếp tục từ ngày 29. Nếu mỗi kỳ tính từ **mốc gốc**, tháng Ba vẫn có ngày 31.

### 7.4. Thiết kế lịch cuối tháng không bị “trôi ngày”

Nếu nghiệp vụ là “ngày cuối của mỗi tháng tính từ một mốc tháng”, nên dùng mốc và quy tắc rõ ràng:

~~~java
LocalDate anchor = LocalDate.of(2024, 1, 31);

for (int monthOffset = 1; monthOffset <= 3; monthOffset++) {
    LocalDate periodEnd = anchor.plusMonths(monthOffset)
        .with(TemporalAdjusters.lastDayOfMonth());
    System.out.println(periodEnd);
}

// 2024-02-29
// 2024-03-31
// 2024-04-30
~~~

Một quy tắc khác — ví dụ “ngày 30, hoặc ngày cuối tháng nếu tháng không có ngày 30” — phải được mô tả và kiểm thử riêng. Đừng tự mặc định mọi hợp đồng thanh toán đều theo “cuối tháng”.

## 8. `Period` và `Duration`: lượng theo lịch khác lượng theo thời gian

### 8.1. `Period` cho năm, tháng, ngày

~~~java
LocalDate start = LocalDate.of(2024, 1, 31);

LocalDate next = start.plus(Period.ofMonths(1));
// 2024-02-29

LocalDate previous = start.minus(Period.ofDays(7));
// 2024-01-24
~~~

`Period` là giá trị bất biến chứa **năm, tháng, ngày**. Nó phù hợp với các công việc tính hạn theo lịch: gia hạn 1 tháng, lùi 2 tuần theo ngày, tính ngày sau một số tháng. Một tháng không mặc định bằng 30 ngày; một năm không mặc định bằng 365 ngày.

### 8.2. `Duration` cho lượng giây, nano

~~~java
LocalDateTime start =
    LocalDateTime.of(2024, 2, 28, 23, 30);

LocalDateTime later =
    start.plus(Duration.ofMinutes(90));
// 2024-02-29T01:00
~~~

`Duration` hữu ích cho lượng thời gian theo giờ/phút/giây/nano. `LocalDateTime` hỗ trợ cộng lượng thời gian kiểu `Duration` vì có trường giờ và phút. `LocalDate` **không hỗ trợ** đơn vị giờ/giây; gọi `LocalDate.plus(Duration.ofHours(24))` là không hợp lệ theo hợp đồng và có thể ném `UnsupportedTemporalTypeException`. Đừng dựa vào giả định “24 giờ luôn tự đổi sang một ngày” cho mọi loại đối tượng.

**Điểm phân biệt khi có múi giờ:** `LocalDateTime` không biết DST. Phép `plusHours(24)` ở cấp LocalDateTime là toán theo giá trị ngày-giờ cục bộ. Nếu cần thời lượng 24 giờ **trên dòng thời gian thực**, hãy chuyển vấn đề sang `Instant` hoặc `ZonedDateTime` với `ZoneId` phù hợp. Với ngày bắt đầu/kết thúc qua DST, cộng **một ngày lịch** và cộng **24 giờ thực** có thể cho kết quả khác nhau.

### 8.3. Chọn đơn vị theo ý định

| Nhu cầu | Cách thường phù hợp |
| --- | --- |
| Gia hạn thêm một tháng lịch | `LocalDate.plusMonths(1)` hoặc `plus(Period.ofMonths(1))` |
| Nhắc trước ba ngày | `LocalDate.minusDays(3)` |
| Cộng 45 phút vào giờ cục bộ | `LocalTime.plusMinutes(45)` |
| Chuyển lịch hẹn cục bộ sau 90 phút | `LocalDateTime.plus(Duration.ofMinutes(90))` |
| Đo 90 phút thực của một phiên làm việc | `Instant`/`Duration` |
| Chọn ngày cuối của tháng hiện tại | `with(TemporalAdjusters.lastDayOfMonth())` |

## 9. Chaining: tạo pipeline ngày giờ mà không sửa biến ban đầu

Một lợi ích của các phép toán immutable là có thể **ghép nhiều bước rõ ràng**:

~~~java
LocalDate today = LocalDate.of(2024, 2, 28);

LocalDate result = today
    .plusMonths(1)
    .withDayOfMonth(1)
    .minusDays(1);

// today  = 2024-02-28
// result = 2024-02-29
~~~

Giải thích từng bước:

1. `plusMonths(1)` → `2024-03-28`.
2. `withDayOfMonth(1)` → `2024-03-01`.
3. `minusDays(1)` → `2024-02-29`.

Với bài toán “cuối tháng hiện tại”, `today.with(TemporalAdjusters.lastDayOfMonth())` thường **ngắn và thể hiện đúng ý định hơn**. Chaining chỉ có ích khi người đọc dễ hiểu quy tắc; không nên nối nhiều phương thức khó đọc chỉ để khoe cú pháp.

**Đừng quên kết quả từng bước:**

~~~java
LocalDate day = LocalDate.of(2024, 2, 28);

day.plusMonths(1);
day.withDayOfMonth(1);
day.minusDays(1);

// day vẫn là 2024-02-28; các kết quả trước bị bỏ đi.
~~~

Nếu không chain, phải gán lại:

~~~java
day = day.plusMonths(1);
day = day.withDayOfMonth(1);
day = day.minusDays(1);
~~~

Đây là gán lại biến `day`, không đột biến đối tượng ngày cũ.

## 10. Chương trình Java hoàn chỉnh, đầu ra xác định

Lưu chương trình sau vào **`LocalDateTimeTransformDemo.java`**. Tất cả API được sử dụng có từ Java 8, nên chương trình biên dịch trên JDK 17+ và có thể kiểm tra bằng `javac --release 8` khi dùng JDK mới.

~~~java
import java.time.DateTimeException;
import java.time.Duration;
import java.time.LocalDate;
import java.time.LocalDateTime;
import java.time.LocalTime;
import java.time.Period;
import java.time.DayOfWeek;
import java.time.temporal.ChronoField;
import java.time.temporal.ChronoUnit;
import java.time.temporal.TemporalAdjusters;
import java.time.temporal.UnsupportedTemporalTypeException;
import java.util.List;
import java.util.stream.Collectors;
import java.util.stream.IntStream;

public class LocalDateTimeTransformDemo {

    public static void main(String[] args) {
        LocalDate janEnd = LocalDate.of(2024, 1, 31);

        System.out.println("jan=" + janEnd);
        System.out.println("plusMonth=" + janEnd.plusMonths(1));
        System.out.println("withMonth=" + janEnd.withMonth(2));
        System.out.println("twiceOneMonth="
                + janEnd.plusMonths(1).plusMonths(1));
        System.out.println("directTwoMonths="
                + janEnd.plusMonths(2));
        System.out.println("janStill=" + janEnd);

        LocalDate leapDay = LocalDate.of(2024, 2, 29);
        System.out.println("plusYear=" + leapDay.plusYears(1));
        System.out.println("withYear=" + leapDay.withYear(2025));

        LocalDate feb = LocalDate.of(2024, 2, 15);
        System.out.println("lastFebruary="
                + feb.with(TemporalAdjusters.lastDayOfMonth()));
        System.out.println("nextMonday="
                + LocalDate.of(2024, 2, 28).with(
                    TemporalAdjusters.next(DayOfWeek.MONDAY)));
        System.out.println("withField="
                + feb.with(ChronoField.DAY_OF_MONTH, 1));
        System.out.println("plusUnit="
                + feb.plus(2, ChronoUnit.WEEKS));

        LocalDate base = LocalDate.of(2024, 2, 28);
        System.out.println("period="
                + base.plus(Period.ofDays(3)));
        System.out.println("minusDays="
                + LocalDate.of(2024, 3, 2).minusDays(3));

        LocalTime evening = LocalTime.of(23, 45);
        System.out.println("timePlus="
                + evening.plusMinutes(30));
        System.out.println("timeWith="
                + evening.withHour(9));
        System.out.println("timeStill=" + evening);

        LocalDateTime late =
                LocalDateTime.of(2024, 2, 28, 23, 30);
        System.out.println("dateTimePlus="
                + late.plusHours(2));
        System.out.println("dateTimeWith="
                + late.withHour(8).withMinute(0));
        System.out.println("dateTimeMinus="
                + late.minusDays(1));
        System.out.println("duration="
                + late.plus(Duration.ofMinutes(90)));
        System.out.println("dateTimeStill=" + late);

        LocalDate endOfFebruary = base.plusMonths(1)
                .withDayOfMonth(1).minusDays(1);
        System.out.println("chained=" + endOfFebruary);

        try {
            leapDay.withDayOfMonth(31);
        } catch (DateTimeException ex) {
            System.out.println("invalidDay="
                    + ex.getClass().getSimpleName());
        }

        try {
            leapDay.plus(Duration.ofHours(24));
        } catch (UnsupportedTemporalTypeException ex) {
            System.out.println("unsupportedUnit="
                    + ex.getClass().getSimpleName());
        }

        System.out.println("equalValues="
                + leapDay.equals(LocalDate.parse("2024-02-29")));

        List<LocalDate> days = IntStream.range(0, 3)
                .parallel()
                .mapToObj(leapDay::plusDays)
                .collect(Collectors.toList());
        System.out.println("parallelDays=" + days);
        System.out.println("originalAfterParallel=" + leapDay);
    }
}
~~~

Biên dịch/chạy:

~~~bash
javac -encoding UTF-8 LocalDateTimeTransformDemo.java
java LocalDateTimeTransformDemo
~~~

**Đầu ra kỳ vọng:**

~~~text
jan=2024-01-31
plusMonth=2024-02-29
withMonth=2024-02-29
twiceOneMonth=2024-03-29
directTwoMonths=2024-03-31
janStill=2024-01-31
plusYear=2025-02-28
withYear=2025-02-28
lastFebruary=2024-02-29
nextMonday=2024-03-04
withField=2024-02-01
plusUnit=2024-02-29
period=2024-03-02
minusDays=2024-02-28
timePlus=00:15
timeWith=09:45
timeStill=23:45
dateTimePlus=2024-02-29T01:30
dateTimeWith=2024-02-28T08:00
dateTimeMinus=2024-02-27T23:30
duration=2024-02-29T01:00
dateTimeStill=2024-02-28T23:30
chained=2024-02-29
invalidDay=DateTimeException
unsupportedUnit=UnsupportedTemporalTypeException
equalValues=true
parallelDays=[2024-02-29, 2024-03-01, 2024-03-02]
originalAfterParallel=2024-02-29
~~~

### Giải thích những dòng dễ gây nhầm

1. **`plusMonth` và `withMonth` đều cho 29/2** ở trường hợp mốc 31/1 năm nhuận, nhưng thao tác đầu là **cộng tháng**, thao tác sau là **đặt tháng = 2**; kết quả trùng chỉ ở đầu vào này.
2. **`twiceOneMonth=2024-03-29`** khác **`directTwoMonths=2024-03-31`** vì lần cộng thứ nhất đã clamp ngày 31 xuống 29.
3. **`plusYear` và `withYear`** chọn ngày 28/2/2025 khi chuyển từ ngày 29/2/2024.
4. **`nextMonday`** là ngày 4/3/2024 vì 28/2/2024 là thứ Tư.
5. **`timePlus=00:15`** không nói ngày nào; **`dateTimePlus=2024-02-29T01:30`** có ngày nên thể hiện việc vượt nửa đêm.
6. **`invalidDay`** kiểm tra phương thức `withDayOfMonth(31)` trên tháng Hai không có ngày 31. **`unsupportedUnit`** minh họa `LocalDate` không chấp nhận `Duration` tính bằng giờ/giây.
7. **`parallelDays`** được tạo từ `IntStream.range` có encounter order; `Collectors.toList()` giữ thứ tự nguồn dù tính toán có thể thực hiện song song. Đây là ví dụ dùng giá trị `LocalDate` immutable trong mapper; không chứng minh mọi state mutable bên ngoài cũng an toàn luồng.
8. `janStill`, `dateTimeStill` và `originalAfterParallel` xác nhận đối tượng ngày giờ gốc không đổi.

## 11. Lỗi và ngoại lệ cần xử lý đúng

### 11.1. `DateTimeException` do trường ngày giờ không hợp lệ

~~~java
LocalDate.of(2023, 2, 29);      // Không phải năm nhuận.
LocalDate.of(2024, 2, 29)
    .withDayOfMonth(31);         // Tháng Hai không có 31.
LocalTime.of(24, 0);             // Giờ hợp lệ là 0..23.
~~~

Các dòng ở trên là **phản ví dụ**, sẽ ném `DateTimeException` nếu chạy; không phải chương trình chạy đầy đủ. Một số thao tác đổi tháng/năm sẽ clamp ngày khi cần; nhưng yêu cầu trực tiếp một ngày/giờ không tồn tại thì không được tự coi là sẽ clamp.

### 11.2. `UnsupportedTemporalTypeException` do sai unit/field

~~~java
LocalDate date = LocalDate.of(2024, 2, 29);

// Không phù hợp vì LocalDate không có giờ:
date.plus(2, ChronoUnit.HOURS);
date.with(ChronoField.HOUR_OF_DAY, 9);
~~~

Đây là mã minh họa về lỗi nếu thực thi. Chọn `LocalDateTime` khi logic thực sự cần ngày và giờ, hoặc chọn `LocalTime` khi chỉ cần giờ. Không đánh đồng `Temporal` với “bất cứ field/unit nào cũng hợp lệ”.

### 11.3. Tràn phạm vi và số âm cực biên

`LocalDate` có phạm vi năm giới hạn, và các giá trị `long` dùng làm lượng cộng/trừ cũng có giới hạn. `LocalDate.MAX.plusDays(1)` không thể tạo một ngày hợp lệ; phép tính có thể ném `DateTimeException` hoặc `ArithmeticException` theo tình huống. Dùng phép toán có kiểm tra, validate đầu vào và bắt ngoại lệ tại ranh giới phù hợp; đừng dùng `try/catch` để che mọi lỗi thời gian thành một giá trị tùy ý.

Nếu lượng đến từ input không đáng tin, cần kiểm tra biên, ngăn cộng quá hạn, và quy định điều gì xảy ra khi hạn không thể tính được.

### 11.4. Quên dùng kết quả trả về

~~~java
LocalDate d = LocalDate.of(2024, 2, 28);
d.plusDays(1);
System.out.println(d); // Vẫn 2024-02-28.
~~~

Đây là lỗi thường gặp nhất khi mới chuyển từ API ngày giờ mutable sang `java.time`. Cách đúng: `d = d.plusDays(1)` hoặc trả trực tiếp `return d.plusDays(1)`.

### 11.5. So sánh bằng reference thay vì giá trị

`a == b` có thể không phản ánh “cùng ngày”. `LocalDate`, `LocalTime` và `LocalDateTime` là value-based, so sánh bằng `equals` hoặc quan hệ theo ngày giờ. Không dùng đối tượng ngày giờ làm khóa monitor dựa vào identity.

### 11.6. Cộng tháng cho lịch thu phí nhưng không xác định chính sách clamp

`2024-01-31.plusMonths(1)` cho 29/2. Nếu tiếp tục cộng từ kết quả, ngày 29 có thể được giữ ở các tháng sau. Nếu yêu cầu phải “cuối mỗi tháng” hoặc “ngày N nếu có, không thì ngày cuối tháng”, cần thiết kế quy tắc rõ và kiểm thử nhiều năm nhuận.

### 11.7. Sai loại ngày giờ khi tính giờ thực

`LocalDateTime.plusHours(24)` tính trên lịch/đồng hồ địa phương mà không có quy tắc DST. Nếu nghiệp vụ đo 24 giờ trôi qua xuyên vùng có DST, nên làm phép cộng/so sánh trên `Instant` hoặc `ZonedDateTime` với zone phù hợp, và kiểm tra sự khác nhau giữa ngày lịch với giờ thực.

## 12. Dùng đối tượng bất biến trong nhiều luồng: đúng phạm vi

Các lớp ngày giờ cục bộ chính của `java.time` là **immutable và thread-safe**. Một `LocalDate` có thể được truyền cho nhiều task, mỗi task gọi `plusDays` hay `withDayOfMonth` để nhận giá trị riêng, mà không cần đồng bộ bảo vệ chính đối tượng đó.

Tuy nhiên, **biến tham chiếu** chứa một `LocalDate` vẫn có thể được các luồng sửa không an toàn:

~~~java
// Phản ví dụ về thiết kế trong một class:
private LocalDate current = LocalDate.of(2024, 1, 1);

void nextDay() {
    current = current.plusDays(1); // Không atomic nếu nhiều thread gọi.
}
~~~

Nhiều luồng có thể cùng đọc giá trị cũ rồi cùng ghi kết quả, khiến mất một lượt cập nhật. Nếu cần cập nhật chung thực sự, dùng `AtomicReference<LocalDate>`, lock hoặc thiết kế không cần shared mutable reference, ví dụ:

~~~java
AtomicReference<LocalDate> current =
    new AtomicReference<>(LocalDate.of(2024, 1, 1));

current.updateAndGet(day -> day.plusDays(1));
~~~

Đây là minh họa, cần import `java.util.concurrent.atomic.AtomicReference`. Callback của `updateAndGet` có thể được gọi **nhiều lần do tranh chấp**, vì thế phải thuần, không có side effect như gửi email hoặc ghi tiền vào hệ thống khác. `plusDays(1)` trên `LocalDate` là phép biến đổi giá trị thích hợp.

Tương tự, `List<LocalDate>` mutable không tự thread-safe để nhiều luồng thêm/xóa, dù phần tử `LocalDate` immutable. Tách an toàn của **đối tượng giá trị** khỏi an toàn của **container/reference**.

## 13. Thực hành nghiệp vụ: ngày đến hạn, giờ hẹn và lịch lặp

### 13.1. Ngày đến hạn sau 14 ngày

~~~java
LocalDate issued = LocalDate.of(2024, 5, 10);
LocalDate due = issued.plusDays(14);

// issued = 2024-05-10
// due    = 2024-05-24
~~~

Rõ ràng, dễ test, không cần tự quy đổi ngày sang milliseconds hoặc tự cộng vào các trường số.

### 13.2. Nhắc trước hạn ba ngày

~~~java
LocalDate reminder = due.minusDays(3);
// Nếu due = 2024-05-24, reminder = 2024-05-21.
~~~

Đoạn này giả sử `due` đã được tính trong cùng phạm vi. Không nhầm `minusDays(3)` với “ba ngày làm việc”: để bỏ qua cuối tuần/ngày nghỉ, cần một **business calendar** cụ thể; `LocalDate.minusDays` xử lý ngày theo lịch ISO chứ không tự biết ngày nghỉ.

### 13.3. Giờ hẹn cố định trong một ngày

~~~java
LocalDate date = LocalDate.of(2024, 5, 10);
LocalTime desiredTime = LocalTime.of(9, 30);

LocalDateTime appointment = date.atTime(desiredTime);
// 2024-05-10T09:30

LocalDateTime moved = appointment.withHour(10);
// 2024-05-10T10:30
~~~

`withHour(10)` chỉ thay giờ, giữ phút là 30. Nếu cần chuyển thành 10:00, dùng `withHour(10).withMinute(0)`.

### 13.4. Hạn cuối một tháng và chu kỳ định kỳ

~~~java
LocalDate reference = LocalDate.of(2024, 4, 12);

LocalDate monthEnd =
    reference.with(TemporalAdjusters.lastDayOfMonth());
// 2024-04-30
~~~

`with(lastDayOfMonth())` thể hiện chính sách cuối tháng rõ ràng. Với lịch lặp theo mốc và quy tắc riêng, hãy lưu **anchor** và tính từng kỳ từ anchor hoặc áp dụng adjuster cuối tháng phù hợp, không vô tình để hiện tượng clamp tích lũy làm trôi mốc.

### 13.5. Khi cần ngày và giờ của “bây giờ”

`LocalDate.now()` / `LocalDateTime.now()` phụ thuộc đồng hồ hệ thống và zone mặc định trong một số overload. Để kiểm thử ổn định, có thể dùng `Clock.fixed` và truyền `Clock` vào logic. Đây là nguyên tắc API vẫn hiện hành: bài toán “thời điểm hiện tại” khác với phép biến đổi `plus/with/minus` trên một giá trị đã biết.

## 14. Checklist trước khi áp dụng

1. Đối tượng là `LocalDate`, `LocalTime` hay `LocalDateTime`? Kiểu có chứa đủ trường cho phép tính không?
2. Muốn **đặt một trường** (`with`), **cộng một lượng** (`plus`) hay **trừ một lượng** (`minus`)?
3. Đã **giữ kết quả trả về** chưa, hay vô tình gọi rồi bỏ đi?
4. Đã phân biệt **giá trị bất biến** với **biến tham chiếu có thể gán lại** chưa?
5. Nếu dùng `with(ChronoField, ...)` hoặc `plus(ChronoUnit, ...)`, field/unit có được kiểu đó hỗ trợ không?
6. Đã kiểm tra ngày cuối tháng, năm nhuận, và khác nhau giữa `withMonth`/`plusMonths` chưa?
7. Nếu cộng tháng lặp, có chủ đích cộng **từng bước** hay tính từ **mốc ban đầu**? Chính sách clamp có làm trôi lịch không?
8. Có trường hợp yêu cầu ngày không tồn tại, ví dụ `withDayOfMonth(31)` trong tháng Hai, cần xử lý `DateTimeException` không?
9. Có dùng `Period` đúng cho năm/tháng/ngày và `Duration` đúng cho thời lượng giờ/phút/giây không?
10. Có tính giờ xuyên DST hoặc chuyển vùng không? Nếu có, đừng coi `LocalDateTime` là một instant với zone.
11. Có dùng `equals` để so giá trị và tránh phụ thuộc `==`/identity không?
12. Nếu nhiều thread cập nhật chung một biến `LocalDate`, đã bảo vệ **reference/update** chứ không chỉ tin vào immutable element chưa?
13. Unit test có bao gồm đầu và cuối tháng, 28/29/30/31 ngày, năm nhuận, vượt nửa đêm, số âm và các trường không hỗ trợ không?

**Kết luận:** `with` chọn **giá trị trường/điều chỉnh lịch**, `plus` cộng lượng, `minus` trừ lượng. Với `LocalDate`, `LocalTime` và `LocalDateTime`, các thao tác này **trả một giá trị bất biến về mặt ngữ nghĩa** và không sửa đối tượng gốc. Sử dụng giá trị trả về, kiểm tra ngày hợp lệ, hiểu quy tắc clamp cuối tháng và chọn đúng kiểu/ngữ nghĩa thời gian là các kỹ năng cốt lõi vẫn đúng trong Java hiện đại.

## Tài liệu chính thức

- [Oracle Java SE 25 — LocalDate: with/plus/minus, xử lý ngày cuối tháng và năm nhuận](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/time/LocalDate.html)
- [Oracle Java SE 25 — LocalTime: withHour, plusMinutes, quay vòng khi qua nửa đêm](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/time/LocalTime.html)
- [Oracle Java SE 25 — LocalDateTime: plusHours/with và phần ngày-giờ cục bộ](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/time/LocalDateTime.html)
- [Oracle Java SE 25 — TemporalAdjusters: lastDayOfMonth, next/nextOrSame](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/time/temporal/TemporalAdjusters.html)
- [Oracle Java SE 25 — ChronoUnit và ChronoField](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/time/temporal/package-summary.html)
- [Oracle Java SE 25 — Period và Duration](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/time/package-summary.html)
