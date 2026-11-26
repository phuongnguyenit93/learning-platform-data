# CsrfConfigurer.spa() trên dòng phiên bản có hỗ trợ

## Mục tiêu và phạm vi

Trong chương **CSRF cho SPA và API** của module **SPRING_SECURITY_HTTP_PROTECTION**, việc tích hợp Single-Page Application (SPA) với Spring Security dễ gặp ba vấn đề cùng lúc: JavaScript đọc **CSRF token gốc từ cookie**, request handler mặc định có thể sử dụng **XOR masking** để giảm rủi ro BREACH, và token cũ có thể bị xóa khi **đăng nhập hoặc đăng xuất**.

Từ **Spring Security 7.0**, cấu hình **Servlet** cung cấp phương thức tiện ích **CsrfConfigurer.spa()**, được gọi qua **HttpSecurity.csrf(...)**, để thiết lập một bộ mặc định phù hợp hơn cho SPA. Đây **không phải API có thể dùng ở mọi phiên bản Spring Security**, cũng không phải một phương thức chung có cùng chữ ký trên **ServerHttpSecurity** của WebFlux.

Bài học giải thích mục đích và giới hạn của preset này, cách viết cấu hình đúng trên dòng phiên bản hỗ trợ, cách triển khai tương đương trên Spring Security 6.x, cách đồng bộ frontend và thiết kế kiểm thử cho cả **Servlet** lẫn **Reactive**. Các nội dung liên quan gồm CORS, SameSite, security headers, CSP, HSTS, HTTP firewall, CSRF token rotation và bảo vệ session.

Sau bài học, người học có thể:

1. Xác định được phiên bản có **CsrfConfigurer.spa()** và không cố dùng lời gọi này trên 6.x.
2. Hiểu preset cấu hình repository cookie và request handler cho SPA, nhưng **không tự cấu hình authentication, CORS hoặc phân quyền**.
3. Phân biệt giá trị **raw XSRF-TOKEN** với biểu diễn **XOR-masked** được xuất qua request attribute.
4. Cấu hình Spring Security 7.x Servlet bằng **csrf.spa()** và cấu hình tương đương thủ công cho 6.x.
5. Tạo luồng frontend **GET bootstrap → đọc cookie → X-XSRF-TOKEN header** và đồng bộ token sau login/logout.
6. Biết lúc nào **không** dùng preset: API Bearer-only, cơ chế CSRF JSON-masked riêng, cookie cross-origin không thể đọc và ứng dụng WebFlux.
7. Viết kiểm thử chứng minh POST thiếu/sai token bị chặn, raw header đúng hoạt động, còn phiên/role vẫn được kiểm tra độc lập.

## 1. Ma trận phiên bản: có spa() ở đâu?

**CsrfConfigurer.spa() là một bổ sung từ Spring Security 7.0.** JavaDoc của chính phương thức đánh dấu **Since: 7.0**. Trong Spring Security 6.5, cấu hình tương đương phải được viết bằng **CookieCsrfTokenRepository** và một **CsrfTokenRequestHandler** phù hợp, thay vì gọi phương thức không có trong API.

| Stack / dòng phiên bản | Có thể gọi csrf.spa()? | Hướng triển khai |
| --- | --- | --- |
| **Spring Security 7.0+ — Servlet HttpSecurity** | **Có**, theo API CsrfConfigurer.spa() | Dùng **.csrf(csrf -> csrf.spa())** |
| **Spring Security 6.5 / 6.x — Servlet HttpSecurity** | **Không có phương thức này** | Cấu hình cookie repository + SPA request handler thủ công |
| **Spring Security 7.x — Reactive ServerHttpSecurity** | **Không dùng API Servlet CsrfConfigurer.spa()** | Cấu hình CSRF WebFlux bằng các class **Server...** riêng |
| **API không có browser-managed credentials, chỉ Bearer header** | API có thể tồn tại nhưng preset không phải giải pháp mặc định phù hợp | Đánh giá CSRF theo đường xác thực, không tự bật preset do tên SPA |

**Đừng nhầm phiên bản Spring Boot với phiên bản Spring Security.** Dự án có thể quản lý dependency bằng Spring Boot BOM hoặc cấu hình độc lập. Khi dùng một ví dụ, hãy kiểm tra **phiên bản spring-security-config đang được resolve thật sự**, không dựa vào tên IDE hoặc bài viết trên Internet.

Cách kiểm tra dependency trong một dự án (lệnh dành để người học tự chạy, không phải bước bắt buộc của bài):

~~~bash
# Maven (một số dự án dùng Maven Wrapper):
./mvnw dependency:tree -Dincludes=org.springframework.security:spring-security-config

# Gradle:
./gradlew dependencyInsight --dependency spring-security-config --configuration runtimeClasspath
~~~

Trong IDE có thể xem JavaDoc của **org.springframework.security.config.annotation.web.configurers.CsrfConfigurer**. Nếu ở phiên bản 6.x **không thấy spa()**, đó là giới hạn API của phiên bản, không phải lỗi import Kotlin/Java hay một option phải bật thêm.

### 1.1. Kết luận nhanh khi thấy lỗi biên dịch

~~~text
Cannot resolve method 'spa' in 'CsrfConfigurer'
~~~

Hãy kiểm tra dependency version. Không sửa bằng cách bỏ CSRF, tự thêm một phương thức extension thiếu kiểm chứng hay mix jar Spring Security 6 và 7. Hai hướng đúng là **dùng phiên bản thực sự hỗ trợ** nếu dự án đã có kế hoạch nâng cấp và tương thích, hoặc **giữ phiên bản hiện tại và cấu hình tương đương thủ công**.

## 2. Vì sao SPA cần một cấu hình riêng?

Với API dùng cookie phiên hoặc cookie JWT để xác thực, browser có thể tự gắn cookie vào request đã đăng nhập. CSRF khai thác sự khác nhau giữa request **mang credential hợp lệ** và request **do người dùng chủ ý thực hiện**.

Spring Security có thể yêu cầu token cho phương thức không an toàn. Frontend thường triển khai:

~~~http
POST /api/preferences HTTP/1.1
Host: app.example.com
Cookie: JSESSIONID=...; XSRF-TOKEN=raw-value
X-XSRF-TOKEN: raw-value
Content-Type: application/json

{"notifications":true}
~~~

Trong mô hình này:

- **JSESSIONID** hoặc cookie xác thực khác cho biết danh tính/phiên, browser tự gửi; cookie xác thực nên giữ **HttpOnly**.
- **XSRF-TOKEN** là cookie CSRF do server cấp. Khi SPA cần tự đọc cookie, cookie này phải **JavaScript-readable**, thường bằng **HttpOnly=false**.
- **X-XSRF-TOKEN** là header do JavaScript chủ động gắn bằng giá trị raw đọc từ cookie.
- **CsrfFilter** so khớp giá trị client gửi với token từ repository, rồi mới cho nghiệp vụ tiếp tục khi hợp lệ.

Một trang tấn công có thể kích hoạt form POST có cookie được browser tự gửi, nhưng không tùy tiện đọc được cookie CSRF host-only của ứng dụng hoặc gắn một custom header đã biết token. Vì vậy **chỉ có cookie CSRF** trong request không được coi là bằng chứng đủ. Spring Security cần **header hoặc form parameter** hợp lệ.

### 2.1. Vấn đề XOR masking và BREACH

Từ Spring Security 6, request handler mặc định Servlet thường sử dụng **XorCsrfTokenRequestAttributeHandler**. Khi đưa CSRF token ra request attribute để nhúng vào HTML, handler có thể **mask** giá trị bằng ngẫu nhiên nhằm giảm một dạng rò rỉ qua response compression (BREACH).

Có hai đường giá trị:

| Vị trí | Định dạng cần hiểu |
| --- | --- |
| Cookie **XSRF-TOKEN** | **Raw token** lưu bởi repository |
| JavaScript đọc **document.cookie** | **Raw token** |
| Header **X-XSRF-TOKEN** của SPA | **Raw token** nếu frontend lấy từ cookie |
| Token trong request attribute/template | Có thể là **XOR-masked token** |
| Form parameter do template phát | Có thể là **masked token** cần XOR handler giải mã |

Nếu request handler cố giải mã **raw header** như token đã XOR-mask, POST có thể nhận **403 InvalidCsrfTokenException**, dù hai chuỗi cookie và header trông giống nhau.

Preset SPA của Spring Security 7 hướng đến việc kết hợp cả hai đường: **raw header từ SPA** và **masked token được trình bày cho HTML**.

### 2.2. Token có thể bị xóa sau login/logout

Trên Servlet, **CsrfAuthenticationStrategy** và **CsrfLogoutHandler** có thể xóa token hiện hành khi login hoặc logout thành công. Cookie XSRF cũ có thể bị xóa/hết hạn; token mới không nhất thiết xuất hiện ngay trong cùng response xác thực.

SPA nên có luồng **GET token/bootstrap mới sau sự kiện xác thực** trước khi gửi POST tiếp theo. Preset **spa()** giúp thiết lập cơ chế token phù hợp với SPA nhưng **không thay client quản lý trạng thái login/logout**, không tự viết UI retry hoặc đồng bộ các tab.

## 3. CsrfConfigurer.spa() thực sự làm gì?

Theo JavaDoc của **CsrfConfigurer.spa()** trên dòng 7.x, phương thức này cấu hình:

- **CookieCsrfTokenRepository.withHttpOnlyFalse()** — lưu token trong cookie phù hợp cho JavaScript đọc;
- một **SPA-specific CsrfTokenRequestHandler** — nhận giá trị token thực tế từ header thay vì luôn giả định nó là biểu diễn encoded/masked;
- trả lại chính **CsrfConfigurer** để tiếp tục chain cấu hình nếu cần.

Triển khai trên nhánh Spring Security 7 có handler phối hợp **CsrfTokenRequestAttributeHandler** (plain) và **XorCsrfTokenRequestAttributeHandler** (XOR). Giá trị từ header được giải theo đường plain; token không đến từ header có thể đi qua đường XOR. Handler SPA tích hợp cũng điều chỉnh cách nạp deferred token để cookie được cung cấp phù hợp cho luồng SPA.

Điều rất quan trọng: **CsrfConfigurer.spa() không phải là một class public tên SpaCsrfTokenRequestHandler để người học tự import từ mọi phiên bản.** Trong triển khai 7.x được đối chiếu, handler dùng nội bộ bởi CsrfConfigurer. Với 6.x, bạn viết class tùy chỉnh riêng; không cố import một class private của 7.x.

### 3.1. Những gì spa() không làm

| Tác vụ | spa() xử lý? | Cần ai làm? |
| --- | --- | --- |
| Chọn cookie CSRF repo và request handler cho SPA Servlet | **Có** | Preset của Spring Security 7 |
| Giữ CsrfFilter để xác minh POST/PATCH/DELETE | **Có**, trong cấu hình CSRF thông thường | Spring Security filter chain |
| Tạo tài khoản, login và đăng xuất | **Không** | Authentication và logout configuration |
| Cấp quyền truy cập endpoint hoặc role | **Không** | Authorization rules |
| Tự động cấu hình allowlist CORS | **Không** | CORS của Servlet và browser policy |
| Tự biến host-only cookie API thành cookie đọc được từ subdomain SPA | **Không** | Thiết kế origin, cookie scope hoặc endpoint JSON |
| Đồng bộ token sau login/logout ở JavaScript | **Không** | SPA state/service và bootstrap |
| Chống XSS, cookie injection và mọi BREACH variant | **Không** | Phòng vệ nhiều lớp, CSP, HTTPS, cookie policy |
| Thay đổi đường xác thực Bearer-only thành cookie session | **Không** | Thiết kế authentication |
| Áp dụng trực tiếp sang WebFlux | **Không** | ServerHttpSecurity/Reactive handlers riêng |

**Bật preset không có nghĩa có thể bỏ đánh giá threat model.** Nếu backend nhận cookie xác thực, CSRF cần được bảo vệ; nếu backend chỉ nhận Bearer header do JS chủ động gửi, đánh giá có thể khác.

## 4. Cấu hình Servlet Spring Security 7.x tối giản

Trên **Spring Security 7.0+**, HttpSecurity hỗ trợ:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
class WebSecurityConfiguration {

    @Bean
    SecurityFilterChain webChain(HttpSecurity http) throws Exception {
        http
            .csrf(csrf -> csrf.spa())
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET, "/api/csrf").permitAll()
                .requestMatchers("/api/**").authenticated()
                .anyRequest().permitAll()
            )
            .formLogin(Customizer.withDefaults())
            .logout(Customizer.withDefaults());

        return http.build();
    }
}
~~~

**Cách đọc ví dụ:**

