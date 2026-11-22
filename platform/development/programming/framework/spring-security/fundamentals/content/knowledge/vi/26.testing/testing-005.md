# MockMvc và tích hợp chuỗi bộ lọc trong ứng dụng Servlet

> **Ngữ cảnh:** Spring Boot 3.x, Spring Security 6.x, Spring MVC trên Servlet stack, Java 17+. Bài học thuộc nhóm **Kiểm thử** và tập trung vào câu hỏi: **một bài test MockMvc có thực sự đi qua Servlet Filter Chain và Spring Security FilterChainProxy giống cấu hình ứng dụng hay không?**

## 1. Vấn đề cần kiểm thử

Giả sử một API có `SecurityFilterChain` yêu cầu xác thực với `/api/profile`, chỉ cho vai trò ADMIN vào `/api/admin`, yêu cầu authority `MESSAGE_WRITE` khi gửi POST và bắt buộc CSRF token với request thay đổi dữ liệu. Ứng dụng còn có `OncePerRequestFilter` tùy chỉnh để ghi một response header.

Một test chỉ gọi controller bằng `MockMvcBuilders.standaloneSetup(controller)` có thể thấy `GET /api/admin` trả **200** cho người ẩn danh. Trong production, request này phải bị từ chối bởi Spring Security. Test “xanh” trong trường hợp đó **không chứng minh bảo mật đúng**, vì đường đi test chưa được gắn bộ lọc thật.

Ngược lại, khi `@SpringBootTest` kết hợp `@AutoConfigureMockMvc`, MockMvc thường tích hợp các filter có trong application context; test có thể trả **401**, **403** hoặc **302** trước khi gọi controller. Đó thường là dấu hiệu bộ lọc đã được thực thi, cần xác định *bộ lọc nào* quyết định phản hồi.

Bài học hướng đến ba kết quả thực hành:

1. Dựng test có **chuỗi Servlet filters, Spring Security filters và MVC controller** đúng phạm vi.
2. Kiểm tra **người ẩn danh, người dùng mô phỏng, credential thật, quyền, CSRF và filter tự viết**; hiểu test nào có đi qua xác thực thực sự.
3. Biết những hành vi MockMvc **không thể kiểm chứng hoàn toàn** vì không có socket HTTP, reverse proxy và servlet container thật.

## 2. Cơ chế: request từ client đến Controller

Một ứng dụng Spring MVC phục vụ trên Tomcat/Jetty/Undertow thường có đường đi khái niệm:

```text
Real HTTP client
    |
    v
Reverse proxy / ingress (nếu có)
    |
    v
HTTP connector + Servlet container
    |
    v
Servlet FilterChain
    |
    +-- Custom Servlet Filter: logging / tracing / CORS / ...
    |
    +-- DelegatingFilterProxy("springSecurityFilterChain")
    |       |
    |       v
    |    FilterChainProxy
    |       |
    |       +-- chọn SecurityFilterChain khớp request
    |       +-- security filters: context, CSRF,
    |           authentication, exception translation,
    |           authorization, ...
    |
    +-- Servlet filters còn lại (theo thứ tự thực tế)
    |
    v
DispatcherServlet
    |
    +-- HandlerMapping / HandlerAdapter
    +-- Controller / service
    +-- HandlerExceptionResolver của Spring MVC
    |
    v
HTTP response
```

Đây là **sơ đồ trách nhiệm**, không phải danh sách chính xác mọi filter hoặc thứ tự mặc định cho tất cả phiên bản. Thứ tự thực tế phụ thuộc vào `FilterRegistrationBean`, `@Order`, đăng ký từ container, cấu hình `SecurityFilterChain`, `DispatcherType` và các extension của ứng dụng.

Ba thuật ngữ thường bị trộn lẫn:

- **Servlet `FilterChain`:** chuỗi filter ở cấp Servlet container; một filter có thể chạy *trước khi* request đến Spring MVC.
- **Spring Security `FilterChainProxy`:** bản thân nó được trình bày như một Servlet Filter, nhưng bên trong quản lý **một hoặc nhiều `SecurityFilterChain`** với các request matcher và security filters tương ứng.
- **`DispatcherServlet`:** nhận request sau các filter đã cho phép tiếp tục, chọn MVC handler rồi gọi controller; nơi này quản lý các `HandlerExceptionResolver` của MVC.

Khi một filter không gọi `chain.doFilter(...)` mà trả phản hồi ngay, controller **không chạy**. Khi `CsrfFilter` từ chối POST, logic validation trong controller có thể chưa được gọi. Khi `AuthorizationFilter` chặn URL, test cần assert đúng status và đảm bảo action phía sau không thực thi.

### MockMvc giữ lại những gì?

`MockMvc` tạo `MockHttpServletRequest` và `MockHttpServletResponse`, gửi request qua **Spring MVC test infrastructure**, bao gồm các filters đã được gắn vào builder. Nó không khởi động socket và không yêu cầu Tomcat nhận một request HTTP thực.

Do đó:

- Có thể kiểm tra controller mapping, JSON binding, MVC exception resolver, filter invocation, status/header/body, security matching, CSRF, Basic/form authentication và kết quả authorization nếu filter chain được tích hợp.
- Không thể suy rằng đã kiểm tra byte parsing của HTTP connector, giới hạn header/request line, TLS, reverse proxy rewrite, các biến thể path do container giải mã, browser cookie policy, compression và error-page dispatch đúng như trên server thật.
- Một số lỗi chưa xử lý trong filter có thể **ném exception từ `mvc.perform(...)`** trong test, thay vì luôn được biến thành response 500 bởi error page của embedded container.

Với các hành vi container/proxy, dùng thêm HTTP integration test có `@SpringBootTest(webEnvironment = RANDOM_PORT)` hoặc end-to-end test qua topology gần production.

## 3. Ba cách khởi tạo MockMvc và mức độ bao phủ

| Cách khởi tạo | Cái gì được nạp | Filter/Security có tự đúng như app? | Dùng khi |
| --- | --- | --- | --- |
| `MockMvcBuilders.standaloneSetup(controller)` | Controller và các thành phần MVC bạn chỉ định | **Không**; filter phải thêm thủ công, không có đầy đủ ApplicationContext | Test mapping/binding riêng của controller |
| `@WebMvcTest(SomeController.class)` | Slice MVC, các bean hợp lệ theo slice, MockMvc | Có thể auto-configure security, nhưng **không mặc nhiên nạp mọi cấu hình tùy chỉnh và service** | Test MVC/security contract có kiểm soát, mock collaborator |
| `@SpringBootTest` + `@AutoConfigureMockMvc` | Full Spring Boot application context (không khởi chạy socket theo mặc định) | Thường có filters từ context; `addFilters=true` mặc định | Kiểm tra luồng controller + Servlet/Security filters với cấu hình gần app |
| `@SpringBootTest(RANDOM_PORT)` + HTTP client thật | Full context và embedded server thật | Qua Servlet container thực tế | Kiểm tra behavior connector, cookie, encoding, redirect, error dispatch |

