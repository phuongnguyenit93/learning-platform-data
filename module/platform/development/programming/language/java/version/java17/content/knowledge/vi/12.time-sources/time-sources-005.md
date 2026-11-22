# Kiểm thử thời điểm hết hạn bằng nguồn fixed trong Java 17

Các chức năng có thời hạn thường phải trả lời câu hỏi: **tại thời điểm kiểm tra, dữ liệu còn hiệu lực hay đã hết hạn?** Ví dụ: mã xác thực chỉ dùng được trong 5 phút, liên kết đặt lại mật khẩu có hiệu lực trong 30 phút, vé chỉ được sử dụng trước giờ khởi hành hoặc gói thuê bao hết hạn vào một thời điểm xác định.

Nếu code gọi trực tiếp `Instant.now()` hoặc `LocalDateTime.now()` ở nhiều nơi, kết quả kiểm thử sẽ phụ thuộc vào đồng hồ thật của máy. Một bài test có thể chạy qua ở lần này nhưng thất bại ở lần khác khi thời gian thực đã vượt qua mốc hết hạn. Dùng `Thread.sleep()` để chờ thời gian trôi qua làm test chậm và dễ thiếu ổn định.

Java cung cấp `java.time.Clock` để tách **nguồn cung cấp thời gian** khỏi logic nghiệp vụ. Trong kiểm thử, `Clock.fixed()` tạo một đồng hồ luôn trả về cùng một thời điểm. Nhờ đó, có thể kiểm tra chính xác trạng thái **trước hạn, đúng thời điểm hết hạn và sau hạn** mà không cần chờ đồng hồ hệ thống.

## 1. Vì sao cần cố định nguồn thời gian khi kiểm thử?

Giả sử một mã xác thực có thời điểm hết hạn là `expiresAt`. Logic đơn giản có thể viết:

```java
boolean isExpired(Instant expiresAt) {
    return Instant.now().isAfter(expiresAt);
}
```

Đoạn code này có hai vấn đề:

1. Hàm tự lấy thời gian từ đồng hồ hệ thống, nên bài test khó quyết định chính xác giá trị “hiện tại”.
2. `isAfter()` chỉ trả `true` khi thời điểm hiện tại **sau hẳn** `expiresAt`. Nếu quy tắc nghiệp vụ xem mã hết hạn ngay tại thời điểm bằng `expiresAt`, điều kiện trên chưa đúng ở ranh giới bằng nhau.

Ví dụ, nếu mã hết hạn lúc `10:00:00`, ứng dụng cần xác định rõ:

| Thời điểm kiểm tra | Trạng thái theo quy tắc “hết hạn khi now >= expiresAt” |
| --- | --- |
| 09:59:59 | Còn hiệu lực |
| 10:00:00 | Đã hết hạn |
| 10:00:01 | Đã hết hạn |

Một bài test dùng thời gian thực khó tái tạo ba tình huống này một cách chính xác. `Clock.fixed()` cho phép chủ động đặt thời điểm kiểm tra để kiểm chứng từng trường hợp.

## 2. `Clock` là gì?

`Clock` là một abstraction trong package `java.time`, đại diện cho nguồn thời gian và múi giờ. Thay vì buộc code nghiệp vụ gọi đồng hồ hệ thống, ta truyền một `Clock` vào nơi cần đọc thời gian.

Một số factory method thường dùng:

| API | Ý nghĩa |
| --- | --- |
| `Clock.systemUTC()` | Đồng hồ hệ thống với zone UTC. |
| `Clock.system(ZoneId)` | Đồng hồ hệ thống theo zone được chỉ định. |
| `Clock.fixed(Instant, ZoneId)` | Đồng hồ luôn trả về một instant cố định. |
| `Clock.offset(Clock, Duration)` | Đồng hồ trả về thời gian của clock gốc cộng thêm một khoảng duration. |
| `Clock.tick(Clock, Duration)` | Đồng hồ làm tròn thời gian theo đơn vị tick được chỉ định. |

Đối với kiểm thử hết hạn, factory method quan trọng nhất là:

```java
Clock fixedClock = Clock.fixed(
        Instant.parse("2026-11-15T10:00:00Z"),
        ZoneOffset.UTC
);
```

Mỗi lần gọi `fixedClock.instant()` đều nhận cùng một thời điểm:

```java
System.out.println(fixedClock.instant());
System.out.println(fixedClock.instant());
```

Kết quả:

```text
2026-11-15T10:00:00Z
2026-11-15T10:00:00Z
```

`Clock.fixed()` không tạo một đồng hồ đếm ngược. Nó cố định thời gian để code có thể được kiểm tra với một mốc xác định. Muốn thử một thời điểm khác, tạo một fixed clock khác với instant khác.

## 3. Thiết kế logic hết hạn để nhận `Clock` từ bên ngoài

Một nguyên tắc quan trọng là **đưa nguồn thời gian vào dependency của lớp**, thay vì tự gọi `Instant.now()` ở bên trong logic nghiệp vụ.

Ví dụ, tạo lớp `AccessPolicy`:

```java
import java.time.Clock;
import java.time.Instant;
import java.util.Objects;

public final class AccessPolicy {

    private final Clock clock;

    public AccessPolicy(Clock clock) {
        this.clock = Objects.requireNonNull(clock, "clock");
    }

    public boolean isExpired(Instant expiresAt) {
        Objects.requireNonNull(expiresAt, "expiresAt");

        Instant now = clock.instant();

        // Hết hạn tại hoặc sau thời điểm expiresAt.
        return !now.isBefore(expiresAt);
    }
}
```

Phương thức `isExpired()` lấy thời điểm hiện tại từ `clock.instant()`. Trong code chạy thật, clock có thể là `Clock.systemUTC()`; trong test, clock có thể là `Clock.fixed(...)`.

### Vì sao dùng `!now.isBefore(expiresAt)`?

Quy tắc được chọn trong ví dụ là:

```java
expired = now >= expiresAt
```

`Instant` có các phương thức so sánh:

- `now.isBefore(expiresAt)`: hiện tại trước thời điểm hết hạn.
- `now.isAfter(expiresAt)`: hiện tại sau thời điểm hết hạn.
- `now.equals(expiresAt)`: hai instant bằng nhau.

Do đó, biểu thức `!now.isBefore(expiresAt)` có nghĩa là **hiện tại bằng hoặc sau thời điểm hết hạn**.

Có thể viết tương đương:

```java
return now.equals(expiresAt) || now.isAfter(expiresAt);
```

Nhưng cách phủ định `isBefore()` ngắn hơn và thể hiện trực tiếp quy tắc bao gồm cả thời điểm bằng nhau.

Nếu nghiệp vụ yêu cầu chỉ hết hạn **sau** thời điểm mốc, không bao gồm trường hợp bằng nhau, có thể dùng `now.isAfter(expiresAt)`. Hãy xác định rõ hợp đồng nghiệp vụ trước khi viết điều kiện.

## 4. Dùng `Clock.fixed()` kiểm thử trước, đúng và sau thời điểm hết hạn

Tạo một test đơn giản bằng Java để thấy cách kiểm tra ba trường hợp.

```java
import java.time.Clock;
import java.time.Instant;
import java.time.ZoneOffset;

public class ExpirationDemo {

    public static void main(String[] args) {
        Instant expiresAt = Instant.parse("2026-11-15T10:00:00Z");

        Clock beforeClock = Clock.fixed(
                Instant.parse("2026-11-15T09:59:59Z"),
                ZoneOffset.UTC
        );

        Clock exactClock = Clock.fixed(
                Instant.parse("2026-11-15T10:00:00Z"),
                ZoneOffset.UTC
        );

        Clock afterClock = Clock.fixed(
                Instant.parse("2026-11-15T10:00:01Z"),
                ZoneOffset.UTC
        );

        System.out.println(
                new AccessPolicy(beforeClock).isExpired(expiresAt)
        );

        System.out.println(
                new AccessPolicy(exactClock).isExpired(expiresAt)
        );

        System.out.println(
                new AccessPolicy(afterClock).isExpired(expiresAt)
        );
    }
}

final class AccessPolicy {

    private final Clock clock;

    AccessPolicy(Clock clock) {
        this.clock = clock;
    }

    boolean isExpired(Instant expiresAt) {
        return !clock.instant().isBefore(expiresAt);
    }
}
```

Kết quả:

```text
false
true
true
```

Bảng diễn giải:

| Fixed clock | So sánh | Kết quả `isExpired` |
| --- | --- | --- |
| 09:59:59Z | `now < expiresAt` | `false` |
| 10:00:00Z | `now = expiresAt` | `true` |
| 10:00:01Z | `now > expiresAt` | `true` |

Ba bài kiểm tra không phải chờ một giây nào. Mỗi lần tạo policy, ta truyền một clock đã cố định ở thời điểm cần thử.

Trong dự án thật, `AccessPolicy` nên được định nghĩa một lần trong file riêng; đoạn trên gom lớp và demo vào cùng một file để người học có thể chạy độc lập.

## 5. Viết unit test bằng JUnit 5

Khi dự án dùng JUnit 5, có thể viết test thể hiện rõ từng trường hợp biên.

Ví dụ lớp nghiệp vụ:

```java
import java.time.Clock;
import java.time.Instant;
import java.util.Objects;

public final class AccessPolicy {

    private final Clock clock;

    public AccessPolicy(Clock clock) {
        this.clock = Objects.requireNonNull(clock);
    }

    public boolean isExpired(Instant expiresAt) {
        Objects.requireNonNull(expiresAt);

        return !clock.instant().isBefore(expiresAt);
    }
}
```

Tệp test `AccessPolicyTest.java`:

```java
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.time.Clock;
import java.time.Instant;
import java.time.ZoneOffset;

import org.junit.jupiter.api.Test;

class AccessPolicyTest {

    private static final Instant EXPIRES_AT =
            Instant.parse("2026-11-15T10:00:00Z");

    @Test
    void shouldNotBeExpiredOneSecondBeforeDeadline() {
        Clock clock = Clock.fixed(
                Instant.parse("2026-11-15T09:59:59Z"),
                ZoneOffset.UTC
        );

        AccessPolicy policy = new AccessPolicy(clock);

        assertFalse(policy.isExpired(EXPIRES_AT));
    }

    @Test
    void shouldBeExpiredExactlyAtDeadline() {
        Clock clock = Clock.fixed(
                EXPIRES_AT,
                ZoneOffset.UTC
        );

        AccessPolicy policy = new AccessPolicy(clock);

        assertTrue(policy.isExpired(EXPIRES_AT));
    }

    @Test
    void shouldBeExpiredAfterDeadline() {
        Clock clock = Clock.fixed(
                Instant.parse("2026-11-15T10:00:01Z"),
                ZoneOffset.UTC
        );

        AccessPolicy policy = new AccessPolicy(clock);

        assertTrue(policy.isExpired(EXPIRES_AT));
    }
}
```

Các test có tên mô tả rõ thời điểm và kết quả mong đợi. Khi test thất bại, tên test cho biết ngay trường hợp nào của ranh giới thời gian cần xem lại.

JUnit 5 là thư viện test độc lập; `Clock.fixed()` thuộc JDK 17 và không cần thư viện test để hoạt động. Nếu dự án chưa dùng JUnit, có thể chạy demo với `main()` và kiểm tra kết quả như phần trước.

### Có thể dùng một helper để tạo fixed clock

Nếu nhiều test cần tạo clock, có thể viết helper:

```java
private static Clock fixedAt(String instant) {
    return Clock.fixed(
            Instant.parse(instant),
            ZoneOffset.UTC
    );
}
```

Sau đó:

```java
@Test
void shouldBeExpiredAtDeadline() {
    AccessPolicy policy = new AccessPolicy(
            fixedAt("2026-11-15T10:00:00Z")
    );

    assertTrue(policy.isExpired(EXPIRES_AT));
}
```

Helper chỉ nên được dùng nếu giúp test dễ đọc hơn. Đối với một hoặc hai test, viết trực tiếp `Clock.fixed()` cũng rõ ràng.

## 6. Kiểm thử thời điểm hết hạn được tính từ thời điểm tạo

Nhiều hệ thống không nhận sẵn `expiresAt` mà tính hạn từ lúc tạo token, phiên đăng nhập hoặc mã xác minh.

Ví dụ: token có thời hạn 15 phút. Nếu tạo lúc `issuedAt`, thời điểm hết hạn là:

```java
Instant expiresAt = issuedAt.plus(Duration.ofMinutes(15));
```

Để test, hãy cố định clock tại thời điểm tạo token và dùng cùng nguồn clock khi tính hạn.

