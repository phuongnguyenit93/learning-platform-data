# Truyền nguồn thời gian vào đối tượng thay vì gọi thời gian trực tiếp trong Java 17

## 1. Vấn đề khi đối tượng tự đọc giờ hệ thống

Một lớp nghiệp vụ thường cần biết thời điểm hiện tại để tạo ngày lập hóa đơn, xác định đơn hàng hết hạn, kiểm tra thời gian dùng thử hoặc ghi nhận thời điểm cập nhật. Cách viết trực tiếp thường gặp:

~~~java
import java.time.Instant;

public final class TrialService {
    public boolean isExpired(Instant expiresAt) {
        return Instant.now().isAfter(expiresAt);
    }
}
~~~

Đoạn mã ngắn và chạy được, nhưng nó phụ thuộc vào đồng hồ thật của máy đang chạy. Khi kiểm thử, bạn không thể chủ động đặt thời điểm hiện tại về một ngày cố định. Kết quả có thể thay đổi theo ngày chạy test, múi giờ của máy, thời gian hệ thống bị điều chỉnh hoặc độ trễ của quá trình thực thi.

Một test kiểu:

~~~java
assertTrue(service.isExpired(Instant.now().minusSeconds(1)));
~~~

đang dùng đồng hồ thật cả khi chuẩn bị dữ liệu lẫn khi thực thi. Nếu hệ thống bị điều chỉnh thời gian giữa hai lời gọi hoặc test chạy gần ranh giới thời gian, việc tái hiện lỗi sẽ khó hơn. Với logic nghiệp vụ có nhiều nhánh theo ngày hoặc giờ, test phụ thuộc thời gian thật còn khó kiểm tra các tình huống trong quá khứ và tương lai.

Giải pháp phù hợp trong Java 17 là **truyền một nguồn thời gian vào đối tượng**. API `java.time.Clock` được thiết kế cho mục đích này: mã nghiệp vụ nhận một `Clock`, rồi lấy thời gian qua nó. Trong production, truyền clock của hệ thống; trong test, truyền clock cố định hoặc clock có độ lệch xác định.

> Thay vì để đối tượng tự quyết định "bây giờ là lúc nào", hãy để nơi khởi tạo đối tượng cung cấp câu trả lời đó.

## 2. `Clock` trong Java Time API

`Clock` là một lớp trừu tượng thuộc package `java.time`. Nó cung cấp nguồn thời gian hiện tại và múi giờ đi kèm. Các phương thức thường dùng:

| Phương thức | Mục đích |
|---|---|
| `Clock.systemUTC()` | Tạo clock dùng thời gian hệ thống với múi giờ UTC. |
| `Clock.system(ZoneId)` | Tạo clock dùng thời gian hệ thống theo múi giờ chỉ định. |
| `Clock.systemDefaultZone()` | Tạo clock theo múi giờ mặc định của hệ thống. |
| `Clock.fixed(Instant, ZoneId)` | Tạo clock luôn trả về cùng một thời điểm. |
| `Clock.offset(Clock, Duration)` | Tạo clock có thời điểm bằng clock gốc cộng thêm một độ lệch. |
| `Clock.tick(Clock, Duration)` | Tạo clock chỉ cập nhật theo các khoảng tick đã chỉ định. |
| `Clock.instant()` | Lấy thời điểm hiện tại từ clock dưới dạng `Instant`. |
| `Clock.millis()` | Lấy số mili giây từ epoch. |
| `Clock.getZone()` | Lấy múi giờ của clock. |
| `Clock.withZone(ZoneId)` | Trả về clock tương ứng với cùng nguồn thời gian nhưng múi giờ khác. |

Với đa số logic nghiệp vụ, cách dùng trực tiếp là:

~~~java
import java.time.Clock;
import java.time.Instant;
import java.time.LocalDate;

Clock clock = Clock.systemUTC();

Instant now = Instant.now(clock);
LocalDate todayUtc = LocalDate.now(clock);
~~~

Các phương thức tĩnh của kiểu thời gian như `Instant.now(Clock)`, `LocalDate.now(Clock)` và `ZonedDateTime.now(Clock)` nhận nguồn thời gian làm tham số. Đây là điểm kết nối giữa `Clock` và các kiểu ngày giờ khác trong Java Time API.

### 2.1. Tại sao dùng `Clock` thay vì tự tạo interface?

Bạn có thể tự định nghĩa interface như `TimeProvider` với một phương thức `now()`, nhưng Java đã cung cấp `Clock` cùng các implementation cần thiết:

- Dùng được trực tiếp với `Instant`, `LocalDate`, `LocalDateTime` và `ZonedDateTime`.
- Có sẵn clock hệ thống, clock cố định, clock có độ lệch và clock tick.
- Không cần tự viết cơ chế giả lập thời gian trong các test đơn giản.
- Dùng được cùng các API trong package `java.time`.

