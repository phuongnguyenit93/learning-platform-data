# Cấu hình CSRF SPA chuyên biệt từ Spring Security 7.0

> **Chương:** Cấu hình và phiên bản  
> **Module:** `SPRING_SECURITY_HTTP_PROTECTION`  
> **Mục tiêu:** Hiểu và áp dụng cấu hình chống Cross-Site Request Forgery (CSRF) chuyên biệt cho Single-Page Application (SPA) kể từ **Spring Security 7.0**, nắm ranh giới Servlet/Reactive, cookie, BREACH, deferred token, login/logout, CORS và kiểm thử phòng vệ HTTP.  
> **Phiên bản:** Tài liệu tham chiếu Spring Security **7.0** và phương án migration từ **6.5**. Dòng 7.0 bổ sung `CsrfConfigurer.spa()` cho **Servlet `HttpSecurity`**; không suy rằng WebFlux có API cùng tên.

## 1. Vì sao SPA cần cấu hình CSRF riêng?

Một trang web truyền thống thường gửi HTML form do server render. Spring Security có thể chèn CSRF token vào trường ẩn `_csrf`; trình duyệt gửi token đó trong POST. SPA React/Vue/Angular lại thường tải một trang HTML ban đầu và sau đó gọi API JSON bằng `fetch`/XHR, không sử dụng form HTML được server render ở mọi request.

Nếu user đăng nhập bằng session cookie, browser có thể **tự gắn** cookie xác thực vào request; một website bên ngoài có khả năng khiến browser gửi request thay đổi trạng thái đến server. Vì vậy, cùng là JSON API nhưng nếu dùng **cookie/session**, vẫn cần CSRF — và cần cách để JavaScript nhận token rồi gửi lại bằng **header không tự động được browser thêm**.

Ví dụ:

```text
Người dùng đăng nhập -> cookie session của api.example.com
                                |
                   Browser tự gửi cookie cho API
                                |
    Website độc hại ----------> POST /api/transfer
                                |
                 Auth cookie hợp lệ là CHƯA ĐỦ
                 CSRF token hợp lệ phải được kiểm tra
```

**Không nhầm:** CSRF không thay authentication/authorization; CORS cũng không thay CSRF. CORS giới hạn quyền đọc response từ JavaScript của origin khác theo cơ chế browser, nhưng không ngăn mọi dạng request cross-site có side effect. Cookie `SameSite` hữu ích như lớp bổ sung, song không phải lý do mặc nhiên tắt CSRF cho ứng dụng dùng cookie.

### Kết quả học tập

Sau bài này, bạn có thể:

1. Giải thích vì sao CSRF mặc định ở Servlet dùng session repository không tự sinh cookie `XSRF-TOKEN` cho SPA.
2. Phân biệt token thô (*raw token*) trong cookie với token biểu diễn đã được che ngẫu nhiên nhằm chống **BREACH**.
3. Hiểu deferred loading và lý do token phải được cấp mới sau authentication/logout.
4. Cấu hình `http.csrf(csrf -> csrf.spa())` trên Servlet **Spring Security từ 7.0**.
5. Biết cách tích hợp frontend theo mô hình same-origin và xử lý trường hợp frontend/backend khác origin.
6. Không sao chép `.spa()` vào `ServerHttpSecurity` của WebFlux; chọn cách cung cấp/kiểm tra token phù hợp Reactive.
7. Kiểm thử token thiếu, sai, hợp lệ, token cũ sau login/logout, CORS preflight, CSRF chain selection và headers bảo vệ khác.

## 2. Ma trận phiên bản: điểm mới thật sự ở 7.0

| Dòng Spring Security | Mặc định CSRF Servlet | Tích hợp SPA |
| --- | --- | --- |
| **5.x** | CSRF bật, thường dùng `HttpSessionCsrfTokenRepository` | Có thể sử dụng cookie repository, nhưng khi nâng major phải xét lại token lifecycle |
| **6.0–6.4** | CSRF bật; deferred token và BREACH masking theo mặc định | Thường cần `CookieCsrfTokenRepository` và `CsrfTokenRequestHandler` tùy chỉnh, đồng thời khởi tạo token sau login/logout |
| **6.5** | Cùng mô hình CSRF 6.x; tài liệu có ví dụ SPA handler tự viết | Chưa có `CsrfConfigurer.spa()`; dùng cấu hình thủ công nếu vẫn ở 6.5 |
| **7.0+ Servlet** | CSRF vẫn bật, default repository không tự đổi chỉ vì nâng version | **Thêm `CsrfConfigurer.spa()`** tạo cookie-based repository và handler phù hợp SPA |
| **7.0+ Reactive/WebFlux** | CSRF bật, default `WebSessionServerCsrfTokenRepository` | `ServerHttpSecurity.CsrfSpec` **không có `spa()`**; cần thiết kế WebFlux riêng |

Với Spring Security 7, cần sử dụng Lambda DSL theo yêu cầu của dòng mới. `csrf(csrf -> csrf.spa())` là **cấu hình được chủ động bật trên một chain Servlet**, không có nghĩa “toàn bộ ứng dụng tự chuyển thành SPA” sau khi cập nhật dependency.

Javadoc chính thức của `CsrfConfigurer.spa()` ghi `Since: 7.0`; chức năng này chọn cookie repository và một request handler giải quyết token thô từ header. Đây là điểm khác với việc chỉ gọi `csrf(Customizer.withDefaults())`. Hãy tra phiên bản `spring-security-config` đã resolve bằng Maven/Gradle, không dựa duy nhất vào dòng Spring Boot ghi trong `pom.xml` hoặc `build.gradle`.

**Dấu hiệu sai phiên bản:** IDE báo `Cannot resolve method 'spa'` trên `CsrfConfigurer` trong project Security 6.5; cách xử lý là chọn hướng dẫn 6.5 hoặc nâng cả tổ hợp Boot/Framework/Security tương thích, **không** ép riêng module Security 7 vào Spring Boot cũ.

## 3. Cấu trúc CSRF Servlet: repository, handler và filter

Spring Security Servlet thường dùng ba thành phần:

| Thành phần | Trách nhiệm | Mặc định hoặc chế độ SPA |
| --- | --- | --- |
| `CsrfFilter` | Xác định request cần bảo vệ, tải và kiểm tra token | Áp dụng theo security chain đã chọn |
| `CsrfTokenRepository` | Sinh, lưu và tải token kỳ vọng | Mặc định `HttpSessionCsrfTokenRepository`; `spa()` chọn `CookieCsrfTokenRepository` |
| `CsrfTokenRequestHandler` | Expose token cho ứng dụng và đọc token từ request | Mặc định `XorCsrfTokenRequestAttributeHandler`; SPA cần nhận header chứa **raw token** |

Điểm quan trọng: **nơi lưu token**, **cách trình bày token cho client** và **cách phân giải token client gửi lên** là ba quyết định khác nhau. Chỉ thấy có cookie `XSRF-TOKEN` chưa đủ kết luận CSRF đang bật; phải thử POST thiếu/sai token.

### 3.1. Mặc định dựa trên session, không tự tạo cookie cho JavaScript

```java
http.csrf(Customizer.withDefaults());
```

Trong Servlet, mặc định repository là `HttpSessionCsrfTokenRepository`. Token kỳ vọng lưu ở `HttpSession`; ứng dụng có thể expose token cho JSP/Thymeleaf hoặc controller. Điều này hợp lý cho server-rendered form nhưng SPA cần tích hợp thêm cách lấy token.

Trong trường hợp dùng cookie, `CookieCsrfTokenRepository` mặc định nhận token từ `X-XSRF-TOKEN` header (hoặc `_csrf` parameter) và ghi cookie `XSRF-TOKEN`. Khi dùng `withHttpOnlyFalse()`, cookie được JavaScript đọc để chuyển thành header. **Đây là CSRF cookie riêng, không phải cookie session xác thực**: session cookie vẫn nên giữ `HttpOnly` nếu có thể.

### 3.2. BREACH: vì sao token ở HTML khác giá trị trong cookie?

Từ Spring Security 6, `XorCsrfTokenRequestAttributeHandler` che token bằng ngẫu nhiên để chống các tình huống rò rỉ bí mật qua nén phản hồi (BREACH). Giá trị token khi được trình bày cho HTML/form có thể **thay đổi ở mỗi request**, dù token nền tảng chưa đổi.

Cookie chứa **token thô** để JavaScript đọc; SPA gửi chính giá trị ấy trong header. Nếu server áp mặc định handler XOR để đọc header, handler có thể đòi token ở dạng mã hóa trong khi frontend chỉ có raw token, dẫn tới 403. Không giải quyết bằng cách tắt toàn bộ BREACH protection cho cả ứng dụng.

```text
Repository lưu token kỳ vọng: T
               |
               +--> HTML form / _csrf attribute
               |         token được che (masked: M(T, random))
               |         default XOR handler giải mã khi submit form
               |
               +--> Cookie XSRF-TOKEN: T
                         JavaScript đọc T (chỉ khi cookie đúng scope)
                         Request header X-XSRF-TOKEN: T
                         SPA handler đọc như plain token
```

