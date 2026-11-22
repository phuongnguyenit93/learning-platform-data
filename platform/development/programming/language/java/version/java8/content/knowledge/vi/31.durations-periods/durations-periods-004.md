# Phân biệt ngày lịch với 24 giờ trong Java: Period, Duration và múi giờ

## 1. Tư duy nền tảng: “một ngày” có ít nhất hai ý nghĩa

Trong lập trình Java, câu “cộng một ngày” dễ bị hiểu theo hai cách khác nhau:

1. **Một ngày lịch (calendar day)**: chuyển từ một ngày trên lịch địa phương sang **ngày kế tiếp**, thường giữ cùng giờ trên đồng hồ tại khu vực đó. Ví dụ nhân viên được hẹn **12:00 ngày mai theo giờ New York**, không phải “chính xác 86.400 giây nữa”.
2. **Một khoảng đúng 24 giờ đã trôi (elapsed duration)**: cộng **24 × 60 × 60 = 86.400 giây** trên trục thời gian, bất kể đồng hồ địa phương có đổi UTC offset trong khoảng này hay không. Ví dụ token hết hạn **chính xác 24 giờ từ thời điểm phát hành**.

Trong khu vực áp dụng **daylight saving time (DST)**, một ngày lịch dân sự có thể dài **23 giờ** khi đồng hồ nhảy tới, **25 giờ** khi đồng hồ lùi lại. Một số thay đổi quy tắc vùng còn có bước nhảy không tròn một giờ. Vì vậy, **“ngày lịch” không luôn đồng nghĩa “24 giờ thực trôi qua”**.

Các lớp trong `java.time` giúp diễn đạt đúng ý nghĩa:

- `LocalDate`: **ngày trên lịch** (năm/tháng/ngày), không lưu giờ và múi giờ.
- `Period`: lượng **năm/tháng/ngày lịch**, chẳng hạn `Period.ofDays(1)`.
- `Duration`: lượng **giây và nano giây đã trôi**, chẳng hạn `Duration.ofHours(24)`.
- `Instant`: **thời điểm trên timeline**, không gắn một giờ đồng hồ địa phương cố định.
- `ZoneId`: **khu vực cùng quy tắc offset theo ngày**, ví dụ `America/New_York`.
- `ZonedDateTime`: ngày và giờ cục bộ gắn với **quy tắc múi giờ khu vực**, nên phép cộng theo ngày và theo giờ có thể khác nhau.
- `LocalDateTime`: ngày/giờ **không có ZoneId**, do đó không thể biết một ngày thực tế ở khu vực ấy dài 23 hay 25 giờ.

Đây là API hiện hành kể từ Java 8, không phải kiến thức legacy. Toàn bộ chương trình chạy thử trong bài dùng **Java 17+**. Bài này giải quyết đúng trọng tâm **“Phân biệt ngày lịch với 24 giờ”** trong nhóm **“Khoảng thời gian”**, không biến thành một hướng dẫn chung về tất cả phương thức ngày giờ.

### Sau bài học bạn sẽ làm được

- Chọn `Period.ofDays(1)` hoặc `Duration.ofDays(1)` đúng ý nghĩa.
- Phân biệt `ZonedDateTime.plusDays(1)` với `plusHours(24)` và `plus(Duration.ofDays(1))`.
- Tính một **ngày lịch địa phương thực sự dài bao lâu** bằng ranh giới hai ngày trong `ZoneId`, thay vì mặc định 24 giờ.
- Biết `ChronoUnit.DAYS.between` tùy kiểu đầu vào, không đồng nhất kết quả với số lượng mốc 24 giờ.
- Giải các trường hợp **DST gap** (giờ không tồn tại) và **overlap** (giờ bị lặp), hiểu chính sách mặc định.
- Thiết kế thời hạn, giờ hẹn, kỳ tính phí, việc làm theo ngày và báo cáo theo lịch mà không nhầm với elapsed time.
- Viết test ổn định bằng dữ liệu cố định và `Clock.fixed(...)`, thay vì chỉ test trong những ngày bình thường.

## 2. Vì sao có ngày 23 giờ hoặc 25 giờ?

Nhiều vùng địa lý thay đổi độ lệch UTC theo mùa:

- **Khi bắt đầu giờ mùa hè (spring forward):** đồng hồ được đặt tiến lên. Một khoảng giờ địa phương bị bỏ qua; cùng một ngày lịch có thể chỉ dài **23 giờ**.
- **Khi kết thúc giờ mùa hè (fall back):** đồng hồ được đặt lùi lại. Một khoảng giờ địa phương lặp hai lần; cùng một ngày lịch có thể dài **25 giờ**.
- **Ngày không chuyển offset:** thường có **24 giờ** theo mô hình Java Time.

Ví dụ thực tế từ quy tắc của `America/New_York`:

| Ngày địa phương | Tình huống | Độ dài từ đầu ngày tới đầu ngày kế tiếp |
| --- | --- | ---: |
| 2024-03-09 | Trước khi nhảy giờ mùa xuân | 24 giờ |
| **2024-03-10** | Chuyển từ UTC-05:00 sang UTC-04:00 | **23 giờ** |
| 2024-03-11 | Sau thay đổi giờ | 24 giờ |
| **2024-11-03** | Chuyển từ UTC-04:00 về UTC-05:00 | **25 giờ** |
| 2024-11-04 | Sau thay đổi giờ | 24 giờ |

Những ngày trên là **mốc lịch sử cụ thể đã xảy ra**, không cần dự đoán quy tắc DST tương lai. Các hệ thống dùng bản tzdb/JDK khác nhau có thể cập nhật quy tắc khu vực, vì vậy các bài toán về ngày tương lai nên dùng `ZoneId` và quy tắc hiện hành của runtime, không hardcode ngày đổi giờ cho mọi năm.

Hình dung ngày chuyển xuân:

```text
New York, 2024-03-10
01:59:59 -05:00
        ↓ đồng hồ nhảy tới
03:00:00 -04:00

Giờ địa phương 02:00..02:59 không tồn tại.
Từ 00:00 của ngày 10 tới 00:00 ngày 11 = 23 giờ đã trôi.
```

Và ngày chuyển thu:

```text
New York, 2024-11-03
01:59:59 -04:00
        ↓ đồng hồ lùi lại
01:00:00 -05:00

Dải 01:00..01:59 xuất hiện hai lần với hai offset khác nhau.
Từ 00:00 ngày 3 tới 00:00 ngày 4 = 25 giờ đã trôi.
```

**Không suy diễn** mọi DST luôn lệch đúng một giờ. `java.time.zone.ZoneOffsetTransition` có thể mô tả chuyển đổi offset khác, và có vùng đã từng bỏ qua cả một ngày lịch. Kiến thức bền vững là: **độ dài ngày địa phương phải được tính từ quy tắc `ZoneId` và mốc cụ thể**.

## 3. `Period.ofDays(1)` không phải `Duration.ofDays(1)`

Hai biểu thức nhìn giống nhau nhưng diễn đạt **khác miền thời gian**:

```java
Period calendarDay = Period.ofDays(1);
Duration elapsedDay = Duration.ofDays(1);

System.out.println(calendarDay); // P1D
System.out.println(elapsedDay);  // PT24H
```

Trong `java.time`:

| Thuộc tính | `Period` | `Duration` |
| --- | --- | --- |
| Đơn vị nội bộ | Năm, tháng, ngày lịch | Giây và phần nano giây |
| Một “ngày” | Một bước ngày theo lịch | **86.400 giây** |
| Ví dụ | `Period.ofDays(1)` | `Duration.ofDays(1)`, tương đương `ofHours(24)` |
| Phù hợp | Ngày mai cùng giờ địa phương, kỳ theo lịch | TTL, timeout, elapsed time |
| Bị ảnh hưởng khi áp vào `ZonedDateTime` có DST | Có thể đổi UTC offset mà giữ ý nghĩa ngày địa phương | Giữ số giây đã trôi trên timeline |
| Một tháng | `Period.ofMonths(1)` có ý nghĩa lịch | Không có độ dài 1 tháng cố định bằng giây |

