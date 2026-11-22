# Tạo `LocalDateTime` từ các thành phần hoặc từ `LocalDate` và `LocalTime`

Trong Java, một thời điểm trên **đồng hồ địa phương** thường được mô tả bằng ngày, tháng, năm và giờ, phút, giây. Ví dụ một biểu mẫu đặt lịch nhận ngày **29/02/2024**, giờ **14:05:06.123**. Để kết hợp thông tin này thành một đối tượng, dùng `java.time.LocalDateTime`:

```java
LocalDateTime meeting = LocalDateTime.of(2024, 2, 29, 14, 5, 6, 123_000_000);
```

Hoặc, khi đã có riêng đối tượng ngày và giờ:

```java
LocalDate date = LocalDate.of(2024, 2, 29);
LocalTime time = LocalTime.of(14, 5, 6, 123_000_000);
LocalDateTime meeting = LocalDateTime.of(date, time);
```

Các đoạn ngắn trên cần `import java.time.*;` khi đặt trong một phương thức hoặc lớp Java. **Hai cách tạo cho cùng giá trị** `2024-02-29T14:05:06.123`.

Điều cần nhớ ngay từ đầu: `LocalDateTime` chỉ có **ngày và giờ địa phương**, chưa có `ZoneId`, UTC offset hay mốc `Instant`. Đó là điểm khác biệt giữa “14:05 ngày 29/02” và “một sự kiện diễn ra vào một thời điểm duy nhất trên thế giới”.

## 1. Hiểu cấu trúc của `LocalDateTime`

`LocalDateTime` thuộc gói `java.time`, ra đời từ Java 8 và có đầy đủ trong Java 17+. Nó biểu diễn **ngày giờ theo lịch ISO-8601** mà không gắn múi giờ. Có thể hình dung:

```text
LocalDate        2024-02-29
LocalTime        14:05:06.123
                      │
          LocalDateTime.of(date, time)
                      ↓
LocalDateTime    2024-02-29T14:05:06.123
```

Các thành phần có ý nghĩa:

| Thành phần | Ví dụ | Giá trị hợp lệ thường gặp |
| --- | --- | --- |
| Năm (`year`) | `2024` | Giá trị năm hợp lệ theo miền hỗ trợ của lịch ISO trong `java.time`, gồm cả năm âm và năm 0 theo hệ đánh số năm thiên văn. |
| Tháng (`month`) | `2` hoặc `Month.FEBRUARY` | Số 1–12 hoặc một enum `Month`. |
| Ngày trong tháng (`dayOfMonth`) | `29` | Phụ thuộc tháng và năm; tháng 2 năm nhuận có ngày 29. |
| Giờ (`hour`) | `14` | 0–23. |
| Phút (`minute`) | `5` | 0–59. |
| Giây (`second`) | `6` | 0–59. |
| Nano giây (`nanoOfSecond`) | `123_000_000` | 0–999.999.999; 123 triệu ns = 123 ms. |

`LocalDateTime` được thiết kế **bất biến** (*immutable*) và an toàn khi chia sẻ giá trị giữa các luồng: thay đổi ngày, giờ hay cộng thời gian trả về một đối tượng giá trị mới. Khi tạo qua `of(...)`, Java kiểm tra ngày và giờ theo lịch: `2024-02-29` hợp lệ vì 2024 là năm nhuận, còn `2025-02-29` không hợp lệ.

Định dạng chuỗi mặc định dùng chữ `T` giữa ngày và giờ theo ISO-8601, ví dụ `2024-02-29T14:05`. Nếu giây hoặc phần thập phân bằng 0, biểu diễn chuỗi có thể bỏ những phần đó; giá trị vẫn có đầy đủ các trường với số 0.

## 2. Tạo trực tiếp từ các trường bằng `LocalDateTime.of(...)`

Khi dữ liệu bắt đầu từ các số nguyên như năm, tháng, ngày, giờ, phút, cách rõ ràng nhất là một trong các overload sau:

| Overload tiêu biểu | Kiểu/ý nghĩa |
| --- | --- |
| `LocalDateTime.of(year, month, day, hour, minute)` | Tạo từ năm, **tháng kiểu số**, ngày, giờ và phút; giây và nano giây bằng 0. |
| `LocalDateTime.of(year, month, day, hour, minute, second)` | Thêm giây, nano giây bằng 0. |
| `LocalDateTime.of(year, month, day, hour, minute, second, nano)` | Thêm độ chính xác nano giây. |
| `LocalDateTime.of(year, Month.JANUARY, day, hour, minute)` | Dùng `Month` enum thay số tháng. |
| `LocalDateTime.of(year, Month.JANUARY, day, hour, minute, second)` | Enum tháng và giây. |
| `LocalDateTime.of(year, Month.JANUARY, day, hour, minute, second, nano)` | Enum tháng, giây và nano giây. |

Ví dụ (cần `import java.time.*;`):

```java
LocalDateTime a = LocalDateTime.of(2024, 2, 29, 14, 5);
LocalDateTime b = LocalDateTime.of(2024, Month.FEBRUARY, 29, 14, 5);
LocalDateTime c = LocalDateTime.of(2024, 2, 29, 14, 5, 6);
LocalDateTime d = LocalDateTime.of(
        2024, Month.FEBRUARY, 29, 14, 5, 6, 123_000_000
);
```

Giá trị `a` và `b` đều là `2024-02-29T14:05`; `c` là `2024-02-29T14:05:06`, còn `d` là `2024-02-29T14:05:06.123`.

**Khi nên dùng kiểu số:** đầu vào đã có các trường riêng biệt hoặc bạn muốn một ví dụ ngắn, rõ ràng. **Khi nên dùng `Month`:** code có tháng cố định được lập trình sẵn, muốn tránh nhầm số 1–12, chẳng hạn `Month.DECEMBER` rõ nghĩa hơn số `12`. `Month` không dùng số 0 cho tháng 1.

**Ranh giới thời gian:** giờ `24` không hợp lệ trong `LocalDateTime.of(...)`; 00:00 của ngày hôm sau phải viết bằng **ngày hôm sau + giờ 00:00**. Giây `60` cũng không hợp lệ trong API này; đừng kỳ vọng `of(...)` tự xử lý giây nhuận theo cách cho phép nhập 60.

## 3. Tạo từ `LocalDate` và `LocalTime` bằng `of(date, time)`

Khi ứng dụng tách ngày và giờ thành hai dữ liệu độc lập, hãy tạo đúng kiểu cho từng phần rồi ghép:

```java
LocalDate deliveryDate = LocalDate.of(2025, 10, 24);
LocalTime deliveryTime = LocalTime.of(9, 30);
LocalDateTime deliveryAt = LocalDateTime.of(deliveryDate, deliveryTime);
```

Kết quả là `2025-10-24T09:30`. Cách này thường tự nhiên hơn việc tách các thành phần ra thành sáu số khi:

- Biểu mẫu có hai input khác nhau, một để chọn ngày và một để chọn giờ.
- Nghiệp vụ đã có ngày chạy (`LocalDate`) và giờ hằng ngày (`LocalTime`).
- Một lịch lặp sử dụng **cùng giờ địa phương** nhưng thay ngày ở từng lần thực hiện.
- Bạn muốn tái sử dụng logic kiểm tra ngày và logic kiểm tra giờ trước khi ghép.

Phương thức này nhận chính xác đối tượng `LocalDate` và `LocalTime`. Không có việc Java tự chuyển đổi múi giờ, và nó không đọc hệ thống để điền các trường còn thiếu. Vì thế, dùng `LocalDateTime.of(date, time)` khi đã có hai giá trị sẽ cho ý nghĩa trực tiếp, dễ đọc và dễ kiểm thử.

### Các cách viết tương đương

