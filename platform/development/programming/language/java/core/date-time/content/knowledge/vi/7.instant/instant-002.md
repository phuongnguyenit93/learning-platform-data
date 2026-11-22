# Tạo thời điểm hiện tại từ đồng hồ với Instant và Clock trong Java

Khi ứng dụng cần ghi lại **thời điểm một hành động xảy ra**, câu hỏi “bây giờ là lúc nào?” thường được trả lời bằng **Instant.now()**. Tuy nhiên, trong nghiệp vụ thực tế còn cần biết **đồng hồ nào cung cấp thời gian**, độ chính xác có thể tin cậy tới đâu, và làm thế nào để viết phép thử không phụ thuộc vào giờ thực tế của máy.

Java cung cấp **java.time.Instant** để biểu diễn một **thời điểm trên trục thời gian UTC**, và **java.time.Clock** để cung cấp nguồn thời gian cho các phép gọi “hiện tại”. Sử dụng hai lớp đúng cách giúp mã xử lý thời gian rõ nghĩa, dễ kiểm thử và tránh lệ thuộc vào múi giờ mặc định của máy chủ.

Bài học tập trung vào **Instant.now()**, **Instant.now(Clock)**, **Clock.systemUTC()**, **Clock.fixed(...)**, cùng các biến thể **Clock.offset(...)**, **Clock.tick(...)** và cách áp dụng trong ứng dụng Java 17+.

## 1. Instant và Clock có nhiệm vụ khác nhau

| Thành phần | Đại diện cho | Ví dụ |
|---|---|---|
| **Instant** | Một thời điểm tuyệt đối trên trục thời gian | Đơn hàng tạo lúc 2026-10-24T10:15:30Z |
| **Clock** | Nguồn cung cấp “thời gian hiện tại”, kèm ZoneId để phục vụ các API cần ngày giờ địa phương | Đồng hồ hệ thống UTC, đồng hồ cố định trong test |
| **ZoneId** | Danh tính vùng với quy tắc offset/DST | Asia/Ho_Chi_Minh, Europe/Paris |
| **Duration** | Khoảng thời gian đã trôi qua theo đơn vị giây/nano giây | Token còn hiệu lực 5 phút |

**Instant** là một giá trị thời gian; **Clock** là cách lấy một giá trị “bây giờ”. Một đối tượng Instant sau khi tạo sẽ không tự tăng theo thời gian: đọc lại biến đó chỉ trả về cùng mốc đã ghi nhận.

~~~java
import java.time.Instant;

Instant capturedAt = Instant.now();
Instant sameValue = capturedAt; // Vẫn là thời điểm đã lấy trước đó
Instant anotherSample = Instant.now(); // Gọi đồng hồ lần nữa
~~~

Đoạn trên là **minh họa**, không phải một chương trình độc lập. **anotherSample** thường muộn hơn **capturedAt**, nhưng không nên viết test mặc định nó phải lớn hơn: độ phân giải đồng hồ có thể khiến hai lần đọc bằng nhau, và đồng hồ hệ thống có thể bị điều chỉnh.

## 2. Instant.now(): lấy thời điểm hiện tại từ đồng hồ hệ thống

Cách phổ biến nhất:

~~~java
Instant createdAt = Instant.now();
~~~

**Instant.now()** dùng đồng hồ hệ thống để lấy thời điểm hiện tại; không cần truyền tham số. Giá trị trả về là **Instant**, phù hợp với dữ liệu như:

- Thời điểm tạo hoặc cập nhật bản ghi (**createdAt**, **updatedAt**).
- Thời điểm hoàn tất giao dịch hoặc nhận một sự kiện.
- Mốc bắt đầu và hết hạn của phiên/token, khi chính sách dùng thời điểm tuyệt đối.
- Thời điểm phát hành thông điệp hay ghi nhận thao tác hệ thống.

Ví dụ kết quả **minh họa** (không phải stdout cố định):

~~~text
2026-10-24T10:15:30.123Z
~~~

Ký hiệu **Z** trong biểu diễn ISO-8601 là UTC offset **+00:00**. **Instant** không tự chứa múi giờ của người dùng, ngày giờ tường địa phương hoặc tên vùng IANA.

