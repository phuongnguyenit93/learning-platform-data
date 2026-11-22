# Tham số token, token_type_hint và xác thực client

> **Chương: Revocation.** Bài thuộc module **SPRING_SECURITY_OAUTH2_OIDC_AUTHORIZATION_SERVER** — học cách thiết kế, cấu hình, bảo mật, kiểm thử và vận hành OAuth 2.0/OpenID Connect Authorization Server bằng Spring Security và Spring Authorization Server trong ứng dụng Spring Boot. Trọng tâm bài là hợp đồng request của **RFC 7009**, ý nghĩa tham số `token`, `token_type_hint`, yêu cầu **xác thực và ràng buộc OAuth client**, cách cấu hình Spring Authorization Server cùng kiểm thử các trường hợp sai/lạm dụng.

## 1. Mục đích và phạm vi Token Revocation

Khi người dùng đăng xuất, ngắt kết nối một ứng dụng, thiết bị bị mất hoặc refresh token nghi bị lộ, OAuth client có thể yêu cầu Authorization Server (AS) làm một token mất hiệu lực **trước thời điểm hết hạn**. Cơ chế chuẩn được định nghĩa bởi **RFC 7009 — OAuth 2.0 Token Revocation**.

Ví dụ xuyên suốt:

| Thành phần | Giá trị minh họa | Vai trò |
|---|---|---|
| Authorization Server | `https://login.example.vn` | Cấp và quản lý token với Spring Authorization Server |
| Revocation Endpoint | `https://login.example.vn/oauth2/revoke` | Nhận token revocation request |
| Confidential OAuth Client | `portal-web` | BFF đăng nhập người dùng và lưu token |
| End User | `user-123` | Chủ thể của authorization grant |
| Resource Server | `https://api.example.vn` | API dùng access token để kiểm soát quyền |
| Token đang có | `A0` (access token), `R0` (refresh token) | Được cấp trong cùng một authorization |

Khi user gỡ kết nối `portal-web`, client gửi `R0` cho revocation endpoint. AS xác thực client, kiểm tra token **đã cấp cho chính client đó** và xử lý trạng thái. Nếu thành công, client không được dùng `R0` để xin access token mới.

**Ba quy tắc cần nhớ:**

1. `token` là **giá trị credential muốn thu hồi**, bắt buộc trong body.
2. `token_type_hint` chỉ là **gợi ý tra cứu**, tùy chọn và có thể sai.
3. Một revocation request phải đi qua **xác thực client phù hợp và kiểm tra token ownership**. Không cho một client thu hồi token của client khác.

### 1.1. Không nhầm revocation với các cơ chế khác

| Cơ chế | Chức năng chính | Khác với revocation |
|---|---|---|
| **Token Revocation — RFC 7009** | Yêu cầu token mất hiệu lực | Là thao tác **thay đổi trạng thái** |
| **Token Introspection — RFC 7662** | Hỏi token có active, scope, aud… hay không | Chủ yếu **đọc trạng thái** |
| **Refresh Token grant** | Xin access token mới bằng refresh token hợp lệ | Không phải thu hồi token |
| **OIDC RP-Initiated Logout** | Kết thúc phiên login tại OpenID Provider | Không tự động đảm bảo mọi OAuth access token đã revoked |
| **Xóa token ở client** | Client ngừng giữ credential | Token có thể vẫn active ở AS |
| **Xóa authorization/grant** | Thu hồi cả authorization theo chính sách quản trị | Có thể rộng hơn một request revoke token |

## 2. HTTP request theo RFC 7009

Client phải gửi `HTTP POST` tới revocation endpoint được lấy từ metadata/cấu hình đáng tin. URL endpoint phải là **HTTPS**. Request body dùng `application/x-www-form-urlencoded`.

Ví dụ confidential client xác thực bằng `client_secret_basic`:

~~~http
POST /oauth2/revoke HTTP/1.1
Host: login.example.vn
Authorization: Basic REDACTED_CLIENT_CREDENTIALS
Content-Type: application/x-www-form-urlencoded
Accept: application/json

token=R0_REDACTED&token_type_hint=refresh_token
~~~

Đây là HTTP minh họa; `R0_REDACTED` và Basic credential không phải giá trị thật. Token thực tế phải được URL-encode đúng quy tắc form. Không ghi body hay Authorization header vào access log.

### 2.1. Bảng tham số

| Tham số | Bắt buộc | Giá trị | Ý nghĩa |
|---|---|---|---|
| `token` | **Có** | Chuỗi access token/refresh token | Token cụ thể client muốn thu hồi |
| `token_type_hint` | Không | Thường `access_token` hoặc `refresh_token` | Gợi ý AS tra token nhanh hơn |
| Client authentication | Tùy kiểu client nhưng bắt buộc phải tuân thủ profile bảo mật | HTTP Basic, JWT assertion, mTLS, hoặc public-client method được hỗ trợ | Chứng minh/nhận diện caller theo RegisteredClient và policy |

Không gửi `grant_type=revocation`: revocation endpoint **không phải một OAuth grant type**. Không đổi tên trường `token` thành `refresh_token` chỉ vì muốn thu hồi refresh token.

### 2.2. Các trường không thuộc request bắt buộc