Với `date` và `time` đã hợp lệ, những cách sau cho cùng giá trị ngày giờ:

```java
LocalDate date = LocalDate.of(2024, 2, 29);
LocalTime time = LocalTime.of(14, 5);

LocalDateTime fromOf = LocalDateTime.of(date, time);
LocalDateTime fromDate = date.atTime(time);
LocalDateTime fromTime = time.atDate(date);
```

- `LocalDateTime.of(date, time)` nhấn mạnh việc **tạo đối tượng ngày giờ từ hai thành phần**.
- `date.atTime(time)` nhấn mạnh **ngày có sẵn được gắn thêm giờ**.
- `time.atDate(date)` nhấn mạnh **giờ có sẵn được gắn thêm ngày**.

Ba cách đều tạo `LocalDateTime`, không có cách nào mặc nhiên mang thông tin múi giờ. Chọn cách thể hiện rõ nguồn dữ liệu nhất; không cần đổi qua lại chỉ vì phong cách. Trong một codebase, dùng cách nhất quán sẽ giúp người đọc.

## 4. Ví dụ Java 17+ hoàn chỉnh: so sánh các cách tạo và kiểm tra tính bất biến

Tạo tệp `LocalDateTimeCreationDemo.java` đúng tên public class:

```java
import java.time.*;

public class LocalDateTimeCreationDemo {
    public static void main(String[] args) {
        LocalDate date = LocalDate.of(2024, 2, 29);
        LocalTime time = LocalTime.of(14, 5, 6, 123_000_000);

        LocalDateTime fromObjects = LocalDateTime.of(date, time);
        LocalDateTime fromNumbers =
                LocalDateTime.of(2024, 2, 29, 14, 5, 6, 123_000_000);
        LocalDateTime fromAtTime = date.atTime(time);

        System.out.println("From objects : " + fromObjects);
        System.out.println("From numbers : " + fromNumbers);
        System.out.println("From atTime  : " + fromAtTime);
        System.out.println("All equal    : "
                + (fromObjects.equals(fromNumbers)
                && fromNumbers.equals(fromAtTime)));

        System.out.println("Only hour/min: "
                + LocalDateTime.of(2024, 2, 29, 14, 5));
        System.out.println("Midnight     : " + date.atStartOfDay());

        LocalDateTime next = fromObjects.plusDays(1);
        System.out.println("Original     : " + fromObjects);
        System.out.println("Plus day     : " + next);

        try {
            LocalDateTime.of(2025, 2, 29, 10, 0);
        } catch (DateTimeException e) {
            System.out.println("Invalid date : DateTimeException");
        }
    }
}
```

Biên dịch/chạy với JDK 17 trở lên:

```bash
javac LocalDateTimeCreationDemo.java
java LocalDateTimeCreationDemo
```

Kết quả đã kiểm chứng:

```text
From objects : 2024-02-29T14:05:06.123
From numbers : 2024-02-29T14:05:06.123
From atTime  : 2024-02-29T14:05:06.123
All equal    : true
Only hour/min: 2024-02-29T14:05
Midnight     : 2024-02-29T00:00
Original     : 2024-02-29T14:05:06.123
Plus day     : 2024-03-01T14:05:06.123
Invalid date : DateTimeException
```

**Phân tích:**

