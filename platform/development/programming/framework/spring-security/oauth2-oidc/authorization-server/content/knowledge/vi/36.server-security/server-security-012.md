# Chính sách khi tài khoản bị khóa, credential bị lộ hoặc phiên bị xâm phạm

Authorization Server phải xử lý được ba tình huống thường bị gộp chung: tài khoản không còn được phép đăng nhập, thông tin xác thực đã bị lộ và một phiên đăng nhập đang bị người khác sử dụng. Mỗi tình huống tác động đến một lớp khác nhau. Khóa tài khoản ngăn xác thực mới; thu hồi authorization grant làm mất hiệu lực token được phát hành từ grant đó; hủy phiên làm mất trạng thái đăng nhập của trình duyệt. Thực hiện một thao tác không tự động hoàn tất hai thao tác còn lại.

Bài học này xây dựng chính sách xử lý sự cố cho ứng dụng Spring Boot dùng Spring Security và Spring Authorization Server. Ví dụ tập trung vào người dùng cuối đăng nhập bằng Authorization Code và OpenID Connect. Với client credentials, service account hoặc khóa ký của máy chủ, cần áp dụng chính sách riêng theo loại credential.

## 1. Phân biệt các trạng thái bảo mật

Trước khi viết code, cần xác định tài nguyên nào đang được bảo vệ và thao tác nào làm thay đổi trạng thái của nó.

| Thành phần | Ví dụ | Cách kiểm soát |
|---|---|---|
| Tài khoản | ACTIVE, LOCKED, DISABLED | Trạng thái trong kho người dùng; kiểm tra khi xác thực |
| Credential | Mật khẩu, passkey, mã khôi phục, client secret | Thu hồi hoặc thay thế credential; kiểm tra lại danh tính |
| Phiên đăng nhập | Cookie phiên SSO, HttpSession, session lưu trong Spring Session | Hết hạn hoặc xóa phiên ở kho lưu trữ |
| Authorization grant | Quyền một người dùng đã cấp cho một client | Xóa hoặc đánh dấu authorization không còn hiệu lực |
| Access token | JWT hoặc reference token | Thu hồi, introspection, denylist hoặc chờ hết hạn theo chính sách |
| Refresh token | Credential dùng để xin access token mới | Thu hồi và phát hiện việc sử dụng lại token đã xoay vòng |
| Khóa ký | Private key ký access token hoặc ID Token | Xoay khóa, loại bỏ khóa bị lộ khỏi tập khóa được tin cậy |

Một người dùng có thể bị khóa trong cơ sở dữ liệu nhưng vẫn đang giữ cookie SSO hợp lệ. Một refresh token có thể vẫn dùng được sau khi mật khẩu đã được đổi nếu ứng dụng không thu hồi grant cũ. Một JWT đã ký có thể tiếp tục được Resource Server chấp nhận dù Authorization Server đã xóa bản ghi authorization, nếu Resource Server chỉ xác minh chữ ký và thời hạn của JWT.

Do đó, chính sách cần xác định rõ phạm vi tác động:

- **Ngăn xác thực mới:** tài khoản bị khóa hoặc vô hiệu hóa.
- **Ngăn cấp token mới:** từ chối authorization request và refresh grant khi tài khoản không đủ điều kiện.
- **Kết thúc phiên:** hủy phiên SSO và các phiên ứng dụng liên quan.
- **Thu hồi quyền đã cấp:** vô hiệu hóa authorization grant, refresh token và access token theo chiến lược token.
- **Khôi phục an toàn:** xác minh người dùng, thay credential và yêu cầu xác thực lại.

## 2. Chính sách khóa tài khoản

### 2.1. Phân biệt khóa tạm thời và khóa do sự cố

Không nên biểu diễn mọi tình huống bằng một cờ boolean duy nhất. Một mô hình tài khoản nên lưu tối thiểu trạng thái, lý do khóa và thời điểm khóa:

| Trường | Ý nghĩa |
|---|---|
| `status` | Trạng thái tài khoản như ACTIVE, LOCKED hoặc DISABLED |
| `lockReason` | FAILED_ATTEMPTS, SUSPECTED_COMPROMISE hoặc ADMINISTRATIVE |
| `lockedAt` | Thời điểm bắt đầu khóa |
| `lockedUntil` | Thời điểm tự động mở khóa; null có thể biểu thị khóa cần người có thẩm quyền xử lý |
| `failedAttempts` | Số lần xác thực thất bại trong cửa sổ theo dõi |
| `securityVersion` | Phiên bản bảo mật tăng sau sự cố hoặc thay đổi credential |
| `passwordChangedAt` | Thời điểm thay mật khẩu gần nhất |

