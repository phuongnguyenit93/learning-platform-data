# Duration và khoảng theo giây, nanosecond trong Java

## 1. Bản chất của `Duration`: khoảng có độ dài theo thời gian thực

`java.time.Duration` biểu diễn **một lượng thời gian có dấu** bằng hai thành phần **giây** và **nano giây**. Đây là API thuộc Java 8, vẫn được sử dụng và được duy trì trên JDK hiện đại. Những câu như “API timeout sau 2 giây”, “tác vụ chạy 125 mili giây”, “hai giao dịch cách nhau 1,5 giây” đều phù hợp để biểu diễn bằng `Duration`.

```java
Duration timeout = Duration.ofSeconds(2);
Duration debounce = Duration.ofMillis(350);
Duration oneNano = Duration.ofNanos(1);
Duration oneAndQuarter = Duration.ofSeconds(1, 250_000_000);
```

Đây là snippet trong method, cần `import java.time.Duration;`. Bốn duration có độ dài lần lượt `2 s`, `350 ms`, `1 ns` và `1,25 s`. Không cần dùng các phép toán trên ngày giờ lịch chỉ để lưu một khoảng thời gian.

**Điều quan trọng:** `Duration` không phải một thời điểm, không phải múi giờ, không mang ngày bắt đầu và không tự biết tháng nào có bao nhiêu ngày. Nó lưu độ dài. Khi cần xác định “từ lúc nào đến lúc nào”, bạn cần các mốc `Instant`/`ZonedDateTime` hoặc dữ liệu ngày-giờ phù hợp.

### 1.1. Bảng phân biệt các kiểu

| Câu hỏi | Kiểu phù hợp | Giải thích |
| --- | --- | --- |
| “Mất bao lâu, tới nano giây?” | `Duration` | Độ dài thực theo giây và nano giây |
| “Sự kiện xảy ra lúc nào?” | `Instant` | Một điểm xác định trên timeline |
| “Ba tháng nữa theo lịch?” | `Period` hoặc `plusMonths` trên kiểu lịch | Tháng có số ngày biến thiên |
| “Cuộc hẹn là ngày nào?” | `LocalDate` | Một ngày lịch, không có giờ |
| “Giờ hẹn tại Paris?” | `ZonedDateTime` | Có vùng giờ và quy tắc DST |
| “Tác vụ dùng bao nhiêu thời gian CPU/wall-time?” | Đồng hồ đo và benchmark thích hợp | Lấy chênh lệch đo được, có thể biểu diễn dưới dạng Duration |
| “Chờ tối đa 750 ms?” | `Duration.ofMillis(750)` | Một độ dài timeout, không phải timestamp |

Không dùng `Duration.ofDays(30)` để thay thế mặc định cho `Period.ofMonths(1)`. Một tháng có 28–31 ngày, không phải 30×24 giờ theo mọi lịch nghiệp vụ.

### 1.2. Duration có hướng: dương, bằng 0 hoặc âm

`Duration.between(start, end)` cho khoảng theo chiều **từ start tới end**. Nếu end ở sau start thì kết quả dương, nếu end ở trước start thì âm. `Duration.ZERO` biểu diễn thời lượng bằng 0. Dấu âm hữu ích khi đánh giá deadline đã qua hạn hoặc kiểm tra thứ tự sự kiện; không tự gọi `abs()` trước khi hiểu ngữ nghĩa.

```text
Instant s ------------------------> Instant e
          Duration.between(s,e) > 0

Instant e <------------------------ Instant s
          Duration.between(s,e) < 0

Cùng mốc: Duration.ZERO
```

## 2. Biểu diễn nội bộ: `long seconds` và `int nanos`

`Duration` không lưu một số `double` kiểu “1,234 giây”. Nó lưu hai phần:

1. `getSeconds()` trả thành phần **giây nguyên** kiểu `long`.
2. `getNano()` trả phần điều chỉnh **nano giây trong giây**, kiểu `int`, luôn trong khoảng từ `0` đến `999_999_999`.

Toàn bộ độ dài bằng:

```text
total = seconds × 1_000_000_000 nanoseconds + nanos
```

Đây là một đẳng thức toán học. Nếu tính bằng phép nhân `long` trong Java với thời lượng rất lớn thì kết quả có thể **tràn**, dù đối tượng `Duration` vẫn hợp lệ. Vì vậy mới có sự khác biệt giữa việc giữ cặp `seconds+nanos` và gọi `toNanos()` để cố ép tổng vào một số `long`.

### 2.1. Ví dụ có phần lẻ nano

```java
Duration d = Duration.ofSeconds(90, 123_456_789);

long seconds = d.getSeconds(); // 90
int nanoPart = d.getNano();     // 123456789

long milliseconds = d.toMillis(); // 90123
long nanoseconds = d.toNanos();   // 90123456789
```

`90,123456789 giây` là một thời lượng có phần lẻ tới nano giây. `toMillis()` bỏ phần nhỏ hơn một mili giây, nên `90123` mili giây **không chứa đủ** thông tin để khôi phục chính xác `123456789` nano phần lẻ.

Các quy đổi cần ghi nhớ:

| Đơn vị | Nano giây tương đương |
| --- | ---: |
| 1 giây | `1_000_000_000` ns |
| 1 mili giây (ms) | `1_000_000` ns |
| 1 micro giây (µs) | `1_000` ns |
| 1 nano giây (ns) | `1` ns |

