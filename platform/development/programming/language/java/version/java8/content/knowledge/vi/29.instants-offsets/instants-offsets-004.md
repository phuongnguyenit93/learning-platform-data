# OffsetDateTime và OffsetTime trong Java: thời điểm, UTC offset và cách chuyển đổi

## 1. Mục tiêu bài học

Trong `java.time`, **`OffsetDateTime`** biểu diễn *ngày + giờ địa phương + UTC offset* (ví dụ `2026-11-06T09:15:30+07:00`), còn **`OffsetTime`** chỉ biểu diễn *giờ trong ngày + UTC offset* (ví dụ `09:15:30+07:00`). Điểm khác biệt “có ngày hay không” quyết định liệu một giá trị có đủ thông tin để xác định **một thời điểm tuyệt đối** trên timeline.

Hai lớp này được giới thiệu từ **Java 8** và vẫn là API hiện hành. Chúng đều immutable, thread-safe và hỗ trợ phần lẻ giây tới nanosecond. Đây là các *value-based class*; so sánh bằng `equals`/các phương thức so sánh của API, không dùng identity (`==`) để kiểm tra hai giá trị có tương đương hay không, không dùng instance làm đối tượng khóa `synchronized`.

Sau bài, bạn có thể:

- Phân biệt `OffsetDateTime`, `OffsetTime`, `Instant`, `LocalDateTime` và `ZonedDateTime`.
- Tạo, parse và format ngày giờ có offset từ dữ liệu ISO-8601.
- Đổi UTC offset theo hai chủ đích khác nhau: **giữ nguyên instant** hoặc **giữ nguyên giờ địa phương**.
- Hiểu `equals`, `isEqual`, `compareTo` và cách sắp xếp trên timeline.
- Chuyển `OffsetDateTime` sang `Instant`, còn `OffsetTime` phải kết hợp thêm ngày.
- Nhận biết khi nào cần `ZoneId` cùng quy tắc DST thay vì offset cố định.
- Dùng `Clock` để test ổn định; tránh sai lệch do máy chạy hoặc múi giờ mặc định.
- Chọn kiểu dữ liệu phù hợp cho API, cơ sở dữ liệu, lịch làm việc, timestamp và giao tiếp liên hệ thống.

Bài dùng các chương trình độc lập theo **Java 17+** và ghi rõ API nào mới hơn Java 8. Kiến thức nền không dựa vào lớp ngày giờ cũ/lỗi thời.

## 2. UTC offset là gì? Khác múi giờ vùng như thế nào?

**UTC offset** là khoảng dịch của đồng hồ địa phương so với UTC, thường viết `Z` (bằng `+00:00`), `+07:00`, `-05:00` hoặc `+05:30`.

Ví dụ:

```text
Giờ địa phương: 09:15:30+07:00
Giờ UTC:       02:15:30Z

Công thức khái niệm:
UTC = LocalDateTime - UTC offset
```

`ZoneOffset` là một kiểu `ZoneId` đặc biệt, thể hiện **một độ lệch cố định**. Nó không chứa lịch sử hoặc quy tắc thay đổi offset theo ngày. Trong Java, offset được giới hạn trong phạm vi hợp lệ khoảng từ `-18:00` đến `+18:00`. Không dùng một offset cố định để thay thế vùng địa lý có DST hay thay đổi chính sách lịch sử.

Trong khi đó, **`ZoneId.of("Europe/Paris")`** mô tả một vùng thời gian có quy tắc. Tại một instant cụ thể, quy tắc của vùng xác định offset có hiệu lực; ví dụ trong các năm lịch sử đã xác định, Paris có thể dùng `+01:00` mùa đông và `+02:00` mùa hè. Một `OffsetDateTime` lưu lại **offset được chọn tại thời điểm đó**, nhưng không giữ toàn bộ tên vùng hay quy tắc tương lai.

**Tóm tắt:** offset trả lời “cách UTC bao nhiêu giây/phút?”, còn region zone trả lời “áp dụng quy tắc thời gian nào theo ngày lịch?”. Hai câu hỏi này liên quan nhưng không đồng nhất.

## 3. Bảng so sánh các kiểu thời gian cần biết

| Kiểu | Ngày | Giờ | UTC offset | Zone rules | Xác định một instant? |
| --- | --- | --- | --- | --- | --- |
| `LocalTime` | Không | Có | Không | Không | Không |
| `OffsetTime` | Không | Có | Có | Không | **Chưa**, vì thiếu ngày |
| `LocalDateTime` | Có | Có | Không | Không | **Chưa**, vì thiếu offset/zone |
| `OffsetDateTime` | Có | Có | Có | Không | **Có** |
| `ZonedDateTime` | Có | Có | Có tại thời điểm đó | Có `ZoneId`/quy tắc | **Có** |
| `Instant` | Điểm trên timeline UTC | Có nghĩa thời điểm tuyệt đối | Quy chiếu UTC | Không | **Có** |

`OffsetDateTime` thích hợp khi một giao thức gửi thời điểm có offset rõ ràng, chẳng hạn `2026-11-06T09:15:30+07:00`. Dữ liệu này đủ để tính ra instant UTC. `OffsetTime` thích hợp khi một giao thức chỉ trao đổi giờ trong ngày cùng offset, nhưng chưa có ngày nào được chọn.

**Không suy luận:** một giá trị `09:00+07:00` tự chỉ ra cùng một sự kiện vào mọi ngày. Ngày là thông tin bắt buộc nếu muốn lưu một bản ghi xảy ra tại thời điểm cụ thể.

## 4. Tạo `OffsetDateTime` bằng `parse`, `of` và `ofInstant`

`OffsetDateTime` có các factory phổ biến:

- `OffsetDateTime.parse(CharSequence)` — đọc chuỗi ISO-8601 có ngày, giờ và offset.
- `OffsetDateTime.of(LocalDate, LocalTime, ZoneOffset)` hoặc `of(LocalDateTime, ZoneOffset)` — kết hợp các giá trị đã biết.
- `OffsetDateTime.ofInstant(Instant, ZoneId)` — dùng một instant tuyệt đối và zone để tạo biểu diễn địa phương phù hợp.
- `OffsetDateTime.now(Clock)` — lấy thời điểm từ đồng hồ được tiêm vào, hữu ích cho test.

Lưu `OffsetDateTimeBasicsDemo.java`:

```java
import java.time.Instant;
import java.time.LocalDateTime;
import java.time.OffsetDateTime;
import java.time.OffsetTime;
import java.time.ZoneOffset;

public class OffsetDateTimeBasicsDemo {
    public static void main(String[] args) {
        OffsetDateTime value = OffsetDateTime.parse(
                "2026-11-06T09:15:30.123456789+07:00");

        LocalDateTime local = value.toLocalDateTime();
        Instant utc = value.toInstant();
        OffsetTime timeOnly = value.toOffsetTime();

        System.out.println("value = " + value);
        System.out.println("local = " + local);
        System.out.println("offset = " + value.getOffset());
        System.out.println("utc = " + utc);
        System.out.println("nano = " + value.getNano());
        System.out.println("timeOnly = " + timeOnly);

        OffsetDateTime built = OffsetDateTime.of(
                local, ZoneOffset.ofHours(7));
        System.out.println("reconstructed = " +
                built.equals(value));
    }
}
```

Biên dịch và chạy:

```bash
javac OffsetDateTimeBasicsDemo.java
java OffsetDateTimeBasicsDemo
```

Đầu ra:

```text
value = 2026-11-06T09:15:30.123456789+07:00
local = 2026-11-06T09:15:30.123456789
offset = +07:00
utc = 2026-11-06T02:15:30.123456789Z
nano = 123456789
timeOnly = 09:15:30.123456789+07:00
reconstructed = true
```

`OffsetDateTime` lưu LocalDateTime và offset. `toInstant()` thực hiện phép quy đổi sang UTC, không xóa phần nanosecond. `toOffsetTime()` **bỏ ngày**, nên không dùng kết quả này thay cho timestamp có đầy đủ ngày giờ.

### 4.1. `ofInstant(instant, zone)` và nguồn thời gian UTC

Nếu đã có `Instant`, nên giữ nó là **nguồn sự thật về thời điểm**. Khi cần hiển thị theo một vùng:

```java
Instant time = Instant.parse("2026-01-01T00:00:00Z");
OffsetDateTime offsetDateTime =
        OffsetDateTime.ofInstant(
                time, ZoneOffset.ofHours(7));
```

*Snippet này dùng `java.time` và phải đặt trong phương thức hoặc chương trình có import phù hợp.* Kết quả là `2026-01-01T07:00+07:00`. Khi đưa `ZoneId` vùng vào `ofInstant`, quy tắc của vùng quyết định offset đúng tại instant đó.

## 5. `withOffsetSameInstant` và `withOffsetSameLocal` khác nhau ở đâu?

Đây là hai phương thức dễ gây bug nhất:

- `withOffsetSameInstant(newOffset)`: **giữ nguyên thời điểm UTC**, thay đổi giờ địa phương cho phù hợp offset mới.
- `withOffsetSameLocal(newOffset)`: **giữ nguyên các trường ngày/giờ địa phương**, thay đổi offset nên **thường làm thay đổi instant**.

Lưu `OffsetDateTimeConversionDemo.java`:

```java
import java.time.OffsetDateTime;
import java.time.ZoneOffset;

public class OffsetDateTimeConversionDemo {
    public static void main(String[] args) {
        OffsetDateTime original = OffsetDateTime.parse(
                "2026-01-15T10:00+07:00");

        OffsetDateTime sameInstant =
                original.withOffsetSameInstant(ZoneOffset.UTC);
        OffsetDateTime sameLocal =
                original.withOffsetSameLocal(ZoneOffset.UTC);

        System.out.println("original = " + original);
        System.out.println("sameInstant = " + sameInstant);
        System.out.println("sameLocal = " + sameLocal);
        System.out.println("instantPreserved = " +
                original.toInstant().equals(
                        sameInstant.toInstant()));
        System.out.println("localPreserved = " +
                original.toLocalDateTime().equals(
                        sameLocal.toLocalDateTime()));
        System.out.println("localChangesInstant = " +
                !original.toInstant().equals(
                        sameLocal.toInstant()));
    }
}
```

```bash
javac OffsetDateTimeConversionDemo.java
java OffsetDateTimeConversionDemo
```

```text
original = 2026-01-15T10:00+07:00
sameInstant = 2026-01-15T03:00Z
sameLocal = 2026-01-15T10:00Z
instantPreserved = true
localPreserved = true
localChangesInstant = true
```

Đổi offset từ +07:00 sang UTC:

- Muốn **hiển thị cùng một cuộc họp** theo UTC → `withOffsetSameInstant(UTC)` cho `03:00Z`.
- Muốn giữ chữ “10:00” nhưng **gán lại** offset UTC → `withOffsetSameLocal(UTC)` cho `10:00Z`, tức một thời điểm **trễ hơn 7 tiếng**.

`OffsetDateTime` là immutable: cả hai phương thức trả đối tượng mới. Thay đổi offset **không** sửa instant ban đầu. `withOffsetSameInstant` có thể ném `DateTimeException` ở các giá trị nằm sát biên phạm vi ngày giờ nếu kết quả vượt phạm vi hỗ trợ.

**Quy tắc:** Khi chuyển timestamp giữa các hệ thống mà vẫn chỉ cùng sự kiện, dùng `withOffsetSameInstant` hoặc `toInstant`. Chỉ dùng `withOffsetSameLocal` khi nghiệp vụ thật sự muốn *diễn giải lại cùng giờ địa phương dưới offset mới*, không phải “chuyển múi giờ”.

## 6. `equals`, `isEqual`, `compareTo` và `timeLineOrder`

Hai giá trị `OffsetDateTime` có thể **khác ngày/giờ hiển thị và offset** nhưng chỉ đến **cùng một instant UTC**:

```text
2026-06-01T09:00+07:00
2026-06-01T02:00Z

Cả hai = 2026-06-01T02:00:00Z
```

Nhưng Java phân biệt:

- `equals(other)`: so sánh **ngày giờ địa phương + offset**.
- `isEqual(other)`: so sánh **instant trên timeline**.
- `isBefore`/`isAfter`: so sánh **instant**, không cần local time giống nhau.
- `compareTo`: so sánh **instant trước**, nếu trùng instant thì so thêm local date-time để nhất quán với `equals`.
- `OffsetDateTime.timeLineOrder()`: Comparator chỉ xét **instant**, vì thế hai biểu diễn khác offset của cùng một instant sẽ có kết quả so sánh bằng 0.

Lưu `OffsetDateTimeComparisonDemo.java`:

```java
import java.time.OffsetDateTime;
import java.util.Set;
import java.util.TreeSet;

public class OffsetDateTimeComparisonDemo {
    public static void main(String[] args) {
        OffsetDateTime hcm = OffsetDateTime.parse(
                "2026-06-01T09:00+07:00");
        OffsetDateTime utc = OffsetDateTime.parse(
                "2026-06-01T02:00Z");

        System.out.println("equals = " + hcm.equals(utc));
        System.out.println("sameInstant = " + hcm.isEqual(utc));
        System.out.println("isBefore = " + hcm.isBefore(utc));
        System.out.println("compareToZero = " +
                (hcm.compareTo(utc) == 0));
        System.out.println("timelineZero = " +
                (OffsetDateTime.timeLineOrder()
                        .compare(hcm, utc) == 0));

        Set<OffsetDateTime> byValue = new TreeSet<>();
        byValue.add(hcm);
        byValue.add(utc);

        Set<OffsetDateTime> byInstant = new TreeSet<>(
                OffsetDateTime.timeLineOrder());
        byInstant.add(hcm);
        byInstant.add(utc);

        System.out.println("valueSetSize = " + byValue.size());
        System.out.println("instantSetSize = " +
                byInstant.size());
    }
}
```

```bash
javac OffsetDateTimeComparisonDemo.java
java OffsetDateTimeComparisonDemo
```

```text
equals = false
sameInstant = true
isBefore = false
compareToZero = false
timelineZero = true
valueSetSize = 2
instantSetSize = 1
```

Điểm cần nhớ khi làm collection:

- `HashSet<OffsetDateTime>` dùng `equals`/`hashCode` nên giữ hai biểu diễn khác nhau của cùng instant.
- `TreeSet` mặc định dùng `compareTo`, cũng có thể giữ chúng vì tie-break theo local.
- `TreeSet` với `timeLineOrder()` coi hai giá trị có cùng instant là **trùng key so sánh** và chỉ giữ một phần tử. Đây là lựa chọn có chủ đích khi nghiệp vụ cần loại trùng trên timeline.

Không khẳng định `compareTo == 0` tương đương `isEqual`. Nếu muốn xét đúng “hai sự kiện xảy ra cùng lúc?”, dùng `isEqual` hoặc so sánh hai `Instant`.

## 7. `OffsetTime`: giờ trong ngày cộng offset, nhưng **không có ngày**

`OffsetTime` lưu `LocalTime` và `ZoneOffset`, ví dụ `09:15:30.123456789+07:00`. Nó hữu ích cho trường giờ trong một giao thức hoặc lịch sử chỉ cần giờ + offset, nhưng **không có ngày**, vì vậy **không thể trực tiếp chuyển thành `Instant` tuyệt đối**.

Các factory/phương thức quen thuộc:

- `OffsetTime.parse("09:15+07:00")`.
- `OffsetTime.of(LocalTime.of(9, 15), ZoneOffset.ofHours(7))`.
- `getHour()`, `getMinute()`, `getSecond()`, `getNano()`, `getOffset()`.
- `toLocalTime()` — bỏ offset, chỉ còn local clock time.
- `withOffsetSameInstant(...)` và `withOffsetSameLocal(...)` — ý nghĩa tương tự, nhưng có caveat khi qua nửa đêm.
- `atDate(LocalDate)` — kết hợp thành `OffsetDateTime`.
- `toEpochSecond(LocalDate)` — chuyển dùng ngày do bạn cung cấp (**có từ Java 9**).

Lưu `OffsetTimeBasicsDemo.java`:

```java
import java.time.LocalDate;
import java.time.OffsetTime;
import java.time.ZoneOffset;

public class OffsetTimeBasicsDemo {
    public static void main(String[] args) {
        OffsetTime original = OffsetTime.parse(
                "09:15:30.123456789+07:00");

        OffsetTime utcTime =
                original.withOffsetSameInstant(ZoneOffset.UTC);
        OffsetTime relabeled =
                original.withOffsetSameLocal(ZoneOffset.UTC);

        System.out.println("time = " + original);
        System.out.println("local = " + original.toLocalTime());
        System.out.println("offset = " + original.getOffset());
        System.out.println("nano = " + original.getNano());
        System.out.println("utcClock = " + utcTime);
        System.out.println("relabeled = " + relabeled);

        System.out.println("dated = " +
                original.atDate(LocalDate.of(2026, 11, 6)));
        System.out.println("instant = " +
                original.atDate(LocalDate.of(2026, 11, 6))
                        .toInstant());
    }
}
```

```bash
javac OffsetTimeBasicsDemo.java
java OffsetTimeBasicsDemo
```

```text
time = 09:15:30.123456789+07:00
local = 09:15:30.123456789
offset = +07:00
nano = 123456789
utcClock = 02:15:30.123456789Z
relabeled = 09:15:30.123456789Z
dated = 2026-11-06T09:15:30.123456789+07:00
instant = 2026-11-06T02:15:30.123456789Z
```

Ở đây khi có ngày `2026-11-06`, `OffsetTime.atDate(...)` tạo `OffsetDateTime` đủ dữ liệu để gọi `toInstant()`. Nếu chỉ có `09:15+07:00`, không có cách hợp lệ để “đoán” duy nhất một instant — cùng giờ ấy có thể xảy ra ở vô số ngày khác nhau.

### 7.1. Chuyển `OffsetDateTime` thành `OffsetTime` làm mất thông tin nào?

`someOffsetDateTime.toOffsetTime()` giữ **giờ địa phương + offset** nhưng **bỏ ngày**. Đây là chuyển đổi mất thông tin. Muốn dựng lại instant ban đầu phải lưu hoặc biết đúng ngày địa phương tương ứng. Nếu không, `toOffsetTime()` không thích hợp để lưu sự kiện đã xảy ra vào bảng log.

## 8. Bẫy nửa đêm: `OffsetTime.withOffsetSameInstant` không giữ được ngày bị bỏ

`OffsetTime.withOffsetSameInstant` điều chỉnh giờ theo hiệu offset và nói đến cùng instant trên **một ngày ngầm hiểu**. Tuy nhiên `OffsetTime` không chứa ngày, nên khi đổi offset làm đồng hồ chạy qua 00:00, kết quả chỉ giữ **giờ đã cuộn trong một ngày**, không giữ thông tin “lùi/sang ngày kế tiếp”.

Ví dụ:

```text
Ngày địa phương giả định: 2026-05-02
00:30+02:00  => UTC 2026-05-01T22:30Z (NGÀY TRƯỚC)
Đổi giờ về offset UTC (chỉ riêng OffsetTime):
22:30Z       => không còn ghi rõ UTC là 2026-05-01
```

