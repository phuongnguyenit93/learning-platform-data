# 23.10. Cookie Secure, HttpOnly, SameSite và quan hệ với OAuth callback

## 1. Bối cảnh: OAuth2 login thất bại dù authorization code và redirect URI có vẻ đúng

Giả sử **Employee Portal** dùng **Spring Boot 3, Spring Security 6, Spring MVC/Servlet** làm một **OAuth2/OIDC Client**. Người dùng truy cập:

~~~text
https://portal.example.test
~~~

và đăng nhập qua OpenID Provider (OP):

~~~text
https://login.identity.example
~~~

Portal sử dụng Authorization Code Flow. Browser được chuyển sang OP, người dùng xác thực, rồi browser điều hướng trở lại:

~~~http
GET /login/oauth2/code/company?code=abc&state=xyz HTTP/1.1
Host: portal.example.test
~~~

Nhưng ứng dụng trả lỗi như:

~~~text
authorization_request_not_found
invalid_state_parameter
OAuth2AuthenticationException
Login failed: authorization request not found
~~~

Một nguyên nhân quan trọng là **browser không gửi cookie phiên của Portal trong request callback**. Lúc đó Spring Security không tìm lại được authorization request đã lưu trước khi redirect đến OP.

Vấn đề không nhất thiết nằm ở `client-secret`, `redirect-uri` hay token endpoint. Cookie có thể đã bị chặn bởi thuộc tính:

- `Secure`: cookie chỉ được gửi qua kết nối an toàn phù hợp.
- `HttpOnly`: JavaScript không đọc trực tiếp cookie.
- `SameSite`: kiểm soát việc browser gửi cookie trong ngữ cảnh same-site/cross-site.
- `Domain` và `Path`: giới hạn host/path nhận cookie.

**Trọng tâm bài học:** OAuth2/OIDC callback không chỉ là một HTTP endpoint. Nó là một **lượt điều hướng của browser** cần tiếp tục đúng trạng thái authorization trước đó. Cookie policy quyết định Spring Security còn nhìn thấy session chứa `state`, thông tin authorization request, `nonce` và PKCE metadata hay không.

> Ví dụ sử dụng Java 17+, Spring Boot 3, Spring Security 6 và Servlet. Phần WebFlux/Spring Session được phân biệt riêng. Browser và chính sách cookie có thể thay đổi theo phiên bản và chế độ bảo vệ quyền riêng tư; cần thử nghiệm trên browser thực, không chỉ gọi callback bằng curl.

## 2. Phân biệt cookie phiên, token và trạng thái OAuth2

Ba đối tượng sau **không đồng nghĩa**:

| Đối tượng | Nơi tồn tại phổ biến | Vai trò |
|---|---|---|
| **Session cookie** như `JSESSIONID` hoặc `SESSION` | Browser giữ một **session identifier** | Browser gửi ID để Portal tìm server-side session |
| **HttpSession / server-side session** | Servlet container, Spring Session hoặc distributed session store | Lưu trạng thái đăng nhập và có thể lưu authorization request |
| **OAuth2AuthorizedClient** | Authorized-client repository/service | Chứa access token và có thể chứa refresh token của OAuth client |

Trong kiến trúc **backend-for-frontend (BFF)**, browser thường chỉ cần cookie phiên:

~~~text
Browser:
  Cookie: JSESSIONID=<opaque-session-id>

Portal backend:
  HttpSession:
    SecurityContext
    OAuth2 authorization request (khi login chưa hoàn tất)

  OAuth2AuthorizedClientRepository/Service:
    access token
    refresh token (nếu được cấp)
~~~

Browser **không cần** giữ OAuth2 access token hoặc refresh token trong cookie để Spring Security gọi Resource Server. Khi Portal là server-side OAuth2 Client, nên ưu tiên để token được bảo vệ ở backend và browser chỉ mang session cookie.

### 2.1. Callback cần gì từ session?

Trước khi chuyển browser sang Authorization Server, Spring Security thường tạo **OAuth2AuthorizationRequest** với những thông tin như:

- `registrationId`, client ID, authorization URI, scopes.
- `redirect_uri` và `state` ngẫu nhiên.
- PKCE `code_verifier` / `code_challenge` nếu áp dụng.
- OIDC `nonce` khi cần xác minh ID Token.
- Thuộc tính bổ sung được authorization request resolver tạo ra.

Mặc định trên Servlet, Spring Security thường lưu authorization request bằng:

~~~java
org.springframework.security.oauth2.client.web
    .HttpSessionOAuth2AuthorizationRequestRepository
~~~

Nếu browser quay lại mà **không mang đúng session cookie**, callback có thể không tìm được authorization request đã phát, dù `code` và `state` vẫn có mặt trên URL.

**Không nên “sửa lỗi” bằng cách bỏ kiểm tra state, nonce hoặc PKCE.** Đây là các cơ chế bảo vệ, không phải thành phần trang trí.

## 3. Luồng Authorization Code Flow và thời điểm cookie được sử dụng

~~~mermaid
sequenceDiagram
    actor Browser as Browser
    participant RP as Portal / Spring Security
    participant OP as OpenID Provider
    participant Session as Server-side Session Store

    Browser->>RP: GET /oauth2/authorization/company
    RP->>Session: Tạo/lưu authorization request với state, nonce, PKCE
    RP-->>Browser: 302 Location: OP /authorize + Set-Cookie: SESSION=...; Secure; HttpOnly; SameSite=Lax
    Browser->>OP: GET /authorize?...&state=...
    OP-->>Browser: Xác thực và 302 callback URL
    Browser->>RP: GET /login/oauth2/code/company?code=...&state=... + Cookie: SESSION=...
    RP->>Session: Tải authorization request bằng session cookie
    Session-->>RP: state, nonce, PKCE metadata
    RP->>RP: So sánh state, đổi code lấy token, validate OIDC
    RP-->>Browser: Login thành công, có thể xoay session ID
~~~

Điểm then chốt:

1. **Portal tạo session hoặc sử dụng session hiện có** trước khi redirect.
2. Browser lưu cookie do **Portal** phát, không phải do OP phát.
3. Browser thực hiện một hoặc nhiều điều hướng tới OP.
4. Khi OP trả browser về callback, browser quyết định **có gửi cookie của Portal hay không**.
5. Spring Security sử dụng session tương ứng để kiểm tra correlation.

Cookie từ `login.identity.example` **không thay thế** cookie của `portal.example.test`. Hai bên có session và security policy riêng.

### 3.1. OIDC redirect không chỉ là trả token

Trên callback, Spring Security phải ghép **authorization response** với **authorization request gốc**. `state` chống CSRF/login swapping ở tầng authorization; `nonce` gắn ID Token với yêu cầu xác thực; PKCE ràng buộc việc đổi authorization code với client đã khởi tạo.

Nếu session bị mất, việc vẫn có authorization code không đủ để chứng minh flow thuộc về browser hiện tại.

## 4. Cookie là gì trong HTTP?

HTTP response có thể đặt cookie:

~~~http
HTTP/1.1 302 Found
Location: https://login.identity.example/authorize?...
Set-Cookie: JSESSIONID=opaque-id; Path=/; Secure; HttpOnly; SameSite=Lax
~~~

Ở lần request tiếp theo đến URL phù hợp, browser có thể gửi:

~~~http
GET /login/oauth2/code/company?code=...&state=... HTTP/1.1
Host: portal.example.test
Cookie: JSESSIONID=opaque-id
~~~

**Cookie request header không chứa lại những thuộc tính** `Secure`, `HttpOnly` hoặc `SameSite`. Các thuộc tính nằm trong `Set-Cookie` khi browser nhận cookie và được browser áp dụng khi quyết định gửi.

Một session cookie thường có:

- **Name**: `JSESSIONID` hoặc `SESSION`.
- **Value**: session ID không đoán được; không nên là dữ liệu user công khai.
- **Path**: request path được phép nhận cookie.
- **Domain**: host hoặc nhóm host được phép nhận nếu được cấu hình.
- **Secure, HttpOnly, SameSite**: các ràng buộc browser.
- **Expires/Max-Age**: nếu là persistent cookie; session cookie không nhất thiết có expiry cố định trong browser.

**Cookie có thể tồn tại trong browser lâu hơn hoặc ngắn hơn HttpSession phía server.** Browser còn cookie không đồng nghĩa session server vẫn hợp lệ; ngược lại, server còn session không giúp browser nếu cookie đã mất.

## 5. Secure: vì sao callback phải đi qua HTTPS?

Cookie có `Secure` chỉ được browser gửi trên những kết nối được browser coi là an toàn, thông thường **HTTPS**.

~~~http
Set-Cookie: JSESSIONID=abc; Path=/; Secure; HttpOnly; SameSite=Lax
~~~

Nếu ứng dụng đặt cookie Secure khi browser truy cập:

~~~text
https://portal.example.test
~~~

thì trong điều kiện bình thường browser gửi cookie ở callback HTTPS phù hợp:

~~~text
https://portal.example.test/login/oauth2/code/company
~~~

Nhưng nếu redirect URI được tạo sai:

~~~text
http://portal.example.test/login/oauth2/code/company
~~~

cookie Secure có thể **không được gửi**, đồng thời flow còn vi phạm yêu cầu dùng kênh an toàn của OAuth/OIDC production.

### 5.1. Secure không có nghĩa cookie không bao giờ bị đánh cắp

`Secure` giảm nguy cơ cookie bị gửi qua plaintext HTTP. Nó **không**:

- Ngăn XSS dùng trình duyệt thực hiện các request với cookie của user.
- Tự chống CSRF.
- Ngăn cookie bị lấy từ log/proxy/browser bị compromise.
- Tự bảo đảm server-side session được mã hóa hoặc phân quyền đúng.

Cần HTTPS, HSTS, bảo mật ứng dụng, cấu hình proxy đúng và session management phù hợp.

