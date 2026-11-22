# 30.5. Kiểm thử principal và security context trong Reactor

Trong ứng dụng **Spring Security OAuth 2.0 / OpenID Connect (OIDC) Client trên Reactive WebFlux**, sau khi người dùng đăng nhập, các thành phần ứng dụng cần biết ai đang thực hiện request, người dùng có quyền gì và một lời gọi `Mono` hoặc `Flux` có còn nhận đúng danh tính khi chuyển qua nhiều operators/schedulers hay không.

Khác Servlet, nơi `SecurityContextHolder` thường gắn `SecurityContext` với thread hiện tại, **Spring Security Reactive sử dụng `ReactiveSecurityContextHolder` và Reactor `Context`** để gắn authentication với luồng subscription. Việc kiểm thử vì thế phải được tổ chức quanh **publisher, subscriber và context propagation**, chứ không chỉ đặt một `ThreadLocal` trước khi gọi service.

Những API trọng tâm của bài:

- **`ReactiveSecurityContextHolder.getContext()`**: truy cập `Mono<SecurityContext>` của subscription hiện tại;
- **`ReactiveSecurityContextHolder.withAuthentication(authentication)`**: tạo Reactor context chứa Authentication phục vụ một nhánh test;
- **`StepVerifier`**: subscribe và kiểm tra `onNext`, `onError`, `onComplete` của service reactive;
- **`@WithMockUser` + Reactor test listener**: tạo danh tính cho reactive method-security tests có Spring Test context;
- **`WebTestClient.mutateWith(mockUser())` / `mockAuthentication()` / `mockOAuth2Login()` / `mockOidcLogin()`**: giả lập SecurityContext theo **HTTP request WebFlux**;
- **`@AuthenticationPrincipal`, `Principal`, `@PreAuthorize`**: kiểm thử controller và business authorization.

Một ví dụ ngắn nhất:

```java
Authentication alice = new TestingAuthenticationToken(
    "alice", "not-used", "ROLE_READER");

Mono<String> currentName = ReactiveSecurityContextHolder.getContext()
    .map(SecurityContext::getAuthentication)
    .map(Authentication::getName);

StepVerifier.create(
        currentName.contextWrite(
            ReactiveSecurityContextHolder.withAuthentication(alice)))
    .expectNext("alice")
    .verifyComplete();
```

Ở đây Authentication nằm trong **Reactor Context của subscription do StepVerifier tạo**. Không có cuộc gọi mạng đến OP, không có Authorization Code exchange và cũng không có ID Token thật.

> **Phạm vi:** Java 17+, Spring Boot 3.x, Spring Security 6.x (tham khảo API 6.5), Reactor 3.x, JUnit 5 và `spring-security-test`. Đây là chương **30. Kiểm thử Reactive**; không trộn API `HttpSecurity`, MockMvc hoặc `SecurityMockMvcRequestPostProcessors` từ Servlet. Các chuỗi ID Token/access token trong ví dụ chỉ là fixture giả.

---

## 1. Bài toán: cùng một request nhưng không nhất thiết cùng thread

Giả sử user Alice đã login qua Company SSO và gọi:

```text
GET /api/me
Cookie: SESSION=<opaque-session-cookie>

WebFlux SecurityWebFilterChain:
    xác thực session
    Authentication = OAuth2AuthenticationToken(
        principal = OidcUser(Alice),
        authorities = [SCOPE_read, ROLE_REPORT_READER]
    )

Reactive controller:
    return identityService.currentUser()
        .flatMap(user -> reportService.load(user))
        .publishOn(Schedulers.parallel())
        .map(this::toResponse)
```

Luồng có thể chuyển thread khi đi qua `publishOn` hoặc khi có I/O asynchronous. Nếu bạn viết:

```java
Authentication auth =
    SecurityContextHolder.getContext().getAuthentication();
```

trong một reactive operator bất kỳ, kết quả **có thể là null hoặc sai ngữ cảnh** nếu code dựa trên ThreadLocal mặc định.

Điều Spring Security Reactive cung cấp là một ngữ cảnh **gắn với subscriber**, truy cập dưới dạng publisher:

```java
Mono<SecurityContext> securityContext =
    ReactiveSecurityContextHolder.getContext();
```

### 1.1. So sánh nhanh Servlet và Reactive

| Tiêu chí | Servlet / MVC | Reactive / WebFlux |
| --- | --- | --- |
| Cấu hình filter chain | `HttpSecurity` / `SecurityFilterChain` | `ServerHttpSecurity` / `SecurityWebFilterChain` |
| HTTP test client | `MockMvc` | **`WebTestClient`** |
| Security context thường dùng | `SecurityContextHolder` | **`ReactiveSecurityContextHolder`** |
| Nơi đặt context | Thường gắn với thread qua strategy | **Reactor Context của subscription** |
| Lấy context | `SecurityContextHolder.getContext()` | `ReactiveSecurityContextHolder.getContext()` → `Mono<SecurityContext>` |
| OIDC login fixture | `oidcLogin()` | **`mockOidcLogin()`** |
| OAuth2 login fixture | `oauth2Login()` | **`mockOAuth2Login()`** |
| Generic user fixture | `user()` / `@WithMockUser` | `mockUser()` / `@WithMockUser` |
| Test publisher | Đồng bộ assertion/MockMvc result | **`StepVerifier`** và WebTestClient |
| Repository cho pending OAuth2 login | `HttpSessionOAuth2AuthorizationRequestRepository` | `WebSessionOAuth2ServerAuthorizationRequestRepository` |

**Không suy ra một unit test thấy context ở ThreadLocal sẽ chứng minh context có mặt trong pipeline Reactive.**

### 1.2. Phân biệt `Authentication`, `Principal` và `SecurityContext`

`SecurityContext` là container cho `Authentication`. Authentication mô tả chủ thể, trạng thái xác thực và authorities.

```text
Reactor Context của subscriber
    |
    v
SecurityContext
    |
    +-- Authentication
          |
          +-- principal: UserDetails / OAuth2User / OidcUser / Jwt ...
          +-- authorities: ROLE_*, SCOPE_*, ...
          +-- name: identity theo kiểu Authentication
          +-- authenticated: trạng thái xác thực
```

Trong OAuth2/OIDC Client, Authentication sau login thường là **`OAuth2AuthenticationToken`**, principal thường là `OAuth2User` hoặc `OidcUser`. Với Resource Server nhận Bearer JWT, Authentication có thể là `JwtAuthenticationToken` — đó là kiểu flow khác.

---

## 2. Reactor Context hoạt động thế nào?

**Reactor Context** là cấu trúc key–value gắn với **subscription** của một chuỗi Reactor. Nó không phải một `Map` toàn cục, cũng không phải biến thành viên mutable của service.

Một publisher được khai báo:

```java
Mono<String> result =
    ReactiveSecurityContextHolder.getContext()
        .map(SecurityContext::getAuthentication)
        .map(Authentication::getName);
```

Ở thời điểm khai báo `result`, code chưa nhất thiết có context hoặc thực hiện thao tác. Khi một subscriber subscribe và context phù hợp được cung cấp, chuỗi operators mới đọc context.

### 2.1. Assembly time và subscription time

```text
Test thread:
  Mono<String> result = buildPipeline()
                       [ASSEMBLY]

StepVerifier:
  StepVerifier.create(result)
              [SUBSCRIPTION]
    |
    v
Reactor Context được truyền vào pipeline
    |
    v
ReactiveSecurityContextHolder.getContext()
    |
    v
Kết quả / error / completion
```

**Sai lầm thường gặp:** tìm Authentication ngay lúc tạo publisher bằng ThreadLocal rồi cất vào field. Điều đó đánh mất tính request/subscriber-scoped của security context.

### 2.2. Context đi theo subscription, không phải theo thread cố định

Khi dùng `publishOn` hoặc `subscribeOn` trong một chuỗi Reactor thuần với việc truyền context đúng, Reactor Context có thể tiếp tục khả dụng qua các scheduler boundaries.

```java
Mono<String> pipeline = Mono.just("work")
    .publishOn(Schedulers.parallel())
    .flatMap(ignored ->
        ReactiveSecurityContextHolder.getContext()
            .map(SecurityContext::getAuthentication)
            .map(Authentication::getName))
    .contextWrite(
        ReactiveSecurityContextHolder.withAuthentication(alice));
```

Điểm chính: **`Thread.currentThread()` có thể thay đổi nhưng identity được gắn với subscription**.

Tuy nhiên, khi chuyển sang một API không thuộc Reactor hoặc tự tạo một subscription khác mà không mang Context theo, giá trị có thể mất. Đó là ranh giới cần kiểm thử.

### 2.3. ContextWrite có phạm vi theo hướng subscription

Một cách nghĩ hữu ích:

```text
upstream publishers/operators  <- Reactor Context do downstream subscriber cung cấp
                                                     ^
                                                contextWrite()
```

`contextWrite(...)` làm cho phần **upstream của nó** nhận được ngữ cảnh đã được biến đổi. Nó không biến context thành một biến toàn cục nhìn thấy từ mọi thread hoặc mọi nhánh không liên quan.

Đặt `contextWrite` ở đúng phạm vi publisher mà bạn muốn kiểm thử. Nếu gắn nó vào một nhánh con nhưng đọc context ở nhánh khác, kết quả có thể khác dự kiến.

### 2.4. Context không phải nơi đặt token tùy tiện

Spring Security quản lý security context, nhưng việc ứng dụng tự thêm client secret, refresh token, authorization code hoặc raw ID Token vào Reactor Context ở mọi operator là một thiết kế rủi ro.

Trong bài kiểm thử, chỉ cung cấp **Authentication/SecurityContext cần thiết**, tránh phản chiếu dữ liệu nhạy cảm ra logs và response.

---

## 3. ReactiveSecurityContextHolder API cốt lõi

Class:

```java
import org.springframework.security.core.context.ReactiveSecurityContextHolder;
```

Ba thao tác cần nhớ:

| API | Ý nghĩa |
| --- | --- |
| `getContext()` | Lấy `Mono<SecurityContext>` gắn với subscriber hiện tại |
| `withAuthentication(Authentication)` | Tạo Reactor `Context` chứa SecurityContext với Authentication đó |
| `withSecurityContext(Mono<? extends SecurityContext>)` | Tạo Context dùng một SecurityContext publisher |
| `clearContext()` | Tạo hàm dùng trong `contextWrite` để xóa security context khỏi một nhánh |

### 3.1. Đọc username an toàn trong Mono

```java
import reactor.core.publisher.Mono;

import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.ReactiveSecurityContextHolder;
import org.springframework.security.core.context.SecurityContext;

public final class CurrentIdentityService {

    public Mono<String> currentUsername() {
        return ReactiveSecurityContextHolder.getContext()
            .map(SecurityContext::getAuthentication)
            .filter(auth -> auth != null && auth.isAuthenticated())
            .map(Authentication::getName);
    }
}
```

Nếu không có context, chuỗi có thể kết thúc **rỗng** thay vì phát một username. Điều này là behavior của `Mono.empty()`, không phải một chuỗi `"null"`.

### 3.2. Cách xử lý anonymous tùy nghiệp vụ

