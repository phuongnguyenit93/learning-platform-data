# Giới hạn của việc tắt filter để làm test thành công

## 1. Test xanh có thật sự chứng minh bảo mật đúng?

Một bài kiểm thử Spring Boot gửi `POST /api/items` qua `MockMvc`, nhận `403 Forbidden`, rồi developer thay annotation thành `@AutoConfigureMockMvc(addFilters = false)`. Bây giờ response là `201 Created` và CI chuyển xanh. Nhưng thay đổi đã loại bỏ việc đăng ký các Servlet Filters từ ApplicationContext vào MockMvc. Nếu hệ thống dùng Spring Security trên Servlet stack, request-level authentication, authorization, CSRF và security headers thường được thi hành qua `FilterChainProxy`, một Filter có thể đã bị bỏ qua.

**Kết luận:** kết quả thành công trong một đường MockMvc không chạy filters **không chứng minh** cùng request được phép khi đi qua server HTTP thật. Đây có thể là cách cô lập một controller-only test, nhưng không phải cách sửa test bảo mật đang thất bại.

Bài học tập trung vào **giới hạn của hành vi tắt filter để làm test pass**. Nội dung dùng Java 17+, Spring Boot 3.5.x, Spring Security 6.x, Spring MVC và JUnit Jupiter. Một ví dụ đầy đủ gồm ứng dụng REST có security policy, **9 bài test giữ filters**, **7 bài test đối chứng** nơi MockMvc bypass nhưng HTTP server vẫn bảo vệ. Khi dùng Spring Boot 4.x, imports/starter packages có thể thay đổi; kiểm tra tài liệu theo major version.

Bạn sẽ phân biệt được:

- MockMvc context-filter registration khác với Servlet filter chain trên HTTP server.
- `@WithMockUser`, `user(...)` và `csrf()` khác `addFilters=false` ra sao.
- Những security contract dễ biến mất khỏi test: 401, 403, role, CSRF, response headers, custom filters.
- Ranh giới method security, MVC interceptors và Bean Validation vẫn có thể hoạt động.
- Khi nào controller-only bypass hợp lý và khi nào nhất thiết phải giữ filters.
- Cách kiểm tra custom SecurityFilterChain, CORS, JWT/OAuth2, tenant context và CI.
- Nguyên tắc không đổi production security chỉ để chiều lòng một test fixture sai.

## 2. HTTP request đi qua những ranh giới nào?

```text
CLIENT HTTP THẬT
      |
      v
Servlet container
      |
      +-- Registered servlet filter chain
      |      |
      |      +-- Spring Security FilterChainProxy
      |      |      - security context/authentication
      |      |      - CSRF
      |      |      - request authorization
      |      |      - exception translation
      |      |      - security response headers
      |      |
      |      +-- Custom servlet filters
      |             - tenant/correlation/audit/CORS...
      |
      v
DispatcherServlet
      |
      +-- MVC HandlerInterceptor / argument resolvers
      |
      v
Controller -> Spring service -> repository
```

Sơ đồ là mô hình khái niệm; tập filters, thứ tự và implementation thực tế do Spring Security/application configuration quyết định. Trong MockMvc được Spring Boot auto-configure, filters từ ApplicationContext được đưa vào MockMvc khi `addFilters=true` (mặc định). Đổi sang false sẽ không thêm các context filters ấy vào MockMvc.

```text
@SpringBootTest + @AutoConfigureMockMvc
      |
      v
    MockMvc
      |
      +-- Context filters (default true)
      +-- Spring Security FilterChainProxy
      |
      v
 DispatcherServlet -> Controller

@SpringBootTest + @AutoConfigureMockMvc(addFilters=false)
      |
      v
    MockMvc
      |
      +-- No context-filter registration by Boot builder
      |
      v
 DispatcherServlet -> Controller
```

**Điều dễ bỏ sót:** một Spring Boot test dùng `RANDOM_PORT` có thể vừa inject MockMvc vừa mở server thật. Flag `addFilters=false` áp dụng cho **MockMvc**, không biến request qua real server thành bypass request.

## 3. Chính xác @AutoConfigureMockMvc(addFilters=false) làm gì?

Theo Spring Boot 3.5 Javadoc, thuộc tính `addFilters` kiểm soát có đăng ký các filters từ ApplicationContext với MockMvc hay không; default là **true**.

| Thành phần | Bị ảnh hưởng bởi addFilters=false? | Ghi chú |
|---|---|---|
| MockMvc do Spring Boot auto-configure | **Có** | Bỏ đăng ký context filters |
| Spring Security servlet chain trong MockMvc path | **Thông thường có** | FilterChainProxy không được chạy theo đường ấy |
| HTTP server thật trên RANDOM_PORT | **Không do flag này** | Servlet container vẫn đăng ký filters bình thường |
| Bean SecurityFilterChain trong Spring context | Không nhất thiết | Bean vẫn có thể tồn tại, dù MockMvc không thực thi |
| `@PreAuthorize` trên Spring-managed service | Không trực tiếp | Method-security AOP hoạt động nếu được bật và gọi qua proxy |
| MVC HandlerInterceptor | Không mặc nhiên | Khác Servlet Filter |
| `@Valid`/Bean Validation ở MVC layer | Không trực tiếp | Vẫn có thể validate DTO |
| `@ControllerAdvice` | Không trực tiếp | HandlerExceptionResolver vẫn có thể xử lý |
| Database row-level security | Không trực tiếp | Nằm tại database resource |
| WebFlux WebFilter | Không thuộc API này | Đây là Servlet MockMvc setting |
| MockMvc tự dựng bằng standalone builder | Phụ thuộc setup riêng | Không thể suy từ annotation Boot cho mọi instance |