**`getNano()` không phải tổng nano giây.** Nếu duration dài hơn một giây, tổng ns là phần giây cộng phần lẻ. Nếu không thể chắc chắn tổng ns nằm trong giới hạn `long`, hãy làm việc trực tiếp với hai phần hoặc kiểu số chính xác lớn hơn.

### 2.2. Chuẩn hóa khi nano adjustment lớn hơn một giây

Factory `ofSeconds(long seconds, long nanoAdjustment)` cho phép nano adjustment vượt `999999999`; API tự đưa phần nguyên sang giây:

```java
Duration d = Duration.ofSeconds(1, 1_500_000_000L);

d.getSeconds(); // 2
d.getNano();    // 500000000
d.toString();   // PT2.5S
```

Số 1,5 tỉ nano giây chính là 1,5 giây; cộng với 1 giây đầu tiên thành **2,5 giây**. Việc chuẩn hóa diễn ra tự động, nhưng nếu kết quả vượt dải `long seconds` thì API vẫn có thể ném `ArithmeticException`.

## 3. Khoảng âm: vì sao `-1 ns` có `getSeconds() == -1`?

Đây là bẫy phổ biến nhất khi học `Duration`. Phần `nanos` của đối tượng luôn **không âm**, kể cả khi độ dài toàn bộ là số âm:

```java
Duration negative = Duration.ofNanos(-1);

negative.getSeconds(); // -1
negative.getNano();    // 999999999
negative.toNanos();    // -1
```

Phép tính:

```text
(-1) × 1_000_000_000 + 999_999_999 = -1 nano giây
```

`getSeconds()` là thành phần **được chuẩn hóa**, không phải số giây sau phép cắt về 0 trong mọi trường hợp. Tương tự:

```java
Duration minusOneMilli = Duration.ofMillis(-1);

minusOneMilli.getSeconds(); // -1
minusOneMilli.getNano();    // 999000000
minusOneMilli.toMillis();   // -1
minusOneMilli.toString();   // PT-0.001S
```

Không dùng `getNano() < 0` để kiểm tra khoảng âm, vì biểu thức đó không bao giờ đúng. Dùng `isNegative()` hoặc `compareTo(Duration.ZERO) < 0`.

### 3.1. Phân biệt thành phần và tổng số giây cắt về 0

Trên Java 9+, `Duration.toSeconds()` trả tổng số giây nguyên của độ dài, theo quy tắc cắt phần lẻ. Nhưng `getSeconds()` truy cập thành phần giây của biểu diễn chuẩn hóa. Khi duration bằng `-0,001 s` thì `getSeconds()==-1`, còn phép đổi tổng độ dài về giây nguyên theo hướng cắt về 0 cho `0`.

**Tương thích Java 8:** `toSeconds()` không có trong API gốc Java 8. Đừng dùng nó trong source được biên dịch với `javac --release 8`. Nếu chỉ cần kiểm tra âm/dương hay so sánh duration, dùng `isNegative()`/`compareTo()` thay vì tự suy diễn từ các thành phần.

### 3.2. So sánh khoảng âm, 0 và dương

```java
Duration a = Duration.ofNanos(-1);
Duration b = Duration.ZERO;
Duration c = Duration.ofNanos(1);

boolean negative = a.isNegative();         // true
boolean zero = b.isZero();                 // true
boolean inOrder = a.compareTo(b) < 0
    && b.compareTo(c) < 0;                 // true
```

`Duration` triển khai `Comparable<Duration>`; kết quả `compareTo` dựa trên **toàn bộ độ dài**, không phải so chuỗi ISO hay so riêng `getNano`.

## 4. Các cách tạo `Duration` từ đơn vị thời gian

| Factory | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| `ofNanos(n)` | n nano giây | `Duration.ofNanos(800)` |
| `ofMillis(m)` | m mili giây | `Duration.ofMillis(250)` |
| `ofSeconds(s)` | s giây | `Duration.ofSeconds(5)` |
| `ofSeconds(s,n)` | s giây cộng n nano | `Duration.ofSeconds(1,250000000)` |
| `ofMinutes(m)` | m phút, mỗi phút 60 giây | `Duration.ofMinutes(2)` |
| `ofHours(h)` | h giờ, mỗi giờ 3600 giây | `Duration.ofHours(3)` |
| `ofDays(d)` | d ngày **cố định 24 giờ** | `Duration.ofDays(1)` |
| `of(amount, unit)` | Lượng theo đơn vị được hỗ trợ | `Duration.of(5, ChronoUnit.SECONDS)` |
| `Duration.ZERO` | Độ dài đúng bằng 0 | `Duration.ZERO` |

`Duration.ofDays(1).equals(Duration.ofHours(24))` trả `true`, vì cả hai đều biểu diễn **86400 giây**. Nhưng điều này không khẳng định mọi ngày trong một múi giờ đều dài 24 giờ thực tế.

### 4.1. `of(amount, unit)` và các đơn vị ước lượng

`Duration.of(long, TemporalUnit)` chỉ hỗ trợ những đơn vị có độ dài chính xác (và `ChronoUnit.DAYS` được xử lý như 24 giờ). Với `ChronoUnit.MONTHS` hoặc `YEARS` có độ dài theo lịch, `Duration.of(1, ChronoUnit.MONTHS)` không phải cách hợp lệ để mô tả một tháng:

```java
Duration fiveSeconds =
    Duration.of(5, ChronoUnit.SECONDS);

// Không dùng: số ngày trong tháng biến thiên.
// Duration oneMonth = Duration.of(1, ChronoUnit.MONTHS);
```

