# 27.2. CSRF tại authorization endpoint, callback và logout

## 1. Bài toán: đã có OAuth2 Login thì còn cần CSRF không?

Một ứng dụng Spring Security cho người dùng đăng nhập bằng OpenID Connect (OIDC). Người triển khai thấy rằng luồng OAuth2 đã có tham số <code>state</code>, nên quyết định:

~~~java
http.csrf(csrf -> csrf.disable());
~~~

Ứng dụng đăng nhập vẫn hoạt động. Nhưng người dùng đã đăng nhập bằng **session cookie** có thể bị một website bên ngoài dụ gửi yêu cầu thay đổi dữ liệu tới ứng dụng, chẳng hạn:

~~~html
<form action="https://portal.example.org/account/change-email"
      method="post">
    <input name="email" value="attacker@example.org">
</form>
<script>document.forms[0].submit();</script>
~~~

Nếu browser tự đính kèm cookie xác thực của <code>portal.example.org</code> và endpoint không kiểm tra CSRF, server có thể xử lý request như thể người dùng chủ động đổi email. Việc OIDC Login đã có <code>state</code> **không** bảo vệ endpoint <code>/account/change-email</code>.

Mặt khác, nếu bật CSRF protection của Spring Security một cách máy móc cho **mọi POST**, ứng dụng có thể gặp lỗi ở một OIDC callback sử dụng <code>response_mode=form_post</code> hoặc endpoint nhận **Back-Channel Logout** từ OpenID Provider (OP), bởi request đó không đến từ form thông thường của browser có sẵn CSRF token của portal.

Vì vậy, bài toán thực sự là **xác định đúng mô hình CSRF cho từng điểm của giao thức**:

1. **Authorization initiation và Authorization Endpoint:** Người dùng bắt đầu OAuth2 login thế nào, ai kiểm soát authorization request, CSRF của OP khác CSRF của Client ra sao?
2. **Callback:** Làm sao biết authorization response đúng là kết quả của authorization request mà browser đã bắt đầu?
3. **Logout:** Browser có được ép kết thúc session của người khác bằng GET/POST cross-site không, và Back-Channel Logout từ OP được xác thực ra sao?
4. **Các nghiệp vụ sau đăng nhập:** Form POST, PATCH, DELETE dựa trên cookie/session còn cần CSRF token hay không?

> **Nguyên tắc cốt lõi:** CSRF token của Spring Security, OAuth2 <code>state</code>, OIDC <code>nonce</code> và PKCE là những cơ chế khác nhau. Chúng có thể bổ sung cho nhau, nhưng không được coi chúng là một khóa bảo vệ chung rồi bỏ qua ranh giới sử dụng.

## 2. Mục tiêu bài học

Sau bài này, bạn có thể:

- Diễn giải CSRF đối với ứng dụng web dùng cookie-based authentication.
- Phân biệt <code>/oauth2/authorization/{registrationId}</code> tại Client với <code>/authorize</code> (Authorization Endpoint) tại Authorization Server/OP.
- Giải thích vai trò của <code>state</code> ở OAuth2 Authorization Code Flow và điều kiện ràng buộc callback.
- Hiểu <code>nonce</code>, PKCE, <code>iss</code> và kiểm tra ID Token bổ sung cho <code>state</code> thế nào.
- Cấu hình CSRF cho các endpoint nghiệp vụ trong **Spring Security Servlet** và **Reactive WebFlux**.
- Giải quyết callback <code>response_mode=form_post</code> khi framework/provider hỗ trợ, bằng ngoại lệ **hẹp** mà không tắt CSRF toàn cục.
- Thực hiện logout qua POST có CSRF protection; hiểu các khác biệt của OIDC RP-Initiated, Front-Channel và Back-Channel Logout.
- Xử lý <code>SameSite</code>, <code>Secure</code>, proxy, session affinity, nhiều tabs và nhiều providers.
- Đọc lỗi HTTP 403 đúng nguyên nhân; không nhầm CSRF failure với thiếu role/scope hoặc lỗi bearer token.
- Tạo kiểm thử CSRF/logout/callback và thiết kế phòng vệ phù hợp khi scale-out.

## 3. Mô hình đe dọa CSRF

### 3.1. Cross-Site Request Forgery là gì?

**CSRF** xảy ra khi attacker khiến browser của một user đã có quan hệ xác thực với ứng dụng gửi request đến ứng dụng đó, trong khi request **không phản ánh ý định hợp lệ của user**.

Browser có thể tự gửi credential gắn với destination, nhất là:

- Session cookie.
- HTTP authentication cache trong một số cơ chế.
- Client certificate tự động được chọn theo cấu hình browser/mTLS.
- Những credential khác được browser tự đính kèm mà JavaScript từ website lạ không cần đọc.

Ví dụ:

~~~mermaid
sequenceDiagram
    autonumber
    actor User
    participant Browser
    participant Evil as Trang attacker.example
    participant Portal as portal.example.org

    User->>Browser: Đăng nhập Portal bằng OIDC
    Portal-->>Browser: Session cookie
    User->>Browser: Mở attacker.example
    Evil-->>Browser: HTML form tự submit sang Portal
    Browser->>Portal: POST /account/change-email kèm cookie nếu browser cho phép
    Note over Portal: Nếu chỉ tin cookie và không kiểm tra CSRF, request có thể thành công
    Portal-->>Browser: Response
~~~

Attacker **không cần biết mật khẩu hoặc session cookie value** để thử CSRF; họ cần một cách khiến browser gửi credential mà browser vốn đã giữ.

### 3.2. Same-Origin Policy không tự ngăn CSRF

Same-Origin Policy chủ yếu hạn chế khả năng script thuộc origin khác **đọc** nội dung response hoặc tương tác với DOM không được phép. Nó không chặn mọi request cross-origin: HTML form, navigation và một số kiểu fetch vẫn có thể tạo request theo những điều kiện trình duyệt.

**CORS cũng không tự thay thế CSRF protection.** CORS kiểm soát việc script được đọc response và một số loại cross-origin requests. Một form HTML cross-site có thể tạo POST ngay cả khi response không được cho phép đọc.

### 3.3. Điều kiện làm CSRF có tác động

Một yêu cầu giả mạo nguy hiểm khi kết hợp:

1. Browser tự gửi credential hữu hiệu đến server đích.
2. Server dùng credential đó để xác thực request.
3. Request có tác dụng thay đổi trạng thái hoặc thực hiện hành động nhạy cảm.
4. Server không có một bằng chứng đáng tin rằng request được tạo từ luồng hợp lệ của user.

Không phải mọi GET cross-site đều là CSRF có tác dụng. Nhưng nếu server dùng **GET để thay đổi dữ liệu**, một link/ảnh/redirect có thể trở thành đường tấn công.

### 3.4. Phân biệt CSRF với XSS

CSRF không nhất thiết cho attacker chạy JavaScript trong origin của Portal. XSS, nếu tồn tại, có thể cho attacker đọc CSRF token hoặc phát request có cùng quyền với trang, khiến phòng vệ CSRF khó phát huy. Do đó CSRF token **không thay thế** output encoding, CSP, input validation và các biện pháp phòng XSS.

## 4. Bốn ranh giới bảo vệ trong một OIDC Login

Xét hệ thống:

~~~text
Browser
  |
  v
Spring Security Portal (OAuth2/OIDC Client)
  |
  | authorization request, code exchange, logout
  v
OpenID Provider / Authorization Server
  |
  | access token
  v
Resource Server / Business API
~~~

Cần phân biệt các endpoint:

| Endpoint | Chủ thể sở hữu | Request thường gặp | Cơ chế bảo vệ trọng tâm |
|---|---|---|---|
| <code>/oauth2/authorization/company</code> | **Client** Spring Security | Browser GET bắt đầu login | Registration allowlist, server-generated authorization request, state/correlation |
| <code>/authorize</code> của OP | **Authorization Server** | Browser GET, tương tác login/consent | OP session/login CSRF, redirect URI, PKCE, policy authorization |
| <code>/login/oauth2/code/company</code> | **Client** Spring Security | Browser GET callback code/state | Kiểm tra state gắn với authorization request, PKCE, issuer, ID Token validation |
| <code>/login/oauth2/code/company</code> với form_post | **Client** Spring Security | Browser cross-site POST callback | OIDC/OAuth state + narrow CSRF handling + session correlation |
| <code>/logout</code> | **Client** Spring Security | Browser POST | Spring Security CSRF token, logout handlers |
| <code>end_session_endpoint</code> | **OP** | Browser redirect/POST theo profile | OIDC RP-Initiated Logout, ID Token hint/OP policy/state |
| <code>/logout/connect/back-channel/company</code> | **Client** Spring Security | OP server-to-server POST | Signed Logout Token validation, issuer/audience/events/sid/sub |
| <code>/api/orders</code> | **Client/API** | Cookie/session-authenticated POST | CSRF token hoặc cơ chế chống CSRF tương đương |

Một sai lầm hay gặp là gọi chung mọi endpoint trên là “OAuth endpoint” rồi tắt CSRF bằng:

~~~java
.csrf(csrf -> csrf.ignoringRequestMatchers("/oauth2/**", "/login/**", "/logout/**"))
~~~

Ngoại lệ rộng như vậy có thể bỏ bảo vệ những route thay đổi trạng thái do ứng dụng tự tạo trong cùng các prefix. Thay vào đó, cần hiểu **đúng method, đường dẫn và giao thức xác thực** của từng endpoint.

## 5. Authorization initiation tại Spring Security Client

### 5.1. URL chọn ClientRegistration

Với Servlet hoặc Reactive WebFlux, Spring Security OAuth2 Login thường cung cấp authorization initiation URL:

~~~text
GET /oauth2/authorization/company
~~~

Một cấu hình minh họa:

~~~yaml
spring:
  security:
    oauth2:
      client:
        registration:
          company:
            provider: company
            client-id: portal-web
            client-secret: ${COMPANY_CLIENT_SECRET}
            authorization-grant-type: authorization_code
            client-authentication-method: client_secret_basic
            redirect-uri: "{baseUrl}/login/oauth2/code/{registrationId}"
            scope:
              - openid
              - profile
        provider:
          company:
            issuer-uri: https://idp.example.org/realms/company
~~~

Spring Security:

1. Tìm <code>ClientRegistration</code> bằng ID <code>company</code>.
2. Tạo <code>OAuth2AuthorizationRequest</code>.
3. Tạo <code>state</code> ngẫu nhiên, cùng nonce/PKCE khi áp dụng.
4. Lưu request/correlation trong repository phù hợp với session.
5. Redirect browser đến Authorization Endpoint của OP.

Đây là **authorization initiation endpoint của Client**, không phải Token Endpoint và cũng không phải Authorization Endpoint mà OP triển khai.

### 5.2. Có cần CSRF token cho GET initiation không?