Khóa do nhập sai mật khẩu nhiều lần thường là khóa tạm thời. Khóa do phát hiện credential bị lộ cần giữ nguyên cho đến khi hoàn thành xác minh và khôi phục. Không tự động mở khóa một tài khoản đang được điều tra chỉ vì hết thời gian khóa tạm thời.

### 2.2. Kết nối trạng thái tài khoản với Spring Security

Spring Security biểu diễn các điều kiện cơ bản của người dùng qua `UserDetails`, gồm `isAccountNonLocked()`, `isEnabled()` và `isCredentialsNonExpired()`. Các phương thức mặc định có thể trả về `true`; vì vậy, implementation lấy dữ liệu từ cơ sở dữ liệu phải ánh xạ đúng trạng thái thực tế.

Ví dụ rút gọn:

```java
public final class AccountPrincipal implements UserDetails {

    private final Account account;

    public AccountPrincipal(Account account) {
        this.account = account;
    }

    @Override
    public String getUsername() {
        return account.username();
    }

    @Override
    public String getPassword() {
        return account.passwordHash();
    }

    @Override
    public boolean isAccountNonLocked() {
        return !account.isLocked();
    }

    @Override
    public boolean isEnabled() {
        return account.isEnabled();
    }

    @Override
    public boolean isCredentialsNonExpired() {
        return !account.areCredentialsExpired();
    }

    // Triển khai getAuthorities() theo quyền của ứng dụng.
}
```

`account.isLocked()` cần áp dụng đúng quy tắc thời hạn khóa. Nếu khóa tạm đã hết hạn, service nên cập nhật trạng thái theo một giao dịch có kiểm soát trước khi cho phép đăng nhập. Không nên để một cờ `locked` hết hạn trong bộ nhớ nhưng vẫn còn LOCKED trong cơ sở dữ liệu.

Khi dùng `DaoAuthenticationProvider` với `UserDetailsService`, trạng thái tài khoản được Spring Security kiểm tra trong quá trình xác thực. Nếu ứng dụng dùng authentication provider tùy chỉnh, cần tự bảo đảm các điều kiện khóa, vô hiệu hóa và hết hạn credential được kiểm tra tương đương. Tham khảo [API UserDetails của Spring Security](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/core/userdetails/UserDetails.html).

### 2.3. Chống brute force mà không tạo cơ hội từ chối dịch vụ

Khóa tài khoản sau nhiều lần nhập sai giúp hạn chế dò mật khẩu, nhưng chỉ dựa vào số lần sai theo username có thể bị lạm dụng để khóa tài khoản của nạn nhân. Nên kết hợp:

- Giới hạn tốc độ theo nhiều chiều: tài khoản, địa chỉ mạng, thiết bị hoặc client; không dựa duy nhất vào IP.
- Tăng dần thời gian chờ sau các lần thất bại liên tiếp.
- Dùng CAPTCHA hoặc bước xác minh bổ sung khi tín hiệu rủi ro tăng.
- Dùng thông báo đăng nhập thất bại chung, tránh tiết lộ username có tồn tại hoặc tài khoản đang bị khóa vì lý do nào.
- Ghi nhận sự kiện và cảnh báo khi có nhiều tài khoản bị thử đăng nhập từ cùng nguồn.
- Chỉ reset bộ đếm theo chính sách sau một lần xác thực thành công hoặc quy trình khôi phục đã xác minh.

Việc tăng bộ đếm phải an toàn khi có nhiều request đồng thời. Dùng cập nhật nguyên tử hoặc khóa hàng trong cơ sở dữ liệu để tránh hai request cùng đọc một giá trị rồi ghi đè kết quả của nhau.

### 2.4. Khóa tài khoản không tự thu hồi phiên và token

Khi tài khoản chuyển sang LOCKED, Spring Security sẽ từ chối lần xác thực mới nếu trạng thái được ánh xạ đúng. Tuy nhiên, trạng thái này không tự xóa một `SecurityContext` đã được lưu trong HttpSession và cũng không tự làm mất hiệu lực access token đã phát hành.

