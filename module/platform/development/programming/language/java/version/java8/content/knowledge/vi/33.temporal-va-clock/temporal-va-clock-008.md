# Truyền Clock vào ứng dụng để kiểm thử xác định trong Java

**Chủ đề:** Java 8 → Temporal và Clock → Truyền Clock vào ứng dụng để kiểm thử xác định.

Trong ứng dụng Java, những dòng như **Instant.now()**, **LocalDate.now()**, **LocalDateTime.now()** và **ZonedDateTime.now()** thường rất tiện. Tuy nhiên, khi một service tự đọc đồng hồ hệ thống, kết quả phụ thuộc **thời điểm thực tế chạy chương trình** và đôi khi cả **múi giờ mặc định của máy chủ**. Vì vậy, một unit test có thể thành công vào buổi sáng nhưng thất bại lúc nửa đêm, hoặc chạy đúng ở máy phát triển nhưng sai trên CI.

Giải pháp hiện đại, có sẵn từ Java 8, là **truyền java.time.Clock vào lớp hoặc hàm cần biết thời điểm hiện tại**. Trong môi trường vận hành, Clock sử dụng đồng hồ hệ thống. Trong kiểm thử, Clock được thay bằng **Clock.fixed(...)** hoặc một Clock được xây dựng có chủ ý, giúp bài test có **mốc thời gian xác định, chạy nhanh và lặp lại được**, không cần ngủ chờ hay thay đổi thời gian hệ điều hành.

~~~text
Ứng dụng thực tế                    Unit test
----------------                    ---------
Clock.systemUTC()                    Clock.fixed(knownInstant, zone)
        │                                      │
        └───────── Constructor injection ─────┘
                             │
                             ▼
                      BusinessService
                             │
                     clock.instant()
                     LocalDate.now(clock)
                             │
                             ▼
                      Quy tắc nghiệp vụ

BusinessService không cần biết Clock nào được truyền vào.
~~~

**Thông điệp chính:** thời gian hiện tại là **một dependency**, tương tự repository, client HTTP hoặc cấu hình. Hãy biến nó thành dependency rõ ràng để kiểm thử được.

Các ví dụ chạy độc lập với **Java 17+**; các API **Clock**, **Instant**, **Duration**, **LocalDate** đều có từ Java 8. Ví dụ dùng **record** được ghi rõ là cú pháp Java 17+, không phải tính năng Java 8 ban đầu.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Giải thích vì sao các lệnh **now()** tĩnh làm bài test lệ thuộc đồng hồ thực.
2. Thiết kế **constructor injection** với **private final Clock clock** và **Objects.requireNonNull(clock)**.
3. Chọn **Clock.systemUTC()** hoặc **Clock.system(zone)** trong production, **Clock.fixed(...)** trong test.
4. Dùng **Clock.offset(...)** để kiểm tra thời điểm trước, đúng tại và sau một deadline mà không sử dụng **Thread.sleep**.
5. Hiểu **getZone()**, **withZone(...)**, **Clock.instant()**, **Clock.millis()**, **Instant.now(clock)** và **LocalDate.now(clock)**.
6. Viết kiểm thử xác định cho TTL, hạn dùng, ngày hết hạn, múi giờ và DST.
7. Tránh lỗi do **nhiều lần đọc thời gian** trong một thao tác hoặc do nhầm **Instant** với **ngày lịch**.
8. Phân biệt **Clock.fixed**, **Clock.offset**, **Clock.tick** và các clock dựa vào thời gian hệ thống.
9. Hiểu giới hạn: Clock không tự là scheduler, stopwatch, bảo đảm đồng hồ đồng bộ hoặc công cụ kiểm thử mọi side effect.
10. Áp dụng nguyên tắc tương tự khi dự án dùng JUnit hoặc dependency injection framework.

## 2. Vấn đề: hard-code thời gian hiện tại

Xét một service tính thời hạn của một token:

~~~java
// Đoạn minh họa ANTI-PATTERN:
boolean isActive(Instant expiresAt) {
    return Instant.now().isBefore(expiresAt);
}
~~~

Logic tưởng như đúng, nhưng trong test:

- Không thể chỉ định chính xác **Instant.now()** sẽ trả giá trị nào.
- Một kết quả gần thời điểm hết hạn có thể thay đổi giữa lần chạy.
- Muốn kiểm tra "15 phút sau" bằng cách **Thread.sleep(15 phút)** là không thực tế.
- Việc sửa đồng hồ máy test hoặc gọi mock các static method có thể ảnh hưởng tới test khác và làm test khó bảo trì.
- Nếu code dùng thêm **LocalDate.now()**, ngày còn có thể phụ thuộc default ZoneId của JVM.

Một tình huống rủi ro khác:

~~~java
// Mã minh họa, không phải class đầy đủ.
Instant createdAt = Instant.now();
// Có các thao tác ở giữa.
Instant updatedAt = Instant.now();
~~~

Hai giá trị có thể khác nhau một chút mặc dù nghiệp vụ muốn "thời điểm tạo ban đầu" là một mốc duy nhất. Nguy cơ tăng khi chạy gần ranh giới hết hạn.

**Sửa bằng cách đưa Clock ra ngoài:**

~~~java
private final Clock clock;

public boolean isActive(Instant expiresAt) {
    return clock.instant().isBefore(expiresAt);
}
~~~

Đây là **đoạn mã thuộc một class có constructor nhận Clock**, không phải chương trình chạy độc lập. Service không tự quyết định lấy thời gian từ nguồn nào; ứng dụng cấp Clock thích hợp.

### 2.1. Vì sao nên inject thay vì chỉ truyền Instant.now() từng nơi?

Truyền thẳng một **Instant cụ thể** là hợp lý khi một phương thức thuần cần kiểm tra tại **một thời điểm do caller xác định**:

~~~java
static boolean activeAt(Instant now, Instant expiresAt) {
    return now.isBefore(expiresAt);
}
~~~

Đây là hàm minh họa có tính quyết định hoàn toàn. Nhưng nếu cả một service phải liên tục đọc thời gian trong nhiều phương thức, inject **Clock** sẽ giúp dùng chung chính sách thời gian, không phải truyền **now** xuyên suốt mọi lớp thủ công.

Hai cách tiếp cận có thể kết hợp:

- **Service có Clock** để lấy thời gian tại ranh giới nghiệp vụ.
- **Hàm thuần nhận Instant/LocalDate** để tính toán mà không cần đọc đồng hồ.

Cách này khiến logic dễ kiểm thử và giảm số chỗ phụ thuộc thời gian thực.

## 3. java.time.Clock là gì?

**Clock** là abstraction cung cấp:

- **Instant instant()** — đọc điểm hiện tại trên timeline.
- **ZoneId getZone()** — zone dùng khi cần diễn giải Instant thành ngày-giờ địa phương.
- **Clock withZone(ZoneId)** — tạo Clock tương ứng với cùng nguồn thời gian nhưng dùng zone khác.
- **long millis()** — epoch milliseconds (khi cần tương thích với API số).

Clock **không phải** một **Instant**, **LocalDateTime** hay một **Temporal** chứa ngày giờ cụ thể. Nó là **nguồn cung cấp thời gian** để các đối tượng thời gian khác đọc.

Ví dụ:

~~~java
Clock clock = Clock.systemUTC();

Instant timestamp = clock.instant();
Instant alsoTimestamp = Instant.now(clock);

LocalDate utcToday = LocalDate.now(clock);
ZonedDateTime utcDateTime = ZonedDateTime.now(clock);
~~~

Đây là **đoạn minh họa**, cần import các kiểu từ **java.time**.

**Điểm quan trọng:** **clock.instant()** và **Instant.now(clock)** lấy Instant từ Clock. Với Clock dựa vào đồng hồ thực, gọi hai lần có thể cho **hai giá trị khác nhau** vì thời gian trôi qua; không suy ra hai lời gọi nhất thiết bằng nhau.

**clock.getZone()** không khiến Instant đổi giá trị. Nó chỉ quyết định **cách diễn giải ngày/giờ địa phương** khi dùng những API như LocalDate.now(clock).

### 3.1. Những overload now(clock) phổ biến

