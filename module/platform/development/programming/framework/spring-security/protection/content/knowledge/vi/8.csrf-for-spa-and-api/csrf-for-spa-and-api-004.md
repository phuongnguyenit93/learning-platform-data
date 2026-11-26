# Lấy CSRF token khi khởi tạo ứng dụng

## Mục tiêu và bối cảnh

Trong chương **CSRF cho SPA và API** của module **SPRING_SECURITY_HTTP_PROTECTION**, ứng dụng một trang (SPA) cần có một câu trả lời thực tế: khi giao diện mới mở, JavaScript lấy **CSRF token** từ đâu để có thể gửi **POST/PUT/PATCH/DELETE** an toàn? Nếu giao diện được render toàn bộ tại trình duyệt, ta không thể mặc định token đã có sẵn trong form HTML do server tạo.

Bài học hướng dẫn một luồng **bootstrap CSRF token** cho SPA dùng cookie để xác thực, áp dụng cho cả **Spring MVC (Servlet)** và **Spring WebFlux (Reactive)**. Nội dung bao gồm endpoint cấp token, cách gọi khi khởi tạo SPA, deferred token, BREACH/XOR masking, vòng đời token sau login/logout, CORS khi SPA khác origin, kiểm thử và chẩn đoán xung đột với session, SameSite, security headers, CSP, HSTS và HTTP firewall.

Sau bài học, người học có thể:

- Giải thích vì sao SPA dùng cookie đăng nhập cần CSRF token cho thao tác thay đổi trạng thái.
- Phân biệt vai trò của **CsrfTokenRepository**, **CsrfTokenRequestHandler** và cơ chế deferred token.
- Tạo endpoint **GET /api/csrf** trả token, tên header và không cho cache chung.
- Thiết kế bootstrap để request ghi chờ token sẵn sàng, đồng bộ token với cookie phiên.
- Làm mới token khi login, logout hoặc session đổi và không retry POST nguy hiểm một cách mù quáng.
- Kiểm thử luồng Servlet/Reactive và phân biệt lỗi CSRF, xác thực, phân quyền, cookie hoặc CORS.

## 1. Tại sao token phải được lấy trước request ghi?

Giả sử SPA gọi API JSON đã đăng nhập bằng cookie:

~~~http
POST /api/orders HTTP/1.1
Host: app.example.com
Cookie: JSESSIONID=...
Content-Type: application/json

{"sku":"P100","quantity":1}
~~~

Browser có thể **tự đính kèm cookie** theo các quy tắc Domain, Path, SameSite, Secure và request credentials. API thấy cookie phiên hợp lệ, nhưng điều đó chưa chứng minh người dùng đã chủ ý gửi request. Một trang không tin cậy có thể gây **Cross-Site Request Forgery (CSRF)** nếu backend chấp nhận request đã xác thực dựa trên cookie mà không xác minh tính chủ ý.

Spring Security thông thường yêu cầu **CSRF token** cho các phương thức không an toàn, chẳng hạn **POST, PUT, PATCH, DELETE**. SPA cần gửi một giá trị token mà website độc hại không dễ lấy được, ví dụ trong header **X-CSRF-TOKEN**; server xác minh token với repository tương ứng.

**Phạm vi quan trọng:** Nếu API chỉ chấp nhận **Authorization: Bearer** do JavaScript chủ động gắn và không có đường xác thực browser tự gửi credential, mô hình CSRF khác. Bài này nói về SPA dùng **session cookie**, **JWT trong cookie** hoặc một cơ chế xác thực dựa trên cookie ở gateway/BFF. API JSON hay backend stateless không tự động miễn CSRF.

### 1.1. Ba cách cấp token cho client

| Cách cấp token | Phù hợp với | Lưu ý |
| --- | --- | --- |
| Token nhúng vào HTML phía server, ví dụ form hoặc meta | Trang server-side rendering | SPA thuần có thể chỉ có một HTML shell tĩnh |
| **GET /api/csrf** trả token và headerName qua JSON | SPA cùng origin hoặc SPA khác origin được CORS cho phép | Giữ cùng cookie ở GET và POST; chú ý cache và vòng đời token |
| Cookie **XSRF-TOKEN** đọc được bằng JavaScript | SPA cùng phạm vi cookie dùng cookie CSRF repository | Cần handler nhận raw token, xem xét masking, subdomain và cookie injection |

Một endpoint JSON rõ ràng thường dễ kiểm soát vì client biết **khi nào** đã nhận token, **header** nào phải gửi và **khi nào** cần lấy lại.

## 2. Luồng bootstrap cho SPA

