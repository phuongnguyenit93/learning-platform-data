# Phân biệt xác thực thành công, Mono.empty và tín hiệu lỗi trong Spring Security Reactive

> **Chủ đề:** Spring Security - authentication → **Xác thực reactive**. Môi trường minh họa: **Spring Boot 3.x, Spring Security 6.x, Spring WebFlux, Reactor, Java 17+**. Trọng tâm là hợp đồng `ReactiveAuthenticationManager.authenticate(Authentication)`: có **ba kiểu tín hiệu khác nhau** và mỗi kiểu mang ý nghĩa bảo mật riêng. Bài cũng phân biệt tín hiệu của **ServerAuthenticationConverter** với tín hiệu của **ReactiveAuthenticationManager**, giải thích xử lý lỗi trong `AuthenticationWebFilter`, và kiểm tra bằng `StepVerifier` cùng `WebTestClient`.

## 1. ReactiveAuthenticationManager không trả boolean

Trong ứng dụng Servlet truyền thống, `AuthenticationManager.authenticate(...)` thường trả một `Authentication` hoặc ném `AuthenticationException`. Trong WebFlux, interface tương ứng là:

```java
package org.springframework.security.authentication;

import org.springframework.security.core.Authentication;
import reactor.core.publisher.Mono;

@FunctionalInterface
public interface ReactiveAuthenticationManager {
    Mono<Authentication> authenticate(Authentication authentication);
}
```

Đây là **chữ ký rút gọn** để minh họa; mã nguồn interface thực thuộc Spring Security. `Mono<Authentication>` không phải một giá trị authentication có sẵn; nó là một **Publisher** có thể phát **0 hoặc 1 phần tử**, sau đó hoàn tất, hoặc phát **một tín hiệu lỗi**. Reactor không cho phép `null` là phần tử `onNext`.

Theo hợp đồng API chính thức, có **ba kết quả**:

| Kết quả ở cấp ReactiveAuthenticationManager | Tín hiệu Reactive Streams | Ngữ nghĩa xác thực |
| --- | --- | --- |
| `Mono.just(verifiedAuthentication)` | `onNext(Authentication)` → `onComplete` | **Đã xác thực thành công**; token kết quả phải chứa principal/quyền đã được xác minh |
| `Mono.empty()` | `onComplete`, **không có onNext** | Manager **không thể đưa ra quyết định** cho yêu cầu này, ví dụ không hỗ trợ loại token; **không phải** “sai mật khẩu” |
| `Mono.error(new BadCredentialsException(...))` | `onError(AuthenticationException)` | **Đã xử lý nhưng xác thực thất bại**; cần theo đường lỗi/failure handler |

Một vài ví dụ mã rất ngắn:

```java
Mono<Authentication> success =
    Mono.just(UsernamePasswordAuthenticationToken.authenticated(
        verifiedPrincipal, null, verifiedAuthorities));

Mono<Authentication> noDecision = Mono.empty();

Mono<Authentication> badCredentials =
    Mono.error(new BadCredentialsException("Invalid credentials"));
```

Trong đó `verifiedPrincipal` và `verifiedAuthorities` phải được lấy **sau khi** kiểm tra credential và dữ liệu danh tính từ nguồn đáng tin. Ba biến trên là ví dụ biểu diễn tín hiệu, **không** phải ba nhánh có thể dùng tùy ý cho cùng một lỗi.

### Nguyên tắc ghi nhớ

- **Có phần tử**: manager đã đưa ra một kết quả Authentication. Với thành công, nó phải là authentication đã được xác minh, thường `isAuthenticated() == true`.
- **Hoàn tất rỗng**: manager không đưa ra kết quả xác thực; nó từ chối **quyết định**, không khẳng định credential đúng hay sai.
- **Có lỗi**: manager khẳng định có thất bại. Với password sai, dùng `BadCredentialsException` hoặc `AuthenticationException` phù hợp; với hạ tầng không hoạt động, giữ nguyên sự khác biệt giữa lỗi hệ thống và credential sai.

Không viết `return null;` thay `Mono.empty()`, không viết `Mono.just(null)` (Reactor không cho phép phần tử null), không dùng `Mono.just(unauthenticatedToken)` như một cách báo đăng nhập thành công “chưa đầy đủ”.

## 2. Hai lớp Mono.empty rất dễ bị nhầm

Spring Security WebFlux thường có `AuthenticationWebFilter` và `ReactiveAuthenticationManager`, nhưng **hai publisher khác nhau** tham gia luồng xử lý:

1. **`ServerAuthenticationConverter.convert(ServerWebExchange)`** chuyển HTTP request thành `Authentication` **chưa được xác minh**.
2. **`ReactiveAuthenticationManager.authenticate(Authentication)`** nhận token yêu cầu, chứng minh hoặc từ chối danh tính.

Ví dụ HTTP Basic:

```text
GET /private
Authorization: Basic <base64(username:password)>
        |
        v
AuthenticationWebFilter
        |
        +-- requiresAuthenticationMatcher(request)?
        |       false -> đi tiếp chain, không có attempt
        |
        v
ServerAuthenticationConverter
        |
        +-- Mono.empty()
        |       -> KHÔNG có credential chuyển đổi được;
        |          bỏ qua attempt, đi tiếp chain
        |
        '-- Mono<Authentication> (request token)
                |
                v
        ReactiveAuthenticationManager.authenticate(...)
                |
                +-- onNext(authenticated token) -> success handler
                |
                +-- onComplete without value -> không có quyết định;
                |    có thể được manager khác xét khi có delegation
                |
                '-- onError(AuthenticationException)
                     -> failure handler / authentication entry point
```

