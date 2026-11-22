# CSRF dựa trên cách trình duyệt gửi thông tin xác thực

Trong **Spring Security OAuth 2.0/OIDC Resource Server**, việc một API có cần CSRF protection không **không thể quyết định chỉ bằng câu “API dùng JWT”, “stateless” hay “đã bật CORS”**. Câu hỏi quan trọng hơn là:

> **Trình duyệt có tự động đính kèm credential mà server chấp nhận khi một trang khác khiến nó gửi request không?**

Nếu browser có session cookie, JWT cookie, thông tin HTTP Basic được ghi nhớ hoặc credential khác được browser tự gửi, attacker có thể lợi dụng một request không có chủ đích của người dùng. Nếu Resource Server chỉ nhận access token trong **Authorization: Bearer** do mã JavaScript đáng tin cậy hoặc non-browser client **chủ động** đính kèm, còn browser không tự gửi loại credential nào khác được API chấp nhận, mô hình CSRF truyền thống thường không áp dụng theo cùng cách.

**CSRF là vấn đề về hành vi gửi credential và ranh giới tin cậy**, không phải chỉ về token là JWT hay opaque. Bài học này phân tích browser/session, cookie, SPA, BFF, OAuth2 Login, Spring Security CSRF filter, cách cấu hình và kiểm thử để lựa chọn policy đúng cho từng kiến trúc.

## 1. CSRF khai thác điều gì?

**Cross-Site Request Forgery (CSRF)** xảy ra khi một trang không đáng tin khiến browser của người dùng gửi request đến một hệ thống mà người dùng đã đăng nhập, trong khi server xử lý request đó dưới danh tính người dùng dù hành động không do họ chủ ý thực hiện.

Giả sử người dùng đang đăng nhập vào **https://shop.example.com**, và server cấp cookie:

~~~http
Set-Cookie: JSESSIONID=session-abc; Path=/; Secure; HttpOnly; SameSite=None
~~~

Một trang khác có thể chứa form:

~~~html
<form action="https://shop.example.com/account/email"
      method="POST">
  <input name="newEmail" value="example@attacker.example">
  <button type="submit">Continue</button>
</form>
~~~

HTML này minh họa cơ chế ở môi trường học tập. Khi người dùng gửi form, browser có thể gửi request đến Shop và **tự thêm JSESSIONID** nếu cookie policy cho phép. Nếu server chỉ dựa vào session cookie để xác thực, không kiểm nguồn/csrf token và chấp nhận dữ liệu form, thao tác có thể xảy ra dưới danh tính nạn nhân.

Attacker **không cần biết giá trị cookie**. Chính browser đã tự gửi credential.

~~~mermaid
sequenceDiagram
    participant U as Người dùng
    participant B as Trình duyệt
    participant S as Shop API
    participant X as Trang không đáng tin
    U->>B: Đăng nhập Shop
    B->>S: POST login hợp lệ
    S-->>B: Set-Cookie session
    U->>B: Mở trang bên ngoài
    B->>X: Tải nội dung
    X-->>B: Form/action hướng tới Shop
    B->>S: POST + session cookie nếu chính sách cho phép
    Note over S: Không có CSRF protection
    S-->>B: Cập nhật dữ liệu bằng quyền người dùng
~~~

Một vụ CSRF cần đồng thời có điều kiện browser gửi credential và server chấp nhận request gây tác động. **SameSite**, yêu cầu token và kiểm request origin có thể chặn các mắt xích này. Tuy nhiên không nên giả định browser luôn gửi cookie: cần xét **SameSite**, cookie domain/path, loại navigation, credentials mode và các chính sách browser.

### 1.1. Same-Origin Policy không tự chặn mọi CSRF

Same-Origin Policy thường ngăn script của trang khác **đọc response** từ Shop. Nhưng **việc không đọc được response khác với việc không gửi được request**. Browser vẫn có thể thực hiện cross-origin form submission hoặc những request khác trong các điều kiện nhất định.

Vì vậy, một request có thể gây thay đổi dữ liệu **ngay cả khi attacker không đọc được JSON phản hồi**.

## 2. Vì sao cách browser gửi credential quan trọng hơn tên token?

Hãy phân biệt hai kiểu credential transmission:

**Credential tự động (ambient credential):** browser quản lý cookie hoặc cơ chế xác thực và tự gửi nó khi request khớp điều kiện. Trang attacker không cần truy cập giá trị credential để khiến browser gửi request.

**Credential được client chủ động đính kèm:** mã JavaScript ứng dụng, native client, CLI hoặc backend tự đặt một header chứa token. Browser không tự lấy token nằm trong biến JavaScript của một origin rồi thêm vào form cross-site của origin khác.

| Kiến trúc | Browser tự gửi credential khi request phù hợp? | Cần xét CSRF? |
|---|---|---|
| Web app đăng nhập bằng **JSESSIONID** | Có, tùy cookie policy | **Có** |
| JWT được lưu trong **HttpOnly cookie**, API tự đọc cookie | Có | **Có** |
| BFF dùng session cookie, giữ OAuth tokens tại server | Có | **Có**, tại browser → BFF |
| OAuth2 Login rồi dùng session cookie cho nghiệp vụ | Có | **Có** |
| Refresh token cookie và endpoint refresh dùng cookie | Có | **Có**, cho endpoint đó |
| HTTP Basic credentials được browser lưu và tự gửi | Có thể | Cần đánh giá |
| TLS client certificate browser tự sử dụng | Có thể | Cần đánh giá |
| SPA tự thêm **Authorization: Bearer** từ token trong bộ nhớ | Không theo cơ chế cookie/form | Thường không cần CSRF token nếu **không có** ambient authentication |
| CLI/mobile tự đặt Bearer header | Không liên quan browser tự gửi | Không theo mô hình CSRF browser |
| Resource Server JWT nhưng custom resolver đọc JWT từ cookie | Có | **Có** |
| API hỗ trợ cả Bearer header và session cookie | Có thể dùng cookie | **Có** trên endpoint chấp nhận cookie |

