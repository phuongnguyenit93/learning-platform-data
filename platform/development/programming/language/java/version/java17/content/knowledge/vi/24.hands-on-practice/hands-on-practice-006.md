# Truyền InstantSource để kiểm thử quy tắc hết hạn

> **Chủ đề:** Java 17  
> **Chương:** Thực hành tổng hợp  
> **Mục tiêu:** Tách việc lấy thời gian hiện tại khỏi logic nghiệp vụ, truyền `java.time.InstantSource` vào thành phần kiểm tra hạn sử dụng và viết test xác định cho các trường hợp trước, đúng tại và sau thời điểm hết hạn.

## 1. Vấn đề: quy tắc hết hạn phụ thuộc thời gian hiện tại

Ứng dụng thường phải quyết định một dữ liệu còn hiệu lực hay đã hết hạn:

- Access token còn dùng được không?
- Phiên đăng nhập đã hết hạn chưa?
- Coupon còn trong thời gian sử dụng không?
- Subscription còn hiệu lực không?
- Reservation có bị quá thời hạn xác nhận không?
- Link đặt lại mật khẩu còn hợp lệ không?

Một cách viết trực tiếp thường gặp:

```java
public boolean isExpired(Instant expiresAt) {
    return Instant.now().isAfter(expiresAt);
}
```

Code này đọc đồng hồ hệ thống ngay bên trong logic nghiệp vụ. Khi kiểm thử, kết quả phụ thuộc thời điểm test chạy. Test có thể chập chờn ở sát ranh giới hết hạn, và khó kiểm tra chính xác tình huống “đúng tại thời điểm hết hạn”.

Không nên giải quyết bằng cách gọi `Thread.sleep()` để chờ thời gian trôi qua. Cách đó làm test chậm, phụ thuộc scheduler của hệ điều hành và dễ flaky trên CI.

Giải pháp là truyền một nguồn cung cấp thời điểm hiện tại vào đối tượng thực hiện quy tắc. Trong Java 17, API phù hợp cho trường hợp chỉ cần lấy `Instant` là `InstantSource`.

## 2. InstantSource trong Java 17

### 2.1. InstantSource là gì?

`java.time.InstantSource` là interface được bổ sung trong Java 17. Nó biểu diễn một nguồn cung cấp thời điểm hiện tại dưới dạng `Instant`:

```java
package java.time;

public interface InstantSource {
    Instant instant();
    default long millis() { ... }

    static InstantSource system() { ... }
    static InstantSource fixed(Instant fixedInstant) { ... }
    static InstantSource offset(InstantSource baseSource, Duration offset) { ... }
    static InstantSource tick(InstantSource baseSource, Duration tickDuration) { ... }
}
```

Đoạn trên mô tả các thành phần chính của API, không phải source code triển khai. Phương thức `instant()` trả về thời điểm hiện tại mà source đại diện. `millis()` trả thời gian epoch milliseconds.

Một điểm quan trọng: `InstantSource` không gắn với múi giờ. Nó chỉ cung cấp một thời điểm trên trục thời gian. Điều này phù hợp với quy tắc hết hạn được lưu dưới dạng `Instant`, chẳng hạn thời điểm token không còn hiệu lực.

### 2.2. InstantSource và Clock

`java.time.Clock` đã có từ Java 8 và trong Java 17 nó triển khai `InstantSource`. Vì vậy, có thể truyền một `Clock` vào nơi nhận `InstantSource`:

```java
InstantSource source = Clock.systemUTC();
Instant now = source.instant();
```

Khác biệt về mục đích:

| API | Mục đích |
|---|---|
| `InstantSource` | Chỉ cần lấy thời điểm hiện tại dưới dạng `Instant` |
| `Clock` | Cung cấp thời điểm và múi giờ, phù hợp khi logic cần chuyển đổi sang ngày/giờ địa phương |

Nếu quy tắc chỉ so sánh hai `Instant`, dùng `InstantSource` giúp thể hiện dependency nhỏ nhất. Nếu logic cần `LocalDate.now(clock)`, giờ địa phương hoặc zone, có thể truyền `Clock` hoặc truyền `InstantSource` cùng `ZoneId` rõ ràng.

### 2.3. Các factory method hữu ích

Java 17 cung cấp các cách tạo nguồn thời gian:

| Factory | Ý nghĩa | Tình huống |
|---|---|---|
| `InstantSource.system()` | Nguồn thời gian hệ thống hiện tại | Production |
| `InstantSource.fixed(instant)` | Luôn trả về cùng một Instant | Test xác định |
| `InstantSource.offset(base, duration)` | Dịch thời gian của source gốc theo một Duration | Test mô phỏng tương lai/quá khứ |
| `InstantSource.tick(base, duration)` | Chỉ thay đổi theo các bước thời gian (tick) | Mô phỏng nguồn thời gian có độ phân giải theo bước |

Ví dụ:

```java
InstantSource productionTime = InstantSource.system();

Instant baseline = Instant.parse("2026-01-01T00:00:00Z");
InstantSource frozenTime = InstantSource.fixed(baseline);

InstantSource tomorrow = InstantSource.offset(
        frozenTime, Duration.ofDays(1));
```

`frozenTime.instant()` luôn trả về `baseline`. `tomorrow.instant()` trả về thời điểm sau baseline một ngày. Các source này giúp test mà không phải thay đổi đồng hồ hệ điều hành.

## 3. Xác định rõ quy tắc hết hạn

Trước khi viết code, cần thống nhất ý nghĩa của thời điểm `expiresAt`.

Một quy tắc thường dùng cho token/session là:

- Còn hiệu lực khi `now < expiresAt`.
- Hết hạn khi `now >= expiresAt`.

Nói cách khác, thời điểm hết hạn là **ranh giới loại trừ**: tại đúng thời điểm đó, dữ liệu đã hết hạn.

Sơ đồ:

```text
          còn hiệu lực                  hết hạn
-------------------------------|------------------------>
                               ^
                           expiresAt

now < expiresAt  => active
now = expiresAt  => expired
now > expiresAt  => expired
```

Trong Java, điều kiện này có thể viết bằng `isBefore`:

```java
boolean isExpired = !now.isBefore(expiresAt);
```

Đây là cách thể hiện rõ ràng quy tắc `now >= expiresAt`. Nếu nghiệp vụ định nghĩa khác, chẳng hạn coupon còn hiệu lực đến hết ngày địa phương, hãy biểu diễn chính sách đó riêng; không nên âm thầm đổi phép so sánh trong nhiều nơi.

## 4. Truyền InstantSource vào service

### 4.1. Tạo model có thời điểm hết hạn

Với token hoặc session, lưu thời điểm hết hạn dưới dạng `Instant`:

```java
import java.time.Instant;

public record AccessToken(String subject, Instant expiresAt) {
}
```

`Instant` biểu diễn một thời điểm tuyệt đối trên timeline UTC. Nó phù hợp để lưu hạn dùng, thời điểm phát hành và thời điểm hết hạn của token.

### 4.2. Viết service nhận InstantSource qua constructor

```java
import java.time.Instant;
import java.time.InstantSource;
import java.util.Objects;

public final class TokenExpirationPolicy {
    private final InstantSource timeSource;

    public TokenExpirationPolicy(InstantSource timeSource) {
        this.timeSource = Objects.requireNonNull(timeSource);
    }

    public boolean isExpired(AccessToken token) {
        Objects.requireNonNull(token);
        Instant now = timeSource.instant();
        return !now.isBefore(token.expiresAt());
    }
}
```

Thiết kế này có ba điểm đáng chú ý:

1. Service không tự gọi `Instant.now()`; nguồn thời gian là dependency được truyền từ bên ngoài.
2. Trong một lần đánh giá, service đọc thời gian đúng một lần vào biến `now`. Điều này tránh việc hai lần đọc đồng hồ trong cùng một phép tính cho ra hai thời điểm khác nhau.
3. Quy tắc hết hạn được biểu diễn rõ bằng `!now.isBefore(expiresAt)`, nghĩa là hết hạn khi `now >= expiresAt`.

### 4.3. Cấu hình production

Ở production, truyền source lấy thời gian hệ thống:

```java
InstantSource timeSource = InstantSource.system();
TokenExpirationPolicy policy =
        new TokenExpirationPolicy(timeSource);
```

Nếu ứng dụng dùng dependency injection framework, đăng ký source thành một dependency dùng chung:

```java
@Configuration
class TimeConfiguration {
    @Bean
    InstantSource instantSource() {
        return InstantSource.system();
    }
}
```

Sau đó inject `InstantSource` vào service qua constructor. Đoạn ví dụ dùng annotation theo phong cách Spring; nếu không dùng framework, chỉ cần tạo source ở composition root và truyền vào constructor như ví dụ đầu.

### 4.4. Không tạo source hệ thống bên trong từng lần gọi

Không nên viết:

```java
public boolean isExpired(AccessToken token) {
    InstantSource source = InstantSource.system();
    return !source.instant().isBefore(token.expiresAt());
}
```

Đoạn code trên vẫn tạo dependency thời gian bên trong method, khiến test khó kiểm soát và làm cấu hình nguồn thời gian phân tán. Hãy tạo source ở composition root rồi truyền vào service.

## 5. Kiểm thử với InstantSource.fixed

### 5.1. Vì sao fixed source hữu ích?

`InstantSource.fixed(instant)` luôn trả về cùng một thời điểm. Điều này cho phép viết test xác định:

- Test luôn chạy với cùng một giá trị `now`.
- Không phụ thuộc đồng hồ máy chạy test.
- Không cần chờ bằng `sleep`.
- Kiểm tra được chính xác ranh giới hết hạn.