**Rất quan trọng:** `Mono.empty()` từ **converter** có nghĩa “request này không cung cấp authentication request mà converter nhận diện được”, nên filter không có attempt để gửi cho manager. `Mono.empty()` từ **manager** có nghĩa “manager này không xác định được kết quả cho authentication đã chuyển đổi”. Những chi tiết cuối cùng về filter/manager chain khi manager trả empty phụ thuộc cấu hình và implementation, không thể tự kết luận chắc chắn là HTTP `401`, `403` hay success từ một `Mono.empty()` đơn lẻ.

Ví dụ:

- GET `/private` không có `Authorization`: Basic converter không có token; authorization của endpoint được bảo vệ sẽ yêu cầu authentication, HTTP Basic entry point thường trả `401 Unauthorized`.
- GET `/private` với `Authorization: Basic ...` đúng loại nhưng sai password: manager **phải phát lỗi** `BadCredentialsException`; filter failure handler xử lý, thường trả `401`.
- Manager chỉ hỗ trợ API key nhưng nhận username/password token: manager có thể `Mono.empty()` để manager khác thử xử lý loại token đó.
- Nếu request có token của loại được hỗ trợ nhưng không tìm thấy account: **không** đổi thành empty ở biên xác thực; đây là credential thất bại cần tín hiệu lỗi.

## 3. Cách đọc một chuỗi Reactor

`Mono` có một trong ba hình dạng sau:

```text
SUCCESS:
Subscription
  |-- onNext(Authentication { authenticated=true })
  '-- onComplete

EMPTY:
Subscription
  '-- onComplete

ERROR:
Subscription
  '-- onError(BadCredentialsException)
```

**Empty không phải error.** Do đó:

| Toán tử Reactor | Success | Empty | Error |
| --- | --- | --- | --- |
| `map(mapper)` | Biến đổi Authentication | Bỏ qua mapper, vẫn empty | Lan truyền lỗi |
| `flatMap(mapper)` | Gọi mapper | Bỏ qua mapper, vẫn empty | Lan truyền lỗi |
| `switchIfEmpty(fallback)` | Không dùng fallback | Dùng publisher fallback | **Không bắt lỗi** |
| `onErrorResume(type, fallback)` | Không gọi fallback | Không gọi fallback | Chỉ xử lý lỗi phù hợp |
| `defaultIfEmpty(value)` | Giữ phần tử gốc | Thay empty bằng phần tử được cung cấp | Không bắt lỗi |
| `doOnNext(...)` | Chạy với Authentication | Không chạy | Không chạy |
| `doOnError(...)` | Không chạy | Không chạy | Chạy với Throwable |
| `doOnSuccess(value)` | Gọi với Authentication | Gọi với **null** khi Mono hoàn tất rỗng | Không chạy |
| `doOnTerminate(...)` | Gọi khi terminal | Gọi khi terminal | Gọi khi terminal |
| `doFinally(...)` | Gọi khi kết thúc | Gọi khi kết thúc | Gọi khi kết thúc hoặc cancel |

`doOnSuccess(null)` **không** có nghĩa Mono đã phát phần tử null: đó là tham số callback đặc biệt để nhận biết empty completion. Không ghi `if (value == null) loggedIn = true;` hoặc dùng callback này để “xác nhận Authentication”.

Một quan sát khác: `doOnNext(...)` chỉ chạy khi thực sự có một `Authentication`. Nếu mã “log thành công” được đặt trong `doOnSuccess` mà không kiểm tra value, nó có thể ghi sai thành công cho `Mono.empty()`.

### Các anti-pattern về toán tử

**Sai — biến mọi lỗi password thành “không có quyết định”:**

```java
return verifyCredentials(token)
    .onErrorResume(BadCredentialsException.class, error -> Mono.empty());
```

Nếu dùng nhiều manager, manager khác có thể được gọi thử tiếp; việc chuyển error thành empty làm mất ngữ nghĩa “đã thử và thất bại”. Không dùng nhánh fallback để né fail.

**Sai — biến “không hỗ trợ token” thành lỗi password sai:**

```java
if (!(token instanceof UsernamePasswordAuthenticationToken)) {
    return Mono.error(new BadCredentialsException("wrong password"));
}
```

Provider kiểu username/password không nên khẳng định password sai với token API key/JWT mà nó không có khả năng kiểm tra. Trả `Mono.empty()` trong trường hợp **không hỗ trợ** hợp đồng token.

**Sai — biến authentication chưa được kiểm tra thành kết quả thành công:**

```java
return Mono.just(token); // token từ client vẫn unauthenticated
```

Filter và authorization có thể nhận một object không thể được coi là identity đã được xác minh. Chỉ trả token được xác thực sau kiểm tra credential, account state và authorities từ server.

**Đúng — tách từng trường hợp:**

```java
if (!supports(token)) {
    return Mono.empty(); // Không xử lý loại token này.
}
return verifySupportedToken(token)
    .switchIfEmpty(Mono.error(
        new BadCredentialsException("Invalid credentials")));
```

Mã trên là **mẫu ý tưởng**: `verifySupportedToken` là phương thức do ứng dụng tự xây dựng; ý nghĩa là nếu một kho account reactive trả empty vì **không có người dùng phù hợp**, tại biên manager xử lý username/password cần chuyển sang lỗi authentication, chứ không cho empty thoát ra như thể provider chưa quyết định.

## 4. Ví dụ Java 17+ độc lập trong ứng dụng Spring WebFlux

Ví dụ dùng HTTP Basic cho API **chỉ có GET** để dễ quan sát tín hiệu. Một manager custom chấp nhận `UsernamePasswordAuthenticationToken`, xác minh username/password demo và phát kết quả trong `Mono`. Nó không tạo session; mỗi request cần gửi Basic credentials lại. Với production, ưu tiên TLS, cơ chế credential và rate limiting phù hợp; Basic không phải mặc định an toàn cho mọi API hoặc browser.

### 4.1. Dependencies Gradle