**JwtDecoder** và **OpaqueTokenIntrospector** giải quyết **tính hợp lệ của access token**. Chúng không tự chứng minh **người dùng có chủ ý khởi tạo request từ browser**.

## 3. Bearer header chủ động và JWT cookie không giống nhau

### 3.1. Bearer token trong header do frontend đặt

Ví dụ một SPA giữ access token trong state/memory và chủ động gọi API:

~~~javascript
async function createOrder(accessToken, order) {
  return fetch("/api/orders", {
    method: "POST",
    headers: {
      Authorization: "Bearer " + accessToken,
      "Content-Type": "application/json"
    },
    body: JSON.stringify(order)
  });
}
~~~

Mã ứng dụng **chủ động** thêm Authorization header. Một HTML form từ website khác không biết accessToken và không thể tự làm browser chèn biến JavaScript đó vào một request.

**Điều kiện an toàn phải được nói đầy đủ:** server **chỉ** chấp nhận token trong Authorization header, không nhận phiên cookie/Basic/certificate từ browser làm authentication thay thế. Nếu vẫn có cookie authentication fallback, rủi ro CSRF trở lại.

Cũng không được suy ra SPA này miễn nhiễm XSS: JavaScript độc hại chạy trong origin thật có thể dùng token hoặc tự gửi hành động. CSRF token không thay thế phòng chống XSS.

### 3.2. JWT trong cookie vẫn bị gửi như cookie

~~~http
Set-Cookie: ACCESS_TOKEN=jwt-value; Path=/; Secure; HttpOnly; SameSite=None
~~~

Nếu một custom filter hoặc **BearerTokenResolver** lấy JWT từ cookie, browser có thể tự gửi credential. Việc JWT được ký hợp lệ bằng RS256 **không chứng minh request do người dùng có ý định thực hiện**.

**JWT + stateless + HttpOnly cookie vẫn có thể cần CSRF protection.**

### 3.3. HttpOnly và Secure giải quyết vấn đề khác

- **HttpOnly** giúp ngăn JavaScript truy cập cookie bằng document.cookie; không ngăn browser gửi cookie.
- **Secure** giới hạn việc gửi cookie qua kênh bảo mật.
- **SameSite** giới hạn cookie được gửi trong những cross-site contexts.
- **CSRF token** yêu cầu một giá trị được client chủ động gửi trong form/header, không tự xuất hiện chỉ vì browser có session cookie.

Một session cookie nên được bảo vệ bằng Secure/HttpOnly và cookie scope hợp lý, nhưng các thuộc tính này không tự thay thế CSRF token trên endpoint nhạy cảm.

## 4. SameSite: quan trọng nhưng không thay thế chính sách CSRF

Ví dụ cookie session:

~~~http
Set-Cookie: JSESSIONID=example; Path=/; Secure; HttpOnly; SameSite=Lax
~~~

| SameSite | Tác dụng khái quát | Giới hạn |
|---|---|---|
| **Strict** | Gửi cookie trong same-site context | Có thể ảnh hưởng luồng điều hướng từ site ngoài |
| **Lax** | Gửi trong same-site và một số cross-site top-level navigation sử dụng safe method | Không bảo vệ nếu GET thực hiện thao tác nguy hiểm |
| **None** | Cho phép cross-site cookie trong các điều kiện browser cho phép | Trên browser hiện đại cần **Secure** |

Nhiều browser áp dụng hành vi mặc định tương tự Lax nếu cookie không khai báo SameSite, nhưng không được phụ thuộc vào chi tiết mặc định giữa mọi browser/phiên bản. Một số trường hợp Lax mặc định có ngoại lệ ngắn cho POST mới đặt cookie.

### 4.1. Same-site khác same-origin

Ví dụ:

~~~text
https://app.example.com
https://api.example.com
https://untrusted.example.com
~~~

Các origin khác nhau nhưng có thể thuộc cùng một **site** theo schemeful site rules. Nếu một subdomain bị kiểm soát bởi bên không đáng tin, **SameSite** không còn là ranh giới đủ chặt để chặn mọi request từ subdomain đó.

Do đó cần đánh giá cookie **Domain** và phạm vi subdomain. Cookie host-only hoặc các prefix như **__Host-** có thể giúp hạn chế cookie scope khi phù hợp.

### 4.2. Không dùng GET để thay đổi trạng thái

Spring Security mặc định không yêu cầu CSRF token cho **GET, HEAD, TRACE, OPTIONS**, vì HTTP semantics xem chúng là safe methods.

Nếu ứng dụng viết:

~~~text
GET /orders/42/cancel
GET /account/delete
GET /logout
~~~

và GET trực tiếp thực hiện hành động thay đổi trạng thái, CSRF có thể xảy ra theo những đường khác nhau. Thay bằng POST/DELETE phù hợp, kết hợp kiểm quyền và CSRF policy. **SameSite=Lax** vẫn cho phép cookie trong một số top-level navigation dùng GET.

## 5. CORS không tự giải quyết CSRF

**CORS** chủ yếu quản lý khả năng browser JavaScript từ origin khác thực hiện một số cross-origin requests và **đọc response**. Nó không thay thế kiểm tra ý định của request.

Một HTML form POST với content type đơn giản có thể được browser gửi cross-origin mà không cần đọc response. Khi server dùng cookie authentication và chấp nhận form request, **ngăn đọc JSON phản hồi không ngăn trạng thái server bị thay đổi**.

### 5.1. Preflight và custom header

Request JavaScript cross-origin chứa **Authorization**, **X-CSRF-TOKEN** hoặc content type không thuộc nhóm đơn giản thường cần CORS preflight. Nếu server không cho origin đó, browser sẽ ngăn request theo mô hình CORS.

Đây là lớp bảo vệ hữu ích nhưng có giới hạn:

- Form submissions có thể gửi request không cần preflight.
- Server có thể chấp nhận nhiều content types hoặc method override.
- CORS configuration có thể cho phép origin không tin cậy.
- Same-site subdomain có thể là origin khác.
- CORS không phải cơ chế xác minh session/CSRF token.

### 5.2. credentials trong fetch

~~~javascript
fetch("https://api.example.com/orders", {
  method: "POST",
  credentials: "include",
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify({ item: "book" })
});
~~~

**credentials: "include"** cho phép browser đính kèm credential phù hợp nếu cookie policy và những ràng buộc browser cho phép. Nó không bảo đảm cookie nào cũng được gửi, nhưng nhắc rằng một SPA có thể dùng **cookie authentication** dù request được tạo từ JavaScript.

**Không mở Access-Control-Allow-Origin bừa bãi cùng credentials.** Kiểm allowlist origin và preflight theo kiến trúc frontend thật.

## 6. CsrfFilter trong Spring Security Servlet

Spring Security cung cấp **CsrfFilter** để kiểm CSRF token trên những HTTP methods được coi là unsafe. Bảo vệ CSRF được bật theo mặc định trong những cấu hình web SecurityFilterChain thông dụng.

Luồng xử lý:

~~~mermaid
flowchart TD
    R[HTTP request] --> C[CsrfFilter]
    C --> M{Method cần CSRF validation?}
    M -->|Không| P[Tiếp tục SecurityFilterChain]
    M -->|Có| L[Load expected CsrfToken]
    L --> T[Đọc token từ header/form parameter]
    T --> V{Token đúng với expected token?}
    V -->|Không hoặc thiếu| D[AccessDenied / thường 403]
    V -->|Có| P
    P --> A[Authentication và Authorization]
    A --> H[Controller / Domain policy]
~~~

Đây là sơ đồ logic; vị trí filter và exception handling thực tế phụ thuộc cấu hình.

### 6.1. Những thành phần liên quan

| Thành phần | Chức năng |
|---|---|
| **CsrfFilter** | Chọn request cần kiểm, so sánh token, từ chối thiếu/sai |
| **CsrfToken** | Tên header/parameter và giá trị token |
| **CsrfTokenRepository** | Sinh/lưu/tải token kỳ vọng |
| **HttpSessionCsrfTokenRepository** | Lưu CSRF token trong HttpSession, là mặc định phổ biến |
| **CookieCsrfTokenRepository** | Lưu expected token trong cookie để hỗ trợ SPA |
| **CsrfTokenRequestHandler** | Đưa token cho view và đọc token gửi trong request |
| **XorCsrfTokenRequestAttributeHandler** | Mask token để giảm nguy cơ BREACH, mặc định Spring Security hiện đại |
| **AccessDeniedHandler** | Xử lý missing/invalid CSRF token |

**CsrfFilter không xác minh JWT signature.** JWT/opaque token phải được JwtDecoder hoặc OpaqueTokenIntrospector tin cậy xử lý độc lập.

### 6.2. Unsafe HTTP methods

Theo default matcher, CsrfFilter thường bỏ qua **GET, HEAD, TRACE, OPTIONS** và yêu cầu token cho **POST, PUT, PATCH, DELETE** cùng các method unsafe khác.

Dù TRACE được coi là safe về CSRF matcher, application có thể nên tắt TRACE vì các rủi ro khác. Quan trọng nhất là **không có nghiệp vụ thay đổi trạng thái qua GET**.

### 6.3. Deferred token và BREACH

Trong Spring Security 6+, CSRF token loading được trì hoãn khi chưa cần; token exposed qua request handler mặc định có thể được **mask với randomness** để giảm rủi ro BREACH.

Do đó ứng dụng SPA đọc raw CSRF token từ cookie phải dùng handler phù hợp, không mặc định copy cách dùng một form đã được server render sang SPA mà không xét khác biệt token masking.

## 7. Synchronizer Token Pattern

Nguyên tắc chuẩn là **server yêu cầu một giá trị khó đoán không được browser tự đính kèm chỉ vì có cookie**.

Quy trình:

1. Server tạo token gắn với session/ngữ cảnh bảo vệ.
2. Token được đưa tới form hoặc giao diện ứng dụng thật theo cách được bảo vệ.
3. Browser gửi session cookie tự động, **nhưng form/JS phải chủ động gửi thêm CSRF token**.
4. Server so sánh submitted CSRF token với expected token; thiếu hoặc sai → từ chối.

~~~mermaid
sequenceDiagram
    participant B as Browser ứng dụng thật
    participant S as Spring Security
    B->>S: GET /profile + session cookie
    S-->>B: Trang chứa token trong form
    B->>S: POST /profile + session cookie + hidden _csrf
    S->>S: Kiểm token khớp session
    S-->>B: Tiếp tục nếu các policy khác đạt
~~~

### 7.1. Hidden form field

~~~html
<form action="/profile" method="post">
  <input name="displayName" value="Example">
  <input type="hidden"
         name="_csrf"
         value="token-created-by-the-server">
  <button type="submit">Save</button>
</form>
~~~

Giá trị phải do server tạo/đưa vào view, không hardcode. View integrations như Thymeleaf và Spring form tag có thể hỗ trợ thêm token tự động khi cấu hình đúng.

### 7.2. Chỉ có CSRF cookie không đủ

Browser cũng tự gửi CSRF cookie. Nếu server chỉ kiểm cookie **tồn tại**, attacker có thể hưởng lợi từ chính việc browser gửi cookie đó.

Cần server xác nhận submitted token trong **hidden field hoặc header** theo repository/handler. Với custom double-submit cookie pattern, cần phòng ngừa cookie injection và liên kết token với phiên, ví dụ signed session-bound token khi thiết kế yêu cầu.

## 8. Website có session/form login: giữ CSRF bật