Giả sử token hết hạn tại:

```java
Instant expiresAt = Instant.parse("2026-05-01T12:00:00Z");
```

Ta có thể tạo ba source:

```java
InstantSource beforeExpiry =
        InstantSource.fixed(expiresAt.minusSeconds(1));

InstantSource atExpiry =
        InstantSource.fixed(expiresAt);

InstantSource afterExpiry =
        InstantSource.fixed(expiresAt.plusSeconds(1));
```

Mỗi source mô phỏng một tình huống mà không phải thay đổi thời gian thực của máy.

### 5.2. Test ba trường hợp biên bằng JUnit 5

Ví dụ test:

```java
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.time.Instant;
import java.time.InstantSource;
import org.junit.jupiter.api.Test;

class TokenExpirationPolicyTest {
    private static final Instant EXPIRES_AT =
            Instant.parse("2026-05-01T12:00:00Z");

    @Test
    void tokenIsActiveBeforeExpiry() {
        var policy = new TokenExpirationPolicy(
                InstantSource.fixed(EXPIRES_AT.minusSeconds(1)));
        var token = new AccessToken("user-1", EXPIRES_AT);

        assertFalse(policy.isExpired(token));
    }

    @Test
    void tokenIsExpiredAtExactBoundary() {
        var policy = new TokenExpirationPolicy(
                InstantSource.fixed(EXPIRES_AT));
        var token = new AccessToken("user-1", EXPIRES_AT);

        assertTrue(policy.isExpired(token));
    }

    @Test
    void tokenIsExpiredAfterBoundary() {
        var policy = new TokenExpirationPolicy(
                InstantSource.fixed(EXPIRES_AT.plusSeconds(1)));
        var token = new AccessToken("user-1", EXPIRES_AT);

        assertTrue(policy.isExpired(token));
    }
}
```

Ba test này xác nhận chính sách tại ba điểm quan trọng:

| Thời điểm hiện tại | Kết quả `isExpired` |
|---|---|
| `expiresAt - 1 giây` | `false` |
| `expiresAt` | `true` |
| `expiresAt + 1 giây` | `true` |

Điểm test tại đúng ranh giới đặc biệt quan trọng. Nếu vô tình viết `now.isAfter(expiresAt)`, test thứ hai sẽ thất bại vì `isAfter` trả về `false` khi hai Instant bằng nhau.

### 5.3. Dùng một hằng thời điểm cho test

Nên khai báo một mốc thời gian dễ đọc, cố định bằng `Instant.parse`. Tránh gọi `Instant.now()` trong test rồi cộng/trừ thời gian vì điều đó làm test phụ thuộc đồng hồ và khó đọc khi so sánh.

Ví dụ:

```java
private static final Instant TEST_NOW =
        Instant.parse("2026-05-01T12:00:00Z");
```

Từ mốc này, tạo các thời điểm trước/sau bằng `minusSeconds`, `plusSeconds`, `minus` hoặc `plus`. Các phép tính trên `Instant` là bất biến và trả về instance mới.

## 6. Kiểm thử tiến trình thời gian với offset và mutable source

`InstantSource.fixed` rất phù hợp khi mỗi test chỉ cần một thời điểm. Nếu test cần mô phỏng thời gian trôi qua trong cùng một kịch bản, có thể dùng `InstantSource.offset` hoặc tự tạo implementation cho test.

### 6.1. Dùng InstantSource.offset

`offset` tạo source có thời điểm bằng source gốc cộng thêm một `Duration`:

```java
Instant base = Instant.parse("2026-05-01T12:00:00Z");
InstantSource baseSource = InstantSource.fixed(base);

InstantSource oneHourLater = InstantSource.offset(
        baseSource, Duration.ofHours(1));

InstantSource oneDayEarlier = InstantSource.offset(
        baseSource, Duration.ofDays(-1));
```

Vì source gốc là fixed, hai source offset cũng cho kết quả ổn định. Đây là cách ngắn gọn để kiểm thử các mốc tương lai/quá khứ mà không cần viết class fake.

### 6.2. Tạo MutableInstantSource cho test cần advance

Khi cần kiểm tra một service qua nhiều thời điểm, có thể tạo source mutable chỉ dùng trong test:

```java
import java.time.Duration;
import java.time.Instant;
import java.time.InstantSource;
import java.util.concurrent.atomic.AtomicReference;

final class MutableInstantSource implements InstantSource {
    private final AtomicReference<Instant> current;

    MutableInstantSource(Instant initialInstant) {
        this.current = new AtomicReference<>(initialInstant);
    }

    @Override
    public Instant instant() {
        return current.get();
    }

    void advanceBy(Duration duration) {
        current.updateAndGet(instant -> instant.plus(duration));
    }

    void set(Instant instant) {
        current.set(instant);
    }
}
```