1. `fromObjects`, `fromNumbers` và `fromAtTime` bằng nhau theo `equals()` vì cùng chứa ngày, giờ, giây và nano giây.
2. Dùng overload chỉ nhận giờ và phút sẽ tạo giây/nano giây bằng 0. `LocalDateTime.toString()` vì vậy hiển thị `2024-02-29T14:05`; không phải một kiểu dữ liệu thiếu giây.
3. `date.atStartOfDay()` tạo `LocalDateTime` tại nửa đêm **không gắn múi giờ**. Nó tương đương `date.atTime(LocalTime.MIDNIGHT)` về giá trị ngày giờ. Khi cần thời điểm hợp lệ đầu ngày trong một vùng cụ thể, dùng overload `date.atStartOfDay(zone)` với kết quả `ZonedDateTime`.
4. `fromObjects.plusDays(1)` cho ngày 01/03 vì sau 29/02 năm nhuận là 01/03, đồng thời giữ giờ `14:05:06.123`. Biến `fromObjects` giữ nguyên vì đối tượng bất biến.
5. Không thể tạo 29/02/2025 vì 2025 không phải năm nhuận. `LocalDateTime.of(...)` ném `DateTimeException` ngay lúc tạo, thay vì tự chuyển sang ngày 01/03.

Trong code nghiệp vụ, nếu người dùng nhập sai ngày, nên bắt/kiểm tra ngoại lệ tại ranh giới nhận input rồi hiển thị thông báo cụ thể. Không nên che lỗi bằng cách tự làm tròn sang một ngày khác mà người dùng không chọn.

## 5. Kiểm soát độ chính xác của giờ, phút, giây và nano giây

Thành phần thời gian được biểu diễn bằng `LocalTime` nên `LocalDateTime` có cùng độ chi tiết đến **nano giây**. Một số phép tạo:

```java
LocalDateTime minutePrecision =
        LocalDateTime.of(2025, 6, 10, 8, 30);
LocalDateTime secondPrecision =
        LocalDateTime.of(2025, 6, 10, 8, 30, 15);
LocalDateTime millisecondPrecision =
        LocalDateTime.of(2025, 6, 10, 8, 30, 15, 250_000_000);
```

Các giá trị lần lượt là `2025-06-10T08:30`, `2025-06-10T08:30:15` và `2025-06-10T08:30:15.250`. Một mili giây bằng **1.000.000 nano giây**, nên 250 ms là `250_000_000` ns, không phải `250` ns.

Đừng suy từ cách `toString()` rút gọn dấu thập phân rằng kiểu dữ liệu chỉ lưu được mili giây. `LocalDateTime` có độ phân giải biểu diễn tới ns, nhưng điều đó **không có nghĩa** đồng hồ máy tính hoặc cơ sở dữ liệu luôn đo/lưu chính xác 1 ns. `of(...)` chỉ tạo giá trị có các thành phần đã được chỉ định; nó không tự quan sát đồng hồ thật.

## 6. Chuyển các trường nhập trên giao diện thành đối tượng

Trường hợp thường gặp trong ứng dụng: giao diện gửi năm, tháng, ngày và giờ/phút ở các trường riêng. Bạn có thể ánh xạ trực tiếp sau bước xác thực:

```java
int year = 2025;
int month = 10;
int day = 24;
int hour = 9;
int minute = 30;

LocalDateTime appointment =
        LocalDateTime.of(year, month, day, hour, minute);
```

Nếu form cung cấp **chuỗi ngày** và **chuỗi giờ** riêng, phân tích từng chuỗi đúng định dạng rồi ghép:

```java
LocalDate date = LocalDate.parse("2025-10-24");
LocalTime time = LocalTime.parse("09:30");
LocalDateTime appointment = LocalDateTime.of(date, time);
```

Hai đoạn này đặt trong một phương thức có `import java.time.*;` và chưa phải tệp Java độc lập. Dữ liệu chuỗi ở đây dùng ISO-8601. Nếu đầu vào là ngày theo định dạng Việt Nam `24/10/2025`, có thể dùng `DateTimeFormatter` rõ ràng:

```java
DateTimeFormatter formatter =
        DateTimeFormatter.ofPattern("dd/MM/uuuu");
LocalDate date = LocalDate.parse("24/10/2025", formatter);
LocalTime time = LocalTime.parse("09:30");
LocalDateTime appointment = date.atTime(time);
```