Nếu gắn **cùng ngày địa phương ban đầu** cho `22:30Z`, bạn đã tạo một instant **muộn hơn đúng 24 giờ**. Vì vậy nếu muốn quy đổi đúng thời điểm khi có khả năng qua nửa đêm, hãy **gắn ngày trước rồi chuyển `OffsetDateTime`**.

Lưu `OffsetTimeMidnightDemo.java`:

```java
import java.time.LocalDate;
import java.time.OffsetDateTime;
import java.time.OffsetTime;
import java.time.ZoneOffset;

public class OffsetTimeMidnightDemo {
    public static void main(String[] args) {
        LocalDate localDate = LocalDate.of(2026, 5, 2);
        OffsetTime original = OffsetTime.parse("00:30+02:00");

        OffsetTime utcTimeOnly =
                original.withOffsetSameInstant(ZoneOffset.UTC);

        OffsetDateTime dated = original.atDate(localDate);
        OffsetDateTime correctUTC =
                dated.withOffsetSameInstant(ZoneOffset.UTC);
        OffsetDateTime wrongIfSameDate =
                utcTimeOnly.atDate(localDate);

        System.out.println("original = " + original);
        System.out.println("utcTimeOnly = " + utcTimeOnly);
        System.out.println("dated = " + dated);
        System.out.println("correctUTC = " + correctUTC);
        System.out.println("wrongIfSameDate = " +
                wrongIfSameDate);
        System.out.println("sameInstant = " +
                correctUTC.isEqual(wrongIfSameDate));
    }
}
```

```bash
javac OffsetTimeMidnightDemo.java
java OffsetTimeMidnightDemo
```

```text
original = 00:30+02:00
utcTimeOnly = 22:30Z
dated = 2026-05-02T00:30+02:00
correctUTC = 2026-05-01T22:30Z
wrongIfSameDate = 2026-05-02T22:30Z
sameInstant = false
```

Đây là khác biệt quan trọng nhất khi thiết kế dữ liệu: giờ trong ngày + offset **không mang ngày**, nên không thể tự bảo toàn timestamp tuyệt đối khi có biến đổi qua nửa đêm. Với hệ thống lập lịch, ngày thuộc **thực thể lịch** riêng; với event, hãy dùng `Instant` hoặc `OffsetDateTime` ngay từ đầu.

## 9. So sánh `OffsetTime`: cùng một ngày ngầm hiểu, không phải sự kiện có ngày

`OffsetTime` cung cấp `equals`, `compareTo`, `isEqual`, `isBefore` và `isAfter`:

- `equals` so sánh local time **và** offset.
- `isEqual`/`isBefore`/`isAfter` quy chiếu hai giá trị lên **cùng một ngày giả định** rồi so sánh thời điểm UTC tương đương.
- `compareTo` trước hết so thứ tự UTC tương đương, rồi so local time nếu UTC bằng nhau để nhất quán với `equals`.

Điều kiện “cùng ngày giả định” có nghĩa là `OffsetTime` thích hợp cho **so sánh biểu diễn thời gian trong ngày**, không phải so sánh hai event không có ngày.

Lưu `OffsetTimeComparisonDemo.java`:

```java
import java.time.OffsetTime;

public class OffsetTimeComparisonDemo {
    public static void main(String[] args) {
        OffsetTime a = OffsetTime.parse("10:00+02:00");
        OffsetTime b = OffsetTime.parse("08:00Z");
        OffsetTime c = OffsetTime.parse("09:00Z");

        System.out.println("equals = " + a.equals(b));
        System.out.println("isEqual = " + a.isEqual(b));
        System.out.println("compareToZero = " +
                (a.compareTo(b) == 0));
        System.out.println("aBeforeC = " + a.isBefore(c));
        System.out.println("aLocal = " + a.toLocalTime());
        System.out.println("bLocal = " + b.toLocalTime());
    }
}
```

```bash
javac OffsetTimeComparisonDemo.java
java OffsetTimeComparisonDemo
```

```text
equals = false
isEqual = true
compareToZero = false
aBeforeC = true
aLocal = 10:00
bLocal = 08:00
```

`10:00+02:00` và `08:00Z` tương ứng **cùng giờ UTC** nếu đặt vào cùng một ngày. Nhưng hai biểu diễn không `equals`. `compareTo` còn tie-break bằng local time, nên hai giá trị cùng UTC vẫn có thể khác 0.

**Không được đánh đồng** `OffsetTime.isEqual` với việc hai cuộc hẹn ở **hai ngày khác nhau** là cùng instant. Đối với event, phải dùng `OffsetTime.atDate(...)` với ngày đúng của từng event rồi so `OffsetDateTime`/`Instant`.

## 10. Offset cố định không thay thế `ZoneId` và quy tắc DST

Một offset `+02:00` chỉ cho biết phép dịch UTC hiện tại; nó **không biết** Paris có mùa hè/mùa đông, ngày bắt đầu DST, hoặc chính sách lịch sử/hiện hành. Nếu nghiệp vụ là “họp lúc 09:00 theo giờ Paris vào mọi ngày trong năm”, phải lưu **`LocalTime` + `ZoneId`** cùng quy tắc chọn ngày, hoặc lưu lịch hẹn theo `ZonedDateTime`/schedule model phù hợp.

Ví dụ đặt cùng một instant vào Paris và đổi một OffsetDateTime thành ZonedDateTime:

- `OffsetDateTime.atZoneSameInstant(zone)`: giữ nguyên instant, chọn ngày giờ tại zone đích theo luật của vùng.
- `OffsetDateTime.atZoneSimilarLocal(zone)`: cố giữ local date-time, đồng thời áp dụng quy tắc gap/overlap của zone; **thường thay đổi instant**.
- `OffsetDateTime.toZonedDateTime()`: dùng **chính offset** như zone, không tự khôi phục tên vùng lịch sử.
- `OffsetDateTime.ofInstant(instant, zone)`: dùng instant để tìm offset theo quy tắc của vùng.

Lưu `OffsetZoneRulesDemo.java`:

```java
import java.time.OffsetDateTime;
import java.time.ZoneId;
import java.time.ZonedDateTime;

public class OffsetZoneRulesDemo {
    public static void main(String[] args) {
        OffsetDateTime value =
                OffsetDateTime.parse("2024-07-01T12:00+07:00");
        ZoneId paris = ZoneId.of("Europe/Paris");

        ZonedDateTime sameInstant =
                value.atZoneSameInstant(paris);
        ZonedDateTime similarLocal =
                value.atZoneSimilarLocal(paris);

        System.out.println("original = " + value);
        System.out.println("sameInstant = " + sameInstant);
        System.out.println("similarLocal = " + similarLocal);
        System.out.println("instantPreserved = " +
                value.toInstant().equals(
                        sameInstant.toInstant()));
        System.out.println("similarChangesInstant = " +
                !value.toInstant().equals(
                        similarLocal.toInstant()));
        System.out.println("offsetAsZone = " +
                value.toZonedDateTime().getZone());
    }
}
```