**Chi tiết API:** `Duration.ofDays(n)` được định nghĩa bằng **n × 86.400 giây**, không hỏi ngày địa phương nào đang xét. Ngược lại, `Period.ofDays(1)` chỉ mang ý nghĩa “1 ngày trong lịch”; để biết chính xác bao nhiêu giây trôi qua, cần áp nó vào một thời điểm có ngày và quy tắc múi giờ.

### 3.1. Cùng biểu diễn “1 ngày” nhưng khác kết quả khi áp vào ZonedDateTime

```java
ZoneId zone = ZoneId.of("America/New_York");
ZonedDateTime start = ZonedDateTime.of(
        2024, 3, 9, 12, 0, 0, 0, zone);

ZonedDateTime byCalendar = start.plus(Period.ofDays(1));
ZonedDateTime byElapsed = start.plus(Duration.ofDays(1));
```

Kết quả chính xác:

```text
start      = 2024-03-09T12:00-05:00[America/New_York]
byCalendar = 2024-03-10T12:00-04:00[America/New_York]
byElapsed  = 2024-03-10T13:00-04:00[America/New_York]
```

Cùng một ngày đích nhưng **giờ hiển thị khác nhau**. `byCalendar` giữ 12:00 ngày kế tiếp theo quy tắc vùng, nên chỉ cách start **23 giờ** trên timeline; `byElapsed` cách start đúng **24 giờ**, nên khi đồng hồ nhảy tới thì thành 13:00.

### 3.2. Một ngày lịch được xác định bởi loại lịch và vùng hiển thị

`Period` có ý nghĩa trong hệ lịch ISO (các class `LocalDate`, `ZonedDateTime` thông thường dùng lịch ISO). Một số lịch không ISO có kiểu ngày/lượng thời gian riêng trong `java.time.chrono`. Đừng coi “calendar day” là phép toán trên `Instant` không cần ngữ cảnh: `Instant` không mang ngày lịch địa phương.

Dùng `Period.ofDays(1)` không tự gắn múi giờ; chỉ khi cộng vào kiểu có ngày/giờ phù hợp mới có kết quả theo lịch.

## 4. `ZonedDateTime.plusDays(1)` và `plusHours(24)` là hai phép khác nhau

`ZonedDateTime` có hai “trục” quan trọng:

- **Local timeline:** ngày và giờ mà người sống ở khu vực đó nhìn trên đồng hồ.
- **Instant timeline:** thời gian tuyệt đối sau khi đã xét UTC offset.

Theo hợp đồng `ZonedDateTime`, các thao tác **theo ngày** như `plusDays` hoạt động trên local timeline; các thao tác **theo giờ** như `plusHours` hoạt động trên instant timeline.

Giả sử ở New York:

```java
ZonedDateTime spring = ZonedDateTime.of(
        2024, 3, 9, 12, 0, 0, 0,
        ZoneId.of("America/New_York"));

ZonedDateTime calendarNext = spring.plusDays(1);
ZonedDateTime exactly24h = spring.plusHours(24);
```

Kết quả:

```text
spring       = 2024-03-09T12:00-05:00[America/New_York]
calendarNext = 2024-03-10T12:00-04:00[America/New_York]
exactly24h   = 2024-03-10T13:00-04:00[America/New_York]
```

Bảng so sánh:

| Ý định | Câu lệnh nên dùng | Vì sao |
| --- | --- | --- |
| “Ngày mai **cùng giờ đồng hồ** theo New York” | `spring.plusDays(1)` | Cộng ngày lịch theo zone |
| “Chính xác **24 giờ nữa**” | `spring.plusHours(24)` | Giữ đúng elapsed 86.400 giây |
| “Một `Period` theo ngày lịch” | `spring.plus(Period.ofDays(1))` | Tương đương ý nghĩa `plusDays(1)` |
| “Một `Duration` 24 giờ” | `spring.plus(Duration.ofDays(1))` | Tương đương elapsed 24 giờ |
| “Thời điểm tuyệt đối sau 24 giờ” | `spring.toInstant().plus(Duration.ofHours(24))` | Nêu rõ timeline tuyệt đối |

**Cảnh báo quan trọng:** `ZonedDateTime.plus(1, ChronoUnit.DAYS)` là cộng theo ngày lịch, còn `plus(24, ChronoUnit.HOURS)` là cộng thời lượng 24 giờ. Việc `ChronoUnit.DAYS.getDuration()` có giá trị ước lượng 24 giờ **không** biến ngày lịch thành 24 giờ ở mọi khu vực.

### 4.1. Ngày chuyển thu: kết quả đảo chiều

Bắt đầu từ `2024-11-02 12:00` tại New York:

```java
ZonedDateTime fall = ZonedDateTime.of(
        2024, 11, 2, 12, 0, 0, 0,
        ZoneId.of("America/New_York"));

ZonedDateTime calendarNext = fall.plusDays(1);
ZonedDateTime exactly24h = fall.plusHours(24);
```

Kết quả:

```text
fall         = 2024-11-02T12:00-04:00[America/New_York]
calendarNext = 2024-11-03T12:00-05:00[America/New_York]
exactly24h   = 2024-11-03T11:00-05:00[America/New_York]
```

Lần này `calendarNext` cách `fall` **25 giờ** vì đồng hồ địa phương lùi lại một giờ. Cộng **đúng 24 giờ** cho kết quả 11:00 ngày hôm sau, sớm hơn “cùng giờ đồng hồ” một tiếng.

### 4.2. Với giờ trong gap hoặc overlap, plusDays có thể điều chỉnh local time

Nói `plusDays(1)` “giữ nguyên giờ” là mô tả mục tiêu **thường gặp**, không phải lời hứa tuyệt đối khi giờ đích **không tồn tại**. Nếu cộng ngày khiến local time rơi vào gap, `ZonedDateTime` điều chỉnh tiến tới thời điểm hợp lệ; khi rơi vào overlap, nó cố giữ offset trước đó nếu hợp lệ, nếu không thường chọn offset sớm hơn theo hợp đồng.

Do đó, một cuộc hẹn “02:30 mỗi ngày” tại nơi có DST phải xác định **policy**: bỏ lượt, dời giờ, hoặc quy tắc giải khác. Chỉ gọi `plusDays(1)` rồi tin giờ luôn giữ được là chưa đủ cho mọi nghiệp vụ.

## 5. Đếm ngày lịch khác tính số giờ đã trôi

Đây là trường hợp rất dễ đánh lừa test:

```java
ZonedDateTime start = ZonedDateTime.of(
        2024, 3, 9, 12, 0, 0, 0,
        ZoneId.of("America/New_York"));
ZonedDateTime next = start.plusDays(1);

long calendarDays = ChronoUnit.DAYS.between(start, next); // 1
long elapsedHours = Duration.between(start, next).toHours(); // 23
```

`ChronoUnit.DAYS.between(start, next)` trên hai `ZonedDateTime` cùng zone dùng quy tắc đơn vị ngày theo **local timeline**; `Duration.between(start, next)` tính thời gian đã trôi dựa trên instant.

Khi đổi cả hai về `Instant`:

```java
long complete24hDays = ChronoUnit.DAYS.between(
        start.toInstant(), next.toInstant()); // 0
```

Vì mới trôi **23 giờ**, chưa đủ một đơn vị ngày 24h. Tên `DAYS` trong hai lời gọi giống nhau nhưng **temporal type khác nhau**, dẫn tới ngữ nghĩa khác khi có DST.

### 5.1. `ChronoUnit.DAYS.between(LocalDate, LocalDate)`

Với chỉ hai ngày, đếm ranh giới ngày là rõ nhất:

```java
LocalDate first = LocalDate.of(2024, 3, 9);
LocalDate second = LocalDate.of(2024, 3, 10);
long days = ChronoUnit.DAYS.between(first, second); // 1
```

Kết quả này **không chịu ảnh hưởng trực tiếp của DST** vì `LocalDate` không có zone. Nó trả số ngày lịch ISO giữa hai mốc, không phải số giờ của người dùng trong hai ngày ấy.

