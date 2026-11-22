# Thiết lập Reactor Context trong kiểm thử đơn vị Spring Security Reactive

> **Phạm vi:** Java 17+, Project Reactor, Spring Security 6.x, JUnit 5 và `reactor-test`. Mục tiêu là tự đưa `Authentication` / `SecurityContext` vào **Reactor Context** của từng subscription trong unit test, kiểm thử đúng cả trường hợp có/không có danh tính, roles/scopes và mất/ngăn rò context. Bài tập trung vào **kiểm thử đơn vị** không cần HTTP server; cuối bài phân biệt với `@WithMockUser` và `WebTestClient`. Mốc ví dụ Spring Boot 3.3.13 dùng để minh họa API tương thích Java 17; production năm 2026 nên chọn phiên bản Spring Boot/Security được hỗ trợ và vá lỗi mới nhất theo môi trường.

## 1. Vì sao cần tự thiết lập Reactor Context khi test?

Trong ứng dụng WebFlux, Spring Security thường cài `SecurityContext` vào Reactor Context trong luồng HTTP đã đi qua các Security WebFilters. Ví dụ một service đọc người dùng hiện tại:

```java
Mono<String> name = ReactiveSecurityContextHolder.getContext()
    .map(SecurityContext::getAuthentication)
    .map(Authentication::getName);
```

Khi chạy trong một request đã xác thực, publisher có thể nhìn thấy authentication do Spring Security thiết lập. Nhưng một **unit test thuần JUnit** tạo service bằng `new` không có `SecurityWebFilterChain`, HTTP request, WebSession, `ReactorContextWebFilter` hoặc Spring Test listener chạy trước. Vì thế:

```java
StepVerifier.create(service.whoAmI())
    .expectNext("alice") // SAI nếu không ai đặt context cho subscription
    .verifyComplete();
```

không có cơ sở để thành công. `ReactiveSecurityContextHolder.getContext()` thường tạo một publisher **rỗng** nếu subscription không có security context; nếu service chuyển trạng thái rỗng thành lỗi, test sẽ nhận lỗi đó.

Cách tạo tình huống xác thực cho unit test:

```java
Authentication alice =
    new TestingAuthenticationToken(
        "alice", "not-a-real-password", "ROLE_USER");

StepVerifier.create(
        service.whoAmI()
            .contextWrite(
                ReactiveSecurityContextHolder.withAuthentication(alice)))
    .expectNext("alice")
    .verifyComplete();
```

Đây là **mảnh code** cần imports và `service.whoAmI()`. Nó mô phỏng danh tính **đã được xác thực**. Nó **không** chạy password authentication, JWT signature verification, WebFilter hay CSRF check. Để kiểm những thứ đó cần integration tests riêng.

## 2. Reactor Context khác ThreadLocal và Java method parameters

Trước khi kiểm Spring Security, phải hiểu Project Reactor:

| Thành phần | Scope / đặc tính | Dùng cho |
|---|---|---|
| `ThreadLocal<T>` | Gắn vào Java thread; thread có thể tái sử dụng hoặc thay đổi giữa callbacks | Imperative thread-bound code, nếu quản lý lifecycle đúng |
| `SecurityContextHolder` | Theo strategy thông thường dùng ThreadLocal | Spring Security Servlet/imperative hoặc tích hợp có bridge |
| `reactor.util.context.Context` | Dữ liệu immutable gắn với **subscriber** và truyền khi subscribe | Correlation ID, tracing metadata, reactive security context |
| `ContextView` | API chỉ đọc dữ liệu context | Lấy giá trị từ `Mono.deferContextual` / `Flux.deferContextual` |
| `ReactiveSecurityContextHolder` | Truy xuất/ghi Spring `SecurityContext` vào Reactor Context | Spring Security WebFlux/method security |
| `Authentication` | Principal, authorities và trạng thái xác thực | Mô tả danh tính đã được cơ chế tin cậy xác nhận |
| `SecurityContext` | Bao `Authentication` | Truyền authentication theo scope reactive |

Trong Reactor, **một subscription khác có thể chạy trên cùng thread** và **một subscription có thể nhảy qua nhiều thread**. Vì vậy “đặt user vào `SecurityContextHolder.getContext()` trong `@BeforeEach`” **không** phải cách chắc chắn để service reactive đọc được user.

```text
Thread event-loop-1:
  subscription #1 (Alice)  -> Context của Alice
  subscription #2 (Bob)    -> Context của Bob

Thread boundedElastic-2:
  subscription #1 (Alice)  -> vẫn có Context của Alice khi đi qua
                              các Reactor operators có propagate context

Không được suy:
  event-loop-1 mang Alice -> mọi callback trên thread đó là Alice
```

### 2.1 Context immutable, gắn vào subscription

`Context` có `put`/`delete` nhưng trả **một Context mới**. Nó không phải mutable global map. Khi viết:

```java
Mono<String> pipeline = Mono.deferContextual(view ->
        Mono.just(view.getOrDefault("traceId", "none")))
    .contextWrite(ctx -> ctx.put("traceId", "t-309"));
```

`contextWrite` tạo context mới cho **upstream operators**. Dữ liệu context được “đưa ngược” theo hướng subscription từ downstream lên upstream. Nó **không** phải một giá trị được mang kèm mỗi `onNext` hoặc một biến ThreadLocal.

### 2.2 Đặt `contextWrite` đúng phía

```java
// ĐÚNG: chỗ đọc context ở upstream của contextWrite.
Mono<String> correct = Mono.deferContextual(view ->
        Mono.just(view.getOrDefault("k", "none")))
    .contextWrite(Context.of("k", "visible"));

// SAI VỊ TRÍ: flatMap nằm downstream của contextWrite,
// nên inner publisher không nhìn thấy k đã ghi ở upstream.
Mono<String> wrong = Mono.just("go")
    .contextWrite(Context.of("k", "hidden"))
    .flatMap(ignored -> Mono.deferContextual(view ->
        Mono.just(view.getOrDefault("k", "none"))));
```

Kết quả mong đợi:

```text
correct -> "visible"
wrong   -> "none"
```

**Quy tắc thực dụng cho unit test:** đặt `.contextWrite(ReactiveSecurityContextHolder.withAuthentication(alice))` ở **cuối pipeline cần test**, sau toàn bộ `map`/`flatMap`/`publishOn` quan trọng. Trường hợp muốn kiểm việc context bị mất do operator sai vị trí, đặt cố ý ở vị trí khác và assert lỗi.

## 3. Các API Spring Security phải nhớ

`org.springframework.security.core.context.ReactiveSecurityContextHolder` có bốn API chủ đạo:

| Phương thức | Kiểu trả về | Ý nghĩa |
|---|---|---|
| `getContext()` | `Mono<SecurityContext>` | Lấy security context từ Reactor Context của subscriber |
| `withAuthentication(Authentication)` | `Context` | Tạo Context chứa security context của một Authentication |
| `withSecurityContext(Mono<? extends SecurityContext>)` | `Context` | Tạo Context chứa publisher phát SecurityContext |
| `clearContext()` | `Function<Context, Context>` | Xóa entry Spring Security khỏi Reactor Context của đoạn upstream |

Ví dụ:

```java
Authentication alice =
    UsernamePasswordAuthenticationToken.authenticated(
        "alice", "unused-in-unit-test",
        List.of(new SimpleGrantedAuthority(
            "SCOPE_documents.read")));

Mono<String> current = ReactiveSecurityContextHolder.getContext()
    .map(SecurityContext::getAuthentication)
    .map(Authentication::getName);

StepVerifier.create(
        current.contextWrite(
            ReactiveSecurityContextHolder.withAuthentication(alice)))
    .expectNext("alice")
    .verifyComplete();
```

Đây là mảnh code với imports ngầm định. `withAuthentication` **không phải login endpoint**: không gọi `ReactiveAuthenticationManager`, không kiểm password, không gọi IdP, không verify token. Chỉ dùng trong các tests cô lập một component giả định đã nhận verified authentication, hoặc trong code framework đã được tin cậy.

### 3.1 Không đoán key nội bộ của Spring Security

