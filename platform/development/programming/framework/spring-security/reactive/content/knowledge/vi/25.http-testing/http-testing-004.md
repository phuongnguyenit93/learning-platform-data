# @WithMockUser, mockUser() và người dùng ẩn danh

> **Chủ đề cha:** Kiểm thử HTTP trong Spring Security reactive. Bài này hướng dẫn dùng **Spring Security Test 6.5.x, Spring WebFlux, WebTestClient, Java 17+, Spring Boot 3.x và JUnit 5** để kiểm thử người dùng giả bằng `@WithMockUser` hoặc `mockUser()`, người dùng **anonymous**, phân quyền theo role/scope, HTTP 200/401/403, CSRF và reactive method security. Các mật khẩu trong ví dụ là dữ liệu demo, không dùng cho hệ thống thật.

## 1. Mục tiêu học tập

Khi hoàn thành, bạn có thể:

1. Phân biệt xác thực (authentication) và phân quyền (authorization) khi kiểm thử HTTP trên WebFlux.
2. Tạo `Authentication` giả bằng `@WithMockUser`, nắm rõ username và authority mặc định.
3. Dùng `WebTestClient.mutateWith(mockUser(...))` để thay principal cho một test client thay vì thay đổi mọi request.
4. Hiểu `@WithAnonymousUser`, request không có credential và lý do anonymous có thể bị chặn ở protected endpoints.
5. Chọn `roles = "ADMIN"` so với `authorities = "SCOPE_reports.read"` đúng trường hợp.
6. Biết thiết lập `WebTestClient.bindToApplicationContext(context).apply(springSecurity())`.
7. Viết tests 200 cho user có quyền, 403 cho user đã xác thực nhưng thiếu quyền và 401 cho anonymous khi cấu hình HTTP Basic entry point.
8. Kiểm thử POST có CSRF protection bằng `mutateWith(csrf())`; hiểu tại sao role đúng vẫn có thể bị 403.
9. Kiểm `@PreAuthorize` trên reactive service bằng `StepVerifier` và Reactor Context.
10. Viết test riêng gửi HTTP Basic credential thật để không nhầm `@WithMockUser` với việc đã kiểm tra password.
11. Hiểu vì sao user giả không thay thế `mockJwt()` hoặc real JWT/opaque token validation, và vì sao nó không được truyền qua remote HTTP port.
12. Thiết kế test isolation, tránh class-level annotation hoặc mutated client làm các bài test anonymous vô tình được cấp quyền.

**Nguyên tắc:** Mock identity **chỉ giả lập một Authentication đã được xác thực**. Nó giúp kiểm logic phân quyền nhưng **không chứng minh credential, password, JWT signature hoặc IdP thực được xác minh**.

## 2. Authentication, authorization và anonymous

Authentication trả lời: **Ai đang gọi?**

- HTTP Basic: server nhận username/password từ `Authorization: Basic ...`, dùng `ReactiveUserDetailsService` và `PasswordEncoder` xác minh.
- OAuth2 Resource Server: server nhận `Authorization: Bearer ...`, dùng JWT decoder hoặc opaque token introspection.
- Session login: principal đến từ phiên đăng nhập đã thiết lập.
- `@WithMockUser` và `mockUser()`: Spring Security Test tạo principal/authorities giả mà không kiểm credential thật.

Authorization trả lời: **Principal đó được làm gì?**

```java
http.authorizeExchange(exchanges -> exchanges
    .pathMatchers("/public/ping").permitAll()
    .pathMatchers("/me").authenticated()
    .pathMatchers("/admin").hasRole("ADMIN")
    .pathMatchers("/reports").hasAuthority("SCOPE_reports.read")
    .anyExchange().denyAll()
);
```

Đây là snippet cấu hình. Một user có ROLE_USER không tự được vào admin. Có ROLE_ADMIN cũng không tự được SCOPE_reports.read vì đó là authority khác.

Anonymous là request mà Spring Security không xác minh như account/session hợp lệ. Trong nhiều cấu hình, có `AnonymousAuthenticationToken` trong security context. Một chi tiết dễ nhầm: token loại này có thể có `isAuthenticated()==true` trên object, nhưng `authenticated()` trong Spring Security authorization expressions **không coi anonymous là user đã login**. Đừng tự kiểm một mình `auth != null && auth.isAuthenticated()` rồi dùng kết quả làm quyết định cấp quyền.

### 2.1 Mô hình kết quả HTTP

| Request | Authentication | Rule | Kết quả thường gặp |
| --- | --- | --- | --- |
| GET public | Anonymous | permitAll | 200 |
| GET protected không credential | Anonymous | authenticated | 401 nếu HTTP Basic/Bearer entry point |
| GET admin với ROLE_USER | Mock/real đã authenticated | hasRole("ADMIN") | 403 |
| GET admin với ROLE_ADMIN | Mock/real đã authenticated | hasRole("ADMIN") | 200 |
| GET reports với SCOPE_reports.read | Mock/real đã authenticated | exact authority | 200 |
| GET reports với ROLE_ADMIN nhưng thiếu scope | Đã authenticated | exact authority | 403 |
| POST editor không có CSRF | Đã authenticated | CSRF protection bật | 403 |
| POST editor có CSRF + đủ role | Đã authenticated | HTTP + method security | 200 |

**Không mặc định mọi project luôn trả 401 cho anonymous.** Với form login, request có thể nhận 302 redirect tới trang đăng nhập. Khi POST thiếu CSRF token, có thể nhận 403 trước khi tới authentication/authorization logic. Bài demo bật Basic và tắt form login để assertions 401/403 dễ đọc.

## 3. @WithMockUser

Import:

```java
import org.springframework.security.test.context.support.WithMockUser;
```

Annotation có thể đặt trên **test method hoặc test class**. Spring Security Test tạo `UsernamePasswordAuthenticationToken` với principal kiểu Spring Security `User` và authority được khai báo; user giả **không phải** record được truy xuất từ database.

### 3.1 Mặc định của @WithMockUser

```java
@Test
@WithMockUser
void example() {
    client.get().uri("/me")
        .exchange()
        .expectStatus().isOk();
}
```

Giá trị mặc định:
- Username: `user`.
- Mock password: `password`; **không có password verification**.
- Granted authority: `ROLE_USER` từ role `USER`.

Nếu endpoint trả `Principal.getName()`, test sẽ thấy tên `user`. Đừng khẳng định tài khoản user có trong `MapReactiveUserDetailsService` hay production DB chỉ vì test pass.

