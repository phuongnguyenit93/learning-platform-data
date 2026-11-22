# CSRF khi trình duyệt tự gửi cookie hoặc thông tin xác thực

## 1. Vấn đề: một request hợp lệ về HTTP nhưng không do người dùng chủ động yêu cầu

Nhân viên đã đăng nhập **https://shop.example.com** bằng session cookie. Một trang lạ khiến browser gửi **POST /api/orders/123/cancel** kèm cookie. Nếu server chỉ kiểm session mà không xác minh ý định/nguồn, đơn có thể bị hủy dưới danh tính nhân viên.

**CSRF** là việc một bên không tin cậy khiến **browser nạn nhân** gửi yêu cầu có **credential tự đính kèm**. Attacker thường **không cần đọc response** để gây tác dụng phụ.

Bài thuộc **API trên trình duyệt**, module **INTEGRATION_API_REST**; kết nối resource/URI, HTTP methods/status, cache, idempotency, OpenAPI, authentication, authorization, lỗi và Java/Spring. Trọng tâm là **unsafe requests với cookie/session**.

**Mục tiêu:** nhận diện CSRF, phân biệt CORS/XSS, cấu hình **Spring Security CSRF**, gửi token bằng Fetch và kiểm thử 403.

## 2. Threat model: credential nào được trình duyệt tự gửi?

Không phải mọi API dùng authentication đều có cùng rủi ro CSRF. Câu hỏi cốt lõi là: **một trang khác có thể khiến browser gửi một request kèm credential hợp lệ mà không biết credential đó không?**

| Cơ chế | Credential có thể tự đi theo request? | Đánh giá CSRF |
| --- | --- | --- |
| **Session/remember-me cookie** | Có, theo Domain/Path/Secure/SameSite và chính sách browser. | **Có rủi ro** với thao tác thay đổi trạng thái, cần CSRF defense. |
| **JWT/access token nằm trong cookie** | Có; định dạng JWT không thay cách cookie được gửi. | **Có rủi ro** tương tự session cookie. |
| **HTTP Basic/Digest đã được browser ghi nhớ** | Browser có thể tự dùng credential cho protection space phù hợp. | **Có rủi ro** nếu endpoint browser truy cập được. |
| **TLS client certificate (mTLS)** | Browser có thể gửi chứng chỉ đã chọn trong phiên TLS. | **Không mặc định miễn CSRF**. |
| **Bearer token trong Authorization header do JS chủ động đặt** | Trang lạ không tự có token hoặc quyền đặt header tùy ý tới API. | Ít có rủi ro CSRF điển hình hơn, nhưng phải xét XSS, CORS, token leakage. |
| **API key do client backend tự gắn** | Không phải ambient browser credential. | CSRF thường không phải cơ chế tấn công chính; vẫn phải xác thực/phân quyền. |

**CSRF thành công** khi browser gửi request có ambient credential đến thao tác tạo side effect mà server không kiểm nguồn/ý định. **CORS chặn đọc response không đồng nghĩa request chưa chạy**.

### 2.1. CSRF không phải XSS hoặc CORS

- **CSRF** lợi dụng credential sẵn có để tạo request không chủ ý; không nhất thiết cần chạy JavaScript trong origin mục tiêu.
- **XSS** là thực thi script trong origin tin cậy. Nếu XSS có thể chạy code với quyền người dùng, nó thường có khả năng lấy hoặc sử dụng CSRF token, nên **CSRF token không chữa XSS**.
- **CORS** là cơ chế browser quản lý **quyền đọc response của cross-origin script và một số request cần preflight**. CORS không chặn mọi HTML form, navigation hoặc request đã được xử lý ở server.
- **Authorization theo object/tenant** vẫn cần thiết: CSRF token hợp lệ không cho phép user xem/sửa order không thuộc quyền.

## 3. Origin, site và điều kiện cookie được gửi

**Origin** = scheme + host + port. **Site** trong SameSite hiện đại thường là scheme + registrable domain (public suffix + 1):

| Cặp địa chỉ | Quan hệ |
| --- | --- |
| **https://app.example.com** và **https://api.example.com** | **Cross-origin** nhưng thường **same-site**. |
| **https://shop.example.com** và **https://evil.example.net** | Cross-origin và cross-site. |
| **http://shop.example.com** và **https://shop.example.com** | Khác scheme, **cross-site** theo schemeful SameSite. |
| **https://shop.example.com:443** và **https://shop.example.com:8443** | Cross-origin, nhưng same-site. |

Một subdomain bị chiếm quyền có thể vẫn **same-site**; **SameSite không thay Origin check/CSRF token**.