- `redirect_uri` và `code_verifier`: dành cho Authorization Code/PKCE, không phải hai trường chính của revocation.
- `scope`: không dùng để quyết định tùy tiện phải thu hồi bao nhiêu scope.
- `user_id` hoặc `tenant_id` từ body: không phải bằng chứng quyền thu hồi.
- `client_id` trong form: có thể cần ở public-client profile, nhưng không thể thay thế client authentication của confidential client.
- `Authorization: Bearer TOKEN_TO_REVOKE`: không phải phương thức thay thế Basic/private_key_jwt/mTLS của client ở revocation endpoint.

### 2.3. Không gửi token qua URL/query

Không dùng:

~~~http
GET /oauth2/revoke?token=R0_REDACTED HTTP/1.1
Host: login.example.vn
~~~

GET/query có thể khiến token lộ qua browser history, Referer, proxy, WAF và telemetry. RFC 7009 có nhắc một số kỹ thuật JSONP/GET cho legacy clients, nhưng **không nên đưa vào hệ thống mới** do rủi ro bảo mật. Dùng POST body với HTTPS, no-store và redact log.

## 3. Tham số `token`: loại token và phạm vi thu hồi

RFC 7009 §2 yêu cầu Authorization Server **MUST** hỗ trợ thu hồi refresh token và **SHOULD** hỗ trợ thu hồi access token. Khi nhận `token`, AS cần xác định token có tồn tại và thuộc client đang yêu cầu hay không.

| Giá trị đưa vào `token` | Điều mong muốn | Phải phân biệt |
|---|---|---|
| Refresh token `R0` | Không còn dùng R0 để refresh | Có thể kéo theo các access token phát từ grant |
| Access token `A0` | Không còn dùng A0 để gọi API | JWT offline có thể chưa nhận được thông tin revoke |
| Token đã expired | Không còn hợp lệ | Không cần trả lỗi chỉ vì vốn đã expired |
| Token đã revoked | Vẫn không hợp lệ | Request lặp nên có ngữ nghĩa idempotent |
| Chuỗi không phải token được AS biết | Không cần sửa trạng thái | RFC trả HTTP 200 khi client hợp lệ |
| Token được cấp cho client khác | Caller không có quyền trên token | AS phải **từ chối**, không được sửa token của client khác |

### 3.1. Thu hồi một token có thể ảnh hưởng các token khác

RFC 7009 §2.1 quy định:

- Khi revoke **refresh token**, nếu server hỗ trợ access token revocation, server **SHOULD** cũng vô hiệu hóa các access token phát từ cùng authorization grant.
- Khi revoke **access token**, server **MAY** cũng vô hiệu refresh token tương ứng.
- Mức độ cascade là chính sách của AS; không thể lấy tên `token_type_hint` để quyết định rằng tất cả phiên người dùng sẽ bị thu hồi.

Đối với nhiều thiết bị, mỗi thiết bị/client có thể có grant và refresh token riêng. Một request `token=R0` không mặc nhiên là lệnh “logout tất cả thiết bị”.

### 3.2. Token invalid không đồng nghĩa request invalid

Token có thể đã hết hạn hoặc không được lưu trong kho. Với **client xác thực hợp lệ**, RFC 7009 yêu cầu trả `200 OK` cho token không hợp lệ để không làm rò trạng thái tồn tại của credential. Ngược lại, request thiếu trường `token` hoặc client authentication sai là lỗi thật.

## 4. `token_type_hint`: tùy chọn và có thể sai

RFC định nghĩa hai hint phổ biến:

- `access_token` — người gọi đoán `token` là access token.
- `refresh_token` — người gọi đoán `token` là refresh token.

Hint giúp AS chọn index hoặc token type để tra cứu trước. **Hint không phải token type đã được chứng thực, không phải quyền và không phải một bộ lọc bắt buộc.**

### 4.1. Fallback bắt buộc khi hint sai

RFC 7009 yêu cầu: **nếu AS không tìm thấy token bằng hint, nó MUST mở rộng tra cứu qua tất cả token types mà nó hỗ trợ**. AS cũng **MAY bỏ qua hint** và tự phát hiện loại token.

Ví dụ `R1` là refresh token thật:

| Request | Đường xử lý hợp lệ | Kết quả mong đợi |
|---|---|---|
| `token=R1&token_type_hint=refresh_token` | Tìm refresh token | Thu hồi R1 |
| `token=R1&token_type_hint=access_token` | Tìm access không ra, fallback refresh | **Vẫn thu hồi R1** |
| `token=R1` | Tự xác định token type | Vẫn thu hồi R1 |
| `token=R1&token_type_hint=unknown_type` | Bỏ qua hint không hợp lệ | Vẫn thu hồi R1 |
| `token=A1&token_type_hint=refresh_token` | Fallback sang access token | Thu hồi A1 nếu AS hỗ trợ |
| `token=UNKNOWN&token_type_hint=refresh_token` | Không tìm thấy trong các loại hỗ trợ | HTTP `200` cho client hợp lệ |

Nếu một custom provider chỉ tìm theo hint rồi trả `200` khi không thấy, **refresh token còn active có thể không được thu hồi**. Đây là lỗi triển khai quan trọng cần có negative test.

### 4.2. Không nhầm với lỗi `unsupported_token_type`

RFC 7009 định nghĩa `unsupported_token_type` khi Authorization Server **không hỗ trợ thu hồi loại token thực tế được trình** — ví dụ server không triển khai access token revocation.

**Sai:** gửi `token_type_hint=typo` ⇒ trả `unsupported_token_type`.

**Đúng:** hint không hợp lệ được **bỏ qua** và không làm thay đổi ý nghĩa response. `unsupported_token_type` nói về **khả năng revoke actual token type**, không phải lỗi đánh máy gợi ý.

