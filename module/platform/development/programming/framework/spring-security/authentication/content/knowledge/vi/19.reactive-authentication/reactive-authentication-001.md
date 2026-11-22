# ReactiveAuthenticationManager và hợp đồng Mono<Authentication>

## 1. ReactiveAuthenticationManager giải quyết vấn đề gì?

Trong ứng dụng **Spring WebFlux**, Spring Security cần kiểm tra một thông tin xác thực được đưa đến từ HTTP Basic, form, Bearer token hoặc cơ chế riêng. Thay vì giả định kết quả có ngay trên thread đang gọi, Spring Security sử dụng giao diện **ReactiveAuthenticationManager**: nhận một đối tượng `Authentication` và trả về một publisher Reactor kiểu `Mono<Authentication>`.

Định nghĩa cốt lõi:

~~~java
package org.springframework.security.authentication;

import org.springframework.security.core.Authentication;
import reactor.core.publisher.Mono;

@FunctionalInterface
public interface ReactiveAuthenticationManager {
    Mono<Authentication> authenticate(Authentication authentication);
}
~~~

Đây là **chữ ký API rút gọn để giải thích hợp đồng**, không phải file cần chép vào source của ứng dụng. Không tự khai báo lại interface này: Spring Security đã cung cấp.

**Ý nghĩa một câu:** `ReactiveAuthenticationManager` trả về **một kết quả xác thực thành công**, **không có kết luận**, hoặc **một lỗi** thông qua ba dạng tín hiệu Reactor khác nhau. Spring Security WebFlux dựa vào những tín hiệu đó để quyết định cách xử lý request tiếp theo.

Khác biệt so với thiết kế Servlet truyền thống:

| Khía cạnh | Servlet security | WebFlux security |
| --- | --- | --- |
| Hợp đồng manager | `AuthenticationManager.authenticate(Authentication)` | `ReactiveAuthenticationManager.authenticate(Authentication)` |
| Kiểu kết quả | `Authentication` hoặc ném exception | `Mono<Authentication>` |
| Thực thi | Thường xử lý đồng bộ trong luồng servlet request | Publisher được subscribe như một phần pipeline reactive |
| Filter giao thức | Servlet `Filter`, `SecurityFilterChain`, `HttpSecurity` | Reactive `WebFilter`, `SecurityWebFilterChain`, `ServerHttpSecurity` |
| Security context | Thường truy cập `SecurityContextHolder` (thread-bound) | `ReactiveSecurityContextHolder` trong **Reactor Context** |
| Kiểm thử | JUnit + MockMvc | JUnit + StepVerifier + WebTestClient |
| Cần tránh | Lạm dụng logic tùy tiện trong provider | `block()`, `subscribe()` thủ công, chặn Netty event loop, dùng ThreadLocal như nguồn context chính |

Đừng ghép nhầm các API: `HttpSecurity`/`UsernamePasswordAuthenticationFilter` thuộc Servlet; `ServerHttpSecurity`/`AuthenticationWebFilter` thuộc WebFlux. Ngay cả khi một ứng dụng có cả hai thư viện trong classpath, không có nghĩa hai filter stack tự pha trộn.

## 2. Ba kết quả bắt buộc phải phân biệt

Hợp đồng công khai của Spring Security quy định ba trường hợp:

| Reactive signal | Ví dụ | Ý nghĩa đúng | Điều **không** được suy ra |
| --- | --- | --- | --- |
| `onNext(authentication)` rồi `onComplete()` | `Mono.just(authenticated)` | **Đã xác thực thành công**; trả một `Authentication` phù hợp, được xác minh, có principal/authorities đáng tin. | Không chỉ cần trả non-null: token chưa xác thực không được xem là login thành công. |
| Chỉ `onComplete()` | `Mono.empty()` | **Manager không thể xác định** liệu nó có xử lý request này; có thể dành cho manager khác. | Không có nghĩa password sai, tài khoản không tồn tại, hoặc lỗi hệ thống. |
| `onError(exception)` | `Mono.error(new BadCredentialsException(...))` | **Xác thực thất bại hoặc dịch vụ xác thực lỗi**. | Không đồng nghĩa mọi lỗi trả về HTTP 401; HTTP mapping do WebFlux filters/handlers quyết định. |

Ví dụ chỉ để đọc:

~~~java
// A. Thành công: có một Authentication được kiểm tra thực sự.
Mono<Authentication> ok = Mono.just(authenticatedToken);

// B. Không nhận trách nhiệm: không phát Authentication nào.
Mono<Authentication> unsupported = Mono.empty();

// C. Từ chối credential sai: phát tín hiệu lỗi.
Mono<Authentication> invalid = Mono.error(
    new BadCredentialsException("Invalid credentials")
);
~~~

Ba biến trên là **đoạn minh họa**, trong đó `authenticatedToken` giả định đã được tạo an toàn bởi thành phần kiểm chứng. Không được copy `Mono.just(authenticatedToken)` rồi gán một token do client tự khai thành authenticated.

### 2.1. Thành công: một Authentication đáng tin

Publisher của `Mono` phát **tối đa một** đối tượng, rồi hoàn tất. Khi xác thực thành công, `Authentication` thường chứa:

- Principal: user, service account hoặc danh tính đã được xác nhận.
- Authorities: role/scope/permission có nguồn từ server hoặc credential đã xác minh.
- `isAuthenticated() == true` theo hợp đồng implementation hợp lệ.
- Credentials được xóa hoặc không giữ lại khi không cần thiết.

Ví dụ sau là **bước tạo kết quả sau khi credential đã được kiểm tra**, không phải toàn bộ chương trình:

~~~java
Authentication verified =
    UsernamePasswordAuthenticationToken.authenticated(
        userDetails,
        null,
        userDetails.getAuthorities()
    );

return Mono.just(verified);
~~~

Phương thức `authenticated(...)` **không tự kiểm tra password**. Nếu gọi trước khi kiểm tra hoặc lấy authorities từ JSON request của client, đây là lỗi nghiêm trọng: bạn đã nâng một token không đáng tin thành kết quả xác thực.

### 2.2. Empty: “không kết luận”, không phải “đăng nhập ẩn danh”

Manager có thể quản lý một loại token riêng, ví dụ `ApiKeyAuthenticationToken`. Nếu gặp `UsernamePasswordAuthenticationToken`, manager đó không có trách nhiệm kiểm tra. Khi ấy trả `Mono.empty()` cho phép một cơ chế điều phối xét manager khác.

~~~java
@Override
public Mono<Authentication> authenticate(Authentication input) {
    if (!(input instanceof MyApiKeyAuthenticationToken)) {
        return Mono.empty();
    }
    return verifyApiKey((MyApiKeyAuthenticationToken) input);
}
~~~

Đây là **pseudocode Java**; `MyApiKeyAuthenticationToken` và `verifyApiKey` phải được ứng dụng định nghĩa. Ý quan trọng là phân biệt **không hỗ trợ loại token** với **API key thuộc mình nhưng sai**. Trường hợp API key sai phải tạo lỗi xác thực, không trả empty để tìm nguồn yếu hơn.

Không dùng:

~~~java
return Mono.just(null); // SAI: Reactor không cho phép null onNext.
~~~

Trong Reactor, `Mono.just(null)` ném `NullPointerException` khi tạo publisher. `Mono.justOrEmpty(null)` tạo publisher rỗng, nhưng không nên dùng nó như “đường tắt” để che tất cả lỗi hoặc mọi username không tìm thấy.

### 2.3. Error: lỗi nhận diện credential và lỗi hệ thống

Ví dụ:

~~~java
return Mono.error(new BadCredentialsException("Invalid credentials"));
~~~

Đây là cách phản ánh credential không đúng khi manager **chịu trách nhiệm xác thực loại token này**. Với tài khoản bị khóa/vô hiệu:

~~~java
return Mono.error(new LockedException("Account locked"));
// Hoặc DisabledException, AccountExpiredException,
// CredentialsExpiredException khi đúng bản chất.
~~~

Với hệ thống xác thực tạm thời không thể hoạt động:

~~~java
return Mono.error(new AuthenticationServiceException(
    "Authentication backend unavailable", originalCause));
~~~

Ở đoạn cuối, `originalCause` là exception gốc đã được bắt từ ranh giới tích hợp. Đó là **đoạn minh họa**, không phải lời khuyên bắt mọi `Exception` và đổi thành một loại lỗi. Lỗi hạ tầng không có nghĩa user đã nhập mật khẩu sai.

**Ranh giới:** `Mono.error(...)` phát một reactive error signal. Java `throw new BadCredentialsException(...)` bên trong `Mono.defer(...)` cũng được Reactor chuyển thành `onError` khi được subscribe, nhưng dùng `Mono.error` rõ ràng hơn cho kiểm soát luồng và kiểm thử.

## 3. Từ Publisher đến tín hiệu: tại sao không được nghĩ Mono là Authentication?

`Mono<Authentication>` **không phải** một `Authentication` đã có sẵn. Một publisher thường là mô tả quá trình chỉ thực thi khi có subscriber:

~~~text
Tạo publisher: manager.authenticate(request)
          |
          | Chưa nhất thiết truy vấn DB hay hash password
          |
     Publisher Mono<Authentication>
          |
       subscribe()
          |
          +-- onNext(auth) -> onComplete
          |
          +-- onComplete không onNext
          |
          +-- onError(AuthenticationException/...)
~~~

Trong một request WebFlux bình thường, **framework là bên subscribe**. Người viết manager chỉ lắp các operator và trả publisher, không tự `subscribe()`, `block()` hoặc `toFuture().get()` trong filter/manager.

### 3.1. Mono.defer khi cần tạo công việc đúng lúc subscribe

~~~java
@Override
public Mono<Authentication> authenticate(Authentication request) {
    return Mono.defer(() -> {
        if (!supportsRequest(request)) {
            return Mono.empty();
        }
        return verifyReactive(request);
    });
}
~~~

Đây là **mã minh họa**; `supportsRequest` và `verifyReactive` do ứng dụng cài đặt. `Mono.defer` đảm bảo quyết định bên trong lambda diễn ra khi có subscription. Nó hữu ích khi việc xây publisher có side effect, cần per-subscription state hoặc chính sách thời điểm.

Cần nhớ:

- Một `Mono` có thể là cold publisher; **nhiều subscription có thể lặp lại** truy vấn/xác minh và tạo tác dụng phụ. Đừng vô tình subscribe hai lần cùng một login để “lấy log”.
- `Mono.just(...)` phát giá trị đã được tính lúc gọi; dùng `Mono.defer`/`fromCallable` khi muốn tính sau.
- `Mono.empty()` không phát một giá trị `null`; nó **không có `onNext` nào**.
- `Mono.error(...)` không phải return bình thường; nếu không được xử lý, tín hiệu lỗi đi tới các operator và handler phía trên.
- `Flux<Authentication>` không phải kiểu return của contract; xác thực một request phải không phát danh sách nhiều user.

### 3.2. flatMap, map và switchIfEmpty

Một pattern đúng:

~~~java
return reactiveUsers.findByUsername(username)
    .switchIfEmpty(Mono.error(
        new BadCredentialsException("Invalid credentials")))
    .flatMap(user -> verifyPasswordThenCreateAuthentication(user, rawPassword));
~~~

Đây là fragment cần hai dependency/hàm tự cài đặt. Những operator này có nghĩa:

- `findByUsername` là publisher reactive, có thể phát user hoặc empty.
- `switchIfEmpty` **chuyển “không tìm thấy username” thành thất bại xác thực**, vì manager đang chịu trách nhiệm với username/password.
- `flatMap` dùng khi quá trình tiếp theo cũng trả một publisher.
- `map` dùng với phép biến đổi đồng bộ không chặn. Không dùng `map(user -> verifyPasswordBlocking(...))` trực tiếp trên Netty event loop.

Đặt `switchIfEmpty` nhầm chỗ có thể làm provider fallback sai. Ví dụ `.onErrorResume(error -> Mono.empty())` ở cuối pipeline biến **password sai, account locked và hạ tầng lỗi** thành “manager không quyết định”: điều này có thể tạo đường bypass nếu chain manager sau chấp nhận request.

## 4. AuthenticationManager đồng bộ khác ReactiveAuthenticationManager thế nào?

Hai hợp đồng có tên gần nhau:

~~~java
// Servlet / đồng bộ
Authentication authenticate(Authentication request)
        throws AuthenticationException;

// WebFlux / reactive
Mono<Authentication> authenticate(Authentication request);
~~~

Với `ProviderManager` đồng bộ, một provider có thể trả `null` khi không xử lý được; với `ReactiveAuthenticationManager`, tín hiệu tương đương trong hợp đồng là **`Mono.empty()`**, không phải `null` và không phải `Mono.just(null)`.

Một số điểm thực dụng:

| Câu hỏi | Đồng bộ Servlet | Reactive WebFlux |
| --- | --- | --- |
| Đã xác thực? | Trả `Authentication` | `Mono` phát `Authentication` |
| Không thể xác định/không hỗ trợ? | Provider trả `null` theo provider contract | Manager trả `Mono.empty()` |
| Sai credential? | Ném `AuthenticationException` | `Mono.error(AuthenticationException)` |
| Thread context | `SecurityContextHolder` thường dựa ThreadLocal | `ReactiveSecurityContextHolder` qua Reactor Context |
| Gọi kho user | Có thể JDBC đồng bộ | Nên dùng reactive repository/client; tránh chặn event loop |
| Nhiều backend | Thứ tự `AuthenticationProvider` của `ProviderManager` | Điều phối `ReactiveAuthenticationManager` hoặc manager resolver |
| Bộ lọc HTTP | `UsernamePasswordAuthenticationFilter`, `BasicAuthenticationFilter` | `AuthenticationWebFilter` và WebFlux security filters |

Không đơn giản dùng `Mono.just(blockingAuthenticationManager.authenticate(...))`: biểu thức bên trong `Mono.just(...)` **đã được thực thi đồng bộ** trước khi publisher được trả. Nó có thể chặn event loop dù bên ngoài có kiểu `Mono`.

Nếu bắt buộc gọi một legacy synchronous `AuthenticationManager`, Spring Security có `ReactiveAuthenticationManagerAdapter` với cơ chế scheduler; đây là giải pháp cầu nối, không biến dependency chặn thành I/O thực sự non-blocking. Ưu tiên thiết kế reactive từ đầu khi backend cho phép.

## 5. Một request WebFlux đi qua đâu?

Sơ đồ khái quát cho HTTP Basic:

~~~text
HTTP GET /api/me
Authorization: Basic ...
          |
          v
Spring WebFlux + Spring Security WebFilter chain
          |
          v
AuthenticationWebFilter / basic authentication support
          |
          +-- SecurityWebFilterChain phù hợp URL?
          |
          +-- ServerAuthenticationConverter đọc request
          |       |
          |       +-- Mono.empty()
          |       |     Không tìm thấy credential phù hợp;
          |       |     không gọi manager cho lần thử này
          |       |
          |       +-- Authentication request token
          |             |
          |             v
          |    ReactiveAuthenticationManager.authenticate(...)
          |             |
          |             +-- onNext(Authentication): success path
          |             +-- onComplete(empty): no decision
          |             +-- onError(...): failure path
          |
          v
ReactiveSecurityContextHolder / success-failure handling
          |
          v
Authorization WebFilter / ServerAccessDeniedHandler
          |
          v
Handler/controller nếu được phép
~~~

**Đừng nhầm hai loại empty khác nhau:**

