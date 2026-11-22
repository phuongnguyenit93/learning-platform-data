# Access token khác ID token và refresh token như thế nào?

## 1. Bài toán: đăng nhập rồi gọi REST API

Giả sử cửa hàng có ứng dụng web **Shop Web**, API **Orders API** và máy chủ định danh **Login Server**. Người dùng đăng nhập một lần rồi xem đơn hàng. Hệ thống cần giải quyết ba câu hỏi khác nhau:

1. **Người dùng vừa đăng nhập là ai, tại hệ thống định danh nào?** Ứng dụng khách cần một bằng chứng về lần xác thực: **ID token** (khi dùng OpenID Connect).
2. **Lời gọi API này được phép làm gì, với tài nguyên nào?** Orders API cần một chứng thư ủy quyền dành cho chính nó: **access token**.
3. **Khi quyền truy cập ngắn hạn hết hạn, ứng dụng có thể xin quyền truy cập mới mà không yêu cầu người dùng đăng nhập lại hay không?** Máy chủ cấp quyền có thể phát hành **refresh token**.

Ba token có thể cùng được trả về sau một lần đăng nhập nhưng **không thể dùng thay cho nhau**. Tên token mô tả **vai trò trong giao thức**, không mô tả định dạng: một access token có thể là JWT hoặc chuỗi opaque; ID token trong OpenID Connect là JWT; refresh token thông thường là chuỗi bí mật mà chỉ Authorization Server hiểu.

### Mục tiêu học tập

Sau bài này, người học có thể đọc một phản hồi OAuth 2.0/OpenID Connect, quyết định token nào được gửi đến API nào, giải thích trường **issuer/audience/scope/expiry**, nhận biết các lỗi xác thực và phân quyền, cấu hình một Java/Spring REST Resource Server và thiết kế kiểm thử ngăn lẫn lộn token.

## 2. Bảng phân biệt ba token

| Tiêu chí | Access token | ID token | Refresh token |
|---|---|---|---|
| Mục đích | Cho phép client truy cập Resource Server theo quyền đã cấp | Chứng minh sự kiện xác thực người dùng cho OIDC Client/Relying Party | Xin access token mới từ Authorization Server |
| Bên sử dụng | Resource Server/API | OIDC Client (ứng dụng đăng nhập) | Authorization Server qua token endpoint; client lưu và gửi lại |
| Đối tượng nhận (audience) | API/tài nguyên được bảo vệ, ví dụ **orders-api** nếu dùng JWT có aud | OIDC client, ví dụ **shop-web** | Thường không công khai cho API; máy chủ cấp quyền kiểm tra ràng buộc client/phiên |
| Định dạng | JWT hoặc opaque, tùy nhà cung cấp và cấu hình | JWT được ký, có thể được mã hóa thêm | Thường là opaque, có thể có cấu trúc nội bộ |
| Thời hạn | Thường ngắn, theo cấu hình và rủi ro | Ngắn; dùng để hoàn tất và kiểm tra đăng nhập | Thường dài hơn access token, song có thể hết hạn, bị thu hồi hoặc luân chuyển |
| Vị trí gửi | Header **Authorization: Bearer** đến API thích hợp (với bearer token) | Luồng xác thực OIDC trong client; không dùng làm bearer cho API | Chỉ đến token endpoint qua kênh bảo mật |
| Kiểm tra quan trọng | Chữ ký hoặc introspection, issuer, audience, thời gian, quyền và quyền đối với đối tượng | Chữ ký, issuer, audience là client, thời gian, nonce nếu đã yêu cầu, các điều kiện OIDC khác | Tính hợp lệ, liên kết client, thời hạn, thu hồi, rotation/replay theo chính sách máy chủ |
| Điều kiện xuất hiện | Có khi quá trình cấp quyền thành công | Chỉ khi có OpenID Connect (ví dụ yêu cầu scope **openid**) | Không bảo đảm có; tùy loại client, grant, scope và chính sách nhà cấp quyền |

Cần phân biệt hai khái niệm nền tảng:

- **OAuth 2.0** giải quyết quyền truy cập tài nguyên. Trả về access token **không tự động** có nghĩa client đã được xác thực danh tính người dùng theo OpenID Connect; access token của luồng **client_credentials** thậm chí có thể đại diện cho chính ứng dụng, không có người dùng cuối.
- **OpenID Connect (OIDC)** là lớp định danh bổ sung trên OAuth 2.0. ID token là kết quả đặc trưng của OIDC, được cấp cho Relying Party để xác nhận lần đăng nhập. API phải kiểm tra access token dành cho API đó.

## 3. Luồng chuẩn: Authorization Code + PKCE

Các bên tham gia:

- **Resource Owner**: người dùng đang đăng nhập.
- **Client/Relying Party**: Shop Web, ứng dụng cần gọi API và nhận thông tin đăng nhập.
- **Authorization Server/OpenID Provider**: Login Server phát hành token.
- **Resource Server**: Orders API bảo vệ dữ liệu đơn hàng.

