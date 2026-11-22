# So sánh cộng một ngày lịch với cộng 24 giờ qua ranh giới DST trong Java

Với `ZonedDateTime`, hai biểu thức tưởng như tương đương sau đây **có thể cho hai thời điểm kết thúc khác nhau**:

```java
ZonedDateTime tomorrowSameLocalTime = start.plusDays(1);
ZonedDateTime exactly24HoursLater  = start.plusHours(24);
```

Lý do là **“một ngày lịch”** và **“24 giờ thời lượng”** không phải cùng một khái niệm. `plusDays(1)` giữ ý định đi tới **ngày lịch kế tiếp theo giờ địa phương**, còn `plusHours(24)` đi tới thời điểm **24 giờ sau trên trục instant**. Khi múi giờ chuyển sang hoặc rời giờ mùa hè (*daylight saving time*, DST), hai phép toán có thể chênh một giờ — hoặc một lượng khác nếu quy tắc vùng đổi offset không đúng một giờ.

Bài học tập trung vào cơ chế trong `java.time.ZonedDateTime`, thí nghiệm qua ranh giới DST mùa xuân/mùa thu, cách phân biệt `Period` với `Duration`, kiểm tra khoảng giờ không tồn tại hoặc bị lặp và chọn phép tính theo yêu cầu nghiệp vụ.

## 1. Hai trục thời gian của `ZonedDateTime`

`ZonedDateTime` kết hợp **ngày–giờ địa phương** (`LocalDateTime`), **ID vùng** (`ZoneId`) và **offset UTC đã phân giải** (`ZoneOffset`). Nó cho phép nhìn một sự kiện ở hai góc độ:

1. **Local time-line (trục ngày giờ địa phương):** `2024-03-10 12:00` tại New York được hiểu theo lịch và giờ đồng hồ tại New York, không có nghĩa tròn 24 giờ từ `2024-03-09 12:00`.
2. **Instant time-line (trục thời điểm):** một `Instant` mô tả vị trí duy nhất trên trục thời gian Java; khi cộng `Duration.ofHours(24)`, thời điểm mới cách thời điểm cũ đúng 24 giờ theo phép toán `java.time`, sau đó được hiển thị lại theo quy tắc offset tại đích.

Java quy định:

| Phép toán trên `ZonedDateTime` | Trục được dùng | Ý nghĩa |
| --- | --- | --- |
| `plusDays(1)` | Ngày giờ địa phương | Chuyển sang ngày lịch kế tiếp, cố giữ giờ địa phương nếu hợp lệ |
| `plusWeeks(1)`, `plusMonths(1)`, `plusYears(1)` | Ngày giờ địa phương | Tiến theo thành phần lịch, giải quyết DST tại ngày mới |
| `plusHours(24)` | Instant | Cộng 24 × 3.600 giây trên trục thời điểm |
| `plusMinutes(1)`, `plusSeconds(1)`, `plusNanos(1)` | Instant | Tiến theo thời lượng chứ không theo đồng hồ treo tường |
| `plus(Period.ofDays(1))` | Ngày giờ địa phương | Tương ứng ý nghĩa cộng một ngày lịch |
| `plus(Duration.ofDays(1))` | Instant | Một `Duration` “day” luôn là 86.400 giây trong API |

`ZonedDateTime` **bất biến**: cả hai phép toán trả đối tượng mới, không sửa `start`. Không nhầm tên `ofDays(1)` của `Period` và `Duration`: một bên là lượng thời gian **dựa trên ngày lịch**, một bên là **số giây** cố định.

### DST khiến một ngày lịch không tròn 24 giờ

Khi vùng **nhảy đồng hồ tiến**, một quãng giữa hai mốc cùng giờ đồng hồ trên hai ngày kề nhau có thể chỉ có **23 giờ** theo instant. Khi vùng **vặn đồng hồ lùi**, quãng tương tự có thể dài **25 giờ**. Đó là ví dụ phổ biến cho chuyển offset 1 giờ. Không phải mọi quốc gia đều có DST, và không phải mọi thay đổi offset trong lịch sử đều dài 1 giờ.

