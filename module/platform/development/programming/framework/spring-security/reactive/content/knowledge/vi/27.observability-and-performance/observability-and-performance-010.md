# Retry, cache và cancellation: tác động đến an toàn bảo mật trong Spring Security Reactive

## Mục tiêu học tập

Trong Spring WebFlux, quá trình xác thực và phân quyền là một phần của **reactive pipeline**. Những tối ưu có vẻ chỉ liên quan đến hiệu năng — **thử lại (retry)** khi gặp lỗi, **bộ nhớ đệm (cache)** để giảm số lần đọc và **hủy đăng ký (cancellation)** khi client ngừng chờ — có thể làm thay đổi thời điểm kiểm tra quyền, danh tính được sử dụng, số lần thực thi tác vụ và khả năng ghi nhận sự kiện bảo mật.

Sau bài học, bạn có thể:

1. Giải thích vì sao retryWhen đăng ký lại upstream và có thể thực thi lại cả kiểm tra quyền lẫn side effect.
2. Phân biệt việc cache JWK, token introspection, danh tính, authority và quyết định phân quyền; thiết kế cache key, TTL, invalidation phù hợp ranh giới tenant.
3. Phân biệt onComplete, onError và cancel; hiểu các ảnh hưởng đối với cleanup, audit, truy vấn I/O và transaction.
4. Sử dụng ReactiveSecurityContextHolder/Reactor Context theo từng subscriber, tránh rò authentication qua shared publisher hoặc subscribe() không kiểm soát.
5. Viết test Java 17+ xác nhận retry có giới hạn, không thử lại credential sai, context không lẫn người dùng, và cancellation được quan sát.

**Phạm vi:** Spring Security WebFlux (reactive), Project Reactor Mono/Flux, JWT hoặc opaque-token Resource Server; ví dụ dựa trên Spring Security 6.x, Reactor 3.5+ và Spring Boot 3.x. Các tính chất của Servlet ThreadLocal không thay thế được Reactor Context.

## 1. Bảo mật thực thi khi publisher được subscribe

Sơ đồ đơn giản:

~~~text
HTTP client
  → SecurityWebFilterChain
      → xác thực JWT / opaque token / session
      → Authentication và SecurityContext
      → kiểm tra route-level authorization
  → WebFlux handler
      → service / method security
      → policy service, repository, downstream HTTP
  → response hoặc onError / cancel
~~~

Với publisher **cold**, việc xây dựng Mono/Flux (assembly) thường chưa gọi database/HTTP. Subscription mới kích hoạt nguồn; subscribe thêm một lần có thể gọi nguồn thêm một lần. Với **hot/shared publisher** hoặc Mono.cache(), dữ liệu có thể được chia sẻ cho nhiều subscribers. Spring Security Reactive dựa trên **Reactor Context theo subscription** để truyền SecurityContext, không phải một biến "current user" toàn cục.

- **onComplete:** upstream hoàn thành bình thường, có hoặc không có onNext.
- **onError:** upstream kết thúc bằng lỗi; downstream có thể áp dụng fallback hoặc retry.
- **cancel:** subscriber thông báo không cần thêm dữ liệu. Cancellation không tương đương với exception; một tác vụ bên ngoài đã commit **không tự rollback**.
- **retryWhen:** khi upstream phát onError phù hợp, Reactor **subscribe lại** nguồn theo chính sách, chứ không chỉ gọi lại phép tính thuần túy.
- **cache():** cache có thể thay đổi tính chất subscription, phát lại tín hiệu trước đó và thậm chí giữ upstream chạy dù subscriber đã hủy.

Nếu dùng sai, các operator trên có thể dẫn tới **fail-open** (lỗi xác thực nhưng vẫn cho phép), **stale authorization** (vẫn dùng quyền bị thu hồi), **cross-user data leak**, **duplicate side effect** hoặc **mất sự kiện audit**.

## 2. Retry: chỉ lặp lại thao tác an toàn và lỗi thích hợp

Một nguồn lạnh có thể chạy lại:

~~~text
subscription 1 → gọi dependency → lỗi
                      ↓ retryWhen
subscription 2 → gọi lại dependency → lỗi/hoàn tất
                      ↓ còn retry budget
subscription 3 → ...
~~~

Retry không tự biết thao tác có idempotent hay không. Nếu một POST đã ghi dữ liệu nhưng phía client nhận timeout, thử lại có thể tạo hai đơn hàng hoặc lặp yêu cầu thay đổi quyền. Retry đặt quanh một chuỗi vừa check permission, vừa ghi database, vừa gửi sự kiện có thể lặp **toàn bộ** chuỗi.

### 2.1. Phân loại lỗi theo ý nghĩa bảo mật