```bash
javac OffsetZoneRulesDemo.java
java OffsetZoneRulesDemo
```

```text
original = 2024-07-01T12:00+07:00
sameInstant = 2024-07-01T07:00+02:00[Europe/Paris]
similarLocal = 2024-07-01T12:00+02:00[Europe/Paris]
instantPreserved = true
similarChangesInstant = true
offsetAsZone = +07:00
```

Với cùng instant tháng 7/2024, Paris là +02:00; phiên bản giữ instant hiển thị `07:00`, còn phiên bản cố giữ local `12:00` biểu diễn sự kiện **khác**. `toZonedDateTime().getZone()` chỉ trả `+07:00`, không thể suy luận rằng nó từng thuộc vùng `Asia/Ho_Chi_Minh` hoặc một zone cụ thể nào khác.

**Lưu ý DST:** Khi giờ địa phương nằm trong khoảng *gap* (không tồn tại) hoặc *overlap* (xảy ra hai lần) của một region zone, việc dựng `ZonedDateTime` cần quy tắc resolve. `atZoneSimilarLocal` có cơ chế xử lý theo API, nhưng bạn phải xác nhận đó có đúng chính sách nghiệp vụ hay không. Nếu một instant đã xác định, `atZoneSameInstant` tránh sự mơ hồ khi hiển thị sang zone khác.

## 11. Lịch làm việc lặp lại: vì sao `OffsetTime` không đủ?

Giả sử business rule là “hệ thống mở cửa **09:00 theo giờ Paris** mỗi ngày”. Nếu lưu `OffsetTime.parse("09:00+01:00")` và dùng nó vào mùa hè, giờ 09:00 với offset +01:00 **khác** giờ 09:00 thực theo zone `Europe/Paris` khi vùng dùng +02:00.

Thay vào đó, lưu:

- `LocalTime.of(9, 0)` — giờ tường/civil time quy định.
- `ZoneId.of("Europe/Paris")` — vùng có quy tắc.
- `LocalDate` của ngày cần giải lịch.

Rồi dựng `ZonedDateTime` cho **ngày cụ thể**. Lưu `RecurringScheduleDemo.java`:

```java
import java.time.LocalDate;
import java.time.LocalTime;
import java.time.OffsetTime;
import java.time.ZoneId;
import java.time.ZonedDateTime;

public class RecurringScheduleDemo {
    public static void main(String[] args) {
        LocalTime opening = LocalTime.of(9, 0);
        ZoneId region = ZoneId.of("Europe/Paris");

        ZonedDateTime winter = LocalDate
                .of(2024, 1, 15).atTime(opening).atZone(region);
        ZonedDateTime summer = LocalDate
                .of(2024, 7, 15).atTime(opening).atZone(region);

        OffsetTime fixed = OffsetTime.parse("09:00+01:00");

        System.out.println("winter = " +
                winter.toOffsetDateTime());
        System.out.println("summer = " +
                summer.toOffsetDateTime());
        System.out.println("fixed = " + fixed);
        System.out.println("sameSummerOffset = " +
                fixed.getOffset().equals(summer.getOffset()));
    }
}
```

```bash
javac RecurringScheduleDemo.java
java RecurringScheduleDemo
```

```text
winter = 2024-01-15T09:00+01:00
summer = 2024-07-15T09:00+02:00
fixed = 09:00+01:00
sameSummerOffset = false
```

Tài liệu hóa chính sách khi DST làm một local time **không tồn tại** hoặc **lặp lại**. `LocalTime + ZoneId` là dữ liệu nền phù hợp hơn `OffsetTime`, nhưng vẫn cần xử lý ngày và quy tắc gap/overlap khi chuyển sang instant.

`OffsetTime` có giá trị khi offset thực sự là **một phần của hợp đồng dữ liệu cố định** (ví dụ một giao thức quy định “09:00 tại offset +07:00” và không muốn dựa vào region rules), chứ không phải mọi trường hợp làm việc theo múi giờ của một thành phố.

## 12. Parse và format ISO-8601 cho `OffsetDateTime`/`OffsetTime`

Java hỗ trợ sẵn định dạng ISO-8601:

- `OffsetDateTime.parse("2026-08-10T14:05:06.123456789+05:30")`.
- `OffsetTime.parse("14:05:06.123456789+05:30")`.
- `DateTimeFormatter.ISO_OFFSET_DATE_TIME` và `ISO_OFFSET_TIME`.
- `DateTimeFormatter.ofPattern(...)` khi giao thức cần cách trình bày cụ thể.
- `DateTimeParseException` khi chuỗi không hợp lệ hoặc thiếu các trường bắt buộc.

Lưu `OffsetParsingFormattingDemo.java`:

```java
import java.time.OffsetDateTime;
import java.time.OffsetTime;
import java.time.format.DateTimeFormatter;
import java.time.format.DateTimeParseException;
import java.util.Locale;

public class OffsetParsingFormattingDemo {
    public static void main(String[] args) {
        OffsetDateTime dateTime = OffsetDateTime.parse(
                "2026-08-10T14:05:06.123456789+05:30");
        OffsetTime time = OffsetTime.parse(
                "14:05:06.123456789+05:30");

        DateTimeFormatter dateFormatter = DateTimeFormatter
                .ofPattern("uuuu-MM-dd HH:mm:ss XXX",
                        Locale.ROOT);
        DateTimeFormatter timeFormatter = DateTimeFormatter
                .ofPattern("HH:mm XXX", Locale.ROOT);

        System.out.println("isoDateTime = " + dateTime);
        System.out.println("isoTime = " + time);
        System.out.println("customDate = " +
                dateTime.format(dateFormatter));
        System.out.println("customTime = " +
                time.format(timeFormatter));

        try {
            OffsetDateTime.parse("2026-02-30T10:00+07:00");
            System.out.println("unexpected");
        } catch (DateTimeParseException e) {
            System.out.println("invalid date rejected");
        }
    }
}
```

```bash
javac OffsetParsingFormattingDemo.java
java OffsetParsingFormattingDemo
```

```text
isoDateTime = 2026-08-10T14:05:06.123456789+05:30
isoTime = 14:05:06.123456789+05:30
customDate = 2026-08-10 14:05:06 +05:30
customTime = 14:05 +05:30
invalid date rejected
```