### 3.2 Đổi username và role

```java
@Test
@WithMockUser(username = "alice", roles = "USER")
void aliceCanReadOwnProfile() {
    client.get().uri("/me")
        .exchange()
        .expectStatus().isOk()
        .expectBody(String.class).isEqualTo("alice");
}
```

`roles = "USER"` được chuyển thành authority `ROLE_USER`. Với admin:

```java
@Test
@WithMockUser(roles = "ADMIN")
void adminCanReadRestrictedPage() {
    client.get().uri("/admin")
        .exchange()
        .expectStatus().isOk();
}
```

**Không dùng `roles = "ROLE_ADMIN"`**: Spring Security tự thêm prefix ROLE_ cho roles. Nếu đã có chuỗi đầy đủ, dùng `authorities = "ROLE_ADMIN"` hoặc chỉ truyền `roles = "ADMIN"`.

### 3.3 Role và scope authority khác nhau

Rule:

```java
.pathMatchers("/reports")
    .hasAuthority("SCOPE_reports.read")
```

Test đúng:

```java
@Test
@WithMockUser(authorities = "SCOPE_reports.read")
void reportScopeCanReadReports() {
    client.get().uri("/reports")
        .exchange()
        .expectStatus().isOk();
}
```

Sai về nghĩa: `roles = "SCOPE_reports.read"` tạo `ROLE_SCOPE_reports.read`, không khớp `SCOPE_reports.read`.

Khi cần nhiều authorities, cung cấp danh sách đầy đủ:

```java
@WithMockUser(authorities = {
    "ROLE_ADMIN",
    "SCOPE_reports.read"
})
```

Dùng `roles` hoặc `authorities` có chủ đích; tránh chỉ định cả hai rồi ngầm hy vọng chúng được nối mà không tuân thủ contract của annotation.

## 4. mockUser(): mutator của WebTestClient

Static import:

```java
import static org.springframework.security.test.web.reactive.server
    .SecurityMockServerConfigurers.mockUser;
```

Ví dụ:

```java
client.mutateWith(mockUser())
    .get().uri("/me")
    .exchange()
    .expectStatus().isOk();
```

`mockUser()` cũng tạo principal giả mặc định `user` với ROLE_USER. Khác annotation, đây là **WebTestClient mutator**, phù hợp khi một test cần đổi identity linh hoạt theo request.

### 4.1 Mutate client không làm client gốc thành admin

```java
WebTestClient adminClient = client.mutateWith(
    mockUser("bob").roles("ADMIN")
);

adminClient.get().uri("/admin")
    .exchange()
    .expectStatus().isOk();

client.get().uri("/admin")
    .exchange()
    .expectStatus().isUnauthorized();
```

Snippet giả định `client` gốc không có class-level `@WithMockUser` hoặc credentials/session. Mutated client có identity bob, còn client gốc vẫn không được gắn admin.

### 4.2 Mutate authorities thay vì roles

```java
client.mutateWith(
    mockUser("analyst").authorities(
        new SimpleGrantedAuthority("SCOPE_reports.read")
    )
).get().uri("/reports")
 .exchange()
 .expectStatus().isOk();
```

Cần import `org.springframework.security.core.authority.SimpleGrantedAuthority`. Đừng trộn `roles("ADMIN")` với `authorities(...)` rồi mong cả hai sets luôn tự động hợp nhất theo ý.

### 4.3 So sánh @WithMockUser và mockUser()

| Tiêu chí | @WithMockUser | mockUser() |
| --- | --- | --- |
| Vị trí | Annotation method/class | `mutateWith` trên WebTestClient |
| Phạm vi chính | Test lifecycle | Client/request cụ thể |
| Username | `username = "alice"` | `mockUser("alice")` |
| Role | `roles = "ADMIN"` | `mockUser().roles("ADMIN")` |
| Exact authority | `authorities = "SCOPE_x"` | `authorities(new SimpleGrantedAuthority("SCOPE_x"))` |
| Có đi qua Basic password verification? | Không | Không |
| Có tự verify JWT? | Không | Không |
| Dễ dùng khi test nhiều users | Cần nhiều test/annotations | Tạo nhiều mutated clients |
| Cần Spring Security Test integration | Có | Có |

**Gợi ý:** Annotation làm tests một identity gọn hơn. Mutator thuận tiện hơn cho test có alice, bob, admin, anonymous trong cùng method.

## 5. @WithAnonymousUser và request không credentials

Import:

```java
import org.springframework.security.test.context.support.WithAnonymousUser;
```

Nếu test class **không** có mock user mặc định, đơn giản không gắn annotation hay Basic/Bearer header:

```java
@Test
void publicEndpointAllowsAnonymous() {
    client.get().uri("/public/ping")
        .exchange()
        .expectStatus().isOk();
}

@Test
void protectedEndpointRejectsAnonymous() {
    client.get().uri("/me")
        .exchange()
        .expectStatus().isUnauthorized();
}
```

Khi test class có `@WithMockUser` cấp class, method-level `@WithAnonymousUser` có thể override:

```java
@SpringBootTest
@WithMockUser(roles = "USER")
class ClassLevelExample {

    @Test
    void testHasMockUser() {
        // Các lệnh test trong method có mock user ROLE_USER.
    }

    @Test
    @WithAnonymousUser
    void testOverridesClassUserWithAnonymous() {
        // Không mặc nhiên dùng class-level authenticated user.
    }
}
```

Đây là **minh họa annotations**, không phải class kiểm thử hoàn chỉnh vì chưa có client/assertions. Mục đích là tránh test anonymous bất ngờ thành công do kế thừa class-level auth.

### 5.1 Anonymous không tự có quyền data

Anonymous có thể có principal biểu diễn dạng `anonymousUser` và authority `ROLE_ANONYMOUS`. Điều này không tương đương account thật. Không cho truy cập dữ liệu cá nhân chỉ vì `Authentication.getName()` trả một string không rỗng hoặc `isAuthenticated()` trả true. Dùng Spring Security authorization rules và domain ACL đáng tin.

### 5.2 Test chính sách public trước khi test protected

Public endpoint `permitAll()` không yêu cầu mock user; nó phải chạy với anonymous. Nếu chỉ dùng `@WithMockUser` để test public endpoint, test đó **không chứng minh** bạn đã cấu hình route public đúng.

