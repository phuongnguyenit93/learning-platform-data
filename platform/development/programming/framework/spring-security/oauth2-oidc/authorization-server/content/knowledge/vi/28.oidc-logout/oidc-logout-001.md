# RP-Initiated Logout và OIDC Logout Endpoint

## 1. Vì sao cần RP-Initiated Logout?

Một ứng dụng Spring Boot dùng OpenID Connect (OIDC) thường có hai trạng thái đăng nhập riêng:

- **Session tại Relying Party (RP):** session/cookie của ứng dụng đang dùng, ví dụ portal hoặc web application.
- **Session tại OpenID Provider (OP):** session SSO của người dùng tại Authorization Server/Identity Provider, có thể được nhiều RP cùng sử dụng.

Khi người dùng bấm “Đăng xuất” ở một RP, việc xóa cookie của RP chỉ kết thúc session cục bộ. Nếu OP vẫn còn session SSO, lần sau người dùng mở RP khác hoặc đăng nhập lại, OP có thể xác thực tự động mà không hỏi mật khẩu. Đây là hành vi bình thường của SSO, nhưng đôi khi không khớp kỳ vọng “đăng xuất khỏi hệ thống”.

**OpenID Connect RP-Initiated Logout 1.0** định nghĩa cách RP chuyển trình duyệt của người dùng tới **Logout Endpoint** của OP để yêu cầu OP kết thúc phiên đăng nhập. OP có thể xác định phiên/ứng dụng yêu cầu logout bằng ID Token đã phát hành trước đó, hỏi người dùng xác nhận khi cần, thực hiện logout và chuyển trình duyệt trở lại RP nếu redirect được phép.

Bài này thuộc chương **OIDC Logout** trong module `SPRING_SECURITY_OAUTH2_OIDC_AUTHORIZATION_SERVER`, tập trung vào **RP-Initiated Logout và OIDC Logout Endpoint** bằng Spring Security và Spring Authorization Server (SAS).

Sau bài học, bạn cần:
1. Phân biệt local logout, RP-Initiated Logout, OP logout và logout notification.
2. Tìm `end_session_endpoint` từ OpenID Provider Configuration.
3. Xây request logout với `id_token_hint`, `post_logout_redirect_uri`, `state` và các tham số tùy chọn.
4. Hiểu quy tắc xác minh ID Token hint và bảo vệ post-logout redirect.
5. Bật và tùy chỉnh Logout Endpoint trong Spring Authorization Server.
6. Kết nối local logout của Spring Security với OP bằng `OidcClientInitiatedLogoutSuccessHandler`.
7. Kiểm thử session lifecycle, redirect, logout idempotency và các tình huống tấn công.

### 1.1. Ba lớp logout trong một hệ thống OIDC

| Lớp | Hành động | Phạm vi |
| --- | --- | --- |
| **RP local logout** | Xóa session/cookie và SecurityContext của ứng dụng | Chỉ RP hiện tại |
| **OP logout** | OP kết thúc session SSO của người dùng | Phiên tại OP; ảnh hưởng khả năng SSO về sau |
| **RP logout notification** | OP báo các RP khác cần kết thúc session tương ứng | Các RP có triển khai front-channel/back-channel/session-management phù hợp |

Một thao tác RP-Initiated Logout thường phối hợp cả local logout và yêu cầu OP logout. Tuy nhiên, các lớp này có cơ chế và kết quả độc lập. Xóa session ở RP không tự xóa session OP; OP logout cũng không tự động chứng minh mọi RP khác đã xử lý thông báo; logout không đồng nghĩa mọi access token đã bị thu hồi.

## 2. Luồng RP-Initiated Logout

RP yêu cầu logout bằng cách điều hướng User Agent (thường là browser) tới Logout Endpoint đã được OP công bố. OP xác minh request, xử lý session và có thể điều hướng browser về RP.

~~~mermaid
sequenceDiagram
    autonumber
    participant U as Người dùng / Browser
    participant RP as Spring Boot RP
    participant OP as Spring Authorization Server / OP
    participant Other as RP khác
    U->>RP: POST /logout (CSRF token)
    RP->>RP: Invalidate local session, clear SecurityContext
    RP->>RP: Tạo logout request từ ID Token đã lưu
    RP-->>U: Redirect tới end_session_endpoint
    U->>OP: GET/POST logout với id_token_hint, redirect URI, state
    OP->>OP: Validate ID Token hint và client/redirect
    OP->>U: Hiển thị xác nhận nếu cần
    U->>OP: Xác nhận logout
    OP->>OP: Kết thúc OP session
    OP->>Other: Logout notification nếu có cơ chế hỗ trợ
    OP-->>U: Redirect về post_logout_redirect_uri + state
    U->>RP: Callback sau logout
    RP->>RP: Kiểm tra state và hiển thị trang đã đăng xuất
~~~

Sơ đồ mô tả luồng có bước xác nhận; OP có thể không cần hỏi lại nếu ID Token hint xác định đúng session hiện tại và policy của OP cho phép. RP có thể local logout trước khi redirect hoặc phối hợp thời điểm local logout theo trải nghiệm sản phẩm. Cần có phương án xử lý khi browser đóng, mạng lỗi, OP từ chối logout hoặc notification không tới.

## 3. Discovery: tìm Logout Endpoint bằng end_session_endpoint

### 3.1. Không tự đoán URL logout

RP cần biết URL Logout Endpoint. Theo RP-Initiated Logout 1.0, khi OP hỗ trợ Discovery, OpenID Provider Configuration phải công bố metadata:

~~~json
{
  "issuer": "https://auth.example.com",
  "authorization_endpoint": "https://auth.example.com/oauth2/authorize",
  "token_endpoint": "https://auth.example.com/oauth2/token",
  "jwks_uri": "https://auth.example.com/oauth2/jwks",
  "end_session_endpoint": "https://auth.example.com/connect/logout"
}
~~~

