# StepVerifier và kiểm thử Publisher chứa quyết định bảo mật

## 1. Vì sao unit test một boolean không đủ?

Trong **Spring Security reactive** và **Project Reactor**, logic phân quyền thường được biểu diễn bằng `Mono<AuthorizationResult>`, `Mono<Boolean>`, `Mono<Void>` hoặc một `Flux` thực hiện kiểm tra quyền theo từng tài nguyên. Quyết định không phải lúc nào cũng có sẵn ngay khi gọi method; nó có thể tới sau một truy vấn membership database, sau timeout, hoặc không phát giá trị nào.

Một bài kiểm thử phân quyền nghiêm túc cần trả lời được các câu hỏi:

- Có thật sự phát ra quyết định **allow** hay publisher chỉ `Mono.empty()` rồi complete?
- Khi quyết định **deny**, có chắc nhánh tải dữ liệu nhạy cảm chưa được subscribe?
- Nếu permission database báo lỗi, request có bị **fail closed** hay vô tình chuyển lỗi thành quyền được cấp?
- Publisher đã được subscribe chưa? Lệnh tạo `Mono` có thực hiện truy vấn hay chưa?
- Nếu client ngắt giữa lúc đợi authorization, upstream có nhận `cancel()` và giải phóng resource?
- Danh tính từ `ReactiveSecurityContextHolder` có đi đúng theo subscriber không?
- Khi `@PreAuthorize` từ chối, test phải chờ `AuthorizationDecision(false)` hay `AccessDeniedException`?
- Có thể kiểm policy timeout/TTL bằng virtual time mà không chờ thật không?
- Test `mockJwt()` có chứng minh chữ ký JWT đã được verify không?

Sau bài này, bạn có thể dùng **StepVerifier**, **TestPublisher**, **PublisherProbe**, **StepVerifierOptions** và Spring Security reactive test APIs để kiểm các nhánh allow/deny/empty/error/cancel, kiểm Reactor Context, backpressure, thời gian và các side effect. Có một **Maven project Java 17+** với mã production tối giản và bộ JUnit Jupiter tests để làm mẫu.

**Nguyên tắc:** Một test xanh chỉ khẳng định những điều nó kiểm. `StepVerifier` kiểm publisher signals; nó không tự xác minh JWT/IdP, kiểm AOP proxy, HTTP 401/403 hoặc ownership dữ liệu nếu những tầng đó chưa được đưa vào test.

## 2. Reactive Streams: thứ tự tín hiệu là một phần hợp đồng bảo mật

~~~text
Caller gets Publisher                  Actual subscription
       |                                       |
       |  Mono<AuthorizationResult>            |
       |-------------------------------------->| onSubscribe
       |                                       | request(n)
       |                                       |
       |                      +----------------+---------------+
       |                      |                |               |
       |                    onNext           onComplete      onError
       |                   decision          (0 value)      exception
       |                      |
       |                  onComplete
       |
       | Client may cancel at any point after onSubscribe
       +--------------------------------------> cancel()
~~~

Một `Publisher` thường **lazy**. Gọi `manager.authorize(auth, resource)` chỉ xây một kế hoạch; `onSubscribe`/`request` mới thúc đẩy xử lý. Những khác biệt chính:

| Publisher | Tín hiệu | Ý nghĩa bảo mật |
| --- | --- | --- |
| `Mono.just(new AuthorizationDecision(true))` | onNext(true) rồi onComplete | Manager cấp quyền |
| `Mono.just(new AuthorizationDecision(false))` | onNext(false) rồi onComplete | Manager từ chối |
| `Mono.empty()` | onComplete **không có onNext** | No decision/abstain, không đồng nghĩa allow |
| `Mono.error(ex)` | onError, không có onNext | Lỗi hạ tầng hoặc một tầng chủ động từ chối |
| `Mono<Void>` hoàn tất | onComplete | Có thể là `verify` cho phép |
| `Mono<Void>` lỗi `AccessDeniedException` | onError | Có thể là `verify` từ chối |
| `Mono.never()` | Không emit, không kết thúc | Check bị treo nếu không timeout/cancel |
| `Flux<AuthorizationResult>` | Nhiều onNext | Mỗi event/resource có thể có một quyết định riêng |
| Subscription bị hủy | cancel() | Không còn cần xử lý; cần dọn upstream |

**Không nhầm Boolean false với publisher trống.** Một operator `filter(Boolean::booleanValue)` có thể biến `Mono.just(false)` thành `Mono.empty()` và làm biến mất thông tin deny. Nếu caller dùng `switchIfEmpty(Mono.just(true))`, lỗi đó có thể trở thành lỗ hổng.

### 2.1. API Spring Security 7.x cần biết

`ReactiveAuthorizationManager<T>` dùng các phương thức:

~~~java
Mono<AuthorizationResult> authorize(
        Mono<Authentication> authentication, T object);

Mono<Void> verify(
        Mono<Authentication> authentication, T object);
~~~

Đây là **chữ ký rút gọn từ Javadoc**, không phải class cần tự định nghĩa. `AuthorizationResult` cung cấp `isGranted()`; `AuthorizationDecision` là implementation phổ biến với constructor nhận `boolean`. `authorize` có thể trả decision hoặc empty nếu không quyết định được. `verify` hoàn tất khi được cấp quyền và phát lỗi `AccessDeniedException` khi từ chối.

Các tài liệu/version cũ có `check(Mono<Authentication>, T)` hoặc API đồng bộ `AuthorizationManager<T>` nhận `Supplier<Authentication>`. Với Spring Security 6.4+/7.x, khi viết code mới hãy dùng `authorize` và đúng interface reactive. Không copy nhầm `AuthorizationManager` của Servlet/method interceptor không reactive sang `ReactiveAuthorizationManager`.

### 2.2. Ba tầng có kết quả khác nhau

~~~text
manager.authorize(...):
  allow -> emit AuthorizationResult(true)
  deny  -> emit AuthorizationResult(false)
  empty -> emit no decision
  error -> emit error

manager.verify(...):
  allow -> Mono<Void> completes
  deny  -> emits AccessDeniedException

proxied @PreAuthorize Spring method:
  allow -> business Publisher executes
  deny  -> emits AccessDeniedException before business result
~~~

Vì vậy **test trực tiếp manager** nên kiểm `result.isGranted()`; **test verify/AOP** nên kiểm completion hoặc error. Không viết `expectError(...)` cho một `authorize` được thiết kế trả `AuthorizationDecision(false)`.

## 3. StepVerifier: viết một kịch bản theo tín hiệu thực tế

~~~java
// Snippets trong phương thức test với Spring Security và reactor-test imports.
Mono<AuthorizationResult> allow =
        Mono.just(new AuthorizationDecision(true));
StepVerifier.create(allow)
        .expectNextMatches(AuthorizationResult::isGranted)
        .verifyComplete();

Mono<AuthorizationResult> deny =
        Mono.just(new AuthorizationDecision(false));
StepVerifier.create(deny)
        .expectNextMatches(r -> !r.isGranted())
        .verifyComplete();

StepVerifier.create(Mono.<AuthorizationResult>empty())
        .verifyComplete();

StepVerifier.create(
        Mono.<AuthorizationResult>error(
                new AccessDeniedException("denied")))
        .expectError(AccessDeniedException.class)
        .verify();
~~~

Bốn kịch bản này **không giống nhau**. Trong test allow, `expectNextMatches(...)` buộc phải nhận một giá trị. Nếu thay bằng chỉ `verifyComplete()`, `Mono.empty()` cũng pass dù chưa hề cho phép truy cập.

### 3.1. Các phương thức nên dùng đúng ngữ nghĩa

