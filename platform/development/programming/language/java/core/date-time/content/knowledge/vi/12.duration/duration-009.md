# Áp dụng Duration cho thời hạn, độ trễ và thời gian thực sự trôi qua

Trong Java, **java.time.Duration** biểu diễn một lượng thời gian theo giây và phần nano giây. Nó phù hợp để nói “timeout 3 giây”, “token có hiệu lực trong 15 phút”, “độ trễ giữa hai mốc là 120 ms”, hoặc “tác vụ đã chạy bao lâu”. Nhưng các câu đó thuộc những bài toán liên quan mà không hoàn toàn giống nhau: một deadline trong lịch phụ thuộc thời điểm tuyệt đối, còn phép đo latency cần một nguồn thời gian tăng đều.

Muốn dùng Duration đúng, trước hết hãy xác định mình đang cần **một lượng thời gian**, **một thời điểm kết thúc**, hay **phép đo thời gian thực sự trôi qua**. Duration có thể cộng vào Instant để tạo deadline, hoặc là kết quả của Duration.between; bản thân Duration không phải đồng hồ, không tự đếm ngược và không lưu thời điểm bắt đầu.

Bài này dùng Java 17+ và tập trung vào tạo Duration, tính deadline, kiểm tra hạn, đo latency, timeout, retry, cách kiểm thử bằng Clock, cùng các lỗi phổ biến khi nhầm đồng hồ lịch với đồng hồ đo thời lượng.

## 1. Duration biểu diễn điều gì?

**Duration** biểu diễn lượng thời gian bằng giây và phần nano giây. Ví dụ:

~~~java
Duration fiveSeconds = Duration.ofSeconds(5);
Duration ninetyMillis = Duration.ofMillis(90);
Duration twentyMinutes = Duration.ofMinutes(20);
Duration oneAndHalfHours = Duration.ofHours(1).plusMinutes(30);
~~~

Duration không giữ ngày bắt đầu, múi giờ hoặc deadline. Giá trị **Duration.ofMinutes(20)** luôn là lượng thời gian 20 phút; khi được cộng vào một Instant, nó sẽ tạo ra một mốc muộn hơn 1.200 giây.

| Kiểu | Ý nghĩa | Ví dụ |
|---|---|---|
| **Duration** | Lượng thời gian đo theo giây/nano giây | 15 phút |
| **Instant** | Một thời điểm tuyệt đối trên trục thời gian | 2026-10-24T10:00:00Z |
| **LocalDateTime** | Ngày giờ lịch địa phương, không có zone | 2026-10-24T17:00 |
| **Period** | Khoảng thời gian theo lịch năm/tháng/ngày | 1 tháng lịch |
| **System.nanoTime()** | Bộ đếm dùng đo chênh lệch thời gian trong cùng JVM | giá trị tick bắt đầu và kết thúc |

**Không nhầm Duration với Period.** “Chờ đúng 24 giờ” là Duration 24 giờ. “Ngày mai cùng giờ địa phương” là phép toán lịch cần LocalDateTime/ZonedDateTime phù hợp. Một tháng lịch không có số giây cố định; nếu nghiệp vụ nói “thêm một tháng”, thường phải dùng quy tắc lịch và Period/plusMonths, không thể thay thế bằng Duration 30 ngày một cách vô điều kiện.

## 2. Tạo Duration bằng factory methods

Các factory thường dùng:

| Phương thức | Ý nghĩa |
|---|---|
| **Duration.ofNanos(n)** | n nano giây |
| **Duration.ofMillis(n)** | n mili giây |
| **Duration.ofSeconds(n)** | n giây |
| **Duration.ofMinutes(n)** | n phút |
| **Duration.ofHours(n)** | n giờ |
| **Duration.ofDays(n)** | 24 giờ mỗi ngày theo mô hình Duration |

Có thể ghép các phần:

~~~java
Duration timeout = Duration.ofSeconds(2).plusMillis(500);
Duration retryDelay = Duration.ofMillis(250);
Duration ttl = Duration.ofMinutes(15);
Duration wait = Duration.ofHours(1).plusMinutes(30);
~~~

