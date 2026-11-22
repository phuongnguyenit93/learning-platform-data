# Tạo Duration từ giây, phút, giờ, ngày 24 giờ và chuỗi ISO-8601

`Duration` trong `java.time` biểu diễn **một khoảng thời gian theo giây và nano giây**, chẳng hạn 90 giây, 2 giờ hoặc 1 ngày danh nghĩa 24 giờ. Bạn có thể tạo nó từ các đơn vị số bằng `Duration.ofSeconds`, `ofMinutes`, `ofHours`, `ofDays` hoặc parse một chuỗi theo định dạng ISO-8601 bằng `Duration.parse`.

Điểm quan trọng: **`Duration.ofDays(1)` luôn có nghĩa 24 giờ (86.400 giây)**. Nó không có nghĩa “đi tới cùng giờ vào ngày lịch kế tiếp ở một múi giờ bất kỳ”; khi có DST, một ngày trên lịch địa phương có thể dài 23 hoặc 25 giờ thực. Vì vậy, hãy phân biệt **thời lượng cố định** với **khoảng cách ngày theo lịch**.

## 1. Duration biểu diễn điều gì?

`Duration` là kiểu dữ liệu bất biến (*immutable*) để biểu diễn độ dài trên trục thời gian. Giá trị được chuẩn hóa thành phần **giây** và **nano giây phụ**; tổng nano giây của toàn bộ khoảng có thể vượt xa một giây hoặc một ngày.

Một số ví dụ:

| Ý nghĩa | Cách tạo | Giá trị được biểu diễn |
| --- | --- | --- |
| 90 giây | `Duration.ofSeconds(90)` | 1 phút 30 giây |
| 15 phút | `Duration.ofMinutes(15)` | 900 giây |
| 2 giờ | `Duration.ofHours(2)` | 7.200 giây |
| 1 ngày 24 giờ | `Duration.ofDays(1)` | 86.400 giây |
| 3,25 giây | `Duration.ofSeconds(3, 250_000_000)` | 3 giây + 250 triệu nano giây |
| Không có thời lượng | `Duration.ZERO` | 0 giây |

`Duration` phù hợp khi cần đo hoặc cộng một khoảng thời gian xác định: thời gian chờ, timeout, khoảng cách giữa hai `Instant`, độ dài một lần chạy tác vụ hoặc “sau đúng 30 phút”.

Nó **không** tự chứa mốc bắt đầu/kết thúc, ngày lịch hoặc múi giờ. `Duration.ofHours(2)` nói “2 giờ” nhưng chưa chỉ ra 2 giờ đó bắt đầu khi nào.

## 2. Tạo từ giây, phút, giờ và ngày

### 2.1. Các factory method cơ bản

```java
import java.time.Duration;

Duration seconds = Duration.ofSeconds(90);
Duration minutes = Duration.ofMinutes(15);
Duration hours = Duration.ofHours(2);
Duration days = Duration.ofDays(1);

System.out.println(seconds); // PT1M30S
System.out.println(minutes.toSeconds()); // 900
System.out.println(hours.toSeconds());   // 7200
System.out.println(days.toHours());      // 24
```

Đây là đoạn minh họa cần đặt trong một phương thức Java. Các hàm `of…` là factory method **static**, còn `toSeconds()` và `toHours()` là phương thức đọc giá trị từ đối tượng `Duration`.

Bảng API:

| API | Đơn vị đầu vào | Ý nghĩa |
| --- | --- | --- |
| `Duration.ofSeconds(long seconds)` | Giây | Tạo từ tổng số giây |
| `Duration.ofSeconds(long seconds, long nanoAdjustment)` | Giây + phần nano giây | Tạo thời lượng có độ chính xác nano giây, chuẩn hóa phần phụ |
| `Duration.ofNanos(long nanos)` | Nano giây | Tạo từ số nano giây |
| `Duration.ofMinutes(long minutes)` | Phút | Mỗi phút bằng 60 giây |
| `Duration.ofHours(long hours)` | Giờ | Mỗi giờ bằng 3.600 giây |
| `Duration.ofDays(long days)` | Ngày 24 giờ | Mỗi ngày luôn bằng 86.400 giây |
| `Duration.ZERO` | Hằng số | Thời lượng bằng 0 |

