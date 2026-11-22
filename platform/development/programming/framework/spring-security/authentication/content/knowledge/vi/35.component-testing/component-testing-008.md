# StepVerifier cho ReactiveAuthenticationManager và các nhánh Mono

## 1. Mục tiêu và phạm vi

Trong Spring Security **WebFlux**, interface `ReactiveAuthenticationManager` nhận một đối tượng `Authentication` mô tả yêu cầu xác thực và trả về `Mono<Authentication>`. Khi kiểm thử thành phần này, gọi `authenticate(...)` rồi chỉ `assertNotNull(mono)` là **không đủ**: `Mono` là biểu diễn một phép tính bất đồng bộ, cần đăng ký subscriber mới quan sát tín hiệu. `StepVerifier` của **Reactor Test** cho phép xác minh chính xác các tín hiệu `onSubscribe`, `onNext`, `onComplete`, `onError`, cancellation, timing và cách fallback.

Bài này tập trung vào **contract và các nhánh Mono của authentication manager**, sau đó mở rộng sang các kiểm thử thực tế Spring Security. Đối tượng chính là Spring Security 6.5.x / Spring Boot 3.x / Java 17+ với Reactor 3.x; ví dụ cấu hình Gradle dành cho dự án đã có plugin/BOM phù hợp.

### Kết quả học tập

1. Phân biệt **`Mono.just(authentication)`**, **`Mono.empty()`** và **`Mono.error(exception)`** theo contract `ReactiveAuthenticationManager`.
2. Dùng `StepVerifier.create(...)` để xác minh đăng nhập thành công, trạng thái `isAuthenticated()`, principal/authorities/credentials và đúng một phần tử.
3. Kiểm tra nhánh từ chối bằng `expectError(...)`, `expectErrorSatisfies(...)` mà không nuốt `AuthenticationException`.
4. Dùng `PublisherProbe` cho fallback giữa manager, phân biệt empty với error; không tự động coi empty là invalid password.
5. Kiểm tra cold publisher, hành vi khi subscribe nhiều lần, timeout, virtual time, cancellation và Reactor Context.
6. So sánh **unit/component test manager** với **WebTestClient test security filter chain** để không nhầm kết quả Mono với HTTP 401/403 hoặc trạng thái SecurityContext.
7. Tránh lỗi test bị treo, dùng blocking, lệch virtual scheduler, test không subscribe, assert thiếu completion hoặc mock che mất logic thật.

**Giới hạn:** `ReactiveAuthenticationManager` thuộc luồng **WebFlux**; Servlet dùng `AuthenticationManager` đồng bộ. `StepVerifier` không thay được `WebTestClient`, integration test JWT signature/Key, hay kiểm thử database/concurrency thật.

## 2. Contract chính xác của ReactiveAuthenticationManager

API:

~~~java
package org.springframework.security.authentication;

@FunctionalInterface
public interface ReactiveAuthenticationManager {
    Mono<Authentication> authenticate(Authentication authentication);
}
~~~

Chữ ký trên **chỉ là bản giản lược mang tính học thuật** (không bao gồm imports), không phải file Java mới cần tạo. Spring Security mô tả ba kết quả:

| Tín hiệu | Phản hồi Mono | Ý nghĩa của manager | Assertion StepVerifier |
| --- | --- | --- | --- |
| **Thành công** | `onNext(authenticated Authentication)` rồi `onComplete` | Manager xác minh credential và trả Authentication | `assertNext(...)` + `verifyComplete()` |
| **Không quyết định** | Chỉ `onComplete`, không có `onNext` | Manager không thể xác thực loại request đó / không nhận định được | `verifyComplete()` ngay, hoặc `expectNextCount(0).verifyComplete()` |
| **Thất bại** | `onError(AuthenticationException)` | Manager nhận request nhưng xác thực thất bại | `expectError(BadCredentialsException.class).verify()` |
| **Chưa kết thúc** | Không complete/error, ví dụ `Mono.never()` | Publisher có thể treo do phụ thuộc/hỏng logic | Test timeout/cancel, không chờ vô hạn |

**Điểm quyết định:** `Mono.empty()` **không đồng nghĩa** “mật khẩu sai”; nó nói manager không đưa ra kết quả. Trong chain nhiều manager, empty có thể cho phép thử manager tiếp theo. Nếu username/password đã được một manager xử lý và credential sai, thông thường nên phát `Mono.error(new BadCredentialsException(...))` để không chuyển sang handler yếu hơn.

**Một `Mono<Authentication>` chỉ được phép phát tối đa một giá trị**, vì đó là `Mono`. Kết quả success phải thỏa `auth.isAuthenticated() == true` và chứa principal/authorities theo policy. Một `Authentication` có `isAuthenticated=false` dù được phát ra bằng `Mono.just(...)` là một tín hiệu phần tử, **không mặc nhiên tương đương xác thực thành công**; test cần kiểm tra thuộc tính.

### Chuỗi tín hiệu trực quan

