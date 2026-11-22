# Giới hạn ngày giờ hỗ trợ trong Java: Instant, OffsetDateTime và ZoneOffset

## 1. Mục tiêu và nguyên tắc chọn kiểu

Các lớp `java.time` không có cùng miền giá trị. Một thời điểm có thể biểu diễn hợp lệ bằng `Instant` nhưng không thể đổi sang `LocalDateTime`; một `Instant` có thể chứa năm rất xa nhưng **không thể** chuyển thành `long` epoch milliseconds; một `ZoneOffset` chỉ chấp nhận độ lệch UTC trong miền đã định. Vì vậy, **giới hạn ngày giờ hỗ trợ** không thể trả lời bằng một con số áp dụng cho mọi lớp.

Bài này tập trung vào nhóm **Instant và offset**, đồng thời đối chiếu giới hạn của `LocalDate`, `LocalTime`, `LocalDateTime` và `OffsetDateTime` để hiểu các điểm giao nhau. Toàn bộ API được dùng đều còn áp dụng trong Java hiện đại. Chương trình kiểm thử hoàn chỉnh dùng **Java 17+**, còn các lớp ngày giờ cơ bản đã có từ Java 8.

Sau bài học, bạn cần:

1. Phân biệt **instant tuyệt đối**, **ngày/giờ cục bộ** và **độ lệch UTC (offset)**, tránh áp giới hạn của một kiểu cho kiểu khác.
2. Nhớ các mốc `Instant.MIN/MAX`, `LocalDate.MIN/MAX`, `LocalDateTime.MIN/MAX`, `ZoneOffset.MIN/MAX`, `OffsetDateTime.MIN/MAX` và lý do chúng khác nhau.
3. Phân biệt **giới hạn kiểu Java**, **giới hạn biểu diễn số epoch** và **giới hạn định dạng/lưu trữ của hệ thống bên ngoài**.
4. Nắm lỗi tại biên: `DateTimeException` khi vượt phạm vi ngày giờ, `ArithmeticException` khi số học hoặc chuyển đơn vị bị tràn.
5. Nhận diện rủi ro đổi `Instant` sang giờ tại một offset hoặc vùng địa lý, đặc biệt ở năm cực trị.
6. Hiểu lịch ISO proleptic Gregorian, năm 0, năm âm, năm nhuận, và ý nghĩa khi dữ liệu có niên đại lịch sử.
7. Thiết kế validate đầu vào và quy tắc bảo toàn độ chính xác nano giây, offset, múi giờ.
8. Kiểm thử boundary/round-trip bằng các giá trị cố định, không phụ thuộc đồng hồ hệ thống.

## 2. Phân biệt phạm vi của các kiểu ngày giờ

| Kiểu Java | Chứa những gì | Có ngày? | Có offset/zone? | Mục đích |
| --- | --- | --- | --- | --- |
| `Instant` | Giây kể từ epoch UTC và phần nano giây | Là một thời điểm trên timeline, không lưu trường ngày địa phương | Có mốc timeline UTC, không lưu `ZoneId` | Lưu event timestamp, so thứ tự thời điểm |
| `LocalDate` | Năm, tháng, ngày theo lịch ISO | Có | Không | Ngày sinh, ngày làm việc |
| `LocalTime` | Giờ, phút, giây, nano giây | Không | Không | Giờ mở cửa, giờ trong ngày |
| `LocalDateTime` | `LocalDate` + `LocalTime` | Có | Không | Ngày giờ địa phương chưa gắn zone |
| `ZoneOffset` | Độ lệch cố định so với UTC | Không | Chính là offset | Chuyển ngày giờ địa phương sang instant |
| `OffsetDateTime` | `LocalDateTime` + `ZoneOffset` | Có | Có fixed offset, không có quy tắc vùng | Timestamp trong API/protocol cần offset |
| `ZonedDateTime` | `LocalDateTime` + `ZoneId` + offset hợp lệ | Có | Có quy tắc múi giờ vùng | Lịch hẹn theo khu vực có DST |

**Phân biệt `ZoneOffset` và `ZoneId`:** `+07:00` là một độ lệch cố định, còn `Asia/Ho_Chi_Minh` là một mã vùng gắn với bộ quy tắc giờ theo từng thời kỳ. `ZoneId` có thể chứa nhiều offset khác nhau theo thời gian và dữ liệu tzdb. Không thể thay mọi `ZoneId` bằng một `ZoneOffset` nếu cần quy tắc mùa/historic.

**Phân biệt `LocalDateTime` và `Instant`:** `2026-03-01T07:30` không cho biết đang là giờ ở Hà Nội, Tokyo hay nơi khác, nên chưa xác định duy nhất một instant. `2026-03-01T00:30:00Z` là một thời điểm cụ thể, có thể hiển thị thành giờ địa phương khác nhau.

## 3. Bảng giới hạn được hỗ trợ bởi java.time

Những hằng số dưới đây là **API công khai**, khác với giới hạn do database hoặc framework tự đặt. Các chuỗi là biểu diễn dạng ISO của các hằng số tương ứng.

| Kiểu/giới hạn | Giá trị nhỏ nhất | Giá trị lớn nhất |
| --- | --- | --- |
| `LocalDate` | `-999999999-01-01` | `+999999999-12-31` |
| `LocalDateTime` | `-999999999-01-01T00:00` | `+999999999-12-31T23:59:59.999999999` |
| `LocalTime` | `00:00` | `23:59:59.999999999` |
| `Instant` | `-1000000000-01-01T00:00:00Z` | `+1000000000-12-31T23:59:59.999999999Z` |
| `ZoneOffset` | `-18:00` | `+18:00` |
| `OffsetDateTime` | `-999999999-01-01T00:00+18:00` | `+999999999-12-31T23:59:59.999999999-18:00` |

Các hằng số Java tương ứng:

```java
Instant.MIN;
Instant.MAX;
LocalDate.MIN;
LocalDate.MAX;
LocalDateTime.MIN;
LocalDateTime.MAX;
LocalTime.MIN;
LocalTime.MAX;
ZoneOffset.MIN;
ZoneOffset.MAX;
OffsetDateTime.MIN;
OffsetDateTime.MAX;
```

Đây là **biểu thức tham chiếu hằng số** để đọc, không phải các statement hữu ích để chạy độc lập. Có thể `System.out.println(Instant.MIN)` hoặc so với giá trị thực trong chương trình.

### 3.1. Vì sao giới hạn `Instant` lớn hơn `LocalDateTime` một năm?

`LocalDateTime` hỗ trợ năm từ `-999_999_999` đến `+999_999_999`. `Instant` hỗ trợ các mốc thời gian từ năm `-1_000_000_000` đến `+1_000_000_000` tính theo UTC.

Thiết kế này cấp thêm khoảng biên để phục vụ thao tác chuyển đổi với `ZoneOffset`, bởi offset có thể làm giờ cục bộ khác ngày hoặc năm UTC. **Không** có nghĩa mọi Instant ở sát hai biên đều đổi được thành `LocalDateTime` tại bất kỳ ZoneId nào.

Ví dụ `Instant.MAX` là một giá trị hoàn toàn hợp lệ, nhưng:

```java
LocalDateTime.ofInstant(Instant.MAX, ZoneOffset.UTC);
```

sẽ ném `DateTimeException` vì ngày giờ tại UTC thuộc năm `1_000_000_000`, vượt giới hạn năm `+999_999_999` của `LocalDateTime`.

**Điểm rút ra:** “Đã tạo được một `Instant`” **không** tự bảo đảm “có thể tạo `LocalDateTime` hoặc `OffsetDateTime` từ nó”.

### 3.2. Vì sao `OffsetDateTime.MIN` dùng `+18:00`, còn `MAX` dùng `-18:00`?

Công thức:

```text
Instant = LocalDateTime - ZoneOffset
```

Theo đó:

- Với cùng ngày giờ cục bộ, offset **dương hơn** tương ứng thời điểm UTC **sớm hơn**.
- Offset **âm hơn** tương ứng thời điểm UTC **muộn hơn**.