`AtomicReference` giúp thao tác đọc/cập nhật mốc thời gian an toàn nếu test vô tình truy cập source từ nhiều thread. Trong test đơn luồng, một field `Instant` mutable cũng có thể đủ, nhưng source dùng chung giữa nhiều thread nên có semantics rõ ràng.

### 6.3. Test một token qua nhiều thời điểm

```java
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.time.Duration;
import java.time.Instant;
import org.junit.jupiter.api.Test;

class TokenExpirationProgressionTest {
    @Test
    void tokenExpiresAsTimeAdvances() {
        Instant start = Instant.parse("2026-05-01T12:00:00Z");
        Instant expiresAt = start.plus(Duration.ofMinutes(30));

        MutableInstantSource time = new MutableInstantSource(start);
        TokenExpirationPolicy policy = new TokenExpirationPolicy(time);
        AccessToken token = new AccessToken("user-1", expiresAt);

        assertFalse(policy.isExpired(token));

        time.advanceBy(Duration.ofMinutes(29));
        assertFalse(policy.isExpired(token));

        time.advanceBy(Duration.ofMinutes(1));
        assertTrue(policy.isExpired(token));
    }
}
```

Test này mô phỏng 29 phút rồi thêm 1 phút. Nó không chờ 30 phút ngoài đời; source chỉ thay đổi giá trị mà nó trả về.

### 6.4. Khi nào nên dùng fixed, offset hay mutable fake?

| Cách tạo source | Nên dùng khi |
|---|---|
| `InstantSource.fixed` | Test một quy tắc tại một mốc cụ thể |
| `InstantSource.offset` | Test một mốc được dịch tương đối từ source gốc |
| Mutable fake | Test một kịch bản nhiều bước cần chủ động advance/set thời gian |
| `InstantSource.system` | Ứng dụng thật cần thời gian hệ thống |

Đừng tạo mutable fake phức tạp nếu một fixed source đã đủ. Test càng ít state càng dễ đọc và ít lỗi.

## 7. InstantSource, Clock và múi giờ

### 7.1. Hạn token nên dùng Instant

Hạn dùng của token, lease hoặc session thường là một thời điểm tuyệt đối. Hãy lưu dưới dạng `Instant`:

```java
Instant issuedAt = timeSource.instant();
Instant expiresAt = issuedAt.plus(Duration.ofMinutes(15));
```

Khi kiểm tra, so sánh `Instant` với `Instant`. Không cần chuyển sang giờ địa phương và không phụ thuộc timezone mặc định của server.

### 7.2. Quy tắc hết hạn theo ngày địa phương cần ZoneId

Một số nghiệp vụ định nghĩa coupon dùng được đến hết ngày tại một khu vực cụ thể. Khi đó, cần có múi giờ rõ ràng, ví dụ:

```java
ZoneId businessZone = ZoneId.of("Asia/Ho_Chi_Minh");
LocalDate validThrough = LocalDate.of(2026, 5, 1);

Instant expiresAtExclusive = validThrough
        .plusDays(1)
        .atStartOfDay(businessZone)
        .toInstant();

boolean expired = !timeSource.instant().isBefore(expiresAtExclusive);
```

Ở đây, thời điểm hết hạn là đầu ngày tiếp theo theo timezone nghiệp vụ. Cách này tránh tự giả định một ngày luôn dài đúng 24 giờ; quy tắc timezone có thể có thay đổi do daylight saving ở những khu vực áp dụng.

### 7.3. Khi nào nên truyền Clock?

Nếu service cần nhiều phép toán ngày/giờ địa phương, truyền `Clock`:

```java
public final class DailyLimitPolicy {
    private final Clock clock;

    public DailyLimitPolicy(Clock clock) {
        this.clock = Objects.requireNonNull(clock);
    }

    public LocalDate currentBusinessDate() {
        return LocalDate.now(clock);
    }
}
```

Test có thể truyền `Clock.fixed(instant, zone)`. Vì `Clock` triển khai `InstantSource`, cùng một clock cũng có thể truyền cho service chỉ nhận `InstantSource`.

Nếu một service cần cả instant và zone, dùng `Clock` thường rõ ràng hơn. Nếu chỉ cần instant, đừng đưa dependency timezone vào chỉ vì API Clock đã quen thuộc.

## 8. Mở rộng quy tắc: thời gian còn lại

Ngoài việc kiểm tra đã hết hạn hay chưa, ứng dụng thường cần biết còn bao lâu trước khi hết hạn:

```java
import java.time.Duration;
import java.time.Instant;
import java.time.InstantSource;
import java.util.Objects;

public final class ExpirationPolicy {
    private final InstantSource timeSource;

    public ExpirationPolicy(InstantSource timeSource) {
        this.timeSource = Objects.requireNonNull(timeSource);
    }

    public boolean isExpired(Instant expiresAt) {
        Objects.requireNonNull(expiresAt);
        Instant now = timeSource.instant();
        return !now.isBefore(expiresAt);
    }

    public Duration remaining(Instant expiresAt) {
        Objects.requireNonNull(expiresAt);
        Duration remaining =
                Duration.between(timeSource.instant(), expiresAt);
        return remaining.isNegative() ? Duration.ZERO : remaining;
    }
}
```