Nếu ứng dụng có yêu cầu đặc thù như đọc đồng hồ từ một dịch vụ bên ngoài hoặc cần một abstraction có nhiều thao tác nghiệp vụ, interface riêng có thể hợp lý. Nhưng với phần lớn ứng dụng Java 17, `Clock` là lựa chọn tiêu chuẩn và đơn giản.

## 3. Constructor injection: truyền Clock vào đối tượng

Một đối tượng phụ thuộc vào thời gian nên nhận `Clock` qua constructor. Ví dụ:

~~~java
import java.time.Clock;
import java.time.Instant;
import java.util.Objects;

public final class TrialService {
    private final Clock clock;

    public TrialService(Clock clock) {
        this.clock = Objects.requireNonNull(clock, "clock");
    }

    public boolean isExpired(Instant expiresAt) {
        Objects.requireNonNull(expiresAt, "expiresAt");
        Instant now = Instant.now(clock);
        return !now.isBefore(expiresAt);
    }
}
~~~

Ở đây:

1. `clock` được truyền vào lúc tạo đối tượng.
2. Trường `private final` giữ nguồn thời gian cố định trong suốt vòng đời của service.
3. `Objects.requireNonNull` xác nhận phụ thuộc bắt buộc, giúp lỗi cấu hình xuất hiện ngay khi tạo đối tượng.
4. Mỗi lần kiểm tra, service lấy thời điểm qua `Instant.now(clock)`.
5. Quy tắc hết hạn được định nghĩa rõ: thời điểm hiện tại **bằng hoặc sau** `expiresAt` thì đã hết hạn.

Việc lưu `Clock` thay vì lưu một `Instant now` trong constructor là rất quan trọng. `Clock` đại diện cho **nguồn có thể đọc nhiều lần**; `Instant` chỉ là một thời điểm. Nếu lưu `Instant.now(clock)` lúc tạo service, đối tượng sẽ luôn dùng thời điểm khởi tạo và không còn cập nhật theo thời gian.

### 3.1. Nơi tạo đối tượng cung cấp clock production

Ở composition root (nơi lắp ghép các đối tượng ứng dụng), tạo clock thật:

~~~java
import java.time.Clock;

public final class Application {
    public static void main(String[] args) {
        Clock clock = Clock.systemUTC();
        TrialService trialService = new TrialService(clock);

        // Lắp ghép và chạy các thành phần ứng dụng khác.
    }
}
~~~

Trong ứng dụng lớn, có thể tạo một bean hoặc dependency dùng chung và truyền nó vào các service qua constructor. Không cần mỗi service tự gọi `Clock.systemUTC()` để tạo nguồn thời gian riêng; truyền từ nơi khởi tạo giúp toàn ứng dụng dễ kiểm soát cấu hình và kiểm thử.

### 3.2. Tránh setter để thay clock sau khi đối tượng đã chạy

Một cách kém rõ ràng là:

~~~java
// Không nên dùng cho dependency bắt buộc.
public final class SomeService {
    private Clock clock;

    public void setClock(Clock clock) {
        this.clock = clock;
    }
}
~~~

Nếu service được gọi trước khi setter được gọi, trường clock có thể chưa được thiết lập. Việc thay clock giữa vòng đời cũng có thể làm hành vi không nhất quán. Với nguồn thời gian bắt buộc, constructor injection và trường `final` giúp hợp đồng đối tượng rõ ràng hơn.

## 4. Dùng Clock cố định để kiểm thử xác định

`Clock.fixed` trả về một clock luôn cung cấp cùng một `Instant`. Nó rất phù hợp khi test các điều kiện theo ngày hoặc thời điểm:

~~~java
import java.time.Clock;
import java.time.Instant;
import java.time.ZoneOffset;

Clock fixedClock = Clock.fixed(
        Instant.parse("2026-11-15T10:00:00Z"),
        ZoneOffset.UTC);

TrialService service = new TrialService(fixedClock);
~~~

Mọi lần gọi `Instant.now(fixedClock)` đều trả về `2026-11-15T10:00:00Z`. Test không phụ thuộc vào thời gian thật, có thể chạy hôm nay, ngày mai hoặc trên máy CI mà vẫn có cùng kết quả.

### 4.1. Viết test với JUnit Jupiter

Ví dụ test cho quy tắc hết hạn:

~~~java
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.time.Clock;
import java.time.Instant;
import java.time.ZoneOffset;
import org.junit.jupiter.api.Test;

class TrialServiceTest {

    private static final Instant NOW =
            Instant.parse("2026-11-15T10:00:00Z");

    private final Clock fixedClock =
            Clock.fixed(NOW, ZoneOffset.UTC);

    private final TrialService service =
            new TrialService(fixedClock);

