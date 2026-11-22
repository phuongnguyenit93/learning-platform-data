# JwtTimestampValidator và kiểm thử tại các mốc thời gian biên

Trong **Spring Security OAuth 2.0 Resource Server**, access token JWT chỉ được chấp nhận khi thỏa các điều kiện bảo mật như chữ ký, issuer, audience, thời hạn và quyền truy cập. Ba claim thời gian thường gặp là **`exp` (Expiration Time)**, **`nbf` (Not Before)** và **`iat` (Issued At)**. Spring Security cung cấp **`JwtTimestampValidator`** để kiểm tra cửa sổ thời gian hợp lệ của JWT, đồng thời hỗ trợ **clock skew**, tức khoảng dung sai cho sai lệch đồng hồ giữa Authorization Server và Resource Server.

Kiểm tra thời gian tưởng như chỉ là so sánh hai con số. Tuy nhiên, khi token hết hạn tại đúng thời điểm request đến, hoặc chỉ chênh một nano giây so với ranh giới cho phép, lựa chọn toán tử **lớn hơn**, **nhỏ hơn** hay **bằng nhau** quyết định token được chấp nhận hay bị từ chối. Vì thế, những kiểm thử dùng đồng hồ thật và `Thread.sleep(...)` thường thiếu ổn định.

Bài này đi sâu vào **ý nghĩa và đơn vị của các claim thời gian**, cách `JwtTimestampValidator` đánh giá `exp`/`nbf`, cách cấu hình clock skew, xây dựng unit test tại các mốc biên với `Clock.fixed(...)` và cách ghép validator vào `NimbusJwtDecoder` mà không làm mất các điều kiện bảo mật khác. Cần đối chiếu API và quy tắc equality với **phiên bản Spring Security đang sử dụng**.

## 1. Vị trí của `JwtTimestampValidator` trong Resource Server

Một client gọi Orders API:

~~~http
GET /api/orders/123 HTTP/1.1
Host: orders.example.com
Authorization: Bearer <access-token>
~~~

Với JWT access token, luồng xác thực Servlet có thể hình dung như sau:

~~~mermaid
flowchart TD
    A["Client gửi Bearer JWT"] --> B["BearerTokenAuthenticationFilter"]
    B --> C["JwtAuthenticationProvider"]
    C --> D["JwtDecoder / NimbusJwtDecoder"]
    D --> E["Kiểm tra chữ ký, algorithm và khóa tin cậy"]
    E --> F["OAuth2TokenValidator<Jwt>"]
    F --> G["JwtTimestampValidator: exp / nbf"]
    F --> H["Issuer / audience / token profile validators"]
    G --> I{"Tất cả điều kiện hợp lệ?"}
    H --> I
    I -- "Không" --> J["Lỗi xác thực: thường 401"]
    I -- "Có" --> K["JwtAuthenticationToken"]
    K --> L["Authorization: scope, tenant và quyền đối tượng"]
    L --> M["Controller hoặc từ chối quyền: thường 403"]
~~~

| Thành phần | Trách nhiệm |
| --- | --- |
| `JwtDecoder` | Giải mã, xác minh JWS và gọi các token validator đã được cấu hình |
| `JwtTimestampValidator` | Kiểm tra các mốc thời gian `exp` và `nbf` theo đồng hồ tham chiếu cùng clock skew |
| `JwtIssuerValidator` | Kiểm tra issuer được chấp nhận |
| Audience/profile validator | Xác minh token dành cho API và đúng hồ sơ token mong muốn |
| Authorization rules | Kiểm tra scope, vai trò và quyền truy cập tài nguyên cụ thể |

**`JwtTimestampValidator` không cấp hay làm mới token.** Khi token không hợp lệ về thời gian, Resource Server từ chối request. Việc xin access token mới thuộc về **OAuth 2.0 Client và Authorization Server**. Token hợp lệ về thời gian cũng không đồng nghĩa người dùng có thể truy cập mọi đơn hàng.

## 2. NumericDate: điều kiện tiên quyết khi so sánh thời gian

Trong JWT (RFC 7519), `exp`, `nbf` và `iat` có kiểu **NumericDate**: **JSON number biểu thị số giây kể từ Unix epoch** (1970-01-01T00:00:00Z). NumericDate có thể mang phần thập phân, dù nhiều Authorization Server chỉ phát số giây nguyên.

Một JWT Claims Set minh họa:

~~~json
{
  "iss": "https://auth.example.com/realms/shop",
  "sub": "user-42",
  "aud": ["orders-api"],
  "iat": 1763164800,
  "nbf": 1763164800,
  "exp": 1763165700,
  "scope": "orders.read"
}
~~~

Đây là **JSON payload để giải thích claim**, chưa phải JWT có chữ ký hợp lệ. Việc Base64URL-decode payload không thay thế xác minh JWS.