Nếu thời điểm hiện tại sau hạn dùng, `Duration.between` trả duration âm; method chuẩn hóa kết quả thành `Duration.ZERO`. Tại đúng thời điểm hết hạn, kết quả cũng là zero.

Ví dụ test:

```java
@Test
void remainingTimeIsCalculatedFromInjectedSource() {
    Instant now = Instant.parse("2026-05-01T12:00:00Z");
    ExpirationPolicy policy =
            new ExpirationPolicy(InstantSource.fixed(now));

    Duration remaining = policy.remaining(now.plusSeconds(90));

    assertEquals(Duration.ofSeconds(90), remaining);
}

@Test
void remainingTimeNeverBecomesNegative() {
    Instant now = Instant.parse("2026-05-01T12:00:00Z");
    ExpirationPolicy policy =
            new ExpirationPolicy(InstantSource.fixed(now));

    Duration remaining = policy.remaining(now.minusSeconds(1));

    assertEquals(Duration.ZERO, remaining);
}
```

Nếu một nghiệp vụ cần nhiều kết quả nhất quán trong cùng một quyết định, hãy đọc `Instant` một lần rồi truyền giá trị `now` đó cho các phép tính tiếp theo. Tránh gọi source nhiều lần trong một phép tính phức tạp.

## 9. Quy tắc kiểm thử cho các trường hợp biên

### 9.1. Kiểm tra trước, đúng tại và sau ranh giới

Một bộ test tối thiểu cho expiration policy nên có:

| Trường hợp | Mốc source | Kết quả mong đợi |
|---|---|---|
| Còn xa hạn | `expiresAt - 1 ngày` | Chưa hết hạn |
| Sát trước hạn | `expiresAt - 1 nanosecond` | Chưa hết hạn |
| Đúng ranh giới | `expiresAt` | Hết hạn |
| Sát sau hạn | `expiresAt + 1 nanosecond` | Hết hạn |
| Đã quá hạn lâu | `expiresAt - 1 ngày` là `now` | Hết hạn |

`Instant` có độ phân giải nanosecond. Nếu hệ thống lưu timestamp ở database với độ chính xác mili giây hoặc micro giây, hãy thống nhất cách làm tròn/truncate tại ranh giới persistence và viết test theo đúng độ chính xác thực tế.

### 9.2. Dùng parameterized test khi có nhiều mốc

Với JUnit 5, có thể dùng `@ParameterizedTest` và `@MethodSource` để kiểm tra nhiều mốc mà không lặp code:

```java
import static org.junit.jupiter.api.Assertions.assertEquals;

import java.time.Instant;
import java.time.InstantSource;
import java.util.stream.Stream;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.MethodSource;
import org.junit.jupiter.params.provider.Arguments;

class ExpirationBoundaryTest {
    private static final Instant EXPIRES_AT =
            Instant.parse("2026-05-01T12:00:00Z");

    static Stream<Arguments> cases() {
        return Stream.of(
                Arguments.of(EXPIRES_AT.minusNanos(1), false),
                Arguments.of(EXPIRES_AT, true),
                Arguments.of(EXPIRES_AT.plusNanos(1), true));
    }

    @ParameterizedTest
    @MethodSource("cases")
    void appliesExclusiveExpiryBoundary(
            Instant now, boolean expectedExpired) {
        var policy = new TokenExpirationPolicy(
                InstantSource.fixed(now));
        var token = new AccessToken("user-1", EXPIRES_AT);

        assertEquals(expectedExpired, policy.isExpired(token));
    }
}
```

Parameterized test yêu cầu dependency JUnit Jupiter Params. Nếu dự án chỉ dùng JUnit Jupiter API/Engine mà chưa thêm module Params, hãy thêm dependency test tương ứng hoặc giữ các test riêng lẻ.

### 9.3. Không dùng sleep để test hết hạn

Tránh:

```java
Thread.sleep(1_000);
assertTrue(policy.isExpired(token));
```

Test trên có thể thất bại nếu scheduler chạy chậm, thời gian máy bị điều chỉnh hoặc test bị tải nặng. Dùng fixed/mutable source sẽ nhanh và xác định.

### 9.4. Không thay đổi đồng hồ hệ điều hành trong test

Không cần thay đổi system clock của máy/CI để test logic hết hạn. Việc thay đổi clock có thể ảnh hưởng các tiến trình khác, cần quyền quản trị và làm test khó cô lập. Truyền một source riêng cho đối tượng đang test là đủ.

## 10. Phân biệt thời điểm tuyệt đối và thời lượng trôi qua