Trong project Spring Boot 3.x đã có Gradle plugin, Java 17, khai báo:

```groovy
// build.gradle - phần dependencies
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
    implementation 'org.springframework.boot:spring-boot-starter-security'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
    testImplementation 'io.projectreactor:reactor-test'
}
```

Không thêm `spring-boot-starter-web` (Servlet MVC) vào demo: ứng dụng cần reactive server thực sự. Với ứng dụng vừa có WebFlux vừa có MVC starter, Spring Boot thường ưu tiên loại ứng dụng Servlet, dễ làm lệch bài test.

### 4.2. Main application

**`src/main/java/example/reactivesignals/ReactiveSignalsApplication.java`**

```java
package example.reactivesignals;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ReactiveSignalsApplication {
    public static void main(String[] args) {
        SpringApplication.run(ReactiveSignalsApplication.class, args);
    }
}
```

### 4.3. Principal đã được xác minh

**`src/main/java/example/reactivesignals/VerifiedPrincipal.java`**

```java
package example.reactivesignals;

import java.security.Principal;

public record VerifiedPrincipal(
        String accountId,
        String username) implements Principal {

    @Override
    public String getName() {
        return username;
    }
}
```

`VerifiedPrincipal` không chứa plaintext password hoặc password hash, giảm rò rỉ khi principal được đọc từ `ReactiveSecurityContextHolder` hoặc ghi audit. Tên và ID lấy từ bản ghi server sau khi credential đã được kiểm tra. Trong sản phẩm thật, account có thể có nhiều trạng thái và quyền; provider phải xác minh các điều kiện tương ứng trước khi cấp authentication.

### 4.4. ReactiveAuthenticationManager trả đúng ba loại tín hiệu

**`src/main/java/example/reactivesignals/DemoReactiveAuthenticationManager.java`**

```java
package example.reactivesignals;

import java.util.List;

import org.springframework.security.authentication.BadCredentialsException;
import org.springframework.security.authentication.ReactiveAuthenticationManager;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.crypto.password.PasswordEncoder;

import reactor.core.publisher.Mono;
import reactor.core.scheduler.Schedulers;

public final class DemoReactiveAuthenticationManager
        implements ReactiveAuthenticationManager {

    private final PasswordEncoder encoder;
    private final String storedPasswordHash;

    public DemoReactiveAuthenticationManager(PasswordEncoder encoder) {
        this.encoder = encoder;
        this.storedPasswordHash = encoder.encode("study-pass");
    }

    @Override
    public Mono<Authentication> authenticate(Authentication request) {

        // 1. Provider chỉ quyết định username/password.
        //    Token khác -> không quyết định, KHÔNG phải sai password.
        if (!(request instanceof UsernamePasswordAuthenticationToken)) {
            return Mono.empty();
        }

        // 2. Username/password trong request chưa đáng tin cậy.
        String username = request.getName();
        Object suppliedCredential = request.getCredentials();

        if (!(suppliedCredential instanceof String password)
                || password.isBlank()
                || username == null || username.isBlank()) {
            return Mono.error(
                new BadCredentialsException("Invalid credentials"));
        }

        // 3. fromCallable() chỉ chạy khi subscriber thực sự subscribe.
        //    BCrypt là tác vụ CPU tốn thời gian; không chạy trên event loop.
        return Mono.<Authentication>fromCallable(() -> {
                boolean passwordMatches =
                    encoder.matches(password, storedPasswordHash);

                // Dùng cùng thông báo cho username sai/password sai.
                if (!"alice".equals(username) || !passwordMatches) {
                    throw new BadCredentialsException("Invalid credentials");
                }

                // 4. Principal và authority đến từ dữ liệu server.
                VerifiedPrincipal principal =
                    new VerifiedPrincipal("acct-101", "alice");

                // Factory authenticated(...) chỉ gọi SAU khi xác minh.
                return UsernamePasswordAuthenticationToken.authenticated(
                    principal,
                    null,
                    List.of(new SimpleGrantedAuthority("ROLE_USER")));
            })
            .subscribeOn(Schedulers.boundedElastic());
    }
}
```

**Phân tích chi tiết:**

1. `Mono.empty()` xảy ra **chỉ khi** request token không thuộc kiểu manager có trách nhiệm kiểm tra. Đây là điểm phân biệt “không hỗ trợ/không quyết định” và “credential xấu”.
2. Request thuộc `UsernamePasswordAuthenticationToken` nhưng username/password thiếu hoặc rỗng là **thất bại**. `Mono.error(BadCredentialsException)` là cách biểu đạt đúng; không trả `Mono.empty()`.
3. `Mono.fromCallable(...)` tạo một publisher **cold/lazy**. Hàm kiểm tra mật khẩu chỉ chạy khi có subscription; exception được Reactor chuyển thành `onError`. Không bắt `BadCredentialsException` rồi trả default principal.
4. `BCryptPasswordEncoder.matches(raw, hash)` xác minh mật khẩu; không so sánh plaintext bằng `equals` hoặc tính lại hash rồi so sánh (BCrypt dùng salt). Ví dụ vẫn thực hiện phép kiểm tra hash cho username không tồn tại để giảm khác biệt nhánh kiểm tra, nhưng production cần xử lý account enumeration, rate limiting và bảo mật timing toàn diện.
5. `Schedulers.boundedElastic()` chuyển công việc kiểm tra hash tốn thời gian ra khỏi Netty event loop. Nó **không làm thuật toán BCrypt trở thành I/O phi chặn**. Với database blocking/JDBC cần adapter/scheduler thích hợp hoặc dùng nguồn dữ liệu reactive (R2DBC); tránh gọi `.block()` trên event loop.
6. Kết quả chỉ có `ROLE_USER` từ server; raw password không còn nằm trong `getCredentials()`. `isAuthenticated()` là true vì factory `authenticated(...)` được gọi sau xác minh. Không copy `request.getAuthorities()`, header hoặc claim do client gửi.
7. Trong ứng dụng production, cần kiểm tra `enabled`, `locked`, password expiry, MFA policy, tenant và authorities từ nguồn có thẩm quyền. Ví dụ bỏ các phần này để tập trung vào **hợp đồng Mono**.

