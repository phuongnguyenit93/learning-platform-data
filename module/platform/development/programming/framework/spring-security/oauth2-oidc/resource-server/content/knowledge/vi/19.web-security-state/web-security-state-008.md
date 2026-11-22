# Cookie chứa token, header chứa token và sự khác nhau về rủi ro

Trong một ứng dụng web sử dụng **Spring Security OAuth 2.0 / OpenID Connect (OIDC) Resource Server**, một **OAuth 2.0 access token** có thể đến API qua header `Authorization: Bearer ...` do Client chủ động thêm, qua **cookie chứa chính token** mà browser tự gửi, hoặc gián tiếp qua **Backend for Frontend (BFF)**: browser giữ session cookie, còn BFF giữ access token ở phía server rồi gọi API bằng Bearer header.

Sự khác biệt này **không chỉ là đổi chỗ lưu một chuỗi token**. Nó quyết định **ai có thể đọc credential**, **trình duyệt có tự gửi credential cho một request không**, và những mối đe dọa như **Cross-Site Request Forgery (CSRF)**, **Cross-Site Scripting (XSS)**, **token theft** hay **session hijacking** được xử lý ra sao.

**Cookie** là một dạng credential có thể được trình duyệt tự gắn vào request nếu phù hợp với domain, path, SameSite và chính sách browser. Do đó, khi API **xác thực bằng cookie**, một website khác có thể tìm cách khiến browser của nạn nhân gửi request kèm credential: **CSRF** trở thành rủi ro quan trọng. **Bearer header** lại thường phải do JavaScript hoặc OAuth2 Client thêm chủ động, nên HTML form cross-site không tự có access token để điền header. Tuy nhiên, nếu JavaScript nắm token thì **XSS vẫn có thể đánh cắp hoặc sử dụng nó**.

> **Nguyên tắc:** Cookie `HttpOnly` hạn chế khả năng JavaScript đọc giá trị cookie, **không** ngăn script độc hại cùng origin gửi request được xác thực. Bearer header giảm một số đường CSRF phụ thuộc cookie tự gửi, **không** ngăn XSS lấy token trong JavaScript. **JWT có stateless hay không không quyết định cần CSRF**: yếu tố quan trọng là credential có được browser **tự động** gắn vào request không.

## 1. Ba kiến trúc cần phân biệt

Giả sử hệ thống gồm:

- **Identity Server:** Authorization Server / OIDC Provider.
- **Shop Web:** OAuth2 Client, web frontend hoặc SPA.
- **Orders API:** Spring Security Resource Server.
- **Order database:** lưu owner, tenant, trạng thái và quyền nghiệp vụ.

| Mô hình | Browser giữ | Credential ở request đến API | Rủi ro trọng tâm |
| --- | --- | --- | --- |
| **A. SPA gửi header** | Access token trong memory hoặc kho JavaScript đọc được | `Authorization: Bearer <access-token>` | XSS/token theft, lưu trữ và vòng đời token; CORS khi cross-origin |
| **B. Access token trong cookie** | Cookie chứa **chính OAuth2 access token**, có thể là `HttpOnly` | `Cookie: ...`; API cần resolver/custom authentication | CSRF do cookie tự gửi, XSS thao tác hộ, cookie scope |
| **C. BFF + session cookie** | Cookie chứa **session ID**, không chứa access token | Browser gọi BFF bằng session cookie; BFF gọi API bằng Bearer header | CSRF với session, session hijacking, bảo vệ token server-side |

**Cookie chứa JWT access token và cookie chứa session ID là hai cơ chế khác nhau.** Session ID thường tham chiếu đến trạng thái server; OAuth access token là credential để gọi API, phải được xác minh issuer/audience/scope/thời hạn. Nếu một JWT được đặt vào cookie, nó không tự biến thành session an toàn; nếu browser có session cookie, Resource Server không tự xem nó như access token.

### 1.1. Token transport không thay thế token verification

Dù token được đưa đến API qua header hay cookie, Resource Server phải kiểm tra:

1. Với JWT: chữ ký JWS bằng khóa tin cậy, issuer, audience, `exp`/`nbf`, token type/profile và các validator khác theo hợp đồng.
2. Với opaque token: introspection từ Authorization Server đáng tin, `active` và resource/audience binding.
3. Scope/`GrantedAuthority` đúng endpoint, ví dụ `SCOPE_orders.read`.
4. Quyền trên đơn hàng thực tế: owner, tenant, role/permission, trạng thái.

**OIDC ID token không phải OAuth2 access token dành cho Orders API**. Không dùng ID token thay access token chỉ vì cả hai có `sub` hoặc đều có hình dạng JWT.

## 2. Header chứa token: Client chủ động gắn credential

Request Bearer thông thường:

~~~http
GET /api/orders/42 HTTP/1.1
Host: api.example.test
Authorization: Bearer eyJhbGciOi...signed-access-token...
Accept: application/json
~~~

Trong một SPA, JavaScript có thể gọi:

~~~javascript
async function getOrder(orderId, accessToken) {
  const response = await fetch(
    "/api/orders/" + encodeURIComponent(orderId),
    {
      headers: {
        Authorization: "Bearer " + accessToken,
        Accept: "application/json"
      }
    }
  );
  if (!response.ok) {
    throw new Error("Unable to read order");
  }
  return response.json();
}
~~~

`fetch` không tự lấy token OAuth từ nơi đăng nhập rồi thêm Bearer header. **Ứng dụng, OAuth2 Client hoặc SDK** phải cung cấp token và quyết định gắn header.

Một website khác không sở hữu access token của người dùng không thể chỉ tạo HTML form là khiến browser tự đặt:

~~~http
Authorization: Bearer <access-token-cua-shop-web>
~~~

Vì vậy mô hình **chỉ chấp nhận Bearer header được gắn chủ động** thường ít bị kiểu CSRF cổ điển dựa trên cookie tự gửi. Nhưng kết luận này có điều kiện quan trọng: **API không được đồng thời chấp nhận session cookie, token trong cookie hoặc loại ambient credential khác để xác thực chính request đó**.

### 2.1. Bearer header vẫn có rủi ro XSS

Nếu script độc hại chạy **trong chính origin của SPA**, nó có thể:

- Đọc token trong `localStorage`, `sessionStorage` hoặc trạng thái JavaScript có thể truy cập.
- Hook luồng gửi request hoặc sử dụng API client đã gắn sẵn header.
- Thực hiện request thay người dùng và đọc dữ liệu trả cho origin ấy.
- Can thiệp UI, thay nội dung form hoặc đánh lừa người dùng thực hiện thao tác.

**Không có chuyện `Authorization` header tự tạo một “vùng bí mật” bảo vệ token khỏi mọi script cùng origin**. Header thay đổi cơ chế **gửi token**, không giải quyết toàn bộ XSS.

### 2.2. Truyền token qua query string có an toàn hơn?

Không. Ví dụ:

~~~http
GET /api/orders/42?access_token=<secret>
~~~

Token có thể lộ qua browser history, referrer, access log, reverse proxy, analytics hoặc hệ thống quan sát. Spring Security có tùy chọn Bearer resolver cho các cách truyền khác trong những trường hợp nhất định, nhưng **không nên bật URI query parameter cho API thông thường**. Header Bearer là lựa chọn phổ biến theo RFC 6750.

## 3. Cookie chứa token: browser có thể tự gửi credential

Ứng dụng có thể đặt một access token trong cookie:

~~~http
HTTP/1.1 200 OK
Set-Cookie: __Host-access_token=<opaque-or-jwt-token>; Path=/; Secure; HttpOnly; SameSite=Lax
~~~

Khi browser gửi request phù hợp:

~~~http
GET /api/orders/42 HTTP/1.1
Host: api.example.test
Cookie: __Host-access_token=<opaque-or-jwt-token>
~~~

Browser **không tự chuyển cookie thành header `Authorization: Bearer`**. Spring Security Resource Server mặc định không đọc JWT/opaque token từ cookie, vì thế muốn dùng cơ chế này cần **`BearerTokenResolver` tùy chỉnh** hoặc một authentication mechanism được thiết kế riêng.

Điểm khác biệt về an toàn nằm ở **tính tự động**: browser có thể gửi cookie khi người dùng điều hướng, submit form hoặc website khác kích hoạt request, nếu điều kiện cookie và chính sách browser cho phép. Attacker không cần **đọc được token** để thử gây một thay đổi trạng thái được xác thực.

### 3.1. Điều kiện cookie được gửi

Cookie không phải luôn xuất hiện ở mọi request. Browser xét nhiều yếu tố:

- Host và thuộc tính `Domain`.
- URL path và thuộc tính `Path`.
- Có HTTPS nếu cookie `Secure`.
- `SameSite` và ngữ cảnh same-site/cross-site.
- Browser policy về third-party cookies.
- Chế độ credentials khi JavaScript gọi cross-origin `fetch`.
- Thời hạn `Max-Age`/`Expires`.

Vì vậy “cookie được browser tự gửi” nghĩa là **khi các điều kiện trên cho phép**, không phải mọi website đều có thể gửi cookie auth tới mọi URL.

### 3.2. Cookie auth không làm JWT tự có state

Một JWT stateless đặt trong cookie vẫn phải được Spring Security xác minh chữ ký, issuer, audience, expiry và quyền. Không được dựa vào việc cookie có tên `access_token` để coi request đã xác thực. Cookie chỉ là **vỏ chuyển tải** credential.

## 4. CSRF: vì sao cookie tự gửi tạo thêm rủi ro?

**CSRF (Cross-Site Request Forgery)** là tình huống attacker khiến browser của một người đang có credential gửi request không mong muốn tới ứng dụng đích, còn server chấp nhận nhờ **credential tự động đính kèm**.

Giả sử API có:

~~~http
POST /api/orders/42/cancel HTTP/1.1
Host: api.example.test
Cookie: __Host-access_token=<access-token-cua-victim>
~~~

Một website khác có thể cố khiến browser gửi form:

~~~html
<!-- Minh họa một đường kích hoạt request, không phải code đề xuất. -->
<form action="https://api.example.test/api/orders/42/cancel"
      method="POST">
  <input type="hidden" name="confirm" value="yes">
</form>
~~~

Nếu browser gửi cookie cho request đó **và** Orders API chỉ tin cookie mà không có CSRF defense, server có thể hủy đơn dù người dùng không chủ động gọi thao tác từ Shop Web.

### 4.1. Vì sao Bearer header làm thay đổi threat model?

Một HTML form cross-site không tự gắn được Bearer header đang được SPA giữ trong JavaScript. Website attacker **không có token** nên request đến **header-only API** thường không có authentication hợp lệ.

Nhưng nếu chính browser đã được đăng nhập bằng session cookie, hoặc API chấp nhận cả cookie lẫn header, attacker có thể nhắm vào **đường cookie**, dù developer nghĩ ứng dụng “có dùng Authorization”.

**Không tuyên bố CSRF biến mất chỉ vì thấy JWT hoặc Bearer xuất hiện đâu đó trong kiến trúc.** Phải xem chính request protected chấp nhận credential nào.

### 4.2. Stateless không miễn CSRF

Sai lầm:

~~~text
JWT trong HttpOnly cookie
 + SessionCreationPolicy.STATELESS
 => không cần CSRF
~~~

**Sai.** CSRF phụ thuộc vào việc trình duyệt tự gửi credential, không phụ thuộc Spring có tạo `HttpSession` hay JWT có phải stateless không. Một API stateless đọc JWT từ cookie **vẫn cần đánh giá và bảo vệ CSRF**.

### 4.3. Request GET thay đổi trạng thái càng nguy hiểm

Nếu developer thiết kế:

~~~http
GET /api/orders/42/cancel
~~~

thì browser có thể gửi GET qua link, điều hướng hoặc tải tài nguyên. Cookie `SameSite=Lax` có thể được gửi trong một số **top-level cross-site navigation với method an toàn**, chẳng hạn GET. Dù có chống CSRF cho POST, thao tác hủy qua GET vẫn là một lỗi thiết kế.

**GET/HEAD/OPTIONS/TRACE không được có side effect nghiệp vụ không an toàn**. Không tạo/hủy đơn, chuyển tiền, đổi mật khẩu hoặc gửi email nhạy cảm qua GET.

## 5. SameSite: lớp giảm thiểu CSRF, không phải quyền truy cập

| Thuộc tính | Hành vi khái quát | Giới hạn |
| --- | --- | --- |
| `SameSite=Strict` | Chỉ gửi cookie trong ngữ cảnh same-site | Có thể ảnh hưởng luồng OAuth/OIDC callback từ site khác |
| `SameSite=Lax` | Gửi trong same-site và một số top-level cross-site navigation bằng method an toàn | Không an toàn nếu GET thay đổi trạng thái; không thay CSRF token |
| `SameSite=None; Secure` | Cho phép gửi cross-site theo chính sách browser | Cần HTTPS, CSRF; third-party cookies có thể bị browser giới hạn |
| Không đặt SameSite | Browser áp dụng default/ngoại lệ tùy phiên bản | Không nên dựa vào default làm hợp đồng bảo mật |

### 5.1. Same-site không phải same-origin

Ví dụ:

~~~text
https://shop.example.com
https://api.example.com
~~~

Hai URL có thể **same-site** nhưng là **hai origin khác nhau**. SameSite kiểm soát khi cookie được gửi theo site; Same-Origin Policy và CORS điều khiển JavaScript cross-origin access.

Điều này quan trọng khi tổ chức có **subdomain không đáng tin**. Một trang ở subdomain khác có thể là **same-site**, nên `SameSite=Strict` không đủ để thay hoàn toàn CSRF token hoặc một chính sách nguồn gốc request. Đừng coi tất cả subdomain cùng site đều cùng mức tin cậy.