~~~mermaid
sequenceDiagram
    autonumber
    participant B as SPA trong browser
    participant S as Spring Security
    participant C as API controller
    B->>S: GET /api/csrf + cookie nếu có
    S->>S: Load hoặc tạo CSRF token
    S->>C: Gắn CsrfToken vào request
    C-->>B: 200 JSON {headerName, token}; no-store
    Note over B: Lưu token trong memory, mở chức năng ghi
    B->>S: POST /api/orders + cookie + header CSRF
    S->>S: Đối chiếu token
    alt Token hợp lệ
        S->>C: Cho request đi tiếp
        C-->>B: Response nghiệp vụ
    else Token thiếu hoặc không hợp lệ
        S-->>B: Thường là 403 Forbidden
    end
~~~

Ở bước GET, CSRF filter mặc định không yêu cầu token đối với một phương thức an toàn. Controller cần thực sự **truy cập token** để deferred token được hiện thực hóa. Ở bước POST, bộ lọc so khớp token cùng repository hiện tại trước khi nghiệp vụ xử lý.

Một token CSRF **không phải access token**: nó không cấp quyền, không xác định danh tính và không thay thế xác thực, phân quyền hay kiểm tra đầu vào.

### 2.1. Sáu điều kiện để chuỗi hoạt động

1. **CSRF protection được bật** cho đường xử lý POST và các thao tác có tác động.
2. **GET /api/csrf đi qua cơ chế cấp token tương thích** với cơ chế kiểm tra POST. Với nhiều SecurityFilterChain, tránh tạo token ở chain này rồi xác minh ở repository hoàn toàn khác.
3. Server trả **token** và **headerName** thực tế, client không tự biến đổi hoặc đoán định dạng.
4. GET và POST có cùng cookie phiên hoặc cùng thông tin repository cần dùng.
5. SPA tải lại token khi login/logout, session hoặc trạng thái xác thực thay đổi.
6. Response token không được cache chia sẻ hay cấp cho JavaScript của origin không tin cậy.

## 3. Spring Security Servlet: GET /api/csrf

Ví dụ dùng **Spring Boot 3, Spring Security 6, Java 17+** ở Servlet stack. Các class chỉ minh họa phần bảo vệ CSRF và phải được đặt cùng cấu hình xác thực thực tế của ứng dụng.

### 3.1. Giữ CSRF, cho phép GET cấp token

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
class SecurityConfiguration {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
        return http
            .csrf(Customizer.withDefaults())
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET, "/api/csrf").permitAll()
                .requestMatchers("/api/**").authenticated()
                .anyRequest().permitAll()
            )
            .build();
    }
}
~~~

**permitAll** ở đây cho phép ứng dụng lấy CSRF token **trước khi đăng nhập**. Một số SPA cần token để gửi chính POST login. Đây là quy tắc ủy quyền, không phải lệnh bỏ CsrfFilter. Các POST vẫn bị kiểm tra CSRF theo cấu hình.

Cấu hình Servlet CSRF mặc định thường dùng **HttpSessionCsrfTokenRepository** để lưu token trong HttpSession. Token sẽ cần được hiện thực hóa khi endpoint đọc nó; GET này có thể tạo session và phát **JSESSIONID** nếu trước đó chưa có. Điều này không biến GET thành thao tác thay đổi dữ liệu nghiệp vụ; đây là state phục vụ bảo mật.

### 3.2. Endpoint trả JSON và chống cache

~~~java
import jakarta.servlet.http.HttpServletRequest;
import org.springframework.http.CacheControl;
import org.springframework.http.ResponseEntity;
import org.springframework.security.web.csrf.CsrfToken;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
class CsrfBootstrapController {

    record CsrfPayload(String headerName, String token) {}

    @GetMapping("/api/csrf")
    ResponseEntity<CsrfPayload> csrf(HttpServletRequest request) {
        CsrfToken csrf = (CsrfToken) request.getAttribute(
            CsrfToken.class.getName());

        if (csrf == null) {
            throw new IllegalStateException("CSRF filter not available");
        }

        // Truy cập getToken() để deferred token được tạo/nạp.
        return ResponseEntity.ok()
            .cacheControl(CacheControl.noStore())
            .body(new CsrfPayload(csrf.getHeaderName(), csrf.getToken()));
    }
}
~~~

Response điển hình:

~~~http
HTTP/1.1 200 OK
Content-Type: application/json
Cache-Control: no-store
Set-Cookie: JSESSIONID=...; Path=/; HttpOnly; Secure

{"headerName":"X-CSRF-TOKEN","token":"..."}
~~~

**Set-Cookie chỉ là ví dụ.** Khi session đã có, server không nhất thiết phát lại cookie. Khi cấu hình repository khác, tên token header và cookie có thể khác.

