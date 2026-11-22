# Nguồn thời gian trong Java 17: tạo Clock system, fixed, offset và tick

Ứng dụng Java thường cần biết thời điểm hiện tại để ghi dấu thời gian tạo đơn hàng, xác định ngày nghiệp vụ, kiểm tra thời hạn hoặc sắp xếp sự kiện. Nếu gọi trực tiếp `Instant.now()` hay `LocalDate.now()` ở khắp nơi, logic nghiệp vụ sẽ phụ thuộc vào đồng hồ thật của máy. Điều đó làm kiểm thử khó tái lập, vì kết quả thay đổi theo thời điểm chạy.

API `java.time.Clock` cung cấp một **nguồn thời gian có thể thay thế**. Thay vì để mọi lớp tự đọc đồng hồ hệ thống, ứng dụng có thể nhận một đối tượng `Clock` qua constructor hoặc tham số. Khi chạy thật, dùng clock hệ thống; khi kiểm thử, dùng clock cố định; khi cần mô phỏng, có thể dùng clock dịch thời gian hoặc chỉ nhảy theo từng nhịp.

Bài học này giải thích bốn cách tạo nguồn thời gian trong Java 17: **system**, **fixed**, **offset** và **tick**; đồng thời phân biệt thời điểm tuyệt đối với múi giờ, cách inject clock và những giới hạn cần biết khi dùng tick.

## 1. Vì sao cần một nguồn thời gian?

Một đoạn code đơn giản có thể lấy thời điểm hiện tại trực tiếp:

~~~java
import java.time.Instant;

Instant createdAt = Instant.now();
System.out.println(createdAt);
~~~

Đoạn mã hợp lệ, nhưng lớp chứa logic không kiểm soát được nguồn thời gian. Khi kiểm thử, mỗi lần gọi có thể trả về một instant khác nhau. Nếu cần kiểm tra “đơn hàng hết hạn sau 30 phút”, bài test phải phụ thuộc vào đồng hồ thật hoặc chờ thời gian trôi qua.

Thay vào đó, lấy thời gian qua `Clock`:

~~~java
import java.time.Clock;
import java.time.Instant;

Clock clock = Clock.systemUTC();
Instant createdAt = Instant.now(clock);
~~~

Lúc này, nguồn thời gian là một đối tượng có thể được thay thế. Cùng một đoạn code có thể nhận:

- clock hệ thống trong môi trường chạy thật;
- clock cố định trong unit test;
- clock offset để mô phỏng thời gian sớm hoặc muộn;
- clock tick để làm tròn thời gian theo một khoảng định trước.

`Clock` không phải timer, scheduler hay bộ đếm thời gian đơn điệu. Nó là abstraction cung cấp **instant hiện tại và zone dùng để diễn giải instant đó**.

## 2. Phân biệt Instant, ZoneId và Clock

Ba kiểu thường xuất hiện cùng nhau nhưng có trách nhiệm khác nhau:

| Kiểu | Vai trò | Ví dụ |
| --- | --- | --- |
| `Instant` | Một thời điểm tuyệt đối trên trục thời gian UTC. | `2026-11-15T10:00:00Z` |
| `ZoneId` | Quy tắc múi giờ dùng để chuyển instant thành ngày/giờ địa phương, gồm cả quy tắc DST nếu có. | `Asia/Ho_Chi_Minh` |
| `Clock` | Nguồn cung cấp instant và zone. | `Clock.system(ZoneId.of("Asia/Ho_Chi_Minh"))` |

Một instant không tự mang múi giờ. Cùng một instant có thể được hiển thị thành giờ địa phương khác nhau:

~~~java
import java.time.Instant;
import java.time.ZoneId;
import java.time.ZonedDateTime;

Instant instant = Instant.parse("2026-11-15T10:00:00Z");

ZonedDateTime inUtc = instant.atZone(ZoneId.of("UTC"));
ZonedDateTime inHcm = instant.atZone(ZoneId.of("Asia/Ho_Chi_Minh"));