    @Test
    void isNotExpiredWhenExpiryIsInFuture() {
        Instant expiresAt = NOW.plusSeconds(60);

        assertFalse(service.isExpired(expiresAt));
    }

    @Test
    void isExpiredWhenExpiryIsInPast() {
        Instant expiresAt = NOW.minusSeconds(60);

        assertTrue(service.isExpired(expiresAt));
    }

    @Test
    void isExpiredAtTheExactExpiryInstant() {
        assertTrue(service.isExpired(NOW));
    }
}
~~~

Ba test bao phủ ba tình huống quan trọng: hạn còn ở tương lai, hạn đã qua và thời điểm hiện tại đúng bằng hạn. Test thứ ba làm rõ quy tắc so sánh ở ranh giới. Nếu nghiệp vụ quy định chỉ hết hạn **sau** thời điểm hạn, hãy đổi phép so sánh và test tương ứng; điều quan trọng là chính sách phải được xác định rõ.

### 4.2. So sánh test phụ thuộc đồng hồ thật và test dùng Clock

| Cách kiểm thử | Đặc điểm |
|---|---|
| Gọi trực tiếp `Instant.now()` trong service | Kết quả thay đổi theo thời điểm chạy; khó đặt thời gian quá khứ/tương lai một cách xác định. |
| Truyền `Clock.systemUTC()` | Phù hợp production; test vẫn phụ thuộc thời gian thực nếu dùng clock này. |
| Truyền `Clock.fixed(...)` | Mỗi lần đọc đều cho cùng một thời điểm; phù hợp test xác định. |
| Truyền `Clock.offset(...)` | Mô phỏng một nguồn thời gian lệch khỏi clock gốc một khoảng xác định. |

Mục tiêu không phải làm cho mọi test đều dùng thời gian giả. Mục tiêu là để logic nghiệp vụ **có thể điều khiển thời gian** khi cần kiểm thử.

## 5. Dùng Clock offset để mô phỏng thời gian tương lai hoặc quá khứ

`Clock.offset` tạo clock có thời điểm bằng clock gốc cộng thêm `Duration`. Ví dụ:

~~~java
Clock base = Clock.fixed(
        Instant.parse("2026-11-15T10:00:00Z"),
        ZoneOffset.UTC);

Clock oneDayLater = Clock.offset(base, Duration.ofDays(1));
Clock oneHourEarlier = Clock.offset(base, Duration.ofHours(-1));

System.out.println(Instant.now(oneDayLater));
System.out.println(Instant.now(oneHourEarlier));
~~~

Kết quả lần lượt là:

~~~text
2026-11-16T10:00:00Z
2026-11-15T09:00:00Z
~~~

Vì clock gốc là fixed, các clock offset này cũng trả về thời điểm cố định. Đây là cách gọn để kiểm tra hành vi tại một ngày hoặc giờ khác mà không sửa đồng hồ hệ điều hành.

### 5.1. Test quy tắc dùng thử theo ngày

~~~java
import java.time.Clock;
import java.time.LocalDate;
import java.time.ZoneId;

public final class TrialPolicy {
    private final Clock clock;

    public TrialPolicy(Clock clock) {
        this.clock = clock;
    }

    public boolean isTrialActive(LocalDate startDate, int trialDays) {
        LocalDate today = LocalDate.now(clock);
        LocalDate endDate = startDate.plusDays(trialDays);
        return !today.isBefore(startDate) && today.isBefore(endDate);
    }
}
~~~

Test có thể tạo một clock tại ngày cụ thể:

~~~java
Clock testClock = Clock.fixed(
        Instant.parse("2026-11-15T12:00:00Z"),
        ZoneId.of("Asia/Ho_Chi_Minh"));

TrialPolicy policy = new TrialPolicy(testClock);
~~~

Ở ví dụ này, `LocalDate.now(clock)` lấy ngày theo zone gắn với clock. Với `Asia/Ho_Chi_Minh`, thời điểm `2026-11-15T12:00:00Z` tương ứng buổi tối cùng ngày tại Việt Nam. Khi test các mốc gần nửa đêm, zone là một phần của dữ liệu kiểm thử chứ không phải chi tiết trang trí.

## 6. Clock và múi giờ: chọn theo ý nghĩa nghiệp vụ

`Clock` có cả nguồn thời gian lẫn `ZoneId`. Cần hiểu rằng **Instant là thời điểm trên dòng thời gian**, còn `LocalDate` và `LocalDateTime` là giá trị lịch địa phương, phụ thuộc múi giờ khi chuyển đổi từ một instant.

### 6.1. Dùng UTC cho thời điểm tuyệt đối

Với timestamp dùng để ghi log, lưu sự kiện hoặc trao đổi giữa các hệ thống, thường nên dùng `Instant`:

~~~java
Instant createdAt = Instant.now(clock);
~~~