Mã là snippet cần import `Duration` và `ChronoUnit`. Nếu yêu cầu là “gia hạn một tháng”, dùng `Period.ofMonths(1)` hoặc `plusMonths(1)` trên kiểu ngày/giờ phù hợp.

### 4.2. Độ chính xác nano là khả năng biểu diễn, không phải chứng nhận đồng hồ

`Duration.ofNanos(1)` hoàn toàn hợp lệ, nhưng đồng hồ hệ điều hành, thiết bị hay timestamp của database có thể chỉ chính xác ở mức mili hoặc micro giây. API lưu được một nano giây **không tạo ra** phép đo vật lý có độ chính xác một nano giây. Khi yêu cầu chất lượng dữ liệu, ghi nhận cả nguồn đo và độ phân giải thực.

## 5. `Duration.parse` và `toString` theo dạng ISO-8601

Cách viết thời lượng theo ISO có cấu trúc `PnDTnHnMn.nS`:

- `P` bắt đầu biểu diễn thời lượng.
- `D` biểu diễn số ngày **chuẩn 24 giờ** trong một `Duration`.
- `T` mở đầu phần **giờ, phút, giây**.
- `H` là giờ, `M` sau `T` là phút, `S` là giây.
- Phần giây thập phân có thể mang tối đa 9 chữ số cho độ chính xác nano giây.

```java
Duration a = Duration.parse("PT1H30M");
Duration b = Duration.parse("PT0.000000001S");
Duration c = Duration.parse("P1DT2H");

a.toString(); // PT1H30M
b.toString(); // PT0.000000001S
c.toString(); // PT26H
```

`P1DT2H` biểu diễn đúng **26 giờ**, và `Duration.toString()` có thể chuẩn hóa thành `PT26H`. **Hai chuỗi khác nhau có thể chứa cùng một giá trị Duration**; hãy so sánh bằng `equals`, không so nguyên chuỗi người dùng nhập.

```java
Duration fromInput = Duration.parse("P1DT2H");
Duration fromOutput = Duration.parse(fromInput.toString());

boolean same = fromInput.equals(fromOutput); // true
```

Không giả định `Duration.parse("500ms")` hoặc `Duration.parse("1h")` sẽ hoạt động theo Java chuẩn. Một số framework có parser riêng cho chuỗi viết tắt; nếu dùng, phải ghi đúng contract và phạm vi phiên bản framework. Với chuỗi cấu hình di động, `"PT0.5S"` hoặc `"PT1H"` rõ ràng hơn.

### 5.1. Biểu diễn âm trong chuỗi ISO

`Duration.parse("-PT1.5S")` là duration âm 1,5 giây. `toString` có thể in kiểu `PT-1.5S`. Đừng tự ghép chuỗi theo cách thay dấu trong trường `getSeconds`; phần nano không âm và có quy tắc chuẩn hóa riêng. Khi trao đổi qua API, dùng `Duration.parse` và `toString` để tránh các lỗi ký hiệu.

## 6. Tính khoảng giữa hai thời điểm với `Duration.between`

`Duration.between(startInclusive, endExclusive)` đo khoảng **từ start đến end**. Khi cả hai là `Instant`, kết quả phản ánh độ dài trên timeline:

```java
Instant start = Instant.parse(
    "2024-02-29T23:59:59.123456789Z");
Instant end = Instant.parse(
    "2024-03-01T00:00:01.123456790Z");

Duration forward = Duration.between(start, end);
// PT2.000000001S

Duration backward = Duration.between(end, start);
// PT-2.000000001S

boolean roundTrip = start.plus(forward).equals(end); // true
```

Việc đi qua ngày mới hoặc năm nhuận không làm thay đổi phép trừ timeline. Kết quả chính xác theo độ phân giải có trong hai `Instant`. Không dùng số ngày chênh lịch nhân 86400 để thay cho hai timestamp tuyệt đối khi khu vực có DST.

### 6.1. `LocalDateTime` không tự có múi giờ

`Duration.between(LocalDateTime, LocalDateTime)` đo chênh lệch các **trường giờ đồng hồ**, vì `LocalDateTime` không có `ZoneId`. Nếu hai giá trị bao quanh bước nhảy DST, kết quả có thể khác thời gian thực trôi qua.

```java
ZoneId paris = ZoneId.of("Europe/Paris");
LocalDateTime before = LocalDateTime.of(2024, 3, 31, 1, 30);
LocalDateTime after = LocalDateTime.of(2024, 3, 31, 3, 30);

Duration clockDifference = Duration.between(before, after);
// PT2H

Duration realDifference = Duration.between(
    before.atZone(paris).toInstant(),
    after.atZone(paris).toInstant());
// PT1H
```

Ngày 31/03/2024 tại Paris, đồng hồ chuyển từ giờ mùa đông sang giờ mùa hè, bỏ qua một khoảng giờ địa phương. “01:30 đến 03:30” trông giống 2 giờ nhưng hai instant thực chỉ cách **1 giờ**. Để đo elapsed time thực, hãy xác định đúng zone/offset của từng sự kiện trước khi tính `Duration.between`.

### 6.2. Chiều âm của `between` hữu ích cho deadline

```java
Instant deadline = Instant.parse("2024-05-01T10:00:00Z");
Instant now = Instant.parse("2024-05-01T10:00:02Z");

Duration remaining = Duration.between(now, deadline);
// PT-2S

boolean expired = remaining.isNegative() || remaining.isZero();
// true
```