**Cẩn thận với tính “bao gồm cả hai đầu”:** `ChronoUnit.DAYS.between(first, second)` là khoảng cách ngày theo **ranh giới**, không tự cộng 1 cho tính inclusive. Ví dụ từ ngày 9 đến ngày 10 là khoảng cách **1 ngày**, nhưng nếu báo cáo “bao gồm cả ngày 9 và ngày 10” có thể có **2 ngày được liệt kê**. Hãy định nghĩa chính sách rõ trước khi tính.

### 5.2. Khi chỉ có LocalDateTime, không thể biết DST

```java
LocalDateTime first = LocalDateTime.of(2024, 3, 9, 12, 0);
LocalDateTime second = LocalDateTime.of(2024, 3, 10, 12, 0);

long hoursWithoutZone = Duration.between(first, second).toHours(); // 24
```

Kết quả là **24 giờ trong các trường ngày giờ cục bộ**, không chứng minh đã có 24 giờ trôi trên timeline New York. Sau khi gắn `ZoneId.of("America/New_York")` đúng theo quy tắc, cặp local time này tương ứng hai Instant cách nhau **23 giờ**.

Đây là lý do không lưu `LocalDateTime` đơn lẻ làm **thời điểm tuyệt đối** để tính timeout, deadline và SLA liên múi giờ.

### 5.3. `Duration.toDays()` không đếm ngày lịch

`Duration.toDays()` chuyển duration sang **số đơn vị 24 giờ trọn vẹn** theo phép chia giây; với duration 23 giờ, nó trả 0, không phải 1 ngày lịch. Với 25 giờ, nó trả 1 (còn dư 1 giờ). Không dùng `duration.toDays()` để đếm số ngày trên hóa đơn hoặc số lần chuyển ngày tại khu vực người dùng.

## 6. Tính độ dài thật của một ngày địa phương

Khi cần biết **ngày cụ thể ở một khu vực dài mấy giờ thực trôi**, cách dễ hiểu là tính từ **đầu ngày này** đến **đầu ngày kế tiếp** theo zone:

```java
static Duration actualCalendarDateLength(
        LocalDate date, ZoneId zone) {
    ZonedDateTime start = date.atStartOfDay(zone);
    ZonedDateTime next = date.plusDays(1).atStartOfDay(zone);
    return Duration.between(start.toInstant(), next.toInstant());
}
```

Đây là **phương thức minh họa** cần `import java.time.*;`. Đầu vào phải là ngày/zone hợp lệ; nếu `date.plusDays(1)` vượt phạm vi `LocalDate` có thể ném `DateTimeException`.

Với các ngày 2024 đã nêu:

```text
actualCalendarDateLength(2024-03-10, America/New_York) = PT23H
actualCalendarDateLength(2024-11-03, America/New_York) = PT25H
actualCalendarDateLength(2024-03-10, UTC)              = PT24H
```

**Đừng chỉ tính** `Duration.between(date.atStartOfDay(), date.plusDays(1).atStartOfDay())` vì hai `LocalDateTime` đó **không có zone**, nên luôn mô tả 24 giờ theo đồng hồ cục bộ kể cả khi một giờ bị nhảy qua.

### 6.1. `atStartOfDay(ZoneId)` không phải lúc nào cũng 00:00

`LocalDate.atStartOfDay(zone)` trả **thời điểm đầu tiên hợp lệ của ngày theo zone**, vốn có thể không đúng `00:00` nếu múi giờ chuyển offset ngay tại nửa đêm. Trong những trường hợp lịch sử hiếm gặp còn có các ngày bị bỏ qua do thay đổi múi giờ lớn.

Vì vậy, nếu yêu cầu lọc dữ liệu theo **ngày địa phương**, nên tính **hai ranh giới bằng zone rules**, không ghép chuỗi `"T00:00"` rồi áp một offset cố định một cách mù quáng.

### 6.2. Ranh giới ngày địa phương là một khoảng nửa mở

Định nghĩa phù hợp cho nhiều truy vấn event:

```text
[startOfDay(date, zone), startOfDay(date.plusDays(1), zone))
```

- **Bao gồm** đầu ngày.
- **Không bao gồm** đầu ngày kế tiếp.
- Tránh việc cùng một event nằm trong hai ngày khi ghép các khoảng liên tiếp.
- Không cần giả định “23:59:59.999999999” là điểm kết thúc hợp lệ trong mọi precision của DB.

Ví dụ lọc `Instant event`:

```java
LocalDate day = LocalDate.of(2024, 3, 10);
ZoneId zone = ZoneId.of("America/New_York");
Instant from = day.atStartOfDay(zone).toInstant();
Instant to = day.plusDays(1).atStartOfDay(zone).toInstant();

boolean inDay = !event.isBefore(from) && event.isBefore(to);
```

Đây là đoạn minh họa trong method với `Instant event` đã tồn tại. Không dùng `to = from.plus(Duration.ofDays(1))` để xác định ngày đích, vì vào ngày DST, `to` có thể là **01:00 của ngày sau** (ngày ngắn) hoặc **23:00 của cùng ngày** (ngày dài).

**Trường hợp ngày bị bỏ qua:** Nếu một vùng đã từng bỏ qua toàn bộ ngày dân sự, hai đầu khoảng có thể trùng nhau: khoảng của ngày đó là rỗng theo chính sách interval. Hệ thống cần xác định rõ có chấp nhận ngày bị bỏ qua hay không, thay vì tự giả định mọi `LocalDate` ở mọi ZoneId luôn có 24 giờ event.

## 7. Gap và overlap: một giờ địa phương có thể không tồn tại hoặc có hai Instant

`ZonedDateTime` và `ZoneId` phải xử lý các trường hợp khi giờ local không ánh xạ 1–1 tới Instant.

### 7.1. DST gap: giờ nhảy tới

Ở New York, `2024-03-10T02:30` không tồn tại. Kiểm tra:

```java
ZoneId ny = ZoneId.of("America/New_York");
LocalDateTime missing = LocalDateTime.of(2024, 3, 10, 2, 30);

int validOffsets = ny.getRules().getValidOffsets(missing).size();
// 0
```

Gọi:

```java
ZonedDateTime adjusted = missing.atZone(ny);
// 2024-03-10T03:30-04:00[America/New_York]
```

`LocalDateTime.atZone` áp quy tắc mặc định: local time trong gap được dịch tới thời điểm hợp lệ bằng độ dài gap. Đây là **quyết định mặc định của API**, không có nghĩa lịch hẹn 02:30 đã thực sự diễn ra lúc 03:30. Nếu ứng dụng cần từ chối lịch bất khả thi, hãy kiểm tra `ZoneRules.getValidOffsets(...)` hoặc dùng chính sách tạo zoned date-time phù hợp thay vì chấp nhận chuyển đổi mặc định.

### 7.2. DST overlap: một giờ xuất hiện hai lần

`2024-11-03T01:30` xảy ra hai lần:

```java
LocalDateTime repeated = LocalDateTime.of(2024, 11, 3, 1, 30);
List<ZoneOffset> offsets =
        ny.getRules().getValidOffsets(repeated);
// Có hai offset: -04:00 và -05:00
```

Tạo mặc định:

```java
ZonedDateTime earlier = repeated.atZone(ny);
// 2024-11-03T01:30-04:00[America/New_York]

ZonedDateTime later = earlier.withLaterOffsetAtOverlap();
// 2024-11-03T01:30-05:00[America/New_York]
```

Hai giá trị có **cùng LocalDateTime**, nhưng `earlier.toInstant()` sớm hơn `later.toInstant()` đúng một giờ. Nếu ứng dụng ghi log hoặc lập lịch tại thời điểm lặp lại, **phải quyết định chọn occurrence nào**, thay vì lưu mỗi chuỗi `"2024-11-03 01:30"`.

### 7.3. Khi nào dùng `ZoneOffset` cố định?

`ZoneOffset.ofHours(-5)` là offset cố định: không có quy tắc DST, do đó mỗi ngày theo mô hình đó thường dài đúng 24 giờ. Nhưng `America/New_York` có lúc dùng -05 và lúc dùng -04. Dùng fixed offset để biểu diễn lịch cửa hàng tại một thành phố có DST sẽ cho kết quả sai ngày đổi giờ.

