# OAuth2User, OidcUser và phân biệt access token với ID token

## 1. Bối cảnh: đăng nhập OAuth2/OIDC trong Spring WebFlux

Một ứng dụng Spring Security Reactive có thể cung cấp nút “Đăng nhập bằng Google/Keycloak/Okta/Microsoft Entra ID”. Người dùng rời ứng dụng đến trang của nhà cung cấp danh tính, xác thực, rồi được chuyển hướng về ứng dụng. Sau login, ứng dụng cần biết **ai đã đăng nhập**, trong khi một số chức năng cần **gọi API** của nhà cung cấp hoặc resource server khác.

Hai nhu cầu này sử dụng những đối tượng khác nhau:

- **OAuth2User:** principal chứa thông tin người dùng và authorities sau OAuth2 Login.
- **OidcUser:** một dạng OAuth2User cho OpenID Connect (OIDC), có thêm ID token và thông tin UserInfo.
- **ID token:** kết quả xác thực end-user dành cho **OIDC client**, không phải credential tiêu chuẩn gửi tới business API.
- **Access token:** credential ủy quyền dành cho **resource server/API** thích hợp.
- **Refresh token:** credential tùy chọn dùng ở token endpoint để cấp access token mới.
- **OAuth2AuthorizedClient:** đối tượng Spring gắn ClientRegistration, principal name và access/refresh tokens.
- **OAuth2AuthenticationToken:** Authentication của login; không đồng nghĩa với OAuth2AuthorizedClient.
- **WebSession:** có thể duy trì trạng thái login trên browser, nhưng thời hạn phiên khác thời hạn các token OAuth.

Ví dụ nguy hiểm:

~~~java
// KHÔNG LÀM: ID token không thay thế access token.
String idTokenValue = oidcUser.getIdToken().getTokenValue();
webClient.get()
        .uri("https://orders-api.example.test/orders")
        .headers(h -> h.setBearerAuth(idTokenValue));
~~~

Đây là đoạn phản ví dụ không độc lập. ID token có audience thông thường là **client_id của ứng dụng đăng nhập**, không phải audience mà API đích yêu cầu; chấp nhận nhầm ID token có thể tạo lỗ hổng token-substitution.

### Mục tiêu học tập

Sau bài học, bạn có thể:
1. Phân biệt OAuth 2.0 và OIDC.
2. Hiểu quan hệ `OidcUser extends OAuth2User` và cách dùng `@AuthenticationPrincipal`.
3. Hiểu token type, issuer, audience, subject, scope, expiry, nonce.
4. Chọn đúng token cho login client và resource server.
5. Lấy access token qua OAuth2AuthorizedClient thay vì principal.
6. Mapping authorities/roles an toàn.
7. Xây ứng dụng Java 17 Spring Boot WebFlux và thử principal bằng WebTestClient.
8. Nhận diện khác biệt Reactive với Servlet, test mock với login thực, quản lý session/refresh/logout.

Bài thuộc nhóm **Đăng nhập OAuth2/OIDC** trong module Spring Security - reactive.

## 2. OAuth 2.0 khác OpenID Connect thế nào?

OAuth 2.0 là một **authorization framework**: một client được ủy quyền truy cập protected resources của resource owner theo các quyền được cấp. Bản thân OAuth 2.0 không đưa ra một giao thức định danh end-user hoàn chỉnh dành cho client.

OpenID Connect 1.0 là lớp **authentication/identity** bên trên OAuth 2.0. Nó thêm ID token, một số claims, UserInfo endpoint, discovery và quy tắc xác minh authentication result.

| Nội dung | OAuth 2.0 | OpenID Connect (OIDC) |
| --- | --- | --- |
| Mục tiêu | Cấp quyền truy cập protected resources | Xác thực end-user với client |
| Token đặc trưng | Access token; refresh token tùy chọn | Access token và ID token; refresh token tùy chọn |
| Principal trong Spring OAuth2 Login | OAuth2User | OidcUser (cũng là OAuth2User) |
| Claims người dùng | Provider-specific attributes | ID token và UserInfo claims theo OIDC |
| Scope biểu thị OIDC | Không bắt buộc có openid | `openid` trong requested scopes |
| Token gửi tới resource server | Access token đúng audience/scope | Vẫn là **access token** |
| Audience ID token | Không áp dụng | OIDC client_id |
| Kiểm chứng định danh | Không suy ra từ một access token tùy ý | Theo validation OIDC (signature, iss, aud, exp, nonce khi áp dụng...) |

Trong Spring Security OAuth2 Login, `openid` trong scope của client registration sẽ dẫn tới OIDC-specific processing khi provider tương thích. Không mặc định mọi provider có OAuth2 login đều cấp ID token.

### 2.1. “Đăng nhập OAuth2” là thuật ngữ sản phẩm, không phải token type

Một sản phẩm có thể gọi chung “OAuth login” cho cả:
- OAuth2-only social login lấy user info từ protected endpoint;
- OIDC Login với ID token được xác minh;
- OAuth2 Authorization Code để cho phép client gọi API khác.

Khi lập trình, phải biết **luồng nào đang được sử dụng**. Không tự suy đoán user đã được xác thực chỉ vì nhận được một chuỗi access token.

## 3. Luồng browser Authorization Code + OIDC

~~~text
Browser                   Spring WebFlux Client                OIDC Provider
   |                              |                                  |
   | GET /oauth2/authorization/demo                                |
   |----------------------------->|                                  |
   |                              | Chuẩn bị client_id, scope=openid  |
   |                              | redirect_uri, state, nonce, PKCE  |
   | 302 đến /authorize           |                                  |
   |<-----------------------------|                                  |
   | GET /authorize...                                               |
   |---------------------------------------------------------------->|
   |                 User xác thực/consent                            |
   | 302 redirect ?code=...&state=...                                 |
   |<----------------------------------------------------------------|
   | GET /login/oauth2/code/demo                                    |
   |----------------------------->|                                  |
   |                              | Verify state                     |
   |                              | Đổi code tại token endpoint      |
   |                              |--------------------------------->|
   |                              | access_token, id_token           |
   |                              |<---------------------------------|
   |                              | Xác minh ID token theo OIDC      |
   |                              | UserInfo (nếu dùng): access token|
   |                              | Tạo OidcUser, Authentication     |
   |                              | Lưu OAuth2AuthorizedClient       |
   | Cookie/redirect sau login    |                                  |
   |<-----------------------------|                                  |
   | GET /api/me dùng login session                                 |
   |----------------------------->|                                  |
   | OIDC principal safe DTO        |                                  |
   |<-----------------------------|                                  |
~~~

Các endpoint thường thấy của Spring Security WebFlux:
- Bắt đầu login: `/oauth2/authorization/{registrationId}`.
- Nhận authorization code: `/login/oauth2/code/{registrationId}`.
- Một số cấu hình cung cấp login page mặc định.

