# spring-security-test và tích hợp filter chain thật trong kiểm thử Spring Boot

## 1. Vấn đề: test “200 OK” chưa chứng minh ứng dụng an toàn

Một ứng dụng Spring Boot sử dụng Spring Security có thể có controller trả dữ liệu đúng, nhưng một bài kiểm thử lại vô tình **bỏ qua lớp bảo mật** khi gọi controller. Ví dụ, `MockMvcBuilders.standaloneSetup(new CatalogController(...))` chỉ dựng MVC handler nếu không thêm security filters. Khi đó:

- Endpoint đáng ra yêu cầu đăng nhập vẫn trả 200 cho request không có credential.
- Một tài khoản không có quyền EDITOR vẫn gọi được API tạo bản ghi.
- Request POST không có CSRF token vẫn thành công dù ứng dụng cấu hình CSRF.
- `@WithMockUser` tạo sẵn người dùng, làm test không phát hiện login/password/JWT decoder bị cấu hình sai.
- Test chỉ kiểm tra controller, không kiểm tra `SecurityFilterChain`, `FilterChainProxy`, HTTP Basic/Bearer filters hoặc `@PreAuthorize`.

**Chủ đề của bài** là dùng thư viện **`spring-security-test`** để xây test đúng lớp, đặc biệt **tích hợp filter chain thật của ứng dụng vào MockMvc**. Ta sẽ phân biệt:

1. **Authentication**: ai đang gọi? Credential đã được kiểm tra thật chưa?
2. **Authorization**: người đó có role/authority phù hợp không?
3. **CSRF và headers**: request thay đổi trạng thái có hợp lệ, security headers được gắn đúng không?
4. **Filter-chain integration**: request có đi qua `springSecurityFilterChain` hay chỉ gọi trực tiếp controller?
5. **Method security**: `@PreAuthorize` trên service có được thực thi qua Spring AOP proxy không?
6. **Phạm vi test**: `@WebMvcTest`, `@SpringBootTest + @AutoConfigureMockMvc` và HTTP server thật khác nhau như thế nào?

Bài sử dụng **Java 17+, Spring Boot 3.5.x, Spring Security 6.x, JUnit Jupiter và MockMvc**. Code mẫu hoàn chỉnh có HTTP Basic và users lưu trong bộ nhớ **chỉ cho demo/test**; production cần credential store, password policy và cơ chế authentication phù hợp.

## 2. Spring Security filter chain xử lý request như thế nào?

Trong ứng dụng Servlet, Spring Security thường tích hợp với servlet container qua `DelegatingFilterProxy` và `FilterChainProxy` (bean `springSecurityFilterChain`). `FilterChainProxy` chọn một `SecurityFilterChain` phù hợp request, rồi chạy các filters theo thứ tự được cấu hình.

```text
HTTP request hoặc MockHttpServletRequest
             |
             v
      Servlet filter infrastructure
             |
     springSecurityFilterChain
       (FilterChainProxy)
             |
      Chọn SecurityFilterChain
      theo securityMatcher/ordering
             |
   +---------+-----------+------------------+
   |                     |                  |
SecurityContext      Authentication      Authorization
CSRF                 HTTP Basic/Bearer   AuthorizationFilter
exception handling   credentials check    deny/allow
   |                     |                  |
   +---------------------+------------------+
             |
             v
  DispatcherServlet -> Controller -> Service
                                         |
                                  @PreAuthorize proxy
             |
             v
         HTTP response
```

Đây là sơ đồ khái niệm, không phải danh sách filters có thứ tự cố định cho mọi cấu hình. Bộ lọc thực thay đổi theo `httpBasic`, `formLogin`, `oauth2ResourceServer`, CSRF, session management, CORS và các `SecurityFilterChain` khác nhau.

**Điểm then chốt:** `@WithMockUser` và `user()` có thể dựng sẵn một `Authentication` cho test, nhưng **filter chain vẫn cần hiện diện** để kiểm tra authorization, CSRF và exception handling. Ngược lại, nếu muốn kiểm tra username/password thực sự được xác thực, phải gửi **HTTP Basic header** qua `BasicAuthenticationFilter` thay vì chỉ tạo sẵn principal.

### 2.1. Không nhầm “security filter chạy” với “server HTTP thật”

`@SpringBootTest(webEnvironment=MOCK) + @AutoConfigureMockMvc(addFilters=true)` khởi tạo Spring context và register filters của ứng dụng vào MockMvc, nhưng **không mở socket HTTP**. Request được MockMvc gửi vào Servlet API mô phỏng. Nó vẫn kiểm tra `FilterChainProxy`, authentication/authorization/CSRF theo cấu hình thật của context.

`@SpringBootTest(webEnvironment=RANDOM_PORT)` với `TestRestTemplate` hoặc HTTP client thật mở **embedded HTTP server** và tạo request qua network stack. Chọn loại này khi cần kiểm chứng container/network, cookies, redirect, TLS integration, proxy headers hoặc behavior của server runtime. Dù là HTTP thật, test vẫn phải dùng **test identities và database cô lập**.

## 3. Dependency bắt buộc: spring-security-test

Trong một Spring Boot 3.5.x MVC project:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}
```

Các dòng trên là **mảnh build.gradle**. Khi dùng Spring Boot BOM, không khai báo một Spring Security version riêng nếu không có lý do rõ ràng: trộn Spring Security 6.x test với Spring Security 7.x runtime có thể gây `NoSuchMethodError` hoặc behavior khác nhau.

Thư viện `spring-security-test` cung cấp:
- `@WithMockUser`, `@WithAnonymousUser`, `@WithUserDetails`, `@WithSecurityContext`.
- `SecurityMockMvcRequestPostProcessors.user()`, `httpBasic()`, `csrf()`, `anonymous()`, `jwt()`, `authentication()`.
- `SecurityMockMvcResultMatchers.authenticated()`, `unauthenticated()`.
- `SecurityMockMvcConfigurers.springSecurity()` để tích hợp vào MockMvc được build thủ công.
- Test listeners đưa `SecurityContext` giả vào đúng thời điểm của test rồi dọn state sau test.

**Không tự suy ra filter chain đã chạy chỉ vì test compile được với @WithMockUser.** Dependency chỉ cung cấp utilities; filter chain phải được đưa vào cấu hình MockMvc đúng cách.

## 4. Mức kiểm thử nào kiểm tra được điều gì?

| Thiết lập | Controller thật? | Security filters thật? | Xác thực credential qua filter? | HTTP socket thật? |
|---|---|---|---|---|
| Mockito mock service/controller | Không hoặc chỉ mock | Không | Không | Không |
| `MockMvcBuilders.standaloneSetup(controller)` mặc định | Controller thật | **Không**, trừ khi gắn rõ filters | Không nếu thiếu filters | Không |
| `MockMvcBuilders.webAppContextSetup(ctx).apply(springSecurity())` | Có | **Có** | Có, nếu gửi header/credential thật | Không |
| `@WebMvcTest + MockMvc` | Controller slice | Có khi security được auto-configured/đúng import | Có nếu config + filter + auth provider được đưa vào slice | Không |
| `@SpringBootTest + @AutoConfigureMockMvc(addFilters=true)` | Có, full context | **Có** | Có khi dùng `httpBasic()`/bearer header | Không |
| `@SpringBootTest(RANDOM_PORT)` + HTTP client | Có, full context | **Có** | Có với HTTP header/token thật | **Có** |

**Quan trọng với `@WebMvcTest`:** Spring Boot 3.5 có thể auto-configure security test infrastructure, nhưng một custom `SecurityFilterChain` hoặc `@Service` của dự án có thể bị giới hạn bởi slice scanning. Cần `@Import` những beans thiết yếu, hoặc dùng full context nếu mục tiêu là kiểm tra cấu hình production đầy đủ.

**Quan trọng với `@AutoConfigureMockMvc`:** tham số `addFilters` mặc định là **true**. Nếu đổi thành `addFilters=false`, các servlet filters trong application context không được register vào MockMvc; các assertions authorization/CSRF có thể không còn bảo vệ cùng đường đi như ứng dụng thật.

## 5. Hợp đồng bảo mật của mini application

Ta thiết kế API để test tách bạch authentication, authorization và CSRF:

| HTTP endpoint | Chính sách |
|---|---|
| `GET /api/public` | Cho phép anonymous |
| `GET /api/items/{id}` | Cần một trong `ROLE_USER`, `ROLE_EDITOR`, `ROLE_ADMIN` |
| `POST /api/items` | Cần `ROLE_EDITOR` **và** CSRF token hợp lệ |
| `DELETE /api/items/{id}` | Cần `ROLE_ADMIN` **và** CSRF token hợp lệ |
| `GET /api/audit` | HTTP layer yêu cầu authenticated; service còn kiểm tra `@PreAuthorize("hasRole('AUDITOR')")` |
| Đường dẫn khác | Deny all |

Tài khoản test (chỉ ví dụ):
- `viewer / viewer-pass` có `ROLE_USER`.
- `editor / editor-pass` có `ROLE_EDITOR`.
- `admin / admin-pass` có `ROLE_ADMIN`.
- `auditor / auditor-pass` có `ROLE_AUDITOR`.

Password trong ví dụ được **encode bằng DelegatingPasswordEncoder** trước khi đưa vào `InMemoryUserDetailsManager`. Dự án production không nên hard-code những user/password này trong application class; demo không có kết nối user store thật.

Chính sách cho phép `httpBasic()` để test request authentication thực. Nó bật CSRF mặc định trong ứng dụng web và ta giữ CSRF rõ ràng; **HTTP Basic không tự loại bỏ rủi ro CSRF** trong các bối cảnh trình duyệt có thể tự đính kèm Basic credentials.

## 6. Dự án Spring Boot 3.5.8 / Java 17 đầy đủ

Cấu trúc:

```text
build.gradle
src/main/java/com/example/securitylab/
    SecurityLabApplication.java
    SecurityConfig.java
    AuditService.java
    CatalogController.java
