# Phân biệt AuthenticationException với AccessDeniedException trong Spring Security Servlet

> **Phạm vi:** Spring Security **Servlet stack**, Java 17+, Spring Boot 3.x, Spring Security 6.x. Trọng tâm: hai họ exception `AuthenticationException` và `AccessDeniedException`, điểm phát sinh trong authentication/authorization pipeline, cách `ExceptionTranslationFilter` quyết định gọi `AuthenticationEntryPoint` hoặc `AccessDeniedHandler`, vai trò riêng của `AuthenticationFailureHandler`, HTTP 401/403/302, xử lý CSRF và method security. Các ví dụ Spring cần một dự án Boot có đầy đủ dependencies; cuối bài có chương trình Java 17 chạy độc lập bằng `javac` và stdout chính xác.

## 1. Tại sao cùng một API có thể trả 401 hoặc 403?

Xét các yêu cầu đến một hệ thống có `/private` chỉ cần đăng nhập, `/admin` yêu cầu `ROLE_ADMIN` và `POST /admin/update` phải qua CSRF protection:

1. Client chưa gửi credential gọi `GET /private`.
2. Client gửi HTTP Basic với mật khẩu sai.
3. User `bob` đăng nhập hợp lệ nhưng chỉ có `ROLE_USER`, gọi `GET /admin`.
4. User `admin` có `ROLE_ADMIN`, nhưng gửi `POST /admin/update` không có CSRF token hợp lệ.
5. User `admin` gửi credential và token hợp lệ, gọi endpoint được phép.

Một bảng quan sát thường gặp trong một API HTTP Basic:

| Tình huống | Điểm gặp lỗi | Status hay gặp |
| --- | --- | --- |
| Chưa có authentication hợp lệ | Yêu cầu xác thực | 401 và `WWW-Authenticate`. |
| Username/password sai | Authentication provider/filter | 401. |
| Đã login nhưng thiếu role | Authorization manager/filter | 403. |
| Có role nhưng POST thiếu CSRF | `CsrfFilter` | 403. |
| Đã login, có role, CSRF đúng | Cho request qua | 200 nếu controller thành công. |

**Hai số 403 không chứng minh cùng một nguyên nhân.** Trường hợp 3 là quyền truy cập không đủ, còn trường hợp 4 là kiểm tra CSRF thất bại trước khi controller chạy. Vì vậy phải phân biệt *lỗi xác thực*, *lỗi phân quyền* và *lỗi khác do security pipeline trả về*, không chỉ nhìn mã HTTP.

## 2. Định nghĩa cốt lõi

- **Authentication (xác thực):** chứng minh danh tính hoặc độ tin cậy của credential hiện tại. Thành phần liên quan có `AuthenticationManager`, `AuthenticationProvider`, `UserDetailsService`, credential validators và authentication filters.
- **Authorization (phân quyền):** quyết định danh tính đã được hệ thống nhận diện có được phép hành động trên URL/method/object không. Thành phần liên quan có `AuthorizationManager`, `AuthorizationFilter`, `@PreAuthorize`, `GrantedAuthority` và policy theo tài nguyên.
- **Exception translation:** chuyển một security exception thành hành vi HTTP cụ thể (yêu cầu đăng nhập, trả status, redirect hoặc body). Thành phần quan trọng là `ExceptionTranslationFilter` cùng các handler/entry point tương ứng.

Trong Spring Security:

~~~java
// Đây là mô tả dạng class, không tạo lại class thư viện.
org.springframework.security.core.AuthenticationException
        extends RuntimeException

org.springframework.security.access.AccessDeniedException
        extends RuntimeException
~~~

Hai loại exception trên **không kế thừa nhau**. Chúng đều là unchecked exceptions, nhưng mang ngữ nghĩa khác nhau. Không dùng `BadCredentialsException` để diễn tả một user xác thực đúng nhưng thiếu quyền xem dữ liệu.

### Bảng đối chiếu

| Khía cạnh | AuthenticationException | AccessDeniedException |
| --- | --- | --- |
| Bản chất | Xác thực thất bại hoặc chưa đủ. | Chính sách truy cập từ chối request/hành động. |
| Package | `org.springframework.security.core` | `org.springframework.security.access` |
| Ví dụ | `BadCredentialsException`, `DisabledException`, `LockedException`, `InsufficientAuthenticationException`. | Từ chối khi `hasRole`/`hasAuthority`; deny từ method security; các CSRF exception liên quan. |
| Có luôn là password sai? | Không. | Không liên quan trực tiếp tới việc so password. |
| Xử lý HTTP thường gặp | Entry point hoặc login failure handler. | Access denied handler, hoặc entry point nếu user chưa xác thực đầy đủ. |
| HTTP status bất biến? | Không: có thể 401 hoặc redirect 302, v.v. | Không: có thể 403, 401/302 nếu bị chuyển sang authentication. |
| Được phép tự động trả raw exception message? | Không khuyến nghị. | Không khuyến nghị. |

Một error response công khai nên nói vừa đủ để client xử lý, không cung cấp credentials, tên policy/role nhạy cảm hoặc thông tin giúp username enumeration.

## 3. Các kiểu AuthenticationException và ý nghĩa

| Subclass thường gặp | Tình huống | Điều nên nhớ |
| --- | --- | --- |
| `BadCredentialsException` | Credential sai. | Không đưa password vào log hoặc body trả client. |
| `UsernameNotFoundException` | `UserDetailsService` không tìm thấy user. | `DaoAuthenticationProvider` thường che nó thành `BadCredentialsException` để giảm lộ tài khoản có tồn tại hay không. |
| `DisabledException` | Account đã bị vô hiệu hóa. | Không tự bật lại account khi failure handler chạy. |
| `LockedException` | Account bị khóa. | UX phục hồi phải theo chính sách sản phẩm. |
| `AccountExpiredException` | Account hết hạn. | Khác với password/token hết hạn. |
| `CredentialsExpiredException` | Credential không còn hiệu lực. | Có thể cần flow đổi credential. |
| `AuthenticationServiceException` | Một số lỗi dịch vụ xác thực. | Phân biệt sự cố hạ tầng và sai credential trong metrics nội bộ. |
| `InsufficientAuthenticationException` | Authentication chưa đạt mức tin cậy mà policy yêu cầu. | Không nhất thiết do password sai. |
| `AuthenticationCredentialsNotFoundException` | Không có authentication cần thiết tại điểm bảo vệ. | Có thể phát sinh trong method security. |

