# Cấu hình repository và request handler trên các dòng trước đó

## Mục tiêu và phạm vi

Trong chương **CSRF cho SPA và API** thuộc module **SPRING_SECURITY_HTTP_PROTECTION**, việc tích hợp Single-Page Application (SPA) với Spring Security trên **các dòng phiên bản chưa có phương thức tiện ích CsrfConfigurer.spa()** yêu cầu cấu hình hai thành phần:

- **CsrfTokenRepository**: token CSRF được sinh, lưu và nạp ở đâu?
- **CsrfTokenRequestHandler**: token được đưa vào request attribute như thế nào và server đọc giá trị token do frontend gửi ra sao?

Đặc biệt từ **Spring Security 6.0**, **deferred CSRF token** và **XOR masking** được bật mặc định trên Servlet. Nếu frontend đọc **raw token từ cookie XSRF-TOKEN** nhưng request handler coi giá trị trong header là **XOR-masked token**, POST có thể trả **403 Forbidden** dù cookie và header giống hệt nhau.

Bài học hướng dẫn cấu hình thủ công trên **Servlet**, đối chiếu **HttpSession vs cookie repository**, triển khai tương ứng trên **Reactive/WebFlux**, kiểm thử thiếu/sai/đúng token và chẩn đoán các xung đột với CORS, SameSite, security headers, CSP, HSTS, HTTP firewall, XSS và vòng đời session.

Sau bài học, người học có thể:

1. Giải thích trách nhiệm của repository, request handler và CsrfFilter mà không nhầm lẫn các thành phần.
2. Phân biệt thay đổi quan trọng khi nâng từ **Spring Security 5.8 lên 6.x**.
3. Cấu hình **CookieCsrfTokenRepository.withHttpOnlyFalse()** cùng handler kết hợp cho raw header và masked form.
4. Sử dụng **HttpSessionCsrfTokenRepository + GET JSON** khi không muốn JavaScript đọc cookie CSRF.
5. Nạp CSRF token khi bootstrap SPA và làm mới sau login/logout.
6. Cấu hình WebFlux qua **CookieServerCsrfTokenRepository** và handler Reactive, không dùng class Servlet.
7. Thiết kế test chứng minh request bị từ chối trước khi nghiệp vụ thay đổi dữ liệu.

## 1. Xác định dòng phiên bản và stack

Trước khi copy cấu hình, kiểm tra phiên bản **spring-security-config** thực sự được resolve và ứng dụng đang chạy **Servlet hay WebFlux**.

| Phiên bản | Cấu hình Servlet | WebFlux | Điểm thay đổi |
| --- | --- | --- | --- |
| **Spring Security 5.8** | CSRF repository và request handler phù hợp API thời kỳ chuyển tiếp | Có các Server CSRF request handler tương ứng | Chuẩn bị chuyển lên 6.x; chú ý namespace Servlet khi dùng Boot 2 |
| **Spring Security 6.0–6.5** | HttpSecurity.csrf(...), CookieCsrfTokenRepository, CsrfTokenRequestHandler | ServerHttpSecurity.csrf(...), CookieServerCsrfTokenRepository, ServerCsrfTokenRequestHandler | Deferred token và XOR masking mặc định tạo yêu cầu riêng cho SPA |
| **Spring Security 7.0+ — Servlet** | Có convenience API **CsrfConfigurer.spa()** | Không suy ra có cùng API trên ServerHttpSecurity | Có thể dùng preset khi kiến trúc phù hợp |

**Mẫu Java Servlet trong bài áp dụng Spring Boot 3, Spring Security 6.x, Java 17+**, sử dụng các class thuộc **jakarta.servlet**. Với ứng dụng **Spring Security 5.8 / Spring Boot 2**, cần kiểm tra import **javax.servlet** và API chính xác của phiên bản thực tế; không copy nguyên class Jakarta.

Có thể xem dependency của dự án bằng:

~~~bash
./mvnw dependency:tree -Dincludes=org.springframework.security:spring-security-config

./gradlew dependencyInsight --dependency spring-security-config --configuration runtimeClasspath
~~~

**CsrfConfigurer.spa() xuất hiện từ Spring Security 7.0 (Servlet).** Nếu ở 6.x, lỗi không tìm thấy method là bình thường; không cần tắt CSRF, mà cấu hình repository và handler thủ công.

## 2. Ba trách nhiệm trong luồng bảo vệ CSRF

**CsrfFilter** trong Servlet xử lý request theo chu trình:

1. Repository tạo **DeferredCsrfToken**, đại diện cho expected token có thể được tải trì hoãn.
2. Handler đưa token vào request attribute, chẳng hạn **_csrf**, để controller hoặc view có thể sử dụng.
3. Với phương thức HTTP cần bảo vệ, CsrfFilter lấy expected token từ repository.
4. Handler giải quyết actual token mà client gửi qua header hoặc form parameter.
5. CsrfFilter so khớp expected và actual token; thiếu hoặc sai token bị từ chối, thường **403**.

~~~mermaid
flowchart TD
    A["Request vào Spring Security"] --> B["CsrfFilter"]
    B --> C["CsrfTokenRepository cung cấp expected token"]
    C --> D["CsrfTokenRequestHandler.handle"]
    D --> E{"HTTP method cần CSRF?"}
    E -->|GET/HEAD/OPTIONS/TRACE thường không| F["Request tiếp tục"]
    E -->|POST/PUT/PATCH/DELETE| G["Repository nạp expected token"]
    G --> H["Handler.resolveCsrfTokenValue đọc actual token"]
    H --> I{"Actual token hợp lệ?"}
    I -->|Có| J["Tiếp tục xác thực, phân quyền và controller"]
    I -->|Không| K["AccessDenied, thường 403"]
~~~

CSRF token hợp lệ **không cấp quyền đăng nhập**; request vẫn cần authentication, authorization và validation. Cookie xác thực hợp lệ **không miễn** CSRF nếu browser có thể tự gửi credential.

### 2.1. Repository và request handler không có cùng nhiệm vụ

