# Điều tra 401, 403 và chuyển hướng lặp bằng dấu vết yêu cầu trong Spring Security

> **Chủ đề:** Spring Security – fundamentals • **Nhóm:** Quan sát và gỡ lỗi • **Môi trường:** Spring MVC trên Servlet stack, Spring Boot 3.x / Spring Security 6.x, Java 17+. Mục đích là xác định **bộ lọc/handler nào** tạo ra 401, 403 hoặc chuỗi redirect, bằng **request ID, chuỗi status/Location, log filter chain và bằng chứng phiên/CSRF**, thay vì sửa ngẫu nhiên quyền hoặc tắt cơ chế bảo mật.

## 1. Tình huống thực tế: cùng là “không vào được”, nhưng lỗi khác nhau

Ba hiện tượng hay gặp:

- **401 Unauthorized:** API trả 401, đôi khi kèm `WWW-Authenticate`. Người dùng chưa được xác thực hoặc credential/token không hợp lệ với cơ chế được cấu hình.
- **403 Forbidden:** request đã được xác thực nhưng không đủ quyền; hoặc request bị chặn bởi một biện pháp khác như **CSRF**, request firewall, policy ở tầng khác. Không thể suy ra “thiếu vai trò” chỉ từ con số 403.
- **Chuyển hướng lặp:** browser đổi qua lại giữa `/private`, `/login` hoặc đường callback, cuối cùng báo “too many redirects”. Mỗi HTTP 302 có thể hợp lệ riêng lẻ, nhưng kết hợp thành một vòng không có trạng thái tiến triển.

Một biểu hiện thứ tư thường đi kèm: **nút bấm trên trình duyệt thất bại nhưng curl/Postman lại được**. Khi đó cần so sánh cookie, CSRF token, `Origin`, `Accept`, cache, proxy, scheme và từng redirect — chứ không chỉ nhìn controller.

Bài này trả lời các câu hỏi:

1. Request thật đi qua `SecurityFilterChain` nào, filter nào, và đến được `DispatcherServlet` hay chưa?
2. Trường hợp 401 là thiếu authentication, mật khẩu sai, token sai hay entry point được cấu hình không đúng?
3. Trường hợp 403 là thiếu quyền, CSRF, method security, lỗi tenant/owner hay policy khác?
4. Redirect nào tạo ra `Location`, redirect nào tiếp tục, và vì sao session/credential không được giữ qua các bước?
5. Có thể tái hiện và chứng minh kết luận bằng log, `curl` và `MockMvc` như thế nào mà không lộ dữ liệu nhạy cảm?

**Nguyên tắc:** đừng dùng `csrf.disable()`, `permitAll()` hoặc `anyRequest().permitAll()` chỉ để “làm hết lỗi” trước khi biết nguyên nhân. Đó là tắt hàng rào an toàn, không phải sửa lỗi.

## 2. Đọc 401, 403 và 302 đúng ngữ cảnh

| Dấu hiệu | Cơ chế có thể tạo response | Đầu mối điều tra |
| --- | --- | --- |
| 401 + `WWW-Authenticate: Basic ...` | HTTP Basic `AuthenticationEntryPoint` | Có header Authorization không? Mật khẩu/encoder/user store đúng không? |
| 401 + `WWW-Authenticate: Bearer ...` | OAuth2 Resource Server entry point | Token có hạn, issuer/audience, signature, scope, scheme? |
| 401 JSON do app định nghĩa | Custom entry point hoặc authentication failure handler | Có đúng handler đã ghi response không? Body schema không xác định nguồn lỗi. |
| 403 khi gọi POST/PUT/DELETE | `CsrfFilter`, thiếu authority, business rule | Thử lại với token CSRF hợp lệ, so sánh security TRACE và authorization logs. |
| 403 khi GET dữ liệu | Thiếu role/authority, rule object-level, firewall hoặc entry point đặc thù | Principal thực là ai? Chain nào khớp? Rule nào deny? |
| 302 `Location: /login` | `LoginUrlAuthenticationEntryPoint` cho tài nguyên cần login | Trang `/login` có được phép truy cập ẩn danh không? |
| 302 `Location: /login?error` sau POST login | `AuthenticationFailureHandler` | Credential sai hay POST thiếu CSRF bị chặn trước login filter? |
| 302 `Location: /web/home` sau POST login | `AuthenticationSuccessHandler` | Session cookie có được lưu ở browser và gửi lại không? |
| 302 liên tiếp giữa hai URL | Proxy, login, saved request, invalid session strategy, application redirect | Liệt kê từng hop có `Location`, `Set-Cookie`, `Cookie`, scheme, host và path. |
| 404 hoặc 500 thay vì 401/403 mong đợi | Route/filter chain khác, error dispatch, container/proxy | Request có đến ứng dụng? Route/dispatcher/exception nào sinh response? |

**Mã HTTP không tự chỉ ra nơi phát sinh.** Cùng 403 có thể do `CsrfFilter` trả trước controller, `AuthorizationFilter` từ chối URL, `@PreAuthorize` ở service ném `AccessDeniedException`, hoặc chính controller trả 403. Cần dấu vết theo **một request cụ thể**.

### 401 không phải lúc nào cũng xuất hiện với trình duyệt

Nếu cấu hình `formLogin` dùng login page, anonymous vào `/web/home` có thể được **302 tới /login**, chứ không phải 401. Với HTTP Basic, client thường nhận 401 và challenge header. Với Bearer token, hành vi và `WWW-Authenticate` lại theo RFC/token handler. Không so status giữa các cơ chế mà không xem entry point đang được chọn.

### 403 không luôn có nghĩa “đã đăng nhập”

Nhiều trường hợp 403 có thể xảy ra khi **chưa xác thực**, chẳng hạn thiếu CSRF token trên POST. Một `Http403ForbiddenEntryPoint` được cố ý cấu hình cũng có thể trả 403 cho anonymous. Vì vậy câu “401 = chưa login, 403 = đã login” chỉ là quy ước hay gặp, **không phải định lý** cho mọi configuration.

## 3. Bản đồ luồng request và nơi nên đặt dấu vết

```text
Client/browser
    |
    v
CDN / WAF / reverse proxy / ingress       <--- Access log: status, Location, request ID
    |
    v
HTTP connector (Tomcat/Jetty/Undertow)
    |
    v
Servlet FilterChain                     <--- Request/response correlation filter
    |
    +-- DelegatingFilterProxy("springSecurityFilterChain")
    |       |
    |       v
    |    FilterChainProxy
    |       |
    |       +-- Chọn SecurityFilterChain đầu tiên khớp request
    |       +-- SecurityContext / session
    |       +-- CsrfFilter
    |       +-- Authentication filter(s)
    |       +-- ExceptionTranslationFilter
    |       +-- AuthorizationFilter
    |       |
    |       +-- AuthenticationEntryPoint / AccessDeniedHandler
    |
    v
DispatcherServlet
    |
    +-- HandlerMapping, Controller, Service
    +-- @PreAuthorize / method security nếu đã bật
    +-- HandlerExceptionResolver / @ControllerAdvice cho MVC exceptions
    |
    v
Client nhận status, headers, body
```

Sơ đồ là **mô hình**: thứ tự và danh sách filter thực tế phụ thuộc cấu hình. `ExceptionTranslationFilter` chỉ chuyển các `AuthenticationException`/`AccessDeniedException` từ đoạn chain mà nó bao quanh; không phải bộ phận bắt mọi exception ở bất kỳ filter nào. Servlet container, `/error` và proxy có thể tạo response **mà không gọi controller gốc**.

Điểm cần nhìn cùng lúc:

- **Client trace:** request method + path, response status, `Location`, `WWW-Authenticate`, `Set-Cookie` và số lần redirect.
- **Ứng dụng:** request ID, dispatcher type, URL server thực nhận, filter invocation, kết quả CSRF, principal/authorities đã chuẩn hóa, authorization decision.
- **Identity/session:** user có được xác thực thật không, session có tồn tại/sống qua redirect không, cookie path/domain/secure có khớp không.
- **Hạ tầng:** request có đến app không, proxy có đổi HTTP/HTTPS hoặc path, có route/rule WAF chặn trước app không.

Nếu không thấy **request ID do ứng dụng tạo** trong response, có thể request không đi qua correlation filter/app hoặc response bị tầng ngoài thay thế. Đừng vội điều chỉnh `SecurityFilterChain` khi chỉ có log WAF.