Spring Security dùng Authorization Code Grant. State, nonce và PKCE là những cơ chế khác nhau:
- `state` giúp liên kết authorization response với request khởi tạo.
- `nonce` gắn ID token với authentication request, giảm replay/mix-up.
- `PKCE` bảo vệ authorization code bằng code verifier/challenge, đặc biệt cần cho public clients và phù hợp với khuyến nghị OAuth hiện đại.
- Không dùng một giá trị nonce/state cố định cho tất cả phiên.
- Luồng chuyển hướng cần HTTPS, redirect URI được đăng ký và kiểm soát reverse proxy đúng cách.

**ID token không đi tới business API trong luồng trên.** Backend muốn gọi API thì sử dụng access token trong OAuth2AuthorizedClient.

## 4. OAuth2User: dữ liệu principal và authorities

Import:

~~~java
import org.springframework.security.oauth2.core.user.OAuth2User;
~~~

Interface này cung cấp:
- `getName()`: tên định danh principal theo implementation/provider.
- `getAttributes()`: map attributes.
- `getAttribute(String name)`: giá trị thuộc tính theo key.
- `getAuthorities()`: danh sách GrantedAuthority mà Spring Security gắn sau login/mapping.

Ví dụ snippet controller:

~~~java
@GetMapping("/api/me")
public Mono<Map<String, Object>> profile(
        @AuthenticationPrincipal OAuth2User user) {
    return Mono.just(Map.of(
            "name", user.getName(),
            "attributeNames", user.getAttributes().keySet()));
}
~~~

Đây không phải file độc lập: cần class @RestController, imports và security configuration. Không serialize trực tiếp `user` hoặc trả toàn bộ attributes vì có thể chứa PII/thuộc tính nội bộ.

### 4.1. Name attribute khác nhau giữa provider

Một OAuth2 provider có field `id`, provider khác có `login` hoặc `user_name`. `DefaultOAuth2User` dùng `nameAttributeKey` để biết field nào là principal name.

~~~java
// Snippet trong một method Java đã có imports thích hợp:
OAuth2User user = new DefaultOAuth2User(
        List.of(new SimpleGrantedAuthority("OAUTH2_USER")),
        Map.of("provider_id", "42", "display_name", "Learner"),
        "provider_id");

System.out.println(user.getName()); // 42
~~~

Các import: `List`, `Map`, `SimpleGrantedAuthority`, `OAuth2User` và `DefaultOAuth2User`. Tên này không tự đồng nghĩa email, username nội bộ hay ID toàn cục.

### 4.2. OAuth2User không phải access-token container

`getAttributes()` phản ánh user attributes; **không** phải token exchange result. Không lấy `getAttribute("access_token")` rồi giả định đây là token OAuth hợp lệ, không trả các thuộc tính chưa kiểm chứng thành role/privilege.

Nếu cần access token được cấp cho client, xem `OAuth2AuthorizedClient` ở phần 9.

## 5. OidcUser là một OAuth2User chuyên biệt

Import:

~~~java
import org.springframework.security.oauth2.core.oidc.user.OidcUser;
~~~

`OidcUser extends OAuth2User`. Nó bổ sung:
- `getIdToken()`: trả `OidcIdToken` của login.
- `getUserInfo()`: trả `OidcUserInfo` khi có.
- `getClaims()`: tập claims OIDC có thể tổng hợp ID token/UserInfo.
- Các accessors chuẩn như `getSubject()`, `getEmail()`, `getPreferredUsername()` tùy claims.

Một controller nhận `OAuth2User` **có thể** được inject `OidcUser` khi login thực dùng OIDC. Điều này phù hợp với kế thừa interface.

~~~java
if (user instanceof OidcUser oidc) {
    String subject = oidc.getIdToken().getSubject();
    // Dùng subject làm provider identity theo policy.
}
~~~

**Không ép kiểu** `(OidcUser) user` cho mọi OAuth2User nếu app có provider OAuth2-only. Hãy kiểm tra `instanceof`, dùng endpoint OIDC-specific được bảo vệ rõ ràng hoặc tạo adapter user-identity nội bộ.

### 5.1. OidcIdToken

ID token có thể chứa claims:

~~~json
{
  "iss": "https://identity.example.test",
  "sub": "user-pairwise-42",
  "aud": "web-client-1",
  "iat": 1760000000,
  "exp": 1760003600,
  "nonce": "request-specific-nonce",
  "email": "learner@example.test",
  "email_verified": true
}
~~~

Đây chỉ là **JSON payload minh họa**, không phải JWT đã ký và không thể dùng login. ID token trong OIDC là JWT, cần xác minh signature và claims theo OIDC trước khi tin.

Các phương thức chính:
- `oidc.getIdToken().getTokenValue()`: token raw — **không đưa ra frontend, log hay analytics**.
- `oidc.getIdToken().getSubject()`: subject đã được provider khai báo trong token.
- `oidc.getIdToken().getClaims()`: claims của ID token, có thể chứa PII.

Trong project thật, chỉ expose DTO tối thiểu với quyền truy cập thích hợp.

### 5.2. OidcUserInfo

OIDC UserInfo endpoint trả claims về end-user cho OIDC client, thường được gọi bằng **access token**. `OidcReactiveOAuth2UserService` có thể sử dụng `DefaultReactiveOAuth2UserService` để tải UserInfo.

**Quan trọng:** OIDC yêu cầu `sub` của UserInfo response phù hợp với `sub` trong ID token; nếu không, không được sử dụng thông tin UserInfo. Đây là biện pháp chống trộn thông tin hai tài khoản.

Không phải provider nào cũng trả `email`, `picture` hoặc `name`. Ngay cả `email_verified=true` cũng không có nghĩa user được cấp quyền ADMIN trong ứng dụng của bạn.

### 5.3. DefaultOidcUser

`DefaultOidcUser` là implementation phổ biến chứa authorities, ID token, UserInfo và tùy chọn key cho principal name. Không tự tạo DefaultOidcUser từ JSON request do client gửi rồi đánh dấu user đã xác thực. Hãy để Spring Security/OIDC provider thực hiện validation trước.

## 6. Bảng phân biệt ba token

| Đặc tính | Access token | ID token | Refresh token |
| --- | --- | --- | --- |
| Mục đích | Ủy quyền gọi protected resource | Xác thực người dùng với OIDC client | Xin access token mới |
| Bên nhận dự kiến | Resource server/API | Client (relying party) | Authorization server/token endpoint |
| Nơi dùng | `Authorization: Bearer ...` tới API thích hợp | Token response của OIDC login; client validate | Refresh-token grant qua token endpoint |
| Dạng | Opaque hoặc JWT, theo provider | JWT ký theo OIDC | Theo provider, thường opaque |
| Thông tin | Resource audience, scopes, expiry | iss, sub, aud, exp, iat, nonce khi áp dụng | Không phải user profile |
| Được lấy ở Spring | `OAuth2AuthorizedClient.getAccessToken()` | `OidcUser.getIdToken()` | `OAuth2AuthorizedClient.getRefreshToken()` khi có |
| Có nên đưa vào URL/query/log? | Không | Không | Không |
| Có thể thay nhau? | **Không** | **Không** | **Không** |