Authentication failure còn có thể liên quan bearer token không hợp lệ/hết hạn hoặc yêu cầu step-up/MFA. Đừng định nghĩa authentication chỉ là username/password. Một token còn hạn nhưng không đủ scope là vấn đề phân quyền; một token giả chữ ký hay hết hạn thường thuộc nhánh xác thực.

### Vì sao BadCredentialsException không dành cho trường hợp thiếu role?

~~~java
// MẢNH CODE dùng trong custom AuthenticationProvider:
if (!passwordEncoder.matches(rawPassword, storedPasswordHash)) {
    throw new BadCredentialsException("Invalid credentials");
}
~~~

Ở đây `BadCredentialsException` đúng vì credential verification thất bại. Mã là fragment, không biên dịch độc lập nếu chưa có `passwordEncoder`, `rawPassword`, `storedPasswordHash` và import thích hợp. Trong production phải có cơ chế chống brute force, bảo vệ timing, hashing password mạnh và log an toàn.

~~~java
// PHẢN VÍ DỤ: không làm thế này khi thiếu quyền.
if (!principalHasRoleAdmin) {
    throw new BadCredentialsException("Not an admin");
}
~~~

Đoạn thứ hai là **sai về ngữ nghĩa**: một user hợp lệ có thể thiếu quyền admin. Nếu ném sai exception, authentication metrics có thể bị nhiễu, frontend bị ép login lại vô ích và hệ thống không phản ánh đúng authorization denial.

## 4. Các tình huống AccessDeniedException

Ví dụ trong `authorizeHttpRequests`:

~~~java
http.authorizeHttpRequests(auth -> auth
    .requestMatchers("/admin/**").hasRole("ADMIN")
    .anyRequest().authenticated());
~~~

User `bob` có `ROLE_USER` nhưng thiếu `ROLE_ADMIN` sẽ bị authorization từ chối khi gọi `/admin/**`. Khi policy đang dùng Spring Security authorization manager chuẩn, nhánh exception có thể là `AccessDeniedException` hoặc một subclass mang kết quả authorization tương ứng. Các bản Spring Security 6.x mới có type `AuthorizationDeniedException`, nhưng constructor/API có thể khác theo minor release; ví dụ này không tự khởi tạo nó.

Trong method security:

~~~java
@PreAuthorize("hasAuthority('REPORT_EXPORT')")
public String exportReport() {
    return "report-data";
}
~~~

Nếu method được gọi qua Spring-managed proxy và user thiếu `REPORT_EXPORT`, denial xảy ra **tại service** dù URL rule phía ngoài có thể cho phép authenticated user vào. Vì vậy một `AccessDeniedException` không nhất thiết được tạo bởi HTTP `AuthorizationFilter`.

### CSRF có liên hệ nhưng không đồng nhất với quyền role

`MissingCsrfTokenException` và `InvalidCsrfTokenException` thuộc nhóm CSRF exception có quan hệ với `AccessDeniedException`, nhưng `CsrfFilter` thường có `AccessDeniedHandler` riêng và có thể trả 403 ngay tại filter này.

~~~text
POST /admin/update
Authenticated user: admin
Authorities: [ROLE_ADMIN]
CSRF token: missing
CsrfFilter: reject
HTTP: 403
~~~

Không được kết luận `hasRole("ADMIN")` từ chối; request có thể **chưa đến** AuthorizationFilter. Với kiểm thử HTTP POST, muốn chứng minh role check hoạt động, gửi CSRF token hợp lệ, ví dụ `.with(csrf())` trong `MockMvc`.

### AccessDeniedException cũng có thể là lỗi theo đối tượng

Một service kiểm tra ownership/tenant của order/document có thể ném denied exception nếu principal có quyền đọc tổng quát nhưng không sở hữu bản ghi được yêu cầu. Phải kiểm tra **dữ liệu phía server** và trước side effect, không tự tin vào owner ID hoặc role do client gửi. Một policy trả 404 thay vì 403 để không lộ sự tồn tại của tài nguyên cần có thiết kế nhất quán và không vô tình trả dữ liệu trái phép.

## 5. ExceptionTranslationFilter: trái tim của việc chuyển exception thành response

`ExceptionTranslationFilter` là một bridge giữa security exceptions và giao thức HTTP. Nó **không kiểm chứng password** và **không tự cấp authorities**. Nó bao một phần filter chain phía sau, nhận security exceptions đi lên và quyết định gọi đúng entry point/handler.

~~~text
ExceptionTranslationFilter
    |
    v
chain.doFilter(request, response)
    |
    +-- AuthenticationException từ downstream
    |       -> yêu cầu authentication
    |       -> AuthenticationEntryPoint
    |       -> 401 / redirect / scheme-specific response
    |
    +-- AccessDeniedException từ downstream
    |       |
    |       +-- Anonymous hoặc remember-me chưa đủ mức
    |       |       -> khởi động authentication
    |       |       -> AuthenticationEntryPoint
    |       |
    |       +-- Authenticated đủ mức theo trust resolver
    |               -> AccessDeniedHandler
    |               -> thường 403
    |
    +-- Exception không thuộc hai họ này
            -> không tự bị dịch thành 401/403
               theo logic security exceptions