| API | Đang xác minh |
| --- | --- |
| `StepVerifier.create(publisher)` | Kịch bản từ lúc subscribe |
| `expectSubscription()` | Phải có onSubscribe |
| `expectNext(value)` | Giá trị onNext đúng |
| `expectNextMatches(predicate)` | Predicate của một onNext đúng |
| `assertNext(consumer)` | Custom assertions cho object |
| `expectNextCount(n)` | Có n giá trị, chưa xét nội dung |
| `verifyComplete()` | Complete và không có tín hiệu trái kỳ vọng |
| `expectError(type).verify()` | Publisher phát lỗi kiểu yêu cầu |
| `expectErrorMatches(predicate).verify()` | Lỗi đúng nguyên nhân/type |
| `then(action)` | Phát tín hiệu test hoặc kiểm state tại bước cụ thể |
| `thenRequest(n)` | Tăng demand sau subscription |
| `thenCancel().verify()` | Test hủy subscription |
| `expectNoEvent(duration)` | Không có signal trong khoảng |
| `withVirtualTime(() -> publisher)` | Dùng virtual scheduler cho timed operators |
| `expectAccessibleContext()` | Reactor Context tồn tại và chứa thông tin mong muốn |
| `verifyThenAssertThat()` | Hậu kiểm state, dropped/discarded elements |
| `StepVerifierOptions.scenarioName(...)` | Đặt tên kịch bản giúp debug |

**Bắt buộc gọi** `verify()` hoặc shortcut có thực thi verification. Chỉ chain `expectNext(...)` mà không gọi verify **không subscribe** Publisher và không chứng minh test gì.

### 3.2. StepVerifier hoàn thành khác với authorize thành công

~~~java
// ANTI-PATTERN: nếu manager trả Mono.empty thì test vẫn xanh.
StepVerifier.create(manager.authorize(auth, resource))
        .verifyComplete();
~~~

Nếu mục tiêu là allow:

~~~java
StepVerifier.create(manager.authorize(auth, resource))
        .expectNextMatches(AuthorizationResult::isGranted)
        .verifyComplete();
~~~

Nếu mục tiêu là deny:

~~~java
StepVerifier.create(manager.authorize(auth, resource))
        .expectNextMatches(decision -> !decision.isGranted())
        .verifyComplete();
~~~

Nếu mục tiêu là **abstain** theo contract, `verifyComplete()` không có `expectNext` mới phù hợp. Trong compositional security policy, downstream phải biết cách xử lý abstain; đừng tự hiểu abstain là permit.

## 4. Bài toán kiểm thử: đọc báo cáo chỉ khi có scope và membership

Giả sử resource `ReportRequest(tenant, reportId)`. User phải:

1. Đã authenticated.
2. Có authority `SCOPE_reports.read`.
3. Có membership ở tenant của báo cáo, xác minh bằng reactive permission service.
4. Chỉ sau khi allow mới được **subscribe** publisher tải report.

Một nguồn membership có thể trả:

~~~text
membership.belongs("alice", "tenant-a"):
  Mono.just(true)   -> allow nếu scope đúng
  Mono.just(false)  -> deny
  Mono.empty()      -> deny by default theo policy ứng dụng
  Mono.error(...)   -> fail closed, không tải dữ liệu
  Mono.never()      -> timeout/cancel, không chờ vô hạn
~~~

Sơ đồ:

~~~text
HTTP / verified Authentication
       |
       v
ReactiveAuthorizationManager<ReportRequest>
       |   has SCOPE_reports.read ?
       +--- no -------> AuthorizationDecision(false)
       |
       +--- yes ------> membership.belongs(user, tenant)
                              |
                     true  / false / empty / error
                              |
                    allow / deny / deny / error
                              |
              +---------------+----------------+
              |                                |
            allow                        deny/error
              |                                |
              v                                v
    subscribe repository               NOT subscribe repository
    return sensitive body               emit error / translate status
~~~

Chỉ assert HTTP 403 mà không assert repository chưa được subscribe là thiếu. Repository có thể đã đọc/cached/logged private rows **trước** khi controller cuối cùng trả 403.

## 5. Maven project Java 17+ để học và tự chạy test

Cấu trúc:

~~~text
reactive-authz-test/
  pom.xml
  src/main/java/com/example/authz/ReportSecurity.java
  src/test/java/com/example/authz/ReportSecurityTest.java
~~~

Project dùng **Spring Boot 4.1.2** BOM để quản lý Spring Security/Reactor, **Java 17+**, JUnit Jupiter, `reactor-test` và không cần IdP/HTTP server. Các credentials trong unit test là **mock authentication**, không phải JWT thật. Project kiểm đúng Publisher và service composition; integration HTTP/Method Security ở phần sau.

### 5.1. pom.xml

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>4.1.2</version>
        <relativePath/>
    </parent>
    <groupId>com.example</groupId>
    <artifactId>reactive-authz-test</artifactId>
    <version>1.0.0</version>
    <properties>
        <java.version>17</java.version>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-security</artifactId>
        </dependency>
        <dependency>
            <groupId>io.projectreactor</groupId>
            <artifactId>reactor-core</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
        </dependency>
        <dependency>
            <groupId>io.projectreactor</groupId>
            <artifactId>reactor-test</artifactId>
            <scope>test</scope>
        </dependency>
    </dependencies>
</project>
~~~

`reactor-test` là dependency riêng phục vụ test, **không** nên đặt production runtime chỉ để tạo `StepVerifier`. Với Boot BOM, không tự ép Spring Security 5.x vào cùng project khi code đang dùng `AuthorizationResult` và `authorize` 7.x.

### 5.2. ReportSecurity.java — code ứng dụng

Tạo `src/main/java/com/example/authz/ReportSecurity.java`:

~~~java
package com.example.authz;

import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.authorization.AuthorizationDecision;
import org.springframework.security.authorization.AuthorizationResult;
import org.springframework.security.authorization.ReactiveAuthorizationManager;
import org.springframework.security.core.Authentication;
import reactor.core.publisher.Mono;

public final class ReportSecurity {

    private ReportSecurity() {}

    public record ReportRequest(String tenant, String reportId) {}

    @FunctionalInterface
    public interface Membership {
        Mono<Boolean> belongs(String userName, String tenant);
    }

    public static final class ReportAuthorizationManager
            implements ReactiveAuthorizationManager<ReportRequest> {

        private final Membership membership;

        public ReportAuthorizationManager(Membership membership) {
            this.membership = membership;
        }

        @Override
        public Mono<AuthorizationResult> authorize(
                Mono<Authentication> authentication,
                ReportRequest request) {

            return Mono.defer(() -> authentication
                    .filter(Authentication::isAuthenticated)
                    .flatMap(auth -> {
                        boolean hasScope = auth.getAuthorities()
                                .stream()
                                .anyMatch(a -> "SCOPE_reports.read"
                                        .equals(a.getAuthority()));
                        if (!hasScope) {
                            return Mono.just((AuthorizationResult)
                                    new AuthorizationDecision(false));
                        }
                        return membership
                                .belongs(auth.getName(), request.tenant())
                                // Missing membership -> explicit deny.
                                .defaultIfEmpty(false)
                                .map(value -> (AuthorizationResult)
                                        new AuthorizationDecision(value));
                    })
                    // Missing Authentication -> explicit deny.
                    .defaultIfEmpty(new AuthorizationDecision(false)));
        }
    }

    public static Mono<String> secureRead(
            Mono<Authentication> authentication,
            ReportRequest request,
            ReactiveAuthorizationManager<ReportRequest> manager,
            Mono<String> repository) {

        return Mono.defer(() -> manager
                .authorize(authentication, request)
                // An external manager may abstain.
                .defaultIfEmpty(new AuthorizationDecision(false))
                .flatMap(decision -> decision.isGranted()
                        ? repository
                        : Mono.error(new AccessDeniedException(
                                "Report access denied"))));
    }
}
~~~