| API | Dữ liệu trả về | Vai trò của Clock |
|---|---|---|
| **Instant.now(clock)** | Instant | Lấy điểm timeline từ Clock |
| **LocalDate.now(clock)** | LocalDate | Lấy Instant và đổi sang ngày bằng zone của Clock |
| **LocalTime.now(clock)** | LocalTime | Lấy giờ địa phương theo zone của Clock |
| **LocalDateTime.now(clock)** | LocalDateTime | Lấy ngày giờ địa phương theo zone của Clock |
| **ZonedDateTime.now(clock)** | ZonedDateTime | Lấy ngày giờ và zone/offset của Clock |
| **OffsetDateTime.now(clock)** | OffsetDateTime | Lấy ngày giờ và offset hiện hành trong zone của Clock |

Các phương thức này cho phép code không hard-code đồng hồ hệ thống vào business logic.

## 4. Các Clock factory quan trọng

| Factory | Cơ chế | Nên dùng khi nào |
|---|---|---|
| **Clock.systemUTC()** | Đồng hồ hệ thống, zone UTC | Production khi cần Instant/audit timestamp |
| **Clock.system(zone)** | Đồng hồ hệ thống, zone được chỉ định | Production khi service cần lịch địa phương |
| **Clock.systemDefaultZone()** | Đồng hồ hệ thống, zone mặc định của JVM | Chỉ khi yêu cầu thật sự dùng default zone |
| **Clock.fixed(instant, zone)** | Luôn trả **cùng một Instant** | Unit test xác định |
| **Clock.offset(base, duration)** | Đọc base Clock rồi cộng một Duration | Test tương lai/quá khứ, hoặc biến thể nguồn thời gian |
| **Clock.tick(base, duration)** | Chỉ báo thời điểm theo các bước thời gian đã cắt | Hiển thị/ứng dụng cần độ phân giải thô hơn |
| **clock.withZone(zone)** | Giữ hành vi nguồn thời gian, thay zone diễn giải | Kiểm tra ngày địa phương ở nhiều vùng |
| **Clock.tickSeconds(zone)** | Clock hệ thống theo giây nguyên | Trường hợp muốn độ phân giải tới giây, Java 9+ |
| **Clock.tickMinutes(zone)** | Clock hệ thống theo phút nguyên | Trường hợp muốn độ phân giải tới phút, Java 9+ |

**Không nhầm tick với việc "tua thời gian".** Clock.tick chỉ làm cho các giá trị quan sát nằm tại những ranh giới tick; nó không tự tăng thời gian sau mỗi lần đọc và không kích hoạt scheduler.

### 4.1. Clock.systemUTC() không phải đồng hồ đứng yên

~~~java
Clock realTime = Clock.systemUTC();
~~~

Đây là clock **đang chạy theo nguồn thời gian hệ thống**, chỉ có zone UTC. Chọn nó giúp tránh phụ thuộc default zone khi chỉ cần Instant. Nó **không** làm bài test xác định.

Để cố định thời điểm, cần:

~~~java
Clock testClock = Clock.fixed(
        Instant.parse("2026-04-01T10:00:00Z"),
        ZoneOffset.UTC);
~~~

**Đừng đặt Clock.fixed trong cấu hình production** trừ khi ứng dụng thật sự được thiết kế để có thời gian mô phỏng; mọi lần đọc sau đó sẽ vẫn thấy cùng timestamp.

### 4.2. Clock.system(zone) và mặc định JVM

~~~java
Clock vietnam = Clock.system(
        ZoneId.of("Asia/Ho_Chi_Minh"));
~~~

Đây vẫn là **đồng hồ thật**, nhưng **LocalDate.now(vietnam)** là ngày theo zone Việt Nam. Không cần gọi **TimeZone.setDefault** hoặc thay zone toàn JVM để kiểm thử nghiệp vụ ở một vùng nhất định.

Dùng **Clock.systemDefaultZone()** khi sản phẩm thật sự muốn theo default zone của máy. Với backend đa vùng, vùng mặc định của container/CI thường không đại diện cho người dùng.

## 5. Constructor injection: mẫu thiết kế khuyến nghị

Một class cần thời gian hiện tại nên nhận Clock qua constructor, lưu trong **private final** và kiểm tra null:

~~~java
import java.time.Clock;
import java.time.Instant;
import java.util.Objects;

public final class TimeAwareService {
    private final Clock clock;

    public TimeAwareService(Clock clock) {
        this.clock = Objects.requireNonNull(clock);
    }

    public Instant currentInstant() {
        return clock.instant();
    }
}
~~~

Đây là **class hợp lệ nhưng không có main()**; muốn chạy cần một chương trình khác tạo instance.

**Ưu điểm:**

1. Clock trở thành **dependency tường minh** và khó bị bỏ quên khi khởi tạo.
2. Business logic không phụ thuộc static call tới system time.
3. Unit test có thể truyền Clock.fixed mà không cần thao tác lên JVM global state.
4. Mỗi service có thể dùng Clock khác nếu nghiệp vụ cần.
5. Code dễ kiểm tra hơn vì chỗ nào phụ thuộc thời gian được nhìn thấy qua constructor.

**Cách lắp ở ranh giới ứng dụng:**

~~~java
// Đoạn minh họa composition root:
Clock productionClock = Clock.systemUTC();

TimeAwareService service =
        new TimeAwareService(productionClock);
~~~

Trong test:

~~~java
// Đoạn minh họa:
Clock clock = Clock.fixed(
        Instant.parse("2026-04-01T10:00:00Z"),
        ZoneOffset.UTC);

TimeAwareService service =
        new TimeAwareService(clock);
~~~

Không phải thay mã nguồn của TimeAwareService. Chỉ thay dependency.

### 5.1. Tại sao final và không tự tạo clock trong service?

**private final Clock clock** thể hiện dependency được cấp lúc khởi tạo. Nó giảm nguy cơ một test hoặc thread khác thay nguồn thời gian ngay trong lúc service chạy.

Tránh:

~~~java
// Anti-pattern: constructor nhận clock nhưng lại bỏ qua nó.
this.clock = Clock.systemUTC();
~~~

Khi đó injection vô hiệu và test vẫn lệ thuộc thời gian thật.

Cũng tránh:

~~~java
// Anti-pattern: mỗi phương thức tự lấy thời gian hệ thống.
Instant time = Instant.now();
~~~

Khi đã inject Clock, mọi lần đọc **thời gian hiện tại do service làm chủ** nên đi qua Clock đó (trừ phần mã cố ý dùng nguồn khác và đã được ghi rõ).

## 6. Ví dụ đầy đủ: service phát hành quyền truy cập có TTL

Yêu cầu nghiệp vụ:

- Khi phát hành một quyền truy cập, lưu **issuedAt** và **expiresAt**.
- TTL được cấu hình, ví dụ **15 phút**.
- Quyền có hiệu lực khi **now < expiresAt**.
- Đúng tại **expiresAt** hoặc sau đó: **không** còn hiệu lực.
- Test cần kiểm tra mọi ranh giới trong vài mili-giây thực tế, không cần sleep.

Lưu thành **ClockInjectionDemo.java**:

~~~java
import java.time.Clock;
import java.time.Duration;
import java.time.Instant;
import java.time.ZoneOffset;
import java.util.Objects;

public class ClockInjectionDemo {
    record AccessPass(
            String id,
            Instant issuedAt,
            Instant expiresAt) {}

    static final class AccessPassService {
        private final Clock clock;
        private final Duration ttl;

        AccessPassService(Clock clock, Duration ttl) {
            this.clock = Objects.requireNonNull(clock);
            this.ttl = Objects.requireNonNull(ttl);

            if (ttl.isNegative() || ttl.isZero()) {
                throw new IllegalArgumentException(
                        "ttl must be positive");
            }
        }

        AccessPass issue(String id) {
            Instant now = clock.instant();

            return new AccessPass(
                    id,
                    now,
                    now.plus(ttl));
        }

        boolean isActive(AccessPass pass) {
            Objects.requireNonNull(pass);
            return clock.instant().isBefore(pass.expiresAt());
        }
    }