Đây là response minh họa. `end_session_endpoint` là URL HTTPS tại OP nhận logout request. RP lấy giá trị này từ discovery document đã xác minh issuer/TLS, hoặc từ một kênh cấu hình tin cậy khác được đặc tả cho phép.

Không tự ghép `/logout` hoặc `/connect/logout` vào issuer. Endpoint path có thể thay đổi theo cấu hình của OP.

### 3.2. Nếu metadata không có end_session_endpoint

Nếu OP không công bố `end_session_endpoint`:
- RP không được giả định OP hỗ trợ RP-Initiated Logout.
- RP vẫn có thể kết thúc session cục bộ.
- Nếu tổ chức cấu hình endpoint bằng kênh ngoài Discovery, phải xác minh endpoint đó thuộc đúng OP và có hợp đồng tương thích.
- Không điều hướng tới một URL logout do query parameter hoặc dữ liệu không tin cậy cung cấp.

Discovery metadata có thể chứa endpoint khác cho authorization, token, UserInfo hoặc revocation; chúng không thay thế Logout Endpoint.

## 4. Các tham số của RP-Initiated Logout Request

RP-Initiated Logout 1.0 định nghĩa các tham số sau:

| Tham số | Mức yêu cầu | Mục đích |
| --- | --- | --- |
| `id_token_hint` | **RECOMMENDED** | ID Token trước đây OP phát hành cho RP, làm gợi ý xác định người dùng/session và client yêu cầu logout |
| `logout_hint` | OPTIONAL | Gợi ý về người dùng/session; semantics do OP quyết định |
| `client_id` | OPTIONAL | OAuth Client Identifier; có thể xác định client khi không gửi ID Token hint |
| `post_logout_redirect_uri` | OPTIONAL | URI browser sẽ được chuyển về sau logout |
| `state` | OPTIONAL | Giá trị opaque để RP liên kết logout request với callback |
| `ui_locales` | OPTIONAL | Ngôn ngữ UI người dùng mong muốn, theo BCP 47 |

`id_token_hint` là khuyến nghị quan trọng vì nó giúp OP biết RP nào và subject/session nào đang yêu cầu logout. Nếu cả `client_id` và `id_token_hint` cùng xuất hiện, OP **MUST** xác minh client ID khớp với client đã dùng khi phát hành ID Token đó.

`logout_hint` không phải bằng chứng xác thực. Ví dụ email, số điện thoại, username hoặc session identifier do RP truyền chỉ là gợi ý; OP không được xem chúng như một ID Token đã xác minh.

### 4.1. id_token_hint

ID Token hint là ID Token trước đó OP phát hành cho RP. OP phải xác minh mình là issuer của token đó. OP nên chấp nhận ID Token dù `exp` đã qua nếu `aud` và/hoặc `sid` của token cho thấy RP có session hiện tại hoặc gần đây tại OP.

Không nên từ chối logout chỉ vì ID Token hint hết hạn. ID Token được dùng làm **hint để tìm session**, không phải access token mới để gọi API. Tuy nhiên, nếu `sid` không khớp session hiện tại hoặc session gần đây của RP tại OP, OP nên xem request là đáng ngờ và có thể từ chối xử lý.

Nếu ID Token có `aud` chứa nhiều giá trị, OP vẫn phải xác định đúng client đã được phát hành token. Nếu request đồng thời gửi `client_id`, hai thông tin phải nhất quán.

### 4.2. post_logout_redirect_uri

Đây là URI mà RP đề nghị OP chuyển browser về sau khi logout hoàn tất. URI:
- Nên dùng HTTPS.
- Phải được đăng ký trước với OP qua `post_logout_redirect_uris` hoặc một cơ chế đăng ký khác.
- Phải khớp **chính xác** một URI đã đăng ký; không dùng wildcard domain hoặc prefix matching.
- Có thể chứa port, path và query theo quy tắc của đặc tả.
- Có thể dùng scheme khác cho native application callback nếu OP hỗ trợ và URI đó được đăng ký.

HTTP chỉ có thể được chấp nhận trong trường hợp client confidential và OP cho phép HTTP RP URI; HTTPS vẫn là lựa chọn nên dùng trong production.

Nếu `post_logout_redirect_uri` được gửi mà không có `id_token_hint`, OP **MUST NOT** redirect về RP trừ khi OP có cách khác để xác nhận tính hợp lệ của redirect target. Điều này ngăn attacker dùng Logout Endpoint làm open redirect.

### 4.3. state

`state` là chuỗi opaque do RP sinh để liên kết request với callback. Nên:
- Sinh giá trị ngẫu nhiên đủ entropy.
- Lưu liên kết state với browser session/logout transaction.
- Dùng một lần và có thời hạn.
- So sánh chính xác khi OP trả lại state.
- Không chứa access token, refresh token, ID Token hoặc dữ liệu PII.

Không dùng `state` thay cho kiểm tra `post_logout_redirect_uri`. State bảo vệ tính liên kết của giao dịch; allowlist redirect bảo vệ đích điều hướng.

## 5. Gửi Logout Request bằng GET hoặc POST

OP phải hỗ trợ cả HTTP GET và POST tại Logout Endpoint. RP có thể chọn một trong hai:
- GET: tham số được serialize thành query string.
- POST: tham số được serialize theo form encoding, thường là `application/x-www-form-urlencoded`.

### 5.1. Ví dụ GET

~~~http
GET /connect/logout?id_token_hint=SIGNED_ID_TOKEN&post_logout_redirect_uri=https%3A%2F%2Fportal.example.com%2Flogged-out&state=OPAQUE_STATE HTTP/1.1
Host: auth.example.com
~~~

Browser điều hướng tới URL được tạo từ `end_session_endpoint` và tham số đã URL-encode.