**Lý do thiết kế:** khi scope thiếu, membership store **không được gọi**. Khi no Authentication hoặc no membership record, `defaultIfEmpty` tạo explicit deny. Khi membership service lỗi, publisher propagate error, không cấp quyền. Khi deny, `secureRead` không subscribe `repository`. `Mono.defer` làm rõ việc mỗi subscription mới kích hoạt authorize path.

**Giới hạn:** code không verify issuer/audience JWT và không kiểm object ownership; đó là trách nhiệm authentication/resource layer và business authorization thực tế. Membership store phải bảo vệ tenant và kiểm đúng user từ verified identity, không tin một giá trị HTTP `X-User-Id` chưa xác minh.

### 5.3. ReportSecurityTest.java — full JUnit class

Tạo `src/test/java/com/example/authz/ReportSecurityTest.java`:

~~~java
package com.example.authz;

import java.time.Duration;
import java.util.List;
import java.util.Set;
import java.util.concurrent.atomic.AtomicInteger;

import org.junit.jupiter.api.Test;
import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.authorization.AuthorizationResult;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.core.context.ReactiveSecurityContextHolder;
import org.springframework.security.core.context.SecurityContext;

import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;
import reactor.test.StepVerifierOptions;
import reactor.test.publisher.PublisherProbe;
import reactor.test.publisher.TestPublisher;
import reactor.util.context.Context;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static com.example.authz.ReportSecurity.*;

class ReportSecurityTest {

    private static final ReportRequest REQUEST =
            new ReportRequest("tenant-a", "report-7");

    private static Authentication auth(String name, String... scopes) {
        List<GrantedAuthority> authorities = Set.of(scopes)
                .stream()
                .map(SimpleGrantedAuthority::new)
                .map(a -> (GrantedAuthority) a)
                .toList();
        return UsernamePasswordAuthenticationToken.authenticated(
                name, "unused", authorities);
    }

    private static ReportAuthorizationManager manager(boolean allowed) {
        return new ReportAuthorizationManager(
                (name, tenant) -> Mono.just(allowed));
    }

    @Test
    void grantsWhenScopeAndMembershipMatch() {
        StepVerifier.create(manager(true).authorize(
                        Mono.just(auth("alice", "SCOPE_reports.read")),
                        REQUEST))
                .expectNextMatches(AuthorizationResult::isGranted)
                .verifyComplete();
    }

    @Test
    void deniesWhenMembershipIsFalse() {
        StepVerifier.create(manager(false).authorize(
                        Mono.just(auth("alice", "SCOPE_reports.read")),
                        REQUEST))
                .expectNextMatches(result -> !result.isGranted())
                .verifyComplete();
    }

    @Test
    void skipsMembershipLookupWhenScopeMissing() {
        AtomicInteger calls = new AtomicInteger();
        var manager = new ReportAuthorizationManager(
                (name, tenant) -> {
                    calls.incrementAndGet();
                    return Mono.just(true);
                });

        StepVerifier.create(manager.authorize(
                        Mono.just(auth("alice", "SCOPE_other")), REQUEST))
                .expectNextMatches(result -> !result.isGranted())
                .verifyComplete();

        assertEquals(0, calls.get());
    }

    @Test
    void missingAuthenticationIsDenied() {
        StepVerifier.create(
                        manager(true).authorize(Mono.empty(), REQUEST))
                .expectNextMatches(result -> !result.isGranted())
                .verifyComplete();
    }

    @Test
    void emptyMembershipMeansDeny() {
        var manager = new ReportAuthorizationManager(
                (name, tenant) -> Mono.empty());

        StepVerifier.create(manager.authorize(
                        Mono.just(auth("alice", "SCOPE_reports.read")),
                        REQUEST))
                .expectNextMatches(result -> !result.isGranted())
                .verifyComplete();
    }

    @Test
    void verifyCompletesOnAllow() {
        StepVerifier.create(manager(true).verify(
                        Mono.just(auth("alice", "SCOPE_reports.read")),
                        REQUEST))
                .verifyComplete();
    }

    @Test
    void verifyErrorsOnDeny() {
        StepVerifier.create(manager(false).verify(
                        Mono.just(auth("alice", "SCOPE_reports.read")),
                        REQUEST))
                .expectError(AccessDeniedException.class)
                .verify();
    }

    @Test
    void repositoryNotSubscribedAfterDeny() {
        PublisherProbe<String> repository =
                PublisherProbe.of(Mono.just("PRIVATE_REPORT"));

        StepVerifier.create(secureRead(
                        Mono.just(auth("alice", "SCOPE_reports.read")),
                        REQUEST,
                        manager(false),
                        repository.mono()))
                .expectError(AccessDeniedException.class)
                .verify();

        repository.assertWasNotSubscribed();
        repository.assertWasNotRequested();
    }

    @Test
    void repositorySubscribedOnlyWhenAllowed() {
        PublisherProbe<String> repository =
                PublisherProbe.of(Mono.just("SAFE_REPORT"));

        StepVerifier.create(secureRead(
                        Mono.just(auth("alice", "SCOPE_reports.read")),
                        REQUEST,
                        manager(true),
                        repository.mono()))
                .expectNext("SAFE_REPORT")
                .verifyComplete();

        repository.assertWasSubscribed();
        repository.assertWasRequested();
    }

    @Test
    void permissionStoreErrorFailsClosed() {
        var manager = new ReportAuthorizationManager(
                (name, tenant) -> Mono.error(
                        new IllegalStateException("permission store down")));
        PublisherProbe<String> repository =
                PublisherProbe.of(Mono.just("PRIVATE_REPORT"));

        StepVerifier.create(secureRead(
                        Mono.just(auth("alice", "SCOPE_reports.read")),
                        REQUEST, manager, repository.mono()))
                .expectErrorMatches(error ->
                        error instanceof IllegalStateException
                                && error.getMessage().contains("store down"))
                .verify();

        repository.assertWasNotSubscribed();
    }

    @Test
    void workStartsOnlyOnSubscription() {
        AtomicInteger count = new AtomicInteger();
        var manager = new ReportAuthorizationManager(
                (name, tenant) -> Mono.defer(() -> {
                    count.incrementAndGet();
                    return Mono.just(true);
                }));

        Mono<AuthorizationResult> publisher = manager.authorize(
                Mono.just(auth("alice", "SCOPE_reports.read")),
                REQUEST);

        assertEquals(0, count.get());

        StepVerifier.create(publisher)
                .expectNextMatches(AuthorizationResult::isGranted)
                .verifyComplete();

        assertEquals(1, count.get());
    }

    @Test
    void testPublisherControlsAsyncDenial() {
        TestPublisher<Boolean> permissions = TestPublisher.create();
        var manager = new ReportAuthorizationManager(
                (name, tenant) -> permissions.mono());

        StepVerifier.create(manager.authorize(
                        Mono.just(auth("alice", "SCOPE_reports.read")),
                        REQUEST))
                .then(() -> permissions.next(false).complete())
                .expectNextMatches(result -> !result.isGranted())
                .verifyComplete();

        permissions.assertWasSubscribed();
    }

    @Test
    void cancellationCancelsPendingPermissionCheck() {
        TestPublisher<Boolean> permissions = TestPublisher.create();
        var manager = new ReportAuthorizationManager(
                (name, tenant) -> permissions.mono());

        StepVerifier.create(manager.authorize(
                        Mono.just(auth("alice", "SCOPE_reports.read")),
                        REQUEST))
                .expectSubscription()
                .then(permissions::assertSubscribers)
                .thenCancel()
                .verify();

        permissions.assertCancelled();
    }