**JWT là định dạng, không xác định mục đích của token.** Access token có thể là JWT, nhưng nó không tự trở thành ID token; ID token có JWT shape cũng không phải access token phù hợp để API chấp nhận.

### 6.1. Access token có audience của API

Ví dụ:
- ID token: `aud = "web-client-1"`.
- Access token: `aud = "orders-api"`, scope `orders.read`.

Backend gọi `orders-api` bằng access token đó; resource server xác minh audience/trust/lifetime/scope theo policy. Nếu API cho phép ID token `aud=web-client-1`, nó đã bỏ qua ranh giới audience.

### 6.2. Token expiration không phải WebSession timeout

Thời hạn ID token, access token, refresh token và login session có thể khác nhau. Một browser session vẫn hợp lệ không tự làm access token mới có hiệu lực; authorized client manager có thể refresh access token theo provider/policy. Refresh token không gửi tới business API.

## 7. Các claims ID token cần hiểu

### Issuer — iss

`iss` là identifier của OIDC Provider đã phát token. Client phải tin đúng provider đã cấu hình, không chấp nhận JWT từ issuer bất kỳ chỉ vì cấu trúc giống nhau.

### Subject — sub

`sub` là ID người dùng trong namespace của issuer. OIDC hỗ trợ public và pairwise subjects; không giả định nó bằng email hay có thể so sánh giữa nhiều issuers.

Khóa liên kết tài khoản hợp lý thường dùng:

~~~text
Trusted external identity = (issuer, subject)
~~~

Không lấy email làm khóa duy nhất vì email có thể đổi, thiếu hoặc thuộc account khác trong một số bối cảnh.

### Audience — aud

ID token `aud` phải phù hợp với `client_id` của relying party. Khi aud có nhiều phần tử, còn phải xem quy tắc liên quan `azp` theo OIDC. **Đây là lý do API khác không nên chấp nhận ID token của web client.**

### Expiry và issued-at — exp, iat

`exp` là hạn chấp nhận token; `iat` là thời điểm phát hành. Client kiểm tra theo OIDC validation, thời gian hệ thống và clock-skew policy. Không chỉ lấy JWT payload decode rồi bỏ qua validation.

### Nonce — nonce

`nonce` gắn authentication request với ID token, chống replay trong flow có nonce. Khi đã gửi nonce, cần xác minh token trả về mang giá trị phù hợp theo protocol. Không hard-code nonce giống nhau giữa các request.

### Email, email_verified, acr, amr

- `email` có thể thiếu/đổi.
- `email_verified` phản ánh việc provider đã xác minh email theo policy của họ; **không phải role entitlement**.
- `acr` và `amr` có thể diễn tả mức/kiểu xác thực nếu provider hỗ trợ; sử dụng cho step-up cần policy rõ ràng, không tin tự động.
- Không dựa vào các claims optional để bỏ qua object/tenant authorization.

## 8. Xác minh ID token: decode không đủ

Một JWT thường có chuỗi `header.payload.signature`. Decode Base64URL có thể xem payload, nhưng **không** chứng minh:
- JWS signature hợp lệ.
- Issuer tin cậy.
- Audience đúng client.
- `exp`/`iat` còn hợp lệ.
- Nonce phù hợp.
- Thuật toán ký đúng policy.
- Key rotation/JWKS hợp lệ.

Spring Security OIDC Login có các thành phần như `ReactiveOidcIdTokenDecoderFactory` và `ReactiveJwtDecoder` để xác minh ID token, cùng logic OIDC phù hợp.

Flow cần:
1. Tạo authorization request có state và các bảo vệ theo client.
2. Nhận authorization code callback và xác nhận state.
3. Đổi code với token endpoint tin cậy.
4. Kiểm tra chữ ký và claims ID token.
5. Nếu dùng UserInfo, đối chiếu subject.
6. Chỉ sau đó tạo OidcUser/Authentication và login session.

Không viết custom code lấy `id_token` từ JSON do browser gửi rồi gọi `new UsernamePasswordAuthenticationToken(..., authorities)` mà bỏ các bước OIDC. Không disable signature/audience validation để chữa một lỗi cấu hình provider.

## 9. OAuth2AuthenticationToken so với OAuth2AuthorizedClient

### 9.1. Authentication sau login

`OAuth2AuthenticationToken` chứa principal, authorities và authorized client registration ID. Ví dụ snippet:

~~~java
if (authentication instanceof OAuth2AuthenticationToken oauth) {
    OAuth2User principal = oauth.getPrincipal();
    String registrationId = oauth.getAuthorizedClientRegistrationId();
}
~~~

**Nó không cung cấp `getAccessToken()` để bạn dùng như authorized client.** Registration ID cho biết client/provider nào liên quan đến login.

### 9.2. OAuth2AuthorizedClient

`OAuth2AuthorizedClient` gắn:
- ClientRegistration.
- Principal name.
- `OAuth2AccessToken`.
- `OAuth2RefreshToken` nếu được cấp.

Những thành phần Reactive dùng để quản lý:
- `ServerOAuth2AuthorizedClientRepository`: persistence theo request/server web context.
- `ReactiveOAuth2AuthorizedClientService`: ứng dụng quản lý authorized clients.
- `ReactiveOAuth2AuthorizedClientManager`: phối hợp authorization, refresh/re-authorization và lưu trữ.

Không serialize object này như JSON trong endpoint profile vì có thể chứa cả access token và refresh token.

### 9.3. Lấy metadata access token trong WebFlux

Snippet không nằm trong project demo độc lập ở phần 13:

~~~java
@GetMapping("/api/token-metadata")
public Mono<Map<String, Object>> metadata(
        @RegisteredOAuth2AuthorizedClient("demo")
        OAuth2AuthorizedClient client) {
    OAuth2AccessToken token = client.getAccessToken();
    return Mono.just(Map.of(
            "tokenType", token.getTokenType().getValue(),
            "scopes", token.getScopes(),
            "hasExpiration", token.getExpiresAt() != null));
}
~~~

Cần imports `@RegisteredOAuth2AuthorizedClient`, `OAuth2AuthorizedClient`, `OAuth2AccessToken`, `Map`, `Mono` và một authorized client thật cho registration `demo`. **Không trả `token.getTokenValue()`**. Ngay cả scope metadata cũng cần đánh giá có nên đưa ra frontend không.

### 9.4. Dùng access token với WebClient

Trong Reactive stack, `ServerOAuth2AuthorizedClientExchangeFilterFunction` giúp gắn access token cho các outbound requests đã chọn:

~~~java
// Snippet @Bean cần manager được cấu hình hợp lệ:
@Bean
WebClient securedWebClient(
        ReactiveOAuth2AuthorizedClientManager manager) {
    var filter =
            new ServerOAuth2AuthorizedClientExchangeFilterFunction(manager);
    return WebClient.builder().filter(filter).build();
}
~~~

Khi dùng, cung cấp registration ID hoặc OAuth2AuthorizedClient phù hợp theo API. Không đặt `setDefaultOAuth2AuthorizedClient(true)` toàn cục nếu không kiểm soát mọi remote URL; token có thể bị gửi tới endpoint không cần hoặc không tin cậy.