### 5.2. Ví dụ POST

~~~http
POST /connect/logout HTTP/1.1
Host: auth.example.com
Content-Type: application/x-www-form-urlencoded

id_token_hint=SIGNED_ID_TOKEN&post_logout_redirect_uri=https%3A%2F%2Fportal.example.com%2Flogged-out&state=OPAQUE_STATE
~~~

POST có thể giảm việc đưa ID Token hint vào query string, access log và browser history, nhưng không biến ID Token thành dữ liệu bí mật an toàn tuyệt đối. Form body vẫn có thể xuất hiện trong log nếu hệ thống ghi request body.

### 5.3. Chọn GET hay POST

| Tiêu chí | GET | POST |
| --- | --- | --- |
| Tương thích redirect đơn giản | Tốt | Cần form-post strategy hoặc trang form |
| Tham số | Query string | Form body |
| Browser history/access log | Có nguy cơ ghi query chứa hint | Thường ít lộ trong URL hơn |
| CSRF | Điều hướng top-level vẫn cần policy logout phù hợp | Cần kiểm soát form submission và origin/CSRF policy |
| Đặc tả | OP MUST hỗ trợ | OP MUST hỗ trợ |

Dù chọn cách nào, RP phải dùng đúng endpoint từ metadata và không tự nhận response redirect là bằng chứng rằng mọi session/token trong hệ thống đã bị hủy.

## 6. OP xử lý Logout Request như thế nào?

### 6.1. Xác minh id_token_hint

Khi có `id_token_hint`, OP:
1. Kiểm tra định dạng và xác minh chữ ký/issuer theo key do chính OP quản lý.
2. Xác nhận token do OP phát hành.
3. Xác định client từ `aud` và thông tin client liên quan.
4. Nếu request có `client_id`, kiểm tra khớp client phát hành ID Token.
5. Xác định session bằng `sid` và/hoặc quan hệ session hiện có của user/client.
6. Kiểm tra request có liên quan đến session hiện tại hoặc session gần đây hay không.
7. Nếu không thể liên kết an toàn, xử lý request như đáng ngờ theo đặc tả và policy.

ID Token hint có thể đã hết hạn. OP nên chấp nhận token hết hạn nếu RP được nêu trong `aud` và/hoặc `sid` có session hiện tại hoặc gần đây tại OP. Không được dùng quy tắc “ID Token hết hạn là luôn từ chối logout” một cách máy móc.

### 6.2. Xác nhận người dùng

OP nên hỏi End-User có muốn đăng xuất khỏi OP hay không. OP **MUST** hỏi nếu:
- Request không có `id_token_hint`; hoặc
- ID Token được gửi không thuộc session OP hiện tại với RP và/hoặc người dùng đang đăng nhập.

Nếu người dùng trả lời đồng ý, OP phải thực hiện logout. Việc xác nhận đặc biệt hữu ích khi không có bằng chứng đủ mạnh để xác định RP/subject/session yêu cầu logout, tránh request giả mạo gây logout hàng loạt hoặc denial of service.

Nếu người dùng từ chối, OP không thực hiện logout OP theo yêu cầu đó. Nếu RP đã kết thúc local session trước khi điều hướng, người dùng vẫn đăng xuất khỏi RP khởi tạo; RP không nên tự tạo session mới chỉ vì OP giữ SSO session.

### 6.3. Logout idempotent

RP-Initiated Logout được thiết kế theo hướng idempotent. Nếu OP không còn xem End-User là đang đăng nhập với RP yêu cầu, việc RP gửi logout request không tự nó là protocol error. OP có thể hiển thị trang phù hợp hoặc tiếp tục theo policy.

Tuy vậy, request validation thất bại thì OP không được dùng dữ liệu không hợp lệ và **MUST NOT** thực hiện post-logout redirect về RP. Không được biến tính idempotent thành lý do chấp nhận redirect URI tùy ý.

### 6.4. Kết thúc OP session

Khi logout được chấp thuận:
- OP kết thúc session đăng nhập tương ứng theo session model của OP.
- Xóa/expire cookie và SecurityContext/session server-side theo implementation.
- Thực hiện logout notification cho các RP đã đăng nhập nếu OP/RP hỗ trợ cơ chế tương ứng.
- Chỉ sau khi xử lý notification theo quy tắc, OP mới thực hiện post-logout redirect nếu request hợp lệ và redirect đã được xác minh.

Việc OP xóa session browser không đồng nghĩa access token JWT đã phát hành tự biến mất hoặc mọi resource server lập tức từ chối token đó. Token revocation và session logout là các cơ chế khác nhau.

## 7. Bảo vệ post-logout redirect

### 7.1. Đăng ký redirect URI trước

Một client registration có thể chứa danh sách:

~~~json
{
  "client_id": "portal-web",
  "post_logout_redirect_uris": [
    "https://portal.example.com/logged-out",
    "https://portal.example.com/session/ended"
  ]
}
~~~

Khi nhận request:

~~~text
requested = post_logout_redirect_uri
registered = client.post_logout_redirect_uris

if requested exactly matches one registered URI:
    allow post-logout redirect
else:
    reject request and do not redirect to RP
~~~

Không cho phép:
- `https://portal.example.com.attacker.example/` chỉ vì chuỗi bắt đầu bằng domain hợp lệ.
- `https://portal.example.com@attacker.example/`.
- Wildcard `https://*.example.com/logout` nếu không có cơ chế xác thực/đăng ký cụ thể an toàn.
- HTTP redirect target không được policy cho phép.
- URI do query parameter khác hoặc cookie ghi đè.

### 7.2. Không redirect khi thiếu bằng chứng client