```java
public Mono<String> currentUsernameOrGuest() {
    return ReactiveSecurityContextHolder.getContext()
        .map(SecurityContext::getAuthentication)
        .filter(auth -> auth != null && auth.isAuthenticated())
        .map(Authentication::getName)
        .defaultIfEmpty("guest");
}
```

**Lưu ý:** `isAuthenticated()` một mình không phải quy tắc xác định user là một end-user đã login. Spring Security có `AnonymousAuthenticationToken`; trong những cấu hình nhất định nó cũng có thể báo `isAuthenticated()=true`. Nếu nghiệp vụ cần phân biệt anonymous, dùng authorization policy/Spring Security trust resolver hoặc authorities phù hợp, không chỉ boolean này.

### 3.3. Truy cập principal kiểu OIDC trong pipeline

```java
import org.springframework.security.oauth2.client.authentication.OAuth2AuthenticationToken;
import org.springframework.security.oauth2.core.oidc.user.OidcUser;

public Mono<String> currentSubject() {
    return ReactiveSecurityContextHolder.getContext()
        .map(SecurityContext::getAuthentication)
        .filter(OAuth2AuthenticationToken.class::isInstance)
        .cast(OAuth2AuthenticationToken.class)
        .map(OAuth2AuthenticationToken::getPrincipal)
        .filter(OidcUser.class::isInstance)
        .cast(OidcUser.class)
        .map(user -> user.getIdToken().getSubject());
}
```

Nếu Authentication không phải OAuth2/OIDC Login thì method trả `Mono.empty()`. Đó là một lựa chọn API; nếu nghiệp vụ yêu cầu OIDC bắt buộc, có thể trả lỗi domain/authentication phù hợp thay vì âm thầm coi user không tồn tại.

### 3.4. ReactiveSecurityContextHolder không phải SecurityContextHolder

Sai trong reactive service:

```java
Mono<String> currentUser() {
    // ANTI-PATTERN: dựa trên ThreadLocal không đảm bảo theo subscription.
    Authentication auth =
        SecurityContextHolder.getContext().getAuthentication();

    return Mono.just(auth.getName());
}
```

Đúng theo Reactor:

```java
Mono<String> currentUser() {
    return ReactiveSecurityContextHolder.getContext()
        .map(SecurityContext::getAuthentication)
        .map(Authentication::getName);
}
```

Bằng cách này, cùng một service có thể phục vụ nhiều requests concurrent mà không dùng một mutable field lưu “current user”.

---

## 4. Dependency và thiết lập môi trường test

### 4.1. Maven

```xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-webflux</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-security</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-oauth2-client</artifactId>
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
    <dependency>
        <groupId>io.projectreactor</groupId>
        <artifactId>reactor-test</artifactId>
        <scope>test</scope>
    </dependency>
</dependencies>
```

`spring-boot-starter-test` thường đã cung cấp reactor-test trong hệ sinh thái Boot phù hợp; phần khai báo tường minh ở đây giúp nhấn mạnh dependency **`StepVerifier`**. Dùng dependency management BOM để đồng bộ phiên bản.

### 4.2. Gradle

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-client'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
    testImplementation 'io.projectreactor:reactor-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

Đây là cấu hình minh họa. Bước soạn bài Markdown **không chạy Gradle, không chỉnh build project**.

### 4.3. Các imports hữu ích

```java
import reactor.core.publisher.Mono;
import reactor.core.publisher.Flux;
import reactor.core.scheduler.Schedulers;
import reactor.test.StepVerifier;

import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.SecurityContext;
import org.springframework.security.core.context.ReactiveSecurityContextHolder;
import org.springframework.security.authentication.TestingAuthenticationToken;

import static org.springframework.security.test.web.reactive.server
    .SecurityMockServerConfigurers.mockUser;
import static org.springframework.security.test.web.reactive.server
    .SecurityMockServerConfigurers.mockOidcLogin;
import static org.springframework.security.test.web.reactive.server
    .SecurityMockServerConfigurers.mockOAuth2Login;
import static org.springframework.security.test.web.reactive.server
    .SecurityMockServerConfigurers.mockAuthentication;
```

Nếu Java style guide không cho xuống dòng trong import, hãy đặt mỗi import trên một dòng. Packages quan trọng ở đây là `org.springframework.security.test.web.reactive.server` và `org.springframework.security.core.context`.

---

## 5. Kiểm thử trực tiếp bằng StepVerifier và withAuthentication

Ở cấp **reactive service unit test**, không cần dựng HTTP server, security filter chain hoặc WebTestClient. Có thể tạo `Authentication` bằng Java và cung cấp vào Context lúc subscribe.

### 5.1. Service mẫu

```java
package example.identity;

import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.ReactiveSecurityContextHolder;
import org.springframework.security.core.context.SecurityContext;
import reactor.core.publisher.Mono;

public final class IdentityLookup {

    public Mono<String> currentName() {
        return ReactiveSecurityContextHolder.getContext()
            .map(SecurityContext::getAuthentication)
            .map(Authentication::getName);
    }
}
```

### 5.2. Test happy path

```java
package example.identity;

import org.junit.jupiter.api.Test;
import org.springframework.security.authentication.TestingAuthenticationToken;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.ReactiveSecurityContextHolder;
import reactor.test.StepVerifier;

class IdentityLookupTest {

    private final IdentityLookup identity = new IdentityLookup();

    @Test
    void seesAuthenticationFromReactorContext() {
        Authentication alice =
            new TestingAuthenticationToken(
                "alice", "not-used", "ROLE_READER");

        StepVerifier.create(
                identity.currentName()
                    .contextWrite(
                        ReactiveSecurityContextHolder
                            .withAuthentication(alice)))
            .expectNext("alice")
            .verifyComplete();
    }
}
```

Tại sao cách này đúng?

1. `identity.currentName()` trả về `Mono<String>` chờ subscription.
2. `contextWrite(withAuthentication(alice))` gắn SecurityContext cho subscription đó.
3. `StepVerifier.create` subscribe và kiểm tra emission.
4. Service đọc đúng Authentication mà không phụ thuộc thread chạy test.

### 5.3. Test khi không có context

```java
@Test
void noSecurityContextCompletesEmpty() {
    StepVerifier.create(identity.currentName())
        .verifyComplete();
}
```

Với service mẫu, `getContext()` không có giá trị nên chuỗi rỗng. **Nếu test đang dùng Spring Security Test listener và `@WithMockUser` ở cấp class**, context có thể đã được inject tự động; khi cần một test “thật sự không context”, hãy cô lập test hoặc chủ động clear context trong nhánh.

### 5.4. Explicit failure thay vì empty

Nếu API yêu cầu Authentication bắt buộc:

```java
import org.springframework.security.authentication.AuthenticationCredentialsNotFoundException;

public Mono<String> requiredName() {
    return ReactiveSecurityContextHolder.getContext()
        .map(SecurityContext::getAuthentication)
        .map(Authentication::getName)
        .switchIfEmpty(Mono.error(
            new AuthenticationCredentialsNotFoundException(
                "Authentication required")));
}
```

Test:

```java
StepVerifier.create(identity.requiredName())
    .expectError(AuthenticationCredentialsNotFoundException.class)
    .verify();
```

**Đây là behavior service do bạn thiết kế**; Spring Security không bắt buộc mọi lần gọi `ReactiveSecurityContextHolder.getContext()` thiếu context đều tự ném exception.

---

## 6. Kiểm thử SecurityContext đầy đủ với withSecurityContext()

Khi muốn kiểm tra một `SecurityContext` cụ thể thay vì truyền Authentication trực tiếp, tạo context:

```java
import org.springframework.security.core.context.SecurityContext;
import org.springframework.security.core.context.SecurityContextImpl;

Authentication bob = new TestingAuthenticationToken(
    "bob", "not-used", "ROLE_AUDITOR");

SecurityContext context = new SecurityContextImpl(bob);

Mono<String> currentName = ReactiveSecurityContextHolder.getContext()
    .map(SecurityContext::getAuthentication)
    .map(Authentication::getName);

StepVerifier.create(
        currentName.contextWrite(
            ReactiveSecurityContextHolder
                .withSecurityContext(Mono.just(context))))
    .expectNext("bob")
    .verifyComplete();
```

### 6.1. Vì sao withSecurityContext nhận Mono?

Trong reactive model, SecurityContext có thể đến từ một **reactive repository** hoặc deferred load. Spring Security cho phép gắn một `Mono<? extends SecurityContext>` vào Reactor context.

Ví dụ:

```java
Mono<SecurityContext> contextPublisher = Mono.just(context);

Mono<String> result = currentName.contextWrite(
    ReactiveSecurityContextHolder.withSecurityContext(contextPublisher));
```

**Không cần `block()` để lấy context trước khi tạo pipeline.** Bên đọc sử dụng `ReactiveSecurityContextHolder.getContext()` để subscribe theo đúng flow.

### 6.2. Kiểm thử clearContext()

Khi cần xác nhận một nhánh được dọn security context:

```java
Mono<String> result = ReactiveSecurityContextHolder.getContext()
    .map(SecurityContext::getAuthentication)
    .map(Authentication::getName)
    .defaultIfEmpty("guest")
    .contextWrite(ReactiveSecurityContextHolder.clearContext());

StepVerifier.create(result)
    .expectNext("guest")
    .verifyComplete();
```

Trong test độc lập này, `clearContext()@@ khiến việc đọc SecurityContext rỗng ở phần upstream. Nó **không phải API thực hiện logout session của OP hoặc thu hồi access token**.

### 6.3. Đừng mutate một SecurityContext dùng chung nhiều tests

Một `SecurityContextImpl` là object mutable. Nếu dùng:

```java
static final SecurityContext SHARED = new SecurityContextImpl();
```

rồi các tests đồng thời thay `setAuthentication(...)`, kết quả có thể bị nhiễm chéo. Tạo context và Authentication riêng cho từng test/subscription hoặc dùng fixture immutable khi thích hợp.

---

## 7. Đọc và kiểm tra authorities trong Reactor

Giả sử một service kiểm tra quyền:

```java
package example.security;

import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.ReactiveSecurityContextHolder;
import org.springframework.security.core.context.SecurityContext;
import org.springframework.security.core.GrantedAuthority;
import reactor.core.publisher.Mono;

public final class AuthorityLookup {