**Một nuance về PasswordEncoder:** `encoder.encode("study-pass")` chạy khi bean manager được khởi tạo để tạo hash demo, không phải mỗi request. Application thực lấy hash đã lưu từ database/repository; nếu hash được lưu/đọc ngoài event loop, thực hiện theo cơ chế reactive phù hợp.

### 4.5. SecurityWebFilterChain cho HTTP Basic stateless

**`src/main/java/example/reactivesignals/SecurityConfig.java`**

```java
package example.reactivesignals;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.web.server.SecurityWebFilterChain;
import org.springframework.security.web.server.context.NoOpServerSecurityContextRepository;

@Configuration
@EnableWebFluxSecurity
public class SecurityConfig {

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    DemoReactiveAuthenticationManager demoAuthenticationManager(
            PasswordEncoder encoder) {
        return new DemoReactiveAuthenticationManager(encoder);
    }

    @Bean
    SecurityWebFilterChain springSecurityFilterChain(
            ServerHttpSecurity http,
            DemoReactiveAuthenticationManager manager) {

        NoOpServerSecurityContextRepository noOp =
            NoOpServerSecurityContextRepository.getInstance();

        http
            .securityContextRepository(noOp)
            .authorizeExchange(exchanges -> exchanges
                .pathMatchers("/public").permitAll()
                .pathMatchers("/private").authenticated()
                .pathMatchers("/admin").hasRole("ADMIN")
                .anyExchange().denyAll())
            .httpBasic(basic -> basic
                .authenticationManager(manager)
                .securityContextRepository(noOp))
            .formLogin(form -> form.disable())
            .logout(logout -> logout.disable());

        // CSRF mặc định của WebFlux vẫn được giữ;
        // demo chỉ công bố GET, không có endpoint thay đổi dữ liệu.
        return http.build();
    }
}
```

Dùng `@EnableWebFluxSecurity` và `SecurityWebFilterChain`, **không** dùng `@EnableWebSecurity` hoặc Servlet `HttpSecurity`. `NoOpServerSecurityContextRepository` khiến HTTP Basic không lưu authentication sang request kế tiếp. Điều này giúp kiểm thử rằng **mỗi request riêng lẻ** phải cung cấp Basic credentials hợp lệ; không có session nào âm thầm biến request không credential thành authenticated.

Dù `HttpBasicSpec` có auth manager riêng, code cũng truyền `noOp` cho filter Basic và chain để hành vi đọc/lưu security context nhất quán. Khi chuyển sang form login stateful, `WebSessionServerSecurityContextRepository` và login success flow có hành vi khác; không áp dụng stateless config của bài này cho hệ thống có browser session mà chưa đánh giá CSRF.

`/admin` chỉ kiểm tra thêm authorization: khi `alice` đăng nhập Basic thành công, cô ấy là user hợp lệ nhưng **không có ROLE_ADMIN**, nên request bị từ chối với `403`. Đây là **authorization failure**, không phải manager phát `Mono.error(BadCredentialsException)`. Phân biệt hai giai đoạn là điều thiết yếu.

### 4.6. Controller ReactiveSecurityContextHolder

**`src/main/java/example/reactivesignals/SignalController.java`**

```java
package example.reactivesignals;

import org.springframework.security.core.context.ReactiveSecurityContextHolder;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

import reactor.core.publisher.Mono;

@RestController
public class SignalController {

    @GetMapping("/public")
    public Mono<String> publicPage() {
        return Mono.just("public");
    }

    @GetMapping("/private")
    public Mono<String> privatePage() {
        return ReactiveSecurityContextHolder.getContext()
            .map(context -> "hello:"
                + context.getAuthentication().getName());
    }

    @GetMapping("/admin")
    public Mono<String> adminPage() {
        return Mono.just("admin");
    }
}
```

Trong WebFlux, `SecurityContext` gắn với **Reactor Context**, không nên đọc `SecurityContextHolder` kiểu ThreadLocal rồi tin rằng nó luôn giữ được identity sau khi pipeline đổi scheduler. `ReactiveSecurityContextHolder.getContext()` là API phù hợp trong reactor chain.

Nếu còn authentication thành công cho `alice`, GET `/private` trả body:

```text
hello:alice
```

Đây là body được **thiết kế** của endpoint; không phải output đã thực thi. Trong API lớn, nên kiểm tra quyền tài nguyên, object ownership và audit bên cạnh quyền đơn giản theo URL.

## 5. Unit tests: quan sát đúng tín hiệu bằng StepVerifier

`StepVerifier` cho phép khẳng định publisher đã phát một `Authentication`, hoàn tất rỗng hay dừng bằng `onError`. Nó rõ ràng hơn việc gọi `.block()`, đặc biệt trong code reactive không muốn block event loop.

**`src/test/java/example/reactivesignals/ReactiveManagerSignalsTest.java`**

