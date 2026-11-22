# between, until và ChronoUnit trong Java: đo khoảng thời gian đúng ngữ nghĩa

`ChronoUnit.between(start, end)`, `Temporal.until(end, unit)`, `Duration.between(start, end)` và `Period.between(startDate, endDate)` đều thuộc bộ API `java.time` có từ Java 8 và **vẫn được hỗ trợ trong Java hiện hành**. Chúng cùng xử lý hai mốc thời gian nhưng **trả lời những câu hỏi khác nhau**:

- `ChronoUnit.DAYS.between(start, end)`: bao nhiêu **đơn vị ngày trọn vẹn**, theo quy tắc của kiểu mốc đầu vào?
- `start.until(end, ChronoUnit.DAYS)`: cùng phép đo số ngày trọn vẹn, chỉ khác cách viết.
- `Duration.between(start, end)`: độ dài được mô tả bằng **giây/nano**, phù hợp đo thời gian đã trôi qua.
- `Period.between(startDate, endDate)`: khoảng **lịch ISO** phân rã thành năm, tháng, ngày.

Ví dụ, hai giờ địa phương ở New York cách nhau **hai ngày trên lịch** có thể chỉ cách nhau **47 giờ thực tế** khi chuyển sang giờ mùa hè, hoặc **49 giờ** khi chuyển về giờ chuẩn. Một khoảng từ ngày 31/01 đến 29/02 có thể chứa 29 ngày nhưng chưa chứa một **tháng trọn vẹn** theo `MONTHS.between`. Đây là những lỗi thường gặp nếu chọn API theo tên thay vì theo yêu cầu nghiệp vụ.

Bài này trình bày cách tính, thời điểm bắt đầu/kết thúc, số đơn vị trọn vẹn, kết quả âm, ngày nhuận và cuối tháng, các khác biệt giữa `Period` và `Duration`, múi giờ và DST, giới hạn unit, ví dụ Java độc lập và kiểm thử.

## 1. Chọn đúng kiểu và đúng đơn vị trước khi tính

| Câu hỏi nghiệp vụ | Kiểu đầu vào phù hợp | API thường dùng |
|---|---|---|
| Hai ngày cách nhau bao nhiêu ngày lịch? | `LocalDate` | `ChronoUnit.DAYS.between` |
| Có bao nhiêu tháng hoặc năm trọn vẹn? | `LocalDate` | `MONTHS.between`, `YEARS.between` |
| Khoảng lịch là mấy năm, tháng, ngày? | `LocalDate` | `Period.between` |
| Hai sự kiện cách nhau mấy giây thực tế? | `Instant` | `Duration.between` |
| Hai mốc theo vùng cách nhau bao nhiêu giờ đã trôi? | `ZonedDateTime` | `HOURS.between` hoặc `Duration.between` |
| Hai mốc trong một vùng cách nhau bao nhiêu ngày lịch? | `ZonedDateTime` | `DAYS.between` |
| Cần đo ngày làm việc, trừ cuối tuần và lễ | Ngày + lịch nghiệp vụ | Thuật toán lịch làm việc, không chỉ ChronoUnit |
| Cần đặt lịch lúc 09:00 theo giờ địa phương | `LocalDateTime` + `ZoneId` | Quy tắc lịch và DST riêng |

**Các kiểu cần hiểu:**

- `LocalDate` biểu diễn ngày lịch ISO, **không chứa giờ hoặc múi giờ**.
- `LocalDateTime` chứa ngày-giờ trên đồng hồ nhưng **không có offset/ZoneId**, vì vậy không xác định duy nhất một instant.
- `Instant` xác định một thời điểm trên trục UTC.
- `ZonedDateTime` có ngày-giờ, vùng và quy tắc offset/DST.
- `Duration` mô tả khoảng dài bằng giây và nanosecond.
- `Period` mô tả khoảng **lịch** bằng năm, tháng, ngày.

Không có một cách đo “ngày” đúng cho tất cả các kiểu. `DAYS.between` trên `Instant` đếm các khối 86.400 giây trọn vẹn; trên `ZonedDateTime`, nó đếm ngày theo **local timeline** và có thể đi qua ngày dài 23/25 giờ vì DST.

## 2. ChronoUnit là gì?

`java.time.temporal.ChronoUnit` là enum triển khai `TemporalUnit`, cung cấp các đơn vị thời gian chuẩn. Dùng nó để đo khoảng cách theo đơn vị, hoặc truyền vào `until`/`plus`/`minus` khi kiểu temporal hỗ trợ.

| Đơn vị ChronoUnit | Ý nghĩa | Lưu ý |
|---|---|---|
| `NANOS`, `MICROS`, `MILLIS` | Nano-, micro-, millisecond | Đo khoảng rất nhỏ; có thể tràn long nếu khoảng cực lớn |
| `SECONDS`, `MINUTES`, `HOURS` | Giây, phút, giờ | Time-based, hợp đo độ dài đã trôi |
| `HALF_DAYS` | 12 giờ | Vẫn còn là API hợp lệ |
| `DAYS`, `WEEKS` | Ngày và tuần | Date-based; trên ZonedDateTime phụ thuộc local timeline |
| `MONTHS`, `YEARS` | Tháng và năm lịch | Không thể quy đổi chính xác bằng số ngày cố định |
| `DECADES`, `CENTURIES`, `MILLENNIA` | 10, 100, 1.000 năm | Dùng trong lịch dài hạn |
| `ERAS` | Kỷ nguyên của lịch | Không phải phép đo giây thông thường |
| `FOREVER` | Đơn vị biểu tượng vô hạn | Không dùng để đếm một số đơn vị hữu hạn thông thường |