Mẫu format `XXX` biểu diễn offset dạng ISO như `+05:30` hoặc `Z`. `OffsetDateTime.toString()`/`OffsetTime.toString()` có thể rút ngắn phần giây khi bằng 0; không dựa vào **độ dài cố định của chuỗi `toString()`** để parse một giao thức tùy ý. Nếu cần chính xác chín chữ số phần giây hoặc cách hiển thị khác, xây formatter rõ ràng bằng `DateTimeFormatterBuilder` và kiểm thử round-trip.

### 12.1. Parse thiếu offset phải làm sao?

`OffsetDateTime.parse("2026-08-10T14:05")` không hợp lệ vì thiếu offset. `LocalDateTime.parse(...)` có thể đọc chuỗi ngày giờ như vậy, nhưng không tạo được instant cho đến khi **người dùng/contract** chỉ ra offset hoặc zone áp dụng.

Tương tự, `OffsetTime.parse("14:05")` thiếu offset; có thể parse bằng `LocalTime.parse("14:05")`, nhưng muốn tạo `OffsetTime` phải bổ sung một `ZoneOffset` **được chọn có căn cứ**. Không tự mặc định offset của máy chạy hoặc `UTC` nếu giao thức chưa định nghĩa.

### 12.2. UTC ký hiệu `Z` và `+00:00`

`Z` là UTC offset 0. Khi parse chuỗi ISO có `+00:00`, Java thường chuẩn hóa biểu diễn `ZoneOffset.UTC` thành `Z` khi in. Cách viết có thể khác dù cùng ý nghĩa offset; dùng object thời gian hoặc formatter theo hợp đồng thay vì so sánh chuỗi raw một cách thiếu chuẩn hóa.

## 13. `now()` và cách viết unit test không phụ thuộc timezone máy

Hai lớp đều có `now()`, `now(ZoneId)` và `now(Clock)`. Với các phương thức không nhận Clock, dữ liệu thực phụ thuộc giờ hệ thống; với `now()` còn có phụ thuộc default zone máy.

Để kiểm thử chính xác, dùng `Clock.fixed(...)` với `ZoneOffset` hoặc `ZoneId` rõ ràng:

Lưu `OffsetClockDemo.java`:

```java
import java.time.Clock;
import java.time.Instant;
import java.time.OffsetDateTime;
import java.time.OffsetTime;
import java.time.ZoneOffset;

public class OffsetClockDemo {
    public static void main(String[] args) {
        Instant fixed =
                Instant.parse("2026-01-01T00:00:00Z");
        Clock plusSeven =
                Clock.fixed(fixed, ZoneOffset.ofHours(7));
        Clock utc =
                Clock.fixed(fixed, ZoneOffset.UTC);

        OffsetDateTime dateTime =
                OffsetDateTime.now(plusSeven);
        OffsetTime time = OffsetTime.now(plusSeven);

        System.out.println("dateTime = " + dateTime);
        System.out.println("time = " + time);
        System.out.println("utc = " +
                OffsetDateTime.now(utc));
        System.out.println("sameInstant = " +
                fixed.equals(dateTime.toInstant()));
    }
}
```

```bash
javac OffsetClockDemo.java
java OffsetClockDemo
```

```text
dateTime = 2026-01-01T07:00+07:00
time = 07:00+07:00
utc = 2026-01-01T00:00Z
sameInstant = true
```

Với `Clock.fixed`, kết quả có thể kiểm thử mà không dùng `Thread.sleep` hoặc dựa vào “bây giờ” của OS. Trong production, việc chọn UTC hoặc zone vùng phải do chính sách của service quyết định. `OffsetDateTime.now()` vẫn là API hợp lệ, nhưng **tiêm Clock** giúp chức năng testable và loại bỏ phụ thuộc ẩn vào cấu hình máy.

## 14. Tính toán cộng/trừ trên `OffsetDateTime` và DST

`OffsetDateTime.plusDays(...)`, `plusHours(...)`, `minusMinutes(...)`, `truncatedTo(...)` tạo giá trị mới; **offset vẫn cố định** trừ khi bạn gọi phương thức đổi offset. Vì vậy `plusHours(24)` và `plusDays(1)` có ý nghĩa trên offset cố định, **không tự hỏi lại zone có DST hay không**.

Với `ZonedDateTime`, các quy tắc region zone có thể thay đổi offset khi cộng theo timeline và lịch. Chẳng hạn ngày DST kết thúc ở Paris năm 2024: sau 2 giờ thực từ mốc `01:30+02:00`, local time thành `02:30+01:00`, chứ không phải `03:30+02:00` như phép cộng ở offset cố định.

Lưu `OffsetArithmeticDstDemo.java`:

```java
import java.time.Duration;
import java.time.OffsetDateTime;
import java.time.ZoneId;
import java.time.ZonedDateTime;

public class OffsetArithmeticDstDemo {
    public static void main(String[] args) {
        OffsetDateTime offsetDateTime =
                OffsetDateTime.parse(
                        "2024-10-27T01:30+02:00");
        ZonedDateTime zoned =
                offsetDateTime.atZoneSameInstant(
                        ZoneId.of("Europe/Paris"));

        OffsetDateTime offsetPlus2 =
                offsetDateTime.plusHours(2);
        ZonedDateTime zonePlus2 = zoned.plusHours(2);

        System.out.println("offsetPlus2 = " + offsetPlus2);
        System.out.println("zonePlus2 = " + zonePlus2);
        System.out.println("sameInstant = " +
                offsetPlus2.toInstant().equals(
                        zonePlus2.toInstant()));
        System.out.println("elapsedHours = " +
                Duration.between(
                        offsetDateTime.toInstant(),
                        zonePlus2.toInstant()).toHours());
    }
}
```

```bash
javac OffsetArithmeticDstDemo.java
java OffsetArithmeticDstDemo
```

```text
offsetPlus2 = 2024-10-27T03:30+02:00
zonePlus2 = 2024-10-27T02:30+01:00[Europe/Paris]
sameInstant = true
elapsedHours = 2
```

Dù local hour và offset sau cộng khác nhau, hai kết quả là cùng instant sau 2 giờ thực. Với lịch “mỗi ngày lúc 09:00 theo giờ địa phương”, phép `plusDays(1)` trên `ZonedDateTime` theo quy tắc zone có ý nghĩa khác với cộng `Duration.ofHours(24)` trong những ngày chuyển DST. Cần phân biệt “sau một ngày lịch” và “sau đúng 24 giờ”.