```java
package example.reactivesignals;

import java.util.List;
import java.util.Set;
import java.util.stream.Collectors;

import org.junit.jupiter.api.Test;
import org.springframework.security.authentication.AnonymousAuthenticationToken;
import org.springframework.security.authentication.BadCredentialsException;
import org.springframework.security.authentication.DelegatingReactiveAuthenticationManager;
import org.springframework.security.authentication.ReactiveAuthenticationManager;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;

import static org.junit.jupiter.api.Assertions.*;

class ReactiveManagerSignalsTest {

    private final DemoReactiveAuthenticationManager manager =
        new DemoReactiveAuthenticationManager(new BCryptPasswordEncoder());

    private static Authentication request(String username, String password) {
        return UsernamePasswordAuthenticationToken.unauthenticated(
            username, password);
    }

    @Test
    void successEmitsOneVerifiedAuthenticationThenCompletes() {
        StepVerifier.create(manager.authenticate(
                request("alice", "study-pass")))
            .assertNext(result -> {
                assertTrue(result.isAuthenticated());
                assertInstanceOf(VerifiedPrincipal.class,
                    result.getPrincipal());

                VerifiedPrincipal principal =
                    (VerifiedPrincipal) result.getPrincipal();
                assertEquals("acct-101", principal.accountId());
                assertEquals("alice", principal.username());
                assertEquals("alice", result.getName());
                assertNull(result.getCredentials());

                Set<String> roles = result.getAuthorities().stream()
                    .map(GrantedAuthority::getAuthority)
                    .collect(Collectors.toSet());
                assertEquals(Set.of("ROLE_USER"), roles);
            })
            .verifyComplete();
    }

    @Test
    void unsupportedTokenCompletesEmptyWithoutOnNext() {
        Authentication otherMechanism = new AnonymousAuthenticationToken(
            "demo-key", "guest",
            List.of(new SimpleGrantedAuthority("ROLE_ANONYMOUS")));

        StepVerifier.create(manager.authenticate(otherMechanism))
            .verifyComplete(); // Không onNext, không onError.
    }

    @Test
    void wrongPasswordProducesAuthenticationError() {
        StepVerifier.create(manager.authenticate(
                request("alice", "wrong")))
            .expectError(BadCredentialsException.class)
            .verify();
    }

    @Test
    void unknownUserAlsoProducesAuthenticationError() {
        StepVerifier.create(manager.authenticate(
                request("not-alice", "study-pass")))
            .expectError(BadCredentialsException.class)
            .verify();
    }

    @Test
    void missingCredentialIsAnErrorNotEmpty() {
        StepVerifier.create(manager.authenticate(
                UsernamePasswordAuthenticationToken.unauthenticated(
                    "alice", null)))
            .expectError(BadCredentialsException.class)
            .verify();
    }

    @Test
    void emptyCanDelegateToAnotherManager() {
        ReactiveAuthenticationManager abstain = ignored -> Mono.empty();
        DelegatingReactiveAuthenticationManager chain =
            new DelegatingReactiveAuthenticationManager(abstain, manager);

        StepVerifier.create(chain.authenticate(
                request("alice", "study-pass")))
            .assertNext(result -> {
                assertTrue(result.isAuthenticated());
                assertEquals("alice", result.getName());
            })
            .verifyComplete();
    }

    @Test
    void aFailureIsNotSilentlyTurnedIntoSuccess() {
        ReactiveAuthenticationManager reject = ignored ->
            Mono.error(new BadCredentialsException("Invalid credentials"));

        StepVerifier.create(reject.authenticate(
                request("alice", "study-pass")))
            .expectError(BadCredentialsException.class)
            .verify();
    }
}
```

**Kết quả kỳ vọng:** tổng cộng **7 `@Test`**. Các phép thử có ý nghĩa:

- `assertNext(...).verifyComplete()` bảo đảm **đúng một Authentication**, sau đó hoàn tất bình thường. Đồng thời kiểm tra principal và authorities từ server.
- `verifyComplete()` ngay sau subscribe xác nhận **không có phần tử nào** và không có lỗi; đó là `Mono.empty()`.
- `expectError(BadCredentialsException.class)` bảo đảm **không có thành công và không empty**, mà có tín hiệu `onError` đúng loại.
- `DelegatingReactiveAuthenticationManager` minh họa một manager không xử lý loại yêu cầu có thể nhường cho manager khác. Theo mặc định, lỗi từ delegate không tự được coi như empty; cấu hình `continueOnError` (nếu sử dụng) cần được đánh giá riêng rất chặt.
- Unit test gọi manager trực tiếp; nó **không** tự kiểm tra phản hồi HTTP. Phần tiếp theo kiểm tra filter và authorization thật.

## 6. WebTestClient: quan sát 200, 401, 403 trong HTTP

Ở tầng HTTP, **không có ánh xạ một-một** từ mọi Reactor signal sang một status cố định; nó phụ thuộc filter, entry point, failure handler và authorization. Trong cấu hình HTTP Basic của ví dụ, có thể đưa ra các kiểm thử cụ thể:

**`src/test/java/example/reactivesignals/ReactiveHttpSignalsTest.java`**

```java
package example.reactivesignals;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.reactive.server.WebTestClient;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
@AutoConfigureWebTestClient
class ReactiveHttpSignalsTest {

    @Autowired
    WebTestClient client;

    @Test
    void publicEndpointWorksWithoutCredentials() {
        client.get().uri("/public").exchange()
            .expectStatus().isOk()
            .expectBody(String.class).isEqualTo("public");
    }

    @Test
    void validBasicCredentialsReturn200() {
        client.get().uri("/private")
            .headers(headers -> headers.setBasicAuth("alice", "study-pass"))
            .exchange()
            .expectStatus().isOk()
            .expectBody(String.class).isEqualTo("hello:alice");
    }

    @Test
    void badCredentialsReturn401() {
        client.get().uri("/private")
            .headers(headers -> headers.setBasicAuth("alice", "wrong"))
            .exchange()
            .expectStatus().isUnauthorized();
    }

    @Test
    void absentCredentialsTriggerAuthenticationEntryPoint() {
        client.get().uri("/private")
            .exchange()
            .expectStatus().isUnauthorized();
    }

    @Test
    void validUserWithoutAdminRoleGets403() {
        client.get().uri("/admin")
            .headers(headers -> headers.setBasicAuth("alice", "study-pass"))
            .exchange()
            .expectStatus().isForbidden();
    }

    @Test
    void statelessBasicDoesNotPersistAuthenticationAcrossRequests() {
        client.get().uri("/private")
            .headers(headers -> headers.setBasicAuth("alice", "study-pass"))
            .exchange()
            .expectStatus().isOk();

        // Request mới không gửi credentials: phải bị challenge.
        client.get().uri("/private")
            .exchange()
            .expectStatus().isUnauthorized();
    }
}
```

