# Duration: Khoảng thời gian âm, bằng không và dương

Trong Java Date-Time API (`java.time`), `Duration` biểu diễn **một độ dài thời gian**, chẳng hạn thời gian một yêu cầu chạy, thời gian giữa hai sự kiện, hoặc độ chênh giữa hai `Instant`. Một `Duration` có thể **dương**, **bằng không** hoặc **âm**. Dấu của nó cho biết độ dài đại số đang biểu diễn, không tự khẳng định thứ tự một cặp sự kiện nếu ta chưa biết quy ước tính.

Ví dụ thường gặp:

~~~java
Duration positive = Duration.ofSeconds(2);   // PT2S
Duration zero = Duration.ZERO;               // PT0S
Duration negative = Duration.ofSeconds(-2);  // PT-2S
~~~

- **Dương**: tổng thời lượng lớn hơn 0.
- **Bằng không**: độ dài đại số bằng đúng 0; `isZero()` trả `true`.
- **Âm**: tổng thời lượng nhỏ hơn 0; `isNegative()` trả `true`.

Dấu âm không phải lỗi mặc định. Ví dụ `Duration.between(later, earlier)` âm nếu đối số thứ hai xảy ra trước đối số thứ nhất. Quyết định có chấp nhận thời lượng âm hay không phụ thuộc quy tắc nghiệp vụ: thống kê thời gian chạy thường mong đợi không âm, nhưng phép so sánh có hướng và chênh lệch lịch sử có thể hợp lệ khi âm.

## 1. Duration là gì?

`Duration` biểu diễn lượng thời gian theo các đơn vị dựa trên giây (seconds) và nano giây. Nó hữu ích cho khoảng thời gian như `PT1.5S` (một giây rưỡi) hoặc `PT15M` (15 phút). Mô hình của nó không phải là một ngày trên lịch hoặc một giờ đồng hồ tại vùng múi giờ.

| Kiểu | Ý nghĩa | Ví dụ |
|---|---|---|
| `Instant` | Một điểm trên dòng thời gian | `2024-01-01T00:00:05Z` |
| `Duration` | Khoảng thời gian có hướng giữa các điểm | `PT5S`, `PT-2S` |
| `Period` | Khoảng theo lịch tính bằng năm/tháng/ngày | `P1M` (một tháng lịch) |
| `LocalTime` | Giờ trên đồng hồ, không có ngày/múi giờ | `10:30` |

**`Duration.ofDays(1)` khác “một ngày lịch” trong mọi ngữ cảnh.** `Duration` coi một ngày là 24 giờ (86.400 giây); `Period.ofDays(1)` là một ngày lịch. Trong vùng dùng DST, một ngày lịch từ nửa đêm đến nửa đêm hôm sau có thể không dài đúng 24 giờ. Hãy chọn kiểu dựa trên ý nghĩa của yêu cầu.

## 2. Dấu của Duration: âm, không, dương

### Kiểm tra dấu bằng API

Các phương thức quan trọng:

| API | Nghĩa |
|---|---|
| `duration.isNegative()` | Trả `true` nếu tổng khoảng thời gian nhỏ hơn 0 |
| `duration.isZero()` | Trả `true` nếu khoảng thời gian chính xác bằng 0 |
| `duration.isPositive()` | Không có phương thức này trong Java 17; kiểm tra dương bằng `!isNegative() && !isZero()` |
| `duration.abs()` | Trả độ lớn không âm tương ứng; có thể lỗi nếu độ lớn vượt miền biểu diễn |
| `duration.negated()` | Trả khoảng có dấu ngược; không sửa đối tượng gốc |

Java 17 có `isNegative()` và `isZero()`, nhưng **không có `isPositive()`**. Nếu cần kiểm tra dương:

~~~java
boolean positive = !duration.isNegative() && !duration.isZero();
~~~

Không viết `duration.getSeconds() > 0` như cách kiểm tra dấu duy nhất, vì `Duration` có thể có phần nano bổ sung ảnh hưởng đến dấu tổng.

### Trạng thái bằng không

`Duration.ZERO` là hằng số biểu diễn thời lượng bằng 0. Một thời lượng bằng không có thể đến từ hai instant giống nhau:

~~~java
Instant event = Instant.parse("2024-01-01T00:00:00Z");
Duration elapsed = Duration.between(event, event);
System.out.println(elapsed);          // PT0S
System.out.println(elapsed.isZero()); // true
System.out.println(elapsed.isNegative()); // false
~~~