    public static void main(String[] args) {
        Instant start =
                Instant.parse("2026-04-01T10:00:00Z");

        Clock base = Clock.fixed(start, ZoneOffset.UTC);
        Duration ttl = Duration.ofMinutes(15);

        AccessPassService atIssue =
                new AccessPassService(base, ttl);

        AccessPass pass = atIssue.issue("P-01");

        Clock justBefore = Clock.offset(
                base,
                ttl.minusNanos(1));

        Clock exactlyAt = Clock.offset(base, ttl);

        Clock justAfter = Clock.offset(
                base,
                ttl.plusNanos(1));

        System.out.println("issued=" + pass.issuedAt());
        System.out.println("expires=" + pass.expiresAt());
        System.out.println("atIssue="
                + atIssue.isActive(pass));

        System.out.println("beforeExpiry="
                + new AccessPassService(justBefore, ttl)
                        .isActive(pass));

        System.out.println("atExpiry="
                + new AccessPassService(exactlyAt, ttl)
                        .isActive(pass));

        System.out.println("afterExpiry="
                + new AccessPassService(justAfter, ttl)
                        .isActive(pass));
    }
}
~~~

~~~bash
javac -encoding UTF-8 ClockInjectionDemo.java
java ClockInjectionDemo
~~~

**Stdout xác định:**

~~~text
issued=2026-04-01T10:00:00Z
expires=2026-04-01T10:15:00Z
atIssue=true
beforeExpiry=true
atExpiry=false
afterExpiry=false
~~~

**Giải thích chi tiết:**

- **Clock.fixed** làm cho start không đổi giữa các lần gọi.
- **issue** đọc một lần **clock.instant()**, rồi tính expiresAt từ chính mốc đó.
- **Clock.offset(base, ttl.minusNanos(1))** nhìn thấy thời gian **một nanosecond trước hạn**.
- **Clock.offset(base, ttl)** nhìn thấy **đúng thời điểm hết hạn**; điều kiện isBefore trả false.
- **Clock.offset(base, ttl.plusNanos(1))** thấy thời điểm sau hạn, cũng trả false.
- Không có lệnh **Thread.sleep**, không phụ thuộc tốc độ CPU, không phải chờ 15 phút.
- **Clock.offset** tạo Clock mới và **không sửa base**, nên các tình huống kiểm thử độc lập.

**Quy ước biên:** Kết quả này áp dụng hợp đồng **[issuedAt, expiresAt)**, tức gồm đầu, loại cuối. Nếu sản phẩm muốn expiresAt còn hợp lệ đúng thời điểm bằng nhau, điều kiện phải được thiết kế khác và cần test rõ. Đừng tự suy ra quy tắc từ tên expiresAt.

### 6.1. Tại sao không dùng end.minusMillis(1)?

Nếu muốn "ngay trước deadline", hãy dùng một thời điểm cụ thể có độ phân giải mà nghiệp vụ xác định. Ví dụ trên dùng **minusNanos(1)** vì Instant có phần nano. Không mặc định database/REST giữ precision tới nano.

Quan trọng hơn: với logic **end-exclusive**, chỉ cần điều kiện **now.isBefore(end)**, không cần trừ một đơn vị vào end khi chạy production.

### 6.2. Dùng cùng một mốc now để tính các trường liên quan

Trong **issue**, chỉ đọc Clock một lần:

~~~java
Instant now = clock.instant();
Instant expiresAt = now.plus(ttl);
~~~

Nếu gọi **clock.instant()** riêng cho issuedAt và expiresAt, hai mốc có thể lệch do thời gian trôi qua. Một Clock.fixed sẽ che giấu vấn đề ấy trong test, nhưng đồng hồ thật thì không. Khi một thao tác cần **một thời điểm logic chung**, đọc một lần và tái sử dụng biến now.

## 7. Test "hôm nay" theo múi giờ: Clock chứa cả Instant và ZoneId

**Instant** biểu diễn một điểm timeline; **LocalDate** biểu diễn ngày lịch. Khi tính "hôm nay" cần chọn zone, vì cùng một Instant có thể là ngày khác nhau ở các vùng.

Ví dụ cùng thời điểm:

~~~text
Instant: 2026-01-01T23:30:00Z

UTC:                  2026-01-01
Asia/Ho_Chi_Minh:     2026-01-02
~~~

Một lỗi phổ biến là service gọi **LocalDate.now()** không tham số trên server có default zone UTC trong khi quy tắc hạn nộp bài sử dụng ngày Việt Nam.

### 7.1. Clock.withZone không làm thay đổi Instant

Lưu thành **ClockZoneDemo.java**:

~~~java
import java.time.Clock;
import java.time.Instant;
import java.time.LocalDate;
import java.time.ZoneId;
import java.time.ZoneOffset;

public class ClockZoneDemo {
    public static void main(String[] args) {
        Instant instant =
                Instant.parse("2026-01-01T23:30:00Z");

        Clock utc = Clock.fixed(
                instant,
                ZoneOffset.UTC);

        Clock vietnam = utc.withZone(
                ZoneId.of("Asia/Ho_Chi_Minh"));

        System.out.println("instant=" + utc.instant());
        System.out.println("utcDate=" + LocalDate.now(utc));
        System.out.println("vietnamDate="
                + LocalDate.now(vietnam));
        System.out.println("sameInstant="
                + utc.instant().equals(vietnam.instant()));
    }
}
~~~

~~~bash
javac -encoding UTF-8 ClockZoneDemo.java
java ClockZoneDemo
~~~

**Stdout:**

~~~text
instant=2026-01-01T23:30:00Z
utcDate=2026-01-01
vietnamDate=2026-01-02
sameInstant=true
~~~

**Ý nghĩa:**

- Hai Clock cùng sử dụng **một Instant cố định**.
- **getZone()** khác nhau, nên **LocalDate.now(clock)** có thể trả ngày khác.
- **Instant.now(clock)** hoặc **clock.instant()** vẫn là cùng một điểm timeline.
- **withZone** tạo Clock mới; không sửa Clock gốc.

**Không nhầm** việc thay zone với việc cộng hay trừ giờ vào Instant. Chuyển zone để **diễn giải**, không làm dịch chuyển sự kiện.

### 7.2. Khi nào truyền thêm ZoneId riêng?

Có hai thiết kế hợp lệ tùy ranh giới trách nhiệm.

**Thiết kế A: Clock mang zone nghiệp vụ.**

~~~java
LocalDate today = LocalDate.now(clock);
~~~

Phù hợp nếu service luôn phục vụ một vùng được cấu hình sẵn và Clock.getZone chính là vùng nghiệp vụ.

**Thiết kế B: Clock cung cấp Instant, ZoneId do nghiệp vụ quy định riêng.**

~~~java
Instant current = clock.instant();
LocalDate today = current.atZone(userZone).toLocalDate();
~~~

Đây là đoạn minh họa với userZone là ZoneId được cấp từ caller. Phù hợp nếu cùng một service phục vụ nhiều khách hàng ở nhiều múi giờ, hoặc khi Clock sản xuất luôn ở UTC để ghi audit còn ngày nghiệp vụ thuộc vùng riêng.

**Không tự chọn thiết kế A hay B theo sự thuận tiện của server**. Hãy xác định xem "hôm nay" thuộc **zone của ai**.

## 8. Ví dụ đầy đủ: hạn nộp theo ngày của khách hàng

Yêu cầu: Một hạn nộp **LocalDate 2026-01-02** trở thành **đến hạn** khi ngày địa phương hiện tại bằng hoặc sau ngày ấy. Dùng Clock cố định ở mốc **2026-01-01T23:30Z**:

- Theo UTC, vẫn là **1/1**, chưa đến hạn.
- Theo Việt Nam, đã là **2/1**, đến hạn.

Lưu thành **BusinessDateClockDemo.java**:

~~~java
import java.time.Clock;
import java.time.Instant;
import java.time.LocalDate;
import java.time.ZoneId;
import java.time.ZoneOffset;
import java.util.Objects;

public class BusinessDateClockDemo {
    static final class DueDateService {
        private final Clock clock;
        private final ZoneId businessZone;

        DueDateService(Clock clock, ZoneId businessZone) {
            this.clock = Objects.requireNonNull(clock);
            this.businessZone =
                    Objects.requireNonNull(businessZone);
        }

        LocalDate today() {
            return clock.instant()
                    .atZone(businessZone)
                    .toLocalDate();
        }

        boolean isDue(LocalDate dueDate) {
            Objects.requireNonNull(dueDate);
            return !today().isBefore(dueDate);
        }
    }

