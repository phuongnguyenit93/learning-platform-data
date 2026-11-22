# 7.5. OAuth2LoginAuthenticationFilter và quá trình tạo Authentication

Trong ứng dụng **Spring Security OAuth 2.0 / OpenID Connect (OIDC) Client chạy trên Servlet**, người dùng bấm “Đăng nhập”, trình duyệt chuyển tới OpenID Provider (OP), rồi quay lại ứng dụng bằng một callback có `code` và `state`. Chính tại callback, **`OAuth2LoginAuthenticationFilter`** tiếp nhận thông điệp HTTP, phối hợp với `AuthenticationManager` và các `AuthenticationProvider` để xác thực kết quả OAuth2/OIDC, rồi tạo ra một đối tượng **`Authentication`** đại diện cho người dùng đã đăng nhập.

Hiểu được filter này giúp trả lời các câu hỏi rất thực tế:

- Tại sao callback `/login/oauth2/code/{registrationId}` không cần controller?
- Filter nhận `code` rồi tạo `OAuth2AuthenticationToken` bằng cách nào?
- Khi nào Spring Security đổi authorization code lấy token, xác minh ID Token và lấy thông tin người dùng?
- `Authentication`, `SecurityContext`, HTTP session và `OAuth2AuthorizedClient` khác nhau ở điểm nào?
- Tại sao login ở OP thành công nhưng ứng dụng vẫn báo chưa đăng nhập?

Bài học sử dụng **Spring Boot 3.x, Spring Security 6.x, Spring MVC/Servlet** và Authorization Code Flow. Tên lớp là các khái niệm công khai của Spring Security; một số chi tiết nội bộ hoặc mặc định có thể thay đổi giữa các phiên bản. Chúng ta tập trung vào trách nhiệm và đường đi của dữ liệu trong framework.

## 1. Vai trò của filter trong sơ đồ đăng nhập

Một luồng OIDC login điển hình có hai phía:

1. **Front-channel qua browser:** redirect từ ứng dụng tới Authorization Endpoint của OP, rồi callback với authorization code.
2. **Back-channel từ backend:** Spring trao đổi code tại Token Endpoint, nhận token và xác minh thông tin OIDC.

`OAuth2LoginAuthenticationFilter` nằm ở **bước callback**. Nó không phải filter đưa browser tới OP lần đầu; bước khởi tạo đó thường do `OAuth2AuthorizationRequestRedirectFilter` thực hiện.

```mermaid
sequenceDiagram
    autonumber
    actor B as Browser
    participant R as OAuth2AuthorizationRequestRedirectFilter
    participant O as OpenID Provider
    participant F as OAuth2LoginAuthenticationFilter
    participant M as AuthenticationManager
    participant P as OAuth2/OIDC AuthenticationProvider
    B->>R: GET /oauth2/authorization/academy
    R->>R: Tạo authorization request; lưu state/context
    R-->>B: 302 tới OP
    B->>O: GET /authorize?client_id=...&state=...
    O-->>B: 302 callback với code & state
    B->>F: GET /login/oauth2/code/academy?code=...&state=...
    F->>F: Lấy authorization request đã lưu
    F->>M: authenticate(OAuth2LoginAuthenticationToken)
    M->>P: Giao cho AuthenticationProvider phù hợp
    P->>O: POST token endpoint (authorization code)
    O-->>P: Access Token + ID Token (OIDC)
    P->>P: Xác minh token; tải và ánh xạ user
    P-->>M: Authentication đã xác thực
    M-->>F: OAuth2LoginAuthenticationToken thành công
    F->>F: Chuyển thành OAuth2AuthenticationToken
    F->>F: Lưu OAuth2AuthorizedClient
    F->>F: Hoàn tất success handling, SecurityContext/session
    F-->>B: 302 về trang đích
    B->>F: Request tiếp theo có session cookie
    Note over B,F: Request mới đi qua SecurityFilterChain; không cần login lại
```

Sơ đồ cố ý tách filter, manager và provider. **Filter điều phối giao tiếp HTTP**, còn provider làm phần cốt lõi của việc xác thực OAuth2/OIDC. Nó cũng cho thấy “có một token do OP phát” chưa đồng nghĩa với “đã có một `Authentication` trong ứng dụng”.

## 2. Các khái niệm cần phân biệt

| Khái niệm | Ý nghĩa trong Spring Security | Ví dụ ở OAuth2/OIDC login |
| --- | --- | --- |
| `Authentication` | Giao diện biểu diễn principal, authorities, credentials/details và trạng thái xác thực | `OAuth2AuthenticationToken` sau login thành công |
| `Principal` | Danh tính người dùng mà ứng dụng hiện nhận diện | `OAuth2User` hoặc `OidcUser` |
| `AuthenticationManager` | Điểm vào xử lý một yêu cầu xác thực | `ProviderManager` chuyển authentication request cho provider hỗ trợ |
| `AuthenticationProvider` | Thành phần xử lý cơ chế xác thực cụ thể | `OAuth2LoginAuthenticationProvider` hoặc `OidcAuthorizationCodeAuthenticationProvider` |
| `SecurityContext` | Vật chứa `Authentication` hiện tại | Gắn với luồng xử lý request và có thể được lưu giữa các request |
| `SecurityContextHolder` | Điểm truy cập context trong quá trình xử lý request | Controller/service đọc người dùng đã xác thực |
| `OAuth2AuthorizedClient` | Dữ liệu gắn client registration và principal với token được cấp | Lưu access token/refresh token (nếu có) để gọi API |
| `HTTP session` | Cơ chế lưu trạng thái giữa các request từ browser | Có thể lưu SecurityContext và thông tin authorization request tạm |

Đối tượng **`Authentication` không đơn giản là access token**. Nó chứa principal, quyền và trạng thái xác thực để Spring Security ra quyết định truy cập. Trong một ứng dụng web, browser thường mang **session cookie** về ứng dụng sau login; access token được backend quản lý riêng qua authorized client.

### 2.1. Các kiểu Authentication xuất hiện trong cùng một flow

Cần chú ý sự biến đổi:

```text
Authorization response (code + state)
             |
             v
OAuth2LoginAuthenticationToken
  - request xác thực chuyển cho AuthenticationManager
  - chứa ClientRegistration và OAuth2AuthorizationExchange
             |
             v
AuthenticationProvider xác thực thành công
  - token, principal và authorities được tạo/đính kèm
             |
             v
OAuth2AuthenticationToken
  - Authentication cuối dùng cho ứng dụng web
  - chứa OAuth2User/OidcUser, authorities, authorizedClientRegistrationId
             |
             v
SecurityContext
  - Authentication được gắn vào request và lưu theo chính sách session
```

`OAuth2LoginAuthenticationToken` là kiểu dùng trong **quá trình xác thực OAuth2 login**. Sau thành công, `OAuth2LoginAuthenticationFilter` chuyển kết quả sang `OAuth2AuthenticationToken` phục vụ ứng dụng. Không nên giả định controller sẽ thấy `OAuth2LoginAuthenticationToken` trong `SecurityContextHolder`.