Vì vậy, `OffsetDateTime.MIN` ghép `LocalDateTime.MIN` với `ZoneOffset.MAX` (`+18:00`), còn `OffsetDateTime.MAX` ghép `LocalDateTime.MAX` với `ZoneOffset.MIN` (`-18:00`). Đây là hai biên theo **timeline**, không đơn giản là ghép offset có tên `MIN` cho thời gian sớm nhất.

```java
boolean earliest = OffsetDateTime.MIN.equals(
        OffsetDateTime.of(LocalDateTime.MIN, ZoneOffset.MAX));
boolean latest = OffsetDateTime.MAX.equals(
        OffsetDateTime.of(LocalDateTime.MAX, ZoneOffset.MIN));
// Cả hai là true.
```

Đây là đoạn minh họa với `import java.time.*;`.

### 3.3. Mọi ngày hợp lệ có nằm giữa năm 1 và 9999 không?

**Không.** `java.time.LocalDate` hỗ trợ năm âm, năm 0 và năm lớn hơn 9999 trong giới hạn nêu trên. Các năm ISO sử dụng **proleptic year**.

Nhưng không đồng nghĩa cơ sở dữ liệu, bộ định dạng hay quy định của hệ thống chấp nhận toàn bộ các năm này. Ví dụ một API đặt chính sách chỉ nhận năm 1900–2100 vẫn có quyền từ chối `LocalDate.of(2500,1,1)`, dù object Java hợp lệ.

Đừng dùng giới hạn kiểu Java như lời cam kết rằng mọi hợp đồng nghiệp vụ đều nên nhận các năm cách hiện tại hàng trăm triệu năm.

## 4. `Instant` lưu thời điểm bằng giây và nano giây

`Instant` dùng hai thành phần:

1. `long epochSecond`: số giây kể từ `1970-01-01T00:00:00Z`, có thể âm khi trước epoch.
2. `int nano`: phần nano giây **trong giây** từ `0` tới `999_999_999`.

Số epochSecond trong một `Instant` **không được phép chạy hết miền số `long`**, vì bản thân `Instant` giới hạn theo năm ±1 tỷ.

Ví dụ:

```java
Instant event = Instant.parse("2026-03-01T00:30:00.125Z");

long sec = event.getEpochSecond();
int nano = event.getNano(); // 125_000_000
```

Đây là đoạn minh họa, `nano` là phần giây. Không có nghĩa `epochSecond` chứa cả số nano giây.

### 4.1. Các factory và giới hạn kiểu số

| API | Đầu vào | Giới hạn/điều cần nhớ |
| --- | --- | --- |
| `Instant.ofEpochSecond(long)` | Giây từ epoch | Vẫn phải nằm trong phạm vi Instant.MIN..MAX |
| `Instant.ofEpochSecond(long, long)` | Giây và điều chỉnh nano | Nano adjustment có thể âm/lớn, được chuẩn hóa; kết quả vẫn phải trong phạm vi |
| `Instant.ofEpochMilli(long)` | Milliseconds từ epoch | Mọi giá trị `long` milliseconds nằm trong phạm vi `Instant` |
| `Instant.parse(CharSequence)` | Chuỗi có thông tin UTC/offset tương thích ISO instant | Formatter, year và instant range đều phải hợp lệ |
| `Instant.now(Clock)` | Nguồn thời gian được cung cấp | Dùng cho test deterministic |

`Instant.ofEpochSecond(Long.MAX_VALUE)` **không hợp lệ** chỉ vì tham số là `long`. Nó vượt phạm vi timeline của `Instant` và gây `DateTimeException`. Ngược lại, `Instant.ofEpochMilli(Long.MAX_VALUE)` hợp lệ, vì milliseconds có tỷ lệ nhỏ hơn rất nhiều so với giây.

### 4.2. Epoch âm và sự chuẩn hóa phần nano

Đây là lỗi kinh điển khi chuyển timestamp trước năm 1970:

```java
Instant beforeEpoch = Instant.ofEpochMilli(-1);
// 1969-12-31T23:59:59.999Z

long epochSecond = beforeEpoch.getEpochSecond(); // -1
int nanoPart = beforeEpoch.getNano();            // 999_000_000
```

Nó không có `epochSecond=0` và `nano=-1_000_000`, vì phần nano giây của `Instant` luôn **không âm**. Nếu lưu timestamp bằng hai cột seconds/nanos, phải tuân thủ quy tắc chuẩn hóa thay vì tự ghép trừ/nhân không kiểm soát.

Đối với `Instant.ofEpochSecond(-1, 1)`, thời điểm là **1 nano giây sau 1969-12-31T23:59:59Z**, tức vẫn trước epoch gần 1 giây. Không được nhầm phần nano dương với “sau epoch”.

### 4.3. Độ chính xác tới nano không phải đồng hồ chính xác nano

`Instant` hỗ trợ biểu diễn nanoseconds, nhưng `Instant.now()` phụ thuộc nguồn clock và OS. Có hệ thống chỉ cung cấp milliseconds hoặc microseconds; những chữ số nano còn lại có thể là 0. Bộ API hỗ trợ lưu precision cao **không** chứng minh phép đo thực đã đạt precision đó.

Không dùng `Instant.now()` như một đồng hồ đo thời gian **monotonic** để benchmark thời lượng tác vụ ngắn: thời gian tường có thể bị đồng bộ/chỉnh. Với đo thời lượng ngắn trong JVM, `System.nanoTime()` phù hợp hơn, nhưng **giá trị nanoTime không là timestamp epoch** và không dùng để tạo một Instant bằng phép cộng trực tiếp.

## 5. Giới hạn khi chuyển sang epoch milliseconds và nanoseconds

### 5.1. `Instant.MAX` không đổi được thành `long` epoch milliseconds

`Instant` có phạm vi gần ±1 tỷ năm, nhưng `long` milliseconds chỉ biểu diễn khoảng ±292 triệu năm so với epoch. Do đó:

```java
Instant.MAX.toEpochMilli();
```

ném `ArithmeticException` do kết quả không thể chứa trong một `long`. **Đừng giả định** vì object Instant hợp lệ nên mọi phép chuyển về một số nguyên đều hợp lệ.

Ngược lại:

```java
Instant.ofEpochMilli(Long.MAX_VALUE);
Instant.ofEpochMilli(Long.MIN_VALUE);
```

đều là những Instant hợp lệ trong giới hạn Java. Nhưng điều này không có nghĩa `LocalDateTime` hay định dạng database có thể biểu diễn mọi giá trị đó mà không kiểm tra.

### 5.2. Đổi sang milliseconds làm mất precision

`Instant.toEpochMilli()` trả về milliseconds, không bảo toàn các phần nhỏ hơn 1 millisecond. Ví dụ:

```java
Instant original = Instant.parse("2026-03-01T00:30:00.123456789Z");
long millis = original.toEpochMilli();
Instant restored = Instant.ofEpochMilli(millis);

boolean same = original.equals(restored); // false
```

Khoảng `456_789` nano giây sau millisecond thứ 123 đã mất. Nếu ứng dụng cần thứ tự sự kiện tới nano giây, hãy lưu `epochSecond + nano` hoặc một định dạng dữ liệu hỗ trợ độ chính xác cần thiết, không chỉ epoch milliseconds.

Với mốc trước epoch, phép chia số âm dễ khiến kết quả bất ngờ nếu bạn tự triển khai. Hãy dùng các API `Instant.ofEpochMilli`, `toEpochMilli` và kiểm thử mốc âm thay vì tự tính `seconds * 1000 + nano / 1_000_000` mà không xét overflow và quy tắc dấu.

### 5.3. `Duration.toNanos()` còn bị giới hạn hơn

`Duration` lưu số giây và phần nano, nhưng `duration.toNanos()` trả **một `long`**. Vì số nano giây trong một khoảng dài rất lớn, nó có thể ném `ArithmeticException`:

```java
Duration distant = Duration.between(Instant.EPOCH, Instant.MAX);
distant.toNanos(); // ArithmeticException do overflow
```

Trong khi đó, bản thân `distant` có thể được tạo hợp lệ. Nếu một duration dài cần trình bày/tính tiếp, giữ dạng `Duration` hoặc xử lý giây và nano riêng, dùng số học kiểm tra overflow.