    public static void main(String[] args) {
        Instant fixed =
                Instant.parse("2026-01-01T23:30:00Z");

        Clock clock = Clock.fixed(
                fixed, ZoneOffset.UTC);

        LocalDate due =
                LocalDate.of(2026, 1, 2);

        DueDateService utc =
                new DueDateService(clock, ZoneOffset.UTC);

        DueDateService vietnam =
                new DueDateService(
                        clock,
                        ZoneId.of("Asia/Ho_Chi_Minh"));

        System.out.println("utcToday=" + utc.today());
        System.out.println("utcDue=" + utc.isDue(due));
        System.out.println("vietnamToday=" + vietnam.today());
        System.out.println("vietnamDue=" + vietnam.isDue(due));
    }
}
~~~

~~~bash
javac -encoding UTF-8 BusinessDateClockDemo.java
java BusinessDateClockDemo
~~~

**Stdout:**

~~~text
utcToday=2026-01-01
utcDue=false
vietnamToday=2026-01-02
vietnamDue=true
~~~

**Tại sao có cả Clock và ZoneId?** Clock cấp mốc thời gian có thể kiểm thử, còn businessZone là quy tắc nghiệp vụ. Nếu dùng **Clock.systemUTC()** trong production, kết quả vẫn đúng khi mỗi khách hàng có ZoneId riêng.

**Lưu ý:** Trong ví dụ, **isDue** đọc clock một lần khi gọi today. Một service phức tạp hơn nên cân nhắc đọc một Instant duy nhất nếu nhiều phép so sánh trong cùng giao dịch phải nhất quán.

## 9. Clock.offset để mô phỏng thời gian tiến hoặc lùi

**Clock.offset(baseClock, duration)** tạo một Clock mà mỗi lần đọc trả thời gian từ baseClock **cộng** Duration.

~~~java
Clock base = Clock.fixed(
        Instant.parse("2026-04-01T10:00:00Z"),
        ZoneOffset.UTC);

Clock future = Clock.offset(
        base,
        Duration.ofMinutes(30));

Clock past = Clock.offset(
        base,
        Duration.ofMinutes(-5));
~~~

Đây là đoạn minh họa, cần import từ java.time.

- **future.instant()** là **2026-04-01T10:30:00Z**.
- **past.instant()** là **2026-04-01T09:55:00Z**.
- **base** vẫn trỏ tới mốc **10:00Z**.
- Không cần thay đồng hồ hệ thống.
- Nếu base là Clock.systemUTC(), Clock.offset(base, ...) vẫn thay đổi theo thời gian thực, chỉ bị dịch một khoảng cố định. **Offset không làm một clock đang chạy trở thành clock fixed.**

### 9.1. Offset không phải nút "advance" trên cùng object

Điều này không tiến hành:

~~~java
Clock base = Clock.fixed(
        Instant.parse("2026-04-01T10:00:00Z"),
        ZoneOffset.UTC);

Clock.offset(base, Duration.ofMinutes(5));

// base.instant() vẫn là 10:00Z
~~~

**Clock.offset trả Clock mới**. Nếu muốn test các pha tuần tự, có thể dùng các instance service với Clock khác nhau, như ví dụ TTL, hoặc thiết kế một **test clock tùy chỉnh** hỗ trợ tiến thời gian.

**Không vội viết custom Clock mutable** cho những trường hợp chỉ cần kiểm tra mốc trước/đúng/sau; Clock.fixed và Clock.offset đã đủ và đơn giản hơn.

## 10. Clock.tick: kiểm soát độ phân giải quan sát, không tua thời gian

**Clock.tick(base, tickDuration)** cung cấp thời gian theo những ranh giới tick. Ví dụ base Clock đang cố định tại **10:15:30.987Z**:

- Tick theo giây: **10:15:30Z**.
- Tick theo phút: **10:15:00Z**.
- Offset thêm một giờ: **11:15:30.987Z**.

Lưu thành **ClockFactoryDemo.java**:

~~~java
import java.time.Clock;
import java.time.Duration;
import java.time.Instant;
import java.time.ZoneId;
import java.time.ZoneOffset;

public class ClockFactoryDemo {
    public static void main(String[] args) {
        Clock base = Clock.fixed(
                Instant.parse("2026-01-01T10:15:30.987Z"),
                ZoneOffset.UTC);

        Clock future = Clock.offset(
                base, Duration.ofHours(1));

        Clock bySecond = Clock.tick(
                base, Duration.ofSeconds(1));

        Clock byMinute = Clock.tick(
                base, Duration.ofMinutes(1));

        Clock vietnam = base.withZone(
                ZoneId.of("Asia/Ho_Chi_Minh"));

        System.out.println("base=" + base.instant());
        System.out.println("offset=" + future.instant());
        System.out.println("tickSecond=" + bySecond.instant());
        System.out.println("tickMinute=" + byMinute.instant());
        System.out.println("baseZone=" + base.getZone());
        System.out.println("vietnamZone=" + vietnam.getZone());
        System.out.println("instantUnchanged="
                + base.instant().equals(vietnam.instant()));
    }
}
~~~

~~~bash
javac -encoding UTF-8 ClockFactoryDemo.java
java ClockFactoryDemo
~~~

**Stdout:**

~~~text
base=2026-01-01T10:15:30.987Z
offset=2026-01-01T11:15:30.987Z
tickSecond=2026-01-01T10:15:30Z
tickMinute=2026-01-01T10:15:00Z
baseZone=Z
vietnamZone=Asia/Ho_Chi_Minh
instantUnchanged=true
~~~

**Những giới hạn cần hiểu:**

- Clock.tick làm **truncation theo nhịp**, không tự gọi sleep hay kích hoạt việc gì.
- Với Clock.system(...) làm base, thời gian vẫn tiến theo hệ thống, nhưng quan sát có độ phân giải bị giới hạn.
- Một số tick clock có thể **cache**; thời điểm bắt đầu một tick quan sát được có thể trễ so với nguồn gốc. Không dùng tick làm bằng chứng về timestamp chính xác tại ranh giới.
- Tick duration phải phù hợp với ràng buộc API; duration âm hoặc một số chia nhỏ giây không hợp lệ có thể ném **IllegalArgumentException**.
- **tickSeconds/tickMinutes/tickMillis** là factory tiện lợi được bổ sung trong các phiên bản Java sau 8; trên Java 17+ có thể dùng. Với code Java 8, **Clock.tick(base, Duration...)** là lựa chọn tương thích.

## 11. Kiểm thử ranh giới deadline mà không cần chờ

Ví dụ TTL ở mục 6 minh họa ba ranh giới:

~~~text
createdAt = 10:00
TTL       = 15 phút
expiresAt = 10:15

10:14:59.999999999 → còn hiệu lực
10:15:00.000000000 → hết hiệu lực
10:15:00.000000001 → hết hiệu lực
~~~

**Trong unit test, mỗi ranh giới được mô phỏng bằng Clock.fixed hoặc Clock.offset**, nên bài test chạy nhanh dù TTL ngoài thực tế là vài phút, vài ngày hoặc vài tháng.

### 11.1. Chọn kiểu thời gian theo nghiệp vụ

| Quy tắc | Dữ liệu và phép tính thích hợp |
|---|---|
| "Hết hạn đúng 15 phút sau" | **Instant + Duration** |
| "Hết hạn đúng 24 giờ sau" | **Instant + Duration.ofHours(24)** |
| "Hết hạn cuối ngày địa phương" | **LocalDate/ZoneId** và ranh giới ngày |
| "Gia hạn một tháng lịch" | **Period/LocalDate/ZonedDateTime** |
| "Hết hạn sau 3 ngày làm việc" | Quy tắc business calendar riêng |
| "Ngày sinh đã qua chưa?" | **LocalDate** và Clock/ZoneId rõ nghĩa |
| "Lệnh đến trước hay sau deadline?" | So **Instant** tại ranh giới |

Clock cấp **nguồn thời gian**, không thay quyết định dùng Duration hay Period hoặc ngày lịch.

### 11.2. Đừng dùng Thread.sleep trong test logic

~~~java
// Anti-pattern:
Thread.sleep(1000);
boolean expired = service.isExpired(token);
~~~

Tại sao không nên?

