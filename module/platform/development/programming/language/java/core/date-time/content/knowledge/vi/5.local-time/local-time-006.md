# LocalTime: Cắt bớt độ chính xác bằng truncatedTo()

Trong `java.time`, `LocalTime` mô tả **giờ trong một ngày** với độ chính xác tới nano giây, ví dụ `14:37:59.987654321`. Có những lúc ta chỉ muốn giữ thông tin đến phút, giờ hoặc mili giây: dùng để gom dữ liệu theo khoảng thời gian, chuẩn hóa đầu vào, hiển thị một độ chi tiết nhất định, hoặc so sánh hai giờ theo cùng mức độ chính xác.

Phương thức `LocalTime.truncatedTo(TemporalUnit unit)` giúp **loại bỏ các thành phần thời gian nhỏ hơn đơn vị được chọn**, tạo ra một `LocalTime` có độ chi tiết phù hợp. Đây là thao tác **cắt bớt**, không phải làm tròn đến đơn vị gần nhất.

Ví dụ:

~~~java
LocalTime time = LocalTime.of(14, 37, 59, 987_654_321);
LocalTime minute = time.truncatedTo(ChronoUnit.MINUTES);
// minute = 14:37, KHÔNG phải 14:38
~~~

## 1. Ý nghĩa chính xác của `truncatedTo()`

Chữ *truncate* trong ngữ cảnh này có nghĩa bỏ phần nhỏ hơn một đơn vị thời gian đã chọn, theo ranh giới tính từ **đầu ngày**.

Với `14:37:59.987654321`:

| Đơn vị giữ lại | `truncatedTo(...)` | Kết quả | Thành phần bị bỏ |
|---|---|---|---|
| Nano giây | `ChronoUnit.NANOS` | `14:37:59.987654321` | Không có |
| Micro giây | `ChronoUnit.MICROS` | `14:37:59.987654` | 321 nano giây cuối |
| Mili giây | `ChronoUnit.MILLIS` | `14:37:59.987` | 654321 nano giây cuối |
| Giây | `ChronoUnit.SECONDS` | `14:37:59` | Toàn bộ phần nano giây |
| Phút | `ChronoUnit.MINUTES` | `14:37` | Giây và phần nano giây |
| Giờ | `ChronoUnit.HOURS` | `14:00` | Phút, giây và nano giây |
| Nửa ngày | `ChronoUnit.HALF_DAYS` | `12:00` | Phần nằm sau mốc 12:00 |
| Ngày | `ChronoUnit.DAYS` | `00:00` | Toàn bộ giờ trong ngày |

Ví dụ `14:37:59` cắt đến phút ra `14:37`, **không nhích lên** thành `14:38` dù có 59 giây. Tương tự, `23:59:59.999999999` cắt đến ngày ra `00:00` **của đồng hồ trong ngày**, không phải 00:00 của ngày hôm sau: `LocalTime` vốn không chứa ngày.

### Phương thức và kiểu tham số

Chữ ký chính:

~~~java
public LocalTime truncatedTo(TemporalUnit unit)
~~~

Trong thực tế, ta thường truyền hằng số từ enum `ChronoUnit`, chẳng hạn `ChronoUnit.MINUTES` hoặc `ChronoUnit.HOURS`. Cần import:

~~~java
import java.time.LocalTime;
import java.time.temporal.ChronoUnit;
~~~

Giá trị trả về là **`LocalTime` mới về mặt giá trị**, với các phần nhỏ hơn đơn vị đã chọn đã được đặt về 0. Vì `LocalTime` là kiểu bất biến (*immutable*), giá trị của đối tượng gốc không bị sửa. Java có thể trả lại cùng tham chiếu khi không cần thay đổi; đừng dựa vào `==` để kiểm tra bằng nhau.

~~~java
LocalTime original = LocalTime.of(9, 12, 45);
LocalTime truncated = original.truncatedTo(ChronoUnit.MINUTES);

// original vẫn là 09:12:45
// truncated là 09:12
~~~

Nếu muốn cập nhật biến, hãy **gán lại kết quả**:

~~~java
original = original.truncatedTo(ChronoUnit.MINUTES);
// original hiện giữ giá trị 09:12
~~~

## 2. Các mức cắt bớt thường gặp

### Cắt đến giây: `ChronoUnit.SECONDS`