**Không dùng `OffsetTime.plusHours(...)` như một công cụ tạo lịch nhiều ngày:** `OffsetTime` chỉ giữ giờ và offset, nên phép cộng qua nửa đêm **không mang ngày mới**; kết hợp với ngày có sẵn sau đó có thể cho một instant sai lệch 24 giờ.

## 15. Kinh nghiệm chọn kiểu dữ liệu cho API, database và nghiệp vụ

| Yêu cầu | Kiểu đề xuất | Lý do |
| --- | --- | --- |
| Ghi thời điểm event xảy ra | `Instant` hoặc `OffsetDateTime` theo contract | Có đủ thông tin timeline; `Instant` chuẩn hóa UTC |
| Client gửi ngày giờ với offset rõ ràng | `OffsetDateTime` | Parse/format giữ offset client gửi cùng thời điểm |
| Chỉ cần giờ trong ngày và offset cố định | `OffsetTime` | Không gắn ngày; không dùng làm event timestamp |
| Giờ mở cửa cố định theo vùng có DST | `LocalTime` + `ZoneId` + quy tắc ngày | Offset có thể thay đổi theo ngày |
| Lịch họp tại vùng địa lý cụ thể | `ZonedDateTime` | Bảo toàn zone rules/gap/overlap |
| Ngày giờ người nhập nhưng chưa biết zone | `LocalDateTime` | Chưa chỉ ra một instant; cần hoàn thiện quy tắc |
| Giao tiếp cross-service cần thống nhất | `Instant`/UTC epoch hoặc ISO offset với schema rõ ràng | Tránh phụ thuộc timezone máy |
| Test deadline/timestamp | `Clock.fixed` và `now(clock)` | Dữ liệu xác định |

### 15.1. Giữ lại offset của client hay chuẩn hóa UTC?

Hai nhu cầu có thể cùng tồn tại:

- **Tính toán/sắp xếp theo thời điểm:** lưu `Instant` hoặc giá trị timeline chuẩn.
- **Hiển thị lại đúng offset client đã gửi:** lưu thêm `ZoneOffset` hoặc chuỗi `OffsetDateTime`, tùy contract.

Nếu chỉ lưu `Instant`, bạn có thể hiển thị trong offset mới, nhưng **không thể biết offset gốc của client chỉ từ Instant**. Nếu chỉ lưu `OffsetDateTime` thì vẫn có thể lấy instant bằng `toInstant()`, nhưng **không thể suy ra tên `ZoneId` ban đầu**. Một offset có thể được nhiều vùng cùng sử dụng tại một thời điểm.

### 15.2. Database precision và nanosecond

`OffsetDateTime`/`OffsetTime` có khả năng giữ tới 9 chữ số phần giây. Nhưng database/driver/serializer/API có thể chỉ lưu milliseconds hoặc microseconds. Hãy định nghĩa rõ độ chi tiết, round/truncate policy, offset-vs-zone semantics và kiểm tra **round-trip** giữa Java và storage.

Không kết luận rằng tên cột `TIMESTAMP WITH TIME ZONE` ở mọi DB luôn giữ region zone hoặc offset ban đầu: semantics khác nhau giữa các database và driver. Đọc tài liệu engine cụ thể, không coi tên kiểu SQL là bảo đảm chung. Tương tự, ép timestamp thành `long epochMillis` sẽ làm mất phần dưới millisecond dù object Java gốc có nanosecond.

### 15.3. Tác động của zone rules khi lập lịch tương lai

Nếu lịch lặp lại đã định nghĩa theo **tên vùng**, giữ `ZoneId` để JDK có thể áp dụng quy tắc hợp lệ theo ngày. Một `OffsetTime` cố định có thể tạo lệch giờ khi vùng đổi offset. Nếu lịch sử thay đổi quy tắc, cũng phải xét **tzdb version** và chính sách cập nhật. Đó là lý do lưu offset và lưu tên region zone là hai yêu cầu khác nhau.

## 16. Xử lý lỗi và các trường hợp biên

| Tình huống | Điều có thể xảy ra | Xử lý |
| --- | --- | --- |
| Parse thiếu offset cho `OffsetDateTime` | `DateTimeParseException` | Đọc bằng `LocalDateTime` nếu dữ liệu thật sự chưa có offset; hỏi/áp dụng quy tắc zone rõ ràng |
| Parse ngày không tồn tại | `DateTimeParseException` | Validate ISO và báo lỗi đầu vào |
| Offset vượt phạm vi `ZoneOffset` | `DateTimeException` | Kiểm tra phần offset, không tự ép về UTC |
| `OffsetTime` được dùng thay cho timestamp | Không có ngày, không thể xác định một instant | Gắn đúng `LocalDate` hoặc lưu `OffsetDateTime` từ đầu |
| Đổi `OffsetTime` qua nửa đêm | Mất thông tin đổi ngày | Gắn ngày trước khi dùng `withOffsetSameInstant` trên `OffsetDateTime` |
| Gán offset bằng `withOffsetSameLocal` khi chỉ muốn đổi cách hiển thị | Thay đổi thời điểm | Dùng `withOffsetSameInstant` |
| So `equals` giữa hai OffsetDateTime cùng instant | Trả `false` nếu local/offset khác | Dùng `isEqual` hoặc `Instant.equals` |
| Đổi offset sang vùng DST bằng `ZoneOffset` | Không xét luật thay đổi theo ngày | Dùng `ZoneId`/`ZonedDateTime` |
| Cộng giờ trên `OffsetDateTime` qua ngày DST | Offset vẫn cố định | Nếu mục tiêu theo vùng, sử dụng `ZonedDateTime` |
| Dùng `now()` trong unit test | Test có thể flaky hoặc lệch timezone | Dùng `Clock.fixed(...)` và `now(clock)` |
| Sắp xếp theo chuỗi ISO chưa chuẩn hóa | Thứ tự từ vựng không nhất thiết theo instant | Parse rồi so timeline |
| Coi giờ `09:00+07:00` là giờ mở cửa theo vùng mãi mãi | Sai khi zone đổi luật/offset | Lưu LocalTime + ZoneId + policy |
| Dùng `==` để so hai object thời gian | Kiểm tra identity không phù hợp value-based class | Dùng `equals`/`isEqual` |
| Dùng cùng một `OffsetDateTime` làm khóa `synchronized` | Không đúng khuyến nghị cho value-based class | Dùng lock object riêng |

## 17. Bài tập kèm lời giải chạy được