Một test vẫn nhận 403 sau addFilters=false không chứng minh security filters còn được áp dụng; có thể service `@PreAuthorize` hoặc một interceptor riêng vẫn chặn. Ngược lại, nếu controller chỉ dựa vào URL authorization ở filter chain, test có thể trả 200 cho anonymous.

### 3.1. Không nhầm các lựa chọn khác nhau

- `addFilters=false`: thay **MockMvc filter registration**, có thể bỏ cả các custom Servlet Filters khác.
- `authorizeHttpRequests(...permitAll())`: thay **URL authorization rule**; filter chain còn tồn tại và có thể vẫn thực thi CSRF, security headers.
- `csrf.disable()`: thay CSRF policy; không tự bỏ authentication/authorization.
- `@WithMockUser`: fake một authenticated principal trong test security context, nhưng authorization vẫn được kiểm tra nếu chain tích hợp đúng.
- `user("name").roles("USER")`: request-specific test identity.
- `csrf()`: cung cấp token CSRF test hợp lệ.
- Excluding SecurityAutoConfiguration: đổi cấu hình/beans của Spring context, không tương đương MockMvc flag.
- Mock `SecurityFilterChain` hoặc `FilterChainProxy`: thay chính đường security; cần xác định scope/coverage cẩn thận, không phải “sửa nhanh”.

**Không đổi một bảo vệ production chỉ để giữ test trả 2xx.** Trước hết xác định fixture của test sai hay production policy thực sai.

## 4. Vì sao bypass filters tạo false positives?

### 4.1. Authentication

Một endpoint chỉ dành cho authenticated user phải từ chối request không đăng nhập. Trong HTTP Basic demo, kết quả mong đợi là 401. Với form login có thể là 302 redirect, với Bearer token/resource server có thể trả 401 và WWW-Authenticate. Khi bỏ security filters khỏi MockMvc, controller có thể được gọi và trả 200, che lỗi authentication config hoặc rule.

### 4.2. Authorization

Một endpoint `/api/admin/metrics` đòi `ROLE_ADMIN`. Test chỉ sử dụng user admin và expect 200 không chứng minh USER bị cấm; test bỏ filter còn tệ hơn vì cả anonymous có thể nhận 200. Phải có **negative tests**: anonymous bị từ chối, USER bị 403 và ADMIN được 200.

Spring Security `hasRole("ADMIN")` thường kiểm tra authority `ROLE_ADMIN`. `@WithMockUser(roles="ADMIN")` và `@WithMockUser(authorities="ADMIN")` **không tương đương** về prefix. Test 403 do role prefix sai cần sửa fixture/policy, không tắt security.

### 4.3. CSRF

Trong nhiều servlet apps có browser/cookie/session authentication, CSRF protection áp dụng với unsafe methods như POST/PUT/PATCH/DELETE. Một user đã authenticated vẫn có thể nhận 403 nếu không gửi valid token. Đừng tắt toàn bộ filters để GET/POST cùng pass.

Spring Security test có request postprocessor:

```java
mvc.perform(post("/api/items")
        .with(user("viewer").roles("USER"))
        .with(csrf())
        .contentType(MediaType.APPLICATION_JSON)
        .content("{\"name\":\"draft\"}"))
        .andExpect(status().isCreated());
```

Đây là snippet dùng trong full example, cần `spring-security-test` và security-enabled MockMvc. CSRF necessity phụ thuộc threat model: stateless Bearer token API có thể khác browser cookie/session API. Câu “REST API không cần CSRF” không phải quy tắc đúng cho mọi kiến trúc.

### 4.4. Security response headers

Spring Security có thể thêm `X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY` và cache headers. Khi security filter chain bị bỏ khỏi MockMvc, một test chỉ nhìn status/body không phát hiện header bị mất. HSTS được thêm theo điều kiện HTTPS, không nên mặc định assert trên plain HTTP; CSP có thể phải cấu hình thêm.

### 4.5. Custom Servlet Filters

Flag `addFilters=false` không giới hạn ở Spring Security. Nó còn có thể bỏ qua filters do ứng dụng định nghĩa cho:

- tenant context/row ownership;
- correlation ID/MDC/tracing/audit;
- custom request validation hoặc body wrapper;
- rate limiting;
- CORS tại Servlet filter layer;
- security headers tùy biến.

Một test không chạy tenant filter có thể trả đúng JSON trên fixture mặc định nhưng thực tế service rò dữ liệu qua tenant. Trong hệ thống multi-tenant, đây là rủi ro security thực, không chỉ test coverage.

## 5. Bypass không tắt toàn bộ security ở mọi layer

Method security là ví dụ đáng chú ý:

```java
@Configuration
@EnableMethodSecurity
class MethodSecurityConfig {}

@Service
class AccountService {
    @PreAuthorize("hasRole('ADMIN')")
    public void closeAccount() {
        // Protected by method-security advice when enabled.
    }
}
```