| Thành phần | Trách nhiệm | Ví dụ |
| --- | --- | --- |
| **HttpSessionCsrfTokenRepository** | Lưu raw expected token vào HttpSession | Token gắn với session backend |
| **CookieCsrfTokenRepository** | Lưu raw expected token vào cookie | Cookie XSRF-TOKEN |
| **CsrfTokenRequestAttributeHandler** | Cung cấp và đọc token dạng plain | Raw header từ SPA |
| **XorCsrfTokenRequestAttributeHandler** | Mask token ở request attribute, giải masked token khi nhận | Form SSR có hidden _csrf |
| **CsrfFilter** | Xác minh actual với expected theo cấu hình | POST thiếu/sai token bị từ chối |

Repository **không tự biết token sẽ được trình bày raw hay masked trong HTML**. Đó là quyết định của request handler.

### 2.2. Cookie raw và token XOR-masked

Một response có thể phát cookie:

~~~http
HTTP/1.1 204 No Content
Set-Cookie: XSRF-TOKEN=raw-T; Path=/; Secure; SameSite=Lax
~~~

Frontend đọc và gửi:

~~~http
POST /api/preferences HTTP/1.1
Host: app.example.com
Cookie: JSESSIONID=session-A; XSRF-TOKEN=raw-T
X-XSRF-TOKEN: raw-T
Content-Type: application/json

{"notifications":true}
~~~

Nhưng request attribute do XOR handler cung cấp cho view có thể là **masked(T, random)** chứ không phải raw-T. Mask có thể thay đổi giữa hai response dù raw expected token không đổi. Đây là cơ chế giảm rủi ro **BREACH response-compression side channel**. Nó **không phải HMAC**, không thay HTTPS và không có tác dụng chống XSS trong origin.

Nếu handler đang giải mã **raw header** như một **masked token**, POST có thể bị lỗi **InvalidCsrfTokenException**. Giải pháp là chọn handler hiểu đúng định dạng token của client, không phải tắt CSRF.

## 3. Chọn repository dựa vào kiến trúc

### 3.1. HttpSessionCsrfTokenRepository — mặc định Servlet

Token lưu trong session backend, frontend thường lấy qua HTML form hoặc endpoint GET trả JSON.

~~~java
import org.springframework.security.web.csrf.HttpSessionCsrfTokenRepository;

// Một biến thể cấu hình HttpSecurity Servlet:
.csrf(csrf -> csrf
    .csrfTokenRepository(new HttpSessionCsrfTokenRepository())
)
~~~

GET token ở trạng thái anonymous có thể tạo HttpSession nếu repository cần lưu token. Khi session hết hạn, expected token cũ không còn hợp lệ. Frontend dùng **cùng session cookie** trên GET lấy token và POST; không cần JavaScript đọc JSESSIONID, và cookie session nên **HttpOnly**.

### 3.2. CookieCsrfTokenRepository — phù hợp SPA đọc XSRF cookie

~~~java
import org.springframework.security.web.csrf.CookieCsrfTokenRepository;

CookieCsrfTokenRepository repository =
    CookieCsrfTokenRepository.withHttpOnlyFalse();
~~~

Theo quy ước thông dụng, repository cookie dùng:

| Đối tượng | Giá trị |
| --- | --- |
| Cookie CSRF | **XSRF-TOKEN** |
| Header mà SPA gửi | **X-XSRF-TOKEN** |
| Form parameter | **_csrf** |
| HttpOnly=false | Chỉ với cookie CSRF trong mô hình JavaScript đọc cookie |
| Cookie đăng nhập | JSESSIONID/JWT phải cấu hình HttpOnly riêng |

Đừng đặt **JSESSIONID HttpOnly=false** chỉ để frontend có thể lấy CSRF token. Cookie phiên và cookie CSRF phục vụ hai mục đích hoàn toàn khác nhau.

### 3.3. So sánh kiến trúc

| Tiêu chí | Session repository | Cookie repository |
| --- | --- | --- |
| Expected token lưu ở đâu? | HttpSession server | Cookie phía browser |
| SPA đọc token từ đâu? | GET JSON hoặc HTML | document.cookie (khi được phép) |
| Cần cookie CSRF JS-readable? | Không | Có nếu SPA đọc trực tiếp |
| Đồng bộ session | GET/POST phải cùng JSESSIONID | Cookie XSRF phải được gửi/đọc phù hợp, cùng ngữ cảnh auth |
| Nguy cơ chính cần xét | Session timeout, state, JSON token cache | Cookie scope, injection, raw/XOR, subdomain |
| SPA và API khác subdomain | Endpoint JSON thường dễ kiểm soát | Cookie host-only API không đọc được từ trang SPA |
| Bearer-only API | Đánh giá CSRF theo threat model | Không thêm cookie token chỉ vì tên SPA |

**CookieCsrfTokenRepository không mặc định là signed double-submit token liên kết HMAC với session/JWT.** Với hệ thống nhạy cảm, đánh giá cookie injection và signed token hoặc synchronizer-token phù hợp.

## 4. Ba kiểu xử lý token

Trong Spring Security 6.x Servlet:

- **CsrfTokenRequestAttributeHandler** nhận token plain từ header/form.
- **XorCsrfTokenRequestAttributeHandler** randomize token xuất hiện trong request attribute; nhận masked token từ header/form.
- **Custom SPA handler** phối hợp đường plain cho **header X-XSRF-TOKEN raw** và đường XOR cho **form parameter masked**.

### 4.1. Ma trận lựa chọn request handler

| Nguồn token | Cách client gửi | Backend cần giải như |
| --- | --- | --- |
| Cookie XSRF-TOKEN JS-readable | Header raw | Plain |
| Form Thymeleaf/JSP lấy request attribute từ XOR handler | Parameter _csrf masked | XOR |
| GET JSON lấy token từ XOR request attribute | Header masked | XOR |
| GET JSON lấy raw token theo handler plain | Header raw | Plain |
| Cùng ứng dụng có SPA cookie raw và HTML form masked | Raw header hoặc masked parameter | Handler kết hợp |

**Không trộn masked JSON với handler chọn plain khi có header.** Nếu JSON trả token đã mask và client gửi nó qua header, handler kiểu SPA raw-header sẽ coi nó là raw và CSRF filter có thể từ chối. Không tự suy đoán bằng độ dài chuỗi token.

## 5. Servlet 6.x: cấu hình CookieCsrfTokenRepository và custom handler

