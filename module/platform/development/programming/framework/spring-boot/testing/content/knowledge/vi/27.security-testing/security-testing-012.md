# Kiểm thử bảo mật Reactive với WebTestClient và Reactor Context

## 1. Tại sao Reactive Security có cơ chế kiểm thử riêng?

Trong ứng dụng **Spring Boot WebFlux**, HTTP request đi qua chuỗi security WebFilters để xác thực người dùng và phân quyền, sau đó controller thường trả về một `Mono` hoặc `Flux`. Reactor có thể chuyển xử lý giữa các threads khi dùng `publishOn`, `subscribeOn` hoặc các publisher bất đồng bộ. Vì thế, cơ chế dựa hoàn toàn vào `ThreadLocal` quen thuộc của nhiều ứng dụng Servlet không phải mô hình thích hợp để suy luận identity ở mọi bước trong reactive chain.

Spring Security hỗ trợ **`ReactiveSecurityContextHolder`**. Nó cho phép lấy `SecurityContext` từ **Reactor Context của subscriber**. Identity không được lưu như một biến global dành cho tất cả các requests; nó được truyền theo phạm vi subscription tương ứng. Một ứng dụng có thể được kiểm thử ở nhiều cấp:

- **Request security:** anonymous bị từ chối, user có role phù hợp được vào, POST thiếu CSRF token bị chặn.
- **Method security:** method `@PreAuthorize` thật được Spring AOP proxy enforce dựa vào authentication trong Reactor Context.
- **Context propagation:** principal vẫn đúng khi một operator downstream được thực thi sau `publishOn`.
- **Authentication path:** HTTP Basic credentials hoặc JWT được xác minh bằng cơ chế thật, khác với việc cung cấp `Authentication` giả bằng `mockUser`.

Công cụ cần dùng đúng vai trò: **`WebTestClient` + `springSecurity()` + `mockUser()/csrf()`** cho WebFlux security request tests; **`StepVerifier` + `ReactiveSecurityContextHolder.withAuthentication(...)` + `contextWrite(...)`** cho tests publisher thuần.

Bài học theo **Java 17, Spring Boot 3.3.0, Spring Security 6.x, Reactor, JUnit Jupiter**; ví dụ code đầy đủ ở bên dưới. Versions này là baseline nhất quán để học, không phải khuyến nghị production mới nhất. **Không tuyên bố tests đã chạy**: expected results chỉ được xác nhận khi người học chạy Gradle trong môi trường phù hợp.

## 2. Bạn sẽ học được gì?

1. Giải thích sự khác biệt giữa `SecurityContextHolder` Servlet/ThreadLocal và `ReactiveSecurityContextHolder` Reactor Context.
2. Cấu hình `SecurityWebFilterChain` qua `ServerHttpSecurity` và bật `@EnableWebFluxSecurity`.
3. Bật `@EnableReactiveMethodSecurity` và kiểm tra `@PreAuthorize` trên bean trả `Mono`.
4. Thiết lập `WebTestClient.bindToApplicationContext(...).apply(springSecurity())`.
5. Dùng `mockUser(...).roles(...)` cho identity/authorization tests mà không giả vờ đã kiểm tra password.
6. Phân biệt HTTP 401, 403 và 200 trong security tests.
7. Dùng `csrf()` để tạo paired tests: đúng role thiếu token 403, có token 200.
8. Gửi HTTP Basic credentials thực để kiểm tra authentication filter/user details service.
9. Viết `StepVerifier` test cho context trên scheduler thread khác.
10. Chứng minh hai subscriptions không rò principal lẫn nhau.
11. Biết sự khác nhau giữa `@WebFluxTest`, `@SpringBootTest(MOCK)` và `RANDOM_PORT`.
12. Tránh các false positive do thiếu security filters, bị mock mất protected bean hoặc method self-invocation.
13. Biết `mockJwt` khác với việc kiểm tra JWT signature, issuer, audience và expiration thực.
14. Nhận diện lỗi bảo mật do `block()`, manual `subscribe()`, static mutable identity và untrusted role headers.
15. Tổ chức tests có cả positive và negative paths, không đoán trạng thái từ một status code không rõ nguyên nhân.

## 3. Sơ đồ request và context

```text
Client (WebTestClient)
       |
       v
WebFlux handler chain
       |
       +-- Authentication WebFilter
       +-- SecurityContext / CSRF / Authorization WebFilters
       |
       v
@RestController returns Mono/Flux
       |
       +-- Calls Spring-managed @Service proxy
       |       |
       |       +-- @PreAuthorize evaluated for reactive publisher
       |
       v
Reactor subscription
       |
       +-- ReactiveSecurityContextHolder.getContext()
       +-- Reactor Context tied to Subscriber
       +-- operators: map, flatMap, publishOn...
       |
       v
HTTP status / body
```

**Quan trọng:** tạo `Mono` là assembly; khi subscribe, các operators mới chạy và context được đọc. `ReactiveSecurityContextHolder.getContext()` trả `Mono<SecurityContext>`, không trả trực tiếp một global `SecurityContext` object bắt buộc tồn tại.

## 4. Authentication, authorization, CSRF và Reactor Context

| Cơ chế | Câu hỏi | Assertion có ý nghĩa |
| --- | --- | --- |
| Authentication | Ai đang gọi? Credentials có hợp lệ? | GET protected anonymous 401; Basic sai 401 |
| Authorization | User có quyền? | READER tới admin method 403, ADMIN 200 |
| CSRF | State-changing request có token phù hợp? | EDITOR POST không token 403; có token 200 |
| Method Security | Annotation có được enforce qua proxy? | @PreAuthorize denied/allowed |
| Reactor Context | Principal còn đúng sau async scheduler? | GET trả "async:alice"; StepVerifier trả "bob" |
| Context isolation | Authentication có rò giữa subscriptions? | alice, bob và anonymous tách biệt |
| JWT validation | Signature, issuer, audience, expiry? | Decoder với token được ký cho test |
| Deployment security | TLS, reverse proxy, IdP? | Test môi trường thực phù hợp |

Trong Spring Security WebFlux có HTTP Basic-only như demo, **unauthenticated GET** protected thường trả **401**, authenticated thiếu authority trả **403**. Nhưng nếu test **POST không có CSRF**, filter CSRF có thể trả **403** trước khi authentication entry point xử lý. Vì vậy không dùng POST thiếu CSRF làm bằng chứng duy nhất về 401.