Các kiểu temporal **không hỗ trợ mọi unit**. Chẳng hạn:

~~~java
LocalDate date = LocalDate.of(2024, 2, 28);

boolean daysSupported = date.isSupported(ChronoUnit.DAYS);   // true
boolean hoursSupported = date.isSupported(ChronoUnit.HOURS); // false
~~~

Mảnh code này cần `import java.time.*;` và `import java.time.temporal.*;`. `LocalDate` có ngày nhưng không có giờ; gọi `HOURS.between` với hai LocalDate sẽ ném `UnsupportedTemporalTypeException`. `Instant` đo trên UTC timeline nhưng không tự biết **tháng lịch ở vùng nào**; không dùng `MONTHS.between` cho hai Instant.

### 2.1. Một ngày trong ChronoUnit có nhất thiết 24 giờ?

~~~java
ChronoUnit.DAYS.isDurationEstimated();  // true
ChronoUnit.HOURS.isDurationEstimated(); // false
ChronoUnit.DAYS.getDuration();          // PT24H
~~~

`getDuration()` trả độ dài **danh nghĩa** của unit. Với các date-based unit như `DAYS`, độ dài có thể **được ước lượng**: ngày lịch có lúc dài 23 hoặc 25 giờ trong vùng có DST. `MONTHS` và `YEARS` càng không có số giây cố định cho mọi ngày bắt đầu.

Không lấy `ChronoUnit.MONTHS.getDuration()` rồi chia Duration cho con số ước lượng để đếm tháng lịch. Nếu cần tháng trọn vẹn theo ngày, chọn `MONTHS.between` với kiểu ngày phù hợp.

## 3. ChronoUnit.between: số đơn vị hoàn chỉnh

Cú pháp chuẩn:

~~~java
long amount = ChronoUnit.DAYS.between(start, end);
~~~

`TemporalUnit.between` có tham số `startInclusive` và `endExclusive`. Nó tính **số nguyên long đại diện cho các đơn vị hoàn chỉnh**, không trả số thực và không làm tròn lên.

- `end` sau `start`: kết quả thường dương.
- Hai mốc bằng nhau: kết quả 0.
- `end` trước `start`: kết quả âm.
- Khoảng chưa đủ một unit: kết quả có thể 0 hoặc chỉ các unit đã hoàn chỉnh.
- Hai kiểu temporal phải tương thích; unit phải được hỗ trợ.
- Phương thức chỉ đọc, không sửa hai đối tượng ngày giờ.
- Có thể ném `DateTimeException`, `UnsupportedTemporalTypeException` hoặc `ArithmeticException` nếu không thể tính.

### 3.1. Start-inclusive và end-exclusive không phải đếm cả hai ngày

~~~java
LocalDate start = LocalDate.of(2024, 3, 1);
LocalDate end = LocalDate.of(2024, 3, 2);

long days = ChronoUnit.DAYS.between(start, end); // 1
~~~

Kết quả 1 vì khoảng từ **đầu ngày 01/03 tới đầu ngày 02/03** có đúng một ngày. Nó **không** phải cách đếm hai nhãn ngày “01/03 và 02/03” đều thuộc danh sách.

Trong nghiệp vụ khách sạn, `DAYS.between(checkIn, checkOut)` thường là số **đêm lưu trú**. Trong báo cáo đếm cả hai đầu, có thể cần một quy tắc khác sau khi validate ngày. Không cộng 1 lên mọi kết quả `between` mà không hỏi yêu cầu.

### 3.2. Java tự biết năm nhuận

~~~java
LocalDate from = LocalDate.of(2024, 2, 28);
LocalDate to = LocalDate.of(2024, 3, 1);

long leapDays = ChronoUnit.DAYS.between(from, to); // 2
~~~

Năm 2024 có ngày 29/02, nên từ đầu 28/02 đến đầu 01/03 là **hai ngày**. Không tự viết phép trừ ngày-tháng bằng số học hoặc coi một tháng là 30 ngày.

### 3.3. Chiều đảo và giá trị âm

~~~java
long forward = ChronoUnit.DAYS.between(
        LocalDate.of(2024, 2, 28),
        LocalDate.of(2024, 3, 1)); // 2

long backward = ChronoUnit.DAYS.between(
        LocalDate.of(2024, 3, 1),
        LocalDate.of(2024, 2, 28)); // -2
~~~

Một SLA hoặc hạn thanh toán cần biết đã quá hạn hay chưa thì **dấu âm/dương có ý nghĩa nghiệp vụ**. Nếu mốc kết thúc không được sớm hơn mốc đầu, nên từ chối đầu vào thay vì lấy trị tuyệt đối và che lỗi. `Math.abs(long)` cũng không luôn có giá trị dương biểu diễn được tại `Long.MIN_VALUE`.

### 3.4. Phần đơn vị chưa trọn vẹn bị loại

~~~java
LocalDateTime a = LocalDateTime.of(2024, 1, 1, 11, 30);
LocalDateTime b = LocalDateTime.of(2024, 1, 1, 13, 29);

long hours = ChronoUnit.HOURS.between(a, b);   // 1
long minutes = ChronoUnit.MINUTES.between(a, b); // 119
~~~

Khoảng 1 giờ 59 phút có **một giờ hoàn chỉnh**, chứ không phải 2. Tương tự, khoảng 9 ngày theo `WEEKS` chỉ có 1 tuần trọn vẹn. Nếu muốn biểu diễn 1 giờ và 59 phút, dùng `Duration.between` và tách thành phần phù hợp; không coi `HOURS.between` là kết quả đã làm tròn lên.

### 3.5. Không trộn hai loại Temporal tùy tiện