~~~text
Mã kiểm thử gọi manager.authenticate(request)
                    |
                    v
             Mono<Authentication>
                    |
              StepVerifier
                 subscribe
                    |
        +-----------+-------------+
        |           |             |
       onNext     onComplete      onError
   Authentication (không value)  AuthenticationException
        |
     onComplete

Mono.just(authentication)  = onNext -> onComplete
Mono.empty()               = onComplete
Mono.error(exception)      = onError
Mono.never()               = không terminal event
~~~

**Không có `Mono.just(null)`** trong Reactor: `null` không phải onNext hợp lệ. Khi branch không có Authentication, dùng `Mono.empty()` đúng mục đích, hoặc `Mono.error(...)` nếu credential bị từ chối. Tránh trả `null` thay `Mono`; đó là lỗi contract có thể nổ `NullPointerException` khi caller subscribe.

## 3. Phụ thuộc và cấu trúc file

Trong dự án Spring Boot 3.x đã cấu hình plugin Spring Boot và dependency management/BOM, thêm những dependencies sau vào `build.gradle`:

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

- `spring-boot-starter-webflux` đưa Reactor/WebFlux vào ứng dụng; tránh vô tình thêm `spring-boot-starter-web` rồi giả định app chạy reactive HTTP: khi có cả hai starter, mặc định Spring Boot có thể chọn MVC trừ khi cấu hình loại ứng dụng.
- `spring-boot-starter-security` cung cấp `ReactiveAuthenticationManager`, `Authentication` và các token/exception.
- `reactor-test` cung cấp `StepVerifier`, `PublisherProbe`, `VirtualTimeScheduler`. Đây là dependency **test scope**.
- `spring-boot-starter-test` thường bao gồm JUnit Jupiter và công cụ test Spring/AssertJ. Chọn BOM đồng bộ, không trộn thủ công Reactor 3.x không tương thích với Boot.
- `spring-security-test` hữu ích cho `WebTestClient`, `mockUser`/JWT mock ở tầng web; không làm manager tự xác thực hơn trong unit test.

Ví dụ chính ở mục 4 là **một class JUnit đầy đủ**, tên file phải đúng `ReactiveAuthenticationManagerStepVerifierTest.java`, đặt tại `src/test/java/example/`. Nó chạy với `./gradlew test --tests "example.ReactiveAuthenticationManagerStepVerifierTest"` khi đã có Gradle wrapper và dependencies trên. Không cần kết nối database hay Spring ApplicationContext vì đây là unit/component test.

## 4. Bộ JUnit 5 hoàn chỉnh: thành công, empty và lỗi

### 4.1. Manager giả dành riêng cho unit test

Ta tạo một implementation chỉ chấp nhận `UsernamePasswordAuthenticationToken`. User `alice` với mật khẩu demo `correct-password` thành công; username/password khác trả `BadCredentialsException` chung; loại token khác trả `Mono.empty()`.

**Đây là test double để kiểm thử contract, không phải authentication implementation được phép dùng production.** Mã demo so sánh string mật khẩu thô để đơn giản hóa nhánh, **không** dùng password encoder, không đọc user database, không chống brute-force. Mọi ứng dụng thật cần `PasswordEncoder`, user store và policy đầy đủ.

### 4.2. File Java chạy trong JUnit

~~~java
package example;

import java.time.Duration;
import java.util.List;
import java.util.concurrent.TimeoutException;
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.concurrent.atomic.AtomicInteger;

import org.junit.jupiter.api.Test;
import org.springframework.security.authentication.AnonymousAuthenticationToken;
import org.springframework.security.authentication.BadCredentialsException;
import org.springframework.security.authentication.ReactiveAuthenticationManager;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.authority.SimpleGrantedAuthority;

import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;
import reactor.test.publisher.PublisherProbe;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertInstanceOf;
import static org.junit.jupiter.api.Assertions.assertNull;
import static org.junit.jupiter.api.Assertions.assertTrue;

class ReactiveAuthenticationManagerStepVerifierTest {

    private static Authentication login(String username, String password) {
        return UsernamePasswordAuthenticationToken.unauthenticated(
            username, password);
    }

    private static Authentication ignoredTokenType() {
        return new AnonymousAuthenticationToken(
            "test-key", "anonymous",
            List.of(new SimpleGrantedAuthority("ROLE_ANONYMOUS")));
    }

    private static Authentication authenticated(String username) {
        return UsernamePasswordAuthenticationToken.authenticated(
            username, null,
            List.of(new SimpleGrantedAuthority("ROLE_USER")));
    }

    private static ReactiveAuthenticationManager sampleManager(
            AtomicInteger subscriptionCount) {

        return request -> Mono.defer(() -> {
            subscriptionCount.incrementAndGet();

            // Một manager không hỗ trợ loại Authentication này
            // phải trả Mono.empty() thay vì ngầm nhận credential.
            if (!(request instanceof UsernamePasswordAuthenticationToken)) {
                return Mono.empty();
            }

            String name = request.getName();
            Object credentials = request.getCredentials();
            if ("alice".equals(name)
                    && "correct-password".equals(credentials)) {
                return Mono.just(authenticated("alice"));
            }

            // Test double: mọi sai lệch của username/password
            // đều dùng lỗi chung. Production dùng user store
            // và PasswordEncoder, không so plaintext.
            return Mono.error(
                new BadCredentialsException("Invalid credentials"));
        });
    }

