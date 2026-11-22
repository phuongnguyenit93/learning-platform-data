# `Duration` biểu diễn lượng thời gian bằng giây và nano giây

Khi một chương trình cần biết tác vụ chạy bao lâu, mã xác thực còn hiệu lực trong bao lâu hoặc hai sự kiện cách nhau bao nhiêu thời gian, ta cần **độ dài thời gian đã trôi qua**. Trong Java, `java.time.Duration` biểu diễn loại khoảng này. Nó thích hợp cho giây, phút, giờ và các phần nhỏ của giây, kể cả khoảng thời gian âm khi hai mốc được đưa vào theo thứ tự ngược.

`Duration` khác `Period`: một phút hay một giờ có thể biểu diễn bằng lượng thời gian cố định, còn một tháng hoặc một ngày theo lịch phụ thuộc lịch và ngữ cảnh. Hiểu chính xác `Duration` giúp tránh lỗi khi tính thời hạn, so sánh thời điểm, đo hiệu năng và làm việc qua vùng có đổi giờ mùa hè.

## 1. Duration là độ dài giữa hai mốc

`Duration` thường được tạo từ hai `Instant`:

~~~java
Instant start = Instant.parse("2026-05-01T10:00:00Z");
Instant end = Instant.parse("2026-05-01T10:00:12Z");

Duration elapsed = Duration.between(start, end);
// PT12S
~~~

Kết quả `PT12S` là biểu diễn ISO-8601 của thời lượng 12 giây. `Duration` không lưu một ngày bắt đầu, giờ địa phương hay múi giờ; nó chỉ biểu diễn khoảng thời gian. Bởi vậy, hai mốc có thể nằm ở những ngày hoặc năm khác nhau mà độ dài vẫn được tính bằng giây và nano giây.

Các đối tượng `Duration` là bất biến. Phép cộng, trừ, nhân hoặc đổi đơn vị tạo giá trị mới, không chỉnh sửa đối tượng cũ.

## 2. Độ chính xác giây và nano giây

Java biểu diễn một `Duration` bằng thành phần giây có dấu và phần nano giây đã chuẩn hóa. Có thể đọc bằng:

- `getSeconds()` — thành phần giây.
- `getNano()` — phần nano giây trong giây đã chuẩn hóa, từ 0 đến 999.999.999.
- `toNanos()` — tổng độ dài quy đổi sang nano giây dạng `long`, nếu không tràn.
- `toMillis()` — tổng độ dài quy đổi sang mili giây dạng `long`.

Ví dụ khoảng 1,5 giây:

~~~java
Duration d = Duration.ofMillis(1500);

System.out.println(d.getSeconds()); // 1
System.out.println(d.getNano());    // 500000000
System.out.println(d.toMillis());   // 1500
System.out.println(d.toNanos());    // 1500000000
~~~

Phần nano cho phép biểu diễn các phân số của giây với độ phân giải nano giây. Điều đó không đảm bảo đồng hồ vật lý hay hệ điều hành luôn đo được chính xác tới 1 ns; độ phân giải biểu diễn và độ chính xác đo là hai khái niệm khác nhau.

### 2.1. Chuẩn hóa thời lượng âm

Khoảng âm vẫn được biểu diễn bằng giây và nano đã chuẩn hóa. Ví dụ `Duration.ofMillis(-500)` biểu diễn âm nửa giây:

~~~java
Duration d = Duration.ofMillis(-500);

System.out.println(d);            // PT-0.5S
System.out.println(d.getSeconds()); // -1
System.out.println(d.getNano());    // 500000000
System.out.println(d.toMillis());   // -500
~~~

Cặp thành phần là `(-1 giây, +500.000.000 nano)`, tổng cộng `-1 + 0,5 = -0,5 giây`. Không giả định nano thành phần sẽ mang dấu âm. Phần giây và nano phải được hiểu cùng nhau.