Cookie chỉ được browser gửi khi khớp phạm vi và chính sách:

- **Domain**: cookie host-only không tự mở rộng cho toàn bộ subdomain; Domain rộng tăng bề mặt tin cậy.
- **Path**: giới hạn nơi cookie được gửi, nhưng **không phải ranh giới bảo mật mạnh** giữa ứng dụng cùng host.
- **Secure**: chỉ gửi qua kết nối bảo mật phù hợp, cần HTTPS.
- **HttpOnly**: script không đọc trực tiếp giá trị cookie; **không ngăn browser gửi cookie**, nên không chống CSRF.
- **SameSite**: quyết định việc đính kèm cookie trong một số ngữ cảnh cross-site. Đây là phòng vệ quan trọng nhưng còn phụ thuộc chế độ navigation, browser và chính sách third-party cookies.

### 3.1. Bảng SameSite cần nhớ

| Thuộc tính session cookie | Hành vi chính | Giới hạn |
| --- | --- | --- |
| **SameSite=Strict** | Hạn chế mạnh gửi cookie từ ngữ cảnh cross-site. | Có thể ảnh hưởng các luồng điều hướng từ trang khác; same-site subdomain vẫn là vấn đề. |
| **SameSite=Lax** | Thường không gửi ở cross-site subresource/POST; vẫn có thể gửi trong **top-level navigation dùng phương thức an toàn** như GET. | **GET phải không có tác dụng phụ**; một số browser có ngoại lệ cho cookie mới tạo trong chế độ mặc định Lax. |
| **SameSite=None; Secure** | Cho phép các ngữ cảnh cross-site khi browser/chính sách third-party cookies cho phép. | **Không phải cơ chế chống CSRF**; cần token/Origin và CORS phù hợp. |
| **Không khai báo SameSite** | Nhiều browser hiện đại áp default kiểu Lax. | Không dựa vào mặc định; cần cấu hình và kiểm thử browser hỗ trợ. |

Chính sách cookie khác nhau theo browser/phiên bản; đừng dựa chỉ vào một bài test browser.

## 4. Một kịch bản HTTP minh họa CSRF

Ứng dụng sai thiết kế cho phép form POST đổi trạng thái order, chỉ kiểm session:

~~~http
POST /api/orders/123/cancel HTTP/1.1
Host: shop.example.com
Cookie: SESSION=<session-id>
Content-Type: application/x-www-form-urlencoded
Origin: https://untrusted.example.net

reason=changed-my-mind
~~~

Một trang cross-site có thể tạo HTML form như sau (ví dụ mô phỏng trên môi trường học tập, không sử dụng với hệ thống bên ngoài):

~~~html
<form action="https://shop.example.com/api/orders/123/cancel"
      method="post">
  <input type="hidden" name="reason" value="changed-my-mind">
  <button type="submit">Send request</button>
</form>
~~~

HTML form gửi **urlencoded, multipart hoặc text/plain** mà không cần quyền đọc CORS; nếu cookie được gửi và server chỉ kiểm session, thao tác có thể thành công.

**CORS không chặn form POST**. **SameSite=Lax** thường chặn cookie cross-site POST nhưng còn cookie khác, same-site subdomain và ngoại lệ browser.

### 4.1. GET không được tạo tác dụng phụ

**GET /api/orders/123/cancel** hay **GET /logout** làm sai HTTP safe methods; navigation có thể kích hoạt chúng, và SameSite=Lax vẫn cho phép cookie ở top-level GET. Chuyển mutation sang **POST/PATCH/DELETE** và bảo vệ CSRF.

**GET/HEAD/OPTIONS** không được tạo mutation nghiệp vụ; access log/metrics là tác dụng phụ kỹ thuật chấp nhận được.

## 5. Defense in depth: chọn biện pháp theo ranh giới tin cậy

| Biện pháp | Vai trò | Không thể tự giải quyết |
| --- | --- | --- |
| **Synchronizer CSRF token** gắn với session | Chứng minh request thay đổi trạng thái được tạo từ trang/client được phục vụ trong phiên hợp lệ. | Không chữa XSS hoặc cấp quyền object. |
| **Signed double-submit cookie** gắn session | Thích hợp cho kiến trúc stateless có thiết kế HMAC và cookie scope đúng. | Naive so khớp hai giá trị không có session binding dễ bị cookie injection. |
| **SameSite=Lax/Strict**, Secure, HttpOnly | Giảm tự động gửi cookie trong nhiều luồng cross-site, bảo vệ bí mật session. | Không chặn tất cả same-site attacker/legacy browser. |
| **Origin/Referer validation** | Kiểm nguồn tạo unsafe request ở lớp server. | Header có thể thiếu hoặc qua proxy; phải có policy xử lý rõ. |
| **Fetch Metadata** như Sec-Fetch-Site | Phát hiện request đến từ cross-site context. | Browser cũ/non-browser có thể không gửi; same-site không nhất thiết đáng tin. |
| **CORS allowlist và JSON-only request** | Giới hạn JS cross-origin và giúp tạo preflight với non-simple headers. | HTML form/navigation và lỗi server-side vẫn cần phòng vệ. |
| **Authentication + authorization** | Quyết định ai được quyền làm gì với resource. | Không chứng minh người dùng chủ động phát sinh POST. |

