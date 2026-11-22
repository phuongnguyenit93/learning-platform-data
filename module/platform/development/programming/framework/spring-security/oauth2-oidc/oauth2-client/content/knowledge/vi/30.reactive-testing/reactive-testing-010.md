# 30.10. Phát hiện blocking và kiểm soát subscription trong luồng bảo mật

## 1. Vấn đề cốt lõi: bảo mật Reactive phải đúng cả quyền lẫn cách thực thi

Trong ứng dụng **Spring Security OAuth 2.0 OIDC Client trên WebFlux**, một request có thể đã được xác thực đúng nhưng hệ thống vẫn gặp lỗi khó tái hiện: login chậm, timeout khi provider tăng tải, `SecurityContext` biến mất, audit không được ghi, token refresh bị lặp, hoặc một tác vụ sau khi request kết thúc vẫn chạy với thông tin bảo mật cũ.

Hai nguyên nhân đặc trưng của lập trình Reactive là:

1. **Blocking trên luồng không cho phép blocking:** JDBC, `Thread.sleep`, `Future.get`, synchronous HTTP client hoặc việc gọi `Mono.block()` trong Reactor Netty event loop.
2. **Subscription không được kiểm soát:** tự gọi `subscribe()` ở giữa filter/service, quên trả về một `Mono` cần được thực thi, tạo side effect trước lúc subscribe, hoặc mất khả năng quản lý cancellation, error và `ReactiveSecurityContextHolder`.

Ví dụ:

~~~java
// PHẢN VÍ DỤ — đoạn code nằm trong request handling.
Mono<Void> onLogin(String userId) {
    auditService.saveAudit(userId).subscribe(); // fire-and-forget
    String role = jdbcRoleRepository.loadRole(userId); // blocking JDBC
    return Mono.empty();
}
~~~

Lỗi không chỉ là hiệu năng: response có thể được trả trước khi audit hoàn tất, audit error bị tách khỏi luồng lỗi của request, và authorization decision có thể được đưa ra từ một dịch vụ đang làm nghẽn event loop. Nếu một task được tự subscribe không kế thừa Reactor Context thích hợp, nó có thể không còn biết user/tenant đã được xác thực.

### Mục tiêu bài học

Hoàn thành bài này, bạn có thể:

- Nhận diện blocking call trong Spring WebFlux, OAuth2/OIDC Client, UserInfo processing, authority mapping và authorized-client persistence.
- Dùng **BlockHound** đúng cách để phát hiện blocking trên các thread non-blocking trong test.
- Sử dụng **`StepVerifier`**, **`PublisherProbe`**, **`TestPublisher`**, virtual time và `WebTestClient` để kiểm soát subscription/cancellation/error paths.
- Viết reactive pipeline **lazy**, do caller/framework subscribe; tránh `block()` và `subscribe()` trong security components.
- Truyền/đọc **`ReactiveSecurityContextHolder` trong Reactor Context**, không nhầm với ThreadLocal security context.
- Kiểm thử rằng unauthorized requests không làm phát sinh downstream API call, token refresh hoặc audit side effect trái phép.
- Phân biệt scheduler dùng để cô lập thư viện blocking với giải pháp non-blocking thực sự.
- Xử lý đúng race condition, timeout và cancellation trong token refresh, UserInfo, logout và hoạt động bảo mật.

> **Ngữ cảnh:** Spring Boot WebFlux + Spring Security OAuth2 Client/OIDC Login, Reactor Core/Test. Các đoạn code minh họa ý tưởng và API thông dụng trong hệ sinh thái Spring Security 6.x; cú pháp/khả năng hỗ trợ cụ thể cần đối chiếu đúng phiên bản BOM. Không dùng test mocking để kết luận rằng toàn bộ giao thức OIDC đã được kiểm thử end-to-end.

## 2. Bản đồ Reactive Security: nơi ai subscribe?

~~~mermaid
flowchart TD
    A["HTTP request trên Reactor Netty"] --> B["SecurityWebFilterChain"]
    B --> C["Authentication WebFilter"]
    C --> D["ReactiveAuthenticationManager"]
    D --> E["Reactive OAuth2/OIDC services"]
    E --> F["Authorized Client/Token Store"]
    B --> G["Reactive Authorization"]
    G --> H["Handler -> Service -> Repository"]
    H --> I["WebClient gọi Resource Server"]
    H --> J["Response Mono"]
    J --> K["Spring WebFlux/HTTP runtime quản lý subscription"]
    G -->|Denied| L["401/403, không gọi protected downstream"]
~~~

Trong một WebFlux HTTP request bình thường, **Spring WebFlux/HTTP runtime là bên thực hiện subscription** vào publisher được trả về. Code ứng dụng nên **xây dựng và trả về** một `Mono`/`Flux`; không tự subscribe trong handler, filter hoặc repository chỉ để “kích hoạt” xử lý.

### 2.1. Các vai trò

| Thành phần | Contract Reactive | Điều cần kiểm thử |
| --- | --- | --- |
| `SecurityWebFilterChain` | Ghép các WebFilters | Match đúng path, không bypass auth |
| `ReactiveAuthenticationManager` | `Mono<Authentication>` | Auth success/error/empty, không blocking |
| `ServerAuthenticationSuccessHandler` | `Mono<Void>` | Side effects được compose vào response |
| `ServerAuthenticationFailureHandler` | `Mono<Void>` | Error response được thực thi chính xác |
| `ReactiveOAuth2UserService` | `Mono<OAuth2User>` | UserInfo/claims non-blocking, correct subject |
| `ReactiveOAuth2AuthorizedClientManager` | `Mono<OAuth2AuthorizedClient>` | Token refresh/success/failure persistence |
| `ReactiveOAuth2AuthorizedClientService` | `Mono<Void>` hoặc publisher liên quan | Save/remove chạy khi subscribe |
| `ReactiveAuthorizationManager` | Reactive decision publisher | Unauthorized không kích hoạt protected operation |
| `WebClient` | `Mono<ClientResponse>` / `Mono<T>` | Timeout, cancellation, 401/403 đúng nghĩa |
| Spring Session reactive | Session operation publisher | Context/session được lưu theo lifecycle |

### 2.2. Nguồn gốc của các failure

~~~text
blocking JDBC/UserInfo SDK
  -> event loop bị chiếm -> latency tăng -> timeout

service tự subscribe
  -> request trả sớm -> side effect/error không được await
  -> security context có thể mất ở subscription riêng

service quên subscribe/không compose
  -> publisher lạnh (cold) không chạy -> audit/store không lưu

manual retry token request
  -> nhiều subscriptions -> có thể đổi authorization code hai lần
  -> refresh rotation race hoặc duplicate side effect
~~~

## 3. Reactor fundamentals cần nhớ khi kiểm thử bảo mật

### 3.1. Publisher thường lazy

~~~java
import reactor.core.publisher.Mono;
import java.util.concurrent.atomic.AtomicInteger;

AtomicInteger calls = new AtomicInteger();

Mono<String> tokenLookup = Mono.fromSupplier(() -> {
    calls.incrementAndGet();
    return "token-metadata";
});

// calls vẫn bằng 0: mới tạo pipeline, chưa có subscription.

tokenLookup.subscribe(); // Ví dụ minh họa semantics, KHÔNG dùng trong service.
// calls = 1 sau khi subscription thực thi.
~~~

Trong test, dùng `StepVerifier` thay vì gọi `subscribe()` thủ công rồi ngủ chờ:

~~~java
StepVerifier.create(tokenLookup)
    .expectNext("token-metadata")
    .verifyComplete();
~~~

### 3.2. Subscription có thể xảy ra nhiều lần

Với cold publisher, **mỗi subscription có thể thực thi lại upstream**:

~~~text
Mono.defer(refreshTokenOnce)
  -> Subscriber A: gọi Token Endpoint
  -> Subscriber B: lại gọi Token Endpoint
~~~

Điều này đặc biệt nguy hiểm với **authorization code chỉ dùng một lần**, Refresh Token rotation, revocation và audit nghiệp vụ. Không mặc định vì đã lưu biến `Mono` thì operation chỉ thực hiện một lần.

### 3.3. Error và cancellation là một phần của contract

Reactive stream có:

- `onSubscribe`: bắt đầu subscription.
- `onNext`: phát item.
- `onComplete`: hoàn thành.
- `onError`: thất bại.
- `cancel`: subscriber không muốn nhận tiếp.