`InstantSource` cung cấp thời điểm lịch (wall-clock instant). Đây là lựa chọn đúng cho quy tắc “token hết hạn lúc 12:00 UTC ngày X”, nhưng không phải công cụ đo thời lượng đơn điệu.

### 10.1. Đồng hồ hệ thống có thể được điều chỉnh

Đồng hồ hệ thống có thể được đồng bộ lại bởi NTP, thay đổi thủ công hoặc điều chỉnh bởi môi trường ảo hóa. Do đó, thời gian đọc ở hai thời điểm liên tiếp không phải lúc nào cũng tăng đúng theo thời gian thực đã trôi qua.

Với hạn sử dụng tuyệt đối đã lưu trong database, điều này thường chấp nhận được: ứng dụng cần so sánh với thời gian hiện tại theo đồng hồ hệ thống.

Với timeout hoặc đo elapsed time trong một tiến trình, nên dùng đồng hồ đơn điệu:

```java
long startedAt = System.nanoTime();

performOperation();

long elapsedNanos = System.nanoTime() - startedAt;
Duration elapsed = Duration.ofNanos(elapsedNanos);
```

`System.nanoTime()` được thiết kế để đo khoảng thời gian, không phải để biểu diễn ngày giờ. Không chuyển trực tiếp giá trị này thành `Instant`.

### 10.2. Chọn API theo bài toán

| Bài toán | Nguồn phù hợp |
|---|---|
| Token/session hết hạn tại một Instant | `InstantSource` |
| Coupon hết hạn theo ngày địa phương | `Clock` hoặc `InstantSource` kết hợp `ZoneId` |
| Đo thời gian một request chạy bao lâu | `System.nanoTime()` |
| Timeout trong một tiến trình | Đồng hồ đơn điệu, thường là `System.nanoTime()` |
| Lưu thời điểm tạo/cập nhật bản ghi | `InstantSource` và `Instant` |

Không nên dùng `InstantSource` cho mọi bài toán chỉ vì nó giúp test thời gian dễ hơn. Hãy chọn khái niệm thời gian đúng với nghiệp vụ.

## 11. Độ chính xác thời gian và đồng bộ giữa hệ thống

### 11.1. Độ chính xác của Instant

`Instant` có thể biểu diễn thời điểm với độ phân giải nanosecond. Tuy nhiên, điều đó không có nghĩa đồng hồ hệ điều hành luôn chính xác đến nanosecond. Độ phân giải thực tế phụ thuộc nền tảng và nguồn thời gian.

Nếu database lưu timestamp ở độ chính xác mili giây, thời điểm ghi ra và đọc lại có thể đã được làm tròn hoặc cắt bớt phần nano. Khi kiểm thử ranh giới:

- Xác định độ chính xác của cột database.
- Chuẩn hóa `expiresAt` theo cùng độ chính xác trước khi lưu hoặc so sánh nếu hợp đồng yêu cầu.
- Viết test cho trường hợp bằng nhau sau khi round-trip qua database.
- Không giả định một giá trị nanosecond sẽ được giữ nguyên bởi mọi hệ thống lưu trữ.

### 11.2. Không tin thời gian do client tự gửi

Với access token, session hoặc coupon, quyết định hết hạn thường phải dựa vào thời gian của server hoặc nguồn thời gian được tổ chức kiểm soát. Không để client gửi trường `now` rồi dùng trực tiếp để quyết định token còn hiệu lực.

Trong hệ thống nhiều node:

- Đồng bộ đồng hồ máy chủ bằng cơ chế vận hành phù hợp.
- Xác định node hoặc dịch vụ nào là nơi ra quyết định cuối cùng.
- Nếu giao thức có clock-skew allowance, định nghĩa rõ khoảng dung sai và áp dụng nhất quán.
- Không thêm dung sai tùy tiện vì có thể kéo dài thời gian hiệu lực ngoài mong muốn.

`InstantSource` giúp kiểm thử và thay thế dependency thời gian trong code; nó không tự đồng bộ clock giữa các máy.

### 11.3. Dùng cùng một thời điểm cho một quyết định

Khi quyết định có nhiều điều kiện phụ thuộc thời gian, lấy `now` một lần:

```java
Instant now = timeSource.instant();

boolean tokenExpired = !now.isBefore(token.expiresAt());
boolean refreshWindowOpen = !now.isBefore(token.refreshAvailableAt());
boolean sessionExpired = !now.isBefore(session.expiresAt());
```

Như vậy, mọi điều kiện trong quyết định sử dụng cùng một mốc thời gian. Nếu mỗi điều kiện tự gọi source, kết quả có thể khác nhau khi thời gian đi qua ranh giới trong lúc method chạy.

## 12. Những lỗi thường gặp khi truyền nguồn thời gian

