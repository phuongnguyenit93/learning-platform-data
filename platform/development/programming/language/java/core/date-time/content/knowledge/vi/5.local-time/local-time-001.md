# LocalTime trong Java: biểu diễn giờ trong ngày, không có ngày và múi giờ

## 1. LocalTime là gì?

`java.time.LocalTime` là kiểu dữ liệu trong **Java Date and Time API** (module `java.base`), dùng để biểu diễn **giờ trên đồng hồ trong một ngày theo lịch ISO**, gồm giờ, phút, giây và nano giây. Đây là một giá trị **local/wall-clock time**: nó chỉ nói “đồng hồ chỉ mấy giờ”, không nói **ngày nào**, **ở đâu**, hay **đó là thời điểm tuyệt đối nào trên dòng thời gian UTC**.

Ví dụ: `LocalTime.of(9, 30)` có nghĩa **09:30**, hữu ích cho giờ bắt đầu lớp học, giờ mở cửa cửa hàng hoặc nhắc việc mỗi ngày. Không thể suy ra từ `09:30` rằng lúc đó là `2026-10-24T02:30:00Z`, bởi để suy ra một `Instant` cần biết ít nhất **ngày và múi giờ/offset hợp lệ**. Cùng 09:30 tại TP.HCM, Tokyo và New York thường tương ứng các thời điểm UTC khác nhau.

Đặc tính của `LocalTime`:

- **Không có ngày:** không chứa năm, tháng, ngày hoặc thứ trong tuần; không biết 09:30 thuộc hôm qua, hôm nay hay ngày mai.
- **Không có múi giờ hoặc UTC offset:** không chứa `ZoneId`, `ZoneOffset`, quy tắc Daylight Saving Time (DST) hay thông tin UTC.
- **Độ chính xác nano giây:** tối đa 9 chữ số thập phân của giây; không có thông tin về ngày nhuận hay giây nhuận.
- **Immutable, thread-safe:** một phép toán trả về giá trị mới; đối tượng ban đầu không bị thay đổi, có thể dùng an toàn giữa nhiều thread.
- **Value-based:** so sánh giá trị bằng `equals` hoặc `compareTo`; không dựa vào identity (`==`), không dùng `synchronized` trên instance như đối tượng nhận dạng ổn định.
- **Thời gian hợp lệ:** từ `00:00:00.000000000` tới `23:59:59.999999999`; `24:00` không phải một `LocalTime` hợp lệ. Giây có giá trị từ 0 đến 59; không chấp nhận `23:59:60`.

### Mô hình khái niệm

| Giá trị | Java type | Có ngày? | Có múi giờ? | Một thời điểm tuyệt đối? |
| --- | --- | --- | --- | --- |
| `09:30` | `LocalTime` | Không | Không | Không |
| `2026-10-24` | `LocalDate` | Có | Không | Không |
| `2026-10-24T09:30` | `LocalDateTime` | Có | Không | Chưa chắc |
| `2026-10-24T09:30+07:00` | `OffsetDateTime` | Có | Offset `+07:00` | Có |
| `2026-10-24T09:30+07:00[Asia/Ho_Chi_Minh]` | `ZonedDateTime` | Có | Vùng + offset | Có |
| `2026-10-24T02:30:00Z` | `Instant` | Mốc UTC | Không gắn một vùng địa phương | Có |

`LocalTime` **không phải** kiểu timestamp, không thể thay `Instant` để ghi mốc sự kiện và không đủ để xác định lịch hẹn xuyên quốc gia.

## 2. Khi nào dùng LocalTime?

Dùng `LocalTime` khi nghiệp vụ quan tâm **giờ trên mặt đồng hồ**, tách khỏi ngày cụ thể:

1. **Giờ mở cửa/đóng cửa:** siêu thị mở 08:00, đóng 22:00 mỗi ngày.
2. **Thời khóa biểu:** môn học bắt đầu 09:30 hằng thứ Hai; dùng thêm `DayOfWeek` hoặc lịch lặp cho quy tắc thứ.
3. **Cấu hình nhắc việc:** gửi thông báo lúc 07:15 theo múi giờ người dùng. Lưu `LocalTime` cùng **`ZoneId`** hoặc cấu hình vùng người dùng; riêng giờ không đủ để xác định lần chạy thực.
4. **Giờ cắt giao dịch (cut-off):** xử lý đơn trước 17:00 theo giờ doanh nghiệp; cần `LocalDate` và vùng khi tính hạn thực tế.
5. **Giờ đặt khám trong một ngày:** người dùng chọn `14:45`; khi xác nhận slot thực tế, phải gắn ngày và vùng.

**Không dùng riêng `LocalTime`** cho log, createdAt/updatedAt, timeout đo thời gian thực, ETA tuyệt đối, ghi lịch họp toàn cầu hoặc so sánh sự kiện ở các vùng. Tình huống đó thường cần `Instant`, `Duration`, `OffsetDateTime` hoặc `ZonedDateTime`.