Trong security pipeline, **cancellation không đồng nghĩa backend side effect chưa xảy ra**. Nếu Token Endpoint đã xử lý Refresh Token nhưng client timeout, điều tra outcome unknown và token rotation, không retry mù quáng.

### 3.4. Scheduler không tự quyết định security context

Reactor Context là **per-subscriber context**, khác `ThreadLocal`. Một pipeline có thể chuyển scheduler mà vẫn giữ Reactor Context đúng cách; một subscription tự tách có thể mất context dù chạy cùng thread.

## 4. Những blocking calls dễ lọt vào reactive security flow

| Vị trí | Ví dụ blocking | Rủi ro |
| --- | --- | --- |
| Custom authentication manager | `JDBC` lookup user/roles | Nghẽn event loop, timeout login |
| Custom UserInfo client | `RestTemplate` hoặc synchronous HTTP SDK | Treo handshake/proxy, giảm throughput |
| OAuth2 authorized client service | JDBC sync/`Thread.sleep` chờ lock | Refresh storm, chậm cấp token |
| OIDC claim enrichment | LDAP/Directory SDK đồng bộ | Chặn event loop trước session creation |
| Security audit | Blocking DB/file writer | Response mất ổn định |
| Token signing/key loading | HSM/provider SDK synchronous | Latency tăng, contention |
| Session store | Blocking Redis client | Callback state không được lưu kịp |
| Role lookup | `CompletableFuture.get()` / `join()` | Blocking chờ remote lookup |
| Application service | `Mono.block()` / `Flux.blockLast()` | Có thể ném lỗi khi chạy trên non-blocking thread |
| Retry/backoff | `Thread.sleep(...)` | Chiếm thread thay vì reactive delay |
| Reflection/legacy library | I/O ẩn bên trong SDK | Khó thấy qua code review |

Blocking không chỉ xuất hiện trong controller. Một `OidcUserService` hoặc authority mapper được gọi khi login cũng có thể chạy trên event-loop nếu được ghép vào reactive chain.

### 4.1. Blocking và computation-heavy là hai vấn đề

Hashing, xác minh chữ ký JWT hoặc xử lý claims phức tạp là **CPU-bound** chứ không nhất thiết là blocking I/O. BlockHound chủ yếu phát hiện **các API blocking được instrument**, không khẳng định một phép tính chiếm CPU 500 ms là an toàn.

Với workload CPU-bound, cần tối ưu/giới hạn concurrency và scheduler phù hợp; không dùng boundedElastic như thuốc chữa mọi vấn đề.

### 4.2. Database reactive vs blocking

- **R2DBC** phù hợp khi muốn DB interactions non-blocking.
- **JDBC/JPA** là synchronous APIs; nếu bắt buộc giữ lại trong WebFlux, cô lập đúng scheduler và giới hạn pool/concurrency.
- Spring Data repository trả `Mono` không tự chứng minh driver ở tầng dưới non-blocking. Cần hiểu implementation.

## 5. BlockHound: công cụ phát hiện blocking trên non-blocking threads

**BlockHound** là công cụ instrument JVM giúp phát hiện một số thao tác blocking (ví dụ `Thread.sleep`) khi chạy trên thread Reactor được đánh dấu **non-blocking**. Khi có thao tác không được phép, nó thường ném `reactor.blockhound.BlockingOperationError`.

Đây là cách tăng khả năng phát hiện lỗi trong **test/integration environment**, không phải bằng chứng rằng toàn bộ chương trình non-blocking.

### 5.1. Dependency

Với Gradle:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-client'

    testImplementation 'io.projectreactor:reactor-test'
    testImplementation 'org.springframework.security:spring-security-test'
    testImplementation 'io.projectreactor.tools:blockhound'
}
~~~

**Cần bảo đảm version của `blockhound`/Reactor/Spring Security tương thích với BOM và JDK**. Một số dự án có thể cần khai báo version BlockHound rõ ràng, runtime instrumentation/Java agent flags hoặc process fork riêng. Không khẳng định snippet tự chạy trên mọi JDK/CI mà không có cấu hình tương thích.

### 5.2. Cài đặt sớm trong JVM test

~~~java
import org.junit.jupiter.api.BeforeAll;
import org.junit.jupiter.api.Test;
import reactor.blockhound.BlockHound;

class BlockHoundSmokeTest {

    @BeforeAll
    static void installOnce() {
        BlockHound.install();
    }

    @Test
    void testPlaceholder() {
        // Bài test blocking bên dưới sẽ subscribe vào pipeline.
    }
}
~~~

**Lưu ý quan trọng:** BlockHound instrumentation thường là **JVM-wide** và cần thiết lập sớm, trước các Reactor schedulers/threads được dùng nhiều. Không nên gọi `BlockHound.install()` lặp ở mọi test class rồi kỳ vọng JVM trở lại trạng thái ban đầu. Trong dự án có test song song, nên cấu hình **một suite/JVM fork chuyên dụng** hoặc bootstrap chung theo tài liệu BlockHound.

### 5.3. Những gì BlockHound có thể và không thể làm

| Tình huống | Kỳ vọng |
| --- | --- |
| `Thread.sleep` trên `Schedulers.parallel()` | Thường phát hiện `BlockingOperationError` |
| `Thread.sleep` trên Reactor Netty event loop | Thường phát hiện nếu instrumentation hợp lệ |
| Blocking I/O trên `Schedulers.boundedElastic()` | Có thể được cho phép vì boundedElastic dành cho blocking |
| JDBC driver blocking ở một thư viện không được instrument | Có thể bỏ sót |
| CPU spin lâu không gọi blocking API | Không nhất thiết bị phát hiện |
| `Mono.block()` trực tiếp trên non-blocking thread | Reactor thường tự ném lỗi blocking; BlockHound có thể cung cấp thêm signal |
| Manually `subscribe()` sai context | BlockHound **không tự phát hiện** lỗi lifecycle này |
| SecurityContext bị mất do custom subscription | Không thể dựa vào BlockHound để phát hiện |

Vì vậy cần kết hợp **BlockHound + StepVerifier/PublisherProbe + WebTestClient + observability**, không thay nhau.

## 6. Test một blocking call bằng BlockHound

Ví dụ riêng cho **môi trường đã cài BlockHound hợp lệ**:

~~~java
import org.junit.jupiter.api.Test;
import reactor.blockhound.BlockingOperationError;
import reactor.core.publisher.Mono;
import reactor.core.scheduler.Schedulers;
import reactor.test.StepVerifier;

class BlockingDetectorTest {

    @Test
    void sleepOnParallelSchedulerIsDetected() {
        Mono<String> source = Mono.fromCallable(() -> {
            Thread.sleep(10); // CỐ Ý SAI để minh họa test.
            return "done";
        }).subscribeOn(Schedulers.parallel());

        StepVerifier.create(source)
            .expectErrorMatches(error ->
                error instanceof BlockingOperationError
                || error.getCause() instanceof BlockingOperationError)
            .verify();
    }
}
~~~

Đoạn này giả định BlockHound đã được cài **trước khi test chạy**, không tự install trong test method. Cách exception được bọc có thể phụ thuộc vào operator/framework; kiểm thử trên JDK/Reactor thực tế và tránh chỉ assert string error message.

### 6.1. Vì sao test phải dùng scheduler non-blocking?

Nếu chỉ viết:

~~~java
Mono.fromCallable(() -> {
    Thread.sleep(10);
    return "done";
});
~~~

rồi chạy test trên JUnit thread thông thường, BlockHound có thể không coi đó là một Reactor non-blocking thread. Kết quả **không chứng minh call là an toàn cho Netty event loop**.

Test phải tạo điều kiện thread scheduler phản ánh môi trường cần bảo vệ hoặc chạy qua WebFlux test harness với instrumentation đúng.

### 6.2. Không whitelist blocking để làm test xanh tùy tiện

BlockHound có cơ chế allow-list/`allowBlockingCallsInside(...)` cho những trường hợp được xác minh. Nếu whitelist quá rộng toàn bộ OAuth2/authorization/user service package, test sẽ mất khả năng phát hiện lỗi thực. Chỉ cho phép ngoại lệ có lập luận, giới hạn cụ thể và issue theo dõi giải pháp lâu dài.

## 7. Sửa blocking: ưu tiên Reactive API, sau đó mới cô lập scheduler

### 7.1. Phản ví dụ: gọi JDBC ngay trong map

~~~java
Mono<String> role = currentUserId()
    .map(userId -> jdbcRoleRepository.loadRole(userId));