Hãy sử dụng `ZoneId` thật như `America/New_York`, thay vì tự gắn offset cố định `-05:00` cho cả năm. `ZoneId` áp dụng quy tắc theo ngày từ dữ liệu timezone của JDK.

## 2. Mùa xuân: mất một giờ đồng hồ

Tại `America/New_York`, ngày **10/03/2024** đồng hồ nhảy tiến từ **01:59:59 EST (UTC−05:00)** sang **03:00:00 EDT (UTC−04:00)**. Trong ngày chuyển này, khoảng giờ địa phương từ **02:00 đến 02:59:59…** không tồn tại.

Giả sử bắt đầu vào trưa hôm trước:

```text
Bắt đầu:
2024-03-09T12:00-05:00[America/New_York]
= 2024-03-09T17:00:00Z

+ 1 ngày lịch:
2024-03-10T12:00-04:00[America/New_York]
= 2024-03-10T16:00:00Z
=> thực tế trôi qua 23 giờ

+ 24 giờ:
2024-03-10T13:00-04:00[America/New_York]
= 2024-03-10T17:00:00Z
=> thực tế trôi qua 24 giờ
```

Với `plusDays(1)`, mục tiêu là “trưa ngày tiếp theo” theo đồng hồ New York: vẫn **12:00**. Nhưng giữa hai buổi trưa đồng hồ đã bỏ qua một giờ, nên chênh lệch instant chỉ **23 giờ**.

Với `plusHours(24)`, mục tiêu là “đủ 24 giờ kể từ lúc bắt đầu”, nên giờ đồng hồ tại đích thành **13:00**. Hai kết quả chênh nhau **1 giờ**.

```java
ZoneId newYork = ZoneId.of("America/New_York");

ZonedDateTime start = ZonedDateTime.of(
        2024, 3, 9, 12, 0, 0, 0, newYork);

ZonedDateTime calendarDay = start.plusDays(1);
ZonedDateTime elapsed24h = start.plusHours(24);

System.out.println(calendarDay);
// 2024-03-10T12:00-04:00[America/New_York]
System.out.println(elapsed24h);
// 2024-03-10T13:00-04:00[America/New_York]

System.out.println(Duration.between(start, calendarDay).toHours());
// 23
System.out.println(Duration.between(start, elapsed24h).toHours());
// 24
```

Đoạn trên là **minh họa trong phương thức**, cần import `java.time.ZoneId`, `ZonedDateTime`, `Duration`.

## 3. Mùa thu: lặp lại một giờ đồng hồ

Tại New York ngày **03/11/2024**, đồng hồ chuyển từ **01:59:59 EDT (UTC−04:00)** quay về **01:00:00 EST (UTC−05:00)**. Khoảng **01:00–01:59:59…** diễn ra **hai lần**, ứng với hai offset khác nhau.

Giả sử bắt đầu lúc trưa hôm trước:

```text
Bắt đầu:
2024-11-02T12:00-04:00[America/New_York]
= 2024-11-02T16:00:00Z

+ 1 ngày lịch:
2024-11-03T12:00-05:00[America/New_York]
= 2024-11-03T17:00:00Z
=> thực tế trôi qua 25 giờ

+ 24 giờ:
2024-11-03T11:00-05:00[America/New_York]
= 2024-11-03T16:00:00Z
=> thực tế trôi qua 24 giờ
```

`plusDays(1)` giữ **12:00** của ngày lịch tiếp theo; vì giờ 01:00 được trải qua hai lần, khoảng giữa hai buổi trưa dài **25 giờ**. `plusHours(24)` vẫn cộng một thời lượng cố định và đến lúc **11:00** địa phương.

```java
ZoneId newYork = ZoneId.of("America/New_York");

ZonedDateTime start = ZonedDateTime.of(
        2024, 11, 2, 12, 0, 0, 0, newYork);

System.out.println(start.plusDays(1));
// 2024-11-03T12:00-05:00[America/New_York]
System.out.println(start.plusHours(24));
// 2024-11-03T11:00-05:00[America/New_York]

System.out.println(Duration.between(
        start, start.plusDays(1)).toHours()); // 25
```

