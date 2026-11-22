# Giới hạn block, subscribe thủ công và tác vụ tách khỏi chuỗi xử lý

> **Module:** Spring Security – authorization · **Chủ đề cha:** Method security Reactive. Bài học phân tích ba loại “thoát khỏi” chuỗi Reactor dễ gây lỗi trong WebFlux: gọi `block()` để chờ đồng bộ, gọi `subscribe()` thủ công bên trong tầng ứng dụng và khởi chạy tác vụ fire-and-forget bằng `@Async`/`CompletableFuture`/executor/queue mà không giữ ranh giới authorization. Trọng tâm không chỉ là hiệu năng: các cách này có thể làm sai thứ tự **kiểm quyền → truy cập dữ liệu → side effect → báo kết quả**, làm rơi authentication trong Reactor Context, bỏ qua cancellation/backpressure hoặc giấu lỗi sau một HTTP 200. Ví dụ Spring sử dụng Java 17+, Spring Boot 3.x, Spring Security 6.x, Spring WebFlux và Reactor 3.x. API cần đối chiếu khi dùng Spring Boot 4/Spring Security 7.

## 1. Kết quả học tập

Sau bài này, bạn có thể:

1. Giải thích **assembly** khác **subscription** và **completion** thế nào; biết ai sở hữu `subscribe()` trong một HTTP handler WebFlux.
2. Biết vì sao `Mono.block()`/`Flux.blockLast()` nguy hiểm khi gọi ở event-loop và vì sao chuyển blocking API vào `Mono.fromCallable(...).subscribeOn(Schedulers.boundedElastic())` chỉ là biện pháp cô lập có giới hạn.
3. Chứng minh `subscribe()` thủ công bên trong `map`/`doOnNext`/service tạo một subscription độc lập: lỗi, timeout, cancellation, Reactor Context và thứ tự side effects không còn do downstream HTTP subscriber quản lý.
4. Biến việc “gọi rồi bỏ mặc” thành `flatMap`, `concatMap`, `then`, `thenReturn` hoặc `Mono.when` tùy yêu cầu, để authorization và operation hoàn tất trong **cùng một publisher**.
5. Dùng `@EnableReactiveMethodSecurity`, `@PreAuthorize` và `ReactiveSecurityContextHolder` để bảo đảm method security không bị vượt qua bằng eager side effect hoặc self-invocation.
6. Xây một service có tenant-specific gate, không thực hiện protected write khi denied/không subscribe và trả lỗi đúng về caller.
7. Phân biệt request-bound work với **detached background job hợp lệ**; dùng transactional outbox và worker có workload identity, tenant scope, idempotency, retry, reauthorization.
8. Kiểm cancellation, retry, timeout, context propagation, exception và double subscription bằng `WebTestClient`/`StepVerifier`.
9. Tránh cache/hot/shared `Mono` chứa quyết định ALLOW cho actor khác; xác định effect của `publishOn`/`subscribeOn` đối với Reactor Context.
10. Chạy ví dụ Java 17 độc lập để thấy “eager”, “detached” và “deferred authorized” tạo kết quả khác nhau.

## 2. Nguyên tắc gốc: phương thức trả Publisher không phải tác vụ đã hoàn tất

Reactor thường dùng một **cold publisher**. Phần code dựng pipeline mô tả thao tác; phần lớn nguồn I/O bắt đầu **khi có subscriber**.

~~~text
assemble: controller -> service -> repository -> Mono/Flux được trả về
subscribe: Spring WebFlux server subscribes to publisher for HTTP response
signals: onSubscribe / request(n) / onNext / onError / onComplete / cancel
~~~

Một method:

~~~java
public Mono<Document> read(Long id) {
    return repository.findById(id);
}
~~~

trả về mô tả việc đọc. Nó **không** buộc DB đã đọc xong ngay sau lệnh `return`. WebFlux runtime là subscriber cuối cho request; nhờ đó authentication, request cancellation và lỗi trong pipeline có thể được quản lý thống nhất.

Ngược lại:

~~~java
public Mono<Document> read(Long id) {
    Document doc = blockingJpaRepository.findById(id).orElseThrow();
    return Mono.just(doc);
}
~~~

thực hiện blocking lookup **ngay khi Java method chạy**, trước khi publisher trả về. `Mono.just` không làm thao tác trước nó thành bất đồng bộ. Nếu side effect đã diễn ra trước khi reactive method security advice cấp quyền, việc trả về `Mono` không thể “thu hồi” side effect đó. Một nguyên tắc phòng thủ: **đặt mọi I/O và thay đổi dữ liệu phía sau một cold publisher và một authorization boundary đã được kiểm thử**.

### 2.1. Ba thời điểm cần phân biệt

| Thời điểm | Điều có thể xảy ra | Yêu cầu |
| --- | --- | --- |
| Assembly | Java tạo chain, kiểm tra input thuần không side-effect | Không query/write protected resource ngay |
| Subscription | Framework cung cấp Reactor Context, kích hoạt guard và source | Authn/authz phải đi trước protected I/O |
| Completion/Error/Cancel | Kết quả, lỗi, hoặc hủy truyền qua chain | Không báo success trước commit/required side effect |

**Lưu ý:** Một số publisher là hot/eager, future đã chạy, cached/sharing publisher, hoặc callback API có hành vi khác cold `Mono.defer`; không suy diễn mọi thứ trả `Publisher` đều lazy. Kiểm tra semantics của từng source.

## 3. block(): khi nào sai và khi nào là ranh giới chấp nhận được?

`Mono.block()` subscribe vào nguồn và **chặn thread hiện tại** để chờ giá trị; `Flux.blockFirst()/blockLast()` có hành vi tương tự. Các lời gọi `toFuture().get()`, `Future.get()`, `Thread.sleep` và JDBC/JPA/synchronous HTTP client trong event-loop cũng block dù không có chữ `block`.

Spring WebFlux/Netty sử dụng số lượng nhỏ event-loop threads. Một thread bị block giữ request I/O khác, gây latency và thread starvation. Trên những scheduler Reactor đánh dấu NonBlocking, `block()` thường ném `IllegalStateException` đại ý “blocking not supported”; nơi khác nó có thể không ném nhưng vẫn không nên dùng trong reactive request path.

### 3.1. Phản ví dụ: gọi block() trong manager hoặc controller

~~~java
// SAI: trích đoạn trong WebFlux/Reactive Method Security.
@PreAuthorize("hasAuthority('document:read')")
public Mono<DocView> read(String tenant, Long id) {
    boolean member = membershipClient.isMember(tenant).block();
    if (!member) {
        return Mono.error(new AccessDeniedException("No membership"));
    }
    return reactiveRepository.findByTenantAndId(tenant, id)
            .map(DocView::from);
}
~~~

Lỗi:
- `block()` tạo subscription thứ hai và chờ; có thể ném exception ở event-loop hoặc làm nghẽn thread.
- Context security của request **không mặc nhiên** sẵn trong subscription mới, nhất là nếu các operator/source kỳ vọng subscriber Context.
- Timeout, cancellation và metrics của outer chain không điều khiển được chính xác inner subscription.
- `Boolean` có thể null khi `Mono.empty()`; unboxing/null gây lỗi ngoài contract.
- Một permission check chạy ở chỗ không chắc đã có đúng actor là rủi ro bảo mật.

### 3.2. Đúng: flatMap giữ authorization trong pipeline

~~~java
// Trích đoạn trong Spring bean; membershipClient trả Mono<Boolean>.
@PreAuthorize("hasAuthority('document:read')")
public Mono<DocView> read(String tenant, Long id) {
    return membershipClient.isMember(tenant)
            .defaultIfEmpty(false)
            .flatMap(member -> member
                    ? reactiveRepository.findByTenantAndId(tenant, id)
                            .map(DocView::from)
                    : Mono.error(new AccessDeniedException("No membership")));
}
~~~

Trong thiết kế thực, `membershipClient` phải kiểm **principal đã xác minh từ Reactor Context**, tenant active và action; method ở trên chỉ minh họa operator, chưa đầy đủ authentication. Khi authority/tenant cần nhiều truy vấn reactive, dùng `flatMap`/`zipWhen` và fail closed, không `block()`.

### 3.3. Nếu bắt buộc gọi API blocking tạm thời

Mẫu chính thức của Reactor:

~~~java
Mono<LegacyResult> wrapped = Mono
        .fromCallable(() -> legacyClient.load(recordId))
        .subscribeOn(Schedulers.boundedElastic());