Trong Spring Boot 3.x, `@AutoConfigureMockMvc(addFilters = true)` là mặc định. Khi dùng `addFilters = false`, filters từ context sẽ không được đăng ký với MockMvc. Điều này có thể phù hợp với test **chỉ tập trung MVC**, nhưng một test có `addFilters=false` **không còn chứng minh được 401/403/CSRF của security filter chain**.

### Hai hiểu nhầm phổ biến

**“`@SpringBootTest` tự tạo field MockMvc để inject.”** Không phải luôn vậy. Với Spring MVC, muốn Boot tự cấu hình bean `MockMvc`, dùng thêm `@AutoConfigureMockMvc` (hoặc tự dựng builder một cách tường minh).

**“`@WebMvcTest` luôn giống hệt ứng dụng production.”** Không. Slice bỏ phần lớn service/repository và có thể không nạp `@Configuration` tùy chỉnh nằm ngoài tập bean được slice hỗ trợ. Nếu test có security cấu hình khác production thì status có thể khác mà controller không sai.

## 4. Phụ thuộc cần có

Một ví dụ Spring Boot 3.3.x + Java 17+ với Gradle, Spring MVC, Spring Security và Spring Security Test:

Tệp `settings.gradle`:

```groovy
rootProject.name = 'mockmvc-filter-demo'
```

Tệp `build.gradle`:

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

**Vì sao cần `spring-security-test`?** Thư viện cung cấp `SecurityMockMvcRequestPostProcessors`, `SecurityMockMvcResultMatchers`, `SecurityMockMvcConfigurers.springSecurity()`, `@WithMockUser`, `@WithUserDetails`, `@WithAnonymousUser` và các công cụ bổ sung cho security test. `spring-boot-starter-test` đã mang JUnit 5 và MockMvc-related Spring Test, nhưng không thay thế được những extension chuyên biệt của Spring Security.

Version trong ví dụ là **mốc tái hiện API Spring Boot 3.3/Security 6**, không phải lời khuyên tiếp tục dùng bản vá cũ trong production. Dự án thật cần tuân theo phiên bản được duy trì và chính sách cập nhật security của chính dự án. Không trộn package Spring Boot 4.x của test vào đoạn mã Boot 3.x; package import đã đổi ở các major version.

## 5. Ứng dụng demo với Servlet filter và Spring Security

Tạo các tệp sau, giữ nguyên package `com.example.mocksecurity`:

```text
src/main/java/com/example/mocksecurity/
  MockSecurityApplication.java
  SecurityConfig.java
  TraceHeaderFilter.java
  DemoController.java

src/test/java/com/example/mocksecurity/
  FullFilterChainTest.java
```

### 5.1. Entry point — `MockSecurityApplication.java`

```java
package com.example.mocksecurity;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class MockSecurityApplication {
    public static void main(String[] args) {
        SpringApplication.run(MockSecurityApplication.class, args);
    }
}
```

### 5.2. Security config — `SecurityConfig.java`

```java
package com.example.mocksecurity;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
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
    SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/public/ping").permitAll()
                .requestMatchers("/api/admin").hasRole("ADMIN")
                .requestMatchers(HttpMethod.POST, "/api/messages")
                    .hasAuthority("MESSAGE_WRITE")
                .anyRequest().authenticated()
            )
            .httpBasic(Customizer.withDefaults());

        // Không tắt CSRF: POST yêu cầu token khi CSRF đang bật.
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

Điều kiện bảo mật trong ví dụ:

- `GET /public/ping`: `permitAll()` — không yêu cầu đăng nhập, nhưng request vẫn đi qua security filter chain nếu chain được gắn.
- `GET /api/profile`: `anyRequest().authenticated()` — 401 khi chưa xác thực với HTTP Basic, 200 khi thông tin xác thực hợp lệ.
- `GET /api/admin`: yêu cầu `ROLE_ADMIN` — người đã xác thực chỉ có `ROLE_USER` thường nhận 403.
- `POST /api/messages`: yêu cầu authority chính xác `MESSAGE_WRITE` **và** CSRF token hợp lệ. Có Basic credential đúng nhưng thiếu token vẫn bị chặn.
- Mọi URL còn lại đều cần xác thực để đi tới tầng MVC, dù controller có thể trả 404 nếu không có mapping.

Đây là chính sách **demo**. Dùng in-memory credentials chỉ cho local/test. Với REST API stateless chỉ nhận Bearer token từ header, cách xử lý CSRF có thể khác; không sao chép việc tắt/bật CSRF mà chưa đánh giá mô hình xác thực và browser.

### 5.3. Servlet Filter — `TraceHeaderFilter.java`

```java
package com.example.mocksecurity;

import java.io.IOException;

import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;

import org.springframework.core.Ordered;
import org.springframework.core.annotation.Order;
import org.springframework.stereotype.Component;
import org.springframework.web.filter.OncePerRequestFilter;

@Component
@Order(Ordered.HIGHEST_PRECEDENCE + 10)
public class TraceHeaderFilter extends OncePerRequestFilter {

    @Override
    protected void doFilterInternal(
            HttpServletRequest request,
            HttpServletResponse response,
            FilterChain filterChain) throws ServletException, IOException {

        response.setHeader("X-Test-Filter", "executed");
        filterChain.doFilter(request, response);
    }
}
```

`@Component` làm filter thành Spring bean để Boot đăng ký ở Servlet layer. `@Order` yêu cầu chạy rất sớm. Trong demo, vì filter chạy trước Spring Security, phản hồi bị security chặn vẫn mang header `X-Test-Filter: executed`.

**Đừng đăng ký trùng filter:** nếu class đã là `@Component` và Boot tự đăng ký ở Servlet container, không đồng thời tự tạo một `FilterRegistrationBean` khác hoặc dùng `http.addFilterBefore(new TraceHeaderFilter(), ...)` mà không kiểm soát registration. Chạy hai lần có thể làm test/header/log gây hiểu nhầm.

**Lưu ý về `OncePerRequestFilter`:** tên class không có nghĩa nó chạy đúng một lần trong toàn bộ vòng đời mạng. Phạm vi “once” liên quan một request dispatch và cơ chế đánh dấu đã lọc; với `ASYNC`, `ERROR` dispatch còn có các điều kiện/cấu hình riêng như `shouldNotFilterAsyncDispatch()` và `shouldNotFilterErrorDispatch()`.

### 5.4. Controller — `DemoController.java`

```java
package com.example.mocksecurity;

