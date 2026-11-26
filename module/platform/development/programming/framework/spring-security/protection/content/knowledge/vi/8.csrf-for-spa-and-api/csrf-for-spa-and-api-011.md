# Frontend khác origin và phối hợp credentials với CORS

## Mục tiêu và phạm vi

Trong chương **CSRF cho SPA và API** thuộc module **SPRING_SECURITY_HTTP_PROTECTION**, frontend một trang (SPA) có thể chạy trên **https://app.example.com**, còn backend Spring Security nằm tại **https://api.example.com**. Hai địa chỉ khác **origin**. Khi API xác thực bằng cookie, tích hợp an toàn cần đồng bộ bốn cơ chế độc lập: **Fetch credentials**, **CORS**, **chính sách cookie** và **CSRF token**.

Chỉ sửa CORS có thể khiến frontend thấy response nhưng vẫn bị **401/403** do cookie không được gửi hoặc token CSRF không đúng. Chỉ sửa CSRF có thể khiến server xử lý request nhưng browser vẫn chặn JavaScript đọc response vì thiếu CORS headers. Đặc biệt, **CORS không phải cơ chế thay thế CSRF**.

Bài học bao gồm luồng trình duyệt, preflight OPTIONS, SameSite, Secure, Domain/Path, cookie phiên, endpoint cấp token JSON, cấu hình **Servlet** và **Reactive/WebFlux**, kiểm thử tấn công và chẩn đoán xung đột với CSP, HSTS, security headers và HTTP firewall.

### Kết quả học tập

Sau bài học, bạn có thể:

1. Phân biệt **origin** với **site**, giải thích vì sao hai subdomain có thể khác origin nhưng cùng site.
2. Chọn đúng chế độ **credentials: omit / same-origin / include** trong Fetch.
3. Cấu hình **Access-Control-Allow-Origin** với allowlist cụ thể và **Access-Control-Allow-Credentials**, không nới wildcard.
4. Giải thích vì sao **OPTIONS preflight không dùng session cookie** và cần được xử lý trước authentication.
5. Cấp CSRF token qua **GET /api/csrf JSON** khi frontend không thể đọc cookie host-only của API.
6. Ghép cấu hình CORS/CSRF đúng stack **HttpSecurity** hoặc **ServerHttpSecurity**.
7. Kiểm thử preflight, POST thiếu/sai token, login/logout, session cookie, SameSite và quyền truy cập.
8. Chẩn đoán nguyên nhân 401/403/CORS error mà không tắt lớp bảo vệ.

## 1. Origin, site và cookie scope không giống nhau

**Origin** của URL gồm **scheme + hostname + port**. Thay đổi một thành phần đã là khác origin.

**Site** trong SameSite hiện đại thường xét **scheme và miền đăng ký được** (*schemeful same-site*). Hai subdomain cùng registrable domain có thể cùng site mặc dù khác origin.

| Frontend | API | Cùng origin? | Cùng site trong tình huống thông thường? |
| --- | --- | --- | --- |
| https://app.example.com | https://app.example.com/api | Có | Có |
| https://app.example.com | https://api.example.com | Không | Có |
| https://app.example.com | https://app.example.com:8443 | Không | Có |
| http://app.example.com | https://app.example.com | Không | Không theo schemeful same-site |
| https://app.example.com | https://login.other-domain.test | Không | Không |

**CORS** điều khiển JavaScript **cross-origin** có được đọc response và thực hiện các request cần preflight không. **SameSite** điều khiển cookie theo quan hệ site. **Domain/Path** quy định phạm vi cookie được gửi và được JavaScript nhìn thấy.

### 1.1. Cookie host-only của API không thể đọc từ SPA subdomain khác

API tại api.example.com có thể trả:

~~~http
HTTP/1.1 200 OK
Set-Cookie: JSESSIONID=session-123; Path=/; HttpOnly; Secure; SameSite=Lax
Set-Cookie: XSRF-TOKEN=token-abc; Path=/; Secure; SameSite=Lax
~~~

Không có thuộc tính **Domain** thì đây thường là **host-only cookie** của api.example.com. Trên trang tại app.example.com:

- JavaScript **không đọc được** cookie XSRF host-only của api.example.com qua **document.cookie**, dù cookie XSRF không có HttpOnly.
- JavaScript cũng không đọc được JSESSIONID vì HttpOnly và hostname khác.
- Browser **có thể gửi cookie này** tới api.example.com khi Fetch credentials, cookie scope và browser policy cho phép.
- CORS allowlist **không trao quyền** cho document.cookie của SPA đọc cookie thuộc host khác.

Nếu đặt **Domain=example.com** cho XSRF-TOKEN, cookie có phạm vi rộng hơn và có thể được JavaScript tại nhiều subdomain đọc. Đây không phải giải pháp mặc định vì mở rộng bề mặt **cookie injection**, duplicate cookies và rò rỉ từ subdomain không đáng tin cậy.

### 1.2. Cookie xác thực và CSRF header có vai trò riêng

| Thành phần | Ai gắn vào request? | Ý nghĩa |
| --- | --- | --- |
| JSESSIONID HttpOnly | Browser khi cookie phù hợp | Phiên đã xác thực |
| JWT trong cookie HttpOnly | Browser khi cookie phù hợp | Credential browser-managed |
| XSRF-TOKEN cookie | Browser khi cookie phù hợp | Nơi chứa token CSRF cho phương án cookie |
| X-CSRF-TOKEN / X-XSRF-TOKEN header | Script của ứng dụng chủ động gắn | Actual CSRF token cho server kiểm tra |
| Authorization: Bearer | Client chủ động gắn | Credential do client quản lý |

Backend stateless vẫn có thể chịu CSRF khi JWT nằm trong cookie được trình duyệt tự gửi. Một API thực sự chỉ nhận Bearer header do frontend chủ động gắn, không có cookie/Basic/SSO fallback, thường có threat model khác; vẫn cần xem xét riêng **login, refresh và logout** nếu các endpoint đó dùng cookie.

## 2. Fetch credentials: cho gửi cookie, không cho đọc cookie host khác

Fetch có ba chế độ credentials:

| Giá trị | Cookie same-origin | Cookie cross-origin | Khi thích hợp |
| --- | --- | --- | --- |
| **omit** | Không | Không | Request không dùng browser credential |
| **same-origin** (mặc định phổ biến) | Có nếu cookie hợp lệ | Không | API cùng origin |
| **include** | Có nếu cookie hợp lệ | Có thể, nếu browser policy cho phép | SPA khác origin gọi API cookie-based |

Ví dụ:

~~~javascript
const API = "https://api.example.com";

async function getCurrentUser() {
  const response = await fetch(API + "/api/me", {
    method: "GET",
    credentials: "include",
    cache: "no-store"
  });

  if (!response.ok) throw new Error("API response " + response.status);
  return response.json();
}
~~~

**credentials: include là điều kiện cần, không đủ.** Cookie phải không hết hạn, khớp Secure/Domain/Path/SameSite, phù hợp ngữ cảnh trình duyệt và có thể chịu thêm third-party cookie restrictions.

### 2.1. credentials include không thay đổi document.cookie

~~~javascript
// Browser có thể gửi cookie hợp lệ của api.example.com:
await fetch("https://api.example.com/api/me", {
  credentials: "include"
});