**Quy tắc chọn:**
- Cần lịch dân sự theo **địa điểm** → `ZoneId` (region ID).
- Cần elapsed 24h kể từ timestamp → `Instant` + `Duration`, sau đó hiển thị tại zone nếu cần.
- Cần chuyển đổi một timestamp đã mang offset và không cần lịch khu vực → `OffsetDateTime` có thể phù hợp, nhưng offset cố định không thay thế ZoneId trong lịch tương lai.

## 8. Một tháng lịch thậm chí không có số ngày cố định

Sự khác biệt calendar period và elapsed duration không chỉ xảy ra ở DST. **Tháng có 28, 29, 30 hoặc 31 ngày**, vì vậy không thể viết “một tháng = 30 × 24 giờ” cho mọi tình huống.

Ví dụ:

```java
LocalDate jan31 = LocalDate.of(2024, 1, 31);
LocalDate nextMonth = jan31.plusMonths(1);
// 2024-02-29
```

Đây là hành vi hợp đồng của `LocalDate.plusMonths`: khi tháng đích không có ngày 31, kết quả được điều chỉnh về **ngày hợp lệ cuối cùng** của tháng. Trong năm không nhuận, tháng 2 thường kết thúc ngày 28.

So sánh:

```java
Period oneMonth = Period.ofMonths(1);
// Không có Duration.ofMonths(1) trong API chuẩn.
Duration thirtyDays = Duration.ofDays(30);
// Chính xác 30 × 86.400 giây, không phải “thêm một tháng lịch”.
```

Tương tự:

```java
LocalDate.of(2024, 2, 28).plusDays(1); // 2024-02-29
LocalDate.of(2025, 2, 28).plusDays(1); // 2025-03-01
```

Đây là lý do billing theo tháng nên dựa trên **LocalDate + Period/YearMonth + chính sách tháng cuối**, không giả định mọi chu kỳ 30 ngày hay 720 giờ.

### 8.1. “Ngày làm việc” không tự có trong Period.ofDays(1)

`Period.ofDays(1)` cộng **một ngày lịch** kể cả thứ Bảy, Chủ nhật và ngày nghỉ. Nó **không** có khái niệm “ngày làm việc của công ty”. Nếu nghiệp vụ yêu cầu “trước 2 ngày làm việc”, cần lịch ngày làm việc/ngày nghỉ riêng, kết hợp `LocalDate` và múi giờ liên quan.

Đừng tự chuyển “business day” thành một `Duration` 24h/48h — đó là khái niệm khác.

## 9. Các tình huống nghiệp vụ: chọn “ngày” hay “24 giờ” như thế nào?

| Tình huống | Ý nghĩa thường cần | Kiểu/thao tác gợi ý |
| --- | --- | --- |
| OTP/token hết hạn sau chính xác 24h | Elapsed time | `Instant issuedAt` + `Duration.ofHours(24)` |
| SLA “phải phản hồi trong 24 giờ” | Elapsed 24h nếu điều khoản nói thời gian thực | `Instant` / `Duration` |
| Lịch hẹn “12:00 ngày mai tại New York” | Ngày lịch và giờ địa phương | `ZonedDateTime.plusDays(1)` hoặc xây ngày đích bằng `LocalDate` |
| Báo cáo doanh thu ngày 10/3 theo giờ New York | Mọi event thuộc ngày dân sự | `LocalDate.atStartOfDay(zone)` cho hai biên |
| Hạn nộp “cuối ngày mai” ở địa điểm cụ thể | Ranh giới ngày lịch | Đầu ngày kế tiếp theo zone, dùng khoảng nửa mở |
| Duy trì job mỗi ngày lúc 08:00 theo giờ cửa hàng | Đồng hồ địa phương lặp lại | `LocalDate` + `LocalTime` + `ZoneId` và DST policy |
| Chạy job mỗi 24 giờ đều đặn | Elapsed 24h | `Instant`/`Duration` hoặc scheduler với fixed delay rõ |
| Thuê phòng tính theo “đêm” | Ngày lịch/check-in/check-out theo thỏa thuận | Đếm LocalDate boundaries, chính sách riêng |
| Thuê thiết bị tính theo số giờ thực | Elapsed seconds/hours | `Duration.between(instants)` |
| Chu kỳ thanh toán mỗi tháng | Lịch tháng | `Period.ofMonths(1)`/`YearMonth`, quy tắc ngày cuối |
| Cộng “7 ngày làm việc” | Ngày làm việc theo lịch riêng | `LocalDate` + business calendar |
| Đo thời gian thực thi code | Elapsed monotonic clock | `System.nanoTime()` cho measurement, không phải timestamp |

**Không có một lựa chọn đúng tuyệt đối cho chữ “ngày”.** Điều khoản hợp đồng/định nghĩa nghiệp vụ phải quyết định. Một dịch vụ có thể tính thời hạn đổi trả theo **ngày lịch** trong khi token xác thực của cùng dịch vụ hết hạn theo **24 giờ elapsed**.

### 9.1. Token TTL chính xác

Nếu token có thời gian sống 24 giờ kể từ mốc phát hành:

```java
Instant issued = Instant.parse("2024-03-09T17:00:00Z");
Instant expires = issued.plus(Duration.ofHours(24));
// 2024-03-10T17:00:00Z
```

Đó là hai mốc Instant cách đúng 86.400 giây. Nếu hiển thị New York, issued là `2024-03-09 12:00 -05:00` và expires là `2024-03-10 13:00 -04:00`. **Không dùng `issued.atZone(ny).plusDays(1)`** để đặt TTL nếu hợp đồng yêu cầu 24 giờ.

### 9.2. Lịch hẹn “cùng giờ ngày mai”

Nếu muốn 12:00 ngày kế tiếp tại New York:

```java
ZoneId ny = ZoneId.of("America/New_York");
ZonedDateTime meeting =
        ZonedDateTime.of(2024, 3, 9, 12, 0, 0, 0, ny);

ZonedDateTime tomorrowSameLocalHour = meeting.plusDays(1);
// 2024-03-10T12:00-04:00[America/New_York]
```

Chênh lệch Instant 23 giờ **không phải bug**: đó là hành vi đúng của ngày lịch và giờ địa phương. Nếu giờ đích nằm trong gap/overlap, phải xác định giải pháp DST phù hợp.

### 9.3. Báo cáo theo ngày địa phương thay vì chia Unix time cho 86400

Với một `Instant event`, xác định ngày mà user nhìn thấy:

```java
LocalDate localDay = event.atZone(zone).toLocalDate();
```

Nếu cần truy vấn sự kiện theo một ngày địa phương, dùng hai `Instant` biên ngày như mục 6. Chia `event.getEpochSecond() / 86400` chỉ nhóm theo các block 24 giờ tính từ epoch, **không** đại diện ngày lịch ở mọi zone.

**Cần thận trọng với số âm:** nếu tự chia epoch seconds âm bằng toán tử `/` của Java, phép làm tròn hướng về 0 có thể khác quy ước floor division cần dùng cho ngày trước epoch. Dùng API date-time/zone thay vì tự hiện thực phân nhóm bằng phép chia nguyên.

### 9.4. Hạn “trước ngày D” và “hết ngày D”

Đừng tự tạo endpoint `23:59:59.999` khi database có thể lưu nanoseconds/microseconds khác nhau.

Ví dụ yêu cầu nhận tất cả event của ngày `D` theo múi giờ `zone`:

```java
Instant includedFrom = D.atStartOfDay(zone).toInstant();
Instant excludedFrom = D.plusDays(1).atStartOfDay(zone).toInstant();

boolean belongs = !event.isBefore(includedFrom)
        && event.isBefore(excludedFrom);
```

Đây là đoạn trong method có `LocalDate D`, `ZoneId zone` và `Instant event` đã định nghĩa. Hai biên được tính **theo zone rules**, không theo số 24 giờ cố định.

## 10. Lỗi khi chỉ dùng `LocalDateTime` để tính elapsed time

`LocalDateTime` biểu diễn trường ngày và giờ **không có UTC offset**. Nó không thể xác định duy nhất Instant nếu có nhiều vùng hay overlap.

Ví dụ:

```java
LocalDateTime a = LocalDateTime.of(2024, 3, 9, 12, 0);
LocalDateTime b = LocalDateTime.of(2024, 3, 10, 12, 0);

long localHours = Duration.between(a, b).toHours(); // 24
```