### 4.3. Ghi nhớ với Spring

Spring Authorization Server có `OAuth2TokenRevocationAuthenticationToken.getToken()` và `getTokenTypeHint()`. Với `OAuth2AuthorizationService.findByToken(...)` hoặc custom storage, phải kiểm thử hint đúng, hint sai, hint vắng mặt và hint vô nghĩa. Không suy từ tên method rằng lookup đã tự tuân thủ fallback cho mọi custom token type.

## 5. Xác thực client tại revocation endpoint

RFC 7009 yêu cầu confidential client gửi authentication credentials như OAuth 2.0 quy định. AS xác thực client **trước**, rồi xác minh token được cấp **cho chính client đó**, mới được invalidate.

Có hai câu hỏi bảo mật **độc lập**:

1. Caller có thực là `portal-web`, với authentication method và credential đã đăng ký không?
2. Token `R0` có thuộc `OAuth2Authorization` của `portal-web` không?

Một client khác như `billing-job` không được revoke token của `portal-web` chỉ vì nó cũng là confidential client hợp lệ.

### 5.1. Các phương thức trong Spring Authorization Server

Spring Authorization Server 1.5.x hỗ trợ các client authentication methods dùng chung cho token/introspection/revocation:

| Method | Cơ chế | Cần lưu ý |
|---|---|---|
| `client_secret_basic` | Client ID + secret trong HTTP Basic | Dùng TLS, secret store, không log Authorization header |
| `client_secret_post` | Client ID + secret trong form body | Chỉ dùng nếu registration cho phép, tránh body logging |
| `private_key_jwt` | Client JWT assertion ký bằng private key | Validate `iss/sub/aud/exp/nbf`, chống replay |
| `client_secret_jwt` | Assertion ký bằng secret | Cần secret mạnh và lifetime ngắn |
| `tls_client_auth` | Chứng thư PKI của client tại mTLS | Kiểm tra certificate chain và identity mapping |
| `self_signed_tls_client_auth` | Certificate được đăng ký trong client JWKS | Kiểm tra certificate đã đăng ký, không tin certificate tùy ý |
| `none` | Public client không có client secret | Cần xác minh behavior/policy, không coi `client_id` tự khai là proof bảo mật |

Không nhúng client secret trong JavaScript của SPA hoặc mobile app rồi gọi nó là confidential client. Public-client revocation cần được AS xử lý theo chính sách phù hợp với threat model và đúng phiên bản triển khai; RFC 7009 có phần riêng về rủi ro public clients.

### 5.2. Token ownership phải gắn với RegisteredClient

Một kiểm tra ở server thường là:

~~~text
registeredClient.id của caller đã xác thực
    ==
authorization.registeredClientId của token được tra cứu
~~~

Không dùng email người dùng, client name hiển thị hay `client_id` chưa xác thực thay cho kiểm tra này. Nếu token thuộc client khác thì không sửa record, không thu hồi phiên của người khác và không rò nội dung token.

### 5.3. PKCE không thay client authentication

PKCE chứng minh client giữ `code_verifier` tương ứng `code_challenge` khi đổi authorization code. Nó **không phải** phương thức xác thực confidential client tại revocation endpoint, cũng không tự chứng minh quyền thu hồi mọi token.

DPoP và mTLS có thể được dùng để sender-constrain token theo profile; nếu revocation policy yêu cầu proof-of-possession, phải triển khai kiểm tra đúng giao thức. Không suy rằng gửi một DPoP-bound token trong `token` tự động chứng minh quyền sở hữu private key.

## 6. Thuật toán xử lý request an toàn

~~~mermaid
flowchart TD
    A["POST HTTPS /oauth2/revoke"] --> B["Kiểm tra form và token bắt buộc"]
    B -->|Thiếu/sai| Bad["invalid_request"]
    B --> C["Client authentication đúng registration"]
    C -->|Thất bại| AuthErr["invalid_client"]
    C --> D["Tìm token; hint chỉ giúp lookup"]
    D --> E{"Token tồn tại?"}
    E -->|Không| Ok["HTTP 200, không leak trạng thái"]
    E -->|Có| F{"Thuộc registered client này?"}
    F -->|Không| Forbidden["Từ chối, không thay đổi token"]
    F -->|Có| G{"Token type được hỗ trợ?"}
    G -->|Không| Unsupported["unsupported_token_type"]
    G -->|Có| H["Invalidate token + cascade theo policy"]
    H --> I["Commit authorization/token state"]
    I --> Ok
~~~

Thứ tự xử lý:

1. Client lấy `revocation_endpoint` từ discovery/registration đáng tin và xác minh HTTPS.
2. Server nhận POST form, kiểm tra `token`, content type và giới hạn độ dài/cỡ body.
3. Client authentication filter xác định RegisteredClient và method hợp lệ.
4. AS tra token theo hint nếu cần, nhưng fallback khi hint sai/không tìm được.
5. Nếu tìm thấy, AS kiểm tra token/authorization thuộc RegisteredClient đang gọi.
6. Áp dụng revocation policy cho loại token và các token/grant liên quan.
7. Thực hiện invalidate và lưu state bền vững; thiết kế transaction nếu có tranh chấp.
8. Trả HTTP 200 cho token đã revoke/unknown từ client hợp lệ, hoặc OAuth error tương ứng.

**Không làm:** một controller công khai nhận `token` rồi tìm trong DB và xóa tùy ý mà không biết caller là client nào.