    @Test
    void reactiveSecurityContextHasSubscriberIdentity() {
        Authentication alice = auth("alice", "SCOPE_reports.read");
        Mono<String> name =
                ReactiveSecurityContextHolder.getContext()
                        .map(SecurityContext::getAuthentication)
                        .map(Authentication::getName);

        StepVerifier.create(name.contextWrite(
                        ReactiveSecurityContextHolder
                                .withAuthentication(alice)))
                .expectNext("alice")
                .verifyComplete();

        StepVerifier.create(name)
                .verifyComplete();
    }

    @Test
    void initialContextCanBeVerified() {
        Mono<String> trace = Mono.deferContextual(ctx ->
                Mono.just((String) ctx.get("traceId")));

        StepVerifier.create(trace,
                        StepVerifierOptions.create()
                                .withInitialContext(
                                        Context.of("traceId", "test-42")))
                .expectAccessibleContext()
                .contains("traceId", "test-42")
                .then()
                .expectNext("test-42")
                .verifyComplete();
    }

    @Test
    void virtualTimeTestsDelayedDecision() {
        StepVerifier.withVirtualTime(() ->
                        Mono.delay(Duration.ofMinutes(5))
                                .map(tick -> (AuthorizationResult)
                                        new org.springframework.security
                                                .authorization
                                                .AuthorizationDecision(false)))
                .expectSubscription()
                .expectNoEvent(Duration.ofMinutes(5))
                .expectNextMatches(result -> !result.isGranted())
                .verifyComplete();
    }
}
~~~

### 5.4. Chạy test và kỳ vọng

Trong thư mục project chứa `pom.xml`, dùng:

~~~bash
mvn test
~~~

Hoặc nếu có Maven wrapper đã được tạo:

~~~bash
./mvnw test
~~~

Maven sẽ chạy JUnit Jupiter tests. **Không khẳng định kết quả của quá trình build chưa thực hiện.** Log chi tiết của Surefire phụ thuộc JDK, Maven và plugin versions; đừng copy một mẫu stdout “BUILD SUCCESS” giả rồi coi là bằng chứng.

Khi test fail, đọc **expected signal vs actual signal**. Nếu allow test nhận `onComplete` mà không có `onNext`, nguyên nhân có thể là manager trả `Mono.empty()`, không phải cứ nới test thành `verifyComplete()`. Nếu deny test nhận `onError` thay vì `AuthorizationDecision(false)`, phải xác định test đang gọi `authorize`, `verify` hay intercepted method.

## 6. Những assertion bảo mật quan trọng trong project

### 6.1. Allow cần result true, không chỉ complete

~~~java
StepVerifier.create(manager.authorize(auth, REQUEST))
        .expectNextMatches(AuthorizationResult::isGranted)
        .verifyComplete();
~~~

Nếu publisher trống, test này fail. Đó là lý do khác biệt với test `verifyComplete()` một mình.

### 6.2. Deny trước mọi side effect

~~~java
PublisherProbe<String> repository =
        PublisherProbe.of(Mono.just("SECRET"));

StepVerifier.create(
        ReportSecurity.secureRead(
                authentication, REQUEST, denyManager,
                repository.mono()))
        .expectError(AccessDeniedException.class)
        .verify();

repository.assertWasNotSubscribed();
~~~

**PublisherProbe** ghi nhận whether source được subscribe/request/cancel. Nó không tự biết việc dữ liệu đã bị đọc trong constructor eager hay không; phải kiểm repository adapter thật sử dụng lazy/reactive API.

### 6.3. Một lời gọi method chưa làm chạy Mono

~~~java
Mono<AuthorizationResult> decision =
        manager.authorize(authentication, REQUEST);

// Không có nghĩa permission database đã được query.
// Subscription mới thúc đẩy thực thi:
StepVerifier.create(decision)
        .expectNextMatches(AuthorizationResult::isGranted)
        .verifyComplete();
~~~

Nếu một developer thay `Mono.defer` thành eager `Mono.just(expensiveLoad())`, side effect có thể chạy **trước** StepVerifier. Test laziness và probe giúp phát hiện rủi ro.

### 6.4. Error không được biến thành allow

~~~java
// ANTI-PATTERN:
return membershipStore.belongs(user, tenant)
        .onErrorReturn(true);
~~~

Tạo quyền mới khi permission store unavailable là fail-open. Tốt hơn là propagate lỗi để ứng dụng từ chối phát dữ liệu, rồi map HTTP status đúng (có thể 5xx đối với outage hạ tầng). Đừng báo nhầm lỗi hạ tầng là “token hết hạn”.

### 6.5. Missing Authentication và missing membership

`Mono.empty()` từ source authentication có thể có nghĩa chưa đăng nhập hoặc component không quyết định được; trong **policy mẫu** phải deny. `Mono.empty()` từ membership store có nghĩa không tìm thấy record, cũng deny. Không tự suy luận mọi implementation của `ReactiveAuthorizationManager` có cùng fallback: composite manager có semantics “abstain” riêng, phải test ở tầng tổng hợp.

## 7. Test PublisherProbe cho nhánh fallback và resource cleanup

Một số publisher trả `Mono<Void>` nên không có `onNext` để phân biệt nó đã chạy. `PublisherProbe.empty()` giúp kiểm có subscribe:

~~~java
PublisherProbe<Void> auditProbe = PublisherProbe.empty();

Mono<Void> result = Mono.<Void>empty()
        .switchIfEmpty(auditProbe.mono());

StepVerifier.create(result)
        .verifyComplete();

auditProbe.assertWasSubscribed();
auditProbe.assertWasRequested();
~~~

Ở code trên, `Mono.<Void>empty()` là source nên `switchIfEmpty` chuyển sang auditProbe. Nhưng khi kiểm security workflow, hãy cẩn thận: fallback khi no-decision **không được tự động thực hiện protected action**. Use probe cho expected cleanup/audit branches, không để nó trở thành bypass rule.

### 7.1. Eager side effect lọt ngoài PublisherProbe

~~~java
// Sai: expensiveRead() chạy ngay trước khi authorize.
Mono<String> result = Mono.just(expensiveRead());
return secureRead(auth, REQUEST, manager, result);
~~~

Với source I/O blocking, đây còn làm chặn Netty nếu tạo trong controller. Đúng hơn dùng adapter reactive và defer side effects:

~~~java
Mono<String> result =
        Mono.defer(() -> reactiveRepository.readReport("report-7"));
return secureRead(auth, REQUEST, manager, result);
~~~

Đây là snippet khi có `reactiveRepository`; không phải file runnable riêng. `PublisherProbe.assertWasNotSubscribed()` + spy repository cùng kiểm được **không có data access trước decision**.

### 7.2. When denied vs when permission store errors

| Case | Manager | Repository |
| --- | --- | --- |
| membership false | Emit `AuthorizationDecision(false)` | Không subscribe |
| membership empty | Explicit deny ở app mẫu | Không subscribe |
| membership error | OnError, không allow | Không subscribe |
| authentication empty | Deny ở app mẫu | Không subscribe |
| scope missing | Deny, membership không gọi | Không subscribe |
| member true/scope valid | Grant true | Subscribe một lần nếu không retry |

Khi backend cần transaction, hãy đảm bảo transaction mở **sau** authorization hoặc được rollback khi deny, không để sensitive data bị ghi vào cache/log trước khi check.

## 8. TestPublisher: điều khiển race, error và cancellation

`TestPublisher<T>` là test source có thể phát `next(...)`, `complete()`, `error(ex)` bằng tay, kèm `assertSubscribers`/`assertCancelled`. Nó phù hợp khi permission store chưa phản hồi và bạn muốn điều khiển đúng thời điểm.

~~~java
TestPublisher<Boolean> permissions = TestPublisher.create();

Mono<AuthorizationResult> decision =
        new ReportAuthorizationManager(
                (user, tenant) -> permissions.mono())
                .authorize(authentication, REQUEST);