Tuy nhiên, khi biểu diễn hai giá trị này trong `America/New_York` tại những ngày tương ứng:

```java
ZoneId zone = ZoneId.of("America/New_York");
long timelineHours = Duration.between(
        a.atZone(zone).toInstant(),
        b.atZone(zone).toInstant()).toHours(); // 23
```

Đây không phải lỗi của `Duration`: nguồn đầu tiên **không có thông tin zone**, trong khi nguồn thứ hai đã xác định hai Instant. Nếu mục tiêu là tính time-on-the-clock theo dữ liệu lịch, LocalDateTime có thể hữu ích; nếu mục tiêu là tính **thời gian thực**, cần kiểu biểu diễn đủ ngữ cảnh.

**Không thay toàn bộ hệ thống LocalDateTime bằng ZonedDateTime một cách vô tội vạ**: ứng dụng cần chọn kiểu theo ý nghĩa. Một cuộc hẹn **chưa biết vùng** vẫn có thể được mô hình bằng LocalDateTime và zone lưu riêng. Nhưng đừng biến LocalDateTime thành timestamp tuyệt đối khi chưa biết ZoneId/offset.

## 11. `ChronoUnit.DAYS`: “một đơn vị ngày” không tự nói cách áp dụng

Trong `java.time.temporal.ChronoUnit`:

- `DAYS` là một **date-based unit**.
- `HOURS` là một **time-based unit**.
- `DAYS.getDuration()` trả **ước lượng độ dài chuẩn** một ngày là 24h; đơn vị date-based là **estimated** khi xét timeline và zone.
- `HOURS.getDuration()` là thời lượng chuẩn một giờ 3.600 giây trong ngữ nghĩa API.

Ví dụ:

```java
boolean daysEstimated = ChronoUnit.DAYS.isDurationEstimated();
// true

Duration nominalDay = ChronoUnit.DAYS.getDuration();
// PT24H
```

Đây là lý do cần phân biệt **duration ước lượng của một đơn vị lịch** với **cách unit được áp dụng lên temporal cụ thể**. Ở `ZonedDateTime`, thêm một ChronoUnit.DAYS dùng local timeline; ở `Instant`, thêm một đơn vị DAYS được hiểu như lượng giây cố định theo API của Instant.

**Đừng dùng `ChronoUnit.DAYS.getDuration().toHours() == 24` làm bằng chứng “mỗi ngày địa phương có 24 giờ”.** Con số đó là chuẩn tính toán của unit, không phản ánh mọi bước nhảy múi giờ lịch sử.

### 11.1. `Period.between` và `ChronoUnit.DAYS.between`

`Period.between(LocalDate start, LocalDate end)` trả **số năm, tháng, ngày theo cấu trúc lịch**. `ChronoUnit.DAYS.between(start,end)` trả **tổng chênh lệch ngày lịch**. Hai số đo khác định dạng và mục đích.

Ví dụ:

```java
LocalDate from = LocalDate.of(2024, 1, 1);
LocalDate to = LocalDate.of(2024, 3, 1);

Period calendarParts = Period.between(from, to); // P2M
long totalCalendarDays = ChronoUnit.DAYS.between(from, to); // 60
```

Năm 2024 nhuận nên hai tháng đó có 31 + 29 = 60 ngày. `Period` nói “2 tháng lịch”, còn chênh ngày là 60. Không quy đổi tùy tiện `P2M` thành 60 ngày cho **mọi** khoảng hai tháng.

## 12. DST không phải là vấn đề của mọi ZoneId

Một số khu vực tại những giai đoạn nhất định không thay đổi offset trong năm. Ví dụ `Asia/Ho_Chi_Minh` hiện sử dụng UTC+07:00 và không có DST hằng năm; các ngày vận hành thông thường tại hiện tại được đo 24 giờ. Nhưng không nên suy ra **mọi vùng, mọi năm và mọi ngày** đều như vậy.

Mô hình đúng vẫn nên chọn:

- Cửa hàng, người dùng và lịch dân sự: lưu ZoneId khu vực (khi cần).
- Timestamp thời điểm đã xảy ra: lưu Instant.
- Elapsed duration: dùng Duration.
- Calendar period theo ngày/tháng/năm: dùng Period/LocalDate/YearMonth.

**Lưu ý về offset trong quá khứ:** Ngay cả nơi hiện không có DST vẫn có thể có lịch sử đổi UTC offset theo quyết định hành chính. Không tự hardcode “khu vực này lúc nào cũng +07:00” khi xử lý dữ liệu lịch sử.

### 12.1. ZoneOffset cố định không thể mô phỏng DST

`ZoneOffset.ofHours(-5)` luôn là -05:00. Ngày 2024-03-10 tính bằng offset cố định dài 24 giờ, nhưng khi dùng `America/New_York`, ngày đó dài 23 giờ vì đổi sang -04:00. Nếu một ứng dụng chỉ lưu offset chụp tại một thời điểm mà không lưu ZoneId, nó có thể không đủ thông tin để suy ra **ngày mai lúc 12:00 theo giờ địa phương của khu vực**.

### 12.2. DST là vấn đề chính sách, không chỉ phép cộng

Với một lịch hẹn định kỳ vào 02:30, giờ có thể bị thiếu tại gap. Với lịch hẹn 01:30, giờ có thể xuất hiện hai lần tại overlap. **Phần mềm phải quyết định** có chuyển sang thời gian gần nhất, bỏ lượt, dùng occurrence sớm/muộn, hoặc yêu cầu người dùng xác nhận. Không có một mặc định phù hợp với mọi loại lịch và hợp đồng kinh doanh.

## 13. Chương trình Java 17+ đầy đủ: đo ngày 23/25 giờ, gap và overlap

Chương trình này dùng mốc năm 2024 đã xảy ra ở New York và `Clock.fixed`. Nó kiểm tra trực tiếp bằng assertion tự định nghĩa, không phụ thuộc ngày/giờ máy chạy.

Tạo tệp **`CalendarDayVs24HoursDemo.java`**:

```java
import java.time.*;
import java.time.temporal.*;
import java.util.*;

public class CalendarDayVs24HoursDemo {
    static void check(boolean ok, String label) {
        if (!ok) {
            throw new AssertionError(label);
        }
    }

    static long dayLengthHours(LocalDate date, ZoneId zone) {
        ZonedDateTime first = date.atStartOfDay(zone);
        ZonedDateTime next = date.plusDays(1).atStartOfDay(zone);
        return Duration.between(
                first.toInstant(), next.toInstant()).toHours();
    }

    public static void main(String[] args) {
        ZoneId ny = ZoneId.of("America/New_York");

        ZonedDateTime spring = ZonedDateTime.of(
                2024, 3, 9, 12, 0, 0, 0, ny);
        ZonedDateTime springCalendar = spring.plusDays(1);
        ZonedDateTime springElapsed =
                spring.plus(Duration.ofHours(24));

        check(Duration.between(
                spring, springCalendar).toHours() == 23,
                "spring 23");
        check(springElapsed.toLocalTime().equals(
                LocalTime.of(13, 0)), "spring 24");

        System.out.println("springStart=" + spring);
        System.out.println("springPlusCalendarDay=" + springCalendar);
        System.out.println("springPlus24Hours=" + springElapsed);
        System.out.println("springElapsedToSameWallHour=" +
                Duration.between(
                        spring, springCalendar).toHours());
        System.out.println("springCalendarDaysBetween=" +
                ChronoUnit.DAYS.between(spring, springCalendar));
        System.out.println("springInstant24hDaysBetween=" +
                ChronoUnit.DAYS.between(
                        spring.toInstant(),
                        springCalendar.toInstant()));
        System.out.println("springLocalDateTimeHoursBetween=" +
                Duration.between(
                        spring.toLocalDateTime(),
                        springCalendar.toLocalDateTime()).toHours());

        ZonedDateTime fall = ZonedDateTime.of(
                2024, 11, 2, 12, 0, 0, 0, ny);
        ZonedDateTime fallCalendar = fall.plusDays(1);
        ZonedDateTime fallElapsed = fall.plusHours(24);

        check(Duration.between(fall, fallCalendar).toHours() == 25,
                "fall 25");
        check(fallElapsed.toLocalTime().equals(
                LocalTime.of(11, 0)), "fall 24");

        System.out.println("fallStart=" + fall);
        System.out.println("fallPlusCalendarDay=" + fallCalendar);
        System.out.println("fallPlus24Hours=" + fallElapsed);
        System.out.println("fallElapsedToSameWallHour=" +
                Duration.between(fall, fallCalendar).toHours());

        System.out.println("springDateHours=" +
                dayLengthHours(LocalDate.of(2024, 3, 10), ny));
        System.out.println("fallDateHours=" +
                dayLengthHours(LocalDate.of(2024, 11, 3), ny));
        System.out.println("utcSpringDateHours=" +
                dayLengthHours(LocalDate.of(2024, 3, 10),
                        ZoneOffset.UTC));
        System.out.println("fixedNewYorkOffsetHours=" +
                dayLengthHours(LocalDate.of(2024, 3, 10),
                        ZoneOffset.ofHours(-5)));

        LocalDate feb = LocalDate.of(2024, 2, 28);
        System.out.println("feb28PlusCalendarDay=" + feb.plusDays(1));
        System.out.println("jan31PlusCalendarMonth=" +
                LocalDate.of(2024, 1, 31).plusMonths(1));
        System.out.println("calendarPeriodOneDay=" +
                Period.ofDays(1));
        System.out.println("elapsedDurationOneDay=" +
                Duration.ofDays(1));

        LocalDateTime gap = LocalDateTime.of(
                2024, 3, 10, 2, 30);
        LocalDateTime overlap = LocalDateTime.of(
                2024, 11, 3, 1, 30);

        check(ny.getRules().getValidOffsets(gap).isEmpty(),
                "gap");
        check(ny.getRules().getValidOffsets(overlap).size() == 2,
                "overlap");

        System.out.println("gapValidOffsets=" +
                ny.getRules().getValidOffsets(gap).size());
        System.out.println("gapAdjusted=" + gap.atZone(ny));
        System.out.println("overlapValidOffsets=" +
                ny.getRules().getValidOffsets(overlap).size());
        System.out.println("overlapEarlier=" +
                overlap.atZone(ny));
        System.out.println("overlapLater=" +
                overlap.atZone(ny).withLaterOffsetAtOverlap());

        System.out.println("apparentSameDate=" +
                spring.toLocalDate().equals(
                        springCalendar.toLocalDate()));

        Clock fixed = Clock.fixed(
                Instant.parse("2024-03-10T06:30:00Z"), ny);
        System.out.println("fixedClock=" +
                ZonedDateTime.now(fixed));

        System.out.println("ALL CHECKS PASSED");
    }
}
```

Biên dịch và chạy:

```bash
javac CalendarDayVs24HoursDemo.java
java CalendarDayVs24HoursDemo
```

**Stdout kỳ vọng chính xác:**

```text
springStart=2024-03-09T12:00-05:00[America/New_York]
springPlusCalendarDay=2024-03-10T12:00-04:00[America/New_York]
springPlus24Hours=2024-03-10T13:00-04:00[America/New_York]
springElapsedToSameWallHour=23
springCalendarDaysBetween=1
springInstant24hDaysBetween=0
springLocalDateTimeHoursBetween=24
fallStart=2024-11-02T12:00-04:00[America/New_York]
fallPlusCalendarDay=2024-11-03T12:00-05:00[America/New_York]
fallPlus24Hours=2024-11-03T11:00-05:00[America/New_York]
fallElapsedToSameWallHour=25
springDateHours=23
fallDateHours=25
utcSpringDateHours=24
fixedNewYorkOffsetHours=24
feb28PlusCalendarDay=2024-02-29
jan31PlusCalendarMonth=2024-02-29
calendarPeriodOneDay=P1D
elapsedDurationOneDay=PT24H
gapValidOffsets=0
gapAdjusted=2024-03-10T03:30-04:00[America/New_York]
overlapValidOffsets=2
overlapEarlier=2024-11-03T01:30-04:00[America/New_York]
overlapLater=2024-11-03T01:30-05:00[America/New_York]
apparentSameDate=false
fixedClock=2024-03-10T01:30-05:00[America/New_York]
ALL CHECKS PASSED
```

### 13.1. Phân tích output theo từng nhóm

**Nhóm spring:**

- `springStart` ở `-05:00`; cùng giờ đồng hồ ngày kế tiếp đã chuyển thành `-04:00`. Tính elapsed bằng `Duration.between` cho **23 giờ**, dù `ChronoUnit.DAYS.between` trên hai ZonedDateTime cho **1 ngày lịch**.
- Khi cộng đúng 24 giờ, `springPlus24Hours` thành **13:00**. Nếu chỉ quan sát local time mà không ghi offset, có thể nhầm đây là một giờ bị “cộng dư” — thực chất là kết quả bảo toàn 86.400 giây.
- `springInstant24hDaysBetween=0` vì hai Instant chỉ cách nhau 23 giờ. `springLocalDateTimeHoursBetween=24` vì loại LocalDateTime không biết DST.

**Nhóm fall:**

- `fallStart` ở `-04:00`; sau một ngày lịch sang `-05:00` và tổng elapsed là **25 giờ**.
- `fallPlus24Hours` thành **11:00** ngày hôm sau. Điều này trái trực giác nếu chỉ nghĩ “24 giờ = ngày mai cùng giờ”, nhưng hoàn toàn đúng theo timeline.

**Nhóm độ dài ngày và offset:**

- Ngày xuân ở New York dài 23 giờ, ngày thu dài 25 giờ.
- Cùng ngày xuân trong múi giờ UTC hoặc fixed offset `-05:00` dài **24 giờ**, chứng tỏ **ZoneId** và **ZoneOffset** không thể được coi tương đương cho lịch có DST.

**Nhóm lịch:**

- Năm 2024 nhuận, `2024-02-28.plusDays(1)` thành `2024-02-29`.
- `2024-01-31.plusMonths(1)` điều chỉnh thành `2024-02-29`, khác phép cộng số ngày cố định.
- `Period.ofDays(1)` in `P1D`; `Duration.ofDays(1)` in `PT24H`. Hai kiểu không có cùng ngữ nghĩa khi cộng vào zoned time qua DST.

**Nhóm gap/overlap:**

- `gapValidOffsets=0`: `02:30` vào ngày 10/3 không tồn tại; quy tắc mặc định `atZone` chuyển sang 03:30.
- `overlapValidOffsets=2`: `01:30` vào ngày 3/11 tồn tại hai lần. `withLaterOffsetAtOverlap` chọn occurrence thứ hai, khác một giờ trên timeline.
- `Clock.fixed` làm test ổn định: Instant UTC 06:30 ngày 10/3 ứng với local 01:30 -05:00 ở New York trước lúc nhảy giờ.

## 14. Các lỗi thường gặp trong ứng dụng

### Lỗi 1: Dùng `Duration.ofDays(1)` cho lịch hẹn “ngày mai cùng giờ”

Nếu có DST, phép cộng đúng 24 giờ có thể cho 11:00 hoặc 13:00 thay vì 12:00. **Sửa:** dùng ngày lịch `plusDays(1)` hoặc xây `LocalDate` đích + `LocalTime` + `ZoneId` theo chính sách gap/overlap.

### Lỗi 2: Dùng `plusDays(1)` cho token TTL 24 giờ

Vào ngày đổi DST, time-to-live có thể là 23h/25h. **Sửa:** lưu `Instant` và cộng `Duration.ofHours(24)` cho TTL.

### Lỗi 3: Tính ngày báo cáo bằng `startInstant.plus(Duration.ofDays(1))`

Khoảng báo cáo bị lệch ranh giới ngày địa phương vào ngày đổi offset. **Sửa:** tính biên `date.atStartOfDay(zone)` và `date.plusDays(1).atStartOfDay(zone)`, sau đó dùng khoảng [from,to).

### Lỗi 4: Coi `LocalDateTime` là timestamp có zone

`Duration.between(LocalDateTime,LocalDateTime)` không có DST; thậm chí LocalDateTime của gap/overlap có thể không ánh xạ duy nhất sang Instant. **Sửa:** bổ sung `ZoneId`/offset hợp lệ hoặc dùng `Instant` khi cần elapsed thực.