### Câu hỏi lựa chọn kiểu nhanh

- Chỉ hỏi “mấy giờ trong ngày?” → `LocalTime`.
- Hỏi “mấy giờ vào **ngày** X?” → `LocalDateTime`; vẫn chưa có timezone.
- Hỏi “mấy giờ vào ngày X **ở vùng** Y?” → `ZonedDateTime`; cân nhắc DST khi nhập.
- Hỏi “sự kiện xảy ra **chính xác lúc nào**?” → `Instant`.
- Hỏi “đã trôi qua bao lâu?” → `Duration` trên các mốc tuyệt đối khi cần elapsed time thực.

## 3. Tạo LocalTime

### 3.1. Các factory method

```java
import java.time.LocalTime;

LocalTime midnight = LocalTime.MIDNIGHT;        // 00:00
LocalTime noon = LocalTime.NOON;                // 12:00
LocalTime min = LocalTime.MIN;                  // 00:00
LocalTime max = LocalTime.MAX;                  // 23:59:59.999999999

LocalTime morning = LocalTime.of(9, 30);       // 09:30
LocalTime precise = LocalTime.of(9, 30, 15);   // 09:30:15
LocalTime nanos = LocalTime.of(9, 30, 15, 123_456_789);
LocalTime fromSecond = LocalTime.ofSecondOfDay(34_200); // 09:30
LocalTime fromNano = LocalTime.ofNanoOfDay(34_200_000_000_000L);
```

*Đây là các dòng dùng bên trong class/method, chưa phải chương trình chạy độc lập.*

- `of(hour, minute)`: giờ 0–23, phút 0–59; có overload thêm giây và nano giây.
- `ofSecondOfDay(long)`: số giây từ đầu ngày, từ 0 tới 86.399.
- `ofNanoOfDay(long)`: số nano giây từ đầu ngày, từ 0 tới 86.399.999.999.999.
- `MIN` và `MIDNIGHT` cùng giá trị 00:00; `MAX` là nano giây cuối ngày, không phải 24:00.

Nếu truyền `LocalTime.of(24, 0)`, `LocalTime.of(10, 60)`, `ofSecondOfDay(86_400)` hoặc các thành phần vượt miền giá trị, Java ném `DateTimeException` (hoặc lớp con tùy lời gọi). Đây là kiểm tra **giờ hợp lệ**, không phải kiểm tra giờ đó có tồn tại trong timezone cụ thể hay không.

### 3.2. Parse từ văn bản

```java
import java.time.LocalTime;

LocalTime a = LocalTime.parse("09:30");                 // 09:30
LocalTime b = LocalTime.parse("09:30:15");              // 09:30:15
LocalTime c = LocalTime.parse("09:30:15.123456789");    // chính xác 9 chữ số nano
```

`LocalTime.parse(text)` dùng `DateTimeFormatter.ISO_LOCAL_TIME`. Nếu đầu vào là `9:30 AM` hoặc `09h30`, cần formatter riêng; không giả định định dạng người dùng luôn được parse mặc định. Giá trị sai như `"25:00"` hoặc `"09:99"` dẫn tới `DateTimeParseException`.

### 3.3. Lấy giờ hiện tại

```java
import java.time.*;

LocalTime machineLocal = LocalTime.now(); // dựa timezone mặc định và thời điểm hiện tại của máy
LocalTime inTokyo = LocalTime.now(ZoneId.of("Asia/Tokyo"));

Clock fixed = Clock.fixed(
    Instant.parse("2026-01-01T12:00:00Z"),
    ZoneId.of("Asia/Ho_Chi_Minh"));
LocalTime stable = LocalTime.now(fixed); // 19:00
```

`now()` tiện cho ứng dụng tương tác, nhưng kết quả đổi theo thời gian và timezone cài ở máy. Khi xây business service có kiểm thử, ưu tiên **tiêm `Clock`** và gọi `LocalTime.now(clock)`. Tham số `ZoneId` trong `now(zone)` chỉ nói **đổi thời điểm hiện tại thành đồng hồ địa phương ở vùng được chọn**, không khiến đối tượng `LocalTime` giữ lại thông tin vùng.

`LocalTime.ofInstant(instant, zone)` (Java 9+) cũng lấy **giờ địa phương** của một `Instant` trong `ZoneId` cụ thể. Điều quan trọng là cần đồng thời cả mốc thời gian thực và vùng. Có thể dùng `instant.atZone(zone).toLocalTime()` với ý nghĩa tương tự.

## 4. Đọc từng trường và chuyển sang đơn vị số

