# CORS không cấp quyền nghiệp vụ và không ngăn mọi client ngoài trình duyệt

> **Module:** Spring Security - fundamentals  
> **Chủ đề cha:** CORS  
> **Luận điểm chính:** CORS là cơ chế phối hợp **HTTP headers và chính sách do trình duyệt thực thi** để kiểm soát việc JavaScript ở origin A đọc response từ origin B. CORS **không phải authentication, không phải authorization nghiệp vụ, không phải firewall** và không thể dựa vào nó để ngăn mọi client như `curl`, Postman, script hoặc service backend gọi API.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

- Giải thích chính xác **origin** và **same-origin policy**, phân biệt scheme/host/port.
- Mô tả luồng **simple CORS request** và **preflight OPTIONS**; hiểu khi nào actual request đã được gửi tới server dù script bị chặn đọc response.
- Phân biệt `Access-Control-Allow-Origin`, `Access-Control-Allow-Credentials`, `Access-Control-Allow-Methods`, `Access-Control-Allow-Headers`, `Access-Control-Expose-Headers` và `Vary`.
- Giải thích vì sao một origin đã được cho phép không đồng nghĩa user có quyền đọc báo cáo, sửa đơn hàng, thanh toán hoặc truy cập tenant khác.
- Chứng minh một client **không phải trình duyệt** vẫn gửi HTTP request tới API; `Origin` header không phải bằng chứng danh tính đáng tin.
- Cấu hình Spring Boot 3.3.5, Java 17 và Spring Security 6.x: CORS chỉ chấp nhận một frontend, API vẫn đòi authentication + authorities, các POST browser vẫn cần CSRF token.
- Viết MockMvc tests tách riêng lỗi CORS, lỗi xác thực, lỗi thiếu quyền và lỗi CSRF.
- Thiết kế kiểm soát ở server theo principal, scopes/roles, resource ownership, tenant và business policy.

## 2. CORS thực sự làm gì?

**Cross-Origin Resource Sharing (CORS)** là cơ chế dùng headers HTTP để một server chỉ ra browser có thể cho phép một web page/script từ origin khác sử dụng response hay không. CORS bổ sung khả năng chia sẻ có kiểm soát lên **same-origin policy** của trình duyệt.

Ví dụ:

~~~text
Trang UI đang mở:
  https://ui.example.test

JavaScript fetch:
  https://api.example.test/reports/7

Hai URL khác origin vì hostname khác nhau.
Browser dùng CORS để xác định script từ UI có thể đọc
response do API trả về hay không.
~~~

Đối với `fetch()` hoặc `XMLHttpRequest` chạy trong browser, CORS là một phần quan trọng của mô hình bảo vệ dữ liệu cross-origin. Nhưng **server API không được coi việc browser chặn response là bằng chứng client đã bị xác thực hoặc bị từ chối quyền nghiệp vụ**.

Một client như `curl` tự gửi HTTP request và tự đọc response từ TCP/TLS connection của nó. Nó không có nghĩa vụ thực thi same-origin policy như browser. Vì vậy:

~~~text
Browser JS từ origin không được phép:
  Có thể bị browser từ chối truy cập response.

curl / Postman / backend service:
  Vẫn có thể gửi HTTP request.
  Response được client đó nhận trực tiếp nếu server xử lý.

Cả hai trường hợp:
  Server vẫn PHẢI xác thực và phân quyền.
~~~

**Quan trọng:** Một Spring CorsFilter hoặc reverse proxy có thể chủ động trả `403` đối với request **mang Origin header không được phép**. Điều đó không làm CORS trở thành hàng rào mạng chống mọi client: một client ngoài browser có thể không gửi `Origin`, có thể gửi một giá trị khác, và server vẫn phải áp dụng security policy độc lập.

## 3. Origin gồm scheme, host và port

Origin được xác định bởi bộ ba:

~~~text
scheme + host + port
~~~

Ví dụ origin của `https://app.example.test:8443/dashboard` là `https://app.example.test:8443`. Đường dẫn `/dashboard` **không** thuộc origin.

| URL | So với `https://app.example.test` |
| --- | --- |
| `https://app.example.test/page2` | Cùng origin (path khác) |
| `https://app.example.test:443` | Cùng origin theo cổng HTTPS mặc định |
| `http://app.example.test` | Khác origin (scheme khác) |
| `https://api.example.test` | Khác origin (host khác) |
| `https://app.example.test:8443` | Khác origin (port khác) |
| `https://app.example.test:3000` | Khác origin (port khác) |

**Origin và site là hai khái niệm khác nhau.** Hai subdomains có thể cùng site theo mô hình SameSite cookie nhưng vẫn khác origin đối với CORS. Đừng dùng thuật ngữ “cùng domain” mà không chỉ rõ scheme, host và port.

CORS thường dành cho browser khi web page cần đọc response của một origin khác. Nó không quy định rằng mọi request khác-origin đều bị cấm trên mạng.

## 4. Simple requests và preflight requests

### 4.1. Simple cross-origin request

Một số request như `GET` với headers được phép có thể không cần preflight. Browser vẫn **gửi actual request** tới server. Nếu response không có CORS headers phù hợp, browser sẽ không cung cấp response cho JavaScript gọi `fetch()`.

~~~text
Browser JS origin https://ui.example.test
       |
       | GET https://api.example.test/public-news
       | Origin: https://ui.example.test
       v
API có thể xử lý request và trả HTTP 200
       |
       | Thiếu Access-Control-Allow-Origin phù hợp
       v
Browser CHẶN script đọc response
       |
       v
API đã nhận và xử lý GET trước đó!
~~~

Điều này đặc biệt quan trọng với **request gây side effect**: không thể nói “CORS sẽ bảo vệ tài khoản khỏi CSRF” khi một số cross-origin requests có thể thực sự đi tới server và gây hiệu ứng dù script không đọc được response.

**Không đặt thay đổi trạng thái trên GET**. Một hệ thống dùng `GET /delete?id=42` đã vi phạm giả định HTTP safe methods và có nguy cơ bị kích hoạt qua nhiều cơ chế không cần JavaScript đọc response.

### 4.2. Preflight OPTIONS

Với một số methods/headers/content types, browser gửi **preflight** trước actual request:

~~~http
OPTIONS /reports/7 HTTP/1.1
Host: api.example.test
Origin: https://ui.example.test
Access-Control-Request-Method: GET
Access-Control-Request-Headers: Authorization
~~~

Server trả về thông tin CORS cho browser, ví dụ:

~~~http
HTTP/1.1 200 OK
Access-Control-Allow-Origin: https://ui.example.test
Access-Control-Allow-Methods: GET,POST,OPTIONS
Access-Control-Allow-Headers: Authorization,Content-Type,X-CSRF-TOKEN
Access-Control-Allow-Credentials: true
Access-Control-Max-Age: 3600
Vary: Origin
~~~