## 3. Filter nằm ở đâu và lắng nghe URL nào?

Trong mô hình Servlet, Spring Security có `FilterChainProxy` và một hoặc nhiều `SecurityFilterChain`. Khi đăng ký:

```java
http.oauth2Login(Customizer.withDefaults());
```

Spring Security thêm các filter và thành phần phục vụ OAuth2 Login, trong đó có `OAuth2LoginAuthenticationFilter`.

### 3.1. Hai URL dễ nhầm

| URL mặc định | Thành phần chủ yếu | Ý nghĩa |
| --- | --- | --- |
| `/oauth2/authorization/{registrationId}` | `OAuth2AuthorizationRequestRedirectFilter` | Bắt đầu login bằng cách tạo authorization request và redirect sang OP. |
| `/login/oauth2/code/{registrationId}` | `OAuth2LoginAuthenticationFilter` | Tiếp nhận callback từ OP và thực hiện xác thực bằng authorization code. |

Ví dụ khi registration ID là `academy`:

```text
GET /oauth2/authorization/academy

GET /login/oauth2/code/academy?code=CODE&state=STATE
```

`OAuth2LoginAuthenticationFilter` có pattern xử lý callback mặc định gắn với `/login/oauth2/code/*`. Dấu `*` ở đây được dùng để khớp đường dẫn callback tương ứng với registration, **không có nghĩa filter sẽ xác thực mọi request trên website**.

Nếu request không khớp URL do filter xử lý, filter không bắt đầu xác thực OAuth2 login từ request đó. Trong ứng dụng có nhiều `SecurityFilterChain`, callback phải rơi vào chain có cấu hình `oauth2Login()`; một chain ưu tiên cao bắt hết callback nhưng không chứa filter có thể làm luồng đăng nhập thất bại.

### 3.2. Filter kế thừa `AbstractAuthenticationProcessingFilter`

`OAuth2LoginAuthenticationFilter` kế thừa **`AbstractAuthenticationProcessingFilter`**. Mẫu xử lý chung là:

1. Kiểm tra request có phải request xác thực dành cho filter hay không.
2. Gọi `attemptAuthentication(...)` để xây dựng yêu cầu và nhờ `AuthenticationManager` xác thực.
3. Nếu thành công, áp dụng chiến lược session, hoàn tất `SecurityContext` và gọi success handler theo cấu hình.
4. Nếu thất bại, xóa bối cảnh xác thực không hợp lệ và gọi failure handler.

Thành công hay thất bại đều có ý nghĩa ở **bước đăng nhập ứng dụng**, không chỉ ở thông điệp HTTP của OP.

## 4. Bước 1: Tạo và lưu authorization request trước callback

Dù trọng tâm bài học là callback filter, không thể hiểu nó nếu bỏ qua những dữ liệu được lưu **trước khi browser sang OP**.

Khi browser truy cập:

```http
GET /oauth2/authorization/academy HTTP/1.1
Host: app.example.com
```

`OAuth2AuthorizationRequestRedirectFilter` cùng authorization request resolver thường:

1. Tìm `ClientRegistration` theo registration ID `academy`.
2. Tạo authorization request chứa `client_id`, `response_type=code`, `redirect_uri` và `scope`.
3. Sinh/đưa vào `state`, cùng các dữ liệu OIDC/PKCE cần thiết như `nonce` và `code_challenge` tùy cấu hình.
4. Lưu `OAuth2AuthorizationRequest` vào một `AuthorizationRequestRepository`.
5. Trả `302 Location` để browser chuyển tới Authorization Endpoint của OP.

Một cơ chế lưu thường dùng là **`HttpSessionOAuth2AuthorizationRequestRepository`**, tức lưu request đang chờ callback trong HTTP session phía server. Browser mang session cookie trở về sau redirect để server tìm lại request ban đầu.

Ví dụ response minh họa:

```http
HTTP/1.1 302 Found
Location: https://idp.example.com/authorize?response_type=code&client_id=academy-web&state=RANDOM_STATE&scope=openid%20profile&redirect_uri=https%3A%2F%2Fapp.example.com%2Flogin%2Foauth2%2Fcode%2Facademy
Set-Cookie: JSESSIONID=SESSION_REFERENCE; Path=/; Secure; HttpOnly
```

**`state` là dữ liệu đối chiếu yêu cầu–phản hồi**, không phải access token. Authorization request lưu phía client giúp filter callback biết yêu cầu nào đã được khởi tạo và provider/client registration nào phải được sử dụng.

Nếu ứng dụng không tìm lại được bản ghi này, việc OP đã đăng nhập người dùng thành công **không đủ** để ứng dụng hoàn tất login một cách an toàn.

## 5. Bước 2: Browser trở về `OAuth2LoginAuthenticationFilter`

Sau khi người dùng xác thực và đồng ý (nếu OP yêu cầu), OP redirect browser về callback đã đăng ký:

```http
GET /login/oauth2/code/academy?code=ONE_TIME_CODE&state=RANDOM_STATE HTTP/1.1
Host: app.example.com
Cookie: JSESSIONID=SESSION_REFERENCE
```

Đây là một request HTTP mới, do browser gửi về **ứng dụng Spring**. Filter nhận callback, đọc tham số và liên kết với authorization request đã lưu.

Ở mức khái niệm, `attemptAuthentication` xử lý các bước:

1. Xác định đây là một **OAuth2 authorization response**, có `code` và `state` khi thành công, hoặc `error` khi OP từ chối.
2. Gọi `AuthorizationRequestRepository` lấy và loại bỏ authorization request đang chờ tương ứng theo cơ chế repository.
3. Lấy **registration ID** thuộc yêu cầu đã lưu và tìm đúng `ClientRegistration`.
4. Xây dựng đối tượng `OAuth2AuthorizationResponse`.
5. Ghép request và response thành **`OAuth2AuthorizationExchange`**.
6. Tạo **`OAuth2LoginAuthenticationToken`** làm đối tượng xác thực đầu vào và chuyển nó tới `AuthenticationManager.authenticate(...)`.

Các bước này chịu trách nhiệm **bảo toàn ngữ cảnh giao thức**. Client không được tùy ý tin vào một `registrationId`, `redirect_uri` hay endpoint do bên ngoài cung cấp mà không ràng buộc với yêu cầu đã khởi tạo.

### 5.1. Vì sao phải khôi phục authorization request?

Một callback đơn lẻ như:

```text
/login/oauth2/code/academy?code=abc&state=xyz
```

chưa đủ để chứng minh:

- Browser trước đó có chủ động đăng nhập không;
- `state` có thuộc yêu cầu mà ứng dụng đang chờ không;
- Client registration và OP nào đã tham gia;
- Redirect URI, scope và PKCE verifier của yêu cầu ban đầu là gì.