StepVerifier.create(decision)
        .then(() -> permissions.next(false).complete())
        .expectNextMatches(r -> !r.isGranted())
        .verifyComplete();

permissions.assertWasSubscribed();
~~~

### 8.1. Vì sao phát signal trong then(...)?

`TestPublisher.create()` thường là **hot**. Nếu gọi `permissions.next(false)` **trước** khi `StepVerifier` subscribe vào source, event có thể không tới subscriber, dẫn đến test bị treo hoặc empty. Đặt `then(...)` sau khi StepVerifier bắt đầu subscription.

### 8.2. Cancellation khi permission chưa trả về

~~~java
TestPublisher<Boolean> permissions = TestPublisher.create();

StepVerifier.create(
        new ReportAuthorizationManager(
                (user, tenant) -> permissions.mono())
            .authorize(authentication, REQUEST))
        .expectSubscription()
        .then(permissions::assertSubscribers)
        .thenCancel()
        .verify();

permissions.assertCancelled();
~~~

Khi HTTP client disconnect, pending permission query không nên giữ mãi resources. Test cancellation ở source chưa đủ để chứng minh DB driver/SDK cleanup đúng; integration test phải kiểm connection/listener/transaction thực.

### 8.3. Lỗi mạng có phải deny result không?

Nếu backend policy service trả `Mono.error(new TimeoutException(...))`, manager có thể emit error chứ không phải `AuthorizationDecision(false)`. Trong thiết kế fail closed, **không phát protected data**. API layer có thể map outage thành 503/500 (và alert) thay vì che thành 401/403; quyết định status tùy contract, không đồng nghĩa grant.

### 8.4. Noncompliant TestPublisher

`TestPublisher.createNoncompliant(...)` tạo publisher cố tình vi phạm Reactive Streams để thử operator adapter khi nhận source không chuẩn. Chỉ sử dụng cho test resilience chuyên biệt; đừng lấy việc một stream noncompliant phát nhiều onNext làm contract bình thường của `Mono<AuthorizationResult>`.

## 9. ReactiveSecurityContextHolder và StepVerifier

Trong Spring Security reactive, danh tính đi theo **Reactor Context**, không phải một `ThreadLocal` toàn cục. Khi test unit logic đọc principal:

~~~java
Authentication alice =
        UsernamePasswordAuthenticationToken.authenticated(
                "alice", "unused",
                List.of(new SimpleGrantedAuthority(
                        "SCOPE_reports.read")));

Mono<String> name = ReactiveSecurityContextHolder.getContext()
        .map(SecurityContext::getAuthentication)
        .map(Authentication::getName);

StepVerifier.create(name.contextWrite(
        ReactiveSecurityContextHolder.withAuthentication(alice)))
        .expectNext("alice")
        .verifyComplete();
~~~

Đây là snippet trong test với imports phù hợp. Nếu không `contextWrite(...)` trong đơn vị test trần, `getContext()` có thể không có security context. Spring WebFlux Security filter tự thiết lập context cho authenticated HTTP subscription; unit test ngoài HTTP phải chủ động tạo bối cảnh.

### 9.1. Kiểm hai subscriber không lẫn user

~~~java
Mono<String> who = ReactiveSecurityContextHolder.getContext()
        .map(SecurityContext::getAuthentication)
        .map(Authentication::getName);

StepVerifier.create(who.contextWrite(
        ReactiveSecurityContextHolder.withAuthentication(alice)))
        .expectNext("alice")
        .verifyComplete();

StepVerifier.create(who.contextWrite(
        ReactiveSecurityContextHolder.withAuthentication(bob)))
        .expectNext("bob")
        .verifyComplete();
~~~

Nếu một service lưu user vào static field, một request có thể ghi đè request khác. Test hai subscribers baseline như trên, bổ sung concurrent test khi có scheduler transitions/external callbacks. Không kết luận `publishOn` tự làm mất Reactor Context: trong một Reactor pipeline chuẩn, Context theo subscriber; rủi ro thường là **tách subscription** bằng `subscribe()` tự phát hoặc code ngoài Reactor không truyền context.

### 9.2. StepVerifierOptions và expectAccessibleContext

~~~java
Mono<String> trace = Mono.deferContextual(ctx ->
        Mono.just((String) ctx.get("traceId")));

StepVerifier.create(trace,
                StepVerifierOptions.create()
                        .scenarioName("reactor-context")
                        .withInitialContext(
                                Context.of("traceId", "test-42")))
        .expectAccessibleContext()
        .contains("traceId", "test-42")
        .then()
        .expectNext("test-42")
        .verifyComplete();
~~~

`expectAccessibleContext()` chứng minh context propagation, **không chứng minh tenant/issuer đã được verify**. Một giá trị `tenant-a` do client tự đưa vào context vẫn là untrusted nếu application chưa xác thực membership hoặc token.

### 9.3. @WithMockUser và reactive method security

`@WithMockUser` của Spring Security Test có thể tạo SecurityContext trong tests có Spring test integration. Với **reactive method security**, tài liệu Spring Security nhắc tới `ReactorContextTestExecutionListener` để tạo `ReactiveSecurityContextHolder` đúng cách. Một JUnit test trần chỉ gắn annotation nhưng không có listener/Context phù hợp có thể không thấy Authentication trong reactive pipeline.

Với unit tests, explicit `contextWrite(...)` là dễ hiểu. Với integration test AOP/WebFlux, cấu hình đúng Spring Security Test, tránh trộn `SecurityContextHolder` Servlet ThreadLocal với Reactor Context.

## 10. Method security @PreAuthorize phải kiểm qua Spring proxy

Spring Security reactive hỗ trợ `@EnableReactiveMethodSecurity` và `@PreAuthorize` trên method trả `Mono`/`Flux`. Ví dụ:

~~~java
@Configuration
@EnableReactiveMethodSecurity
class MethodSecurityConfig {
}

@Service
class ReportsService {

    @PreAuthorize("hasAuthority('SCOPE_reports.read')")
    public Mono<String> read() {
        return Mono.just("SAFE_REPORT");
    }
}
~~~

Đây là **snippet trong Spring application**, cần các imports và dependencies AOP/method-security đúng. Điều cần test không phải gọi `new ReportsService().read()`, mà là gọi **bean proxy được Spring inject**.

~~~java
Mono<String> allowed = reportsService.read().contextWrite(
        ReactiveSecurityContextHolder.withAuthentication(reader));

StepVerifier.create(allowed)
        .expectNext("SAFE_REPORT")
        .verifyComplete();

Mono<String> denied = reportsService.read().contextWrite(
        ReactiveSecurityContextHolder.withAuthentication(noScopeUser));

StepVerifier.create(denied)
        .expectError(AccessDeniedException.class)
        .verify();
~~~

**Khác biệt:** `@PreAuthorize` deny thường phát **AccessDeniedException** từ interceptor. Unit test `manager.authorize` deny trong project của bài chỉ trả decision false. Bạn phải kiểm đúng layer.

### 10.1. Self-invocation bypass

Nếu bean A gọi `this.securedMethod()` nội bộ, Spring AOP proxy có thể không intercept call đó. Một test trực tiếp vào proxy method đã đúng chưa chứng minh đường self-invocation. Khi thực tế có các method gọi nhau, hãy test HTTP/service call graph hoặc tách secured method sang bean khác. Không dùng `@PreAuthorize` như một annotation trang trí rồi bỏ kiểm AOP route.

### 10.2. Policy trả Mono<Boolean> trong SpEL

Spring Security hỗ trợ authorization bean được tham chiếu bằng SpEL, có thể trả `Mono<Boolean>`:

~~~java
@PreAuthorize("@reportPolicy.allowed(#tenant)")
public Mono<String> readForTenant(String tenant) {
    return reactiveRepository.readForTenant(tenant);
}
~~~