System.out.println(inUtc);
System.out.println(inHcm);
~~~

Kết quả biểu diễn cùng thời điểm nhưng phần giờ địa phương khác nhau:

~~~text
2026-11-15T10:00Z[UTC]
2026-11-15T17:00+07:00[Asia/Ho_Chi_Minh]
~~~

Vì vậy, khi tạo clock, hãy chọn zone theo ý nghĩa nghiệp vụ:

- Dùng UTC khi cần thời điểm nhất quán để lưu trữ, trao đổi hoặc ghi log.
- Dùng zone cụ thể khi logic cần ngày/giờ địa phương của một khu vực.
- Tránh phụ thuộc ngầm vào múi giờ mặc định của máy chủ nếu nghiệp vụ cần một zone xác định.

## 3. Tạo clock hệ thống: system, systemUTC và systemDefaultZone

### 3.1. Clock.system(ZoneId)

Tạo clock dựa trên đồng hồ hệ thống với zone được chỉ định:

~~~java
import java.time.Clock;
import java.time.ZoneId;

Clock hcmClock = Clock.system(ZoneId.of("Asia/Ho_Chi_Minh"));
~~~

Mỗi lần gọi `hcmClock.instant()`, clock lấy thời điểm hiện tại từ nguồn thời gian của hệ thống. Các API như `LocalDate.now(hcmClock)` dùng zone của clock để xác định ngày địa phương.

Ví dụ:

~~~java
import java.time.Clock;
import java.time.LocalDate;
import java.time.LocalTime;
import java.time.ZoneId;

public class SystemClockDemo {
    public static void main(String[] args) {
        Clock clock = Clock.system(ZoneId.of("Asia/Ho_Chi_Minh"));

        System.out.println("Instant: " + clock.instant());
        System.out.println("Date: " + LocalDate.now(clock));
        System.out.println("Time: " + LocalTime.now(clock));
    }
}
~~~

`Clock.system(zone)` phù hợp khi muốn lấy giờ hệ thống nhưng chủ động chỉ định múi giờ diễn giải.

### 3.2. Clock.systemUTC()

Nếu ứng dụng chủ yếu làm việc với instant UTC, dùng:

~~~java
Clock utcClock = Clock.systemUTC();
Instant now = Instant.now(utcClock);
~~~

Clock này có zone UTC. Đây là lựa chọn rõ ràng cho các trường hợp cần mốc thời gian tuyệt đối, tránh phụ thuộc múi giờ cấu hình trên máy chạy.

### 3.3. Clock.systemDefaultZone()

Tạo clock dùng múi giờ mặc định của JVM:

~~~java
Clock defaultClock = Clock.systemDefaultZone();
System.out.println(defaultClock.getZone());
~~~

Lựa chọn này hữu ích khi ứng dụng thực sự muốn tuân theo cấu hình timezone mặc định của tiến trình. Tuy nhiên, kết quả có thể khác giữa máy developer, máy CI, container và production nếu cấu hình không đồng nhất.

Nếu nghiệp vụ yêu cầu một zone cố định, hãy dùng `Clock.system(ZoneId.of("..."))` để thể hiện rõ ý định.

### 3.4. Clock hệ thống không phải đồng hồ đơn điệu

Clock hệ thống phản ánh thời gian lịch (wall-clock time). Thời gian có thể được điều chỉnh bởi hệ điều hành, đồng bộ NTP, người quản trị hoặc môi trường ảo hóa. Vì vậy, hai lần đọc liên tiếp không được đảm bảo luôn tăng đều theo một nhịp ổn định.

Để đo **thời lượng đã trôi qua** hoặc thời gian thực thi, dùng `System.nanoTime()`:

~~~java
long start = System.nanoTime();
performWork();
long elapsedNanos = System.nanoTime() - start;
System.out.println("Elapsed ns = " + elapsedNanos);
~~~