### Lỗi 5: Phân nhóm theo `epochSecond / 86400`

Đây là block thời gian chuẩn 24 giờ từ epoch, không phải ngày tại khu vực. **Sửa:** `event.atZone(zone).toLocalDate()` hoặc các biên ngày địa phương.

### Lỗi 6: Nghĩ `ChronoUnit.DAYS.getDuration() == PT24H` chứng minh ngày lịch luôn dài 24 giờ

`ChronoUnit.DAYS` là date-based unit với duration **ước lượng**. **Sửa:** phân biệt phép cộng lịch với phép cộng elapsed; tính bằng Instant ở hai đầu khi cần số giờ thật.

### Lỗi 7: Không có chính sách DST gap/overlap

Lịch hẹn 02:30 có thể không tồn tại; 01:30 có thể diễn ra hai lần. **Sửa:** xác thực `ZoneRules.getValidOffsets`, xác định bỏ/dời lượt, chọn offset theo yêu cầu.

### Lỗi 8: Giả định tháng là 30 ngày

`Period.ofMonths(1)` không tương đương `Duration.ofDays(30)`. **Sửa:** dùng `LocalDate.plusMonths`/`YearMonth` và chính sách ngày cuối tháng.

### Lỗi 9: Coi “ngày làm việc” là ngày lịch

`plusDays(1)` vẫn cộng qua cuối tuần, ngày nghỉ. **Sửa:** tích hợp business calendar/holiday policy phù hợp. Không thay bằng một lượng giây cố định.

### Lỗi 10: Cho rằng `ZoneOffset` fixed là tương đương `ZoneId` địa phương

Offset cố định không biết DST hoặc đổi quy tắc lịch sử/tương lai. **Sửa:** lưu region ID khi lịch được gắn với một địa điểm.

### Lỗi 11: Test ngày giờ chỉ trên múi giờ UTC

UTC che khuất lỗi DST. **Sửa:** có test cả vùng với gap và overlap, ví dụ New York tại các ngày lịch sử đã xác định.

### Lỗi 12: Test `now()` trực tiếp rồi kỳ vọng một giờ cụ thể

Phụ thuộc máy và thời điểm chạy. **Sửa:** inject `Clock` và dùng `Clock.fixed` khi test business rule.

### Lỗi 13: Lưu “hết ngày” bằng 23:59:59.999

DB có thể hỗ trợ precision cao hơn; event sau mốc này vẫn cùng ngày. **Sửa:** dùng điều kiện `event < nextDayStart`, không hardcode maximum time trong ngày.

### Lỗi 14: Tự bắt mọi exception rồi coi giờ điều chỉnh là hợp lệ nghiệp vụ

`atZone` có chính sách mặc định khi local time không tồn tại, nhưng điều đó không có nghĩa cuộc hẹn “02:30” nên được dời sang “03:30”. **Sửa:** xác thực và ghi rõ resolution policy, thông báo cho user nếu lịch bị thay đổi.

## 15. Kiểm thử boundary và quy tắc ngày

| Test | Input | Expected |
| --- | --- | --- |
| Cộng 1 ngày lịch trước DST xuân | New York 2024-03-09 12:00 | 2024-03-10 12:00 -04, elapsed 23h |
| Cộng 24 giờ trước DST xuân | New York 2024-03-09 12:00 | 2024-03-10 13:00 -04 |
| Cộng 1 ngày lịch trước DST thu | New York 2024-11-02 12:00 | 2024-11-03 12:00 -05, elapsed 25h |
| Cộng 24 giờ trước DST thu | New York 2024-11-02 12:00 | 2024-11-03 11:00 -05 |
| Độ dài ngày xuân | 2024-03-10, New York | 23h |
| Độ dài ngày thu | 2024-11-03, New York | 25h |
| Cùng ngày với fixed offset | 2024-03-10, -05:00 | 24h |
| Cùng ngày với UTC | 2024-03-10, UTC | 24h |
| LocalDate+1 ngày ở năm nhuận | 2024-02-28 | 2024-02-29 |
| LocalDate+1 tháng cuối tháng | 2024-01-31 | 2024-02-29 |
| `ChronoUnit.DAYS` trên ZonedDateTime | Hai mốc trưa cách một ngày lịch qua spring | 1 |
| `ChronoUnit.DAYS` trên Instant | Hai Instant cách 23h | 0 |
| `Duration.between` trên LocalDateTime | Hai LocalDateTime cùng giờ hai ngày liên tiếp | 24h (không biết DST) |
| Gap | 2024-03-10 02:30, New York | 0 offset hợp lệ |
| Overlap | 2024-11-03 01:30, New York | 2 offset hợp lệ |
| Round-trip instant | `zdt.toInstant().atZone(zone)` | Giữ cùng một Instant |
| Clock cố định | 2024-03-10T06:30Z tại New York | 01:30 -05 |

**Không test theo số thread của stream hoặc thời gian hiện tại**; ngày giờ cần expected từ dữ liệu cố định. Với hệ thống đa khu vực, nên bổ sung vùng không có DST hiện nay và vùng có quy tắc DST đặc biệt, tùy phạm vi kinh doanh thực tế.

### 15.1. Bất biến quan trọng khi chuyển zone

`ZonedDateTime.withZoneSameInstant(newZone)` giữ nguyên Instant; `withZoneSameLocal(newZone)` cố giữ ngày giờ địa phương, có thể đổi Instant. Hai phương thức này cũng giống hai khái niệm “cùng thời điểm thực” và “cùng giờ đồng hồ”. Không đổi zone chỉ bằng cách sửa chuỗi ký tự offset.

## 16. Bài tập và đáp án

**Bài 1.** `Duration.ofDays(1)` tương đương chính xác bao nhiêu giây?

**Đáp án:** **86.400 giây** (`Duration.ofHours(24)`). Điều đó không khẳng định mọi ngày địa phương cũng dài đúng 86.400 giây.

**Bài 2.** `Period.ofDays(1)` cộng vào `ZonedDateTime` ở New York trước ngày DST xuân có giữ giờ 12:00 không?

**Đáp án:** Trong ví dụ 2024-03-09 12:00, kết quả là 2024-03-10 12:00 -04:00, cách 23 giờ. Nhưng nếu giờ đích nằm trong gap, API có thể điều chỉnh giờ theo zone rules.

**Bài 3.** Tại sao `plusHours(24)` từ trưa ngày 9/3/2024 ra 13:00 ngày 10/3 ở New York?

**Đáp án:** Đồng hồ địa phương đã nhảy tới một giờ. Cộng elapsed 24h giữ lượng giây trên timeline, nên giờ hiển thị muộn hơn một giờ.

**Bài 4.** Tại sao trưa ngày 2/11/2024 cộng `plusDays(1)` tại New York cách trưa ngày 3/11 tới 25 giờ?

**Đáp án:** Đồng hồ lùi một giờ ngày 3/11; khoảng cùng giờ địa phương hai ngày liên tiếp dài 25 giờ.

**Bài 5.** Một báo cáo theo ngày 10/3/2024 ở New York phải tính đến mốc kết thúc nào?

**Đáp án:** Tính `2024-03-11.atStartOfDay(America/New_York)` rồi lấy `Instant` làm exclusive upper bound. Không dùng đầu ngày 10/3 cộng 24h.

**Bài 6.** `ChronoUnit.DAYS.between` trên hai ZonedDateTime trưa liên tiếp qua ngày đổi DST cho 1, nhưng trên hai Instant đó cho 0. Có mâu thuẫn không?

**Đáp án:** Không. Kiểu ZonedDateTime áp ngày trên local timeline, trong khi Instant đếm những đoạn thời lượng chuẩn 24h; hai Instant chỉ cách 23h.

**Bài 7.** `LocalDateTime.of(2024,3,10,2,30)` có hợp lệ không? Có xảy ra ở New York không?

**Đáp án:** LocalDateTime hợp lệ vì không có zone. Nhưng tại New York, local time ấy nằm trong DST gap và không tương ứng một Instant hợp lệ theo giờ đồng hồ địa phương ngày đó.

