# Kiểm thử method security Reactive bằng StepVerifier

## 1. Bài toán: annotation có thật sự chặn truy cập?

Trong Spring WebFlux, một service có thể trả `Mono<Document>` và được đánh dấu:

```java
@PreAuthorize("hasAuthority('DOC_READ')")
public Mono<String> readDocument(String id) {
    return repository.findTitle(id);
}
```

Developer thấy test `readDocument("42")` trả dữ liệu đúng rồi kết luận tính năng phân quyền đã hoạt động. Kết luận đó **chưa đủ**: test trên mới chỉ chứng minh nghiệp vụ trả kết quả, không chứng minh người thiếu quyền bị từ chối, người chưa xác thực bị chặn, một `Mono` lỗi không trở thành PERMIT, hay interceptor thực sự được Spring đăng ký.

Trong mô hình reactive, method security có thêm yếu tố quan trọng: **Authentication nằm trong Reactor Context của subscriber**, không mặc định là ThreadLocal mà một test bình thường có thể đọc qua `SecurityContextHolder`. `Mono`/`Flux` là publisher; kiểm tra quyền có thể diễn ra khi subscription được thực hiện. Vì vậy **StepVerifier** của `reactor-test` là công cụ phù hợp để kiểm thử chuỗi tín hiệu thực: giá trị, hoàn tất, từ chối bằng error, không phát dữ liệu khi bị từ chối, và các trường hợp timeout.

Bài tập trung vào đúng chủ đề **kiểm thử method security Reactive bằng StepVerifier**, không thay bằng việc chỉ thử HTTP 401/403. Chúng ta sẽ tạo một Spring-managed service thật, bật `@EnableReactiveMethodSecurity`, inject bean qua Spring AOP proxy và sử dụng `StepVerifier.create(...)` cùng `ReactiveSecurityContextHolder.withAuthentication(...)`.

### Sau bài học, bạn sẽ làm được

1. Kiểm tra grant và deny của `@PreAuthorize` trên `Mono` và `Flux`.
2. Đưa Authentication thử nghiệm vào Reactor Context bằng `contextWrite`.
3. Xác minh `AccessDeniedException` và **không có phần tử nhạy cảm nào được phát ra**.
4. Kiểm tra `@PostAuthorize` đối với đối tượng được trả về.
5. Dùng bean policy reactive trả `Mono<Boolean>` và kiểm tra fail-closed với empty/error.
6. Phân biệt `@WithMockUser`/test listener với việc inject authentication thủ công.
7. Test side effects và query subscriptions, tránh kết quả “403 nhưng đã ghi dữ liệu”.
8. Phát hiện self-invocation, tự tạo object bằng `new` và cấu hình thiếu `@EnableReactiveMethodSecurity`.
9. Dùng `StepVerifier.withVirtualTime(...)` cho timeout theo thời gian ảo khi phù hợp.
10. Biết khi nào cần thêm `WebTestClient` và JWT decoder integration tests.

## 2. Ba lớp cần tách trong một bộ kiểm thử

```text
              Test HTTP
WebTestClient / SecurityWebFilterChain
   - 401 chưa xác thực
   - 403 không được phép gọi route
                    |
                    v
             Test method security
         @EnableReactiveMethodSecurity
              Spring AOP proxy
          @PreAuthorize/@PostAuthorize
                    |
                    v
       Test reactive domain/repository
       tenant, owner, ACL, query scope
```

- **HTTP security test** chứng minh filter chain và route matcher chặn request. Một 403 ở HTTP chưa chứng minh `@PreAuthorize` trong service đã được gọi.
- **Method security test** chứng minh một Spring bean thực, có interceptor, từ chối khi chưa đủ điều kiện và cho phép khi đúng quyền. Đây là phần chính của bài.
- **Data security test** chứng minh bản ghi thuộc tenant/owner hoặc policy cụ thể. Một `hasAuthority('DOC_READ')` thành công không tự động thêm `WHERE tenant_id=...` vào database.

Để kiểm thử riêng method security, hãy cho controller/HTTP layer chấp nhận caller đã xác thực nhưng thiếu quyền chức năng, rồi quan sát **service method** trả 403 hoặc error. Ở mức test trực tiếp với StepVerifier, gọi bean service **thông qua Spring context**, không gọi controller.

### Phạm vi các assertion

```text
PERMIT:
  onNext(expectedData) -> onComplete

DENY:
  onError(AccessDeniedException)
  no onNext protectedData
  no data-side-effect

EMPTY RESULT khi caller được phép:
  onComplete, no onNext

EMPTY POLICY DECISION:
  fail closed, không coi là permit

POLICY ERROR/TIMEOUT:
  không có protectedData hoặc mutation
  error/deny được phân loại theo API contract
```

Việc một publisher hoàn tất rỗng khi caller **được phép** là bình thường (tài liệu không tồn tại). Nhưng một publisher **rỗng do không đưa ra quyết định quyền** không được tự biến thành PERMIT. Hai nguồn empty nằm ở **hai tầng khác nhau**, test phải thể hiện rõ.

## 3. Nền tảng: Reactor Context và thời điểm subscribe

Spring Security Reactive sử dụng `ReactiveSecurityContextHolder` để lấy `SecurityContext` từ Reactor Context. Tài liệu Spring Security 6.5 minh họa:

```java
Authentication alice = new TestingAuthenticationToken(
        "alice", "n/a", "DOC_READ");

Mono<String> who = ReactiveSecurityContextHolder.getContext()
        .map(SecurityContext::getAuthentication)
        .map(Authentication::getName)
        .contextWrite(
            ReactiveSecurityContextHolder.withAuthentication(alice));

StepVerifier.create(who)
        .expectNext("alice")
        .verifyComplete();
```

Đây là **snippet unit test**, cần imports của Spring Security, Reactor và reactor-test. Nó kiểm tra context nhưng **chưa chứng minh method security annotation** đã được áp dụng: không có protected Spring bean nào được gọi.

### Ý nghĩa của contextWrite

```text
Publisher khai báo ở test:
    service.read("42")
         |
         v
.contextWrite(withAuthentication(alice))
         |
         v
StepVerifier.subscribe()
         |
         v
Interceptor đọc Authentication từ Reactor Context
         |
         +-- GRANTED -> Mono<String> phát dữ liệu
         |
         +-- DENIED  -> Mono error, không phát dữ liệu
```

`contextWrite(...)` đặt context cho **upstream** của subscription đó. Không tạo một biến `SecurityContextHolder.getContext()` trong test thread rồi mong mọi scheduler nhận được.

### Vì sao không dùng block() để kiểm thử?

```java
// Cách này có thể kiểm tra giá trị, nhưng bỏ lỡ mô tả tín hiệu reactive.
String value = service.read("42").block();
```

`StepVerifier` cho phép assert cụ thể `expectNext`, `verifyComplete`, `expectError`, `expectNoEvent`, `thenCancel`, deadline và virtual time. Nó phù hợp với API phát `Mono`/`Flux` hơn việc dùng `block()` rồi bắt exception bằng JUnit theo kiểu đồng bộ. Nếu test có `block()` như một utility ở test thread thì không phải luôn sai, nhưng không phải công cụ tốt nhất cho bài học này và tuyệt đối không dùng `block()` trong WebFlux event loop.

## 4. Kiến thức cần có về Spring Security phiên bản

- Spring Security 5.8 giới thiệu `@EnableReactiveMethodSecurity(useAuthorizationManager = true)` cho infrastructure mới; trong 5.8 mặc định cờ này là **false**.
- Từ Spring Security 6.0, `useAuthorizationManager` mặc định là **true**. Với 6.x, `@EnableReactiveMethodSecurity` là cấu hình gọn.
- JavaDoc 7.0 cũng ghi mặc định là true; khi lên 7.x, kiểm tra API của bản minor/BOM cụ thể và chạy regression tests.
- Với Java reactive method security, phương thức được bảo vệ nên trả `Publisher`: `Mono<T>` hoặc `Flux<T>`, để tích hợp Reactor Context.
- `@EnableWebFluxSecurity`/`SecurityWebFilterChain` **không thay** `@EnableReactiveMethodSecurity`.
- `@EnableMethodSecurity` dùng cho đường method security thông thường; không mặc nhiên là annotation thay thế cho WebFlux reactive.

### Tại sao version quan trọng với test?

