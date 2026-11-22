# Thiết lập WebTestClient với springSecurity()

## 1. Bối cảnh, mục tiêu và phạm vi

Bài học thuộc phần **Kiểm thử HTTP** của khóa **Spring Security - reactive**. Spring WebFlux xử lý HTTP theo mô hình reactive, còn Spring Security áp các quy tắc bảo mật thông qua **`SecurityWebFilterChain`**, `AuthenticationWebFilter`, `AuthorizationWebFilter`, CSRF filter và Reactor Context. Khi kiểm thử một controller bảo vệ bằng authentication, authorization hoặc CSRF, **`WebTestClient` phải được gắn đúng security test support**; nếu không, bài test có thể kiểm tra được controller mà không hề đi qua các filters và cho kết quả sai lệch với ứng dụng thực tế.

Spring Security cung cấp configurer **`SecurityMockServerConfigurers.springSecurity()`** để tích hợp với `WebTestClient` ở chế độ **mock server / in-memory**. Mẫu quan trọng nhất:

```java
WebTestClient client = WebTestClient
        .bindToApplicationContext(applicationContext)
        .apply(springSecurity())
        .configureClient()
        .build();
```

Đây là **fragment setup**, giả định đã import `springSecurity()` và có `ApplicationContext` chứa WebFlux configuration cùng `SecurityWebFilterChain`. Nó là khởi điểm cho các mutators như `mockUser()`, `csrf()`, `mockJwt()` hay `mockOidcLogin()`.

Mục tiêu học tập:

1. Hiểu **`springSecurity()` làm gì** và phân biệt nó với việc chỉ khởi tạo một `WebTestClient` thông thường.
2. Thiết lập đúng **Gradle dependencies**, `@SpringBootTest`, `WebTestClient.bindToApplicationContext(...)`, `.apply(springSecurity())`, `.configureClient()` và `@BeforeEach`.
3. Viết ứng dụng mẫu **Java 17+, Spring Boot 3.3.5, Spring Security WebFlux 6.3.x** có routes công khai, route authenticated, route chỉ ADMIN và POST có CSRF.
4. Kiểm thử **401 (chưa xác thực)**, **403 (thiếu quyền/thiếu CSRF)**, **200 OK**, **201 Created**, **HTTP Basic đúng/sai mật khẩu**.
5. Hiểu sự khác nhau giữa `mockUser()` / `@WithMockUser` và gửi **HTTP Basic thật** trong cùng WebTestClient.
6. Dùng `csrf()` cho các unsafe HTTP methods khi Spring Security CSRF được bật; biết rằng `csrf()` là test support, không phải chứng minh quy trình lấy token ngoài browser đã hoạt động.
7. Phân biệt **mock in-memory WebTestClient** với **`bindToServer()` / RANDOM_PORT** và giới hạn của mutators dựa vào test server context.
8. Nhận ra các sai lầm phổ biến: nhầm `MockMvc` Servlet với WebFlux, đặt `.apply` sai vị trí, bỏ sót security filters, test mọi route với fake principal, hoặc disable CSRF chỉ để test xanh.
9. Có checklist, troubleshooting, bài tập và tài liệu chính thức để kiểm chứng bộ kiểm thử trong dự án thực.

**Phạm vi:** Đây là bài **thiết lập WebTestClient cùng Spring Security cho WebFlux**, không phải hướng dẫn dựng hệ thống OIDC/JWT server. Những ví dụ `mockJwt()`, `mockOAuth2Login()` hoặc `mockOidcLogin()` được trình bày như phần mở rộng và có ghi rõ giới hạn.

**Ghi chú phiên bản:** Spring Boot 3.3.5 được dùng làm mốc mã nguồn tương thích Java 17 và API Spring Security 6.3.x. Khi triển khai dự án production vào thời điểm mới hơn, dùng bản framework **còn được hỗ trợ và đã vá bảo mật**, đối chiếu release notes khi thay đổi API.

## 2. `WebTestClient` là gì?

`WebTestClient` trong `org.springframework.test.web.reactive.server.WebTestClient` là HTTP testing client của **Spring WebFlux**. Nó có cú pháp gần với `WebClient` nhưng cung cấp các assertions dành cho test:

```java
client.get().uri("/public")
        .exchange()
        .expectStatus().isOk()
        .expectBody(String.class)
        .isEqualTo("public-ok");
```

Các bước:

- `get()`: xây HTTP GET request.
- `uri("/public")`: chọn request URI.
- `exchange()`: gửi request tới mock WebFlux handler hoặc server thật, tùy binding.
- `expectStatus()`: xác nhận HTTP status.
- `expectHeader()`: kiểm tra response headers.
- `expectBody(...)`: xác nhận nội dung JSON/text/binary.
- `returnResult()` hoặc `returnResult(Class)`: lấy result để kiểm tra nâng cao khi thực sự cần.

### Ba chế độ binding thường gặp

| Cách tạo | Thực sự kiểm tra | Lưu ý security |
| --- | --- | --- |
| `bindToController(controller)` | Controller và infrastructure dựng cho test | Dễ **không có** production SecurityWebFilterChain; phải cấu hình filters rõ nếu muốn test security |
| `bindToApplicationContext(context)` | WebFlux stack và beans trong ApplicationContext, **không mở TCP port** | **Khuyến nghị cho `springSecurity()`** trong bài này |
| `bindToServer().baseUrl(...).build()` | Server đang lắng nghe TCP/HTTPS thực | Kiểm tra network behavior; **không dùng `mockUser()` kiểu in-memory để giả auth** |

**Điểm quan trọng:** `WebTestClient` là testing tool; nó không tự tạo security rules. Các rules thật xuất phát từ `SecurityWebFilterChain` trong Spring context. `springSecurity()` **không thay thế** việc bạn phải bật bảo mật và nạp đúng configuration.

### Tại sao không dùng MockMvc cho WebFlux?

`MockMvc`/`SecurityMockMvcRequestPostProcessors` là kiểm thử stack **Servlet/MVC**. Với WebFlux, sử dụng:
- `WebTestClient`;
- `SecurityMockServerConfigurers.springSecurity()`;
- `SecurityMockServerConfigurers.mockUser()`;
- `SecurityMockServerConfigurers.csrf()`.

Không copy `MockMvcRequestBuilders`/`SecurityMockMvcRequestPostProcessors.user(...)` rồi dùng với `WebTestClient`. Hai stack có class names và lifecycle khác nhau.

## 3. `springSecurity()` thật sự thiết lập gì?

Import đúng:

```java
import static org.springframework.security.test.web.reactive.server
        .SecurityMockServerConfigurers.springSecurity;
```

Dấu xuống dòng giữa package và class chỉ để hiển thị; trong các tệp Java hoàn chỉnh phần dưới sẽ dùng một import **một dòng**.

Theo Spring Security test API, `springSecurity()` chuẩn bị mock-server test support cho các bộ lọc và mutators. Khi gắn vào `WebTestClient.bindToApplicationContext(...)`, request đi qua **WebFlux handler với security filter chain từ ApplicationContext**, đồng thời có bộ phận test hỗ trợ inject `SecurityContext` cho các mutators/annotations.