Đối với hai mốc, `Duration.between(start, end)` trả thời lượng dương nếu `end` sau `start` và âm nếu `end` trước `start`:

~~~java
Instant later = Instant.parse("2026-01-01T00:00:01Z");
Instant earlier = Instant.parse("2026-01-01T00:00:00Z");

System.out.println(Duration.between(earlier, later)); // PT1S
System.out.println(Duration.between(later, earlier)); // PT-1S
~~~

Thứ tự đối số là quan trọng. Nếu thời lượng âm xuất hiện ngoài dự kiến, hãy kiểm tra cách chọn mốc bắt đầu/kết thúc.

## 3. Tạo Duration bằng các factory method

### 3.1. Giây, phút, giờ và đơn vị nhỏ hơn

Các phương thức thường gặp:

| Phương thức | Ví dụ | Ý nghĩa |
| --- | --- | --- |
| `Duration.ofNanos(n)` | `ofNanos(500)` | 500 nano giây |
| `Duration.ofMillis(n)` | `ofMillis(1250)` | 1,25 giây |
| `Duration.ofSeconds(n)` | `ofSeconds(30)` | 30 giây |
| `Duration.ofMinutes(n)` | `ofMinutes(5)` | 300 giây |
| `Duration.ofHours(n)` | `ofHours(2)` | 7.200 giây |
| `Duration.ofDays(n)` | `ofDays(1)` | Chính xác 24 giờ trong Duration |
| `Duration.between(a, b)` | `between(start, end)` | Độ dài từ a tới b |

`Duration.ofDays(1)` tương đương chính xác 24 giờ, không phải “ngày kế tiếp tại một địa phương”. Cách tính này quan trọng qua DST, khi ngày trên lịch có thể kéo dài 23 hoặc 25 giờ trên dòng thời gian.

Các factory method chấp nhận lượng có dấu, trong phạm vi kiểu dữ liệu cho phép. Chúng không tự suy ra ngày lịch hoặc múi giờ.

### 3.2. Parse chuỗi ISO-8601

`Duration.parse` đọc thời lượng theo ISO-8601:

~~~java
Duration a = Duration.parse("PT15M"); // 15 phút
Duration b = Duration.parse("PT1H30M"); // 1 giờ 30 phút
Duration c = Duration.parse("P2DT3H"); // 2 ngày (48 giờ) + 3 giờ
Duration negative = Duration.parse("PT-0.5S"); // âm nửa giây
~~~

Ký hiệu `P` bắt đầu phần thời lượng, `T` phân tách phần thời gian với phần ngày/tháng/năm. Trong `Duration`, ngày `D` tương đương 24 giờ; năm và tháng theo lịch không phải đơn vị thời lượng cố định của `Duration`.

Khi nhận dữ liệu từ API, hãy thống nhất định dạng và đơn vị. Chuỗi `"90"` tự nó không xác định là 90 giây, mili giây hay phút; ISO `PT90S` thể hiện rõ đó là 90 giây.

### 3.3. Dựng từ seconds và nano adjustment

`Duration.ofSeconds(seconds, nanoAdjustment)` cho phép cộng phần nano điều chỉnh. Đầu vào được chuẩn hóa tương tự quy tắc giây/nano của thời lượng:

~~~java
Duration a = Duration.ofSeconds(1, 500_000_000);
Duration b = Duration.ofSeconds(2, -500_000_000);

System.out.println(a); // PT1.5S
System.out.println(b); // PT1.5S
System.out.println(a.equals(b)); // true
~~~

Nano adjustment không nhất thiết phải nằm trong phạm vi 0–999.999.999 trước khi gọi; Java điều chỉnh sang thành phần giây thích hợp. Dẫu vậy, trong code nghiệp vụ thường nên truyền lượng có ý nghĩa rõ ràng và để API quản lý phần chuẩn hóa.

## 4. So sánh và lấy thành phần