    @Test
    void successfulAuthenticationEmitsOneAuthenticatedValueAndCompletes() {
        var manager = sampleManager(new AtomicInteger());

        StepVerifier.create(manager.authenticate(
                login("alice", "correct-password")))
            .assertNext(value -> {
                assertTrue(value.isAuthenticated());
                assertEquals("alice", value.getName());
                assertNull(value.getCredentials());
                assertTrue(value.getAuthorities().stream()
                    .anyMatch(a -> a.getAuthority().equals("ROLE_USER")));
            })
            .verifyComplete();
    }

    @Test
    void invalidCredentialsProduceAuthenticationErrorNotEmptyCompletion() {
        var manager = sampleManager(new AtomicInteger());

        StepVerifier.create(manager.authenticate(
                login("alice", "incorrect")))
            .expectErrorSatisfies(error -> {
                assertInstanceOf(BadCredentialsException.class, error);
            })
            .verify();
    }

    @Test
    void unknownUsernameAlsoFailsWithGenericAuthenticationError() {
        var manager = sampleManager(new AtomicInteger());

        StepVerifier.create(manager.authenticate(
                login("unknown", "correct-password")))
            .expectError(BadCredentialsException.class)
            .verify();
    }

    @Test
    void unsupportedTokenTypeCompletesEmptyWithoutAuthenticationValue() {
        var manager = sampleManager(new AtomicInteger());

        StepVerifier.create(manager.authenticate(ignoredTokenType()))
            .verifyComplete();
    }

    @Test
    void coldMonoDefersWorkUntilSubscription() {
        var count = new AtomicInteger();
        var manager = sampleManager(count);

        Mono<Authentication> result =
            manager.authenticate(login("alice", "correct-password"));

        assertEquals(0, count.get());

        StepVerifier.create(result)
            .expectNextMatches(Authentication::isAuthenticated)
            .verifyComplete();
        assertEquals(1, count.get());

        // Resubscribe chạy lại source Mono.defer trong test double.
        StepVerifier.create(result)
            .expectNextCount(1)
            .verifyComplete();
        assertEquals(2, count.get());
    }

    @Test
    void emptyResultCanTriggerFallbackToSecondManager() {
        var first = sampleManager(new AtomicInteger());
        PublisherProbe<Authentication> fallback = PublisherProbe.of(
            Mono.just(authenticated("fallback-user")));

        Mono<Authentication> result =
            first.authenticate(ignoredTokenType())
                .switchIfEmpty(fallback.mono());

        StepVerifier.create(result)
            .assertNext(value -> {
                assertTrue(value.isAuthenticated());
                assertEquals("fallback-user", value.getName());
            })
            .verifyComplete();

        fallback.assertWasSubscribed();
    }

    @Test
    void errorDoesNotTriggerSwitchIfEmptyFallback() {
        var first = sampleManager(new AtomicInteger());
        PublisherProbe<Authentication> fallback = PublisherProbe.of(
            Mono.just(authenticated("fallback-user")));

        Mono<Authentication> result =
            first.authenticate(login("alice", "wrong"))
                .switchIfEmpty(fallback.mono());

        StepVerifier.create(result)
            .expectError(BadCredentialsException.class)
            .verify();

        fallback.assertWasNotSubscribed();
    }

    @Test
    void virtualTimeTestsDelayedAuthenticationWithoutRealWaiting() {
        ReactiveAuthenticationManager delayed = request ->
            Mono.delay(Duration.ofMinutes(5))
                .map(tick -> authenticated("alice"));

        StepVerifier.withVirtualTime(() -> delayed.authenticate(
                login("alice", "correct-password")))
            .expectSubscription()
            .expectNoEvent(Duration.ofMinutes(5))
            .assertNext(value -> {
                assertTrue(value.isAuthenticated());
                assertEquals("alice", value.getName());
            })
            .verifyComplete();
    }

    @Test
    void timeoutErrorIsASeparateBranchFromWrongPassword() {
        ReactiveAuthenticationManager stalled =
            request -> Mono.never();

        StepVerifier.withVirtualTime(() ->
                stalled.authenticate(login("alice", "correct-password"))
                    .timeout(Duration.ofSeconds(3)))
            .expectSubscription()
            .thenAwait(Duration.ofSeconds(3))
            .expectError(TimeoutException.class)
            .verify();
    }

    @Test
    void cancellationNotifiesPublisher() {
        var cancelled = new AtomicBoolean(false);

        ReactiveAuthenticationManager pending = request ->
            Mono.<Authentication>never()
                .doOnCancel(() -> cancelled.set(true));

        StepVerifier.create(pending.authenticate(
                login("alice", "correct-password")))
            .thenCancel()
            .verify();

        assertTrue(cancelled.get());
    }
}
~~~