`reportPolicy.allowed(...)` là method custom do ứng dụng cung cấp. Khi test, kiểm policy publisher trả true/false/empty/error và kiểm AOP proxy xử lý. Tài liệu Spring Security hiện hành nói empty có thể biểu thị abstain ở custom authorization logic; **không dựa vào empty để được phép**. Với các rule kinh doanh nhạy cảm, fail closed rõ ràng.

## 11. Virtual time cho timeout và quyết định đến muộn

### 11.1. withVirtualTime cần dựng Publisher trong Supplier

~~~java
StepVerifier.withVirtualTime(() ->
        Mono.delay(Duration.ofMinutes(5))
                .map(tick -> new AuthorizationDecision(false)))
        .expectSubscription()
        .expectNoEvent(Duration.ofMinutes(5))
        .expectNextMatches(result -> !result.isGranted())
        .verifyComplete();
~~~

`withVirtualTime` thay scheduler của Reactor timed operators để không chờ 5 phút thực. Lambda phải **tạo source sau khi virtual scheduler được kích hoạt**. Anti-pattern:

~~~java
// Source created too early; virtual scheduler may not be used.
Mono<Long> delayed = Mono.delay(Duration.ofMinutes(5));
StepVerifier.withVirtualTime(() -> delayed)
        .thenAwait(Duration.ofMinutes(5))
        .expectNext(0L)
        .verifyComplete();
~~~

Trong trường hợp này source có thể giữ scheduler thật, khiến test chờ lâu hoặc treo. Luôn tạo source timed bên trong Supplier và tránh trộn scheduler riêng không điều khiển.

### 11.2. expectNoEvent tính cả subscription

`expectNoEvent(Duration)` kiểm không có signal trong khoảng. `onSubscribe` cũng được tính là một signal, do đó:

~~~java
StepVerifier.withVirtualTime(() ->
        Mono.delay(Duration.ofSeconds(30)))
        .expectSubscription()
        .expectNoEvent(Duration.ofSeconds(30))
        .expectNext(0L)
        .verifyComplete();
~~~

Đặt `expectSubscription()` trước khi đòi không có event.

### 11.3. VirtualTimeScheduler không đổi Clock của JVM

Nếu code expiry có `Instant.now()`, tiến virtual scheduler không làm đồng hồ JVM tự nhảy. Khi test JWT `exp` hoặc stream lease, inject `Clock`:

~~~java
Instant expiration = Instant.parse("2026-11-07T00:00:10Z");
Clock clock = Clock.fixed(
        Instant.parse("2026-11-07T00:00:11Z"), ZoneOffset.UTC);
boolean expired = !Instant.now(clock).isBefore(expiration);
~~~

Đây là snippet yêu cầu `java.time.Clock/Instant/ZoneOffset` imports. Virtual time điều khiển `Mono.delay`/`Flux.interval`; Clock điều khiển **policy wall time**. Có thể cần cả hai để test expiry mà không phụ thuộc tốc độ máy CI.

### 11.4. Chặn permission check vô hạn

~~~java
Mono<AuthorizationResult> bounded =
        manager.authorize(authentication, request)
                .timeout(Duration.ofSeconds(2));
~~~

Nếu check không hoàn thành, publisher lỗi timeout. Không dùng `onErrorResume(ex -> Mono.just(new AuthorizationDecision(true)))`, vì đó là fail-open. Tầng HTTP nên đặt deadline/circuit breaker và trạng thái lỗi hạ tầng phù hợp. Nếu test timeout trên virtual scheduler, phải bảo đảm toàn bộ operators liên quan dùng scheduler được inject.

## 12. Cancellation và backpressure

### 12.1. thenCancel để test source không hoàn tất

~~~java
TestPublisher<Boolean> pending = TestPublisher.create();

StepVerifier.create(pending.mono())
        .expectSubscription()
        .thenCancel()
        .verify();

pending.assertCancelled();
~~~

Cancellation **không phải** onError hoặc onComplete. Nếu pending query đã được đẩy vào SDK bên ngoài, test phải kiểm SDK/resource được dọn khi cancel; operator `doFinally(SignalType.CANCEL)` hoặc `usingWhen` có thể hỗ trợ cleanup.

### 12.2. Kiểm request(n) theo demand

~~~java
StepVerifier.create(
                Flux.just("grant-a", "grant-b"),
                StepVerifierOptions.create().initialRequest(0))
        .expectSubscription()
        .thenRequest(1)
        .expectNext("grant-a")
        .thenRequest(1)
        .expectNext("grant-b")
        .verifyComplete();
~~~

Publisher không nên phát `onNext` khi downstream chưa request. Một authorization per-item `Flux` có thể được chạy khi streaming; cần test backpressure nếu permission check phối hợp với broker data, tránh buffers không giới hạn và event cross-tenant.

### 12.3. Quyết định theo từng event/resource

~~~java
Flux<Event> secured = events.concatMap(event ->
        policy.canRead(user, tenant, event.resourceId())
                .flatMap(allowed ->
                        allowed ? Mono.just(event)
                                : Mono.error(
                                        new AccessDeniedException(
                                                "access revoked"))));
~~~

Đây là **snippet kiến trúc**, `events`, `policy`, `Event` và user/tenant chưa được khai báo. Nó minh họa mỗi event phải được authorize trước khi emit. `concatMap` giữ thứ tự nhưng có thể làm throughput bị giới hạn bởi policy service. Nếu policy service error, không cho phép phát event sau đó. Nếu response SSE đã commit HTTP 200, không thể sửa thành 403; cần kết thúc/đóng stream theo protocol và reconnect có auth mới.

### 12.4. Cancellation và onComplete phụ thuộc vị trí operator

`Flux.take(2)` sẽ hoàn thành **downstream** sau hai giá trị, nhưng có thể cancel upstream. Nếu `doFinally` đặt **trước** take, upstream quan sát `CANCEL`; nếu đặt **sau**, outer subscriber thường quan sát `ON_COMPLETE`. Đặt test assertion ở đúng publisher boundary, đừng coi mọi complete là “client hủy”.

## 13. WebTestClient và JWT: đừng dùng một test thay cả hệ thống

`StepVerifier` kiểm Publisher; `WebTestClient` kiểm HTTP/WebFlux Security chain:

| Tầng test | Điều được chứng minh |
| --- | --- |
| Unit manager | Grant/deny/empty/error/timeout/laziness |
| Service composition | Không subscribe repository trước allow |
| Spring AOP method security | `@PreAuthorize` thật sự intercept bean proxy |
| WebFlux + WebTestClient | HTTP 401/403, route rules và response mapping |
| JWT integration | Chữ ký, issuer, audience, expiry/JWKS thật hoặc test keys |
| DB/business isolation | Dữ liệu trả về thực sự theo đúng tenant/user ownership |

Một snippet WebFlux:

~~~java
// Test snippet trong project có WebTestClient và Spring Security Test.
webTestClient.mutateWith(mockJwt()
        .authorities(new SimpleGrantedAuthority(
                "SCOPE_reports.read")))
        .get().uri("/api/reports/report-7")
        .exchange()
        .expectStatus().isOk();

webTestClient.mutateWith(mockJwt()
        .authorities(new SimpleGrantedAuthority(
                "SCOPE_other")))
        .get().uri("/api/reports/report-7")
        .exchange()
        .expectStatus().isForbidden();
~~~

`mockJwt()` tạo JWT/Authentication giả để test authorization. Nó **không** chứng minh JWT signature/issuer/audience/JWK Set đã được verify. Với resource server thật, phải kiểm JWT ký bằng private key test và decoder validator tương thích hoặc một fake IdP/JWKS controlled endpoint.

### 13.1. HTTP status và security signals

