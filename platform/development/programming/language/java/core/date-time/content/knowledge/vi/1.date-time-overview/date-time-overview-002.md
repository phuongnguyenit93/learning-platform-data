# Phân biệt ngày, giờ địa phương, thời điểm và khoảng thời gian trong Java

Khi lập trình xử lý ngày giờ, câu hỏi đầu tiên không phải là “dùng kiểu dữ liệu nào?” mà là **giá trị đang mô tả điều gì**: một ngày trên lịch, một giờ trên đồng hồ, một thời điểm xác định trên dòng thời gian, hay một độ dài/khoảng cách giữa các mốc? Java 8 trở lên cung cấp các kiểu bất biến trong `java.time` để biểu diễn riêng những khái niệm đó. Phân biệt đúng giúp tránh lỗi múi giờ, giờ mùa hè (DST), lịch hẹn, ngày hết hạn và tính thời lượng.

## 1. Bản đồ các khái niệm

| Khái niệm | Kiểu Java | Có ngày? | Có giờ? | Có múi giờ/offset? | Ý nghĩa và ví dụ |
| --- | --- | --- | --- | --- | --- |
| Ngày địa phương | `LocalDate` | Có | Không | Không | Ngày sinh `2025-01-15`, không phải một thời điểm. |
| Giờ địa phương | `LocalTime` | Không | Có | Không | Giờ mở cửa `09:30`, chưa gắn với ngày hay nơi. |
| Ngày và giờ địa phương | `LocalDateTime` | Có | Có | Không | “15/01/2025 lúc 09:30”; chưa đủ để biết thời điểm toàn cầu. |
| Thời điểm tuyệt đối | `Instant` | Dòng thời gian | Dòng thời gian | Ngầm tham chiếu UTC | Mốc duy nhất: `2025-01-15T02:30:00Z`. |
| Ngày giờ có múi giờ vùng | `ZonedDateTime` | Có | Có | `ZoneId`, quy tắc DST | Lịch hẹn `09:30 Asia/Ho_Chi_Minh`. |
| Ngày giờ có UTC offset | `OffsetDateTime` | Có | Có | Offset cố định như `+07:00` | Dữ liệu có ghi rõ độ lệch UTC tại mốc đó. |
| Thời lượng theo giây | `Duration` | Không theo lịch | Độ dài tính bằng giây/nano | Không | Timeout 90 phút, khoảng cách giữa hai `Instant`. |
| Khoảng theo đơn vị lịch | `Period` | Năm, tháng, ngày | Không | Không | Cộng 1 tháng hợp đồng, 10 ngày theo lịch. |

**Quy tắc nhớ:** `Local*` diễn tả lịch/đồng hồ **mà chưa chọn múi giờ**; `Instant` diễn tả **một mốc trên dòng thời gian**; `Duration` là **bao lâu theo thời gian trôi**; `Period` là **bao nhiêu đơn vị lịch**. `ZonedDateTime` là cầu nối giữa “giờ ở một nơi” và “thời điểm thực”.

Một giá trị `LocalDateTime` có thể tương ứng với nhiều `Instant` ở các vùng khác nhau; tại vùng có DST, một giờ địa phương thậm chí có thể **không tồn tại** hoặc **xảy ra hai lần**.

## 2. Ngày và giờ địa phương: `LocalDate`, `LocalTime`, `LocalDateTime`

### `LocalDate`: ngày trên lịch, không có giờ

`LocalDate.of(2025, 1, 15)` chỉ cho biết ngày 15 tháng 1 năm 2025 theo lịch ISO-8601; không xác định lúc bắt đầu ngày đó theo UTC. Dùng cho ngày sinh, ngày nghỉ, ngày lập hóa đơn, ngày đến hạn theo lịch. Các thao tác `plusDays`, `plusMonths`, `isBefore`, `getDayOfWeek` hoạt động theo lịch.

Ví dụ, `LocalDate.of(2024, 1, 31).plusMonths(1)` trả `2024-02-29`: lịch tự điều chỉnh sang ngày hợp lệ cuối cùng của tháng 2 năm nhuận. Giá trị này không diễn đạt “sau đúng 30 hoặc 31 ngày”.