Dòng thao tác cốt lõi:

```java
client = WebTestClient.bindToApplicationContext(context)
        .apply(springSecurity())
        .configureClient()
        .build();
```

Giải thích chính xác:

1. `bindToApplicationContext(context)` dựng mock WebFlux handler dựa trên beans/routes/filters từ context.
2. `apply(springSecurity())` gắn Spring Security test configurer **vào mock-server spec trước khi build**.
3. `configureClient()` chuyển sang giai đoạn cấu hình options cho client (base URL, headers, timeout hoặc filters phía client khi cần).
4. `build()` tạo `WebTestClient` dùng trong test methods.
5. `mutateWith(mockUser(...))` ở một request/client bản sao tạo một **authenticated test principal**, không cần password thật.
6. `mutateWith(csrf())` tạo điều kiện CSRF hợp lệ cho request test; không disable production CSRF.
7. `@WithMockUser` có thể tạo test security context qua Spring TestExecutionListeners khi test runner được tích hợp đúng.

**Không nhầm:** `springSecurity()` là **test configurer**; còn `mockUser()`/`csrf()` là **request/client mutators**. Bạn thường `apply(springSecurity())` một lần khi dựng in-memory test client và `mutateWith(...)` cho các request cần giả lập identity/CSRF.

### Những việc `springSecurity()` KHÔNG làm

- Không tự cấp một user/password thật trong ứng dụng.
- Không thay thế `@EnableWebFluxSecurity` hoặc `SecurityWebFilterChain`.
- Không bắt buộc route nào cũng authenticated: đó là việc của `authorizeExchange`.
- Không tự xác minh token giả được tạo bởi `mockJwt()`: JWT mock bypass cryptographic decoder theo thiết kế.
- Không tự chứng minh TLS, cookies của browser thật, reverse proxy, network timeouts, database persistence, external IdP hoặc CSRF token lifecycle end-to-end.
- Không biến một `bindToServer()` tới server TCP thành “mock-user in-memory”: test mutators cần mock-server binding.
- Không tự thêm CSRF token vào mọi POST; test phải chủ động chọn `csrf()` khi cần.

## 4. Kiến trúc request test

```text
JUnit 5 / SpringBootTest
        |
        v
Spring ApplicationContext
  ├── SecurityWebFilterChain
  ├── ReactiveUserDetailsService
  ├── Controller / Handler
  └── WebFlux WebFilters
        |
        v
WebTestClient.bindToApplicationContext(context)
        |
        +--> .apply(springSecurity())
        |
        v
WebTestClient (mock in-memory)
        |
        +-- GET /public            -> permitAll -> 200
        |
        +-- GET /me (anonymous)    -> authentication required -> 401
        |
        +-- GET /me + mockUser     -> mock authenticated -> 200
        |
        +-- GET /admin + USER     -> role mismatch -> 403
        |
        +-- GET /admin + ADMIN    -> hasRole ADMIN -> 200
        |
        +-- POST /notes + USER,
        |   no CSRF                 -> 403
        |
        +-- POST /notes + USER,
        |   csrf()                  -> 201
        |
        +-- GET /me + Basic header
            -> real ReactiveUserDetailsService/password verify
            -> 200 hoặc 401
```

Dù không mở cổng TCP, in-memory test vẫn có thể đi qua **Spring Security WebFilters thật**. Nhưng mock user **không đi qua password verification thật**. Cùng một test class có thể có:
- Authorization tests với `mockUser()`.
- Authentication integration tests với `Authorization: Basic ...`.
- CSRF rule tests với `csrf()`.

Nhờ tách hai loại assertions, bạn biết test nào đã thực sự kiểm tra thành phần nào.

## 5. Dự án mẫu Java 17 / Spring Boot 3.3.5 / Spring WebFlux

Mục tiêu tạo một dự án **nhỏ, tự đủ**, không cần database hoặc IdP bên ngoài. Có hai user test được cấu hình bằng BCrypt trong memory:
- `alice / alice-pass`: có role `USER`.
- `admin / admin-pass`: có role `ADMIN`.

Các routes:
- `GET /public`: công khai.
- `GET /me`: cần authenticated user.
- `GET /admin`: cần `ROLE_ADMIN`.
- `POST /notes`: cần `ROLE_USER` **và CSRF token hợp lệ**.
- Mọi request còn lại: `denyAll()`.

### 5.1. Cấu trúc dự án

```text
webflux-security-test-demo/
├── settings.gradle
├── build.gradle
└── src/
    ├── main/
    │   └── java/dev/example/httptests/
    │       ├── HttpTestsApplication.java
    │       ├── SecurityConfig.java
    │       └── DemoController.java
    └── test/
        └── java/dev/example/httptests/
            └── SecurityWebTestClientTests.java
```

Tất cả Java files có `package dev.example.httptests;` khớp đường dẫn. Không cần application.yml: Spring Boot mặc định chạy tại `localhost:8080` khi dùng `bootRun`, nhưng **`@SpringBootTest(webEnvironment = MOCK)` không mở server TCP**.

### 5.2. Gradle

`settings.gradle`:

```groovy
rootProject.name = 'webflux-security-test-demo'
```

`build.gradle`:

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.5'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'dev.example'
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

**Bắt buộc chú ý `spring-security-test`**:
- `spring-boot-starter-test` mang JUnit 5, Spring Test, WebTestClient tests và assertion support.
- `spring-security-test` cung cấp **`SecurityMockServerConfigurers.springSecurity()`, `mockUser()`, `csrf()`, `@WithMockUser`**.
- `reactor-test` hữu ích khi kiểm thử riêng `Mono`/`Flux` bằng `StepVerifier`, dù bài này chủ yếu dùng WebTestClient.
- Thiếu `spring-security-test` thường dẫn đến lỗi compile không tìm thấy `SecurityMockServerConfigurers`.
- Đừng thêm `spring-boot-starter-web` (Servlet/MVC starter) vào demo WebFlux thuần: Spring Boot thường ưu tiên MVC khi cả hai starters đều có mặt.
- Với Boot 3.3.5, quản lý Spring Security version theo Boot BOM, không tự chọn một version test jar không tương thích.

### 5.3. Application main

`src/main/java/dev/example/httptests/HttpTestsApplication.java`:

```java
package dev.example.httptests;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class HttpTestsApplication {
    public static void main(String[] args) {
        SpringApplication.run(HttpTestsApplication.class, args);
    }
}
```

Đây là main class để chạy ứng dụng; `@SpringBootTest` trong test sẽ tải cùng Spring application context.

### 5.4. Spring Security reactive configuration

`src/main/java/dev/example/httptests/SecurityConfig.java`:

```java
package dev.example.httptests;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.core.userdetails.MapReactiveUserDetailsService;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.web.server.SecurityWebFilterChain;
import org.springframework.http.HttpMethod;

@Configuration
@EnableWebFluxSecurity
public class SecurityConfig {

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    MapReactiveUserDetailsService userDetailsService(
            PasswordEncoder encoder) {

        return new MapReactiveUserDetailsService(
                User.withUsername("alice")
                        .password(encoder.encode("alice-pass"))
                        .roles("USER")
                        .build(),
                User.withUsername("admin")
                        .password(encoder.encode("admin-pass"))
                        .roles("ADMIN")
                        .build());
    }

    @Bean
    SecurityWebFilterChain securityWebFilterChain(
            ServerHttpSecurity http) {

        return http
                .authorizeExchange(exchanges -> exchanges
                        .pathMatchers(HttpMethod.GET, "/public")
                            .permitAll()
                        .pathMatchers(HttpMethod.GET, "/me")
                            .authenticated()
                        .pathMatchers(HttpMethod.GET, "/admin")
                            .hasRole("ADMIN")
                        .pathMatchers(HttpMethod.POST, "/notes")
                            .hasRole("USER")
                        .anyExchange().denyAll())
                .httpBasic(Customizer.withDefaults())
                .formLogin(form -> form.disable())
                // Cố ý KHÔNG disable CSRF.
                .build();
    }
}
```

**Phân tích:**
1. `@EnableWebFluxSecurity` và `ServerHttpSecurity` là cơ chế **WebFlux**, không phải Servlet `HttpSecurity`.
2. `MapReactiveUserDetailsService` chứa hai user test, password được BCrypt encode. Các password mẫu **chỉ dành cho local development**, không dùng ở production.
3. `hasRole("ADMIN")` tìm authority `ROLE_ADMIN`; `hasRole("USER")` tìm `ROLE_USER`. Đừng truyền chuỗi `ROLE_ADMIN` vào `hasRole(...)`: framework tự xử lý prefix.
4. `httpBasic(...)` cho phép kiểm thử credential **thật** với HTTP Basic, trả challenge/401 khi chưa xác thực thay vì redirect login page.
5. `formLogin(...disable())` tắt form login cho demo để status của HTTP tests rõ; nếu form login bật, unauthenticated route có thể redirect `302` thay vì `401`.
6. `csrf(...)` không được tắt: Spring Security WebFlux bảo vệ unsafe methods mặc định. `POST /notes` có thể bị **403 do CSRF**, dù authentication đã được mock thành công.
7. `anyExchange().denyAll()` là deny-by-default: các routes/methods không được khai báo sẽ không vô tình public.
8. Đừng hiểu HTTP Basic là phù hợp production qua HTTP không mã hóa: phải dùng HTTPS/TLS trong mạng thật.

### 5.5. WebFlux REST controller

`src/main/java/dev/example/httptests/DemoController.java`:

```java
package dev.example.httptests;

import java.security.Principal;
import java.util.Map;

import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RestController;

import reactor.core.publisher.Mono;

@RestController
public class DemoController {

    @GetMapping("/public")
    public Mono<String> publicInfo() {
        return Mono.just("public-ok");
    }

    @GetMapping("/me")
    public Mono<Map<String, String>> me(Principal principal) {
        return Mono.just(Map.of("username", principal.getName()));
    }

    @GetMapping("/admin")
    public Mono<String> adminPanel() {
        return Mono.just("admin-ok");
    }

    @PostMapping("/notes")
    public Mono<ResponseEntity<String>> createNote() {
        return Mono.just(
                ResponseEntity.status(HttpStatus.CREATED)
                        .body("created"));
    }
}
```

`Principal` của `/me` là authentication identity trong request hiện tại. Khi dùng `mockUser("alice")`, controller sẽ thấy test principal alice. Khi gửi HTTP Basic credentials thật, framework kiểm tra `ReactiveUserDetailsService` và controller thấy identity tương ứng.

Từ `@RestController` trở về `Mono<T>` là đúng hướng reactive; không gọi `block()` hoặc `subscribe()` trong controller.

## 6. Lớp kiểm thử hoàn chỉnh với `springSecurity()`

Đây là phần quan trọng nhất của bài. Chúng ta dùng **`@SpringBootTest(webEnvironment = MOCK)`** để có Spring ApplicationContext thực của ứng dụng nhưng **không chạy TCP server**. Test dựng thủ công `WebTestClient` từ context để thao tác `springSecurity()` được minh bạch.

Tệp `src/test/java/dev/example/httptests/SecurityWebTestClientTests.java`:

```java
package dev.example.httptests;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;

import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.ApplicationContext;
import org.springframework.test.web.reactive.server.WebTestClient;

import org.springframework.security.test.context.support.WithMockUser;

import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.csrf;
import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.mockUser;
import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.springSecurity;

@SpringBootTest(
        webEnvironment = SpringBootTest.WebEnvironment.MOCK)
class SecurityWebTestClientTests {

    @Autowired
    ApplicationContext context;

    private WebTestClient client;

    @BeforeEach
    void setUp() {
        client = WebTestClient
                .bindToApplicationContext(context)
                .apply(springSecurity())
                .configureClient()
                .build();
    }

    @Test
    void publicRouteAllowsAnonymous() {
        client.get().uri("/public")
                .exchange()
                .expectStatus().isOk()
                .expectBody(String.class)
                .isEqualTo("public-ok");
    }

    @Test
    void privateRouteRejectsAnonymous() {
        client.get().uri("/me")
                .exchange()
                .expectStatus().isUnauthorized();
    }

    @Test
    void mockUserCanAccessAuthenticatedRoute() {
        client.mutateWith(mockUser("alice").roles("USER"))
                .get().uri("/me")
                .exchange()
                .expectStatus().isOk()
                .expectBody()
                .jsonPath("$.username")
                .isEqualTo("alice");
    }

    @Test
    void mockUserWithoutAdminRoleIsForbidden() {
        client.mutateWith(mockUser("alice").roles("USER"))
                .get().uri("/admin")
                .exchange()
                .expectStatus().isForbidden();
    }

    @Test
    void mockAdminCanAccessAdminRoute() {
        client.mutateWith(mockUser("operator").roles("ADMIN"))
                .get().uri("/admin")
                .exchange()
                .expectStatus().isOk()
                .expectBody(String.class)
                .isEqualTo("admin-ok");
    }

    @Test
    @WithMockUser(username = "annotated-admin", roles = "ADMIN")
    void withMockUserAnnotationCanAccessAdminRoute() {
        client.get().uri("/admin")
                .exchange()
                .expectStatus().isOk()
                .expectBody(String.class)
                .isEqualTo("admin-ok");
    }

    @Test
    void postWithMockUserButNoCsrfIsForbidden() {
        client.mutateWith(mockUser("alice").roles("USER"))
                .post().uri("/notes")
                .exchange()
                .expectStatus().isForbidden();
    }

    @Test
    void postWithMockUserAndCsrfIsCreated() {
        client.mutateWith(mockUser("alice").roles("USER"))
                .mutateWith(csrf())
                .post().uri("/notes")
                .exchange()
                .expectStatus().isCreated()
                .expectBody(String.class)
                .isEqualTo("created");
    }

    @Test
    void csrfWithoutAuthenticationDoesNotGrantAccess() {
        client.mutateWith(csrf())
                .post().uri("/notes")
                .exchange()
                .expectStatus().isUnauthorized();
    }

    @Test
    void realBasicCredentialsAreAuthenticated() {
        client.get().uri("/me")
                .headers(h -> h.setBasicAuth(
                        "alice", "alice-pass"))
                .exchange()
                .expectStatus().isOk()
                .expectBody()
                .jsonPath("$.username")
                .isEqualTo("alice");
    }

    @Test
    void wrongBasicPasswordIsRejected() {
        client.get().uri("/me")
                .headers(h -> h.setBasicAuth(
                        "alice", "wrong-pass"))
                .exchange()
                .expectStatus().isUnauthorized();
    }

    @Test
    void unknownRouteIsDeniedToAuthenticatedUser() {
        client.mutateWith(mockUser("alice").roles("USER"))
                .get().uri("/internal-not-registered")
                .exchange()
                .expectStatus().isForbidden();
    }
}
```