### 2.2. Vì sao đơn vị đầu vào là long?

Thời lượng có thể lớn hơn phạm vi của `int`. Các factory method nhận `long` để hỗ trợ khoảng dài. Khi gọi với literal số lớn, có thể sử dụng dấu gạch dưới để dễ đọc:

```java
Duration tenMinutes = Duration.ofSeconds(600L);
Duration oneDay = Duration.ofSeconds(86_400L);
Duration twoDays = Duration.ofDays(2);
```

Đây là đoạn minh họa. Dấu gạch dưới trong literal số là cú pháp Java hợp lệ và không thay đổi giá trị. Với `Duration.ofDays(2)`, tổng thời lượng là 172.800 giây, tương đương chính xác 48 giờ.

### 2.3. Tạo phần giây lẻ

`Duration` hỗ trợ chính xác tới nano giây:

```java
Duration fractional = Duration.ofSeconds(3, 250_000_000);
Duration nanos = Duration.ofNanos(3_250_000_000L);

System.out.println(fractional); // PT3.25S
System.out.println(nanos);      // PT3.25S
System.out.println(fractional.equals(nanos)); // true
```

Đoạn minh họa cần import `java.time.Duration`. Tham số `nanoAdjustment` của `ofSeconds(seconds, nanoAdjustment)` không chỉ nhận 0–999.999.999; Java chuẩn hóa phần phụ để biểu diễn tổng thời lượng tương đương, miễn là các phép toán không vượt giới hạn số hỗ trợ.

Ví dụ `Duration.ofSeconds(3, 1_250_000_000)` tương đương 4 giây và 250 triệu nano giây sau chuẩn hóa. Cách viết thường dễ đọc hơn là cung cấp giây cùng một phần nano hợp lý.

**Đừng nhầm** `Duration.ofNanos(500_000_000)` (nửa giây) với `Duration.ofMillis(500_000_000)` (500 triệu mili giây). Đơn vị là một phần quan trọng của hợp đồng dữ liệu.

## 3. Ngày 24 giờ không giống một ngày trên lịch

`Duration.ofDays(n)` coi một ngày là **đúng 24 giờ**. Đây là quy ước cố định độc lập với múi giờ:

```java
Duration oneDay = Duration.ofDays(1);
System.out.println(oneDay.getSeconds()); // 86400
System.out.println(oneDay.toHours());    // 24
```

Đoạn minh họa cần import `java.time.Duration`. Nếu bắt đầu từ một `Instant` và cộng `Duration.ofDays(1)`, kết quả luôn cách đúng 86.400 giây trên trục thời gian.

Trong một vùng sử dụng DST, thời gian thực giữa hai mốc nửa đêm của hai ngày liên tiếp có thể là 23 hoặc 25 giờ. Nếu yêu cầu là “ngày mai cùng giờ địa phương”, dùng ngày lịch và zone, ví dụ `ZonedDateTime.plusDays(1)`, thay vì cộng `Duration.ofDays(1)` vào thời điểm tuyệt đối mà không xét quy tắc vùng.

`Period` là kiểu khác để biểu diễn thành phần lịch như năm, tháng, ngày. `Period.ofDays(1)` có ý nghĩa “một ngày lịch” khi áp dụng lên ngày/giờ có ngữ cảnh lịch phù hợp; `Duration.ofDays(1)` có nghĩa “24 giờ thực”. Đặc biệt, số ngày trong một `Period` không thể luôn được quy đổi thành một số giây duy nhất mà không biết mốc thời gian và lịch áp dụng.

| Mong muốn | Kiểu/API nên dùng |
| --- | --- |
| Sau đúng 24 giờ | `instant.plus(Duration.ofDays(1))` |
| Tăng ngày lịch lên một ngày, giữ giờ địa phương theo vùng | `zonedDateTime.plusDays(1)` hoặc phép tính lịch tương đương |
| Khoảng cách giữa hai thời điểm | `Duration.between(start, end)` |
| Tính tháng/năm/ngày lịch | `Period` cùng ngày hoặc loại thời gian có ngữ cảnh lịch phù hợp |