### 4.1. ROLE_ prefix

`hasRole("ADMIN")` thông thường yêu cầu authority `ROLE_ADMIN`. `mockUser("alice").roles("ADMIN")` thêm authority đúng kiểu đó. `hasAuthority("REPORT_READ")` lại so trực tiếp authority name. Không nhầm role với scope, và không dùng `roles("ROLE_ADMIN")` khi builder đã tự thêm prefix.

### 4.2. Các dấu hiệu false positive

Test chỉ yêu cầu “anonymous bị 403/401” có thể pass khi cấu hình `denyAll` đã chặn mọi người. Test chỉ yêu cầu “ADMIN được 200” có thể pass khi method annotation đã bị gỡ. Vì vậy mỗi rule cần **cặp cho phép và từ chối**.

## 5. Chọn đúng chế độ WebTestClient

### 5.1. Bind-to-controller

```java
WebTestClient client =
        WebTestClient.bindToController(
                new ExampleController())
                .build();
```

Đây là **snippet minh họa** vì `ExampleController` không có trong project thực hành. Mode này chạy simulated WebFlux requests nhưng không tự bảo đảm `SecurityWebFilterChain` của application được nạp. Dùng cho controller-focused tests khi đã biết scope.

### 5.2. Bind-to-ApplicationContext

```java
WebTestClient client = WebTestClient
        .bindToApplicationContext(context)
        .apply(springSecurity())
        .configureClient()
        .build();
```

Code mẫu ở phần dưới dùng setup này. `springSecurity()` là helper từ `SecurityMockServerConfigurers` trong dependency `spring-security-test`. Nó tích hợp Spring Security test support, giúp mock WebFlux handler pipeline dùng security filters và các `mockUser`/`csrf` mutators. **Không mở HTTP TCP port**.

Nếu quên `.apply(springSecurity())` ở manual-bound client, security filters/test mutator có thể không hoạt động đúng với điều bạn nghĩ mình đang kiểm tra. Test nên có anonymous 401 và reader 403 để phát hiện thiếu filter chain.

### 5.3. SpringBootTest RANDOM_PORT

```java
@SpringBootTest(
        webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
@AutoConfigureWebTestClient
class LiveTest {
    @Autowired WebTestClient client;
}
```

Đây là khung cấu hình; phần sau có class runnable. Server thật được mở ở random port; client kết nối qua HTTP. **`mockUser` trong JUnit JVM không phải authentication object được truyền qua network** tới một remote server. Hãy gửi credentials/token thực sự qua request header/cookie khi kiểm tra authentication path.

### 5.4. @WebFluxTest vs @SpringBootTest

- `@WebFluxTest` tạo slice web-focused, không tự scan mọi `@Service`/repository; cần `@Import` hoặc mock collaborator có chủ đích.
- `@WebFluxTest` có thể không detect custom `SecurityWebFilterChain` configuration; import security config nếu muốn test rules thật.
- `@SpringBootTest` nạp full application context, thích hợp khi muốn test cả controller và method-security service bean thật.
- Trong Spring Boot 3.3, `@MockBean` có thể thay Spring bean; nếu mock chính secured service, bạn có thể bỏ qua method interceptor đang muốn test.
- Khi classpath có cả Spring MVC và WebFlux, Boot thường ưu tiên MVC; project này **chỉ** dùng starter WebFlux.

## 6. Reactor Context khác ThreadLocal

Trong Servlet, `SecurityContextHolder` thường dùng ThreadLocal theo request thread. Trong WebFlux, Reactor Context đi theo **subscriber**, nên các reactive operators có thể truy cập principal qua:

```java
ReactiveSecurityContextHolder.getContext()
        .map(SecurityContext::getAuthentication)
        .map(Authentication::getName)
```

Đây là expression snippet, không phải class độc lập. `getContext()` có thể hoàn tất rỗng nếu subscription không có security context.

### 6.1. contextWrite tại subscription time

```java
Authentication auth = new TestingAuthenticationToken(
        "alice", "unused", "ROLE_READER");

Mono<String> name =
        ReactiveSecurityContextHolder.getContext()
            .map(SecurityContext::getAuthentication)
            .map(Authentication::getName)
            .contextWrite(
                ReactiveSecurityContextHolder.withAuthentication(auth));
```

`TestingAuthenticationToken` cấp authentication giả dùng trong test. `contextWrite` tạo context biến thể cho upstream chain trong subscription, không lưu `alice` thành một global mutable field. Phần `ReactiveContextUnitTest` có đầy đủ imports/StepVerifier.

### 6.2. publishOn và subscribeOn

`publishOn(Schedulers.parallel())` có thể chuyển downstream work sang scheduler thread. `subscribeOn` ảnh hưởng cách subscription/upstream được schedule. Trong một Reactor chain được compose đúng, Reactor Context theo subscriber, nên `ReactiveSecurityContextHolder.getContext()` vẫn đọc được ở các operators thích hợp.

Không suy luận rằng **mọi** ThreadLocal của bạn cũng được truyền. Nếu app dùng `CompletableFuture.supplyAsync`/Executor hoặc callback ngoài Reactor, phải có context-propagation bridge phù hợp và test riêng.

### 6.3. FlatMap vs manual subscribe

```java
// Anti-pattern - detached subscription:
Mono.just("start").doOnNext(value -> {
    downstreamPublisher.subscribe();
});
```

`downstreamPublisher` là biến minh họa. Manual `subscribe()` có thể tách error/cancellation/backpressure/context của inner flow. Khi muốn compose, dùng `flatMap(value -> downstreamPublisher)` để inner publisher được gắn vào cùng reactive chain. Tránh `block()` trên Netty event loop để đọc username.

## 7. Full runnable lab — Java 17, Spring Boot 3.3.0

Cây thư mục:

```text
reactive-security-lab/
├── settings.gradle
├── build.gradle
└── src/
    ├── main/java/example/reactivesecurity/
    │   ├── ReactiveSecurityLabApplication.java
    │   ├── SecurityConfig.java
    │   ├── IdentityService.java
    │   ├── AuditService.java
    │   ├── NoteInput.java
    │   ├── NoteResult.java
    │   └── SecureController.java
    └── test/java/example/reactivesecurity/
        ├── SecurityWebTestClientTest.java
        ├── ReactiveContextUnitTest.java
        └── LiveBasicAuthTest.java
```