| Kết quả | Ý nghĩa | Có nên retry cùng credential/request? |
| --- | --- | --- |
| JWT sai chữ ký, sai issuer, hết hạn; opaque introspection trả active=false | Credential không hợp lệ; Resource Server thường trả **401** | **Không** retry cùng credential với hy vọng hợp lệ |
| Authentication thành công nhưng thiếu scope/role, không đủ ACL/tenant | Không được cấp quyền; thường trả **403** | **Không** retry để "vượt qua" quyết định cấm |
| Identity provider/policy service timeout, connection reset hoặc 5xx tạm thời | Hạ tầng kiểm tra quyền chưa sẵn sàng | Có thể retry **có giới hạn**, nếu operation idempotent và vẫn fail closed |
| HTTP 429 hoặc có Retry-After | Quota/rate limit | Chỉ retry theo quota, deadline, backoff phù hợp |
| Payload sai, converter lỗi, cấu hình issuer/JWK sai | Lỗi có tính hệ thống | Không retry mù quáng; sửa nguyên nhân |
| Transaction ghi không rõ đã commit hay chưa | Không chắc trạng thái side effect | Cần idempotency key, transaction/outbox và reconciliation trước khi thử lại |

**Fail closed** nghĩa là **không bao giờ** biến lỗi xác thực/phân quyền thành ALLOW. Nó **không có nghĩa** mọi lỗi hạ tầng phải giả thành 403: khi identity provider không khả dụng, ứng dụng có thể trả 503/5xx tùy thiết kế exception handler. Giữ sự phân biệt giữa credential không hợp lệ và dịch vụ cấp quyền gặp sự cố.

### 2.2. Bounded retry với filter và backoff

Đây là **mảnh mã trong service**, giả sử lookupPolicy(...) là request **đọc idempotent** và adapter đã ánh xạ lỗi hạ tầng tạm thời thành TemporaryPolicyServiceException:

~~~java
Mono<PolicyDecision> decision = Mono.defer(
        () -> policyClient.lookupPolicy(tenantId, subjectId, resourceId))
    .timeout(Duration.ofSeconds(2))
    .retryWhen(
        Retry.backoff(2, Duration.ofMillis(100))
            .maxBackoff(Duration.ofSeconds(1))
            .jitter(0.3)
            .filter(error -> error instanceof TemporaryPolicyServiceException)
    );

Mono<PolicyDecision> bounded = decision.timeout(Duration.ofSeconds(5));
~~~

Giải thích:

- Retry.backoff(2, ...) cho tối đa **2 lần thử lại**, cộng lần đầu thành tối đa **3 lần gọi nguồn**.
- filter loại lỗi credential/permission ra khỏi retry. Không dùng retryWhen mặc định bắt mọi lỗi cho lớp security.
- timeout ở **trước** retryWhen áp dụng cho mỗi lần thử; timeout ở **sau** retryWhen đặt giới hạn cho toàn bộ chuỗi.
- Backoff và jitter giảm đồng bộ retry giữa nhiều requests, nhưng vẫn cần kiểm soát số concurrent calls và circuit breaker/rate limit khi cần.
- Cần kiểm soát ngân sách độ trễ và cancellation; không giả định retry chỉ chạy một lần hoặc luôn kết thúc thành công.

Đoạn trên **không phải class Java độc lập**: PolicyDecision, policyClient, TemporaryPolicyServiceException và tham số là thành phần của ứng dụng thực.

### 2.3. Vị trí retry quyết định thứ gì lặp lại

~~~java
// Tập trung retry vào dependency đọc, an toàn để gọi lại.
Mono<PolicyDecision> lookup = policyClient.lookupPolicy(key)
    .retryWhen(transientRetry);

// NGUY HIỂM nếu cả chuỗi có side effect đã thực hiện một phần.
Mono<Result> wholeOperation = authorizeThenCreateOrder()
    .retryWhen(transientRetry);
~~~

Ở ví dụ thứ hai, nếu order được tạo rồi mới lỗi khi gửi event, resubscribe có thể tạo order lần nữa. Tách policy lookup khỏi transaction, dùng idempotency key, unique constraint và outbox trong ranh giới phù hợp. Nếu quyền phải đúng tới thời điểm commit, cần kiểm tra quyền **trong ranh giới nghiệp vụ nhất quán**, không chỉ ở đầu HTTP request.

### 2.4. Fallback gây lỗi bảo mật

~~~java
// PHẢN VÍ DỤ: lỗi dependency phân quyền → biến thành quyền truy cập.
Mono<Boolean> allowed = policyClient.isAllowed(subject, resource)
    .onErrorReturn(true);
~~~

Cách này có thể biến downtime thành truy cập trái phép. Giữ lỗi để security/error handler trả kết quả thất bại phù hợp; chỉ triển khai degradation cho nội dung được xác định rõ là công khai. Không áp dụng onErrorResume(... allow ...) chung cho mọi endpoint.

### 2.5. Retry và token refresh