Chế độ SPA cần **hai con đường đọc token**: giá trị thô từ request header SPA, và token đã che cho trường hợp form/request parameter truyền thống. `csrf.spa()` của Security 7 giải quyết việc này trong Servlet.

### 3.3. Deferred loading: tại sao token chưa chắc xuất hiện trên mọi GET?

Trong Spring Security 6+, việc tải token có thể được trì hoãn cho tới khi cần. Điều này giảm việc truy cập session/repository không cần thiết, nhưng dễ khiến SPA không có cookie mới trong lần GET mà developer cho rằng “phải có token”.

Ngoài ra, `CsrfAuthenticationStrategy` và `CsrfLogoutHandler` có thể xóa token trước đó khi xác thực thành công hoặc logout thành công. Token cũ trở nên không phù hợp; frontend phải có cơ chế lấy lại token **sau những sự kiện thay đổi trạng thái xác thực**.

`csrf.spa()` áp dụng handler SPA và cách tạo cookie phù hợp cho luồng này; tuy vậy, **đừng giả định mọi kiểu login, redirect, proxy, CORS hay client đều đã nhận cookie mới đúng thời điểm**. Cần xác minh cookie trên response thực tế, và dùng một request bootstrap an toàn để lấy token mới khi cần.

## 4. Cấu hình Spring Security 7 Servlet bằng `csrf.spa()`

Ví dụ một ứng dụng Spring MVC cung cấp SPA cùng origin qua reverse proxy: frontend gọi `/csrf` và `/api/orders` trên cùng origin với backend (proxy có thể route nội bộ tới các service khác nhau). Ứng dụng dùng form login/session cookie.

### 4.1. SecurityFilterChain đầy đủ

```java
package com.example.security;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configuration.EnableWebSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
@EnableWebSecurity
public class SpaSecurityConfiguration {

    @Bean
    SecurityFilterChain spaWeb(HttpSecurity http) throws Exception {
        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET,
                    "/", "/index.html", "/assets/**", "/csrf").permitAll()
                .requestMatchers("/api/admin/**").hasRole("ADMIN")
                .anyRequest().authenticated()
            )
            .csrf(csrf -> csrf.spa())
            .headers(headers -> headers
                .contentSecurityPolicy(csp -> csp
                    .policyDirectives(
                        "default-src 'self'; object-src 'none'; frame-ancestors 'none'"
                    )
                )
            )
            .formLogin(Customizer.withDefaults())
            .logout(Customizer.withDefaults());

        return http.build();
    }
}
```

**Cần hiểu đúng các thành phần:**

1. `csrf(csrf -> csrf.spa())` là **phần mới từ Security 7.0 trên Servlet**, không phải `csrf.disable()`.
2. `spa()` thiết lập `CookieCsrfTokenRepository.withHttpOnlyFalse()` và request handler cho SPA. Nó **không** tự thêm quyền truy cập URL, CORS allowlist, cookie session policies, CSP hay JWT authentication.
3. Mọi URL quan trọng được một chain xử lý vì không có `securityMatcher` hẹp. Nếu ứng dụng có nhiều chain, phải áp cấu hình SPA cho **chain nhận request browser dùng cookie**.
4. `permitAll()` ở `GET /csrf` chỉ miễn authorization: nó không tự tắt CSRF trên POST. CSRF vẫn bảo vệ những unsafe HTTP methods theo matcher mặc định.
5. `formLogin` và `logout` cần được tích hợp với SPA login state/token bootstrap; khi dùng custom login endpoint hoặc login với JSON cần thêm cấu hình tương ứng.
6. CSP ở ví dụ chỉ là baseline. Nếu frontend tải script từ CDN hoặc gọi API ở origin khác, phải thiết kế `script-src`/`connect-src` đúng nguồn.

Đoạn code giả định các endpoint và trang frontend tồn tại. Không có controller `/api/orders` thì test có thể nhận 404, dù security chain hoạt động chính xác. Với Spring Boot app đã có cấu hình Security khác, **không tạo thêm một chain chồng lấp** chỉ để gọi `spa()`; hãy cập nhật chain sở hữu URL.

### 4.2. Endpoint bootstrap để chủ động lấy cookie mới

Khi SPA cần bảo đảm token hiện diện trước POST (đặc biệt sau login/logout), có thể cung cấp một GET chỉ dùng để khởi tạo token:

```java
package com.example.security;

import org.springframework.http.CacheControl;
import org.springframework.http.ResponseEntity;
import org.springframework.security.web.csrf.CsrfToken;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class CsrfBootstrapController {

    @GetMapping("/csrf")
    public ResponseEntity<Void> csrf(CsrfToken token) {
        // Buộc truy xuất token trên request bootstrap.
        token.getToken();
        return ResponseEntity.noContent()
            .cacheControl(CacheControl.noStore())
            .build();
    }
}
```

Đây là một lựa chọn **bổ sung**, không phải yêu cầu bắt buộc cho mọi app dùng `spa()`. Response có thể dùng `Set-Cookie: XSRF-TOKEN=...` tùy việc token/cookie hiện đã tồn tại và chính sách repository. Frontend nhận cookie bằng browser, rồi đọc nó từ `document.cookie` **chỉ khi cookie thuộc domain/path mà trang được phép đọc**. Endpoint `/csrf` không cần trả token qua JSON ở mô hình cookie same-origin.

Nếu cookie bị xóa sau xác thực thành công/logout hoặc handler login trả redirect không làm token mới được quan sát như mong muốn, gọi lại GET `/csrf` trước khi gửi unsafe request. Thêm `Cache-Control: no-store` và kiểm tra CDN/proxy không cache nhầm response bootstrap.

### 4.3. Luồng dự kiến

```text
Browser GET /index.html
       |
       v
SPA gọi GET /csrf (cùng origin)
       |
       v
Spring Security CSRF repo tạo/tải token T
       |
       v
Set-Cookie: XSRF-TOKEN=T  (nếu cần)
       |
       v
JavaScript đọc cookie XSRF-TOKEN=T
       |
       v
POST /api/orders
  Cookie: JSESSIONID=...; XSRF-TOKEN=T
  X-XSRF-TOKEN: T
       |
       v
CsrfFilter so sánh header token với repository
       |
       +-- Thiếu/sai -> 403
       +-- Hợp lệ -> authorization và controller tiếp tục
```

**Cơ chế double-submit cookie không có nghĩa là “chỉ cần browser tự gửi hai cookie”.** Spring Security SPA cần frontend **đọc token và chủ động đưa vào header**; một request giả mạo từ website ngoài không tự biết/đính kèm header này nếu Same-Origin Policy và CORS được cấu hình đúng.

## 5. Mã frontend: đọc đúng cookie và gửi request header

Ví dụ JavaScript thuần dưới đây dành cho mô hình **same-origin**: trang `https://app.example.com` phục vụ frontend và reverse proxy cung cấp `/csrf`, `/api/orders` cùng origin. Cookie CSRF do backend cấp phải có Path phù hợp và được JavaScript đọc tại origin này.

```javascript
function readCookie(name) {
  const prefix = encodeURIComponent(name) + "=";
  const item = document.cookie
    .split("; ")
    .find((entry) => entry.startsWith(prefix));
  return item ? decodeURIComponent(item.slice(prefix.length)) : null;
}

async function refreshCsrfCookie() {
  const response = await fetch("/csrf", {
    method: "GET",
    credentials: "same-origin",
    cache: "no-store"
  });
  if (!response.ok) throw new Error("Cannot initialize CSRF token");
}

async function createOrder(order) {
  let token = readCookie("XSRF-TOKEN");
  if (!token) {
    await refreshCsrfCookie();
    token = readCookie("XSRF-TOKEN");
  }
  if (!token) throw new Error("CSRF cookie not visible to this page");

  const response = await fetch("/api/orders", {
    method: "POST",
    credentials: "same-origin",
    headers: {
      "Content-Type": "application/json",
      "X-XSRF-TOKEN": token
    },
    body: JSON.stringify(order)
  });
  if (!response.ok) throw new Error("Request was not accepted");
  return response;
}
```

Sau login/logout thành công, ứng dụng cần làm mới trạng thái token và **chủ động gọi lại `refreshCsrfCookie()`** trước unsafe request tiếp theo, hoặc đảm bảo một flow tải trang mới đã cấp cookie. Khi nhận 403, đừng tự động retry vô hạn; có thể token cũ, hết phiên, user thiếu quyền hoặc CORS/proxy sai.

**Không sao chép thẳng `document.cookie` sang SPA khác origin rồi kỳ vọng đọc được cookie API.** Một script ở `https://app.example.com` không thể đọc cookie **host-only** của `https://api.example.com` mặc dù CORS có thể cho phép fetch. Cần chọn phương án cùng origin/BFF, hoặc thiết kế bootstrap token qua API có kiểm soát (mục 8), hoặc chia sẻ cookie domain sau khi đánh giá rủi ro; không nới cookie Domain chỉ để vượt qua lỗi.