**Không đồng nhất:** khả năng tạo đối tượng thời gian và khả năng biến nó thành **một scalar `long` theo đơn vị rất nhỏ** là hai giới hạn khác nhau.

## 6. `ZoneOffset`: biên ±18 giờ, không phải một múi giờ khu vực

`java.time.ZoneOffset` đại diện một độ lệch cố định so với UTC, trong khoảng:

```text
ZoneOffset.MIN = -18:00 = -64_800 giây
ZoneOffset.UTC = Z      = 0 giây
ZoneOffset.MAX = +18:00 = +64_800 giây
```

Các cách tạo:

```java
ZoneOffset utc = ZoneOffset.UTC;
ZoneOffset vietnam = ZoneOffset.of("+07:00");
ZoneOffset fiveThirty = ZoneOffset.ofHoursMinutes(5, 30);
ZoneOffset custom = ZoneOffset.ofTotalSeconds(5 * 3600 + 30 * 60);
```

**Vì sao offset tối đa không chỉ là ±12 hay ±14 giờ?** Các offset ngoài khoảng thường gặp vẫn có thể được biểu diễn theo API, nhưng Java chọn giới hạn rộng **±18 giờ** để có không gian cho lịch sử và các quy định có thể thay đổi. Không nên mặc định mỗi giá trị ±18 là offset hiện hành của một địa điểm.

### 6.1. Những đầu vào vượt biên bị từ chối

```java
ZoneOffset.ofHours(19);          // DateTimeException
ZoneOffset.ofHoursMinutes(18, 1); // DateTimeException
ZoneOffset.ofTotalSeconds(64_801); // DateTimeException
```

Đây là các ví dụ **cố ý gây lỗi**; không được đặt cùng happy path mà không xử lý exception. Khi phần giờ đã là +18 hoặc -18 thì phần phút/giây phải bằng 0, nếu không vượt quá biên.

`ZoneOffset.ofHoursMinutes(hours,minutes)` cũng có quy tắc dấu nhất quán giữa hour và minute, ví dụ offset `-03:30` phải dùng `ofHoursMinutes(-3,-30)`, không dùng `(-3,30)`.

### 6.2. Offset chỉ là một phần của bài toán zone

Một offset `+01:00` không đủ để biết đó là giờ Paris, London hay một vùng khác, cũng không cho biết DST trong ngày cụ thể. `ZoneId.of("Europe/Paris")` tham chiếu bộ quy tắc thay đổi offset theo thời gian; `ZoneOffset.of("+01:00")` thì không.

Nếu hệ thống nhận lịch hẹn ở một khu vực, nên lưu **ZoneId của khu vực** và LocalDateTime/instant phù hợp. Nếu hệ thống nhận một log sự kiện có offset cụ thể và không cần tái dựng quy tắc lịch khu vực, `OffsetDateTime` có thể phù hợp.

### 6.3. Offset làm thay đổi ngày và năm khi quy đổi

Một `LocalDateTime` sát nửa đêm có thể rơi vào ngày trước hoặc ngày sau khi chuyển sang UTC, tùy offset:

```java
OffsetDateTime local = OffsetDateTime.parse("2026-03-01T07:30:00+07:00");
Instant instant = local.toInstant();
// 2026-03-01T00:30:00Z
```

Đây là phép đổi **giữ nguyên thời điểm tuyệt đối** nhưng thay thông tin biểu diễn. Gần biên năm tối thiểu/tối đa, thay đổi offset có thể khiến local date vượt khỏi miền của `LocalDateTime`, làm phép chuyển đổi bị từ chối.

## 7. Ranh giới `OffsetDateTime` và cách so sánh

`OffsetDateTime` chứa cả local date-time và offset. Nó có thể biểu diễn:

```java
OffsetDateTime early = OffsetDateTime.MIN;
// -999999999-01-01T00:00+18:00

OffsetDateTime late = OffsetDateTime.MAX;
// +999999999-12-31T23:59:59.999999999-18:00
```

Bản thân `OffsetDateTime` là immutable và thread-safe. Các phương thức `with...`, `plus...` trả object mới; nếu một phép cộng làm ngày cục bộ vượt miền, nó có thể ném `DateTimeException`.

### 7.1. `withOffsetSameInstant` khác `withOffsetSameLocal`

Có một giá trị:

```java
OffsetDateTime original = OffsetDateTime.parse(
        "2026-03-01T07:30:00+07:00");

OffsetDateTime sameInstant = original.withOffsetSameInstant(
        ZoneOffset.UTC);
// 2026-03-01T00:30Z

OffsetDateTime sameLocal = original.withOffsetSameLocal(
        ZoneOffset.UTC);
// 2026-03-01T07:30Z
```

| Thao tác | Giữ nguyên cái gì? | Có giữ nguyên `Instant`? |
| --- | --- | --- |
| `withOffsetSameInstant(newOffset)` | Cùng một **thời điểm** trên timeline | Có |
| `withOffsetSameLocal(newOffset)` | Cùng **ngày giờ hiển thị** | Không, trừ khi offset mới bằng cũ |

Đừng chọn một trong hai chỉ vì tên giống nhau. Trong giao dịch tài chính, audit log hoặc event timestamp, thường cần bảo toàn instant. Trong lịch hẹn dân dụng, có trường hợp muốn bảo toàn local time, nhưng phải ghi rõ vùng/offset của người dùng.

### 7.2. `equals`, `isEqual` và `compareTo`

Hai `OffsetDateTime` ở các offset khác nhau có thể biểu diễn **cùng một Instant**:

```java
OffsetDateTime hcm =
        OffsetDateTime.parse("2026-03-01T07:30:00+07:00");
OffsetDateTime utc =
        OffsetDateTime.parse("2026-03-01T00:30:00Z");

boolean samePoint = hcm.toInstant().equals(utc.toInstant()); // true
boolean sameByIsEqual = hcm.isEqual(utc);                    // true
boolean sameObjectValue = hcm.equals(utc);                  // false
```

`equals` so các thành phần date-time và offset, nên khác offset thì thường không bằng nhau dù cùng instant. `isEqual` dựa trên instant. `OffsetDateTime.compareTo` so theo instant trước, rồi có bước so local date-time khi hai instant trùng để nhất quán với equals; nếu chỉ muốn thứ tự timeline, có `OffsetDateTime.timeLineOrder()`.

**Không dùng `==`** cho các object `java.time` kiểu value-based; so `equals` hoặc comparator phù hợp.

### 7.3. Chuyển đổi ở biên có thể thất bại

`OffsetDateTime.ofInstant(instant, offset)` phải tạo được một `LocalDateTime` sau khi áp offset. `Instant.MAX` vẫn nằm trên timeline hợp lệ, nhưng năm của thời điểm UTC đó vượt `LocalDateTime.MAX`, nên không thể cứ chuyển sang `OffsetDateTime` ở UTC.

Tương tự, `withOffsetSameInstant(...)` có thể ném `DateTimeException` nếu offset mới khiến local time vượt phạm vi năm. Phải xử lý điều này như **lỗi dữ liệu/miền biểu diễn**, không dùng một offset tùy ý làm fallback có thể âm thầm đổi instant.

## 8. Lịch ISO: năm 0, năm âm, năm nhuận và lịch sử

### 8.1. Proleptic Gregorian là gì?

`LocalDate` theo `ISO-8601` sử dụng **proleptic Gregorian calendar**: quy tắc lịch Gregorian hiện đại được kéo ngược về quá khứ, kể cả những thời kỳ trước khi lịch Gregorian được áp dụng ở các quốc gia. Điều này thích hợp cho tính toán nhất quán của API, nhưng **không tự bảo đảm đúng lịch sử dân sự địa phương** ở thời kỳ cổ/đổi lịch.

Ví dụ:

```java
LocalDate yearZeroLeapDay = LocalDate.of(0, 2, 29);
// Hợp lệ trong ISO proleptic Gregorian.
```