- `ServerAuthenticationConverter.convert(exchange)` trả empty nghĩa là **không tạo authentication request token**, ví dụ thiếu header Basic: authentication filter có thể bỏ qua việc xác thực và tiếp tục filter chain.
- `ReactiveAuthenticationManager.authenticate(token)` trả empty nghĩa là **có một token cần xét nhưng manager không kết luận được**. Cách `AuthenticationWebFilter`/bộ điều phối xử lý phụ thuộc implementation và security configuration; **không cam kết** rằng empty từ manager luôn là anonymous, 401, hoặc “thử mọi manager kế tiếp”.

Sau khi có kết quả, `ServerAuthenticationSuccessHandler` hoặc `ServerAuthenticationFailureHandler` xử lý request. Response có thể là 401/403/redirect hoặc status API tùy entry point, authorization rule và exception handling được cấu hình. Manager không trực tiếp viết HTTP response.

### 5.1. Reactor Context chứa danh tính

Trong WebFlux, reactive operators có thể thực thi trên nhiều thread; không lấy `SecurityContextHolder` ThreadLocal thông thường làm nguồn đảm bảo danh tính của request.

~~~java
Mono<String> username = ReactiveSecurityContextHolder.getContext()
    .map(SecurityContext::getAuthentication)
    .map(Authentication::getName);
~~~

Đây là fragment được phép chạy **bên trong pipeline** có Reactive Security Context. Nếu gọi độc lập ngoài request mà không có context, publisher có thể empty. Spring Security đưa context vào Reactor Context cho request được bảo vệ.

Ví dụ test độc lập minh họa:

~~~java
Authentication verified = UsernamePasswordAuthenticationToken.authenticated(
    "student", null, List.of(new SimpleGrantedAuthority("ROLE_USER"))
);

Mono<String> name = ReactiveSecurityContextHolder.getContext()
    .map(SecurityContext::getAuthentication)
    .map(Authentication::getName)
    .contextWrite(ReactiveSecurityContextHolder.withAuthentication(verified));

StepVerifier.create(name)
    .expectNext("student")
    .verifyComplete();
~~~

Đây là **đoạn test minh họa** cần imports Spring Security, Reactor và Reactor Test; `verified` là token test tự tạo, không phải lời khuyên nâng quyền người dùng thật. Reactor Context lan theo subscription, không thay bằng `ThreadLocal`, static biến global hoặc tự tạo `SecurityContextHolder.setContext` trong một task async rồi kỳ vọng nó tự lan sang nơi khác.

## 6. Quy tắc cài đặt manager tùy chỉnh

Trước khi viết code, xác định rõ phạm vi:

1. **Loại Authentication nào được xử lý?** Ví dụ `UsernamePasswordAuthenticationToken` dùng cho HTTP Basic.
2. **Khi loại không hỗ trợ?** Trả `Mono.empty()`.
3. **Khi thuộc phạm vi nhưng username/password sai?** Trả `Mono.error(new BadCredentialsException(...))`.
4. **Khi account locked/disabled?** Trả đúng `AccountStatusException` như `LockedException`/`DisabledException`.
5. **Khi backend lỗi?** Phân loại lỗi xác thực/service; không đổi thành empty hoặc sai password.
6. **Khi thành công?** Trả `Authentication` mới đã xác thực, principal/authorities từ server, không gửi lại raw password.
7. **Có blocking call nào không?** Dùng reactive DB/API nếu có; kiểm tra password hash tiêu tốn CPU phải được bố trí scheduler phù hợp.
8. **Ai subscribe và xử lý HTTP?** Framework/caller, không phải manager tự subscribe.
9. **Nếu nhiều manager?** Thiết kế routing/fallback minh bạch; không coi `onError` là tín hiệu “hãy thử backend yếu hơn”.
10. **Nguồn security context?** Reactor Context, không giữ authentication bằng biến toàn cục hay ThreadLocal qua các operator.

### 6.1. Không để username không tồn tại thành empty

Ví dụ sau **sai về semantics** nếu manager phụ trách username/password:

~~~java
return users.findByUsername(username)
    .flatMap(user -> checkAndAuthenticate(user, password));
// Nếu user không tồn tại, kết quả là Mono.empty() => KHÔNG ĐÚNG
// cho trường hợp credential đã thuộc manager và bị từ chối.
~~~

Code đúng phải xử lý lookup empty thành lỗi:

~~~java
return users.findByUsername(username)
    .switchIfEmpty(Mono.error(
        new BadCredentialsException("Invalid credentials")))
    .flatMap(user -> checkAndAuthenticate(user, password));
~~~

Các đoạn này là fragment; `users`, `username`, `password` và `checkAndAuthenticate` phải có trong class thật. Ngoài client, không nên phân biệt “không tồn tại username” và “password sai” bằng thông điệp chi tiết để tránh user enumeration. Có thể cân nhắc kỹ thuật giảm timing leaks nếu rủi ro phù hợp.

### 6.2. Không chặn event loop bằng I/O đồng bộ

Các anti-pattern:

~~~java
// SAI: thực thi query đồng bộ khi TẠO publisher.
return Mono.just(jdbcRepository.findByUsername(username));

// SAI: đợi kết quả reactive ngay trong request.
UserDetails user = reactiveUsers.findByUsername(username).block();

// SAI: subscribe tách rời pipeline xác thực.
reactiveUsers.findByUsername(username).subscribe(user -> audit(user));
return Mono.empty();
~~~

Giải pháp:

- Ưu tiên `ReactiveUserDetailsService` với backend reactive.
- Nếu bắt buộc tích hợp một API chặn, dùng `Mono.fromCallable(...)` và scheduler phù hợp, rồi **trả publisher**.
- Password hash như BCrypt là tính toán CPU tương đối tốn; không chạy trực tiếp trên Netty event loop. Cân nhắc scheduler riêng hoặc `Schedulers.parallel()` theo tải, đo throughput và giới hạn số tác vụ.
- Không truy xuất secret từ external service bằng lời gọi đồng bộ trên event loop.
- Không dùng `parallel()` vô điều kiện trên mọi công đoạn: scheduling phải dựa vào loại công việc CPU-bound, blocking I/O hay asynchronous I/O.

## 7. Ví dụ Spring Boot 3.x / Java 17+: manager xác thực HTTP Basic

Đây là ứng dụng WebFlux tối thiểu để người học có thể kiểm tra ba tín hiệu. Sử dụng HTTP Basic vì nó dễ tạo `UsernamePasswordAuthenticationToken`; không cần tự viết login JSON hoặc cookie session. Chỉ dùng user demo trong memory, không triển khai mật khẩu hardcode ra production.

Cấu trúc:

~~~text
src/main/java/com/example/reactiveauth/
  ReactiveAuthApplication.java
  LocalReactiveAuthenticationManager.java
  ReactiveSecurityConfig.java
  WhoAmIController.java

src/test/java/com/example/reactiveauth/
  LocalReactiveAuthenticationManagerTest.java
  ReactiveAuthHttpTest.java
~~~

### 7.1. Dependencies

Trong một Spring Boot 3.x Gradle project có plugin và dependency management:

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

Đây là đoạn đưa vào `build.gradle` của một project đã có Spring Boot plugin, repositories và Java 17+. **Không thêm `spring-boot-starter-web`** vào demo vì nó có thể làm app mặc định chuyển sang Servlet MVC và khiến bộ filter WebFlux không khớp. Nếu cần cả hai stack, phải chủ động quyết định application type và security chain, không dựa vào classpath ngẫu nhiên.

### 7.2. ReactiveAuthApplication.java

~~~java
package com.example.reactiveauth;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ReactiveAuthApplication {

    public static void main(String[] args) {
        SpringApplication.run(ReactiveAuthApplication.class, args);
    }
}
~~~

### 7.3. LocalReactiveAuthenticationManager.java

Mã dưới đây cài đặt đủ ba tín hiệu:

- Không xử lý loại token khác → `Mono.empty()`.
- Username/password sai → `Mono.error(BadCredentialsException)`.
- Xác thực đúng → `Mono.just(Authentication)`.

~~~java
package com.example.reactiveauth;

import org.springframework.security.authentication.AccountExpiredException;
import org.springframework.security.authentication.BadCredentialsException;
import org.springframework.security.authentication.CredentialsExpiredException;
import org.springframework.security.authentication.DisabledException;
import org.springframework.security.authentication.LockedException;
import org.springframework.security.authentication.ReactiveAuthenticationManager;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.userdetails.ReactiveUserDetailsService;
import org.springframework.security.crypto.password.PasswordEncoder;

import reactor.core.publisher.Mono;
import reactor.core.scheduler.Schedulers;

public final class LocalReactiveAuthenticationManager
        implements ReactiveAuthenticationManager {

    private final ReactiveUserDetailsService users;
    private final PasswordEncoder passwordEncoder;

    public LocalReactiveAuthenticationManager(
            ReactiveUserDetailsService users,
            PasswordEncoder passwordEncoder) {
        this.users = users;
        this.passwordEncoder = passwordEncoder;
    }

    @Override
    public Mono<Authentication> authenticate(Authentication request) {
        // defer: logic chạy trong lúc framework subscribe.
        return Mono.defer(() -> {
            // Manager này chỉ xử lý username/password.
            if (!(request instanceof UsernamePasswordAuthenticationToken)) {
                return Mono.empty();
            }

            String username = request.getName();
            Object credentials = request.getCredentials();

            if (username == null || username.isBlank()
                    || !(credentials instanceof String rawPassword)
                    || rawPassword.isBlank()) {
                return Mono.error(new BadCredentialsException(
                    "Invalid username or password"));
            }

            // Lookup từ ReactiveUserDetailsService có thể empty.
            return users.findByUsername(username)
                .switchIfEmpty(Mono.error(new BadCredentialsException(
                    "Invalid username or password")))
                .flatMap(user -> {
                    // Phân biệt trạng thái account với mật khẩu sai.
                    if (!user.isEnabled()) {
                        return Mono.error(new DisabledException(
                            "Account disabled"));
                    }
                    if (!user.isAccountNonLocked()) {
                        return Mono.error(new LockedException(
                            "Account locked"));
                    }
                    if (!user.isAccountNonExpired()) {
                        return Mono.error(new AccountExpiredException(
                            "Account expired"));
                    }
                    if (!user.isCredentialsNonExpired()) {
                        return Mono.error(new CredentialsExpiredException(
                            "Credentials expired"));
                    }

                    // BCrypt là tác vụ tính toán CPU; tách khỏi
                    // Netty event loop. Kiểm thử/đo tải scheduler.
                    return Mono.fromCallable(() ->
                            passwordEncoder.matches(
                                rawPassword, user.getPassword()))
                        .subscribeOn(Schedulers.parallel())
                        .flatMap(matches -> {
                            if (!matches) {
                                return Mono.error(new BadCredentialsException(
                                    "Invalid username or password"));
                            }

                            Authentication verified =
                                UsernamePasswordAuthenticationToken.authenticated(
                                    user, null, user.getAuthorities());

                            return Mono.just(verified);
                        });
                });
        });
    }
}
~~~

**Phân tích luồng chính xác:**

1. `Mono.defer(...)` không tự làm I/O blocking thành reactive, nhưng tạo công việc khi subscribe.
2. Kiểm tra class trước: manager không xử lý token khác thì `Mono.empty()`, không ném `ClassCastException`.
3. Credential trống hoặc không thuộc dạng String trong demo được từ chối; trong production, converter/manager phải định nghĩa kiểu credential đúng protocol.
4. `ReactiveUserDetailsService.findByUsername(...)` trả empty nếu user không tồn tại; `switchIfEmpty(Mono.error(...))` bắt buộc làm rõ thất bại credential.
5. Account status được kiểm tra **trước** password để tránh tiếp tục cho tài khoản đã bị khóa/vô hiệu.
6. BCrypt `matches` được chạy trên scheduler dành cho tính toán CPU, không chiếm Netty event loop; cần đo tải/mức độ đồng thời thực tế. Bộ manager chuẩn của Spring Security cũng có cách xử lý scheduling riêng, vì vậy nên ưu tiên dùng implementation chuẩn nếu không cần logic đặc thù.
7. Sau khi kiểm tra thành công, tạo một `Authentication` mới với authorities từ `UserDetails` của server.
8. Credentials trong authenticated result được đặt `null`; không log raw password hoặc trả nó cho client.
9. Lỗi từ `ReactiveUserDetailsService` do outage không được đổi thành `BadCredentialsException`/empty trong code này; application cần cấu hình observability, error mapping và resilience ở ranh giới phụ thuộc.
10. Không có `subscribe()` hay `block()` thủ công: request flow của WebFlux subscribe theo framework.

**Giới hạn demo:** user store trong memory phục vụ học tập. Hệ thống production thường dùng manager/framework chuẩn như `UserDetailsRepositoryReactiveAuthenticationManager`, JWT manager hoặc custom integration riêng; cần account lockout, rate limit, audit, hashing policy, latency budget và tests.

### 7.4. ReactiveSecurityConfig.java

~~~java
package com.example.reactiveauth;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.authentication.ReactiveAuthenticationManager;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.core.userdetails.MapReactiveUserDetailsService;
import org.springframework.security.core.userdetails.ReactiveUserDetailsService;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.web.server.SecurityWebFilterChain;

@Configuration
@EnableWebFluxSecurity
public class ReactiveSecurityConfig {

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    ReactiveUserDetailsService reactiveUsers(PasswordEncoder encoder) {
        return new MapReactiveUserDetailsService(
            User.withUsername("student")
                .password(encoder.encode("demo-pass"))
                .roles("READER")
                .build()
        );
    }

    @Bean
    ReactiveAuthenticationManager authenticationManager(
            ReactiveUserDetailsService users,
            PasswordEncoder encoder) {
        return new LocalReactiveAuthenticationManager(users, encoder);
    }

    @Bean
    SecurityWebFilterChain springSecurityFilterChain(
            ServerHttpSecurity http,
            ReactiveAuthenticationManager manager) {
        return http
            .authorizeExchange(exchange -> exchange
                .pathMatchers("/public").permitAll()
                .pathMatchers("/api/me").hasRole("READER")
                .anyExchange().denyAll()
            )
            .httpBasic(basic -> basic.authenticationManager(manager))
            .formLogin(form -> form.disable())
            .build();
    }
}
~~~

Giải thích:

- `@EnableWebFluxSecurity` và `SecurityWebFilterChain` là mô hình **reactive**; không có `HttpSecurity` hay servlet filter.
- `MapReactiveUserDetailsService` giữ một user demo nhưng implements `ReactiveUserDetailsService`, giúp sử dụng đúng API.
- `ReactiveAuthenticationManager` custom được gắn trực tiếp vào HTTP Basic authentication mechanism qua `httpBasic(...authenticationManager(manager))`.
- `/public` mở, `/api/me` cần `ROLE_READER`, URL khác bị deny.
- Form login được tắt để demo chỉ có HTTP Basic. Request thiếu Basic credentials sẽ không được auto-login bằng session form.
- CSRF mặc định không bị tắt trong ví dụ; các endpoint demo đều là GET. Nếu thêm POST và browser tự gửi credential/cookie, phải đánh giá CSRF riêng, không tắt chỉ vì app dùng WebFlux.

### 7.5. WhoAmIController.java

~~~java
package com.example.reactiveauth;

import java.util.Map;

import org.springframework.security.core.context.ReactiveSecurityContextHolder;
import org.springframework.security.core.context.SecurityContext;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

import reactor.core.publisher.Mono;

@RestController
public class WhoAmIController {

    @GetMapping("/public")
    public Mono<Map<String, String>> publicPage() {
        return Mono.just(Map.of("message", "public"));
    }