Mẫu dưới đây dùng **Spring Boot 3 / Spring Security 6.x / Java 17+**, giả định SPA dùng cookie authentication cùng origin, và ứng dụng có thể phục vụ cả HTML form.

### 5.1. SecurityFilterChain

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.csrf.CookieCsrfTokenRepository;

@Configuration
class SpaSecurityConfiguration {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
        CookieCsrfTokenRepository repository =
            CookieCsrfTokenRepository.withHttpOnlyFalse();

        // Dùng API setCookieCustomizer ở bản 6.x có hỗ trợ.
        // Production cần HTTPS.
        repository.setCookieCustomizer(cookie -> cookie
            .secure(true)
            .sameSite("Lax")
            .path("/")
        );

        return http
            .csrf(csrf -> csrf
                .csrfTokenRepository(repository)
                .csrfTokenRequestHandler(new SpaCsrfTokenRequestHandler())
            )
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

**Chú ý:**

- **withHttpOnlyFalse()** chỉ làm **cookie XSRF-TOKEN** JavaScript-readable, không tác động cookie xác thực.
- **Secure=true** dành cho HTTPS production; khi dùng HTTP development thông thường cookie có thể không được gửi. Ưu tiên HTTPS local thay vì hạ bảo mật production.
- **SameSite=Lax** giúp giảm một số trường hợp cookie cross-site, nhưng không thay thế CSRF protection và không phân biệt mọi subdomain cùng site.
- **permitAll()** ở GET cấp token không tắt CSRF cho POST; login/logout bằng cookie vẫn có thể phải gửi CSRF token.
- Với nhiều **SecurityFilterChain**, GET /api/csrf và POST được bảo vệ phải dùng repository/handler tương thích; tránh chuỗi filter này cấp token chuỗi khác không nhận.
- **formLogin** minh họa cơ chế có cookie phiên, không tự tạo JSON login API. OAuth/OIDC/JSON login phải được tích hợp theo luồng thực tế.

### 5.2. Request handler kết hợp raw header và masked form

~~~java
import java.util.function.Supplier;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import org.springframework.security.web.csrf.CsrfToken;
import org.springframework.security.web.csrf.CsrfTokenRequestAttributeHandler;
import org.springframework.security.web.csrf.CsrfTokenRequestHandler;
import org.springframework.security.web.csrf.XorCsrfTokenRequestAttributeHandler;
import org.springframework.util.StringUtils;

final class SpaCsrfTokenRequestHandler implements CsrfTokenRequestHandler {

    private final CsrfTokenRequestHandler plain =
        new CsrfTokenRequestAttributeHandler();

    private final CsrfTokenRequestHandler xor =
        new XorCsrfTokenRequestAttributeHandler();

    @Override
    public void handle(
            HttpServletRequest request,
            HttpServletResponse response,
            Supplier<CsrfToken> csrfToken) {

        // Giữ token XOR-masked ở request attribute cho HTML.
        this.xor.handle(request, response, csrfToken);

        // Hiện thực hóa deferred token để cookie mới được tạo khi cần.
        csrfToken.get();
    }

    @Override
    public String resolveCsrfTokenValue(
            HttpServletRequest request,
            CsrfToken csrfToken) {

        String header = request.getHeader(csrfToken.getHeaderName());

        // SPA gửi raw token qua header, form SSR gửi masked parameter.
        return (StringUtils.hasText(header) ? this.plain : this.xor)
            .resolveCsrfTokenValue(request, csrfToken);
    }
}
~~~

**XOR trong handle()** giúp các form HTML vẫn dùng token masked, giảm nguy cơ BREACH khi token được xuất hiện trong response nén. **Supplier.get()** buộc token được nạp/tạo, để cookie XSRF có thể được phát sau authentication/logout thay vì đợi đến request không an toàn đầu tiên.

**resolveCsrfTokenValue()** chọn plain khi header đã có giá trị, và chọn XOR khi token đến từ parameter của form. Chính sách này có chủ đích: **nó không nhận masked token JSON trong header theo đường XOR**. Nếu frontend có hai kiểu token, hãy chuẩn hóa hợp đồng thay vì đoán định dạng trong server.

### 5.3. Biến thể plain dành cho API JSON-only

~~~java
import org.springframework.security.web.csrf.CookieCsrfTokenRepository;
import org.springframework.security.web.csrf.CsrfTokenRequestAttributeHandler;

// Biến thể THAY THẾ, không chồng thêm handler kết hợp:
.csrf(csrf -> csrf
    .csrfTokenRepository(CookieCsrfTokenRepository.withHttpOnlyFalse())
    .csrfTokenRequestHandler(new CsrfTokenRequestAttributeHandler())
)
~~~

Biến thể này chấp nhận raw header; khi không render HTML chứa CSRF token thì có thể đủ phù hợp. Tuy nhiên, **nó không giữ XOR masking trên request attribute**. Nếu dùng SSR/render HTML và response có nén, phải đánh giá rủi ro BREACH; không coi opt-out masking là cấu hình mặc định áp dụng mọi dự án.

Không phải mọi GET sẽ tự tạo cookie khi dùng plain handler vì **deferred token**. Cần endpoint bootstrap chủ động đọc token.

## 6. Bootstrap token khi deferred loading

Trong Spring Security 6.x, token có thể được nạp trì hoãn. Một request **GET /dashboard** không nhất thiết phát cookie XSRF mới, kể cả khi controller đã chạy bình thường.

### 6.1. GET /api/csrf cho cookie repository

~~~java
import jakarta.servlet.http.HttpServletRequest;
import org.springframework.http.CacheControl;
import org.springframework.http.ResponseEntity;
import org.springframework.security.web.csrf.CsrfToken;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
class CsrfBootstrapController {