Năm 0 là một năm nhuận theo quy tắc Gregorian proleptic vì chia hết cho 400. Nhưng trong cách ghi năm “trước Công nguyên” của một số nguồn lịch sử, **không tồn tại năm 0**. Quy đổi cách ghi năm lịch sử sang năm ISO proleptic phải được làm theo quy tắc rõ ràng:

| Cách diễn đạt năm | Proleptic ISO year |
| --- | ---: |
| 1 CE | `1` |
| 1 BCE | `0` |
| 2 BCE | `-1` |

Không viết `LocalDate.of(-1,1,1)` và ghi nhãn “1 BCE” mà không hiểu phép quy đổi này. `-1` trong hệ proleptic là **2 BCE**.

### 8.2. Quy tắc năm nhuận, ngày hợp lệ

Trong lịch ISO Gregorian:

- Năm chia hết cho 4 thường là năm nhuận.
- Năm chia hết cho 100 **không** nhuận, trừ khi chia hết cho 400.
- Vì vậy năm 2000 nhuận, năm 1900 không nhuận.

`LocalDate.of(2026,2,29)` sẽ ném `DateTimeException` vì năm 2026 không nhuận. `LocalDate.of(2024,2,29)` hợp lệ.

Dù năm nằm trong miền ±999.999.999, tháng/ngày cũng phải phù hợp lịch. **Năm hợp lệ không đồng nghĩa mọi tổ hợp month/day hợp lệ**.

### 8.3. Format năm lớn, năm âm và năm 0

`LocalDate.toString()` và formatter ISO_LOCAL_DATE có thể in thêm dấu cho năm ngoài `0000..9999`:

```java
LocalDate.MAX.toString(); // "+999999999-12-31"
LocalDate.MIN.toString(); // "-999999999-01-01"
LocalDate.of(0,1,1).toString(); // "0000-01-01"
```

Khi định dạng tùy biến:

- `uuuu` là **proleptic year**, có thể bao gồm năm 0.
- `yyyy` là **year-of-era**, không tương đương `uuuu` với năm 0/BCE.
- `YYYY` là **week-based-year**, có thể khác calendar year gần ranh giới đầu/cuối năm.

Vì vậy đừng thay `uuuu-MM-dd` bằng `yyyy-MM-dd` hoặc `YYYY-MM-dd` mà không hiểu hệ năm. Với giao tiếp dữ liệu dùng `DateTimeFormatter.ISO_LOCAL_DATE`/`ISO_INSTANT` hoặc format chuẩn đã cam kết.

**Giới hạn formatter không đồng nhất với miền của object:** Một số pattern hoặc bộ formatter chỉ cho phép năm 4 chữ số, trong khi `LocalDate` lưu được năm nhiều chữ số. Nếu parser/gateway chỉ chấp nhận `YYYY-MM-DD` cố định, cần kiểm tra riêng hợp đồng đó.

## 9. Lỗi vượt giới hạn và cách xử lý

### 9.1. `DateTimeException`: giá trị ngày giờ không thể biểu diễn

Các trường hợp:

```java
LocalDate.MAX.plusDays(1);            // DateTimeException.
Instant.MAX.plusNanos(1);             // DateTimeException.
LocalDate.of(2026, 2, 29);            // DateTimeException.
ZoneOffset.ofHoursMinutes(18, 1);     // DateTimeException.
LocalDateTime.ofInstant(
        Instant.MAX, ZoneOffset.UTC); // DateTimeException.
```

Đây là **đoạn anti-example**, mỗi dòng cố ý có thể ném ngoại lệ. Khi dùng sản xuất, catch ở ranh giới xử lý input hoặc validate trước, không ghép chúng vào một happy path.

`DateTimeParseException` là subtype của `DateTimeException` dành cho việc parse chuỗi không phù hợp formatter. Nhưng thông báo lỗi có thể thay đổi theo JDK và locale, không nên biến stack trace thành hợp đồng API.

### 9.2. `ArithmeticException`: phép tính số nguyên không chứa được kết quả

Ví dụ:

```java
Instant.MAX.toEpochMilli(); // ArithmeticException.
Duration.between(Instant.EPOCH, Instant.MAX).toNanos();
// ArithmeticException.
```

Kết quả biểu diễn bằng **`long` milliseconds/nanoseconds** quá lớn. Cần phân biệt lỗi này với `DateTimeException` khi chính mốc `Instant` hoặc `LocalDate` vượt phạm vi.

### 9.3. `NullPointerException`: đối số không có mặt

Đưa `null` vào `Instant.parse`, `ZoneId.of` hoặc các API có ràng buộc non-null có thể gây `NullPointerException`. Không dùng `null` để nói “UTC” hoặc “không có offset”: chọn `ZoneOffset.UTC` hoặc một kiểu dữ liệu tùy chọn riêng nếu thực sự thiếu thông tin.

### 9.4. Không “sửa” lỗi vượt biên bằng cách wrap âm/dương

Nếu `Instant.MAX.plusNanos(1)` lỗi, không được lấy modulo đơn vị thời gian để tự quay về quá khứ; `Instant` mô tả timeline tuyệt đối **không** quay vòng. `LocalTime.plusHours(...)` có ngữ nghĩa quay vòng 24 giờ nhưng đó là **kiểu khác**, không áp dụng cho `Instant` hay ngày lịch.

Nếu nghiệp vụ muốn giới hạn kết quả vào một khoảng, ví dụ chỉ chấp nhận ngày 1900–2100, hãy xây **chính sách clamp/reject có tài liệu**, không âm thầm dùng `LocalDate.MAX` làm ngày hợp lệ cuối cùng của ứng dụng.

## 10. Đọc và tính khoảng thời gian mà không bị tràn

### 10.1. Tránh tự nhân epoch seconds thành milliseconds

Một công thức như:

```java
long millis = instant.getEpochSecond() * 1_000L;
```

là nguy hiểm nếu `instant` có giá trị lớn. Phép nhân `long` có thể overflow âm thầm trước khi bạn nhận ra. Hơn nữa, nó **bỏ phần nano giây**, nên không tương đương `Instant.toEpochMilli()`.

Ưu tiên:

```java
long millis = instant.toEpochMilli();
```

Nếu vượt miền `long`, phương thức ném `ArithmeticException` để caller xử lý. Nếu cần tự kết hợp nhiều phần số, dùng `Math.multiplyExact`, `Math.addExact` và quy tắc làm tròn/dấu được kiểm thử.

### 10.2. Duration có thể hợp lệ khi một dạng chuyển đổi cụ thể không

`Duration.between(start, end)` trả một `Duration` chứa seconds và nanos. Dữ liệu có thể quá lớn đối với `toMillis()`/`toNanos()` nhưng vẫn hợp lệ dưới dạng Duration.

Ví dụ trong phép tính lịch:

- `duration.getSeconds()` lấy phần giây dạng `long`.
- `duration.getNano()` lấy phần nano giây trong `0..999_999_999`.
- Chỉ đổi sang một số milliseconds/nanoseconds duy nhất khi biết kết quả nằm trong miền kiểu.

Với thời lượng rất lớn hoặc dữ liệu có độ chính xác cao, có thể giữ `Duration` hoặc dùng `BigInteger` để tính tổng đơn vị nhỏ nếu thực sự cần và thiết kế API hỗ trợ.

### 10.3. Thời gian lịch và thời gian đã trôi không hoàn toàn giống nhau

`Period` diễn tả năm/tháng/ngày trên **lịch**, còn `Duration` diễn tả lượng thời gian dựa trên seconds/nanos. Cộng một ngày lịch bằng `ZonedDateTime.plusDays(1)` tại ngày chuyển DST có thể khác cộng `Duration.ofHours(24)` khi quan tâm instant thực.

`Instant` không hỗ trợ đơn vị tháng/năm theo kiểu calendar một cách trực tiếp: tháng có độ dài thay đổi, năm có thể nhuận. Muốn cộng một tháng lịch, hãy chuyển sang loại date-time có ngày và zone phù hợp rồi áp phép cộng lịch.

## 11. Giới hạn ở ranh giới chuyển đổi và lịch theo vùng

### 11.1. Từ Instant tới OffsetDateTime