`Duration` có thể so sánh bằng `compareTo`, `equals` và các phương thức `isZero`, `isNegative`:

~~~java
Duration shortWait = Duration.ofSeconds(5);
Duration longWait = Duration.ofSeconds(10);

System.out.println(shortWait.compareTo(longWait) < 0); // true
System.out.println(shortWait.isZero()); // false
System.out.println(shortWait.isNegative()); // false
~~~

Các phương thức `toDays()`, `toHours()`, `toMinutes()`, `toSeconds()` trả về số đơn vị **toàn phần**, không giữ phần lẻ của đơn vị lớn hơn:

~~~java
Duration d = Duration.ofSeconds(90);

System.out.println(d.toMinutes()); // 1
System.out.println(d.toSeconds()); // 90
~~~

Trong đó `toMinutes()` không phải 1,5 vì kết quả là `long` nguyên. Nếu cần phần thập phân của phút để hiển thị, cần tự định nghĩa cách đổi sang số thực hoặc đơn vị nhỏ hơn với độ chính xác mong muốn. Tránh dùng số thực khi cần so sánh ranh giới thời hạn chính xác.

`toNanos()` và `toMillis()` có thể ném `ArithmeticException` nếu giá trị vượt phạm vi `long`. Không được giả định mọi `Duration` hợp lệ đều quy đổi được sang tổng nano giây nguyên. Khi thời lượng rất lớn, so sánh trực tiếp hoặc dùng các phép toán phù hợp trên `Duration` có thể an toàn hơn so với tự nhân số đơn vị.

## 5. Cộng, trừ và nhân thời lượng

Có thể tạo giá trị mới bằng `plus`, `minus`, `multipliedBy` và `dividedBy`:

~~~java
Duration base = Duration.ofMinutes(10);
Duration plus = base.plus(Duration.ofSeconds(30));
Duration minus = base.minus(Duration.ofMinutes(2));
Duration doubled = base.multipliedBy(2);
Duration half = base.dividedBy(2);

System.out.println(plus);    // PT10M30S
System.out.println(minus);   // PT8M
System.out.println(doubled); // PT20M
System.out.println(half);    // PT5M
~~~

`Duration` là bất biến, vì vậy `base` vẫn là `PT10M`. Dùng `plusSeconds`, `minusMillis`, `plusNanos` khi muốn thể hiện trực tiếp đơn vị.

Một thời lượng có thể bị tràn nếu phép tính vượt phạm vi hỗ trợ; nên kiểm tra dữ liệu từ bên ngoài và xử lý ngoại lệ thích hợp. Phép chia số nguyên cũng cần được hiểu theo độ chính xác của `Duration`, không suy diễn rằng mọi thời lượng đều chia ra kết quả nguyên nanosecond.

## 6. Duration không giống Period hoặc một ngày trên lịch

Đây là nhầm lẫn quan trọng nhất:

- `Duration.ofHours(24)`: lượng thời gian đúng 24 giờ.
- `Period.ofDays(1)`: một ngày lịch.
- `ZonedDateTime.plusDays(1)`: dịch sang ngày kế tiếp của lịch vùng, theo quy tắc giờ địa phương.
- `ZonedDateTime.plusHours(24)`: tiến chính xác 24 giờ trên dòng thời gian.

Giả sử bắt đầu lúc 12:00 ngày 31/10/2026 tại New York, trước khi đồng hồ lùi để kết thúc DST:

~~~java
ZoneId zone = ZoneId.of("America/New_York");
ZonedDateTime start = LocalDateTime.of(2026, 10, 31, 12, 0)
        .atZone(zone);

ZonedDateTime nextCalendarDay = start.plusDays(1);
ZonedDateTime after24Hours = start.plusHours(24);

System.out.println(start);
System.out.println(nextCalendarDay);
System.out.println(after24Hours);
System.out.println(Duration.between(
        start.toInstant(), nextCalendarDay.toInstant()).toHours());