Đây là **snippet minh họa**, không phải file của ứng dụng runnable phía dưới. Nếu method security đã bật và service được gọi qua Spring proxy, `@PreAuthorize` có thể vẫn deny khi Servlet filters bị bỏ khỏi MockMvc. Spring Boot starter-security **không tự bật method security** trong mọi ứng dụng; cần `@EnableMethodSecurity`.

Tương tự, MVC interceptors, Bean Validation, controller advice và DB policies có ranh giới riêng. Vì thế tránh cả hai suy diễn sai: “addFilters=false tắt mọi bảo mật” và “vẫn còn 403 nên security filters chắc chắn được test”.

## 6. Phân biệt đúng các HTTP lỗi

| Kết quả | Nguyên nhân có thể | Cách kiểm tra |
|---|---|---|
| 401 với HTTP Basic/Bearer | Chưa authenticated, credentials thiếu/sai | Authentication entry point và principal |
| 403 với user cho GET admin | Authorization deny | Role/authority, matcher, method security |
| 403 với POST có user | CSRF thiếu/sai hoặc authorization | Thử token `csrf()` khi policy yêu cầu |
| 302 tới login | Form login entry point | Redirect target/session |
| 400 | DTO/body/Bean Validation | JSON/content type/validators |
| 404 | Path/handler không có hoặc policy ẩn resource | Route mapping, filter path |
| 405 | HTTP method không hợp lệ | @GetMapping/@PostMapping |
| 5xx | Exception/service/config lỗi | Root cause, logs đã redact |

Khi POST **vừa anonymous vừa thiếu CSRF**, CSRF filter có thể reject trước authentication entry point, tạo 403 thay vì 401. Để tìm nguyên nhân, test GET anonymous riêng, POST có user nhưng thiếu CSRF riêng, POST có CSRF nhưng anonymous riêng, cuối cùng POST có cả user lẫn token.

## 7. Ví dụ Java 17+/Spring Boot 3.5: một application, hai đường test

Ứng dụng demo có:

- `GET /public/ping` — public.
- `GET /api/items` — cần authenticated user.
- `POST /api/items` — authenticated và valid CSRF token.
- `GET /api/admin/metrics` — chỉ ROLE_ADMIN.

Security configuration dùng HTTP Basic để 401/403 dễ quan sát, InMemoryUserDetailsManager với **hai account giả chỉ cho demo**, không có DB. Test class thứ nhất giữ filters (9 methods). Test class thứ hai cố ý bỏ filters khỏi MockMvc nhưng gửi thêm HTTP request thật tới `RANDOM_PORT` (7 methods). **Tổng 16 JUnit tests**.

Không dùng credentials demo trong production; production phải có identity provider/user store và HTTPS phù hợp.

### 7.1. Dependency snippets

**Gradle Groovy DSL** trong project đã có Boot 3.5 plugin, BOM/dependency management, repositories và Java 17 toolchain:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}

tasks.named('test', Test) {
    useJUnitPlatform()
}
```

**Maven** trong project đã có Spring Boot 3.5 parent/BOM và compiler/Surefire phù hợp:

```xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-web</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-security</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-test</artifactId>
        <scope>test</scope>
    </dependency>
    <dependency>
        <groupId>org.springframework.security</groupId>
        <artifactId>spring-security-test</artifactId>
        <scope>test</scope>
    </dependency>
</dependencies>
```

Đây là **trích đoạn dependencies**, không phải build files đầy đủ. `spring-security-test` cần khai báo explicit để dùng `@WithMockUser`, `user(...)` và `csrf()`.

### 7.2. File tree

```text
src/
├── main/java/com/example/securityfilters/
│   ├── SecurityFiltersApplication.java
│   ├── DemoSecurityConfiguration.java
│   └── ItemController.java
└── test/java/com/example/securityfilters/
    ├── FilterEnabledMockMvcTest.java
    └── BypassMockMvcAndRealHttpTest.java
```

### 7.3. Main application

**File `src/main/java/com/example/securityfilters/SecurityFiltersApplication.java`:**

```java
package com.example.securityfilters;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class SecurityFiltersApplication {
    public static void main(String[] args) {
        SpringApplication.run(SecurityFiltersApplication.class, args);
    }
}
```

### 7.4. Security configuration thực

**File `src/main/java/com/example/securityfilters/DemoSecurityConfiguration.java`:**

```java
package com.example.securityfilters;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.factory.PasswordEncoderFactories;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;

@Configuration(proxyBeanMethods = false)
public class DemoSecurityConfiguration {

    @Bean
    SecurityFilterChain filterChain(HttpSecurity http) throws Exception {
        http.authorizeHttpRequests(auth -> auth
                .requestMatchers("/public/**").permitAll()
                .requestMatchers("/api/admin/**").hasRole("ADMIN")
                .anyRequest().authenticated());
        http.httpBasic(Customizer.withDefaults());
        http.csrf(Customizer.withDefaults());
        return http.build();
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return PasswordEncoderFactories
                .createDelegatingPasswordEncoder();
    }