### 6.1. Giải thích những dòng thiết lập bắt buộc

`@SpringBootTest(webEnvironment = MOCK)`:
- Tải Spring Boot application context cùng WebFlux security beans.
- Không tạo Netty listener/TCP port.
- Cho phép `bindToApplicationContext(context)` thực hiện **mock-server exchange** qua WebFlux.

`@Autowired ApplicationContext context`:
- Cấp đúng handler/filter beans cho test client.
- Giúp test kiểm thử **real application rules**, không chỉ một controller object dựng tay.

`WebTestClient.bindToApplicationContext(context)`:
- Xây test server handler từ context.
- Khác `bindToController(new DemoController())` không tự chắc chắn có đầy đủ production security filters.

`.apply(springSecurity())`:
- Cấu hình Spring Security test support để gắn với mock-server testing.
- Đặt **trước** `configureClient()` và `build()`.
- Không nên dùng `.mutateWith(springSecurity())`: `springSecurity()` là configurer ở giai đoạn setup, khác mutators của từng request.

`.configureClient()`:
- Chuyển sang builder client để tùy biến default headers, base URL, timeout hoặc filters.
- Trong ví dụ, không đặt Basic authentication mặc định cho client, vì như vậy sẽ vô tình biến test “anonymous” thành authenticated request.

### 6.2. Tại sao test method có thể dùng `mockUser()`?

Sau khi setup đúng:
- `client.mutateWith(mockUser("alice").roles("USER"))` xây một client/request variant có **SecurityContext test**, không cần password/record user thật.
- Spring Security authorization filters nhìn thấy authentication test này.
- Controller nhận principal `alice`.
- `roles("USER")` map sang `ROLE_USER`, nên route `/notes` có thể vượt qua role check.
- Nhưng **CSRF còn là lớp riêng**; POST không có `csrf()` vẫn 403.

**Giới hạn:** `mockUser("alice")` có thể giả lập một user **không tồn tại** trong `MapReactiveUserDetailsService` mà vẫn pass authorization. Test này **không chứng minh login/password validation** hoặc user store đang hoạt động.

### 6.3. Khi nào dùng `@WithMockUser`?

`@WithMockUser` thuộc `org.springframework.security.test.context.support.WithMockUser`, được Spring Security test dùng qua test context listeners. Ví dụ:

```java
@Test
@WithMockUser(username = "auditor", roles = "ADMIN")
void annotationExample() {
    client.get().uri("/admin")
            .exchange()
            .expectStatus().isOk();
}
```

**Ưu điểm:** ít lặp khi nhiều requests trong cùng test dùng một principal. Nó cũng hữu ích cho method security tests khi Spring Test tích hợp đúng.

**Nhược điểm:** authentication được cung cấp cho **toàn bộ method test**, nên khó đọc hơn khi muốn thử xen kẽ anonymous/user/admin trong cùng method. Với trường hợp cần isolation per request, thường chọn `client.mutateWith(mockUser(...))`.

**Chú ý:** Không dùng `@WithMockUser` để khẳng định mật khẩu, database login, JWT signature hoặc issuer validation được kiểm thử. Nó tiêm test Authentication chứ không gọi real login.

### 6.4. CSRF: vì sao phải có hai mutators?

Để POST /notes được chấp nhận, yêu cầu **hai điều kiện**:
- Authentication có `ROLE_USER`.
- CSRF token hợp lệ.

```java
client
        .mutateWith(mockUser("alice").roles("USER"))
        .mutateWith(csrf())
        .post().uri("/notes")
        .exchange()
        .expectStatus().isCreated();
```

Nếu chỉ mock user:

```java
client.mutateWith(mockUser("alice").roles("USER"))
        .post().uri("/notes")
        .exchange()
        .expectStatus().isForbidden();
```

Nếu chỉ csrf:

```java
client.mutateWith(csrf())
        .post().uri("/notes")
        .exchange()
        .expectStatus().isUnauthorized();
```

**Kết luận:** CSRF token **không chứng minh người dùng đã authenticated**; user login **không tự thay CSRF token**. Test phải phản ánh từng lớp bảo vệ thay vì tắt CSRF để POST thành công.

### 6.5. HTTP Basic: test credential thật

```java
client.get().uri("/me")
        .headers(headers ->
                headers.setBasicAuth("alice", "alice-pass"))
        .exchange()
        .expectStatus().isOk();
```

Request trên **không dùng `mockUser`**. Basic authentication filter thực hiện:
1. Đọc `Authorization: Basic ...`.
2. Trích username/password.
3. Gọi reactive authentication manager và `MapReactiveUserDetailsService`.
4. Đối chiếu BCrypt-encoded password bằng `PasswordEncoder`.
5. Đưa authenticated principal vào Reactor Context nếu đúng.
6. Route `/me` lấy principal và trả JSON.

Do đó test này kiểm tra **một đường authentication thực** trong in-memory Spring context, mạnh hơn test fake principal về mặt credential validation. Nó vẫn **không chứng minh TLS, reverse proxy, browser cookie hoặc network behavior** vì không mở socket.

Dùng HTTP Basic trên **HTTPS trong production**. Mật khẩu `alice-pass` và `admin-pass` trong demo chỉ là credentials học tập ở môi trường local.

## 7. Run và kiểm tra test report

Từ thư mục `webflux-security-test-demo`:

```bash
gradle test
```

Nếu có Gradle Wrapper:

```bash
./gradlew test
```

Windows:

```powershell
.\gradlew.bat test
```

**Kết quả dự kiến theo code:** 12 JUnit tests thành công. Đây là **kỳ vọng**, không phải tuyên bố Gradle đã được thực thi trong workspace này.

| Test | Status kỳ vọng | Hành vi xác minh |
| --- | --- | --- |
| Public GET anonymous | 200 | `permitAll` và controller |
| Private GET anonymous | 401 | Chưa có Authentication |
| GET /me + mockUser USER | 200 | Test SecurityContext được dùng |
| GET /admin + USER | 403 | Thiếu role ADMIN |
| GET /admin + ADMIN | 200 | Đủ role ADMIN |
| GET /admin + `@WithMockUser` ADMIN | 200 | Annotation-based test context |
| POST /notes + USER, no csrf | 403 | CSRF enabled |
| POST /notes + USER + csrf() | 201 | Auth + CSRF + controller |
| POST /notes + csrf(), anonymous | 401 | CSRF không thay auth |
| GET /me + Basic đúng | 200 | Real password verification |
| GET /me + Basic sai | 401 | Authentication failure |
| GET unknown route + authenticated USER | 403 | Deny-by-default |

