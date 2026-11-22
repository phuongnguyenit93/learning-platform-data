# Kết hợp `LocalTime` với `LocalDate` hoặc `ZoneOffset`

`LocalTime` biểu diễn **giờ trong một ngày**, chẳng hạn `09:30` hoặc `23:45:20.123`. Nó không chứa ngày, múi giờ hoặc offset so với UTC. Vì vậy, `LocalTime` phù hợp để lưu giờ mở cửa, giờ học, giờ hẹn theo đồng hồ, nhưng **chưa đủ để xác định một thời điểm duy nhất trên trục thời gian toàn cầu**.

Khi kết hợp `LocalTime` với `LocalDate`, ta nhận được **ngày giờ địa phương** (`LocalDateTime`). Khi kết hợp với `ZoneOffset`, ta nhận được **giờ kèm offset** (`OffsetTime`). Muốn có một `Instant` cụ thể, ta cần tối thiểu **ngày + giờ + offset**, hoặc **ngày + giờ + `ZoneId` cùng quy tắc giải quyết khoảng thời gian chuyển múi giờ**.

## 1. Phân biệt các kiểu trước khi ghép

| Kiểu | Giữ thông tin gì? | Ví dụ | Có xác định một `Instant`? |
| --- | --- | --- | --- |
| `LocalTime` | Giờ, phút, giây, nano giây | `09:30` | Chưa |
| `LocalDate` | Ngày, tháng, năm ISO | `2026-10-24` | Chưa |
| `LocalDateTime` | Ngày và giờ địa phương | `2026-10-24T09:30` | Chưa |
| `ZoneOffset` | Độ lệch cố định so với UTC | `+07:00` | Một offset riêng lẻ chưa đủ |
| `OffsetTime` | Giờ địa phương và offset | `09:30+07:00` | Chưa: còn thiếu ngày |
| `OffsetDateTime` | Ngày, giờ địa phương và offset | `2026-10-24T09:30+07:00` | Có |
| `ZoneId` | Định danh vùng và bộ quy tắc offset | `Asia/Ho_Chi_Minh` | Vùng riêng lẻ chưa đủ |
| `ZonedDateTime` | Ngày, giờ, vùng và offset đã phân giải | `2026-10-24T09:30+07:00[Asia/Ho_Chi_Minh]` | Có |
| `Instant` | Một điểm trên trục thời gian Java/UTC | `2026-10-24T02:30:00Z` | Chính là thời điểm |

**Phân biệt tên giống nhau:** `ZoneOffset` là một **độ lệch cố định**, ví dụ UTC+07:00. `ZoneId` như `Europe/Berlin` biểu diễn vùng có lịch sử và quy tắc thay đổi offset (bao gồm DST khi áp dụng). Một `ZoneId` có thể cho những offset khác nhau tùy ngày, và một offset có thể được dùng bởi nhiều vùng.

### Tại sao `LocalTime` chưa cho biết timestamp?

Chỉ biết “09:30” không xác định được đó là ngày nào. Dù biết `+07:00`, “09:30+07:00” vẫn có thể xảy ra mỗi ngày. Để đổi thành mốc UTC, cần một **ngày cụ thể**:

```text
LocalTime 09:30
   + LocalDate 2026-10-24
   = LocalDateTime 2026-10-24T09:30
   + ZoneOffset +07:00
   = OffsetDateTime 2026-10-24T09:30+07:00
   = Instant 2026-10-24T02:30:00Z
```

Chúng ta có thể bắt đầu từ `LocalTime` và ghép theo nhiều thứ tự khác nhau, miễn là **giữ đủ ngày, giờ và offset/vùng** khi cần một thời điểm tuyệt đối.

## 2. Ghép `LocalTime` với `LocalDate`: `atDate()`

Phương thức **`LocalTime.atDate(LocalDate)`** trả về `LocalDateTime`. Cách tương đương là **`LocalDate.atTime(LocalTime)`**.

```java
import java.time.LocalDate;
import java.time.LocalDateTime;
import java.time.LocalTime;

LocalDate date = LocalDate.of(2026, 10, 24);
LocalTime time = LocalTime.of(9, 30);

LocalDateTime first = time.atDate(date);
LocalDateTime second = date.atTime(time);

System.out.println(first);                // 2026-10-24T09:30
System.out.println(first.equals(second)); // true
```

