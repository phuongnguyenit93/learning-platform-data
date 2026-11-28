# Instant, LocalDate, LocalTime và LocalDateTime trong Java 27

Khi viết ứng dụng Java 27, câu hỏi “bây giờ là mấy giờ?” khác về bản chất với “ngày sinh của khách hàng là ngày nào?” hoặc “cuộc hẹn diễn ra lúc 09:00 theo giờ Hà Nội?”. Nếu chọn sai kiểu dữ liệu thời gian, ứng dụng có thể hiển thị nhầm múi giờ, tính sai khoảng thời gian hoặc lưu một lịch hẹn không thể xác định thành thời điểm thực tế.

Gói `java.time` cung cấp các kiểu **bất biến** (*immutable*) dành cho những nhu cầu khác nhau. Trong bài này, bốn kiểu nền tảng là:

- `Instant` — một **thời điểm trên dòng thời gian** có thể so sánh trên toàn cầu.
- `LocalDate` — **ngày theo lịch**, không chứa giờ hay múi giờ.
- `LocalTime` — **giờ trong ngày**, không chứa ngày hay múi giờ.
- `LocalDateTime` — **ngày và giờ địa phương**, vẫn **không có múi giờ hoặc offset**.

Bài thuộc chương **Thời gian và số học chính xác**, trong module **Java 27 và các kiến thức liên quan**. Nội dung dùng các API ổn định và hiện hành của Java SE 27; không dựa vào những cách xử lý ngày giờ đã lỗi thời. Mục tiêu là chọn đúng kiểu, tạo/định dạng/tính toán đúng và hiểu khi nào bắt buộc bổ sung `ZoneId`, `ZoneOffset` hoặc `Clock`.

## 1. Mô hình tư duy: “thời điểm” khác “ngày giờ trên đồng hồ”

Xét một sự kiện xảy ra vào thời điểm:

```text
2026-11-27T03:15:30Z
```

Hậu tố `Z` biểu thị UTC offset bằng 0. Cùng thời điểm đó có thể được hiển thị tại Việt Nam là:

```text
2026-11-27 10:15:30  (Asia/Ho_Chi_Minh, UTC+07:00)
```

Hai biểu diễn trên nói về **cùng một sự kiện**, không phải hai sự kiện cách nhau bảy giờ. Ngược lại, chuỗi `2026-11-27T10:15:30` **không kèm múi giờ** nên một mình nó không đủ để xác định thời điểm tuyệt đối.

| Kiểu | Chứa những gì? | Không chứa gì? | Ví dụ giá trị | Tình huống phù hợp |
| --- | --- | --- | --- | --- |
| `Instant` | Một điểm trên dòng thời gian, độ phân giải biểu diễn đến nanosecond | Múi giờ hiển thị, ngày giờ theo lịch cụ thể | `2026-11-27T03:15:30Z` | Timestamp sự kiện, audit log, thời điểm bắt đầu/kết thúc |
| `LocalDate` | Năm, tháng, ngày theo lịch ISO | Giờ, phút, giây, offset, múi giờ | `2026-11-27` | Ngày sinh, hạn thanh toán theo ngày, ngày nghỉ |
| `LocalTime` | Giờ, phút, giây, phần lẻ giây | Ngày, offset, múi giờ | `09:30:00` | Giờ mở cửa hằng ngày, giờ hiển thị trong lịch |
| `LocalDateTime` | Ngày + giờ theo lịch ISO | Offset, múi giờ, một instant duy nhất | `2026-11-27T09:30:00` | Lịch hẹn tại địa điểm đã biết múi giờ, dữ liệu giờ địa phương |

Đây không phải bốn mức độ “chi tiết hơn” của cùng một kiểu. `Instant` và `LocalDateTime` trả lời **hai câu hỏi khác nhau**: *sự kiện xảy ra khi nào trên dòng thời gian?* và *đồng hồ tại một nơi có thể hiển thị ngày giờ nào?*

> **Nguyên tắc đầu tiên:** Nếu dữ liệu được dùng để xác định hoặc so sánh thời điểm của sự kiện trên toàn hệ thống, hãy cân nhắc `Instant`. Nếu dữ liệu thuộc về lịch hoặc đồng hồ địa phương và cố ý chưa có thông tin múi giờ, dùng kiểu `Local...` tương ứng.

## 2. `Instant` — một thời điểm tuyệt đối

`java.time.Instant` biểu diễn một điểm trên trục thời gian, dựa trên số giây tính từ mốc epoch cùng phần nanosecond trong giây. Mốc epoch là:

```text
1970-01-01T00:00:00Z
```

Các cách tạo `Instant` thường dùng:

```java
import java.time.Instant;

Instant epoch = Instant.EPOCH;
Instant parsed = Instant.parse("2026-11-27T03:15:30Z");
Instant fromSeconds = Instant.ofEpochSecond(1_000L);
Instant fromMillis = Instant.ofEpochMilli(1_000L);

System.out.println(epoch);       // 1970-01-01T00:00:00Z
System.out.println(fromSeconds); // 1970-01-01T00:16:40Z
System.out.println(fromMillis);  // 1970-01-01T00:00:01Z
```

Chú ý khác biệt đơn vị: `ofEpochSecond(1_000)` là **1.000 giây**, còn `ofEpochMilli(1_000)` là **1.000 mili giây = 1 giây**. Nhầm giây với mili giây là lỗi phổ biến khi tích hợp API và database.

### 2.1. Lấy thời điểm hiện tại

```java
Instant now = Instant.now();
```

`Instant.now()` đọc nguồn thời gian hệ thống; kết quả không phụ thuộc kiểu hiển thị ngày/giờ ở Việt Nam hay nước khác. Có thể định dạng `Instant` thành chuỗi ISO-8601, thường có hậu tố `Z`.

Với logic cần kiểm thử, nên **truyền `Clock` vào phương thức** thay vì gọi thời gian hệ thống ở nhiều nơi:

```java
import java.time.Clock;
import java.time.Instant;

static Instant createdAt(Clock clock) {
    return Instant.now(clock);
}
```

Khi test có thể dùng `Clock.fixed(...)` để mọi lần gọi trả cùng thời điểm. Phần kiểm thử sẽ được trình bày chi tiết ở mục sau.

### 2.2. Độ chính xác biểu diễn và độ chính xác của đồng hồ

`Instant` hỗ trợ phần lẻ của giây đến **nanosecond**:

```java
Instant precise = Instant.parse("2026-11-27T03:15:30.123456789Z");

System.out.println(precise.getNano()); // 123456789
```

Điều này **không** có nghĩa đồng hồ hệ điều hành hay mọi cơ sở dữ liệu cung cấp độ chính xác nanosecond. Độ phân giải và độ chính xác thực tế phụ thuộc nguồn thời gian và hệ thống lưu trữ.

`toEpochMilli()` chuyển thời điểm thành số mili giây kể từ epoch và có thể **làm mất phần nhỏ hơn một mili giây**:

```java
long milliseconds = precise.toEpochMilli();
```

Ngoài ra, với `Instant` quá xa epoch, việc chuyển sang `long` milli giây có thể bị tràn phạm vi và ném `ArithmeticException`. Nếu hệ thống cần giữ đến nanosecond, hãy chọn schema/lưu trữ phù hợp thay vì mặc định chỉ có một cột epoch milliseconds.

### 2.3. Tính toán và so sánh `Instant`

```java
import java.time.Duration;
import java.time.Instant;

Instant start = Instant.parse("2026-11-27T03:00:00Z");
Instant end = start.plusSeconds(90);

System.out.println(end);                         // 2026-11-27T03:01:30Z
System.out.println(start.isBefore(end));         // true
System.out.println(Duration.between(start, end)); // PT1M30S
```

Đây là cách tự nhiên để đo **thời gian trôi qua** giữa hai sự kiện. Với mốc lấy từ đồng hồ hệ thống, kết quả thời gian trôi qua có thể bị ảnh hưởng bởi việc đồng hồ được điều chỉnh; để benchmark hiệu năng trong **cùng một tiến trình**, API đo thời gian đơn điệu thích hợp hơn có thể là `System.nanoTime()`. Không dùng `System.nanoTime()` làm timestamp có nghĩa trên lịch.

## 3. `LocalDate` — ngày theo lịch, không có thời gian

`LocalDate` biểu diễn ngày dựa trên hệ lịch **ISO-8601** với các trường năm, tháng và ngày. Nó không mang giờ hay múi giờ.

```java
import java.time.LocalDate;
import java.time.Month;

LocalDate invoiceDate = LocalDate.of(2026, 11, 27);
LocalDate birthday = LocalDate.of(2000, Month.MARCH, 15);
LocalDate parsed = LocalDate.parse("2026-11-27");

System.out.println(invoiceDate);          // 2026-11-27
System.out.println(birthday.getMonth());  // MARCH
System.out.println(parsed.getDayOfMonth()); // 27
```

Một giá trị `LocalDate.of(2026, 11, 27)` không thay đổi khi ứng dụng chạy trên máy ở Tokyo, Hà Nội hay New York. Nếu “ngày sinh” là ngày trên giấy tờ, lưu nó thành `Instant` ở nửa đêm UTC thường là **sai mô hình**: khi hiển thị ở múi giờ khác, ngày có thể bị đổi.

### 3.1. Java kiểm tra tính hợp lệ của ngày

```java
LocalDate leapDay = LocalDate.of(2024, 2, 29); // Hợp lệ

// Ném DateTimeException: 2026 không có ngày 29/02.
// LocalDate invalid = LocalDate.of(2026, 2, 29);
```

Không cần tự viết bảng số ngày trong từng tháng để tạo `LocalDate` hợp lệ. Java xử lý năm nhuận và quy tắc lịch ISO.

### 3.2. Cộng/trừ ngày, tháng, năm

```java
LocalDate date = LocalDate.of(2026, 1, 31);

System.out.println(date.plusDays(1));  // 2026-02-01
System.out.println(date.plusMonths(1)); // 2026-02-28
System.out.println(date.minusWeeks(1)); // 2026-01-24
```

Một tháng không luôn có 30 ngày. Khi cộng một tháng vào 31/01 mà tháng đích chỉ có 28 ngày, `LocalDate.plusMonths(1)` điều chỉnh về **ngày hợp lệ cuối cùng của tháng đích**.

Cần xác định quy tắc nghiệp vụ riêng với hóa đơn, lãi, ngày gia hạn: “thêm một tháng theo lịch” không nhất thiết giống “thêm 30 ngày”.

### 3.3. Cộng năm vào ngày nhuận

```java
LocalDate leapBirthday = LocalDate.of(2024, 2, 29);
System.out.println(leapBirthday.plusYears(1)); // 2025-02-28
```

Đây là quy tắc chỉnh ngày không hợp lệ của API. Nhưng nếu nghiệp vụ muốn kỷ niệm ngày 29/02 vào **01/03** trong năm không nhuận, phải lập trình quy tắc riêng; không nên nhầm mặc định thư viện với chính sách doanh nghiệp.

### 3.4. Kết hợp ngày với một giờ trong ngày

```java
import java.time.LocalDateTime;
import java.time.LocalTime;

LocalDate workDay = LocalDate.of(2026, 11, 27);
LocalTime opening = LocalTime.of(9, 30);

LocalDateTime openingDateTime = workDay.atTime(opening);
System.out.println(openingDateTime); // 2026-11-27T09:30
```

`atTime(...)` ghép hai thành phần địa phương. Nó **chưa gắn múi giờ** và chưa tạo `Instant`.

## 4. `LocalTime` — giờ trong ngày, không có ngày

`LocalTime` biểu diễn giờ, phút, giây và nanosecond trong **một ngày 24 giờ trên đồng hồ địa phương**, không kèm ngày hoặc múi giờ.

```java
import java.time.LocalTime;

LocalTime opening = LocalTime.of(8, 30);
LocalTime closing = LocalTime.of(17, 45);
LocalTime parsed = LocalTime.parse("09:15:30");

System.out.println(opening);          // 08:30
System.out.println(closing.isAfter(opening)); // true
System.out.println(parsed.getSecond());      // 30
```

Điều này phù hợp để diễn đạt “cửa hàng mở lúc 08:30” theo lịch thường lệ. Một `LocalTime` duy nhất **không** cho biết giờ đó ứng với thời điểm nào trên dòng thời gian.

### 4.1. Cộng giờ có thể vòng qua nửa đêm

```java
LocalTime time = LocalTime.of(23, 50);

System.out.println(time.plusMinutes(20)); // 00:10
```

Kết quả vòng về đầu ngày vì `LocalTime` **không lưu ngày**. Nếu yêu cầu là “20 phút sau lúc 23:50 ngày 27/11/2026”, cần dùng `LocalDateTime` hoặc một kiểu đã gắn múi giờ để **không đánh mất ngày**.