### 7.1. settings.gradle

```groovy
rootProject.name = 'reactive-security-lab'
```

### 7.2. build.gradle

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.0'
    id 'io.spring.dependency-management' version '1.1.5'
}

group = 'example'
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
    testRuntimeOnly 'org.junit.platform:junit-platform-launcher'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

Spring Boot BOM quản lý versions Framework, Security, Reactor và test dependencies tương thích với Boot 3.3. Không tự override sang Spring Security 7.x vì khác API/version requirements.

**Không có Spring MVC starter** trong lab để ứng dụng đi theo reactive WebFlux auto-configuration.

## 8. Main application

**src/main/java/example/reactivesecurity/ReactiveSecurityLabApplication.java**

```java
package example.reactivesecurity;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ReactiveSecurityLabApplication {
    public static void main(String[] args) {
        SpringApplication.run(
                ReactiveSecurityLabApplication.class, args);
    }
}
```

## 9. SecurityConfig: SecurityWebFilterChain và method security

**src/main/java/example/reactivesecurity/SecurityConfig.java**

```java
package example.reactivesecurity;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.method.configuration.EnableReactiveMethodSecurity;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.core.userdetails.MapReactiveUserDetailsService;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.web.server.SecurityWebFilterChain;

@Configuration(proxyBeanMethods = false)
@EnableWebFluxSecurity
@EnableReactiveMethodSecurity
public class SecurityConfig {

    @Bean
    SecurityWebFilterChain springSecurityFilterChain(
            ServerHttpSecurity http) {
        return http
                .authorizeExchange(exchanges -> exchanges
                        .pathMatchers(HttpMethod.GET, "/public")
                            .permitAll()
                        .pathMatchers(
                                HttpMethod.POST, "/api/notes")
                            .hasRole("EDITOR")
                        .pathMatchers("/api/**")
                            .authenticated()
                        .anyExchange()
                            .denyAll())
                .httpBasic(Customizer.withDefaults())
                .csrf(Customizer.withDefaults())
                .build();
    }

    @Bean
    MapReactiveUserDetailsService users() {
        UserDetails reader = User.withUsername("reader")
                .password("{noop}reader-pass")
                .roles("READER")
                .build();

        UserDetails editor = User.withUsername("editor")
                .password("{noop}editor-pass")
                .roles("EDITOR")
                .build();

        UserDetails admin = User.withUsername("admin")
                .password("{noop}admin-pass")
                .roles("ADMIN")
                .build();

        return new MapReactiveUserDetailsService(
                reader, editor, admin);
    }
}
```

### 9.1. Vì sao thiết kế URL rules như vậy?

- `GET /public` cho anonymous.
- `POST /api/notes` cần `ROLE_EDITOR` và CSRF trong cấu hình bài mẫu.
- `/api/**` còn lại chỉ cần authenticated.
- `GET /api/admin/audit` không được URL rule giới hạn ADMIN, **cố ý** để kiểm tra `@PreAuthorize` của service.
- `anyExchange().denyAll()` chặn paths chưa khai báo.
- `httpBasic` bật authentication dựa vào request credentials.
- `csrf` bật để test missing/present token.

### 9.2. Cảnh báo bảo mật về demo credentials

`{noop}` và password literals là **tài khoản giả dành cho lab local**. Production cần PasswordEncoder an toàn (BCrypt/Argon2 theo chính sách), secret management, TLS, user lifecycle và IdP phù hợp. Không copy cấu hình no-op password encoder vào dịch vụ public.

### 9.3. @EnableReactiveMethodSecurity

Annotation này kích hoạt reactive method-security AOP. Secured methods nên trả reactive publisher theo contract. Trong lab, `AuditService` là Spring-managed bean, `readAudit()` trả `Mono<String>`, controller gọi qua Spring proxy.

Không tự gọi `new AuditService()` rồi kỳ vọng annotation có hiệu lực; cũng tránh self-invocation từ method cùng bean bypass proxy.

## 10. IdentityService.java

**src/main/java/example/reactivesecurity/IdentityService.java**

```java
package example.reactivesecurity;

import org.springframework.security.core.context.ReactiveSecurityContextHolder;
import org.springframework.security.core.context.SecurityContext;
import org.springframework.stereotype.Service;
import reactor.core.publisher.Mono;

@Service
public class IdentityService {

    public Mono<String> currentUsername() {
        return ReactiveSecurityContextHolder.getContext()
                .map(SecurityContext::getAuthentication)
                .map(authentication -> authentication.getName());
    }
}
```

Class này không lưu username trong một singleton field. Mỗi HTTP subscription sẽ đọc Authentication đang gắn vào Reactor Context. Khi không có security context, publisher có thể complete rỗng; trong lab, `/api/**` yêu cầu authenticated nên đường WebFlux hợp lệ có context thích hợp.

Đừng dùng `SecurityContextHolder.getContext().getAuthentication()` trong WebFlux scheduler callback rồi giả định nó luôn là user của request.

## 11. AuditService.java và @PreAuthorize

**src/main/java/example/reactivesecurity/AuditService.java**

```java
package example.reactivesecurity;

import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.stereotype.Service;
import reactor.core.publisher.Mono;

@Service
public class AuditService {

    @PreAuthorize("hasRole('ADMIN')")
    public Mono<String> readAudit() {
        return Mono.defer(() -> Mono.just("audit-ok"));
    }
}
```

Method-level rule dùng `ROLE_ADMIN` từ Authentication trong Reactor Context. Khi READER đã authenticated nhưng gọi method qua proxy, Spring Security có thể từ chối với `AccessDeniedException` và WebFlux security error handling chuyển thành HTTP 403.

**Vì sao cần negative/positive pair?** Nếu annotation bị vô hiệu hóa, ADMIN vẫn nhận 200, nhưng READER cũng có thể được vào; test READER 403 bắt lỗi đó.

## 12. DTO classes

**src/main/java/example/reactivesecurity/NoteInput.java**

```java
package example.reactivesecurity;

public record NoteInput(String text) {}
```