`OffsetDateTime.ofInstant(instant, offset)` chuyển từ timeline sang ngày giờ địa phương tại offset:

```java
Instant event = Instant.parse("2026-03-01T00:30:00Z");
OffsetDateTime local = OffsetDateTime.ofInstant(
        event, ZoneOffset.ofHours(7));
// 2026-03-01T07:30+07:00
```

Ở ngày bình thường, dễ dàng round-trip:

```java
boolean unchanged = local.toInstant().equals(event); // true
```

Nhưng ở biên `Instant.MAX`, như đã thấy, việc tạo local date-time tại UTC có thể vượt phạm vi. Không giả định `OffsetDateTime.ofInstant` là một phép chuyển đổi toàn phần cho mọi `Instant`.

### 11.2. Từ LocalDateTime tới Instant

`LocalDateTime` **không** có ZoneId. Để chuyển thành Instant, cần ít nhất một `ZoneOffset`:

```java
LocalDateTime input = LocalDateTime.of(2026, 3, 1, 7, 30);
Instant event = input.toInstant(ZoneOffset.ofHours(7));
// 2026-03-01T00:30:00Z
```

Nếu nguồn là giờ ở một thành phố có DST, offset có thể phụ thuộc ngày. Lúc đó dùng `ZoneId`/`ZonedDateTime` để xác định offset hợp lệ tại ngày, xử lý gap/overlap theo chính sách nghiệp vụ. **Không lấy offset “hiện tại” rồi áp cho một ngày lịch sử/tương lai** nếu vùng có thể đổi quy tắc.

### 11.3. Độ lệch theo vùng có thể có giây

`ZoneOffset` hỗ trợ độ lệch với phần giây trong phạm vi ±18 giờ. Điều này hữu ích cho dữ liệu lịch sử, nơi offset không nhất thiết tròn phút. `ZoneOffset.getTotalSeconds()` là API chính xác để tính độ lệch thay vì chỉ lấy số giờ rồi nhân 3600.

Do vậy, khi chuyển zone gần biên phút hoặc ngày, tránh giả định mọi offset đều là số giờ tròn.

### 11.4. Vấn đề DST và giới hạn của quy tắc zone

Các quy tắc múi giờ phụ thuộc dữ liệu tzdb/JDK và có thể được cập nhật do thay đổi chính sách quốc gia. Một `LocalDateTime` hợp lệ về calendar vẫn có thể rơi vào **gap** (giờ không tồn tại) hoặc **overlap** (giờ lặp lại) ở một khu vực.

`ZonedDateTime.ofLocal` và `ZonedDateTime.ofStrict` có những chính sách xử lý khác nhau. Nếu lịch thanh toán/lịch vận hành cần chính xác, xác định rõ có dịch giờ/cho lỗi/chọn offset nào. Đừng chỉ kiểm tra `LocalDateTime` thuộc miền ±999.999.999 rồi coi đó là đủ cho mọi lịch.

### 11.5. Giới hạn kỹ thuật của vùng rất xa trong quá khứ/tương lai

`ZoneId.of("Europe/Paris")` xác định vùng, nhưng không đồng nghĩa dữ liệu lịch sử có độ chính xác vô hạn tới hàng tỷ năm. Lịch dân sự thực tế, dữ liệu tzdb và chính sách chính phủ đều có phạm vi áp dụng thực tế. Một giá trị `Instant` hợp lệ ở năm cực trị nên được xem là giới hạn biểu diễn tính toán của API, không phải một mốc lịch sử thực được xác minh.

## 12. Cơ sở dữ liệu, API và hệ thống ngoài Java có giới hạn riêng

### 12.1. Kiểu dữ liệu database có thể hẹp hơn

Không phải mọi cột `DATE`, `TIMESTAMP` hay `TIMESTAMP WITH TIME ZONE` đều tương đương trực tiếp với miền `java.time`. Mỗi DBMS/dialect/driver có quy tắc riêng về:

- Năm tối thiểu/tối đa.
- Có chấp nhận năm 0 hoặc năm BCE không.
- Có lưu offset hay zone ID không.
- Độ chính xác giây, milliseconds, microseconds hoặc nano giây.
- Cách chuyển kiểu timestamp, múi giờ phiên kết nối và DST.
- Khi vượt phạm vi: từ chối, làm tròn hoặc ép về giá trị khác theo chính sách hệ thống.

**Không đưa `Instant.MAX` vào database rồi mong round-trip luôn đúng.** Hãy kiểm tra schema của hệ thống đang dùng, cấu hình JDBC/ORM và kiểu dữ liệu thực.

### 12.2. JSON, string và chuỗi ISO

Với sự kiện cần timestamp tuyệt đối, một chuỗi như:

```text
2026-03-01T00:30:00Z
```

cho biết UTC. Chuỗi:

```text
2026-03-01T07:30:00+07:00
```

cũng xác định cùng instant, nhưng giữ offset ban đầu. Chuỗi:

```text
2026-03-01T07:30:00
```

không cho biết múi giờ hay offset, nên không đủ xác định một instant.

Dù `DateTimeFormatter.ISO_INSTANT` có thể biểu diễn năm mở rộng, một API công khai có thể yêu cầu năm bốn chữ số hoặc một profile timestamp hẹp hơn. Kiểm tra chuẩn giao tiếp cụ thể trước khi gửi năm cực trị hoặc phần nano.

### 12.3. Độ chính xác dữ liệu đầu/cuối pipeline

Giả sử Java chứa `2026-03-01T00:30:00.123456789Z` nhưng DB chỉ lưu microseconds. Dữ liệu đọc lại sẽ có thể khác ở ba chữ số nano cuối. Đó là **sự mất độ chính xác khi lưu**, không phải lỗi `Instant.equals`.

Nên quy định chính xác “cho phép làm tròn/cắt đến đơn vị nào” ngay ở ranh giới dữ liệu. Không che giấu bằng cách chỉ so chuỗi hiển thị đến giây nếu nghiệp vụ cần phân biệt sự kiện theo nano.

### 12.4. Giới hạn nghiệp vụ thường hẹp hơn rất nhiều

Ví dụ một hệ thống đặt chỗ có thể cho phép lịch hẹn từ hôm nay tới 18 tháng tới. Một chương trình quản lý nhân sự có thể chỉ nhận ngày tuyển dụng từ năm 1900 đến 2100. Các chính sách này không liên quan trực tiếp đến khả năng biểu diễn năm ±999.999.999 của `LocalDate`.

Hãy validate theo **ba lớp**:

1. **Java type**: ngày/tháng/offset hợp lệ theo `java.time`.
2. **Giao tiếp/lưu trữ**: định dạng, phạm vi, precision mà API/DB hỗ trợ.
3. **Business rule**: khoảng thời gian được phép theo nghiệp vụ.

Thất bại ở bất kỳ lớp nào cần được báo lỗi có cấu trúc và dễ hiểu.

## 13. Chương trình Java 17+ đầy đủ kiểm thử các giá trị biên

Chương trình dùng hằng số public và exception công khai, **không** đọc các field nội bộ của JDK, không phụ thuộc giờ thực. Tạo tệp **`DateRangeLimitsDemo.java`**:

```java
import java.time.*;
import java.time.format.*;
import java.time.temporal.*;
import java.util.*;

public class DateRangeLimitsDemo {
    static void require(boolean ok, String label) {
        if (!ok) {
            throw new AssertionError(label);
        }
    }

    // Chính sách minh họa của ứng dụng, KHÔNG phải giới hạn Java.
    static boolean validBusinessDate(LocalDate date) {
        Objects.requireNonNull(date);
        return date.getYear() >= 1900 && date.getYear() <= 2100;
    }

    public static void main(String[] args) {
        System.out.println("instantMin=" + Instant.MIN);
        System.out.println("instantMax=" + Instant.MAX);
        System.out.println("localDateMin=" + LocalDate.MIN);
        System.out.println("localDateMax=" + LocalDate.MAX);
        System.out.println("localDateTimeMin=" + LocalDateTime.MIN);
        System.out.println("localDateTimeMax=" + LocalDateTime.MAX);
        System.out.println("offsetMin=" + ZoneOffset.MIN);
        System.out.println("offsetMax=" + ZoneOffset.MAX);
        System.out.println("offsetDateTimeMin=" + OffsetDateTime.MIN);
        System.out.println("offsetDateTimeMax=" + OffsetDateTime.MAX);

        // ISO proleptic Gregorian có năm 0 và năm 0 là năm nhuận.
        boolean yearZero = LocalDate.of(0, 2, 29).isLeapYear();
        require(yearZero, "proleptic leap 0");
        System.out.println("yearZeroLeap=" + yearZero);

        boolean invalidDate = false;
        try {
            LocalDate.of(2026, 2, 29);
        } catch (DateTimeException ex) {
            invalidDate = true;
        }
        require(invalidDate, "invalid calendar date");
        System.out.println("invalidLeapDateRejected=" + invalidDate);

        boolean beyondLocal = false;
        try {
            LocalDate.MAX.plusDays(1);
        } catch (DateTimeException ex) {
            beyondLocal = true;
        }
        require(beyondLocal, "local boundary");
        System.out.println("localMaxPlusDayRejected=" + beyondLocal);

        boolean beyondInstant = false;
        try {
            Instant.MAX.plusNanos(1);
        } catch (DateTimeException ex) {
            beyondInstant = true;
        }
        require(beyondInstant, "instant boundary");
        System.out.println("instantMaxPlusNanoRejected=" + beyondInstant);

        boolean badOffset = false;
        try {
            ZoneOffset.ofHoursMinutes(18, 1);
        } catch (DateTimeException ex) {
            badOffset = true;
        }
        require(badOffset, "max offset");
        System.out.println("offsetPlus1801Rejected=" + badOffset);

        Instant epochMinusMilli = Instant.ofEpochMilli(-1);
        require(epochMinusMilli.getEpochSecond() == -1
                && epochMinusMilli.getNano() == 999_000_000,
                "negative milli");
        System.out.println("negativeMilli=" + epochMinusMilli);
        System.out.println("negativeMilliParts=" +
                epochMinusMilli.getEpochSecond() + "/" +
                epochMinusMilli.getNano());

        System.out.println("maxInstantEpochSecond=" +
                Instant.MAX.getEpochSecond());

        boolean millisecondsOverflow = false;
        try {
            Instant.MAX.toEpochMilli();
        } catch (ArithmeticException ex) {
            millisecondsOverflow = true;
        }
        require(millisecondsOverflow, "millis overflow");
        System.out.println("maxToEpochMilliOverflow=" +
                millisecondsOverflow);

        boolean nanosOverflow = false;
        try {
            Duration.between(Instant.EPOCH, Instant.MAX).toNanos();
        } catch (ArithmeticException ex) {
            nanosOverflow = true;
        }
        require(nanosOverflow, "duration nanos overflow");
        System.out.println("durationToNanosOverflow=" + nanosOverflow);

        boolean localConversionRejected = false;
        try {
            LocalDateTime.ofInstant(Instant.MAX, ZoneOffset.UTC);
        } catch (DateTimeException ex) {
            localConversionRejected = true;
        }
        require(localConversionRejected, "conversion exceeds localdate");
        System.out.println("maxInstantToLocalRejected=" +
                localConversionRejected);

        OffsetDateTime vietnam =
                OffsetDateTime.parse("2026-03-01T07:30:00+07:00");
        OffsetDateTime utc =
                OffsetDateTime.parse("2026-03-01T00:30:00Z");
        require(vietnam.toInstant().equals(utc.toInstant()),
                "same instant");
        require(!vietnam.equals(utc), "different representation");

        System.out.println("sameInstant=" + vietnam.isEqual(utc));
        System.out.println("sameOffsetDateTimeObjectValue=" +
                vietnam.equals(utc));
        System.out.println("changeOffsetKeepInstant=" +
                vietnam.withOffsetSameInstant(ZoneOffset.UTC));
        System.out.println("changeOffsetKeepLocal=" +
                vietnam.withOffsetSameLocal(ZoneOffset.UTC));

        System.out.println("businessYear2500Allowed=" +
                validBusinessDate(LocalDate.of(2500, 1, 1)));
        System.out.println("businessYear2026Allowed=" +
                validBusinessDate(LocalDate.of(2026, 1, 1)));

        boolean extremeMillisFromLong =
                Instant.ofEpochMilli(Long.MAX_VALUE)
                        .isBefore(Instant.MAX);
        System.out.println("longMaxMillisIsValidInstant=" +
                extremeMillisFromLong);

        System.out.println("ALL CHECKS PASSED");
    }
}
```

Biên dịch và chạy:

```bash
javac DateRangeLimitsDemo.java
java DateRangeLimitsDemo
```

**Stdout chính xác (đã kiểm thử với JDK hỗ trợ Java 17+):**

```text
instantMin=-1000000000-01-01T00:00:00Z
instantMax=+1000000000-12-31T23:59:59.999999999Z
localDateMin=-999999999-01-01
localDateMax=+999999999-12-31
localDateTimeMin=-999999999-01-01T00:00
localDateTimeMax=+999999999-12-31T23:59:59.999999999
offsetMin=-18:00
offsetMax=+18:00
offsetDateTimeMin=-999999999-01-01T00:00+18:00
offsetDateTimeMax=+999999999-12-31T23:59:59.999999999-18:00
yearZeroLeap=true
invalidLeapDateRejected=true
localMaxPlusDayRejected=true
instantMaxPlusNanoRejected=true
offsetPlus1801Rejected=true
negativeMilli=1969-12-31T23:59:59.999Z
negativeMilliParts=-1/999000000
maxInstantEpochSecond=31556889864403199
maxToEpochMilliOverflow=true
durationToNanosOverflow=true
maxInstantToLocalRejected=true
sameInstant=true
sameOffsetDateTimeObjectValue=false
changeOffsetKeepInstant=2026-03-01T00:30Z
changeOffsetKeepLocal=2026-03-01T07:30Z
businessYear2500Allowed=false
businessYear2026Allowed=true
longMaxMillisIsValidInstant=true
ALL CHECKS PASSED
```

### 13.1. Phân tích những kết quả quan trọng

- `instantMin`/`instantMax` xác định hai mốc ±1.000.000.000 năm (theo ISO UTC), trong khi `localDateMin`/`localDateMax` chỉ tới ±999.999.999.
- `offsetMin=-18:00` và `offsetMax=+18:00` là các hằng số `ZoneOffset`, còn `OffsetDateTime.MIN` ghép **local minimum với offset maximum**.
- `yearZeroLeap=true` vì ISO dùng năm 0 theo proleptic Gregorian; `2026-02-29` bị từ chối do 2026 không nhuận.
- `localMaxPlusDayRejected=true` và `instantMaxPlusNanoRejected=true` cho thấy cộng vượt biên **không tự quay vòng**, mà ném lỗi.
- `offsetPlus1801Rejected=true` xác nhận +18:01 nằm ngoài miền offset.
- `negativeMilliParts=-1/999000000` cho thấy Instant giữ epochSecond âm và nanoOfSecond **không âm**.
- `maxInstantEpochSecond` là một số `long` lớn nhưng không tới `Long.MAX_VALUE`; phạm vi `Instant` hẹp hơn miền số long seconds.
- `maxToEpochMilliOverflow=true` chứng minh Instant hợp lệ vẫn có thể vượt khả năng biểu diễn dưới dạng long milliseconds.
- `durationToNanosOverflow=true` chứng minh chuyển một Duration dài sang một `long` nanos cũng có thể tràn.
- `maxInstantToLocalRejected=true` cho thấy phép đổi từ Instant sang LocalDateTime tại UTC có miền giá trị hẹp hơn Instant.
- `sameInstant=true`, `sameOffsetDateTimeObjectValue=false` phân biệt **cùng thời điểm** với **cùng biểu diễn local+offset**.
- `changeOffsetKeepInstant` trả 00:30Z; `changeOffsetKeepLocal` trả 07:30Z vì mỗi phương thức giữ bất biến khác nhau.
- `businessYear2500Allowed=false` dù `LocalDate.of(2500,1,1)` hợp lệ. Đó là chính sách **do ứng dụng tự đặt**, không phải giới hạn Java.
- `longMaxMillisIsValidInstant=true` cho thấy toàn bộ miền long milliseconds nằm trong miền Instant (dù không thể chuyển mọi Instant sang long milliseconds).