import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.security.core.Authentication;
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

    @GetMapping("/api/profile")
    public String profile(Authentication authentication) {
        return "hello:" + authentication.getName();
    }

    @GetMapping("/api/admin")
    public String admin() {
        return "admin";
    }

    @PostMapping(
        value = "/api/messages",
        consumes = MediaType.APPLICATION_JSON_VALUE)
    @ResponseStatus(HttpStatus.CREATED)
    public String createMessage(@RequestBody MessageRequest request) {
        return "created:" + request.text();
    }

    public record MessageRequest(String text) {
    }
}
```

Không đặt `@PreAuthorize` ở demo vì bài đang tập trung vào **Servlet/Spring Security filters của request**. Trong ứng dụng thật, có thể kết hợp method security và phân quyền theo đối tượng ở service; MockMvc cần được bổ sung test trực tiếp qua service hoặc integration test phù hợp nếu chính sách đó tồn tại.

Ví dụ cũng chưa triển khai lưu dữ liệu thật. Response `created:hello` chỉ chứng minh endpoint controller được gọi sau khi mọi điều kiện security cho phép.

## 6. Tích hợp toàn bộ filter chain với @SpringBootTest + @AutoConfigureMockMvc

Đây là test quan trọng nhất của bài. Tệp `FullFilterChainTest.java`:

```java
package com.example.mocksecurity;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

import org.springframework.security.test.context.support.WithMockUser;

import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.httpBasic;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.user;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class FullFilterChainTest {

    @Autowired
    private MockMvc mvc;

    @Test
    void publicEndpointPassesThroughCustomServletFilter() throws Exception {
        mvc.perform(get("/public/ping"))
            .andExpect(status().isOk())
            .andExpect(content().string("pong"))
            .andExpect(header().string("X-Test-Filter", "executed"));
    }

    @Test
    void anonymousUserIsRejectedBeforePrivateController() throws Exception {
        mvc.perform(get("/api/profile"))
            .andExpect(status().isUnauthorized())
            .andExpect(header().string("X-Test-Filter", "executed"))
            .andExpect(header().exists("WWW-Authenticate"));
    }

    @Test
    void actualHttpBasicCredentialsAreValidatedBySecurity() throws Exception {
        mvc.perform(get("/api/profile")
                .with(httpBasic("reader", "reader-pass")))
            .andExpect(status().isOk())
            .andExpect(content().string("hello:reader"));
    }

    @Test
    void wrongBasicPasswordReturns401() throws Exception {
        mvc.perform(get("/api/profile")
                .with(httpBasic("reader", "wrong")))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void authenticatedReaderCannotOpenAdminRoute() throws Exception {
        mvc.perform(get("/api/admin")
                .with(httpBasic("reader", "reader-pass")))
            .andExpect(status().isForbidden());
    }

    @Test
    @WithMockUser(username = "test-admin", roles = "ADMIN")
    void mockAdminMayAccessAdminRoute() throws Exception {
        mvc.perform(get("/api/admin"))
            .andExpect(status().isOk())
            .andExpect(content().string("admin"));
    }

    @Test
    void requestPostProcessorCanSupplyMockPrincipal() throws Exception {
        mvc.perform(get("/api/profile")
                .with(user("sample-user").roles("USER")))
            .andExpect(status().isOk())
            .andExpect(content().string("hello:sample-user"));
    }

    @Test
    void writerWithValidCsrfAndAuthorityCanPost() throws Exception {
        mvc.perform(post("/api/messages")
                .with(httpBasic("writer", "writer-pass"))
                .with(csrf())
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"text\":\"hello\"}"))
            .andExpect(status().isCreated())
            .andExpect(content().string("created:hello"));
    }

    @Test
    void writerWithoutCsrfIsRejected() throws Exception {
        mvc.perform(post("/api/messages")
                .with(httpBasic("writer", "writer-pass"))
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"text\":\"hello\"}"))
            .andExpect(status().isForbidden());
    }

    @Test
    void writerWithInvalidCsrfIsRejected() throws Exception {
        mvc.perform(post("/api/messages")
                .with(httpBasic("writer", "writer-pass"))
                .with(csrf().useInvalidToken())
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"text\":\"hello\"}"))
            .andExpect(status().isForbidden());
    }

    @Test
    void readerWithCsrfStillLacksWriteAuthority() throws Exception {
        mvc.perform(post("/api/messages")
                .with(httpBasic("reader", "reader-pass"))
                .with(csrf())
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"text\":\"hello\"}"))
            .andExpect(status().isForbidden());
    }
}
```

Trong tệp test, không cần thêm `@ExtendWith(SpringExtension.class)` vì `@SpringBootTest` đã tích hợp Spring Test với JUnit Jupiter. `@AutoConfigureMockMvc` tự đăng ký cấu hình MockMvc phù hợp context Boot; **không dựng một `MockMvcBuilders.standaloneSetup(...)` khác bên trong test này** vì sẽ làm mất phần filter integration đang cần kiểm tra.

### Tại sao từng test có giá trị?

| Test | Điều chứng minh | Giới hạn |
| --- | --- | --- |
| `publicEndpointPassesThroughCustomServletFilter` | Route công khai vẫn có filter tùy chỉnh chạy | Header không chứng minh mọi filter khác đều đúng; cần test security riêng. |
| `anonymousUserIsRejectedBeforePrivateController` | Security chain chặn route cần login | Không kiểm thử credential provider. |
| `actualHttpBasicCredentialsAreValidatedBySecurity` | Basic header đi qua authentication mechanism và user store demo | Không chứng minh password production hoặc external IdP. |
| `wrongBasicPasswordReturns401` | Credentials sai thực sự bị từ chối | Chưa kiểm thử rate limit/brute-force protections. |
| `authenticatedReaderCannotOpenAdminRoute` | Route-level authorization từ chối USER | Chưa kiểm tra quyền theo từng bản ghi. |
| `mockAdminMayAccessAdminRoute` | Quy tắc authority với mock principal | Không chứng minh tài khoản `test-admin` có thật. |
| `writerWithValidCsrfAndAuthorityCanPost` | Có cả authority và token thì controller chạy | Chưa test persistence DB hay proxy/container. |
| `writerWithoutCsrfIsRejected` | CSRF filter đang hoạt động | Không được dùng test này để kết luận người dùng thiếu quyền. |
| `readerWithCsrfStillLacksWriteAuthority` | Bỏ nhiễu CSRF để test đúng logic phân quyền | Không thay thế kiểm tra nghiệp vụ trong service. |

Các body `pong`, `hello:reader`, `admin`, `created:hello` trong controller là chuỗi cố định, nên kết quả `content().string(...)` được xác định rõ. Mã trạng thái có thể khác trong ứng dụng với form login/exception handler khác; đối với **cấu hình demo HTTP Basic nêu trên**, 401/403/201 là các kết quả cần kiểm tra.

### Cách chạy

```bash
# Nếu project đã có Gradle wrapper:
./gradlew test