Với **session cookie**, dùng **CSRF token + SameSite + Origin/Fetch Metadata + quyền từng order** theo threat model.

### 5.1. Synchronizer token hoạt động thế nào?

1. Sau khi có phiên hợp lệ, server sinh một token **khó đoán bằng bộ sinh ngẫu nhiên an toàn**, gắn vào session hoặc cơ chế lưu trữ có thể xác minh.
2. Server cung cấp token cho HTML/JS chạy trong **origin được tin** thông qua hidden form field, response cùng origin hoặc kênh được thiết kế tương đương.
3. Với POST/PATCH/PUT/DELETE, client gửi token trong **header tùy biến** hoặc form field, **không gửi token trong URL**.
4. Server so sánh token với giá trị/đối tượng gắn với session và **từ chối trước khi thực hiện side effect** nếu thiếu hoặc sai.
5. Sau login/logout/session rotation, client nhận token tương ứng phiên mới; token cũ không được mặc định chấp nhận.

~~~http
POST /api/orders/123/cancel HTTP/1.1
Host: shop.example.com
Cookie: SESSION=<session-id>
Content-Type: application/json
X-CSRF-TOKEN: <csrf-token>

{"reason":"changed-my-mind"}
~~~

**Cookie tự gửi**, còn **X-CSRF-TOKEN** do client tin cậy bổ sung. CSRF token **không thay access token, idempotency key hoặc object authorization**.

### 5.2. Double-submit cookie: không dùng bản so sánh ngây thơ

Double-submit gửi token trong **cookie và header/form**. So khớp hai chuỗi mà không gắn session dễ bị **cookie injection**. Dạng chắc chắn hơn dùng **HMAC server-side gắn session và nonce**, không để client tự tạo binding.

Đánh giá **CookieCsrfTokenRepository**, token masking, cookie scope và request handler theo phiên bản Spring. Với session, token do Spring quản lý thường dễ hơn tự xây crypto.

## 6. Origin, Fetch Metadata và CORS hỗ trợ CSRF defense thế nào?

### 6.1. Kiểm tra Origin ở server cho unsafe methods

**Origin** mang scheme/host/port của nguồn request. Với unsafe cookie request, so khớp Origin với **allowlist**; proxy phải chuẩn hóa Host/Forwarded headers, không tin header do client tự khai báo.

Một chính sách phòng vệ bổ trợ:

~~~text
Unsafe request nhận cookie session:
  1. Spring Security xác thực session.
  2. Kiểm CSRF token khớp session và không bị thiếu.
  3. Nếu Origin có mặt, kiểm chính xác scheme + host + port
     trong allowlist tin cậy; từ chối Origin không hợp lệ.
  4. Nếu Origin vắng, xét Referer hoặc policy fallback phù hợp.
  5. Domain service kiểm quyền actor trên order thật.
~~~

Origin có thể **vắng/null**, Referer có thể bị lược; cần fallback policy rõ ràng. Với non-browser client không có header này, dùng API authentication tách biệt thay vì ngoại lệ chung làm yếu CSRF.

### 6.2. Fetch Metadata phát hiện cross-site request

Các header như **Sec-Fetch-Site**, **Sec-Fetch-Mode**, **Sec-Fetch-Dest** cho server biết ngữ cảnh tạo request. Ví dụ:

~~~http
POST /api/orders/123/cancel HTTP/1.1
Host: shop.example.com
Origin: https://untrusted.example.net
Sec-Fetch-Site: cross-site
Sec-Fetch-Mode: navigate
~~~

Có thể từ chối **Sec-Fetch-Site: cross-site**, xét **same-site** theo trust boundary và fallback nếu header vắng. **CSRF token vẫn là chính**.

**same-site** không đồng nghĩa trusted subdomain; **Sec-Fetch-Site: none** cũng không miễn token cho unsafe requests.