## 4. Chuỗi ISO-8601: Duration.parse

`Duration.parse(String)` đọc biểu diễn thời lượng theo ISO-8601. Các ký hiệu chính:

- `P` bắt đầu phần thời lượng (*period*).
- `D` chỉ ngày.
- `T` mở đầu phần thời gian trong ngày: giờ, phút, giây.
- `H` chỉ giờ, `M` chỉ phút, `S` chỉ giây.
- Phần giây có thể chứa phần thập phân như `PT3.5S`.

Ví dụ:

| Chuỗi ISO-8601 | Ý nghĩa |
| --- | --- |
| `PT0S` | 0 giây |
| `PT30S` | 30 giây |
| `PT15M` | 15 phút |
| `PT2H` | 2 giờ |
| `P1D` | 1 ngày = 24 giờ |
| `P2DT3H` | 2 ngày + 3 giờ = 51 giờ |
| `PT1H30M` | 1 giờ 30 phút |
| `PT3.25S` | 3,25 giây |
| `P2DT3H4M5.5S` | 2 ngày + 3 giờ + 4 phút + 5,5 giây |

Lưu ý ký hiệu `M` phụ thuộc vị trí: trước `T` là **tháng** trong biểu diễn lịch ISO, còn sau `T` là **phút** trong phần thời lượng giờ-phút-giây. `Duration` không biểu diễn lịch theo tháng như `Period`; ví dụ thời lượng 2 tháng không có số giây cố định nếu chưa xác định cách quy đổi theo lịch.

### Ví dụ parse và format

```java
import java.time.Duration;

Duration duration = Duration.parse("P2DT3H4M5.5S");

System.out.println(duration);
// PT51H4M5.5S
System.out.println(duration.getSeconds());
// 183845
System.out.println(duration.getNano());
// 500000000
```

Đây là đoạn minh họa. `Duration.parse` chuyển chuỗi ISO-8601 thành giá trị; khi `toString()` định dạng lại, Java có thể biểu diễn tương đương bằng cách chuẩn hóa tổng số giờ thay cho thành phần ngày ban đầu. Vì vậy `P2DT3H4M5.5S` được in là `PT51H4M5.5S`, vẫn là cùng thời lượng.

`Duration.parse` ném `DateTimeParseException` (là lớp con của `DateTimeException`) nếu chuỗi không được chấp nhận. Với dữ liệu người dùng hoặc API bên ngoài, nên xử lý lỗi parse thay vì cho rằng mọi chuỗi đều hợp lệ.

## 5. Chương trình Java 17+ hoàn chỉnh

Tạo tệp **`DurationCreationDemo.java`**:

```java
import java.time.Duration;
import java.time.temporal.ChronoUnit;

public class DurationCreationDemo {
    public static void main(String[] args) {
        Duration seconds = Duration.ofSeconds(90);
        Duration minutes = Duration.ofMinutes(15);
        Duration hours = Duration.ofHours(2);
        Duration days = Duration.ofDays(1);
        Duration fractional = Duration.ofSeconds(3, 250_000_000);
        Duration iso = Duration.parse("P2DT3H4M5.5S");
        Duration negative = Duration.ofSeconds(-1, 500_000_000);

        System.out.println("90 seconds: " + seconds);
        System.out.println("15 minutes in seconds: " + minutes.toSeconds());
        System.out.println("2 hours in seconds: " + hours.toSeconds());
        System.out.println("1 day in hours: " + days.toHours());
        System.out.println("Fractional seconds: " + fractional);
        System.out.println("ISO duration: " + iso);
        System.out.println("ISO total seconds: " + iso.getSeconds());
        System.out.println("Negative normalized: " + negative);
        System.out.println("One day seconds: " + Duration.ofDays(1).getSeconds());
        System.out.println("Rounded down to minutes: "
                + Duration.ofSeconds(125).truncatedTo(ChronoUnit.MINUTES));
        System.out.println("Zero duration: " + Duration.ZERO);
    }
}
```

Biên dịch và chạy:

```bash
javac DurationCreationDemo.java
java DurationCreationDemo
```