### `LocalTime`: giờ trên đồng hồ, không có ngày

`LocalTime.of(9, 30)` là 09:30. Nó phù hợp cho giờ mở cửa hằng ngày, mốc bắt đầu ca hay thời gian biểu trong một ngày. `LocalTime` **không mang thông tin ngày hoặc vùng**, nên không thể tự suy ra thời điểm thực. Việc cộng giờ có thể vòng qua nửa đêm: `LocalTime.of(23, 30).plusHours(2)` thành `01:30`, nhưng không cho biết là ngày hôm sau.

### `LocalDateTime`: ngày + giờ trên đồng hồ, chưa có vùng

`LocalDateTime.of(2025, 1, 15, 9, 30)` ghép ngày và giờ địa phương. Nó phù hợp để lưu một lịch hẹn **theo giờ tường** khi vùng sẽ được chọn sau. Tuy nhiên, không được hiểu `LocalDateTime` là giờ UTC, giờ máy chủ hay một `timestamp` toàn cầu.

Ví dụ `2025-01-15T09:30` ở Việt Nam tương ứng `02:30Z`, còn ở Tokyo tương ứng `00:30Z`. Chỉ số trên đồng hồ giống nhau, nhưng hai sự kiện lệch nhau hai giờ.

## 3. `Instant`, múi giờ và cách nối hai mô hình

`Instant` đánh dấu một điểm trên trục thời gian, thường hiển thị dạng ISO-8601 kết thúc bằng `Z` (UTC), ví dụ `2025-01-15T02:30:00Z`. Hai người ở hai múi giờ có thể nhìn thấy giờ địa phương khác nhau của cùng `Instant`, nhưng sự kiện chỉ có **một thời điểm**. Dùng `Instant` cho log, thời điểm tạo đơn hàng, thời điểm bắt đầu/kết thúc, đo mốc sự kiện hoặc truyền thời gian giữa các hệ thống.

`ZoneId` như `Asia/Ho_Chi_Minh`, `Asia/Tokyo`, `America/New_York` mô tả **vùng với quy tắc offset lịch sử, hiện tại và quy tắc áp dụng theo dữ liệu múi giờ**. `ZoneOffset` như `+07:00` chỉ là **độ lệch cố định** tại một thời điểm; nó không chứa lịch chuyển DST của một khu vực. Đừng dùng `+07:00` để thay thế một `ZoneId` nếu nghiệp vụ là lịch hẹn lặp lại theo giờ địa phương của một vùng có thể đổi offset.

- `local.atZone(zone)` diễn giải giờ địa phương trong vùng đã chọn và tạo `ZonedDateTime`; tại giờ DST bất thường phải có chính sách xử lý.
- `zoned.toInstant()` lấy mốc trên dòng thời gian; `instant.atZone(zone)` hiển thị **cùng mốc** dưới đồng hồ của vùng đó.
- `zoned.withZoneSameInstant(otherZone)` giữ nguyên sự kiện, đổi cách hiển thị; `withZoneSameLocal(otherZone)` giữ nguyên chữ số ngày/giờ, vì vậy thường **đổi sự kiện thực**.
- `OffsetDateTime` chứa ngày giờ và offset, đủ để suy ra một `Instant`, nhưng không giữ đầy đủ thông tin quy tắc của `ZoneId`.

### Ví dụ Java 17+: cùng một lịch hẹn nhìn từ Việt Nam và Nhật Bản

Lưu tệp `DateTimeKindsDemo.java`:

```java
import java.time.*;

public class DateTimeKindsDemo {
    public static void main(String[] args) {
        LocalDate date = LocalDate.of(2025, 1, 15);
        LocalTime time = LocalTime.of(9, 30);
        LocalDateTime meeting = LocalDateTime.of(date, time);

        ZoneId vietnam = ZoneId.of("Asia/Ho_Chi_Minh");
        ZonedDateTime vietnamMeeting = meeting.atZone(vietnam);
        Instant moment = vietnamMeeting.toInstant();
        ZonedDateTime tokyoView = moment.atZone(ZoneId.of("Asia/Tokyo"));

        Duration elapsed = Duration.ofMinutes(90);
        Period calendarGap = Period.between(date, date.plusDays(10));

        System.out.println("LocalDate       : " + date);
        System.out.println("LocalTime       : " + time);
        System.out.println("LocalDateTime   : " + meeting);
        System.out.println("ZonedDateTime   : " + vietnamMeeting);
        System.out.println("Instant         : " + moment);
        System.out.println("Tokyo           : " + tokyoView);
        System.out.println("Duration        : " + elapsed);
        System.out.println("Period          : " + calendarGap);
    }
}
```