1. **csrf.spa()** là thành viên **CsrfConfigurer** mà lambda của **HttpSecurity.csrf(...)** nhận được.
2. **/api/csrf** được **permitAll** để SPA lấy token trước login và sau logout, nhưng **permitAll không tắt CsrfFilter**.
3. **formLogin** và **logout** chỉ minh họa một web app sử dụng cookie/session. Với API JSON login hoặc OAuth/OIDC, cần cấu hình authentication thực tế.
4. Các endpoint dưới **/api/** yêu cầu đăng nhập nhưng vẫn cần phân quyền theo nghiệp vụ; ví dụ không thay thế authorization chi tiết.
5. Trong hệ thống có nhiều SecurityFilterChain, phải xác minh GET /api/csrf và POST protected cùng đi qua cấu hình CSRF tương thích.

**Không chạy snippet này trên Spring Security 6.x.** Trên 6.x, lỗi không có phương thức spa() là đúng theo API; xem phần cấu hình thay thế ở dưới.

### 4.1. Khi cần tùy chỉnh cookie CSRF

Nếu ứng dụng muốn đặt **Secure, SameSite, Path** phù hợp với HTTPS production, có thể tạo repository riêng và truyền vào CsrfConfigurer. Nhưng phải hiểu **thứ tự lời gọi**: **spa() chọn repository/handler mặc định**, nên việc gọi **csrfTokenRepository(...) sau spa()** có thể thay repository mà vẫn dùng SPA request handler.

~~~java
import org.springframework.security.web.csrf.CookieCsrfTokenRepository;

CookieCsrfTokenRepository repository =
    CookieCsrfTokenRepository.withHttpOnlyFalse();

repository.setCookieCustomizer(cookie -> cookie
    .secure(true)
    .sameSite("Lax")
    .path("/")
);

// Bên trong HttpSecurity; Spring Security 7.x:
http.csrf(csrf -> csrf
    .spa()
    .csrfTokenRepository(repository)
);
~~~

Đây là **biến thể thay thế** cho dòng .csrf(csrf -> csrf.spa()) ở phần 4, không cấu hình cả hai chồng lên nhau. Khi thay repository, phải giữ được hợp đồng **XSRF-TOKEN cookie → X-XSRF-TOKEN raw header**. Nếu thay bằng repository session hoặc tên header khác, cần sửa frontend và kiểm thử.

**Không đặt HttpOnly=true** cho chính XSRF cookie nếu JavaScript được yêu cầu đọc cookie. Cookie xác thực JSESSIONID/JWT vẫn cần cấu hình **HttpOnly** độc lập. Cookie Secure chỉ hoạt động với kết nối an toàn theo chính sách browser; ưu tiên HTTPS local thay vì hạ bảo mật production.

### 4.2. Bảo vệ cookie phiên tách biệt

Trong ứng dụng Servlet sử dụng session, Spring Boot có các thuộc tính cấu hình cookie phiên, ví dụ tùy dòng phiên bản Boot:

~~~properties
server.servlet.session.cookie.http-only=true
server.servlet.session.cookie.secure=true
server.servlet.session.cookie.same-site=lax
~~~

Các thuộc tính này dành cho **session cookie**, không thay thế cấu hình cookie **XSRF-TOKEN** của CookieCsrfTokenRepository. Nếu ứng dụng tự phát cookie JWT, phải cấu hình HttpOnly/Secure/SameSite trực tiếp cho cookie JWT.

**CSRF token không cấp quyền:** trình duyệt gửi CSRF token hợp lệ nhưng thiếu session hoặc quyền ghi vẫn phải bị từ chối.

## 5. Luồng frontend cùng origin sử dụng preset

Giả sử SPA được phục vụ tại **https://app.example.com** và API nằm dưới cùng origin đó. Browser có thể nhận **XSRF-TOKEN** do Spring Security phát, JavaScript đọc nó và thêm header ở request không an toàn.

~~~mermaid
sequenceDiagram
    autonumber
    participant SPA as JavaScript SPA
    participant B as Browser cookie jar
    participant S as Spring Security Servlet
    participant API as API Controller
    SPA->>S: GET /api/csrf
    S->>S: spa() dùng cookie CSRF repo + SPA handler
    S-->>B: Set-Cookie XSRF-TOKEN=raw
    B-->>SPA: document.cookie có raw XSRF token
    SPA->>S: POST /api/profile + Cookie + X-XSRF-TOKEN=raw
    S->>S: Handler lấy raw header và CsrfFilter so khớp
    alt CSRF hợp lệ, người dùng đủ quyền
        S->>API: Cho phép controller xử lý
        API-->>SPA: Response nghiệp vụ
    else Thiếu hoặc token sai
        S-->>SPA: Thường 403
    end
~~~

### 5.1. Endpoint GET bootstrap có kiểm soát

Dù preset có cơ chế nạp token phục vụ SPA, một endpoint **GET /api/csrf** giúp giao diện chủ động khởi tạo hoặc làm mới token, đặc biệt sau login/logout.

~~~java
import jakarta.servlet.http.HttpServletRequest;
import org.springframework.http.CacheControl;
import org.springframework.http.ResponseEntity;
import org.springframework.security.web.csrf.CsrfToken;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
class SpaCsrfBootstrapController {

    @GetMapping("/api/csrf")
    ResponseEntity<Void> bootstrap(HttpServletRequest request) {
        CsrfToken token = (CsrfToken) request.getAttribute(
            CsrfToken.class.getName());

        if (token == null) {
            throw new IllegalStateException("CSRF filter not configured");
        }

        token.getToken(); // Bảo đảm token đã được truy cập.
        return ResponseEntity.noContent()
            .cacheControl(CacheControl.noStore())
            .build();
    }
}
~~~

Endpoint trả **204 No Content** vì SPA lấy raw token qua cookie thay vì lấy token masked qua JSON. Đừng chỉ kiểm tra 204; browser còn phải nhận **Set-Cookie**, và trang frontend phải ở **đúng phạm vi Domain/Path** để đọc.

**Lý do không trả token request attribute qua JSON ở đây:** preset SPA xử lý header từ cookie như **raw token**. Trong khi token trình bày ở request attribute có thể **XOR-masked**. Nếu frontend lấy masked token từ JSON rồi gửi qua header mà backend coi header là raw, sẽ xuất hiện **InvalidCsrfTokenException**. Hãy chọn một contract rõ ràng, không trộn hai nguồn.

### 5.2. JavaScript đọc cookie

~~~javascript
function readCookie(name) {
  const prefix = encodeURIComponent(name) + "=";
  const match = document.cookie
    .split("; ")
    .find(value => value.startsWith(prefix));

  return match ? decodeURIComponent(match.slice(prefix.length)) : null;
}

async function bootstrapXsrf() {
  const response = await fetch("/api/csrf", {
    method: "GET",
    credentials: "same-origin",
    cache: "no-store"
  });

  if (!response.ok) {
    throw new Error("CSRF bootstrap failed: " + response.status);
  }

  const value = readCookie("XSRF-TOKEN");
  if (!value) {
    throw new Error("XSRF cookie was not created or is not readable");
  }
  return value;
}
~~~

**Không log giá trị token** hay đưa vào URL. Việc đọc cookie là thao tác của JS; **JSESSIONID HttpOnly** sẽ không xuất hiện trong document.cookie nhưng browser vẫn tự gửi nó khi request phù hợp.

### 5.3. Gửi POST với token gốc

~~~javascript
async function saveProfile(profile) {
  const token = readCookie("XSRF-TOKEN") || await bootstrapXsrf();

  const response = await fetch("/api/profile", {
    method: "PATCH",
    credentials: "same-origin",
    headers: {
      "Content-Type": "application/json",
      "X-XSRF-TOKEN": token
    },
    body: JSON.stringify(profile)
  });

  if (response.status === 403) {
    // 403 có thể do CSRF hoặc quyền; không tự lặp PATCH.
    throw new Error("Forbidden; inspect CSRF and authorization");
  }
  if (!response.ok) {
    throw new Error("Update failed: " + response.status);
  }

  return response.status === 204 ? null : response.json();
}
~~~

Với React, Vue, Angular hoặc Axios, có thể gom logic vào HTTP service/interceptor. Chỉ thêm header này khi gọi **backend tin cậy**; không gửi token tới origin ngoài danh sách API. Một số client tự động chỉ thêm header XSRF cho URL tương đối/same-origin; phải kiểm tra request thật trong DevTools thay vì suy đoán từ cấu hình.

## 6. Làm mới XSRF token sau đăng nhập và đăng xuất

### 6.1. Sau login thành công

Với Spring Security Servlet, **CsrfAuthenticationStrategy** có thể xóa token trước đăng nhập. Token mới được tạo/nạp theo request handler và repository; không giả định response login luôn phát sẵn cookie mới.

Luồng đúng:

~~~text
Mở SPA → GET /api/csrf → XSRF token A
POST /login cùng cookie và X-XSRF-TOKEN: A
Backend xác thực thành công → session/cookie có thể đổi, A có thể bị xóa
GET /api/csrf với cookie phiên hiện hành → XSRF token B
POST /api/profile với X-XSRF-TOKEN: B
~~~

Frontend cần **đợi backend xác nhận login thật sự thành công**. Với formLogin mặc định có redirect, status 200 cuối cùng của Fetch có thể là một trang HTML sau redirect chứ không phải bằng chứng login thành công. JSON login custom phải có response/error contract rõ ràng.

### 6.2. Sau logout thành công

~~~text
POST /logout dùng XSRF token B đang hợp lệ và cookie phiên
Backend logout thành công → token/cookie cũ có thể bị xóa
SPA xóa token/cache thuộc phiên đã đăng nhập
GET /api/csrf trong trạng thái anonymous mới → XSRF token C nếu cần
~~~

**Đừng xóa XSRF token trước khi gửi POST logout** nếu logout cũng được CsrfFilter bảo vệ. Không dùng GET cho logout có side effect chỉ để tiện SPA.

### 6.3. Không có session đăng nhập vẫn có thể có CSRF cookie

Sau logout, Spring Security có thể cấp CSRF token mới cho anonymous để bảo vệ form login hoặc endpoint public không an toàn. Vì vậy nhìn thấy **XSRF-TOKEN** sau logout **không chứng minh người dùng còn đăng nhập**. Cần xác minh SecurityContext/principal và quyền.

### 6.4. Trường hợp nhiều tab và request đến trễ

Cookie browser có thể được chia sẻ giữa các tab, nhưng biến JavaScript trong mỗi tab không tự đồng bộ. Một GET token cũ gửi trước login có thể trả response **sau** GET token mới.

Để tránh token cũ ghi đè:

- Xóa cached CSRF token sau khi backend xác nhận auth transition.
- Dùng **generation/epoch** hoặc AbortController kết hợp kiểm tra trạng thái cho các request bootstrap đang chạy.
- Không gửi POST mới khi trạng thái login/logout đang chuyển.
- Với nhiều tab, phát tín hiệu **auth changed** qua kênh cùng origin nếu cần, nhưng không chia sẻ giá trị token cho mục tiêu thông báo.
- Server luôn phải kiểm tra cookie, CSRF token và quyền, không chỉ dựa vào cờ client.

## 7. Tương đương trên Spring Security 6.x: tự cấu hình hai thành phần

**Spring Security 6.5 không có CsrfConfigurer.spa().** Để giữ phòng vệ tương đương cho SPA Servlet, cấu hình **CookieCsrfTokenRepository** cùng **CsrfTokenRequestHandler** nhận token raw ở header và token XOR-masked trong form.

### 7.1. SecurityFilterChain của Servlet 6.x

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.csrf.CookieCsrfTokenRepository;

@Configuration
class LegacySpaSecurityConfiguration {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
        CookieCsrfTokenRepository repository =
            CookieCsrfTokenRepository.withHttpOnlyFalse();

        return http
            .csrf(csrf -> csrf
                .csrfTokenRepository(repository)
                .csrfTokenRequestHandler(
                    new LegacySpaCsrfTokenRequestHandler())
            )
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET, "/api/csrf").permitAll()
                .requestMatchers("/api/**").authenticated()
                .anyRequest().permitAll()
            )
            .formLogin(Customizer.withDefaults())
            .build();
    }
}
~~~

**LegacySpaCsrfTokenRequestHandler** là class ứng dụng tự viết, không phải một class public cùng tên nằm sẵn trong mọi phiên bản framework:

~~~java
import java.util.function.Supplier;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import org.springframework.security.web.csrf.CsrfToken;
import org.springframework.security.web.csrf.CsrfTokenRequestAttributeHandler;
import org.springframework.security.web.csrf.CsrfTokenRequestHandler;
import org.springframework.security.web.csrf.XorCsrfTokenRequestAttributeHandler;
import org.springframework.util.StringUtils;

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

        // Giữ XOR masking cho request attribute/HTML form.
        this.xor.handle(request, response, csrfToken);

        // Hiện thực hóa deferred token để XSRF cookie được phát khi cần.
        csrfToken.get().getToken();
    }

    @Override
    public String resolveCsrfTokenValue(
            HttpServletRequest request,
            CsrfToken csrfToken) {

        String header = request.getHeader(csrfToken.getHeaderName());

        // Header có raw token từ JS; form parameter dùng masked token.
        return (StringUtils.hasText(header) ? this.plain : this.xor)
            .resolveCsrfTokenValue(request, csrfToken);
    }
}
~~~

Nếu chỉ có JSON API, có thể chọn handler plain đơn giản hơn, nhưng khi nhúng token vào HTML có response compression, phải đánh giá BREACH/masking. Class kết hợp ở trên tránh việc đánh đổi masking cho toàn bộ ứng dụng chỉ để frontend gửi raw header.

### 7.2. Điểm giống và khác với preset Spring Security 7

| Phần | Spring Security 6.x thủ công | CsrfConfigurer.spa() ở 7.x |
| --- | --- | --- |
| Lưu CSRF token | CookieCsrfTokenRepository.withHttpOnlyFalse() | Cookie repository JavaScript-readable do preset chọn |
| Đọc raw header của SPA | Plain CsrfTokenRequestAttributeHandler | SPA handler nội bộ xử lý |
| Xử lý masked token ở form | XorCsrfTokenRequestAttributeHandler | SPA handler nội bộ xử lý |
| Deferred loading | Mẫu tự gọi token supplier | Cơ chế nạp token do handler tích hợp đảm nhiệm |
| Mã cần duy trì | Một class custom handler | Không cần class custom cho trường hợp thường gặp |
| Phân quyền, login và CORS | Vẫn phải cấu hình riêng | Vẫn phải cấu hình riêng |

Trong mã nguồn 7.x được đối chiếu, handler nội bộ điều chỉnh tên request attribute của XOR handler để đảm bảo nạp token phù hợp; trong ví dụ 6.x ở đây ta dùng **csrfToken.get().getToken()** một cách tường minh. Không coi cách triển khai private của một phiên bản là API public bất biến. Khi nâng cấp, phải chạy regression test.

### 7.3. Không nâng cấp cả dự án chỉ vì một method tiện ích

Nâng từ Spring Security 6 sang 7 có thể kéo theo thay đổi Spring Framework, Spring Boot, các API và dependency test. Đừng ép upgrade nếu dự án chưa sẵn sàng, cũng đừng trộn jar 6.x và 7.x để cố làm hiện ra spa(). Một cấu hình thủ công được kiểm thử tốt trên phiên bản hiện tại vẫn là lựa chọn hợp lý.

## 8. WebFlux: ServerHttpSecurity không dùng DSL Servlet spa()

**CsrfConfigurer.spa() thuộc HttpSecurity Servlet.** Reactive dùng **ServerHttpSecurity**, **SecurityWebFilterChain**, **ServerCsrfTokenRepository** và **ServerCsrfTokenRequestHandler** riêng. Không sao chép trực tiếp lời gọi Servlet vào cấu hình WebFlux:

~~~java
// KHÔNG dùng đoạn này như ví dụ ServerHttpSecurity:
http.csrf(csrf -> csrf.spa());
~~~

Với WebFlux API JSON cùng origin, SPA đọc raw XSRF cookie, cấu hình tham khảo:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.web.server.SecurityWebFilterChain;
import org.springframework.security.web.server.csrf.CookieServerCsrfTokenRepository;
import org.springframework.security.web.server.csrf.ServerCsrfTokenRequestAttributeHandler;

@Bean
SecurityWebFilterChain reactiveApiSecurity(ServerHttpSecurity http) {
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
            .anyExchange().authenticated()
        )
        .build();
}
~~~

Đây là **biến thể raw token**, không phải bản sao đầy đủ mọi hành vi của SPA handler Servlet 7. Nếu cùng ứng dụng còn HTML form cần XOR masking, phải xây dựng request handler Reactive tương ứng và kiểm thử, không đưa HttpServletRequest vào WebFlux.

### 8.1. Bootstrap Reactive với Mono<CsrfToken>

~~~java
import org.springframework.http.CacheControl;
import org.springframework.http.ResponseEntity;
import org.springframework.security.web.server.csrf.CsrfToken;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ServerWebExchange;
import reactor.core.publisher.Mono;

@RestController
class ReactiveXsrfBootstrapController {

    @GetMapping("/api/csrf")
    Mono<ResponseEntity<Void>> csrf(ServerWebExchange exchange) {
        Mono<CsrfToken> tokenMono =
            exchange.getAttribute(CsrfToken.class.getName());

        if (tokenMono == null) {
            return Mono.error(
                new IllegalStateException("CSRF filter not configured"));
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

Không gọi **block()** trong WebFlux controller. Pipeline phải subscribe Mono để token được nạp/tạo. Các cơ chế authentication, logout, WebSession và cookie trong WebFlux cần được kiểm thử bằng flow Reactive thật; không giả định các strategy/logout handler Servlet đang chạy ở stack này.

## 9. Khi SPA và API khác origin: preset không mở phạm vi cookie

Ví dụ SPA ở **https://app.example.com**, API ở **https://api.example.com**. Cookie host-only **XSRF-TOKEN** do API phát cho api.example.com sẽ **không được JavaScript ở app.example.com đọc qua document.cookie**. Dù hai subdomain thường cùng site, chúng khác origin, và Fetch khác origin cần **credentials: "include"** nếu muốn gửi cookie.

~~~javascript
const response = await fetch("https://api.example.com/api/csrf", {
  credentials: "include",
  cache: "no-store"
});
// credentials=include không cho JavaScript quyền đọc cookie host-only
// thuộc api.example.com qua document.cookie tại app.example.com.
~~~

**spa() không thay đổi quy tắc cookie của trình duyệt.** Đánh giá ba hướng:

| Giải pháp | Lợi ích | Điều cần kiểm soát |
| --- | --- | --- |
| Reverse proxy/BFF để SPA và API chung origin | Giữ cookie host-only, tránh CORS phức tạp | Bảo vệ ranh giới browser → BFF và quyền |
| GET /api/csrf trả token JSON cho origin tin cậy | SPA khác origin đọc response qua CORS | Handler phải nhận **đúng định dạng token JSON** (raw hoặc XOR-masked) |
| Đặt Domain=example.com cho cookie XSRF | JS ở subdomain khác có thể đọc cookie | Rủi ro cookie injection và rò rỉ trên subdomain không tin cậy |

**Tránh trộn hợp đồng:** Nếu GET JSON trả một token đã XOR-mask từ request attribute nhưng handler SPA nhận token header theo đường raw, POST có thể bị **InvalidCsrfTokenException**. Khi chọn JSON, phải cấu hình repository và request handler đồng bộ với định dạng trả về; không cho rằng spa() tự chấp nhận mọi biểu diễn token.

### 9.1. CORS allowlist Servlet

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
    cors.setAllowedMethods(List.of("GET", "POST", "PUT", "PATCH", "DELETE"));
    cors.setAllowedHeaders(List.of(
        "Content-Type", "X-XSRF-TOKEN", "X-CSRF-TOKEN"));
    cors.setAllowCredentials(true);

    UrlBasedCorsConfigurationSource source =
        new UrlBasedCorsConfigurationSource();
    source.registerCorsConfiguration("/api/**", cors);
    return source;
}
~~~

Trong HttpSecurity dùng **.cors(Customizer.withDefaults())** để xử lý preflight đúng thứ tự. WebFlux cần CORS Reactive với các package tương ứng.

Không dùng wildcard Origin cùng credentials. Một custom header như **X-XSRF-TOKEN** thường khiến browser gửi OPTIONS preflight từ origin khác. CORS ngăn JavaScript không được phép đọc response, nhưng **không thay CsrfFilter** cho các đường request giả mạo có cookie.

**SameSite, Secure, Domain/Path, third-party cookies và Fetch credentials** vẫn quyết định cookie có được gửi/lưu hay không. Cookie có HttpOnly=false cho XSRF không thay đổi quyền đọc session cookie HttpOnly.

## 10. Giới hạn bảo mật và phương pháp phòng vệ bổ sung

### 10.1. XSS

Trong mô hình SPA đọc cookie CSRF, **XSRF-TOKEN không có HttpOnly** để JavaScript hợp lệ có thể lấy token. Script XSS chạy cùng origin cũng có thể đọc nó hoặc gọi API với cookie đăng nhập HttpOnly do browser tự gửi.

Vì vậy phải chống XSS riêng: output encoding đúng ngữ cảnh, tránh DOM injection, giới hạn script bên thứ ba và cấu hình **CSP** phù hợp. spa() không làm XSS biến mất.

### 10.2. Cookie injection và double-submit

CookieCsrfTokenRepository dùng cookie làm nguồn token. Một subdomain không đáng tin cậy có thể tạo rủi ro cookie injection nếu cookie đặt Domain quá rộng hoặc hệ thống cho phép cookie trùng tên với scope khác nhau.

Biện pháp:

- Ưu tiên cookie **host-only**, hạn chế Domain chia sẻ.
- Dùng **Secure** và HTTPS/HSTS production.
- Xem xét tiền tố **__Host-** khi cookie đáp ứng Secure, Path=/ và không có Domain; frontend/repository phải cùng tên.
- Quản lý subdomain và những điểm có thể tạo Set-Cookie.
- Với yêu cầu cao, cân nhắc **signed double-submit token** có ràng buộc mật mã với phiên hoặc synchronizer token có state.
- Dùng Origin/Referer hoặc Fetch Metadata làm lớp hỗ trợ theo chính sách rõ ràng.

**XOR masking nhằm giảm BREACH, không phải chữ ký HMAC.** Cũng không được coi spa() là giải pháp cho mọi biến thể cookie injection.

### 10.3. Stateless và Bearer-only

Nếu API chỉ chấp nhận **Authorization: Bearer** do frontend chủ động gửi, không có cookie/Basic/SSO browser-managed credential fallback, CSRF trình duyệt truyền thống thường không phải mối đe dọa chính trên các route đó. Không dùng preset cookie chỉ vì frontend là React hoặc Angular.

Nếu API stateless xác thực bằng **JWT cookie**, gateway/BFF dùng cookie hoặc endpoint refresh/logout dùng cookie, vẫn phải đánh giá CSRF theo đường xác thực thực tế.

## 11. Kiểm thử Servlet trên dòng 7.x bằng MockMvc

Một test tốt không chỉ kiểm tra ứng dụng đã có cookie, mà phải chứng minh **cookie tự gửi không đủ** để vượt CSRF, còn **raw header đúng** được request handler giải quyết và so khớp. Đồng thời server vẫn phải kiểm tra người dùng và quyền.

### 11.1. Test GET bootstrap, POST thiếu/sai/đúng header

Giả sử ứng dụng dùng **csrf.spa()**, đã triển khai GET **/api/csrf** trả 204 như phần 5, có POST **/api/preferences** nhận JSON trả 2xx khi dữ liệu hợp lệ, và dùng **spring-security-test**.

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
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;