Hợp đồng cho phép một số phép chuyển kiểu tương thích và có thể **chuyển mốc thứ hai theo loại mốc đầu**, nhưng không phải mọi cách phối hợp đều hợp lệ. Tốt nhất truyền **cùng loại temporal** đã được chọn theo yêu cầu:

~~~java
Instant a = Instant.parse("2024-01-01T00:00:00Z");
Instant b = Instant.parse("2024-01-02T00:00:00Z");

long hours = ChronoUnit.HOURS.between(a, b); // 24
~~~

Nếu một mốc là `LocalDateTime` và mốc kia là `ZonedDateTime`, phải quyết định có cần quy tắc múi giờ và DST hay không rồi chuyển cả hai về cùng mô hình. Không dựa vào conversion ngầm để đưa ra quyết định nghiệp vụ.

## 4. Temporal.until: cùng phép đo, cách gọi từ start

`Temporal.until(endExclusive, unit)` tính số unit trọn vẹn từ đối tượng hiện tại tới mốc cuối. Hai dòng sau **tương đương** khi hai temporal và unit tương thích:

~~~java
long byUnit = ChronoUnit.DAYS.between(start, end);
long byTemporal = start.until(end, ChronoUnit.DAYS);
~~~

Khi `start` và `end` là `LocalDate`, kết quả `byUnit == byTemporal`. Chọn cách đọc rõ hơn:

- `DAYS.between(start, end)` nhấn mạnh **đơn vị**.
- `start.until(end, DAYS)` nhấn mạnh **mốc bắt đầu**.

Không có khác biệt ngầm như một bên tính cả mốc cuối, bên kia không. Cũng không có chuyện `until` mặc định lấy thời điểm hiện tại: chính người gọi cung cấp `end`.

### 4.1. Hai overload LocalDate.until trả kiểu khác nhau

~~~java
LocalDate start = LocalDate.of(2024, 1, 15);
LocalDate end = LocalDate.of(2025, 3, 18);

long months = start.until(end, ChronoUnit.MONTHS); // 14
Period period = start.until(end);                  // P1Y2M3D
~~~

`until(end, MONTHS)` trả một **long**: 14 tháng trọn vẹn. `LocalDate.until(end)` không có tham số unit lại trả **Period**: một năm, hai tháng, ba ngày. Không viết `long x = start.until(end)` vì đây là lỗi kiểu dữ liệu, và không dùng `period.getMonths()` như tổng số tháng.

Nếu cần lấy ngày hôm nay trong code production, có thể truyền `Clock` vào service rồi lấy ngày theo ZoneId phù hợp. Khi test, ưu tiên ngày cố định thay vì `LocalDate.now()` để kết quả không thay đổi theo thời điểm chạy.

## 5. Tháng trọn vẹn khác phép cộng một tháng

Một bẫy thường gặp với ngày cuối tháng:

~~~java
LocalDate jan31 = LocalDate.of(2024, 1, 31);
LocalDate feb29 = LocalDate.of(2024, 2, 29);

long wholeMonths = ChronoUnit.MONTHS.between(jan31, feb29); // 0
LocalDate next = jan31.plusMonths(1);                     // 2024-02-29
Period calendar = Period.between(jan31, feb29);          // P29D
~~~

`plusMonths(1)` điều chỉnh **31/01 thành 29/02** trong năm nhuận vì tháng 2 không có ngày 31. Nhưng `MONTHS.between(31/01,29/02)` chưa tính được một **tháng hoàn chỉnh theo quy tắc so ngày trong tháng**, nên kết quả là **0**. `Period.between` biểu diễn khoảng này là 29 ngày.

Do đó, **`plusMonths` và `MONTHS.between` không phải hai phép nghịch đảo hoàn hảo trên mọi ngày**. Với kỳ trả lương, hợp đồng gia hạn hoặc tuổi theo “tròn tháng”, phải định nghĩa rõ quy tắc ngày cuối tháng.

Ví dụ khoảng dài:

~~~java
LocalDate from = LocalDate.of(2024, 1, 15);
LocalDate to = LocalDate.of(2025, 3, 18);

long fullMonths = ChronoUnit.MONTHS.between(from, to); // 14
Period parts = Period.between(from, to);              // P1Y2M3D
~~~

`parts.getYears()` là 1, `getMonths()` là 2, `getDays()` là 3. **`getMonths()` không phải tổng số tháng giữa hai mốc**, cũng như `getDays()` không phải tổng số ngày giữa chúng. Khi cần tổng ngày thực tế trong lịch, dùng `ChronoUnit.DAYS.between(from,to)`.

**Không dùng 365 ngày làm một năm hoặc 30 ngày làm một tháng.** Năm nhuận và độ dài tháng thay đổi; `ChronoUnit.YEARS`/`MONTHS` dùng quy tắc lịch trọn vẹn chứ không phải phép chia cho số ngày trung bình.

## 6. Period.between: một khoảng lịch ISO

`Period.between(LocalDate startDateInclusive, LocalDate endDateExclusive)` tính khoảng thời gian theo **năm, tháng, ngày của lịch ISO**.

~~~java
Period p = Period.between(
        LocalDate.of(2024, 1, 15),
        LocalDate.of(2025, 3, 18));

System.out.println(p); // P1Y2M3D
~~~

Hai cách viết tương ứng trên `LocalDate`:

~~~java
Period p1 = Period.between(startDate, endDate);
Period p2 = startDate.until(endDate);
~~~

Khác với `Duration`, một `Period.ofMonths(1)` **không phải số giây cố định**. Tùy ngày bắt đầu, một tháng lịch có 28/29/30/31 ngày; khi gắn với một vùng có DST, số giờ thực tế lại có thể thay đổi.

