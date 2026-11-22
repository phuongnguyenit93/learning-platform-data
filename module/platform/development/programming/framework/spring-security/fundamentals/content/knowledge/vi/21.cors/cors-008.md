# Phân biệt CORS với CSRF để chọn biện pháp bảo vệ phù hợp

> **Spring Security fundamentals → CORS.** CORS (*Cross-Origin Resource Sharing*) và CSRF (*Cross-Site Request Forgery*) đều xuất hiện trong ứng dụng browser, nhưng **giải quyết hai bài toán khác nhau**. CORS là chính sách cho phép hoặc hạn chế **JavaScript thuộc origin khác truy cập tài nguyên/đọc response** qua browser. CSRF là bảo vệ để **một trang không đáng tin không thể lợi dụng credential mà browser tự gửi để thực hiện thay đổi trạng thái**. Bài học này giúp xác định **khi nào cần CORS, khi nào cần CSRF, khi nào cần cả hai**, cấu hình Spring Security 6 / Spring Boot 3.x / Java 17+, và kiểm thử tách biệt hai cơ chế.

## 1. Câu hỏi mở đầu: tại sao bật CORS chưa giải quyết CSRF?

Giả sử:

- Frontend chính thức ở `https://app.example.test`.
- API xử lý dữ liệu người dùng ở `https://api.example.test`.
- Browser giữ cookie đăng nhập của API, nên khi gửi request phù hợp, cookie có thể được browser đính kèm theo chính sách.
- Người dùng đôi khi mở trang thuộc `https://evil.example.net`, một origin không đáng tin.

Có hai tình huống độc lập.

**Tình huống A — frontend chính thức muốn đọc dữ liệu từ API:**

```javascript
const response = await fetch("https://api.example.test/api/profile", {
  credentials: "include"
});
const data = await response.json();
```

JavaScript chạy ở `app.example.test` đang gọi API ở `api.example.test`. Đó là **cross-origin fetch**. Browser sẽ yêu cầu API có chính sách CORS cho phép frontend đọc response. Nếu browser không thấy CORS headers phù hợp, script thường không đọc được response, kể cả khi network request đã được gửi.

**Tình huống B — trang không đáng tin cố thay đổi dữ liệu:**

```html
<form action="https://api.example.test/api/email" method="post">
  <input name="newEmail" value="attacker@example.net">
  <button type="submit">Continue</button>
</form>
```

Một HTML form truyền thống có thể **gửi một request cross-origin mà không cần được CORS cấp phép để đọc response**. Nếu cookie đăng nhập được browser tự gửi và API không đòi bằng chứng chống CSRF, thao tác có thể bị thực hiện dù website lạ **không bao giờ đọc được response**. Chính sách CORS chặt chẽ là một lớp bảo vệ hữu ích, nhưng không thay được việc đánh giá **CSRF đối với credential tự gửi**, thiết kế HTTP safe methods và kiểm soát quyền.

**Kết luận ngắn:** CORS hỏi “JavaScript của origin nào được phép dùng/đọc resource này qua trình duyệt?”; CSRF hỏi “request thay đổi trạng thái này có thật sự xuất phát từ luồng được người dùng cho phép, thay vì bị một website khác kích hoạt cùng cookie hay không?”.

## 2. Origin và site: hai khái niệm không đồng nghĩa

### 2.1. Origin là bộ ba scheme, host, port

Một origin được xác định bởi **scheme + host + port**. So sánh:

| URL A | URL B | Cùng origin? | Giải thích |
|---|---|---|---|
| `https://shop.example.test` | `https://shop.example.test/cart` | Có | Scheme, host, port giống nhau |
| `https://shop.example.test` | `https://api.example.test` | Không | Khác hostname |
| `https://shop.example.test` | `http://shop.example.test` | Không | Khác scheme |
| `https://shop.example.test:443` | `https://shop.example.test` | Có trong chuẩn URL khi dùng cổng mặc định | Explicit/default port tương đương |
| `https://shop.example.test` | `https://shop.example.test:8443` | Không | Khác port |
| `http://localhost:3000` | `http://localhost:8080` | Không | Khác port |

Browser sử dụng **Same-Origin Policy** làm nền tảng. CORS là cơ chế **nới quyền đọc response của cross-origin script một cách có kiểm soát**, không phải hệ thống identity của người dùng.

### 2.2. Site không phải origin

Cookie `SameSite` sử dụng khái niệm **site** (trong trình duyệt hiện đại thường xét scheme và registrable domain) chứ không phải origin. Hai subdomain `https://app.example.test` và `https://api.example.test` có thể **cross-origin nhưng same-site**. Vì thế:

- Một yêu cầu có thể **cần CORS** dù vẫn là same-site.
- `SameSite=Lax` hay `Strict` không tự làm các subdomain trở thành cùng origin.
- Cookie policy có thể cho phép gửi cookie theo “site” trong khi CORS vẫn quyết định việc script có đọc response được không.
- Nếu frontend và API thật sự cross-site (khác registrable domain), cookie `SameSite=None; Secure` hoặc thiết kế identity khác có thể cần, nhưng browser còn chính sách third-party cookies; CORS **không ép browser gửi cookie**.

**Đừng kết luận “CORS error = thiếu cookie” hoặc “SameSite đã bật = không cần xem CSRF”.** Hai cơ chế xét các ranh giới khác nhau.

## 3. Bảng so sánh CORS và CSRF

| Thuộc tính | CORS | CSRF |
|---|---|---|
| Tên đầy đủ | Cross-Origin Resource Sharing | Cross-Site Request Forgery |
| Vấn đề chính | Quyền cross-origin JavaScript truy cập/đọc response | Request giả mạo được gửi bằng credential browser tự đính kèm |
| Thực thi chính | Browser kiểm tra `Origin` và CORS response headers; server/framework có thể từ chối Origin | Server kiểm tra CSRF token hoặc biện pháp tương đương trong request unsafe |
| Tín hiệu chính | `Origin`, `Access-Control-Request-Method`, `Access-Control-Request-Headers` | `_csrf` trong form, `X-CSRF-TOKEN`/`X-XSRF-TOKEN` trong header, session/cookie repository |
| Header response thường gặp | `Access-Control-Allow-Origin`, `Access-Control-Allow-Credentials`, `Access-Control-Allow-Methods` | Không có “Access-Control-Allow-CSRF”; token được cấp qua view/API/cookie theo thiết kế |
| Có liên quan GET? | Có, cross-origin GET JSON rất phổ biến | Thông thường không yêu cầu token với GET an toàn |
| Có liên quan POST? | Có; POST cross-origin có thể cần preflight hoặc là simple request | Có; POST thay đổi trạng thái thường cần token với cookie-auth |
| Bật một cơ chế có thay thế cơ chế kia? | Không | Không |
| CORS có xác thực user? | Không | Không |
| CSRF token có cấp quyền đọc object? | Không | Không |
| API machine-to-machine | Thường browser CORS không áp dụng | CSRF browser-cookie thường không áp dụng nếu không có credential tự gửi |
| Lỗi điển hình | Browser báo blocked by CORS; Spring có thể trả 403 cho Origin không được phép | Spring `CsrfFilter` thường trả 403 nếu thiếu/sai token |