    public Mono<Boolean> has(String authority) {
        return ReactiveSecurityContextHolder.getContext()
            .map(SecurityContext::getAuthentication)
            .map(Authentication::getAuthorities)
            .map(granted -> granted.stream()
                .map(GrantedAuthority::getAuthority)
                .anyMatch(authority::equals))
            .defaultIfEmpty(false);
    }
}
```

Test:

```java
@Test
void checksAuthoritiesFromCurrentSubscription() {
    Authentication editor = new TestingAuthenticationToken(
        "editor", "unused", "ROLE_EDITOR", "SCOPE_reports.read");

    Mono<Boolean> allowed = new AuthorityLookup()
        .has("ROLE_EDITOR")
        .contextWrite(
            ReactiveSecurityContextHolder.withAuthentication(editor));

    StepVerifier.create(allowed)
        .expectNext(true)
        .verifyComplete();
}
```

Negative test:

```java
@Test
void rejectsWhenRequiredAuthorityIsAbsent() {
    Authentication viewer = new TestingAuthenticationToken(
        "viewer", "unused", "ROLE_VIEWER");

    Mono<Boolean> allowed = new AuthorityLookup()
        .has("ROLE_EDITOR")
        .contextWrite(
            ReactiveSecurityContextHolder.withAuthentication(viewer));

    StepVerifier.create(allowed)
        .expectNext(false)
        .verifyComplete();
}
```

**Quan trọng:** `GrantedAuthority` có thể là `ROLE_EDITOR` hoặc `SCOPE_reports.read`. Một OIDC claim tên `groups` không tự chuyển thành `ROLE_EDITOR` nếu production không có role mapper.

---

## 8. Giả lập OIDC principal thực sự trong Reactor Context

Với Spring Security OAuth2 Client, production Authentication thường là `OAuth2AuthenticationToken` có `OidcUser`. Nếu muốn unit test service đọc `OidcUser`, có thể tự dựng một principal và Authentication.

### 8.1. Khởi tạo OidcUser mock

```java
import org.springframework.security.core.authority.AuthorityUtils;
import org.springframework.security.oauth2.core.oidc.OidcIdToken;
import org.springframework.security.oauth2.core.oidc.user.DefaultOidcUser;
import org.springframework.security.oauth2.core.oidc.user.OidcUser;

OidcIdToken idToken = OidcIdToken.withTokenValue("synthetic-id-token")
    .claim("sub", "employee-42")
    .claim("tenant_id", "tenant-a")
    .claim("preferred_username", "nguyen.an")
    .build();

OidcUser user = new DefaultOidcUser(
    AuthorityUtils.createAuthorityList(
        "SCOPE_read", "ROLE_REPORT_READER"),
    idToken,
    "preferred_username");
```

Đây là **mock ID Token object**, không phải ID Token được OP ký hoặc đã được JwtDecoder xác minh.

### 8.2. Tạo OAuth2AuthenticationToken

```java
import org.springframework.security.oauth2.client.authentication.OAuth2AuthenticationToken;

OAuth2AuthenticationToken authentication =
    new OAuth2AuthenticationToken(
        user,
        user.getAuthorities(),
        "company");
```

Registration ID `company` thể hiện client login đã sử dụng; nó **không tự chứng minh issuer thực** của ID Token. Khi test ranh giới multi-provider, hãy đặt registrationId, ID Token issuer, subject và policy độc lập một cách nhất quán.

### 8.3. StepVerifier đọc subject

Service:

```java
import org.springframework.security.oauth2.core.oidc.user.OidcUser;

public Mono<String> currentOidcSubject() {
    return ReactiveSecurityContextHolder.getContext()
        .map(SecurityContext::getAuthentication)
        .filter(auth -> auth instanceof OAuth2AuthenticationToken)
        .map(auth -> (OAuth2AuthenticationToken) auth)
        .map(OAuth2AuthenticationToken::getPrincipal)
        .filter(principal -> principal instanceof OidcUser)
        .map(principal -> ((OidcUser) principal).getIdToken().getSubject());
}
```

Test:

```java
StepVerifier.create(
        identityService.currentOidcSubject()
            .contextWrite(
                ReactiveSecurityContextHolder
                    .withAuthentication(authentication)))
    .expectNext("employee-42")
    .verifyComplete();
```

Nếu service yêu cầu `@PreAuthorize`, phải kiểm thử thông qua **Spring-managed proxy** trong một context bật reactive method security; tạo service bằng `new` không tự áp dụng method interceptor.

### 8.4. Khi nào nên tự tạo principal?

- Unit test một service đọc `Authentication` từ Reactor Context;
- Test policy phụ thuộc `registrationId`, `sub`, `tenant_id` hoặc authorities;
- Không muốn khởi động HTTP server;
- Cần test context propagation hoặc cancellation trên publisher.

Khi mục tiêu là **HTTP controller test**, dùng `WebTestClient.mutateWith(mockOidcLogin())` thường ngắn hơn và phù hợp hơn.

---

## 9. WebTestClient và Spring Security Reactive

`WebTestClient` là công cụ kiểm thử HTTP WebFlux. Spring Security Test có các `WebTestClientConfigurer` để inject Authentication cho request kiểm thử.

### 9.1. Bảng chọn helper

| Mục tiêu của request | Spring Security Test Reactive helper |
| --- | --- |
| Generic username/roles | **`mockUser()`** |
| Authentication hoàn chỉnh | **`mockAuthentication(authentication)`** |
| OAuth2 login principal + attributes | **`mockOAuth2Login()`** |
| OIDC login principal + ID Token/UserInfo | **`mockOidcLogin()`** |
| Authorized client độc lập | `mockOAuth2Client("registration-id")` |
| Resource Server Bearer JWT | **`mockJwt()`** |
| Resource Server opaque token | `mockOpaqueToken()` |
| CSRF trên HTTP request | `csrf()` mutator |

**Không gọi `oidcLogin()` của Servlet MockMvc trên WebTestClient.**

### 9.2. Setup WebTestClient rõ ràng

Nếu tự bind tới Spring ApplicationContext:

```java
import org.junit.jupiter.api.BeforeEach;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.context.ApplicationContext;
import org.springframework.test.web.reactive.server.WebTestClient;

import static org.springframework.security.test.web.reactive.server
    .SecurityMockServerConfigurers.springSecurity;

class ReactiveWebTests {

    @Autowired
    ApplicationContext context;

    WebTestClient client;

    @BeforeEach
    void setup() {
        client = WebTestClient.bindToApplicationContext(context)
            .apply(springSecurity())
            .configureClient()
            .build();
    }
}
```

Đoạn này giả định test class đã có Spring Test context, ví dụ `@SpringJUnitConfig`, `@WebFluxTest` hoặc `@SpringBootTest` với WebFlux. Nếu dùng `@WebFluxTest` được auto-configure `WebTestClient`, có thể inject client trực tiếp nhưng vẫn phải xác nhận Spring Security filter chain có hiệu lực.

### 9.3. @WebFluxTest khác @SpringBootTest

- `@WebFluxTest`: tập trung MVC-equivalent WebFlux controllers, codecs, validators và những config được slice nạp; các services khác có thể cần mock/import.
- `@SpringBootTest`: toàn application context, phù hợp kiểm tra wiring rộng hơn.
- `WebTestClient.bindToApplicationContext`: chạy HTTP exchange mô phỏng **trong application context**, không cần mở TCP port.
- `WebTestClient.bindToServer`: HTTP client nói chuyện với server thật; mock mutators gắn SecurityContext vào in-memory server exchange **không thể thay thế xác thực thực sự ở server process khác**.

Đừng dùng `@WithMockUser` ở test thread rồi giả định một server đang chạy trên port khác sẽ nhìn thấy ThreadLocal của test đó.

---

## 10. mockUser(): generic principal và authorities

Khi controller chỉ cần `Principal.getName()`, `Authentication.getName()` hoặc role, `mockUser()` là đủ.

Controller:

```java
import java.security.Principal;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Mono;

@RestController
class GreetingController {

    @GetMapping("/api/greet")
    Mono<String> greet(Principal principal) {
        return Mono.just("Hello " + principal.getName());
    }
}
```

Test:

```java
import static org.springframework.security.test.web.reactive.server
    .SecurityMockServerConfigurers.mockUser;

client.mutateWith(mockUser("alice").roles("USER"))
    .get().uri("/api/greet")
    .exchange()
    .expectStatus().isOk()
    .expectBody(String.class).isEqualTo("Hello alice");
```

### 10.1. @WithMockUser trong WebTestClient tests

Spring Security Test cũng hỗ trợ:

```java
@Test
@WithMockUser(username = "alice", roles = "USER")
void greetingWithAnnotation() {
    client.get().uri("/api/greet")
        .exchange()
        .expectStatus().isOk()
        .expectBody(String.class).isEqualTo("Hello alice");
}
```

Đoạn này yêu cầu **Spring Test context và Spring Security test listeners** đúng. Đối với HTTP request độc lập và fixtures khác nhau theo từng call, `mutateWith(mockUser(...))` thường minh bạch hơn.

### 10.2. @WithMockUser không tạo OidcUser

Nếu controller khai báo `@AuthenticationPrincipal OidcUser`, một `@WithMockUser` thông thường chỉ tạo principal là Spring Security `User`, không phải `OidcUser`.

Hãy dùng `mockOidcLogin()` hoặc `mockAuthentication(OAuth2AuthenticationToken)` để kiểm thử đúng principal type.

### 10.3. authorities và roles không giống nhau

```java
client.mutateWith(mockUser("bob")
        .authorities(
            new SimpleGrantedAuthority("SCOPE_reports.read")))
    .get().uri("/api/reports")
    .exchange();
```

`hasRole("REPORT_READER")` sẽ tìm `ROLE_REPORT_READER` (default prefix), không phải `SCOPE_reports.read`. Test phải đặt authority khớp với production authorization policy.

---

## 11. mockAuthentication(): kiểm thử Authentication tùy chỉnh

Khi muốn inject đúng instance Authentication, dùng:

```java
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.authority.SimpleGrantedAuthority;

Authentication auth = UsernamePasswordAuthenticationToken.authenticated(
    "user-42",
    "unused",
    java.util.List.of(
        new SimpleGrantedAuthority("ROLE_REPORT_READER")));

client.mutateWith(mockAuthentication(auth))
    .get().uri("/api/whoami")
    .exchange()
    .expectStatus().isOk();
```

`mockAuthentication(...)` là **test mutator trên Reactive WebTestClient**. Nó không qua password check, token exchange, issuer validation hoặc một AuthenticationManager production.

### 11.1. Lựa chọn khi có principal tùy chỉnh

Nếu code cần:
- Custom `UserDetails`;
- `OAuth2AuthenticationToken` đặc thù;
- `JwtAuthenticationToken`;
- Một test implementation của `Authentication`;

thì inject instance phù hợp qua `mockAuthentication`. Đừng ép controller cast principal thành `OidcUser` nếu fixture đang là String hoặc `UserDetails`.

### 11.2. Test đủ cả allowed và denied

Một policy kiểm tra `ROLE_REPORT_READER` cần ít nhất:
- User có authority → được phép;
- User đã authenticated nhưng thiếu authority → bị từ chối;
- Không có authenticated user → nhận 401/302 theo security entry point.

Test thành công đơn lẻ không chứng minh security filter đã thật sự được áp dụng.

---

## 12. mockOidcLogin(): kiểm thử OIDC principal và claims

Với WebFlux OIDC Client, helper chuẩn:

```java
import static org.springframework.security.test.web.reactive.server
    .SecurityMockServerConfigurers.mockOidcLogin;
```

Ví dụ:

```java
client.mutateWith(mockOidcLogin())
    .get().uri("/api/oidc-subject")
    .exchange()
    .expectStatus().isOk()
    .expectBody(String.class).isEqualTo("user");