Nếu có `post_logout_redirect_uri` nhưng không có `id_token_hint`, OP phải có cơ chế khác để xác nhận redirect target thuộc client thực sự yêu cầu. Ví dụ `client_id` đã được xác thực qua một quy trình phù hợp cùng đăng ký redirect URI có thể là đầu vào cho quyết định, nhưng không được bỏ qua yêu cầu xác minh legitimacy của OP.

### 7.3. Kiểm tra state ở RP

Khi browser quay lại `post_logout_redirect_uri`, OP trả lại nguyên giá trị `state` nếu request đã có state:
- RP đọc `state`.
- So khớp với transaction đang chờ trong session/cookie server-side.
- Từ chối callback không có state tương ứng hoặc state đã dùng/hết hạn.
- Không dùng callback query để khôi phục access token hoặc tạo session đăng nhập mới.
- Xóa transaction sau khi xử lý.

Trang logged-out nên là trang thông tin đơn giản, không tự đăng nhập lại hoặc điều hướng tới URL tùy ý do callback cung cấp.

## 8. Local logout tại Relying Party với Spring Security

### 8.1. Spring Security local logout làm gì?

Với Servlet application, Spring Security cung cấp Logout Filter. Khi logout qua POST hợp lệ, các handler mặc định thường:
- Invalidate HTTP session.
- Xóa SecurityContextHolder và SecurityContextRepository.
- Dọn remember-me authentication.
- Xóa CSRF token.
- Phát LogoutSuccessEvent.
- Chuyển tới logout success handler.

Khi CSRF protection bật, RP nên dùng POST logout với CSRF token. GET logout mặc định có thể hiển thị trang xác nhận để lấy CSRF token; không biến GET tùy tiện thành thao tác thay đổi trạng thái nếu chưa cân nhắc CSRF.

### 8.2. Tích hợp OidcClientInitiatedLogoutSuccessHandler

Spring Security OAuth2 Client cung cấp `OidcClientInitiatedLogoutSuccessHandler`. Handler này sử dụng `ClientRegistrationRepository`, thông tin OIDC login (bao gồm ID Token) và provider metadata để điều hướng tới `end_session_endpoint` khi provider công bố endpoint đó.

Ví dụ cấu hình Servlet:

~~~java
@Bean
LogoutSuccessHandler oidcLogoutSuccessHandler(
        ClientRegistrationRepository clientRegistrationRepository) {

    OidcClientInitiatedLogoutSuccessHandler handler =
            new OidcClientInitiatedLogoutSuccessHandler(
                    clientRegistrationRepository);

    // URI này phải được đăng ký trước ở OpenID Provider.
    handler.setPostLogoutRedirectUri("{baseUrl}/logged-out");

    return handler;
}

@Bean
SecurityFilterChain applicationSecurity(
        HttpSecurity http,
        LogoutSuccessHandler oidcLogoutSuccessHandler) throws Exception {

    http
        .authorizeHttpRequests(authorize -> authorize
            .anyRequest().authenticated()
        )
        .oauth2Login(Customizer.withDefaults())
        .logout(logout -> logout
            .logoutSuccessHandler(oidcLogoutSuccessHandler)
        );

    return http.build();
}
~~~

`{baseUrl}` là placeholder do handler hỗ trợ, được thay bằng base URL của ứng dụng tại thời điểm xử lý. Nếu sử dụng path `/logged-out`, URI đầy đủ phải được đăng ký với OP, ví dụ `https://portal.example.com/logged-out`.

Handler thực hiện local logout theo Spring Security rồi điều hướng browser tới OP. RP nên kiểm thử với ClientRegistration có provider metadata chứa `end_session_endpoint`. Nếu OP không công bố endpoint hoặc Authentication không phải OIDC login, ứng dụng cần cấu hình logout fallback phù hợp.

### 8.3. GET redirect hay POST form

`OidcClientInitiatedLogoutSuccessHandler` mặc định dùng HTTP redirect GET tới OP. Nếu muốn gửi request bằng POST form, Spring Security cung cấp `FormPostRedirectStrategy`:

~~~java
@Bean
LogoutSuccessHandler oidcLogoutSuccessHandler(
        ClientRegistrationRepository registrations) {

    OidcClientInitiatedLogoutSuccessHandler handler =
            new OidcClientInitiatedLogoutSuccessHandler(registrations);

    handler.setPostLogoutRedirectUri("{baseUrl}/logged-out");
    handler.setRedirectStrategy(new FormPostRedirectStrategy());

    return handler;
}
~~~

POST form có thể phù hợp khi không muốn ID Token hint nằm trong query string. Cần kiểm thử CSP, browser behavior, OP hỗ trợ POST và trang/form redirect được tạo đúng. Không tự viết HTML form nhận endpoint từ input không tin cậy.

### 8.4. Lưu ID Token đủ lâu cho logout

RP cần giữ ID Token trong Authentication/session theo vòng đời đăng nhập để handler có thể gửi `id_token_hint`. Không lưu ID Token vào URL nội bộ, local storage hoặc log chỉ để phục vụ logout. Nếu ứng dụng đã xóa toàn bộ Authentication trước khi tạo logout request, handler có thể không còn ID Token để gửi; hãy để Spring Logout Filter điều phối success handler hoặc tự thiết kế một flow có lưu trữ an toàn.

## 9. Bật OIDC Logout Endpoint trong Spring Authorization Server

### 9.1. OIDC cần được bật

Spring Authorization Server hỗ trợ OIDC Logout Endpoint qua `OidcLogoutEndpointConfigurer`. OIDC không được bật chỉ vì OAuth Authorization Server endpoints đang chạy; cần cấu hình `oidc(...)` trên `OAuth2AuthorizationServerConfigurer`.

Ví dụ SAS 1.5.x:

~~~java
@Bean
@Order(Ordered.HIGHEST_PRECEDENCE)
SecurityFilterChain authorizationServerSecurityFilterChain(
        HttpSecurity http) throws Exception {

    OAuth2AuthorizationServerConfigurer authorizationServer =
            OAuth2AuthorizationServerConfigurer.authorizationServer();

    http
        .securityMatcher(authorizationServer.getEndpointsMatcher())
        .with(authorizationServer, server -> server
            .oidc(oidc -> oidc
                .logoutEndpoint(Customizer.withDefaults())
            )
        )
        .authorizeHttpRequests(authorize -> authorize
            .anyRequest().authenticated()
        );

    return http.build();
}
~~~

Đây là phần cấu hình filter chain Authorization Server; ứng dụng thực tế còn cần chain login, client repository, authorization service, issuer, JWK source và các bean nền tảng khác. OIDC Logout Endpoint được filter của SAS xử lý, không phải một controller tự viết có thể nhận mọi URL redirect.

### 9.2. Cấu hình đường dẫn trong AuthorizationServerSettings

SAS mặc định sử dụng `/connect/logout` cho OIDC Logout Endpoint. Có thể thay đổi:

~~~java
@Bean
AuthorizationServerSettings authorizationServerSettings() {
    return AuthorizationServerSettings.builder()
            .issuer("https://auth.example.com")
            .oidcLogoutEndpoint("/connect/v1/logout")
            .build();
}
~~~

Khi thay đổi path, discovery metadata `end_session_endpoint` phải phản ánh URL public tương ứng. RP không được tiếp tục dùng path cũ. Với reverse proxy, kiểm tra scheme/host/path external để metadata không trả địa chỉ nội bộ.

### 9.3. OidcLogoutEndpointConfigurer có những extension point nào?

`OidcLogoutEndpointConfigurer` cho phép tùy chỉnh:
- `logoutRequestConverter` / `logoutRequestConverters`: đọc HTTP request và tạo `OidcLogoutAuthenticationToken`.
- `authenticationProvider` / `authenticationProviders`: xác thực logout request và kiểm tra tham số.
- `logoutResponseHandler`: xử lý logout thành công.
- `errorResponseHandler`: xử lý lỗi xác thực và trả OAuth/OIDC error response.

SAS mặc định cung cấp:
- `OidcLogoutAuthenticationConverter`.
- `OidcLogoutAuthenticationProvider`.
- `OidcLogoutAuthenticationSuccessHandler`.
- Error handler nội bộ gắn với `OAuth2Error`.

Không thay default converter/provider/handler chỉ để thay đổi một chi tiết nhỏ nếu extension point phù hợp hơn. Customization phải giữ các validation bắt buộc, đặc biệt là kiểm tra `id_token_hint`, client và redirect URI.

### 9.4. Custom validation cho post_logout_redirect_uri

SAS có validator mặc định `OidcLogoutAuthenticationValidator` để kiểm tra các tham số logout, trong đó có `post_logout_redirect_uri`. Nếu cần policy riêng, `OidcLogoutAuthenticationProvider` cho phép cài `Consumer<OidcLogoutAuthenticationContext>` qua `setAuthenticationValidator(...)`.

Một custom validator cần:
1. Lấy client/session context từ authentication token đã được xác minh.
2. So sánh redirect URI chính xác với danh sách đã đăng ký.
3. Kiểm tra điều kiện có `id_token_hint` hoặc bằng chứng khác khi redirect.
4. Ném `OAuth2AuthenticationException` nếu validation thất bại.
5. Không redirect về URL chưa được xác minh.

Không viết validator chỉ kiểm tra domain bằng `startsWith` hoặc regex lỏng. Nếu thay validator mặc định, cần giữ toàn bộ quy tắc bảo mật của đặc tả và kiểm thử các trường hợp open redirect.

## 10. SessionRegistry trong Spring Authorization Server

### 10.1. Vì sao logout endpoint cần SessionRegistry?

SAS dùng `SessionRegistry` để theo dõi các session người dùng đã xác thực. `OidcLogoutAuthenticationProvider` sử dụng registry để tìm `SessionInformation` gắn với End-User đang yêu cầu logout.

Khi OIDC bật:
- Nếu ứng dụng không đăng ký `SessionRegistry` bean, SAS có thể dùng implementation mặc định `SessionRegistryImpl`.
- Nếu đăng ký `SessionRegistryImpl` riêng, nên đăng ký thêm `HttpSessionEventPublisher` để phát các session lifecycle events như `SessionDestroyedEvent` và giúp registry loại bỏ session đã hủy.
- Nếu Spring Security Concurrent Session Control cũng sử dụng registry, nên dùng chung một bean để trạng thái session nhất quán.

Ví dụ:

~~~java
@Bean
SessionRegistry sessionRegistry() {
    return new SessionRegistryImpl();
}

@Bean
HttpSessionEventPublisher httpSessionEventPublisher() {
    return new HttpSessionEventPublisher();
}
~~~

Không tạo hai SessionRegistry khác nhau cho cùng một hệ thống rồi kỳ vọng logout endpoint luôn tìm được session mà Authorization Endpoint đã đăng ký.

### 10.2. Cluster và distributed session

Trong triển khai nhiều instance:
- Session store và registry phải có khả năng nhìn thấy session trên các node.
- Session destruction event phải được truyền hoặc đồng bộ.
- Không dùng registry in-memory độc lập ở từng node nếu request có thể tới node khác.
- Kiểm thử logout khi authorization request chạy ở node A nhưng logout request chạy ở node B.
- Đảm bảo reverse proxy/load balancer không làm sai session cookie hoặc issuer.

Một SessionRegistry in-memory đơn node có thể phù hợp cho demo, nhưng không tự giải quyết distributed session tracking.

## 11. RP-Initiated Logout khác Front-Channel và Back-Channel Logout

RP-Initiated Logout là **RP yêu cầu OP logout** bằng điều hướng browser tới Logout Endpoint. Việc OP thông báo cho các RP khác là một phần phối hợp riêng.