Thông tin này phải được lấy từ **ngữ cảnh được tin cậy phía client**. Nếu authorization request không tồn tại hoặc callback không hợp lệ, Spring Security phải kết thúc flow bằng lỗi thay vì tạo một `Authentication` từ code bất kỳ.

### 5.2. Lỗi `authorization_request_not_found`

Một lỗi điển hình khi nhận callback là không thể tìm được authorization request đã lưu. Những nguyên nhân thường gặp gồm:

- Browser không gửi lại session cookie vì `Secure`, `SameSite`, `Domain`, `Path` hoặc khác hostname;
- HTTP session hết hạn trong thời gian người dùng đăng nhập ở OP;
- Request khởi đầu và callback đi vào hai instance không chia sẻ session;
- Người dùng mở nhiều luồng login cạnh tranh với cách lưu request không hỗ trợ yêu cầu đồng thời;
- Callback được gọi trực tiếp mà không qua bước khởi tạo;
- Cấu hình callback URI hoặc security chain không nhất quán.

Không sửa bằng cách bỏ lưu request hoặc bỏ kiểm tra `state`. Cần xác định nơi session và authorization request bị mất.

## 6. Bước 3: Tạo `OAuth2LoginAuthenticationToken`

Dữ liệu đầu vào từ callback và request đã lưu được đóng gói trong một Authentication chuyên biệt cho quá trình login.

Sơ đồ quan hệ:

```text
ClientRegistration
  - registrationId = academy
  - clientId, client authentication method, scopes
  - authorizationUri, tokenUri, jwkSetUri, issuer metadata
            |
            v
OAuth2AuthorizationRequest  +  OAuth2AuthorizationResponse
            |                            |
            +---- OAuth2AuthorizationExchange ----+
                                                  |
                                                  v
                              OAuth2LoginAuthenticationToken
                                                  |
                                                  v
                              AuthenticationManager.authenticate(...)
```

Đây là lúc Spring chuyển **thông tin giao thức HTTP** thành **authentication request** mà hệ thống authentication của Spring Security hiểu được.

Điểm cần ghi nhớ:

- `OAuth2LoginAuthenticationToken` ở đầu flow **chưa chứng minh người dùng đã đăng nhập**.
- Authorization code **chưa phải danh tính người dùng**.
- `AuthenticationManager` được gọi để đưa request này qua provider hỗ trợ.
- `OAuth2AuthenticationToken` dùng trong `SecurityContext` sẽ được tạo **sau khi provider xác thực thành công**.

Trong code ứng dụng thông thường, bạn không cần tự `new OAuth2LoginAuthenticationToken(...)`. Spring Security đã thực hiện bước đó khi callback đến đúng filter.

## 7. Bước 4: `AuthenticationManager` chọn provider và xác thực

`AuthenticationManager` là giao diện có phương thức chính:

```java
Authentication authenticate(Authentication authentication)
        throws AuthenticationException;
```

Trong cấu hình phổ biến, triển khai `ProviderManager` chuyển việc xác thực đến một `AuthenticationProvider` phù hợp với loại Authentication được nhận. Đối với OAuth2 Login, các provider quan trọng gồm:

| Provider | Ngữ cảnh chủ yếu | Kết quả |
| --- | --- | --- |
| `OAuth2LoginAuthenticationProvider` | OAuth2 Login không có lớp OIDC, ví dụ provider trả thông tin người dùng qua UserInfo API riêng | Trao đổi code lấy token, dùng `OAuth2UserService` để lấy principal OAuth2 và ánh xạ authorities. |
| `OidcAuthorizationCodeAuthenticationProvider` | **OIDC Authorization Code Flow**, khi đăng nhập có `openid` | Trao đổi code lấy token, xác minh ID Token và tạo `OidcUser` theo cấu hình OIDC. |

Provider có thể sử dụng các thành phần thấp hơn như **`OAuth2AccessTokenResponseClient`** để gọi Token Endpoint và **`OAuth2UserService` / `OidcUserService`** để tạo principal từ dữ liệu người dùng. Những class cụ thể cho HTTP client, token decoder và repository có thể thay đổi theo phiên bản hoặc tùy biến.

### 7.1. Trao đổi authorization code lấy token

Từ authorization exchange đã tạo, provider thực hiện yêu cầu HTTP server-to-server tới Token Endpoint của OP:

```http
POST /oauth2/token HTTP/1.1
Host: idp.example.com
Content-Type: application/x-www-form-urlencoded
Authorization: Basic <client-credentials-when-applicable>

grant_type=authorization_code&code=ONE_TIME_CODE&redirect_uri=https%3A%2F%2Fapp.example.com%2Flogin%2Foauth2%2Fcode%2Facademy
```

Request được minh họa rút gọn. Với client dùng PKCE, request còn mang **`code_verifier`**. Với confidential client, phương thức xác thực client có thể là `client_secret_basic`, `client_secret_post` hoặc cơ chế khác do OP hỗ trợ.

Điểm quan trọng: **backend của Spring thực hiện token request**; browser không cần biết client secret hoặc PKCE verifier. OP kiểm tra code hợp lệ, đúng client/redirect URI, chưa dùng và các điều kiện PKCE trước khi cấp token.

Response OIDC có thể có dạng:

```json
{
  "access_token": "<access-token>",
  "token_type": "Bearer",
  "expires_in": 3600,
  "scope": "openid profile email",
  "id_token": "<signed-oidc-id-token>"
}
```

Một số OP cấp thêm `refresh_token` nếu client, grant, scopes và chính sách OP cho phép; không mặc định token refresh luôn tồn tại.

### 7.2. Kiểm tra `state`, PKCE và ranh giới của filter

Ba kiểm tra xảy ra ở những vị trí khác nhau trong toàn flow:

| Cơ chế | Được xử lý ở đâu về mặt trách nhiệm? | Mục tiêu |
| --- | --- | --- |
| `state` | Client đối chiếu authorization response với authorization request đã lưu trong quá trình xử lý callback/authorization code | Liên kết response với request; chống login CSRF và callback giả mạo. |
| PKCE | OP kiểm tra `code_verifier` ở Token Endpoint với challenge đã nhận trước đó | Gắn code với bên đã bắt đầu authorization request. |
| OIDC `nonce` | OIDC Client kiểm tra nonce trong ID Token sau khi xác minh token | Gắn ID Token với lần xác thực đã khởi tạo. |

Không nên hiểu rằng `OAuth2LoginAuthenticationFilter` tự mình thực hiện toàn bộ phép kiểm tra mật mã. Filter điều phối callback và chuyển authentication request tới các provider; provider, token response client và OIDC decoder/validator xử lý phần giao thức tương ứng.

Khi tự thay các thành phần mặc định, cần bảo toàn tất cả ràng buộc này. Việc “đăng nhập được” sau tùy biến không chứng minh luồng còn đủ bảo vệ.