`Instant` biểu diễn thời điểm theo UTC timeline và không chứa múi giờ địa phương. Khi hiển thị cho người dùng, chuyển sang zone của họ:

~~~java
ZonedDateTime localView =
        createdAt.atZone(ZoneId.of("Asia/Ho_Chi_Minh"));
~~~

### 6.2. Dùng zone rõ ràng cho ngày nghiệp vụ

Một báo cáo "ngày hôm nay" của cửa hàng ở Việt Nam có thể khác ngày hôm nay của hệ thống đặt tại Mỹ. Vì vậy, hãy chỉ định zone nghiệp vụ:

~~~java
ZoneId businessZone = ZoneId.of("Asia/Ho_Chi_Minh");
Clock businessClock = Clock.system(businessZone);

LocalDate businessDate = LocalDate.now(businessClock);
~~~

Không nên phụ thuộc ngầm vào múi giờ mặc định của máy chủ bằng `Clock.systemDefaultZone()` nếu logic nghiệp vụ cần một zone ổn định. Giá trị mặc định có thể khác giữa máy phát triển, máy CI và production.

### 6.3. `withZone` thay đổi cách nhìn, không đổi thời điểm gốc

~~~java
Clock utcClock = Clock.fixed(
        Instant.parse("2026-11-15T23:30:00Z"),
        ZoneOffset.UTC);

Clock vietnamClock = utcClock.withZone(
        ZoneId.of("Asia/Ho_Chi_Minh"));

System.out.println(LocalDate.now(utcClock));
System.out.println(LocalDate.now(vietnamClock));
~~~

Hai clock biểu diễn cùng một instant cố định, nhưng `LocalDate.now` có thể trả về ngày khác vì zone khác nhau. Đây là lý do test theo ngày cần chỉ định zone, đặc biệt khi xử lý người dùng ở nhiều quốc gia hoặc thời điểm gần nửa đêm.

### 6.4. Tránh tự cộng số giờ để đổi múi giờ

Không nên làm:

~~~java
// Không nên dùng phép cộng cố định để đổi múi giờ.
Instant local = Instant.now(clock).plus(Duration.ofHours(7));
~~~

Múi giờ là tập quy tắc lịch sử và có thể có quy tắc giờ mùa hè (*daylight saving time*). Hãy dùng `ZoneId` và các phép chuyển đổi của Java Time API:

~~~java
ZonedDateTime local = Instant.now(clock)
        .atZone(ZoneId.of("Asia/Ho_Chi_Minh"));
~~~

Khi làm việc với zone có daylight saving time, `ZonedDateTime` và dữ liệu zone rules giúp xử lý khoảng giờ bị bỏ qua hoặc lặp lại. Một offset cố định như `ZoneOffset.ofHours(7)` chỉ phù hợp khi hợp đồng thực sự yêu cầu offset cố định, không thay thế một múi giờ địa lý.

## 7. Thiết kế service không phụ thuộc đồng hồ hệ thống

Một ứng dụng thường có nhiều lớp cần biết thời gian. Nếu mỗi lớp tự gọi `Instant.now()`, thời điểm dùng trong một thao tác có thể không nhất quán và rất khó điều khiển khi test. Hãy truyền cùng một `Clock` vào các đối tượng cần nguồn thời gian.

Ví dụ service tạo sự kiện:

~~~java
import java.time.Clock;
import java.time.Instant;
import java.util.Objects;

public final class OrderService {
    private final Clock clock;

    public OrderService(Clock clock) {
        this.clock = Objects.requireNonNull(clock, "clock");
    }

    public OrderCreated createOrder(String orderId) {
        Objects.requireNonNull(orderId, "orderId");
        return new OrderCreated(orderId, Instant.now(clock));
    }
}

record OrderCreated(String orderId, Instant createdAt) {
}
~~~

Ở đây, thời điểm tạo đơn được đọc từ clock đã truyền vào. Không cần truyền `Instant.now()` từ bên ngoài mỗi lần gọi `createOrder`, vì service cần **nguồn thời gian có thể đọc tại thời điểm thao tác**, không phải một timestamp đã tính trước.

### 7.1. Chia sẻ cùng Clock giữa các service

~~~java
Clock clock = Clock.systemUTC();

OrderService orderService = new OrderService(clock);
TrialService trialService = new TrialService(clock);
~~~

Trong production, hai service cùng đọc từ một nguồn clock được cấu hình tại composition root. Trong test, có thể thay bằng một `Clock.fixed` cho cả hai để kiểm tra một kịch bản xuyên suốt.

Không nhất thiết phải có một đối tượng clock toàn cục static. Truyền phụ thuộc tường minh giúp thấy rõ lớp nào cần thời gian, dễ thay thế khi test và tránh ẩn dependency trong mã.

### 7.2. Constructor injection trong framework DI