Resource Server phải từ chối bearer token không hợp lệ; không tự làm cho JWT sai chữ ký thành hợp lệ bằng cách retry. Ở phía OAuth2 **client**, refresh token hợp lệ có thể được dùng để xin access token mới theo hợp đồng; việc gửi lại một request cần được giới hạn và phải bảo đảm an toàn khi replay, nhất là với mutation. Một vòng "401 → refresh/retry vô hạn" có thể tạo bão request hoặc lặp side effect.

## 3. Cache: quyền và danh tính có thời gian sống

Cache bảo mật có nhiều lớp:

- **JWK public keys:** cache khóa ký để giảm tải JWK endpoint, cần refresh khi key rotation/kid mới.
- **Opaque-token introspection:** cache trạng thái active, attributes, authorities; nguy cơ cấp quyền cho token đã bị revoke.
- **User roles/permissions:** nguy cơ một tài khoản đã bị hạ ROLE_ADMIN vẫn dùng cache cũ.
- **Authorization decisions:** nguy cơ dùng ALLOW của action/resource/tenant khác.
- **HTTP response/business data:** nguy cơ một người dùng nhận dữ liệu của người khác qua cache key sai hoặc shared HTTP/CDN cache.
- **Mono.cache()/Flux.cache():** nguy cơ phát lại chính Authentication hoặc SecurityContext từ subscription cũ.

### 3.1. Không cache ReactiveSecurityContextHolder trong singleton

~~~java
// PHẢN VÍ DỤ: shared field trong singleton service.
private final Mono<String> sharedUser =
    ReactiveSecurityContextHolder.getContext()
        .map(ctx -> ctx.getAuthentication().getName())
        .cache();
~~~

Reactor Context theo subscriber, nhưng Mono.cache() có thể lưu **giá trị của subscription đầu tiên**. Nếu Alice subscribe trước, Bob có nguy cơ nhận tên Alice từ sharedUser. Đây là lỗi xuyên người dùng, không phải tối ưu cache hợp lệ.

~~~java
// ĐÚNG: xây dựng logic lấy principal như cold publisher cho từng subscription.
public Mono<String> currentUserName() {
    return ReactiveSecurityContextHolder.getContext()
        .map(ctx -> ctx.getAuthentication().getName());
}
~~~

Nếu cùng một request cần dùng lại **một** kết quả repository đắt đỏ, có thể tạo Mono.cache() **bên trong request scope**, sau khi đã chốt principal đúng, và bảo đảm publisher không được giữ lại toàn cục. Điều này vẫn phải phù hợp với yêu cầu kiểm tra lại permission trước thao tác nhạy cảm.

### 3.2. Cache key không được bỏ qua ranh giới bảo mật

Quyết định "được chỉnh sửa report 42" có thể phụ thuộc:

~~~text
issuer / audience
+ subject / client identity
+ tenant
+ resource id / owner
+ action: read/write/approve
+ role / scope / principal attributes
+ permissionVersion / policyVersion
+ thời điểm, trạng thái tài nguyên hoặc môi trường áp dụng
~~~

Không dùng chỉ một key như "report-42", "ADMIN" hay "username" cho nhiều tenant hoặc hành động. Nếu phải biểu diễn token trong key, không đưa raw bearer token vào URL/log/metrics; dùng fingerprint được bảo vệ (ví dụ HMAC với khóa nội bộ) và kết hợp identity/issuer/tenant/policy metadata theo hợp đồng. Tránh log nguyên văn token, claims cá nhân hoặc secret introspection.

### 3.3. TTL, revoke và invalidation

Một giới hạn TTL minh họa cho cache dựa trên token:

~~~text
effectiveTTL <= min(configuredTTL,
                    tokenExpiresAt - now - clockSkew,
                    maximumPermittedRevocationDelay)
~~~

Nếu TTL tính được không dương, không tiếp tục dùng cache. Với JWT tự chứa, muốn revoke ngay có thể cần denylist, session version, token rất ngắn hạn hoặc kiểm tra một hệ thống ngoài; chỉ dùng TTL không bảo đảm thu hồi tức thời.

| Loại cache | Sai lầm | Khắc phục |
| --- | --- | --- |
| JWK key | Cache mãi key đã rotate | Dùng cache/refresh với thời gian hợp lý và phát hiện kid mới |
| Opaque introspection | active=true được giữ sau revoke | TTL bị chặn bởi expiry và yêu cầu revocation; hỗ trợ invalidation |
| Permission | ROLE_ADMIN vẫn còn sau khi hạ quyền | permissionVersion hoặc invalidation theo sự kiện; kiểm tra lại ở điểm quan trọng |
| Decision | ALLOW của người này được dùng cho người khác | Key theo subject, tenant, resource, action, policy version |
| Response | Rò data khi cache/CDN dùng chung | Cache-Control/Vary/key theo principal và tenant nếu thích hợp |
| Error/empty | Lỗi hạ tầng tạm thời bị giữ lâu | Kiểm soát negative/error caching riêng |

### 3.4. Mono.cache() lưu cả lỗi và không nhất thiết dừng source khi cancel

Theo semantics của Reactor:

- **Mono.cache()** có thể giữ kết quả, onComplete hoặc onError **không thời hạn** khi publisher còn tồn tại.
- **Mono.cache(Duration)** cũng replay **value, error hoặc empty completion** trong TTL. Vì vậy cache có thể biến lỗi tạm thời thành lỗi lặp lại nhiều lần dù dependency đã phục hồi.
- Một **Mono.cache() đã bắt đầu subscribe source** sẽ không nhất thiết cancel upstream khi downstream subscriber cancel; Reactor mô tả nguồn cache đã bắt đầu là không thể hủy theo cách cancel thường. Điều này ảnh hưởng chi phí và cleanup khi khách hàng ngắt kết nối.
- **cacheInvalidateIf / cacheInvalidateWhen** có thể invalidate giá trị đã lưu, nhưng không tự hiểu chính sách tenant, revoke, chữ ký hay expiry; các request race vẫn cần được đánh giá. Các API thiên về value, không cache error/empty giống cache() thông thường.

Vị trí operator cũng có ý nghĩa:

~~~java
// Retry trước cache: nếu hết budget, lỗi cuối vẫn có thể bị cache theo TTL.
Mono<String> a = remoteRead()
    .retryWhen(transientRetry)
    .cache(Duration.ofSeconds(30));

// Cache trước retry: retry có thể chỉ nhận lại đúng lỗi đã cache,
// không phát một HTTP call mới cho đến khi cache hết hạn.
Mono<String> b = remoteRead()
    .cache(Duration.ofSeconds(30))
    .retryWhen(transientRetry);
~~~

Hai đoạn là ví dụ cấu trúc, với remoteRead()/transientRetry có sẵn. Nếu chỉ muốn cache **giá trị thành công**, hãy dùng API/cấu trúc cache phù hợp và verify trường hợp error, empty, race và cancel. **Không cache Mono<Authentication> hoặc Mono<SecurityContext> toàn ứng dụng.**

## 4. Cancellation: client rời đi không đồng nghĩa công việc đã bị hoàn tác

Cancellation có thể đến từ client disconnect, timeout, chủ động dispose(), take(n), next(), switchMap() hủy nguồn trước hoặc một downstream operator không còn cần toàn bộ dữ liệu.

| Sự kiện | Reactor signal | Điều cần xét |
| --- | --- | --- |
| Kết quả thành công | onNext rồi onComplete, hoặc complete rỗng | Output đúng quyền; transaction/audit đã xử lý |
| Lỗi xác thực/quyền | onError hoặc HTTP 401/403 sau mapping | Không rò dữ liệu, không cho phép mặc định |
| Client disconnect / timeout | cancel có thể lan upstream | I/O bên ngoài đã gửi vẫn có thể tiếp tục; cleanup và audit |
| Shared/cached publisher còn subscriber khác | Cancel một subscriber | Upstream có thể vẫn hoạt động; không giả định nguồn dừng |

**Cancellation là best effort đối với upstream**, không phải cam kết distributed rollback. Một HTTP POST gửi đi có thể đã commit; việc người dùng tắt tab không làm bản ghi database biến mất. Một khi hệ thống đã chấp nhận lệnh nhạy cảm, phải có contract để truy vấn trạng thái và deduplicate request về sau.

### 4.1. doFinally quan sát đầy đủ ba trạng thái

~~~java
return securedOperation()
    .doFinally(signal -> {
        // ON_COMPLETE, ON_ERROR, CANCEL
        // Ghi metric không nhạy cảm; không in token hoặc PII.
        metrics.recordTermination(signal);
    });
~~~

doOnSuccess không quan sát error/cancel; đối với Mono hoàn thành rỗng, callback doOnSuccess còn có thể nhận null. doFinally có thể quan sát SignalType.CANCEL, phù hợp đếm số lần hủy và giải phóng tài nguyên **đồng bộ**. Callback không tự chờ một publisher async ghi audit.

**Phản ví dụ nguy hiểm:**

~~~java
return securedOperation()
    .doOnSuccess(result -> auditRepository.save(result).subscribe());
~~~

Đoạn này bỏ qua error/cancel, tự subscribe ra một luồng xử lý không liên kết tự động với request security context, transaction, cancellation và error handling. Dữ liệu audit có thể bị mất; cũng không có retry/dedup đáng tin cậy.

### 4.2. Cleanup không đồng bộ qua usingWhen

Đây là **mảnh thiết kế Java**, giả định leaseService.acquire(...) trả Mono<Lease>, lease.close() trả Mono<Void> và protectedWrite(...) trả Mono<WriteResult>:

~~~java
Mono<WriteResult> result = Mono.usingWhen(
    leaseService.acquire(resourceId),
    lease -> protectedWrite(lease, request),
    lease -> lease.close(),                 // normal completion
    (lease, error) -> lease.close(),        // error
    lease -> lease.close()                  // cancellation
);
~~~