    @GetMapping("/api/csrf")
    ResponseEntity<Void> csrf(HttpServletRequest request) {
        CsrfToken csrfToken = (CsrfToken) request.getAttribute(
            CsrfToken.class.getName());

        if (csrfToken == null) {
            throw new IllegalStateException("CSRF filter is not active");
        }

        csrfToken.getToken();
        return ResponseEntity.noContent()
            .cacheControl(CacheControl.noStore())
            .build();
    }
}
~~~

Phản hồi khi token mới được tạo có thể có:

~~~http
HTTP/1.1 204 No Content
Cache-Control: no-store
Set-Cookie: XSRF-TOKEN=...; Path=/; Secure; SameSite=Lax
~~~

**Không kỳ vọng Set-Cookie ở mọi GET** khi cookie token đã tồn tại. Frontend cần kiểm tra cookie thực sự nằm trong phạm vi JavaScript đọc được, không chỉ nhìn HTTP status 204.

### 6.2. GET JSON cho session repository

Khi dùng HttpSessionCsrfTokenRepository, token có thể được cung cấp qua JSON, không cần tạo cookie CSRF riêng cho JavaScript.

~~~java
import jakarta.servlet.http.HttpServletRequest;
import org.springframework.http.CacheControl;
import org.springframework.http.ResponseEntity;
import org.springframework.security.web.csrf.CsrfToken;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
class SessionCsrfController {

    record CsrfPayload(String headerName, String token) {}

    @GetMapping("/api/csrf")
    ResponseEntity<CsrfPayload> csrf(HttpServletRequest request) {
        CsrfToken token = (CsrfToken) request.getAttribute(
            CsrfToken.class.getName());

        if (token == null) {
            throw new IllegalStateException("CSRF filter missing");
        }

        return ResponseEntity.ok()
            .cacheControl(CacheControl.noStore())
            .body(new CsrfPayload(
                token.getHeaderName(), token.getToken()));
    }
}
~~~

**Đây là một biến thể thay thế, không triển khai đồng thời hai controller trùng mapping GET /api/csrf.** Khi JSON nhận masked token từ XOR handler, client gửi đúng nguyên giá trị JSON qua header và backend phải giải theo XOR. Không kết hợp tùy tiện session JSON-masked với handler SPA coi mọi header là raw.

## 7. Frontend cùng origin: đọc raw XSRF cookie và gửi header

### 7.1. Đọc cookie đúng tên

~~~javascript
function readCookie(name) {
  const prefix = encodeURIComponent(name) + "=";
  const entry = document.cookie
    .split("; ")
    .find(item => item.startsWith(prefix));

  return entry
    ? decodeURIComponent(entry.slice(prefix.length))
    : null;
}
~~~

Chỉ đọc cookie **XSRF-TOKEN**. Cookie xác thực **JSESSIONID** nên giữ HttpOnly và sẽ không có trong document.cookie; browser vẫn có thể tự gửi nó.

### 7.2. Bootstrap tránh nhiều GET đồng thời

~~~javascript
let loadingXsrf = null;

async function ensureXsrfToken() {
  const current = readCookie("XSRF-TOKEN");
  if (current) return current;

  if (!loadingXsrf) {
    loadingXsrf = (async () => {
      const response = await fetch("/api/csrf", {
        method: "GET",
        credentials: "same-origin",
        cache: "no-store"
      });

      if (!response.ok) {
        throw new Error("CSRF bootstrap failed: " + response.status);
      }

      const token = readCookie("XSRF-TOKEN");
      if (!token) {
        throw new Error("XSRF cookie is missing or unreadable");
      }
      return token;
    })().finally(() => {
      loadingXsrf = null;
    });
  }

  return loadingXsrf;
}

async function updatePreferences(preferences) {
  const token = await ensureXsrfToken();

  const response = await fetch("/api/preferences", {
    method: "PATCH",
    credentials: "same-origin",
    headers: {
      "Content-Type": "application/json",
      "X-XSRF-TOKEN": token
    },
    body: JSON.stringify(preferences)
  });

  if (response.status === 403) {
    throw new Error("Forbidden: check CSRF and authorization");
  }
  if (!response.ok) {
    throw new Error("Update failed: " + response.status);
  }

  return response.status === 204 ? null : response.json();
}
~~~

Hàm Promise chung tránh nhiều component gọi bootstrap đồng thời. Một HTTP interceptor có thể thêm header XSRF cho POST/PUT/PATCH/DELETE, nhưng **chỉ gửi token đến backend đáng tin cậy**.

Không tự động retry request ghi chỉ vì 403. Lỗi có thể do thiếu quyền, và request có side effect cần chính sách retry/idempotency rõ ràng.

### 7.3. Sau login/logout

Trong Servlet, **CsrfAuthenticationStrategy** và **CsrfLogoutHandler** có thể xóa token cũ. Luồng cần kiểm chứng:

~~~text
GET /api/csrf ở trạng thái anonymous → token A
POST /login kèm token A → đăng nhập thành công
GET /api/csrf với cookie phiên mới → token B
POST /api/preferences kèm token B
POST /logout kèm token B → logout thành công
GET /api/csrf ở trạng thái anonymous mới → token C nếu cần
~~~

**POST login cần token trước login; POST logout cần token hiện hành trước logout.** Chỉ sau khi backend xác nhận sự kiện thành công, frontend mới bỏ token cũ và bootstrap token phù hợp với trạng thái mới. Không suy luận auth success chỉ từ response 200 sau redirect.

## 8. Reactive/WebFlux: repository và handler có API riêng

WebFlux sử dụng **ServerHttpSecurity**, **SecurityWebFilterChain**, **CsrfWebFilter**, **ServerCsrfTokenRepository** và **ServerCsrfTokenRequestHandler**; không sử dụng trực tiếp HttpSecurity/HttpServletRequest của Servlet.

| Khái niệm | Servlet | WebFlux |
| --- | --- | --- |
| Security chain | SecurityFilterChain | SecurityWebFilterChain |
| Cookie repository | CookieCsrfTokenRepository | CookieServerCsrfTokenRepository |
| Session repository | HttpSessionCsrfTokenRepository | WebSessionServerCsrfTokenRepository |
| Plain handler | CsrfTokenRequestAttributeHandler | ServerCsrfTokenRequestAttributeHandler |
| XOR handler | XorCsrfTokenRequestAttributeHandler | XorServerCsrfTokenRequestAttributeHandler |
| Request context | HttpServletRequest | ServerWebExchange |
| Deferred token | Supplier/CsrfToken | Mono<CsrfToken> |
| Testing | MockMvc | WebTestClient |

Theo hướng dẫn Spring Security Reactive, **5.8 dùng ServerCsrfTokenRequestAttributeHandler làm mặc định**, còn từ **6.0** mặc định là **XorServerCsrfTokenRequestAttributeHandler** nhằm bảo vệ token khi xuất hiện trong response. Vì vậy WebFlux cũng cần phân biệt cookie raw với token masked.

### 8.1. WebFlux JSON-only dùng cookie CSRF raw

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.web.server.SecurityWebFilterChain;
import org.springframework.security.web.server.csrf.CookieServerCsrfTokenRepository;
import org.springframework.security.web.server.csrf.ServerCsrfTokenRequestAttributeHandler;

@Bean
SecurityWebFilterChain securityWebFilterChain(ServerHttpSecurity http) {
    return http
        .csrf(csrf -> csrf
            .csrfTokenRepository(
                CookieServerCsrfTokenRepository.withHttpOnlyFalse())
            .csrfTokenRequestHandler(
                new ServerCsrfTokenRequestAttributeHandler())
        )
        .authorizeExchange(auth -> auth
            .pathMatchers(HttpMethod.GET, "/api/csrf").permitAll()
            .pathMatchers("/api/**").authenticated()
            .anyExchange().permitAll()
        )
        .build();
}
~~~

Đây là **biến thể plain/raw cho JSON-only SPA**. Khi dùng SSR/form HTML cần masked token, hãy dùng handler kết hợp thay vì đơn giản tắt XOR masking.

### 8.2. Handler kết hợp của WebFlux

Các interface Reactive cho phép viết handler phục vụ cả raw header và XOR parameter:

~~~java
import org.springframework.security.web.server.csrf.CsrfToken;
import org.springframework.security.web.server.csrf.ServerCsrfTokenRequestAttributeHandler;
import org.springframework.security.web.server.csrf.ServerCsrfTokenRequestHandler;
import org.springframework.security.web.server.csrf.XorServerCsrfTokenRequestAttributeHandler;
import org.springframework.util.StringUtils;
import org.springframework.web.server.ServerWebExchange;
import reactor.core.publisher.Mono;

final class ReactiveSpaCsrfTokenRequestHandler
        implements ServerCsrfTokenRequestHandler {

    private final ServerCsrfTokenRequestHandler plain =
        new ServerCsrfTokenRequestAttributeHandler();

    private final ServerCsrfTokenRequestHandler xor =
        new XorServerCsrfTokenRequestAttributeHandler();

    @Override
    public void handle(
            ServerWebExchange exchange,
            Mono<CsrfToken> csrfToken) {
        // Giữ masked token cho HTML/view.
        this.xor.handle(exchange, csrfToken);
    }

    @Override
    public Mono<String> resolveCsrfTokenValue(
            ServerWebExchange exchange,
            CsrfToken csrfToken) {

        String header = exchange.getRequest().getHeaders()
            .getFirst(csrfToken.getHeaderName());

        return (StringUtils.hasText(header) ? this.plain : this.xor)
            .resolveCsrfTokenValue(exchange, csrfToken);
    }
}
~~~

Thay **new ServerCsrfTokenRequestAttributeHandler()** trong cấu hình 8.1 bằng **new ReactiveSpaCsrfTokenRequestHandler()** nếu muốn hai nhánh. Mẫu này **không tự subscribe Mono trong handle()**; muốn hiện thực hóa token, hãy dùng endpoint bootstrap dưới đây.

**Không gọi block() hoặc subscribe() tùy tiện trong filter/handler** để cưỡng ép token; điều đó có thể tạo side effect ngoài chuỗi xử lý Reactive. Kiểm thử các API của phiên bản WebFlux dự án đang dùng trước khi tích hợp.

### 8.3. GET /api/csrf trong WebFlux

~~~java
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
    Mono<ResponseEntity<Void>> csrf(ServerWebExchange exchange) {
        Mono<CsrfToken> tokenMono =
            exchange.getAttribute(CsrfToken.class.getName());

        if (tokenMono == null) {
            return Mono.error(
                new IllegalStateException("CSRF filter missing"));
        }

        return tokenMono.map(token -> {
            token.getToken();
            return ResponseEntity.noContent()
                .cacheControl(CacheControl.noStore())
                .build();
        });
    }
}
~~~