~~~java
LocalTime time = LocalTime.of(8, 5, 42, 345_678_901);
LocalTime withoutFraction = time.truncatedTo(ChronoUnit.SECONDS);
// withoutFraction = 08:05:42
~~~

Thao tác này bỏ toàn bộ phần nhỏ hơn giây (`getNano() == 0`), nhưng giữ nguyên giờ, phút và giây.

### Cắt đến mili giây hoặc micro giây

~~~java
LocalTime time = LocalTime.of(8, 5, 42, 345_678_901);
LocalTime millis = time.truncatedTo(ChronoUnit.MILLIS);
// millis = 08:05:42.345

LocalTime micros = time.truncatedTo(ChronoUnit.MICROS);
// micros = 08:05:42.345678
~~~

Một giây có 1.000 mili giây, mỗi mili giây có 1.000 micro giây, mỗi micro giây có 1.000 nano giây. Vì vậy:

- Cắt đến mili giây giữ phần nano trong giây ở bội số của `1_000_000`.
- Cắt đến micro giây giữ phần nano trong giây ở bội số của `1_000`.
- Cắt đến nano giây giữ nguyên độ chính xác tối đa vốn có của `LocalTime`.

`truncatedTo(ChronoUnit.NANOS)` không tạo ra dữ liệu chính xác hơn: nó chỉ giữ nguyên giá trị đang có.

### Cắt đến phút hoặc giờ

~~~java
LocalTime time = LocalTime.of(8, 5, 42, 345_678_901);

LocalTime toMinute = time.truncatedTo(ChronoUnit.MINUTES);
// 08:05

LocalTime toHour = time.truncatedTo(ChronoUnit.HOURS);
// 08:00
~~~

Đây là trường hợp phổ biến khi muốn gom các giờ thành cùng một **mốc phút** hoặc **mốc giờ** trong ngày.

Ví dụ hai thời điểm `08:05:01` và `08:05:59` sau khi cắt đến phút đều trở thành `08:05`. Chúng thuộc cùng một phút trên đồng hồ, dù không phải cùng một thời điểm chính xác.

### Cắt đến nửa ngày hoặc ngày

~~~java
LocalTime time = LocalTime.of(14, 37, 59, 987_654_321);

LocalTime halfDay = time.truncatedTo(ChronoUnit.HALF_DAYS);
// 12:00

LocalTime startOfDay = time.truncatedTo(ChronoUnit.DAYS);
// 00:00
~~~

`HALF_DAYS` chia ngày thành hai khoảng 12 giờ: từ `00:00` đến trước `12:00`, và từ `12:00` đến trước `24:00`. Cắt đến đơn vị này cho ra `00:00` hoặc `12:00`.

`DAYS` luôn đưa `LocalTime` về `00:00`; nó không tạo hoặc trả về `LocalDate`. Phép cắt này chỉ có ích nếu nghiệp vụ thật sự cần giá trị đồng hồ đầu ngày.

## 3. Điều kiện để một đơn vị được chấp nhận

Không phải mọi `TemporalUnit` đều dùng được với `LocalTime.truncatedTo()`. Theo hợp đồng Java, một đơn vị cắt hợp lệ phải có **độ dài không vượt quá một ngày chuẩn và độ dài đó phải chia hết một ngày chuẩn (24 giờ) không dư**, ở độ chính xác nano giây.

Những `ChronoUnit` thông dụng sau đều hợp lệ:

~~~text
NANOS, MICROS, MILLIS, SECONDS, MINUTES, HOURS, HALF_DAYS, DAYS
~~~

Các đơn vị như `ChronoUnit.WEEKS` hoặc `ChronoUnit.MONTHS` **không hợp lệ** cho thao tác này. Một tuần dài hơn 24 giờ; tháng cũng không có độ dài cố định tương ứng một phần nguyên của ngày chuẩn.

~~~java
LocalTime time = LocalTime.NOON;
time.truncatedTo(ChronoUnit.WEEKS);
// Ném java.time.temporal.UnsupportedTemporalTypeException
~~~

Đoạn code là minh họa lỗi, không phải chương trình đầy đủ. `UnsupportedTemporalTypeException` thuộc nhánh `DateTimeException`. Giá trị `null` cho `unit` sẽ gây `NullPointerException`; nên truyền một `ChronoUnit` hợp lệ, rõ ràng.