Tương tự, route `authenticated()` cần negative test thật không credentials; một test mock authenticated trả 200 chưa đủ chứng minh endpoint được bảo vệ.

## 6. WebTestClient + springSecurity() setup

Trong Spring Security 6.5 reactive test, cấu hình điển hình là:

```java
import static org.springframework.security.test.web.reactive.server
    .SecurityMockServerConfigurers.springSecurity;

@BeforeEach
void setUp() {
    client = WebTestClient.bindToApplicationContext(context)
        .apply(springSecurity())
        .configureClient()
        .build();
}
```

- `bindToApplicationContext` gửi request nội bộ qua WebFlux application context.
- `apply(springSecurity())` gắn integration của Spring Security Test vào WebTestClient.
- `configureClient().build()` hoàn thiện client.
- Với `@SpringBootTest`, Spring TestContext và security test listeners thực hiện lifecycle của `@WithMockUser`/`@WithAnonymousUser`.
- WebFlux SecurityContext sử dụng **Reactor Context**, không phải chỉ `ThreadLocal SecurityContextHolder` của Servlet.

**Không nhầm với MVC:** Servlet tests dùng `MockMvc`, `HttpSecurity`, `SecurityFilterChain` và `SecurityMockMvcRequestPostProcessors.user()`. WebFlux dùng `WebTestClient`, `ServerHttpSecurity`, `SecurityWebFilterChain` và `SecurityMockServerConfigurers.mockUser()`.

Nếu chỉ `WebTestClient.bindToController(new Controller())` mà không gắn WebFlux SecurityFilterChain, test có thể chạy handler nhưng bỏ qua authorization. Để kiểm filter/security thật, dùng bind-to-application-context với springSecurity support hoặc integration test được cấu hình tương đương.

## 7. Mini project: Java 17+, Spring Boot 3.x, WebFlux

Ví dụ cung cấp:

| Endpoint | Policy | Để test |
| --- | --- | --- |
| GET `/public/ping` | `permitAll()` | Anonymous 200 |
| GET `/me` | `authenticated()` | Anonymous 401; mock/basic user 200 |
| GET `/admin` | `hasRole("ADMIN")` | User 403, admin 200 |
| GET `/reports` | `hasAuthority("SCOPE_reports.read")` | Scope 200, role đơn thuần 403 |
| POST `/notes/approve` | HTTP authenticated + `@PreAuthorize("hasRole('EDITOR')")` ở service | CSRF + role |
| Route khác | `denyAll()` | Không tự mở route mới |

### 7.1 Dependencies

Tạo Spring Boot 3.x Gradle Groovy project Java 17+ với Reactive Web và Security. Phần dependencies trong `build.gradle` (project đã có Spring Boot plugins):

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
    implementation 'org.springframework.boot:spring-boot-starter-security'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
    testImplementation 'io.projectreactor:reactor-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

`spring-security-test` chứa mock annotations/mutators; `reactor-test` chứa StepVerifier. Không thêm `spring-boot-starter-web` vào project chỉ muốn WebFlux, vì Boot thường ưu tiên Spring MVC khi cả hai starters có mặt.

### 7.2 File layout

```text
src/main/java/com/example/reactivetest/
  ReactiveTestApplication.java
  WebSecurityConfiguration.java
  NoteService.java
  DemoController.java
src/test/java/com/example/reactivetest/
  ReactiveHttpSecurityTest.java
  NoteServiceSecurityTest.java
```

Mỗi public class lưu trong file cùng tên, package `com.example.reactivetest`. Các ví dụ yêu cầu Spring Boot dependency classpath, không chạy bằng `javac` riêng rẽ.

### 7.3 ReactiveTestApplication.java

`src/main/java/com/example/reactivetest/ReactiveTestApplication.java`:

```java
package com.example.reactivetest;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ReactiveTestApplication {

    public static void main(String[] args) {
        SpringApplication.run(ReactiveTestApplication.class, args);
    }
}
```

### 7.4 WebSecurityConfiguration.java

`src/main/java/com/example/reactivetest/WebSecurityConfiguration.java`:

```java
package com.example.reactivetest;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.method.configuration.EnableReactiveMethodSecurity;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.crypto.factory.PasswordEncoderFactories;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.MapReactiveUserDetailsService;
import org.springframework.security.web.server.SecurityWebFilterChain;

@Configuration(proxyBeanMethods = false)
@EnableWebFluxSecurity
@EnableReactiveMethodSecurity
public class WebSecurityConfiguration {

    @Bean
    PasswordEncoder passwordEncoder() {
        return PasswordEncoderFactories.createDelegatingPasswordEncoder();
    }

    @Bean
    MapReactiveUserDetailsService users(PasswordEncoder encoder) {
        var reader = User.withUsername("reader")
            .password(encoder.encode("reader-demo-password"))
            .roles("USER")
            .build();

        var editor = User.withUsername("editor")
            .password(encoder.encode("editor-demo-password"))
            .roles("USER", "EDITOR")
            .build();

        var admin = User.withUsername("admin")
            .password(encoder.encode("admin-demo-password"))
            .roles("USER", "ADMIN")
            .build();

        return new MapReactiveUserDetailsService(
            reader, editor, admin
        );
    }

    @Bean
    SecurityWebFilterChain securityWebFilterChain(
            ServerHttpSecurity http) {

        return http
            .authorizeExchange(exchanges -> exchanges
                .pathMatchers(HttpMethod.GET, "/public/ping")
                    .permitAll()
                .pathMatchers(HttpMethod.GET, "/me")
                    .authenticated()
                .pathMatchers(HttpMethod.GET, "/admin")
                    .hasRole("ADMIN")
                .pathMatchers(HttpMethod.GET, "/reports")
                    .hasAuthority("SCOPE_reports.read")
                .pathMatchers(HttpMethod.POST, "/notes/approve")
                    .authenticated()
                .anyExchange().denyAll()
            )
            .httpBasic(Customizer.withDefaults())
            .formLogin(ServerHttpSecurity.FormLoginSpec::disable)
            // CSRF remains ENABLED for unsafe HTTP methods.
            .build();
    }
}
```

- UserDetailsService là store demo, không phải DB user production.
- Basic được bật để có test với **password thật** qua Spring Security authentication filter.
- Form login tắt để unauthenticated request không bị redirect tới login page; protected anonymous GET dự kiến 401.
- `@EnableReactiveMethodSecurity` bật `@PreAuthorize` trên reactive service.
- CSRF mặc định **không bị tắt**; POST không có csrf() có thể bị 403 trước khi đến service.
- Route fallback denyAll giúp endpoint mới không vô tình public.