### 13.2. Vì sao ví dụ không gọi `Instant.now()`?

Các giới hạn là hằng số public; bài kiểm thử cần có kết quả lặp lại, không phụ thuộc ngày giờ thật hoặc cấu hình JVM. Test dùng mốc cố định để quan sát khả năng biểu diễn, phép cộng tại biên và cách chuyển offset. Khi cần kiểm thử giờ hiện tại trong ứng dụng, inject `Clock.fixed(...)` thay vì gọi trực tiếp `now()` và so với một chuỗi thời gian cố định.

## 14. Lập ma trận kiểm thử các giới hạn

| Trường hợp | Expected | Lỗi giúp phát hiện |
| --- | --- | --- |
| `Instant.MIN` và `Instant.MAX` | Tạo và in hợp lệ | Giả định Instant chỉ hỗ trợ 4 chữ số năm |
| `LocalDate.MIN/MAX` | Giới hạn ±999.999.999 | Nhầm với Instant ±1.000.000.000 |
| `LocalDate.MAX.plusDays(1)` | `DateTimeException` | Tưởng ngày lịch tự wrap |
| `Instant.MAX.plusNanos(1)` | `DateTimeException` | Tưởng Instant tự wrap |
| `ZoneOffset.MIN/MAX` | -18h/+18h | Giới hạn offset bị đoán sai |
| `ZoneOffset.ofHoursMinutes(18,1)` | `DateTimeException` | Bỏ qua biên offset |
| `OffsetDateTime.MIN/MAX` | Ghép offset ngược dấu với local min/max | Sai thứ tự timeline |
| `LocalDate.of(0,2,29)` | Hợp lệ | Không hiểu ISO proleptic |
| `LocalDate.of(2026,2,29)` | `DateTimeException` | Bỏ qua quy tắc năm nhuận |
| `Instant.ofEpochMilli(-1)` | second -1, nano 999.000.000 | Xử lý dấu timestamp âm sai |
| `Instant.MAX.toEpochMilli()` | `ArithmeticException` | Tưởng mọi Instant đổi sang long được |
| `Duration.between(EPOCH,MAX).toNanos()` | `ArithmeticException` | Tràn khi đổi sang nano scalar |
| `LocalDateTime.ofInstant(Instant.MAX, UTC)` | `DateTimeException` | Không kiểm tra miền đích |
| Hai offset cùng Instant | `toInstant`/`isEqual` bằng nhau, `equals` có thể khác | Đồng nhất UTC instant với chuỗi hiển thị |
| `withOffsetSameInstant` | Không đổi Instant | Đổi offset mà dịch timeline |
| `withOffsetSameLocal` | Không đổi local date-time | Nhầm đổi offset giữ local với giữ instant |
| Year hợp lệ nhưng ngoài policy ứng dụng | Reject theo business rule | Dùng giới hạn Java thay quy tắc nghiệp vụ |
| Chuỗi năm dài/âm và formatter custom | Phải parse/format theo contract | Hardcode 4-digit year |
| DB/JDBC round-trip nano | Độ chính xác theo DB thật | Cho rằng DB giữ mọi nano |

**Nguyên tắc kiểm thử:** Tạo dữ liệu oracle độc lập; không chỉ so “kết quả format trước và sau giống nhau” nếu formatter đã cắt precision. Với timestamp, kiểm tra cả seconds và nanos khi yêu cầu độ chính xác cao; với offset, kiểm tra `Instant` trước và sau chuyển đổi.

## 15. Những lỗi thiết kế phổ biến

### 15.1. Trả về `long` epoch milliseconds nhưng đầu vào nhận mọi Instant

Nếu API đầu vào chấp nhận `Instant.MAX`, còn đầu ra luôn gọi `toEpochMilli()` thì API không có miền biểu diễn thống nhất. Hoặc giới hạn đầu vào ở những Instant đổi được sang millis, hoặc đổi kiểu đầu ra sang cặp seconds+nanos/chuỗi ISO phù hợp.

### 15.2. Dùng LocalDateTime làm định danh cho sự kiện toàn cầu

Hai sự kiện diễn ra ở những offset khác nhau có thể có LocalDateTime giống nhau nhưng Instant khác nhau. Ngược lại, cùng Instant có thể có ngày giờ local khác nhau. Với audit event và ordering toàn cục, lưu `Instant` hoặc thông tin timestamp đủ xác định timeline.

### 15.3. Tự viết phép đổi giữa offset và giờ địa phương bằng cộng trừ long không kiểm tra

Cộng `offset.getTotalSeconds()` vào epoch second bằng `+` có thể overflow nếu dữ liệu tùy ý rất lớn. Dùng API `atOffset`/`ofInstant` và xử lý exception theo miền của kiểu đích, hoặc dùng `Math.addExact` nếu phải tính số học nguyên thủy.

### 15.4. Dùng `Year.of(0)` như “năm không có dữ liệu”

Trong ISO proleptic, năm 0 **là một năm hợp lệ**. Đừng dùng 0 làm sentinel thiếu. Nếu nghiệp vụ chỉ nhận năm dương, xác thực ở lớp business rule; nếu dữ liệu thiếu, dùng trạng thái riêng hoặc `Optional` theo API.

### 15.5. Cho rằng offset ±18h là offset “ngoài trái đất” nên tự từ chối

`ZoneOffset` API cho phép ±18h. Nếu yêu cầu chỉ nhận offset đang sử dụng cho một khu vực, hãy xác thực bằng `ZoneId`/`ZoneRules` theo mốc thời gian hoặc một tập luật nghiệp vụ, không tự lấy “-12..+14” làm giới hạn ngôn ngữ Java.

### 15.6. Ép mọi timestamp vào kiểu date của database mà không kiểm tra

Một DB hoặc hệ thống khách có thể không hỗ trợ năm âm, năm 0 hay phần nano. Cần xác nhận schema và thực hiện round-trip test ở môi trường thật; không đợi lỗi production với dữ liệu cận biên.

### 15.7. Coi “ISO” luôn là đúng lịch sử mọi quốc gia

Lịch proleptic Gregorian thống nhất về số học, nhưng các xã hội đã thay lịch vào các thời điểm khác nhau. Nếu ứng dụng quản lý tư liệu cổ/hồ sơ lịch sử, cần mô hình hóa lịch/tài liệu nguồn thay vì chỉ parse `LocalDate` rồi khẳng định đó là ngày dân sự chính xác.

### 15.8. Cố khôi phục dữ liệu đã mất precision

`Instant.ofEpochMilli(original.toEpochMilli())` không thể khôi phục phần nano dưới millisecond. Nếu cần round-trip nano, chọn định dạng lưu trữ phù hợp ngay từ đầu; không thể suy ra những chữ số đã cắt.

## 16. Quy trình thiết kế API ngày giờ an toàn

**Bước 1 — Xác định loại dữ liệu.** Đó là ngày lịch, giờ lặp lại, ngày giờ địa phương, một Instant hay timestamp kèm offset? Không chọn kiểu chỉ vì tên cột là “time”.

**Bước 2 — Xác định precision yêu cầu.** Năm/tháng/ngày? Giây? Milliseconds? Nanoseconds? Nhớ rằng `java.time` hỗ trợ nano nhưng DB/clock có thể ít hơn.

**Bước 3 — Xác định miền thời gian.** Dữ liệu có lịch sử trước năm 1? Có năm 0/BCE? Cần năm >9999? Quy định business/DB có hẹp hơn Java không?

**Bước 4 — Chọn cách lưu và chuyển đổi.** `Instant` và `OffsetDateTime` khác nhau ở việc giữ offset, `LocalDateTime` không có offset, `ZonedDateTime` giữ ZoneId. Nếu cần timeline chính xác, bảo toàn instant.

