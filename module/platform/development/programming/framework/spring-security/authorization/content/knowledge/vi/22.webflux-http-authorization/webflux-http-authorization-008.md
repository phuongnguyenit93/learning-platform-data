# ReactiveSecurityContextHolder và Reactor Context

> **Chủ đề:** Spring Security – authorization → **HTTP trên WebFlux**. Bài viết hướng dẫn cách Spring Security lưu và truyền `SecurityContext` trong Reactor `Context` theo từng subscription, sử dụng `ReactiveSecurityContextHolder`, hiểu `contextWrite`/`deferContextual`, giữ danh tính khi chạy `Mono`/`Flux` trên nhiều scheduler, tránh rò rỉ dữ liệu giữa người dùng, kiểm thử với `StepVerifier`/`WebTestClient` và kết hợp Reactive Method Security. Ví dụ dùng Java 17+, Spring Boot 3.x và Spring Security 6.x.

## 1. Vì sao WebFlux không nên lấy user bằng ThreadLocal?

Trong servlet app đồng bộ, bạn có thể thấy:

~~~java
Authentication authentication =
        SecurityContextHolder.getContext().getAuthentication();

String username = authentication.getName();
~~~

`SecurityContextHolder` trong mô hình imperative thường gắn `SecurityContext` với thread hiện tại. Nhưng WebFlux chạy bằng reactive execution: một thread có thể xử lý nhiều yêu cầu, và một yêu cầu có thể được tiếp tục ở thread khác.

~~~text
HTTP Request A (alice)            HTTP Request B (bob)
      |                                 |
   event-loop-1                      event-loop-1
      |                                 |
   flatMap                            flatMap
      |                                 |
   parallel-2                        parallel-3
      |                                 |
   Response A                        Response B
~~~

Nếu code cố lưu tên user trong `ThreadLocal` và đọc lại sau một `publishOn` hoặc callback khác, giá trị có thể biến mất hoặc bị dùng sai. Rủi ro không chỉ là exception: dùng nhầm danh tính trong authorization có thể làm lộ dữ liệu tenant khác.

**Giải pháp:** Reactor `Context` gắn với **Subscriber/subscription**, không gắn với một thread cố định. Spring Security đặt SecurityContext vào Reactor Context; code reactive đọc bằng `ReactiveSecurityContextHolder.getContext()`.

> Danh tính người dùng không được gắn vào một singleton field, static variable, cached `Mono` dùng chung, hoặc header tự khai. Hãy dựa vào Authentication đã được xác minh trong đúng reactive subscription.

## 2. Phân biệt các lớp dữ liệu bảo mật

| Khái niệm | Chứa/giải quyết điều gì? | Sai lầm hay gặp |
| --- | --- | --- |
| `Authentication` | Principal, authorities, trạng thái xác thực | Nhầm role chung với quyền trên mọi object |
| `SecurityContext` | Đối tượng chứa Authentication | Nhầm với HTTP session/JWT |
| `SecurityContextHolder` | API context kiểu imperative, thường qua thread | Dùng mặc định trong WebFlux |
| Reactor `Context` | Map key/value theo Subscriber | Nhầm thành một mutable global map |
| `ReactiveSecurityContextHolder` | API get/put SecurityContext qua Reactor Context | Tưởng là “current user” toàn cục |
| `ReactiveSecurityContextHolder.getContext()` | `Mono<SecurityContext>` | Tưởng trả SecurityContext trực tiếp |
| `@EnableReactiveMethodSecurity` | Bật kiểm tra method reactive | Nhầm với `@EnableMethodSecurity` kiểu servlet |

Cấu trúc khái niệm:

~~~text
Reactor Context (gắn với Subscriber)
      |
      +-- key của Spring Security
             |
             +-- Mono<SecurityContext>
                         |
                         +-- Authentication
                                 |-- principal / name
                                 |-- authorities
                                 +-- isAuthenticated
      |
      +-- traceId / correlationId / other keys
~~~

`Reactor Context` có thể chứa nhiều dữ liệu ngữ cảnh khác nhau; `ReactiveSecurityContextHolder` sử dụng phần của Spring Security. Một custom key `"user"` do application đặt không tự trở thành `Authentication` đã được xác minh.

## 3. Cơ chế của Reactor Context

### 3.1. Publisher được dựng trước, subscription xảy ra sau

~~~text
Assembly phase:
  Mono<String> request = service.currentName();
  // Chưa chạy request logic.

Subscription phase:
  subscriber
       |
       v
  contextWrite(...) -> upstream operators -> data/error/completion
~~~

Một `Mono` mô tả công việc; việc đọc context xảy ra trong luồng subscription. Khi bạn gọi `ReactiveSecurityContextHolder.getContext()`, hãy **compose** kết quả thay vì chặn đồng bộ bằng `block()`.

### 3.2. Context bất biến

~~~java
Context first = Context.of("traceId", "t-1");
Context second = first.put("tenant", "acme");
~~~

`second` chứa key mới, `first` không bị sửa tại chỗ. `ContextView` là giao diện chỉ đọc; `getOrDefault`/`getOrEmpty` giúp tránh ném exception nếu một key không tồn tại. Không nên dùng context như một Map global thay đổi từ nhiều request.

### 3.3. Context gắn với subscriber, không với Java thread

| Thao tác | Reactor Context | ThreadLocal mặc định |
| --- | --- | --- |
| `map`, `flatMap` trong cùng subscription | Có thể đọc khi context đặt đúng | Phụ thuộc thread |
| `publishOn(Schedulers.parallel())` | Giữ ngữ cảnh reactive trong pipeline | ThreadLocal có thể không còn |
| `subscribeOn(...)` | Context thuộc subscription | Không tự sao chép thread-local |
| `new Thread(...)`, `Executor.submit(...)` | Không tự có parent Reactor Context | Không tự truyền ThreadLocal |
| `CompletableFuture.supplyAsync(...)` | Không tự hiểu Reactor Context | Không tự giữ ThreadLocal |
| `subscribe()` mới ngoài request chain | Subscription riêng, không mặc nhiên nhận context cũ | Không bảo đảm |
| WebClient gọi remote service | Context không tự thành HTTP Authorization header | ThreadLocal cũng không tự gửi token |