## 7. HTTP response: 200, lỗi giao thức và 503

### 7.1. HTTP 200 cho token đã thu hồi hoặc token lạ

RFC 7009 §2.2 yêu cầu HTTP 200 cho revocation thành công **hoặc token không hợp lệ**. Client không được phụ thuộc body để biết token có từng tồn tại hay không.

~~~http
HTTP/1.1 200 OK
Cache-Control: no-store
Pragma: no-cache
Content-Length: 0
~~~

Không tạo API revocation trả:

~~~json
{
  "token_exists": true,
  "revoked_now": true,
  "subject": "user-123"
}
~~~

Response đó có thể bị dùng để dò token/identity. Đừng biến thành công theo RFC thành một oracle tiết lộ trạng thái nội bộ.

### 7.2. Bảng xử lý

| Trường hợp | Kết quả kỳ vọng | Giải thích |
|---|---|---|
| Client đúng, token active thuộc nó | `200` | Token được invalidated |
| Client đúng, token unknown | `200` | Tránh xác nhận token có tồn tại |
| Client đúng, token đã expired/revoked | `200` | Idempotent về trạng thái mong muốn |
| Hint sai/vô nghĩa | Vẫn xử lý token thật | Hint không ràng buộc |
| Thiếu `token` hoặc form sai | `invalid_request` hoặc lỗi protocol phù hợp | Request không đủ đầu vào |
| Secret/JWT client assertion sai | `invalid_client` (thường 401) | Caller chưa được xác thực |
| Token thuộc client khác | Từ chối theo policy, không revoke | Không cho cross-client mutation |
| AS không hỗ trợ revoke actual token type | `unsupported_token_type` | Không phải lỗi hint |
| Server trả HTTP 503 | Token có thể vẫn active | Retry có backoff theo RFC |

**Không trả 200 cho mọi sai sót.** Nếu client authentication thất bại mà server trả 200, client có thể tưởng token đã an toàn trong khi AS chưa thực hiện revocation.

### 7.3. Timeout và retry

Nếu revocation endpoint trả `503`, RFC 7009 yêu cầu client **giả định token vẫn có thể tồn tại** và chỉ retry sau khoảng hợp lý; dùng `Retry-After` khi có.

Nếu request timeout sau khi đã gửi, client không biết AS đã commit revoke chưa. Vì revoke có ngữ nghĩa idempotent, retry có kiểm soát có thể phù hợp, với:

- Giới hạn số lần, exponential backoff và jitter.
- Không ghi raw token vào log của retry.
- Không coi HTTP timeout là xác nhận token đã bị thu hồi.
- Nếu user đã logout, chặn tiếp tục sử dụng credential **ở client** theo local policy, nhưng không nhầm local cleanup với server revocation.
- Có cơ chế reconcile/retry server-side cho hệ thống cần bảo đảm thu hồi.

## 8. Cấu hình Spring Authorization Server 1.5.x

Spring Authorization Server cung cấp Revocation Endpoint mặc định tại `/oauth2/revoke` qua `AuthorizationServerSettings`; **không cần bật OIDC**. Các thành phần liên quan:

| Thành phần | Vai trò |
|---|---|
| `OAuth2TokenRevocationEndpointFilter` | Nhận request revocation |
| `OAuth2TokenRevocationAuthenticationConverter` | Trích `token`/`token_type_hint` từ form |
| `OAuth2TokenRevocationAuthenticationToken` | Mang token string, hint và client principal |
| `OAuth2TokenRevocationAuthenticationProvider` | Xử lý revocation |
| `OAuth2ClientAuthenticationFilter` | Xác thực client theo registration |
| `OAuth2AuthorizationService` | Tìm/lưu authorization và metadata token |
| `OAuth2TokenRevocationEndpointConfigurer` | Mở rộng converters/providers/response handlers |
| `AuthorizationServerSettings` | Đường dẫn endpoint, issuer |

### 8.1. SecurityFilterChain

Ví dụ cấu hình Spring Authorization Server 1.5.x/Spring Security 6.x:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.core.annotation.Order;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.oauth2.server.authorization.config.annotation.web.configurers.OAuth2AuthorizationServerConfigurer;
import org.springframework.security.oauth2.server.authorization.settings.AuthorizationServerSettings;
import org.springframework.security.web.SecurityFilterChain;

class AuthorizationServerRevocationConfig {

    @Bean
    @Order(1)
    SecurityFilterChain authorizationServerChain(HttpSecurity http)
            throws Exception {
        OAuth2AuthorizationServerConfigurer server =
                OAuth2AuthorizationServerConfigurer.authorizationServer();

        http.securityMatcher(server.getEndpointsMatcher())
                .with(server, authorizationServer ->
                        authorizationServer.tokenRevocationEndpoint(
                                Customizer.withDefaults()))
                .authorizeHttpRequests(authorize ->
                        authorize.anyRequest().authenticated());
        return http.build();
    }

    @Bean
    AuthorizationServerSettings authorizationServerSettings() {
        return AuthorizationServerSettings.builder()
                .issuer("https://login.example.vn")
                .tokenRevocationEndpoint("/oauth2/revoke")
                .build();
    }
}
~~~

Đây là filter-chain skeleton, chưa phải toàn bộ Authorization Server có thể chạy độc lập: cần RegisteredClientRepository, OAuth2AuthorizationService, token generator, signing keys nếu phát JWT và các chain/user authentication khác. `tokenRevocationEndpoint(Customizer.withDefaults())` cho thấy điểm mở rộng; endpoint này vốn được cấu hình trong chuỗi endpoint mặc định.