**Lưu ý:** Một test `expectStatus().isUnauthorized()` có thể là đúng do HTTP Basic entry point đã cấu hình; nếu bạn bật form login thay vào đó, một số request anonymous có thể trả `302` tới trang login. Trước khi thay assertions, cần xác định UX/security config mà API thực tế mong muốn.

### 7.1. Chạy ứng dụng qua HTTP thật để so sánh

Ngoài in-memory tests, bạn có thể chạy:

```bash
gradle bootRun
```

Sau đó từ terminal local:

```bash
curl -i http://localhost:8080/public

curl -i http://localhost:8080/me

curl -i --user alice http://localhost:8080/me

curl -i --user alice http://localhost:8080/admin
```

`curl --user alice` có thể hỏi password tương tác, tránh ghi password trực tiếp trong shell history. Dự kiến:
- `/public` → 200.
- `/me` không auth → 401.
- `/me` auth alice đúng password → 200.
- `/admin` auth alice → 403.

Đây là HTTP qua socket **khác** test `bindToApplicationContext`. Trong môi trường production, phải dùng HTTPS/TLS (và có certificate validation), không gửi Basic credentials qua HTTP công khai.

## 8. In-memory WebTestClient và live-server khác nhau thế nào?

### 8.1. In-memory: khuyến nghị khi học `springSecurity()`

```java
WebTestClient client = WebTestClient
        .bindToApplicationContext(context)
        .apply(springSecurity())
        .configureClient()
        .build();
```

**Có:** ApplicationContext, WebFlux WebFilters, Reactor Context, Spring Security test mutators, controller, route authorization, CSRF rules.

**Không:** TCP/Netty server thật, TLS handshake, reverse proxy, network timeouts, DNS/load balancer, browser behavior.

Rất phù hợp cho các quy tắc **Spring Security WebFlux** vì nhanh, tách biệt và không cần mở cổng.

### 8.2. Live server: kiểm tra giao tiếp HTTP thực

```java
WebTestClient live = WebTestClient
        .bindToServer()
        .baseUrl("http://localhost:8080")
        .build();

live.get().uri("/me")
        .headers(headers ->
                headers.setBasicAuth("alice", "alice-pass"))
        .exchange()
        .expectStatus().isOk();
```

Đây là fragment giả định ứng dụng đang chạy ở port 8080. `bindToServer()` mở HTTP connection thực. **Không áp `springSecurity()` lên live-client để sử dụng `mockUser()`**: mock auth/CSRF mutators của Spring Security test dùng mock-server filters và không được gửi qua HTTP như một credential protocol thật.

### 8.3. `@SpringBootTest(RANDOM_PORT)`

Một mô hình E2E/integration:

```java
@SpringBootTest(
        webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
@AutoConfigureWebTestClient
class LiveHttpTests {
    @Autowired
    WebTestClient client;

    @Test
    void basicAuthenticationWorksOverRealHttp() {
        client.get().uri("/me")
                .headers(headers ->
                        headers.setBasicAuth("alice", "alice-pass"))
                .exchange()
                .expectStatus().isOk();
    }
}
```

Đây là **fragment lớp test** bổ sung; cần imports của JUnit/Spring Boot, và sử dụng đúng HTTP stack. Trong trường hợp này Spring Boot tự chuẩn bị WebTestClient với server port đang chạy. Test nên gửi **credentials thật**, cookie/CSRF token thực hoặc bearer JWT được ký thật tùy application.

**Không nhầm các mode:**

| Mục tiêu | Kiểu test hợp lý |
| --- | --- |
| Route authz theo ROLE_USER/ROLE_ADMIN | In-memory + `springSecurity()` + `mockUser()` |
| CSRF enabled trên POST | In-memory + `springSecurity()` + `csrf()` |
| PasswordEncoder + ReactiveUserDetailsService | In-memory + HTTP Basic thật |
| Login cookie/session/redirect qua HTTP thật | RANDOM_PORT + HTTP client/browser |
| OAuth2/OIDC redirect tới external IdP | Contract/E2E với IdP test |
| JWT cryptographic signature, issuer và audience | Signed test JWT + decoder thật |
| Reverse proxy, TLS, CORS browser preflight | Deployment E2E |

## 9. Các cách thiết lập khác và trade-offs

### 9.1. `@AutoConfigureWebTestClient` trong Spring Boot

Khi dùng Spring Boot test, `@AutoConfigureWebTestClient` có thể inject một WebTestClient đã tích hợp với test infrastructure của Boot:

```java
@SpringBootTest(
        webEnvironment = SpringBootTest.WebEnvironment.MOCK)
@AutoConfigureWebTestClient
class AutoClientExample {
    @Autowired
    WebTestClient client;
}
```

Tuy nhiên, **cấu hình có thể phụ thuộc test slice/auto-configuration**, nên khi đang học chính xác `springSecurity()`, mẫu thủ công `bindToApplicationContext(context).apply(springSecurity())` minh bạch hơn. Không tự `.apply(springSecurity())` hai lần lên một test client đã được Boot config trước khi hiểu test setup.

Nếu `@WebFluxTest` chỉ nạp controller slice, cần bảo đảm security config/filter beans cần test thực sự có mặt. Một controller-only slice có thể thiếu các authentication dependencies bạn mong muốn.

### 9.2. `bindToController(...)`

`WebTestClient.bindToController(new DemoController())` có ích cho test controller độc lập. Nhưng nó **không tự chứng minh** `SecurityWebFilterChain` production đang bảo vệ route. Ngay cả khi áp một mock configurer, cần cung cấp đúng security filters/context; nếu không, test controller có thể pass vì bỏ qua security.

**Khi mục tiêu đề bài là “thiết lập WebTestClient với springSecurity()”**, hãy ưu tiên **bind application context có security chain thật**.

### 9.3. Test theo annotation hay mutation?

`@WithMockUser`:
- Gọn với cùng identity trong cả method test.
- Dễ viết method security tests.
- Cần Spring Security TestExecutionListeners/JUnit Spring integration đúng.

`mockUser()`:
- Rõ identity của từng request.
- Thích hợp kiểm thử anonymous, user, admin xen kẽ.
- Không thay đổi password DB; principal là giả.
- `mutateWith(...)` tạo client variant, tránh đặt mock auth mặc định cho toàn suite.

`mockAuthentication(...)`:
- Dùng khi cần custom `Authentication` loại khác UsernamePasswordAuthenticationToken.
- Nhưng chỉ nên tạo authenticated token khi mục tiêu là test **authorization**, không phải authentication manager.

### 9.4. Mở rộng sang OAuth2/JWT

Nếu ứng dụng có OAuth2 Resource Server JWT, thêm dependency thích hợp:

```groovy
implementation 'org.springframework.boot:spring-boot-starter-oauth2-resource-server'
```

Sau đó có thể dùng:

```java
client.mutateWith(mockJwt()
        .jwt(jwt -> jwt
                .subject("partner-01")
                .claim("scope", "reports:read")))
        .get().uri("/api/reports")
        .exchange();
```

Đây là **fragment dành cho ứng dụng có resource-server JWT config**, không phải mã chạy trong dự án HTTP Basic phần 5. Import static `SecurityMockServerConfigurers.mockJwt` khi sử dụng.

**Cảnh báo:** `mockJwt()` tạo một principal test đã authenticated và có authorities do test định nghĩa. Nó **không kiểm chứng JWT signature, issuer, audience, `exp`, `nbf`, JWK rotation hoặc token revocation**. Không dùng mockJwt làm bằng chứng Resource Server decoder an toàn.

Tương tự:
- `mockOAuth2Login()`: giả Oauth2 Login Authentication.
- `mockOidcLogin()`: giả OIDC user/session context.
- `mockOpaqueToken()`: giả BearerTokenAuthentication và claims.
- `mockAuthentication(...)`: đưa authentication test tuỳ chỉnh.

Tất cả dùng để **kiểm tra authorization/controller behavior**; authentication/login/token verification thật cần integration tests riêng.

### 9.5. Reactive method security

Nếu ứng dụng bật `@EnableReactiveMethodSecurity` và service trả `Mono`/`Flux`, Spring Security dùng Reactor Context để đưa Authentication tới method authorization. Với in-memory WebTestClient + `springSecurity()` + `mockUser()`, bạn có thể kiểm tra quyền ở cả HTTP route và `@PreAuthorize` khi bean/service được Spring proxy đúng.

Ví dụ fragment method security (không nằm trong app mẫu):

```java
@PreAuthorize("hasAuthority('ROLE_ADMIN')")
public Mono<String> auditReport() {
    return Mono.just("secret-report");
}
```

Đây là **fragment trong một Spring bean** và chỉ hoạt động với reactive method security đã bật. Test phải dùng service bean do Spring quản lý; gọi new Service() trực tiếp sẽ bỏ qua AOP security proxy.

## 10. Kiểm tra CSRF đúng mức độ

Spring Security mặc định bảo vệ HTTP methods thay đổi state với CSRF khi dùng session/browser authentication. Các tests nên có ít nhất:

| Request | Auth | CSRF | Kết quả kỳ vọng |
| --- | --- | --- | --- |
| GET /public | Không | Không cần | 200 |
| GET /me | Không | Không cần | 401 |
| POST /notes | USER | Thiếu | 403 |
| POST /notes | USER | `csrf()` | 201 |
| POST /notes | Không | `csrf()` | 401 |
| POST /notes | ADMIN | `csrf()` | 403 vì không có ROLE_USER trong demo |

**Tại sao dùng `csrf()` ở in-memory test?** Nó giúp dựng request có token hợp lệ cho CSRF kiểm tra. Khi muốn test **quy trình lấy token từ trang/form/cookie thực**, phải thực hiện chuỗi request đúng session qua server và kiểm tra CSRF token repository thật; `csrf()` **không thay** browser E2E.

**Không sửa lỗi 403 bằng `csrf.disable()`** trong production code chỉ để test POST pass. Hãy xem đang thiếu token hay thiếu role, sau đó chọn test scenario chính xác.

### CSRF và API stateless Bearer token

Nếu một resource server chỉ nhận `Authorization: Bearer` header từ machine clients và không có browser cookie authentication tự động, ứng dụng có thể thiết kế tắt CSRF sau threat-model review. Khi đó test POST với `csrf()` không còn là bằng chứng có giá trị vì filter đã bị tắt.

Nếu ứng dụng dùng form login/WebSession cookies, thường phải giữ CSRF và test đúng session. Khi nhiều security chains, CSRF rules có thể khác theo path; tests nên bao phủ đúng chain, không gán một giả định cho mọi endpoint.

## 11. Phát hiện “test xanh giả”

### 11.1. Chỉ test controller, bỏ security filters

Anti-pattern:

```java
WebTestClient client = WebTestClient
        .bindToController(new DemoController())
        .build();

client.get().uri("/public")
        .exchange()
        .expectStatus().isOk();
```

Bài test trên có thể đúng cho `/public`, nhưng **không chứng minh `/me` được bảo vệ**. Hãy thêm case anonymous `/me` phải 401 qua context có SecurityWebFilterChain.

### 11.2. Mock user trong mọi test

Anti-pattern:

```java
// Nếu client mặc định luôn có ADMIN, test anonymous không còn ý nghĩa.
WebTestClient adminClient = client
        .mutateWith(mockUser("root").roles("ADMIN"));
```

Đây là một cấu hình **không sai về API** nhưng sai khi dùng làm client duy nhất của cả suite. Một missing-auth test phải thực sự **không có authentication mutator/credentials**, không nhận ADMIN qua default test setup.

### 11.3. Test mock chứng minh sai điều gì?

| Test | Đã kiểm tra | Chưa kiểm tra |
| --- | --- | --- |
| `mockUser("alice")` → 200 | Authorization/context/controller | Password encoder, DB |
| `@WithMockUser(roles="ADMIN")` | Test context và role policy | Login, user disabled status |
| HTTP Basic thật → 200 | Converter/manager/users/password trong mock app | TLS/ingress/proxy |
| `mockJwt()` → 200 | Scope/claims mapping trong test mutator và authz | Signed JWT verification |
| `csrf()` → POST 201 | CSRF protection test path | Browser token issuance/lifecycle |
| RANDOM_PORT với Basic | HTTP server + credential handling | Production gateway/cert configuration |
| Browser E2E với session cookies | Redirect, cookies, CSRF flow | Security tại mọi backend nếu chưa test |

**Lưu ý:** Nếu ứng dụng có custom authentication logic, `mockUser()` có thể đi vòng qua logic đó. Muốn kiểm thử custom `ReactiveAuthenticationManager`/API key/token decoder, gửi credential **thật** đến filter trong test hoặc dùng signed-token fixture cùng real decoder.

### 11.4. Chỉ assert status mà không assert nội dung

Không nên chỉ:

```java
client.get().uri("/me").exchange()
        .expectStatus().isOk();
```

Nên kiểm tra thêm principal đúng:

```java
client.mutateWith(mockUser("alice"))
        .get().uri("/me")
        .exchange()
        .expectStatus().isOk()
        .expectBody()
        .jsonPath("$.username").isEqualTo("alice");
```

Khi role/tenant khác nhau, assert dữ liệu được phép, không chỉ status 200. Một request 200 trả nhầm dữ liệu của tenant khác vẫn là lỗi nghiêm trọng.

### 11.5. Dùng sleep/block để chờ reactive result

`WebTestClient.exchange()` và Reactor testing utilities đã tích hợp subscription/test lifecycle. Đừng thêm `Thread.sleep` để “đợi server”, hoặc gọi `block()` tùy ý trong controller/security code. Với custom `Mono`/`Flux` services, dùng `StepVerifier` hoặc WebTestClient streaming assertions phù hợp.