```

Theo tài liệu Spring Security Test 6.5, `mockOidcLogin()` cung cấp mặc định:
- Một `OidcUser`;
- `OidcIdToken` có `sub=user`;
- `OidcUserInfo` không có claims;
- Authorities có `SCOPE_read`;
- Một mock authorized client được liên kết trong `ServerOAuth2AuthorizedClientRepository` phù hợp.

### 12.1. ID Token claims

```java
client.mutateWith(mockOidcLogin()
        .idToken(idToken -> idToken
            .claim("sub", "employee-42")
            .claim("tenant_id", "tenant-a")
            .claim("preferred_username", "nguyen.an")))
    .get().uri("/api/oidc-tenant")
    .exchange()
    .expectStatus().isOk()
    .expectBody(String.class).isEqualTo("tenant-a");
```

`idToken(...)` chỉ chỉnh **model ID Token trong fixture**. Nó không ký JWT thật và không chạy JwtDecoder/OIDC issuer/nonce validation.

### 12.2. UserInfo — khác tên method với Servlet

Trong **Reactive Spring Security Test 6.5**, dùng:

```java
client.mutateWith(mockOidcLogin()
        .userInfo(info -> info
            .claim("name", "Nguyễn An")
            .claim("locale", "vi-VN")))
    .get().uri("/api/display-name")
    .exchange()
    .expectStatus().isOk();
```

**API Reactive là `mockOidcLogin().userInfo(...)`**. Đừng copy `oidcLogin().userInfoToken(...)` từ Servlet MockMvc rồi áp vào Reactive.

### 12.3. Authorities

```java
client.mutateWith(mockOidcLogin()
        .authorities(
            new SimpleGrantedAuthority("ROLE_REPORT_READER"),
            new SimpleGrantedAuthority("SCOPE_reports.read")))
    .get().uri("/api/reports")
    .exchange()
    .expectStatus().isOk();
```

Những authorities được chỉ định phục vụ test authorization. **Claim `groups` hoặc `roles` trong ID Token không tự động được map thành `ROLE_*` bởi post-processor**. Kiểm thử role mapping production ở service/mapper riêng.

### 12.4. Custom OidcUser

Nếu principal name cần dùng `preferred_username`:

```java
OidcUser custom = new DefaultOidcUser(
    AuthorityUtils.createAuthorityList("SCOPE_read"),
    OidcIdToken.withTokenValue("synthetic-token")
        .claim("sub", "employee-42")
        .claim("preferred_username", "nguyen.an")
        .build(),
    "preferred_username");

client.mutateWith(mockOidcLogin().oidcUser(custom))
    .get().uri("/api/whoami")
    .exchange();
```

`oidcUser(custom)` thay principal hoàn chỉnh. Nếu đã cung cấp custom principal, tránh giả định các `idToken(...)` hoặc `userInfo(...)` khác tự merge theo precedence bạn mong muốn.

### 12.5. Registration và multi-provider

`mockOidcLogin().clientRegistration(clientRegistration)` cho phép chọn `ClientRegistration` gắn với authorized client test.

Ví dụ cùng `sub=user-42` nhưng hai issuers khác nhau không tự là một danh tính; test identity mapping nên dùng **`(issuer, subject)`** và chính sách account linking rõ ràng. Post-processor không tự kiểm tra rằng ID Token issuer claim khớp registration.

---

## 13. mockOAuth2Login(): kiểm thử principal OAuth2 không phải OIDC

Một controller cần `OAuth2User.getAttribute("user_id")`:

```java
import org.springframework.security.oauth2.core.user.OAuth2User;

@GetMapping("/api/oauth2-user-id")
Mono<String> oauth2UserId(@AuthenticationPrincipal OAuth2User user) {
    return Mono.justOrEmpty(user.getAttribute("user_id"));
}
```

Test:

```java
client.mutateWith(mockOAuth2Login()
        .attributes(attrs -> {
            attrs.put("sub", "user-42");
            attrs.put("user_id", "internal-123");
            attrs.put("email_verified", Boolean.TRUE);
        }))
    .get().uri("/api/oauth2-user-id")
    .exchange()
    .expectStatus().isOk()
    .expectBody(String.class).isEqualTo("internal-123");
```

`mockOAuth2Login()` tạo `OAuth2User` với attributes; nó **không tự có `OidcIdToken`**.

### 13.1. Custom OAuth2User

```java
OAuth2User custom = new DefaultOAuth2User(
    AuthorityUtils.createAuthorityList("SCOPE_read"),
    java.util.Map.of(
        "user_name", "partner-01",
        "user_id", "partner-123"),
    "user_name");

client.mutateWith(mockOAuth2Login().oauth2User(custom))
    .get().uri("/api/whoami")
    .exchange();
```

`oauth2User(custom)` hữu ích khi cần test `getName()` hoặc custom principal implementation.

### 13.2. Dùng đúng kiểu dữ liệu claim

Một attribute `email_verified` thường là Boolean. Nếu test đưa chuỗi `"true"`, một `Boolean` cast trong production có thể lỗi.

Với list/group claims, dùng đúng type như `List<String>` hoặc `Map<String,Object>`. Không giả định dữ liệu raw của mọi OP giống nhau.

---

## 14. WebFlux controller đọc Authentication từ Reactor Context

Để thấy rõ context được đọc tại **subscription time**, tạo controller:

```java
package example.web;

import java.util.Map;

import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.ReactiveSecurityContextHolder;
import org.springframework.security.core.context.SecurityContext;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.oauth2.core.oidc.user.OidcUser;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Mono;

@RestController
class IdentityController {

    @GetMapping("/api/whoami")
    Mono<Map<String, String>> whoami() {
        return ReactiveSecurityContextHolder.getContext()
            .map(SecurityContext::getAuthentication)
            .map(auth -> Map.of(
                "name", auth.getName(),
                "authenticationType",
                    auth.getClass().getSimpleName()));
    }

    @GetMapping("/api/oidc-subject")
    Mono<String> subject(@AuthenticationPrincipal OidcUser user) {
        return Mono.just(user.getIdToken().getSubject());
    }

    @GetMapping("/api/oidc-tenant")
    Mono<String> tenant(@AuthenticationPrincipal OidcUser user) {
        return Mono.justOrEmpty(
            user.getIdToken().getClaimAsString("tenant_id"));
    }
}
```

Đoạn này giả định các endpoints được bảo vệ và `/api/oidc-*` chỉ được gọi khi Authentication thực sự có `OidcUser`. Với ứng dụng nhận nhiều kiểu user, cần kiểm tra principal type/missing claim để tránh `NullPointerException`.

### 14.1. Config SecurityWebFilterChain

```java
package example.security;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.web.server.SecurityWebFilterChain;

@Configuration
@EnableWebFluxSecurity
class WebSecurityConfiguration {

    @Bean
    SecurityWebFilterChain webSecurity(ServerHttpSecurity http) {
        return http
            .authorizeExchange(exchanges -> exchanges
                .pathMatchers("/public", "/error").permitAll()
                .anyExchange().authenticated())
            .httpBasic(Customizer.withDefaults())
            .build();
    }
}
```

Cấu hình này **cố ý dùng HTTP Basic trong test/demo** để một anonymous request thường nhận 401 dễ quan sát. Khi ứng dụng production bật `oauth2Login()`, entry point của browser có thể trả **302 đến trang đăng nhập**, không phải 401.

### 14.2. Test với @WebFluxTest

```java
package example.web;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.WebFluxTest;
import org.springframework.context.annotation.Import;
import org.springframework.test.web.reactive.server.WebTestClient;

import static org.springframework.security.test.web.reactive.server
    .SecurityMockServerConfigurers.mockOidcLogin;
import static org.springframework.security.test.web.reactive.server
    .SecurityMockServerConfigurers.mockUser;

@WebFluxTest(controllers = IdentityController.class)
@Import(WebSecurityConfiguration.class)
class IdentityControllerWebTest {

    @Autowired
    WebTestClient client;

    @Test
    void currentAuthenticationComesFromRequest() {
        client.mutateWith(mockUser("alice").roles("USER"))
            .get().uri("/api/whoami")
            .exchange()
            .expectStatus().isOk()
            .expectBody()
            .jsonPath("$.name").isEqualTo("alice");
    }

    @Test
    void oidcSubjectIsAvailable() {
        client.mutateWith(mockOidcLogin()
                .idToken(token ->
                    token.claim("sub", "employee-42")))
            .get().uri("/api/oidc-subject")
            .exchange()
            .expectStatus().isOk()
            .expectBody(String.class).isEqualTo("employee-42");
    }

    @Test
    void oidcCustomClaimIsAvailable() {
        client.mutateWith(mockOidcLogin()
                .idToken(token ->
                    token.claim("tenant_id", "tenant-a")))
            .get().uri("/api/oidc-tenant")
            .exchange()
            .expectStatus().isOk()
            .expectBody(String.class).isEqualTo("tenant-a");
    }

    @Test
    void anonymousRequestIsRejected() {
        client.get().uri("/api/whoami")
            .exchange()
            .expectStatus().isUnauthorized();
    }
}
```

**Điều kiện chạy:** test phải có Spring Security filters thực sự tích hợp với `WebTestClient`. Với `@WebFluxTest` cấu hình chuẩn, Spring Boot thường auto-configure WebTestClient; khi tự dựng client hoặc thay slice configuration, có thể phải dùng `.apply(springSecurity())` rõ ràng như mục 9.

**Lưu ý:** import `WebSecurityConfiguration` từ package khác phải chỉnh Java import tương ứng trong source thực tế. Ví dụ tách class thành nhiều file theo package là minh họa kiến trúc, không phải một file Java copy/paste duy nhất.

---

## 15. Kiểm thử reactive method security với @WithMockUser

Phần này quan trọng vì một service reactive có thể được bảo vệ bởi `@PreAuthorize`.

Service mẫu:

```java
package example.reports;

import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.ReactiveSecurityContextHolder;
import org.springframework.security.core.context.SecurityContext;
import org.springframework.stereotype.Service;
import reactor.core.publisher.Mono;

@Service
public class ReportService {

    @PreAuthorize("hasAuthority('ROLE_REPORT_READER')")
    public Mono<String> summary() {
        return ReactiveSecurityContextHolder.getContext()
            .map(SecurityContext::getAuthentication)
            .map(auth -> "summary-for:" + auth.getName());
    }
}
```

Cấu hình method security:

```java
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.method.configuration.EnableReactiveMethodSecurity;

@Configuration
@EnableReactiveMethodSecurity
class ReportMethodSecurityConfiguration {
}
```

### 15.1. Test bằng @WithMockUser và StepVerifier

```java
package example.reports;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.test.context.support.WithMockUser;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;
import reactor.test.StepVerifier;

@SpringJUnitConfig(classes = {
    ReportMethodSecurityConfiguration.class,
    ReportService.class
})
class ReportServiceSecurityTest {

    @Autowired
    ReportService reports;

    @Test
    @WithMockUser(
        username = "alice",
        authorities = "ROLE_REPORT_READER")
    void readerCanRead() {
        StepVerifier.create(reports.summary())
            .expectNext("summary-for:alice")
            .verifyComplete();
    }

    @Test
    @WithMockUser(
        username = "bob",
        authorities = "ROLE_VIEWER")
    void viewerCannotRead() {
        StepVerifier.create(reports.summary())
            .expectError(AccessDeniedException.class)
            .verify();
    }