Theo thiết kế mặc định, <code>GET /oauth2/authorization/company</code> là một navigation khởi tạo authorization flow. Spring Security CSRF filter thường không yêu cầu synchronizer CSRF token cho các HTTP methods được coi là an toàn như GET.

Tuy vậy, GET initiation có thể tạo authorization-request state trong session. Website bên ngoài có thể thử **khiến browser điều hướng** đến URL này. Do đó login initiation cần phòng vệ phù hợp:

- Chỉ chấp nhận registration IDs đã được cấu hình.
- Tạo authorization request/state ở server, không lấy state từ caller.
- Ràng buộc callback với browser session và request gốc.
- Xác minh issuer/client/redirect URI.
- Đừng coi một URL initiation do attacker đưa là bằng chứng user đã chủ động đồng ý kết nối tài khoản hoặc thay active identity.

**Không có nghĩa mỗi link GET initiation bắt buộc được bảo vệ bằng CSRF token dạng form.** Nếu ứng dụng có hành động nhạy cảm “đổi account”, “link identity”, “cấp quyền mới”, nên thêm một bước POST có CSRF và xác nhận ý định **trước** khi redirect đến initiation URL chuẩn.

### 5.3. Login CSRF tại initiation khác business CSRF

Ví dụ một attacker cố đưa browser user vào một login flow mà cuối cùng ứng dụng tạo session dưới tài khoản attacker. Đây là dạng **login CSRF/session swapping**. Trong OAuth2, <code>state</code> được tạo trong Client session và kiểm tra tại callback là tuyến phòng vệ quan trọng.

Ngược lại, một POST sửa email ở Portal sau đăng nhập cần CSRF token của ứng dụng. **OAuth state không được gắn vào các POST nghiệp vụ như một CSRF token đa dụng**.

### 5.4. Không cho browser thay provider endpoint

Sai:

~~~text
GET /oauth2/authorization?issuer=https://unknown.example
~~~

nếu ứng dụng lấy issuer URL trực tiếp từ query parameter rồi tạo registration động. Attacker có thể hướng authorization đến OP không tin cậy hoặc gây SSRF/mix-up.

Đúng hơn là chọn:

~~~text
/oauth2/authorization/company
/oauth2/authorization/partner
~~~

trong allowlist của backend. Với nhiều providers, state phải ràng buộc authorization response với **đúng registration/issuer**.

## 6. CSRF tại Authorization Endpoint của OP

Authorization Endpoint thực sự là endpoint tại **Authorization Server/OpenID Provider**, ví dụ:

~~~text
https://idp.example.org/realms/company/protocol/openid-connect/auth
~~~

Ứng dụng Client bình thường **không quản lý** CSRF token ở login form của OP. OP chịu trách nhiệm bảo vệ:

- Login pages và credential submission.
- Consent approval/rejection.
- SSO session management.
- Authentication method selection và step-up/MFA.
- Các hành động thay đổi trạng thái diễn ra trong origin của OP.

### 6.1. Authorization Endpoint là điểm bảo mật của OP

Một request khái niệm:

~~~http
GET /authorize?response_type=code&client_id=portal-web&redirect_uri=https%3A%2F%2Fportal.example.org%2Flogin%2Foauth2%2Fcode%2Fcompany&scope=openid%20profile&state=RANDOM_STATE HTTP/1.1
Host: idp.example.org
~~~

OP cần kiểm tra Client registration, redirect URI được phép, response type, scope, user authentication và consent policy. Khi OP hiển thị form POST consent, OP phải bảo vệ form đó theo mô hình CSRF của **OP**.

### 6.2. Không nhầm OAuth state với CSRF token của OP

<code>state</code> thường là dữ liệu Client gửi đi và kỳ vọng nhận lại nguyên vẹn trong authorization response để correlate callback. Nó **không phải** synchronizer token của OP dùng bảo vệ form “Approve access”.

Nếu phát triển cả Authorization Server, cần một thiết kế CSRF riêng cho những endpoint state-changing của Authorization Server. Không trông chờ Spring Security OAuth2 Client configuration ở Portal sẽ tự bảo vệ consent form trên OP.

### 6.3. Redirect URI exact matching

Nếu OP cho phép redirect URI tùy ý hoặc matching quá rộng, authorization code có thể bị chuyển đến attacker. Với Authorization Code Flow, OP phải thực hiện validation redirect URI theo yêu cầu giao thức/security profile.

Không sử dụng wildcard callback bừa bãi:

~~~text
https://*.example.org/*
~~~

chỉ để thuận tiện khi triển khai nhiều environments. Đăng ký redirect URIs rõ ràng, dùng HTTPS và giữ đúng host/path.

### 6.4. PKCE bổ sung cho code binding

PKCE dùng:

~~~text
code_verifier         bí mật tạm thời Client giữ
code_challenge        dẫn xuất từ verifier, gửi đến OP
code_challenge_method S256
~~~

PKCE giảm rủi ro authorization code interception/injection; nó không tự bảo vệ một POST thay đổi email của Portal và không thay thế Client request correlation nếu flow cần <code>state</code>.

Theo OAuth2 security best practices, Authorization Code + PKCE là mô hình ưu tiên, đặc biệt với public clients; nhiều deployments cũng áp dụng PKCE cho confidential clients để tăng phòng vệ.

## 7. Callback OAuth2: state mới là tuyến phòng vệ correlation

Sau khi user xác thực, OP redirect:

~~~http
HTTP/1.1 302 Found
Location: https://portal.example.org/login/oauth2/code/company?code=AUTH_CODE&state=RANDOM_STATE
~~~

Đây thường là **GET callback**. Spring Security CSRF protection mặc định không yêu cầu CSRF form token cho GET, nhưng callback không vì thế mà “không được bảo vệ”.

Spring Security OAuth2 Login phải:

1. Tìm authorization request đã được lưu **trước khi redirect sang OP**.
2. Đối chiếu <code>state</code> trên callback với state đã lưu.
3. Kiểm tra request còn liên kết với session/browser/registration phù hợp.
4. Gửi authorization code đến Token Endpoint đúng OP, bằng PKCE verifier/client authentication đúng.
5. Với OIDC, xác minh ID Token, nonce nếu có, issuer, audience, chữ ký và các ràng buộc khác.
6. Chỉ khi đạt các bước trên mới tạo Authentication và phiên đăng nhập.

### 7.1. Vì sao không yêu cầu Spring CSRF token trên GET callback?

Một callback chuẩn từ OP chứa <code>code</code> và <code>state</code>, không chứa synchronizer token của portal. Kỳ vọng browser/OP mang token CSRF của form portal vào authorization callback là không đúng luồng.

Vì callback là GET, Spring Security CSRF filter thông thường không cản nó. **Cơ chế chống CSRF trực tiếp trong OAuth2 login callback là state/correlation validation**.

Điều này không cho phép ứng dụng bỏ qua state. Nếu xử lý callback tự viết như:

~~~java
@GetMapping("/oauth2/callback")
void callback(@RequestParam String code) {
    // Đổi code mà không kiểm tra state/session/registration!
}
~~~

thì ứng dụng đã loại bỏ bảo vệ quan trọng và có thể bị login CSRF, code injection hoặc provider mix-up.

### 7.2. Sequence diagram

~~~mermaid
sequenceDiagram
    autonumber
    actor User
    participant B as Browser
    participant RP as Spring Security Client
    participant OP as OpenID Provider

    User->>B: Chọn login
    B->>RP: GET /oauth2/authorization/company
    RP->>RP: Tạo state=S1; lưu request trong session
    RP-->>B: Redirect OP kèm state=S1
    B->>OP: Authorization request S1
    OP->>User: Authentication/consent theo policy
    OP-->>B: 302 code=C1, state=S1
    B->>RP: GET /login/oauth2/code/company?code=C1&state=S1
    RP->>RP: Load request và kiểm tra S1
    RP->>OP: Exchange C1 (+ PKCE/client authentication)
    OP-->>RP: Token response
    RP->>RP: Validate ID Token khi OIDC
    RP-->>B: Session authenticated
~~~

Nếu callback gửi state <code>S2</code> không khớp <code>S1</code>:

~~~text
Callback S2
    → Authorization request correlation fails
    → Không đổi code như flow hợp lệ
    → Không tạo authenticated session
~~~

### 7.3. state phải có entropy và không thể đoán

<code>state</code> cần được tạo bằng cơ chế ngẫu nhiên an toàn, ràng buộc với authorization request/session và được kiểm tra nghiêm ngặt.

Không đặt:

~~~text
state=user-123
state=company
state=timestamp
~~~

theo cách dễ đoán hoặc không có binding. Nếu ứng dụng tùy biến state để chứa return URL/context, phải bảo vệ tính toàn vẹn và chống replay, không đưa một URL tùy ý vào state rồi redirect sau login mà không validation.

### 7.4. Authorization request repository

Trong Servlet:

~~~text
OAuth2AuthorizationRequestRepository<OAuth2AuthorizationRequest>
    ↳ HttpSessionOAuth2AuthorizationRequestRepository
~~~

Trong WebFlux:

~~~text
ServerAuthorizationRequestRepository<OAuth2AuthorizationRequest>
    ↳ WebSessionOAuth2ServerAuthorizationRequestRepository
~~~

Repository lưu request gốc để callback kiểm tra. Khi triển khai multi-instance, state/correlation phải truy cập được trên node nhận callback. Nếu cookie/session thất lạc, callback phải thất bại an toàn.

Không giải quyết lỗi <code>authorization_request_not_found</code> hoặc <code>invalid_state</code> bằng cách bỏ kiểm tra state.

## 8. OIDC nonce và ID Token validation không phải CSRF token

OIDC thêm <code>nonce</code> trong các flow phù hợp để ràng buộc ID Token với authentication request.

| Cơ chế | Được trao đổi ở đâu? | Mục đích |
|---|---|---|
| Spring CSRF token | Form/header từ trang ứng dụng đến ứng dụng | Chứng minh request thay đổi trạng thái xuất phát từ ngữ cảnh hợp lệ của browser/session |
| OAuth2 <code>state</code> | Authorization request và authorization callback | Ràng buộc response với request gốc, chống login CSRF |
| OIDC <code>nonce</code> | Authorization request và ID Token | Chống ID Token replay/substitution trong flow áp dụng |
| PKCE verifier/challenge | Authorization + Token Endpoints | Ràng buộc authorization code với Client khởi tạo flow |
| OIDC <code>iss</code>/<code>aud</code> | ID Token / authorization response theo profile | Chứng minh issuer và intended audience |

### 8.1. Một flow OIDC không thể “được bảo vệ” chỉ vì có nonce

Nếu callback chưa được correlate với request/session, một nonce được dùng sai hoặc không kiểm tra cũng không cứu được login CSRF. Spring Security phải sử dụng **đúng toàn bộ cơ chế của flow**.