| Lỗi/hiểu nhầm | Vì sao có vấn đề | Cách xử lý |
|---|---|---|
| Gọi `Instant.now()` bên trong domain service | Test phụ thuộc đồng hồ thật | Inject `InstantSource` qua constructor |
| Dùng `now.isAfter(expiresAt)` cho quy tắc `now >= expiresAt` | Bỏ sót trường hợp hai thời điểm bằng nhau | Dùng `!now.isBefore(expiresAt)` |
| Dùng `Thread.sleep()` trong test | Test chậm và không ổn định theo scheduler | Dùng `InstantSource.fixed` hoặc mutable test source |
| Nghĩ `InstantSource` có timezone | Interface chỉ cung cấp instant | Dùng `Clock` hoặc truyền `ZoneId` riêng cho quy tắc theo ngày địa phương |
| Dùng `InstantSource` để đo timeout | Wall clock có thể bị điều chỉnh | Dùng `System.nanoTime()` để đo elapsed time |
| Đọc source nhiều lần trong một quyết định | Có thể lấy các mốc khác nhau qua ranh giới hết hạn | Lấy `Instant now` một lần rồi dùng lại |
| Dùng mutable source chung cho production | Một thành phần có thể thay đổi thời gian của thành phần khác | Production dùng source hệ thống; mutable fake chỉ dùng trong test |
| Dùng `InstantSource.tick` cho kiểm tra ranh giới chính xác | Tick làm tròn thời điểm theo bước, có thể đổi kết quả sát hạn | Dùng fixed source hoặc system source không tick cho expiration |
| So sánh `LocalDateTime` với `Instant` bằng cách đổi ngầm timezone mặc định | Kết quả phụ thuộc cấu hình máy | Dùng `Instant` cho thời điểm tuyệt đối hoặc chỉ định `ZoneId` rõ ràng |
| Tin `now` do client gửi lên | Client có thể giả mạo đồng hồ | Quyết định bằng thời gian server được kiểm soát |
| Bỏ qua độ chính xác của database | Timestamp round-trip có thể mất phần nano | Chuẩn hóa và test theo precision của storage |
| Thêm clock-skew allowance không có hợp đồng | Có thể kéo dài hạn dùng | Định nghĩa rõ dung sai và áp dụng nhất quán |

## 13. Ví dụ tổng hợp: phát hành và kiểm tra token

Một service có thể dùng cùng một nguồn thời gian để tạo thời điểm phát hành, tính hạn dùng và kiểm tra hiệu lực:

```java
import java.time.Duration;
import java.time.Instant;
import java.time.InstantSource;
import java.util.Objects;

public final class AccessTokenService {
    private final InstantSource timeSource;
    private final Duration tokenLifetime;

    public AccessTokenService(
            InstantSource timeSource,
            Duration tokenLifetime) {
        this.timeSource = Objects.requireNonNull(timeSource);
        this.tokenLifetime = Objects.requireNonNull(tokenLifetime);
        if (tokenLifetime.isNegative() || tokenLifetime.isZero()) {
            throw new IllegalArgumentException(
                    "tokenLifetime must be positive");
        }
    }

    public AccessToken issue(String subject) {
        Instant issuedAt = timeSource.instant();
        Instant expiresAt = issuedAt.plus(tokenLifetime);
        return new AccessToken(subject, expiresAt);
    }

    public boolean isExpired(AccessToken token) {
        Instant now = timeSource.instant();
        return !now.isBefore(token.expiresAt());
    }
}
```

Test phát hành token với thời gian cố định:

```java
@Test
void issuedTokenUsesInjectedTimeAndConfiguredLifetime() {
    Instant now = Instant.parse("2026-05-01T12:00:00Z");
    var service = new AccessTokenService(
            InstantSource.fixed(now),
            Duration.ofMinutes(15));

    AccessToken token = service.issue("user-1");

    assertEquals("user-1", token.subject());
    assertEquals(now.plus(Duration.ofMinutes(15)), token.expiresAt());
}
```

Test này xác nhận cả hai hành vi: thời điểm phát hành lấy từ source được inject và hạn dùng được tính bằng lifetime cấu hình. Không cần giả lập đồng hồ toàn hệ thống.

Trong hệ thống thật, object token thường còn có ID, issuer, audience hoặc chữ ký. Ví dụ tập trung vào quy tắc thời gian; việc ký/xác thực token cần được xử lý theo giao thức bảo mật tương ứng.

## 14. Tổ chức dependency trong ứng dụng

### 14.1. Tạo source ở composition root

Một điểm khởi tạo ứng dụng nên quyết định nguồn thời gian:

```java
public final class Application {
    public static void main(String[] args) {
        InstantSource timeSource = InstantSource.system();

        TokenExpirationPolicy expirationPolicy =
                new TokenExpirationPolicy(timeSource);

        // Truyền expirationPolicy vào các thành phần cần dùng.
    }
}
```

Điều này làm rõ dependency và giúp thay thế source trong test hoặc môi trường đặc biệt.

### 14.2. Tránh static global clock có thể thay đổi