usingWhen đưa cleanup async vào lifecycle cho các nhánh terminal; cleanup phải idempotent và lỗi cleanup phải được xử lý. Nó **không** tự thay thế DB transaction, timeout của distributed lock, crash recovery hoặc durable audit. Nếu process chết trước khi gửi cleanup, vẫn cần TTL/lease expiration hoặc cơ chế phục hồi.

### 4.3. Audit và nghiệp vụ phải bền vững ở đúng thời điểm

Đánh giá từng operation:

- **Chỉ đọc:** có thể cho phép cancel để tiết kiệm tài nguyên, với điều kiện không để lại tài nguyên hoặc quyền tạm thời vô chủ.
- **Đã chấp nhận tạo đơn/chi tiền/thu hồi token:** khi response HTTP bị cancel, server vẫn phải có cách xác định thao tác được chấp nhận có hoàn thành hay không. Dùng idempotency key, unique constraint, durable queue/job và endpoint trạng thái nếu phù hợp.
- **Audit bắt buộc:** cân nhắc outbox ghi cùng transaction nghiệp vụ, worker xử lý event với retry/dedup. doFinally và một fire-and-forget subscribe() không mang tính bền vững qua crash.
- **Kiểm tra quyền trước commit:** nếu thao tác kéo dài, hoặc quyền có thể bị revoke, chính sách phải định nghĩa thời điểm recheck/compare version trong giao dịch nhất quán.

Không phải mọi request đều cần queue. Chỉ những side effect có nghĩa vụ hoàn thành sau HTTP disconnect mới cần ranh giới bền vững tương ứng.

## 5. Reactor Context: ranh giới identity theo subscription

Spring Security Reactive cung cấp **ReactiveSecurityContextHolder**. Ví dụ truy cập tên principal trong luồng:

~~~java
public Mono<String> getCurrentUser() {
    return ReactiveSecurityContextHolder.getContext()
        .map(context -> context.getAuthentication().getName());
}
~~~

Nếu chưa có context xác thực, Mono có thể hoàn thành rỗng. Việc enforce access control vẫn cần SecurityWebFilterChain hoặc reactive method security; không tự tạo principal có quyền cao khi context trống. **Không** dùng giá trị userId từ query/header tự khai báo thay cho authentication thực.

Các sai lầm thường gặp:

1. Giữ Authentication trong static field hoặc singleton mutable field giữa các requests.
2. Cache SecurityContext/username ở Mono field toàn cục.
3. Gọi subscribe() tùy tiện trong service, tách rời request context và lỗi.
4. Dùng ThreadLocal để đọc principal trong scheduler/callback khác và giả định tương đương Reactor Context.
5. Tự contextWrite(withAuthentication(...)) bằng input không tin cậy để “khôi phục” danh tính.
6. Dùng authority chung như SCOPE_read mà quên kiểm tra **resource owner và tenant**.

Trong chuỗi Reactor đúng cách, publishOn/subscribeOn không mặc nhiên làm mất Reactor Context; rủi ro là **tách subscription, bridging đến API không hỗ trợ Reactor Context hoặc chia sẻ dữ liệu giữa subscribers**.

Ví dụ **mảnh method security**:

~~~java
@PreAuthorize("hasAuthority('SCOPE_reports.write')")
public Mono<Report> updateReport(String id, ReportChange change) {
    return repository.findById(id)
        .flatMap(report -> verifyTenantAndUpdate(report, change));
}
~~~

Cần bật @EnableReactiveMethodSecurity và gọi qua bean Spring để proxy xử lý annotation; ví dụ trên chưa phải class độc lập. hasAuthority chỉ kiểm tra chuỗi authority; muốn chặn truy cập chéo tenant phải có thêm kiểm tra của chính resource. Với operation thực thi sau hàng đợi, người dùng đã xác thực ở request đầu tiên không tự mang quyền vĩnh viễn vào job về sau.

## 6. Ví dụ Java 17+ có thể chạy: kiểm tra retry, identity, cancel

Bài test sau là **JUnit unit test thực thi Reactor**, không cần mở HTTP server. Nó làm rõ semantics trước khi bổ sung WebTestClient integration tests.

Nếu dùng dự án Gradle Spring Boot 3.x có WebFlux/Security, phần dependencies cần thiết có thể là (mảnh build.gradle, không phải file độc lập):

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-resource-server'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
    testImplementation 'io.projectreactor:reactor-test'
}
test {
    useJUnitPlatform()
}
~~~

Tệp **src/test/java/example/security/ReactiveSecurityOperatorTest.java**:

~~~java
package example.security;

import java.time.Duration;
import java.util.concurrent.atomic.AtomicInteger;

import org.junit.jupiter.api.Test;
import org.springframework.security.authentication.TestingAuthenticationToken;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.ReactiveSecurityContextHolder;
import org.springframework.security.core.context.SecurityContext;

import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;
import reactor.util.retry.Retry;

import static org.junit.jupiter.api.Assertions.assertEquals;