Hai hướng ghép đều giữ nguyên thành phần đã cung cấp. `LocalTime`, `LocalDate` và `LocalDateTime` chuẩn đều bất biến: `atDate` tạo giá trị kết hợp mà không làm thay đổi `date` hoặc `time`.

**`LocalDateTime` vẫn chưa chứa offset/vùng.** Cùng `2026-10-24T09:30` có thể là 09:30 ở Hà Nội, Tokyo, London hoặc nhiều địa điểm khác; chúng có thể chỉ tới các instant khác nhau.

### Cách tạo trực tiếp và lấy lại thành phần

```java
LocalDateTime combined = LocalDateTime.of(date, time);
LocalDate extractedDate = combined.toLocalDate();
LocalTime extractedTime = combined.toLocalTime();
```

`LocalDateTime.of(date, time)` là một cách viết trực tiếp tương đương khi đã có cả hai giá trị. `toLocalDate()` và `toLocalTime()` lấy lại các thành phần tương ứng; hữu ích khi cần gắn ngày cho giờ hẹn đã được chọn.

## 3. Ghép `LocalTime` với `ZoneOffset`: `atOffset()`

**`LocalTime.atOffset(ZoneOffset)`** trả về `OffsetTime`, tức giờ trong ngày cùng một độ lệch cố định so với UTC.

```java
import java.time.LocalTime;
import java.time.OffsetTime;
import java.time.ZoneOffset;

LocalTime time = LocalTime.of(9, 30);
ZoneOffset offset = ZoneOffset.ofHours(7);
OffsetTime offsetTime = time.atOffset(offset);

System.out.println(offsetTime); // 09:30+07:00
```

`ZoneOffset.of("+07:00")` cũng tạo giá trị `+07:00`. `ZoneOffset.UTC` là offset `Z` (UTC+00:00). Offset hợp lệ của Java nằm từ **-18:00 tới +18:00** theo quy tắc của API; nếu đầu vào không hợp lệ, Java ném `DateTimeException`.

`OffsetTime` không có thông tin ngày. Nó cho biết “09:30 theo đồng hồ có offset +07:00”, nhưng **không thể chuyển thẳng thành `Instant`**. Cần ghép thêm ngày; `OffsetTime` không có phương thức `toInstant()` độc lập.

### Lấy ngày cùng với `OffsetTime`

```java
LocalDate date = LocalDate.of(2026, 10, 24);
OffsetTime offsetTime = LocalTime.of(9, 30)
        .atOffset(ZoneOffset.ofHours(7));

OffsetDateTime timestamp = date.atTime(offsetTime);
System.out.println(timestamp);           // 2026-10-24T09:30+07:00
System.out.println(timestamp.toInstant());// 2026-10-24T02:30:00Z
```

`LocalDate.atTime(OffsetTime)` là overload khác với `LocalDate.atTime(LocalTime)`: cùng tên `atTime` nhưng kiểu đầu vào quyết định kiểu kết quả (`OffsetDateTime` thay vì `LocalDateTime`).

### Đổi offset trên một `OffsetTime`

Hai phương thức có ngữ nghĩa khác nhau:

```java
OffsetTime vietnam = LocalTime.of(9, 30)
        .atOffset(ZoneOffset.ofHours(7));

OffsetTime sameReferenceTime = vietnam.withOffsetSameInstant(
        ZoneOffset.UTC); // 02:30Z
OffsetTime sameWallClock = vietnam.withOffsetSameLocal(
        ZoneOffset.UTC); // 09:30Z
```

- `withOffsetSameInstant` điều chỉnh giờ để giữ cùng vị trí tương đối trên một **ngày tham chiếu ngầm định** khi so các `OffsetTime`. Nó **không gắn ngày thực tế** cho đối tượng.
- `withOffsetSameLocal` giữ nguyên giờ hiện trên đồng hồ, chỉ đổi offset; nếu gắn cùng một ngày, instant thường thay đổi.

Thận trọng khi chuyển offset làm giờ vượt qua nửa đêm: `OffsetTime` chỉ giữ **giờ trong ngày**, không cho biết ngày đã tăng/giảm. Nếu nghiệp vụ cần bảo toàn thời điểm **và ngày lịch thực tế**, hãy thêm ngày trước, rồi chuyển qua `OffsetDateTime.withOffsetSameInstant` hoặc `ZonedDateTime.withZoneSameInstant`.