Manual snippet chỉ khi có access token đúng resource:

~~~java
return webClient.get()
        .uri("https://orders-api.example.test/orders")
        .headers(h -> h.setBearerAuth(
                authorizedClient.getAccessToken().getTokenValue()))
        .retrieve()
        .bodyToMono(String.class);
~~~

Đây là snippet không độc lập; `authorizedClient` phải được cấp/quản lý bởi hệ thống đúng user, đúng client registration và đúng API audience.

## 10. OAuth2 Login, OIDC Login và Resource Server khác nhau

| Chức năng Spring Security | Đầu vào chính | Principal/Authentication thường gặp | Mục tiêu |
| --- | --- | --- | --- |
| OAuth2 Login (non-OIDC) | Authorization Code + OAuth2 provider user info | OAuth2AuthenticationToken + OAuth2User | Login người dùng |
| OIDC Login | Authorization Code, ID token, UserInfo | OAuth2AuthenticationToken + OidcUser | Login có OIDC ID token |
| OAuth2 Resource Server JWT | Incoming Bearer JWT **access token** | JwtAuthenticationToken | Bảo vệ API |
| Resource Server opaque token | Incoming Bearer opaque access token | BearerTokenAuthentication hoặc principal dạng OAuth2AuthenticatedPrincipal | Bảo vệ API |
| OAuth2 Client WebClient | Authorized client / access token | OAuth2AuthorizedClient | Gọi API bên ngoài |

Đừng dùng `@AuthenticationPrincipal OidcUser` ở API chỉ cấu hình Resource Server JWT rồi thắc mắc vì sao principal là Jwt/Authentication type khác. Hai đường xử lý có thể kết hợp trong một app, nhưng cần rõ security chains và route scope.

### 10.1. API Resource Server cần kiểm tra access token của chính nó

Snippet kiến trúc (không thuộc project runnable dưới):

~~~java
return http
        .authorizeExchange(ex -> ex
                .pathMatchers("/api/orders/**")
                    .hasAuthority("SCOPE_orders.read")
                .anyExchange().denyAll())
        .oauth2ResourceServer(oauth2 ->
                oauth2.jwt(Customizer.withDefaults()))
        .build();
~~~

Cần `spring-boot-starter-oauth2-resource-server`, cấu hình decoder issuer/JWKS/audience và authorization thích hợp. OIDC login client không tự thay thế JWT Resource Server validation.

## 11. Authorities và scopes không tự biến thành role nội bộ

Spring Security có thể gắn authorities `OAUTH2_USER` hoặc `OIDC_USER`, các `SCOPE_...` và quyền khác tùy mapping. `hasRole("ADMIN")` thường kiểm tra `ROLE_ADMIN`, **không tương đương** `hasAuthority("ADMIN")`.

~~~java
// Snippet trong authorizeExchange:
.pathMatchers("/api/admin/**").hasRole("ADMIN")
.pathMatchers("/api/reports/**").hasAuthority("SCOPE_reports.read")
~~~

Nhưng OIDC scopes như `openid`, `email`, `profile` không có nghĩa người dùng được đọc báo cáo của người khác.

Cách mapping authorities an toàn:
1. Xác thực OIDC issuer/subject và nhận login principal từ library đã validate.
2. Tra quyền từ database/entitlement service **đáng tin** của ứng dụng.
3. Gắn role theo tenant/account mapping, không dựa trên email suffix.
4. Kiểm tra ownership/tenant tại service đối với từng resource.
5. Viết negative tests cho người đã login nhưng thiếu quyền.

Anti-pattern:

~~~java
// SAI: email thuộc một domain không đủ là bằng chứng có quyền ADMIN.
if (email.endsWith("@company.example.test")) {
    authorities.add(new SimpleGrantedAuthority("ROLE_ADMIN"));
}
~~~

Email có thể thiếu, chưa verify, hoặc không biểu thị membership/entitlements nội bộ. Ngay cả `email_verified=true` cũng không thay security review/tenant policy.

Spring Security Reactive có `GrantedAuthoritiesMapper`, `ReactiveOAuth2UserService` và `OidcReactiveOAuth2UserService` để ánh xạ authorities, nhưng cần giữ lại những quyền hợp lệ sau khi gọi UserInfo/entitlement endpoints.

## 12. WebFlux Reactive khác Servlet

| WebFlux/Reactive | Servlet/MVC | Vai trò |
| --- | --- | --- |
| ServerHttpSecurity | HttpSecurity | Security configuration |
| SecurityWebFilterChain | SecurityFilterChain | Filter chain |
| ReactiveClientRegistrationRepository | ClientRegistrationRepository | Client registrations |
| ReactiveOAuth2AuthorizedClientService | OAuth2AuthorizedClientService | Client token persistence |
| ServerOAuth2AuthorizedClientRepository | OAuth2AuthorizedClientRepository | Authorized clients theo web request |
| ReactiveOAuth2UserService | OAuth2UserService | Load user attributes |
| DefaultReactiveOAuth2UserService | DefaultOAuth2UserService | Non-OIDC user service |
| OidcReactiveOAuth2UserService | OidcUserService | OIDC user service |
| ServerOAuth2AuthorizedClientExchangeFilterFunction | Servlet WebClient counterpart | Truyền access token đến API |

`OAuth2User`, `OidcUser` và các token model là abstractions **chung** của Spring Security, nhưng security filters/user services/authorized-client persistence dùng loại Reactive.

Trong WebFlux, không dùng `HttpServletRequest` hoặc tự `block()` trong user service. `DefaultReactiveOAuth2UserService` dùng `WebClient`; hãy compose các `Mono` khi tùy biến mapping.

## 13. Project Java 17+ runnable: quan sát OAuth2User và OidcUser

Ví dụ này dùng **Java 17, Spring Boot 3.5.7, WebFlux và Spring Security Reactive**. Nó có OAuth2 client registration tĩnh trỏ đến hostname **minh họa**, để app/kiểm thử có thể được khởi tạo mà không cần kết nối tới OIDC Discovery ở bước bootstrap.

Mục tiêu:
- App khởi động local, có `GET /public/ping`.
- API chưa có login trả 401 theo chủ đích.
- `GET /api/me` trả **DTO chọn lọc** cho OAuth2User hoặc OidcUser.
- `GET /api/oidc` minh họa chỉ dùng OIDC-specific feature khi đúng principal type.
- `WebTestClient` dùng `mockOAuth2Login` / `mockOidcLogin` để test mà không cần provider thật.

**Không thể hoàn thành login thật với `idp.example.test`!** Muốn login browser thật phải thay provider URLs/issuer, client ID/secret và redirect URI bằng thông số tin cậy. Test mock không phải bằng chứng ID token đã được ký và xác minh.

### 13.1. Cấu trúc

~~~text
reactive-oidc-user-demo/
├── settings.gradle
├── build.gradle
└── src/
    ├── main/java/demo/
    │   ├── DemoApplication.java
    │   ├── SecurityConfig.java
    │   └── IdentityController.java
    ├── main/resources/
    │   └── application.yml
    └── test/java/demo/
        └── OAuth2OidcPrincipalTest.java