### 4.2. Giờ của ca làm đêm cần thêm thông tin ngày

```java
LocalTime start = LocalTime.of(22, 0);
LocalTime end = LocalTime.of(6, 0);

System.out.println(end.isBefore(start)); // true
```

Điều này không có nghĩa ca làm có thời lượng âm. Chỉ có nghĩa 06:00 đứng trước 22:00 trên **cùng một đồng hồ trong ngày**. Một ca qua nửa đêm cần ngày bắt đầu/ngày kết thúc hoặc quy tắc “ca hôm sau”.

```java
LocalDate day = LocalDate.of(2026, 11, 27);

LocalDateTime startsAt = day.atTime(start);
LocalDateTime endsAt = day.plusDays(1).atTime(end);
```

Hai giá trị này đã đủ để mô tả ca theo thời gian địa phương; nếu phải tính **thời gian thực tế** qua các lần đổi giờ mùa hè ở một khu vực, còn phải xác định múi giờ và chuyển sang thời điểm tuyệt đối.

## 5. `LocalDateTime` — có ngày và giờ nhưng chưa có múi giờ

`LocalDateTime` kết hợp các thành phần của `LocalDate` và `LocalTime`:

```java
import java.time.LocalDate;
import java.time.LocalDateTime;
import java.time.LocalTime;

LocalDateTime meeting = LocalDateTime.of(2026, 11, 27, 9, 30);
LocalDateTime parsed = LocalDateTime.parse("2026-11-27T09:30:00");
LocalDateTime combined = LocalDate.of(2026, 11, 27)
        .atTime(LocalTime.of(9, 30));

System.out.println(meeting);             // 2026-11-27T09:30
System.out.println(meeting.equals(parsed)); // true
System.out.println(meeting.equals(combined)); // true
```

Các giá trị bằng nhau vì chứa cùng các thành phần ngày và giờ, dù cách tạo khác nhau.

**Điểm cần nhớ:** `LocalDateTime` **không chứa** `ZoneId`, `ZoneOffset` hoặc một timestamp tuyệt đối. Chỉ từ `2026-11-27T09:30`, ta không thể biết sự kiện xảy ra lúc nào theo UTC.

### 5.1. Đừng dùng LocalDateTime làm timestamp tuyệt đối

Giả sử hai hệ thống đều ghi:

```text
2026-11-27T09:30
```

Nếu hệ thống A ở `Asia/Ho_Chi_Minh` và hệ thống B ở `Europe/Paris`, hai thời điểm thực tế **không giống nhau**. Việc sắp xếp hai chuỗi hoặc hai `LocalDateTime` không thể thay thế quy tắc so sánh các instant từ các vùng khác nhau.

Nếu nghiệp vụ cần ghi lại **sự kiện đã xảy ra**, nên lưu `Instant` (hoặc kiểu chứa offset đầy đủ phù hợp với schema), và chỉ đổi sang múi giờ người xem khi hiển thị.

### 5.2. Cộng/trừ ngày giờ địa phương

```java
LocalDateTime end = LocalDateTime
        .of(2026, 12, 31, 23, 30)
        .plusHours(2);

System.out.println(end); // 2027-01-01T01:30
```

Khác với `LocalTime`, `LocalDateTime` giữ cả ngày nên có thể chuyển qua năm mới. Nhưng phép cộng này diễn ra trên **ngày giờ địa phương**, chưa xét sự thay đổi offset múi giờ.

## 6. Tạo đối tượng bằng `now()` và dùng `Clock` cho kết quả xác định

Cả bốn kiểu đều có các factory method lấy giá trị hiện tại phù hợp:

```java
import java.time.Instant;
import java.time.LocalDate;
import java.time.LocalDateTime;
import java.time.LocalTime;

Instant instant = Instant.now();
LocalDate today = LocalDate.now();
LocalTime currentTime = LocalTime.now();
LocalDateTime localNow = LocalDateTime.now();
```

Các phương thức `Local...now()` **không nhận tham số** sử dụng múi giờ mặc định của hệ thống. Nếu cùng chương trình chạy trên server ở UTC và laptop ở Việt Nam, ngày/giờ địa phương thu được có thể khác nhau tại cùng một thời điểm.

Khi múi giờ là yêu cầu nghiệp vụ, hãy truyền rõ:

```java
import java.time.ZoneId;

ZoneId vietnam = ZoneId.of("Asia/Ho_Chi_Minh");

LocalDate todayInVietnam = LocalDate.now(vietnam);
LocalTime timeInVietnam = LocalTime.now(vietnam);
LocalDateTime localNowInVietnam = LocalDateTime.now(vietnam);
```

Đối với ứng dụng cần **kiểm thử dễ lặp lại**, nên truyền vào một `Clock` thay vì đọc trực tiếp môi trường ở mỗi nơi:

```java
import java.time.Clock;
import java.time.Instant;
import java.time.LocalDate;
import java.time.LocalDateTime;
import java.time.LocalTime;
import java.time.ZoneId;

Clock fixed = Clock.fixed(
        Instant.parse("2026-11-27T03:15:30Z"),
        ZoneId.of("Asia/Ho_Chi_Minh")
);

System.out.println(Instant.now(fixed));       // 2026-11-27T03:15:30Z
System.out.println(LocalDate.now(fixed));     // 2026-11-27
System.out.println(LocalTime.now(fixed));     // 10:15:30
System.out.println(LocalDateTime.now(fixed)); // 2026-11-27T10:15:30
```

Tất cả giá trị đều dựa trên **cùng instant cố định**, nhưng ba kiểu Local được diễn giải theo múi giờ của `Clock`.

### 6.1. Ví dụ phương thức dễ kiểm thử

```java
import java.time.Clock;
import java.time.LocalDate;

static boolean isExpired(LocalDate dueDate, Clock clock) {
    return LocalDate.now(clock).isAfter(dueDate);
}
```

Với quy tắc “hết hạn sau ngày đến hạn”, đoạn trên trả `true` **chỉ khi ngày hiện tại lớn hơn dueDate**. Nếu hợp đồng là “hết hạn ngay từ đầu ngày đến hạn”, cần dùng chính sách khác.

Điểm quan trọng: business rule phải xác định **ngày hiện tại theo múi giờ nào**, và clock cung cấp múi giờ đó. Test dùng `Clock.fixed` để kiểm tra rõ trước/sau ranh giới ngày.