```java
import java.time.Clock;
import java.time.Duration;
import java.time.Instant;
import java.util.Objects;

public final class TokenService {

    private final Clock clock;

    public TokenService(Clock clock) {
        this.clock = Objects.requireNonNull(clock);
    }

    public Token issue() {
        Instant issuedAt = clock.instant();
        Instant expiresAt = issuedAt.plus(Duration.ofMinutes(15));

        return new Token(issuedAt, expiresAt);
    }

    public boolean isExpired(Token token) {
        return !clock.instant().isBefore(token.expiresAt());
    }

    public record Token(Instant issuedAt, Instant expiresAt) {
    }
}
```

Một test với fixed clock:

```java
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.time.Clock;
import java.time.Duration;
import java.time.Instant;
import java.time.ZoneOffset;

import org.junit.jupiter.api.Test;

class TokenServiceTest {

    @Test
    void tokenExpiresAtFifteenMinuteBoundary() {
        Instant issuedAt = Instant.parse("2026-11-15T10:00:00Z");

        Clock atIssueTime = Clock.fixed(issuedAt, ZoneOffset.UTC);
        TokenService service = new TokenService(atIssueTime);

        TokenService.Token token = service.issue();

        assertFalse(service.isExpired(token));
        assertEquals(
                issuedAt.plus(Duration.ofMinutes(15)),
                token.expiresAt()
        );

        Clock atExpiry = Clock.fixed(
                token.expiresAt(),
                ZoneOffset.UTC
        );

        TokenService serviceAtExpiry = new TokenService(atExpiry);

        assertTrue(serviceAtExpiry.isExpired(token));
    }
}
```

Đoạn test cần thêm import `assertEquals` cùng các import khác:

```java
import static org.junit.jupiter.api.Assertions.assertEquals;
```

Ví dụ này minh họa hai nguồn clock cố định: clock ở lúc phát hành và clock tại ranh giới hết hạn. Vì `Clock.fixed` không tự tiến lên, cần tạo một clock khác để mô phỏng thời điểm sau đó.

Một lưu ý về cách tổ chức: nếu test chỉ cần kiểm tra phương thức `isExpired`, không nhất thiết phải test luôn việc phát hành token trong cùng một test. Tách test tính `expiresAt` và test ranh giới hết hạn sẽ giúp nguyên nhân lỗi rõ hơn.

## 7. Kiểm thử một thời điểm trong quá khứ hoặc tương lai

`Clock.fixed` có thể cố định bất kỳ instant hợp lệ nào, kể cả quá khứ hoặc tương lai so với đồng hồ thật của máy.

Ví dụ, kiểm tra một giấy phép đã hết hạn từ năm trước:

```java
Instant expiresAt = Instant.parse("2025-12-31T23:59:59Z");

Clock testClock = Clock.fixed(
        Instant.parse("2026-01-01T00:00:00Z"),
        ZoneOffset.UTC
);

AccessPolicy policy = new AccessPolicy(testClock);

System.out.println(policy.isExpired(expiresAt)); // true
```

Hoặc kiểm tra một giấy phép còn hạn trong tương lai xa:

```java
Instant expiresAt = Instant.parse("2030-01-01T00:00:00Z");

Clock testClock = Clock.fixed(
        Instant.parse("2026-01-01T00:00:00Z"),
        ZoneOffset.UTC
);

AccessPolicy policy = new AccessPolicy(testClock);

System.out.println(policy.isExpired(expiresAt)); // false
```

Điểm mạnh là bài test không phụ thuộc ngày chạy. Dù chạy hôm nay hay nhiều năm sau, clock vẫn trả về đúng instant đã chọn.

## 8. Kiểm thử thời hạn theo ngày và múi giờ

Không phải mọi thời hạn đều được lưu dưới dạng instant chính xác. Một số nghiệp vụ nói rằng “có hiệu lực đến hết ngày 15/11 tại múi giờ của cửa hàng”.

Đây là quy tắc theo **ngày lịch**, nên cần xác định zone trước khi chuyển thành instant.

Ví dụ, giấy phép có hiệu lực hết ngày `2026-11-15` tại múi giờ `Asia/Ho_Chi_Minh`. Ta có thể xem thời điểm kết thúc là đầu ngày kế tiếp theo múi giờ đó (cận trên không bao gồm):