~~~mermaid
sequenceDiagram
    actor U as Người dùng
    participant C as Shop Web (OIDC Client)
    participant A as Login Server (AS/OP)
    participant R as Orders API (Resource Server)
    U->>C: Xem đơn hàng
    C->>A: /authorize?response_type=code + state + nonce + PKCE
    A->>U: Xác thực, xin quyền nếu cần
    A-->>C: Redirect về callback với code + state
    C->>A: POST /token: code + code_verifier
    A-->>C: access_token + id_token (+ refresh_token nếu cấp)
    Note over C: Kiểm tra ID token, tạo phiên ứng dụng
    C->>R: GET /api/orders với Bearer access_token
    R-->>C: 200 OK: đơn hàng được phép xem
    Note over C,A: Access token hết hạn
    C->>A: POST /token: grant_type=refresh_token (nếu có)
    A-->>C: Access token mới (+ refresh token mới nếu rotation)
    C->>R: GET /api/orders với access token mới
~~~

### 3.1. Bước nhận authorization code

Ví dụ yêu cầu được đơn giản hóa để dễ theo dõi (giá trị mẫu không phải chứng thư thật):

~~~http
GET /authorize?response_type=code&client_id=shop-web&redirect_uri=https%3A%2F%2Fshop.example.test%2Fcallback&scope=openid%20profile%20orders.read&state=state-random-123&nonce=nonce-random-456&code_challenge=challenge-value&code_challenge_method=S256 HTTP/1.1
Host: login.example.test
~~~

Login Server xác thực người dùng và trả về **authorization code**, không trả các token qua URL callback trong luồng này. Client kiểm tra **state** để chống tráo phản hồi và dùng **code_verifier** tương ứng với **code_challenge** (PKCE) khi đổi code. **Nonce**, nếu gửi trong yêu cầu OIDC, phải khớp với ID token trả về. Các giá trị state, nonce và PKCE verifier cần được tạo ngẫu nhiên đủ mạnh và được liên kết với đúng giao dịch đăng nhập.

~~~http
POST /token HTTP/1.1
Host: login.example.test
Content-Type: application/x-www-form-urlencoded

grant_type=authorization_code&code=one-time-code&redirect_uri=https%3A%2F%2Fshop.example.test%2Fcallback&client_id=shop-web&code_verifier=original-random-verifier
~~~

Ứng dụng confidential client còn phải xác thực client theo phương thức được cấu hình (ví dụ client authentication); public client không được giả định mình có khả năng giữ client secret.

### 3.2. Phản hồi token endpoint

~~~http
HTTP/1.1 200 OK
Content-Type: application/json
Cache-Control: no-store
Pragma: no-cache

{
  "access_token": "example-access-token",
  "token_type": "Bearer",
  "expires_in": 600,
  "scope": "openid profile orders.read",
  "id_token": "example-signed-id-token-jwt",
  "refresh_token": "example-opaque-refresh-secret"
}
~~~

Đây là phản hồi **minh họa**, không phải quy định rằng mọi nhà cấp quyền đều trả đủ ba token. **expires_in** mô tả thời hạn của access token tính bằng giây; không lấy nó làm thời hạn mặc định của ID token hay refresh token. Tùy provider, refresh token có thể không được cấp, đòi hỏi **offline_access** hoặc điều kiện riêng. Khi refresh về sau, phản hồi cũng không nhất thiết chứa ID token mới.

### 3.3. Gọi REST API bằng access token

~~~http
GET /api/orders HTTP/1.1
Host: api.example.test
Authorization: Bearer example-access-token
Accept: application/json
~~~

Orders API cần xác nhận token được cấp **cho Orders API**, còn hiệu lực và chứa quyền đọc đơn hàng. Nếu hợp lệ, API vẫn phải kiểm soát người dùng/tenant có quyền với **từng đơn hàng cụ thể**; có scope **orders.read** không đồng nghĩa có thể đọc mọi đơn hàng.

~~~http
HTTP/1.1 200 OK
Content-Type: application/json

{
  "items": [
    { "id": "ord-101", "ownerId": "user-42", "total": 320000 }
  ]
}
~~~

Không thay access token trong header bằng ID token, dù hai token cùng được ký bởi Login Server và cùng chứa trường **sub**.

## 4. Phân tích từng loại token

### 4.1. Access token: chứng thư ủy quyền cho một tài nguyên

Nếu access token là JWT, payload **có thể** giống như sau:

~~~json
{
  "iss": "https://login.example.test",
  "sub": "user-42",
  "aud": ["orders-api"],
  "client_id": "shop-web",
  "scope": "orders.read",
  "iat": 1780000000,
  "nbf": 1780000000,
  "exp": 1780000600,
  "jti": "at-001"
}
~~~

- **iss**: bên phát hành, phải khớp nhà cấp quyền mà API tin cậy.
- **aud**: đối tượng nhận. Orders API kỳ vọng **orders-api**; access token có aud **billing-api** phải bị từ chối, dù chữ ký hợp lệ.
- **exp/nbf/iat**: hết hạn, chưa có hiệu lực, thời điểm phát hành. API áp dụng kiểm tra thời gian và độ lệch đồng hồ hợp lý.
- **scope** (hoặc dạng claim quyền khác theo provider): giới hạn khả năng được ủy quyền. Kiểm tra quyền theo endpoint và tài nguyên vẫn là trách nhiệm của API.
- **sub**: chủ thể token; cách diễn giải phụ thuộc grant và hợp đồng của issuer. Không luôn là ID của một người dùng cuối.
- **jti**: định danh token nếu có, giúp liên hệ nhật ký/sự kiện thu hồi theo thiết kế; không thay thế kiểm tra chữ ký, audience hay hết hạn.