| Method | Ý nghĩa | Với `09:30:15.123456789` |
| --- | --- | --- |
| `getHour()` | Giờ trong ngày, 0–23 | `9` |
| `getMinute()` | Phút trong giờ, 0–59 | `30` |
| `getSecond()` | Giây trong phút, 0–59 | `15` |
| `getNano()` | Nano giây trong giây, 0–999.999.999 | `123456789` |
| `toSecondOfDay()` | Tổng giây từ 00:00 | `34215` |
| `toNanoOfDay()` | Tổng nano giây từ 00:00 | `34215123456789` |
| `get(ChronoField.HOUR_OF_DAY)` | Đọc trường theo `TemporalField` | `9` |

Ví dụ `LocalTime.of(9,30).toSecondOfDay()` bằng `9×3600 + 30×60 = 34200`. Với `toNanoOfDay()`, giá trị dùng `long` vì có thể vượt giới hạn `int`.

`LocalTime` triển khai `Temporal` và `TemporalAdjuster`. Do đó có thể dùng `get(ChronoField...)`, `isSupported(...)`, `with(...)` và `plus(...)` để thao tác theo trường/đơn vị. Tuy nhiên không có trường ngày: đọc `ChronoField.DAY_OF_MONTH` từ `LocalTime` là sai ngữ nghĩa và có thể ném `UnsupportedTemporalTypeException`.

## 5. Cộng, trừ và thay đổi thành phần giờ

`LocalTime` là immutable: method trả giá trị mới. Ví dụ:

```java
import java.time.LocalTime;

LocalTime start = LocalTime.of(9, 30);
LocalTime after = start.plusHours(2).plusMinutes(15); // 11:45
LocalTime before = start.minusMinutes(45);           // 08:45
LocalTime roundedHour = start.withMinute(0);         // 09:00
LocalTime shifted = start.withHour(13);               // 13:30
// start vẫn bằng 09:30
```

Các nhóm method quan trọng:

- `plusHours`, `plusMinutes`, `plusSeconds`, `plusNanos` và phiên bản `minus...`.
- `withHour`, `withMinute`, `withSecond`, `withNano` để thay một trường và giữ các trường còn lại.
- `plus(long, TemporalUnit)` hoặc `with(TemporalField, long)` khi code dùng API `java.time.temporal` tổng quát.
- `truncatedTo(ChronoUnit.MINUTES)` để đặt phần giây và nano về 0; `truncatedTo(ChronoUnit.HOURS)` để đặt phút/giây/nano về 0. Đây là **cắt phần lẻ**, không làm tròn đến đơn vị gần nhất.

### 5.1. Quan trọng: phép toán quay vòng trong 24 giờ

```java
LocalTime night = LocalTime.of(23, 30);
LocalTime later = night.plusHours(2); // 01:30
LocalTime earlier = LocalTime.MIDNIGHT.minusMinutes(1); // 23:59
```

Đây là **số giờ trên đồng hồ** sau khi cộng/trừ theo vòng 24 giờ; không có ngày để biểu thị “đã sang hôm sau”. `night.plusHours(24)` trở lại 23:30, và `plusHours(48)` vẫn là 23:30. Nếu bài toán cần biết một sự kiện cách 2 ngày hay một ngày đã đổi, phải có `LocalDate`/`LocalDateTime` hoặc mốc `Instant` tương ứng.

Không thể dựa vào kết quả `LocalTime.plusHours(...)` để kết luận số ngày đã trôi qua.

### 5.2. Tính chênh lệch giữa hai LocalTime

```java
import java.time.*;
import java.time.temporal.ChronoUnit;

LocalTime start = LocalTime.of(9, 30);
LocalTime end = LocalTime.of(17, 45);

long minutes = ChronoUnit.MINUTES.between(start, end); // 495
Duration duration = Duration.between(start, end);       // PT8H15M
```

`Duration.between(LocalTime, LocalTime)` là khoảng chênh lệch **theo cặp giờ trên cùng trục giờ địa phương**. Nó không tự giả định “sang ngày hôm sau”:

```java
LocalTime late = LocalTime.of(23, 30);
LocalTime early = LocalTime.of(0, 30);
Duration wrongForOvernight = Duration.between(late, early); // PT-23H
```

Nếu nghiệp vụ quy định một ca bắt đầu 23:30 và kết thúc 00:30 **ngày kế tiếp**, kết hợp với ngày:

```java
LocalDate d = LocalDate.of(2026, 10, 24);
LocalDateTime begin = d.atTime(23, 30);
LocalDateTime finish = d.plusDays(1).atTime(0, 30);

Duration actualByLocalCalendar = Duration.between(begin, finish); // PT1H
```

Ví dụ cuối cho kết quả một giờ vì ngày đã được chỉ rõ, nhưng **`LocalDateTime` vẫn chưa giải quyết timezone/DST**. Nếu tính thời lượng thực tại vùng có chuyển giờ mùa hè, hãy xác định `ZoneId`, giải quyết offset cho mỗi thời điểm rồi dùng `Duration.between(startZoned.toInstant(), endZoned.toInstant())`. Hai mốc `Instant` cho kết quả elapsed time rõ ràng.