Reactor Context lan theo **subscription chain và các operator Reactor**, không tự đi qua mọi callback ngoài Reactor, message queue, thread thủ công hoặc network boundary.

## 4. API của ReactiveSecurityContextHolder

Import:

~~~java
import org.springframework.security.core.context.ReactiveSecurityContextHolder;
~~~

| Method | Kiểu trả về | Mục đích |
| --- | --- | --- |
| `getContext()` | `Mono<SecurityContext>` | Lấy SecurityContext trong current reactive subscription |
| `withAuthentication(Authentication)` | Reactor `Context` | Đặt Authentication vào context của một nhánh/subscription |
| `withSecurityContext(Mono<? extends SecurityContext>)` | Reactor `Context` | Đặt reactive SecurityContext vào context |
| `clearContext()` | `Function<Context, Context>` | Xóa entry SecurityContext ở phần upstream bị tác động |

### 4.1. `getContext()`

~~~java
Mono<String> name = ReactiveSecurityContextHolder.getContext()
        .flatMap(ctx ->
                Mono.justOrEmpty(ctx.getAuthentication()))
        .map(Authentication::getName);
~~~

Imports:

~~~java
import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.ReactiveSecurityContextHolder;
import reactor.core.publisher.Mono;
~~~

Nếu không có context hoặc Authentication, publisher trên hoàn tất rỗng. Với endpoint nhạy cảm, **không được** coi “không có context” là user hệ thống. Nên fail closed bằng `switchIfEmpty(Mono.error(...))` hoặc một reactive authorization mechanism phù hợp.

### 4.2. `withAuthentication(...)`

~~~java
Authentication trustedAuthentication = /* giá trị đã xác minh */;

Mono<String> response = service.currentName()
        .contextWrite(
                ReactiveSecurityContextHolder.withAuthentication(
                        trustedAuthentication));
~~~

**Đây là đoạn minh họa tích hợp**, không phải file Java độc lập; `service` và Authentication cần được định nghĩa. Trong tests, có thể dựng Authentication giả định một cách có chủ đích. Trong production không dùng username/authority do client tự gửi để tạo authenticated principal.

`withAuthentication` trả về Reactor `Context`, **không** thay thế user global hay sửa một SecurityContextHolder ThreadLocal.

### 4.3. `withSecurityContext(...)`

~~~java
SecurityContext securityContext =
        new SecurityContextImpl(trustedAuthentication);

Mono<String> response = service.currentName()
        .contextWrite(
                ReactiveSecurityContextHolder.withSecurityContext(
                        Mono.just(securityContext)));
~~~

Imports liên quan:

~~~java
import org.springframework.security.core.context.SecurityContext;
import org.springframework.security.core.context.SecurityContextImpl;
~~~

Method này nhận một `Mono<? extends SecurityContext>`; nếu đã có `Authentication`, dùng `withAuthentication(...)` gọn hơn.

### 4.4. `clearContext()`

~~~java
Mono<String> response = service.currentName()
        .contextWrite(
                ReactiveSecurityContextHolder.clearContext());
~~~

`clearContext()` trả về **hàm biến đổi Context**, không phải logout toàn bộ server, không xóa cookie/session và không revoke JWT. Nó chỉ xóa dữ liệu SecurityContext khỏi phạm vi các operator upstream mà `contextWrite` tác động.

## 5. Hướng của contextWrite: downstream → upstream

Trong Reactor, `contextWrite` đưa dữ liệu context từ phía subscriber **lên các operator upstream**. Vị trí operator quan trọng.

### 5.1. Ghi đúng phía

~~~java
Mono<String> pipeline = Mono.deferContextual(ctx -> {
    String traceId = ctx.getOrDefault("traceId", "missing");
    return Mono.just("trace=" + traceId);
}).contextWrite(ctx -> ctx.put("traceId", "t-42"));
~~~

Khi subscribe, kết quả:

~~~text
trace=t-42
~~~

### 5.2. Ghi sai phía

~~~java
Mono<String> pipeline = Mono.just("start")
        .contextWrite(ctx -> ctx.put("traceId", "t-42"))
        .flatMap(ignored -> Mono.deferContextual(ctx -> {
            String traceId = ctx.getOrDefault("traceId", "missing");
            return Mono.just(traceId);
        }));
~~~

Kết quả:

~~~text
missing
~~~

Reader ở **downstream** của `contextWrite` không thấy key đó. Đừng suy ra rằng “operator viết context đứng trước trong code” nghĩa là toàn bộ phía dưới đều thấy.

### 5.3. Hai lần ghi cùng key

~~~java
Mono<String> pipeline = Mono.deferContextual(ctx -> {
    String value = ctx.get("role");
    return Mono.just(value);
})
.contextWrite(ctx -> ctx.put("role", "INNER"))
.contextWrite(ctx -> ctx.put("role", "OUTER"));
~~~

Kết quả:

~~~text
INNER
~~~

Operator `contextWrite` gần reader hơn trong chiều subscription có thể ghi đè key cùng tên. Đối với **security context**, điều này có nghĩa một thư viện/callback thay context tùy tiện có thể làm upstream đọc một identity khác. Chỉ viết Authentication từ nguồn tin cậy.

### 5.4. Inner publisher trong flatMap

~~~java
Mono<String> pipeline = Mono.just("A")
        .flatMap(value -> Mono.deferContextual(ctx -> {
            String scope = ctx.getOrDefault("scope", "none");
            return Mono.just(value + "-" + scope);
        }).contextWrite(ctx -> ctx.put("scope", "inner")))
        .flatMap(value -> Mono.deferContextual(ctx -> {
            String scope = ctx.getOrDefault("scope", "none");
            return Mono.just(value + "-" + scope);
        }))
        .contextWrite(ctx -> ctx.put("scope", "outer"));
~~~