## 7. Kết nối các kiểu: `ZoneId`, `ZoneOffset` và `ZonedDateTime`

Bốn kiểu trong bài trả lời các nhu cầu khác nhau; khi muốn đổi một giá trị ngày giờ địa phương thành thời điểm tuyệt đối, ta cần **ngữ cảnh múi giờ**.

- `ZoneId` như `Asia/Ho_Chi_Minh` hoặc `Europe/Paris` định danh một khu vực với **tập quy tắc offset theo lịch sử/tương lai**. Quy tắc có thể được cập nhật theo cơ sở dữ liệu múi giờ của JDK.
- `ZoneOffset` như `+07:00` biểu diễn **một offset cụ thể so với UTC**, không chứa mọi quy tắc lịch sử của khu vực.
- `ZonedDateTime` kết hợp ngày giờ địa phương với zone, cho phép xác định instant khi quy tắc múi giờ và cách xử lý trường hợp đặc biệt đã được giải quyết.

### 7.1. Từ Instant tới ngày giờ ở một khu vực

```java
import java.time.Instant;
import java.time.ZoneId;
import java.time.ZonedDateTime;

Instant event = Instant.parse("2026-11-27T03:15:30Z");
ZoneId vietnam = ZoneId.of("Asia/Ho_Chi_Minh");

ZonedDateTime displayed = event.atZone(vietnam);

System.out.println(displayed);
// 2026-11-27T10:15:30+07:00[Asia/Ho_Chi_Minh]

System.out.println(displayed.toLocalDate());     // 2026-11-27
System.out.println(displayed.toLocalTime());     // 10:15:30
System.out.println(displayed.toLocalDateTime()); // 2026-11-27T10:15:30
```

Ở ví dụ này, `event` là mốc chuẩn để lưu hoặc so sánh. Giá trị `displayed` thể hiện cách người dùng ở Việt Nam nhìn thấy cùng thời điểm đó.

Có thể lấy trực tiếp `LocalDateTime` từ Instant với vùng đã biết:

```java
LocalDateTime local = LocalDateTime.ofInstant(event, vietnam);
```

### 7.2. Từ LocalDateTime tới Instant cần bổ sung múi giờ

```java
import java.time.Instant;
import java.time.LocalDateTime;
import java.time.ZoneId;

LocalDateTime meeting = LocalDateTime.of(2026, 11, 27, 9, 30);
ZoneId meetingZone = ZoneId.of("Asia/Ho_Chi_Minh");

Instant scheduledAt = meeting.atZone(meetingZone).toInstant();

System.out.println(scheduledAt); // 2026-11-27T02:30:00Z
```

Không có phép chuyển đổi đúng nghĩa `meeting.toInstant()` **không tham số**: bản thân `LocalDateTime` thiếu offset. Biểu thức `atZone(meetingZone)` là bước áp dụng chính sách múi giờ để tạo `ZonedDateTime`, sau đó mới lấy `Instant`.

Nếu một bản ghi lịch hẹn cần được xử lý trong nhiều năm, nên giữ cả **giờ địa phương và ZoneId nghiệp vụ** cùng chính sách xử lý DST. Lưu riêng một offset cố định đôi khi không thể biểu diễn các thay đổi quy tắc múi giờ trong tương lai.

### 7.3. Đừng đánh đồng ZoneId khu vực với offset cố định

`ZoneId.of("Asia/Ho_Chi_Minh")` mang định danh vùng; `ZoneOffset.ofHours(7)` chỉ mang offset `+07:00`. Ở thời điểm của ví dụ, hai cách diễn giải có thể trùng nhau, nhưng về mô hình không tương đương.

Đặc biệt với vùng có đổi giờ mùa hè, một offset không mô tả được các lần đổi giờ. Hãy ưu tiên **ZoneId theo khu vực** khi nghiệp vụ đề cập đến “giờ địa phương của địa điểm” (như cuộc họp ở New York), và `ZoneOffset` khi dữ liệu thực sự được mô tả bằng một offset cụ thể.

## 8. Lỗ hổng và giờ trùng khi đổi giờ mùa hè (DST)

Một `LocalDateTime` không phải lúc nào cũng ánh xạ **duy nhất** tới `Instant` trong khu vực có thay đổi offset theo mùa.

Có hai trường hợp cần xét:

1. **Gap (giờ không tồn tại):** đồng hồ được chỉnh tiến lên; một số giờ địa phương bị bỏ qua.
2. **Overlap (giờ lặp lại):** đồng hồ được chỉnh lùi; cùng một giờ địa phương xảy ra hai lần tại hai offset khác nhau.

Ví dụ với quy tắc DST tại `America/New_York` trong năm 2026:

```java
import java.time.LocalDateTime;
import java.time.ZoneId;

ZoneId newYork = ZoneId.of("America/New_York");

LocalDateTime gap = LocalDateTime.of(2026, 3, 8, 2, 30);
LocalDateTime overlap = LocalDateTime.of(2026, 11, 1, 1, 30);
```

- `2026-03-08 02:30` nằm trong **khoảng giờ bị nhảy qua** theo quy tắc New York hiện hành. Khi gọi `gap.atZone(newYork)`, API mặc định điều chỉnh ngày giờ địa phương tiến theo độ dài khoảng gap để tạo thời điểm hợp lệ.
- `2026-11-01 01:30` thuộc **khoảng giờ xuất hiện hai lần**. Khi gọi `overlap.atZone(newYork)`, API mặc định dùng offset sớm hơn của hai offset hợp lệ (thường là offset mùa hè ở lần xuất hiện đầu). Có thể chọn lần thứ hai qua `withLaterOffsetAtOverlap()` trên `ZonedDateTime`.

Có thể kiểm tra các offset hợp lệ **trước khi** quyết định:

```java
import java.time.LocalDateTime;
import java.time.ZoneId;
import java.time.ZoneOffset;
import java.util.List;

static List<ZoneOffset> validOffsets(
        LocalDateTime local, ZoneId zone) {
    return zone.getRules().getValidOffsets(local);
}
```

Diễn giải kết quả:

- `0` offset hợp lệ: local time rơi vào **gap**.
- `1` offset hợp lệ: thời điểm địa phương ánh xạ rõ ràng.
- `2` offset hợp lệ: **overlap**, cần chọn lần xuất hiện.