### 7.5 NoteService.java

`src/main/java/com/example/reactivetest/NoteService.java`:

```java
package com.example.reactivetest;

import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.stereotype.Service;
import reactor.core.publisher.Mono;

@Service
public class NoteService {

    @PreAuthorize("hasRole('EDITOR')")
    public Mono<String> approve() {
        return Mono.just("approved");
    }
}
```

Phương thức trả `Mono<String>` đúng reactive method security; `@PreAuthorize` đòi ROLE_EDITOR. Service phải được Spring quản lý; tự `new NoteService()` sẽ không có method-security proxy.

### 7.6 DemoController.java

`src/main/java/com/example/reactivetest/DemoController.java`:

```java
package com.example.reactivetest;

import java.security.Principal;

import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RestController;

import reactor.core.publisher.Mono;

@RestController
public class DemoController {

    private final NoteService noteService;

    public DemoController(NoteService noteService) {
        this.noteService = noteService;
    }

    @GetMapping(
        value = "/public/ping",
        produces = MediaType.TEXT_PLAIN_VALUE
    )
    public Mono<String> ping() {
        return Mono.just("pong");
    }

    @GetMapping(
        value = "/me",
        produces = MediaType.TEXT_PLAIN_VALUE
    )
    public Mono<String> me(Principal principal) {
        return Mono.just(principal.getName());
    }

    @GetMapping(
        value = "/admin",
        produces = MediaType.TEXT_PLAIN_VALUE
    )
    public Mono<String> admin() {
        return Mono.just("admin-ok");
    }

    @GetMapping(
        value = "/reports",
        produces = MediaType.TEXT_PLAIN_VALUE
    )
    public Mono<String> reports() {
        return Mono.just("reports-ok");
    }

    @PostMapping(
        value = "/notes/approve",
        produces = MediaType.TEXT_PLAIN_VALUE
    )
    public Mono<String> approve() {
        return noteService.approve();
    }
}
```

`Principal` ở `/me` chỉ được đưa vào sau rule authenticated. Public endpoint không cố trích username để không đưa anonymous vào logic user-specific. Đây là ví dụ đơn giản, chưa có tenant/resource ACL.

## 8. ReactiveHttpSecurityTest.java: 18 bài test HTTP

Tạo `src/test/java/com/example/reactivetest/ReactiveHttpSecurityTest.java`. Bộ test dùng `WebTestClient` kết nối application context thật, không mở HTTP port. Những test `@WithMockUser` kiểm authorization; những test Basic header không có annotation để đi qua authentication filter.

```java
package com.example.reactivetest;

import static org.springframework.security.test.web.reactive.server
    .SecurityMockServerConfigurers.csrf;
import static org.springframework.security.test.web.reactive.server
    .SecurityMockServerConfigurers.mockUser;
import static org.springframework.security.test.web.reactive.server
    .SecurityMockServerConfigurers.springSecurity;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.ApplicationContext;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.test.context.support.WithAnonymousUser;
import org.springframework.security.test.context.support.WithMockUser;
import org.springframework.test.web.reactive.server.WebTestClient;

@SpringBootTest(
    webEnvironment = SpringBootTest.WebEnvironment.MOCK
)
class ReactiveHttpSecurityTest {

    @Autowired
    ApplicationContext context;

    WebTestClient client;

    @BeforeEach
    void setUp() {
        client = WebTestClient
            .bindToApplicationContext(context)
            .apply(springSecurity())
            .configureClient()
            .build();
    }

    @Test
    void anonymousCanReadPublic() {
        client.get().uri("/public/ping")
            .exchange()
            .expectStatus().isOk()
            .expectBody(String.class).isEqualTo("pong");
    }

    @Test
    void unauthenticatedCannotReadMe() {
        client.get().uri("/me")
            .exchange()
            .expectStatus().isUnauthorized();
    }

    @Test
    @WithAnonymousUser
    void explicitlyAnonymousCannotCallAdmin() {
        client.get().uri("/admin")
            .exchange()
            .expectStatus().isUnauthorized();
    }

    @Test
    @WithMockUser
    void defaultMockUsernameIsUser() {
        client.get().uri("/me")
            .exchange()
            .expectStatus().isOk()
            .expectBody(String.class).isEqualTo("user");
    }

    @Test
    @WithMockUser(username = "alice", roles = "USER")
    void aliceNameComesFromMockPrincipal() {
        client.get().uri("/me")
            .exchange()
            .expectStatus().isOk()
            .expectBody(String.class).isEqualTo("alice");
    }

    @Test
    @WithMockUser(roles = "USER")
    void userCannotCallAdmin() {
        client.get().uri("/admin")
            .exchange()
            .expectStatus().isForbidden();
    }

    @Test
    @WithMockUser(roles = "ADMIN")
    void annotatedAdminCanCallAdmin() {
        client.get().uri("/admin")
            .exchange()
            .expectStatus().isOk()
            .expectBody(String.class).isEqualTo("admin-ok");
    }

    @Test
    void perRequestAdminDoesNotChangeOriginalClient() {
        WebTestClient asAdmin =
            client.mutateWith(mockUser("bob").roles("ADMIN"));

        asAdmin.get().uri("/admin")
            .exchange()
            .expectStatus().isOk();

        client.get().uri("/admin")
            .exchange()
            .expectStatus().isUnauthorized();
    }

    @Test
    void mockUserWithExactScopeCanReadReports() {
        client.mutateWith(
            mockUser("analyst").authorities(
                new SimpleGrantedAuthority("SCOPE_reports.read")
            )
        ).get().uri("/reports")
         .exchange()
         .expectStatus().isOk()
         .expectBody(String.class).isEqualTo("reports-ok");
    }

    @Test
    @WithMockUser(authorities = "SCOPE_reports.read")
    void annotatedScopeCanReadReports() {
        client.get().uri("/reports")
            .exchange()
            .expectStatus().isOk();
    }

    @Test
    @WithMockUser(roles = "ADMIN")
    void adminRoleDoesNotImplyReportScope() {
        client.get().uri("/reports")
            .exchange()
            .expectStatus().isForbidden();
    }

    @Test
    @WithMockUser(roles = "EDITOR")
    void editorPostWithoutCsrfIsRejected() {
        client.post().uri("/notes/approve")
            .exchange()
            .expectStatus().isForbidden();
    }

    @Test
    @WithMockUser(roles = "EDITOR")
    void editorWithCsrfCanApprove() {
        client.mutateWith(csrf())
            .post().uri("/notes/approve")
            .exchange()
            .expectStatus().isOk()
            .expectBody(String.class).isEqualTo("approved");
    }

    @Test
    @WithMockUser(roles = "USER")
    void csrfDoesNotGrantEditorRole() {
        client.mutateWith(csrf())
            .post().uri("/notes/approve")
            .exchange()
            .expectStatus().isForbidden();
    }

    @Test
    void correctBasicPasswordAuthenticatesRealFilter() {
        client.get().uri("/me")
            .headers(h -> h.setBasicAuth(
                "reader", "reader-demo-password"))
            .exchange()
            .expectStatus().isOk()
            .expectBody(String.class).isEqualTo("reader");
    }

    @Test
    void incorrectBasicPasswordIsRejected() {
        client.get().uri("/me")
            .headers(h -> h.setBasicAuth(
                "reader", "incorrect-password"))
            .exchange()
            .expectStatus().isUnauthorized();
    }

    @Test
    void basicReaderLacksAdminRole() {
        client.get().uri("/admin")
            .headers(h -> h.setBasicAuth(
                "reader", "reader-demo-password"))
            .exchange()
            .expectStatus().isForbidden();
    }

    @Test
    void basicAdminCanCallAdmin() {
        client.get().uri("/admin")
            .headers(h -> h.setBasicAuth(
                "admin", "admin-demo-password"))
            .exchange()
            .expectStatus().isOk()
            .expectBody(String.class).isEqualTo("admin-ok");
    }
}
```