Kết quả:

~~~text
A-inner-outer
~~~

Context riêng được ghi trong một inner reactive chain không tự biến thành context của tất cả inner chains sau đó. Cần kiểm thử phạm vi khi ứng dụng ghép nhiều helper.

## 6. Spring Security tích hợp với WebFlux

Luồng tổng quan:

~~~text
HTTP Request
    |
    v
Spring WebFlux WebFilter chain
    |
    v
SecurityWebFilterChain
    |
    +-- Authentication (Basic / OAuth2 / session)
    +-- kiểm tra thông tin đăng nhập
    +-- đặt SecurityContext vào Reactor Context
    +-- HTTP authorization
    |
    v
Controller -> Mono/Flux -> service -> reactive repository
                             |
                             v
           ReactiveSecurityContextHolder.getContext()
~~~

Một request HTTP đã được Spring Security xác thực thường không cần controller tự gọi `withAuthentication`; framework gắn context vào reactive execution. Các scheduled jobs, message consumers, tests thuần Reactor **không có sẵn request context** nên không được tự suy ra user từ thread đang chạy.

### 6.1. Khi nào nên truyền Authentication vào controller?

Spring WebFlux/Spring Security có thể inject thông tin đã xác thực:

~~~java
@GetMapping("/api/me")
public Mono<String> me(Authentication authentication) {
    return Mono.just(authentication.getName());
}
~~~

Cách này thuận tiện nếu controller chỉ cần user ngay tại HTTP boundary. Nhưng nếu đọc principal trong một reactive service sâu hơn hoặc lúc subscription thực thi ở scheduler khác, `ReactiveSecurityContextHolder.getContext()` phù hợp hơn với cách compose Publisher.

Argument Authentication được framework resolve từ request đã xác minh, **không** phải chuỗi do user tự gửi.

## 7. Ví dụ Java 17+ và Spring Boot 3.x hoàn chỉnh

Ứng dụng demo dùng:
- Spring WebFlux + HTTP Basic;
- `ReactiveSecurityContextHolder` trong service;
- `@EnableReactiveMethodSecurity` và `@PreAuthorize`;
- Hai user demo Alice và Bob với authorities khác nhau;
- Controllers trả `Mono<String>`;
- JUnit tests qua `WebTestClient` và `StepVerifier`.

Ví dụ dùng một project Spring Boot 3.x với Java 17, Gradle, plugin Boot và dependency management đúng version. Các dependencies để BOM của Spring Boot quản lý Spring Security/Reactor. Demo không phải authentication architecture cho production.

### 7.1. `build.gradle` dependencies

~~~groovy
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
~~~

Không thêm `spring-boot-starter-web` cho demo chỉ WebFlux. Spring Security starter **không tự bật** Reactive Method Security nếu chưa có cấu hình tương ứng.

### 7.2. `src/main/java/demo/reactivecontext/ReactiveContextApplication.java`

~~~java
package demo.reactivecontext;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ReactiveContextApplication {
    public static void main(String[] args) {
        SpringApplication.run(ReactiveContextApplication.class, args);
    }
}
~~~

### 7.3. `src/main/java/demo/reactivecontext/ReactiveSecurityConfig.java`

~~~java
package demo.reactivecontext;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.method.configuration.EnableReactiveMethodSecurity;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.crypto.factory.PasswordEncoderFactories;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.MapReactiveUserDetailsService;
import org.springframework.security.web.server.SecurityWebFilterChain;

@Configuration
@EnableWebFluxSecurity
@EnableReactiveMethodSecurity
public class ReactiveSecurityConfig {

    @Bean
    SecurityWebFilterChain security(ServerHttpSecurity http) {
        return http
                .authorizeExchange(exchanges -> exchanges
                        .pathMatchers("/api/public/ping").permitAll()
                        .pathMatchers("/api/me", "/api/restricted")
                            .authenticated()
                        .anyExchange().denyAll())
                .httpBasic(Customizer.withDefaults())
                .formLogin(form -> form.disable())
                .build();
    }

    @Bean
    MapReactiveUserDetailsService users() {
        PasswordEncoder encoder =
                PasswordEncoderFactories.createDelegatingPasswordEncoder();

        UserDetails alice = User.withUsername("alice")
                .password(encoder.encode("alice-pass"))
                .authorities("DOC_READ")
                .build();

        UserDetails bob = User.withUsername("bob")
                .password(encoder.encode("bob-pass"))
                .authorities("DOC_VIEW")
                .build();

        return new MapReactiveUserDetailsService(alice, bob);
    }
}
~~~

**Giải thích:**
1. `@EnableWebFluxSecurity` kích hoạt WebFlux Security.
2. `@EnableReactiveMethodSecurity` cho phép xét quyền ở method reactive, ví dụ `@PreAuthorize`.
3. `/api/public/ping` public; `/api/me` và `/api/restricted` cần Authentication hợp lệ; mọi URL khác bị deny.
4. `httpBasic` dùng trong demo; `formLogin` bị tắt để response API gọn và có 401 challenge.
5. Alice có `DOC_READ`, Bob chỉ có `DOC_VIEW`, nên đăng nhập thành công không đồng nghĩa được phép gọi mọi method.
6. CSRF mặc định tiếp tục bật với unsafe HTTP methods; ví dụ chỉ dùng GET. Không tắt CSRF nếu browser có thể tự gửi credentials.

`MapReactiveUserDetailsService` chỉ là user store trong RAM cho tests, không dùng mật khẩu nhúng cứng ở production. Trong hệ thống thật cần Identity Provider, HTTPS, password/secret management, chống brute force và policy tenant/resource.

### 7.4. `src/main/java/demo/reactivecontext/CurrentActorService.java`

~~~java
package demo.reactivecontext;

import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.security.authentication.AnonymousAuthenticationToken;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.ReactiveSecurityContextHolder;
import org.springframework.stereotype.Service;
import reactor.core.publisher.Mono;

@Service
public class CurrentActorService {