    @Test
    void anonymousCannotRead() {
        StepVerifier.create(reports.summary())
            .expectError(AccessDeniedException.class)
            .verify();
    }
}
```

Spring Security tài liệu reactive method testing sử dụng **`@WithMockUser`** cùng `StepVerifier`. Để hoạt động, cần:
- Spring Test extension/listeners;
- Spring-managed bean/proxy của service;
- `@EnableReactiveMethodSecurity`;
- `ReactorContextTestExecutionListener` khi môi trường test không tự đăng ký;
- Publisher được **subscribe**, ví dụ bằng StepVerifier.

### 15.2. ReactorContextTestExecutionListener làm gì?

Spring Security test infrastructure có hai listener liên quan:

| Listener | Vai trò |
| --- | --- |
| `WithSecurityContextTestExecutionListener` | Khởi tạo test Authentication theo `@WithMockUser` / `@WithSecurityContext` |
| **`ReactorContextTestExecutionListener`** | Đưa security context test sang **ReactiveSecurityContextHolder/Reactor context** cho reactive tests |

Nếu chỉ có ThreadLocal TestSecurityContextHolder mà không có Reactor listener, unit test Java đồng bộ có thể thấy user nhưng publisher reactive không nhất thiết nhận được.

### 15.3. Khi test listeners bị tùy chỉnh thủ công

```java
@TestExecutionListeners(
    listeners = {
        WithSecurityContextTestExecutionListener.class,
        ReactorContextTestExecutionListener.class
    },
    mergeMode = TestExecutionListeners.MergeMode.MERGE_WITH_DEFAULTS
)
```

Đây là **mẫu bổ sung khi cấu hình listener bị thiếu**, không phải lời khuyên luôn đăng ký trùng mọi listener trong mọi test. Với Spring Security Test + Spring Test chuẩn, các listeners có thể đã được phát hiện/đăng ký. Nếu tự cấu hình, kiểm tra listener order và merge semantics đúng version.

### 15.4. Vì sao cần cả positive và negative cases?

Nếu test chỉ:

```java
@WithMockUser(authorities = "ROLE_REPORT_READER")
```

và nhận được kết quả, vẫn có thể có bug là `@EnableReactiveMethodSecurity` chưa bật: method không bị chặn, positive case vẫn pass.

Test thiếu quyền (mong `AccessDeniedException`) là phần quan trọng để chứng minh method interceptor thực sự hoạt động.

### 15.5. Không new service khi muốn test @PreAuthorize

Sai:

```java
ReportService service = new ReportService();
StepVerifier.create(service.summary()) ...;
```

Object được tạo bằng `new` bên ngoài Spring context **không có method-security AOP proxy**. Nếu mục tiêu kiểm thử annotation, inject bean từ Spring Test context.

---

## 16. Kiểm thử method security với contextWrite thay vì annotation

Trong một số trường hợp bạn cần principal phức tạp như `OidcUser` mà `@WithMockUser` không cung cấp. Có thể cung cấp `OAuth2AuthenticationToken` bằng `contextWrite` ngay trên publisher trả bởi Spring-managed bean:

```java
OidcUser oidcUser = new DefaultOidcUser(
    AuthorityUtils.createAuthorityList(
        "ROLE_REPORT_READER"),
    OidcIdToken.withTokenValue("synthetic")
        .claim("sub", "employee-42")
        .build());

Authentication authentication = new OAuth2AuthenticationToken(
    oidcUser,
    oidcUser.getAuthorities(),
    "company");

Mono<String> result = reportService.summary()
    .contextWrite(
        ReactiveSecurityContextHolder.withAuthentication(authentication));

StepVerifier.create(result)
    .expectNext("summary-for:employee-42")
    .verifyComplete();
```

Điều kiện:
- `reportService` phải là **Spring-managed proxy** nếu cần `@PreAuthorize`;
- Method phải trả publisher và interceptor đọc context trong subscription;
- `OidcUser.getName()` mặc định thường dựa trên subject, nên expected username từ fixture là `employee-42`;
- Mục tiêu là test **authorization với Authentication có loại principal cụ thể**, không phải test ID Token signature.

### 16.1. Test tenant/role kết hợp

Nếu có method policy như:

```java
@PreAuthorize("hasAuthority('ROLE_REPORT_READER') and @tenantGuard.allowed(#tenantId)")
public Mono<String> report(String tenantId) { ... }
```

test phải verify cả:
- User có role trong tenant A gọi tenant A → pass;
- User có role trong tenant A gọi tenant B → denied;
- User thiếu role trong tenant A → denied;
- Anonymous → denied.

`withAuthentication` giúp truyền principal có `tenant_id` test fixture cho service, nhưng **không tự thực thi tenant guard** nếu service không được Spring AOP quản lý.

---

## 17. Spring-managed @WithMockUser và direct contextWrite khác nhau thế nào?

| Cách test | Phù hợp | Phụ thuộc |
| --- | --- | --- |
| **`@WithMockUser`** | Reactive method security với generic UserDetails + roles | Spring Test + Security test listeners |
| **`.contextWrite(withAuthentication(...))`** | Unit test publisher hoặc service cần custom Authentication | Reactor Context trên publisher |
| **`.contextWrite(withSecurityContext(Mono.just(...)))`** | Test SecurityContext tùy chỉnh/deferred | SecurityContext publisher |
| **`WebTestClient.mutateWith(mockUser())`** | Generic HTTP WebFlux request | Spring Security WebTestClient support |
| **`WebTestClient.mutateWith(mockOidcLogin())`** | OIDC HTTP principal, claims, authorities | Spring Security reactive test config |
| **`WebTestClient.mutateWith(mockAuthentication(...))`** | HTTP request với Authentication custom | Spring Security reactive test config |

**Không có một cách duy nhất luôn tốt hơn.** Chọn dựa trên boundary:
- Unit test publisher: `StepVerifier + contextWrite`;
- Spring AOP method test: `@WithMockUser` hoặc contextWrite trên proxied service;
- WebFlux HTTP test: `WebTestClient.mutateWith`;
- OIDC redirect/PKCE/JWT validation thật: integration test với mock OP.

---

## 18. Kiểm thử context propagation qua các Reactor operators

Một câu hỏi thực tế là **“khi đổi scheduler, Authentication có còn đúng không?”**.

### 18.1. Với publishOn

```java
@Test
void keepsIdentityAcrossPublishOn() {
    Authentication alice = new TestingAuthenticationToken(
        "alice", "unused", "ROLE_USER");

    Mono<String> pipeline = Mono.just("request")
        .publishOn(Schedulers.parallel())
        .flatMap(ignored ->
            ReactiveSecurityContextHolder.getContext()
                .map(SecurityContext::getAuthentication)
                .map(Authentication::getName))
        .contextWrite(
            ReactiveSecurityContextHolder.withAuthentication(alice));

    StepVerifier.create(pipeline)
        .expectNext("alice")
        .verifyComplete();
}
```

Đây là một test cho **native Reactor Context propagation**. Bạn không cần copy ThreadLocal thủ công từ thread test sang `Schedulers.parallel()`.

### 18.2. Với Flux.flatMap concurrent

```java
@Test
void multipleElementsSeeSameSubscriberIdentity() {
    Authentication alice = new TestingAuthenticationToken(
        "alice", "unused", "ROLE_USER");

    Flux<String> values = Flux.range(1, 3)
        .flatMap(i ->
            ReactiveSecurityContextHolder.getContext()
                .map(SecurityContext::getAuthentication)
                .map(auth -> auth.getName() + ":" + i))
        .contextWrite(
            ReactiveSecurityContextHolder.withAuthentication(alice));

    StepVerifier.create(values.collectList())
        .assertNext(list -> {
            org.assertj.core.api.Assertions.assertThat(list)
                .containsExactlyInAnyOrder(
                    "alice:1", "alice:2", "alice:3");
        })
        .verifyComplete();
}
```

`flatMap` có thể thay đổi thứ tự emission, nên dùng `containsExactlyInAnyOrder` thay vì giả định một trật tự cố định.

### 18.3. Kiểm thử hai subscriptions khác danh tính

```java
@Test
void subscriptionsDoNotShareCurrentUser() {
    Mono<String> current = ReactiveSecurityContextHolder.getContext()
        .map(SecurityContext::getAuthentication)
        .map(Authentication::getName);

    Authentication alice = new TestingAuthenticationToken(
        "alice", "unused", "ROLE_USER");
    Authentication bob = new TestingAuthenticationToken(
        "bob", "unused", "ROLE_USER");

    StepVerifier.create(current.contextWrite(
            ReactiveSecurityContextHolder.withAuthentication(alice)))
        .expectNext("alice")
        .verifyComplete();

    StepVerifier.create(current.contextWrite(
            ReactiveSecurityContextHolder.withAuthentication(bob)))
        .expectNext("bob")
        .verifyComplete();
}
```

Hai subscriptions dùng cùng **publisher blueprint** nhưng có contexts riêng. Không tạo một `static String currentUsername` rồi ghi đè ở mỗi request.

### 18.4. Không dùng Thread.sleep() để “chờ context xuất hiện”

Reactor Context được xác định theo subscription, không theo thời gian trễ. Nếu test thiếu context, đợi 1 giây không tự thêm Authentication. Hãy kiểm tra vị trí `contextWrite`, WebTestClient config và test listeners.

---

## 19. Các ranh giới có thể làm mất SecurityContext

Reactor Context có thể giữ nguyên qua nhiều operators, nhưng không có nghĩa mọi cơ chế asynchronous bên ngoài đều tự kế thừa.

### 19.1. Manually subscribe()

Anti-pattern trong service:

```java
public Mono<String> process() {
    downstreamCall()
        .subscribe(result -> audit(result)); // Detached subscription!
    return Mono.just("accepted");
}
```

Subscription mới có lifecycle và Context riêng; người gọi không thể dùng `StepVerifier` của publisher được return để kiểm soát/kiểm tra đầy đủ side effect. SecurityContext có thể không được truyền đúng vào detached subscription.

Tốt hơn:

```java
public Mono<String> process() {
    return downstreamCall()
        .flatMap(result -> audit(result)
            .thenReturn("accepted"));
}
```

Trong ví dụ, `audit(result)` trả `Mono<Void>`; như vậy cùng chain được compose, context và error/cancellation được kiểm soát tốt hơn.

### 19.2. Chuyển sang CompletableFuture/Executor

```java
CompletableFuture.supplyAsync(() ->
    SecurityContextHolder.getContext().getAuthentication());