src/test/java/com/example/securitylab/
    SecurityChainIntegrationTest.java
    SecurityMvcSliceTest.java
    SecurityLiveHttpTest.java
```

### 6.1. build.gradle

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.5.8'
    id 'io.spring.dependency-management' version '1.1.7'
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
    testRuntimeOnly 'org.junit.platform:junit-platform-launcher'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

Spring Boot BOM quản lý các phiên bản Spring/Security/JUnit tương thích. `spring-security-test` chỉ nằm ở test scope. `@SpringBootTest` và JUnit Jupiter được tích hợp qua starter-test, không cần tự viết `@ExtendWith(SpringExtension.class)` cho mỗi test Boot đã được annotate phù hợp.

Để chạy bằng `./gradlew` cần có Gradle wrapper trong project; file build ở trên **không tự sinh wrapper**.

### 6.2. Application class

Tệp `src/main/java/com/example/securitylab/SecurityLabApplication.java`:

```java
package com.example.securitylab;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class SecurityLabApplication {

    public static void main(String[] args) {
        SpringApplication.run(SecurityLabApplication.class, args);
    }
}
```

### 6.3. Cấu hình SecurityFilterChain và test identities

Tệp `src/main/java/com/example/securitylab/SecurityConfig.java`:

```java
package com.example.securitylab;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.factory.PasswordEncoderFactories;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;

@Configuration(proxyBeanMethods = false)
@EnableMethodSecurity
public class SecurityConfig {

    @Bean
    SecurityFilterChain apiSecurity(HttpSecurity http) throws Exception {
        http
            .authorizeHttpRequests(authorize -> authorize
                .requestMatchers(HttpMethod.GET, "/api/public")
                    .permitAll()
                .requestMatchers(HttpMethod.GET, "/api/items/*")
                    .hasAnyRole("USER", "EDITOR", "ADMIN")
                .requestMatchers(HttpMethod.POST, "/api/items")
                    .hasRole("EDITOR")
                .requestMatchers(HttpMethod.DELETE, "/api/items/*")
                    .hasRole("ADMIN")
                .requestMatchers(HttpMethod.GET, "/api/audit")
                    .authenticated()
                .anyRequest().denyAll())
            .httpBasic(Customizer.withDefaults())
            .csrf(Customizer.withDefaults());

        return http.build();
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return PasswordEncoderFactories
                .createDelegatingPasswordEncoder();
    }

    @Bean
    UserDetailsService userDetailsService(PasswordEncoder encoder) {
        return new InMemoryUserDetailsManager(
            User.withUsername("viewer")
                .password(encoder.encode("viewer-pass"))
                .roles("USER")
                .build(),
            User.withUsername("editor")
                .password(encoder.encode("editor-pass"))
                .roles("EDITOR")
                .build(),
            User.withUsername("admin")
                .password(encoder.encode("admin-pass"))
                .roles("ADMIN")
                .build(),
            User.withUsername("auditor")
                .password(encoder.encode("auditor-pass"))
                .roles("AUDITOR")
                .build()
        );
    }
}
```

**Giải thích:**
- `SecurityFilterChain` bean là cấu hình được `FilterChainProxy` sử dụng, không phải một Java mock.
- `authorizeHttpRequests` áp dụng rules theo HTTP method và path; `anyRequest().denyAll()` bảo vệ các đường dẫn chưa được khai báo.
- `hasRole("EDITOR")` mặc định tìm authority `ROLE_EDITOR`; không truyền `ROLE_EDITOR` vào `hasRole` khi sử dụng prefix mặc định.
- `httpBasic` cài bộ lọc đọc header `Authorization: Basic ...` và xác thực qua `UserDetailsService`/`PasswordEncoder`.
- `csrf` được giữ bật để test các state-changing requests. Trong ứng dụng production chỉ nên disable CSRF khi threat model xác nhận phù hợp, ví dụ một API bearer-only stateless không nhận ambient browser credentials.
- `@EnableMethodSecurity` kích hoạt method security proxies để `@PreAuthorize` trên service có hiệu lực; HTTP URL rules **không thay thế** method security.

Ví dụ này chạy độc lập nhưng chứa **user credentials demo** trong source code nhằm mục đích đào tạo. Khi triển khai hệ thống thật, chuyển credentials sang identity provider/store an toàn, secrets manager và chính sách password/token phù hợp.

### 6.4. Service dùng @PreAuthorize

Tệp `src/main/java/com/example/securitylab/AuditService.java`:

```java
package com.example.securitylab;

import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.stereotype.Service;

@Service
public class AuditService {

    @PreAuthorize("hasRole('AUDITOR')")
    public String readAudit() {
        return "audit-report";
    }
}
```

Method này chỉ được phép khi `Authentication` có `ROLE_AUDITOR`. `@PreAuthorize` được thực thi qua **Spring proxy**; nếu code tự gọi `new AuditService().readAudit()` ngoài Spring, annotation không được AOP xử lý.

### 6.5. REST controller với endpoint cho từng rule

Tệp `src/main/java/com/example/securitylab/CatalogController.java`:

```java
package com.example.securitylab;