Nếu preflight không được chấp nhận, browser thông thường **không gửi actual request** theo flow preflight đó. Tuy nhiên, preflight chỉ hỏi liệu browser có được dùng method/headers cross-origin hay không; nó **không chứng minh principal đã authenticated** và không trao quyền trên tài nguyên.

**Preflight không gửi credentials như cookie session theo Fetch standard.** Spring Security khuyến cáo xử lý CORS trước authentication/filter chain, vì nếu application đòi session cookie ngay tại OPTIONS, preflight sẽ bị từ chối như request chưa đăng nhập. Không “sửa” lỗi preflight bằng `permitAll("/**")` cho mọi actual requests.

### 4.3. Preflight được chấp nhận không có nghĩa POST tiếp theo sẽ thành công

~~~text
OPTIONS /reports
  Origin: https://ui.example.test
  Access-Control-Request-Method: POST
  -> CORS OK (browser có thể gửi POST)

POST /reports
  Authorization: Bearer ...
  X-CSRF-TOKEN: ...
  -> vẫn phải qua authentication
  -> vẫn phải qua authorization
  -> vẫn phải qua CSRF khi cơ chế đó áp dụng
  -> vẫn phải qua object/business policy
~~~

Một browser có thể được quyền **gửi/đọc cross-origin response**, nhưng tài khoản người dùng vẫn không được tạo báo cáo nếu thiếu `report:create`.

## 5. CORS headers không phải security roles

| Header | Chức năng | Không có nghĩa |
| --- | --- | --- |
| `Origin` | Browser cho server biết origin của caller web context | Không phải JWT, username, user ID hay credential đáng tin |
| `Access-Control-Allow-Origin` | Origin mà browser được phép đọc response | Không chứng minh caller có quyền với resource |
| `Access-Control-Allow-Credentials` | Cho browser biết response credentialed request có được chia sẻ trong flow CORS không | Không xác thực cookie/JWT và không tự cấp quyền |
| `Access-Control-Allow-Methods` | HTTP methods browser có thể dùng theo CORS policy | Không thay `@PreAuthorize` hay authorization theo method |
| `Access-Control-Allow-Headers` | Request headers browser có thể sử dụng trong cross-origin request | Không chứng minh header có chứa token hợp lệ |
| `Access-Control-Expose-Headers` | Những response headers mà JS được đọc ngoài safelist | Không mở quyền nghiệp vụ |
| `Access-Control-Max-Age` | Gợi ý browser cache kết quả preflight | Không làm credential sống lâu hơn |
| `Vary: Origin` | Giúp shared caches không dùng nhầm biến thể response theo Origin | Không phải quyền truy cập hay authentication |

Server phải phân biệt một **origin được phép** với một **user có quyền**. Origin thường đại diện cho web application/site, không đại diện cho user hay tenant.

### Credentialed requests cần cấu hình nghiêm ngặt

Khi một browser gửi cross-origin request kèm credentials (ví dụ `fetch(..., { credentials: "include" })`), response không được dùng `Access-Control-Allow-Origin: *` để cho JavaScript đọc credentialed response. Server cần cho phép **origin cụ thể** và thiết lập `Access-Control-Allow-Credentials: true` trong trường hợp thích hợp.

**Tránh “phản chiếu” mọi Origin tùy ý** chỉ để làm hết CORS errors, nhất là khi bật credentials. Nếu phản chiếu origin mà không kiểm tra allowlist, gần như mọi site có thể đọc response được xác thực bằng cookie, tạo nguy cơ rò rỉ dữ liệu nghiêm trọng.

Ngay cả với origin explicit, bạn vẫn cần authentication, role/authority và object-level authorization.

## 6. CORS khác gì authentication, authorization, CSRF và network security?

| Cơ chế | Câu hỏi nó trả lời | Ví dụ |
| --- | --- | --- |
| **CORS** | Browser script của origin A có được đọc response từ origin B? | `Access-Control-Allow-Origin` |
| **Authentication** | Request mang danh tính/credential hợp lệ không? | Session login, OAuth2 bearer, HTTP Basic |
| **Authorization** | Principal này được thực hiện action trên resource này không? | `hasAuthority("report:read")`, tenant policy |
| **CSRF protection** | Một request dùng browser auto-credentials có đủ dấu hiệu chủ động từ nguồn hợp lệ? | CSRF token trong form/header |
| **Network policy** | Client có thể mở kết nối đến server không? | Firewall, VPC, allowlist mạng, mTLS |
| **Rate limiting** | Client/identity có gửi quá nhiều request không? | Quota, request rate, abuse detection |
| **Input validation** | Request data có đúng schema và quy tắc nghiệp vụ không? | Bean Validation, domain validation |

Không dùng một hàng CORS allowlist thay cho access-control list ở backend. CORS không tự ngăn:

- `curl`, Postman, Python `requests` hoặc các SDK gọi API.
- Server-to-server calls không có browser.
- Một attacker dùng credentials/token bị lộ (trừ khi server authentication/authorization từ chối).
- Người dùng đã login từ origin được phép nhưng không có quyền trên report của người khác.
- Một browser same-origin client gọi API với quyền tài khoản hiện hành.
- Request CSRF dạng simple cross-origin request trong các điều kiện cookie được tự gửi.

**Mối đe dọa không biến mất vì DevTools hiện “blocked by CORS policy”.** Có thể server đã nhận và thực thi request hoặc đã gửi response mà JavaScript không được đọc.

## 7. Ví dụ quyền nghiệp vụ: đọc báo cáo của tenant khác

Giả sử frontend `https://ui.example.test` được phép gọi API. Alice đăng nhập thành công, có `report:read` nhưng thuộc tenant A; báo cáo số 77 thuộc tenant B.

~~~text
CORS:
  Origin=https://ui.example.test -> ALLOWED

Authentication:
  Alice có token/session hợp lệ -> AUTHENTICATED

Authority:
  Alice có report:read -> TRUE

Object-level authorization:
  report 77 thuộc tenant B, Alice thuộc tenant A -> DENY

Kết quả mong đợi: Không tiết lộ report 77.
~~~

CORS pass và authority pass vẫn **không đủ** nếu chính sách có phân quyền theo resource/owner/tenant.

Một tầng service có thể dùng Spring method security:

~~~java
// ĐOẠN MINH HỌA trong Spring-managed service.
// Cần bean reportPolicy và repository thật của ứng dụng.
@PreAuthorize(
    "hasAuthority('report:read') and " +
    "@reportPolicy.canRead(authentication, #reportId)"
)
public Report findReport(long reportId) {
    return repository.findById(reportId).orElseThrow();
}
~~~