```

Đoạn trên dùng một thread khác và ThreadLocal. Nó không tự tiếp cận ReactiveSecurityContextHolder của subscription.

Nếu cần gọi API blocking:
- Ưu tiên giữ dữ liệu flow dưới publisher và đi qua `boundedElastic` hợp lý;
- Chuyển các identity fields tối thiểu đã xác minh vào đối số của callable khi cần;
- Cân nhắc context propagation bridge/instrumentation phù hợp phiên bản Reactor;
- Không tự copy toàn bộ SecurityContext sang global mutable variable;
- Không thực hiện blocking trên event loop.

### 19.3. Bật automatic context propagation không thay authentication

Reactor có chức năng hỗ trợ automatic context propagation qua một số ThreadLocal bridges khi được cấu hình. Đây là **cơ chế interoperability**, không có nghĩa có thể quay lại dùng `SecurityContextHolder` ở mọi nơi hoặc không cần `ReactiveSecurityContextHolder` nữa.

Test nên dùng **API security reactive** làm nguồn chân lý. Nếu tích hợp thư viện ThreadLocal cũ, viết test riêng cho ranh giới đó và khai báo rõ assumptions/tooling.

### 19.4. Mất context do nhánh không được compose

Ví dụ:

```java
Mono<String> createPublisher() {
    Mono<String> inner = someOperation()
        .contextWrite(
            ReactiveSecurityContextHolder.withAuthentication(alice));

    return otherOperation(); // inner không được return/subscribed.
}
```

Việc có một publisher được khai báo không bảo đảm nó đã chạy. Trong Reactor, composition là điều kiện thiết yếu để giữ lifecycle và context đúng.

---

## 20. Kiểm thử context ở thời điểm subscribe

Một nguyên tắc: **đừng chụp Authentication ở thời điểm xây dựng publisher** nếu nó phải phụ thuộc subscriber.

### 20.1. Sai: snapshot một giá trị global

```java
Authentication auth =
    SecurityContextHolder.getContext().getAuthentication();

Mono<String> response = Mono.just(auth.getName());
```

Vấn đề:
- Có thể `auth=null` trước khi request được subscribe;
- Có thể chụp user sai;
- Không phản ánh user của từng subscription.

### 20.2. Đúng: deferred/reactive lookup

```java
Mono<String> response =
    ReactiveSecurityContextHolder.getContext()
        .map(SecurityContext::getAuthentication)
        .map(Authentication::getName);
```

Context của **người subscribe** quyết định kết quả.

### 20.3. Mono.deferContextual khi cần Reactor Context chung

```java
Mono<String> traceId = Mono.deferContextual(view ->
    Mono.just(view.getOrDefault("traceId", "none")));
```

Cách này dành cho **ứng dụng tự đặt Reactor Context key**. Đối với Spring Security Authentication, ưu tiên **`ReactiveSecurityContextHolder.getContext()`** thay vì mò tìm key nội bộ của Spring Security trong `ContextView`.

### 20.4. Không lưu Authentication trong biến instance

```java
@Service
class BadCurrentUserService {
    private Authentication current; // Sai: shared mutable state trên singleton.

    Mono<String> name() {
        return Mono.just(current.getName());
    }
}
```

Spring services thường là singletons; nếu mỗi request cập nhật field này, người dùng có thể nhìn nhầm danh tính của request khác. Reactor Context giúp tránh thiết kế sai như vậy.

---

## 21. Kiểm thử không rò danh tính giữa nhiều người dùng

Giả sử application có hai request đồng thời:
- Alice: `ROLE_REPORT_READER`;
- Bob: `ROLE_VIEWER`.

Một test hữu ích là **cùng service publisher** được subscribe dưới hai contexts.

```java
Mono<String> currentName = ReactiveSecurityContextHolder.getContext()
    .map(SecurityContext::getAuthentication)
    .map(Authentication::getName);

Authentication alice = new TestingAuthenticationToken(
    "alice", "unused", "ROLE_REPORT_READER");

Authentication bob = new TestingAuthenticationToken(
    "bob", "unused", "ROLE_VIEWER");

Mono<String> aliceCall = currentName
    .delayElement(java.time.Duration.ofMillis(10))
    .contextWrite(
        ReactiveSecurityContextHolder.withAuthentication(alice));

Mono<String> bobCall = currentName
    .delayElement(java.time.Duration.ofMillis(5))
    .contextWrite(
        ReactiveSecurityContextHolder.withAuthentication(bob));

StepVerifier.create(Mono.zip(aliceCall, bobCall))
    .expectNextMatches(tuple ->
        tuple.getT1().equals("alice")
            && tuple.getT2().equals("bob"))
    .verifyComplete();
```

`Mono.zip` tạo subscriptions riêng cho hai sources, mỗi source có contextWrite riêng. Việc delay/threads là phụ, **không phải cơ chế an toàn**. Mục tiêu là kiểm chứng identity isolation.

### 21.1. Không dùng userName từ raw request header

```java
String current = request.getHeaders().getFirst("X-User");
```

Nếu header do client bên ngoài có thể tự gửi, nó không phải identity đã xác minh. Controller/service nên lấy identity từ Authentication được Spring Security thiết lập, không từ header tự khai báo trừ khi có một trusted gateway contract được bảo vệ rõ ràng.

### 21.2. Multi-tenant cần kiểm thử khác role chung

Một user có `ROLE_REPORT_READER` nhưng chỉ thuộc tenant A không tự có quyền đọc report của tenant B.

Khi test, cần giữ `issuer`, `sub`, `tenant_id` và authorities nhất quán và kiểm tra domain authorization policy riêng, không chỉ `hasRole`.

---

## 22. Test anonymous và authenticated: điều dễ sai

### 22.1. Reactor Context vắng Authentication

Nếu `ReactiveSecurityContextHolder.getContext()` là empty, một service trả `Mono.empty()` có thể chỉ dẫn tới HTTP 200 với body rỗng nếu controller không tự enforce authentication.

Để test endpoint **thật sự được bảo vệ**, cần Spring Security `SecurityWebFilterChain`:

```java
http.authorizeExchange(exchanges -> exchanges
    .pathMatchers("/api/**").authenticated()
    .anyExchange().permitAll());
```

Hoặc method security tương ứng. Controller chỉ gọi `getContext()` không tự biến mọi missing Authentication thành HTTP 401.

### 22.2. AnonymousAuthenticationToken trong WebFlux

Tùy filter chain, anonymous request có thể có `AnonymousAuthenticationToken`. Đừng dựa duy nhất vào `auth != null` hay `auth.isAuthenticated()` để kết luận “đã login qua OIDC”.

Dùng `authenticated()` authorization matcher hoặc principal type checks phù hợp.

### 22.3. 401, 403 và 302

- **401**: HTTP API với entry point trả Unauthorized, ví dụ HTTP Basic;
- **403**: User authenticated nhưng thiếu authority, hoặc CSRF failure;
- **302**: Browser OAuth2 Login entry point có thể redirect tới trang login/OP.

Một test `WebTestClient.expectStatus().isUnauthorized()` chỉ đúng nếu security chain và endpoint được thiết kế trả 401. Đừng dùng expected status của test-only chain để suy ra production browser login behavior.

---

## 23. Kiểm thử Reactor Context trong các publisher trả lỗi

Một pipeline có thể thất bại sau khi đã đọc Authentication. Test phải kiểm tra **error signal**, không chỉ happy path.

### 23.1. Fail nếu thiếu quyền

```java
import org.springframework.security.access.AccessDeniedException;

Mono<String> guarded = ReactiveSecurityContextHolder.getContext()
    .map(SecurityContext::getAuthentication)
    .flatMap(auth -> {
        boolean allowed = auth.getAuthorities().stream()
            .anyMatch(granted ->
                "ROLE_REPORT_READER".equals(granted.getAuthority()));

        return allowed
            ? Mono.just("ok")
            : Mono.error(
                new AccessDeniedException("forbidden"));
    })
    .switchIfEmpty(
        Mono.error(new AccessDeniedException("no authentication")));

Authentication viewer = new TestingAuthenticationToken(
    "viewer", "unused", "ROLE_VIEWER");

StepVerifier.create(guarded.contextWrite(
        ReactiveSecurityContextHolder.withAuthentication(viewer)))
    .expectError(AccessDeniedException.class)
    .verify();
```

### 23.2. Không che lỗi bằng onErrorResume cấp quyền mặc định

Sai:

```java
return securityCheck()
    .onErrorResume(error -> Mono.just("ADMIN"));
```

Nếu `securityCheck()` thất bại vì thiếu Authentication/authorization, `onErrorResume` không được biến lỗi thành một principal/role có quyền cao.

Đúng là xử lý fail closed và trả mã lỗi phù hợp, không mở quyền để “giảm test flakes”.

### 23.3. Kiểm thử cancel

```java
Flux<String> securedStream = Flux.interval(
        java.time.Duration.ofMillis(10))
    .flatMap(i ->
        ReactiveSecurityContextHolder.getContext()
            .map(SecurityContext::getAuthentication)
            .map(Authentication::getName))
    .contextWrite(
        ReactiveSecurityContextHolder.withAuthentication(alice));

StepVerifier.create(securedStream)
    .expectNext("alice")
    .thenCancel()
    .verify();
```

Với source không kết thúc như `Flux.interval`, `thenCancel()` giúp test không chờ completion vô hạn. Đừng quên rằng cancellation cũng ảnh hưởng cleanup của resources, không chỉ SecurityContext.

### 23.4. Đừng block event loop để test

```java
String name = securedStream.blockLast();
```

Đây không phải cách phù hợp cho một `Flux` vô hạn và có thể block event loop nếu dùng sai ngữ cảnh. `StepVerifier` cho phép xác minh signals có giới hạn và explicit termination.

---

## 24. Principal từ Controller Method Argument hay từ ReactiveSecurityContextHolder?

WebFlux controller có thể nhận principal bằng argument:

```java
@GetMapping("/api/me")
Mono<String> me(Principal principal) {
    return Mono.just(principal.getName());
}
```

Hoặc dùng:

```java
@GetMapping("/api/subject")
Mono<String> subject(@AuthenticationPrincipal OidcUser user) {
    return Mono.just(user.getIdToken().getSubject());
}
```

Hoặc đọc trong service bằng:

```java
Mono<String> currentName() {
    return ReactiveSecurityContextHolder.getContext()
        .map(SecurityContext::getAuthentication)
        .map(Authentication::getName);
}
```

**Khi nào dùng cách nào?**

| Vị trí | Cách lấy identity phù hợp |
| --- | --- |
| Controller chỉ cần tên | `Principal` hoặc `Authentication` argument |
| Controller cần ID Token/UserInfo | `@AuthenticationPrincipal OidcUser` |
| Reactive service sâu trong pipeline | **`ReactiveSecurityContextHolder.getContext()`**, hoặc truyền identity có chủ đích |
| Domain service thuần Java | Truyền `userId/tenantId` đã được xác minh như tham số, tránh coupling framework khi phù hợp |
| Outbound WebClient cần OAuth2 token | `ServerOAuth2AuthorizedClientExchangeFilterFunction` / authorized-client infrastructure, không phải raw ID Token |
| Resource Server API | Authentication từ Bearer token, thường `JwtAuthenticationToken` |

Một domain service dùng identity explicit argument dễ unit test hơn. Nhưng nếu service phải kiểm tra quyền ở subscription context, test `ReactiveSecurityContextHolder` là cần thiết.

---

## 25. @RegisteredOAuth2AuthorizedClient trong WebFlux test

Trong OAuth2/OIDC Client, đôi khi controller cần authorized client để gọi downstream API:

```java
@GetMapping("/api/connection")
Mono<String> connection(
    @RegisteredOAuth2AuthorizedClient("reports")
    OAuth2AuthorizedClient authorizedClient) {

    return Mono.just(
        authorizedClient.getClientRegistration().getRegistrationId());
}
```

Reactive test helper:

```java
client.mutateWith(mockOAuth2Client("reports"))
    .get().uri("/api/connection")
    .exchange()
    .expectStatus().isOk()
    .expectBody(String.class).isEqualTo("reports");