**Duration.ofDays(1)** có nghĩa 86.400 giây, không phải khái niệm “ngày lịch tiếp theo tại mọi vùng”. Khi áp dụng vào Instant, nó cộng đúng độ dài 24 giờ trên trục thời gian. Khi áp dụng vào ZonedDateTime qua ngày đổi giờ mùa hè, cộng 24 giờ có thể khác cộng một ngày lịch.

### Số âm và giá trị bằng không

Duration cũng có thể biểu diễn 0 hoặc âm:

~~~java
Duration zero = Duration.ZERO;
Duration negative = Duration.ofSeconds(-5);
~~~

Một Duration âm có thể hữu ích trong phép tính chênh lệch, nhưng không phải chính sách timeout thông thường. Trong API của ứng dụng, cần định nghĩa timeout/TTL phải dương hay cho phép 0 để chỉ vô hiệu hóa. Không mặc định dùng Duration âm như “không có thời hạn” nếu hợp đồng chưa quy định.

Một số API cho phép duration bằng 0 hoặc âm mang nghĩa đặc biệt; hành vi cụ thể phụ thuộc API đó. Ví dụ Thread.sleep không chấp nhận số âm, trong khi Duration tự nó có thể lưu giá trị âm.

## 3. Duration giữa hai thời điểm

Có hai cách tiếp cận phổ biến:

- **Duration.between(start, end)**: trả lượng thời gian giữa hai Temporal có thể đo được.
- **end.minus(start)**: với hai Instant, có thể dùng Instant.until hoặc tính bằng Duration; Duration.between thường dễ đọc.

Ví dụ:

~~~java
Instant start = Instant.parse("2026-10-24T10:00:00Z");
Instant end = Instant.parse("2026-10-24T10:00:03.250Z");

Duration elapsed = Duration.between(start, end);
~~~

Kết quả là **3 giây 250 mili giây**. Nếu end trước start, kết quả Duration âm. Phương thức không tự đảo hai giá trị hoặc đảm bảo elapsed không âm.

Duration có thể đọc bằng:

- **toDays()**: số ngày nguyên theo mô hình 24 giờ, có quy tắc cắt phần lẻ.
- **toHours()**, **toMinutes()**, **toSeconds()**: đơn vị nguyên.
- **toMillis()**, **toNanos()**: chuyển sang số nguyên đơn vị nhỏ hơn, có thể ném ArithmeticException nếu kết quả vượt phạm vi long.
- **toSecondsPart()**, **toMillisPart()**, **toNanosPart()**: lấy thành phần phần dư tương ứng.

Nếu cần trình bày chính xác cả ngày/giờ/phút/giây, hãy xác định cách hiển thị và xử lý dấu âm; đừng cộng thủ công các phần một cách dễ đếm trùng.

### Không phải mọi đối tượng thời gian đều đo được cùng một khoảng

Duration thường phù hợp với Instant hoặc các mốc có thể xác định lượng thời gian rõ ràng. LocalDateTime không chứa zone, nên Duration.between hai LocalDateTime chỉ đo khoảng cách giữa hai giá trị lịch/đồng hồ theo mô hình địa phương. Nó không thể suy ra khoảng thời gian thực nếu có đổi offset DST ở một vùng cụ thể.

Với **LocalTime**, kết quả giữa hai giá trị có thể âm khi đồng hồ quay qua nửa đêm, bởi LocalTime không ghi ngày. Ví dụ Duration.between(23:30, 01:00) không tự đoán rằng 01:00 là ngày kế tiếp. Hãy giữ ngày bằng LocalDateTime hoặc dùng Instant khi cần thời gian thực tế.

## 4. Chọn đồng hồ theo câu hỏi

Một trong những quyết định quan trọng nhất là **nguồn thời gian nào nên được dùng**.

### Đồng hồ lịch: Instant.now(clock)

Đồng hồ lịch trả về mốc thời gian tuyệt đối, thường dùng để ghi log, tạo timestamp và xác định một deadline theo lịch:

~~~java
Instant createdAt = Instant.now(clock);
Instant expiresAt = createdAt.plus(Duration.ofMinutes(15));
~~~

Ở đây, Clock cần được cung cấp. Production thường dùng Clock.systemUTC(); test có thể dùng Clock.fixed để tạo kết quả lặp lại.