Bằng không là trường hợp riêng, không phải âm và cũng không phải dương. Nếu điều kiện cần “thời lượng lớn hơn 0”, chỉ kiểm tra `!isNegative()` là chưa đủ vì giá trị 0 cũng vượt qua điều kiện đó.

## 3. Cách đọc Duration âm và thành phần giây/nano

Một điểm dễ nhầm là `Duration` chuẩn hóa phần nano về khoảng **0 đến 999.999.999**, kể cả khi toàn bộ khoảng thời gian âm. Ví dụ:

~~~java
Duration negative = Duration.ofSeconds(-2, 500_000_000);
System.out.println(negative);          // PT-1.5S
System.out.println(negative.getSeconds()); // -2
System.out.println(negative.getNano());    // 500000000
System.out.println(negative.isNegative()); // true
~~~

Đọc đúng ý nghĩa: tổng thời lượng bằng `-2 + 0,5 = -1,5` giây. `getSeconds()` trả `-2` và `getNano()` trả `500_000_000` — nano không âm. Nếu chỉ nhìn `getSeconds()` hoặc chỉ nhìn `getNano()`, sẽ rất dễ hiểu sai dấu của toàn bộ thời lượng.

Quy tắc chuẩn hóa này giúp biểu diễn mọi giá trị theo cặp giây + phần nano hợp lệ. Không tự kết luận một `Duration` là dương chỉ vì `getNano()` lớn hơn 0.

### ISO-8601 string của Duration

`Duration.toString()` dùng dạng văn bản theo ISO-8601:

| Thời lượng | Chuỗi phổ biến |
|---|---|
| Hai giây dương | `PT2S` |
| 1,5 giây dương | `PT1.5S` |
| Hai giây âm | `PT-2S` |
| 1,5 giây âm | `PT-1.5S` |
| Bằng không | `PT0S` |
| 15 phút | `PT15M` |
| Một ngày 24 giờ | `PT24H` |

`P` mở đầu phần period; `T` đánh dấu phần giờ/phút/giây; `S` biểu diễn giây. Đây là định dạng duration, không phải định dạng một ngày giờ như `2024-01-01T00:00:00Z`.

Khi đọc duration từ API hoặc cấu hình, nên dùng `Duration.parse("PT-1.5S")` và xác thực nó với phạm vi nghiệp vụ. Đừng phân tích chuỗi bằng cách chỉ loại bỏ chữ `PT` hoặc đoán dấu từ một thành phần.

## 4. Duration.between: thứ tự hai đối số quyết định dấu

`Duration.between(start, end)` tính khoảng từ đối số đầu tới đối số thứ hai. Về ý nghĩa đại số, nó tương đương **end − start**:

- Nếu end xảy ra sau start: duration dương.
- Nếu end bằng start: duration bằng 0.
- Nếu end xảy ra trước start: duration âm.

~~~java
Instant start = Instant.parse("2024-01-01T00:00:10Z");
Instant end = Instant.parse("2024-01-01T00:00:12Z");

Duration forward = Duration.between(start, end); // PT2S
Duration backward = Duration.between(end, start); // PT-2S
~~~

Bảng minh họa:

| Start | End | Kết quả | Dấu |
|---|---|---|---|
| 10 giây | 12 giây | `PT2S` | Dương |
| 10 giây | 10 giây | `PT0S` | Bằng không |
| 12 giây | 10 giây | `PT-2S` | Âm |

**Đối số không tự được sắp xếp theo thời gian.** Nếu bạn đảo vị trí hai đối số, dấu bị đảo. Khi một duration âm bất ngờ xuất hiện, trước hết kiểm tra thứ tự truyền vào và ý nghĩa của hai biến. Có thể nghiệp vụ yêu cầu từ chối dữ liệu kết thúc trước lúc bắt đầu, hoặc có thể phép trừ có hướng là chính xác.

Với `Instant`, `Duration.between(a,b)` là cách phù hợp để đo khoảng thời gian trên timeline. Với kiểu khác, kết quả tuân theo cách kiểu đó mô hình hóa thời gian; đặc biệt không coi `Duration.between(LocalTime...)` là thời lượng toàn cục giữa hai sự kiện nếu không biết ngày và cách xử lý qua nửa đêm.