**Điểm cần hiểu sâu:** CORS có thể khiến Spring Security/Spring MVC từ chối request có Origin không được phép **ngay trên server**. Nhưng cơ chế bảo vệ được CORS tiêu chuẩn hóa chủ yếu là browser access control; không thể dùng “frontend không đọc được response” để suy ra “side effect không xảy ra”. Một form cross-site có thể được phát đi; hơn nữa, non-browser clients không bị Browser CORS policy trói buộc. Muốn chống request giả mạo trong ứng dụng dùng cookie, phải đặt CSRF policy đúng theo threat model.

## 4. CORS hoạt động như thế nào?

### 4.1. Simple requests: có thể không có preflight

Một số request **thuộc nhóm CORS-safelisted** có thể gửi ngay, ví dụ GET thông thường hoặc một POST với `Content-Type: application/x-www-form-urlencoded` không có custom headers bất thường.

```http
GET /api/profile HTTP/1.1
Host: api.example.test
Origin: https://app.example.test
Cookie: JSESSIONID=<browser-cookie>
```

Nếu API cho phép origin chính thức và có response thích hợp:

```http
HTTP/1.1 200 OK
Access-Control-Allow-Origin: https://app.example.test
Access-Control-Allow-Credentials: true
Vary: Origin
Content-Type: application/json

{"username":"alice"}
```

Browser có thể cho script ở `app.example.test` đọc response khi request/response và credential policy đều hợp lệ. Nếu API trả `Access-Control-Allow-Origin: https://evil.example.net` cho attacker, JavaScript ở origin đó có thể đọc dữ liệu mà browser gửi kèm cookie phù hợp; đó là mức độ tin cậy rất lớn.

**Không phải mọi response đều nhất thiết có đúng từng header trên**; đây là mẫu dùng credentials. Với một tài nguyên public không dùng credential, policy có thể khác. CORS headers không thay authentication/authorization, nên dữ liệu private vẫn cần các tầng bảo vệ thường lệ.

### 4.2. Non-simple requests: browser gửi preflight OPTIONS

Một frontend muốn gửi JSON cùng custom header:

```javascript
fetch("https://api.example.test/api/theme", {
  method: "POST",
  credentials: "include",
  headers: {
    "Content-Type": "application/json",
    "X-CSRF-TOKEN": csrfToken
  },
  body: JSON.stringify({ theme: "dark" })
});
```

Trước khi gửi POST thực tế, browser thường phát request kiểm tra trước:

```http
OPTIONS /api/theme HTTP/1.1
Host: api.example.test
Origin: https://app.example.test
Access-Control-Request-Method: POST
Access-Control-Request-Headers: content-type,x-csrf-token
```

Server phản hồi, nếu policy đồng ý:

```http
HTTP/1.1 200 OK
Access-Control-Allow-Origin: https://app.example.test
Access-Control-Allow-Methods: GET,POST,OPTIONS
Access-Control-Allow-Headers: content-type,x-csrf-token
Access-Control-Allow-Credentials: true
Access-Control-Max-Age: 3600
Vary: Origin
```

Browser mới gửi **actual POST** theo policy. Preflight là request an toàn `OPTIONS` để xin phép **origin, method, headers**, không phải request thay đổi trạng thái và không mang CSRF token của POST. Preflight CORS thường **không gửi cookie đăng nhập**; Spring Security cần tích hợp xử lý CORS đủ sớm để request OPTIONS này không bị coi là một anonymous request cần login.

### 4.3. Request thực tế vẫn cần security checks

Sau preflight thành công, request POST thực tế vẫn đi qua:

```text
Browser -> OPTIONS preflight -> CORS policy cho phép
                      |
                      v
Browser -> POST actual (credential + CSRF header)
                      |
                      v
           CORS kiểm tra Origin
                      |
                      v
           CSRF token validation
                      |
                      v
           Authentication + Authorization
                      |
                      v
           Controller + service + data scope
```

Preflight pass **không có nghĩa POST đã được phép thay đổi dữ liệu**. CORS không xác nhận token CSRF; CSRF không xác nhận user; authentication không chứng minh user có quyền trên bản ghi khác tenant. Mỗi tầng có trách nhiệm riêng.

### 4.4. Vì sao CORS “block” không đảm bảo request chưa tới server?

Một request GET hoặc POST safelisted có thể **được browser gửi trước khi browser biết response có được đọc hay không**. Nếu không thấy CORS headers phù hợp, browser chặn JavaScript **đọc response**, không mặc định rollback side effect đã xảy ra. CORS-enabled server frameworks có thể từ chối actual request sai Origin, nhưng đó là hành vi policy/filter ở server, **không phải lời hứa rằng mọi hệ thống chỉ dùng CORS sẽ chống CSRF đầy đủ**.

Đây là lý do phải thiết kế GET safe, CSRF token trên POST cookie-based và các quy tắc bảo vệ dữ liệu. Một endpoint thanh toán dùng GET là lỗi thiết kế nghiêm trọng dù CORS bị khóa.

## 5. CORS với credentials: không dùng wildcard một cách tùy tiện

### 5.1. Browser credentials và `fetch`

Trong `fetch`:
- `credentials: "same-origin"` (mặc định thông dụng) gửi cookie chỉ với request same-origin.
- `credentials: "include"` cho phép đưa credential theo browser policy vào request cross-origin.
- `credentials: "omit"` không dùng credential.

`include` **không buộc browser vượt qua SameSite, Secure, third-party cookie restrictions, Partitioned cookies hoặc chính sách chặn cookie**. CORS `Access-Control-Allow-Credentials: true` cũng chỉ là một điều kiện để browser cho script đọc credentialed response; nó không cấp cookie hoặc đăng nhập người dùng.

### 5.2. `Access-Control-Allow-Origin: *` và credentials

Đối với credentialed CORS response, **không dùng `Access-Control-Allow-Origin: *`** để mở mọi origin. Browser không chấp nhận wildcard theo kiểu này cùng credentialed request. Trong Spring Framework, `CorsConfiguration#setAllowCredentials(true)` không cho phép đặt `allowedOrigins=["*"]` như một tổ hợp hợp lệ; có `allowedOriginPatterns` cho trường hợp thực sự cần pattern, nhưng pattern quá rộng có thể cấp quyền đọc dữ liệu private cho nhiều domain ngoài ý muốn.

Thiết kế tốt:

```java
config.setAllowedOrigins(
    List.of("https://app.example.test"));
config.setAllowCredentials(true);
```

Chỉ origin frontend đã được kiểm soát mới nhận credentialed CORS response. Không dùng `https://*.example.test` như một allowlist mặc định nếu các subdomain có thể do bên thứ ba quản lý, host user-generated content hoặc bị takeover.

### 5.3. Public response có thể có policy khác

Một CDN chứa font hoặc danh sách public không có cookie/auth có thể dùng:

```http
Access-Control-Allow-Origin: *
```

Điều này **không phù hợp tự động** cho `/api/me`, `/admin`, `/csrf` hay tài nguyên cá nhân. Tách CORS config theo endpoint/chain, tránh đặt chung wildcard cho mọi đường dẫn.

### 5.4. `Origin: null`, regex và phản chiếu Origin

Đừng tin `Origin: null` chỉ vì nó là một string cụ thể; nó có thể xuất hiện trong sandboxed documents, local files và các ngữ cảnh opaque origin. Đừng viết filter kiểu:

```java
// Phản ví dụ: không triển khai trong production.
response.setHeader(
    "Access-Control-Allow-Origin",
    request.getHeader("Origin"));
response.setHeader(
    "Access-Control-Allow-Credentials", "true");
```

Đây là **đoạn Java minh họa nguy hiểm**, không phải cấu hình chạy độc lập. Nó phản chiếu mọi Origin với credential support, có thể cho website không đáng tin đọc nội dung private. Thay bằng allowlist chính xác, giới hạn methods/headers và test deny cases.

## 6. CSRF hoạt động như thế nào?

### 6.1. Synchronizer token pattern

Trong ứng dụng session cookie-based, Spring Security thường sinh một CSRF token kỳ vọng và lưu trong `HttpSession` qua `HttpSessionCsrfTokenRepository`. UI hợp lệ nhận token khi render form hoặc gọi endpoint bootstrap và gửi lại trong một **hidden input** hoặc **custom HTTP header**. Filter so token gửi trong request với expected token từ repository.

```html
<form action="/api/theme" method="post">
  <input type="hidden" name="theme" value="dark">
  <input type="hidden" name="_csrf"
         value="TOKEN_DUOC_SERVER_RENDER">
  <button type="submit">Lưu</button>
</form>
```

Giá trị ví dụ không có tác dụng; Spring Security phải cấp token thật theo phiên. Khi client gửi token, server so khớp:

```http
POST /api/theme HTTP/1.1
Cookie: JSESSIONID=<session-cookie>
Content-Type: application/x-www-form-urlencoded

theme=dark&_csrf=<valid-token-for-this-session>
```

Nếu attacker chỉ dùng HTML form của origin lạ, thông thường họ không thể đọc token hợp lệ từ UI hoặc response cross-origin vì Same-Origin Policy/CORS. Một request có cookie nhưng không có token đúng phải bị từ chối.

### 6.2. Dùng CSRF header cho JavaScript

Frontend tin cậy có thể lấy token từ `GET /csrf` của API trong một môi trường CORS đã được cho phép, rồi gửi:

```http
POST /api/theme HTTP/1.1
Origin: https://app.example.test
Cookie: JSESSIONID=<session-cookie>
Content-Type: application/x-www-form-urlencoded
X-CSRF-TOKEN: <masked-token-from-csrf-endpoint>

theme=dark
```

Với `HttpSessionCsrfTokenRepository` và handler mặc định, tên header thông dụng là `X-CSRF-TOKEN`. Với `CookieCsrfTokenRepository`, header thường là `X-XSRF-TOKEN`; khi JavaScript đọc **raw token** từ cookie, Spring Security 6 có lưu ý riêng về masked token/BREACH, nên phải sử dụng SPA request handler thích hợp. Đừng cho browser đọc CSRF token của người dùng khác bằng CORS wildcard.

### 6.3. Token thay đổi ở ranh giới login/logout

Spring Security có thể xóa CSRF token sau authentication success/logout. Một tab hoặc SPA giữ token cũ có thể bị 403 khi gửi request unsafe tiếp theo; client cần lấy lại token trong phiên hiện hành. Lỗi 403 không nhất thiết nghĩa CORS — kiểm tra request thật, session cookie, token và authority.

### 6.4. CSRF áp dụng cho unsafe HTTP methods

Spring Security Servlet mặc định bật CSRF cho `POST`, `PUT`, `PATCH`, `DELETE` theo matcher chuẩn. GET/HEAD/OPTIONS/TRACE được xem là safe, nhưng **backend phải bảo đảm GET không thực hiện mutation**. CSRF filter không có tác dụng trên request mà đã bị allowlist bỏ qua theo cấu hình; kiểm tra chain và matcher thực tế.

### 6.5. CSRF token không phải authentication token

Một CSRF token hợp lệ không nói người dùng là Alice hay Bob, và không cho phép tự ý đọc tài khoản. Authentication/session nhận diện chủ thể; authorization kiểm tra role/authority/tenant/owner; CSRF chỉ ngăn một kiểu request giả mạo. Các bước phải được phối hợp thay vì dùng một biện pháp để thay cả ba.

## 7. Quy tắc lựa chọn: khi nào cần CORS, CSRF hay cả hai?

| Kiến trúc / tình huống | CORS | CSRF | Tại sao |
|---|---|---|---|
| Monolith server-rendered form, UI và backend cùng origin, session cookie | Thường **không cần** cấu hình cross-origin | **Cần** cho unsafe methods | Browser tự gửi session cookie; UI không cross-origin |
| SPA `app.example.test` gọi cookie API `api.example.test` | **Cần** để JS đọc response | **Cần** cho unsafe requests | Cross-origin + credential tự gửi |
| SPA cùng origin như API, dùng session cookie | Không cần thêm CORS cho cùng origin | **Cần** | Cookie auto-sent và form/fetch unsafe |
| SPA khác origin dùng Bearer trong JS `Authorization`, API không dùng cookie auth | **Cần** nếu cross-origin browser | CSRF truyền thống có thể **không cần** cho bearer-only endpoints | JS chủ động chọn Bearer header; cần đánh giá XSS, storage và refresh cookie |
| API JSON bearer-only gọi từ server tới server | Không liên quan browser | Thường không có cookie-based CSRF | Không có browser Same-Origin Policy hoặc auto cookie |
| Endpoint refresh/logout dùng cookie HttpOnly, dù access token là Bearer | Tùy origin frontend | **Cần đánh giá/bảo vệ** | Cookie refresh được browser tự gửi |
| Public font/asset API không có credential | Có thể dùng wildcard CORS | Không có mutation | Dữ liệu public, browser cần đọc resource |
| Admin session API private, không cho frontend khác origin | Không mở CORS ngoài origin | **Giữ CSRF** | Không mở JS access nhưng vẫn có browser session |
| OAuth2/OIDC redirect/callback | CORS phụ thuộc giao thức/flow, nhiều redirect không phải CORS fetch | Login CSRF, `state`/nonce và callback validation theo chuẩn | Đừng coi allowOrigins thay OAuth2 transaction binding |
| Webhook từ đối tác server-to-server | Không cần CORS | CSRF cookie-based thường không áp dụng | Cần chữ ký webhook, replay prevention, auth phù hợp |

**Cách quyết định nhanh nhất:**

```text
Ứng dụng có Browser JS gọi một origin khác?
    |
    +-- Không  → Không cần CORS chỉ vì có API.
    |
    +-- Có    → Cấu hình CORS chỉ cho trusted origins/methods/headers.

Request có thể thay đổi trạng thái?
    |
    +-- Không (GET safe) → Không cần CSRF theo matcher mặc định,
    |                      nhưng vẫn kiểm tra auth/permission.
    |
    +-- Có
          |
          +-- Browser tự gắn credential? (session/refresh cookie,
          |   Basic auth theo browser, hybrid credential)
          |       |
          |       +-- Có → Áp dụng CSRF token hoặc biện pháp
          |       |        đã threat-model tương đương.
          |       |
          |       +-- Không → Đánh giá CSRF theo kiến trúc
          |                  và bảo vệ Bearer/XSS/replay/authorization.
          |
          +-- Dù có CORS hay không, không bỏ kiểm tra quyền.
```