Cần quy định theo nguyên nhân:

- Khóa tạm do nhập sai mật khẩu: có thể chỉ chặn đăng nhập mới, đồng thời theo dõi phiên hiện tại. Nếu phát hiện thêm tín hiệu chiếm quyền, chuyển sang quy trình sự cố và thu hồi phiên/token.
- Khóa do nghi ngờ credential bị lộ: khóa tài khoản, hủy các phiên và thu hồi các grant của người dùng.
- Khóa hành chính hoặc vô hiệu hóa vĩnh viễn: chặn xác thực mới và áp dụng chính sách thu hồi quyền đã cấp tương ứng với yêu cầu quản trị.

Khi dùng refresh token, cần bảo đảm refresh grant cũng kiểm tra trạng thái tài khoản hoặc authorization đã bị thu hồi. Không giả định rằng việc kiểm tra `UserDetails` ở lần đăng nhập đầu tiên sẽ tự chạy lại ở mọi lần refresh. Spring Authorization Server cho phép tùy chỉnh các provider ở token endpoint qua `OAuth2TokenEndpointConfigurer.authenticationProviders(...)`; có thể dùng extension point này để bổ sung kiểm tra trạng thái tài khoản và `securityVersion` trước khi phát hành token mới.

## 3. Xử lý khi credential bị lộ

### 3.1. Xác định credential nào bị ảnh hưởng

“Credential bị lộ” có thể là nhiều loại bí mật khác nhau. Phải xác định loại credential trước khi chọn hành động.

| Credential bị lộ | Hành động ưu tiên |
|---|---|
| Mật khẩu người dùng | Khóa hoặc đặt trạng thái cần khôi phục; đặt lại mật khẩu; thu hồi phiên và grant theo chính sách |
| Passkey hoặc khóa xác thực thiết bị | Thu hồi credential bị ảnh hưởng; yêu cầu đăng ký lại sau khi xác minh |
| Mã khôi phục hoặc mã MFA dự phòng | Vô hiệu hóa các mã còn lại cùng bộ; cấp bộ mới sau xác minh |
| Refresh token | Thu hồi authorization grant chứa token; kiểm tra dấu hiệu replay và các access token liên quan |
| Access token | Thu hồi token hoặc grant; đánh giá thời hạn còn lại và khả năng Resource Server kiểm tra trạng thái |
| Client secret | Vô hiệu hóa hoặc xoay secret của client; thu hồi authorization được phát hành cho client nếu có nguy cơ |
| Private signing key | Xoay khóa ký khẩn cấp; loại khóa bị lộ khỏi tập khóa được chấp nhận; xử lý cache khóa và token đã ký bằng khóa cũ |

Credential của client hoặc khóa ký của Authorization Server có phạm vi ảnh hưởng lớn hơn một tài khoản người dùng. Không xử lý sự cố client secret bằng cách chỉ khóa user sở hữu client đó. Với private signing key bị lộ, cần phối hợp cập nhật JWKS, `kid`, cache của Resource Server và chính sách chấp nhận token cũ.

### 3.2. Quy trình xử lý mật khẩu bị lộ

Một quy trình khôi phục nên thực hiện theo thứ tự sau:

1. Đánh dấu tài khoản cần xử lý sự cố và ngăn xác thực mới.
2. Xác minh người yêu cầu khôi phục bằng kênh độc lập, chẳng hạn MFA hoặc quy trình hỗ trợ có kiểm tra danh tính.
3. Thu hồi các phiên SSO và authorization grant hiện có theo mức độ sự cố.
4. Yêu cầu đặt mật khẩu mới; kiểm tra chính sách mật khẩu và chặn mật khẩu đã biết là bị lộ nếu hệ thống có nguồn kiểm tra phù hợp.
5. Thu hồi hoặc thay các mã khôi phục, thiết bị tin cậy và credential phụ có thể đã bị lộ.
6. Tăng `securityVersion`, ghi audit event và yêu cầu đăng nhập lại trên các thiết bị.
7. Theo dõi các lần refresh thất bại, lần đăng nhập từ thiết bị mới và hành vi bất thường sau khi khôi phục.