~~~

- `fromCallable` hoãn lời gọi blocking tới lúc subscription.
- `subscribeOn(boundedElastic)` chuyển quá trình subscribe/run source sang scheduler dành cho tác vụ blocking **có giới hạn**; nó **không gọi subscribe()** và không biến thư viện blocking thành non-blocking.
- Với các operator sau, kết quả vẫn đi qua cùng chain và error/cancellation được quản lý ở mức reactive signal.
- `boundedElastic` có giới hạn worker/queue: tăng tải có thể làm đầy queue; cần connection-pool, timeout, concurrency limit và quan trắc.
- Một blocking call đang chạy có thể không bị interrupt/rollback hoàn toàn ngay khi downstream cancel. Đừng hứa rằng cancel = đã hoàn tác DB write.
- Đặt `subscribeOn` gần nguồn `fromCallable` để không vô tình chạy đoạn blocking trước đó trên event-loop.

**Không dùng `Schedulers.parallel()` hoặc `Schedulers.single()` để thực hiện blocking I/O**, vì các scheduler này phục vụ việc không block. Giải pháp lâu dài với DB/HTTP là reactive driver (R2DBC, WebClient...) nếu lợi ích kiến trúc phù hợp; `boundedElastic` là cầu nối.

### 3.4. Không phải mọi block() đều bị cấm tuyệt đối

Ở **biên imperative chủ động sở hữu lifecycle**, ví dụ command-line `main`, migration script, một số phép thử JUnit ngoài event-loop, `block(Duration)` có thể hợp lý. Khi đó đã xác định thread, deadline và xử lý exception; không đặt trong WebFlux controller, reactive service/method-security manager hoặc pipeline được kỳ vọng non-blocking. Trong test reactive, `StepVerifier` thường làm semantics rõ hơn `block()`.

## 4. subscribe() thủ công: vì sao một cú gọi nhỏ gây bốn loại mất kiểm soát

Phản ví dụ:

~~~java
// SAI: giả sử publishAudit trả Mono<Void>.
public Mono<Receipt> approve(Command command) {
    return permissionGuard(command)
            .then(saveApproval(command))
            .doOnNext(saved -> publishAudit(saved).subscribe());
}
~~~

`doOnNext` không chờ publisher do `publishAudit` trả về. `subscribe()` tạo một subscription **khác** ngay trong callback. Hậu quả:
1. HTTP response có thể hoàn tất trước khi audit thành công hoặc thất bại.
2. Exception của audit không được truyền vào outer `Mono<Receipt>` như một phần của contract; có thể bị dropped/log thiếu correlation.
3. Nếu client hủy request, detached audit có thể vẫn chạy; nếu audit cần cancel theo request thì mất liên kết.
4. Reactor Context/SecurityContext của subscriber mới không được đảm bảo giống publisher cha; những dữ liệu `tenant`/`Authentication` có thể thiếu hoặc bị copy sai cách.

Điều này nguy hiểm nếu “audit” thực ra là kiểm quyền, thu tiền, gửi khóa truy cập, ghi outbox hoặc publish domain event bắt buộc. **Không được trả 200 khi phần bắt buộc còn là một task fire-and-forget chưa được giám sát.**

### 4.1. Đúng: một publisher cho tất cả tác vụ bắt buộc

~~~java
public Mono<Receipt> approve(Command command) {
    return permissionGuard(command)
            .then(saveApproval(command))
            .flatMap(saved ->
                    publishAudit(saved).thenReturn(saved));
}
~~~

`flatMap` đợi publisher nội bộ hoàn tất theo reactive composition. `thenReturn(saved)` chỉ emit receipt nếu audit kết thúc thành công; lỗi từ audit đi lên outer chain. Không cần `subscribe()` trong service. WebFlux runtime sẽ subscribe vào publisher cuối cho HTTP response.

Nếu muốn đảm bảo **DB mutation và outbox event cùng commit**, việc tuần tự hóa hai Mono chưa đủ vì database transaction có thể đã commit trước `publishAudit`. Dùng transactional outbox hoặc transaction reactive thực sự cho persistence chung, rồi dispatch event sau commit.

### 4.2. doOnNext/doOnSuccess không phải nơi thực hiện async business operation

~~~java
// SAI: result Mono của asyncAction bị bỏ qua.
return repository.save(doc)
        .doOnNext(saved -> asyncAction(saved));

// Cũng SAI: subscribe để “bắt nó chạy”:
return repository.save(doc)
        .doOnNext(saved -> asyncAction(saved).subscribe());
~~~

`doOnNext` phù hợp với **side effect đồng bộ, rất nhẹ** như tăng counter/log redacted. Nó không compose `Mono` khác. `doOnSuccess` của Mono còn có thể nhận `null` nếu Mono complete rỗng, nên code phải hiểu semantics. Với async work, dùng `flatMap`/`concatMap`/`then`.

### 4.3. Operator nào dùng cho tình huống nào?

| Ý định | Operator thường phù hợp | Ý nghĩa |
| --- | --- | --- |
| Kiểm quyền rồi chạy nghiệp vụ không cần giá trị guard | `guard.then(work)` | Chờ guard complete; lỗi dừng chain |
| Ghi bản ghi rồi gửi audit và trả bản ghi | `save.flatMap(x -> audit(x).thenReturn(x))` | Chờ audit trước khi emit x |
| Tìm resource rồi update theo value | `find.flatMap(this::update)` | Compose publisher per item |
| Xử lý dòng events theo thứ tự | `Flux.concatMap(this::handle)` | Bảo toàn thứ tự và tuần tự xử lý |
| Độc lập, tất cả phải thành công | `Mono.when(a,b)` | Completion của mọi nguồn; quan tâm giao dịch nếu có |
| Trả response sau khi chain hoàn tất | `thenReturn(response)` | Emit sau completion |
| Hủy nếu deadline vượt | `timeout(Duration)` | Emit lỗi timeout; side effect đã commit không tự rollback |
| Xử lý lỗi có điều kiện | `onErrorResume(...)` | Không được nuốt AccessDenied thành ALLOW |
| Thêm log nhẹ | `doOnEach(...)` | Có thể đọc signal/context; không gọi async subscribe bên trong |

**Không mặc định `Mono.when` bảo đảm “không có tác dụng phụ nếu một nguồn lỗi”**: các nguồn có thể chạy đồng thời. Nếu yêu cầu authorization trước mọi write, dùng `guard.then(work)`, không `Mono.when(guard, work)` vì work có thể bắt đầu trước guard thành công.

## 5. Nguy cơ đặc biệt trong Reactive Method Security

Spring Security reactive method security dùng Reactor Context qua `ReactiveSecurityContextHolder`. `@EnableReactiveMethodSecurity(useAuthorizationManager=true)` tích hợp method authorization vào Publisher return type như `Mono`/`Flux`. Khi method được gọi qua **Spring-managed proxy**, advisor có thể chặn trước hoặc sau invocation tùy annotation/config.

Phản ví dụ:

~~~java
// SAI: protected side effect đã bắt đầu trong lúc dựng method return.
@PreAuthorize("hasAuthority('document:write')")
public Mono<Void> delete(Long id) {
    externalBlockingClient.deleteNow(id); // eager I/O
    return Mono.empty();
}
~~~

Thậm chí nếu interceptor phiên bản hiện tại defer method invocation đúng lúc, side effect này làm code phụ thuộc chi tiết AOP/assembly thay vì đảm bảo trong Publisher. Refactor để mọi effect ở sau guard và trong source lazy, kiểm bằng test deny:

~~~java
@PreAuthorize("hasAuthority('document:write')")
public Mono<Void> delete(Long id) {
    return Mono.defer(() ->
            reactiveRepository.deleteById(id));
}
~~~

Đây là trích đoạn **chưa** có object/tenant authorization; với production phải kiểm actor, tenant, resource scope và transaction trước khi delete. Thay `deleteById` global bằng query đã tenant-scoped nếu ID không tự cấp bảo đảm tenant.

### 5.1. Method args không phải authenticated principal

~~~text
read(tenant="beta", id=7)
~~~

`tenant` chỉ là selector do client có thể thay. Trong WebFlux, lấy authentication từ `ReactiveSecurityContextHolder.getContext()` hoặc `Mono<Authentication>` do reactive interceptor cung cấp, rồi verify membership/roles của tenant đó. Không tin `userId`, `role`, `isOwner` truyền trực tiếp như quyền. Một manager `ReactiveAuthorizationManager<MethodInvocation>` có thể kiểm method args và authenticated actor bất đồng bộ trước khi cho phép.