    public Mono<String> currentName() {
        return ReactiveSecurityContextHolder.getContext()
                .flatMap(ctx ->
                        Mono.justOrEmpty(ctx.getAuthentication()))
                .filter(auth -> auth.isAuthenticated()
                        && !(auth instanceof AnonymousAuthenticationToken))
                .map(Authentication::getName)
                .switchIfEmpty(Mono.error(
                        new AccessDeniedException(
                                "Authentication required")));
    }

    @PreAuthorize("hasAuthority('DOC_READ')")
    public Mono<String> restrictedMessage() {
        return currentName().map(name -> "READ:" + name);
    }
}
~~~

**Tại sao source này an toàn hơn một `SecurityContextHolder` imperative?**
- `getContext` trả `Mono<SecurityContext>` được resolve ở subscription.
- `Mono.justOrEmpty` xử lý trường hợp Authentication null.
- `filter` không coi anonymous là user đã đăng nhập (anonymous token có thể báo `isAuthenticated` true).
- `switchIfEmpty` ném `AccessDeniedException` khi không xác minh được danh tính; không fallback sang `system`.
- `restrictedMessage` được bảo vệ bởi Spring reactive method security. Nó trả `Mono`, không tự subscribe/block.
- Từ controller, gọi service qua Spring-managed bean proxy; self-invocation vào chính method được annotate có thể bypass interceptors.

### 7.5. `src/main/java/demo/reactivecontext/ReactiveUserController.java`

~~~java
package demo.reactivecontext;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Mono;

@RestController
public class ReactiveUserController {

    private final CurrentActorService actors;

    public ReactiveUserController(CurrentActorService actors) {
        this.actors = actors;
    }

    @GetMapping("/api/public/ping")
    public Mono<String> ping() {
        return Mono.just("pong");
    }

    @GetMapping("/api/me")
    public Mono<String> me() {
        return actors.currentName();
    }

    @GetMapping("/api/restricted")
    public Mono<String> restricted() {
        return actors.restrictedMessage();
    }
}
~~~

Không đọc username/authority từ request body. Controller trả `Mono` để WebFlux subscribe và quản lý cancel/error/lifecycle. Service lấy identity theo ngữ cảnh được Spring Security xác lập.

### 7.6. Kết quả HTTP kỳ vọng

~~~bash
curl -i http://localhost:8080/api/public/ping
curl -i -u alice:alice-pass http://localhost:8080/api/me
curl -i -u bob:bob-pass http://localhost:8080/api/restricted
curl -i -u alice:alice-pass http://localhost:8080/api/restricted
~~~

| Request | HTTP | Body chính |
| --- | --- | --- |
| GET public/ping, anonymous | 200 | `pong` |
| GET /api/me, Alice | 200 | `alice` |
| GET /api/restricted, Bob | 403 | Denied |
| GET /api/restricted, Alice | 200 | `READ:alice` |

Các ví dụ chỉ dành cho local demo. Khi triển khai ngoài máy học, dùng HTTPS và không để credentials trong shell history/scripts công khai.

## 8. Integration tests bằng WebTestClient và StepVerifier

`WebTestClient` đi qua WebFlux security filters khi bind vào ApplicationContext và áp dụng `springSecurity()`. `StepVerifier` là công cụ đúng để xác minh `Mono`/`Flux` và context của mỗi subscription mà không dùng `block()` trong service.

### 8.1. `src/test/java/demo/reactivecontext/ReactiveContextIntegrationTest.java`

~~~java
package demo.reactivecontext;

import java.util.List;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.ApplicationContext;
import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.core.context.ReactiveSecurityContextHolder;
import org.springframework.test.web.reactive.server.WebTestClient;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;
import reactor.core.scheduler.Schedulers;
import reactor.test.StepVerifier;

import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.springSecurity;

@SpringBootTest(
        classes = ReactiveContextApplication.class,
        webEnvironment = SpringBootTest.WebEnvironment.MOCK)
class ReactiveContextIntegrationTest {

    @Autowired ApplicationContext applicationContext;
    @Autowired CurrentActorService actors;

    private WebTestClient client;

    @BeforeEach
    void setup() {
        client = WebTestClient
                .bindToApplicationContext(applicationContext)
                .apply(springSecurity())
                .configureClient()
                .build();
    }

    private Authentication user(String name, String authority) {
        return new UsernamePasswordAuthenticationToken(
                name, "test-only",
                List.of(new SimpleGrantedAuthority(authority)));
    }

    @Test
    void publicPingWithoutLogin() {
        client.get().uri("/api/public/ping")
                .exchange()
                .expectStatus().isOk()
                .expectBody(String.class).isEqualTo("pong");
    }

    @Test
    void anonymousCannotReadCurrentUser() {
        client.get().uri("/api/me")
                .exchange()
                .expectStatus().isUnauthorized();
    }

    @Test
    void httpBasicPrincipalIsVisibleInsideMono() {
        client.get().uri("/api/me")
                .headers(h -> h.setBasicAuth("alice", "alice-pass"))
                .exchange()
                .expectStatus().isOk()
                .expectBody(String.class).isEqualTo("alice");
    }

    @Test
    void bobSeesBobNotAlice() {
        client.get().uri("/api/me")
                .headers(h -> h.setBasicAuth("bob", "bob-pass"))
                .exchange()
                .expectStatus().isOk()
                .expectBody(String.class).isEqualTo("bob");
    }

    @Test
    void methodSecurityDeniesAuthenticatedUserWithoutAuthority() {
        client.get().uri("/api/restricted")
                .headers(h -> h.setBasicAuth("bob", "bob-pass"))
                .exchange()
                .expectStatus().isForbidden();
    }

    @Test
    void methodSecurityAllowsDocReadAuthority() {
        client.get().uri("/api/restricted")
                .headers(h -> h.setBasicAuth("alice", "alice-pass"))
                .exchange()
                .expectStatus().isOk()
                .expectBody(String.class).isEqualTo("READ:alice");
    }