## 8. Bước 5: Từ token của OP đến `OAuth2User` hoặc `OidcUser`

Một access token và ID Token là dữ liệu do OP phát, nhưng Spring cần **principal** và **authorities** để ứng dụng hiểu người dùng là ai và có thể làm gì.

### 8.1. OAuth2 Login thông thường

Với provider OAuth2 không dùng OIDC, Spring thường dùng `OAuth2UserService` (ví dụ `DefaultOAuth2UserService`) để nhận dữ liệu từ UserInfo endpoint hoặc API người dùng đã cấu hình, rồi tạo `OAuth2User`.

Principal có thể có:

- `getName()`: định danh được ánh xạ theo `user-name-attribute`;
- `getAttributes()`: các thuộc tính provider trả về;
- `getAuthorities()`: tập quyền mà Spring Security dùng khi authorization.

Nếu provider trả JSON như:

```json
{
  "id": "u-928",
  "display_name": "Learner A",
  "email": "learner@example.com"
}
```

thì `user-name-attribute: id` có thể được dùng theo cấu hình OAuth2 user mapping. Không nên mặc định email là định danh bất biến hoặc được xác minh.

### 8.2. OIDC Login

Khi request có scope `openid` và OP trả ID Token hợp lệ, Spring xử lý luồng **OIDC**. `OidcAuthorizationCodeAuthenticationProvider` xác minh ID Token theo OIDC, bao gồm những điều kiện phù hợp như:

- Chữ ký và thuật toán được cho phép, khóa ký từ provider tin cậy;
- `iss` đúng issuer được cấu hình;
- `aud` chứa client ID tương ứng;
- `exp`/các điều kiện thời gian;
- `nonce` khớp authorization request nếu nonce đã được gửi;
- các ràng buộc OIDC khác như `azp` khi áp dụng.

Sau đó `OidcUserService` có thể kết hợp ID Token và dữ liệu UserInfo theo điều kiện triển khai để tạo **`OidcUser`**. `OidcUser` là một dạng `OAuth2User` với khả năng truy cập ID Token và OIDC claims.

Ví dụ principal OIDC có thể cung cấp:

```java
OidcUser principal = ...;

String subject = principal.getSubject();
String issuer = principal.getIssuer().toString();
String displayName = principal.getFullName();
String email = principal.getEmail();
```

Đoạn này minh họa API đọc claims, không phải đoạn code tạo principal. `getFullName()` hoặc `getEmail()` có thể trả `null` vì provider không nhất thiết cung cấp toàn bộ claims.

**ID Token dành để xác thực người dùng cho OIDC Client**, không thay thế access token khi ứng dụng gọi API. Dữ liệu UserInfo cũng phải được liên kết với subject của ID Token theo quy tắc OIDC.

### 8.3. Authorities được tạo và ánh xạ như thế nào?

`Authentication` chứa **`GrantedAuthority`**, ví dụ các authority mặc định đại diện người dùng OAuth2/OIDC và các authority được ánh xạ từ claims/scope theo cơ chế framework. Nhưng OP gửi claim `groups` hay `roles` **không đồng nghĩa** Spring tự cấp `ROLE_ADMIN`.

Ví dụ với quy tắc:

```java
.requestMatchers("/admin/**").hasRole("ADMIN")
```

Spring Security tìm authority phù hợp, thông thường `ROLE_ADMIN`. Nếu principal chỉ có authority OIDC mặc định, user không có quyền admin. Ứng dụng phải định nghĩa rõ cách tin cậy và ánh xạ claim của OP sang authority nội bộ, hoặc đọc quyền từ cơ sở dữ liệu riêng.

Các điểm mở rộng thường là:

- `GrantedAuthoritiesMapper` để chuyển authorities từ provider sang authority dùng trong ứng dụng;
- `OidcUserService` tùy biến để đọc và chuyển claims bổ sung;
- một `OAuth2UserService` riêng cho provider OAuth2 không theo OIDC.

Khi thêm authority, cần kiểm tra nguồn claims, issuer, audience, hợp đồng phân quyền và khả năng thay đổi của từng provider. Không xây dựng phân quyền chỉ bằng cách tin tất cả claims được gửi từ browser.

## 9. Bước 6: Chuyển thành `OAuth2AuthenticationToken`

Sau khi provider xác thực thành công và trả kết quả chứa principal, authorities và token liên quan, `OAuth2LoginAuthenticationFilter` chuyển nó thành một **`OAuth2AuthenticationToken`** thông qua cơ chế converter tương ứng.

Có thể hình dung:

```text
OAuth2LoginAuthenticationToken (kết quả từ provider)
  - ClientRegistration = academy
  - OAuth2User hoặc OidcUser
  - GrantedAuthority collection
  - AccessToken (và RefreshToken nếu có)
           |
           | chuyển authentication result
           v
OAuth2AuthenticationToken
  - principal = OAuth2User / OidcUser
  - authorities = quyền ứng dụng đọc từ principal
  - authorizedClientRegistrationId = academy
  - authenticated = true
```

`OAuth2AuthenticationToken` là đối tượng mà các thành phần như **`SecurityContextHolder`**, authorization rules, controller và method security thường thấy sau login thành công.

Ở mức API, bạn có thể đọc:

```java
Authentication authentication =
        SecurityContextHolder.getContext().getAuthentication();

String name = authentication.getName();
boolean authenticated = authentication.isAuthenticated();
Collection<? extends GrantedAuthority> authorities =
        authentication.getAuthorities();
```

**Đừng kết luận người dùng hợp lệ chỉ vì `isAuthenticated()` trả `true` trong một đối tượng bất kỳ do code của bạn tự tạo.** Trong flow chuẩn, Spring Security chỉ lưu kết quả sau khi AuthenticationManager/provider xác thực thành công. Tránh tự chèn Authentication chưa được tin cậy vào context để “bỏ qua login”.

### 9.1. Access token nằm ở đâu?

`OAuth2AuthenticationToken` chủ yếu đại diện cho **người dùng đã đăng nhập**. Token để gọi API được quản lý qua **`OAuth2AuthorizedClient`**, vốn gắn:

- `ClientRegistration`;
- tên/định danh principal được ủy quyền;
- access token và thông tin thời hạn;
- refresh token nếu có.

Vì vậy đọc `Authentication.getCredentials()` hoặc ép `OAuth2AuthenticationToken` sang một kiểu Bearer token để lấy access token là sai mô hình. Có thể dùng `OAuth2AuthorizedClientRepository`, `OAuth2AuthorizedClientService` hoặc tích hợp OAuth2 Client phù hợp để lấy token khi gọi downstream API.

## 10. Bước 7: Lưu `OAuth2AuthorizedClient`

Trong flow login Servlet thông dụng, sau khi nhận kết quả xác thực, `OAuth2LoginAuthenticationFilter` tạo/đăng ký một `OAuth2AuthorizedClient` tương ứng với registration và principal. Dữ liệu được lưu qua **`OAuth2AuthorizedClientRepository`** được cấu hình.