### 5.2. Self-invocation bỏ qua proxy

~~~java
@Service
class DemoService {
    public Mono<String> outer() {
        return this.securedInner(); // nguy cơ bypass Spring AOP advice
    }

    @PreAuthorize("hasAuthority('admin')")
    public Mono<String> securedInner() {
        return Mono.just("protected");
    }
}
~~~

Trong proxy-based Spring AOP thông thường, `this.securedInner()` không đi qua proxy. Nếu `outer` đang được expose và không có bảo vệ tương đương, annotation ở inner method có thể không chạy. Tách secured service bean, gọi qua Spring proxy, kiểm test bean thực; không “chữa” bằng manual subscribe.

### 5.3. Method return Publisher là điều kiện quan trọng

Với Java reactive method security, phương thức bảo vệ nên trả kiểu reactive được hỗ trợ (`Mono`/`Flux`). Nếu trả plain object/`void` rồi bên trong dùng `subscribe()`, framework không còn Publisher kết quả để compose và enforce theo subscriber. Kotlin coroutines có hỗ trợ theo version/config khác; kiểm document của dependency đang chạy.

### 5.4. Reactor Context không phải ThreadLocal

~~~java
// SAI khi dùng cho identity trong reactive pipeline bất kỳ:
Authentication auth =
        SecurityContextHolder.getContext().getAuthentication();
~~~

Trong WebFlux, Reactor Context gắn với **subscriber**, không gắn vĩnh viễn với thread. `publishOn`/`subscribeOn` có thể đổi thread mà Reactor Context vẫn chảy qua các operator đúng, nhưng raw `ThreadLocal` hoặc `@Async` thread khác không tự nhận identity. Đọc đúng:

~~~java
Mono<String> currentUser =
        ReactiveSecurityContextHolder.getContext()
                .map(context -> context.getAuthentication().getName());
~~~

Đoạn này giả sử SecurityContext tồn tại; production cần xử lý empty/anonymous theo deny và hạn chế expose username trong logs.

### 5.5. Không tự subscribe vào auth Mono trong custom manager

~~~java
// SAI: đoạn trong ReactiveAuthorizationManager.
authentication.subscribe(a -> loadMembership(a.getName()));
return Mono.just(new AuthorizationDecision(true));
~~~

Đây là **cấp quyền trước khi kết quả membership tới**, classic TOCTOU/fail-open. Đúng là compose:

~~~java
return authentication
        .flatMap(auth -> memberships.canRead(auth.getName(), tenant)
                .map(AuthorizationDecision::new))
        .defaultIfEmpty(new AuthorizationDecision(false));
~~~

Đây chỉ là trích đoạn giả sử `tenant` đã validate, `memberships` dùng nguồn trusted, manager chữ ký API đúng version. Không viết logic độc lập ở đây nếu chưa có caller constraints. Khi membership lỗi, phải DENY/error-closed, không `onErrorReturn(new AuthorizationDecision(true))`.

## 6. Ứng dụng Spring Boot WebFlux: mọi bước bắt buộc ở chung một chain

Bài demo dùng:
- HTTP Basic user in-memory để học (không dùng mật khẩu `{noop}` trong production).
- HTTP GET có authentication gate; method `@PreAuthorize` kiểm feature authority.
- Tenant-specific membership **từ map do server quản lý** để tránh client giả.
- Store theo composite key `(tenant,documentId)`, hai tenant dùng cùng ID 7.
- Service `read` và `rename` luôn trả cold Publisher, không gọi `block()` hay `subscribe()`.
- `rename` là method nghiệp vụ có side effect để kiểm chứng **trước subscribe không có write**, và người bị deny không kích hoạt write. Nó không expose HTTP mutation route trong demo nên không cần nới lỏng CSRF; mutation được test bằng StepVerifier trên bean proxy.

Các file:
~~~text
src/main/java/demo/reactive/ReactiveBoundaryApplication.java
src/test/java/demo/reactive/ReactiveBoundaryApplicationTest.java
~~~

### 6.1. Mã ứng dụng hoàn chỉnh

Lưu `src/main/java/demo/reactive/ReactiveBoundaryApplication.java`:

~~~java
package demo.reactive;

import java.util.Map;
import java.util.Set;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.ConcurrentMap;
import java.util.concurrent.atomic.AtomicInteger;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.http.HttpStatus;
import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.security.authentication.AnonymousAuthenticationToken;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.method.configuration.EnableReactiveMethodSecurity;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.ReactiveSecurityContextHolder;
import org.springframework.security.core.context.SecurityContext;
import org.springframework.security.core.userdetails.MapReactiveUserDetailsService;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.web.server.SecurityWebFilterChain;
import org.springframework.stereotype.Component;
import org.springframework.stereotype.Service;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ResponseStatusException;

import reactor.core.publisher.Mono;

@SpringBootApplication
@EnableWebFluxSecurity
@EnableReactiveMethodSecurity(useAuthorizationManager = true)
public class ReactiveBoundaryApplication {
    public static void main(String[] args) {
        SpringApplication.run(ReactiveBoundaryApplication.class, args);
    }

    @Bean
    SecurityWebFilterChain security(ServerHttpSecurity http) {
        return http.authorizeExchange(ex -> ex
                    .pathMatchers("/api/tenants/**").authenticated()
                    .anyExchange().denyAll())
                .httpBasic(Customizer.withDefaults())
                .build();
        // Chỉ GET, không disable CSRF tùy tiện.
    }

    @Bean
    MapReactiveUserDetailsService users() {
        return new MapReactiveUserDetailsService(
                User.withUsername("alice")
                    .password("{noop}demo")
                    .authorities("document:read", "document:write")
                    .build(),
                User.withUsername("bob")
                    .password("{noop}demo")
                    .authorities("document:read", "document:write")
                    .build(),
                User.withUsername("viewer")
                    .password("{noop}demo")
                    .authorities("profile:read")
                    .build());
    }
}

record DocKey(String tenant, long id) {}
record Doc(long id, String tenant, String title) {}
record DocView(long id, String tenant, String title) {}

@Component
class TenantMemberships {
    private final Map<String, Map<String, Set<String>>> rights = Map.of(
            "alice", Map.of("alpha", Set.of("READ", "WRITE")),
            "bob", Map.of("beta", Set.of("READ")),
            "viewer", Map.of("alpha", Set.of("READ")));

    Mono<Boolean> has(String principal, String tenant, String action) {
        return Mono.defer(() -> Mono.just(
                rights.getOrDefault(principal, Map.of())
                    .getOrDefault(tenant, Set.of())
                    .contains(action)));
    }
}

@Component
class DocStore {
    private final ConcurrentMap<DocKey, Doc> data =
            new ConcurrentHashMap<>(Map.of(
                new DocKey("alpha", 7L),
                    new Doc(7L, "alpha", "ALPHA:Budget"),
                new DocKey("beta", 7L),
                    new Doc(7L, "beta", "BETA:Budget"),
                new DocKey("alpha", 8L),
                    new Doc(8L, "alpha", "ALPHA:Notes")));

    private final AtomicInteger writeCount = new AtomicInteger();

    Mono<Doc> findWithinTenant(String tenant, Long id) {
        return Mono.defer(() ->
                Mono.justOrEmpty(data.get(new DocKey(tenant, id))));
    }

    Mono<Doc> rename(String tenant, Long id, String newTitle) {
        // Mutation chạy khi SUBSCRIBE, không chạy khi tạo Mono.
        return Mono.defer(() -> {
            Doc changed = data.computeIfPresent(
                    new DocKey(tenant, id),
                    (key, old) -> new Doc(
                            old.id(), old.tenant(), newTitle));
            if (changed != null) {
                writeCount.incrementAndGet();
            }
            return Mono.justOrEmpty(changed);
        });
    }

    int writes() {
        return writeCount.get();
    }
}

@Service
class DocumentService {
    private final TenantMemberships memberships;
    private final DocStore store;

    DocumentService(TenantMemberships memberships, DocStore store) {
        this.memberships = memberships;
        this.store = store;
    }