**src/main/java/example/reactivesecurity/NoteResult.java**

```java
package example.reactivesecurity;

public record NoteResult(String text) {}
```

Demo chỉ echo text. Mục đích là thử CSRF/role/JSON binding, không cung cấp persistence hoặc business validation mẫu. Hệ thống thật phải thêm validations/authorization ở tài nguyên và dữ liệu nếu cần.

## 13. SecureController.java — Reactor Context sau publishOn

**src/main/java/example/reactivesecurity/SecureController.java**

```java
package example.reactivesecurity;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Mono;
import reactor.core.scheduler.Schedulers;

@RestController
public class SecureController {

    private final IdentityService identityService;
    private final AuditService auditService;

    public SecureController(
            IdentityService identityService,
            AuditService auditService) {
        this.identityService = identityService;
        this.auditService = auditService;
    }

    @GetMapping("/public")
    public Mono<String> publicMessage() {
        return Mono.just("public-ok");
    }

    @GetMapping("/api/me")
    public Mono<String> currentUser() {
        return identityService.currentUsername();
    }

    @GetMapping("/api/me/async")
    public Mono<String> asyncCurrentUser() {
        return Mono.just("go")
                .publishOn(Schedulers.parallel())
                .flatMap(ignored ->
                        identityService.currentUsername())
                .map(name -> "async:" + name);
    }

    @GetMapping("/api/admin/audit")
    public Mono<String> audit() {
        return auditService.readAudit();
    }

    @PostMapping("/api/notes")
    public Mono<NoteResult> createNote(
            @RequestBody Mono<NoteInput> input) {
        return input.map(note ->
                new NoteResult(note.text()));
    }
}
```

Ở `asyncCurrentUser`, lệnh `publishOn` xảy ra **trước** `flatMap(ignored -> identityService.currentUsername())`, vì vậy context được truy cập sau scheduling boundary. Test chỉ assert `async:alice`, không assert thread name `parallel-N` hoặc độ trễ ngẫu nhiên.

Không gọi `subscribe()` thủ công bên trong controller để làm công việc tiếp theo: WebFlux sẽ subscribe publisher trả về và giữ context/lifecycle theo request.

## 14. SecurityWebTestClientTest.java — 12 tests request-level

**src/test/java/example/reactivesecurity/SecurityWebTestClientTest.java**

```java
package example.reactivesecurity;

import java.time.Duration;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.ApplicationContext;
import org.springframework.http.MediaType;
import org.springframework.test.web.reactive.server.WebTestClient;

import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.csrf;
import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.mockUser;
import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.springSecurity;

@SpringBootTest(
        webEnvironment = SpringBootTest.WebEnvironment.MOCK
)
class SecurityWebTestClientTest {

    @Autowired
    ApplicationContext context;

    private WebTestClient client;

    @BeforeEach
    void buildClientWithSecurityFilters() {
        client = WebTestClient
                .bindToApplicationContext(context)
                .apply(springSecurity())
                .configureClient()
                .responseTimeout(Duration.ofSeconds(5))
                .build();
    }

    @Test
    void publicEndpointAllowsAnonymous() {
        client.get()
                .uri("/public")
                .exchange()
                .expectStatus().isOk()
                .expectBody(String.class)
                    .isEqualTo("public-ok");
    }

    @Test
    void protectedWithoutAuthenticationIs401() {
        client.get()
                .uri("/api/me")
                .exchange()
                .expectStatus().isUnauthorized();
    }

    @Test
    void mockReaderNameFromReactorContext() {
        client.mutateWith(
                mockUser("alice").roles("READER"))
                .get()
                .uri("/api/me")
                .exchange()
                .expectStatus().isOk()
                .expectBody(String.class)
                    .isEqualTo("alice");
    }

    @Test
    void mockUserCannotAccessAdminMethod() {
        client.mutateWith(
                mockUser("alice").roles("READER"))
                .get()
                .uri("/api/admin/audit")
                .exchange()
                .expectStatus().isForbidden();
    }

    @Test
    void mockAdminCanAccessAdminMethod() {
        client.mutateWith(
                mockUser("sara").roles("ADMIN"))
                .get()
                .uri("/api/admin/audit")
                .exchange()
                .expectStatus().isOk()
                .expectBody(String.class)
                    .isEqualTo("audit-ok");
    }

    @Test
    void identitySurvivesPublishOn() {
        client.mutateWith(
                mockUser("alice").roles("READER"))
                .get()
                .uri("/api/me/async")
                .exchange()
                .expectStatus().isOk()
                .expectBody(String.class)
                    .isEqualTo("async:alice");
    }

    @Test
    void editorBasicWithoutCsrfGets403() {
        client.post()
                .uri("/api/notes")
                .headers(headers ->
                        headers.setBasicAuth(
                                "editor", "editor-pass"))
                .contentType(MediaType.APPLICATION_JSON)
                .bodyValue(new NoteInput("first"))
                .exchange()
                .expectStatus().isForbidden();
    }

    @Test
    void editorBasicWithCsrfGets200() {
        client.mutateWith(csrf())
                .post()
                .uri("/api/notes")
                .headers(headers ->
                        headers.setBasicAuth(
                                "editor", "editor-pass"))
                .contentType(MediaType.APPLICATION_JSON)
                .bodyValue(new NoteInput("accepted"))
                .exchange()
                .expectStatus().isOk()
                .expectBody()
                .jsonPath("$.text")
                    .isEqualTo("accepted");
    }

    @Test
    void readerBasicWithCsrfLacksRole() {
        client.mutateWith(csrf())
                .post()
                .uri("/api/notes")
                .headers(headers ->
                        headers.setBasicAuth(
                                "reader", "reader-pass"))
                .contentType(MediaType.APPLICATION_JSON)
                .bodyValue(new NoteInput("not allowed"))
                .exchange()
                .expectStatus().isForbidden();
    }

    @Test
    void invalidBasicCredentialsAre401() {
        client.get()
                .uri("/api/me")
                .headers(headers ->
                        headers.setBasicAuth(
                                "reader", "wrong-password"))
                .exchange()
                .expectStatus().isUnauthorized();
    }

    @Test
    void mockUserDoesNotLeakIntoNextRequest() {
        client.mutateWith(
                mockUser("alice").roles("READER"))
                .get()
                .uri("/api/me")
                .exchange()
                .expectStatus().isOk()
                .expectBody(String.class)
                    .isEqualTo("alice");

        client.get()
                .uri("/api/me")
                .exchange()
                .expectStatus().isUnauthorized();
    }

    @Test
    void injectedRoleHeaderCannotElevate() {
        client.mutateWith(
                mockUser("alice").roles("READER"))
                .get()
                .uri("/api/admin/audit")
                .header("X-Role", "ADMIN")
                .exchange()
                .expectStatus().isForbidden();
    }
}
```