Đừng lấy `remaining.abs()` trước khi kiểm tra hết hạn, vì khoảng âm sẽ bị biến thành số dương và làm mất dấu hiệu rằng deadline đã qua. Nếu bắt buộc hiển thị “quá hạn 2 giây”, chỉ khi đó mới lấy trị tuyệt đối cho mục đích trình bày.

## 7. Cộng, trừ, nhân, chia và tính bất biến

`Duration` là một lớp **immutable**, **thread-safe**, **value-based**. Các thao tác trả về giá trị mới; chúng không chỉnh sửa duration gốc:

```java
Duration base = Duration.ofSeconds(2);
Duration longer = base.plusMillis(250);  // PT2.25S
Duration shorter = base.minusNanos(1);  // PT1.999999999S

// base vẫn là PT2S.
```

Nhóm API tính toán bao gồm:

- `plus(Duration)`, `minus(Duration)`: cộng/trừ hai duration.
- `plusSeconds`, `plusMillis`, `plusNanos` và các biến thể cho phút, giờ, ngày chuẩn.
- `multipliedBy(long)`: nhân với hệ số nguyên, có thể đổi dấu.
- `dividedBy(long)`: chia thời lượng, độ phân giải thấp hơn một nano không thể biểu diễn và bị xử lý theo quy tắc chia.
- `negated()`: đổi dấu.
- `abs()`: độ lớn không âm, chỉ dùng khi thực sự cần.
- `withSeconds(long)`, `withNanos(int)`: thay **thành phần** của một bản sao, không phải cộng thêm.

```java
Duration a = Duration.ofSeconds(3);
Duration b = Duration.ofMillis(250);

Duration sum = a.plus(b);         // PT3.25S
Duration diff = a.minus(b);       // PT2.75S
Duration triple = b.multipliedBy(3); // PT0.75S
Duration neg = b.negated();       // PT-0.25S
```

**`withNanos(500_000_000)` khác `plusNanos(500_000_000)`**: phương thức đầu thay thành phần nano, phương thức sau cộng lượng nano. Không đặt lại trường giây/nano khi bạn thực sự chỉ muốn cộng một thời lượng.

Phép toán có thể thất bại nếu vượt dải biểu diễn, ví dụ cộng một giây vào duration đã ở giới hạn số giây kiểu `long`. Đừng nghĩ `Duration` không bao giờ tràn chỉ vì `getSeconds()` là `long`.

## 8. Đổi đơn vị, mất phần lẻ và giới hạn của `long`

| API | Kết quả | Điểm cần chú ý |
| --- | --- | --- |
| `toDays()` | Số ngày chuẩn 24h nguyên | Không phải tổng ngày lịch |
| `toHours()` | Số giờ nguyên | Bỏ phần nhỏ hơn giờ |
| `toMinutes()` | Số phút nguyên | Bỏ phần nhỏ hơn phút |
| `toMillis()` | Tổng số mili giây `long` | Bỏ nano nhỏ hơn 1ms; có thể tràn |
| `toNanos()` | Tổng nano giây `long` | Có thể tràn dù Duration hợp lệ |
| `getSeconds()` | Thành phần giây đã chuẩn hóa | Không phải luôn là số giây cắt về 0 nếu âm |
| `getNano()` | Phần nano trong một giây | Không phải tổng nano giây |

```java
Duration value = Duration.ofSeconds(90, 123_456_789);
long minutes = value.toMinutes(); // 1
long millis = value.toMillis();   // 90123
long nanos = value.toNanos();     // 90123456789
```

Chuyển sang đơn vị nguyên có thể **đánh mất thông tin**. `Duration.ofNanos(1).toMillis()` bằng `0`; điều đó không làm duration gốc biến thành 0. Không chuyển duration cần chính xác tới nano sang milliseconds trước khi so sánh theo yêu cầu nghiệp vụ.

### 8.1. `toNanos()` không bao phủ toàn miền `Duration`

Một `long` chứa tối đa khoảng 9,22×10¹⁸. Tổng nano giây vượt giới hạn này khi duration dài hơn khoảng **292 năm**; trong khi `Duration` vẫn có thể lưu phần giây kiểu `long` lớn hơn rất nhiều.

```java
Duration huge = Duration.ofDays(200_000);
// Duration hợp lệ.

// huge.toNanos(); // ArithmeticException: tổng ns vượt long.
```

Nếu cần lưu độ dài lớn với độ chính xác cao, dùng **cặp `getSeconds()` + `getNano()`**, hoặc biểu diễn `BigInteger` theo hợp đồng dữ liệu. Không tự nhân giây × 1_000_000_000 bằng `long` và mặc định giá trị không tràn.

### 8.2. `truncatedTo` và helper được bổ sung từ Java 9

`Duration.truncatedTo(TemporalUnit)` **chỉ có từ Java 9**, tương tự `toSeconds()` và nhóm `toDaysPart()`, `toHoursPart()`, `toMinutesPart()`, `toSecondsPart()`, `toMillisPart()`, `toNanosPart()`. Đây là API **hiện hành**, không phải legacy, nhưng không được gọi trong chương trình yêu cầu tương thích Java 8 gốc.

Ví dụ sau dành cho **Java 9+**, không phải phần của chương trình Java 8 ở mục 11:

```java
Duration positive = Duration.ofMillis(1_750);
Duration whole = positive.truncatedTo(ChronoUnit.SECONDS);
// PT1S

Duration negative = Duration.ofMillis(-1_500);
Duration negativeWhole = negative.truncatedTo(
    ChronoUnit.SECONDS);
// PT-1S
```