**Quan trọng:** chương trình chạy vào các thời điểm khác nhau sẽ in Instant khác nhau. Vì vậy không đưa một giá trị timestamp cụ thể vào phần “đầu ra chính xác” cho ví dụ gọi **Instant.now()** trực tiếp.

### “Thời điểm hiện tại” không đồng nghĩa “thời gian chắc chắn đúng tuyệt đối”

Đồng hồ hệ thống của máy có thể sai, được đồng bộ qua NTP, bị quản trị viên chỉnh, hoặc nhận điều chỉnh khi chạy trong môi trường ảo hóa. **Instant.now()** phản ánh **nguồn thời gian mà hệ điều hành/JVM cung cấp**; API không bảo đảm đồng hồ luôn chính xác với đồng hồ chuẩn hoặc luôn tăng đều giữa các lần đọc.

Ngoài ra, **Instant** có khả năng biểu diễn phần nano giây, nhưng **độ chính xác và độ phân giải thực tế của Instant.now() phụ thuộc môi trường**. Không suy ra máy có độ chính xác nano giây chỉ vì kiểu Instant có trường nano giây.

## 3. Instant.now(Clock): chủ động chọn nguồn thời gian

Thay vì đọc đồng hồ mặc định ngầm định:

~~~java
Instant now = Instant.now();
~~~

có thể truyền một **Clock**:

~~~java
Clock clock = Clock.systemUTC();
Instant now = Instant.now(clock);
~~~

Hai cách đều tạo Instant ứng với thời điểm hiện tại từ nguồn thời gian hệ thống tại lúc gọi. Trong ví dụ thứ hai, nguồn thời gian là **tham số tường minh**, có thể thay bằng đồng hồ cố định khi kiểm thử.

**Clock.systemUTC()** trả về đồng hồ hệ thống sử dụng vùng **UTC**. ZoneId của Clock hữu ích với các API ngày giờ địa phương, nhưng bản thân **Instant** vẫn biểu diễn một thời điểm tuyệt đối. **Instant.now(clock)** lấy thời điểm từ Clock, không “gán giờ địa phương” vào Instant.

Một cách đọc tương đương về ý định là:

~~~java
Instant a = Instant.now(clock);
Instant b = clock.instant();
~~~

Hai lời gọi trên không nhất thiết trả về **đúng cùng giá trị** nếu Clock đang chạy, vì chúng được thực hiện ở hai thời điểm khác nhau. Với **Clock.fixed(...)**, cả hai trả về cùng một Instant.

### Tại sao nhận Clock từ bên ngoài?

Nếu service tự gọi **Instant.now()** ở nhiều chỗ, phép thử phải chạy đúng tại thời điểm ngoài đời hoặc dùng biên thời gian khó kiểm soát. Khi service nhận Clock, phép thử chỉ cần truyền **Clock.fixed(...)**, từ đó có thể mô phỏng “bây giờ” chính xác mà không chờ thời gian thật trôi qua.

Đây là lý do **dependency injection cho Clock** hữu ích ngay cả trong một ứng dụng nhỏ. Service phụ thuộc vào **khái niệm nguồn thời gian**, còn môi trường chạy quyết định sử dụng đồng hồ thật hay đồng hồ giả có kiểm soát.

## 4. Những cách tạo Clock thường dùng

| Cách tạo | Ý nghĩa và ứng dụng |
|---|---|
| **Clock.systemUTC()** | Đồng hồ hệ thống có vùng UTC; phù hợp làm nguồn mặc định cho dấu thời gian |
| **Clock.systemDefaultZone()** | Đồng hồ hệ thống với vùng mặc định JVM; có ích nếu API đọc ngày giờ địa phương cần vùng đó, nhưng cần tránh phụ thuộc ngầm vào cấu hình máy |
| **Clock.system(zone)** | Đồng hồ hệ thống gắn ZoneId được chọn rõ |
| **Clock.fixed(instant, zone)** | Luôn trả về **cùng Instant**; dùng cho test và ví dụ có kết quả tái lập được |
| **Clock.offset(baseClock, duration)** | Tạo đồng hồ đọc thời gian lệch so với đồng hồ gốc; hữu ích để mô phỏng trước/sau hạn |
| **Clock.tick(baseClock, tickDuration)** | Trả thời gian được cắt theo bước tick; dùng khi thực sự muốn lượng tử hóa thời điểm lấy mẫu |
| **clock.withZone(zone)** | Tạo Clock tương đương với vùng khác, **không** tự sửa Instant do nguồn thời gian trả về |