~~~

Với quy tắc timezone New York cho ví dụ này, kết quả:

~~~text
2026-10-31T12:00-04:00[America/New_York]
2026-11-01T12:00-05:00[America/New_York]
2026-11-01T11:00-05:00[America/New_York]
25
~~~

Ngày kế tiếp cùng 12:00 cách 25 giờ thực vì đồng hồ đã lùi một giờ. Một `Duration` không mang ZoneId nên không tự phản ánh các quy tắc lịch theo vùng. Chọn phép toán theo đúng câu hỏi nghiệp vụ: “sau 24 giờ” hay “cùng giờ ngày mai”.

## 7. Tính thời lượng đã trôi qua

### 7.1. Dùng Instant khi đo khoảng cách hai thời điểm thực

~~~java
Instant start = Instant.parse("2026-05-01T10:00:00Z");
Instant finish = Instant.parse("2026-05-01T10:03:40Z");

Duration elapsed = Duration.between(start, finish);
System.out.println(elapsed); // PT3M40S
System.out.println(elapsed.toSeconds()); // 220
~~~

Cách này phù hợp với hai mốc tuyệt đối đã được xác định. Với các sự kiện ở các múi giờ khác nhau, chuyển chúng về Instant rồi lấy Duration giúp tính thời gian trôi qua đúng.

Đừng lấy hai `LocalDateTime` không có timezone ở hai địa điểm khác nhau rồi cho rằng hiệu số của chúng là thời lượng thực. Nếu mốc địa phương có thể chịu DST hoặc thuộc các vùng khác nhau, phải giải quyết zone/offset trước.

### 7.2. Đo một đoạn code trong JVM

Khi đo thời gian thực hiện tác vụ, dùng hiệu hai giá trị `System.nanoTime()`:

~~~java
long startNanos = System.nanoTime();
// Thực hiện công việc cần đo.
long elapsedNanos = System.nanoTime() - startNanos;
Duration elapsed = Duration.ofNanos(elapsedNanos);
~~~

`nanoTime()` dành cho đo khoảng cách trong cùng tiến trình, không phải timestamp của lịch hay số nano giây kể từ epoch. Không in giá trị tuyệt đối của nó như ngày giờ và không so sánh trực tiếp giữa hai máy. Khi đo hiệu năng, cần lưu ý warm-up JIT, tải hệ thống, garbage collection và lặp đủ số lần nếu muốn benchmark đáng tin cậy.

### 7.3. Có thể dùng Clock để kiểm thử thời hạn

`Clock` giúp kiểm soát “bây giờ” trong code cần deadline:

~~~java
Clock clock = Clock.fixed(
        Instant.parse("2026-05-01T10:00:00Z"),
        ZoneOffset.UTC);

Instant now = Instant.now(clock);
Instant deadline = now.plus(Duration.ofMinutes(5));
boolean expired = !now.isBefore(deadline);
~~~

Ví dụ dùng thời điểm cố định nên có thể test ngay tại ranh giới mà không chờ đồng hồ thật. Trong ứng dụng, nguồn giờ dùng để quyết định deadline phải được chọn có chủ đích, thường là nguồn thời gian đáng tin cậy của máy chủ.

## 8. Thời hạn và ranh giới

Một cách phổ biến để diễn đạt thời hạn: bắt đầu tại instant `start` và hết hạn sau `ttl`:

~~~java
Instant expiresAt = start.plus(Duration.ofMinutes(15));
boolean expired = !Instant.now().isBefore(expiresAt);
~~~

Điều kiện trên coi **đúng thời điểm hết hạn** là đã hết hạn. Nếu nghiệp vụ dùng quy ước khác ở biên, hãy thể hiện rõ bằng `isBefore` hoặc `isAfter`.