Thực tế có thể dùng kiểm tra Origin/Sec-Fetch-Site, SameSite cookies và custom header như defense-in-depth. Nhưng **không được âm thầm bỏ synchronizer token** trong một cookie-auth browser app chỉ vì đã cấu hình CORS.

## 8. Mẫu Spring Boot 3.x / Spring Security 6 / Java 17+ chạy được

Ta xây API Servlet với:
- Frontend được tin: `https://app.example.test`.
- API giả định ở `https://api.example.test` (code chạy local ở port 8080; Origin header test mô phỏng môi trường deploy).
- Chỉ cho frontend tin cậy gọi cross-origin các URL `/api/**` và `/csrf`.
- Có cookie-based form login (demo in-memory user).
- `GET /csrf` để frontend lấy CSRF token của phiên.
- `GET /api/theme` cần login, không đổi trạng thái.
- `POST /api/theme` cần **cả login và CSRF token**, dù CORS đã cho phép origin.
- Từ chối origin lạ trong preflight và actual CORS requests.

### 8.1. Dependencies Gradle

Tạo project Spring Initializr, Spring Boot 3.x, Java 17+, với Spring Web và Spring Security. Trong `build.gradle` đã có Boot plugin, repositories và toolchain:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}
```

Đây là **khối dependencies**, không phải toàn bộ Gradle build file. Dùng BOM/version do Boot quản lý; không chọn lẻ version Security không tương thích.

### 8.2. Ứng dụng đầy đủ

Đặt `src/main/java/example/corscsrf/CorsCsrfDemoApplication.java`:

```java
package example.corscsrf;

import java.util.List;
import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.http.CacheControl;
import org.springframework.http.HttpMethod;
import org.springframework.http.ResponseEntity;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.csrf.CsrfToken;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.cors.CorsConfiguration;
import org.springframework.web.cors.UrlBasedCorsConfigurationSource;

@SpringBootApplication
public class CorsCsrfDemoApplication {

    static final String FRONTEND = "https://app.example.test";

    public static void main(String[] args) {
        SpringApplication.run(CorsCsrfDemoApplication.class, args);
    }

    @Bean
    UrlBasedCorsConfigurationSource corsConfigurationSource() {
        CorsConfiguration cors = new CorsConfiguration();
        cors.setAllowedOrigins(List.of(FRONTEND));
        cors.setAllowedMethods(List.of("GET", "POST", "OPTIONS"));
        cors.setAllowedHeaders(List.of(
            "Content-Type", "X-CSRF-TOKEN"));
        cors.setAllowCredentials(true);
        cors.setMaxAge(3600L);

        UrlBasedCorsConfigurationSource source =
            new UrlBasedCorsConfigurationSource();
        source.registerCorsConfiguration("/api/**", cors);
        source.registerCorsConfiguration("/csrf", cors);
        return source;
    }

    @Bean
    SecurityFilterChain security(HttpSecurity http) throws Exception {
        return http
            .cors(Customizer.withDefaults())
            .csrf(Customizer.withDefaults())
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET, "/csrf").permitAll()
                .requestMatchers(HttpMethod.GET, "/public/ping")
                    .permitAll()
                .requestMatchers(HttpMethod.GET, "/api/theme")
                    .authenticated()
                .requestMatchers(HttpMethod.POST, "/api/theme")
                    .authenticated()
                .anyRequest().denyAll())
            .formLogin(form -> form.permitAll())
            .build();
    }

    @Bean
    UserDetailsService users() {
        UserDetails alice = User.withUsername("alice")
            .password("{noop}demo123")
            .roles("USER")
            .build();
        return new InMemoryUserDetailsManager(alice);
    }
}

@RestController
class DemoController {
    private final Map<String, String> themes =
        new ConcurrentHashMap<>();

    @GetMapping("/public/ping")
    String ping() {
        return "ok";
    }

    @GetMapping("/csrf")
    ResponseEntity<Map<String, String>> csrf(CsrfToken token) {
        // Body chỉ được phép đọc từ trusted origin.
        // Cache-Control giúp tránh token bị shared-cache phát nhầm.
        return ResponseEntity.ok()
            .cacheControl(CacheControl.noStore())
            .body(Map.of(
                "headerName", token.getHeaderName(),
                "parameterName", token.getParameterName(),
                "token", token.getToken()));
    }

    @GetMapping("/api/theme")
    Map<String, String> read(Authentication auth) {
        return Map.of(
            "user", auth.getName(),
            "theme", themes.getOrDefault(auth.getName(), "unset"));
    }

