# Test expired token

## Mục tiêu học tập

Sau bài này, bạn có thể:

- Giải thích ý nghĩa của thời điểm hết hạn trong JWT, opaque access token và refresh token.
- Thiết kế kiểm thử cho các trường hợp token còn hạn, vừa chạm thời điểm hết hạn, đã hết hạn và được chấp nhận trong khoảng clock skew.
- Kiểm tra cách resource server, API gateway và authorization server phản hồi khi nhận token hết hạn.
- Tạo test xác định bằng đồng hồ giả lập, tránh phụ thuộc vào `Thread.sleep()` hoặc thời gian chạy thực tế.
- Phát hiện lỗi cấu hình thường gặp như sai đơn vị thời gian, cache vượt quá thời hạn token hoặc bỏ qua kiểm tra expiration.

## 1. Vì sao phải kiểm thử token hết hạn?

Token là thông tin xác thực hoặc ủy quyền có thời hạn. Khi token hết hạn, hệ thống phải ngừng chấp nhận nó theo chính sách đã công bố. Nếu resource server vẫn cho phép token hết hạn truy cập tài nguyên, kẻ tấn công có thể tiếp tục sử dụng bearer token đã bị lộ sau khoảng thời gian mà hệ thống dự kiến bảo vệ.

Ngược lại, nếu hệ thống từ chối token còn hạn do tính thời gian sai, người dùng và dịch vụ hợp lệ sẽ gặp lỗi xác thực ngẫu nhiên. Lỗi này thường xuất hiện ở ranh giới thời gian, khi các máy chủ lệch đồng hồ, khi cache giữ kết quả xác thực quá lâu hoặc khi một thành phần dùng giây còn thành phần khác dùng mili giây.

Kiểm thử expiration cần xác minh cả hai điều:

1. **Đúng thời điểm:** token chỉ được chấp nhận trong khoảng thời gian mà chính sách cho phép.
2. **Đúng hành vi:** khi token hết hạn, hệ thống từ chối truy cập, không thực hiện nghiệp vụ được bảo vệ và trả phản hồi phù hợp.

## 2. Hiểu đúng các mốc thời gian của token

### 2.1 JWT và claim exp

Trong JWT, claim **exp** (Expiration Time) biểu diễn thời điểm hết hạn dưới dạng **NumericDate**: số giây tính từ Unix Epoch `1970-01-01T00:00:00Z`, có thể biểu diễn phần lẻ của giây. Theo RFC 7519, một JWT không được chấp nhận để xử lý tại hoặc sau thời điểm `exp`; thời điểm hiện tại phải đứng trước `exp`. Thư viện có thể hỗ trợ một khoảng dung sai nhỏ để xử lý sai lệch đồng hồ.

Ví dụ payload:

~~~json
{
  "iss": "https://identity.example",
  "sub": "user-42",
  "aud": "orders-api",
  "iat": 1893455700,
  "nbf": 1893455700,
  "exp": 1893456000,
  "scope": "orders.read"
}
~~~

Trong ví dụ, `exp` là một mốc thời gian tuyệt đối. Nó không phải số giây token được phép sống kể từ lúc resource server nhận request. Khi kiểm tra, verifier so sánh thời gian hiện tại với giá trị đã giải mã từ token sau khi xác minh chữ ký và các điều kiện tin cậy khác.

JWT nói chung không bắt buộc mọi loại token đều phải có `exp` trong mọi ngữ cảnh. Tuy nhiên, hồ sơ bảo mật của hệ thống có thể và thường nên yêu cầu access token phải có expiration. Với OpenID Connect ID Token, claim `exp` là bắt buộc. Bài kiểm thử phải xác minh đúng yêu cầu của loại token và profile mà hệ thống sử dụng; nếu policy yêu cầu `exp` mà claim bị thiếu, token phải bị từ chối.

### 2.2 Access token, refresh token và ID Token

Các loại token có mục đích và vòng đời khác nhau:

| Loại token | Dùng để làm gì? | Điều cần kiểm thử |
| --- | --- | --- |
| Access token | Truy cập resource server | Không truy cập API sau expiration; kiểm tra `exp` hoặc trạng thái active |
| Refresh token | Xin access token mới | Refresh token hết hạn hoặc bị thu hồi không được dùng để cấp token mới |
| ID Token | Mang thông tin xác thực người dùng cho client OIDC | Client xác minh issuer, audience, chữ ký và `exp` theo OIDC |
| Token exchange output | Đại diện quyền truy cập tới audience đích | Token mới phải có thời hạn hợp lệ theo policy; không kéo dài quyền từ token đầu vào trái phép |

