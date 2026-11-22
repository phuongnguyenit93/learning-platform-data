# InstantSource và bài toán phụ thuộc giờ hệ thống trong Java 17

Nhiều chương trình cần biết thời điểm hiện tại: ghi dấu thời gian tạo đơn hàng, kiểm tra token hết hạn, xác định ngày làm việc hoặc tính thời lượng xử lý. Cách gọi trực tiếp `Instant.now()` hay `System.currentTimeMillis()` có vẻ đơn giản, nhưng nó khiến logic nghiệp vụ phụ thuộc vào đồng hồ thật của máy.

Khi kiểm thử, bạn khó tái tạo chính xác một thời điểm; khi hệ thống chạy ở nhiều múi giờ, cùng một instant có thể tương ứng với ngày địa phương khác nhau; khi đo thời gian trôi qua, đồng hồ hệ thống có thể bị điều chỉnh. Java 17 cung cấp `InstantSource` để tách **nguồn cung cấp thời điểm hiện tại** khỏi logic sử dụng thời gian.

Ý tưởng chính là: thay vì để lớp nghiệp vụ tự đọc giờ hệ thống, hãy truyền một nguồn thời gian vào lớp đó. Trong production, nguồn có thể là đồng hồ hệ thống; trong test, nguồn có thể cố định tại một instant đã biết.

## 1. Vấn đề khi phụ thuộc trực tiếp vào giờ hệ thống

Giả sử một dịch vụ kiểm tra đơn hàng đã hết hạn:

```java
import java.time.Instant;

public class OrderExpiryService {
    public boolean isExpired(Instant expiresAt) {
        return Instant.now().isAfter(expiresAt);
    }
}
```

Phương thức này đọc thời gian thật mỗi khi chạy. Điều đó gây một số khó khăn:

- **Kiểm thử khó xác định:** kết quả phụ thuộc thời điểm test thực thi. Một test có thể qua hôm nay nhưng thất bại khi chạy vào ngày khác.
- **Khó tái tạo lỗi:** nếu lỗi xảy ra đúng lúc chuyển ngày hoặc đúng thời điểm token hết hạn, không dễ dựng lại hoàn cảnh.
- **Phụ thuộc môi trường:** máy chạy có thể cấu hình sai đồng hồ, đồng bộ NTP trễ hoặc chạy ở múi giờ khác.
- **Khó mô phỏng tình huống biên:** không dễ kiểm tra chính xác thời điểm trước hạn, đúng hạn và sau hạn.

Một cách cải thiện là truyền một abstraction đại diện cho nguồn thời gian. Trong Java 17, abstraction nhỏ gọn cho mục đích lấy instant là `InstantSource`.

## 2. InstantSource là gì?

`java.time.InstantSource` là một interface đại diện cho **nguồn cung cấp instant hiện tại**. Nó được bổ sung trong Java 17. Một instant là một điểm trên dòng thời gian toàn cầu, được biểu diễn bởi `java.time.Instant`, không phụ thuộc múi giờ.

Các thành phần chính:

| API | Vai trò |
| --- | --- |
| `InstantSource.system()` | Tạo nguồn dựa trên đồng hồ hệ thống. |
| `InstantSource.fixed(Instant)` | Tạo nguồn luôn trả về một instant cố định. |
| `InstantSource.offset(InstantSource, Duration)` | Tạo nguồn trả về thời điểm lệch một khoảng so với nguồn khác. |
| `InstantSource.tick(InstantSource, Duration)` | Tạo nguồn làm tròn thời điểm theo nhịp thời gian được chỉ định. |
| `instant()` | Lấy instant hiện tại từ nguồn. |
| `millis()` | Lấy số mili giây từ epoch theo nguồn. |
| `withZone(ZoneId)` | Tạo một `Clock` dùng nguồn đó với múi giờ chỉ định. |

Ví dụ đơn giản:

```java
import java.time.Instant;
import java.time.InstantSource;

public class InstantSourceDemo {
    public static void main(String[] args) {
        InstantSource source = InstantSource.system();
        Instant now = source.instant();

        System.out.println(now);
    }
}
```

`InstantSource` chỉ tập trung vào việc cung cấp instant. Nó không mang theo múi giờ mặc định như `Clock`. Khi cần chuyển instant sang ngày hoặc giờ địa phương, hãy chỉ định `ZoneId` riêng.

## 3. Phân biệt InstantSource, Clock, Instant và System.currentTimeMillis

Các API này liên quan đến thời gian nhưng đại diện cho những khái niệm khác nhau:

| API | Bản chất | Dùng khi |
| --- | --- | --- |
| `Instant` | Một thời điểm cụ thể trên dòng thời gian | Lưu thời điểm tạo/cập nhật, thời điểm hết hạn, timestamp sự kiện. |
| `InstantSource` | Nguồn cung cấp instant | Tách việc đọc giờ hiện tại khỏi logic nghiệp vụ; dễ thay nguồn trong test. |
| `Clock` | Nguồn thời gian có cả instant và múi giờ | Cần cung cấp thời gian cho API như `LocalDate.now(clock)` hoặc `ZonedDateTime.now(clock)`. |
| `System.currentTimeMillis()` | Số mili giây từ epoch theo đồng hồ hệ thống | Tương tác với API yêu cầu epoch milliseconds hoặc hệ thống cũ. |
| `System.nanoTime()` | Bộ đếm thời gian đơn điệu dùng đo thời lượng | Đo elapsed time, timeout và benchmark tương đối. |

`Clock` là một lớp trừu tượng triển khai `InstantSource`. Do đó, một `Clock` có thể được dùng ở nơi cần `InstantSource`; chiều ngược lại, một `InstantSource` không nhất thiết có thông tin múi giờ cho tới khi gọi `withZone`.

### 3.1. Instant không phải giờ địa phương

`Instant` biểu diễn thời điểm toàn cầu, ví dụ:

```java
Instant eventTime = Instant.parse("2026-11-15T10:00:00Z");
```

Hậu tố `Z` biểu thị UTC. Nếu hiển thị cho người dùng tại một múi giờ, chuyển đổi sang `ZonedDateTime`:

```java
import java.time.Instant;
import java.time.ZoneId;
import java.time.ZonedDateTime;

Instant instant = Instant.parse("2026-11-15T10:00:00Z");
ZonedDateTime local = instant.atZone(ZoneId.of("Asia/Ho_Chi_Minh"));

System.out.println(local);
```

Múi giờ là quy tắc chuyển đổi giữa instant và giờ lịch địa phương. Nó có thể chứa quy tắc giờ mùa hè (*daylight saving time*), lịch sử thay đổi offset và các điều chỉnh do cơ quan có thẩm quyền ban hành.

Không nên lưu giờ địa phương không kèm múi giờ nếu dữ liệu cần xác định một thời điểm toàn cầu. Với sự kiện đã xảy ra, `Instant` thường là lựa chọn phù hợp; với lịch hẹn theo giờ địa phương, cần lưu thêm `ZoneId` hoặc một biểu diễn thời gian có múi giờ theo yêu cầu nghiệp vụ.

### 3.2. InstantSource không phải đồng hồ đơn điệu

`InstantSource.system()` lấy thời điểm theo đồng hồ hệ thống. Đồng hồ này có thể bị điều chỉnh bởi hệ điều hành, NTP hoặc cấu hình quản trị. Thời điểm đọc sau có thể nhảy tiến hoặc lùi so với thời điểm trước.

Vì vậy, `InstantSource` phù hợp để biết “bây giờ là thời điểm nào” theo đồng hồ lịch, nhưng không phải công cụ phù hợp để đo chính xác “đã trôi qua bao lâu”.

Để đo thời lượng, dùng `System.nanoTime()`:

```java
long start = System.nanoTime();

performWork();

long elapsedNanos = System.nanoTime() - start;
System.out.println("Elapsed ns: " + elapsedNanos);
```

`nanoTime` chỉ có ý nghĩa tương đối giữa các lần đọc trong cùng JVM; không dùng nó làm timestamp để lưu vào database hoặc gửi cho hệ thống khác. Để kiểm tra một thời điểm hết hạn trên lịch, dùng instant; để đo timeout hoặc thời lượng thực thi, dùng nguồn đơn điệu như `nanoTime`.

## 4. Tách phụ thuộc giờ hệ thống bằng dependency injection

Thay vì gọi `Instant.now()` trực tiếp trong logic nghiệp vụ, hãy nhận `InstantSource` qua constructor:

```java
import java.time.Instant;
import java.time.InstantSource;
import java.util.Objects;

public class OrderExpiryService {
    private final InstantSource timeSource;

    public OrderExpiryService(InstantSource timeSource) {
        this.timeSource = Objects.requireNonNull(timeSource, "timeSource");
    }

    public boolean isExpired(Instant expiresAt) {
        Instant now = timeSource.instant();
        return !now.isBefore(expiresAt);
    }
}
```

Lớp không cần biết nguồn là đồng hồ hệ thống hay đồng hồ giả lập. Nó chỉ yêu cầu một instant.

Trong production:

```java
OrderExpiryService service =
        new OrderExpiryService(InstantSource.system());
```

Trong test:

```java
Instant fixedNow = Instant.parse("2026-11-15T10:00:00Z");
OrderExpiryService service =
        new OrderExpiryService(InstantSource.fixed(fixedNow));
```

Hai môi trường dùng cùng logic nhưng khác nguồn thời gian. Đây là dependency injection đơn giản, không cần framework DI.

### 4.1. Vì sao constructor injection hữu ích?

- Phụ thuộc thời gian được thể hiện rõ trong constructor.
- Test có thể kiểm soát thời điểm mà không thay đổi đồng hồ máy.
- Lớp nghiệp vụ không cần gọi API hệ thống ở nhiều nơi.
- Có thể thay nguồn trong môi trường mô phỏng, demo hoặc kiểm thử tích hợp.
- Mã dễ đọc hơn vì người duy trì nhìn thấy rõ logic cần một nguồn thời gian.

Tránh tạo `InstantSource.system()` mới bên trong mỗi phương thức nghiệp vụ. Tạo nguồn ở composition root hoặc tầng cấu hình rồi truyền xuống các thành phần cần nó.

## 5. InstantSource.fixed: kiểm thử tại một thời điểm xác định

`InstantSource.fixed(instant)` tạo nguồn luôn trả về cùng một instant. Nó đặc biệt hữu ích khi kiểm tra điều kiện trước hạn, đúng hạn và sau hạn.

Ví dụ một dịch vụ kiểm tra thời hạn:

```java
import java.time.Instant;
import java.time.InstantSource;

public class ExpiryTestExample {
    public static void main(String[] args) {
        Instant expiry = Instant.parse("2026-11-15T12:00:00Z");

        OrderExpiryService before = new OrderExpiryService(
                InstantSource.fixed(
                        Instant.parse("2026-11-15T11:59:59Z")));

        OrderExpiryService exactly = new OrderExpiryService(
                InstantSource.fixed(expiry));

        OrderExpiryService after = new OrderExpiryService(
                InstantSource.fixed(
                        Instant.parse("2026-11-15T12:00:01Z")));

        System.out.println(before.isExpired(expiry));   // false
        System.out.println(exactly.isExpired(expiry));  // true
        System.out.println(after.isExpired(expiry));    // true
    }
}
```

Trong ví dụ này, quy tắc nghiệp vụ được định nghĩa là **hết hạn tại hoặc sau instant hết hạn**. Biểu thức `!now.isBefore(expiresAt)` thể hiện đúng ranh giới đó.