~~~

### 13.2. settings.gradle

~~~groovy
rootProject.name = 'reactive-oidc-user-demo'
~~~

### 13.3. build.gradle

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.5.7'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'demo'
version = '0.0.1-SNAPSHOT'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-client'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

`spring-boot-starter-oauth2-client` dùng cho login/client API. `spring-boot-starter-oauth2-resource-server` là dependency khác cho incoming Bearer API access tokens.

### 13.4. application.yml cho bài học local

~~~yaml
server:
  port: 8080
  reactive:
    session:
      cookie:
        http-only: true

spring:
  application:
    name: reactive-oidc-user-demo
  security:
    oauth2:
      client:
        registration:
          demo:
            provider: demo
            client-id: DEMO_CLIENT_ID
            client-secret: DEMO_CLIENT_SECRET
            authorization-grant-type: authorization_code
            redirect-uri: "{baseUrl}/login/oauth2/code/{registrationId}"
            scope:
              - openid
              - profile
              - email
        provider:
          demo:
            authorization-uri: https://idp.example.test/authorize
            token-uri: https://idp.example.test/token
            jwk-set-uri: https://idp.example.test/jwks.json
            user-info-uri: https://idp.example.test/userinfo
            user-name-attribute: sub
~~~

Provider URLs là placeholder documentation và **không có IdP hoạt động**. Không có `issuer-uri` ở config offline để tránh một OIDC discovery call tới hostname giả ngay lúc khởi tạo. **Không triển khai production** với cấu hình này; production phải cấu hình provider issuer/JWKS đáng tin, validation issuer/audience, client secret an toàn và HTTPS.

### 13.5. DemoApplication.java

`src/main/java/demo/DemoApplication.java`:

~~~java
package demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class DemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }
}
~~~

### 13.6. SecurityConfig.java

`src/main/java/demo/SecurityConfig.java`:

~~~java
package demo;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.http.HttpStatus;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.web.server.SecurityWebFilterChain;
import org.springframework.security.web.server.authentication.HttpStatusServerEntryPoint;

@Configuration
@EnableWebFluxSecurity
public class SecurityConfig {

    @Bean
    SecurityWebFilterChain securityFilterChain(ServerHttpSecurity http) {
        return http
                .authorizeExchange(ex -> ex
                        .pathMatchers(HttpMethod.GET, "/public/ping")
                                .permitAll()
                        .pathMatchers(HttpMethod.GET, "/api/me", "/api/oidc")
                                .authenticated()
                        .anyExchange().denyAll())
                .oauth2Login(Customizer.withDefaults())
                .exceptionHandling(ex -> ex.authenticationEntryPoint(
                        new HttpStatusServerEntryPoint(
                                HttpStatus.UNAUTHORIZED)))
                .build();
    }
}
~~~

- `oauth2Login` bật login client hỗ trợ OAuth2/OIDC.
- `/api/me`, `/api/oidc` yêu cầu authentication; `anyExchange().denyAll()` chặn business routes chưa khai báo.
- `HttpStatusServerEntryPoint` cố ý trả **401** thay vì chuyển hướng API tới trang login. Interactive login vẫn bắt đầu tại `/oauth2/authorization/demo`.
- CSRF vẫn bật theo mặc định, cần bảo vệ POST/session-based browser flows khi bổ sung.
- Đây là cấu hình học tập; trong ứng dụng thật kiểm thử login callback, default login page, logout và entrypoint trên từng security chain.

### 13.7. IdentityController.java

`src/main/java/demo/IdentityController.java`:

~~~java
package demo;

import java.util.LinkedHashMap;
import java.util.Map;

import org.springframework.http.HttpStatus;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.oauth2.core.oidc.user.OidcUser;
import org.springframework.security.oauth2.core.user.OAuth2User;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ResponseStatusException;

import reactor.core.publisher.Mono;

@RestController
public class IdentityController {

    @GetMapping("/public/ping")
    public Mono<String> ping() {
        return Mono.just("pong");
    }

    @GetMapping("/api/me")
    public Mono<Map<String, Object>> me(
            @AuthenticationPrincipal OAuth2User principal) {

        if (principal == null) {
            return Mono.error(new ResponseStatusException(
                    HttpStatus.UNAUTHORIZED, "OAuth2 login required"));
        }

        Map<String, Object> view = new LinkedHashMap<>();
        view.put("principalType",
                principal instanceof OidcUser ? "OIDC" : "OAUTH2");
        view.put("principalName", principal.getName());
        view.put("authorities", principal.getAuthorities().stream()
                .map(GrantedAuthority::getAuthority)
                .sorted()
                .toList());

        if (principal instanceof OidcUser oidc) {
            view.put("idTokenSubject",
                    oidc.getIdToken().getSubject());
            view.put("hasUserInfo", oidc.getUserInfo() != null);
        }

        // Không serialize whole principal / raw tokens / PII.
        return Mono.just(view);
    }

    @GetMapping("/api/oidc")
    public Mono<Map<String, Object>> oidcOnly(
            @AuthenticationPrincipal OAuth2User principal) {

        if (!(principal instanceof OidcUser oidc)) {
            return Mono.error(new ResponseStatusException(
                    HttpStatus.FORBIDDEN, "OIDC principal required"));
        }

        return Mono.just(Map.of(
                "principalType", "OIDC",
                "subject", oidc.getIdToken().getSubject(),
                "hasUserInfo", oidc.getUserInfo() != null));
    }
}
~~~

Đây là DTO **có chủ đích không trả** `getIdToken().getTokenValue()`, `OAuth2AuthorizedClient`, access/refresh tokens hoặc toàn bộ claims/attributes. `subject`/`principalName` là identifiers minh họa; production cần privacy policy phù hợp vì chúng vẫn có thể được xem là thông tin người dùng.

`/api/oidc` trả 403 khi principal không phải OidcUser **chỉ để chứng minh phân biệt kiểu**, không có nghĩa mọi endpoint nghiệp vụ phải kiểm tra Java type thay vì authorization/roles.

Code dùng Java 17 pattern matching `instanceof` và không block Reactor event loop.

## 14. Chạy app và các điều kiện quan sát

Tại thư mục có `build.gradle`:

~~~bash
gradle test
gradle bootRun
~~~

Nếu dùng Gradle Wrapper: `./gradlew` trên Linux/macOS hoặc `gradlew.bat` trên Windows. Các lệnh này dành cho người học tự chạy; **không khẳng định đã thực thi build/test tại đây**.

### 14.1. Public ping

~~~bash
curl -i http://localhost:8080/public/ping
~~~

Kỳ vọng HTTP **200**, body:

~~~text
pong
~~~

### 14.2. Chưa đăng nhập

~~~bash
curl -i http://localhost:8080/api/me
~~~

Kỳ vọng HTTP **401 Unauthorized** theo entry point đã cấu hình. Với OIDC login thông thường, route protected có thể redirect tới login page tùy policy, nhưng ví dụ API này chủ động trả 401.