**Vì sao những tests này có giá trị?**
- Anonymous tests kiểm endpoint public lẫn protected, không bị @WithMockUser class-level ẩn đi.
- Mock annotation kiểm username/roles và rule HTTP.
- Mock mutator kiểm isolation và exact scope authorities.
- POST tests chứng minh CSRF và role là hai lớp riêng.
- Basic tests dùng **thông tin xác thực thật** của demo `MapReactiveUserDetailsService`, không bypass password manager.

### 8.1 Kết quả dự kiến

| Nhóm | Kịch bản | HTTP |
| --- | --- | --- |
| Anonymous | GET /public/ping | 200 |
| Anonymous | GET /me không credentials | 401 |
| Explicit anonymous | GET /admin | 401 |
| @WithMockUser default | GET /me, username=user | 200 |
| @WithMockUser alice | GET /me, username=alice | 200 |
| @WithMockUser ROLE_USER | GET /admin | 403 |
| @WithMockUser ROLE_ADMIN | GET /admin | 200 |
| mockUser bob/ADMIN | GET /admin | 200 |
| Client gốc không mock | GET /admin | 401 |
| mockUser SCOPE_reports.read | GET /reports | 200 |
| @WithMockUser SCOPE_reports.read | GET /reports | 200 |
| Role ADMIN nhưng thiếu scope | GET /reports | 403 |
| EDITOR không csrf() | POST /notes/approve | 403 |
| EDITOR có csrf() | POST /notes/approve | 200 |
| USER có csrf() | POST /notes/approve | 403 |
| Basic reader đúng password | GET /me | 200 |
| Basic reader sai password | GET /me | 401 |
| Basic reader tới admin | GET /admin | 403 |
| Basic admin tới admin | GET /admin | 200 |

Bảng có 19 dòng HTTP assertions vì test `perRequestAdminDoesNotChangeOriginalClient` kiểm **hai requests**. File có **18 test methods**. Đây là kết quả **kỳ vọng theo mã**; chưa thực thi Gradle trong môi trường biên soạn.

### 8.2 Chạy test

Linux/macOS:

```bash
./gradlew test --tests '*ReactiveHttpSecurityTest'
```

Windows PowerShell:

```powershell
.\gradlew.bat test --tests '*ReactiveHttpSecurityTest'
```

Vì `WebTestClient` bind vào application context, không cần chạy `bootRun` trước khi chạy test.

## 9. Test @PreAuthorize trên reactive service bằng StepVerifier

`@EnableReactiveMethodSecurity` kết hợp `@PreAuthorize` bảo vệ service. Với reactive return type `Mono`/`Flux`, evaluation dựa trên `Reactor Context` trong quá trình subscription.

`src/test/java/com/example/reactivetest/NoteServiceSecurityTest.java`:

```java
package com.example.reactivetest;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.security.test.context.support.WithAnonymousUser;
import org.springframework.security.test.context.support.WithMockUser;

import reactor.test.StepVerifier;

@SpringBootTest(
    webEnvironment = SpringBootTest.WebEnvironment.MOCK
)
class NoteServiceSecurityTest {

    @Autowired
    NoteService notes;

    @Test
    @WithMockUser(roles = "EDITOR")
    void editorCanApprove() {
        StepVerifier.create(notes.approve())
            .expectNext("approved")
            .verifyComplete();
    }

    @Test
    @WithMockUser(roles = "USER")
    void userIsDenied() {
        StepVerifier.create(notes.approve())
            .expectError()
            .verify();
    }

    @Test
    @WithAnonymousUser
    void anonymousIsDenied() {
        StepVerifier.create(notes.approve())
            .expectError()
            .verify();
    }
}
```

Test này kiểm security proxy của Spring-managed `NoteService`. `expectError()` ở hai trường hợp từ chối không ép mọi phiên bản/nơi gọi dùng cùng exception subclass; khi cần chặt hơn, kiểm `AccessDeniedException` theo contract thực.

### 9.1 Vì sao không khởi tạo service bằng new?

Sai:

```java
NoteService service = new NoteService();
StepVerifier.create(service.approve())
    .expectNext("approved")
    .verifyComplete();
```

Mã này gọi object **không đi qua Spring AOP proxy**, do đó `@PreAuthorize` có thể không chạy. Đúng: autowire `NoteService` từ Spring context có `@EnableReactiveMethodSecurity`.

### 9.2 Vì sao Reactor Context quan trọng?

Không tự dùng `SecurityContextHolder.setContext(...)` theo cách Servlet rồi kỳ vọng nó tự truyền xuyên qua mọi reactive subscription. Với WebFlux, security context đi theo Reactor subscriber context; Spring Security Test có `ReactorContextTestExecutionListener` để tương thích.

Nếu cần test thủ công không dùng annotation, có thể:

```java
Authentication authentication =
    new TestingAuthenticationToken(
        "alice", "unused", "ROLE_EDITOR");

Mono<String> result = notes.approve()
    .contextWrite(
        ReactiveSecurityContextHolder.withAuthentication(
            authentication)
    );

StepVerifier.create(result)
    .expectNext("approved")
    .verifyComplete();
```

**Đây là snippet**, cần imports `Authentication`, `TestingAuthenticationToken`, `ReactiveSecurityContextHolder`, `Mono` và `StepVerifier`; `notes` phải là Spring-managed proxied service. Test annotations tiện hơn cho cases thông thường.

## 10. Vì sao POST có mock editor vẫn 403?

`@WithMockUser(roles="EDITOR")` cung cấp **Authentication**, không cung cấp **CSRF token**. Spring Security WebFlux mặc định bật CSRF protection cho các methods gây thay đổi trạng thái (POST/PUT/PATCH/DELETE).

Đúng hai tests riêng:

```java
@Test
@WithMockUser(roles = "EDITOR")
void withoutCsrfShouldFail() {
    client.post().uri("/notes/approve")
        .exchange()
        .expectStatus().isForbidden();
}

@Test
@WithMockUser(roles = "EDITOR")
void withCsrfShouldPass() {
    client.mutateWith(csrf())
        .post().uri("/notes/approve")
        .exchange()
        .expectStatus().isOk();
}
```

Static import `csrf` từ `SecurityMockServerConfigurers`. Với user ROLE_USER, ngay cả khi đã có CSRF token thì service `@PreAuthorize("hasRole('EDITOR')")` vẫn từ chối.

### 10.1 CSRF không phải role

| User | CSRF token | Quyền ở service | Kỳ vọng |
| --- | --- | --- | --- |
| EDITOR | Thiếu | Có ROLE_EDITOR | 403 do CSRF |
| EDITOR | Hợp lệ | Có ROLE_EDITOR | 200 |
| USER | Hợp lệ | Không ROLE_EDITOR | 403 do method security |
| Anonymous | Thiếu | Không | Có thể 403 do CSRF hoặc 401 tùy entrypoint/filter order |
| Admin | Hợp lệ | Route HTTP denyAll | 403 do HTTP authorization |

Không bỏ CSRF trên toàn ứng dụng để làm tests pass. Với API Bearer-only không có ambient browser credentials, có thể thiết kế CSRF policy khác nhưng cần threat model rõ. CORS cũng không thay thế CSRF hoặc authentication.

## 11. Anonymous, 401/403 và form-login redirect

**401 Unauthorized**: protected API yêu cầu Authentication nhưng caller chưa có credential hợp lệ. Khi bật HTTP Basic, response thường có `WWW-Authenticate: Basic ...`.

**403 Forbidden**: caller đã authenticated nhưng thiếu authority, hoặc request bị CSRF filter từ chối. Do đó hai tests cùng `expectStatus().isForbidden()` có thể đang kiểm **hai nguyên nhân khác nhau**.

**302 redirect**: nếu bật form login, anonymous vào protected route có thể được chuyển tới login page. Điều này không có nghĩa policy đúng/sai hơn; chỉ khác authentication entrypoint.

**404 Not Found**: nếu route chưa tồn tại hoặc handler không match, status phụ thuộc security filter order. Không dùng một 404 đơn lẻ làm bằng chứng authorization đã chặn tài nguyên.

**Fail closed**: thiếu/sai authentication không được biến thành permitAll để tránh test hỏng.

## 12. Mock authentication không kiểm password, JWT và IdP

### 12.1 HTTP Basic thật khác @WithMockUser

`@WithMockUser(username="reader")` pass khi rule chỉ đòi authenticated, ngay cả nếu reader không tồn tại trong DB. Đó là tính năng mock, không phải lỗi.

Test credential thực cần:

```java
client.get().uri("/me")
    .headers(h -> h.setBasicAuth(
        "reader", "reader-demo-password"))
    .exchange()
    .expectStatus().isOk();

client.get().uri("/me")
    .headers(h -> h.setBasicAuth(
        "reader", "incorrect-password"))
    .exchange()
    .expectStatus().isUnauthorized();
```

**Không đặt `@WithMockUser` trên test đang cố chứng minh Basic password sai**, vì mock identity có thể ảnh hưởng kết quả.

### 12.2 JWT và opaque Bearer tokens

Một fake mock user có `SCOPE_reports.read` không chứng minh:
- JWT có chữ ký hợp lệ;
- `iss`, `aud`, `exp`, `nbf` và allowed algorithms được kiểm;
- Opaque token đã được introspection và `active:true`;
- `WWW-Authenticate` hoặc malformed Bearer headers đúng;
- Token revocation, role mapper, tenant scope đúng.

Nếu app thật là OAuth2 Resource Server, Spring Security Test có `mockJwt()` / `mockOpaqueToken()` để mô phỏng authentication type phù hợp. Ví dụ snippet **chỉ dành cho ứng dụng đã cấu hình JWT Resource Server**, không phải project Basic-only ở mục 7:

```java
client.mutateWith(
    mockJwt().authorities(
        new SimpleGrantedAuthority("SCOPE_reports.read")
    )
).get().uri("/reports")
 .exchange()
 .expectStatus().isOk();
```

Import `mockJwt` đúng package Spring Security WebFlux Test. `mockJwt()` vẫn **không verify JWS signature**. Hãy bổ sung integration tests với real `ReactiveJwtDecoder` hoặc IdP/JWKS sandbox và case issuer/audience/key/exp sai.

### 12.3 Principal type khác nhau

`@WithMockUser` thông thường tạo `UsernamePasswordAuthenticationToken` và principal kiểu Spring Security `User`, **không** phải `JwtAuthenticationToken` hoặc custom principal application-specific.

Nếu production code ép cast principal thành JwtAuthenticationToken, dùng `mockJwt()` hoặc real token integration tests; `@WithMockUser` có thể làm test lỗi `ClassCastException` dù policy thực vận hành đúng. Nên tối thiểu hóa coupling với auth implementation class và dùng verified claims/service layer phù hợp.

## 13. WebTestClient in-memory và real server không giống nhau

`WebTestClient.bindToApplicationContext(context)` chạy qua WebFlux application context trong cùng test process. `mockUser()` và `@WithMockUser` có thể tham gia Spring Security Test integration.

Khi ứng dụng khởi động với:

```java
@SpringBootTest(
    webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT
)
```