**Cache-Control: no-store** giúp ngăn trình duyệt, proxy và CDN lưu response chứa token gắn với ngữ cảnh phiên. Ngoài ra nên cấu hình tầng gateway/CDN không cache đường **/api/csrf**. Không đưa token vào query string hoặc URL để tránh lộ qua browser history, log và Referer. Không in token ra log ứng dụng hoặc analytics.

### 3.3. Vì sao GET thông thường có thể chưa sinh token?

Spring Security hiện đại hỗ trợ **deferred CSRF token**: repository có thể hoãn việc tải và lưu token cho đến khi code thật sự cần. Chỉ đi qua CsrfFilter hoặc trả **204 No Content** có thể chưa làm **XSRF-TOKEN** cookie xuất hiện.

Vì vậy controller **gọi getToken()**. Đây là hành vi cần kiểm thử, không nên chỉ kiểm tra status GET là 200. Khi dùng CookieCsrfTokenRepository, bước truy cập token cũng giúp cookie có cơ hội được ghi ra response.

### 3.4. XOR masking và BREACH

Spring Security Servlet 6 mặc định thường dùng **XorCsrfTokenRequestAttributeHandler**: giá trị token được trình bày trong request attribute có thể được **mask** để giảm rủi ro kiểu **BREACH** khi token xuất hiện trong response. Token JSON nhận được có thể khác chuỗi raw trong repository, dù cả hai biểu diễn cùng token nền.

Ở cấu hình mặc định, SPA cần gửi lại **đúng chuỗi token từ GET JSON** qua **headerName được trả về**. Đừng tự cắt chuỗi, Base64-decode, so sánh token với cookie hay cố định độ dài. Spring Security sẽ giải mã và xác minh theo request handler đang cấu hình.

Nếu đổi sang repository cookie mà JavaScript gửi giá trị token raw, phải chọn handler phù hợp. Đó là lý do không nên trộn tùy tiện mã bootstrap dựa trên token JSON được mask với mã đọc raw từ cookie.

## 4. JavaScript: khởi tạo an toàn, tránh race condition

Một SPA thường có nhiều component cùng gọi API. Nếu mỗi component tự fetch token, client có thể tạo nhiều GET không cần thiết hoặc race khi trạng thái xác thực thay đổi. Tách việc cấp token thành một service, giữ token trong memory và gộp các yêu cầu tải song song vào một Promise chung.

~~~javascript
const API_BASE = "";   // API cùng origin với SPA.
let currentCsrf = null;
let csrfPromise = null;

async function ensureCsrfToken({ force = false } = {}) {
  if (currentCsrf && !force) return currentCsrf;
  if (csrfPromise) return csrfPromise;

  csrfPromise = (async () => {
    const response = await fetch(API_BASE + "/api/csrf", {
      method: "GET",
      credentials: "same-origin",
      cache: "no-store"
    });

    if (!response.ok) {
      throw new Error("CSRF bootstrap failed: " + response.status);
    }

    const body = await response.json();
    if (typeof body.headerName !== "string" ||
        typeof body.token !== "string" ||
        body.token.length === 0) {
      throw new Error("Invalid CSRF bootstrap response");
    }

    currentCsrf = {
      headerName: body.headerName,
      token: body.token
    };
    return currentCsrf;
  })().finally(() => {
    csrfPromise = null;
  });

  return csrfPromise;
}

function clearCsrfToken() {
  currentCsrf = null;
}

async function updateProfile(profile) {
  const csrf = await ensureCsrfToken();

  const response = await fetch(API_BASE + "/api/profile", {
    method: "PATCH",
    credentials: "same-origin",
    headers: {
      "Content-Type": "application/json",
      [csrf.headerName]: csrf.token
    },
    body: JSON.stringify(profile)
  });

  if (response.status === 403) {
    clearCsrfToken();
    throw new Error("Request denied; check CSRF or permissions");
  }
  if (!response.ok) {
    throw new Error("Update failed: " + response.status);
  }

  return response.status === 204 ? null : response.json();
}

// Hàm UI này do ứng dụng tự định nghĩa.
async function bootstrapApp() {
  try {
    await ensureCsrfToken();
    enableWriteActions();
  } catch (error) {
    renderCsrfBootstrapError(error);
  }
}

bootstrapApp();
~~~

**enableWriteActions** và **renderCsrfBootstrapError** là hai hàm giao diện do ứng dụng cung cấp, không phải API có sẵn của JavaScript hay Spring Security.

### 4.1. Những trạng thái UI nên có