Không suy ra thời hạn refresh token từ thời hạn access token. Một hệ thống có thể cấp access token sống ngắn và refresh token sống lâu hơn, nhưng refresh token vẫn có thể hết hạn, bị thu hồi hoặc bị vô hiệu hóa khi rotation phát hiện tái sử dụng. Kiểm thử phải dùng đúng policy của authorization server.

### 2.3 Opaque token

Opaque token không để resource server tự đọc claim `exp` từ nội dung token. Resource server thường xác minh trạng thái qua introspection endpoint hoặc cơ chế tra cứu tin cậy khác. Theo RFC 7662, phản hồi introspection có trường `active`; token hết hạn phải được xem là không active. Trường `exp` có thể được trả về để client/resource server biết thời hạn, tùy phản hồi và profile triển khai.

Do đó, bộ test opaque token cần kiểm tra cả phản hồi introspection và cache kết quả. Nếu cache giữ trạng thái `active=true` lâu hơn expiration, resource server có thể chấp nhận token đã hết hạn dù authorization server đã trả trạng thái mới là inactive.

## 3. Xác định chính xác ranh giới expiration

Giả sử token có thời điểm hết hạn `T` và hệ thống không cấu hình clock skew:

| Thời điểm kiểm tra | Kỳ vọng |
| --- | --- |
| `T - 1 giây` | Còn hạn |
| Ngay trước `T` | Còn hạn |
| Đúng `T` | Hết hạn |
| `T + 1 giây` | Hết hạn |

Điều kiện cốt lõi của JWT là `now < exp`. Vì vậy, phép so sánh phải giữ đúng ranh giới: `now == exp` không còn hợp lệ nếu không có dung sai.

### Clock skew là gì?

Các máy chủ có thể lệch nhau một khoảng thời gian nhỏ do đồng bộ đồng hồ. Một số JWT verifier cho phép cấu hình **clock skew/leeway** để tránh từ chối nhầm token vì chênh lệch này. Nếu policy cho phép dung sai `L`, verifier có thể chấp nhận token tới trước `exp + L`. Cách áp dụng cụ thể phụ thuộc thư viện và cấu hình; phải kiểm thử theo đúng semantics của verifier đang dùng.

Clock skew cần nhỏ, có chủ đích và thống nhất giữa các thành phần. Không tăng dung sai lớn để che giấu máy chủ không đồng bộ thời gian. Nếu dung sai là 60 giây, token có thể được chấp nhận thêm gần 60 giây sau `exp`, nên đây cũng là một phần của cửa sổ rủi ro.

### Phân biệt exp, nbf và iat

| Claim | Ý nghĩa | Lỗi cần kiểm thử |
| --- | --- | --- |
| `exp` | Token không còn được chấp nhận từ thời điểm hết hạn trở đi | Token hết hạn vẫn được chấp nhận |
| `nbf` | Token chưa được chấp nhận trước thời điểm bắt đầu hiệu lực | Token được dùng quá sớm |
| `iat` | Thời điểm token được phát hành | Dùng sai để thay thế kiểm tra expiration |

`iat` không thay thế `exp`. Một token có `iat` cũ không nhất thiết đã hết hạn nếu vẫn còn trong lifetime được policy cho phép; ngược lại, `iat` mới không làm token hợp lệ nếu `exp` đã qua hoặc chữ ký không hợp lệ.

## 4. Kiểm thử theo từng lớp hệ thống

### 4.1 Unit test cho logic thời gian

Đưa nguồn thời gian vào qua `Clock` giúp test kiểm soát được thời điểm hiện tại. Test có thể đặt đồng hồ đúng trước, tại hoặc sau `exp`, chạy ngay lập tức và luôn cho kết quả lặp lại.

Ví dụ Java:

~~~java
import java.time.Clock;
import java.time.Duration;
import java.time.Instant;

final class TokenExpirationPolicy {
    private final Clock clock;
    private final Duration clockSkew;

    TokenExpirationPolicy(Clock clock, Duration clockSkew) {
        if (clockSkew.isNegative()) {
            throw new IllegalArgumentException("clockSkew must not be negative");
        }
        this.clock = clock;
        this.clockSkew = clockSkew;
    }

    // Policy của ví dụ yêu cầu mọi access token phải có exp.
    boolean isValid(Instant expiresAt) {
        if (expiresAt == null) {
            return false;
        }
        Instant acceptanceDeadline = expiresAt.plus(clockSkew);
        return clock.instant().isBefore(acceptanceDeadline);
    }
}
~~~