Nếu nghiệp vụ quy định chỉ hết hạn khi thời điểm hiện tại lớn hơn nghiêm ngặt thời điểm hết hạn, hãy dùng `now.isAfter(expiresAt)` và viết test riêng cho trường hợp bằng nhau. Quan trọng là xác định ranh giới trước khi viết điều kiện.

### 5.1. Kiểm tra các ranh giới thời gian

Với thời hạn `T`, nên mô tả rõ kết quả tại:

| Thời điểm | Điều kiện | Ví dụ theo quy tắc hết hạn tại hoặc sau T |
| --- | --- | --- |
| Trước T | `now < T` | Chưa hết hạn |
| Đúng T | `now = T` | Đã hết hạn |
| Sau T | `now > T` | Đã hết hạn |

Các test với fixed source không phụ thuộc tốc độ máy, lịch chạy test hoặc thời gian thực.

## 6. InstantSource.offset: mô phỏng thời gian lệch

`InstantSource.offset(base, duration)` tạo một nguồn trả về thời điểm lệch một khoảng so với nguồn gốc. Nó hữu ích khi muốn mô phỏng một hệ thống đang chạy nhanh hơn hoặc chậm hơn một khoảng xác định.

Ví dụ:

```java
import java.time.Duration;
import java.time.InstantSource;

InstantSource system = InstantSource.system();
InstantSource oneDayAhead =
        InstantSource.offset(system, Duration.ofDays(1));

System.out.println("System: " + system.instant());
System.out.println("Ahead:  " + oneDayAhead.instant());
```

Nguồn `oneDayAhead` trả instant bằng nguồn gốc cộng thêm một ngày. Đây là nguồn giả lập để thử các logic phụ thuộc ngày tháng; không thay đổi đồng hồ thật của máy.

Có thể tạo nguồn lệch về quá khứ bằng duration âm:

```java
InstantSource yesterday =
        InstantSource.offset(
                InstantSource.system(),
                Duration.ofDays(-1));
```

`offset` không phải cách sửa đồng hồ hệ thống. Nó chỉ tạo một view thời gian khác cho thành phần nhận nguồn đó.

## 7. InstantSource.tick: làm tròn theo nhịp thời gian

`InstantSource.tick(base, duration)` tạo nguồn có thời điểm được làm tròn xuống theo đơn vị tick được chỉ định. Điều này hữu ích khi không cần độ phân giải nhỏ hơn một khoảng nhất định, hoặc khi muốn mô phỏng nguồn thời gian cập nhật theo nhịp.

Ví dụ:

```java
import java.time.Duration;
import java.time.InstantSource;

InstantSource minuteClock =
        InstantSource.tick(
                InstantSource.system(),
                Duration.ofMinutes(1));

System.out.println(minuteClock.instant());
```

Thời điểm trả về được cắt xuống ranh giới phút tương ứng. Ví dụ một instant trong khoảng `10:42:00` đến trước `10:43:00` sẽ cho mốc phút `10:42:00`.

Lưu ý:

- Tick không làm thời gian chạy nhanh hoặc chậm; nó thay đổi độ phân giải của instant được quan sát.
- Hai lần đọc gần nhau có thể trả cùng một instant.
- Tick duration phải hợp lệ và dương theo quy tắc API.
- Không dùng tick để đo elapsed time hoặc timeout chính xác.

Nếu chỉ cần thời gian hệ thống bình thường, không cần bọc thêm tick. Dùng nó khi logic thực sự chấp nhận độ phân giải theo khoảng đã chọn.

## 8. Khi cần múi giờ: chuyển InstantSource thành Clock

`InstantSource` chỉ cung cấp instant. Nhiều API của `java.time` nhận `Clock` để lấy cả thời điểm hiện tại và múi giờ.

Phương thức `withZone(ZoneId)` tạo một `Clock` từ nguồn:

```java
import java.time.Clock;
import java.time.InstantSource;
import java.time.LocalDate;
import java.time.ZoneId;

InstantSource source = InstantSource.system();
Clock vietnamClock =
        source.withZone(ZoneId.of("Asia/Ho_Chi_Minh"));

LocalDate businessDate = LocalDate.now(vietnamClock);
System.out.println(businessDate);
```

Ở đây:

- `source.instant()` là instant toàn cầu.
- `vietnamClock` gắn instant với múi giờ `Asia/Ho_Chi_Minh`.
- `LocalDate.now(vietnamClock)` tính ngày lịch tại múi giờ đó.

Nếu nghiệp vụ theo múi giờ của một chi nhánh, người dùng hoặc thị trường, hãy chỉ định `ZoneId` rõ ràng. Tránh phụ thuộc vào `ZoneId.systemDefault()` nếu kết quả cần giống nhau giữa các máy.

### 8.1. Dùng Clock trực tiếp nếu cần cả instant và zone

Nếu nhiều API trong ứng dụng cần múi giờ, có thể inject `Clock`:

```java
import java.time.Clock;
import java.time.LocalDate;
import java.time.ZoneId;

public class BusinessDateService {
    private final Clock clock;

    public BusinessDateService(Clock clock) {
        this.clock = clock;
    }

    public LocalDate today() {
        return LocalDate.now(clock);
    }
}
```

Production:

```java
Clock productionClock =
        Clock.system(ZoneId.of("Asia/Ho_Chi_Minh"));
BusinessDateService service = new BusinessDateService(productionClock);
```

Test:

```java
Clock testClock = Clock.fixed(
        Instant.parse("2026-11-15T17:00:00Z"),
        ZoneId.of("Asia/Ho_Chi_Minh"));
```

`Clock` đã có các factory tương ứng như `system`, `fixed`, `offset` và `tick`. Hãy chọn `InstantSource` khi logic chỉ cần instant; chọn `Clock` khi logic cần cả zone hoặc API được sử dụng yêu cầu Clock.

## 9. Quyết định dùng InstantSource hay Clock

| Câu hỏi | Lựa chọn phù hợp |
| --- | --- |
| Chỉ cần lấy instant hiện tại để so sánh hạn? | `InstantSource` |
| Cần inject một nguồn thời gian nhỏ, không mang theo múi giờ? | `InstantSource` |
| Cần dùng `LocalDate.now(clock)` hoặc `ZonedDateTime.now(clock)`? | `Clock` |
| Nhiều thành phần cần cùng quy tắc múi giờ? | `Clock` |
| Đang dùng API legacy đã nhận `Clock`? | Tiếp tục truyền `Clock`; nó cũng là `InstantSource`. |
| Muốn test một ngày địa phương cố định? | `Clock.fixed(instant, zone)` |
| Muốn test một instant cố định nhưng không quan tâm zone? | `InstantSource.fixed(instant)` |

Đừng chuyển mọi thứ sang `InstantSource` chỉ vì API mới hơn. Chọn abstraction nhỏ nhất đáp ứng hợp đồng của lớp.

## 10. Bài toán phụ thuộc giờ hệ thống trong kiểm thử

### 10.1. Tránh gọi now() rải rác

Một lớp có thể gọi `Instant.now()` ở nhiều vị trí:

```java
if (Instant.now().isAfter(start)) {
    // ...
}

auditRepository.save(new AuditEvent(Instant.now()));
```

Hai lần gọi có thể nhận hai instant khác nhau, dù chỉ cách nhau rất ít. Điều đó đôi khi là mong muốn, nhưng nếu cùng một nghiệp vụ cần dùng một mốc thời gian nhất quán, hãy đọc một lần:

```java
Instant now = timeSource.instant();

if (now.isAfter(start)) {
    // ...
}

auditRepository.save(new AuditEvent(now));
```

Việc đọc một lần giúp tất cả quyết định trong thao tác dùng cùng một mốc. Nếu muốn timestamp của từng sự kiện khác nhau, hãy đọc tại ranh giới sự kiện có chủ đích.