và request đi qua **HTTP socket thật**, test security context trong test thread **không thể tự truyền qua network** thành danh tính của server. Trong E2E/remote HTTP test, gửi Basic/Bearer/session credentials thật, không kỳ vọng `mockUser()` giả lập identity từ phía client qua mạng.

Điều này **không** có nghĩa `@WithMockUser` vô dụng cho integration tests: nó rất hữu ích ở **in-memory WebFlux integration**. Chỉ cần hiểu giới hạn giữa local mock security state và credential qua network boundary.

## 14. Test isolation, tránh nhiễm security context

Một lỗi thường gặp là gắn `@WithMockUser` trên toàn class rồi viết:

```java
@Test
void noAuthorizationHeaderShouldGet401() {
    client.get().uri("/me")
        .exchange()
        .expectStatus().isUnauthorized();
}
```

Nếu class đã có mock user, test này có thể nhận 200 dù không gửi Authorization header. Cách sửa: dùng `@WithAnonymousUser` cho method ấy, hoặc để class anonymous mặc định rồi thêm `@WithMockUser` chỉ cho những test cần.

Đừng mutate trực tiếp một field `client` rồi dùng lại qua nhiều tests theo thứ tự; tạo WebTestClient mới trong `@BeforeEach` và dùng biến local:

```java
var asUser = client.mutateWith(
    mockUser("alice").roles("USER")
);

var asAdmin = client.mutateWith(
    mockUser("bob").roles("ADMIN")
);
```

Sau đó kiểm từng client riêng. Không dùng `@TestMethodOrder` để che state leakage. Mục tiêu là mỗi test có preconditions rõ ràng, chạy độc lập và chạy song song không ngẫu nhiên mất context.

## 15. Bảng lỗi phổ biến

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| @WithMockUser không có tác dụng với WebTestClient | Thiếu springSecurity() hoặc TestContext listeners | Bind application context và apply springSecurity |
| mockUser() không compile | Import nhầm MockMvc user() | Import SecurityMockServerConfigurers.mockUser |
| Username user mock pass dù không có trong DB | Mock bypass credential verification | Đúng mục đích; thêm real password test |
| @WithMockUser(roles="ROLE_ADMIN") lỗi | roles tự thêm prefix | Dùng roles="ADMIN" |
| Có scope nhưng test reports 403 | Dùng roles thay exact SCOPE authority | authorities="SCOPE_reports.read" |
| Anonymous test nhận 200 | Class-level mock user hoặc client mutated | @WithAnonymousUser hoặc test class riêng |
| Anonymous test nhận 302 | Form login được bật | Kiểm entrypoint, đừng luôn ép 401 |
| POST đúng role vẫn 403 | CSRF token thiếu | mutateWith(csrf()), giữ CSRF policy |
| Có csrf vẫn 403 | Thiếu authority ở HTTP/service | Kiểm @PreAuthorize/hasRole |
| @PreAuthorize không chạy | Tạo service bằng new, thiếu EnableReactiveMethodSecurity | Autowire proxied service |
| StepVerifier không thấy Authentication | Reactor Context/TestExecutionListener thiếu | Kiểm ReactorContextTestExecutionListener |
| GET protected 200 dù không gửi header | Mock identity/session đang tồn tại | Kiểm scope annotation/client |
| Basic sai vẫn test 200 | Đã mock user trong test | Tách real Basic integration test |
| JWT test mock pass, server thật 401 | Mock không verify signature/issuer | Test real ReactiveJwtDecoder và signed tokens |
| ClassCastException với JwtAuthenticationToken | WithMockUser tạo username/password token | mockJwt hoặc real JWT |
| Test RANDOM_PORT không nhận mock identity | Test context không truyền qua HTTP | Gửi real credentials |
| BindToController test pass khi security sai | Không qua security filters | BindToApplicationContext + springSecurity |
| AnonymousAuthenticationToken có isAuthenticated true | Hiểu sai authentication object semantics | Dùng authorization expressions chính thức |
| CSRF test bị trộn với auth test | Thiếu CSRF token trên unsafe method | Dùng GET để cô lập authentication hoặc thêm csrf |
| Mọi test đều ADMIN | Chỉ kiểm happy path | Thêm anonymous, USER, thiếu scope/CSRF |
| Role USER truy cập tenant khác | HTTP role không thay object authorization | Thêm domain ACL tests |
| User giả bị lộ sang test khác | Dùng lại mutated client field | Tạo per-test local clients |
| Security test thiếu dependency | spring-security-test không có | Bổ sung testImplementation |
| WebFlux test đang dùng MockMvc | Nhầm stack Servlet/Reactive | WebTestClient, ServerHttpSecurity |

## 16. Chiến lược kiểm thử đa tầng

**Tầng A — HTTP authorization bằng mock identities**

Dùng `@WithMockUser`, `mockUser()` và `@WithAnonymousUser` để test:
- Public vs protected;
- 200/401/403 theo role/scope;
- Scope không tương đương role;
- CSRF positive/negative;
- Không có state leak giữa tests.

**Tầng B — Authentication filter thật**

Dùng Basic credentials hoặc Bearer token thật trong WebTestClient:
- Password đúng/sai;
- Malformed Authorization header;
- JWT issuer/audience/expiry/signature sai;
- Opaque token active true/false;
- Session login/logout/cookie khi app có.

**Tầng C — Reactive method security**

Dùng `StepVerifier` với Spring-managed service:
- EDITOR được approve;
- USER/anonymous bị từ chối;
- Domain ACL và tenant ownership;
- Reactor Context propagation khi flatMap/parallel/deferred operations.

**Tầng D — E2E**

Dùng real server/socket để test:
- TLS/headers/gateway;
- Reverse proxy, CORS, CSRF;
- Cookie/session boundaries;
- Token revocation, key rotation, auth provider outage;
- Real status/challenge body theo API contract.

Mock identity giúp tests nhanh, ổn định và chỉ rõ authorization intent, nhưng không thay thế authentication integration.

## 17. Checklist trước khi merge