Có **6 `@Test`** trong test HTTP, tổng cộng **13 test** ở cả hai lớp.

| Request | Điều đang xảy ra | Response kỳ vọng với cấu hình ví dụ |
| --- | --- | --- |
| GET `/public` không Authorization | `permitAll()` | `200` |
| GET `/private`, Basic đúng | Manager phát Authentication đã xác minh | `200` và `hello:alice` |
| GET `/private`, Basic sai | Manager phát `BadCredentialsException` | `401` do Basic failure handler |
| GET `/private`, không header | Converter không tạo auth request; authorization yêu cầu đăng nhập | `401` do Basic entry point |
| GET `/admin`, Basic đúng của alice | Đã xác thực nhưng không có `ROLE_ADMIN` | `403` Forbidden |
| GET `/private`, request thứ hai không Basic | Repo no-op, không lưu auth giữa các request | `401` |

**Không kết luận** rằng “`Mono.empty()` của manager luôn bằng HTTP 401” từ test thiếu header. Trường hợp thiếu header **không gọi manager**, vì converter không có token. Muốn test manager empty ở cấp HTTP, phải dựng một converter tạo đúng loại token được đưa tới manager trả empty và xác định rõ behavior của chain/entry point; điều đó nằm ngoài phạm vi API Basic demo và không nên suy đoán.

### Lệnh chạy

Từ root project đã có Gradle wrapper:

```bash
./gradlew test --tests example.reactivesignals.ReactiveManagerSignalsTest
./gradlew test --tests example.reactivesignals.ReactiveHttpSignalsTest
./gradlew bootRun
```

Trên Windows dùng `gradlew.bat`. Bộ ví dụ được viết theo Spring Security 6.x và Java 17; các kết quả trên là **assertion dự kiến**, không phải báo cáo đã thực thi trong tài liệu. Test HTTP khởi động server nhúng ở cổng ngẫu nhiên, test manager không cần HTTP server.

## 7. Trường hợp có nhiều authentication managers

Một ứng dụng có thể hỗ trợ nhiều loại request: Basic username/password, bearer JWT, API key hoặc client certificate. Các manager **không nhất thiết** phải kiểm tra cùng một loại `Authentication`. Khi thiết kế composite manager, một manager có thể nói “tôi không xử lý loại này” bằng `Mono.empty()` và manager kế tiếp xử lý.

```text
Incoming Authentication
         |
         v
DelegatingReactiveAuthenticationManager
         |
         +-- manager A: username/password?
         |     |- loại đúng: verify
         |     |    |- success -> Authentication
         |     |    '-- failure -> AuthenticationException
         |     '-- loại khác: Mono.empty()
         |
         +-- manager B: API key?
         |     |- loại đúng: verify
         |     '-- loại khác: Mono.empty()
         |
         '-- manager C: JWT?
               |- loại đúng: verify signature, issuer, audience, exp...
               '-- loại khác: Mono.empty()
```

Một số lỗi cần tránh:

1. Nếu manager A **đã** xác định mật khẩu sai nhưng lại trả empty, một manager khác có thể được thử và tình cờ chấp nhận một đường xác thực không mong muốn.
2. Nếu manager A trả error cho **mọi token lạ**, manager xử lý JWT/API key phía sau có thể không được thử, gây từ chối xác thực sai cơ chế.
3. Không bật `setContinueOnError(true)` chỉ để cho hệ thống “đăng nhập dễ hơn”: với các manager khác nhau, xử lý tiếp sau error có thể làm yếu ranh giới bảo mật. Kiểm tra API/version và threat model trước khi thay đổi default.
4. Nếu mọi manager đều trả empty, chưa có chứng cứ xác thực thành công. Filter/entry point phải xử lý tình huống đó theo chính sách; không nên tự tạo default `ROLE_USER` cho request.
5. Phân loại bằng **kiểu token và matcher hợp lệ**, không tin một trường `type=admin` hoặc `role=ADMIN` do client tự khai mà không kiểm tra.
6. Nếu có nhiều `SecurityWebFilterChain`, matcher và thứ tự chain quyết định cơ chế nào được chạy. AuthenticationManager chỉ đưa ra quyết định cho token mà filter của chain chuyển vào. Không dùng một manager fallback rộng vô tình nhận mọi credential.

### Khi kho user reactive trả Mono.empty

Một `ReactiveUserDetailsService.findByUsername("missing")` hoặc repository reactive có thể trả `Mono.empty()` để biểu thị **không có bản ghi**. Nhưng nếu manager đã cam kết xử lý token username/password, việc không tìm được user là **authentication failure**, không phải “manager không hỗ trợ”.

Ví dụ pseudo-code:

```java
Mono<Authentication> findAndVerify(
        String username, String rawPassword) {

    return reactiveDirectory.findByUsername(username)
        .switchIfEmpty(Mono.error(
            new BadCredentialsException("Invalid credentials")))
        .flatMap(account -> verifyPasswordAndBuildAuthentication(
            account, rawPassword));
}
```

`reactiveDirectory` và `verifyPasswordAndBuildAuthentication` ở đoạn này là **API giả định của ứng dụng**, không phải class/thư viện có sẵn. Ý tưởng cần nhớ là **empty của repository** nên được chuyển thành **AuthenticationException** khi username/password request đã được manager nhận xử lý.