### 8.2. RegisteredClient dùng Client Secret Basic

~~~java
import org.springframework.security.oauth2.core.AuthorizationGrantType;
import org.springframework.security.oauth2.core.ClientAuthenticationMethod;
import org.springframework.security.oauth2.server.authorization.client.RegisteredClient;
import org.springframework.security.oauth2.server.authorization.settings.ClientSettings;

static RegisteredClient portalClient(String encodedSecret) {
    return RegisteredClient.withId("registration-portal-web")
            .clientId("portal-web")
            .clientSecret(encodedSecret)
            .clientAuthenticationMethod(
                    ClientAuthenticationMethod.CLIENT_SECRET_BASIC)
            .authorizationGrantType(
                    AuthorizationGrantType.AUTHORIZATION_CODE)
            .authorizationGrantType(
                    AuthorizationGrantType.REFRESH_TOKEN)
            .redirectUri(
                    "https://portal.example.vn/login/oauth2/code/portal")
            .scope("orders.read")
            .clientSettings(ClientSettings.builder()
                    .requireProofKey(true)
                    .build())
            .build();
}
~~~

`encodedSecret` phải là giá trị đã hash bằng PasswordEncoder, không phải secret bản rõ. Lưu client qua RegisteredClientRepository. **Không tồn tại grant type `REVOCATION` cần thêm vào RegisteredClient.** Revocation không phải OAuth grant.

### 8.3. Tùy biến có kiểm soát

`OAuth2TokenRevocationEndpointConfigurer` hỗ trợ:

- `revocationRequestConverter(...)` / `revocationRequestConverters(...)`.
- `authenticationProvider(...)` / `authenticationProviders(...)`.
- `revocationResponseHandler(...)`.
- `errorResponseHandler(...)`.

Nếu thêm custom AuthenticationProvider để áp policy tenant/token family, đừng cho provider mới bỏ qua bước xác thực client và kiểm tra ownership. Một provider được thêm **sau** provider mặc định có thể không chạy khi provider mặc định đã xử lý request; phải xác minh thứ tự và behavior thực tế.

Không tự triển khai một `@PostMapping("/oauth2/revoke")` công khai đi vòng qua filter chain của Spring.

### 8.4. Discovery

AS có thể công bố:

~~~json
{
  "issuer": "https://login.example.vn",
  "revocation_endpoint": "https://login.example.vn/oauth2/revoke",
  "revocation_endpoint_auth_methods_supported": [
    "client_secret_basic",
    "private_key_jwt",
    "tls_client_auth"
  ]
}
~~~

Đây chỉ là mẫu metadata; các giá trị phải khớp cấu hình runtime. Client lấy địa chỉ từ nguồn tin cậy và verify HTTPS/issuer. Không lấy revocation URL từ query do user cung cấp, tránh SSRF/token exfiltration.

## 9. Ownership và metadata token trong OAuth2AuthorizationService

`OAuth2Authorization` lưu RegisteredClient ID, principal, grant, scopes và token metadata. `OAuth2AuthorizationService.findByToken(token, tokenType)` có thể tra authorization theo giá trị token. `OAuth2Authorization.Token.isActive()` dựa trên thời hạn và metadata invalidated.

**Điểm bảo mật cốt lõi:** sau khi tìm được token, AS phải so:

~~~text
authenticatedRegisteredClient.getId()
       ==
authorization.getRegisteredClientId()
~~~

Không so token theo username/email để quyết định quyền thu hồi, vì nhiều OAuth client có thể cùng sử dụng một user.

### 9.1. Mẫu service kiểm tra ownership

~~~java
import org.springframework.security.oauth2.server.authorization.OAuth2Authorization;
import org.springframework.security.oauth2.server.authorization.OAuth2AuthorizationService;
import org.springframework.security.oauth2.server.authorization.client.RegisteredClient;

final class OwnedTokenLookup {
    private final OAuth2AuthorizationService authorizationService;

    OwnedTokenLookup(OAuth2AuthorizationService authorizationService) {
        this.authorizationService = authorizationService;
    }

    OAuth2Authorization findOwned(
            RegisteredClient authenticatedClient,
            String rawToken) {

        // null: lookup qua các token types mà store hỗ trợ.
        OAuth2Authorization authorization =
                authorizationService.findByToken(rawToken, null);

        if (authorization == null) {
            return null; // 200 cho unknown token sau auth hợp lệ.
        }

        if (!authorization.getRegisteredClientId()
                .equals(authenticatedClient.getId())) {
            throw new SecurityException("Revocation not permitted");
        }
        return authorization;
    }
}
~~~

Đây là ví dụ **chỉ đọc và kiểm tra ownership**, không phải controller hay provider hoàn chỉnh. `authenticatedClient` phải đến từ client authentication đã thành công. Nếu custom storage không hỗ trợ `findByToken(token, null)` cho mọi token type, hãy triển khai fallback theo RFC 7009 thay vì coi hint là bộ lọc bắt buộc.

### 9.2. Vô hiệu token sau khi đã xác thực và authorize

Spring Authorization Server 1.4+ có API `OAuth2Authorization.Builder.invalidate(OAuth2Token)`. Ví dụ skeleton ở **tầng service nội bộ**:

~~~java
import org.springframework.security.oauth2.core.OAuth2Token;
import org.springframework.security.oauth2.server.authorization.OAuth2Authorization;
import org.springframework.security.oauth2.server.authorization.OAuth2AuthorizationService;