Không dùng `Instant.now(clock)` để benchmark hoặc đo elapsed time nếu cần đồng hồ đơn điệu. Dùng `Clock` cho thời điểm lịch; dùng `System.nanoTime()` cho đo khoảng thời gian.

## 4. Tạo clock cố định: Clock.fixed

`Clock.fixed(Instant, ZoneId)` tạo một clock luôn trả về **cùng một instant**. Đây là lựa chọn rất hữu ích cho unit test và mô phỏng.

~~~java
import java.time.Clock;
import java.time.Instant;
import java.time.ZoneId;

Instant fixedInstant = Instant.parse("2026-04-10T03:00:00Z");
Clock fixedClock = Clock.fixed(
        fixedInstant,
        ZoneId.of("Asia/Ho_Chi_Minh")
);

System.out.println(fixedClock.instant());
System.out.println(fixedClock.instant());
~~~

Cả hai lần gọi đều trả về:

~~~text
2026-04-10T03:00:00Z
2026-04-10T03:00:00Z
~~~

Múi giờ của clock không làm thay đổi instant cố định. Nó chỉ ảnh hưởng cách các API chuyển instant thành ngày/giờ địa phương.

### 4.1. Dùng clock cố định để kiểm thử ngày địa phương

~~~java
import java.time.Clock;
import java.time.Instant;
import java.time.LocalDate;
import java.time.ZoneId;

public class FixedClockDemo {
    public static void main(String[] args) {
        Clock clock = Clock.fixed(
                Instant.parse("2026-04-10T18:00:00Z"),
                ZoneId.of("Asia/Ho_Chi_Minh")
        );

        System.out.println(Instant.now(clock));
        System.out.println(LocalDate.now(clock));
    }
}
~~~

Instant là 18:00 UTC; ở Ho Chi Minh City, đó là 01:00 sáng ngày hôm sau. Vì vậy ngày địa phương được in là:

~~~text
2026-04-11
~~~

Ví dụ này cho thấy test phải cố định cả **instant** và **zone** nếu logic phụ thuộc ngày địa phương.

### 4.2. Ứng dụng trong unit test

Giả sử service cần ghi thời điểm tạo đơn:

~~~java
import java.time.Clock;
import java.time.Instant;
import java.util.Objects;

final class OrderService {
    private final Clock clock;

    OrderService(Clock clock) {
        this.clock = Objects.requireNonNull(clock);
    }

    Instant createdAt() {
        return Instant.now(clock);
    }
}
~~~

Test không cần chờ hoặc phụ thuộc giờ máy:

~~~java
import java.time.Clock;
import java.time.Instant;
import java.time.ZoneOffset;

public class OrderServiceDemo {
    public static void main(String[] args) {
        Instant expected = Instant.parse("2026-04-10T03:00:00Z");
        Clock testClock = Clock.fixed(expected, ZoneOffset.UTC);

        OrderService service = new OrderService(testClock);

        System.out.println(service.createdAt().equals(expected)); // true
    }
}
~~~

Test có thể lặp lại với cùng đầu vào. Đây là lợi ích lớn nhất của việc inject `Clock`: thời gian trở thành một dependency có thể điều khiển.

## 5. Tạo clock dịch thời gian: Clock.offset

`Clock.offset(baseClock, duration)` tạo clock có instant bằng instant của clock gốc cộng thêm một khoảng thời gian. Duration có thể dương hoặc âm.

~~~java
import java.time.LocalDateTime;
import java.time.Clock;
import java.time.Duration;
import java.time.Instant;
import java.time.ZoneId;
import java.time.ZoneOffset;

Instant baseInstant = Instant.parse("2026-04-10T03:00:00Z");
Clock base = Clock.fixed(baseInstant, ZoneOffset.UTC);

Clock twoHoursLater = Clock.offset(base, Duration.ofHours(2));
Clock oneDayEarlier = Clock.offset(base, Duration.ofDays(-1));

System.out.println(twoHoursLater.instant());
System.out.println(oneDayEarlier.instant());
~~~

Kết quả:

~~~text
2026-04-10T05:00:00Z
2026-04-09T03:00:00Z
~~~