    @Bean
    UserDetailsService users(PasswordEncoder encoder) {
        UserDetails viewer = User.withUsername("viewer")
                .password(encoder.encode("viewer-pass"))
                .roles("USER")
                .build();
        UserDetails admin = User.withUsername("admin")
                .password(encoder.encode("admin-pass"))
                .roles("ADMIN")
                .build();
        return new InMemoryUserDetailsManager(viewer, admin);
    }
}
```

**Giải thích:** public URL được `permitAll` nhưng filter chain vẫn chạy và thêm headers. Admin URL cần `ROLE_ADMIN`. Các URL còn lại cần authenticated principal. HTTP Basic tạo 401 thay vì form-login 302. CSRF vẫn bật cho POST. Passwords chỉ là **giả trong demo**, được encode bằng PasswordEncoder; không hardcode chúng vào ứng dụng production.

Để phân biệt rõ Servlet filter với method security, application demo **không bật @EnableMethodSecurity**. Admin restriction được đặt chỉ trong request-level SecurityFilterChain.

### 7.5. Controller deterministic

**File `src/main/java/com/example/securityfilters/ItemController.java`:**

```java
package com.example.securityfilters;

import java.util.List;
import java.util.Map;

import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.ResponseStatus;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class ItemController {

    public record Item(String id, String name) {}
    public record NewItem(String name) {}

    @GetMapping("/public/ping")
    public Map<String, String> ping() {
        return Map.of("status", "up");
    }

    @GetMapping("/api/items")
    public List<Item> items() {
        return List.of(new Item("item-1", "Sample"));
    }

    @PostMapping("/api/items")
    @ResponseStatus(HttpStatus.CREATED)
    public Item create(@RequestBody NewItem body) {
        return new Item("created-1", body.name());
    }

    @GetMapping("/api/admin/metrics")
    public Map<String, Integer> metrics() {
        return Map.of("items", 1);
    }
}
```

Controller không tự kiểm tra principal/roles/CSRF; security filters chịu trách nhiệm trước DispatcherServlet. Vì demo không có DB, status 201 chỉ cho biết response đã được tạo, không phải transaction đã commit.

## 8. Test giữ filter chain: 9 trường hợp nên có

**File `src/test/java/com/example/securityfilters/FilterEnabledMockMvcTest.java`:**

```java
package com.example.securityfilters;

import org.junit.jupiter.api.Test;

import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.security.test.context.support.WithMockUser;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.user;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest(classes = SecurityFiltersApplication.class)
@AutoConfigureMockMvc
class FilterEnabledMockMvcTest {

    @Autowired MockMvc mvc;

    @Test
    void publicRouteIs200AndHasSecurityHeader() throws Exception {
        mvc.perform(get("/public/ping"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.status").value("up"))
                .andExpect(header().string(
                        "X-Content-Type-Options", "nosniff"));
    }

    @Test
    void anonymousCannotReadProtectedItems() throws Exception {
        mvc.perform(get("/api/items"))
                .andExpect(status().isUnauthorized());
    }

    @Test
    @WithMockUser(username = "viewer", roles = "USER")
    void authenticatedUserCanReadItems() throws Exception {
        mvc.perform(get("/api/items"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$[0].id").value("item-1"));
    }

    @Test
    void regularUserCannotReadAdminMetrics() throws Exception {
        mvc.perform(get("/api/admin/metrics")
                .with(user("viewer").roles("USER")))
                .andExpect(status().isForbidden());
    }

    @Test
    void adminUserCanReadAdminMetrics() throws Exception {
        mvc.perform(get("/api/admin/metrics")
                .with(user("admin").roles("ADMIN")))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.items").value(1));
    }

    @Test
    void authenticatedPostWithoutCsrfIsForbidden() throws Exception {
        mvc.perform(post("/api/items")
                .with(user("viewer").roles("USER"))
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"name\":\"draft\"}"))
                .andExpect(status().isForbidden());
    }

    @Test
    void validCsrfWithoutAuthenticationIsUnauthorized()
            throws Exception {
        mvc.perform(post("/api/items")
                .with(csrf())
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"name\":\"draft\"}"))
                .andExpect(status().isUnauthorized());
    }

    @Test
    void authenticatedPostWithCsrfIsCreated() throws Exception {
        mvc.perform(post("/api/items")
                .with(user("viewer").roles("USER"))
                .with(csrf())
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"name\":\"draft\"}"))
                .andExpect(status().isCreated())
                .andExpect(jsonPath("$.id").value("created-1"))
                .andExpect(jsonPath("$.name").value("draft"));
    }

    @Test
    void invalidCsrfIsForbiddenEvenWithUser() throws Exception {
        mvc.perform(post("/api/items")
                .with(user("viewer").roles("USER"))
                .with(csrf().useInvalidToken())
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"name\":\"draft\"}"))
                .andExpect(status().isForbidden());
    }
}
```

**Kỳ vọng:** 9 JUnit methods pass trên đúng Spring Boot 3.5/Spring Security 6.x test environment. Mỗi test có trách nhiệm riêng, không cố biến tất cả cases thành 200:

| Scenario | HTTP status |
|---|---:|
| Public GET không login | 200 và header nosniff |
| Anonymous protected GET | 401 |
| Mock ROLE_USER protected GET | 200 |
| ROLE_USER admin GET | 403 |
| ROLE_ADMIN admin GET | 200 |
| ROLE_USER POST thiếu CSRF | 403 |
| Anonymous POST có CSRF | 401 |
| ROLE_USER POST có valid CSRF | 201 |
| ROLE_USER POST có invalid CSRF | 403 |

Test `@WithMockUser` xác minh URL policy với một mock principal; **không** test real password validation. Request postprocessor `user(...)` yêu cầu Spring Security MockMvc integration đúng. Với Boot auto-configured MockMvc mặc định và dependencies thích hợp, context filters được sử dụng. Nếu dùng standalone/manual MockMvc, cần `springSecurity()` hoặc cấu hình chain tương ứng.

## 9. Test đối chứng: MockMvc bypass, real HTTP vẫn bảo vệ (7 trường hợp)

**File `src/test/java/com/example/securityfilters/BypassMockMvcAndRealHttpTest.java`:**

```java
package com.example.securityfilters;