### 6.3. CORS không tự chống CSRF

Cross-origin **fetch** có X-CSRF-TOKEN hoặc JSON thường cần **OPTIONS preflight**; nếu không được cho phép, browser chặn request theo kiểu này. **Không thay CSRF token**:

- HTML form với content type đơn giản vẫn có thể gửi **POST không cần CORS permission**.
- Một cấu hình parser quá rộng có thể chấp nhận **text/plain** như JSON hoặc thay đổi state qua GET, mở đường lách giả định “API chỉ nhận JSON”.
- CORS allowlist bị cấu hình phản chiếu mọi Origin, đặc biệt kết hợp credentials, làm giảm hoặc mất ranh giới đã định.
- Trình duyệt chặn **đọc response** không đảm bảo chặn **tác dụng phụ đã xảy ra**.

Không dùng **Access-Control-Allow-Origin: \*** với **Allow-Credentials: true**; chỉ allowlist origin/methods/headers cần thiết.

## 7. Spring Boot/Spring Security: session API với CSRF bật

Ví dụ sau dành cho **Spring Boot 3, Spring MVC, Spring Security 6** và ứng dụng web đăng nhập bằng **session cookie**. Client có thể là HTML server-rendered hoặc SPA same-origin. Spring Security cung cấp **CsrfFilter**, mặc định yêu cầu CSRF token đối với các unsafe methods khi CSRF protection được bật.

### 7.1. SecurityFilterChain không tắt CSRF

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
class BrowserSessionSecurity {
    @Bean
    SecurityFilterChain browserSecurity(HttpSecurity http)
            throws Exception {
        return http
                .authorizeHttpRequests(auth -> auth
                        .requestMatchers("/public/**").permitAll()
                        .anyRequest().authenticated())
                .formLogin(Customizer.withDefaults())
                .csrf(Customizer.withDefaults())
                .build();
    }
}
~~~

**CsrfFilter** mặc định dùng token gắn session và kiểm trước mutation. Spring Security 6 có **deferred token** và **masking** chống compression side channel; không dùng hướng dẫn handler cũ mà bỏ qua cơ chế này.

**formLogin** có thể trả **302** tới login thay vì API JSON 401; cần entry point thích hợp. **403 do CSRF khác 403 do authorization**, dù cùng status.

### 7.2. Controller bảo vệ domain và không làm việc ở GET

~~~java
import java.util.UUID;
import org.springframework.http.ResponseEntity;
import org.springframework.security.core.Authentication;
import org.springframework.web.bind.annotation.*;

interface OrderCommandService {
    void cancelAuthorized(String actor, UUID orderId, String reason);
}

record CancelOrder(String reason) {}

@RestController
@RequestMapping("/api/orders")
class OrderCommandController {
    private final OrderCommandService service;

    OrderCommandController(OrderCommandService service) {
        this.service = service;
    }

    @PostMapping("/{id}/cancel")
    ResponseEntity<Void> cancel(
            @PathVariable UUID id,
            @RequestBody CancelOrder command,
            Authentication authentication) {
        service.cancelAuthorized(
                authentication.getName(), id, command.reason());
        return ResponseEntity.noContent().build();
    }
}
~~~

**cancelAuthorized** kiểm tenant/order, trạng thái, transaction; bổ sung validation, Problem Details và idempotency khi cần. **CSRF không thay authorization**.

### 7.3. Server-rendered HTML form

Trong ứng dụng render HTML, server đưa token vào một **hidden field**. Spring Security tích hợp với các cơ chế form/view được hỗ trợ để cung cấp CSRF token. Cấu trúc kết quả:

~~~html
<form method="post" action="/orders/123/cancel">
  <input type="hidden" name="_csrf"
         value="TOKEN_RENDERED_BY_TRUSTED_SERVER">
  <input name="reason" value="changed-my-mind">
  <button type="submit">Cancel order</button>
</form>
~~~

Token phải được server render theo session, **không dùng placeholder cố định**. Ví dụ này giả định endpoint HTML form **/orders/.../cancel** riêng; controller **/api/orders/.../cancel** nhận JSON thì dùng Fetch, không tắt CSRF để tránh lỗi body.

### 7.4. Endpoint cung cấp token cho SPA same-origin

Một SPA same-origin có thể lấy CSRF token từ endpoint đã xác thực; ví dụ:

~~~java
import java.util.Map;
import org.springframework.http.CacheControl;
import org.springframework.http.ResponseEntity;
import org.springframework.security.web.csrf.CsrfToken;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
class CsrfTokenController {
    @GetMapping("/api/csrf")
    ResponseEntity<Map<String, String>> csrf(CsrfToken token) {
        return ResponseEntity.ok()
                .cacheControl(CacheControl.noStore())
                .body(Map.of(
                        "headerName", token.getHeaderName(),
                        "token", token.getToken()));
    }
}
~~~