**Bài 8.** `2024-11-03 01:30` tại New York chỉ định được duy nhất một Instant không?

**Đáp án:** Không. Nó xuất hiện hai lần với -04:00 và -05:00; cần chọn offset/occurrence theo nghiệp vụ.

**Bài 9.** `LocalDate.of(2024,1,31).plusMonths(1)` là ngày nào?

**Đáp án:** 2024-02-29 vì năm nhuận và Java điều chỉnh về ngày hợp lệ cuối tháng đích.

**Bài 10.** Muốn token hết hạn đúng 24h thì chọn `Period.ofDays(1)` hay `Duration.ofHours(24)`?

**Đáp án:** `Duration.ofHours(24)` trên `Instant` của thời điểm phát hành.

**Bài 11.** “Ngày nghỉ sau 2 ngày làm việc” có thể tính chỉ bằng `Period.ofDays(2)` không?

**Đáp án:** Không. Business day đòi hỏi lịch làm việc, cuối tuần và ngày nghỉ cụ thể; `Period.ofDays` chỉ là ngày lịch.

**Bài 12.** Một `LocalDate` ở vùng có thay đổi offset lịch sử có chắc ngày đó dài 24h không?

**Đáp án:** Không. Phải dùng `LocalDate.atStartOfDay(zone)` cho ngày ấy và ngày kế tiếp, so hai Instant. Một số thay đổi vùng không đi theo mẫu DST một giờ tiêu chuẩn.

**Bài 13.** Vì sao không nên lưu “cuối ngày” bằng 23:59:59.999?

**Đáp án:** Có thể bỏ sót event ở precision micro/nano cao hơn và làm logic ranh giới khó kiểm tra. Dùng upper bound loại trừ là đầu ngày kế tiếp theo ZoneId.

**Bài 14.** Khi chạy test giờ hiện tại, vì sao `Clock.fixed(...)` tốt hơn `ZonedDateTime.now()` mặc định?

**Đáp án:** Nó tạo mốc thời gian và zone ổn định, không phụ thuộc môi trường, giúp kiểm thử chính xác trường hợp trước/sau DST hoặc ở ranh giới.

## 17. Quy trình lựa chọn kiểu dữ liệu cho một yêu cầu có chữ “ngày”

**Bước 1 — Hỏi “ngày trên lịch hay số giây?”.** Nếu cần một ngày người dùng nhìn thấy, chọn LocalDate/Period và ZoneId. Nếu cần chính xác 86.400 giây, chọn Instant/Duration.

**Bước 2 — Xác định địa điểm tính ngày.** Ngày 10/3 ở New York không có cùng ranh giới Instant như ngày 10/3 ở Hà Nội. Nếu yêu cầu theo địa điểm, lấy ZoneId của địa điểm đó.

**Bước 3 — Xác định giờ lặp lại.** “12:00 mỗi ngày” phải giữ LocalTime và quy tắc gap/overlap; “mỗi 24 giờ” không nhất thiết giữ cùng LocalTime qua DST.

**Bước 4 — Xác định biên khoảng.** Với truy vấn theo ngày, dùng `[startOfDay, nextStartOfDay)`. Với deadline, quy định rõ tính “trước ngày”, “trước giờ”, hay “sau đúng N giờ”.

**Bước 5 — Áp business calendar khi cần.** Ngày lịch không phải ngày làm việc; lịch tháng cũng không cố định bằng số ngày.

**Bước 6 — Kiểm tra kiểu của toán hạng.** `ChronoUnit.DAYS.between` với LocalDate, ZonedDateTime và Instant có thể trả câu trả lời mang ngữ nghĩa khác nhau. Đừng chỉ nhìn tên đơn vị.

**Bước 7 — Kiểm tra vùng chuyển offset.** Nếu local date-time rơi vào gap/overlap, chọn policy để không âm thầm dịch lịch sai yêu cầu.

**Bước 8 — Viết test tại các ngày chuyển DST và ngày cuối tháng.** Test cả đơn vị lịch và elapsed bằng expected độc lập từ các mốc cố định, không chỉ các ngày bình thường.

**Bước 9 — Lưu dữ liệu đủ tái hiện.** Event timestamp: Instant. Hẹn theo lịch địa phương: LocalDate + LocalTime + ZoneId (và rule resolution nếu cần). Tùy hệ thống, có thể lưu cả Instant đã resolve và zone để audit.

**Bước 10 — Kiểm tra hệ thống ngoài Java.** Database/scheduler/API có thể dùng offset hoặc cấu hình timezone khác Java. Đảm bảo pipeline giữ đúng ý nghĩa calendar-vs-duration.

## 18. Checklist trước khi đưa vào production

- [ ] Đã xác nhận “một ngày” trong yêu cầu là ngày lịch hay elapsed 86.400 giây?
- [ ] Với lịch khu vực, dùng ZoneId của địa điểm, không thay bằng offset cố định nếu có quy tắc DST?
- [ ] Với TTL, timeout và SLA theo giờ thực, dùng Instant/Duration?
- [ ] Với ngày báo cáo, dùng LocalDate và **hai ranh giới zoned start-of-day**, không cộng 24h từ đầu ngày?
- [ ] Hiểu `Period.ofDays(1)` và `Duration.ofDays(1)` khác nhau về ngữ nghĩa?
- [ ] Hiểu `ZonedDateTime.plusDays(1)` và `plusHours(24)` có thể khác một giờ địa phương?
- [ ] Kiểm thử ca DST spring/fall 23/25 giờ (hoặc chuyển đổi offset phù hợp vùng của ứng dụng)?
- [ ] Đã xác định chính sách xử lý local time rơi vào gap/overlap?
- [ ] Không dùng `LocalDateTime` thiếu zone để đo elapsed tuyệt đối?
- [ ] Không đánh đồng `Duration.toDays()` với đếm ngày lịch?
- [ ] Nếu yêu cầu tính tháng, dùng Period/LocalDate/YearMonth và chính sách cuối tháng?
- [ ] Nếu yêu cầu business day, dùng lịch làm việc và ngày nghỉ thực tế?
- [ ] Dùng điều kiện `[from,to)` thay cho “23:59:59.999” để lọc toàn bộ ngày?
- [ ] Khi đổi zone, phân biệt giữ Instant với giữ local date-time?
- [ ] Đã inject Clock/fixed data cho unit test thay vì phụ thuộc thời gian hệ thống?

## Tài liệu tham khảo chính thức vẫn áp dụng

1. [Oracle JDK 26 — ZonedDateTime: phép cộng date-based trên local timeline, time-based trên instant timeline và xử lý gap/overlap](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/time/ZonedDateTime.html)
2. [Oracle JDK 26 — Duration: ofDays là một ngày chuẩn 86.400 giây, không phải độ dài mọi ngày địa phương](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/time/Duration.html)
3. [Oracle JDK 26 — Period: năm, tháng, ngày theo lịch ISO](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/time/Period.html)
4. [Oracle JDK 26 — LocalDate.atStartOfDay(ZoneId): thời điểm hợp lệ đầu tiên của ngày theo quy tắc khu vực](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/time/LocalDate.html)
5. [Oracle JDK 26 — ChronoUnit: date-based units, estimated duration và phép between](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/time/temporal/ChronoUnit.html)
6. [Oracle JDK 26 — ZoneId và ZoneRules](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/time/ZoneId.html)
7. [Oracle JDK 26 — ZoneOffsetTransition: gap/overlap khi offset thay đổi](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/time/zone/ZoneOffsetTransition.html)
8. [Oracle JDK 26 — Instant: mốc thời gian trên timeline](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/time/Instant.html)
9. [Oracle JDK 26 — Clock: fixed Clock cho kiểm thử đáng tin](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/time/Clock.html)

**Ghi nhớ quan trọng nhất:** Một **ngày trên lịch** là bước chuyển của lịch địa phương theo **ZoneId**, còn **24 giờ** là một lượng thời gian cố định **86.400 giây**. Chúng thường trùng nhau nhưng **không phải một** ở các ranh giới thay đổi UTC offset. Khi yêu cầu có chữ “ngày”, hãy làm rõ ý nghĩa trước khi chọn `Period`, `Duration` và toán tử cộng.