- [ ] Spring Boot application thật dùng WebFlux và SecurityWebFilterChain.
- [ ] Test dependency có spring-security-test và reactor-test.
- [ ] WebTestClient dùng bindToApplicationContext(context).apply(springSecurity()).
- [ ] Test anonymous public endpoint → 200.
- [ ] Test anonymous protected endpoint → 401 theo Basic entrypoint demo.
- [ ] Nếu class-level @WithMockUser, có @WithAnonymousUser override cho negative cases.
- [ ] Hiểu default @WithMockUser tạo user/ROLE_USER.
- [ ] Dùng roles="ADMIN" với hasRole("ADMIN"), không roles="ROLE_ADMIN".
- [ ] Dùng authorities="SCOPE_reports.read" với hasAuthority(...).
- [ ] Có tests đủ role/scope → 200 và thiếu role/scope → 403.
- [ ] Có test với nhiều mock users qua client.mutateWith(mockUser(...)).
- [ ] Client gốc không bị mutate vĩnh viễn hoặc rò state.
- [ ] Với POST, có CSRF thiếu/đúng và kiểm riêng quyền trong method.
- [ ] Không disable CSRF chỉ vì test dùng mock user bị 403.
- [ ] @EnableReactiveMethodSecurity bật, service được Spring-managed.
- [ ] StepVerifier test @PreAuthorize có cả success/error.
- [ ] Có test password Basic thật khi app hỗ trợ Basic.
- [ ] Nếu có Bearer JWT/opaque, có integration tests verify thật.
- [ ] Không coi mockJwt/mockOpaqueToken là test cryptographic verification.
- [ ] Không ép @WithMockUser truyền qua RANDOM_PORT network.
- [ ] Không tin AnonymousAuthenticationToken.isAuthenticated() là user authenticated.
- [ ] Không dùng MockMvc post processors trong WebFlux.
- [ ] Test negative cases có thể chạy độc lập và không phụ thuộc thứ tự.
- [ ] Không commit password/token thật trong test source hay logs.

## 18. Tự kiểm tra

**1. @WithMockUser có kiểm username/password không?** Không, nó tạo Authentication giả.

**2. Username và quyền mặc định của @WithMockUser?** `user` và `ROLE_USER`.

**3. Sự khác nhau của roles và authorities?** `roles` thêm ROLE_ prefix; `authorities` dùng exact string.

**4. HasAuthority("SCOPE_reports.read") cần cấu hình gì?** `@WithMockUser(authorities="SCOPE_reports.read")` hoặc `mockUser().authorities(new SimpleGrantedAuthority(...))`.

**5. mockUser khác @WithMockUser thế nào?** Một cái là WebTestClient mutator, một cái là annotation theo lifecycle test.

**6. Khi nào @WithAnonymousUser đặc biệt hữu ích?** Khi cần override class-level mock user.

**7. Tại sao không gửi Authorization header mà vẫn nhận 200?** Có thể do @WithMockUser hoặc mutated WebTestClient đã cung cấp Authentication.

**8. Khi nào protected anonymous thường nhận 401?** Với HTTP Basic/Bearer entrypoint cho API không có user hợp lệ.

**9. Vì sao USER vào admin bị 403?** Đã authenticated nhưng thiếu ROLE_ADMIN.

**10. Vì sao POST editor không có csrf() bị 403?** Thiếu CSRF token, không phải thiếu role.

**11. Có csrf() thì USER tự thành EDITOR?** Không; CSRF không thay quyền từ @PreAuthorize.

**12. Test @PreAuthorize nên lấy service thế nào?** Autowire Spring-managed bean, không new trực tiếp.

**13. Method security reactive lấy identity từ đâu?** Reactor Context theo subscriber, Spring Security Test listener hỗ trợ.

**14. AnonymousAuthenticationToken.isAuthenticated() có thể true?** Có; authorization expressions phân biệt anonymous.

**15. Mock user có thể thay JWT signed token integration test?** Không. Nó không verify signature/issuer/audience/exp.

**16. Vì sao WebTestClient RANDOM_PORT không dùng mockUser như in-memory?** Mock SecurityContext test không truyền qua network.

**17. Nhầm WebTestClient với MockMvc có hại gì?** Import DSL và test processors sai stack, security filters có thể không chạy.

**18. Tại sao cần test cả 401 và 403?** Để phân biệt chưa xác thực với đã xác thực nhưng thiếu quyền, và phát hiện authorization bypass.

## 19. Tổng kết

- **`@WithMockUser`** tạo user giả trong một test method/class; mặc định `user` + `ROLE_USER`.
- **`mockUser()`** gắn Authentication giả thông qua WebTestClient mutator cho client/request; rất phù hợp test nhiều identities.
- **`@WithAnonymousUser`** giúp kiểm anonymous và override mock user trên class.
- **`springSecurity()`** phải được áp dụng trong setup WebTestClient WebFlux thông thường.
- **`csrf()`** là điều kiện riêng khi test POST/unsafe HTTP methods với CSRF protection.
- **`@PreAuthorize` + `StepVerifier`** kiểm method security dựa trên Reactor Context.
- **Mock authorization tests ≠ real authentication tests**: cần bổ sung Basic/Bearer integration và negative cases.

**Hai điểm cần nhớ nhất:** Anonymous phải bị từ chối ở protected endpoints, và mock user có quyền không có nghĩa server đã kiểm credential thật. Hãy tổ chức tests có cả anonymous, đủ/thiếu quyền, CSRF và authentication filters thật.

### Nguồn tham khảo chính thức

- [Spring Security 6.5 — Testing Authentication (Reactive)](https://docs.spring.io/spring-security/reference/6.5/reactive/test/web/authentication.html)
- [Spring Security 6.5 — WebTestClient Security Setup](https://docs.spring.io/spring-security/reference/6.5/reactive/test/web/setup.html)
- [Spring Security 6.5 — Testing Reactive Method Security](https://docs.spring.io/spring-security/reference/6.5/reactive/test/method.html)
- [Spring Security 6.5 — Reactive Method Security](https://docs.spring.io/spring-security/reference/6.5/reactive/authorization/method.html)
- [Spring Security 6.5 — CSRF Protection in WebFlux](https://docs.spring.io/spring-security/reference/6.5/reactive/exploits/csrf.html)
- [Spring Security 6.5 — Reactive OAuth2 Test](https://docs.spring.io/spring-security/reference/6.5/reactive/test/web/oauth2.html)
- [Spring Security 6.5.x API — @WithMockUser](https://docs.spring.io/spring-security/site/docs/6.5.x/api/org/springframework/security/test/context/support/WithMockUser.html)
- [Spring Security 6.5.x API — @WithAnonymousUser](https://docs.spring.io/spring-security/site/docs/6.5.x/api/org/springframework/security/test/context/support/WithAnonymousUser.html)