    private Mono<Void> requireTenantAction(String tenant, String action) {
        if (tenant == null
                || !tenant.matches("[a-z][a-z0-9-]{0,31}")) {
            return Mono.error(new AccessDeniedException("Invalid tenant"));
        }

        return ReactiveSecurityContextHolder.getContext()
                .map(SecurityContext::getAuthentication)
                .switchIfEmpty(Mono.error(
                        new AccessDeniedException("No Authentication")))
                .flatMap(auth -> {
                    if (auth == null || !auth.isAuthenticated()
                            || auth instanceof AnonymousAuthenticationToken) {
                        return Mono.<Void>error(
                                new AccessDeniedException("Unauthenticated"));
                    }
                    return memberships.has(auth.getName(), tenant, action)
                            .defaultIfEmpty(false)
                            .flatMap(allowed -> allowed
                                    ? Mono.<Void>empty()
                                    : Mono.<Void>error(
                                            new AccessDeniedException(
                                                "Tenant/action denied")));
                }).then();
    }

    @PreAuthorize("hasAuthority('document:read')")
    public Mono<DocView> read(String tenant, Long id) {
        if (id == null || id <= 0) {
            return Mono.error(new AccessDeniedException("Invalid ID"));
        }
        return requireTenantAction(tenant, "READ")
                .then(store.findWithinTenant(tenant, id))
                .switchIfEmpty(Mono.error(
                        new ResponseStatusException(HttpStatus.NOT_FOUND)))
                .map(d -> new DocView(
                        d.id(), d.tenant(), d.title()));
    }

    @PreAuthorize("hasAuthority('document:write')")
    public Mono<DocView> rename(
            String tenant, Long id, String newTitle) {
        if (id == null || id <= 0 || newTitle == null
                || newTitle.isBlank() || newTitle.length() > 180) {
            return Mono.error(new AccessDeniedException("Invalid input"));
        }
        return requireTenantAction(tenant, "WRITE")
                .then(store.rename(tenant, id, newTitle))
                .switchIfEmpty(Mono.error(
                        new ResponseStatusException(HttpStatus.NOT_FOUND)))
                .map(d -> new DocView(
                        d.id(), d.tenant(), d.title()));
    }
}

@RestController
@RequestMapping("/api/tenants/{tenant}/documents")
class DocumentController {
    private final DocumentService service;

    DocumentController(DocumentService service) {
        this.service = service;
    }

    @GetMapping("/{id}")
    Mono<DocView> get(@PathVariable("tenant") String tenant,
                      @PathVariable("id") Long id) {
        return service.read(tenant, id);
    }
}
~~~

**Phạm vi của ví dụ:**
- Spring WebFlux nhận HTTP request; `@PreAuthorize` bảo vệ feature authority qua Spring-managed service proxy.
- `requireTenantAction` lấy Authentication từ Reactor Context của subscriber; membership trong memory chỉ là PIP demo.
- `Mono.defer` giữ cả read/write lazy. Không có bất kỳ `subscribe()` hay `block()` trong application service.
- `then(store.rename(...))` chỉ cho write chạy nếu authorization chain **complete thành công**. Nếu `requireTenantAction` trả `Mono.error(AccessDeniedException)`, store không nhận subscription.
- Hai tenant có ID 7 trùng nhau nhưng `DocKey(tenant,id)` giữ isolation.
- `writeCount` giúp kiểm chứng side effect chỉ xảy ra sau subscription có quyền.
- `rename` **không** expose HTTP PATCH/POST để tránh phức tạp CSRF trong ví dụ; trong production HTTP mutation cần CSRF protection thích hợp nếu có cookie/browser credentials, authorization đồng bộ với transaction, optimistic version/tenant predicate.
- Không có object-specific ACL; nếu user trong cùng tenant nhưng chỉ được đọc subset, phải thêm kiểm ACL/owner trước khi trả nội dung.
- `{noop}` password và local HTTP chỉ dùng cho demo, production dùng HTTPS và password hashing/token validation.
- Với thực tế, dùng R2DBC/reactive store hoặc cách ly blocking DB I/O có kiểm soát; map trong code không thay thế query `WHERE tenant_id=:tenant`.

### 6.2. Gradle dependencies

Trong một project đã cấu hình Spring Boot Gradle plugin/dependency management và Java 17+:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
    implementation 'org.springframework.boot:spring-boot-starter-security'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
    testImplementation 'io.projectreactor:reactor-test'
}
~~~

Đây là đoạn `dependencies`, không phải `build.gradle` đầy đủ. Mẫu không thêm MVC starter; khi trộn WebFlux và MVC cùng classpath, Spring Boot có quy tắc lựa chọn web application type cần kiểm soát. Các class test ở mục sau dùng Boot 3.x.

### 6.3. Thử HTTP

~~~bash
./gradlew bootRun

curl --user alice:demo http://localhost:8080/api/tenants/alpha/documents/7
curl --user bob:demo http://localhost:8080/api/tenants/beta/documents/7
curl --user bob:demo http://localhost:8080/api/tenants/alpha/documents/7
curl --user viewer:demo http://localhost:8080/api/tenants/alpha/documents/7
~~~

Kỳ vọng:
- Alice→alpha/7: 200 với `ALPHA:Budget`.
- Bob→beta/7: 200 với `BETA:Budget`.
- Bob→alpha/7: 403 do membership.
- Viewer→alpha/7: 403 vì thiếu feature authority.
- Anonymous: HTTP Basic thường trả 401.

Đây là thử nghiệm local; không gửi Basic credentials qua mạng HTTP công cộng. Trước production, cấu hình TLS/JWT/session đúng threat model.

## 7. Integration tests: authorization, laziness và không có detached side effect

Tạo `src/test/java/demo/reactive/ReactiveBoundaryApplicationTest.java`:

~~~java
package demo.reactive;

import java.util.List;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.core.context.ReactiveSecurityContextHolder;
import org.springframework.test.annotation.DirtiesContext;
import org.springframework.test.web.reactive.server.WebTestClient;

import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;

import static org.junit.jupiter.api.Assertions.assertEquals;