### 5.2. Localhost và môi trường phát triển

Một số browser có ngoại lệ hoặc xử lý đặc biệt cho **localhost** với Secure cookies. Không nên dựa vào ngoại lệ này để suy luận hành vi trên domain public.

Production nên dùng HTTPS end-to-end ở phía browser. Khi test local, có thể dùng HTTPS local hoặc một profile phát triển riêng có cấu hình cookie thích hợp; **không vô hiệu Secure cho production chỉ vì test HTTP localhost lỗi**.

## 6. HttpOnly: JavaScript không đọc session cookie, nhưng browser vẫn gửi cookie

~~~http
Set-Cookie: JSESSIONID=abc; Path=/; Secure; HttpOnly; SameSite=Lax
~~~

`HttpOnly` ngăn JavaScript truy cập cookie qua các API như:

~~~javascript
document.cookie
~~~

Do đó, nếu frontend chạy:

~~~javascript
console.log(document.cookie);
~~~

và không thấy `JSESSIONID`, đó **có thể là hành vi đúng và an toàn**.

**HttpOnly không chặn browser tự gửi cookie** tới URL phù hợp. Khi user gọi callback, cookie HttpOnly vẫn có thể được gửi bình thường nếu Secure, Domain, Path, SameSite và chính sách browser cho phép.

### 6.1. HttpOnly không triệt tiêu tác hại của XSS

Mã JavaScript độc hại không đọc trực tiếp giá trị session cookie HttpOnly, nhưng có thể phát request bằng phiên hiện tại và đọc dữ liệu frontend được phép truy cập nếu XSS xảy ra trong same-origin context.

Vì vậy cần:

- Escape/encode output và phòng tránh XSS.
- Content Security Policy phù hợp.
- Không đưa access/refresh token vào DOM hoặc JavaScript không cần thiết.
- Authorization phía server cho mọi thao tác.
- Cookie HttpOnly kết hợp Secure và SameSite, không phải dùng thay các biện pháp khác.

### 6.2. Cookie CSRF không phải session cookie

Một số SPA dùng `XSRF-TOKEN` cookie để JavaScript đọc rồi gửi lại giá trị trong header chống CSRF. Cookie đó có thể được cấu hình **không HttpOnly** theo pattern của framework.

Điều này **không có nghĩa phải bỏ HttpOnly trên session cookie**. Phân biệt:

~~~text
SESSION / JSESSIONID: giữ HttpOnly = true.
XSRF-TOKEN: cơ chế đọc bằng JS tùy CSRF strategy.
~~~

OAuth2 `state` cũng không phải là `XSRF-TOKEN` cookie; chúng bảo vệ những luồng khác nhau.

## 7. SameSite: khái niệm quyết định cookie có được gửi trong OAuth callback

`SameSite` có ba giá trị quan trọng:

| Giá trị | Ý nghĩa tổng quan | Ảnh hưởng callback OAuth từ IdP khác site |
|---|---|---|
| `Strict` | Cookie chỉ được gửi trong ngữ cảnh same-site | Cross-site callback thường **không mang session cookie** |
| `Lax` | Cho phép cookie trong same-site và một số **top-level navigation** an toàn | Phù hợp với **top-level GET callback** thường gặp |
| `None` | Cho phép cookie trong ngữ cảnh cross-site nếu browser cho phép | Có thể cần cho **form_post POST callback**, nhưng **phải có Secure** |

**SameSite không phải CORS**, và **site không đồng nghĩa origin**.

### 7.1. Site là gì?

Trong mô hình browser hiện đại, **schemeful same-site** xét scheme và registrable domain (dựa trên Public Suffix List). Ví dụ:

~~~text
https://portal.example.com
https://admin.example.com
~~~

thường cùng **site** (`https://example.com`) nhưng **khác origin** vì hostname khác nhau.

~~~text
https://portal.example.com
https://login.other-idp.test
~~~

là **cross-site**.

~~~text
http://portal.example.com
https://portal.example.com
~~~

được xem là **cross-site theo schemeful same-site** dù hostname giống nhau.

Vì vậy, khi phân tích cookie callback, phải biết **scheme, host và cách browser định nghĩa site**, không chỉ nhìn hai URL có chữ `example`.

### 7.2. Cùng site vẫn có thể khác origin

Hai host:

~~~text
https://portal.example.com
https://api.example.com
~~~

thường được xem là same-site, nhưng request JavaScript cross-origin vẫn bị **Same-Origin Policy/CORS** chi phối.

Ngược lại, OAuth callback top-level GET từ một IdP cross-site có thể được SameSite=Lax cho gửi cookie mà **không cần CORS**, vì đó là browser navigation, không phải `fetch()`.

## 8. SameSite=Lax với top-level GET callback — trường hợp phổ biến

Authorization Code Flow mặc định thường trả browser về RP bằng **GET** với `code` và `state` trong query:

~~~text
IdP:
  https://login.identity.example
       |
       | 302 Location
       v
Portal:
  https://portal.example.test/login/oauth2/code/company
    ?code=...
    &state=...
~~~

Browser đang thực hiện **top-level navigation GET** từ site IdP về site Portal. Cookie `SameSite=Lax` của Portal **thường được gửi** nếu những điều kiện khác (Secure, Domain, Path, expiry, browser policy) đúng.

~~~http
Set-Cookie: JSESSIONID=abc; Path=/; Secure; HttpOnly; SameSite=Lax
~~~

**Lax là lựa chọn thường phù hợp cho session cookie của một ứng dụng web server-rendered/BFF dùng OAuth2 Authorization Code Flow với GET callback.** Nó giảm bề mặt CSRF so với None nhưng vẫn hỗ trợ lượt điều hướng callback thông dụng.

### 8.1. Lax chỉ cho phép một số top-level navigations an toàn

Điểm cần nhớ:

- **Top-level navigation**: browser đổi trang/tab hiện tại sang Portal.
- **Safe HTTP method**: trong trường hợp thông dụng là GET.
- **Cross-site POST**: không được gửi cookie `SameSite=Lax` theo nguyên tắc mặc định.
- **Cross-site iframe/fetch**: không được hưởng ngoại lệ top-level GET.

Không suy từ “IdP redirect về Portal” rằng **mọi callback mode đều tương thích Lax**. Cần xác định callback là GET hay POST và có phải top-level navigation không.

## 9. SameSite=Strict: tăng hạn chế nhưng có thể làm đứt OAuth callback

~~~http
Set-Cookie: JSESSIONID=abc; Path=/; Secure; HttpOnly; SameSite=Strict
~~~

Nếu browser quay về từ IdP cross-site:

~~~text
login.identity.example
      |
      | redirect GET
      v
portal.example.test/login/oauth2/code/company
~~~

cookie Strict của Portal **có thể không được gửi**. Portal tạo session mới hoặc không tìm thấy session cũ, và Spring Security mất authorization request đã lưu với `state`.

Kết quả:

~~~text
Người dùng đăng nhập IdP thành công.
IdP trả authorization code hợp lệ.
Portal không tìm thấy authorization request của session cũ.
OAuth login thất bại.
~~~

**Không thể sửa bằng cách bỏ kiểm tra state.** Nếu session cần tồn tại qua cross-site redirect, cookie Strict có thể không đáp ứng flow.

### 9.1. Strict có thể hoạt động trong một số triển khai same-site

Nếu IdP và Portal thuộc cùng schemeful site, hoặc luồng navigation có đặc điểm khác, cookie Strict có thể được gửi. Tuy nhiên, **không nên dựa trên giả định IdP luôn same-site**: các tổ chức có thể đổi sang IdP ngoài, dùng broker hoặc liên kết nhiều nhà cung cấp.

Hãy test thực tế từng IdP và callback mode. Với browser-login dùng IdP cross-site, Lax thường thực dụng hơn Strict.

## 10. SameSite=None: khi nào cần và rủi ro gì?

~~~http
Set-Cookie: JSESSIONID=abc; Path=/; Secure; HttpOnly; SameSite=None
~~~

`SameSite=None` yêu cầu **Secure** trên browser hiện đại. Cookie có:

~~~http
Set-Cookie: JSESSIONID=abc; SameSite=None
~~~

nhưng **thiếu Secure** có thể bị browser từ chối ngay khi nhận.

None cho phép browser gửi cookie trong các ngữ cảnh cross-site mà Strict/Lax sẽ chặn, **nếu** browser cho phép cookie đó. Điều này hữu ích khi:

- IdP trả callback bằng **cross-site POST** (OIDC `response_mode=form_post`).
- Ứng dụng thực sự phải hoạt động trong iframe/cross-site embedded context theo một kiến trúc được phê duyệt.
- Một integration hợp lệ đòi cookie trong ngữ cảnh third-party.

Đổi lại:

- Cookie được gửi trong nhiều cross-site contexts hơn, tăng rủi ro CSRF nếu ứng dụng thiếu bảo vệ.
- Browser có thể chặn third-party cookie vì privacy settings, tracking prevention hoặc enterprise policy.
- `SameSite=None` **không bảo đảm** mọi browser/iframe đều cho phép cookie.

**None không phải “chế độ sửa tất cả lỗi OAuth callback”.** Nó phải được chọn cho callback mode và kiến trúc cụ thể, đi kèm CSRF/state/nonce/PKCE, TLS và kiểm thử browser.

### 10.1. None và third-party cookie blocking không phải một điều

Một cookie được đặt `SameSite=None; Secure` có thể thỏa điều kiện SameSite nhưng vẫn bị browser chặn trong iframe vì chính sách third-party cookies.

Ngược lại, một **top-level redirect** về Portal không giống một tài nguyên Portal nằm trong iframe third-party. Vì vậy cần phân biệt browser navigation và embedded login.

## 11. Bảng quyết định SameSite theo callback mode