### 10.2. Test logic hết hạn mà không chờ thời gian thật

Ví dụ kiểm tra quyền truy cập:

```java
import java.time.Instant;
import java.time.InstantSource;

public class AccessTokenPolicy {
    private final InstantSource timeSource;

    public AccessTokenPolicy(InstantSource timeSource) {
        this.timeSource = timeSource;
    }

    public boolean isValidUntil(Instant expiresAt) {
        return timeSource.instant().isBefore(expiresAt);
    }
}
```

Test có thể tạo nguồn cố định trước, đúng và sau thời hạn mà không cần sleep:

```java
Instant expiry = Instant.parse("2026-11-15T12:00:00Z");

AccessTokenPolicy before = new AccessTokenPolicy(
        InstantSource.fixed(expiry.minusSeconds(1)));
AccessTokenPolicy at = new AccessTokenPolicy(
        InstantSource.fixed(expiry));
AccessTokenPolicy after = new AccessTokenPolicy(
        InstantSource.fixed(expiry.plusSeconds(1)));

assert before.isValidUntil(expiry);
assert !at.isValidUntil(expiry);
assert !after.isValidUntil(expiry);
```

Ví dụ này định nghĩa token hợp lệ khi `now < expiresAt`. Nếu hợp đồng khác, hãy thay điều kiện và các assertion tương ứng.

### 10.3. Test thời gian trôi qua: fixed source chưa đủ

`InstantSource.fixed` luôn trả cùng một instant. Nó phù hợp để kiểm tra quy tắc dựa trên thời điểm, nhưng không thể tự mô phỏng thời gian tăng dần.

Nếu logic cần quan sát thời gian thay đổi qua từng lần gọi, có thể tạo một implementation test nhỏ:

```java
import java.time.Instant;
import java.time.InstantSource;
import java.util.Iterator;
import java.util.List;

final class SequenceInstantSource implements InstantSource {
    private final Iterator<Instant> instants;

    SequenceInstantSource(List<Instant> instants) {
        this.instants = instants.iterator();
    }

    @Override
    public Instant instant() {
        if (!instants.hasNext()) {
            throw new IllegalStateException("No test instant remaining");
        }
        return instants.next();
    }
}
```

Test có thể cung cấp chuỗi thời điểm đã định trước. Cách này hữu ích cho logic đọc thời gian nhiều lần; cần đảm bảo thứ tự đọc trong test khớp với hợp đồng mong muốn.

Nếu muốn mô phỏng đồng hồ có thể tiến/lùi chủ động, hãy xây dựng một test clock có trạng thái được kiểm soát hoặc dùng một abstraction thời gian của ứng dụng. Không thay đổi đồng hồ hệ điều hành trong test.

## 11. Giới hạn của giờ hệ thống và múi giờ

Tách nguồn thời gian giúp kiểm soát phụ thuộc, nhưng không tự giải quyết mọi vấn đề về thời gian.

### 11.1. Đồng hồ máy có thể sai hoặc bị điều chỉnh

Đồng hồ hệ thống có thể:

- Chạy nhanh hoặc chậm so với thời gian chuẩn.
- Bị đồng bộ lại qua NTP.
- Bị quản trị viên điều chỉnh.
- Bị ảnh hưởng bởi cấu hình máy ảo/container hoặc môi trường cloud.

`InstantSource.system()` phản ánh đồng hồ hệ thống mà JVM nhìn thấy. Nó không đảm bảo thời gian chính xác tuyệt đối. Nếu nghiệp vụ cần độ tin cậy thời gian cao, cần xem xét đồng bộ đồng hồ, nguồn thời gian hạ tầng, giám sát độ lệch và quy trình xử lý sai lệch.

### 11.2. Múi giờ mặc định không phải quy tắc nghiệp vụ

`ZoneId.systemDefault()` trả múi giờ mặc định của JVM/môi trường. Nó có thể khác giữa máy developer, CI, container và production.