`truncatedTo` cắt về 0 tới đơn vị yêu cầu. Với khoảng âm `-1,5` giây, kết quả `-1` giây chứ không phải `-2` giây. Nếu dự án biên dịch bằng `javac --release 8`, đừng lén dùng `truncatedTo` trong mã Java 8; phải nâng mức API hoặc diễn đạt thao tác theo API Java 8 với chính sách cắt rõ ràng.

## 9. `Duration.ofDays(1)` và `Period.ofDays(1)` khác nhau qua DST

- `Duration.ofDays(1)` = **86.400 giây**, tức 24 giờ chuẩn.
- `Period.ofDays(1)` = **một ngày lịch** khi áp dụng vào kiểu ngày/giờ có ngữ cảnh.

Ở khu vực chuyển giờ mùa hè, hai phép có thể dẫn tới **cùng ngày nhưng giờ địa phương khác nhau**:

```java
ZoneId paris = ZoneId.of("Europe/Paris");
ZonedDateTime noon = ZonedDateTime.of(
    2024, 3, 30, 12, 0, 0, 0, paris);

ZonedDateTime nextCalendarNoon = noon.plusDays(1);
// 2024-03-31T12:00+02:00[Europe/Paris]

ZonedDateTime after24Hours = noon.plus(Duration.ofDays(1));
// 2024-03-31T13:00+02:00[Europe/Paris]
```

Đây là snippet trong method với import `java.time.*`. Paris chuyển DST ngày 31/03/2024; giữa **12:00 ngày 30/3** và **12:00 ngày 31/3** chỉ có 23 giờ tuyệt đối. Vì vậy “ngày mai cùng giờ địa phương” không đồng nghĩa “sau đúng 24 giờ”.

### 9.1. Độ dài thực của một ngày lịch

```java
LocalDate date = LocalDate.of(2024, 3, 31);
ZoneId paris = ZoneId.of("Europe/Paris");

Instant dayStart = date.atStartOfDay(paris).toInstant();
Instant nextDayStart = date.plusDays(1)
    .atStartOfDay(paris).toInstant();

long actualHours =
    Duration.between(dayStart, nextDayStart).toHours();
// 23
```

Một ngày địa phương cũng có thể dài 25 giờ khi DST kết thúc. Đối với báo cáo theo ngày của một địa điểm, tính ranh giới đầu ngày và đầu ngày tiếp theo theo zone, sử dụng khoảng nửa mở `[start, end)`. Không mặc định end = start + 24h.

### 9.2. `LocalDate` không phải timestamp để tính giây trực tiếp

`LocalDate` lưu ngày nhưng không lưu giờ/zone; `Duration.between(date1,date2)` không phải API thích hợp để lấy khoảng giây và có thể ném `UnsupportedTemporalTypeException`. Nếu cần **số ngày lịch**, dùng `Period.between` hoặc `ChronoUnit.DAYS.between` trên các ngày. Nếu cần **số giây thực**, xác định zone và ranh giới thành `Instant` trước khi dùng Duration.

## 10. Đo thời gian xử lý và thiết kế timeout

### 10.1. `System.nanoTime()` cho chênh lệch elapsed time

`System.nanoTime()` trả một số đếm có gốc tùy ý dành cho đo chênh lệch thời gian; không phải Unix timestamp. Chỉ sử dụng **hiệu số** giữa hai lần đọc:

```java
long started = System.nanoTime();

// Thực hiện một công việc ở đây.

long elapsedNanos = System.nanoTime() - started;
Duration elapsed = Duration.ofNanos(elapsedNanos);
```

Đoạn code là snippet, không có stdout cố định. Mặc dù số đếm có đơn vị nano, điều đó **không đảm bảo** đồng hồ thực có độ phân giải 1 ns. Khi benchmark thao tác Java ngắn, JIT, warm-up, GC và compiler có thể làm nhiễu; dùng JMH khi muốn kết luận về hiệu năng.

`Instant.now()` phù hợp ghi timestamp sự kiện. Nó lấy đồng hồ wall-clock có thể được đồng bộ/điều chỉnh; không nên coi hai lời gọi `Instant.now()` là một nguồn monotonic chuyên dụng để đo benchmark hoặc deadline nội bộ độ chính xác cao.

### 10.2. Đơn vị timeout và quy tắc số 0

`Duration timeout = Duration.ofMillis(750)` rõ ý nghĩa hơn một số `long timeout=750` không có đơn vị. Nhưng khi truyền sang một thư viện chỉ nhận millis:

- `timeout.toMillis()` có thể trả `0` nếu duration nhỏ hơn 1ms.
- Một số API hiểu timeout `0` là **chờ vô hạn**, một số khác là **không chờ**, vì vậy phải xem contract cụ thể.
- `toMillis()` có thể ném `ArithmeticException` nếu duration rất lớn.
- Duration âm cần được validate hoặc xử lý theo quy định của API đích.
- Nếu thư viện hỗ trợ overload nhận `Duration`, ưu tiên đường đó để tránh mất đơn vị và overflow khi tự đổi.

Không có một quy tắc timeout chung cho mọi JDBC, HTTP, executor hay network API; đây là trách nhiệm của lớp adapter gọi API cụ thể.

### 10.3. Deadline và thời lượng chờ không phải cùng kiểu dữ liệu

`Instant deadline` là **đến lúc nào**, còn `Duration timeout` là **đợi tối đa bao lâu**. Ở tầng domain, để rõ nghĩa:

```java
Instant deadline = Instant.parse("2024-05-01T10:00:00Z");
Instant current = Instant.parse("2024-05-01T09:59:57Z");

Duration remaining = Duration.between(current, deadline);
// PT3S
```

Nếu deadline do ứng dụng tự tạo cho vòng chờ ngắn bên trong tiến trình, nên dùng cơ chế monotonic/deadline của API nếu có. Nếu deadline là thời điểm trong tương lai do người dùng hoặc giao thức đưa vào, cần giải nghĩa thành `Instant` đúng, không tự gắn múi giờ mặc định cho chuỗi ngày giờ chưa có zone.

## 11. Chương trình đầy đủ có thể biên dịch bằng Java 8

Chương trình dưới đây kiểm tra trực tiếp các điểm then chốt: chuẩn hóa nano giây, duration âm, parse, khoảng `Instant`, sai khác DST, overflow và phép cộng bất biến. Nó dùng **chỉ API có từ Java 8**, không dùng `Duration.truncatedTo` (Java 9+), và không phụ thuộc ngày hiện tại hay timezone mặc định.

Lưu vào **DurationSecondsNanosDemo.java**:

```java
import java.time.Duration;
import java.time.Instant;
import java.time.LocalDate;
import java.time.LocalDateTime;
import java.time.ZoneId;

public class DurationSecondsNanosDemo {
    public static void main(String[] args) {
        Duration base = Duration.ofSeconds(90, 123_456_789);
        System.out.println("Base: " + base);
        System.out.println("Parts: " + base.getSeconds()
            + "s, " + base.getNano() + "ns");
        System.out.println("Base millis: " + base.toMillis());
        System.out.println("Base nanos: " + base.toNanos());

        System.out.println("Normalized: "
            + Duration.ofSeconds(1, 1_500_000_000L));

        Duration negative = Duration.ofNanos(-1);
        System.out.println("Negative 1ns parts: "
            + negative.getSeconds() + "," + negative.getNano());
        System.out.println("Negative 1ns total: "
            + negative.toNanos());
        System.out.println("Negative 1ms: "
            + Duration.ofMillis(-1));

        System.out.println("Parsed P1DT2H: "
            + Duration.parse("P1DT2H"));

        Instant start = Instant.parse(
            "2024-02-29T23:59:59.123456789Z");
        Instant end = Instant.parse(
            "2024-03-01T00:00:01.123456790Z");
        Duration diff = Duration.between(start, end);
        System.out.println("Between: " + diff);
        System.out.println("Reverse: "
            + Duration.between(end, start));
        System.out.println("Round trip: "
            + start.plus(diff).equals(end));

        System.out.println("36h toDays: "
            + Duration.ofHours(36).toDays());

        ZoneId paris = ZoneId.of("Europe/Paris");
        LocalDateTime before =
            LocalDateTime.of(2024, 3, 31, 1, 30);
        LocalDateTime after =
            LocalDateTime.of(2024, 3, 31, 3, 30);
        System.out.println("DST local: "
            + Duration.between(before, after));
        System.out.println("DST actual: "
            + Duration.between(
                before.atZone(paris).toInstant(),
                after.atZone(paris).toInstant()));

        LocalDate day = LocalDate.of(2024, 3, 31);
        Instant first = day.atStartOfDay(paris).toInstant();
        Instant next = day.plusDays(1)
            .atStartOfDay(paris).toInstant();
        System.out.println("Paris day hours: "
            + Duration.between(first, next).toHours());
        System.out.println("Standard day hours: "
            + Duration.ofDays(1).toHours());

        boolean overflow = false;
        try {
            Duration.ofDays(200_000).toNanos();
        } catch (ArithmeticException expected) {
            overflow = true;
        }
        System.out.println("Large toNanos overflow: " + overflow);
        System.out.println("Zero is zero: "
            + Duration.ZERO.isZero());
        System.out.println("Plus millis: "
            + Duration.ofSeconds(1).plusMillis(250));
    }
}
```

Biên dịch và chạy:

```bash
javac -encoding UTF-8 DurationSecondsNanosDemo.java
java DurationSecondsNanosDemo
```

**Stdout chính xác:**

```text
Base: PT1M30.123456789S
Parts: 90s, 123456789ns
Base millis: 90123
Base nanos: 90123456789
Normalized: PT2.5S
Negative 1ns parts: -1,999999999
Negative 1ns total: -1
Negative 1ms: PT-0.001S
Parsed P1DT2H: PT26H
Between: PT2.000000001S
Reverse: PT-2.000000001S
Round trip: true
36h toDays: 1
DST local: PT2H
DST actual: PT1H
Paris day hours: 23
Standard day hours: 24
Large toNanos overflow: true
Zero is zero: true
Plus millis: PT1.25S
```

### 11.1. Giải thích từng nhóm kết quả

- `base` là 90,123456789 giây. `toMillis` bỏ phần lẻ nhỏ hơn 1 ms, còn `toNanos` giữ chính xác toàn bộ độ dài vì tổng này nằm trong `long`.
- `ofSeconds(1,1_500_000_000)` tự chuẩn hóa thành 2,5 giây. Với âm 1 ns, `getSeconds==-1` và `getNano==999999999`, đúng theo công thức seconds+nanos.
- `Duration.parse("P1DT2H")` tính một ngày 24 giờ cộng 2 giờ và in `PT26H`.
- Hai `Instant` cố định cách nhau 2 giây + 1 ns; đảo chiều làm duration âm, và cộng khoảng vào mốc đầu cho đúng mốc cuối.
- 36 giờ chỉ có **một ngày chuẩn 24h nguyên**; `toDays` không trả `1,5` vì kết quả kiểu `long`.
- DST tại Paris tạo chênh lệch **2 giờ đồng hồ** nhưng **1 giờ thực**, đồng thời ngày địa phương 31/03/2024 chỉ dài 23 giờ.
- Một duration rất dài vẫn hợp lệ nhưng `toNanos` có thể tràn; chương trình bắt ngoại lệ và in boolean, tránh phụ thuộc thông điệp ngoại lệ của runtime.
- `Duration.ZERO` có độ dài 0, còn `plusMillis(250)` trên 1 giây tạo một đối tượng mới 1,25 giây.