## 4. Ghép đủ ngày + giờ + offset để có `Instant`

Một mốc thời gian tuyệt đối cần ngữ cảnh đủ để quy về UTC. Có nhiều cách kết hợp tương đương:

```java
LocalDate date = LocalDate.of(2026, 10, 24);
LocalTime time = LocalTime.of(9, 30);
ZoneOffset offset = ZoneOffset.ofHours(7);

// Cách 1: LocalTime -> LocalDateTime -> OffsetDateTime
OffsetDateTime a = time.atDate(date).atOffset(offset);

// Cách 2: LocalTime -> OffsetTime -> OffsetDateTime
OffsetDateTime b = date.atTime(time.atOffset(offset));

// Cách 3: factory trực tiếp
OffsetDateTime c = OffsetDateTime.of(date, time, offset);

// Cách 4: tạo Instant trực tiếp khi đã có đủ ngày, giờ và offset
Instant instant = time.atDate(date).toInstant(offset);

System.out.println(a.equals(b));                // true
System.out.println(a.equals(c));                // true
System.out.println(instant);                    // 2026-10-24T02:30:00Z
System.out.println(a.toInstant().equals(instant)); // true
```

(Cần import `java.time.LocalDate`, `LocalTime`, `ZoneOffset`, `OffsetDateTime`, `Instant` nếu đưa đoạn này vào lớp riêng.)

Cách chọn trong thực tế:

- Đang thao tác các trường giờ/ngày địa phương → ghép ra `LocalDateTime` trước.
- API đã có `OffsetTime` từ nguồn khác → dùng `date.atTime(offsetTime)`.
- Cần dấu thời gian để lưu hoặc so sánh giữa dịch vụ → lấy `toInstant()` sau khi ngữ cảnh đã đủ.
- Cần hiển thị lại offset/vùng của người dùng → lưu thêm thông tin nghiệp vụ cần thiết; mỗi `Instant` riêng lẻ không lưu offset/vùng ban đầu.

**Một shortcut trong Java 9+:** `LocalTime.toEpochSecond(LocalDate, ZoneOffset)` ghép ngày + giờ + offset và tính giây epoch:

```java
long epochSecond = time.toEpochSecond(date, offset);
long sameEpochSecond = instant.getEpochSecond();
System.out.println(epochSecond == sameEpochSecond); // true
```

Phương thức này nhận đủ ba thành phần nên khác với việc chỉ có `OffsetTime`. Nếu cần giữ **nano giây**, hãy dùng `LocalDateTime.toInstant(offset)` hoặc `OffsetDateTime.toInstant()` thay vì chỉ lưu `long` giây epoch; số giây nguyên bỏ qua phần nano giây.

## 5. `ZoneOffset` khác `ZoneId`: nên dùng kiểu nào?

Một offset như `+07:00` là con số cố định, **không tự thay đổi theo ngày**. Ngược lại, vùng `Europe/Berlin` có quy tắc chuyển giữa các offset tại những thời điểm khác nhau. `Asia/Ho_Chi_Minh` cũng là một `ZoneId` thực: quy tắc lịch sử vùng có thể khác, dù với ngày 2026-10-24 vùng này dùng UTC+07:00.

### Dùng `ZoneId` cho lịch gắn một địa điểm

```java
LocalDate date = LocalDate.of(2026, 10, 24);
LocalTime time = LocalTime.of(9, 30);

ZoneId zone = ZoneId.of("Asia/Ho_Chi_Minh");
ZonedDateTime zoned = time.atDate(date).atZone(zone);

System.out.println(zoned);
// 2026-10-24T09:30+07:00[Asia/Ho_Chi_Minh]

System.out.println(zoned.toInstant());
// 2026-10-24T02:30:00Z
```

Với một **cuộc họp thực sự diễn ra ngày/giờ địa phương tại một vùng**, giữ `ZoneId` hữu ích vì nó cho phép diễn giải quy tắc offset của vùng tại **ngày cụ thể**. Với giao tiếp với hệ thống chỉ cung cấp offset hợp lệ, `OffsetDateTime` có thể phù hợp hơn. Hai kiểu không thay thế hoàn toàn cho nhau.