~~~

`map` chạy trong context của upstream signal; khi request xử lý trên event loop, JDBC đồng bộ có thể chặn event loop.

### 7.2. Nếu có reactive repository

~~~java
Mono<String> role = currentUserId()
    .flatMap(userId -> reactiveRoleRepository.findRoleByUserId(userId));
~~~

Ở đây `findRoleByUserId` trả `Mono<String>` do driver non-blocking thực hiện. Khi không tìm thấy role, cần business policy: reject hoặc default restricted authority, không mặc định nâng quyền.

### 7.3. Nếu bắt buộc dùng blocking JDBC

~~~java
import reactor.core.publisher.Mono;
import reactor.core.scheduler.Schedulers;

Mono<String> roleForUser(String userId) {
    return Mono.fromCallable(() ->
            jdbcRoleRepository.loadRole(userId))
        .subscribeOn(Schedulers.boundedElastic());
}
~~~

`Mono.fromCallable` trì hoãn blocking call cho tới lúc subscribe; `subscribeOn(Schedulers.boundedElastic())` đưa source vào scheduler thiết kế để bao bọc blocking I/O.

**Giới hạn:**

- BoundedElastic có giới hạn thread/queue, không tạo capacity vô hạn.
- Chuyển scheduler không biến JDBC thành non-blocking.
- Giữ timeout/concurrency bound và connection pool phù hợp.
- Scheduler isolation phải bao quanh **chính operation blocking**; không đưa phần nguy hiểm lên event loop trước rồi mới gọi `publishOn(boundedElastic())`.
- Nếu được, chuyển sang R2DBC/non-blocking HTTP client để đơn giản hóa.

### 7.4. `subscribeOn` và `publishOn` khác nhau

| Operator | Hiệu ứng chính | Lỗi thường gặp |
| --- | --- | --- |
| `subscribeOn(scheduler)` | Ảnh hưởng nơi source subscription và upstream execution khởi đầu | Đặt sau một side effect đã được thực thi tại assembly |
| `publishOn(scheduler)` | Chuyển nơi xử lý downstream signals sau nó | Blocking xảy ra trước publishOn vẫn chặn thread cũ |

Ví dụ:

~~~java
// PHẢN VÍ DỤ: blocking call xảy ra NGAY khi tạo Mono.
String value = jdbcRoleRepository.loadRole(userId);
Mono<String> source =
    Mono.just(value).subscribeOn(Schedulers.boundedElastic());

// ĐÚNG HƠN nếu chưa thể thay JDBC:
Mono<String> safeSource = Mono
    .fromCallable(() -> jdbcRoleRepository.loadRole(userId))
    .subscribeOn(Schedulers.boundedElastic());
~~~

## 8. Subscription phải thuộc caller/framework, không thuộc service

### 8.1. Phản ví dụ: fire-and-forget trong service bảo mật

~~~java
public Mono<Void> recordLogin(String userId) {
    auditRepository.saveEvent(userId).subscribe(); // SAI.
    return Mono.empty();
}
~~~

Vấn đề:

- Response có thể hoàn tất trước audit.
- Không có error propagation đúng.
- Cancellation của request không kiểm soát child subscription.
- Reactor Context (authentication/tenant/correlation) có thể bị tách.
- Test không thể chờ audit hoàn tất qua returned publisher.
- Framework retry/circuit breaker không bao được side effect này.

### 8.2. Compose publisher vào return value

~~~java
public Mono<Void> recordLogin(String userId) {
    return auditRepository.saveEvent(userId)
        .then();
}
~~~

Với success handler:

~~~java
public Mono<Void> afterLoginSuccess(
        WebFilterExchange exchange,
        Authentication authentication) {

    return auditService.recordSuccess(authentication)
        .then(redirectSuccessHandler.onAuthenticationSuccess(
            exchange, authentication));
}
~~~

Đây là **method body minh họa** cho `ServerAuthenticationSuccessHandler`, giả định audit policy yêu cầu ghi xong trước khi redirect và các dependencies đã được khai báo. Nếu audit không được phép làm login fail, cần **thiết kế outbox/queue/error policy minh bạch**, không chữa bằng `subscribe()` tự do.

### 8.3. Khi side effect không cần chặn response

Một hệ thống có thể dùng **transactional outbox**: ghi sự kiện trong giao dịch có kiểm soát, sau đó worker/queue subscriber riêng xử lý. Đó là một **subscription boundary được thiết kế, giám sát và sở hữu** — khác với `subscribe()` lạc lõng trong request.

Không thể vừa tuyên bố audit bắt buộc vừa tự subscribe vào audit và trả 200 bất kể audit chưa thực hiện.

## 9. Subscription và các operators dễ gây sai bảo mật

| Anti-pattern | Vấn đề | Thay thế/kiểm tra |
| --- | --- | --- |
| `mono.subscribe()` trong `WebFilter` | Tạo stream không do request quản lý | Return `Mono<Void>` |
| `mono.block()` trong event loop | Chặn non-blocking thread | Compose `flatMap`/`then` |
| `doOnNext(v -> asyncService.save(v).subscribe())` | Side effect tách biệt | `flatMap(v -> asyncService.save(v).thenReturn(v))` |
| `onErrorResume(e -> Mono.empty())` mọi lỗi | Che lỗi authentication/authorization | Chỉ handle error đã phân loại |
| `switchIfEmpty(expensiveFallback())` với fallback tạo side effect ngay | Eager assembly effect | `switchIfEmpty(Mono.defer(() -> expensiveFallback()))` |
| `Mono.when(authCheck, apiCall)` | Cùng subscribe, API có thể chạy trước quyết định quyền | `authCheck.then(apiCall)` khi authCheck lỗi nếu từ chối |
| `flatMap` khi bắt buộc thứ tự | Concurrency và reorder | `concatMap` hoặc `flatMapSequential` đúng điều kiện |
| `cache()` trên shared user token stream | Có thể cache credential qua subscriber/context sai | Per-principal lifecycle có policy, tránh global cache |
| `retry()` trên authorization code exchange | Reuse one-time code | Controlled login retry mới |
| `timeout(...).onErrorReturn("allow")` | Fail-open authorization | Fail-closed policy |

### 9.1. `Mono.when` không bảo đảm authorization trước resource operation

Phản ví dụ:

~~~java
Mono<Void> result = Mono.when(
    authorizeAccess(),      // Nếu lỗi, downstream khác có thể đã bắt đầu.
    deleteProtectedRecord()
);
~~~

`Mono.when` subscribe vào các publishers để phối hợp hoàn thành; các publishers khác có thể đã bắt đầu trước khi authorization fail. Đối với thao tác được bảo vệ, cần sequencing:

~~~java
Mono<Void> result = authorizeAccess()
    .then(Mono.defer(() -> deleteProtectedRecord()));
~~~

`authorizeAccess()` ở ví dụ này phải **error** khi bị từ chối và complete khi được phép. Nếu nó chỉ trả `Mono<Boolean>`, cần kiểm tra boolean rồi mới gọi operation.

### 9.2. Đừng dùng `doOn...` để ghép một tác vụ bất đồng bộ

~~~java
// SAI — publisher do asyncService tạo không được compose.
return authenticate()
    .doOnNext(auth -> asyncAudit.save(auth));

// ĐÚNG — audit trở thành một phần pipeline.
return authenticate()
    .flatMap(auth -> asyncAudit.save(auth).thenReturn(auth));
~~~

`doOnNext` phù hợp cho observation đồng bộ, lightweight và an toàn; không phù hợp để tạo một publisher không được subscribe.

## 10. Kiểm soát nhánh authorization bằng PublisherProbe

`PublisherProbe` từ `reactor-test` giúp chứng minh publisher có được subscribe/request/cancel hay không. Nó rất hữu ích khi muốn bảo đảm một request **không đủ quyền không chạm đến Resource Server**.

### 10.1. Test unauthorized không gọi downstream

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.security.access.AccessDeniedException;
import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;
import reactor.test.publisher.PublisherProbe;

class AuthorizationSubscriptionTest {

    @Test
    void deniedAccessMustNotSubscribeToProtectedOperation() {
        PublisherProbe<String> downstream =
            PublisherProbe.of(Mono.just("sensitive-result"));

        Mono<String> result = Mono.just(false)
            .flatMap(allowed -> allowed
                ? downstream.mono()
                : Mono.error(new AccessDeniedException("Denied")));

        StepVerifier.create(result)
            .expectError(AccessDeniedException.class)
            .verify();

        downstream.assertWasNotSubscribed();
    }