| Claim | Tên đầy đủ | Ý nghĩa |
| --- | --- | --- |
| `exp` | Expiration Time | Thời điểm JWT hết hiệu lực. RFC 7519 diễn đạt: thời gian hiện tại phải **trước** thời điểm `exp` để token hợp lệ, với khả năng áp dụng leeway nhỏ |
| `nbf` | Not Before | JWT không được chấp nhận **trước** mốc này, ngoài khoảng dung sai cho phép |
| `iat` | Issued At | Thời điểm phát hành token, thường dùng để xác định tuổi token hoặc phục vụ chính sách riêng |

NumericDate là **giây**, trong khi nhiều API Java dùng **mili giây**:

| Biểu diễn | Đơn vị | Ví dụ cho 2024-01-01T00:00:00Z |
| --- | --- | --- |
| JWT `NumericDate` | Giây | `1704067200` |
| `Instant.getEpochSecond()` | Giây | `1704067200L` |
| `Instant.toEpochMilli()` | Mili giây | `1704067200000L` |
| `Date.getTime()` | Mili giây | `1704067200000L` |
| `System.currentTimeMillis()` | Mili giây | Một giá trị 13 chữ số ở thời điểm tương ứng |

Nếu phía phát token ghi `System.currentTimeMillis()` vào `exp` mà không đổi đơn vị, thời hạn sẽ sai nghiêm trọng. Nếu tự đọc một NumericDate bằng `Instant.ofEpochMilli(...)`, thời điểm được hiểu gần năm 1970 thay vì năm dự kiến.

Spring Security thường chuyển các claim thời gian chuẩn trong `Jwt` sang `Instant`. Khi đọc JWT đã được xác minh, ưu tiên:

~~~java
import java.time.Instant;
import org.springframework.security.oauth2.jwt.Jwt;

Instant expiresAt = jwt.getExpiresAt();
Instant notBefore = jwt.getNotBefore();
Instant issuedAt = jwt.getIssuedAt();
~~~

Các getter có thể trả `null` nếu claim tương ứng không hiện diện. Tránh `(Long) jwt.getClaims().get("exp")` vì claim có thể đã được chuyển thành `Instant` thay vì `Long`.

## 3. Clock skew là gì?

Giả sử Authorization Server và Resource Server cùng xử lý token tại một thời điểm vật lý, nhưng đồng hồ của Resource Server nhanh hơn **20 giây**. Token có thể bị từ chối sớm nếu API so sánh `exp` và `nbf` mà không cho phép sai số nhỏ. Việc đồng bộ NTP giảm rủi ro nhưng không loại bỏ hoàn toàn độ lệch đồng hồ và độ trễ giữa các hệ thống.

**Clock skew** là khoảng dung sai `S` khi so sánh. Ví dụ cấu hình `Duration.ofSeconds(30)` có thể:

- Chấp nhận token trong một khoảng ngắn **sau `exp`** danh nghĩa.
- Chấp nhận token trong một khoảng ngắn **trước `nbf`** danh nghĩa.

Đây chỉ là quy tắc xác minh ở Resource Server. Skew không sửa nội dung JWT, không gia hạn phiên người dùng và không yêu cầu Authorization Server cấp token mới.

Trong nhiều phiên bản Spring Security, giá trị clock skew mặc định của `JwtTimestampValidator` khoảng **60 giây**. Không nên coi đây là bảo đảm xuyên mọi phiên bản hoặc mọi cấu hình decoder. Khi cần một chính sách xác định, hãy truyền `Duration` tường minh vào validator.

**Clock skew càng lớn, cửa sổ chấp nhận càng mở rộng.** Nếu cấu hình skew 10 phút, API có thể chấp nhận token danh nghĩa đã hết hạn gần 10 phút. Hãy đồng bộ đồng hồ, chọn dung sai nhỏ phù hợp thực tế và không dùng skew để che lỗi đơn vị giây/mili giây.

### Không được nhầm timezone với clock skew

`Instant` biểu thị thời điểm tuyệt đối UTC. Hai máy hiển thị một máy ở UTC và một máy ở `Asia/Ho_Chi_Minh` vẫn có thể cùng một `Instant.now()` nếu đồng hồ được đồng bộ. Múi giờ là cách hiển thị, **không tạo sai lệch bảy giờ** trong NumericDate của JWT.

Do đó không nên cộng hoặc trừ 7 giờ từ `exp` để sửa lỗi. Nếu thời gian bị diễn giải sai, phải sửa chuyển đổi dữ liệu sang `Instant` hoặc cấu hình đồng hồ hệ thống.

## 4. Công thức kiểm tra và vấn đề ở thời điểm bằng nhau

Đặt:

- `T` = thời điểm hiện tại của `Clock` trong validator.
- `S` = khoảng clock skew.
- `E` = mốc `exp`.
- `N` = mốc `nbf`.

Một số phiên bản thông dụng của `JwtTimestampValidator` xử lý tương đương với đoạn mã sau:

~~~java
Instant now = Instant.now(clock);

boolean expirationFailure =
    expiresAt != null && now.minus(clockSkew).isAfter(expiresAt);

boolean notBeforeFailure =
    notBefore != null && now.plus(clockSkew).isBefore(notBefore);
~~~

Đoạn trên giải thích **hành vi của một kiểu triển khai**, không phải mã nguồn bắt buộc của mọi phiên bản. Nếu sử dụng phép so sánh trên:

~~~text
Từ chối do exp nếu: T - S > E
Từ chối do nbf nếu: T + S < N

Qua kiểm tra exp nếu: T - S <= E
Qua kiểm tra nbf nếu: T + S >= N
~~~

Với `Instant.isAfter(...)` và `Instant.isBefore(...)`, **trường hợp bằng nhau không tạo lỗi**. Ví dụ `T-S == E` và `T+S == N` được coi là ở ngay ranh giới hợp lệ trong cách triển khai ấy.

Cần hiểu sự khác biệt giữa điều này và quy tắc ngôn ngữ của RFC 7519 rằng thời gian hiện tại phải **trước** `exp`. Các version có thể khác về cách kiểm tra chính xác tại equality. Khi cần chính sách nghiêm ngặt ở đúng thời điểm hết hạn, phải đối chiếu implementation/version và viết test khóa chặt kỳ vọng.

### Bảng ranh giới với skew 30 giây

Giả sử `T = 2026-11-15T10:00:00Z` và `S = 30 giây`.

| Claim | Giá trị | Kỳ vọng theo công thức `isAfter/isBefore` ở trên |
| --- | --- | --- |
| `exp` | `09:59:29Z` | **Từ chối**, vì đã vượt quá skew |
| `exp` | `09:59:30Z` | **Chấp nhận tại ranh giới** |
| `exp` | `09:59:31Z` | Chấp nhận trong khoảng skew |
| `exp` | `10:00:00Z` | Chấp nhận trong cách so sánh nêu trên |
| `exp` | `10:10:00Z` | Chấp nhận nếu các điều kiện khác đúng |
| `nbf` | `10:00:31Z` | **Từ chối**, chưa đến mốc được phép sau skew |
| `nbf` | `10:00:30Z` | **Chấp nhận tại ranh giới** |
| `nbf` | `10:00:29Z` | Chấp nhận trong khoảng skew |
| `nbf` | `10:00:00Z` | Chấp nhận |
| `nbf` | `09:50:00Z` | Chấp nhận nếu các điều kiện khác đúng |

Khi token có **cả `exp` và `nbf`**, hai điều kiện đều phải thành công. Token chưa đến `nbf` vẫn bị từ chối dù `exp` còn xa. Token quá `exp` vẫn bị từ chối dù `nbf` đã qua từ lâu.

### Claim thiếu có được phép không?

`JwtTimestampValidator` trong các triển khai phổ biến kiểm tra `exp` và `nbf` **nếu có**, không phải lúc nào cũng buộc JWT chứa cả hai claim. Sự hiện diện của `exp`, `nbf` hoặc `iat` là quy định của token profile/hợp đồng riêng.

Nếu API yêu cầu `exp` bắt buộc, hãy bổ sung validator đảm bảo claim tồn tại và đúng kiểu. `iat` không đồng nghĩa với `nbf`; quy tắc giới hạn issued-at trong tương lai hoặc tuổi token tối đa có thể cần validator khác.

## 5. Cố định đồng hồ khi kiểm thử

Trong Java, `java.time.Clock` tách khái niệm “bây giờ” khỏi đồng hồ của máy đang chạy. Dùng `Clock.fixed(...)` giúp một test luôn kiểm tra đúng `T`, không bị ảnh hưởng bởi CI chậm hoặc tốc độ thực thi.

~~~java
import java.time.Clock;
import java.time.Duration;
import java.time.Instant;
import java.time.ZoneOffset;
import org.springframework.security.oauth2.jwt.JwtTimestampValidator;

Instant reference = Instant.parse("2026-11-15T10:00:00Z");
Clock fixedClock = Clock.fixed(reference, ZoneOffset.UTC);

JwtTimestampValidator validator =
    new JwtTimestampValidator(Duration.ofSeconds(30));
validator.setClock(fixedClock);
~~~

Ví dụ dùng phương thức `setClock(Clock)` khi phiên bản Spring Security của dự án cung cấp API này. Với phiên bản có API khác, cần dùng cách tương ứng thay vì dựa vào đồng hồ thật trong test biên.

| Clock | Đặc tính | Khi nào phù hợp? |
| --- | --- | --- |
| `Clock.systemUTC()` | Lấy thời gian thật, luôn tiến lên | Khi ứng dụng chạy thực tế |
| `Clock.fixed(T, ZoneOffset.UTC)` | Luôn trả cùng thời điểm `T` | Test tại equality, ±1ns, ±1s |
| `Clock.offset(base, Duration.ofSeconds(20))` | Dịch thời gian tham chiếu | Mô phỏng server nhanh/chậm |
| `Clock.tick(...)` | Đồng hồ với độ phân giải và bước nhảy cố định | Những bài toán yêu cầu mô phỏng làm tròn thời gian |

**Không dùng `Thread.sleep(...)` để đợi token hết hạn rồi kiểm tra sát biên.** Một test dựa vào thời gian thật có thể thất bại ngẫu nhiên khi hệ điều hành điều phối thread khác nhau.