    @GetMapping("/api/me")
    public Mono<Map<String, String>> me() {
        return ReactiveSecurityContextHolder.getContext()
            .map(SecurityContext::getAuthentication)
            .map(authentication -> Map.of(
                "username", authentication.getName(),
                "authenticated",
                Boolean.toString(authentication.isAuthenticated())
            ));
    }
}
~~~

Ở đây `ReactiveSecurityContextHolder` lấy danh tính từ Reactor Context của request. Controller không giải Basic header lần thứ hai và không tạo `Authentication` mới. Endpoint đã được `SecurityWebFilterChain` kiểm tra quyền trước khi vào controller.

### 7.6. Chạy và kỳ vọng HTTP

Trong dự án Gradle có wrapper:

~~~bash
./gradlew bootRun
~~~

Trên Windows:

~~~powershell
.\gradlew.bat bootRun
~~~

Thử bằng client local:

~~~bash
# Endpoint public: 200
curl -i http://localhost:8080/public

# Không Authorization: 401/challenge Basic
curl -i http://localhost:8080/api/me

# Credential đúng: 200
curl -i -u student:demo-pass http://localhost:8080/api/me

# Credential sai: 401
curl -i -u student:wrong http://localhost:8080/api/me

# Username không tồn tại: 401
curl -i -u nobody:demo-pass http://localhost:8080/api/me
~~~

Payload JSON thành công mong đợi:

~~~json
{
  "username": "student",
  "authenticated": "true"
}
~~~

Đây là **response dự kiến từ code**, chưa phải stdout/HTTP log đã được chạy thực tế. `curl -u` có thể làm password xuất hiện trong process args hoặc command history. Dùng dummy password ở localhost và HTTPS cho môi trường ngoài. Server Base64 decode HTTP Basic không được coi là mã hóa bảo mật; Basic phải chạy trên TLS.

**Không kết luận** rằng `ReactiveAuthenticationManager` trực tiếp trả HTTP 401: manager phát `Mono.error(BadCredentialsException)`, HTTP Basic filter/failure handler/entry point tạo response.

## 8. JUnit 5 + StepVerifier: test chính xác ba tín hiệu

`StepVerifier` giúp kiểm chứng số lượng `onNext`, loại exception và việc kết thúc publisher. Nó tốt hơn so sánh `Mono.toString()` hoặc gọi `block()` rồi bỏ qua empty/error semantics.

File `src/test/java/com/example/reactiveauth/LocalReactiveAuthenticationManagerTest.java`:

~~~java
package com.example.reactiveauth;

import org.junit.jupiter.api.Test;
import org.springframework.security.authentication.BadCredentialsException;
import org.springframework.security.authentication.DisabledException;
import org.springframework.security.authentication.TestingAuthenticationToken;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.userdetails.MapReactiveUserDetailsService;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.ReactiveUserDetailsService;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;

import reactor.test.StepVerifier;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

class LocalReactiveAuthenticationManagerTest {

    private final PasswordEncoder encoder = new BCryptPasswordEncoder(4);

    private final ReactiveUserDetailsService users =
        new MapReactiveUserDetailsService(
            User.withUsername("student")
                .password(encoder.encode("demo-pass"))
                .roles("READER")
                .build()
        );

    private final LocalReactiveAuthenticationManager manager =
        new LocalReactiveAuthenticationManager(users, encoder);

    private static Authentication input(String name, String password) {
        return UsernamePasswordAuthenticationToken.unauthenticated(
            name, password);
    }

    @Test
    void emitsAuthenticatedValueWhenPasswordIsCorrect() {
        StepVerifier.create(manager.authenticate(
                input("student", "demo-pass")))
            .assertNext(result -> {
                assertTrue(result.isAuthenticated());
                assertEquals("student", result.getName());
                assertTrue(result.getAuthorities().stream()
                    .anyMatch(a -> "ROLE_READER".equals(a.getAuthority())));
            })
            .verifyComplete();
    }

    @Test
    void completesEmptyForUnsupportedAuthenticationClass() {
        Authentication other = new TestingAuthenticationToken(
            "student", "other-credential");

        StepVerifier.create(manager.authenticate(other))
            .verifyComplete(); // Không có onNext.
    }

    @Test
    void rejectsWrongPasswordAsErrorNotEmpty() {
        StepVerifier.create(manager.authenticate(
                input("student", "wrong")))
            .expectError(BadCredentialsException.class)
            .verify();
    }

    @Test
    void rejectsUnknownUsernameAsErrorNotEmpty() {
        StepVerifier.create(manager.authenticate(
                input("nobody", "demo-pass")))
            .expectError(BadCredentialsException.class)
            .verify();
    }

    @Test
    void rejectsBlankCredential() {
        StepVerifier.create(manager.authenticate(
                input("student", "")))
            .expectError(BadCredentialsException.class)
            .verify();
    }

    @Test
    void rejectsDisabledAccountWithoutAcceptingCorrectPassword() {
        ReactiveUserDetailsService disabledUsers =
            new MapReactiveUserDetailsService(
                User.withUsername("disabled")
                    .password(encoder.encode("demo-pass"))
                    .disabled(true)
                    .roles("READER")
                    .build()
            );

        LocalReactiveAuthenticationManager disabledManager =
            new LocalReactiveAuthenticationManager(
                disabledUsers, encoder);

        StepVerifier.create(disabledManager.authenticate(
                input("disabled", "demo-pass")))
            .expectError(DisabledException.class)
            .verify();
    }

    @Test
    void doesNotConvertBackendErrorIntoBadCredentials() {
        ReactiveUserDetailsService failedStore =
            name -> reactor.core.publisher.Mono.error(
                new org.springframework.security.authentication
                    .AuthenticationServiceException(
                        "Credential store unavailable",
                        new IllegalStateException("Simulated outage"))
            );

        LocalReactiveAuthenticationManager failedManager =
            new LocalReactiveAuthenticationManager(
                failedStore, encoder);

        StepVerifier.create(failedManager.authenticate(
                input("student", "demo-pass")))
            .expectError(
                org.springframework.security.authentication
                    .AuthenticationServiceException.class)
            .verify();
    }
}
~~~

**Lưu ý khi đọc test:**

- `verifyComplete()` mà không có `expectNext` kiểm tra publisher **không phát value** và kết thúc bình thường. Nó chỉ dùng với token type unsupported, không dùng cho password sai.
- `assertNext(...)` vừa kiểm tra có đúng một result vừa xem principal/authorities. `verifyComplete()` xác nhận không có value phụ và không có error.
- `expectError(...)` khẳng định lỗi thật được phát ra. Nếu manager vô tình trả `Mono.empty()`, test fail.
- Test account disabled bảo đảm không chỉ “mật khẩu đúng” mới được cấp quyền; trạng thái account vẫn có ý nghĩa.
- Test store lỗi mô phỏng một `AuthenticationServiceException` với cause: manager không biến outage thành user/password sai.
- BCrypt strength 4 chỉ để test nhanh; trong production phải dùng cost phù hợp quy định và cân bằng hiệu suất/bảo mật.
- `TestingAuthenticationToken` được dùng làm loại token không hỗ trợ, không phải credential gửi qua HTTP Basic thật.

**Không gọi `block()` trong handler production để “đơn giản hóa test”.** StepVerifier ở test là đúng công cụ để subscribe và assert tín hiệu.

## 9. Kiểm thử WebFlux từ HTTP bằng WebTestClient

Unit test manager không chứng minh `AuthenticationWebFilter`, entry point, authorization và Reactor Context đã được wiring đúng. Bổ sung integration test dùng `WebTestClient`.

File `src/test/java/com/example/reactiveauth/ReactiveAuthHttpTest.java`:

~~~java
package com.example.reactiveauth;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive
    .AutoConfigureWebTestClient;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.reactive.server.WebTestClient;