Biên dịch và chạy với JDK 17 trở lên:

```bash
javac DateTimeKindsDemo.java
java DateTimeKindsDemo
```

Kết quả (dùng ngày lịch sử, vùng tường minh nên không phụ thuộc múi giờ mặc định của máy):

```text
LocalDate       : 2025-01-15
LocalTime       : 09:30
LocalDateTime   : 2025-01-15T09:30
ZonedDateTime   : 2025-01-15T09:30+07:00[Asia/Ho_Chi_Minh]
Instant         : 2025-01-15T02:30:00Z
Tokyo           : 2025-01-15T11:30+09:00[Asia/Tokyo]
Duration        : PT1H30M
Period          : P10D
```

Điểm cần hiểu: `09:30` tại Việt Nam và `11:30` tại Nhật trong ví dụ là **cùng một `Instant`**, không phải hai lịch hẹn. `Duration` 90 phút in theo ISO-8601 là `PT1H30M`; `Period` 10 ngày lịch là `P10D`. Cả hai dùng chữ “khoảng” nhưng mang đơn vị và phép tính khác nhau.

## 4. `Duration` và `Period`: hai kiểu khoảng khác bản chất

### `Duration`: thời gian trôi thực, độ chính xác đến nano giây

`Duration` chứa số giây và nano giây. `Duration.ofHours(24)` luôn biểu diễn 86.400 giây; `Duration.ofMinutes(90)` là 5.400 giây. Có thể tính bằng `Duration.between(startInstant, endInstant)`, sử dụng `toMinutes()`, `toHours()`, `isNegative()`, `plus`... Dùng cho timeout, SLA, thời gian chạy tác vụ, độ trễ hoặc chênh lệch giữa **hai thời điểm đã xác định**.

Ví dụ `Duration.between(Instant.parse("2025-01-15T02:30:00Z"), Instant.parse("2025-01-15T04:00:00Z"))` cho `PT1H30M`. Nếu đầu sau nhỏ hơn đầu trước, kết quả có thể âm. Khi đo hiệu năng thực thi ngắn trên JVM, nên dùng `System.nanoTime()` cho khoảng thời gian đơn điệu, không phụ thuộc chỉnh đồng hồ hệ thống; `Instant.now()` dành cho timestamp trên lịch thực.

### `Period`: lượng năm, tháng, ngày trên lịch

`Period.ofYears(1)`, `Period.ofMonths(1)`, `Period.ofDays(1)` mô tả bước dịch theo lịch ISO, không quy đổi cố định ra giây. Các tháng có 28–31 ngày; một ngày địa phương qua thời điểm chuyển DST có thể có 23 hoặc 25 giờ. `Period.between(startDate, endDate)` trả khoảng **theo thành phần năm/tháng/ngày**, trong khi `ChronoUnit.DAYS.between(startDate, endDate)` trả số ngày lịch giữa hai ngày.

Ví dụ với `LocalDate.of(2024, 1, 31)`:
- `plus(Period.ofMonths(1))` thành `2024-02-29`;
- `plusDays(30)` thành `2024-03-01`.

Hai phép tính không tương đương. Dùng `Period` cho chu kỳ gia hạn theo lịch, tuổi theo năm/tháng/ngày hoặc quy tắc “ngày này tháng sau”. Quy tắc nghiệp vụ có thể yêu cầu chính sách riêng cho ngày 29–31, ví dụ ngày đến hạn cuối tháng.

### Một ngày trên lịch không nhất thiết là 24 giờ