## 6. Unit test `JwtTimestampValidator` với JUnit 5

Khi chỉ muốn kiểm tra timestamp validator, có thể xây dựng `Jwt` trực tiếp bằng `Jwt.withTokenValue(...)`. Không cần private key, token ký thật hoặc mock HTTP server vì đây là **unit test logic kiểm tra thời gian**, không phải kiểm tra xác minh JWS.

Ví dụ:

~~~java
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.time.Clock;
import java.time.Duration;
import java.time.Instant;
import java.time.ZoneOffset;
import org.junit.jupiter.api.Test;
import org.springframework.security.oauth2.core.OAuth2TokenValidatorResult;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.jwt.JwtTimestampValidator;

class JwtTimestampValidatorBoundaryTest {

    private static final Instant T =
        Instant.parse("2026-11-15T10:00:00Z");
    private static final Duration SKEW = Duration.ofSeconds(30);

    private JwtTimestampValidator validatorAt(Instant now) {
        JwtTimestampValidator validator =
            new JwtTimestampValidator(SKEW);
        validator.setClock(Clock.fixed(now, ZoneOffset.UTC));
        return validator;
    }

    private Jwt token(Instant expiresAt, Instant notBefore) {
        Jwt.Builder builder = Jwt.withTokenValue("jwt-for-validator-test")
            .header("alg", "RS256")
            .subject("user-42")
            .issuedAt(T.minusSeconds(120));

        if (expiresAt != null) {
            builder.expiresAt(expiresAt);
        }
        if (notBefore != null) {
            builder.notBefore(notBefore);
        }

        return builder.build();
    }

    private boolean valid(Instant exp, Instant nbf) {
        OAuth2TokenValidatorResult result =
            validatorAt(T).validate(token(exp, nbf));
        return !result.hasErrors();
    }

    @Test
    void expirationBeyondSkewIsRejected() {
        // T - 30 giây - 1 nano giây: quá ranh giới.
        Instant exp = T.minus(SKEW).minusNanos(1);
        assertFalse(valid(exp, T.minusSeconds(60)));
    }

    @Test
    void expirationExactlyAtSkewBoundaryIsAccepted() {
        // Trong implementation dùng isAfter, equality không tạo lỗi.
        Instant exp = T.minus(SKEW);
        assertTrue(valid(exp, T.minusSeconds(60)));
    }

    @Test
    void expirationJustInsideSkewIsAccepted() {
        Instant exp = T.minus(SKEW).plusNanos(1);
        assertTrue(valid(exp, T.minusSeconds(60)));
    }

    @Test
    void notBeforeBeyondSkewIsRejected() {
        Instant nbf = T.plus(SKEW).plusNanos(1);
        assertFalse(valid(T.plusSeconds(600), nbf));
    }

    @Test
    void notBeforeExactlyAtSkewBoundaryIsAccepted() {
        // Trong implementation dùng isBefore, equality không tạo lỗi.
        Instant nbf = T.plus(SKEW);
        assertTrue(valid(T.plusSeconds(600), nbf));
    }

    @Test
    void notBeforeJustInsideSkewIsAccepted() {
        Instant nbf = T.plus(SKEW).minusNanos(1);
        assertTrue(valid(T.plusSeconds(600), nbf));
    }

    @Test
    void bothConditionsMustPass() {
        // exp tốt, nbf quá xa tương lai.
        assertFalse(valid(T.plusSeconds(60), T.plusSeconds(31)));

        // nbf tốt, exp quá xa quá khứ.
        assertFalse(valid(T.minusSeconds(31), T.minusSeconds(60)));

        // Cả exp và nbf hợp lệ.
        assertTrue(valid(T.plusSeconds(60), T.minusSeconds(60)));
    }
}
~~~

Ở đây chuỗi `"jwt-for-validator-test"` không phải JWT ký hợp lệ; `Jwt` dựng tay chỉ dùng để gọi validator. Test này **không chứng minh decoder đã xác minh chữ ký, issuer hay audience**. Các kỳ vọng equality phản ánh triển khai dùng `isAfter/isBefore`; cần đối chiếu và điều chỉnh theo phiên bản thư viện thực tế.

### Test ma trận thời gian với `@ParameterizedTest`

Thay vì tạo nhiều phép thử lặp, có thể tham số hóa offset của `exp` so với `T`. Ví dụ:

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;

import java.time.Clock;
import java.time.Duration;
import java.time.Instant;
import java.time.ZoneOffset;
import java.util.stream.Stream;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.Arguments;
import org.junit.jupiter.params.provider.MethodSource;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.jwt.JwtTimestampValidator;

class ExpirationMatrixTest {

    private static final Instant T =
        Instant.parse("2026-11-15T10:00:00Z");

    static Stream<Arguments> cases() {
        return Stream.of(
            Arguments.of(-31L, false),
            Arguments.of(-30L, true),
            Arguments.of(-29L, true),
            Arguments.of(0L, true),
            Arguments.of(60L, true)
        );
    }