Đừng tự lấy `ZoneOffset.ofHours(1)` và áp cho mọi ngày của `Europe/Berlin`: vùng này không sử dụng một offset cố định quanh năm.

### Kết hợp với vùng có DST: giờ không tồn tại và giờ lặp

Một `LocalDateTime` bất kỳ đều có thể được tạo, nhưng khi áp dụng `ZoneId` với daylight saving time, một số giờ địa phương có thể **không tồn tại** hoặc có **hai instant hợp lệ**.

Ví dụ với quy tắc `Europe/Berlin` năm 2024:

| Loại | Ngày giờ địa phương | Kết quả của `atZone(ZoneId.of("Europe/Berlin"))` |
| --- | --- | --- |
| Bình thường | `2024-03-30T02:30` | `2024-03-30T02:30+01:00[Europe/Berlin]` |
| **Gap**, nhảy đồng hồ tiến | `2024-03-31T02:30` | Được đẩy thành `2024-03-31T03:30+02:00[Europe/Berlin]` |
| **Overlap**, đồng hồ lùi | `2024-10-27T02:30` | Mặc định chọn offset sớm hơn `+02:00`; cũng có lựa chọn `+01:00` |

```java
ZoneId berlin = ZoneId.of("Europe/Berlin");

LocalDateTime gap = LocalDateTime.of(2024, 3, 31, 2, 30);
ZonedDateTime resolvedGap = gap.atZone(berlin);
// 2024-03-31T03:30+02:00[Europe/Berlin]

LocalDateTime overlap = LocalDateTime.of(2024, 10, 27, 2, 30);
ZonedDateTime early = overlap.atZone(berlin);
// 2024-10-27T02:30+02:00[Europe/Berlin]

ZonedDateTime late = early.withLaterOffsetAtOverlap();
// 2024-10-27T02:30+01:00[Europe/Berlin]
```

Các đoạn trên **minh họa**, cần `import java.time.ZoneId;`, `LocalDateTime;`, `ZonedDateTime;` khi dùng trong lớp Java.

Đừng tưởng `atZone` chỉ “đính kèm” vùng mà không động tới giá trị: trong khoảng gap, Java **điều chỉnh local time tiến qua khoảng trống**. Nếu nghiệp vụ phải **từ chối** thay vì tự phân giải thời gian không tồn tại/không rõ ràng, kiểm tra `zone.getRules().getValidOffsets(localDateTime)`:

- Danh sách rỗng → gap, không có offset hợp lệ.
- Một offset → trường hợp thông thường.
- Hai offset → overlap, cần chọn rõ lần xuất hiện.

`ZonedDateTime.ofStrict(localDateTime, offset, zone)` yêu cầu offset đưa vào phải hợp lệ cho ngày giờ địa phương và vùng đó; nó sẽ ném `DateTimeException` với trường hợp không hợp lệ. Đây là lựa chọn hữu ích khi hệ thống yêu cầu xác định chính xác ý người đặt lịch.

### Gắn offset không đồng nghĩa xác nhận offset hợp lệ trong vùng

```java
LocalDateTime local = LocalDateTime.of(2024, 7, 1, 10, 0);
OffsetDateTime arbitrary = local.atOffset(ZoneOffset.ofHours(1));
```

Đoạn này hợp lệ vì `OffsetDateTime` cho phép mọi kết hợp ngày giờ và offset trong phạm vi API, **kể cả khi UTC+01 không phải offset phù hợp của Berlin ngày 1/7/2024**. Nếu cần “giờ Berlin lúc đó”, dùng `local.atZone(ZoneId.of("Europe/Berlin"))` hoặc xác thực offset theo `ZoneRules`.

## 6. Qua nửa đêm: giữ ngày khi thực hiện phép tính

`LocalTime` chỉ có giờ trong một ngày, nên các phép cộng của nó **quay vòng 24 giờ**:

```java
LocalTime start = LocalTime.of(23, 30);
LocalTime result = start.plusHours(2);

System.out.println(result); // 01:30
```

Kết quả `01:30` không cho biết đã sang hôm sau. Nếu công việc thực sự bắt đầu lúc 23:30 ngày 24/10 và kéo dài hai giờ, hãy ghép ngày trước:

```java
LocalDateTime startedAt = LocalDate.of(2026, 10, 24)
        .atTime(LocalTime.of(23, 30));
LocalDateTime endedAt = startedAt.plusHours(2);

System.out.println(endedAt); // 2026-10-25T01:30
```