```text
Đăng nhập từ OP
   |
   +--> OAuth2AuthenticationToken
   |      Đưa vào SecurityContext
   |      => ứng dụng biết người dùng đã đăng nhập
   |
   +--> OAuth2AuthorizedClient
          Lưu access token / refresh token khi có
          => ứng dụng có thể gọi API thay mặt người dùng
```

Hai nhánh này phục vụ nhu cầu khác nhau. HTTP session có thể được dùng để giữ cả SecurityContext và authorized client ở ứng dụng đơn giản, nhưng repository/service hoàn toàn có thể được thay bằng cơ chế lưu bền vững hoặc phân tán.

Ví dụ Spring MVC nhận authorized client khi đã bật tích hợp tương ứng:

```java
import java.util.Map;

import org.springframework.security.oauth2.client.OAuth2AuthorizedClient;
import org.springframework.security.oauth2.client.annotation.RegisteredOAuth2AuthorizedClient;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
class TokenStateController {

    @GetMapping("/token-state")
    Map<String, Object> tokenState(
            @RegisteredOAuth2AuthorizedClient("academy")
            OAuth2AuthorizedClient client) {

        return Map.of(
                "registrationId", client.getClientRegistration().getRegistrationId(),
                "expiresAt", client.getAccessToken().getExpiresAt().toString());
    }
}
```

Ví dụ chỉ trả trạng thái kỹ thuật, **không trả giá trị access token**. Nó giả định authorized client đã tồn tại và resolver được tích hợp trong Spring MVC/Security; ở tình huống khác cần xử lý trường hợp authorized client chưa có. Đối với ứng dụng sản xuất, tránh expose endpoint nội bộ mô tả token nếu không có lý do và kiểm soát truy cập.

Nếu ứng dụng chỉ cần đăng nhập web, bạn vẫn có thể dùng `oauth2Login()` mà không tự viết bất kỳ code nào đọc access token. Khi cần gọi API, có thể tích hợp `OAuth2AuthorizedClientManager` hoặc HTTP client hỗ trợ OAuth2.

## 11. Bước 8: `SecurityContext`, session và success handler

Sau khi `attemptAuthentication` trả về kết quả thành công, luồng của `AbstractAuthenticationProcessingFilter` tiếp tục hoàn tất đăng nhập. Trong ứng dụng Servlet dùng session, các việc quan trọng gồm:

1. Áp dụng **`SessionAuthenticationStrategy`** phù hợp, ví dụ bảo vệ session fixation bằng cách thay đổi session ID khi đăng nhập.
2. Tạo hoặc cập nhật **`SecurityContext`** với `OAuth2AuthenticationToken` đã xác thực.
3. Dùng **`SecurityContextRepository`** để lưu SecurityContext theo chính sách cấu hình; trong Spring Security 6 cần lưu theo cơ chế phù hợp thay vì tùy ý giả định mọi thiết lập đều tự động lưu.
4. Phát sự kiện/thực hiện remember-me callback theo cấu hình của filter/framework khi áp dụng.
5. Gọi **`AuthenticationSuccessHandler`**, thường chuyển browser về request đã được lưu hoặc trang đích.

Từ đây, request sau có thể gửi session cookie, Spring Security khôi phục `SecurityContext` và ứng dụng biết người dùng đã đăng nhập mà không cần gọi OP cho mỗi request.

```http
HTTP/1.1 302 Found
Location: /account
Set-Cookie: JSESSIONID=UPDATED_SESSION_REFERENCE; Path=/; Secure; HttpOnly
```

Browser tiếp tục:

```http
GET /account HTTP/1.1
Host: app.example.com
Cookie: JSESSIONID=UPDATED_SESSION_REFERENCE
```

Đây là ví dụ minh họa header: không phải mọi login đều tạo cookie mới với cùng tên/thuộc tính. Hành vi session phụ thuộc session strategy, container, proxy và cấu hình ứng dụng.

### 11.1. Ba nơi lưu trạng thái không được đánh đồng

| Dữ liệu | Mục đích | Vòng đời |
| --- | --- | --- |
| Authorization request tạm | Lưu `state` và dữ liệu để kiểm tra callback/đổi code | Từ lúc bắt đầu flow đến khi hoàn thành/hủy/hết hạn |
| `SecurityContext` chứa Authentication | Cho biết request đã đăng nhập bằng principal nào và có authority gì | Theo policy của request/session và logout |
| `OAuth2AuthorizedClient` | Lưu token của client để dùng tiếp khi gọi tài nguyên | Theo storage, vòng đời token và chính sách refresh/revoke |

Session của OP (SSO login) lại là một phiên độc lập khác. Hết session của Spring app chưa nhất thiết là đã logout khỏi OP; hết hạn access token chưa nhất thiết làm session đăng nhập Spring app hết hạn.

### 11.2. Vì sao không tự redirect trước khi success handling hoàn tất?

Nếu tự viết filter/controller nhận callback rồi gọi `response.sendRedirect(...)` mà bỏ qua cơ chế xác thực và lưu context, browser có thể nhìn thấy một trang đích nhưng request tiếp theo vẫn bị xem là anonymous.

Để tùy biến hành vi sau login, hãy dùng **`AuthenticationSuccessHandler`** hoặc các extension point được Spring Security hỗ trợ, giữ nguyên đường đi xác thực và lưu bối cảnh. Nếu thay success handler mặc định, cần tự quyết định có giữ tính năng trở về **saved request** hay không.

## 12. Cấu hình tối thiểu để filter hoạt động

Giả sử OP có issuer discovery và client `academy` đã đăng ký callback phù hợp.

### 12.1. Dependency

Với ứng dụng Spring Boot MVC dùng Maven:

```xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-web</artifactId>
</dependency>
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-oauth2-client</artifactId>
</dependency>
```

### 12.2. `application.yml`

```yaml
spring:
  security:
    oauth2:
      client:
        registration:
          academy:
            provider: academy-oidc
            client-id: ${OIDC_CLIENT_ID}
            client-secret: ${OIDC_CLIENT_SECRET}
            authorization-grant-type: authorization_code
            scope:
              - openid
              - profile
              - email
            redirect-uri: "{baseUrl}/login/oauth2/code/{registrationId}"
        provider:
          academy-oidc:
            issuer-uri: ${OIDC_ISSUER_URI}
```

Trong đó:

- `academy` là **registration ID**: cũng là phần cuối URL `/oauth2/authorization/academy` và callback.
- `academy-oidc` là alias cho OP có issuer cụ thể.
- `openid` cho biết đây là OIDC login, giúp framework xử lý ID Token và `OidcUser`.
- `{baseUrl}` được Spring Security suy ra từ request/môi trường triển khai; sau reverse proxy phải thiết lập forwarded headers một cách tin cậy.
- `${OIDC_CLIENT_SECRET}` được cung cấp từ môi trường/secret store, không ghi secret vào Git.