~~~mermaid
stateDiagram-v2
    [*] --> Loading: Khởi tạo SPA
    Loading --> Ready: GET token thành công
    Loading --> Failed: Network/CORS/5xx/JSON sai
    Failed --> Loading: Người dùng thử lại
    Ready --> Loading: Login/logout hoặc phiên thay đổi
    Ready --> Failed: Lỗi cần đồng bộ lại
    Ready --> Ready: GET đọc và POST hợp lệ
~~~

Không bắt buộc khóa toàn bộ trang nếu dữ liệu public vẫn đọc được; chỉ những chức năng ghi phụ thuộc token mới cần đợi. Một service tập trung giúp React, Angular hoặc Vue dùng cùng logic thay vì mỗi component tự giữ một token khác nhau.

### 4.2. Vì sao không tự retry POST khi nhận 403?

Response **403** có thể là **CSRF không hợp lệ**, nhưng cũng có thể do **thiếu quyền**. Hơn nữa, tự động lặp lại request tạo đơn hoặc chuyển tiền có thể tạo tác dụng phụ ngoài ý muốn nếu tầng backend xử lý không đồng nhất.

Nên xóa token cũ, chẩn đoán phản hồi lỗi có cấu trúc và lấy lại token có kiểm soát. Chỉ gửi lại thao tác ghi sau khi chắc chắn an toàn hoặc có hành động phù hợp từ người dùng.

## 5. Khi nào tải token: khởi động, trước ghi hay sau login?

| Thời điểm | Lợi ích | Chi phí/cạm bẫy |
| --- | --- | --- |
| **Ngay lúc mở SPA** | Nút ghi sẵn sàng sớm, lỗi bootstrap rõ ràng | Thêm GET; với session repository có thể tạo phiên cho cả khách chỉ đọc |
| **Trước thao tác ghi đầu tiên** | Giảm request và state không cần thiết | Client phải await Promise, tránh gửi POST khi token chưa sẵn sàng |
| **Sau login/session rotation** | Tránh token cũ không còn khớp phiên | Phải phân biệt token trước login và sau login |
| **Sau logout nếu SPA vẫn chạy** | Chuẩn bị trạng thái anonymous mới | Không tiếp tục dùng token của người dùng vừa đăng xuất |
| **Sau khi phát hiện session/token hết hạn** | Khôi phục luồng giao diện | Không retry mù quáng các POST không an toàn |

### 5.1. Login có thể làm CSRF token cũ hết hiệu lực

Trong Spring Security, **CsrfAuthenticationStrategy** có thể xóa token cũ sau khi xác thực thành công. Khi SPA lấy token A ở trạng thái anonymous và sử dụng A để gửi POST login, token A có thể không còn hợp lệ sau login.

~~~text
Mở SPA → GET /api/csrf → token A
POST /login + cookie + token A
Login thành công → xác thực/session thay đổi, token A có thể bị xóa
GET /api/csrf với cookie phiên hiện tại → token B
POST /api/orders + token B → kiểm tra CSRF và phân quyền
~~~

Phía client:

~~~javascript
async function onLoginSuccess() {
  clearCsrfToken();
  await ensureCsrfToken({ force: true });
  // Chỉ sau đó mới kích hoạt các thao tác ghi có xác thực.
}
~~~

Lưu ý cơ chế login thực tế có thể dùng Spring Security formLogin, JSON login handler, OAuth/OIDC redirect hoặc BFF. Sau redirect về SPA, cần gọi lại token trong **ngữ cảnh cookie hiện tại**, không giữ giả định token trước redirect vẫn hợp lệ.

### 5.2. Logout

**CsrfLogoutHandler** có thể xóa token khi logout. POST logout trước hết vẫn phải kèm token hợp lệ; sau khi logout, client bỏ token cũ. Nếu SPA vẫn hiển thị một giao diện anonymous có thao tác ghi, gọi GET token lại.

~~~text
POST /logout cùng token và cookie hiện tại
→ thành công; cookie/session và token có thể bị vô hiệu hóa
→ xóa token khỏi memory
→ GET /api/csrf nếu tiếp tục dùng SPA anonymous
~~~

### 5.3. Session timeout và nhiều tab

Nếu repository dùng **HttpSession**, token gắn với session backend. Sau timeout, session ID đổi hoặc một tab khác thực hiện login/logout, token cache ở SPA có thể lỗi thời. Các tab khác nhau không được đảm bảo đồng bộ bộ nhớ token.

Nên xử lý 401/403 theo luồng xác thực rõ ràng, cho phép tái khởi tạo token và điều hướng đăng nhập khi cần; không giả định cứ nhận 403 là do CSRF. Có thể kiểm thử bằng cách mở hai tab, đổi session ở tab A rồi thử POST ở tab B.

## 6. Tùy chọn: cookie XSRF-TOKEN cho SPA