## 12. Danh sách lỗi thường gặp

| Hiện tượng | Nguyên nhân khả dĩ | Cách kiểm tra/sửa |
| --- | --- | --- |
| `springSecurity()` không resolve | Thiếu `spring-security-test` hoặc sai import | Thêm testImplementation đúng BOM, import reactive |
| Không có `WebTestClient` | Thiếu WebFlux/test dependencies | Thêm `starter-webflux` và `starter-test` |
| Test anonymous `/me` trả 200 | SecurityWebFilterChain chưa có, permitAll quá rộng hoặc mock principal còn sót | Bind đúng ApplicationContext + apply springSecurity; test không mutator |
| GET /me không auth trả 302 thay 401 | Form login entry point đang hoạt động | Nếu API muốn 401, cấu hình HTTP Basic/entry point rõ |
| POST với mockUser trả 403 | Chưa có CSRF | Thêm `mutateWith(csrf())` cho case thành công |
| POST có CSRF vẫn 403 | Thiếu ROLE_USER hoặc method matcher sai | Check authority prefix và route |
| POST có CSRF nhưng anonymous trả 401 | Hành vi đúng | CSRF không tạo Authentication |
| Basic đúng password nhưng 401 | UserDetailsService/encoder mismatch | Kiểm tra BCrypt, username, header |
| Basic sai password vẫn pass test | Đang dùng mockUser trong request | Dùng HTTP Basic thật, không mock |
| `@WithMockUser` không hoạt động | Thiếu Security TestExecutionListeners hoặc mock-server setup | Spring Test + security-test + apply springSecurity |
| `mockJwt()` không có | Thiếu spring-security-test hoặc wrong import | Add test jar và OAuth2 Resource Server config khi dùng |
| Spring Boot test khởi động Servlet | Thêm `starter-web` song song với WebFlux | Chỉ dùng WebFlux starter |
| `bindToServer()` không chấp nhận `mockUser()` | Mutator cần mock-server filter context | Dùng real HTTP credentials hoặc bindToApplicationContext |
| WebFlux test không thấy `@PreAuthorize` | Chưa bật reactive method security/proxy | `@EnableReactiveMethodSecurity` và Spring bean thật |
| Mock test pass nhưng production JWT fail | Test bypasses decoder | Signed JWT integration test |
| Test body JSON fail vì order khác | JSON object key order không cố định | Assert JSONPath/semantic JSON |
| `/unknown` trả 403 thay 404 | `denyAll` chặn trước router | Đó là security policy, assert tương ứng |
| Session cookie giữa tests làm lẫn principal | Client chia sẻ cookie/mutated state | Tạo fresh client per test, tách flows |
| Multi-chain rule không kích hoạt | Chain matcher/order sai | Test path/method với đúng filter chain |
| Security filter bị vô tình tắt trong slice | @WebFluxTest chỉ nạp một phần beans | Import exact security config, hoặc SpringBootTest |
| CORS OPTIONS trả 401 | CORS preflight chưa được xử lý trước security | Test/preconfigure CORS phù hợp browser case |
| Redirect test thiếu Location | Đang dùng Basic 401 hoặc entry point khác | Chọn đúng security config, assert header khi cần |
| Tests phụ thuộc database/IdP ngoài | Setup thiếu mocks/fixtures | Tách unit authz và integration credential tests |

## 13. Checklist chất lượng khi thiết lập WebTestClient

- [ ] Ứng dụng thực sự là **WebFlux** và có `SecurityWebFilterChain` đúng.
- [ ] `spring-security-test` đã thêm trong `testImplementation`.
- [ ] Import `SecurityMockServerConfigurers.springSecurity` là từ **reactive.server**, không phải MockMvc.
- [ ] Dùng `WebTestClient.bindToApplicationContext(context)` cho mock-server setup.
- [ ] Gọi `.apply(springSecurity())` trước `.configureClient().build()`.
- [ ] Client mặc định **không** chứa user ADMIN/Basic credentials nếu test cần anonymous.
- [ ] Có test route công khai 200 và route bảo vệ anonymous 401/redirect theo contract.
- [ ] Có test authenticated USER 200 và thiếu role ADMIN 403.
- [ ] Có test ADMIN 200 và denied-by-default route.
- [ ] Với unsafe method và CSRF enabled: test thiếu token 403, có `csrf()` thành công.
- [ ] Dùng `@WithMockUser` hoặc `mockUser()` đúng phạm vi; không coi chúng là password test.
- [ ] Có ít nhất một test **real credential flow** nếu mục tiêu gồm authentication.
- [ ] Không dùng mockJwt() để chứng minh JWT signature/issuer/audience đã verify.
- [ ] Nếu có OAuth2/OIDC, tách mocked authz test khỏi external IdP integration.
- [ ] Nếu dùng method security, test qua Spring-managed bean và Reactor Context.
- [ ] Không disable CSRF/filters vì test fail.
- [ ] Không làm lộ password, session cookie, bearer token, client secrets qua logs/test reports.
- [ ] Những test cần browser/network được tách sang RANDOM_PORT/proxy E2E.
- [ ] Assert cả HTTP status và body/headers quan trọng (principal, tenant, Location, challenge).
- [ ] Test 401 và 403 theo security entry point/config thật, không giả định mọi app luôn cùng status.
- [ ] Chạy toàn bộ tests sau khi thay `SecurityWebFilterChain` hoặc Boot/Spring Security version.
- [ ] Trên CI, test reports được lưu/audit nhưng không chứa credentials thật.

## 14. Câu hỏi tự kiểm tra

**1. `springSecurity()` được import từ đâu?**  
`org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.springSecurity`.

**2. Vì sao phải gọi `.apply(springSecurity())`?**  
Để gắn Spring Security mock-server test support vào `WebTestClient` và hỗ trợ các security mutators/test context cùng security filter chain.

**3. `bindToApplicationContext` khác `bindToServer` ở đâu?**  
Một bên kiểm thử in-memory bằng WebFlux context không mở TCP; bên kia gửi HTTP qua mạng đến server thực.

**4. `mockUser()` có kiểm tra password database không?**  
Không, nó tạo test Authentication.

**5. `@WithMockUser` phù hợp khi nào?**  
Khi một test method cần một principal giả qua Spring Test context integration.

**6. Test GET /me không auth nên trả gì trong mẫu này?**  
401 vì route cần authenticated và HTTP Basic entry point được bật, form login tắt.

**7. Vì sao GET /admin + USER trả 403?**  
USER đã authenticated nhưng không có `ROLE_ADMIN`.

**8. Vì sao POST /notes + mockUser vẫn trả 403 khi thiếu `csrf()`?**  
CSRF là rào chắn riêng cho state-changing requests.

**9. CSRF token có tự làm user authenticated không?**  
Không. Có CSRF mà không authentication vẫn bị 401 trong mẫu này.

**10. `mutateWith(csrf())` có chứng minh cookie/CSRF repository browser thực không?**  
Không; nó là test support trong mock-server mode.