    @Test
    void grantedAccessSubscribesExactlyThroughSelectedBranch() {
        PublisherProbe<String> downstream =
            PublisherProbe.of(Mono.just("allowed"));

        Mono<String> result = Mono.just(true)
            .flatMap(allowed -> allowed
                ? downstream.mono()
                : Mono.error(new AccessDeniedException("Denied")));

        StepVerifier.create(result)
            .expectNext("allowed")
            .verifyComplete();

        downstream.assertWasSubscribed();
        downstream.assertWasRequested();
    }
}
~~~

`PublisherProbe` chứng minh subscription/request/cancellation của một nhánh, không thay thế kiểm tra OIDC signature hay API policy.

### 10.2. Điều kiện security phải nằm trước operation

Một thiết kế service:

~~~java
Mono<String> readProtectedData(
        String userId, String documentId) {

    return authorizationService
        .assertCanRead(userId, documentId)
        .then(Mono.defer(() ->
            reactiveRepository.readContent(documentId)));
}
~~~

Trong thiết kế này, `assertCanRead` phải phát `onError` khi từ chối, `onComplete` khi cho phép. Nếu nó return `Mono<Boolean>`, phải dùng `flatMap`/`filter` để giải thích rõ false; `then` bỏ qua giá trị boolean và **không tự từ chối**.

### 10.3. Security check có thể cần re-evaluate theo policy

Với authorization nhạy cảm, kiểm tra user/tenant ở thời điểm request và đúng resource, không cache quyết định chỉ theo username bất chấp thời gian/tenant/context. Test probe nên chứng minh branch chặn API call, nhưng vẫn cần policy tests ở application/domain layer.

## 11. Dùng TestPublisher để kiểm tra cancellation

`TestPublisher` cho phép điều khiển tín hiệu `next/error/complete` theo thời điểm test, hữu ích để phát hiện operation đã **cancel** sau khi đủ dữ liệu hoặc subscriber disconnect.

~~~java
import org.junit.jupiter.api.Test;
import reactor.test.StepVerifier;
import reactor.test.publisher.TestPublisher;

class CancellationTest {

    @Test
    void takeOneCancelsUpstreamAfterFirstValue() {
        TestPublisher<String> source = TestPublisher.create();

        StepVerifier.create(source.flux().take(1))
            .then(() -> source.next("first"))
            .expectNext("first")
            .verifyComplete();

        source.assertCancelled();
    }
}
~~~

### 11.1. Cancellation có ý nghĩa gì trong security flow?

Nếu browser ngắt kết nối khi application vừa gọi Token Endpoint hoặc Revocation Endpoint:

- Local publisher có thể bị cancel.
- Remote server **có thể đã xử lý request** dù client không nhận response.
- Một Refresh Token có thể đã được rotate.
- Không được tự động retry operation one-time như Authorization Code exchange.

Test cancellation cần kiểm tra **state consistency/recovery** chứ không chỉ số lượng thread.

### 11.2. `doFinally` để quan sát, không phải cấp quyền

~~~java
return protectedPipeline()
    .doFinally(signal -> metrics.recordTermination(signal.name()));
~~~

`doFinally` có thể thấy `CANCEL`, `ON_COMPLETE`, `ON_ERROR`. Không dùng `doFinally` như nơi thực hiện blocking revoke/audit bắt buộc vì operation termination đã xảy ra và side effect được thực thi theo semantics của callback đồng bộ.

## 12. StepVerifier: test đủ completion, error và timeout

### 12.1. Success path

~~~java
StepVerifier.create(Mono.just("authenticated"))
    .expectNext("authenticated")
    .verifyComplete();
~~~

### 12.2. Authorization denied

~~~java
Mono<String> denied = Mono.error(
    new org.springframework.security.access.AccessDeniedException(
        "Policy denied"));

StepVerifier.create(denied)
    .expectError(
        org.springframework.security.access.AccessDeniedException.class)
    .verify();
~~~

### 12.3. Test timeout bằng virtual time

~~~java
import java.time.Duration;
import java.util.concurrent.TimeoutException;
import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;

StepVerifier.withVirtualTime(() ->
        Mono.<String>never()
            .timeout(Duration.ofSeconds(5)))
    .expectSubscription()
    .thenAwait(Duration.ofSeconds(5))
    .expectError(TimeoutException.class)
    .verify();
~~~

Điểm quan trọng: **tạo publisher bên trong supplier** của `withVirtualTime` để virtual scheduler được dùng đúng thời điểm. Không để source/timer sử dụng scheduler cũ trước khi kích hoạt virtual time. Virtual time giúp tránh `Thread.sleep(5000)` trong test.

### 12.4. Không nhầm timeout và authorization failure

Nếu UserInfo/Token Endpoint timeout, không chuyển thành `Mono.just(approvedUser)` để login thành công. Policy có thể chấp nhận degraded behavior cho **thông tin profile tùy chọn** nhưng không được bỏ xác minh identity hoặc account/tenant authorization.

## 13. Test tính lazy: chưa subscribe thì không có side effect

~~~java
import java.util.concurrent.atomic.AtomicInteger;
import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;

AtomicInteger attempts = new AtomicInteger();

Mono<String> source = Mono.defer(() -> {
    attempts.incrementAndGet();
    return Mono.just("safe-metadata");
});

// assertEquals(0, attempts.get()) trước khi tạo StepVerifier.

StepVerifier.create(source)
    .expectNext("safe-metadata")
    .verifyComplete();

// assertEquals(1, attempts.get()) sau verification.
~~~

Trong production, một bất đồng bộ operation tạo side effect ngay lúc method call mà **không chờ subscribe** có thể phá lazy semantics. Ví dụ `Mono.just(blockingCall())` thực thi `blockingCall()` ngay lập tức, còn `Mono.fromCallable(() -> blockingCall())` trì hoãn nó.

### 13.1. Deferred fallback

~~~java
return primaryLookup()
    .switchIfEmpty(Mono.defer(() -> fallbackLookup()));
~~~

Nếu `fallbackLookup()` có tác dụng phụ ngay khi được gọi để tạo Publisher, `Mono.defer` giúp chỉ tạo nó khi primary empty. Tuy nhiên fallback vẫn phải tuân thủ authorization policy, không được là “fallback admin”.

## 14. Reactor SecurityContext: không sử dụng ThreadLocal như Servlet

Trong Servlet, nhiều đoạn code đọc:

~~~java
SecurityContextHolder.getContext().getAuthentication();
~~~

Trong Reactive WebFlux, bảo mật truyền bằng **Reactor Context**, nên ưu tiên:

~~~java
import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.ReactiveSecurityContextHolder;
import reactor.core.publisher.Mono;

Mono<Authentication> authentication =
    ReactiveSecurityContextHolder.getContext()
        .map(context -> context.getAuthentication());
~~~

`ReactiveSecurityContextHolder.getContext()` có thể là `Mono.empty()` nếu không có security context; phải xử lý không có Authentication theo policy.

### 14.1. Vì sao mất context?

- Tự gọi `subscribe()` tạo subscriber mới, không mang context mong muốn.
- Dùng `CompletableFuture` hoặc SDK callback rồi không bridge context.
- Tạo thread mới và đọc `SecurityContextHolder` ThreadLocal.
- Lấy Authentication trước khi security filter ghi context.
- Background job không có request principal.
- Test tạo source ở context khác hoặc đặt `contextWrite` sai hướng.

### 14.2. Chuyển scheduler không mặc định làm mất Reactor Context

Với Reactor publishers được compose đúng, Context propagation thường đi qua nhiều operators/schedulers. Không kết luận chỉ cần `publishOn` là Authentication biến mất; hãy kiểm tra **subscription boundary** và nơi context được gắn.

## 15. Unit test ReactiveSecurityContextHolder bằng StepVerifier

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.security.authentication.TestingAuthenticationToken;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.ReactiveSecurityContextHolder;
import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;

class ReactiveSecurityContextTest {

    Mono<String> principalName() {
        return ReactiveSecurityContextHolder.getContext()
            .map(context -> context.getAuthentication().getName())
            .switchIfEmpty(Mono.error(
                new IllegalStateException("No security context")));
    }

    @Test
    void contextIsVisibleInsideReactiveChain() {
        Authentication auth = new TestingAuthenticationToken(
            "alice", "unused", "ROLE_USER");

        StepVerifier.create(
                principalName().contextWrite(
                    ReactiveSecurityContextHolder.withAuthentication(auth)))
            .expectNext("alice")
            .verifyComplete();
    }