Endpoint nhận **CsrfToken** từ Spring Security, có **no-store**, không log hay cấp CORS cho origin lạ. Với Spring Security 6, token có thể được **mask**; gửi lại đúng giá trị do handler/repository chấp nhận.

### 7.5. Fetch gửi token cùng cookie theo chính sách

~~~javascript
async function cancelOrder(orderId, reason) {
  const tokenResponse = await fetch("/api/csrf", {
    credentials: "same-origin",
    cache: "no-store",
    headers: { Accept: "application/json" }
  });
  if (!tokenResponse.ok) {
    throw new Error("Cannot obtain CSRF token");
  }
  const { headerName, token } = await tokenResponse.json();

  const response = await fetch(
    "/api/orders/" + encodeURIComponent(orderId) + "/cancel",
    {
      method: "POST",
      credentials: "same-origin",
      headers: {
        "Content-Type": "application/json",
        [headerName]: token
      },
      body: JSON.stringify({ reason })
    }
  );
  if (!response.ok) {
    throw new Error("Cancel failed: HTTP " + response.status);
  }
}
~~~

Fetch mặc định **credentials: same-origin**; code viết rõ để dễ kiểm thử. Không gửi token qua URL/log; tải lại sau đổi phiên và không retry POST vô hạn. **XSS vẫn có thể sử dụng token**, cần chống XSS/CSP.

### 7.6. Cookie flags là lớp bổ trợ, không thay token

Ví dụ cấu hình session cookie trong Spring Boot (cần HTTPS ở production):

~~~properties
server.servlet.session.cookie.secure=true
server.servlet.session.cookie.http-only=true
server.servlet.session.cookie.same-site=lax
~~~

Giới hạn **Domain/Path**; prefix **__Host-** đòi Secure, Path=/, không Domain. Cookie flags **không thay CSRF token/quyền domain**.

## 8. SPA khác origin và cookie: cấu hình CORS mà không bỏ CSRF

**https://app.example.com** gọi **https://api.example.com** là **cross-origin, same-site**. Fetch cần **credentials: include**, API cần CORS allowlist và **vẫn kiểm CSRF token**.

Ví dụ Spring Web MVC với bean cấu hình CORS:

~~~java
import java.util.List;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.cors.CorsConfiguration;
import org.springframework.web.cors.CorsConfigurationSource;
import org.springframework.web.cors.UrlBasedCorsConfigurationSource;

@Configuration
class BrowserCorsConfig {
    @Bean
    CorsConfigurationSource corsConfigurationSource() {
        CorsConfiguration config = new CorsConfiguration();
        config.setAllowedOrigins(
                List.of("https://app.example.com"));
        config.setAllowedMethods(
                List.of("GET", "POST", "PATCH", "DELETE", "OPTIONS"));
        config.setAllowedHeaders(
                List.of("Content-Type", "X-CSRF-TOKEN"));
        config.setAllowCredentials(true);

        UrlBasedCorsConfigurationSource source =
                new UrlBasedCorsConfigurationSource();
        source.registerCorsConfiguration("/api/**", config);
        return source;
    }
}
~~~

Trong SecurityFilterChain, thêm **.cors(Customizer.withDefaults())** để xử lý preflight; không phản chiếu Origin tùy ý hoặc dùng wildcard với credentials.

Client tương ứng dùng:

~~~javascript
const csrfResponse = await fetch(
  "https://api.example.com/api/csrf",
  { credentials: "include", cache: "no-store" }
);
if (!csrfResponse.ok) throw new Error("CSRF init failed");
const csrf = await csrfResponse.json();

const result = await fetch(
  "https://api.example.com/api/orders/123/cancel",
  {
    method: "POST",
    credentials: "include",
    headers: {
      "Content-Type": "application/json",
      [csrf.headerName]: csrf.token
    },
    body: JSON.stringify({ reason: "user-requested" })
  }
);
~~~

Nếu SPA ở **site khác**, cookie có thể cần **SameSite=None; Secure** nhưng vẫn bị browser chặn third-party cookies. Cân nhắc **BFF/OAuth-OIDC** thay vì nới lỏng toàn bộ CORS/SameSite.

Với **CookieCsrfTokenRepository.withHttpOnlyFalse()**, chỉ cookie **CSRF** mới cần JS đọc; cookie **session vẫn HttpOnly**. Spring Security 6 cần SPA request handler tương thích **masked token**, đặc biệt sau login/logout.