| Tình huống | Browser request đến Portal | Lax | Strict | None + Secure |
|---|---|---|---|---|
| IdP cross-site redirect về Portal | **Top-level GET** | **Thường gửi cookie** | **Thường không gửi** | Có thể gửi |
| OIDC `response_mode=form_post` | **Top-level POST** | **Thông thường không gửi** | Không gửi nếu cross-site | Có thể gửi |
| Portal trong cross-site iframe | Request iframe/navigation | Thường không gửi | Thường không gửi | Có thể gửi nhưng còn third-party policy |
| Portal gọi chính nó cùng site | Same-site request | Gửi nếu thuộc tính khác đúng | Gửi nếu thuộc tính khác đúng | Gửi nếu thuộc tính khác đúng |
| `fetch()` tới cross-site API | XHR/fetch | Không gửi cross-site theo SameSite | Không gửi | Có thể gửi nếu fetch credentials/CORS/browser policy cho phép |
| IdP và Portal cùng schemeful site | Same-site callback | Thường gửi | Có thể gửi | Có thể gửi |

**Điểm quyết định:** kiểm tra **URL thực**, **HTTP method**, **top-level hay iframe**, **schemeful site** và **browser policy**.

### 11.1. “Lax+POST trong hai phút” có dùng để thiết kế không?

Một số browser từng/đang áp dụng ngoại lệ tương thích cho cookie **không khai báo SameSite** mới được tạo, cho phép một số cross-site POST trong thời gian ngắn. Hành vi này thường được gọi là **Lax-allowing-unsafe** hoặc “Lax+POST grace period”.

**Không dựa vào ngoại lệ đó để thiết kế OAuth form_post callback.** Nó có thể chỉ áp dụng cho cookie không khai báo SameSite, khác cookie được đặt rõ `SameSite=Lax`, và khác nhau giữa browser, phiên bản, thời điểm.

Nếu cần cross-site POST callback, phải thiết kế cookie/response mode hỗ trợ POST thực sự và kiểm thử trên browser mục tiêu.

## 12. OIDC response_mode=form_post: tình huống dễ gây mất session

Một số OP hỗ trợ:

~~~text
response_mode=form_post
~~~

Thay vì redirect GET chứa `code`/`state`, OP trả một trang HTML với form tự submit:

~~~html
<form method="post"
      action="https://portal.example.test/login/oauth2/code/company">
  <input type="hidden" name="code" value="EXAMPLE_CODE">
  <input type="hidden" name="state" value="EXAMPLE_STATE">
  <button type="submit">Continue</button>
</form>
~~~

Đây là **cross-site POST navigation** từ OP tới Portal. Browser có thể **không gửi** cookie `SameSite=Lax` của Portal:

~~~text
1. Portal lưu state trong HttpSession S1.
2. Portal đặt JSESSIONID=S1; SameSite=Lax.
3. Browser tới OP.
4. OP trả form_post POST callback.
5. Browser không gửi cookie S1 vì cross-site POST.
6. Spring Security callback không tìm được HttpSession S1.
7. authorization_request_not_found / state mismatch.
~~~

Với form_post, có thể cần cookie `SameSite=None; Secure` cho trạng thái correlation liên quan. Nhưng đó chỉ là **một phần**.

### 12.1. Còn có CSRF filter của Spring Security

Servlet Spring Security thường có **CSRF protection** cho HTTP methods thay đổi trạng thái, trong đó có POST. Callback OIDC `form_post` là POST do OP gửi, thường **không có CSRF token của ứng dụng trong form**.

Vì vậy cần kiểm tra **hai rào cản độc lập**:

1. Cookie session có được browser gửi trên cross-site POST không?
2. CSRF filter có cho callback POST đi tới `OAuth2LoginAuthenticationFilter` không?

Nếu CSRF filter chặn POST, đổi SameSite thành None **không đủ**. Ngược lại, bỏ CSRF check callback nhưng giữ cookie Lax cũng **không đủ**.

### 12.2. Miễn CSRF hẹp cho đúng callback POST

Trong một ứng dụng đã chủ đích chọn `response_mode=form_post`, ví dụ Servlet Spring Security 6:

~~~java
package com.example.portal.config;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.util.matcher.AntPathRequestMatcher;

@Configuration
public class OidcFormPostSecurityConfig {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {
        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/", "/error").permitAll()
                .anyRequest().authenticated())
            .csrf(csrf -> csrf
                .ignoringRequestMatchers(
                    new AntPathRequestMatcher(
                        "/login/oauth2/code/*",
                        "POST"
                    )
                ))
            .oauth2Login(Customizer.withDefaults())
            .oauth2Client(Customizer.withDefaults())
            .build();
    }
}
~~~

Đây là **mẫu có điều kiện cho form_post**, không phải cấu hình khuyến nghị nếu bạn chỉ dùng GET callback. Đường dẫn phải khớp callback thực tế và matcher phù hợp Spring Security version.

**Không tắt CSRF toàn ứng dụng** bằng `csrf.disable()` chỉ để một callback hoạt động. Việc miễn token CSRF cho callback chỉ hợp lý khi **state, nonce, authorization request correlation, PKCE và validation OIDC** vẫn được thực hiện đầy đủ theo flow.

### 12.3. Cấu hình response_mode cần đồng bộ với IdP

Một authorization request resolver có thể thêm tham số:

~~~java
import org.springframework.security.oauth2.client.registration
    .ClientRegistrationRepository;
import org.springframework.security.oauth2.client.web
    .DefaultOAuth2AuthorizationRequestResolver;

DefaultOAuth2AuthorizationRequestResolver resolver =
    new DefaultOAuth2AuthorizationRequestResolver(
        registrations,
        "/oauth2/authorization"
    );

resolver.setAuthorizationRequestCustomizer(builder ->
    builder.additionalParameters(params ->
        params.put("response_mode", "form_post")
    )
);
~~~

`registrations` là bean `ClientRegistrationRepository` đã có. Resolver này phải được gắn vào `oauth2Login().authorizationEndpoint()` đúng flow:

~~~java
http.oauth2Login(login -> login
    .authorizationEndpoint(endpoint -> endpoint
        .authorizationRequestResolver(resolver)
    )
);
~~~

Không chỉ thêm `response_mode=form_post` mà bỏ qua khả năng xử lý POST của callback, CSRF matcher, cookie None/Secure và hỗ trợ thực tế từ OP. Nếu không có yêu cầu form_post, **GET callback với Lax** thường đơn giản hơn cho ứng dụng Servlet/BFF.

## 13. Cookie Domain: host-only so với Domain cookie

Cookie đặt từ:

~~~text
https://portal.example.com
~~~

không có thuộc tính Domain:

~~~http
Set-Cookie: SESSION=abc; Path=/; Secure; HttpOnly; SameSite=Lax
~~~

là **host-only cookie**: browser giới hạn cookie cho `portal.example.com`. Đây thường là lựa chọn tốt cho session đăng nhập.

Nếu đặt:

~~~http
Set-Cookie: SESSION=abc; Domain=example.com; Path=/; Secure; HttpOnly; SameSite=Lax
~~~

cookie có thể được gửi tới nhiều subdomain thuộc `example.com` theo quy tắc domain matching.

### 13.1. Vì sao không mở Domain rộng để “chữa OAuth callback”?

Nếu Portal và IdP thuộc các registrable domains **khác nhau**, đặt `Domain=example.com` **không** làm cookie Portal được gửi đến IdP khác site và **không cần làm như vậy**. Callback vẫn về Portal; browser chỉ cần gửi cookie khi callback tới đúng Portal host.

Mở rộng Domain không cần thiết có thể tăng rủi ro từ các subdomain khác, bao gồm subdomain takeover hoặc ứng dụng kém tin cậy. Session cookie nên **host-only** trừ khi có nhu cầu chia sẻ session giữa subdomains đã được thiết kế và bảo vệ chặt chẽ.

### 13.2. Cookie của app.example.com không đi sang portal.example.com

Nếu lần đầu browser khởi tạo login ở:

~~~text
https://app.example.com/oauth2/authorization/company
~~~

nhưng IdP callback về:

~~~text
https://portal.example.com/login/oauth2/code/company
~~~

cookie host-only của `app.example.com` không được gửi tới `portal.example.com`, dù hai host có thể cùng site.

**Đây là lỗi hostname/redirect URI**, không phải lỗi SameSite đơn thuần. Nên giữ một canonical public host cho login start và callback, hoặc thiết kế session/correlation across hosts có chủ đích.

## 14. Cookie Path và callback endpoint

Cookie:

~~~http
Set-Cookie: SESSION=abc; Path=/portal; Secure; HttpOnly; SameSite=Lax
~~~

chỉ được gửi tới những request path tương thích với `/portal` theo quy tắc cookie Path.

Nếu callback thực sự ở:

~~~text
/login/oauth2/code/company
~~~

cookie Path `/portal` có thể **không được gửi**.

Tương tự, nếu ứng dụng deploy dưới context path:

~~~text
/employee
~~~

thì login initiation, callback và cookie path cần được cấu hình nhất quán.

### 14.1. Path không phải một cơ chế phân quyền

Cookie Path chỉ quyết định browser gửi cookie tới URL nào. Nó **không** ngăn ứng dụng cùng origin hay một XSS trong cùng website truy cập các endpoint khác thông qua browser.

Không dựa vào Path thay cho authentication/authorization server-side.

### 14.2. Cookie prefix __Host-__

Một cookie có tên bắt đầu bằng `__Host-` phải thỏa các điều kiện hiện đại như:

- Có `Secure`.
- `Path=/`.
- **Không có Domain**.
- Được đặt trong ngữ cảnh an toàn.

Ví dụ:

~~~http
Set-Cookie: __Host-SESSION=opaque; Path=/; Secure; HttpOnly; SameSite=Lax
~~~