### 14.1. Bài học từ nhóm test request

- **Anonymous GET 401**: route protected được kiểm tra.
- **READER GET 200 với body alice**: identity được truyền đúng, không chỉ bất kỳ user nào.
- **READER admin 403, ADMIN admin 200**: method security có hiệu lực.
- **Async GET trả async:alice**: context còn nhìn thấy sau publishOn.
- **Basic EDITOR POST thiếu CSRF 403, có CSRF 200**: CSRF condition được quan sát.
- **Basic READER có CSRF vẫn 403**: CSRF không thay quyền role.
- **Bad password GET 401**: một phần authentication path thật được thực thi, không dùng mockUser.
- **Request sau mockUser vẫn anonymous**: identity không bị giữ global.
- **X-Role: ADMIN không nâng quyền**: client-supplied role header không được tin.

### 14.2. Spring method security thực được test ở đâu?

URL matcher chỉ yêu cầu authenticated cho `/api/admin/audit`, nhưng `AuditService.readAudit()` có `@PreAuthorize("hasRole('ADMIN')")`. Vì controller inject service bean, lời gọi đi qua Spring proxy. Nếu annotation bị tắt, READER denial test có thể đỏ dù ADMIN test vẫn xanh.

### 14.3. 401 vs 403 paired cases

Nếu POST không có CSRF nhưng READER được assert 403, bạn không biết lỗi do missing CSRF hay missing role. Lab dùng **đúng EDITOR role** ở cả no-CSRF và with-CSRF tests để cô lập nguyên nhân. Sau đó dùng **READER có token** để xác nhận role rule.

### 14.4. csrf() là test helper

`SecurityMockServerConfigurers.csrf()` giúp tạo token hợp lệ cho mock WebTestClient security infrastructure. Nó không chứng minh browser cookie/session flow, SameSite, Secure attributes hay CSRF token repository trong live deployment. Khi product có session cookies, bổ sung test thực phù hợp.

### 14.5. Không coi mockUser là authentication test

`mockUser` cấp principal/roles đã được test tin cậy. Nó không gọi password encoder hoặc JWT decoder. Khi muốn kiểm tra real credentials, gửi Basic/Bearer trong HTTP headers hoặc token fixture thực theo security config. MockUser phù hợp cho **authorization và Reactor Context**.

## 15. ReactiveContextUnitTest.java — 4 tests không cần HTTP

**src/test/java/example/reactivesecurity/ReactiveContextUnitTest.java**

```java
package example.reactivesecurity;

import org.junit.jupiter.api.Test;
import org.springframework.security.authentication.TestingAuthenticationToken;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.ReactiveSecurityContextHolder;
import org.springframework.security.core.context.SecurityContext;
import reactor.core.publisher.Mono;
import reactor.core.scheduler.Schedulers;
import reactor.test.StepVerifier;

class ReactiveContextUnitTest {

    private Authentication user(String name) {
        return new TestingAuthenticationToken(
                name, "unused", "ROLE_READER");
    }

    private Mono<String> currentName() {
        return ReactiveSecurityContextHolder.getContext()
                .map(SecurityContext::getAuthentication)
                .map(Authentication::getName)
                .defaultIfEmpty("anonymous");
    }

    @Test
    void authenticationFromContextIsVisibleOnSubscribe() {
        Mono<String> publisher = currentName()
                .contextWrite(
                        ReactiveSecurityContextHolder
                                .withAuthentication(user("alice")));

        StepVerifier.create(publisher)
                .expectNext("alice")
                .verifyComplete();
    }

    @Test
    void contextCrossesScheduler() {
        Mono<String> publisher = Mono.just("go")
                .publishOn(Schedulers.parallel())
                .flatMap(ignored -> currentName())
                .contextWrite(
                        ReactiveSecurityContextHolder
                                .withAuthentication(user("bob")));

        StepVerifier.create(publisher)
                .expectNext("bob")
                .verifyComplete();
    }

    @Test
    void differentSubscriptionsRemainIsolated() {
        Mono<String> lookup = currentName();

        StepVerifier.create(
                lookup.contextWrite(
                        ReactiveSecurityContextHolder
                                .withAuthentication(user("alice"))))
                .expectNext("alice")
                .verifyComplete();

        StepVerifier.create(
                lookup.contextWrite(
                        ReactiveSecurityContextHolder
                                .withAuthentication(user("bob"))))
                .expectNext("bob")
                .verifyComplete();

        StepVerifier.create(lookup)
                .expectNext("anonymous")
                .verifyComplete();
    }

    @Test
    void absentContextDefaultsToAnonymous() {
        StepVerifier.create(currentName())
                .expectNext("anonymous")
                .verifyComplete();
    }
}
```

### 15.1. Vì sao StepVerifier là phép đo phù hợp?

`StepVerifier.create(publisher)` tạo subscription và assert `onNext`/`onComplete` hoặc error signals. Nó không tự cấp Authentication. `contextWrite(withAuthentication(...))` được đặt ở publisher cần test, vì vậy mỗi subscription có identity mong muốn.

### 15.2. Context không có giá trị

`ReactiveSecurityContextHolder.getContext()` có thể empty ngoài HTTP security chain. Helper `currentName()` dùng `defaultIfEmpty("anonymous")` để mô tả observable. Trong production, thiếu context tại secured boundary thường phải bị từ chối chứ không âm thầm cho anonymous sử dụng privileged method.

### 15.3. Không rò giữa subscriptions

`differentSubscriptionsRemainIsolated` dùng lại cùng một publisher nhưng ba subscriptions: alice, bob và không auth. Nó chứng minh principal đến từ subscription context, không phải một biến static ghi đè bởi test trước.

### 15.4. Test method security trực tiếp