### 14.3. Interactive login cần IdP thật

Bắt đầu tại:

~~~text
http://localhost:8080/oauth2/authorization/demo
~~~

Với provider demo `idp.example.test` không tồn tại, không thể hoàn thành authorization-code callback. Để chạy login thật, cấu hình issuer/credentials/redirect URI thật như phần 16. Các test dưới đây không cần provider mạng vì mock principal.

## 15. WebTestClient: mô phỏng OAuth2User và OidcUser

Spring Security Test Reactive có `mockOAuth2Login()` và `mockOidcLogin()`. Chúng thiết lập SecurityContext và principal mô phỏng, **không verify chữ ký ID token hoặc gọi IdP**. Vì vậy, chúng rất phù hợp cho **controller tests**, không thay tests giao thức OIDC đầy đủ.

`src/test/java/demo/OAuth2OidcPrincipalTest.java`:

~~~java
package demo;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.ApplicationContext;
import org.springframework.test.web.reactive.server.WebTestClient;

import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.mockOAuth2Login;
import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.mockOidcLogin;
import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.springSecurity;

@SpringBootTest
class OAuth2OidcPrincipalTest {

    @Autowired
    ApplicationContext context;

    private WebTestClient client;

    @BeforeEach
    void setUp() {
        client = WebTestClient.bindToApplicationContext(context)
                .apply(springSecurity())
                .configureClient()
                .build();
    }

    @Test
    void publicPingWorks() {
        client.get().uri("/public/ping")
                .exchange()
                .expectStatus().isOk()
                .expectBody(String.class).isEqualTo("pong");
    }

    @Test
    void anonymousUserReceives401() {
        client.get().uri("/api/me")
                .exchange()
                .expectStatus().isUnauthorized();
    }

    @Test
    void oauth2LoginHasGenericPrincipal() {
        client.mutateWith(mockOAuth2Login()
                    .attributes(attrs -> attrs.put("sub", "oauth-user-42")))
                .get().uri("/api/me")
                .exchange()
                .expectStatus().isOk()
                .expectBody()
                .jsonPath("$.principalType").isEqualTo("OAUTH2")
                .jsonPath("$.principalName").isEqualTo("oauth-user-42")
                .jsonPath("$.idTokenSubject").doesNotExist();
    }

    @Test
    void oidcLoginHasIdTokenSubject() {
        client.mutateWith(mockOidcLogin()
                    .idToken(token -> token.claim("sub", "oidc-user-24")))
                .get().uri("/api/me")
                .exchange()
                .expectStatus().isOk()
                .expectBody()
                .jsonPath("$.principalType").isEqualTo("OIDC")
                .jsonPath("$.idTokenSubject").isEqualTo("oidc-user-24");
    }

    @Test
    void oauth2OnlyPrincipalCannotUseOidcDemoEndpoint() {
        client.mutateWith(mockOAuth2Login())
                .get().uri("/api/oidc")
                .exchange()
                .expectStatus().isForbidden();
    }

    @Test
    void oidcPrincipalCanUseOidcDemoEndpoint() {
        client.mutateWith(mockOidcLogin()
                    .idToken(token -> token.claim("sub", "oidc-user-99")))
                .get().uri("/api/oidc")
                .exchange()
                .expectStatus().isOk()
                .expectBody()
                .jsonPath("$.principalType").isEqualTo("OIDC")
                .jsonPath("$.subject").isEqualTo("oidc-user-99");
    }

    @Test
    void profileDoesNotReturnTokenValues() {
        client.mutateWith(mockOidcLogin())
                .get().uri("/api/me")
                .exchange()
                .expectStatus().isOk()
                .expectBody()
                .jsonPath("$.accessToken").doesNotExist()
                .jsonPath("$.idTokenValue").doesNotExist()
                .jsonPath("$.refreshToken").doesNotExist();
    }
}
~~~

Dự kiến **7 tests** kiểm tra các response của controller. Test mô phỏng OAuth2-only có kiểu principal khác OIDC; test `mockOidcLogin()` cấp `OidcIdToken` có subject do bạn khai báo. Những token trong mock **không phải token có chữ ký thật**.

**Không dùng test này để khẳng định issuer/audience/nonce validation an toàn.** Cần thêm integration tests với OIDC Provider được cấu hình cho testing, JWKS hợp lệ và cases negative.

### 15.1. Test authority mapping

Có thể mở rộng bằng:

~~~java
// Snippet trong test method, cần import SimpleGrantedAuthority.
client.mutateWith(mockOidcLogin()
        .authorities(new SimpleGrantedAuthority("ROLE_READER")))
        .get().uri("/api/me")
        .exchange()
        .expectStatus().isOk();
~~~

Mục đích chỉ là tạo một authentication mock có authority cụ thể. Không suy từ đây rằng provider thật luôn cấp ROLE_READER.

### 15.2. Những test integration cần có với IdP thực/mô phỏng

- Authorization redirect, state mismatch, nonce mismatch.
- ID token sai signature, issuer, audience, exp/iat.
- JWKS rotation và lỗi HTTP/TLS.
- UserInfo subject mismatch.
- Multi-tenant/issuer restrictions.
- Access token có wrong audience/scope ở resource server.
- Login/logout, expired session, refresh token rotation.
- Không rò token/claims trong API response hoặc logs.

## 16. Chuyển config sang IdP thật

Thay **toàn bộ nhóm provider.demo** placeholder ở `application.yml` bằng một provider tin cậy, thường dùng `issuer-uri` với OIDC Discovery.

~~~yaml
spring:
  security:
    oauth2:
      client:
        registration:
          demo:
            provider: demo
            client-id: YOUR_CLIENT_ID_FROM_SECRET_MANAGER
            client-secret: YOUR_CLIENT_SECRET_FROM_SECRET_MANAGER
            authorization-grant-type: authorization_code
            redirect-uri: "{baseUrl}/login/oauth2/code/{registrationId}"
            scope:
              - openid
              - profile
              - email
        provider:
          demo:
            issuer-uri: https://your-oidc-issuer.example.test
~~~

Đây là **cấu hình minh họa thay thế**, không phải credentials thật. Trong production dùng environment variables/secret manager thay chuỗi ví dụ, HTTPS và issuer đúng provider; metadata discovery có thể truy cập mạng lúc khởi tạo.

Checklist:
1. Tạo client registration ở provider; dùng đúng client ID/secret/redirect URI.
2. Bật login/OIDC với scope `openid`.
3. Xác minh callback URL, TLS/reverse proxy forwarded headers và session cookie Secure/HttpOnly/SameSite.
4. Giữ OIDC issuer/audience/signature/nonce validation.
5. Hạn chế UserInfo scopes và claims cần thiết.
6. Dùng audience/resource-specific access token cho APIs.
7. Không lưu secrets trong Git, logs, query strings hoặc browser source.
8. Tùy mô hình, dùng PKCE và bảo vệ state/session theo yêu cầu provider.
9. Kiểm tra login trên nhiều instances, shared session store và token persistence.
10. Thiết kế logout ở ứng dụng và IdP theo nhu cầu riêng.