**JWT chỉ là cách đóng gói claims**, không phải loại quyền. Access token có thể là chuỗi opaque; khi đó Resource Server dùng **token introspection** hoặc cơ chế xác minh phù hợp với nhà cấp quyền để biết token có active, audience và quyền gì. Không tự tách chuỗi opaque thành JWT, cũng không mặc định token JWT có thể được mọi API của cùng hệ thống chấp nhận.

Access token kiểu **Bearer** có nghĩa **ai nắm giữ token có thể sử dụng nó** trong phạm vi cho phép. Nếu cần giảm khả năng phát lại sau khi lộ token, cân nhắc sender-constrained tokens bằng DPoP hoặc mTLS khi hạ tầng hỗ trợ; lúc đó Resource Server phải kiểm tra thêm bằng chứng ràng buộc, không chỉ JWT.

### 4.2. ID token: kết quả xác thực dành cho OIDC client

Payload ID token minh họa:

~~~json
{
  "iss": "https://login.example.test",
  "sub": "user-42",
  "aud": "shop-web",
  "iat": 1780000000,
  "exp": 1780000300,
  "auth_time": 1779999950,
  "nonce": "nonce-random-456",
  "email": "customer@example.test"
}
~~~

Ý nghĩa then chốt: **aud là shop-web**, vì ID token trả lời câu hỏi “Login Server đã xác thực chủ thể nào cho client này?”. Nó không phải tấm vé được cấp cho Orders API. OIDC client phải kiểm tra chữ ký bằng khóa tin cậy của issuer, **iss**, **aud** chứa client_id của chính mình, thời gian hiệu lực, **nonce** nếu đã gửi và các yêu cầu OIDC tương ứng với flow. Nếu có **azp** thì kiểm tra authorized party theo quy tắc OIDC; các claim như **auth_time**, **at_hash** cần được xử lý trong trường hợp giao thức yêu cầu.

**sub** (kết hợp với **iss**) thường là khóa nhận diện ổn định phù hợp hơn email. Email có thể đổi, không nhất thiết được xác minh hoặc duy nhất theo hệ thống; đừng dùng email làm khóa phân quyền nội bộ chỉ vì nó xuất hiện trong ID token.

Sau khi kiểm tra ID token, ứng dụng web có thể thiết lập **phiên đăng nhập riêng** bằng cookie phiên an toàn. Phiên này khác với access token API: một request nội bộ từ browser đến web server có thể dùng session cookie, còn web server sử dụng access token khi gọi Orders API.

**Sai lầm điển hình:** API nhận ID token có chữ ký đúng rồi suy ra người dùng được xem đơn hàng. Chữ ký chỉ cho biết token do issuer ký và payload không bị sửa; trường audience vẫn là **shop-web**, không phải **orders-api**. Cách dùng này tạo lỗ hổng **token substitution/confused deputy**.

### 4.3. Refresh token: quyền xin token mới tại Authorization Server

Refresh token là bí mật có giá trị cao vì nó có thể duy trì quyền truy cập qua nhiều vòng access token. Client gửi nó **chỉ đến token endpoint**:

~~~http
POST /token HTTP/1.1
Host: login.example.test
Content-Type: application/x-www-form-urlencoded

grant_type=refresh_token&refresh_token=example-opaque-refresh-secret&client_id=shop-web
~~~

Máy chủ cấp quyền kiểm tra token có thuộc client/phân quyền tương ứng, còn hạn, chưa bị thu hồi và đáp ứng chính sách bảo vệ phát lại. Confidential client xác thực như cấu hình. Một phản hồi có thể là:

~~~http
HTTP/1.1 200 OK
Content-Type: application/json
Cache-Control: no-store

{
  "access_token": "new-example-access-token",
  "token_type": "Bearer",
  "expires_in": 600,
  "refresh_token": "new-example-refresh-secret"
}
~~~

Với **refresh-token rotation**, mỗi lần làm mới thành công trả refresh token mới; client lưu token mới một cách an toàn và ngừng dùng token cũ. Nếu phát hiện token cũ bị dùng lại, Authorization Server có thể coi đó là dấu hiệu lộ token và vô hiệu hóa chuỗi phiên theo chính sách. Với public client, các biện pháp chống phát lại như rotation hoặc sender-constraining là đặc biệt quan trọng. Không phải mọi provider đều triển khai rotation giống nhau; client phải tuân theo hợp đồng provider và xử lý cả trường hợp phản hồi **không có** refresh token mới.

Nếu refresh token hết hạn/bị thu hồi/không hợp lệ, token endpoint thường trả lỗi OAuth **invalid_grant**; client phải xóa trạng thái ủy quyền liên quan và bắt đầu lại luồng đăng nhập/cấp quyền khi thích hợp. Không thử vô hạn, không gửi refresh token cho Resource Server, không đưa nó vào URL hay log.

## 5. Ai kiểm tra gì? Ranh giới tin cậy