    @ParameterizedTest(name = "offset={0}s, valid={1}")
    @MethodSource("cases")
    void validateAtOffsets(long offsetSeconds, boolean expectedValid) {
        JwtTimestampValidator validator =
            new JwtTimestampValidator(Duration.ofSeconds(30));
        validator.setClock(Clock.fixed(T, ZoneOffset.UTC));

        Jwt token = Jwt.withTokenValue("jwt-test")
            .header("alg", "RS256")
            .subject("user-42")
            .issuedAt(T.minusSeconds(120))
            .notBefore(T.minusSeconds(120))
            .expiresAt(T.plusSeconds(offsetSeconds))
            .build();

        boolean valid = !validator.validate(token).hasErrors();
        assertEquals(expectedValid, valid);
    }
}
~~~

Có thể xây ma trận tương tự cho `nbf` ở các offset `+29s`, `+30s`, `+31s`. Các trường hợp ±1 nano giây thường rõ hơn khi viết test riêng, bởi offset nguyên giây sẽ không phát hiện khác biệt ở độ phân giải subsecond.

## 7. Skew bằng zero và quy tắc strict expiration

Nếu cấu hình:

~~~java
JwtTimestampValidator validator =
    new JwtTimestampValidator(Duration.ZERO);
validator.setClock(Clock.fixed(T, ZoneOffset.UTC));
~~~

thì trong triển khai dùng `isAfter`, tại đúng `T == exp` phép kiểm tra `T.isAfter(exp)` trả false, tức không tạo lỗi expiration ở **đúng điểm bằng nhau**. Tuy nhiên, RFC 7519 diễn đạt điều kiện `exp` theo quy tắc thời gian hiện tại phải **trước** expiration time.

Điều này tạo ra hai câu hỏi khác nhau:

1. **JWT profile có yêu cầu gì?** Token được sử dụng khi nào, leeway cho phép bao nhiêu, có giới hạn thời gian bổ sung không?
2. **Phiên bản thư viện thực hiện phép so sánh nào?** Equality có được chấp nhận theo code của version đó hay không?

Hãy kiểm thử đúng boundary thay vì suy luận rằng skew bằng 0 luôn bảo đảm strict `now < exp`. Nếu API yêu cầu từ chối token ngay ở chính thời điểm `exp`, hãy thể hiện chính sách rõ ràng bằng cấu hình hoặc validator phù hợp với version và yêu cầu bảo mật.

Với request thực tế, thời điểm đồng hồ có thể đạt độ chính xác khác NumericDate của issuer, nên equality rất hiếm; nhưng test boundary cố tình tạo tình huống này để tránh bug nằm ẩn trong triển khai.

## 8. Các ràng buộc thời gian nằm ngoài `JwtTimestampValidator`

Một bộ kiểm tra thời gian an toàn có thể cần nhiều điều kiện hơn kiểm tra `exp` và `nbf` so với `now`.

### 8.1. Claim bắt buộc

Theo JWT tổng quát, `exp`/`nbf`/`iat` không mặc nhiên bắt buộc trong mọi token. Nhưng profile riêng như OAuth 2.0 JWT access token theo RFC 9068 có những yêu cầu claim cụ thể. Nếu API bắt buộc `exp`, cần có validator yêu cầu claim hiện diện, đúng kiểu và có ý nghĩa.

Không nên mặc định `JwtTimestampValidator` tự từ chối mọi JWT thiếu `exp`. Ngoài ra, `nbf` có thể là tùy chọn theo profile; thiếu `nbf` không nhất thiết là token sai.

### 8.2. `iat` ở tương lai

`iat` là thời điểm **phát hành**, không phải thời điểm bắt đầu được dùng. Một token có `iat` nằm trong tương lai có thể cần bị từ chối theo profile hoặc chính sách API, nhưng không nên giả định timestamp validator mặc định luôn kiểm tra quy tắc này. Khi cần, tạo validation riêng cho điều kiện:

~~~text
iat <= now + issuedAtAllowedSkew
~~~

### 8.3. Quan hệ giữa `nbf` và `exp`

Một token có thể mang `nbf > exp`:

~~~json
{
  "iat": 1763164800,
  "nbf": 1763165700,
  "exp": 1763165400
}
~~~

Về logic, cửa sổ hiệu lực danh nghĩa bị đảo ngược. `JwtTimestampValidator` thường kiểm tra `exp` và `nbf` **riêng biệt** so với clock. Nếu profile yêu cầu `exp > nbf` hoặc `exp > iat`, API cần validator bảo đảm quan hệ đó.

Ví dụ validator chính sách đòi cả `exp` và `nbf` hiện diện và `exp` lớn hơn `nbf`:

~~~java
import java.time.Instant;
import org.springframework.security.oauth2.core.OAuth2Error;
import org.springframework.security.oauth2.core.OAuth2TokenValidator;
import org.springframework.security.oauth2.core.OAuth2TokenValidatorResult;
import org.springframework.security.oauth2.jwt.Jwt;

class TimeWindowPolicyValidator implements OAuth2TokenValidator<Jwt> {