### 4.3. Đọc đúng kỳ vọng từng test

- Test `successfulAuthentication...` đòi **một onNext** chứa `Authentication` đã xác thực, principal là Alice, credentials đã xóa và có `ROLE_USER`; tiếp theo phải có `onComplete`. Nếu manager trả `Mono.empty()`, `assertNext` fail.
- Test `invalidCredentials...` đòi `onError(BadCredentialsException)`. Nếu manager trả empty để giấu lỗi, test fail. Đây là policy bảo vệ “credential sai không được rơi vào fallback”.
- Test `unknownUsername...` bảo đảm test double không tạo nhánh thông báo riêng cho username không tồn tại; đây chưa phải kiểm thử timing/user enumeration ở HTTP.
- Test `unsupportedTokenType...` đòi completion **không có phần tử**. `verifyComplete()` tại bước đầu tiên đủ để bắt một `onNext` ngoài ý muốn; không cần `expectNextCount(0)`.
- Test `coldMono...` có `Mono.defer` nên tăng counter **khi subscribe**, không phải khi gọi `authenticate`. Lần subscribe thứ hai chạy lại source. **Không** mặc định mọi manager thật đều idempotent: nếu source có tác dụng phụ, hai subscriber có thể gây hai lần lookup/token issue.
- `PublisherProbe` cho phép khẳng định có hay không có subscription ở nhánh dự phòng, mạnh hơn việc chỉ kiểm tra output; `switchIfEmpty` chỉ fallback khi upstream **complete rỗng**, không fallback khi `onError`.
- Test `virtualTime...` tạo `Mono.delay` **bên trong Supplier** truyền cho `withVirtualTime`; scheduler ảo có thể thay thế default scheduler trước khi publisher được lắp ráp.
- Test `timeout...` cho thấy lỗi `TimeoutException` là lỗi hệ thống/timeout, không phải `BadCredentialsException`. Application có thể chuyển thành lỗi tạm thời (ví dụ 503), không trả 401 sai mật khẩu.
- Test `cancellation...` hủy một source chưa kết thúc; kiểm tra tín hiệu hủy được phát. Cancellation không chứng minh tác vụ mạng/DB đã dừng ngay trên mọi driver.

**Output:** các test không in `System.out`; thành công nghĩa JUnit runner đánh dấu pass. Không bịa một stdout cố định cho `./gradlew test` vì còn phụ thuộc Gradle version và cấu hình logging. Các test minh họa dùng `@Test` của JUnit Jupiter và imports đều nằm trong file.

### 4.4. Lệnh chạy

~~~bash
./gradlew test --tests "example.ReactiveAuthenticationManagerStepVerifierTest"
~~~

Trên Windows PowerShell:

~~~powershell
.\gradlew.bat test --tests "example.ReactiveAuthenticationManagerStepVerifierTest"
~~~

Bài kiểm thử này **không cần `@SpringBootTest`**, giảm chi phí dựng application context; đây chính là lợi thế của component test kiểm tra tín hiệu Mono. Nếu yêu cầu kiểm tra integration với Spring Security filter chain, xem mục 9.

## 5. Kiểm thử manager thực dùng ReactiveUserDetailsService

Test double ở trên giúp hiểu contract, nhưng không chứng minh `UserDetailsRepositoryReactiveAuthenticationManager` của Spring Security làm việc đúng với password encoder, trạng thái account và user store. Để thử manager thật với một **user store in-memory chỉ dành cho test**, tạo `src/test/java/example/RealReactiveUserDetailsManagerTest.java`:

~~~java
package example;

import org.junit.jupiter.api.Test;
import org.springframework.security.core.AuthenticationException;
import org.springframework.security.authentication.UserDetailsRepositoryReactiveAuthenticationManager;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.userdetails.MapReactiveUserDetailsService;
import org.springframework.security.core.userdetails.User;

import reactor.test.StepVerifier;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

class RealReactiveUserDetailsManagerTest {

    private UserDetailsRepositoryReactiveAuthenticationManager manager() {
        var user = User.withUsername("alice")
            // {noop} chỉ chấp nhận ở ví dụ test, không cho production.
            .password("{noop}correct-password")
            .roles("USER")
            .build();

        var users = new MapReactiveUserDetailsService(user);
        return new UserDetailsRepositoryReactiveAuthenticationManager(users);
    }

    @Test
    void authenticatesExistingUserWithCorrectPassword() {
        var input = UsernamePasswordAuthenticationToken
            .unauthenticated("alice", "correct-password");

        StepVerifier.create(manager().authenticate(input))
            .assertNext(authentication -> {
                assertTrue(authentication.isAuthenticated());
                assertEquals("alice", authentication.getName());
            })
            .verifyComplete();
    }