Prefix này giúp browser thực thi một số ràng buộc về phạm vi cookie. Nếu ứng dụng muốn Path `/portal` hoặc cần Domain cookie, **không** thể dùng tên `__Host-SESSION` theo cùng cách mà vẫn hợp lệ.

Prefix `__Secure-` chỉ yêu cầu Secure và có phạm vi khác; không thay thế các quy tắc của `__Host-`.

## 15. Bảng các yếu tố khiến cookie không được gửi ở callback

| Hiện tượng | Vì sao browser không gửi? | Cách xác định |
|---|---|---|
| `SameSite=Strict` | Callback đến từ IdP cross-site | Xem Initiator/Site, Cookie blocked reason |
| `SameSite=Lax` + `form_post` | Cross-site POST không hưởng ngoại lệ Lax GET | Xem Request Method: POST và Set-Cookie |
| `SameSite=None` thiếu Secure | Browser có thể từ chối lưu cookie | Xem Set-Cookie issues/blocked reason |
| `Secure` + callback HTTP | Không gửi qua HTTP không an toàn | Xem Request URL scheme |
| Host khác | Host-only cookie không match callback host | So sánh host login start/callback |
| Path khác | Cookie Path không match callback path | So sánh Path với Request URL |
| Cookie hết hạn/bị xóa | Browser không còn session ID | Xem cookie storage/Expires/Max-Age |
| Domain rộng/sai | Cookie bị từ chối hoặc không match | Xem Domain và host response |
| Third-party/iframe restrictions | Browser privacy policy chặn | Xem iframe context và browser issues |
| Cookie quá lớn/quá nhiều | Browser/proxy/container có thể từ chối hoặc thay thế | Kiểm tra cookie size/count/header limits |
| Session ID khác | Server xoay session, app đổi host hoặc session không đồng bộ | So sánh session lifecycle phía server an toàn |

**Đừng đổi đồng thời mọi thuộc tính** khi debug. Tìm chính xác lý do cookie không được gửi/lưu trước.

## 16. Cấu hình Spring Boot Servlet session cookie

Trên Spring Boot 3 với embedded Servlet container, có thể cấu hình:

~~~yaml
# application-prod.yml
server:
  servlet:
    session:
      timeout: 30m
      cookie:
        name: __Host-SESSION
        path: /
        secure: true
        http-only: true
        same-site: lax
~~~

**Ý nghĩa:**

- `name`: tên cookie phiên; ở đây sử dụng `__Host-SESSION` theo prefix rules.
- `path: /`: callback và các endpoint cùng host nhận được cookie.
- `secure: true`: cookie chỉ qua kết nối an toàn.
- `http-only: true`: JS không đọc trực tiếp session ID.
- `same-site: lax`: tương thích top-level GET callback thông thường.
- `timeout: 30m`: thời hạn không hoạt động phía server; **không phải OAuth access token TTL**.

**Không khai báo `domain` nếu dùng `__Host-` prefix**. Hãy đảm bảo ứng dụng thực sự chạy ở HTTPS public URL.

### 16.1. Nếu không dùng prefix

Một cấu hình đơn giản:

~~~yaml
server:
  servlet:
    session:
      cookie:
        name: JSESSIONID
        secure: true
        http-only: true
        same-site: lax
        path: /
~~~

Lựa chọn giữa `JSESSIONID`, `SESSION` hoặc tên tùy chỉnh không tự thay đổi semantics của SameSite. Phần quan trọng là **cookie nào thực sự mang session mà Spring Security đang dùng**.

### 16.2. Trường hợp deployment dưới context path

Nếu app chạy dưới `/employee`, default session cookie Path có thể theo context path hoặc cấu hình container. Kiểm tra header `Set-Cookie` thật, không chỉ dựa vào YAML.

Nếu chọn tên `__Host-SESSION`, phải dùng `Path=/`. Nếu chính sách yêu cầu path hẹp hơn, cân nhắc **không dùng prefix __Host-** và đảm bảo cookie path khớp callback.

### 16.3. Không nhầm thuộc tính ứng dụng và cookie thực tế

Tùy Servlet container, Spring Session, reverse proxy hoặc gateway, cookie cuối cùng có thể được viết bởi **một lớp khác**.

Luôn kiểm tra:

~~~http
Set-Cookie: ...
~~~

trên HTTP response **đến browser**. Có YAML đúng nhưng một filter/proxy lại rewrite SameSite/Domain/Path thì browser vẫn áp dụng header thực nhận.

## 17. Spring Session Redis/JDBC có thể dùng cookie khác Servlet container

Nếu dự án sử dụng **Spring Session**, session ID thường được phát bằng Spring Session cookie serializer thay vì chỉ nhờ cấu hình cookie của embedded Tomcat.

Ví dụ `DefaultCookieSerializer`:

~~~java
package com.example.portal.config;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.session.web.http.CookieSerializer;
import org.springframework.session.web.http.DefaultCookieSerializer;

@Configuration
public class SpringSessionCookieConfig {

    @Bean
    CookieSerializer cookieSerializer() {
        DefaultCookieSerializer serializer =
            new DefaultCookieSerializer();

        serializer.setCookieName("__Host-SESSION");
        serializer.setCookiePath("/");
        serializer.setUseSecureCookie(true);
        serializer.setUseHttpOnlyCookie(true);
        serializer.setSameSite("Lax");

        // Không setDomainName(...) với prefix __Host-.
        return serializer;
    }
}
~~~

Ở đây Spring Session phải được thêm dependency và backend store cấu hình đúng; snippet chỉ tập trung vào **serialization của cookie**.

### 17.1. Tránh vô tình có hai session cookies

Một deployment có thể có:

~~~text
JSESSIONID=...  (Servlet container)
SESSION=...     (Spring Session)
~~~

Nếu login filter sử dụng Spring Session nhưng debug lại nhìn nhầm cookie của container, kết luận sẽ sai.

Xác định cookie nào thực sự mang ID của session đang lưu `SPRING_SECURITY_CONTEXT` và authorization request. Không cấu hình hai cookies khác nhau để cùng điều khiển một session mà không có lý do kiến trúc rõ ràng.

### 17.2. Redis còn dữ liệu không bảo đảm callback thành công

Session Redis có thể vẫn tồn tại, nhưng browser không gửi cookie để tra session → app **không thể biết phải lấy session nào**.

Ngược lại, browser gửi cookie đầy đủ nhưng Redis mất session/TTL hết hạn → app cũng không tìm được authorization request. Cần kiểm tra **cả browser cookie lẫn server-side store**.

## 18. HTTPS phía ngoài, HTTP phía trong: reverse proxy và load balancer

Một mô hình phổ biến:

~~~text
Browser
  |
  | HTTPS https://portal.example.test
  v
Load Balancer / Ingress
  |
  | HTTP http://portal-service:8080
  v
Spring Boot Servlet
~~~

Ứng dụng chỉ nhìn thấy kết nối nội bộ HTTP nếu không được cấu hình proxy headers. Điều này có thể gây:

- Redirect URI được tạo thành `http://...` dù public URL dùng HTTPS.
- Hostname/port nội bộ xuất hiện trong callback.
- `request.isSecure()` cho kết quả khác điều browser nhìn thấy.
- Cookie Secure bị đặt thiếu nếu hệ thống dựa vào scheme nội bộ để suy ra security.

### 18.1. Cấu hình forwarded headers có kiểm soát

Ví dụ Spring Boot:

~~~yaml
server:
  forward-headers-strategy: framework
  servlet:
    session:
      cookie:
        secure: true
        http-only: true
        same-site: lax
~~~

Khi chọn `framework`, Spring xử lý `Forwarded` hoặc `X-Forwarded-*` theo cơ chế tương ứng để ứng dụng nhận biết external scheme/host. Một số hạ tầng dùng `native` với cơ chế container/ingress riêng.

**Ràng buộc bảo mật bắt buộc:** chỉ tin forwarded headers từ **reverse proxy đáng tin**, và proxy phải **loại bỏ/ghi đè giá trị do client từ Internet tự cung cấp**. Nếu tin header spoofed, kẻ tấn công có thể ảnh hưởng redirect URL, host validation hoặc chính sách URL.

### 18.2. Redirect URI do Spring Security dựng

Ví dụ:

~~~yaml
spring:
  security:
    oauth2:
      client:
        registration:
          company:
            provider: company
            client-id: ${OIDC_CLIENT_ID}
            client-secret: ${OIDC_CLIENT_SECRET}
            authorization-grant-type: authorization_code
            redirect-uri: "{baseUrl}/login/oauth2/code/{registrationId}"
            scope:
              - openid
              - profile
        provider:
          company:
            issuer-uri: ${OIDC_ISSUER_URI}
~~~

`{baseUrl}` phụ thuộc thông tin request/proxy được nhận diện. Nếu baseUrl là `http://portal-service:8080` nhưng OP chỉ đăng ký:

~~~text
https://portal.example.test/login/oauth2/code/company
~~~

thì có thể bị `redirect_uri_mismatch` hoặc browser callback vào host không có cookie session.

**Chú ý:** lỗi redirect URI không nhất thiết là cookie SameSite; chúng có thể xuất hiện cùng nhau vì proxy config sai.

### 18.3. Không chỉ sửa bằng cách hard-code redirect URI

Hard-code public redirect URI có thể giúp nhanh một môi trường, nhưng không chữa:

- Cookie Secure không được đặt đúng.
- Cookie Path/Domain không match.
- Server tin X-Forwarded-Host từ nguồn không tin cậy.
- Load balancer chuyển callback sang node không tìm được session.

Sửa nguyên nhân ở proxy/public URL/session architecture. Hard-code có thể vẫn hữu ích khi deployment có canonical URI rõ ràng, nhưng phải đồng bộ IdP registration và environment.

## 19. HttpSessionOAuth2AuthorizationRequestRepository và state correlation