import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.time.Duration;
import java.util.Base64;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.server.LocalServerPort;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

import static org.assertj.core.api.Assertions.assertThat;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest(
    classes = SecurityFiltersApplication.class,
    webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT
)
@AutoConfigureMockMvc(addFilters = false)
class BypassMockMvcAndRealHttpTest {

    @Autowired MockMvc mvc;
    @LocalServerPort int port;

    private static final HttpClient CLIENT =
            HttpClient.newHttpClient();

    private URI uri(String path) {
        return URI.create("http://127.0.0.1:" + port + path);
    }

    private HttpResponse<String> call(HttpRequest request)
            throws Exception {
        return CLIENT.send(
                request,
                HttpResponse.BodyHandlers.ofString(
                        StandardCharsets.UTF_8));
    }

    @Test
    void mockMvcAnonymousProtectedGetCanReturn200()
            throws Exception {
        mvc.perform(get("/api/items"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$[0].id").value("item-1"));
    }

    @Test
    void mockMvcAnonymousAdminGetCanReturn200()
            throws Exception {
        mvc.perform(get("/api/admin/metrics"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.items").value(1));
    }

    @Test
    void mockMvcAnonymousPostWithoutCsrfCanReturn201()
            throws Exception {
        mvc.perform(post("/api/items")
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"name\":\"draft\"}"))
                .andExpect(status().isCreated())
                .andExpect(jsonPath("$.name").value("draft"));
    }

    @Test
    void mockMvcLacksSecurityHeaderFromSkippedFilter()
            throws Exception {
        mvc.perform(get("/public/ping"))
                .andExpect(status().isOk())
                .andExpect(header().doesNotExist(
                        "X-Content-Type-Options"));
    }

    @Test
    void realHttpAnonymousGetIs401() throws Exception {
        HttpRequest request = HttpRequest.newBuilder(
                uri("/api/items"))
                .timeout(Duration.ofSeconds(5))
                .GET()
                .build();

        assertThat(call(request).statusCode()).isEqualTo(401);
    }

    @Test
    void realHttpAnonymousPostWithoutCsrfIs403()
            throws Exception {
        HttpRequest request = HttpRequest.newBuilder(
                uri("/api/items"))
                .timeout(Duration.ofSeconds(5))
                .header("Content-Type", "application/json")
                .POST(HttpRequest.BodyPublishers.ofString(
                        "{\"name\":\"draft\"}"))
                .build();

        assertThat(call(request).statusCode()).isEqualTo(403);
    }

    @Test
    void realHttpValidBasicAuthenticationCanRead()
            throws Exception {
        String credentials = Base64.getEncoder()
                .encodeToString(
                        "viewer:viewer-pass".getBytes(
                                StandardCharsets.UTF_8));

        HttpRequest request = HttpRequest.newBuilder(
                uri("/api/items"))
                .timeout(Duration.ofSeconds(5))
                .header("Authorization", "Basic " + credentials)
                .GET()
                .build();

        HttpResponse<String> response = call(request);

        assertThat(response.statusCode()).isEqualTo(200);
        assertThat(response.body()).contains("item-1");
    }
}
```

Đây là **7 @Test methods**. Java 17 `HttpClient.newHttpClient()` được sử dụng trực tiếp; không có try-with-resources cho HttpClient. HTTP request được gửi qua loopback 127.0.0.1 với cổng do Spring Boot chọn; không cần internet/IdP ngoài.

### 9.1. Ý nghĩa đối chứng

| Request | MockMvc filters=false | Server thật RANDOM_PORT |
|---|---:|---:|
| Anonymous GET /api/items | 200 | 401 |
| Anonymous GET /api/admin/metrics | 200 | 401 trong HTTP Basic demo |
| Anonymous POST /api/items thiếu CSRF | 201 | 403 |
| GET /public/ping | 200, không có nosniff từ filter | 200, security header theo configuration |
| GET /api/items với valid Basic | Không cần auth trong bypass path | 200 sau auth |

Một test class vừa khởi động HTTP server vừa inject MockMvc: hai đối tượng này **không có cùng filter path khi addFilters=false**. Flag thay MockMvc builder, không tắt Servlet filters của real server.

### 9.2. Đừng suy từ @WithMockUser ra real authentication

Default MockMvc test giữ filter và dùng fake Authentication để đánh giá URL authorization. Real HTTP test dùng HTTP Basic header thật, InMemoryUserDetailsManager và PasswordEncoder trong demo. Cách thứ hai kiểm tra nhiều hơn về Basic authentication, nhưng vẫn **không** chứng minh OAuth2/JWT/TLS, cookie/session login hoặc external identity provider production.

## 10. Chạy ví dụ và xác nhận kết quả

**Linux/macOS với Gradle Wrapper:**

```bash
./gradlew test --tests "com.example.securityfilters.FilterEnabledMockMvcTest"
./gradlew test --tests "com.example.securityfilters.BypassMockMvcAndRealHttpTest"
```

**Linux/macOS với Maven Wrapper:**

```bash
./mvnw -Dtest=FilterEnabledMockMvcTest test
./mvnw -Dtest=BypassMockMvcAndRealHttpTest test
```

**Windows PowerShell:**

```powershell
.\gradlew.bat test --tests "com.example.securityfilters.FilterEnabledMockMvcTest"
.\gradlew.bat test --tests "com.example.securityfilters.BypassMockMvcAndRealHttpTest"

# Or use Maven Wrapper when the project is Maven:
.\mvnw.cmd "-Dtest=FilterEnabledMockMvcTest" test
.\mvnw.cmd "-Dtest=BypassMockMvcAndRealHttpTest" test
```

Chọn **một** build tool có trong project, không chạy cả Gradle/Maven nếu project không hỗ trợ. Kiểm tra JUnit report có **16 methods được thực thi**, không skipped/disabled. Với RANDOM_PORT, CI phải cho phép mở loopback socket và ephemeral port. Không cần DB, credentials thật hoặc Docker.

**Kỳ vọng thiết kế:** cả 16 bài test pass trong đúng Spring Boot 3.5/Spring Security 6.x environment. Đây là mã được rà soát theo API; không tuyên bố runtime compilation/tests đã chạy trong phiên soạn Knowledge.

## 11. Khi nào tắt filters có thể chấp nhận?

Có thể dùng có chủ đích cho một **controller-only test** khi mục tiêu chính là:

- JSON serialization/deserialization hoặc HTTP DTO contract;
- request mapping, @RequestBody, response status;
- Bean Validation ở MVC layer;
- @ControllerAdvice exception body mapping;
- controller→mocked business service interactions.

Nhưng phải đáp ứng:

1. Security **không phải acceptance criterion** của test đó.
2. Tên class/test ghi đúng MVC/controller-only scope.
3. Không có Servlet filter mà controller phụ thuộc cho business result.
4. Có security-enabled suite **khác** bảo vệ các URLs quan trọng.
5. Không đặt addFilters=false ở một test base class làm tất cả web tests vô tình bỏ filters.
6. Không thay production SecurityFilterChain chỉ để test pass.
7. Có negative tests cho anonymous/USER/ADMIN/CSRF.
8. CI chạy tất cả các nhóm test, không coi skipped security suite là PASS.

Nếu đang test business logic thuần, nên test service trực tiếp mà không có MockMvc. Nếu cần HTTP security contract, giữ filters và tạo user/CSRF fixture hợp lệ.

## 12. @WebMvcTest, MockMvc tự dựng và custom SecurityFilterChain

`@WebMvcTest(MyController.class)` chỉ tải MVC slice. Spring Security có thể được auto-configure trong slice, nhưng custom `@Configuration` của app không chắc được scan như full context. Vì vậy khi test security policy:

- Dùng `@Import(MySecurityConfiguration.class)` khi slice cần nạp đúng config.
- Dùng `@MockitoBean` (Spring Framework 6.2 / Boot 3.4+) cho business collaborators không thuộc MVC slice.
- Đừng dùng default security từ slice rồi kết luận production custom matchers đúng.
- Nếu khó đảm bảo policy parity, dùng `@SpringBootTest + @AutoConfigureMockMvc` với filters enabled.

`MockMvcBuilders.standaloneSetup(controller)` thích hợp cho controller-only test nhưng không tự có Spring Security filter chain. Khi cần tự dựng MockMvc từ WebApplicationContext:

```java
MockMvc mvc = MockMvcBuilders
        .webAppContextSetup(webApplicationContext)
        .apply(springSecurity())
        .build();
```

Đây là snippet, cần WebApplicationContext/imports và `spring-security-test`. Khi dùng Boot auto-configured MockMvc đúng cách, thường không cần xây lại builder thủ công.

## 13. @WithMockUser và user() không vô hiệu hóa authorization

- `@WithMockUser(username="alice", roles="USER")` tạo authenticated principal giả. URL access rules vẫn có thể chạy.
- `user("alice").roles("USER")` áp dụng identity cho từng MockMvc request.
- `roles="ADMIN"` tạo `ROLE_ADMIN`, khác `authorities="ADMIN"` nếu không có custom prefix.
- `@WithUserDetails` hữu ích nếu app dùng custom UserDetailsService/principal.
- `@WithSecurityContext` cho custom authentication objects.
- `jwt()` postprocessor cho OAuth2 resource-server authorization scenarios có thể giả JWT authentication nhưng **không chứng minh JWT signature được real decoder verify**.

Với production OAuth/JWT, cần real decoder/token/issuer/audience test khi chính các yếu tố ấy là mục tiêu. Với browser cookie/session auth, cần tests về session, login/logout, CSRF và cookie flags theo contract.

## 14. Những lớp bảo vệ khác cần test riêng

### 14.1. Method security

Nếu method-security advisors đã bật qua `@EnableMethodSecurity`, `@PreAuthorize` có thể vẫn từ chối service call dù MockMvc filters đã bị bỏ. Điều này **không** thay cho URL authorization test. Method security còn phụ thuộc proxy/self-invocation và correct authentication context.

### 14.2. CORS

CORS có thể được quản lý ở SecurityFilterChain, Servlet CORS filter hoặc Spring MVC handler mappings. addFilters=false có thể bỏ CORS tại filter layer trong khi MVC CORS handling vẫn còn. Test CORS bằng preflight `OPTIONS`, Origin, Access-Control-Request-Method và expected Access-Control-Allow-* headers theo actual configuration; không suy từ GET 200.

### 14.3. Tenant/audit/tracing filters

Bỏ tenant filter có thể dẫn đến default tenant/null tenant, làm test nhìn dữ liệu sai hoặc bỏ qua isolation. Bỏ audit/correlation filter có thể gây missing request IDs, MDC, security principal trong logs. Với hệ thống multi-tenant cần cả tests về tenant mismatch bị chặn và readback records đúng owner ở DB layer.

### 14.4. Security response headers

Một filter-enabled MockMvc test nên assert những headers mà application yêu cầu, chẳng hạn `X-Content-Type-Options: nosniff`. Không mặc định assert HSTS trên HTTP, và không giả định CSP luôn có. Với TLS/mTLS/HTTPS, cần test ở layer có transport/security thực.

## 15. Chẩn đoán 401/403 thay vì bypass

Trình tự:

1. Xác nhận method/path/content type/body.
2. Phân biệt 401 authentication, 302 login redirect và 403 authorization/CSRF.
3. Với POST/PUT/PATCH/DELETE, kiểm tra token CSRF khi policy yêu cầu.
4. Kiểm tra `@WithMockUser`/`user(...)` có đúng roles/authorities không.
5. Kiểm tra principal có thật sự được Spring Security MockMvc integration nhận.
6. Xem SecurityFilterChain nào match URL và thứ tự nhiều chains.
7. Trong @WebMvcTest, custom security configuration có được nạp không.
8. Kiểm tra custom authentication converter, JWT claims, OAuth scopes hoặc role hierarchy nếu có.
9. Kiểm tra method security/proxy, custom filters, tenant resolver.
10. Đọc root cause, resolved exception, headers trong logs đã redact.
11. Sửa fixture khi test input thiếu; sửa production policy **chỉ khi policy thật sai**.
12. Bổ sung negative regression test và chạy cả security suite.

Có thể dùng `andDo(print())` khi debug, nhưng không in password, token, PII hoặc Authorization headers thật vào CI artifacts.

### 15.1. Test trả 403 có thể là điều đúng

Nếu role USER bị từ chối ở admin endpoint, 403 là expected. Bỏ filter để ép 200 là thay **đề bài kiểm thử**. Đặt tên test là `userCannotReadAdmin()`, assert 403 và có thêm `adminCanReadAdmin()` assert 200.

## 16. Anti-pattern thường gặp

| Mẫu sai | Vấn đề | Cách tốt hơn |
|---|---|---|
| addFilters=false trên mọi test | Mất security/custom filters coverage | Opt-out hẹp, default filter-enabled |
| Chỉ dùng admin test user | Không kiểm tra least privilege | Anonymous/USER/ADMIN matrix |
| Tắt CSRF production vì POST test 403 | Thay threat model để né test | `csrf()` hoặc reviewed policy |
| @WebMvcTest thiếu custom security config | Slice test không giống production | @Import hoặc full-context test |
| Mọi positive endpoint đều 200 | Không chứng minh denied paths | 401/403/invalid CSRF tests |
| Mock JWT rồi tuyên bố signature validated | Decoder/auth pipeline bị giả | Real token/decoder integration |
| Tắt tenant filter để controller JSON pass | Không kiểm tra tenant isolation | Filter-enabled tenant tests |
| Sử dụng standalone MockMvc và gọi security E2E | Không có filter chain thực | springSecurity() hoặc Boot MockMvc |
| Chỉ test MockMvc mà gọi là socket test | Không đi qua servlet container thật | RANDOM_PORT + real HttpClient |
| Bỏ qua security headers | Miss defense-in-depth | Header assertions |
| Sửa test bằng anyRequest().permitAll() | Không kiểm tra production rules | Keep actual SecurityFilterChain |
| Bỏ security tests khỏi CI | Đánh mất regression guard | Run enabled suite and track skips |

## 17. Bài tập thực hành kèm lời giải

**A — POST 403 dù có @WithMockUser:** Kiểm tra CSRF. Nếu CSRF policy bật, thêm `csrf()` và test negative missing/invalid token; không tắt filters.

**B — USER vào admin bị 403:** Hành vi đúng nếu URL cần ROLE_ADMIN. Test nên assert 403 cho USER và 200 cho ADMIN, thay vì bypass.

**C — MockMvc GET 200 nhưng real HTTP 401:** addFilters=false chỉ đổi MockMvc; server vẫn chạy SecurityFilterChain.

**D — @WithMockUser có verify password không?** Không. Nó giả authentication object; dùng real HTTP Basic/JWT verification test khi cần.

**E — addFilters=false nhưng @PreAuthorize vẫn deny?** Có thể, bởi method-security AOP hoạt động ở boundary khác nếu được bật.

**F — CORS test pass khi filter off có đủ không?** Không. CORS có thể được thực thi tại Servlet filter/Spring Security/MVC layer; cần preflight/header tests theo policy thật.

**G — Chỉ test GET 200 của admin có đủ không?** Không. Cấu hình permitAll sai cũng có thể trả 200; negative tests là bắt buộc.

**H — Khi nào addFilters=false được phép?** Khi chỉ kiểm thử MVC/DTO/validation có mục đích rõ, custom filters không cần cho behavior ấy, và còn một security-enabled suite đầy đủ.

**I — Bật CSRF cho mọi API có bắt buộc?** Phụ thuộc browser credentials, session/cookie và threat model; không suy từ tên REST API hoặc lỗi test.

**J — JWT mock test pass chứng minh token signature?** Không. Cần test real JwtDecoder và valid/invalid token signatures cho authentication stack.

## 18. Checklist QA

- [ ] Đã ghi rõ test kiểm tra business logic, MVC contract hay security contract.
- [ ] Không dùng addFilters=false để giấu lỗi 401/403 chưa phân loại.
- [ ] Security-enabled tests giữ default addFilters=true.
- [ ] Anonymous protected request có negative test.
- [ ] USER không vào admin; ADMIN vào đúng.
- [ ] Unsafe requests có valid, missing và invalid CSRF tests khi cần.
- [ ] Phân biệt fake user và real authentication/JWT validation.
- [ ] Security response headers được kiểm tra ở filter-enabled path.
- [ ] @WebMvcTest nạp security config đúng khi kiểm tra policy.
- [ ] Các custom filters tenant/CORS/audit có tests riêng.
- [ ] Method security được hiểu là một layer độc lập.
- [ ] Không sửa production CSRF/auth config chỉ để test xanh.
- [ ] Không dùng real credentials/secrets/PII trong test.
- [ ] Có real HTTP smoke tests khi cần Servlet container behavior.
- [ ] HTTP statuses phản ánh đúng scheme Basic/form/Bearer thay vì đoán.
- [ ] Test classes có thể chạy độc lập, không phụ thuộc thứ tự.
- [ ] CI báo đúng tests executed/failed/skipped.
- [ ] Java 17, Spring Boot 3.5, security-test imports tương thích.
- [ ] Bypass nếu có được ghi rõ chỉ kiểm tra controller-only.
- [ ] Không xem status 2xx trong bypass mode là bằng chứng secure.

## 19. Kết luận

**Khi tắt filters để bài test thành công, bạn thường đã thay đổi câu hỏi của test.** Thay vì hỏi “request này có được bảo vệ đúng không?”, bạn đang hỏi “controller làm gì khi bỏ qua Servlet filters?”. Hai kết quả không thể thay thế nhau.

Với Spring Boot 3.5/Spring Security 6:

- `@AutoConfigureMockMvc(addFilters=false)` bỏ context filters khỏi **MockMvc**, không tự tắt security của HTTP server thật.
- Nó có thể che lỗi authentication, authorization, CSRF và các custom filters.
- `@WithMockUser`, `user(...)`, `csrf()` cho phép tạo request hợp lệ **mà vẫn giữ security policy**.
- Method security, MVC validation và database policies có boundaries khác.
- Bypass chỉ có thể dùng có chủ đích trong controller-only tests và phải có security integration suite bù coverage.
- Security tests phải kiểm tra cả **được phép** và **bị từ chối**.

Bộ ví dụ dùng chung production controller/security config với 16 JUnit methods, minh họa rõ MockMvc bypass có thể cho 200/201 trong khi server thật trả 401/403. Đây là ranh giới cần nắm trước khi sửa một test failing bằng cách xóa filters.

## Tài liệu tham khảo chính thức

- [Spring Boot 3.5 — AutoConfigureMockMvc API](https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/test/autoconfigure/web/servlet/AutoConfigureMockMvc.html): addFilters default true.
- [Spring Boot 3.5 — Testing Spring Boot Applications](https://docs.spring.io/spring-boot/3.5/reference/testing/spring-boot-applications.html): MockMvc, WebMvcTest, SpringBootTest, RANDOM_PORT.
- [Spring Boot 3.5 — Testing How-to](https://docs.spring.io/spring-boot/3.5/how-to/testing.html): importing security config in MVC slices.
- [Spring Security — Setting Up MockMvc and Spring Security](https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/setup.html): FilterChainProxy and springSecurity() configurer.
- [Spring Security — Running a Test as a User](https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/authentication.html): @WithMockUser and user(...).
- [Spring Security — Testing CSRF](https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/csrf.html): csrf(), asHeader(), invalid tokens.
- [Spring Security — CSRF threat model](https://docs.spring.io/spring-security/reference/servlet/exploits/csrf.html): csrf for browser/unsafe methods.
- [Spring Security — HTTP Authorization](https://docs.spring.io/spring-security/reference/servlet/authorization/authorize-http-requests.html): matchers/roles.
- [Spring Security — Method Security](https://docs.spring.io/spring-security/reference/servlet/authorization/method-security.html): @EnableMethodSecurity and @PreAuthorize.
- [Spring Security — Response Headers](https://docs.spring.io/spring-security/reference/servlet/exploits/headers.html): nosniff, frame, HSTS.