Một số SPA muốn JS đọc trực tiếp cookie **XSRF-TOKEN** và đặt vào header **X-XSRF-TOKEN**. Spring Security Servlet hỗ trợ **CookieCsrfTokenRepository**:

~~~java
import org.springframework.security.web.csrf.CookieCsrfTokenRepository;
import org.springframework.security.web.csrf.CsrfTokenRequestAttributeHandler;

// Thay phần cấu hình CSRF của SecurityFilterChain Servlet:
.csrf(csrf -> csrf
    .csrfTokenRepository(CookieCsrfTokenRepository.withHttpOnlyFalse())
    .csrfTokenRequestHandler(new CsrfTokenRequestAttributeHandler())
)
~~~

Trong biến thể này:

- **withHttpOnlyFalse()** chỉ dành cho cookie **CSRF token** mà JavaScript cần đọc, không áp dụng cho cookie **JSESSIONID/JWT xác thực**.
- **CsrfTokenRequestAttributeHandler** nhận token raw mà client gửi qua header, nhưng việc thay XOR handler ảnh hưởng cơ chế masking/BREACH nếu ứng dụng cũng render token vào HTML. Với ứng dụng có cả HTML và SPA, cân nhắc handler SPA phối hợp XOR và raw header theo phiên bản Spring Security.
- Chỉ bật CookieCsrfTokenRepository vẫn có thể chưa phát cookie cho đến khi deferred token được truy cập. Dùng GET bootstrap thực sự đọc **getToken()**.
- Cần bảo vệ khỏi cookie injection từ subdomain kém tin cậy; repository cookie không tự chứng minh token là một **signed double-submit** ràng buộc mật mã với phiên.

JavaScript minh họa trên cùng hostname:

~~~javascript
function readCookie(name) {
  const prefix = encodeURIComponent(name) + "=";
  const match = document.cookie
    .split("; ")
    .find(item => item.startsWith(prefix));
  return match ? decodeURIComponent(match.slice(prefix.length)) : null;
}

async function saveSettings(settings) {
  const csrfValue = readCookie("XSRF-TOKEN");
  if (!csrfValue) throw new Error("XSRF-TOKEN cookie is missing");

  return fetch("/api/settings", {
    method: "POST",
    credentials: "same-origin",
    headers: {
      "Content-Type": "application/json",
      "X-XSRF-TOKEN": csrfValue
    },
    body: JSON.stringify(settings)
  });
}
~~~

Nếu SPA tại **app.example.com**, còn API tại **api.example.com**, JS ở SPA không thể đọc cookie **host-only** của API. Cách dễ kiểm soát hơn là GET JSON qua CORS allowlist, không tùy tiện mở rộng thuộc tính **Domain=.example.com**.

## 7. Khi SPA và API khác origin

Giả sử giao diện tại **https://app.example.com**, API tại **https://api.example.com**. Dù thường cùng site, đây là **hai origin khác nhau**. Fetch mặc định sử dụng **credentials: same-origin**, nên sẽ không gửi cookie đến API khác origin. Nếu backend dùng cookie, cả lần lấy token và lần POST cần:

~~~javascript
const API_URL = "https://api.example.com";

const csrfResponse = await fetch(API_URL + "/api/csrf", {
  credentials: "include",
  cache: "no-store"
});
if (!csrfResponse.ok) throw new Error("Cannot bootstrap CSRF");
const csrf = await csrfResponse.json();

const response = await fetch(API_URL + "/api/orders", {
  method: "POST",
  credentials: "include",
  headers: {
    "Content-Type": "application/json",
    [csrf.headerName]: csrf.token
  },
  body: JSON.stringify({ sku: "P100", quantity: 1 })
});
~~~

Servlet CORS cho origin cụ thể:

~~~java
import java.util.List;
import org.springframework.context.annotation.Bean;
import org.springframework.web.cors.CorsConfiguration;
import org.springframework.web.cors.CorsConfigurationSource;
import org.springframework.web.cors.UrlBasedCorsConfigurationSource;

@Bean
CorsConfigurationSource corsConfigurationSource() {
    CorsConfiguration config = new CorsConfiguration();
    config.setAllowedOrigins(List.of("https://app.example.com"));
    config.setAllowedMethods(List.of("GET", "POST", "PUT", "PATCH", "DELETE"));
    config.setAllowedHeaders(List.of("Content-Type", "X-CSRF-TOKEN"));
    config.setAllowCredentials(true);

    UrlBasedCorsConfigurationSource source = new UrlBasedCorsConfigurationSource();
    source.registerCorsConfiguration("/api/**", config);
    return source;
}
~~~