Đoạn trên cần `import java.time.format.DateTimeFormatter;` và `import java.time.*;`. `DateTimeFormatter` thuộc một phần riêng về phân tích/định dạng dữ liệu; điều cốt lõi của bài này là **sau khi đã có `LocalDate` và `LocalTime` thì ghép bằng `of(date, time)` hoặc `date.atTime(time)`**.

Việc tách ngày và giờ thành các giá trị có kiểu giúp tránh ghép chuỗi thủ công như `dateText + "T" + timeText` khi còn phải kiểm tra tính hợp lệ của dữ liệu. Nếu form thiếu một trường bắt buộc, hãy yêu cầu người dùng nhập đủ; không nên tự lấy `LocalDate.now()` hoặc `LocalTime.now()` làm mặc định nếu nghiệp vụ chưa cho phép.

## 7. Phân biệt tạo giá trị với lấy “ngày giờ hiện tại”

`LocalDateTime.of(...)` tạo một giá trị **xác định bởi các tham số**; nó không đọc đồng hồ hệ thống. So sánh:

| Cách tạo | Nguồn dữ liệu | Đặc điểm |
| --- | --- | --- |
| `LocalDateTime.of(2025, 10, 24, 9, 30)` | Các trường số được truyền vào | Tạo giá trị cố định, luôn như nhau. |
| `LocalDateTime.of(date, time)` | Hai đối tượng `LocalDate` và `LocalTime` | Ghép ngày/giờ đã biết. |
| `date.atTime(time)` | Ngày đã biết và giờ đã biết | Cách diễn đạt tự nhiên khi khởi đầu từ ngày. |
| `LocalDateTime.parse("2025-10-24T09:30")` | Chuỗi có định dạng hợp lệ | Dùng khi nguồn là văn bản ISO-8601. |
| `LocalDateTime.now()` | Đồng hồ và múi giờ mặc định của hệ thống | Giá trị thay đổi theo thời điểm gọi và môi trường. |
| `LocalDateTime.now(zone)` | Đồng hồ hệ thống trong vùng chỉ định | Giờ địa phương hiện tại, nhưng kết quả vẫn không mang thông tin vùng. |
| `LocalDateTime.now(clock)` | Đồng hồ `Clock` truyền vào | Thuận tiện để kiểm thử với đồng hồ giả lập. |

Khi viết test cho logic ngày giờ, ưu tiên các giá trị tạo bằng `of(...)` hoặc `Clock.fixed(...)` thay vì test phụ thuộc ngày chạy thực. Khi triển khai ứng dụng, chú ý `LocalDateTime.now()` dùng múi giờ mặc định của tiến trình; kết quả có thể khác nhau giữa máy phát triển và container CI.

Đặc biệt, nếu bài toán cần “đơn hàng được tạo **ở mốc thực nào**”, giá trị `Instant.now()` mới trực tiếp thể hiện ý nghĩa sự kiện. `LocalDateTime.now()` mô tả ngày giờ địa phương của hệ thống tại mốc đó nhưng bỏ thông tin vùng trong kết quả.

## 8. Vì sao `LocalDateTime.of(...)` chưa xác định thời điểm UTC?

Tạo ngày giờ bằng các trường hoặc ghép `LocalDate`/`LocalTime` **chưa chọn múi giờ**. Ví dụ `2025-10-24T09:30` ở Việt Nam và `2025-10-24T09:30` tại New York tương ứng những thời điểm khác nhau. Nếu muốn quy đổi thành `Instant`, phải xác định vùng hoặc offset theo yêu cầu nghiệp vụ:

```java
LocalDate date = LocalDate.of(2025, 10, 24);
LocalTime time = LocalTime.of(9, 30);
LocalDateTime localAppointment = LocalDateTime.of(date, time);

ZoneId vietnam = ZoneId.of("Asia/Ho_Chi_Minh");
ZonedDateTime zonedAppointment = localAppointment.atZone(vietnam);
Instant instant = zonedAppointment.toInstant();
```