    @Test
    void missingContextIsNotTreatedAsAuthenticated() {
        StepVerifier.create(principalName())
            .expectError(IllegalStateException.class)
            .verify();
    }
}
~~~

Ví dụ test trực tiếp service-level context; không chứng minh ID Token được ký đúng. `TestingAuthenticationToken` chỉ là authentication giả được kiểm soát trong test.

### 15.1. Chỗ đặt `contextWrite` có quan trọng

Reactor Context truyền từ **subscriber downstream lên upstream**; vì vậy đặt `contextWrite` ở nơi không bao bọc operation cần Authentication có thể khiến upstream khác không nhận được context.

Giả định mọi operator đều có access một global ThreadLocal user là sai mô hình. Khi test context, cần có negative path **không Authentication** và path **Authentication khác user/tenant**.

### 15.2. Không đưa raw ID Token vào Reactor Context

Context nên giữ security context/principal do framework quản lý, correlation/tracing metadata cần thiết, không dùng như nơi chứa raw client secret/Refresh Token để tiện truy cập toàn hệ thống.

## 16. Kiểm thử method security với Reactive

`@EnableReactiveMethodSecurity` hỗ trợ reactive method security cho các method phù hợp, ví dụ:

~~~java
import org.springframework.security.access.prepost.PreAuthorize;
import reactor.core.publisher.Mono;

public class ReportService {

    private final ReactiveReportRepository repository;

    public ReportService(ReactiveReportRepository repository) {
        this.repository = repository;
    }

    @PreAuthorize("hasAuthority('ROLE_REPORT_VIEWER')")
    public Mono<String> readReport(String reportId) {
        return repository.readContent(reportId);
    }
}
~~~

Trong app thực, method security cần được bật qua `@EnableReactiveMethodSecurity` và method phải được gọi qua **Spring proxy** (self-invocation có thể bỏ qua interceptor). Khi bị từ chối, test nên xác nhận:

1. Publisher kết thúc với access denied, không phải fallback allow.
2. Reactive repository không được subscribe.
3. HTTP/WebFlux exception translation trả status đúng theo authentication state.
4. Không tiết lộ nội dung báo cáo qua error message hoặc logs.

### 16.1. Don't mix return types

Nếu method có blocking repository và trả `Mono.just(blockingCall())`, reactive method-security annotation không làm blocking call biến mất. Cần reactive repository hoặc isolation phù hợp.

### 16.2. Authorization check trước bên trong publisher

Một điểm dễ sai: method assembly có thể chạy trước khi interceptor quyết định subscription. Để side effects được bảo vệ, tránh thực thi side effect ngay tại method entry:

~~~java
// SAI nếu được gọi trước authorization check.
public Mono<String> readReport(String id) {
    String content = jdbcRepo.loadReport(id); // side effect/blocking tại assembly.
    return Mono.just(content);
}

// An toàn hơn về lazy semantics, nhưng JDBC vẫn cần scheduler isolation.
public Mono<String> readReport(String id) {
    return Mono.fromCallable(() -> jdbcRepo.loadReport(id))
        .subscribeOn(reactor.core.scheduler.Schedulers.boundedElastic());
}
~~~

## 17. WebTestClient: test security filter chain mà không tự subscribe

`WebTestClient` cung cấp test harness cho WebFlux. Khi dùng Spring Security Test, có thể cấu hình `springSecurity()` cho WebTestClient và mock authentication theo đúng loại.

~~~java
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.ApplicationContext;
import org.springframework.test.web.reactive.server.WebTestClient;

import static org.springframework.security.test.web.reactive.server
    .SecurityMockServerConfigurers.springSecurity;
import static org.springframework.security.test.web.reactive.server
    .SecurityMockServerConfigurers.mockOidcLogin;

@SpringBootTest
class OidcReactiveWebTest {

    @Autowired ApplicationContext context;
    WebTestClient client;

    @BeforeEach
    void setup() {
        client = WebTestClient.bindToApplicationContext(context)
            .apply(springSecurity())
            .configureClient()
            .build();
    }

    @Test
    void authenticatedOidcUserCanReachProtectedPage() {
        client.mutateWith(mockOidcLogin())
            .get().uri("/account")
            .exchange()
            .expectStatus().isOk();
    }
}
~~~

Giả định ứng dụng có route `GET /account` trả HTTP 200 khi đã login và cấu hình OIDC/authorization phù hợp. Nếu route không tồn tại hoặc yêu cầu authority khác, phải sửa test expectation/fixture theo business contract.

### 17.1. `mockOidcLogin()` kiểm thử cái gì?

Nó mô phỏng OIDC authenticated principal để kiểm tra:

- `SecurityWebFilterChain` và route authorization.
- Authorities và principal claims application sử dụng.
- Reactive SecurityContext propagation trong handler/service.
- Response/HTTP error khi user authenticated/unauthenticated.

Nó **không thực hiện thật** Authorization Code exchange, PKCE, ID Token signature/JWKS, UserInfo `sub` matching hoặc Token Endpoint HTTP call. Các phần đó cần protocol integration tests với mock/test OP.

### 17.2. Anonymous request response có thể khác nhau

Với `oauth2Login()` browser flow, unauthenticated request thường có thể nhận **302 redirect login**; API được cấu hình bearer/resource-server có thể trả **401**. Test không nên hard-code mọi anonymous request là 401 mà không xét `ServerAuthenticationEntryPoint` và route.

### 17.3. Security test fixture chỉ được tạo một lần đúng nghĩa

Nếu test dùng `mockOidcLogin()` và sau đó tự `subscribe()` service với subscriber khác, Authentication có thể không được propagate như WebTestClient request. Hãy assert qua HTTP exchange hoặc dùng `StepVerifier` với Reactor Context được cài rõ ràng.

## 18. Test login mock khác integration OIDC protocol

Một bộ tests đầy đủ thường cần:

| Lớp test | Mục tiêu | Có thực hiện OIDC protocol? |
| --- | --- | --- |
| Unit `StepVerifier` | Service context, signals, errors, cancellation | Không |
| `PublisherProbe` | Downstream được subscribe hay không | Không |
| `BlockHound` JVM test | Blocking calls trên non-blocking scheduler | Không |
| `WebTestClient + mockOidcLogin` | Filter chain/route/authorities | Không |
| Mock OP integration | Authorization Code, PKCE, ID Token, JWKS, UserInfo | Có, khi thiết lập đầy đủ |
| Browser E2E + Test OP | Redirect/callback/cookies/session | Có |
| Load/perf test | Event-loop saturation và throughput | Theo hệ thống kiểm thử |

### 18.1. Mock OP test cần kiểm tra

- Authorization request có `state`, code challenge và issuer đúng.
- Callback code/state được correlate với session.
- Token Endpoint không bị gọi hai lần vì duplicate subscription.
- ID Token signature/issuer/audience/nonce được verify.
- UserInfo `sub` khớp ID Token.
- Authorized client mới được lưu.
- Reactive chain không gọi blocking API trên event loop.
- OIDC login result có đúng authorities/session.

Không dùng token/credential của người dùng production trong CI hoặc test fixtures.

## 19. Kiểm thử OAuth2AuthorizedClientManager Reactive

Reactive client manager thường cung cấp:

~~~java
Mono<OAuth2AuthorizedClient> authorizedClient =
    reactiveAuthorizedClientManager.authorize(authorizationRequest);
~~~

Phải **return/compose** Mono này, không tự `subscribe()` trong service rồi tiếp tục với giá trị token chưa sẵn sàng.

### 19.1. Phản ví dụ: access token chưa được cấp

~~~java
// SAI: out-of-band subscription.
AtomicReference<OAuth2AuthorizedClient> ref =
    new AtomicReference<>();

manager.authorize(request).subscribe(ref::set);
OAuth2AuthorizedClient client = ref.get(); // Có thể null/race.
~~~

### 19.2. Compose token authorization với API call

~~~java
Mono<Report> loadReport(OAuth2AuthorizeRequest request) {
    return manager.authorize(request)
        .switchIfEmpty(Mono.error(
            new IllegalStateException("Authorized client unavailable")))
        .flatMap(client ->
            reportsGateway.fetchReport(client));
}
~~~

Đây là **fragment minh họa** với `Report`, `reportsGateway`, `manager` được định nghĩa trong ứng dụng. Gateway cần dùng Access Token đúng Resource Server/audience/scope, qua HTTPS; không log hoặc trả token ra frontend.

