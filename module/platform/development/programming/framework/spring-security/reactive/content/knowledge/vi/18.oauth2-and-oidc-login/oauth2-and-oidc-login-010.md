# Tùy chỉnh kết quả đăng nhập, lỗi callback và trang chọn nhà cung cấp

## 1. Mục tiêu, phạm vi và bối cảnh

Một ứng dụng **Spring Security Reactive (Spring WebFlux)** có thể cho người dùng đăng nhập bằng nhiều nhà cung cấp danh tính (Identity Provider — IdP): nhà cung cấp dành cho nhân viên, khách hàng doanh nghiệp, hoặc một nhà cung cấp OIDC công cộng. Sau khi người dùng chọn nhà cung cấp, browser được chuyển tới IdP; khi xác thực xong, IdP đưa browser quay về **callback** của ứng dụng. Kết quả cuối cùng không chỉ là “đăng nhập được hay chưa” mà còn gồm:

- Hiển thị **trang chọn nhà cung cấp** đúng các client registration được phép.
- Xử lý **đăng nhập thành công**: lưu Authentication, chọn đích redirect hợp lệ, bảo toàn trải nghiệm quay lại tài nguyên đã yêu cầu.
- Xử lý **đăng nhập thất bại**: token lỗi, user hủy consent, state mismatch, cấu hình redirect URI sai, IdP không phản hồi; thông báo thân thiện nhưng không lộ code/token/exception nội bộ.
- Đảm bảo browser giữ **WebSession** cho request bắt đầu login và request callback.
- Phân biệt một callback thành công của OAuth 2.0 với xác thực **OpenID Connect** có ID token.
- Kiểm thử các quyết định và redirect trong **WebFlux**, không trộn API Servlet.

Bài học này tập trung vào chủ đề **“Tùy chỉnh kết quả đăng nhập, lỗi callback và trang chọn nhà cung cấp”**, thuộc chương **Đăng nhập OAuth2/OIDC** của module **Spring Security - reactive**.

Sau bài, bạn có thể:

1. Vẽ luồng authorization code từ `/signin` → `/oauth2/authorization/{registrationId}` → IdP → `/login/oauth2/code/{registrationId}` → success/failure.
2. Phân biệt **authentication entry point**, **authorization request resolver**, **callback authentication filter**, **success handler** và **failure handler**.
3. Dùng `ServerHttpSecurity.oauth2Login(...)` với `ServerAuthenticationSuccessHandler` / `ServerAuthenticationFailureHandler` và `RedirectServerAuthenticationEntryPoint`.
4. Thiết kế trang chọn nhà cung cấp tự đọc danh sách `ClientRegistration` từ repository, chỉ render registration IDs server cho phép và escape HTML.
5. Dùng `RedirectServerAuthenticationSuccessHandler` và hiểu tại sao **saved request** có thể được ưu tiên trước fallback destination.
6. Trả lỗi callback bằng mã thông báo công khai an toàn, không phản chiếu raw `error_description` hoặc `AuthenticationException.getMessage()`.
7. Phân biệt `state`, PKCE, OIDC `nonce`, redirect URI, issuer, audience và liên kết session; tránh sửa lỗi callback bằng cách tắt các kiểm tra bảo mật.
8. Chạy project Spring Boot 3.5.x/Java 17+ với hai provider giả lập để **test offline** trang chọn provider và authorization redirect, kiểm thử độc lập success/failure handlers; biết cách gắn IdP thật để test end-to-end.
9. Xác định các giới hạn của mock callback, test tích hợp thật với IdP, và các yêu cầu sản xuất về HTTPS, cookies, proxy, logging và account linking.

**Phạm vi phiên bản:** mã Java áp dụng cho **Spring Boot 3.x, Spring Security 6.5.x, Java 17+**, inbound **WebFlux**. Spring Security 7.x có thể thay đổi API/behavior; luôn kiểm tra dependency tree và Javadoc của phiên bản đang sử dụng. Chỉ các class trong `org.springframework.security.web.server...` và `ServerHttpSecurity` mới phù hợp inbound reactive; đừng copy `HttpSecurity.oauth2Login().loginPage(...)` hoặc `AuthenticationSuccessHandler` Servlet sang đây.

## 2. Cơ chế nền: ứng dụng đóng vai trò gì?

### 2.1. OAuth 2.0 Client vs OIDC login vs Resource Server

Ứng dụng website muốn cho user đăng nhập qua IdP là **OAuth 2.0 Client**, sử dụng Authorization Code Flow. Khi registration có scope `openid` và IdP hỗ trợ chuẩn OIDC, Spring Security dùng các thành phần **OIDC login** để xác minh ID token/claims và tạo identity. Nếu không có `openid`, OAuth2 login có thể dựa trên UserInfo endpoint theo chiến lược provider.

Đừng nhầm ba vai trò:

| Vai trò | Chức năng |
|---|---|
| OAuth 2.0 Client / OIDC Relying Party | Đưa browser sang IdP, đổi code lấy token, thiết lập Authentication cho website |
| Authorization Server / OpenID Provider | Xác thực user, phát authorization code, token, ID token và metadata |
| Resource Server | Bảo vệ API dựa trên access token trong request, không tự là trang đăng nhập website |

Một ứng dụng có thể đồng thời làm client và resource server, nhưng **`oauth2Login` khác `oauth2ResourceServer`**. Bài này nói về browser login qua authorization code và callback, không phải xác thực Bearer JWT ở mọi request.

### 2.2. Hai URL mặc định dễ nhầm

Với ClientRegistration có `registrationId = "alpha"`:

- **Bắt đầu login:** `GET /oauth2/authorization/alpha`. Đây là URL **trên ứng dụng**, được Spring Security xử lý để tạo authorization request và redirect browser sang IdP.
- **Nhận callback:** `GET /login/oauth2/code/alpha`. Đây là redirect URI **của ứng dụng**, IdP gửi user trở lại sau khi người dùng xác thực/hủy/không cho phép.

Chuỗi mặc định dùng trong registration:

```text
{baseUrl}/login/oauth2/code/{registrationId}
```

`{baseUrl}` được tính từ địa chỉ ứng dụng thực tế (scheme, host, port, context path tùy environment và framework). Khi triển khai sau reverse proxy, phải đảm bảo địa chỉ này khớp redirect URI đăng ký với IdP. Đừng đổi callback path chỉ trong IdP rồi quên `ClientRegistration.redirectUri` và matcher của Spring Security.

### 2.3. Luồng đăng nhập đầy đủ

```text
1. Browser: GET /private
      |
      v
   Authorization yêu cầu authenticated
      |
      v
   RedirectServerAuthenticationEntryPoint -> 302 /signin

2. Browser: GET /signin
      |
      v
   Trang chọn:
      "Alpha Identity" -> /oauth2/authorization/alpha
      "Beta Identity"  -> /oauth2/authorization/beta

3. Browser: GET /oauth2/authorization/alpha
      |
      v
   OAuth2AuthorizationRequestRedirectWebFilter
   DefaultServerOAuth2AuthorizationRequestResolver
      |
      +-- xác định ClientRegistration "alpha"
      +-- tạo state ngẫu nhiên (và tham số khác khi phù hợp)
      +-- lưu authorization request để đối chiếu callback
      +-- redirect browser -> IdP authorization endpoint

4. Browser ở IdP:
      -> xác thực / consent / chọn tài khoản
      -> IdP redirect browser về callback ứng dụng

5. Browser: GET /login/oauth2/code/alpha?code=...&state=...
      |
      v
   Reactive authentication flow:
      -> nạp authorization request đã lưu
      -> kiểm tra correlation (state, client, redirect ...)
      -> trao đổi code với token endpoint
      -> nếu OIDC: xác thực ID token/claims qua thành phần tương ứng
      -> có Authentication đã xác thực
      |
      +-- SUCCESS
      |     -> lưu security context theo strategy
      |     -> ServerAuthenticationSuccessHandler
      |     -> redirect saved URL hoặc /home
      |
      +-- FAILURE
            -> ServerAuthenticationFailureHandler
            -> redirect /signin?error=oauth2
            -> thông báo công khai không chứa code/token/stacktrace
```

Đây là **sơ đồ khái niệm**, không cam kết thứ tự nội bộ mọi filter cho mọi version/provider. Callback có `error=access_denied` thay vì `code` nếu user hủy hoặc IdP từ chối. Không tự gọi token endpoint bằng tay từ controller callback; Spring Security đã cung cấp authentication pipeline.

## 3. Trang chọn nhà cung cấp: mặc định và tùy chỉnh

### 3.1. Trang mặc định do Spring Security tạo

Khi OAuth2 Login được bật và không có custom login page, Spring Security Reactive có thể dùng `LoginPageGeneratingWebFilter` tạo trang login tự động, liệt kê các OAuth Client được cấu hình.

Trang mặc định lấy nhãn hiển thị từ `ClientRegistration.clientName` và tạo link theo mẫu:

```html
<a href="/oauth2/authorization/google">Google</a>
```

Điều kiện quan trọng: repository dùng để phát hiện client cho **generated page** cần hỗ trợ duyệt `Iterable<ClientRegistration>`. `InMemoryReactiveClientRegistrationRepository` implement cả `ReactiveClientRegistrationRepository` và `Iterable<ClientRegistration>`. Nếu bạn dùng repository thuần reactive chỉ có `findByRegistrationId(...)`, trang mặc định có thể không liệt kê provider như dự kiến.