```java
import java.time.Clock;
import java.time.Instant;
import java.time.LocalDate;
import java.time.ZoneId;

public class CalendarExpiry {

    static boolean isExpired(
            LocalDate validThrough,
            Clock clock
    ) {
        ZoneId zone = clock.getZone();

        Instant expiresAtExclusive = validThrough
                .plusDays(1)
                .atStartOfDay(zone)
                .toInstant();

        return !clock.instant().isBefore(expiresAtExclusive);
    }
}
```

Test với fixed clock:

```java
import java.time.Clock;
import java.time.Instant;
import java.time.LocalDate;
import java.time.ZoneId;

ZoneId zone = ZoneId.of("Asia/Ho_Chi_Minh");

Clock beforeEnd = Clock.fixed(
        Instant.parse("2026-11-15T16:59:59Z"),
        zone
);

Clock atNextDay = Clock.fixed(
        Instant.parse("2026-11-15T17:00:00Z"),
        zone
);

LocalDate validThrough = LocalDate.of(2026, 11, 15);

System.out.println(CalendarExpiry.isExpired(validThrough, beforeEnd));
System.out.println(CalendarExpiry.isExpired(validThrough, atNextDay));
```

Kết quả:

```text
false
true
```

Trong ví dụ này, `17:00Z` tương ứng `00:00` ngày 16/11 tại `Asia/Ho_Chi_Minh`. Giấy phép còn hiệu lực trong ngày 15/11 và hết hạn ngay khi bước sang ngày kế tiếp theo zone đó.

Dùng `atStartOfDay(zone)` để chuyển ngày lịch sang thời điểm bắt đầu ngày trong múi giờ đã chọn. Cách này xử lý quy tắc múi giờ tốt hơn việc tự cộng một số giờ cố định vào UTC, vì một số zone có quy tắc thay đổi theo lịch sử hoặc daylight saving time.

Nếu nghiệp vụ chỉ có một mốc thời gian tuyệt đối, hãy lưu và so sánh bằng `Instant`. Nếu nghiệp vụ dựa trên ngày địa phương, hãy giữ `LocalDate` cùng `ZoneId` và xác định rõ quy tắc chuyển đổi.

## 9. Phân biệt `Instant`, `LocalDateTime` và `Clock`

Ba kiểu này có vai trò khác nhau:

| Kiểu | Mô tả | Khi nào dùng |
| --- | --- | --- |
| `Instant` | Một thời điểm tuyệt đối trên timeline UTC. | Token, session, timestamp, thời điểm hết hạn chính xác. |
| `LocalDateTime` | Ngày và giờ địa phương nhưng không kèm zone/offset. | Lịch hẹn địa phương khi zone được quản lý riêng. |
| `Clock` | Nguồn cung cấp thời gian và zone. | Cho phép logic lấy thời gian hệ thống hoặc thời gian cố định khi test. |
| `LocalDate` | Một ngày lịch, không có giờ và zone. | Ngày hiệu lực hoặc hạn theo lịch địa phương. |
| `ZonedDateTime` | Ngày giờ gắn với một `ZoneId` cụ thể. | Quy tắc lịch gắn với múi giờ như giờ mở cửa hoặc hạn cuối ngày. |

Đối với thời hạn token hoặc session, `Instant` thường phù hợp vì nó biểu diễn thời điểm tuyệt đối. So sánh hai `Instant` không phụ thuộc múi giờ hiển thị.

`Clock` có zone vì nó cũng hỗ trợ các API như `LocalDate.now(clock)`. Khi chỉ gọi `clock.instant()`, giá trị là instant tuyệt đối; zone không làm thay đổi instant đó.

## 10. Dùng cùng một clock trong toàn bộ phép tính

Một lỗi thiết kế là gọi đồng hồ hệ thống nhiều lần trong cùng một thao tác:

```java
Instant issuedAt = Instant.now();
Instant expiresAt = Instant.now().plus(Duration.ofMinutes(5));
```

Hai lệnh `now()` có thể trả về hai thời điểm khác nhau. Khoảng cách thường nhỏ, nhưng khi kiểm thử hoặc tính toán chính xác, việc đọc thời gian hai lần có thể gây sai lệch.

Tốt hơn là lấy một instant duy nhất rồi sử dụng nó:

```java
Instant now = clock.instant();

Instant issuedAt = now;
Instant expiresAt = now.plus(Duration.ofMinutes(5));
```