Nếu tính ngày chốt sổ tại Việt Nam, hãy dùng `ZoneId.of("Asia/Ho_Chi_Minh")` thay vì dựa vào zone mặc định. Nếu mỗi tài khoản có múi giờ riêng, lưu và sử dụng `ZoneId` của tài khoản theo hợp đồng dữ liệu.

### 11.3. DST và giờ địa phương không tồn tại hoặc bị lặp

Ở những khu vực có daylight saving time, khi chuyển giờ:

- Có thể có một khoảng giờ địa phương không tồn tại khi đồng hồ nhảy tiến.
- Có thể có một khoảng giờ địa phương xuất hiện hai lần khi đồng hồ lùi.

Một `LocalDateTime` không chứa zone nên tự nó không xác định duy nhất instant trong những tình huống này. Với lịch hẹn, cần có `ZoneId` và quy tắc xử lý gap/overlap; với sự kiện đã xảy ra, lưu `Instant` thường rõ ràng hơn.

### 11.4. InstantSource không thay thế System.nanoTime

Không dùng:

```java
Instant start = source.instant();
performWork();
Duration elapsed = Duration.between(start, source.instant());
```

để đo timeout cần tính ổn định trước các thay đổi đồng hồ. Cách phù hợp cho đo thời lượng trong cùng JVM:

```java
long start = System.nanoTime();
performWork();
long elapsed = System.nanoTime() - start;
```

Sử dụng `InstantSource` cho thời điểm lịch; sử dụng `System.nanoTime` cho thời gian trôi qua.

## 12. Thiết kế lớp nghiệp vụ với nguồn thời gian

Một quy ước hữu ích là truyền nguồn thời gian ở constructor của các thành phần cần biết “bây giờ”. Ví dụ:

```java
import java.time.Duration;
import java.time.Instant;
import java.time.InstantSource;
import java.util.Objects;

public class SessionService {
    private final InstantSource timeSource;
    private final Duration sessionLifetime;

    public SessionService(
            InstantSource timeSource,
            Duration sessionLifetime) {
        this.timeSource = Objects.requireNonNull(timeSource);
        this.sessionLifetime = Objects.requireNonNull(sessionLifetime);

        if (sessionLifetime.isNegative() || sessionLifetime.isZero()) {
            throw new IllegalArgumentException(
                    "sessionLifetime must be positive");
        }
    }

    public Instant calculateExpiry() {
        return timeSource.instant().plus(sessionLifetime);
    }

    public boolean isExpired(Instant expiresAt) {
        return !timeSource.instant().isBefore(expiresAt);
    }
}
```

Ở composition root:

```java
SessionService sessionService =
        new SessionService(
                InstantSource.system(),
                Duration.ofMinutes(30));
```

Trong test:

```java
InstantSource fixed =
        InstantSource.fixed(Instant.parse("2026-11-15T10:00:00Z"));

SessionService sessionService =
        new SessionService(fixed, Duration.ofMinutes(30));

System.out.println(sessionService.calculateExpiry());
```

Nếu cùng một thao tác gọi `calculateExpiry()` nhiều lần với nguồn hệ thống, mỗi lần sẽ có mốc mới. Nếu cần một mốc nhất quán cho toàn bộ giao dịch, hãy lấy `Instant now` một lần ở ranh giới use case rồi truyền nó xuống các phép tính.

## 13. Những lỗi thiết kế thường gặp

**Gọi `Instant.now()` trực tiếp trong mọi lớp nghiệp vụ.**  
Làm logic khó kiểm thử và phụ thuộc đồng hồ thật. Truyền `InstantSource` hoặc `Clock` vào lớp cần thời gian.

**Dùng `InstantSource` như một đồng hồ có múi giờ.**  
`InstantSource` chỉ cung cấp instant. Dùng `withZone` để lấy `Clock` hoặc inject `Clock` ngay từ đầu nếu cần zone.