Một dự án 5.8 dùng legacy infrastructure có thể khác về extension point và hỗ trợ expression reactive so với cơ chế AuthorizationManager. Khi test có custom bean trả `Mono<Boolean>`, hãy xác nhận cấu hình đã bật `useAuthorizationManager = true` trên 5.8 hoặc đang dùng 6.x tương ứng.

### Project mẫu

Ví dụ phần lớn bài dùng Spring Boot **3.5.16** (Security 6.x do BOM quản lý), Java 17, JUnit 5, reactor-test. Đây là phiên bản cuối cùng của nhánh Boot 3.5 hỗ trợ OSS, theo thông báo Spring ngày 25/6/2026; dành cho demo học tập. Với production mới, dùng nhánh Boot còn được hỗ trợ và xác minh các APIs tương ứng. Không tự override riêng `spring-security-*` sang major 7.x bên trong Boot 3.5.

## 5. StepVerifier: các lệnh assertion cơ bản

| API | Ý nghĩa | Dùng cho security |
| --- | --- | --- |
| `StepVerifier.create(publisher)` | Subscribe và ghi kỳ vọng | Cần cho Mono/Flux được bảo vệ |
| `expectNext(value)` | Giá trị kế tiếp phải đúng | GRANT phát đúng document |
| `expectNextMatches(predicate)` | Kiểm tra record/projection | GRANT đúng tenant/owner |
| `expectNextCount(n)` | Xác nhận số lượng phần tử | Test Flux, không dùng thay ID assertion |
| `expectComplete()` + `verify()` | Nguồn hoàn tất | Stream được phép và kết thúc |
| `verifyComplete()` | Rút gọn expectComplete+verify | Mono/Flux thành công |
| `expectError(AccessDeniedException.class)` | Terminal signal là lỗi quyền | Method deny |
| `expectErrorMatches(...)` | Kiểm tra subtype/cause/message | Các phiên bản Spring hoặc lý do |
| `verifyError(...)` | Rút gọn error assertion | Denied path |
| `expectNoEvent(Duration)` | Không có event trong khoảng thời gian | Kiểm tra delay/backpressure; chú ý onSubscribe |
| `thenCancel()` | Cancel subscription | Flux vô hạn/timeouts |
| `withVirtualTime(supplier)` | Thời gian ảo | Retry/timeout/delay deterministic |

Một lỗi kiểm thử thường gặp:

```java
StepVerifier.create(service.read("42"))
        .expectNext("doc:42")
        .verifyComplete();
```

Nếu service gọi bằng Spring proxy nhưng không có Reactor SecurityContext, test có thể thất bại do không có Authentication. **Đừng chữa bằng cách tạo service bằng `new`**; hãy tạo principal và đưa vào Reactor Context.

Ngược lại, nếu test chỉ gọi `new DocumentService()` thì `@PreAuthorize` không hoạt động; một test 200 như vậy chưa chứng minh Spring Security.

## 6. Dự án đầy đủ: Java 17 + Spring Boot WebFlux + StepVerifier

Dự án sau tạo **Spring-managed bean thật**, gắn method annotations, và test qua `@SpringBootTest` không cần mở server. Có thêm bean policy trả `Mono<Boolean>` để kiểm tra tenant và fail closed.

```text
reactive-stepverifier-security/
├── pom.xml
└── src/
    ├── main/java/example/security/
    │   ├── ReactiveSecurityApplication.java
    │   ├── DocumentService.java
    │   └── TenantPolicy.java
    └── test/java/example/security/
        └── DocumentMethodSecurityTest.java
```

### 6.1. pom.xml

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
           https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.16</version>
        <relativePath/>
    </parent>

    <groupId>example</groupId>
    <artifactId>reactive-stepverifier-security</artifactId>
    <version>1.0.0</version>

    <properties>
        <java.version>17</java.version>
    </properties>

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
</project>
```

Dependency `reactor-test` cung cấp StepVerifier. `spring-boot-starter-test` cung cấp JUnit 5 và Spring testing; `spring-security-test` hữu ích cho `@WithMockUser` và authentication test helpers. Project dùng Security 6.x nên không cần ghi `useAuthorizationManager=true`.

### 6.2. ReactiveSecurityApplication.java

```java
package example.security;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.security.config.annotation.method.configuration
        .EnableReactiveMethodSecurity;

@SpringBootApplication
@EnableReactiveMethodSecurity
public class ReactiveSecurityApplication {

    public static void main(String[] args) {
        SpringApplication.run(ReactiveSecurityApplication.class, args);
    }
}
```

Import `EnableReactiveMethodSecurity` có thể viết một dòng:

```java
import org.springframework.security.config.annotation.method.configuration.EnableReactiveMethodSecurity;
```

**Điểm quan trọng:** annotation nằm trên configuration được Spring Boot scan; nó đăng ký các method interceptors. Bản thân `@SpringBootApplication` không đồng nghĩa method-level security luôn bật. Không cần mở HTTP server trong unit/integration test `@SpringBootTest(webEnvironment=NONE)`.

### 6.3. DocumentService.java

```java
package example.security;

import java.util.concurrent.atomic.AtomicInteger;

import org.springframework.security.access.prepost.PostAuthorize;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.SecurityContext;
import org.springframework.security.core.context.ReactiveSecurityContextHolder;
import org.springframework.stereotype.Service;

import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

@Service
public class DocumentService {

    private final AtomicInteger readSubscriptions = new AtomicInteger();
    private final AtomicInteger auditSubscriptions = new AtomicInteger();
    private final AtomicInteger tenantSubscriptions = new AtomicInteger();

    @PreAuthorize("hasAuthority('DOC_READ')")
    public Mono<String> read(String documentId) {
        return Mono.defer(() -> {
            readSubscriptions.incrementAndGet();
            return Mono.just("doc:" + documentId);
        });
    }

    @PreAuthorize("hasAuthority('DOC_READ')")
    public Mono<String> emptyWhenAllowed() {
        return Mono.empty();
    }

    @PreAuthorize("hasAuthority('AUDIT_READ')")
    public Flux<String> audit() {
        return Flux.defer(() -> {
            auditSubscriptions.incrementAndGet();
            return Flux.just("audit:1", "audit:2");
        });
    }

    @PreAuthorize("@tenantPolicy.canRead(authentication, #p0)")
    public Mono<String> readTenant(String requestedTenant) {
        return Mono.defer(() -> {
            tenantSubscriptions.incrementAndGet();
            return Mono.just("tenant:" + requestedTenant);
        });
    }

    @PostAuthorize("returnObject.owner == authentication.name")
    public Mono<OwnedDocument> owned(String id) {
        return Mono.defer(() ->
                Mono.just(new OwnedDocument(id, "alice")));
    }

    @PreAuthorize("hasAuthority('DOC_READ')")
    public Mono<String> currentUser() {
        return ReactiveSecurityContextHolder.getContext()
                .map(SecurityContext::getAuthentication)
                .map(Authentication::getName);
    }

    public int getReadSubscriptions() {
        return readSubscriptions.get();
    }

    public int getAuditSubscriptions() {
        return auditSubscriptions.get();
    }

    public int getTenantSubscriptions() {
        return tenantSubscriptions.get();
    }

    public static final class OwnedDocument {

        private final String id;
        private final String owner;

        public OwnedDocument(String id, String owner) {
            this.id = id;
            this.owner = owner;
        }

        public String getId() {
            return id;
        }

        public String getOwner() {
            return owner;
        }
    }
}
```

**Vì sao Mono.defer và Flux.defer?**

- `Mono.defer(...)` chỉ chạy phần tăng counter/tạo giá trị khi có subscription.
- Nếu `@PreAuthorize` từ chối **trước khi nguồn nghiệp vụ được subscribe**, `readSubscriptions` không tăng.
- `Flux.defer` làm tương tự để kiểm tra không có audit events bị phát khi caller thiếu `AUDIT_READ`.
- Getter counters không dùng làm bằng chứng bảo mật production; chỉ là phép đo side effect trong test.
- Method `owned` dùng `@PostAuthorize` kiểm tra owner trên giá trị trả về. Nó có thể đã tạo/đọc object trước khi check, nên **không** phù hợp để bảo vệ mutation gây side effect.
- `currentUser` giúp chứng minh Authentication được lấy từ Reactor Context trong quá trình thực thi.

Method `readTenant` gọi bean `tenantPolicy` bằng SpEL. `#p0` là tham số method thứ nhất theo vị trí, tránh phụ thuộc metadata tên tham số. Production nên dùng object-level policy phức tạp hơn và xác minh tenant từ membership server, không dựa vào tên tenant do client tự chọn.