// Chỉ chạy SAU khi đã xác thực client và kiểm tra ownership!
OAuth2Authorization.Token<? extends OAuth2Token> entry =
        authorization.getToken(rawToken);

if (entry != null && entry.isActive()) {
    OAuth2Authorization updated = OAuth2Authorization.from(authorization)
            .invalidate(entry.getToken())
            .build();
    authorizationService.save(updated);
}
~~~

Đoạn mã này **không thay thế provider mặc định**: chưa xử lý cascade, transaction/CAS, errors, audit, token type policy, race với refresh, đồng bộ multi-node. Chỉ dùng để hiểu cách token metadata được đánh dấu. Với `JdbcOAuth2AuthorizationService`, lưu dữ liệu trong DB **không tự chứng minh** mọi thao tác read–invalidate–save là nguyên tử giữa nhiều pod.

## 10. Tác động lên JWT, opaque token và logout

### 10.1. Refresh token revocation và token family

Khi AS revoke refresh token `R0`, refresh grant dùng R0 phải bị từ chối. Nếu AS áp dụng rotation, client có thể đang giữ successor `R1`; khi user muốn kết thúc **toàn authorization grant**, phải xác định cơ chế revoke token family/authorization thay vì chỉ đánh dấu chuỗi R0 đã consumed.

Chính sách thu hồi có thể ảnh hưởng access token dựa cùng grant. Hãy đo/kiểm chứng đúng phiên bản provider và storage, không coi HTTP 200 là bằng chứng mọi token cùng family đã tự biến mất.

### 10.2. JWT access token

Một Resource Server chỉ xác minh JWT offline (signature, issuer, audience, expiry, scope) **không tự biết** AS vừa invalidate token. JWT đã phát vẫn có chữ ký hợp lệ đến `exp`. Nếu yêu cầu thu hồi nhanh, cân nhắc TTL ngắn, introspection/status check, denylist hoặc propagation event. Có thể có trễ cache/replication.

### 10.3. Opaque/reference access token

Resource Server dùng introspection có thể nhận `active=false` sau revoke. Nếu API cache introspection response, token vẫn có thể được chấp nhận trong TTL cache. Hãy xác định propagation SLO, TTL và chiến lược cache invalidation.

### 10.4. Local logout và OIDC logout

User bấm đăng xuất khỏi `portal-web` không nhất thiết làm hết hiệu lực phiên SSO của OP. Ngược lại, OIDC RP-Initiated Logout không tự đảm bảo thu hồi tất cả access token/refresh token của mọi client.

Luồng logout có thể gồm: dọn local session, revoke refresh token, xử lý access token/grant theo policy, và nếu cần thì OIDC logout. **Không dùng `token_type_hint=refresh_token` như lệnh logout toàn bộ thiết bị.**

## 11. Concurrency: refresh đồng thời với revoke

Giả sử request A đang đổi `R0` thành `R1`, đồng thời request B yêu cầu revoke `R0`. Nếu hai AS pod đọc snapshot cũ và ghi trạng thái không kiểm phiên bản, có nguy cơ token/grant đã revoked bị “hồi sinh”.

~~~mermaid
sequenceDiagram
    autonumber
    participant C1 as Client refresh request
    participant C2 as Client revoke request
    participant AS1 as AS pod 1
    participant AS2 as AS pod 2
    participant DB as Shared authorization store

    C1->>AS1: POST /oauth2/token (R0)
    C2->>AS2: POST /oauth2/revoke (R0)
    AS1->>DB: Đọc version v1
    AS2->>DB: Đọc version v1
    AS2->>DB: Commit revoke v1->v2
    AS1->>DB: Cố commit rotation từ v1
    DB-->>AS1: CAS conflict / version mismatch
    AS1-->>C1: invalid_grant hoặc lỗi policy
    AS2-->>C2: HTTP 200
~~~

Đây là **mô hình storage có version/CAS do hệ thống thiết kế**, không phải khẳng định Spring mặc định đã tự cấp CAS cho mọi backend.

Những bất biến quan trọng:

- Nếu revoke commit trước, refresh sau phải bị từ chối theo policy.
- Nếu refresh commit trước, revoke grant/family cần xử lý successor đã được cấp.
- Không cho stale writer ghi đè trường revoked bằng trạng thái active.
- Mọi AS pod dùng shared storage hoặc replication đúng ràng buộc consistency.
- Không cho client retry refresh token đã revoked chỉ vì một request khác vẫn đang xử lý.
- Revocation của một token không được lan sang token của RegisteredClient khác.

## 12. Ma trận kiểm thử