Đồng hồ hệ thống có thể được đồng bộ hoặc điều chỉnh. Vì vậy, khi đo “mã chạy trong bao nhiêu mili giây”, không nên mặc định lấy hai Instant.now() trừ nhau là phép đo latency chính xác nhất. Đồng hồ tường có thể nhảy tiến hoặc lùi.

### Đồng hồ tăng đều: System.nanoTime()

Để đo thời lượng một thao tác trong cùng JVM, dùng bộ đếm monotonic:

~~~java
long started = System.nanoTime();
// Thực hiện thao tác cần đo
long elapsedNanos = System.nanoTime() - started;
~~~

**System.nanoTime()** không phải timestamp lịch, không thể chuyển trực tiếp thành ngày giờ UTC và giá trị tuyệt đối của nó không có ý nghĩa độc lập. Chỉ lấy hiệu giữa các lần đọc trong cùng phép đo. Phép trừ là cách chuẩn để đo thời lượng, đồng thời tránh tự so sánh tick bằng các phép quan hệ dễ sai khi bộ đếm quay vòng sau một khoảng rất dài.

**Duration** có thể lưu kết quả đo được từ hai nguồn mono­tonic: Duration.ofNanos(elapsedNanos). Việc đo dùng System.nanoTime(); Duration chỉ biểu diễn kết quả lượng thời gian.

### Bảng chọn nhanh

| Nhu cầu | Cách tiếp cận phù hợp |
|---|---|
| Thời điểm tạo đơn hàng | Instant.now(clock) |
| Hết hạn tuyệt đối lúc nào | expiresAt = createdAt.plus(ttl) |
| Thời gian chạy một đoạn code | System.nanoTime() và hiệu giữa hai lần đọc |
| Phân phối độ trễ request | Đo nanoTime cho từng request, lưu/ghi lại độ trễ |
| Ngày mai lúc 09:00 theo cửa hàng | Quy tắc lịch + LocalDate/LocalTime + ZoneId |
| Đợi 2 giây rồi thử lại | Duration/đơn vị thời gian của cơ chế scheduler hoặc timer |
| Token hợp lệ đến mốc Instant đã lưu | So sánh Instant hiện tại với expiresAt |

## 5. Deadline khác thời lượng

**Duration** là khoảng thời gian. **Deadline** là một mốc kết thúc cụ thể.

Ví dụ cấp token lúc:

~~~text
issuedAt = 2026-10-24T10:00:00Z
ttl = 15 phút
expiresAt = 2026-10-24T10:15:00Z
~~~

Tính deadline từ thời điểm cấp:

~~~java
Instant issuedAt = Instant.parse("2026-10-24T10:00:00Z");
Duration ttl = Duration.ofMinutes(15);
Instant expiresAt = issuedAt.plus(ttl);
~~~

Khi kiểm tra hiệu lực, phải định rõ biên. Một quy ước phổ biến là khoảng nửa mở **[issuedAt, expiresAt)**: có hiệu lực tại issuedAt nhưng không còn hiệu lực khi now bằng expiresAt.

~~~java
boolean expired = !now.isBefore(expiresAt);
boolean stillValid = now.isBefore(expiresAt);
~~~

Trong quy tắc đó, **now >= expiresAt** có nghĩa đã hết hạn. Nếu chỉ viết now.isAfter(expiresAt), thời điểm đúng bằng deadline sẽ bị coi là chưa hết hạn. Đây là lỗi biên thường gặp.

Nếu nhiều phép so sánh trong cùng quyết định phải dựa vào một khoảnh khắc nhất quán, đọc Instant.now(clock) **một lần** rồi tái sử dụng. Đừng gọi now nhiều lần rồi vô tình vượt qua deadline ở giữa một nhánh xử lý.

## 6. Ví dụ chạy được: thời hạn có thể kiểm thử

Tạo tệp **DeadlineDurationDemo.java**:

~~~java
import java.time.Clock;
import java.time.Duration;
import java.time.Instant;
import java.time.ZoneOffset;
import java.util.Objects;

public class DeadlineDurationDemo {
    private final Clock clock;

    public DeadlineDurationDemo(Clock clock) {
        this.clock = Objects.requireNonNull(clock, "clock");
    }