`Period` không tự biết “ngày làm việc” hay ngày nghỉ lễ. Nếu cần tính 5 ngày làm việc, phải có lịch kinh doanh, quy tắc cuối tuần, ngày nghỉ và vùng phù hợp.

### 6.1. Cộng Period trên ZonedDateTime

~~~java
ZonedDateTime meeting = ZonedDateTime.of(
        2024, 3, 9, 12, 0, 0, 0,
        ZoneId.of("America/New_York"));

ZonedDateTime plusCalendar = meeting.plus(Period.ofDays(2));
ZonedDateTime plusElapsed = meeting.plus(Duration.ofHours(48));
~~~

Trong khoảng đổi sang giờ mùa hè, `plusCalendar` đi tới **12:00 ngày 11/03** theo giờ địa phương, còn `plusElapsed` đi tới **13:00 ngày 11/03** vì cộng đúng 48 giờ đã trôi. Đây là hai yêu cầu lịch khác nhau. Không dùng Duration 48 giờ để thay hai ngày dân sự nếu sản phẩm cần giữ cùng giờ đồng hồ.

## 7. Duration.between: thời gian dựa trên seconds và nanos

`Duration.between(start, end)` trả một `Duration`, không trả số tháng hoặc năm. Nó hữu ích khi đo khoảng trên trục thời gian:

~~~java
Instant start = Instant.parse("2024-01-01T00:00:00Z");
Instant end = Instant.parse("2024-01-01T01:30:00Z");

Duration elapsed = Duration.between(start, end); // PT1H30M
long fullHours = ChronoUnit.HOURS.between(start, end); // 1
~~~

Một Duration có thể âm nếu end sớm hơn start. `Duration.toHours()` và `toMinutes()` cũng cung cấp **số lượng đơn vị nguyên**; nếu cần thành phần chi tiết, dùng `toHoursPart()`/`toMinutesPart()` hoặc tính phù hợp theo các thành phần giây/nano.

### 7.1. LocalDateTime không tự có múi giờ

~~~java
LocalDateTime a = LocalDateTime.of(2024, 1, 1, 11, 30);
LocalDateTime b = LocalDateTime.of(2024, 1, 1, 13, 29);

Duration localDifference = Duration.between(a, b); // PT1H59M
~~~

Đây là phép đo trên **ngày-giờ địa phương không có ZoneId**. Nó không tự biết khu vực nào đã đổi DST. Khi cần thời gian thực tế giữa hai mốc ở một thành phố, hãy chọn ZoneId và diễn giải giờ địa phương thành `ZonedDateTime`/`Instant` trước khi tính.

### 7.2. Duration.between không dùng trực tiếp cho LocalDate

`Duration` cần temporal hỗ trợ đơn vị giây. `LocalDate` không có seconds:

~~~java
LocalDate a = LocalDate.of(2024, 1, 1);
LocalDate b = LocalDate.of(2024, 1, 2);

// Duration.between(a, b); // UnsupportedTemporalTypeException
long days = ChronoUnit.DAYS.between(a, b); // 1
Period p = Period.between(a, b);          // P1D
~~~

Không thêm giả định “00:00 UTC” vào ngày thuần túy để ép tạo Duration nếu nghiệp vụ chưa quy định múi giờ. Dùng ngày lịch hoặc yêu cầu thêm thông tin thời điểm.

## 8. DST: hai ngày lịch có thể không dài 48 giờ

Với `America/New_York` năm 2024:

~~~java
ZoneId ny = ZoneId.of("America/New_York");

ZonedDateTime from = ZonedDateTime.of(
        2024, 3, 9, 12, 0, 0, 0, ny);
ZonedDateTime to = ZonedDateTime.of(
        2024, 3, 11, 12, 0, 0, 0, ny);

long calendarDays = ChronoUnit.DAYS.between(from, to); // 2
long elapsedHours = ChronoUnit.HOURS.between(from, to); // 47
Duration realElapsed = Duration.between(from, to);     // PT47H
~~~

Tại cuối tuần đó, đồng hồ chuyển sang DST, “mất” một giờ. Từ 12:00 ngày 9 tới 12:00 ngày 11 là **hai ngày trên lịch**, nhưng chỉ **47 giờ thực tế**.

Ở chiều đổi từ DST về giờ chuẩn:

~~~java
ZonedDateTime a = ZonedDateTime.of(
        2024, 11, 2, 12, 0, 0, 0, ny);
ZonedDateTime b = ZonedDateTime.of(
        2024, 11, 4, 12, 0, 0, 0, ny);

long days = ChronoUnit.DAYS.between(a, b);  // 2
long hours = ChronoUnit.HOURS.between(a, b); // 49
~~~

Các đoạn trên là **mảnh minh họa trong những scope riêng**, cần import `java.time.*` và `java.time.temporal.*`.

### 8.1. Vì sao cùng một API có thể trả số ngày khác?

`ZonedDateTime.until` tính:

- **Date-based unit** như `DAYS`, `MONTHS`: theo **local timeline**, phản ánh ngày-giờ tại vùng.
- **Time-based unit** như `HOURS`, `SECONDS`: theo **instant timeline**, phản ánh thời lượng thực tế đã trôi qua.

Nếu chuyển hai ZonedDateTime mùa xuân ở trên sang Instant:

~~~java
long daysFromZoned = ChronoUnit.DAYS.between(from, to); // 2

long daysFromInstant = ChronoUnit.DAYS.between(
        from.toInstant(), to.toInstant()); // 1

long hoursFromLocal = ChronoUnit.HOURS.between(
        from.toLocalDateTime(), to.toLocalDateTime()); // 48

long hoursFromInstant = ChronoUnit.HOURS.between(
        from.toInstant(), to.toInstant()); // 47
~~~