    @Override
    public OAuth2TokenValidatorResult validate(Jwt jwt) {
        Instant exp = jwt.getExpiresAt();
        Instant nbf = jwt.getNotBefore();

        if (exp == null || nbf == null || !exp.isAfter(nbf)) {
            return OAuth2TokenValidatorResult.failure(
                new OAuth2Error("invalid_token", "Invalid token window", null)
            );
        }
        return OAuth2TokenValidatorResult.success();
    }
}
~~~

**Đây là một chính sách ví dụ**, không phải yêu cầu phổ quát của mọi JWT. Nếu issuer được phép bỏ `nbf`, không nên áp dụng validator yêu cầu `nbf` một cách tùy tiện.

### 8.4. Token lifetime tối đa

Token có `exp` rất xa trong tương lai vẫn “chưa hết hạn” theo phép kiểm tra đơn giản, nhưng API có thể giới hạn lifetime, ví dụ tối đa 15 phút từ `iat`. Đây là điều kiện:

~~~text
exp - iat <= maximumTokenLifetime
~~~

Nó khác với clock skew và cần một validator chính sách riêng. Đừng nới skew để điều chỉnh tuổi token tối đa.

## 9. Ghép validator vào `NimbusJwtDecoder`

### 9.1. Cấu hình Resource Server mặc định

Ứng dụng Spring Boot Servlet thường dùng dependency:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-oauth2-resource-server</artifactId>
</dependency>
~~~

Ví dụ `application.yml`:

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://auth.example.com/realms/shop
~~~

Spring Security dùng issuer để tìm cấu hình/khóa xác minh phù hợp và áp dụng các validator mặc định theo phiên bản. **Audience và JWT profile dành riêng cho API vẫn cần được xác định rõ và cấu hình khi cần**.