Nếu ứng dụng dùng framework dependency injection, có thể đăng ký một clock bean và inject vào constructor:

~~~java
// Minh họa cấu trúc constructor; không phụ thuộc framework cụ thể.
public final class AuditService {
    private final Clock clock;

    public AuditService(Clock clock) {
        this.clock = Objects.requireNonNull(clock);
    }

    public Instant recordedAt() {
        return Instant.now(clock);
    }
}
~~~

Framework có thể tạo `Clock.systemUTC()` trong cấu hình production và một clock fixed trong cấu hình test. Nếu không dùng framework, việc tạo thủ công tại `main` hoặc factory của ứng dụng vẫn là dependency injection.

## 8. Clock cho LocalDate, LocalDateTime và ZonedDateTime

Không phải mọi bài toán thời gian đều cần `Instant`. Hãy chọn kiểu theo ý nghĩa dữ liệu:

| Kiểu | Ý nghĩa | Cách lấy từ clock |
|---|---|---|
| `Instant` | Thời điểm tuyệt đối trên UTC timeline. | `Instant.now(clock)` |
| `LocalDate` | Ngày trên lịch, không có giờ hay zone. | `LocalDate.now(clock)` |
| `LocalTime` | Giờ trên đồng hồ địa phương, không có ngày hay zone. | `LocalTime.now(clock)` |
| `LocalDateTime` | Ngày và giờ địa phương, không có offset/zone. | `LocalDateTime.now(clock)` |
| `OffsetDateTime` | Ngày giờ cùng UTC offset cụ thể. | `OffsetDateTime.now(clock)` |
| `ZonedDateTime` | Ngày giờ gắn với một `ZoneId`. | `ZonedDateTime.now(clock)` |

Ví dụ một báo cáo cần ngày địa phương:

~~~java
LocalDate reportDate = LocalDate.now(
        clock.withZone(ZoneId.of("Asia/Ho_Chi_Minh")));
~~~

Ví dụ một audit event cần timestamp:

~~~java
Instant eventTime = Instant.now(clock);
~~~

Không nên lưu `LocalDateTime` cho một sự kiện toàn cầu nếu không lưu zone hoặc offset đi kèm; một giờ địa phương có thể mơ hồ khi có thay đổi daylight saving time. Với sự kiện cần xác định chính xác thời điểm, `Instant` thường là lựa chọn dễ trao đổi giữa các hệ thống.

## 9. Kiểm thử các ranh giới thời gian

Truyền `Clock` cho phép test các tình huống mà trước đây phải chờ đồng hồ thật đi tới:

- Hạn sử dụng đúng tại thời điểm hiện tại.
- Một giây trước hoặc sau hạn.
- Ngày đầu tiên hoặc ngày cuối cùng của thời gian dùng thử.
- Đầu tháng, cuối tháng, ngày nhuận và giao thừa.
- Thời điểm sát nửa đêm theo múi giờ nghiệp vụ.
- Thay đổi offset do daylight saving time ở những zone có quy tắc này.

### 9.1. Kiểm tra ngày nhuận và ngày cuối tháng

Giả sử service xác định một báo cáo có thuộc tháng hiện tại hay không:

~~~java
public final class MonthlyReportService {
    private final Clock clock;

    public MonthlyReportService(Clock clock) {
        this.clock = Objects.requireNonNull(clock);
    }

    public boolean belongsToCurrentMonth(LocalDate date) {
        YearMonth currentMonth = YearMonth.now(clock);
        return YearMonth.from(date).equals(currentMonth);
    }
}
~~~

Test với ngày cố định:

~~~java
Clock februaryClock = Clock.fixed(
        Instant.parse("2024-02-29T12:00:00Z"),
        ZoneOffset.UTC);

MonthlyReportService service =
        new MonthlyReportService(februaryClock);

assertTrue(service.belongsToCurrentMonth(
        LocalDate.of(2024, 2, 1)));
assertFalse(service.belongsToCurrentMonth(
        LocalDate.of(2024, 3, 1)));
~~~

Năm 2024 là năm nhuận, vì vậy tháng Hai có ngày 29. Test không cần đợi đến tháng Hai hoặc chỉnh đồng hồ hệ điều hành.

### 9.2. Kiểm tra múi giờ ở ranh giới ngày

~~~java
Instant nearMidnightUtc =
        Instant.parse("2026-11-15T23:30:00Z");

Clock utc = Clock.fixed(nearMidnightUtc, ZoneOffset.UTC);
Clock vietnam = utc.withZone(
        ZoneId.of("Asia/Ho_Chi_Minh"));

assertEquals(LocalDate.of(2026, 11, 15), LocalDate.now(utc));
assertEquals(LocalDate.of(2026, 11, 16), LocalDate.now(vietnam));
~~~