// Nhưng trang app.example.com chỉ thấy cookie có scope của chính nó:
const cookieNamesVisibleHere = document.cookie
  .split("; ")
  .map(value => value.split("=")[0]);
~~~

CORS không khiến JavaScript có thể đọc trực tiếp giá trị **Set-Cookie** trong response header Fetch; đây là header đặc biệt được browser xử lý, không phải dữ liệu mà client script được quyền đọc.

### 2.2. Authorization header là quyết định khác

Nếu frontend tự gắn **Authorization: Bearer**, header đó do code tạo chứ không phải cookie browser tự gửi. Khi gọi cross-origin, header Authorization có thể kích hoạt preflight và phải được khai báo trong allowedHeaders. Không mặc định dùng **credentials: include** nếu API Bearer-only không cần cookie.

Nhưng nếu backend đồng thời nhận cookie JWT hoặc session làm credential dự phòng, không được kết luận rằng “vì frontend dùng Bearer nên toàn bộ API không có CSRF”.

## 3. CORS và Access-Control-Allow-Credentials

**CORS** là chính sách phối hợp giữa browser và server để xác định origin JavaScript nào được phép truy cập response cross-origin. Khi frontend gửi Fetch với credentials include, response cần cho phép **đúng origin** và **credentials**.

~~~http
HTTP/1.1 200 OK
Access-Control-Allow-Origin: https://app.example.com
Access-Control-Allow-Credentials: true
Vary: Origin
Content-Type: application/json

{"id":"u-123","displayName":"Alice"}
~~~

Với request có credentials, **Access-Control-Allow-Origin phải là origin cụ thể**, không dùng ký tự wildcard. Không viết middleware phản chiếu tùy tiện mọi Origin và trả **Access-Control-Allow-Credentials: true**, bởi origin độc hại có thể nhận dữ liệu phiên nếu các điều kiện khác cho phép.

### 3.1. Những header CORS quan trọng

| Header | Vai trò |
| --- | --- |
| Origin (request) | Origin của JavaScript khởi phát |
| Access-Control-Allow-Origin | Origin được phép đọc response |
| Access-Control-Allow-Credentials | Cho phép response của credentialed request được cung cấp cho JS |
| Access-Control-Allow-Methods | Methods được chấp nhận trong preflight |
| Access-Control-Allow-Headers | Custom request headers được chấp nhận trong preflight |
| Access-Control-Max-Age | Cache kết quả preflight trong giới hạn browser |
| Vary: Origin | Giúp cache phân biệt Origin khi cần |
| Access-Control-Expose-Headers | Cho JS đọc thêm response header thông thường; không làm Set-Cookie đọc được |

**CORS là cơ chế browser thực thi**, không phải xác thực ở backend. Curl/Postman có thể gửi request trực tiếp không chịu chính sách CORS như browser; API vẫn phải có authentication, authorization, CSRF verification và validation.

### 3.2. Browser báo CORS error không chứng minh request chưa được xử lý

Với một request “simple” không cần preflight, browser có thể gửi request đến server trước, rồi mới chặn JavaScript đọc response do server thiếu header CORS. **Side effect có thể đã xảy ra**, dù frontend thấy CORS error.

Vì thế, không dùng CORS thay CsrfFilter. CORS hỗ trợ kiểm soát JavaScript cross-origin, trong khi CSRF token kiểm tra tính hợp lệ của request có tác động, kể cả request do HTML form ở trang khác kích hoạt.

## 4. OPTIONS preflight không mang session cookie

Một SPA cross-origin POST JSON với header CSRF tùy biến thường khiến browser tự phát **preflight**:

~~~http
OPTIONS /api/orders HTTP/1.1
Host: api.example.com
Origin: https://app.example.com
Access-Control-Request-Method: POST
Access-Control-Request-Headers: content-type,x-csrf-token
~~~

Preflight thường **không có Cookie: JSESSIONID** và không có token CSRF của POST thực tế. Đây là hành vi bình thường. Server CORS xử lý OPTIONS và có thể phản hồi:

~~~http
HTTP/1.1 200 OK
Access-Control-Allow-Origin: https://app.example.com
Access-Control-Allow-Credentials: true
Access-Control-Allow-Methods: GET,POST,PUT,PATCH,DELETE
Access-Control-Allow-Headers: content-type,x-csrf-token
Access-Control-Max-Age: 900
Vary: Origin
~~~

Nếu chính sách cho phép, browser mới gửi request POST thực với cookie và CSRF header:

~~~http
POST /api/orders HTTP/1.1
Host: api.example.com
Origin: https://app.example.com
Cookie: JSESSIONID=authenticated-session
X-CSRF-TOKEN: token-from-current-session
Content-Type: application/json

{"sku":"P100","quantity":2}
~~~

~~~mermaid
sequenceDiagram
    autonumber
    participant UI as SPA app.example.com
    participant B as Browser
    participant C as CORS trong Spring
    participant SEC as CSRF/Auth
    participant API as Controller
    UI->>B: fetch POST JSON + header CSRF, credentials include
    B->>C: OPTIONS với Origin và Access-Control-Request-*
    C-->>B: Allow origin, credentials, method và header
    B->>SEC: POST thực với Cookie và CSRF header
    SEC->>SEC: Kiểm tra CSRF token, session và quyền
    SEC->>API: Request hợp lệ
    API-->>B: Response và CORS headers
    B-->>UI: Trả response nếu CORS hợp lệ
~~~

Nếu authentication chạy trước CORS, nó có thể coi OPTIONS là request anonymous do không có cookie và trả **401/403/redirect**. Browser báo preflight failure; lúc này việc sửa CSRF repository thường không giải quyết đúng vấn đề.

**CORS processor phải xử lý preflight trước các bước authentication.** Spring Security có tích hợp **CorsFilter** trên Servlet và **CorsWebFilter** trên Reactive. Đừng tắt toàn bộ bảo mật hoặc chỉ permitAll OPTIONS mà bỏ qua cấu hình CORS headers.

## 5. CSRF và CORS phải được kiểm tra độc lập

| Tình huống | CORS | Cookie/session | CSRF | Kết quả điển hình |
| --- | --- | --- | --- | --- |
| SPA đúng origin được cấp quyền nhưng thiếu credentials include | Đúng | Không được gửi | Có thể lệch phiên | 401/403 |
| SPA gửi cookie nhưng thiếu CSRF header | Đúng | Có | Thiếu | CSRF filter chặn |
| SPA gửi token đúng nhưng người dùng thiếu role | Đúng | Có | Đúng | Authorization 403 |
| Origin không nằm allowlist | Không được JS đọc response | Cookie có thể được browser xử lý theo chính sách | Không rõ | CORS error; backend vẫn phải tự bảo vệ |
| Preflight bị authentication chặn | OPTIONS thất bại | Preflight không có cookie | POST chưa được gửi | Browser không gửi POST sau preflight |
| POST thực có CSRF đúng nhưng response thiếu CORS | Lỗi phía JS | Có | Có thể đúng | Server có thể đã xử lý |
| API chỉ dùng Bearer header do client chủ động gửi | Vẫn cần CORS | Có thể không cần cookie | Tùy threat model | Xác thực Bearer và quyền |

### 5.1. HTML form và custom header

HTML form ở website ngoài origin có thể khởi phát POST mà không cần truy cập response. Cookie có được browser gửi hay không còn tùy SameSite và loại request, nhưng **CORS không phải hàng rào để dựa vào cho mọi form POST**.