| Thành phần | Dữ liệu nhận | Phải xác minh | Không được làm |
|---|---|---|---|
| Shop Web (OIDC client) | ID token từ Login Server | Issuer, chữ ký/thuật toán, audience là client_id, exp/iat, nonce nếu có, các điều kiện OIDC | Dùng ID token làm bearer cho Orders API |
| Orders API (Resource Server) | Access token ở Authorization header | JWT: chữ ký, issuer, audience, exp/nbf, quyền; opaque: introspection và thuộc tính tương ứng; thêm quyền trên đơn hàng | Chỉ decode JWT hoặc chỉ nhìn sub/email; chấp nhận token dành cho client/API khác |
| Login Server (Authorization Server) | Authorization code, refresh token, client authentication, PKCE verifier | Ràng buộc code/client/redirect URI/PKCE; refresh token/client/thu hồi/rotation | Phát token mới từ refresh token đã bị vô hiệu |
| Browser/mobile app | Dữ liệu phiên và token được phép nắm giữ | State và liên kết giao dịch; PKCE; storage và lifecycle theo loại client | Đặt token vào query URL, log công khai, hoặc hardcode bí mật dài hạn |

### Phân biệt xác thực, ủy quyền và phân quyền đối tượng

- **Authentication**: “Ai đã đăng nhập?” OIDC client dùng ID token đã kiểm chứng và quản lý phiên.
- **Authorization ở biên API**: “Request có access token phù hợp và scope cần thiết không?” Resource Server kiểm tra bearer token và quyền.
- **Object-level authorization**: “Chủ thể/tenant này có được xem ord-101 không?” Business layer kiểm tra owner, tenant, role, policy; không suy ra toàn quyền từ scope.

Hai access token có thể cùng chứa scope **orders.read**, nhưng nếu **sub/tenant** khác nhau thì tập đơn hàng được trả về phải khác nhau. Việc client gửi **userId** trong query không có giá trị xác thực nếu API không đối chiếu nó với principal được xác minh.

### JWT và opaque không quyết định nhiệm vụ của token

Một JWT được ký đúng vẫn có thể bị từ chối vì sai **aud**, sai **iss**, quá hạn, thiếu scope hoặc chỉ dành cho OIDC client. Ngược lại, một access token opaque vẫn hợp lệ nếu API nhận được kết quả introspection tin cậy từ Authorization Server, xác minh active và các ràng buộc cần thiết. Không xác định token dùng cho mục đích nào chỉ bằng việc chuỗi có ba đoạn cách nhau bởi dấu chấm.

## 6. HTTP status và hành vi phía client

Ví dụ Orders API yêu cầu access token hợp lệ với scope **orders.read**.

| Trường hợp | Phản hồi API đúng | Client nên làm gì |
|---|---|---|
| Không mang access token | **401 Unauthorized**, thường có header **WWW-Authenticate: Bearer** | Lấy access token hợp lệ trước khi gọi lại |
| Access token hết hạn, chữ ký sai, sai issuer hoặc audience | **401 Unauthorized**, có thể kèm **invalid_token** | Nếu có refresh token hợp lệ thì thử làm mới có kiểm soát; nếu không, cấp quyền lại |
| Access token hợp lệ nhưng thiếu **orders.read** | **403 Forbidden**, có thể kèm **insufficient_scope** | Không lặp request vô hạn; xin quyền phù hợp nếu UX cho phép |
| Scope đủ nhưng không được xem đơn hàng cụ thể | **403 Forbidden** hoặc **404 Not Found** theo chính sách tránh rò rỉ tài nguyên | Không suy đoán quyền chỉ từ scope |
| Token và quyền đều đúng | **200 OK** (hoặc mã 2xx thích hợp theo thao tác) | Xử lý dữ liệu |
| Refresh token không còn hợp lệ | **400 Bad Request** ở **token endpoint** với lỗi **invalid_grant** thông thường | Hủy trạng thái làm mới và bắt đầu lại luồng đăng nhập/ủy quyền |

Phản hồi cho bearer token sai ví dụ:

~~~http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer error="invalid_token"
Cache-Control: no-store
~~~

Phản hồi cho quyền thiếu ví dụ:

~~~http
HTTP/1.1 403 Forbidden
WWW-Authenticate: Bearer error="insufficient_scope", scope="orders.read"
~~~

**401** diễn đạt việc thiếu/không chấp nhận được thông tin xác thực cho API; **403** diễn đạt thông tin xác thực đã được chấp nhận nhưng quyền không đủ. Header **WWW-Authenticate** tuân theo RFC 6750 và chính sách thực tế; không trả nội dung token, khóa ký hay thông tin nhạy cảm trong body lỗi. Refresh endpoint không phải endpoint Resource Server, vì vậy lỗi **invalid_grant** không nhất thiết mang mã 401.

## 7. Triển khai với Java và Spring Security

Ví dụ sau là **hai ứng dụng tách biệt**: Orders API đóng vai Resource Server, Shop Web đóng vai OIDC Client. Cách phân vai giúp tránh dùng nhầm ID token trong API. Ví dụ dùng Spring Boot 3.x/Spring Security 6.x và Java hiện đại; URL/issuer/audience đều là giá trị minh họa cần thay theo provider.

### 7.1. Orders API: xác thực access token và audience