import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.security.core.Authentication;
import org.springframework.web.bind.annotation.DeleteMapping;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class CatalogController {

    private final AuditService auditService;

    public CatalogController(AuditService auditService) {
        this.auditService = auditService;
    }

    @GetMapping("/api/public")
    public String publicMessage() {
        return "public";
    }

    @GetMapping("/api/items/{id}")
    public ItemView readItem(
            @PathVariable long id,
            Authentication authentication) {
        return new ItemView(
                id, "Notebook", authentication.getName());
    }

    @PostMapping("/api/items")
    public ResponseEntity<ItemView> create(
            @RequestBody CreateItem request,
            Authentication authentication) {

        ItemView saved = new ItemView(
                101L, request.name(), authentication.getName());

        return ResponseEntity
                .status(HttpStatus.CREATED)
                .body(saved);
    }

    @DeleteMapping("/api/items/{id}")
    public ResponseEntity<Void> delete(@PathVariable long id) {
        return ResponseEntity.noContent().build();
    }

    @GetMapping("/api/audit")
    public String audit() {
        return auditService.readAudit();
    }

    public record CreateItem(String name) {
    }

    public record ItemView(
            long id, String name, String actor) {
    }
}
```

Controller không có database: nó trả dữ liệu xác định để test chỉ tập trung **security controls**. Trong ứng dụng thật, authorization còn có thể phụ thuộc owner/tenant hoặc dữ liệu từng record; cần service/domain security tests tương ứng.

Endpoint `GET /api/items/{id}` nhận `Authentication` từ Spring Security argument resolver. Khi một request bị chặn, MVC handler không được chạy và không có `actor` để trả.

## 7. Kiểm thử toàn bộ security filter chain bằng MockMvc

Tệp `src/test/java/com/example/securitylab/SecurityChainIntegrationTest.java`:

```java
package com.example.securitylab;

import org.junit.jupiter.api.Test;

import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.test.context.support.WithAnonymousUser;
import org.springframework.security.test.context.support.WithMockUser;
import org.springframework.security.test.context.support.WithUserDetails;
import org.springframework.security.web.FilterChainProxy;
import org.springframework.test.web.servlet.MockMvc;

import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.springframework.security.test.web.servlet.request
        .SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.security.test.web.servlet.request
        .SecurityMockMvcRequestPostProcessors.httpBasic;
import static org.springframework.security.test.web.servlet.request
        .SecurityMockMvcRequestPostProcessors.user;
import static org.springframework.security.test.web.servlet.response
        .SecurityMockMvcResultMatchers.authenticated;
import static org.springframework.test.web.servlet.request
        .MockMvcRequestBuilders.delete;
import static org.springframework.test.web.servlet.request
        .MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request
        .MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result
        .MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result
        .MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result
        .MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result
        .MockMvcResultMatchers.status;

@SpringBootTest(
    webEnvironment = SpringBootTest.WebEnvironment.MOCK)
@AutoConfigureMockMvc(addFilters = true)
class SecurityChainIntegrationTest {

    @Autowired
    MockMvc mvc;

    @Autowired
    FilterChainProxy securityFilterChain;

    @Test
    void securityFilterChainBeanIsPresent() {
        assertFalse(
            securityFilterChain.getFilterChains().isEmpty());
    }

    @Test
    void publicResourceAllowsAnonymousRequests() throws Exception {
        mvc.perform(get("/api/public"))
            .andExpect(status().isOk())
            .andExpect(content().string("public"));
    }

    @Test
    void protectedGetWithoutCredentialsReturns401()
            throws Exception {
        mvc.perform(get("/api/items/7"))
            .andExpect(status().isUnauthorized())
            .andExpect(header().exists("WWW-Authenticate"));
    }

    @Test
    void incorrectBasicPasswordReturns401() throws Exception {
        mvc.perform(get("/api/items/7")
                .with(httpBasic("viewer", "wrong-password")))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void realBasicAuthenticationForViewerSucceeds()
            throws Exception {
        mvc.perform(get("/api/items/7")
                .with(httpBasic("viewer", "viewer-pass")))
            .andExpect(status().isOk())
            .andExpect(authenticated().withUsername("viewer"))
            .andExpect(jsonPath("$.id").value(7))
            .andExpect(jsonPath("$.actor").value("viewer"));
    }

    @Test
    @WithMockUser(username = "alice", roles = "USER")
    void withMockUserExercisesAuthorizationWithoutPassword()
            throws Exception {
        mvc.perform(get("/api/items/9"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.actor").value("alice"));
    }

    @Test
    @WithUserDetails("viewer")
    void withUserDetailsLoadsPrincipalWithoutBasicLogin()
            throws Exception {
        mvc.perform(get("/api/items/10"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.actor").value("viewer"));
    }

    @Test
    void perRequestUserPostProcessorSetsUserForThisRequest()
            throws Exception {
        mvc.perform(get("/api/items/11")
                .with(user("synthetic-viewer").roles("USER")))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.actor")
                .value("synthetic-viewer"));
    }

    @Test
    void viewerCannotCreateEvenWithValidCsrf() throws Exception {
        mvc.perform(post("/api/items")
                .with(httpBasic("viewer", "viewer-pass"))
                .with(csrf())
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"name\":\"Notebook\"}"))
            .andExpect(status().isForbidden());
    }

    @Test
    void editorWithoutCsrfIsForbidden() throws Exception {
        mvc.perform(post("/api/items")
                .with(httpBasic("editor", "editor-pass"))
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"name\":\"Notebook\"}"))
            .andExpect(status().isForbidden());
    }

    @Test
    void editorWithInvalidCsrfIsForbidden() throws Exception {
        mvc.perform(post("/api/items")
                .with(httpBasic("editor", "editor-pass"))
                .with(csrf().useInvalidToken())
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"name\":\"Notebook\"}"))
            .andExpect(status().isForbidden());
    }

    @Test
    void editorWithValidCsrfCanCreate() throws Exception {
        mvc.perform(post("/api/items")
                .with(httpBasic("editor", "editor-pass"))
                .with(csrf().asHeader())
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"name\":\"Notebook\"}"))
            .andExpect(status().isCreated())
            .andExpect(jsonPath("$.id").value(101))
            .andExpect(jsonPath("$.name").value("Notebook"))
            .andExpect(jsonPath("$.actor").value("editor"));
    }

    @Test
    void adminDeleteWithoutCsrfIsForbidden() throws Exception {
        mvc.perform(delete("/api/items/13")
                .with(httpBasic("admin", "admin-pass")))
            .andExpect(status().isForbidden());
    }

    @Test
    void adminDeleteWithCsrfReturns204() throws Exception {
        mvc.perform(delete("/api/items/13")
                .with(httpBasic("admin", "admin-pass"))
                .with(csrf()))
            .andExpect(status().isNoContent());
    }

    @Test
    void viewerCannotDeleteEvenWithValidCsrf() throws Exception {
        mvc.perform(delete("/api/items/13")
                .with(httpBasic("viewer", "viewer-pass"))
                .with(csrf()))
            .andExpect(status().isForbidden());
    }