JavaScript hợp lệ của SPA cần lấy token CSRF theo một giao thức được backend bảo vệ và chủ động gửi nó trong **X-CSRF-TOKEN** hoặc **X-XSRF-TOKEN**. Spring Security xác minh token độc lập với CORS. Header tùy biến thường tạo preflight ở cross-origin, nhưng không phải lý do để bỏ CSRF token.

## 6. Spring Security Servlet: CORS có credentials nhưng vẫn bật CSRF

Ví dụ sử dụng **Spring Boot 3, Spring Security 6.x và Java 17+**. SPA chạy tại **https://app.example.com**, API tại **https://api.example.com**, backend nhận **cookie session** để xác thực. Đầu tiên tạo một chính sách CORS chính xác.

### 6.1. Cấu hình CorsConfigurationSource theo API

~~~java
import java.util.List;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.cors.CorsConfiguration;
import org.springframework.web.cors.UrlBasedCorsConfigurationSource;

@Configuration
class ApiCorsConfiguration {

    @Bean
    UrlBasedCorsConfigurationSource corsConfigurationSource() {
        CorsConfiguration cors = new CorsConfiguration();

        cors.setAllowedOrigins(List.of(
            "https://app.example.com"
        ));
        cors.setAllowedMethods(List.of(
            "GET", "POST", "PUT", "PATCH", "DELETE"
        ));
        cors.setAllowedHeaders(List.of(
            "Content-Type", "X-CSRF-TOKEN", "X-XSRF-TOKEN"
        ));

        cors.setAllowCredentials(true);
        cors.setMaxAge(900L);

        UrlBasedCorsConfigurationSource source =
            new UrlBasedCorsConfigurationSource();
        source.registerCorsConfiguration("/api/**", cors);
        return source;
    }
}
~~~

Đọc kỹ từng lựa chọn:

- **allowedOrigins** sử dụng **origin đầy đủ** gồm scheme/host/port; không chỉ điền example.com vì đó không phải một Origin hợp lệ.
- **allowCredentials(true)** cho browser nhận response của request credentialed khi cookie hợp lệ, **không buộc browser phải gửi cookie**.
- **allowedMethods** là các phương thức API thực cho phép trong preflight. CORS processor biết xử lý OPTIONS; không cần biến toàn bộ API thành endpoint công khai.
- **allowedHeaders** phải có custom CSRF header frontend sử dụng. Nếu API dùng Authorization: Bearer, thêm Authorization khi thực sự cần.
- **maxAge** là cache kết quả preflight, **không phải** cache CSRF token hoặc user response.
- **/api/** là scope ví dụ. Nếu frontend gọi POST login, POST logout hay refresh cookie tại path khác, CORS policy phải bao phủ các path đó theo hợp đồng phù hợp.
- **Không dùng allowedOrigins wildcard với allowCredentials=true**, không tự phản chiếu mọi Origin. Với danh sách subdomain động, allowedOriginPatterns phải được giới hạn cực kỳ cẩn thận và kiểm thử origin không đáng tin.

Nếu một ứng dụng có nhiều **SecurityFilterChain** hoặc nhiều **CorsConfigurationSource** bean, nên chỉ rõ source theo chain; Spring Security không thể luôn tự quyết định source nào đúng. Hạn chế cấu hình chồng nhau giữa Spring MVC, filter tự viết và Spring Security.

### 6.2. SecurityFilterChain xử lý CORS trước authentication

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
class ApiSecurityConfiguration {

    @Bean
    SecurityFilterChain apiSecurity(HttpSecurity http) throws Exception {
        return http
            .cors(Customizer.withDefaults())
            .csrf(Customizer.withDefaults())
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET, "/api/csrf").permitAll()
                .requestMatchers("/api/**").authenticated()
                .anyRequest().permitAll()
            )
            .formLogin(Customizer.withDefaults())
            .logout(Customizer.withDefaults())
            .build();
    }
}
~~~

**Tại sao không dùng csrf.disable()?** CORS giúp browser cross-origin trao đổi thông tin; cookie session vẫn được gửi tự động trong request phù hợp, nên các POST/PATCH/DELETE cần CSRF token theo chính sách. Bật **cors(...)** không làm mất CsrfFilter.

**formLogin ở đây chỉ minh họa một web app dùng session cookie.** Form login mặc định thường dùng POST /login và redirect, không phải JSON login có response 200 được định nghĩa riêng. Với SPA khác origin, nếu login/logout qua Fetch, cần viết và kiểm thử authentication success/failure contract, session cookie, CSRF của POST login/logout và CORS đúng đường dẫn. Không suy ra toàn bộ hệ thống login từ hai bean trên.

**permitAll GET /api/csrf** phục vụ lấy token trước login hoặc sau logout, nhưng không cấp quyền thao tác nghiệp vụ. Trong ứng dụng thực tế, authorization dưới /api/** phải được siết theo vai trò, scope và nghiệp vụ.

### 6.3. Endpoint GET /api/csrf JSON cho frontend khác hostname

Khi API cấp cookie **host-only** thuộc api.example.com, script ở app.example.com không đọc được XSRF cookie ấy. Một cách rõ ràng là giữ **HttpSessionCsrfTokenRepository** mặc định và trả token cho đúng SPA origin trong **JSON response**. GET này được bảo vệ bởi CORS allowlist, trong khi POST vẫn được CsrfFilter xác minh.

~~~java
import jakarta.servlet.http.HttpServletRequest;
import org.springframework.http.CacheControl;
import org.springframework.http.ResponseEntity;
import org.springframework.security.web.csrf.CsrfToken;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
class SessionCsrfController {

    record CsrfResponse(String headerName, String token) {}

    @GetMapping("/api/csrf")
    ResponseEntity<CsrfResponse> csrf(HttpServletRequest request) {
        CsrfToken csrfToken = (CsrfToken) request.getAttribute(
            CsrfToken.class.getName());

        if (csrfToken == null) {
            throw new IllegalStateException("CSRF filter is not configured");
        }

        return ResponseEntity.ok()
            .cacheControl(CacheControl.noStore())
            .body(new CsrfResponse(
                csrfToken.getHeaderName(),
                csrfToken.getToken()
            ));
    }
}
~~~

**Điều kiện để endpoint hoạt động an toàn:**

1. GET token dùng **credentials: include** từ SPA để browser gửi/lưu cookie session phù hợp.
2. **getToken()** hiện thực hóa token đang deferred; nếu cần lưu token vào session anonymous, backend có thể cấp một JSESSIONID trước login.
3. GET response JSON có **Cache-Control: no-store**, không log token và chỉ origin đã allowlist được browser cho đọc.
4. POST sử dụng **cùng cookie session** với GET token, rồi đưa token vào header có tên **headerName** trong response.
5. Spring Security 6 Servlet thường dùng **XorCsrfTokenRequestAttributeHandler** mặc định. Giá trị CSRF token mà endpoint lấy từ request attribute có thể là **XOR-masked token**. Client gửi **nguyên giá trị JSON**; request handler phải giải mã đúng.
6. Không kết hợp một endpoint JSON trả masked token với custom handler luôn coi token trong header là raw, trừ khi thiết kế và test protocol riêng.
7. **Không dùng GET /api/csrf để cấp xác thực.** Token anonymous không cấp quyền truy cập API protected.

Response minh họa:

~~~http
HTTP/1.1 200 OK
Access-Control-Allow-Origin: https://app.example.com
Access-Control-Allow-Credentials: true
Vary: Origin
Cache-Control: no-store
Content-Type: application/json
Set-Cookie: JSESSIONID=anonymous-session; Path=/; HttpOnly; Secure; SameSite=Lax

{"headerName":"X-CSRF-TOKEN","token":"token-presentation"}
~~~

Cookie session được browser lưu, nhưng frontend JS không được đọc trực tiếp giá trị JSESSIONID từ Set-Cookie. Trong môi trường khác, cookie có thể đã tồn tại nên response GET không nhất thiết có Set-Cookie.

### 6.4. Cấu hình cookie phiên cho HTTPS production

~~~properties
server.servlet.session.cookie.http-only=true
server.servlet.session.cookie.secure=true
server.servlet.session.cookie.same-site=lax
~~~

Đây là ví dụ **SPA/API khác origin nhưng cùng site qua HTTPS**. SameSite=Lax thông thường vẫn cho phép cookie ở fetch cross-origin **cùng site** nếu các điều kiện khác phù hợp. Nếu SPA và API nằm ở **hai site khác nhau**, Lax có thể chặn cookie trong request fetch cross-site, dù CORS đã đúng.

Chỉ chọn **SameSite=None; Secure** sau khi đánh giá third-party cookie restrictions, CSRF, SSO và đường triển khai. Có thể cần kiến trúc BFF/cùng site nếu browser không hỗ trợ cookie bên thứ ba như mong muốn.

### 6.5. Nếu muốn dùng CookieCsrfTokenRepository

Có thể dùng **CookieCsrfTokenRepository** và handler phù hợp, nhưng frontend khác hostname thường **không thể đọc raw cookie host-only** của API. Có ba phương án:

- Đưa SPA và API về cùng origin qua **reverse proxy/BFF**, rồi đọc XSRF-TOKEN cookie bằng JavaScript và gửi **X-XSRF-TOKEN** raw.
- Dùng API endpoint cấp token trong **JSON**, với repository và request handler đồng nhất về **raw/masked token**; không bắt buộc cookie CSRF phải JS-readable.
- Cân nhắc Domain cookie chia sẻ subdomain chỉ khi có thể tin cậy toàn bộ phạm vi, đã đánh giá cookie injection và chính sách browser.

Không đặt **HttpOnly=false** cho cookie session để frontend đọc nó. Cookie phiên có nhiệm vụ xác thực và nên giữ HttpOnly, trong khi CSRF token có thể được cấp qua JSON.

## 7. Frontend JavaScript: cùng credentials ở bootstrap và POST

### 7.1. Lấy CSRF token của phiên hiện tại

~~~javascript
const API = "https://api.example.com";

async function fetchCsrf() {
  const response = await fetch(API + "/api/csrf", {
    method: "GET",
    credentials: "include",
    cache: "no-store"
  });

  if (!response.ok) {
    throw new Error("CSRF bootstrap failed: " + response.status);
  }

  const body = await response.json();

  if (typeof body.headerName !== "string" ||
      typeof body.token !== "string" ||
      body.token.length === 0) {
    throw new Error("Unexpected CSRF response");
  }

  return {
    headerName: body.headerName,
    token: body.token
  };
}
~~~

Token GET gắn với **cookie/session browser đã dùng để gọi API**. Nếu GET dùng include nhưng POST bỏ include, server có thể thấy phiên khác. Nếu GET thiếu include và tạo session anonymous khác với session authenticated đã có, token cũng có thể lệch.

### 7.2. Gửi request ghi có CSRF header

~~~javascript
async function updateProfile(profile) {
  const csrf = await fetchCsrf();

  const response = await fetch(API + "/api/profile", {
    method: "PATCH",
    credentials: "include",
    headers: {
      "Content-Type": "application/json",
      [csrf.headerName]: csrf.token
    },
    body: JSON.stringify(profile)
  });

  if (response.status === 401) {
    throw new Error("Login required or session expired");
  }
  if (response.status === 403) {
    throw new Error("Forbidden: check CSRF and authorization");
  }
  if (!response.ok) {
    throw new Error("Update failed: " + response.status);
  }

  return response.status === 204 ? null : response.json();
}
~~~

GET token mỗi lần giúp minh họa contract nhưng có chi phí. SPA thực tế có thể cache token trong memory và **xóa cache khi login/logout hoặc phiên thay đổi**. Không dùng localStorage để lưu bền vững token CSRF chỉ vì thuận tiện.

### 7.3. Chống race condition sau login/logout

Khi SPA mở nhiều component, một GET token trước login có thể hoàn tất **sau** GET token mới. Để không lưu token của phiên cũ, có thể quản lý một số phiên bản trạng thái:

~~~javascript
const csrfState = {
  generation: 0,
  current: null,
  loading: null
};

function invalidateCsrfAfterAuthChange() {
  csrfState.generation += 1;
  csrfState.current = null;
  csrfState.loading = null;
}

async function ensureCsrf() {
  if (csrfState.current) return csrfState.current;
  if (csrfState.loading) return csrfState.loading;

  const expected = csrfState.generation;
  const task = (async () => {
    const token = await fetchCsrf();

    if (expected !== csrfState.generation) {
      throw new Error("Obsolete CSRF response");
    }
    csrfState.current = token;
    return token;
  })();

  csrfState.loading = task;
  try {
    return await task;
  } finally {
    if (csrfState.loading === task) csrfState.loading = null;
  }
}

async function refreshAfterAuthChange() {
  invalidateCsrfAfterAuthChange();
  return ensureCsrf();
}
~~~

Sau **login được backend xác nhận thành công**, gọi refreshAfterAuthChange() với cookie mới. Sau **logout được xác nhận thành công**, cũng refresh nếu SPA vẫn cần gọi public POST/login tiếp theo.

**Không xóa token cũ trước khi gửi POST logout** nếu logout được CSRF bảo vệ. Và không tự tuyên bố login thành công chỉ vì Fetch trả HTTP 200 cuối cùng sau redirect đến trang login; xác minh chính xác auth success/failure contract.

### 7.4. Header chỉ được gửi tới API tin cậy

Không thêm CSRF token vào mọi URL do người dùng nhập, mọi domain analytics hoặc CDN. Dù CSRF token không phải credential đăng nhập, nó vẫn là bí mật bảo vệ luồng thao tác. HTTP service chỉ được gắn header cho API được phép theo URL và phương thức; không đưa token vào query string, analytics hoặc log.

## 8. Cấu hình Spring Security Reactive/WebFlux

WebFlux dùng **ServerHttpSecurity**, **SecurityWebFilterChain** và **CorsConfigurationSource** thuộc package **org.springframework.web.cors.reactive**. Đây là các class khác với Servlet, dù có tên gần giống.

### 8.1. Reactive CorsConfigurationSource

~~~java
import java.util.List;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.cors.CorsConfiguration;
import org.springframework.web.cors.reactive.UrlBasedCorsConfigurationSource;

@Configuration
class ReactiveCorsConfiguration {

    @Bean
    UrlBasedCorsConfigurationSource reactiveCorsSource() {
        CorsConfiguration cors = new CorsConfiguration();

        cors.setAllowedOrigins(List.of(
            "https://app.example.com"
        ));
        cors.setAllowedMethods(List.of(
            "GET", "POST", "PUT", "PATCH", "DELETE"
        ));
        cors.setAllowedHeaders(List.of(
            "Content-Type", "X-CSRF-TOKEN", "X-XSRF-TOKEN"
        ));
        cors.setAllowCredentials(true);
        cors.setMaxAge(900L);

        UrlBasedCorsConfigurationSource source =
            new UrlBasedCorsConfigurationSource();
        source.registerCorsConfiguration("/api/**", cors);
        return source;
    }
}
~~~

**Package reactive trong import rất quan trọng.** Không dùng class UrlBasedCorsConfigurationSource của Spring MVC Servlet trong tham số ServerHttpSecurity CorsSpec.

### 8.2. Cấu hình SecurityWebFilterChain có CORS đúng thứ tự

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.web.server.SecurityWebFilterChain;
import org.springframework.web.cors.reactive.CorsConfigurationSource;

@Bean
SecurityWebFilterChain reactiveApiSecurity(
        ServerHttpSecurity http,
        CorsConfigurationSource reactiveCorsSource) {

    return http
        .cors(cors -> cors.configurationSource(reactiveCorsSource))
        .csrf(Customizer.withDefaults())
        .authorizeExchange(auth -> auth
            .pathMatchers(HttpMethod.GET, "/api/csrf").permitAll()
            .pathMatchers("/api/**").authenticated()
            .anyExchange().permitAll()
        )
        .formLogin(Customizer.withDefaults())
        .build();
}
~~~

Cách cấu hình **cors(...).configurationSource(...)** tích hợp CORS với đúng thứ tự trong Spring Security WebFlux. Phương án khác là đăng ký **CorsWebFilter** có source phù hợp, nhưng tránh nhân đôi CORS filters khi đã dùng DSL tích hợp.

**formLogin** chỉ minh họa authentication dựa trên WebSession. Nếu frontend dùng JSON login khác origin, phải xây dựng login flow Reactive, CORS cho path liên quan và CSRF token đúng; ví dụ này không tự tạo endpoint JSON login.

### 8.3. GET CSRF JSON bằng Mono

~~~java
import java.util.Map;
import org.springframework.http.CacheControl;
import org.springframework.http.ResponseEntity;
import org.springframework.security.web.server.csrf.CsrfToken;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ServerWebExchange;
import reactor.core.publisher.Mono;

@RestController
class ReactiveCsrfController {

    @GetMapping("/api/csrf")
    Mono<ResponseEntity<Map<String, String>>> csrf(
            ServerWebExchange exchange) {

        Mono<CsrfToken> tokenMono =
            exchange.getAttribute(CsrfToken.class.getName());

        if (tokenMono == null) {
            return Mono.error(new IllegalStateException(
                "CSRF filter is not configured"));
        }

        return tokenMono.map(token -> ResponseEntity.ok()
            .cacheControl(CacheControl.noStore())
            .body(Map.of(
                "headerName", token.getHeaderName(),
                "token", token.getToken()
            )));
    }
}
~~~

**Không gọi block() trong Reactive controller.** Mono phải được subscribe trong response pipeline để materialize token. Với WebFlux, token có thể nằm trong **WebSessionServerCsrfTokenRepository** hoặc CookieServerCsrfTokenRepository theo cấu hình, và default XOR request handler có thể làm token trình bày khác raw repository token.

SPA phải gửi **giá trị JSON do chính endpoint cấp** trong header tương ứng với handler đã chọn. Không lấy cookie raw thay masked JSON nếu chưa cấu hình handler cho raw.

## 9. Cookie SameSite, Secure, Domain/Path và third-party policy

CORS không thể vượt qua chính sách cookie của browser. API nhận session cookie cần xem xét từng thuộc tính:

| Thuộc tính | Tác dụng | Khi cấu hình sai |
| --- | --- | --- |
| **Secure** | Chỉ gửi cookie trên kênh an toàn phù hợp | HTTP development không gửi cookie hoặc production thiếu bảo vệ |
| **HttpOnly** | Ngăn JavaScript đọc trực tiếp giá trị cookie | JS không thấy JSESSIONID là điều mong muốn |
| **SameSite** | Giới hạn cookie được gửi trong bối cảnh site | API cross-site không nhận cookie |
| **Domain** | Cookie host-only hay thuộc phạm vi nhiều subdomain | SPA không thấy XSRF API; mở rộng quá mức có thể bị injection |
| **Path** | Phạm vi URL có thể gửi/đọc cookie | Session có ở /api nhưng không có ở /auth |
| **Max-Age/Expires** | Vòng đời cookie | Session hết hạn, CSRF token cũ không còn hợp lệ |

### 9.1. Khác origin nhưng cùng site

Với **https://app.example.com** và **https://api.example.com**:

- **credentials include vẫn bắt buộc** cho fetch cross-origin dùng cookie.
- Cookie **SameSite=Lax** thông thường vẫn có thể được gửi trong request same-site nếu các thuộc tính khác khớp.
- Cookie host-only của api.example.com vẫn có thể gửi tới API, dù trang app.example.com không được đọc cookie qua document.cookie.
- CORS allowlist vẫn cần để frontend JavaScript nhận response.
- CSRF token vẫn cần cho thao tác xác thực bằng cookie; cùng site không bảo đảm mọi subdomain đều đáng tin.

### 9.2. Khác origin và khác site

Với frontend **https://app.example.com** và API **https://api.partner.test**, một fetch cross-site sẽ bị SameSite=Lax hoặc Strict hạn chế trong nhiều trường hợp.

Đối với thiết kế có chủ đích sử dụng cookie cross-site, **SameSite=None; Secure** có thể cần thiết. Nhưng một số browser hoặc thiết lập người dùng có thể **chặn third-party cookies ngay cả khi các thuộc tính này đúng**. Không thể giải quyết giới hạn đó bằng cách sửa Access-Control-Allow-Origin hay tắt CsrfFilter.

Nếu có thể, xem xét **Backend for Frontend (BFF)** hoặc reverse proxy để API browser-facing ở cùng origin/site với frontend. Điều này thường giảm phức tạp cookie, CORS, login redirect và CSRF bootstrap.

### 9.3. Những bẫy thường gặp

**Schemeful same-site:** HTTP và HTTPS có thể bị xem là khác site, dù hostname giống. Ưu tiên HTTPS nhất quán.

**Development localhost:** Cookie Secure trên localhost có thể có hành vi ngoại lệ riêng theo browser. Kiểm thử trên HTTPS local với hostname gần production thay vì bỏ Secure trên production.

**Origin: null:** Có thể đến từ sandboxed iframe hoặc file URL. Không mặc định cho phép Origin null đọc API cookie-authenticated; phải có threat model rõ ràng nếu thực sự cần.

**Cookie trùng tên:** Host-only và Domain cookie cùng tên có thể tạo ambiguity. Không mở Domain cookie chỉ để JavaScript đọc XSRF ở subdomain khác, nhất là khi có subdomain không đáng tin cậy.

## 10. Token CSRF sau login/logout khi SPA khác origin

### 10.1. Chu trình xác thực an toàn

~~~mermaid
sequenceDiagram
    autonumber
    participant SPA as SPA app.example.com
    participant B as Browser cookie jar
    participant SEC as Spring Security API
    SPA->>SEC: GET /api/csrf với credentials include
    SEC-->>B: JSON token A và session cookie nếu cần
    SPA->>SEC: POST login với A, cookie phiên anonymous
    SEC->>SEC: Login thành công, có thể đổi session và xóa A
    SEC-->>B: Login response và cookie phiên mới
    SPA->>SEC: GET /api/csrf với credentials include
    SEC-->>SPA: Token B của session authenticated
    SPA->>SEC: POST /api/orders với B và cookie
    SEC-->>SPA: Kết quả nếu CSRF, auth và quyền hợp lệ
    SPA->>SEC: POST logout với B và cookie hiện hành
    SEC->>SEC: Logout, token B có thể bị xóa
    SEC-->>SPA: Logout response
    SPA->>SEC: GET /api/csrf trong trạng thái anonymous
    SEC-->>SPA: Token C nếu cần
~~~

Token A/B/C là ký hiệu ngữ cảnh, không bảo đảm mọi chuỗi token phải khác nhau. Trong Spring Security Servlet, **CsrfAuthenticationStrategy** và **CsrfLogoutHandler** có thể xóa token cũ. Cơ chế deferred loading nghĩa token mới có thể chỉ xuất hiện khi endpoint GET token được truy cập.

### 10.2. JSON login khác formLogin mặc định

Với formLogin mặc định, browser có thể nhận redirect khi login thành công hoặc thất bại. Fetch tự theo redirect có thể trả HTTP 200 từ trang login cuối cùng. Do vậy:

- **Không chỉ dựa vào response.ok** để kết luận đã đăng nhập.
- Nếu SPA cần JSON login, cấu hình success/failure contract rõ ràng và bảo vệ chính POST login bằng CSRF khi dùng cookie.
- Cho phép CORS trên **đường login/logout/refresh thật**, không chỉ /api/** nếu các endpoint nằm ngoài đó.
- Chỉ sau khi login được backend xác nhận và cookie mới đã được browser xử lý, SPA mới GET CSRF token cho phiên mới.
- **POST logout cần token còn hiệu lực** trước khi xóa state client; sau khi logout thành công mới bootstrap token anonymous khi cần.
- Không tự retry POST/PATCH gây side effect chỉ vì gặp 403; lỗi có thể do thiếu quyền.

### 10.3. Session fixation protection, race và nhiều tab

Spring Security có thể đổi session ID khi login để giảm nguy cơ session fixation. Nếu GET token trước login thuộc session anonymous, POST sau login phải dùng token hợp lệ cho session mới.

Một response GET token cũ có thể đến muộn và ghi đè token mới trong memory SPA. Sử dụng **generation/epoch** ở phần 7 để loại bỏ response thuộc authentication state trước đó.

Cookie có thể được chia sẻ giữa nhiều tab, nhưng biến JavaScript không tự đồng bộ. Có thể phát tín hiệu **auth changed** qua BroadcastChannel và GET token lại khi tab focus. Không cần gửi giá trị token qua kênh chỉ dùng để thông báo. Backend luôn kiểm tra session, CSRF và authorization của từng request.

Sau logout, server có thể cấp một CSRF token mới gắn với session anonymous; sự tồn tại của JSESSIONID mới **không có nghĩa người dùng vẫn đăng nhập**.

## 11. Kiểm thử Servlet với MockMvc

### 11.1. Preflight không cần cookie đăng nhập

Giả sử dùng Spring Boot 3, SecurityFilterChain và CORS source ở phần 6, MockMvc được cấu hình với Spring Security filters:

~~~java
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.options;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

@SpringBootTest
@AutoConfigureMockMvc
class ApiCorsPreflightTests {

    @Autowired MockMvc mvc;

    @Test
    void trustedOriginPreflightWorksWithoutSessionCookie()
            throws Exception {
        mvc.perform(options("/api/orders")
                .header("Origin", "https://app.example.com")
                .header("Access-Control-Request-Method", "POST")
                .header("Access-Control-Request-Headers",
                    "content-type,x-csrf-token"))
            .andExpect(status().isOk())
            .andExpect(header().string(
                "Access-Control-Allow-Origin",
                "https://app.example.com"))
            .andExpect(header().string(
                "Access-Control-Allow-Credentials",
                "true"));
    }

    @Test
    void untrustedOriginIsRejected() throws Exception {
        mvc.perform(options("/api/orders")
                .header("Origin", "https://evil.example.test")
                .header("Access-Control-Request-Method", "POST")
                .header("Access-Control-Request-Headers",
                    "content-type,x-csrf-token"))
            .andExpect(status().isForbidden());
    }
}
~~~

**Không gắn JSESSIONID vào OPTIONS** là chủ đích của test. Cấu hình CORS minh họa thường trả 200 khi được phép và 403 khi không được phép. Với custom filter/entry point, kiểm tra chính xác response header mà browser cần; không chỉ nhìn status.

### 11.2. GET CSRF và POST cùng session

Ví dụ tiếp theo giả định GET /api/csrf như phần 6, API **POST /api/orders** thực sự tồn tại, trả 2xx khi người dùng đã đăng nhập và có quyền, và dùng HttpSessionCsrfTokenRepository.

~~~java
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.user;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import com.jayway.jsonpath.JsonPath;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.mock.web.MockHttpSession;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;

@SpringBootTest
@AutoConfigureMockMvc
class CrossOriginCsrfTests {

    @Autowired MockMvc mvc;

    @Test
    void csrfHeaderWorksForCurrentSession() throws Exception {
        MvcResult boot = mvc.perform(get("/api/csrf")
                .header("Origin", "https://app.example.com"))
            .andExpect(status().isOk())
            .andExpect(header().string(
                "Access-Control-Allow-Origin",
                "https://app.example.com"))
            .andReturn();

        String json = boot.getResponse().getContentAsString();
        String headerName = JsonPath.read(json, "$.headerName");
        String token = JsonPath.read(json, "$.token");
        MockHttpSession session =
            (MockHttpSession) boot.getRequest().getSession(false);

        if (session == null) {
            throw new AssertionError("Session-backed CSRF expected");
        }

        mvc.perform(post("/api/orders")
                .session(session)
                .with(user("alice"))
                .header("Origin", "https://app.example.com")
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"sku\":\"P100\",\"quantity\":1}"))
            .andExpect(status().isForbidden());

        mvc.perform(post("/api/orders")
                .session(session)
                .with(user("alice"))
                .header("Origin", "https://app.example.com")
                .header(headerName, token)
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"sku\":\"P100\",\"quantity\":1}"))
            .andExpect(status().is2xxSuccessful());
    }
}
~~~

**Giới hạn:** MockMvc không mô phỏng đầy đủ SameSite, Fetch credentials hoặc third-party cookie policy. Helper **user("alice")** mô phỏng principal, không kiểm chứng login thật. Controller POST và quyền phù hợp cần tồn tại. Bổ sung assertion **dữ liệu không thay đổi** khi CSRF 403; chỉ status chưa đủ để đánh giá side effect.

Mỗi đường test có mục đích riêng: OPTIONS chứng minh CORS trước authentication; GET/POST cùng session chứng minh token JSON và request handler tương thích. Browser end-to-end test còn cần thiết để kiểm tra cookie thực tế và redirects.

## 12. Kiểm thử Reactive/WebFlux với WebTestClient

### 12.1. CORS preflight trên Reactive

Với WebTestClient đã gắn SecurityWebFilterChain của phần 8, có thể kiểm tra OPTIONS trước khi request thật được gửi:

~~~java
import org.springframework.http.HttpHeaders;

// Đoạn thân test; webTestClient phải được cấu hình từ ứng dụng.
webTestClient.options().uri("/api/orders")
    .header(HttpHeaders.ORIGIN, "https://app.example.com")
    .header(HttpHeaders.ACCESS_CONTROL_REQUEST_METHOD, "POST")
    .header(HttpHeaders.ACCESS_CONTROL_REQUEST_HEADERS,
        "content-type,x-csrf-token")
    .exchange()
    .expectStatus().isOk()
    .expectHeader().valueEquals(
        HttpHeaders.ACCESS_CONTROL_ALLOW_ORIGIN,
        "https://app.example.com")
    .expectHeader().valueEquals(
        HttpHeaders.ACCESS_CONTROL_ALLOW_CREDENTIALS,
        "true");
~~~

Nếu OPTIONS nhận 401 hoặc redirect, kiểm tra package Reactive của CorsConfigurationSource, đường **/api/** và **cors(...).configurationSource(...)** trước khi sửa CSRF. Preflight không cần session cookie.

### 12.2. CsrfWebFilter vẫn phải chặn request thiếu token

~~~java
import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.csrf;
import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.mockUser;

// Đoạn thân test; cần java.util.Map và endpoint thực tế.
webTestClient.mutateWith(mockUser("alice"))
    .post().uri("/api/orders")
    .bodyValue(Map.of("sku", "P100", "quantity", 1))
    .exchange()
    .expectStatus().isForbidden();

webTestClient.mutateWith(mockUser("alice")).mutateWith(csrf())
    .post().uri("/api/orders")
    .bodyValue(Map.of("sku", "P100", "quantity", 1))
    .exchange()
    .expectStatus().is2xxSuccessful();
~~~

Các helper **mockUser()** và **csrf()** chỉ kiểm tra security filter trong ngữ cảnh test. Chúng **không chứng minh trình duyệt đã gửi cookie cross-origin** hoặc JSON token endpoint và request handler thực sự đồng nhất.

Bổ sung integration test dùng một client giữ **WebSession cookie**: GET /api/csrf → POST không token → POST với token JSON → login/logout thật → GET token mới. Kiểm tra cả side effect trong dữ liệu, không chỉ HTTP status.

## 13. Ma trận kiểm thử trình duyệt và acceptance

| Kịch bản | Dấu hiệu cần kiểm tra | Kỳ vọng |
| --- | --- | --- |
| OPTIONS từ app.example.com không Cookie | Network preflight | CORS xử lý, không đòi login |
| OPTIONS từ origin ngoài allowlist | Response CORS | Browser không cho tiếp tục request cần preflight |
| GET token thiếu credentials include | Network Cookie header | Browser không gửi cookie API cross-origin |
| GET token có include và cookie đúng | Network/Storage | API dùng cùng session hiện hành |
| POST chỉ có cookie, thiếu CSRF header | Status và dữ liệu | Bị CSRF từ chối, không có side effect |
| POST token JSON đúng nhưng thiếu role | Authorization | Vẫn bị từ chối |
| POST cookie/session khác với GET token | Cookie jar | 403 hoặc authentication failure |
| Response Allow-Origin wildcard với credentials | Console | Browser từ chối response |
| Response thiếu Allow-Credentials | Console | JS không được đọc credentialed response |
| SPA đọc XSRF host-only cookie API subdomain khác | document.cookie | Không thấy cookie của API |
| SameSite=Lax với fetch cross-site | Cookie header | Có thể thiếu cookie dù CORS đúng |
| SameSite=None; Secure nhưng third-party cookie bị chặn | Browser blocked reason | CORS không sửa được |
| Login đổi session và CSRF token cũ | Network requests | SPA GET token mới trước thao tác ghi |
| Login redirect về HTML | Redirect chain | Không suy auth success từ HTTP 200 cuối |
| CORS error ở response nhưng dữ liệu đã đổi | Database / audit | Phải sửa CSRF, không chỉ CORS |
| Một tab logout, tab khác giữ token cũ | Cookie và cache JS | Tab còn lại refresh authentication state |
| Origin null hoặc origin giả | Allowlist | Không cấp quyền đọc dữ liệu phiên tùy ý |
| XSS ở origin SPA | Security review | CORS/CSRF không thay chống XSS |
| Header CSRF raw và handler mong XOR | Backend error | Chọn request handler đúng contract |

### 13.1. Đánh giá lỗi trên trình duyệt thay vì chỉ dùng curl

Một HTTP client không thực thi CORS hoặc SameSite như browser. Curl trả 200 không chứng minh JavaScript có thể đọc response, cookie được lưu hay preflight thành công. Khi test thật:

1. Kiểm tra **Network → OPTIONS** trước, đặc biệt Origin, Access-Control-Request-Method và Access-Control-Request-Headers.
2. Kiểm tra preflight response có Allow-Origin chính xác, Allow-Methods/Headers cần thiết, Allow-Credentials nếu dùng cookie.
3. Kiểm tra **Network → GET /api/csrf** có credentials mode include, session cookie gửi/lưu, body JSON và Cache-Control no-store.
4. Kiểm tra **Network → POST** có Cookie của API và header CSRF mà frontend chủ động thêm.
5. Kiểm tra status, security exception và **trạng thái nghiệp vụ sau request**.
6. Khi cookie không được gửi, xem DevTools báo lý do cookie bị chặn vì SameSite, Secure, Path, Domain hay third-party policy.
7. Không in token CSRF, session ID hoặc JWT ra log khi điều tra; dùng correlation ID và loại exception.

## 14. Sơ đồ chẩn đoán CORS và CSRF

~~~mermaid
flowchart TD
    A["SPA gọi API và gặp lỗi"] --> B{"Có OPTIONS preflight?"}
    B -->|Có| C{"OPTIONS có allow headers đúng?"}
    C -->|Không| D["Xem CORS allowlist, path và filter order"]
    C -->|Có| E["Xem request thực"]
    B -->|Không| E
    E --> F{"Browser có gửi cookie/API session?"}
    F -->|Không| G["credentials include, SameSite, Secure, Domain, Path, policy"]
    F -->|Có| H{"Request có CSRF header đúng format?"}
    H -->|Không| I["GET token JSON, raw/XOR handler, token cũ"]
    H -->|Có| J{"Auth và quyền hợp lệ?"}
    J -->|Không| K["Kiểm tra login, session, role và security chain"]
    J -->|Có| L{"Response có CORS headers đúng?"}
    L -->|Không| M["Sửa CORS response / gateway / error path"]
    L -->|Có| N["Kiểm tra validation và nghiệp vụ"]
~~~

### “Preflight request does not pass access control check”, HTTP 401

OPTIONS preflight không có JSESSIONID, nhưng authentication hoặc gateway đang kiểm tra nó trước khi CORS processor chạy. Kiểm tra CorsFilter/CorsWebFilter và tích hợp CORS vào Spring Security đúng chain. Không giải quyết bằng csrf.disable().

### “Access-Control-Allow-Origin cannot be wildcard with credentials”

Response trả wildcard Origin trong khi frontend dùng credentials include. Chuyển sang exact origin allowlist, Access-Control-Allow-Credentials true và Vary: Origin khi cần. Không phản chiếu Origin tùy ý.

### “CORS đã đúng nhưng GET /api/me vẫn 401”

Kiểm tra Fetch credentials có include ở chính request không; cookie phiên có thực sự được gửi không; Domain, Path, Secure, SameSite, thời hạn cookie và third-party restrictions. CORS không tự đăng nhập người dùng.

### “GET /api/csrf trả JSON nhưng POST bị 403”

Kiểm tra GET và POST có cùng session cookie không; backend có cùng repository ở hai chain không; headerName và token JSON có được sử dụng nguyên vẹn không; request handler nhận raw hay XOR-masked token; login/logout có làm token cũ hết hiệu lực không. Sau đó phân biệt lỗi CSRF với authorization.

### “API có Set-Cookie XSRF, nhưng JavaScript tại SPA không đọc được”

Nếu cookie host-only của api.example.com và SPA ở app.example.com, đây là giới hạn hostname của document.cookie. CORS không cấp quyền đọc đó. Dùng GET JSON trong allowlist hoặc BFF cùng origin.

### “POST báo CORS error nhưng database đã đổi”

Request thực có thể đã được server xử lý trước khi browser chặn response. Phải kiểm tra **CsrfFilter, authentication, authorization** và những request form/simple không cần preflight. Không dùng CORS để thay kiểm tra CSRF.

### “Login trả 200 nhưng API tiếp theo 401”

Fetch có thể đã theo redirect về trang login. Kiểm tra authentication success/failure thực tế, cookie session được browser xử lý và CORS trên đường login/redirect. Chỉ sau login thành công mới bootstrap CSRF token phiên mới.

### “WebFlux lỗi type CorsConfigurationSource”

Có thể đã import type Servlet thay vì **org.springframework.web.cors.reactive.CorsConfigurationSource** hoặc UrlBasedCorsConfigurationSource Reactive. Xem lại imports, không trộn filter chain Servlet với WebFlux.

### “Dùng SameSite=None vẫn thiếu cookie”

Browser có thể chặn third-party cookies hoặc request không phải HTTPS/Secure. CORS không ép browser gửi cookie. Xem lý do bị chặn và cân nhắc same-site/BFF, không nới origin wildcard.

## 15. Bài tập thực hành

**Bài A — Kiểm tra origin và site:** So sánh app.example.com với api.example.com, cùng host khác port và hai domain độc lập. Ghi rõ khi nào cần CORS, khi nào SameSite có thể chặn cookie.

**Bài B — Reproduce preflight 401:** Cấu hình CORS xử lý sai thứ tự, gửi OPTIONS không cookie từ SPA test. Khôi phục CorsFilter/CorsWebFilter trong Spring Security và chứng minh preflight không cần session.

**Bài C — CORS allowlist:** Tạo origin tin cậy và origin không được phép. Với credentialed fetch, kiểm tra Allow-Origin là exact origin, không wildcard, và origin không được phép không đọc response.

**Bài D — Token JSON:** Dùng HttpSessionCsrfTokenRepository, GET /api/csrf trả JSON và POST ghi. Kiểm thử GET/POST cùng cookie, POST bỏ credentials, thiếu header, sai token, đúng token.

**Bài E — Cookie host-only:** API cấp XSRF cookie host-only, frontend ở subdomain khác. Kiểm tra document.cookie không đọc được cookie API; thay bằng JSON bootstrap qua CORS allowlist.

**Bài F — SameSite:** Thử SPA/API cùng site và khác site, so sánh Lax/Strict/None; quan sát browser blocked reason và đánh giá third-party cookie restrictions.

**Bài G — Auth lifecycle:** Login làm session/cookie đổi, rồi lấy token mới. Logout dùng token trước logout, sau đó kiểm tra anonymous token không cấp quyền API protected.

**Bài H — Reactive:** Dùng ServerHttpSecurity.cors với Reactive CorsConfigurationSource, GET token qua Mono, test preflight và POST bằng WebTestClient.

**Bài I — Simple form request:** Trong môi trường test được phép, thử một form POST cross-site không có CSRF token; xác minh dữ liệu không thay đổi kể cả nếu browser có gửi cookie. So sánh với console CORS error để hiểu khác biệt.

## 16. Nguyên tắc cần ghi nhớ

1. **Khác origin không đồng nghĩa khác site.** CORS hoạt động theo origin, SameSite hoạt động theo ngữ cảnh site, cookie scope theo Domain/Path.
2. **credentials include cần cho cookie-authenticated Fetch cross-origin**, nhưng không vượt cookie policy hoặc quyền đọc document.cookie của host khác.
3. **Preflight OPTIONS không mang session cookie** và phải được xử lý trước authentication bằng CORS integration đúng stack.
4. **Credentialed CORS cần exact origin và Allow-Credentials**, không wildcard hoặc phản chiếu Origin không kiểm soát.
5. **CORS không thay CSRF.** Simple/form request có thể gây side effect ngay cả khi JS không đọc được response.
6. **GET /api/csrf JSON** là cách cấp token rõ ràng cho SPA khác hostname; token từ JSON phải khớp request handler raw/XOR.
7. **Cookie phiên nên HttpOnly, Secure và SameSite phù hợp**; JavaScript không cần đọc JSESSIONID để browser gửi nó.
8. **Servlet dùng CorsConfigurationSource Servlet + HttpSecurity**, WebFlux dùng CorsConfigurationSource Reactive + ServerHttpSecurity.
9. **Login/logout, session timeout và nhiều tab** yêu cầu đồng bộ lại CSRF token theo cookie phiên hiện hành.
10. **Kiểm thử thực trên browser và side effect dữ liệu** song song với MockMvc/WebTestClient để tránh kết luận sai từ status hoặc console.

**Kết luận:** Khi SPA và API khác origin, hãy giữ bốn câu hỏi độc lập: **browser có gửi đúng credential không, CORS có cho frontend nhận response không, CSRF token có hợp lệ theo phiên và handler không, và user có đủ quyền không**. Cấu hình chính xác cả bốn lớp giúp phòng vệ HTTP nhất quán hơn việc chỉ nới CORS cho hết lỗi trình duyệt.

## Tài liệu tham khảo chính thức

- [Spring Security 6.5 — CORS trên Servlet](https://docs.spring.io/spring-security/reference/6.5/servlet/integrations/cors.html)
- [Spring Security 6.5 — CORS trên WebFlux](https://docs.spring.io/spring-security/reference/6.5/reactive/integrations/cors.html)
- [Spring Security 6.5 — CSRF trên Servlet và SPA](https://docs.spring.io/spring-security/reference/6.5/servlet/exploits/csrf.html)
- [Spring Security 6.5 — CSRF trên Reactive/WebFlux](https://docs.spring.io/spring-security/reference/6.5/reactive/exploits/csrf.html)
- [Spring Framework 6.2 — CORS trên WebFlux](https://docs.spring.io/spring-framework/reference/6.2/web/webflux-cors.html)
- [MDN — Request.credentials](https://developer.mozilla.org/en-US/docs/Web/API/Request/credentials)
- [MDN — CORS](https://developer.mozilla.org/en-US/docs/Web/HTTP/Guides/CORS)
- [MDN — Set-Cookie và SameSite](https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/Set-Cookie)