**stdout chính xác** (đã kiểm tra với `javac --release 17` và `java`):

```text
90 seconds: PT1M30S
15 minutes in seconds: 900
2 hours in seconds: 7200
1 day in hours: 24
Fractional seconds: PT3.25S
ISO duration: PT51H4M5.5S
ISO total seconds: 183845
Negative normalized: PT-0.5S
One day seconds: 86400
Rounded down to minutes: PT2M
Zero duration: PT0S
```

Chương trình minh họa việc tạo bằng đơn vị số, parse chuỗi, giữ phần nano giây, chuẩn hóa giá trị âm và cắt độ chính xác. Kết quả là **đầu ra của chương trình Java**, không phải một ví dụ phỏng đoán.

## 6. Đọc giá trị Duration và chuyển đổi đơn vị

Các phương thức thường dùng:

| Phương thức | Trả về | Ý nghĩa |
| --- | --- | --- |
| `getSeconds()` | `long` | Thành phần giây đã chuẩn hóa |
| `getNano()` | `int` | Thành phần nano giây trong phần giây, từ 0 đến 999.999.999 |
| `toSeconds()` | `long` | Tổng thời lượng quy đổi ra giây nguyên |
| `toMinutes()` | `long` | Tổng số phút nguyên |
| `toHours()` | `long` | Tổng số giờ nguyên |
| `toDays()` | `long` | Tổng số ngày 24 giờ nguyên |
| `toMillis()` | `long` | Tổng mili giây; có thể lỗi nếu không vừa `long` |
| `toNanos()` | `long` | Tổng nano giây; phạm vi nhỏ hơn nhiều so với miền `Duration` |

Ví dụ một `Duration` 125 giây:

```java
Duration d = Duration.ofSeconds(125);

System.out.println(d.toMinutes()); // 2
System.out.println(d.toSeconds()); // 125
System.out.println(d.toHours());   // 0
```

`toMinutes()` lấy đơn vị nguyên, không làm tròn 125 giây thành 3 phút. Nếu bạn cần cắt rõ ràng về phút, `truncatedTo(ChronoUnit.MINUTES)` tạo một `Duration` mới đã bỏ phần nhỏ hơn phút. Đây không phải phép làm tròn tới phút gần nhất.

Với khoảng thời gian lớn, `toNanos()` và `toMillis()` có thể ném `ArithmeticException` nếu tổng không biểu diễn được bằng `long`. `Duration` có miền giá trị lớn hơn số nano giây có thể chứa trong một `long`. Khi xử lý thời lượng lớn, dùng `getSeconds()`/`getNano()` hoặc phép toán trực tiếp của `Duration` thay vì chuyển toàn bộ thành nano giây.

Tương tự, chú ý khác biệt giữa **thành phần** và **tổng**: `getSeconds()` trả thành phần giây được chuẩn hóa của đối tượng; `toSeconds()` trả tổng số giây nguyên tương ứng với toàn bộ thời lượng theo quy tắc chuyển đổi của API. Để hiểu chính xác, nên sử dụng các hàm `to…` cho nhu cầu chuyển đổi đơn vị và các hàm `get…` khi cần xem thành phần chuẩn hóa.

## 7. Thời lượng âm và chuẩn hóa nano giây

`Duration` có thể âm, ví dụ khoảng thời gian giữa hai thời điểm khi kết thúc sớm hơn bắt đầu. Các phép toán của Java chuẩn hóa phần nano giây sao cho thành phần nano luôn nằm trong khoảng 0–999.999.999; dấu âm có thể nằm ở thành phần giây.

```java
Duration negative = Duration.ofSeconds(-1, 500_000_000);
System.out.println(negative);           // PT-0.5S
System.out.println(negative.getSeconds()); // -1
System.out.println(negative.getNano());    // 500000000
```

Đây là đoạn minh họa cần import `java.time.Duration`. Dù `getSeconds()` trả -1 và `getNano()` trả 500 triệu, tổng thời lượng là **−0,5 giây**. Đừng tính nhầm tổng bằng cách coi nano giây luôn là phần dương cộng vào trị tuyệt đối của giây; phải hiểu quy tắc chuẩn hóa của `Duration`.