## 4. Quy trình điều tra có thứ tự — thu đủ bằng chứng trước khi sửa

### Bước 1. Lặp lại một request tối giản

Ghi **method, URL, scheme, host, path, query có thể đã rút gọn, headers quan trọng đã che, loại client, thời điểm và status**. Không copy nguyên `Authorization`, `Cookie`, access token, mật khẩu hoặc dữ liệu riêng tư vào ticket/log.

Dùng request càng gần production càng tốt: POST khác GET; `Accept: text/html` khác `Accept: application/json` có thể chọn entry point khác; browser tự quản cookie/redirect trong khi curl có thể không.

Ví dụ:

```bash
# Chỉ xem response của một request, KHÔNG tự theo redirect.
curl -sS -D - -o /dev/null \
  -H 'Accept: text/html' \
  http://localhost:8080/web/home

# Hiển thị request/response của HTTP Basic API, có status và headers.
curl -i http://localhost:8080/api/me
```

**Không dùng `curl -L` ngay từ đầu**, vì nó làm bạn bỏ lỡ hop đầu tiên sinh redirect. Hãy xem từng `Location` trước.

### Bước 2. Gắn correlation ID

Mỗi request nên có một ID ngẫu nhiên do server cấp hoặc ID từ hạ tầng đã được **xác thực/kiểm tra tính hợp lệ**. Dùng ID này để nối app log, proxy log, truy vấn DB/job nếu có. Với demo, ID do app sinh mới cho mỗi HTTP request, response có `X-Request-ID`. Một chuỗi 302→302→200 là **nhiều request HTTP**, vì vậy sẽ có nhiều ID; cần nhóm chúng theo phiên truy vết client/test run.

Với môi trường phân tán, dùng W3C Trace Context (`traceparent`) thông qua cơ chế tracing chuẩn; đừng tùy tiện tin một ID do client đưa vào có thể chứa CR/LF hoặc dữ liệu độc hại. **Trace ID không phải secret**, nhưng có thể trở thành dữ liệu liên kết hoạt động người dùng nên vẫn cần chính sách lưu trữ.

### Bước 3. Bật log đúng phạm vi, đúng thời điểm

Trong môi trường local/staging:

```properties
# application-local.properties — chỉ bật tạm để gỡ lỗi
logging.level.org.springframework.security=TRACE
logging.level.org.springframework.security.web.FilterChainProxy=TRACE
logging.level.com.example.securitytrace=DEBUG
```

Spring Security ghi log `DEBUG`/`TRACE` liên quan request, filter order, CSRF và authorization. Trong log khởi động, `DefaultSecurityFilterChain` thường in danh sách filter; khi request chạy, `FilterChainProxy` ở TRACE có thể cho thấy `Invoking ... (n/N)`. Danh sách **có thể khác nhau giữa các phiên bản** và giữa các `SecurityFilterChain`, không hard-code tên/số lượng filter như tiêu chí test.

Bật TRACE cho **gói hẹp** khi có thể, trong thời gian ngắn, ở môi trường kiểm thử. Tránh bật `org.springframework.security=TRACE` dài hạn ở production: log có thể chứa đường dẫn, user metadata, details liên quan xác thực, tạo lượng log lớn. Tắt lại sau khi kết luận; có thể điều chỉnh mức log runtime qua công cụ vận hành đã được cấp quyền nếu ứng dụng hỗ trợ.

### Bước 4. Tìm filter ra quyết định, không chỉ filter cuối ghi status

Ví dụ các dòng *minh họa dạng log*, không phải stdout nguyên văn bắt buộc:

```text
trace=1f... request.start GET /api/me dispatch=REQUEST
DEBUG ... FilterChainProxy : Securing GET /api/me
TRACE ... FilterChainProxy : Invoking ...
DEBUG ... ExceptionTranslationFilter : ... start authentication ...
trace=1f... request.end status=401
```

Hoặc:

```text
trace=2c... request.start POST /api/messages dispatch=REQUEST
TRACE ... FilterChainProxy : Invoking CsrfFilter ...
DEBUG ... CsrfFilter : Invalid CSRF token found for ...
trace=2c... request.end status=403
```

Không suy ra từ `status=403` rằng `@PreAuthorize` đã chạy. Nếu `CsrfFilter` dừng request trước, service thậm chí chưa được gọi.

### Bước 5. Lập bảng giả thuyết và phép thử đối chứng

| Giả thuyết | Phép thử có kiểm soát | Kết luận khi đối chứng thay đổi |
| --- | --- | --- |
| API 401 do thiếu credential | Thử cùng path với HTTP Basic hợp lệ (local account) | 401→200 cho thấy đường Basic hoạt động; điều tra client header. |
| 401 do mật khẩu/encoder sai | Thử credential đúng và sai; xem authentication logs không lộ password | Credential đúng vẫn 401: kiểm tra provider/UserDetailsService/encoder. |
| POST 403 do CSRF | Cùng principal/URL, thêm token CSRF hợp lệ | 403→201/200: nguyên nhân liên quan token hoặc CSRF path. |
| 403 do quyền | Giữ token hợp lệ, đổi authority/principal trong test | Người đủ quyền được, người thiếu quyền bị từ chối. |
| 403 do object-level policy | Cùng principal, đổi ID resource được phép/không được phép | Chứng minh rule theo owner/tenant chứ không phải URL chung. |
| Redirect do login page bị bảo vệ | GET trực tiếp `/login` như anonymous | GET /login cũng 302 về /login: cấu hình access rule/login page. |
| Loop do cookie phiên không đi cùng redirect | Xem `Set-Cookie` hop login và `Cookie` hop sau | Cookie thiếu hoặc đổi: kiểm tra Domain/Path/Secure/SameSite/proxy. |
| Loop do proxy HTTP↔HTTPS hoặc host | Theo từng `Location` qua proxy và gọi trực tiếp app có kiểm soát | Scheme/host đổi qua lại: cấu hình trusted forwarded headers và canonical URL. |

**Mỗi lần chỉ thay một biến**: method, header, principal, CSRF, URL hoặc cookie. Nếu đồng thời sửa 3 thứ, một request thành công không chứng minh nguyên nhân nào đúng.

## 5. Demo có thể chạy: hai vùng bảo vệ, một filter tạo dấu vết

Dùng một ứng dụng Servlet duy nhất để tái hiện:

- `/api/**`: HTTP Basic; người ẩn danh trả **401**, thiếu quyền trả **403**; POST cần CSRF nếu bật.
- `/web/**`: form login; người ẩn danh được redirect **302 về /login**; đăng nhập thành công đến `/web/home`.
- `/login`, `/public/**`: cho phép anonymous để tránh redirect vòng ngay tại login.
- Một Servlet `OncePerRequestFilter` đặt trước security, sinh `X-Request-ID` và log thời điểm bắt đầu/kết thúc, kể cả security chặn trước controller.

Đây là **ví dụ local**, password cố định, in-memory users và log quan sát đơn giản. Không triển khai user/password này lên production. Mã trong từng khối là một tệp riêng, chạy bằng Gradle với classpath Spring, **không** phải những tệp Java có thể gọi `javac` độc lập mà không thêm dependencies.

### 5.1. Cấu trúc thư mục

```text
security-trace-demo/
├── settings.gradle
├── build.gradle
└── src/
    ├── main/
    │   ├── resources/application.properties
    │   └── java/com/example/securitytrace/
    │       ├── SecurityTraceApplication.java
    │       ├── SecurityConfig.java
    │       ├── RequestTraceFilter.java
    │       └── DemoController.java
    └── test/java/com/example/securitytrace/
        └── RequestTraceIntegrationTest.java
```

### 5.2. Gradle

`settings.gradle`:

```groovy
rootProject.name = 'security-trace-demo'
```

`build.gradle`:

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.5'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'com.example'
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
```

Bản plugin được ghim để dễ tái hiện ví dụ API của dòng Boot 3.3; **không có nghĩa đây là bản vá mới nhất cho production**. Dự án thật phải sử dụng phiên bản đang được tổ chức cập nhật/duy trì. Gradle cần phiên bản tương thích với Spring Boot 3.3 và JDK 17+.

### 5.3. Cấu hình log — `src/main/resources/application.properties`

```properties
# Dùng trên máy local để quan sát. Trên production: bỏ TRACE.
logging.level.org.springframework.security=TRACE
logging.level.com.example.securitytrace=DEBUG