## 6. Trên Spring Security 6.5: cấu hình thủ công thay cho `spa()`

Trước khi có API chuyên dụng từ 7.0, tài liệu Spring Security 6.x hướng dẫn ghép **cookie repository** và **request handler SPA tự viết**. Cơ chế này giúp người học hiểu chính xác thứ `spa()` mới gom lại, đồng thời phục vụ migration khi dự án chưa thể nâng lên dòng 7.

### 6.1. Ví dụ Servlet 6.5

```java
package com.example.security;

import java.util.function.Supplier;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import org.springframework.security.web.csrf.CookieCsrfTokenRepository;
import org.springframework.security.web.csrf.CsrfToken;
import org.springframework.security.web.csrf.CsrfTokenRequestHandler;
import org.springframework.security.web.csrf.CsrfTokenRequestAttributeHandler;
import org.springframework.security.web.csrf.XorCsrfTokenRequestAttributeHandler;
import org.springframework.util.StringUtils;

// Handler dùng cho Spring Security 6.5 Servlet;
// không cần sao chép sang Security 7 khi đã dùng csrf.spa().
final class LegacySpaCsrfTokenRequestHandler
        implements CsrfTokenRequestHandler {

    private final CsrfTokenRequestHandler plain =
        new CsrfTokenRequestAttributeHandler();

    private final CsrfTokenRequestHandler xor =
        new XorCsrfTokenRequestAttributeHandler();

    @Override
    public void handle(
            HttpServletRequest request,
            HttpServletResponse response,
            Supplier<CsrfToken> csrfToken) {

        // Form/server-rendered response vẫn có BREACH protection.
        this.xor.handle(request, response, csrfToken);

        // Buộc load token để cookie được tạo lại khi cần.
        csrfToken.get();
    }

    @Override
    public String resolveCsrfTokenValue(
            HttpServletRequest request,
            CsrfToken token) {

        String header = request.getHeader(token.getHeaderName());
        // SPA gửi raw token trong header; form có token đã che.
        return (StringUtils.hasText(header) ? plain : xor)
            .resolveCsrfTokenValue(request, token);
    }
}
```

Đưa handler trên vào **cấu hình Servlet Spring Security 6.5**:

```java
http.csrf(csrf -> csrf
    .csrfTokenRepository(CookieCsrfTokenRepository.withHttpOnlyFalse())
    .csrfTokenRequestHandler(new LegacySpaCsrfTokenRequestHandler())
);
```

**Lưu ý:** `LegacySpaCsrfTokenRequestHandler` ở đây là class do dự án tự tạo, **không** phải một public bean Spring Security cùng tên. Không copy code thủ công này sang 7.x nếu `csrf.spa()` đã đáp ứng use case; duy trì hai cơ chế chồng chéo chỉ làm khó debug.

### 6.2. So sánh cách cũ với cách mới

| Vấn đề | Servlet 6.5 | Servlet 7.0+ |
| --- | --- | --- |
| Nơi giữ token kỳ vọng | `CookieCsrfTokenRepository.withHttpOnlyFalse()` tự cấu hình | `spa()` chọn cookie repository |
| Đọc raw token từ header | Handler SPA tự viết chọn `CsrfTokenRequestAttributeHandler` | Handler nội bộ do `spa()` chọn |
| Giữ BREACH khi trình bày form token | Handler tự viết chuyển cho `XorCsrfTokenRequestAttributeHandler` | Handler nội bộ xử lý |
| Deferred token và cookie sau các sự kiện auth | Handler tự gọi `csrfToken.get()` để kích hoạt load khi request được xử lý | Chế độ SPA quản lý cách expose/load token phù hợp |
| Độ dài cấu hình | Nhiều dòng và class tùy chỉnh | `csrf(csrf -> csrf.spa())` |
| Các yêu cầu CORS, cookie scope, CSRF client header | **Vẫn phải giải quyết** | **Vẫn phải giải quyết** |

**Điểm migration quan trọng:** chỉ thay hai dòng custom handler/repository bằng `spa()` khi hành vi người dùng giữ nguyên. Nếu dự án có custom `CookieCsrfTokenRepository` (tên cookie, path, cookie customizer, Domain, Secure, SameSite), `spa()` có thể không giữ các tùy chỉnh đó. Hãy kiểm tra repository cuối cùng và response `Set-Cookie`; không bỏ các điều kiện bắt buộc chỉ để có cấu hình ngắn hơn.

### 6.3. Những điều `spa()` *không* tự giải quyết

- Phân biệt authentication session với bearer token và phạm vi security chain.
- Cookie `Domain`, `Path`, `Secure`, `SameSite` theo topology triển khai.
- CORS allowlist, preflight headers/credentials và browser third-party cookie policies.
- CSP chống XSS, output escaping, frame options và HSTS qua reverse proxy.
- Quy trình nhận token của client thực tế, nhất là cross-origin frontend.
- Cách xử lý khi login/logout thay đổi session/token mà SPA không refresh cookie.
- Bảo đảm HTML caching/CDN không làm lộ token hoặc phát nhầm token của người này cho người khác.

API mới là **tiện ích cấu hình**, không phải “giải pháp bảo mật toàn diện chỉ với một method”.

## 7. Servlet và Reactive không có cùng `spa()` API

Đây là ranh giới dễ bị bỏ qua khi nhóm có cả Spring MVC và Spring WebFlux.

| Tiêu chí | Servlet / Spring MVC | Reactive / WebFlux |
| --- | --- | --- |
| Builder | `HttpSecurity` | `ServerHttpSecurity` |
| Chain bean | `SecurityFilterChain` | `SecurityWebFilterChain` |
| CSRF filter | `CsrfFilter` | `CsrfWebFilter` |
| Default repository | `HttpSessionCsrfTokenRepository` | `WebSessionServerCsrfTokenRepository` |
| Repository cookie | `CookieCsrfTokenRepository` | `CookieServerCsrfTokenRepository` |
| Request handler | `CsrfTokenRequestHandler` | `ServerCsrfTokenRequestHandler` |
| Mặc định masking (6+) | `XorCsrfTokenRequestAttributeHandler` | `XorServerCsrfTokenRequestAttributeHandler` |
| **API `spa()` từ 7.0** | **Có, `CsrfConfigurer.spa()`** | **Không có trong `ServerHttpSecurity.CsrfSpec` của 7.0** |
| Kiểm thử | `MockMvc` + `spring-security-test` | `WebTestClient` + `spring-security-test` |

Nếu bạn sao chép:

```java
// KHÔNG HỢP LỆ cho WebFlux Spring Security 7.0:
serverHttpSecurity.csrf(csrf -> csrf.spa());
```

compiler sẽ không tìm thấy method `spa()` trên `ServerHttpSecurity.CsrfSpec`. Không chữa bằng cách ép kiểu sang Servlet `CsrfConfigurer` hoặc import `CookieCsrfTokenRepository` vào WebFlux. Chúng đại diện cho hai pipeline HTTP khác nhau.

### 7.1. Chiến lược Reactive khuyến nghị khi muốn giữ BREACH mặc định

Trong WebFlux, một cách rõ ràng là dùng **WebSession repository mặc định** và cung cấp token cho SPA qua endpoint `GET /csrf`. Server trả giá trị token được request handler expose, và SPA gửi lại đúng giá trị trong request header. Với default XOR handler ở WebFlux, token có thể là **dạng đã che**; frontend **không tự chuyển nó thành raw token từ cookie**.

Ví dụ WebFlux độc lập:

```java
package com.example.security.reactive;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.web.server.SecurityWebFilterChain;

@Configuration
class ReactiveSecurityConfig {

    @Bean
    SecurityWebFilterChain webFlux(ServerHttpSecurity http) {
        return http
            .authorizeExchange(auth -> auth
                .pathMatchers(HttpMethod.GET, "/csrf").permitAll()
                .pathMatchers("/api/admin/**").hasRole("ADMIN")
                .anyExchange().authenticated()
            )
            .csrf(Customizer.withDefaults())
            .formLogin(Customizer.withDefaults())
            .build();
    }
}
```

Trong ví dụ trên, `csrf(Customizer.withDefaults())` giữ WebFlux CSRF mặc định, không dùng `spa()`. Tiếp theo cung cấp token thông qua exchange attribute:

```java
package com.example.security.reactive;

import java.util.Map;
import org.springframework.http.CacheControl;
import org.springframework.http.ResponseEntity;
import org.springframework.security.web.server.csrf.CsrfToken;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ServerWebExchange;
import reactor.core.publisher.Mono;

@RestController
class ReactiveCsrfEndpoint {

    @GetMapping("/csrf")
    public Mono<ResponseEntity<Map<String, String>>> csrf(
            ServerWebExchange exchange) {

        Mono<CsrfToken> tokenMono =
            exchange.getAttribute(CsrfToken.class.getName());
        if (tokenMono == null) {
            return Mono.error(new IllegalStateException(
                "CSRF filter did not expose a token"));
        }

        return tokenMono.map(token ->
            ResponseEntity.ok()
                .cacheControl(CacheControl.noStore())
                .body(Map.of(
                    "headerName", token.getHeaderName(),
                    "token", token.getToken()
                ))
        );
    }
}
```