**Lưu ý:** nếu tính “tới lần xuất hiện kế tiếp của giờ đóng cửa trong tối đa 24 giờ”, có thể dùng modulo cho bài toán lịch lặp đã định nghĩa rõ. Tuy nhiên modulo sẽ loại bỏ thông tin số ngày, và khoảng 00:00 tới 00:00 có thể có ý nghĩa **0 giờ hoặc 24 giờ** tùy yêu cầu; cần xác định trước chính sách nghiệp vụ.

## 6. So sánh và bằng nhau

Các cách dùng tiêu biểu:

- `a.equals(b)`: bằng nhau về giá trị giờ/phút/giây/nano.
- `a.isBefore(b)`: giờ đồng hồ đứng trước trong cùng chu kỳ một ngày.
- `a.isAfter(b)`: giờ đồng hồ đứng sau trong cùng chu kỳ.
- `a.compareTo(b)`: âm/0/dương để sắp xếp theo thứ tự giờ trong ngày.

```java
LocalTime opening = LocalTime.of(9, 30);
LocalTime closing = LocalTime.of(17, 45);

boolean earlier = opening.isBefore(closing);          // true
boolean identical = opening.equals(LocalTime.parse("09:30")); // true
```

Không suy ra thứ tự sự kiện ngoài đời từ so sánh `LocalTime` khác ngày hoặc khác vùng. Ví dụ 23:45 hôm nay có thể **sớm hơn** 00:15 ngày mai theo thứ tự thời điểm tuyệt đối, nhưng phép `LocalTime.of(23,45).isAfter(LocalTime.of(0,15))` vẫn `true` bởi chỉ so “giờ trong ngày”.

Đối tượng `LocalTime` là value-based, vì thế **không dựa vào `==`** để kiểm tra hai giá trị, dù có một số giá trị có thể được JVM tái sử dụng. Ưu tiên `equals`.

## 7. Định dạng và parse có kiểm soát

### 7.1. Chuẩn ISO

`LocalTime.toString()` sinh biểu diễn ISO tự chọn độ chi tiết đủ giữ giá trị, chẳng hạn:

| Giá trị | Chuỗi hiển thị |
| --- | --- |
| `LocalTime.of(9,30)` | `09:30` |
| `LocalTime.of(9,30,15)` | `09:30:15` |
| `LocalTime.of(9,30,15,123_000_000)` | `09:30:15.123` |
| `LocalTime.of(9,30,15,123_456_789)` | `09:30:15.123456789` |

Mặc dù Java có precision nano, đồng hồ phần cứng/OS không nhất thiết cung cấp độ chính xác quan sát tương đương. Không dùng nano giây chỉ vì type hỗ trợ; chọn precision theo dữ liệu thực tế và yêu cầu nghiệp vụ.

### 7.2. Pattern HH:mm và 12 giờ

```java
import java.time.LocalTime;
import java.time.format.DateTimeFormatter;
import java.util.Locale;

DateTimeFormatter hhmm = DateTimeFormatter.ofPattern("HH:mm", Locale.ROOT);
String text = LocalTime.of(9, 30).format(hhmm); // "09:30"
LocalTime parsed = LocalTime.parse(text, hhmm); // 09:30
```

Một số ký hiệu cần nắm:

| Pattern | Ý nghĩa | Minh họa |
| --- | --- | --- |
| `HH` | Giờ 00–23 | `09`, `17` |
| `H` | Giờ 0–23, tối thiểu một chữ số | `9`, `17` |
| `mm` | Phút 00–59 | `03`, `30` |
| `ss` | Giây 00–59 | `05`, `15` |
| `S` đến `SSSSSSSSS` | Phần thập phân giây (fraction) | `SSS` → 3 chữ số |
| `hh` | Giờ 01–12 | `09`, `11` |
| `a` | AM/PM | `AM`/`PM` tùy locale |

`MM` là **tháng**, không phải phút. Với `hh:mm a`, nên truyền `Locale.ENGLISH` nếu chuỗi đầu vào chứa `AM`/`PM` tiếng Anh, tránh phụ thuộc locale của máy. Khi không cần giao diện 12 giờ, `HH:mm` thường dễ dùng và ít nhầm hơn.

### 7.3. Parse sai và giới hạn dữ liệu

```java
import java.time.LocalTime;
import java.time.format.DateTimeParseException;

try {
    LocalTime input = LocalTime.parse("25:00");
} catch (DateTimeParseException ex) {
    System.out.println("Gio khong hop le");
}
```

Chuỗi `25:00` nằm ngoài miền giờ 0–23, nên ví dụ in `Gio khong hop le`. Dùng `DateTimeParseException` ở ranh giới nhập liệu để trả lỗi thân thiện cho người dùng. Trong API, có thể lựa chọn lưu chuỗi chuẩn hóa như `HH:mm` hoặc ISO với giây, tùy precision yêu cầu.