Mono được subscribe trong pipeline trả response thì repository có cơ hội nạp/tạo token, từ đó phát cookie XSRF khi cần. **Không block() trong controller WebFlux.** Cookie không nhất thiết được phát lại khi đã có token hợp lệ.

Trong WebFlux, authentication/logout và WebSession có cơ chế riêng; không tự giả định các class Servlet như CsrfAuthenticationStrategy hoặc CsrfLogoutHandler chạy nguyên xi trên WebFlux. Kiểm thử token sau auth transition theo phiên bản/luồng thật.

## 9. SPA khác origin: CORS và cookie scope

Giả sử SPA ở **https://app.example.com**, API ở **https://api.example.com**. Hai địa chỉ khác origin dù có thể cùng site. Cookie **host-only** XSRF-TOKEN do api.example.com cấp **không được JavaScript tại app.example.com đọc qua document.cookie**.

**credentials: include** giúp browser gửi cookie trong fetch khác origin khi policy cho phép, **không cấp quyền đọc cookie host-only của host khác**. CORS cũng không thay đổi phạm vi document.cookie.

### 9.1. Chọn kiến trúc

| Hướng | Điểm mạnh | Rủi ro cần xử lý |
| --- | --- | --- |
| SPA và API chung origin qua BFF/reverse proxy | Cookie host-only và header raw đơn giản hơn | Bảo vệ ranh giới browser-BFF |
| GET /api/csrf trả token JSON qua CORS | SPA khác origin có thể đọc body response | Token JSON raw/masked và handler phải khớp |
| Domain cookie chia sẻ các subdomain | Có thể đọc cookie từ nhiều subdomain | Cookie injection, subdomain không đáng tin, scope rộng |

Khi chọn JSON, cần **JSON masked + XOR handler** hoặc **JSON raw + plain handler**, không sử dụng handler SPA coi mọi header raw nếu response JSON lại chứa masked token.

### 9.2. Servlet CORS allowlist cho CSRF header

~~~java
import java.util.List;
import org.springframework.context.annotation.Bean;
import org.springframework.web.cors.CorsConfiguration;
import org.springframework.web.cors.CorsConfigurationSource;
import org.springframework.web.cors.UrlBasedCorsConfigurationSource;