Đây là mã tích hợp, **không phải class độc lập**. `reportPolicy` phải kiểm tra owner/tenant bằng dữ liệu server tin cậy, không dựa vào `tenantId` do client tự gửi. `@EnableMethodSecurity` cần được bật ở Spring context và lời gọi phải đi qua Spring bean proxy/advice để `@PreAuthorize` có hiệu lực.

**Đừng đặt policy bằng so sánh `Origin` với tên tenant.** Một origin hợp lệ có thể phục vụ nhiều user/tenants, và một client ngoài browser có thể giả mạo `Origin`.

## 8. Chứng minh bằng `curl`: Origin không phải credential

Giả sử server chấp nhận CORS từ `https://ui.example.test`, và route `GET /reports/7` cần authenticated principal có `report:read`.

Một client như `curl` có thể gửi:

~~~bash
# Không gửi Origin; đây là request HTTP bình thường.
curl -i -u alice:demo-pass http://localhost:8080/reports/7

# Giữ credential hợp lệ nhưng tự gắn Origin không được phép:
curl -i -u alice:demo-pass \
  -H 'Origin: https://untrusted.example.test' \
  http://localhost:8080/reports/7

# Có thể đổi hoặc bỏ header Origin khi tự xây dựng request:
curl -i -u alice:demo-pass \
  -H 'Origin: https://ui.example.test' \
  http://localhost:8080/reports/7
~~~

Trong ví dụ Spring Boot ở phần sau, request đầu **có thể trả 200** vì Basic authentication và `report:read` hợp lệ, dù không có CORS header trong request. Request thứ hai có thể bị Spring CorsFilter trả 403 **vì đã tự khai báo một Origin không được phép**. Request thứ ba cũng có thể trả 200 cùng CORS headers nếu credential hợp lệ.

Điều cần rút ra:

- `Origin` header **không chứng minh** request thật sự do code tại origin đó tạo.
- `curl` không phải browser nên không có lý do bắt buộc áp dụng same-origin policy; nó tự quyết định HTTP headers cần gửi.
- Server-side CORS processing có thể từ chối request có Origin không hợp lệ, nhưng không phải mạng lưới chống mọi client.
- Điều thực sự bảo vệ báo cáo là **xác thực + authorization**; không có credentials hợp lệ thì `curl` không được truy cập route protected.

Không biến việc `curl` bỏ `Origin` thành khuyến nghị vượt quyền. Nó chỉ là minh chứng lý thuyết rằng CORS **không phải cơ chế quản lý quyền truy cập API**.

## 9. Ví dụ Spring Boot 3.3.5 / Java 17: CORS và quyền nghiệp vụ độc lập

Mục tiêu ứng dụng demo:

1. Chấp nhận cross-origin browser requests từ **duy nhất** `https://ui.example.test`.
2. Cho phép frontend này gửi headers `Authorization`, `Content-Type` và `X-CSRF-TOKEN`.
3. Chỉ user có `report:read` được GET `/reports/{id}`.
4. Chỉ user có `report:create` và CSRF token hợp lệ được POST `/reports`.
5. Giữ `GET /public` công khai.
6. Chứng minh một preflight được chấp nhận **không** có nghĩa actual request đã được cấp quyền.
7. Chứng minh user gọi không có Origin vẫn được xử lý theo chính sách server.

**Phiên bản học tập:** Java 17+, Gradle 8.x, Spring Boot 3.3.5, Spring Security 6.x. Mã dùng Servlet/Spring MVC và MockMvc, **không dùng WebFlux**.

### 9.1. Cấu trúc project

~~~text
cors-authz-demo/
├── settings.gradle
├── build.gradle
└── src/
    ├── main/java/demo/cors/
    │   ├── CorsAuthzApplication.java
    │   ├── SecurityConfig.java
    │   └── ReportController.java
    └── test/java/demo/cors/
        └── CorsAndAuthorizationTest.java
~~~

File `settings.gradle`:

~~~groovy
rootProject.name = 'cors-authz-demo'
~~~

File `build.gradle`:

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.5'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'demo'
version = '0.0.1-SNAPSHOT'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

`spring-boot-starter-web` cung cấp Spring MVC/Tomcat; `spring-boot-starter-security` cung cấp Spring Security; hai test starters cung cấp JUnit, MockMvc và `@WithMockUser`. `spring-boot-starter-security` không tự đặt business authorization policy đúng cho ứng dụng; ta khai báo rõ bên dưới.

### 9.2. Main application

File `src/main/java/demo/cors/CorsAuthzApplication.java`:

~~~java
package demo.cors;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class CorsAuthzApplication {
    public static void main(String[] args) {
        SpringApplication.run(CorsAuthzApplication.class, args);
    }
}
~~~

### 9.3. Spring Security: CORS cho browser + authz cho mọi HTTP client

File `src/main/java/demo/cors/SecurityConfig.java`:

~~~java
package demo.cors;

import java.util.List;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.web.cors.CorsConfiguration;
import org.springframework.web.cors.UrlBasedCorsConfigurationSource;

@Configuration
public class SecurityConfig {

    @Bean
    UrlBasedCorsConfigurationSource corsConfigurationSource() {
        CorsConfiguration cors = new CorsConfiguration();

        // Explicit origin; KHÔNG dùng "*" với credentialed browser requests.
        cors.setAllowedOrigins(List.of("https://ui.example.test"));
        cors.setAllowedMethods(List.of("GET", "POST", "OPTIONS"));
        cors.setAllowedHeaders(List.of(
            "Authorization", "Content-Type", "X-CSRF-TOKEN"
        ));
        cors.setAllowCredentials(true);
        cors.setMaxAge(3600L);

        UrlBasedCorsConfigurationSource source =
            new UrlBasedCorsConfigurationSource();
        source.registerCorsConfiguration("/**", cors);
        return source;
    }

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {
        return http
            .cors(Customizer.withDefaults())
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET, "/public").permitAll()
                .requestMatchers(
                    HttpMethod.GET, "/reports/**"
                ).hasAuthority("report:read")
                .requestMatchers(
                    HttpMethod.POST, "/reports"
                ).hasAuthority("report:create")
                .anyRequest().denyAll()
            )
            .httpBasic(Customizer.withDefaults())
            // CSRF vẫn được bật cho POST của browser.
            .csrf(Customizer.withDefaults())
            .build();
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    UserDetailsService users(PasswordEncoder encoder) {
        UserDetails alice = User.withUsername("alice")
            .password(encoder.encode("demo-pass"))
            .authorities("report:read")
            .build();

        UserDetails bob = User.withUsername("bob")
            .password(encoder.encode("demo-pass"))
            .authorities("report:create")
            .build();

        return new InMemoryUserDetailsManager(alice, bob);
    }
}
~~~