Ngày 10/03/2024 tại New York chuyển từ giờ chuẩn sang giờ mùa hè. Ví dụ tiếp theo dùng ngày đã biết và vùng cụ thể để thấy rõ sự khác biệt.

Lưu tệp `CalendarVsElapsedDemo.java`:

```java
import java.time.*;

public class CalendarVsElapsedDemo {
    public static void main(String[] args) {
        ZoneId zone = ZoneId.of("America/New_York");
        ZonedDateTime start = ZonedDateTime.of(2024, 3, 9, 12, 0, 0, 0, zone);

        ZonedDateTime nextCalendarDay = start.plus(Period.ofDays(1));
        ZonedDateTime after24Hours = start.plus(Duration.ofHours(24));

        System.out.println("Start            : " + start);
        System.out.println("Plus 1 day       : " + nextCalendarDay);
        System.out.println("Elapsed to day   : "
                + Duration.between(start, nextCalendarDay).toHours() + " hours");
        System.out.println("Plus 24 hours    : " + after24Hours);
        System.out.println("Elapsed to 24h   : "
                + Duration.between(start, after24Hours).toHours() + " hours");
    }
}
```

```bash
javac CalendarVsElapsedDemo.java
java CalendarVsElapsedDemo
```

```text
Start            : 2024-03-09T12:00-05:00[America/New_York]
Plus 1 day       : 2024-03-10T12:00-04:00[America/New_York]
Elapsed to day   : 23 hours
Plus 24 hours    : 2024-03-10T13:00-04:00[America/New_York]
Elapsed to 24h   : 24 hours
```

`Period.ofDays(1)` giữ mục tiêu **12:00 ngày hôm sau theo lịch địa phương**; `Duration.ofHours(24)` bảo đảm **đúng 24 giờ trôi trên dòng thời gian**. Kết quả khác nhau vì đồng hồ tại vùng này tiến thêm một giờ khi bắt đầu DST. Ở lần kết thúc DST, một ngày có thể dài 25 giờ.

## 5. Giờ địa phương bất thường trong vùng có DST

Không phải mọi `LocalDateTime` đều ánh xạ thành đúng một thời điểm của một `ZoneId`:

1. **Giờ bị khuyết (gap):** đồng hồ nhảy từ 01:59 sang 03:00; các giá trị 02:00–02:59 không tồn tại trong vùng vào ngày đó. Ví dụ `2024-03-10T02:30` tại `America/New_York`.
2. **Giờ bị lặp (overlap):** khi đồng hồ quay lại, một giá trị như `2024-11-03T01:30` tại New York tương ứng **hai offset và hai thời điểm khác nhau**.
3. **Giờ bình thường:** có đúng một offset hợp lệ.

Mặc định, `LocalDateTime.atZone(zone)` điều chỉnh giờ bị khuyết tiến qua gap và thường chọn offset sớm hơn trong trường hợp giờ lặp. Cách đó tiện để xử lý thông thường, nhưng hệ thống đặt lịch, trả lương hoặc giao dịch phải **chủ động định nghĩa chính sách**: từ chối giờ không tồn tại, hỏi người dùng chọn lần đầu/lần sau, hay tự chuyển đến giờ hợp lệ. Có thể kiểm tra bằng `zone.getRules().getValidOffsets(local)`: danh sách có 0, 1 hoặc 2 offset tương ứng gap, bình thường hoặc overlap; `ZonedDateTime.ofStrict(local, chosenOffset, zone)` từ chối cặp giờ/offset không hợp lệ.

Điều này giải thích vì sao lưu một `LocalDateTime` trần cho sự kiện toàn cầu là thiếu thông tin. Để diễn đạt lịch hẹn sắp tới theo giờ một thành phố, cần lưu **giờ địa phương mong muốn + `ZoneId` + chính sách DST**; sau khi xác định mốc cụ thể có thể lưu thêm `Instant` để đối chiếu. Quy tắc múi giờ trong cơ sở dữ liệu tzdb có thể được cập nhật trong tương lai, đặc biệt với lịch hẹn nhiều tháng/năm sau.

## 6. So sánh, tính toán và chuyển đổi đúng kiểu