## 5. Phép toán trên thời lượng có dấu

### Cộng và trừ duration

~~~java
Duration negative = Duration.ofMillis(-1500); // PT-1.5S
Duration adjusted = negative.plusSeconds(3); // PT1.5S
Duration shorter = Duration.ofSeconds(2).minusSeconds(5); // PT-3S
~~~

Cộng thời lượng dương có thể khiến duration âm trở thành dương; trừ một khoảng lớn hơn độ lớn ban đầu có thể làm kết quả âm. Các phép toán không sửa đối tượng gốc vì `Duration` là immutable; phải giữ giá trị trả về.

### Đảo dấu và lấy trị tuyệt đối

~~~java
Duration d = Duration.ofSeconds(-2);
Duration flipped = d.negated(); // PT2S
Duration magnitude = d.abs();    // PT2S
~~~

`negated()` và `abs()` khác nhau về mục đích: `negated()` đổi dấu đại số; `abs()` trả độ lớn không âm. Tránh dùng `abs()` để che khuất một dữ liệu bất thường khi dấu âm đang mang thông tin quan trọng.

**Chú ý tràn số:** `Duration` có miền biểu diễn hữu hạn. `abs()` hoặc `negated()` có thể ném `ArithmeticException` cho giá trị đặc biệt có độ lớn không biểu diễn được sau khi đổi dấu; không nên giả định trị tuyệt đối luôn an toàn với mọi duration.

### Chia duration

~~~java
Duration duration = Duration.ofMillis(-1500);
Duration half = duration.dividedBy(2); // PT-0.75S
~~~

Chia một duration là chia **độ dài đại số**, giữ dấu và chuẩn hóa phần nano. Nó không phải làm tròn số nguyên giây theo cách thủ công. Nếu hệ thống chuyển kết quả sang mili giây, nano giây hoặc giây nguyên, hãy xem rõ bước chuyển đơn vị và phần chính xác bị mất.

## 6. Chuyển đổi đơn vị và giới hạn số học

Một số API tiện dụng:

- `toDays()`, `toHours()`, `toMinutes()`, `toSeconds()` trả số nguyên đơn vị tương ứng; phần dư nhỏ hơn đơn vị bị bỏ theo quy tắc của API.
- `toMillis()` chuyển sang mili giây; có thể ném `ArithmeticException` nếu kết quả vượt miền `long`.
- `toNanos()` chuyển sang nano giây dạng `long`; cũng có thể tràn với khoảng lớn.
- `getSeconds()` và `getNano()` đọc cặp giây/nano chuẩn hóa; không tương đương với một số thực đơn giản nếu chỉ nhìn riêng một thành phần.

Ví dụ, với `Duration.ofMillis(-1500)`:

~~~java
Duration d = Duration.ofMillis(-1500);
System.out.println(d.toSeconds()); // -1
System.out.println(d.toMillis());  // -1500
~~~

`toSeconds()` trả số giây nguyên và bỏ phần lẻ; nó không phải phép làm tròn đến giây gần nhất. Dấu của kết quả nguyên cũng có thể khác trực giác nếu chỉ nhìn phần giây và phần nano riêng lẻ — đọc `isNegative()` để kiểm tra dấu tổng.

Nếu duration bắt nguồn từ một chênh lệch lớn, đừng mặc định đổi sang mili/nano luôn an toàn. Hãy xác nhận miền đầu vào và xử lý ngoại lệ khi chuyển đơn vị có thể tràn.

## 7. Ví dụ Java 17 chạy độc lập

Tạo tệp **`DurationSignDemo.java`**:

~~~java
import java.time.Duration;
import java.time.Instant;