**Giải thích từng lớp:**

- `corsConfigurationSource()` khai báo browser origins, methods, headers được phép dùng CORS. Nó **không nói** ai được xem report.
- `http.cors(...)` tích hợp Spring Security với CORS processing để preflight được xử lý trước authentication. Với bean `UrlBasedCorsConfigurationSource`, Spring Security có đủ thông tin cấu hình CORS.
- `GET /public` được `permitAll()` vì không yêu cầu danh tính, không phải vì CORS đã kiểm tra.
- `GET /reports/**` cần `report:read`; `POST /reports` cần `report:create`; mặc định các routes không khai báo bị `denyAll()`.
- `httpBasic(...)` cung cấp một phương thức authentication thật cho demo và các lệnh `curl`. Trong production phải dùng HTTPS và auth mechanism phù hợp, không đưa mật khẩu thật vào script/log.
- `csrf(Customizer.withDefaults())` giữ CSRF được bật; request POST có quyền tạo báo cáo vẫn phải có token trong ngữ cảnh ứng dụng browser này.
- `setAllowCredentials(true)` minh họa một UI cần credentialed cross-origin behavior; **chỉ** origin explicit được phép. Cookie thực còn tuân theo SameSite/Secure/Path/Domain và browser policies.
- `setAllowedMethods(...)` là **CORS negotiation**, không thay authorizeHttpRequests; dù POST được phép ở CORS, Alice vẫn không có `report:create`.

### 9.4. Controller với trạng thái tạo report quan sát được

File `src/main/java/demo/cors/ReportController.java`:

~~~java
package demo.cors;

import java.util.concurrent.atomic.AtomicInteger;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class ReportController {

    private final AtomicInteger created = new AtomicInteger();

    @GetMapping("/public")
    public String publicPage() {
        return "public";
    }

    @GetMapping("/reports/{id}")
    public String readReport(@PathVariable long id) {
        return "report:" + id;
    }

    @PostMapping("/reports")
    public ResponseEntity<String> createReport() {
        int id = created.incrementAndGet();
        return ResponseEntity.status(HttpStatus.CREATED)
            .body("created:" + id);
    }

    public int createdCount() {
        return created.get();
    }

    public void resetForTest() {
        created.set(0);
    }
}
~~~

`AtomicInteger` là **giả lập side effect** giúp test phát hiện unauthorized mutation. API này không lưu report vào database và không triển khai quyền theo owner/tenant; chúng ta cố ý tách để thấy rằng CORS và authority check là hai cơ chế khác nhau. Production phải có resource-level policy như phần 7.

### 9.5. MockMvc tests: phân biệt từng tầng từ chối

File `src/test/java/demo/cors/CorsAndAuthorizationTest.java`:

~~~java
package demo.cors;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.HttpHeaders;
import org.springframework.security.test.context.support.WithMockUser;
import org.springframework.test.web.servlet.MockMvc;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.springframework.security.test.web.servlet.request
    .SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.security.test.web.servlet.request
    .SecurityMockMvcRequestPostProcessors.httpBasic;
import static org.springframework.test.web.servlet.request
    .MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request
    .MockMvcRequestBuilders.options;
import static org.springframework.test.web.servlet.request
    .MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result
    .MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result
    .MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result
    .MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class CorsAndAuthorizationTest {

    private static final String UI = "https://ui.example.test";
    private static final String OTHER =
        "https://untrusted.example.test";

    @Autowired
    MockMvc mvc;

    @Autowired
    ReportController reports;

    @BeforeEach
    void reset() {
        reports.resetForTest();
    }

    @Test
    void publicEndpointDoesNotRequireLogin() throws Exception {
        mvc.perform(get("/public"))
            .andExpect(status().isOk())
            .andExpect(content().string("public"));
    }

    @Test
    void allowedPreflightNeedsNoLogin() throws Exception {
        mvc.perform(options("/reports/7")
                .header(HttpHeaders.ORIGIN, UI)
                .header(HttpHeaders.ACCESS_CONTROL_REQUEST_METHOD, "GET"))
            .andExpect(status().isOk())
            .andExpect(header().string(
                HttpHeaders.ACCESS_CONTROL_ALLOW_ORIGIN, UI
            ))
            .andExpect(header().string(
                HttpHeaders.ACCESS_CONTROL_ALLOW_CREDENTIALS, "true"
            ));
    }

    @Test
    void disallowedPreflightIsRejectedByCors() throws Exception {
        mvc.perform(options("/reports/7")
                .header(HttpHeaders.ORIGIN, OTHER)
                .header(HttpHeaders.ACCESS_CONTROL_REQUEST_METHOD, "GET"))
            .andExpect(status().isForbidden());
    }

    @Test
    void allowedOriginWithoutAuthenticationIsStillRejected()
            throws Exception {
        mvc.perform(get("/reports/7")
                .header(HttpHeaders.ORIGIN, UI))
            .andExpect(status().isUnauthorized());
    }

    @Test
    @WithMockUser(username = "bob", authorities = "report:create")
    void allowedOriginWithoutReadPermissionIsStillForbidden()
            throws Exception {
        mvc.perform(get("/reports/7")
                .header(HttpHeaders.ORIGIN, UI))
            .andExpect(status().isForbidden());
    }

    @Test
    @WithMockUser(username = "alice", authorities = "report:read")
    void allowedOriginWithReadPermissionWorks() throws Exception {
        mvc.perform(get("/reports/7")
                .header(HttpHeaders.ORIGIN, UI))
            .andExpect(status().isOk())
            .andExpect(content().string("report:7"))
            .andExpect(header().string(
                HttpHeaders.ACCESS_CONTROL_ALLOW_ORIGIN, UI
            ));
    }

    @Test
    void validBasicRequestWithoutOriginIsAuthorized()
            throws Exception {
        // Mô phỏng HTTP client không gửi Origin.
        mvc.perform(get("/reports/7")
                .with(httpBasic("alice", "demo-pass")))
            .andExpect(status().isOk())
            .andExpect(content().string("report:7"));
    }

    @Test
    void untrustedOriginHeaderGetsCorsRejection()
            throws Exception {
        mvc.perform(get("/reports/7")
                .with(httpBasic("alice", "demo-pass"))
                .header(HttpHeaders.ORIGIN, OTHER))
            .andExpect(status().isForbidden());
    }

    @Test
    @WithMockUser(username = "bob", authorities = "report:create")
    void postMissingCsrfCannotMutate() throws Exception {
        mvc.perform(post("/reports")
                .header(HttpHeaders.ORIGIN, UI))
            .andExpect(status().isForbidden());

        assertEquals(0, reports.createdCount());
    }

    @Test
    @WithMockUser(username = "bob", authorities = "report:create")
    void postWithCsrfAndCreatePermissionWorks() throws Exception {
        mvc.perform(post("/reports")
                .header(HttpHeaders.ORIGIN, UI)
                .with(csrf()))
            .andExpect(status().isCreated())
            .andExpect(content().string("created:1"));

        assertEquals(1, reports.createdCount());
    }

    @Test
    @WithMockUser(username = "alice", authorities = "report:read")
    void postWithCsrfButWithoutCreatePermissionIsRejected()
            throws Exception {
        mvc.perform(post("/reports")
                .header(HttpHeaders.ORIGIN, UI)
                .with(csrf()))
            .andExpect(status().isForbidden());

        assertEquals(0, reports.createdCount());
    }
}
~~~