Nên tính `expiresAt` một lần khi tạo thời hạn, sau đó so sánh với instant hiện tại. Tránh mỗi lần kiểm tra lại cộng 15 phút vào `now`, vì như thế thời hạn sẽ liên tục dời xa tương lai.

Với TTL trong hệ thống phân tán, còn cần xác định nguồn thời gian, đồng hồ bị lệch, độ trễ mạng và cách xử lý retry. `Duration` diễn tả lượng thời gian; nó không tự đồng bộ đồng hồ các máy hay đảm bảo tác vụ thực thi đúng đúng tại deadline.

## 9. Giây âm, chuẩn hóa và mất độ chính xác

Một `Duration` cũng có thể âm:

~~~java
Duration negative = Duration.ofMillis(-1);
System.out.println(negative); // PT-0.001S
System.out.println(negative.getSeconds()); // -1
System.out.println(negative.getNano()); // 999000000
~~~

Cặp `(-1 giây, +999000000 nano)` có tổng là âm một mili giây. Tương tự như `Instant`, không nên tự viết cấu trúc seconds/nanos mà giả định nano luôn cùng dấu với duration.

Khi chuyển xuống độ phân giải mili giây hoặc giây, phần nhỏ hơn đơn vị sẽ bị mất. `Duration.ofNanos(1).toMillis()` trả 0, vì một nano giây chưa đầy một mili giây. `Duration.ofNanos(-1).toMillis()` cũng trả 0 theo phép đổi đơn vị của Duration; đừng nhầm việc này với `Instant.toEpochMilli()`, vốn tính timestamp tương đối epoch với quy tắc ranh giới riêng ở phía âm.

Nên dùng API trực tiếp thay vì tự tính tổng nanosecond hoặc mili giây bằng phép nhân có thể tràn. Khi cần một biểu diễn truyền qua API, hãy công bố đơn vị và độ chính xác.

## 10. Lỗi thường gặp

| Lỗi | Vì sao sai | Cách khắc phục |
| --- | --- | --- |
| Xem `Duration.ofDays(1)` như ngày mai theo địa phương | Nó là đúng 24 giờ | Dùng phép toán theo lịch trên ZonedDateTime khi cần ngày kế |
| Coi `Duration` là `Period` | Thời lượng cố định khác khoảng lịch | Chọn theo ý nghĩa yêu cầu |
| Lấy hiệu hai LocalDateTime ở các vùng khác nhau | Chưa có zone/offset để xác định hai instant | Giải quyết vùng rồi dùng Instant |
| Dùng `System.currentTimeMillis()` để benchmark rất ngắn | Đồng hồ lịch có thể được điều chỉnh, độ phân giải không phù hợp | Dùng hiệu `System.nanoTime()` |
| Nghĩ `toMinutes()` trả số thực | Trả phút nguyên kiểu long | Giữ giây/nano hoặc định nghĩa phép làm tròn |
| Gọi `toNanos()` cho thời lượng rất lớn mà không kiểm tra | Tổng có thể tràn long | Xử lý ArithmeticException hoặc giữ Duration |
| Tính lại deadline từ now trong mỗi lần kiểm tra | Deadline trôi mãi | Tính expiresAt một lần |
| Giả định đối tượng Duration thay đổi tại chỗ | Duration immutable | Gán kết quả plus/minus vào biến |
| Tự lưu nano âm mà không chuẩn hóa | Sai biểu diễn | Dùng factory method và getter của API |
| Lẫn timestamp và thời lượng | Timestamp là mốc, duration là khoảng cách | Dùng Instant cho mốc, Duration cho khoảng |

## 11. Chương trình Java 17+ chạy độc lập

Chương trình dùng giá trị cố định để minh họa Duration dương/âm, độ chính xác, phép toán, khoảng giữa hai instant và thời hạn. Kết quả không phụ thuộc giờ hiện tại.

~~~java
import java.time.Duration;
import java.time.Instant;