@Bean
CorsConfigurationSource corsConfigurationSource() {
    CorsConfiguration cors = new CorsConfiguration();
    cors.setAllowedOrigins(List.of("https://app.example.com"));
    cors.setAllowedMethods(List.of(
        "GET", "POST", "PUT", "PATCH", "DELETE"));
    cors.setAllowedHeaders(List.of(
        "Content-Type", "X-XSRF-TOKEN", "X-CSRF-TOKEN"));
    cors.setAllowCredentials(true);

    UrlBasedCorsConfigurationSource source =
        new UrlBasedCorsConfigurationSource();
    source.registerCorsConfiguration("/api/**", cors);
    return source;
}
~~~

Thêm **cors(Customizer.withDefaults())** vào HttpSecurity và sử dụng CORS Reactive tương ứng nếu dự án là WebFlux. Header tùy biến khác origin thường cần **OPTIONS preflight**; hãy cho phép origin, method và header cụ thể. Không phản chiếu mọi Origin kèm credentials và không dùng wildcard.

### 9.3. JSON bootstrap cross-origin

~~~javascript
const API = "https://api.example.com";

async function loadCsrfFromJson() {
  const response = await fetch(API + "/api/csrf", {
    credentials: "include",
    cache: "no-store"
  });
  if (!response.ok) throw new Error("CSRF bootstrap failed");
  return response.json();
}

async function createOrder(order) {
  const csrf = await loadCsrfFromJson();

  return fetch(API + "/api/orders", {
    method: "POST",
    credentials: "include",
    headers: {
      "Content-Type": "application/json",
      [csrf.headerName]: csrf.token
    },
    body: JSON.stringify(order)
  });
}
~~~

Ví dụ này đòi endpoint **GET JSON thực sự tồn tại** và request handler backend hiểu đúng định dạng token mà GET trả về. Browser vẫn áp dụng Secure, SameSite, Domain/Path, Fetch credentials và third-party cookie policy. CORS đúng **không tự buộc browser lưu cookie**.

## 10. Cookie security, XSS và phòng vệ HTTP bổ sung

| Cơ chế | Vai trò | Giới hạn |
| --- | --- | --- |
| **HttpOnly** | Giảm script đọc cookie xác thực | Browser vẫn tự gửi cookie, không tự chống CSRF |
| **Secure, HTTPS/HSTS** | Bảo vệ vận chuyển token/cookie | Không chứng minh ý định của request |
| **SameSite** | Hạn chế nhiều bối cảnh cross-site | Không coi mọi subdomain cùng site là đáng tin |
| **Domain/Path** | Phạm vi cookie được đọc/gửi | Không phải cách chống XSS cùng origin |
| **CORS** | Kiểm soát response và preflight cross-origin | Không thay CsrfFilter |
| **CSP/output encoding** | Giảm XSS | CSRF token không chống mã độc chạy cùng origin |
| **HTTP firewall** | Chặn request HTTP bất thường | Không đối chiếu CSRF token |
| **Authentication/authorization** | Kiểm tra danh tính, quyền | CSRF token đúng không cấp thêm quyền |
| **Cache-Control: no-store** | Giảm cache response chứa token | Không thay cookie policy |

### 10.1. XSS

Khi XSRF cookie được cho JavaScript đọc, một đoạn script XSS chạy cùng origin có thể đọc token và gọi API với cookie session HttpOnly do browser tự gửi. Do đó phải chống XSS bằng encoding, CSP, kiểm soát DOM và giới hạn script không đáng tin; không coi cookie HttpOnly hoặc XOR masking là thuốc chữa XSS.

### 10.2. Cookie injection và double-submit

CookieCsrfTokenRepository không mặc định tạo **signed double-submit** có HMAC ràng buộc token với session. Nếu Domain cookie rộng và subdomain không tin cậy có khả năng đặt cookie, cần xem xét cookie injection và trùng cookie.

Ưu tiên cookie host-only, HTTPS/HSTS, quản lý subdomain, tiền tố **__Host-** khi đáp ứng Secure/Path=/ và không có Domain, hoặc cơ chế signed double-submit/synchronizer-token phù hợp. XOR masking là kỹ thuật giảm BREACH, không phải HMAC.

### 10.3. Stateless không tự bỏ CSRF

API nhận JWT từ **cookie** vẫn có browser-managed credential, nên phải đánh giá CSRF cho request có tác động. API chỉ nhận **Authorization: Bearer** do JavaScript chủ động gắn, không có cookie/Basic/SSO fallback, thường có mô hình CSRF khác. Đừng bật cookie repository chỉ vì frontend tên là SPA, cũng đừng tắt CSRF chỉ vì backend stateless.

## 11. MockMvc: xác minh repository và request handler Servlet

Mục tiêu kiểm thử không phải chỉ thấy cookie XSRF trong browser, mà là **chứng minh CSRF filter từ chối request không hợp lệ trước khi nghiệp vụ thay đổi dữ liệu**. Cần tách kiểm thử raw header với kiểm thử masked form parameter.

### 11.1. Cookie không thay thế header

Giả định SecurityFilterChain và CsrfBootstrapController của phần 5–6 đã được dùng, có POST **/api/preferences** nhận JSON trả 2xx khi hợp lệ, và dependency **spring-security-test**.

~~~java
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.user;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import jakarta.servlet.http.Cookie;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;

@SpringBootTest
@AutoConfigureMockMvc
class CookieCsrfIntegrationTests {

    @Autowired MockMvc mvc;

    @Test
    void rawHeaderMustMatchCookie() throws Exception {
        MvcResult result = mvc.perform(get("/api/csrf"))
            .andExpect(status().isNoContent())
            .andReturn();

        Cookie xsrf = result.getResponse().getCookie("XSRF-TOKEN");
        assertNotNull(xsrf, "CSRF bootstrap should issue XSRF cookie");
        assertFalse(xsrf.isHttpOnly(), "SPA needs to read XSRF cookie");

        mvc.perform(post("/api/preferences")
                .with(user("alice"))
                .cookie(xsrf)
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"notifications\":true}"))
            .andExpect(status().isForbidden());