Mật khẩu chỉ được lưu dưới dạng hash thích hợp. Với Spring Security, có thể dùng `PasswordEncoderFactories.createDelegatingPasswordEncoder()` để tạo `DelegatingPasswordEncoder`; cơ chế này lưu định danh encoder cùng hash và hỗ trợ nâng cấp thuật toán theo thời gian.

```java
@Bean
PasswordEncoder passwordEncoder() {
    return PasswordEncoderFactories.createDelegatingPasswordEncoder();
}
```

Không mã hóa thuận nghịch mật khẩu để có thể khôi phục plaintext. Không ghi mật khẩu, token, mã MFA, cookie phiên hoặc header Authorization vào log. Xem [Password Storage của Spring Security](https://docs.spring.io/spring-security/reference/features/authentication/password-storage.html).

### 3.3. Xoay refresh token và giảm nguy cơ replay

Refresh token có giá trị cao vì có thể dùng để xin access token mới. Với public client, [RFC 9700](https://www.rfc-editor.org/rfc/rfc9700.html) yêu cầu Authorization Server phát hiện replay bằng sender-constrained refresh token hoặc refresh token rotation. Khi xoay vòng, mỗi lần refresh phát hành token mới và vô hiệu hóa token cũ; nếu token cũ xuất hiện lần nữa, server có tín hiệu về khả năng token đã bị sao chép.

Trong Spring Authorization Server, có thể cấu hình không tái sử dụng refresh token:

```java
TokenSettings tokenSettings = TokenSettings.builder()
    .reuseRefreshTokens(false)
    .build();
```

Đặt thời hạn access token ngắn phù hợp với rủi ro, giới hạn scope và audience, đồng thời bảo vệ refresh token khi truyền và lưu trữ. RFC 9700 cũng khuyến nghị access token sender-constrained, chẳng hạn DPoP hoặc mutual TLS, để giảm khả năng sử dụng token bị đánh cắp.

## 4. Thu hồi authorization grant và OAuth token

### 4.1. Dùng Token Revocation Endpoint

[RFC 7009](https://www.rfc-editor.org/rfc/rfc7009.html) định nghĩa OAuth 2.0 Token Revocation. Client gửi HTTP POST đến revocation endpoint, xác thực client theo cấu hình và gửi token cần thu hồi. Authorization Server xác minh token thuộc client gửi yêu cầu rồi vô hiệu hóa token. RFC yêu cầu hỗ trợ thu hồi refresh token và khuyến nghị hỗ trợ access token. Khi refresh token bị thu hồi, nếu server hỗ trợ thu hồi access token thì nên thu hồi cả access token phát sinh từ cùng grant.

Spring Authorization Server cung cấp `OAuth2TokenRevocationEndpointConfigurer` để cấu hình endpoint và các extension point cho converter, provider và response handler. Endpoint chuẩn nên được dùng cho client thu hồi token của chính nó. Với hành động quản trị như khóa người dùng hoặc xử lý sự cố, gọi service nội bộ có quyền phù hợp để thu hồi các authorization của principal; không giả lập một client bên ngoài.

Ví dụ request theo RFC 7009:

```http
POST <revocation_endpoint>
Content-Type: application/x-www-form-urlencoded
Authorization: Basic <client-credentials>

token=<refresh-token>&token_type_hint=refresh_token
```

Lấy URL endpoint từ Authorization Server Metadata hoặc cấu hình đã công bố, không hard-code URL tùy tiện. Phản hồi thành công của revocation endpoint không có nghĩa client được phép tiếp tục dùng token; client phải loại bỏ token khỏi nơi lưu trữ của mình.

### 4.2. Thu hồi authorization trong Spring Authorization Server

`OAuth2Authorization` đại diện cho một authorization grant và liên kết các token được phát hành trong grant đó. `OAuth2AuthorizationService` là thành phần lưu và truy vấn các authorization; interface cung cấp `findByToken`, `findById`, `save` và `remove`.

Ví dụ thu hồi toàn bộ grant được tìm thấy từ một refresh token đã bị lộ:

```java
@Service
public class AuthorizationRevocationService {

    private final OAuth2AuthorizationService authorizationService;

    public AuthorizationRevocationService(
            OAuth2AuthorizationService authorizationService) {
        this.authorizationService = authorizationService;
    }

    public void revokeGrantByRefreshToken(String refreshToken) {
        OAuth2Authorization authorization = authorizationService.findByToken(
            refreshToken,
            OAuth2TokenType.REFRESH_TOKEN
        );

        if (authorization != null) {
            // Xóa authorization làm mất bản ghi của grant và các token gắn với nó.
            authorizationService.remove(authorization);
        }
    }
}
```

Đối với sự cố của một người dùng, thường phải thu hồi nhiều grant được cấp cho nhiều client. `OAuth2AuthorizationService` không cung cấp truy vấn tất cả authorization theo `principalName`. Ứng dụng nên duy trì index/repository riêng theo principal, hoặc triển khai service lưu authorization có truy vấn phù hợp. Khi lưu authorization, index theo `OAuth2Authorization.getPrincipalName()`; khi xóa authorization, cập nhật index trong cùng ranh giới giao dịch. Sau đó, quy trình thu hồi có thể lấy các authorization ID của principal, gọi `findById` và `remove` từng bản ghi.

Không dùng `InMemoryOAuth2AuthorizationService` làm kho production cho hệ thống nhiều instance hoặc cần dữ liệu bền vững. Spring Authorization Server cung cấp `JdbcOAuth2AuthorizationService`; có thể dùng implementation JDBC hoặc một implementation lưu trữ bền vững phù hợp với kiến trúc. Xem [Core Model / Components](https://docs.spring.io/spring-authorization-server/reference/core-model-components.html) và [Protocol Endpoints](https://docs.spring.io/spring-authorization-server/reference/protocol-endpoints.html).

### 4.3. JWT và giới hạn của thu hồi tức thời

Cần chọn cách xác minh token dựa trên yêu cầu thu hồi:

| Cách xác minh | Khi grant bị thu hồi | Đánh đổi |
|---|---|---|
| Reference/opaque token + introspection | Resource Server có thể thấy token không còn active khi introspection đọc được trạng thái mới | Có chi phí gọi mạng; cache introspection tạo độ trễ thu hồi |
| JWT tự chứa, chỉ kiểm tra chữ ký và exp | JWT đã phát hành có thể tiếp tục hợp lệ đến khi hết hạn | Xác minh nhanh, ít phụ thuộc Authorization Server |
| JWT + denylist theo `jti` | Resource Server từ chối token có `jti` trong denylist | Phải chia sẻ trạng thái thu hồi và dọn entry khi token hết hạn |
| JWT + kiểm tra `securityVersion` | Resource Server từ chối token có phiên bản cũ | Cần tra cứu hoặc cache phiên bản tài khoản khi xử lý request |

Nếu yêu cầu thu hồi access token ngay khi có sự cố, chỉ xóa bản ghi authorization trong database là chưa đủ đối với Resource Server đang xác minh JWT hoàn toàn offline. Cần triển khai denylist hoặc kiểm tra phiên bản bảo mật ở Resource Server, hoặc dùng reference token với introspection. Với introspection, [RFC 7662](https://www.rfc-editor.org/rfc/rfc7662.html) định nghĩa trường `active`; token đã hết hạn, bị thu hồi hoặc không hợp lệ với resource server thường phải được trả về là inactive. Thời gian cache phải ngắn tương ứng với độ trễ thu hồi mà hệ thống chấp nhận.

Nếu chọn JWT offline, đặt access token TTL ngắn và giới hạn scope/audience để giảm thiệt hại khi token bị lộ. Ghi rõ trong chính sách rằng JWT có thể còn được chấp nhận đến `exp` nếu không có cơ chế kiểm tra thu hồi. Không quảng bá “logout tức thời” khi Resource Server không có đường nhận trạng thái thu hồi.

## 5. Xử lý khi phiên đăng nhập bị xâm phạm

### 5.1. Phiên trình duyệt và token là hai loại trạng thái khác nhau

Phiên SSO của Authorization Server thường được giữ bằng HttpSession hoặc kho phiên dùng chung. Một ứng dụng client có thể đồng thời có phiên đăng nhập riêng. Access token và refresh token lại có vòng đời độc lập. Vì vậy, “đăng xuất khỏi Authorization Server” không tự bảo đảm mọi client đã xóa session riêng hoặc mọi Resource Server đã từ chối access token.

Khi xác nhận một phiên bị xâm phạm:

- Xác định session ID, principal, client, thời điểm và các authorization liên quan.
- Đánh dấu phiên bị xâm phạm và kết thúc phiên tại kho lưu trữ phiên.
- Thu hồi refresh token/grant gắn với phiên hoặc principal theo phạm vi sự cố.
- Thu hồi access token nếu chiến lược token cho phép; nếu dùng JWT offline, áp dụng denylist/version check hoặc chờ TTL theo kế hoạch ứng phó.
- Yêu cầu xác thực lại và MFA trước khi tạo phiên mới.
- Thông báo cho người dùng qua kênh đã xác minh và ghi lại sự kiện kiểm toán.

Không dùng địa chỉ IP đơn lẻ làm bằng chứng duy nhất để kết luận một phiên bị đánh cắp. Thiết bị, user-agent, vị trí tương đối, thời gian, thay đổi credential và hành vi truy cập nên được đánh giá cùng nhau.

### 5.2. Quản lý HttpSession bằng Spring Security

Spring Security hỗ trợ theo dõi phiên qua `SessionRegistry` và kiểm soát số phiên đồng thời. Cấu hình concurrent-session support thường đăng ký `HttpSessionEventPublisher` và đặt giới hạn phiên trong `sessionManagement`:

```java
@Bean
HttpSessionEventPublisher httpSessionEventPublisher() {
    return new HttpSessionEventPublisher();
}

@Bean
SecurityFilterChain applicationSecurity(HttpSecurity http) throws Exception {
    http.sessionManagement(session ->
        session.maximumSessions(5)
    );
    return http.build();
}
```

Con số 5 chỉ là ví dụ; chọn giới hạn theo mô hình sử dụng của ứng dụng. Khi cần hết hạn các phiên của một principal đã được xác định, có thể đánh dấu chúng hết hạn qua `SessionRegistry`:

```java
public void expireSessions(
        SessionRegistry sessionRegistry,
        Object principal) {

    sessionRegistry.getAllSessions(principal, false)
        .forEach(SessionInformation::expireNow);
}
```

`expireNow()` đánh dấu phiên cần kết thúc. Filter quản lý phiên của Spring Security sẽ xử lý phiên hết hạn khi request tiếp theo đi qua ứng dụng. Nếu yêu cầu phải xóa session ngay cả khi phiên không gửi thêm request, dùng API xóa session của kho phiên thực tế, chẳng hạn kho Spring Session dùng chung, và xác minh session ID đã biến mất.

`SessionRegistryImpl` mặc định giữ dữ liệu trong bộ nhớ của một instance. Với nhiều node, cần giải pháp session registry/kho phiên dùng chung hoặc cơ chế phát sự kiện thu hồi đến tất cả node. Nếu dùng custom `UserDetails`, triển khai `equals()` và `hashCode()` ổn định để SessionRegistry nhận diện đúng principal. Tham khảo [Authentication Persistence and Session Management](https://docs.spring.io/spring-security/reference/servlet/authentication/session-management.html).

### 5.3. OpenID Connect logout

Spring Authorization Server có thể bật OIDC và cấu hình `OidcLogoutEndpointConfigurer` cho RP-Initiated Logout:

```java
authorizationServer.oidc(oidc ->
    oidc.logoutEndpoint(Customizer.withDefaults())
);
```

Endpoint này xử lý yêu cầu logout từ Relying Party. Provider mặc định dùng `SessionRegistry` để tìm thông tin phiên của End-User. Với client dùng Spring Security OAuth2 Client, `OidcClientInitiatedLogoutSuccessHandler` hỗ trợ khởi tạo RP-Initiated Logout.

Theo [OpenID Connect RP-Initiated Logout 1.0](https://openid.net/specs/openid-connect-rpinitiated-1_0-final.html), Authorization Server phải xác minh `id_token_hint` nếu được gửi và chỉ chuyển hướng đến `post_logout_redirect_uri` đã đăng ký chính xác. Không chấp nhận redirect URL tùy ý do request cung cấp.

RP-Initiated Logout, Front-Channel Logout và Back-Channel Logout là các cơ chế liên quan nhưng có mục đích riêng. RP-Initiated Logout yêu cầu OP kết thúc phiên; Front-Channel/Back-Channel Logout truyền thông báo logout từ OP đến các RP. Muốn kết thúc session cục bộ tại từng client, các RP phải hỗ trợ và xử lý cơ chế logout tương ứng. Logout OIDC cũng không thay thế việc thu hồi OAuth authorization grant khi chính sách sự cố yêu cầu thu hồi token.

## 6. Bảng quyết định theo loại sự cố

| Sự cố | Tài khoản | Phiên SSO | Authorization grant/token | Điều kiện khôi phục |
|---|---|---|---|---|
| Nhập sai mật khẩu vượt ngưỡng | Khóa tạm, giới hạn thử lại | Theo dõi; chỉ hủy nếu có tín hiệu chiếm quyền | Thường giữ nguyên nếu chưa có dấu hiệu compromise | Hết thời gian khóa hoặc xác minh bổ sung |
| Nghi ngờ mật khẩu bị lộ | Khóa hoặc đặt trạng thái cần xác minh | Hủy tất cả phiên người dùng | Thu hồi grant và refresh token; xử lý access token theo kiểu token | Đặt mật khẩu mới, kiểm tra MFA và credential phụ |
| Refresh token bị replay | Có thể khóa tài khoản tùy mức độ | Hủy phiên liên quan hoặc toàn bộ phiên | Thu hồi grant chứa refresh token và các token liên quan | Xác thực lại và cấp grant mới |
| Cookie/session bị đánh cắp | Có thể giữ ACTIVE nếu chỉ một phiên bị ảnh hưởng; khóa nếu phạm vi rộng | Hủy session ID bị ảnh hưởng | Thu hồi token gắn với phiên; mở rộng nếu không xác định được phạm vi | MFA và tạo phiên mới |
| Client secret bị lộ | Không nhất thiết khóa user | Không nhất thiết hủy phiên user | Vô hiệu hóa/đổi secret và thu hồi grant của client | Cập nhật secret ở client và xác minh kết nối |
| Private signing key bị lộ | Không nhất thiết khóa mọi user | Đánh giá theo phạm vi | Xoay khóa, loại `kid` bị lộ khỏi tập được chấp nhận và xử lý token cũ | Resource Server đã nhận chính sách khóa mới |

Bảng này là baseline. Tổ chức cần quy định ai được quyền khóa/mở khóa, ai được phép thu hồi grant, mức sự cố nào yêu cầu thu hồi toàn bộ phiên, và thời gian tối đa để truyền trạng thái thu hồi đến Resource Server.

## 7. Thiết kế luồng xử lý sự cố

Nên gom các thao tác vào một service nghiệp vụ thay vì để controller tự cập nhật nhiều bảng:

```text
SecurityIncidentService
  ├── lockAccount(reason, until)
  ├── revokeBrowserSessions(principal)
  ├── revokeAuthorizations(principal, clientScope)
  ├── rotateOrInvalidateCredentials(principal, credentialType)
  ├── requireReauthentication(principal)
  └── writeAuditEvent(incidentId, actor, target, reason)
```

Luồng xử lý điển hình:

1. **Phân loại:** xác định principal, credential, session, client và token bị ảnh hưởng; gán incident ID.
2. **Ngăn phát sinh quyền mới:** cập nhật trạng thái tài khoản/client và chặn refresh grant theo trạng thái mới.
3. **Thu hồi:** xóa phiên và authorization theo phạm vi đã chọn; phát sự kiện đến các node và Resource Server cần biết.
4. **Thay credential:** đặt lại mật khẩu, thay client secret, mã MFA hoặc khóa ký tùy sự cố.
5. **Khôi phục:** xác minh danh tính, yêu cầu MFA và cấp phiên/grant mới.
6. **Theo dõi:** giám sát refresh token reuse, đăng nhập thất bại, thiết bị mới và request bị từ chối sau thu hồi.

Các thao tác nên idempotent: xử lý lại cùng incident không tạo thêm token, không mở khóa nhầm tài khoản và không làm sống lại phiên đã thu hồi. Với hệ thống nhiều service, dùng transactional outbox hoặc cơ chế phát sự kiện bền vững để trạng thái khóa, thu hồi grant và thông báo đến các node không bị thất lạc khi một service tạm thời không hoạt động.

Audit event nên có incident ID, actor, principal/client đích, loại thao tác, lý do, thời gian, request/correlation ID và kết quả. Không lưu raw password, raw access/refresh token, cookie phiên, client secret hay private key. Nếu cần đối chiếu token, lưu định danh an toàn như hash của token hoặc `jti`, kèm issuer và thời hạn.

## 8. Kiểm thử chính sách

Kiểm thử cả luồng thành công, lỗi và độ trễ lan truyền. Các trường hợp tối thiểu gồm:

- Tài khoản LOCKED không thể hoàn tất đăng nhập bằng mật khẩu đúng.
- Tài khoản DISABLED không thể nhận authorization code mới.
- Tài khoản bị khóa không thể dùng refresh token để nhận access token mới.
- Khóa tạm hết hạn đúng chính sách; khóa do sự cố không tự mở khóa.
- Một refresh token đã bị thu hồi không thể dùng lại; authorization liên quan được xử lý đúng theo chính sách.
- Introspection trả `active=false` cho token đã thu hồi hoặc hết hạn.
- Resource Server dùng JWT offline từ chối token bị thu hồi theo cơ chế denylist/version, hoặc tài liệu vận hành ghi rõ token chỉ hết hiệu lực tại `exp`.
- Phiên đã đánh dấu hết hạn bị từ chối ở request kế tiếp; với session store dùng chung, mọi node đều thấy phiên đã bị xóa.
- OIDC logout từ client hợp lệ kết thúc phiên OP; redirect URI chưa đăng ký bị từ chối.
- Đổi mật khẩu hoặc thay credential làm tăng `securityVersion` và áp dụng đúng phạm vi thu hồi.
- Xử lý lại cùng incident không làm sai trạng thái hoặc phát sinh side effect ngoài dự kiến.

Có thể kiểm thử endpoint với MockMvc và test service với repository giả lập, nhưng các bài kiểm thử tích hợp cần dùng cùng kiểu lưu trữ authorization/session với môi trường triển khai. Đặc biệt, một test chỉ chạy trên `InMemoryOAuth2AuthorizationService` không chứng minh rằng nhiều instance production đã đồng bộ trạng thái thu hồi.

## 9. Checklist vận hành

- [ ] Có chính sách riêng cho khóa tạm, khóa do nghi ngờ compromise và vô hiệu hóa tài khoản.
- [ ] `UserDetails` ánh xạ đúng `isAccountNonLocked()`, `isEnabled()` và `isCredentialsNonExpired()`.
- [ ] Login, authorization request và refresh grant đều kiểm tra trạng thái bảo mật hiện tại.
- [ ] Có quy trình thu hồi session SSO, authorization grant, refresh token và access token.
- [ ] Đã xác định rõ giới hạn thu hồi JWT offline và độ trễ cache introspection.
- [ ] Production dùng kho authorization/session bền vững, đồng bộ giữa các instance.
- [ ] Refresh token rotation hoặc sender-constraining được cấu hình phù hợp với loại client.
- [ ] OIDC logout chỉ chuyển hướng đến URI đã đăng ký và các RP xử lý thông báo logout phù hợp.
- [ ] Credential không xuất hiện trong log, trace, exception hoặc audit event.
- [ ] Có người chịu trách nhiệm phê duyệt mở khóa và xác nhận khôi phục sau sự cố.

## 10. Tài liệu tham khảo

- [Spring Security — UserDetails API](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/core/userdetails/UserDetails.html)
- [Spring Security — Password Storage](https://docs.spring.io/spring-security/reference/features/authentication/password-storage.html)
- [Spring Security — Authentication Persistence and Session Management](https://docs.spring.io/spring-security/reference/servlet/authentication/session-management.html)
- [Spring Authorization Server — Core Model / Components](https://docs.spring.io/spring-authorization-server/reference/core-model-components.html)
- [Spring Authorization Server — Protocol Endpoints](https://docs.spring.io/spring-authorization-server/reference/protocol-endpoints.html)
- [RFC 7009 — OAuth 2.0 Token Revocation](https://www.rfc-editor.org/rfc/rfc7009.html)
- [RFC 7662 — OAuth 2.0 Token Introspection](https://www.rfc-editor.org/rfc/rfc7662.html)
- [RFC 9700 — Best Current Practice for OAuth 2.0 Security](https://www.rfc-editor.org/rfc/rfc9700.html)
- [OpenID Connect RP-Initiated Logout 1.0](https://openid.net/specs/openid-connect-rpinitiated-1_0-final.html)
- [OpenID Connect Back-Channel Logout 1.0](https://openid.net/specs/openid-connect-backchannel-1_0-final.html)