Trong Servlet stack, Spring Security có repository:

~~~java
HttpSessionOAuth2AuthorizationRequestRepository
~~~

Về mặt khái niệm:

~~~text
Browser bắt đầu authorization:
  GET /oauth2/authorization/company

Server:
  generate OAuth2AuthorizationRequest:
    authorizationUri, clientId, redirectUri, scopes
    state = RANDOM_STATE
    nonce/PKCE attributes khi có
  store request in HttpSession

Browser callback:
  GET /login/oauth2/code/company?code=...&state=RANDOM_STATE

Server:
  find HttpSession by session cookie
  load matching request
  compare state
  continue code exchange
~~~

Mất session có thể khiến repository không tìm thấy authorization request.

### 19.1. state không phải session ID

`state` là giá trị correlation/CSRF cho OAuth authorization response. `JSESSIONID` là giá trị giúp tìm session tại Portal.

~~~text
state     = random-OAuth-correlation-value
JSESSIONID = random-web-session-identifier
~~~

Chúng có thể cùng xuất hiện trong một flow nhưng có mục đích riêng. Không đặt `state = JSESSIONID`, không đưa session ID vào query parameter để “chữa cookie bị chặn”.

### 19.2. state có xuất hiện ở URL nghĩa là callback chắc chắn hợp lệ?

Không. Attacker cũng có thể gửi request chứa `state` tùy ý. Spring Security cần biết state **đã được phát trong authorization request gốc thuộc session/flow nào**.

Nếu missing authorization request, không được tự tạo một request giả rồi chấp nhận `code` từ URL.

### 19.3. OIDC nonce và PKCE vẫn cần được bảo vệ

Khi login hoàn tất:

- PKCE `code_verifier` cần đúng với `code_challenge` của yêu cầu ban đầu.
- OIDC nonce trong ID Token cần đối chiếu với nonce đã phát theo flow.
- ID Token cần được xác minh issuer/audience/signature/expiry và các điều kiện OIDC liên quan.

Cookie policy đảm bảo **tìm lại context**, nhưng không thay thế những validation này.

## 20. Session fixation protection và đổi session ID sau login

Một hiện tượng dễ bị hiểu nhầm:

~~~text
Trước login:
  JSESSIONID = S1

Callback thành công:
  Session fixation protection có thể đổi session ID.

Sau login:
  JSESSIONID = S2
~~~

Spring Security thường có cơ chế **session fixation protection**, giúp giảm nguy cơ attacker cố định trước session ID của user rồi lợi dụng sau đăng nhập.

**Việc session ID đổi sau authentication không tự là lỗi.** Quan trọng là:

1. Trước callback, browser phải gửi **S1** để tìm authorization request.
2. Sau login thành công, ứng dụng có thể phát **S2**.
3. Browser phải lưu cookie mới và dùng S2 cho các request sau.

### 20.1. Không cố giữ nguyên session ID để sửa callback

Nếu callback thiếu S1 do SameSite=Strict hoặc POST với Lax, tắt session fixation protection **không giải quyết** vấn đề. Nó chỉ làm yếu bảo vệ ở một lớp khác.

### 20.2. Multiple tabs và nhiều authorization requests

Nếu user mở hai login flows gần như đồng thời:

~~~text
Tab A -> authorization request state=A
Tab B -> authorization request state=B
Tab A -> callback state=A
~~~

tùy repository/session implementation, request sau có thể thay thế hoặc xung đột request trước. Khi gặp state mismatch:

- Kiểm tra cookie có được gửi hay không.
- Kiểm tra có nhiều tabs/popups/login attempts hay không.
- Kiểm tra session persistence giữa các nodes.
- Kiểm tra custom authorization request repository có hỗ trợ nhiều flows hay không.

**Không mặc định mọi state mismatch đều do SameSite.**

## 21. SessionCreationPolicy.STATELESS và OAuth2 login

Một lỗi cấu hình phổ biến:

~~~java
http.sessionManagement(session ->
    session.sessionCreationPolicy(SessionCreationPolicy.STATELESS));
~~~

rồi cũng dùng default `oauth2Login()` với `HttpSessionOAuth2AuthorizationRequestRepository`.

`STATELESS` thường không phù hợp với một login flow vẫn dựa vào HttpSession để lưu authorization request/SecurityContext. Nếu không thiết kế một repository stateless/correlation mechanism thay thế, callback có thể thiếu trạng thái.

### 21.1. Tách security chains khi ứng dụng vừa là BFF vừa là API

Một ứng dụng có thể có:

- **Browser/login endpoints**: session-based, OAuth2/OIDC login.
- **Machine API endpoints**: stateless bearer token/resource server.

Không áp dụng một chính sách `STATELESS` cho mọi endpoint nếu browser login vẫn cần session. Có thể tách `SecurityFilterChain` theo request matchers và điều chỉnh policies.

Điều này liên quan đến session storage, **không thể sửa chỉ bằng đổi SameSite**.

## 22. Cookie-based AuthorizationRequestRepository: có nên thay HttpSession?

Spring Security cho phép thay:

~~~java
org.springframework.security.oauth2.client.web
    .AuthorizationRequestRepository<OAuth2AuthorizationRequest>
~~~

Ví dụ bạn muốn lưu authorization request correlation trong một cookie riêng thay vì HttpSession. Thiết kế này cần nhiều cân nhắc:

- Cookie thường có giới hạn kích thước (thường vài KiB), không phù hợp lưu tùy ý toàn bộ serialized request.
- Dữ liệu từ browser có thể bị sửa; phải chống tampering, binding và replay.
- Không đưa code verifier, nonce, credential hoặc chi tiết nhạy cảm vào cookie có thể bị JavaScript đọc.
- Nếu cookie chứa state, cần ký/mã hóa phù hợp và kiểm tra TTL, audience, client registration, redirect URI.
- Cần xử lý nhiều concurrent login flows mà không overwrite lẫn nhau.
- Callback cookie vẫn chịu chính sách **Secure/HttpOnly/SameSite/Domain/Path**.
- Có thể cần rotation key và cleanup cookie sau login/failure.

### 22.1. Đổi repository không tự giải quyết SameSite

Nếu bạn chuyển từ HttpSession sang cookie-based repository nhưng vẫn đặt:

~~~http
Set-Cookie: OAUTH2_REQUEST=...; Secure; HttpOnly; SameSite=Strict
~~~

và callback từ IdP cross-site, cookie custom **vẫn có thể không được gửi**.

Thay repository chỉ đổi nơi lưu correlation; **browser cookie policy vẫn tác động như cũ**.

### 22.2. Không coi client-side cookie là một cơ chế trust mới

Nếu browser gửi một cookie tự nhận “tôi đã đăng nhập với sub=admin”, server không được tin giá trị đó để bỏ qua ID Token validation hoặc phân quyền.

OAuth2/OIDC callback phải giữ kiểm tra state, nonce/PKCE và token validation; cookie chỉ là một cách vận chuyển state/correlation được bảo vệ.

## 23. Lax callback GET khác logout và front-channel iframe

Không phải mọi luồng OIDC đều dùng một kiểu request:

| Luồng | Hình thức thường gặp | Hệ quả cookie |
|---|---|---|
| OIDC authorization-code callback | Top-level GET | Lax thường phù hợp |
| OIDC form_post callback | Top-level POST | Lax thường không gửi cookie |
| RP-Initiated Logout | Top-level browser redirect | Cookie có thể được dùng ở RP tùy endpoint và flow |
| Front-channel logout qua iframe | Cross-site iframe | Lax/Strict có thể chặn cookie; None có thể vẫn bị third-party restrictions |
| Back-channel logout | Server-to-server HTTP | Không phụ thuộc browser cookie giống callback |
| Silent login/refresh trong iframe | Embedded cross-site context | Browser third-party cookie restrictions có thể khiến flow thất bại |

**Một cấu hình cookie tối ưu cho top-level GET callback không tự đảm bảo front-channel logout qua iframe hoạt động.**

### 23.1. Không đánh đồng SameSite=None với việc “cho phép silent login”

Browser có thể hạn chế third-party cookies và tracking, khiến iframe login/cookie không có dù Set-Cookie đúng. Cần xem hướng dẫn OP và browser policy cho luồng embedded authentication. Thường nên ưu tiên top-level redirect/authorization code + PKCE thay vì phụ thuộc silent iframe trong môi trường modern privacy restrictions.

### 23.2. Logout ở Portal khác token revocation tại OP

Xóa cookie/session local:

~~~text
Browser không còn phiên Portal.
~~~

không có nghĩa:

~~~text
Access token, refresh token và SSO session ở OP đều đã bị revoke.
~~~

Cần thiết kế local logout, OIDC OP logout, authorized-client cleanup và token revocation theo yêu cầu hệ thống; **cookie SameSite không thay thế những hành động này**.

## 24. CSRF: SameSite hỗ trợ nhưng không thay thế CSRF defense

CSRF xảy ra khi attacker khiến browser của user gửi request có cookie tới ứng dụng tin cậy. `SameSite=Lax` làm giảm một số cross-site cookie requests, đặc biệt những requests không phải top-level safe navigation.

Tuy nhiên, nó **không phải bảo vệ toàn diện** vì:

- Browser khác nhau có chính sách/tương thích khác nhau.
- Same-site subdomain attacker có thể tạo request vẫn được xem là same-site.
- Có thể tồn tại **GET endpoints gây side effect trái chuẩn**.
- Cookie `SameSite=None` cho phép cross-site context rộng hơn.
- Login callback cần một cơ chế correlation chuyên dụng là `state`.

Vì vậy:

1. Giữ CSRF protection cho form/action dựa trên session.
2. Dùng `state` cho OAuth2 authorization response.
3. Dùng `nonce` cho OIDC correlation và PKCE khi áp dụng.
4. Miễn CSRF token chỉ ở **endpoint POST callback cụ thể** nếu `form_post` thực sự cần.
5. Không tắt CSRF toàn app chỉ để callback hoạt động.