### 19.3. Một subscription cho một refresh?

Không mặc định. Nếu nhiều requests cùng subscribe và Access Token hết hạn, manager/store có thể cần concurrency protection. Với Refresh Token rotation, hai concurrent refresh trên cùng token có thể gây `invalid_grant` và xóa nhầm token mới.

Test nên mô phỏng concurrent refresh, persistence version/CAS và failure-handler cleanup; không dùng `Mono.cache()` chung cho mọi principals để “giải quyết” race vì dễ trộn user/tenant credentials.

### 19.4. Background jobs không có ServerWebExchange

Với scheduled jobs ngoài HTTP exchange, cân nhắc `AuthorizedClientServiceReactiveOAuth2AuthorizedClientManager` với `ReactiveOAuth2AuthorizedClientService` và application principal ổn định. Đừng kỳ vọng một `ServerOAuth2AuthorizedClientRepository` gắn WebSession sẽ tự có session của user trong background worker.

## 20. Khi HTTP request bị hủy: token exchange outcome unknown

Một timeout/cancellation có thể xảy ra đúng lúc Token Endpoint xử lý:

~~~mermaid
sequenceDiagram
    participant App as Reactive OAuth2 Client
    participant OP as Authorization Server
    App->>OP: Refresh R1
    Note over App: Local timeout/cancel
    OP-->>App: A2 + R2 (response có thể không được nhận)
    App->>App: Store còn R1
    App->>OP: Retry R1
    OP-->>App: invalid_grant
~~~

Lỗi này không nhất thiết chứng minh attacker đã lấy Refresh Token. Cần hiểu token rotation, persistence và outcome unknown. Retry mù quáng sau timeout có thể làm hỏng cả token family.

### 20.1. Đo cancellation nhưng không suy đoán remote outcome

Trong test, có thể mô phỏng API `Mono.never()` + `timeout`, ghi event `CANCEL` và kiểm tra connection state. Không kết luận remote server không làm gì chỉ vì local publisher bị cancel.

### 20.2. Không tự retry Authorization Code exchange

Authorization code thường một lần. Một `retryWhen` chung cho mọi WebClient call có thể gửi lại cùng code sau timeout, rồi nhận `invalid_grant`. Đối với login, khởi động lại authorization flow an toàn thường hợp lý hơn so với retry code cũ vô hạn.

## 21. Test HTTP 401/403: fail-closed và không kích hoạt quyền cao

Trong WebFlux OAuth2 Client, Resource Server có thể trả:

~~~http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer error="invalid_token"
~~~

~~~http
HTTP/1.1 403 Forbidden
WWW-Authenticate: Bearer error="insufficient_scope", scope="reports.write"
~~~

### 21.1. Những assertions quan trọng

- `401 invalid_token`: token stale có thể được cleanup theo failure handler phù hợp; không tự assume token bị đánh cắp.
- `403 insufficient_scope`: không gửi request lại với machine admin client credentials để bypass.
- Business 403: không tự xóa Refresh Token; kiểm tra tenant/ACL.
- API 503: không refresh Access Token liên tục để “chữa lỗi API”.
- Timeout: giới hạn retry và giữ đúng connection state.

### 21.2. Kiểm tra WebClient filter failure handler

`ServerOAuth2AuthorizedClientExchangeFilterFunction` giúp gắn Access Token của authorized client vào WebClient request. Khi khởi tạo bằng `ReactiveClientRegistrationRepository` và `ServerOAuth2AuthorizedClientRepository`, nó có thể có default failure handling cho Bearer errors phù hợp. Khi khởi tạo bằng `ReactiveOAuth2AuthorizedClientManager`, **không tự có** failure handler cho Resource Server 401/403; cần cấu hình `setAuthorizationFailureHandler(...)` khi muốn cleanup token stale theo API response.

Không nhầm failure handler tại **Token Endpoint authorization** với failure handler tại **Resource Server HTTP response**.

### 21.3. Probe ngăn gọi API sau deny

Trong test, dùng `PublisherProbe` cho gateway call và bắt buộc `assertWasNotSubscribed()` khi user thiếu role hoặc tenant membership.

Chỉ kiểm tra HTTP status 403 là chưa đủ nếu code đã gọi downstream API rồi mới trả forbidden.

## 22. Test custom OIDC UserInfo service không blocking

`ReactiveOAuth2UserService<OidcUserRequest, OidcUser>` xử lý reactive OIDC user loading. Khi tùy biến, nên delegate sang implementation reactive của Spring Security, sau đó áp dụng business policy/claim mapping trong pipeline.

Một anti-pattern:

~~~java
// PHẢN VÍ DỤ: synchronous HTTP client trong reactive mapping.
return delegate.loadUser(request)
    .map(user -> {
        String groups = restTemplate.getForObject(
            "https://directory.example.net/groups", String.class);
        return enrich(user, groups);
    });
~~~

Điều này có thể block event loop. Ngoài ra, source URL và Access Token phải đến từ trusted config, không từ request input; tránh token exfiltration.

### 22.1. Sử dụng WebClient được cấu hình đúng

~~~java
return delegate.loadUser(request)
    .flatMap(user ->
        directoryGateway.fetchAllowedGroups(user)
            .map(groups -> enrich(user, groups)));
~~~

`directoryGateway` là reactive gateway giả định; nó phải có:

- Access Token đúng resource audience/scope theo provider contract.
- TLS/host allowlist, timeout/rate limit/backoff.
- Không log groups/token/PII thô.
- Policy fail-closed nếu nhóm dùng để cấp quyền.
- Không tự cấp role khi Directory API 503.

### 22.2. UserInfo sub equality không được bỏ qua

Nếu custom service tự gọi UserInfo HTTP, claim `sub` trong response **phải khớp chính xác** `sub` trong ID Token. Test cả happy path và mismatch; **không sử dụng UserInfo claims khi mismatch**.

### 22.3. BlockHound không kiểm tra nghiệp vụ

Ngay cả khi UserInfo gateway non-blocking, nó vẫn có thể trả claims của user khác hoặc map arbitrary `admin` thành `ROLE_ADMIN`. Protocol, identity và authorization tests vẫn cần riêng.

## 23. Test Reactive logout và session persistence

Một WebFlux OIDC application có thể có:

- RP `WebSession`.
- OP SSO session.
- `ReactiveOAuth2AuthorizedClientService`.
- OIDC Session Registry cho Back-Channel Logout.
- Access/Refresh Tokens còn ở OP hoặc Resource Server.

### 23.1. Logout publisher phải được compose

Phản ví dụ:

~~~java
session.invalidate().subscribe(); // SAI trong WebFilter/handler.
return Mono.empty();
~~~

Đúng hơn:

~~~java
return session.invalidate()
    .then(auditService.recordLogout(userAlias));
~~~

Giả định audit service có chính sách riêng và `recordLogout` trả `Mono<Void>`. Nếu audit fail, phải có policy cụ thể; không tùy tiện nuốt lỗi trong một sự kiện bảo mật bắt buộc.

### 23.2. Subscription audit của Back-Channel Logout

OP gửi signed Logout Token server-to-server. RP phải verify token, tìm session theo `sid`/`sub`, invalidate sessions qua reactive store và **trả Mono cho request pipeline**, không tự `subscribe()` vào session cleanup rồi trả 200 trước.

Tests:

1. Signature/issuer/audience/events invalid → không xóa session.
2. `sid` hợp lệ → chỉ session tương ứng bị invalidate.
3. Session store fail → lỗi được quan sát/handled theo contract, không trả success giả.
4. Cluster → registry/session state có hiệu lực trên các nodes.
5. Không nhầm OP `sid` với RP cookie `SESSION`.

### 23.3. Local logout không đồng nghĩa token revocation

`removeAuthorizedClient(...)` trong store chỉ xóa local token record. RFC 7009 token revocation là request khác tới OP. Test nên phân biệt, không hứa local session invalidation đã vô hiệu mọi Access Token.

## 24. Subscription, transaction và persistence

Reactive transaction thường dựa trên **Reactor Context**. Một child `subscribe()` tách biệt có thể không tham gia transaction/security context của request.

### 24.1. Phản ví dụ

~~~java
public Mono<Void> updatePermissions(UserId id) {
    roleRepository.saveRoles(id).subscribe();
    return auditRepository.recordRoleChange(id).then();
}
~~~