### Đồng hồ hệ thống theo UTC hay theo múi giờ máy?

~~~java
Clock utc = Clock.systemUTC();
Clock localSystem = Clock.systemDefaultZone();

Instant first = Instant.now(utc);
Instant second = Instant.now(localSystem);
~~~

**first** và **second** đều là Instant. Chúng có thể chênh nhau vì được đọc **liên tiếp tại hai thời điểm**, không phải vì ZoneId tạo ra một thời điểm khác trên trục thời gian. Đừng kiểm thử bằng **first.equals(second)** cho hai lời gọi đồng hồ đang chạy.

Khi cần **LocalDate.now(clock)** hoặc **ZonedDateTime.now(clock)**, **clock.getZone()** mới trực tiếp ảnh hưởng ngày/giờ địa phương được trả về. Nếu nghiệp vụ tính ngày kết thúc tại Hà Nội, nên truyền **ZoneId.of("Asia/Ho_Chi_Minh")** rõ ràng, thay vì phụ thuộc múi giờ của container chạy ứng dụng.

### Clock.fixed: đóng băng thời điểm trong phép thử

~~~java
Clock frozen = Clock.fixed(
        Instant.parse("2026-10-24T10:15:30Z"),
        ZoneOffset.UTC
);

Instant one = Instant.now(frozen);
Instant two = Instant.now(frozen);
~~~

**one** và **two** cùng bằng **2026-10-24T10:15:30Z** bất kể phép thử chạy lúc nào. Bạn có thể dùng một thời điểm bất kỳ hợp lệ; nên chọn giá trị dễ đọc và tường minh.

Khi chạy production, không dùng **Clock.fixed** làm nguồn thời gian thật cho các nghiệp vụ cần cập nhật liên tục: mọi lần đọc từ đồng hồ cố định sẽ tiếp tục trả về cùng một mốc.

## 5. Múi giờ của Clock ảnh hưởng gì đến Instant?

Với cùng một đồng hồ cố định:

~~~java
Clock utc = Clock.fixed(
        Instant.parse("2026-10-24T10:15:30Z"),
        ZoneOffset.UTC
);
Clock hcm = utc.withZone(ZoneId.of("Asia/Ho_Chi_Minh"));
~~~

Kết quả của **Instant.now(utc)** và **Instant.now(hcm)** giống hệt nhau. Nhưng kết quả **LocalDateTime.now(utc)** là **10:15:30**, còn **LocalDateTime.now(hcm)** là **17:15:30** cùng ngày theo vùng +07:00.

Đây là điểm cần nhớ:

- **Clock** cung cấp Instant và ZoneId.
- **Instant.now(clock)** quan tâm tới Instant của Clock.
- **LocalDateTime.now(clock)** dùng vùng gắn trên Clock để biểu diễn ngày/giờ tường.
- Việc chuyển **Instant** sang ngày giờ địa phương cần gọi **instant.atZone(zone)** hoặc API tương ứng với ZoneId.
- Thay ZoneId **không làm thay đổi thời điểm thật** được diễn đạt bởi Instant.

Nói “Instant trong múi giờ +07:00” dễ gây nhầm. Nên nói “Instant được hiển thị ở múi giờ +07:00” hoặc “Instant được biểu diễn thành ZonedDateTime tại vùng đó”.

## 6. Chương trình Java 17+ với đồng hồ cố định, đổi vùng, offset và tick

Tạo tệp **InstantClockDemo.java**:

~~~java
import java.time.Clock;
import java.time.Duration;
import java.time.Instant;
import java.time.LocalDateTime;
import java.time.ZoneId;
import java.time.ZoneOffset;