        mvc.perform(post("/api/preferences")
                .with(user("alice"))
                .cookie(xsrf)
                .header("X-XSRF-TOKEN", "invalid")
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"notifications\":true}"))
            .andExpect(status().isForbidden());

        mvc.perform(post("/api/preferences")
                .with(user("alice"))
                .cookie(xsrf)
                .header("X-XSRF-TOKEN", xsrf.getValue())
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"notifications\":true}"))
            .andExpect(status().is2xxSuccessful());
    }
}
~~~

**Giới hạn:** Đây là ví dụ trong một Spring Boot 3 Servlet application với security filters gắn vào MockMvc. **user("alice")** là helper giả lập principal, **không kiểm chứng form login và session cookie thật**. POST endpoint phải tồn tại và có quyền tương ứng; trạng thái 2xx chỉ đúng trong ngữ cảnh đó. GET bootstrap lần đầu được giả định phát cookie; nếu token đã tồn tại, cần dùng cookie jar thay vì đòi Set-Cookie ở mọi GET.

Cần assert **dữ liệu không thay đổi** trong hai request 403. Chỉ kiểm tra status code sẽ bỏ sót side effect xảy ra trước khi bị chặn.

### 11.2. Test form với token XOR-masked

Khi ứng dụng còn Thymeleaf/JSP:

~~~http
POST /account/preferences HTTP/1.1
Host: app.example.com
Cookie: JSESSIONID=...; XSRF-TOKEN=raw-T
Content-Type: application/x-www-form-urlencoded

_csrf=masked-token-from-GET&notifications=true
~~~

Hãy lấy masked token trong form HTML do server render, gửi POST giữ cookie cùng ngữ cảnh **và không gắn X-XSRF-TOKEN**. Handler kết hợp sẽ chọn XOR để khôi phục raw token. Gửi parameter sai phải bị từ chối. Nếu một interceptor lại gắn header raw không khớp, handler có thể ưu tiên header và bỏ qua form parameter đúng — đây là tình huống cần test.

Không đòi chuỗi masked từ hai GET giống nhau: randomness để giảm BREACH có thể khiến chúng khác, dù raw token không thay đổi.

### 11.3. Test session repository nhận token JSON

Với HttpSessionCsrfTokenRepository:

~~~text
GET /api/csrf trả JSON {headerName, token}, lưu cùng JSESSIONID
POST /api/preferences không header → 403
POST cùng JSESSIONID và token JSON → vượt CSRF
POST token cũ nhưng JSESSIONID khác → không được chấp nhận
~~~

Nếu JSON trả masked token, backend phải dùng XOR handler; **không dùng handler SPA luôn giải header theo đường plain** mà không đổi contract. Với logout/login thật, xác minh token đã được xóa/tái cấp theo strategy thực tế.

## 12. WebTestClient và kiểm thử browser

### 12.1. Kiểm thử CsrfWebFilter

~~~java
import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.csrf;
import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.mockUser;

// Đoạn thân test; cần WebTestClient đã gắn Spring Security.
webTestClient.mutateWith(mockUser("alice"))
    .post().uri("/api/preferences")
    .bodyValue(Map.of("notifications", true))
    .exchange()
    .expectStatus().isForbidden();

webTestClient.mutateWith(mockUser("alice")).mutateWith(csrf())
    .post().uri("/api/preferences")
    .bodyValue(Map.of("notifications", true))
    .exchange()
    .expectStatus().is2xxSuccessful();
~~~

Đoạn thân test cần import **java.util.Map**, instance WebTestClient và controller POST có thật. Helper **csrf()** chỉ mô phỏng token hợp lệ; nó không kiểm tra repository cookie thực tế. Để test đường dữ liệu, GET /api/csrf bằng client giữ cookie jar, đọc XSRF-TOKEN, sau đó POST cùng cookie và raw header. Thử header thiếu/sai, sau login/logout, cùng form masked nếu có.

### 12.2. Kịch bản kiểm thử browser

1. Mở DevTools **Application/Storage → Cookies**; cookie XSRF JavaScript-readable, cookie JSESSIONID HttpOnly.
2. Xem GET bootstrap có 204 hoặc JSON như contract, **Cache-Control: no-store**, và Set-Cookie khi cấp token mới.
3. Xem POST thực tế có Cookie và custom header X-XSRF-TOKEN, không chỉ cookie.
4. Bỏ hoặc đổi header trong môi trường kiểm thử: request bị từ chối, không có dữ liệu bị sửa.
5. Đăng nhập/đăng xuất, timeout phiên và mở nhiều tab: token mới được lấy khi cần; token cũ không được tự động retry.
6. Với SPA khác origin, kiểm tra OPTIONS preflight, Access-Control-Allow-Origin và cookie policy trong browser. Curl/Postman không mô phỏng đầy đủ SameSite/CORS.

## 13. Ma trận hành vi và chẩn đoán

| Tình huống | Kỳ vọng |
| --- | --- |
| Dùng Spring Security 6.x, không có csrf.spa() | Cấu hình repository + handler thủ công, không tắt CSRF |
| Dùng source Jakarta với Boot 2/Security 5.8 | Cần kiểm tra namespace javax/API phiên bản |
| GET không đọc deferred token | Có thể chưa phát XSRF cookie |
| GET bootstrap đọc CsrfToken.getToken() | Token được materialize và cookie có thể được tạo |
| POST chỉ có cookie session và cookie XSRF | Bị CSRF chặn vì thiếu actual header/parameter |
| POST có header raw sai | Bị chặn; dữ liệu không đổi |
| POST có raw header đúng, cookie và quyền hợp lệ | Qua CsrfFilter, controller được phép xử lý |
| POST có CSRF token đúng nhưng không login | Vẫn bị authentication/authorization chặn |
| Form có masked parameter đúng, không raw header | Handler kết hợp dùng XOR |
| JSON masked gửi vào handler coi header là raw | Lỗi contract; không mặc định chấp nhận |
| GET token/POST đi qua hai SecurityFilterChain khác nhau | Cần thống nhất repository/handler |
| SPA khác subdomain đọc host-only cookie API | Không thể qua document.cookie |
| CORS preflight custom header thất bại | Cần allowlist origin/method/header phù hợp |
| Login/logout làm token cũ mất hiệu lực | Bootstrap lại token đúng phiên |
| XSS cùng origin | CSRF token không thay chống XSS |
| Cookie Domain rộng với subdomain không tin cậy | Đánh giá cookie injection/signed double-submit |