`CsrfWebFilter` expose `Mono<CsrfToken>` trong `ServerWebExchange` theo tên `CsrfToken.class.getName()`; controller **subscribe bằng cách trả Mono**, không gọi `block()` trong event loop. Token do handler expose cần được client gửi lại không biến đổi trong header được trả về. Đây là một phương án **khác** so với Servlet SPA đọc raw cookie: không được trộn các dạng token/handler giữa hai phương án.

Endpoint chỉ phục vụ một mục đích: cấp token cho client trong session/exchange thích hợp. Đặt response `Cache-Control: no-store` và không log token. Nếu endpoint được phép anonymous để client lấy token trước login, phải kiểm tra CORS, rate limit, cookie/session và cơ chế refresh sau login/logout; cấp CSRF token **không** tương đương cấp authenticated session.

### 7.2. Frontend dùng endpoint Reactive

Ví dụ JavaScript với API cùng origin:

```javascript
async function getCsrfEnvelope() {
  const response = await fetch("/csrf", {
    method: "GET",
    credentials: "same-origin",
    cache: "no-store"
  });
  if (!response.ok) throw new Error("Cannot obtain CSRF token");
  return response.json();
}

async function updateProfile(profile) {
  const csrf = await getCsrfEnvelope();
  return fetch("/api/profile", {
    method: "POST",
    credentials: "same-origin",
    headers: {
      "Content-Type": "application/json",
      [csrf.headerName]: csrf.token
    },
    body: JSON.stringify(profile)
  });
}
```

Mẫu lấy token trước request giúp tránh token cũ sau login/logout, nhưng có thêm HTTP request. Ứng dụng có thể cache token ở client theo vòng đời session và refresh sau sự kiện auth, song phải có test token stale và tránh lưu lâu trong localStorage hay log. Nếu API không cùng origin, phải điều chỉnh `fetch` credentials và **CORS allowlist**, giữ cookie scope đúng.

### 7.3. Khi dùng Reactive cookie repository

WebFlux cũng có:

```java
import org.springframework.security.web.server.csrf.CookieServerCsrfTokenRepository;

http.csrf(csrf -> csrf
    .csrfTokenRepository(CookieServerCsrfTokenRepository.withHttpOnlyFalse())
);
```

Nhưng đoạn này **chỉ đổi repository**, không tương đương với `HttpSecurity.csrf(csrf -> csrf.spa())`: default `XorServerCsrfTokenRequestAttributeHandler` có cách resolve token bị che. SPA đọc **raw cookie** và gửi header thô có thể không khớp handler mặc định. Nếu cần flow cookie/header tương tự Servlet, phải lựa chọn/request handler Reactive phù hợp và đảm bảo token được load khi cần; việc thay bằng `ServerCsrfTokenRequestAttributeHandler` có thể **bỏ BREACH protection**, nên phải có đánh giá rủi ro và kiểm thử.

Một cách ít mơ hồ hơn khi không cần JavaScript đọc cookie là giữ **WebSession repository + `GET /csrf` trả token đang được handler expose** như mục 7.1–7.2.

## 8. Cùng-origin, khác-origin và cookie: ba tầng không được đánh đồng

### 8.1. Same-origin qua proxy/BFF

Ví dụ:

```text
Trình duyệt: https://app.example.com
  GET /index.html  ----> CDN/BFF
  GET /csrf        ----> proxy -> Spring Servlet
  POST /api/orders ----> proxy -> Spring Servlet

Browser chỉ thấy CÙNG ORIGIN https://app.example.com
XSRF-TOKEN cookie ở host app.example.com có thể được JavaScript đọc
Session cookie auth vẫn cần HttpOnly/Secure/SameSite phù hợp
```

Ưu điểm là không cần CORS cho những fetch cùng origin; ít nhầm lẫn về cookie hostname và credentials. Tuy nhiên, proxy phải chuyển `Set-Cookie` và `Cookie` đúng, giữ Path/Domain, cache và HTTPS, không để endpoint login/token lọt khỏi security chain.

### 8.2. SPA và API khác subdomain

```text
Frontend: https://app.example.com
API:      https://api.example.com

Chúng khác ORIGIN, có thể cùng SITE nếu cùng scheme và registrable domain.
Cookie host-only do api.example.com ghi:
  -> browser có thể gửi tới api.example.com nếu chính sách cho phép
  -> JavaScript ở app.example.com KHÔNG đọc được cookie host-only đó
```

`Access-Control-Allow-Origin: https://app.example.com` giúp frontend đọc **response API** khi chính sách CORS cho phép; nó **không cấp quyền JavaScript đọc cookie host-only của api.example.com qua `document.cookie`**.

Các lựa chọn thiết kế:

| Lựa chọn | Lợi ích | Điều cần đánh giá |
| --- | --- | --- |
| Same-origin reverse proxy/BFF | Đọc cookie XSRF bằng JS tại cùng host, không cần CORS cho API call | Proxy path, Set-Cookie, session và cache |
| Endpoint `GET /csrf` trả token qua JSON | Không cần JS đọc cookie ở API host | CORS đúng allowlist/credentials, caching, không lộ token sang origin lạ |
| Cookie `Domain=.example.com` | Script ở các subdomain có thể nhìn thấy cookie không HttpOnly theo scope | Mở rộng bề mặt tấn công: subdomain bị compromise, cookie injection, ranh giới tin cậy |
| Chuyển sang Bearer-only API đúng threat model | Không có session cookie auth auto-sent nên nguy cơ CSRF thay đổi | Token storage/XSS, authentication scheme, không chấp nhận cookie ngầm |

Đừng cấu hình `Domain=.example.com` cho **session authentication cookie** chỉ để JavaScript đọc được CSRF token. Cookie auth vẫn nên được bảo vệ chặt; nếu chia sẻ CSRF cookie, đánh giá cả việc tên miền phụ không đáng tin có thể ghi/chèn cookie.

### 8.3. CORS preflight khi gửi header CSRF

Frontend khác origin gửi `X-XSRF-TOKEN` và `Content-Type: application/json` thường phát sinh preflight:

```http
OPTIONS /api/orders HTTP/1.1
Host: api.example.com
Origin: https://app.example.com
Access-Control-Request-Method: POST
Access-Control-Request-Headers: content-type,x-xsrf-token
```

Nguồn CORS phải cho phép **exact frontend origin**, method POST và các header tương ứng. Nếu dùng session cookie cross-origin cần `Access-Control-Allow-Credentials: true` cùng `Access-Control-Allow-Origin` cụ thể, không wildcard. Frontend phải dùng `credentials: "include"` khi request khác origin.

Với Servlet:

```java
import java.util.List;
import org.springframework.context.annotation.Bean;
import org.springframework.web.cors.CorsConfiguration;
import org.springframework.web.cors.UrlBasedCorsConfigurationSource;

@Bean
UrlBasedCorsConfigurationSource corsConfigurationSource() {
    CorsConfiguration cors = new CorsConfiguration();
    cors.setAllowedOrigins(List.of("https://app.example.com"));
    cors.setAllowedMethods(List.of("GET", "POST", "PUT", "DELETE"));
    cors.setAllowedHeaders(
        List.of("Content-Type", "X-XSRF-TOKEN", "X-CSRF-TOKEN"));
    cors.setAllowCredentials(true);

    UrlBasedCorsConfigurationSource source =
        new UrlBasedCorsConfigurationSource();
    source.registerCorsConfiguration("/**", cors);
    return source;
}
```

Thêm `http.cors(Customizer.withDefaults())` nếu chain cần tích hợp CORS từ nguồn này. Nếu có nhiều source, dùng `cors.configurationSource(source)` tường minh cho chain. **WebFlux phải dùng `org.springframework.web.cors.reactive.UrlBasedCorsConfigurationSource`**, không dùng source Servlet.

Browser có thể gửi request cross-origin ngay cả khi không được đọc response trong một số tình huống; CORS **không thay CSRF**. Hãy kiểm tra origin lạ không được cấp quyền đọc, rồi kiểm tra POST thiếu token bị CSRF từ chối.

### 8.4. Cookie security và SPA CSRF

- `Secure`: cookie auth/CSRF truyền trên HTTPS theo policy; local HTTP và TLS proxy cần kiểm thử riêng.
- `HttpOnly`: nên bật cho **session authentication cookie**; riêng cookie XSRF dùng `withHttpOnlyFalse()` để JavaScript đọc nếu kiến trúc thật sự cần.
- `SameSite`: quyết định browser có gửi cookie trong yêu cầu cross-site; **cross-origin khác same-site**.
- `Domain`/`Path`: cookie phải thuộc host/path của trang khi JS cần đọc, và thuộc API URL khi browser cần gửi.
- Logout/session rotation: token cũ có thể bị xóa, phải cấp mới đúng vòng đời.
- Cấu hình reverse proxy/CDN: không cache nhầm `Set-Cookie`/token của người này cho người khác.