Thêm dependency **spring-boot-starter-web**, **spring-boot-starter-security** và **spring-boot-starter-oauth2-resource-server**. Login Server công bố JWKS ở địa chỉ đã được cấu hình/tin cậy; ứng dụng không tự tin **jku** hoặc URL khóa do token cung cấp.

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configurers.AbstractHttpConfigurer;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.oauth2.core.OAuth2Error;
import org.springframework.security.oauth2.core.OAuth2TokenValidator;
import org.springframework.security.oauth2.core.OAuth2TokenValidatorResult;
import org.springframework.security.oauth2.core.DelegatingOAuth2TokenValidator;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.jwt.JwtDecoder;
import org.springframework.security.oauth2.jwt.JwtValidators;
import org.springframework.security.oauth2.jwt.NimbusJwtDecoder;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
class ApiSecurity {
    private static final String ISSUER = "https://login.example.test";
    private static final String AUDIENCE = "orders-api";

    @Bean
    SecurityFilterChain apiChain(HttpSecurity http) throws Exception {
        return http
            // Chỉ hợp lý với API stateless dùng bearer header,
            // không dùng cookie session để xác thực request.
            .csrf(AbstractHttpConfigurer::disable)
            .sessionManagement(s ->
                s.sessionCreationPolicy(SessionCreationPolicy.STATELESS))
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET, "/api/orders/**")
                    .hasAuthority("SCOPE_orders.read")
                .anyRequest().authenticated())
            .oauth2ResourceServer(oauth -> oauth.jwt(Customizer.withDefaults()))
            .build();
    }

    @Bean
    JwtDecoder jwtDecoder() {
        NimbusJwtDecoder decoder = NimbusJwtDecoder
            .withJwkSetUri("https://login.example.test/.well-known/jwks.json")
            .build();

        OAuth2TokenValidator<Jwt> audienceValidator = jwt ->
            jwt.getAudience() != null
                && jwt.getAudience().contains(AUDIENCE)
                ? OAuth2TokenValidatorResult.success()
                : OAuth2TokenValidatorResult.failure(
                    new OAuth2Error(
                        "invalid_token", "Wrong token audience", null));

        decoder.setJwtValidator(new DelegatingOAuth2TokenValidator<>(
            JwtValidators.createDefaultWithIssuer(ISSUER),
            audienceValidator
        ));
        return decoder;
    }
}
~~~

Ở đây **JwtValidators.createDefaultWithIssuer** kiểm tra issuer và các quy tắc JWT mặc định (trong đó có thời gian hiệu lực); validator riêng kiểm tra **audience**. NimbusJwtDecoder xác minh chữ ký bằng khóa tin cậy từ JWKS. Spring Security ánh xạ claim **scope/scp** theo quy tắc mặc định thành authority có tiền tố **SCOPE_**, do đó **orders.read** khớp **SCOPE_orders.read**. Nếu provider dùng claim quyền khác, cần cấu hình **JwtAuthenticationConverter** rõ ràng.

**Lưu ý triển khai:** chỉ tắt CSRF theo mẫu nếu API thực sự chỉ dựa vào bearer header và không dùng cookie/session tự động được browser đính kèm để xác thực. Ứng dụng web dựa vào session cookie phải có chính sách CSRF riêng. Với access token opaque, thay cấu hình JWT bằng **opaqueToken/introspection** cùng cơ chế xác thực tới introspection endpoint; không cố decode opaque thành JWT.

Controller minh họa việc lấy principal đã kiểm chứng:

~~~java
import java.util.List;
import java.util.Map;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
class OrderController {
    @GetMapping("/api/orders")
    Map<String, Object> myOrders(@AuthenticationPrincipal Jwt jwt) {
        String subject = jwt.getSubject();

        // Thay danh sách rỗng bằng truy vấn có lọc owner/tenant
        // dựa trên subject và quyền được server xác minh.
        return Map.of("subject", subject, "items", List.of());
    }
}
~~~

Ở ứng dụng thật, service/repository phải lọc theo principal/tenant hoặc áp dụng policy trên từng bản ghi; controller mẫu chỉ minh họa cách đọc **sub** đã xác thực, không phải logic quản lý đơn hàng hoàn chỉnh.

### 7.2. Shop Web: dùng ID token cho đăng nhập, access token để gọi API

Ứng dụng OIDC Client sử dụng **spring-boot-starter-oauth2-client**, client registration có issuer-uri, client-id, redirect-uri, scope **openid** và cấu hình xác thực client thích hợp. Với web app dạng confidential client, bí mật client phải đặt trong hệ thống quản lý secret hoặc biến cấu hình an toàn. Cấu hình Spring Security của **ứng dụng web** có thể dùng:

~~~java
@Bean
SecurityFilterChain webChain(HttpSecurity http) throws Exception {
    return http
        .authorizeHttpRequests(auth -> auth
            .requestMatchers("/").permitAll()
            .anyRequest().authenticated())
        .oauth2Login(Customizer.withDefaults())
        .build();
}
~~~

Sau đăng nhập OIDC, Spring Security kiểm tra ID token trong luồng OIDC, xây dựng **OidcUser** và quản lý phiên web. Khi cần gọi API, lấy **OAuth2AccessToken** của authorized client:

~~~java
import org.springframework.security.oauth2.client.OAuth2AuthorizedClient;
import org.springframework.security.oauth2.client.annotation.RegisteredOAuth2AuthorizedClient;
import org.springframework.security.oauth2.core.oidc.user.OidcUser;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.ResponseBody;
import org.springframework.stereotype.Controller;
import org.springframework.web.client.RestClient;

@Controller
class ShopWebController {
    private final RestClient ordersApi =
        RestClient.create("https://api.example.test");

    @GetMapping("/my-orders")
    @ResponseBody
    String orders(
        @AuthenticationPrincipal OidcUser user,
        @RegisteredOAuth2AuthorizedClient("shop-web")
            OAuth2AuthorizedClient authorizedClient
    ) {
        String loggedInSubject = user.getSubject();
        // ID token đã được xử lý trong OIDC login:
        // loggedInSubject chỉ dùng cho ngữ cảnh phiên ứng dụng.

        String accessToken =
            authorizedClient.getAccessToken().getTokenValue();

        return ordersApi.get()
            .uri("/api/orders")
            .headers(headers -> headers.setBearerAuth(accessToken))
            .retrieve()
            .body(String.class);
    }
}
~~~

**shop-web** trong annotation là **registrationId** đã cấu hình; client thực tế có thể đặt tên khác. Để tự động làm mới, tích hợp **OAuth2AuthorizedClientManager** với provider hỗ trợ **refreshToken()** và lưu authorized client an toàn ở phía server. Mã trên trình bày cách chọn token phù hợp; việc có refresh token và chính sách tự làm mới phụ thuộc cấu hình/provider, không nên mặc định điều đó luôn xảy ra.

Ứng dụng browser thuần SPA có ràng buộc khác với web backend: SPA là public client, không thể giữ client secret. Chọn Authorization Code + PKCE; nếu có điều kiện kiến trúc, mô hình **Backend-for-Frontend (BFF)** giữ access/refresh token ở backend và chỉ gửi session cookie **HttpOnly, Secure, SameSite** cho browser sẽ giảm khả năng token bị JavaScript đọc. Cookie phiên cần bảo vệ CSRF phù hợp. Ứng dụng mobile nên dùng kho bí mật an toàn của hệ điều hành và PKCE.

### 7.3. Khi nào Java client gọi lại hoặc refresh?

Một quy tắc thực hành an toàn:

1. Kiểm tra thời gian hết hạn access token với khoảng dự phòng nhỏ để tránh lỗi do lệch đồng hồ.
2. Nếu cần refresh và client thực sự có refresh token, gửi **refresh token đến token endpoint** thông qua thành phần quản lý authorized client.
3. Lưu atomic token mới; khi dùng rotation phải thay refresh token cũ ngay, xử lý đồng thời nhiều request để tránh hai luồng cùng dùng lại một refresh token.
4. Gọi lại API có kiểm soát khi nhận **401 invalid_token** và khả năng refresh phù hợp. Chỉ retry request ghi dữ liệu nếu đã xem xét **idempotency** và an toàn phát lại.
5. Nếu refresh thất bại vì **invalid_grant**, xóa trạng thái cấp quyền liên quan và yêu cầu đăng nhập/cấp quyền mới. **403 insufficient_scope** không được “chữa” bằng vòng refresh vô hạn.

Không log token nguyên văn, kể cả trong logger HTTP, exception hay hệ thống tracing. Khi cần điều tra sự cố, ghi mã lỗi, request ID, token ID đã băm hoặc thông tin phi bí mật được phê duyệt.

## 8. Bảo mật và các lỗi thiết kế thường gặp

| Lỗi thiết kế | Hậu quả | Cách khắc phục |
|---|---|---|
| API nhận ID token vì có chữ ký đúng | Token vốn dành cho client được dùng để truy cập API (token substitution) | API chỉ chấp nhận access token được cấp đúng issuer/audience, quyền |
| Chỉ decode base64 của JWT rồi đọc sub/scope | Token giả hoặc bị sửa có thể vượt qua kiểm tra | Xác minh chữ ký/thuật toán, issuer, audience, thời gian, quyền; không tin dữ liệu chưa xác minh |
| API chỉ kiểm tra scope, bỏ qua owner/tenant | Lộ dữ liệu đơn hàng của người khác (BOLA/IDOR) | Phân quyền theo bản ghi tại business layer |
| Gửi refresh token trong Authorization header đến API | Lộ bí mật dài hạn sang hệ thống không cần nhận | Chỉ gửi refresh token đến token endpoint đã tin cậy |
| Dùng access token cho mọi API của cùng issuer | Một token được dùng vượt khỏi tài nguyên đích | Ràng buộc audience, scope và policy theo từng API |
| Lưu token dài hạn ở localStorage hoặc URL | XSS, lịch sử trình duyệt, log/proxy có thể làm lộ token | Ưu tiên BFF/session an toàn khi phù hợp; kho bí mật chuyên dụng cho native |
| Không kiểm tra nonce/state/PKCE | Dễ bị tráo phản hồi hoặc chiếm authorization code | State, PKCE S256, nonce OIDC khi sử dụng, redirect URI cố định |
| Không rotation/revoke hoặc xử lý đồng thời refresh thiếu nhất quán | Token lộ bị tái sử dụng lâu; race gây invalid_grant | Rotation/sender-constraining theo chính sách, lưu thay thế atomic, phát hiện reuse |
| Dùng email trong ID token làm khóa bất biến | Gắn sai chủ thể khi email thay đổi/tái sử dụng | Sử dụng cặp issuer + subject và ánh xạ định danh nội bộ |
| Coi logout là thu hồi ngay mọi JWT | Access token còn hạn có thể tiếp tục được dùng | Thu hồi refresh/session, access token TTL ngắn; nếu cần tức thời dùng cơ chế kiểm tra trạng thái thích hợp |