### 6.4. TenantPolicy.java

```java
package example.security;

import org.springframework.security.core.Authentication;
import org.springframework.stereotype.Component;
import reactor.core.publisher.Mono;

@Component("tenantPolicy")
public class TenantPolicy {

    public Mono<Boolean> canRead(
            Authentication authentication, String requestedTenant) {

        if (authentication == null || requestedTenant == null) {
            return Mono.just(false);
        }

        Mono<Boolean> decision = switch (requestedTenant) {
            case "no-decision" -> Mono.empty();
            case "offline" -> Mono.error(
                    new IllegalStateException("PDP unavailable"));
            default -> Mono.just(
                    "alpha".equals(requestedTenant)
                    && "alice".equals(authentication.getName())
                    && authentication.getAuthorities().stream()
                        .anyMatch(a -> "DOC_READ"
                                .equals(a.getAuthority())));
        };

        // Chỉ một Boolean true tường minh mới được cấp quyền.
        return decision.defaultIfEmpty(false)
                .onErrorReturn(false);
    }
}
```

Đây là **chính sách mô phỏng**, không phải thiết kế đầy đủ để production. Nó mô tả ba nhánh quan trọng:

1. `alpha` + Alice + `DOC_READ` → `Mono.just(true)`.
2. `no-decision` → `Mono.empty()`, được chuẩn hóa thành false.
3. `offline` → `Mono.error(...)`, được chuẩn hóa thành false.

Sự cố PDP thực tế nên được ghi typed outcome/metrics riêng (không nhầm với DENY do policy), nhưng **không được chuyển thành true**. Trong production, tenancy phải dựa trên Authentication đã xác thực, membership/ACL từ nguồn đáng tin, resource tenant và action; chuỗi `"alpha"` hardcode chỉ để giữ test minh bạch.

## 7. Viết StepVerifier tests trên Spring-managed service thật

Tệp `src/test/java/example/security/DocumentMethodSecurityTest.java`:

```java
package example.security;

import static org.junit.jupiter.api.Assertions.assertEquals;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.authority.AuthorityUtils;
import org.springframework.security.core.context.ReactiveSecurityContextHolder;

import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;
import reactor.core.scheduler.Schedulers;
import reactor.test.StepVerifier;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.NONE)
class DocumentMethodSecurityTest {

    @Autowired
    DocumentService service;

    private static Authentication user(String name, String... authorities) {
        return new UsernamePasswordAuthenticationToken(
                name, "n/a",
                AuthorityUtils.createAuthorityList(authorities));
    }

    private static <T> Mono<T> as(
            Mono<T> source, Authentication authentication) {
        return source.contextWrite(
                ReactiveSecurityContextHolder.withAuthentication(authentication));
    }

    private static <T> Flux<T> as(
            Flux<T> source, Authentication authentication) {
        return source.contextWrite(
                ReactiveSecurityContextHolder.withAuthentication(authentication));
    }

    @Test
    void readerWithExactAuthorityCanRead() {
        StepVerifier.create(as(
                service.read("42"), user("alice", "DOC_READ")))
            .expectNext("doc:42")
            .verifyComplete();
    }

    @Test
    void viewerDeniedBeforeSourceIsSubscribed() {
        int before = service.getReadSubscriptions();

        StepVerifier.create(as(
                service.read("42"), user("viewer", "ROLE_VIEWER")))
            .expectError(AccessDeniedException.class)
            .verify();

        assertEquals(before, service.getReadSubscriptions());
    }

    @Test
    void rolePrefixIsNotExactDocReadAuthority() {
        StepVerifier.create(as(
                service.read("42"), user("alice", "ROLE_DOC_READ")))
            .expectError(AccessDeniedException.class)
            .verify();
    }

    @Test
    void noAuthenticationMustNotGrantAccess() {
        StepVerifier.create(service.read("42"))
            .expectError()
            .verify();
    }

    @Test
    void allowedEmptyResultIsCompletionNotDenial() {
        StepVerifier.create(as(
                service.emptyWhenAllowed(), user("alice", "DOC_READ")))
            .verifyComplete();
    }

    @Test
    void missingAuthorityDoesNotTurnEmptyIntoSuccess() {
        StepVerifier.create(as(
                service.emptyWhenAllowed(), user("viewer", "ROLE_VIEWER")))
            .expectError(AccessDeniedException.class)
            .verify();
    }

    @Test
    void auditFluxCanEmitTwoItemsWhenGranted() {
        StepVerifier.create(as(
                service.audit(), user("auditor", "AUDIT_READ")))
            .expectNext("audit:1", "audit:2")
            .verifyComplete();
    }

    @Test
    void auditFluxDenialEmitsNoProtectedItems() {
        int before = service.getAuditSubscriptions();

        StepVerifier.create(as(
                service.audit(), user("viewer", "ROLE_VIEWER")))
            .expectError(AccessDeniedException.class)
            .verify();

        assertEquals(before, service.getAuditSubscriptions());
    }

    @Test
    void postAuthorizeAcceptsRealOwner() {
        StepVerifier.create(as(
                service.owned("42"), user("alice", "DOC_READ")))
            .expectNextMatches(doc ->
                "42".equals(doc.getId())
                    && "alice".equals(doc.getOwner()))
            .verifyComplete();
    }

    @Test
    void postAuthorizeDeniesSomeoneElseDocument() {
        StepVerifier.create(as(
                service.owned("42"), user("bob", "DOC_READ")))
            .expectError(AccessDeniedException.class)
            .verify();
    }

    @Test
    void reactiveTenantPolicyGrantsValidCombination() {
        StepVerifier.create(as(
                service.readTenant("alpha"), user("alice", "DOC_READ")))
            .expectNext("tenant:alpha")
            .verifyComplete();
    }

    @Test
    void reactiveTenantPolicyDeniesWrongTenant() {
        int before = service.getTenantSubscriptions();

        StepVerifier.create(as(
                service.readTenant("beta"), user("alice", "DOC_READ")))
            .expectError(AccessDeniedException.class)
            .verify();

        assertEquals(before, service.getTenantSubscriptions());
    }

    @Test
    void emptyPolicyDecisionNeverBecomesPermit() {
        StepVerifier.create(as(
                service.readTenant("no-decision"),
                user("alice", "DOC_READ")))
            .expectError(AccessDeniedException.class)
            .verify();
    }

    @Test
    void policyBackendErrorNeverBecomesPermit() {
        StepVerifier.create(as(
                service.readTenant("offline"),
                user("alice", "DOC_READ")))
            .expectError(AccessDeniedException.class)
            .verify();
    }

    @Test
    void contextSurvivesReactiveSchedulerSwitch() {
        StepVerifier.create(as(
                service.currentUser(), user("alice", "DOC_READ"))
                    .publishOn(Schedulers.parallel()))
            .expectNext("alice")
            .verifyComplete();
    }

    @Test
    void sameColdPublisherUsesEachSubscribersAuthentication() {
        Mono<String> source = service.read("shared-id");

        StepVerifier.create(as(
                source, user("alice", "DOC_READ")))
            .expectNext("doc:shared-id")
            .verifyComplete();

        StepVerifier.create(as(
                source, user("bob", "ROLE_VIEWER")))
            .expectError(AccessDeniedException.class)
            .verify();
    }
}
```

Có **16 phương thức @Test**, bao phủ grant, deny, role/authority, thiếu Authentication, empty value, Flux, `@PostAuthorize`, policy reactive true/empty/error, scheduler switch và hai subscribers khác nhau trên cùng cold publisher.

### Những chi tiết giúp test thực sự có giá trị