**Chú ý về độ chính xác khi định dạng:** `LocalTime.of(9,30,15).format(DateTimeFormatter.ofPattern("HH:mm"))` tạo ra chuỗi `09:30` và **mất thông tin giây**; nếu parse trở lại thành `LocalTime`, không thể khôi phục `:15`. Chọn format không làm mất precision có chủ ý khi dùng cho lưu trữ/đồng bộ.

## 8. LocalTime không có ngày và múi giờ: hệ quả thực tế

### 8.1. Không trực tiếp chuyển LocalTime thành Instant

Một giờ đơn lẻ như 09:30 **không đủ dữ liệu để có UTC timestamp**. Bạn cần ít nhất một ngày và một vùng/offset, cộng với chính sách nếu ngày đó có DST.

```java
import java.time.*;

LocalTime appointmentTime = LocalTime.of(9, 30);
LocalDate appointmentDate = LocalDate.of(2026, 10, 24);
ZoneId city = ZoneId.of("Asia/Ho_Chi_Minh");

LocalDateTime wallTime = appointmentDate.atTime(appointmentTime);
ZonedDateTime zoned = wallTime.atZone(city);
Instant instant = zoned.toInstant();
```

Trong ví dụ, `instant` là `2026-10-24T02:30:00Z` do TP.HCM dùng offset `+07:00` tại ngày đã chọn. **Không** ghép nhầm `LocalTime` và `ZoneOffset.UTC` nếu ý nghĩa nghiệp vụ thực sự là giờ địa phương tại TP.HCM.

### 8.2. DST khiến cùng giờ địa phương có thể vô hiệu hoặc trùng

Ở `America/New_York` năm 2026:

- **08/03/2026 lúc 02:30:** giờ địa phương không tồn tại khi đồng hồ nhảy từ 02:00 lên 03:00. `getValidOffsets(local)` trả danh sách rỗng.
- **01/11/2026 lúc 01:30:** giờ lặp lại hai lần, lần ở offset `-04:00` và lần ở `-05:00`. `getValidOffsets(local)` trả hai lựa chọn.
- **Một giờ bình thường:** trả một offset.

Ví dụ nhận giờ người dùng chọn:

```java
import java.time.*;
import java.time.zone.ZoneRules;
import java.util.List;

LocalDateTime local = LocalDateTime.of(
        LocalDate.of(2026, 11, 1),
        LocalTime.of(1, 30));
ZoneId zone = ZoneId.of("America/New_York");
ZoneRules rules = zone.getRules();
List<ZoneOffset> options = rules.getValidOffsets(local);

if (options.isEmpty()) {
    // Giờ không tồn tại; từ chối hoặc yêu cầu chọn giờ khác.
} else if (options.size() == 2) {
    // Giờ xảy ra hai lần; yêu cầu chọn offset/lần xuất hiện.
} else {
    // Giờ bình thường, có đúng một offset.
}
```

Đây là **minh họa xử lý nằm trong method**. Sau khi người dùng đã chọn offset hợp lệ, có thể dùng `ZonedDateTime.ofStrict(local, selectedOffset, zone)` để dựng một mốc chính xác.

`LocalTime` tự nó **không biết DST** vì không biết ngày và vùng. Nó vẫn có thể biểu diễn `02:30`; câu hỏi “02:30 hôm đó có tồn tại ở New York không?” phải được trả lời bằng **`LocalDateTime + ZoneId + ZoneRules`**.

### 8.3. “09:00 mỗi ngày” khác “sau mỗi 24 giờ”

Nếu hệ thống cần gửi nhắc việc **09:00 mỗi ngày tại New York**, lặp theo giờ địa phương phải giữ `LocalTime.of(9,0)` + `ZoneId` và tìm **ngày kế tiếp**, sau đó giải quyết DST. Lặp một `Instant` bằng `Duration.ofHours(24)` có thể làm giờ địa phương đổi trong ngày chuyển DST (ví dụ 09:00 thành 10:00 hoặc 08:00 theo vùng/quy tắc). Chọn mô hình dữ liệu theo yêu cầu: **giờ đồng hồ địa phương** hay **khoảng cách elapsed time thực**.

## 9. Ví dụ Java 17+ chạy đầy đủ

Tạo file **`LocalTimeDemo.java`**. Chương trình tổng hợp: tạo và đọc `LocalTime`, đổi sang giây trong ngày, cộng giờ, so sánh, format, cắt giây, tính khoảng thời gian cùng ngày, giải quyết ca qua nửa đêm bằng `LocalDateTime`, và lấy giờ từ `Clock.fixed` để kết quả ổn định.