**Chú ý:** `Duration.ofMinutes(5)` là đối tượng `Duration`, **không phải `TemporalUnit`**. Vì vậy không thể gọi `time.truncatedTo(Duration.ofMinutes(5))`. Khi muốn tạo ranh giới 5 hoặc 15 phút, có thể tính theo phút kể từ nửa đêm, hoặc triển khai một `TemporalUnit` phù hợp; xem ví dụ nhóm 5 phút ở phần áp dụng.

## 4. Ví dụ hoàn chỉnh với Java 17

Tạo tệp **`LocalTimeTruncationDemo.java`**:

~~~java
import java.time.DateTimeException;
import java.time.LocalTime;
import java.time.temporal.ChronoUnit;

public class LocalTimeTruncationDemo {
    public static void main(String[] args) {
        LocalTime original = LocalTime.of(14, 37, 59, 987_654_321);
        System.out.println("original       = " + original);
        System.out.println("nanos          = "
                + original.truncatedTo(ChronoUnit.NANOS));
        System.out.println("micros         = "
                + original.truncatedTo(ChronoUnit.MICROS));
        System.out.println("millis         = "
                + original.truncatedTo(ChronoUnit.MILLIS));
        System.out.println("seconds        = "
                + original.truncatedTo(ChronoUnit.SECONDS));
        System.out.println("minutes        = "
                + original.truncatedTo(ChronoUnit.MINUTES));
        System.out.println("hours          = "
                + original.truncatedTo(ChronoUnit.HOURS));
        System.out.println("half days      = "
                + original.truncatedTo(ChronoUnit.HALF_DAYS));
        System.out.println("days           = "
                + original.truncatedTo(ChronoUnit.DAYS));
        System.out.println("original again = " + original);

        LocalTime nearMidnight = LocalTime.of(23, 59, 59, 999_999_999);
        System.out.println("late minute    = "
                + nearMidnight.truncatedTo(ChronoUnit.MINUTES));
        System.out.println("late day       = "
                + nearMidnight.truncatedTo(ChronoUnit.DAYS));
        System.out.println("already exact  = "
                + LocalTime.of(14, 37).truncatedTo(ChronoUnit.MINUTES));

        try {
            original.truncatedTo(ChronoUnit.WEEKS);
        } catch (DateTimeException exception) {
            System.out.println("weeks rejected = "
                    + exception.getClass().getSimpleName());
        }
    }
}
~~~

Biên dịch và chạy từ thư mục chứa tệp, với JDK 17 trở lên:

~~~bash
javac LocalTimeTruncationDemo.java
java LocalTimeTruncationDemo
~~~

Kết quả thực tế đã kiểm chứng bằng `javac --release 17`:

~~~text
original       = 14:37:59.987654321
nanos          = 14:37:59.987654321
micros         = 14:37:59.987654
millis         = 14:37:59.987
seconds        = 14:37:59
minutes        = 14:37
hours          = 14:00
half days      = 12:00
days           = 00:00
original again = 14:37:59.987654321
late minute    = 23:59
late day       = 00:00
already exact  = 14:37
weeks rejected = UnsupportedTemporalTypeException
~~~

**Diễn giải:**

1. `original` vẫn giữ `14:37:59.987654321` sau mọi phép cắt; đối tượng bất biến.
2. Giảm độ chính xác từ nano sang micro/mili giây chỉ bỏ phần thấp hơn, không làm tròn.
3. Cắt đến phút, giờ hoặc nửa ngày cho các mốc `14:37`, `14:00` và `12:00`.
4. Cắt đến `DAYS` trả `00:00`, kể cả từ giờ sát cuối ngày; không có chuyện tự tăng ngày trong `LocalTime`.
5. Giá trị đã chính xác tới phút `14:37` không bị thay đổi về nội dung.
6. Cắt đến tuần bị từ chối bằng một ngoại lệ thời gian rõ ràng.

## 5. Ứng dụng thực tế

### Gom các giá trị theo từng phút

Giả sử có các giờ lấy từ một thiết bị đo trong **cùng ngày lịch**:

~~~java
LocalTime first = LocalTime.of(10, 25, 3);
LocalTime second = LocalTime.of(10, 25, 58);

LocalTime firstBucket = first.truncatedTo(ChronoUnit.MINUTES);
LocalTime secondBucket = second.truncatedTo(ChronoUnit.MINUTES);