Clock offset giữ zone của clock gốc; nó dịch **instant** được trả về.

### 5.1. offset khác withZone

Hai thao tác thường bị nhầm:

- `Clock.offset(base, duration)` làm thay đổi instant bằng cách cộng duration.
- `base.withZone(zone)` giữ nguyên instant, chỉ đổi zone dùng để biểu diễn ngày/giờ.

~~~java
Clock base = Clock.fixed(
        Instant.parse("2026-04-10T03:00:00Z"),
        ZoneOffset.UTC
);

Clock shifted = Clock.offset(base, Duration.ofHours(2));
Clock sameInstantInHcm =
        base.withZone(ZoneId.of("Asia/Ho_Chi_Minh"));

System.out.println(base.instant().equals(shifted.instant())); // false
System.out.println(base.instant().equals(sameInstantInHcm.instant())); // true
System.out.println(LocalDateTime.now(base));
System.out.println(LocalDateTime.now(sameInstantInHcm));
~~~

`withZone` không phải cách “cộng giờ”; nó chỉ thay đổi cách diễn giải cùng một thời điểm. Nếu muốn mô phỏng đồng hồ chạy nhanh hơn hai tiếng, dùng `offset`.

### 5.2. Mô phỏng thời gian trong test

Ví dụ một service kiểm tra thời hạn:

~~~java
import java.time.Clock;
import java.time.Duration;
import java.time.Instant;
import java.time.ZoneOffset;

Instant start = Instant.parse("2026-04-10T03:00:00Z");
Clock fixed = Clock.fixed(start, ZoneOffset.UTC);
Clock thirtyMinutesLater =
        Clock.offset(fixed, Duration.ofMinutes(30));

System.out.println(Instant.now(fixed));
System.out.println(Instant.now(thirtyMinutesLater));
~~~

Bạn có thể kiểm tra nhánh “chưa hết hạn” và “đã hết hạn” mà không phải chờ 30 phút thực. Trong test phức tạp hơn, truyền từng clock vào service hoặc tạo clock offset theo từng kịch bản.

## 6. Tạo clock chỉ nhảy theo nhịp: Clock.tick

`Clock.tick(baseClock, tickDuration)` tạo clock lấy thời gian từ clock gốc nhưng **làm tròn xuống theo các mốc tick**. Ví dụ, với tick 10 giây, thời gian quan sát được chỉ thay đổi ở các mốc 00, 10, 20, 30, 40, 50 giây.

~~~java
import java.time.Clock;
import java.time.Duration;
import java.time.ZoneOffset;

Clock base = Clock.systemUTC();
Clock tenSecondClock = Clock.tick(base, Duration.ofSeconds(10));

System.out.println(tenSecondClock.instant());
~~~

Nếu thời gian hệ thống là 12:34:27.800Z, giá trị tick tương ứng được làm tròn xuống mốc 12:34:20Z.

### 6.1. Các factory tiện lợi

Java cung cấp các phương thức tiện dụng:

| Factory | Tác dụng |
| --- | --- |
| `Clock.tickMillis(zone)` | Clock tick theo mili giây. |
| `Clock.tickSeconds(zone)` | Clock tick theo giây. |
| `Clock.tickMinutes(zone)` | Clock tick theo phút. |
| `Clock.tick(base, duration)` | Tự chọn clock gốc và khoảng tick. |

Ví dụ:

~~~java
Clock secondsInHcm =
        Clock.tickSeconds(ZoneId.of("Asia/Ho_Chi_Minh"));
Clock minutesUtc = Clock.tickMinutes(ZoneOffset.UTC);
Clock millisUtc = Clock.tickMillis(ZoneOffset.UTC);
~~~

Các factory tiện lợi tương đương việc tick một clock hệ thống với zone được truyền vào và duration tương ứng.

### 6.2. Quy tắc duration