### Bảng so sánh tại New York năm 2024

| Trường hợp | Bắt đầu | `plusDays(1)` | Thời lượng tới đích ngày lịch | `plusHours(24)` |
| --- | --- | --- | --- | --- |
| Không qua DST | 03/02 12:00 −05 | 04/02 12:00 −05 | 24 giờ | 04/02 12:00 −05 |
| Chuyển DST mùa xuân | 09/03 12:00 −05 | 10/03 12:00 −04 | **23 giờ** | 10/03 13:00 −04 |
| Chuyển DST mùa thu | 02/11 12:00 −04 | 03/11 12:00 −05 | **25 giờ** | 03/11 11:00 −05 |

**Kết luận quan trọng:** `plusDays(1)` **không có nghĩa** “luôn cộng 23 hoặc 25 giờ khi đi qua DST”. Kết quả phụ thuộc **thời điểm bắt đầu, thời điểm đích và quy tắc chuyển đổi**. Khi khoảng từ giờ địa phương đầu tới giờ địa phương đích không bao trùm sự thay đổi offset, hai cách có thể vẫn bằng nhau; xem tình huống đặc biệt bên dưới.

## 4. `Period.ofDays(1)` và `Duration.ofDays(1)`

Hai kiểu biểu diễn một lượng thời gian nhưng có ngữ nghĩa khác nhau:

- **`Period`:** năm, tháng, ngày theo lịch ISO, không đại diện trực tiếp một số giây cố định. Dùng khi yêu cầu nói về **ngày trên lịch**.
- **`Duration`:** số giây và nano giây của một khoảng trên trục instant. `Duration.ofDays(1)` được định nghĩa là **86.400 giây**, kể cả khi ngày lịch tại vùng có 23 hoặc 25 giờ do DST.

```java
ZonedDateTime start = ZonedDateTime.of(
        2024, 3, 9, 12, 0, 0, 0,
        ZoneId.of("America/New_York"));

ZonedDateTime byCalendar = start.plus(Period.ofDays(1));
ZonedDateTime byElapsed = start.plus(Duration.ofDays(1));

System.out.println(byCalendar.equals(start.plusDays(1))); // true
System.out.println(byElapsed.equals(start.plusHours(24))); // true
System.out.println(byCalendar.equals(byElapsed));          // false
```

`Duration.between(start.toInstant(), byCalendar.toInstant())` cho chênh lệch thực tế trên instant time-line: 23 giờ trong ví dụ mùa xuân. Nếu cần đo khoảng đã trôi qua, hãy tính từ các `Instant` hoặc dùng `Duration.between` trên các đối tượng có đầy đủ thông tin vùng/offset, không lấy hai `LocalDateTime` rồi suy diễn số giây thực.

### `ChronoUnit.DAYS` khác `ChronoUnit.HOURS`

Có thể viết tương ứng:

```java
ZonedDateTime nextCalendarDay = start.plus(1, ChronoUnit.DAYS);
ZonedDateTime after24Hours = start.plus(24, ChronoUnit.HOURS);
```

(Cần import `java.time.temporal.ChronoUnit`.) Theo quy tắc `ZonedDateTime`, `DAYS` là đơn vị theo ngày lịch; `HOURS` là đơn vị theo instant. Không hoán đổi hai biểu thức một cách máy móc để “tối ưu” khi dùng timezone có DST.

## 5. Trường hợp đặc biệt: qua DST nhưng hai kết quả vẫn trùng

Nói “đi qua DST thì `plusDays(1)` **luôn** khác `plusHours(24)`” cũng sai.

Ví dụ bắt đầu vào **02:30 sáng 09/03/2024** tại New York. Ngày hôm sau, `02:30` là giờ **không tồn tại** do nhảy từ 02:00 lên 03:00. Quy tắc `ZonedDateTime.plusDays(1)` cố đặt `02:30` ở ngày 10/03, rồi **đẩy thời điểm địa phương qua khoảng trống** thành `03:30-04:00`.