### 24.1. HttpOnly không phải CSRF defense

Ngay cả khi attacker không đọc được `JSESSIONID` qua JavaScript, browser vẫn tự đính cookie vào requests đủ điều kiện. Vì vậy `HttpOnly` bảo vệ khỏi một loại token exfiltration, không ngăn mọi CSRF request.

### 24.2. SameSite cũng không thay authentication

Một endpoint nội bộ vẫn phải kiểm tra Authentication/Authorization. Cookie được gửi không chứng minh user có quyền thay đổi mọi resource. Với multi-tenant apps, cần kiểm tra tenant/resource ownership phía server.

## 25. Callback bằng fetch/AJAX: vì sao thường không đúng mô hình?

OAuth2 Authorization Code Flow trong Spring Security Servlet thường được thiết kế theo **browser navigation**:

~~~text
Browser -> Portal start authorization
Browser -> IdP login
Browser -> Portal callback
~~~

Nếu frontend cố:

~~~javascript
fetch("https://portal.example.test/login/oauth2/code/company?code=...")
~~~

thì request có thể gặp CORS/cookie credentials constraints, không có context navigation cần thiết, và có thể không thuộc flow gốc đã lưu state.

**Callback URL không phải API tùy ý để frontend tự gửi code.** Nên để browser theo authorization redirect đã được phát bởi Spring Security/IdP.

### 25.1. Cross-origin fetch và credentials

Nếu frontend ở:

~~~text
https://frontend.example.com
~~~

và BFF ở:

~~~text
https://portal.example.com
~~~

thì đây có thể là **cross-origin nhưng same-site**.

Muốn gửi cookie khi dùng fetch, frontend có thể cần:

~~~javascript
fetch("https://portal.example.com/api/me", {
  credentials: "include"
});
~~~

và server cần chính sách CORS phù hợp, ví dụ origin cụ thể và credentials được phép. Nhưng **credentials: include không vượt qua SameSite, Secure hoặc third-party cookie blocking**.

**CORS là cơ chế của JavaScript cross-origin fetch**, không áp dụng cùng cách cho top-level OAuth browser redirect. Không thêm wildcard CORS để “chữa” callback GET.

## 26. SameSite và các subdomain: phân tích ba ví dụ thực tế

### 26.1. IdP ở domain ngoài, callback GET

~~~text
Portal: https://portal.example.com
IdP:    https://login.company-idp.net
Method callback: GET
Cookie: Secure; HttpOnly; SameSite=Lax; Path=/
~~~

Thường hoạt động với top-level redirect. Không cần `Domain=example.com` hay `SameSite=None` chỉ vì IdP ở site khác.

### 26.2. IdP ngoài, callback POST

~~~text
Portal: https://portal.example.com
IdP:    https://login.company-idp.net
Method callback: POST (form_post)
Cookie: Secure; HttpOnly; SameSite=Lax
~~~

Cross-site POST thường làm cookie Lax **không được gửi**. Cần đánh giá `SameSite=None; Secure`, CSRF callback matcher và việc OP/RP hỗ trợ response_mode=form_post.

### 26.3. IdP cùng registrable domain, host khác

~~~text
Portal: https://portal.example.com
IdP:    https://login.example.com
Method callback: GET hoặc POST
~~~

Đây thường là **same-site** vì scheme và registrable domain giống nhau. Cookie SameSite=Strict có thể được gửi trong context same-site, nhưng cookie **host-only của Portal vẫn không được gửi sang login.example.com** — và cũng không cần gửi sang IdP.

Đừng “chia sẻ cookie giữa Portal và OP” chỉ vì cùng site; mỗi bên nên quản lý session riêng theo security boundary.

## 27. Bảo mật cookie khi có reverse proxy/CDN

Ngoài cấu hình tại ứng dụng, kiểm tra lớp proxy:

- Có terminate TLS đúng certificate không?
- Có HSTS trên public HTTPS host theo policy không?
- Có rewrite `Set-Cookie` không?
- Có strip/normalize `X-Forwarded-Proto`, `Host` và `X-Forwarded-Host` không?
- Có thay Location redirect từ HTTPS sang HTTP không?
- Có cache nhầm login response chứa `Set-Cookie` không?
- Có log session cookie hoặc query `code/state` không?
- Có gửi cookie đến hostname của CDN/static domain ngoài phạm vi không?

**Không cache các response cá nhân có Set-Cookie/authorization artifacts một cách công khai.** Nếu proxy log đầy đủ callback URL, authorization code có thể xuất hiện trong access logs; cần masking và retention phù hợp.

### 27.1. Set-Cookie đến browser mới là nguồn sự thật

Trong application logs bạn có thể thấy:

~~~text
session created successfully
~~~

nhưng nếu proxy loại `SameSite=None`, xóa `Secure` hoặc thay `Path`, browser sẽ xử lý khác.

Hãy kiểm tra HTTP response **thực** tại Network tab trên browser và những intermediate proxy có quyền truy cập an toàn.

## 28. Multi-instance: cookie đúng nhưng session store không đúng

Giả sử Portal chạy hai replicas:

~~~mermaid
flowchart TD
    B["Browser giữ SESSION=S1"] --> LB["Load Balancer"]
    LB --> A["Portal Node A: tạo authorization request trong S1"]
    LB --> C["Portal Node B: xử lý OAuth callback"]
    A --> LocalA["Local HttpSession Store A"]
    C --> LocalB["Local HttpSession Store B"]
~~~

Nếu cookie được gửi đúng nhưng Node B không tìm thấy S1 trong local store, callback vẫn lỗi `authorization_request_not_found`.

Các phương án:

- **Shared session storage**, ví dụ Spring Session với Redis/JDBC theo kiến trúc.
- Sticky sessions nếu có chủ đích, nhưng phải hiểu failover/scale limitations.
- Kiểm tra thời hạn session và mapping cookie-to-session.

**SameSite=Lax không thể khắc phục session không được chia sẻ giữa nodes.**

### 28.1. Session stickiness không phải authorization security

Ngay cả khi sticky routing hoạt động, server vẫn phải kiểm tra state, nonce, PKCE, client registration và ID Token. Sticky session chỉ giúp callback đến đúng state store.

### 28.2. Race với session fixation và parallel callback

Khi một request login thành công và đổi session ID, request khác đang giữ cookie cũ có thể gặp trạng thái khác. Cần test multi-tab/concurrent flows và storage consistency, không chỉ nhìn lỗi cookie blocked.

## 29. Điều tra bằng Browser DevTools

Một quy trình khoanh vùng thực tế:

**Bước 1 — Mở tab ẩn danh/test profile phù hợp.** Tránh session cookie cũ, extension và nhiều tabs che kết quả.

**Bước 2 — Truy cập Portal bằng HTTPS public URL.** Không bắt đầu login ở host nội bộ hoặc HTTP rồi callback ở host khác.

**Bước 3 — Mở DevTools Network, bật Preserve log.** Theo dõi request:

~~~text
GET /oauth2/authorization/company
302 Location: https://login.identity.example/authorize...
GET /login/oauth2/code/company?code=...&state=...
~~~

**Bước 4 — Kiểm tra response đầu của Portal:**

~~~http
Set-Cookie: JSESSIONID=...; Secure; HttpOnly; SameSite=Lax; Path=/
~~~

Xác minh cookie có thực sự được lưu không; xem `Application/Storage → Cookies` và browser **Issues/blocked reasons**.

**Bước 5 — Kiểm tra callback request tới Portal:** ở Network → Request Headers → `Cookie`. Browser có gửi cùng session cookie (trước khi Spring Security rotate session ID) không?

**Bước 6 — Kiểm tra method:** callback là **GET** hay **POST**? Nếu POST, có phải form_post và đã cấu hình SameSite/CSRF hợp lý?

**Bước 7 — Kiểm tra scheme/host/path:** `https://portal.example.test` có đúng từ lúc bắt đầu đến callback không?

**Bước 8 — Nếu cookie được gửi:** kiểm tra server session store, state correlation, nhiều login attempts và filter chain matching.

### 29.1. Không copy cookie hoặc code thật vào tickets/logs

Khi chia sẻ HAR, Network trace hoặc screenshot, phải **redact**:

- `Cookie: JSESSIONID=...` hoặc `SESSION=...`.
- Authorization code trong query/body.
- OAuth2 `state` và OIDC `nonce` nếu không cần.
- `Authorization: Basic/Bearer`.
- ID Token, access token, refresh token.
- Client secret và PII.

Các giá trị đó có thể còn hiệu lực hoặc giúp người khác liên kết phiên. Ghi nhận **cookie có/không, thuộc tính, timestamp và status** thường đã đủ để khoanh vùng.

## 30. Phân biệt lỗi cookie bị chặn và cookie không tồn tại

Hai trường hợp:

~~~text
A. Cookie không được lưu:
   Response Set-Cookie có nhưng browser từ chối.

B. Cookie đã được lưu nhưng không được gửi:
   Browser có cookie, callback request không kèm Cookie.
~~~

Nguyên nhân khác nhau:

| Trường hợp | Ví dụ nguyên nhân |
|---|---|
| Không lưu | SameSite=None thiếu Secure, Domain không hợp lệ, browser policy, giới hạn cookie |
| Không gửi | SameSite=Strict, Lax + POST, Secure + HTTP, Path/Domain mismatch, hết hạn, iframe restrictions |
| Gửi đúng nhưng server không có session | Session timeout, Redis outage, node khác với local store |
| Gửi cookie nhưng callback vẫn lỗi | State mismatch, parallel login, request repository sai, client registration/callback filter không match |

**Đừng chỉ nhìn cookie có xuất hiện trong Storage tab rồi kết luận browser đã gửi nó tới callback.** Phải kiểm tra request headers của chính callback.