# Hiện traceId từ SLF4J MDC trên mỗi dòng log khi có.
logging.pattern.level=%5p [trace=%X{traceId:-}]
```

Ở giai đoạn khởi động, MDC chưa có `traceId` nên phần trace rỗng; đó là bình thường. Request gắn ID ở filter chạy trong request thread thì log của các security filters cùng thread có cơ hội hiển thị ID. Nếu hệ thống dùng task bất đồng bộ, Reactor/virtual thread hoặc nhiều dispatch, **MDC không tự được truyền qua mọi thread**; nên dùng tracing context propagation của hệ thống.

### 5.4. Ứng dụng — `SecurityTraceApplication.java`

```java
package com.example.securitytrace;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class SecurityTraceApplication {
    public static void main(String[] args) {
        SpringApplication.run(SecurityTraceApplication.class, args);
    }
}
```

### 5.5. Hai SecurityFilterChain — `SecurityConfig.java`

```java
package com.example.securitytrace;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.annotation.Order;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SecurityConfig {

    @Bean
    @Order(1)
    SecurityFilterChain api(HttpSecurity http) throws Exception {
        http
            .securityMatcher("/api/**")
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET, "/api/admin")
                    .hasRole("ADMIN")
                .requestMatchers(HttpMethod.POST, "/api/messages")
                    .hasAuthority("MESSAGE_WRITE")
                .anyRequest().authenticated()
            )
            .httpBasic(Customizer.withDefaults());

        // Demo giữ CSRF bật. POST phải có token hợp lệ.
        return http.build();
    }

    @Bean
    @Order(2)
    SecurityFilterChain browser(HttpSecurity http) throws Exception {
        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/login", "/public/**", "/error")
                    .permitAll()
                .requestMatchers("/web/admin")
                    .hasRole("ADMIN")
                .anyRequest().authenticated()
            )
            .formLogin(form -> form
                .loginPage("/login")
                .defaultSuccessUrl("/web/home", true)
                .failureUrl("/login?error")
                .permitAll()
            )
            .logout(logout -> logout
                .logoutSuccessUrl("/login?logout")
                .permitAll()
            );

        return http.build();
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    UserDetailsService users(PasswordEncoder encoder) {
        var reader = User.withUsername("reader")
            .password(encoder.encode("reader-pass"))
            .roles("USER")
            .build();

        var writer = User.withUsername("writer")
            .password(encoder.encode("writer-pass"))
            .authorities("ROLE_USER", "MESSAGE_WRITE")
            .build();

        var admin = User.withUsername("admin")
            .password(encoder.encode("admin-pass"))
            .roles("ADMIN")
            .build();

        return new InMemoryUserDetailsManager(reader, writer, admin);
    }
}
```

**Lý do có hai chain:** `FilterChainProxy` chọn **chain đầu tiên có `securityMatcher` khớp**. `/api/me` được xử lý bởi chain 1 (HTTP Basic), trong khi `/web/home` và `/login` đi theo chain 2 (form login). Nếu bạn thêm một chain có matcher `/**` đứng đầu, chain còn lại có thể không được chọn. Hai chain có thể có tập security filters khác nhau; không phải request nào cũng chạy cả hai.

**Lý do `/login` được `permitAll`:** trang login phải truy cập được khi chưa có authentication. Với custom `loginPage`, không cho anonymous xem login page là nguyên nhân kinh điển của **redirect về chính /login**. Thao tác POST login cũng được phép bởi `formLogin(...permitAll())`, nhưng **không được bỏ CSRF token** chỉ vì login URL được permit.

**Lý do `defaultSuccessUrl(..., true)`:** sau login hợp lệ luôn redirect đến `/web/home`, không dùng saved request làm đích. Điều này giúp demo nhất quán, không chứng minh mọi ứng dụng nên bỏ saved request; trong app thật, giữ redirect về URL ban đầu thường hợp lý.

**Lý do giữ CSRF trên API Basic:** demo đi qua Servlet và có thể dùng browser; không tắt CSRF chỉ để kiểm thử POST dễ hơn. Với API thật chỉ nhận Bearer token ở header và không dựa vào cookie, threat model CSRF có thể khác. Quyết định phải căn cứ cách client tự động gửi credentials, không chỉ tên “REST API”.

### 5.6. Correlation filter — `RequestTraceFilter.java`

```java
package com.example.securitytrace;

import java.io.IOException;
import java.util.UUID;
import java.util.concurrent.TimeUnit;

import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.slf4j.MDC;
import org.springframework.core.Ordered;
import org.springframework.core.annotation.Order;
import org.springframework.stereotype.Component;
import org.springframework.web.filter.OncePerRequestFilter;

@Component
@Order(Ordered.HIGHEST_PRECEDENCE + 10)
public class RequestTraceFilter extends OncePerRequestFilter {

    private static final Logger log =
        LoggerFactory.getLogger(RequestTraceFilter.class);

    @Override
    protected void doFilterInternal(
            HttpServletRequest request,
            HttpServletResponse response,
            FilterChain chain) throws ServletException, IOException {

        String traceId = UUID.randomUUID().toString();
        long started = System.nanoTime();

        response.setHeader("X-Request-ID", traceId);
        MDC.put("traceId", traceId);

        try {
            log.info("request.start method={} path={} dispatcher={}",
                request.getMethod(), request.getRequestURI(),
                request.getDispatcherType());

            chain.doFilter(request, response);
        } finally {
            long elapsedMs = TimeUnit.NANOSECONDS.toMillis(
                System.nanoTime() - started
            );

            log.info("request.end status={} durationMs={}",
                response.getStatus(), elapsedMs);

            MDC.remove("traceId");
        }
    }
}
```

**Giải thích chi tiết:**

- `@Component` để Spring Boot đăng ký **Servlet Filter**; `@Order(Ordered.HIGHEST_PRECEDENCE + 10)` giúp filter chạy sớm hơn đăng ký security mặc định trong môi trường Boot thông thường, nên có thể ghi dấu cả response 401/403 trả trước controller. Với ứng dụng có registration đặc biệt, vẫn cần **xác minh thứ tự thực tế**.
- Tự sinh `UUID` ở server; không tin chuỗi `X-Request-ID` do client gửi trong ví dụ. Không ghi query string, body, Authorization, Cookie hoặc token CSRF vào log.
- `X-Request-ID` được đặt **trước** `chain.doFilter`; nếu security chặn mà response vẫn đi qua filter, header vẫn có mặt.
- `finally` ghi duration/status và dọn `MDC` ngay cả khi chain ném exception. Với exception chưa xử lý, status tại filter lúc đó **chưa chắc là status cuối** do Servlet container/`/error` tạo sau khi exception thoát ra.
- `OncePerRequestFilter` có quy tắc dispatch riêng: không giả định filter được gọi cùng số lần cho `REQUEST`, `ASYNC`, `ERROR`. Đọc `shouldNotFilterAsyncDispatch()`, `shouldNotFilterErrorDispatch()` và registration nếu cần.
- Đây là request correlation tối giản; production thường dùng Micrometer Tracing / OpenTelemetry cùng correlation ID xuyên proxy/gateway và service, kèm sampling/redaction.

**Cảnh báo log URI:** ngay cả path không chứa query vẫn có thể chứa ID bí mật nếu API nhúng token vào path. Với API có URL nhạy cảm, ghi **route template** hoặc thông tin đã redacted, không log raw path tùy tiện.

### 5.7. Controller — `DemoController.java`

```java
package com.example.securitytrace;

import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.security.core.Authentication;
import org.springframework.security.web.csrf.CsrfToken;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.ResponseStatus;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class DemoController {

    @GetMapping("/public/ping")
    public String ping() {
        return "pong";
    }

    @GetMapping("/public/csrf")
    public CsrfToken csrf(CsrfToken token) {
        return token;
    }

    @GetMapping(value = "/login",
                produces = MediaType.TEXT_HTML_VALUE)
    public String login(CsrfToken token) {
        return """
            <!doctype html>
            <html lang="vi">
              <body>
                <form method="post" action="/login">
                  <input name="username" autocomplete="username">
                  <input name="password" type="password">
                  <input type="hidden" name="%s" value="%s">
                  <button type="submit">Đăng nhập</button>
                </form>
              </body>
            </html>
            """.formatted(token.getParameterName(), token.getToken());
    }

    @GetMapping("/web/home")
    public String home(Authentication auth) {
        return "home:" + auth.getName();
    }

    @GetMapping("/web/admin")
    public String webAdmin() {
        return "web-admin";
    }

    @GetMapping("/api/me")
    public String me(Authentication auth) {
        return "api:" + auth.getName();
    }

    @GetMapping("/api/admin")
    public String apiAdmin() {
        return "api-admin";
    }

    @PostMapping(value = "/api/messages",
                 consumes = MediaType.APPLICATION_JSON_VALUE)
    @ResponseStatus(HttpStatus.CREATED)
    public String create(@RequestBody Message message) {
        return "created:" + message.text();
    }

    public record Message(String text) {
    }
}
```

Tệp này có trang login HTML rất nhỏ chỉ để **test form login và redirect**. Sản phẩm thật nên dùng template engine với HTML escaping và giao diện hợp lệ, không dùng cách nối string HTML cho input tùy ý. Ở đây tên param CSRF và token do Spring Security cấp; hai chuỗi đó là giá trị framework tạo, không lấy trực tiếp từ client.

`GET /public/csrf` cho phép lấy token khi thử POST bằng curl. Nếu hệ thống dùng **session cookie** để bảo vệ request, client cần gửi token và cookie phù hợp; test `csrf()` của MockMvc là helper trong test, không thay thế cho trao đổi CSRF token trong browser.

### 5.8. Chạy demo

```bash
# Với Gradle wrapper đã được tạo trong project:
./gradlew test
./gradlew bootRun

# Nếu chưa có wrapper và máy cài Gradle tương thích:
gradle test
gradle bootRun
```

Dự án cần JDK 17+. Để tiện lặp lại, bạn có thể chạy tests trước, khởi động app sau. Không có một stdout/log tổng kết cố định vì thời gian, thread và request ID đều thay đổi; các assertions ở mục 8 mới là bằng chứng tự động.

## 6. Điều tra HTTP 401: authentication và entry point

### 6.1. Đối chứng với /api/me

Với demo đã chạy:

```bash
# 401: chưa có Authorization header
curl -i http://localhost:8080/api/me

# 200: header Basic tạo từ local credential hợp lệ
curl -i -u reader:reader-pass \
  http://localhost:8080/api/me

# 401: Basic credential không hợp lệ
curl -i -u reader:wrong \
  http://localhost:8080/api/me
```

Kỳ vọng:

| Request | Status | Body/header quan trọng |
| --- | --- | --- |
| Anonymous GET `/api/me` | 401 | Thường có `WWW-Authenticate` từ HTTP Basic entry point. |
| Basic reader đúng | 200 | `api:reader`. |
| Basic reader sai | 401 | Không gọi `me()` để trả `api:reader`. |
| Anonymous GET `/web/home` | 302 | `Location` dẫn đến `/login`, do form login entry point. |

**Không in nguyên base64 credentials** trong log/ticket; Base64 không mã hóa an toàn password, chỉ là cách biểu diễn header HTTP Basic. Dùng TLS cho Basic ở môi trường thật. Lệnh `curl -u user:password` trong ví dụ chỉ dùng credential demo; production nên dùng cơ chế tránh password lộ trong history/process list.

### 6.2. Khi 401 xuất hiện, đọc dấu vết theo thứ tự

1. **Xác định chain:** log `FilterChainProxy` có “Securing GET /api/me” và invocation của Basic filter hay không? Nếu route vào chain không có Basic, cùng credentials có thể không được xử lý.
2. **Kiểm tra request:** có `Authorization: Basic ...` hay `Bearer ...` đúng scheme? Header có bị proxy strip không? Client có bỏ header sau redirect cross-origin không?
3. **Xác định auth provider:** user store có username đó không, `PasswordEncoder` và hash đúng không, account locked/disabled/expired không?
4. **Kiểm tra exception/entry point:** 401 được tạo do không có auth hay do một lần login failed? `AuthenticationEntryPoint` và `AuthenticationFailureHandler` là những điểm khác nhau.
5. **Kiểm tra khác biệt environments:** mật khẩu seed test, secrets, JWKS cache, issuer/audience/time skew, proxy hoặc clock hệ thống.
6. **Kiểm tra request ID:** nếu app log không thấy ID của response, request có thể bị gateway chặn hoặc chuyển sang service khác.

### 6.3. Bearer JWT khác HTTP Basic

Nếu hệ thống thực dùng OAuth2 Resource Server:

- `401` thường liên quan token thiếu, sai signature, expired, issuer/audience/scheme không hợp lệ.
- `403` có thể xảy ra khi token hợp lệ nhưng thiếu quyền/scope.
- `WWW-Authenticate: Bearer ...` có thể chứa mã lỗi theo scheme; không tự xóa header để ép client nhận JSON tùy ý.
- `with(jwt())` trong Spring Security Test **tạo principal JWT mô phỏng**, không tự xác minh chữ ký token. Muốn kiểm thử decoder/issuer/key rotation, cần integration test với JWT/IdP phù hợp.

Không copy Basic-specific test của demo để kết luận toàn bộ JWT authorization đã đúng.

## 7. Điều tra HTTP 403: CSRF, quyền, object policy hay chặn từ bên ngoài?

### 7.1. CSRF có thể tạo 403 trước Authentication/Controller

`POST /api/messages` của demo yêu cầu `MESSAGE_WRITE` và CSRF token. Dù writer có authority, request thiếu CSRF có thể dừng tại `CsrfFilter`.

Phép thử:

```bash
# Writer có credential hợp lệ nhưng thiếu CSRF => 403.
curl -i -u writer:writer-pass \
  -H 'Content-Type: application/json' \
  -d '{"text":"hello"}' \
  http://localhost:8080/api/messages
```

Bật security TRACE trên máy local rồi tìm thông điệp của `CsrfFilter` về token không hợp lệ/thiếu. Nếu không có log request từ app, cần xem proxy/WAF trước.

Để test đúng **authorization**, cấp CSRF hợp lệ nhưng dùng tài khoản không có `MESSAGE_WRITE`. Với `curl` và `jq`:

```bash
# Lấy CSRF token từ chain web, giữ session cookie trong file.
TOKEN=$(curl -sS -b cookies.txt -c cookies.txt \
  http://localhost:8080/public/csrf | jq -r '.token')

# Reader có CSRF hợp lệ nhưng thiếu quyền ghi => 403.
curl -i -u reader:reader-pass \
  -b cookies.txt -c cookies.txt \
  -H "X-CSRF-TOKEN: $TOKEN" \
  -H 'Content-Type: application/json' \
  -d '{"text":"hello"}' \
  http://localhost:8080/api/messages

# Writer có CSRF và authority => 201.
curl -i -u writer:writer-pass \
  -b cookies.txt -c cookies.txt \
  -H "X-CSRF-TOKEN: $TOKEN" \
  -H 'Content-Type: application/json' \
  -d '{"text":"hello"}' \
  http://localhost:8080/api/messages
```

**Lưu ý quan trọng cho demo hai chain:** mỗi `SecurityFilterChain` có thể mang cấu hình `CsrfTokenRepository`, CSRF handler và session strategy riêng. Lệnh trên chỉ là quy trình minh họa khi cấu hình mặc định tương thích; với thực tế nhiều chain, token lấy từ chain web **không phải lúc nào** cũng được chain API chấp nhận. Nếu muốn test HTTP end-to-end ổn định, nên cấp CSRF token theo một endpoint **trong cùng chain** hoặc dùng cơ chế repository chung được cấu hình tường minh. Với `MockMvc`, `with(csrf())` có thể bảo đảm token trong phạm vi test cụ thể, nhưng không chứng minh token exchange thật đã đúng.

Nếu request hợp lệ vẫn 403, hãy phân biệt:

- Lỗi CSRF do thiếu/sai token — có dấu vết tại `CsrfFilter`.
- Lỗi authority — dấu vết ở `AuthorizationFilter` và handler deny.
- Lỗi method security — service đã được gọi qua proxy và policy từ chối.
- Lỗi object/tenant-level — identity đúng nhưng resource không nằm trong phạm vi cho phép.
- 403 từ WAF/proxy — có thể không vào app, không có app trace ID.
- `RequestRejectedException` từ `HttpFirewall` — xử lý bởi `RequestRejectedHandler`, không tự đồng nghĩa `AccessDeniedException`.

### 7.2. Khi thiếu quyền thật sự

Người dùng `reader` có `ROLE_USER`, không có `ROLE_ADMIN`. Vì thế:

```bash
curl -i -u reader:reader-pass \
  http://localhost:8080/api/admin

curl -i -u admin:admin-pass \
  http://localhost:8080/api/admin
```

Kỳ vọng `reader` nhận **403**, `admin` nhận **200**. Phép thử này là GET nên không lẫn với CSRF của POST. Nhưng nó chỉ kiểm chứng **function-level** rule ở URL; quyền theo từng bản ghi cần kiểm tra thêm owner/tenant tại service/repository.

**Nhớ tiền tố role:** `hasRole("ADMIN")` thường khớp `ROLE_ADMIN`, trong khi `hasAuthority("MESSAGE_WRITE")` khớp chuỗi chính xác. Token JWT có `scope=admin` không tự biến thành `ROLE_ADMIN` nếu converter chưa ánh xạ. Trace authorities ở dạng **đã giảm thiểu và chỉ trong test** để kiểm tra tên đúng.

## 8. MockMvc kiểm chứng giả thuyết thay vì đoán

Tạo test file `src/test/java/com/example/securitytrace/RequestTraceIntegrationTest.java`:

```java
package com.example.securitytrace;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.mock.web.MockHttpSession;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;

import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.httpBasic;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class RequestTraceIntegrationTest {

    @Autowired
    MockMvc mvc;

    @Test
    void apiAnonymousGets401WithTraceHeader() throws Exception {
        mvc.perform(get("/api/me"))
            .andExpect(status().isUnauthorized())
            .andExpect(header().exists("WWW-Authenticate"))
            .andExpect(header().exists("X-Request-ID"));
    }

    @Test
    void apiCorrectBasicCredentialsWork() throws Exception {
        mvc.perform(get("/api/me")
                .with(httpBasic("reader", "reader-pass")))
            .andExpect(status().isOk())
            .andExpect(content().string("api:reader"));
    }

    @Test
    void wrongPasswordGets401() throws Exception {
        mvc.perform(get("/api/me")
                .with(httpBasic("reader", "wrong")))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void authenticatedWithoutAdminAuthorityGets403() throws Exception {
        mvc.perform(get("/api/admin")
                .with(httpBasic("reader", "reader-pass")))
            .andExpect(status().isForbidden());
    }

    @Test
    void adminGets200() throws Exception {
        mvc.perform(get("/api/admin")
                .with(httpBasic("admin", "admin-pass")))
            .andExpect(status().isOk())
            .andExpect(content().string("api-admin"));
    }

    @Test
    void writerWithoutCsrfGets403() throws Exception {
        mvc.perform(post("/api/messages")
                .with(httpBasic("writer", "writer-pass"))
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"text\":\"hello\"}"))
            .andExpect(status().isForbidden());
    }

    @Test
    void readerWithCsrfButNoWritePermissionGets403() throws Exception {
        mvc.perform(post("/api/messages")
                .with(httpBasic("reader", "reader-pass"))
                .with(csrf())
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"text\":\"hello\"}"))
            .andExpect(status().isForbidden());
    }

    @Test
    void writerWithCsrfGets201() throws Exception {
        mvc.perform(post("/api/messages")
                .with(httpBasic("writer", "writer-pass"))
                .with(csrf())
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"text\":\"hello\"}"))
            .andExpect(status().isCreated())
            .andExpect(content().string("created:hello"));
    }

    @Test
    void anonymousBrowserRequestRedirectsToLogin() throws Exception {
        mvc.perform(get("/web/home"))
            .andExpect(status().is3xxRedirection())
            .andExpect(header().string(
                "Location",
                org.hamcrest.Matchers.endsWith("/login")
            ));
    }

    @Test
    void loginPageIsReachableAnonymously() throws Exception {
        mvc.perform(get("/login"))
            .andExpect(status().isOk())
            .andExpect(content().string(
                org.hamcrest.Matchers.containsString("<form")
            ));
    }

    @Test
    void browserLoginCreatesSessionForFollowingRequest() throws Exception {
        MvcResult login = mvc.perform(post("/login")
                .with(csrf())
                .param("username", "reader")
                .param("password", "reader-pass"))
            .andExpect(status().is3xxRedirection())
            .andExpect(header().string(
                "Location",
                org.hamcrest.Matchers.endsWith("/web/home")
            ))
            .andReturn();

        MockHttpSession session =
            (MockHttpSession) login.getRequest().getSession(false);
        assertNotNull(session);

        mvc.perform(get("/web/home").session(session))
            .andExpect(status().isOk())
            .andExpect(content().string("home:reader"));
    }

    @Test
    void wrongFormPasswordRedirectsToLoginError() throws Exception {
        mvc.perform(post("/login")
                .with(csrf())
                .param("username", "reader")
                .param("password", "wrong"))
            .andExpect(status().is3xxRedirection())
            .andExpect(header().string(
                "Location",
                org.hamcrest.Matchers.endsWith("/login?error")
            ));
    }
}
```

**Giá trị của test:** cùng một bộ filter config tạo **401** cho API anonymous, **403** cho reader thiếu role, **403** cho POST thiếu CSRF, **302** cho browser anonymous và **302** login success/failure. Test riêng từng biến giúp tránh quy lỗi nhầm.

**Điểm cần hiểu về `MockMvc`:**

- `@SpringBootTest` + `@AutoConfigureMockMvc` nạp Spring context và gắn filters được Boot cấu hình cho MockMvc (mặc định `addFilters=true`). Nếu dùng `standaloneSetup` không có Security FilterChainProxy, bạn có thể nhận 200 ở URL vốn phải 401/403.
- `httpBasic(...)` tạo Basic auth header để filter xác thực thật với in-memory user store; `@WithMockUser` và `with(user(...))` tạo test principal, **không** chứng minh password/provider thật.
- `with(csrf())` tạo token test hợp lệ. Nó không chứng minh browser đã giữ đúng cookie và token thực qua reverse proxy.
- `MockMvc` **không tự theo redirect**. Mỗi `mvc.perform(...)` là một request; muốn test session giữa các request phải tái sử dụng `MockHttpSession` hoặc cơ chế phù hợp.
- Filter correlation ID hoạt động trong MockMvc nếu filter đã được đăng ký. Ở embedded server thực, headers/status có thể bị proxy/error page điều chỉnh.
- Nếu exception xảy ra trước `DispatcherServlet`, MockMvc có thể ném exception lên test thay vì phản hồi như Tomcat/`/error`; cần live HTTP test cho trường hợp đó.

**Đừng tắt `addFilters` hoặc gắn `@WithMockUser` cho mọi test chỉ để suite xanh.** Một suite không thực thi security filters không chứng minh được quyền.

## 9. Chẩn đoán redirect loop theo từng hop

### 9.1. Cần thu thập những gì?

Một chuỗi ví dụ:

```text
1) GET /web/home
   302 Location: /login
   Set-Cookie: ... (nếu có)

2) GET /login
   302 Location: /login

3) GET /login
   302 Location: /login
   ... lặp lại
```

Dấu hiệu: `/login` đã bị yêu cầu xác thực, hoặc một filter/controller khác lại redirect trang login tới chính nó. Với lỗi cookie, chuỗi có thể là:

```text
1) GET /web/home   -> 302 /login
2) GET /login      -> 200 form
3) POST /login     -> 302 /web/home; Set-Cookie: JSESSIONID=...
4) GET /web/home   -> 302 /login (không mang cookie hợp lệ)
5) GET /login      -> 200 form
... người dùng tiếp tục nhập mật khẩu; nhìn như "loop"
```

Hai chuỗi trên **khác nguyên nhân**: chuỗi đầu là redirect loop trực tiếp, chuỗi sau là **session/login loop** xảy ra sau thao tác người dùng. Cần phân biệt khi phân tích HAR và status history.

### 9.2. Dùng curl lưu và theo redirect có giới hạn

```bash
# Quan sát hop đầu, không theo Location:
curl -sS -D - -o /dev/null \
  http://localhost:8080/web/home

# Xem mọi hop trong một chuỗi (giới hạn để không lặp vô hạn):
curl -v -L --max-redirs 5 \
  -b cookies.txt -c cookies.txt \
  http://localhost:8080/web/home
```

`curl -v` hiển thị chi tiết request headers, có thể bao gồm cookie hoặc Authorization nếu bạn cung cấp. **Không copy nguyên log verbose vào ticket**; che bí mật trước khi chia sẻ. Có thể lọc/trích chỉ status, `Location`, `Set-Cookie` đã che, `X-Request-ID` và method/host/path.

**Đừng tùy tiện dùng `curl -I -L` để mô phỏng browser GET**: `-I` gửi HEAD; bảo mật và controller có thể xử lý HEAD khác GET. Truy vết vòng redirect GET thì dùng GET và `-D - -o /dev/null` như trên.

### 9.3. Luồng login thật với CSRF và cookie jar

Ví dụ với endpoint `/public/csrf` của demo. Trong Bash có `jq`:

```bash
# Lấy CSRF token và giữ cookie (nếu ứng dụng cấp cookie).
CSRF=$(curl -sS -b cookies.txt -c cookies.txt \
  http://localhost:8080/public/csrf | jq -r '.token')

# POST form login. Không dùng -L để xem Location và Set-Cookie hop này.
curl -i -b cookies.txt -c cookies.txt \
  -H "X-CSRF-TOKEN: $CSRF" \
  --data-urlencode "username=reader" \
  --data-urlencode "password=reader-pass" \
  http://localhost:8080/login

# Gửi tiếp cookie sau login; kỳ vọng 200 thay vì 302 /login.
curl -i -b cookies.txt -c cookies.txt \
  http://localhost:8080/web/home
```

Khi đăng nhập thành công, Spring Security có thể **xóa/luân chuyển CSRF token cũ**; nếu POST khác sau login, cần lấy token mới. Browser có thể gửi cookie phiên nếu Domain/Path/Secure/SameSite đúng; cấu hình HTTPS, reverse proxy và CORS cần được kiểm thử thực tế. Với HTTP Basic API, session/cookie behavior không nhất thiết giống form login.

### 9.4. Các nguyên nhân loop điển hình và cách chứng minh

| Nguyên nhân | Dấu vết thường thấy | Phương án xác minh |
| --- | --- | --- |
| `/login` bị bảo vệ | GET `/login` anonymous 302 về `/login` | Thêm rule `permitAll` chính xác và test 200 anonymous cho login GET. |
| Login POST URL không nằm trong chain phù hợp | POST login 404/403/302 khác kỳ vọng | Kiểm tra `securityMatcher`, `loginProcessingUrl`, thứ tự chains. |
| Login thành công nhưng session không được lưu | POST login 302 tới private, GET private 302 về login | Xác minh `Set-Cookie` và `Cookie`, session repository, proxy, auth success handler. |
| Cookie bị browser loại bỏ | DevTools thấy Set-Cookie cảnh báo hoặc request sau không có Cookie | Kiểm tra Secure/HTTPS, Domain, Path, SameSite, chính sách third-party cookies. |
| Session ID bị coi invalid liên tục | Redirect tới invalidSessionUrl rồi lại redirect | Kiểm tra `SessionManagementFilter`, invalid session strategy, stale cookies; không ép session mới vô hạn. |
| Request cache lưu URL không phù hợp | Login success redirect về URL lại kích hoạt auth | Ghi saved request/target (không lộ query bí mật), lựa chọn success URL, cache policy. |
| Proxy HTTP↔HTTPS/host đổi qua lại | `Location` lúc HTTP, lúc HTTPS hoặc domain A/B | Kiểm tra trusted forwarded headers, TLS termination, URL canonicalization. |
| Callback OAuth2/OIDC sai | Login → IdP → callback → login → IdP ... | Kiểm tra redirect URI đã đăng ký, state/nonce/session cookie, client config, clock. |
| Một app route khác tự redirect | Security logs cho phép, nhưng controller trả 302 | Xem controller/Servlet filter redirect và gateway rules. |

**Không “fix” loop bằng cách bỏ authorization của trang đích** nếu nguyên nhân là session cookie không được gửi; điều đó có thể biến một trang private thành public.

### 9.5. Lưu ý saved request

`ExceptionTranslationFilter` có thể dùng `RequestCache` để lưu request gốc trước khi chuyển người dùng tới login. `SavedRequestAwareAuthenticationSuccessHandler` có thể đưa họ trở về URL đó sau khi xác thực. Nếu URL gốc do app/proxy định tuyến sai hoặc chính nó lại yêu cầu một authentication mechanism khác, sau login có thể tái hiện đường đi lỗi.

Để điều tra, ghi **đường dẫn đã chuẩn hóa và ID phiên/truy vết đã băm** theo chính sách logging, không ghi full query chứa token. Nếu app cố ý điều hướng luôn về một URL cố định, `defaultSuccessUrl(..., true)` có thể làm luồng rõ hơn; đó là **chính sách sản phẩm**, không phải phương thuốc chung cho mọi loop.

## 10. Điều tra sai lệch do reverse proxy, TLS và forwarded headers

Một request ngoài có thể là:

```text
Client:  https://example.com/web/home
Proxy:   http://app:8080/web/home
App sees request.isSecure() == false nếu forwarded info chưa được xử lý
App redirects /login hoặc http://example.com/login
Proxy redirects http://example.com/... -> https://example.com/...
App tạo URL HTTP lần nữa -> có thể thành vòng
```

Không phải mọi reverse proxy tạo loop như vậy, nhưng nếu **cùng URL liên tục đổi scheme hoặc host**, kiểm tra nơi tạo redirect tuyệt đối và cấu hình nhận forwarded headers.

Trong Spring Boot Servlet có cách cấu hình forward headers, ví dụ `server.forward-headers-strategy` với giá trị phù hợp môi trường triển khai. Một số container/ingress cần thiết lập riêng và chính sách **trust proxy**. Không bật mù quáng việc chấp nhận `X-Forwarded-Host`/`X-Forwarded-Proto` do bất kỳ client bên ngoài gửi; header không đáng tin có thể dẫn tới host header injection hoặc open redirect.

Quy trình kiểm chứng:

1. Xem external `Host`, scheme và URL browser truy cập.
2. Xem proxy access log và header forwarding ở ranh giới đã xác thực.
3. Xem `request.getScheme()`/`isSecure()` trong một log **đã bảo vệ**, không ghi input tùy ý.
4. So sánh `Location` do app tự tạo và do proxy sửa/trả.
5. Kiểm tra `Secure` cookie trên HTTPS, `Path` theo context path, `Domain` và SameSite.
6. Sau cấu hình, thử request live từ ngoài proxy lẫn gọi trực tiếp backend qua môi trường test có kiểm soát.

**HTTP 301/308 cũng là redirect**, không chỉ 302. Browser cache permanent redirect có thể làm test sau sửa vẫn khó hiểu; thử bằng client mới/ẩn danh/curl để loại tác động cache.

## 11. Multiple SecurityFilterChain và matcher: nguyên nhân khó thấy của 401/302

Ví dụ demo có:

```text
@Order(1) securityMatcher("/api/**")
    -> httpBasic
    -> 401 cho API anonymous

@Order(2) fallback chain
    -> formLogin
    -> 302 tới /login cho browser anonymous
```

Nếu một service cấu hình `securityMatcher("/api/**")` cho cả form login nhưng `loginProcessingUrl("/login")` ở ngoài `/api/**`, filter xử lý login trong chain đó **không nhận POST /login**. Kết quả có thể là 404, 403, redirect lặp hoặc một chain khác xử lý request.

Các câu cần trả lời bằng trace:

- Request cuối cùng sau proxy/context path là `/api/login`, `/login` hay đường khác?
- FilterChainProxy có chọn chain chứa authentication filter cần thiết không?
- Rule `requestMatchers` có được so trong **đúng chain** và thứ tự đúng không?
- `permitAll` ở một chain có áp dụng đến chain khác không? **Không**: request đã chọn chain đầu tiên khớp.
- Có `web.ignoring()` hoặc `filters="none"` làm request bỏ qua security không? Với URL public, thường **`permitAll` vẫn giữ security filter chain** và nhiều protection hữu ích.
- Mismatch `/api/**` và `/api` (không slash cuối) hoặc context path có gây chọn sai không? Kiểm tra bằng test cụ thể.

Phép thử nên có **mỗi đường trọng yếu ở cả phía trước/sau ranh giới matcher**: `/api/me`, `/api/admin`, `/web/home`, `/login`, `/error` và callback/loginProcessingUrl thực. Không xem cấu hình “có rule đúng” là đủ nếu rule đó nằm trong chain không bao giờ được chọn.

## 12. Session, SecurityContext và “đăng nhập rồi lại bị logout”

### 12.1. Điều gì cần được lưu?

Với form login stateful, successful authentication thường gắn với session/security context; browser giữ cookie (thường `JSESSIONID`) để dùng cho request tiếp theo. `AuthenticationSuccessHandler` trả 302 **không tự bảo đảm browser đã gửi cookie phiên ở request sau**.

Kiểm tra:

- Có response `Set-Cookie` khi session được tạo/đổi ID?
- Client có thực nhận và lưu cookie?
- Request tới `/web/home` tiếp theo có `Cookie` tương ứng?
- Cookie `Path` có bao phủ path đích? `Domain`/scheme/`Secure`/`SameSite` có phù hợp?
- Server nhận cookie nhưng session có tồn tại trong repository? Có load balancer đến node khác mà không có shared session?
- Session timeout, invalid-session strategy, concurrent-session controls có vô hiệu hóa phiên không?
- `SecurityContextRepository` và security context persistence được cấu hình theo phiên bản đang dùng ra sao?
- Có custom filter ghi đè `SecurityContextHolder` hoặc đặt stateless session policy nhầm chain không?

**Không ghi nguyên session ID trong log.** Muốn đối chiếu, dùng hash có salt/scope phù hợp, hoặc correlation code không thể dùng làm session credential. Client request ID không thay thế session ID.

### 12.2. Dùng MockMvc kiểm tra session, nhưng đừng dừng tại đó

Test `browserLoginCreatesSessionForFollowingRequest` cho thấy server-side session được giữ qua hai request MockMvc khi truyền `MockHttpSession`. Nó **không kiểm tra** browser chấp nhận cookie của domain/secure/samesite hoặc proxy rewrite. Cần một live HTTP/browser test khi loop chỉ xảy ra ở production.

### 12.3. Stateless Bearer khác cookie login

Với JWT stateless, mỗi request cần gửi Bearer token đúng. Nếu client nhận token rồi quên gắn `Authorization` ở redirect/new request, 401 sẽ xảy ra dù “vừa đăng nhập thành công”. Đừng điều tra theo `JSESSIONID` nếu hệ thống không dùng session. Kiểm tra token delivery/storage/renewal và chính sách CORS, đồng thời tránh lộ token trong query string hoặc log.

## 13. Bảo vệ dữ liệu khi thu thập dấu vết

Dấu vết là bằng chứng kỹ thuật nhưng có thể trở thành rủi ro bảo mật. Một trace tốt có:

- Timestamp có timezone, request ID/trace ID, service/instance, method, route template, dispatcher type, status, duration.
- Filter/handler đã quyết định chặn và **mã lý do đã chuẩn hóa**, ví dụ `AUTH_REQUIRED`, `ACCESS_DENIED`, `CSRF_INVALID`, `LOGIN_REDIRECT`.
- User ID pseudonymized hoặc identifier tối thiểu, authorities đã được kiểm soát, tenant ID đã giảm thiểu theo chính sách.
- Redirect target **đã kiểm tra và redacted**; nếu có query chứa code/token thì không ghi nguyên.
- Request category/scope để so sánh TEST/PROD, nhưng tránh đi sâu vào nội dung PII.

Không nên ghi:

- `Authorization`/Bearer/JWT, cookie/session ID, CSRF token raw, password, OTP, client secret, SAML assertion, OAuth authorization code.
- Body đăng nhập, form chứa credential hoặc personal information.
- Full query string chứa token/link reset-password/signed URL.
- Tất cả headers ở DEBUG/TRACE mà không qua redaction.
- Stack trace lặp liên tục từ thông tin nhạy cảm trong production logs.

**Có thể dùng response error code an toàn cho client, nhưng log phía server phải đủ phân biệt nguồn lỗi.** Không tiết lộ cho anonymous rằng tài khoản X tồn tại hay không; không trả raw `AuthenticationException.getMessage()` vào body.

Khi bật TRACE tạm trên production để điều tra sự cố, cần quyền truy cập hạn chế, thời gian ngắn, volume limit, retention và redaction phù hợp. Ở hệ thống có dữ liệu cực nhạy cảm, ưu tiên tái hiện trong staging với dữ liệu giả.

## 14. Phân biệt MVC exception với Security filter rejection

`@RestControllerAdvice` xử lý các exception được Spring MVC `DispatcherServlet` đưa qua `HandlerExceptionResolver`, không tự bao phủ mọi Servlet Filter. Một request bị `CsrfFilter` từ chối hoặc authentication entry point trả 401 có thể **không gọi controller/advice**.

Ví dụ luồng:

```text
POST /api/messages
  -> RequestTraceFilter log START
  -> Spring Security CsrfFilter thiếu token
  -> AccessDeniedHandler trả 403
  -> RequestTraceFilter log END status=403
  -> DemoController.create(...) KHÔNG CHẠY
```

Trong khi đó:

```text
GET /web/home (đã xác thực)
  -> RequestTraceFilter
  -> Spring Security cho phép
  -> DispatcherServlet -> DemoController.home(...)
  -> 200 "home:reader"
```

Nếu một custom filter ném `IllegalArgumentException` mà không xử lý, app có thể trả 500 từ container/`/error`, không phải JSON do advice của controller dự kiến. Khi phân tích status, xác định **filter dừng chain**, **MVC handler ném lỗi**, hay **container/gateway xử lý lỗi**.

## 15. Kiểm tra redirect loop bằng test có giới hạn

Một test không nên thực sự lặp redirect vô hạn. Hãy đo **đúng một hoặc vài hop**:

- Anonymous `GET /web/home` phải nhận redirect `Location` tới `/login`.
- Anonymous `GET /login` phải nhận 200 HTML, không được redirect lại `/login`.
- Login POST với CSRF và credential đúng phải redirect tới `/web/home`.
- Khi truyền lại `MockHttpSession`, `GET /web/home` phải 200, không quay lại `/login`.
- Login POST sai credential phải redirect `/login?error` và **GET /login?error` phải mở được** (tức rule login path cho anonymous).
- Nếu có `invalidSessionUrl`, test cả request với cookie cũ và URL invalid-session đích; tránh tạo vòng mới.
- Nếu có OAuth2/OIDC, test callback URI đã đăng ký, state, nonce và cookie tại trình duyệt thật.

Có thể bổ sung một **client HTTP test** dùng redirect policy “never follow” để assert từng hop hoặc “max 5” để phát hiện loop, không cần gửi vô hạn. Với app cụ thể, thiết kế integration test ngoài proxy theo môi trường gần production là cách mạnh nhất để tìm lỗi scheme/host/cookie.

## 16. Khi lỗi chỉ xuất hiện trong môi trường thật

Một quy trình kiểm tra 3 tầng có ích:

| Tầng | Test/công cụ | Có thể chứng minh | Không chứng minh đủ |
| --- | --- | --- | --- |
| Test logic controller/method | JUnit + MockMvc với security context phù hợp | Mapping, handler, authorization trong Spring nếu filter được gắn | Browser và proxy nhận/trả cookie như thật |
| Test full application + Servlet container | `@SpringBootTest(webEnvironment = RANDOM_PORT)` + HTTP client | Connector và servlet lifecycle thật của embedded server, cookie/header/error dispatch gần thực tế | TLS/proxy/IdP ngoài môi trường test nếu chưa chạy chúng |
| E2E qua ingress/IdP gần production | Browser automation, HAR đã che, gateway logs | Thứ tự redirect, cookie policies, HTTPS, CORS, SSO/callback | Mọi nhánh lỗi nếu chưa có test coverage |

Cẩn thận với một số khái niệm dễ nhầm:

- **CORS preflight** là OPTIONS; bị từ chối trước khi browser gửi request chính có thể được báo như lỗi CORS trên UI. Xem response OPTIONS và config CORS, đừng chỉ gọi GET bằng curl.
- **Cookie SameSite/Secure** là chính sách browser; curl có thể gửi cookie trong trường hợp browser không gửi, nên curl “chạy được” không tự chứng minh frontend đúng.
- **Forwarded headers** phải đến từ proxy tin cậy; đừng cho phép client ngoài tự định nghĩa host/scheme rồi bị app dùng để redirect.
- **HTTP response caching** có thể khiến frontend dùng 302 cũ; kiểm tra cache và test client mới.
- **Node/session affinity** có thể khiến login thành công ở node A nhưng GET sau đến node B không thấy session; quan sát instance ID và session store.
- **RequestRejectedHandler/HttpFirewall** có thể chặn URI chứa encoding/semicolon/đường dẫn bất thường trước MVC; kiểm tra raw URL ở edge và normalized URL ở app một cách an toàn.

## 17. Gặp lỗi không nên sửa bằng các cách này

1. **`csrf.disable()` toàn cục vì POST trả 403:** có thể mở cửa CSRF với ứng dụng dùng cookie/session.
2. **`anyRequest().permitAll()` để hết 401:** biến endpoint bảo vệ thành public.
3. **`web.ignoring().requestMatchers("/login")` tùy tiện:** bỏ security filters khỏi URL; thường dùng `permitAll` đủ để login page truy cập được mà vẫn có bảo vệ phù hợp.
4. **Đổi mọi status thành 200 và trả `{"success":false}`:** đánh lạc hướng client và hệ thống giám sát.
5. **Cho đăng nhập thành công bằng cách ghi `SecurityContextHolder` thủ công nhưng không lưu context/session đúng:** có thể tạo login loop hoặc bypass chiến lược phiên.
6. **Log nguyên request headers/body để “tìm token sai”:** có thể ghi password/JWT/cookie thật vào hệ thống log.
7. **Bỏ `WWW-Authenticate` của HTTP Basic/Bearer khi custom entry point:** client có thể không biết cách xác thực đúng protocol.
8. **Thay đổi thứ tự filter mà không xác định chain đang chạy:** gây lỗi CSRF, exception translation hoặc authorization khác.
9. **Tự tạo redirect sang URL từ query `next` chưa validate:** có nguy cơ open redirect.
10. **Chỉ nhìn final URL sau `curl -L`:** mất dấu hop nào tạo loop.
11. **Test bằng `@WithMockUser` rồi khẳng định password/provider đúng:** mock user không đi qua credential verification.
12. **Tin redirect 302 là chứng minh auth success:** 302 có thể do entry point yêu cầu login hoặc failure handler.
13. **Sửa chỉ frontend khi app thực ra trả 401/403 từ backend:** cần log correlation để biết nơi quyết định.
14. **Phân tích mọi request dưới cùng một trace ID mà không phân biệt hop:** redirect sinh request mới, dễ trộn lẫn log và kết luận sai.
15. **Đổi proxy scheme/host mà không khóa trusted forwarded headers:** có thể tạo lỗi mới hoặc lỗ hổng.
16. **Không kiểm tra `ERROR`/`FORWARD` dispatch:** status sau error page có thể che lỗi ban đầu hoặc security chặn error dispatch.
17. **Bật Spring Security TRACE suốt ngày trên production:** tăng volume và rủi ro lộ metadata.
18. **Không kiểm tra side effect của request bị chặn:** cần xác minh dữ liệu không bị thay đổi dù response cuối báo 403.

## 18. Checklist thực hành khi nhận một ticket 401/403/redirect loop

- [ ] Ghi lại URL/method, giờ, client, environment, status và response headers cần thiết đã che.
- [ ] Xác định `X-Request-ID`/trace ID và app instance/ingress hop tương ứng.
- [ ] Xác định request đến được app không, hay bị proxy/WAF chặn trước.
- [ ] Xác định `SecurityFilterChain` nào khớp request và filter order hiện tại.
- [ ] Phân biệt 401 entry point, 401 login failure, 403 authorization, 403 CSRF và 403 do cơ chế khác.
- [ ] Đối chứng credential đúng/sai nhưng không lộ password/token trong logs.
- [ ] Với POST/PUT/DELETE, thử CSRF hợp lệ để tách lỗi CSRF khỏi lỗi permission.
- [ ] Với 403 thiếu quyền, kiểm tra authority string, role prefix, mapping JWT/claims và object policy.
- [ ] Với redirect, ghi từng hop status/Location và source tạo redirect; đặt redirect cap.
- [ ] Kiểm tra GET `/login` anonymous có thể trả 200, không redirect tới chính nó.
- [ ] Kiểm tra POST login URL nằm đúng chain, CSRF hợp lệ và success/failure handler chọn đúng mục tiêu.
- [ ] Theo dõi Set-Cookie và Cookie đã redacted giữa POST login và GET private.
- [ ] Nếu qua proxy, đối chiếu HTTP/HTTPS, host, context path và forwarded header đã tin cậy.
- [ ] Nếu nhiều nodes, xác minh session store hoặc sticky routing.
- [ ] Nếu có async/error dispatch hoặc custom filter, kiểm tra status cuối ở container thật.
- [ ] Viết MockMvc test để ngăn lỗi quay lại; bổ sung live HTTP/E2E test cho hành vi ngoài MockMvc.
- [ ] Tắt lại DEBUG/TRACE mở tạm, redaction và hạn chế retention bằng chứng.

### Câu hỏi tự kiểm tra

1. Vì sao API HTTP Basic anonymous thường trả 401 còn web form anonymous thường được redirect 302?
2. Tại sao hai request cùng trả 403 có thể do CSRF và authorization, và phép thử nào tách chúng?
3. `FilterChainProxy` quyết định SecurityFilterChain nào chạy khi có nhiều chain?
4. Vì sao `@ControllerAdvice` không tự nhận mọi lỗi do security filter sinh ra?
5. Một response có 302 `/login` có đủ để kết luận login thành công không?
6. Đâu là bằng chứng cho thấy browser không gửi cookie session sau POST login?
7. Vì sao `MockMvc` với `@WithMockUser` không chứng minh password thực được xác thực?
8. Vì sao nên có request ID trước security filter và MDC phải được dọn trong `finally`?
9. Vì sao redirect loop HTTP→HTTPS có thể liên quan `X-Forwarded-Proto`?
10. Tại sao truy vết `curl -L` không có giới hạn có thể che chỗ phát sinh redirect?
11. Trong ứng dụng nhiều chain, vì sao `/login` có thể không được login filter xử lý dù `formLogin` đã khai báo?
12. Vì sao bật TRACE production lâu dài không phải phương pháp quan sát mặc định an toàn?

**Gợi ý:** (1) entry point/challenge khác nhau; (2) gửi CSRF hợp lệ, giữ nguyên principal và URL; (3) chain đầu tiên khớp matcher; (4) MVC resolver nằm sau servlet/security filters; (5) không, có thể là redirect để bắt đầu login; (6) xem Set-Cookie/Cookie, browser DevTools và policy Domain/Path/Secure/SameSite; (7) user mô phỏng bỏ qua authentication provider; (8) nối log và tránh rò MDC sang request khác; (9) app không thấy external HTTPS khi proxy kết thúc TLS; (10) mất hop nguyên nhân và dễ lặp không giới hạn; (11) loginProcessingUrl ngoài securityMatcher; (12) log volume và metadata/credentials có thể nhạy cảm.

## Tài liệu chính thức

- Spring Security 6.5 — Servlet architecture, FilterChainProxy, logging và exception translation: https://docs.spring.io/spring-security/reference/6.5/servlet/architecture.html
- Spring Security — Servlet authentication architecture và SecurityContext: https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/architecture.html
- Spring Security — Form login: https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/passwords/form.html
- Spring Security — Session management: https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/session-management.html
- Spring Security — CSRF: https://docs.spring.io/spring-security/reference/6.5/servlet/exploits/csrf.html
- Spring Security — Request authorization: https://docs.spring.io/spring-security/reference/6.5/servlet/authorization/authorize-http-requests.html
- Spring Security — MockMvc setup: https://docs.spring.io/spring-security/reference/6.5/servlet/test/mockmvc/setup.html
- Spring Security — Testing HTTP Basic: https://docs.spring.io/spring-security/reference/6.5/servlet/test/mockmvc/http-basic.html
- Spring Security — Testing CSRF: https://docs.spring.io/spring-security/reference/6.5/servlet/test/mockmvc/csrf.html
- Spring Boot 3.3 — Logging: https://docs.spring.io/spring-boot/3.3/reference/features/logging.html
- Spring Boot 3.3 — Testing Spring Boot applications: https://docs.spring.io/spring-boot/3.3/reference/testing/spring-boot-applications.html