**Kết quả kỳ vọng:** tất cả **11 test pass** khi chạy với đúng dependencies/configuration ở trên. Đây là các kết quả được **suy ra từ mã ví dụ**, không phải log test đã thực thi trong bài.

Chạy từ root project bằng JDK 17+ và Gradle 8.x:

~~~bash
gradle test
~~~

### 9.6. Bảng chứng cứ từ test

| Test/điều kiện | Kỳ vọng | Kết luận |
| --- | --- | --- |
| `GET /public` | 200 | Endpoint public không cần login |
| OPTIONS preflight từ UI hợp lệ | 200 + `Access-Control-Allow-Origin` | Browser được phép thử actual GET cross-origin |
| OPTIONS preflight từ origin khác | 403 | CORS config từ chối origin đã khai báo |
| Actual GET từ UI hợp lệ nhưng không có authentication | 401 | CORS pass **không tự đăng nhập** |
| Actual GET từ UI hợp lệ, Bob chỉ có `report:create` | 403 | CORS pass **không cấp quyền đọc** |
| Actual GET từ UI hợp lệ, Alice có `report:read` | 200 | Authz quyết định quyền đọc báo cáo |
| GET không có Origin, Basic Alice hợp lệ | 200 | Non-browser-style request vẫn được server xử lý |
| GET có Origin lạ, Basic Alice hợp lệ | 403 | Spring CORS processor từ chối Origin đã khai báo |
| POST của Bob có Origin hợp lệ, thiếu CSRF | 403, counter 0 | CORS/authz không thay CSRF của browser |
| POST của Bob có CSRF và `report:create` | 201, counter 1 | Đáp ứng đủ các lớp bảo vệ |
| POST của Alice có CSRF nhưng không có `report:create` | 403, counter 0 | CSRF pass không cấp business authority |

**Đừng diễn giải test “Origin lạ → 403” thành “không client bên ngoài nào gọi được”.** Test “không Origin + Basic hợp lệ → 200” thể hiện chính ranh giới đó. Tùy server/proxy, một request ngoài browser thậm chí có thể tự đặt `Origin` hợp lệ; Origin không phải credential.

`@WithMockUser` giả lập `SecurityContext` để tập trung kiểm tra authorization; nó không kiểm chứng đăng nhập Basic thực. Test `validBasicRequestWithoutOriginIsAuthorized` sử dụng `httpBasic(...)` để đi qua authentication filter và UserDetailsService demo.

### 9.7. Thử trực tiếp bằng `curl`

Chạy ứng dụng:

~~~bash
gradle bootRun
~~~

Trong một terminal khác:

~~~bash
# Không có Origin, nhưng Basic auth của Alice hợp lệ -> dự kiến 200.
curl -i -u alice:demo-pass http://localhost:8080/reports/7

# Không có credential -> dự kiến 401.
curl -i http://localhost:8080/reports/7

# Bob có credential đúng nhưng thiếu quyền đọc -> dự kiến 403.
curl -i -u bob:demo-pass http://localhost:8080/reports/7

# Origin hợp lệ và user có quyền -> dự kiến 200, kèm CORS headers.
curl -i -u alice:demo-pass \
  -H 'Origin: https://ui.example.test' \
  http://localhost:8080/reports/7

# Gắn Origin không được phép -> CorsFilter có thể trả 403.
curl -i -u alice:demo-pass \
  -H 'Origin: https://untrusted.example.test' \
  http://localhost:8080/reports/7

# Tự gửi preflight OPTIONS từ origin UI:
curl -i -X OPTIONS http://localhost:8080/reports/7 \
  -H 'Origin: https://ui.example.test' \
  -H 'Access-Control-Request-Method: GET'
~~~

Kết quả cuối dự kiến là status 200 và `Access-Control-Allow-Origin: https://ui.example.test`. Việc `curl` in headers không phải do nó cần CORS để đọc response, mà vì ta chủ động gửi một request chứa những CORS headers.

**Lưu ý:** lệnh `curl -u` chỉ dùng cho local demo, tránh lộ mật khẩu trên command history/telemetry; production nên dùng HTTPS và cách lưu credential an toàn.

### 9.8. Ví dụ browser `fetch`

JavaScript từ `https://ui.example.test`:

~~~javascript
const response = await fetch("https://api.example.test/reports/7", {
  method: "GET",
  credentials: "include"
});
if (!response.ok) {
  throw new Error("API returned " + response.status);
}
console.log(await response.text());
~~~

**Ví dụ này giả định** frontend/backend thật đã được triển khai đúng hostname, cookie phù hợp và user đã authenticated. Demo Spring Boot local chỉ cung cấp `localhost:8080`; không có server UI hay OP tại `.example.test`. Trong browser, `credentials: "include"` và `Access-Control-Allow-Credentials: true` chỉ giải quyết bước chia sẻ credentialed response theo CORS. Cookie `SameSite`, `Secure`, policy third-party cookies và authentication vẫn quyết định có cookie nào được gửi.

Nếu browser request không có authentication hợp lệ, server trả 401 bất kể origin được phép. Nếu user thiếu authority, server trả 403 dù CORS hoàn toàn đúng.

## 10. CORS và CSRF: không thay thế nhau

CORS thường kiểm soát **browser script có thể đọc response cross-origin hay không**. CSRF kiểm soát **request làm thay đổi trạng thái được browser gửi với credential tự động có đúng ý người dùng không**.

Ví dụ một ứng dụng dùng session cookie:

~~~text
Alice login -> Browser có JSESSIONID
Alice ghé trang độc hại -> Trang tạo cross-site form POST

Browser có thể gửi POST với cookie theo chính sách cookie,
dù trang độc hại không đọc được response.

Nếu server không kiểm tra CSRF token, lệnh có thể vẫn chạy.
~~~

Vì vậy:

- Cho phép CORS từ một UI đáng tin **không có nghĩa** được tắt CSRF cho tất cả POST.
- Cấm origin bằng CORS **không bảo đảm** mọi form request đều không được gửi.
- `SameSite` cookie giúp giảm một số tình huống CSRF nhưng không thay tất cả các lớp bảo vệ theo threat model.
- Nếu frontend chỉ dùng bearer access token chủ động đặt trong `Authorization` header, không có auto-credentials và API thật sự stateless, có thể cân nhắc mô hình CSRF khác; vẫn cần bảo vệ token và issuer/audience/scope.
- Nếu JWT nằm trong cookie, browser vẫn có thể tự gửi nó: **JWT không tự làm ứng dụng miễn CSRF**.

Trong project mẫu, `POST /reports` vừa yêu cầu `report:create` vừa yêu cầu CSRF token. Test chứng minh một điều kiện không thay điều kiện còn lại.

## 11. Vì sao preflight phải được xử lý trước authentication?

Một preflight browser gửi `OPTIONS`, `Origin`, `Access-Control-Request-Method` và `Access-Control-Request-Headers` theo nhu cầu. Nó **không kèm cookie phiên** theo chuẩn CORS preflight. Nếu Spring Security đòi authentication trước khi CORS xử lý, request có thể bị coi là anonymous và trả 401/403, khiến frontend báo CORS error.

Spring Security hỗ trợ:

~~~java
http.cors(Customizer.withDefaults());
~~~

với `CorsConfigurationSource` phù hợp. `CorsFilter`/CORS integration xử lý preflight trước các bước cần authenticated principal. **Đây không phải lệnh cho toàn bộ OPTIONS bỏ qua mọi security**; CORS preflight được xử lý theo origin/method/header policy.

Không sửa lỗi preflight bằng:

~~~java
// SAI: mở tất cả endpoints chỉ để OPTIONS hoạt động.
http.authorizeHttpRequests(auth -> auth
    .anyRequest().permitAll());
~~~

Thay vào đó, cấu hình CORS integration và kiểm tra chính xác preflight status/headers. Actual GET/POST vẫn được Spring Security xác thực, phân quyền và bảo vệ CSRF.

### Vì sao đôi khi OPTIONS 401?

Các nguyên nhân thực tế gồm:

1. `http.cors(...)` chưa được bật hoặc source không được tìm thấy.
2. Reverse proxy/gateway từ chối OPTIONS trước khi đến ứng dụng.
3. Cấu hình nhiều `SecurityFilterChain` có chain match khác nhau và chain chứa CORS không phải chain đang xử lý.
4. Đường dẫn/method/header không nằm trong CORS allowlist.
5. Servlet filter tự viết chặn request trước CORS.
6. Preflight không được nhận diện đúng vì thiếu `Origin` hoặc `Access-Control-Request-Method`.

Hãy kiểm tra network trace và filter chain áp dụng trước khi nới lỏng quyền cho actual requests.

## 12. CORS có thể được thực thi ở nhiều lớp

CORS headers có thể được xử lý tại:

- Spring MVC `@CrossOrigin` hoặc `WebMvcConfigurer`.
- Spring Security `http.cors()` tích hợp `CorsConfigurationSource`.
- Một `CorsFilter` độc lập.
- API gateway/reverse proxy/CDN.
- Platform ingress hoặc service mesh policies.

**Tránh cấu hình CORS mâu thuẫn hoặc trùng lặp ở nhiều nơi.** Ví dụ gateway trả `Access-Control-Allow-Origin: *` nhưng app trả một origin explicit, hoặc cả hai cùng tạo nhiều header values, browser có thể từ chối response hoặc xảy ra cấu hình chia sẻ dữ liệu quá rộng.

Nếu API sau load balancer, xác định **một nguồn chính của CORS policy**, sau đó kiểm thử cả đường preflight và actual responses qua entrypoint production. Đừng chỉ test port localhost của service mà bỏ qua gateway.

### `@CrossOrigin` có thay authz không?

~~~java
// Chỉ là CORS metadata cho endpoint của controller.
@CrossOrigin(origins = "https://ui.example.test")
@GetMapping("/reports/{id}")
public String read(@PathVariable long id) {
    return "report:" + id;
}
~~~

Annotation trên không tạo principal, không gán authority, không kiểm tra tenant, và không bảo vệ dữ liệu ở service. Bạn vẫn phải có `SecurityFilterChain`/method security/domain policy thật.

Nếu app vừa dùng global CORS source vừa dùng `@CrossOrigin`, cần hiểu cơ chế kết hợp config của Spring MVC/Security; không dựa vào kết quả ngẫu nhiên.

## 13. Allowed origins, credentials, patterns và cache

### Origin allowlist: chính xác và tối thiểu

- Chỉ cho phép frontend thực sự cần gọi API.
- Tách development/staging/production, không cấp wildcard cho toàn Internet vì test local cần nhanh.
- Scheme và port rất quan trọng: `http://localhost:3000` khác `http://localhost:4200` và khác `https://localhost:3000`.
- Không dùng trailing slash trong giá trị origin; origin không bao gồm path.
- Với multi-tenant subdomain, dùng rule được kiểm soát và review kỹ, không cho tất cả subdomains không đáng tin hoặc user-controlled domains.
- Nếu có `allowedOriginPatterns`, hiểu rằng pattern matching có thể tạo allowlist rất rộng và Spring sẽ phản ánh origin phù hợp trong response. **Pattern không phải xác thực danh tính caller**.

### Credentials: tối thiểu cần thiết

Nếu frontend không cần cookie/client certificates hoặc HTTP auth credentials trong cross-origin flow, đừng bật `allowCredentials` tùy tiện. Nếu cần, dùng origin allowlist rõ ràng và xác minh policies của browser/cookie. `Access-Control-Allow-Credentials: true` không tạo cookie và không đăng nhập user.

### CORS headers và shared cache

Khi response `Access-Control-Allow-Origin` phụ thuộc `Origin` request, shared cache phải tôn trọng `Vary: Origin` để tránh trả biến thể của origin A cho origin B. Với preflight, `Access-Control-Request-Method` và `Access-Control-Request-Headers` cũng có thể ảnh hưởng biến thể response. Tùy cache/proxy, cần xem đúng `Vary` và cache configuration.

**Không đặt session/token nhạy cảm trong response chỉ vì origin được allowlist.** Cần thực thi authorization và cache-control phù hợp cho dữ liệu riêng tư.

## 14. “CORS error” trong browser có thể che giấu lỗi gốc

Trong browser, JavaScript thường chỉ nhận lỗi mạng dạng “Failed to fetch”, “blocked by CORS policy” hoặc không đọc được status/response body, vì browser không expose response cross-origin khi policy không khớp. Nguyên nhân có thể là:

- API thực sự trả `401 Unauthorized` nhưng response thiếu CORS headers.
- Server trả `403 Forbidden` vì role hoặc CSRF.
- Preflight OPTIONS bị gateway trả 404/405/401.
- `Access-Control-Allow-Origin` sai scheme/port.
- Request với `credentials: include` nhưng server trả `Access-Control-Allow-Origin: *`.
- `Access-Control-Allow-Headers` không cho phép `Authorization` hoặc `Content-Type`.
- Redirect login về origin khác không phù hợp với CORS flow.
- TLS certificate, DNS, mixed content hoặc network error thật.

**Quy trình debug:**

1. Mở browser DevTools Network, xem **OPTIONS preflight** và **actual request** là hai bước có thể khác nhau.
2. Xem `Origin` thực tế, `Access-Control-Request-Method` và `Access-Control-Request-Headers`.
3. Kiểm tra response `Access-Control-Allow-Origin`, methods, headers, credentials.
4. Kiểm tra HTTP status và log ở backend/gateway để xác định request đã tới controller chưa.
5. Nếu CORS đã pass, kiểm tra authentication, authorities, CSRF, method-security và object-level policy.
6. Dùng `curl` để kiểm tra server trực tiếp; hiểu rằng curl không mô phỏng browser CORS enforcement.
7. Không “sửa” bằng wildcard origin, tắt Spring Security hoặc chuyển mọi endpoint sang `permitAll`.

Một điểm phân biệt quan trọng: **`curl` trả 200 nhưng browser báo CORS error** có thể hoàn toàn hợp lý vì `curl` không bị same-origin policy, còn browser cần CORS headers hợp lệ. Ngược lại, **browser đọc response được** không chứng minh server đã authorization đúng; một API trả dữ liệu không có bảo vệ vẫn có thể rò rỉ cho mọi caller.

## 15. Non-browser clients và những phương án bảo vệ API thật

Để bảo vệ API khỏi clients không được cấp quyền, dùng cơ chế backend:

| Yêu cầu | Cơ chế phù hợp |
| --- | --- |
| Chỉ user hợp lệ được gọi | Authentication có thể kiểm chứng: session/OAuth2 bearer/API key phù hợp |
| Chỉ người có quyền được đọc/sửa | `hasAuthority`/`hasRole`/`@PreAuthorize` và policy |
| Chỉ chủ tài nguyên hoặc tenant đúng | Object-level authorization với dữ liệu server tin cậy |
| Service A được gọi Service B | OAuth2 client credentials, mTLS hoặc workload identity |
| Chỉ mạng nội bộ truy cập | Firewall, private networking, network policy — không thay user authz |
| Chống bot/brute force/quá tải | Rate limiting, quota, monitoring, abuse detection |
| Chống request giả mạo dùng cookie | CSRF token, SameSite và các lớp bổ trợ |
| Hạn chế cross-origin browser JS đọc response | CORS allowlist chính xác |
| Dữ liệu không vượt user/tenant | Query scoping + authorization tại service/resource boundary |

**`Origin` header không phải principal.** Một `curl -H "Origin: https://ui.example.test"` không hề chứng minh người gọi là user của UI hợp lệ. Authentication phải xác minh credentials theo chính sách; authorization sau đó phải xem principal có quyền thực hiện action trên resource hay không.

Với APIs có quyền nhạy cảm, cần kiểm tra cả tại ranh giới HTTP và domain/service: ví dụ một job scheduler hoặc message consumer gọi service trực tiếp sẽ **không đi qua CORS**, nhưng vẫn cần policy nghiệp vụ phù hợp.

## 16. Các nhầm lẫn phổ biến

| Nhầm lẫn | Vì sao sai | Cách sửa |
| --- | --- | --- |
| “CORS chỉ cho phép website A nên Postman không gọi được” | Postman không chịu browser same-origin policy | Dùng authentication/authorization/network controls |
| “`Access-Control-Allow-Origin` cấp quyền xem report” | Nó chỉ nói về browser response sharing | Dùng role/authority + object policy |
| “OPTIONS 200 nghĩa POST đã được ủy quyền” | Preflight là thỏa thuận browser method/headers, không có credentials | Kiểm tra actual request qua authn/authz/CSRF |
| “Browser báo CORS nên server không xử lý request” | Simple request có thể đã tới server | Xem network/backend logs, tránh GET side effect |
| “Dùng CORS thay CSRF” | Simple cross-site request và auto cookies vẫn nguy hiểm | Giữ CSRF cho session-based mutation |
| “`Origin` là header chỉ browser mới gửi được” | Non-browser client có thể tự đặt hoặc bỏ | Không dùng Origin để xác thực |
| “Wildcard origin + credentials cho tiện” | Browser credentialed response không được wildcard và cấu hình rộng nguy hiểm | Explicit origin allowlist |
| “Cứ `@CrossOrigin` là API đã bảo mật” | Annotation không tạo principal/quyền nghiệp vụ | SecurityFilterChain/domain authorization |
| “Mọi OPTIONS phải được permitAll mọi nơi” | Nới quyền sai mục tiêu | Xử lý CORS preflight trước Spring Security |
| “Dùng JWT thì CORS tự quyết định scope/role” | CORS không xác minh token | JwtDecoder + scope/authority mapping đáng tin |
| “CORS block là lỗi backend 403” | Có thể là browser chặn đọc response 200 | Phân biệt status thực với CORS enforcement |
| “Chỉ test từ localhost” | Không kiểm tra proxy/ingress và public hostname | Test end-to-end qua gateway và nhiều origins |

## 17. Ma trận kiểm thử cần có

Hãy tạo test suite theo các chiều **origin × credentials × authority × method × CSRF**.

| Trường hợp | CORS | Authentication | Authorization | Kỳ vọng |
| --- | --- | --- | --- | --- |
| UI được phép → OPTIONS preflight | Pass | Không cần credential cho preflight | Không cấp quyền nghiệp vụ | Trả CORS headers phù hợp |
| Origin bị cấm → OPTIONS | Reject | Không liên quan | Không cấp quyền | Browser không được gửi actual preflighted request |
| UI được phép → GET protected, chưa login | Pass | Fail | Không kiểm tra/không pass | 401 hoặc login redirect theo entry point |
| UI được phép → GET protected, sai authority | Pass | Pass | Fail | 403 |
| UI được phép → GET protected, đúng authority | Pass | Pass | Pass | 200 |
| No Origin → GET protected, đúng credential | CORS không áp dụng như browser cross-origin request | Pass | Pass | 200 |
| UI được phép → POST browser, thiếu CSRF | Pass | Pass | Bị CSRF chặn trước nghiệp vụ | 403, không mutate |
| UI được phép → POST browser, CSRF đúng, sai role | Pass | Pass | Fail | 403, không mutate |
| UI được phép → POST browser, CSRF đúng, đúng role | Pass | Pass | Pass | 2xx, đúng một mutation |
| UI được phép → report khác tenant | Pass | Pass | Object policy DENY | Không rò rỉ tài nguyên |
| Origin hợp lệ nhưng token hết hạn | Pass | Fail | Không cấp quyền | 401/appropriate auth error |
| Origin lạ, client `curl` bỏ Origin | Không tự chứng minh trust | Bắt buộc kiểm credential | Bắt buộc kiểm quyền | Không được vượt authz |