public class DurationSignDemo {
    public static void main(String[] args) {
        Duration negative = Duration.ofSeconds(-2, 500_000_000);
        Duration zero = Duration.ZERO;
        Duration positive = Duration.ofMillis(1500);

        System.out.println("negative = " + negative);
        System.out.println("negative seconds = " + negative.getSeconds());
        System.out.println("negative nanos = " + negative.getNano());
        System.out.println("negative isNegative = " + negative.isNegative());
        System.out.println("negative isZero = " + negative.isZero());
        System.out.println("zero = " + zero);
        System.out.println("zero isNegative = " + zero.isNegative());
        System.out.println("zero isZero = " + zero.isZero());
        System.out.println("positive = " + positive);
        System.out.println("positive isNegative = " + positive.isNegative());
        System.out.println("positive millis = " + positive.toMillis());
        System.out.println("negative divided by 2 = " + negative.dividedBy(2));
        System.out.println("negative plus 3 sec = " + negative.plusSeconds(3));

        Instant later = Instant.parse("2024-01-01T00:00:10Z");
        Instant earlier = Instant.parse("2024-01-01T00:00:12Z");
        Duration reverse = Duration.between(earlier, later);
        System.out.println("reverse between = " + reverse);
        System.out.println("reverse sign negative = " + reverse.isNegative());
        System.out.println("absolute = " + reverse.abs());
        System.out.println("abs equals positive? = " +
                reverse.abs().equals(Duration.ofSeconds(2)));
    }
}
~~~

Biên dịch và chạy với JDK 17 trở lên:

~~~bash
javac DurationSignDemo.java
java DurationSignDemo
~~~

Đầu ra đã được xác minh khi biên dịch bằng `javac --release 17`:

~~~text
negative = PT-1.5S
negative seconds = -2
negative nanos = 500000000
negative isNegative = true
negative isZero = false
zero = PT0S
zero isNegative = false
zero isZero = true
positive = PT1.5S
positive isNegative = false
positive millis = 1500
negative divided by 2 = PT-0.75S
negative plus 3 sec = PT1.5S
reverse between = PT-2S
reverse sign negative = true
absolute = PT2S
abs equals positive? = true
~~~

**Đọc đầu ra:**

1. `negative` tổng là âm dù `getNano()` dương; cặp `-2 giây + 500.000.000 ns` biểu diễn `-1,5 giây`.
2. `Duration.ZERO` không âm, nhưng cũng không dương: `isZero()` là `true`.
3. `PT1.5S` là duration dương, có thể đổi thành 1500 mili giây.
4. Chia `-1,5` giây cho hai được `-0,75` giây; cộng 3 giây cho duration gốc được kết quả `+1,5` giây.
5. `Duration.between(earlier, later)` ở ví dụ được cố tình đặt ngược thời gian, nên trả `PT-2S`; lấy `abs()` cho độ lớn 2 giây.

## 8. Ứng dụng và chính sách nghiệp vụ

### Đo thời gian chạy tác vụ

Nếu đo khoảng giữa lúc bắt đầu và lúc hoàn tất bằng hai `Instant`:

~~~java
Instant started = Instant.now();
// thực hiện công việc
Instant finished = Instant.now();
Duration elapsed = Duration.between(started, finished);
~~~

Thông thường ta kỳ vọng `elapsed` không âm, nhưng đồng hồ hệ thống có thể bị điều chỉnh. Với đo hiệu năng trong một tiến trình, `System.nanoTime()` phù hợp hơn vì dùng đồng hồ đơn điệu; `Instant` phù hợp để ghi mốc thời gian theo đồng hồ thực. Không dùng duration từ đồng hồ tường như bảo đảm tuyệt đối về thời lượng chạy.

### Validate thời lượng phải dương

Nếu thời lượng phải lớn hơn 0:

~~~java
if (duration.isNegative() || duration.isZero()) {
    throw new IllegalArgumentException("Thời lượng phải lớn hơn 0");
}
~~~

Nếu nghiệp vụ cho phép bằng 0 nhưng không cho phép âm:

~~~java
if (duration.isNegative()) {
    throw new IllegalArgumentException("Thời lượng không được âm");
}
~~~

Dùng điều kiện phản ánh chính xác yêu cầu; đừng chỉ viết `!duration.isNegative()` khi zero không hợp lệ. Một duration âm đôi lúc hoàn toàn đúng nếu đang biểu diễn “kết thúc trước thời điểm bắt đầu” trong phép tính có hướng, nên quyết định từ ngữ cảnh.

### Khi nhận duration từ API hoặc cấu hình

- Chốt đơn vị/hợp đồng định dạng, ví dụ chuỗi ISO `PT30S` hoặc `PT-1.5S`.
- Validate dấu theo nghiệp vụ: timeout, thời hạn hoặc độ trễ thường có yêu cầu riêng.
- Khi chuyển sang số mili giây/nano giây, kiểm tra khả năng tràn.
- Không nhầm `Duration` với số timestamp của `Instant`: một cái là **độ dài**, cái còn lại là **điểm**.
- Nếu dữ liệu âm ngoài hợp đồng, trả lỗi xác thực có ý nghĩa thay vì lấy trị tuyệt đối để che khuất đầu vào.