- Test chậm và tăng thời gian CI.
- Scheduler hệ điều hành có thể làm thời gian chờ dài/ngắn hơn dự kiến.
- Tăng nguy cơ flaky khi chạy song song.
- Không thể kiểm tra chính xác một nanosecond trước deadline.

Dùng Clock.fixed/offset cho **logic dựa trên "now"**. Tuy vậy, nếu test đang kiểm tra **scheduler, hàng đợi hoặc timer thực**, chỉ inject Clock không đủ; test cần khả năng điều khiển scheduler hoặc môi trường thời gian của thành phần đó.

## 12. Bài test tự chạy không cần JUnit

Trong môi trường học tập, có thể xây một test harness bằng **main** và ném **AssertionError**. Cách này không cần thư viện ngoài, không dựa vào cờ **-ea** của Java.

Lưu thành **ClockDeterminismTest.java**:

~~~java
import java.time.Clock;
import java.time.Duration;
import java.time.Instant;
import java.time.LocalDate;
import java.time.ZoneId;
import java.time.ZoneOffset;

public class ClockDeterminismTest {
    static void check(String name, boolean condition) {
        if (!condition) {
            throw new AssertionError(name);
        }

        System.out.println("PASS " + name);
    }

    public static void main(String[] args) {
        Instant baseTime =
                Instant.parse("2026-04-01T10:00:00Z");

        Clock fixed = Clock.fixed(
                baseTime, ZoneOffset.UTC);

        check("fixed",
                fixed.instant().equals(baseTime));

        check("repeatable",
                fixed.instant().equals(fixed.instant()));

        Instant end = baseTime.plusSeconds(900);

        Clock before = Clock.offset(
                fixed, Duration.ofSeconds(899));

        Clock atEnd = Clock.offset(
                fixed, Duration.ofSeconds(900));

        check("before-end",
                before.instant().isBefore(end));

        check("at-end",
                !atEnd.instant().isBefore(end));

        Clock nearMidnight = Clock.fixed(
                Instant.parse("2026-01-01T23:30:00Z"),
                ZoneOffset.UTC);

        check("utc-day",
                LocalDate.now(nearMidnight)
                        .equals(LocalDate.of(2026, 1, 1)));

        check("vietnam-day",
                LocalDate.now(nearMidnight.withZone(
                        ZoneId.of("Asia/Ho_Chi_Minh")))
                        .equals(LocalDate.of(2026, 1, 2)));
    }
}
~~~

~~~bash
javac -encoding UTF-8 ClockDeterminismTest.java
java ClockDeterminismTest
~~~

**Stdout:**

~~~text
PASS fixed
PASS repeatable
PASS before-end
PASS at-end
PASS utc-day
PASS vietnam-day
~~~

**Ưu điểm:** Không cần thời gian hệ thống, không cần JUnit, không thay đổi timezone global, và test có stdout cố định. Nếu một điều kiện sai, **AssertionError** làm chương trình thất bại.

**Lưu ý:** Test **repeatable** chỉ xác minh Clock.fixed; nó không đủ để chứng minh một service không vô tình gọi thêm **Instant.now()** ở nơi khác. Để kiểm chứng sự tuân thủ injection, cần test các phương thức nghiệp vụ ở các ranh giới.

## 13. Kết hợp với JUnit 5

Trong dự án dùng JUnit Jupiter, mẫu tương tự có thể được kiểm thử bằng assertions. Ví dụ sau **phụ thuộc vào thư viện JUnit 5** trong build; nó không phải class tự chạy bằng javac thuần như các ví dụ trước.

~~~java
import static org.junit.jupiter.api.Assertions.*;
import java.time.Clock;
import java.time.Instant;
import java.time.LocalDate;
import java.time.ZoneId;
import java.time.ZoneOffset;
import org.junit.jupiter.api.Test;

class DateClockTest {
    @Test
    void vietnamDateIsDeterministic() {
        Instant instant = Instant.parse(
                "2026-01-01T23:30:00Z");

        Clock clock = Clock.fixed(
                instant, ZoneOffset.UTC);

        Clock vietnamClock = clock.withZone(
                ZoneId.of("Asia/Ho_Chi_Minh"));

        assertEquals(
                LocalDate.of(2026, 1, 2),
                LocalDate.now(vietnamClock));
    }
}
~~~

**Giải thích:** Test đưa vào một Clock cố định, không mock static LocalDate.now, không sleep, và không phụ thuộc múi giờ của runner. Các khái niệm **Clock injection** cũng áp dụng với TestNG hoặc những framework khác; chỉ cách khai báo assertion/test annotation thay đổi.

**Không cần bắt buộc dùng mock framework để mock Clock.** Clock.fixed thường đơn giản, đáng tin và dễ đọc hơn.

## 14. Test ngày nhuận và cuối tháng

Giả sử service cần biết "hôm nay có phải ngày cuối tháng không?".

~~~java
// Đoạn minh họa trong service có Clock:
LocalDate today = LocalDate.now(clock);
boolean lastDay =
        today.getDayOfMonth() == today.lengthOfMonth();
~~~

Với test, dùng hai Clock.fixed ở hai thời điểm được chọn theo zone nghiệp vụ, ví dụ **29/2/2024** và **28/2/2025** ở UTC.

Không cần thay ngày máy tính để thử năm nhuận hoặc cuối tháng. Một service khác có thể dùng **YearMonth.from(today).atEndOfMonth()** để tính ranh giới.

**Lưu ý:** Nếu ngày nghiệp vụ thuộc một vùng khác UTC, Clock.fixed nên được gắn với đúng zone hoặc service phải nhận ZoneId riêng. Cố định Instant mà không cố định cách diễn giải zone có thể khiến test ngày khác mong đợi.

## 15. Kiểm thử DST bằng Clock cố định

Mốc thời điểm tuyệt đối có thể **được diễn giải thành hai giờ đồng hồ** trước và sau bước nhảy DST. Clock injection giúp tạo những thời điểm lịch sử như thế mà không cần thay timezone của JVM.

Vào ngày **10/3/2024**, New York tiến giờ từ khoảng **01:59** sang **03:00**. Xét hai Instant cách nhau một giờ:

~~~text
2024-03-10T06:30:00Z
    → 2024-03-10T01:30-05:00[America/New_York]

2024-03-10T07:30:00Z
    → 2024-03-10T03:30-04:00[America/New_York]
~~~

Lưu thành **ClockDstDemo.java**:

~~~java
import java.time.Clock;
import java.time.Duration;
import java.time.Instant;
import java.time.ZoneId;
import java.time.ZonedDateTime;

public class ClockDstDemo {
    public static void main(String[] args) {
        ZoneId newYork =
                ZoneId.of("America/New_York");

        Clock before = Clock.fixed(
                Instant.parse("2024-03-10T06:30:00Z"),
                newYork);

        Clock after = Clock.offset(
                before, Duration.ofHours(1));

        ZonedDateTime localBefore =
                ZonedDateTime.now(before);

        ZonedDateTime localAfter =
                ZonedDateTime.now(after);

        System.out.println("before=" + localBefore);
        System.out.println("after=" + localAfter);
        System.out.println("elapsedHours="
                + Duration.between(
                        before.instant(),
                        after.instant()).toHours());
    }
}
~~~

~~~bash
javac -encoding UTF-8 ClockDstDemo.java
java ClockDstDemo
~~~

**Stdout theo quy tắc lịch sử New York năm 2024:**

~~~text
before=2024-03-10T01:30-05:00[America/New_York]
after=2024-03-10T03:30-04:00[America/New_York]
elapsedHours=1
~~~

**Giải thích:** Hai Clock cho cùng vùng nhưng hai Instant cách một giờ. Đồng hồ địa phương nhảy hai giờ vì DST. Nếu logic nghiệp vụ liên quan ngày giờ vùng, test cần chọn cả **Instant** lẫn **ZoneId** phù hợp.

**Clock không giải quyết chính sách gap/overlap cho lịch hẹn tương lai.** Khi chuyển **LocalDateTime + ZoneId → Instant** tại giờ bị lặp hoặc thiếu, ứng dụng vẫn phải có chính sách giải quyết thích hợp (có thể dùng ZoneRules, ZonedDateTime.ofStrict...).

## 16. Một request nên đọc Clock bao nhiêu lần?