Bổ sung các điểm vận hành: bắt buộc **HTTPS** cho mọi endpoint và token transport; không đặt token trong query string, log, analytics hoặc thông báo lỗi; giới hạn **scope** tối thiểu; dùng JWKS/issuer đã cấu hình trước và chỉ chấp nhận thuật toán được phép; xử lý key rotation; áp dụng rate limit và giám sát lỗi refresh/reuse. **CORS** là chính sách trình duyệt, không thay thế việc xác minh token hay phân quyền ở backend.

## 9. Kiểm thử Spring Security và hợp đồng HTTP

Kiểm thử phải tách hai tầng: **authorization rules** của controller/filter chain và **validation thật** của token.

### 9.1. Kiểm thử luật scope bằng MockMvc

Thêm dependency kiểm thử **spring-security-test** cùng các starter test. Các ví dụ sau giả định **ApiSecurity** và **OrderController** ở trên đã được nạp vào Spring context.

~~~java
import static org.springframework.security.test.web.servlet.request
    .SecurityMockMvcRequestPostProcessors.jwt;
import static org.springframework.test.web.servlet.request
    .MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result
    .MockMvcResultMatchers.status;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.test.web.servlet.MockMvc;

@SpringBootTest
@AutoConfigureMockMvc
class OrdersSecurityTest {
    @Autowired MockMvc mvc;