Tick duration phải **lớn hơn zero**. Duration không hợp lệ có thể khiến `Clock.tick` ném `IllegalArgumentException`. Với duration có phần nhỏ hơn một mili giây, quy tắc của API yêu cầu duration chia hết một giây để việc xác định tick có thể thực hiện chính xác theo đơn vị nano giây.

Ví dụ các khoảng thông dụng:

~~~java
Clock oneSecond = Clock.tick(Clock.systemUTC(), Duration.ofSeconds(1));
Clock fiveMinutes = Clock.tick(Clock.systemUTC(), Duration.ofMinutes(5));
Clock halfSecond = Clock.tick(Clock.systemUTC(), Duration.ofMillis(500));
~~~

Chọn khoảng tick theo độ phân giải cần thiết. Tick 1 phút không phù hợp nếu ứng dụng cần dấu thời gian chính xác đến mili giây.

### 6.3. Tick không phải bộ lập lịch sự kiện

Clock tick chỉ làm tròn giá trị thời gian mà nó trả về. Nó **không phát tín hiệu**, không gọi callback ở mỗi tick và không bảo đảm task được chạy đúng tại mốc tick.

Ngoài ra, implementation có thể sử dụng chiến lược cache. Vì vậy, thời điểm quan sát được khi một tick bắt đầu có thể muộn hơn thời điểm bắt đầu thực tế của khoảng đó. Không dùng `Clock.tick` để đo chính xác elapsed time, điều khiển animation, tạo scheduler hoặc thay thế `ScheduledExecutorService`.

Nếu cần chạy một tác vụ định kỳ, dùng scheduler:

~~~java
import java.util.concurrent.Executors;
import java.util.concurrent.TimeUnit;

var scheduler = Executors.newSingleThreadScheduledExecutor();
scheduler.scheduleAtFixedRate(
        () -> System.out.println("Run task"),
        0,
        10,
        TimeUnit.SECONDS
);
~~~

Đoạn minh họa này cần được kết thúc bằng `scheduler.shutdown()` khi ứng dụng không còn cần scheduler. Scheduler điều khiển việc thực thi task; `Clock.tick` chỉ cung cấp giá trị thời gian đã làm tròn.

### 6.4. Tick theo duration không đồng nghĩa ranh giới lịch địa phương

Không nên giả định `Clock.tick(base, Duration.ofDays(1))` là cách diễn đạt đúng cho “đồng hồ chỉ đổi lúc nửa đêm theo múi giờ địa phương”. Tick dựa trên khoảng thời gian cố định, trong khi một ngày lịch tại zone có quy tắc DST có thể dài 23 hoặc 25 giờ.

Nếu nghiệp vụ cần ngày hiện tại hoặc đầu ngày tại một zone, hãy dùng API lịch:

~~~java
import java.time.Clock;
import java.time.Instant;
import java.time.LocalDate;
import java.time.ZoneId;
import java.time.ZoneOffset;
import java.time.ZonedDateTime;

LocalDate today = LocalDate.now(clock);
ZonedDateTime startOfDay =
        today.atStartOfDay(clock.getZone());
~~~

`atStartOfDay(zone)` áp dụng quy tắc múi giờ để tìm thời điểm bắt đầu ngày lịch. Đó là khái niệm khác với tick theo một duration cố định.

## 7. Kết hợp các loại clock

Các factory có thể kết hợp để tạo nguồn thời gian phục vụ một mục tiêu cụ thể.

### 7.1. Tick một clock offset

~~~java
Clock base = Clock.systemUTC();
Clock shifted = Clock.offset(base, Duration.ofMinutes(15));
Clock shiftedAndTicked =
        Clock.tick(shifted, Duration.ofSeconds(30));
~~~

Thời gian được dịch thêm 15 phút rồi làm tròn xuống mốc 30 giây. Đây là ví dụ mô phỏng; cần ghi rõ ý nghĩa của việc dịch thời gian trong cấu hình hoặc test để tránh nhầm với giờ thực.

### 7.2. Đổi zone của clock fixed