**Test chỉ có “Origin được phép → 200” chưa đủ.** Bài kiểm thử quan trọng hơn thường là “Origin được phép nhưng người thiếu quyền → 403” và “Không Origin nhưng có credential và quyền đúng → 200”, vì chúng chứng minh CORS **không là authorization**.

## 18. Câu hỏi tự kiểm tra

**Câu 1.** API chỉ trả `Access-Control-Allow-Origin: https://ui.example.test`. Một lệnh `curl` không gửi Origin có bị browser CORS chặn không?

**Đáp án:** Không có browser tham gia để thực thi same-origin policy. Server vẫn có thể xử lý request và áp dụng authentication/authorization riêng. CORS không ngăn mọi client ngoài browser.

**Câu 2.** OPTIONS preflight trả 200 từ origin UI. User không có `report:read` có được đọc report không?

**Đáp án:** Không. Preflight chỉ cho phép browser thử actual request, không tạo user/principal hoặc cấp quyền đọc báo cáo.

**Câu 3.** Một script từ site lạ gửi simple POST. Browser chặn JavaScript đọc response, vậy POST chắc chắn chưa chạy?

**Đáp án:** Không. Với simple request, actual request có thể đã được gửi tới server trước khi browser quyết định không cung cấp response. Đó là một lý do CSRF protection vẫn cần thiết cho ứng dụng dùng browser auto-credentials.

**Câu 4.** Vì sao `Access-Control-Allow-Origin: *` không dùng được cho credentialed browser requests?

**Đáp án:** Fetch/CORS không cho browser chia sẻ credentialed response với wildcard origin. Nếu cần credentials, response phải nêu origin cụ thể được phép và có header credentials phù hợp.

**Câu 5.** `@CrossOrigin` có thay `@PreAuthorize("hasAuthority('report:read')")` không?

**Đáp án:** Không. Annotation CORS điều khiển cross-origin browser behavior; authorization rule quyết định principal có đủ authority theo policy server hay không.

**Câu 6.** Vì sao Spring Security cần xử lý CORS trước authentication cho preflight?

**Đáp án:** Preflight không gửi cookie session theo chuẩn. Nếu authentication kiểm tra trước, OPTIONS có thể bị từ chối như anonymous; cấu hình CORS integration giúp trả preflight response mà không mở quyền actual requests.

**Câu 7.** Frontend dùng JWT trong cookie, có thể bỏ CSRF vì đã bật CORS chính xác không?

**Đáp án:** Không mặc nhiên. Cookie có thể được browser tự gửi; CORS không thay CSRF và không bảo đảm mọi cross-site request chưa được server xử lý.

**Câu 8.** Một user có `report:read` và xuất phát từ UI được phép nhưng report thuộc tenant khác, phải xử lý thế nào?

**Đáp án:** CORS và quyền tổng quát chưa đủ. Backend phải kiểm tra object-level/tenant authorization và từ chối tài nguyên không thuộc phạm vi cho phép.

## 19. Checklist trước khi triển khai CORS ở production

- [ ] Có danh sách frontend origins thực sự cần cross-origin browser access; không cho wildcard tùy tiện.
- [ ] Scheme/host/port đúng từng môi trường; không nhầm origin với hostname hoặc site.
- [ ] `allowCredentials` chỉ bật khi thật sự cần, không dùng `allowedOrigins("*")` cùng credentialed responses.
- [ ] Preflight xử lý đúng trước authentication trong Spring Security hoặc gateway; actual requests vẫn được kiểm tra.
- [ ] Authentication sử dụng credential có thể xác minh độc lập với `Origin`.
- [ ] Authorization kiểm tra action, authority/scope, user, owner/tenant và business policy tại server.
- [ ] CSRF và cookie/SameSite phù hợp với ứng dụng stateful; không coi CORS là cơ chế CSRF.
- [ ] CORS configuration ở gateway/MVC/Security không mâu thuẫn, không trùng lặp sai.
- [ ] Response riêng tư có cache controls phù hợp; `Vary` được kiểm tra khi origin-dependent.
- [ ] Đã test origins hợp lệ/không hợp lệ, methods, preflight, headers và credentialed requests.
- [ ] Đã test client không gửi Origin vẫn **không vượt authentication/authorization**.
- [ ] Đã test người có quyền ở origin hợp lệ nhưng không có quyền trên một resource cụ thể bị từ chối.
- [ ] Đã test POST với CSRF thiếu/sai/đúng và xác nhận **không có mutation** ở nhánh bị từ chối.
- [ ] Có cơ chế giám sát CORS errors, 401/403 thực và policy drift sau proxy/deploy.

## 20. Kết luận và tài liệu chính thức

**CORS quản lý việc web browser chia sẻ response giữa các origins; không phải security policy để quyết định ai được dùng API.** Một origin hợp lệ không tạo principal hay quyền nghiệp vụ. Một request từ `curl` hoặc backend service không bị browser same-origin policy, nên API phải luôn kiểm tra credential, authorities, object ownership, tenant và business invariants ở server.

Hãy dùng CORS allowlist để giảm bề mặt đọc dữ liệu cross-origin trong browser, đồng thời giữ nguyên các ranh giới **authentication → authorization → domain policy → CSRF (khi dùng browser auto-credentials)**. Nếu browser báo CORS error, sửa đúng nguyên nhân ở headers/preflight/proxy, không mở toàn bộ endpoints hoặc tắt Spring Security.

Tài liệu tham khảo:

- [Spring Security — CORS Integration](https://docs.spring.io/spring-security/reference/servlet/integrations/cors.html)
- [Spring Framework — CORS](https://docs.spring.io/spring-framework/reference/web/webmvc-cors.html)
- [MDN — Cross-Origin Resource Sharing (CORS)](https://developer.mozilla.org/en-US/docs/Web/HTTP/Guides/CORS)
- [MDN — Same-Origin Policy](https://developer.mozilla.org/en-US/docs/Web/Security/Defenses/Same-origin_policy)
- [MDN — Using Fetch / Credentials](https://developer.mozilla.org/en-US/docs/Web/API/Fetch_API/Using_Fetch)
- [Spring Security — Authorize HTTP Requests](https://docs.spring.io/spring-security/reference/servlet/authorization/authorize-http-requests.html)
- [Spring Security — CSRF Protection](https://docs.spring.io/spring-security/reference/servlet/exploits/csrf.html)