    @Test
    void missingTokenReturns401() throws Exception {
        mvc.perform(get("/api/orders"))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void validPrincipalButMissingScopeReturns403() throws Exception {
        mvc.perform(get("/api/orders").with(jwt()
                .authorities(new SimpleGrantedAuthority("SCOPE_profile"))))
            .andExpect(status().isForbidden());
    }

    @Test
    void grantedScopeAllowsRequest() throws Exception {
        mvc.perform(get("/api/orders").with(jwt()
                .authorities(new SimpleGrantedAuthority("SCOPE_orders.read"))))
            .andExpect(status().isOk());
    }
}
~~~

**Giới hạn quan trọng:** MockMvc **jwt()** tạo principal kiểm thử và **không chứng minh** hệ thống đã xác thực chữ ký JWT, issuer, audience hay hạn dùng thật. Để kiểm tra cấu hình **JwtDecoder**, dùng token ký bằng khóa thử nghiệm và JWKS server thử nghiệm, đưa request mang **Authorization: Bearer** qua filter chain thật; kiểm tra trường hợp chữ ký sai, issuer sai, **aud=shop-web**, **aud=billing-api**, hết hạn và key rotation.

### 9.2. Ma trận kiểm thử tích hợp tối thiểu

| Đầu vào | Kỳ vọng | Phần cần quan sát |
|---|---|---|
| Không có Authorization | 401 + Bearer challenge | Security filter chain |
| Bearer ID token có aud **shop-web** | 401, dù chữ ký issuer hợp lệ | Audience validation |
| Access token aud **billing-api** | 401 | Audience validation |
| Access token hết hạn hoặc bị sửa chữ ký | 401 | Time/signature validation |
| Access token hợp lệ nhưng thiếu **orders.read** | 403 | Scope authorization |
| Access token hợp lệ, scope đủ, đơn hàng không thuộc chủ thể | 403/404 theo policy | Object-level authorization |
| Access token hợp lệ, scope đủ, đúng owner | 200 | Luồng thành công |
| Refresh token hợp lệ, rotation bật | Phát access token và refresh token mới | Token endpoint, lưu trữ atomic |
| Dùng lại refresh token đã rotate | Từ chối; phát hiện reuse theo chính sách | Replay detection |
| Refresh token sai/bị thu hồi | Token endpoint trả **invalid_grant** | Client khởi tạo lại đăng nhập, không retry vô hạn |

Đừng chỉ kiểm tra mã 2xx: thử gọi **POST/PATCH** có access token hết hạn để bảo đảm client không phát lại thao tác không idempotent khi không có bảo vệ tương ứng, và thử truy cập đơn hàng của người khác ngay cả khi caller có scope hợp lệ.

## 10. Tình huống thực hành

### Bài tập 1: chọn token đúng

Cho ba chứng thư sau (đều do Login Server phát hành):

- **T1**: JWT có **aud=shop-web**, **sub=user-42**, **nonce=n-1**, hết hạn sau 5 phút.
- **T2**: JWT có **aud=orders-api**, **scope=orders.read**, hết hạn sau 10 phút.
- **T3**: chuỗi opaque cho phép xin quyền mới ở token endpoint, có chính sách rotation.

Hãy xác định token nào Shop Web dùng để hoàn tất đăng nhập, token nào dùng gọi **GET /api/orders**, token nào dùng khi T2 hết hạn. Giải thích vì sao Orders API phải từ chối T1 dù cả T1 và T2 đều được ký bởi cùng issuer.

**Gợi ý:** T1 là ID token cho client; T2 là access token cho API; T3 là refresh token cho Authorization Server. Việc cùng issuer không làm cho audience trở nên tương đương.

### Bài tập 2: sửa cấu hình API

Một API Spring có đoạn code chỉ kiểm tra:

~~~java
if (jwt.getSubject() != null) {
    return orderService.listAll();
}
~~~

Hãy thiết kế lại để (1) kiểm tra issuer, chữ ký, hạn dùng và **aud=orders-api** tại resource-server filter; (2) yêu cầu scope **orders.read**; (3) lọc đơn hàng theo subject/tenant; (4) trả 401 cho token không hợp lệ và 403/404 cho tài nguyên không được phép. Viết ít nhất năm ca kiểm thử phủ các đường đi quan trọng.

**Tiêu chí đạt:** Token aud client khác bị loại; access token hợp lệ không tự cho phép đọc mọi đơn hàng; kiểm thử signature/audience nằm ở tầng xác minh token thật, không chỉ MockMvc jwt().

### Bài tập 3: xử lý refresh race

Shop Web gửi hai request song song sau khi access token hết hạn. Cả hai đọc cùng refresh token **r1**; lần thứ nhất thành công và nhận **r2**, lần thứ hai gửi lại **r1** khiến provider đánh dấu reuse.

Hãy vẽ sequence và đề xuất một cơ chế **single-flight refresh** trên server: mọi request cùng phiên dùng chung một thao tác refresh đang thực hiện, ghi **r2** một lần theo giao dịch/khóa thích hợp, sau đó sử dụng access token mới. Xác định cách xử lý nếu refresh thất bại với **invalid_grant** và chỉ ra vì sao không nên phát lại POST tạo đơn hàng tùy tiện.

### Bài tập 4: kiểm tra một phản hồi OAuth

Một developer thấy phản hồi có **access_token** và **expires_in**, nhưng không có **id_token** hoặc **refresh_token**. Hãy nêu ba giả thuyết hợp lệ cần kiểm tra (ví dụ request có scope **openid** không, có thực sự dùng OIDC không, loại grant/chính sách refresh token là gì). Vì sao thiếu refresh token không tự động chứng minh một lỗi giao thức?

## 11. Câu hỏi tự kiểm tra

1. **Access token là JWT thì có phải ID token không?** Không. JWT là định dạng; loại token phụ thuộc mục đích, issuer, audience và hợp đồng cấp phát.
2. **Có thể dùng ID token làm Bearer cho REST API không?** Không trong thiết kế chuẩn ở đây; ID token được cấp cho OIDC client, còn API cần access token đúng audience.
3. **Refresh token nên gửi đến đâu?** Token endpoint của Authorization Server, cùng xác thực/ràng buộc client phù hợp; không gửi đến Resource Server.
4. **Scope orders.read đủ để xem mọi đơn hàng?** Không. API còn phải thực thi phân quyền ở mức đối tượng/tenant.
5. **Access token hết hạn có luôn refresh được không?** Không. Cần refresh token hợp lệ và provider cho phép; nếu không phải bắt đầu lại luồng cấp quyền/đăng nhập.
6. **JWT có chữ ký hợp lệ có chắc được API chấp nhận?** Không. Còn issuer, audience, thời gian, scope, ràng buộc người dùng và các chính sách khác.

## 12. Tài liệu chuẩn để đối chiếu

- **OAuth 2.0 Framework**, RFC 6749: các vai trò, authorization grant, access và refresh token — https://www.rfc-editor.org/rfc/rfc6749
- **Bearer Token Usage**, RFC 6750: Authorization header, WWW-Authenticate, invalid_token và insufficient_scope — https://www.rfc-editor.org/rfc/rfc6750
- **PKCE**, RFC 7636: liên kết authorization code với code_verifier — https://www.rfc-editor.org/rfc/rfc7636
- **Token Introspection**, RFC 7662; **Token Revocation**, RFC 7009: xác minh opaque token và thu hồi quyền — https://www.rfc-editor.org/rfc/rfc7662 và https://www.rfc-editor.org/rfc/rfc7009
- **JWT Best Current Practices**, RFC 8725; **OAuth 2.0 Security Best Current Practice**, RFC 9700: ngăn nhầm token, replay và bảo vệ refresh token — https://www.rfc-editor.org/rfc/rfc8725 và https://www.rfc-editor.org/rfc/rfc9700
- **OpenID Connect Core 1.0**: ID token, kiểm tra issuer/audience/nonce và các flow OIDC — https://openid.net/specs/openid-connect-core-1_0.html

**Ghi nhớ trong thiết kế REST:** Client dùng **ID token** để hiểu kết quả đăng nhập OIDC, Resource Server dùng **access token** để xét quyền truy cập tài nguyên, và Authorization Server dùng **refresh token** để xét yêu cầu cấp lại quyền. Mỗi token phải được kiểm chứng bởi đúng bên nhận, với đúng audience và đúng trách nhiệm bảo mật.