Generated page phù hợp để thử nhanh. Một sản phẩm thực cần logo/brand, mô tả cơ chế dùng tài khoản, hỗ trợ accessibility, hiển thị lỗi, i18n, lựa chọn tenant và quy tắc an toàn.

### 3.2. WebFlux custom page: khác Servlet

Đối với Spring Security Reactive 6.5, tài liệu hướng dẫn custom page qua:

```java
.exceptionHandling(ex -> ex
    .authenticationEntryPoint(
        new RedirectServerAuthenticationEntryPoint("/signin")))
.oauth2Login(oauth -> oauth
    // Những cấu hình OIDC/OAuth2 cần thiết.
)
```

Đây là **mảnh cấu hình**, không phải class độc lập. Bạn phải cung cấp controller phục vụ `GET /signin` và cho phép route đó theo authorization rules. Không tìm `.loginPage("/signin")` trong Servlet OAuth2LoginSpec rồi copy máy móc: hướng đi của **WebFlux** là custom `ServerAuthenticationEntryPoint` và trang do ứng dụng render.

Với `/oauth2/authorization/{registrationId}` giữ default, không cần custom authorization request resolver chỉ để đổi giao diện trang chọn nhà cung cấp. Nếu muốn đổi URL bắt đầu login, cần cấu hình `ServerOAuth2AuthorizationRequestResolver` cùng matcher phù hợp và đổi tất cả links; không tự thay link rồi cho rằng Spring Security sẽ tự nhận.

### 3.3. Nguồn dữ liệu trang chọn

Một chiến lược đáng tin cậy:

1. Lấy danh sách registration đã cấu hình **ở server**, không từ query `?providerUrl=...` do client gửi.
2. Dùng registrationId ổn định, chỉ bao gồm ký tự cho phép hoặc URL-encode path segment.
3. Chỉ render provider được phép trong **tenant hoặc business context** hiện tại nếu có nhiều tenant; không tự biến một provider người dùng nhập thành endpoint đáng tin.
4. Escape tên/nhãn theo ngữ cảnh HTML để tránh XSS nếu cấu hình có giá trị không đáng tin.
5. Không đưa `clientSecret`, access token, refresh token, JWKS private key hoặc OIDC ID token lên trang.
6. Link tới local path tương đối `/oauth2/authorization/{registrationId}`, **không** link thẳng tới một authorize URL được client tùy ý cung cấp.
7. Cân nhắc accessibility: liên kết là `<a>` thực, tên rõ ràng, focus keyboard và thông báo lỗi có `role="alert"`.
8. Khi provider bị ngừng hoặc chỉ dùng cho nhân viên, quyết định ẩn/cho phép dựa trên policy server-side; chỉ ẩn trong UI không đủ để chặn endpoint bắt đầu OAuth2 của provider đó.

### 3.4. Không tạo open redirect

Một pattern nguy hiểm là:

```text
/signin?next=https://attacker.example/collect
```

Nếu thành công rồi success handler gọi `redirect(next)` mà không kiểm tra origin/target, attacker có thể đưa user tới website giả mạo, đánh cắp thông tin qua URL, phishing hoặc OAuth flow confusion.

Trong code demo, redirect target được **cố định** ở `/home`, có thể ưu tiên saved request do Spring Security quản lý. Nếu business thật cần `returnTo`, chỉ chấp nhận local path hợp lệ từ allowlist, cấm scheme/host/`//`/encoded bypass, chuẩn hóa URI và kiểm thử open redirect. Không phản chiếu thẳng `Referer` hoặc `redirect_uri` từ request thành redirect target sau login.

## 4. Điểm tùy biến: entry point, success handler và failure handler

### 4.1. Authentication entry point: chưa có đăng nhập

`ServerAuthenticationEntryPoint` được dùng khi một request đến resource protected nhưng **chưa có Authentication hợp lệ**. Với browser website, ta thường redirect về trang chọn provider:

```java
ServerAuthenticationEntryPoint entry =
    new RedirectServerAuthenticationEntryPoint("/signin");
```

Đây là mảnh code, import `org.springframework.security.web.server.ServerAuthenticationEntryPoint` và `org.springframework.security.web.server.authentication.RedirectServerAuthenticationEntryPoint`. Nó khác failure handler: thiếu đăng nhập **không giống** một attempt đăng nhập OAuth2 đã thất bại.

Ví dụ:
- Anonymous gọi `GET /private` → redirect `/signin`.
- Người đã xác thực nhưng thiếu role → thường 403, **không** phải luôn redirect login.
- SPA/API clients thường thích 401 JSON hơn redirect HTML; có thể cần **security chains/entry points khác nhau** cho UI và API.

### 4.2. ServerAuthenticationSuccessHandler: callback thành công

Trong Spring Security WebFlux:

```java
public interface ServerAuthenticationSuccessHandler {
    Mono<Void> onAuthenticationSuccess(
        WebFilterExchange webFilterExchange,
        Authentication authentication);
}
```

Đây là **mô tả API**, không cần tự khai báo interface trong project. Handler được gọi sau khi authentication thành công trong flow tương ứng. Nó có thể redirect, ghi audit category hoặc chọn landing page an toàn; nó **không được tin kết quả authentication do client tự khai**.

DSL:

```java
.oauth2Login(oauth2 -> oauth2
    .authenticationSuccessHandler(
        new RedirectServerAuthenticationSuccessHandler("/home")))
```

`RedirectServerAuthenticationSuccessHandler("/home")` dùng `/home` như **fallback**. Theo Javadoc, handler thường ưu tiên **saved request** đã cache trước login nếu có; nếu không, nó redirect `/home`. Như vậy không nên nhìn constructor rồi kết luận “mọi login luôn về /home”.

Nếu yêu cầu **bất kể saved request cũng về /home**, cần quyết định rõ việc vô hiệu hóa/không dùng request cache trong handler hoặc toàn security chain, ví dụ:

```java
RedirectServerAuthenticationSuccessHandler handler =
    new RedirectServerAuthenticationSuccessHandler("/home");
handler.setRequestCache(NoOpServerRequestCache.getInstance());
```

Đây là **mảnh code minh họa** trong cấu hình chuyên biệt; cần import `NoOpServerRequestCache`. Đánh đổi là user có thể không quay về URL protected ban đầu. Không tự cài handler lưu returnUrl từ query không kiểm soát.

### 4.3. ServerAuthenticationFailureHandler: callback/login attempt thất bại

WebFlux contract:

```java
public interface ServerAuthenticationFailureHandler {
    Mono<Void> onAuthenticationFailure(
        WebFilterExchange webFilterExchange,
        AuthenticationException exception);
}
```

Ví dụ:

```java
.oauth2Login(oauth2 -> oauth2
    .authenticationFailureHandler(
        new RedirectServerAuthenticationFailureHandler(
            "/signin?error=oauth2")))
```

Nó chuyển user về **trang lỗi thân thiện** sau một authentication attempt do login filter xử lý bị lỗi. Query param `error=oauth2` là **mã cố định do server chọn**, không lấy từ IdP. Trang `/signin` chỉ hiển thị thông báo chung; không phản chiếu raw `error_description`, `code`, `state`, `id_token`, `access_token` hoặc `exception.getMessage()`.

Javadoc 6.5 của `OAuth2LoginSpec` nêu default failure handler là `RedirectServerAuthenticationFailureHandler` redirect `/login?error`. Khi đổi custom page, nên đổi cả failure target để tránh redirect về trang mặc định không còn phù hợp.

### 4.4. Khác nhau về thời điểm và lỗi

| Tình huống | Thành phần xử lý chính | Hành vi UI |
|---|---|---|
| Anonymous tới `/private` | Authentication entry point | Redirect `/signin` |
| User bấm link provider | Authorization-request redirect filter | Redirect tới IdP |
| Callback hợp lệ, tokens/user được xác minh | OAuth2 authentication filter/manager + success handler | Redirect saved URL hoặc `/home` |
| Callback được filter nhận nhưng authentication failed | Failure handler | Redirect `/signin?error=oauth2` |
| User authenticated nhưng không có quyền | Authorization + access denied handler | 403 hoặc flow tùy loại client |
| IdP URL không phản hồi trên browser | Browser/network/IdP, chưa có callback | Không nhất thiết có server-side failure handler |
| Cấu hình route/callback không match filter | Router/chain khác hoặc 404 | Không chắc đi qua success/failure handler |
| Lỗi server ngoài AuthenticationException | Error handling/container | Có thể 5xx, không luôn chuyển thành OAuth2 failure redirect |

**Tránh một nhầm lẫn lớn:** không phải mọi request `/login/oauth2/code/...` lỗi đều được `ServerAuthenticationFailureHandler` bao trùm. Nếu request không khớp matcher, bị chặn bởi chain khác, hoặc lỗi xảy ra ngoài authentication attempt, xử lý có thể đi theo exception filter, 404 hoặc error handler. Test đúng từng loại lỗi.

### 4.5. Không tự subscribe trong handlers

Một custom handler có kiểu:

```java
ServerAuthenticationSuccessHandler handler =
    (exchange, authentication) -> {
        return auditService.recordLogin(authentication.getName())
            .then(new RedirectServerAuthenticationSuccessHandler("/home")
                .onAuthenticationSuccess(exchange, authentication));
    };
```