    @Test
    void oneColdMonoTwoSubscribersTwoIdentities() {
        Mono<String> cold = actors.currentName();

        StepVerifier.create(cold.contextWrite(
                ReactiveSecurityContextHolder.withAuthentication(
                        user("alice", "DOC_READ"))))
                .expectNext("alice")
                .verifyComplete();

        StepVerifier.create(cold.contextWrite(
                ReactiveSecurityContextHolder.withAuthentication(
                        user("bob", "DOC_VIEW"))))
                .expectNext("bob")
                .verifyComplete();
    }

    @Test
    void missingContextIsRejected() {
        StepVerifier.create(actors.currentName())
                .expectError(AccessDeniedException.class)
                .verify();
    }

    @Test
    void contextStillWorksAfterSchedulerSwitch() {
        Mono<String> sequence = actors.currentName()
                .publishOn(Schedulers.parallel())
                .map(String::toUpperCase)
                .contextWrite(
                        ReactiveSecurityContextHolder.withAuthentication(
                                user("alice", "DOC_READ")));

        StepVerifier.create(sequence)
                .expectNext("ALICE")
                .verifyComplete();
    }

    @Test
    void nestedFluxOperatorsShareSubscriberContext() {
        Mono<List<String>> values = Flux.range(1, 3)
                .concatMap(i -> actors.currentName()
                        .map(name -> i + ":" + name))
                .collectList()
                .contextWrite(
                        ReactiveSecurityContextHolder.withAuthentication(
                                user("bob", "DOC_VIEW")));

        StepVerifier.create(values)
                .expectNext(List.of("1:bob", "2:bob", "3:bob"))
                .verifyComplete();
    }

    @Test
    void clearContextMasksAuthenticationUpstream() {
        Mono<String> sequence = actors.currentName()
                .contextWrite(
                        ReactiveSecurityContextHolder.clearContext())
                .contextWrite(
                        ReactiveSecurityContextHolder.withAuthentication(
                                user("alice", "DOC_READ")));

        StepVerifier.create(sequence)
                .expectError(AccessDeniedException.class)
                .verify();
    }

    @Test
    void injectedIdentityDrivesReactiveMethodSecurity() {
        StepVerifier.create(actors.restrictedMessage()
                .contextWrite(
                        ReactiveSecurityContextHolder.withAuthentication(
                                user("alice", "DOC_READ"))))
                .expectNext("READ:alice")
                .verifyComplete();

        StepVerifier.create(actors.restrictedMessage()
                .contextWrite(
                        ReactiveSecurityContextHolder.withAuthentication(
                                user("bob", "DOC_VIEW"))))
                .expectError(AccessDeniedException.class)
                .verify();
    }
}
~~~

### 8.2. Ma trận kiểm thử

| Kiểm thử | Kết quả | Chứng minh |
| --- | --- | --- |
| Public ping | 200, pong | Public route vẫn hoạt động |
| No login /api/me | 401 | HTTP layer không nhận anonymous |
| Alice HTTP Basic | alice | User trong Reactor Context đúng |
| Bob HTTP Basic | bob | Không dùng danh tính Alice |
| Bob vào restricted | 403 | Authenticated không đủ authority |
| Alice vào restricted | READ:alice | Method Security allow |
| Cùng một cold Mono, hai subscriptions | Alice rồi Bob | Context riêng cho từng subscriber |
| Không có context trong StepVerifier | AccessDeniedException | Fail closed |
| `publishOn` | ALICE | Context không phụ thuộc một thread |
| `concatMap` và inner Mono | 1:bob, 2:bob, 3:bob | Context được nhìn thấy trong reactive composition |
| `clearContext()` | AccessDeniedException | Nhánh upstream không thấy context |
| Inject test auth vào @PreAuthorize | Alice allow, Bob deny | Method Security dùng Reactive Context |

Đối với các tests inject auth, `withAuthentication` là tiện ích kiểm thử/trusted integration, không phải cơ chế xác thực client. Tests HTTP Basic mới bao gồm authentication filter thực của Spring Security.

### 8.3. Chạy test

~~~bash
./gradlew test --tests demo.reactivecontext.ReactiveContextIntegrationTest
./gradlew bootRun
~~~

Windows:

~~~text
gradlew.bat test --tests demo.reactivecontext.ReactiveContextIntegrationTest
gradlew.bat bootRun
~~~

Mã không có `System.out.println`, nên không có stdout nghiệp vụ cố định. Tiêu chí là assertions đều pass và HTTP status/body đúng. Ví dụ đã được kiểm tra tĩnh; cần chạy trên môi trường Boot 3.x/Security 6.x thực tế trước khi dùng production.

## 9. Các anti-pattern liên quan trực tiếp tới bảo mật

### 9.1. Đọc SecurityContextHolder kiểu imperative trên event loop

~~~java
// SAI CHO WEBFLUX:
public Mono<String> currentNameUnsafe() {
    Authentication auth =
            SecurityContextHolder.getContext().getAuthentication();
    return Mono.just(auth.getName());
}
~~~

Đoạn này đọc context **theo thread hiện tại** khi gọi method, không phải Authentication của Reactor subscription. Thread có thể đổi, context có thể null. Sửa bằng reactive `getContext()` bên trong `Mono`.

### 9.2. `block()` tạo subscription mới, có thể làm mất context

~~~java
// SAI trong event-loop/controller reactive:
public String currentNameBlocking() {
    return ReactiveSecurityContextHolder.getContext()
            .map(ctx -> ctx.getAuthentication().getName())
            .block();
}
~~~

`block()` đợi đồng bộ, có thể gây lỗi trên non-blocking thread và tạo subscription độc lập không mang context mong muốn. Không dùng để đổi `Mono<Authentication>` thành Authentication trong WebFlux request.

Thay bằng:

~~~java
public Mono<String> currentNameReactive() {
    return ReactiveSecurityContextHolder.getContext()
            .flatMap(ctx ->
                    Mono.justOrEmpty(ctx.getAuthentication()))
            .map(Authentication::getName);
}
~~~

### 9.3. Tự subscribe bên trong service