## 17. Access token dành cho API, ID token dành cho client

Nếu provider cấp:
- `id_token` với `aud=web-client`.
- `access_token` dành cho `orders-api` với scope `orders.read`.

Khi backend gọi resource server:

~~~http
GET /orders HTTP/1.1
Host: orders-api.example.test
Authorization: Bearer <access-token-for-orders-api>
~~~

Không dùng:

~~~http
Authorization: Bearer <id-token-for-web-client>
~~~

Resource server phải kiểm tra token theo semantics của nó. Không chấp nhận JWT chỉ vì chữ ký issuer đúng mà bỏ qua audience, scope, expiry hoặc token profile; một signed ID token vẫn không cấp quyền API.

OIDC UserInfo endpoint cũng là protected resource sử dụng **access token**, không nhận ID token làm credential theo protocol.

## 18. Login session, token expiry và logout

Ba đồng hồ không đồng nhất:

| Thành phần | Lifecycle |
| --- | --- |
| WebSession/login session | Cookie, idle timeout, invalidate/logout, có thể được gia hạn khi hoạt động |
| Access token | Expiry, scopes/audience, refresh/re-authorization |
| ID token | Exp và OIDC validation phục vụ xác thực lúc login |

Ví dụ user đăng nhập lúc 10:00, access token TTL 10 phút, WebSession idle timeout 30 phút: đến 10:12, browser session có thể còn nhưng authorized client cần refresh access token trước khi gọi API. Không được mang ID token sang API thay cho access token đã hết hạn.

### 18.1. Logout tại app không nhất thiết logout ở IdP

WebFlux session invalidation xóa trạng thái login cục bộ theo cơ chế hiện hành. OIDC Provider có thể vẫn giữ SSO session, vì vậy lần đăng nhập tiếp theo có thể được tự động xác nhận. Nếu cần Single Logout, xem OIDC RP-Initiated Logout và khả năng provider.

Một hệ thống còn phải xét thu hồi access/refresh tokens nếu threat model hoặc chính sách yêu cầu. Xóa cookie ở browser không thu hồi một token đã bị đánh cắp trước đó.

### 18.2. Bảo vệ authorized-client storage

Access và refresh tokens có thể được lưu trong ServerOAuth2AuthorizedClientRepository/ReactiveOAuth2AuthorizedClientService. Không expose object, không log token, không dùng shared storage không có access controls, không đưa token vào session/URL theo cách gây rò.

## 19. Những sai lầm thường gặp

| Sai lầm | Tác hại | Cách sửa |
| --- | --- | --- |
| Dùng ID token như Bearer access token | Sai audience và mục đích; token substitution | Lấy access token từ AuthorizedClient |
| Coi một access token JWT là ID token | OAuth2 access token không thay giao thức authentication | Dùng OIDC ID token validation |
| Đọc getAttributes() để tìm access token | Principal không phải token store | AuthorizedClient repository/manager |
| Trả OidcUser hoặc ID token value qua JSON | Lộ PII/credentials | DTO tối thiểu |
| Parse JWT không kiểm tra chữ ký | Chấp nhận token giả | Decoder/validator chuẩn |
| Chỉ kiểm chữ ký, không kiểm iss/aud | Chấp nhận token của app/provider khác | Validate issuer/audience/time/nonce |
| Dùng email làm ID duy nhất | Email có thể đổi/chưa verify | Trusted issuer + subject |
| Cấp ADMIN theo email domain | Domain không phải entitlement | Tra quyền từ nguồn tin cậy |
| Ép OAuth2User thành OidcUser | OAuth2-only không có ID token | instanceof hoặc adapter |
| Gửi access token tới mọi WebClient URL | Rò token ngoài trust boundary | Gắn token có chọn lọc |
| Nhầm JwtAuthenticationToken với OidcUser | API Resource Server khác login client | Tách hai security roles |
| Coi scope openid là quyền đọc dữ liệu | Openid kích hoạt OIDC, không phải role | Authorization/ownership riêng |
| Dùng client secret trong frontend | Không giữ bí mật được | Server-side secret/PKCE theo client |
| Disable issuer/nonce để login thành công | Bỏ bảo vệ anti-replay/trust | Sửa provider/config |
| Nghĩ access token TTL = session TTL | Đăng nhập và quyền gọi API lệch | Kiểm tra từng lifecycle |
| Coi mockOidcLogin là ID token valid | Mock bỏ validation/IdP | Integration test riêng |
| Block trong Reactive user service | Chặn event loop | Dùng Mono/flatMap |
| Chỉ logout local nhưng cần SSO logout | IdP session còn | OIDC logout policy |
| Không bảo vệ token logs/storage | Credential leak | Redaction, encryption, ACLs |

## 20. Troubleshooting theo triệu chứng

### 20.1. Principal trả OAuth2User thay vì OidcUser

- Client registration có `openid` chưa?
- Provider có OIDC, cấp ID token hợp lệ không?
- Request đang qua oauth2Login hay qua Basic/Resource Server?
- App có custom ReactiveOAuth2UserService thay đổi principal không?
- Controller có xác định đúng authentication principal/type không?

Không cast mù quáng sang OidcUser. Nếu provider OAuth2-only, hãy hỗ trợ OAuth2User; nếu cần OIDC, sửa client/provider flow.

### 20.2. Access token gọi API A được nhưng API B bị 401/403

- Kiểm tra audience của token cho API B.
- Scope/permissions được cấp có đúng không?
- Token đã hết hạn/revoked/refresh cần thiết?
- Authorization header có vô tình chứa ID token?
- Resource Server B có issuer/JWKS/token profile khác?
- AuthorizedClient registration có thuộc đúng user?
- WebClient filter có đưa token của client A tới host B không?

Không giải quyết bằng cách tắt audience validation.

### 20.3. Mock test PASS nhưng browser login FAIL

- Authorization endpoint/redirect URI/callback code/state.
- Client secret/token endpoint authentication.
- OIDC issuer/JWKS/signature/audience/nonce.
- Session cookie Secure/SameSite, reverse proxy TLS.
- Shared session store nếu multi-instance.
- Consent/callback errors từ provider.
- UserInfo sub mismatch.

Mock test không thực hiện OAuth code exchange hoặc token validation; phải test end-to-end với provider tin cậy.

### 20.4. User đã login nhưng thiếu quyền

- `ROLE_ADMIN` khác `OIDC_USER` và `SCOPE_profile`.
- Role mapping/tenant entitlement có được tải từ nguồn tin cậy?
- Route có đúng authorization matcher không?
- Method-level/object-level checks có từ chối?
- POST có CSRF token không?
- Quyền cũ có còn ở session cache không?

Không đổi 403 thành 200 hoặc cấp ADMIN cho mọi user đã OIDC login.

## 21. Checklist kiến trúc và kiểm thử