| Cơ chế | Ai khởi tạo? | Kênh thông báo | RP xử lý |
| --- | --- | --- | --- |
| RP-Initiated Logout | RP | Browser redirect tới OP | RP yêu cầu OP kết thúc session |
| Front-Channel Logout | OP | Browser/iframe điều hướng tới RP | RP nhận logout qua browser context |
| Back-Channel Logout | OP | HTTP server-to-server | RP nhận Logout Token và kết thúc session liên quan |
| Session Management | RP kiểm tra trạng thái OP qua browser | Browser communication/iframe | Phát hiện session OP thay đổi theo cơ chế riêng |
| Local logout | Người dùng hoặc ứng dụng | Nội bộ RP | Chỉ xóa session tại RP hiện tại |

### 11.1. Front-Channel Logout

OP có thể mở front-channel logout URI của các RP qua browser. Cách này phụ thuộc browser, iframe và cookie policy. Third-party cookie blocking, SameSite và privacy protection của browser có thể ảnh hưởng việc RP tìm đúng session.

RP không nên coi một iframe request đơn thuần là bằng chứng mạnh rằng người dùng đã xác thực mới. Front-channel endpoint cần nhận diện session phù hợp theo cơ chế đã đăng ký và xử lý idempotent.

### 11.2. Back-Channel Logout

Back-channel logout là thông báo server-to-server từ OP tới RP. OP gửi Logout Token (JWT) theo Back-Channel Logout 1.0; RP xác minh chữ ký, issuer, audience, thời gian và event claim trước khi kết thúc session tương ứng.

Logout Token không phải ID Token hint:
- `id_token_hint` đi từ RP tới OP trong RP-Initiated Logout Request.
- Logout Token đi từ OP tới RP để thông báo logout.
- Không dùng một loại token thay thế loại kia.

Nếu hỗ trợ back-channel logout, RP cần mapping `sid` và/hoặc `sub` tới các local sessions, replay protection và xử lý notification nhiều lần. Việc bật RP-Initiated Logout Endpoint trong SAS **không tự chứng minh** hệ thống đã triển khai đầy đủ Front-Channel hoặc Back-Channel Logout.

## 12. Logout không đồng nghĩa token revocation

Logout Endpoint chủ yếu xử lý session đăng nhập. OAuth Token Revocation (RFC 7009) là endpoint/protocol riêng để thu hồi access token hoặc refresh token theo khả năng của OP.

| Tài nguyên | RP local logout | OP session logout | Token revocation |
| --- | --- | --- | --- |
| RP session cookie | Có thể xóa | Không nhất thiết | Không |
| OP SSO cookie/session | Không | Có | Không nhất thiết |
| Access token JWT đã phát hành | Không tự vô hiệu | Không tự vô hiệu ngay nếu RS chỉ kiểm chữ ký/exp | Phụ thuộc RS/token format và revocation support |
| Refresh token | Không tự thu hồi | Không tự động đồng nghĩa thu hồi | Có thể thu hồi theo endpoint/policy |
| Session ở RP khác | Không | Chỉ khi notification mechanism hỗ trợ và RP xử lý | Không tự động |
| SecurityContext tại RP hiện tại | Có | Không trực tiếp | Không |

Nếu yêu cầu nghiệp vụ là “người dùng logout thì token không thể dùng tiếp”, cần thiết kế thêm:
- Thu hồi refresh token hoặc authorization tương ứng.
- Access token lifetime ngắn, introspection hoặc revocation-aware resource server khi cần.
- Logout notification để các RP xóa local session.
- Chính sách xử lý token đã phát hành, cache và distributed session.
- Audit để biết request logout đã kết thúc những thành phần nào.

Không hứa “global logout hoàn tất” chỉ dựa vào redirect thành công tới OP.

## 13. Bảo mật và lỗi triển khai thường gặp

| Rủi ro | Nguyên nhân | Biện pháp |
| --- | --- | --- |
| Open redirect | OP chấp nhận post_logout_redirect_uri tùy ý | Exact match URI đã đăng ký; fail closed |
| Logout CSRF | Endpoint local logout GET hoặc form thiếu CSRF protection | POST có CSRF token tại RP; policy phù hợp tại OP |
| Client mix-up | client_id không khớp ID Token hint | Nếu cả hai cùng có, bắt buộc xác minh match |
| Token hint misuse | Dùng ID Token từ issuer/client khác | OP xác minh issuer, audience/client và session |
| ID Token hint bị lộ | Ghi query URL vào access log/history | POST form khi phù hợp, redact log, không analytics URL |
| Replay | Lặp callback/state hoặc logout transaction | State entropy cao, one-time, expiration; xử lý idempotent |
| Session confusion | ID Token sid không thuộc session hiện tại | Kiểm tra session registry; xử lý suspect request |
| Cross-tenant logout | Cùng subject string nhưng khác issuer/tenant | Ràng buộc issuer + subject + session + client |
| Fake logout_hint | Tin email/username như proof | Xem logout_hint chỉ là hint, không phải credential |
| Incomplete global logout | Chỉ xóa RP hiện tại | Thiết kế notification/revocation riêng |
| Stale SessionRegistry | Registry không nhận session-destroyed event | HttpSessionEventPublisher hoặc distributed session store |
| Host/issuer poisoning | Suy endpoint từ Host/forwarded header không tin | Cấu hình issuer public cố định và trusted proxy |

### 13.1. ID Token hint có thể xuất hiện trong URL

Nếu dùng GET, `id_token_hint` có thể nằm trong query string. JWT thường có claims nhận dạng user và có thể xuất hiện trong:
- Reverse proxy access log.
- Browser history.
- APM/tracing.
- Referrer nếu cấu hình không phù hợp.
- Hệ thống phân tích URL.