Khi cộng/trừ thời lượng, nhiều phép toán có thể vượt miền số và phát sinh `ArithmeticException`. Nếu dữ liệu đến từ bên ngoài, cần xác thực miền giá trị và xử lý ngoại lệ phù hợp; không dùng một con số “ngày lớn” tùy ý nếu không xác định giới hạn hợp đồng.

## 8. Cộng Duration vào thời điểm, trừ hai thời điểm

`Duration` thường có ý nghĩa nhất khi áp dụng lên `Instant` hoặc kiểu thời gian thích hợp:

```java
import java.time.*;

Instant start = Instant.parse("2024-03-01T09:00:00Z");
Instant after90Minutes = start.plus(Duration.ofMinutes(90));
System.out.println(after90Minutes);
// 2024-03-01T10:30:00Z

Duration elapsed = Duration.between(start, after90Minutes);
System.out.println(elapsed); // PT1H30M
```

Đây là đoạn minh họa cần import `java.time.*`. `Duration.between(start, end)` trả độ dài từ đầu đến cuối; nếu `end` trước `start`, kết quả âm. Hai thời điểm là thứ cần xác định rõ để thời lượng có ý nghĩa.

Khi cộng `Duration.ofDays(1)` vào `Instant`, bạn nhận mốc cách đúng 86.400 giây. Khi cộng vào `ZonedDateTime`, API vẫn cộng khoảng thời gian thực, nên giờ hiển thị có thể lệch một giờ so với ngày lịch kế tiếp qua DST. Nếu yêu cầu là “cùng giờ ngày mai theo lịch địa phương”, hãy dùng `zoned.plusDays(1)`.

## 9. Duration và Period: không dùng thay nhau

| Đặc điểm | `Duration` | `Period` |
| --- | --- | --- |
| Biểu diễn chính | Giây và nano giây | Năm, tháng, ngày theo lịch |
| `ofDays(1)` / `ofDays(1)` | Luôn 24 giờ | Một ngày lịch khi áp dụng vào kiểu có ngày |
| Tháng có độ dài cố định? | Không có đơn vị tháng | Có thành phần tháng, độ dài thực phụ thuộc lịch/mốc |
| Dùng để đo thời gian giữa hai Instant | Phù hợp | Không phải mục tiêu chính |
| Dùng cho “sau một tháng trên lịch” | Không nên quy về số giây cố định | Phù hợp khi áp dụng trong ngữ cảnh lịch |

Ví dụ:

```java
LocalDate date = LocalDate.of(2024, 3, 1);

LocalDate nextCalendarDay = date.plus(Period.ofDays(1));
// 2024-03-02

Instant now = Instant.parse("2024-03-01T09:00:00Z");
Instant next24Hours = now.plus(Duration.ofDays(1));
// 2024-03-02T09:00:00Z
```

Đoạn minh họa cần import `java.time.*`. Ở `LocalDate` không có giờ hoặc zone, thêm `Period.ofDays(1)` là thao tác ngày lịch rõ ràng. Với `Instant`, `Duration.ofDays(1)` là 24 giờ tuyệt đối. Khác biệt càng quan trọng khi tính lương, ca trực, lịch hẹn, ngày thanh toán hoặc báo cáo theo ngày địa phương.

## 10. ISO-8601 và lỗi thường gặp