Đây là đoạn minh họa cần `import java.time.*;`. Trong trường hợp này, kết quả ngày giờ có vùng là `2025-10-24T09:30+07:00[Asia/Ho_Chi_Minh]`, còn `Instant` là `2025-10-24T02:30:00Z`.

**Lưu ý:** `ZoneId` như `America/New_York` chứa quy tắc múi giờ theo vùng, bao gồm DST trong các năm có chuyển đổi; `ZoneOffset` như `-05:00` chỉ nêu một độ lệch cố định. Nếu lên lịch nhiều tháng sau theo giờ địa phương của một thành phố, chọn `ZoneId` phù hợp để áp dụng quy tắc vùng thay vì giả định offset không đổi.

### Giờ địa phương bị khuyết hoặc lặp do DST

Java vẫn có thể tạo `LocalDateTime` từ các trường hợp lệ về lịch mà một vùng nhất định không có thời điểm tương ứng. `of(...)` không biết vùng nào nên không thể tự kết luận thời điểm đó có tồn tại tại nơi đặt lịch.

- **Gap:** tại New York, `2024-03-10T02:30` không tồn tại trong đồng hồ địa phương vì chuyển sang giờ mùa hè.
- **Overlap:** tại New York, `2024-11-03T01:30` xuất hiện hai lần khi đồng hồ chuyển về giờ chuẩn; một lần theo offset `-04:00`, lần sau theo `-05:00`.

Dưới đây là chương trình kiểm chứng độc lập. Tạo tệp `LocalDateTimeZoneDemo.java`:

```java
import java.time.*;

public class LocalDateTimeZoneDemo {
    public static void main(String[] args) {
        ZoneId zone = ZoneId.of("America/New_York");

        LocalDateTime gap = LocalDateTime.of(2024, 3, 10, 2, 30);
        LocalDateTime overlap = LocalDateTime.of(
                LocalDate.of(2024, 11, 3),
                LocalTime.of(1, 30)
        );

        System.out.println("Gap local       : " + gap);
        System.out.println("Gap offsets     : "
                + zone.getRules().getValidOffsets(gap));
        System.out.println("Gap resolved    : " + gap.atZone(zone));
        System.out.println("Overlap local   : " + overlap);
        System.out.println("Overlap offsets : "
                + zone.getRules().getValidOffsets(overlap));
        System.out.println("Earlier instant : "
                + overlap.atZone(zone).toInstant());
        System.out.println("Later instant   : "
                + overlap.atZone(zone).withLaterOffsetAtOverlap().toInstant());
    }
}
```

```bash
javac LocalDateTimeZoneDemo.java
java LocalDateTimeZoneDemo
```

Kết quả đã được chạy và đối chiếu:

```text
Gap local       : 2024-03-10T02:30
Gap offsets     : []
Gap resolved    : 2024-03-10T03:30-04:00[America/New_York]
Overlap local   : 2024-11-03T01:30
Overlap offsets : [-04:00, -05:00]
Earlier instant : 2024-11-03T05:30:00Z
Later instant   : 2024-11-03T06:30:00Z
```

Cả `gap` và `overlap` được tạo thành công bằng `LocalDateTime.of(...)`. Tuy nhiên, `getValidOffsets(gap)` trả danh sách rỗng vì giờ đó **không tồn tại** trong vùng, và `atZone(zone)` mặc định đẩy giờ qua khoảng bị khuyết. Với `overlap` có hai offset hợp lệ, tạo hai `Instant` cách nhau một giờ.

Vì vậy, khi xây dựng lịch hẹn thực hoặc giao dịch theo vùng, sau bước tạo `LocalDateTime` cần thêm **chính sách DST**: từ chối giờ không tồn tại, tự điều chỉnh, hoặc cho người dùng chọn một trong hai lần trùng giờ. Không nên coi `LocalDateTime.of(...)` là phép kiểm tra đầy đủ cho một lịch hẹn có múi giờ.

## 9. Các trường hợp biên và lỗi thường gặp khi tạo