### 8.2. ID Token không thay thế access token

Sau callback, ID Token xác thực End-User cho Client. Nó không thay thế access token dùng gọi Resource Server. Cần kiểm tra audience/scope/role riêng khi gọi downstream API.

Đừng gộp “có JWT hợp lệ” thành “request an toàn khỏi mọi CSRF”. Token format là một vấn đề khác với browser request-origin intent.

## 9. Callback sử dụng response_mode=form_post

OIDC/OAuth deployments có thể dùng **<code>response_mode=form_post</code>**, khi OP đưa authorization response về Client bằng auto-submitting HTML form:

~~~html
<form method="post"
      action="https://portal.example.org/login/oauth2/code/company">
    <input type="hidden" name="code" value="AUTH_CODE">
    <input type="hidden" name="state" value="STATE_VALUE">
</form>
<script>document.forms[0].submit();</script>
~~~

Browser gửi **cross-site POST** từ origin OP tới callback của RP.

### 9.1. Xung đột với CSRF filter thông thường

Spring Security CSRF mặc định thường yêu cầu token cho POST. OP **không biết CSRF token của RP** và không thể đơn giản thêm nó vào form như một trang cùng origin.

Kết quả có thể là:

~~~text
POST /login/oauth2/code/company
    → CSRF filter từ chối 403
    → OAuth2 Login callback filter chưa được xử lý
~~~

Tuy nhiên, **không phải mọi Spring Security version/cấu hình OAuth2 Login tự hỗ trợ form_post callback chỉ bằng thay CSRF matcher**. Cần xác nhận callback processing, form body extraction, response_mode support và OP registration cho phiên bản đang dùng.

### 9.2. Nguyên tắc ngoại lệ hẹp

Nếu stack/framework đã hỗ trợ form_post callback, có thể cần loại trừ **chỉ POST callback path** khỏi synchronizer CSRF token check, đồng thời vẫn bắt buộc:

- OAuth2 <code>state</code> validation.
- Correlation với authorization request lưu trong session.
- Registration/issuer binding.
- PKCE và OIDC nonce validation khi áp dụng.
- Kiểm tra ID Token/Token Endpoint đúng provider.
- Giới hạn method/path và không có business action trong endpoint này.

**Không dùng**:

~~~java
http.csrf(csrf -> csrf.disable());
~~~

chỉ để làm <code>form_post</code> callback chạy được.

### 9.3. Ví dụ Servlet ngoại lệ đúng path/method

Giả sử ứng dụng **đã** có integration xử lý callback POST đúng chuẩn:

~~~java
import org.springframework.security.web.util.matcher.AntPathRequestMatcher;

http.csrf(csrf -> csrf.ignoringRequestMatchers(
    new AntPathRequestMatcher(
        "/login/oauth2/code/*", "POST")));
~~~

Đây là minh họa Spring Security 6.x về request matcher; API <code>AntPathRequestMatcher</code> có thay đổi/deprecation ở các phiên bản mới. Dùng matcher được Spring Security version thực tế hỗ trợ.

**Không mặc định copy đoạn này vào production**:

1. Chỉ dùng khi callback POST là một feature được yêu cầu và framework đã xử lý response_mode=form_post an toàn.
2. Path/method phải khớp chính xác với callback registration.
3. Không mở rộng matcher sang <code>/**</code>, <code>/login/**</code> hay mọi POST.
4. Nếu có proxy/context path, kiểm tra servlet path/matcher semantics.
5. Đảm bảo <code>state</code> và tất cả OAuth2/OIDC validation vẫn bật.

Nếu callback là GET mặc định, **không cần thêm ngoại lệ POST** chỉ để “đề phòng”.

### 9.4. SameSite cookie có thể khiến callback không tìm được session

<code>SameSite=Lax</code> thường cho phép cookie ở **top-level cross-site GET navigation**. Nhưng với **cross-site POST** từ <code>form_post</code>, browser có thể không gửi cookie session theo chính sách SameSite.

Kết quả:

~~~text
CSRF filter đã cho callback POST đi qua
    ↓
Spring Security không tìm được authorization request
    ↓
state missing / authorization_request_not_found
~~~

Đây không còn là vấn đề CSRF synchronizer token; đó là **session/cookie correlation**.

Với các browser/flow yêu cầu cross-site POST cookie, có thể cần <code>SameSite=None; Secure</code> hoặc một thiết kế correlation khác tương thích browser/provider. Thay đổi SameSite tác động toàn bộ cookie-based session security nên phải đánh giá CSRF phòng vệ cho các route khác, HTTPS và domain/path.

**Đừng tắt state validation hoặc tự lấy state từ callback để tạo authorization request mới** khi cookie không đi kèm.

### 9.5. Một quyết định thiết kế thực tế

Nếu không có yêu cầu bắt buộc dùng <code>form_post</code>, Authorization Code Flow với **GET callback** mặc định thường đơn giản hơn cho browser session correlation. Khi phải dùng <code>form_post</code>, cần integration tests trên đúng Spring Security version và browser/cookie policy production.

## 10. Spring Security CSRF cho các POST nghiệp vụ sau login

Trước khi bàn logout, cần giữ đúng nền tảng:

~~~text
Cookie-authenticated browser:
    POST /orders
    PATCH /settings
    DELETE /files/{id}
    → CSRF protection cần được xem xét và thường được bật
~~~

### 10.1. Synchronizer token pattern

Spring Security CSRF dùng token được liên kết với một context tin cậy (thường HTTP session hoặc cookie repository), và yêu cầu client gửi token ở form parameter/header.

Attacker website khác không thể đơn giản biết token từ trang portal nếu không có XSS hoặc lỗ hổng cross-origin.

Ví dụ form:

~~~html
<form action="/account/change-email" method="post">
    <label for="email">Email mới</label>
    <input id="email" name="email" type="email" required>
    <input type="hidden" name="_csrf" value="CSRF_TOKEN_FROM_SERVER">
    <button type="submit">Lưu</button>
</form>
~~~

Trong template engine thực tế, CSRF value cần được tạo từ Spring Security (chẳng hạn Thymeleaf integration), không hardcode literal trên.

### 10.2. CSRF token không có nghĩa đã authorize nghiệp vụ

Một POST có CSRF token hợp lệ có thể vẫn bị từ chối do:

- Người dùng thiếu role.
- Không thuộc tenant/resource owner.
- Account đã bị vô hiệu hóa.
- Access token gửi downstream API sai audience/scope.

CSRF token chống yêu cầu giả mạo từ browser, **không cấp quyền kinh doanh**.

### 10.3. CSRF và stateless bearer API

Một API **thực sự stateless**, chỉ chấp nhận Bearer token trong HTTP <code>Authorization</code> header mà browser không tự thêm, có thể không cần synchronizer CSRF token theo threat model.

Nhưng nếu cùng API còn chấp nhận **session cookie**, basic auth của browser hoặc credential tự động được gửi, không thể tuyên bố “API là REST nên tắt CSRF được”.

Tiêu chí là **credential được browser tự gửi hay không**, không phải ứng dụng có tên REST, SPA hay WebFlux.

## 11. Cấu hình Servlet: mặc định giữ CSRF bật

Một cấu hình Spring Boot 3/Spring Security 6 cho OIDC Client:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-client'
}
~~~

~~~java
package example.security;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class PortalSecurityConfig {

    @Bean
    SecurityFilterChain portalChain(HttpSecurity http) throws Exception {

        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/", "/login", "/error", "/assets/**")
                    .permitAll()
                .anyRequest().authenticated())
            .oauth2Login(Customizer.withDefaults())
            .csrf(Customizer.withDefaults())
            .logout(Customizer.withDefaults());

        return http.build();
    }
}
~~~

Trong cấu hình:

- OAuth2 Login quản lý authorization initiation/callback.
- CSRF filter bảo vệ các request state-changing thuộc browser session theo defaults.
- Logout theo cấu hình chuẩn, thường thực hiện bằng **POST** khi CSRF protection đang bật.
- GET callback OAuth2 Login vẫn được xử lý với <code>state</code> mà không cần CSRF form token.

Không cần khai báo <code>.csrf(Customizer.withDefaults())</code> nếu default đã áp dụng; nó được viết ra để thể hiện chủ đích.

### 11.1. Biểu mẫu logout có CSRF token

Ví dụ Thymeleaf:

~~~html
<form th:action="@{/logout}" method="post">
    <button type="submit">Đăng xuất</button>
</form>
~~~

Với Spring Security và template integration đúng, hidden CSRF field có thể được thêm tự động. Trong frontend tự viết, cần gửi CSRF token thích hợp; không chỉ tạo link GET rồi kỳ vọng logout luôn an toàn.

### 11.2. Phân biệt link logout GET với POST logout

Khi CSRF protection bật, Spring Security có thể hiển thị trang xác nhận khi <code>GET /logout</code>; **POST /logout** mới thực hiện logout theo flow được cấu hình.

Nếu ứng dụng tự triển khai controller:

~~~java
@GetMapping("/logout")
public String logout() {
    invalidateSession();
    return "redirect:/";
}
~~~

thì GET đã có side effect. Website khác có thể ép browser điều hướng để logout user, gây **logout CSRF** và gián đoạn phiên.

Tránh tạo endpoint logout GET chỉ để tiết kiệm một form POST.

## 12. Logout CSRF có tác động gì?

Một attacker không cần lấy cắp dữ liệu để gây ảnh hưởng:

~~~html
<img src="https://portal.example.org/logout">
~~~

Nếu <code>GET /logout</code> thực sự invalidate session, browser đến từ website attacker có thể bị đăng xuất ngoài ý muốn (tùy cookie/SameSite và implementation).

Một số hệ quả:

- Gây denial of service mức phiên.
- Phá công việc chưa lưu.
- Là bước phụ trợ trong login CSRF/session swapping: ép user logout rồi hướng vào login flow do attacker kiểm soát một phần.
- Làm gián đoạn quy trình thanh toán/ủy quyền.
- Gây nhầm lẫn giữa nhiều tài khoản hoặc OP sessions.

**Logout không nên được coi là hành động vô hại** chỉ vì nó không thay đổi dữ liệu nghiệp vụ.

### 12.1. POST + CSRF là lựa chọn mặc định phù hợp cho browser

Browser form gửi:

~~~http
POST /logout HTTP/1.1
Host: portal.example.org
Content-Type: application/x-www-form-urlencoded
Cookie: JSESSIONID=SESSION_PLACEHOLDER

_csrf=CSRF_TOKEN_PLACEHOLDER
~~~

Spring Security CSRF filter kiểm tra token theo repository/handler đã cấu hình; sau đó logout filter mới thực hiện các logout handlers.

### 12.2. Local logout xử lý những gì?

Thường gồm:

- Xóa <code>Authentication</code> khỏi SecurityContext.
- Invalidate HTTP session khi cấu hình mặc định yêu cầu.
- Xóa SecurityContext được lưu trong security context repository.
- Thực hiện logout handlers khác theo cấu hình.

Nhưng **không tự bảo đảm**:

- OpenID Provider SSO session đã kết thúc.
- Refresh token đã bị revoke tại Token Endpoint.
- JWT access token đã cấp không còn được Resource Server chấp nhận.
- Authorized client trong persistent service đã bị xóa.

Các tác vụ này có chính sách và endpoint riêng.

## 13. OIDC RP-Initiated Logout: CSRF ở bước nào?

**RP-Initiated Logout** xảy ra khi Client yêu cầu OP kết thúc SSO session, thường sau user logout tại Portal.

Luồng ví dụ:

~~~mermaid
sequenceDiagram
    autonumber
    actor U as Người dùng
    participant B as Browser
    participant RP as Spring Security Portal
    participant OP as OpenID Provider
    U->>B: Click Đăng xuất
    B->>RP: POST /logout + CSRF token
    RP->>RP: CSRF check; local logout handlers
    RP-->>B: Redirect tới OP end_session_endpoint
    B->>OP: OIDC RP-Initiated Logout request
    OP->>OP: Kiểm tra session/id_token_hint/client policy
    OP-->>B: Redirect về post_logout_redirect_uri nếu hợp lệ
    B->>RP: GET /login?logout
~~~

CSRF protection của **Portal** áp dụng ở POST local logout. OP quản lý bảo mật cho endpoint logout của **OP** theo OIDC RP-Initiated Logout và SSO session policy.

### 13.1. Servlet logout success handler

Ví dụ khi provider có <code>end_session_endpoint</code>:

~~~java
package example.security;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.oauth2.client.oidc.web.logout
    .OidcClientInitiatedLogoutSuccessHandler;
import org.springframework.security.oauth2.client.registration
    .ClientRegistrationRepository;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class OidcRpInitiatedLogoutConfig {

    @Bean
    SecurityFilterChain securityFilterChain(
            HttpSecurity http,
            ClientRegistrationRepository registrations) throws Exception {

        var successHandler =
            new OidcClientInitiatedLogoutSuccessHandler(registrations);
        successHandler.setPostLogoutRedirectUri(
            "{baseUrl}/login?logout");

        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/login", "/error").permitAll()
                .anyRequest().authenticated())
            .oauth2Login(Customizer.withDefaults())
            .csrf(Customizer.withDefaults())
            .logout(logout -> logout
                .logoutSuccessHandler(successHandler));

        return http.build();
    }
}
~~~

**Đây là phương án SecurityFilterChain thay thế cho mục 11**, không đồng thời khai báo hai chain cùng matcher.

Giải thích:

1. User kích hoạt local logout theo method và CSRF policy của Portal.
2. Spring Security logout success handler hướng browser tới OP logout endpoint theo ClientRegistration/OIDC metadata.
3. OP kiểm tra thông tin như <code>id_token_hint</code> và post-logout redirect theo capability/registration.
4. Portal không tự gửi session cookie của người dùng cho OP.

Nếu OP không hỗ trợ RP-Initiated Logout, cần fallback local logout phù hợp; không tự xây endpoint logout OP bằng một URL từ browser chưa tin cậy.

### 13.2. post_logout_redirect_uri

OP có thể yêu cầu <code>post_logout_redirect_uri</code> được đăng ký trước. Không truyền giá trị <code>returnTo=https://attacker.example</code> trực tiếp sang OP hoặc redirect sau logout mà không allowlist/validation.

### 13.3. Khi logout OP qua GET

OIDC RP-Initiated Logout có thể sử dụng browser navigation tới OP endpoint. Đây là **một phần của giao thức logout tại OP**, không phải lý do để mở <code>GET /logout</code> local làm side effect mà không có bảo vệ CSRF/ý định user.

OP chịu trách nhiệm chính sách của OP logout endpoint, bao gồm confirmation hoặc session-binding khi phù hợp.

## 14. OIDC Front-Channel Logout và CSRF

Front-Channel Logout sử dụng browser làm kênh để OP thông báo cho RP. Nó có thể liên quan tới iframe hoặc navigation:

~~~text
OP → browser → RP front-channel logout URL
~~~

Đặc điểm:

- Browser có thể gửi cookie của RP tùy SameSite/third-party cookie policy.
- OP có thể truyền <code>iss</code>, <code>sid</code> theo profile và registration.
- Bên RP cần xác định thông điệp hợp lệ theo thiết kế, không coi một GET tùy ý do attacker tạo là bằng chứng OP logout.
- Browser privacy restrictions có thể chặn third-party cookies, khiến Front-Channel Logout không tìm được session.

### 14.1. Không biến endpoint front-channel thành public force-logout

Nếu bất cứ ai có thể gửi:

~~~text
GET /frontchannel-logout?sub=user-123
~~~

và server lập tức xóa mọi session của user-123 mà không có correlation/validation, attacker có thể gây logout hàng loạt.

Đây không phải thiết kế an toàn. Cần hiểu đúng OIDC Front-Channel Logout profile, <code>iss</code>/<code>sid</code> correlation và giới hạn của browser channel. Không dùng <code>sub</code> được caller khai báo như bằng chứng duy nhất.

### 14.2. Front-Channel khác Back-Channel

| Thuộc tính | Front-Channel Logout | Back-Channel Logout |
|---|---|---|
| Kênh | Browser/user agent | Server-to-server POST |
| Browser cookie | Có thể tham gia, phụ thuộc policy | Không cần browser cookie |
| Thông điệp | Front-channel protocol params | **Signed Logout Token** |
| Rủi ro chính | Third-party cookie restrictions/iframe/forged navigation | JWT validation, session mapping, replay, endpoint availability |
| Spring Security integration | Phụ thuộc stack/version/provider | Có DSL OIDC Back-Channel Logout ở các version hỗ trợ |

Không áp dụng CSRF policy của một HTML form business vào Back-Channel Logout mà không hiểu JWT protocol; cũng không dùng signed JWT Back-Channel Logout handler để xử lý tùy ý mọi GET iframe.

## 15. OIDC Back-Channel Logout: server-to-server POST không có CSRF form token

Ở **Back-Channel Logout**, OpenID Provider gửi một request như:

~~~http
POST /logout/connect/back-channel/company HTTP/1.1
Host: portal.example.org
Content-Type: application/x-www-form-urlencoded

logout_token=SIGNED_LOGOUT_TOKEN_PLACEHOLDER
~~~

Không có session cookie của browser; OP không có CSRF token của local RP form.

Vì thế điểm bảo vệ chính không phải synchronizer CSRF token, mà là **Logout Token JWT validation**.

### 15.1. Logout Token cần được xác minh

Payload minh họa:

~~~json
{
  "iss": "https://idp.example.org/realms/company",
  "aud": "portal-web",
  "iat": 1794800000,
  "exp": 1794800120,
  "jti": "logout-event-01",
  "sid": "op-session-123",
  "sub": "user-456",
  "events": {
    "http://schemas.openid.net/event/backchannel-logout": {}
  }
}
~~~

Những thông tin cần kiểm tra theo OIDC Back-Channel Logout profile:

- Chữ ký của OP và thuật toán/key được tin cậy.
- <code>iss</code> đúng OP đã đăng ký.
- <code>aud</code> chứa Client ID tương ứng.
- <code>iat</code>, <code>exp</code> và clock skew theo profile.
- <code>events</code> chứa URI sự kiện logout chính xác.
- Có ít nhất một trong <code>sub</code> hoặc <code>sid</code>.
- <code>nonce</code> **không được xuất hiện**.
- <code>jti</code> và replay/idempotency policy khi triển khai.

Không dùng access token hoặc ID Token bình thường làm Logout Token chỉ vì cùng được OP ký.

### 15.2. Vì sao không bắt browser CSRF token cho Back-Channel POST?

Request do **OP server** gửi. OP không thể lấy CSRF token của browser session tại RP và không nên được cấp quyền truy cập cookie browser.

Vì vậy cần để **framework OIDC Back-Channel Logout handler** xử lý đúng protocol path, không áp dụng một blanket policy buộc mọi POST đều có form CSRF token.

Tuy nhiên, **bỏ qua synchronizer CSRF check không đồng nghĩa endpoint được phép bỏ JWT validation**. Nếu một endpoint back-channel chấp nhận <code>sub=user-123</code> chưa được ký/xác minh rồi xóa session, đó là một lỗ hổng có thể bị khai thác bằng request giả.

### 15.3. Bật DSL theo phiên bản hỗ trợ

Ví dụ Servlet Spring Security có tính năng:

~~~java
http
    .oauth2Login(Customizer.withDefaults())
    .oidcLogout(oidc -> oidc
        .backChannel(Customizer.withDefaults()));
~~~

Reactive WebFlux:

~~~java
http
    .oauth2Login(Customizer.withDefaults())
    .oidcLogout(oidc -> oidc
        .backChannel(Customizer.withDefaults()));
~~~

Mã DSL nhìn gần giống nhưng types là:

~~~text
Servlet:
    HttpSecurity + SecurityFilterChain

Reactive:
    ServerHttpSecurity + SecurityWebFilterChain
~~~

Tính năng OIDC Back-Channel Logout tích hợp bắt đầu có từ Spring Security 6.2; handler/configuration và default behavior thay đổi theo bản 6.2.x, 6.5 và 7.x. **Kiểm tra API thực của version** trước khi copy config, đặc biệt custom handler, internal logout URI và CSRF/session integration.

### 15.4. Không tắt CSRF toàn ứng dụng để phục vụ back-channel

Nếu cần cấu hình CSRF matcher/handler cho back-channel, chỉ điều chỉnh đường dẫn/method giao thức được framework xử lý. Đừng viết:

~~~java
.csrf(csrf -> csrf.ignoringRequestMatchers("/logout/**"))
~~~

vì prefix đó có thể chứa local browser logout hoặc business endpoint. Sự tách biệt **back-channel protocol endpoint** và **local /logout** phải được giữ rõ ràng.

### 15.5. Session registry và cluster

Back-channel request không mang browser cookie nên RP cần mapping:

~~~text
(issuer, clientId, sid/sub) → local session ID(s)
~~~

Spring Security có <code>OidcSessionRegistry</code> trong Servlet và <code>ReactiveOidcSessionRegistry</code> trong WebFlux theo version hỗ trợ.

Nếu ứng dụng có hai instance A/B nhưng registry chỉ in-memory:

~~~text
Login ở A → A lưu OP sid ↔ local session S1
Logout Token đến B → B không biết S1
~~~

Ngay cả khi Spring Session Redis chia sẻ HTTP sessions, **OIDC session registry có thể vẫn cần storage phân tán riêng**. Đây là vấn đề availability/consistency, không phải thiếu CSRF token.

## 16. Ba cơ chế “state”, “CSRF token”, “Logout Token” nhìn cùng một luồng

~~~mermaid
flowchart TD
    START["Browser bắt đầu OIDC Login"] --> INIT["GET /oauth2/authorization/company"]
    INIT --> STATE["Client tạo state, nonce/PKCE"]
    STATE --> OP["OP Authorization Endpoint"]
    OP --> CB["GET callback code + state"]
    CB --> VERIFY{"state + token validations hợp lệ?"}
    VERIFY -->|Không| FAIL["Từ chối login"]
    VERIFY -->|Có| AUTH["Tạo authenticated browser session"]
    AUTH --> FORM["Browser POST /settings"]
    FORM --> CSRF{"Spring CSRF token hợp lệ?"}
    CSRF -->|Không| FORBID["403 CSRF"]
    CSRF -->|Có| BIZ["Kiểm tra role/tenant, thực thi nghiệp vụ"]
    AUTH --> LOGOUT["Browser POST /logout"]
    LOGOUT --> LOGCSRF{"CSRF token hợp lệ?"}
    LOGCSRF -->|Không| FORBID
    LOGCSRF -->|Có| LOCAL["Local session logout"]
    AUTH --> BACK["OP POST back-channel Logout Token"]
    BACK --> JWT{"Signed Logout Token hợp lệ?"}
    JWT -->|Không| BAD["Từ chối request"]
    JWT -->|Có| LOCAL
~~~

Với callback <code>form_post</code>, đường <code>CB</code> là POST nhưng vẫn cần **state/nonce/PKCE/issuer validation**; CSRF matcher phải được điều chỉnh **riêng theo protocol** nếu framework/cookie configuration hỗ trợ.

## 17. Spring Security Servlet: cấu hình session, CSRF repository và token handler

### 17.1. SessionCsrfTokenRepository

Spring Security có thể lưu CSRF token trong HTTP session. Điểm cần hiểu:

~~~text
HttpSession
   ├── SecurityContext
   ├── OAuth2AuthorizationRequest (state/correlation)
   └── CSRF token (cho browser POST)
~~~

Đây là ba dữ liệu khác nhau, dù cùng nằm trong session.

Với browser rendered forms, cách sử dụng CSRF token có thể được template engine/Spring MVC tích hợp tự động.

### 17.2. CSRF token trong SPA

Với SPA cùng backend BFF, một pattern có thể dùng cookie CSRF token và gửi lại qua header. Spring Security cung cấp <code>CookieCsrfTokenRepository</code>:

~~~java
import org.springframework.security.web.csrf.CookieCsrfTokenRepository;

http.csrf(csrf -> csrf
    .csrfTokenRepository(
        CookieCsrfTokenRepository.withHttpOnlyFalse()));
~~~

**Không copy đoạn này mặc định cho mọi ứng dụng.** Lý do:

- <code>withHttpOnlyFalse()</code> cho JavaScript đọc cookie CSRF token; phù hợp một số SPA patterns nhưng tăng khả năng token bị script trong origin đọc.
- Cookie CSRF token **khác session cookie**; session cookie nên giữ <code>HttpOnly</code> khi có thể.
- Spring Security có deferred CSRF tokens, XOR/BREACH token handling và các ví dụ SPA CSRF integration phụ thuộc version.
- Một SPA cần cách lấy token mới sau login/logout/session rotation và gửi đúng header, không dùng stale token.

Nếu dùng SPA, tham khảo giải pháp CSRF SPA của đúng Spring Security version thay vì chỉ thêm cookie repository rồi kỳ vọng mọi request hoạt động.

### 17.3. Không coi header tùy ý là đủ

Một request:

~~~http
POST /account/change-email HTTP/1.1
X-CSRF-TOKEN: attacker-supplied-value
~~~

chỉ an toàn nếu giá trị được **server so sánh với token hợp lệ** trong repository/handler. Việc có header tên <code>X-CSRF-TOKEN</code> không tự chứng minh request hợp lệ.

## 18. Reactive WebFlux: CSRF và OIDC flow

Reactive stack sử dụng:

| Servlet | WebFlux |
|---|---|
| <code>HttpSecurity</code> | <code>ServerHttpSecurity</code> |
| <code>SecurityFilterChain</code> | <code>SecurityWebFilterChain</code> |
| <code>HttpSession</code> | <code>WebSession</code> |
| <code>HttpSessionOAuth2AuthorizationRequestRepository</code> | <code>WebSessionOAuth2ServerAuthorizationRequestRepository</code> |
| <code>CsrfTokenRepository</code> | <code>ServerCsrfTokenRepository</code> |
| <code>CsrfFilter</code> | <code>CsrfWebFilter</code> |
| <code>HttpServletRequest</code> | <code>ServerWebExchange</code> |
| <code>SecurityContextHolder</code> | <code>ReactiveSecurityContextHolder</code> |

### 18.1. Dependencies

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-client'
}
~~~

Không vô tình thêm <code>spring-boot-starter-web</code> nếu mục tiêu là Reactive WebFlux; khi cả MVC/WebFlux cùng có mặt, Spring Boot thường ưu tiên Servlet MVC.

### 18.2. SecurityWebFilterChain

~~~java
package example.security;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.web.server.SecurityWebFilterChain;

@Configuration
@EnableWebFluxSecurity
public class WebFluxSecurityConfig {

    @Bean
    SecurityWebFilterChain securityWebFilterChain(
            ServerHttpSecurity http) {

        return http
            .authorizeExchange(exchanges -> exchanges
                .pathMatchers("/", "/login", "/error")
                    .permitAll()
                .anyExchange().authenticated())
            .oauth2Login(Customizer.withDefaults())
            .csrf(Customizer.withDefaults())
            .logout(Customizer.withDefaults())
            .build();
    }
}
~~~

Nguyên tắc tương tự Servlet:

- OAuth2 callback GET dùng state/correlation.
- Browser POST nghiệp vụ và local logout được bảo vệ bằng CSRF.
- Back-channel logout cần handler OIDC chuyên biệt theo version.
- Reactive session/WebFilter không được trộn với Servlet API.

### 18.3. WebSessionServerCsrfTokenRepository

Trong WebFlux, có <code>WebSessionServerCsrfTokenRepository</code> dùng WebSession:

~~~java
import org.springframework.security.web.server.csrf
    .WebSessionServerCsrfTokenRepository;

http.csrf(csrf -> csrf
    .csrfTokenRepository(
        new WebSessionServerCsrfTokenRepository()));
~~~

Đây là cấu hình ví dụ. Trong một dự án thực tế, có thể đã có repository mặc định tương đương; không cần khai báo bean/handler mới không cần thiết. Cách expose CSRF token cho reactive view/SPA phụ thuộc Spring Security version và view technology.

### 18.4. Reactive cookie CSRF repository

Spring Security WebFlux cũng có:

~~~java
import org.springframework.security.web.server.csrf
    .CookieServerCsrfTokenRepository;

http.csrf(csrf -> csrf
    .csrfTokenRepository(
        CookieServerCsrfTokenRepository.withHttpOnlyFalse()));
~~~

Những lưu ý đối với SPA và readable CSRF cookie ở mục 17.2 vẫn áp dụng. **Đừng dùng cookie repository chỉ để tránh quản lý WebSession cho OIDC Login**, vì authorization request state và login security context vẫn cần storage/correlation phù hợp.

### 18.5. Không block() và không tự subscribe()

Nếu viết custom reactive authorization request repository hoặc CSRF token handler, không gọi:

~~~java
exchange.getSession().block();
~~~

trong WebFlux request pipeline. Dùng <code>Mono.flatMap</code> hoặc reactive interfaces. Một callback/csrf handler blocking Netty event-loop có thể gây tải cao và làm mất ổn định login.

## 19. Khi nhiều SecurityFilterChains cùng tồn tại

Một ứng dụng có thể vừa phục vụ:

- Browser OIDC Login: dùng cookie/session/CSRF.
- API chỉ nhận Bearer access token: stateless và có thể không cần CSRF token nếu browser không tự gửi credential.

### 19.1. Servlet: chain API và chain browser

Ví dụ:

~~~java
package example.security;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.annotation.Order;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SplitSecurityChains {

    @Bean
    @Order(1)
    SecurityFilterChain apiChain(HttpSecurity http)
            throws Exception {

        http
            .securityMatcher("/api/**")
            .authorizeHttpRequests(auth -> auth
                .anyRequest().authenticated())
            .oauth2ResourceServer(oauth2 ->
                oauth2.jwt(Customizer.withDefaults()))
            .csrf(csrf -> csrf.disable());

        return http.build();
    }

    @Bean
    @Order(2)
    SecurityFilterChain browserChain(HttpSecurity http)
            throws Exception {

        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/", "/login", "/error").permitAll()
                .anyRequest().authenticated())
            .oauth2Login(Customizer.withDefaults())
            .csrf(Customizer.withDefaults())
            .logout(Customizer.withDefaults());

        return http.build();
    }
}
~~~

Nếu dùng JWT Resource Server ở API chain, cần dependency <code>spring-boot-starter-oauth2-resource-server</code> và issuer/audience validation phù hợp.

**Chỉ tắt CSRF cho API chain khi threat model xác nhận API thực sự chỉ chấp nhận non-automatic bearer credentials.** Nếu <code>/api/**</code> vẫn dùng session cookie, mẫu trên phải được điều chỉnh.

### 19.2. securityMatcher khác authorizeHttpRequests

- <code>securityMatcher("/api/**")</code>: chọn **chain nào xử lý**.
- <code>authorizeHttpRequests(...)</code>: xác định **quyền trong chain đã chọn**.

Nếu API chain ở <code>@Order(1)</code> match <code>/**</code>, nó có thể nuốt:

~~~text
/oauth2/authorization/company
/login/oauth2/code/company
/logout
/logout/connect/back-channel/company
~~~

Khi đó login/callback/logout filter của browser chain không chạy, và người triển khai có thể nhầm 401/403 là CSRF failure dù nguyên nhân là **chain selection**.

### 19.3. WebFlux cũng có nguyên tắc tương tự

Với Reactive, dùng nhiều <code>SecurityWebFilterChain</code> và <code>securityMatcher(...)</code> tương ứng. API chain không được match những browser/OIDC protocol routes ngoài chủ đích.

Không dùng Servlet <code>AntPathRequestMatcher</code> bên trong WebFlux exchange matcher; chọn API reactive theo Spring Security version.

## 20. SameSite, Secure, HttpOnly và browser cookie policies

CSRF protection hoạt động cùng cookie/session policies.

### 20.1. SameSite=Lax

Với <code>SameSite=Lax</code>:

- Cookie thường có thể được gửi khi browser top-level navigate bằng GET từ OP về RP.
- Cookie thường **không** được gửi cho cross-site POST, ví dụ OIDC <code>form_post</code> callback.
- Một số browser có behavior đặc thù với cookie mới tạo/unspecified SameSite; không dựa vào behavior không đồng nhất làm security contract.

### 20.2. SameSite=Strict

<code>SameSite=Strict</code> có thể gây lỗi OIDC callback vì cross-site navigation từ OP về RP không mang session cookie. Không chọn Strict chỉ vì “bảo mật nhất” mà bỏ qua luồng đăng nhập thực tế.

### 20.3. SameSite=None

<code>SameSite=None; Secure</code> cho phép cookie được gửi trong nhiều ngữ cảnh cross-site hơn, cần cho một số flow/embedding. Nhưng nó cũng làm browser gửi cookie ở nhiều request cross-site, khiến **CSRF token và Origin/Referer policy** càng cần được triển khai đúng.

### 20.4. HttpOnly

<code>HttpOnly</code> giảm khả năng JavaScript đọc session cookie. Nó **không** ngăn browser tự gửi cookie trong request cross-site, nên không thay thế CSRF protection.

### 20.5. Secure

<code>Secure</code> yêu cầu browser chỉ gửi cookie qua HTTPS, giảm nguy cơ lộ cookie qua HTTP. Nó **không** chống CSRF nếu request HTTPS cross-site vẫn gửi cookie hợp lệ.

### 20.6. Domain và Path

Cookie domain/path quyết định cookie được gửi tới những host/routes nào. Không dùng domain quá rộng như <code>.example.org</code> khi các subdomains không có cùng mức tin cậy; sibling subdomain bị xâm phạm có thể ảnh hưởng cookie/session policy.

### 20.7. Cấu hình Servlet minh họa

~~~yaml
server:
  servlet:
    session:
      cookie:
        http-only: true
        secure: true
        same-site: lax
~~~

Đây là một baseline thường phù hợp **GET callback** trên HTTPS. Nếu dùng <code>form_post</code>, cần thiết kế và kiểm thử lại SameSite/correlation; không tự đổi sang None mà không đánh giá các routes còn lại.

Spring Session có thể dùng tên cookie <code>SESSION</code> khác <code>JSESSIONID</code>; tên cookie không ảnh hưởng mục đích của CSRF token, nhưng liên quan callback/session/logout handlers.

## 21. Reverse proxy, redirect URI và CSRF login failures

Ứng dụng đằng sau load balancer:

~~~text
Browser → https://portal.example.org
Proxy   → http://app:8080
~~~

Nếu Spring Boot không biết public scheme/host, authorization request có thể tạo:

~~~text
redirect_uri=http://app:8080/login/oauth2/code/company
~~~

OP từ chối do redirect URI mismatch. User có thể thấy “OAuth2 Login failed” và nhầm là CSRF token issue.

### 21.1. Chỉ tin forwarded headers từ proxy đáng tin

Có thể cấu hình xử lý <code>Forwarded</code>/<code>X-Forwarded-*</code> theo Spring Boot/version, nhưng chỉ khi ingress/proxy kiểm soát và loại bỏ headers do client không tin cậy tự gửi.

Nếu tin attacker-controlled <code>X-Forwarded-Host</code>, ứng dụng có thể xây redirect URI tới attacker domain, ảnh hưởng OAuth security.

### 21.2. Cùng domain và cookie policy

Kiểm tra:

- <code>redirect_uri</code> đúng public HTTPS URL.
- Session cookie Domain/Path đúng callback route.
- Browser có gửi session cookie tại callback không?
- CSRF cookie có đúng domain và path của các POST nghiệp vụ không?
- Multiple app instances có chung session store hoặc session affinity?

Không nhầm <code>redirect_uri_mismatch</code> với CSRF 403 từ Spring Security.

## 22. Multi-instance: state và CSRF token nằm ở đâu?

Trong cluster:

~~~text
Browser
   ↓
Load Balancer
   ├── Instance A
   └── Instance B
         ↓
    Shared session store
~~~

Authorization initiation trên A có thể lưu state/correlation vào A-local <code>HttpSession</code>. Callback đến B sẽ không tìm thấy request gốc nếu session không được chia sẻ.

### 22.1. Spring Session Redis

Spring Session có thể chia sẻ HTTP session/WebSession giữa nodes. Tùy repository:

~~~text
Session S123
    ├── SecurityContext
    ├── AuthorizationRequest(state=S1)
    └── CSRF token (nếu Session CSRF repository)
~~~

B nhận cookie của S123 rồi đọc shared session, có thể xử lý callback và POST CSRF hợp lệ theo đúng state/repository.

**Nhưng Spring Session không tự đồng bộ mọi in-memory store khác**, ví dụ:

- <code>InMemoryOAuth2AuthorizedClientService</code>.
- Custom in-memory saved requests.
- OIDC Back-Channel Logout registry in-memory.
- Local deduplication/lock caches.

### 22.2. Không có lý do tắt state/CSRF vì cluster

Nếu node B báo <code>invalid_state</code>, nguyên nhân có thể là session/cookie/storage; **bỏ state validation tạo login CSRF risk**.

Nếu node B báo CSRF token mismatch cho form POST, nguyên nhân có thể là session store/token repository/SPA token stale; **tắt CSRF toàn ứng dụng tạo business CSRF risk**.

### 22.3. Multiple tabs

Trong cùng browser session:

~~~text
Tab 1 bắt đầu OIDC login Company: state=S1
Tab 2 bắt đầu OIDC login Partner: state=S2
Tab 1 callback state=S1
~~~

Nếu repository tùy biến chỉ lưu một authorization request và Tab 2 ghi đè Tab 1, callback S1 có thể thất bại. Không coi đây là lý do để chấp nhận mọi state.

Thiết kế repository hỗ trợ nhiều concurrent requests hoặc xử lý UX tránh các login flows đồng thời. CSRF token nghiệp vụ của session không được dùng thay state cho từng OAuth2 flow.

## 23. Login CSRF khi “đổi tài khoản” hoặc account linking

Một ứng dụng hỗ trợ nhiều providers thường có:

~~~text
/oauth2/authorization/company
/oauth2/authorization/partner
~~~

Nếu user đã đăng nhập và chọn “Liên kết tài khoản Partner”, ứng dụng đang thực hiện một **hành động nhạy cảm**: gắn identity mới vào internal account hiện tại.

### 23.1. Authorization initiation GET chưa phải linking consent

Một link GET tới OP chỉ bắt đầu login. Nó không tự chứng minh user đã đồng ý gắn account.

Đúng hơn:

1. User đã authenticated ở internal account A.
2. User gửi **POST /account/link/provider** có CSRF.
3. Backend kiểm tra provider allowlist, xác nhận intent, yêu cầu step-up khi cần.
4. Backend tạo linking transaction được ràng buộc với session và state.
5. Browser bắt đầu OAuth2/OIDC authorization tới provider B.
6. Callback được validate state, issuer, subject và policy.
7. Backend chỉ liên kết khi identity B chưa thuộc account khác và có authorization rõ ràng.

Không tự gộp account chỉ vì email giống nhau giữa hai providers.

### 23.2. Đổi tài khoản có thể làm session swapping

Nếu attacker ép browser đã đăng nhập thành account attacker, user có thể vô tình nhập dữ liệu nhạy cảm vào session không thuộc mình. CSRF của login flow/state validation và UI confirmation là hai lớp giảm thiểu.

Một POST đổi active account phải được bảo vệ bằng CSRF/session validation theo policy. Sau switch, role/tenant/caches phải được xác định lại theo principal mới.

### 23.3. Không lấy issuer từ browser

Một authorization request do browser cung cấp <code>provider=https://evil.example</code> không được khiến Client tự tạo OP mới để đổi code/token ở endpoint tùy ý.

Với nhiều providers, bảo vệ OAuth mix-up bằng request correlation/registration binding, chính xác issuer/audience và những biện pháp như issuer identification (RFC 9207) khi provider/framework hỗ trợ.

## 24. Phân biệt lỗi CSRF với authentication/authorization

Khi thấy HTTP 403, không kết luận mọi trường hợp là CSRF.

| Triệu chứng | Lớp lỗi có thể | Cách xác minh |
|---|---|---|
| Browser POST <code>/settings</code> 403, thiếu <code>_csrf</code> | CSRF filter | Kiểm tra CSRF token repository, request header/form, session cookie |
| POST <code>/logout</code> 403 | Logout CSRF | Form/header có CSRF token và cookie đúng chưa |
| GET OAuth callback báo <code>invalid_state</code> | OAuth2 correlation | Session, authorization request repository, state |
| Form-post callback 403 trước login filter | CSRF matcher | Kiểm tra response_mode support và narrow exception |
| Callback state missing sau chuyển node | Session distribution | Spring Session/cookie/session affinity |
| Token Endpoint trả <code>invalid_grant</code> | OAuth grant/code/refresh token | Token request, code_verifier, expiry, replay |
| Token Endpoint trả <code>invalid_client</code> | Client authentication | Secret/key, method, ClientRegistration |
| Resource Server trả 401 | Bearer token authentication | Issuer, audience, expiry, signature, Authorization header |
| Resource Server trả 403 <code>insufficient_scope</code> | OAuth authorization | Scope/resource policy, không refresh mù |
| Browser <code>/admin</code> trả 403 | Spring authorities/business authorization | Role, tenant, ownership |
| OP consent POST bị chặn | CSRF/policy tại OP | Kiểm tra OP logs/form/session, không sửa CSRF ở RP |
| Back-channel POST trả 400 | Logout Token JWT validation | iss/aud/signature/events/exp/sid/sub/nonce |
| Back-channel POST trả 401 | Sai chain, API Bearer authentication | Đúng endpoint OIDC/logout filter chưa |

### 24.1. 401 khác 403

HTTP 401 thường liên quan request chưa được xác thực hoặc token không được chấp nhận. HTTP 403 thường liên quan quyền không đủ hoặc CSRF protection từ chối request. Nhưng gateway/WAF và application handlers có thể thay đổi status, nên cần xem source của response.

### 24.2. Xem lỗi tại filter nào

Trong Spring Security Servlet, một số khái niệm:

~~~text
CsrfFilter
OAuth2AuthorizationRequestRedirectFilter
OAuth2LoginAuthenticationFilter
LogoutFilter
ExceptionTranslationFilter
AuthorizationFilter
~~~

Trong WebFlux:

~~~text
CsrfWebFilter
OAuth2AuthorizationRequestRedirectWebFilter
OAuth2LoginAuthenticationWebFilter
LogoutWebFilter
AuthorizationWebFilter
~~~

**Không suy luận thứ tự filter tuyệt đối từ thứ tự trong danh sách này.** Mỗi security chain và Spring Security version có vị trí filter cụ thể; cần kiểm tra chain thật khi chẩn đoán.

Một exception handler của CSRF có thể tạo 403 trước khi code controller/login handler chạy, trong khi một 403 từ Resource Server có thể đến sau khi OAuth2 Login đã thành công.

## 25. Quy trình chẩn đoán theo endpoint

~~~mermaid
flowchart TD
    A["Request thất bại"] --> B{"Đến endpoint nào?"}
    B -->|"/oauth2/authorization/{id}"| C["Registration/issuer/redirect URI/state creation"]
    B -->|"OP /authorize / consent"| D["OP login/consent CSRF + client/redirect policy"]
    B -->|"GET OAuth2 callback"| E["state, session, code exchange, PKCE, OIDC ID Token"]
    B -->|"POST form_post callback"| F["form_post support, narrow CSRF path, cookie SameSite, state"]
    B -->|"POST /logout"| G["Spring CSRF token, session, logout handlers"]
    B -->|"Back-channel logout"| H["Signed Logout Token validation, session registry"]
    B -->|"Browser POST business"| I["CSRF token + role/tenant/ownership"]
    B -->|"Bearer API"| J["Access token issuer/audience/scope/authorization"]
~~~

### 25.1. Dữ liệu debug an toàn

Log phù hợp có thể gồm:

~~~text
routeTemplate=/login/oauth2/code/{registrationId}
httpMethod=GET
registrationId=company
securityChain=browser
sessionPresent=true
authorizationRequestPresent=false
oauth2Error=authorization_request_not_found
correlationId=...
~~~

Không log:

~~~text
authorization_code
state thật
nonce thật
code_verifier
CSRF token value
access_token / refresh_token / id_token
session cookie / client secret
~~~

Nếu cần liên kết sự kiện, dùng request correlation ID riêng không phải credential. Tránh dùng raw session ID hoặc subject/email làm metric labels.

## 26. Kiểm thử CSRF và OIDC Login trong Servlet

Spring Security Test có thể dùng MockMvc để kiểm tra browser endpoints.

### 26.1. Dependencies

~~~groovy
testImplementation 'org.springframework.boot:spring-boot-starter-test'
testImplementation 'org.springframework.security:spring-security-test'
~~~

### 26.2. POST nghiệp vụ thiếu CSRF phải bị từ chối

Ví dụ test:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.security.test.web.servlet.request
    .SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.security.test.web.servlet.request
    .SecurityMockMvcRequestPostProcessors.oauth2Login;
import static org.springframework.test.web.servlet.request
    .MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result
    .MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class CsrfBusinessEndpointTest {

    @Autowired
    MockMvc mockMvc;

    @Test
    void postWithoutCsrfIsRejected() throws Exception {
        mockMvc.perform(post("/account/change-email")
                .with(oauth2Login())
                .param("email", "new@example.org"))
            .andExpect(status().isForbidden());
    }

    @Test
    void postWithCsrfPassesCsrfCheck() throws Exception {
        mockMvc.perform(post("/account/change-email")
                .with(oauth2Login())
                .with(csrf())
                .param("email", "new@example.org"))
            .andExpect(status().is2xxSuccessful());
    }
}
~~~

Test thứ hai **chỉ phù hợp nếu endpoint tồn tại**, user trong mock được phép thực hiện nghiệp vụ, và controller trả 2xx. Nếu policy yêu cầu role/validation khác, assertion phải phản ánh chúng. <code>.with(csrf())</code> chứng minh vượt qua CSRF check, **không** tự cấp business authorization.

### 26.3. Kiểm thử logout

Ví dụ:

~~~java
@Test
void logoutPostWithoutCsrfIsRejected() throws Exception {
    mockMvc.perform(post("/logout")
            .with(oauth2Login()))
        .andExpect(status().isForbidden());
}

@Test
void logoutPostWithCsrfIsProcessed() throws Exception {
    mockMvc.perform(post("/logout")
            .with(oauth2Login())
            .with(csrf()))
        .andExpect(status().is3xxRedirection());
}
~~~

Tùy <code>logoutSuccessHandler</code>, response sau logout có thể khác redirect thông thường (ví dụ OIDC RP-Initiated Logout). Assert đúng contract của ứng dụng thay vì coi mọi 302 là thành công.

### 26.4. Mock OIDC Login không kiểm tra OAuth callback

<code>oauth2Login()</code>/<code>oidcLogin()</code> trong Spring Security Test có thể giả lập principal đã authenticated. Chúng **không kiểm chứng**:

- Authorization request repository có tạo/lưu state đúng không.
- PKCE verifier/challenge được tạo và kiểm tra ra sao.
- Provider callback có đúng state không.
- ID Token signature/issuer/audience/nonce verification.
- Browser SameSite và form_post behavior.

Những yêu cầu giao thức cần integration test với OP test/fixture có khóa và metadata đáng tin cậy.

## 27. Kiểm thử CSRF trong Reactive WebFlux

Spring Security Test hỗ trợ WebTestClient:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.reactive.server.WebTestClient;

import static org.springframework.security.test.web.reactive.server
    .SecurityMockServerConfigurers.csrf;
import static org.springframework.security.test.web.reactive.server
    .SecurityMockServerConfigurers.mockOidcLogin;

@SpringBootTest
@AutoConfigureWebTestClient
class ReactiveCsrfTest {

    @Autowired
    WebTestClient webTestClient;

    @Test
    void postWithValidCsrfCanReachHandler() {
        webTestClient
            .mutateWith(mockOidcLogin())
            .mutateWith(csrf())
            .post()
            .uri("/account/update")
            .bodyValue("{\"value\":\"demo\"}")
            .exchange()
            .expectStatus().is2xxSuccessful();
    }
}
~~~

Ví dụ giả định <code>/account/update</code> tồn tại và trả 2xx khi mock principal được phép, DTO/body phù hợp. Đây là **mẫu kiểm tra CSRF integration**, không phải bài test có thể copy chạy khi chưa có controller.

Muốn test thiếu CSRF, bỏ <code>.mutateWith(csrf())</code> và kỳ vọng 403 khi request thực sự có cookie-based authenticated context theo test setup.

Đừng viết test chỉ kiểm tra <code>GET /login/oauth2/code/company</code> với code giả và mong trả 200; callback thật cần state/authorization request/Token Endpoint/ID Token validation.

## 28. Ma trận integration test cho authorization/callback/logout

| Kịch bản | Điều kỳ vọng |
|---|---|
| Browser GET <code>/oauth2/authorization/company</code> | Redirect OP đúng registration; authorization request được lưu |
| Browser đến callback GET với state hợp lệ | Correlation đạt, token exchange/validation diễn ra |
| Callback GET state sai | Không tạo Authentication |
| Callback GET thiếu authorization request trong session | Không chấp nhận code |
| Callback code đã dùng lại | Token Endpoint/flow từ chối theo policy |
| Callback ID Token sai nonce/issuer/audience | Login thất bại |
| Browser POST form-post callback không có CSRF form token | Chỉ có thể xử lý nếu path được điều chỉnh hẹp và OIDC state validation vẫn đạt |
| Form-post callback có cookie SameSite không phù hợp | Correlation không tìm được session; không bỏ state |
| Browser POST <code>/settings</code> không CSRF | Bị từ chối |
| Browser POST <code>/settings</code> có CSRF, thiếu role | Vẫn bị từ chối theo authorization |
| Browser POST <code>/logout</code> không CSRF | Bị từ chối |
| Browser POST <code>/logout</code> có CSRF | Local logout theo policy |
| Website khác ép GET <code>/logout</code> | Không làm logout side effect tùy ý |
| OP Back-Channel Logout có JWT sai chữ ký | Bị từ chối |
| OP Back-Channel Logout JWT đúng | Invalidate đúng session mapping |
| Browser GET callback tới node khác A/B | State còn truy cập được nếu shared session hoạt động |
| OP POST back-channel tới node khác login | Shared registry tìm được session, nếu feature được thiết kế HA |
| API Bearer 401 <code>invalid_token</code> | Xử lý token validation, không nhầm CSRF |
| API Bearer 403 <code>insufficient_scope</code> | Xử lý quyền, không refresh mù |

### 28.1. Test browser thực tế

MockMvc/WebTestClient không mô phỏng hoàn toàn behavior SameSite, third-party cookies hoặc OP UI. Khi có <code>response_mode=form_post</code>, cần kiểm thử trên browser thật/automation có session và OP thử nghiệm.

### 28.2. Test nhiều tabs

Khởi tạo đồng thời hai authorization requests cùng browser session. Kiểm tra repository có hỗ trợ correlation cả hai hoặc ứng dụng xử lý UX rõ ràng, không “cho qua mọi state”.

### 28.3. Test rate limiting và endpoint input

Đặc biệt với Back-Channel Logout:

- Invalid JWT phải bị từ chối mà không làm invalidated session.
- Body quá lớn phải bị giới hạn.
- Replay logout event cần idempotent/được xử lý theo policy.
- Không đưa raw JWT vào logs.

## 29. Các bài tập tình huống

### Bài 1 — Đã có state, có tắt CSRF không?

Một ứng dụng OIDC Client dùng session cookie và có POST <code>/transfer</code>. Developer tắt toàn bộ CSRF vì OAuth2 đã có state.

**Câu hỏi:** Sai ở đâu?

**Đáp án:** <code>state</code> chỉ ràng buộc OAuth2 callback với authorization request, không bảo vệ POST nghiệp vụ. Phải bảo vệ <code>/transfer</code> bằng CSRF token hoặc cơ chế tương đương phù hợp threat model.

### Bài 2 — Authorization Endpoint của ai?

Ứng dụng Portal có <code>/oauth2/authorization/company</code> và OP có <code>/authorize</code>.

**Câu hỏi:** Bên nào kiểm tra CSRF của form consent tại OP?

**Đáp án:** Authorization Server/OP. Portal quản lý authorization initiation và state của OAuth2 Client; nó không quản lý CSRF token trong OP consent form.

### Bài 3 — Callback GET

Browser quay về <code>/login/oauth2/code/company?code=C&amp;state=S</code>. Request không có <code>_csrf</code>.

**Câu hỏi:** Có phải lỗi bảo mật mặc định không?

**Đáp án:** Không. GET callback của Authorization Code Flow được bảo vệ bằng state/correlation, PKCE và OIDC validation theo flow. CSRF form token của browser POST không bắt buộc cho GET callback.

### Bài 4 — Callback state mismatch

Authorization request ban đầu có state S1, callback mang S2.

**Câu hỏi:** Có thể bỏ state validation nếu ID Token sau đó ký đúng không?

**Đáp án:** Không. Callback phải được liên kết với request/session gốc. Token ký đúng không tự chứng minh user đã khởi tạo flow đó.

### Bài 5 — Form-post callback 403

OP chuyển về callback bằng cross-site POST, Spring Security CSRF filter trả 403.

**Câu hỏi:** Cần làm gì?

**Đáp án:** Kiểm tra framework hỗ trợ form_post và cookie/session correlation, sau đó chỉ loại trừ **POST callback path chính xác** khỏi synchronizer CSRF check nếu cần; vẫn bắt buộc state/nonce/PKCE/issuer validation. Không disable CSRF toàn ứng dụng.

### Bài 6 — SameSite=Lax và form_post

Sau khi điều chỉnh CSRF matcher, form-post callback vẫn báo state missing.

**Câu hỏi:** Vì sao?

**Đáp án:** Cross-site POST có thể không mang session cookie theo SameSite=Lax, nên Client không tìm được authorization request đã lưu. Phải kiểm tra cookie policy, browser và flow; không tạo state giả từ callback.

### Bài 7 — GET /logout

Ứng dụng tự tạo <code>GET /logout</code> invalidate session.

**Câu hỏi:** Tác động?

**Đáp án:** Website bên ngoài có thể ép navigation để logout user, gây logout CSRF/gián đoạn. Ưu tiên POST có CSRF protection cho local logout.

### Bài 8 — Back-channel POST không có _csrf

OP gửi một signed Logout Token qua POST nhưng không có CSRF form token.

**Câu hỏi:** Có nên từ chối mọi request như vậy chỉ vì thiếu <code>_csrf</code>?

**Đáp án:** Back-Channel Logout dùng JWT Logout Token signature/claims validation, không dùng browser session CSRF token. Cấu hình handler đúng stack/version để chỉ protocol endpoint được xử lý, không bỏ JWT validation.

### Bài 9 — Back-channel JWT có nonce

Logout Token có chữ ký hợp lệ nhưng có claim <code>nonce</code>.

**Câu hỏi:** Chấp nhận không?

**Đáp án:** Không. Logout Token không được có nonce theo OIDC Back-Channel Logout profile; phải tránh nhầm ID Token với Logout Token.

### Bài 10 — API Resource Server và CSRF

<code>/api/**</code> chỉ nhận Bearer token trong Authorization header, không dùng browser cookie. Browser portal routes dùng session cookie.

**Câu hỏi:** Có được tắt CSRF chỉ trong API chain không?

**Đáp án:** Có thể nếu threat model xác nhận không có credential browser tự gửi; cần chain matcher riêng, giữ CSRF cho browser routes. Không tắt CSRF cho mọi chain chỉ vì có API.

### Bài 11 — CSRF token hợp lệ, nhưng user không có role

Browser POST <code>/admin/users</code> có CSRF token hợp lệ và session user bình thường, nhưng API trả 403.

**Câu hỏi:** Có phải CSRF lỗi?

**Đáp án:** Không nhất thiết; có thể là authorization failure. CSRF token chỉ chứng minh request-origin intent theo session, không cấp role ADMIN.

### Bài 12 — Hai providers

Browser bắt đầu authorization tại Company nhưng callback lại cố dùng token/issuer của Partner.

**Câu hỏi:** Chỉ có state đủ để bảo vệ hoàn toàn không?

**Đáp án:** Cần ràng buộc request với registration/issuer/redirect URI gốc, state validation, và OIDC issuer/audience/nonce/ID Token checks; đánh giá mix-up mitigation theo RFC 9207 khi hỗ trợ.

### Bài 13 — Multi-instance

Authorization initiation diễn ra tại node A, callback tới node B và không thấy state.

**Câu hỏi:** Có nên disable Spring Security CSRF filter?

**Đáp án:** Không. Đây thường là lỗi session/correlation storage, cookie hoặc affinity. Cần shared session store và kiểm tra authorization request repository.

### Bài 14 — Account linking

Một website ngoài ép browser đã login tại Portal vào URL liên kết identity Partner.

**Câu hỏi:** Ngoài state callback, Portal cần gì?

**Đáp án:** Hành động link nên bắt đầu bằng POST có CSRF và xác nhận ý định, rồi dùng linking transaction gắn với session/identity hiện tại; callback vẫn phải validate OAuth state, issuer và subject.

### Bài 15 — Thiết kế bảo vệ ba endpoint

Thiết kế ứng dụng có:

~~~text
GET  /oauth2/authorization/company
GET  /login/oauth2/code/company
POST /logout
POST /account/change-email
POST /logout/connect/back-channel/company
~~~

**Yêu cầu:** Nêu cơ chế bảo vệ chính cho từng endpoint.

**Gợi ý đáp án:**

1. GET initiation: ClientRegistration allowlist, server-generated authorization request, state; không cho caller tự chọn issuer tùy ý.
2. GET callback: state và request correlation, PKCE/nonce/issuer/audience validation; không cần browser form CSRF token.
3. POST local logout: CSRF token hợp lệ và standard logout handlers.
4. POST đổi email: CSRF token **và** business authorization/validation.
5. POST back-channel: signed Logout Token validation/registry/issuer/audience, không dùng form CSRF token của browser.

### Bài 16 — Thực hành Spring Security

1. Tạo Spring Boot Servlet app có <code>spring-boot-starter-oauth2-client</code>.
2. Cấu hình registration <code>company</code> dùng Authorization Code và OIDC.
3. Bật <code>oauth2Login()</code> và giữ CSRF mặc định.
4. Tạo trang/form POST đổi một setting, thử không có và có CSRF token.
5. Tạo form POST logout, xác minh thiếu CSRF bị từ chối.
6. Login qua OP thử nghiệm và kiểm tra callback GET dùng state/correlation.
7. Thử callback với state giả, xác nhận không tạo session.
8. Chỉ nếu OP/framework hỗ trợ <code>form_post</code>, kiểm thử POST callback cùng cookie/SameSite policy và narrow CSRF handling.
9. Nếu dùng RP-Initiated Logout, xác minh local POST có CSRF rồi mới redirect OP.
10. Nếu dùng Back-Channel Logout, bật DSL đúng version và kiểm tra signed Logout Token/registry.
11. Tạo API Bearer-only chain riêng và kiểm tra browser CSRF vẫn bật.
12. Kiểm thử hai instances và quan sát session/state/csrf store khi callback đi qua node khác.
13. Giữ logs không chứa token, authorization code, session cookie hoặc CSRF value.

## 30. Tổng kết

- **CSRF** xuất hiện khi attacker khiến browser tự gửi credential của user để thực hiện request không chủ đích. Ứng dụng OIDC dùng session cookie vẫn cần CSRF protection cho các POST/PATCH/DELETE có side effect.
- <code>/oauth2/authorization/{registrationId}</code> tại **Client** khác <code>/authorize</code> tại **OP**. Client quản lý authorization initiation và state; OP bảo vệ form login/consent của OP.
- **OAuth2 <code>state</code>** ràng buộc callback với authorization request và browser session; **Spring CSRF token** bảo vệ browser form/request state-changing. Chúng không thay thế nhau.
- **OIDC nonce, PKCE và issuer/audience validation** bổ sung phòng vệ chống replay, code injection và provider mix-up; không tự thay thế CSRF token nghiệp vụ.
- GET authorization-code callback thông thường **không cần CSRF form token**, nhưng phải được Spring Security OAuth2 Login kiểm tra state/correlation nghiêm ngặt.
- Với <code>response_mode=form_post</code>, cần framework hỗ trợ callback POST, session cookie tương thích SameSite và **ngoại lệ CSRF hẹp cho đúng protocol endpoint** khi cần; tuyệt đối không tắt CSRF toàn hệ thống.
- Local logout nên thực hiện bằng **POST có CSRF**. Một GET tự động hủy session có thể gây logout CSRF.
- OIDC **RP-Initiated Logout** là Client yêu cầu OP kết thúc SSO sau local logout; **Front-Channel Logout** dùng browser; **Back-Channel Logout** dùng server-to-server signed Logout Token, không dùng browser CSRF token.
- Back-Channel Logout phải validate JWT issuer/audience/events/expiry/sid/sub/no-nonce và session mapping; loại trừ CSRF mà bỏ JWT validation sẽ rất nguy hiểm.
- API thực sự **Bearer-only stateless** có thể không cần CSRF token, nhưng browser session routes phải được giữ trong security chain có CSRF protection.
- SameSite, Secure/HttpOnly, reverse proxy, multiple tabs và shared session store có thể quyết định callback/CSRF token được khôi phục hay không; không sửa lỗi storage bằng cách bỏ bảo vệ.
- Kiểm thử cần tách **browser business CSRF**, **OAuth callback state**, **OIDC token validation**, **logout CSRF** và **back-channel logout token validation**.

### Tài liệu tham khảo

- **Spring Security Reference — Servlet CSRF Protection:** <code>CsrfFilter</code>, token repository, CSRF request handler và SPA integration.
- **Spring Security Reference — Reactive CSRF Protection:** <code>CsrfWebFilter</code>, <code>ServerCsrfTokenRepository</code>, WebSession/cookie approaches.
- **Spring Security Reference — OAuth2 Login (Servlet/Reactive):** authorization initiation, authorization request repository, callback và OIDC validation.
- **Spring Security Reference — Logout (Servlet/Reactive):** local logout handlers, CSRF và logout success handlers.
- **Spring Security Reference — OIDC Login Logout:** RP-Initiated Logout, Back-Channel Logout và session registries theo phiên bản hỗ trợ.
- **RFC 6749 — The OAuth 2.0 Authorization Framework:** Authorization Code Flow, Authorization Endpoint, <code>state</code> và Token Endpoint.
- **RFC 7636 — Proof Key for Code Exchange (PKCE):** authorization code binding.
- **RFC 9207 — OAuth 2.0 Authorization Server Issuer Identification:** issuer-based mix-up mitigation.
- **RFC 9700 — Best Current Practice for OAuth 2.0 Security:** browser-based flow, redirect URI, mix-up và CSRF considerations.
- **OpenID Connect Core 1.0:** <code>state</code>, <code>nonce</code>, ID Token, issuer, audience, max_age và OIDC login semantics.
- **OAuth 2.0 Form Post Response Mode 1.0:** cross-site callback sử dụng HTML form POST.
- **OpenID Connect RP-Initiated Logout 1.0:** <code>end_session_endpoint</code>, <code>id_token_hint</code> và post-logout redirection.
- **OpenID Connect Front-Channel Logout 1.0:** browser channel và session correlation.
- **OpenID Connect Back-Channel Logout 1.0:** <code>logout_token</code>, signed JWT validation và session correlation.
- **OWASP Cross-Site Request Forgery Prevention Cheat Sheet:** synchronizer/double-submit tokens, SameSite, Origin/Referer và defense-in-depth.
- **OWASP Session Management Cheat Sheet:** session cookie configuration, session fixation, authentication/session lifecycle.