**Dùng `LocalDateTime.now()` để lưu thời điểm sự kiện toàn cầu.**  
`LocalDateTime` không chứa zone/offset nên không xác định duy nhất instant. Dùng `Instant` hoặc `OffsetDateTime`/`ZonedDateTime` theo yêu cầu.

**Dùng `InstantSource.system()` để đo elapsed time.**  
Đồng hồ hệ thống có thể bị điều chỉnh. Dùng `System.nanoTime()` để đo thời lượng.

**Dựa vào `ZoneId.systemDefault()` cho ngày nghiệp vụ.**  
Kết quả có thể khác giữa môi trường. Chỉ định zone theo nghiệp vụ.

**Dùng fixed source rồi mong thời gian tự tăng.**  
`InstantSource.fixed` luôn trả một instant. Dùng offset/tick hoặc implementation test có trạng thái nếu cần mô phỏng thời gian tiến.

**Đọc thời gian nhiều lần trong cùng một quyết định nghiệp vụ.**  
Các lần đọc có thể khác nhau. Nếu cần cùng mốc, lấy instant một lần và truyền cho các phép tính.

**Cho rằng InstantSource đảm bảo đồng hồ chính xác tuyệt đối.**  
Nó chỉ trừu tượng hóa nguồn thời gian; chất lượng đồng hồ vẫn phụ thuộc môi trường hệ thống.

## 14. Câu hỏi tự kiểm tra

**1. `InstantSource` được dùng để làm gì?**  
Đại diện nguồn cung cấp instant hiện tại, giúp tách việc lấy giờ khỏi logic nghiệp vụ.

**2. `InstantSource` được bổ sung từ phiên bản Java nào?**  
Java 17.

**3. Khác biệt chính giữa `InstantSource` và `Clock` là gì?**  
`InstantSource` cung cấp instant; `Clock` cũng là nguồn instant nhưng có thêm múi giờ và hỗ trợ trực tiếp các API lịch cần Clock.

**4. Vì sao inject `InstantSource` giúp test dễ hơn?**  
Test có thể dùng `InstantSource.fixed` để kiểm soát thời điểm, không phụ thuộc đồng hồ thật.

**5. `InstantSource.offset` dùng để làm gì?**  
Tạo nguồn thời gian lệch một khoảng so với nguồn gốc, hữu ích để mô phỏng thời gian.

**6. `InstantSource.tick` có làm thời gian chạy nhanh hơn không?**  
Không. Nó làm tròn thời điểm trả về theo nhịp được chọn.

**7. Khi nào nên dùng `Clock` thay vì `InstantSource`?**  
Khi cần múi giờ hoặc dùng API như `LocalDate.now(clock)`.

**8. Có nên dùng `InstantSource.system()` để đo thời lượng một tác vụ?**  
Không. Dùng `System.nanoTime()` để đo elapsed time.

**9. `InstantSource.fixed` có tự tăng theo thời gian không?**  
Không. Nó luôn trả cùng instant.

**10. Làm sao tính ngày nghiệp vụ nhất quán giữa các máy?**  
Dùng `Clock` với `ZoneId` được xác định theo quy tắc nghiệp vụ, không dựa vào múi giờ mặc định của máy.

## Tài liệu tham khảo chính thức

- [Java SE 17 API — `java.time.InstantSource`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/InstantSource.html): nguồn instant, các factory `system`, `fixed`, `offset`, `tick` và `withZone`.
- [Java SE 17 API — `java.time.Clock`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/Clock.html): đồng hồ có múi giờ và các factory tương ứng.
- [Java SE 17 API — `java.time.Instant`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/Instant.html): biểu diễn instant trên dòng thời gian.
- [Java SE 17 API — `java.time.ZoneId`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/ZoneId.html): định danh và quy tắc múi giờ.
- [Java SE 17 API — `System.nanoTime()`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/System.html#nanoTime()): đo thời gian trôi qua tương đối.