## 9. Khi nào API stateless có thể không cần CSRF token?

API **chỉ nhận Bearer Authorization header**, không nhận ambient browser credentials, thường **không gặp CSRF truyền thống**. Điều kiện là **thực sự bearer-only**, không phải chỉ có tên REST/JWT/SPA.

| Thiết kế | Lựa chọn CSRF |
| --- | --- |
| Web đăng nhập bằng session cookie | **Giữ CSRF protection** cho unsafe methods. |
| SPA có JWT **trong cookie** tự gửi | **Vẫn cần CSRF protection**. |
| API cho mobile/backend, Bearer header rõ ràng, không ambient browser credentials | Có thể **tắt CSRF cho đúng security chain** sau khi xác minh threat model. |
| HTTP Basic/remembered credentials hoặc browser mTLS | **Không tự coi là miễn CSRF**. |
| Ứng dụng đồng thời session web và Bearer M2M | **Tách security chains** và route ownership rõ ràng. |

Ví dụ security chain **riêng** cho các endpoint machine-to-machine:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.annotation.Order;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configurers.AbstractHttpConfigurer;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
class MachineApiSecurity {
    @Bean
    @Order(1)
    SecurityFilterChain machineApi(HttpSecurity http) throws Exception {
        return http
                .securityMatcher("/m2m/**")
                .sessionManagement(s -> s.sessionCreationPolicy(
                        SessionCreationPolicy.STATELESS))
                .csrf(AbstractHttpConfigurer::disable)
                .authorizeHttpRequests(auth -> auth
                        .anyRequest().hasAuthority("SCOPE_orders.write"))
                .oauth2ResourceServer(oauth -> oauth.jwt(
                        Customizer.withDefaults()))
                .build();
    }
}
~~~

Chain trên **chỉ match /m2m/** và chỉ dùng Bearer. Với cùng ứng dụng, browser chain phần 7 đặt **@Order(2)** và **giữ CSRF bật**; không để cookie/session routes rơi vào chain miễn CSRF.

Bearer-only API vẫn phải chống **XSS, token theft, replay, BOLA**, kiểm TLS/scope/tenant và idempotency; miễn CSRF không đồng nghĩa an toàn hoàn toàn.

## 10. Các trường hợp biên của API trên trình duyệt

- **Login CSRF:** trang lạ có thể cố đưa nạn nhân đăng nhập vào **tài khoản do attacker kiểm soát** để làm sai ngữ cảnh giao dịch. Login form và OAuth/OIDC redirect cần CSRF/state protection phù hợp, không chỉ bảo vệ POST nghiệp vụ sau login.
- **Logout CSRF:** logout qua GET có thể bị kích hoạt bằng navigation/link. Nên dùng POST có CSRF protection hoặc flow được framework hỗ trợ và tránh thay đổi phiên qua GET.
- **Cookie lifetime/session fixation:** CSRF token phải gắn đúng vòng đời phiên; sau xác thực/đăng xuất/đổi session có thể cần tải token mới. Không retry unsafe POST với token hết hiệu lực vô hạn.
- **Subdomain takeover/cookie injection:** kẻ tấn công kiểm soát một subdomain cùng site có thể làm hỏng giả định SameSite hoặc naive double-submit. Giới hạn host, kiểm Origin và dùng token gắn phiên.
- **WebSocket:** browser có thể gửi cookie trong WebSocket handshake. Nếu server chấp nhận nâng cấp từ origin bất kỳ, nguy cơ **cross-site WebSocket hijacking** xuất hiện; kiểm **Origin**, phiên/quyền và handshake/message authorization. CORS của Fetch không phải bảo vệ tự động cho WebSocket.
- **CORS preflight:** thường là **OPTIONS**, bình thường không mang cookie; xử lý trước authentication và không yêu cầu CSRF token cho OPTIONS.
- **Response cache:** endpoint **/api/csrf** trả token gắn phiên cần **Cache-Control: no-store**, không được public CDN cache hoặc trộn token giữa người dùng.

### 10.1. Status HTTP và hợp đồng lỗi