class ReactiveSecurityOperatorTest {

    static class TemporaryAuthServiceException extends RuntimeException {
    }

    static class InvalidCredentialException extends RuntimeException {
    }

    static Mono<String> currentName() {
        return ReactiveSecurityContextHolder.getContext()
                .map(SecurityContext::getAuthentication)
                .map(Authentication::getName);
    }

    @Test
    void retriesOnlyTemporaryDependencyFailures() {
        AtomicInteger calls = new AtomicInteger();

        Mono<String> lookup = Mono.defer(() -> {
            int attempt = calls.incrementAndGet();
            if (attempt < 3) {
                return Mono.<String>error(
                        new TemporaryAuthServiceException());
            }
            return Mono.just("policy-allow");
        }).retryWhen(
            Retry.backoff(2, Duration.ofMillis(1))
                    .jitter(0.0)
                    .filter(TemporaryAuthServiceException.class::isInstance));

        StepVerifier.create(lookup)
                .expectNext("policy-allow")
                .verifyComplete();
        assertEquals(3, calls.get());
    }

    @Test
    void doesNotRetryAnInvalidCredential() {
        AtomicInteger calls = new AtomicInteger();

        Mono<String> validation = Mono.defer(() -> {
            calls.incrementAndGet();
            return Mono.<String>error(new InvalidCredentialException());
        }).retryWhen(
            Retry.backoff(2, Duration.ofMillis(1))
                    .filter(TemporaryAuthServiceException.class::isInstance));

        StepVerifier.create(validation)
                .expectError(InvalidCredentialException.class)
                .verify();
        assertEquals(1, calls.get());
    }

    @Test
    void eachSubscriberGetsItsOwnSecurityContext() {
        Authentication alice =
                new TestingAuthenticationToken("alice", "unused", "SCOPE_read");
        Authentication bob =
                new TestingAuthenticationToken("bob", "unused", "SCOPE_read");

        Mono<String> current = currentName(); // cold, không cache

        StepVerifier.create(current.contextWrite(
                ReactiveSecurityContextHolder.withAuthentication(alice)))
            .expectNext("alice")
            .verifyComplete();

        StepVerifier.create(current.contextWrite(
                ReactiveSecurityContextHolder.withAuthentication(bob)))
            .expectNext("bob")
            .verifyComplete();
    }

    @Test
    void observesCancellation() {
        AtomicInteger cancellations = new AtomicInteger();

        Mono<String> pending = Mono.<String>never()
                .doOnCancel(cancellations::incrementAndGet);

        StepVerifier.create(pending)
                .thenCancel()
                .verify();

        assertEquals(1, cancellations.get());
    }
}
~~~

Chạy trong dự án Gradle có Spring Boot/dependency management đã được cấu hình:

~~~bash
./gradlew test --tests example.security.ReactiveSecurityOperatorTest
~~~

Với Windows PowerShell:

~~~powershell
.\gradlew.bat test --tests example.security.ReactiveSecurityOperatorTest
~~~

**Kết quả mong đợi:** 4 test PASS. Kiểm thử xác nhận lần lượt 3 lần gọi transient, chỉ 1 lần gặp credential sai, Alice và Bob được đọc đúng Reactor Context của riêng mình và callback cancel được gọi 1 lần. Class không in stdout; kết quả do JUnit/Gradle báo, không giả định chuỗi console cụ thể.

### 6.1. Thí nghiệm cho thấy lỗi cross-user cache

Mảnh mã dưới đây cố tình minh họa **anti-pattern**, không được lưu publisher shared như vậy trong ứng dụng:

~~~java
Mono<String> shared = ReactiveSecurityContextHolder.getContext()
    .map(ctx -> ctx.getAuthentication().getName())
    .cache();

// Alice subscribe trước; shared cache được nạp bằng "alice".
StepVerifier.create(shared.contextWrite(
        ReactiveSecurityContextHolder.withAuthentication(alice)))
    .expectNext("alice")
    .verifyComplete();

// Bob subscribe sau nhưng shared phát lại "alice": lỗi bảo mật.
StepVerifier.create(shared.contextWrite(
        ReactiveSecurityContextHolder.withAuthentication(bob)))
    .expectNext("alice")
    .verifyComplete();
~~~

Hai biến Authentication alice/bob được giả định đã khai báo như trong test chính. Đây là **test phơi bày một lỗi cố ý**, không phải assertion mong muốn trong production. Sửa bằng cold publisher theo từng subscription, hoặc cache ở request scope với kiểm soát ranh giới.

### 6.2. Cancellation với source đã cache

~~~java
Mono<String> sharedPending = Mono.<String>never()
    .doOnCancel(() -> metrics.recordUpstreamCancel())
    .cache();
~~~

Sau khi cache bắt đầu load, cancel ở subscriber phía dưới **không nhất thiết cancel upstream**. Không thể lấy số lần recordUpstreamCancel bằng 0 để kết luận mọi công việc đã dừng; kiểm tra connection/outstanding I/O và dùng giới hạn timeout ở adapter. Đây là đoạn minh họa; metrics là dependency giả định.