- Test sử dụng `@SpringBootTest` và `@Autowired DocumentService`. Đây là **bean Spring-managed**, đi qua interceptor. Không thay bằng `new DocumentService()`.
- `new UsernamePasswordAuthenticationToken(name, "n/a", grantedAuthorities)` với constructor ba đối số tạo Authentication được đánh dấu authenticated. Đây là **identity giả cho unit/integration test**, không phải chứng minh mật khẩu/JWT thật.
- `contextWrite(withAuthentication(authentication))` đưa user vào Reactor Context **trên từng subscription**.
- `expectError(AccessDeniedException.class)` chấp nhận các subtype của AccessDeniedException như các exception authorization cụ thể của phiên bản.
- Counter giữ nguyên chứng minh nguồn dữ liệu `Mono.defer`/`Flux.defer` không bị subscribe khi before-method guard deny. Test chỉ assert HTTP 403 sẽ không phát hiện side effect đã chạy.
- `@PostAuthorize` kiểm tra **sau khi giá trị được tạo**, nên không thể dùng assertion zero reads như `@PreAuthorize`. Bài này chỉ dùng nó cho read-only DTO.
- `sameColdPublisher...` kiểm tra publisher không tự ghi nhớ PERMIT của Alice và phát lại cho Bob. Không nên gọi `.cache()` trên shared authorization Publisher của singleton.
- Các tests không dựa vào một HTTP route bảo vệ thay cho method layer; chúng kiểm tra trực tiếp proxy.

### Ghi chú về compile/runtime

Đây là project **runnable-by-design** với Maven/Java 17 và API Spring Security 6.x. Nếu chạy với nhánh Spring mới hơn, kiểm tra tương thích `@PostAuthorize`/reactive SpEL và version BOM. Bài viết không khẳng định mã đã được biên dịch và kiểm thử trong môi trường hiện tại; các assertions mô tả expected behavior phải được thực thi trong dự án thực.

## 8. Lệnh chạy và điều cần quan sát

Từ thư mục chứa `pom.xml`:

```bash
java -version
mvn -version
mvn -q clean test
```

Maven/Surefire báo cáo chi tiết tại `target/surefire-reports`. Kết quả cần đạt: các tests grant phát đúng values, các tests deny kết thúc bằng error như kỳ vọng, test owner không phát document cho Bob, policy empty/error không thành PERMIT và counters không tăng khi guard từ chối.

Không in giả một stdout từ Maven vì output phụ thuộc Maven, plugin và môi trường; dùng báo cáo test thực để xác nhận. Khi suite báo lỗi, **không thay `expectError` bằng `expectNext` để làm test xanh**: trước tiên kiểm tra cấu hình `@EnableReactiveMethodSecurity`, proxy, Reactor Context và policy expression.

### Những lỗi build cần kiểm tra

- `reactor.test.StepVerifier` không tìm thấy → thiếu `reactor-test` scope test.
- `ReactiveSecurityContextHolder` không tìm thấy → thiếu Spring Security reactive dependencies/version sai.
- `@EnableReactiveMethodSecurity` không có hiệu lực → configuration không được scan hoặc test không tải app context đúng.
- @PreAuthorize error khi parse SpEL → kiểm tra method visibility, bean name `tenantPolicy` và `#p0`.
- Context errors không đúng kỳ vọng → kiểm tra service có được proxy hay không và authentication có được đặt vào Publisher trước khi subscribe.
- No tests executed → kiểm tra file test/class name, JUnit 5/Surefire và Maven surefire reports.
- Nếu Boot 3.5.16 không được dùng vì dự án đã nâng lên Boot 4.x, hãy cập nhật BOM đồng bộ thay vì chỉ ép một artifact Spring Security.

## 9. Kiểm tra @PreAuthorize bằng StepVerifier theo cơ chế nào?

Luồng gọi thực tế:

```text
1. JUnit tạo test
2. Spring test context inject proxied DocumentService
3. Test gọi service.read("42") -> publisher có method-security advice
4. Test áp contextWrite(withAuthentication(reader/viewer))
5. StepVerifier subscribe
6. Advice đọc Authentication từ Reactor Context
7. SpEL đánh giá hasAuthority('DOC_READ')
8a. GRANT -> subscribe business Mono.defer -> onNext("doc:42")
8b. DENY  -> signal AccessDeniedException, không subscribe business Mono.defer
9. StepVerifier xác nhận onNext/onError/onComplete đúng thứ tự
```

**Tại sao có cả positive và negative tests?** Nếu không bật method security, positive test vẫn xanh vì service trả `doc:42`; chỉ negative test `viewerDenied...` có thể phát hiện đường bypass. Tương tự, test với chỉ một admin đủ quyền không phát hiện `@PreAuthorize` chưa đăng ký.

### Negative control có chủ đích

Trong một nhánh test tạm thời, bỏ annotation `@EnableReactiveMethodSecurity` nhưng giữ HTTP security: test viewer trên method trực tiếp sẽ không còn bị từ chối nếu không có enforcement nào khác. Đây là phép chứng minh test **đo đúng layer**. Không thực hiện thay đổi này trong production; chỉ dùng như thí nghiệm và hoàn nguyên.

### Khi DENY không phải AccessDeniedException?

Nếu policy bean ném ngoại lệ network/timeout chưa xử lý, upstream có thể phát error kỹ thuật chứ không phải AccessDeniedException. Khi đó test phải phản ánh API contract nhưng **không** được có onNext protected data. Trong ví dụ `TenantPolicy` đã chuyển empty/error thành false để method guard phát AccessDeniedException.

## 10. Khi nào dùng @WithMockUser thay vì contextWrite thủ công?

Spring Security Test có `@WithMockUser`, `@WithAnonymousUser`, `@WithUserDetails` và `@WithSecurityContext`. Với reactive method security, listener cần thiết không chỉ là `WithSecurityContextTestExecutionListener` cho test-thread security context, mà còn `ReactorContextTestExecutionListener` để đưa thông tin vào `ReactiveSecurityContextHolder`.

Ví dụ ý tưởng:

```java
@Test
@WithMockUser(username = "alice", authorities = "DOC_READ")
void canReadWithMockUserListener() {
    StepVerifier.create(service.read("42"))
            .expectNext("doc:42")
            .verifyComplete();
}
```

**Điều kiện:** cấu hình test context của dự án có `ReactorContextTestExecutionListener` đúng phiên bản; nếu tự khai danh sách `@TestExecutionListeners`, đừng vô tình bỏ listener này. Khi cần kiểm soát identity chính xác cho **mỗi subscriber**, `contextWrite(withAuthentication(...))` trực tiếp như project ở trên thường dễ đọc và ít phụ thuộc listener hơn.

### Test listener minh họa (snippet tích hợp)

```java
@TestExecutionListeners(
    listeners = {
        WithSecurityContextTestExecutionListener.class,
        ReactorContextTestExecutionListener.class
    },
    mergeMode = TestExecutionListeners.MergeMode.MERGE_WITH_DEFAULTS
)
```

Đoạn này cần import hai lớp listener từ `org.springframework.security.test.context.support` và `TestExecutionListeners` của Spring Test. Khi dùng cấu hình mặc định của Spring Boot, có thể đã có listeners cần thiết; không thêm trùng một cách máy móc. Nếu muốn dùng custom authentication/JWT principal, `@WithSecurityContext` hoặc `@WithUserDetails` phù hợp hơn `@WithMockUser` mặc định.

### Không nhầm test identity với authentication thực

- `@WithMockUser` không xác minh JWT chữ ký, `iss`, `aud` hoặc credentials người dùng thật.
- `TestingAuthenticationToken` hoặc `UsernamePasswordAuthenticationToken` do test tạo cũng không chứng minh login flow.
- Khi cần kiểm thử OAuth2 Resource Server, thêm `WebTestClient` hoặc test decoder bằng signed test JWT và security filter chain.
- Khi test truy cập tenant, user “alice” trong `@WithMockUser` không tự có membership tenant alpha trừ khi test data/policy tạo điều đó.

**Phân biệt HTTP test:** nếu gọi server thật trên thread/socket khác, `@WithMockUser` gắn ở JUnit thread không tự xác thực HTTP request. Cần dùng `WebTestClient` security test support hoặc đưa Basic/Bearer credentials vào request.

## 11. @PostAuthorize: test kết quả có quyền nhưng không che được side effect

`@PostAuthorize` kiểm tra giá trị **sau** method invocation và trước khi dữ liệu được trả về cho caller. Ví dụ:

```java
@PostAuthorize("returnObject.owner == authentication.name")
public Mono<OwnedDocument> getDocument(String id) {
    return repository.findById(id);
}
```