## 31. Dùng curl để kiểm tra HTTP headers — nhưng không thay thế browser

Có thể xem server có trả Set-Cookie và Location đúng không:

~~~bash
curl --silent --show-error --include \
  https://portal.example.test/oauth2/authorization/company
~~~

Phản hồi minh họa:

~~~http
HTTP/1.1 302 Found
Set-Cookie: JSESSIONID=...; Path=/; Secure; HttpOnly; SameSite=Lax
Location: https://login.identity.example/authorize?client_id=...&...
~~~

**Không dùng `curl -k` để bỏ xác minh TLS trong phép kiểm tra production**. Không công bố raw response có authorization code/cookie/session ID.

### 31.1. curl không thực thi chính sách SameSite như browser

Cookie jar của curl và HTTP client libraries không mô phỏng đầy đủ các quy tắc:

- Site/top-level navigation.
- Strict/Lax cross-site restrictions.
- iframe third-party blocking.
- Browser privacy policies.

Vì vậy “curl gửi cookie được” **không chứng minh browser callback gửi được**. Muốn kiểm chứng SameSite, dùng browser thật hoặc browser automation điều hướng qua các sites.

## 32. Test bằng MockMvc: điều gì có thể và không thể chứng minh?

Với Spring Security Test, có thể kiểm tra authorization/login endpoint và policy của server. Nhưng **MockMvc không phải browser** nên không tự áp dụng SameSite như Chrome, Firefox hoặc Safari.

Ví dụ ý tưởng:

~~~java
@Test
void authorizationEndpointRedirectsToProvider() throws Exception {
    mvc.perform(get("/oauth2/authorization/company"))
        .andExpect(status().is3xxRedirection())
        .andExpect(header().string(
            "Location",
            org.hamcrest.Matchers.containsString("state=")
        ));
}
~~~

Ở đây `mvc` là `MockMvc` đã cấu hình với Spring Security và registration giả phù hợp.

### 32.1. MockMvc không phải phép test Set-Cookie đầy đủ

Việc Servlet container tạo cookie phiên, hoặc reverse proxy thay header, có thể không được MockMvc mô phỏng giống production. Khi cần kiểm tra `Secure/HttpOnly/SameSite` trên cookie **thực sự xuất ra**, dùng embedded-container integration test hoặc môi trường staging qua HTTP client.

### 32.2. Test state mismatch

Test callback không có đúng authorization request/session để bảo đảm Spring Security **từ chối**:

~~~text
Given:
  Callback có code và state.
  Không có session đã lưu OAuth2AuthorizationRequest.

Then:
  Login không thành công.
  Không tạo authenticated principal chỉ vì code có mặt.
~~~

Không cần bypass state để test happy path. Với integration test hoàn chỉnh, cần browser/session repository và fake Authorization Server đúng contract.

## 33. Browser end-to-end tests: bộ trường hợp tối thiểu

| Test case | Cookie | Callback | Kết quả cần quan sát |
|---|---|---|---|
| Happy path phổ biến | Secure; HttpOnly; Lax | Top-level GET | Browser gửi cookie, state được tìm thấy |
| Strict + IdP cross-site | Secure; HttpOnly; Strict | Top-level GET | Cookie có thể bị chặn, login thất bại đúng lý do |
| Lax + form_post | Secure; HttpOnly; Lax | Top-level POST | Cookie thường không được gửi |
| None + form_post | Secure; HttpOnly; None | Top-level POST | Browser có thể gửi cookie; vẫn cần CSRF callback config |
| None thiếu Secure | HttpOnly; None | GET hoặc POST | Browser có thể từ chối Set-Cookie |
| Secure + callback HTTP | Secure | GET | Cookie không được gửi theo HTTPS policy |
| Khác hostname | Host-only cookie cho host A | Callback host B | Không gửi host-only cookie |
| Path mismatch | Path=/portal | Callback /login/oauth2/code | Cookie không match path |
| Shared session store lỗi | Cookie hợp lệ | GET | Server không tìm thấy session |
| Nhiều tabs login | Cookie đúng | GET | Có thể có state collision tùy repository |
| Callback POST CSRF blocked | None; Secure | POST | HTTP 403 nếu CSRF matcher chưa cho phép |
| Iframe third-party | None; Secure | Embedded | Có thể bị browser privacy blocking |

**Không coi những expected failures này là test production phải giữ nguyên lỗi.** Chúng là kiểm chứng cơ chế để quyết định cấu hình đúng.

### 33.1. Test qua staging public host, không chỉ localhost

Cookie matching phụ thuộc scheme, hostname, top-level navigation và browser privacy mode. Chạy ít nhất một bài test:

~~~text
https://staging-portal.example.test
    -> IdP staging
    -> https://staging-portal.example.test/login/oauth2/code/company
~~~

Qua đúng reverse proxy/load balancer như production. Test chỉ với `localhost:8080` có thể bỏ sót Secure, public host, forwarded header và third-party policy.

## 34. Các cấu hình sai thường thấy

### 34.1. Đặt SameSite=Strict cho mọi session cookie

~~~http
Set-Cookie: SESSION=...; Secure; HttpOnly; SameSite=Strict
~~~

Nếu IdP là cross-site, callback GET có thể mất cookie. Chọn Lax cho standard top-level GET flow hoặc thiết kế phù hợp callback mode; **không bỏ state check**.

### 34.2. Đặt SameSite=None mà quên Secure

~~~http
Set-Cookie: SESSION=...; HttpOnly; SameSite=None
~~~

Browser có thể từ chối cookie. Cần:

~~~http
Set-Cookie: SESSION=...; Secure; HttpOnly; SameSite=None
~~~

và HTTPS/third-party policy phù hợp.

### 34.3. Dùng form_post nhưng quên cấu hình POST callback CSRF

Ngay cả khi cookie được gửi, Spring Security CSRF filter có thể chặn POST. Chỉ miễn endpoint callback cụ thể nếu form_post được dùng, còn state/nonce/PKCE validation vẫn phải hoạt động.

### 34.4. OAuth login start và callback khác host

~~~text
Start:    https://app.example.com/oauth2/authorization/company
Callback: https://portal.example.com/login/oauth2/code/company
~~~

Host-only cookie không follow sang host B. Sửa canonical host/redirect URL hoặc thiết kế cross-host state storage; không mở Domain rộng vô điều kiện.

### 34.5. Thay HttpOnly=false để JavaScript đọc session

Việc JS không thấy cookie HttpOnly là đúng. **Không tắt HttpOnly** để debug OAuth callback.

### 34.6. Disable CSRF toàn app

~~~java
http.csrf(csrf -> csrf.disable());
~~~

Không nên dùng như biện pháp mặc định. Session-based browser app vẫn cần CSRF protection cho các tác vụ thay đổi trạng thái.

### 34.7. SessionCreationPolicy.STATELESS trên login chain

Nếu Spring Security vẫn dùng HttpSession để lưu authorization request, callback có thể không có context. Cần phù hợp session strategy hoặc custom authorization request repository đúng cách.

### 34.8. Tin X-Forwarded-Proto từ Internet

Attacker có thể giả header nếu proxy không strip/normalize. Cần thiết lập trust boundary ở ingress, không chỉ bật forwarded headers trong Boot.

### 34.9. Cho rằng token hết hạn vì callback mất cookie

Callback có thể lỗi **trước khi** token exchange diễn ra. Phân biệt lỗi state/session với access token expiry, refresh token invalid và Resource Server 401.

### 34.10. Lưu access token trong cookie phiên

Việc cookie dễ gửi lại không có nghĩa nên chứa access/refresh token. Trong server-side BFF, giữ token ở backend, dùng cookie chứa opaque session ID được bảo vệ.

## 35. Troubleshooting theo triệu chứng

| Triệu chứng | Giả thuyết đáng kiểm tra | Dấu hiệu xác nhận |
|---|---|---|
| Login tới IdP được nhưng callback `authorization_request_not_found` | Browser không gửi session cookie | Callback Request Headers thiếu Cookie |
| Chỉ lỗi khi dùng form_post | Lax không cho cross-site POST hoặc CSRF filter chặn POST | Request Method POST, SameSite/callback 403 |
| Chỉ lỗi với Chrome/Safari một số profile | Cookie privacy policy hoặc default SameSite | DevTools blocked reason, browser settings |
| Lỗi khi HTTPS qua ingress | X-Forwarded-Proto/Host sai | Redirect URI hoặc Secure attributes không đúng |
| IdP báo redirect_uri_mismatch | Callback đăng ký khác generated URI | So sánh URI tuyệt đối, không phải cookie |
| Cookie có trong Storage nhưng callback không gửi | Secure/Domain/Path/SameSite restriction | Network request Cookie header thiếu |
| Cookie được gửi nhưng Spring báo thiếu authorization request | Redis/session node mismatch, session timeout, multi-tab overwrite | Session store không có request tương ứng |
| Chỉ lỗi ở second tab | State collision/parallel logins | Hai authorization requests cùng session |
| Callback login thành công rồi cookie đổi | Session fixation ID rotation | Set-Cookie mới sau login, flow vẫn thành công |
| Backend API gọi được nhưng browser bị logout | Session cookie mất/hết hạn dù access token còn | SecurityContext/session khác OAuth token |
| Đổi SameSite=None vẫn lỗi | Cookie third-party blocked, Secure thiếu, CSRF, proxy | Kiểm tra từng tầng |
| JS không đọc được JSESSIONID | HttpOnly đúng cấu hình | Browser vẫn gửi cookie ở requests phù hợp |
| Cookie không tới subdomain khác | Host-only scope | Host callback khác host đặt cookie |
| Callback trả 404 | Security matcher/path/context mismatch | Request tới URL đúng nhưng filter không nhận |
| Lỗi chỉ khi scale nhiều pods | Local sessions không chia sẻ | Cookie đúng, node khác không có state |
| Sau logout login lại lập tức lỗi | Cookie stale/session store/cache mismatch | Old vs new session ID và cookie serialization |