`saveRoles` và audit có thể chạy riêng, lỗi không đồng bộ hoặc transaction khác.

### 24.2. Compose theo thứ tự

~~~java
public Mono<Void> updatePermissions(UserId id) {
    return roleRepository.saveRoles(id)
        .then(auditRepository.recordRoleChange(id));
}
~~~

Nếu nghiệp vụ yêu cầu atomicity, thêm reactive transaction management phù hợp store và `TransactionalOperator`. Đừng giả định `@Transactional` của blocking JDBC tự bao trùm các child subscriptions tách biệt.

### 24.3. Multiple database operations

`Mono.when` chạy nhiều publishers đồng thời; nếu phụ thuộc thứ tự hoặc cần bảo đảm authorization trước write, hãy dùng `then`/`flatMap`/`concatMap`. Nếu muốn parallel read độc lập sau khi được cấp quyền, cần đánh giá bounded concurrency và context propagation.

## 25. Kịch bản phân tích blocking thực tế

### Tình huống A — Login OIDC chậm khi user thuộc nhiều groups

Một custom claims mapper gọi synchronous Directory SDK rồi chặn event loop.

**Triệu chứng:** event-loop latency tăng, request timeout, CPU không nhất thiết cao, throughput giảm.

**Định vị:** BlockHound test với mock Directory SDK, thread dumps, scheduler metrics; xem UserInfo/authority enrichment path.

**Xử lý:** chuyển sang reactive HTTP/API hoặc cô lập boundedElastic tạm thời; giới hạn concurrency và quyền API.

### Tình huống B — Audit login biến mất trong một số requests

`audit.save(...).subscribe()` chạy fire-and-forget.

**Định vị:** PublisherProbe không thấy audit là một phần returned Mono, audit errors không làm request fail/cảnh báo.

**Xử lý:** compose `audit.save(...).then(redirect())` hoặc transactional outbox nếu chấp nhận asynchronous audit.

### Tình huống C — API đã bị gọi dù user nhận 403

Code dùng `Mono.when(authorize(), callApi())`.

**Định vị:** PublisherProbe của `callApi()` cho thấy đã subscribe trước khi authorization fail.

**Xử lý:** `authorize().then(Mono.defer(() -> callApi()))` khi authorization bằng complete/error; với `Mono<Boolean>` dùng flatMap để kiểm tra false.

### Tình huống D — `ReactiveSecurityContextHolder` trống

Một service tự subscribe vào `Mono` từ web filter rồi trong callback đọc current user.

**Định vị:** StepVerifier với/không context, log safe stage. Kiểm tra subscription boundary.

**Xử lý:** giữ pipeline được compose, dùng `ReactiveSecurityContextHolder.getContext()`, không phụ thuộc Servlet ThreadLocal.

### Tình huống E — Token Refresh Token rotation race

Hai requests subscribe vào nguồn refresh cũ cùng lúc.

**Định vị:** token endpoint mock đếm refresh requests, test race bằng `TestPublisher` hoặc controlled responses, versioned persistence.

**Xử lý:** single-flight theo user/registration, optimistic locking và failure handler không xóa token mới.

### Tình huống F — `Mono.block()` trong Reactive controller

Một developer muốn lấy token synchronously:

~~~java
// PHẢN VÍ DỤ trong event-loop:
OAuth2AuthorizedClient client = manager.authorize(request).block();
~~~

**Triệu chứng:** Reactor ném lỗi blocking hoặc event-loop latency; BlockHound có thể phát hiện.

**Xử lý:** `return manager.authorize(request).flatMap(client -> ...)`.

### Tình huống G — Test xanh nhưng production chậm

BlockHound test chạy trên JUnit thread không đánh dấu non-blocking; JDBC blocking không bị phát hiện.

**Định vị:** chạy test trên `Schedulers.parallel()`/WebFlux harness có BlockHound instrumentation, bổ sung load tests và traces.

**Xử lý:** không coi một smoke test là bảo đảm tuyệt đối.

### Tình huống H — Mock OIDC Login thành công nhưng callback thật lỗi

`WebTestClient.mutateWith(mockOidcLogin())` bỏ qua Token Endpoint/PKCE/JWKS.

**Định vị:** protocol integration test với Test OP và browser callback.

**Xử lý:** giữ unit/filter tests nhưng bổ sung full OIDC flow test.

### Tình huống I — Logout WebFlux trả 200 trước khi session invalidated

Một success handler tự subscribe vào `session.invalidate()` và trả `Mono.empty()`.

**Định vị:** PublisherProbe, controlled delayed session store.

**Xử lý:** compose session invalidation vào returned `Mono<Void>` và kiểm tra semantics HTTP/OP logout.

### Tình huống J — Provider timeout làm tất cả users bị xóa token

Một `onErrorResume` xử lý mọi error bằng `removeAuthorizedClient()`.

**Định vị:** TestPublisher/WebClient mock cho 503, kiểm tra authorized client store không bị xóa.

**Xử lý:** phân biệt transient timeout/503 với permanent `invalid_grant`; retry bounded và giữ security state.

### Tình huống K — JDBC đã chuyển qua boundedElastic nhưng vẫn nghẽn

Số thread pool/queue/DB connections không đủ, mỗi request tạo blocking query lâu.

**Định vị:** boundedElastic queue, DB pool latency, request backlog, thread dumps.

**Xử lý:** giảm blocking work, chuyển R2DBC hoặc caching được phép, bulkhead và timeout.

### Tình huống L — Claim mapper tạo side effect trước authorization

`Mono.just(loadSensitiveGroupData())` chạy ngay khi method được gọi, dù sau đó authorization bị từ chối.

**Định vị:** AtomicInteger counter trước subscription, PublisherProbe negative test.

**Xử lý:** `Mono.defer`/`fromCallable` và authorization sequencing đúng, không đọc sensitive data trước permission.

## 26. Checklist kiểm thử theo từng lớp

| Lớp | Câu hỏi phải trả lời | Công cụ |
| --- | --- | --- |
| Reactor semantics | Publisher có lazy, cold và retry đúng? | `StepVerifier`, counters |
| Subscription | Denied branch có chạm downstream? | `PublisherProbe` |
| Cancellation | Khi client disconnect, upstream có hủy? | `TestPublisher`, `doFinally` |
| Blocking | Có sleep/JDBC/sync SDK trên non-blocking thread? | BlockHound, thread dumps |
| Scheduler | Blocking được cô lập và có capacity? | Metrics, boundedElastic instrumentation |
| Security Context | Authentication có trong Reactor Context đúng user? | `StepVerifier.contextWrite` |
| Reactive method security | Denied không subscribe repository? | Method security + PublisherProbe |
| HTTP filter chain | Anonymous/OIDC users có status phù hợp? | `WebTestClient` |
| OIDC protocol | PKCE/ID Token/UserInfo validation thật? | Test OP + browser integration |
| Authorized client | Token save/load và refresh không race? | Mock provider + store |
| API | invalid_token/insufficient_scope đúng? | Mock Resource Server |
| Logout | Session được invalidate đúng và await? | Reactive session integration tests |
| Operations | Event-loop latency, retry storms, pool backlog? | Tracing/load tests |

## 27. Checklist trước khi merge code production

1. Không gọi `Mono.block()`/`Flux.blockLast()` trên Netty event loop.
2. Không có `subscribe()` rải rác trong WebFilter, authentication manager, user service, authorized-client manager, controller hay repository.
3. Blocking libraries được thay bằng reactive driver hoặc cô lập có giới hạn trên `boundedElastic`.
4. BlockHound tests chạy trên non-blocking schedulers/JVM configuration phù hợp.
5. Không whitelist BlockHound blocking calls trên diện rộng để test xanh.
6. Authorization decision được thực thi **trước** protected downstream publisher.
7. Unauthorized branch có `PublisherProbe.assertWasNotSubscribed()`.
8. Các publisher ghi audit/session/authorized client được **compose** và error policy rõ.
9. Reactive SecurityContext được đọc bằng `ReactiveSecurityContextHolder`, không dựa vào ThreadLocal.
10. Tests bao phủ thiếu context, wrong user, wrong tenant, thiếu role.
11. Test timeout/cancellation không mặc định remote operation chưa xảy ra.
12. Authorization code one-time và Refresh Token rotation không bị retry/subscription trùng vô tình.
13. Success/failure handlers không xóa nhầm token mới do concurrent refresh.
14. UserInfo `sub` must match ID Token `sub` trong protocol integration.
15. `WebTestClient.mockOidcLogin` không bị nhầm là real OIDC Token Endpoint test.
16. Không log ID/Access/Refresh Token, client secret, code, verifier, session cookie.
17. Token-bearing WebClient có trusted host/audience/scope, không dùng arbitrary URLs.
18. HTTP 401/403/503 được phân loại, không fail-open trong authorization.
19. Reactive transaction và WebSession persistence không bị tách bởi manual subscriptions.
20. Monitoring có event-loop latency, scheduler backlog, provider timeout, refresh failures và audit failures.