## 12. Value-based, so sánh và dùng làm khóa dữ liệu

`Duration` là immutable và thread-safe. Hai duration có cùng độ dài là hai **giá trị có thể thay thế nhau**:

```java
Duration first = Duration.ofMillis(1000);
Duration second = Duration.ofSeconds(1);

boolean equal = first.equals(second); // true
boolean sameHash = first.hashCode() == second.hashCode();
// true
```

Không so bằng `==` để xác định hai duration có bằng nhau không, vì Java không cam kết object identity của value-based class. Không dùng `Duration` làm monitor `synchronized(duration)` hoặc dựa vào `System.identityHashCode(duration)`. `Duration.compareTo` và `equals` so **toàn bộ độ dài**, phù hợp việc xếp thứ tự/đặt ngưỡng.

Có thể dùng một `Duration` bất biến làm khóa `Map` trong ứng dụng có lý do nghiệp vụ rõ ràng; nhưng không nên lạm dụng identity hoặc tạo cấu trúc phức tạp chỉ để thay một trường timeout có tên rõ.

## 13. Các lỗi thường gặp khi làm việc với giây/nano giây

### 13.1. `getNano()` không phải tổng nano giây

**Sai:** lấy `duration.getNano()` làm thời gian thực thi tổng, bỏ qua thành phần giây. **Đúng:** dùng `toNanos` khi biết không tràn hoặc dùng seconds+nanos.

### 13.2. Tưởng duration âm phải có nano âm

**Sai:** kỳ vọng `Duration.ofNanos(-1).getNano() == -1`. **Đúng:** phần nano luôn không âm và được cộng với giây âm để tạo độ dài cuối.

### 13.3. Dùng `getSeconds()` để cắt về 0

**Sai:** suy ra `-1 ms` là `-1 giây nguyên đã cắt`. **Đúng:** `getSeconds` là thành phần chuẩn hóa; muốn cắt có chủ đích, dùng `truncatedTo` trên Java 9+ hoặc quy tắc khác được định nghĩa rõ.

### 13.4. Nhầm `Duration.ofDays(1)` với một ngày lịch

**Sai:** cộng 24 giờ qua DST rồi kỳ vọng cùng giờ địa phương ngày mai. **Đúng:** dùng `plusDays`/`Period` trên kiểu lịch có zone; Duration dùng cho 24 giờ thực.

### 13.5. Dùng `LocalDateTime` thiếu zone để tính elapsed time thực

**Sai:** lấy khoảng chênh giữa hai local time khác khu vực hoặc qua bước đổi DST rồi coi nó là chênh timeline. **Đúng:** đưa về `Instant` theo quy tắc zone rõ ràng.

### 13.6. Dùng `LocalDate` để tính giây không có giờ/zone

**Sai:** giả định mỗi ngày lịch có 86400 giây. **Đúng:** dùng `Period`/`ChronoUnit.DAYS` cho ngày lịch, hoặc chuyển ranh giới theo zone sang instant khi tính elapsed seconds.

### 13.7. Cho rằng `toMillis()` không mất độ chính xác

**Sai:** `Duration.ofNanos(1).toMillis() == 0` rồi suy ra duration bằng 0. **Đúng:** giữ độ chính xác phù hợp và so `Duration.equals`.

### 13.8. Không kiểm soát tràn số

**Sai:** mọi duration hợp lệ đều chuyển được thành tổng `long nanos`. **Đúng:** giới hạn miền giá trị, xử lý `ArithmeticException`, hoặc dùng cặp seconds+nanos.

### 13.9. Timeout 0 không nhất thiết nghĩa là “không chờ”

Ý nghĩa số 0 phụ thuộc API; có API coi nó là **vô hạn**. Sau khi `toMillis()` làm khoảng rất ngắn về 0, có thể gây lỗi vận hành. Kiểm tra contract và chính sách rounding.

### 13.10. Dùng `Instant.now()` như đồng hồ benchmark monotonic

`Instant.now()` là wall clock. `System.nanoTime()` có gốc tùy ý nhưng thích hợp tính elapsed; dùng hiệu số và tránh so trực tiếp với epoch. Với benchmark yêu cầu chính xác, dùng JMH.

### 13.11. Dùng `truncatedTo` trong Java 8

`Duration.truncatedTo` **ra mắt Java 9**. Mã compile `--release 8` sẽ báo không có method. Đừng nhầm “API vẫn áp dụng trên JDK hiện đại” với “API đã có trong Java 8”.

### 13.12. So sánh chuỗi ISO thay vì giá trị thời lượng

`Duration.parse("P1DT2H")` và `Duration.parse("PT26H")` có cùng độ dài. So `String` theo mặt chữ sẽ cho khác nhau. So `Duration.equals`.

## 14. Quyết định theo từng tình huống