## 9. Lỗi thường gặp

| Nhầm lẫn | Vì sao sai | Cách đúng |
|---|---|---|
| Cho rằng duration âm luôn là bug | Kết quả `between(a,b)` âm khi b sớm hơn a | Kiểm tra thứ tự đầu vào và quy tắc nghiệp vụ |
| Nghĩ `getNano()` âm khi duration âm | Thành phần nano được chuẩn hóa không âm | Xem `isNegative()` và hiểu cặp giây/nano |
| Dùng `getSeconds() > 0` để xác nhận dương | Không xử lý tổng duration và phần nano đúng nghĩa | Dùng `!isNegative() && !isZero()` |
| Dùng `!isNegative()` để xác nhận dương | Bằng không cũng không âm | Thêm kiểm tra `!isZero()` |
| Coi zero và negative giống nhau | Zero chính xác là 0; negative nhỏ hơn 0 | Phân biệt `isZero()` và `isNegative()` |
| Xem `Duration.ofDays(1)` là một ngày lịch trong mọi zone | Nó bằng 24 giờ cố định | Dùng `Period.ofDays(1)` khi ý nghĩa là một ngày lịch |
| Đảo thứ tự `Duration.between(start,end)` | Dấu bị đảo vì phép tính có hướng | Xác minh end trừ start đúng ý |
| Gọi `abs()` rồi bỏ qua dữ liệu âm | Có thể che đi lỗi dữ liệu/luồng nghiệp vụ | Chỉ dùng trị tuyệt đối khi nghiệp vụ cần độ lớn |
| Tin rằng `toMillis()` luôn thành công | Giá trị lớn có thể vượt `long` | Kiểm tra giới hạn và bắt `ArithmeticException` |
| Nghĩ `Duration` sửa đối tượng khi cộng/trừ | Kiểu bất biến | Lưu giá trị mới trả về |
| Dùng `Duration` cho tháng lịch | Tháng có số ngày khác nhau | Dùng `Period` cho năm/tháng/ngày lịch |

## 10. Câu hỏi tự kiểm tra

1. `Duration.ofSeconds(2).isNegative()` là gì? **false**, duration dương.
2. `Duration.ZERO.isZero()` và `isNegative()` là gì? **true** và **false**.
3. `Duration.between(later, earlier)` âm hay dương nếu `earlier` xảy ra trước `later`? **Âm**, vì đối số thứ hai sớm hơn đối số đầu.
4. Vì sao `Duration.ofSeconds(-2, 500_000_000)` in thành `PT-1.5S`? Vì tổng đại số là **-1,5 giây**, dù nano thành phần là số dương.
5. Java 17 có `Duration.isPositive()` không? **Không**; kiểm tra bằng `!isNegative() && !isZero()`.
6. `Duration.ofMillis(-1500).toSeconds()` trả gì? **-1**, phần lẻ bị bỏ; `toMillis()` trả **-1500**.
7. Dùng API nào để lấy độ lớn không âm? **`abs()`**, nhưng vẫn lưu ý tràn ở cực trị.
8. Có nên lấy `abs()` cho mọi duration âm không? **Không**; chỉ khi yêu cầu là độ lớn, vì dấu có thể mang nghĩa dữ liệu.
9. Một ngày của `Duration` dài bao lâu? **24 giờ**; một ngày lịch ở vùng DST có thể dài khác 24 giờ.
10. Nếu “thời lượng phải dương” nhưng duration bằng zero, điều kiện nào từ chối? **`isNegative() || isZero()`**.

**Ghi nhớ:** Dấu của `Duration` phản ánh **tổng khoảng thời gian có hướng**: âm khi nhỏ hơn zero, bằng zero khi chính xác bằng 0, và dương khi lớn hơn zero. Dùng `isNegative()` cùng `isZero()` để phân loại; khi tính `Duration.between(a,b)`, nhớ rằng dấu phụ thuộc thứ tự hai đối số và ý nghĩa nghiệp vụ.

### Tài liệu tham khảo

- [Java SE 17 — Duration](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/Duration.html)
- [Java SE 17 — Instant](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/Instant.html)
- [Java SE 17 — Period](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/Period.html)