Có thể dùng POST form redirect nếu OP hỗ trợ. Dù dùng GET hay POST, vẫn cần redact log và tránh lưu raw request body/query chứa token. Không coi ID Token hint là secret thay cho access token, nhưng vẫn phải bảo vệ nó như credential nhạy cảm.

### 13.2. Logout request không có id_token_hint

Một request không có `id_token_hint` có thể gây logout sai người dùng nếu OP không xác nhận. Đặc tả yêu cầu OP hỏi người dùng xác nhận khi thiếu hint. Nếu OP không thể xác định client/redirect legitimacy, không thực hiện redirect về RP.

### 13.3. Không dùng post_logout_redirect_uri như returnUrl tùy ý

Không lấy `post_logout_redirect_uri` trực tiếp từ tham số mà user gửi tới local `/logout` rồi chuyển tiếp lên OP. RP nên dùng URI đã cấu hình và đăng ký trước. Nếu cần hỗ trợ nhiều trang kết thúc, chọn từ allowlist nội bộ.

## 14. Ma trận kiểm thử RP-Initiated Logout

### 14.1. Kiểm thử Discovery và endpoint

| Test | Hành động | Kỳ vọng |
| --- | --- | --- |
| Discovery metadata | GET OP Configuration | Có `end_session_endpoint` khi OP hỗ trợ logout + Discovery |
| Endpoint HTTPS | Đọc `end_session_endpoint` | URL dùng HTTPS |
| OIDC disabled | Tắt OIDC trong SAS | Không quảng cáo logout endpoint OIDC như thể đang hoạt động |
| Endpoint path | Cấu hình `oidcLogoutEndpoint` custom | Metadata và route thực tế khớp |
| GET request | Gửi GET logout hợp lệ | OP xử lý |
| POST request | Gửi POST form hợp lệ | OP xử lý |
| Unknown endpoint | Dùng path cũ sau khi đổi settings | Không giả định route cũ còn hoạt động |

### 14.2. Kiểm thử tham số và redirect

| Test | Input | Kỳ vọng |
| --- | --- | --- |
| Valid hint | ID Token do OP phát hành, client/session hợp lệ | Xác định đúng session |
| Wrong issuer | Hint từ OP khác | Từ chối/không logout dựa trên hint |
| Expired but recent | Hint hết hạn nhưng session còn hiện tại/gần đây | OP có thể chấp nhận theo đặc tả |
| Stale sid | sid không khớp session hiện tại/gần đây | Xem suspect, có thể từ chối |
| Client mismatch | client_id khác client phát hành hint | Từ chối |
| Registered redirect | URI exact match | Có thể redirect sau logout |
| Prefix lookalike | Domain hợp lệ cộng suffix attacker | Từ chối |
| Unregistered redirect | URI chưa đăng ký | Từ chối và không redirect |
| No hint + redirect | Không có id_token_hint và không có xác minh khác | Không redirect |
| State | State ngẫu nhiên hợp lệ | Trả lại nguyên giá trị |
| State replay | Callback dùng state đã tiêu thụ | RP từ chối callback |
| logout_hint only | Gửi email/username làm hint | Không xem đó là bằng chứng xác thực |
| Idempotency | Logout khi OP session đã hết | Không coi việc không còn session là protocol error |

### 14.3. Kiểm thử Spring Security và session

- POST local logout có CSRF token kết thúc session RP và xóa SecurityContext.
- Logout success handler lấy đúng ID Token của OIDC principal trước khi điều hướng.
- Không có OIDC Authentication thì RP dùng fallback local logout URL.
- Handler dùng `end_session_endpoint` đã discovery, không tự nối path.
- `post_logout_redirect_uri` của handler khớp chính xác URI đăng ký tại OP.
- SessionRegistry tìm đúng session khi logout request chạy ở node khác.
- HttpSessionEventPublisher cập nhật SessionRegistry khi session bị hủy.
- Logout notification lặp lại không làm lỗi hoặc xóa nhầm session khác.
- Access token/refresh token lifecycle được kiểm tra riêng với session logout.
- Logs không chứa ID Token hint, raw Logout Token, refresh token hoặc PII.

## 15. Bài tập tình huống

Một tổ chức có OP tại `https://auth.example.com` và hai RP:
- Portal: `portal-web`.
- Admin Console: `admin-console`.

Cả hai RP dùng cùng OP session. Portal đang có ID Token với `iss` đúng OP, `aud` là `portal-web` và `sid` đại diện phiên SSO hiện tại.

Portal đăng xuất bằng request:

~~~http
GET /connect/logout?id_token_hint=PORTAL_ID_TOKEN&post_logout_redirect_uri=https%3A%2F%2Fportal.example.com%2Flogged-out&state=STATE_123 HTTP/1.1
Host: auth.example.com
~~~

OP phát hiện:
- `post_logout_redirect_uri` đã đăng ký cho `portal-web`.
- Session `sid` vẫn hoạt động.
- Admin Console cũng có session của cùng người dùng.
- Refresh token của portal vẫn còn hạn.
- OP chưa bật Back-Channel Logout.

Hãy phân tích:

1. OP xác định client và session logout từ thông tin nào?
2. Có cần hỏi người dùng xác nhận logout OP không? Vì sao?
3. OP cần làm gì với session của Portal và Admin Console khi chưa có Back-Channel Logout?
4. Refresh token còn hạn có tự bị thu hồi khi OP session bị xóa không?
5. Nếu portal gửi thêm `client_id=admin-console` thì kết quả thế nào?
6. Nếu redirect URI đổi thành `https://portal.example.com.attacker.test/` thì OP phải xử lý ra sao?
7. Nếu ID Token hint hết hạn nhưng `sid` vẫn chỉ đúng session gần đây, OP có thể xử lý thế nào?
8. Đề xuất kiến trúc bổ sung để đáp ứng yêu cầu logout toàn bộ RP và thu hồi refresh token.
9. Viết test chứng minh callback state được xác minh và không thể dùng lại.
10. Mô tả cách cấu hình `OidcClientInitiatedLogoutSuccessHandler` tại Portal.