Bổ sung **.cors(Customizer.withDefaults())** trong **HttpSecurity** để Spring Security xử lý preflight phù hợp trước lớp xác thực. Nếu dùng request handler/repository với header **X-XSRF-TOKEN**, cập nhật allowed headers tương ứng.

**CORS và cookie là hai lớp kiểm soát độc lập**: CORS cho phép origin cụ thể đọc response; việc browser gửi/lưu cookie còn phụ thuộc **SameSite, Secure, Domain, Path, credentials mode và third-party cookie policy**. Tránh phản chiếu Origin tùy ý kết hợp credentials, và không dùng wildcard origin cho cookie auth.

Với SPA/API **khác site** thật sự, cookie có thể cần **SameSite=None; Secure**, nhưng vẫn có thể bị browser chặn third-party cookies; cân nhắc kiến trúc **BFF/cùng site** trước khi mở rộng CORS. Cookie HttpOnly bảo vệ khỏi JavaScript đọc trực tiếp, nhưng không tự loại bỏ CSRF.

### 7.1. Bảng chẩn đoán nhanh ở trình duyệt

| Hiện tượng | Kiểm tra |
| --- | --- |
| GET token 200 nhưng POST 403 | GET và POST có cùng session cookie không, token có cũ sau login không, headerName có đúng không |
| GET token nhận JSON nhưng browser không lưu cookie | credentials include, Set-Cookie, SameSite, Secure, Domain/Path, third-party policy |
| Console báo CORS error | Origin allowlist, Allow-Credentials, preflight, headers của response |
| POST bị chặn ở OPTIONS | Allowed methods và **X-CSRF-TOKEN/Content-Type**; xử lý CORS trước authentication |
| Cookie XSRF-TOKEN không đọc được | Cookie chưa được tạo, HttpOnly, host-only khác subdomain hoặc Path |
| CSRF token hợp lệ nhưng vẫn 401/403 | Authentication hoặc authorization, session timeout, security chain và access denied handler |

## 8. Spring Security WebFlux (Reactive): bootstrap Mono<CsrfToken>

Reactive sử dụng **SecurityWebFilterChain**, **ServerHttpSecurity** và **CsrfWebFilter**. Repository mặc định thường gắn với **WebSession**; token có thể được cấp qua một **Mono<CsrfToken>** dưới request attribute của **ServerWebExchange**.

### 8.1. Cấu hình Reactive

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.web.server.SecurityWebFilterChain;

@Bean
SecurityWebFilterChain webFluxSecurity(ServerHttpSecurity http) {
    return http
        .csrf(Customizer.withDefaults())
        .authorizeExchange(auth -> auth
            .pathMatchers(HttpMethod.GET, "/api/csrf").permitAll()
            .pathMatchers("/api/**").authenticated()
            .anyExchange().permitAll()
        )
        .build();
}
~~~

### 8.2. Controller phản hồi JSON và hiện thực hóa token

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
class ReactiveCsrfBootstrapController {

    @GetMapping("/api/csrf")
    Mono<ResponseEntity<Map<String, String>>> csrf(ServerWebExchange exchange) {
        Mono<CsrfToken> tokenMono =
            exchange.getAttribute(CsrfToken.class.getName());

        if (tokenMono == null) {
            return Mono.error(
                new IllegalStateException("CSRF filter not configured"));
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

Khi pipeline **subscribe** vào Mono và tạo body JSON, token được truy cập, tránh tình trạng deferred Mono không chạy. **Không block()** trong reactive controller. Khi dùng **CookieServerCsrfTokenRepository**, cần lựa chọn handler tương ứng của WebFlux; không dùng trực tiếp lớp request handler của Servlet.

CORS cho WebFlux sử dụng các thành phần **Reactive** như **CorsWebFilter** và **org.springframework.web.cors.reactive.UrlBasedCorsConfigurationSource**. Đảm bảo preflight được xử lý trước các bước xác thực. JavaScript vẫn phải dùng **credentials: include** nếu API khác origin và xác thực bằng cookie.

## 9. Kiểm thử luồng bootstrap

### 9.1. MockMvc: nhận token thực và dùng cùng session

Test helper **.with(csrf())** xác minh được filter, nhưng luồng bootstrap còn cần kiểm thử lấy token từ endpoint, lưu cùng session và gửi header tương ứng.

Ví dụ bên dưới giả định có **POST /api/profile**, nhận JSON và có nghiệp vụ trả 2xx khi dữ liệu hợp lệ.

~~~java
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.user;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
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
class CsrfBootstrapTests {

    @Autowired MockMvc mvc;

    @Test
    void tokenFromBootstrapCanBeUsedInSameSession() throws Exception {
        MvcResult bootstrap = mvc.perform(get("/api/csrf"))
            .andExpect(status().isOk())
            .andReturn();

        String body = bootstrap.getResponse().getContentAsString();
        String headerName = JsonPath.read(body, "$.headerName");
        String token = JsonPath.read(body, "$.token");

        MockHttpSession session =
            (MockHttpSession) bootstrap.getRequest().getSession(false);

        if (session == null || token == null || token.isEmpty()) {
            throw new AssertionError("Bootstrap did not create CSRF token");
        }

        mvc.perform(post("/api/profile")
                .session(session)
                .with(user("alice"))
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"displayName\":\"Alice\"}"))
            .andExpect(status().isForbidden());

        mvc.perform(post("/api/profile")
                .session(session)
                .with(user("alice"))
                .header(headerName, "invalid-token")
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"displayName\":\"Alice\"}"))
            .andExpect(status().isForbidden());

        mvc.perform(post("/api/profile")
                .session(session)
                .with(user("alice"))
                .header(headerName, token)
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"displayName\":\"Alice\"}"))
            .andExpect(status().is2xxSuccessful());
    }
}
~~~