```

Cần context có WebFlux OAuth2 Client argument resolver/authorized client infrastructure phù hợp. Trong một `@WebFluxTest` slice cực nhỏ không có resolver này, `mockOAuth2Client` một mình không thể tạo infrastructure bị thiếu.

### 25.1. Authentication và authorized client khác nhau

- **`Authentication`**: user hiện tại đã được xác thực, roles/authorities;
- **`OAuth2AuthorizedClient`**: registration + access token/refresh token phục vụ outbound resource access;
- **`ReactiveClientRegistrationRepository`**: metadata các OAuth2/OIDC clients.

Test `mockOidcLogin()` có thể dựng một authorized client mock tiện lợi, nhưng nếu service đang dùng `client_credentials` độc lập user, hãy dùng helper authorized client tương ứng.

### 25.2. Mock authorized client không thực hiện refresh token

`mockOAuth2Client` không tự:
- Gửi Authorization Code token request;
- Refresh access token;
- Validate OP/JWKS;
- Revoke credential;
- Gọi API thật.

Nếu mục tiêu test refresh failure/`invalid_grant`, cần test `ReactiveOAuth2AuthorizedClientManager`/provider hoặc integration test token endpoint riêng.

---

## 26. Kiểm thử Resource Server khác OIDC Client login

Một WebFlux service có thể đồng thời làm OAuth2 Client và Resource Server. Hai dạng request:

```text
Browser OIDC Login:
  SecurityWebFilterChain -> OAuth2AuthenticationToken(OidcUser)

API Bearer:
  Authorization: Bearer <access-token>
  SecurityWebFilterChain -> JwtAuthenticationToken / BearerTokenAuthentication
```

Trong `WebTestClient`:
- **`mockOidcLogin()`** dùng cho OIDC login session;
- **`mockOAuth2Login()`** dùng cho generic OAuth2 login;
- **`mockJwt()`** dùng cho Resource Server JWT;
- **`mockOpaqueToken()`** dùng cho opaque-token Resource Server.

Nếu controller yêu cầu `OidcUser`, `mockJwt()` không tạo principal đúng loại. Ngược lại, một API service dựa vào `JwtAuthenticationToken` không nên test bằng OIDC session fixture để làm 200.

### 26.1. Token signature validation không được chạy bởi mockJwt()

`mockJwt()` cung cấp một Authentication giả phục vụ kiểm thử authorization/controller. Nó **không chứng minh JWT đã được ký đúng**. Nếu mục tiêu kiểm tra decoder issuer/audience/signature/expiry thì cần test decoder/integration path thật.

Tương tự `mockOidcLogin()` không thực hiện OP authorization, PKCE, nonce hoặc ID Token validation.

---

## 27. Lỗi cấu hình test dễ gặp

| Triệu chứng | Nguyên nhân khả dĩ | Hướng sửa |
| --- | --- | --- |
| `ReactiveSecurityContextHolder.getContext()` rỗng | Context không được đặt vào subscription | `contextWrite(withAuthentication(...))` / test listener |
| Test thấy user qua ThreadLocal nhưng publisher rỗng | Dùng `SecurityContextHolder` thay reactive | Dùng ReactiveSecurityContextHolder và Reactor listener |
| `@WithMockUser` không có hiệu lực trong StepVerifier | ReactorContextTestExecutionListener thiếu hoặc không có Spring Test context | Đăng ký listeners đúng cách |
| `mockOidcLogin()` không compile | Sai static import / thiếu spring-security-test | Dùng reactive SecurityMockServerConfigurers |
| `oidcLogin()` không dùng được với WebTestClient | Đang dùng Servlet helper | Đổi thành `mockOidcLogin()` |
| `userInfoToken()` không có trên reactive helper | Khác API Servlet | Reactive dùng **`userInfo(...)`** |
| `@AuthenticationPrincipal OidcUser` = null | Dùng mockUser hoặc mockJwt sai type | Dùng mockOidcLogin |
| Controller đọc tenant_id = null | Claim đặt sai nguồn hoặc không có | Đặt `idToken(...).claim(...)` |
| Authentication thay user ở request khác | Shared mutable field/SecurityContext | Tạo fixtures theo subscription |
| `@PreAuthorize` không chặn viewer | Chưa bật reactive method security, bean không proxied | `@EnableReactiveMethodSecurity` + Spring bean + negative test |
| Test 401 nhưng nhận 302 | OAuth2 browser login entry point | Assert theo chain thực tế |
| Test 403 khi POST dù có role | CSRF filter từ chối trước method security | Thêm `mutateWith(csrf())` khi test policy sau CSRF |
| WebTestClient mutator không có hiệu lực | Chưa `.apply(springSecurity())` hoặc client kết nối live server | Dùng mock binding/in-memory context đúng |
| `StepVerifier` không thấy emissions | Không subscribe đúng publisher, source không complete | StepVerifier và termination/cancel |
| Thread đổi là context mất | Code rời Reactor hoặc detached subscription | Compose publishers, kiểm tra boundary |
| `publishOn` hoạt động nhưng CompletableFuture mất user | ThreadLocal/Context không tự truyền qua non-Reactor API | Pass identity explicit hoặc bridge an toàn |
| Test pass dù ID Token sai issuer | Mock OIDC bypass cryptographic validation | Integration test OIDC decoder/callback |
| Authority group claim không có ROLE_* | Mock login không tự chạy role mapper | Test mapping riêng hoặc set authorities |
| Test có role nhưng truy cập tenant khác vẫn pass | Chỉ kiểm tra role global | Test domain ACL/tenant guard |
| Một test ảnh hưởng test sau | Reuse shared context hoặc sticky @WithMockUser | Isolate fixtures, listener cleanup, no mutable static |
| Lỗi khi chạy trên port thật | @WithMockUser chỉ ở test context | Gửi HTTP auth thật/mock server binding |
| AuthenticationCredentialsNotFound vs AccessDenied | Khác vị trí exception translation/policy | Xem layer method vs HTTP và assert đúng kiểu |
| WebFlux test đang chạy MVC stack | Có cả web & webflux starters, Boot chọn servlet | Xác nhận reactive application type/config |
| Body trả rỗng thay vì 401 | Service trả Mono.empty, HTTP filter permitAll | Bảo vệ route/method đúng |
| Scheduled job thiếu user context | Không có HTTP subscriber/session | Cấp service identity hoặc explicit auth policy |

### 27.1. Không sửa test bằng cách bỏ security

```java
// Anti-pattern khi mục tiêu là kiểm thử authorization:
http.authorizeExchange(exchanges ->
    exchanges.anyExchange().permitAll());
```

Một test có status 200 không chứng minh Authentication đã được kiểm tra. Đảm bảo security chain/method interceptors đang áp dụng và thêm negative tests.

### 27.2. Không gọi block() để “bắt” identity

```java
// Không nên làm trong request-processing reactive service:
String user = ReactiveSecurityContextHolder.getContext()
    .map(SecurityContext::getAuthentication)
    .map(Authentication::getName)
    .block();
```

Blocking có thể gây lỗi trên non-blocking event loop và phá kiến trúc reactive. Giữ `Mono<String>` trong service và dùng `StepVerifier` ở test boundary.

---

## 28. Tình huống thực hành

### Tình huống A — Context rỗng sau khi gọi service

Test:

```java
StepVerifier.create(identity.currentName())
    .expectNext("alice")
    .verifyComplete();
```

**Vấn đề:** Không có Authentication nào được đưa vào subscription.

**Cách sửa:** Dùng `contextWrite(ReactiveSecurityContextHolder.withAuthentication(alice))` hoặc Spring Test listener phù hợp nếu test dùng `@WithMockUser`.

### Tình huống B — @WithMockUser có hiệu lực ở test thường nhưng reactive service trả empty

**Gợi ý:** Có thể thiếu `ReactorContextTestExecutionListener` hoặc test dùng một publisher không được subscribe trong context đã inject. Kiểm tra test configuration; không chuyển service sang `SecurityContextHolder` ThreadLocal.

### Tình huống C — Controller cần OidcUser

Controller:

```java
Mono<String> subject(@AuthenticationPrincipal OidcUser user)
```

Test dùng `mockUser("alice")`.

**Vấn đề:** principal không phải `OidcUser`. Dùng `mockOidcLogin()` với ID Token claims thích hợp.

### Tình huống D — Thay UserInfo claims

Test viết `mockOidcLogin().userInfoToken(...)`.

**Vấn đề:** Đây là tên method của Servlet `oidcLogin()` trong Spring Security 6.5. Reactive test dùng **`mockOidcLogin().userInfo(...)`**.

### Tình huống E — Có group claim nhưng method vẫn 403

```java
mockOidcLogin().idToken(token ->
    token.claim("groups", List.of("report-readers")))