## 28. Câu hỏi ôn tập

**1. Tại sao `Mono.just(jdbcRepository.load())` không bảo vệ event loop?**

Vì `jdbcRepository.load()` được thực hiện ngay khi tạo Mono. Cần dùng reactive repository hoặc `Mono.fromCallable(...).subscribeOn(boundedElastic())` để trì hoãn và cô lập thao tác blocking nếu không thay driver được.

**2. BlockHound có phát hiện mọi blocking API không?**

Không. Nó instrument một tập blocking methods và phát hiện khi chúng chạy trên non-blocking threads phù hợp. Không thay thế performance test, code review hoặc context/subscription tests.

**3. Vì sao không gọi `subscribe()` bên trong `ServerAuthenticationSuccessHandler`?**

Vì framework đã subscribe vào returned `Mono<Void>`. Tự subscribe tạo child stream khó kiểm soát error/cancellation/context, có thể trả response trước khi audit/session persistence hoàn tất.

**4. `PublisherProbe.assertWasNotSubscribed()` kiểm tra được điều gì?**

Nó cho biết publisher của protected downstream branch chưa được subscribe, hữu ích để chứng minh authorization denial không kích hoạt API call.

**5. Đặt `subscribeOn(boundedElastic())` sau `Mono.just(blockingCall())` có giải quyết không?**

Không. Blocking call đã xảy ra trước khi `Mono.just` được tạo; scheduler chỉ ảnh hưởng publisher được subscribe sau đó.

**6. `Mono.when(authorize(), delete())` có bảo đảm authorize trước delete không?**

Không. Các publishers có thể được subscribe đồng thời. Với thao tác bảo vệ, cần sequencing và semantics deny rõ, ví dụ `authorize().then(Mono.defer(() -> delete()))`.

**7. Vì sao SecurityContext có thể mất khi tự subscribe?**

Reactive SecurityContext nằm trong Reactor Context gắn với subscriber chain; một subscription riêng không mặc nhiên kế thừa context của request.

**8. `mockOidcLogin()` có chứng minh ID Token signature và nonce đã validate?**

Không. Nó mô phỏng Authentication cho HTTP/filter/authorization tests. Full protocol cần test OP và callback/token/JWKS/UserInfo.

**9. Timeout khi refresh có chứng minh provider không rotate Refresh Token?**

Không. OP có thể đã xử lý nhưng client không nhận response. Retry cùng token cũ có thể `invalid_grant` hoặc gây token family invalidation.

**10. Vì sao cần test cancellation ở luồng logout?**

Vì nếu HTTP request bị cancel hoặc handler trả sớm, session cleanup/audit có thể chưa hoàn tất. Returned publisher phải quản lý kết quả và error policy phù hợp.

## 29. Tài liệu tham khảo

- Reactor — Reference Guide, Schedulers and Threading: https://projectreactor.io/docs/core/release/reference/coreFeatures/schedulers.html
- Reactor — Reference Guide, Context: https://projectreactor.io/docs/core/release/reference/advancedFeatures/context.html
- Reactor — Testing Reactor (`StepVerifier`, `TestPublisher`, `PublisherProbe`): https://projectreactor.io/docs/core/release/reference/testing.html
- Reactor — BlockHound repository/documentation: https://github.com/reactor/BlockHound
- Spring Security — Reactive Architecture: https://docs.spring.io/spring-security/reference/reactive/index.html
- Spring Security — Reactive Authentication: https://docs.spring.io/spring-security/reference/reactive/authentication/index.html
- Spring Security — Reactive Authorization: https://docs.spring.io/spring-security/reference/reactive/authorization/index.html
- Spring Security — Reactive OAuth2 Login: https://docs.spring.io/spring-security/reference/reactive/oauth2/login/index.html
- Spring Security — Reactive OAuth2 Client: https://docs.spring.io/spring-security/reference/reactive/oauth2/client/index.html
- Spring Security — Reactive OAuth2 Client Core: https://docs.spring.io/spring-security/reference/reactive/oauth2/client/core.html
- Spring Security — Reactive Testing: https://docs.spring.io/spring-security/reference/reactive/test/index.html
- Spring Security — WebTestClient Security Test Support: https://docs.spring.io/spring-security/reference/reactive/test/web/index.html
- Spring Security — Reactive Method Security: https://docs.spring.io/spring-security/reference/reactive/authorization/method.html
- Spring Security — `ReactiveSecurityContextHolder` Javadoc: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/core/context/ReactiveSecurityContextHolder.html
- Spring Security — `ServerOAuth2AuthorizedClientExchangeFilterFunction` Javadoc: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/client/web/reactive/function/client/ServerOAuth2AuthorizedClientExchangeFilterFunction.html
- Spring Framework — WebFlux Reference: https://docs.spring.io/spring-framework/reference/web/webflux.html
- Spring Framework — WebTestClient: https://docs.spring.io/spring-framework/reference/testing/webtestclient.html
- Spring Data R2DBC — Reference: https://docs.spring.io/spring-data/relational/reference/r2dbc.html
- OpenID Connect Core 1.0: https://openid.net/specs/openid-connect-core-1_0.html
- OAuth 2.0 Security Best Current Practice — RFC 9700: https://www.rfc-editor.org/rfc/rfc9700

## 30. Tổng kết: bảo mật Reactive đúng phải kiểm soát execution lifecycle

~~~text
HTTP request
   |
   v
Spring Security WebFlux
   |
   +-- Reactive Authentication / OIDC Login
   +-- Reactive Authorization / Method Security
   +-- OAuth2 Authorized Client Manager
   |
   v
Compose một Publisher graph
   |
   +-- Lazy source: Mono.defer / fromCallable
   +-- Non-blocking I/O hoặc boundedElastic nếu bắt buộc
   +-- SecurityContext trong Reactor Context
   +-- Authorization trước protected side effects
   +-- Correct error, cancellation, timeout handling
   |
   v
Spring WebFlux runtime subscribes
   |
   +-- StepVerifier kiểm tra signals
   +-- PublisherProbe kiểm tra branch subscription
   +-- TestPublisher kiểm tra cancellation
   +-- BlockHound phát hiện blocking trên non-blocking threads
   +-- WebTestClient kiểm tra filter/security boundaries
   +-- Test OP kiểm tra giao thức OIDC thực
~~~

**Sáu nguyên tắc cần ghi nhớ:**

1. **Blocking trong WebFlux nguy hiểm dù Authentication đúng.** Tìm JDBC, synchronous HTTP SDK, `Thread.sleep` và `block()` trong custom OIDC/security services; dùng BlockHound và load/latency telemetry để phát hiện.
2. **Không tự subscribe trong request/security services.** Trả về và compose `Mono`/`Flux` để framework sở hữu error, cancellation, context và persistence lifecycle.
3. **Authorization phải xảy ra trước protected operation.** `PublisherProbe` nên chứng minh denied path không subscribe API/repository; `Mono.when` không thay thế sequencing.
4. **ReactiveSecurityContextHolder thuộc Reactor Context.** Không dựa vào Servlet ThreadLocal; test context đúng subscriber và các nhánh missing/wrong Authentication.
5. **Timeout/cancellation và concurrent subscriptions có thể tạo security side effects.** Nhất là authorization code một lần, Refresh Token rotation, revoke và logout; cần idempotency/conditional persistence và retry policy theo protocol.
6. **Test nhiều lớp mới đủ tin cậy.** BlockHound, StepVerifier, TestPublisher, WebTestClient và mock OIDC Login giải quyết các lỗi khác nhau; vẫn phải có test OP/JWKS/UserInfo và kiểm thử hoạt động multi-instance.

Mục tiêu cuối cùng không chỉ là làm cho WebFlux trả HTTP 200, mà là **bảo đảm mỗi quyết định bảo mật chỉ kích hoạt đúng tác vụ được phép, trên đúng execution context, không blocking event loop và không tạo subscription nằm ngoài khả năng kiểm soát của hệ thống**.