| # | Tình huống | Kỳ vọng |
|---|---|---|
| 1 | Revoke refresh token R0 với hint đúng | HTTP 200; R0 inactive |
| 2 | Revoke access token A0 với hint đúng | HTTP 200 nếu server hỗ trợ |
| 3 | Revoke R0 **không có** hint | R0 vẫn inactive |
| 4 | Revoke R0 với hint sai `access_token` | Fallback, R0 vẫn inactive |
| 5 | Revoke A0 với hint sai `refresh_token` | Fallback, A0 inactive nếu được hỗ trợ |
| 6 | Revoke R0 với hint `made_up_type` | Bỏ qua hint, vẫn xử lý token |
| 7 | Revoke token ngẫu nhiên/không tồn tại | HTTP 200 sau auth hợp lệ |
| 8 | Revoke token đã revoked/expired | HTTP 200, không rò trạng thái cũ |
| 9 | Thiếu `token` | `invalid_request`/lỗi request phù hợp |
| 10 | `token=` rỗng | Từ chối request không hợp lệ |
| 11 | Form có hai trường `token` | Không được revoke nhầm; test converter validation |
| 12 | Confidential client thiếu secret | `invalid_client`; token không đổi |
| 13 | Secret sai/đã rotate | `invalid_client`; token không đổi |
| 14 | Basic khác method đăng ký | Client authentication thất bại |
| 15 | JWT client assertion sai aud/exp | Client authentication thất bại |
| 16 | mTLS certificate không khớp client | TLS/OAuth client authentication thất bại |
| 17 | Client A revoke token của client B | Không revoke, token B còn active |
| 18 | Cùng user, hai client khác nhau | Không cho A điều khiển grant của B |
| 19 | Public client method `none` | Đúng policy; không cho arbitrary cross-client revoke |
| 20 | Actual token type không được hỗ trợ | `unsupported_token_type` nếu áp dụng |
| 21 | Token endpoint/service DB trả 503 | Client coi token có thể vẫn active |
| 22 | Hint sai trên custom authorization store | Token vẫn bị tìm và revoke |
| 23 | Revoke R0 rồi gọi refresh R0 | `invalid_grant`/lỗi hợp lệ; không cấp token |
| 24 | Revoke A0, RS chỉ verify JWT offline | Xác định rõ cửa sổ token có thể còn dùng |
| 25 | Revoke R0 và cascade A0 | Kiểm tra chính sách thực tế tại AS/RS |
| 26 | Revocation và refresh đồng thời | Không hồi sinh grant sau revoke commit |
| 27 | Revoke tại AS pod 1, lookup ở pod 2 | State đồng nhất sau commit |
| 28 | Cross-tenant/cross-user request | Không xâm phạm authorization khác |
| 29 | Gateway log/tracing bật | Không lộ raw token, client secret, Authorization header |
| 30 | Request quá lớn/đồng loạt | Rate limit, size bound, không gây DoS |

### 12.1. Test sai hint đúng cách

Không test hint sai bằng cách **revoke cùng token lần thứ hai**, vì token đã inactive rồi. Phải tạo một fresh token R2, gửi `token_type_hint=access_token`, xác minh:

1. Endpoint xác thực client đúng.
2. Token R2 vẫn được tìm trong refresh-token store.
3. Server trả 200.
4. Thử refresh R2 không còn được cấp token mới.
5. Authorization metadata ghi nhận invalidation đúng; không ảnh hưởng client khác.

### 12.2. Test ownership với Java (skeleton)

~~~java
@Test
void cannotRevokeAnotherClientsToken() {
    RegisteredClient clientA = registeredClient("portal-web");
    RegisteredClient clientB = registeredClient("billing-job");

    String tokenB = issueRefreshTokenFor(clientB);

    assertThrows(SecurityException.class, () ->
            ownedTokenLookup.findOwned(clientA, tokenB));

    assertTrue(isTokenActive(tokenB));
}
~~~

Các helper và fixture `registeredClient(...)`, `issueRefreshTokenFor(...)` và `isTokenActive(...)` do test suite của ứng dụng định nghĩa. Test này chỉ kiểm ownership helper; integration test còn phải gửi HTTP thật qua Spring filter chain để kiểm tra client authentication.

## 13. Troubleshooting, audit và runbook

| Triệu chứng | Nguyên nhân có thể | Xử lý |
|---|---|---|
| 404 ở `/oauth2/revoke` | Path sai, security matcher/proxy routing | Kiểm tra AuthorizationServerSettings/metadata |
| `invalid_client` | Credential sai, client auth method không khớp | Kiểm tra RegisteredClient, secret hash và method |
| `invalid_request` | Form thiếu token, sai encoding, token rỗng | Kiểm tra Content-Type và parser |
| HTTP 200 nhưng R0 vẫn refresh được | Lookup hint sai, save không bền vững, race | Kiểm tra service/store, transaction và tests |
| HTTP 200 nhưng JWT A0 vẫn gọi API được | RS verify offline, không nhận revocation | TTL ngắn, introspection/denylist/caching |
| Hint lạ trả `unsupported_token_type` | Implementation hiểu hint là actual type | Sửa theo RFC 7009 |
| Client A làm token B inactive | Thiếu ownership check ở custom provider | Chặn rollout và kiểm tra authorization matching |
| 503 tăng | DB down, replica lag hoặc quá tải | Retry có backoff; không tuyên bố token đã revoked |
| Cùng request được/không trên các pod | Store hoặc config lệch | Shared persistence và kiểm tra rollout |
| Token value xuất hiện trong APM | Logging body/header quá rộng | Redact, xoay credential bị lộ và audit |

### 13.1. Metrics và log

Các metrics gợi ý: `revocation_requests_total{outcome}`, `revocation_client_auth_failures_total`, `revocation_lookup_miss_total` (nội bộ), `revocation_latency_seconds`, `revocation_store_failures_total`, `revocation_cascade_errors_total`, `revocation_race_conflicts_total`.

Audit có thể dùng request/correlation ID, client ID được phép, loại token **đã xác minh** và outcome. Không đặt raw access token, refresh token, Basic header, email, user ID hoặc high-cardinality identifiers vào metric labels; không lưu body nguyên văn.

### 13.2. Khi nghi token bị đánh cắp