    @Test
    void rejectsWrongPassword() {
        var input = UsernamePasswordAuthenticationToken
            .unauthenticated("alice", "wrong-password");

        StepVerifier.create(manager().authenticate(input))
            .expectError(AuthenticationException.class)
            .verify();
    }
}
~~~

**Tại sao dùng `expectError(AuthenticationException.class)` thay vì assert message?** API có thể sử dụng subclass cụ thể hay nội dung message khác nhau giữa phiên bản/cấu hình để tránh lộ chi tiết. Test hành vi xác thực cần tập trung vào **loại lỗi hợp đồng**, không khóa cứng chuỗi tiếng Anh không được bảo đảm.

Trong Spring Security 6.5, `UserDetailsRepositoryReactiveAuthenticationManager` kế thừa `AbstractUserDetailsReactiveAuthenticationManager` và dùng `ReactiveUserDetailsService`. Password encoder mặc định hỗ trợ định dạng `{id}encodedPassword` thông qua `DelegatingPasswordEncoder`. `{noop}` chỉ để đơn giản hóa test; production cần bcrypt/argon2/scrypt/PBKDF2 hoặc phương án mật khẩu đã được lựa chọn phù hợp và quản lý hash an toàn.

**Không tạo chứng chỉ tài khoản production bằng `{noop}`**, không hardcode mật khẩu thật trong tests/logs và không lưu plain password ở database.

Lệnh chạy:

~~~bash
./gradlew test --tests "example.RealReactiveUserDetailsManagerTest"
~~~

Nếu dự án sử dụng UserDetailsService reactive từ R2DBC/LDAP/custom RPC, thay MapReactiveUserDetailsService bằng test double hoặc test container có độ trễ và lỗi được kiểm soát. Vẫn nên giữ một bộ unit test cho contract và một bộ integration test riêng để kiểm tra interactions, deadlock, scheduler, transaction và load.

## 6. Fallback với nhiều ReactiveAuthenticationManager: nhánh empty khác lỗi

Một kiến trúc có thể có nhiều cơ chế credential (JWT, opaque token, username/password, custom). Manager thứ nhất trả empty khi **không hỗ trợ loại Authentication** và để manager khác thử. Manager đã nhận request nhưng xác minh thất bại thường phát `AuthenticationException` để chặn fallback sang phương thức yếu.

~~~text
authentication request
     |
     v
manager A.authenticate(request)
     |-- onNext(auth) + complete ---> SUCCESS
     |-- complete empty ----------> thử manager B (theo chain/policy)
     |-- onError(AuthException) ---> FAIL, không fallback mặc định
     |
     v
manager B.authenticate(request)
     |-- onNext(auth) + complete ---> SUCCESS
     |-- complete empty ----------> chưa có manager xử lý
     |-- onError(...) ------------> FAIL
~~~

Trong Reactor, `switchIfEmpty(alternative)` là công cụ để minh họa; **nhưng đừng tự lắp chain authentication trong production khi framework đã có `DelegatingReactiveAuthenticationManager`** trừ khi hiểu rõ semantics, thứ tự và audit. Với Spring Security 6.3+, `DelegatingReactiveAuthenticationManager` có `setContinueOnError(boolean)`; mặc định `false`. Bật `true` có thể khiến manager tiếp theo thử dù manager trước đã lỗi, nên phải xem threat model, đặc biệt nguy cơ downgrade/bypass. Không đánh đồng “không xử lý” và “xác thực thất bại”.

### PublisherProbe bảo đảm nhánh nào được subscribe

Hai test ở mục 4 chứng minh:

- `Mono.empty().switchIfEmpty(probe.mono())` → fallback **được subscribe**.
- `Mono.error(BadCredentialsException).switchIfEmpty(probe.mono())` → fallback **không được subscribe**.

Nếu chỉ assert result success mà không kiểm tra `PublisherProbe`, test có thể vẫn pass dù fallback luôn được gọi hoặc side-effect bị kích hoạt ngoài ý muốn. `PublisherProbe.assertWasSubscribed()` và `assertWasNotSubscribed()` bắt được điều đó. Có thể dùng thêm `assertWasRequested()`, `assertWasCancelled()` khi cần kiểm tra nhu cầu/request và hủy.

### Khi nào dùng onErrorResume?

~~~java
// KHÔNG KHUYẾN NGHỊ: biến bad credentials thành empty,
// tạo cơ hội dùng nhánh auth yếu hơn ở downstream.
Mono<Authentication> unsafe =
    manager.authenticate(request)
           .onErrorResume(BadCredentialsException.class,
                          error -> Mono.empty());
~~~

Đây là **snippet** trong class đã có `manager` và `request`; không phải mã độc lập. Chuyển lỗi credential thành completion rỗng là một **thay đổi nghĩa bảo mật**, phải được review. Có thể dùng `onErrorMap` để chuyển lỗi hạ tầng thành một loại lỗi vận hành tương thích hoặc `doOnError` để ghi metric đã redact; không dùng `onErrorResume` bừa bãi chỉ để test pass.