| Kịch bản | Kết quả mong muốn |
| --- | --- |
| Chưa có phiên hoặc cookie session hết hạn | **401** cho API JSON nếu entry point đã cấu hình; web form flow có thể **302** tới login. |
| Đã đăng nhập nhưng thiếu/sai CSRF token ở POST | **403 Forbidden**, service **không** được gọi. |
| Có CSRF token đúng nhưng không có quyền order | **403 hoặc 404** theo domain policy; không lộ order. |
| CSRF và quyền hợp lệ, yêu cầu hủy thành công | **204 No Content** hoặc trạng thái theo API contract. |
| GET/HEAD/OPTIONS không gây side effect | Trả status theo semantics HTTP; không cần CSRF token chỉ để đọc. |
| Content-Type không hỗ trợ hoặc JSON sai | **415/400** theo contract; không tắt CSRF để né lỗi này. |

Không coi mọi 403 là lỗi CSRF. Dùng error code nội bộ, metrics có nhãn an toàn và tracing để phân biệt **CSRF rejection** với **access denied**. Nếu trả Problem Details cho lỗi CSRF, không đưa token hay cấu trúc session vào body lỗi. Với trạng thái 403, không khuyến khích client tự động gửi lại cùng thao tác cho tới khi làm rõ phiên/token và ý định người dùng.

## 11. Kiểm thử CSRF trên HTTP và browser thực

### 11.1. Ma trận kiểm thử tối thiểu