`spa()` không loại trừ nguy cơ **XSS**: nếu attacker chạy JavaScript trong origin tin cậy, script có thể đọc cookie XSRF không HttpOnly. Vì vậy phải tiếp tục dùng CSP hợp lý, output encoding, validation và dependency hygiene. Không quảng bá CSRF token như biện pháp bảo vệ XSS.

## 9. Nhiều security chain: SPA CSRF chỉ có hiệu lực trong chain được chọn

Giả sử hệ thống có API Bearer-only tách biệt với giao diện dùng session cookie:

```text
@Order(1) API chain: securityMatcher("/machine/**")
          - OAuth2 Resource Server / Bearer JWT
          - Không có browser credential tự gửi
          - Có thể tắt CSRF sau khi duyệt threat model

@Order(2) Browser/SPA chain: matcher còn lại
          - Form login / session cookie
          - csrf(csrf -> csrf.spa())
          - CORS, CSP, HTTPS headers và session policy
          - GET /csrf, POST /api/orders, POST /logout
```

Ví dụ khung Servlet:

```java
@Bean
@Order(1)
SecurityFilterChain machineApi(HttpSecurity http) throws Exception {
    http
        .securityMatcher("/machine/**")
        .authorizeHttpRequests(a -> a
            .anyRequest().authenticated()
        )
        .csrf(csrf -> csrf.disable()) // Chỉ theo Bearer-only threat model
        .oauth2ResourceServer(oauth2 -> oauth2
            .jwt(Customizer.withDefaults())
        );
    return http.build();
}

@Bean
@Order(2)
SecurityFilterChain browser(HttpSecurity http) throws Exception {
    http
        .authorizeHttpRequests(a -> a
            .requestMatchers(HttpMethod.GET, "/", "/csrf").permitAll()
            .requestMatchers("/admin/**").hasRole("ADMIN")
            .anyRequest().authenticated()
        )
        .csrf(csrf -> csrf.spa())
        .formLogin(Customizer.withDefaults())
        .logout(Customizer.withDefaults());
    return http.build();
}
```

Đoạn này là **khung phân chain**, không chứa toàn bộ CORS/CSP/cookie settings của production. Không dùng `csrf.spa()` ở machine-to-machine Bearer API nếu client không cần và không dùng CSRF cookie; không tắt CSRF ở browser chain chỉ vì có một API khác stateless.

**Cấp chain vs cấp CSRF request matcher:**

- `securityMatcher` chọn filter chain và quyết định có CSRF filter của chain đó hay không.
- `csrf.ignoringRequestMatchers(...)` (Servlet) miễn CSRF cho một request **bên trong chain**; không làm request trở thành authenticated hoặc được authorization cho phép.
- `authorizeHttpRequests(...permitAll())` chỉ quyết định authorization; `POST /public/feedback` vẫn cần CSRF khi thuộc SPA chain có bảo vệ.
- Nếu thiếu **fallback chain**, các URL ngoài matcher hẹp có thể không vào bất kỳ Spring Security chain nào. Không trông chờ Spring Boot tự sinh chain bảo vệ phần còn lại sau khi đã khai báo custom chain.

Với Servlet Spring Security 7, string URL matcher dùng `PathPatternRequestMatcher`; khi nâng từ 6.x, cần kiểm tra context path, servlet path, trailing slash và proxy rewrite để chắc chắn `/csrf`, `/login`, `/logout` thuộc chain dự kiến. Ở Reactive dùng `ServerWebExchangeMatcher`, không dùng Servlet matcher để chọn WebFlux chain.

## 10. Login và logout: khi nào token phải được cấp lại?

### 10.1. Vòng đời token điển hình

```text
1. Chưa đăng nhập
   GET /csrf -> nhận XSRF-TOKEN=T1

2. Gửi POST /login
   Cookie session / token T1 + X-XSRF-TOKEN:T1
   -> server xác thực -> CsrfAuthenticationStrategy xóa token cũ

3. Sau login thành công
   SPA fetch GET /csrf -> nhận token mới T2

4. POST /api/orders
   Cookie session đã đăng nhập + X-XSRF-TOKEN:T2
   -> được kiểm tra rồi mới xử lý nghiệp vụ

5. POST /logout với token hợp lệ
   -> CsrfLogoutHandler xóa token, logout handler xóa/đổi session

6. SPA cần gọi GET /csrf trước unsafe request mới
   -> có thể nhận token T3
```

Đây là **mô hình kỳ vọng**, không phải cam kết thứ tự Set-Cookie giống hệt trên mọi app. Security 7 `spa()` tạo lại cookie phù hợp khi token được load; tùy flow redirect, response và proxy, client vẫn phải kiểm tra cookie mới có được quan sát trước POST hay không.

### 10.2. Thời điểm frontend cần refresh

- Sau tải lần đầu nếu `XSRF-TOKEN` chưa hiện diện.
- Sau login thành công, session fixation protection hoặc thay đổi authentication context.
- Sau logout thành công, trước bất kỳ POST/PUT/PATCH/DELETE tiếp theo.
- Sau phiên hết hạn/được gia hạn làm token cũ không còn phù hợp.
- Khi ứng dụng chuyển user hoặc đổi tenant/namespace nếu token repository phụ thuộc ngữ cảnh.

Nếu `POST` trả 403, phân biệt ba lỗi: **`MissingCsrfTokenException`**, **`InvalidCsrfTokenException`**, và **`AccessDeniedException` do authorization**. Không tự động retry POST có side effect khi không biết server đã xử lý được tới đâu; với thao tác thanh toán/đặt hàng, cần idempotency key và chính sách retry riêng.

### 10.3. Login endpoint phải nằm trong đúng security chain

Khi chain chỉ match `/secured/**` nhưng `formLogin` dùng endpoint mặc định `/login` nằm ngoài matcher, login filter không tự tạo endpoint global. Cần đặt login URL trong phạm vi chain hoặc sử dụng fallback bảo vệ `/login`, `/logout`. Nếu dùng login page custom, ứng dụng phải cung cấp GET page thực.

**Đừng thay login/logout thành GET có side effect** để né CSRF. Logout GET có thể bị kích hoạt cross-site. Giữ unsafe method phù hợp và đính CSRF token.

## 11. Kiểm thử Servlet bằng MockMvc: từ policy tới cookie thật

Một chương trình test cần ít nhất hai tầng:

1. **Unit/integration ở Spring Security:** `spring-security-test` cấp user và CSRF token để kiểm chứng filter chain.
2. **HTTP cookie round-trip:** thật sự lấy `XSRF-TOKEN` qua `GET /csrf`, gửi cookie và header, rồi xác nhận thiếu/sai/đúng token. Đây mới là kiểm thử riêng cho flow `spa()`.

### 11.1. Test mặc định CSRF vẫn bật

Giả sử ứng dụng có `POST /api/orders` trả 200 khi user `alice` có quyền và payload hợp lệ; `MockMvc mvc` đã tích hợp filter chain:

```java
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.user;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@Test
void spaPostStillNeedsCsrfToken() throws Exception {
    mvc.perform(post("/api/orders").with(user("alice")))
        .andExpect(status().isForbidden());

    mvc.perform(post("/api/orders")
            .with(user("alice"))
            .with(csrf().useInvalidToken()))
        .andExpect(status().isForbidden());

    mvc.perform(post("/api/orders")
            .with(user("alice"))
            .with(csrf()))
        .andExpect(status().isOk());
}
```

Ví dụ trên giả định controller/test fixture, chưa chứng minh cookie `XSRF-TOKEN` hoạt động. `with(csrf())` của `spring-security-test` cung cấp token phục vụ test, không tự kiểm tra JavaScript đã đọc được cookie raw hay CORS hoạt động đúng.

### 11.2. Test round-trip cookie/header của `spa()`

Ví dụ Servlet kiểm tra cookie từ chính repository và gửi raw token bằng header:

```java
import jakarta.servlet.http.Cookie;
import org.junit.jupiter.api.Test;
import org.springframework.test.web.servlet.MvcResult;

import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.user;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@Test
void spaCookieTokenCanBeSentInRequestHeader() throws Exception {
    MvcResult bootstrap = mvc.perform(get("/csrf"))
        .andExpect(status().isNoContent())
        .andReturn();

    Cookie xsrf = bootstrap.getResponse().getCookie("XSRF-TOKEN");
    assertNotNull(xsrf, "GET /csrf must initialize XSRF-TOKEN");

    mvc.perform(post("/api/orders")
            .with(user("alice"))
            .cookie(xsrf))
        .andExpect(status().isForbidden());

    mvc.perform(post("/api/orders")
            .with(user("alice"))
            .cookie(xsrf)
            .header("X-XSRF-TOKEN", "intentionally-wrong"))
        .andExpect(status().isForbidden());

    mvc.perform(post("/api/orders")
            .with(user("alice"))
            .cookie(xsrf)
            .header("X-XSRF-TOKEN", xsrf.getValue()))
        .andExpect(status().isOk());
}
```