- So sánh **ngày**: `LocalDate.isBefore(other)`, `isAfter` hoặc `equals`. Không có nghĩa so hai timestamp.
- So sánh **thời điểm**: `Instant.isBefore(other)`, `Duration.between(a, b)`. Hai `ZonedDateTime` có thể hiển thị khác ngày/giờ nhưng vẫn chỉ một `Instant`; muốn kiểm tra cùng sự kiện, so sánh `toInstant()`.
- Tính **số ngày lịch**: `ChronoUnit.DAYS.between(date1, date2)` với `LocalDate`; tính tuổi có thể dùng `Period.between(birthDate, today)`. Không chia số mili giây cho 86.400.000 để tính ngày lịch xuyên múi giờ/DST.
- Tính **thời gian trôi**: chuyển hai mốc đã định về `Instant`, rồi dùng `Duration.between`. Tránh tự trừ phần `hour` hoặc `minute` vì sai qua ngày và DST.
- Chuyển **giờ địa phương thành thời điểm**: phải cung cấp `ZoneId` (hoặc offset phù hợp) và xử lý DST. Đừng gán bừa UTC hoặc dùng múi giờ mặc định môi trường.
- Chuyển **thời điểm thành ngày địa phương**: `instant.atZone(zone).toLocalDate()` hoặc `instant.atZone(zone).toLocalDateTime()`. Cùng `Instant` có thể rơi vào **hai ngày khác nhau** tùy vùng.
- `LocalDate.atStartOfDay(zone)` lấy đầu ngày hợp lệ trong vùng; tại một số biến động múi giờ, thời điểm hợp lệ đầu tiên có thể không trùng 00:00.

Các kiểu của `java.time` là **bất biến**: `date.plusDays(1)` trả đối tượng mới, không sửa `date`. Muốn thay đổi giá trị biến thì cần gán lại.

## 7. Chọn kiểu dữ liệu theo yêu cầu thực tế

| Yêu cầu | Kiểu nên dùng | Lý do |
| --- | --- | --- |
| Ngày sinh, ngày nghỉ lễ, ngày chốt công | `LocalDate` | Là ngày trên lịch, không có thời điểm UTC cố hữu. |
| Giờ quán mở cửa mỗi ngày | `LocalTime` + `ZoneId` của cơ sở | Lịch lặp theo giờ địa phương; cần vùng khi lập mốc thực. |
| Biểu mẫu người dùng chọn “ngày X lúc Y” | `LocalDateTime` + vùng do người dùng/chính sách chọn | Chưa đủ thông tin nếu thiếu vùng và quy tắc DST. |
| Gửi lịch họp xuyên quốc gia | `ZonedDateTime` khi nhận lịch, `Instant` để đồng bộ mốc | Mỗi người xem cùng sự kiện theo múi giờ riêng. |
| Timestamp tạo bản ghi, log, thời điểm giao dịch | `Instant` | Một mốc toàn cầu; chuyển sang vùng khi hiển thị. |
| API trả thời điểm kèm độ lệch UTC | `OffsetDateTime` hoặc chuỗi ISO-8601 có offset | Offset xác định mốc, nhưng không nêu đầy đủ quy tắc vùng. |
| Timeout mạng, cache TTL 15 phút | `Duration` | Số giây/phút trôi thực. |
| Hợp đồng sau 1 tháng, hạn theo 7 ngày lịch | `Period`/`LocalDate.plus...` | Tính theo lịch thay vì số giây. |
| Tính số ngày giữa hai ngày | `ChronoUnit.DAYS.between(LocalDate, LocalDate)` | Khoảng cách ngày lịch là một số nguyên. |

**Đầu vào/đầu ra:** định dạng ISO-8601 thường giúp trao đổi ổn định: `LocalDate.parse("2025-01-15")`, `LocalDateTime.parse("2025-01-15T09:30")`, `Instant.parse("2025-01-15T02:30:00Z")`. Chuỗi `2025-01-15T09:30` không có vùng/offset; nếu cần một timestamp có nghĩa toàn cầu, hãy truyền kèm offset hoặc vùng theo hợp đồng API. Việc ánh xạ Java sang kiểu `DATE`, `TIME`, `TIMESTAMP` của CSDL phụ thuộc driver và hệ quản trị; phải xác minh quy tắc xử lý múi giờ khi đọc/ghi.