Nếu test service `@PreAuthorize` không qua HTTP, cần lấy **Spring-managed bean proxy** và subscribe với Reactor authentication. Ví dụ (snippet minh họa cần Spring test context/imports):

```java
Authentication reader = new TestingAuthenticationToken(
        "alice", "unused", "ROLE_READER");

Mono<String> result = auditService.readAudit()
        .contextWrite(
                ReactiveSecurityContextHolder
                        .withAuthentication(reader));

StepVerifier.create(result)
        .expectError(AccessDeniedException.class)
        .verify();
```

Nếu `auditService` được tạo bằng `new`, Spring AOP method interceptor không có hiệu lực. Đừng đặt một test này trong pure unit class rồi nghĩ @PreAuthorize tự chạy.

## 16. LiveBasicAuthTest.java — HTTP server thật

**src/test/java/example/reactivesecurity/LiveBasicAuthTest.java**

```java
package example.reactivesecurity;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.reactive.server.WebTestClient;

@SpringBootTest(
        webEnvironment =
                SpringBootTest.WebEnvironment.RANDOM_PORT
)
@AutoConfigureWebTestClient
class LiveBasicAuthTest {

    @Autowired
    WebTestClient client;

    @Test
    void liveServerAcceptsRealBasicCredentials() {
        client.get()
                .uri("/api/me")
                .headers(headers ->
                        headers.setBasicAuth(
                                "reader", "reader-pass"))
                .exchange()
                .expectStatus().isOk()
                .expectBody(String.class)
                    .isEqualTo("reader");
    }
}
```

Test này chạy embedded HTTP server ở một port ngẫu nhiên. HTTP Basic header được gửi thật qua network socket, Spring Security authentication filter dùng user details của lab và `IdentityService` đọc principal từ Reactor Context.

Không xem test này đã xác minh external TLS/PKI, reverse proxy, OAuth2 IdP, mTLS hoặc security của production network. Muốn test các yêu cầu ấy cần môi trường tích hợp thích hợp.

## 17. Lệnh chạy và kết quả dự kiến

Máy cần JDK 17, Gradle Wrapper tương thích (ví dụ Gradle 8.7), truy cập Maven Central/cache dependencies. Dự án không cần Docker hay database.

Linux/macOS:

```bash
./gradlew test
./gradlew test --tests example.reactivesecurity.SecurityWebTestClientTest
./gradlew test --tests example.reactivesecurity.ReactiveContextUnitTest
./gradlew test --tests example.reactivesecurity.LiveBasicAuthTest
```

Windows PowerShell:

```powershell
.\gradlew.bat test
.\gradlew.bat test --tests example.reactivesecurity.SecurityWebTestClientTest
.\gradlew.bat test --tests example.reactivesecurity.ReactiveContextUnitTest
```

| Test class | Methods | Spring context | HTTP TCP |
| --- | ---: | --- | --- |
| `SecurityWebTestClientTest` | 12 | Có | Không |
| `ReactiveContextUnitTest` | 4 | Không | Không |
| `LiveBasicAuthTest` | 1 | Có | Có |
| **Tổng** | **17** | Tùy class | Tùy class |

**Kết quả dự kiến:** 17 test methods pass nếu code được đặt đúng package/files và dependencies/configuration phù hợp. Đây không phải ghi nhận chạy Gradle; người học phải kiểm tra report thật trước khi báo PASS. Không có business stdout cố định; HTTP port, scheduler thread name, logs và test order có thể khác nhau.

## 18. Lỗi phổ biến khi test WebFlux Security

### 18.1. Mock setup thiếu springSecurity()

Trong manual `bindToApplicationContext` client, nếu bỏ `.apply(springSecurity())`, security test mutators/WebFilters có thể không hoạt động đúng. Chỉ test `/public` 200 không cho biết security chain đã được kiểm tra; phải có anonymous 401, reader 403.

### 18.2. Method security bị bypass

Một Spring bean có `@PreAuthorize` nhưng test tạo object bằng `new`, hoặc mock chính service đó, thì AOP method interceptor không được đi qua. Dùng Spring-managed injected bean/implementation thật. Cẩn thận self-invocation trong cùng bean.

### 18.3. Chỉ assert 403

POST READER không token trả 403 vì CSRF hay role? Không biết. Làm paired tests với đúng role có/không token và thiếu role có token.

### 18.4. Dùng @WithMockUser như Context của mọi Reactor chain

`@WithMockUser` thuộc Spring Security test support. Ở pure publisher unit test không đi qua HTTP/Integration context, đừng giả định annotation này tự gắn principal qua mọi scheduler; explicit `contextWrite` rõ hơn.

### 18.5. Dùng ThreadLocal để đo identity

`Thread.currentThread().getName()` không xác minh context. Một `ThreadLocal<String>` có thể mất khi `publishOn`. Assert string được đọc từ `ReactiveSecurityContextHolder` trong operator downstream.

### 18.6. .subscribe() tách rời parent chain

Tạo manual subscription trong service làm error/cancellation/context khó kiểm soát. Dùng flatMap/map/reactive composition và trả publisher cho WebFlux runtime subscribe.

### 18.7. Block trên Netty event loop

`block()`/`Thread.sleep()` trong reactive handler có thể chặn event loop, gây timeout/hung và làm mất ý nghĩa nonblocking. Không cần làm vậy để lấy Authentication vì API reactive đã cung cấp Mono.

### 18.8. Static field chứa current user

Một singleton service có `static String username` hoặc field mutable “current principal” gây nguy cơ rò data cross-request. Reactor Context là per subscription.

### 18.9. Tắt CSRF để test chạy

Chỉ disable CSRF khi threat model và auth mechanism thật đòi hỏi, không phải để chữa test thiếu token. Với cookie/session authentication qua browser, CSRF là rủi ro quan trọng. Stateless bearer API có threat model khác; phải phân tích cụ thể.

### 18.10. Test 401 với POST missing CSRF

CSRF có thể trả 403 trước authentication. Để test authentication entry point rõ, chọn safe GET protected endpoint rồi gửi anonymous/invalid credentials.

### 18.11. X-Role: ADMIN được coi là trusted

Client tự đặt HTTP header không tạo quyền. Nếu muốn roles từ headers, phải có trusted proxy/authenticated boundary và signature/validation phù hợp. Lab cố ý test header spoof không nâng quyền.