Nếu cần đo **đúng hai giờ đã trôi qua theo instant** ở vùng có DST, hãy tính trên `Instant` hoặc `ZonedDateTime.plusHours(2)` với zone đã xác định, thay vì tùy tiện đổi `LocalDateTime` qua giờ nhảy DST. `plusHours` trên `ZonedDateTime` sử dụng trục thời gian instant, còn `LocalDateTime.plusHours` chỉ dùng các trường ngày giờ địa phương.

## 7. Ví dụ hoàn chỉnh Java 17+

Tạo tệp **`LocalTimeCombineDemo.java`**:

```java
import java.time.Instant;
import java.time.LocalDate;
import java.time.LocalDateTime;
import java.time.LocalTime;
import java.time.OffsetDateTime;
import java.time.OffsetTime;
import java.time.ZoneId;
import java.time.ZoneOffset;
import java.time.ZonedDateTime;

public class LocalTimeCombineDemo {
    public static void main(String[] args) {
        LocalDate date = LocalDate.of(2026, 10, 24);
        LocalTime time = LocalTime.of(9, 30);
        ZoneOffset offset = ZoneOffset.ofHours(7);

        LocalDateTime localDateTime = time.atDate(date);
        LocalDateTime sameLocalDateTime = date.atTime(time);
        OffsetTime offsetTime = time.atOffset(offset);
        OffsetDateTime offsetDateTime = localDateTime.atOffset(offset);
        OffsetDateTime byDateAndOffsetTime = date.atTime(offsetTime);
        Instant instant = offsetDateTime.toInstant();

        System.out.println("time = " + time);
        System.out.println("local date-time = " + localDateTime);
        System.out.println("same local = "
                + localDateTime.equals(sameLocalDateTime));
        System.out.println("offset time = " + offsetTime);
        System.out.println("offset date-time = " + offsetDateTime);
        System.out.println("same offset date-time = "
                + offsetDateTime.equals(byDateAndOffsetTime));
        System.out.println("instant = " + instant);
        System.out.println("epoch equal = "
                + (time.toEpochSecond(date, offset)
                == instant.getEpochSecond()));

        OffsetTime utcTime = offsetTime.withOffsetSameInstant(
                ZoneOffset.UTC);
        System.out.println("offset time as UTC = " + utcTime);

        ZoneId vietnam = ZoneId.of("Asia/Ho_Chi_Minh");
        ZonedDateTime zoned = localDateTime.atZone(vietnam);
        System.out.println("zoned = " + zoned);
        System.out.println("zoned instant same = "
                + zoned.toInstant().equals(instant));

        LocalTime late = LocalTime.of(23, 30);
        System.out.println("time + 2h = " + late.plusHours(2));
        System.out.println("date-time + 2h = "
                + date.atTime(late).plusHours(2));

        ZoneId berlin = ZoneId.of("Europe/Berlin");
        ZonedDateTime gap = LocalDateTime.of(2024, 3, 31, 2, 30)
                .atZone(berlin);
        ZonedDateTime overlapEarly =
                LocalDateTime.of(2024, 10, 27, 2, 30)
                        .atZone(berlin);
        ZonedDateTime overlapLate =
                overlapEarly.withLaterOffsetAtOverlap();

        System.out.println("Berlin gap = " + gap);
        System.out.println("Berlin overlap early = " + overlapEarly);
        System.out.println("Berlin overlap late = " + overlapLate);
    }
}
```

Biên dịch/chạy với JDK 17 trở lên:

```bash
javac LocalTimeCombineDemo.java
java LocalTimeCombineDemo
```

Kết quả dự kiến với dữ liệu múi giờ chuẩn có các quy tắc Berlin 2024:

```text
time = 09:30
local date-time = 2026-10-24T09:30
same local = true
offset time = 09:30+07:00
offset date-time = 2026-10-24T09:30+07:00
same offset date-time = true
instant = 2026-10-24T02:30:00Z
epoch equal = true
offset time as UTC = 02:30Z
zoned = 2026-10-24T09:30+07:00[Asia/Ho_Chi_Minh]
zoned instant same = true
time + 2h = 01:30
date-time + 2h = 2026-10-25T01:30
Berlin gap = 2024-03-31T03:30+02:00[Europe/Berlin]
Berlin overlap early = 2024-10-27T02:30+02:00[Europe/Berlin]
Berlin overlap late = 2024-10-27T02:30+01:00[Europe/Berlin]
```