Hai kết quả khác nhau là đúng vì cùng một thời điểm tuyệt đối được nhìn từ hai múi giờ khác nhau. Test này hữu ích cho hệ thống có báo cáo hoặc hạn nghiệp vụ theo khu vực.

## 10. Khi cần mô phỏng thời gian trôi qua

`Clock.fixed` không tiến về phía trước. Điều này rất tốt cho các test cần một thời điểm ổn định, nhưng có thể chưa đủ khi muốn kiểm tra nhiều bước theo thời gian trong cùng một test.

Một lựa chọn là dùng `Clock.offset` từ các fixed clock khác nhau cho từng giai đoạn:

~~~java
Instant start = Instant.parse("2026-11-15T10:00:00Z");
Clock startClock = Clock.fixed(start, ZoneOffset.UTC);
Clock afterTenMinutes = Clock.offset(
        startClock, Duration.ofMinutes(10));
~~~

Hoặc tạo hai instance service với hai clock fixed tương ứng để mô phỏng trước/sau một mốc. Cách này giữ test đơn giản và không cần một clock có trạng thái mutable.

### 10.1. Mutable Clock chỉ nên là test utility có chủ đích

Nếu nhiều bước của cùng một đối tượng cần quan sát thời gian thay đổi, có thể viết một implementation `Clock` nhỏ trong test. Ví dụ minh họa:

~~~java
import java.time.Clock;
import java.time.Duration;
import java.time.Instant;
import java.time.ZoneId;
import java.util.Objects;

final class AdjustableClock extends Clock {
    private Instant current;
    private final ZoneId zone;

    AdjustableClock(Instant initial, ZoneId zone) {
        this.current = Objects.requireNonNull(initial);
        this.zone = Objects.requireNonNull(zone);
    }

    @Override
    public ZoneId getZone() {
        return zone;
    }

    @Override
    public Clock withZone(ZoneId newZone) {
        return new AdjustableClock(current, newZone);
    }

    @Override
    public Instant instant() {
        return current;
    }

    void advance(Duration duration) {
        current = current.plus(duration);
    }
}
~~~

Test có thể điều khiển thời gian:

~~~java
AdjustableClock clock = new AdjustableClock(
        Instant.parse("2026-11-15T10:00:00Z"),
        ZoneOffset.UTC);

TrialService service = new TrialService(clock);
Instant expiresAt =
        Instant.parse("2026-11-15T10:05:00Z");

assertFalse(service.isExpired(expiresAt));

clock.advance(Duration.ofMinutes(5));

assertTrue(service.isExpired(expiresAt));
~~~

Đây là test utility đơn giản, không phải implementation production hoàn chỉnh. Nó không thread-safe và `withZone` trả về một clock mới với trạng thái thời gian tại thời điểm tạo; nếu test cần nhiều zone cùng chia sẻ một đồng hồ mutable, hãy thiết kế trạng thái dùng chung và đồng bộ rõ ràng. Trong phần lớn test, hai `Clock.fixed` hoặc `Clock.offset` là đủ.

## 11. Phân biệt thời gian lịch với thời gian đo khoảng

Một điểm quan trọng: `Clock` mô tả **thời gian hiện tại trên đồng hồ dân sự** (*wall-clock time*). Đồng hồ hệ thống có thể được đồng bộ lại, chỉnh thủ công hoặc thay đổi theo cơ chế của hệ điều hành. Vì vậy, `Clock` không phải nguồn thích hợp để đo chính xác thời gian trôi qua.

Nếu cần đo thời lượng thực thi, timeout hoặc benchmark, hãy dùng `System.nanoTime()`:

~~~java
long start = System.nanoTime();

performWork();

long elapsedNanos = System.nanoTime() - start;
Duration elapsed = Duration.ofNanos(elapsedNanos);
System.out.println("Elapsed: " + elapsed);
~~~

`System.nanoTime()` dùng đồng hồ đơn điệu (*monotonic time source*) cho phép đo khoảng thời gian. Giá trị trả về không phải timestamp có thể chuyển thành ngày giờ; chỉ nên lấy hiệu giữa hai lần đọc trong cùng một JVM.

| Mục tiêu | API phù hợp |
|---|---|
| Ghi nhận thời điểm tạo đơn hàng | `Instant.now(clock)` |
| Xác định ngày nghiệp vụ tại một zone | `LocalDate.now(clock.withZone(zone))` |
| Kiểm tra hạn sử dụng | `Instant.now(clock)` so với `expiresAt` |
| Đo thời gian chạy của một phương thức | `System.nanoTime()` |
| Tạo deadline/timeout theo đồng hồ đơn điệu | `System.nanoTime()` hoặc API timeout cấp cao được thiết kế phù hợp |
| Benchmark hiệu năng | Công cụ benchmark chuyên dụng; không dùng wall clock để tính duration ngắn |