**Nguyên tắc thực tế:** Nếu một request cần một **thời điểm nhất quán** cho nhiều trường và nhiều phép kiểm tra, hãy lấy **clock.instant()** một lần rồi truyền Instant đó vào các hàm thuần.

Ví dụ:

~~~java
// Đoạn minh họa:
Instant now = clock.instant();

boolean expired = !now.isBefore(expiresAt);
Instant auditAt = now;
LocalDate businessDate =
        now.atZone(businessZone).toLocalDate();
~~~

Cả ba phép dùng cùng một thời điểm logic. Nếu mỗi dòng tự gọi clock.instant(), thời gian có thể trôi và thậm chí bước qua nửa đêm giữa các lệnh.

**Không tạo Instant ở constructor và dùng mãi:**

~~~java
// Anti-pattern trong service sống lâu:
this.now = clock.instant();
~~~

Việc ấy chỉ chụp một snapshot tại lúc service khởi tạo; tất cả các request sau có thể dùng một timestamp cũ. **Inject Clock**, nhưng **đọc Instant trong thao tác đang xử lý**, không trong constructor nếu ý định là "thời điểm hiện tại của request".

### 16.1. Một số hàm tốt nhất nên thuần

~~~java
static boolean expiredAt(
        Instant now,
        Instant expiresAt) {

    return !now.isBefore(expiresAt);
}
~~~

Khi hàm nhận cả hai Instant làm input, nó hoàn toàn xác định và test càng đơn giản. Clock nên được dùng ở **boundary** nơi cần chuyển "hiện tại" thành một giá trị đầu vào.

## 17. Tách business time khỏi audit time

Một hệ thống có thể có hai khái niệm thời gian:

- **Audit timestamp:** một Instant biểu diễn thời điểm ghi nhận, có thể dùng Clock.systemUTC.
- **Business date:** ngày thuộc lịch của người dùng hoặc tổ chức, cần ZoneId cụ thể.

Ví dụ:

~~~java
Instant occurredAt = clock.instant();

LocalDate businessDate = occurredAt.atZone(
        ZoneId.of("Asia/Ho_Chi_Minh")).toLocalDate();
~~~

Đây là đoạn minh họa với clock đã inject.

**Không dùng LocalDate.now() theo default timezone server rồi tự coi đó là ngày hóa đơn của khách hàng.** Trong hệ thống đa vùng, cùng request có thể có audit timestamp dạng UTC nhưng ngày hóa đơn phải theo một region zone.

Trong test, cố định Instant gần nửa đêm và thử những ZoneId khác nhau; đó là cách phát hiện lỗi lệch ngày mà test giữa trưa thường bỏ sót.

## 18. Clock injection không thay thế điều khiển scheduler

Có hai nhóm logic cần phân biệt:

1. **Logic đồng bộ hỏi "hiện tại là lúc nào?"**: Clock.fixed/offset rất phù hợp.
2. **Logic chờ callback/timer/job chạy trong tương lai**: còn phụ thuộc scheduler, thread pool, queue, OS timer và cơ chế trigger.

Ví dụ một job dùng:

~~~java
// Mã minh họa:
scheduler.schedule(task, delay, TimeUnit.SECONDS);
~~~

Inject một Clock.fixed vào business service **không tự làm scheduler gọi task**. Nếu muốn test lịch chạy, cần cách điều khiển scheduler hoặc dùng fake scheduler/test scheduler thích hợp, ngoài việc điều khiển Clock.

**Clock cũng không phải Stopwatch.** Để đo elapsed time của một đoạn code trong cùng JVM, dùng **System.nanoTime()** hoặc công cụ đo thời gian phù hợp. Không chuyển System.nanoTime thành epoch Instant: giá trị tuyệt đối của nanoTime không có ý nghĩa timestamp.

### 18.1. Wall-clock và monotonic time

**Clock.systemUTC()** sử dụng nguồn thời gian hệ thống và có thể chịu ảnh hưởng của việc điều chỉnh đồng hồ. API không hứa Clock sẽ luôn tăng đều hoặc phản ánh đồng bộ toàn cầu giữa các máy.

- **Timestamps thực tế:** Instant/Clock.
- **Elapsed-time measurement trong một JVM:** nanoTime.
- **Thứ tự sự kiện trong hệ thống phân tán:** có thể cần thêm sequence, log offset hoặc cơ chế đồng bộ/logic clock.

Clock injection giúp kiểm thử code, **không tự giải quyết drift giữa các máy chủ**.

## 19. Factory nâng cao và những giới hạn cần nhớ

### 19.1. Clock.fixed

**Clock.fixed(instant, zone)** trả cùng Instant trong mọi lần đọc. Đây là lựa chọn mặc định cho phần lớn unit test quy tắc thời gian.

- Không tự tiến.
- Không cần sleep.
- Immutable, thread-safe theo hợp đồng.
- Zone phục vụ việc diễn giải ngày-giờ.
- **Không dùng làm clock production** nếu muốn thời gian thực luôn tiến.

### 19.2. Clock.offset

**Clock.offset(base, duration)** bọc Clock khác và cộng Duration.

- Với base fixed, kết quả vẫn fixed nhưng ở mốc khác.
- Với base system, kết quả vẫn chạy, chỉ bị dịch.
- Duration âm có thể mô phỏng quá khứ.
- Không mutate base Clock.
- Khi muốn kiểm tra nhiều boundary, tạo nhiều offset clocks từ cùng một base.

### 19.3. Clock.tick

**Clock.tick(base, tickDuration)** tạo thời gian quan sát theo tick, có thể cache. Nó dùng để giới hạn độ phân giải, không phải timer.

- Dùng **Clock.tick(base, Duration.ofMinutes(1))** nếu thích hợp.
- Không dùng tick để kiểm tra "sẽ chạy sau 1 phút" khi không có scheduler.
- Tick không đảm bảo giá trị đổi đúng ngay tại ranh giới theo thời gian thực.
- Chọn duration phù hợp với giới hạn API.

### 19.4. Clock.withZone

**clock.withZone(zone)** cho Clock tương ứng nhưng dùng zone khác. Với Clock.fixed, Instant không đổi; LocalDate/LocalTime.now(clock) có thể đổi.

**withZone không phải phép cộng UTC offset**; nếu muốn mô phỏng tương lai, dùng **Clock.offset**.

### 19.5. Clock.millis

**clock.millis()** cho epoch milliseconds, có thể hữu ích khi tích hợp API cũ hoặc cần số nguyên. Tuy nhiên, nếu business logic cần timestamp, **Instant** biểu diễn giàu thông tin hơn và tránh nhầm seconds/milliseconds. Khi chuyển qua millis, có thể mất precision dưới một millisecond.

### 19.6. InstantSource trên Java 17+

Từ **Java 17**, **java.time.InstantSource** là một abstraction nhẹ hơn dành cho nơi **chỉ cần lấy Instant**, không cần ZoneId. Clock hiện đại triển khai InstantSource.

Nếu dự án hỗ trợ Java 17+ và một service chỉ cần timestamp tuyệt đối, **InstantSource** có thể là lựa chọn phù hợp. Nếu service còn tính **LocalDate.now(clock)** hoặc **ZonedDateTime.now(clock)**, Clock vẫn tiện vì mang ZoneId.

**Quan trọng khi học module Java 8:** **InstantSource không có trong Java 8 ban đầu**, vì vậy không giới thiệu nó như API chạy được trên JDK 8. Kiến trúc constructor injection với Clock vẫn áp dụng cho cả Java 8 và các phiên bản hiện hành.

## 20. Khi nào cần custom Clock?

Đối với đa số test:

- **Clock.fixed** kiểm tra một mốc.
- **Clock.offset(fixed, duration)** kiểm tra các mốc tương đối.
- **Clock.withZone** kiểm tra ngày giờ địa phương.
- Tách các hàm thuần nhận Instant/LocalDate giúp phần lớn business logic không cần mock Clock phức tạp.

Nếu test mô phỏng **một service sống lâu** và cần tăng/giảm thời gian trong nhiều bước trên **cùng instance service**, một **mutable test clock** có thể hữu ích. Khi tự kế thừa Clock, phải triển khai **getZone()**, **instant()**, **withZone(...)** và đảm bảo thread safety; Clock là class dùng chung có thể được gọi từ nhiều thread.