public class InstantClockDemo {
    public static void main(String[] args) {
        Clock fixedUtc = Clock.fixed(
                Instant.parse("2026-10-24T10:15:30Z"),
                ZoneOffset.UTC
        );
        Clock fixedHcm = fixedUtc.withZone(
                ZoneId.of("Asia/Ho_Chi_Minh")
        );

        System.out.println("instantUTC=" + Instant.now(fixedUtc));
        System.out.println("instantHCM=" + Instant.now(fixedHcm));
        System.out.println("sameInstant=" +
                Instant.now(fixedUtc).equals(Instant.now(fixedHcm)));

        System.out.println("localUTC=" + LocalDateTime.now(fixedUtc));
        System.out.println("localHCM=" + LocalDateTime.now(fixedHcm));

        Clock tenMinutesLater = Clock.offset(
                fixedUtc, Duration.ofMinutes(10)
        );
        System.out.println("plus10m=" + Instant.now(tenMinutesLater));

        Clock roundedToMinute = Clock.tick(
                fixedUtc, Duration.ofMinutes(1)
        );
        System.out.println("tickMinute=" + Instant.now(roundedToMinute));
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac InstantClockDemo.java
java InstantClockDemo
~~~

Stdout chính xác:

~~~text
instantUTC=2026-10-24T10:15:30Z
instantHCM=2026-10-24T10:15:30Z
sameInstant=true
localUTC=2026-10-24T10:15:30
localHCM=2026-10-24T17:15:30
plus10m=2026-10-24T10:25:30Z
tickMinute=2026-10-24T10:15:00Z
~~~

**Giải thích:**

1. Hai Clock có ZoneId khác nhau nhưng cùng Instant cố định nên hai dòng **instant** giống nhau.
2. **LocalDateTime.now(clock)** phụ thuộc múi giờ gắn với Clock nên hơn nhau 7 giờ ở ví dụ này.
3. **Clock.offset** dịch nguồn thời gian thêm đúng 10 phút; dùng để kiểm tra các mốc trước và sau thời hạn.
4. **Clock.tick** với bước 1 phút trả thời gian đã cắt xuống mốc phút, nên **10:15:30Z** thành **10:15:00Z**. Nó không tự làm cho thời gian hệ thống chính xác hơn.

**Lưu ý:** Clock.tick có thể trả các giá trị bị lượng tử hóa hoặc trễ theo hành vi triển khai/cache; chỉ dùng nếu yêu cầu thật sự là lấy mẫu theo bước. Không dùng một đồng hồ đã cắt phút để đưa ra quyết định hết hạn cần chính xác tới giây hoặc nano giây.

## 7. Đưa Clock vào service: ví dụ hết hạn token

Nghiệp vụ thường cần câu trả lời ổn định:

- Khi cấp token, thời điểm hết hạn bằng **thời điểm cấp + thời lượng hiệu lực**.
- Tại đúng mốc hết hạn, token được coi là **hết hạn**.
- Trước hạn, token còn hiệu lực.
- Không phải dùng **Thread.sleep(...)** để test thời gian trôi qua.

Tạo tệp **TokenExpiryDemo.java**:

~~~java
import java.time.Clock;
import java.time.Duration;
import java.time.Instant;
import java.time.ZoneOffset;
import java.util.Objects;

public class TokenExpiryDemo {
    private final Clock clock;

    public TokenExpiryDemo(Clock clock) {
        this.clock = Objects.requireNonNull(clock, "clock");
    }

    public Instant expiresAfter(Duration ttl) {
        if (ttl == null || ttl.isZero() || ttl.isNegative()) {
            throw new IllegalArgumentException(
                    "ttl must be a positive duration"
            );
        }
        Instant issuedAt = Instant.now(clock);
        return issuedAt.plus(ttl);
    }

    public boolean isExpired(Instant expiresAt) {
        Objects.requireNonNull(expiresAt, "expiresAt");
        Instant checkedAt = Instant.now(clock);
        return !checkedAt.isBefore(expiresAt);
    }

    public static void main(String[] args) {
        Clock base = Clock.fixed(
                Instant.parse("2026-10-24T10:15:30Z"),
                ZoneOffset.UTC
        );

        TokenExpiryDemo atStart = new TokenExpiryDemo(base);
        Instant expiresAt = atStart.expiresAfter(
                Duration.ofMinutes(5)
        );

        System.out.println("expiresAt=" + expiresAt);
        System.out.println("expiredAtStart=" +
                atStart.isExpired(expiresAt));

        Clock atBoundary = Clock.offset(
                base, Duration.ofMinutes(5)
        );
        Clock afterBoundary = Clock.offset(
                base, Duration.ofMinutes(6)
        );

        System.out.println("expiredAtBoundary=" +
                new TokenExpiryDemo(atBoundary).isExpired(expiresAt));
        System.out.println("expiredAfterBoundary=" +
                new TokenExpiryDemo(afterBoundary).isExpired(expiresAt));
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac TokenExpiryDemo.java
java TokenExpiryDemo
~~~

Stdout:

~~~text
expiresAt=2026-10-24T10:20:30Z
expiredAtStart=false
expiredAtBoundary=true
expiredAfterBoundary=true
~~~

**Tại sao ví dụ này đáng học?** Đồng hồ cố định giúp phép thử có kết quả chắc chắn, còn **Clock.offset** giả lập việc thời gian tiến đến đúng giới hạn và qua giới hạn mà không cần ngủ/chờ. Phương thức **isExpired** dùng **!now.isBefore(expiresAt)**, tương đương quy tắc **now >= expiresAt** trên trục thời gian.

Trong ứng dụng thực tế, thường khai báo một **Clock** chung tại lớp cấu hình, ví dụ **Clock.systemUTC()**, rồi truyền vào service. Khi test, thay thế bằng **Clock.fixed(...)** hoặc một Clock điều khiển được. Có thể cung cấp service qua constructor; ví dụ ở đây dùng Java thuần, không cần Spring.

### Chỉ lấy “now” một lần cho một quyết định

Nếu một quy tắc nghiệp vụ có nhiều so sánh phải dùng **cùng một thời điểm quan sát**, hãy đọc **Instant.now(clock)** một lần rồi dùng lại:

~~~java
Instant checkedAt = Instant.now(clock);
boolean isActive = !checkedAt.isBefore(validFrom)
        && checkedAt.isBefore(validUntil);
~~~

Đoạn mã minh họa giả định **validFrom** và **validUntil** là các Instant hợp lệ, với quy tắc khoảng **[validFrom, validUntil)**. Gọi now nhiều lần trong một quyết định có thể tạo kết quả không nhất quán nếu đồng hồ tiến qua ranh giới giữa các phép so sánh.

## 8. Clock.offset và Clock.tick: mô phỏng thời gian đúng mục đích

### Clock.offset: tạo góc nhìn “sau N phút”

~~~java
Clock base = Clock.fixed(
        Instant.parse("2026-10-24T10:15:30Z"),
        ZoneOffset.UTC
);
Clock later = Clock.offset(base, Duration.ofHours(2));
Clock earlier = Clock.offset(base, Duration.ofMinutes(-30));
~~~

Các đồng hồ **later** và **earlier** cung cấp thời điểm cộng hoặc trừ lượng thời gian tương ứng so với **base**. Nếu base là đồng hồ hệ thống, offset cũng **trôi theo đồng hồ hệ thống**; nếu base là Clock.fixed, offset tiếp tục cố định. **Clock.offset** không điều chỉnh đồng hồ hệ điều hành.

Ứng dụng điển hình là test hạn sử dụng, khoảng mở đăng ký, kiểm tra chính sách “chỉ cho phép từ thời điểm X”, hoặc tái tạo các kịch bản trước/sau sự kiện.

### Clock.tick: giới hạn bước hiển thị/đọc thời gian

~~~java
Clock wholeSeconds = Clock.tick(
        Clock.systemUTC(),
        Duration.ofSeconds(1)
);
~~~

Đồng hồ này trả giá trị đã cắt theo bước một giây theo hợp đồng tick. Nó có thể phù hợp với yêu cầu “chỉ cần phân giải tới giây”, nhưng **không bảo đảm bộ đếm độc lập sẽ tăng đúng mỗi giây**, cũng không thay thế bộ hẹn giờ. Ứng dụng không nên phụ thuộc vào tick để bảo đảm thứ tự sự kiện sát nhau.

Bước tick cần phù hợp với yêu cầu và hợp lệ theo hợp đồng API; không chọn tick theo thói quen chỉ để loại phần mili/nano giây.

## 9. Độ chính xác, tính tăng đều và đo thời gian thực thi

### 9.1. Instant.now là đồng hồ tường (wall clock)

Thời điểm hiện tại có ý nghĩa khi so sánh với mốc lịch, ví dụ:

- “Bản ghi này được tạo vào lúc nào?”
- “Token đã hết hạn theo đồng hồ hệ thống chưa?”
- “Đến giờ công bố kết quả hay chưa?”

Với dữ liệu dạng **timestamp**, Instant thường phù hợp. Nhưng sự khác nhau giữa hai Instant đọc từ đồng hồ hệ thống **không phải lúc nào cũng là thời lượng chạy tác vụ đáng tin cậy** nếu đồng hồ bị điều chỉnh trong lúc chạy.

### 9.2. Đo thời gian xử lý: dùng bộ đếm monotonic

Để đo latency của đoạn code trên một JVM, chọn **System.nanoTime()** thay vì dùng Instant.now() làm đồng hồ bấm giờ:

~~~java
long startTick = System.nanoTime();
// Thực hiện công việc cần đo tại đây
long elapsedNanos = System.nanoTime() - startTick;
~~~

Đoạn này là **minh họa**; kết quả phụ thuộc công việc và môi trường. **System.nanoTime()** dành cho chênh lệch thời gian trong cùng quá trình/JVM, không phải Unix timestamp, không biểu diễn ngày giờ và không nên lưu như Instant. Không chuyển giá trị tuyệt đối của nanoTime sang UTC.

**Clock** mặc định của java.time không cam kết là monotonic. Nếu xử lý timeout cực kỳ nhạy cảm với đồng hồ lùi hoặc tiến do điều chỉnh hệ thống, nên dựa trên thời lượng monotonic do cơ chế timeout cung cấp. Đối với hạn nghiệp vụ cần so sánh qua các dịch vụ, vẫn cần một quy tắc về thời điểm tuyệt đối và độ tin cậy đồng hồ của từng máy.

### 9.3. Instant có nano giây không đồng nghĩa nguồn đo có độ phân giải nano

~~~java
Instant now = Instant.now();
int nanoFraction = now.getNano();
~~~

**getNano()** là phần nano giây trong một giây của Instant, không phải bằng chứng máy có thể đo chính xác nano giây. Trên hệ thống cụ thể, phần nano có thể phản ánh độ phân giải mili/micro/nano tùy cách nền tảng cấp thời gian. Ngoài ra, **Clock.millis()** chỉ cung cấp mili giây nên có thể mất độ chính xác dưới mili giây khi dùng **Instant.ofEpochMilli(clock.millis())**.

Không dùng các giá trị timestamp để tạo khóa duy nhất tuyệt đối: nhiều sự kiện có thể ghi nhận cùng timestamp. Dùng ID hoặc sequence được thiết kế cho tính duy nhất.

## 10. Thiết kế API và lưu trữ thời điểm tạo

### 10.1. Lưu Instant như một mốc tuyệt đối

Một payload tiêu biểu:

~~~json
{
  "createdAt": "2026-10-24T10:15:30Z",
  "expiresAt": "2026-10-24T10:20:30Z"
}
~~~

Trong hợp đồng API, chỉ rõ các trường này là **Instant** hay timestamp theo UTC, cách parse ISO-8601, độ chính xác mong muốn và ý nghĩa của biên hết hạn. Ví dụ nếu **expiresAt** là mốc đầu tiên không còn hiệu lực, dùng điều kiện **now >= expiresAt** để hết hạn.

Không lấy “createdAt = LocalDateTime.now()” ở một máy chủ rồi giả sử giá trị đó là UTC. **LocalDateTime** không mang thông tin offset hoặc zone để xác định một Instant.

### 10.2. Khi hiển thị cho người dùng

~~~java
Instant createdAt = Instant.parse("2026-10-24T10:15:30Z");

ZonedDateTime inVietnam = createdAt.atZone(
        ZoneId.of("Asia/Ho_Chi_Minh")
);
~~~

Giờ hiển thị ở vùng Việt Nam là **17:15:30** ngày **24/10/2026**, nhưng **createdAt** gốc vẫn là cùng Instant. Đừng lưu đè timestamp gốc sau khi áp dụng vùng hiển thị.

Nếu ứng dụng cần thông tin “09:00 sáng tại cửa hàng” như lịch lặp, kiểu đầu vào thường là **LocalTime + ZoneId**, sau đó tính từng lần thực hiện thành Instant. **Instant.now()** là nguồn “bây giờ” trên trục thời gian, không thay thế mô hình lịch lặp.

### 10.3. Đồng bộ máy chủ và cơ sở dữ liệu

Nếu dữ liệu được tạo từ nhiều máy chủ, chúng có thể đọc đồng hồ hệ thống lệch nhau. Dù dùng Instant, thứ tự timestamp **chỉ chính xác trong giới hạn mức đồng bộ và sai số của nguồn thời gian**.

Nếu cơ sở dữ liệu và ứng dụng đều có cơ chế cấp **createdAt**, nên xác định **một nguồn chân lý** cho trường đó, tránh tình trạng mỗi tầng tự gán thời gian rồi ghi đè lẫn nhau. Lưu và truy xuất Instant phải được kiểm thử với driver/ORM/cơ sở dữ liệu cụ thể để bảo toàn độ chính xác cần thiết. Một số kiểu timestamp trong cơ sở dữ liệu giữ một thời điểm tuyệt đối nhưng **không bảo toàn tên ZoneId**; muốn lưu vùng nghiệp vụ phải có trường riêng.

## 11. Các lỗi thường gặp

| Cách dùng dễ sai | Vấn đề | Cách sửa |
|---|---|---|
| Test so sánh **Instant.now()** với một literal cứng | Kết quả phụ thuộc lúc chạy | Tiêm **Clock.fixed(...)** |
| Gọi now nhiều lần trong một quyết định hợp lệ/hết hạn | Có thể vượt qua ranh giới giữa hai lần đọc | Đọc **Instant checkedAt** một lần |
| Nghĩ Clock.systemUTC bảo đảm đồng hồ máy luôn chính xác | Nguồn hệ thống vẫn có thể lệch hoặc bị chỉnh | Giám sát/đồng bộ nguồn thời gian; phân biệt độ chính xác với kiểu dữ liệu |
| Cho rằng Instant.now và Instant.now(clock) luôn bằng nhau khi clock hệ thống | Hai lần lấy mẫu diễn ra ở thời điểm khác nhau | Chỉ so sánh trong test với Clock.fixed |
| Đổi zone của Clock rồi mong Instant đổi theo | ZoneId không làm đổi một thời điểm tuyệt đối | Dùng **ZonedDateTime** cho biểu diễn địa phương |
| Dùng LocalDateTime.now làm timestamp UTC không kèm vùng | Mất offset/zone | Dùng **Instant.now(clock)** |
| Sử dụng **Clock.fixed** trong production cho đồng hồ thực | Tất cả timestamp mới bị đóng băng | Cung cấp **Clock.systemUTC()** khi chạy thật |
| Dùng Clock.tick theo phút cho mốc hết hạn cần chính xác tới giây | Mất thông tin dưới phút | Dùng Clock không bị lượng tử hóa |
| Dùng **Instant.now()** tính thời lượng benchmark | Đồng hồ tường có thể nhảy | Dùng **System.nanoTime()** hoặc công cụ đo monotonic |
| Nghĩ Instant hỗ trợ nano nên máy đo chính xác đến nano | Khả năng kiểu và độ chính xác đồng hồ khác nhau | Xác định độ chính xác thực tế và chính sách lưu |
| Dùng Instant.now() làm khóa bản ghi duy nhất | Nhiều sự kiện có thể cùng timestamp | Dùng ID/sequence riêng |
| Gán ngày địa phương bằng **ZoneId.systemDefault()** không kiểm soát | Container hoặc máy dev có zone khác | Nhận ZoneId tường minh từ yêu cầu nghiệp vụ |
| Cho rằng “now” trên hai server phải tăng theo thứ tự nhận yêu cầu | Sai số clock, độ trễ và cạnh tranh có thể đảo thứ tự | Tạo thứ tự bằng cơ chế giao dịch/sequence thích hợp khi cần |

## 12. Checklist triển khai và kiểm thử

Trước khi quyết định nơi gọi “thời điểm hiện tại”, hãy kiểm tra:

1. Nghiệp vụ cần **một Instant** (thời điểm tuyệt đối) hay **LocalDate/LocalTime** (ngày hoặc giờ theo địa phương)?
2. Dịch vụ dùng **Clock** được truyền từ ngoài hay gọi now trực tiếp?
3. Production cung cấp **Clock.systemUTC()** hay một nguồn được cấu hình rõ khác?
4. Test có dùng **Clock.fixed** để nhận kết quả lặp lại, không cần sleep?
5. Quy tắc biên **at/after expiresAt** có được định nghĩa rõ không?
6. Nếu cần dịch thời gian trong test, có thể dùng **Clock.offset** và kiểm tra trước/đúng/sau biên?
7. Có đoạn logic nào gọi now hai lần nhưng đáng lẽ phải dùng cùng một mốc kiểm tra?
8. Các giá trị **UTC Instant** có được tách khỏi **ZoneId** dùng hiển thị cho khách hàng?
9. Có yêu cầu đo **thời lượng chạy thực tế** không? Nếu có, cần monotonic clock thay vì wall clock.
10. Hệ thống nhiều server có chiến lược bảo đảm độ chính xác giờ và thứ tự sự kiện phù hợp không?

### Câu hỏi tự đánh giá

**1. Instant.now() trả về gì?**  
Một Instant biểu diễn thời điểm hiện tại theo nguồn đồng hồ hệ thống; không chứa ZoneId của người dùng.

**2. Vì sao ưu tiên Instant.now(clock) trong service?**  
Có thể thay đồng hồ thật bằng Clock.fixed hoặc Clock.offset trong test, làm kết quả tái lập được.

**3. Hai Clock.fixed có cùng Instant nhưng ZoneId khác nhau: Instant.now(clock) có khác không?**  
Không. Instant giống nhau; cách biểu diễn LocalDateTime/ZonedDateTime theo vùng có thể khác.

**4. Clock.tick(base, Duration.ofMinutes(1)) là cách tăng độ chính xác?**  
Không. Nó cắt/giới hạn thời gian về các mốc tick và có thể làm mất thông tin nhỏ hơn một phút.

**5. Token hết hạn đúng 10:20:30Z: đọc đồng hồ được 10:20:30Z, token còn hiệu lực không?**  
Theo quy tắc khoảng hiệu lực **[createdAt, expiresAt)**, token đã hết hạn vì now **không còn trước** expiresAt.

**6. Muốn đo thời gian chạy 300 micro giây, nên dùng Instant.now hay System.nanoTime?**  
Dùng bộ đếm thời lượng **System.nanoTime()**; độ phân giải thực tế còn tùy nền tảng.

**7. Nếu gọi Instant.now() hai lần và nhận cùng một giá trị, chương trình bị lỗi?**  
Không nhất thiết. Độ phân giải đồng hồ có thể khiến hai lần lấy mẫu cùng timestamp.

**Ghi nhớ:** **Instant** trả lời “sự kiện xảy ra ở thời điểm tuyệt đối nào?”, còn **Clock** trả lời “lấy khái niệm bây giờ từ nguồn nào?”. Với nghiệp vụ có thể kiểm thử, **truyền Clock vào service**, dùng **Clock.systemUTC()** trong môi trường thật và **Clock.fixed(...)** trong test. Khi cần tính giờ địa phương, bổ sung ZoneId; khi cần đo latency, dùng nguồn monotonic phù hợp.