~~~java
// PHẢN VÍ DỤ: publisher mới bị tách khỏi vòng đời HTTP request.
public Mono<String> handle() {
    actorService.currentName().subscribe(name -> audit(name));
    return Mono.just("done");
}
~~~

Code này không propagate lỗi của audit về request, có thể tách context/cancel, và response có thể thành công trước khi audit hoàn tất. `actorService` và `audit` là dependencies minh họa.

Đúng hướng:

~~~java
public Mono<String> handle() {
    return actorService.currentName()
            .flatMap(name -> auditReactive(name)
                    .thenReturn("done"));
}
~~~

`auditReactive` ở đây là method reactive do bạn triển khai riêng. Quan trọng là **compose Mono/Flux**, để framework làm subscriber và quản lý lỗi.

### 9.4. Global Mono.cache() có thể rò rỉ user

~~~java
// CỰC KỲ NGUY HIỂM nếu giữ publisher trong singleton/global:
Mono<String> cachedCurrentUser =
        actorService.currentName().cache();
~~~

`Mono.cache()` lưu **result từ lần subscribe đầu**. Lần tiếp theo, dù subscriber có Authentication của user khác, nó có thể được trả lại tên user đầu tiên. `Reactor Context` của subscriber mới không tự invalid cache result đã tính.

Nguyên tắc:
- Không cache publisher có giá trị phụ thuộc Authentication **xuyên các request**.
- Nếu cache domain data, key phải chứa principal/tenant/resource/action/policy revision hợp lệ.
- Thiết kế TTL/revocation/authorization-invalidation phù hợp.
- Không đưa user-specific Mono vào singleton mutable field rồi chia cho mọi caller.

### 9.5. Tự tạo Authentication từ header chưa xác minh

~~~java
// PHẢN VÍ DỤ: X-User/X-Role từ client không phải identity tin cậy.
Authentication forged =
        new UsernamePasswordAuthenticationToken(
                userHeader,
                "ignored",
                List.of(new SimpleGrantedAuthority("ROLE_ADMIN")));

return service.readSecret().contextWrite(
        ReactiveSecurityContextHolder.withAuthentication(forged));
~~~

`withAuthentication` **không xác minh** username, role, chữ ký JWT hay credential; nó chỉ gắn một object được cung cấp vào Reactor Context. Không dùng đầu vào không đáng tin để tự nhận đó là authenticated principal.

### 9.6. Tenant context là selector, không phải quyền

~~~java
Mono<String> response = service.readDocument()
        .contextWrite(Context.of("tenantId", requestedTenant));
~~~

Nếu `requestedTenant` đến từ URL/header, nó chỉ là tenant muốn thao tác; chưa được authorize. Phải kiểm tra actor có membership đúng tenant và tài nguyên thật sự thuộc tenant đó. Reactor Context **chuyển dữ liệu, không chứng minh độ tin cậy** của dữ liệu.

## 10. Thay đổi scheduler và các boundary ngoài Reactor

### 10.1. publishOn, subscribeOn

~~~java
Mono<String> pipeline = actors.currentName()
        .publishOn(Schedulers.parallel())
        .map(String::toUpperCase)
        .contextWrite(
                ReactiveSecurityContextHolder.withAuthentication(
                        trustedAuthentication));
~~~

`trustedAuthentication` trong ví dụ là một Authentication đã được xác thực, không phải user do request tự khai. Reactor Context được truyền khi pipeline dùng `publishOn` hoặc `subscribeOn` đúng cách; điều đó không có nghĩa mọi `ThreadLocal` của một thư viện khác tự có cùng giá trị.

### 10.2. Ranh giới dễ mất context

| Boundary | Điều không nên giả định | Cách tiếp cận |
| --- | --- | --- |
| `new Thread`/`Executor.submit` | Child thread tự có security context | Truyền trusted actor explicit hoặc bridge có kiểm soát |
| `CompletableFuture.supplyAsync` | Future tự thấy Reactor Context | Sử dụng context propagation được hỗ trợ |
| Detached `subscribe()` | Subscription mới tự giữ auth HTTP | Compose vào pipeline gốc |
| Remote WebClient | Reactor Context tự gửi Bearer token | OAuth2 authorized client/token relay có scope |
| Kafka/Rabbit consumer | Có user HTTP của producer trong memory | Xác minh source command/service principal |
| Scheduled job | Có người dùng đăng nhập gần nhất | Service identity với least privilege |
| `Mono.cache()` global | Result tự phân vùng theo principal | Không chia sẻ cached user result |
| Custom context replacement | Giữ lại Spring Security key | Merge/contextWrite đúng, tránh xóa toàn bộ |

### 10.3. Micrometer Context Propagation và MDC

Reactor hỗ trợ Context Propagation ở các phiên bản gần đây, có thể tích hợp Micrometer Context Propagation và những `ThreadLocalAccessor` đã đăng ký. `contextCapture()` hoặc `Hooks.enableAutomaticContextPropagation()` hữu ích khi phải bridge data giữa Reactor Context và ThreadLocal của thư viện logging/tracing.

Nhưng không được suy ra:
- Bật hook là tự xác thực user.
- Tự chuyển principal qua network.
- Có thể phục hồi context cho một subscription detached không có nguồn gốc đúng.
- Sửa được lỗi cached Mono result rò từ user trước.
- Mọi ThreadLocal, kể cả security context imperative, đều tự khớp nếu chưa cấu hình accessor/version.

Với Spring WebFlux, vẫn ưu tiên `ReactiveSecurityContextHolder` làm nguồn Authentication trong reactive flow. MDC/traceId là một concern khác, không nên chứa raw token hoặc mật khẩu.

## 11. Reactive Method Security vẫn cần resource authorization

Một rule:

~~~java
@PreAuthorize("hasAuthority('DOC_READ')")
public Mono<Document> getById(Long id) {
    return repository.findById(id);
}
~~~