# Khởi động ứng dụng để thử qua HTTP thật:
./gradlew bootRun
```

Nếu một project vừa tạo chưa có wrapper, dùng `gradle test`/`gradle bootRun` với Gradle tương thích hoặc tạo wrapper theo quy trình dự án. Đây là ví dụ **Spring Boot app**, không biên dịch từng file bằng `javac` đơn thuần vì classpath phụ thuộc Spring/Security/JUnit.

Lúc chạy tests, Gradle/JUnit xuất kết quả tổng hợp, không có một stdout chuẩn duy nhất phải khớp. Các assertions mã HTTP/header/body mới là bằng chứng kiểm thử.

## 7. Phân biệt mock authentication và authentication thật

Spring Security Test cung cấp nhiều công cụ. Chúng giải quyết **các câu hỏi khác nhau**.

### 7.1. `.with(user(...))` — tạo SecurityContext cho request

```java
mvc.perform(get("/api/profile")
        .with(user("alice").roles("USER")))
    .andExpect(status().isOk())
    .andExpect(content().string("hello:alice"));
```

`user(...)` là một `RequestPostProcessor`: gán principal và authorities cho test request theo cơ chế Spring Security Test khi được tích hợp đúng. Người dùng `alice` **không cần có trong database hoặc `UserDetailsService`**.

Dùng khi muốn tập trung kiểm tra các rule như `hasRole`, `hasAuthority`, access control và thông tin principal mà controller/service nhận. Đây **không phải test mật khẩu** hoặc test token JWT thật.

`roles("USER")` sinh authority `ROLE_USER`; còn `authorities("MESSAGE_WRITE")` giữ nguyên tên. Không viết `roles("ROLE_USER")` khi ý định là role USER đơn giản, vì có thể gây sai tiền tố.

### 7.2. `@WithMockUser` — tạo ngữ cảnh xác thực cho một test

```java
@Test
@WithMockUser(username = "report-viewer", roles = {"USER"})
void mockPrincipalExample() throws Exception {
    mvc.perform(get("/api/profile"))
        .andExpect(status().isOk())
        .andExpect(content().string("hello:report-viewer"));
}
```

Annotation thuộc `spring-security-test` và được `WithSecurityContextTestExecutionListener` xử lý; nó thiết lập security context cho test rồi dọn sau khi test kết thúc. Giống `with(user(...))`, nó không xác thực mật khẩu qua `AuthenticationManager`.

Với method security cần principal đặc biệt, `@WithUserDetails` có thể tải người dùng thực từ `UserDetailsService`, còn `@WithSecurityContext` tùy chỉnh hỗ trợ principal/token tùy loại. Đừng gắn `@WithMockUser` cấp class cho **toàn bộ suite** nếu một số test cần anonymous; cách đó sẽ làm test 401 trả 200 và che lỗi.

### 7.3. `.with(httpBasic(...))` — gửi header credentials thực tới filter

```java
mvc.perform(get("/api/profile")
        .with(httpBasic("reader", "reader-pass")))
    .andExpect(status().isOk());

mvc.perform(get("/api/profile")
        .with(httpBasic("reader", "bad-pass")))
    .andExpect(status().isUnauthorized());
```

`httpBasic` postprocessor chỉ tạo header HTTP Basic; nó **không tự cấp user đã đăng nhập**. Khi full Spring Security filter chain có `BasicAuthenticationFilter` và `AuthenticationManager` phù hợp, credentials mới được kiểm tra. Đây là cách kiểm chứng đường xác thực Basic tốt hơn `with(user(...))`.

Tuy nhiên, để kiểm thử session form login, OAuth2 redirect, Bearer JWT hay SAML, phải dùng request/handler đúng cơ chế; không coi Basic là đại diện cho tất cả các loại authentication.

### 7.4. `csrf()` — chỉ dùng cho kiểm thử CSRF, không phải “quyền admin”

```java
mvc.perform(post("/api/messages")
        .with(user("writer").authorities("MESSAGE_WRITE"))
        .with(csrf())
        .contentType(MediaType.APPLICATION_JSON)
        .content("{\"text\":\"ok\"}"))
    .andExpect(status().isCreated());
```

`csrf()` cung cấp token hợp lệ cho request test; `csrf().asHeader()` đưa token trong header, `csrf().useInvalidToken()` chủ động tạo token sai. Nó không thêm authority hay authentication. Và nó **không chứng minh** browser/SPA production có gửi đúng cookie và CSRF token; test live HTTP sẽ làm điều đó.

Tùy thực tế, với cookie session và browser, CSRF là kiểm soát quan trọng. Nếu một test POST gặp 403, trước tiên thử thêm token hợp lệ để tách **CSRF failure** khỏi **authorization failure**, thay vì bỏ `csrf()` hoặc `csrf.disable()` một cách bừa bãi.

## 8. Manual MockMvc builder: dùng springSecurity() đúng chỗ

Khi không muốn dùng `@AutoConfigureMockMvc` và muốn tự dựng MockMvc từ `WebApplicationContext`, cấu hình Spring Security Test cung cấp:

```java
package com.example.mocksecurity;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.setup.MockMvcBuilders;
import org.springframework.web.context.WebApplicationContext;

import static org.springframework.security.test.web.servlet.setup.SecurityMockMvcConfigurers.springSecurity;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
class ManualMockMvcWithSecurityTest {

    @Autowired
    private WebApplicationContext applicationContext;

    private MockMvc mvc;

    @BeforeEach
    void createMvc() {
        mvc = MockMvcBuilders.webAppContextSetup(applicationContext)
            .addFilters(new TraceHeaderFilter())
            .apply(springSecurity())
            .build();
    }

    @Test
    void customFilterAndSecurityAreBothInvoked() throws Exception {
        mvc.perform(get("/api/profile"))
            .andExpect(status().isUnauthorized())
            .andExpect(header().string("X-Test-Filter", "executed"));
    }
}
```

`springSecurity()` gắn Spring Security `FilterChainProxy` và test support cần thiết cho `with(user(...))`, `@WithMockUser`. `addFilters(new TraceHeaderFilter())` thêm **Servlet filter tùy chỉnh** theo cách tường minh để test này bao phủ cả hai. Manual builder **không tự bảo đảm** mọi servlet filter do Boot đăng ký trong production đều đã có mặt; với nhiều filter/order/dispatcher types, `@AutoConfigureMockMvc` thường gần behavior của Boot hơn.

**Cách trên là lựa chọn thay thế** cho `@SpringBootTest + @AutoConfigureMockMvc` đã trình bày ở mục 6. Không nên tự thêm cùng một `FilterChainProxy` hai lần vào builder hoặc thêm lại một Servlet filter đang được builder đăng ký, vì có thể làm filter chạy hai lần và sai kết quả.

### Nếu gọi standaloneSetup

```java
MockMvc mvc = MockMvcBuilders
    .standaloneSetup(new DemoController())
    .build();