@SpringBootTest(
        webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
@AutoConfigureWebTestClient
@DirtiesContext(classMode = DirtiesContext.ClassMode.AFTER_EACH_TEST_METHOD)
class ReactiveBoundaryApplicationTest {
    @Autowired WebTestClient client;
    @Autowired DocumentService service; // Spring-managed AOP proxy.
    @Autowired DocStore store;

    private Authentication actor(String username, String authority) {
        return UsernamePasswordAuthenticationToken.authenticated(
                username, "unused",
                List.of(new SimpleGrantedAuthority(authority)));
    }

    @Test
    void authorizedAlphaAndBetaSameIdNeverMix() {
        client.get().uri("/api/tenants/alpha/documents/7")
                .headers(h -> h.setBasicAuth("alice", "demo"))
                .exchange().expectStatus().isOk()
                .expectBody().jsonPath("$.title")
                .isEqualTo("ALPHA:Budget");

        client.get().uri("/api/tenants/beta/documents/7")
                .headers(h -> h.setBasicAuth("bob", "demo"))
                .exchange().expectStatus().isOk()
                .expectBody().jsonPath("$.title")
                .isEqualTo("BETA:Budget");
    }

    @Test
    void unauthorizedRequestDoesNotReadAcrossTenant() {
        client.get().uri("/api/tenants/alpha/documents/7")
                .headers(h -> h.setBasicAuth("bob", "demo"))
                .exchange().expectStatus().isForbidden();
    }

    @Test
    void viewerLacksFeatureAuthority() {
        client.get().uri("/api/tenants/alpha/documents/7")
                .headers(h -> h.setBasicAuth("viewer", "demo"))
                .exchange().expectStatus().isForbidden();
    }

    @Test
    void noSubscriptionMeansNoProtectedWrite() {
        Authentication alice = actor("alice", "document:write");
        Mono<DocView> action =
                service.rename("alpha", 7L, "ALPHA:Updated")
                        .contextWrite(
                          ReactiveSecurityContextHolder.withAuthentication(
                                  alice));

        assertEquals(0, store.writes()); // assembly không ghi.
        StepVerifier.create(action)
                .expectNextMatches(v ->
                        v.title().equals("ALPHA:Updated"))
                .verifyComplete();
        assertEquals(1, store.writes()); // subscribe và GRANT mới ghi.
    }

    @Test
    void deniedTenantWriteNeverTouchesStore() {
        // Bob có global document:write nhưng beta membership chỉ READ.
        Authentication bob = actor("bob", "document:write");
        Mono<DocView> action =
                service.rename("beta", 7L, "BETA:Forbidden")
                        .contextWrite(
                          ReactiveSecurityContextHolder.withAuthentication(
                                  bob));

        StepVerifier.create(action)
                .expectError(AccessDeniedException.class)
                .verify();
        assertEquals(0, store.writes());
    }

    @Test
    void missingReactiveAuthenticationDeniesWrite() {
        StepVerifier.create(
                service.rename("alpha", 7L, "ALPHA:Forbidden"))
                .expectError(AccessDeniedException.class)
                .verify();
        assertEquals(0, store.writes());
    }

    @Test
    void invalidInputDoesNotMutate() {
        Authentication alice = actor("alice", "document:write");
        StepVerifier.create(
                service.rename("alpha", -1L, "Bad")
                        .contextWrite(
                           ReactiveSecurityContextHolder.withAuthentication(
                                   alice)))
                .expectError(AccessDeniedException.class)
                .verify();
        assertEquals(0, store.writes());
    }
}
~~~

Các test WebTestClient gửi request vào server reactive; StepVerifier gọi **Spring-injected service proxy** và gắn Authentication vào subscriber context. Nếu thay service bằng `new DocumentService(...)`, lời gọi không đi qua AOP và test có thể xanh giả khi method security chưa từng chạy. `@DirtiesContext` cô lập state in-memory của từng test; test suite lớn có thể dùng fixture reset để hiệu quả hơn.

### 7.1. Vì sao thử “không subscribe” đặc biệt có giá trị?

Một lỗi phổ biến là code cập nhật DB ở assembly:

~~~java
// PHẢN VÍ DỤ:
Doc changed = storeBlocking.renameNow(tenant, id, title);
return Mono.just(changed);
~~~

Test chỉ kiểm “sau subscribe thì value đúng” có thể bỏ lọt việc write đã chạy **trước subscription/authorization**. Test `noSubscriptionMeansNoProtectedWrite` kiểm trực tiếp bất biến: chỉ tạo `Mono` và gắn Reactor Context chưa làm thay đổi store. Sau `StepVerifier` subscribe với quyền hợp lệ mới có đúng một write.

### 7.2. Test cancellation và timeout: đừng kỳ vọng rollback kỳ diệu

Nếu producer chưa bắt đầu hiệu ứng phụ, cancel phải ngăn source được subscribe/tiếp tục; nhưng nếu DB transaction đã commit, cancel không thể đảo ngược tự động. Với test cancellation đáng tin, tạo một publisher trì hoãn bằng `Mono.delay`/`TestPublisher`/virtual time rồi cancel **trước khi đoạn effect subscribe**; đo counter và xác định đúng event ordering. Không dùng `thenCancel()` với source đồng bộ lập tức rồi khẳng định write không chạy: source có thể hoàn tất trước khi hủy.

~~~java
// Trích đoạn test độc lập: protected work nằm SAU một gate chưa phát.
var gate = new reactor.test.publisher.TestPublisher<Void>();
var writes = new java.util.concurrent.atomic.AtomicInteger();

Mono<Void> sequence = gate.mono()
        .then(Mono.fromRunnable(writes::incrementAndGet));

StepVerifier.create(sequence)
        .thenCancel()
        .verify();

// Vì gate chưa complete nên effect phía sau chưa chạy:
assertEquals(0, writes.get());
~~~

Đây chỉ là trích đoạn của JUnit test, không phải mã application. Với `TestPublisher<Void>`, hãy kiểm chính xác API/test compiler version và lựa chọn `Mono.never()` nếu chỉ cần gate không bao giờ complete. Test cancellation cần xác minh riêng tác vụ bên ngoài không còn chạy, resource được release và event đã commit xử lý idempotency ra sao.

### 7.3. Test loss of context bằng two subscriptions

Một same publisher nếu subscribe dưới Alice rồi Bob phải đánh giá quyền theo **mỗi subscriber**, không dùng static cached grant:

~~~java
// Trích đoạn: same Spring proxy, hai Authentication context khác nhau.
Mono<DocView> source = service.read("alpha", 7L);

StepVerifier.create(source.contextWrite(
        ReactiveSecurityContextHolder.withAuthentication(alice)))
        .expectNextCount(1).verifyComplete();

StepVerifier.create(source.contextWrite(
        ReactiveSecurityContextHolder.withAuthentication(bob)))
        .expectError(AccessDeniedException.class).verify();
~~~

Ở đây `alice`/`bob` là authenticated tokens được thiết lập trong test, tương ứng authority và tenant membership. Không dùng `source.cache()` hoặc `share()` trên Publisher đã có kết quả per-user rồi lưu global, vì một ALLOW ở subscriber trước có thể bị replay khi người khác subscribe nếu cache đặt sai tầng.

## 8. Tác vụ tách khỏi chuỗi xử lý: loại nào phải chờ và loại nào có thể chạy nền?

Phân biệt rõ business contract:

| Loại tác vụ | Có cần hoàn tất trước HTTP success? | Thiết kế |
| --- | --- | --- |
| Authorization để cho phép read/write | **Bắt buộc** | Compose vào chain trước protected data |
| DB update chính của request | **Bắt buộc** | Compose, transaction, kết quả/error rõ |
| Audit pháp lý bắt buộc đồng bộ | Thường bắt buộc hoặc ghi durable evidence trước success | Compose vào transaction/outbox |
| Domain event “phải được phát cuối cùng” | Cần chứng cứ durable trước success | Transactional outbox cùng DB commit |
| Email notification hậu xử lý, có thể retry | Có thể tách **sau khi event durable** | Outbox + worker |
| Cache warmup không bắt buộc | Có thể tách với owner/lifecycle rõ | Scheduled/background service, bounded concurrency |
| Analytics/telemetry không nhạy cảm | Có thể async qua được quản lý | Metrics/tracing SDK, không raw PII |
| Thanh toán/cấp token/quyền | Không được fire-and-forget đơn giản | Domain transaction/state machine + idempotency |

### 8.1. Phản ví dụ fire-and-forget bên trong HTTP

~~~java
// SAI:
public Mono<Response> submit(Request request) {
    reactiveAuthorization(request)
            .subscribe();  // bỏ qua kết quả quyết định

    save(request)
            .subscribe();  // write chạy độc lập và có thể bắt đầu sớm

    return Mono.just(new Response("accepted"));
}
~~~

Nguy cơ: `save` có thể chạy trước authorization, HTTP success dù save lỗi, exception không đến caller, cancellation không tác động, security context không được gắn rõ cho hai subscription mới.

### 8.2. Đúng: đồng bộ hóa tất cả điều kiện bắt buộc trong một chain

~~~java
public Mono<Response> submit(Request request) {
    return reactiveAuthorization(request)
            .then(save(request))
            .flatMap(saved ->
                    auditPersist(saved).thenReturn(saved))
            .map(saved -> new Response("completed"));
}
~~~

Mỗi lời gọi giả định trả `Mono` đúng kiểu, publisher cold; nếu `reactiveAuthorization` có thể emit empty như “không có quyết định” mà chỉ complete, `then(save)` vẫn chạy. Vì thế **authorization guard phải biến deny/unknown/empty thành `Mono.error(AccessDeniedException)`**, không dùng empty-completion làm DENY. Đừng dùng `then` trực tiếp sau một authorization decision `Mono<Boolean>` mà bỏ kiểm boolean:

~~~java
// SAI: Boolean false vẫn complete bình thường nên THEN vẫn chạy.
return canWrite(tenant).then(save(doc));
~~~

Cách đúng:

~~~java
return canWrite(tenant)
        .defaultIfEmpty(false)
        .flatMap(allowed -> allowed
                ? Mono.<Void>empty()
                : Mono.<Void>error(new AccessDeniedException("Denied")))
        .then(save(doc));
~~~

Điều này đặc biệt quan trọng khi policy service trả `Mono.empty()` do không có quyết định.

### 8.3. Transactional outbox: background work có thể tách nhưng không được quên

Khi cần ghi DB và phát event cho queue/broker, tốt hơn:

~~~text
HTTP request subscription
  -> authenticated actor + tenant/action verification
  -> DB transaction:
       UPDATE tenant-scoped business row
       INSERT outbox_event(tenant, actor, type, id, payload, version)
  -> COMMIT
  -> HTTP 202/200 theo contract
  ...
  -> outbox dispatcher (được giám sát) publish broker event
  -> consumer xác thực producer + tenant scope
  -> revalidate rights/resource state khi nghiệp vụ yêu cầu
  -> idempotent processing + retry/DLQ + audit
~~~

Ghi outbox trong cùng transaction với domain mutation bảo đảm **durable intent to publish** (không bảo đảm exactly-once end-to-end). Publisher/consumer có thể retry hoặc gửi trùng, nên cần idempotency keys và at-least-once semantics. Không đánh đồng “đã ghi outbox” với “đã giao email/thanh toán xong”. API response contract phải phân biệt `ACCEPTED`, `PENDING`, `COMPLETED`.

### 8.4. Ai sở hữu background subscription?

`subscribe()` không bị cấm tuyệt đối. Một component **sở hữu lifecycle** như Spring-managed queue consumer, scheduled worker, application startup runner hay một Reactor `Flux` được khởi động có kiểm soát có thể là subscriber. Component đó phải:
- Tự xác thực workload/service identity; không mượn mù quáng authentication của HTTP request đã hoàn tất.
- Xác minh tenant/action/resource theo policy cho công việc đang chạy; actor có thể bị thu hồi membership.
- Giữ `Disposable`/subscription để stop/cancel khi shutdown; xử lý error, retry, backpressure, health/metrics và resource cleanup.
- Có giới hạn concurrency, idempotency, DLQ, correlation ID và audit.
- Không tự báo `COMPLETED` nếu chỉ vừa lên lịch.
- Không ghim `SecurityContext` của người dùng vào static global/hàng đợi vô thời hạn.

**Ranh giới:** thư viện/service trả `Mono` cho caller có trách nhiệm **compose**, còn người sở hữu lifecycle thực sự mới nên subscribe. Điều này giữ quyền quyết định khi nào chạy, khi nào timeout/cancel và khi nào báo success ở một nơi rõ ràng.

## 9. @Async, CompletableFuture, executor và Reactor Context

Ví dụ sai:

~~~java
@PreAuthorize("hasAuthority('document:write')")
public Mono<String> startJob(String tenant, Long id) {
    CompletableFuture.runAsync(() -> {
        // Task tách khỏi Reactor Context/request lifecycle.
        legacyWriter.write(tenant, id);
    });
    return Mono.just("OK");
}
~~~

Một `CompletableFuture` có thể bắt đầu ngay ở assembly, trước khi request có kết quả policy cuối; task có thể chạy với thread pool khác, thiếu SecurityContext, có lỗi không được quan sát và tiếp tục sau HTTP cancellation. `@Async` cũng chuyển execution context, không tự sao chép Reactor Context/authentication một cách an toàn trong mọi topology.

### 9.1. Nếu chỉ cần offload blocking work nhưng vẫn thuộc request

~~~java
public Mono<LegacyResult> readLegacy(Long id) {
    return reactiveAuthorizationFor(id)
            .then(Mono.fromCallable(() ->
                    blockingLegacyClient.read(id))
                    .subscribeOn(Schedulers.boundedElastic()));
}
~~~

Đây là trích đoạn có `reactiveAuthorizationFor(id)` trả `Mono<Void>` **lỗi khi DENY**, không phải Mono<Boolean> bỏ kiểm. Tác vụ vẫn là phần của request chain: error/cancel/timeout có thể truyền theo Reactor signal. Tuy nhiên blocking call có thể không dừng tức thì khi cancel; cần timeout ở client/socket, thread pool limits và consistency contract.

### 9.2. Nếu bắt buộc dispatch sang queue

Không gửi full `Authentication`, raw JWT, cookie hoặc cached ALLOW như “đơn cấp phép vĩnh viễn”. Event envelope tối thiểu:

~~~json
{
  "eventId": "evt-041",
  "tenantId": "alpha",
  "actorId": "opaque-user-17",
  "action": "GENERATE_REPORT",
  "resourceId": "doc-7",
  "schemaVersion": 1,
  "correlationId": "request-391"
}
~~~

Đây là dữ liệu minh họa. Worker chỉ tin message sau producer authentication/integrity check, kiểm quyền theo job identity/actor policy và trạng thái mới, giới hạn retry/timeouts. Có thể dùng dedicated service principal và các “delegated actor” rules được quản trị rõ; không giả định một user đã authorize request t1 còn có quyền ở t2.

### 9.3. Reactor Context có đi qua publishOn/subscribeOn không?

Với các operator Reactor thông thường, Context gắn vào subscriber và lan trong cùng chain dù scheduler thay đổi. Nhưng **ThreadLocal không tự động trở thành Reactor Context** và Context cũng không được chuyển một cách kỳ diệu sang task `CompletableFuture.runAsync` bên ngoài chain. Công cụ context propagation/automatic mode có thể hỗ trợ bridge theo version và cấu hình, nhưng không tự phục hồi một subscription đã bị tách với identity/authorization scope sai.

## 10. Timeout, cancellation, retry và HTTP kết quả

### 10.1. timeout() không phải rollback

~~~java
return authorize()
        .then(writeToDatabase())
        .timeout(Duration.ofSeconds(2));
~~~

Nếu deadline vượt, outer publisher phát lỗi timeout và có thể cancel upstream. Nếu DB đã commit trước khi có cancellation, dữ liệu vẫn đã thay đổi. Phải bảo đảm idempotency, transaction, retry policy và reconciliation; không coi HTTP 504/timeout là chứng cứ “write chắc chắn không xảy ra”.

### 10.2. Retry không được cấp quyền bằng kết quả stale

Nếu `retryWhen` đặt quanh toàn chain, authorization có thể chạy lại; nếu chỉ retry business write sau một lần ALLOW, membership có thể đổi giữa attempts. Lựa chọn tùy risk model. Với WRITE/DELETE nhạy cảm, cần recheck hoặc transaction guarded consistency. Không retry vô hạn và không retry non-idempotent side effect mà thiếu idempotency key.

### 10.3. Cancellation có thể bị phá bởi manual subscribe

~~~text
outer request subscribes
 -> authorized and starts work
 -> client disconnects, outer subscription cancelled
 -> child started by service.subscribe(): still running
 -> child may write or emit secret with no active owner
~~~

Với business task bắt buộc, việc có cancellation semantics rõ không đồng nghĩa luôn hủy được sau commit; với background task cố ý phải tiếp tục, chuyển sang durable queue/outbox và **document rằng nó độc lập**. Không để trạng thái nửa vời chỉ vì một `subscribe()` không được quản lý.

### 10.4. doFinally và cleanup

`doFinally(signalType -> ...)` chạy khi onComplete/onError/cancel; thích hợp cho metrics/cleanup đồng bộ, nhưng không nên `subscribe()` một reactive audit bắt buộc ngay trong callback. Với tài nguyên reactive, dùng `usingWhen`/reactive transaction boundary để release asynchronously trong cùng composition. Nếu cleanup thất bại phải có error/compensation contract, không mất trong log.

## 11. Java 17 độc lập: eager, detached và deferred

Không cần Spring/Reactor để hiểu lỗi thứ tự. Chương trình sau dùng `Supplier` và `Runnable` của JDK 17 làm mô hình đơn giản. **Nó không mô phỏng Reactor Context, non-blocking I/O hay Spring method advisor.** Nó cho thấy khác biệt giữa:
- Eager side effect diễn ra trước kiểm quyền.
- Detached task bị kích hoạt ngoài đường authorization.
- Deferred supplier kiểm quyền rồi mới thực hiện effect khi caller chủ động chạy.

Lưu `AuthorizedLifecycleDemo.java`:

~~~java
import java.util.concurrent.atomic.AtomicInteger;
import java.util.function.Supplier;

public class AuthorizedLifecycleDemo {
    record Actor(String name, boolean allowed) {}

    private static final AtomicInteger WRITES = new AtomicInteger();

    static Supplier<String> authorizedWrite(Actor actor) {
        // Giống bước "assembly": chỉ tạo description.
        return () -> {
            if (actor == null || !actor.allowed()) {
                return "DENY";
            }
            WRITES.incrementAndGet();
            return "GRANT";
        };
    }

    static String eagerWriteThenCheck(Actor actor) {
        WRITES.incrementAndGet();  // Side effect đã xảy ra!
        return actor != null && actor.allowed()
                ? "GRANT" : "DENY_TOO_LATE";
    }

    static Runnable detachedTask() {
        return WRITES::incrementAndGet;
    }

    public static void main(String[] args) {
        Actor alice = new Actor("alice", true);
        Actor bob = new Actor("bob", false);

        Supplier<String> lazy = authorizedWrite(alice);
        System.out.println("before-run=" + WRITES.get());

        System.out.println("denied=" + authorizedWrite(bob).get());
        System.out.println("after-deny=" + WRITES.get());

        System.out.println("allowed=" + lazy.get());
        System.out.println("after-allow=" + WRITES.get());

        System.out.println("eager-denied=" + eagerWriteThenCheck(bob));
        System.out.println("after-eager=" + WRITES.get());

        Runnable task = detachedTask();
        task.run();  // Không hề kiểm actor/tenant!
        System.out.println("after-detached=" + WRITES.get());

        System.out.println("missing-auth=" + authorizedWrite(null).get());
        System.out.println("final-writes=" + WRITES.get());
    }
}
~~~

Biên dịch/chạy:

~~~bash
javac --release 17 AuthorizedLifecycleDemo.java
java AuthorizedLifecycleDemo
~~~

**stdout chính xác:**

~~~text
before-run=0
denied=DENY
after-deny=0
allowed=GRANT
after-allow=1
eager-denied=DENY_TOO_LATE
after-eager=2
after-detached=3
missing-auth=DENY
final-writes=3
~~~

Giải thích:
- `authorizedWrite(alice)` lúc tạo Supplier **không tăng** counter; chỉ `.get()` mới chạy.
- Bob bị từ chối trước effect nên counter không đổi.
- `eagerWriteThenCheck(bob)` trả DENY nhưng side effect đã chạy trước: kiểm quyền quá muộn không thể xóa một write.
- `detachedTask().run()` minh họa tác vụ chạy độc lập không tự có authorization. Trong Reactor, `subscribe()` nội bộ có thể tạo một ranh giới tách biệt tương tự.
- `authorizedWrite(null)` fail closed.

### 11.1. Khác biệt quan trọng với Reactor

JDK `Supplier#get()` không hỗ trợ cancellation, backpressure, Scheduler, Context hoặc async errors như `Mono`. Nó chỉ cho thấy **thứ tự**. Đừng dùng Supplier thay `Mono` trong production WebFlux. Trong reactive server, runtime là subscriber và Spring method security quyết định theo Reactor Context của subscription.

## 12. Các bẫy tinh vi khi operator trông có vẻ đúng

### 12.1. Mono.just(blockingCall()) không phải lazy

~~~java
return Mono.just(jdbcDao.load(id));  // load chạy ngay.
~~~

Đúng khi migrate tạm sang blocking:

~~~java
return Mono.fromCallable(() -> jdbcDao.load(id))
        .subscribeOn(Schedulers.boundedElastic());
~~~

Hoặc dùng reactive repository thật. Chú ý null từ Callable dẫn đến empty Mono; nếu null là “không có quyết định”, convert thành DENY tường minh.

### 12.2. Mono.defer nhưng callback tự subscribe()

~~~java
return Mono.defer(() -> {
    auditMono.subscribe(); // vẫn detached, chưa đúng.
    return saveMono;
});
~~~

`defer` chỉ trì hoãn việc **tạo subscription con**, không gắn child vào outer chain. Đúng:

~~~java
return Mono.defer(() -> saveMono.flatMap(
        saved -> auditMonoFor(saved).thenReturn(saved)));
~~~

### 12.3. Mono.when(authorization, write) có thể chạy write sớm

~~~java
// SAI: độc lập/có thể chạy song song.
return Mono.when(authorizationGuard, protectedWrite);
~~~

Nếu guard phải chạy trước write, dùng `authorizationGuard.then(protectedWrite)` **với guard trả lỗi nếu deny**. `Mono.when` dành cho các nguồn độc lập, không phải bảo đảm thứ tự authorization.

### 12.4. onErrorResume(... -> Mono.empty()) có thể biến lỗi thành success

~~~java
// SAI khi kiểm quyền:
return verifyPermission()
        .onErrorResume(e -> Mono.empty())
        .then(writeData());
~~~

Nếu verify gặp AccessDeniedException và biến thành empty-completion, `then` chạy write. Với required permission, propagating error hoặc chuyển thành explicit deny publisher là bắt buộc. Tương tự `onErrorComplete()`/`onErrorReturn(true)` là nguy hiểm trên authz gate.

### 12.5. concatMap vs flatMap cho side effects có thứ tự

Khi xử lý `Flux<Command>` có write theo thứ tự, `flatMap(this::process)` có thể interleave và chạy đồng thời (theo concurrency); `concatMap(this::process)` bảo toàn thứ tự. Cần thiết kế transaction/race/idempotency riêng. Dù dùng `concatMap`, từng command phải được xác minh actor/tenant/action; thứ tự không thay authorization.

### 12.6. cache()/share() và multi-subscriber authorization

~~~java
// SAI nếu authorization phụ thuộc actor/subscription:
Mono<Boolean> globallyCachedGrant = checkPermissionForCurrentUser()
        .cache();
~~~

`cache()` có thể lưu lại decision từ một lần subscription và tái phát cho subscriber khác. Nếu current actor lấy từ Reactor Context, lần sau có context khác vẫn có thể dùng quyết định cũ. Không cache `Mono<AuthorizationDecision>` global theo user không định danh; quyết định nhạy cảm nên re-evaluate hoặc cache key theo tenant, actor, action, resource, ACL/policy revisions và invalidation có kiểm chứng.

### 12.7. create()/sink() và callback không rõ lifecycle

Khi bridge callback API sang Reactor bằng `Mono.create`/`Flux.create`, đăng ký cancellation/disposal và đảm bảo callback không phát sau cancel, không call security check ở một raw thread thiếu context. Với DB hoặc message broker, phải kiểm thức concurrency, backpressure, event loss, shutdown và error. Tốt nhất dùng reactive integration có contract rõ khi có sẵn.

### 12.8. doOnNext không phải nơi đưa secrets vào logs

Log redacted IDs, correlation ID, outcome và tenant đã verify; không log JWT, raw document content hoặc toàn bộ `SecurityContext`. Một manual child subscription có thể mất MDC/trace context dẫn đến audit thiếu actor. Reactor Context và logging MDC bridge cần config, test và cleanup.

## 13. Ma trận test về bảo mật và lifecycle

| Test case | Kỳ vọng |
| --- | --- |
| Alice có READ alpha, ID 7 | 200, nội dung alpha |
| Bob có READ beta, ID 7 | 200, nội dung beta, không trộn |
| Bob chọn alpha | DENY trước store/response |
| Viewer có tenant nhưng thiếu feature | DENY |
| Anonymous, Reactor Context thiếu | DENY |
| Service rename được tạo nhưng không subscribe | Không write |
| Denied rename có subscription | Error, không write |
| Authorized rename được subscribe | Một write đúng tenant |
| Permission Mono.empty() | DENY, không tiếp tục bằng then |
| Authorization Mono.error() | Không write, có metrics lỗi |
| Một child subscribe bị bỏ qua | Lint/test phát hiện |
| audit publisher lỗi | Outer publisher không báo success nếu audit bắt buộc |
| HTTP cancellation trước effect | Effect chưa subscribe không chạy |
| HTTP cancellation sau commit | Có reconciliation/idempotency, không giả rollback |
| Retry sau timeout | Không duplicate non-idempotent side effect |
| Blocking driver chạy event-loop | Performance test/BlockHound có thể phát hiện |
| Legacy blocking wrapper | boundedElastic, timeout/concurrency controlled |
| Same publisher dưới Alice rồi Bob | Quyền theo từng subscriber, không cached grant |
| Self-invocation vào annotated method | Proxy bypass được phát hiện |
| @Async task ở thread mới | Không reuse tenant/security context cũ |
| Outbox worker nhận duplicate event | Idempotent, không chi tiền/gửi lặp trái contract |
| Tenant membership bị revoke khi job pending | Reauthorize theo policy ở worker |
| Unauthorized resource với shared ID | Repository/cache luôn tenant-scoped |
| No request subscriber | Không có protected eager side effect |
| Flux nhiều items và one unauthorized item | Không emit protected data trước authorization |
| Reactor context chảy qua publishOn | Không nhầm với ThreadLocal |
| Spring Security version upgrade | Method annotation/adapter behavior test |
| Dead-letter queue và logs | Không chứa raw JWT/secrets |
| Metrics/trace | Thấy detached error/cancel, correlation không mất |

### 13.1. Mutation tests

Thử cố ý làm hỏng các điểm quan trọng trong một test branch:
- Chuyển `DocStore.rename` từ `Mono.defer` sang update eager ⇒ test “no subscription” phải đỏ.
- Xóa `@PreAuthorize` và membership guard ⇒ viewer/Bob negative tests phải đỏ.
- Chuyển `guard.then(store.rename)` thành `Mono.when(guard, store.rename)` ⇒ test không side-effect khi DENY phải đỏ.
- Đổi `defaultIfEmpty(false)` thành `defaultIfEmpty(true)` ⇒ missing-membership test phải đỏ.
- Gọi `auditMono.subscribe()` thay `flatMap` ⇒ test audit failure propagated phải đỏ.
- Cache globally decision của Alice rồi dùng cho Bob ⇒ context test phải đỏ.

Nếu các mutation trên không làm test thất bại, suite chưa chứng minh security boundary thực sự.

## 14. Checklist code review cho WebFlux method security

- [ ] Protected service method là Spring-managed bean đi qua AOP proxy; không self-invocation vào method security.
- [ ] WebFlux/MVC stack được chọn rõ; reactive methods trả `Mono`/`Flux` được hỗ trợ.
- [ ] Không `block()` trong controller/service/custom reactive manager hoặc reactor event-loop.
- [ ] Blocking I/O bắt buộc được hoãn bằng `fromCallable` và offload có kiểm soát, không giả đó là non-blocking.
- [ ] Không gọi `subscribe()` trong `map`/`flatMap`/`doOnNext`/service để “ép task chạy”.
- [ ] Authorization check được compose trước protected I/O; denied/unknown/error không complete như success.
- [ ] `Mono.defer`/reactive repository giữ side effects lazy tới subscription.
- [ ] Principal lấy từ verified Reactor Context; tenant từ args chỉ là selector cần verify.
- [ ] Method security advisor và `@PreAuthorize` thực sự được test với Spring proxy.
- [ ] Mutation có transaction/version/tenant predicate và idempotency khi retry.
- [ ] Error/cancellation/timeout đi qua cùng chain; API response contract rõ.
- [ ] Business effect bắt buộc không fire-and-forget, không báo success trước durability.
- [ ] Background work cố ý có outbox/queue, owner/lifecycle, auth, retry, DLQ, dedup, observability.
- [ ] Không lưu/copy raw JWT hay full Authentication vào queue/task để dùng mãi.
- [ ] Không cache ALLOW/publisher chung giữa principals.
- [ ] Test “not subscribed ⇒ not written”, denied write, two tenants same ID, context per subscriber.
- [ ] Nếu dùng `doFinally`/`usingWhen`, cleanup và error propagation có contract.
- [ ] Bảo vệ logging/metrics khỏi PII/secrets và context loss.

## 15. Bài tập tự luyện

**Câu 1 — `block()` và `subscribe()` khác gì?**  
**Đáp án:** `block()` tạo subscription và đợi đồng bộ trên thread gọi; `subscribe()` kích hoạt subscription và thường trả ngay, đặc biệt các nguồn async. Cả hai có thể tạo subscription ngoài chuỗi do WebFlux quản lý nếu gọi trong service, phá boundary theo cách khác nhau.

**Câu 2 — `Mono.just(jdbcDao.save(...))` đã nonblocking chưa?**  
**Đáp án:** Chưa; `jdbcDao.save(...)` chạy ngay trong assembly. Dùng reactive driver hoặc `Mono.fromCallable(...).subscribeOn(boundedElastic)` nếu phải cô lập blocking I/O tạm thời.

**Câu 3 — `canWrite(tenant).then(save(...))` an toàn không?**  
**Đáp án:** Không nếu `canWrite` trả `Mono<Boolean>` với `false`/empty completion; `then` bỏ qua giá trị rồi chạy write. Hãy map false/empty thành `Mono.error(AccessDeniedException)` trước `then`.

**Câu 4 — Tại sao `audit(record).subscribe()` trong `doOnNext` nguy hiểm?**  
**Đáp án:** Child subscription tách biệt; HTTP có thể trả success trước audit, lỗi/cancel/trace/security context không được quản lý cùng request. Với audit bắt buộc, dùng `flatMap(saved -> audit(saved).thenReturn(saved))`.

**Câu 5 — Có bao giờ được subscribe thủ công?**  
**Đáp án:** Có ở boundary sở hữu lifecycle như scheduled worker/queue consumer được quản lý, biết authentication/tenant, giữ Disposable, retry/backpressure/shutdown. Không ở method library/service trả Publisher cho caller.

**Câu 6 — Vì sao cancellation không luôn hoàn tác DB mutation?**  
**Đáp án:** Cancellation là signal của subscription; external DB commit có thể đã hoàn tất. Transaction/idempotency/reconciliation giải quyết consistency, không dựa vào cancel như undo.

**Câu 7 — Alice và Bob cùng subscribe một cached decision Mono có an toàn?**  
**Đáp án:** Không nếu Mono cache kết quả permission gắn Alice rồi phát lại cho Bob. Không cache global ALLOW theo subscriber; dùng source-specific policy evaluation và cache key/freshness thực sự đúng nếu cần.

**Câu 8 — Worker chạy một giờ sau khi user bị thu hồi membership có nên dùng cached ALLOW?**  
**Đáp án:** Không theo mặc định. Worker xác minh lại task/tenant/actor hoặc dùng delegated service policy có expiry/authority boundary rõ. Outbox bảo đảm intent được ghi durable chứ không bảo đảm người dùng còn quyền ở thời điểm xử lý.

## 16. Kết luận

Trong reactive method security, **quyền phải là một mắt xích của cùng chuỗi xử lý với dữ liệu và side effects**, không phải check được “bắn ra” bằng `subscribe()` hoặc kiểm được chờ bằng `block()` trên event-loop.

~~~text
WebFlux subscriber + Reactor SecurityContext
  -> @PreAuthorize / ReactiveAuthorizationManager
  -> verified tenant + actor + action
  -> lazy/nonblocking protected operation
  -> mandatory persistence/audit/outbox
  -> onNext/onComplete OR onError/cancel under explicit contract
  -> HTTP response / durable job handoff
~~~

Dùng `flatMap`/`then` để giữ nghĩa vụ bắt buộc trong chain, `Mono.defer` để tránh eager effect, `fromCallable` + `boundedElastic` có giới hạn cho thư viện blocking, và **outbox + managed worker** khi thực sự cần background work sau request. Không dùng `subscribe()` như nút “chạy task” trong business service. Câu hỏi review cuối cùng: **“Nếu request bị từ chối, không có subscription, timeout hoặc client disconnect, liệu một thao tác ghi, cấp quyền, gửi event bắt buộc hoặc download dữ liệu nhạy cảm vẫn có thể chạy bên ngoài cơ chế kiểm soát của PEP không?”** Nếu có, cần đưa tác vụ vào chain hoặc thiết kế một background authorization boundary độc lập.

## Tài liệu chính thức

- [Spring Security – Reactive Method Security 6.5](https://docs.spring.io/spring-security/reference/6.5/reactive/authorization/method.html): Reactor Context, `@EnableReactiveMethodSecurity`, `@PreAuthorize` và reactive authorization advisors.
- [Spring Security – ReactiveSecurityContextHolder API](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/core/context/ReactiveSecurityContextHolder.html): đọc/gắn Authentication trong Reactor subscriber Context.
- [Spring Security – WebFlux Security](https://docs.spring.io/spring-security/reference/reactive/configuration/webflux.html): reactive `SecurityWebFilterChain`, request auth.
- [Spring Framework 6.2 – WebFlux Concurrency Model](https://docs.spring.io/spring-framework/reference/6.2/web/webflux/new-framework.html): event-loop, non-blocking và blocking API considerations.
- [Project Reactor – Introduction to Reactive Programming](https://projectreactor.io/docs/core/release/reference/reactiveProgramming.html): cold Publisher, subscription, signals và backpressure.
- [Project Reactor – FAQ: Wrap synchronous blocking call](https://projectreactor.io/docs/core/release/reference/faq.html): `fromCallable` + `subscribeOn(boundedElastic)`.
- [Project Reactor – Adding a Context](https://projectreactor.io/docs/core/release/reference/advancedFeatures/context.html): `contextWrite`, `deferContextual`, subscriber context propagation.
- [Project Reactor – Backpressure and subscribing](https://projectreactor.io/docs/core/release/reference/subscribe-backpressure.html): `subscribe()`, request demand, bounded backpressure.
- [Project Reactor – Testing](https://projectreactor.io/docs/core/release/reference/testing.html): `StepVerifier`, virtual time, TestPublisher và cancellation tests.
- [Spring Framework – Reactive Transactions](https://docs.spring.io/spring-framework/reference/data-access/transaction/programmatic.html#tx-prog-operator): transactional reactive operators and lifecycle.