**Đồng hồ hệ thống và kiểm thử:** `LocalDate.now()`, `Instant.now()` lấy đồng hồ/múi giờ mặc định tùy overload. Với code cần kiểm thử tái lập, truyền `Clock` và vùng tường minh: `Clock.fixed(Instant.parse("2025-01-15T02:30:00Z"), ZoneId.of("UTC"))`, rồi gọi `Instant.now(clock)`, `LocalDate.now(clock)`. Không viết test phụ thuộc vào ngày thực tế hay múi giờ máy CI.

## 8. Lỗi phổ biến cần tránh

1. **Gọi `LocalDateTime.now()` rồi coi là UTC:** hàm lấy ngày giờ theo vùng mặc định của đồng hồ; kiểu trả về không giữ vùng. Nếu cần mốc hiện tại, dùng `Instant.now()`.
2. **Coi `LocalDateTime` là thời điểm toàn cầu:** cùng chữ số ngày giờ tại hai nơi khác nhau là hai `Instant` khác nhau.
3. **Dùng offset cố định thay vùng IANA cho lịch tương lai:** `-05:00` không mô tả việc New York có thể chuyển sang `-04:00`.
4. **Coi `Period.ofDays(1)` bằng `Duration.ofHours(24)`:** sai khi vùng đổi giờ mùa hè.
5. **Trừ hai `LocalTime` để tính ca qua nửa đêm:** thiếu ngày bắt đầu/kết thúc và quy tắc vùng.
6. **Lưu hoặc parse ngày giờ không ghi rõ ý nghĩa:** chuỗi `15/01/2025 09:30` không chứa đủ thông tin để đồng bộ quốc tế; phải xác định định dạng, vùng và mô hình nghiệp vụ.
7. **Dùng múi giờ mặc định ngầm:** cùng code có thể chạy khác khi đổi cấu hình máy chủ hoặc container. Hãy truyền `ZoneId` tường minh tại các ranh giới nghiệp vụ.
8. **Quên phép cộng trên kiểu bất biến:** `date.plusDays(1)` không thay đổi `date` nếu bỏ qua giá trị trả về.
9. **Tính timeout bằng timestamp tường:** chỉnh giờ NTP/hệ thống có thể làm chênh lệch bị nhảy; dùng nguồn thời gian đơn điệu cho phép đo thời gian thực thi.
10. **Bỏ qua trường hợp giờ lặp/khuyết do DST:** cần chính sách nhất quán, nhất là lịch chạy tác vụ, giao dịch và tính công.

## 9. Tự kiểm tra cách hiểu

- “Sinh ngày 15/01/2025”: `LocalDate`, bởi ngày sinh không cần gắn UTC.
- “Mỗi ngày 08:00 tại New York”: `LocalTime` + `ZoneId` + quy tắc DST; mỗi lần lập lịch tạo một `ZonedDateTime` và `Instant` tương ứng.
- “Đơn hàng được xác nhận đúng lúc nào?”: `Instant`; khi hiển thị dùng vùng của người xem.
- “Tác vụ phải hết hạn sau đúng 90 phút”: `Duration.ofMinutes(90)`.
- “Đến hạn vào cùng ngày tháng sau”: `LocalDate.plusMonths(1)` hoặc `Period.ofMonths(1)`, cộng với quy tắc ngày cuối tháng của nghiệp vụ.
- “2024-03-10 12:00 ở New York có cách 2024-03-09 12:00 đúng 24 giờ?”: Không; ví dụ DST phía trên cho **23 giờ**.

Chọn kiểu theo ý nghĩa nghiệp vụ **trước** khi parse, lưu DB hay format cho UI. Khi cần định danh sự kiện thực, hãy đi qua `Instant`; khi lịch là trọng tâm, giữ ngày/giờ địa phương và `ZoneId`; khi tính khoảng, phân biệt thời gian trôi (`Duration`) và đơn vị lịch (`Period`).