    public Instant createDeadline(Duration ttl) {
        if (ttl == null || ttl.isZero() || ttl.isNegative()) {
            throw new IllegalArgumentException(
                    "ttl must be positive"
            );
        }
        return Instant.now(clock).plus(ttl);
    }

    public boolean isExpired(Instant deadline) {
        Instant now = Instant.now(clock);
        return !now.isBefore(deadline);
    }

    public static void main(String[] args) {
        Clock base = Clock.fixed(
                Instant.parse("2026-10-24T10:00:00Z"),
                ZoneOffset.UTC
        );

        DeadlineDurationDemo atIssue =
                new DeadlineDurationDemo(base);
        Instant deadline =
                atIssue.createDeadline(Duration.ofMinutes(15));

        Clock justBefore = Clock.offset(
                base, Duration.ofMinutes(14).plusSeconds(59)
        );
        Clock atBoundary = Clock.offset(
                base, Duration.ofMinutes(15)
        );

        System.out.println("deadline=" + deadline);
        System.out.println("expiredAtIssue=" +
                atIssue.isExpired(deadline));
        System.out.println("expiredBefore=" +
                new DeadlineDurationDemo(justBefore).isExpired(deadline));
        System.out.println("expiredAtBoundary=" +
                new DeadlineDurationDemo(atBoundary).isExpired(deadline));
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac DeadlineDurationDemo.java
java DeadlineDurationDemo
~~~

Stdout chính xác:

~~~text
deadline=2026-10-24T10:15:00Z
expiredAtIssue=false
expiredBefore=false
expiredAtBoundary=true
~~~

**Vì sao Clock.fixed và Clock.offset hữu ích?** Chúng tạo một nguồn thời gian xác định, giúp thử trước hạn, đúng hạn và sau hạn mà không phải gọi Thread.sleep. Clock.offset dịch góc nhìn thời gian so với đồng hồ gốc; nó không thay đổi đồng hồ của hệ điều hành.

Production có thể truyền Clock.systemUTC(); test truyền Clock.fixed hoặc Clock.offset. Đây là một ví dụ của dependency injection: service phụ thuộc vào Clock thay vì gắn cứng vào “bây giờ” thật.

## 7. Đo latency đúng cách bằng System.nanoTime()

Ví dụ đơn giản:

~~~java
long started = System.nanoTime();

String normalized = input.trim().toLowerCase();

long elapsedNanos = System.nanoTime() - started;
Duration elapsed = Duration.ofNanos(elapsedNanos);
~~~

Đoạn này chỉ minh họa; nếu thời gian nhỏ, overhead JVM, JIT, GC, scheduler và phần đo có thể ảnh hưởng kết quả. Đừng coi một lần đo đơn lẻ là benchmark tin cậy; khi cần so sánh hiệu năng, dùng phương pháp benchmark phù hợp, lặp đủ nhiều và kiểm soát môi trường.

Với một bộ đếm monotonic, chỉ **hiệu giữa hai lần đọc** có ý nghĩa. Không in hoặc lưu giá trị tuyệt đối của nanoTime rồi cho là timestamp. Nếu cần audit “bắt đầu lúc nào”, ghi Instant riêng; nếu cần “chạy bao lâu”, đo bằng nanoTime.

### Ví dụ Java 17+ với đầu ra ổn định

Để minh họa phép chuyển đổi mà không phụ thuộc tốc độ máy, chương trình sau dùng khoảng đã biết trước. Nó không phải benchmark:

~~~java
import java.time.Duration;

public class DurationPartsDemo {
    public static void main(String[] args) {
        Duration elapsed = Duration.ofMillis(2345);

        System.out.println("millis=" + elapsed.toMillis());
        System.out.println("seconds=" + elapsed.toSeconds());
        System.out.println("secondsPart=" + elapsed.toSecondsPart());
        System.out.println("millisPart=" + elapsed.toMillisPart());
        System.out.println("toString=" + elapsed);
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac DurationPartsDemo.java
java DurationPartsDemo
~~~

Stdout:

~~~text
millis=2345
seconds=2
secondsPart=2
millisPart=345
toString=PT2.345S
~~~

Đối với Duration dương 2,345 giây, toSeconds trả số giây nguyên là 2; toMillis vẫn giữ tổng mili giây là 2345. Đừng nhầm tổng đơn vị với thành phần phần dư.

## 8. Timeout, sleep và retry

Duration mô tả độ dài timeout/delay, nhưng **cách chờ và hủy tác vụ do API thực thi quyết định**.

- Với API nhận Duration, truyền rõ đơn vị: Duration.ofSeconds(2), Duration.ofMillis(250).
- Nếu API chỉ nhận long, đọc kỹ tham số là milliseconds, nanoseconds hay một đơn vị khác.
- Thread.sleep(long) nhận mili giây; Thread.sleep(millis, nanos) dùng hai tham số khác nhau. Không truyền trực tiếp Duration vào method không hỗ trợ.
- Với ScheduledExecutorService, đơn vị của schedule có thể được chỉ định bằng TimeUnit; Duration.toNanos có thể tràn với khoảng quá lớn, nên chọn conversion và giới hạn phù hợp.
- Với HTTP/client/database timeout, ưu tiên truyền vào cấu hình chính thức của thư viện, không chỉ kiểm tra Duration bên ngoài rồi giả định thao tác bên trong tự dừng.

Một delay 250 ms nghĩa là “không chạy sớm hơn/được lên lịch sau khoảng delay theo API” chứ không phải đảm bảo chính xác tiến hành tại thời điểm đó. Tải CPU, thread scheduling và GC có thể làm callback chạy muộn.

### Deadline tổng thể và timeout cho mỗi lần thử

Giả sử retry tối đa 3 lần, mỗi request có timeout 2 giây. Nếu mỗi lần đều bắt đầu timeout mới mà không kiểm tra deadline tổng thể, toàn bộ yêu cầu có thể chạy lâu hơn kỳ vọng (thêm delay và thời gian xử lý). Đối với một tổng deadline, tính mốc hết hạn hoặc ngân sách thời gian còn lại sau mỗi bước:

~~~java
Duration remaining = Duration.between(Instant.now(clock), deadline);
if (remaining.isZero() || remaining.isNegative()) {
    // Đã hết ngân sách thời gian
}
~~~

Đây là ví dụ về deadline theo đồng hồ lịch. Trong hệ thống cần timeout chắc chắn không bị ảnh hưởng bởi điều chỉnh đồng hồ tường trong khi request chạy, nên dùng đồng hồ monotonic hoặc cơ chế deadline của thư viện phù hợp. Cũng cần chú ý các hệ thống phân tán: Instant deadline có thể truyền qua mạng, nhưng sai số đồng hồ giữa máy gửi và máy nhận phải được tính đến.

## 9. Duration giữa ngày giờ địa phương và DST

Duration luôn là lượng thời gian theo giây/nano. Nhưng cộng Duration vào một kiểu ngày giờ địa phương có thể khác với cộng một ngày lịch.

Ví dụ với ZonedDateTime ở vùng có DST:

~~~java
ZonedDateTime start = ZonedDateTime.of(
        2026, 3, 7, 12, 0, 0, 0,
        ZoneId.of("America/New_York")
);
ZonedDateTime after24Hours = start.plus(Duration.ofHours(24));
ZonedDateTime nextCalendarDay = start.plusDays(1);
~~~

Theo quy tắc DST ở New York năm 2026, hai giá trị có thể có giờ địa phương khác nhau vì ngày chuyển sang giờ mùa hè chỉ có 23 giờ trên trục thời gian. **Duration.ofHours(24)** giữ độ dài 24 giờ; **plusDays(1)** giữ phép tiến một ngày theo quy tắc lịch của ZonedDateTime.

Không suy ra “ngày mai cùng giờ” bằng Duration.ofHours(24) nếu yêu cầu là giờ đồng hồ địa phương. Ngược lại, nếu nghiệp vụ cần chính xác 24 giờ trôi qua, Duration là cách diễn đạt đúng.

Nếu chỉ có hai **LocalDateTime** không vùng, Duration.between không thể tự biết vùng và DST. Khi phải đo khoảng thực tế, hãy xác định các Instant phù hợp trước.

## 10. Độ chính xác, giới hạn số học và dấu âm

Duration lưu độ dài theo giây và nano giây, nhưng các phương thức chuyển tổng sang kiểu long có giới hạn:

- **toMillis()** hoặc **toNanos()** có thể ném **ArithmeticException** nếu kết quả không vừa long.
- **toDays()** trả số ngày nguyên theo 24 giờ; phần còn lại không được biểu diễn trong số nguyên ngày này.
- **isNegative()** và **isZero()** giúp kiểm tra duration trước khi dùng làm timeout/TTL.
- Phép cộng/trừ Duration với Instant cũng bị giới hạn bởi miền giá trị của Instant; không phải giá trị lớn bất kỳ nào cũng hợp lệ.

Ví dụ kiểm tra đầu vào:

~~~java
Duration ttl = Duration.ofMinutes(15);

if (ttl.isZero() || ttl.isNegative()) {
    throw new IllegalArgumentException("ttl must be positive");
}
~~~

Đây là quy tắc do ứng dụng chọn. Một hệ thống khác có thể dùng **Duration.ZERO** để chỉ vô hiệu hóa timeout; quan trọng là hợp đồng phải rõ trước khi xử lý.

### Định dạng Duration

Duration.toString() dùng định dạng dựa trên ISO-8601, ví dụ:

~~~text
PT2.345S
PT15M
PT1H30M
PT-5S
~~~

Đây là biểu diễn kỹ thuật của lượng thời gian, không phải timestamp ngày/giờ. **PT15M** nghĩa 15 phút; nó không chứa ngày bắt đầu hay múi giờ.

## 11. Ví dụ nghiệp vụ: request có deadline tổng và đo thời lượng

Có thể vừa cần biết **request nhận lúc nào** vừa cần đo **xử lý mất bao lâu**. Hai mục đích cần hai nguồn tương ứng:

~~~java
Instant receivedAt = Instant.now(clock);  // Timestamp cho log
long startedTick = System.nanoTime();     // Tick để đo elapsed

// Gọi dịch vụ/đọc dữ liệu/xử lý...

long elapsedNanos = System.nanoTime() - startedTick;
Duration processingTime = Duration.ofNanos(elapsedNanos);
~~~

Nếu deadline là 2 giây tính từ lúc nhận, tạo **deadline = receivedAt.plus(Duration.ofSeconds(2))**. Tuy vậy khi thi hành timeout nội bộ, một deadline dựa trên Instant có thể bị ảnh hưởng nếu đồng hồ hệ thống thay đổi; hệ thống nhạy cảm cần chuyển thành ngân sách monotonic hoặc dùng deadline/timeout API phù hợp.

Đừng dùng một giá trị thời gian cho mọi mục đích chỉ để đơn giản code. Một timestamp phục vụ log và một bộ đếm phục vụ latency trả lời hai câu hỏi khác nhau.

## 12. Lỗi phổ biến và cách sửa

| Lỗi | Hậu quả | Cách sửa |
|---|---|---|
| Dùng **Duration.ofDays(30)** cho “một tháng lịch” | Một tháng có 28, 29, 30 hoặc 31 ngày | Dùng phép toán lịch/Period theo chính sách nghiệp vụ |
| Dùng Instant.now() trừ nhau để benchmark | Đồng hồ tường có thể bị điều chỉnh | Dùng System.nanoTime() |
| Dùng giá trị nanoTime tuyệt đối làm timestamp | Không liên hệ UTC và chỉ có nghĩa để đo chênh lệch trong JVM | Chỉ trừ hai lần đọc; dùng Instant cho timestamp |
| Kiểm tra **isAfter(deadline)** để xác định hết hạn | Đúng tại deadline vẫn có thể bị xem chưa hết hạn | Định nghĩa biên rõ; thường dùng **!now.isBefore(deadline)** |
| Gọi now nhiều lần trong một quyết định | Có thể vượt deadline giữa các phép so sánh | Chụp một Instant rồi dùng lại |
| Truyền Duration.toNanos() cho API với khoảng cực lớn | Có thể tràn long | Kiểm tra giới hạn và dùng đơn vị/hàm API phù hợp |
| Coi Duration là đồng hồ đếm ngược | Nó chỉ là giá trị lượng thời gian, không tự chạy | Kết hợp Clock/Instant hoặc scheduler/timer |
| Mong sleep/retry chính xác tới mili giây | Scheduler và hệ điều hành có thể chạy muộn | Thiết kế deadline, timeout và đo latency phù hợp |
| Dùng LocalTime để đo ca qua nửa đêm | Không có ngày nên kết quả khoảng thời gian có thể âm | Ghép ngày hoặc dùng Instant |
| Cộng 24 giờ và nghĩ luôn là cùng giờ ngày mai | DST khiến giờ địa phương có thể lệch | Dùng ZonedDateTime.plusDays(1) cho phép toán lịch |
| Coi Duration âm là vô hạn | Ý nghĩa không chuẩn chung | Xác định rõ chính sách 0/âm trong API |
| Đo thời gian một lần rồi kết luận hiệu năng | Nhiễu JIT/GC/scheduler | Dùng benchmark thích hợp và nhiều lần lặp |

## 13. Checklist áp dụng Duration

Trước khi dùng Duration, hãy trả lời:

1. **Đó là lượng thời gian hay một thời điểm?** Lượng thời gian dùng Duration; deadline cần Instant hoặc một kiểu lịch/vùng phù hợp.
2. **Yêu cầu là thời gian thực sự trôi qua hay phép tiến lịch?** 24 giờ khác một ngày địa phương tại DST.
3. **Đo latency bằng gì?** Dùng System.nanoTime() cho chênh lệch trong cùng JVM.
4. **Deadline có quy tắc biên rõ chưa?** Chẳng hạn hết hạn khi now >= deadline.
5. **Timeout có tổng deadline không?** Đừng cấp lại toàn bộ timeout mỗi lần retry nếu cần một giới hạn tổng.
6. **Duration có thể âm/0 không?** Định nghĩa và validate chính sách.
7. **Có thể tràn khi đổi sang millis/nanos không?** Kiểm tra khoảng lớn.
8. **Clock có được tiêm vào service để test không?** Dùng Clock.fixed/offset cho biên trước, tại và sau hạn.
9. **Các ví dụ đo thời gian có phân biệt timestamp với elapsed không?**
10. **Kết quả API/database có giữ đơn vị và ý nghĩa không?**

### Câu hỏi tự kiểm tra

**1. Duration.ofMinutes(15) có phải thời điểm hết hạn?**  
Không. Đây là lượng thời gian 15 phút. Cộng nó vào Instant của lúc cấp mới tạo deadline.

**2. Nên dùng gì để đo latency trong cùng JVM?**  
Dùng hiệu giữa hai lần gọi System.nanoTime(), rồi có thể gói hiệu đó thành Duration.ofNanos(...).

**3. Token hết hạn khi now bằng expiresAt chưa?**  
Theo khoảng hiệu lực nửa mở [issuedAt, expiresAt), token đã hết hạn khi now >= expiresAt.

**4. Duration.ofDays(1) có giống ngày mai cùng giờ ở mọi múi giờ?**  
Không. Duration.ofDays(1) là 24 giờ; ngày lịch ở vùng DST có thể dài 23 hoặc 25 giờ.

**5. Duration.between(LocalTime.of(23,30), LocalTime.of(1,0)) có tự trả 90 phút?**  
Không. LocalTime không có ngày và phép tính không tự suy ra nửa đêm; phải dùng ngày đầy đủ hoặc quy tắc nghiệp vụ tường minh.

**6. Tại sao Clock.fixed hữu ích cho test deadline?**  
Nó cho phép xác định chính xác “now” mà không cần chờ thời gian thật trôi qua. Clock.offset có thể mô phỏng trước/đúng/sau deadline.

**7. Duration tự hủy một tác vụ khi hết hạn?**  
Không. Nó chỉ biểu diễn lượng thời gian. Timeout phải được thực thi bởi API/client/scheduler hoặc logic ứng dụng phù hợp.

**Ghi nhớ:** Duration trả lời **“bao lâu?”**, còn Instant trả lời **“khi nào?”**. Deadline được tạo từ một mốc thời gian cộng Duration; phép đo latency cần đồng hồ monotonic; ngày lịch và giờ địa phương cần các kiểu lịch cùng ZoneId. Khi xác định rõ từng ý nghĩa này, timeout, retry và thời hạn dễ kiểm thử hơn và ít mắc lỗi biên.