Điều này cũng giúp kết quả có tính nhất quán: thời điểm phát hành và thời điểm hết hạn được tính từ cùng một mốc.

Tương tự, khi một phương thức phải kiểm tra nhiều điều kiện liên quan đến cùng thời điểm, hãy đọc clock một lần:

```java
public boolean canUse(Instant startsAt, Instant expiresAt) {
    Instant now = clock.instant();

    return !now.isBefore(startsAt)
            && now.isBefore(expiresAt);
}
```

Ví dụ này định nghĩa khoảng hiệu lực theo dạng **bao gồm đầu, không bao gồm cuối**: bắt đầu có hiệu lực khi `now >= startsAt` và hết hiệu lực khi `now >= expiresAt`.

## 11. Kiểm thử clock cố định với nhiều chính sách thời hạn

Một hệ thống có thể có nhiều loại quy tắc:

- Hết hạn tại đúng mốc (`now >= expiresAt`).
- Còn hiệu lực đến trước mốc (`now < expiresAt`).
- Bắt đầu hiệu lực tại mốc (`now >= startsAt`).
- Khoảng hiệu lực `[startsAt, expiresAt)`.
- Có khoảng ân hạn sau khi hết hạn (grace period).

Hãy biểu diễn rõ từng quy tắc thay vì dùng một phép so sánh chung mà không giải thích.

Ví dụ khoảng thời gian hiệu lực:

```java
import java.time.Clock;
import java.time.Instant;
import java.util.Objects;

public final class ValidityWindow {

    private final Clock clock;

    public ValidityWindow(Clock clock) {
        this.clock = Objects.requireNonNull(clock);
    }

    public boolean isActive(Instant startsAt, Instant expiresAt) {
        Objects.requireNonNull(startsAt);
        Objects.requireNonNull(expiresAt);

        if (expiresAt.isBefore(startsAt)) {
            throw new IllegalArgumentException(
                    "expiresAt không được trước startsAt"
            );
        }

        Instant now = clock.instant();

        return !now.isBefore(startsAt)
                && now.isBefore(expiresAt);
    }
}
```

Test tại hai biên:

```java
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.time.Clock;
import java.time.Instant;
import java.time.ZoneOffset;

import org.junit.jupiter.api.Test;

class ValidityWindowTest {

    private static final Instant START =
            Instant.parse("2026-11-15T10:00:00Z");

    private static final Instant END =
            Instant.parse("2026-11-15T11:00:00Z");

    @Test
    void isActiveAtStart() {
        Clock clock = Clock.fixed(START, ZoneOffset.UTC);

        assertTrue(new ValidityWindow(clock).isActive(START, END));
    }

    @Test
    void isNotActiveBeforeStart() {
        Clock clock = Clock.fixed(
                Instant.parse("2026-11-15T09:59:59Z"),
                ZoneOffset.UTC
        );

        assertFalse(new ValidityWindow(clock).isActive(START, END));
    }

    @Test
    void isNotActiveAtEnd() {
        Clock clock = Clock.fixed(END, ZoneOffset.UTC);

        assertFalse(new ValidityWindow(clock).isActive(START, END));
    }
}
```

Bài test ở đầu khoảng xác nhận mốc bắt đầu được bao gồm. Bài test ở cuối khoảng xác nhận mốc hết hạn không được bao gồm. Đây là cách làm rõ ranh giới mà các lỗi thời gian thường xuất hiện.

## 12. Khi nào dùng `Clock.offset()`?

`Clock.offset()` tạo một clock dựa trên clock khác nhưng dịch chuyển thời gian theo một `Duration`.

Ví dụ:

```java
import java.time.Clock;
import java.time.Duration;
import java.time.Instant;
import java.time.ZoneOffset;

Clock base = Clock.fixed(
        Instant.parse("2026-11-15T10:00:00Z"),
        ZoneOffset.UTC
);

Clock fiveMinutesLater = Clock.offset(
        base,
        Duration.ofMinutes(5)
);

System.out.println(base.instant());
System.out.println(fiveMinutesLater.instant());
```

Kết quả:

```text
2026-11-15T10:00:00Z
2026-11-15T10:05:00Z
```

Đây là một cách tiện lợi để kiểm tra một mốc tương đối với clock gốc. Vì clock gốc là fixed, clock offset cũng không tự trôi theo thời gian thực.

Có thể dùng để test token hết hạn sau 5 phút:

```java
Clock issueClock = Clock.fixed(
        Instant.parse("2026-11-15T10:00:00Z"),
        ZoneOffset.UTC
);

TokenService issuer = new TokenService(issueClock);
TokenService.Token token = issuer.issue();

Clock atExpiry = Clock.offset(issueClock, Duration.ofMinutes(15));
TokenService verifier = new TokenService(atExpiry);

System.out.println(verifier.isExpired(token)); // true
```

`Clock.offset()` không thay đổi clock gốc. Nó trả một clock mới với thời điểm được dịch theo duration. Nếu bài test cần một thời điểm tuyệt đối rõ ràng, `Clock.fixed()` thường dễ đọc hơn; nếu cần diễn đạt “sau 15 phút từ mốc gốc”, `Clock.offset()` có thể ngắn gọn.

## 13. Những lỗi thường gặp khi kiểm thử hết hạn

| Lỗi | Hệ quả | Cách xử lý |
| --- | --- | --- |
| Gọi trực tiếp `Instant.now()` trong logic nghiệp vụ | Test phụ thuộc đồng hồ thật và khó tái tạo ranh giới. | Inject `Clock` và gọi `clock.instant()`. |
| Dùng `Thread.sleep()` để chờ hết hạn | Test chậm, phụ thuộc scheduler và độ chính xác thời gian. | Dùng `Clock.fixed()` với instant trước/đúng/sau hạn. |
| Chỉ test trường hợp trước hạn | Bỏ sót lỗi so sánh tại thời điểm bằng nhau. | Có test cho `now < expiresAt`, `now = expiresAt` và `now > expiresAt`. |
| Dùng `isAfter()` trong khi nghiệp vụ hết hạn tại thời điểm bằng | Token vẫn được coi là hợp lệ đúng tại mốc hết hạn. | Dùng `!now.isBefore(expiresAt)` nếu quy tắc là `now >= expiresAt`. |
| Dùng `LocalDateTime` mà không xác định zone | Có thể hiểu sai thời điểm khi chạy ở môi trường khác múi giờ. | Dùng `Instant` cho mốc tuyệt đối hoặc quản lý `ZoneId` rõ ràng cho ngày giờ địa phương. |
| Dùng clock có zone khác với zone nghiệp vụ | Ngày lịch được tính sai ngày. | Tạo clock với zone rõ ràng và kiểm thử bằng cùng zone. |
| Mong `Clock.fixed()` tự tiến theo thời gian | Test luôn nhận cùng một instant. | Tạo fixed clock mới hoặc dùng `Clock.offset()` cho mốc dịch chuyển. |
| Lấy thời gian nhiều lần trong cùng một quyết định | Các điều kiện có thể dựa trên những instant khác nhau. | Đọc `clock.instant()` một lần vào biến `now`. |
| Cho rằng fixed clock kiểm thử được mọi vấn đề thời gian hệ thống | Không kiểm tra được mọi sai lệch đồng hồ, đồng bộ máy chủ hay vấn đề phân tán. | Test logic bằng clock cố định; kiểm tra hạ tầng thời gian bằng quy trình riêng. |

## 14. Tích hợp với ứng dụng chạy thật

Trong production, ứng dụng thường cần thời gian hiện tại từ hệ thống. Có thể truyền `Clock.systemUTC()` khi khởi tạo service:

```java
Clock productionClock = Clock.systemUTC();

AccessPolicy policy = new AccessPolicy(productionClock);
```

Nếu ứng dụng dùng framework dependency injection, hãy đăng ký một bean hoặc provider `Clock` và inject vào các service cần thời gian. Ví dụ đơn giản với constructor injection đã đủ để giữ code độc lập framework.

Không nên tạo `Clock.fixed()` trong cấu hình production thông thường, vì mọi lần đọc thời gian sẽ trả về cùng một mốc và các token/thời hạn sẽ không tự hết hạn.

Cũng không nên thay đổi đồng hồ hệ điều hành của máy test chỉ để kiểm tra logic hết hạn. Việc đó có thể ảnh hưởng các tiến trình khác và cần quyền hệ thống. `Clock.fixed()` cho phép mô phỏng thời gian ở cấp ứng dụng mà không thay đổi đồng hồ thật.

### Truyền clock qua constructor hay static utility?