Bên trong project, `OwnedDocument#getOwner()` được dùng để SpEL đánh giá property `owner`. Vì có JavaBean getter nên biểu thức đơn giản và rõ hơn so với kỳ vọng parser tự hiểu mọi hình thức record property.

StepVerifier với Alice:

```java
StepVerifier.create(service.owned("42")
        .contextWrite(
            ReactiveSecurityContextHolder.withAuthentication(
                user("alice", "DOC_READ"))))
    .expectNextMatches(doc -> "alice".equals(doc.getOwner()))
    .verifyComplete();
```

StepVerifier với Bob:

```java
StepVerifier.create(service.owned("42")
        .contextWrite(
            ReactiveSecurityContextHolder.withAuthentication(
                user("bob", "DOC_READ"))))
    .expectError(AccessDeniedException.class)
    .verify();
```

Đây là **snippet gắn với project mục 6–7**: `user(...)` là helper private của test. Trong test thật, đảm bảo document của Bob chưa bị publish ra ngoài trước lỗi.

### Điều không nên làm

```java
@PostAuthorize("returnObject.owner == authentication.name")
public Mono<Receipt> transferMoney(...) {
    // Thao tác ghi được thực hiện trước khi post-check.
}
```

Ngay cả khi caller nhận 403, khoản tiền có thể đã chuyển. Dùng `@PreAuthorize` cho trước khi thực hiện và transaction/conditional update khi cần; `@PostAuthorize` không phải cơ chế rollback toàn bộ side effects mặc định.

### Khi method trả Flux

Khi áp `@PostAuthorize`/`@PostFilter` lên nhiều kết quả, phải kiểm tra **từng phần tử và cả trường hợp error/partial emission** theo contract phiên bản. Đặc biệt với `@PostFilter` sau phân trang DB, count/metadata có thể sai; ưu tiên query-time authorization khi làm search/count/stats. Bài này dùng `@PreAuthorize` trên Flux để chứng minh không emit item trước khi method guard cấp quyền.

## 12. Chứng minh không có dữ liệu bị đọc khi DENY

Chỉ assert:

```java
StepVerifier.create(viewerPublisher)
        .expectError(AccessDeniedException.class)
        .verify();
```

chứng minh luồng đã kết thúc bằng lỗi quyền, nhưng **chưa chứng minh thao tác bên trong không chạy** nếu method có side effect trước khi tạo Publisher.

Một nguồn reactive đúng cách:

```java
@PreAuthorize("hasAuthority('DOC_READ')")
public Mono<String> read(String id) {
    return Mono.defer(() -> {
        readSubscriptions.incrementAndGet();
        return repository.findTitle(id);
    });
}
```

Với test:

```java
int before = service.getReadSubscriptions();

StepVerifier.create(service.read("42")
        .contextWrite(
            ReactiveSecurityContextHolder.withAuthentication(viewer)))
    .expectError(AccessDeniedException.class)
    .verify();

assertEquals(before, service.getReadSubscriptions());
```

Ở đây counter tăng **khi subscribe vào nguồn nghiệp vụ**. Nếu `@PreAuthorize` deny trước đó, nguồn không được subscribe. Nếu dùng một method tạo/ghi DB đồng bộ **trước khi trả Mono**, counter test có thể không bắt trọn; phải di chuyển side effect vào publisher đúng cách và dùng transaction/data-level tests.

### Nguồn hot và side effect khởi động sớm

Một `Flux` hot hoặc một lời gọi ngoài reactive được kích hoạt ngay lúc method invocation có thể tạo dữ liệu trước khi authorization tại subscription. Hãy thiết kế service theo cold/deferred publishers cho dữ liệu bảo vệ:

```java
public Mono<Document> read(String id) {
    return Mono.defer(() -> repository.findById(id));
}
```

Nếu `repository.findById(id)` vốn đã trả Mono cold, `Mono.defer` có thể không cần; giá trị của nó trong bài là làm rõ thời điểm bắt đầu side effect.

Không biến `Mono.empty()` từ policy backend thành “không có tài liệu, vậy cho phép”. Một bên là authorization decision; một bên là business result. Chúng phải được xử lý khác nhau.

## 13. StepVerifier với Flux và nhiều phần tử

Một service:

```java
@PreAuthorize("hasAuthority('AUDIT_READ')")
public Flux<String> audit() {
    return Flux.just("audit:1", "audit:2");
}
```

Người có quyền:

```java
StepVerifier.create(service.audit()
        .contextWrite(
            ReactiveSecurityContextHolder.withAuthentication(auditor)))
    .expectNext("audit:1", "audit:2")
    .verifyComplete();
```

Người thiếu quyền:

```java
StepVerifier.create(service.audit()
        .contextWrite(
            ReactiveSecurityContextHolder.withAuthentication(viewer)))
    .expectError(AccessDeniedException.class)
    .verify();
```

StepVerifier đã yêu cầu **terminal error ngay**, không chấp nhận bất kỳ `onNext` nào trước khi error ở nhánh này. Nếu Flux đã emit một phần dữ liệu rồi mới phát lỗi, `expectError` sẽ thất bại vì sự kiện đến trước không được dự kiến.

### Kiểm tra số lượng không đủ để bảo vệ từng item

`expectNextCount(2)` chỉ chứng minh có 2 phần tử, không đảm bảo chúng thuộc tenant/owner hợp lệ. Với dữ liệu nhạy cảm, dùng `expectNextMatches(doc -> ...)`, `recordWith(...)`/`consumeRecordedWith(...)` hoặc list exact IDs để phát hiện record trái quyền.

### Flux vô hạn

Với stream dạng `Flux.interval(...)`, test cần `thenCancel` hoặc virtual time, tránh `verifyComplete()` mãi chờ stream vô hạn. Khi method security không cho phép, expectation là lỗi trước khi emit item; khi được phép, chỉ assert một số phần tử/đúng deadline rồi cancel.

## 14. Kiểm thử policy bean trả Mono<Boolean>

Spring Security AuthorizationManager-based reactive method security cho phép method security expression gọi bean trả `Mono<Boolean>`, ví dụ:

```java
@PreAuthorize("@tenantPolicy.canRead(authentication, #p0)")
public Mono<String> readTenant(String tenant) {
    return repository.loadForTenant(tenant);
}
```

Tuy nhiên, **không** mặc định mọi `Mono.empty()` từ bean policy là DENY của chính sách. Theo Spring Security, nó có thể biểu thị **abstain**. Nếu chính sách này là guard bắt buộc thì adapter phải normalize:

```java
Mono<Boolean> safeDecision = policyClient.check(subject, tenant)
        .defaultIfEmpty(false)
        .onErrorReturn(false);
```

Trong domain model thực, nên giữ error/timeout thành typed outcome để monitoring hoặc trả 503 thay vì 403; invariant là không tạo PERMIT.

### Ba test bắt buộc

- Tên/role/tenant đúng: `Mono.just(true)` → emitted business value.
- Backend trả empty: `Mono.empty()` được normalize thành false → `AccessDeniedException`, không chạy repository.
- Backend trả error: `Mono.error(...)` được normalize thành false → deny; nếu dự án propagate 503, assertion sẽ khác nhưng vẫn không emit business value.

Trong ví dụ `TenantPolicy`, lựa chọn `"offline"` và `"no-decision"` là test hooks cố định, không phải những tenant hợp lệ. Không đem các strings đặc biệt này vào hệ thống production.

### Timeout với bean policy

Một snippet tích hợp:

```java
Mono<Boolean> safeRemoteDecision =
        policyClient.checkRead(subject, resource)
            .timeout(Duration.ofMillis(250))
            .defaultIfEmpty(false)
            .onErrorReturn(false);
```

`Duration` cần import `java.time.Duration`; 250ms là ví dụ. Timeout làm phát error; `onErrorReturn(false)` bảo đảm không cấp quyền. Nếu dùng circuit breaker hoặc retry, vẫn phải ràng buộc deadline tổng và không fallback `true`.

## 15. Kiểm thử timeout bằng StepVerifier.withVirtualTime

Với một reactive publisher có `delayElement`/`Mono.delay`/`timeout`, dùng `withVirtualTime` để test không phải chờ đồng hồ thật.

Ví dụ minh họa độc lập trên Reactor:

```java
StepVerifier.withVirtualTime(() ->
        Mono.delay(Duration.ofMinutes(5))
            .map(ignored -> true)
            .timeout(Duration.ofSeconds(2))
            .onErrorReturn(false))
    .expectSubscription()
    .thenAwait(Duration.ofSeconds(2))
    .expectNext(false)
    .verifyComplete();
```

Đây là **snippet JUnit/reactor-test**, cần import `Duration`, `Mono`, `StepVerifier`. Tạo publisher **bên trong Supplier** của `withVirtualTime` để scheduler được thay bằng virtual scheduler trước khi source/operator dùng clock.

Nó chứng minh khi check chưa hoàn thành sau 2 giây ảo, kết quả thành false thay vì PERMIT. Đây chưa phải test method-security proxy; muốn test integration, đưa policy bean tạo source trong subscription và StepVerifier subscribe vào service proxied.

### Lưu ý withVirtualTime

- Đừng tạo publisher time-based trước khi `withVirtualTime` cài virtual scheduler.
- Nếu dùng custom scheduler không bị virtual time thay thế, test có thể vẫn chờ thật.
- `thenAwait` di chuyển thời gian ảo; có thể cần `thenRequest(n)` với các nguồn có backpressure.
- Với timeout của remote HTTP client thật, virtual time không thay thế test connect/read timeout bằng stub server; đây là hai tầng kiểm thử khác nhau.
- Đừng đặt một test `Mono.never()` rồi gọi `verifyComplete()` không có timeout: nó sẽ treo.

### Timeout và HTTP status

StepVerifier trên service thấy reactive error/decision. HTTP 503/403/401 là trách nhiệm của WebFlux filter chain/exception mapping và cần `WebTestClient` để test. Một error kỹ thuật không tự biến thành 403 nếu chưa được policy layer chuyển thành negative authorization result.

## 16. Giữ Reactor Context khi đổi Scheduler

Reactor chain có thể chuyển thread qua `publishOn`/`subscribeOn`. Method security reactive lấy Authentication từ Reactor Context, không nhất thiết từ thread-local servlet.

Một test:

```java
StepVerifier.create(
        service.currentUser()
            .contextWrite(
                ReactiveSecurityContextHolder.withAuthentication(
                    user("alice", "DOC_READ")))
            .publishOn(Schedulers.parallel()))
    .expectNext("alice")
    .verifyComplete();
```

Snippet gắn với project (cần `user` helper ở test). Bởi subscription context được mang theo chuỗi, method vẫn thấy Alice sau khi đổi scheduler. Test cần chạy đúng service bean đã được proxy; nếu trong implementation đọc `SecurityContextHolder.getContext()` của worker thread, có thể thấy principal không đúng hoặc null.

### Dùng Context không tự biến raw tenant thành trusted tenant

Ứng dụng có thể đặt `AuthorizedTenantScope` vào Reactor Context nhưng scope phải được sinh từ validated Authentication + membership server-side, không chỉ `X-Tenant-Id`. StepVerifier nên có test thay tenant raw header không làm đổi authorized scope, nhưng phải test cùng `TenantResolver` thực của dự án.

### Retry / repeat và nhiều subscriptions

Một cold publisher có thể được subscribe nhiều lần. `retry`/`repeat` cũng tạo subscriptions mới và có thể đánh giá lại policy. Không cache một `PERMIT` cho user A rồi đưa cho user B; nếu dùng cache, key phải gồm subject/tenant/resource/action/entitlement version và TTL.

## 17. Hai subscribers trên cùng một publisher: phép thử rất có giá trị

`Mono` tự nó thường cold. Nếu cùng source được subscribe dưới hai Reactor Context khác nhau, method security phải đánh giá quyền theo **mỗi subscriber**, không giữ Authentication toàn cục.

```java
Mono<String> shared = service.read("42");

StepVerifier.create(shared.contextWrite(
        ReactiveSecurityContextHolder.withAuthentication(
                user("alice", "DOC_READ"))))
    .expectNext("doc:42")
    .verifyComplete();

StepVerifier.create(shared.contextWrite(
        ReactiveSecurityContextHolder.withAuthentication(
                user("bob", "ROLE_VIEWER"))))
    .expectError(AccessDeniedException.class)
    .verify();
```

Nếu source/decision bị `cache()` sai phạm vi, Bob có thể nhận kết quả của Alice. Một service singleton có `Mono<Boolean> cachedDecision` được khởi tạo theo request đầu tiên là nguy hiểm. Thay vì cache publisher chung, cache những quyết định đã có key đúng subject/tenant/resource/action/revision và thời hạn theo chính sách.

**Cảnh báo:** tùy thiết kế source, việc tái dùng chính một Publisher được tạo ngoài context có thể giữ state khác. Bài này dùng nguồn cold, không khuyến nghị tạo shared publisher cho protected dữ liệu production. Test nhằm chứng minh **không có grant xuyên subscriber**.

## 18. Cách test self-invocation và proxy bypass

Ví dụ phản mẫu:

```java
@Service
class DocumentWorkflow {

    public Mono<String> outer(String id) {
        return protectedInner(id);
    }

    @PreAuthorize("hasAuthority('DOC_READ')")
    public Mono<String> protectedInner(String id) {
        return Mono.just("doc:" + id);
    }
}
```

`outer()` gọi `protectedInner()` bằng `this`; lời gọi nội bộ có thể không đi qua Spring AOP proxy, nên interceptor của `protectedInner` không được thực thi.

**Test chỉ gọi `service.protectedInner(...)` không đủ** nếu route thực tế gọi `service.outer(...)`. Cần negative test đúng đường đi runtime.

Giải pháp phù hợp hơn:

```java
@Service
class ProtectedDocumentReader {

    @PreAuthorize("hasAuthority('DOC_READ')")
    public Mono<String> read(String id) {
        return Mono.just("doc:" + id);
    }
}

@Service
class DocumentWorkflow {

    private final ProtectedDocumentReader reader;

    DocumentWorkflow(ProtectedDocumentReader reader) {
        this.reader = reader;
    }

    public Mono<String> outer(String id) {
        return reader.read(id); // Gọi qua bean khác đã proxy.
    }
}
```

Đây là **snippet tích hợp**; dependencies/annotations cần imports. Test inject `DocumentWorkflow` rồi gọi `outer` dưới reader/viewer Authentication: viewer phải nhận `AccessDeniedException`. Không gọi `new ProtectedDocumentReader()`; Spring chỉ áp advisors với beans do context quản lý.

### Private/final methods

Spring AOP proxy thông thường không intercept private method. Final classes/methods cũng có giới hạn với class-based proxy. Trước khi nghĩ rằng StepVerifier sai, kiểm tra method visibility, proxy class, cấu hình `proxyTargetClass` và liệu Java/Kotlin class có thể được proxy hay không.

## 19. Phân biệt thiếu Authentication và thiếu authority

Một user chưa xác thực và một user đã xác thực nhưng không có `DOC_READ` không giống nhau:

| Trường hợp | Với method StepVerifier | Với HTTP WebFlux |
| --- | --- | --- |
| Không có Authentication trong Reactor Context | Thường terminal error liên quan authentication/authorization; kiểm tra contract/version | Thường 401 nếu route cần auth |
| Authenticated viewer thiếu DOC_READ | `AccessDeniedException` | Thường 403 |
| Authenticated reader có DOC_READ | Data + complete | Thường 200 nếu controller thành công |
| Policy bean timeout | Error/deny theo adapter; không data | 503 hoặc 403 theo cách map |
| Resource không tồn tại trong authorized scope | Business Mono.empty hoặc not-found mapping | 404/empty theo API contract |
| Resource ở tenant khác | Không cấp quyền/không lộ data | 403/404 theo privacy policy |

Trong test `noAuthenticationMustNotGrantAccess`, ta không khóa quá chặt vào một exception subtype vì các phiên bản/đường advice có thể khác nhau; test quan trọng là **không có `onNext` bảo vệ** và kết thúc bằng lỗi. Với viewer đã xác thực, kỳ vọng `AccessDeniedException` rõ ràng hơn.

**Không dùng `onErrorResume(ex -> Mono.empty())` quanh authorization rồi coi test hoàn tất rỗng là an toàn** nếu controller phía sau có fallback lấy dữ liệu khác hoặc biến empty thành allow. Khi cần 404 che tài nguyên, xử lý cố ý tại API boundary và test không có data leak.