**Bài 1 — Một instant, hai offset.** Cho `2026-12-10T09:30+07:00`. Đổi sang UTC mà vẫn giữ instant; in giá trị UTC và xác nhận `isEqual`. Sau đó đổi cùng giá trị bằng `withOffsetSameLocal` và chỉ ra sự khác biệt.

**Bài 2 — Gắn ngày cho `OffsetTime`.** Có `08:45+07:00` và ngày `2026-12-10`. Tạo `OffsetDateTime`, chuyển thành `Instant`. Nếu đổi `08:45+07:00` thành `01:45Z` trước khi gắn ngày thì trong ví dụ này có qua nửa đêm không? Nếu giờ ban đầu là `00:30+07:00` thì sao?

**Bài 3 — So sánh theo timeline.** Cho hai giá trị cùng instant nhưng offset khác nhau. Vì sao `equals` có thể là false mà `isEqual` là true? Trong `TreeSet` nên chọn `compareTo` hay `timeLineOrder` nếu chỉ muốn một bản ghi trên mỗi instant?

**Bài 4 — Lịch theo vùng.** Nếu lịch chạy 09:00 mỗi ngày ở Paris, giải thích tại sao `OffsetTime.parse("09:00+01:00")` không đủ cho cả năm và đề xuất mô hình dữ liệu thay thế.

**Bài 5 — Test bằng Clock.** Viết đoạn test với `Clock.fixed(Instant, ZoneOffset.ofHours(7))` để chứng minh rằng `OffsetDateTime.now(clock).toInstant()` vẫn là instant ban đầu.

Lời giải chạy được cho bài 1–3, lưu `OffsetPractice.java`:

```java
import java.time.LocalDate;
import java.time.OffsetDateTime;
import java.time.OffsetTime;
import java.time.ZoneOffset;
import java.util.Set;
import java.util.TreeSet;

public class OffsetPractice {
    public static void main(String[] args) {
        OffsetDateTime original = OffsetDateTime.parse(
                "2026-12-10T09:30+07:00");
        OffsetDateTime utc =
                original.withOffsetSameInstant(ZoneOffset.UTC);
        OffsetDateTime relabeled =
                original.withOffsetSameLocal(ZoneOffset.UTC);

        System.out.println("utc = " + utc);
        System.out.println("preserved = " +
                original.isEqual(utc));
        System.out.println("relabeledPreserved = " +
                original.isEqual(relabeled));

        OffsetTime time = OffsetTime.parse("08:45+07:00");
        OffsetDateTime dated =
                time.atDate(LocalDate.of(2026, 12, 10));

        System.out.println("dated = " + dated);
        System.out.println("instant = " + dated.toInstant());

        Set<OffsetDateTime> byInstant = new TreeSet<>(
                OffsetDateTime.timeLineOrder());
        byInstant.add(original);
        byInstant.add(utc);

        System.out.println("distinctInstants = " +
                byInstant.size());
    }
}
```

```bash
javac OffsetPractice.java
java OffsetPractice
```

```text
utc = 2026-12-10T02:30Z
preserved = true
relabeledPreserved = false
dated = 2026-12-10T08:45+07:00
instant = 2026-12-10T01:45:00Z
distinctInstants = 1
```

**Giải thích:** UTC của `09:30+07:00` là `02:30Z`; giữ local `09:30` rồi gán UTC lại thành một instant khác. `08:45+07:00` khi quy về UTC vẫn cùng ngày, nhưng `00:30+07:00` sẽ nằm vào ngày UTC **trước đó**, nên phải giữ đúng ngày trong dữ liệu. `TreeSet` với `timeLineOrder()` loại trùng theo instant, không theo offset/local time.

## 18. Checklist trước khi sử dụng trong ứng dụng

- Tôi cần **ngày + giờ + offset** hay chỉ **giờ + offset**? Có thiếu ngày để xác định instant không?
- Nguồn dữ liệu có lưu **offset cố định**, hay thực ra là **region zone có DST**?
- Khi đổi offset, mục tiêu của tôi là **giữ instant** hay **giữ local time**?
- Nếu đang xử lý event thật, đã dùng `Instant`/`OffsetDateTime` thay vì `OffsetTime` chưa?
- Có gắn ngày **trước** khi đổi `OffsetTime` qua nửa đêm không?
- So sánh event theo timeline có dùng `isEqual`/`toInstant`/`timeLineOrder` phù hợp, thay vì `equals` khi offset khác không?
- Có đang dùng `OffsetDateTime.toOffsetTime()` làm mất ngày mà không biết không?
- Với lịch lặp lại, có lưu `LocalTime` + `ZoneId` và kiểm tra DST gap/overlap không?
- Có parse ISO với offset rõ ràng, xử lý input thiếu offset/invalid date không?
- Formatter có giữ số chữ số nano và offset theo hợp đồng API/storage không?
- Test có tiêm `Clock.fixed`/`now(clock)` để tránh phụ thuộc timezone máy?
- Có tránh coi `ZoneOffset` như tên vùng hoặc dùng `toZonedDateTime()` để “khôi phục” region không?
- Các thao tác cộng/trừ thời gian có đúng ngữ nghĩa “ngày lịch” và “duration thực” không?
- Khi lưu database, đã kiểm tra precision, timezone semantics và round-trip chưa?

## 19. Tài liệu Oracle Java hiện hành

- `OffsetDateTime` — constructors, instant, compare, offset transformations, zone interop: https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/time/OffsetDateTime.html
- `OffsetTime` — time + offset, comparison on implied date, atDate: https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/time/OffsetTime.html
- `ZoneOffset` — fixed UTC offset: https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/time/ZoneOffset.html
- `ZoneId` — region time-zone rules: https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/time/ZoneId.html
- `Instant` — timeline moment: https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/time/Instant.html
- `ZonedDateTime` — zone rules và daylight saving time: https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/time/ZonedDateTime.html
- `Clock` — fixed clock cho unit test: https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/time/Clock.html
- `DateTimeFormatter` — ISO_OFFSET_DATE_TIME và ISO_OFFSET_TIME: https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/time/format/DateTimeFormatter.html

**Kết luận:** `OffsetDateTime` có đủ ngày, giờ và offset để biểu diễn **một instant**; `OffsetTime` chỉ có giờ và offset nên **không thể** xác định một timestamp tuyệt đối nếu chưa biết ngày. `ZoneOffset` là độ dịch cố định, khác `ZoneId` là bộ quy tắc vùng. Hãy giữ nguyên instant khi chuyển cách hiển thị, giữ ngày khi vượt nửa đêm, và chọn đúng kiểu lưu trữ cho event so với lịch lặp lại.