```java
ZoneId newYork = ZoneId.of("America/New_York");
ZonedDateTime beforeGap = ZonedDateTime.of(
        2024, 3, 9, 2, 30, 0, 0, newYork);

System.out.println(beforeGap.plusDays(1));
// 2024-03-10T03:30-04:00[America/New_York]
System.out.println(beforeGap.plusHours(24));
// 2024-03-10T03:30-04:00[America/New_York]
```

Cả hai phép tính trong trường hợp này tới **cùng instant**, dù cách tính **khác nhau**. Lý do không phải mỗi ngày luôn 24 giờ, mà là cách Java xử lý ngày giờ không hợp lệ ở đích khiến hai kết quả tình cờ trùng nhau.

Tương tự, vào DST overlap mùa thu, một giờ địa phương có **hai offset hợp lệ**. Khi cộng theo ngày lịch, `ZonedDateTime` cố giữ offset trước đó nếu vẫn hợp lệ; nếu không, thường chọn offset trước chuyển đổi. Khi cộng theo giờ, Java tiến trên instant time-line rồi suy ra local time. Do vậy phải kiểm thử theo **giờ cụ thể**, không chỉ theo ngày đổi DST.

## 6. Gap và overlap: cơ chế phân giải trong `ZonedDateTime`

Một `ZoneId` có bộ quy tắc (`ZoneRules`). Với một `LocalDateTime` nhất định, số offset hợp lệ có thể là:

| Số offset hợp lệ | Loại | Ý nghĩa |
| ---: | --- | --- |
| 1 | Normal | Giờ địa phương chỉ khớp một instant |
| 0 | Gap | Giờ địa phương không tồn tại do đồng hồ nhảy tiến |
| 2 | Overlap | Giờ địa phương xuất hiện hai lần khi đồng hồ lùi |

Với `plusDays(1)`, Java cộng ngày trên local time-line rồi phân giải theo zone rules:

- **Normal:** dùng offset hợp lệ của ngày giờ mới.
- **Gap:** đẩy ngày giờ địa phương tiến thêm độ dài khoảng trống; ví dụ `02:30` thành `03:30`.
- **Overlap:** giữ offset cũ nếu phù hợp; nếu không, chọn offset sớm hơn theo quy tắc mặc định của API.

`plusHours(24)` thì cộng thời lượng trên instant time-line, nơi mỗi instant xác định một offset tại vùng, nên không cần “chọn một trong hai instant” ở đích từ một local time mơ hồ.

### Phát hiện giờ đích có hợp lệ hay không

Nếu nghiệp vụ cần từ chối một cuộc hẹn bị đặt vào giờ không tồn tại hoặc bắt buộc người dùng chọn lần 01:30 đầu/nhì khi overlap:

```java
ZoneId zone = ZoneId.of("America/New_York");

LocalDateTime gap = LocalDateTime.of(2024, 3, 10, 2, 30);
LocalDateTime overlap = LocalDateTime.of(2024, 11, 3, 1, 30);

System.out.println(zone.getRules().getValidOffsets(gap).size()); // 0
System.out.println(zone.getRules().getValidOffsets(overlap).size()); // 2
```

Đây là **đoạn minh họa trong một phương thức**, cần import `java.time.ZoneId` và `LocalDateTime`. Danh sách offset từ `getValidOffsets` giúp xác định trạng thái trước khi lưu lịch. Với overlap, có thể dùng `withEarlierOffsetAtOverlap()`/`withLaterOffsetAtOverlap()`. Với logic phải xác thực offset chỉ định, dùng `ZonedDateTime.ofStrict(localDateTime, offset, zone)` và xử lý `DateTimeException` nếu không phù hợp.

Lưu ý DST không nhất thiết chuyển đúng một giờ, không phải vùng nào cũng có DST, và dữ liệu lịch sử hoặc quy định tương lai có thể khác. Không tính số giờ “mất/thêm” bằng hằng số 1 cho mọi vùng.

## 7. Ví dụ Java 17+ hoàn chỉnh, kết quả xác định

Tạo tệp **`CalendarDayVs24HoursDemo.java`**:

```java
import java.time.Duration;
import java.time.LocalDateTime;
import java.time.Period;
import java.time.ZoneId;
import java.time.ZonedDateTime;

public class CalendarDayVs24HoursDemo {
    private static final ZoneId NEW_YORK =
            ZoneId.of("America/New_York");

    private static void compare(
            String label, int year, int month, int day) {
        ZonedDateTime start = ZonedDateTime.of(
                year, month, day, 12, 0, 0, 0, NEW_YORK);
        ZonedDateTime byDay = start.plusDays(1);
        ZonedDateTime byHours = start.plusHours(24);

        System.out.println(label + " start = " + start);
        System.out.println(label + " +1 day = " + byDay);
        System.out.println(label + " +24 hours = " + byHours);
        System.out.println(label + " day elapsed hours = "
                + Duration.between(start, byDay).toHours());
        System.out.println(label + " fixed elapsed hours = "
                + Duration.between(start, byHours).toHours());
    }

    public static void main(String[] args) {
        compare("Spring", 2024, 3, 9);
        compare("Fall", 2024, 11, 2);
        compare("Normal", 2024, 2, 3);

        ZonedDateTime start = ZonedDateTime.of(
                2024, 3, 9, 12, 0, 0, 0, NEW_YORK);
        System.out.println("Period equals plusDays = "
                + start.plus(Period.ofDays(1))
                        .equals(start.plusDays(1)));
        System.out.println("Duration equals plusHours = "
                + start.plus(Duration.ofDays(1))
                        .equals(start.plusHours(24)));

        ZonedDateTime beforeGap = ZonedDateTime.of(
                2024, 3, 9, 2, 30, 0, 0, NEW_YORK);
        System.out.println("Gap +1 day = " + beforeGap.plusDays(1));
        System.out.println("Gap +24 hours = "
                + beforeGap.plusHours(24));

        LocalDateTime missing = LocalDateTime.of(
                2024, 3, 10, 2, 30);
        LocalDateTime repeated = LocalDateTime.of(
                2024, 11, 3, 1, 30);
        System.out.println("Gap valid offsets = "
                + NEW_YORK.getRules().getValidOffsets(missing).size());
        System.out.println("Overlap valid offsets = "
                + NEW_YORK.getRules().getValidOffsets(repeated).size());
    }
}
```

Biên dịch và chạy bằng JDK 17 trở lên:

```bash
javac CalendarDayVs24HoursDemo.java
java CalendarDayVs24HoursDemo
```

Kết quả với dữ liệu timezone tiêu chuẩn cho New York năm 2024:

```text
Spring start = 2024-03-09T12:00-05:00[America/New_York]
Spring +1 day = 2024-03-10T12:00-04:00[America/New_York]
Spring +24 hours = 2024-03-10T13:00-04:00[America/New_York]
Spring day elapsed hours = 23
Spring fixed elapsed hours = 24
Fall start = 2024-11-02T12:00-04:00[America/New_York]
Fall +1 day = 2024-11-03T12:00-05:00[America/New_York]
Fall +24 hours = 2024-11-03T11:00-05:00[America/New_York]
Fall day elapsed hours = 25
Fall fixed elapsed hours = 24
Normal start = 2024-02-03T12:00-05:00[America/New_York]
Normal +1 day = 2024-02-04T12:00-05:00[America/New_York]
Normal +24 hours = 2024-02-04T12:00-05:00[America/New_York]
Normal day elapsed hours = 24
Normal fixed elapsed hours = 24
Period equals plusDays = true
Duration equals plusHours = true
Gap +1 day = 2024-03-10T03:30-04:00[America/New_York]
Gap +24 hours = 2024-03-10T03:30-04:00[America/New_York]
Gap valid offsets = 0
Overlap valid offsets = 2
```

Các chuỗi in ra do `ZonedDateTime.toString()` sinh ra. Mã dùng **ngày cố định và `ZoneId` cụ thể**, không phụ thuộc đồng hồ hoặc timezone mặc định của máy. Quy tắc vùng do TZDB/JDK cung cấp; nếu dữ liệu múi giờ được thay đổi về mặt lịch sử hoặc từ nhà cung cấp khác, cần đối chiếu lại kết quả theo môi trường triển khai.

## 8. Chọn phép cộng theo yêu cầu nghiệp vụ