```java
import java.time.*;
import java.time.format.DateTimeFormatter;
import java.time.temporal.ChronoUnit;
import java.util.Locale;

public class LocalTimeDemo {
    public static void main(String[] args) {
        LocalTime opening = LocalTime.of(9, 30);
        LocalTime closing = LocalTime.of(17, 45);
        LocalTime precise = LocalTime.parse("09:30:15.123456789");

        DateTimeFormatter hhmm = DateTimeFormatter.ofPattern("HH:mm", Locale.ROOT);
        Clock fixed = Clock.fixed(
                Instant.parse("2026-01-01T12:00:00Z"),
                ZoneId.of("Asia/Ho_Chi_Minh"));

        System.out.println("Mo cua: " + opening.format(hhmm));
        System.out.println("Do chinh xac: " + precise);
        System.out.println("Gio: " + opening.getHour());
        System.out.println("Giay tu dau ngay: " + opening.toSecondOfDay());
        System.out.println("Dong cua sau mo cua: " + closing.isAfter(opening));
        System.out.println("Phut mo cua: " + ChronoUnit.MINUTES.between(opening, closing));
        System.out.println("Cong 17 gio: " + opening.plusHours(17));
        System.out.println("Lam tron phut: " + precise.truncatedTo(ChronoUnit.MINUTES));
        System.out.println("Qua nua dem (chi gio): " + LocalTime.of(23, 30).plusHours(2));
        System.out.println("Duration nguoc: " +
                Duration.between(LocalTime.of(23, 30), LocalTime.of(0, 30)).toHours());
        LocalDate today = LocalDate.of(2026, 10, 24);
        LocalDateTime start = today.atTime(23, 30);
        LocalDateTime end = today.plusDays(1).atTime(0, 30);
        System.out.println("Duration qua ngay: " + Duration.between(start, end).toHours());
        System.out.println("Clock co dinh (HCM): " + LocalTime.now(fixed));
    }
}
```

Chạy trong thư mục chứa file bằng JDK 17+:

```bash
javac -encoding UTF-8 LocalTimeDemo.java
java LocalTimeDemo
```

Kết quả stdout được xác định bằng dữ liệu cố định trong chương trình:

```text
Mo cua: 09:30
Do chinh xac: 09:30:15.123456789
Gio: 9
Giay tu dau ngay: 34200
Dong cua sau mo cua: true
Phut mo cua: 495
Cong 17 gio: 02:30
Lam tron phut: 09:30
Qua nua dem (chi gio): 01:30
Duration nguoc: -23
Duration qua ngay: 1
Clock co dinh (HCM): 19:00
```

**Phân tích output:**

- `opening.format(hhmm)` cho đúng `09:30`; `LocalTime.parse` giữ chính xác `.123456789`.
- `09:30` tương đương `34200` giây tính từ 00:00; từ `09:30` đến `17:45` là `8h15m = 495` phút.
- Cộng `17` giờ vào `09:30` quay vòng qua nửa đêm và trả `02:30` mà không lưu “ngày hôm sau”.
- `truncatedTo(MINUTES)` loại bỏ phần giây/nano, trả `09:30`; tên lệnh in ra “Lam tron phut” chỉ là nhãn hiển thị, bản chất phép toán là **truncate**, không round.
- `Duration.between(23:30,00:30)` giữa hai `LocalTime` trả `-23` giờ vì không có ngày; khi ghép ngày 24/10 và 25/10, chênh lệch là `1` giờ theo lịch địa phương.
- `Clock.fixed` cố định mốc UTC 12:00 và zone HCM; vì thế `LocalTime.now(fixed)` luôn 19:00, không phụ thuộc giờ thực của máy.

## 10. Lưu trữ, truyền API và kiểm thử

### 10.1. Lưu trong database và JSON

Khi dữ liệu thực sự là giờ mở cửa/giờ lặp hằng ngày, một trường kiểu SQL **`TIME` không mang múi giờ** thường phù hợp hơn timestamp. Với JDBC hỗ trợ Java 8+ date-time mappings, có thể truyền `LocalTime` bằng `PreparedStatement.setObject(index, localTime)` hoặc đọc qua `ResultSet.getObject(column, LocalTime.class)`; **kiểm tra driver cụ thể** vì cách hỗ trợ và precision có thể khác nhau.

Trong JSON, nên thỏa thuận format rõ ràng, ví dụ:

```json
{
  "opensAt": "09:30",
  "closesAt": "22:00",
  "businessZone": "Asia/Ho_Chi_Minh"
}
```

Chuỗi `09:30` biểu thị `LocalTime`. Trường `businessZone` là thông tin **riêng của nghiệp vụ**, cần khi chuyển giờ mở cửa thành một sự kiện cụ thể theo ngày. Đừng thêm ký tự `Z` vào `"09:30"`; `Z` mô tả offset UTC trên giá trị datetime/time phù hợp, không phải thành phần có sẵn của `LocalTime`.

Trong các framework JSON như Jackson, khả năng serialize/deserialize `LocalTime` phụ thuộc module Java Time và cấu hình mapper/format; kiểm tra integration thực tế, không giả định mọi framework tự parse giống nhau.

### 10.2. Tách đồng hồ khỏi nghiệp vụ