Vì `CookieCsrfTokenRepository` đọc token kỳ vọng từ cookie, negative test chỉ đưa cookie mà **không có header** phải bị từ chối. Positive test cung cấp **cùng token** trong cookie và header; đây là điểm khác với form server-rendered dùng token đã masking.

Nếu endpoint nghiệp vụ trả 201 hoặc 204, thay `isOk()` theo contract. Test nếu không có handler `/api/orders` hoặc không gắn `springSecurity()` có thể báo kết quả sai. Tùy cookie lifecycle của từng bản Spring Security, những test có session riêng, custom cookie path hoặc proxy phải tạo fixture tương ứng; không chỉ dùng `getCookie` trên mock response rồi kết luận production browser sẽ nhìn thấy cookie.

### 11.3. Test login/logout và token rotation bằng flow thực

`with(user("alice"))` chỉ mô phỏng user, **không** kích hoạt mọi authentication success handler và session strategy thực. Vì vậy để kiểm tra token bị xóa/sinh mới:

1. GET `/csrf`, ghi nhận token `T1` và cookie/session của client test.
2. Đăng nhập bằng **POST thực tới login endpoint** (có token CSRF phù hợp), theo đúng credentials/test account.
3. Kiểm tra token `T1` không còn được chấp nhận sau khi authentication strategy invalidates nó.
4. GET `/csrf` lần nữa, nhận cookie mới `T2` (nếu repository cấp lại).
5. POST nghiệp vụ với `T2` qua đúng session, xác nhận được qua CSRF.
6. POST logout với token hợp lệ, kiểm tra phiên cũ mất hiệu lực.
7. GET `/csrf` trong trạng thái mới, kiểm tra token tiếp theo trước khi thực hiện unsafe method.

Thực hiện trong một cookie-aware client/jar hoặc trình duyệt E2E. Không hard-code giả định token luôn đổi trên mọi GET; **chỉ cần token cũ không còn hợp lệ sau sự kiện xóa/đổi token**.

## 12. Kiểm thử Reactive bằng WebTestClient

WebFlux không có `csrf.spa()`, nên test giúp xác minh lựa chọn **WebSession + `GET /csrf`** đã hoạt động đúng.

Với `WebTestClient client` bind vào `ApplicationContext` và áp dụng `springSecurity()`, controller `POST /api/orders` trả 200 nếu hợp lệ:

```java
import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.csrf;
import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.mockUser;

@Test
void webFluxPostMustHaveCsrfToken() {
    client.mutateWith(mockUser("alice"))
        .post().uri("/api/orders")
        .exchange()
        .expectStatus().isForbidden();

    client.mutateWith(mockUser("alice"))
        .mutateWith(csrf())
        .post().uri("/api/orders")
        .exchange()
        .expectStatus().isOk();
}

@Test
void csrfBootstrapEndpointReturnsTokenEnvelope() {
    client.get().uri("/csrf")
        .exchange()
        .expectStatus().isOk()
        .expectHeader().valueEquals(
            "Cache-Control", "no-store"
        )
        .expectBody()
        .jsonPath("$.token").isNotEmpty()
        .jsonPath("$.headerName").isNotEmpty();
}
```

Nếu hạ tầng thêm thành phần `Cache-Control` khác, kiểm tra chứa directive `no-store` thay vì so sánh tuyệt đối toàn chuỗi. Mặc định `WebTestClient` không cần làm việc trên network nếu bind vào context; điều này khác test qua HTTPS public. `mockUser()` không đăng nhập vào một server từ xa. Kiểm thử thật phải giữ WebSession cookie giữa GET `/csrf` và POST kế tiếp, rồi gửi **token mà endpoint trả về** trong header được chỉ định.

Ví dụ client test setup:

```java
WebTestClient client = WebTestClient
    .bindToApplicationContext(applicationContext)
    .apply(springSecurity())
    .configureClient()
    .build();
```

`csrf()` của `spring-security-test` xác nhận server chấp nhận một token hợp lệ; test endpoint token và HTTP round-trip cần được viết riêng để chứng minh SPA thực sự nhận token đúng.

## 13. Kiểm thử HTTP qua proxy: CORS, cookies, CSP và HSTS

Các lệnh sau là **mẫu** với hostname minh họa, chỉ thực hiện ở hệ thống bạn sở hữu và được phép kiểm thử:

```bash
# Bước 1: bootstrap token, giữ cookie vào cookie jar cục bộ.
curl -i -c csrf-cookie-jar.txt -b csrf-cookie-jar.txt \
  "https://app.example.com/csrf"

# Bước 2: kiểm tra preflight từ SPA origin được phép.
curl -i -X OPTIONS "https://api.example.com/api/orders" \
  -H "Origin: https://app.example.com" \
  -H "Access-Control-Request-Method: POST" \
  -H "Access-Control-Request-Headers: content-type,x-xsrf-token"

# Bước 3: preflight từ origin không được phép.
curl -i -X OPTIONS "https://api.example.com/api/orders" \
  -H "Origin: https://untrusted.example" \
  -H "Access-Control-Request-Method: POST"

# Bước 4: xem security headers trên HTTPS công khai.
curl -i "https://app.example.com/"
```

Ở bước 1, cookie jar chứa token/credential nhạy cảm: không commit lên Git, không dán nội dung vào log, xóa theo quy trình bảo mật. `curl` không thực thi CORS policy như browser, nên kết quả preflight là phép quan sát HTTP headers, **không** thay thế thử bằng browser.

### Điều cần quan sát

| Quan sát | Nếu đúng | Nếu sai, kiểm tra |
| --- | --- | --- |
| Cookie `XSRF-TOKEN` sau bootstrap | Có thể đọc bằng JS khi cùng hostname, không HttpOnly | Cookie Domain/Path, handler, cache, Set-Cookie proxy |
| Session cookie auth | `HttpOnly`/`Secure` theo policy | Reverse proxy TLS, container, session flags |
| POST thiếu token | Bị CSRF chặn | CSRF có bị tắt? Request đi vào đúng chain? |
| POST với raw token từ cookie vào `X-XSRF-TOKEN` | Vượt qua CSRF, tiếp tục authorization | Handler XOR/plain, token hết hạn hoặc sai cookie scope |
| OPTIONS origin đúng | Allow-origin/headers/method/credentials hợp lệ | CORS source, OPTIONS trước auth, ingress |
| OPTIONS origin lạ | Không được cấp phép origin | Allowlist quá rộng, proxy phản chiếu origin |
| HTML response | CSP phù hợp script/connect sources | CSP do CDN phục vụ, không phải API |
| HTTPS response | HSTS khi cấu hình | Proxy scheme, forwarded headers, chain header writer |

**Một CSRF request thành công không bảo đảm cả ứng dụng an toàn:** vẫn cần authorization, validation, XSS prevention, clickjacking defense, HTTPS, session fixation/timeout và HTTP firewall.

## 14. Chẩn đoán lỗi khi chuyển sang `csrf.spa()`

### Tình huống A — `Cannot resolve method 'spa'`

**Biểu hiện:** Java compiler/IDE không tìm thấy `spa()` trong lambda `csrf`.

**Khả năng:**

- Ứng dụng vẫn resolve `spring-security-config` 6.x.
- Đang dùng `ServerHttpSecurity` Reactive chứ không phải Servlet `HttpSecurity`.
- Classpath có module Spring Security nhiều dòng không tương thích.

**Cách xử lý:** xác minh dependency graph. Với Security 7 Servlet, dùng `http.csrf(csrf -> csrf.spa())`. Với Servlet 6.5, dùng handler thủ công hoặc giải pháp token endpoint của phiên bản đó. Với WebFlux, dùng `ServerHttpSecurity.CsrfSpec` và thiết kế Reactive riêng; không cố thêm dependency Servlet để “có method”.

### Tình huống B — Có cookie `XSRF-TOKEN` nhưng POST vẫn 403

**Biểu hiện:** response có `Set-Cookie: XSRF-TOKEN=...`, song API từ SPA bị 403.

**Nguyên nhân có thể:**

1. SPA **không gắn `X-XSRF-TOKEN` header**, chỉ gửi cookie tự động.
2. Header chứa token cũ, cookie mới sau login/logout.
3. JavaScript đọc nhầm cookie ở origin/path khác.
4. Có custom handler/repository ghi đè config mặc định của `spa()`.
5. Token header/raw không khớp chế độ XOR/handler mà server đang sử dụng.
6. Request được route vào security chain khác hoặc CSRF matcher bị tùy chỉnh.
7. `403` thực chất do thiếu quyền, không phải CSRF.

**Cách điều tra:** quan sát request ở browser Network tab: Cookie, `X-XSRF-TOKEN`, URL, method và status; kiểm tra server logs cho `MissingCsrfTokenException`/`InvalidCsrfTokenException`/AccessDenied. Không tắt CSRF toàn app để khắc phục.

### Tình huống C — Sau login lần thứ nhất mọi thứ chạy, sau logout/login lại thất bại

**Khả năng:** `CsrfAuthenticationStrategy`/`CsrfLogoutHandler` xóa token, SPA giữ token cũ trong biến/memory, không bootstrap lại. Một redirect có thể trả cookie mới mà client xử lý sai do proxy/CORS.