Đây là **snippet** cần một `auditService` trả `Mono<Void>`. Không gọi `auditService.recordLogin(...).subscribe()` rồi trả redirect độc lập: nó tách error/cancellation/lifecycle. Nếu audit backend lỗi, quyết định fail-open hay fail-closed cho login phải được thiết kế; không để mất đăng nhập tùy tiện hoặc rò token qua log.

Với audit quan trọng cần hệ thống queue/outbox đúng nghĩa, không biến handler thành nơi gọi nhiều hệ thống đồng bộ có thể làm callback timeout.

### 4.6. List success handlers trong 6.3+

`OAuth2LoginSpec.authenticationSuccessHandler(...)` có overload nhận một `ServerAuthenticationSuccessHandler` và overload nhận `Consumer<List<ServerAuthenticationSuccessHandler>>` từ Spring Security 6.3. Javadoc lưu ý setter single-handler có thể **thay thế/clear** những handler được thêm bằng overload list. Điều này quan trọng với các cơ chế khác như session-concurrency/registration.

Nếu ứng dụng có thêm OIDC session registry, maximum sessions hoặc event handler, hãy review **toàn bộ list success handlers** và thứ tự khi cấu hình custom redirect. Không giả định gọi setter đơn giản luôn giữ các handler khác; test logout/session tracking và nâng cấp framework.

## 5. Callback OAuth2/OIDC và những nơi có thể lỗi

### 5.1. Mặc định callback URL

Với `registrationId="alpha"`:

```text
Application authorization start:
  GET /oauth2/authorization/alpha

IdP callback to application:
  GET /login/oauth2/code/alpha?code=...&state=...
```

`code` là authorization code ngắn hạn, thường dùng một lần. `state` liên kết response với authorization request khởi tạo trước đó để giảm CSRF/login injection/response mix-up. Đây là **các giá trị nhạy cảm**, không ghi raw vào logs/URLs bổ sung hoặc hiển thị trong trang lỗi.

### 5.2. Authorization request repository và WebSession

Khi bắt đầu login, `OAuth2AuthorizationRequestRedirectWebFilter` tạo authorization request, thường kèm random `state` và có thể PKCE/OIDC parameters phù hợp. `ServerAuthorizationRequestRepository` lưu request để callback so sánh. Với Spring Security Reactive, implementation mặc định là `WebSessionOAuth2ServerAuthorizationRequestRepository`.

Hệ quả:

- Browser phải tiếp tục dùng cùng WebSession/cookie giữa bắt đầu login và callback.
- Nếu browser chặn cookie, WebSession hết hạn, tab đổi profile/incognito hoặc load balancer chuyển node nhưng store không chia sẻ, state correlation có thể thất bại.
- User có thể mở nhiều tab và bắt đầu login song song; cần kiểm thử hành vi của repository và browser thực tế, không giả định nó giữ vô hạn authorization requests đồng thời.
- Khi dùng SameSite cookie, top-level GET callback thường phù hợp với `Lax` trong nhiều browser; nếu IdP dùng `response_mode=form_post`, cookie semantics có thể khác và cần đánh giá chặt.
- Không “sửa state mismatch” bằng cách bỏ state validation hoặc chấp nhận callback khi authorization request không tồn tại.

### 5.3. Các lỗi thường gặp

| Nơi lỗi | Ví dụ | Cách xử lý an toàn |
|---|---|---|
| User tại IdP | Hủy login/consent, IdP trả `error=access_denied` | Thông báo chung, cho user chọn provider khác hoặc thử lại |
| Authorization request | registrationId không có/không được phép | Không dựng redirect tới URL user nhập; render lỗi/generic 404 |
| Correlation | `state` thiếu/sai/replay/session không khớp | Từ chối, không bỏ kiểm tra; debug cookie/session |
| Redirect URI | IdP báo `redirect_uri_mismatch` | Đối chiếu registration, app baseUrl, HTTPS/proxy |
| Authorization code | Đã hết hạn, dùng lại, token endpoint từ chối | Không retry bằng code cũ; bắt đầu authorization mới |
| Client authentication | client-id/secret sai, secret hết hạn | Sửa cấu hình/secret manager, không log secret |
| PKCE | `code_verifier` không khớp `code_challenge` | Không tắt PKCE khi policy/client yêu cầu; xem session/repository |
| OIDC ID token | Chữ ký/JWK/issuer/audience/nonce/time không hợp lệ | Deny, kiểm tra IdP metadata và clock skew có giới hạn |
| UserInfo | Endpoint 401/403/timeout, dữ liệu thiếu | Không tạo user từ claims chưa được xác minh; xử lý lỗi |
| Authentication persistence | Login thành công nhưng session/context không được nạp request sau | Kiểm tra `ServerSecurityContextRepository` read/write |
| Network | IdP không truy cập được, proxy timeout | Error page hỗ trợ retry có kiểm soát, observability |
| Security chain | Callback bị 404 hoặc redirect vòng lặp | So matcher, route, thứ tự chain, context path |
| Browser | Cookie bị chặn/thay, SameSite sai | Kiểm tra DevTools cookie và redirect chain |
| Multiple replicas | Node B không biết request lưu ở node A | Shared WebSession store/distributed session strategy |

### 5.4. OIDC khác OAuth2 UserInfo

Trong OIDC, ID token chứa claims về xác thực user, phải được verify đúng issuer, audience, thời hạn, signature và những giá trị cần thiết theo flow. Scope `openid` là dấu hiệu dùng OIDC trong Spring Security; các scopes `profile`, `email` cung cấp quyền nhận claims, **không tự tạo role ADMIN**.

Đừng dùng email chưa được xác minh làm khóa liên kết tài khoản. Identifier ổn định nên dựa trên `iss + sub` hoặc mapping đáng tin tương đương. Hai IdP có thể có cùng `sub` string; nếu chỉ lưu `sub` mà bỏ issuer/provider context sẽ có nguy cơ trộn identities. Cũng không tự nâng quyền dựa vào domain email hoặc một claim không được kiểm tra theo policy.

### 5.5. Lỗi provider redirect không phải luôn “server callback failure”

Nếu browser không thể mở trang IdP, DNS lỗi hoặc user đóng tab trước callback, backend có thể không nhận request callback nào. `authenticationFailureHandler` không biết sự việc đó. UI cần giúp người dùng thử lại; monitoring có thể quan sát tỷ lệ initiation/callback với correlation an toàn (không log code/state thô).

## 6. Redirect sau login: lưu intent và tránh redirect nguy hiểm

### 6.1. Saved request

Người dùng chưa đăng nhập mở `/reports/2026`, security chain nhận thấy cần authentication, và request cache có thể lưu URL gốc trong WebSession. Sau OAuth2 login, `RedirectServerAuthenticationSuccessHandler` có thể redirect người dùng về URL đã lưu, thay vì fallback `/home`.

```text
GET /reports/2026
  -> redirect /signin
  -> user chọn Alpha
  -> browser /oauth2/authorization/alpha
  -> IdP login và callback thành công
  -> success handler:
       nếu saved request hợp lệ => /reports/2026
       nếu không             => /home
```

Đây là **hành vi khi request cache được cấu hình/phù hợp**; không cam kết mọi request đều được cache. Một request API `POST`/body lớn không nên tự động “replay” bằng redirect theo giả định không an toàn. Kiểm tra `WebSessionServerRequestCache` và policy của ứng dụng.

### 6.2. Fallback landing page

`RedirectServerAuthenticationSuccessHandler("/home")` nêu địa chỉ fallback. Dùng local relative path cố định thay URL ngoài do user truyền. Nếu sản phẩm phân luồng admin/customer, nên dùng claims/authorities đã được xác minh và server-side allowlist; không tin `role=admin` trên query callback.

### 6.3. Hoàn tất login rồi không lưu Authentication

Nếu callback được xác thực nhưng handler redirect thành công và request sau trở lại anonymous, hãy kiểm tra:

- `OAuth2LoginSpec.securityContextRepository(...)` (save sau OAuth2 login) và `ServerHttpSecurity.securityContextRepository(...)` (load vào Reactor context) có strategy tương thích không.
- Browser có giữ session cookie do ứng dụng phát không?
- Session ID có rotate sau login không? Browser phải dùng **cookie mới**.
- Ứng dụng có nhiều node và session store chia sẻ không?
- Có các security chains khác nhau dùng state/no-op repository không?

**Không** sửa bằng cách truyền token qua URL query tới `/home`. OAuth2/OIDC tokens phải được giữ ở storage phù hợp, với quyền truy cập/expiry được quản lý, không phản chiếu ra browser URL/log.

### 6.4. RedirectURI và behind-proxy

IdP so sánh redirect URI theo policy đã đăng ký. Nếu external site là `https://app.example` nhưng Spring backend nhìn `http://service:8080`, giá trị `baseUrl` có thể sai.

Hãy cấu hình forwarded headers **chỉ tin từ reverse proxy đáng tin**, TLS termination, host/port/context path chính xác, rồi đăng ký callback IdP tương ứng. Không tin `Host`/`X-Forwarded-Host` do client công khai tự đặt để dựng redirect tùy ý.

## 7. Project Java 17+ WebFlux chạy được, kiểm thử offline không cần IdP thật

Ví dụ dùng **hai registration giả lập** chỉ để chứng minh:

- Trang `/signin` render danh sách Alpha/Beta với links an toàn.
- Request `/oauth2/authorization/alpha` và `/oauth2/authorization/beta` tạo redirect đến fake IdP endpoint, có `state`.
- Request protected `/private` chuyển về `/signin`.
- `ServerAuthenticationSuccessHandler` / `ServerAuthenticationFailureHandler` tạo redirect đúng và không chèn exception detail.
- Callback **thành công thật** không thể hoàn tất với fake IdP hostname, vì không có authorization/token/JWKS server thật. Test end-to-end cần IdP thật hoặc test IdP server đáng tin.

Giới hạn này giúp bài code **chạy và kiểm thử được phần tùy chỉnh**, mà không giả tạo một callback có thể bypass OIDC validation. Sau khi thay bằng các endpoints và credentials thật của provider, application mới hỗ trợ login end-to-end.

### 7.1. Dependencies và cấu trúc

Tạo Gradle Groovy project từ [Spring Initializr](https://start.spring.io/) với Java 17+, Spring Boot 3.5.x và các starters:
- Spring Reactive Web.
- Spring Security.
- OAuth2 Client.
- Spring Boot Starter Test, Spring Security Test, Reactor Test.

Phần `dependencies` trong `build.gradle` do Initializr tạo:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-client'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
    testImplementation 'io.projectreactor:reactor-test'
    testRuntimeOnly 'org.junit.platform:junit-platform-launcher'
}
```

Đây **chỉ là block dependencies**, không phải file Gradle đầy đủ. Giữ Gradle plugins, toolchain và repositories từ Initializr. Tránh `spring-boot-starter-web` khi inbound stack cần WebFlux, vì khi có cả MVC và WebFlux, Boot 3.x thường ưu tiên Servlet MVC.

Bố cục:

```text
src/main/java/demo/oauthlogin/
  OidcLoginApplication.java
  SecurityConfig.java
  LoginRedirects.java
  ProviderPageController.java
  PagesController.java
src/test/java/demo/oauthlogin/
  OAuthLoginWebTests.java
  LoginRedirectHandlerTests.java
```

### 7.2. OidcLoginApplication.java

```java
package demo.oauthlogin;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class OidcLoginApplication {

    public static void main(String[] args) {
        SpringApplication.run(OidcLoginApplication.class, args);
    }
}
```

### 7.3. SecurityConfig.java: client registrations và WebFlux security

```java
package demo.oauthlogin;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.oauth2.client.registration.ClientRegistration;
import org.springframework.security.oauth2.client.registration.InMemoryReactiveClientRegistrationRepository;
import org.springframework.security.oauth2.core.AuthorizationGrantType;
import org.springframework.security.oauth2.core.ClientAuthenticationMethod;
import org.springframework.security.web.server.SecurityWebFilterChain;
import org.springframework.security.web.server.authentication.RedirectServerAuthenticationEntryPoint;

@Configuration
@EnableWebFluxSecurity
public class SecurityConfig {

    @Bean
    public SecurityWebFilterChain chain(ServerHttpSecurity http) {
        return http
            .authorizeExchange(exchanges -> exchanges
                .pathMatchers(HttpMethod.GET,
                    "/", "/signin").permitAll()
                .pathMatchers(HttpMethod.GET,
                    "/oauth2/authorization/**").permitAll()
                .pathMatchers(HttpMethod.GET,
                    "/login/oauth2/code/**").permitAll()
                .pathMatchers(HttpMethod.GET,
                    "/home", "/private").authenticated()
                .anyExchange().denyAll()
            )
            .exceptionHandling(exceptions -> exceptions
                .authenticationEntryPoint(
                    new RedirectServerAuthenticationEntryPoint("/signin")))
            .oauth2Login(oauth2 -> oauth2
                .authenticationSuccessHandler(LoginRedirects.success())
                .authenticationFailureHandler(LoginRedirects.failure()))
            .formLogin(form -> form.disable())
            .httpBasic(basic -> basic.disable())
            .build();
    }

    @Bean
    public InMemoryReactiveClientRegistrationRepository registrations() {
        return new InMemoryReactiveClientRegistrationRepository(
            demo("alpha", "Alpha Identity",
                "https://login.alpha.example.test"),
            demo("beta", "Beta Identity",
                "https://login.beta.example.test")
        );
    }