### 8.1. “Mỗi ngày lúc 09:00 tại một địa điểm”

Ví dụ hệ thống gửi thông báo mỗi ngày lúc **09:00 theo giờ New York**. Nhu cầu là **thời gian trên đồng hồ địa phương**, không phải cứ đúng 86.400 giây gửi một lần.

```java
ZoneId location = ZoneId.of("America/New_York");

ZonedDateTime scheduled = ZonedDateTime.of(
        2024, 3, 9, 9, 0, 0, 0, location);

ZonedDateTime next = scheduled.plusDays(1);
System.out.println(next);
// 2024-03-10T09:00-04:00[America/New_York]
```

Dùng `plusDays(1)`, hoặc lưu riêng `LocalTime` và `ZoneId` rồi giải quyết từng ngày lịch. Cần quy tắc riêng khi giờ hẹn rơi đúng gap/overlap. **Không** dùng `plusHours(24)` liên tục cho lịch lặp theo giờ đồng hồ, vì sau mỗi lần đổi DST nó có thể trôi dần khỏi giờ người dùng đã chọn.

### 8.2. “Phiên truy cập hết hạn sau đúng 24 giờ”

Nếu token, session, cache hoặc dịch vụ quy định thời hạn là **24 giờ elapsed time kể từ khi tạo**, hãy tính trên instant:

```java
Instant createdAt = Instant.parse("2024-03-09T17:00:00Z");
Instant expiresAt = createdAt.plus(Duration.ofHours(24));
```

Đoạn minh họa cần import `java.time.Instant` và `Duration`. Chuyển sang `ZonedDateTime` khi hiển thị giờ địa phương, nhưng không dùng `plusDays(1)` vì có thể rút ngắn/kéo dài thời hạn thực quanh DST. Khi đo timeout nội bộ trong tiến trình, nên cân nhắc đồng hồ đơn điệu; việc `Instant.now()` dựa đồng hồ hệ thống cũng có thể bị chỉnh lại.

### 8.3. “Ngày mai cùng giờ” và “24 giờ kể từ bây giờ”

Đây là hai yêu cầu khác nhau:

| Người dùng nói | Ý định ưu tiên | API phù hợp |
| --- | --- | --- |
| “Mai lúc 12:00, theo giờ địa phương” | Ngày lịch kế tiếp, giờ đồng hồ 12:00 | `plusDays(1)` hoặc tạo ngày mới + `LocalTime` + `ZoneId` |
| “Sau đúng 24 giờ” | Khoảng thời lượng cố định | `plusHours(24)`, `plus(Duration.ofHours(24))` hoặc `Instant.plus` |
| “Sau một ngày làm việc” | Quy tắc lịch làm việc, nghỉ lễ, cuối tuần | Cần business calendar, không chỉ `plusDays(1)` |
| “Cuối ngày mai lúc 23:59 địa phương” | Mốc theo lịch vùng | Tạo giờ đích từ ngày và `ZoneId`; đừng suy từ 48 giờ |
| “Sau đúng 1 × 86.400 giây” | Thời lượng giây | `Duration.ofDays(1)` / `Duration.ofSeconds(86_400)` |

Đối với nghiệp vụ tài chính, SLA hoặc tính phí, cần xác định ý nghĩa “một ngày” trong hợp đồng: **ngày lịch**, **24 giờ**, hay **ngày làm việc**. Không tự chọn dựa trên việc API nào ngắn hơn.

### 8.4. Qua DST và gần nửa đêm

```text
New York 2024-03-09T23:30-05:00
  + 1 ngày lịch → 2024-03-10T23:30-04:00
  + 24 giờ      → 2024-03-11T00:30-04:00
```

Ở ví dụ này, kết quả **khác cả ngày lịch**, không chỉ khác giờ. Nếu ứng dụng tính “ngày hết hạn” bằng cách cộng một số giây cố định rồi lấy `toLocalDate()`, nó có thể trả về ngày khác ý định.

## 9. Những điều không nên suy luận từ kết quả