Các điểm cần phân biệt:

- **user("alice")** mô phỏng principal đã xác thực để tập trung kiểm tra CSRF; nó không kiểm thử quy trình login và cookie thật.
- Ví dụ dựa vào **HttpSessionCsrfTokenRepository** mặc định. Nếu dùng **CookieCsrfTokenRepository**, phải duy trì cookie CSRF; không giả định có session lưu token.
- Nên kiểm tra **dữ liệu không đổi** ở hai request bị từ chối; chỉ so status 403 chưa đủ.
- Giá trị token JSON có thể là token masked; gửi lại nguyên vẹn phù hợp request handler mặc định. Không tự thay đổi token trong test.
- Trong dự án thực tế, phải bảo đảm Spring Security filters được gắn vào MockMvc và response 2xx phù hợp với controller đã có.

### 9.2. WebFlux/WebTestClient

~~~java
import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.mockUser;
import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.csrf;

// webTestClient đã gắn Spring Security; có controller /api/profile.
webTestClient.mutateWith(mockUser("alice"))
    .post().uri("/api/profile")
    .bodyValue(Map.of("displayName", "Alice"))
    .exchange()
    .expectStatus().isForbidden();

webTestClient.mutateWith(mockUser("alice")).mutateWith(csrf())
    .post().uri("/api/profile")
    .bodyValue(Map.of("displayName", "Alice"))
    .exchange()
    .expectStatus().is2xxSuccessful();
~~~

Đây là đoạn thân test; cần **java.util.Map**, instance **WebTestClient** và endpoint có thật. Helper **csrf()** giúp kiểm tra filter, còn luồng bootstrap đầy đủ cần integration test thực hiện **GET /api/csrf**, duy trì WebSession/cookie của cùng client, rồi POST với token JSON đã nhận.

### 9.3. Ma trận kiểm thử cần có

| Kịch bản | Kỳ vọng |
| --- | --- |
| GET /api/csrf khi anonymous, endpoint permitAll | 200 JSON có headerName và token; response không được cache chia sẻ |
| POST chỉ có cookie đăng nhập, không có CSRF header | Bị từ chối, thường 403; dữ liệu không đổi |
| POST có token sai hoặc của phiên khác | Bị từ chối; dữ liệu không đổi |
| POST có cookie cùng phiên, token hợp lệ | Vượt kiểm tra CSRF; vẫn chịu authentication/authorization và nghiệp vụ |
| Token hợp lệ nhưng người dùng không đủ quyền | Vẫn bị từ chối bởi phân quyền |
| Login thành công rồi dùng token cũ | Token có thể bị xóa; SPA phải khởi tạo lại |
| Logout rồi POST dùng token cũ | Không được giả định token cũ còn hiệu lực |
| Session timeout giữa GET và POST | Phát hiện lỗi và khôi phục phiên/token có kiểm soát |
| GET khác origin không gửi cookie | POST có thể thiếu/sai phiên hoặc token |
| Preflight với X-CSRF-TOKEN từ origin không được phép | Browser không gửi request thực tế; backend vẫn phải bảo vệ CSRF |
| Nhiều component cùng chờ token | Client không gửi POST trước token; trạng thái lỗi có thể retry rõ ràng |
| Cache/proxy trả CSRF token của user khác | Phải coi là cấu hình sai và ngăn cache chia sẻ đường endpoint |

## 10. Chẩn đoán lỗi thường gặp

### “GET /api/csrf trả 200 nhưng không thấy cookie XSRF-TOKEN”