**Không có mâu thuẫn**. Trên Instant, `DAYS` tương ứng các khối **24 giờ**: 47 giờ chỉ chứa một khối 24 giờ hoàn chỉnh. Trên ZonedDateTime, `DAYS` là số ngày trọn vẹn của local timeline. Trên LocalDateTime, hai giờ tường cách nhau 48 giờ vì thông tin DST bị lược bỏ.

### 8.2. Cẩn thận khi dùng hai ZonedDateTime ở vùng khác nhau

Theo hợp đồng `ZonedDateTime.until`, nếu mốc cuối khác zone, nó được chuẩn hóa về zone của mốc đầu trước khi tính. Nếu phải đo **giờ thực tế**, chuyển cả hai thành Instant là cách diễn đạt rõ:

~~~java
Duration elapsed = Duration.between(
        first.toInstant(), second.toInstant());
~~~

Nếu phải đo **ngày lịch**, trước tiên hãy chọn vùng theo nghiệp vụ, rồi chuyển cả hai mốc sang cùng ZoneId bằng `withZoneSameInstant` và đo `DAYS`. Đừng để zone ngầm của máy chủ quyết định một vấn đề cần nhất quán.

## 9. Những trường hợp API không hỗ trợ

Không phải mọi unit đều phù hợp với mọi kiểu:

~~~java
LocalDate from = LocalDate.of(2024, 2, 28);
LocalDate to = LocalDate.of(2024, 3, 1);

// Sai: ChronoUnit.HOURS.between(from, to);
// Sai: Duration.between(from, to);

boolean canMeasureHours = from.isSupported(ChronoUnit.HOURS);
// false
~~~

Hai lời gọi sai trong comment sẽ phát sinh `UnsupportedTemporalTypeException` nếu thực thi. Nếu đầu vào không có giờ, không thể xác định tổng số giờ thực tế một cách trung thực.

**Các lỗi nên chủ động kiểm:**

- Unit không được hỗ trợ: `UnsupportedTemporalTypeException`.
- Hai temporal không tương thích hoặc không thể đổi kiểu: `DateTimeException`.
- Khoảng quá lớn khi đo đơn vị nhỏ: `ArithmeticException` do overflow.
- Input/null không hợp lệ: exception tùy API, cần validation hợp đồng trước.
- Mốc cuối trước mốc đầu: kết quả âm có ý nghĩa, không tự động lỗi.

`ChronoUnit.between` trả `long`; không ép về int nếu dữ liệu lịch rất dài có thể vượt 2,147,483,647 đơn vị. Với nano giây, ngay cả khoảng nhỏ hơn nhiều so với năm có thể khiến long tràn ở mốc rất xa.

## 10. Tình huống nghiệp vụ: chọn API theo câu hỏi

### 10.1. Số đêm lưu trú

~~~java
LocalDate checkIn = LocalDate.parse("2024-07-01");
LocalDate checkOut = LocalDate.parse("2024-07-04");

long nights = ChronoUnit.DAYS.between(checkIn, checkOut); // 3
~~~

Đây là số đêm từ ngày nhận phòng đến trước ngày trả phòng. Nếu checkout trước checkin, nên báo lỗi hơn là lấy `Math.abs` che sai thứ tự. Nếu cùng ngày, chính sách sản phẩm quyết định được hay không.

### 10.2. Tuổi tính bằng năm trọn vẹn

~~~java
LocalDate birth = LocalDate.parse("2000-06-10");
LocalDate asOf = LocalDate.parse("2024-06-09");

long completeYears = ChronoUnit.YEARS.between(birth, asOf); // 23
~~~

Nếu ngày sinh 29/02, một số chính sách pháp lý có quy định ngày kỷ niệm khác nhau trong năm không nhuận; `ChronoUnit.YEARS` thể hiện phép đo lịch ISO, không thay mọi quy định địa phương.

### 10.3. Độ trễ API và TTL

~~~java
Instant created = Instant.parse("2024-01-01T00:00:00Z");
Instant expires = created.plus(Duration.ofMinutes(90));

Duration ttl = Duration.between(created, expires); // PT1H30M
~~~

Với timeout/TTL cần **90 phút thực tế**, dùng Instant và Duration. Với lịch gửi thông báo “09:00 hằng ngày tại New York”, dùng `LocalTime`/`ZoneId` và quy tắc lịch — không cố thay thế lịch hằng ngày bằng một khoảng 24 giờ cố định.

Khi cần đo **thời gian chạy bên trong một process** theo đồng hồ monotonic, có thể cân nhắc `System.nanoTime()` để tránh thay đổi wall clock; với các mốc đã lưu cần so sánh xuyên máy, dùng Instant cùng chính sách đồng bộ thời gian.

### 10.4. Thời hạn hợp đồng cuối tháng

~~~java
LocalDate signedAt = LocalDate.of(2024, 1, 31);
LocalDate nextBillDate = signedAt.plusMonths(1); // 2024-02-29

long elapsedFullMonths =
        ChronoUnit.MONTHS.between(signedAt, nextBillDate); // 0
~~~

Đây là hai ngữ nghĩa khác nhau. Quy tắc “ngày thanh toán tiếp theo là ngày cuối tháng nếu không có ngày tương ứng” được giải quyết bằng phép cộng lịch; đo “đã qua trọn tháng theo ChronoUnit” là câu hỏi khác. Hãy lưu chính sách trong đặc tả sản phẩm và test cuối tháng/năm nhuận.

### 10.5. Ngày làm việc không phải ngày lịch