`ReactiveSecurityContextHolder` tự quản lý entry trong Reactor Context. **Không** viết:

```java
// SAI: không tương đương với API Spring Security.
Context.of(SecurityContext.class, new SecurityContextImpl(alice));
```

Spring Security dùng key/giá trị theo implementation của nó (bao gồm publisher `Mono<SecurityContext>`). Chỉ dùng `withAuthentication` hoặc `withSecurityContext`, đừng tự đặt tên key literal `"SPRING_SECURITY_CONTEXT"` hay suy từ các bài blog cũ.

### 3.2 `clearContext()` không phải “đăng xuất toàn hệ thống”

`clearContext` xóa security context **trong Reactor Context upstream của publisher được áp dụng**. Nó không hủy WebSession, JWT, cookie, refresh token, không phát sự kiện revoke và không xóa mọi subscriber. Nó rất có ích để test một branch mà **không có** SecurityContext dù branch bên ngoài từng có.

### 3.3 Với SecurityContext có sẵn

Nếu cần thể hiện cả security context object:

```java
SecurityContext context = new SecurityContextImpl();
context.setAuthentication(alice);

Mono<String> pipeline = service.whoAmI()
    .contextWrite(ReactiveSecurityContextHolder
        .withSecurityContext(Mono.just(context)));
```

`withSecurityContext` nhận **Mono<? extends SecurityContext>`, không nhận trực tiếp `SecurityContext`. Có thể dùng `Mono.defer` / `Mono.fromSupplier` khi muốn quan sát tính lazy hoặc đưa một context được tạo lúc subscribe.

## 4. Không có context là gì?

Ba tình huống thường bị trộn:

1. **Không có Reactor security context entry:** `ReactiveSecurityContextHolder.getContext()` hoàn thành rỗng.
2. **Có SecurityContext nhưng không có Authentication:** `getAuthentication()` có thể là `null`; component phải xử lý thay vì `map(SecurityContext::getAuthentication)` khiến Reactor phát NullPointerException.
3. **Có AnonymousAuthenticationToken:** một số loại anonymous Authentication có `isAuthenticated() == true` về mặt object state; điều đó **không** chứng tỏ user đã xác thực thật.

Khi thiết kế một service tự kiểm quyền trong bài lab, dùng `AuthenticationTrustResolverImpl.isAnonymous(...)` hoặc cơ chế authorization chuẩn của Spring Security để phân biệt anonymous với user thật. Không viết duy nhất:

```java
// THIẾU để kết luận user thực đã login:
if (authentication.isAuthenticated()) { allow(); }
```

Với ứng dụng thật, ưu tiên `@PreAuthorize`/`ReactiveAuthorizationManager` và business ACL, không tự tạo authentication bằng cách tin header “X-User”.

## 5. Chuẩn bị dự án Java 17+ để chạy unit tests không khởi động server

Mẫu này **không cần Spring Boot Application class, không có controller/Netty**, và dùng một service Java thuần có import Spring Security. Spring Boot dependency management cung cấp các phiên bản Spring Security/Reactor tương thích.

```text
reactive-context-unit-tests/
  settings.gradle
  build.gradle
  src/main/java/example/context/DocumentService.java
  src/test/java/example/context/DocumentServiceTest.java
```

**settings.gradle**

```groovy
rootProject.name = 'reactive-context-unit-tests'
```

**build.gradle**

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.13' apply false
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'example.context'
version = '1.0.0'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

// Không áp dụng boot plugin cho ứng dụng không có main method.
// Chỉ import BOM để quản lý phiên bản dependency.
dependencyManagement {
    imports {
        mavenBom org.springframework.boot.gradle.plugin
            .SpringBootPlugin.BOM_COORDINATES
    }
}

dependencies {
    implementation 'org.springframework.security:spring-security-core'
    implementation 'io.projectreactor:reactor-core'

    testImplementation 'org.junit.jupiter:junit-jupiter'
    testImplementation 'io.projectreactor:reactor-test'
    testImplementation 'org.springframework.security:spring-security-test'

    testRuntimeOnly 'org.junit.platform:junit-platform-launcher'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

**Lưu ý build file:** Cú pháp `org.springframework.boot.gradle.plugin.SpringBootPlugin.BOM_COORDINATES` nằm ở Gradle build script và thuộc plugin Spring Boot. Một lựa chọn khác là áp dụng `org.springframework.boot` và dependency-management rồi thêm `spring-boot-starter-test`, nhưng khi không có main class, tránh nhiệm vụ `bootJar` yêu cầu tìm main. `test` của Java plugin không đòi chạy web server.

Tài liệu Spring Boot 3.3.x BOM quản lý `spring-security-core`, `reactor-core`, `reactor-test` và JUnit 5. Có thể viết nhanh hơn bằng:

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.13'
    id 'io.spring.dependency-management' version '1.1.6'
}
bootJar { enabled = false }
jar { enabled = true }
```

Đây là **phương án build thay thế** cần giữ `dependencies`/`repositories` của mẫu chính, không dán đồng thời hai blocks `plugins`. Với bài lab thuần unit test, cách chỉ dùng Java plugin và BOM của mẫu chính giúp tránh tạo một Spring Boot app thừa.

### 5.1 Vì sao không cần SecurityWebFilterChain?

Các test ở đây không kiểm HTTP authentication hoặc CSRF. Chúng test **một service đọc Reactor SecurityContext**, tự cung cấp verified identity giả lập. Do đó không cần `@SpringBootTest`, `@AutoConfigureWebTestClient`, `@EnableWebFluxSecurity` hoặc `SecurityWebFilterChain`.

Nếu muốn kiểm Security WebFilters thực sự, tạo integration tests bằng `WebTestClient` và `spring-security-test`, xem mục 12; **không** gọi pure unit test là E2E.

## 6. Service có logic nghiệp vụ để kiểm security context

**src/main/java/example/context/DocumentService.java**

```java
package example.context;

import java.util.Objects;

import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.authentication.AuthenticationCredentialsNotFoundException;
import org.springframework.security.authentication.AuthenticationTrustResolver;
import org.springframework.security.authentication.AuthenticationTrustResolverImpl;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.ReactiveSecurityContextHolder;
import org.springframework.security.core.context.SecurityContext;

import reactor.core.publisher.Mono;

public final class DocumentService {

    private final AuthenticationTrustResolver trust =
        new AuthenticationTrustResolverImpl();

    public Mono<String> whoAmI() {
        return verifiedAuthentication()
            .map(Authentication::getName);
    }

    public Mono<String> read(String documentId) {
        return requireAuthority("SCOPE_documents.read")
            .map(auth -> "READ|" + documentId + "|" + auth.getName());
    }

    public Mono<String> write(String documentId) {
        return requireAuthority("SCOPE_documents.write")
            .map(auth -> "WRITE|" + documentId + "|" + auth.getName());
    }

    // Không dựa vào ThreadLocal: traceId là context key của bài lab.
    public Mono<String> whoAmIWithTrace() {
        return Mono.deferContextual(view ->
            whoAmI().map(name ->
                view.getOrDefault("traceId", "none")
                    + ":" + name));
    }

    private Mono<Authentication> verifiedAuthentication() {
        return ReactiveSecurityContextHolder.getContext()
            .flatMap(security ->
                Mono.justOrEmpty(security.getAuthentication()))
            .filter(auth -> auth.isAuthenticated()
                && !trust.isAnonymous(auth))
            .switchIfEmpty(Mono.error(
                new AuthenticationCredentialsNotFoundException(
                    "Authenticated Reactor SecurityContext required")));
    }

    private Mono<Authentication> requireAuthority(String authority) {
        return verifiedAuthentication().flatMap(auth -> {
            boolean granted = auth.getAuthorities().stream()
                .anyMatch(a -> authority.equals(a.getAuthority()));
            return granted ? Mono.just(auth)
                : Mono.error(new AccessDeniedException(
                    "Missing authority: " + authority));
        });
    }
}
```

**Cách đọc service:**