Security filter chain minh họa:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
class ApiSecurity {
    @Bean
    SecurityFilterChain apiSecurity(HttpSecurity http) throws Exception {
        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/public/**").permitAll()
                .anyRequest().authenticated())
            .oauth2ResourceServer(oauth2 ->
                oauth2.jwt(Customizer.withDefaults()))
            .build();
    }
}
~~~

Đây là cấu hình mô tả cơ chế xác thực Bearer JWT. Ứng dụng thực tế cần bổ sung scope, method authorization và quyền truy cập bản ghi, đồng thời xử lý CSRF/session theo kiểu client và cơ chế xác thực. Không phải mọi API đều nên tắt CSRF.

### 9.2. Tùy chỉnh clock skew

Khi cần skew 30 giây thay mặc định, tạo `JwtTimestampValidator(Duration)` và đặt nó trong một **tập validator đầy đủ**:

~~~java
import java.time.Duration;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.oauth2.core.DelegatingOAuth2TokenValidator;
import org.springframework.security.oauth2.core.OAuth2Error;
import org.springframework.security.oauth2.core.OAuth2TokenValidator;
import org.springframework.security.oauth2.core.OAuth2TokenValidatorResult;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.jwt.JwtDecoder;
import org.springframework.security.oauth2.jwt.JwtIssuerValidator;
import org.springframework.security.oauth2.jwt.JwtTimestampValidator;
import org.springframework.security.oauth2.jwt.NimbusJwtDecoder;

@Configuration
class OrdersJwtDecoderConfiguration {
    private static final String ISSUER =
        "https://auth.example.com/realms/shop";

    @Bean
    JwtDecoder jwtDecoder() {
        NimbusJwtDecoder decoder = NimbusJwtDecoder
            .withIssuerLocation(ISSUER)
            .build();

        JwtTimestampValidator timestamps =
            new JwtTimestampValidator(Duration.ofSeconds(30));

        OAuth2TokenValidator<Jwt> audience = jwt ->
            jwt.getAudience().contains("orders-api")
                ? OAuth2TokenValidatorResult.success()
                : OAuth2TokenValidatorResult.failure(
                    new OAuth2Error(
                        "invalid_token", "Invalid audience", null
                    )
                );

        decoder.setJwtValidator(
            new DelegatingOAuth2TokenValidator<>(
                timestamps,
                new JwtIssuerValidator(ISSUER),
                audience
            )
        );
        return decoder;
    }
}
~~~

**Cẩn thận với `setJwtValidator(...)`:** phương thức này **thay thế** tập validator gắn trên decoder, vì thế phải bảo đảm đầy đủ timestamp, issuer, audience, profile/`typ` và các claim bắt buộc phù hợp phiên bản. Nếu ứng dụng dùng access token RFC 9068 `at+jwt`, chỉ kiểm tra ba điều kiện trên là **chưa đủ** để bảo đảm toàn bộ token profile.

Không nên ghép `JwtValidators.createDefaultWithIssuer(ISSUER)` (thường đã chứa một timestamp validator) cùng một `JwtTimestampValidator` khác có skew 30 giây, rồi vô tình tạo **hai chính sách timestamp** chồng chéo. Hãy xác định rõ tập validator nào chịu trách nhiệm cho từng điều kiện, bảo đảm không bỏ sót các kiểm tra có sẵn của version.

### 9.3. Khi token hết hạn, HTTP response thường ra sao?

Nếu JWT không qua được timestamp validation, request thường bị từ chối ở bước **authentication**:

~~~http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer error="invalid_token"
Content-Length: 0
~~~

Đây là response minh họa; body/header thực tế tùy entry point, exception handler và phiên bản Spring Security. Token đã xác thực nhưng thiếu scope hoặc quyền nghiệp vụ thường dẫn đến **403 Forbidden**. Một lỗi 401 không nhất thiết chỉ do `exp`: có thể còn do chữ ký, issuer, audience, profile hay Bearer parsing.

## 10. Unit test, decoder test và HTTP integration test khác nhau

| Loại kiểm thử | Xác nhận | Chưa chứng minh |
| --- | --- | --- |
| Unit test `JwtTimestampValidator` với Clock cố định | Logic `exp`/`nbf`/skew và equality | Chữ ký JWS, issuer, audience hoặc HTTP status |
| Test `JwtDecoder` với JWT ký thật | Giải mã/chữ ký và validator được gắn đúng | Cấu hình quyền endpoint nếu không gửi request HTTP |
| Integration test qua Spring Security filter chain | Bearer parsing, 401/403 và authorization trong request | Cần chắc chắn đang gọi decoder thật |
| MockMvc dùng `jwt()` của Spring Security Test | Scope/authorities/endpoint khi có Authentication thử nghiệm | Thường không kiểm tra signature hoặc timestamp validator thật |

Ví dụ một test phân quyền dùng mock JWT:

~~~java
// Chỉ minh họa dạng test authorization, không phải test thời gian JWT.
// mockMvc.perform(get("/api/orders")
//     .with(jwt().authorities(
//         new SimpleGrantedAuthority("SCOPE_orders.read"))))
//     .andExpect(status().isOk());
~~~

Test trên hữu ích khi kiểm tra quyền `SCOPE_orders.read`, nhưng nó không chứng minh `exp` quá hạn bị từ chối. Để kiểm tra **401 do JWT hết hạn**, cần một token ký bằng khóa kiểm thử, decoder thật với validator/Clock theo chính sách, rồi request đi qua filter chain.

Với JUnit unit test, không cần dùng đồng hồ thật. Với decoder/integration test, có thể cấu hình decoder dùng validator có Clock cố định, thay vì cố chờ token hết hạn ngoài đời.

### Mô phỏng sai lệch đồng hồ mà không sửa đồng hồ hệ thống

~~~java
import java.time.Clock;
import java.time.Duration;
import java.time.Instant;
import java.time.ZoneOffset;

Clock issuerClock = Clock.fixed(
    Instant.parse("2026-11-15T10:00:00Z"),
    ZoneOffset.UTC
);
Clock resourceClock = Clock.offset(
    issuerClock, Duration.ofSeconds(25)
);

Instant issuerNow = Instant.now(issuerClock);     // 10:00:00Z
Instant apiNow = Instant.now(resourceClock);     // 10:00:25Z
~~~

Đặt `resourceClock` vào `JwtTimestampValidator` và tạo JWT với `nbf`/`exp` theo thời điểm issuer để mô phỏng API nhanh hơn 25 giây. Skew 30 giây có thể bù độ lệch này; skew bằng 0 sẽ tạo kết quả khác gần mốc ranh giới.

## 11. Ma trận tình huống cần hiểu khi kiểm thử biên

Lấy `T` là thời điểm cố định, `S = 30s`. Bảng sau nêu tình huống cần mô tả, độc lập với việc hiện thực test bằng JUnit hoặc công cụ khác:

| Tình huống | Dữ liệu | Mục đích |
| --- | --- | --- |
| Token quá hạn rõ ràng | `exp = T - 5 phút` | Khẳng định từ chối expiration |
| `exp` chạm ranh giới skew | `exp = T - 30s` | Phân biệt equality và quá hạn |
| `exp` quá ranh giới 1ns | `exp = T - 30s - 1ns` | Kiểm tra strict boundary |
| `exp` trong ranh giới | `exp = T - 29s` | Kiểm tra dung sai hoạt động |
| `nbf` xa tương lai | `nbf = T + 5 phút` | Khẳng định từ chối chưa đến hiệu lực |
| `nbf` chạm ranh giới skew | `nbf = T + 30s` | Kiểm tra equality |
| `nbf` quá ranh giới 1ns | `nbf = T + 30s + 1ns` | Kiểm tra strict boundary |
| `nbf` trong ranh giới | `nbf = T + 29s` | Kiểm tra dung sai |
| Hai claim cùng hợp lệ | `nbf = T - 1m`, `exp = T + 1m` | Chấp nhận về thời gian |
| `exp` hợp lệ, `nbf` sai | `exp = T + 1m`, `nbf = T + 1m` | Không bỏ qua kiểm tra `nbf` |
| `nbf` hợp lệ, `exp` sai | `nbf = T - 1m`, `exp = T - 1m` | Không bỏ qua `exp` |
| Không có `exp` | Claim `exp` không hiện diện | Phân biệt timestamp validator và required-claim validator |
| `iat` nằm ở tương lai | `iat = T + 5m` | Kiểm tra policy riêng nếu áp dụng |
| Có dữ liệu sai đơn vị | `exp` ghi milliseconds thay seconds | Phát hiện lỗi hợp đồng JSON |
| Skew khác nhau trên nhiều API | Cùng token, policy 0s và 30s | Kiểm tra tính nhất quán vận hành |

Nên đặc biệt chú ý **độ phân giải thời gian**: `Instant` hỗ trợ nano giây, nhưng JWT issuer có thể chỉ phát số giây nguyên. Unit test ở ±1ns làm rõ toán tử so sánh, còn test tích hợp cần hiểu cách thư viện chuyển NumericDate trong JSON sang `Instant`.

## 12. Câu hỏi thường gặp

### “Access token đã tới giờ `exp`, tại sao đôi khi Resource Server vẫn chấp nhận?”

Có thể Resource Server đang áp dụng clock skew. Khi skew được cho phép, thời gian kiểm tra có thể nằm trong một cửa sổ trễ sau `exp` danh nghĩa. Ngoài ra, cách so sánh tại **đúng điểm bằng nhau** phụ thuộc phiên bản. Cần kiểm tra cấu hình thật và không coi clock skew là refresh token.

### “Tăng skew có sửa được mọi lỗi JWT hết hạn không?”

Không. Lỗi có thể do sai đơn vị giây/mili giây, đồng hồ hệ thống lệch lớn, issuer phát `exp` sai hoặc API đang từ chối token vì chữ ký/audience/issuer. Tăng skew tùy tiện mở rộng thời gian sử dụng token, có thể tạo lỗ hổng bảo mật.

### “`JwtTimestampValidator` có kiểm tra `iat` và tuổi token tối đa không?”

Không nên giả định như vậy. Trong các phiên bản thông dụng, validator này tập trung vào `exp` và `nbf`. Nếu token profile quy định `iat` không được vượt quá `now + skew` hoặc `exp - iat` không quá một giới hạn, cần validator bổ sung theo hợp đồng.

### “Nếu test với `Clock.fixed` pass, tại sao gọi API thật vẫn nhận 401?”

Unit test timestamp không kiểm tra signature, thuật toán, JWKS, issuer, audience, loại JWT hoặc cú pháp bearer token. Cần phân biệt lỗi từ decoder/validators và lỗi authorization. Không nên ghi nguyên access token vào log khi chẩn đoán.

### “Có thể sửa `exp` trong JWT để sử dụng tiếp không?”

Không. JWT ký bằng JWS bảo vệ cả header và payload; thay `exp` làm chữ ký không còn hợp lệ. Client phải xin access token mới từ Authorization Server theo grant phù hợp. Resource Server chỉ xác thực token được gửi đến.

### “Có phải cứ `exp` hợp lệ là endpoint trả 200?”

Không. Token còn hạn vẫn có thể sai chữ ký, issuer, audience, type/profile; hoặc người dùng thiếu scope, không được xem bản ghi cụ thể. `JwtTimestampValidator` chỉ phụ trách một phần của việc xác thực JWT.

## 13. Nguyên tắc áp dụng trong hệ thống

1. **Đọc đúng NumericDate:** JWT dùng giây Unix epoch; Java `Instant` giúp so sánh thời điểm tuyệt đối. Không tự trộn epoch milliseconds.
2. **Định nghĩa chính sách rõ ràng:** claim nào bắt buộc, skew bao nhiêu, có cần kiểm tra `iat`, token lifetime tối đa hoặc quan hệ `nbf < exp` hay không.
3. **Kiểm thử bằng Clock cố định:** tạo `T` và các mốc `T-S`, `T+S`, ±1ns để phát hiện sai khác ở boundary mà không cần `sleep`.
4. **Đối chiếu đúng phiên bản:** đặc biệt với equality và khả năng cấu hình `setClock(Clock)`/`JwtDecoder`, không suy luận từ ví dụ thuộc phiên bản khác.
5. **Giữ tập validators đầy đủ:** signature và khóa tin cậy, issuer, audience, time, token profile, claim bắt buộc và quyền nghiệp vụ. `setJwtValidator(...)` không được làm mất các điều kiện quan trọng.
6. **Phân biệt kiểm tra token và phân quyền:** lỗi timestamp thường dẫn đến 401; token đã xác thực nhưng thiếu quyền thường dẫn đến 403.
7. **Test đúng lớp xử lý:** unit test validator, decoder test dùng JWT ký thật và HTTP integration test có filter chain thật trả lời các câu hỏi khác nhau.

**Điểm cần nhớ:** `JwtTimestampValidator` dùng đồng hồ tham chiếu và clock skew để quyết định JWT có nằm trong cửa sổ thời gian hợp lệ hay không. Những lỗi khó thấy thường xuất hiện ở **đơn vị NumericDate**, **mốc `exp`/`nbf` sát ranh giới** và **phép so sánh bằng nhau**. Dùng `Clock.fixed(...)` cùng các mốc ±1 giây/±1 nano giây giúp diễn đạt chính sách chính xác, ổn định và có thể lặp lại.