    @Test
    void authorityWithoutRolePrefixDoesNotSatisfyHasRole()
            throws Exception {
        mvc.perform(post("/api/items")
                .with(user("synthetic")
                    .authorities(
                        new SimpleGrantedAuthority("EDITOR")))
                .with(csrf())
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"name\":\"Notebook\"}"))
            .andExpect(status().isForbidden());
    }

    @Test
    void methodSecurityRejectsViewerAfterHttpAuthentication()
            throws Exception {
        mvc.perform(get("/api/audit")
                .with(httpBasic("viewer", "viewer-pass")))
            .andExpect(status().isForbidden());
    }

    @Test
    void auditorPassesMethodSecurity() throws Exception {
        mvc.perform(get("/api/audit")
                .with(httpBasic("auditor", "auditor-pass")))
            .andExpect(status().isOk())
            .andExpect(content().string("audit-report"));
    }

    @Test
    @WithAnonymousUser
    void anonymousAnnotationStillRequiresAuthentication()
            throws Exception {
        mvc.perform(get("/api/items/12"))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void authenticatedUnknownPathIsDenied() throws Exception {
        mvc.perform(get("/api/unknown")
                .with(httpBasic("viewer", "viewer-pass")))
            .andExpect(status().isForbidden());
    }

    @Test
    void securityDefaultAddsNosniffHeader() throws Exception {
        mvc.perform(get("/api/public"))
            .andExpect(status().isOk())
            .andExpect(
                header().string(
                    "X-Content-Type-Options", "nosniff"));
    }
}
```

### 7.1. Những bảo đảm của lớp test

Bộ test trên kiểm tra ba điều kiện tách biệt:

**A. Filter chain có tồn tại và chạy không?** Test `securityFilterChainBeanIsPresent` kiểm tra `FilterChainProxy` có các chains, nhưng **chưa đủ một mình**. Các test anonymous 401, thiếu CSRF 403 và deny-all 403 mới chứng minh request **thực sự chịu tác động** của security filters theo configuration.

**B. Authentication thật qua HTTP Basic?** `httpBasic("viewer", "viewer-pass")` tạo `Authorization: Basic ...`, rồi `BasicAuthenticationFilter`/authentication provider so khớp tài khoản và mật khẩu đã encode. Test sai password phải 401 và đúng password mới qua 200. Đó là integration của **filter + credential lookup** (nhưng chưa kiểm tra IdP/LDAP/OIDC production nếu app dùng các hệ thống đó).

**C. Authorization hay CSRF?** Một editor có quyền `POST` vẫn bị 403 khi thiếu/invalid CSRF. Một viewer có valid CSRF vẫn bị 403 vì không có `ROLE_EDITOR`. Hai test này chống cách giải thích sai rằng mọi 403 đều có cùng nguyên nhân.

### 7.2. `@WithMockUser` không kiểm tra password

`@WithMockUser(username="alice", roles="USER")` tạo `Authentication` thử nghiệm và đặt vào `SecurityContext`; user alice **không phải tồn tại** trong `InMemoryUserDetailsManager`. Nó rất phù hợp để kiểm thử **authorization/logic theo principal**, nhưng không hề xác minh Basic password, token signature, OAuth login hoặc `UserDetailsService.loadUserByUsername`.

Tương tự, `user("synthetic-viewer").roles("USER")` là request post-processor, không gửi username/password thật qua HTTP Basic. `@WithUserDetails("viewer")` tải user details từ bean nhưng **không thực hiện một lần kiểm tra credential**. Vì thế dùng chúng **bổ sung** cho real login tests, không thay thế.

### 7.3. Có nhất thiết kiểm tra 401 và 403?

**Có, nếu đó là contract security:**
- **401 Unauthorized** thường dành cho request chưa được xác thực hoặc credential không hợp lệ, kèm `WWW-Authenticate` khi HTTP Basic cần challenge.
- **403 Forbidden** thường dành cho principal đã xác thực nhưng không đủ quyền, hoặc request thiếu CSRF token khi CSRF protection áp dụng.
- Trong cấu hình security khác (form login, OAuth2 login), request anonymous có thể được **redirect 302** tới trang login thay vì 401. Không copy mọi expected status của HTTP Basic test sang form-login app.

Test với user có role sai nhưng CSRF hợp lệ giúp xác minh **authorization** thực sự từ chối; test với user có role đúng nhưng CSRF thiếu giúp xác minh **CSRF** thực sự từ chối.

### 7.4. Role và authority trong Spring Security Test

`@WithMockUser(roles="EDITOR")` hoặc `user("x").roles("EDITOR")` thường tạo `GrantedAuthority("ROLE_EDITOR")`.

Nếu bạn dùng `user("x").authorities(new SimpleGrantedAuthority("EDITOR"))`, user chỉ có authority `EDITOR`, không có `ROLE_EDITOR`, nên `hasRole("EDITOR")` mặc định **không thỏa**. Tương tự, token JWT thường có authorities theo `SCOPE_...`, không tự thành `ROLE_...` nếu chưa cấu hình `JwtAuthenticationConverter` hoặc authorization rule tương ứng.

Trong dự án custom role prefix, phải dùng cùng converter/prefix với production và test những authorities **thực** được trao.

## 8. @WebMvcTest: bảo vệ đúng slice, không nhầm với full context

Khi chỉ muốn test MVC controller + security rules, `@WebMvcTest` khởi tạo hạ tầng servlet/MVC nhưng **không** quét mọi `@Service`. Nếu controller phụ thuộc `AuditService`, cần `@Import` implementation thật hoặc mock dependency phù hợp; và custom `SecurityConfig` cần được import để tránh dùng một chain mặc định khác production.

Tệp `src/test/java/com/example/securitylab/SecurityMvcSliceTest.java`:

```java
package com.example.securitylab;

import org.junit.jupiter.api.Test;

import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.context.annotation.Import;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.security.test.web.servlet.request
        .SecurityMockMvcRequestPostProcessors.httpBasic;
import static org.springframework.test.web.servlet.request
        .MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result
        .MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result
        .MockMvcResultMatchers.status;

@WebMvcTest(CatalogController.class)
@Import({SecurityConfig.class, AuditService.class})
class SecurityMvcSliceTest {

    @Autowired
    MockMvc mvc;