Với SQL database reactive, dùng R2DBC/repository reactive để tránh blocking query trên Netty. Nếu dùng JDBC/LDAP blocking, dùng scheduler/offloading thích hợp, có timeout, pool/backpressure; không gọi `.block()` trong request chain. Các lỗi I/O/database downtime không tự biến thành wrong password; không để hệ thống “fail open” bằng một principal mặc định khi nguồn danh tính không truy cập được.

## 8. Chiến lược xử lý lỗi: fail closed và không làm lộ nội bộ

### 8.1. Authentication failure so với backend failure

| Tình huống | Ý nghĩa | Cách biểu đạt |
| --- | --- | --- |
| Password sai | Bằng chứng không hợp lệ | `Mono.error(new BadCredentialsException("Invalid credentials"))` |
| Username không tồn tại (trong provider username/password) | Không chứng minh được danh tính | `Mono.error(BadCredentialsException)`, tránh enumeration |
| Account bị khóa | Trạng thái tài khoản không cho phép | `Mono.error(new LockedException(...))` hoặc exception thích hợp |
| Token không thuộc loại manager hỗ trợ | Manager không quyết định | `Mono.empty()` |
| Credential đúng và account được phép login | Xác thực thành công | `Mono.just(authenticatedToken)` hoặc `Mono.fromCallable(...)` phát token |
| Database/IdP bị lỗi mạng | Không thể xác minh an toàn vì hạ tầng lỗi | `onError`, phân loại riêng; không default sang authenticated |

Thông báo lỗi trả cho client nên đủ dùng nhưng không tiết lộ username có tồn tại hay không, hash, thông tin cấu hình IdP hoặc credential. Server log/audit có thể phân loại lỗi ở mức an toàn, kèm request ID và thời gian, **không ghi raw Authorization header/password/token**.

Ở HTTP Basic/WebFlux, `AuthenticationException` thường được failure handler chuyển thành challenge `401`. Những lỗi khác như lỗi I/O hoặc lập trình có thể đi theo exception handler của server và sinh `5xx`; không hứa một mã response thống nhất nếu chưa cấu hình cụ thể. Điều quan trọng là không đẩy lỗi backend về `Mono.empty()` như thể request không cần xác thực.

### 8.2. Kiểu lỗi ảnh hưởng operator

Với publisher `Mono<Authentication>`, thứ tự toán tử làm thay đổi kết quả:

```java
Mono<Authentication> source = authenticateSupportedRequest(token);

// Nếu source EMPTY, vẫn rỗng và không gọi mapper.
Mono<Authentication> mapped = source.map(auth -> auth);

// Nếu source ERROR, lỗi vẫn được lan truyền.
Mono<Authentication> notEmptyFallback =
    source.switchIfEmpty(Mono.error(
        new BadCredentialsException("No result for supported request")));

// Bắt lỗi chỉ khi chủ ý thiết kế failure policy cụ thể.
Mono<Authentication> explicitFailure = source.onErrorMap(
    UnavailableIdentityStoreException.class,
    ex -> new AuthenticationServiceException(
        "Authentication service unavailable", ex));
```

Ở đoạn này `UnavailableIdentityStoreException` là tên **exception ví dụ của ứng dụng**, không có sẵn trong Spring Security. Các snippet này minh họa Reactor operators, không phải method đầy đủ để copy vào project. Nếu muốn code compile, phải cung cấp class exception đó hoặc thay bằng exception hạ tầng thật.

**Không cần** thêm `onErrorResume(ignored -> Mono.just(adminToken))` để “đảm bảo luôn có login”, vì đó là lỗ hổng authentication nghiêm trọng. Không dùng `onErrorComplete()` trên toàn chuỗi xác thực nếu nó biến password sai hoặc nguồn danh tính lỗi thành empty một cách khó quan sát.

## 9. Kiểm tra Reactor context và lifecycle

### 9.1. Cold Publisher và thời điểm xác minh

`Mono.fromCallable(...)` có công việc **thực sự chạy khi subscribe**. Bởi vậy:

```java
Mono<Authentication> mono = manager.authenticate(
    UsernamePasswordAuthenticationToken.unauthenticated(
        "alice", "study-pass"));

// Tạo Mono chưa đảm bảo đã kiểm tra password.
// StepVerifier / WebFlux filter sẽ subscribe vào chuỗi.
```

Không đặt các side effects nguy hiểm ở thời điểm tạo publisher nếu mục tiêu là chỉ chạy sau khi filter bắt đầu attempt; và không tự subscribe thủ công bên trong manager. **Trả về publisher** để framework quản lý subscribe, backpressure, cancellation và context.

### 9.2. ReactiveSecurityContextHolder thay cho ThreadLocal

Trên WebFlux, filter thành công cần đặt Authentication vào **Reactor Context**, để endpoint phía sau có thể đọc qua `ReactiveSecurityContextHolder`. Vì thread có thể thay đổi sau `publishOn`/`subscribeOn`, đừng dùng `SecurityContextHolder.getContext()` ThreadLocal như ở Servlet để xác định user trong reactive pipeline.

```java
return ReactiveSecurityContextHolder.getContext()
    .map(security -> security.getAuthentication())
    .map(Authentication::getName);
```

Cách đọc này hữu ích trong controller/service thực sự chạy bên trong reactive chain. Với test trực tiếp manager, không có HTTP filter context để tự động lưu danh tính; test chỉ kiểm tra publisher và object kết quả. Đừng nhầm “manager đã phát Authentication” với “browser có session cookie” hoặc “context được persist cho request sau”.

### 9.3. Cancel không đồng nghĩa login thất bại