là **đoạn mô hình**, chưa có `Document` và `repository`. Nó kiểm tra authority chung, không tự kiểm document thuộc tenant nào, owner là ai hay trạng thái locked. Nếu Alice chỉ có quyền với ACME, `DOC_READ` không đồng nghĩa Alice được đọc mọi document BETA.

Một policy đầy đủ có thể yêu cầu:

~~~text
authenticated(actor)
AND hasAuthority(actor, "DOC_READ")
AND activeMembership(actor, targetTenant)
AND document.tenantId == targetTenant
AND permissionEvaluator.hasPermission(actor, document, "READ")
AND document.status != LOCKED
~~~

Đặt chốt ở service/repository ngoài HTTP URL rule, vì cùng use case có thể bị gọi từ GraphQL, background worker hay message consumer. Cũng cần lưu ý `@PreAuthorize` trên reactive publisher phải đi qua Spring proxy; self-invocation có thể không được intercept.

## 12. Authentication/Session/Logout là câu chuyện khác clearContext

Một security context trong Reactor Context tồn tại ở một subscription hoặc phạm vi operator. Không nhầm:

- `ReactiveSecurityContextHolder.clearContext()`: xóa entry trong một nhánh.
- Logout HTTP: làm sạch SecurityContext repository/session/cookie theo cấu hình.
- JWT revocation: làm mất hiệu lực token/entitlement theo protocol, không chỉ gỡ context cục bộ.
- Role revocation: cập nhật IAM/policy/cache, chưa chắc được thấy ngay trong JWT cũ.
- MFA/step-up: authentication requirement tùy action, không tự được thực hiện khi đọc context.

Nếu một access token hết hạn hoặc một user bị khóa giữa lúc request đang chạy, hệ thống cần hợp đồng revocation/consistency riêng cho các hành động nhạy cảm. “Reactive context còn thấy Alice” không chứng minh Alice vẫn có quyền ở thời điểm domain mutation.

## 13. Background jobs, WebClient và message consumers

### Scheduled jobs

Một `@Scheduled` job không tự có HTTP principal. Hãy dùng service identity minh bạch với minimal scope:

~~~text
actorType=SERVICE
actorId=nightly-indexer
tenantScope=acme
permissions=[DOC_INDEX]
jobId=nightly-2026
~~~

Nếu tạo trusted service Authentication và `withAuthentication`, cần audit và cấp quyền tối thiểu. Đừng dùng `ROLE_SYSTEM_ADMIN` chung cho mọi task.

### WebClient

~~~java
return webClient.get()
        .uri("/documents/{id}", id)
        .retrieve()
        .bodyToMono(DocumentView.class);
~~~

Code trên chỉ minh họa vì `webClient` và `DocumentView` cần được cấu hình riêng. Local Reactor Context **không tự** tạo Authorization header hợp lệ cho dịch vụ khác. Token relay hay client credentials phải có filter/authorized-client integration phù hợp, audience và scope đúng. Không forward mọi header inbound đến host tùy ý.

### Message consumers

Một message chứa `principalId`/`tenantId` không tự chứng minh producer được phép nhân danh user đó. Consumer phải xác minh producer/service identity, signature/trust, replay, tenant scope và policy tại thời điểm xử lý. Không gọi `withAuthentication` từ message body chưa được xác minh rồi coi là Authentication hợp lệ.

## 14. Reactive transaction và Reactor SecurityContext là hai context khác nhau

Trong Spring Reactive Transaction Management, transaction cũng có thể dùng Reactor Context để giữ transaction state. Nhưng:

| Concern | Ngữ cảnh liên quan | Ý nghĩa |
| --- | --- | --- |
| Security | `Mono<SecurityContext>` | Ai đang gọi, authorities |
| Transaction | Reactive transaction metadata | Commit/rollback các thao tác tham gia |
| Tracing | Trace/span/correlation | Theo dõi request |
| Tenant | Tenant selection/membership | Phạm vi dữ liệu |

Có Authentication trong Reactor Context **không tự mở transaction**. Có transaction **không chứng minh actor có quyền**. Khi mutate domain data, cần authorization đúng resource và transaction/locking phù hợp.

Không thay toàn bộ Context bằng context rỗng một cách tùy tiện; có thể làm mất cả security và transaction/tracing metadata cần thiết. Dùng API của từng framework và `contextWrite(ctx -> ctx.put(...))` khi thêm key mới.

## 15. Những lỗi thường gặp

| Hiện tượng | Nguyên nhân | Khắc phục |
| --- | --- | --- |
| `getContext()` rỗng trong StepVerifier | Không gắn test auth | `contextWrite(withAuthentication(...))` |
| HTTP login thành công nhưng service thiếu principal | Detached subscription/custom async boundary | Compose chain; test WebTestClient |
| `SecurityContextHolder.getContext()` null sau publishOn | Dùng imperative ThreadLocal trong reactive | ReactiveSecurityContextHolder |
| Bob nhìn thấy tên Alice | Shared `Mono.cache()`/singleton state | Không cache kết quả theo user toàn cục |
| `contextWrite` không có tác dụng | Đặt sai phía reader | Writer downstream của reader |
| `clearContext` mà user vẫn có session | Clear local entry không logout | Thiết kế logout/revocation riêng |
| `@PreAuthorize` không chạy | Thiếu `@EnableReactiveMethodSecurity` hoặc proxy | Bật đúng annotation/test bean injected |
| Bob `restricted` được phép | Authority mapping/proxy sai | Test HTTP 403 + service reactive |
| API trả 401 | Không có Authentication hợp lệ | Kiểm HTTP Basic/JWT filter |
| API trả 403 | Role thiếu hoặc CSRF | Tách positive/negative HTTP tests |
| `block()` ném lỗi event-loop | Blocking reactive thread | Compose Mono/Flux |
| CompletableFuture không thấy security | Không tự hiểu Reactor Context | Explicit actor/capture/bridge |
| MDC không có traceId | Logger ThreadLocal thiếu context propagation | Cấu hình Micrometer đúng version |
| Job xử lý bằng user cũ | Reuse global/ThreadLocal state | Service identity riêng |
| WebClient downstream 401 | Không truyền token theo policy | OAuth2 client/filter có scope |
| Truy cập chéo tenant | Có identity nhưng thiếu domain check | Tenant-scoped queries + permissions |
| Anonymous được tính authenticated | Chỉ check flag `isAuthenticated()` | Filter anonymous/trust resolver |
| Token revoked nhưng request vẫn allow | Cache/JWT cũ | Revocation strategy, version hoặc policy lookup |