```

Đoạn này dựng controller đơn lẻ, chưa có `FilterChainProxy`. Bởi thế `GET /api/admin` có thể trả **200** trong test không security, dù production phải trả 401/403. Đây là **đặc tính của phạm vi test**, không phải một phát hiện lỗi production.

`standaloneSetup` vẫn có giá trị cho unit-ish MVC tests: mapping, body serialization, status hoặc exception resolver bạn đã đăng ký thủ công. Nhưng đừng dùng kết quả standalone làm bằng chứng rằng security rules đang bảo vệ endpoint.

## 9. Slice test @WebMvcTest: đủ nhanh nhưng phải biết thành phần nào đã nạp

`@WebMvcTest(DemoController.class)` chỉ nạp một phần web layer; thường bao gồm controllers, controller advice, MVC-related converters, một số filter, security auto-configuration và MockMvc. **Service/repository bean thông thường** không được tự nạp; hãy mock các collaborator cần thiết hoặc import cấu hình phù hợp.

Ví dụ slice test với controller demo không có service dependency:

```java
package com.example.mocksecurity;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.context.annotation.Import;
import org.springframework.test.web.servlet.MockMvc;

import org.springframework.security.test.context.support.WithMockUser;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@WebMvcTest(DemoController.class)
@Import(SecurityConfig.class)
class DemoControllerSliceTest {

    @Autowired
    MockMvc mvc;

    @Test
    @WithMockUser(username = "admin-in-slice", roles = "ADMIN")
    void adminRuleIsExercisedInSlice() throws Exception {
        mvc.perform(get("/api/admin"))
            .andExpect(status().isOk())
            .andExpect(content().string("admin"));
    }
}
```

`@Import(SecurityConfig.class)` yêu cầu slice sử dụng cấu hình security đã chỉ định, thay vì dựa vào cấu hình ngầm có thể khác app. Với hệ thống thật, hãy kiểm tra các dependency, exception handlers, conversion, servlet filters và security rules nào bị slice loại bỏ; thêm mock và imports có chủ đích. Không nên import toàn bộ mọi service chỉ để biến một slice thành integration test mơ hồ.

Đôi khi test `@WebMvcTest` bị 401 dù bạn chỉ muốn kiểm tra JSON body; có hai lựa chọn hợp lý:

- Giữ filter/security và thêm principal đúng vào request (ví dụ `with(user(...))`), nếu test cần kiểm tra được security behavior.
- Tách một MVC-only test không gắn filters và đặt tên/nội dung rõ là **chỉ kiểm tra MVC behavior**, rồi duy trì một full-chain test riêng để bảo đảm authorization.

Đừng phản ứng bằng cách tắt Security cho toàn bộ dự án test rồi tuyên bố mọi endpoint được bảo vệ.

## 10. Kiểm thử form login, redirect và session khác Basic

Ứng dụng demo mục 5 cấu hình **HTTP Basic**, chưa bật `formLogin`. Vì vậy, ví dụ sau chỉ áp dụng **sau khi ứng dụng được cấu hình form login riêng** bằng `http.formLogin(Customizer.withDefaults())` và `UserDetailsService` tương ứng.

Spring Security Test hỗ trợ request builder `formLogin()`. Với form login mặc định, nó gửi POST `/login` kèm parameter `username`, `password` và **CSRF token hợp lệ**.

```java
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestBuilders.formLogin;
import static org.springframework.security.test.web.servlet.response.SecurityMockMvcResultMatchers.authenticated;
import static org.springframework.security.test.web.servlet.response.SecurityMockMvcResultMatchers.unauthenticated;

// Đặt trong @SpringBootTest + @AutoConfigureMockMvc có formLogin:
mvc.perform(formLogin().user("reader").password("reader-pass"))
    .andExpect(authenticated().withUsername("reader"));

mvc.perform(formLogin().user("reader").password("wrong"))
    .andExpect(unauthenticated());
```

Đây là **minh họa riêng**, không thêm trực tiếp hai lệnh vào class FullFilterChainTest của cấu hình HTTP Basic-only. Khi cấu hình login khác `/login` hoặc đổi tên parameter, dùng overload tương ứng như `formLogin("/auth").user("u", "reader").password("p", "reader-pass")`.

### Kiểm thử SavedRequest và cookie/session

`@WithMockUser` chỉ tạo principal giả trong test; nó **không chứng minh** rằng người dùng đăng nhập thật đã được lưu vào session và có thể đi tiếp sau redirect. Với form login và session-based authentication, bài test nên:

1. Gọi URL được bảo vệ khi chưa login, kiểm tra redirect tới login.
2. Gửi login với CSRF token.
3. Giữ cùng `MockHttpSession`/cookie giữa các request MockMvc.
4. Gọi lại URL được bảo vệ và xác minh authenticated principal.
5. Gọi logout POST với CSRF hợp lệ, rồi kiểm tra URL private không còn được truy cập bằng session cũ.

Khi kiểm thử session, mỗi lần `mvc.perform(...)` tạo request mới. Đừng giả định cookies/session tự được duy trì giữa các lần gọi giống một browser; phải truyền `MockHttpSession` hoặc sử dụng API hỗ trợ quản lý session một cách tường minh. Với redirect, `status().is3xxRedirection()` và `redirectedUrl(...)` kiểm tra phản hồi chuyển hướng; MockMvc **không tự đi theo redirect** như browser.

Nếu dùng OAuth2/OIDC login, HTTP Basic hoặc Bearer JWT, cách lấy context/session và assertions cần thay bằng test support phù hợp. `formLogin()` chỉ kiểm chứng cơ chế form login.

## 11. Khi một ứng dụng có nhiều SecurityFilterChain

Spring Security có thể định nghĩa nhiều bean `SecurityFilterChain` và chọn dựa trên `RequestMatcher`. Ví dụ:

```java
@Bean
@Order(1)
SecurityFilterChain api(HttpSecurity http) throws Exception {
    http
        .securityMatcher("/api/**")
        .authorizeHttpRequests(auth -> auth
            .anyRequest().authenticated()
        )
        .httpBasic(Customizer.withDefaults());
    return http.build();
}