1. **Nhầm `P1D` với một tháng lịch.** `Duration.parse("P1D")` là một ngày 24 giờ, không phải tháng hoặc ngày lịch có độ dài thực biến đổi.
2. **Đặt `M` sai vị trí.** Phần ngày/tháng trước `T` dùng ngữ nghĩa lịch; phần sau `T` là phút. Với `Duration`, hãy dùng các chuỗi giờ–phút–giây ISO phù hợp như `PT1H30M`.
3. **Nghĩ chuỗi ISO giữ nguyên từng thành phần khi format.** `Duration.parse("P2DT3H")` có thể được in là `PT51H`; giá trị vẫn tương đương.
4. **Dùng `ofDays(1)` để đến cùng giờ địa phương ngày mai.** Đây là đúng 24 giờ, có thể lệch giờ qua DST; dùng phép tính lịch trên `ZonedDateTime` khi đó là mục tiêu.
5. **Coi `toMinutes()` là phép làm tròn.** Nó trả tổng phút nguyên, bỏ phần dư nhỏ hơn một phút.
6. **Dùng `toNanos()` với thời lượng rất lớn.** Tổng nano giây có thể vượt `long`; dùng giây + nano hoặc phương thức thích hợp.
7. **Nhầm `getNano()` với tổng nano giây của thời lượng.** Đây là thành phần nano đã chuẩn hóa, không phải tổng nano của cả thời lượng.
8. **Bỏ qua thời lượng âm.** `Duration.between(later, earlier)` có thể âm; kiểm tra thứ tự mốc khi logic không cho phép.
9. **Parse chuỗi người dùng mà không bắt lỗi.** Chuỗi sai định dạng có thể gây `DateTimeParseException`.
10. **Nhầm Duration với giờ đồng hồ.** `Duration` không chứa mốc bắt đầu hoặc múi giờ; dùng `Instant`/`ZonedDateTime` để gắn ngữ cảnh thời điểm.

## 11. Các ca kiểm thử cần có

| Trường hợp | Kết quả mong đợi |
| --- | --- |
| `Duration.ofSeconds(90)` | `PT1M30S` |
| `Duration.ofMinutes(15).toSeconds()` | 900 |
| `Duration.ofHours(2).toSeconds()` | 7200 |
| `Duration.ofDays(1).getSeconds()` | 86400 |
| `Duration.parse("P2DT3H4M5.5S")` | `PT51H4M5.5S` |
| `Duration.parse("PT3.25S").getNano()` | 250.000.000 |
| `Duration.ZERO` | `PT0S` |
| `Duration.ofSeconds(125).toMinutes()` | 2 |
| `Duration.ofSeconds(125).truncatedTo(MINUTES)` | `PT2M` |
| Parse chuỗi ISO sai | `DateTimeParseException` |
| `Duration.ofDays(1)` cộng vào `Instant` | Cách đúng 86.400 giây |
| `ZonedDateTime.plusDays(1)` qua DST | Giữ ý nghĩa ngày lịch/giờ địa phương theo quy tắc vùng; thời lượng thực có thể không phải 24 giờ |

Trong JUnit 5, bạn có thể dùng `assertEquals` để so sánh `Duration` mong đợi, hoặc `assertThrows(DateTimeParseException.class, () -> Duration.parse("not-a-duration"))` để xác nhận đầu vào sai bị từ chối. Nên kiểm tra riêng tổng giây, phần nano và các trường hợp âm/lớn nếu logic dựa vào chúng.

## 12. Chọn API theo ý nghĩa dữ liệu

| Nhu cầu | API |
| --- | --- |
| Tạo theo giây | `Duration.ofSeconds(seconds)` |
| Tạo theo phút | `Duration.ofMinutes(minutes)` |
| Tạo theo giờ | `Duration.ofHours(hours)` |
| Tạo theo ngày 24 giờ | `Duration.ofDays(days)` |
| Tạo theo nano giây | `Duration.ofNanos(nanos)` |
| Parse chuỗi ISO-8601 | `Duration.parse(text)` |
| Lấy thời lượng giữa hai thời điểm | `Duration.between(start, end)` |
| Cộng khoảng thời gian cố định | `instant.plus(duration)` |
| Cắt phần nhỏ hơn đơn vị | `duration.truncatedTo(ChronoUnit.MINUTES)` |
| Tính theo năm/tháng/ngày lịch | `Period` và kiểu ngày/giờ có ngữ cảnh phù hợp |

**Ghi nhớ:** Dùng `Duration` khi nghiệp vụ nói đến một **khoảng thời gian có độ dài xác định**, khởi tạo từ giây, phút, giờ, ngày 24 giờ hoặc chuỗi ISO-8601. Dùng `Period` và quy tắc lịch khi cần năm/tháng/ngày theo lịch địa phương. Đừng để chữ “ngày” làm bạn nhầm 24 giờ tuyệt đối với một ngày lịch qua DST.