## 16. Checklist review WebFlux security context

1. Sử dụng WebFlux `SecurityWebFilterChain` thay vì servlet `HttpSecurity`?
2. `ReactiveSecurityContextHolder.getContext()` dùng trong Publisher đúng subscription?
3. Có fail closed nếu Authentication null, anonymous hoặc context rỗng?
4. Không gọi `block()` trên event-loop, không tự `subscribe()` trong controller/service?
5. Không để tên user/Authentication trong singleton mutable field hoặc global `Mono.cache()`?
6. Các operator `contextWrite` nằm đúng downstream so với reader cần truy cập?
7. `publishOn`/`subscribeOn` và inner `flatMap` đã được test?
8. Có kiểm thử hai users với cùng cold Publisher nhưng contexts khác nhau?
9. Không tự dựng authenticated principal từ request/header chưa được xác minh?
10. `@EnableReactiveMethodSecurity` bật và methods có reactive return type?
11. Methods protected được gọi qua Spring-managed proxies, không self-invocation?
12. Quyền theo tenant/document được xét riêng, không chỉ authority toàn cục?
13. Background jobs và message consumers dùng trusted identity và minimal scope?
14. WebClient OAuth2/token relay chỉ gửi token đúng destination/audience?
15. ThreadLocal/MDC bridge có accessor/version và không coi là security primitive?
16. Reactive transaction và SecurityContext tách trách nhiệm rõ ràng?
17. HTTP test gắn đủ Spring Security filters, StepVerifier test đúng subscription?
18. Logs đã redact password/JWT, trace/security metadata không lộ dữ liệu?

## 17. Bài tập thực hành

**Bài 1 – Hai subscribers.** Tạo một cold `Mono` từ `currentName()` và subscribe hai lần với Alice/Bob. Dùng `withAuthentication` cho mỗi subscription; kiểm tra kết quả độc lập.

**Bài 2 – Vị trí contextWrite.** Thử `Mono.deferContextual` đọc traceId với `contextWrite` trước/sau reader. Giải thích vì sao một trường hợp ra `missing`.

**Bài 3 – Clear context.** Ghép `currentName().contextWrite(clearContext()).contextWrite(withAuthentication(alice))`. Dùng StepVerifier xác nhận fail closed; giải thích vì sao đó không phải logout HTTP.

**Bài 4 – Scheduler.** Dùng `publishOn(Schedulers.parallel())` và `subscribeOn(Schedulers.boundedElastic())` trên cùng pipeline. So sánh Reactive SecurityContext với `ThreadLocal`; không dùng `block()` trong event loop.

**Bài 5 – Leak qua cache.** Thử tạo một `Mono.cache()` dùng chung để đọc currentName, cho Alice subscribe trước rồi Bob. Xem rủi ro rò tên và sửa bằng cách không share cache phụ thuộc principal.

**Bài 6 – Method Security.** Thêm method `@PreAuthorize("hasAuthority('DOC_EXPORT')")` trả Mono. Kiểm thử account đủ và thiếu authority bằng StepVerifier/WebTestClient.

**Bài 7 – Tenant scope.** Bổ sung reactive repository query theo documentId + tenantId, kiểm membership và policy tài nguyên. Test user tenant ACME không đọc document BETA dù Authentication hợp lệ.

**Bài 8 – Detached task.** Tạo `CompletableFuture`/`subscribe()` tách request, quan sát thiếu context; thay bằng `flatMap`/reactive composition hoặc explicit trusted actor boundary.

**Bài 9 – WebClient.** Test local context hợp lệ nhưng downstream không có Bearer token; bổ sung OAuth2 authorized client và kiểm scope/audience.

**Bài 10 – Correlation ID.** Dùng Reactor Context + `deferContextual` truyền traceId qua các operator. Đánh giá MDC ThreadLocal và cơ chế context propagation khi đổi scheduler.

**Tiêu chí hoàn thành:** hiểu Reactor Context theo Subscriber, phân biệt `SecurityContextHolder` với `ReactiveSecurityContextHolder`, sử dụng đúng `getContext`/`withAuthentication`/`withSecurityContext`/`clearContext`, đặt `contextWrite` đúng vị trí, tránh block/subscribe/cache user result, bật Reactive Method Security và kiểm thử HTTP + reactive subscriptions.

## 18. Tài liệu tham khảo chính thức

- Spring Security – **ReactiveSecurityContextHolder API**: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/core/context/ReactiveSecurityContextHolder.html
- Spring Security – **Reactive Method Security**, `@EnableReactiveMethodSecurity` và Reactor Context: https://docs.spring.io/spring-security/reference/reactive/authorization/method.html
- Spring Security – **WebFlux Security Configuration**: https://docs.spring.io/spring-security/reference/reactive/configuration/webflux.html
- Spring Security – **Testing WebFlux Authentication**: https://docs.spring.io/spring-security/reference/reactive/test/web/authentication.html
- Spring Security – **WebTestClient Security Setup**: https://docs.spring.io/spring-security/reference/reactive/test/web/setup.html
- Spring Security – **Method Security Tests** và `ReactorContextTestExecutionListener`: https://docs.spring.io/spring-security/reference/servlet/test/method.html
- Project Reactor – **Adding a Context to a Reactive Sequence**: https://projectreactor.io/docs/core/release/reference/advancedFeatures/context.html
- Project Reactor – **Context Propagation Support**: https://projectreactor.io/docs/core/release/reference/advancedFeatures/contextPropagation.html
- Spring Framework – **Transaction Management**: https://docs.spring.io/spring-framework/reference/data-access/transaction/programmatic.html