Lỗi bất ngờ `IllegalStateException`, DB timeout hay network failure không được tự chuyển thành “sai mật khẩu”; phân loại để server trả thông tin công khai an toàn và vận hành nhận được lý do phù hợp.

## 7. Virtual time, timeout, cancellation và tính quyết định của test

`StepVerifier.withVirtualTime(Supplier<Publisher<T>>)` giúp kiểm tra `Mono.delay`, `timeout`, `retryWhen`, `delayElement` mà không phải sleep thật.

**Quy tắc:** dựng publisher **trong supplier** sau khi virtual scheduler được kích hoạt. Đây là điều kiện quan trọng để đồng hồ ảo có hiệu lực.

~~~java
// ĐÚNG: delay được tạo khi Supplier được gọi
StepVerifier.withVirtualTime(() ->
        Mono.delay(Duration.ofMinutes(5)))
    .expectSubscription()
    .expectNoEvent(Duration.ofMinutes(5))
    .expectNext(0L)
    .verifyComplete();
~~~

~~~java
// CẦN TRÁNH: dựng publisher quá sớm rồi mới trả lại
Mono<Long> delayed = Mono.delay(Duration.ofMinutes(5));
StepVerifier.withVirtualTime(() -> delayed)
    .expectSubscription()
    .thenAwait(Duration.ofMinutes(5))
    .expectNext(0L)
    .verifyComplete();
~~~

Đoạn thứ hai **không có bảo đảm virtual time hoạt động như mong muốn**, vì scheduler có thể đã được bắt trước khi StepVerifier thiết lập scheduler ảo. Nó minh họa anti-pattern, không nên chạy như test chính.

### expectSubscription() trước expectNoEvent()

`expectNoEvent(Duration)` xem **subscription cũng là một event**. Nếu đặt `expectNoEvent` làm bước đầu tiên thì test có thể fail ngay vì subscription signal. Trình tự đúng:

~~~java
StepVerifier.withVirtualTime(() ->
        Mono.delay(Duration.ofSeconds(5)))
    .expectSubscription()
    .expectNoEvent(Duration.ofSeconds(5))
    .expectNext(0L)
    .verifyComplete();
~~~

`thenAwait(duration)` chỉ đẩy thời gian/chờ mà **không khẳng định không có onNext trước đó**; `expectNoEvent(duration)` là assertion mạnh hơn nếu muốn kiểm tra không có tín hiệu đến sớm.

### Test timeout mà không treo CI

- Khi source cố ý là `Mono.never()`, phải có `thenCancel()` hoặc `timeout(...)`. `StepVerifier.create(Mono.never()).verifyComplete()` có thể treo vì không có terminal event.
- Với component test không dùng virtual time, đặt timeout hữu hạn cho `verify(Duration.ofSeconds(3))` hoặc timeout do framework thiết lập; không để infinite hang.
- `TimeoutException` không tự là `AuthenticationException`. Ở tầng HTTP, lỗi hạ tầng/timeout cần được phân loại và trả response công khai thích hợp (có thể 503), tránh đánh đồng 401.
- Khi manager sử dụng scheduler **được inject riêng** thay vì Reactor default `Schedulers` factory, virtual time không tự thay thế được mọi scheduler; truyền `VirtualTimeScheduler` tương ứng vào code đang kiểm thử hoặc dùng test timeout thực ngắn và ổn định.
- `Mono.delay`/Schedulers trong test ảo khác việc kiểm tra external IdP, bcrypt, Redis, JDBC thực chạy đồng thời. Không tuyên bố rằng virtual time tự kiểm thử mọi giới hạn SLA thực tế.

### Kiểm thử hủy và side effects

`StepVerifier.create(publisher).thenCancel().verify()` đảm bảo subscriber phát cancel. Nếu producer đã bắt đầu DB request không hủy được, hiệu ứng phía hệ thống ngoài vẫn có thể hoàn thành; test cần xác định **hệ quả nghiệp vụ** (lệnh revoke token, phát OTP, tăng login attempt) có idempotent và được bảo vệ transaction không. Không dùng cancellation làm chứng minh chắc chắn mọi thao tác external đã rollback.

## 8. Reactor Context và ReactiveSecurityContextHolder

`ReactiveAuthenticationManager.authenticate(...)` trả `Mono<Authentication>`; điều đó **không tự chứng minh** WebFlux đã lưu Authentication vào `SecurityContext`. Trong WebFlux, `ReactiveSecurityContextHolder` lấy SecurityContext từ **Reactor Context**, không phải ThreadLocal servlet `SecurityContextHolder`.

Một test riêng có thể xác minh việc truyền SecurityContext trong reactive chain; **nó không test manager** mà test context wiring:

~~~java
package example;

import java.util.List;

import org.junit.jupiter.api.Test;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.core.context.ReactiveSecurityContextHolder;

import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;

class ReactiveSecurityContextTest {