1. **Tháng bắt đầu bằng 1, không phải 0.** `LocalDateTime.of(2025, 0, 1, 9, 0)` là giá trị không hợp lệ, không có tháng 0.
2. **Ngày phải hợp lệ theo tháng và năm.** `LocalDateTime.of(2025, 2, 29, 9, 0)` lỗi; `LocalDateTime.of(2024, 2, 29, 9, 0)` hợp lệ. Java kiểm tra năm nhuận.
3. **Giờ hợp lệ là 0–23, phút/giây 0–59.** `24:00`, `09:60` hoặc giây `60` không được chấp nhận bằng overload số nguyên. Muốn nửa đêm ngày sau, cộng ngày rồi dùng `00:00`.
4. **Nanosecond khác millisecond.** Giá trị `123` cho tham số `nanoOfSecond` chỉ là 123 ns, không phải 123 ms. 123 ms phải viết `123_000_000` ns.
5. **Không ghép `null` thay dữ liệu thiếu.** `LocalDateTime.of(date, null)` sẽ không tạo một giờ mặc định; với các phương thức yêu cầu đối tượng, tham số bắt buộc phải có giá trị thích hợp.
6. **Tạo ngày giờ không tự chuyển múi giờ.** `LocalDateTime.of(...)` không gắn `Asia/Ho_Chi_Minh` chỉ vì ứng dụng chạy tại Việt Nam.
7. **Không dùng `LocalDateTime` như timestamp toàn cầu.** Cùng một giá trị có thể ứng với các `Instant` khác nhau tùy vùng; dùng `Instant` hoặc giá trị có offset/vùng nếu nghiệp vụ yêu cầu thời điểm thực.
8. **Không thay đổi đối tượng đã tạo bằng phép cộng.** `appointment.plusDays(1)` trả đối tượng mới. Muốn lưu kết quả thì gán sang biến mới hoặc gán lại biến hiện tại.
9. **Không ghép các chuỗi tự chế khi API đã có kiểu dữ liệu rõ ràng.** Nếu nguồn có trường số, tạo trực tiếp; nếu nguồn là văn bản, parse đúng định dạng rồi ghép đối tượng.
10. **Kiểm tra múi giờ/DST ở bước áp vùng.** `of(...)` chỉ kiểm tra giá trị lịch/giờ, không biết một thành phố có bỏ hoặc lặp lại thời điểm địa phương đó.
11. **Đầu ngày không phải luôn “24 giờ trước đầu ngày kế tiếp” theo thời gian thực.** `LocalDate.atStartOfDay(zone)` có quy tắc vùng; giữa hai đầu ngày có thể là 23 hoặc 25 giờ qua DST.
12. **Không giả định hệ thống lưu toàn bộ nanosecond.** Khi ghi CSDL hoặc gửi JSON, kiểm tra độ chính xác và định dạng mà thư viện, driver hay hợp đồng API cho phép; có thể phải làm tròn hoặc chuẩn hóa theo quy định nghiệp vụ.

### Xử lý dữ liệu không hợp lệ

Với đầu vào không hợp lệ, `of(...)` ném `DateTimeException` hoặc ngoại lệ con phù hợp. Điều này giúp phát hiện lỗi sớm. Tại tầng giao diện/API, nên xác thực đầu vào và chuyển ngoại lệ thành thông báo như “Ngày 29/02 không tồn tại trong năm 2025”, thay vì trả stack trace cho người dùng.

Nếu trường ngày và trường giờ đến từ các bước độc lập, tạo riêng `LocalDate` và `LocalTime` giúp xác định lỗi ở đúng phần trước khi ghép. Nếu form đã cung cấp số hợp lệ, gọi thẳng `LocalDateTime.of(...)` là đủ rõ ràng.

## 10. Ứng dụng thực tế và bài tập