1. `ReactiveSecurityContextHolder.getContext()` được đọc bên trong publisher ở lúc subscribe; không lấy một global object trong constructor.
2. `flatMap(... Mono.justOrEmpty(...))` xử lý đúng một `SecurityContext` chứa `null` Authentication. Không dùng `map` trả `null` vì Reactor cấm emission null.
3. `AuthenticationTrustResolverImpl` nhận diện anonymous token chuẩn; kết hợp `isAuthenticated()` làm lab rõ nghĩa. Framework method security có logic đầy đủ hơn cho từng loại authentication; hãy ưu tiên API built-in ở production.
4. `switchIfEmpty(Mono.error(...))` biến trường hợp không có verified user thành **lỗi có thể test được**, thay vì service âm thầm trả `Mono.empty()` rồi controller tưởng không có gì sai.
5. `SCOPE_documents.read` và `SCOPE_documents.write` là authorities **riêng**. User chỉ có read không được write; auth không tự đồng nghĩa có quyền mọi document.
6. `documentId` chỉ được đưa vào chuỗi minh họa, **chưa có object-level authorization/tenant ownership**. Trong production, bổ sung ACL và database query predicates theo document ID/tenant.
7. `whoAmIWithTrace()` dùng `Mono.deferContextual` lấy một key của **bài lab**; nó không chạm private key của Spring Security.
8. Tất cả methods trả `Mono<String>`; không `block()`, `subscribe()` thủ công trong service.
9. Không ghi credential ra log; nội dung string chỉ chứa user name mock và document ID lab.

**Ranh giới quan trọng:** unit test gắn một `Authentication` đã “authenticated” vào context để kiểm hành vi service. Điều đó **không chứng minh** HTTP bearer JWT, password hoặc cookie thực sự được kiểm. Tách authentication protocol tests ra khỏi method/business policy tests.

## 7. Test đầy đủ với StepVerifier và Reactor Context

**src/test/java/example/context/DocumentServiceTest.java**

```java
package example.context;

import static org.junit.jupiter.api.Assertions.assertEquals;

import java.util.Arrays;
import java.util.List;
import java.util.Set;

import org.junit.jupiter.api.Test;
import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.authentication.AnonymousAuthenticationToken;
import org.springframework.security.authentication.AuthenticationCredentialsNotFoundException;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.core.authority.AuthorityUtils;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.core.context.ReactiveSecurityContextHolder;
import org.springframework.security.core.context.SecurityContext;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.security.core.context.SecurityContextImpl;

import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;
import reactor.core.scheduler.Schedulers;
import reactor.test.StepVerifier;
import reactor.test.StepVerifierOptions;
import reactor.util.context.Context;

class DocumentServiceTest {

    private final DocumentService service = new DocumentService();

    private static Authentication user(
            String name, String... authorities) {

        List<GrantedAuthority> granted = Arrays.stream(authorities)
            .map(a -> (GrantedAuthority)
                new SimpleGrantedAuthority(a))
            .toList();

        // Factory này tạo một Authentication đã authenticated.
        // Chỉ dùng trong test của component phía sau authentication.
        return UsernamePasswordAuthenticationToken.authenticated(
            name, "not-a-real-password", granted);
    }

    @Test
    void missingContextFailsClosed() {
        StepVerifier.create(service.whoAmI())
            .expectError(
                AuthenticationCredentialsNotFoundException.class)
            .verify();
    }

    @Test
    void aliceInReactorContextCanRead() {
        Authentication alice = user(
            "alice", "SCOPE_documents.read");

        StepVerifier.create(
                service.read("doc-1")
                    .contextWrite(ReactiveSecurityContextHolder
                        .withAuthentication(alice)))
            .expectNext("READ|doc-1|alice")
            .verifyComplete();
    }

    @Test
    void readAuthorityDoesNotImplyWriteAuthority() {
        Authentication alice = user(
            "alice", "SCOPE_documents.read");

        StepVerifier.create(
                service.write("doc-1")
                    .contextWrite(ReactiveSecurityContextHolder
                        .withAuthentication(alice)))
            .expectError(AccessDeniedException.class)
            .verify();
    }

    @Test
    void bobWithWriteAuthorityCanWrite() {
        Authentication bob = user(
            "bob", "SCOPE_documents.write");

        StepVerifier.create(
                service.write("doc-2")
                    .contextWrite(ReactiveSecurityContextHolder
                        .withAuthentication(bob)))
            .expectNext("WRITE|doc-2|bob")
            .verifyComplete();
    }

    @Test
    void missingWritePermissionAndNoAuthenticationDiffer() {
        Authentication alice = user(
            "alice", "SCOPE_documents.read");

        StepVerifier.create(
                service.write("doc-3")
                    .contextWrite(ReactiveSecurityContextHolder
                        .withAuthentication(alice)))
            .expectError(AccessDeniedException.class)
            .verify();

        StepVerifier.create(service.write("doc-3"))
            .expectError(
                AuthenticationCredentialsNotFoundException.class)
            .verify();
    }

    @Test
    void unauthenticatedObjectIsNotAccepted() {
        Authentication candidate =
            UsernamePasswordAuthenticationToken.unauthenticated(
                "mallory", "unverified-password");

        StepVerifier.create(
                service.whoAmI()
                    .contextWrite(ReactiveSecurityContextHolder
                        .withAuthentication(candidate)))
            .expectError(
                AuthenticationCredentialsNotFoundException.class)
            .verify();
    }

    @Test
    void anonymousAuthenticationIsNotARealUser() {
        Authentication anonymous = new AnonymousAuthenticationToken(
            "test-only-key",
            "anonymousUser",
            AuthorityUtils.createAuthorityList(
                "ROLE_ANONYMOUS"));

        StepVerifier.create(
                service.whoAmI()
                    .contextWrite(ReactiveSecurityContextHolder
                        .withAuthentication(anonymous)))
            .expectError(
                AuthenticationCredentialsNotFoundException.class)
            .verify();
    }

    @Test
    void emptySecurityContextAlsoFailsClosed() {
        SecurityContext empty = new SecurityContextImpl();

        StepVerifier.create(
                service.whoAmI()
                    .contextWrite(ReactiveSecurityContextHolder
                        .withSecurityContext(Mono.just(empty))))
            .expectError(
                AuthenticationCredentialsNotFoundException.class)
            .verify();
    }

    @Test
    void withSecurityContextAcceptsMonoOfSecurityContext() {
        Authentication alice = user(
            "alice", "SCOPE_documents.read");
        SecurityContext security = new SecurityContextImpl(alice);

        StepVerifier.create(
                service.whoAmI()
                    .contextWrite(ReactiveSecurityContextHolder
                        .withSecurityContext(Mono.just(security))))
            .expectNext("alice")
            .verifyComplete();
    }

    @Test
    void samePublisherCanHaveDifferentSubscriberIdentities() {
        Mono<String> reusable = service.whoAmI();
        Authentication alice = user("alice");
        Authentication bob = user("bob");

        StepVerifier.create(
                reusable.contextWrite(ReactiveSecurityContextHolder
                    .withAuthentication(alice)))
            .expectNext("alice")
            .verifyComplete();

        StepVerifier.create(
                reusable.contextWrite(ReactiveSecurityContextHolder
                    .withAuthentication(bob)))
            .expectNext("bob")
            .verifyComplete();

        StepVerifier.create(reusable)
            .expectError(
                AuthenticationCredentialsNotFoundException.class)
            .verify();
    }

    @Test
    void flatMapAndFluxInheritSubscriberContext() {
        Authentication alice = user("alice");

        Flux<String> events = Flux.range(1, 3)
            .concatMap(i -> service.whoAmI()
                .map(name -> name + "#" + i))
            .contextWrite(ReactiveSecurityContextHolder
                .withAuthentication(alice));

        StepVerifier.create(events)
            .expectNext("alice#1", "alice#2", "alice#3")
            .verifyComplete();
    }

    @Test
    void publishOnDoesNotAutomaticallyEraseReactorContext() {
        Authentication alice = user("alice");

        Mono<String> pipeline = Mono.just("event")
            .publishOn(Schedulers.parallel())
            .flatMap(ignored -> service.whoAmI())
            .contextWrite(ReactiveSecurityContextHolder
                .withAuthentication(alice));

        StepVerifier.create(pipeline)
            .expectNext("alice")
            .verifyComplete();
    }

    @Test
    void subscribeOnCanReadSubscriptionContext() {
        Authentication alice = user("alice");

        Mono<String> pipeline = Mono.defer(service::whoAmI)
            .subscribeOn(Schedulers.boundedElastic())
            .contextWrite(ReactiveSecurityContextHolder
                .withAuthentication(alice));

        StepVerifier.create(pipeline)
            .expectNext("alice")
            .verifyComplete();
    }

    @Test
    void nestedContextWriteClosestToReaderWins() {
        Authentication alice = user("alice");
        Authentication bob = user("bob");

        Mono<String> pipeline = service.whoAmI()
            .contextWrite(ReactiveSecurityContextHolder
                .withAuthentication(bob))
            .contextWrite(ReactiveSecurityContextHolder
                .withAuthentication(alice));

        StepVerifier.create(pipeline)
            .expectNext("bob")
            .verifyComplete();
    }

    @Test
    void clearContextRemovesAuthenticationForUpstream() {
        Authentication alice = user("alice");

        Mono<String> pipeline = service.whoAmI()
            .contextWrite(ReactiveSecurityContextHolder
                .clearContext())
            .contextWrite(ReactiveSecurityContextHolder
                .withAuthentication(alice));

        StepVerifier.create(pipeline)
            .expectError(
                AuthenticationCredentialsNotFoundException.class)
            .verify();
    }

    @Test
    void contextWriteAtWrongPlaceDoesNotReachDownstreamFlatMap() {
        Authentication alice = user("alice");

        Mono<String> wrong = Mono.just("go")
            .contextWrite(ReactiveSecurityContextHolder
                .withAuthentication(alice))
            .flatMap(ignored -> service.whoAmI());

        StepVerifier.create(wrong)
            .expectError(
                AuthenticationCredentialsNotFoundException.class)
            .verify();
    }

    @Test
    void stepVerifierOptionsSetsInitialSecurityContext() {
        Authentication alice = user("alice");

        StepVerifierOptions options = StepVerifierOptions.create()
            .scenarioName("initial-authentication")
            .withInitialContext(ReactiveSecurityContextHolder
                .withAuthentication(alice));

        StepVerifier.create(service.whoAmI(), options)
            .expectNext("alice")
            .verifyComplete();
    }

    @Test
    void stepVerifierCanAssertOrdinaryContextKeys() {
        Authentication alice = user("alice");

        Context initial = ReactiveSecurityContextHolder
            .withAuthentication(alice)
            .put("traceId", "test-309");

        StepVerifier.create(
                service.whoAmIWithTrace(),
                StepVerifierOptions.create()
                    .withInitialContext(initial))
            .expectAccessibleContext()
            .contains("traceId", "test-309")
            .then()
            .expectNext("test-309:alice")
            .verifyComplete();
    }

    @Test
    void ordinaryTraceKeyCannotReplaceSecurityContext() {
        Mono<String> pipeline = service.whoAmI()
            .contextWrite(Context.of("traceId", "only-trace"));

        StepVerifier.create(pipeline)
            .expectError(
                AuthenticationCredentialsNotFoundException.class)
            .verify();
    }

    @Test
    void separateBranchesDoNotShareUser() {
        Mono<String> alice = service.whoAmI()
            .contextWrite(ReactiveSecurityContextHolder
                .withAuthentication(user("alice")));
        Mono<String> bob = service.whoAmI()
            .contextWrite(ReactiveSecurityContextHolder
                .withAuthentication(user("bob")));

        StepVerifier.create(Flux.merge(alice, bob).collectList())
            .assertNext(names -> assertEquals(
                Set.of("alice", "bob"), Set.copyOf(names)))
            .verifyComplete();
    }

    @Test
    void plainThreadLocalIsNotTheReactiveContext() {
        Authentication alice = user("alice");

        SecurityContextHolder.getContext().setAuthentication(alice);
        try {
            StepVerifier.create(service.whoAmI())
                .expectError(
                    AuthenticationCredentialsNotFoundException.class)
                .verify();
        } finally {
            SecurityContextHolder.clearContext();
        }
    }
}
```