~~~java
Instant instant = Instant.parse("2026-04-10T03:00:00Z");
Clock fixedUtc = Clock.fixed(instant, ZoneOffset.UTC);
Clock fixedHcm = fixedUtc.withZone(
        ZoneId.of("Asia/Ho_Chi_Minh")
);

System.out.println(fixedUtc.instant().equals(fixedHcm.instant())); // true
System.out.println(LocalDate.now(fixedUtc));
System.out.println(LocalDate.now(fixedHcm));
~~~

Instant vẫn cố định, nhưng ngày địa phương có thể khác nếu thời điểm gần ranh giới ngày.

## 8. Inject Clock vào ứng dụng

Thay vì gọi trực tiếp `Instant.now()` hoặc `LocalDate.now()` trong mọi lớp, hãy đưa `Clock` vào nơi cần biết thời gian.

~~~java
import java.time.Clock;
import java.time.Instant;
import java.time.LocalDate;
import java.time.ZoneId;
import java.util.Objects;

public final class SubscriptionService {
    private final Clock clock;

    public SubscriptionService(Clock clock) {
        this.clock = Objects.requireNonNull(clock);
    }

    public Instant subscriptionStartedAt() {
        return Instant.now(clock);
    }

    public LocalDate billingDate() {
        return LocalDate.now(clock);
    }
}
~~~

Trong composition root hoặc cấu hình ứng dụng, tạo clock dùng thật:

~~~java
Clock applicationClock =
        Clock.system(ZoneId.of("Asia/Ho_Chi_Minh"));
SubscriptionService service =
        new SubscriptionService(applicationClock);
~~~

Trong unit test, truyền clock cố định:

~~~java
Clock testClock = Clock.fixed(
        Instant.parse("2026-04-10T03:00:00Z"),
        ZoneId.of("Asia/Ho_Chi_Minh")
);
SubscriptionService service = new SubscriptionService(testClock);
~~~

Lợi ích:

- Test không phụ thuộc ngày giờ thực của máy.
- Có thể kiểm tra thời điểm trước/sau hạn bằng `fixed` và `offset`.
- Zone được chọn rõ ràng ở nơi cấu hình.
- Logic nghiệp vụ không cần biết đồng hồ được lấy từ hệ điều hành hay từ test.

Không cần inject `Clock` vào mọi lớp. Chỉ đưa nó vào những thành phần thực sự phụ thuộc thời gian, rồi truyền kết quả (`Instant`, `LocalDate`, v.v.) sang các lớp không cần tự đọc clock.

## 9. Các phương thức thời gian nhận Clock

Nhiều kiểu trong `java.time` có overload nhận clock:

~~~java
Instant instant = Instant.now(clock);
LocalDate date = LocalDate.now(clock);
LocalTime time = LocalTime.now(clock);
LocalDateTime localDateTime = LocalDateTime.now(clock);
ZonedDateTime zonedDateTime = ZonedDateTime.now(clock);
OffsetDateTime offsetDateTime = OffsetDateTime.now(clock);
~~~

Điều này giúp dùng chung một nguồn thời gian cho nhiều loại giá trị. Hãy lựa chọn kiểu theo ý nghĩa:

| Kiểu | Dùng khi |
| --- | --- |
| `Instant` | Cần mốc thời gian tuyệt đối, lưu trữ hoặc trao đổi giữa hệ thống. |
| `LocalDate` | Cần ngày lịch tại một zone. |
| `LocalTime` | Cần giờ trong ngày tại một zone. |
| `LocalDateTime` | Cần ngày và giờ địa phương nhưng không mang zone/offset. |
| `ZonedDateTime` | Cần ngày giờ gắn với zone và quy tắc múi giờ. |
| `OffsetDateTime` | Cần ngày giờ kèm UTC offset cụ thể. |

Nếu cần lưu một thời điểm sự kiện, thường ưu tiên `Instant`. Chỉ chuyển sang ngày giờ địa phương ở biên hiển thị hoặc khi nghiệp vụ thực sự dựa vào lịch của một khu vực.