Code phụ thuộc “bây giờ” nên nhận `Clock` qua constructor:

```java
import java.time.Clock;
import java.time.LocalTime;

final class OpeningHoursService {
    private final Clock clock;

    OpeningHoursService(Clock clock) {
        this.clock = clock;
    }

    boolean isOpen(LocalTime opens, LocalTime closes) {
        LocalTime now = LocalTime.now(clock);
        return !now.isBefore(opens) && now.isBefore(closes);
    }
}
```

Đây là **class minh họa**, không phải file có `main`. Hàm `isOpen` dùng khoảng **[opens, closes)** và chỉ phù hợp khi `opens` đứng trước `closes` trong **cùng ngày lịch tại một vùng**. Nếu giờ mở cửa kéo dài qua nửa đêm, cần chính sách và thuật toán riêng; ví dụ thêm nhánh so sánh vòng ngày hoặc kết hợp `LocalDateTime`/`ZonedDateTime`. Khi timezone của business được cấu hình, truyền `Clock.system(businessZone)`; test dùng `Clock.fixed(..., businessZone)`.

### 10.3. Các ca kiểm thử cần có

| Trường hợp | Đầu vào | Kỳ vọng |
| --- | --- | --- |
| Giờ đầu ngày | `00:00` | `LocalTime.MIDNIGHT` |
| Giờ cuối ngày | `23:59:59.999999999` | `LocalTime.MAX` |
| Giờ ngoài giới hạn | `24:00` | `DateTimeException` khi dùng `of(24,0)` |
| Phút không hợp lệ | `09:60` | `DateTimeParseException` khi parse ISO |
| Độ chính xác | `09:30:15.123456789` | Giữ đủ 9 chữ số nano |
| Phép toán wrap | `23:30` + 2 giờ | `01:30` |
| Thay giá trị không mutate | `09:30` + 1 giờ | Giá trị mới 10:30; giá trị gốc vẫn 09:30 |
| Khoảng giờ cùng ngày | 09:30 → 17:45 | `495` phút |
| Khoảng qua nửa đêm | 23:30 ngày 24/10 → 00:30 ngày 25/10 | `60` phút khi ghép ngày |
| Giờ hiện tại có kiểm thử | `Clock.fixed` ở HCM | Giá trị giữ ổn định theo vùng cấu hình |
| DST gap/overlap | 02:30 ngày 08/03 và 01:30 ngày 01/11/2026, New York | Chỉ kiểm được sau khi có ngày + `ZoneId` |

**Đừng kiểm thử bằng `LocalTime.now()` không đối số** nếu test mong đợi một giá trị cố định. Ngoài ra, nếu so giờ quanh DST theo `LocalTime`, bạn chỉ đang so số trên đồng hồ, chưa biết khoảng thời gian thực.

## 11. Lỗi thường gặp và cách sửa

1. **Nhầm `LocalTime` với `LocalDateTime`:** `LocalTime.of(9,30)` không có thông tin ngày. Khi lịch hẹn cần ngày, ghép `LocalDate.atTime(time)`.
2. **Nghĩ `LocalTime` chứa timezone:** thực tế timezone chỉ được dùng khi tạo giờ từ `Clock`/`Instant`; instance kết quả không lưu `ZoneId`.
3. **Lưu createdAt bằng LocalTime:** cùng `09:30` xảy ra mỗi ngày; dùng `Instant` để xác định mốc event.
4. **Dùng `plusHours` để tính số ngày trôi qua:** `LocalTime` tự quay vòng sau 24 giờ; cần dữ liệu ngày hoặc timestamp.
5. **Tính ca xuyên đêm bằng `Duration.between(LocalTime,LocalTime)`:** kết quả có thể âm; gắn ngày bắt đầu/kết thúc, gắn zone/instant khi cần elapsed time thật.
6. **Nhầm `mm` với `MM`:** `mm` là phút, `MM` là tháng. Pattern `HH:mm` cho đồng hồ 24 giờ.
7. **Dùng `HH:mm` để serialize giờ có giây/nano:** làm mất thông tin; truyền định dạng ISO đủ precision hoặc contract API quy định đơn vị rõ.
8. **Dùng `==` để so instance:** dùng `equals` hoặc các method `isBefore`/`isAfter`.
9. **Thay đối tượng nhưng không dùng giá trị trả về:** `time.plusMinutes(5);` không sửa biến gốc. Gán `time = time.plusMinutes(5);`.
10. **Quên DST khi ghép LocalTime vào ngày/vùng:** `01:30` có thể xảy ra hai lần, `02:30` có thể không tồn tại; dùng `ZoneRules` và chính sách nghiệp vụ.
11. **Dùng ngày giả cố định để tạo Instant:** nếu ý nghĩa là giờ mở cửa lặp lại, việc gắn một ngày giả có thể tạo offset sai cho thời điểm thực tế; giữ `LocalTime + ZoneId` và chỉ giải quyết thành mốc khi đã biết ngày.