**21 phương thức `@Test`** sử dụng JUnit + `StepVerifier` trong **một lớp**. Mỗi test tự gắn context vào publisher/StepVerifier, không dùng một field `static SecurityContext` để tất cả tests cùng thay đổi.

### 7.1 Test được mong đợi chứng minh điều gì?

| Test | Tình huống | Dự kiến |
|---|---|---|
| `missingContextFailsClosed` | Không có context | AuthenticationCredentialsNotFoundException |
| `aliceInReactorContextCanRead` | Alice có scope read | `READ\|doc-1\|alice` |
| `readAuthorityDoesNotImplyWriteAuthority` | Alice chỉ read, đòi write | AccessDeniedException |
| `bobWithWriteAuthorityCanWrite` | Bob có scope write | `WRITE\|doc-2\|bob` |
| `unauthenticatedObjectIsNotAccepted` | Object `isAuthenticated()==false` | Từ chối |
| `anonymousAuthenticationIsNotARealUser` | AnonymousAuthenticationToken | Từ chối |
| `emptySecurityContextAlsoFailsClosed` | SecurityContext không có Authentication | Từ chối có kiểm soát |
| `samePublisherCanHaveDifferentSubscriberIdentities` | Reuse publisher với hai subscriptions | Alice, Bob riêng; lần không context bị từ chối |
| `flatMapAndFluxInheritSubscriberContext` | Nhiều inner publishers | Cả ba emissions có Alice |
| `publishOn...` | Chuyển Reactor scheduler | Vẫn đọc được Alice trong reactive chain |
| `subscribeOn...` | Chuyển subscription scheduler | Vẫn đọc được Alice |
| `nestedContextWrite...` | Hai context cùng key ở vị trí khác | Reader nhận Bob (scope gần reader hơn) |
| `clearContext...` | Xóa context upstream | Authentication thiếu → lỗi |
| `contextWriteAtWrongPlace...` | Ghi context vào upstream khác | Downstream `flatMap` không thấy user |
| `stepVerifierOptions...` | Initial subscriber context | Reader thấy Alice |
| `stepVerifierCanAssert...` | Custom key `traceId` và SecurityContext | Context assertion + `test-309:alice` |
| `ordinaryTraceKeyCannotReplace...` | Chỉ có trace | Không tự được xác thực |
| `separateBranches...` | Hai branches merge | Không rò user giữa subscriber branches |
| `plainThreadLocal...` | Chỉ đặt imperative ThreadLocal | Reactive service không tự đọc được |

Hai test khác trong file kiểm kết hợp missing auth/write authority và dùng `withSecurityContext(Mono.just(...))`. Số lượng test lớn nhằm chứng minh cả **hành vi đúng** và các đường đi dễ sai; không có test nào xác minh mật khẩu/token thật.

### 7.2 Chạy Gradle

Tại gốc dự án, có Java 17+ và Gradle tương thích:

```bash
gradle test
```

Nếu dự án có Gradle Wrapper phù hợp, ưu tiên:

```bash
./gradlew test

# Trên Windows PowerShell/cmd:
gradlew.bat test
```

Khi các source/dependencies đúng và các test được thực thi thành công, Gradle báo build/test thành công. **Không có stdout test thực tế được chạy trong quá trình biên soạn tài liệu này**; các giá trị `expectNext`/`expectError` là kỳ vọng được xác định từ ngữ nghĩa API. Trong CI, dùng báo cáo XML/HTML `build/test-results/test` và `build/reports/tests/test` để xác nhận.

## 8. Phân tích sâu về cách context được lan truyền

### 8.1 `contextWrite` truyền từ subscriber lên upstream

```text
source:             service.whoAmI() -> map -> flatMap
                                           |
                                           v
downstream:              contextWrite(withAuthentication(Alice))
                                           |
                                      StepVerifier.create(...)
                                           |
                                         subscribe
      Context được thiết lập trên dòng subscription đi ngược lên source
```

Do đó nhiều người nhìn code từ trên xuống tưởng `contextWrite` “chạy sau” và không thể ảnh hưởng `getContext` ở trước nó. Thực tế context được gắn **khi subscribe** và xuất hiện với upstream operators.