Với hệ thống đặt lịch quan trọng, không nên mặc định mọi giá trị `LocalDateTime` đều hợp lệ và duy nhất. Hãy xác định cách xử lý gap/overlap: từ chối, yêu cầu người dùng chọn, hoặc áp dụng quy tắc nghiệp vụ rõ ràng. Quy tắc múi giờ có thể thay đổi theo cập nhật dữ liệu tzdb, nên các trường hợp này cần được kiểm thử trên môi trường thực tế.

## 9. So sánh và tính bằng nhau

Bốn kiểu đều là các giá trị bất biến; khi cần so sánh nội dung, dùng `equals`, `compareTo`, `isBefore` hoặc `isAfter` thay vì `==`.

```java
import java.time.Instant;
import java.time.LocalDate;

LocalDate a = LocalDate.of(2026, 11, 27);
LocalDate b = LocalDate.parse("2026-11-27");

System.out.println(a.equals(b)); // true
System.out.println(a.isBefore(b)); // false

Instant first = Instant.parse("2026-11-27T03:00:00Z");
Instant second = Instant.parse("2026-11-27T03:30:00Z");

System.out.println(first.isBefore(second)); // true
```

`==` chỉ kiểm tra hai tham chiếu có trỏ tới **chính cùng một instance**. Java không bảo đảm hai lời gọi tạo giá trị ngày giờ bằng nhau trả cùng identity; các lớp `java.time` trong bài là *value-based classes*, không nên dùng identity hoặc khóa đồng bộ trên instance của chúng.

**So sánh đúng “loại thời gian”:**

- `Instant` được so sánh trên dòng thời gian.
- `LocalDate` được so sánh theo ngày lịch.
- `LocalTime` được so sánh theo giờ trên một ngày chuẩn, không biết ngày hôm qua/hôm sau.
- `LocalDateTime` được so sánh theo cặp ngày + giờ **địa phương**, không phải một timeline toàn cầu.

Nếu hai giá trị `LocalDateTime` đến từ những vùng khác nhau, phải quy đổi về cùng mốc tuyệt đối với zone/offset phù hợp **trước khi** suy ra sự kiện nào xảy ra trước.

## 10. `Duration` và `Period` — khoảng thời gian trôi qua khác khoảng theo lịch

Để tính toán đúng, cần phân biệt:

- `Duration`: lượng thời gian theo **giây và nanosecond**; phù hợp cho khoảng thời gian trôi qua.
- `Period`: khoảng theo **năm, tháng, ngày lịch**; phù hợp cho lịch trình, ngày đến hạn, tuổi theo lịch.

```java
import java.time.Duration;
import java.time.Instant;
import java.time.LocalDate;
import java.time.Period;

Instant start = Instant.parse("2026-11-27T03:00:00Z");
Instant end = start.plusSeconds(90);
Duration elapsed = Duration.between(start, end);

System.out.println(elapsed.toSeconds()); // 90

LocalDate startDate = LocalDate.of(2026, 11, 27);
LocalDate dueDate = startDate.plusMonths(1);
Period calendarGap = Period.between(startDate, dueDate);

System.out.println(dueDate);          // 2026-12-27
System.out.println(calendarGap);      // P1M
```

### 10.1. Một ngày theo lịch không phải lúc nào cũng dài 24 giờ

Tại vùng có DST, hai cách cộng sau có thể cho **giờ địa phương khác nhau**:

```java
import java.time.Duration;
import java.time.Period;
import java.time.ZoneId;
import java.time.ZonedDateTime;

ZonedDateTime beforeChange = ZonedDateTime.of(
        2026, 3, 7, 12, 0, 0, 0,
        ZoneId.of("America/New_York")
);

ZonedDateTime nextCalendarDay =
        beforeChange.plus(Period.ofDays(1));

ZonedDateTime after24Hours =
        beforeChange.plus(Duration.ofDays(1));
```

Với quy tắc DST New York năm 2026, `nextCalendarDay` biểu diễn **trưa ngày hôm sau theo lịch**, còn `after24Hours` là **chính xác 24 giờ trôi qua** và có thể rơi vào 13:00 theo đồng hồ địa phương.

Vì vậy:

- Nếu nghiệp vụ là “ngày hôm sau lúc 12:00 theo giờ cửa hàng”, ưu tiên thao tác lịch theo zone.
- Nếu nghiệp vụ là “hết hạn đúng 24 giờ sau khi tạo”, thao tác trên `Instant` với `Duration.ofHours(24)` thường rõ ràng hơn.

Đừng thay một tháng bằng `Duration.ofDays(30)` nếu yêu cầu thực tế là **một tháng lịch**.

### 10.2. Tính chênh lệch ngày và giờ bằng ChronoUnit

`ChronoUnit` hữu ích khi câu hỏi là “có bao nhiêu đơn vị trọn vẹn?”:

```java
import java.time.LocalDate;
import java.time.temporal.ChronoUnit;

LocalDate first = LocalDate.of(2026, 11, 27);
LocalDate second = LocalDate.of(2026, 12, 1);

long days = ChronoUnit.DAYS.between(first, second);
System.out.println(days); // 4
```

Với `LocalTime`, việc tính chênh lệch không tự suy luận có qua nửa đêm hay không:

```java
import java.time.Duration;
import java.time.LocalTime;

Duration delta = Duration.between(
        LocalTime.of(23, 30),
        LocalTime.of(0, 30)
);

System.out.println(delta); // PT-23H
```

Muốn tính “từ 23:30 hôm nay đến 00:30 ngày mai”, cần đưa **ngày** vào các mốc rồi tính bằng loại thời gian phù hợp; nếu liên quan DST, tiếp tục xác định zone.

## 11. Parsing: chuyển chuỗi thành đúng kiểu dữ liệu

Mỗi lớp có phương thức `parse(...)` cho biểu diễn chuẩn ISO tương ứng:

```java
import java.time.Instant;
import java.time.LocalDate;
import java.time.LocalDateTime;
import java.time.LocalTime;

Instant instant = Instant.parse("2026-11-27T03:15:30Z");
LocalDate date = LocalDate.parse("2026-11-27");
LocalTime time = LocalTime.parse("10:15:30");
LocalDateTime dateTime = LocalDateTime.parse("2026-11-27T10:15:30");
```