class SpaCsrfFilterTests {

    // Dự án cần tạo MockMvc có Spring Security filters qua test config.
    @Autowired MockMvc mvc;

    @Test
    void rawHeaderIsRequiredInAdditionToCsrfCookie() throws Exception {
        MvcResult start = mvc.perform(get("/api/csrf"))
            .andExpect(status().isNoContent())
            .andReturn();

        Cookie xsrf = start.getResponse().getCookie("XSRF-TOKEN");
        assertNotNull(xsrf, "Expected XSRF cookie after bootstrap");
        assertFalse(xsrf.isHttpOnly(), "SPA must read this CSRF cookie");

        // Browser có cookie XSRF nhưng client không chủ động gửi header.
        mvc.perform(post("/api/preferences")
                .with(user("alice"))
                .cookie(xsrf)
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"notifications\":true}"))
            .andExpect(status().isForbidden());

        mvc.perform(post("/api/preferences")
                .with(user("alice"))
                .cookie(xsrf)
                .header("X-XSRF-TOKEN", "incorrect")
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

Đây là **đoạn test tích hợp minh họa**, yêu cầu test context riêng của phiên bản Boot/Framework dự án để tạo và inject **MockMvc** đã gắn SecurityFilterChain. Nó cũng giả định endpoint POST có thật và cho phép thao tác hợp lệ. **user("alice")** mô phỏng principal, không kiểm chứng authentication/session cookie thực tế.

Nên assert thêm **dữ liệu không thay đổi** khi 403; chỉ xem status code chưa đủ nếu có một side effect xảy ra trước khi request bị từ chối.

### 11.2. Test form HTML masked token

Nếu ứng dụng còn dùng Thymeleaf/JSP:

1. GET trang form có hidden input **_csrf**, dùng token request attribute.
2. Giữ cookie XSRF của cùng browser.
3. POST form với masked token trong parameter **_csrf**, không có X-XSRF-TOKEN header.
4. Kỳ vọng CSRF filter giải mã token bằng đường XOR và cho request hợp lệ đi tiếp.
5. POST form với token sai: phải bị từ chối.
6. Thử gắn một header raw không khớp vào request form: handler có thể chọn nhánh header và từ chối dù parameter masked đúng.

Bước cuối chứng minh **thứ tự ưu tiên header/parameter là một phần hợp đồng**. Không tự để interceptor gắn XSRF header bị lỗi vào mọi form HTML.

### 11.3. Kiểm thử login/logout với cookie thật

Test dùng một HTTP client hoặc browser giữ cookie jar:

~~~text
GET /api/csrf anonymous → XSRF cookie token A
POST /login + A → authentication thật thành công
GET /api/csrf authenticated → XSRF cookie token B
POST /api/preferences + B → xử lý khi đủ quyền
POST /logout + B → logout thật
GET /api/csrf anonymous → XSRF cookie token C nếu cần
POST /api/preferences anonymous + C → vẫn không có quyền
~~~

Với các authentication/logout strategy thông thường, token cũ có thể bị xóa và cần bootstrap lại. Không tự khẳng định chuỗi A, B, C **luôn khác nhau** trong mọi implementation; kiểm tra trạng thái repository, request thành công/thất bại và principal thực tế.

### 11.4. WebFlux cần test riêng, không tái dùng MockMvc

Reactive dùng WebTestClient và test helper của **spring-security-test**:

~~~java
import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.csrf;
import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.mockUser;

// Đoạn thân test; webTestClient đã được gắn SecurityWebFilterChain.
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

Cần khai báo **java.util.Map**, WebTestClient và handler tương ứng. **mockUser()** cùng **csrf()** chỉ kiểm tra filter ở mức test helper; để chứng minh **CookieServerCsrfTokenRepository** hoạt động, phải chạy integration test GET bootstrap và POST cùng cookie/raw header thật.

## 12. Ma trận acceptance và regression trước khi triển khai

| Trường hợp | Kết quả mong đợi |
| --- | --- |
| Spring Security 7.0+ Servlet dùng csrf.spa() | Code biên dịch bằng đúng version spring-security-config |
| Spring Security 6.5 Servlet dùng csrf.spa() | Lỗi do method chưa tồn tại; dùng cấu hình thủ công |
| WebFlux gọi CsrfConfigurer.spa() của Servlet | Sửa sang ServerHttpSecurity và request handler Reactive |
| GET bootstrap khi XSRF cookie chưa có | Cookie được cấp khi token được hiện thực hóa |
| SPA cùng origin đọc XSRF-TOKEN | JavaScript đọc được cookie token đã chủ đích đặt HttpOnly=false |
| JSESSIONID có HttpOnly | JavaScript không đọc trực tiếp giá trị cookie đăng nhập |
| POST chỉ mang cookie session và XSRF, thiếu header | CSRF filter chặn, dữ liệu không đổi |
| POST raw header không khớp | Bị từ chối |
| POST raw header khớp và session/quyền hợp lệ | Vượt CSRF và nghiệp vụ có thể xử lý |
| POST raw header khớp nhưng thiếu quyền | Bị từ chối do authorization |
| Form HTML gửi masked _csrf parameter | Handler XOR giải quyết được khi cấu hình phù hợp |
| SPA gửi masked JSON vào handler nhận raw header | Không được mặc định chấp nhận; phải sửa hợp đồng |
| Login thành công làm token cũ hết hiệu lực | SPA bootstrap token mới trước POST |
| Logout thành công rồi tiếp tục anonymous | Có token CSRF mới nếu cần, không còn quyền user cũ |
| Request khác origin có custom header | Preflight phải được CORS cho phép đúng origin/method/header |
| SPA ở subdomain khác đọc host-only cookie API | Không đọc được; thiết kế BFF/JSON contract |
| Session timeout hoặc nhiều tab thay đổi auth | Không tự lặp request ghi nguy hiểm, đồng bộ state |
| Subdomain không tin cậy có thể chèn cookie | Đánh giá scope cookie, signed double-submit và subdomain |

**Đừng dùng kết quả curl thành công làm bằng chứng trình duyệt luôn thành công.** Browser thực thi cookie policy, SameSite và CORS; một HTTP client dòng lệnh không tự mô phỏng đầy đủ những cơ chế này.

## 13. Lỗi phổ biến và cách chẩn đoán

### “Cannot resolve method spa()”

Kiểm tra class **CsrfConfigurer** được IDE resolve từ jar nào. JavaDoc chính thức ghi **Since: 7.0**, nên không có trên Spring Security 6.5. Không tắt CSRF để sửa lỗi compile; dùng cấu hình thủ công hoặc nâng cấp toàn stack theo kế hoạch.

### “Biên dịch trên 7.x nhưng runtime NoSuchMethodError”

Kiểm tra dependency của module **spring-security-config** ở **runtime**, đặc biệt khi dự án override BOM hoặc có jar 6.x cũ trong classpath. Đồng bộ các Spring Security modules, không trộn phiên bản chỉ để gọi spa().

### “Đã dùng spa() mà POST vẫn 403”

Kiểm tra thứ tự: GET bootstrap đã cấp token, XSRF cookie có nằm trong đúng phạm vi, frontend có gắn **X-XSRF-TOKEN** raw, cookie/token có bị xóa sau login/logout, SecurityFilterChain nào thực tế xử lý POST. 403 cũng có thể do thiếu quyền, không chỉ do CSRF.

### “Tôi gọi spa() rồi tùy biến csrfTokenRequestHandler mà raw token không còn hoạt động”

Các lời gọi setter **sau preset** có thể thay thế request handler tích hợp. Hãy xác minh handler cuối cùng nhận raw cookie token hay masked JSON. Chỉ giữ một hợp đồng nhất quán rồi chạy lại test.

### “GET /api/csrf thành công nhưng document.cookie không có XSRF-TOKEN”

Kiểm tra hostname, Path, Domain, Secure, HttpOnly và việc cookie được phát qua **Set-Cookie**. Nếu SPA và API ở hai subdomain, cookie host-only của API không hiển thị trong document.cookie ở SPA. Việc thêm credentials include không vượt qua ranh giới đó.

### “Sau login/logout, POST đầu tiên lỗi nhưng F5 lại được”

Có thể token cũ bị xóa và SPA chưa bootstrap token mới hoặc POST chạy trước khi cookie mới được browser áp dụng. Gọi GET token sau khi backend xác nhận auth transition, đợi hoàn thành rồi mới cho thao tác ghi.

### “Angular/Axios có cookie nhưng không có header XSRF trên production”

Kiểm tra tên header/cookie, URL request là tương đối hay absolute, khác origin hay không, điều kiện interceptor của phiên bản HTTP client và CORS preflight. Không mở rộng Domain hoặc phản chiếu Origin tùy ý chỉ để sửa lỗi HTTP client.

### “Có CSP/HSTS/SameSite/HTTP firewall thì CSRF có còn cần?”

Các cơ chế này giải quyết những khía cạnh khác nhau: **CSP** giảm rủi ro script độc hại, **HSTS** cải thiện bảo vệ kết nối HTTPS, **SameSite** hạn chế nhiều tình huống browser tự gửi cookie, **HTTP firewall** từ chối request bất thường, còn **CORS** điều khiển script khác origin. Chúng **không** thay thế việc chứng minh CSRF token hợp lệ khi API chấp nhận cookie xác thực.

## 14. Quy trình chuyển từ cấu hình 6.x sang spa() trên 7.x

Một dự án đã có custom SPA request handler trên 6.x nên nâng cấp có kiểm soát, không chỉ xóa class và thay một dòng:

1. **Chốt phiên bản dependency** Spring Security, Framework, Boot và spring-security-test.
2. **Ghi nhận cookie và header hiện tại**: XSRF-TOKEN, X-XSRF-TOKEN, HttpOnly, Secure, SameSite, Domain, Path và vòng đời token.
3. **Xác minh threat model**: cookie-auth ở browser hay Bearer-only; SPA cùng origin hay khác origin.
4. **Thay cấu hình** sang **csrf.spa()** trên 7.x; chỉ tùy biến repository khi có lý do và kiểm tra thứ tự gọi method.
5. **Kiểm tra GET bootstrap** lần đầu, sau login và sau logout.
6. **Kiểm tra raw-header contract** bằng Fetch/Angular/Axios thực tế.
7. **Kiểm tra form HTML nếu có** để bảo đảm masked parameter vẫn được chấp nhận.
8. **Chạy ma trận regression** về CSRF, authentication, authorization, CORS, cookie policy và dữ liệu không đổi khi request bị chặn.
9. **Giám sát triển khai an toàn** bằng loại exception/status/correlation ID, không ghi CSRF token hay session ID vào log.

Khi thay đổi version, masked token có thể có biểu diễn khác; không kết luận nguyên nhân chỉ bằng so sánh chuỗi. Tập trung vào **repository, request handler, cookie và giá trị token mà client thực sự gửi**.

## 15. Tình huống thực hành và kết luận

**Tình huống A — Dự án Spring Security 6.5 dùng đoạn ví dụ csrf.spa().** IDE báo thiếu method.  
**Kết luận:** Đúng với API 6.5. Chọn cấu hình repository + custom handler thủ công hoặc nâng cấp có kế hoạch.

**Tình huống B — Spring Security 7.x Servlet, SPA cùng origin.** Cookie XSRF đã được cấp nhưng POST thiếu header.  
**Kết luận:** Browser tự gửi cookie không đủ. SPA phải đọc raw token và thêm **X-XSRF-TOKEN**.

**Tình huống C — SPA ở app.example.com, API ở api.example.com.** API phát cookie host-only nhưng JavaScript trên SPA không đọc được.  
**Kết luận:** spa() không phá ranh giới cookie. Ưu tiên BFF cùng origin hoặc GET JSON với CORS và request handler nhất quán.

**Tình huống D — Form HTML và SPA cùng một ứng dụng.** Form gửi masked parameter, SPA gửi raw header.  
**Kết luận:** Cơ chế handler SPA cho phép giải quyết hai đường dữ liệu; phải test cả hai và tránh interceptor header không đồng bộ.

**Tình huống E — Hệ thống tự thay CSRF repository sau spa().** Frontend vẫn kỳ vọng XSRF cookie nhưng repo mới lưu token trong session.  
**Kết luận:** Đã thay đổi contract; cần thiết kế lại nguồn token và handler, không coi preset là lớp bảo vệ bất biến sau khi override.

### Nguyên tắc cần nhớ

1. **CsrfConfigurer.spa() có từ Spring Security 7.0 trên Servlet HttpSecurity.**
2. **Preset chọn cookie CSRF JavaScript-readable và SPA request handler**, nhưng không thêm interceptor JS hay thay authentication/CORS.
3. **Raw XSRF cookie → raw X-XSRF-TOKEN header**, trong khi form HTML có thể sử dụng XOR-masked token.
4. **Dòng 6.x cần custom handler thủ công** hoặc một thiết kế CSRF phù hợp khác, không tắt bảo vệ vì thiếu method.
5. **WebFlux dùng các API Server... riêng**, không copy csrf.spa() Servlet.
6. **Login/logout và deferred token đòi hỏi bootstrap/làm mới token** theo cookie/session hiện hành.
7. **CORS, SameSite, Secure, Domain/Path và CSP/HSTS** bổ sung phòng vệ nhưng không tự thay CsrfFilter.
8. **Kiểm thử request thật và side effects**, không chỉ nhìn cookie, status hoặc có biên dịch thành công.

**Kết luận:** Dùng **csrf.spa()** khi dự án thực sự ở dòng phiên bản hỗ trợ **và** cơ chế xác thực/cookie phù hợp. Lợi ích của preset là bớt cấu hình lặp, chứ không thay việc hiểu cách token được lưu, JavaScript đọc, request handler giải quyết và CsrfFilter xác minh.

## Tài liệu tham khảo chính thức

- [Spring Security 7.0 — CsrfConfigurer JavaDoc, phương thức spa() ghi Since: 7.0](https://docs.spring.io/spring-security/reference/7.0/api/java/org/springframework/security/config/annotation/web/configurers/CsrfConfigurer.html)
- [Spring Security 7.0 — CSRF cho Servlet và Single-Page Applications](https://docs.spring.io/spring-security/reference/7.0/servlet/exploits/csrf.html)
- [Spring Security 6.5 — CsrfConfigurer JavaDoc](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/config/annotation/web/configurers/CsrfConfigurer.html)
- [Spring Security 6.5 — CSRF và custom request handler cho SPA](https://docs.spring.io/spring-security/reference/6.5/servlet/exploits/csrf.html)
- [Spring Security 7.0 — CSRF trong Reactive/WebFlux](https://docs.spring.io/spring-security/reference/7.0/reactive/exploits/csrf.html)