@SpringBootTest(
    webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
@AutoConfigureWebTestClient
class ReactiveAuthHttpTest {

    @Autowired
    WebTestClient client;

    @Test
    void publicEndpointDoesNotNeedCredentials() {
        client.get()
            .uri("/public")
            .exchange()
            .expectStatus().isOk()
            .expectBody()
            .jsonPath("$.message").isEqualTo("public");
    }

    @Test
    void basicCredentialsProduceAuthenticatedPrincipal() {
        client.get()
            .uri("/api/me")
            .headers(headers -> headers.setBasicAuth(
                "student", "demo-pass"))
            .exchange()
            .expectStatus().isOk()
            .expectBody()
            .jsonPath("$.username").isEqualTo("student")
            .jsonPath("$.authenticated").isEqualTo("true");
    }

    @Test
    void wrongPasswordGetsUnauthorized() {
        client.get()
            .uri("/api/me")
            .headers(headers -> headers.setBasicAuth(
                "student", "wrong"))
            .exchange()
            .expectStatus().isUnauthorized();
    }

    @Test
    void unknownUsernameGetsUnauthorized() {
        client.get()
            .uri("/api/me")
            .headers(headers -> headers.setBasicAuth(
                "nobody", "demo-pass"))
            .exchange()
            .expectStatus().isUnauthorized();
    }

    @Test
    void missingCredentialsAreNotAutomaticallyAuthenticated() {
        client.get()
            .uri("/api/me")
            .exchange()
            .expectStatus().isUnauthorized();
    }
}
~~~

Chạy:

~~~bash
./gradlew test --tests com.example.reactiveauth.LocalReactiveAuthenticationManagerTest
./gradlew test --tests com.example.reactiveauth.ReactiveAuthHttpTest
~~~

Windows:

~~~powershell
.\gradlew.bat test --tests com.example.reactiveauth.LocalReactiveAuthenticationManagerTest
.\gradlew.bat test --tests com.example.reactiveauth.ReactiveAuthHttpTest
~~~

Đây là **bài kiểm thử dự kiến theo source**; chưa có Gradle run được thực hiện trong bài. Khi dự án compile và tests pass, Gradle thường ghi `BUILD SUCCESSFUL`; các log khác có thể thay đổi theo version.

Vì ví dụ sử dụng HTTP Basic ở WebFlux, khi thiếu hoặc sai credential, cấu hình `AuthenticationEntryPoint` mặc định thường tạo 401 và Basic challenge. Tuy nhiên điều đó **không phải quy tắc của mọi manager**: API JSON/custom filter có thể cần `ServerAuthenticationFailureHandler` để ánh xạ lỗi hệ thống thành 503 hoặc response khác, không lộ stack trace cho client.

## 10. DelegatingReactiveAuthenticationManager: thứ tự và fallback

Khi hệ thống có nhiều loại credential hoặc nhiều nguồn user, Spring Security cung cấp `DelegatingReactiveAuthenticationManager`. Nó nhận nhiều `ReactiveAuthenticationManager` và điều phối.

### 10.1. Luật mặc định

Với hai manager A và B:

~~~text
A.authenticate(token)
     |
     +-- Mono.just(Authentication) → dừng, trả thành công
     |
     +-- Mono.empty() → thử B
     |
     +-- Mono.error(...) → dừng theo mặc định, không thử B

B.authenticate(token)
     |
     +-- Mono.just(Authentication) → thành công
     +-- Mono.empty()              → chưa có kết quả
     +-- Mono.error(...)            → lỗi
~~~

`setContinueOnError(false)` là mặc định. Từ Spring Security 6.3, `setContinueOnError(true)` cho phép manager tiếp tục tìm kết quả ngay cả khi delegate trước phát lỗi. Đây là **quyết định bảo mật**: nếu manager mạnh trả `BadCredentialsException`, một manager khác có thể chấp nhận cùng danh tính qua cơ chế yếu hơn. Đừng bật tùy tiện chỉ để bỏ qua lỗi.

### 10.2. Mã minh họa đúng cơ chế

~~~java
ReactiveAuthenticationManager first =
    request -> Mono.empty();

ReactiveAuthenticationManager second =
    request -> Mono.just(
        UsernamePasswordAuthenticationToken.authenticated(
            "fallback-user",
            null,
            List.of(new SimpleGrantedAuthority("ROLE_USER"))
        )
    );

DelegatingReactiveAuthenticationManager delegates =
    new DelegatingReactiveAuthenticationManager(first, second);
~~~

Đây là **fragment**, trong đó manager `second` cố tình “chấp nhận” để minh họa **thứ tự**. **Không bao giờ dùng manager chấp nhận mà không xác minh credential trong production.**

Test sau minh họa logic:

~~~java
StepVerifier.create(delegates.authenticate(
        UsernamePasswordAuthenticationToken.unauthenticated(
            "anyone", "example")))
    .assertNext(result ->
        assertEquals("fallback-user", result.getName()))
    .verifyComplete();
~~~

Đây là đoạn test cần `delegates` từ fragment trên cùng các imports. Nó cho thấy `Mono.empty()` từ A tạo cơ hội cho B.

### 10.3. Error không mặc định fallback

~~~java
ReactiveAuthenticationManager rejecting = request ->
    Mono.error(new BadCredentialsException("Denied by first manager"));

ReactiveAuthenticationManager fallback = request ->
    Mono.just(UsernamePasswordAuthenticationToken.authenticated(
        "unexpected-user",
        null,
        List.of(new SimpleGrantedAuthority("ROLE_USER"))
    ));

DelegatingReactiveAuthenticationManager guarded =
    new DelegatingReactiveAuthenticationManager(rejecting, fallback);

// Với cấu hình mặc định, BadCredentialsException được phát ra.
StepVerifier.create(guarded.authenticate(
        UsernamePasswordAuthenticationToken.unauthenticated(
            "student", "wrong")))
    .expectError(BadCredentialsException.class)
    .verify();
~~~

Nếu gọi `guarded.setContinueOnError(true)`, cùng phép thử có thể chuyển thành **thành công của fallback**, chính là tình huống cần phân tích nguy cơ bypass. Ví dụ này cố tình đưa ra fallback nguy hiểm nhằm giải thích semantics, không phải cấu hình gợi ý dùng thật.

### 10.4. Nên route theo loại token/endpoint thay vì trộn fallback mơ hồ

Lựa chọn thường dễ kiểm soát:

- `/api/**` dùng JWT/Bearer manager và từ chối token sai.
- `/login/**` dùng username/password manager.
- Cơ chế custom API key dùng token class riêng và manager riêng.
- Chọn `ReactiveAuthenticationManagerResolver<ServerWebExchange>` hoặc chain theo matcher khi cần route theo request, thay vì dùng `onErrorResume` chung cho mọi lỗi.

Nếu một token type được nhiều manager hỗ trợ và đều có quyền trả successful Authentication, phải có **chính sách ownership** rõ ràng để không cho backend yếu hơn mở đường vào tài khoản đã bị từ chối ở backend mạnh.

## 11. Các lỗi anti-pattern thường gặp

### 11.1. Dùng Mono.empty cho sai password

~~~java
if (!passwordMatches) {
    return Mono.empty();  // SAI NGỮ NGHĨA.
}
~~~

Hậu quả: người gọi có thể hiểu “manager không xử lý” và dùng fallback khác. Đúng phải là `Mono.error(new BadCredentialsException(...))`.

### 11.2. Dùng Mono.just(null)

~~~java
return Mono.just(null);  // Reactor không hỗ trợ null onNext.
~~~

`null` không phải một sự kiện thành công rỗng. Trả `Mono.empty()` khi **không thể xác định**, không cho phép `null` che lỗi.

### 11.3. Mono.just với blocking call

~~~java
return Mono.just(legacyAuthManager.authenticate(request));
~~~

Câu lệnh `legacyAuthManager.authenticate(...)` chạy **ngay lúc xây Mono**, có thể chặn Netty event loop. Dùng manager reactive, adapter/scheduler có kiểm soát hoặc `Mono.fromCallable(...).subscribeOn(...)` nếu không thể bỏ API đồng bộ.

### 11.4. Tự block, subscribe hoặc dùng ThreadLocal

~~~java
Authentication a = manager.authenticate(request).block();
manager.authenticate(request).subscribe(this::saveGlobalUser);
SecurityContextHolder.getContext().setAuthentication(a);
~~~

Đây là **anti-pattern** trong request WebFlux. Việc tách subscription hoặc dựa vào ThreadLocal có thể làm mất Reactor Context và gây lỗi phân quyền xuyên request. Trả publisher và để WebFlux xử lý chain.

### 11.5. Bắt mọi lỗi rồi cho qua

~~~java
return backendAuthenticate(input)
    .onErrorResume(error -> Mono.empty());
~~~

Một outage DB, account lock hoặc credential sai sẽ bị đánh đồng “không biết”. Nếu có fallback, request có thể được chấp nhận sai chính sách. Chỉ dùng `onErrorResume` cho những loại exception cụ thể và kết quả đã được security review.

### 11.6. Dùng onErrorReturn một Authentication đã xác thực

~~~java
return verify(input)
    .onErrorReturn(UsernamePasswordAuthenticationToken.authenticated(
        "guest", null, List.of()));
~~~

Sai và nguy hiểm: manager biến **mọi failure** thành Authentication success của một principal mà client chưa thực sự chứng minh. Nếu cần anonymous, để Spring Security WebFlux cung cấp anonymous processing và authorization tương ứng; không giả authentication trong manager.

### 11.7. Đưa raw credentials vào result hoặc log

Không để `getCredentials()` chứa password/plaintext trong object lưu dài hạn, log, JSON response hoặc telemetry. Không log Basic header/JWT/API key. Trả credentials `null` trong kết quả nếu không cần.

### 11.8. Tin rằng isAuthenticated được Spring tự xác minh sau khi code tự set true

`Authentication.isAuthenticated` không phải phép kiểm tra password. Một custom manager phải **tự xác minh đầy đủ** trước khi tạo authenticated result. Không tin user-supplied role/username tự khai mà không kiểm chứng.

### 11.9. Kiểm tra chỉ HTTP 401 mà quên tín hiệu Mono

Cùng HTTP 401 có thể đến từ converter không tạo token, manager ném `BadCredentialsException`, entry point, hoặc access policy. Kiểm thử ở cả **StepVerifier manager** và **WebTestClient HTTP** để biết đường nào thật sự được thực thi.

### 11.10. Dùng ReactiveAuthenticationManager thay cho ReactiveAuthorizationManager

Authentication xác định **ai đang gọi**; authorization quyết định **người đã xác thực có được phép thực hiện hành động**. `ReactiveAuthorizationManager` và `authorizeExchange` thuộc authorization. Đừng thêm rule role trong manager để thay toàn bộ authorization policy: manager có thể tạo authorities đúng, nhưng endpoint vẫn phải kiểm tra.

## 12. Lỗi hệ thống: không để sai password che outage

Ngoài `BadCredentialsException`, cần phân biệt:

| Loại tình huống | Tín hiệu hợp lý | Response HTTP có thể được ứng dụng thiết kế |
| --- | --- | --- |
| Username/password sai | `Mono.error(BadCredentialsException)` | 401, thông điệp chung |
| Username thuộc phạm vi manager nhưng không tìm thấy | Thường `Mono.error(BadCredentialsException)` | 401, không lộ có/tồn tại user |
| Token type không thuộc manager | `Mono.empty()` | Tùy router/manager khác/entry point |
| Tài khoản bị khóa | `Mono.error(LockedException)` | Không tự fallback; status theo policy |
| Tài khoản disabled | `Mono.error(DisabledException)` | Không tự fallback |
| Database credential timeout | `Mono.error(AuthenticationServiceException)` hoặc lỗi hạ tầng đã được phân loại | Có thể 503 nếu có handler tùy chỉnh |
| API remote trả dữ liệu không hợp lệ | Reactive error giữ cause, fail closed | Không cấp role/Authentication |
| Hợp lệ | `Mono.just(Authentication)` | Tiếp tục tới authorization; có thể 200 hoặc 403 |

**Đừng tuyên bố Spring Security mặc định trả 503 cho mọi `AuthenticationServiceException`.** WebFlux filter/error handler quyết định HTTP mapping. Trong môi trường production, log lỗi hạ tầng theo correlation ID (không chứa credential), metrics, tracing đã redaction, timeout và circuit breaker/ratelimiting nếu phù hợp.

Một pattern phân loại ở ranh giới tích hợp (pseudocode):

~~~java
return remoteIdentityService.verify(input)
    .onErrorMap(RemoteIdentityUnavailableException.class,
        ex -> new AuthenticationServiceException(
            "Identity provider unavailable", ex));
~~~

Chỉ map **đúng** sự cố không thể xác minh; không bắt `BadCredentialsException`, `LockedException` hay mọi `RuntimeException` rồi biến thành `Mono.empty()`. Các lớp `remoteIdentityService` và `RemoteIdentityUnavailableException` là tên giả định, chưa thành một chương trình độc lập.

## 13. Kiểm thử laziness, cancellation, timeout và scheduler

Một manager reactive có thể trả publisher đúng kiểu nhưng vẫn khó vận hành nếu operator đặt sai.

### 13.1. Laziness

~~~java
AtomicInteger calls = new AtomicInteger();

ReactiveUserDetailsService spy = username ->
    Mono.defer(() -> {
        calls.incrementAndGet();
        return Mono.just(userDetails);
    });

Mono<Authentication> result =
    new LocalReactiveAuthenticationManager(spy, encoder)
        .authenticate(
            UsernamePasswordAuthenticationToken.unauthenticated(
                "student", "demo-pass")
        );

// Nếu chưa subscribe, calls có thể vẫn là 0
// vì spy thực hiện side effect trong defer.
assertEquals(0, calls.get());

StepVerifier.create(result)
    .expectNextCount(1)
    .verifyComplete();

assertEquals(1, calls.get());
~~~

Đây là **test fragment**, không phải file chạy độc lập: `userDetails` phải có password hash hợp lệ và các imports. Nó chứng minh per-subscription effects, không nói rằng mọi publisher ngoài ứng dụng luôn lazy.

### 13.2. Timeout/cancellation

Khi backend không trả lời, không nên để request chờ vô hạn. Timeout hợp lý có thể được đặt ở reactive client hoặc pipeline, kèm phân loại timeout thành lỗi dịch vụ. Tuy nhiên:

- `timeout(...)` tạo error signal, không được mặc nhiên đổi thành `BadCredentialsException` hoặc empty.
- Cancellation dừng subscription ở mức Reactor, nhưng remote operation có thể cần hỗ trợ cancellation đúng nghĩa.
- Retry bừa bãi password verification hoặc credential POST có thể tạo áp lực, lockout và phát sinh duplicate side effect.
- Không trả authenticated result nếu verification đã timeout hoặc bị cancel.
- Test bằng `StepVerifier.withVirtualTime` cho operator time-based khi code hỗ trợ virtual scheduler; đừng dùng `Thread.sleep` lâu để kiểm tra timeout.

### 13.3. Scheduler đúng tính chất công việc

- Reactive DB/HTTP client thật sự non-blocking: không cần `boundedElastic()` quanh tất cả thao tác.
- Password hashing CPU-intensive: có thể dùng `Schedulers.parallel()` hoặc scheduler riêng đã giới hạn, đo tải.
- Legacy JDBC/blocking call: dùng `Mono.fromCallable(...).subscribeOn(Schedulers.boundedElastic())` tạm thời, nhưng phải giới hạn concurrency và ưu tiên chuyển sang reactive.
- Không dùng `Schedulers.immediate()` cho BCrypt nặng nếu dẫn tới chạy trên event loop.
- Không tạo scheduler mới trên từng request, vì dễ gây thread leak/overhead.

## 14. Kết hợp nhiều nguồn credential an toàn

Một request WebFlux có thể mang session cookie, HTTP Basic, Bearer token hoặc API key. `ReactiveAuthenticationManager` chỉ xử lý **đối tượng Authentication mà filter/converter đưa cho nó**; nó không tự quyết định mọi kiểu credential nào “thắng” request.

Cần lần lượt xác định:

1. `SecurityWebFilterChain` nào khớp URL; chỉ chain được chọn sẽ hoạt động.
2. Authentication filter/converter nào có mặt và có nhìn thấy credential không.
3. `ReactiveAuthenticationManager` hoặc manager resolver nào được dùng.
4. Manager trả onNext/empty/error và fallback được cấu hình ra sao.
5. Sau authentication, authorization policy kiểm tra role/scope nào.
6. Security context được lưu trong Reactor Context hoặc repository nào; request tiếp theo còn cần credential hay không.

Hãy ưu tiên route cơ chế theo endpoint/token type rõ ràng. Khi token sai đã được cung cấp, **không tự fallback** sang cookie hoặc nguồn yếu hơn trừ khi sản phẩm có policy đã chứng minh an toàn. `DelegatingReactiveAuthenticationManager.setContinueOnError(true)` là một công cụ có thể hợp lệ trong những trường hợp đặc thù, nhưng phải test cả “manager A từ chối, manager B chấp nhận” trước khi cho phép triển khai.

## 15. Ma trận QA cho ReactiveAuthenticationManager

| Case | Đầu vào | Tín hiệu cần có | Kiểm tra thêm |
| --- | --- | --- | --- |
| RA-01 | Token type được hỗ trợ, credential đúng | `onNext(Authentication)` + complete | principal, authorities, `isAuthenticated` |
| RA-02 | Token type không hỗ trợ | complete không value | `Mono.empty()`, không có lỗi |
| RA-03 | Password sai | `onError(BadCredentialsException)` | không được chuyển thành empty |
| RA-04 | Username không tồn tại trong nguồn chịu trách nhiệm | `onError(BadCredentialsException)` | không lộ user enumeration |
| RA-05 | Credential null/blank | `onError(BadCredentialsException)` | không `NullPointerException` ngoài ý muốn |
| RA-06 | User disabled | `onError(DisabledException)` | không cấp quyền dù password đúng |
| RA-07 | User locked | `onError(LockedException)` | không fallback |
| RA-08 | User credential expired | `onError(CredentialsExpiredException)` | trạng thái account được bảo vệ |
| RA-09 | Backend unavailable | `onError(AuthenticationServiceException)` hoặc error rõ | giữ cause, không thành BadCredentials |
| RA-10 | Manager đầu empty, manager sau success | onNext từ manager sau | `DelegatingReactiveAuthenticationManager` theo thứ tự |
| RA-11 | Manager đầu error, mặc định delegating | error, không gọi manager sau | chính sách fail closed |
| RA-12 | `continueOnError(true)` | manager sau có thể chạy sau error | kiểm tra nguy cơ bypass |
| RA-13 | Chưa subscribe | không thực thi các side effect deferred | test laziness |
| RA-14 | HTTP Basic đúng | `WebTestClient` nhận 200 + principal | context và role đúng |
| RA-15 | HTTP Basic sai | nhận 401 theo entry point | không lộ stack trace/password |
| RA-16 | Không Basic header | chưa authenticated | converter có thể empty |
| RA-17 | Manager phát onNext nhưng thiếu ROLE | authorization 403 | authentication khác authorization |
| RA-18 | Runtime outage ở user store | không cấp Authentication | observability và status phù hợp |
| RA-19 | Subscription bị cancel/timeout | không phát success giả | timeout/cancel policy |
| RA-20 | Reactive pipeline đổi thread | context vẫn đúng | Reactor Context, không ThreadLocal |

Bộ test quan trọng nhất cho **hợp đồng** là RA-01/02/03: cùng một phương thức `authenticate(...)` nhưng phát ra **ba kiểu terminal behavior khác nhau**. Các test HTTP RA-14/15/16 chứng minh request thật gọi đúng WebFlux filter/manager, không chỉ unit test một class bị bỏ khỏi cấu hình.

## 16. Kết luận

**ReactiveAuthenticationManager không trả một Authentication ngay lập tức: nó trả một Mono mô tả quá trình xác thực.** Contract yêu cầu phân biệt chặt chẽ:

- **`Mono.just(authenticated)`**: có một kết quả được xác thực thật, principal/authorities từ nguồn đáng tin.
- **`Mono.empty()`**: manager không thể xác định/không nhận trách nhiệm với token cụ thể; có thể giúp điều phối manager khác, **không** dành cho password sai.
- **`Mono.error(AuthenticationException)`**: thông tin xác thực đã bị từ chối hoặc quá trình authentication lỗi; phải giữ ngữ nghĩa exception cụ thể.
- **`DelegatingReactiveAuthenticationManager`**: đi tiếp khi empty, **dừng ở error theo mặc định**; bật tiếp tục khi error là quyết định có rủi ro.
- **WebFlux**: `SecurityWebFilterChain`, `AuthenticationWebFilter`, Reactor Context và Spring Security handlers quyết định cách request diễn ra và HTTP response.
- **Cài đặt đúng**: không `block()`, `subscribe()` thủ công, không `Mono.just(null)`, không dùng ThreadLocal như nguồn context, không bật fallback bừa khi credential sai.
- **Kiểm thử đúng**: dùng `StepVerifier` để khẳng định onNext/empty/error và `WebTestClient` để kiểm tra luồng HTTP, authorization, entry point, principal thật.

Khi có thể, **ưu tiên manager chuẩn** của Spring Security cho username/password, JWT hoặc opaque token; chỉ tự viết `ReactiveAuthenticationManager` khi có protocol/nguồn dữ liệu đặc thù. Đó là cách giữ contract rõ ràng, dễ test và ít rủi ro bảo mật hơn.

### Tài liệu tham khảo

- Spring Security 6.5 API — ReactiveAuthenticationManager: https://www.springframework.org/spring-security/reference/6.5/api/java/org/springframework/security/authentication/ReactiveAuthenticationManager.html
- Spring Security 6.5 API — DelegatingReactiveAuthenticationManager: https://www.springframework.org/spring-security/reference/6.5/api/java/org/springframework/security/authentication/DelegatingReactiveAuthenticationManager.html
- Spring Security 6.5 API — AuthenticationWebFilter: https://docs.spring.io/spring-security/site/docs/6.5.x/api/org/springframework/security/web/server/authentication/AuthenticationWebFilter.html
- Spring Security 6.5 API — ServerHttpSecurity.HttpBasicSpec: https://www.springframework.org/spring-security/reference/6.5/api/java/org/springframework/security/config/web/server/ServerHttpSecurity.HttpBasicSpec.html
- Spring Security 6.5 API — AbstractUserDetailsReactiveAuthenticationManager: https://docs.spring.io/spring-security/site/docs/6.5.x/api/org/springframework/security/authentication/AbstractUserDetailsReactiveAuthenticationManager.html
- Spring Security Reference — WebFlux Security: https://docs.spring.io/spring-security/reference/reactive/configuration/webflux.html
- Spring Security Reference — Reactive Authentication: https://docs.spring.io/spring-security/reference/reactive/authentication/index.html
- Spring Security Reference — Reactive Authorization / Reactor Context: https://docs.spring.io/spring-security/reference/reactive/authorization/method.html
- Project Reactor — Mono Javadoc: https://projectreactor.io/docs/core/release/api/reactor/core/publisher/Mono.html
- Reactor Test — StepVerifier: https://projectreactor.io/docs/test/release/api/reactor/test/StepVerifier.html