Test với JUnit 5:

~~~java
import static org.junit.jupiter.api.Assertions.*;

import java.time.Clock;
import java.time.Duration;
import java.time.Instant;
import java.time.ZoneOffset;
import org.junit.jupiter.api.Test;

class TokenExpirationPolicyTest {
    private static final Instant EXP =
            Instant.parse("2030-01-01T00:00:00Z");

    private TokenExpirationPolicy policyAt(
            Instant now, Duration skew) {
        Clock clock = Clock.fixed(now, ZoneOffset.UTC);
        return new TokenExpirationPolicy(clock, skew);
    }

    @Test
    void acceptsTokenBeforeExpiration() {
        var policy = policyAt(EXP.minusSeconds(1), Duration.ZERO);
        assertTrue(policy.isValid(EXP));
    }

    @Test
    void rejectsTokenAtExactExpiration() {
        var policy = policyAt(EXP, Duration.ZERO);
        assertFalse(policy.isValid(EXP));
    }

    @Test
    void rejectsTokenAfterExpiration() {
        var policy = policyAt(EXP.plusSeconds(1), Duration.ZERO);
        assertFalse(policy.isValid(EXP));
    }

    @Test
    void appliesConfiguredClockSkew() {
        var policy = policyAt(
                EXP.plusSeconds(30), Duration.ofSeconds(60));
        assertTrue(policy.isValid(EXP));
    }

    @Test
    void rejectsAtEndOfClockSkewWindow() {
        var policy = policyAt(
                EXP.plusSeconds(60), Duration.ofSeconds(60));
        assertFalse(policy.isValid(EXP));
    }

    @Test
    void rejectsMissingExpirationWhenPolicyRequiresIt() {
        var policy = policyAt(EXP.minusSeconds(10), Duration.ZERO);
        assertFalse(policy.isValid(null));
    }
}
~~~

Đây là ví dụ cho **policy thời gian** để minh họa cách kiểm thử ranh giới. Trong ứng dụng thật, nên để thư viện JWT đã được kiểm chứng thực hiện xác minh chữ ký, thuật toán, issuer, audience và claims; cấu hình clock/skew qua API của thư viện nếu có. Không coi riêng class trên là JWT verifier hoàn chỉnh.

### 4.2 Integration test với JWT

Tạo token bằng khóa kiểm thử và thời gian cố định. Không dùng token production hoặc bí mật thật trong test. Bộ test cần xác minh:

1. Token có chữ ký hợp lệ, đúng issuer/audience và `exp` còn hạn được chấp nhận.
2. Token có chữ ký hợp lệ nhưng `exp` đã qua bị từ chối.
3. Token có `exp` đúng bằng thời gian hiện tại bị từ chối khi skew bằng 0.
4. Token thiếu `exp` bị từ chối nếu profile access token yêu cầu claim này.
5. Token có `exp` bị sửa sau khi ký không được chấp nhận; thay đổi payload mà không ký lại phải làm chữ ký thất bại.
6. Token có `nbf` ở tương lai bị từ chối theo policy, dù `exp` còn ở tương lai.
7. Token hết hạn không kích hoạt nghiệp vụ được bảo vệ, ví dụ không tạo đơn hàng hoặc không cập nhật dữ liệu.

Để tách nguyên nhân lỗi, nên có test riêng cho token hết hạn, chữ ký sai, issuer sai, audience sai, token bị thu hồi và scope không đủ. Nếu gộp mọi trường hợp vào một test, kết quả fail không chỉ ra được expiration validator có hoạt động đúng hay không.

### 4.3 Integration test với opaque token

Thiết lập introspection server giả lập hoặc test authorization server:

- Trước thời hạn: trả `active: true` và thông tin token theo contract.
- Sau thời hạn: trả `active: false`.
- Resource server nhận `active: false`: từ chối request được bảo vệ.
- Introspection timeout hoặc lỗi kết nối: xử lý theo chính sách fail-closed phù hợp với dữ liệu nhạy cảm; không tự suy diễn token vẫn active.
- Cache: thời gian cache dương không được vượt quá thời gian còn lại của token, cộng/trừ theo chính sách được xác định rõ. Sau expiration, cache không được tiếp tục trả `active: true`.

Ví dụ kiểm tra cache: token còn 10 giây nhưng cache được cấu hình TTL 60 giây. Nếu hệ thống giữ kết quả active đủ 60 giây, có thể có 50 giây truy cập vượt hạn. Test phải bắt được lỗi này.

### 4.4 Kiểm thử refresh token hết hạn