@Bean
@Order(2)
SecurityFilterChain web(HttpSecurity http) throws Exception {
    http
        .authorizeHttpRequests(auth -> auth
            .anyRequest().permitAll()
        );
    return http.build();
}
```

Đây là **ví dụ thay thế** cho bean `SecurityFilterChain` ở mục 5, không đặt ba bean chồng nhau vào cùng demo. Cần imports `@Bean`, `@Order`, `HttpSecurity`, `SecurityFilterChain`, `Customizer` trong lớp config.

Ý nghĩa:

- Chain thứ nhất chỉ áp cho `/api/**`; method `@Order(1)` được xét trước.
- Chain thứ hai là fallback cho request còn lại.
- Mỗi request thường đi qua **SecurityFilterChain đầu tiên khớp** trong `FilterChainProxy`.
- `anyRequest().authenticated()` trong chain đầu tiên **không** bảo vệ path ở ngoài `/api/**`.
- Với các route xử lý authentication/logout, cần chắc đường login/logout cũng nằm trong matcher của chain thích hợp; nếu không, filter có thể không bao giờ xử lý chúng.

Test cần dùng request đại diện **ở mỗi securityMatcher boundary**: `/api/profile`, `/public/ping`, đường fallback, và các route gần giống nhưng không nằm trong matcher. Một test chỉ xác minh `GET /api/profile` chưa chứng minh chain web được cấu hình đúng.

## 12. Chứng minh custom filter có chạy và chạy ở tầng nào

Một response header `X-Test-Filter` là dấu hiệu dễ quan sát, nhưng khi điều tra vấn đề phức tạp cần xem:

- Filter được đăng ký thành **Servlet Filter bean** hay được thêm bằng `http.addFilterBefore/After/At(...)` vào **một SecurityFilterChain**?
- Có filter bị đăng ký **hai lần** ở hai tầng không?
- Đang dùng loại dispatcher `REQUEST`, `FORWARD`, `ERROR` hay `ASYNC` nào?
- `@Order` hay `FilterRegistrationBean.setOrder(...)` kiểm soát vị trí tương đối với `DelegatingFilterProxy` thế nào?
- Một filter có gọi `filterChain.doFilter(...)` không? Nếu trả response sớm thì các filter/handler sau đó có chạy không?
- Test setup có add filters tự động hay chỉ add đúng một filter thủ công?

**Ví dụ chặn request trước controller** (minh họa trong một `OncePerRequestFilter` khác, không thêm thẳng vào DemoController):

```java
if ("blocked".equals(request.getHeader("X-Demo-Mode"))) {
    response.sendError(HttpServletResponse.SC_BAD_REQUEST);
    return;
}
filterChain.doFilter(request, response);
```

Nếu filter được gắn vào MockMvc, request có `X-Demo-Mode: blocked` sẽ không gọi controller. Nhưng chi tiết xử lý `sendError` bởi container thật và `ERROR` dispatch có thể khác MockMvc. Nếu test chỉ thấy status 400, hãy đối chiếu filter nào đã chặn, không suy rằng `@ControllerAdvice` ở MVC đã xử lý.

**Không bắt mọi `RuntimeException` từ `chain.doFilter(...)` để ép tất cả thành 400.** Cách đó có thể che lỗi Security, lỗi chương trình và lỗi dữ liệu, gây status sai hoặc ghi response hai lần.

## 13. CSRF, method, role và status dễ gây nhầm

### 13.1. Thiếu CSRF thường che lỗi authorization

Với cấu hình demo:

```text
POST /api/messages + writer valid Basic + no CSRF
    -> 403 từ CSRF check

POST /api/messages + reader valid Basic + valid CSRF
    -> 403 vì thiếu MESSAGE_WRITE

POST /api/messages + writer valid Basic + valid CSRF
    -> 201 từ controller

GET /api/profile + reader valid Basic
    -> 200

GET /api/profile + anonymous
    -> 401 + HTTP Basic challenge
```

Thứ tự cụ thể của security filters thay đổi theo cấu hình, nhưng trong demo, việc thiếu CSRF có thể chặn POST trước khi rule authorization của controller được dùng. Vì thế chỉ thấy “403” không cho biết **đó là lỗi thiếu quyền hay CSRF**. Tạo hai test riêng như mục 6 để cô lập nguyên nhân.

### 13.2. Phân biệt role và authority

- `hasRole("ADMIN")` mặc định so khớp authority `ROLE_ADMIN`.
- `hasAuthority("MESSAGE_WRITE")` so khớp chuỗi chính xác `MESSAGE_WRITE`.
- `user("alice").roles("ADMIN")` tạo role có tiền tố theo quy ước.
- `user("alice").authorities("MESSAGE_WRITE")` tạo authority nguyên văn.

Nếu test dùng `@WithMockUser(roles="ADMIN")` trả 200 nhưng user thật từ JWT/DB vẫn 403, có thể mối quan hệ giữa claims/roles/authorities khi chuyển thành `GrantedAuthority` chưa đúng. Test bằng mock principal không thể chứng minh converter hoặc identity provider thật; phải có test cho credential/token-to-authority mapping.

### 13.3. Form login có thể 302 thay vì 401

Khi ứng dụng bật form login và dùng `LoginUrlAuthenticationEntryPoint`, request ẩn danh vào tài nguyên bảo vệ thường **redirect 302** về trang login. Với HTTP Basic entry point, request đó thường trả **401** và `WWW-Authenticate`. Vì thế đừng copy assertion 401 của demo Basic sang ứng dụng browser form login mà không hiểu cấu hình.

### 13.4. Method-level security

Nếu service sử dụng `@PreAuthorize`, test `@WebMvcTest` có thể không nạp service/proxy thật; bạn cần test method security hoặc full-context riêng. `@EnableMethodSecurity` phải được bật. Đồng thời lưu ý Spring proxy self-invocation: `this.protectedMethod()` trong cùng object có thể bỏ qua interceptor. MockMvc test một controller giả lập service sẽ không bắt được lỗi này.

## 14. Xử lý async dispatch, ERROR dispatch và giới hạn giả lập

### 14.1. Async controller

Spring MVC hỗ trợ controller trả `Callable` hoặc `DeferredResult`. Với MockMvc, lần `perform` đầu có thể bắt đầu async processing, và phải dùng `asyncDispatch` để kiểm tra response cuối:

```java
// Đoạn minh họa sau giả định ứng dụng có
// GET /api/async trả về Callable<String>.
MvcResult result = mvc.perform(get("/api/async")
        .with(user("reader").roles("USER")))
    .andExpect(request().asyncStarted())
    .andReturn();

mvc.perform(asyncDispatch(result))
    .andExpect(status().isOk())
    .andExpect(content().string("done"));
```

Các imports tĩnh tương ứng:

```java
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.asyncDispatch;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.request;
```

Đây là **snippet phụ thuộc endpoint `/api/async`**; không có trong DemoController ban đầu. Nếu muốn thử độc lập, thêm method sau vào controller:

```java
@GetMapping("/api/async")
public java.util.concurrent.Callable<String> async() {
    return () -> "done";
}
```

Khi chạy async, cần kiểm tra security context có được truyền đúng đến giai đoạn xử lý async hay không; không dựa vào `ThreadLocal` tùy tiện trong worker thread. Filter nào được gọi lại ở `ASYNC` dispatch tùy registration/`OncePerRequestFilter`. Một test header ở request đầu chưa chứng minh filter chạy trên mọi dispatch.

### 14.2. ERROR dispatch và lỗi filter

Spring Boot có cơ chế `/error` dựa trên container error pages. Khi exception thoát khỏi filter, MockMvc **không tái tạo đầy đủ** error dispatch của Tomcat. Vì vậy:

- Nếu `mvc.perform(...)` ném exception, không tự kết luận production trả response body giống exception đó.
- Nếu thật sự cần xác minh `BasicErrorController`, `DispatcherType.ERROR`, headers sau `sendError` hoặc filter nhận ERROR dispatch, hãy chạy embedded server với random port và HTTP client thực.
- Test `@ControllerAdvice` chỉ kiểm chứng exception thuộc vòng đời MVC; exception từ filter trước `DispatcherServlet` **không tự** đi vào MVC exception resolver.

### 14.3. URL encoding và container firewall

MockMvc có thể dựng request với path được cấu hình trực tiếp; HTTP server và proxy ngoài thực tế có thể chuẩn hóa/giải mã encoded slash, `..`, semicolon hoặc backslash trước khi Spring Security thấy request. Dùng MockMvc để test `HttpFirewall` và matcher ở mức Spring là hữu ích, nhưng không kết luận rằng production connector xử lý URI “y hệt”.

Nếu threat model phụ thuộc encoded path, request smuggling, HTTP/2, transfer encoding, header size hay TLS, cần test thêm qua **đúng đường HTTP thật**, không dựng riêng `MockHttpServletRequest` rồi xem là đủ.

## 15. HTTP integration test bổ sung cho MockMvc

Khi cần kiểm tra embedded servlet container, Spring Boot có:

```java
@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class RealHttpIntegrationTest {
    // Dùng một HTTP client thực gửi request tới port được cấp.
    // Kiểm tra status, redirect, cookies, headers và error dispatch.
}
```

Đây là **mẫu annotation**, không phải tệp test đầy đủ. Có thể dùng `@LocalServerPort` để lấy port thực rồi gửi request bằng RestClient, TestRestTemplate hoặc thư viện HTTP client trong test class. Cần chọn HTTP client đúng dependency và phiên bản Spring Boot đang dùng; không mặc định mọi client tự giữ session/cookie.

Với DemoController ở mục 5 chạy local qua `bootRun`, có thể dùng curl:

```bash
# 200 + pong
curl -i http://localhost:8080/public/ping

# 401 + WWW-Authenticate (HTTP Basic)
curl -i http://localhost:8080/api/profile

# 200 + hello:reader
curl -i -u reader:reader-pass http://localhost:8080/api/profile

# 403 vì reader không có ROLE_ADMIN
curl -i -u reader:reader-pass http://localhost:8080/api/admin
```

Các lệnh POST/CSRF qua HTTP thật cần có **CSRF token hợp lệ** từ cơ chế cấp token của ứng dụng; `.with(csrf())` là công cụ MockMvc, không phải thứ curl tự thêm. Demo chưa định nghĩa endpoint cấp token riêng, vì bài tập trung vào MockMvc; nếu triển khai browser/SPA thực tế, thêm và kiểm thử phương án cấp CSRF token phù hợp ứng dụng.

## 16. Đọc kết quả test để chẩn đoán chính xác

Một checklist điều tra khi test thất bại:

| Hiện tượng | Nguyên nhân đáng kiểm tra | Bằng chứng nên thu thập |
| --- | --- | --- |
| Mọi protected GET đều trả 200 cho anonymous | MockMvc không gắn Security FilterChainProxy, `addFilters=false` hoặc rule quá rộng | Test 401 cố ý, cấu hình builder, bean `springSecurityFilterChain` |
| Mọi POST đều trả 403 | CSRF token thiếu/sai, hoặc deny rule | So sánh POST có/không `with(csrf())` cùng principal |
| Test dùng `@WithMockUser` pass nhưng Basic thật 401 | Mock principal bỏ qua bước authenticate, user/pass sai hoặc password encoder lỗi | Test `httpBasic` đúng/sai credentials |
| Test 401 kỳ vọng nhưng nhận 302 | Form login/entry point redirect | Header `Location`, `SecurityFilterChain` tương ứng |
| Filter header không có | Filter không được đăng ký trong MockMvc, sai path/dispatcher type, thứ tự/response rewrite | Inspect filter registration và test riêng đường public/protected |
| Controller advice không chạy với lỗi filter | Exception ném trước `DispatcherServlet` | Stack trace điểm phát sinh, filter/ERROR dispatch |
| Test slice bị thiếu bean service | `@WebMvcTest` không nạp phần lớn service beans | Mock collaborator hoặc chuyển full context test |
| MockMvc xanh nhưng production path lạ bị chặn | Connector/proxy decode URI khác mô phỏng | Live request raw path qua đúng proxy/connector |
| Session giữa hai `perform` mất | Chưa truyền lại `MockHttpSession`, test không thực hiện login thật | Inspect session/cookie và login filter handler |
| Một filter chạy hai lần | Đăng ký cả Servlet Filter lẫn Security filter, nhiều dispatch hoặc hai lần add vào MockMvc | Liệt kê filter registrations, dispatch type và call trace |

Khi cần xem thông tin request trong test, dùng `andDo(print())` tại test đang điều tra:

```java
mvc.perform(get("/api/profile"))
    .andDo(print())
    .andExpect(status().isUnauthorized());
```

Import:

```java
import static org.springframework.test.web.servlet.result.MockMvcResultHandlers.print;
```

Nó cho bạn request/handler/status/headers/body ở mức MockMvc. Không đưa password, cookie, bearer token hoặc PII thực vào log CI. Đối với security chain chi tiết, bật logging phù hợp cho `org.springframework.security` trong **môi trường test** và chỉ khi cần, sau đó tắt mức verbose.

### Chú ý khi dùng @MockitoBean/@MockBean

Spring Framework đời mới có `@MockitoBean` để thay thế bean trong test context, còn ví dụ Spring Boot 3.3 cũ thường dùng `@MockBean`. Nếu bean service/repository bị mock và mặc định trả dữ liệu trống, một test controller có thể báo 404 dù security đã cho phép. Cần cấu hình giá trị mock đúng để test phân biệt lỗi business với lỗi security. Đừng mock `SecurityFilterChain` hoặc `AuthenticationManager` vô tội vạ rồi coi test là chứng minh được authentication thực.

## 17. Những sai lầm làm test bảo mật “xanh giả”

1. **Chỉ dùng `standaloneSetup` để chứng minh phân quyền:** builder không có full filters trừ khi tự thêm.
2. **Tắt `addFilters` để “sửa” 401/403:** test mất lớp đang cần kiểm tra.
3. **Gắn `@WithMockUser` ở cả class rồi test anonymous:** anonymous test thực tế có user giả.
4. **Dùng `with(user(...))` để nói mật khẩu/JWT đã được xác thực:** công cụ này tạo test principal.
5. **Quên `with(csrf())` với POST/PUT/DELETE:** test có thể dừng tại CSRF trước khi đạt rule chức năng.
6. **Chỉ assert status 403:** không biết do CSRF, thiếu authority hay deny rule; cần test từng nguyên nhân.
7. **Không kiểm tra custom Servlet filter registration:** thành công controller chưa có nghĩa audit/header/filter được gọi.
8. **Đăng ký filter hai lần:** test khác production hoặc có side effect lặp.
9. **Giả định `@WebMvcTest` mang mọi config/service:** slice loại nhiều bean, kể cả @Configuration tùy chỉnh.
10. **Không thử route outside `securityMatcher`:** một phần URL có thể không đi qua chain bạn nghĩ.
11. **Nhầm `MockMvc` với HTTP server thật:** mất kiểm tra URL parsing, TLS, container error page và reverse proxy.
12. **Tin status 200 đồng nghĩa request thật được bảo vệ:** nếu bypass filters thì 200 chỉ phản ánh controller.
13. **Không test credential sai hoặc principal không tồn tại:** mock principal pass chưa chứng minh authentication provider.
14. **Bỏ kiểm tra side effects sau deny:** một handler/service có thể sửa dữ liệu trước khi quyết định quyền nếu thiết kế sai; với use case update/delete cần kiểm tra DB không đổi.
15. **Viết test pass bằng cách hard-code response của security mock:** có thể không xác minh chain thực thi.
16. **Test không tách tầng:** cần MVC-focused tests, filter-chain tests và live HTTP tests có mục tiêu cụ thể, đủ để tìm đúng nguyên nhân khi thất bại.

## 18. Bộ tiêu chí hoàn thành bài kiểm thử Filter Chain

- [ ] Test rõ loại ứng dụng: Servlet MVC (không nhầm WebFlux/WebTestClient reactive).
- [ ] Dependency `spring-security-test` được khai báo cho test scope.
- [ ] `@SpringBootTest` + `@AutoConfigureMockMvc` chạy với `addFilters=true` khi cần full chain.
- [ ] Có test anonymous GET protected và xác minh 401/redirect theo entry point đang dùng.
- [ ] Có test credential đúng/sai qua authentication filter thật cho cơ chế ứng dụng sử dụng.
- [ ] Có test authenticated nhưng thiếu quyền, phân biệt với chưa xác thực.
- [ ] Có test request có CSRF token hợp lệ và thiếu/sai token.
- [ ] Có test custom Servlet filter: header/behavior được quan sát khi controller chạy và khi Security chặn.
- [ ] Có kiểm tra route nằm ngoài hoặc giao nhau giữa nhiều `securityMatcher`.
- [ ] Có kiểm tra handler/business không chạy khi request bị chặn, nhất là khi thao tác thay đổi dữ liệu.
- [ ] Có test controller advice riêng và hiểu filter exceptions không tự thuộc MVC resolver.
- [ ] Có test HTTP thật khi cần chứng minh container, proxy, URI encoding, cookie, redirect hoặc error dispatch.
- [ ] Không dùng `@WithMockUser` để thay thế bài test xác thực thật.
- [ ] Không dùng `standaloneSetup` hoặc `addFilters=false` làm bằng chứng toàn bộ security chain.
- [ ] Đã kiểm tra cấu hình bean và package của ứng dụng trong test; không xuất hiện filter duplication không mong đợi.

### Câu hỏi tự kiểm tra

1. Vì sao `MockMvcBuilders.standaloneSetup(new DemoController())` có thể trả 200 cho `/api/admin` khi ứng dụng production trả 401/403?
2. `@AutoConfigureMockMvc(addFilters=false)` làm mất bằng chứng bảo mật nào?
3. `springSecurity()` làm gì khi dùng `MockMvcBuilders.webAppContextSetup(...)`?
4. Khác biệt giữa `with(user("reader"))` và `with(httpBasic("reader","reader-pass"))` là gì?
5. Vì sao một POST không có CSRF token có thể trả 403 dù writer có `MESSAGE_WRITE`?
6. `@WithMockUser(roles="ADMIN")` có chứng minh tài khoản admin tồn tại trong database không?
7. Vì sao `@WebMvcTest` có thể cho kết quả khác `@SpringBootTest` dù cùng controller?
8. Cần test thêm gì nếu reverse proxy/container có cách xử lý encoded URL khác MockMvc?
9. Một exception phát sinh trong Servlet Filter có tự chạy `@RestControllerAdvice` không?
10. Vì sao phải thử các URL thuộc nhiều `securityMatcher` khác nhau?
11. Một `OncePerRequestFilter` có chắc chỉ chạy một lần cho cả REQUEST, ASYNC và ERROR không?
12. Làm thế nào xác minh rằng một request bị chặn không làm thay đổi dữ liệu?

**Gợi ý:** (1) standalone chưa đăng ký security filters; (2) authorization, CSRF, custom filter processing; (3) đăng ký FilterChainProxy và security test integration; (4) principal mock so với gửi Basic header để filter xác thực; (5) CSRF filter chặn trước; (6) không; (7) slice khác full context; (8) live HTTP test trên đúng server/proxy; (9) không tự động; (10) lựa chọn chain theo matcher; (11) phụ thuộc dispatcher types và filter behavior; (12) assert state DB/side effect bên cạnh HTTP status.

## Tài liệu chính thức để đối chiếu theo phiên bản

- Spring Security 6.5 — Setting up MockMvc and Spring Security: https://docs.spring.io/spring-security/reference/6.5/servlet/test/mockmvc/setup.html
- Spring Security — Running a Test as a User: https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/authentication.html
- Spring Security — Testing HTTP Basic: https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/http-basic.html
- Spring Security — Testing CSRF: https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/csrf.html
- Spring Security — Testing Form Login: https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/form-login.html
- Spring Security — Testing Method Security: https://docs.spring.io/spring-security/reference/6.5/servlet/test/method.html
- Spring Framework — MockMvc Setup Options: https://docs.spring.io/spring-framework/reference/testing/mockmvc/setup-options.html
- Spring Boot 3.3 — Testing Spring Boot Applications: https://docs.spring.io/spring-boot/3.3/reference/testing/spring-boot-applications.html
- Spring Security — Servlet Security Architecture: https://docs.spring.io/spring-security/reference/servlet/architecture.html