    @PostMapping("/api/theme")
    Map<String, String> update(
            @RequestParam String theme, Authentication auth) {
        if (!"dark".equals(theme) && !"light".equals(theme)) {
            throw new org.springframework.web.server.ResponseStatusException(
                org.springframework.http.HttpStatus.BAD_REQUEST,
                "Unsupported theme");
        }
        themes.put(auth.getName(), theme);
        return Map.of("user", auth.getName(), "theme", theme);
    }
}
```

**Các phần quan trọng:**

1. `UrlBasedCorsConfigurationSource` là nguồn cấu hình CORS được Spring Security tích hợp với `http.cors(...)`. Dùng một allowlist origin chính xác, không phản chiếu `Origin` nhận từ browser.
2. `setAllowCredentials(true)` dành riêng cho frontend đáng tin, kết hợp với `setAllowedOrigins(List.of(FRONTEND))`; không thêm `"*"`.
3. `allowedMethods`/`allowedHeaders` chỉ chấp thuận nhu cầu thực, không mở toàn bộ methods/headers chỉ để hết lỗi preflight.
4. CORS chỉ áp dụng ở `/api/**` và `/csrf`; không mở cross-origin data cho mọi controller. `/csrf` ở allowlist chỉ vì frontend tin cậy cần lấy token.
5. `http.cors(Customizer.withDefaults())` tích hợp CORS đủ sớm để preflight OPTIONS không bị chặn như anonymous request.
6. `http.csrf(Customizer.withDefaults())` giữ CSRF protection cho POST trong browser/session flow. Spring Security thường dùng `HttpSessionCsrfTokenRepository` trong Servlet.
7. `GET /csrf` trả request CSRF token theo handler của Spring Security 6; token hiển thị có thể masked. Frontend phải gửi nguyên giá trị vừa nhận qua header do `headerName` chỉ định, với cùng session.
8. `/api/theme` GET và POST yêu cầu authenticated; token CSRF đúng **không** thay login. Nếu user chưa login, response thường redirect tới login theo form-login entry point.
9. `{noop}` chỉ dành cho demo local, **không mã hóa password**; production cần password encoder, TLS, identity provider, session hardening và policy quyền nghiệp vụ.
10. `ConcurrentHashMap` chỉ là in-memory demo, không phải cách lưu dữ liệu đa instance/multi-tenant.

**Chú ý bảo mật:** Mặc dù cấu hình cho frontend khác origin đọc `/csrf`, frontend đó phải là origin đáng tin ngang mức được cấp quyền sử dụng phiên. Nếu frontend bị XSS hoặc origin bị takeover, việc đọc token trở thành nguy cơ; CSRF không bảo vệ khi attacker chạy script ở trusted origin. Đừng expose `/csrf` sang mọi Origin hay qua public CDN.

### 8.3. Luồng frontend cross-origin với session cookie

JavaScript chạy tại `https://app.example.test`, gọi API tại `https://api.example.test`:

```javascript
const api = "https://api.example.test";

async function changeTheme(theme) {
  // Login/session cookie phải tồn tại theo flow của sản phẩm.
  // Lấy CSRF token qua CORS credentialed request.
  const boot = await fetch(api + "/csrf", {
    credentials: "include",
    cache: "no-store"
  });
  if (!boot.ok) {
    throw new Error("Cannot load CSRF token");
  }
  const csrf = await boot.json();

  const result = await fetch(api + "/api/theme", {
    method: "POST",
    credentials: "include",
    headers: {
      "Content-Type": "application/x-www-form-urlencoded",
      [csrf.headerName]: csrf.token
    },
    body: new URLSearchParams({ theme })
  });
  if (!result.ok) {
    throw new Error("POST rejected");
  }
  return result.json();
}
```

**Hai cơ chế cùng làm việc:**

- CORS cho phép browser JavaScript của origin `app.example.test` đọc token và response của origin `api.example.test`.
- CSRF xác minh request POST đi kèm token đúng với session.
- Authentication/authorization quyết định user nào được cập nhật theme.
- `credentials: "include"` không vượt qua cookie restrictions; phải kiểm tra SameSite/Secure/Domain/Path, login flow và third-party cookie restrictions trong deployment thực.

Trong demo local, script trên không chạy y nguyên nếu bạn chưa triển khai API tại `https://api.example.test` với TLS và cookie phù hợp. Để kiểm thử cơ chế CORS ở localhost, integration tests dưới đây gửi `Origin` giả định và xác minh HTTP headers. Không nên giả định test MockMvc mô phỏng toàn bộ chính sách cookie của browser.

## 9. Integration tests: xác minh CORS và CSRF **độc lập**

Đặt `src/test/java/example/corscsrf/CorsCsrfDemoApplicationTest.java`:

```java
package example.corscsrf;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.HttpHeaders;
import org.springframework.mock.web.MockHttpSession;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;

import static org.assertj.core.api.Assertions.assertThat;
import static org.springframework.security.test.web.servlet.request
    .SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.security.test.web.servlet.request
    .SecurityMockMvcRequestPostProcessors.user;
import static org.springframework.test.web.servlet.request
    .MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request
    .MockMvcRequestBuilders.options;
import static org.springframework.test.web.servlet.request
    .MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result
    .MockMvcResultMatchers.*;

@SpringBootTest
@AutoConfigureMockMvc
class CorsCsrfDemoApplicationTest {

    static final String TRUSTED =
        CorsCsrfDemoApplication.FRONTEND;
    static final String UNTRUSTED =
        "https://evil.example.net";

    @Autowired MockMvc mvc;
    @Autowired ObjectMapper mapper;

    @Test
    void preflightWorksBeforeAuthentication() throws Exception {
        // Không kèm session hoặc user: preflight OPTIONS
        // vẫn được xử lý bởi CORS.
        mvc.perform(options("/api/theme")
                .header(HttpHeaders.ORIGIN, TRUSTED)
                .header(HttpHeaders.ACCESS_CONTROL_REQUEST_METHOD, "POST")
                .header(HttpHeaders.ACCESS_CONTROL_REQUEST_HEADERS,
                        "content-type,x-csrf-token"))
            .andExpect(status().isOk())
            .andExpect(header().string(
                HttpHeaders.ACCESS_CONTROL_ALLOW_ORIGIN, TRUSTED))
            .andExpect(header().string(
                HttpHeaders.ACCESS_CONTROL_ALLOW_CREDENTIALS, "true"));
    }

    @Test
    void untrustedPreflightIsRejected() throws Exception {
        mvc.perform(options("/api/theme")
                .header(HttpHeaders.ORIGIN, UNTRUSTED)
                .header(HttpHeaders.ACCESS_CONTROL_REQUEST_METHOD, "POST")
                .header(HttpHeaders.ACCESS_CONTROL_REQUEST_HEADERS,
                        "content-type,x-csrf-token"))
            .andExpect(status().isForbidden());
    }

    @Test
    void allowedOriginDoesNotSkipAuthentication() throws Exception {
        mvc.perform(get("/api/theme")
                .header(HttpHeaders.ORIGIN, TRUSTED))
            .andExpect(status().is3xxRedirection());
    }

    @Test
    void allowedOriginDoesNotSkipCsrf() throws Exception {
        mvc.perform(post("/api/theme")
                .header(HttpHeaders.ORIGIN, TRUSTED)
                .with(user("alice"))
                .param("theme", "dark"))
            .andExpect(status().isForbidden());
    }

    @Test
    void validCsrfHeaderAllowsAuthenticatedPost()
            throws Exception {
        mvc.perform(post("/api/theme")
                .header(HttpHeaders.ORIGIN, TRUSTED)
                .with(user("alice"))
                .with(csrf().asHeader())
                .param("theme", "dark"))
            .andExpect(status().isOk())
            .andExpect(header().string(
                HttpHeaders.ACCESS_CONTROL_ALLOW_ORIGIN, TRUSTED))
            .andExpect(jsonPath("$.theme").value("dark"));
    }

    @Test
    void validCsrfDoesNotOverrideCors() throws Exception {
        mvc.perform(post("/api/theme")
                .header(HttpHeaders.ORIGIN, UNTRUSTED)
                .with(user("alice"))
                .with(csrf().asHeader())
                .param("theme", "dark"))
            .andExpect(status().isForbidden());
    }

    @Test
    void invalidCsrfIsRejectedEvenFromTrustedOrigin()
            throws Exception {
        mvc.perform(post("/api/theme")
                .header(HttpHeaders.ORIGIN, TRUSTED)
                .with(user("alice"))
                .with(csrf().useInvalidToken())
                .param("theme", "dark"))
            .andExpect(status().isForbidden());
    }

    @Test
    void csrfEndpointTokenWorksWithSameSession()
            throws Exception {
        MvcResult bootstrap = mvc.perform(get("/csrf")
                .header(HttpHeaders.ORIGIN, TRUSTED))
            .andExpect(status().isOk())
            .andExpect(header().string(
                HttpHeaders.ACCESS_CONTROL_ALLOW_ORIGIN, TRUSTED))
            .andReturn();

        JsonNode tokenJson = mapper.readTree(
            bootstrap.getResponse().getContentAsString());
        String name = tokenJson.path("headerName").asText();
        String value = tokenJson.path("token").asText();
        assertThat(value).isNotBlank();

        MockHttpSession session = (MockHttpSession)
            bootstrap.getRequest().getSession(false);
        assertThat(session).isNotNull();

        mvc.perform(post("/api/theme")
                .session(session)
                .header(HttpHeaders.ORIGIN, TRUSTED)
                .header(name, value)
                .with(user("alice"))
                .param("theme", "light"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.theme").value("light"));
    }

    @Test
    void readOnlyGetNeedsNoCsrf() throws Exception {
        mvc.perform(get("/api/theme")
                .header(HttpHeaders.ORIGIN, TRUSTED)
                .with(user("alice")))
            .andExpect(status().isOk())
            .andExpect(header().string(
                HttpHeaders.ACCESS_CONTROL_ALLOW_ORIGIN, TRUSTED));
    }
}
```

Chạy test với Gradle Wrapper:

```bash
./gradlew test
```

Trên Windows PowerShell:

```powershell
.\gradlew.bat test
```

**Diễn giải ma trận kiểm thử:**

| Ca | Trạng thái dự kiến | Chứng minh |
|---|---:|---|
| Trusted origin preflight, không login | 200 | CORS xử lý OPTIONS trước authentication |
| Untrusted origin preflight | 403 | CORS deny origin |
| Trusted origin GET nhưng anonymous | Redirect login (3xx) | CORS không cấp identity |
| Trusted origin + authenticated POST thiếu CSRF | 403 | CORS không thay CSRF |
| Trusted origin + authenticated POST đúng CSRF | 200 | CORS và CSRF đều thỏa |
| Untrusted origin + valid CSRF POST | 403 | CSRF không mở khóa CORS |
| Trusted origin + CSRF sai | 403 | Server so token |
| `GET /csrf` rồi POST cùng session | 200 | Token thực từ endpoint dùng được |
| Trusted origin + authenticated GET | 200 | GET safe không cần CSRF |

`with(user("alice"))` mô phỏng authenticated principal trong test, giúp giữ nguyên biến authentication khi test CORS/CSRF. Nó không chứng minh trình duyệt login đúng, session persistence/cookie settings đúng hoặc CORS hoạt động qua proxy thực. `csrf().asHeader()` cũng tạo CSRF token trong test; test `csrfEndpointTokenWorksWithSameSession` bổ sung việc lấy token từ endpoint rồi gửi cùng `MockHttpSession`. Cần end-to-end browser test nếu sản phẩm triển khai cross-origin cookie authentication.

### 9.1. Thêm các negative test có giá trị

Nên kiểm tra thêm:
- `Origin: null` hoặc origin từ iframe sandbox: từ chối nếu không nằm trong allowlist.
- Preflight yêu cầu `DELETE` khi allowlist chỉ GET/POST: từ chối.
- Preflight yêu cầu custom header không được phép: từ chối.
- POST authenticated với token của session khác: từ chối.
- Token bị xóa sau login/logout rồi POST: chỉ nhận token mới.
- Nhiều filter chains có CORS config khác nhau: đúng chain và exact Origin.
- Request Bearer JWT thiếu scope, dù CORS/CSRF qua: 403 tại authorization.
- Browser thật có `credentials: include` nhưng cookie bị SameSite/third-party policy chặn: lỗi login/session độc lập với CORS.
- Trusted origin bị compromise: coi là rủi ro supply-chain/XSS, không tin một header Origin như bằng chứng user intent.

## 10. Khi nào CORS preflight thất bại?

Một số triệu chứng:

| Triệu chứng trên browser | Khả năng cao | Cách kiểm tra |
|---|---|---|
| “No Access-Control-Allow-Origin header” | Server không bật CORS cho endpoint/origin, hoặc response lỗi thiếu headers | Xem preflight/actual response và chain |
| Preflight trả 401/redirect login | CORS chưa xử lý trước authentication | Tích hợp `http.cors` và `CorsConfigurationSource` phù hợp |
| Preflight trả 403 | Origin, method hoặc header không được phép; server security filter từ chối | Kiểm tra Access-Control-Request-Method/Headers, status |
| ACAO là `*` nhưng fetch dùng credentials | Browser không chấp nhận wildcard credentialed CORS | Dùng trusted origin cụ thể + ACAC đúng |
| Response 200 trong Network nhưng script báo CORS | Browser chặn việc đọc vì CORS headers không hợp lệ | Đối chiếu Origin, ACAO, ACAC, redirects và browser console |
| SameSite cookie không được gửi | Cookie/site policy, không phải thiếu ACAO đơn thuần | Xem Cookie và Set-Cookie, Secure, Domain, SameSite |
| Chỉ POST báo CORS, GET hoạt động | POST có JSON/custom header → preflight, hoặc POST trả 403 CSRF | Tách OPTIONS vs actual, kiểm tra CSRF |
| Một route chạy, route khác lỗi | CORS mapping/chain khác nhau | Kiểm tra `/api/**`, `/csrf` và proxy path |
| Request qua proxy lỗi, localhost pass | Proxy strip Origin/headers hoặc cấu hình trusted forwards sai | So sánh request trên edge và backend |

**Đừng sửa bằng cách thêm `@CrossOrigin(origins="*")` ở mọi controller hoặc `cors.disable()`.** Phải hiểu preflight đang bị chặn tại đâu, policy origin nào được cấp và client thật sự cần method/header gì.

## 11. Khi nào CSRF thất bại mà trông giống CORS?

Một request cross-origin đã qua preflight nhưng actual POST nhận 403 có thể khiến browser hiển thị thông báo CORS nếu response lỗi không mang đủ ACAO headers. Thực chất có thể là **CSRF token thiếu/sai hoặc authentication hết hạn**.

Debug theo thứ tự:

1. Browser gửi request preflight OPTIONS chưa? OPTIONS trả status và CORS headers gì?
2. Browser đã gửi actual POST chưa? Nếu chưa, thường là CORS/preflight.
3. Nếu POST được gửi, server log có `MissingCsrfTokenException` hay `InvalidCsrfTokenException`? Log loại lỗi, không log raw token.
4. JS có gửi `X-CSRF-TOKEN`/`X-XSRF-TOKEN` theo repository đang dùng không?
5. Token được lấy trong **cùng session/cookie** và sau login/logout gần nhất không?
6. CSRF token có bị deferred, masked (XOR) hay cookie raw token gây mismatch?
7. Browser có gửi session cookie không? `credentials`, SameSite, Secure và third-party restrictions ra sao?
8. Có trộn filter chain nào `csrf.disable()` và chain khác bật CSRF không?
9. Response 403 do CSRF hay do `hasAuthority`/ownership? Test độc lập với valid CSRF.
10. HTTP endpoint có đang làm mutation trong GET, hoặc client gửi POST JSON mà server tự đặt Content-Type/redirect khác?
11. Edge/proxy có strip Origin, preflight headers, cookie hoặc CSRF header không?
12. Backend có trả CORS headers nhất quán trên error responses trong luồng filter không?

Một cách test tốt là **giữ cùng user và Origin, chỉ đổi CSRF token**, rồi **giữ cùng user và token, chỉ đổi Origin**. Hai ca khác nhau sẽ chứng minh hệ thống áp dụng cả hai chính sách.

## 12. Cookie, SameSite, XSS và bảo vệ nhiều tầng

### 12.1. SameSite là defense-in-depth

`SameSite=Lax` hoặc `Strict` có thể hạn chế gửi cookie trên các cross-site requests, giúp giảm nhiều CSRF vectors. Tuy nhiên:
- Không nên dùng SameSite làm lý do duy nhất để bỏ kiểm tra CSRF khi sản phẩm cần bảo vệ request unsafe.
- Cùng site nhưng khác origin (subdomains) có thể vẫn gửi cookie theo chính sách.
- Một site tin cậy có nhiều subdomain do đối tác kiểm soát cần review rủi ro.
- Nếu cross-site frontend cần cookie, `SameSite=None; Secure` có thể cần, nhưng tạo yêu cầu bảo mật và tương thích trình duyệt cao hơn.
- CORS không khống chế SameSite; hai thứ được browser đánh giá độc lập.

### 12.2. XSS có thể vượt qua CSRF token

Nếu attacker chạy JavaScript trong trusted origin do XSS hoặc dependency bị nhiễm, script có thể đọc token từ DOM hoặc gọi endpoint `/csrf` nếu chính origin đó được phép. Vì thế CSRF token không thay **output encoding, CSP, dependency scanning, Content Security Policy, cookie HttpOnly** và authorization.

### 12.3. CSRF token exposure là một quyết định trust

Frontend khác origin được CORS cho đọc `/csrf` gần như được cấp khả năng thực hiện các request có token tương ứng nếu browser cũng gửi session cookie. Chỉ cho phép origin do bạn quản trị và có bảo mật tương xứng. Không cache response CSRF token trên public CDN hoặc đưa raw token ra logs.

### 12.4. Custom headers và CORS preflight

Header `X-CSRF-TOKEN` do JS thêm làm request có thể yêu cầu preflight. Điều đó tăng ma sát với website không được tin, nhưng **CSRF protection không chỉ là “có preflight”**: server phải validate token và trạng thái session. Nếu cấu hình CORS vô tình cho attacker-origin đọc token hoặc chấp nhận credentials, preflight không giúp ngăn attacker thuộc origin được phép.

## 13. Nhiều security chains và WebFlux

### 13.1. Servlet có nhiều `SecurityFilterChain`

Một ứng dụng có thể có:
- Chain web form-login ở `/web/**`, dùng cookie/session và CSRF.
- Chain API bearer-only ở `/api/**`, stateless và được cấu hình CORS cho trusted SPA.
- Chain fallback từ chối các đường còn lại.

Khi dùng nhiều chains, kiểm tra `securityMatcher`/`@Order` để biết request nào được chain nào xử lý. `anyRequest().denyAll()` trong một chain chỉ áp dụng các requests mà chain ấy nhận; CORS config và CSRF matcher cũng cần được định nghĩa cho đúng chain.

Đặc biệt, một preflight `OPTIONS /api/orders` cần khớp chain phù hợp và được CORS xử lý trước auth; đừng khai báo matchers chỉ GET/POST mà vô tình khiến OPTIONS rơi ra ngoài security chain hoặc bị chặn trước CORS.

Nếu có nhiều `CorsConfigurationSource`, Spring Security không nhất thiết tự chọn source nào; có thể truyền source cụ thể trong `http.cors(cors -> cors.configurationSource(source))` cho mỗi chain. Đừng tạo nhiều CorsFilter thừa hoặc cấu hình CORS trùng lặp ở proxy, servlet filter và MVC annotation mà không biết rule nào thắng.

### 13.2. WebFlux dùng các API khác

Spring WebFlux dùng `ServerHttpSecurity`, `SecurityWebFilterChain` và thường tích hợp `CorsWebFilter`/reactive CORS configuration, không dùng nguyên Servlet `HttpSecurity`, `HttpSession`, `CorsFilter` hoặc `CsrfFilter`. CSRF reactive dùng `ServerCsrfTokenRepository` và các thành phần reactive tương ứng.

**Nhưng quyết định kiến trúc không đổi:** cross-origin browser JS cần policy CORS; browser tự gửi cookie trên mutation cần chống CSRF theo threat model; cả hai không thay authentication/authorization. Với WebFlux, kiểm thử bằng WebTestClient và browser E2E đúng stack, không lẫn code Servlet vào reactive service.

### 13.3. Reverse proxy và gateway

Nếu TLS kết thúc ở gateway hoặc URL bên ngoài khác context path của Spring Boot, cần kiểm tra:
- Trusted proxy xử lý `Host` và `X-Forwarded-*` đúng; không tin headers giả từ Internet.
- Gateway có strip/add `Origin`, `Access-Control-Request-*`, `Access-Control-Allow-*` không.
- Có quá nhiều lớp cùng trả ACAO dẫn đến duplicate headers hoặc conflict.
- Redirect login tới HTTPS API domain đúng, không mất cookie.
- CORS allowlist dùng **origin hiển thị cho browser**, không phải hostname nội bộ giữa services.
- CORS trên `/csrf` đủ để frontend tin cậy lấy token, nhưng không cho attacker-origin đọc.
- Error responses của 401/403 đi qua CORS integration nhất quán để browser phân biệt lỗi.

## 14. Anti-patterns và cách sửa

| Anti-pattern | Hậu quả | Thay thế |
|---|---|---|
| Bật CORS rồi `csrf.disable()` cho app session cookie | Mở CSRF khi browser tự gửi cookie | Giữ CSRF token trên unsafe requests |
| “CORS bị chặn, POST chắc chắn chưa xảy ra” | Safelisted requests có thể đã gửi | Đừng rely vào unreadable response; kiểm soát mutation |
| `Access-Control-Allow-Origin: *` + credential | Browser từ chối; hoặc server config không hợp lệ | Exact trusted origins + ACAC chỉ khi cần |
| Phản chiếu `Origin` lên ACAO | Cho untrusted frontend đọc private responses | Allowlist origin cố định |
| `@CrossOrigin("*")` trên mọi endpoint | Mở rộng bề mặt đọc dữ liệu | Mapping hẹp theo API use case |
| Cho mọi headers/methods chỉ để preflight hết lỗi | Cấp nhiều capability hơn cần thiết | Liệt kê methods/headers thật |
| Bật `withHttpOnlyFalse()` cho session cookie | Tăng rủi ro JS đọc credential | Nếu cần, chỉ cookie CSRF đọc được |
| Dùng SameSite như thay thế hoàn toàn token | Bỏ sót flow và policy | Kết hợp defense-in-depth và CSRF |
| Lấy token CSRF từ query URL | Lộ qua history/log | Header hoặc hidden form |
| Chỉ kiểm tra `hasRole` mà bỏ tenant/owner | IDOR/BOLA | Service/data-layer authorization |
| Đổi mọi POST thành GET để tránh 403 | Mutation dễ bị kích hoạt | Dùng unsafe HTTP method + CSRF |
| Coi JSON parse không được là lỗi CORS | Có thể 401/403/HTML login redirect | Kiểm tra network method/status/content-type |
| Tắt CORS trong Security để “disable bảo vệ browser” | Cross-origin browser không hoạt động, không thay SOP | Config CORS đúng mục tiêu |
| Dùng CSRF token để xác thực bearer-only API | Sai vai trò token | Auth bằng Bearer, authorization theo quyền |
| Copy code WebFlux sang Servlet | Sai class/filter semantics | Dùng đúng web stack |
| Chỉ test happy-path 200 | Không phát hiện Origin/token mở sai | Negative tests cho cả hai |
| Đưa CSRF response cho mọi origin | Trusted boundary bị phá | Chỉ cho approved frontend, no-store |
| Không test browser credential flags | MockMvc pass, production browser lỗi | E2E với HTTPS/cookie/proxy |

## 15. Checklist review và kiểm thử

### CORS

- [ ] Xác định **origin** thực tế của frontend và API (scheme, hostname, port).
- [ ] Đã kiểm tra nhu cầu cross-origin thật; app cùng origin không cần mở thêm CORS.
- [ ] `allowedOrigins` là danh sách cụ thể; không phản chiếu `Origin` chưa tin.
- [ ] `allowCredentials=true` chỉ khi cần cookie/credentials từ trusted frontend.
- [ ] Methods/headers/path mappings được giới hạn; không mở mọi endpoint.
- [ ] Preflight OPTIONS không cần login cookie và được xử lý trước authorization.
- [ ] Response được phép có ACAO đúng origin và ACAC khi credentials.
- [ ] Untrusted origin/`Origin: null`/method/header không được phép bị từ chối.
- [ ] CORS headers trên error responses được kiểm tra; gateway/proxy không tạo xung đột.
- [ ] Browser `credentials`, SameSite/Secure/Domain/Path policy đã được test thật.

### CSRF

- [ ] Credential có được browser tự gửi trên unsafe request hay không?
- [ ] Form POST có hidden `_csrf` từ server theo session hiện hành.
- [ ] Fetch/AJAX có header `X-CSRF-TOKEN` hoặc `X-XSRF-TOKEN` theo repository/handler.
- [ ] `CsrfFilter` vẫn bật cho cookie-auth chain; không disable chỉ để hết lỗi.
- [ ] Token được lấy lại sau login/logout khi framework xóa token cũ.
- [ ] SPA cookie-based phân biệt raw token với XOR-masked token theo Spring Security version.
- [ ] `GET /csrf` chỉ lộ cho same-origin/trusted origins và không bị shared-cache.
- [ ] POST thiếu/sai token của user đã xác thực bị chặn trước mutation.
- [ ] Có kiểm thử token của session khác và session timeout.
- [ ] GET/HEAD không có side effect; state-changing methods đúng semantics.
- [ ] Authentication và authorization (role/owner/tenant/ACL) vẫn được enforce.

### QA tích hợp

- [ ] Negative tests tách CORS deny, CSRF deny và authorization deny bằng cách giữ các yếu tố khác cố định.
- [ ] Kiểm thử preflight không có cookies, actual request có cookies nếu browser cho phép.
- [ ] Khi gặp 403, xác định filter/handler nào phát sinh; không chỉ nhìn status.
- [ ] Có E2E test browser sau reverse proxy và HTTPS với frontend thật.
- [ ] Không log session IDs, CSRF tokens, authorization headers, private response bodies.
- [ ] Đã review sự khác nhau giữa OAuth2 login, bearer access token, refresh cookie và stateless API.
- [ ] Đã xem lại CORS/CSRF khi nâng phiên bản Spring Security hoặc đổi frontend domain.

## 16. Bài tập suy luận

**Câu 1.** Một React SPA chạy ở `https://app.example.test` gọi API ở `https://api.example.test` bằng session cookie. Cần gì?

**Đáp án:** CORS allowlist cho origin frontend để JS có thể đọc response, và CSRF token trên unsafe methods vì browser tự gửi cookie. Sau đó vẫn phải kiểm tra authentication và quyền trên từng tài nguyên.

**Câu 2.** Một POST cross-site không đọc được response do CORS, nghĩa là backend chắc chắn không thay đổi dữ liệu?

**Đáp án:** Không. Safelisted request có thể được gửi trước, browser chỉ chặn script đọc response. Server-side CORS filter có thể từ chối Origin, nhưng không được coi đó là lời bảo đảm toàn diện thay CSRF trong mọi môi trường.

**Câu 3.** Preflight OPTIONS tới private API không có `JSESSIONID`. Nó nên được 401 vì chưa đăng nhập?

**Đáp án:** Không, nếu Origin/method/headers hợp lệ, CORS cần xử lý preflight mà không cần cookie đăng nhập. Actual POST sau đó mới đi qua authentication/authorization/CSRF.

**Câu 4.** `Access-Control-Allow-Origin: *` và `Access-Control-Allow-Credentials: true` dùng được cho cookie API?

**Đáp án:** Không phải cấu hình credentialed CORS hợp lệ cho browser; chọn origin tin cậy cụ thể, ACAC khi cần, và cookie policy phù hợp.

**Câu 5.** Token CSRF hợp lệ có cho phép user Alice sửa đơn hàng của Bob?

**Đáp án:** Không. CSRF chứng minh một yêu cầu không bị giả mạo theo pattern của hệ thống, không quyết định quyền nghiệp vụ. Phải kiểm tra owner/tenant/ACL ở service/repository.

**Câu 6.** API machine-to-machine chỉ dùng Bearer token trong Authorization header, không có browser. Phải bật CORS?

**Đáp án:** Không. CORS là cơ chế browser. API vẫn cần HTTPS, signature/issuer/audience/scope validation, rate limits và authorization.

**Câu 7.** Frontend `app.example.test` được allowlist CORS nhưng POST vẫn 403. Sai ở đâu?

**Đáp án:** Có thể do thiếu CSRF token, session cookie không được gửi, token cũ sau login, role/permission thiếu hoặc sai CORS method/header. Xem OPTIONS rồi actual POST, server log an toàn và dùng negative tests tách nguyên nhân.

**Câu 8.** Dùng CORS để hạn chế ai có thể gọi API bằng curl có đủ không?

**Đáp án:** Không. Non-browser HTTP client có thể gửi request mà không bị chính sách browser Same-Origin Policy điều khiển. Cần authentication, authorization, validation và các security controls server-side phù hợp.

## 17. Tài liệu chính thức

- [Spring Security 6.5 — CORS (Servlet)](https://docs.spring.io/spring-security/reference/6.5/servlet/integrations/cors.html): CORS preflight trước authentication, `UrlBasedCorsConfigurationSource`, nhiều chains.
- [Spring Security 6.5 — CSRF (Servlet)](https://docs.spring.io/spring-security/reference/6.5/servlet/exploits/csrf.html): request CSRF filters, `CsrfTokenRepository`, token cho form/JS, BREACH và SPA.
- [Spring Framework — Spring MVC CORS](https://docs.spring.io/spring-framework/reference/web/webmvc-cors.html): `CorsConfiguration`, `allowedOrigins`, `allowCredentials`, preflight/actual requests.
- [Spring Security — MockMvc CSRF Testing](https://docs.spring.io/spring-security/reference/6.5/servlet/test/mockmvc/csrf.html): `csrf()`, `csrf().asHeader()`, invalid-token tests.
- [Spring Security — WebFlux CORS](https://docs.spring.io/spring-security/reference/reactive/integrations/cors.html): CORS theo reactive stack và `CorsWebFilter`.
- [Spring Security — WebFlux CSRF](https://docs.spring.io/spring-security/reference/reactive/exploits/csrf.html): reactive CSRF repository và filter tương ứng.
- [OWASP — Cross-Site Request Forgery Prevention Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Cross-Site_Request_Forgery_Prevention_Cheat_Sheet.html): CSRF threat model, synchronizer tokens, SameSite và defense-in-depth.
- [MDN — Cross-Origin Resource Sharing (CORS)](https://developer.mozilla.org/en-US/docs/Web/HTTP/Guides/CORS): browser requests, preflight, safelisted requests và CORS response headers.

**Kết luận:** Không chọn CORS *hoặc* CSRF theo kiểu một-mất-một-còn. Nếu **JavaScript truy cập API khác origin**, cấu hình CORS chính xác cho frontend được tin. Nếu **browser tự gửi cookie/credential tới endpoint thay đổi trạng thái**, áp dụng CSRF protection đúng flow. Với ứng dụng vừa cross-origin vừa session-based, **cần cả hai**, và vẫn phải giữ authentication, authorization và an toàn dữ liệu.