**11. HTTP Basic thật trong test khác mockUser như thế nào?**  
Basic gọi authentication manager, reactive user details service và password encoder; mockUser bỏ qua các bước đó.

**12. `mockJwt()` có xác minh chữ ký không?**  
Không. Nó giả lập authenticated JWT principal.

**13. Vì sao không dùng `bindToController` làm bằng chứng security đã được áp?**  
Vì controller-only binding có thể không chứa production SecurityWebFilterChain.

**14. `hasRole("ADMIN")` kiểm tra authority nào?**  
`ROLE_ADMIN`.

**15. Có nên tắt CSRF để làm test POST pass không?**  
Không nếu ứng dụng thật cần CSRF; dùng `csrf()` cho test success và kiểm tra 403 cho thiếu token.

**16. Form login có thể thay đổi unauthenticated response như thế nào?**  
Có thể redirect 302 tới trang login thay vì HTTP Basic 401.

**17. `springSecurity()` có áp lên live `bindToServer()` giống mock client không?**  
Không dùng như vậy để tiêm fake user; live HTTP cần credentials/token thật.

**18. Khi bật reactive method security, Authentication được truyền thế nào?**  
Qua Reactor Context, không dựa vào ThreadLocal theo cách Servlet.

**19. Test mock ADMIN pass có nghĩa admin password còn đúng không?**  
Không. Muốn kiểm tra password phải test real authentication flow.

**20. Vì sao test anonymous nên dùng client mới không chứa mutators?**  
Để không vô tình carry over fake Authentication và tạo false-positive.

**21. Khi HTTP status 200 nhưng JSON trả sai tenant, test pass được không?**  
Không nên. Assert tenant/resource identity và các fields quan trọng.

**22. Test suite nào nên chạy trước khi triển khai production?**  
In-memory security policy tests, real credential/token tests, HTTP/TLS/proxy/browser E2E theo threat model, security regressions của Boot/Spring Security.

### Bài tập thực hành

1. Chạy `SecurityWebTestClientTests` và mô tả tại sao mỗi case 200/201/401/403 xảy ra.
2. Bỏ `.apply(springSecurity())` trên một nhánh học tập; quan sát các mock principal/CSRF tests và giải thích test support đã thiếu ở đâu.
3. Thay `/admin` thành `hasAuthority("ROLE_ADMIN")` và so sánh với `hasRole("ADMIN")`.
4. Viết thêm một test dùng `@WithMockUser(roles="USER")` để xác nhận route /admin bị 403.
5. Thêm JSON payload cho POST /notes và assert response body; giữ CSRF required.
6. Dùng `mockUser("bob")` không có trong MapReactiveUserDetailsService, xác nhận test /me vẫn có thể pass, rồi giải thích tại sao đó **không** là password validation test.
7. Test Basic password `wrong-pass` → 401, sau đó thay password encoder trong code và xác nhận real auth flow fail nếu hash không khớp.
8. Bật form login, thay expected unauthenticated status theo UX, kiểm tra Location redirect.
9. Thêm service annotated `@PreAuthorize` + `@EnableReactiveMethodSecurity` và test qua Spring proxy.
10. Viết `@WebFluxTest` controller slice với `@Import(SecurityConfig.class)` và các beans cần thiết; kiểm tra SecurityWebFilterChain thật sự có mặt.
11. Viết RANDOM_PORT test gửi Basic credentials thật qua socket, không dùng `mockUser()`.
12. Thêm OAuth2 Resource Server vào một project riêng, dùng `mockJwt()` để test scopes và signed JWT fixture để test decoder signature.
13. Viết CORS preflight test nếu app có cross-origin browser client, không đòi token/CSRF ở preflight.
14. Thêm protected route theo tenant, assert user A không thấy dữ liệu tenant B dù status/role trông hợp lệ.
15. Test timeout hoặc error propagation của một reactive authentication manager custom; không cho pass khi store unavailable.
16. Cấu hình bộ test không lưu raw credentials trong logs/CI reports.
17. So sánh SpringBootTest MOCK, RANDOM_PORT và WebFlux slice về tốc độ, mức wiring và coverage.
18. Thực hiện code review đảm bảo những routes mới không rơi vào `permitAll` hoặc bỏ filter chain.

## 15. Tài liệu chính thức

- [Spring Security — WebTestClient Security Setup](https://docs.spring.io/spring-security/reference/reactive/test/web/setup.html): `bindToApplicationContext(...).apply(springSecurity()).configureClient().build()`.
- [Spring Security — Testing Authentication (WebFlux)](https://docs.spring.io/spring-security/reference/reactive/test/web/authentication.html): `mockUser()` và `@WithMockUser`.
- [Spring Security — Testing CSRF (WebFlux)](https://docs.spring.io/spring-security/reference/reactive/test/web/csrf.html): `csrf()` mutator.
- [Spring Security — Testing OAuth2 (WebFlux)](https://docs.spring.io/spring-security/reference/reactive/test/web/oauth2.html): `mockJwt()`, `mockOAuth2Login()`, `mockOidcLogin()` và phạm vi authz tests.
- [Spring Security — WebFlux Security Configuration](https://docs.spring.io/spring-security/reference/reactive/configuration/webflux.html): `ServerHttpSecurity`, `SecurityWebFilterChain`.
- [Spring Security — Reactive CSRF](https://docs.spring.io/spring-security/reference/reactive/exploits/csrf.html): CSRF semantics với browser sessions.
- [Spring Security — Reactive Method Security](https://docs.spring.io/spring-security/reference/reactive/authorization/method.html): `@EnableReactiveMethodSecurity` và Reactor Context.
- [Spring Framework — WebTestClient](https://docs.spring.io/spring-framework/reference/testing/webtestclient.html): mock server và live server bindings, assertions.
- [Spring Boot — Testing Spring Boot Applications](https://docs.spring.io/spring-boot/3.3/reference/testing/spring-boot-applications.html): `@SpringBootTest`, `@AutoConfigureWebTestClient`, test slices.
- [Spring Security 6.3 — SecurityMockServerConfigurers](https://docs.spring.io/spring-security/site/docs/6.3.10/api/org/springframework/security/test/web/reactive/server/SecurityMockServerConfigurers.html): API test configurer.
- [JUnit 5 User Guide](https://junit.org/junit5/docs/current/user-guide/): `@BeforeEach`, `@Test` và test lifecycle.

**Ghi nhớ:** Để kiểm thử HTTP security trong **Spring WebFlux**, hãy dựng `WebTestClient.bindToApplicationContext(context).apply(springSecurity()).configureClient().build()`. Dùng `mockUser()` hoặc `@WithMockUser` cho **authorization scenarios**, `csrf()` khi test **POST/PUT/DELETE có CSRF**, và gửi **HTTP credentials thật** khi cần kiểm chứng authentication. **Mock pass không có nghĩa password, JWT signature, cookies, TLS hoặc IdP đã được test thật.** Luôn kiểm thử 200/201/401/403 theo cấu hình thực và không làm mất SecurityWebFilterChain trong test setup.