### 8.2 Hai `contextWrite` có cùng security key

Vì Spring Security context entry cùng key logic, scope **gần reader** hơn sẽ ghi đè:

```java
Mono<String> value = service.whoAmI()
    .contextWrite(ReactiveSecurityContextHolder
        .withAuthentication(userBob))
    .contextWrite(ReactiveSecurityContextHolder
        .withAuthentication(userAlice));
```

Reader `service.whoAmI()` thấy Bob, không thấy Alice, vì Bob được gắn ở `contextWrite` gần nguồn hơn (dù Alice có operator bên dưới). Không dùng cách này như một hệ thống “impersonation” tự do; trong production switching user phải có authenticated delegation và kiểm quyền.

### 8.3 `flatMap`, `concatMap` và nhiều inner publishers

Nếu inner publisher được subscribe như một phần của Reactor pipeline, nó thường nhận context từ subscriber của operator tương ứng:

```java
Flux<String> result = Flux.just("A", "B", "C")
    .concatMap(label ->
        ReactiveSecurityContextHolder.getContext()
            .map(SecurityContext::getAuthentication)
            .map(auth -> label + "=" + auth.getName()))
    .contextWrite(ReactiveSecurityContextHolder
        .withAuthentication(alice));
```

Dự kiến:

```text
A=alice
B=alice
C=alice
```

Không cần copy username vào một `ThreadLocal` trên mỗi thread. Nhưng nếu code gọi `subscribe()` thủ công tạo **subscription mới** nằm ngoài pipeline cần test, context ban đầu có thể **không được mang sang**. Các method reactive nên **trả Mono/Flux** để caller compose, thay vì tự subscribe rồi bỏ qua cancellation/error handling.

### 8.4 `publishOn` / `subscribeOn` không phải “xóa security”

Reactor Context gắn subscriber; khi dùng operators Reactor đúng, nó có thể đi qua `publishOn`/`subscribeOn` dù callback chạy thread khác. Điều này **không** bảo đảm một `CompletableFuture`/raw `Executor` hoặc thư viện blocking tùy ý tự biết context.

Phân biệt:

```text
Mono -> publishOn(Schedulers.parallel()) -> flatMap(Mono...)
     -> contextWrite(withAuthentication(alice))
     -> StepVerifier               : thường giữ Reactor Context

executor.submit(() -> SecurityContextHolder.getContext())
                                : ThreadLocal ở thread khác không được
                                  tự động coi là Reactor Context Alice
```

Muốn bridge sang ThreadLocal cho tracing/legacy code, nghiên cứu Micrometer Context Propagation, Reactor hooks và Spring support theo phiên bản. **Không** bật global `Hooks.enableAutomaticContextPropagation()` trong mọi unit test chỉ để “sửa” một publisher đặt `contextWrite` sai; hooks toàn cục có thể làm tests phụ thuộc lẫn nhau.

## 9. Khi nào dùng StepVerifierOptions.withInitialContext?

Hai cách tạo initial security context:

**Cách A — Gắn vào publisher:**

```java
StepVerifier.create(service.whoAmI()
        .contextWrite(ReactiveSecurityContextHolder
            .withAuthentication(alice)))
    .expectNext("alice")
    .verifyComplete();
```

**Cách B — Gắn vào test subscriber:**

```java
StepVerifierOptions options = StepVerifierOptions.create()
    .withInitialContext(
        ReactiveSecurityContextHolder.withAuthentication(alice));

StepVerifier.create(service.whoAmI(), options)
    .expectNext("alice")
    .verifyComplete();
```

Cả hai là cách hợp lệ cho **unit tests**. Chọn cách A khi muốn thể hiện rõ context thuộc đoạn code đang test; chọn B khi cần kiểm framework/operator nhận initial context từ subscriber, hoặc cần cùng một initial context cho nhiều operators được kết nối.

### 9.1 Context assertion là loại kiểm thử khác

`StepVerifier.expectAccessibleContext()` dùng để xác nhận Reactor Context **có thể được truy cập**, rồi chuyển về event expectations bằng `then()`:

```java
StepVerifier.create(
        Mono.deferContextual(view ->
            Mono.just(view.<String>get("traceId"))),
        StepVerifierOptions.create()
            .withInitialContext(Context.of("traceId", "abc")))
    .expectAccessibleContext()
    .contains("traceId", "abc")
    .then()
    .expectNext("abc")
    .verifyComplete();
```

**Không nhầm:** thấy Reactor Context có key `traceId` **không chứng minh** Spring Security context có authentication. Với security context, dùng `ReactiveSecurityContextHolder.getContext()`/service behavior để assert principal/authorities. Đừng kiểm private key của Spring Security bằng string không chính thức.

### 9.2 Cách hiểu `expectNoAccessibleContext()`

`expectNoAccessibleContext()` có ý nghĩa khi một publisher không có Reactor context propagation có thể truy cập (ví dụ một Publisher không phải Reactor). Nó **không** tương đương “security context rỗng”. Một Reactor publisher có thể có Context object truy cập được nhưng không có Spring Security entry. Để test anonymous/missing authentication, nên tạo test publisher đọc `ReactiveSecurityContextHolder.getContext()` rồi assert empty/error theo contract.

## 10. Mô phỏng lỗi mất context trong test

### 10.1 Sai: ghi context trước khi gọi flatMap downstream

```java
Mono<String> faulty = Mono.just("command")
    .contextWrite(ReactiveSecurityContextHolder
        .withAuthentication(alice))
    .flatMap(command -> service.whoAmI());
```

Vì `flatMap` nằm **sau** `contextWrite`, đoạn inner service nằm downstream của nơi ghi context và sẽ không thấy Alice từ operator đó. Di chuyển `contextWrite` về cuối:

```java
Mono<String> fixed = Mono.just("command")
    .flatMap(command -> service.whoAmI())
    .contextWrite(ReactiveSecurityContextHolder
        .withAuthentication(alice));
```

Đây là hai publisher khác nhau về **scope context**, mặc dù cùng có một danh sách operators.

### 10.2 Sai: cố đặt vào SecurityContextHolder trong @BeforeEach

```java
@BeforeEach
void setUp() {
    SecurityContextHolder.getContext()
        .setAuthentication(alice);
}
```

Đoạn này là **mảnh code thiếu field/import**. Trong Spring Test có listeners/bridges, dữ liệu thread-local có thể được chuyển sang reactive context theo cơ chế test support. Nhưng trong **plain JUnit 5** không cấu hình listener, đặt imperative ThreadLocal **không tự tạo** Reactor SecurityContext cho service reactive. Nguy cơ còn là state bị giữ lại ở test thread nếu không clear.

Khuyến nghị plain JUnit: **tạo authentication riêng cho mỗi test và dùng `contextWrite` hoặc `StepVerifierOptions`**, không dùng global state.

### 10.3 Sai: lưu user trong biến static

```java
// SAI: global mutable state dùng chung test requests/subscribers.
static Authentication CURRENT_USER;
```

Hai tests Alice/Bob chạy song song sẽ đọc lẫn user hoặc gây test flaky. Reactor Context theo subscriber giúp cách ly tốt hơn, nhưng vẫn không nên lưu một mutable Authentication object và chỉnh authorities giữa các subscriptions.

### 10.4 Sai: gọi block trong WebFlux event loop

```java
// PHẢN VÍ DỤ production:
String current = service.whoAmI().block();
```

`block()` tạo một subscription riêng và có thể block event loop, phá reactive flow hoặc mất context nếu được gọi ngoài pipeline có auth. Trong **unit test** người ta đôi khi dùng `block()` để xem result, nhưng `StepVerifier` thường tốt hơn vì kiểm được completion/error/cancellation và initial context.

### 10.5 Sai: tự subscribe tách khỏi luồng chính

```java
// PHẢN VÍ DỤ:
public Mono<String> wrong() {
    service.whoAmI().subscribe(System.out::println);
    return Mono.just("ok");
}
```

Subscription mới không mặc nhiên hưởng context của caller đang kiểm; exceptions/cancellation cũng bị tách. Phương án đúng:

```java
public Mono<String> correct() {
    return service.whoAmI()
        .map(user -> "ok for " + user);
}
```

Hai đoạn là **mảnh method** không có class/import và chỉ nhằm so sánh. Không lấy `System.out` làm cơ chế audit principal hoặc ghi PII của user thật.

## 11. Test các trường hợp SecurityContext không chuẩn

Đừng chỉ thử Alice có đủ quyền và kết luận “xong unit test”. Những trạng thái âm tính cần kiểm:

| Input context | Behavior cần chứng minh |
|---|---|
| Không có `SecurityContext` entry | Fail closed hoặc Mono.empty rõ contract |
| Có `SecurityContext` nhưng `getAuthentication()==null` | Không NPE, không cấp quyền |
| `Authentication.isAuthenticated()==false` | Không tự cho truy cập |
| `AnonymousAuthenticationToken` | Không coi như user xác thực thật |
| Authenticated không có authority cần thiết | `AccessDeniedException` hoặc deny result |
| Có authority READ nhưng đòi WRITE | Deny |
| Authority `ROLE_USER` nhưng service đòi `SCOPE_documents.read` | Không tự map thành scope |
| Context Alice được gắn rồi test Bob | Không bị rò Alice sang Bob |
| Một publisher reuse ở hai subscriptions | Identity theo subscription, không theo object Mono |
| Clear context upstream | Không còn authentication trong scope đó |
| Context key độc lập như traceId | Không được dùng làm security identity |
| Nested contexts | Quy tắc gần reader, test explicit |
| JWT/credentials giả trong Authentication | Không suy là đã verify protocol |
| Token expiration sau khi object tạo | Unit test này không kiểm expiration; integration token tests phải xử lý |

Đặc biệt, việc tạo một `UsernamePasswordAuthenticationToken.authenticated(...)` trong test **không** kiểm password. Nếu test cần đảm bảo invalid JWT không login, phải kiểm tại `ReactiveJwtDecoder`/Resource Server filter và sử dụng JWT ký bằng test key/issuer đúng.

## 12. Phân biệt pure unit test với Spring Test, @WithMockUser và WebTestClient

### 12.1 Plain JUnit + StepVerifier

Bài này dùng:

```java
@Test
void aUnitTest() {
    Authentication user = /* test authentication */;
    StepVerifier.create(service.whoAmI()
            .contextWrite(ReactiveSecurityContextHolder
                .withAuthentication(user)))
        .expectNext("alice")
        .verifyComplete();
}
```

Dấu comment `test authentication` là **placeholder minh họa**; trong file compile-ready mục 7 đã có `user(...)` tạo token. Test này không cần Spring context, AOP proxy hoặc HTTP filters.

**Thích hợp khi:** test business code có `ReactiveSecurityContextHolder.getContext()`, các operator Reactor, missing/changed context, logic roles/scopes và việc cách ly publishers.

### 12.2 Reactive method security @PreAuthorize

Nếu method mang:

```java
@PreAuthorize("hasAuthority('SCOPE_documents.read')")
public Mono<String> readDocument(String documentId) {
    return Mono.just(documentId);
}
```

thì quyền được kiểm qua Spring Security **method interceptor/AOP proxy** khi bật `@EnableReactiveMethodSecurity`. Nếu test `new DocumentService()` trực tiếp, **annotation không được áp dụng**. Vì vậy test method security thật cần Spring-managed bean/proxy:

```java
@Configuration
@EnableReactiveMethodSecurity
class MethodSecurityConfiguration {
    @Bean
    SecuredDocumentService secured() {
        return new SecuredDocumentService();
    }
}
```

Đây là **hai mảnh code định hướng**: method và configuration phải đặt vào class/package đầy đủ cùng dependencies khi triển khai. Có thể test bằng `@SpringJUnitConfig(MethodSecurityConfiguration.class)`, `@WithMockUser`/`ReactorContextTestExecutionListener` hoặc trực tiếp `contextWrite` gắn vào publisher trả từ proxy.

**Không** mô tả test của class `new` là đã test `@PreAuthorize` thật.

### 12.3 @WithMockUser và ReactorContextTestExecutionListener

`@WithMockUser(username = "alice", roles = "USER")` đến từ Spring Security Test. Trong Spring Test, `WithSecurityContextTestExecutionListener` tạo context cho test; với reactive method security, `ReactorContextTestExecutionListener` đảm bảo reactive context có thể được dựng từ test security context.

```java
@ExtendWith(SpringExtension.class)
@ContextConfiguration(classes = MethodSecurityConfiguration.class)
@WithMockUser(username = "alice", roles = "USER")
class MethodSecurityTest {
    // Inject proxied bean, kiểm result bằng StepVerifier.
}
```

Đây là **khung test** không có class/method đầy đủ. `@WithMockUser` trong plain JUnit test mà **không có Spring Test listeners** không phải phép thuật tự đẩy authentication vào mọi Reactor subscription. Nếu dự án dùng custom `@TestExecutionListeners`, bảo đảm không vô ý loại các listener mặc định, đặc biệt listener phục vụ Reactor Context.

`@WithMockUser(roles = "USER")` tạo authority `ROLE_USER`. Nếu cần authority literal `SCOPE_documents.read`, dùng:

```java
@WithMockUser(
    username = "alice",
    authorities = "SCOPE_documents.read")
```

**Đừng** dùng `roles = "SCOPE_documents.read"` để mô phỏng scope: với roles, Spring tự thêm tiền tố `ROLE_`, làm sai expression `hasAuthority('SCOPE_documents.read')`.

### 12.4 WebTestClient mutateWith(mockUser()) là integration khác

Với WebFlux endpoint, Spring Security Test có:

```java
// MẢNH CODE: WebTestClient đã được bind tới ApplicationContext,
// áp dụng Spring Security test support.
webTestClient
    .mutateWith(mockUser().roles("USER"))
    .get()
    .uri("/documents")
    .exchange()
    .expectStatus().isOk();
```

Cần static import:

```java
import static org.springframework.security.test.web.reactive.server
    .SecurityMockServerConfigurers.mockUser;
```

**Đây không phải file runnable độc lập**. Khi tạo client manually:

```java
WebTestClient client =
    WebTestClient.bindToApplicationContext(context)
        .apply(springSecurity())
        .build();
```

`springSecurity()` cũng từ `SecurityMockServerConfigurers`. Trong Spring Boot test environment, có thể dùng `@AutoConfigureWebTestClient` rồi mutate; kiểm setup thực tế theo version.

Khác biệt:

| Kiểu test | Có HTTP exchange? | Security identity được đặt ở đâu? | Kiểm được gì? |
|---|---|---|---|
| Plain JUnit + StepVerifier | Không | Reactor Context của subscription do test cấp | Behavior của publisher/service |
| Spring Test + @WithMockUser | Không bắt buộc | Spring Test listener, có thể bridge reactive | Reactive method security trên Spring bean |
| WebTestClient + mockUser | Có request mô phỏng | Spring Security test WebFlux mutator/request | Route/controller/filter authorization với mock user |
| WebTestClient + Bearer JWT thật | Có request | Authorization header và Resource Server filters | Token validation, status, claims khi IdP/JWK đúng |
| End-to-end qua network | Có HTTP thật | Browser/cookie/token/IdP server | Toàn bộ auth flow và deployment controls |

**Mock user không phải chứng cứ JWT signature validation.** Nếu yêu cầu threat model gồm issuer/audience/expiry, cần test decoder/JWK/IdP hoặc real signed JWT integration.

## 13. Bảo mật context trong unit tests

### 13.1 Không truyền raw secrets qua Context

Reactor Context là phương tiện truyền dữ liệu theo subscription; nó **không mặc nhiên mã hóa** thông tin. Không đặt password, client secret hoặc bearer token raw vào key tự đặt rồi log cả Context.

```java
// Không nên tạo context kiểu này:
Context.of("Authorization", "Bearer real-production-token");
```

Dùng mock authentication không có credentials thật. Nếu test claims JWT, tạo một `Jwt` giả phù hợp test và phân biệt với việc verifier đã xác nhận chữ ký.

### 13.2 Authentication object có thể mutable