| Nhiệm vụ | Cách tạo gợi ý | Lý do |
| --- | --- | --- |
| Lịch họp từ dropdown năm/tháng/ngày, giờ/phút | `LocalDateTime.of(year, month, day, hour, minute)` | Đầu vào đang là thành phần số. |
| Giao diện có date picker và time picker | `LocalDateTime.of(date, time)` | Hai thành phần đã là `LocalDate` và `LocalTime`. |
| Ngày đến hạn cố định lúc 17:00 | `dueDate.atTime(17, 0)` | Ngày đã biết, chỉ cần bổ sung giờ. |
| Ca trực bắt đầu từ giờ quen thuộc trong một ngày mới | `shiftTime.atDate(shiftDate)` | Bắt đầu từ một `LocalTime` có sẵn. |
| Nửa đêm một ngày không cần múi giờ | `date.atStartOfDay()` | Trả `LocalDateTime` tại `00:00`. |
| Lịch chạy 09:00 tại New York | `date.atTime(9, 0).atZone(zone)` kèm kiểm tra DST | Phải chọn vùng và quy tắc đổi giờ. |
| Ghi timestamp khi đơn hàng được tạo | `Instant.now()` | Mục tiêu là mốc sự kiện thực, không phải chỉ ngày giờ địa phương. |

**Bài tập 1 — So sánh hai cách tạo.** Tạo `2026-01-15T08:45` bằng `of(int, ...)` và `of(LocalDate, LocalTime)`, sau đó dùng `equals()` để kiểm chứng bằng nhau.

```java
LocalDateTime a = LocalDateTime.of(2026, 1, 15, 8, 45);
LocalDate date = LocalDate.of(2026, 1, 15);
LocalTime time = LocalTime.of(8, 45);
LocalDateTime b = LocalDateTime.of(date, time);
// a.equals(b) == true
```

**Bài tập 2 — Phần giây và nano giây.** `LocalDateTime.of(2026, 1, 15, 8, 45)` có giây/nano giây bằng mấy?

**Đáp án:** Cả hai bằng 0, dù `toString()` thông thường chỉ hiển thị `2026-01-15T08:45`.

**Bài tập 3 — Hẹn ở ngày nhuận.** `2024-02-29T23:30` cộng một ngày bằng gì? Có sửa đối tượng ban đầu không?

**Đáp án:** `2024-03-01T23:30`. Phép `plusDays(1)` trả đối tượng mới; đối tượng cũ không đổi.

**Bài tập 4 — Thời điểm thực.** Một lịch hẹn có `LocalDateTime.of(2025, 10, 24, 9, 30)`. Có thể kết luận đó là `2025-10-24T09:30Z` không?

**Đáp án:** Không. Cần biết offset hoặc `ZoneId`. 09:30 ở Việt Nam vào ngày đó tương ứng `02:30Z`, còn 09:30 ở vùng khác có thể tương ứng một `Instant` khác.

**Bài tập 5 — Giá trị giờ trùng.** Có phải `LocalDateTime.of(2024, 11, 3, 1, 30)` tại New York luôn chỉ một thời điểm?

**Đáp án:** Không. Vào ngày kết thúc DST, 01:30 có thể xuất hiện hai lần, dẫn tới hai `Instant` khác nhau nếu chọn offset khác nhau.

## Ghi nhớ

`LocalDateTime.of(year, month, day, hour, minute, ...)` dùng khi bạn **đã có các số thành phần**; `LocalDateTime.of(date, time)` dùng khi bạn **đã có `LocalDate` và `LocalTime`**. `date.atTime(time)` và `time.atDate(date)` là các cách diễn đạt thuận tiện, tạo cùng kiểu kết quả. Trong cả các cách trên, Java kiểm tra giá trị lịch/giờ hợp lệ và trả đối tượng bất biến; **không phương thức nào tự cấp múi giờ hoặc xác định một `Instant`**. Chọn `ZoneId`/offset và chính sách DST ở bước nghiệp vụ cần xác định thời điểm thực.