## 10. Các giới hạn và lỗi thường gặp

| Hiện tượng | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| Unit test cho ngày hiện tại lúc đúng lúc sai | Code gọi đồng hồ hệ thống trực tiếp. | Inject `Clock`, dùng `Clock.fixed` trong test. |
| Ngày khác nhau giữa máy developer và server | Dùng `systemDefaultZone()` hoặc timezone mặc định khác nhau. | Chọn `ZoneId` rõ ràng theo nghiệp vụ. |
| Nghĩ `withZone` làm thời gian chạy nhanh/chậm | `withZone` chỉ đổi zone, không dịch instant. | Dùng `Clock.offset` nếu cần dịch instant. |
| Dùng `tick` để chạy task mỗi giây | `Clock.tick` không lập lịch và không phát callback. | Dùng `ScheduledExecutorService` hoặc scheduler phù hợp. |
| Tick theo ngày nhưng lệch nửa đêm địa phương | Duration cố định không đồng nghĩa ngày lịch ở zone. | Dùng `LocalDate` và `atStartOfDay(zone)`. |
| Đo elapsed time bằng hai lần đọc clock hệ thống | Wall clock có thể bị điều chỉnh. | Dùng `System.nanoTime()` để đo khoảng thời gian. |
| Tick duration bằng zero hoặc âm | Duration không hợp lệ. | Dùng duration dương theo yêu cầu API. |
| Cần độ chính xác cao nhưng dùng tick phút/giây | Clock đã làm tròn giá trị trả về. | Chọn duration nhỏ hơn hoặc dùng clock gốc phù hợp. |
| Offset clock bị nhầm là giờ hệ thống | `Clock.offset` thay đổi instant được trả về. | Chỉ dùng cho mô phỏng hoặc quy tắc thời gian có chủ đích. |

## 11. Ví dụ tổng hợp: kiểm thử thời hạn đăng ký

Ví dụ sau mô hình hóa một subscription có thời hạn 30 ngày. Service nhận clock để kiểm tra trạng thái tại thời điểm hiện tại:

~~~java
import java.time.Clock;
import java.time.Duration;
import java.time.Instant;
import java.time.ZoneOffset;
import java.util.Objects;

final class Subscription {
    private final Instant startedAt;

    Subscription(Instant startedAt) {
        this.startedAt = Objects.requireNonNull(startedAt);
    }

    boolean isExpired(Clock clock) {
        Instant expiresAt = startedAt.plus(Duration.ofDays(30));
        return !Instant.now(clock).isBefore(expiresAt);
    }
}

public class SubscriptionClockDemo {
    public static void main(String[] args) {
        Instant startedAt = Instant.parse("2026-01-01T00:00:00Z");
        Subscription subscription = new Subscription(startedAt);

        Clock beforeExpiry = Clock.fixed(
                Instant.parse("2026-01-30T23:59:59Z"),
                ZoneOffset.UTC
        );
        Clock atExpiry = Clock.fixed(
                Instant.parse("2026-01-31T00:00:00Z"),
                ZoneOffset.UTC
        );

        System.out.println(subscription.isExpired(beforeExpiry)); // false
        System.out.println(subscription.isExpired(atExpiry)); // true
    }
}
~~~

Hai kịch bản chạy tức thì và kết quả không phụ thuộc đồng hồ máy. Ví dụ dùng `Duration.ofDays(30)` để biểu diễn đúng 30 × 24 giờ. Nếu nghiệp vụ là “hết hạn vào cùng ngày lịch tháng sau” hoặc “hết hạn lúc nửa đêm tại một zone”, cần mô hình bằng `LocalDate`, `Period`, `ZonedDateTime` và quy tắc lịch tương ứng thay vì coi đó là cùng một khoảng duration.

## 12. Bài tập tự luyện

### Bài 1 — Chọn loại clock

Chọn factory phù hợp:

1. Ứng dụng production cần thời điểm UTC hiện tại.
2. Unit test cần mọi lần đọc trả về đúng cùng một instant.
3. Test cần mô phỏng thời gian đi trước 90 phút.
4. Một báo cáo chỉ cần thời gian thay đổi theo từng phút.

**Gợi ý:** `systemUTC`, `fixed`, `offset` và `tickMinutes` tương ứng.

### Bài 2 — Phân biệt offset và zone

~~~java
Clock base = Clock.fixed(
        Instant.parse("2026-04-10T03:00:00Z"),
        ZoneOffset.UTC
);
Clock plusOneHour = Clock.offset(base, Duration.ofHours(1));
Clock hcmZone = base.withZone(ZoneId.of("Asia/Ho_Chi_Minh"));
~~~

Hãy dự đoán:

- Clock nào trả về instant khác `base`?
- Clock nào chỉ đổi cách chuyển instant thành giờ địa phương?

**Đáp án:** `plusOneHour` trả instant khác; `hcmZone` giữ instant và đổi zone.

### Bài 3 — Test không phụ thuộc đồng hồ thật

Viết một class `ReminderService` nhận `Clock` qua constructor và có phương thức trả về ngày hiện tại. Tạo hai test với hai `Clock.fixed` ở hai ngày khác nhau để chứng minh kết quả có thể điều khiển.

### Bài 4 — Tick và scheduler

Giải thích vì sao `Clock.tickSeconds(ZoneOffset.UTC)` không thể thay cho một scheduler chạy công việc mỗi giây. Hãy nêu API phù hợp để lên lịch công việc và API phù hợp để lấy thời gian đã làm tròn.

### Bài 5 — Ngày lịch hay duration?

Một gói dịch vụ hết hạn “sau 24 giờ” hay “vào đầu ngày tiếp theo tại múi giờ của khách hàng” là hai yêu cầu khác nhau. Hãy chọn giữa `Duration`, `LocalDate`, `ZoneId` và `atStartOfDay` cho từng trường hợp, rồi giải thích ảnh hưởng của ngày có thay đổi DST.

## 13. Ghi nhớ khi tạo nguồn thời gian

- `Clock` cung cấp instant và zone; nó giúp tách logic nghiệp vụ khỏi đồng hồ thật.
- `Clock.system(zone)` lấy thời gian hệ thống theo zone đã chọn; `systemUTC()` dùng UTC; `systemDefaultZone()` phụ thuộc timezone mặc định của JVM.
- `Clock.fixed(instant, zone)` luôn trả cùng một instant, rất hữu ích cho unit test.
- `Clock.offset(base, duration)` dịch instant của clock gốc; duration có thể dương hoặc âm.
- `Clock.tick(base, duration)` làm tròn xuống theo nhịp; các factory `tickMillis`, `tickSeconds`, `tickMinutes` là dạng tiện lợi.
- `withZone(zone)` đổi zone nhưng giữ nguyên instant; không nhầm với `offset`.
- Tick không phải scheduler, không phải đồng hồ đo thời lượng và không đại diện tự động cho ranh giới ngày lịch.
- Dùng `System.nanoTime()` để đo elapsed time; dùng `Clock`/`Instant` cho thời điểm lịch.
- Inject `Clock` vào các thành phần phụ thuộc thời gian để test xác định và dễ mô phỏng.

### Tài liệu tham khảo

- [Java SE 17 API — `java.time.Clock`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/Clock.html) — factory system, fixed, offset, tick, zone và hợp đồng của Clock.
- [Java SE 17 API — `Instant`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/Instant.html) — biểu diễn thời điểm tuyệt đối và overload `now(Clock)`.
- [Java SE 17 API — `ZoneId`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/ZoneId.html) — định danh múi giờ và quy tắc zone.
- [Java SE 17 API — `System.nanoTime()`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/System.html#nanoTime()) — nguồn thời gian đơn điệu dùng đo thời lượng.
- [Java SE 17 API — `ScheduledExecutorService`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ScheduledExecutorService.html) — lập lịch tác vụ định kỳ hoặc có độ trễ.