Không nên giả định một chuỗi ISO chứa offset có thể được parse trực tiếp bằng `LocalDateTime.parse(...)` mặc định như một chuỗi local thuần. Khi đầu vào có offset hoặc zone, hãy chọn kiểu và formatter tương ứng (ví dụ `OffsetDateTime` hoặc `ZonedDateTime`), sau đó chuyển đổi theo mục tiêu.

### 11.1. Định dạng theo yêu cầu hiển thị

`DateTimeFormatter` là API bất biến và thread-safe để parse/format dữ liệu ngày giờ.

```java
import java.time.LocalDateTime;
import java.time.format.DateTimeFormatter;
import java.time.format.ResolverStyle;
import java.util.Locale;

DateTimeFormatter formatter = DateTimeFormatter
        .ofPattern("dd/MM/uuuu HH:mm", Locale.ROOT)
        .withResolverStyle(ResolverStyle.STRICT);

LocalDateTime appointment = LocalDateTime.of(2026, 11, 27, 10, 15);

String text = appointment.format(formatter);
LocalDateTime parsed = LocalDateTime.parse(text, formatter);

System.out.println(text);    // 27/11/2026 10:15
System.out.println(parsed);  // 2026-11-27T10:15
```

Pattern `dd/MM/uuuu HH:mm` diễn tả ngày/tháng/năm-ISO giờ:phút. Cần phân biệt:

- `MM`: **tháng**, còn `mm`: **phút**.
- `HH`: giờ 00–23; `hh`: giờ 01–12, cần kèm ngữ cảnh AM/PM.
- `uuuu`: *proleptic year* hữu ích trong parse strict; `yyyy` có semantics là *year-of-era* và có thể cần thông tin era trong một số kiểu parse nghiêm ngặt.
- `YYYY` là **week-based year**, không phải năm lịch thông thường; dùng nhầm có thể làm năm hiển thị khác ở ngày gần năm mới.

Không dùng pattern ngày/giờ có mục đích hiển thị như thể đó là định dạng wire/storage chắc chắn ổn định. Với dữ liệu trao đổi giữa dịch vụ, nên ưu tiên định dạng ISO rõ ràng và kèm offset/zone đúng hợp đồng.

### 11.2. Xử lý dữ liệu nhập sai

```java
import java.time.LocalDate;
import java.time.format.DateTimeParseException;

static LocalDate parseDate(String input) {
    try {
        return LocalDate.parse(input);
    } catch (DateTimeParseException ex) {
        throw new IllegalArgumentException(
                "Ngày phải theo định dạng yyyy-MM-dd hợp lệ", ex
        );
    }
}
```

Chuỗi như `2026-02-29` không hợp lệ vì 2026 không phải năm nhuận. Cần phân biệt:

1. **Sai định dạng** (ví dụ `27-11-2026` khi yêu cầu ISO).
2. **Sai giá trị lịch** (ví dụ 29/02 ở năm không nhuận).
3. **Thiếu ngữ cảnh múi giờ** khi nghiệp vụ cần một thời điểm tuyệt đối.

Formatter kiểm tra cú pháp và giá trị ngày giờ theo resolver style; nó không tự quyết định chính sách lịch hẹn, múi giờ hay xử lý DST thay ứng dụng.

## 12. Bất biến, thread safety và giới hạn của mô hình

Các lớp `Instant`, `LocalDate`, `LocalTime` và `LocalDateTime` đều **bất biến và thread-safe** theo hợp đồng API. Phép `plus...` hoặc `with...` tạo giá trị kết quả, không làm đổi đối tượng ban đầu.

```java
import java.time.LocalDate;

LocalDate original = LocalDate.of(2026, 11, 27);
LocalDate next = original.plusDays(1);

System.out.println(original); // 2026-11-27
System.out.println(next);     // 2026-11-28
```

Đây là ưu điểm khi truyền giá trị giữa các tầng ứng dụng. Tuy nhiên, một record/entity chứa `LocalDateTime` vẫn có thể **mutable** nếu chính entity cho phép thay đổi trường hoặc trạng thái liên quan; tính bất biến của giá trị thời gian không tự tạo giao dịch nguyên tử cho toàn hệ thống.

Lưu ý khác:

- Không dùng `==` như một phép so sánh giá trị; dùng `equals` hoặc phương thức so sánh.
- Không đồng bộ trên các value-based instances bằng `synchronized(dateTime)`; dùng cơ chế đồng bộ của ứng dụng.
- Không suy luận từ tên `LocalDateTime` rằng đối tượng có thể tự xác định múi giờ hay xử lý DST.
- Múi giờ thuộc dữ liệu cấu hình nghiệp vụ, không phải luôn thuộc thiết lập mặc định của máy chủ.

## 13. Thiết kế dữ liệu thời gian trong API và database

Chọn kiểu theo **nghĩa của cột dữ liệu**, không chỉ theo kiểu chuỗi đầu vào.

| Dữ liệu nghiệp vụ | Kiểu Java nên cân nhắc | Thông tin cần giữ |
| --- | --- | --- |
| Sự kiện đã xảy ra lúc nào | `Instant` | Mốc tuyệt đối; quy ước precision khi lưu |
| Ngày sinh hoặc ngày nghỉ | `LocalDate` | Ngày lịch, không tự gắn UTC |
| Giờ cửa hàng mở mỗi ngày | `LocalTime` | Giờ trong ngày **và** zone của cửa hàng được quản lý ở nơi khác |
| Lịch họp “09:30 ở New York” | `LocalDateTime` + `ZoneId`, hoặc `ZonedDateTime` | Local time, khu vực và quy tắc DST |
| Thời hạn “sau đúng 90 phút” | `Instant` + `Duration` | Thời gian trôi qua |
| Gia hạn “thêm một tháng lịch” | `LocalDate` + `Period`/`plusMonths` | Quy tắc lịch, điều chỉnh ngày cuối tháng |
| Thời điểm nhận từ API có offset `+07:00` | `OffsetDateTime` hoặc parse thành `Instant` tùy mục tiêu | Offset nguồn nếu cần giữ, instant nếu cần so sánh |

### 13.1. Đừng để tên cột “timestamp” che giấu ngữ nghĩa

Các hệ quản trị dữ liệu có cách khác nhau để xử lý kiểu `DATE`, `TIME`, `TIMESTAMP` và kiểu có/không có múi giờ. Không nên mặc định “cột timestamp trong database” luôn giống `Instant`, hoặc “cột không timezone” luôn an toàn khi cần thời điểm thực tế.

Để tránh hiểu nhầm, cần xác định rõ:

1. Giá trị được lưu là **instant tuyệt đối** hay **ngày giờ địa phương**?
2. Nếu là local time, zone/offset được lưu và kiểm chứng ở đâu?
3. Tầng JDBC/ORM có tự áp dụng múi giờ JVM hoặc database không?
4. Precision lưu được đến giây, mili giây, micro giây hay nano giây?
5. Khi hiển thị cho người dùng khác múi giờ, quy tắc chuyển đổi là gì?
6. Dữ liệu lịch hẹn tương lai có cần giữ *ZoneId* để thích ứng khi quy tắc DST thay đổi không?

Chỉ gọi `toString()` của `LocalDateTime` rồi lưu như “UTC” là sai về mặt ngữ nghĩa: nó không mang thông tin UTC nào cả.

### 13.2. API nhận đầu vào của người dùng

Một mẫu giao tiếp rõ ràng cho lịch hẹn:

```text
localDateTime: "2026-11-27T09:30:00"
zoneId: "Asia/Ho_Chi_Minh"
```

Ứng dụng xác minh tính hợp lệ của zone và quy tắc gap/overlap, rồi tính `Instant` khi cần đặt lịch hoặc ghi audit. Nếu người dùng gửi thời điểm tuyệt đối, có thể nhận chuỗi ISO chứa `Z`/offset tương ứng và dùng kiểu phù hợp để parse.

Nếu yêu cầu hợp đồng chỉ là “ngày”, ví dụ ngày sinh, **đừng buộc client gửi cả một timestamp lúc nửa đêm**.

## 14. Ví dụ Java 27 hoàn chỉnh và có kết quả xác định

Chương trình sau minh họa cả bốn kiểu trong một luồng xử lý: lấy instant từ `Clock.fixed`, nhìn ngày/giờ tại Việt Nam, xây dựng lịch hẹn địa phương, chuyển nó thành instant để lưu và định dạng cho người dùng.

Tạo file `DateTimeTypesDemo.java`:

```java
import java.time.Clock;
import java.time.Instant;
import java.time.LocalDate;
import java.time.LocalDateTime;
import java.time.LocalTime;
import java.time.ZoneId;
import java.time.format.DateTimeFormatter;
import java.util.Locale;

public class DateTimeTypesDemo {

    public static void main(String[] args) {
        ZoneId vietnam = ZoneId.of("Asia/Ho_Chi_Minh");

        Clock clock = Clock.fixed(
                Instant.parse("2026-11-27T03:15:30Z"),
                vietnam
        );

        Instant eventTime = Instant.now(clock);
        LocalDate today = LocalDate.now(clock);
        LocalTime localTime = LocalTime.now(clock);
        LocalDateTime localDateTime = LocalDateTime.now(clock);

        System.out.println("Instant: " + eventTime);
        System.out.println("Date: " + today);
        System.out.println("Time: " + localTime);
        System.out.println("DateTime: " + localDateTime);

        LocalDate appointmentDay = LocalDate.of(2026, 12, 31);
        LocalTime appointmentClock = LocalTime.of(9, 30);

        LocalDateTime appointment =
                LocalDateTime.of(appointmentDay, appointmentClock);

        Instant appointmentInstant = appointment
                .atZone(vietnam)
                .toInstant();

        DateTimeFormatter viewFormat = DateTimeFormatter
                .ofPattern("dd/MM/uuuu HH:mm", Locale.ROOT);

        System.out.println("Appointment: "
                + appointment.format(viewFormat));
        System.out.println("Appointment UTC: " + appointmentInstant);

        LocalDate monthEnd = LocalDate.of(2026, 1, 31)
                .plusMonths(1);
        LocalTime afterMidnight = LocalTime.of(23, 50)
                .plusMinutes(20);

        System.out.println("After month: " + monthEnd);
        System.out.println("After midnight: " + afterMidnight);
    }
}
```

Biên dịch và chạy với JDK 27:

```bash
javac -encoding UTF-8 DateTimeTypesDemo.java
java DateTimeTypesDemo
```

Kết quả:

```text
Instant: 2026-11-27T03:15:30Z
Date: 2026-11-27
Time: 10:15:30
DateTime: 2026-11-27T10:15:30
Appointment: 31/12/2026 09:30
Appointment UTC: 2026-12-31T02:30:00Z
After month: 2026-02-28
After midnight: 00:10
```

Phân tích:

1. `Clock.fixed` giữ thời điểm UTC không đổi, nên kết quả không phụ thuộc lúc thực tế chương trình chạy.
2. Ba kiểu địa phương đọc múi giờ từ clock (`Asia/Ho_Chi_Minh`), cho ra 10:15:30 khi instant là 03:15:30Z.
3. `LocalDate.of(...)` và `LocalTime.of(...)` được ghép thành một `LocalDateTime` cho cuộc hẹn, chưa phải mốc tuyệt đối.
4. `appointment.atZone(vietnam).toInstant()` áp dụng zone và cho mốc cần lưu/so sánh.
5. `DateTimeFormatter` phục vụ hiển thị; không thay đổi đối tượng ngày giờ.
6. `plusMonths(1)` xử lý ngày 31/01 hợp lệ sang 28/02/2026, không cộng cứng 30 ngày.
7. `LocalTime.plusMinutes(20)` tự quay về 00:10, vì không giữ thông tin ngày.

Bài demo tránh sử dụng `now()` trực tiếp để kiểm tra đầu ra. Trong production, có thể khởi tạo `Clock.system(zone)` và truyền nó vào những thành phần cần thời gian hiện tại.

## 15. Lỗi thường gặp và cách sửa