Đừng lấy hai giá trị `Instant.now(clock)` rồi trừ nhau để benchmark hoặc tính timeout nhạy với điều chỉnh đồng hồ. Với thời gian đo, monotonic clock là lựa chọn đúng.

## 12. Những lỗi thiết kế thường gặp

| Cách làm | Vấn đề | Cách xử lý |
|---|---|---|
| Gọi `Instant.now()` rải rác trong service | Test khó điều khiển thời điểm; dependency thời gian bị ẩn. | Inject `Clock` qua constructor, gọi `Instant.now(clock)`. |
| Lưu `Instant.now(clock)` ở constructor rồi dùng mãi | Service luôn dùng thời điểm lúc khởi tạo. | Lưu `Clock`, đọc instant tại thời điểm nghiệp vụ cần. |
| Tạo `Clock.systemUTC()` trong từng phương thức | Khó thay nguồn thời gian trong test và cấu hình. | Tạo clock tại composition root rồi truyền vào. |
| Dùng `Clock.systemDefaultZone()` cho nghiệp vụ cần zone ổn định | Kết quả phụ thuộc cấu hình máy chủ. | Chỉ định `ZoneId` nghiệp vụ tường minh. |
| Cho rằng `Clock.fixed` tự tiến theo thời gian | Nó luôn trả về cùng một instant. | Dùng clock khác, `Clock.offset` hoặc test utility có thể điều chỉnh. |
| Dùng `Clock` để đo thời gian chạy | Wall clock có thể bị điều chỉnh. | Dùng `System.nanoTime()` cho elapsed time. |
| Nghĩ `Instant` chứa múi giờ | `Instant` chỉ biểu diễn thời điểm tuyệt đối. | Dùng `ZonedDateTime` hoặc chuyển đổi qua `ZoneId` khi hiển thị. |
| Truyền `LocalDateTime` giữa các hệ thống như một timestamp toàn cầu | Không có offset/zone, có thể mơ hồ. | Dùng `Instant` hoặc kiểu có offset/zone theo hợp đồng. |
| Cho phép clock null | Lỗi chỉ xuất hiện khi nghiệp vụ đọc thời gian. | Xác thực bằng `Objects.requireNonNull` ngay constructor. |
| Dùng một clock mutable không đồng bộ trong nhiều thread | Test hoặc logic có thể gặp trạng thái đua. | Ưu tiên clock immutable; nếu cần mutable, đồng bộ và giới hạn trong test. |

## 13. Ví dụ hoàn chỉnh: dịch vụ phát hành và kiểm tra hạn dùng thử

Ví dụ dưới đây kết hợp constructor injection, thời điểm tạo và quy tắc hết hạn. Hai lớp có thể đặt trong cùng file `TrialDemo.java` nếu chỉ một lớp là `public`:

~~~java
import java.time.Clock;
import java.time.Duration;
import java.time.Instant;
import java.util.Objects;

record Trial(Instant startedAt, Instant expiresAt) {
    Trial {
        Objects.requireNonNull(startedAt, "startedAt");
        Objects.requireNonNull(expiresAt, "expiresAt");
        if (expiresAt.isBefore(startedAt)) {
            throw new IllegalArgumentException(
                    "expiresAt must not be before startedAt");
        }
    }
}

final class TrialManager {
    private final Clock clock;
    private final Duration trialDuration;

    TrialManager(Clock clock, Duration trialDuration) {
        this.clock = Objects.requireNonNull(clock, "clock");
        this.trialDuration =
                Objects.requireNonNull(trialDuration, "trialDuration");
        if (trialDuration.isNegative()) {
            throw new IllegalArgumentException(
                    "trialDuration must not be negative");
        }
    }

    Trial startTrial() {
        Instant startedAt = Instant.now(clock);
        return new Trial(startedAt, startedAt.plus(trialDuration));
    }

    boolean isExpired(Trial trial) {
        Objects.requireNonNull(trial, "trial");
        return !Instant.now(clock).isBefore(trial.expiresAt());
    }
}

public final class TrialDemo {
    private TrialDemo() {
    }

    public static void main(String[] args) {
        Clock clock = Clock.systemUTC();
        TrialManager manager =
                new TrialManager(clock, Duration.ofDays(14));

        Trial trial = manager.startTrial();
        System.out.println("Started: " + trial.startedAt());
        System.out.println("Expires: " + trial.expiresAt());
        System.out.println("Expired: " + manager.isExpired(trial));
    }
}
~~~

Trong production, `Clock.systemUTC()` được truyền vào manager. Trong test, có thể truyền clock fixed và kiểm tra chính xác:

~~~java
Instant start = Instant.parse("2026-11-15T10:00:00Z");
Clock clock = Clock.fixed(start, ZoneOffset.UTC);

TrialManager manager =
        new TrialManager(clock, Duration.ofDays(14));