**Một ngày của `LocalDate` không có số giờ cố định.** `LocalDate.plusDays(1)` chỉ tăng ngày trong lịch ISO, không cần quan tâm DST. Sau khi kết hợp với `LocalTime` và `ZoneId`, việc chuyển hai ngày thành instant mới làm xuất hiện chênh lệch 23/24/25 giờ. Vì vậy tính số giờ giữa hai `LocalDate` mà không biết vùng/giờ đầu cuối là không đủ thông tin.

**`LocalDateTime.plusDays(1)` không tự xử lý múi giờ.** Nó tăng thành phần lịch, không có zone/offset; kết quả có thể ứng với giờ địa phương không tồn tại. Nếu cần một instant hợp lệ, sau đó còn phải gắn `ZoneId` và phân giải DST. `ZonedDateTime.plusDays(1)` đã có ngữ cảnh vùng để làm phần này.

**UTC hoặc offset cố định không có chuyển DST theo quy tắc vùng.** Ví dụ `ZoneOffset.UTC` và `ZoneOffset.ofHours(7)` tự thân có offset không đổi; hai phép cộng thường trùng nhau đối với các khoảng bình thường trong những offset này. Dùng `Asia/Ho_Chi_Minh` cho lịch Việt Nam thay vì mặc định mọi nơi có DST.

**Chênh lệch `Duration` không đồng nghĩa số ngày lịch.** `Duration.between(start, end).toHours()` trả số giờ nguyên theo instant time-line. Để xác định “ngày nào trên lịch địa phương”, dùng `toLocalDate()`; để tính lịch làm việc cần thêm quy tắc nghiệp vụ.

**Giá trị `ZonedDateTime` có thể hiển thị khác mà trỏ cùng instant.** Nếu phải so sánh mốc thời gian, dùng `toInstant()` hoặc `isEqual`; chỉ so sánh ngày giờ địa phương có thể bỏ qua offset.

**Không tự dự báo giờ chuyển DST bằng công thức cố định.** Mỗi `ZoneId` có bộ quy tắc, thay đổi giữa vùng và các giai đoạn lịch sử. Các chính phủ có thể sửa quy tắc trong tương lai, vì vậy kiểm thử sát ngày chuyển đổi của vùng nghiệp vụ và cập nhật dữ liệu tzdb.

## 10. Lỗi phổ biến và cách sửa

| Lỗi | Hậu quả | Cách đúng |
| --- | --- | --- |
| Cho rằng `plusDays(1) == plusHours(24)` ở mọi vùng | Sai ở ranh giới thay đổi offset | Chọn local calendar hay elapsed time theo ý nghĩa nghiệp vụ |
| Thay `Period.ofDays(1)` bằng `Duration.ofDays(1)` | Biến ngày lịch thành 86.400 giây | Dùng `Period` khi cộng ngày lịch |
| Dùng `plusHours(24)` cho lịch “mỗi ngày 09:00” | Giờ hiển thị trôi sau DST | Dùng `plusDays(1)`/tạo local date + time theo vùng |
| Dùng `plusDays(1)` để tạo timeout 24 giờ | Có thể timeout sau 23 hoặc 25 giờ | Dùng `Instant.plus(Duration.ofHours(24))` |
| Áp offset `-05:00` cố định cho New York cả năm | Không phản ánh quy tắc DST `-04:00` mùa hè | Sử dụng `ZoneId.of("America/New_York")` |
| Khẳng định qua DST thì kết quả **luôn** khác | Có thể trùng khi đích được điều chỉnh qua gap hoặc offset hợp lệ | Kiểm tra thời điểm cụ thể, không khái quát |
| Nghĩ `plusDays` luôn giữ chính xác số giờ/phút đồng hồ | Giờ đích có thể rơi trong gap và được đẩy tiến | Kiểm tra `getValidOffsets` và chọn chính sách |
| Không xử lý giờ bị lặp trong overlap | Hai instant cho một local time | Cho chọn offset hoặc phân giải theo yêu cầu rõ ràng |
| Tính `Duration` từ `LocalDateTime` rồi coi là elapsed time thực | Thiếu zone để phản ánh thay đổi offset | Tính từ `Instant` hoặc `ZonedDateTime` đã phân giải |
| Chỉ test ngày thường | Không phát hiện lỗi đổi DST | Test trước/sau cả hai đợt đổi, gap và overlap |
| Giả định DST luôn ±1 giờ trên toàn thế giới | Sai với thay đổi offset không chuẩn, lịch sử | Dựa vào `ZoneRules` của vùng cụ thể |