    @Test
    void anonymousItemIsProtectedByImportedChain()
            throws Exception {
        mvc.perform(get("/api/items/4"))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void viewerLoginGoesThroughImportedChain()
            throws Exception {
        mvc.perform(get("/api/items/4")
                .with(httpBasic("viewer", "viewer-pass")))
            .andExpect(status().isOk());
    }

    @Test
    void serviceMethodSecurityIsStillEffective()
            throws Exception {
        mvc.perform(get("/api/audit")
                .with(httpBasic("viewer", "viewer-pass")))
            .andExpect(status().isForbidden());
    }
}
```

Với `@Import({SecurityConfig.class,AuditService.class})`, slice có security rules và service proxy cần thiết. **Lưu ý:** nếu dự án production có nhiều authentication providers, filters, tenant resolvers hoặc configuration conditional, slice có thể không đại diện đầy đủ cho app. Khi mục tiêu là **tích hợp filter chain thật của cả hệ thống**, `@SpringBootTest + @AutoConfigureMockMvc` thường cho bằng chứng mạnh hơn.

### 8.1. Điều gì xảy ra nếu @WebMvcTest không import đúng SecurityConfig?

Spring Boot có thể dựng default security chain khi custom chain không vào slice. Khi đó endpoint vẫn bị 401, khiến một test `anonymousIsDenied` **xanh giả** dù security config thật không được kiểm chứng. Hãy assert ít nhất:
- Endpoint public được permit.
- Endpoint user role hợp lệ trả đúng.
- Endpoint role sai bị 403.
- CSRF enabled/disabled theo chủ ý.
- Method security nếu thuộc use case.
- Một số rule đặc thù của chính configuration sản phẩm.

Nếu SecurityConfig dùng external beans không thuộc slice, mock/import đúng phụ thuộc hoặc chuyển sang full integration test; đừng vô ý tắt authentication để “sửa” lỗi context.

## 9. Manual MockMvc setup phải thêm springSecurity()

Nếu bạn không dùng Boot auto-configured MockMvc, cấu hình theo Spring Security testing reference:

```java
MockMvc mvc = MockMvcBuilders
        .webAppContextSetup(webApplicationContext)
        .apply(springSecurity())
        .build();
```

Đây là **fragment** dùng trong JUnit setup method, với `WebApplicationContext webApplicationContext`, imports `MockMvcBuilders` và static import `SecurityMockMvcConfigurers.springSecurity`. Nó yêu cầu Spring context chứa `springSecurityFilterChain`.

`apply(springSecurity())` bổ sung setup cần thiết cho Spring Security, gồm `FilterChainProxy` và hỗ trợ `TestSecurityContextHolderPostProcessor` để `@WithMockUser`/`user()` liên kết đúng với MockMvc requests.

**Phản ví dụ:**

```java
MockMvc mvc = MockMvcBuilders
        .standaloneSetup(new CatalogController(...))
        .build();
```

Đây là đoạn **minh họa anti-pattern không độc lập**, với `...` tượng trưng các dependencies. Nếu bạn chỉ muốn test JSON mapping của một controller mà cố ý **không** test security, standalone setup vẫn có giá trị. Nhưng không được gọi nó là “integration test filter chain”. Việc `.with(user(...))` không tự đưa toàn bộ filter chain vào một MockMvc instance thiếu filters.

### 9.1. Vì sao `@AutoConfigureMockMvc(addFilters=false)` nguy hiểm cho security tests?

Nó có thể khiến:
- URL protected không được Security authorization filter chặn.
- CSRF filter không hoạt động.
- Request header authentication không được decode/validate.
- Method security vẫn có thể hoạt động nếu proxy được tạo, dẫn đến test 403 “đúng” vì một cơ chế khác trong khi HTTP filter chain đã bị bỏ.

**Vì thế cần test từ nhiều góc:** anonymous 401 của URL protected, Basic wrong password 401, valid password 200, missing CSRF 403 và role-specific 403. Một assertion duy nhất có thể đánh lừa.

## 10. CSRF: test cần xác minh cả token thiếu, sai và đúng

Với browser-authenticated flows, CSRF là cơ chế bảo vệ quan trọng cho các HTTP methods thay đổi trạng thái (`POST`, `PUT`, `PATCH`, `DELETE`). Trong ví dụ, `SecurityFilterChain` có CSRF enabled.

```java
// Thiếu CSRF: mặc định POST bị 403.
mvc.perform(post("/api/items")
        .with(httpBasic("editor", "editor-pass"))
        .contentType(MediaType.APPLICATION_JSON)
        .content("{\"name\":\"Notebook\"}"))
    .andExpect(status().isForbidden());

// CSRF hợp lệ trong MockMvc:
mvc.perform(post("/api/items")
        .with(httpBasic("editor", "editor-pass"))
        .with(csrf())
        .contentType(MediaType.APPLICATION_JSON)
        .content("{\"name\":\"Notebook\"}"))
    .andExpect(status().isCreated());

// CSRF sai:
mvc.perform(post("/api/items")
        .with(httpBasic("editor", "editor-pass"))
        .with(csrf().useInvalidToken())
        .contentType(MediaType.APPLICATION_JSON)
        .content("{\"name\":\"Notebook\"}"))
    .andExpect(status().isForbidden());
```

Các đoạn trên nằm trong test có `MockMvc mvc`, các static imports và controller/chain của bài; không phải file độc lập.

`csrf()` thường thêm token hợp lệ theo setup test; `csrf().asHeader()` đưa token qua header, `csrf().useInvalidToken()` tạo token không hợp lệ để xác minh hành vi từ chối.

**Giới hạn của mock CSRF:** `.with(csrf())` không chứng minh browser/UI thực sự đã lấy token từ server và gửi về đúng cookie/header theo cơ chế production. Với flow yêu cầu `CookieCsrfTokenRepository`, SPA hoặc session setup, cần integration test trao đổi token/session thực tế. Trong HTTP test qua `TestRestTemplate`, không có `.with(csrf())`; phải lấy token theo protocol web thật.

### 10.1. CSRF và stateless Bearer APIs

Một REST API chỉ chấp nhận bearer token do client chủ động đưa trong Authorization header, không dùng cookies/browser ambient auth, có thể có threat model khác và cấu hình CSRF disabled có chủ đích. Nhưng không được copy `csrf.disable()` chỉ để POST test pass khi ứng dụng còn dùng session cookie/form login/HTTP Basic từ trình duyệt.

**Test đúng** phải theo chính sách thật: nếu CSRF enabled thì thiếu/invalid token bị từ chối; nếu disabled có chủ đích, test cần xác nhận API vẫn yêu cầu authentication/authorization. CSRF disabled **không có nghĩa** mọi POST nên được public.

## 11. @WithMockUser, @WithUserDetails và request processors khác nhau

| Công cụ | Principal tạo ra từ đâu? | Có thử password/token decoder thật không? | Giá trị chính |
|---|---|---|---|
| `@WithMockUser(username="alice", roles="USER")` | Spring Security Test tự tạo mock user | **Không** | Authorization, principal-based logic |
| `@WithAnonymousUser` | Anonymous authentication test context | **Không** | Anonymous flow |
| `@WithUserDetails("viewer")` | `UserDetailsService` bean trong context | **Không** kiểm tra password supplied | UserDetails/roles từ store |
| `.with(user("alice").roles("USER"))` | User giả cho một MockMvc request | **Không** | Per-request principal/authorities |
| `.with(httpBasic("viewer","viewer-pass"))` | Authorization header đi qua `BasicAuthenticationFilter` | **Có** trong Spring context có Basic provider | Real HTTP Basic authentication integration |
| `.with(csrf())` | Test CSRF token | Không liên quan credential | Kiểm tra CSRF filter |
| `.with(jwt())` | JWT Authentication được dựng trong test | **Không** xác minh JWT signature/decoder | Authorization theo claims/authorities |
| `Authorization: Bearer token` với resource server config | Filter đọc header rồi dùng `JwtDecoder` | Có đi qua decoder được cấu hình | Bearer parsing và resource server integration |

**Cảnh báo về tên `@WithMockUser`:** Nó không mock luôn toàn bộ `SecurityFilterChain`. Khi MockMvc có filters thật, mock principal vẫn đi qua authorization rules/CSRF như trong ứng dụng. Điều nó **bỏ qua** là thao tác đăng nhập và xác minh credential.

### 11.1. Cấu hình default roles

`@WithMockUser` có username `user` và role `USER` theo mặc định. Đừng test endpoint cần ADMIN bằng `@WithMockUser` không có arguments rồi nghĩ mọi role đều được cấp.

Khi dùng `roles={"USER","ADMIN"}`, Spring Security Test tự thêm prefix `ROLE_`. Nếu đang dùng chính sách dựa trên OAuth scopes hoặc authority không có `ROLE_`, dùng `authorities={"SCOPE_orders.read"}` hoặc request JWT postprocessor phù hợp, và đảm bảo filter chain authorization rule thật tương ứng.

### 11.2. @WithSecurityContext cho custom principal

Khi ứng dụng cần custom `Authentication` (tenant id, claims, domain user), bạn có thể tạo meta-annotation với `@WithSecurityContext(factory=...)`. Factory cần xây một `SecurityContext` với principal/authorities đúng contract, giúp test không phải copy boilerplate.

**Không cần** custom factory chỉ để test một `ROLE_USER`; `@WithMockUser` thường rõ ràng hơn. Custom context vẫn không kiểm tra credential validation nếu factory dựng sẵn Authentication.

## 12. Method security: filter chain thật chưa đủ nếu method proxy bị bỏ qua

HTTP authorization quyết định request có được vào controller hay không. Method security cho phép áp quy tắc ở service, thường bằng `@PreAuthorize`, `@PostAuthorize`, `@PreFilter` hoặc `@PostFilter` khi được bật.

Trong ví dụ:
- `GET /api/audit` qua URL rule chỉ yêu cầu **authenticated**.
- `AuditService.readAudit()` có `@PreAuthorize("hasRole('AUDITOR')")`.
- `viewer` xác thực thành công bằng HTTP Basic nhưng **bị từ chối 403 khi gọi method**.
- `auditor` có đúng role và nhận `audit-report`.

Test method security có giá trị khi:
- Service được Spring tạo thành bean/proxy thật.
- `@EnableMethodSecurity` thực sự được cấu hình.
- Controller gọi service **qua Spring bean**, không tạo `new Service()` trực tiếp.
- Test có một case đủ role và một case thiếu role.

Nếu gọi `this.securedMethod()` từ cùng service theo proxy-based AOP, self-invocation có thể bỏ qua advice. Cần review thiết kế service và test cả internal call path nếu nghiệp vụ có rủi ro.

### 12.1. Kiểm thử service mà không cần MVC

Đối với logic method authorization thuần, một Spring test có thể inject `AuditService` và gọi trực tiếp với:
- `@WithMockUser(roles="AUDITOR")` → trả report.
- `@WithMockUser(roles="USER")` → ném `AccessDeniedException`.

Khi test phương thức trực tiếp qua bean/proxy, nó kiểm tra **method security**, nhưng không kiểm tra servlet filter/CSRF/HTTP 401/403 mapping. Để tuyên bố filter chain chạy thật, vẫn cần MockMvc/HTTP test tương ứng.

## 13. HTTP server thật: TestRestTemplate kiểm tra Basic authentication qua socket

Để bổ sung bằng chứng integration không phụ thuộc MockMvc, viết một test với `RANDOM_PORT`.

Tệp `src/test/java/com/example/securitylab/SecurityLiveHttpTest.java`:

```java
package com.example.securitylab;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.client.TestRestTemplate;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;

@SpringBootTest(
    webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class SecurityLiveHttpTest {

    @Autowired
    TestRestTemplate http;

    @Test
    void anonymousHttpRequestGets401() {
        ResponseEntity<String> response =
                http.getForEntity(
                    "/api/items/21", String.class);

        assertEquals(
                HttpStatus.UNAUTHORIZED,
                response.getStatusCode());
    }

    @Test
    void validBasicAuthWorksOverActualHttp() {
        ResponseEntity<CatalogController.ItemView> response =
            http.withBasicAuth("viewer", "viewer-pass")
                .getForEntity(
                    "/api/items/21",
                    CatalogController.ItemView.class);

        assertEquals(
                HttpStatus.OK,
                response.getStatusCode());
        assertNotNull(response.getBody());
        assertEquals(21L, response.getBody().id());
        assertEquals("viewer", response.getBody().actor());
    }
}
```

Điểm được thêm so với MockMvc:
- Embedded server thực sự listen trên random port.
- `TestRestTemplate` gửi HTTP request từ test JVM qua socket.
- Server servlet filter chain và Spring Security xử lý Basic header thực.
- Có thể quan sát HTTP response như một client độc lập.

Tuy nhiên, test này **không kiểm tra** TLS/ngược proxy/gateway production, không có user store bên ngoài và không thực hiện CSRF state-changing request. Đó là những test bổ sung khi kiến trúc yêu cầu.

## 14. OAuth2 Resource Server và JWT: phân biệt giả Authentication với thật Bearer filter

Nếu ứng dụng dùng JWT Resource Server, `spring-security-test` có `jwt()` postprocessor rất hữu ích:

```java
mvc.perform(get("/api/orders")
        .with(jwt().authorities(
            new SimpleGrantedAuthority("SCOPE_orders.read"))))
    .andExpect(status().isOk());
```

Đây là **đoạn minh họa** cho ứng dụng **đã có endpoint và SecurityFilterChain hỗ trợ JWT/authority thích hợp**. Nó không thuộc runnable HTTP Basic demo và cần import `SecurityMockMvcRequestPostProcessors.jwt`, `SimpleGrantedAuthority`, cùng security test dependencies.

**Không hiểu sai:** `.with(jwt())` tạo một authentication được chuẩn bị trước trong request, vì vậy nó **không giải mã một Bearer token bytes thật**, không kiểm tra signature/issuer/audience của JWT hay lỗi token expired do decoder.

Nếu muốn xác minh request đi qua `BearerTokenAuthenticationFilter`:
1. Cấu hình `http.oauth2ResourceServer(oauth -> oauth.jwt(...))` trên một chain phù hợp.
2. Cung cấp `JwtDecoder` theo production config hoặc một **test-only decoder mock**.
3. Gửi HTTP header thật:
   `Authorization: Bearer sample-token`.
4. Kiểm tra decoder nhận token, converter tạo authorities đúng, endpoint trả 200/403/401 tùy claims.
5. Để test **signature/issuer/audience thật**, không mock decoder; dùng signing keys/JWK test fixture và decoder config thực.

Trong Spring Boot 3.5, dependency cần cho case resource server thường là `spring-boot-starter-oauth2-resource-server`; không nên thêm JWT test giả vào HTTP Basic demo rồi kết luận app đang bật Bearer filter.

### 14.1. JWT roles, scopes và converter

JWT claim `scope="orders.read"` thường được Spring Security chuyển thành `SCOPE_orders.read`, trong khi `hasRole("USER")` mặc định đòi `ROLE_USER`. Một test `.with(jwt().authorities(...))` tự gán authorities có thể bỏ qua **converter thực** và tạo false positive nếu production converter đọc sai claims.

Do vậy cần ít nhất hai nhóm test:
- **Authorization rules** nhanh: `jwt()` với authorities dự kiến.
- **Filter/decoder/converter integration**: gửi Bearer header và kiểm tra `JwtDecoder`/converter thật hoặc test-configured.

Đừng log JWT/Authorization header thật trong failed assertions hoặc trace output.

## 15. CORS, nhiều filter chains và các điểm mù khó phát hiện

### 15.1. Nhiều SecurityFilterChain beans

Ứng dụng có thể có một chain cho `/api/**`, một chain khác cho `/admin/**` hoặc actuator. Mỗi chain có `securityMatcher(...)`, `@Order` và rules khác nhau. `FilterChainProxy` chọn chain **đầu tiên phù hợp**.

Test phải gửi requests đến từng nhóm URL và kiểm tra:
- Public endpoint thuộc chain nào?
- Protected endpoint có bị một chain rộng hơn “ăn” mất không?
- Có URL không match chain nào và đi ngoài security không?
- CSRF/session/Bearer config của từng chain có được áp dụng đúng không?
- Actuator/error/static resource routes có policies riêng không?

Một test chỉ kiểm tra bean `FilterChainProxy` tồn tại **không đủ** chứng minh mọi URL đều được bảo vệ. Nên có negative cases cho từng đường dẫn quan trọng.

### 15.2. Security headers

Spring Security mặc định hỗ trợ một số response headers, ví dụ `X-Content-Type-Options: nosniff`; ví dụ có một test kiểm tra header đó. Các headers khác có điều kiện:
- `Strict-Transport-Security` thường chỉ xuất hiện với HTTPS/secure request thích hợp, không nên assert chắc chắn trên HTTP MockMvc mặc định.
- `Content-Security-Policy` không được tùy tiện coi là auto-enabled; ứng dụng thường phải khai báo chính sách theo giao diện.
- CORS (`Access-Control-Allow-Origin`) phụ thuộc Origin, preflight và CorsConfiguration.
- `X-Frame-Options` và các policies khác phải tương thích nhu cầu embedding thực.

Test headers theo **hợp đồng security của ứng dụng**, không bằng snapshot cứng của mọi header mặc định trong framework.

### 15.3. CORS preflight không giống authentication request

Một browser có thể gửi `OPTIONS` preflight trước khi gửi request thật. Preflight không chứa credential như actual request; nếu security configuration chặn mọi `OPTIONS` vì thiếu Basic, ứng dụng có thể hoạt động với Postman nhưng fail trong browser.

Khi API phục vụ cross-origin, cấu hình CORS rõ ràng rồi test:
- Origin được cho phép → preflight trả headers/methods hợp lệ.
- Origin không được phép → preflight bị từ chối.
- Actual request vẫn yêu cầu authentication/authorization.
- `Access-Control-Allow-Credentials` không được kết hợp wildcard Origin tùy tiện.

Không thêm `permitAll(OPTIONS, "/**")` như một cách sửa chung mà không xét domain security policy và CORS processing.

## 16. @WithMockUser, SecurityContext và vòng đời test

Spring Security Test có `WithSecurityContextTestExecutionListener`, dựng test `SecurityContext` trước khi chạy test method (hoặc vào thời điểm được cấu hình) và cleanup khi kết thúc. Vì vậy hai test với `@WithMockUser` khác nhau không nên chia sẻ principal từ test trước nếu listener hoạt động đúng.

**Không giữ `SecurityContextHolder` trong static variable** rồi cho rằng state được cô lập tự động. Với test tự tạo threads/executors, SecurityContext gắn ThreadLocal không tự được truyền trừ khi sử dụng wrapper/context propagation đúng. Điều này khác với Reactor Context của giao dịch reactive; Spring Security MVC test chủ yếu làm việc với Servlet request và thread-bound context.

Các failure thường thấy:
- Gọi trực tiếp method và assert `SecurityContextHolder.getContext().getAuthentication()` nhưng không gửi HTTP request → chưa chứng minh filter chain.
- Quên test listener do cấu hình `@TestExecutionListeners` tùy biến thay thế mặc định → `@WithMockUser` không hoạt động.
- Dùng `@BeforeAll` để kiểm tra principal trong khi listener chỉ chuẩn bị context cho từng test → principal chưa có.
- Test run song song tạo static mutable security context → rò state cross-test.
- Nếu cần custom principal, `@WithSecurityContext` tạo context test được kiểm soát, nhưng vẫn không thay authentication filter.

### 16.1. Tests authorization thuần và tests credential nên tách tên

Một convention hữu ích:
- `viewerCannotDeleteEvenWithCsrf`: kiểm tra **authorization**.
- `incorrectBasicPasswordReturns401`: kiểm tra **authentication**.
- `editorWithInvalidCsrfIsForbidden`: kiểm tra **CSRF**.
- `methodSecurityRejectsViewer`: kiểm tra **method security**.
- `securityFilterChainBeanIsPresent`: kiểm tra **infrastructure**.
- `validBasicAuthWorksOverActualHttp`: kiểm tra **HTTP integration**.

Đặt tên theo hành vi và lý do thất bại giúp debug nhanh hơn so với `securityTest1`, `securityTest2`.

## 17. Bảo mật phiên, trạng thái và data layer trong security integration tests

Dự án ví dụ không tạo database record. Khi test security cho app có JPA/JDBC:
- `@Transactional` test có thể rollback thay đổi **trong test thread**, nhưng HTTP server thread thật có transaction riêng.
- `MockMvc` dùng cùng application context, nhưng service `@Transactional(REQUIRES_NEW)` có thể commit độc lập; cleanup cần xem đúng ranh giới.
- Test `403` nên còn kiểm tra **không có side effect** như tạo đơn hàng hoặc gửi event, nếu endpoint có tác động quan trọng.
- Nếu app có `@PreAuthorize("#id == authentication.principal.tenantId")`, cần test principal/resource thuộc tenant A/B và hành vi denial, không chỉ role đủ.
- Khi dùng session login, test `session fixation`, session invalidation/logout và cookies theo cấu hình nếu chúng thuộc threat model.
- Khi dùng JWT stateless, test scopes/claims/expiry/audience và bearer filter config, không dùng `@WithMockUser` để kết luận token validation đã được kiểm tra.

**Bảo mật là end-to-end property:** URL authorization đúng nhưng service bỏ qua tenant ownership vẫn có thể xảy ra IDOR (truy cập tài nguyên không thuộc quyền). Security filter tests là nền tảng, không thay business authorization tests.

## 18. Các lỗi thường gặp khi kiểm thử security

| Biểu hiện | Nguyên nhân thường gặp | Hướng kiểm tra |
|---|---|---|
| Endpoint protected trả 200 cho anonymous | MockMvc không gắn filters; `addFilters=false`; matcher sai | Bật filters, test anonymous 401/403, kiểm tra chain |
| Tất cả test 401 dù `@WithMockUser` | Security test listener/integration setup thiếu | `apply(springSecurity())` hoặc Boot `@AutoConfigureMockMvc` |
| HTTP Basic pass với sai password | Đang dùng mock principal thay vì Basic header | Test `httpBasic(user,wrong)` qua filter chain thật |
| Test `@WithMockUser` pass nhưng production login fail | Mock principal bỏ qua UserDetails/decoder | Thêm authentication filter + credential tests |
| POST 403 dù user có EDITOR | CSRF missing/invalid | Thêm `csrf()`; test riêng missing vs invalid |
| POST 403 dù đã thêm CSRF | User thiếu `ROLE_EDITOR` | Kiểm tra authority prefix và rule |
| Anonymous API trả 302 thay vì 401 | Form login redirect đang bật | Xác nhận entry point/authentication mechanism |
| `403` bị hiểu là “không đăng nhập” | Đã authenticated nhưng thiếu role, hoặc CSRF fail | Test cùng request với role/token riêng |
| `@PreAuthorize` không có hiệu lực | Thiếu `@EnableMethodSecurity`; self-invocation hoặc service tạo bằng new | Import config và dùng Spring bean proxy |
| `@WebMvcTest` báo thiếu bean service | Slice không scan ordinary services | `@Import` service cần hoặc mock dependency |
| `@WebMvcTest` dùng security khác production | Custom SecurityConfig bị slice loại | Import đúng config, assert positive/negative policies |
| `NoSuchBeanDefinitionException` với `FilterChainProxy` | Security auto-config không tạo chain | Kiểm tra dependency, bean SecurityFilterChain và config |
| Test session state rò giữa methods | Shared session/ContextHolder/static state | Dùng lifecycle per test, không giữ global auth |
| Security header test fail trong HTTP MockMvc | Header chỉ được thêm cho secure requests | Kiểm tra HTTPS precondition, không assert HSTS trên HTTP |
| JWT test `.with(jwt())` pass nhưng Bearer token thật fail | Bỏ qua JwtDecoder và signature/converter | Gửi Authorization: Bearer qua real resource-server chain |
| JWT user role thiếu `ROLE_` | JWT chuyển sang `SCOPE_` theo converter mặc định | Assert authorities thực, config converter |
| GET public vẫn 401 | URL không match permitAll hoặc bị chain khác chọn | Kiểm tra requestMatchers/securityMatcher/order |
| `OPTIONS` preflight bị 401 | CORS chưa chạy trước auth filters | Cấu hình CORS và test preflight riêng |
| `@AutoConfigureMockMvc(addFilters=false)` làm test CSRF pass | CSRF filter đã bị bỏ khỏi MockMvc | Giữ addFilters=true cho security tests |
| Test 403 nhưng DB vẫn có record | Side effect chạy trước authorization hoặc transaction khác commit | Kiểm tra side effects sau rejected request |
| Test chạy riêng pass, chạy suite fail | SecurityContext/context cache/static state hoặc shared data | Đọc test report, isolate test lifecycle |
| Build thành công nhưng không có tests | Wrong JUnit runner, skipped hoặc NO-SOURCE | Kiểm tra số methods được execute trong reports |

### 18.1. Cách debug một test “bị 403” có phương pháp

1. Xác định request thực sự đã đi qua **FilterChainProxy**.
2. Kiểm tra status và reason: anonymous/authentication/authorization/CSRF có khác nhau.
3. Kiểm tra test dùng `@WithMockUser` hay gửi `httpBasic()`/bearer header thật.
4. Xác định authority thực được tạo: `ROLE_EDITOR` khác `EDITOR` hoặc `SCOPE_editor`.
5. Với POST/PUT/PATCH/DELETE, kiểm tra CSRF config và token trong request.
6. Kiểm tra matcher và chain order: URL/method có match intended rule không.
7. Với `@PreAuthorize`, kiểm tra proxy và method interceptor.
8. Kiểm tra cookies/session/authorization header và entry point, nhưng **không in token/password thật** vào logs.
9. Nếu test gọi HTTP server thật, xác minh base URL/port và filter mapping thay vì giả định MockMvc behavior.
10. Nếu kết quả đúng nhưng test vẫn không bảo vệ được đường rủi ro, thêm negative case phù hợp thay vì chỉ test happy path.

## 19. Chạy tests và đọc report

Từ root project có Gradle wrapper:

```bash
./gradlew test --tests "com.example.securitylab.SecurityChainIntegrationTest"
./gradlew test --tests "com.example.securitylab.SecurityMvcSliceTest"
./gradlew test --tests "com.example.securitylab.SecurityLiveHttpTest"
```

Windows PowerShell:

```powershell
.\gradlew.bat test --tests "com.example.securitylab.SecurityChainIntegrationTest"
.\gradlew.bat test --tests "com.example.securitylab.SecurityMvcSliceTest"
.\gradlew.bat test --tests "com.example.securitylab.SecurityLiveHttpTest"
```

Nếu dự án đã có Maven wrapper với dependencies/BOM và Surefire tương đương:

```bash
./mvnw -Dtest=SecurityChainIntegrationTest test
./mvnw -Dtest=SecurityMvcSliceTest test
./mvnw -Dtest=SecurityLiveHttpTest test
```

Kiểm tra `build/reports/tests/test/index.html` (Gradle) hoặc `target/surefire-reports/` (Maven) của đúng module. Không coi `BUILD SUCCESSFUL` là bằng chứng test chạy nếu task ở trạng thái `NO-SOURCE` hoặc các methods bị skip.

**Mã nguồn trong bài được thiết kế để chạy với Java 17+ và Spring Boot 3.5.x** khi project có wrapper/dependencies phù hợp. Đây là tài liệu và expected behavior; không có chứng cứ runtime trong môi trường hiện tại, nên **không tuyên bố JUnit tests đã thực thi PASS**. Với Boot 4/Security 7, kiểm tra package mới của Boot test auto-configuration và những thay đổi API theo BOM tương ứng trước khi copy imports từ Boot 3.5.

### 19.1. Tại sao không dùng javac đơn lẻ?

Mã ví dụ sử dụng Spring MVC, Spring Security, JUnit và Gradle-managed dependencies. Chạy `javac CatalogController.java` đơn lẻ sẽ thiếu classpath framework. Cách xác thực thực tế là `./gradlew test` hoặc Maven/Surefire đã khai báo dependencies.

Khi viết Java thuần không có dependencies, `javac/java` là đủ; bài này là một integration testing project và nên chạy qua build tool.

## 20. Checklist review security test

- [ ] Có `spring-security-test` trong test dependencies, cùng BOM với runtime Spring Security.
- [ ] Dùng `SecurityFilterChain` thật, không mock toàn bộ authorization layer.
- [ ] Với MockMvc, `@AutoConfigureMockMvc(addFilters=true)` hoặc manual `apply(springSecurity())`.
- [ ] Có ít nhất một request anonymous bị từ chối trên protected URL.
- [ ] Có test credential đúng và sai đi qua real authentication filter khi đó là mục tiêu.
- [ ] `@WithMockUser` dùng cho authorization, không bị nhầm với password/JWT verification.
- [ ] `@WithUserDetails` dùng đúng `UserDetailsService` bean nhưng không bị coi là password check.
- [ ] Test 401/302/403 phù hợp entry point của ứng dụng.
- [ ] Test ít nhất một user đủ role và một user thiếu role cho mỗi sensitive endpoint.
- [ ] Role prefix, authorities, scopes và custom converters được kiểm tra.
- [ ] Với non-safe methods, test CSRF thiếu, sai và hợp lệ theo chính sách đã cấu hình.
- [ ] Nếu có `@PreAuthorize`, bật `@EnableMethodSecurity` và dùng Spring proxy thật.
- [ ] `@WebMvcTest` có security config/service dependencies đúng, không tự trôi sang default chain.
- [ ] Nếu có nhiều filter chains, test URL nằm trong từng `securityMatcher` và rule ưu tiên.
- [ ] Security headers/HSTS/CORS được test theo protocol/threat model, không theo giả định cứng.
- [ ] Khi JWT, tách test `jwt()` authorities với Bearer filter/JwtDecoder integration.
- [ ] Với HTTP server thật, có test qua random port và client thực nếu yêu cầu.
- [ ] Bị 401/403 không phát sinh DB/external side effect trái phép.
- [ ] Không hard-code production credentials hoặc log token/PII.
- [ ] Đọc reports để xác nhận số test thực sự được discover và execute.

## 21. Tài liệu chính thức để đối chiếu

- [Spring Security 6.5 — Servlet Testing](https://docs.spring.io/spring-security/reference/6.5/servlet/test/index.html): tổng quan `spring-security-test`.
- [Spring Security 6.5 — Setting Up MockMvc and Spring Security](https://docs.spring.io/spring-security/reference/6.5/servlet/test/mockmvc/setup.html): `FilterChainProxy` và `springSecurity()`.
- [Spring Security 6.5 — Running a Test as a User](https://docs.spring.io/spring-security/reference/6.5/servlet/test/mockmvc/authentication.html): `user()`, `@WithMockUser`, `@WithUserDetails`.
- [Spring Security 6.5 — HTTP Basic Testing](https://docs.spring.io/spring-security/reference/6.5/servlet/test/mockmvc/http-basic.html): `httpBasic()` tạo Authorization header.
- [Spring Security 6.5 — CSRF Testing](https://docs.spring.io/spring-security/reference/6.5/servlet/test/mockmvc/csrf.html): `csrf()`, `asHeader()`, `useInvalidToken()`.
- [Spring Security 6.5 — Method Security Tests](https://docs.spring.io/spring-security/reference/6.5/servlet/test/method.html): `@WithMockUser` khi kiểm thử method security.
- [Spring Boot 3.5 — Testing Spring Boot Applications](https://docs.spring.io/spring-boot/3.5/reference/testing/spring-boot-applications.html): `@WebMvcTest`, `@SpringBootTest`, `@AutoConfigureMockMvc`.
- [Spring Boot 3.5 — AutoConfigureMockMvc Javadoc](https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/test/autoconfigure/web/servlet/AutoConfigureMockMvc.html): `addFilters=true` mặc định.
- [Spring Security 6.5 — Java Configuration](https://docs.spring.io/spring-security/reference/6.5/servlet/configuration/java.html): `SecurityFilterChain`, matcher và filter configuration.
- [Spring Security 6.5 — Testing OAuth2 Resource Server JWT](https://docs.spring.io/spring-security/reference/6.5/servlet/test/mockmvc/oauth2.html): `jwt()` cho authorization test.
- [Spring Security — CSRF Protection](https://docs.spring.io/spring-security/reference/servlet/exploits/csrf.html): threat model và CSRF policies.

**Kết luận:** `spring-security-test` cung cấp principal giả, request post-processors và result matchers rất tiện, nhưng bài kiểm thử security chỉ có ý nghĩa khi **MockMvc đã thực sự tích hợp filter chain của Spring Security**. Dùng `@SpringBootTest + @AutoConfigureMockMvc(addFilters=true)` hoặc manual `apply(springSecurity())`, kết hợp test anonymous 401, user thiếu quyền 403, Basic credentials đúng/sai, CSRF token thiếu/sai/đúng và method `@PreAuthorize`. `@WithMockUser` và `jwt()` giúp kiểm thử phân quyền nhưng **không thay thế authentication/decoder tests**. Khi cần xác minh HTTP transport, bổ sung `RANDOM_PORT` và client thật; khi cần bảo vệ business ownership, bổ sung authorization/domain tests tương ứng.