### 5.2. SameSite và OAuth/OIDC redirect

Trong Authorization Code flow, browser được điều hướng đến AS rồi trở về redirect URI của Client. Cookie login/state của Client có thể cần gửi trong callback này.

`SameSite=Strict` có thể cản cookie khi callback đi từ site AS khác. `SameSite=Lax` thường tương thích với top-level GET redirect, nhưng response mode dạng `form_post` hoặc iframe có yêu cầu khác. **Hãy kiểm thử bằng browser thật với flow OIDC thực tế**; không chọn Strict chỉ vì tên nghe mạnh hơn.

### 5.3. Third-party cookie restrictions

Khi frontend và API khác **site** hoàn toàn:

~~~text
https://shop.example.com
https://api.example.net
~~~

cookie cross-site thường cần `SameSite=None; Secure` và `credentials: "include"` cho cross-origin fetch, nhưng browser vẫn có thể chặn third-party cookies. Đây là lý do kiến trúc cross-site cookie auth cần test trên browser mục tiêu thay vì chỉ dựa vào MockMvc.

## 6. Những thuộc tính cookie bảo vệ điều gì?

### 6.1. `Secure`

~~~http
Set-Cookie: __Host-access_token=<token>; Secure; HttpOnly; Path=/; SameSite=Lax
~~~

`Secure` giúp browser chỉ gửi cookie trên kết nối bảo mật theo quy tắc của nó. Vẫn cần HTTPS/TLS xuyên hệ thống và bảo vệ reverse proxy/log. `Secure` không chứng minh token đúng issuer/audience.

### 6.2. `HttpOnly`

`HttpOnly` khiến JavaScript thông thường **không thể đọc cookie auth qua `document.cookie`**. Điều này giảm một đường đánh cắp token khi XSS.

Nhưng `HttpOnly` **không ngăn browser gửi cookie**. Nếu script độc hại chạy trong **chính origin hợp lệ**, nó có thể thử gọi:

~~~javascript
// Minh họa nguyên tắc: browser có thể đính cookie hợp lệ.
await fetch("/api/orders/42/cancel", { method: "POST" });
~~~

Request này vẫn chịu CSRF token, scope và policy; không phải cứ gọi là thành công. Tuy nhiên, nó chứng minh **script không cần đọc raw cookie để sử dụng credential do browser tự gửi**.

### 6.3. `Domain` và `Path`

Cookie host-only (không đặt `Domain`) thường chỉ được gửi đến host phát cookie. Đặt `Domain=example.com` có thể khiến cookie được gửi cho nhiều subdomain hơn mức cần thiết, tăng bề mặt rủi ro. `Path` giới hạn đường request được gửi cookie, nhưng **không phải một security sandbox chống JavaScript cùng origin**.

### 6.4. Prefix `__Host-`

Cookie `__Host-access_token` yêu cầu `Secure`, `Path=/`, và **không có `Domain`** đối với browser hỗ trợ prefix đó. Điều này giúp giảm cookie shadowing/injection giữa các subdomain. Nhưng nó **không** thay CSRF, XSS defense hoặc access-token validation.

### 6.5. `Max-Age` và thời hạn token

~~~text
Cookie Max-Age = 60 phút
JWT exp        = 10 phút
~~~

Sau 10 phút, Resource Server vẫn phải từ chối JWT hết hạn dù cookie còn. Xóa cookie khi logout **không tương đương thu hồi access token** nếu token đã bị đánh cắp; cần cơ chế revocation, introspection hoặc token lifetime phù hợp.

## 7. XSS: token trong JavaScript có thể bị đánh cắp ra sao?

Một SPA gửi Bearer header thường cần token trong một môi trường mà JavaScript có thể sử dụng.

| Nơi lưu | Điểm thuận tiện | Rủi ro |
| --- | --- | --- |
| **Memory của SPA** | Không mặc định tồn tại lâu qua reload | XSS có thể gọi API, hook luồng request hoặc truy cập state nếu có đường |
| **`sessionStorage`** | Lưu theo session/tab theo browser | Script cùng origin đọc được; không phải `HttpOnly` |
| **`localStorage`** | Bền qua reload/restart | XSS có thể đọc/trích xuất; token tồn tại lâu |
| **IndexedDB** | Lưu dữ liệu có cấu trúc | JavaScript cùng origin có quyền đọc theo browser |
| **`HttpOnly` cookie** | Script web không đọc raw cookie trực tiếp | CSRF và XSS thao tác hộ vẫn có thể xảy ra |
| **BFF server-side** | Browser không nắm access token nếu thiết kế đúng | Server phải bảo vệ token/session; web vẫn có CSRF/XSS |

**`sessionStorage` không phải nơi lưu bí mật chống XSS**. Memory giảm mức lưu trữ bền vững nhưng không khiến XSS trở nên an toàn.

### 7.1. Script độc hại có thể làm nhiều việc hơn đọc token

Nếu XSS chạy trong origin Shop Web, attacker có thể:

- Đọc/chỉnh nội dung DOM và dữ liệu trả về cho ứng dụng.
- Thực hiện lệnh API thay user bằng những request được ứng dụng phép gửi.
- Can thiệp function/SDK thêm Bearer header.
- Lấy token từ storage hoặc thời điểm token được sử dụng.
- Lừa user xác nhận một giao dịch không mong muốn.

Do đó cần **output encoding, không dùng DOM injection sinks nguy hiểm, CSP được triển khai đúng, Trusted Types khi phù hợp, kiểm soát dependency và script bên thứ ba, scope tối thiểu, kiểm tra tài nguyên phía server**. Không chọn cookie hay header thay cho việc sửa lỗ hổng XSS.

### 7.2. BFF có giảm rủi ro XSS không?

Nếu BFF không gửi access token xuống browser, XSS không thể trực tiếp đọc một token **không có trong browser**. Đó là lợi ích thật. Nhưng XSS vẫn có thể gửi request qua session đến BFF và lấy dữ liệu hợp lệ mà BFF trả về. BFF **giảm token exposure**, không ngăn mọi hành động của XSS.

## 8. CORS không phải CSRF protection

**CORS** điều khiển việc JavaScript cross-origin có thể gửi một số loại request và **đọc response** theo chính sách browser. **CSRF** là rủi ro attacker kích hoạt một request có credential tự động nhằm tạo side effect.

Một frontend ở `https://shop.example.com` gọi API ở `https://api.example.com`:

~~~javascript
await fetch("https://api.example.com/api/orders/42", {
  headers: { Authorization: "Bearer " + accessToken }
});
~~~

`Authorization` là non-safelisted request header nên browser có thể gửi **CORS preflight**. API phải cấu hình origin, method và header được phép nếu muốn browser frontend đọc response.

### 8.1. Cross-origin fetch với cookie