boolean sameMinute = firstBucket.equals(secondBucket); // true
~~~

Đây là phép tạo **khóa nhóm** theo phút trong ngày. Nếu cần nhóm sự kiện thuộc nhiều ngày, khóa chỉ gồm `LocalTime` sẽ khiến `10:25` hôm nay lẫn với `10:25` hôm sau. Khi đó hãy giữ thêm `LocalDate` hoặc làm việc với một kiểu có đủ thông tin ngày/thời điểm.

### Chuẩn hóa giờ hẹn chỉ nhận đến phút

Ví dụ nhập `09:15:42.500` nhưng quy ước lưu giờ hẹn đến phút:

~~~java
LocalTime submitted = LocalTime.of(9, 15, 42, 500_000_000);
LocalTime minutePrecision = submitted.truncatedTo(ChronoUnit.MINUTES);
// minutePrecision = 09:15
~~~

Điều này **chủ động thay đổi giá trị**: phần giây/nano bị bỏ và không thể phục hồi chỉ từ `minutePrecision`. Nếu nghiệp vụ yêu cầu “làm tròn đến phút gần nhất”, đây không phải API phù hợp; cần định nghĩa rõ quy tắc làm tròn (đặc biệt ở `23:59:59`) và xử lý cả ngày khi vượt qua nửa đêm.

### Nhóm theo khoảng 5 phút

`truncatedTo(ChronoUnit.MINUTES)` chỉ làm việc với đơn vị phút, không trực tiếp chỉ định “5 phút”. Vì `LocalTime` nằm trong phạm vi một ngày, có thể tính số giây từ 00:00 để chia khoảng:

~~~java
LocalTime time = LocalTime.of(10, 27, 49);
int secondsPerBucket = 5 * 60;
int startSecond = (time.toSecondOfDay() / secondsPerBucket)
        * secondsPerBucket;
LocalTime bucket = LocalTime.ofSecondOfDay(startSecond);
// bucket = 10:25
~~~

Đây là **đoạn mã minh họa trong một phương thức**, không phải file Java chạy độc lập. Với giờ trong ngày, `toSecondOfDay()` nằm trong khoảng 0–86.399, nên phép chia nguyên giúp tìm ranh giới 5 phút gần nhất **không vượt quá giờ đầu vào**. Phần nano giây đương nhiên bị bỏ. Trường hợp cần nhóm các sự kiện thực vượt nhiều ngày, hãy có thêm thông tin ngày/múi giờ trước khi thiết kế khóa nhóm.

### Cắt giá trị và định dạng hiển thị là hai thao tác khác nhau

Nếu chỉ muốn **hiển thị** `14:37` nhưng vẫn **giữ dữ liệu giây/nano gốc**, dùng định dạng:

~~~java
import java.time.format.DateTimeFormatter;

// Minh họa bên trong phương thức, biến time đã tồn tại:
String displayed = time.format(DateTimeFormatter.ofPattern("HH:mm"));
~~~

Chuỗi kết quả có thể là `14:37` nhưng đối tượng `time` vẫn giữ độ chính xác vốn có. Ngược lại, `truncatedTo(ChronoUnit.MINUTES)` trả về một giá trị thời gian đã bỏ dữ liệu nhỏ hơn phút. Chọn cách nào tùy yêu cầu: **chỉ hiển thị** hay **thay đổi giá trị được xử lý/lưu**.

## 6. Giới hạn quan trọng và lỗi dễ gặp