**Không viết custom Clock bằng một trường Instant mutable không đồng bộ** khi test có thể chạy song song. Có thể sử dụng AtomicReference/đồng bộ phù hợp, nhưng cần giữ mối liên hệ giữa zone và time source. Nếu nhu cầu chỉ là kiểm tra vài deadline, ưu tiên factory có sẵn để giảm độ phức tạp.

## 21. Dependency injection framework và cấu hình production

Nguyên tắc không phụ thuộc framework:

1. Tại **composition root**, khởi tạo một Clock production phù hợp, thường là Clock.systemUTC().
2. Inject Clock qua constructor vào mọi service cần nguồn thời gian.
3. Trong unit test, thay Clock production bằng Clock.fixed hoặc Clock.offset.
4. Nếu mỗi tenant có business zone khác nhau, truyền ZoneId theo tenant/địa điểm thay vì dùng timezone global.
5. Không dùng **static final Instant NOW = Instant.now()** làm giá trị "hiện tại" dài hạn.

Một framework DI có thể đăng ký Clock là bean/dependency, nhưng ý tưởng là giống nhau. Không cần một thư viện ngoài nào để sử dụng Clock trong Java thuần.

**Tránh constructor tạo mặc định Clock.systemUTC() một cách âm thầm** trong đường test chính. Một constructor mặc định có thể là tiện ích khi yêu cầu rõ, nhưng constructor nhận Clock nên là đường đi được dùng trong kiểm thử để mọi phụ thuộc thời gian luôn nhìn thấy.

## 22. Những lỗi thường gặp

### Lỗi 1 — Dùng Instant.now() bên trong service đã inject Clock

~~~java
// Sai ý tưởng:
Instant now = Instant.now();

// Đúng:
Instant now = clock.instant();
~~~

Nếu vẫn gọi static now, test không còn điều khiển được tất cả đường đi.

### Lỗi 2 — Dùng LocalDate.now() không tham số

Ngày bị phụ thuộc timezone của JVM. Dùng **LocalDate.now(clock)** nếu Clock mang đúng zone, hoặc **clock.instant().atZone(businessZone).toLocalDate()**.

### Lỗi 3 — Tưởng Clock.systemUTC() là Clock cố định

Nó là Clock hệ thống đang chạy. Cố định thì dùng **Clock.fixed**.

### Lỗi 4 — Tạo Clock trong service thay vì nhận qua constructor

**Clock.systemUTC()** bên trong service hard-code nguồn thời gian, làm test khó kiểm soát. Chuyển factory này ra composition root.

### Lỗi 5 — Dùng Thread.sleep để kiểm tra token hết hạn

Test chậm và flaky. Dùng fixed/offset clocks để kiểm tra ranh giới.

### Lỗi 6 — Đọc Clock nhiều lần trong một giao dịch cần cùng mốc

Có thể tạo createdAt/updatedAt khác nhau hoặc bước qua midnight. Lấy một Instant rồi tái sử dụng cho những trường có cùng thời điểm logic.

### Lỗi 7 — Lấy Instant một lần ở constructor rồi dùng mãi

Giá trị "hiện tại" bị đóng băng ngoài ý muốn trong service sống lâu. Inject Clock, đọc khi xử lý từng request.

### Lỗi 8 — Dùng Clock.offset(fixed, duration) nhưng không giữ kết quả

Factory trả Clock mới, không mutate. Nếu không gán/truyền Clock trả về, service vẫn nhìn thấy Clock cũ.

### Lỗi 9 — Dùng withZone để mô phỏng tiến thời gian

withZone chỉ đổi vùng diễn giải, không đổi Instant. Dùng Clock.offset hoặc một Clock test phù hợp để tiến thời gian.

### Lỗi 10 — Dùng tick như một scheduler

Tick cắt độ phân giải và có thể cache. Không tự kích hoạt job, không thức dậy sau mỗi tick.

### Lỗi 11 — Bỏ qua zone khi kiểm tra "hôm nay"

Một Instant có thể là ngày khác ở UTC và Việt Nam. Test phải ghi rõ business ZoneId.

### Lỗi 12 — Dùng Duration cố định cho ngày lịch có DST

Một ngày địa phương có thể dài 23/25 giờ. Nếu nghiệp vụ là "ngày mai cùng giờ", dùng số học lịch với ZoneId thay vì Duration.ofHours(24).

### Lỗi 13 — Không test đúng tại deadline

Chỉ test trước và sau mà không test **now.equals(expiresAt)** dễ bỏ sót lỗi **<** và **<=**. Quy định end-exclusive hoặc end-inclusive và kiểm tra đúng biên.

### Lỗi 14 — Dùng assert thường mà quên bật -ea

Java assertions dạng **assert condition;** có thể bị vô hiệu mặc định. Dùng JUnit assertion hoặc ném AssertionError trực tiếp trong test harness chạy thuần.

### Lỗi 15 — Tưởng Clock làm test tự động kiểm soát scheduler

Clock chỉ cấp time source. Nếu một scheduler thực vẫn chạy theo OS time, cần test scheduler riêng.

### Lỗi 16 — Giả định Clock trả thời gian luôn tăng

System clock có thể bị điều chỉnh. Khi đo elapsed time trong một JVM, dùng nanoTime phù hợp.

### Lỗi 17 — Tưởng timestamp đủ xác định thứ tự giữa mọi máy

Clock không bảo đảm đồng bộ tuyệt đối giữa các node. Có thể cần ID, sequence hoặc log offsets.

### Lỗi 18 — Dùng Clock.fixed làm cấu hình production

Thời gian không tiến khiến TTL, audit và hạn dùng sai nghiêm trọng. Chỉ sử dụng cho môi trường test/mô phỏng được chủ động cấu hình.

### Lỗi 19 — Không validate Clock/null/TTL

Dùng **Objects.requireNonNull(clock)** và kiểm tra Duration hợp lệ. Với TTL <= 0, ứng dụng nên định nghĩa rõ hành vi: từ chối hoặc chấp nhận theo nghiệp vụ.

### Lỗi 20 — Test ngày hôm nay nhưng dùng ngày cứng trong production

Clock.fixed chỉ là test fixture. Production phải dùng nguồn thời gian thật được cấp tại ranh giới ứng dụng.

### Lỗi 21 — Dùng clock test ngoài ý muốn trong cấu hình bảo mật

Việc phát hành/kiểm tra token trong production cần nguồn thời gian đáng tin và chính sách bảo mật phù hợp. Clock injection giúp test, nhưng không tự bảo vệ chống điều chỉnh clock hoặc giả mạo thời gian nếu cấu hình bị thay đổi.

### Lỗi 22 — Tự viết mutable Clock không thread-safe

Clock có thể được chia sẻ giữa thread. Nếu thật sự cần custom Clock, phải tuân thủ yêu cầu thread-safety của API; nếu không cần, dùng built-in fixed/offset.

## 23. Checklist kiểm thử cho ứng dụng thời gian

| Test case | Clock setup | Điều cần xác minh |
|---|---|---|
| Khởi tạo bản ghi | fixed T0 | createdAt chính xác T0 |
| TTL vừa cấp | fixed T0 | Còn hiệu lực |
| Ngay trước expiry | offset(T0, ttl−1ns) | Còn hiệu lực |
| Đúng expiry | offset(T0, ttl) | Hết hiệu lực với end-exclusive |
| Sau expiry | offset(T0, ttl+1ns) | Hết hiệu lực |
| Một request nhiều timestamp | fixed hoặc hàm thuần nhận now | Các trường dùng cùng thời điểm logic |
| Zone UTC | fixed 23:30Z với UTC | Ngày lịch tại UTC |
| Zone Việt Nam | Cùng Instant, zone HCM | Ngày hôm sau |
| DST gap/overlap | fixed các Instant biên, zone New York | Thời gian địa phương đúng |
| End-of-month | fixed ngày 31 và calendar logic | Không tự giả định 30 ngày/tháng |
| Ngày nhuận | fixed cuối tháng 2/2024 | Ngày 29/2 hợp lệ |
| Zero/negative TTL | fixed, TTL không hợp lệ | Constructor từ chối theo chính sách |
| Clock trong test chạy song song | fixed riêng từng test | Không thay state global |
| Dữ liệu persistence | injected Clock + repository fake | Timestamp được ghi nhất quán |
| Scheduler | fake/controlled scheduler ngoài Clock | Callback được kích hoạt đúng |
| Production wiring | systemUTC hoặc system(zone) | Không vô tình dùng fixed clock |
| Quan sát tick | fixed base + tick | Truncation và precision đúng |
| InstantSource nếu Java17+ | dependency chỉ cần Instant | Không vô ý phụ thuộc timezone |