Các dòng `same local`, `same offset date-time` và `zoned instant same` cho thấy những con đường kết hợp khác nhau vẫn có thể xác định **cùng giá trị hoặc cùng `Instant`** khi ngày, giờ và quy tắc offset được cung cấp nhất quán. Ba dòng Berlin minh họa rằng **vùng địa lý có quy tắc** cần được phân giải theo ngày thực tế, không chỉ gắn một số offset cố định.

## 8. Chọn kiểu cho tình huống thực tế

### A. Giờ mở cửa lặp lại hằng ngày

Một cửa hàng mở lúc **09:30 theo giờ địa phương**. Nếu chỉ lưu `LocalTime.of(9,30)`, bạn đang lưu **giờ trên đồng hồ**, chưa lưu thời điểm mở cửa của một ngày cụ thể. Để tạo sự kiện cho ngày 24/10/2026 ở Việt Nam:

```java
LocalTime opensAt = LocalTime.of(9, 30);
LocalDate targetDate = LocalDate.of(2026, 10, 24);
ZoneId storeZone = ZoneId.of("Asia/Ho_Chi_Minh");

ZonedDateTime opening = opensAt.atDate(targetDate)
        .atZone(storeZone);
Instant openingInstant = opening.toInstant();
```

Với lịch lặp lại cho nhiều ngày ở vùng có DST, hãy kết hợp lại **ngày + giờ + vùng** cho từng ngày để dùng quy tắc offset đúng. Nếu lấy offset của hôm nay rồi gắn cứng cho tất cả ngày trong tương lai, có thể sai một giờ hoặc nhiều hơn ở thời điểm chuyển DST.

### B. Nhận API có giờ và offset nhưng thiếu ngày

Ví dụ phía đối tác trả `"09:30+07:00"`, có thể parse thành:

```java
OffsetTime value = OffsetTime.parse("09:30+07:00");
```

Nếu chỉ muốn hiển thị giờ kèm offset, `OffsetTime` là đủ. Nếu muốn lưu lịch sử sự kiện tuyệt đối, yêu cầu **ngày sự kiện** từ nguồn hoặc một quy tắc nghiệp vụ xác định; không được tự gán ngày hôm nay nếu bản ghi không cung cấp thông tin ấy. Sau khi có ngày, dùng `date.atTime(value).toInstant()`.

### C. Lịch họp có ngày/giờ theo vùng địa lý

Một cuộc hẹn “02:30 ngày 27/10/2024 ở Berlin” trùng giờ lặp DST. Nếu không hỏi người dùng muốn lần 02:30 **trước hay sau** khi đồng hồ lùi, sẽ có hai instant hợp lệ. API có thể mặc định chọn một, nhưng mặc định đó có thể không phải ý định của người dùng. Kiểm tra `getValidOffsets` trước khi chốt lịch; lưu `Instant` chính xác và thông tin vùng/offset khi cần hiển thị hoặc giải thích quyết định.

### D. Tính hạn chót qua nửa đêm

Nếu có ngày + giờ bắt đầu, luôn ghép ngày trước rồi cộng khoảng thời gian. Nếu có yêu cầu “chính xác 2 giờ thực”, chuyển sang trục `Instant` khi tính thời lượng; nếu có yêu cầu “ngày mai cùng giờ địa phương”, tính theo lịch vùng, có xét DST. Hai loại yêu cầu không luôn tương đương.

## 9. Sai lầm thường gặp