Gọi token endpoint với refresh token đã hết hạn hoặc đã bị vô hiệu hóa. Authorization server không được cấp access token mới. Theo OAuth 2.0, yêu cầu refresh không hợp lệ có thể nhận lỗi `invalid_grant`; response không nên tiết lộ chi tiết nhạy cảm về trạng thái tài khoản hoặc token.

Nếu hệ thống có refresh token rotation, cần kiểm thử riêng:

- Refresh token cũ đã được dùng và bị thay thế không thể tiếp tục dùng theo policy rotation.
- Refresh token hết hạn không được kéo dài bằng cách gửi lại yêu cầu refresh.
- Refresh token bị thu hồi không được đổi thành access token mới.
- Refresh token hợp lệ tạo access token mới theo scope/resource đã được cho phép.

Không áp dụng thời hạn access token lên refresh token hoặc ngược lại. Mỗi loại phải được kiểm tra theo trạng thái và policy của authorization server.

## 5. Kiểm tra phản hồi HTTP khi access token hết hạn

Với Bearer access token, resource server thường trả `401 Unauthorized` khi token hết hạn hoặc không hợp lệ. Theo RFC 6750, header `WWW-Authenticate` có thể chỉ ra lỗi `invalid_token`.

Ví dụ:

~~~http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer error="invalid_token"
Content-Type: application/json

{
  "error": "unauthorized"
}
~~~

Không trả `403 insufficient_scope` cho một token hết hạn. `insufficient_scope` mô tả trường hợp token hợp lệ nhưng quyền/scope không đủ; token hết hạn là vấn đề xác thực tính hợp lệ của credential.

Trong integration test, đừng chỉ assert status code. Hãy xác minh:

- Header xác thực phù hợp với contract.
- Response không chứa token, chữ ký, claims nhạy cảm hoặc thông tin nội bộ.
- Controller/service không thực hiện side effect.
- Log/metric có thể phân loại lỗi expiration nhưng không ghi raw bearer token.
- Client không lặp request vô hạn với cùng token đã hết hạn; luồng refresh/re-authentication tuân theo thiết kế client.

## 6. Các lỗi thời gian và cấu hình cần chủ động tìm

| Lỗi | Biểu hiện | Cách kiểm thử/phát hiện |
| --- | --- | --- |
| Nhầm giây và mili giây | Token bị coi là hết hạn ngay hoặc sống lâu bất thường | Kiểm tra NumericDate được chuyển bằng giây, ví dụ `Instant.ofEpochSecond(exp)` |
| So sánh sai biên | Token vẫn hợp lệ đúng tại `exp` khi không có skew | Test `now == exp` |
| Clock skew quá lớn | Token đã hết hạn lâu vẫn được chấp nhận | Kiểm thử đúng cuối cửa sổ skew và xác minh cấu hình production |
| Máy chủ lệch giờ | Một node chấp nhận, node khác từ chối cùng token | Integration test nhiều node với clock lệch có kiểm soát |
| Cache quá hạn | Token hết hạn nhưng gateway vẫn dùng kết quả xác thực cũ | Test cache TTL so với thời gian còn lại |
| Chỉ kiểm tra lúc đăng nhập | Session/API tiếp tục dùng token sau expiration | Gọi API sau khi đồng hồ tiến qua `exp` |
| Tin claim chưa xác minh | Client tự sửa `exp` để kéo dài token | Sửa payload mà không ký lại và xác minh bị từ chối |
| Bỏ qua claim thiếu | Token không có `exp` vẫn được chấp nhận dù profile yêu cầu | Test missing claim |
| Dùng `iat` thay cho `exp` | Token cũ bị xử lý sai hoặc token không có giới hạn tuổi | Test độc lập từng claim |
| Retry không giới hạn | Client gửi lặp token đã hết hạn gây tải lớn | Kiểm thử client retry và quan sát request count |

Để kiểm thử lệch giờ, có thể cấu hình hai `Clock` trong môi trường test: issuer nhanh hơn resource server 30 giây và issuer chậm hơn resource server 30 giây. Kiểm tra kết quả theo clock skew được thống nhất. Trong production, đồng bộ thời gian giữa máy chủ bằng hạ tầng thời gian đáng tin cậy và cảnh báo khi độ lệch vượt ngưỡng.

## 7. Quy trình xây dựng test suite

Một test suite thực tế có thể triển khai theo thứ tự:

1. **Xác định contract:** loại token, issuer, audience, claim bắt buộc, TTL, clock skew và cách xử lý refresh/revocation.
2. **Tạo fixture thời gian:** một thời điểm cố định UTC; tạo token trước hạn, tại hạn và sau hạn.
3. **Unit test:** kiểm tra policy expiration và các ranh giới bằng đồng hồ giả lập.
4. **JWT integration test:** ký token bằng test key, gửi tới resource server thật trong môi trường test.
5. **Opaque integration test:** giả lập hoặc chạy introspection server, kiểm tra `active` và cache.
6. **Refresh flow test:** xác minh refresh token hết hạn/thu hồi không thể cấp access token mới.
7. **HTTP behavior test:** xác minh 401, challenge header, không có side effect và không lộ dữ liệu.
8. **Regression test:** giữ lại test cho lỗi từng gặp như sai đơn vị thời gian, lệch đồng hồ và cache quá hạn.

Không cần chờ token hết hạn bằng `Thread.sleep()`. Hãy tiêm `Clock`, dùng test fixture có thời gian xác định hoặc điều khiển thời gian trong test server. Sleep làm test chậm, dễ flaky và không kiểm tra chính xác được ranh giới `exp`.

## 8. Ví dụ tình huống thực tế

Một API Gateway xác thực JWT rồi cache kết quả xác minh trong 5 phút. Access token chỉ sống 2 phút. Người dùng gửi request tại giây thứ 30 sau khi token được phát hành; gateway xác minh thành công và cache kết quả trong 5 phút. Đến phút thứ 3, cùng token vẫn có thể được chấp nhận nếu gateway chỉ đọc cache và không kiểm tra expiration tại mỗi request.

Test hồi quy nên:

- Đặt `exp` tại `T + 120 giây`.
- Gửi request tại `T + 30 giây`, xác minh request được chấp nhận.
- Tiến clock tới `T + 121 giây` nhưng vẫn trong thời gian cache ban đầu.
- Gửi lại cùng token và xác minh gateway trả 401.
- Xác minh nghiệp vụ không chạy ở request thứ hai.

Giải pháp có thể là giới hạn TTL cache theo thời gian còn lại của token, kiểm tra expiration ở mỗi lần dùng token hoặc kết hợp cả hai. Cache không được biến một quyết định xác thực đúng tại thời điểm trước thành quyền truy cập kéo dài sau expiration.

## 9. Checklist trước khi phát hành

- [ ] Đã xác định `exp` có bắt buộc với loại access token đang dùng hay không.
- [ ] Đã kiểm thử token trước hạn, đúng hạn và sau hạn.
- [ ] Đã kiểm thử clock skew ở cả hai phía của ranh giới.
- [ ] Đã xác minh NumericDate dùng đơn vị giây và UTC.
- [ ] Đã kiểm thử token thiếu `exp`, sai chữ ký, sai issuer và sai audience độc lập.
- [ ] Đã kiểm thử opaque token qua introspection và cache.
- [ ] Đã kiểm thử refresh token hết hạn/thu hồi không thể cấp token mới.
- [ ] API từ chối token hết hạn bằng phản hồi phù hợp và không thực hiện side effect.
- [ ] Client không retry vô hạn với token hết hạn.
- [ ] Log và metric hỗ trợ điều tra nhưng không chứa raw token hoặc bí mật.

## Ghi nhớ

Expiration là một điều kiện an ninh được kiểm tra tại **thời điểm sử dụng token**. Với JWT, verifier so sánh thời gian hiện tại với `exp` đã được xác minh; với opaque token, resource server dựa trên trạng thái tin cậy như introspection. Kiểm thử tốt phải bao phủ ranh giới thời gian, clock skew, cache, refresh flow và phản hồi HTTP. Dùng đồng hồ giả lập giúp test nhanh, chính xác và ổn định.

### Tài liệu tham khảo

- IETF RFC 7519 — *JSON Web Token (JWT)*, đặc biệt các mục NumericDate và `exp`: https://www.rfc-editor.org/rfc/rfc7519
- IETF RFC 6749 — *The OAuth 2.0 Authorization Framework*, refresh token và lỗi token endpoint: https://www.rfc-editor.org/rfc/rfc6749
- IETF RFC 6750 — *The OAuth 2.0 Authorization Framework: Bearer Token Usage*, `invalid_token` và `insufficient_scope`: https://www.rfc-editor.org/rfc/rfc6750
- IETF RFC 7662 — *OAuth 2.0 Token Introspection*, trường `active`: https://www.rfc-editor.org/rfc/rfc7662
- OpenID Connect Core 1.0 — ID Token validation và claim `exp`: https://openid.net/specs/openid-connect-core-1_0.html