## 7. Khi ba operator tương tác: thứ tự sự kiện và race

Giả sử:

~~~text
t0  Alice đang có ROLE_EDITOR.
t1  Alice gọi cập nhật report; cached decision trả ALLOW.
t2  Admin revoke ROLE_EDITOR của Alice.
t3  Dependency bị timeout; retry kích hoạt subscription mới.
t4  Client đóng kết nối, downstream cancel.
t5  Lệnh ghi đã gửi vẫn có thể commit; audit nằm ở doOnSuccess không chạy.
~~~

Đây là **một rủi ro có điều kiện**, không phải khẳng định Spring WebFlux luôn xử lý theo đúng chuỗi trên. Nó phụ thuộc cách tách transaction, key/TTL của cache, vị trí retry và sự hợp tác của dependency khi cancel. Phải xác định rõ:

- Chính sách **freshness**: quyền kiểm tra ở t1 được phép sống bao lâu? Mutation quan trọng có cần recheck hoặc compare policyVersion khi commit?
- **Idempotency**: retry sau timeout có thể tạo bao nhiêu bản ghi? Unique constraint, request ID và transaction/outbox xử lý thế nào?
- **Revocation**: sự kiện quyền thay đổi tại t2 vô hiệu cache nào, qua nhiều instances ra sao?
- **Cancellation contract**: tác vụ nào được hủy an toàn, tác vụ nào đã chấp nhận và phải hoàn thành hoặc có trạng thái truy vết?
- **Context isolation**: lần retry/subscription mới lấy principal đúng request, không đọc shared stale Authentication?

Không có một operator duy nhất tự giải quyết đồng thời retry, cache, identity và durability.

## 8. Quan sát và đo lường lỗi đúng cách

Pipeline thường nên phân tách:

~~~text
SecurityWebFilterChain
 ├─ validate token / resolve Authentication
 ├─ reject invalid credential
 └─ check basic authority
      ↓
Application handler/service
 ├─ đọc principal từ Reactor Context
 ├─ kiểm tra tenant + resource ownership
 ├─ policy lookup: bounded retry chỉ cho lỗi transient
 ├─ mutation: idempotency, transaction, audit/outbox
 ├─ response
 └─ doFinally: metrics cho COMPLETE/ERROR/CANCEL
~~~

Các chỉ số cần đo riêng:

1. **Authentication fail (401)**, **authorization deny (403)**, **dependency unavailable (5xx/503)**. Không gộp tất cả thành “bad token”.
2. Số retry trên mỗi dependency, retry exhausted, backoff tổng, latency và áp lực hạ tầng.
3. Cache hit/miss, tuổi cache, số invalidation, độ trễ đồng bộ permissionVersion và số stale decision được phát hiện.
4. Cancellation count, thời gian cleanup và số request downstream vẫn đang chạy sau disconnect.
5. Idempotency key collisions/dedup, trạng thái durable job và backlog audit outbox.

Không log nguyên văn Authorization, JWT/opaque tokens, session cookies, private claims hoặc introspection response. Dùng correlation/request ID với quyền truy cập log phù hợp, cân nhắc cardinality của metric labels.

## 9. Ma trận kiểm thử tích hợp với Spring Security WebFlux

Các unit tests trên chứng minh behavior operator, **không** chứng minh SecurityWebFilterChain thực trả đúng HTTP status. Với WebTestClient và test doubles thích hợp cho ReactiveJwtDecoder / ReactiveOpaqueTokenIntrospector, kiểm tra thêm:

| Ca | Thiết lập | Điều cần xác nhận |
| --- | --- | --- |
| Không Authentication | Request không bearer/session | HTTP 401 theo entry point ứng dụng |
| JWT/opaque token không hợp lệ | Decoder/introspector báo credential lỗi | 401, không retry vô hạn, không fallback allow |
| Đã đăng nhập nhưng thiếu authority | Principal thiếu quyền | HTTP 403 và mutation không xảy ra |
| Policy service lỗi tạm 2 lần rồi OK | Fake trả lỗi transient 2 lần | Tổng 3 lần gọi, quyền đúng người/tenant |
| Policy service lỗi kéo dài | Fake luôn lỗi hạ tầng | Không được allow; trả failure phù hợp sau retry budget |
| Quyền bị thu hồi sau cache fill | Đổi permissionVersion/invalidate | Lần truy cập sau tuân thủ freshness contract |
| Hai principal đồng thời | Alice/Bob, hai tenant | Không có cache hoặc SecurityContext rò chéo |
| Source được cache rồi client cancel | Controlled Publisher/StepVerifier | Semantics cancel thực tế và resource budget được quan sát |
| Retry mutation sau timeout | Downstream commit nhưng response timeout | Chỉ một kết quả nghiệp vụ nhờ idempotency |
| Cache lưu lỗi | Lần đầu 5xx, sau đó phục hồi | Error caching không chặn phục hồi ngoài policy |
| Di chuyển scheduler/async bridge | publishOn và callback ngoài Reactor | Principal không sai, không phụ thuộc ThreadLocal |