| ID | Request / môi trường | Kỳ vọng |
| --- | --- | --- |
| C01 | POST có session, **không có CSRF token** | **403**, service không được gọi. |
| C02 | POST có session, token không đúng phiên hoặc bị sửa | **403**, không có side effect. |
| C03 | POST có session và token đúng, actor có quyền | **204** theo contract, đúng một mutation. |
| C04 | POST có token đúng nhưng actor không sở hữu order | **403/404** từ domain, không lọt dữ liệu. |
| C05 | GET /api/orders/{id} không gửi CSRF token | GET vẫn hoạt động theo authentication/authorization, **không thay trạng thái**. |
| C06 | Cross-site HTML form và cookie SameSite=None | Không thực hiện mutation nếu thiếu CSRF token, bất kể có đọc được response hay không. |
| C07 | SPA đổi Origin sang host không nằm trong CORS allowlist | CORS không cho phép script đọc/thực hiện non-simple cross-origin request; server vẫn chặn unsafe simple requests thiếu CSRF. |
| C08 | Login/logout/session rotation, SPA giữ token cũ | Token cũ không được mặc định chấp nhận; tải lại token đúng phiên. |
| C09 | Cross-origin same-site subdomain bị kiểm soát | Không vượt token/Origin policy chỉ nhờ SameSite. |
| C10 | /m2m/** Bearer-only và /api/** cookie-session | Chỉ M2M chain được miễn CSRF; browser session routes vẫn bảo vệ. |

### 11.2. Spring MockMvc với spring-security-test

Giả định ứng dụng có **BrowserSessionSecurity** và **OrderCommandController** ở phần 7, cùng service fixture cho order có quyền:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.*;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.*;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.*;

@SpringBootTest
@AutoConfigureMockMvc
class OrderCsrfIT {
    @Autowired MockMvc mvc;
    private static final String ID =
            "11111111-1111-4111-8111-111111111111";

    @Test
    void noCsrfTokenIsForbidden() throws Exception {
        mvc.perform(post("/api/orders/{id}/cancel", ID)
                .with(user("alice"))
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"reason\":\"requested\"}"))
            .andExpect(status().isForbidden());
    }

    @Test
    void invalidCsrfTokenIsForbidden() throws Exception {
        mvc.perform(post("/api/orders/{id}/cancel", ID)
                .with(user("alice"))
                .with(csrf().useInvalidToken())
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"reason\":\"requested\"}"))
            .andExpect(status().isForbidden());
    }

    @Test
    void validCsrfTokenAllowsAuthorizedCommand() throws Exception {
        mvc.perform(post("/api/orders/{id}/cancel", ID)
                .with(user("alice"))
                .with(csrf())
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"reason\":\"requested\"}"))
            .andExpect(status().isNoContent());
    }
}
~~~

**Điều kiện chạy:** phải thêm **spring-security-test**, bật security filters và chuẩn bị **OrderCommandService** test fixture cho actor alice có quyền cancel. Nếu service từ chối do domain rule, test cuối sẽ trả lỗi domain chứ không phải 204. Các ví dụ **csrf()** là request post-processor của MockMvc; chúng **không chứng minh trình duyệt đã nhận cookie và truyền token đúng**.

### 11.3. Kiểm thử round-trip thật qua browser

Với môi trường thử nghiệm được phép, dùng browser automation hoặc kiểm thử tích hợp trên local/staging:

1. Đăng nhập, ghi nhận cookie flags **Secure/HttpOnly/SameSite** và lấy token thông qua **GET /api/csrf**; response phải **no-store**.
2. Gửi POST cùng cookie **không có token** và **token sai**: 403, DB không thay đổi.
3. Gửi POST có token đúng: trả status nghiệp vụ dự kiến; yêu cầu hủy phải kiểm owner.
4. Chuyển sang một origin giả lập không tin cậy và thử **HTML form**; xác nhận browser cookie behavior và server không có side effect.
5. Từ **app.example.com** gọi **api.example.com** với credentials include và CORS allowlist; thử origin khác và preflight không hợp lệ.
6. Logout/login lại hoặc đổi session, xác nhận token vòng đời cũ không dùng lại được theo thiết kế.

**Không chỉ dựa vào DevTools thấy “CORS blocked”**: cần kiểm DB/audit rằng side effect không xảy ra. Đối với kiểm thử Browser API, kết quả phụ thuộc scheme, origin, SameSite, browser và cookie configuration thực tế; **MockMvc đơn thuần không mô phỏng tất cả**.

## 12. Bài tập: Orders SPA và tài khoản nhân viên

**Bối cảnh:** frontend chạy ở **https://app.example.com**, backend ở **https://api.example.com**. Nhân viên đăng nhập bằng session cookie của API. Một đội đề xuất **SameSite=None; Secure** để frontend gọi được API và tắt CSRF vì đã có CORS allowlist. Một endpoint **GET /api/orders/{id}/approve** lại thực hiện phê duyệt đơn. API còn có nhánh **/m2m/** dành cho batch dùng Bearer JWT.

**Yêu cầu:** (1) Phân biệt origin/site của app và API. (2) Chỉ ra ít nhất ba rủi ro trong phương án trên. (3) Đề xuất cookie flags, CSRF token flow và CORS/Origin policy. (4) Sửa endpoint GET approve về HTTP method phù hợp. (5) Nêu phạm vi tắt CSRF có thể chấp nhận được cho /m2m/**. (6) Viết ít nhất bốn phép test phát hiện CSRF, quyền tài nguyên và cấu hình sai.

**Hướng giải:** app và API **cross-origin nhưng same-site** khi cùng HTTPS và registrable domain; fetch cần credentials include và allowlist origin. **Không tắt CSRF trên session routes**; cấp token qua endpoint same-origin/allowlisted origin, gửi qua header trên unsafe requests và không lưu token ở URL/cache công khai. Cookie Secure, HttpOnly (cho session), SameSite phù hợp với luồng thực; **SameSite=None chỉ khi thật sự cần cross-site**. Chuyển approve sang **POST/PATCH** với token + domain authorization. Chỉ chain **Bearer-only stateless /m2m/** mới có thể tắt CSRF sau khi xác nhận không nhận ambient browser credentials. Test thiếu/sai token 403, token đúng nhưng thiếu quyền bị từ chối, form từ origin không tin cậy không đổi DB, và CORS không mở cho origin lạ.

## 13. Checklist triển khai

- [ ] Phân loại credential: cookie/session, browser Basic/mTLS hay Bearer header chủ động.
- [ ] **GET/HEAD/OPTIONS** không thực hiện command nghiệp vụ; unsafe methods dùng đúng semantics.
- [ ] Session/ambient credential routes có **CSRF token** được kiểm trước side effect.
- [ ] Token có entropy đủ mạnh, ràng buộc đúng phiên; không gửi qua URL, logs, cache công khai.
- [ ] Cookie session có **Secure, HttpOnly, SameSite, Domain/Path** phù hợp và HTTPS thật.
- [ ] **CORS allowlist**, Origin/Fetch Metadata là lớp bổ trợ, không thay CSRF token.
- [ ] SPA có quy trình lấy/gửi/làm mới token sau login/logout/session rotation.
- [ ] Stateless Bearer-only routes được tách security chain; không tắt CSRF toàn bộ ứng dụng.
- [ ] Domain service vẫn kiểm tenant/object authorization, idempotency và concurrency.
- [ ] Test 403 khi thiếu/sai token, flow browser thực, subdomain, redirect/CORS và không có side effect.

**Kết luận:** **CSRF không phụ thuộc API có tên REST, dùng JSON hay JWT; nó phụ thuộc việc trình duyệt có tự gửi credential hay không**. Với session/cookie, cần **token chống CSRF được kiểm ở server**, cấu hình cookie và origin đúng, không thực hiện thay đổi trạng thái qua GET, đồng thời giữ nguyên **authentication và object-level authorization**. CORS và SameSite là các lớp bổ trợ; chỉ miễn CSRF cho những endpoint thật sự không dùng ambient browser credential, với ranh giới và kiểm thử rõ ràng.