- Thiếu/invalid Bearer authentication: thường HTTP **401**.
- Authenticated nhưng scope không đủ: thường HTTP **403**.
- Custom manager trả false rồi service phát `AccessDeniedException`: thường HTTP 403 trong WebFlux security handler phù hợp.
- Permission database timeout/connection failure: lỗi hạ tầng, có thể HTTP **5xx**; vẫn phải fail closed.
- `Mono.empty()` trong controller/business có thể thành HTTP 200 với body trống hoặc 404 theo handler. Đừng để **no decision** vô tình biến thành success response.

### 13.2. @WithMockUser không tự thay Reactor Context trong mọi test

Spring Security Test hỗ trợ `@WithMockUser` với các test listeners. Với **reactive method security**, cần context support phù hợp (`ReactorContextTestExecutionListener`). Trong unit test không có Spring context, dùng `ReactiveSecurityContextHolder.withAuthentication` là tường minh hơn.

### 13.3. Đừng block trên Netty event loop

`StepVerifier` được dùng trong **test code**. Không đem `policy.canRead(...).block()` vào production security manager; nó có thể gây deadlock/latency và phá reactive chain. Nếu một repository là blocking JDBC, dùng adapter/scheduler được thiết kế riêng hoặc chuyển sang reactive driver; không gọi blocking code trong `flatMap` chạy trên event loop.

## 14. Debug test fail: nắm expected và actual signals

Một số tình huống thường gặp:

| Expected | Actual | Nguyên nhân cần điều tra |
| --- | --- | --- |
| `expectNextMatches(true)` | onComplete không value | `Mono.empty()`, filter bỏ false, thiếu Authentication |
| `expectNextMatches(false)` | onError | Test nhầm `verify`/interceptor thay vì `authorize` hoặc policy source lỗi |
| `expectError(AccessDeniedException)` | onNext(report) | Bypass policy, fail-open, AOP proxy không chạy |
| `expectError(AccessDeniedException)` | onError(NullPointerException) | Bug trong test/implementation, không phải denied chuẩn |
| `verifyComplete()` | Chờ mãi | `Mono.never()`, pending source, timeout thiếu, virtual clock chưa advance |
| PublisherProbe not subscribed | Có subscribe | Protected repository bị bắt đầu trước allow |
| TestPublisher no subscribers | Test expected subscription | Publisher chưa subscribe, hot event gửi quá sớm |
| Context expected user alice | empty hoặc bob | Sai `contextWrite`, tách subscription, state mutable global |
| withVirtualTime timeout | Time không tiến | Publisher tạo trước virtual scheduler hoặc scheduler riêng |
| StepVerifier cancellation expected | Source vẫn running | Adapter không xử lý cancel; có subscribe tách riêng |
| Test expected 403 | HTTP 401 | Authentication chưa pass, không đến authorization |
| Test expected 401 | HTTP 403 | Token đã authenticated nhưng thiếu authority |
| `mockJwt()` success | Real JWT fails | Missing audience/issuer/keys/expiry; test mocks không verify cryptography |

### 14.1. scenarioName và as

~~~java
StepVerifier.create(decision,
                StepVerifierOptions.create()
                        .scenarioName("tenant-a / report-read / deny"))
        .expectNextMatches(result -> !result.isGranted())
        .as("explicit denial expected")
        .verifyComplete();
~~~

Tên scenario nên dùng **fixture ID giả**, không ghi bearer token, email, raw user subject hoặc báo cáo nhạy cảm vào assertion messages/log.

### 14.2. verifyThenAssertThat

~~~java
StepVerifier.create(Flux.just(1, 2).take(1))
        .expectNext(1)
        .expectComplete()
        .verifyThenAssertThat();
~~~

Đoạn này minh họa post-verification API. Các assertions tiếp theo trên object trả về có thể kiểm dropped/discarded items khi operator có hành vi đó. Tuy nhiên `verifyThenAssertThat` **không tự** chứng minh dữ liệu không đến repository/cache/log; phải có PublisherProbe/spy và kiểm side effects.

### 14.3. Timeout test hợp lý

Mặc định `verify()` và `verifyComplete()` có thể chờ vô hạn nếu không cấu hình timeout. Với Publisher không complete:

~~~java
StepVerifier.create(Mono.never())
        .expectSubscription()
        .thenCancel()
        .verify(Duration.ofSeconds(3));
~~~

Test trên cancel và verify, không chờ complete. `StepVerifier.setDefaultTimeout(...)` thay global config, có thể ảnh hưởng parallel tests, nên ưu tiên timeout từng kịch bản khi có thể.

## 15. Các rủi ro với ReactiveAuthorizationManager custom

### 15.1. Error từ permission service không phải permission denied

Một lỗi mạng và một quyết định false có semantics khác nhau. API có thể map false thành 403, còn lỗi hạ tầng thành 503; cả hai đều **không được trả private data**. Dùng metrics khác nhau cho `authorization.denied` và `authorization.backend.error`; không log claims/token.

### 15.2. Cần bảo vệ decision caching

Một `Mono<AuthorizationResult>.cache()` được tái sử dụng toàn cục có thể cấp allow của user A cho user B. Nếu cache permissions, key phải bao gồm verified issuer/subject/tenant/resource/action, TTL và invalidation khi thu hồi quyền. Không cache allow vô hạn, đặc biệt với multi-tenant và streaming.

### 15.3. Retry có thể nhân số permission lookups

`retryWhen` resubscribe source. Nếu permission store lỗi rồi retry vô hạn, hệ thống có thể tạo bão queries; nếu policy thay đổi giữa các lần retry, kết quả càng khó dự đoán. Dùng deadline, retry budget khi transient và fail closed. Không replay business request có side effect chỉ vì authorization service timeout.

### 15.4. Self-invocation và eager publisher

Proxy security có thể bị bypass qua `this.method()`, trong khi eager `Mono.just(expensiveCall())` có thể chạy side effect trước khi interceptor quyết định. Test method invocation thực qua Spring bean + kiểm laziness trên adapter, không chỉ đơn vị policy.

### 15.5. Dynamic authorization cho Flux dài hạn

Một lần allow khi subscribe không tự bảo đảm user còn quyền sau đó. Nếu user bị revoke, phải kiểm entitlement theo sự kiện/chu kỳ hoặc kết thúc stream tại lease/expiry; thử bằng `TestPublisher`/virtual time để mô phỏng revoke giữa các events. Nếu bất kỳ một event cross-tenant lọt qua trước check, test cần fail.

## 16. Ma trận kiểm thử nên có

| Scenario | Manager / Publisher | Assertion then |
| --- | --- | --- |
| Có auth, đúng scope và membership | Emit granted=true | Repository subscribed |
| Thiếu scope | Emit granted=false | Membership không gọi, repository không subscribe |
| Membership false | Emit false | Denied path |
| Membership empty | Theo app mẫu false | Không tự allow |
| Authentication empty | Theo app mẫu false | Không dựa vào empty |
| Membership throws error | onError | Không subscribe sensitive data |
| `verify` allowed | Mono<Void> complete | Có thể tiếp tục business |
| `verify` denied | AccessDeniedException | Business bị chặn |
| @PreAuthorize allowed | Business Mono emit | Qua injected proxy |
| @PreAuthorize denied | AccessDeniedException | Không business result |
| Client cancel trong lúc query | cancel | Upstream cleanup |
| Policy timeout | onError(timeout) | Fail closed |
| 2 user Reactor Context | Hai identity riêng | Không leak qua subscriptions |
| Per-event revoke | Denied/error/complete | Không emit sensitive event sau revoke |
| Source no demand | Không có onNext trước request(n) | Backpressure giữ được |
| JWT invalid issuer/aud/signature | HTTP 401 | Decoder reject |
| JWT valid, sai scope | HTTP 403 | Route deny |
| WebTestClient mockJwt pass | Chỉ authorization pass | Không suy thật sự verify JWT |
| Repository eager call trước allow | Test phải fail | Refactor defer/reactive source |
| Re-subscribe policy Mono | Multiple checks nếu không cache | Kiểm concurrency/rate limits |