### 18.12. WebFluxTest không import security config

Web slice có thể thiếu custom `SecurityWebFilterChain` hoặc service cần cho method security. Import config/collaborators có chủ đích hoặc dùng full SpringBootTest.

## 19. Reactive method-security, JWT và scopes

`@EnableReactiveMethodSecurity` dùng Reactor Context để evaluate method authorization. Với `@PreAuthorize("hasRole('ADMIN')")`, authority ROLE_ADMIN là điều kiện. Những rules phức tạp có thể dựa vào user ownership/tenant ID, scopes hoặc trusted claims; chỉ role-level tests không đủ bảo vệ dữ liệu đa tenant.

### 19.1. mockJwt không chứng minh JWT signature

`mockJwt()` là test mutator dùng trong ứng dụng có OAuth2 resource server configuration và dependencies phù hợp. Nó cho phép gắn claims/authorities mô phỏng vào test exchange, thường **không** gọi real JWT decoder/signature verification.

Snippet chỉ minh họa (không thuộc project runnable vì thiếu resource-server module/route):

```java
client.mutateWith(
        mockJwt()
            .jwt(jwt -> jwt.subject("alice"))
            .authorities(
                new SimpleGrantedAuthority("SCOPE_read")))
        .get()
        .uri("/api/secure")
        .exchange();
```

Để test JWT security thật, cấu hình `ReactiveJwtDecoder` và test keys, gửi bearer token được ký thực, có cả invalid signature/issuer/audience/expiry. Không dùng production tokens vào CI fixtures/logs.

### 19.2. @WithMockUser và mockUser

`mockUser` phù hợp scope từng WebTestClient request; `@WithMockUser` là annotation-based setup trong Spring Security tests. Cả hai **giả lập principal**, không kiểm tra password encoder, user database hay external IdP.

Một pure StepVerifier test cần context trong publisher. Nếu không có HTTP security chain, explicit `ReactiveSecurityContextHolder.withAuthentication(...)` là cách dễ giải thích nhất.

## 20. Khi nào phải kiểm tra bên ngoài HTTP mock boundary?

| Mục tiêu | Test cần thiết |
| --- | --- |
| Method security và HTTP statuses | Mock-bound WebTestClient + security config |
| Reactor context sau scheduler | StepVerifier + contextWrite |
| HTTP Basic qua socket | SpringBootTest RANDOM_PORT |
| Cookie-based CSRF repository/SameSite | Live HTTP/browser-like test có sessions |
| JWT issuer/audience/signature/expiry | Decoder + signed fixture/JWKS test |
| OAuth2 login redirects/session | Provider sandbox/auth server test |
| mTLS, reverse proxy, ingress, WAF | Deployment/security integration environment |
| Multi-tenant data isolation | Authorization tests với nhiều tenants/resources |
| Replay/duplicate requests | Idempotency tests qua business/storage layers |

Không gọi một `WebTestClient` mock-bound test là end-to-end với IdP/production network, dù nó chạy Controller/Service/SecurityConfig thật.

## 21. Security context trong scheduled jobs/messaging

Kafka consumers và scheduled jobs có thể tạo Reactor publisher **ngoài một HTTP request**, do đó `ReactiveSecurityContextHolder.getContext()` có thể empty. Nếu business method yêu cầu authenticated identity:

1. Quyết định service identity đáng tin đến từ đâu.
2. Xác minh event signature/token/source trước khi biến thành Authentication.
3. Gắn Authentication vào Reactor Context của chính pipeline đó.
4. Không dùng một role header do client tự cung cấp rồi gọi `withAuthentication`.
5. Test thiếu identity, identity đúng role và identity thiếu quyền.
6. Không cache context như global field hoặc cho request A thừa kế principal từ request B.

**`withAuthentication` chỉ là phương tiện đặt context**, không tự xác minh authentication object có đáng tin hay không.

## 22. Troubleshooting nhanh

| Triệu chứng | Nguyên nhân | Hướng kiểm tra |
| --- | --- | --- |
| Anonymous GET 200 | Security filter thiếu hoặc URL permitAll | Chain/configurer |
| mockUser GET 401 | Chưa mutate đúng client hoặc filter | apply springSecurity() |
| READER admin 200 | Method security không enforce | @EnableReactiveMethodSecurity, AOP proxy |
| ADMIN admin 403 | Role/authority name sai | ROLE_ADMIN vs hasRole |
| EDITOR POST 403 | Thiếu CSRF token hoặc wrong role | Paired token tests |
| READER + CSRF 403 | Thiếu ROLE_EDITOR | Expected |
| Wrong Basic password 200 | Auth flow bị bypass/mocked | Real Basic header & user details |
| getContext empty | Không có context trong subscription | WebFilter hoặc contextWrite |
| Scheduler identity sai | Detached subscribe/ThreadLocal | Compose chain, read downstream |
| Live HTTP mockUser không tác động | Mock principal không qua socket | Real credentials/token |
| Test pass khi annotation bị bỏ | Chỉ positive case | Thêm READER negative |
| @WebFluxTest thiếu beans | Slice không scan custom config | @Import hoặc full context |
| 302 thay vì 401 | Form login entry point | Match security config |
| POST anonymous 403 thay vì 401 | CSRF filter chặn trước auth | GET auth test |
| WebFlux event loop bị block | block/sleep/legacy I/O | Nonblocking operators, StepVerifier |
| Hai requests thấy cùng principal | Static mutable field/cache scope | Context isolation tests |

Khi cần test-only logs:

```properties
logging.level.org.springframework.security=DEBUG
logging.level.org.springframework.web.reactive=DEBUG
```

Không bật debug/trace rộng cho production hoặc public CI nếu logs có thể chứa Authorization headers, tokens, credentials, principal names, session IDs hoặc PII.

## 23. Bài tập