**Gợi ý:** `id_token_hint` xác định token do OP phát hành cho Portal; `sid` giúp liên kết session. Nếu token hint xác định đúng session hiện tại, OP không bắt buộc hỏi xác nhận trong mọi trường hợp. Logout endpoint phải kết thúc session OP theo policy, notification tới Admin Console cần cơ chế riêng; refresh token không tự động bị revoke chỉ do browser session logout. Client mismatch và redirect URI không khớp phải bị từ chối.

## 16. Checklist triển khai production

1. **Discovery:** OP công bố `end_session_endpoint` HTTPS trong metadata khi hỗ trợ RP-Initiated Logout.
2. **Client registration:** quản lý `post_logout_redirect_uris` riêng cho từng client; exact match.
3. **RP logout:** local POST logout có CSRF protection, xóa session và SecurityContext.
4. **ID Token hint:** gửi ID Token do đúng OP phát hành cho RP; không tạo hint từ user input.
5. **Client binding:** nếu có `client_id` và `id_token_hint`, kiểm tra chúng khớp.
6. **Session lookup:** dùng `sid`/session registry để xác định session hiện tại hoặc gần đây; xử lý token hint hết hạn theo đặc tả.
7. **Confirmation:** hỏi người dùng khi thiếu hint hoặc hint không thuộc session hiện tại theo yêu cầu đặc tả.
8. **Redirect:** chỉ redirect URI đã đăng ký; không redirect nếu validation fail hoặc không xác minh được legitimacy.
9. **State:** entropy cao, one-time, timeout và callback verification.
10. **GET/POST:** OP hỗ trợ cả hai; RP chọn GET/POST theo privacy, compatibility và browser behavior.
11. **SAS:** bật OIDC và cấu hình `OidcLogoutEndpointConfigurer`; không nhầm OAuth logout với OIDC endpoint.
12. **SessionRegistry:** chia sẻ registry với concurrent session control; thêm HttpSessionEventPublisher khi dùng SessionRegistryImpl.
13. **Cluster:** session store/registry đồng bộ giữa các node.
14. **Notifications:** triển khai Front-Channel/Back-Channel Logout nếu cần single logout đa RP; kiểm tra từng cơ chế riêng.
15. **Token lifecycle:** thu hồi refresh/access token theo policy riêng nếu yêu cầu; không giả định session logout tự revoke token.
16. **Observability:** log client/session correlation và outcome code, redact token/PII.
17. **Testing:** kiểm tra mismatch issuer/client/sid, redirect abuse, expired hint, replay state, no-session idempotency và distributed sessions.
18. **Incident response:** có quy trình xử lý session compromise, revoke token, invalidate sessions và thông báo RP.

## 17. Tài liệu chuẩn và Spring cần đối chiếu

- [OpenID Connect RP-Initiated Logout 1.0 — Final](https://openid.net/specs/openid-connect-rpinitiated-1_0.html): logout request, tham số, discovery metadata, redirect validation và security considerations.
- [OpenID Connect Discovery 1.0](https://openid.net/specs/openid-connect-discovery-1_0.html): OpenID Provider Configuration và endpoint metadata.
- [OpenID Connect Session Management 1.0](https://openid.net/specs/openid-connect-session-1_0.html): session state và logout phối hợp.
- [OpenID Connect Front-Channel Logout 1.0](https://openid.net/specs/openid-connect-frontchannel-1_0.html): logout notification qua browser.
- [OpenID Connect Back-Channel Logout 1.0](https://openid.net/specs/openid-connect-backchannel-1_0.html): Logout Token và server-to-server notification.
- [RFC 7009 — OAuth 2.0 Token Revocation](https://www.rfc-editor.org/rfc/rfc7009.html): thu hồi access/refresh token, khác với logout session.
- [Spring Authorization Server 1.5.x — Protocol Endpoints](https://docs.spring.io/spring-authorization-server/reference/protocol-endpoints.html): `OidcLogoutEndpointConfigurer`, converter/provider và logout response/error handlers.
- [Spring Authorization Server 1.5.x — Configuration Model](https://docs.spring.io/spring-authorization-server/reference/configuration-model.html): `AuthorizationServerSettings` và endpoint `/connect/logout`.
- [Spring Authorization Server — SessionRegistry](https://docs.spring.io/spring-authorization-server/reference/core-model-components.html): đăng ký authenticated sessions, logout lookup và HttpSessionEventPublisher.
- [Spring Security — OIDC Logout](https://docs.spring.io/spring-security/reference/servlet/oauth2/login/logout.html): `OidcClientInitiatedLogoutSuccessHandler` và local logout integration.
- [Spring Security — Handling Logouts](https://docs.spring.io/spring-security/reference/servlet/authentication/logout.html): Logout Filter, CSRF, session invalidation và LogoutHandler.

**Ghi nhớ:** RP-Initiated Logout là request từ RP yêu cầu OP kết thúc session SSO thông qua `end_session_endpoint`. `id_token_hint` giúp OP xác định đúng issuer/client/session; `post_logout_redirect_uri` chỉ được dùng khi đã xác minh và khớp chính xác URI đăng ký; `state` liên kết callback với transaction của RP. Trong Spring Security, `OidcClientInitiatedLogoutSuccessHandler` phối hợp local logout với redirect tới OP. Trong Spring Authorization Server, `OidcLogoutEndpointConfigurer` xử lý logout request và `SessionRegistry` giúp tìm session tương ứng. Logout session không tự động thu hồi mọi access/refresh token hoặc đăng xuất mọi RP khác; cần thiết kế token revocation và Front-Channel/Back-Channel Logout riêng khi yêu cầu nghiệp vụ cần chúng.