### 35.1. Đường điều tra nhanh

~~~text
OAuth2 callback failure
    |
    v
Callback URL/scheme/host/path đúng?
    |-- Không -> sửa redirect URI/proxy/routing.
    |
    v
Callback method GET hay POST?
    |-- POST -> xem SameSite=None;Secure và CSRF callback exception hẹp.
    |
    v
Browser có cookie của Portal?
    |-- Không -> xem Set-Cookie response và browser blocked reason.
    |
    v
Cookie có được gửi trong callback request?
    |-- Không -> xem SameSite, Secure, Domain, Path, expiry, iframe policy.
    |
    v
Server có session tương ứng?
    |-- Không -> xem TTL, Redis, sticky/shared session và session ID.
    |
    v
OAuth2AuthorizationRequest có state phù hợp?
    |-- Không -> xem repository, multi-tab, state/nonce/PKCE.
    |
    v
Token exchange và OIDC validation có thành công?
    |-- Không -> kiểm tra token endpoint, client auth, issuer/audience.
    |
    v
Login thành công; kiểm tra session ID sau login.
~~~

## 36. Bài tập thực hành

### Bài tập 1 — Lax và GET callback

~~~text
Portal = https://portal.example.com
IdP    = https://login.idp.net
Cookie = Secure; HttpOnly; SameSite=Lax; Path=/
Callback = top-level GET
~~~

**Câu hỏi:** Browser có thể gửi session cookie ở callback không?

**Hướng giải:** Có, Lax thường cho phép cookie trong top-level cross-site navigation bằng safe method như GET, nếu Domain/Path/Secure/expiry và policy khác phù hợp.

### Bài tập 2 — Strict và state bị mất

Same scenario nhưng cookie `SameSite=Strict`.

**Câu hỏi:** Có nên bỏ kiểm tra OAuth state để callback thành công?

**Hướng giải:** Không. Cookie Strict có thể không được gửi trong cross-site callback. Chọn cookie policy phù hợp hoặc thiết kế lại flow, giữ state/nonce/PKCE validation.

### Bài tập 3 — form_post và CSRF

IdP gửi POST tới `/login/oauth2/code/company`. Browser lưu session cookie `SameSite=Lax` và Spring Security có CSRF filter.

**Câu hỏi:** Có hai lý do nào khiến flow thất bại?

**Hướng giải:** Lax thường chặn cookie trên cross-site POST; CSRF filter có thể chặn POST callback vì không có CSRF token của ứng dụng. Cần config form_post có chủ đích: cookie phù hợp, callback matcher và state/nonce/PKCE vẫn đầy đủ.

### Bài tập 4 — Secure và reverse proxy

Browser truy cập HTTPS nhưng Spring Boot phía sau load balancer thấy HTTP và tạo:

~~~text
redirect_uri=http://portal-service:8080/login/oauth2/code/company
~~~

**Câu hỏi:** Nên kiểm tra gì?

**Hướng giải:** Trusted proxy/forwarded headers, public baseUrl, redirect URI registration và cookie Secure. Không chỉ bỏ Secure.

### Bài tập 5 — HttpOnly

Frontend chạy `document.cookie` không thấy `JSESSIONID`. Nhưng browser tự gửi Cookie đến `/api/me`.

**Câu hỏi:** Có bất thường không?

**Hướng giải:** Không. HttpOnly ngăn JS đọc giá trị cookie, nhưng browser vẫn gửi cookie trong request hợp lệ.

### Bài tập 6 — Domain và Path

Session cookie được đặt:

~~~http
Set-Cookie: SESSION=abc; Path=/employee; Secure; HttpOnly; SameSite=Lax
~~~

Callback thực tế:

~~~text
https://portal.example.com/login/oauth2/code/company
~~~

**Câu hỏi:** Vì sao cookie có thể không được gửi?

**Hướng giải:** Cookie Path `/employee` không match callback `/login/...`. Cần đồng bộ context path/callback hoặc chọn cookie path hợp lệ.

### Bài tập 7 — Multi-replica

Node A tạo authorization request trong local HttpSession, callback được load balancer gửi tới Node B. Browser có đủ cookie.

**Câu hỏi:** SameSite=None có giải quyết không?

**Hướng giải:** Không. Cookie đã được gửi đúng; vấn đề là Node B không có session state. Dùng shared session store hoặc routing/session strategy thích hợp.

### Bài tập 8 — Third-party iframe

Portal login chạy trong iframe cross-site, cookie đã đặt `SameSite=None; Secure` nhưng một browser vẫn không gửi.

**Câu hỏi:** Điều đó có mâu thuẫn với SameSite=None không?

**Hướng giải:** Không. Browser có thể chặn third-party cookies vì privacy policy. SameSite=None là điều kiện về SameSite chứ không phải giấy phép vượt mọi chính sách browser.

### Bài tập 9 — Session ID sau login thay đổi

Trước callback user có `SESSION=S1`, sau callback Portal trả `Set-Cookie: SESSION=S2`.

**Câu hỏi:** Có phải bug?

**Hướng giải:** Không nhất thiết. Session fixation protection thường đổi session ID sau authentication. Kiểm tra session continuity trước callback và cookie mới sau login; không tắt bảo vệ để giữ S1.

### Bài tập 10 — CORS không sửa callback

Login GET callback lỗi thiếu state. Team đề xuất:

~~~http
Access-Control-Allow-Origin: *
~~~

**Câu hỏi:** Có giúp browser top-level redirect gửi session cookie không?

**Hướng giải:** Không. CORS chủ yếu áp dụng cho cross-origin JavaScript requests; SameSite/Domain/Path/Secure và session repository quyết định cookie của OAuth callback navigation.

## 37. Checklist triển khai Cookie cho OAuth2/OIDC callback

| Câu hỏi | Điều cần xác nhận |
|---|---|
| Browser bắt đầu login ở host nào? | Public HTTPS canonical host |
| Callback trả về host nào? | Cùng host/path phù hợp cookie hoặc thiết kế rõ cross-host |
| Callback method là GET hay POST? | Quyết định SameSite policy |
| IdP và Portal cùng site không? | Dựa schemeful site/registrable domain |
| Session cookie là JSESSIONID hay SESSION? | Xác định cookie thực mang session |
| Cookie có Secure? | Có ở production HTTPS |
| Cookie có HttpOnly? | Có cho session identifier |
| Cookie SameSite là gì? | Lax cho top-level GET thông dụng, None nếu thật sự cần cross-site POST |
| None có Secure đi cùng? | Bắt buộc trên browser hiện đại |
| Cookie có Domain không? | Ưu tiên host-only nếu không cần chia sẻ |
| Cookie Path có match callback? | Có |
| Có dùng `__Host-` prefix? | Secure, Path=/, không Domain |
| Browser có thật sự lưu cookie? | Xem DevTools Storage và blocked reasons |
| Browser có gửi cookie ở callback? | Xem Network Request Headers của callback |
| Login có lưu OAuth2AuthorizationRequest? | Repository/session hoạt động |
| callback có cùng session chưa? | Session ID/TTL/store đúng |
| State/nonce/PKCE được kiểm tra? | Có, không bỏ để chữa cookie |
| Dùng form_post? | CSRF callback POST được thiết kế hẹp, cookie phù hợp |
| Dùng reverse proxy? | Forwarded headers đáng tin, public scheme/host đúng |
| Session store multi-node? | Shared store hoặc routing strategy ổn định |
| Có Spring Session? | Kiểm tra DefaultCookieSerializer, không nhầm container cookie |
| Có nhiều login tabs? | Test state correlation/concurrency |
| App có STATELESS chain? | Không phá login flow dùng HttpSession |
| Có iframe/third-party context? | Đánh giá browser privacy restrictions |
| Có tách CSRF/cookie session? | Giữ HttpOnly cho session, CSRF defense phù hợp |
| Có test browser thật? | Có, không chỉ curl/MockMvc |
| Logs có lộ session/codes/tokens? | Đã mask secrets, query và headers |

## 38. Tổng kết

Cookie **`Secure`**, **`HttpOnly`** và **`SameSite`** bảo vệ những khía cạnh khác nhau của phiên đăng nhập. Secure hạn chế cookie trên kênh HTTP không an toàn; HttpOnly ngăn JavaScript đọc trực tiếp session ID; SameSite quyết định browser có gửi cookie trong các ngữ cảnh same-site/cross-site hay không. Kèm theo đó, **Domain** và **Path** quy định cookie được gửi tới host/path nào.

Với **Spring Security OAuth2/OIDC Client trên Servlet**, Authorization Code Flow thường lưu `OAuth2AuthorizationRequest` trong **HttpSession**. Khi browser quay lại callback, nó phải mang **đúng session cookie** để Spring Security tìm và so sánh `state`, cùng dữ liệu `nonce`/PKCE cần thiết. Vì vậy, **SameSite=Lax** thường phù hợp với **top-level GET callback** từ IdP khác site; **Strict** dễ làm mất cookie; **None; Secure** có thể cần cho **form_post POST** nhưng phải kết hợp CSRF callback handling và vẫn có thể gặp browser privacy restrictions.

Khi OAuth callback lỗi, cần điều tra **browser cookie storage và request headers**, **callback method/scheme/host/path**, **forwarded proxy headers**, **server-side session store**, rồi mới đến state/token validation. **Không tắt HttpOnly, CSRF, state, nonce hoặc PKCE để che dấu một cookie configuration bug.** Cấu hình cookie và login flow đúng không chỉ giúp đăng nhập ổn định, mà còn giữ ranh giới giữa **browser session**, **OAuth2 authorized client** và **bảo mật của Authorization Server/Resource Server**.