Với web app sử dụng **JSESSIONID** và form login, Spring Security thường bật CSRF protection mặc định.

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
class WebSecurityConfig {

    @Bean
    SecurityFilterChain webChain(HttpSecurity http) throws Exception {
        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/assets/**", "/login").permitAll()
                .anyRequest().authenticated()
            )
            .formLogin(Customizer.withDefaults())
            .csrf(Customizer.withDefaults());
        return http.build();
    }
}
~~~

**csrf(Customizer.withDefaults())** diễn đạt rõ policy; trong nhiều cấu hình Servlet, không cần viết nó vì CSRF đã bật mặc định.

Nếu một POST từ form bị 403 do thiếu CSRF token, **không khắc phục bằng cách tắt CSRF toàn bộ**. Cần đảm bảo form có token và session/token còn hợp lệ.

### 8.1. Login và logout cũng liên quan CSRF

- **Login CSRF** có thể khiến browser nạn nhân đăng nhập vào tài khoản không mong muốn hoặc làm sai luồng danh tính.
- **Logout CSRF** có thể khiến attacker ép nạn nhân logout. Khi CSRF protection bật, Spring Security thông thường dùng **POST /logout** có CSRF token thay vì logout bằng GET.
- Endpoint link account, change email, password reset và hành động nhạy cảm khác cần được đánh giá theo browser credential/threat model.

Một public URL **permitAll** không đồng nghĩa request POST tới URL đó bỏ qua CsrfFilter.

## 9. SPA và BFF dùng cookie: vẫn cần CSRF token

Một SPA có thể gọi API bằng session cookie hoặc một BFF cookie:

~~~text
Browser lưu session cookie HttpOnly
  -> JavaScript gửi POST /api/orders
  -> Browser tự gắn cookie
  -> JavaScript gửi thêm X-CSRF-TOKEN hoặc X-XSRF-TOKEN
  -> Server đối chiếu token
~~~

### 9.1. CookieCsrfTokenRepository

Spring Security hỗ trợ:

~~~java
import org.springframework.security.web.csrf.CookieCsrfTokenRepository;

CookieCsrfTokenRepository repository =
    CookieCsrfTokenRepository.withHttpOnlyFalse();
~~~

Các tên thường gặp:

~~~text
Cookie: XSRF-TOKEN
Header: X-XSRF-TOKEN
Form parameter: _csrf
~~~

**withHttpOnlyFalse()** được dùng khi frontend thật sự phải đọc CSRF cookie bằng JavaScript. **Không làm như vậy cho session cookie hoặc access token cookie** chỉ vì cần CSRF. Nếu frontend nhận CSRF token qua server-rendered HTML hoặc cách khác, có thể không cần JavaScript-readable CSRF cookie.

### 9.2. Cần xử lý raw token và BREACH masking đúng phiên bản

Spring Security 6 sử dụng **XorCsrfTokenRequestAttributeHandler** theo mặc định. Khi form server-rendered gửi token được mask, handler có thể giải mã; trong khi SPA đọc token thô từ cookie và gửi **X-XSRF-TOKEN**.

Vì vậy Spring Security có hướng dẫn **SPA-specific request handler**, phân biệt raw header với masked form parameter và làm mới CSRF cookie sau authentication/logout. Chỉ đặt CookieCsrfTokenRepository không nhất thiết đủ với mọi version/integration.

Trong **Spring Security 7.0+**, API cấu hình có thể dùng:

~~~java
http.csrf(csrf -> csrf.spa());
~~~

**spa()** thiết lập những thành phần phù hợp cho SPA theo tài liệu Spring Security 7. **Đừng copy sang Spring Security 6 nếu phương thức chưa tồn tại.** Với Boot 3/Security 6, cần dùng recipe thủ công trong tài liệu đúng phiên bản.

### 9.3. JavaScript gửi CSRF header

~~~javascript
async function updateProfile(csrfToken, profile) {
  return fetch("/api/profile", {
    method: "POST",
    credentials: "same-origin",
    headers: {
      "Content-Type": "application/json",
      "X-XSRF-TOKEN": csrfToken
    },
    body: JSON.stringify(profile)
  });
}
~~~

Ví dụ giả định frontend đã nhận CSRF token hợp lệ. Request khác origin cần cấu hình credentials và CORS đúng theo kiến trúc, không mở tùy tiện. **Giá trị token được gửi trong header** là phần khác với session cookie tự gửi.

## 10. OAuth2/OIDC Login: state, nonce và PKCE không thay thế CSRF sau đăng nhập

Trong Authorization Code/OIDC Login:

- **state** liên kết authorization request/response và hỗ trợ chống login CSRF/response mix-up theo thiết kế.
- **nonce** liên kết ID Token với authentication request khi OIDC sử dụng.
- **PKCE** ràng buộc authorization code với code verifier của client.
- **redirect_uri**, issuer/client validation bảo vệ các ranh giới khác.

Những cơ chế này không tự bảo vệ:

~~~text
POST /account/change-email
POST /orders/approve
POST /logout
POST /auth/refresh
~~~

nếu browser truy cập chúng bằng session cookie hoặc credential tự động.

Ví dụ người dùng đăng nhập qua OAuth2 Login, ứng dụng giữ **JSESSIONID** và dùng nó cho thao tác nghiệp vụ. Sau login, **POST /account/change-email** vẫn có thể cần CSRF token, dù authorization code flow trước đó có state/nonce/PKCE.

### 10.1. Refresh token cookie

Nếu browser lưu refresh token trong HttpOnly cookie, endpoint **/auth/refresh** được gọi bằng cookie tự gắn. Hãy xét CSRF cho endpoint này dựa trên hiệu ứng của việc refresh/rotate session/token, đồng thời kiểm CORS, caching, token rotation và replay protection.

Đừng loại mọi URL **/auth/** khỏi CSRF theo một rule rộng chỉ vì đó là “endpoint xác thực”.

## 11. BFF: xem hai chặng riêng biệt

Một Backend for Frontend giữ OAuth2 access token/refresh token ở server, trong khi browser chỉ giữ session cookie.

~~~mermaid
flowchart LR
    B[Browser] -->|Session cookie tự gửi| F[BFF]
    F -->|Bearer header chủ động gắn| R[Resource Server]
    F <-->|OAuth protocol/token phía server| A[Authorization Server]
~~~

**Chặng browser → BFF:** cookie tự gửi, các thao tác POST/PUT/DELETE có CSRF risk và thường cần CSRF protection.

**Chặng BFF → Resource Server:** BFF chủ động gắn Authorization Bearer. Nếu Resource Server không nhận ambient browser credentials thì threat model CSRF có thể khác.

Một lập luận sai là **“BFF không đưa access token cho browser, nên không có CSRF.”** Browser vẫn có cookie đăng nhập vào BFF, nên cần bảo vệ đúng tại biên browser-facing.

## 12. Resource Server thuần Bearer header: khi nào có thể tắt CSRF?

Có thể xét tắt CsrfFilter trên chain chỉ dành cho API nếu **tất cả điều kiện liên quan đều được xác nhận**:

1. API chỉ xác thực Bearer token có trong **Authorization header** do client chủ động gửi.
2. API không dùng **JSESSIONID** hoặc bất kỳ cookie nào như credential đăng nhập.
3. API không đọc JWT/opaque token từ cookie bằng custom resolver/filter.
4. API không có browser-managed HTTP Basic hoặc client-certificate authentication được chấp nhận thay thế.
5. API không có fallback session authentication khi thiếu Authorization header.
6. Endpoint login/refresh/logout/BFF có ambient credentials nằm trong chain khác và vẫn được bảo vệ.
7. Request chỉ có cookie nhưng không có Bearer header **không được chấp nhận**.
8. Các kiểm tra JWT/opaque token và authorization vẫn hoạt động bình thường.
9. CORS, XSS, token storage, TLS và security headers được đánh giá độc lập.

Ví dụ Servlet JWT Resource Server **Bearer-only**:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.annotation.Order;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
class BearerOnlySecurityConfig {

    @Bean
    @Order(1)
    SecurityFilterChain apiChain(HttpSecurity http) throws Exception {
        http
            .securityMatcher("/api/**")
            .sessionManagement(session -> session
                .sessionCreationPolicy(SessionCreationPolicy.STATELESS))
            // Chỉ sau khi xác nhận chain không có ambient credentials.
            .csrf(csrf -> csrf.disable())
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/api/public/**").permitAll()
                .anyRequest().authenticated()
            )
            .oauth2ResourceServer(oauth2 -> oauth2
                .jwt(Customizer.withDefaults()));
        return http.build();
    }
}
~~~

**Không copy đoạn này vào app cookie-authenticated.** Nó chỉ minh họa policy của **một chain API** đã được phân tích đúng threat model.

### 12.1. STATELESS không tự bảo vệ CSRF

**SessionCreationPolicy.STATELESS** nói Spring Security không sử dụng HttpSession để lưu/truy xuất SecurityContext theo policy đó. Nó **không ngăn browser gửi cookie** và **không ngăn một custom filter đọc JWT từ cookie**.

Một backend không lưu session nhưng nhận JWT cookie vẫn có ambient credential. CSRF protection cần được quyết định dựa trên hành vi xác thực thực tế.

### 12.2. Opaque token cũng theo nguyên tắc tương tự

Với:

~~~java
.oauth2ResourceServer(oauth2 -> oauth2
    .opaqueToken(Customizer.withDefaults()))
~~~

nếu token luôn được client chủ động đặt trong Authorization header, kết luận CSRF tương tự JWT Bearer-only. **JwtDecoder** và **OpaqueTokenIntrospector** khác nhau về phương pháp xác minh, không khác nhau về điều kiện browser tự gửi credential.

### 12.3. Tắt CSRF không có nghĩa tắt authentication

Khi disable CSRF cho một chain Bearer-only, Resource Server vẫn phải:

- Kiểm issuer, key/signature hoặc introspection endpoint tin cậy.
- Kiểm audience, exp/nbf, token type/profile theo policy.
- Kiểm scope/authority và quyền tenant/ownership.
- Từ chối không token, token giả, hết hạn hoặc thiếu quyền.
- Bảo vệ credential bằng HTTPS và không ghi raw token vào log.

Không dùng csrf.disable() để “chữa” 401 invalid_token hoặc 403 insufficient_scope.

## 13. Hệ thống hỗn hợp: SecurityFilterChain theo ranh giới credential

Một ứng dụng có thể cung cấp cả API Bearer-only và UI dùng session cookie. Khi đó có thể tách security chains.

Ví dụ nguyên tắc:

~~~text
@Order(1) /api/**:
  JWT Bearer header only
  stateless
  CSRF disabled theo threat model đã xác nhận
  Scope/authority authorization

@Order(2) /web/**:
  Form login/OAuth2 Login
  HttpSession và session cookie
  CSRF enabled

@Order(3) fallback:
  Deny unhandled requests hoặc policy đã thiết kế
~~~

Mẫu cấu hình:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.annotation.Order;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
class MixedSecurityConfig {

    @Bean
    @Order(1)
    SecurityFilterChain api(HttpSecurity http) throws Exception {
        http
            .securityMatcher("/api/**")
            .sessionManagement(session -> session
                .sessionCreationPolicy(SessionCreationPolicy.STATELESS))
            .csrf(csrf -> csrf.disable())
            .authorizeHttpRequests(auth -> auth
                .anyRequest().authenticated())
            .oauth2ResourceServer(oauth2 -> oauth2
                .jwt(Customizer.withDefaults()));
        return http.build();
    }

    @Bean
    @Order(2)
    SecurityFilterChain web(HttpSecurity http) throws Exception {
        http
            .securityMatcher("/web/**")
            .authorizeHttpRequests(auth -> auth
                .anyRequest().authenticated())
            .formLogin(Customizer.withDefaults())
            .csrf(Customizer.withDefaults());
        return http.build();
    }

    @Bean
    @Order(3)
    SecurityFilterChain fallback(HttpSecurity http) throws Exception {
        http.authorizeHttpRequests(auth -> auth.anyRequest().denyAll());
        return http.build();
    }
}
~~~

**Giới hạn ví dụ:** chain **/web/** chỉ là minh họa về matcher và policy, chưa cấu hình đầy đủ login page, callback OIDC, logout, error/static routes. Nếu sử dụng formLogin mặc định, các URL login/logout cần được đặt vào đúng chain hoặc cấu hình lại endpoint; không mặc định copy mẫu vào production.

**FilterChainProxy chọn chain đầu tiên khớp**, không cộng dồn policies. Nếu cùng một endpoint chấp nhận cả cookie session lẫn Bearer header, không được bỏ CSRF chỉ vì endpoint có khả năng xử lý Bearer.

## 14. Bỏ CSRF có chọn lọc khác bỏ toàn bộ Spring Security

Spring Security cho phép bỏ kiểm CSRF cho một số request:

~~~java
http.csrf(csrf -> csrf
    .ignoringRequestMatchers("/integration/webhook/**"));
~~~

Nhưng phải kiểm endpoint đó **không xác thực bằng browser-ambient credentials**, đồng thời có cơ chế bảo vệ khác phù hợp (ví dụ HMAC signature và chống replay cho webhook). Chỉ loại khỏi CSRF **không làm endpoint được xác thực**.

Phân biệt:

- **csrf.ignoringRequestMatchers**: bỏ riêng CSRF validation trên request khớp; những filters/authorization khác vẫn có thể hoạt động.
- **web.ignoring().requestMatchers**: bỏ qua Spring Security filter chain ở phạm vi rộng hơn, có thể bỏ luôn authentication/authorization.
- **permitAll()**: cho qua bước authorization không cần authentication, nhưng **CsrfFilter vẫn có thể yêu cầu token cho POST**.

Không dùng **web.ignoring** để chữa lỗi CSRF của endpoint nghiệp vụ.

## 15. Token repository: Session so với Cookie

### 15.1. HttpSessionCsrfTokenRepository

~~~java
import org.springframework.security.web.csrf.HttpSessionCsrfTokenRepository;

http.csrf(csrf -> csrf
    .csrfTokenRepository(new HttpSessionCsrfTokenRepository()));
~~~

Giá trị kỳ vọng nằm trong HttpSession, phù hợp với server-rendered form. Nếu session hết hạn, CSRF token từ trang cũ có thể không hợp lệ, gây 403; ứng dụng cần xử lý session timeout UX đúng thay vì tắt validation.

### 15.2. CookieCsrfTokenRepository

~~~java
import org.springframework.security.web.csrf.CookieCsrfTokenRepository;

http.csrf(csrf -> csrf
    .csrfTokenRepository(CookieCsrfTokenRepository.withHttpOnlyFalse()));
~~~

Mẫu này là **chỉ phần repository**, không phải recipe SPA hoàn chỉnh cho Spring Security 6. Với raw token từ cookie và masked token của BREACH handler, cần cấu hình request handler phù hợp, đồng thời làm mới token sau authentication/logout.

Không đặt CSRF token trong URL, query string hoặc referer-prone locations. Tránh ghi raw session cookie, access token và CSRF token vào log.

## 16. Origin, Referer, Fetch Metadata như defense-in-depth

Các lớp bổ sung có thể giúp giảm CSRF:

| Cơ chế | Tác dụng | Giới hạn |
|---|---|---|
| **Origin validation** | So sánh origin của request với allowlist | Origin có thể thiếu/null tùy request; cần fallback policy |
| **Referer validation** | Có thể hỗ trợ khi Origin không có | Có thể bị browser/privacy policy lược bỏ |
| **Sec-Fetch-Site** | Phân biệt same-origin, same-site, cross-site | Client không phải lúc nào có header; same-site subdomain chưa chắc tin cậy |
| **SameSite=Lax/Strict** | Giảm các tình huống cookie gửi cross-site | Không bảo vệ mọi đường đi, nhất là sai ngữ nghĩa GET |
| **Strict Content-Type** | Giảm khả năng form đơn giản gọi JSON-only handler | Không đủ nếu server hỗ trợ content type khác, method override hoặc CORS lỗi |
| **CSRF token** | Yêu cầu giá trị khó đoán được gửi chủ động | Phải bảo vệ khỏi XSS/leak và xử lý lifecycle |

Không so sánh origin bằng phép kiểm hậu tố chuỗi đơn giản, không tin proxy forwarded headers từ client tùy ý và không giả định mọi browser đều gửi Fetch Metadata.

## 17. CSRF và XSS là hai vấn đề khác nhau

**CSRF:** attacker không đọc được credential nhưng khiến browser tự gửi credential.

**XSS:** attacker chạy JavaScript trong origin ứng dụng. Khi ấy script có thể:

- Đọc CSRF token hiển thị trong DOM/cookie JavaScript-readable.
- Gửi request có CSRF header hợp lệ.
- Đọc access token lưu trong nơi JavaScript truy cập được.
- Thực hiện thao tác dưới session của nạn nhân.

Vì vậy CSRF token **không bảo vệ hoàn toàn khi có XSS**, và HttpOnly cookie **không tự chống CSRF**. Cần kết hợp template escaping/output encoding, CSP, dependency hygiene, đúng cookie policy và bảo vệ Bearer token.

## 18. Kiểm thử CSRF bằng Spring Security MockMvc

Spring Security Test có **csrf() request post-processor** cho Servlet MockMvc.

Giả sử controller **POST /web/profile** đã tồn tại và trả **204 No Content** khi update thành công:

~~~java
import static org.springframework.security.test.web.servlet.request
    .SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.security.test.web.servlet.request
    .SecurityMockMvcRequestPostProcessors.user;
import static org.springframework.test.web.servlet.request
    .MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result
    .MockMvcResultMatchers.status;

import org.junit.jupiter.api.Test;
import org.springframework.http.MediaType;

// Trong test class đã có MockMvc và SecurityFilterChain thật.
@Test
void postWithoutCsrfIsForbidden() throws Exception {
    mockMvc.perform(post("/web/profile")
            .with(user("alice"))
            .contentType(MediaType.APPLICATION_JSON)
            .content("{\"displayName\":\"Alice\"}"))
        .andExpect(status().isForbidden());
}

@Test
void postWithValidCsrfPassesFilter() throws Exception {
    mockMvc.perform(post("/web/profile")
            .with(user("alice"))
            .with(csrf())
            .contentType(MediaType.APPLICATION_JSON)
            .content("{\"displayName\":\"Alice\"}"))
        .andExpect(status().isNoContent());
}

@Test
void postWithInvalidCsrfIsForbidden() throws Exception {
    mockMvc.perform(post("/web/profile")
            .with(user("alice"))
            .with(csrf().useInvalidToken())
            .contentType(MediaType.APPLICATION_JSON)
            .content("{\"displayName\":\"Alice\"}"))
        .andExpect(status().isForbidden());
}
~~~

Đây là ví dụ test CSRF/authorization, không phải một test class hoàn chỉnh. **204** phụ thuộc controller, auth policy và fixture. Giá trị cốt lõi là phân biệt **thiếu/sai CSRF token** với **token hợp lệ**.

### 18.1. MockMvc jwt() không tự vô hiệu hóa CsrfFilter

Spring Security Test hỗ trợ **jwt()** để tạo Authentication mô phỏng. Nếu bạn gọi:

~~~java
mockMvc.perform(post("/api/orders").with(jwt()));
~~~

trên chain **vẫn bật CSRF**, request có thể bị **403 vì thiếu CSRF token**. Điều đó không chứng minh JWT luôn cần CSRF; nó chỉ phản ánh **policy của chain trong test**.

Nếu test Bearer-only API đã disable CSRF theo threat model, hãy dùng đúng security configuration đó để test scope/authority, và có thêm integration test với Authorization header thật để kiểm JwtDecoder.

### 18.2. Test các tình huống từ browser thật

Ngoài MockMvc, cần test:

1. Cookie-authenticated POST thiếu CSRF → từ chối.
2. CSRF token không đúng session → từ chối.
3. Đúng cookie và CSRF token → đi qua CsrfFilter.
4. Bearer-only API không token → từ chối.
5. Bearer-only API chỉ có JSESSIONID/cookie → **không authenticate**.
6. JWT giả chữ ký hoặc sai issuer/audience → bị từ chối.
7. JWT hợp lệ thiếu scope → bị authorization từ chối.
8. SameSite/CORS behavior trên những origin/public URL thực tế.
9. OIDC Login, logout, refresh cookie, BFF endpoints.
10. SecurityFilterChain @Order và matcher chính xác.

**Không dùng MockMvcBuilders.standaloneSetup** chưa gắn Spring Security filters hoặc **@AutoConfigureMockMvc(addFilters=false)** để kết luận về CSRF production.

## 19. Phân biệt 401, 403 do CSRF, 403 do scope

| Request | Nguồn quyết định | Kết quả thông dụng |
|---|---|---|
| POST có session cookie nhưng thiếu CSRF | **CsrfFilter** | **403** |
| POST có session cookie, CSRF sai | **CsrfFilter** | **403** |
| GET protected API không Bearer token | Authentication | **401** |
| POST Bearer-only chain đã disable CSRF, không token | Authentication | **401** |
| JWT signature sai | JwtDecoder | **401 invalid_token** thường gặp |
| Token hợp lệ nhưng thiếu scope | Authorization | **403**, có thể insufficient_scope |
| Token đủ scope nhưng không có quyền tenant | Domain policy | **403/404** tùy thiết kế |
| POST có Bearer token hợp lệ nhưng chain vẫn bật CSRF | CsrfFilter | Có thể **403 do thiếu CSRF** |

**Không phải mọi 403 đều là thiếu OAuth2 scope.** Nếu CsrfFilter từ chối, đừng vội trả **WWW-Authenticate: Bearer error="insufficient_scope"** hoặc sửa JwtAuthenticationConverter.

Khi debug, xác định filter chain được chọn, csrf request matcher, exception type như **MissingCsrfTokenException/InvalidCsrfTokenException**, rồi mới xét JwtDecoder/scope.

## 20. Những sai lầm phổ biến

**“REST API không render HTML nên không có CSRF.”** Sai nếu API dùng cookie hoặc browser-managed authentication.

**“Stateless và JWT nên không có CSRF.”** Sai khi browser tự gửi JWT cookie.

**“HttpOnly chống CSRF.”** Sai: HttpOnly giảm khả năng JavaScript đọc cookie nhưng không chặn việc browser gửi cookie.

**“CORS chặn origin khác nên đủ.”** Không, form cross-site có thể gửi request mà không đọc response.

**“SameSite=Lax thay CSRF token.”** Không trong mọi trường hợp, đặc biệt nếu GET thay đổi trạng thái hoặc có subdomain same-site không đáng tin.

**“OIDC Login đã có state/nonce/PKCE.”** Các cơ chế đó bảo vệ authorization/login flow, không tự bảo vệ POST nghiệp vụ dùng session cookie.

**“BFF giữ token ở server nên không có CSRF.”** Browser vẫn gửi BFF session cookie.

**“permitAll đồng nghĩa không cần CSRF.”** Không, permitAll là authorization rule, CsrfFilter vẫn có thể kiểm unsafe methods.

**“Chỉ cần XSRF-TOKEN cookie tồn tại.”** Không, phải kiểm token được gửi chủ động trong header/form theo repository/handler.

**“Tắt CSRF là cách khắc phục mọi POST 403.”** Nguy hiểm. Phải xác định 403 do CSRF, scope, role hay domain policy.

**“Tắt CSRF trên một chain thì các chain khác cũng an toàn.”** Mỗi chain/matcher có authentication mechanisms và policy riêng, cần đánh giá toàn bộ URL.

## 21. Quy trình quyết định policy trong dự án

**Bước 1 — Liệt kê endpoint và phương thức xác thực.** Ghi URL, method, SecurityFilterChain, loại token, session cookie, Basic, mTLS, BFF/refresh cookie.

**Bước 2 — Xác định credential nào browser tự gửi.** Xét cookie Domain/Path/SameSite, browser auth cache, certificate, credentials mode và các đường fallback.

**Bước 3 — Xác định endpoint thay đổi trạng thái.** Bao gồm không chỉ CRUD mà còn login, logout, refresh, approve, transfer, billing, link account và token rotation.

**Bước 4 — Chọn CSRF mechanism.** Với cookie/session authentication, giữ token validation, kết hợp SameSite/Origin/Fetch Metadata. Với Bearer-only chain được xác nhận không ambient credentials, có thể tắt CSRF cho đúng chain đó.

**Bước 5 — Kiểm cấu hình Spring Security.** SecurityFilterChain selection, @Order, securityMatcher, csrf.ignoringRequestMatchers, CsrfTokenRepository, request handler, fallback và servlet filter registration.

**Bước 6 — Test negative scenarios.** Không token, cookie-only, token giả, thiếu scope, CSRF thiếu/sai, tenant khác và browser/proxy thực tế.

**Bước 7 — Đánh giá lại khi đổi kiến trúc.** Chuyển JWT từ Authorization header sang cookie, thêm OAuth2Login, BFF hay refresh cookie có thể làm quyết định tắt CSRF trước đó **không còn đúng**.

## 22. Bài tập tình huống

### A. SPA thuần Bearer header

Frontend chủ động gắn Authorization Bearer, API chỉ tin header này và không dùng session/cookie/Basic. **CSRF truyền thống thường không có điều kiện ambient credential; có thể xem xét tắt CSRF cho API chain**, nhưng vẫn phải chống XSS, token theft, kiểm issuer/audience/scope và CORS.

### B. JWT nằm trong HttpOnly cookie, backend stateless

Browser tự gửi cookie JWT. **CSRF risk vẫn có thể tồn tại**, dù server không lưu session và JWT được ký hợp lệ.

### C. OAuth2 Login rồi dùng JSESSIONID

OIDC state/nonce/PKCE bảo vệ login flow, nhưng POST thay đổi hồ sơ dùng session cookie **vẫn cần CSRF protection** theo mô hình browser.

### D. BFF giữ access token ở server

Browser → BFF qua session cookie có CSRF risk; BFF → Resource Server chủ động gắn Bearer là chặng có threat model khác.

### E. GET /orders/42/cancel

GET thực hiện hủy đơn là thiết kế unsafe. CsrfFilter mặc định bỏ qua GET; phải chuyển sang phương thức phù hợp và áp dụng CSRF/authorization.

### F. MockMvc POST có jwt() trả 403

Nếu CsrfFilter vẫn bật, 403 có thể do thiếu CSRF token chứ không phải scope. Kiểm chain và exception trước khi đổi policy.

## Kết luận

**CSRF phụ thuộc vào việc browser tự gửi credential mà server chấp nhận**, không phụ thuộc đơn thuần vào JWT, opaque token, REST hay stateless. Cookie session, JWT cookie, BFF session, OAuth2 Login có session và các cơ chế browser-managed khác đều cần đánh giá CSRF cho thao tác thay đổi trạng thái.

**Spring Security Servlet** cung cấp CsrfFilter, CsrfTokenRepository và CsrfTokenRequestHandler để kiểm giá trị chống giả mạo được gửi **chủ động** qua form/header. SameSite, Origin/Fetch Metadata, CORS và cookie flags là những lớp hỗ trợ quan trọng, không tự thay thế token validation trong mọi kiến trúc.

Một **Resource Server thuần Authorization: Bearer** có thể không cần CSRF token nếu đã xác nhận không có ambient credentials và có test chứng minh. **SessionCreationPolicy.STATELESS, HttpOnly, chữ ký JWT và OIDC state/PKCE không phải những công tắc tự động loại bỏ CSRF.**

### Tài liệu tham khảo

- [Spring Security Reference — Servlet CSRF](https://docs.spring.io/spring-security/reference/servlet/exploits/csrf.html)
- [Spring Security — CSRF Concepts and Synchronizer Token Pattern](https://docs.spring.io/spring-security/reference/features/exploits/csrf.html)
- [Spring Security — Resource Server JWT](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html)
- [Spring Security — Resource Server Opaque Tokens](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/opaque-token.html)
- [Spring Security — OAuth2 Login](https://docs.spring.io/spring-security/reference/servlet/oauth2/login/index.html)
- [Spring Security — Servlet CSRF Tests](https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/csrf.html)
- [Spring Security API — CsrfConfigurer.spa()](https://docs.spring.io/spring-security/site/docs/current/api/org/springframework/security/config/annotation/web/configurers/CsrfConfigurer.html)
- [OWASP — Cross-Site Request Forgery Prevention Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Cross-Site_Request_Forgery_Prevention_Cheat_Sheet.html)
- [MDN — Using HTTP Cookies](https://developer.mozilla.org/en-US/docs/Web/HTTP/Guides/Cookies)
- [MDN — Set-Cookie and SameSite](https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/Set-Cookie)
- [RFC 9110 — HTTP Semantics](https://www.rfc-editor.org/rfc/rfc9110)
- [RFC 6750 — OAuth 2.0 Bearer Token Usage](https://www.rfc-editor.org/rfc/rfc6750)