~~~javascript
await fetch("https://api.example.com/api/orders/42", {
  credentials: "include"
});
~~~

`credentials: "include"` cho browser sử dụng credential cross-origin **nếu cookie policy cho phép**. Nó không bỏ qua SameSite, third-party cookie restriction hay CSRF validation.

API có thể trả:

~~~http
Access-Control-Allow-Origin: https://shop.example.com
Access-Control-Allow-Credentials: true
Vary: Origin
~~~

Không dùng `Access-Control-Allow-Origin: *` kèm `Access-Control-Allow-Credentials: true` để mong browser cho phép credentialed response. Cần origin allowlist có chủ đích.

### 8.2. Vì sao CORS không chặn mọi CSRF?

Một HTML form có thể gửi một request theo các giới hạn web protocol **mà không cần đọc response**. Nếu server đã thay đổi dữ liệu, việc browser chặn attacker đọc body trả về **không hoàn tác side effect**.

~~~text
Website khác -> kích hoạt request
Browser -> có thể tự gửi cookie theo cookie policy
Server -> nếu chỉ dựa cookie, thiếu CSRF defense
      -> có thể xử lý thao tác không mong muốn
Attacker -> không cần xem response
~~~

Vì thế phải phân biệt **CORS: quyền đọc response/cross-origin fetch** với **CSRF: tính hợp lệ của một hành động đến từ browser có ambient credential**.

## 9. Spring Security mặc định lấy Bearer token ở đâu?

Với `oauth2ResourceServer().jwt()` hoặc `opaqueToken()`, Spring Security Servlet thông thường sử dụng `DefaultBearerTokenResolver` để lấy token từ:

~~~http
Authorization: Bearer <access-token>
~~~

**Nó không mặc định đọc cookie `access_token` hay `__Host-access_token`.** Cookie có thể chứa locale, session, CSRF token hoặc nhiều dữ liệu khác; Spring không thể tự đoán cookie nào là OAuth credential.

### 9.1. Header-only JWT Resource Server

Ví dụ Spring Boot 3 / Spring Security 6:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configurers.AbstractHttpConfigurer;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
class HeaderBearerApiSecurity {

    @Bean
    SecurityFilterChain ordersApi(HttpSecurity http) throws Exception {
        return http
            .securityMatcher("/api/**")
            .csrf(AbstractHttpConfigurer::disable)
            .sessionManagement(session -> session
                .sessionCreationPolicy(SessionCreationPolicy.STATELESS))
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET, "/api/orders/**")
                    .hasAuthority("SCOPE_orders.read")
                .requestMatchers(HttpMethod.POST, "/api/orders/**")
                    .hasAuthority("SCOPE_orders.write")
                .anyRequest().denyAll())
            .oauth2ResourceServer(oauth2 -> oauth2
                .jwt(Customizer.withDefaults()))
            .build();
    }
}
~~~

**Lý do tắt CSRF trong ví dụ là một giả định kiến trúc rất cụ thể**: `/api/**` chỉ xác thực bằng Bearer token do Client **chủ động gửi trong header**, không xác thực bằng session cookie, access token cookie hoặc ambient HTTP credentials. **Không phải “JWT stateless nên được tắt CSRF”.**

Cấu hình issuer, audience, JWT validators và token profile vẫn cần thiết nhưng nằm ngoài nội dung transport của ví dụ. Ngoài ra, `securityMatcher("/api/**")` không tự bảo vệ URL ngoài `/api/**`; ứng dụng cần fallback chain hoặc chính sách phù hợp.

### 9.2. Không bật query token chỉ vì tiện

`DefaultBearerTokenResolver` có những tùy chọn cho token trong form body hoặc URI parameter theo các ràng buộc nhất định. Đối với API thông thường, tránh truyền access token qua query string, vì query dễ xuất hiện trong logs, history và referrers. Quyết định transport phải có hợp đồng rõ, không bật nhiều nguồn credential một cách tùy tiện.

## 10. Nếu buộc phải nhận access token từ cookie

**Cookie token là một kiến trúc có thể thực hiện nhưng cần CSRF defense**. Một cách hiểu rõ cơ chế là cung cấp một `BearerTokenResolver` chỉ đọc đúng cookie tên `__Host-access_token`.

### 10.1. Resolver cookie-only

~~~java
import jakarta.servlet.http.Cookie;
import jakarta.servlet.http.HttpServletRequest;

import org.springframework.security.oauth2.core.OAuth2AuthenticationException;
import org.springframework.security.oauth2.server.resource.BearerTokenErrors;
import org.springframework.security.oauth2.server.resource.web.BearerTokenResolver;

public final class CookieBearerTokenResolver
        implements BearerTokenResolver {

    private static final String TOKEN_COOKIE = "__Host-access_token";

    @Override
    public String resolve(HttpServletRequest request) {
        Cookie[] cookies = request.getCookies();
        if (cookies == null) {
            return null;
        }

        String found = null;
        for (Cookie cookie : cookies) {
            if (!TOKEN_COOKIE.equals(cookie.getName())) {
                continue;
            }

            String value = cookie.getValue();
            if (found != null || value == null || value.isBlank()) {
                throw new OAuth2AuthenticationException(
                    BearerTokenErrors.invalidRequest(
                        "Invalid or duplicate bearer cookie"));
            }
            found = value;
        }
        return found;
    }
}
~~~

Quy ước:

- Chỉ đọc **một cookie tên cố định**; không đọc token từ query/body.
- Nếu cookie vắng: không có Bearer credential từ nguồn cookie.
- Duplicate/empty auth cookies bị từ chối để tránh cookie shadowing/credential ambiguity.
- Không mặc định fallback sang Bearer header nếu cookie vắng. Mỗi endpoint/chain nên có **một hợp đồng nguồn credential rõ ràng**.
- Giá trị token vẫn phải đi qua **`JwtDecoder` hoặc opaque introspection**; cookie đúng tên không phải bằng chứng token hợp lệ.

Header `Cookie` của request **không truyền `Secure`, `HttpOnly`, `Domain` hoặc `SameSite`** tới server; các thuộc tính này thuộc Set-Cookie và browser policy. Vì vậy resolver không thể “kiểm tra lại” cookie đã được đánh dấu HttpOnly chỉ bằng request Cookie header.

### 10.2. Filter chain cookie-only phải bật CSRF

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.csrf.CookieCsrfTokenRepository;
import org.springframework.security.web.csrf.CsrfTokenRequestAttributeHandler;

@Configuration
class CookieBearerApiSecurity {