1. Tạm bỏ `.apply(springSecurity())`; xem negative cases còn phát hiện filter bị thiếu không.
2. Bỏ `@EnableReactiveMethodSecurity`; READER có vào `/api/admin/audit` không? Khôi phục.
3. Đổi mock admin thành READER; expected 403.
4. Tạm bỏ `csrf()` ở POST EDITOR; expected 403; thêm lại expected 200.
5. Dùng READER cùng CSRF; expected 403 do role.
6. Đổi HTTP Basic password đúng thành sai, expected 401.
7. Chuyển đọc context trước publishOn rồi chỉ truyền String; phân biệt test context propagation thật với String propagation.
8. Bỏ `contextWrite` khỏi StepVerifier test; expected "anonymous" ở helper.
9. Subscribe cùng publisher bằng alice/bob contexts riêng; kiểm tra không leak.
10. Gọi `new AuditService()` rồi so sánh với Spring proxy để hiểu AOP boundary.
11. Thử test WebFlux slice; import security config/collaborators để giữ rules.
12. Thêm JWT decoder integration test với test key; mockJwt chỉ dùng cho authorization unit.
13. Mở rộng multi-tenant ownership authorization; role giống nhau chưa đủ xem tài nguyên của tenant khác.
14. Cho READER gửi `X-Role: ADMIN`, chắc chắn không nâng quyền.
15. Kiểm tra background publisher không HTTP context và service authentication có nguồn xác minh.
16. Chạy live RANDOM_PORT test và kiểm tra wrong Basic password ngoài socket.

## 24. Checklist trước khi chốt QA

- [ ] Spring WebFlux được chọn đúng, không lẫn Servlet MVC.
- [ ] SecurityWebFilterChain/ServerHttpSecurity configuration được nạp.
- [ ] Manual-bound WebTestClient có apply springSecurity().
- [ ] Anonymous GET 401 và authenticated GET 200 được kiểm tra.
- [ ] READER 403, ADMIN 200 tại secured method.
- [ ] @EnableReactiveMethodSecurity và proxy bean thật được sử dụng.
- [ ] POST đúng role thiếu CSRF token 403, có token 200.
- [ ] POST có CSRF nhưng thiếu role vẫn 403.
- [ ] MockUser được hiểu là fake identity, không phải credential validation.
- [ ] Khi cần real authentication, gửi Basic/Bearer header thật.
- [ ] ReactiveSecurityContextHolder dùng trong Publisher.
- [ ] StepVerifier inject context bằng contextWrite(withAuthentication).
- [ ] Đã kiểm tra đọc context sau publishOn.
- [ ] Không leak principal giữa requests/subscriptions.
- [ ] Không lưu current user trong singleton/static mutable field.
- [ ] Không manual subscribe hoặc block trong WebFlux handler.
- [ ] Không self-invocation bypass @PreAuthorize.
- [ ] Không @MockBean thay chính bean cần test method security.
- [ ] Không tin X-Role/header/claim chưa xác thực.
- [ ] Không coi mockJwt là JWT signature verification.
- [ ] CSRF được bật/tắt theo threat model, không theo tiện ích test.
- [ ] Live HTTP test dùng real credentials, không mock principal qua socket.
- [ ] Test không assert thread name, port hoặc timing cố định.
- [ ] Không ghi real credentials/JWT/PII trong fixtures/logs.
- [ ] Có thông tin executed/passed/failed/skipped thật khi báo kết quả.
- [ ] Chưa chứng minh TLS, IdP, production ingress chỉ bằng mock WebTestClient.

## 25. Tóm tắt quyết định

```text
Mục tiêu test?
    |
    +-- Pure business rule?
    |      -> JUnit/Mockito.
    |
    +-- WebFlux request auth/roles/CSRF?
    |      -> WebTestClient.bindToApplicationContext
    |         + springSecurity() + mockUser()/csrf().
    |
    +-- Reactor identity across schedulers?
    |      -> ReactiveSecurityContextHolder
    |         + contextWrite + StepVerifier.
    |
    +-- @PreAuthorize method enforcement?
    |      -> Spring proxy + allowed/denied tests.
    |
    +-- Real Basic/Bearer HTTP?
    |      -> RANDOM_PORT + actual headers.
    |
    +-- JWT signature/issuer/audience?
    |      -> Real token decoder and test keys.
    |
    +-- TLS/IdP/ingress/HA?
           -> Staging/deployment security tests.
```

**Ghi nhớ:** Test bảo mật Reactive phải xét cả HTTP security filters lẫn **Reactor subscriber context**. `WebTestClient` giúp kiểm tra 401/403, `mockUser` và `csrf` trong request pipeline; `StepVerifier` và `ReactiveSecurityContextHolder` kiểm tra identity propagation theo reactive subscription. Positive/negative pairs ngăn test xanh giả. Không được đồng nhất principal mock với authentication thực hoặc mock HTTP test với production security certification.

## 26. Tài liệu chính thức

- Spring Boot 3.3 — Testing Spring Boot Applications, WebFlux/WebTestClient: https://docs.spring.io/spring-boot/3.3/reference/testing/spring-boot-applications.html
- Spring Framework — WebTestClient mock and live setup: https://docs.spring.io/spring-framework/reference/testing/webtestclient.html
- Spring Security — Reactive WebTestClient setup: https://docs.spring.io/spring-security/reference/reactive/test/web/setup.html
- Spring Security — Testing Authentication, mockUser: https://docs.spring.io/spring-security/reference/reactive/test/web/authentication.html
- Spring Security — Testing CSRF, csrf(): https://docs.spring.io/spring-security/reference/reactive/test/web/csrf.html
- Spring Security — Enable Reactive Method Security: https://docs.spring.io/spring-security/reference/reactive/authorization/method.html
- Spring Security — Reactive HTTP authorization: https://docs.spring.io/spring-security/reference/reactive/authorization/authorize-http-requests.html
- Spring Security — Reactive CSRF: https://docs.spring.io/spring-security/reference/reactive/exploits/csrf.html
- Spring Security — ReactiveSecurityContextHolder: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/core/context/ReactiveSecurityContextHolder.html
- Spring Security — SecurityMockServerConfigurers Javadoc: https://docs.spring.io/spring-security/site/docs/current/api/org/springframework/security/test/web/reactive/server/SecurityMockServerConfigurers.html
- Project Reactor — Context: https://projectreactor.io/docs/core/release/reference/advancedFeatures/context.html
- Project Reactor — Testing with StepVerifier: https://projectreactor.io/docs/core/release/reference/testing.html
- JUnit Jupiter — User Guide: https://docs.junit.org/current/user-guide/