public class DurationBasicsDemo {
    public static void main(String[] args) {
        Duration d = Duration.ofMillis(1500);
        Duration negative = Duration.ofMillis(-500);

        System.out.println("d=" + d);
        System.out.println("d.seconds=" + d.getSeconds());
        System.out.println("d.nanos=" + d.getNano());
        System.out.println("d.millis=" + d.toMillis());
        System.out.println("negative=" + negative);
        System.out.println("negative.seconds=" + negative.getSeconds());
        System.out.println("negative.nanos=" + negative.getNano());

        Instant start = Instant.parse("2026-05-01T10:00:00Z");
        Instant end = Instant.parse("2026-05-01T10:03:40Z");
        Duration elapsed = Duration.between(start, end);
        System.out.println("elapsed=" + elapsed);
        System.out.println("elapsed.seconds=" + elapsed.toSeconds());

        Instant deadline = start.plus(Duration.ofMinutes(5));
        System.out.println("deadline=" + deadline);
        System.out.println("shorterThanDeadline="
                + start.isBefore(deadline));
        System.out.println("exactNanos=" + Duration.ofNanos(1).toNanos());
        System.out.println("subMillisecond=" + Duration.ofNanos(1).toMillis());
    }
}
~~~

Lưu đúng tên `DurationBasicsDemo.java`, rồi chạy:

~~~bash
javac DurationBasicsDemo.java
java DurationBasicsDemo
~~~

Đầu ra chuẩn:

~~~text
d=PT1.5S
d.seconds=1
d.nanos=500000000
d.millis=1500
negative=PT-0.5S
negative.seconds=-1
negative.nanos=500000000
elapsed=PT3M40S
elapsed.seconds=220
deadline=2026-05-01T10:05:00Z
shorterThanDeadline=true
exactNanos=1
subMillisecond=0
~~~

Đối chiếu: `negative` có giây `-1` và nano `500000000`, tổng là âm nửa giây. `elapsed` bằng 220 giây. `deadline` được tạo từ start cộng năm phút, và thời lượng một nano giây không đủ để tạo thành một mili giây.

## 12. Bài tập tự kiểm tra

1. `Duration.ofMillis(1500)` có `getSeconds()` và `getNano()` bằng bao nhiêu? Vì sao tổng vẫn là 1,5 giây?
2. `Duration.between(a, b)` âm khi nào? Hãy đảo thứ tự hai instant và quan sát.
3. So sánh `Duration.ofDays(1)` với `Period.ofDays(1)`. Trường hợp nào phù hợp cho timeout 24 giờ, trường hợp nào phù hợp “ngày kế tiếp”?
4. Với `Duration.ofMillis(-1)`, tại sao `getSeconds()` bằng -1 còn `getNano()` không âm?
5. Vì sao `toNanos()` có thể thất bại với Duration rất lớn? Hãy xử lý lỗi chuyển đổi trong một chương trình.
6. Viết test kiểm tra thời điểm trước deadline, đúng deadline và sau deadline. Quy định rõ deadline có được coi là đã hết hạn khi bằng nhau không.
7. Đo đoạn code bằng `System.nanoTime()` rồi chuyển hiệu số sang Duration. Vì sao không lưu giá trị nanoTime tuyệt đối làm ngày giờ?
8. Một yêu cầu nói “gửi thông báo sau 24 giờ” và yêu cầu khác nói “gửi lúc 09:00 ngày mai tại New York”. Hãy chọn mô hình thời gian và phép toán phù hợp cho từng yêu cầu.

**Ghi nhớ:** `Duration` trả lời câu hỏi **“khoảng thời gian dài bao lâu?”** bằng giây và nano giây. Nó không lưu thời điểm bắt đầu hay quy tắc lịch địa phương. Dùng `Instant` để xác định mốc, `Duration` để biểu diễn độ dài thực, và phép toán theo lịch khi yêu cầu là cùng giờ vào ngày kế tiếp.