## 11. Checklist kiểm thử và vận hành

1. **Xác định ý định:** “ngày lịch kế tiếp” hay “đủ N giờ đã trôi qua”? Ghi rõ vào tên hàm, chẳng hạn `nextDailyOccurrence` và `expiresAfterDuration`.
2. **Dùng `ZoneId` gắn với địa điểm:** tránh chỉ lưu offset hiện tại cho những lịch sẽ diễn ra trong tương lai.
3. **Kiểm thử ba kiểu ngày:** ngày thường, ngày DST nhảy tiến, ngày DST lùi.
4. **Kiểm thử giờ nhạy cảm:** ngay trước/sau ranh giới, giờ không tồn tại, giờ lặp và các giờ gần nửa đêm.
5. **Xác minh cả hai góc nhìn:** kết quả `toLocalDateTime()` và `Duration.between(start.toInstant(), end.toInstant())`.
6. **Quy định chính sách gap/overlap:** tự chuyển giờ hay từ chối; offset sớm hay muộn; cần hỏi người dùng khi giờ lặp hay không.
7. **Đồng bộ dữ liệu múi giờ:** dùng tzdb cập nhật, và cân nhắc điều kiện khi quy tắc pháp lý thay đổi sau khi lịch được tạo.

### Bài tập tự kiểm tra

**1.** Trưa 09/03/2024 ở New York cộng một ngày lịch đến mấy giờ, và đã trôi bao nhiêu giờ?  
→ `2024-03-10T12:00-04:00`, **23 giờ**.

**2.** Cùng thời điểm trên cộng 24 giờ thì sao?  
→ `2024-03-10T13:00-04:00`, đã trôi **24 giờ**.

**3.** Trưa 02/11/2024 cộng một ngày lịch ở New York đã trôi bao nhiêu giờ?  
→ **25 giờ** vì có một giờ đồng hồ lặp lại.

**4.** `Duration.ofDays(1)` có phải ngày lịch kế tiếp không?  
→ Không. Đây là **86.400 giây**, có thể khác `Period.ofDays(1)` trên `ZonedDateTime`.

**5.** `plusDays(1)` có nhất thiết giữ nguyên giờ đồng hồ khi giờ đích rơi vào DST gap không?  
→ Không. Java có thể **đẩy giờ đích tiến** qua khoảng gap.

**6.** Vì sao đôi khi cộng một ngày và cộng 24 giờ vẫn ra cùng kết quả dù có ranh giới DST?  
→ Quy tắc phân giải gap/overlap và vị trí hai mốc có thể khiến hai đường tính về cùng một instant; phải xét giờ cụ thể.

### Tài liệu API chính thức

- [Oracle Java SE 17 — `ZonedDateTime.plusDays` và `plusHours`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/ZonedDateTime.html): mô tả rõ local time-line và instant time-line, cùng cách xử lý gap/overlap.
- [Oracle Java SE 17 — `Duration`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/Duration.html): thời lượng dựa trên giây, mỗi “day” của `Duration` là 86.400 giây.
- [Oracle Java SE 17 — `Period`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/Period.html): năm, tháng, ngày theo lịch.
- [Oracle Java SE 17 — `ZoneRules`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/zone/ZoneRules.html): quy tắc offset hợp lệ, gap và overlap.

**Ghi nhớ:** `ZonedDateTime.plusDays(1)` cộng **một ngày theo lịch địa phương**; `plusHours(24)` cộng **24 giờ elapsed time**. Chúng chỉ giống nhau khi quy tắc vùng và giờ đang xét cho cùng mốc. Nếu yêu cầu là “ngày mai cùng giờ”, ưu tiên ngày lịch; nếu yêu cầu là “sau đúng 24 giờ”, ưu tiên `Duration`/`Instant`.