    private ClientRegistration demo(
            String id, String display, String base) {
        return ClientRegistration.withRegistrationId(id)
            .clientId(id + "-demo-client")
            .clientSecret("not-a-real-secret")
            .clientAuthenticationMethod(
                ClientAuthenticationMethod.CLIENT_SECRET_BASIC)
            .authorizationGrantType(
                AuthorizationGrantType.AUTHORIZATION_CODE)
            .redirectUri("{baseUrl}/login/oauth2/code/{registrationId}")
            .scope("openid", "profile", "email")
            .authorizationUri(base + "/authorize")
            .tokenUri(base + "/token")
            .jwkSetUri(base + "/jwks")
            .userInfoUri(base + "/userinfo")
            .userNameAttributeName("sub")
            .clientName(display)
            .build();
    }
}
```

**Cảnh báo quan trọng:** các host `.example.test`, client ID và client secret trên là **dữ liệu không có IdP thật**, chỉ để test locally generated authorization redirect. Không dùng trong production và không coi việc nhận 302 là đã đăng nhập thành công. Muốn tích hợp thật, đăng ký OAuth/OIDC client với IdP, thay endpoints, dùng `clientId`/`clientSecret` từ secret manager/env, thiết lập issuer/JWKS và callback HTTPS đúng. Với OIDC, provider metadata và ID token validation phải thực sự được xác minh, không tự chấp nhận unsigned token.

Cấu hình trên:

1. Cho phép `GET /signin` và `/oauth2/authorization/**` để browser chọn/bắt đầu login.
2. Để callback khớp OAuth2 authentication filter; `permitAll` trên callback **không cho phép bỏ qua state/ID token validation**. Security authentication filter vẫn xử lý callback trước authorization controller trong chain đúng.
3. Bảo vệ `/home` và `/private`.
4. Redirect anonymous request về `/signin` nhờ entry point.
5. Tùy chỉnh success/failure theo `LoginRedirects`.
6. Giữ CSRF protection mặc định, không bật Basic/Form Login. OAuth2 callback mặc định dùng GET; nếu dùng POST response mode phải xem matcher/cookie/CSRF cụ thể.
7. Hai ClientRegistration thuộc OIDC do scope `openid`, nhưng demo không thể verify ID token nếu không có real IdP.
8. `InMemoryReactiveClientRegistrationRepository` implement `Iterable<ClientRegistration>`, thuận tiện để tự render provider page.

### 7.4. LoginRedirects.java: success/failure targets dùng chung

```java
package demo.oauthlogin;

import org.springframework.security.web.server.authentication.RedirectServerAuthenticationFailureHandler;
import org.springframework.security.web.server.authentication.RedirectServerAuthenticationSuccessHandler;
import org.springframework.security.web.server.authentication.ServerAuthenticationFailureHandler;
import org.springframework.security.web.server.authentication.ServerAuthenticationSuccessHandler;

public final class LoginRedirects {

    private LoginRedirects() {
    }

    public static ServerAuthenticationSuccessHandler success() {
        // Saved request (nếu có) được ưu tiên trước fallback /home.
        return new RedirectServerAuthenticationSuccessHandler("/home");
    }

    public static ServerAuthenticationFailureHandler failure() {
        // Luôn dùng error code cố định, không echo IdP/error details.
        return new RedirectServerAuthenticationFailureHandler(
            "/signin?error=oauth2");
    }
}
```

Code này chứa logic chung cho configuration và unit tests. Khi muốn thêm audit, wrap/compose handler bằng `Mono<Void>`, đừng tự `subscribe()` vào một side effect rời.

Không tự tạo response body chứa token trên success. Mục tiêu redirect là **local path** cố định; URI của saved request phải được quản lý trong framework request cache/allowlist, không lấy trực tiếp từ request query.

### 7.5. ProviderPageController.java: render các provider từ repository

```java
package demo.oauthlogin;

import java.util.Comparator;
import java.util.List;
import java.util.Set;
import java.util.stream.StreamSupport;

import org.springframework.http.MediaType;
import org.springframework.security.oauth2.client.registration.ClientRegistration;
import org.springframework.security.oauth2.client.registration.InMemoryReactiveClientRegistrationRepository;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ServerWebExchange;
import org.springframework.web.util.HtmlUtils;
import reactor.core.publisher.Mono;

@RestController
public class ProviderPageController {

    private static final Set<String> ALLOWED =
        Set.of("alpha", "beta");

    private final InMemoryReactiveClientRegistrationRepository clients;

    public ProviderPageController(
            InMemoryReactiveClientRegistrationRepository clients) {
        this.clients = clients;
    }

    @GetMapping(value = "/signin",
                produces = MediaType.TEXT_HTML_VALUE)
    public Mono<String> signIn(
            @RequestParam(name = "error", required = false)
            String error,
            ServerWebExchange exchange) {

        exchange.getResponse().getHeaders()
            .setCacheControl("no-store");

        List<ClientRegistration> providers =
            StreamSupport.stream(clients.spliterator(), false)
                .filter(c -> ALLOWED.contains(c.getRegistrationId()))
                .sorted(Comparator.comparing(
                    ClientRegistration::getClientName))
                .toList();

        StringBuilder html = new StringBuilder("""
            <!doctype html>
            <html lang="vi">
            <head><meta charset="utf-8">
            <title>Chọn tài khoản đăng nhập</title></head>
            <body>
            <h1>Chọn nhà cung cấp danh tính</h1>
            """);

        if ("oauth2".equals(error)) {
            html.append("""
                <p role="alert">Không thể hoàn tất đăng nhập.
                Vui lòng thử lại hoặc liên hệ hỗ trợ.</p>
                """);
        }

        html.append("<ul>");
        for (ClientRegistration c : providers) {
            String id = c.getRegistrationId();
            // Chỉ cho phép các registrationId cố định từ ALLOWED.
            html.append("<li><a href=\"/oauth2/authorization/")
                .append(id)
                .append("\">")
                .append(HtmlUtils.htmlEscape(c.getClientName()))
                .append("</a></li>");
        }
        html.append("</ul></body></html>");

        return Mono.just(html.toString());
    }
}
```

Đây là **controller Java 17+ độc lập**:

- `ALLOWED` là allowlist server-side. Việc này không thay policy ở authorization endpoint; nếu nhiều tenant, cần policy server-side tương ứng cho phép bắt đầu login, không chỉ ẩn link.
- Dùng `StreamSupport` vì repository demo implement `Iterable<ClientRegistration>`. Với repository chỉ implement `ReactiveClientRegistrationRepository` mà không `Iterable`, thiết kế lại cách lấy danh sách provider đáng tin (ví dụ config/service riêng). **Không cast mù** một repository bất kỳ thành Iterable.
- `HtmlUtils.htmlEscape` tránh đưa tên provider trực tiếp vào HTML không escape.
- `registrationId` chỉ lấy từ allowlist không có ký tự đặc biệt; với provider IDs không tĩnh, cần validate và URI-encode path segment.
- Trang chỉ nhận query `error` thuộc danh sách value cho phép; không render mọi `error_description` raw.
- `Cache-Control: no-store` giảm nguy cơ cache HTML lỗi đăng nhập.
- Trong HTML thực, thêm styling, accessibility/i18n, link chính sách quyền riêng tư và hành trình hỗ trợ IdP.

Cấu hình Spring Security 6.5 custom login page **không cần** route `POST /signin` để nhận password, vì password được nhập **tại IdP**. Form nhận password từ browser của chính app sẽ chuyển sang mô hình khác (form login) và có risk riêng.

### 7.6. PagesController.java: phân biệt public và authenticated

```java
package demo.oauthlogin;

import org.springframework.security.core.context.ReactiveSecurityContextHolder;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Mono;

@RestController
public class PagesController {

    @GetMapping("/")
    public Mono<String> index() {
        return Mono.just("public landing");
    }

    @GetMapping("/private")
    public Mono<String> privatePage() {
        return Mono.just("private content");
    }

    @GetMapping("/home")
    public Mono<String> home() {
        return ReactiveSecurityContextHolder.getContext()
            .map(context -> context.getAuthentication().getName())
            .map(name -> "signed in as " + name);
    }
}
```

`/home` cần authentication trước khi được gọi. Với OIDC, `Authentication.getName()` thường là một stable principal identifier, không phải luôn email hoặc display name; đừng giả định name có role hay email đã xác minh.

### 7.7. Chạy demo

Tại root project:

```bash
./gradlew bootRun
```

Windows PowerShell:

```powershell
.\gradlew.bat bootRun
```

Mở:

```text
http://localhost:8080/
http://localhost:8080/signin
http://localhost:8080/private
```

Dự kiến:

- `GET /`: HTTP 200, `public landing`.
- `GET /signin`: HTTP 200 HTML có hai links Alpha và Beta.
- `GET /private`: anonymous nhận redirect về `/signin`.
- `GET /oauth2/authorization/alpha`: HTTP 302 đến fake authorization endpoint `https://login.alpha.example.test/authorize`, chứa `client_id`, `response_type=code`, `redirect_uri` và `state` theo flow. Browser follow link sẽ gặp IdP không tồn tại: **đây là giới hạn có chủ ý của demo offline**.
- `GET /home` trước login: redirect về `/signin`.
- Không có callback thành công hợp lệ nếu chưa thay IdP demo bằng thật.

Xem redirect đầu tiên mà **không tự follow IdP**:

```bash
curl -i http://localhost:8080/oauth2/authorization/alpha
```

Response dự kiến có một `Location` tới `https://login.alpha.example.test/authorize?...`; các query parameters được encode, `state` thay đổi mỗi lần, và app có thể đặt cookie session. **Không** copy `state`/`code` từ môi trường production vào log công khai.

## 8. Test WebTestClient: trang chọn nhà cung cấp và authorize redirect

File `src/test/java/demo/oauthlogin/OAuthLoginWebTests.java`:

```java
package demo.oauthlogin;

import java.net.URI;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.HttpHeaders;
import org.springframework.test.web.reactive.server.WebTestClient;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertTrue;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
@AutoConfigureWebTestClient
class OAuthLoginWebTests {

    @Autowired
    WebTestClient client;

    @Test
    void publicLandingWorks() {
        client.get().uri("/")
            .exchange()
            .expectStatus().isOk()
            .expectBody(String.class)
            .isEqualTo("public landing");
    }

    @Test
    void providerPageContainsOnlyConfiguredChoices() {
        client.get().uri("/signin")
            .exchange()
            .expectStatus().isOk()
            .expectBody(String.class)
            .value(html -> {
                assertTrue(html.contains(
                    "/oauth2/authorization/alpha"));
                assertTrue(html.contains(
                    "/oauth2/authorization/beta"));
                assertTrue(html.contains("Alpha Identity"));
                assertTrue(html.contains("Beta Identity"));
                assertFalse(html.contains("not-a-real-secret"));
            });
    }

    @Test
    void errorPageUsesGenericTextNotProviderDetails() {
        client.get()
            .uri("/signin?error=oauth2&error_description=SECRET_DEBUG")
            .exchange()
            .expectStatus().isOk()
            .expectBody(String.class)
            .value(html -> {
                assertTrue(html.contains(
                    "Không thể hoàn tất đăng nhập"));
                assertFalse(html.contains("SECRET_DEBUG"));
            });
    }

    @Test
    void anonymousPrivatePageRedirectsToProviderPage() {
        var result = client.get().uri("/private")
            .exchange()
            .expectStatus().is3xxRedirection()
            .returnResult(Void.class);

        URI location = result.getResponseHeaders().getLocation();
        assertNotNull(location);
        assertEquals("/signin", location.getPath());
    }

    @Test
    void authorizationLinkRedirectsToProviderWithState() {
        var result = client.get()
            .uri("/oauth2/authorization/alpha")
            .exchange()
            .expectStatus().is3xxRedirection()
            .expectHeader().exists(HttpHeaders.LOCATION)
            .returnResult(Void.class);

        URI location = result.getResponseHeaders().getLocation();
        assertNotNull(location);
        assertEquals("login.alpha.example.test", location.getHost());

        String query = location.getRawQuery();
        assertNotNull(query);
        assertTrue(query.contains("response_type=code"));
        assertTrue(query.contains("client_id="));
        assertTrue(query.contains("redirect_uri="));
        assertTrue(query.contains("state="));
    }

    @Test
    void secondProviderHasDifferentAuthorizationHost() {
        var result = client.get()
            .uri("/oauth2/authorization/beta")
            .exchange()
            .expectStatus().is3xxRedirection()
            .returnResult(Void.class);

        URI location = result.getResponseHeaders().getLocation();
        assertNotNull(location);
        assertEquals("login.beta.example.test", location.getHost());
    }

    @Test
    void homeRequiresRealAuthentication() {
        var result = client.get().uri("/home")
            .exchange()
            .expectStatus().is3xxRedirection()
            .returnResult(Void.class);

        URI location = result.getResponseHeaders().getLocation();
        assertNotNull(location);
        assertEquals("/signin", location.getPath());
    }
}
```

**7 integration test methods** kiểm tra UI/login entry point/authorization initiation. `WebTestClient` không tự follow redirect tới `.example.test`, vì vậy **không cần DNS/IdP thật** để xác minh bước tạo authorization request. Nó cũng **không chứng minh** một callback OIDC đã thành công: muốn điều đó cần fake IdP được thiết kế cho test hoặc provider thật với test account.

### 8.1. Vì sao không gọi callback với code tự bịa để test login success?

Sai về tư duy:

```http
GET /login/oauth2/code/alpha?code=fake&state=fake
```

Không có authorization request được lưu tương ứng, code không thể đổi thành token hợp lệ và ID token không thể được xác minh. Spring Security phải từ chối. Nếu một test muốn `GET callback?code=fake` trả authenticated success, tức là test đang **bypass hoặc mock quá sâu** việc xác thực. Test success redirect nên được kiểm tra riêng với handler, còn full callback cần IdP test có authorization/token/JWK responses hợp lệ và state/nonce/PKCE nhất quán.

### 8.2. Test giá trị Location không phải giá trị state cố định

Random `state` không được hardcode trong assertion. Test chỉ cần xác minh redirect có state, scheme/host đúng và URL không có credential lộ. Muốn kiểm tra tính không lặp có thể so hai requests nhưng cần tránh các test xác suất không cần thiết. Test business của callback phải kiểm tra negative paths về state mismatch/replay và không làm giả signed token vô hiệu.

## 9. Unit tests: tách handler redirect khỏi IdP

Để test success/failure handler mà không cần token thật, ta gọi contract `ServerAuthenticationSuccessHandler` và `ServerAuthenticationFailureHandler` **trực tiếp** với mock exchange. Đây là test hành vi **redirect-only**, không kiểm tra token exchange, state, hay OIDC signature.

File `src/test/java/demo/oauthlogin/LoginRedirectHandlerTests.java`:

```java
package demo.oauthlogin;

import java.net.URI;
import org.junit.jupiter.api.Test;
import org.springframework.http.HttpStatus;
import org.springframework.mock.http.server.reactive.MockServerHttpRequest;
import org.springframework.mock.web.server.MockServerWebExchange;
import org.springframework.security.authentication.BadCredentialsException;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.authority.AuthorityUtils;
import org.springframework.security.web.server.WebFilterExchange;
import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;

class LoginRedirectHandlerTests {

    private MockServerWebExchange exchange() {
        return MockServerWebExchange.from(
            MockServerHttpRequest
                .get("/login/oauth2/code/alpha").build());
    }

    private WebFilterExchange bridge(MockServerWebExchange exchange) {
        return new WebFilterExchange(
            exchange,
            next -> Mono.empty()
        );
    }

    @Test
    void successHandlerRedirectsToFallbackHome() {
        MockServerWebExchange exchange = exchange();
        Authentication authentication =
            UsernamePasswordAuthenticationToken.authenticated(
                "test-subject",
                "not-used",
                AuthorityUtils.createAuthorityList("ROLE_USER"));

        StepVerifier.create(
                LoginRedirects.success().onAuthenticationSuccess(
                    bridge(exchange), authentication))
            .verifyComplete();

        assertEquals(HttpStatus.FOUND,
            exchange.getResponse().getStatusCode());

        URI location = exchange.getResponse()
            .getHeaders().getLocation();
        assertNotNull(location);
        assertEquals("/home", location.getPath());
    }

    @Test
    void failureHandlerRedirectsWithGenericCodeOnly() {
        MockServerWebExchange exchange = exchange();

        StepVerifier.create(
                LoginRedirects.failure().onAuthenticationFailure(
                    bridge(exchange),
                    new BadCredentialsException(
                        "internal-details-not-for-browser")))
            .verifyComplete();

        assertEquals(HttpStatus.FOUND,
            exchange.getResponse().getStatusCode());

        URI location = exchange.getResponse()
            .getHeaders().getLocation();
        assertNotNull(location);
        assertEquals("/signin", location.getPath());
        assertEquals("error=oauth2", location.getRawQuery());
    }
}
```

`WebFilterExchange` nhận `ServerWebExchange` và một `WebFilterChain`. Lambda `next -> Mono.empty()` chỉ là một chain rỗng cho unit test. `Authentication` được test dựng để gọi **success handler**, không phải một kết quả IdP hợp lệ: test này **không được tính là đã xác minh OIDC**.

Trong một request thật có saved request, success handler có thể redirect theo request cache thay vì fallback `/home`. Unit test dùng exchange không có saved request nên kỳ vọng `/home` là hợp lý. Việc test saved-request redirect cần thêm test session/request cache hoặc full OIDC flow.

Run tests:

```bash
./gradlew test
```

Windows PowerShell:

```powershell
.\gradlew.bat test
```

Project định nghĩa **9 test methods** (7 WebTestClient + 2 handler unit). Đây là **kỳ vọng từ mã và API Spring Security 6.5**, không phải tuyên bố đã chạy Gradle trong workspace người học. Nếu một assertion về redirect status/location khác do framework/redirect strategy, đọc actual response và Javadoc version đang chạy rồi kiểm tra, không bỏ bảo vệ chỉ để test xanh.

## 10. Gắn IdP thật để kiểm thử end-to-end

Demo trên có thể chạy offline vì chỉ test **bắt đầu login và handlers**. Để có callback thực sự:

1. Tạo ứng dụng **Confidential Web Client** với provider OIDC tin cậy; đăng ký callback external URL dạng `https://app.example/login/oauth2/code/alpha`.
2. Thay `authorizationUri`, `tokenUri`, `jwkSetUri`, `userInfoUri`/issuer metadata bằng endpoint của IdP thật. Không dùng domain `.example.test`.
3. Đặt `clientId` và `clientSecret` ở secret manager hoặc environment, không commit vào source. Kiểm tra auth method provider hỗ trợ (`client_secret_basic`, `client_secret_post` hoặc cơ chế khác theo policy).
4. Bảo đảm scope `openid` cho OIDC; yêu cầu scopes tối thiểu. Xác minh signature, issuer, audience, nonce, expiry với framework thay vì tự parse JWT.
5. Cấu hình HTTPS/proxy/forwarded headers đúng và đảm bảo IdP redirect URI match chính xác.
6. Chạy flow từ browser: `GET /private` → `/signin` → IdP → callback → trang protected trở lại.
7. Sau login, gọi request thứ hai **chỉ với session cookie**, không cần code/token trong URL, xác minh Authentication vẫn còn hiệu lực.
8. Test user hủy consent (`access_denied`), state mismatch, cookie bị xóa, code replay, token endpoint lỗi, ID token invalid, provider unavailable.
9. Test nhiều account/tenant: chọn provider khác, logout/login lại, đổi user, email chưa verified, identity linking; tuyệt đối không tự nối account dựa vào email chưa tin cậy.
10. Quan sát logout/session expiry và session ID rotation; với nhiều replicas, dùng shared session store phù hợp hoặc chiến lược state đáng tin.

### 10.1. Kiểm thử với một IdP giả lập nghiêm túc

Một test IdP hợp lệ phải có khả năng:
- Trả 302 authorization response có đúng `state` nhận từ authorization request.
- Phát authorization code một lần, gắn đúng client, redirect URI và PKCE khi áp dụng.
- Tại token endpoint, chấp nhận client authentication hợp lệ và code đúng; từ chối code giả, mã đã dùng hoặc code verifier sai.
- Trả signed ID token có `iss`, `aud`, `sub`, `exp`, `iat` và `nonce` khi flow yêu cầu, kèm JWKS public keys.
- Thực hiện rotation JWK và negative tests (wrong key/kid, stale exp, wrong issuer/audience, nonce mismatch).
- Cho Spring Security callback filter đi qua full path, không ép Authentication thành success bằng mockUser.

Các framework test như WireMock/MockWebServer có thể làm HTTP endpoints; phần generate JWT ký cho IdP test cần thư viện phù hợp và quản lý key test riêng. Không tái sử dụng HMAC secret production trong test, và không ký token giả rồi triển khai như IdP thực.

### 10.2. Error callback từ IdP

Một response lỗi có thể có dạng:

```http
GET /login/oauth2/code/alpha?error=access_denied&state=... HTTP/1.1
Host: app.example
Cookie: SESSION=<cookie-from-initiation>
```

Đây là **minh họa**. Khi matched callback được authentication pipeline xử lý như một thất bại, failure handler của `oauth2Login` có thể redirect người dùng tới `/signin?error=oauth2`. Đừng phản chiếu `error_description` lên UI hoặc ghi code/state raw vào log. Nếu không có matching saved authorization request hoặc callback không được filter nhận, outcome có thể khác; test riêng và đảm bảo fail closed.

### 10.3. Callback bảo vệ và login CSRF

`state` liên kết OAuth2 authorization response với phiên/authorization request đã tạo trước, nhưng **không thay thế CSRF protection cho các POST business endpoints của ứng dụng**. Cookie-based browser webapp vẫn cần CSRF token theo threat model khi thay đổi trạng thái.

`PKCE` làm giảm rủi ro đánh cắp authorization code bằng cách ràng buộc code vào verifier; với public clients là cơ chế bắt buộc trong nhiều cấu hình hiện đại. `nonce` trong OIDC giúp ràng buộc ID token với authentication request; không có nghĩa sẽ luôn xuất hiện với tất cả providers hoặc OAuth2 (không OIDC). Đừng tự xoá state/PKCE/nonce checks khi thấy callback lỗi.

## 11. Bảo mật nội dung trang login và handler lỗi

### 11.1. Chỉ dùng thông báo công khai được allowlist

Ví dụ query:

```text
/signin?error=oauth2
```

Chỉ render một message static:

```text
Không thể hoàn tất đăng nhập. Vui lòng thử lại hoặc liên hệ hỗ trợ.
```

Không hiển thị:
- Raw query `code` / `state` / `id_token` / `access_token`.
- `AuthenticationException.getMessage()` hay stacktrace.
- Nội dung `error_description` nguyên từ IdP.
- `clientSecret`, token endpoint response body, JWT/JWK private material.
- Email/claims nhạy cảm hoặc internal tenant mapping.

Một trang lỗi có thể nhận query do attacker tùy ý nhập; nếu render raw query không escape sẽ có nguy cơ reflected XSS và phishing. Thông báo generic giữ UX vừa đủ và giảm lộ cơ chế nội bộ.

### 11.2. Logging và correlation IDs

Ghi metrics có kiểm soát: provider ID thuộc allowlist, error category chuẩn hóa, HTTP status, latency, correlation ID nội bộ, giai đoạn initiation/callback/success/failure. Không ghi raw code, state, Authorization header, Cookie, refresh token, ID token, clientSecret hoặc exception message chứa dữ liệu nhạy cảm.

Một dashboard hữu ích:
- Số lượt bấm Alpha/Beta.
- Tỷ lệ redirect tới IdP và callback về.
- Tỷ lệ success, cancellation, state mismatch, token endpoint error.
- p95/p99 thời gian callback.
- Tỷ lệ login-loop và session/cookie bị mất.
- Tỷ lệ IdP unavailable và token validation failures.

Không dùng mỗi `error=oauth2` trên URL công khai làm nguồn audit đủ tin cậy vì user có thể tự nhập nó.

### 11.3. Chặn provider poisoning và open redirects

Không làm:

```java
// Ví dụ thiết kế SAI, không dùng trong ứng dụng thật:
String providerUrl = request.getQueryParams()
    .getFirst("providerUrl");
response.getHeaders().setLocation(URI.create(providerUrl));
```

Đây là snippet lỗi, không phải class đầy đủ. Nó có nguy cơ đưa user đến endpoint giả do attacker điều khiển. Provider phải đến từ `ClientRegistration` trusted, registrationId cần được validate/allowlist. Tương tự, đừng tự nhận `redirect_uri` do browser gửi trong callback rồi chấp nhận tùy ý.

### 11.4. Cookie, SameSite, HTTPS và multi-node

Authorization request thường được lưu trong WebSession. Cookie của session khởi tạo phải trở lại trên callback. Cần kiểm tra:
- `Secure`/`HttpOnly`/`SameSite`, domain/path của cookie phù hợp.
- Browser callback top-level GET vs form POST, cross-site context.
- TLS termination và forwarded host/proto đáng tin.
- Session store distributed khi nhiều replicas.
- Session fixation protection/rotation sau auth.
- Timeout và cleanup request đã dùng.
- Những lần login đồng thời ở nhiều tab và xử lý login lại khi user đổi account.

Không đặt authorization request hoặc token vào global static map không có TTL/tenant isolation chỉ để tránh session.

### 11.5. Không cho phép login loops

Một lỗi điển hình:

```text
GET /private -> 302 /signin
GET /signin  -> lại bị .authenticated() -> 302 /signin
... lặp mãi
```

Sửa bằng `permitAll` cho custom login page, authorization initiation endpoint và các tài nguyên cần để hiển thị trang. Nhưng **không** mở `/home` hay các resource nhạy cảm. Test với browser không login và không dùng cookie.

## 12. Phân biệt ba loại điều hướng sau login

| Loại | Trigger | Đích thường gặp | Điều cần kiểm tra |
|---|---|---|---|
| Entry point | Request protected khi anonymous | `/signin` | `/signin` được permit, không login loop |
| Authorization request redirect | User bấm provider | IdP `/authorize` URL | registrationId trusted, state/redirectUri/PKCE |
| Callback success redirect | Authentication thành công | Saved request hoặc `/home` | Redirect local, Authentication persist, không lộ code |
| Callback failure redirect | Authentication attempt thất bại | `/signin?error=oauth2` | Generic message, không echo raw error/token |

Một HTTP 302 xuất hiện ở **cả bốn tình huống**. Đừng coi một test `expectStatus().is3xxRedirection()` là chứng minh login thành công: phải kiểm tra `Location` và, đối với callback success thật, request sau đã authenticated.

## 13. Lỗi thực tế và cách chẩn đoán

| Triệu chứng | Nguyên nhân thường gặp | Hướng giải quyết |
|---|---|---|
| Trang chọn provider không hiện danh sách | Repository custom không implement Iterable hoặc controller không lấy đúng registrations | Dùng source danh sách trusted, kiểm tra `ReactiveClientRegistrationRepository` |
| Click Alpha nhưng không tới IdP | Link sai base path hoặc matcher bị đổi | So `/oauth2/authorization/{registrationId}` với `ServerOAuth2AuthorizationRequestResolver` |
| IdP báo redirect_uri_mismatch | External baseUrl khác HTTPS/host/port/context path đã đăng ký | So callback URI, proxy config và registration |
| Callback về 404 | `authenticationMatcher` không match, callback path/context path khác | Đồng bộ matcher và redirectUri |
| Callback báo state invalid | Cookie session mất, timeout, saved request không còn, login song song | Debug session continuity; **không tắt state** |
| User hủy login nhưng thấy 500 | Error path/handler chưa xử lý callback error đúng | Kiểm tra loại lỗi, chain và generic failure redirect |
| IdP/token endpoint timeout | Network/TLS/proxy/client config | Timeout, alerting, retry login ở UI an toàn |
| Login trả 302 nhưng user vẫn anonymous | Security context save/load khác repo hoặc mất cookie | Kiểm tra WebSession/securityContextRepository |
| User quay về `/home` thay vì URL gốc | Không cache saved request, handler cấu hình no-op hoặc request không thuộc rule | Kiểm tra request cache/fallback semantics |
| User quay về URL ngoài attacker | Success handler tin returnUrl/query | Allowlist local path, không dùng raw input |
| Lỗi redirect vòng lặp | Trang login không permit hoặc entry point áp dụng trên nó | Permit `GET /signin` và static assets |
| 302 tới /login?error thay vì /signin | Chưa custom OAuth2 failure handler | `authenticationFailureHandler` với generic target |
| Raw error_description lộ lên HTML | Controller echo query/exceptions | Static generic message, HTML escaping, log redaction |
| Đăng nhập IdP rồi role ứng dụng sai | Giả định scopes/email = application roles | Map authorities/ACL từ nguồn đáng tin |
| Email giống nhau từ hai IdP bị gộp tài khoản | Link bằng email không kiểm tra issuer/sub/email_verified | Identity mapping `iss + sub` và chính sách account linking |
| Callback hoạt động một pod nhưng fail khi scale | Authorization request chỉ nằm WebSession local | Shared session store / distributed strategy |
| CORS lỗi khi IdP redirect browser | Nhầm OAuth2 top-level navigation với browser API CORS | Kiểm tra callback URL/cookie/matcher; CORS chủ yếu cho fetch |
| Logout rồi callback cũ thành công | Authorization request/session cleanup chưa rõ, replay handling | Test state invalidation và code replay |
| Tests mockUser pass nhưng OIDC thật fail | Đã bỏ qua signature/token/state/cookie flow | Test với IdP thật hoặc fake có token/JWKS hợp lệ |
| Success handler thay mất session registration handler | Setter single-handler clear list success handlers | Kiểm tra overload list, session concurrency và OIDC registry |
| Debug log chứa code/token | Log raw callback query hoặc exception body | Redact, không ghi secret |

### 13.1. Checklist debug theo thứ tự

1. Xác nhận **Spring WebFlux** đang xử lý inbound HTTP, không phải MVC/Servlet.
2. Kiểm tra `/signin` có trả 200, không redirect loop.
3. Kiểm tra links dùng registration IDs thực và server-allowlisted.
4. Kiểm tra `GET /oauth2/authorization/{registrationId}` trả 302 đúng IdP với `state`.
5. Quan sát cookie được lưu khi initiate login; không ghi cookie vào log.
6. Kiểm tra IdP registered redirect URI khớp external HTTPS URL.
7. Xem callback có tới Spring app hay bị proxy/gateway/404/chain khác chặn.
8. Kiểm tra saved authorization request/state theo session, không expose raw state ra UI/log.
9. Xem token exchange/OIDC signature validation và user info theo error category.
10. Kiểm tra success/failure handler có chạy, `Location` cuối cùng là gì.
11. Kiểm tra request protected sau login **chỉ với cookie** còn authenticated.
12. Kiểm tra logout, session expiry và multi-node sticky/shared store.

## 14. Bài tập có đáp án

### Bài 1 — Trang chọn nhà cung cấp và entry point

Người dùng chưa đăng nhập mở `/private`; ứng dụng có hai provider Alpha và Beta. Vì sao nên redirect tới `/signin` thay vì tự động tới Alpha?

**Đáp án:** Vì product cho phép chọn nhà cung cấp. `RedirectServerAuthenticationEntryPoint("/signin")` đưa user tới trang chọn; trang cung cấp links `/oauth2/authorization/alpha` và `.../beta`. Tự động redirect Alpha có thể không phù hợp tenant và làm user không thể chọn account khác.

### Bài 2 — Có phải mọi redirect 302 đều là login success?

**Đáp án:** Không. Có 302 khi anonymous được đưa tới trang chọn, khi bắt đầu OAuth2 tới IdP, khi callback thành công và khi callback thất bại. Phải xem `Location` và session state sau callback.

### Bài 3 — Vì sao login page không hiện provider?

Một custom `ReactiveClientRegistrationRepository` chỉ implement `findByRegistrationId`, nhưng generated login page không hiện links. Vì sao?

**Đáp án:** `LoginPageGeneratingWebFilter` cần khả năng liệt kê registrations thông qua `Iterable<ClientRegistration>` để render links. Dùng implementation phù hợp hoặc custom page lấy provider list từ nguồn server đáng tin riêng.

### Bài 4 — Callback state không khớp

Browser bắt đầu login với session A rồi callback mang cookie phiên B. Có nên bỏ `state` validation cho callback đi qua?

**Đáp án:** Không. `state` correlation bảo vệ against login injection/CSRF và phản hồi không cùng authorization request. Sửa session cookie, timeout, SameSite, proxy và store, không bỏ kiểm tra.

### Bài 5 — User hủy ở IdP

IdP trả `error=access_denied`. Trang custom nên hiển thị gì?

**Đáp án:** Message chung như “Không thể hoàn tất đăng nhập, vui lòng thử lại”. Không hiển thị raw `error_description`/trace/code/state; thông tin debug nằm trong logs có redaction và access control.

### Bài 6 — RedirectServerAuthenticationSuccessHandler có luôn về /home không?

Handler dùng constructor `("/home")` nhưng người dùng vẫn về `/private`. Có phải handler lỗi?

**Đáp án:** Không nhất thiết. Success handler có thể ưu tiên saved request trong request cache trước, và chỉ dùng `/home` như fallback. Nếu muốn luôn về /home, phải chủ ý thay request-cache behavior và chấp nhận mất saved-navigation UX.

### Bài 7 — Thay redirect URI ở IdP

IdP đăng ký `https://app.example/auth/callback/alpha` nhưng `ClientRegistration.redirectUri` vẫn `{baseUrl}/login/oauth2/code/{registrationId}`. Outcome?

**Đáp án:** Redirect mismatch hoặc callback không match authentication filter. Phải đồng bộ registration, callback matcher và IdP setting; test external URL thật qua proxy.

### Bài 8 — Có thể đưa client secret lên provider page để IdP biết đăng nhập không?

**Đáp án:** Không. Link provider chỉ cần local authorization initiation URL. OAuth2 client secret thuộc server/secret manager, không nằm trong HTML, JS, URL hay browser logs.

### Bài 9 — Không có IdP thật, test được những gì?

**Đáp án:** Có thể test `/signin`, provider allowlist, link URLs, redirect initiation có state, entry point, success/failure handler redirect độc lập. Không thể kết luận token exchange/ID token validation/callback session thực đã thành công nếu không có IdP thực hoặc fake IdP đúng protocol.

### Bài 10 — Email claim làm username và account linking

Hai IdP trả cùng email cho hai người khác nhau. Có thể dùng email để tự gộp account không?

**Đáp án:** Không. Phải dùng identity key đáng tin như issuer + subject và một quy trình account linking có xác minh. `email_verified` (nếu có) không tự thay thế quyền cho việc gộp tài khoản hay cấp role.

### Bài 11 — Success handler custom và Open Redirect

Ứng dụng nhận `?next=https://evil.example` rồi redirect y nguyên sau login. Vấn đề gì?

**Đáp án:** Open redirect/phishing và có thể lộ thông tin. Dùng fallback local path, request cache đáng tin hoặc allowlist target, normalize URI, không cho external scheme/host do user nhập.

### Bài 12 — Sự khác biệt giữa OAuth2 Login và Resource Server

Website đang dùng `oauth2ResourceServer().jwt()` để kiểm tra Bearer. Vì sao không tự có trang chọn provider?

**Đáp án:** Resource Server xác thực access token gửi đến API, không tự thực hiện browser authorization code login. Cần cấu hình `oauth2Login` và `ReactiveClientRegistrationRepository` cho website login.

### Bài 13 — Missing cookie trên callback

User login thành công ở IdP nhưng callback báo “invalid state”. Nguyên nhân đáng kiểm tra đầu tiên là gì?

**Đáp án:** Kiểm tra session cookie từ initiation còn được gửi lại callback không, timeout, browser SameSite, session store multi-node, redirect scheme/host và logic request repository. Không nhập code/state thủ công.

### Bài 14 — Custom success handler có làm mất hành vi session khác không?

**Đáp án:** Có thể nếu sử dụng overload setter thay thế handlers trong cấu hình tích hợp nhiều thành phần. Review Javadoc `authenticationSuccessHandler(...)`, handler list của phiên bản đang chạy, session registration, OIDC session registry và integration test.

### Bài 15 — Lỗi provider không phản hồi

User click Alpha, browser không thể mở hostname IdP; backend failure handler có chắc được gọi không?

**Đáp án:** Không. Nếu browser chưa quay về callback của ứng dụng, authentication filter không có failure event từ request đó. UI và monitoring cần xử lý IdP unavailable ở cấp product/network.

## 15. Checklist triển khai production

- [ ] Dùng `ServerHttpSecurity`/`SecurityWebFilterChain` và `oauth2Login` đúng reactive stack.
- [ ] Có `ReactiveClientRegistrationRepository` với registration IDs, issuer/endpoints và credentials hợp lệ.
- [ ] Client secret nằm trong secret manager/env, không trong source/HTML/log/URL.
- [ ] Provider selection page lấy danh sách trusted, escaped HTML, allowlisted registration ID.
- [ ] Custom `/signin` và assets được phép truy cập anonymous, không redirect loop.
- [ ] Link tới `/oauth2/authorization/{registrationId}` khớp resolver/matcher.
- [ ] Callback `/login/oauth2/code/{registrationId}` khớp registration và IdP URI chính xác.
- [ ] `state`/PKCE/OIDC nonce/signature/issuer/audience/expiry validation không bị bypass.
- [ ] WebSession authorization request tồn tại từ initiation đến callback, kiểm tra cookies/SameSite và distributed store.
- [ ] Success redirect dùng local allowlist, không tin raw `next`/`redirect_uri` query.
- [ ] Saved request vs fallback `/home` behavior được chủ ý chọn và test.
- [ ] Failure redirect cố định, không echo `error_description`/`code`/`state`/exception message.
- [ ] 401 anonymous, 403 thiếu quyền, success/failure callbacks phân biệt rõ.
- [ ] Với OIDC, account mapping dùng issuer + subject và kiểm tra claim cần thiết.
- [ ] HTTPS/TLS/proxy/forwarded headers được cấu hình từ nguồn đáng tin.
- [ ] Security context read/save sau login nhất quán và test request sau chỉ với cookie.
- [ ] Không tự `block()`/`subscribe()` trong custom reactive success/failure handlers.
- [ ] Logs, traces, analytics redacted không chứa tokens, client secrets, session cookies.
- [ ] Browser tests cho logout, expired session, provider cancellation, callback replay.
- [ ] Test full OIDC bằng IdP thật/fake đúng chuẩn, không xem mockUser là chứng minh login.
- [ ] Review overload success handler khi thêm session concurrency/session registry.
- [ ] Rate limiting, security headers, CSRF trên POST của app và chống XSS ở trang login.

## 16. Tóm tắt nhanh

```text
CHỌN IDP:
  GET /signin
  -> local link /oauth2/authorization/alpha | /beta

BẮT ĐẦU LOGIN:
  OAuth2AuthorizationRequestRedirectWebFilter
  -> trusted ClientRegistration
  -> random state, authorization request repository (WebSession)
  -> 302 tới IdP

CALLBACK:
  GET /login/oauth2/code/{registrationId}
  -> state correlation + code exchange
  -> với OIDC: verify ID token và claims
  |
  +-- SUCCESS
  |    -> persist Authentication
  |    -> ServerAuthenticationSuccessHandler
  |    -> saved request hoặc /home
  |
  +-- FAILURE
       -> ServerAuthenticationFailureHandler
       -> /signin?error=oauth2 (generic)

ANONYMOUS:
  RedirectServerAuthenticationEntryPoint("/signin")

PHÂN BIỆT:
  entry point != OAuth callback failure handler
  302 authorization redirect != login thành công
  success handler redirect != token verification
  Provider UI link != client secret hoặc issuer validation
  state != CSRF token cho mọi POST của ứng dụng
  fake IdP redirect test != end-to-end OIDC login
```

**Bài học cốt lõi:** Hãy phân tách **chọn nhà cung cấp**, **bắt đầu OAuth2 authorization**, **nhận và xác thực callback**, và **điều hướng UI sau success/failure**. Spring Security Reactive đã có các filter/handler tương ứng. Tùy biến nên tập trung trải nghiệm, redirect an toàn và kiểm thử, **không thay/bỏ** các kiểm tra state, token hoặc identity được framework bảo vệ.

## 17. Tài liệu chính thức

- [Spring Security 6.5 — OAuth2 Login Core Configuration](https://docs.spring.io/spring-security/reference/6.5/reactive/oauth2/login/core.html)
- [Spring Security — Reactive OAuth2 Login Advanced Configuration](https://docs.spring.io/spring-security/reference/reactive/oauth2/login/advanced.html)
- [Spring Security — Reactive OAuth2 Authorization Code](https://docs.spring.io/spring-security/reference/reactive/oauth2/client/authorization-grants.html)
- [Spring Security 6.5 — ServerHttpSecurity.OAuth2LoginSpec API](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/config/web/server/ServerHttpSecurity.OAuth2LoginSpec.html)
- [Spring Security 6.5 — RedirectServerAuthenticationSuccessHandler API](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/web/server/authentication/RedirectServerAuthenticationSuccessHandler.html)
- [Spring Security 6.5 — RedirectServerAuthenticationFailureHandler API](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/web/server/authentication/RedirectServerAuthenticationFailureHandler.html)
- [Spring Security 6.5 — RedirectServerAuthenticationEntryPoint API](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/web/server/authentication/RedirectServerAuthenticationEntryPoint.html)
- [Spring Security — InMemoryReactiveClientRegistrationRepository API](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/oauth2/client/registration/InMemoryReactiveClientRegistrationRepository.html)
- [Spring Security — WebSessionOAuth2ServerAuthorizationRequestRepository API](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/oauth2/client/web/server/WebSessionOAuth2ServerAuthorizationRequestRepository.html)
- [Spring Security — OAuth2 Client and Login Overview](https://docs.spring.io/spring-security/reference/reactive/oauth2/)
- [OpenID Connect Core 1.0](https://openid.net/specs/openid-connect-core-1_0.html)
- [OAuth 2.0 Security Best Current Practice (RFC 9700)](https://www.rfc-editor.org/rfc/rfc9700.html)
- [OAuth 2.0 PKCE (RFC 7636)](https://www.rfc-editor.org/rfc/rfc7636)
- [OWASP — OAuth2 Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/OAuth2_Cheat_Sheet.html)