## 17. Lỗi phổ biến

1. Chỉ dùng `verifyComplete()` để kiểm “allow” dù publisher có thể `Mono.empty()`.
2. Đòi `expectError` ở một `authorize` có contract trả `AuthorizationDecision(false)`.
3. Nhầm `verify` returns `Mono<Void>` với `authorize` returns decision object.
4. Không gọi `verify()`, nên StepVerifier chưa thực hiện subscription.
5. Cho phép vì publisher empty/abstain mà không có explicit composition policy.
6. Dùng `onErrorReturn(true)` khi permission store lỗi: fail-open.
7. Không kiểm repository chưa được subscribe trước deny.
8. Truy vấn dữ liệu eager bằng `Mono.just(expensiveRead())` trước authorization.
9. Lấy principal từ `SecurityContextHolder` ThreadLocal thay vì Reactor Context.
10. Tin `@WithMockUser` hoạt động trong mọi reactive unit test không có test listener.
11. Test `@PreAuthorize` bằng `new Service()` bypass Spring proxy.
12. Đọc JWT claims trong `mockJwt` test rồi coi là test signature/JWKS.
13. Dựng `Mono.delay` trước `withVirtualTime` làm virtual time không tác dụng.
14. Cho rằng virtual scheduler thay `Instant.now()`; phải dùng injectable `Clock`.
15. Gọi `expectNoEvent` trước `expectSubscription`.
16. Phát TestPublisher signal trước khi subscriber sẵn sàng.
17. Nhầm cancel với complete/error trong `doFinally`.
18. Bỏ timeout nên test infinite/pending Publisher treo CI.
19. Dùng unbounded `Flux.onBackpressureBuffer()` cho permission/event stream.
20. Cache authorization decision không xét tenant/user/resource/expiry.
21. Chỉ assert HTTP 403 mà không đo data side effects.
22. Retry authorization lỗi vô hạn và tự tạo request storm.
23. Phát event ra client trước khi per-item policy Mono hoàn thành.
24. Dùng raw bearer/subject/PII trong tên scenario/log/probe.
25. Không test real path qua Spring AOP/HTTP/token validation/data ownership.

## 18. Checklist áp dụng ở dự án

1. Ghi rõ API version và contract Publisher của từng lớp security.
2. Kiểm all five signal classes: value granted, value denied, empty, error, cancel.
3. Mọi allow test cần assert onNext granted, không chỉ onComplete.
4. Mọi deny phải chứng minh protected Publisher không được subscribe.
5. Một permission database error luôn fail closed.
6. Mọi membership/tenant lookups lấy user từ verified identity.
7. Có test laziness trước subscribe.
8. Có TestPublisher test pending result, cancellation và permission store failure.
9. Có StepVerifierOptions/contextWrite test principal đúng subscriber.
10. Có withVirtualTime + Clock test timeout và expiry nếu dùng.
11. Test backpressure và bounded resources nếu có Flux dài hạn.
12. Test `@PreAuthorize` trên Spring-managed proxy và self-invocation path.
13. Test WebFlux HTTP 401/403 bằng WebTestClient.
14. Test JWT cryptography/issuer/audience riêng, không chỉ mockJwt.
15. Test ownership/tenant isolation ở repository thực.
16. Đặt timeout cho tests có khả năng never complete.
17. Không dùng blocking I/O trong reactive authorization flow.
18. Không cache global allow results vượt permission TTL/revocation policy.
19. Có observability cho denied/error/cancel khác nhau, không log tokens.
20. Chạy Maven tests trong CI và kiểm báo cáo Surefire thật.

## 19. Câu hỏi tự kiểm tra

**Câu 1.** Vì sao `StepVerifier.create(Mono.empty()).verifyComplete()` không chứng minh đã cho phép?

**Đáp án:** Vì publisher chỉ complete, không phát quyết định `AuthorizationResult(true)`.

**Câu 2.** `ReactiveAuthorizationManager.authorize` trả gì khi deny?

**Đáp án:** Có thể emit `AuthorizationResult(false)` rồi complete; không nhất thiết onError.

**Câu 3.** `verify` khi deny thường cho tín hiệu nào?

**Đáp án:** `onError(AccessDeniedException)`, không có onNext.

**Câu 4.** Tại sao cần PublisherProbe khi kiểm quyền đọc private report?

**Đáp án:** Để chứng minh repository Publisher chưa được subscribe/request khi deny/error.

**Câu 5.** Membership database lỗi có được chuyển `Mono.error` thành `true` để giữ availability không?

**Đáp án:** Không. Đó là fail-open, có thể cấp quyền trái phép.

**Câu 6.** TestPublisher.next(false) nên phát vào lúc nào?

**Đáp án:** Sau khi StepVerifier đã subscribe, thường trong callback `then(...)`.

**Câu 7.** Vì sao test @PreAuthorize cần Spring bean proxy?

**Đáp án:** Interception dựa vào AOP, `new Service()` và self-invocation có thể bypass.

**Câu 8.** `withVirtualTime` có thay `Instant.now()` không?

**Đáp án:** Không. Cần injectable Clock cho security wall time.

**Câu 9.** `mockJwt()` chứng minh điều gì?

**Đáp án:** Kiểm authorization với mock JWT/Authentication, không chứng minh signature/issuer/audience thật.

**Câu 10.** Test HTTP 403 pass nhưng repository đã query dữ liệu trước khi deny, có an toàn không?

**Đáp án:** Chưa. Phải kiểm thứ tự subscription và side effects tại service/data boundary.

**Câu 11.** Nếu permission publisher `Mono.never()`, cần gì?

**Đáp án:** Timeout/deadline và cancellation, không chờ vô hạn hoặc tự cấp quyền.

**Câu 12.** Vì sao authorization quyết định trên Flux stream cần kiểm lại theo event?

**Đáp án:** Quyền/tenant/object có thể khác nhau giữa các events hoặc bị thu hồi sau initial subscription; phải áp policy theo SLA.

## 20. Tài liệu chính thức

- [Project Reactor — Testing with StepVerifier, TestPublisher and PublisherProbe](https://projectreactor.io/docs/core/release/reference/testing.html)
- [Reactor Test API — StepVerifier](https://projectreactor.io/docs/test/release/api/reactor/test/StepVerifier.html)
- [Reactor Test API — StepVerifierOptions](https://projectreactor.io/docs/test/release/api/reactor/test/StepVerifierOptions.html)
- [Reactor Test API — TestPublisher](https://projectreactor.io/docs/test/release/api/reactor/test/publisher/TestPublisher.html)
- [Reactor Test API — PublisherProbe](https://projectreactor.io/docs/test/release/api/reactor/test/publisher/PublisherProbe.html)
- [Spring Security — Reactive Method Security](https://docs.spring.io/spring-security/reference/reactive/authorization/method.html)
- [Spring Security Javadoc — ReactiveAuthorizationManager](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/authorization/ReactiveAuthorizationManager.html)
- [Spring Security Javadoc — AuthorizationResult](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/authorization/AuthorizationResult.html)
- [Spring Security Javadoc — AuthorizationDecision](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/authorization/AuthorizationDecision.html)
- [Spring Security Javadoc — AuthorizationDeniedException](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/authorization/AuthorizationDeniedException.html)
- [Spring Security — Reactive WebTestClient Authentication](https://docs.spring.io/spring-security/reference/reactive/test/web/authentication.html)
- [Spring Security — Testing WebFlux JWT](https://docs.spring.io/spring-security/reference/reactive/test/web/oauth2.html)
- [Spring Boot — Testing and Test-Scope Dependencies](https://docs.spring.io/spring-boot/reference/testing/test-scope-dependencies.html)