    @Test
    void authenticationIsReadFromReactorContext() {
        var auth = UsernamePasswordAuthenticationToken.authenticated(
            "alice", null,
            List.of(new SimpleGrantedAuthority("ROLE_USER")));

        Mono<String> name =
            ReactiveSecurityContextHolder.getContext()
                .map(context -> context.getAuthentication().getName())
                .contextWrite(
                    ReactiveSecurityContextHolder.withAuthentication(auth));

        StepVerifier.create(name)
            .expectNext("alice")
            .verifyComplete();
    }

    @Test
    void withoutContextThereIsNoSecurityContextValue() {
        Mono<String> name =
            ReactiveSecurityContextHolder.getContext()
                .map(context -> context.getAuthentication().getName());

        StepVerifier.create(name)
            .verifyComplete();
    }
}
~~~

Tại `ReactiveSecurityContextHolder.getContext()`, nếu không có context được thiết lập, Mono có thể complete rỗng như trong ví dụ. Nếu tích hợp method security, hãy đặt `.contextWrite(ReactiveSecurityContextHolder.withAuthentication(auth))` **ở đúng vị trí** của reactive composition rồi xác minh method service nhận đúng Authentication. **Không sử dụng ThreadLocal SecurityContextHolder để suy ra identity trong một stream chạy qua nhiều threads**; Reactor Context gắn với subscriber chain.

Trong ứng dụng WebFlux được cấu hình đúng, security filters chịu trách nhiệm đưa Authentication/SecurityContext vào context cho downstream. Một unit test gọi manager trực tiếp chưa chứng minh điều đó.

## 9. Component test so với WebTestClient: kiểm thử ở đúng tầng

| Cần kiểm tra | Công cụ chính | Vì sao |
| --- | --- | --- |
| Manager trả `onNext`/`onComplete`/`onError` đúng | `StepVerifier` | Quan sát trực tiếp Publisher contract |
| Password encoder/UserDetailsReactiveService | `StepVerifier` + manager thật | Không cần dựng HTTP server |
| Nhánh manager thứ hai có được gọi không | `PublisherProbe` / Mockito verify | Phân biệt fallback và error |
| Timeout/backoff/delay | `withVirtualTime` / controlled scheduler | Test nhanh, không sleep |
| Reactive SecurityContext | `StepVerifier` + `ReactiveSecurityContextHolder` | Context theo subscription |
| HTTP Basic/WebFlux login trả 401 hoặc 302? | `WebTestClient` + `SecurityWebFilterChain` | Status/challenge/redirect thuộc filter |
| JWT thật được validate chữ ký, `iss`, `aud` | Integration với decoder/key/test IdP | Mock auth không chứng minh cryptographic validation |
| Cookies, CSRF, anonymous vs authenticated HTTP | `WebTestClient` + `spring-security-test` | Test behavior client |
| Event loop không blocking dưới tải | Integration/load/blocking detector | Unit StepVerifier một mình không chứng minh không block |

### WebTestClient snippet (không phải test class độc lập)

Đoạn này yêu cầu đã có `WebTestClient client` bound với `ApplicationContext` hoặc server WebFlux, `SecurityWebFilterChain` bảo vệ `/api/private`, và HTTP Basic cấu hình:

~~~java
client.get()
      .uri("/api/private")
      .exchange()
      .expectStatus().isUnauthorized();

// Sai credential đi qua HTTP Basic filter và manager:
client.get()
      .uri("/api/private")
      .headers(headers -> headers.setBasicAuth("alice", "wrong"))
      .exchange()
      .expectStatus().isUnauthorized();
~~~

Với authentication success, có thể assert 200 trên endpoint cụ thể khi account có quyền; nếu thiếu role, request authenticated có thể 403. **Không áp một status cố định chỉ vì manager phát `Mono.empty()`**: HTTP entry point, error handler, method security và policy mới định nghĩa response.

Khi sử dụng `mockUser()`, `mockJwt()`/JWT test postprocessors, đó là **mô phỏng SecurityContext/Authentication**, không xác minh password, signature hay gọi toàn bộ manager. Dùng đúng loại test để tránh “green test” bỏ qua cơ chế thật.

### Bắt lỗi ngoài ý muốn

Một `StepVerifier` unit test có thể pass vì mock luôn trả `Mono.just(authenticated)`, trong khi code thật bị lỗi lookup hoặc timing; nên có ít nhất một bộ test manager thật (mục 5) và một bộ test filter HTTP. Không cần Spring context trong tất cả test: ưu tiên nhanh cho hợp đồng tín hiệu, chọn integration ở nơi có boundaries thật.

## 10. Những lỗi phổ biến khi test ReactiveAuthenticationManager