## 20. @WithMockUser, @WithUserDetails và security test listeners

Nhiều test suites Spring dùng annotation thay vì tạo Authentication thủ công:

```java
@Test
@WithMockUser(username = "alice", authorities = {"DOC_READ"})
void readerAuthorizedWithListener() {
    StepVerifier.create(service.read("42"))
        .expectNext("doc:42")
        .verifyComplete();
}
```

Để chạy với reactive method security:

- `@WithMockUser` tạo test SecurityContext; `ReactorContextTestExecutionListener` cần tham gia để chuyển test context phù hợp vào Reactor.
- Nếu test class dùng `@TestExecutionListeners(listeners=..., mergeMode=REPLACE_DEFAULTS)` và bỏ listener reactive, test có thể thất bại vì Context rỗng.
- `@WithMockUser(roles={"ADMIN"})` tạo `ROLE_ADMIN`; `authorities={"DOC_READ"}` tạo chính xác DOC_READ. Không nhầm `hasRole` với `hasAuthority`.
- `@WithUserDetails` yêu cầu user có trong test UserDetailsService; `@WithMockUser` không cần user thật.
- `@WithSecurityContext` cho phép dựng custom principal/JWT claims giả trong unit tests, nhưng không xác minh chữ ký thật.
- Dùng `contextWrite` là cách tường minh khi muốn thử hai users trong **cùng một test** mà không dựa vào JUnit listeners.

### Không trộn principal theo ThreadLocal

Một test có thể vừa gắn `@WithMockUser("alice")` vừa `contextWrite(withAuthentication(bob))`. Test trở nên khó hiểu. Nếu chủ ý kiểm tra Reactor Context ưu tiên, hãy ghi rõ kỳ vọng và tách hai luồng; còn thông thường chọn một cách xây Authentication để giảm nhiễu.

## 21. Testing với WebTestClient khác StepVerifier

**StepVerifier** tập trung vào publisher và method advice. **WebTestClient** tập trung vào HTTP:

```java
web.get()
   .uri("/api/documents/42")
   .headers(headers ->
        headers.setBasicAuth("viewer", "pass"))
   .exchange()
   .expectStatus().isForbidden();
```

Đây là snippet tích hợp yêu cầu `web` được tạo, HTTP SecurityWebFilterChain và credentials hợp lệ. Nó **không thay thế** StepVerifier trên bean, vì HTTP filter có thể trả 403 trước khi method được gọi.

### Thiết kế integration test rõ ranh giới

1. Bật `SecurityWebFilterChain` yêu cầu authenticated trên GET `/api/**`.
2. Gắn `@PreAuthorize("hasAuthority('DOC_READ')")` ở service.
3. Reader authenticated với DOC_READ → endpoint trả 200.
4. Viewer authenticated nhưng thiếu DOC_READ → endpoint trả 403 **do method**, vì HTTP layer đã cho qua authenticated.
5. Anonymous → 401 do HTTP.
6. Query document tenant khác → 403/404 hoặc response không chứa record theo chính sách dữ liệu.
7. Kiểm tra service invocation counters và DB state để chắc chắn không side effect.
8. Với JWT Resource Server, gửi test token qua security filter hoặc dùng mock support có chú thích phạm vi; `@WithMockUser` không kiểm tra decoder/chữ ký/audience.

### WebTestClient có thể assert response, không đo mọi tín hiệu backend

`WebTestClient` trả status/body của API; nó không luôn cho biết publisher có bị subscribe trước khi deny hay không. Dùng unit/integration StepVerifier và counters/mock repository để kiểm tra chính xác layer reactive, rồi thêm HTTP tests để bảo vệ end-to-end.

## 22. Test quyền trên dữ liệu, tenant và object-level security

`@PreAuthorize("hasAuthority('DOC_READ')")` không đảm bảo Alice được xem document của Bob hoặc tenant beta. Method security test phải kết hợp với repository policy test:

```java
@PreAuthorize("@documentPolicy.canRead(authentication, #p0)")
public Mono<DocumentView> read(String id) {
    return repository.findByIdAndAuthorizedTenant(id);
}
```

Đây là snippet kiến trúc. `documentPolicy` nên dựa trên principal đã xác thực, tenant membership và document metadata từ server; không tin raw tenant/owner trong request.

Ma trận nên seed:

| User | Tenant | Document | Quan hệ | Kỳ vọng |
| --- | --- | --- | --- | --- |
| Alice | alpha | Doc 11 alpha | owner | PERMIT |
| Alice | alpha | Doc 12 alpha | được share READ | PERMIT |
| Alice | alpha | Doc 13 alpha | private Bob | DENY |
| Alice | alpha | Doc 21 beta | cross-tenant | DENY |
| Bob | beta | Doc 21 beta | owner | PERMIT |
| Viewer không DOC_READ | alpha | Doc 11 alpha | dù là owner | DENY theo function policy |

Khi kiểm thử với StepVerifier, assert đúng document ID/tenant trong emitted result, không chỉ `expectNextCount(1)`. Dùng `Mono.defer` trong repository giả có counter để bảo đảm query không chạy khi local guard deny.

### Tránh TOCTOU với mutation

Nếu policy cho phép tại T1 nhưng owner/tenant/version của document đổi tại T2, một write có thể cần conditional SQL/transaction để ngăn race. StepVerifier test permission alone không thay thế mutation consistency tests. Với write quan trọng, kiểm tra affected rows và data state sau denial/race.

### Phân trang/thống kê

Method security chỉ quyết định method có được gọi; nếu đã được gọi, `Page.totalElements`, `count`, `facets`, `sum` cũng cần scope như danh sách. Một StepVerifier test trả `Flux<Document>` đúng IDs nhưng count chưa scoped vẫn có thể là data leak qua metadata.

## 23. StepVerifier và các bẫy logic Reactor

Khi một policy expression phụ thuộc nhiều reactive checks, phải đặc biệt lưu ý:

| Operator | Rủi ro với authorization |
| --- | --- |
| `Mono.zip(a,b)` | Nếu một nhánh empty, zip có thể hoàn tất empty; không tự coi đó là permit |
| `defaultIfEmpty(true)` | Không có quyết định thành ALLOW |
| `onErrorReturn(true)` | PDP outage thành ALLOW |
| `filter(Boolean::booleanValue).switchIfEmpty(Mono.just(true))` | DENY=false bị filter thành empty rồi grant |
| `Flux.all(...)` | Với tập rỗng, kết quả **true** theo vacuous truth |
| `Flux.any(...)` | Chỉ kiểm tra một nhánh grant, không thay AND bắt buộc |
| `hasElement()` | `Mono.just(false).hasElement()` vẫn true |
| `thenReturn(true)` | Bỏ qua upstream Boolean false và phát true |
| `Mono.when(...)` | Chỉ đợi completion, không AND các giá trị Boolean |
| `Mono.cache()` | Có thể giữ decision của subscriber khác nếu publisher bị chia sẻ |
| `retry()` không giới hạn | Tăng tải, delay và lẫn policy version |

StepVerifier tests nên có `Mono.just(true)`, `Mono.just(false)`, `Mono.empty()`, `Mono.error(...)` và `Mono.never()` với timeout hợp lý. Không dùng một bộ test toàn true để kết luận policy composition là an toàn.

Ví dụ test nhỏ:

```java
StepVerifier.create(
        Flux.<Boolean>empty().all(Boolean::booleanValue))
    .expectNext(true)
    .verifyComplete();
```

Đây là **đúng semantics Reactor**, nhưng **sai nếu hiểu “không có check” là PERMIT**. Khi các checks là required, kiểm tra danh sách không rỗng trước khi gọi `all` và normalize missing decisions thành false.

## 24. Ma trận regression tests cho Reactive Method Security