**Cách xử lý:** sau thay đổi auth state, lấy token mới và thay token đang giữ; kiểm thử cả browser cookie jar, session rotation, load balancer và HTTP redirects. Không retry tự động nhiều lần trên request có side effect mà không có idempotency controls.

### Tình huống D — Không thấy `XSRF-TOKEN` sau GET, dù đã bật `spa()`

**Khả năng:** request không đi qua chain gọi `spa()`, `/csrf` bị CDN phục vụ, cookie Path/Domain không được browser hiển thị, custom filter/cache cản `Set-Cookie`, hoặc client gửi/nhận cookie theo cơ chế khác.

**Cách xử lý:** test Servlet GET `/csrf` với `MockMvc` trước; sau đó kiểm tra HTTP public ở proxy, cookie jar và selected chain. Với Security 7, handler SPA được thiết kế để tải token và ghi cookie khi cần; nhưng không dùng “mọi GET phải có Set-Cookie” làm bất biến, vì token có thể đã tồn tại và không cần ghi lại.

### Tình huống E — SPA ở `app.example.com` không đọc được CSRF cookie của `api.example.com`

**Nguyên nhân:** JavaScript ở app host không được đọc cookie host-only của API host. Đây là ranh giới browser origin/cookie Domain, không phải lỗi Spring Security handler.

**Cách xử lý:** ưu tiên proxy/BFF same-origin hoặc token endpoint JSON có CORS và credentials kiểm soát. Chỉ mở rộng cookie domain sau khi đánh giá subdomain trust và cookie injection; không tắt `HttpOnly` của session cookie auth.

### Tình huống F — CORS preflight 401/403, browser không gửi POST thật

**Khả năng:** preflight OPTIONS không có session cookie; CORS source không phù hợp, thiếu `X-XSRF-TOKEN` trong allowedHeaders, sai origin/method, hoặc ingress chặn OPTIONS trước authentication.

**Cách xử lý:** gửi một preflight test có đủ `Origin`, `Access-Control-Request-Method` và `Access-Control-Request-Headers`, kiểm tra CORS filter trước authentication. `permitAll()` cho OPTIONS không thay CORS source.

### Tình huống G — Test `with(csrf())` pass nhưng SPA production vẫn bị 403

**Nguyên nhân:** `spring-security-test` hỗ trợ inject token hợp lệ trực tiếp trong test; nó không nhất thiết mô phỏng raw cookie lifecycle, JavaScript cookie access, CORS hay proxy.

**Cách xử lý:** thêm cookie round-trip `GET /csrf` -> `XSRF-TOKEN` -> `X-XSRF-TOKEN` -> POST, rồi E2E browser test qua HTTPS public. Dùng cả test token sai và token cũ sau login/logout.

### Tình huống H — Spring WebFlux không nhận raw token cookie dù dùng `CookieServerCsrfTokenRepository`

**Nguyên nhân:** WebFlux không có `csrf.spa()` và có default `XorServerCsrfTokenRequestAttributeHandler`. Cookie repository chỉ quyết định lưu token, không tự giải quyết ngữ nghĩa của header raw so với token bị che.

**Cách xử lý:** chọn giải pháp rõ ràng, ví dụ `GET /csrf` trả token được default Reactive handler expose và SPA gửi lại nguyên dạng; hoặc thiết kế custom Reactive handler đã kiểm chứng. Không làm mất BREACH protection một cách vô thức.

### Tình huống I — CSRF chạy nhưng trình duyệt vẫn báo CSP/CORS error

**Nguyên nhân:** `csrf.spa()` chỉ cấu hình CSRF; nó không cấp `Access-Control-Allow-Origin`, `connect-src` hay `script-src`.

**Cách xử lý:** xác định **ai phát HTML frontend** và CSP của nó; nếu dùng API khác origin, chỉnh CSP `connect-src` có chủ đích và cấu hình API CORS allowlist riêng. Không đặt CSP trên API response rồi kỳ vọng nó tác động tới HTML do CDN phục vụ.

### Tình huống J — Cookie session hết hạn giữa GET token và POST

**Nguyên nhân:** request bootstrap và request nghiệp vụ không cùng session context; cookie thiếu `Secure`/`SameSite`/`Domain`/`Path`, session store không dùng chung giữa nhiều replicas, hoặc session hết hạn.

**Cách xử lý:** test cookie jar duy trì qua HTTPS, session persistence/rotation, cùng session store hoặc topology load balancer phù hợp. Không coi CSRF token là xác thực danh tính; token hợp lệ không thay một session đăng nhập còn hiệu lực.

### Tình huống K — `XSRF-TOKEN` tồn tại nhưng request được phép dù header thiếu

**Đây là cảnh báo bảo mật cần kiểm tra ngay.** Có thể `csrf.disable()` ở chain hiện tại, CSRF request matcher loại trừ endpoint, method là GET/HEAD/OPTIONS, hoặc request không đi qua Spring Security filter chain.

Xác định chain `SecurityFilterChain` nhận URL (với `@Order`), method và matcher CSRF. Tạo POST state-changing test đã xác thực **không header và không parameter**; nếu vẫn được xử lý, phải điều tra ngoại lệ trước khi go-live.

## 15. Hướng nâng cấp từ 6.5 lên 7.x cho ứng dụng SPA

Một migration có thể đi theo thứ tự sau:

1. **Ghi nhận baseline:** Spring Boot/Framework/Security/JDK đã resolve, Servlet hay Reactive, chain matcher, cookie Domain/Path/flags, raw XSRF header và flow login/logout.
2. **Kiểm thử trước nâng:** POST thiếu token/sai token/đúng token; token mới sau login/logout; preflight hợp lệ/sai origin; CSP, HSTS và proxy path.
3. **Kiểm tra API mục tiêu:** `CsrfConfigurer.spa()` chỉ có từ Spring Security 7.0 Servlet. Nếu vẫn trên 6.5 hoặc đang chạy Reactive, chọn phương án đúng phiên bản/stack.
4. **Đơn giản hóa Servlet 7:** thay handler SPA thủ công và `CookieCsrfTokenRepository.withHttpOnlyFalse()` bằng `csrf(csrf -> csrf.spa())` khi các custom cookie behaviors đã được xem xét.
5. **Giữ cấu hình ngoài CSRF:** authorization, session/authentication, CORS allowlist, CSP, HSTS, cookie security và header writers; `spa()` không thay thế các phần này.
6. **Xác nhận token presentation:** frontend same-origin lấy raw token từ `XSRF-TOKEN` cookie, gửi `X-XSRF-TOKEN` header. Không nhầm với masked token trong form `_csrf`.
7. **Xác nhận token lifecycle:** thử login/logout, token cũ bị loại, token mới có thể lấy trước POST kế tiếp.
8. **Kiểm tra multi-chain:** request SPA thuộc đúng chain có `spa()`; Bearer-only API chỉ miễn CSRF nếu threat model đã duyệt; có fallback chain.
9. **Tách kiểm thử Reactive:** WebFlux dùng `ServerCsrfTokenRepository`/`ServerCsrfTokenRequestHandler` riêng; test token endpoint/header, không dùng `spa()`.
10. **Triển khai staging giống production:** TLS proxy, cookie/session store, CORS, CSP/CDN, HSTS, browser behavior và multi-instance.
11. **Quan sát sau deploy:** theo dõi `MissingCsrfTokenException`/`InvalidCsrfTokenException`, 401/403 và preflight failures mà không log token/cookie.
12. **Chuẩn bị rollback:** rollback cả code và config cookie/session/CORS; không dựa vào việc xóa dependency riêng lẻ khi đang dùng Boot BOM.

### Bảng đối chiếu trước/sau

| Kịch bản | Trước migration ở 6.5 | Sau migration ở Servlet 7+ | Ý nghĩa |
| --- | --- | --- | --- |
| GET bootstrap từ same-origin SPA | Tạo/đọc XSRF cookie theo handler cũ | Cookie SPA được khởi tạo qua cấu hình chuyên biệt | Client có nguồn token |
| POST thiếu `X-XSRF-TOKEN` | 403 | 403 | Chống CSRF không bị tắt |
| POST sai token | 403 | 403 | Kiểm tra giá trị token vẫn có hiệu lực |
| POST đúng raw token | Vượt CSRF | Vượt CSRF | Đọc token từ header SPA |
| Form dùng token đã masking | Vẫn chạy nếu handler cũ hỗ trợ XOR | Vẫn cần test form và header tương ứng | Không mất BREACH handling |
| Sau login/logout dùng token cũ | Bị từ chối | Bị từ chối | Rotation/invalidations hoạt động |
| Sau login/logout lấy token mới | Hoạt động | Hoạt động | SPA không mất khả năng POST |
| CORS origin lạ | Không được cấp permission | Không được cấp permission | CSRF không thay CORS |
| WebFlux compile `csrf.spa()` | Không hỗ trợ | Vẫn không hỗ trợ API Servlet này | Không áp dụng sai web stack |