1. **Chỉ assert Mono khác null:** không subscribe thì logic trong `Mono.defer`/publisher cold chưa chạy. Dùng `StepVerifier.create(...)`.
2. **Nhầm `Mono.empty()` thành sai password:** empty = manager không quyết định; wrong password thường là `Mono.error(AuthenticationException)`.
3. **Dùng `expectNextCount(1)` mà không kiểm tra `isAuthenticated`:** Authentication phát ra vẫn có thể chưa xác thực.
4. **Dùng `expectErrorMessage("...")` cho exception nội bộ không ổn định:** test dễ vỡ khi framework/localization thay đổi. Ưu tiên type và policy.
5. **Chỉ `expectNext(...)` mà không `verifyComplete()`:** bỏ sót publisher phát thêm lỗi/không hoàn thành.
6. **Gọi `.block()` trong code production WebFlux:** có thể khóa event loop; chỉ blocking verifier thread trong test là hợp lệ. StepVerifier không bắt buộc dùng `block()`.
7. **Dùng `onErrorResume(... -> Mono.empty())` để “sửa” test:** dễ biến authentication failure thành fallback/downgrade.
8. **Xây `Mono.delay` trước `withVirtualTime`:** virtual scheduler không được áp dụng như mong đợi.
9. **Đặt `expectNoEvent` trước subscription:** subscription cũng tính là event và gây fail.
10. **Không giới hạn verify timeout với source có thể treo:** làm CI chờ vô hạn. Dùng timeout/hủy cụ thể.
11. **Cho rằng cancel bảo đảm rollback external side effect:** hủy subscriber không phải transaction rollback của IdP/DB.
12. **Giả định Servlet `SecurityContextHolder` là Reactor Context:** dẫn tới leak hoặc mất identity khi đổi thread.
13. **Chỉ stub Mockito cho happy path:** không kiểm tra thứ tự, fallback, authentication error và manager thật.
14. **Không test negative branch khi user bị disable/locked:** cần AuthenticationException hoặc policy đúng, không phát Authentication đã xác thực.
15. **Cho manager hỗ trợ mọi token type:** nguy cơ xử lý token không phù hợp bằng cơ chế credential yếu; cần nhánh empty hoặc error đúng policy.
16. **Không phân biệt authentication và authorization:** manager trả Authentication thành công không bảo đảm request qua `AuthorizationWebFilter` có đủ scope/role.
17. **Nhận lỗi runtime/timeout thành `BadCredentialsException`:** phía client nhận 401 giả và vận hành không thấy outage.
18. **Tạo Authentication mới mà còn giữ raw password trong credentials:** tránh đưa credential thô vào result và log; test có thể kiểm tra `getCredentials()==null` theo design.

## 11. Checklist tự đánh giá

- [ ] Ba nhánh `Mono.just(authenticated)` / `Mono.empty()` / `Mono.error(AuthenticationException)` đã có test StepVerifier riêng.
- [ ] Success kiểm tra principal, `isAuthenticated`, authorities, credential handling, một giá trị và completion.
- [ ] Wrong credentials không trở thành empty/fallback; type AuthenticationException được assert đúng.
- [ ] Unsupported authentication type được kiểm thử không tạo user authenticated.
- [ ] `PublisherProbe` chứng minh nhánh fallback chỉ subscribe khi empty.
- [ ] Cold/resubscribe behavior được test và side effects được review.
- [ ] Virtual time tạo publisher trong Supplier, tránh sleep; test timeout và cancellation có terminal condition.
- [ ] Lỗi bất ngờ của infrastructure không bị báo sai là bad credentials.
- [ ] SecurityContext reactive được test bằng Reactor Context; không lạm dụng Servlet ThreadLocal.
- [ ] Có ít nhất một component test dùng manager thực và user store test; không chỉ mock.
- [ ] Có WebTestClient integration cho HTTP status, headers, CSRF, JWT/password flows tùy hệ thống.
- [ ] Tests độc lập, không hardcode secrets production, không log credentials hoặc token.

**Ghi nhớ:** `StepVerifier` kiểm tra **tín hiệu của Publisher**. Với `ReactiveAuthenticationManager`, thành công là một `Authentication` đã xác thực và completion; “không xử lý” là completion rỗng; sai credential là error. Phân biệt đúng ba nhánh giúp tránh fallback không an toàn và tạo unit tests phản ánh hành vi xác thực thật.

## 12. Tài liệu chính thức

- Spring Security 6.5 — `ReactiveAuthenticationManager`: https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/authentication/ReactiveAuthenticationManager.html
- Spring Security 6.5 — `UserDetailsRepositoryReactiveAuthenticationManager`: https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/authentication/UserDetailsRepositoryReactiveAuthenticationManager.html
- Spring Security 6.5 — WebFlux Security: https://docs.spring.io/spring-security/reference/6.5/reactive/configuration/webflux.html
- Spring Security 6.5 — Reactive method security and Reactor Context: https://docs.spring.io/spring-security/reference/6.5/reactive/authorization/method.html
- Spring Security — `DelegatingReactiveAuthenticationManager` API: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/authentication/DelegatingReactiveAuthenticationManager.html
- Project Reactor — Testing with `StepVerifier` / `PublisherProbe` / Virtual Time: https://projectreactor.io/docs/core/release/reference/testing.html
- Project Reactor — `StepVerifier` API: https://projectreactor.io/docs/test/release/api/reactor/test/StepVerifier.html