**Nên ưu tiên constructor injection** cho service có logic phụ thuộc thời gian:

```java
public final class PasswordResetService {
    private final Clock clock;

    public PasswordResetService(Clock clock) {
        this.clock = Objects.requireNonNull(clock);
    }
}
```

Cách này giúp mỗi test tạo service với clock riêng. Static method tự gọi `Instant.now()` sẽ khó thay thế nguồn thời gian và dễ khiến test phụ thuộc môi trường.

Nếu một helper chỉ định dạng một instant đã được truyền vào, nó không cần `Clock`. Chỉ nơi thực sự phải hỏi “bây giờ là lúc nào?” mới cần phụ thuộc vào clock.

## 15. Bài thực hành

### Bài 1 — kiểm tra hạn mã xác minh

Tạo record:

```java
record VerificationCode(String value, Instant expiresAt) {
}
```

Viết service nhận `Clock` và phương thức `isExpired(VerificationCode code)`. Quy tắc: mã hết hạn khi `now >= expiresAt`.

Tạo ba fixed clock: một giây trước hạn, đúng hạn và một giây sau hạn. Xác định kết quả mong đợi.

### Bài 2 — token có thời hạn 10 phút

Viết service phát hành token với `issuedAt = clock.instant()` và `expiresAt = issuedAt.plus(Duration.ofMinutes(10))`. Dùng fixed clock để kiểm tra token còn hiệu lực tại phút thứ 9 và hết hạn tại phút thứ 10.

### Bài 3 — khoảng hiệu lực

Viết phương thức `isActive(startsAt, expiresAt)` với quy tắc `startsAt <= now < expiresAt`. Tạo test cho:

- Trước thời điểm bắt đầu.
- Đúng thời điểm bắt đầu.
- Ở giữa khoảng.
- Đúng thời điểm kết thúc.
- Sau thời điểm kết thúc.

### Bài 4 — hạn theo ngày địa phương

Một phiếu giảm giá có hiệu lực hết ngày 15/11/2026 tại `Asia/Ho_Chi_Minh`. Chuyển ngày hết hạn thành instant cận trên bằng đầu ngày tiếp theo trong zone đó. Dùng fixed clock kiểm tra ngay trước và đúng thời điểm cận trên.

### Bài 5 — kiểm tra code có phụ thuộc đồng hồ thật

Tìm các lời gọi `Instant.now()`, `LocalDate.now()` hoặc `System.currentTimeMillis()` trong lớp nghiệp vụ. Xác định nơi nào nên nhận `Clock` từ bên ngoài và viết lại để test có thể điều khiển thời gian.

## 16. Ghi nhớ nhanh

| Nhu cầu | Cách làm |
| --- | --- |
| Lấy thời gian hiện tại trong code có thể test | Inject `Clock` rồi gọi `clock.instant()`. |
| Tạo thời gian cố định | `Clock.fixed(instant, ZoneOffset.UTC)`. |
| Kiểm tra trước hạn | Cố định clock tại instant nhỏ hơn `expiresAt`. |
| Kiểm tra đúng hạn | Cố định clock bằng chính `expiresAt`. |
| Kiểm tra sau hạn | Cố định clock tại instant lớn hơn `expiresAt`. |
| Hết hạn tại hoặc sau mốc | `!now.isBefore(expiresAt)`. |
| Chỉ hết hạn sau mốc | `now.isAfter(expiresAt)`. |
| Mô phỏng thời gian dịch chuyển | `Clock.offset(baseClock, duration)`. |
| Kiểm thử hạn theo ngày địa phương | Dùng `LocalDate` cùng `ZoneId` rõ ràng, chuyển sang instant theo quy tắc nghiệp vụ. |
| Chạy ứng dụng thật | Thường inject `Clock.systemUTC()` cho logic instant. |

**Nguyên tắc cốt lõi:** Hãy xem thời gian hiện tại là một dependency có thể thay thế. Trong Java 17, inject `Clock` vào logic nghiệp vụ và dùng `Clock.fixed()` trong test để cố định chính xác thời điểm kiểm tra. Với quy tắc hết hạn tại hoặc sau mốc, biểu thức `!now.isBefore(expiresAt)` bao gồm cả thời điểm bằng nhau. Cách làm này giúp test nhanh, lặp lại ổn định và tập trung đúng vào các ranh giới thời gian quan trọng.