Có thể server đang dùng **HttpSessionCsrfTokenRepository** và lưu token trong session, không tạo XSRF cookie. Kiểm tra repository thực tế, GET có gọi **getToken()**, có JSESSIONID không, và Set-Cookie có bị chặn bởi browser hay không.

### “POST đầu tiên 403, tải lại trang thì được”

Có thể SPA gửi POST trước khi token/bootstrap hoàn tất, hoặc token cũ sau login. Bảo đảm action ghi await Promise dùng chung; lấy lại token sau khi trạng thái xác thực thay đổi.

### “CSRF token đã có mà POST vẫn InvalidCsrfTokenException”

Kiểm tra **cookie phiên của hai request**, CSRF repository, token bị đổi sau login/logout, tên header và sự khác nhau giữa token raw và token XOR-mask. Với cấu hình mặc định, gửi đúng token JSON, không tự giải mã.

### “SPA khác origin: GET được nhưng POST không gửi cookie”

Cần **credentials: include** ở cả hai request, CORS allowlist, **Access-Control-Allow-Credentials** phù hợp và cookie được browser chấp nhận. Cookie SameSite=Lax có thể áp dụng giữa hai subdomain cùng site, nhưng **khác origin** vẫn cần include cho fetch.

### “OPTIONS preflight trả 401 trước khi POST”

CORS phải được xử lý trước lớp xác thực cho API JSON có header CSRF. Kiểm tra allowed methods, allowed headers, origin và cấu hình Spring Security Servlet/Reactive đúng stack.

### “Đã có CSP/HSTS/HTTP firewall rồi sao vẫn cần CSRF?”

**CSP** giúp hạn chế XSS; **HSTS** thúc đẩy HTTPS; **HTTP firewall** loại bỏ request HTTP có cấu trúc nguy hiểm; **CORS** điều khiển JavaScript khác origin. Những cơ chế này không thay việc chứng minh request đã xác thực bằng cookie là do người dùng chủ ý. Đồng thời, nếu có XSS cùng origin, script độc hại có thể gọi GET token; phải chống XSS độc lập.

## 11. Bài tập thực hành

**Bài tập 1 — Bootstrap cùng origin:** Triển khai GET /api/csrf và POST /api/profile. Dùng DevTools chứng minh GET có token, POST thiếu/sai token bị từ chối, POST với token đúng và session phù hợp được xử lý.

**Bài tập 2 — Deferred token:** So sánh GET chỉ trả 204 với GET trả JSON đã gọi getToken(). Quan sát session/cookie được tạo khi nào và giải thích deferred loading.

**Bài tập 3 — Login/logout:** Khởi tạo token trước login; sau login thử token cũ và token mới. Logout rồi kiểm tra việc khởi tạo lại cho anonymous. Xác minh vòng đời dựa trên request thực chứ không suy luận từ độ dài token.

**Bài tập 4 — Khác origin:** Dùng app.example.com gọi api.example.com. So sánh GET/POST khi có hoặc thiếu credentials include, thử origin không nằm allowlist và quan sát preflight.

**Bài tập 5 — Nhiều tab, timeout:** Mở hai tab, đăng nhập lại hoặc để session timeout, thử POST ở tab có token cũ. Thiết kế thông báo và thao tác lấy token mới an toàn, tránh tự động lặp lại POST ngoài ý muốn.

## 12. Nguyên tắc cần nhớ

1. **Lấy CSRF token trước request ghi** khi SPA dùng cookie xác thực; endpoint JSON giúp quản lý thời điểm token sẵn sàng.
2. **Deferred loading** có nghĩa token không nhất thiết được tạo trên mọi GET; Servlet cần truy cập **getToken()**, Reactive cần subscribe **Mono<CsrfToken>**.
3. **Không đoán định dạng token**; với request handler mặc định, gửi lại nguyên token JSON được server cung cấp cùng headerName.
4. **Cookie phải nhất quán giữa GET và POST**; khác origin cần credentials include và cấu hình CORS, SameSite, Secure chính xác.
5. **Sau login/logout và session rotation**, xóa token cũ trong client và tải token mới khi cần.
6. **Không tự retry POST nguy hiểm chỉ vì 403**; lỗi có thể liên quan CSRF hoặc phân quyền.
7. **Kiểm thử hành vi thực**: token thiếu/sai/đúng, session khác, nhiều tab, cookie, CORS và dữ liệu không bị thay đổi khi request bị từ chối.

Một SPA được bootstrap đúng sẽ **biết khi nào CSRF token đã sẵn sàng**, **gửi token cùng phiên đăng nhập tương ứng** và **làm mới hợp lý khi phiên thay đổi**. Đó là cơ sở để lớp phòng vệ CSRF của Spring Security hoạt động ổn định trong ứng dụng JSON hiện đại.