**Bước 5 — Validate ở mỗi ranh giới.** Parse ISO/formatter; kiểm tra `DateTimeException`/`DateTimeParseException`; khi đổi scalar milliseconds/nanoseconds, xét `ArithmeticException`; khi đổi zone tại biên, xét miền ngày địa phương.

**Bước 6 — Quy định lỗi.** Reject với mã lỗi rõ ràng; nếu hệ thống thực sự cần clamp vào khoảng có policy, ghi minh bạch quy tắc và test, đừng lặng lẽ lấy MIN/MAX.

**Bước 7 — Test cả cực trị và dữ liệu thực tế.** Không chỉ test `2026-01-01`; thêm `Instant.MIN/MAX`, `ZoneOffset.MIN/MAX`, negative epoch, năm 0, leap day, DST gap/overlap khi có zone vùng.

**Bước 8 — Kiểm tra round-trip qua công nghệ thật.** JSON serializer, database, message queue, API client và Java có thể không cùng precision/range; đo trực tiếp bằng dữ liệu đại diện.

## 17. Bài tập có đáp án

**Bài 1.** `Instant.MAX` hợp lệ nhưng `Instant.MAX.toEpochMilli()` có hợp lệ không?

**Đáp án:** Không. Instant có miền thời điểm rộng hơn miền `long` milliseconds; `toEpochMilli()` ném `ArithmeticException`.

**Bài 2.** `LocalDate.MAX.plusDays(1)` trả năm `1_000_000_000` hay wrap về năm âm?

**Đáp án:** Không cả hai. Nó ném `DateTimeException` do ngoài miền ngày được hỗ trợ.

**Bài 3.** Phạm vi hợp lệ của `ZoneOffset` là bao nhiêu?

**Đáp án:** Từ `-18:00` đến `+18:00`, bao gồm hai đầu; `+18:01` bị từ chối.

**Bài 4.** Vì sao `OffsetDateTime.MIN` có offset `+18:00` chứ không phải `-18:00`?

**Đáp án:** Với cùng local date-time, offset dương hơn ứng với instant UTC sớm hơn. Giới hạn MIN của OffsetDateTime chọn local min kết hợp offset max để có thời điểm sớm nhất.

**Bài 5.** `LocalDate.of(0,2,29)` có hợp lệ không? Năm 0 là gì?

**Đáp án:** Hợp lệ theo proleptic Gregorian, năm 0 là năm nhuận. Trong cách chuyển đổi 1 BCE sang ISO proleptic, năm 1 BCE tương ứng năm 0.

**Bài 6.** `Instant.ofEpochMilli(-1)` có `getEpochSecond()` và `getNano()` bằng bao nhiêu?

**Đáp án:** Epoch second là `-1`, nanoOfSecond là `999_000_000`; biểu diễn timestamp `1969-12-31T23:59:59.999Z`.

**Bài 7.** Hai `OffsetDateTime` `2026-03-01T07:30+07:00` và `2026-03-01T00:30Z` có bằng nhau theo `equals` không?

**Đáp án:** `equals` trả false vì local fields/offset khác nhau; `isEqual` hoặc `toInstant().equals(...)` trả true vì cùng thời điểm tuyệt đối.

**Bài 8.** Một hệ thống chỉ chấp nhận ngày từ năm 1900 đến 2100. `LocalDate.of(2500,1,1)` có “sai Java” không?

**Đáp án:** Không, ngày hợp lệ theo Java. Nó chỉ bị từ chối bởi **business rule** của hệ thống.

**Bài 9.** Có nên lấy `Duration.between(Instant.EPOCH, Instant.MAX).toNanos()` để lưu vào `long` không?

**Đáp án:** Không, chuyển sang nanos vượt miền `long` và ném `ArithmeticException`. Giữ `Duration` hoặc cấu trúc chính xác phù hợp.

**Bài 10.** `ZoneId.of("Europe/Paris")` và `ZoneOffset.of("+01:00")` có ý nghĩa giống nhau mãi không?

**Đáp án:** Không. Một bên mang quy tắc vùng có thể biến đổi theo thời gian, một bên luôn là offset cố định.

**Bài 11.** `Instant.MAX` không đổi được thành LocalDateTime ở UTC. Có được suy luận nó là Instant không hợp lệ không?

**Đáp án:** Không. Nó hợp lệ trong miền Instant, nhưng vượt miền ngày của LocalDateTime ở offset đã chọn. Đây là giới hạn **miền đích**, không phải miền nguồn.

**Bài 12.** Khi định dạng năm BCE, có nên dùng `yyyy` thay cho `uuuu` một cách tùy tiện không?

**Đáp án:** Không. `yyyy` biểu diễn year-of-era, còn `uuuu` biểu diễn proleptic year có năm 0; cần chọn đúng theo hợp đồng dữ liệu.

## 18. Checklist production

- [ ] Chọn đúng kiểu `Instant`/`LocalDate`/`LocalDateTime`/`OffsetDateTime`/`ZonedDateTime` theo ý nghĩa dữ liệu.
- [ ] Đã biết `Instant.MIN/MAX` khác `LocalDate.MIN/MAX` và `LocalDateTime.MIN/MAX`.
- [ ] Giới hạn `ZoneOffset` được hiểu đúng: ±18 giờ, bao gồm biên.
- [ ] Không giả định mọi Instant đổi được sang LocalDateTime tại mọi offset hoặc ZoneId.
- [ ] Không giả định `Instant.toEpochMilli()` hay `Duration.toNanos()` luôn thành công.
- [ ] Không tự nhân `epochSecond * 1000` thiếu kiểm tra overflow và precision.
- [ ] Đã xử lý epoch âm và nano phần giây không âm.
- [ ] Đã phân biệt `withOffsetSameInstant` và `withOffsetSameLocal`.
- [ ] Đã biết năm 0/năm âm và lịch proleptic Gregorian khác cách ghi lịch sử ở một số hệ.
- [ ] Đã xử lý ngày không hợp lệ (29/2 năm thường), vượt year range và sai format.
- [ ] Đã phân biệt fixed offset với zone khu vực và các vấn đề DST/tzdb.
- [ ] Đã kiểm tra giới hạn và precision của JSON/database/JDBC/ORM thay vì chỉ dựa vào Java.
- [ ] Đã có quy tắc miền ngày hợp lệ của business, có thông báo reject rõ.
- [ ] Đã test MIN/MAX, overflow, negative epoch, round-trip, offset conversion và dữ liệu thực.
- [ ] Không dùng `==`/identity locking cho các lớp ngày giờ value-based.

## Tài liệu tham khảo chính thức hiện hành

1. [Oracle JDK 25 — Instant: MIN/MAX, epoch seconds/nanos, toEpochMilli, phép cộng vượt biên](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/time/Instant.html)
2. [Oracle JDK 25 — LocalDate: lịch ISO proleptic, năm và MIN/MAX](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/time/LocalDate.html)
3. [Oracle JDK 25 — LocalDateTime: giới hạn năm và ofInstant](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/time/LocalDateTime.html)
4. [Oracle JDK 25 — ZoneOffset: miền -18:00 tới +18:00](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/time/ZoneOffset.html)
5. [Oracle JDK 25 — OffsetDateTime: MIN/MAX, withOffsetSameInstant và withOffsetSameLocal](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/time/OffsetDateTime.html)
6. [Oracle JDK 25 — Duration: kiểu giây+nano và giới hạn toNanos](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/time/Duration.html)
7. [Oracle JDK 25 — DateTimeFormatter: ISO_INSTANT, ISO_LOCAL_DATE và năm mở rộng](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/time/format/DateTimeFormatter.html)
8. [Oracle JDK 25 — ZonedDateTime: gap/overlap và quy tắc ZoneId](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/time/ZonedDateTime.html)

**Ghi nhớ:** `java.time` có giới hạn rộng nhưng **khác nhau giữa các lớp và giữa các biểu diễn**. Hãy kiểm tra cả miền nguồn, miền đích, phép đổi đơn vị và hợp đồng hệ thống ngoài Java; một Instant hợp lệ không bảo đảm mọi cách chuyển đổi hay lưu trữ đều hợp lệ.