## 12. Bài tập thực hành

### Bài 1 — Đọc và tạo giờ

Tạo các giá trị `LocalTime` biểu diễn 06:05, 12:00, 23:59:30.250000000. In từng giá trị bằng `toString()` và dùng `getHour`/`getMinute`/`getNano` để kiểm tra. Thử tạo `LocalTime.of(24,0)` và giải thích nguyên nhân exception.

**Gợi ý kết quả:** `LocalTime.of(6,5).toString()` là `06:05`; `LocalTime.of(23,59,30,250_000_000).toString()` là `23:59:30.250`.

### Bài 2 — Khung giờ mở cửa trong cùng ngày

Cửa hàng mở `08:15` và đóng `20:45`. Viết hàm kiểm tra một `LocalTime` có nằm trong khoảng **[08:15,20:45)** hay không và tính số phút mở cửa. Trường hợp kiểm tra: `08:15` là mở, `20:44` là mở, `20:45` là đóng.

**Đáp án chênh lệch:** `ChronoUnit.MINUTES.between(08:15,20:45)` = `750` phút. Bài toán này **chưa** xử lý trường hợp thời gian qua ngày.

### Bài 3 — Ca làm qua nửa đêm

Một nhân viên bắt đầu `22:30` ngày 24/10/2026, kết thúc `06:00` ngày 25/10/2026. Ghép `LocalDateTime` đúng ngày rồi tính `Duration.between`; thời lượng là **7 giờ 30 phút** nếu xét đơn thuần ngày-giờ địa phương. Nếu ca diễn ra ở vùng có DST vào ngày chuyển giờ, đổi sang `ZonedDateTime`/`Instant` và so elapsed time thực.

### Bài 4 — Giờ hẹn theo vùng

Cho `LocalTime.of(9,30)`, ngày `2026-10-24` và `ZoneId.of("Asia/Ho_Chi_Minh")`. Tạo `ZonedDateTime` rồi chuyển sang `Instant`. Dự kiến `2026-10-24T02:30:00Z`. Giải thích vì sao chỉ từ `09:30` không thể có kết quả này.

### Bài 5 — Giờ hiện tại không phụ thuộc máy

Viết service nhận `Clock`, lấy `LocalTime.now(clock)`. Test với clock cố định ở mốc `2026-01-01T12:00:00Z` tại `Asia/Ho_Chi_Minh` và kiểm tra kết quả **19:00**; lặp lại 100 lần phải như nhau.

### Bài 6 — Câu hỏi thiết kế

Với ba trường: “giờ mở cửa 09:00 mỗi ngày”, “sự kiện được tạo lúc 09:00 ngày hôm qua”, “hẹn 09:00 ngày 24/10 tại Tokyo”, chọn kiểu dữ liệu phù hợp:

- Giờ mở cửa hằng ngày: `LocalTime` và có thể kèm `ZoneId` của cơ sở.
- Mốc tạo sự kiện: `Instant` (hoặc datetime có offset rõ).
- Lịch hẹn tại Tokyo: `LocalDate` + `LocalTime` + `ZoneId` → `ZonedDateTime`/`Instant` sau khi giải quyết quy tắc vùng.

## 13. Checklist tự đánh giá

- [ ] Nêu được rằng `LocalTime` biểu diễn **giờ trong ngày**, không chứa **ngày**, **ZoneId**, **ZoneOffset** hoặc `Instant`.
- [ ] Biết tạo bằng `of`, `parse`, `ofSecondOfDay` và hiểu giới hạn 00:00 đến 23:59:59.999999999.
- [ ] Biết đọc giờ/phút/giây/nano, chuyển sang giây/nano kể từ đầu ngày.
- [ ] Dùng được `plus`/`minus`/`with` và hiểu immutable cùng phép quay vòng 24 giờ.
- [ ] So sánh được hai giá trị `LocalTime` mà không suy diễn thứ tự sự kiện khác ngày.
- [ ] Định dạng/parse với `DateTimeFormatter` và xử lý chuỗi sai bằng `DateTimeParseException`.
- [ ] Biết cần ngày và `ZoneId` để chuyển giờ hẹn thành `Instant`; nhận biết trường hợp DST đặc biệt.
- [ ] Tính đúng khoảng qua nửa đêm bằng ngày thích hợp; khi cần thời gian thực, tính giữa `Instant`.
- [ ] Viết test ổn định bằng `Clock.fixed` thay cho đồng hồ môi trường.

## Tài liệu tham khảo chính thức (JDK 17)

- [`LocalTime` — API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/LocalTime.html)
- [`LocalDateTime` — API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/LocalDateTime.html)
- [`DateTimeFormatter` — API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/format/DateTimeFormatter.html)
- [`Duration` — API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/Duration.html)
- [`ZoneRules` — API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/zone/ZoneRules.html)