~~~

### Trường hợp quan trọng: denied nhưng client nhận 401/302

Một request **anonymous** có thể tới `AuthorizationFilter`, manager thấy policy cần authenticated và ném AccessDeniedException. `ExceptionTranslationFilter` dùng `AuthenticationTrustResolver` nhận diện rằng user anonymous/remember-me chưa có mức xác thực phù hợp, nên khởi động authentication qua `AuthenticationEntryPoint` **thay vì** trả forbidden ngay.

- HTTP Basic API: thường 401 và header `WWW-Authenticate: Basic ...`.
- Form login: thường redirect 302 tới `/login`.
- Bearer resource server: entry point tương ứng token, có thể trả 401 kèm Bearer challenge.

Như vậy, **AccessDeniedException không bảo đảm HTTP 403**. Một yêu cầu chưa xác thực có thể rơi vào authorization denial nhưng HTTP response vẫn mang nghĩa “hãy xác thực”.

### AnonymousAuthenticationToken không bằng user đăng nhập

`AnonymousAuthenticationFilter` có thể đưa `AnonymousAuthenticationToken` vào SecurityContext. Token này có thể có `isAuthenticated()` true theo implementation, nhưng Spring Security dùng trust resolver để phân biệt anonymous với user đã xác thực theo chính sách. Không chỉ nhìn boolean đó rồi tự gắn tất cả denial vào nhánh 403.

### Remember-me không luôn đủ để truy cập tác vụ nhạy cảm

Một user có remember-me authentication có thể cần đăng nhập đầy đủ hoặc step-up ở một số policy. Khi denial xảy ra, entry point có thể được dùng để yêu cầu xác thực lại; điều này không có nghĩa password user vừa nhập sai.

### SecurityContext và RequestCache

Khi bắt đầu authentication, ExceptionTranslationFilter có thể làm sạch context theo flow, lưu SavedRequest qua `RequestCache` rồi kích hoạt entry point. Với ứng dụng form login, SavedRequest hỗ trợ điều hướng lại trang mà user định truy cập sau khi login; với stateless APIs, thường cần policy request cache khác hoặc không lưu session. Không gán hành vi lưu session mặc định cho mọi chain.

## 6. Tại sao ExceptionTranslationFilter không bắt được mọi lỗi đăng nhập?

Một authentication filter có thể **nằm phía trước ExceptionTranslationFilter** trong standard Servlet filter chain, và có luồng failure riêng:

- `UsernamePasswordAuthenticationFilter` kế thừa `AbstractAuthenticationProcessingFilter`. Khi username/password không hợp lệ, nó thường gọi `AuthenticationFailureHandler`, chẳng hạn redirect về `/login?error`.
- `BasicAuthenticationFilter` có xử lý failure riêng và sử dụng `AuthenticationEntryPoint` theo cấu hình cho HTTP Basic.
- Bearer token authentication filter có error handling phù hợp với resource server/Bearer scheme.

Vì vậy không thể chỉ sửa `ExceptionTranslationFilter` rồi giả định mọi form-login password failure sẽ đi qua. Hãy xác định **filter nào xử lý request**, **exception có được filter đó catch hay không**, và **handler nào thực sự sinh response**.

### Ba thành phần hay bị nhầm

| Component | Khi nào dùng |
| --- | --- |
| `AuthenticationFailureHandler` | Khi **một login attempt cụ thể** thất bại trong authentication filter (đặc biệt form login). |
| `AuthenticationEntryPoint` | Khi cần **bắt đầu/yêu cầu authentication** cho request chưa đủ credential; cũng có thể dùng ở authentication filters. |
| `AccessDeniedHandler` | Khi policy từ chối user đã có authentication đầy đủ theo flow. |

Một web app có thể dùng cả ba: POST /login sai password → failure handler; GET /private anonymous → entry point; GET /admin với user thiếu role → denied handler. Chúng khác nhau về điểm phát sinh và kỳ vọng UX.

## 7. 401, 403 và 302 không có ánh xạ 1–1 với exception

### 401 Unauthorized

Theo semantics HTTP, 401 thường báo request chưa có authentication credentials hợp lệ. Với HTTP Basic, response có thể chứa:

~~~http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Basic realm="api"
~~~

Với bearer, scheme/header khác. Không gửi 401 Basic mà thiếu challenge phù hợp khi client cần xác thực theo protocol.

### 403 Forbidden

403 thường thể hiện server từ chối thực hiện request:

~~~http
HTTP/1.1 403 Forbidden
~~~

Một user đã xác thực nhưng thiếu quyền là trường hợp điển hình, **không phải duy nhất**. CSRF, gateway/WAF, controller hoặc resource policy cũng có thể trả 403.

### 302 redirect

Với form login:

~~~http
HTTP/1.1 302 Found
Location: /login
~~~

Request protected anonymous thường được đưa đến trang login, còn POST login sai thường do failure handler chuyển đến `/login?error`. Đừng coi mọi redirect là authentication thành công, và đừng coi form-login denial phải luôn là 401.

### Ma trận để nhớ

| Nguyên nhân thực | HTTP Basic thường thấy | Form login thường thấy |
| --- | --- | --- |
| Không có credential gọi private | 401 | 302 login. |
| Credential sai | 401 | 302 login?error. |
| User authenticated thiếu role | 403 | 403. |
| POST thiếu CSRF token | 403 | 403. |
| Đủ credential, đủ quyền | Tùy controller, thường 200 | Tùy controller, thường 200. |

Các giá trị là **thường gặp**, không phải cam kết về mọi project: một custom entry point/handler, nhiều chains hoặc API framework có thể đổi response.

## 8. Ví dụ Spring Boot 3 và Java 17: API HTTP Basic

Ví dụ sử dụng HTTP Basic để phân biệt anonymous, credential sai và thiếu role mà không cần cookie/browser. Giữ CSRF mặc định bật để minh họa **403 từ CSRF không phải 403 từ role**. Bật method security để kiểm tra denial ở service.