Reactive Streams còn có **cancel** do client đóng kết nối, timeout hoặc downstream không còn subscriber. Cancel không phải `Mono.empty()` hoặc `Mono.error()` theo nghĩa publisher đã hoàn tất bình thường; nó là vòng đời subscription bị hủy. Khi làm metrics, dùng `doFinally(signalType)` để phân biệt `ON_COMPLETE`, `ON_ERROR` và `CANCEL`, tránh ghi “login success” chỉ vì chain dừng.

Trong mọi trường hợp, việc một downstream subscriber cancel không được làm manager phát một authentication không được kiểm chứng. Các thao tác lưu context, audit và cấp credential cần gắn với success handler và cơ chế giao dịch/side-effect an toàn.

## 10. Tổng hợp mã sai và cách sửa

| Cách viết sai hoặc thiếu | Vấn đề | Cách làm đúng |
| --- | --- | --- |
| `return null;` từ `ReactiveAuthenticationManager` | Vi phạm hợp đồng publisher | Trả `Mono.empty()`, `Mono.error(...)` hoặc `Mono<Authentication>` |
| `Mono.just(null)` | Reactor không cho phép onNext null | Dùng `Mono.empty()` khi không có kết quả |
| `return Mono.empty()` khi password sai | Bỏ mất tín hiệu thất bại, có thể thử manager khác | `Mono.error(BadCredentialsException)` |
| `return Mono.error(BadCredentialsException)` với token loại khác | Chặn đường xác thực khác dù manager không hỗ trợ | `Mono.empty()` cho loại token ngoài phạm vi |
| `return Mono.just(requestToken)` trước kiểm tra | Hợp thức hóa credential chưa được xác minh | Tạo `authenticated(...)` sau đối chiếu |
| Copy `request.getAuthorities()` | Client có thể mang claim quyền giả | Ánh xạ roles từ nguồn server/issuer đã xác minh |
| `doOnSuccess(auth -> logSuccess())` không xét auth | Empty completion có callback với null | Dùng `doOnNext` hoặc kiểm tra value thực |
| `switchIfEmpty(...)` và nghĩ nó bắt error | Không chặn `onError` | Dùng toán tử lỗi riêng, giữ đúng security semantics |
| `onErrorResume(ex -> Mono.empty())` cho mọi lỗi | Che giấu password sai và outage | Phân loại lỗi, fail closed |
| `block()` trong Netty event loop | Có thể lỗi hoặc làm nghẽn server reactive | Return publisher; dùng nguồn I/O reactive/offload phù hợp |
| Dùng `SecurityContextHolder` ThreadLocal trong WebFlux | Context có thể mất khi scheduler đổi | `ReactiveSecurityContextHolder` |
| Kết luận thiếu Basic header là manager trả empty | Converter thường không tạo token, manager chưa được gọi | Test riêng converter và manager |
| Dùng test HTTP để suy ra mọi empty = 401 | Response phụ thuộc filter/composition/entry point | Test contract StepVerifier và HTTP flow cụ thể |
| Trả authenticated fallback khi IdP/database lỗi | Fail open, nguy cơ chiếm quyền | Báo lỗi và từ chối authentication |
| Log raw password/token/Authorization header | Rò rỉ credential | Redact và log metadata tối thiểu |

## 11. Checklist tự kiểm tra

- [ ] Manager phát `Mono<Authentication>` với principal/quyền đã được xác minh khi thành công.
- [ ] Token thuộc loại khác trách nhiệm trả `Mono.empty()`, không ném “sai mật khẩu” giả.
- [ ] Sai password, username không tồn tại hoặc malformed supported credential trả `Mono.error(AuthenticationException)`.
- [ ] Kho dữ liệu reactive trả empty được chuyển thành authentication failure tại manager xử lý token đó.
- [ ] Lỗi hạ tầng không bị biến thành success/empty; ứng dụng fail closed.
- [ ] Không phát null, không lấy quyền từ request và không dùng token chưa xác thực làm success.
- [ ] Test `StepVerifier` xác minh success (1 onNext), empty (0 onNext), error (onError) riêng biệt.
- [ ] Không nhầm `ServerAuthenticationConverter Mono.empty()` và `ReactiveAuthenticationManager Mono.empty()`.
- [ ] HTTP tests chứng minh 200 khi đúng credential, 401 khi thiếu/sai credential, 403 khi đã xác thực nhưng thiếu role.
- [ ] Các toán tử `switchIfEmpty`, `onErrorResume`, `doOnSuccess` được dùng đúng ngữ nghĩa; không suppress security errors.
- [ ] Không `block()` trong event loop; các phép kiểm BCrypt/blocking I/O được offload hoặc dùng nguồn reactive phù hợp.
- [ ] WebFlux dùng `SecurityWebFilterChain` và `ReactiveSecurityContextHolder`; không copy Servlet filter chain.
- [ ] Test với TLS/timeout/cancellation, observability, rate limit và kiểm soát account enumeration trong ứng dụng thật.

### Tài liệu chính thức

- [Spring Security 6.5 — ReactiveAuthenticationManager API](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/authentication/ReactiveAuthenticationManager.html)
- [Spring Security 6.5 — AuthenticationWebFilter API](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/web/server/authentication/AuthenticationWebFilter.html)
- [Spring Security 6.5 — DelegatingReactiveAuthenticationManager](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/authentication/DelegatingReactiveAuthenticationManager.html)
- [Spring Security 6.5 — ServerHttpSecurity API](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/config/web/server/ServerHttpSecurity.html)
- [Spring Security — WebFlux Security Reference](https://docs.spring.io/spring-security/reference/6.5/reactive/index.html)
- [Spring Security — Reactive Security Context](https://docs.spring.io/spring-security/reference/6.5/reactive/authentication/index.html)
- [Project Reactor — Mono API](https://projectreactor.io/docs/core/release/api/reactor/core/publisher/Mono.html)
- [Project Reactor — Testing with StepVerifier](https://projectreactor.io/docs/core/release/reference/testing.html)