1. Xác định client/issuer/token type và phạm vi sự cố mà không chụp raw credential vào ticket.
2. Xác thực quyền của caller/đơn vị vận hành đối với authorization.
3. Revoke token/authorization theo policy, có thể cần cả token family và các access token liên quan.
4. Đánh giá token còn được chấp nhận ở Resource Server nào (JWT offline/introspection/cache).
5. Nếu client secret/private key/mTLS certificate cũng bị lộ, rotate credential; token revocation không thay key rotation.
6. Thử lại các negative cases (refresh sau revoke, API call sau revoke, multi-node).
7. Lưu audit timeline và hoàn thiện root-cause analysis.

## 14. Checklist production và tự đánh giá

- [ ] `/oauth2/revoke` chỉ được công bố qua HTTPS, nhận POST form body và không log token.
- [ ] Có đúng trường `token` bắt buộc; không nhầm với tên tham số `refresh_token`.
- [ ] `token_type_hint` chỉ tối ưu lookup; sai/thiếu/vô nghĩa phải được xử lý theo RFC.
- [ ] `unsupported_token_type` chỉ dành cho actual type không hỗ trợ revoke.
- [ ] Confidential client authentication theo RegisteredClient, không để request ẩn danh tự revoke token.
- [ ] So `authorization.registeredClientId` với client đã xác thực trước mutation.
- [ ] Public client được xử lý theo chính sách riêng; không coi PKCE hay client_id tự khai là confidential client authentication.
- [ ] HTTP 200 cho token unknown/already revoked từ client hợp lệ; không tiết lộ token exists.
- [ ] Thất bại authentication, malformed request và backend outage không bị che thành 200 giả.
- [ ] Cascade refresh/access token và revocation propagation được tài liệu hóa, kiểm thử.
- [ ] JWT offline, opaque introspection và cache behavior đã được đánh giá.
- [ ] Race refresh/revoke, shared store nhiều pod và transaction consistency có negative tests.
- [ ] Metadata issuer/revocation endpoint/auth methods khớp runtime.
- [ ] Không bật GET/JSONP revocation legacy nếu không bắt buộc; CORS theo allowlist.
- [ ] Có audit, metrics, alert và runbook mà không log secrets.
- [ ] Client không tiếp tục dùng token sau khi nhận 200; xử lý 503/timeout với retry giới hạn.

**Câu hỏi tự kiểm tra**

1. Tại sao revoke refresh token vẫn phải gửi trường `token` thay vì `refresh_token`?
2. Khi R0 là refresh token nhưng hint là `access_token`, RFC 7009 yêu cầu server xử lý ra sao?
3. Vì sao hint vô nghĩa không phải lý do để trả `unsupported_token_type`?
4. Token không tồn tại nhận 200 khác gì client auth sai?
5. Tại sao xác thực client hợp lệ vẫn chưa đủ nếu không so token ownership?
6. PKCE có thể thay client authentication tại revocation endpoint không?
7. Revoke refresh token có bắt buộc làm JWT A0 đã phát chết tức thì ở RS không?
8. Client nên xử lý 503 và timeout thế nào?
9. Khi refresh và revoke cùng R0 xảy ra đồng thời, cần bất biến transaction nào?
10. Làm sao test hint fallback mà không bị “false pass” do token đã revoked trước đó?

## Tài liệu tham khảo

- [RFC 7009 — OAuth 2.0 Token Revocation](https://www.rfc-editor.org/rfc/rfc7009.html): §2.1–2.2 về `token`, `token_type_hint`, xác thực client, HTTP 200/503 và lỗi.
- [RFC 6749 — OAuth 2.0 Authorization Framework](https://www.rfc-editor.org/rfc/rfc6749.html): client authentication, token types và OAuth errors.
- [RFC 7662 — OAuth 2.0 Token Introspection](https://www.rfc-editor.org/rfc/rfc7662.html): trạng thái `active` và introspection.
- [RFC 8414 — OAuth 2.0 Authorization Server Metadata](https://www.rfc-editor.org/rfc/rfc8414.html): metadata `revocation_endpoint` và auth methods.
- [RFC 9700 — Best Current Practice for OAuth 2.0 Security](https://www.rfc-editor.org/rfc/rfc9700.html): bảo vệ client và refresh token.
- [Spring Authorization Server 1.5.8 — Protocol Endpoints](https://docs.spring.io/spring-authorization-server/reference/protocol-endpoints.html): `OAuth2TokenRevocationEndpointConfigurer` và providers.
- [Spring Authorization Server 1.5.8 — Configuration Model](https://docs.spring.io/spring-authorization-server/reference/configuration-model.html): revocation path và client authentication.
- [Spring Authorization Server 1.5.8 — Core Model](https://docs.spring.io/spring-authorization-server/reference/core-model-components.html): `OAuth2Authorization` và `OAuth2AuthorizationService`.
- [Spring Authorization Server 1.5.8 — OAuth2Authorization.Builder API](https://docs.spring.io/spring-authorization-server/reference/api/java/org/springframework/security/oauth2/server/authorization/OAuth2Authorization.Builder.html): `invalidate(OAuth2Token)`.
- [Spring Authorization Server 1.5.8 — OAuth2TokenRevocationAuthenticationToken API](https://docs.spring.io/spring-authorization-server/reference/api/java/org/springframework/security/oauth2/server/authorization/authentication/OAuth2TokenRevocationAuthenticationToken.html): `getToken()` và `getTokenTypeHint()`.