    @Bean
    SecurityFilterChain cookieApi(HttpSecurity http) throws Exception {
        CsrfTokenRequestAttributeHandler csrfHandler =
                new CsrfTokenRequestAttributeHandler();

        return http
            .securityMatcher("/cookie-api/**")
            .sessionManagement(session -> session
                .sessionCreationPolicy(SessionCreationPolicy.STATELESS))
            .csrf(csrf -> csrf
                .csrfTokenRepository(
                    CookieCsrfTokenRepository.withHttpOnlyFalse())
                .csrfTokenRequestHandler(csrfHandler))
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/cookie-api/orders/**")
                    .hasAuthority("SCOPE_orders.read")
                .anyRequest().denyAll())
            .oauth2ResourceServer(oauth2 -> oauth2
                .bearerTokenResolver(new CookieBearerTokenResolver())
                .jwt(Customizer.withDefaults()))
            .build();
    }
}
~~~

**Đây là ví dụ diễn giải cơ chế, chưa phải cấu hình production hoàn chỉnh.** Nó tập trung vào việc:

1. Resource Server đọc credential **từ cookie** bằng resolver tùy chỉnh.
2. CSRF **vẫn được bật** dù session policy là `STATELESS`.
3. `CookieCsrfTokenRepository.withHttpOnlyFalse()` tạo một cookie `XSRF-TOKEN` mà JavaScript **được phép đọc** để gửi trong header `X-XSRF-TOKEN`. **Cookie CSRF không phải cookie access token.**

Với SPA trên Spring Security 6, cần cân nhắc **deferred CSRF token**, **XOR masking/BREACH handling** và làm mới token sau login/logout. Ví dụ dùng `CsrfTokenRequestAttributeHandler` để nhận raw token từ header theo lối SPA; việc lựa chọn handler/CSRF token delivery phải đối chiếu đúng phiên bản và threat model. **CSRF cookie phải được sinh và phân phối trước request unsafe**, không để browser gửi POST đầu tiên mà frontend chưa có token CSRF.

Ngoài CSRF, cần cookie hardening, Origin/Referer validation phù hợp và kiểm tra subdomain không đáng tin. Nếu attacker có thể đặt CSRF cookie cùng tên, double-submit không gắn với phiên user có thể yếu; cân nhắc token có binding/signature hoặc chiến lược của framework được cấu hình đúng.

### 10.3. Phát cookie access token với thuộc tính an toàn

~~~java
import java.time.Duration;

import org.springframework.http.HttpHeaders;
import org.springframework.http.ResponseCookie;

// Chỉ minh họa sau một luồng authentication đã hợp lệ.
ResponseCookie cookie = ResponseCookie.from(
        "__Host-access_token", accessToken)
    .path("/")
    .secure(true)
    .httpOnly(true)
    .sameSite("Lax")
    .maxAge(Duration.ofMinutes(10))
    .build();

response.addHeader(HttpHeaders.SET_COOKIE, cookie.toString());
~~~

Đây là đoạn code **bên trong server response**, với `response` và `accessToken` được cung cấp bởi luồng OAuth an toàn. Không lấy một chuỗi token tùy ý từ query rồi đặt thành cookie. Prefix `__Host-` yêu cầu `Secure`, `Path=/` và không có `Domain`.

Nếu frontend/API ở hai **site** khác nhau, `SameSite=Lax` có thể không cho gửi cookie cross-site; đổi sang `SameSite=None` phải kèm `Secure`, thiết kế CSRF/CORS và test third-party cookie restrictions. Đừng coi một ví dụ cookie phù hợp mọi kiến trúc.

### 10.4. Cookie auth và Authorization header cùng xuất hiện

Một request có thể có:

~~~http
Authorization: Bearer <token-A>
Cookie: __Host-access_token=<token-B>
~~~

Nếu server nhận cả hai, cần quy định **credential precedence**, xử lý mâu thuẫn và CSRF policy. Nếu code “header không hợp lệ thì fallback sang cookie”, request có thể được xác thực bằng **chủ thể khác** với token mà Client nghĩ mình đang sử dụng. Tốt hơn nên tách endpoint/chain header-only và cookie-only, hoặc từ chối multi-source ambiguity theo hợp đồng.

## 11. BFF: browser chỉ giữ session cookie, API nhận Bearer header

Kiến trúc **Backend for Frontend** chuyển OAuth access token ra khỏi browser:

~~~mermaid
sequenceDiagram
    actor U as Người dùng
    participant B as Browser
    participant W as Shop BFF (OAuth2 Client)
    participant AS as Authorization Server
    participant API as Orders API

    U->>B: Bắt đầu đăng nhập
    B->>W: GET /oauth2/authorization/shop
    W->>AS: Authorization Code flow
    AS-->>W: Authorization code qua callback
    W->>AS: Đổi code lấy access token phía server
    AS-->>W: Access token
    W-->>B: HttpOnly Secure session cookie
    B->>W: GET /orders/42 + session cookie
    W->>W: Tìm server-side authorized client/token
    W->>API: Authorization Bearer access token
    API-->>W: Order theo scope + policy
    W-->>B: Dữ liệu/HTML theo ứng dụng
~~~

Lợi ích:

- Browser **không cần nhận OAuth access token** trong JavaScript/cookie nếu BFF được thiết kế đúng.
- BFF quản lý refresh, token rotation, logout/session revocation.
- Resource Server downstream vẫn nhận Bearer header theo cơ chế mặc định.
- Có thể dùng một origin duy nhất cho giao diện và BFF, giảm độ phức tạp CORS.

Đánh đổi:

- BFF cần quản lý **session state**, authorized client storage, TTL, HA và scaling.
- Session cookie vẫn là **ambient credential**: CSRF defense cần thiết.
- XSS trong Shop origin vẫn có thể gọi BFF thay user.
- BFF phải ngăn việc proxy URL/host tùy ý hoặc cho Client tự chèn credential vào downstream mà không kiểm tra.

### 11.1. Spring Security cấu hình OAuth2 login/session

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
class ShopBffSecurity {

    @Bean
    SecurityFilterChain web(HttpSecurity http) throws Exception {
        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/assets/**",
                                 "/login/**",
                                 "/oauth2/**").permitAll()
                .anyRequest().authenticated())
            .oauth2Login(Customizer.withDefaults())
            .oauth2Client(Customizer.withDefaults())
            .csrf(Customizer.withDefaults())
            .build();
    }
}
~~~

Đây là cấu hình của **ứng dụng BFF**, không phải chain JWT Resource Server. Cần cấu hình ClientRegistration, issuer/provider, redirect URI và lưu trữ authorized client phù hợp. BFF nên gọi Orders API với token ở phía server, **không trả access token xuống HTML/JSON hoặc cookie cho browser**.

### 11.2. Session cookie BFF

Trong Spring Boot Servlet:

~~~yaml
server:
  servlet:
    session:
      cookie:
        http-only: true
        secure: true
        same-site: lax
~~~

Đây là ví dụ cho HTTPS và một OIDC login flow dùng callback top-level GET. Nếu AS dùng response mode `form_post` hoặc có iframe/cross-site use case, cần test lại SameSite. `csrf(Customizer.withDefaults())` còn cần tích hợp đúng CSRF token trong form/fetch; cookie settings không thay CSRF.

Không phải mọi BFF đều cần Spring Session, nhưng hệ thống đa replica thường cần chiến lược session persistence/availability rõ ràng. **Session cookie không phải access token**, song nếu session ID bị chiếm thì attacker vẫn có thể chiếm phiên cho đến khi bị vô hiệu.

## 12. CSRF token: một cookie đọc được bởi JS không đồng nghĩa cookie auth

Để browser gửi POST khi authentication dựa cookie, ứng dụng có thể yêu cầu header CSRF:

~~~http
POST /cookie-api/orders/42/cancel HTTP/1.1
Host: api.example.test
Cookie: __Host-access_token=<auth-token>; XSRF-TOKEN=<csrf-token>
X-XSRF-TOKEN: <csrf-token>
Content-Type: application/json

{"reason":"customer-request"}
~~~

Ở đây có **hai giá trị khác mục đích**:

- `__Host-access_token`: Bearer credential xác thực, nên là `HttpOnly` và được Resource Server xác minh.
- `XSRF-TOKEN`/`X-XSRF-TOKEN`: token CSRF phục vụ chứng minh request được gửi từ ngữ cảnh ứng dụng dự kiến, có thể được JS đọc theo thiết kế và phải được server kiểm tra.

**CSRF token không cấp quyền `orders.cancel`**. Token auth còn phải có scope, role/permission và quyền trên Order 42.

### 12.1. Vì sao cookie CSRF có thể không HttpOnly?

Nếu frontend phải đọc CSRF token từ cookie để gắn vào custom header, CSRF cookie được thiết kế là **JS-readable**. Nó khác cookie session/access-token cần tránh bị JavaScript đọc. Không sao chép `withHttpOnlyFalse()` sang **auth cookie** chỉ vì thấy code CSRF.

### 12.2. CSRF token không thay XSS defense

Một script độc hại cùng origin có thể đọc CSRF token mà frontend được phép đọc hoặc tận dụng cơ chế gửi request của ứng dụng. Vì vậy CSRF protection giúp ngăn **cross-site request forgery**, không bảo đảm chống mọi hành vi script đã xâm nhập origin.

### 12.3. CSRF và thứ tự filter ảnh hưởng status

Với request `POST` thiếu cả authentication và CSRF token, Spring Security có thể trả **403 vì CSRF** trước khi đi tới Bearer authentication. Không mặc định mọi POST thiếu Bearer đều phải là 401 trong tất cả cấu hình.

~~~text
GET protected + không token -> thường 401
POST có cookie auth + thiếu CSRF -> thường 403
POST có cookie auth + CSRF sai -> thường 403
POST có cookie auth + CSRF đúng, scope thiếu -> 403 theo authorization
POST có cookie auth + CSRF đúng, scope đủ nhưng sai tenant -> deny theo policy
~~~

Điều cần kiểm tra nhất là **không xảy ra thao tác được bảo vệ** nếu một điều kiện chưa đạt.

## 13. So sánh hai cách truyền credential theo các cuộc tấn công

### 13.1. Request từ website khác

**Header-only:**

~~~text
Website attacker -> submit form tới Orders API
Browser không tự đính Bearer token của Shop SPA
Orders API chỉ đọc Authorization: Bearer
=> không có authentication hợp lệ
~~~

**Cookie-token:**

~~~text
Website attacker -> kích hoạt request tới Orders API
Browser có thể gửi auth cookie nếu cookie policy cho phép
Orders API đọc cookie làm Bearer credential
=> cần CSRF defense trước thao tác thay đổi dữ liệu
~~~

**BFF session:**

~~~text
Website attacker -> kích hoạt request tới BFF
Browser có thể gửi session cookie
BFF có thể dùng server-held token gọi API
=> BFF cần CSRF defense và policy nghiệp vụ
~~~

### 13.2. XSS trong Shop origin

**Header-only với token JS-readable:** có thể lộ access token và/hoặc bị gọi API thay user.

**HttpOnly auth cookie:** khó đọc raw cookie bằng `document.cookie`, nhưng script vẫn có thể dùng cookie qua request.

**BFF session:** browser không chứa access token server-side để trích xuất trực tiếp, nhưng script có thể gửi request đến BFF bằng session cookie.

### 13.3. Token bị lộ qua log

**Header-only:** tránh log toàn bộ `Authorization` header.

**Cookie-token/session:** tránh log toàn bộ `Cookie` hoặc `Set-Cookie`, session ID, CSRF token không cần thiết và credentials.

**Cả hai:** không đặt token trong query string, URL redirect, analytics payload hoặc response lỗi.

## 14. Kiểm thử: cần chứng minh transport, token validation và policy

Để kiểm chứng hệ thống, nên tách:

1. **Credential transport:** Spring lấy token từ header hay cookie? Có xử lý duplicate/mixed credential đúng không?
2. **Token verification:** JWT có được kiểm tra chữ ký/issuer/audience/time? Opaque có introspection đúng không?
3. **CSRF:** với cookie auth, request unsafe không có/sai CSRF token có bị chặn không?
4. **Authorization:** scope, role, owner, tenant và hành động nghiệp vụ có đúng không?
5. **Browser behavior:** SameSite, CORS, cookie flags, OAuth callback có hoạt động như dự kiến không?

### 14.1. Ma trận test mẫu

| Test case | Header-only API | Cookie-token API | BFF |
| --- | --- | --- | --- |
| GET protected không credential | 401 điển hình | 401 điển hình | Redirect/401 theo session policy |
| GET chỉ có cookie token | **Không tự xác thực** | Xác thực nếu cookie token hợp lệ | Session xác thực nếu cookie là session ID hợp lệ |
| GET chỉ có Authorization Bearer | Xác thực token hợp lệ | Không tự dùng header nếu resolver cookie-only | Không nhất thiết nhận browser Bearer |
| POST có cookie auth, thiếu CSRF | Không áp dụng nếu cookie không phải auth | **Deny** | **Deny** |
| POST có cookie auth, CSRF sai | Không áp dụng | **Deny** | **Deny** |
| CSRF đúng nhưng scope thiếu | 403 khi Bearer token thiếu scope | 403 | BFF/downstream policy deny |
| JWT sai chữ ký hoặc aud | **Deny** | **Deny** | Downstream Resource Server deny |
| Token hết hạn nhưng cookie chưa hết | Không nhận token hết hạn | **Deny** | BFF xử lý token lifecycle |
| Role/scope đủ, owner khác tenant | **Deny ở data policy** | **Deny ở data policy** | **Deny ở data policy** |
| Request cross-site từ form | Không có Bearer header tự động | Kiểm tra SameSite/CSRF | Kiểm tra SameSite/CSRF |

**HTTP status cụ thể có thể thay đổi theo filter order và exception handling**, đặc biệt POST thiếu cả CSRF lẫn authentication. Test nên chứng minh **không có side effect** và xác định đúng lớp bị chặn.

### 14.2. Unit test CookieBearerTokenResolver

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNull;
import static org.junit.jupiter.api.Assertions.assertThrows;

import jakarta.servlet.http.Cookie;
import org.junit.jupiter.api.Test;
import org.springframework.mock.web.MockHttpServletRequest;
import org.springframework.security.oauth2.core.OAuth2AuthenticationException;

class CookieBearerTokenResolverTest {

    private final CookieBearerTokenResolver resolver =
            new CookieBearerTokenResolver();

    @Test
    void noCookieMeansNoBearerToken() {
        assertNull(resolver.resolve(new MockHttpServletRequest()));
    }

    @Test
    void readsOnlyDesignatedCookie() {
        var request = new MockHttpServletRequest();
        request.setCookies(
            new Cookie("theme", "dark"),
            new Cookie("__Host-access_token", "test-token"));

        assertEquals("test-token", resolver.resolve(request));
    }

    @Test
    void rejectsDuplicateAuthCookies() {
        var request = new MockHttpServletRequest();
        request.setCookies(
            new Cookie("__Host-access_token", "token-A"),
            new Cookie("__Host-access_token", "token-B"));

        assertThrows(OAuth2AuthenticationException.class,
            () -> resolver.resolve(request));
    }

    @Test
    void headerDoesNotBecomeCookieCredential() {
        var request = new MockHttpServletRequest();
        request.addHeader("Authorization", "Bearer header-token");
        assertNull(resolver.resolve(request));
    }
}
~~~

Test này chỉ kiểm tra resolver, **không chứng minh JWT/token hợp lệ**. Cần integration test riêng với signed JWT hoặc mock introspection.

### 14.3. MockMvc CSRF test

Spring Security Test có `csrf()` để giả lập CSRF token hợp lệ:

~~~java
import static org.springframework.security.test.web.servlet.request
        .SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.test.web.servlet.request
        .MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result
        .MockMvcResultMatchers.status;

// Phần thân test minh họa: đã có MockMvc, controller,
// SecurityFilterChain và decoder/introspector test phù hợp.

mockMvc.perform(post("/cookie-api/orders/42")
        .cookie(new Cookie("__Host-access_token", "valid-test-token")))
    .andExpect(status().isForbidden());

// Có CSRF: chỉ vượt được CSRF filter;
// authentication, scope và owner/tenant vẫn phải được kiểm tra.
mockMvc.perform(post("/cookie-api/orders/42")
        .cookie(new Cookie("__Host-access_token", "valid-test-token"))
        .with(csrf()));
~~~

`csrf()` **không mô phỏng đầy đủ browser tạo/đọc cookie CSRF thực tế**, và `valid-test-token` phải được decoder/introspector test công nhận theo fixture. Muốn kiểm chứng luồng end-to-end, dùng mock AS/JWKS và browser thật.

### 14.4. `jwt()` không test token transport

~~~java
mockMvc.perform(get("/api/orders/42")
    .with(jwt().authorities(
        new SimpleGrantedAuthority("SCOPE_orders.read"))));
~~~

`jwt()` của Spring Security Test **giả lập `JwtAuthenticationToken`**. Nó hữu ích để kiểm tra HTTP authorization nhưng **không chứng minh** Bearer header/cookie resolver đang hoạt động, cũng **không kiểm tra chữ ký, issuer hoặc audience thật**.

### 14.5. Browser E2E test

MockMvc không mô phỏng đầy đủ:

- SameSite và third-party cookie policies.
- Cross-origin fetch, CORS preflight và credential mode.
- OIDC redirect/`form_post` callback.
- Trailing slash/rewrites qua gateway.
- Xóa cookie khi logout hoặc expiry trong browser.

Sử dụng browser E2E test để xác nhận cookie flags, actual request headers, CSRF từ origin không tin cậy, CORS và login callback. Với request bị từ chối, **kiểm tra không có database/event side effect**.

## 15. Chọn mô hình phù hợp với Client

### Mobile và machine-to-machine

**Bearer Authorization header** thường phù hợp. Những Client không phải browser không tự gửi cookie theo cách browser thường làm, nên CSRF không phải rủi ro trung tâm; vẫn phải chống token theft/replay, sai audience, quyền quá rộng và credential leakage.

### SPA gọi API trực tiếp

Có thể dùng **Authorization Code + PKCE** cho public OAuth2 Client rồi gửi access token trong header. Không nhúng Client secret trong JavaScript. Cân nhắc memory storage, access token sống ngắn và refresh/reauthorization theo khuyến nghị AS/SDK thực tế; localStorage dễ tạo rủi ro token extraction khi XSS.

### Web frontend và backend do cùng một đội kiểm soát

**BFF/session cookie** đáng cân nhắc nếu không muốn browser giữ OAuth access token. Đổi lại cần session/CSRF, server-side token storage, scaling và lifecycle management.

### Muốn auth cookie để JavaScript không đọc token

Có thể dùng `HttpOnly` cookie chứa token, **nhưng phải bật CSRF**, kiểm soát cookie domain/SameSite/CORS và tùy biến BearerTokenResolver. Không copy header-only `csrf.disable()` sang chain cookie.

### Frontend/API khác site hoàn toàn

Cross-site cookie có thể phức tạp vì `SameSite=None; Secure` và third-party cookie restrictions. Bearer header hoặc BFF same-origin có thể đơn giản hơn tùy hệ thống. Quyết định cần dựa trên browser mục tiêu và threat model thực tế.

## 16. Các hiểu nhầm thường gặp

**“JWT stateless thì không cần CSRF.”** Không đúng nếu JWT nằm trong cookie browser tự gửi.

**“Cookie HttpOnly chặn XSS hoàn toàn.”** Không. Nó ngăn đọc cookie trực tiếp bằng JavaScript, nhưng XSS vẫn có thể thao tác qua request authenticated.

**“Bearer header làm access token không bao giờ bị lộ.”** Không. Nếu JavaScript giữ token, XSS/supply-chain compromise có thể đọc hoặc dùng nó.

**“sessionStorage an toàn hơn localStorage trước XSS.”** Không theo nghĩa chống script độc hại cùng origin; cả hai đều JS-readable.

**“CORS chặn mọi CSRF.”** Không. Attacker có thể chỉ cần gây side effect mà không đọc response.

**“SameSite=Strict thay hoàn toàn CSRF token.”** Không. Same-site subdomain, browser behavior và OAuth callback là những ranh giới cần tính.

**“Spring Resource Server tự đọc access token trong cookie.”** Không mặc định; cần resolver/authentication tùy biến.

**“Một cookie có tên __Host-access_token là credential hợp lệ.”** Tên cookie không chứng minh JWT signature/issuer/audience/expiry hoặc opaque active.

**“CSRF token đúng nghĩa là có quyền hủy đơn.”** Không. CSRF defense không thay OAuth scope hoặc quyền trên owner/tenant.

**“BFF không có rủi ro vì token ở server.”** Vẫn có session hijacking, CSRF, XSS thao tác hộ và rủi ro server-side token storage.

**“Cookie Max-Age có thể kéo dài hạn JWT.”** Không. Token hết hạn vẫn phải bị từ chối.

**“Chỉ cần disable CSRF cho REST JSON.”** Không. Quyết định CSRF dựa vào ambient credential, không dựa tên REST/JSON.

**“Đặt access token vào URL tiện để debug.”** Không nên; query string dễ bị lưu và lộ.

**“Cùng site nghĩa cùng origin.”** Không. SameSite và CORS/Same-Origin Policy dùng những ranh giới khác nhau.

**“API đã có CORS allowlist nên curl hoặc server khác không gọi được.”** CORS là cơ chế trình duyệt, không phải authentication; API vẫn cần kiểm tra token và quyền.

## 17. Hợp đồng triển khai mẫu

### A. Header-only Orders API

~~~yaml
# Tài liệu hợp đồng, không phải cấu hình Spring tự đọc.
resource_server: orders-api
token_format: jwt
authentication_transport: authorization_bearer_header_only
cookie_authentication: not_accepted
trusted_issuer: https://identity.example.test/realms/shop
expected_audience: orders-api
csrf: disabled_for_this_chain_only_because_no_ambient_auth
authorization:
  GET_orders: SCOPE_orders.read
  POST_orders: SCOPE_orders.write
  data_policy: owner_and_tenant
tests:
  - missing_header_denied_even_if_cookie_present
  - signed_jwt_validated
  - wrong_issuer_or_audience_denied
  - insufficient_scope_denied
~~~

### B. Cookie-token Orders API

~~~yaml
# Tài liệu hợp đồng, không phải cấu hình Spring tự đọc.
resource_server: cookie-orders-api
authentication_transport: "__Host-access_token cookie only"
cookie:
  secure: true
  http_only: true
  same_site: lax
  path: /
  domain: omitted_host_only
token_validation: jwt_signature_issuer_audience_exp
csrf:
  enabled: true
  required_on_unsafe_methods: true
  token_delivery: dedicated_csrf_cookie_or_endpoint
  expected_header: X-XSRF-TOKEN
  origin_policy: controlled
authorization:
  GET_orders: SCOPE_orders.read
  POST_orders: SCOPE_orders.write
  data_policy: owner_and_tenant
tests:
  - missing_or_invalid_csrf_denied
  - valid_csrf_but_insufficient_scope_denied
  - duplicate_auth_cookie_denied
  - bearer_header_does_not_override_cookie_contract
  - cross_site_browser_behavior_tested
~~~

Một ứng dụng BFF sẽ có hợp đồng thứ ba: **browser gửi session ID**, BFF lưu OAuth token phía server, kiểm tra CSRF/session, và downstream Orders API vẫn nhận **Bearer header**.

## 18. Tình huống thực hành

**A.** JWT đặt trong `HttpOnly` cookie, server dùng `STATELESS` và tắt CSRF. An toàn chưa?

**Chưa.** Cookie vẫn tự gửi. Stateless không xóa rủi ro CSRF; phải có CSRF strategy phù hợp.

**B.** SPA lưu token trong `localStorage` rồi gọi API bằng Bearer header. Khi trang có XSS, token có thể bị lấy không?

**Có nguy cơ.** Script cùng origin có thể đọc localStorage hoặc sử dụng luồng gửi request.

**C.** Cookie `HttpOnly`, attacker XSS không đọc được `document.cookie`. Có thể gọi API thay user không?

**Có thể.** Browser vẫn có thể gửi cookie khi script cùng origin gọi request; còn phải kiểm tra CSRF/authority/policy.

**D.** `SameSite=Lax` và một URL GET thực hiện xóa dữ liệu. Có vấn đề không?

**Có.** Top-level cross-site GET có thể mang cookie Lax. GET không được có side effect nguy hiểm.

**E.** CORS chặn origin attacker đọc response. Có cần CSRF khi API xác thực bằng cookie?

**Có.** Attacker có thể chỉ cần gửi request tạo side effect, không cần đọc response.

**F.** Client gửi cookie tên `access_token` tới Spring Resource Server chỉ có `oauth2ResourceServer().jwt()`. Nó có tự được xác thực không?

**Không mặc định.** Resource Server thường tìm `Authorization: Bearer`; cookie cần resolver riêng.

**G.** BFF chỉ cho browser session cookie, không gửi OAuth access token. Có hết XSS/CSRF không?

**Không.** Giảm exposure của access token nhưng session vẫn là ambient credential và script cùng origin vẫn có thể thao tác hộ.

**H.** Cookie auth + CSRF header đúng, nhưng token chỉ có `orders.read` và request muốn hủy đơn. Có cho phép không?

**Không.** CSRF không cấp OAuth scope hay quyền trên đối tượng. Còn phải kiểm tra `orders.cancel` và owner/tenant/trạng thái.

**I.** Header-only API bất ngờ nhận cả cookie và header do một thay đổi resolver. Điều gì cần xem lại?

**Credential precedence, CSRF, chain selection và test không chấp nhận cookie ngầm.** Không dùng fallback âm thầm sang một credential browser tự gửi.

**J.** Frontend/API khác origin nhưng cùng site. `SameSite=Lax` có nghĩa browser JS được đọc response không?

**Không.** SameSite quyết định gửi cookie, còn CORS điều khiển JavaScript đọc response cross-origin.

---

## Kết luận

**Cookie chứa access token** và **Authorization header chứa access token** khác nhau ở chỗ **cookie có thể được trình duyệt tự động gửi**, còn Bearer header thường được OAuth2 Client/JavaScript gắn một cách chủ động. Vì thế **cookie auth phải đối mặt với CSRF**, ngay cả khi cookie chứa JWT stateless; **header-only SPA phải đặc biệt chú ý XSS và việc lưu token trong JavaScript**. `HttpOnly` giúp hạn chế đọc trộm cookie nhưng không chặn mọi hành động XSS; `SameSite`, `Secure` và CORS là những lớp bảo vệ bổ sung, không phải thay thế CSRF hoặc authorization.

Với Spring Security Resource Server, `jwt()`/`opaqueToken()` **mặc định nhận `Authorization: Bearer`**, không tự đọc cookie. Khi chủ động nhận token trong cookie, cần **`BearerTokenResolver` riêng, cookie hardening và CSRF defense cho unsafe requests**; `SessionCreationPolicy.STATELESS` không thay đổi yêu cầu đó. Với hệ thống web muốn giữ OAuth token ngoài browser, **BFF dùng session cookie và gửi Bearer header từ server tới API** là một phương án đáng cân nhắc, nhưng vẫn cần CSRF, XSS defense và session protection. Bất kể cách truyền credential, Resource Server luôn phải xác minh token, scope/authorities và quyền trên **owner, tenant, tài nguyên thực tế** trước khi xử lý thao tác được bảo vệ.