### 12.3. `SecurityFilterChain`

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
class SecurityConfig {

    @Bean
    SecurityFilterChain webSecurityFilterChain(HttpSecurity http) throws Exception {
        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/", "/assets/**", "/error").permitAll()
                .anyRequest().authenticated()
            )
            .oauth2Login(Customizer.withDefaults());

        return http.build();
    }
}
```

Nếu chưa tự tạo `SecurityFilterChain`, Spring Boot với starter phù hợp có thể cung cấp auto-configuration mặc định. Khi **đã tự khai báo chain**, cần chắc chắn chain đó thực sự bật `oauth2Login()` và matcher không bỏ sót callback. Không cần khai báo bean trực tiếp cho `OAuth2LoginAuthenticationFilter` trong cấu hình cơ bản.

Ứng dụng có thể bắt đầu flow trực tiếp bằng:

```text
GET http://localhost:8080/oauth2/authorization/academy
```

Đường dẫn OP redirect về thường là:

```text
http://localhost:8080/login/oauth2/code/academy
```

Callback URI này phải được đăng ký trong OP. Ở production, HTTPS là yêu cầu thông thường.

## 13. Quan sát Authentication từ controller

Sau khi login thành công, một controller có thể dùng `Authentication` hoặc `@AuthenticationPrincipal`.

### 13.1. Đọc Authentication chung

```java
import java.util.List;
import java.util.Map;

import org.springframework.security.core.Authentication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
class SessionUserController {

    @GetMapping("/whoami")
    Map<String, Object> whoami(Authentication authentication) {
        List<String> authorities = authentication.getAuthorities()
                .stream()
                .map(a -> a.getAuthority())
                .toList();

        return Map.of(
                "name", authentication.getName(),
                "type", authentication.getClass().getSimpleName(),
                "authenticated", authentication.isAuthenticated(),
                "authorities", authorities);
    }
}
```

Nếu endpoint được bảo vệ và login bằng OAuth2/OIDC, kiểu Authentication thường là `OAuth2AuthenticationToken`. Trong code thực tế, không nên dùng tên lớp hiển thị hoặc danh sách authority làm đầu vào tin cậy từ client; server tự lấy chúng từ SecurityContext.

### 13.2. Đọc OIDC principal

```java
import java.util.Map;

import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.oauth2.core.oidc.user.OidcUser;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
class OidcProfileController {

    @GetMapping("/profile")
    Map<String, String> profile(@AuthenticationPrincipal OidcUser user) {
        return Map.of(
                "subject", user.getSubject(),
                "name", user.getFullName() != null
                        ? user.getFullName() : "(không cung cấp)");
    }
}
```

Ví dụ áp dụng cho endpoint chỉ nhận người dùng **OIDC**. Nếu ứng dụng hỗ trợ nhiều loại authentication, controller phải xử lý phù hợp khi principal không phải `OidcUser`.

Các getter cho OIDC claims không thay thế bước xác minh ID Token: Spring Security đã thực hiện xác thực trước khi principal trở thành kết quả login. Để định danh người dùng xuyên suốt, nên cân nhắc cặp **(issuer, subject)**; không tự động ghép tài khoản chỉ dựa trên email.

### 13.3. Vì sao principal có thể khác tên/claim mong muốn?

Trong OIDC, tên hiển thị, email và username có thể không có trong ID Token hoặc UserInfo. Việc ánh xạ `OidcUser` phụ thuộc scope, provider và `OidcUserService`. Không coi thiếu `email` là bằng chứng filter không chạy, và không buộc mọi provider trả cùng bộ claims.

## 14. Tùy biến login nhưng vẫn giữ cơ chế xác thực

### 14.1. Tùy biến callback path

Nếu OP yêu cầu callback theo quy ước riêng, có thể đổi **redirection endpoint** của Spring Security đồng thời đổi redirect URI template của client registration.

Ví dụ dùng callback `/auth/callback/{registrationId}`:

```yaml
spring:
  security:
    oauth2:
      client:
        registration:
          academy:
            redirect-uri: "{baseUrl}/auth/callback/{registrationId}"
```

```java
@Bean
SecurityFilterChain webSecurityFilterChain(HttpSecurity http) throws Exception {
    http
        .authorizeHttpRequests(auth -> auth
            .requestMatchers("/", "/assets/**", "/error").permitAll()
            .anyRequest().authenticated()
        )
        .oauth2Login(oauth2 -> oauth2
            .redirectionEndpoint(redirection -> redirection
                .baseUri("/auth/callback/*")));

    return http.build();
}
```

**Hai đường dẫn phải cùng khớp**: URI gửi cho OP và callback matcher của filter. Ngoài ra, phải cập nhật allowlist ở OP. Nếu chỉ đổi một trong hai, browser có thể quay về URL mà filter không xử lý.

Đoạn bean là **phương án thay thế** cho security chain ở mục 12.3, không phải một chain thứ hai cần copy thêm.

### 14.2. Tùy biến thành công/thất bại

Có thể cấu hình:

```java
.oauth2Login(oauth2 -> oauth2
    .defaultSuccessUrl("/dashboard", false)
    .failureUrl("/login?error"))
```

Đây là đoạn DSL gắn bên trong một `HttpSecurity` đang cấu hình. Tham số `false` cho phép cơ chế điều hướng xét request đã được lưu theo hành vi của success handler mặc định. Nếu đặt `true`, login sẽ luôn về `/dashboard` trong cấu hình tương ứng, thay vì ưu tiên saved request.

Một số hệ thống cần tự audit login hoặc ánh xạ người dùng vào database. Có thể dùng success handler hoặc sự kiện xác thực phù hợp, nhưng tránh:

- In access token, refresh token, authorization code, session ID hoặc client secret ra log;
- Tự chèn `Authentication` chưa được provider xác thực;
- Redirect đến URL do client cung cấp mà chưa kiểm tra để tránh open redirect;
- Thực hiện nghiệp vụ không thể lặp lại trong success handler khi chưa xử lý lỗi và tính idempotent.

### 14.3. Tùy biến thông tin người dùng

OIDC custom user service có thể được gắn qua:

```java
.oauth2Login(oauth2 -> oauth2
    .userInfoEndpoint(userInfo -> userInfo
        .oidcUserService(customOidcUserService)))
```

`customOidcUserService` là bean/đối tượng `OAuth2UserService<OidcUserRequest, OidcUser>` đã được ứng dụng định nghĩa. Tùy biến nên **ủy quyền cho `OidcUserService` chuẩn** để tải user đúng cách, rồi chỉ ánh xạ thêm dữ liệu cần thiết. Nếu tự thay toàn bộ cơ chế tải user, phải bảo vệ ràng buộc issuer, token validation và subject matching.

Thay đổi principal không làm token endpoint hoặc browser callback khác đi; đó là phần sau khi provider đã có token hợp lệ.

## 15. Khi xác thực thất bại, chuyện gì xảy ra?

`OAuth2LoginAuthenticationFilter` dựa trên mẫu `AbstractAuthenticationProcessingFilter`: khi quá trình authentication ném `AuthenticationException`, Spring Security đi qua nhánh thất bại, xóa context không hợp lệ theo cơ chế filter và chuyển cho failure handler.

Các nguồn lỗi có thể xuất hiện ở nhiều thời điểm:

```text
Callback nhận được
    |
    +-- Authorization response thiếu/sai?
    |
    +-- Authorization request không tồn tại trong repository?
    |
    +-- ClientRegistration không tìm được?
    |
    +-- state, code, PKCE, redirect_uri không hợp lệ?
    |
    +-- Token endpoint trả invalid_client / invalid_grant?
    |
    +-- ID Token sai chữ ký, issuer, audience, hạn dùng hoặc nonce?
    |
    +-- UserInfo request / mapping principal thất bại?
    |
    v
AuthenticationException -> failure handler
    |
    v
Không lập phiên đăng nhập thành công
```

Trong nhiều cấu hình web mặc định, người dùng được đưa về trang login có tham số lỗi, ví dụ `/login?error`. Với custom failure handler, ứng dụng có thể chọn cách hiển thị khác. Không nên đưa raw error description từ OP hoặc stack trace có token ra trang public.

### 15.1. Bảng chẩn đoán theo điểm xử lý

| Hiện tượng | Nơi nên điều tra | Gợi ý |
| --- | --- | --- |
| Callback `404`, không vào login flow | Security chain/callback matcher | So `redirect-uri` với `redirectionEndpoint().baseUri(...)`; chain có `oauth2Login()` không? |
| `authorization_request_not_found` | `AuthorizationRequestRepository`, session | Browser có gửi đúng session cookie? Request trước callback có bị mất/hết hạn? |
| State không khớp | Correlation giữa request và response | Callback khác phiên, request đã bị tiêu thụ, URL/cookie/flow song song bị nhầm. |
| Token endpoint trả `invalid_client` | Client registration và cách xác thực tại OP | Client ID/secret, client-authentication-method, tenant hoặc endpoint sai. |
| Token endpoint trả `invalid_grant` | Authorization code exchange | Code hết hạn/đã dùng, redirect URI khác, PKCE verifier sai/thiếu. |
| ID Token bị từ chối | OIDC provider/decoder/validator | Chữ ký, JWKS, `iss`, `aud`, `exp`, `nonce`, đồng hồ. |
| UserInfo trả `401` | `OAuth2UserService`/`OidcUserService` | Access token, scope, UserInfo URI và cách gửi credential. |
| Callback thành công nhưng lại bị đưa về login | `SecurityContextRepository`, cookie, session | Context không lưu/không được khôi phục; cookie domain/path/SameSite/Secure sai; session đa instance. |
| Login xong `403` ở `/admin` | Authorization/authorities | Principal chưa có authority ứng dụng yêu cầu; không đồng nghĩa login thất bại. |
| Browser login được nhưng API Bearer trả `401` | OAuth2 Resource Server | Access token audience/issuer/scope hoặc API configuration; web session không tự bảo vệ API. |

**`invalid_grant` không chỉ là lỗi PKCE**; mã lỗi này có thể phản ánh nhiều nguyên nhân ở token endpoint. Cần đối chiếu thông số và log đã được loại bỏ dữ liệu nhạy cảm.

### 15.2. Logging an toàn

Trong môi trường học tập, có thể bật log của Spring Security ở mức phù hợp:

```yaml
logging:
  level:
    org.springframework.security: DEBUG
```

Log cho biết filter chain, xác thực và các lỗi; nhưng **tránh bật log nhạy cảm trên production**. Đặc biệt không thu thập nguyên văn callback URL chứa code, header `Authorization`, token, session cookie, PKCE verifier, client secret hoặc ID Token trong hệ thống log được chia sẻ rộng.

Khi cần phân tích, log những giá trị phi nhạy cảm như request ID, registration ID, loại exception đã chuẩn hóa, endpoint (không kèm query), thời điểm và kết quả.

## 16. Những điểm thường gây nhầm lẫn

### 16.1. “Callback có code là đã đăng nhập”

Sai. Code chỉ là credential tạm để **đổi token**, có thời hạn, được gắn với client/redirect URI và chỉ dùng một lần. Spring còn phải tìm authorization request, xác thực trao đổi và xây dựng principal.

### 16.2. “OAuth2LoginAuthenticationFilter tự kiểm tra tất cả token”

Sai về cách phân chia trách nhiệm. Filter nhận callback và phối hợp xử lý; `AuthenticationManager` và các provider, OAuth2 token client, OIDC decoder/user service xử lý các bước protocol và xác minh nội dung cần thiết.

### 16.3. “ID Token chính là Authentication”

ID Token là một token do OP phát nhằm chứng minh sự kiện xác thực cho OIDC Client. `Authentication` là đối tượng Spring Security dùng cho principal và authorities của ứng dụng. Chúng liên quan nhưng **không cùng kiểu hoặc mục đích**.

### 16.4. “Có Authentication là tự động có access token gọi API”

`OAuth2AuthenticationToken` đại diện người dùng đã đăng nhập; token để gọi API nằm trong authorized client và cần được dùng đúng client registration/scopes/audience. Có thể ứng dụng có session hợp lệ nhưng access token đã hết hạn hoặc không có scope cần thiết.

### 16.5. “Login ở OP thành công thì ứng dụng bắt buộc có session”

Login ở OP và login ở Spring app là **hai phiên khác nhau**. Nếu callback lỗi, state không hợp lệ hoặc context không được lưu, ứng dụng vẫn chưa đăng nhập. Session timeout ở Spring cũng độc lập với thời hạn SSO tại OP.

### 16.6. “Sau khi login phải gọi AuthenticationManager ở mỗi request”

Trong ứng dụng Servlet stateful thông dụng, Spring Security **khôi phục SecurityContext từ session** ở request tiếp theo. Không cần trao đổi authorization code hoặc xác minh lại ID Token với OP mỗi lần mở trang. Chính sách session và token freshness có thể yêu cầu cơ chế cập nhật hoặc xác thực lại riêng khi nghiệp vụ cần.

### 16.7. “Tắt CSRF để callback chạy”

`state` của Authorization Code Flow giúp liên kết authorization response với request đã lưu, trong khi **CSRF protection của ứng dụng web** bảo vệ các request làm thay đổi trạng thái khi browser tự gửi cookie. Không vô hiệu hóa CSRF toàn bộ chỉ để loại bỏ một lỗi callback mà chưa xác định được chain, method, cookie và cấu hình.

## 17. Theo dõi một tình huống hoàn chỉnh

Giả sử người dùng chưa đăng nhập mở `/orders`.

**Bước A — Request bị yêu cầu xác thực**

```text
Browser -> GET /orders
Spring Security -> lưu request cần quay lại
Spring Security -> điều hướng tới login
```

**Bước B — Khởi tạo OAuth2 Login**

```text
Browser -> GET /oauth2/authorization/academy
Spring -> xây authorization request, lưu state và ngữ cảnh
Spring -> 302 tới Authorization Endpoint của OP
```

**Bước C — Callback vào đúng filter**

```text
Browser -> GET /login/oauth2/code/academy?code=CODE&state=STATE
OAuth2LoginAuthenticationFilter -> đọc response
OAuth2LoginAuthenticationFilter -> lấy authorization request đã lưu
OAuth2LoginAuthenticationFilter -> tạo OAuth2LoginAuthenticationToken
```

**Bước D — AuthenticationManager thực hiện xác thực**

```text
AuthenticationManager -> provider phù hợp (OIDC)
Provider -> đổi CODE lấy token ở OP
Provider -> xác minh ID Token và claims OIDC
Provider -> tạo OidcUser và authorities
```

**Bước E — Filter hoàn tất login**

```text
OAuth2LoginAuthenticationFilter -> chuyển kết quả sang OAuth2AuthenticationToken
OAuth2LoginAuthenticationFilter -> lưu OAuth2AuthorizedClient
AbstractAuthenticationProcessingFilter -> xử lý phiên, SecurityContext, success handler
Browser <- 302 tới /orders
```

**Bước F — Request sau dùng Authentication đã lưu**

```text
Browser -> GET /orders + session cookie
SecurityContextRepository -> khôi phục Authentication
Authorization -> cho phép hoặc từ chối theo authority/chính sách
Controller -> đọc OidcUser/Authentication
```

Ở bước F, controller **không trực tiếp nhận authorization code** và không tự gọi Token Endpoint để xây dựng người dùng. Những phần đó thuộc flow đăng nhập mà Spring Security đã xử lý.

## 18. Bài tập tự kiểm tra

**Câu 1.** Một ứng dụng đăng ký `redirect-uri: "{baseUrl}/login/oauth2/code/academy"`, nhưng filter được cấu hình xử lý `/auth/callback/*`. Điều gì xảy ra?

**Gợi ý:** OP có thể redirect đúng URL mà client đã đăng ký, nhưng request trở về không khớp matcher của login filter. Cần thống nhất redirect URI, redirection endpoint và allowlist của OP.

**Câu 2.** Người dùng đăng nhập thành công ở OP, nhưng callback báo `authorization_request_not_found`. Có nên tự tạo `OAuth2LoginAuthenticationToken` từ code nhận được để tiếp tục không?

**Gợi ý:** Không. Ứng dụng chưa khôi phục được authorization request và các ràng buộc của nó. Điều tra session/cookie/repository; không tự bỏ qua phần xác thực ngữ cảnh.

**Câu 3.** Sau khi callback thành công, trong controller `Authentication` là `OAuth2AuthenticationToken`, còn principal là `OidcUser`. Có bất thường không?

**Gợi ý:** Không. Đây là sự phân biệt đúng giữa đối tượng Authentication dùng trong `SecurityContext` và principal OIDC đại diện người dùng.

**Câu 4.** Một người dùng có `Authentication.isAuthenticated() == true` nhưng bị `403` ở `/admin`.

**Gợi ý:** Authentication trả lời “ai đang đăng nhập”; authorization kiểm tra authorities/chính sách endpoint. Hãy xem ánh xạ quyền, không bắt đầu từ token endpoint.

**Câu 5.** Sau login, ứng dụng muốn gọi downstream API. Nên lấy access token từ `Authentication.getCredentials()` hay từ authorized client?

**Gợi ý:** Dùng `OAuth2AuthorizedClient` và cơ chế quản lý/token refresh phù hợp. Authentication phục vụ principal/authorities của web request; token cấp quyền gọi API được quản lý riêng.

## 19. Những ý chính để ghi nhớ

- **`OAuth2LoginAuthenticationFilter` xử lý callback** của OAuth2/OIDC Login trong ứng dụng Servlet, thường tại `/login/oauth2/code/{registrationId}`.
- Nó **khôi phục authorization request**, xây `OAuth2AuthorizationExchange` và đưa `OAuth2LoginAuthenticationToken` cho `AuthenticationManager`.
- **`AuthenticationProvider`** đảm nhận token exchange, xác minh OAuth2/OIDC và tạo principal `OAuth2User` hoặc `OidcUser`.
- Khi thành công, filter chuyển kết quả thành **`OAuth2AuthenticationToken`**, lưu **`OAuth2AuthorizedClient`** và để quy trình authentication success thiết lập/lưu **`SecurityContext`** theo cơ chế session.
- **Principal, Authentication, SecurityContext, authorized client và session cookie** là các đối tượng/khái niệm phục vụ những mục đích khác nhau.
- Callback lỗi dù OP đã xác thực thành công vẫn có thể do `state`, session, redirect URI, token endpoint, ID Token hoặc cấu hình security chain.
- Với luồng tiêu chuẩn, **để Spring Security quản lý filter và provider**, chỉ tùy biến qua extension point khi có yêu cầu cụ thể; bảo toàn đầy đủ các bước kiểm tra bảo mật.

### Tài liệu tham khảo

- [Spring Security Reference — OAuth 2.0 Login](https://docs.spring.io/spring-security/reference/servlet/oauth2/login/index.html).
- [Spring Security Reference — OAuth 2.0 Login Advanced Configuration](https://docs.spring.io/spring-security/reference/servlet/oauth2/login/advanced.html).
- [Spring Security Reference — OAuth 2.0 Client](https://docs.spring.io/spring-security/reference/servlet/oauth2/client/index.html).
- [Spring Security API — OAuth2LoginAuthenticationFilter](https://docs.spring.io/spring-security/site/docs/current/api/org/springframework/security/oauth2/client/web/OAuth2LoginAuthenticationFilter.html).
- [Spring Security API — OAuth2LoginAuthenticationToken](https://docs.spring.io/spring-security/site/docs/current/api/org/springframework/security/oauth2/client/authentication/OAuth2LoginAuthenticationToken.html).
- [Spring Security API — OAuth2AuthenticationToken](https://docs.spring.io/spring-security/site/docs/current/api/org/springframework/security/oauth2/client/authentication/OAuth2AuthenticationToken.html).
- [Spring Security API — AbstractAuthenticationProcessingFilter](https://docs.spring.io/spring-security/site/docs/current/api/org/springframework/security/web/authentication/AbstractAuthenticationProcessingFilter.html).
- [OpenID Connect Core 1.0 — Authorization Code Flow](https://openid.net/specs/openid-connect-core-1_0.html).
- [RFC 6749 — OAuth 2.0 Authorization Framework](https://www.rfc-editor.org/rfc/rfc6749).
- [RFC 9700 — OAuth 2.0 Security Best Current Practice](https://www.rfc-editor.org/rfc/rfc9700).