| Trường hợp | Khuyến nghị | Tránh |
| --- | --- | --- |
| Timeout HTTP là 750ms | `Duration.ofMillis(750)` | Số `750` không ghi đơn vị |
| Tính 2,5 giây chính xác | `Duration.ofSeconds(2,500_000_000)` | `double` không có quy tắc làm tròn |
| Đo elapsed ngắn | `System.nanoTime()` hiệu số → `Duration.ofNanos` | Lưu `nanoTime()` như timestamp |
| Hai timestamp UTC | `Duration.between(Instant,Instant)` | Bỏ offset rồi tính local |
| Thêm một ngày lịch | `ZonedDateTime.plusDays(1)` | `Duration.ofDays(1)` qua DST |
| Tìm số tháng lịch | `Period`/`ChronoUnit.MONTHS` | Chia số giây theo 30 ngày |
| Lưu duration dài và chính xác | Cặp seconds+nanos | Ép tổng nano vào `long` khi vượt giới hạn |
| Chuỗi config portable | `PT0.75S` với `Duration.parse` | `750ms` nếu không có parser riêng |
| Kiểm tra deadline đã qua | `Duration.between(now,deadline).isNegative()` | Luôn gọi `abs()` |
| Chuyển xuống milliseconds | `toMillis` với kiểm tra độ chính xác/overflow | Tin rằng mọi nano được giữ |
| Code nhắm Java 8 | `getSeconds`, `getNano`, `toMillis`, `toNanos` | `truncatedTo`, `toSeconds`, `to...Part` |
| Code Java 17+ | Có thể dùng thêm `truncatedTo`, các helper Part | Quên kiểm tra phiên bản khi backport |

## 15. Câu hỏi tự luyện và lời giải

1. **`Duration.ofNanos(-1).getSeconds()` và `getNano()`?** → `-1` và `999999999`. Cặp này biểu diễn đúng âm 1 nano giây.
2. **`Duration.ofSeconds(1,1_500_000_000L)` hợp lệ không?** → Có. Kết quả được chuẩn hóa thành `PT2.5S`.
3. **`Duration.ofDays(1)` dài bao nhiêu giây?** → Chính xác `86400` giây, theo ngày chuẩn 24h.
4. **`Duration.ofHours(36).toDays()`?** → `1` ngày nguyên theo quy tắc 24h/ngày.
5. **`Duration.between(a,b)` đổi thứ tự thành `between(b,a)`?** → Đảo dấu, giữ độ lớn nếu tính được và không vượt miền.
6. **`Duration.ofNanos(1).toMillis()`?** → `0`, vì độ dài nhỏ hơn mili giây.
7. **Vì sao `toNanos` có thể ném exception?** → Tổng nano giây không luôn nằm trong `long` dù seconds+nanos hợp lệ.
8. **Paris 01:30→03:30 ngày 31/03/2024, elapsed thực bao lâu?** → `1` giờ; nếu chỉ trừ `LocalDateTime` sẽ thấy `2` giờ.
9. **Chọn Duration hay Period cho “một tháng nữa”?** → `Period.ofMonths(1)` hoặc `plusMonths` trên kiểu lịch thích hợp.
10. **`Duration.parse("P1DT2H").toString()`?** → `PT26H`, vì ngày được tính thành 24 giờ.
11. **Có được dùng `Duration.truncatedTo` khi compile `--release 8`?** → Không; method xuất hiện từ Java 9.
12. **Duration có đảm bảo đồng hồ hệ thống chính xác 1 ns?** → Không; nó có độ phân giải biểu diễn tới 1ns, nguồn đo có thể kém chính xác hơn.
13. **`System.nanoTime()` có phải Unix timestamp?** → Không; chỉ dùng hiệu số cho elapsed time.
14. **`Duration.ZERO.isZero()` trả gì?** → `true`; `isNegative()` trả `false`.
15. **Thiết kế API chờ 500ms sao cho không mơ hồ?** → Truyền `Duration.ofMillis(500)`, hoặc tham số số có tên `timeoutMillis` và contract rõ ràng.

## 16. Tài liệu chính thức (các API còn được duy trì)

Những API có trong Java 8 và những API ra mắt Java 9+ đã được phân biệt rõ trong bài; các nguồn kiểm tra hiện hành:

- [`Duration` — Java SE 26 API](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/time/Duration.html): seconds+nanos, số âm, `between`, `parse`, `truncatedTo` và phép đổi đơn vị.
- [`Duration` — Java SE 9 API](https://docs.oracle.com/javase/9/docs/api/java/time/Duration.html): đối chiếu mốc `Since: 9` của `truncatedTo` và helper mới.
- [`Instant` — Java SE 26 API](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/time/Instant.html): mốc tuyệt đối trên timeline và phần nano giây.
- [`Period` — Java SE 26 API](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/time/Period.html): khoảng theo ngày-tháng-năm lịch.
- [`ZonedDateTime` — Java SE 26 API](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/time/ZonedDateTime.html): cộng giờ thực và cộng ngày lịch theo zone.
- [`LocalDateTime` — Java SE 26 API](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/time/LocalDateTime.html): giá trị ngày-giờ không chứa zone.
- [`ChronoUnit` — Java SE 26 API](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/time/temporal/ChronoUnit.html): các đơn vị thời gian chính xác và đơn vị ước lượng.
- [`System.nanoTime()` — Java SE 26 API](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/System.html): phép đo chênh lệch có gốc tùy ý.
- [JMH — OpenJDK Microbenchmark Harness](https://openjdk.org/projects/code-tools/jmh/): benchmark Java có warm-up và measurement đúng phương pháp.