| Sai lầm | Vì sao sai | Cách sửa |
| --- | --- | --- |
| Cho rằng `LocalTime.atDate(date)` đã là timestamp UTC | `LocalDateTime` không có offset/zone | Thêm offset hoặc `ZoneId` để xác định `Instant` |
| Cho rằng `LocalTime.atOffset(offset)` có thể gọi `toInstant()` | `OffsetTime` không giữ ngày | Ghép `LocalDate`: `date.atTime(offsetTime).toInstant()` |
| Nhầm `ZoneOffset` và `ZoneId` | Offset là số cố định; vùng chứa quy tắc thay đổi theo thời gian | Chọn offset khi dữ liệu chỉ có offset; chọn vùng khi lịch gắn địa điểm |
| Gắn offset hiện tại cho lịch tương lai ở vùng có DST | Offset có thể thay đổi theo ngày | Xác định `ZoneId` và phân giải theo ngày thực tế |
| Nghĩ `atZone` không thể đổi local time | Giờ nằm trong DST gap có thể được đẩy tiến | Kiểm tra `getValidOffsets` và giải quyết gap/overlap theo nghiệp vụ |
| Nghĩ ngày giờ trong DST overlap chỉ có một instant | Có hai offset hợp lệ | Chọn rõ offset trước/sau; dùng `ofStrict` nếu cần từ chối trường hợp sai |
| Cộng giờ chỉ trên `LocalTime` rồi suy ra ngày kết thúc | `LocalTime.plusHours` quay vòng 24h, mất ngày | Kết hợp thành `LocalDateTime` hoặc `ZonedDateTime` trước |
| Chuyển offset trên `OffsetTime` rồi tin đã bảo toàn ngày thực tế | `OffsetTime` không mang ngày và có thể qua nửa đêm | Dùng `OffsetDateTime.withOffsetSameInstant` khi cần giữ ngày/thời điểm |
| Lưu mỗi `Instant` rồi kỳ vọng khôi phục vùng ban đầu | `Instant` không chứa zone/offset ban đầu | Lưu thêm zone/offset theo yêu cầu nghiệp vụ |
| Dùng `LocalTime.now()` để xác định giờ giao dịch ở địa điểm khác | Mặc định theo hệ thống JVM, có thể khác vùng mong muốn | Lấy thời gian theo `Clock`/`ZoneId` nghiệp vụ |

## 10. Câu hỏi tự kiểm tra

1. **`LocalTime.of(9,30).atDate(LocalDate.of(2026,10,24))` trả kiểu gì?**  
   → `LocalDateTime`: `2026-10-24T09:30`. Chưa có `Instant`.
2. **`LocalTime.of(9,30).atOffset(ZoneOffset.ofHours(7))` trả kiểu gì?**  
   → `OffsetTime`: `09:30+07:00`. Vẫn thiếu ngày.
3. **Làm sao đổi `09:30+07:00` ngày 24/10/2026 thành UTC?**  
   → `date.atTime(offsetTime).toInstant()` → `2026-10-24T02:30:00Z`.
4. **Tại sao không nên cố định `ZoneOffset.ofHours(1)` cho mọi ngày tại Berlin?**  
   → Quy tắc vùng có DST khiến offset thay đổi theo ngày.
5. **`LocalTime.of(23,30).plusHours(2)` cho kết quả nào?**  
   → `01:30`; không lưu thông tin đã sang ngày tiếp theo.
6. **Điều gì xảy ra khi ghép `2024-03-31T02:30` với `Europe/Berlin`?**  
   → Đó là giờ không tồn tại trong DST gap; `atZone` thông thường dịch thành `03:30+02:00`.
7. **Với `2024-10-27T02:30` ở Berlin, cần chú ý gì?**  
   → Giờ lặp có hai offset hợp lệ, nên cần chính sách chọn lần xuất hiện.
8. **Có thể lưu lịch “09:30 mỗi ngày” chỉ bằng `Instant` không?**  
   → Một `Instant` chỉ định một lần cụ thể; để biểu diễn quy tắc lặp giờ địa phương, giữ `LocalTime` và `ZoneId`, rồi phân giải từng ngày.

### Nguồn API Java chính thức

- [`LocalTime` — `atDate`, `atOffset`, `toEpochSecond`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/LocalTime.html)
- [`LocalDate` — `atTime(LocalTime)` và `atTime(OffsetTime)`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/LocalDate.html)
- [`LocalDateTime` — `atOffset`, `atZone` và DST](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/LocalDateTime.html)
- [`ZoneRules` — `getValidOffsets`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/zone/ZoneRules.html)

**Ghi nhớ:** `LocalTime + LocalDate → LocalDateTime`; `LocalTime + ZoneOffset → OffsetTime`; **ngày + giờ + offset → OffsetDateTime → Instant**. Khi giờ địa phương gắn với một địa điểm và có thể chịu DST, ưu tiên `ZoneId` và xác định rõ cách giải quyết gap/overlap.