```

**Giải thích:** Chỉ có claim không bảo đảm có `ROLE_REPORT_READER`. Hoặc dùng `authorities(...)` để test policy, hoặc test mapper production thật.

### Tình huống F — Method security test chỉ có một positive case

Test role admin trả 200 nhưng viewer cũng trả 200.

**Nguyên nhân:** Có thể bean không được proxied hoặc `@EnableReactiveMethodSecurity` chưa bật. Thêm negative test và dùng Spring-managed bean.

### Tình huống G — Flux.flatMap chạy không theo thứ tự

`Flux.range(1,3).flatMap(...)` phát 2,1,3.

**Cách assert:** Nếu thứ tự không phải contract nghiệp vụ, dùng `containsExactlyInAnyOrder`. Reactor Context vẫn có thể đúng dù scheduling khác.

### Tình huống H — Detached subscription mất danh tính

Service tự `subscribe()` một publisher khác rồi return. Test StepVerifier của publisher chính không thấy side effect hoặc context ở publisher con.

**Cách sửa:** Compose publisher bằng `flatMap`/`then`; tránh fire-and-forget trong business request path.

### Tình huống I — Hai HTTP requests bị nhiễm principal

Application có field `static Authentication current`; Alice và Bob cùng gọi endpoint.

**Vấn đề:** Shared mutable Authentication không phải per-subscriber; có nguy cơ thông tin người dùng chéo. Sử dụng ReactiveSecurityContextHolder hoặc truyền user ID được xác minh xuống pipeline.

### Tình huống J — Test WebTestClient qua network thật

Test dùng `@WithMockUser` ở test class nhưng gọi một application server chạy trên port khác.

**Giải thích:** Server khác process/thread không nhìn thấy test context của client. Cần HTTP credentials/real login/test identity provider hoặc in-memory application-context binding.

### Tình huống K — Client và Resource Server cùng trong ứng dụng

Controller cần `JwtAuthenticationToken` nhưng test dùng `mockOidcLogin()`.

**Cách sửa:** Dùng `mockJwt()` để test inbound JWT, không nhầm với OIDC Login principal.

### Tình huống L — OIDC ID Token "hết hạn" nhưng mock test vẫn OK

**Giải thích:** MockOidcLogin đã cung cấp Authentication giả lập, bỏ qua OP/JWT validation. Cần kiểm thử decoder/token/issuer/nonce bằng integration test phù hợp.

### Tình huống M — Anonymous service trả Mono.empty

Client mong 401 nhưng controller `Mono.empty()` và route `permitAll` nên nhận 200 rỗng.

**Cách sửa:** Đặt authorization tại filter/method hoặc chủ động trả lỗi trong service. Missing context không tự thành Unauthorized.

### Tình huống N — Authority scope và role bị nhầm

`hasRole("ADMIN")` yêu cầu `ROLE_ADMIN` (default prefix). Mock user có `SCOPE_admin`.

**Kết quả:** Denied. Kiểm thử bằng đúng authorities và policy; không tự đổi scope thành role.

### Tình huống O — Multi-tenant role leakage

Test có `ROLE_REPORT_READER` và tenant claim A, nhưng API vẫn cho xem tenant B.

**Giải thích:** Role global chưa đủ. Domain tenant guard phải kiểm tra tenant/ownership; test cả user role hợp lệ nhưng tenant sai.

### Tình huống P — Async boundary bằng CompletableFuture

Service đọc `SecurityContextHolder` bên trong `CompletableFuture.supplyAsync()` và thấy null.

**Cách xử lý:** Đừng dựa vào ThreadLocal. Truyền identity đã xác minh vào boundary hoặc dùng context propagation bridge có kiểm thử rõ ràng; giữ phần lớn flow trong Reactor nếu khả thi.

### Tình huống Q — Không có Spring Security filter với WebTestClient

`mutateWith(mockUser())` không tạo được principal trong controller.

**Gợi ý:** Kiểm tra `WebTestClient.bindToApplicationContext(...).apply(springSecurity())` hoặc Boot test security setup; không dùng mutators khi test đang nói chuyện với server thật qua network.

### Tình huống R — Test cần OIDC authorization code/PKCE

**Hỏi:** `mockOidcLogin()` có kiểm tra state, PKCE hoặc nonce của authorization callback không?

> Không. Đây là helper giả lập user đã đăng nhập. Kiểm thử flow thật cần mock OP/token endpoint/JWKS và redirect-callback integration test.

---

## 29. Ma trận kiểm thử đề xuất

| Lớp | Fixture | Kiểm tra |
| --- | --- | --- |
| Reactive service unit | `withAuthentication(alice)` + StepVerifier | Current user trong subscription |
| Reactive service unit | No context / clearContext | Empty/fail closed |
| Reactive service unit | `withSecurityContext(Mono.just(context))` | Context đầy đủ |
| Reactor pipeline | `publishOn` / `flatMap` | Identity không mất trong Reactor |
| Concurrent requests | Two contexts + `Mono.zip` | Không lẫn Alice/Bob |
| Reactive method security | `@WithMockUser` + Spring AOP + StepVerifier | @PreAuthorize allow/deny |
| OIDC method security | `OAuth2AuthenticationToken` + `contextWrite` | Quyền + principal đúng loại |
| WebFlux controller | `WebTestClient.mutateWith(mockUser())` | Generic identity |
| WebFlux controller | `mockOidcLogin().idToken(...)` | OIDC claims |
| WebFlux controller | `mockOidcLogin().userInfo(...)` | UserInfo claims |
| WebFlux controller | `mockOAuth2Login().attributes(...)` | Generic OAuth2 attributes |
| WebFlux controller | `mockAuthentication(custom)` | Custom Authentication |
| WebFlux authorized client | `mockOAuth2Client(...)` | Registration/token metadata mocking |
| Resource Server API | `mockJwt()` | JWT principal/authorization |
| Authorization Code protocol | Mock OP + token endpoint + JWKS | State/PKCE/nonce/token validation |
| External HTTP server | Real test credentials/OP | Toàn bộ network/browser contract |

### 29.1. Có cần test cancellation không?

Có nếu ứng dụng dùng streaming hoặc long-running publishers. `StepVerifier.thenCancel()` giúp không treo test, và bạn nên xác nhận cleanup/cancellation của resource được thực hiện. Nhưng cancellation không phải cách đăng xuất user hay xóa session.

### 29.2. Có cần test StepVerifier.withVirtualTime?

Nếu logic liên quan retry, delay hoặc timeout, `StepVerifier.withVirtualTime(...)` có thể hữu ích. Nhưng nó không thay đổi semantics của SecurityContext. Điều bạn cần kiểm tra vẫn là identity có ở subscription và có được giữ khi thời gian/scheduler thay đổi hay không.

### 29.3. Có cần test mọi ID Token claim?

Không nhất thiết. Tập trung vào claims mà business code sử dụng, kèm negative cases cho missing/type mismatch. Việc valid chữ ký/issuer/audience là một layer integration khác.

---

## 30. Checklist khi debugging “principal null” trong Reactive test

1. Đang chạy **WebFlux** hay Servlet? Kiểm tra loại filter chain thực sự được tạo.
2. Code dùng `ReactiveSecurityContextHolder` hay ThreadLocal `SecurityContextHolder`?
3. Có một subscription thực sự không (StepVerifier/WebTestClient)?
4. `contextWrite` có nằm trên đúng publisher/upstream branch cần đọc context không?
5. `Authentication` được tạo có đúng principal type và authorities?
6. Với Spring Test `@WithMockUser`, listeners hỗ trợ Reactive context đã được đăng ký?
7. Test `@PreAuthorize` có dùng Spring-managed proxy và `@EnableReactiveMethodSecurity` không?
8. Với WebTestClient tự dựng, có `.apply(springSecurity())` không?
9. `mockOidcLogin()`/`mockOAuth2Login()` đã được dùng đúng stack chưa?
10. `@AuthenticationPrincipal` yêu cầu OIDC nhưng fixture đang là `mockUser` hoặc `mockJwt`?
11. Pipeline có `subscribe()` tách rời hoặc chuyển sang non-Reactor async API không?
12. Có dùng static/global mutable Authentication khiến requests chồng nhau?
13. Context vắng thì service trả empty hay error theo thiết kế?
14. HTTP status test có phù hợp entry point Basic/OAuth2 Login không?
15. Test claims và authorities có đúng source/mapping không?
16. Có cần test ID Token signature hoặc authorization code thật thay vì mock login không?
17. Nếu test song song, fixtures/SecurityContext có được tạo mới cho mỗi subscription?
18. Nếu có nhiều providers, `registrationId`, `iss`, `sub` và tenant/roles có nhất quán không?

---

## 31. Sơ đồ quyết định cuối cùng

```text
Muốn kiểm thử principal / security context trong Reactor
                |
                v
Đang test lớp nào?
                |
                +-- Reactive service / Mono / Flux
                |       |
                |       +-- Tạo Authentication / SecurityContext
                |       +-- contextWrite(withAuthentication(...))
                |       +-- StepVerifier:
                |             expectNext / expectError / verifyComplete
                |       +-- Test empty context, concurrency, scheduler
                |
                +-- Spring @PreAuthorize method security
                |       |
                |       +-- @EnableReactiveMethodSecurity
                |       +-- Spring-managed proxy
                |       +-- @WithMockUser + ReactorContextTestExecutionListener
                |       |      hoặc contextWrite(custom Authentication)
                |       +-- Positive + negative StepVerifier tests
                |
                +-- WebFlux HTTP controller
                |       |
                |       +-- WebTestClient + springSecurity()
                |       +-- mockUser()                   [generic user]
                |       +-- mockAuthentication(custom)  [custom auth]
                |       +-- mockOAuth2Login()           [OAuth2User]
                |       +-- mockOidcLogin()             [OidcUser]
                |       +-- mockJwt()                   [Bearer JWT]
                |       +-- Assert status + response + authorization
                |
                +-- OIDC authorization protocol thật
                        |
                        +-- Mock/test OP + token endpoint + JWKS
                        +-- Redirect/state/PKCE/nonce/issuer validation
                        +-- KHÔNG chỉ dùng mockOidcLogin()

Khi context thiếu:
    -> Không bỏ method-security checks
    -> Không tạo Authentication từ input không tin cậy
    -> Không dùng ThreadLocal global để chữa
    -> Chọn đúng subscription/test infrastructure
```

### Những điểm cốt lõi

1. **ReactiveSecurityContextHolder đọc context từ Reactor subscription**, không dựa trên ThreadLocal request cố định.
2. **`contextWrite(withAuthentication(...))` + StepVerifier** là cách đơn giản nhất để unit test một Mono/Flux phụ thuộc current user.
3. **`withSecurityContext(Mono.just(...))`** cho phép inject SecurityContext đầy đủ; `clearContext()@@ giúp test ngữ cảnh rỗng.
4. **`@WithMockUser` trên reactive method security cần Spring Test + ReactorContextTestExecutionListener** và bean được AOP proxy.
5. **WebTestClient với `springSecurity()` và `mutateWith(...)`** là đường kiểm thử HTTP WebFlux; không dùng MockMvc RequestPostProcessors.
6. **`mockOidcLogin()` tạo OidcUser**, còn `mockOAuth2Login()` tạo OAuth2User, `mockJwt()` dành cho Resource Server.
7. **Reactive helper sử dụng `mockOidcLogin().userInfo(...)`**, khác Servlet `oidcLogin().userInfoToken(...)`.
8. **Authorities và claims không tự đồng nghĩa**: role mapping là logic riêng phải được test.
9. **Reactor Context tồn tại qua các operators được compose đúng**, nhưng detached subscriptions/non-Reactor async boundaries cần xử lý riêng.
10. **Mock authentication không chứng minh OP/JWT validation thật**, và không được dùng dữ liệu/tokens production trong test fixtures.

### Tài liệu tham khảo chính thức

- [Spring Security 6.5 — Reactive Testing OAuth2, OIDC Login, JWT](https://docs.spring.io/spring-security/reference/6.5/reactive/test/web/oauth2.html)
- [Spring Security 6.5 — Reactive WebTestClient Security Setup](https://docs.spring.io/spring-security/reference/6.5/reactive/test/web/setup.html)
- [Spring Security 6.5 — Reactive Testing Authentication](https://docs.spring.io/spring-security/reference/6.5/reactive/test/web/authentication.html)
- [Spring Security 6.5 — Reactive Testing Method Security](https://docs.spring.io/spring-security/reference/6.5/reactive/test/method.html)
- [Spring Security 6.5 — Reactive Method Security](https://docs.spring.io/spring-security/reference/6.5/reactive/authorization/method.html)
- [Spring Security — ReactiveSecurityContextHolder API](https://docs.spring.io/spring-security/site/docs/6.5.x/api/org/springframework/security/core/context/ReactiveSecurityContextHolder.html)
- [Spring Security — ReactorContextTestExecutionListener API](https://docs.spring.io/spring-security/site/docs/6.5.x/api/org/springframework/security/test/context/support/ReactorContextTestExecutionListener.html)
- [Spring Security — Reactive OAuth2 Login](https://docs.spring.io/spring-security/reference/6.5/reactive/oauth2/login/index.html)
- [Project Reactor — Context: Adding a Context to a Reactive Sequence](https://projectreactor.io/docs/core/release/reference/advancedFeatures/context.html)
- [Project Reactor — Testing](https://projectreactor.io/docs/core/release/reference/testing.html)
- [OpenID Connect Core 1.0](https://openid.net/specs/openid-connect-core-1_0.html)