| Lỗi hoặc giả định | Hậu quả | Cách xử lý |
| --- | --- | --- |
| Dùng `LocalDateTime` làm timestamp UTC mà không lưu zone/offset | Không xác định được instant thực tế | Dùng `Instant` cho sự kiện, hoặc lưu thông tin múi giờ kèm local time |
| Dùng `Instant` để biểu diễn ngày sinh | Chuyển múi giờ có thể làm đổi ngày | Dùng `LocalDate` |
| Gọi `LocalDateTime.now()` trên server mà bỏ qua zone | Kết quả phụ thuộc cấu hình máy chủ | Truyền `ZoneId`/`Clock` rõ ràng |
| Lấy `LocalTime` rồi cộng qua nửa đêm và suy ra ngày hôm sau | `LocalTime` không chứa ngày | Dùng `LocalDateTime` hoặc kiểu gắn zone |
| Cho rằng mỗi ngày luôn có 24 giờ | Sai khi có DST | Phân biệt `Period.ofDays(1)` với `Duration.ofDays(1)` |
| Cộng 30 ngày khi nghiệp vụ là “thêm một tháng” | Sai ở tháng dài/ngắn và năm nhuận | Dùng `plusMonths(1)`/`Period.ofMonths(1)` |
| Gán `Instant.now()` với độ chính xác nanosecond tuyệt đối | Đồng hồ thực tế có precision/resolution giới hạn | Xác định precision nguồn và schema |
| Nhầm epoch seconds với epoch milliseconds | Lệch thời điểm hàng nghìn lần | Đặt tên/trường đơn vị tường minh, dùng đúng factory method |
| Parse thời điểm có offset như `LocalDateTime` không zone | Mất hoặc đọc sai ngữ nghĩa offset | Dùng `OffsetDateTime`/`Instant` hoặc formatter đúng |
| Dùng `LocalDateTime.atZone(zone)` mà không xét DST | Gap/overlap có thể được giải quyết theo mặc định khác yêu cầu | Kiểm tra `ZoneRules.getValidOffsets(...)` và quy tắc nghiệp vụ |
| Dùng `==` với các kiểu `java.time` | So sánh identity thay vì giá trị | Dùng `equals`, `isBefore`, `isAfter` |
| Dùng `YYYY` để định dạng năm lịch | Week-based year có thể khác ở ranh giới năm | Dùng `uuuu` khi cần proleptic year |
| Tin rằng `DateTimeFormatter` tự xác định zone nghiệp vụ | Formatter chủ yếu xử lý biểu diễn/parse | Lưu/chọn zone đúng trước khi chuyển sang instant |
| Khẳng định mọi chuỗi local đều ứng với một thời điểm | Không đúng ở vùng có DST | Xử lý gap/overlap tường minh |
| Dùng cùng `LocalDateTime` để so thứ tự sự kiện từ nhiều vùng | So sánh local fields, không so actual timeline | Chuyển cả hai sang `Instant` |
| Dùng `System.nanoTime()` làm mốc thời gian lịch | Không có ý nghĩa epoch | Dùng `Instant` cho timestamp; `nanoTime` cho đo elapsed nội bộ khi thích hợp |

## 16. Checklist chọn đúng kiểu thời gian

Trước khi chọn một kiểu dữ liệu thời gian trong Java 27, hãy tự hỏi:

1. **Đang biểu diễn một sự kiện đã xảy ra?** Chọn `Instant` nếu cần một điểm tuyệt đối trên dòng thời gian.
2. **Chỉ là ngày lịch?** Chọn `LocalDate`; đừng thêm giờ/UTC không có trong yêu cầu.
3. **Chỉ là giờ trong ngày?** Chọn `LocalTime` và nhớ nó không theo dõi ngày.
4. **Là ngày và giờ địa phương?** Chọn `LocalDateTime`, nhưng nhận thức rằng chưa thể suy ra instant.
5. **Địa điểm có ý nghĩa không?** Lưu `ZoneId` khu vực (ví dụ `Asia/Ho_Chi_Minh`) nếu lịch trình phụ thuộc quy tắc nơi đó.
6. **Có thể đi qua DST không?** Xử lý gap và overlap trước khi xác nhận lịch hẹn.
7. **Bài toán cần cộng thời gian trôi qua hay khoảng lịch?** Chọn `Duration` hoặc `Period`/các thao tác `plus...` phù hợp.
8. **Dữ liệu lấy từ đồng hồ hệ thống?** Truyền `Clock` nếu cần khả năng kiểm thử và tái lập kết quả.
9. **Dữ liệu đến từ API/database?** Quy định rõ offset/zone, format, precision và epoch unit.
10. **Kết quả cần hiển thị cho người dùng?** Áp dụng múi giờ thích hợp rồi định dạng bằng `DateTimeFormatter`.
11. **Cần so sánh hai sự kiện ở hai vùng khác nhau?** Quy về `Instant` trước khi so sánh.
12. **Giá trị có thể không hợp lệ?** Dùng factory/parse chuẩn, xử lý `DateTimeException` hoặc `DateTimeParseException` và kiểm tra quy tắc nghiệp vụ.

**Tóm tắt:** `Instant` trả lời **khi nào trên dòng thời gian**; `LocalDate` trả lời **ngày nào**; `LocalTime` trả lời **giờ nào trong ngày**; `LocalDateTime` trả lời **ngày giờ nào tại địa phương**, nhưng chưa nói **địa phương ở đâu**. Khi cần chuyển địa phương thành sự kiện tuyệt đối, phải bổ sung thông tin múi giờ và xử lý quy tắc của khu vực.

## 17. Tài liệu chính thức Java SE 27

- [`java.time.Instant` — Java SE 27 API](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/time/Instant.html): mô hình thời điểm, epoch, nanosecond, so sánh và chuyển đổi.
- [`java.time.LocalDate` — Java SE 27 API](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/time/LocalDate.html): ngày theo lịch ISO, tạo giá trị, phép cộng theo lịch.
- [`java.time.LocalTime` — Java SE 27 API](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/time/LocalTime.html): giờ trong ngày, thời gian tới nanosecond, vòng qua nửa đêm.
- [`java.time.LocalDateTime` — Java SE 27 API](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/time/LocalDateTime.html): ngày/giờ địa phương và cách ghép hoặc gắn zone.
- [`java.time.ZoneId` — Java SE 27 API](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/time/ZoneId.html): định danh khu vực và quy tắc múi giờ.
- [`java.time.ZonedDateTime` — Java SE 27 API](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/time/ZonedDateTime.html): chuyển giữa local date-time và timeline, giải quyết DST.
- [`java.time.Clock` — Java SE 27 API](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/time/Clock.html): đồng hồ có thể tiêm vào ứng dụng/test, bao gồm `Clock.fixed`.
- [`java.time.Duration` và `java.time.Period` — Java SE 27 API](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/time/Duration.html): [Period](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/time/Period.html) mô tả khoảng theo lịch.
- [`java.time.format.DateTimeFormatter` — Java SE 27 API](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/time/format/DateTimeFormatter.html): parse, format, ký hiệu pattern và resolver style.
- [`java.time.zone.ZoneRules` — Java SE 27 API](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/time/zone/ZoneRules.html): offset hợp lệ và chuyển tiếp múi giờ.