### Dependencies và cấu trúc

Tạo project Java 17+ Spring Boot 3.x với:

~~~text
spring-boot-starter-web
spring-boot-starter-security
spring-boot-starter-aop       (nêu rõ cơ chế proxy method)
spring-boot-starter-test      (scope test)
spring-security-test         (scope test)
~~~

Đặt mã trong cùng package `com.example.exceptionlesson`:

~~~text
src/main/java/com/example/exceptionlesson/
  ExceptionLessonApplication.java
  SecurityConfig.java
  ReportService.java
  DemoController.java

src/test/java/com/example/exceptionlesson/
  SecurityExceptionIntegrationTest.java
~~~

**Lưu ý:** Spring Boot 3.x tương thích với những minor Spring Security 6.x cụ thể do BOM quản lý. Không nâng riêng lẻ một artifact Security mà không kiểm tra compatibility. Demo không có database và không sử dụng mật khẩu thật.

### 8.1. SecurityConfig.java

~~~java
package com.example.exceptionlesson;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
@EnableMethodSecurity
public class SecurityConfig {

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    UserDetailsService users(PasswordEncoder encoder) {
        UserDetails admin = User.withUsername("admin")
                .password(encoder.encode("admin-demo-only"))
                .authorities("ROLE_ADMIN", "REPORT_EXPORT")
                .build();

        UserDetails bob = User.withUsername("bob")
                .password(encoder.encode("bob-demo-only"))
                .authorities("ROLE_USER")
                .build();

        return new InMemoryUserDetailsManager(admin, bob);
    }

    @Bean
    SecurityFilterChain apiSecurity(HttpSecurity http)
            throws Exception {

        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/public").permitAll()
                .requestMatchers(HttpMethod.GET, "/private")
                    .authenticated()
                .requestMatchers(HttpMethod.GET, "/admin")
                    .hasRole("ADMIN")
                .requestMatchers(HttpMethod.POST, "/admin/update")
                    .hasRole("ADMIN")

                // HTTP: chỉ cần authenticated.
                // Service: phải có REPORT_EXPORT.
                .requestMatchers(HttpMethod.GET, "/reports/export")
                    .authenticated()
                .anyRequest().denyAll())
            .httpBasic(Customizer.withDefaults());

        // Không tắt CSRF để demo thể hiện đúng 403 do token.
        return http.build();
    }
}
~~~

Các rule:

1. `/public` là public.
2. `GET /private` yêu cầu authentication nhưng không yêu cầu role admin.
3. `GET /admin` và `POST /admin/update` yêu cầu authority `ROLE_ADMIN` qua `hasRole("ADMIN")`.
4. `GET /reports/export` yêu cầu login ở tầng HTTP, sau đó `@PreAuthorize` của service kiểm tra `REPORT_EXPORT`.
5. `anyRequest().denyAll()` bảo vệ route/method chưa khai báo.
6. `httpBasic(...)` giúp test gửi Basic credentials trực tiếp. Không dùng Basic qua HTTP plaintext trong production; dùng TLS và bảo vệ credentials.
7. `BCryptPasswordEncoder` phù hợp cho password demo; các chuỗi `admin-demo-only` và `bob-demo-only` chỉ là tài khoản thử nghiệm, không đưa vào môi trường thật.

### 8.2. ReportService.java

~~~java
package com.example.exceptionlesson;

import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.stereotype.Service;

@Service
public class ReportService {

    @PreAuthorize("hasAuthority('REPORT_EXPORT')")
    public String export() {
        return "report-data";
    }
}
~~~

Lời gọi phải đi qua Spring-managed bean/proxy để method security áp dụng. Nếu bạn tự dùng `new ReportService()` hoặc self-invocation trong cùng bean, AOP method advice có thể không chạy. Không dùng `@PreAuthorize` như cách thay thế kiểm tra owner/tenant của bản ghi trong service nghiệp vụ.

### 8.3. DemoController.java

~~~java
package com.example.exceptionlesson;

import org.springframework.security.core.Authentication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class DemoController {

    private final ReportService reports;

    public DemoController(ReportService reports) {
        this.reports = reports;
    }

    @GetMapping("/public")
    public String publicPage() {
        return "public";
    }

    @GetMapping("/private")
    public String privatePage(Authentication authentication) {
        return "hello:" + authentication.getName();
    }

    @GetMapping("/admin")
    public String adminPage() {
        return "admin";
    }

    @PostMapping("/admin/update")
    public String updateAdmin() {
        // Demo chỉ trả chuỗi, không thay đổi DB.
        return "updated";
    }

    @GetMapping("/reports/export")
    public String export() {
        return reports.export();
    }
}
~~~

### 8.4. ExceptionLessonApplication.java

~~~java
package com.example.exceptionlesson;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ExceptionLessonApplication {
    public static void main(String[] args) {
        SpringApplication.run(ExceptionLessonApplication.class, args);
    }
}
~~~

Với Maven Wrapper của project, chạy:

~~~bash
./mvnw spring-boot:run
~~~

Có thể kiểm thử trực tiếp bằng curl (chỉ trên localhost với credential giả):

~~~bash
# Public:
curl -i http://localhost:8080/public

# Anonymous cần authentication:
curl -i http://localhost:8080/private

# Bob hợp lệ nhưng thiếu quyền admin:
curl -i -u bob:bob-demo-only \
  http://localhost:8080/admin

# Admin hợp lệ:
curl -i -u admin:admin-demo-only \
  http://localhost:8080/admin
~~~

Theo cấu hình demo, các status logic tương ứng là 200, 401, 403 và 200. Đừng đưa credential thật lên command line (có thể lộ trong shell history/process list); ví dụ dùng local user giả. Các HTTP headers/body do server tạo còn phụ thuộc version/container, không có transcript cố định.