| # | Test | Kỳ vọng |
| --- | --- | --- |
| 1 | Caller DOC_READ đọc Mono document | Value đúng + complete |
| 2 | Caller authenticated thiếu DOC_READ | AccessDenied error |
| 3 | Không Authentication | Không emit protected data |
| 4 | ROLE_DOC_READ khác DOC_READ | DENY |
| 5 | Role ADMIN không tự có DOC_READ | DENY nếu policy yêu cầu exact authority |
| 6 | DOC_READ, business Mono.empty() | Complete rỗng hợp lệ |
| 7 | Viewer, business Mono.empty() | AccessDenied, không biến thành complete |
| 8 | AUDIT_READ, Flux nhiều items | Đúng IDs/items, complete |
| 9 | Viewer, Flux audit | No items, AccessDenied |
| 10 | `@PostAuthorize` owner đúng | Emit resource |
| 11 | `@PostAuthorize` owner khác | Không emit resource |
| 12 | Bean policy `Mono.just(true)` | PERMIT |
| 13 | Bean policy `Mono.empty()` | Fail closed |
| 14 | Bean policy `Mono.error(...)` | Fail closed, ghi lỗi vận hành |
| 15 | Bean policy timeout | No data/side effect |
| 16 | Tenant không khớp | DENY |
| 17 | Resource tenant không khớp | DENY |
| 18 | Self-invocation vào protected method | Test phát hiện đường bypass |
| 19 | Đối tượng tự tạo bằng new | Không coi annotation đã được enforce |
| 20 | Reactor `publishOn` | Identity vẫn đúng |
| 21 | Cùng cold Publisher, hai users | Không reuse quyền |
| 22 | Cache quyết định sai scope | Test phát hiện cross-user leakage |
| 23 | PostAuthorize sau một write | Test xác nhận rủi ro side effect, dùng precheck |
| 24 | HTTP authenticated viewer | 403 do service khi HTTP chỉ cần authenticated |
| 25 | HTTP anonymous | 401 |
| 26 | JWT issuer/audience/signature sai | Bị chặn ở auth boundary |
| 27 | `Flux.all` trên checks rỗng | Không được coi PERMIT |
| 28 | Retry/repeat nhiều subscriptions | Không reuse stale Authentication |
| 29 | Đổi owner giữa check/update | DB conditional predicate bảo vệ |
| 30 | Nâng Spring Security version | Grant/deny semantics không đổi ngoài migration có chủ đích |

Một suite production không nhất thiết mỗi hàng là một `@Test` riêng, nhưng cần bằng chứng coverage. Kiểm thử **denial** và **no side effects** quan trọng ngang kiểm thử happy path.

## 25. Các lỗi thường gặp khi học StepVerifier

**Lỗi 1 — Chỉ test `Mono.just("ok")`.** Chưa kiểm tra method security.

**Lỗi 2 — Gọi `new DocumentService()`.** Không đi qua Spring proxy nên `@PreAuthorize` có thể không áp dụng.

**Lỗi 3 — Quên `@EnableReactiveMethodSecurity`.** Annotation không tự kích hoạt chỉ vì đã thêm dependency Spring Security.

**Lỗi 4 — Dùng `SecurityContextHolder` của test thread trong reactive chain.** Context theo subscription có thể khác thread.

**Lỗi 5 — Quên `contextWrite(withAuthentication(...))` trong StepVerifier trực tiếp.** Publisher không có caller.

**Lỗi 6 — Cho rằng `@WithMockUser` luôn truyền vào Reactor Context dù test listeners bị thay.** Kiểm tra `ReactorContextTestExecutionListener`.

**Lỗi 7 — Dùng `block()` trong WebFlux service hoặc SpEL.** Có thể nghẽn event loop.

**Lỗi 8 — Chỉ test “được phép” mà không test DENY.** Bỏ qua interceptor vẫn làm happy path xanh.

**Lỗi 9 — HTTP cũng đã deny, rồi kết luận method guard chạy.** Tách ranh giới HTTP và service.

**Lỗi 10 — Chỉ assert error nhưng không assert side effects.** Có thể dữ liệu đã được ghi/fetch trước khi deny.

**Lỗi 11 — Dùng `@PostAuthorize` thay precheck cho mutation.** Post-check có thể quá muộn.

**Lỗi 12 — Nhầm ROLE_ prefix.** `hasRole('ADMIN')` khác `hasAuthority('ADMIN')`.

**Lỗi 13 — `Mono.empty()` policy được coi là permit.** Không có decision không phải grant.

**Lỗi 14 — `onErrorReturn(true)` cho policy remote.** Sự cố PDP mở quyền.

**Lỗi 15 — `Flux.all(empty)` trả true rồi dùng làm phép AND required rules.** Cần guard danh sách rỗng.

**Lỗi 16 — Dùng `hasElement()` trên Mono<Boolean>.** Một DENY=false cũng là emitted item.

**Lỗi 17 — Tạo hot/shared cached Publisher cho nhiều users.** Dễ lẫn AuthorizationResult/Context.

**Lỗi 18 — Dùng `expectNextCount` thay assert đúng ID/tenant.** Không phát hiện bản ghi trái quyền.

**Lỗi 19 — Dùng `StepVerifier.withVirtualTime` với Publisher tạo sớm.** Scheduler ảo có thể không được áp dụng.

**Lỗi 20 — Không kiểm tra dependency version sau migration.** Method/security infrastructure và test listener thay đổi có thể khiến test sai.

## 26. Checklist trước khi đưa vào CI/CD

- [ ] Application có `@EnableReactiveMethodSecurity` theo phiên bản đã khóa.
- [ ] Service method trả Mono/Flux và là Spring-managed proxied bean.
- [ ] Negative tests gọi đúng bean path thực tế, không bypass qua `new`/`this.method()`.
- [ ] StepVerifier dùng Reactor Context xác thực tại subscription.
- [ ] Có test GRANT đúng authority và DENY thiếu authority.
- [ ] Có test unauthenticated và role prefix.
- [ ] Có test Mono business empty khác policy decision empty.
- [ ] Có test Flux nhiều items, DENY không có onNext.
- [ ] Có test `@PostAuthorize` trên read-only resource và rủi ro side effect.
- [ ] Có test policy backend error/timeout fail closed.
- [ ] Có assertion counter/repository không chạy khi precheck deny.
- [ ] Có kiểm tra tenant, owner, ACL và DB query scope riêng.
- [ ] Có test Reactor Context qua Scheduler, retry/repeat hoặc nhiều subscribers nếu ứng dụng dùng.
- [ ] Có tests cache decision theo đúng subject/tenant/resource/action/TTL.
- [ ] Có thêm WebTestClient end-to-end cho HTTP 401/403/503.
- [ ] JWT tests không chỉ dùng @WithMockUser; đã kiểm tra issuer/audience/signature ở decoder boundary.
- [ ] `withVirtualTime` chỉ dùng cho reactive timers/timeout tương thích.
- [ ] Build Maven/JUnit chạy trong CI với BOM Spring Security/Reactor cụ thể.
- [ ] Không làm test xanh bằng cách chuyển error thành empty hoặc fallback allow.

**Kết luận:** Kiểm thử Reactive Method Security bằng StepVerifier không chỉ là “đọc được một giá trị”. Bằng cách dùng **Spring AOP proxy thật**, đưa Authentication vào **Reactor Context**, xác nhận cả **onNext/onComplete và onError**, và kiểm tra **không có side effect khi DENY**, bạn chứng minh được rằng `@PreAuthorize`, `@PostAuthorize` và chính sách reactive đang thực thi đúng. Hãy bổ sung `WebTestClient` để kiểm tra HTTP boundary và database/tenant tests để chứng minh không có dữ liệu vượt quyền.

## Tài liệu chính thức

- [Spring Security 6.5 — Reactive Method Security](https://docs.spring.io/spring-security/reference/6.5/reactive/authorization/method.html)
- [Spring Security 7.1 — Reactive Method Security](https://docs.spring.io/spring-security/reference/reactive/authorization/method.html)
- [Spring Security — Testing Method Security](https://docs.spring.io/spring-security/reference/servlet/test/method.html)
- [Spring Security — WebFlux Testing](https://docs.spring.io/spring-security/reference/reactive/test/index.html)
- [Spring Security — ReactiveSecurityContextHolder JavaDoc](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/core/context/ReactiveSecurityContextHolder.html)
- [Project Reactor — Testing with StepVerifier](https://projectreactor.io/docs/core/release/reference/testing.html)
- [Project Reactor — Reactor Context](https://projectreactor.io/docs/core/release/reference/advancedFeatures/context.html)
- [Project Reactor — StepVerifier JavaDoc](https://projectreactor.io/docs/test/release/api/reactor/test/StepVerifier.html)
- [Spring Boot 3.5.16 Release Notes](https://spring.io/blog/2026/06/25/spring-boot-3-5-16-available-now/)