`SecurityContextImpl` có setter `setAuthentication`; một authentication/token có thể chứa details, authorities, credentials. **Đừng** tạo static mutable `SecurityContext` rồi test A set Alice, test B set Bob; publisher có thể còn giữ tham chiếu. Mỗi test tạo object riêng và hạn chế mutation giữa subscriptions.

### 13.3 Context không phải thay thế object-level authorization

Test `service.read("doc-1")` ở bài lab chỉ kiểm authority read. Trong product đa tenant, phải kiểm owner/tenant của `doc-1` ở business repository:

```text
authenticated user (issuer, sub, tenant)
             |
       hasAuthority("documents.read")?
             |
       document.tenant == user.tenant?
             |
       owner / grant / ABAC policy?
             |
       query DB với tenant predicate
```

`contextWrite(withAuthentication(...))` cho phép mô phỏng principal khi unit test permission service, nhưng identity phải được **verified** trong production security chain. Đừng chấp nhận `X-User-Id` HTTP header làm authenticated user chỉ để test qua.

### 13.4 Không để test state rò giữa cases

- Ưu tiên test-local `Authentication` objects.
- Dùng `contextWrite` ngay trên publisher cần test thay vì global ThreadLocal.
- Nếu bắt buộc dùng `SecurityContextHolder` trong một test kết hợp imperative, `try/finally` và `SecurityContextHolder.clearContext()`.
- Đừng bật Reactor global hooks rồi quên reset; điều này có thể khiến tests khác nhận được behavior khác.
- Trong JUnit parallel mode, tránh shared mutable context, shared counters và security test data thay đổi không được đồng bộ.
- Không log toàn bộ context hoặc serialized `Authentication` có credential.

## 14. Về context propagation qua các boundary khác

### 14.1 Scheduled tasks

Một scheduler không có HTTP request authenticated. Nếu ứng dụng cần một identity service để chạy job, hãy **thiết kế service identity/authorization riêng**; không lấy context của user cuối cùng rồi gắn lên job. Trong test, có thể `contextWrite` một service authentication **chỉ khi** component thật sự được thiết kế/được cấp quyền chạy nhân danh service.

### 14.2 CompletableFuture, Executor, callbacks

Reactor Context được quản lý trong reactive subscriber chain. Nếu code nhảy sang `CompletableFuture.supplyAsync` và sau đó gọi trực tiếp `SecurityContextHolder.getContext()`, thường không có cùng user. Muốn bridge phải dùng cơ chế được thiết kế và kiểm thử, hoặc truyền **định danh/authorization context đã được xác minh** tới function một cách tường minh theo trust boundary.

### 14.3 RxJava/Kotlin Flow/custom Publisher

Không suy rằng mọi API reactive đều dùng Reactor Context với semantics giống nhau. Chuyển framework có thể làm mất context. `StepVerifier.expectNoAccessibleContext()` không phải phép kiểm security; khi tích hợp qua adapters, test người dùng thực được thấy/không thấy ở điểm đọc `ReactiveSecurityContextHolder.getContext()`.

### 14.4 Cache và share

Một publisher có `cache()`, `share()`, hoặc một hot source có thể có semantics subscription khác cold publisher bình thường. Đặc biệt nếu **cache data đã được cá nhân hóa** dựa trên security context rồi reuse chung, có nguy cơ một subscriber khác nhận kết quả của người khác. Không cache kết quả `myDocuments` theo global key khi user/tenant không nằm trong cache key. Test hai subscribers Alice/Bob với publisher có cache và thiết kế lại nếu có cross-user leak.

### 14.5 Micrometer Context Propagation

Reactor có chế độ context-propagation phục vụ bridge với ThreadLocal trong một số tình huống khi dependency phù hợp. `Hooks.enableAutomaticContextPropagation()` là **thiết lập toàn cục**, không phải API mặc định cần gọi cho `ReactiveSecurityContextHolder.withAuthentication(...)`. Test context cơ bản nên dùng Reactor Context gốc; nếu project có bridge tracing/MDC, kiểm riêng theo thread/scheduler và reset hooks sau tests để không làm thay đổi suite khác.

## 15. Ma trận lỗi và cách chẩn đoán

| Dấu hiệu | Nguyên nhân phổ biến | Cách sửa / test |
|---|---|---|
| `ReactiveSecurityContextHolder.getContext()` empty | Không có context cho subscriber | `contextWrite(withAuthentication(auth))` tại pipeline cần test |
| Test mong `expectNext` nhưng chỉ complete empty | Service không chuyển missing auth thành error | Định nghĩa contract rõ, `switchIfEmpty(...)` hoặc kiểm empty |
| Unit test pass nhưng production 401 | Mock authentication bypass login/token verification | Bổ sung HTTP auth integration/JWT tests |
| User A xuất hiện trong test B | Dùng static mutable SecurityContext, cache kết quả cá nhân hóa | Test-local context và subscriber isolation |
| `SecurityContextHolder.getContext()` có Alice nhưng reactive service không thấy | ThreadLocal ≠ Reactor Context | Dùng reactive API/test listener đúng |
| `contextWrite` không tác động inner `flatMap` | Đặt operator upstream sai scope | Di chuyển contextWrite xuống cuối pipeline |
| `publishOn` đổi thread, log không có user | MDC/ThreadLocal không propagate | Đọc ReactiveSecurityContextHolder; bridge logging nếu cần |
| `@WithMockUser` trong plain JUnit không tác dụng | Không có Spring Test listeners | Dùng contextWrite/StepVerifierOptions |
| `@PreAuthorize` không chặn trong unit test | Đối tượng tạo bằng `new`, không qua Spring proxy | Test Spring-managed proxied bean |
| `roles="SCOPE_x"` không match authority | Roles thêm `ROLE_` | Dùng `authorities="SCOPE_x"` |
| AnonymousAuthenticationToken có `isAuthenticated() == true` | Nhầm authenticated flag với real user | Trust resolver / Spring authorization APIs |
| NPE vì `SecurityContext.getAuthentication()` null | Dùng `map` phát null | `flatMap(ctx -> Mono.justOrEmpty(...))` |
| Lỗi “Missing authority” thành HTTP 401 sai | Unit exceptions khác HTTP translation | Integration test exception mapping 401/403 |
| Test chạy song song bị flaky | Shared Auth/SecurityContext hoặc Reactor hooks | Isolate context per subscriber/test |
| Flux emits không thấy context ở nested subscription | Manual `subscribe()` hoặc thư viện khác | Compose publisher, test subscription boundary |
| `expectAccessibleContext` pass nhưng identity sai | Chỉ test custom key, không test authentication | Assert service principal/authorities |
| JWT test tạo Jwt object là “verified” | Bỏ qua cryptographic validation | Resource Server/JWKS integration tests |
| Service `block()` làm request treo | Blocking trong event loop/new subscription | Trả Mono/Flux, dùng StepVerifier tests |
| Cached publisher trả data Alice cho Bob | Caching kết quả phụ thuộc context toàn cục | Cache theo user/tenant hoặc không cache |
| Revoke role rồi publisher cũ vẫn trả dữ liệu | Context identity/auth snapshot, không recheck ACL | Business policy hiện tại và revocation handling |

## 16. Kiểm thử từng cấp độ: cần những lớp nào?

| Cấp test | Đối tượng | Ví dụ | Không chứng minh |
|---|---|---|---|
| **Unit Context** | `ReactiveSecurityContextHolder` và service pure Java | Alice có read, Bob không; contextWrite | JWT ký hợp lệ |
| **Unit policy** | `ReactiveAuthorizationManager`/ABAC service | user+tenant+resource+action | HTTP CORS/CSRF |
| **Method security** | Proxied `@PreAuthorize` method | `hasAuthority` trong Spring context | Token issuer validation |
| **HTTP/WebFlux slice** | `WebTestClient` + mockUser/mockJwt | 200/401/403, route matching | IdP thật |
| **Resource Server integration** | JWT decoder/opaque introspection | bad signature, exp, aud, iss | Data ACL nếu không test |
| **Full E2E** | Browser/IdP/session/microservices | login, callbacks, token refresh, logout | Không thay security review |