### 23.1. Những câu hỏi cần trả lời trước khi thiết kế

1. Nghiệp vụ cần một **Instant**, **LocalDate** hay **ZonedDateTime**?
2. "Hôm nay" thuộc **zone của ai**?
3. Cần **một now cho cả request** hay đọc nhiều lần có chủ đích?
4. Deadline gồm hay không gồm thời điểm bằng nhau?
5. TTL tính theo **Duration** hay theo ngày/tháng lịch?
6. Service có cần Clock hay chỉ cần nhận một Instant ở phương thức thuần?
7. Test có thể dùng Clock.fixed/offset thay vì sleep không?
8. Scheduler/timer có phải dependency khác cần điều khiển không?
9. Hệ thống chạy trên nhiều máy có yêu cầu đồng bộ clock/sequence không?
10. Cấu hình production có cách bảo đảm không dùng nhầm clock mô phỏng không?

## 24. Bài tập tự kiểm tra

**Câu 1.** Vì sao lời gọi Instant.now() trực tiếp trong service có thể làm unit test không xác định?

**Câu 2.** Clock.systemUTC() có luôn trả cùng một Instant không?

**Câu 3.** Clock.fixed(instant, zone) trả giá trị nào khi gọi instant() nhiều lần?

**Câu 4.** Hai Clock.fixed cùng Instant nhưng khác ZoneId có cho LocalDate.now(clock) giống nhau không?

**Câu 5.** Clock.offset(base, Duration.ofMinutes(15)) có tự thay đổi base hay không?

**Câu 6.** Clock.tick(base, Duration.ofMinutes(1)) có kích hoạt job mỗi phút không?

**Câu 7.** Một phiên có expiresAt=10:15 và quy tắc now < expiresAt. Tại đúng 10:15, phiên còn hiệu lực không?

**Câu 8.** Có nên dùng Thread.sleep(15 phút) để test TTL 15 phút không?

**Câu 9.** Khi test tại 2026-01-01T23:30Z, ngày theo UTC và Asia/Ho_Chi_Minh là ngày nào?

**Câu 10.** Tại sao nên đọc Clock một lần để khởi tạo createdAt và expiresAt từ cùng sự kiện?

**Câu 11.** Vì sao dùng Clock.fixed ngay trong production là rủi ro?

**Câu 12.** Chuyển Clock.withZone(newZone) có làm Instant thay đổi không?

**Câu 13.** Khi nghiệp vụ là "ngày mai cùng giờ địa phương" qua DST, Duration.ofHours(24) có luôn đúng không?

**Câu 14.** Inject Clock có khiến một scheduler thật chạy các job khi test tua Clock không?

**Câu 15.** Đo hiệu năng của một đoạn code bằng Instant.now() hay System.nanoTime() phù hợp hơn?

**Câu 16.** Ở Java 17+, nếu service chỉ cần Instant mà không cần ZoneId, abstraction nào có thể dùng ngoài Clock?

**Câu 17.** Một fake Clock tùy chỉnh có cần thread-safe không?

**Câu 18.** Trong JUnit, có nhất thiết mock static Instant.now() để kiểm tra service đã inject Clock không?

**Câu 19.** Làm thế nào kiểm thử được một ngày nhuận mà không thay đổi clock hệ điều hành?

**Câu 20.** Clock injection có tự bảo đảm đồng hồ nhiều server luôn đồng bộ tuyệt đối không?

### Đáp án

1. Vì nó đọc thời gian hệ thống thật, thay đổi theo lúc chạy và không kiểm soát được trong test.
2. **Không.** systemUTC là system clock đang chạy, chỉ dùng UTC zone.
3. **Cùng một Instant**.
4. **Không nhất thiết.** Cùng Instant có thể là ngày khác ở các múi giờ khác nhau.
5. **Không.** Clock.offset trả Clock mới, không mutate base.
6. **Không.** Tick chỉ giới hạn nhịp/độ phân giải quan sát.
7. **Không**, vì điều kiện isBefore là false khi bằng nhau.
8. **Không nên.** Dùng Clock.fixed/offset để test ngay các boundary.
9. **UTC: 2026-01-01; Việt Nam: 2026-01-02**.
10. Để các field dựa trên cùng một mốc thời gian logic, tránh thời gian trôi giữa hai lời gọi.
11. Clock fixed không tiến, khiến hạn dùng/audit/time-based logic sai trong vận hành thực tế.
12. **Không** với cùng time source; chỉ zone diễn giải thay đổi.
13. **Không.** Ngày địa phương có DST có thể dài 23/25 giờ.
14. **Không.** Cần điều khiển scheduler/test environment riêng.
15. **System.nanoTime()** cho elapsed-time trong một JVM; Instant dùng cho timestamp.
16. **InstantSource** (có từ Java 17).
17. **Có**, nếu viết custom Clock có thể chia sẻ nhiều thread; theo hợp đồng Clock phải thread-safe.
18. **Không.** Clock.fixed thường đủ, dễ đọc và ít brittle.
19. Inject Clock.fixed tại Instant/ZoneId tương ứng ngày 29/2/2024, rồi kiểm tra LocalDate.now(clock).
20. **Không.** Cần cơ chế đồng bộ và các công cụ giải quyết thứ tự khi cần.

## 25. Tổng kết

**Truyền Clock vào ứng dụng là cách tách business logic khỏi đồng hồ thực**. Nó giúp unit test **nhanh, ổn định, xác định và không lệ thuộc thời điểm chạy**.

Những nguyên tắc nên mang vào dự án:

- **Constructor inject Clock** vào service cần "now"; đừng hard-code Instant.now()/LocalDate.now() không tham số trong business logic.
- **Production:** Clock.systemUTC() khi chủ yếu dùng Instant, hoặc Clock.system(zone) khi cần zone nghiệp vụ cụ thể.
- **Test:** Clock.fixed(instant, zone) cho mốc xác định; Clock.offset để kiểm tra tương lai/quá khứ và deadline.
- **Clock.withZone** thay múi giờ diễn giải, không thay điểm thời gian; kiểm thử near-midnight và DST với zone cụ thể.
- **Clock.tick** giới hạn độ phân giải quan sát, không phải scheduler hoặc cơ chế tua thời gian.
- **Clock và Instant đều không thay việc thiết kế lịch nghiệp vụ:** TTL theo Duration khác hạn dùng theo ngày lịch/ZoneId.
- **Đọc Clock một lần trong một thao tác cần thời điểm chung**, rồi truyền Instant cho các hàm thuần.
- **Không dùng Thread.sleep hoặc thay đồng hồ JVM** để test những quy tắc đồng bộ dựa vào thời gian.
- **Clock không bảo đảm đồng bộ nhiều máy hoặc thời gian luôn tăng đều**; khi cần đo elapsed time, dùng System.nanoTime, và khi cần thứ tự sự kiện tuyệt đối còn cần cơ chế khác.
- **Trong Java 17+** có thêm InstantSource cho các service chỉ cần một nguồn Instant, nhưng Clock vẫn là giải pháp từ Java 8 phù hợp khi cần cả zone.

### Tài liệu chính thức (áp dụng với Java hiện hành)

- [Clock — Oracle Java SE 26: dependency injection, fixed, offset, tick, withZone, systemUTC](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/time/Clock.html)
- [Instant — Oracle Java SE 26: now(Clock), timeline, equals, isBefore](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/time/Instant.html)
- [LocalDate — Oracle Java SE 26: now(Clock), ngày cục bộ](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/time/LocalDate.html)
- [ZonedDateTime — Oracle Java SE 26: now(Clock), zone rules và DST](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/time/ZonedDateTime.html)
- [Duration — Oracle Java SE 26: lượng thời gian chính xác](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/time/Duration.html)
- [ZoneId — Oracle Java SE 26: timezone vùng và quy tắc](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/time/ZoneId.html)
- [InstantSource — Oracle Java SE 26: nguồn Instant (Java 17+)](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/time/InstantSource.html)