### 13.1. Quy trình chẩn đoán lỗi 403

~~~mermaid
flowchart TD
    A["POST bị 403"] --> B{"Có CSRF header hoặc parameter?"}
    B -->|Không| C["Client quên token"]
    B -->|Có| D{"Cookie hoặc session GET và POST có khớp?"}
    D -->|Không| E["Kiểm tra SameSite, Secure, credentials, Domain/Path"]
    D -->|Có| F{"Raw hay masked đúng handler?"}
    F -->|Không| G["Sửa contract repository-handler-client"]
    F -->|Có| H{"Token cũ sau login/logout?"}
    H -->|Có| I["Lấy token mới"]
    H -->|Không| J["Kiểm tra authorization, chain và error handler"]
~~~

**403 không luôn là lỗi CSRF.** Cần phân biệt MissingCsrfTokenException, InvalidCsrfTokenException, AccessDeniedException và lỗi xác thực/role. Không log nguyên token hoặc session ID khi chẩn đoán.

### 13.2. Những lỗi phổ biến

**Cookie có nhưng POST vẫn 403:** Header có thật sự được frontend gửi? Handler mặc định XOR có đang cố giải raw token? Token có cũ sau login/logout hoặc repository bị thay ở chain khác không?

**GET thành công nhưng XSRF cookie chưa được tạo:** Deferred token chưa được materialize, repository không phải cookie hoặc cookie bị browser chặn bởi Secure/Domain/Path.

**Form có token khác cookie:** Form có thể chứa masked representation, không cần giống raw cookie.

**SPA khác origin không đọc được cookie API:** Cookie host-only không vượt ranh giới hostname; CORS không sửa quyền document.cookie. Dùng JSON endpoint hoặc BFF cùng origin.

**Dùng class Servlet trong WebFlux bị lỗi type:** Phải dùng ServerHttpSecurity/ServerWebExchange/Mono và các handler Reactive.

**Token hợp lệ nhưng vẫn 403:** Xem role, authentication, security chain và business authorization; CSRF không cấp quyền.

## 14. Bài tập thực hành

**Bài A — Hai repository:** Tạo biến thể session repo + JSON token và biến thể cookie repo + raw header. So sánh cookie, session state và hành vi sau timeout.

**Bài B — Raw vs XOR:** Gửi raw token cookie vào XOR handler mặc định trên 6.x, quan sát lỗi, sau đó dùng handler kết hợp và test lại.

**Bài C — Form SSR + SPA:** Cùng chain, cho form gửi masked parameter và SPA gửi raw header. Test hai đường và trường hợp token sai.

**Bài D — Deferred token:** So sánh GET 204 không đọc token với GET bootstrap có getToken(), kiểm tra cookie thực tế.

**Bài E — Login/logout:** Lấy token anonymous, login thật, bootstrap lại; logout bằng token hiện hành rồi lấy token anonymous mới nếu cần.

**Bài F — Cross-origin:** SPA ở app.example.com, API ở api.example.com; kiểm tra cookie host-only, CORS, credentials include và JSON-token contract.

**Bài G — Reactive:** Dùng CookieServerCsrfTokenRepository và handler plain, sau đó handler kết hợp nếu có HTML; WebTestClient GET bootstrap và POST thực tế.

**Bài H — Cookie injection:** Kiểm tra cấu hình Domain rộng và subdomain không tin cậy trong môi trường test; đánh giá host-only và signed double-submit phù hợp.

## 15. Nguyên tắc cần nhớ

1. **Repository lưu expected token; request handler trình bày và đọc actual token; CsrfFilter so khớp.**
2. **Spring Security 6.x không có csrf.spa().** Tích hợp SPA cookie cần repository + handler thủ công.
3. **Raw XSRF cookie → raw X-XSRF-TOKEN header**; form SSR có thể sử dụng masked parameter.
4. **Hybrid handler** giữ XOR cho HTML và plain cho raw header, nhưng không tùy tiện nhận masked JSON qua raw-header path.
5. **Deferred token phải được materialize** khi SPA bootstrap và sau login/logout.
6. **Session repo và cookie repo có hợp đồng frontend khác nhau**, không yêu cầu JavaScript đọc session cookie.
7. **WebFlux dùng Server... API và Mono**, không copy HttpServletRequest handler.
8. **CORS, SameSite, CSP, HSTS, cookie scope và HTTP firewall** bổ sung bảo vệ nhưng không thay CsrfFilter.
9. **Token CSRF không cấp quyền**; vẫn kiểm tra authentication, authorization và input.
10. **Kiểm thử request thực và side effects**: thiếu/sai/đúng token, login/logout, raw/XOR, cookie khác origin và session timeout.

**Kết luận:** Trên các dòng Spring Security trước khi có preset SPA, cấu hình đúng không nằm ở số dòng code mà ở **sự nhất quán giữa repository, request handler, nguồn token của frontend và CsrfFilter**. Đối với Servlet 6.x, CookieCsrfTokenRepository với handler kết hợp là một mô hình thực tế cho SPA đọc raw cookie mà vẫn bảo vệ form HTML bằng XOR; WebFlux cần các class Reactive tương ứng.

## Tài liệu tham khảo chính thức

- [Spring Security 6.5 — CSRF Servlet, repository, request handler và SPA](https://docs.spring.io/spring-security/reference/6.5/servlet/exploits/csrf.html)
- [Spring Security 6.5 — CookieCsrfTokenRepository JavaDoc](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/web/csrf/CookieCsrfTokenRepository.html)
- [Spring Security 6.5 — CsrfTokenRequestHandler JavaDoc](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/web/csrf/CsrfTokenRequestHandler.html)
- [Spring Security 6.5 — CSRF Reactive/WebFlux](https://docs.spring.io/spring-security/reference/6.5/reactive/exploits/csrf.html)
- [Spring Security 6.5 — ServerCsrfTokenRequestAttributeHandler JavaDoc](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/web/server/csrf/ServerCsrfTokenRequestAttributeHandler.html)
- [Spring Security 7.0 — CsrfConfigurer JavaDoc, spa() xuất hiện từ 7.0](https://docs.spring.io/spring-security/reference/7.0/api/java/org/springframework/security/config/annotation/web/configurers/CsrfConfigurer.html)