Từ thứ Sáu đến thứ Hai có ba ngày lịch theo nhiều cặp mốc nhưng không đồng nghĩa ba ngày **làm việc**. Nếu cần ngày làm việc, hãy bổ sung quy tắc cuối tuần, ngày nghỉ và ZoneId/địa điểm; `ChronoUnit.DAYS` không biết lịch nghỉ của doanh nghiệp.

## 11. Chương trình Java hoàn chỉnh đã kiểm chứng

Tạo file **`BetweenUntilDemo.java`**. Chương trình dưới đây chạy trên JDK 17+ và chỉ dùng `java.time` có từ Java 8, không cần thư viện ngoài. Các mốc thời gian đều cố định nên stdout không phụ thuộc thời điểm chạy hay múi giờ mặc định của máy.

~~~java
import java.time.*;
import java.time.temporal.*;

public class BetweenUntilDemo {
    public static void main(String[] args) {
        LocalDate from = LocalDate.of(2024, 2, 28);
        LocalDate to = LocalDate.of(2024, 3, 1);
        System.out.println("Leap days: "
                + ChronoUnit.DAYS.between(from, to));
        System.out.println("Until DAYS: "
                + from.until(to, ChronoUnit.DAYS));
        System.out.println("Reverse days: "
                + ChronoUnit.DAYS.between(to, from));
        System.out.println("Nine days in weeks: "
                + ChronoUnit.WEEKS.between(
                        LocalDate.of(2024, 1, 1),
                        LocalDate.of(2024, 1, 10)));

        LocalDate jan31 = LocalDate.of(2024, 1, 31);
        LocalDate feb29 = LocalDate.of(2024, 2, 29);
        System.out.println("Full months Jan31-Feb29: "
                + ChronoUnit.MONTHS.between(jan31, feb29));
        System.out.println("One calendar month added: "
                + jan31.plusMonths(1));
        System.out.println("Period Jan31-Feb29: "
                + Period.between(jan31, feb29));

        LocalDate yStart = LocalDate.of(2024, 1, 15);
        LocalDate yEnd = LocalDate.of(2025, 3, 18);
        System.out.println("Whole months: "
                + ChronoUnit.MONTHS.between(yStart, yEnd));
        System.out.println("Calendar period: "
                + Period.between(yStart, yEnd));

        LocalDateTime t1 = LocalDateTime.of(2024, 1, 1, 11, 30);
        LocalDateTime t2 = LocalDateTime.of(2024, 1, 1, 13, 29);
        System.out.println("Complete hours: "
                + ChronoUnit.HOURS.between(t1, t2));
        System.out.println("Complete minutes: "
                + t1.until(t2, ChronoUnit.MINUTES));
        System.out.println("Reverse hours: "
                + ChronoUnit.HOURS.between(t2, t1));
        System.out.println("Duration: "
                + Duration.between(t1, t2));

        ZoneId ny = ZoneId.of("America/New_York");
        ZonedDateTime springStart =
                ZonedDateTime.of(2024, 3, 9, 12, 0, 0, 0, ny);
        ZonedDateTime springEnd =
                ZonedDateTime.of(2024, 3, 11, 12, 0, 0, 0, ny);
        System.out.println("Spring date-based DAYS: "
                + ChronoUnit.DAYS.between(springStart, springEnd));
        System.out.println("Spring elapsed HOURS: "
                + ChronoUnit.HOURS.between(springStart, springEnd));
        System.out.println("Spring Duration: "
                + Duration.between(springStart, springEnd));
        System.out.println("Spring instant DAYS: "
                + ChronoUnit.DAYS.between(
                        springStart.toInstant(), springEnd.toInstant()));
        System.out.println("Spring local HOURS: "
                + ChronoUnit.HOURS.between(
                        springStart.toLocalDateTime(),
                        springEnd.toLocalDateTime()));

        ZonedDateTime fallStart =
                ZonedDateTime.of(2024, 11, 2, 12, 0, 0, 0, ny);
        ZonedDateTime fallEnd =
                ZonedDateTime.of(2024, 11, 4, 12, 0, 0, 0, ny);
        System.out.println("Fall date-based DAYS: "
                + ChronoUnit.DAYS.between(fallStart, fallEnd));
        System.out.println("Fall elapsed HOURS: "
                + ChronoUnit.HOURS.between(fallStart, fallEnd));

        System.out.println("DAYS estimated: "
                + ChronoUnit.DAYS.isDurationEstimated());
        System.out.println("HOURS estimated: "
                + ChronoUnit.HOURS.isDurationEstimated());
        System.out.println("Nominal day duration: "
                + ChronoUnit.DAYS.getDuration());
        System.out.println("LocalDate supports HOURS: "
                + from.isSupported(ChronoUnit.HOURS));

        try {
            ChronoUnit.HOURS.between(from, to);
        } catch (UnsupportedTemporalTypeException expected) {
            System.out.println("HOURS on LocalDate rejected");
        }
        try {
            Duration.between(from, to);
        } catch (UnsupportedTemporalTypeException expected) {
            System.out.println("Duration on LocalDate rejected");
        }
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac -encoding UTF-8 BetweenUntilDemo.java
java BetweenUntilDemo
~~~

Stdout đã kiểm tra:

~~~text
Leap days: 2
Until DAYS: 2
Reverse days: -2
Nine days in weeks: 1
Full months Jan31-Feb29: 0
One calendar month added: 2024-02-29
Period Jan31-Feb29: P29D
Whole months: 14
Calendar period: P1Y2M3D
Complete hours: 1
Complete minutes: 119
Reverse hours: -1
Duration: PT1H59M
Spring date-based DAYS: 2
Spring elapsed HOURS: 47
Spring Duration: PT47H
Spring instant DAYS: 1
Spring local HOURS: 48
Fall date-based DAYS: 2
Fall elapsed HOURS: 49
DAYS estimated: true
HOURS estimated: false
Nominal day duration: PT24H
LocalDate supports HOURS: false
HOURS on LocalDate rejected
Duration on LocalDate rejected
~~~

**Giải thích từng nhóm kết quả:**

1. `Leap days: 2`, `Until DAYS: 2` chứng minh hai phương thức trả giống nhau; đảo chiều cho `Reverse days: -2`.
2. `Nine days in weeks: 1` đếm **một tuần trọn vẹn** trong 9 ngày.
3. `Full months Jan31-Feb29: 0` và `One calendar month added: 2024-02-29` minh họa khác nhau giữa đo tháng trọn vẹn và cộng một tháng lịch.
4. `Period Jan31-Feb29: P29D`; `Whole months: 14` và `Calendar period: P1Y2M3D` phân biệt tổng unit với các thành phần lịch.
5. `Complete hours: 1`, `Complete minutes: 119` và `Duration: PT1H59M` minh họa phần dư của đơn vị.
6. `Spring date-based DAYS: 2` khác `Spring elapsed HOURS: 47` và `Spring instant DAYS: 1` do DST. `Spring local HOURS: 48` minh họa dữ liệu LocalDateTime thiếu thông tin vùng.
7. `Fall elapsed HOURS: 49` khi đồng hồ lùi một giờ.
8. `DAYS estimated: true` nhưng `Nominal day duration: PT24H` vì ngày lịch có thể dài không đúng 24 giờ.
9. `LocalDate supports HOURS: false` và hai dòng rejected minh họa kiểm unit, tránh ép LocalDate vào phép đo giây.

Dữ liệu New York cố định theo những ngày chuyển DST năm 2024 để kiểm chính xác. Không suy ra quy tắc DST sẽ bất biến trong mọi năm tương lai; dữ liệu vùng có thể được cập nhật theo luật.

## 12. Kiểm thử các bất biến cần thiết

| Tình huống | Kết quả kỳ vọng |
|---|---|
| Cùng hai ngày | `DAYS.between` trả 0 |
| Từ trước tới sau | Kết quả dương theo số unit trọn vẹn |
| Đảo hai mốc | Kết quả âm |
| Đo 1 giờ 59 phút theo HOURS | Chỉ 1 giờ trọn vẹn |
| Đo 9 ngày theo WEEKS | 1 tuần trọn vẹn |
| Qua năm nhuận 2024 | Đếm ngày 29/02 chính xác |
| Từ 31/01 tới 29/02/2024 | `MONTHS.between` 0; `plusMonths(1)` tới 29/02 |
| `LocalDate.until(end)` | Trả `Period` |
| `LocalDate.until(end, DAYS)` | Trả `long` |
| `Duration.between` với LocalDate | Bị từ chối, không có seconds |
| `HOURS.between` với LocalDate | `UnsupportedTemporalTypeException` |
| Hai ngày lịch qua DST mùa xuân ở New York | `DAYS` trên ZonedDateTime = 2, `HOURS` = 47 |
| Hai ngày lịch qua DST mùa thu ở New York | `DAYS` = 2, `HOURS` = 49 |
| `DAYS` trên hai Instant cách nhau 47h | 1 khối 24 giờ trọn vẹn |
| Giá trị đầu vào không cùng kiểu và không tương thích | Lỗi rõ ràng hoặc conversion được tài liệu hóa |
| Chênh lệch rất lớn đo nano giây | Cần kiểm overflow long |
| Yêu cầu ngày làm việc | Có lịch nghỉ/cuối tuần riêng |

Một test cho tính tương đương:

~~~java
LocalDate a = LocalDate.of(2024, 2, 28);
LocalDate b = LocalDate.of(2024, 3, 1);

long x = ChronoUnit.DAYS.between(a, b);
long y = a.until(b, ChronoUnit.DAYS);

if (x != y || x != 2) {
    throw new AssertionError("Wrong number of days");
}
~~~

Với test ngày giờ, dùng **mốc cố định** thay vì `LocalDate.now()` hoặc `ZoneId.systemDefault()` khi muốn output xác định. Nếu cần “bây giờ” trong production, truyền `Clock` vào service và dùng `Clock.fixed(...)` trong test.

Đối với DST, test cả **giờ trên đồng hồ** và **Instant thực tế**; chỉ nhìn một con số DAYS có thể bỏ sót sai số thời lượng. Khi kiểm thuật toán ngày làm việc, dùng bộ dữ liệu ngày nghỉ được kiểm soát bởi chính ứng dụng, không mong java.time tự hiểu lịch địa phương.

## 13. Lỗi thường gặp

**1. Cho rằng between đếm cả hai ngày đầu và cuối.** API dùng start-inclusive/end-exclusive, còn cách đếm ngày tham gia là một quy tắc nghiệp vụ riêng.

**2. Coi between trả phần lẻ.** Nó trả long số đơn vị trọn vẹn; 1 giờ 59 phút tính HOURS là 1.

**3. Nhầm hai overload của LocalDate.until.** Có unit trả long; không có unit trả Period.

**4. Dùng Duration cho hai LocalDate.** LocalDate không hỗ trợ giây; dùng DAYS hoặc Period.

**5. Quy đổi tháng bằng số ngày chia 30.** Số ngày mỗi tháng khác nhau, tháng theo lịch cần ChronoUnit.MONTHS/Period.

**6. Tin plusMonths là nghịch đảo tuyệt đối của MONTHS.between.** Cuối tháng có thể được điều chỉnh; 31/01 → 29/02 khác phép đo tháng trọn vẹn.

**7. Dùng Period.getMonths() như tổng mọi tháng.** P1Y2M3D có thành phần months=2, còn số tháng trọn vẹn tổng cộng có thể là 14.

**8. Coi một ngày ZonedDateTime luôn đúng 24 giờ.** DST có thể khiến ngày lịch dài 23/25 giờ.

**9. Coi LocalDateTime là UTC instant.** Nó không có ZoneId hoặc offset, không tự phản ánh DST.

**10. Đo ngày lịch bằng DAYS.between trên Instant.** Instant đếm khối 24 giờ; ZonedDateTime có thể đếm ngày lịch theo vùng.

**11. Tự dùng ZoneId.systemDefault() để giải thích giờ của mọi người dùng.** Server có thể ở múi giờ khác; truyền ZoneId đúng nghiệp vụ.

**12. Dùng MONTHS.between với Instant.** Instant không có lịch vùng để đo tháng.

**13. Nghĩ DAYS.getDuration()=PT24H bảo đảm mọi ngày lịch 24h.** Date-based units có độ dài ước lượng.

**14. Không kiểm giá trị âm.** Với deadline, end trước start có thể là lỗi; không tự gọi abs để che sai thứ tự.

**15. Dùng ChronoUnit.DAYS cho ngày làm việc.** Nó không trừ cuối tuần hay lễ.

**16. Trộn Period và Duration như hai kiểu cùng ý nghĩa.** Một kiểu theo lịch, một kiểu theo thời lượng giây.

**17. Không kiểm unit có được hỗ trợ.** LocalDate không có HOURS, Instant không có MONTHS; phải chọn kiểu đúng.

**18. Quên overflow khi trả long hoặc ép sang int.** Với khoảng rất lớn và unit rất nhỏ, ArithmeticException hoặc tràn khi ép kiểu có thể xảy ra.

## 14. Bài tập tự luyện

1. `DAYS.between(2024-02-28,2024-03-01)` bằng mấy? Khi đổi thứ tự?
2. Tại sao `HOURS.between(11:30,13:29)` bằng 1, nhưng `MINUTES.between` bằng 119?
3. Với ngày 31/01 và 29/02/2024, `MONTHS.between` bằng mấy? `plusMonths(1)` trả ngày nào?
4. `Period.between(2024-01-15,2025-03-18)` biểu diễn thế nào? `getMonths()` bằng tổng số tháng chưa?
5. `start.until(end)` và `start.until(end,ChronoUnit.DAYS)` trả cùng kiểu hay khác kiểu?
6. Vì sao `Duration.between(LocalDate,LocalDate)` không phù hợp?
7. Tại New York, hai ngày lịch từ 12:00 ngày 09/03/2024 tới 12:00 ngày 11/03/2024 cách nhau bao nhiêu giờ thực tế?
8. Đổi hai ZonedDateTime của câu 7 sang Instant rồi đo DAYS, được mấy?
9. Khoảng qua DST mùa thu từ 02/11 tới 04/11/2024 tại New York, cùng giờ 12:00, bao nhiêu giờ?
10. Khi cần đúng 48 giờ chờ, nên dùng Period 2 ngày hay Duration 48 giờ?
11. Khi muốn luôn gửi thông báo lúc 09:00 địa phương, dùng kiểu nào?
12. `ChronoUnit.DAYS.isDurationEstimated()` là true mà `getDuration()` là PT24H có mâu thuẫn không?
13. Tính ngày làm việc có thể chỉ dùng `DAYS.between` không?
14. Nêu hai phép đo unsupported với `LocalDate` hoặc `Instant`.

**Đáp án gợi ý:** (1) 2 và -2. (2) Vì chỉ đếm đơn vị hoàn chỉnh. (3) 0 và 29/02/2024. (4) P1Y2M3D, getMonths là 2, không phải 14. (5) Khác: Period và long. (6) Thiếu thông tin giây. (7) 47 giờ. (8) 1 ngày theo 24 giờ. (9) 49 giờ. (10) Duration 48h. (11) LocalTime/LocalDate + ZoneId cùng chính sách DST. (12) Không, ngày lịch có thể dài 23/25 giờ. (13) Không, cần lịch làm việc/ngày nghỉ. (14) HOURS.between(LocalDate,LocalDate), MONTHS.between(Instant,Instant) hoặc Duration.between(LocalDate,LocalDate).

## Tổng kết

`ChronoUnit.between` và `Temporal.until(end,unit)` là hai cách tính **số unit hoàn chỉnh tương đương**. `LocalDate.until(end)` không truyền unit trả `Period`, còn `Duration.between` mô tả thời lượng theo seconds/nanos. Với ngày/tháng/năm lịch, ưu tiên `LocalDate` cùng `ChronoUnit`/`Period`. Với giây/giờ thực tế, ưu tiên `Instant`/`ZonedDateTime` cùng `Duration`. Qua DST, **ngày lịch không đồng nhất với một khoảng 24 giờ**, và tháng lịch không đồng nhất với 30 ngày. Thiết kế rõ yêu cầu, đầu vào và đơn vị rồi mới viết mã.

### Tài liệu chính thức, còn áp dụng

- [Oracle Java SE 27 — ChronoUnit](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/time/temporal/ChronoUnit.html)
- [Oracle Java SE 27 — TemporalUnit.between](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/time/temporal/TemporalUnit.html)
- [Oracle Java SE 27 — Temporal.until](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/time/temporal/Temporal.html)
- [Oracle Java SE 27 — LocalDate.until](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/time/LocalDate.html)
- [Oracle Java SE 27 — Period](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/time/Period.html)
- [Oracle Java SE 27 — Duration.between](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/time/Duration.html)
- [Oracle Java SE 27 — ZonedDateTime.until và DST](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/time/ZonedDateTime.html)
- [Oracle Java SE 27 — Instant](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/time/Instant.html)