Đây là **bảng kỳ vọng về hợp đồng**, không phải báo cáo một dự án đã chạy test thật. Hãy biến từng dòng thành test của ứng dụng mình.

## 16. Bài tập thực hành

### Bài tập 1 — Phân biệt CSRF cookie, session cookie và masked token

Một SPA dùng `CookieCsrfTokenRepository`, nhận cookie `XSRF-TOKEN` và gửi header `X-XSRF-TOKEN`. Hãy giải thích:

- Vì sao browser tự gửi `JSESSIONID` vẫn chưa đủ chống CSRF?
- Vì sao `XSRF-TOKEN` được JavaScript đọc còn `JSESSIONID` nên giữ HttpOnly?
- Vì sao token trong JSP `_csrf` có thể khác chuỗi raw trong cookie?
- Vai trò của `CsrfTokenRequestHandler` là gì?

### Bài tập 2 — Chuyển ứng dụng Servlet 6.5 sang 7

Cho cấu hình có `CookieCsrfTokenRepository.withHttpOnlyFalse()` và `LegacySpaCsrfTokenRequestHandler`. Viết phiên bản rút gọn bằng `csrf(csrf -> csrf.spa())`. Thêm test GET `/csrf` tạo cookie, POST thiếu header bị 403, POST có header raw hợp lệ được đi tiếp và token cũ bị vô hiệu hóa sau logout.

### Bài tập 3 — Frontend khác subdomain

SPA ở `https://app.example.com`, API ở `https://api.example.com`. Backend cấp cookie `XSRF-TOKEN` host-only cho `api.example.com`, và CORS cho phép `app.example.com`. Tại sao JavaScript ở app domain vẫn không thấy cookie qua `document.cookie`? Đề xuất ít nhất hai kiến trúc an toàn (BFF/same-origin, token endpoint JSON có CORS credentials, hoặc chính sách Domain sau đánh giá rủi ro).

### Bài tập 4 — WebFlux không có `spa()`

Tạo ứng dụng WebFlux với `SecurityWebFilterChain`, repository `WebSessionServerCsrfTokenRepository` và endpoint `GET /csrf` trả token từ exchange attribute. Client gọi POST với header/token nhận được. Thêm test thiếu token, sai token và token đúng. Giải thích vì sao `CookieServerCsrfTokenRepository.withHttpOnlyFalse()` một mình chưa tương đương cấu hình Servlet SPA.

### Bài tập 5 — CORS, CSP và CSRF trong SPA

Frontend khác origin gọi POST JSON với `X-XSRF-TOKEN` và session cookie. Hãy cấu hình preflight allowlist chính xác, `Access-Control-Allow-Credentials`, cookie SameSite/Secure khi cần và CSP `connect-src` trên **HTML frontend**. Chứng minh origin lạ không được cấp quyền CORS và request thiếu CSRF token bị từ chối dù user đã đăng nhập.

### Bài tập 6 — Security chain và login/logout

Một ứng dụng có `@Order(1)` Bearer API chain `/machine/**` (tắt CSRF theo threat model) và browser fallback chain `csrf.spa()`. Hãy thử `POST /api/orders`, `POST /machine/jobs`, `POST /logout`, `GET /csrf` và `GET /admin/report`. Xác định chain, CSRF và authorization của từng URL. Thêm test tránh trường hợp API chain có matcher `/**` che browser chain.

### Bài tập 7 — Chẩn đoán 403 sau logout/login

Sau logout, SPA lưu `T1` trong memory; user đăng nhập lại, backend dùng `T2`, nhưng frontend vẫn gửi `X-XSRF-TOKEN: T1`. Hãy xây quy trình refresh token đúng thời điểm, phân biệt CSRF 403 với authorization 403 và bảo đảm retry không tạo giao dịch trùng.

## 17. Checklist trước khi dùng `csrf.spa()` trong production

- [ ] Đã xác nhận **Servlet Spring Security 7.0+**; không gọi `spa()` trên `ServerHttpSecurity` Reactive hoặc Security 6.5.
- [ ] Không thay riêng một module Security phá tương thích Spring Boot/Framework/BOM.
- [ ] Browser dùng credential tự động (cookie/session) nên **CSRF vẫn bật**.
- [ ] `csrf(csrf -> csrf.spa())` nằm trong đúng `SecurityFilterChain` xử lý SPA URLs.
- [ ] JavaScript đọc đúng cookie `XSRF-TOKEN` ở hostname/path của trang và gửi `X-XSRF-TOKEN`.
- [ ] Cookie session xác thực vẫn HttpOnly/Secure/SameSite phù hợp; cookie XSRF riêng chỉ mở HttpOnly khi thật sự cần JS đọc.
- [ ] Đã kiểm tra BREACH masking của form/request attribute và raw token của SPA header; không tự tắt toàn bộ BREACH để “sửa 403”.
- [ ] Có cách bootstrap token trước POST và refresh sau authentication success/logout success.
- [ ] Có test thiếu token, sai token, token đúng, token cũ sau login/logout và cookie round-trip thật.
- [ ] Nếu SPA/API khác origin, có mô hình BFF/same-origin hoặc token endpoint/Domain policy đã đánh giá rủi ro.
- [ ] CORS allowlist chính xác, credentials/preflight đúng và origin lạ không được cấp phép.
- [ ] CSP frontend `connect-src`/`script-src`, output escaping và XSS prevention vẫn được thực thi.
- [ ] HSTS và cookie Secure được xác minh trên HTTPS public sau reverse proxy.
- [ ] `/csrf`, `/login`, `/logout` và API URL thuộc đúng chain, có fallback bảo vệ URL còn lại.
- [ ] Servlet và WebFlux dùng đúng repository/handler/test stack; không cố dùng chung một bean token repository.
- [ ] Không log token, session cookie, JWT hoặc lưu cookie jar trong Git/CI artifacts.
- [ ] Kết quả đã được thử bằng MockMvc/WebTestClient **và** browser/HTTP qua ingress/CDN.

## Nguồn tham khảo chính thức

1. [Spring Security 7.0 — What's New](https://docs.spring.io/spring-security/reference/7.0/whats-new.html) — công bố tính năng SPA-based CSRF configuration mới ở 7.0.
2. [Spring Security 7.0 — Servlet CSRF](https://docs.spring.io/spring-security/reference/7.0/servlet/exploits/csrf.html) — `csrf(csrf -> csrf.spa())`, token lifecycle, BREACH, deferred token và hướng dẫn SPA/HTML form.
3. [Spring Security 7.0 API — CsrfConfigurer](https://docs.spring.io/spring-security/site/docs/7.0.x/api/org/springframework/security/config/annotation/web/configurers/CsrfConfigurer.html) — `spa()`, `Since: 7.0` và hành vi cookie repository + request handler.
4. [Spring Security 6.5 — Servlet CSRF](https://docs.spring.io/spring-security/reference/6.5/servlet/exploits/csrf.html) — ví dụ handler SPA thủ công, cách giải quyết raw header, masked form token và eager token loading trước khi có API mới.
5. [Spring Security 7.0 — Reactive CSRF](https://docs.spring.io/spring-security/reference/7.0/reactive/exploits/csrf.html) — `WebSessionServerCsrfTokenRepository`, `CookieServerCsrfTokenRepository`, `CsrfWebFilter` và Reactive request handler.
6. [Spring Security 7.0 API — ServerHttpSecurity.CsrfSpec](https://docs.spring.io/spring-security/site/docs/current/api/org/springframework/security/config/web/server/ServerHttpSecurity.CsrfSpec.html) — API CSRF Reactive và sự khác biệt với `CsrfConfigurer.spa()` Servlet.
7. [Spring Security — Servlet CORS](https://docs.spring.io/spring-security/reference/servlet/integrations/cors.html) và [Reactive CORS](https://docs.spring.io/spring-security/reference/reactive/integrations/cors.html) — preflight, allowed origin, credentials.
8. [Spring Security — Servlet Security Headers](https://docs.spring.io/spring-security/reference/servlet/exploits/headers.html) và [Reactive Security Headers](https://docs.spring.io/spring-security/reference/reactive/exploits/headers.html) — CSP, HSTS, các lớp bảo vệ trình duyệt.
9. [Spring Security — MockMvc CSRF Testing](https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/csrf.html) và [Reactive CSRF Testing](https://docs.spring.io/spring-security/reference/reactive/test/web/csrf.html) — kiểm tra token hợp lệ/sai ở đúng HTTP stack.

**Tự đánh giá:** Tại sao `csrf.spa()` không đồng nghĩa `csrf.disable()`? Vì sao raw cookie token cần request handler riêng khi BREACH masking đang bật? Điều gì xảy ra với token cũ sau login/logout? Một SPA ở `app.example.com` có thể đọc cookie host-only của `api.example.com` chỉ nhờ CORS không? Vì sao WebFlux không thể gọi `ServerHttpSecurity.csrf(csrf -> csrf.spa())`? Và test nào chứng minh SPA thực sự đọc được cookie rồi gửi lại token, thay vì chỉ chứng minh `spring-security-test.with(csrf())` hoạt động?