| Nhầm lẫn | Vì sao sai | Cách đúng |
|---|---|---|
| Nghĩ cắt đến phút là làm tròn gần nhất | `14:37:59` thành `14:37`, không thành `14:38` | Nếu muốn làm tròn, thiết kế phép làm tròn riêng |
| Viết `time.truncatedTo(...)` mà bỏ kết quả | `LocalTime` bất biến; đối tượng gốc không đổi | Gán `LocalTime result = ...` hoặc gán lại biến |
| Dùng `ChronoUnit.MINUTE` hay `ChronoUnit.HOUR` | Các enum hằng là dạng số nhiều | Dùng `ChronoUnit.MINUTES`, `ChronoUnit.HOURS` |
| Gọi `truncatedTo(Duration.ofMinutes(5))` | `Duration` không triển khai `TemporalUnit` | Dùng `ChronoUnit` được hỗ trợ hoặc tính ranh giới nhóm |
| Dùng `WEEKS`/`MONTHS` | Không thỏa giới hạn chia đều một ngày chuẩn | Chỉ truyền đơn vị hợp lệ |
| Tưởng `truncatedTo(DAYS)` chuyển qua ngày hôm sau | `LocalTime` chỉ chứa giờ, kết quả là `00:00` | Nếu quan tâm ngày, dùng kiểu có ngày và áp dụng nghiệp vụ chuyển ngày |
| Dùng `==` để so sánh kết quả | Không nên dựa vào đồng nhất tham chiếu | Dùng `equals(...)` khi so sánh giá trị `LocalTime` |
| Coi `LocalTime` là timestamp thực tế | Không có ngày và vùng múi giờ | Dùng `LocalDateTime`/`ZonedDateTime`/`Instant` đúng ngữ cảnh |
| Chỉ muốn định dạng `HH:mm` mà lại cắt mất dữ liệu | Truncation thay đổi giá trị biểu diễn nội bộ | Dùng `DateTimeFormatter` nếu chỉ cần trình bày |
| Cho rằng cắt giữ được dữ liệu gốc ở kết quả | Phần nhỏ hơn đơn vị được chọn đã mất | Giữ biến `original` nếu còn cần thời gian đầy đủ |

**Giới hạn của ngữ cảnh giờ trong ngày:** `LocalTime` không biết giờ mùa hè (DST), múi giờ hoặc ngày. Thao tác `truncatedTo()` của `LocalTime` chia theo **ngày chuẩn 24 giờ**. Trong thực tế, các ngày tại một số vùng múi giờ có thể dài 23 hoặc 25 giờ do thay đổi đồng hồ; nếu hệ thống nhóm sự kiện theo giờ thực hoặc theo lịch địa phương nhiều ngày, cần lựa chọn `Instant`/`ZonedDateTime` và quy tắc nhóm phù hợp, thay vì chỉ cắt `LocalTime`.

## 7. Câu hỏi tự luyện

1. `LocalTime.of(16, 28, 59).truncatedTo(ChronoUnit.MINUTES)` bằng gì? **`16:28`**, không phải `16:29`.
2. `LocalTime.of(16, 28, 59, 123_456_789).truncatedTo(ChronoUnit.MILLIS)` bằng gì? **`16:28:59.123`**.
3. Cắt `LocalTime.of(23, 59, 59)` đến `DAYS` có tự chuyển sang ngày mai không? **Không**; kết quả `00:00` và không có ngày đi kèm.
4. Cắt đến `HOURS` với `06:45:00` trả gì? **`06:00`**.
5. `LocalTime.of(13, 0).truncatedTo(ChronoUnit.HALF_DAYS)` trả gì? **`12:00`**.
6. Có thể truyền `ChronoUnit.WEEKS` vào `LocalTime.truncatedTo()` không? **Không**, sẽ bị từ chối bởi `UnsupportedTemporalTypeException`.
7. Muốn giữ giờ gốc `10:25:48` nhưng chỉ hiển thị `10:25` nên dùng gì? **`DateTimeFormatter`**; không cần cắt và mất dữ liệu.
8. Hai bản ghi lúc `10:25` ở hai ngày khác nhau có cùng khóa sau khi cắt `LocalTime` đến phút không? **Có**, nên phải thêm **ngày** nếu nghiệp vụ cần phân biệt hai bản ghi.

**Ghi nhớ:** `LocalTime.truncatedTo(ChronoUnit.MINUTES)` cắt giây và nano giây, `truncatedTo(ChronoUnit.HOURS)` cắt cả phút, giây và nano giây; mọi phép cắt đều **không làm tròn** và **không sửa đối tượng gốc**. Chọn đơn vị phù hợp và phân biệt giờ trong ngày với thời điểm có ngày/múi giờ.

### Tài liệu tham khảo

- [Java SE 17 — LocalTime](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/LocalTime.html)
- [Java SE 17 — ChronoUnit](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/temporal/ChronoUnit.html)
- [Java SE 17 — TemporalUnit](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/temporal/TemporalUnit.html)
- [Java SE 17 — DateTimeFormatter](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/format/DateTimeFormatter.html)