### OIDC login
- [ ] Có scope openid và provider hỗ trợ OIDC.
- [ ] Dùng Authorization Code, state, nonce/PKCE theo flow.
- [ ] Issuer/JWKS/redirect URI từ nguồn tin cậy.
- [ ] Kiểm signature, iss, aud, exp, iat, nonce khi cần.
- [ ] UserInfo sub khớp ID token.
- [ ] Không tin email/name làm role hoặc khóa định danh duy nhất.
- [ ] Không đưa raw ID token/PII vào response/log.

### OAuth2 client và Resource Server
- [ ] Access token dùng đúng API/resource audience.
- [ ] Token scope phù hợp nghiệp vụ.
- [ ] Lấy token từ OAuth2AuthorizedClient/manager, không từ OidcUser.getIdToken.
- [ ] Refresh token giữ bí mật, không gửi tới business API.
- [ ] Resource server xác minh incoming access token đúng issuer/audience/signature/introspection.
- [ ] Không bật token propagation mặc định tới mọi URL.
- [ ] Không nhầm JwtAuthenticationToken với OAuth2 login principal.

### Authorization, session, vận hành
- [ ] Authorities/roles map từ nguồn tin cậy.
- [ ] Object/tenant ownership được kiểm tra ngoài HTTP matcher.
- [ ] WebSession/logout và token TTL được thiết kế riêng.
- [ ] OIDC SSO logout được xem xét nếu yêu cầu.
- [ ] Cookies Secure/HttpOnly/SameSite và HTTPS phù hợp.
- [ ] OAuth secrets không nằm trong code/frontend/log.
- [ ] CORS/CSRF được đánh giá cho browser-based login.

### Testing
- [ ] mockOAuth2Login và mockOidcLogin có tests riêng.
- [ ] Test anonymous và wrong principal type.
- [ ] Test không lộ ID/access/refresh token.
- [ ] Test authority mapping và ownership.
- [ ] Test issuer/audience/nonce/signature với IdP/validator integration.
- [ ] Test UserInfo sub mismatch.
- [ ] Test refresh/logout/multiple sessions.
- [ ] Không coi WebTestClient mock là xác minh OIDC protocol thật.

## 22. Câu hỏi tự kiểm tra

**1. OAuth2User khác OidcUser thế nào?**

> OAuth2User mô tả principal OAuth2 login với attributes/authorities; OidcUser mở rộng nó với OIDC ID token, UserInfo và claims.

**2. OidcUser có thể truyền vào parameter OAuth2User không?**

> Có, vì OidcUser extends OAuth2User.

**3. Access token dùng để làm gì?**

> Dùng gọi protected resource/API phù hợp audience, scopes và authorization policy.

**4. ID token dành cho ai?**

> Dành cho OIDC client/relying party để xác nhận authentication result, không phải API business.

**5. Access token luôn là JWT không?**

> Không. Nó có thể opaque hoặc JWT tùy provider.

**6. Vì sao ID token payload đọc được chưa đáng tin?**

> Decode không kiểm tra signature, issuer, audience, expiry và nonce.

**7. Muốn gọi API sau login, tìm access token trong OidcUser.getClaims() có đúng không?**

> Không. Lấy từ OAuth2AuthorizedClient hoặc Reactive authorized client manager.

**8. Có nên dùng id_token làm Authorization: Bearer khi gọi UserInfo không?**

> Không. UserInfo dùng access token.

**9. Scope openid có đồng nghĩa ROLE_ADMIN không?**

> Không. Nó bật OIDC; role nội bộ cần entitlement riêng.

**10. Vì sao nên dùng issuer + sub để liên kết account?**

> Vì subject nằm trong namespace issuer; email có thể thay đổi hoặc không có.

**11. mockOidcLogin() có xác minh ký số JWT không?**

> Không. Nó mô phỏng authenticated principal cho test controller.

**12. ID token hết hạn có làm WebSession tự hết hạn ngay không?**

> Không mặc nhiên; mỗi đối tượng có lifecycle khác nhau.

**13. Đăng xuất app có tự kết thúc SSO ở IdP không?**

> Không mặc nhiên. Cần provider logout protocol/config nếu yêu cầu.

**14. Resource Server API thường có principal loại nào với JWT Bearer?**

> Thường là JwtAuthenticationToken, không phải OidcUser của browser login.

**15. Tại sao không setDefaultOAuth2AuthorizedClient(true) cho mọi WebClient call?**

> Nó có thể chuyển token tới URL không cần credential hoặc không đáng tin; chỉ gửi có chọn lọc.

## 23. Tổng kết

Trong **Spring Security Reactive**:

- **`OAuth2User` / `OidcUser` là principal** sau login. OidcUser là một OAuth2User có ID token/UserInfo đặc thù OIDC.
- **ID token dành cho OIDC client**, có issuer, subject, audience, expiry và các claims xác thực. Nó không phải token ủy quyền mặc định cho business API.
- **Access token dành cho resource server** thích hợp và được quản lý cùng OAuth2AuthorizedClient. Khi gọi downstream API, hãy gửi access token đúng audience và scope.
- **Refresh token** chỉ dùng cho token lifecycle tại authorization server, không gửi cho API nghiệp vụ.
- **Authentication không thay authorization**: roles, tenant, ownership và API scopes phải kiểm tra độc lập với việc đã login.

Khi triển khai, hãy dùng API WebFlux Reactive đúng loại, giữ issuer/audience/signature/nonce validation, tách session/token lifetimes, bảo vệ credentials và kiểm thử cả principal mocks lẫn real OIDC flow.

### Tài liệu tham khảo chính thức

- Spring Security — Reactive OAuth2/OIDC Login: https://docs.spring.io/spring-security/reference/6.5/reactive/oauth2/login/index.html
- Spring Security — Reactive OAuth2 Login Core: https://docs.spring.io/spring-security/reference/6.5/reactive/oauth2/login/core.html
- Spring Security — Advanced OAuth2/OIDC Login: https://docs.spring.io/spring-security/reference/6.5/reactive/oauth2/login/advanced.html
- Spring Security — OAuth2 Client Core Interfaces (Reactive): https://docs.spring.io/spring-security/reference/6.5/reactive/oauth2/client/core.html
- Spring Security — Authorized Client Features: https://docs.spring.io/spring-security/reference/6.5/reactive/oauth2/client/authorized-clients.html
- Spring Security — Testing OAuth2/OIDC in WebFlux: https://docs.spring.io/spring-security/reference/6.5/reactive/test/web/oauth2.html
- Spring Security API — OAuth2User: https://docs.spring.io/spring-security/site/docs/6.5.x/api/org/springframework/security/oauth2/core/user/OAuth2User.html
- Spring Security API — OidcUser: https://docs.spring.io/spring-security/site/docs/6.5.x/api/org/springframework/security/oauth2/core/oidc/user/OidcUser.html
- OpenID Connect Core 1.0: https://openid.net/specs/openid-connect-core-1_0.html
- OAuth 2.0 Authorization Framework RFC 6749: https://www.rfc-editor.org/rfc/rfc6749
- OAuth2 JWT Access Token Profile RFC 9068: https://www.rfc-editor.org/rfc/rfc9068
- OAuth 2.0 Security Best Current Practice RFC 9700: https://www.rfc-editor.org/rfc/rfc9700