Nếu dùng **mockJwt()** hoặc **mockOpaqueToken()**, bạn có thể test role/scope tại rule/method security; chúng thường đặt Authentication giả lập và **bỏ qua xác minh chữ ký, exp/issuer, introspection HTTP**. Để test decoder và token cache, gửi bearer header vào Resource Server thật với decoder/introspector stub ở đúng tầng, hoặc dùng server test nếu muốn xác minh cả JWK rotation và giao thức introspection. Tránh dùng mockJwt().authorities(...) rồi tuyên bố đã kiểm tra converter thực.

Khi test race/time, ưu tiên controllable publisher, StepVerifier virtual time hoặc đồng bộ sự kiện bằng latch; tránh Thread.sleep gây flaky. Nếu doFinally gửi signal xuống downstream trước khi callback hoàn tất, cần xác nhận metric/cleanup sau đúng điểm đồng bộ thay vì assert quá sớm.

## 10. Checklist an toàn trước production

- [ ] Retry có filter lỗi, max attempts, backoff/jitter và tổng deadline; **không** retry authentication/authorization denial.
- [ ] Không có onErrorReturn(true) hoặc fallback ALLOW khi kiểm tra quyền bị lỗi.
- [ ] Mutation có thể gửi lại được bảo vệ bằng **idempotency key + transaction/unique constraint**.
- [ ] Cache key tách đúng **principal, issuer, tenant, resource, action và policyVersion** nếu các trường này ảnh hưởng quyết định.
- [ ] Cache dựa trên token không vượt thời hạn token và mức trễ revoke cho phép; thiết kế invalidation và negative/error caching.
- [ ] Không cache SecurityContext/Authentication hoặc publisher lấy principal trong singleton dùng chung.
- [ ] Không đọc principal từ ThreadLocal hoặc request input không tin cậy trong reactive authorization.
- [ ] Không phụ thuộc subscribe() fire-and-forget hoặc doOnSuccess để bảo đảm audit.
- [ ] Cleanup xử lý success/error/cancel; tác vụ quan trọng cần durable queue/outbox hoặc cơ chế khôi phục.
- [ ] Có test 401, 403, 5xx, revoke sau cache fill, hai users/tenants, retry duplicate và cancellation.

## 11. Câu hỏi tự kiểm tra

1. Retry.backoff(2, ...) cho phép tối đa bao nhiêu lượt gọi? **3**: một lần đầu và hai lần thử lại.
2. JWT sai chữ ký có nên tự retry cùng token không? **Không**; đây là credential invalid, không phải lỗi mạng tạm thời.
3. Vì sao cache một Mono đọc ReactiveSecurityContextHolder ở singleton nguy hiểm? **Có thể phát lại context của subscriber đầu tiên cho người khác.**
4. Mono.cache(Duration) có cache onError không? **Có**, trong thời hạn TTL.
5. Client cancel có hoàn tác transaction đã commit không? **Không**.
6. doFinally(CANCEL) có bảo đảm audit bền vững qua crash không? **Không**; cần ranh giới durable.
7. Muốn kiểm thử token signature/expiry có thể chỉ dùng mockJwt() không? **Không**; phải kiểm tra decoder/validator hoặc luồng bearer thật.
8. Tại sao role cache cần permissionVersion hoặc invalidation? **Để hạn chế việc tiếp tục sử dụng quyền đã bị hạ/thu hồi.**

## 12. Nguồn tham khảo

- Spring Security — Reactive: https://docs.spring.io/spring-security/reference/reactive/index.html
- Spring Security — Reactive Method Security: https://docs.spring.io/spring-security/reference/reactive/authorization/method.html
- Spring Security — Reactive OAuth2 Resource Server: https://docs.spring.io/spring-security/reference/reactive/oauth2/resource-server/index.html
- Spring Security — ReactiveSecurityContextHolder API: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/core/context/ReactiveSecurityContextHolder.html
- Project Reactor — Error Handling / Retry: https://projectreactor.io/docs/core/release/reference/coreFeatures/error-handling.html
- Project Reactor — Context: https://projectreactor.io/docs/core/release/reference/advancedFeatures/context.html
- Project Reactor — Mono API: https://projectreactor.io/docs/core/release/api/reactor/core/publisher/Mono.html
- Project Reactor — RetryBackoffSpec API: https://projectreactor.io/docs/core/release/api/reactor/util/retry/RetryBackoffSpec.html

Ví dụ code đã phân biệt những phần có thể chạy độc lập như JUnit test với các mảnh minh họa phụ thuộc ứng dụng. Chính sách retry/cache/revocation/audit cụ thể phải tuân theo security và consistency contract của hệ thống.