Không nên tạo một biến static mutable như `CurrentTime.source` rồi thay giá trị trong từng test. Nếu test chạy song song, test này có thể đổi clock của test khác. Constructor injection tạo ranh giới riêng cho từng instance và giảm coupling.

### 14.3. Không cần mock framework cho InstantSource

Vì `InstantSource` là interface nhỏ và có factory method sẵn, phần lớn test không cần Mockito hoặc mock framework:

- Dùng `InstantSource.fixed` cho một mốc cố định.
- Dùng `InstantSource.offset` cho mốc dịch tương đối.
- Dùng fake mutable nhỏ cho kịch bản nhiều bước.

Mock framework chỉ cần khi có yêu cầu tương tác phức tạp hoặc muốn verify số lần gọi. Với quy tắc hết hạn, kết quả thường quan trọng hơn việc verify method `instant()` được gọi bao nhiêu lần.

## 15. Bài tập thực hành

### Bài 1 — Tách Instant.now khỏi service

Cho service cũ:

```java
public boolean isCouponExpired(Instant expiresAt) {
    return Instant.now().isAfter(expiresAt);
}
```

Hãy sửa để:

1. Inject `InstantSource` qua constructor.
2. Đọc thời gian một lần trong method.
3. Xác định coupon hết hạn tại đúng `expiresAt`.
4. Viết test bằng `InstantSource.fixed` cho trước, đúng tại và sau hạn dùng.

### Bài 2 — Kiểm thử token hết hạn

Tạo record `AccessToken` và service kiểm tra hạn dùng. Viết ba test JUnit 5 với mốc cố định:

- `now = expiresAt - 1 second`.
- `now = expiresAt`.
- `now = expiresAt + 1 second`.

Giải thích vì sao dùng `isAfter` đơn lẻ không đáp ứng quy tắc hết hạn tại thời điểm bằng nhau.

### Bài 3 — Mô phỏng thời gian trôi qua

Tạo `MutableInstantSource` có phương thức `advanceBy(Duration)`. Viết test chứng minh token ban đầu còn hiệu lực, sau đó hết hạn khi source được advance tới đúng ranh giới.

Không dùng `Thread.sleep`.

### Bài 4 — Tính thời gian còn lại

Bổ sung method `remaining(Instant expiresAt)` trả `Duration`. Quy định kết quả không âm: nếu đã hết hạn, trả `Duration.ZERO`. Viết test cho trường hợp còn 90 giây và trường hợp đã hết hạn.

### Bài 5 — Coupon hết hạn theo ngày địa phương

Coupon có hiệu lực đến hết ngày 1/5/2026 tại `Asia/Ho_Chi_Minh`. Dùng `LocalDate`, `ZoneId` và `InstantSource` để tính thời điểm hết hạn loại trừ ở đầu ngày tiếp theo. Viết test trước và đúng tại thời điểm đó.

### Bài 6 — Phân biệt wall-clock và monotonic time

Một request cần timeout sau 2 giây. Giải thích vì sao `InstantSource` không phải công cụ tốt nhất để đo elapsed time. Viết đoạn code dùng `System.nanoTime()` để đo thời gian xử lý.

### Bài 7 — Thiết kế dependency

Một ứng dụng có ba service: token expiration, báo cáo theo ngày địa phương và đo timeout nội bộ. Chọn dependency thời gian phù hợp cho từng service và giải thích:

- `InstantSource`.
- `Clock`.
- `System.nanoTime()`.

## 16. Tài liệu chính thức của Java 17

- [Java SE 17 API — InstantSource](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/InstantSource.html): interface nguồn thời gian, factory method `system`, `fixed`, `offset`, `tick` và `instant`.
- [Java SE 17 API — Clock](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/Clock.html): clock có timezone và các factory method như `systemUTC`, `fixed`, `offset`.
- [Java SE 17 API — Instant](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/Instant.html): biểu diễn thời điểm trên timeline và các phép toán thời gian.
- [Java SE 17 API — Duration](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/Duration.html): biểu diễn khoảng thời gian và phép tính remaining duration.
- [Java SE 17 API — System.nanoTime](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/System.html#nanoTime()): đồng hồ đơn điệu dùng đo thời lượng trôi qua.
- [JUnit 5 User Guide](https://junit.org/junit5/docs/current/user-guide/): `@Test`, parameterized tests và `@MethodSource`.

**Ghi nhớ:** Để kiểm thử quy tắc hết hạn, hãy truyền `InstantSource` vào service thay vì gọi `Instant.now()` trực tiếp. Dùng `InstantSource.system()` trong production và `InstantSource.fixed()` trong test; dùng `offset` hoặc mutable fake khi cần mô phỏng thời gian trôi qua. Xác định rõ ranh giới hết hạn, thường là `now >= expiresAt`, và test cả trường hợp bằng nhau. `InstantSource` phù hợp với thời điểm tuyệt đối; dùng `Clock` khi cần timezone và `System.nanoTime()` khi đo timeout/elapsed time.