Bộ unit tests ở mục 7 cố tình không khởi động HTTP server để dễ chạy, tốc độ nhanh, debug rõ. Hãy giữ một số tests với **credential thực sự được xác minh** ở lớp tích hợp để không có lỗ hổng “unit test cho phép admin vì đã tự tạo admin token”.

## 17. Checklist khi viết unit test dùng Reactor Context

1. Xác định method trả `Mono`/`Flux` và cần `Authentication` hay chỉ custom context key.
2. Dựng một `Authentication` riêng, có authorities hợp đồng rõ.
3. Gắn bằng `.contextWrite(ReactiveSecurityContextHolder.withAuthentication(auth))` hoặc `StepVerifierOptions.withInitialContext(...)`.
4. Dùng `StepVerifier` để assert next/completion/error; không dùng `block()` trong service production.
5. Có test thiếu SecurityContext, context không chứa Authentication, unauthenticated token và anonymous.
6. Có test scope/role thiếu, read/write khác nhau, identity thuộc tenant khác.
7. Có test reuse publisher cho hai subscribers và không còn user ở subscription thứ ba.
8. Có test nested contextWrite order, clearContext và contextWrite placement.
9. Có test `publishOn` / `subscribeOn` nếu service dùng scheduler/async operators.
10. Dùng `expectAccessibleContext()` cho custom context keys, **không** đoán private security key.
11. Với `@PreAuthorize`, kiểm bean được Spring proxied, `@EnableReactiveMethodSecurity` bật và Spring Test listener thích hợp.
12. Với `WebTestClient`, dùng `springSecurity()`/`mockUser()` đúng test scope; test raw JWT separately.
13. Tránh mock auth làm thay một bài test password/JWT/issuer validation.
14. Không lưu token/password thật trong context/logs.
15. Dọn imperatives `SecurityContextHolder` hoặc Reactor global hooks nếu test có dùng.
16. Với hot/cached publisher, chứng minh không leak data theo user/tenant.
17. Khẳng định business ACL data-level chứ không dừng ở `isAuthenticated()`.
18. Chạy CI với JDK/Gradle version chuẩn, thực thi suite sau mọi thay đổi security config.

## 18. Bài tập nâng cao

1. Viết một `Mono<String>` trả `SecurityContext.getAuthentication().getName()`. Không gắn context thì StepVerifier nhận gì?
2. Dùng `withAuthentication(user("alice","ROLE_USER"))` để kiểm principal. Đổi sang `user("bob","ROLE_ADMIN")` trên **cùng publisher gốc** và kiểm không lẫn.
3. Gọi `service.write("d1")` với chỉ `SCOPE_documents.read`. Tại sao test nên mong `AccessDeniedException` chứ không `Mono.empty()`?
4. Tạo một `SecurityContextImpl()` không có authentication. Tránh NPE bằng `Mono.justOrEmpty` như thế nào?
5. Tạo `AnonymousAuthenticationToken`; kiểm `isAuthenticated` và `AuthenticationTrustResolver.isAnonymous`. Vì sao chỉ đọc boolean flag là thiếu?
6. Di chuyển `contextWrite` lên trước `flatMap` như test lỗi. Giải thích chiều truyền subscription context.
7. Thêm `.publishOn(Schedulers.parallel())` trước lần đọc identity. Kết quả vì sao vẫn có Alice?
8. Dùng `StepVerifierOptions.withInitialContext(ReactiveSecurityContextHolder.withAuthentication(...))` thay vì `contextWrite`. So sánh chỗ gắn context.
9. Thêm key `traceId` bằng `Context.of(...)` và viết `expectAccessibleContext().contains(...)`. Vì sao chưa đủ để chứng minh authenticated?
10. Thêm hai `contextWrite` Alice/Bob và thay đổi thứ tự. Identity nhìn thấy ở upstream thay đổi ra sao?
11. Xóa context bằng `ReactiveSecurityContextHolder.clearContext()` giữa hai operations; chứng minh không auto logout toàn server.
12. Đưa kết quả `service.whoAmI()` vào `.cache()` rồi subscribe Alice/Bob; phân tích nguy cơ dữ liệu Alice bị trả cho Bob và sửa cache design.
13. Viết một `@PreAuthorize("hasAuthority('SCOPE_documents.read')")` trên Spring-managed bean và test khác với pure `new` object.
14. Viết `WebTestClient.mutateWith(mockUser().authorities(...))` cho HTTP route, phân biệt với JUnit StepVerifier pure.
15. Viết JWT Resource Server test cho token sai issuer/audience (signed JWT), giải thích vì sao `withAuthentication` không kiểm điều đó.
16. Viết test composite `Flux.merge` để khẳng định không leak identity trên concurrent branches.
17. Đo subscribe vào publisher bằng `AtomicInteger`, chứng minh context được đọc lúc subscription chứ không phải assembly.
18. Viết một helper `testAs(String user, Publisher<?> publisher)` nhưng đảm bảo không lưu `Authentication` trong mutable static state.
19. Khi dùng `CompletableFuture`, thử đọc reactive context trong callback. Thiết kế một bridge an toàn có giới hạn.
20. Đề xuất security regression suite khi nâng Spring Security/Reactor (ThreadLocal bridge, contextWrite order, @PreAuthorize và client mock support).

## Kết luận

Trong **kiểm thử đơn vị Spring Security Reactive**, identity không nằm mặc nhiên trong JUnit thread hoặc một object global. Nó nằm trong **Reactor Context của từng subscription**. Dùng `ReactiveSecurityContextHolder.withAuthentication(auth)` hoặc `withSecurityContext(Mono<SecurityContext>)` cùng `contextWrite`; hoặc thiết lập `StepVerifierOptions.withInitialContext(...)`. `StepVerifier` kiểm được onNext/onComplete/onError và context metadata, đồng thời cho phép các ca âm tính: không có context, anonymous/unauthenticated, authority thiếu, scope đặt sai, nested context và subscriber isolation. Tránh nhầm `SecurityContextHolder` ThreadLocal với reactive context; `@WithMockUser` chỉ tự động hỗ trợ trong Spring Test phù hợp; `@PreAuthorize` cần proxy và `WebTestClient` là cấp kiểm thử khác. Unit test gắn mock authentication **không chứng minh** password/JWT/issuer hợp lệ — kiểm protocol, quyền dữ liệu và HTTP security ở các lớp test bổ sung.

## Tài liệu tham khảo chính thức

1. Spring Security — Reactive Method Security, ví dụ `contextWrite(withAuthentication(...))` và StepVerifier: https://docs.spring.io/spring-security/reference/6.5/reactive/authorization/method.html
2. Spring Security — `ReactiveSecurityContextHolder` Javadoc (API `getContext`/`withAuthentication`/`withSecurityContext`/`clearContext`): https://docs.spring.io/spring-security/site/docs/6.3.0/api/org/springframework/security/core/context/ReactiveSecurityContextHolder.html
3. Project Reactor 3.6 — Context, immutable semantics và `contextWrite`: https://projectreactor.io/docs/core/3.6.13/reference/index.html
4. Project Reactor — Testing Reactor Context, `StepVerifierOptions`/`expectAccessibleContext`: https://projectreactor.io/docs/core/3.6.13/reference/index.html#_testing_the_context
5. Reactor Test API — `StepVerifierOptions.withInitialContext`: https://projectreactor.io/docs/test/release/api/reactor/test/StepVerifierOptions.html
6. Spring Security — Testing Method Security, Spring Test listeners và `@WithMockUser`: https://docs.spring.io/spring-security/reference/6.5/servlet/test/method.html
7. Spring Security — Reactive WebTestClient Authentication tests, `springSecurity`/`mockUser`: https://docs.spring.io/spring-security/reference/6.5/reactive/test/web/authentication.html
8. Spring Security — WebFlux Security configuration and reactive context: https://docs.spring.io/spring-security/reference/6.5/reactive/configuration/webflux.html
9. Spring Security 6.3 — `TestingAuthenticationToken` Javadoc: https://docs.spring.io/spring-security/site/docs/6.3.10/api/org/springframework/security/authentication/TestingAuthenticationToken.html