Trial trial = manager.startTrial();
assertEquals(start, trial.startedAt());
assertEquals(start.plus(Duration.ofDays(14)), trial.expiresAt());
~~~

Nếu cần kiểm tra manager sau 14 ngày, hãy tạo manager với một clock offset/fixed tương ứng hoặc dùng test clock có thể điều chỉnh như phần 10. Điều này làm cho thời gian trong test hoàn toàn xác định.

## 14. Bài tập thực hành

### Bài tập 1 — Chuyển từ gọi giờ trực tiếp sang Clock injection

Cho lớp:

~~~java
public final class InvoiceService {
    public Invoice create(String id) {
        return new Invoice(id, Instant.now());
    }
}
~~~

Hãy thêm trường `Clock`, constructor nhận clock, rồi thay lời gọi trực tiếp bằng `Instant.now(clock)`. Tạo một instance production bằng `Clock.systemUTC()`.

### Bài tập 2 — Kiểm tra hạn tại ranh giới

Viết test cho một phương thức `isExpired(Instant expiresAt)` với clock cố định. Cần ít nhất ba ca: hạn trong tương lai, hạn trong quá khứ và hạn bằng chính thời điểm hiện tại. Nêu rõ chính sách equality mà bạn chọn.

### Bài tập 3 — Mô phỏng ngày nghiệp vụ

Một cửa hàng chốt báo cáo lúc 00:00 theo `Asia/Ho_Chi_Minh`. Dùng `Clock.fixed` để kiểm thử một instant gần 17:00 UTC và xác định ngày nghiệp vụ tương ứng. So sánh kết quả với `LocalDate.now(Clock.systemUTC())`.

### Bài tập 4 — Phân biệt Clock và nanoTime

Viết đoạn đo thời lượng một tác vụ bằng `System.nanoTime()`. Giải thích vì sao không nên dùng `Instant.now(clock)` để đo benchmark hoặc timeout.

### Bài tập 5 — Test thời gian tiến lên

Dùng hai clock fixed hoặc `Clock.offset` để mô phỏng một thời điểm trước và sau hạn dùng thử. Viết hai test cho cùng service và xác nhận kết quả thay đổi theo clock được inject.

### Gợi ý tự đối chiếu

- Bài 1: Constructor lưu `Objects.requireNonNull(clock)` trong trường `private final`.
- Bài 2: Dùng `Clock.fixed(now, ZoneOffset.UTC)` và xác nhận kết quả đúng với quy tắc trước/đúng/sau hạn.
- Bài 3: Chuyển instant sang zone nghiệp vụ; không cộng cố định số giờ để thay thế `ZoneId`.
- Bài 4: `nanoTime` đo elapsed time; `Clock` cung cấp wall-clock time.
- Bài 5: `Clock.offset(fixed, Duration.ofDays(...))` có thể mô phỏng mốc tương lai mà không thay đổi hệ thống.

## 15. Nguyên tắc áp dụng trong dự án

- Đối tượng cần biết thời điểm hiện tại nên nhận `Clock` qua constructor.
- Chỉ tạo clock hệ thống ở nơi lắp ghép ứng dụng; truyền cùng nguồn thời gian cho các service cần dùng.
- Gọi `Instant.now(clock)`, `LocalDate.now(clock)` hoặc API tương ứng thay cho các lời gọi trực tiếp không thể điều khiển.
- Dùng `Clock.fixed` để kiểm thử xác định, `Clock.offset` để mô phỏng độ lệch; chỉ viết mutable clock khi test thực sự cần thời gian tiến trong cùng đối tượng.
- Chọn `ZoneId` theo nghiệp vụ. Dùng `Instant` cho thời điểm tuyệt đối, chuyển sang zone khi cần hiển thị hoặc tính ngày địa phương.
- Không dùng `Clock` để đo thời gian chạy hoặc timeout nhạy với điều chỉnh đồng hồ; dùng `System.nanoTime()`.
- Không giả định `Clock.systemDefaultZone()` giống nhau giữa các môi trường.
- Kiểm thử ranh giới: trước hạn, đúng hạn, sau hạn, đầu/cuối ngày và múi giờ.

Truyền nguồn thời gian vào đối tượng là một thay đổi nhỏ trong cấu trúc nhưng giúp logic ngày giờ dễ kiểm thử và dễ hiểu hơn. Với Java 17, `Clock` cung cấp sẵn abstraction cần thiết để ứng dụng dùng đồng hồ thật trong production và dùng thời điểm có thể kiểm soát trong test.

### Tài liệu tham khảo

- [Java SE 17 API — `Clock`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/Clock.html).
- [Java SE 17 API — `Instant`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/Instant.html).
- [Java SE 17 API — `LocalDate`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/LocalDate.html).
- [Java SE 17 API — `ZoneId`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/ZoneId.html).
- [Java SE 17 API — `System.nanoTime()`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/System.html#nanoTime()).