## 9. MockMvc: chứng minh cả authentication và authorization

Mã test sau chạy qua `SecurityFilterChain`, không chỉ gọi Java method mock. Với Spring Boot 3 và `spring-security-test`, tạo `src/test/java/com/example/exceptionlesson/SecurityExceptionIntegrationTest.java`:

~~~java
package com.example.exceptionlesson;

import static org.springframework.security.test.web.servlet.request
        .SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.security.test.web.servlet.request
        .SecurityMockMvcRequestPostProcessors.httpBasic;
import static org.springframework.test.web.servlet.request
        .MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request
        .MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result
        .MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result
        .MockMvcResultMatchers.status;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

@SpringBootTest
@AutoConfigureMockMvc
class SecurityExceptionIntegrationTest {

    @Autowired
    MockMvc mvc;

    @Test
    void publicEndpointDoesNotNeedAuthentication()
            throws Exception {
        mvc.perform(get("/public"))
            .andExpect(status().isOk())
            .andExpect(content().string("public"));
    }

    @Test
    void anonymousPrivateRequestGets401() throws Exception {
        mvc.perform(get("/private"))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void wrongPasswordGets401() throws Exception {
        mvc.perform(get("/private")
                .with(httpBasic("bob", "wrong")))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void validBasicAuthenticationCanAccessPrivate()
            throws Exception {
        mvc.perform(get("/private")
                .with(httpBasic("bob", "bob-demo-only")))
            .andExpect(status().isOk())
            .andExpect(content().string("hello:bob"));
    }

    @Test
    void validUserWithoutAdminAuthorityGets403()
            throws Exception {
        mvc.perform(get("/admin")
                .with(httpBasic("bob", "bob-demo-only")))
            .andExpect(status().isForbidden());
    }

    @Test
    void adminCanAccessAdminEndpoint() throws Exception {
        mvc.perform(get("/admin")
                .with(httpBasic("admin", "admin-demo-only")))
            .andExpect(status().isOk())
            .andExpect(content().string("admin"));
    }

    @Test
    void missingCsrfGives403DespiteHavingAdminRole()
            throws Exception {
        mvc.perform(post("/admin/update")
                .with(httpBasic("admin", "admin-demo-only")))
            .andExpect(status().isForbidden());
    }

    @Test
    void missingRoleGives403AfterValidCsrf()
            throws Exception {
        mvc.perform(post("/admin/update")
                .with(csrf())
                .with(httpBasic("bob", "bob-demo-only")))
            .andExpect(status().isForbidden());
    }

    @Test
    void adminWithValidCsrfCanPost() throws Exception {
        mvc.perform(post("/admin/update")
                .with(csrf())
                .with(httpBasic("admin", "admin-demo-only")))
            .andExpect(status().isOk())
            .andExpect(content().string("updated"));
    }

    @Test
    void methodSecurityAlsoRaisesAuthorizationDenial()
            throws Exception {
        mvc.perform(get("/reports/export")
                .with(httpBasic("bob", "bob-demo-only")))
            .andExpect(status().isForbidden());

        mvc.perform(get("/reports/export")
                .with(httpBasic("admin", "admin-demo-only")))
            .andExpect(status().isOk())
            .andExpect(content().string("report-data"));
    }
}
~~~

**Cách đọc các assertion:**

- `GET /private` anonymous 401 và password sai 401 là **hai nguyên nhân khác nhau** cùng status.
- Bob được truy cập `/private` khi dùng credential đúng, chứng minh user thực sự authenticated.
- Bob thiếu `ROLE_ADMIN` ở `GET /admin` dẫn đến denial 403.
- Admin đủ role vào `GET /admin` được 200.
- Admin POST thiếu CSRF 403 dù role đúng. Test này **không** xác nhận `hasRole`.
- Bob POST với `csrf()` hợp lệ nhưng thiếu role cũng 403: điều kiện CSRF không che kết quả authorization.
- Admin POST với `csrf()` được 200, xác nhận cả hai lớp bảo vệ.
- Bob qua HTTP-level `authenticated()` nhưng bị `@PreAuthorize` từ chối tại service, cho thấy method security cũng tạo denied flow.
- `@WithMockUser` là công cụ tốt cho unit-test authorization nhưng không đủ để test credential sai: nó có thể bỏ qua bước authentication provider và Basic filter.

Chạy trong Maven project:

~~~bash
./mvnw test
~~~

Test mô tả kỳ vọng với cấu hình và dependencies đã nêu, **không tuyên bố đã thực thi test trên một project cụ thể**. Khi có nhiều `SecurityFilterChain` hoặc custom exception handlers, các status có thể khác, cần kiểm chứng trên đúng chain thật.

## 10. Tùy biến response cho REST API

Một frontend có thể yêu cầu error body có cấu trúc (ví dụ `application/problem+json`). Hãy thiết kế response thống nhất nhưng **không gộp** authentication, authorization, CSRF, validation và lỗi server thành cùng một nhánh.

### AuthenticationEntryPoint

Khi request cần authentication, entry point có thể tạo 401. Với HTTP Basic, cần giữ challenge:

~~~java
// MẢNH CODE cho một bean AuthenticationEntryPoint.
// Cần import javax/jakarta theo Servlet API của project;
// Spring Boot 3 dùng jakarta.servlet.
@Bean
AuthenticationEntryPoint apiEntryPoint() {
    return (request, response, exception) -> {
        response.setStatus(401);
        response.setHeader(
            "WWW-Authenticate", "Basic realm=\"demo\"");
        response.setContentType("application/problem+json;charset=UTF-8");
        response.getWriter().write(
            "{\"title\":\"Unauthorized\",\"status\":401}");
    };
}
~~~

Mảnh này cần đặt trong class `@Configuration` và import `org.springframework.context.annotation.Bean`, `org.springframework.security.web.AuthenticationEntryPoint`. Không log raw `exception` hoặc phản chiếu nội dung exception message ra client.

### AccessDeniedHandler

~~~java
// MẢNH CODE cho bean AccessDeniedHandler.
@Bean
AccessDeniedHandler apiDeniedHandler() {
    return (request, response, exception) -> {
        response.setStatus(403);
        response.setContentType("application/problem+json;charset=UTF-8");
        response.getWriter().write(
            "{\"title\":\"Forbidden\",\"status\":403}");
    };
}
~~~

Cần import `org.springframework.security.web.access.AccessDeniedHandler`. Cơ chế này dùng cho những denial được chuyển đến handler; nó **không tự định nghĩa toàn bộ authorization policy**.

Gắn các bean vào chain (mảnh thay thế cấu hình, không trộn vào demo ban đầu mà không kiểm thử):

~~~java
http
    .exceptionHandling(ex -> ex
        .authenticationEntryPoint(apiEntryPoint)
        .accessDeniedHandler(apiDeniedHandler))
    .httpBasic(basic -> basic
        .authenticationEntryPoint(apiEntryPoint));
~~~

Trong mảnh trên, `apiEntryPoint` và `apiDeniedHandler` là biến kiểu interface được injection vào method cấu hình; tránh nhầm với việc gọi factory method `@Bean` tùy tiện. Chú ý `httpBasic` có entry point riêng cho lỗi credential ở Basic filter nên cần gắn đúng kênh.

### Form login còn có failure handler khác

Nếu ứng dụng sử dụng form login, ví dụ:

~~~java
http.formLogin(form -> form
    .failureUrl("/login?error"));
~~~

thì một POST /login sai password thường được `UsernamePasswordAuthenticationFilter` chuyển cho failure handler, chứ không được xử lý duy nhất bằng custom entry point. Để thống nhất JSON response cho login API, cần xác định authentication mechanism và cấu hình failure handler của nó đúng cách; đừng chỉ thay `AccessDeniedHandler`.

### CSRF error handler cũng có đường riêng

`CsrfFilter` thường dùng `AccessDeniedHandler` của nó. Một JSON denied handler được đăng ký ở `exceptionHandling(...)` không được mặc định suy là sẽ format mọi CSRF failure. Nếu client cần cùng error schema cho CSRF, phải review cấu hình CSRF-specific handler tương thích với Spring Security version và test POST không/sai token.

## 11. Lưu ý HTTP protocol cho Basic và Bearer

401 không chỉ là một status:

~~~http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Basic realm="demo"
~~~

Một HTTP Basic client cần biết server yêu cầu scheme nào. Với Bearer, challenge thường dùng `Bearer`, và resource server có thể trả thông tin lỗi tuân thủ đặc tả OAuth2 phù hợp. Không tự áp Basic challenge cho JWT endpoint hoặc ngược lại.

403 là phản hồi từ chối dù client hiểu yêu cầu:

~~~http
HTTP/1.1 403 Forbidden
~~~

Nó có thể là thiếu role/scope hoặc một lớp security khác. Trên browser app, HTTP redirect tới login có thể thuận tiện cho anonymous; với REST clients, nên dùng status và body nhất quán theo contract. Khi user authenticated nhưng không có quyền, tránh đưa danh sách role đang thiếu ra response công khai.

## 12. Luồng form login: cùng exception nhưng response khác

Một web ứng dụng có form login thường có các nhánh:

~~~text
GET /private anonymous
  -> authorization cần xác thực
  -> ExceptionTranslationFilter khởi động login
  -> AuthenticationEntryPoint
  -> thường 302 Location: /login

POST /login sai password, CSRF hợp lệ
  -> UsernamePasswordAuthenticationFilter
  -> BadCredentialsException
  -> AuthenticationFailureHandler
  -> thường 302 Location: /login?error

POST /login thiếu CSRF
  -> CsrfFilter từ chối
  -> thường 403

GET /admin sau login nhưng chỉ ROLE_USER
  -> Authorization manager deny
  -> AccessDeniedHandler
  -> thường 403
~~~

Trong flow này, một failure handler chuyên cho POST login khác với entry point khởi động login do request protected. Nên kiểm thử cả hai, đặc biệt khi custom login endpoint hoặc chuyển sang SPA.

**Đừng trộn HTTP 302 redirect và HTTP 401 cho tất cả clients mà không phân biệt request.** Một browser frontend cần redirect, trong khi API client có thể cần nhận 401 JSON để quyết định refresh token hoặc hiển thị login. Chọn explicit security chain và entry point nếu ứng dụng hỗ trợ cả UI/session và token API.

## 13. Những nhầm lẫn cần tránh

| Nhầm lẫn | Vì sao sai | Cách kiểm tra |
| --- | --- | --- |
| `AuthenticationException` luôn 401 | Form login có thể redirect; failure handler khác entry point. | Test filter thực tế. |
| `AccessDeniedException` luôn 403 | Anonymous/remember-me có thể được chuyển sang entry point. | Kiểm tra trust resolver/context. |
| Mọi 403 là thiếu quyền | CSRF, gateway, controller cũng trả 403. | Test CSRF riêng và theo dõi nguồn lỗi. |
| `BadCredentialsException` để báo thiếu admin role | Sai ngữ nghĩa, metrics và UX. | Dùng authorization policy/denial. |
| Dùng một `@ControllerAdvice(Exception.class)` bắt tất cả | Lỗi ở security filters có thể xảy ra trước MVC. | Dùng security handlers đúng tầng. |
| Tắt CSRF vì POST thiếu quyền luôn 403 | Che lỗi thay vì kiểm thử role. | Dùng `csrf()` trong MockMvc. |
| Dùng `@WithMockUser` để test password | Mock user bỏ qua credential validation. | Gửi credential từ test fixture. |
| JSON handler phản chiếu raw exception | Có thể lộ thông tin nhạy cảm. | Generic client error + redacted internal audit. |
| 401 Basic mà không có `WWW-Authenticate` | Sai kỳ vọng HTTP authentication challenge. | Assert headers. |
| 403 bị biến thành 200 với error body | Client có thể hiểu request thành công. | Giữ status chuẩn. |
| Proxy lỗi 403 đều tính là Spring authorization | Request có thể chưa tới app. | Đối chiếu gateway và application logs. |
| Access denied sau service mutation | 403 không rollback thay đổi trước đó. | Kiểm tra authorization trước side effects và transaction. |

## 14. Logging và metrics đúng ngữ nghĩa

Có thể phân nhóm metrics theo nguồn thực sự:

~~~text
security.authentication.failure
security.authorization.denied
security.csrf.rejected
http.server.requests{status="401"}
http.server.requests{status="403"}
~~~

Các tên trên chỉ là **gợi ý**; không khẳng định Spring tự tạo đủ chúng. Để phân biệt nguyên nhân:

- Authentication failures có thể được lấy qua `AuthenticationEventPublisher`, failure handler hoặc instrumentation Basic/Bearer tùy flow.
- Authorization denied có thể được quan sát qua `AuthorizationEventPublisher` và denied events nếu tích hợp đúng, hoặc access-denied handling.
- CSRF failure cần instrumentation phù hợp với `CsrfFilter`, không nên xem tất cả 403 là CSRF.
- HTTP server metrics đo status cuối; một 403 không chỉ ra nguồn lỗi.
- Một request có thể có nhiều authorization checks. Tổng events không nhất thiết bằng số HTTP requests duy nhất.

Không log password, token, API key, session cookie, `Authorization` header hoặc CSRF token. Tránh `exception.toString()`/`Authentication.toString()` nguyên vẹn nếu không kiểm soát được dữ liệu đi kèm. Audit có thể ghi mã lỗi nội bộ, route template, http method, correlation ID, service, policy ID và principal đã pseudonymize nếu cần, theo retention/access control thích hợp.

## 15. Trình tự chẩn đoán 401/403

1. **Xác nhận đúng service và SecurityFilterChain**: URL, context path, method và `securityMatcher`.
2. **Nhìn authentication mechanism**: form/session, HTTP Basic, bearer, custom filter.
3. **Xác nhận credential/authentication state**: anonymous, remember-me, authenticated hay invalid token/credentials.
4. **Xác định exception đến từ đâu**: authentication provider/filter, authorization manager, method security, CsrfFilter, gateway/controller.
5. **Xác minh GrantedAuthority**: `ROLE_ADMIN` và `ADMIN` khác nhau; scope cũng thường có prefix `SCOPE_`.
6. **Xem entry point/handler**: `AuthenticationFailureHandler`, `AuthenticationEntryPoint`, `AccessDeniedHandler`, CSRF-specific handler.
7. **Nếu test POST**: có CSRF hợp lệ chưa? Nếu không, 403 không xác nhận rule WRITE.
8. **Nếu method security**: `@EnableMethodSecurity` và proxy có hoạt động không?
9. **Kiểm tra response contract**: status, challenge header, redirect, content type, không lộ secrets.
10. **Kiểm thử cả positive lẫn negative**: user hợp lệ có quyền phải được vào; sai password và thiếu role phải bị xử lý khác nhau theo contract.
11. **Tách observability**: metrics authentication, authorization, CSRF và gateway không bị gộp nhầm.
12. **Không nới quyền để chữa lỗi**: không dùng `permitAll()`, tắt CSRF hoặc cấp `ROLE_ADMIN` cho mọi user chỉ vì có 403.

## 16. Java 17 độc lập: mô phỏng hai nhánh exception

Tạo file `ExceptionBoundaryDemo.java`. Đây là **mô hình Java SE**, không import thư viện Spring; hai exception trong mã chỉ minh họa hai loại lỗi.

~~~java
public final class ExceptionBoundaryDemo {

    static final class DemoAuthenticationFailure
            extends RuntimeException {
    }

    static final class DemoAccessDenied
            extends RuntimeException {
    }

    static String request(
            boolean credentialsPresented,
            boolean credentialsValid,
            boolean hasAdminRole) {
        try {
            if (!credentialsPresented || !credentialsValid) {
                throw new DemoAuthenticationFailure();
            }
            if (!hasAdminRole) {
                throw new DemoAccessDenied();
            }
            return "200 ALLOWED";
        } catch (DemoAuthenticationFailure e) {
            return "401 AUTHENTICATION_REQUIRED";
        } catch (DemoAccessDenied e) {
            return "403 ACCESS_DENIED";
        }
    }

    public static void main(String[] args) {
        System.out.println("anonymous="
                + request(false, false, false));
        System.out.println("wrongPassword="
                + request(true, false, false));
        System.out.println("missingRole="
                + request(true, true, false));
        System.out.println("admin="
                + request(true, true, true));

        // Phân biệt lỗi CSRF ở tầng khác.
        System.out.println("missingCsrf=403 CSRF_REJECTED");
    }
}
~~~

Chạy JDK 17 trở lên:

~~~bash
javac ExceptionBoundaryDemo.java
java ExceptionBoundaryDemo
~~~

Stdout **chính xác**:

~~~text
anonymous=401 AUTHENTICATION_REQUIRED
wrongPassword=401 AUTHENTICATION_REQUIRED
missingRole=403 ACCESS_DENIED
admin=200 ALLOWED
missingCsrf=403 CSRF_REJECTED
~~~

Mã không thực hiện HTTP/CSRF thật và không phản ánh `ExceptionTranslationFilter` đầy đủ: trong Spring Security thực, AccessDeniedException với anonymous vẫn có thể kích hoạt 401 hoặc 302; form login failure có thể redirect; status tùy các handler và authentication mechanism. Chương trình dùng để nhớ **nguồn lỗi** và sự khác biệt giữa authentication, authorization và CSRF, không thay thế integration tests.

## 17. Ma trận kiểm thử tổng hợp

| Tình huống | Status demo Basic | Ý nghĩa |
| --- | --- | --- |
| Anonymous GET /public | 200 | PermitAll. |
| Anonymous GET /private | 401 | Start authentication. |
| GET /private với password sai | 401 | Authentication failure. |
| Bob GET /private đúng password | 200 | Authenticated. |
| Bob GET /admin | 403 | Thiếu ROLE_ADMIN. |
| Admin GET /admin | 200 | Có ROLE_ADMIN. |
| Admin POST /admin/update thiếu CSRF | 403 | CSRF reject. |
| Bob POST /admin/update với CSRF | 403 | Authorization reject. |
| Admin POST /admin/update với CSRF | 200 | Qua cả hai lớp. |
| Bob GET /reports/export | 403 | Method security reject. |
| Admin GET /reports/export | 200 | Có REPORT_EXPORT. |
| Form login anonymous truy cập private | Thường 302 | Entry point login page. |
| Form login password sai | Thường 302 /login?error | AuthenticationFailureHandler. |
| Bearer token sai/hết hạn | Thường 401 | Bearer authentication entry point. |
| Bearer token hợp lệ thiếu scope | Thường 403 | Access denied. |

Các kết quả khác có thể đến từ custom handlers, gateway, CSRF config hoặc multi-chain; không suy ra exception type duy nhất từ status.

## 18. Câu hỏi ôn tập

**Q1. Hai exception có kế thừa nhau không?** Không; đều unchecked exception nhưng thuộc hai nhánh khác nhau và biểu diễn ngữ nghĩa khác nhau.

**Q2. Sai password trong form login thường vào handler nào?** `AuthenticationFailureHandler` của authentication filter, không nhất thiết là `ExceptionTranslationFilter`.

**Q3. User xác thực đúng nhưng thiếu `ROLE_ADMIN` có phải `BadCredentialsException` không?** Không. Đó là authorization denial, thường thuộc `AccessDeniedException`/subclass phù hợp.

**Q4. Tại sao một `AccessDeniedException` có thể dẫn đến 401 hoặc redirect?** `ExceptionTranslationFilter` có thể coi user anonymous/remember-me chưa đủ authentication và khởi động entry point.

**Q5. Một HTTP 403 chứng minh authorization manager đã deny?** Không. `CsrfFilter`, gateway, controller hoặc business layer có thể trả 403.

**Q6. `InsufficientAuthenticationException` luôn do sai mật khẩu?** Không. Nó có thể thể hiện mức authentication chưa đủ.

**Q7. Muốn test POST thiếu WRITE nhưng gặp CSRF 403, phải làm gì?** Gửi CSRF token hợp lệ, ví dụ `.with(csrf())`, để kiểm tra denial do thiếu authority.

**Q8. `@ControllerAdvice` có thay thế tất cả security filter handlers không?** Không, nhiều lỗi được xử lý trước MVC bởi security filters.

**Q9. Basic 401 custom phải chú ý header nào?** `WWW-Authenticate` theo scheme/realm phù hợp.

**Q10. Vì sao không nên log raw exception?** Có thể tiết lộ account, policy, token, cookie hoặc request details ngoài dự kiến.

**Q11. Method security có tạo AccessDeniedException dù HTTP rule đã qua không?** Có thể, khi `@PreAuthorize` hoặc authorization tại service từ chối.

**Q12. Có nên thay 403 bằng 200 và JSON message “forbidden”?** Không; làm sai semantics giao thức và client có thể coi request thành công.

## 19. Checklist trước khi phát hành

- [ ] Phân biệt authentication failure với authorization denial trong API contract.
- [ ] Không ánh xạ cứng `AuthenticationException = 401`, `AccessDeniedException = 403` cho mọi authentication mechanism.
- [ ] Hiểu cách `ExceptionTranslationFilter` dùng `AuthenticationTrustResolver` với anonymous/remember-me.
- [ ] Biết `AuthenticationFailureHandler`, `AuthenticationEntryPoint`, `AccessDeniedHandler` không phải một.
- [ ] Kiểm tra vị trí filter vì authentication filter phía trước có thể xử lý lỗi cục bộ.
- [ ] Có test riêng cho credential sai, anonymous, thiếu role, đủ role và CSRF.
- [ ] Có test method security nếu ứng dụng dùng `@PreAuthorize`.
- [ ] Không tắt CSRF hoặc thêm `permitAll()` để xử lý lỗi phân quyền.
- [ ] Giữ header `WWW-Authenticate` đúng cho Basic/Bearer.
- [ ] Error body không chứa password, token, cookie, role/policy nhạy cảm hoặc raw exception message.
- [ ] Log/metrics phân loại nguồn lỗi, không đếm mọi 403 là authorization denial.
- [ ] Test thực trên đúng SecurityFilterChain và context path/method.
- [ ] Nếu có form login/SPA/API hỗn hợp, mỗi flow có failure handler và entry point rõ.
- [ ] Kiểm tra resource owner/tenant ở tầng tin cậy; denial thực thi trước side effects.
- [ ] Có positive test chứng minh user đủ quyền thực sự vào được endpoint.

**Kết luận:** `AuthenticationException` nói về **xác thực thất bại hoặc chưa đủ**; `AccessDeniedException` nói về **quyết định không cho truy cập**. Response cuối cùng phụ thuộc **nguồn lỗi, vị trí filter, authentication state và entry point/handler đang dùng**. Một ứng dụng an toàn cần tách 401/302/403, CSRF, authentication failure và authorization denial bằng logic và kiểm thử rõ ràng, không suy nguyên nhân từ status đơn lẻ.
