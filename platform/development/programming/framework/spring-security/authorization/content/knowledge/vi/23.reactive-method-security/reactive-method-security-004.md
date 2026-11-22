# ReactiveAuthorizationManager với MethodInvocation

> **Module:** Spring Security – authorization · **Nhóm:** Method security Reactive. Bài Knowledge này đi sâu vào `ReactiveAuthorizationManager<MethodInvocation>`: cách Spring Security bảo vệ một phương thức trả về `Mono`/`Flux` bằng quyết định bất đồng bộ, dùng `MethodInvocation` để đọc method/arguments, dùng `Mono<Authentication>` đến từ Reactor Context và gắn một custom authorization manager vào `AuthorizationManagerBeforeReactiveMethodInterceptor`. Phần API/đoạn mã Spring chủ yếu nhắm **Spring Security 6.5.x, Spring Boot 3.x, Spring WebFlux, Java 17+**. Spring Security 7.x có biến đổi về interface `authorize`; không trộn chữ ký hai phiên bản khi sao chép code. Một ví dụ JDK 17 độc lập ở cuối minh họa quyết định theo invocation mà không cần dependency.

## 1. Sau bài học bạn cần làm được gì?

1. Phân biệt authorization ở reactive method, reactive HTTP request và servlet method; không nhầm generic type `MethodInvocation` với `ServerWebExchange` hoặc `MethodInvocationResult`.
2. Giải thích Reactor Context và vai trò `ReactiveSecurityContextHolder`, thay vì đọc `SecurityContextHolder` thread-local trong pipeline WebFlux.
3. Hiểu chữ ký `ReactiveAuthorizationManager<MethodInvocation>` trong Spring Security 6.5: `check(Mono<Authentication>, MethodInvocation)` trả `Mono<AuthorizationDecision>`; `authorize` là API mới hơn trong quá trình chuyển đổi.
4. Dùng `MethodInvocation#getMethod()`, `getArguments()` và `getThis()` để xây yêu cầu quyền; validate type/length/tenant từ method arguments.
5. Triển khai một custom manager không block, quyết định explicit DENY khi thiếu Authentication, dữ liệu membership, argument hoặc service policy gặp lỗi.
6. Đăng ký custom advisor cho annotation riêng bằng `AnnotationMatchingPointcut.forMethodAnnotation`, tránh ghi đè nhầm hệ thống `@PreAuthorize` mặc định.
7. Tạo ứng dụng Spring Boot WebFlux với `@EnableReactiveMethodSecurity(useAuthorizationManager=true)` và service trả `Mono`, kiểm tra quyền theo user/tenant và resource-scoped repository.
8. Kiểm tra permission GRANT/DENY qua `WebTestClient` và StepVerifier, bao gồm case một resource ID trùng giữa hai tenant.
9. Phân tích lỗi `Mono.empty()` (abstain), `block()` trong reactive chain, side effects eager, self-invocation, caching authorization sai scope, context loss và time-of-check/time-of-use.
10. Phân biệt custom method interceptor và biểu thức `@PreAuthorize` dùng bean trả `Mono<Boolean>`; lựa chọn phù hợp với quy mô policy.
11. Phân loại trước/sau invocation: kiểm quyền trước khi thực thi với `MethodInvocation`, kiểm kết quả trả về với `MethodInvocationResult`/post-authorization hoặc domain object policy.

## 2. Bối cảnh: Reactive method authorization khác Servlet thế nào?

Trong Spring MVC/Servlet truyền thống, method security thường dùng:

~~~java
AuthorizationManager<MethodInvocation> manager;  // Imperative
// authorize(Supplier<Authentication>, MethodInvocation) ...
~~~

Trong WebFlux/Reactor, authentication của từng subscription thường được lưu trong **Reactor Context**, nên reactive method security làm việc với:

~~~java
ReactiveAuthorizationManager<MethodInvocation> manager; // Reactive
// Spring Security 6.5.x:
// check(Mono<Authentication>, MethodInvocation)
// -> Mono<AuthorizationDecision>
~~~

Đây là **minh họa API**, không phải chương trình Java độc lập. Các kiểu liên quan:

| API | Đối tượng nhận quyết định | Thường dùng ở đâu? |
| --- | --- | --- |
| `AuthorizationManager<MethodInvocation>` | Invocation và `Supplier<Authentication>` | Method security imperative/Servlet |
| `ReactiveAuthorizationManager<MethodInvocation>` | Invocation và reactive `Authentication` | **Reactive before-method security** |
| `ReactiveAuthorizationManager<AuthorizationContext>` | Request authorization context | `ServerHttpSecurity.authorizeExchange(...).access(...)` |
| `ReactiveAuthorizationManager<MethodInvocationResult>` | Invocation và object kết quả | Reactive **after-method** authorization |
| `ReactiveSecurityContextHolder` | Reactor `Context` của subscriber | Cung cấp security context cho reactive pipeline |
| `AuthorizationDecision` | `isGranted()` true/false | Kết quả tường minh của policy |

**Không** tạo `ReactiveAuthorizationManager<ServerWebExchange>` rồi truyền nó vào `AuthorizationManagerBeforeReactiveMethodInterceptor`: generic type không tương thích và đối tượng ngữ nghĩa khác. `MethodInvocation` đại diện cuộc gọi Java đã được AOP intercept, không chứa HTTP request mặc định.

### 2.1. Reactor Context là ngữ cảnh gắn với subscription

~~~text
WebFilter xác thực yêu cầu
    |
    v
Reactor Context chứa SecurityContext/Authentication
    |
    v
Spring AOP reactive method interceptor
    |
    +-- manager nhận Mono<Authentication> cho subscription
    |       |
    |       +-- policy/tenant checks bất đồng bộ
    |       |
    |       +-- GRANT -> cho Publisher của method tiếp tục
    |       +-- DENY  -> publisher lỗi AccessDeniedException
    |
    v
Mono/Flux business result
~~~

Vì authentication đi theo reactive subscription, đọc thẳng `SecurityContextHolder.getContext()` trong một callback bất kỳ có thể trả về context rỗng hoặc sai thread; không xem đó là cách lấy identity chuẩn cho WebFlux. Custom manager đã được **framework truyền `Mono<Authentication>`**, hãy dùng chính publisher đó.

### 2.2. Cold Publisher và lazy side effects

Một service `Mono<Doc>` nên trì hoãn I/O cho tới subscription, ví dụ `Mono.defer(...)` hoặc reactive repository API; không chạy thao tác ghi/đọc có side effect ngay lúc method chỉ **xây Publisher**. Method security bảo vệ **đường subscribe/emit**, không nên phụ thuộc một body eager đã gọi remote side effects trước khi policy đánh giá.

Không gọi `.block()`, `.blockOptional()`, `.toFuture().get()`, `Thread.sleep` hoặc JDBC/JPA blocking trực tiếp trên event-loop. Với legacy blocking I/O không thể thay ngay, phải cô lập trên scheduler phù hợp (`Schedulers.boundedElastic()`) và cân nhắc bảo mật/latency; nhưng bản thân việc offload không tự giải quyết transaction/context.

## 3. Chính xác chữ ký API Spring Security 6.5 và lưu ý nâng cấp

Trong Spring Security **6.5.x**, interface `ReactiveAuthorizationManager<T>` có method `check(Mono<Authentication>, T)` trả `Mono<AuthorizationDecision>`. `check` được đánh dấu deprecated trong những bản 6.5 mới khi chuyển sang `authorize(Mono<Authentication>,T)` trả `Mono<AuthorizationResult>`; cách triển khai phụ thuộc đúng version. Vì `check` vẫn là phương thức cần triển khai của interface 6.5, ví dụ dưới đây chọn `check` và ghi rõ version thay vì trộn hai hình thức.

~~~java
// Spring Security 6.5.x: code contract trích đoạn.
public final class TenantReadAuthorizationManager
        implements ReactiveAuthorizationManager<MethodInvocation> {

    @Override
    @SuppressWarnings("deprecation")
    public Mono<AuthorizationDecision> check(
            Mono<Authentication> authentication,
            MethodInvocation invocation) {

        // Bắt buộc trả một publisher thực sự, tránh null.
        return Mono.just(new AuthorizationDecision(false));
    }
}
~~~

Với Spring Security 7.x, kiểm Javadoc `ReactiveAuthorizationManager#authorize` trong dependency được build và đổi chữ ký/return type tương ứng. Không lấy chữ ký `Supplier<Authentication>` của **imperative** `AuthorizationManager` rồi gắn cho reactive manager. Một số ví dụ tài liệu ở nhánh tham khảo có thể hiển thị chữ ký khác so với Javadoc minor version; **dependency API thực tế là nguồn quyết định cho compile**.

### 3.1. Mono.empty() là không đưa ra quyết định, không phải DENY tường minh

Trong reactive authorization, một manager có thể trả `Mono.empty()` nghĩa là **abstain/không kết luận**. Việc interceptor/composite xử lý abstain phụ thuộc cấu hình và version; đối với ranh giới bắt buộc như tenant membership hoặc resource owner, không dựa vào một publisher rỗng để “tự từ chối”. Trả:

~~~java
return Mono.just(new AuthorizationDecision(false));
~~~

khi thiếu authentication/tenant/action bắt buộc. Ở ví dụ đầy đủ, `defaultIfEmpty(DENY)` giúp biến authentication publisher không phát giá trị hoặc membership không trả kết quả thành DENY tường minh.

### 3.2. Mono.error() khác DENY

`Mono.error(new IllegalStateException(...))` báo policy service bị lỗi; không đồng nghĩa policy quyết định false. Có thể map lỗi đó thành deny/error-closed ở security boundary và đo metrics `policy_unavailable` riêng. Tại API, outage có thể trả 503 (không được truy cập dữ liệu), còn policy-denied có thể trả 403. Không mặc định catch mọi lỗi rồi cấp quyền chỉ vì muốn dịch vụ tiếp tục chạy.

### 3.3. MethodInvocation xem được gì?

~~~java
Method method = invocation.getMethod();
Object[] args = invocation.getArguments();
Object target = invocation.getThis();
String methodName = method.getName();
Class<?>[] types = method.getParameterTypes();
~~~

Đoạn này nằm trong method manager khi có `MethodInvocation invocation`. Dùng những thông tin đó để xác định **method nào** và **các tham số đã được caller truyền**, không dùng làm bằng chứng chúng đã được phép. Nếu method nhận `tenantId` từ URL, giá trị đó là **selector** phải được so với membership phía server. Nếu method nhận `userId`, không coi nó là principal: principal lấy từ authenticated `Mono<Authentication>`.

Một target có thể là proxy hoặc object có method bridge/generic. Nếu cần đọc annotation/parameter name qua reflection, lưu ý interface vs implementation, bridge methods và Spring `AnnotatedElementUtils`/`AopUtils` phù hợp. Tránh index magic khi service signature thường đổi; tốt nhất giới hạn annotation trên một contract đã quy định và viết test cho mọi shape.

## 4. Khi nào dùng custom manager thay vì @PreAuthorize?

Hai cách đều là reactive method security:

**Đơn giản:** dùng annotation `@PreAuthorize("hasAuthority('document:read')")` nếu kiểm tra chỉ cần authority.

**Policy theo dữ liệu bất đồng bộ:** dùng bean biểu thức:

~~~java
// Spring service trích đoạn:
// @PreAuthorize("@tenantPolicy.canRead(authentication, #tenant)")
// Mono<DocView> read(String tenant, Long id) { ... }
~~~

Spring Security reactive method expression có thể hỗ trợ bean trả `Mono<Boolean>` ở cấu hình dùng authorization manager. Đảm bảo expression gọi bean thông qua SpEL đúng phiên bản, và principal/tenant/action được xác minh. Cách này tiện cho vài rule nhỏ, nhưng khi cùng rule phủ nhiều method, cần kiểm thứ tự, audit, abstain và context đồng nhất, một `ReactiveAuthorizationManager<MethodInvocation>` riêng dễ test hơn.

**Custom AOP advisor:** chọn annotation `@TenantRead`; interceptor sẽ gắn manager vào **mọi method được đánh dấu**, không yêu cầu copy/paste biểu thức nhiều lần. Ta không thay `@PreAuthorize` mặc định. Các method khác vẫn có thể dùng `@PreAuthorize`; nếu cả hai advice cùng áp dụng, cần hiểu ordering để không có side effects sớm.

## 5. Thiết kế an toàn với MethodInvocation và tenant

Giả sử service có chữ ký:

~~~java
@TenantRead
public Mono<DocView> read(String tenant, Long documentId) {
    return store.findWithinTenant(tenant, documentId)
            .map(doc -> new DocView(doc.id(), doc.tenant(), doc.title()));
}
~~~

Điều kiện policy:
- Reactive authentication có user đã xác thực, không anonymous.
- User có authority `document:read` (feature gate).
- Tenant ID hợp lệ, documentId hợp lệ.
- User có membership READ ở **tenant được chọn** (không phải ở tenant khác).
- Query/loader chỉ đọc document có `tenant_id` tương ứng; documentId hợp lệ nhưng tenant khác phải không trả dữ liệu.
- Nếu có object ACL/owner, phải kiểm riêng theo trusted resource metadata; member tenant không tự được đọc mọi document trong tenant.

Một ý tưởng quan trọng: **manager chỉ nhận method arguments và authentication**, còn record thực sự có tenant nào thường chỉ biết sau query repository. Có hai lối thiết kế:
1. Manager kiểm actor+membership+action **trước invocation**; service/repository chỉ query tenant-scoped, sau đó áp object ACL nếu cần.
2. Manager thực hiện thêm một reactive PIP lookup đáng tin theo tenant+ID trước khi GRANT, rồi service thao tác dưới transaction/version policy phù hợp.

Bài demo chọn (1) để minh họa đúng `MethodInvocation`. Không lấy `tenantId` từ argument rồi gán là `verifiedTenantId` mà không đối chiếu membership.

## 6. Spring Boot WebFlux demo đầy đủ: custom @TenantRead advisor

Các file hướng dẫn:

~~~text
src/main/java/demo/reactive/TenantMethodSecurityApplication.java
src/test/java/demo/reactive/TenantMethodSecurityApplicationTest.java
~~~

Tạo Spring Boot **3.x** project, Java **17+**, chỉ dùng starter webflux và security (không thêm Spring MVC starter cho mẫu này). Dùng một Java file chứa main class public và các class package-private để đơn giản hóa bài học. Trong production hãy tách domain, policy, repository và web layer thành files/packages có visibility/testability thích hợp.

### 6.1. Ứng dụng và custom manager

Lưu toàn bộ code sau thành `src/main/java/demo/reactive/TenantMethodSecurityApplication.java`:

~~~java
package demo.reactive;

import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;
import java.util.Map;
import java.util.Optional;
import java.util.Set;

import org.aopalliance.intercept.MethodInvocation;
import org.springframework.aop.Advisor;
import org.springframework.aop.support.annotation.AnnotationMatchingPointcut;
import org.springframework.beans.factory.config.BeanDefinition;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Role;
import org.springframework.http.HttpStatus;
import org.springframework.security.authentication.AnonymousAuthenticationToken;
import org.springframework.security.authorization.AuthorizationDecision;
import org.springframework.security.authorization.ReactiveAuthorizationManager;
import org.springframework.security.authorization.method.AuthorizationManagerBeforeReactiveMethodInterceptor;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.method.configuration.EnableReactiveMethodSecurity;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.GrantedAuthority;
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
import org.springframework.security.config.web.server.ServerHttpSecurity;

import reactor.core.publisher.Mono;

@SpringBootApplication
@EnableWebFluxSecurity
@EnableReactiveMethodSecurity(useAuthorizationManager = true)
public class TenantMethodSecurityApplication {
    public static void main(String[] args) {
        SpringApplication.run(TenantMethodSecurityApplication.class, args);
    }

    @Bean
    SecurityWebFilterChain web(ServerHttpSecurity http) {
        return http
                .authorizeExchange(ex -> ex
                        .pathMatchers("/api/tenants/**").authenticated()
                        .anyExchange().denyAll())
                .httpBasic(Customizer.withDefaults())
                .build();
        // Chỉ có GET trong demo; không vô hiệu CSRF tùy tiện.
    }

    @Bean
    MapReactiveUserDetailsService users() {
        return new MapReactiveUserDetailsService(
                User.withUsername("alice")
                    .password("{noop}demo")
                    .authorities("document:read")
                    .build(),
                User.withUsername("bob")
                    .password("{noop}demo")
                    .authorities("document:read")
                    .build(),
                User.withUsername("viewer")
                    .password("{noop}demo")
                    .authorities("profile:read")
                    .build());
        // {noop} CHỈ dành cho demo, không dùng production.
    }

    // Dùng annotation riêng để không thay built-in @PreAuthorize.
    @Bean
    @Role(BeanDefinition.ROLE_INFRASTRUCTURE)
    Advisor tenantReadAdvisor(TenantReadAuthorizationManager manager) {
        var pointcut = AnnotationMatchingPointcut
                .forMethodAnnotation(TenantRead.class);
        return new AuthorizationManagerBeforeReactiveMethodInterceptor(
                pointcut, manager);
    }
}

@Target(ElementType.METHOD)
@Retention(RetentionPolicy.RUNTIME)
@interface TenantRead {
}

record DocKey(String tenant, long id) {
}

record Doc(long id, String tenant, String title) {
}

record DocView(long id, String tenant, String title) {
}

// PIP demo: membership thuộc server, không đọc role từ HTTP header.
@Component
class TenantMemberships {
    private final Map<String, Set<String>> readers = Map.of(
            "alice", Set.of("alpha"),
            "bob", Set.of("beta"),
            "viewer", Set.of("alpha"));

    Mono<Boolean> canRead(String user, String tenant) {
        return Mono.defer(() -> Mono.just(
                readers.getOrDefault(user, Set.of()).contains(tenant)));
    }
}

// Đây là Spring Security 6.5.x:
// ReactiveAuthorizationManager#check(Mono<Authentication>, MethodInvocation).
@Component
class TenantReadAuthorizationManager
        implements ReactiveAuthorizationManager<MethodInvocation> {

    private static final AuthorizationDecision DENY =
            new AuthorizationDecision(false);

    private final TenantMemberships memberships;

    TenantReadAuthorizationManager(TenantMemberships memberships) {
        this.memberships = memberships;
    }

    @Override
    @SuppressWarnings("deprecation")
    public Mono<AuthorizationDecision> check(
            Mono<Authentication> authentication,
            MethodInvocation invocation) {

        Object[] args = invocation.getArguments();
        if (args.length != 2
                || !(args[0] instanceof String tenant)
                || !(args[1] instanceof Long documentId)
                || documentId <= 0
                || !tenant.matches("[a-z][a-z0-9-]{0,31}")) {
            return Mono.just(DENY);
        }

        // Authentication được Spring Security chuyển qua Reactor Context.
        // Không đọc SecurityContextHolder thread-local.
        return authentication
                .filter(Authentication::isAuthenticated)
                .filter(a -> !(a instanceof AnonymousAuthenticationToken))
                .flatMap(a -> {
                    boolean featureAllowed =
                            a.getAuthorities().stream()
                                .map(GrantedAuthority::getAuthority)
                                .anyMatch("document:read"::equals);

                    if (!featureAllowed) {
                        return Mono.just(DENY);
                    }

                    // Nguồn membership riêng trong server, bất đồng bộ.
                    return memberships.canRead(a.getName(), tenant)
                            .map(AuthorizationDecision::new)
                            .defaultIfEmpty(DENY);
                })
                .defaultIfEmpty(DENY)      // Không có Authentication => DENY.
                .onErrorReturn(DENY);      // PIP lỗi => không cấp quyền.
    }
}

@Component
class DocumentStore {
    private final Map<DocKey, Doc> docs = Map.of(
            new DocKey("alpha", 7L),
                new Doc(7L, "alpha", "ALPHA:Budget"),
            new DocKey("beta", 7L),
                new Doc(7L, "beta", "BETA:Budget"),
            new DocKey("alpha", 8L),
                new Doc(8L, "alpha", "ALPHA:Notes"));

    Mono<Doc> findWithinTenant(String tenant, Long id) {
        // Cold publisher: không đọc store trước subscription.
        return Mono.defer(() ->
                Mono.justOrEmpty(docs.get(new DocKey(tenant, id))));
    }
}

@Service
class DocumentService {
    private final DocumentStore store;

    DocumentService(DocumentStore store) {
        this.store = store;
    }

    @TenantRead
    public Mono<DocView> read(String tenant, Long id) {
        return store.findWithinTenant(tenant, id)
                .switchIfEmpty(Mono.error(
                        new ResponseStatusException(HttpStatus.NOT_FOUND)))
                .map(d -> new DocView(d.id(), d.tenant(), d.title()));
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

**Điểm quan trọng của mã:**
- `@EnableWebFluxSecurity` bật HTTP security của WebFlux; `@EnableReactiveMethodSecurity(useAuthorizationManager=true)` bật reactive method security. Không thay bằng `@EnableMethodSecurity` chỉ dành cho imperative.
- `@TenantRead` là annotation marker tự tạo, chỉ tồn tại runtime; `AnnotationMatchingPointcut.forMethodAnnotation(...)` chọn các method có marker.
- `AuthorizationManagerBeforeReactiveMethodInterceptor` nhận chính `ReactiveAuthorizationManager<MethodInvocation>` của chúng ta và intercept service qua Spring AOP.
- Manager đọc `getArguments()`, kiểm kiểu và độ dài. Nó lấy `Authentication` từ **Mono do interceptor cung cấp**, không lấy `userId` do caller gửi.
- `Mono.defer` trong membership/store minh họa dữ liệu chỉ được đọc khi subscribe; trong production thay memory map bằng reactive database client.
- `defaultIfEmpty(DENY)` và `onErrorReturn(DENY)` là lựa chọn fail closed cho một điều kiện bắt buộc; muốn phân biệt outage trong HTTP status/metrics, nâng cấp policy error handling chứ không fallback allow.
- `DocKey(tenant,id)` giữ scope tại nguồn dữ liệu; cùng `id=7` vẫn có hai record khác tenant.
- `DocumentService.read` trả `Mono<DocView>`, không dùng blocking JPA.
- Không có object-specific ACL: user thuộc tenant và có `document:read` được đọc mọi tài liệu trong tenant. Nếu nghiệp vụ có owner/ACL/classification, bổ sung policy ở service/PIP; đừng lấy demo làm chứng cứ tenant membership thay object authorization.
- Annotation custom có thể bổ sung vào nhiều service methods, nhưng **mọi method phải theo đúng contract args** hoặc manager trả DENY. Khi cần signature đa dạng, thiết kế một typed request resolver/annotation attribute và kiểm thử thay vì đọc `args[0]` bằng giả định vô hạn.
- Trong AOP proxy mode, gọi `this.read(...)` từ cùng bean hoặc tạo service bằng `new` có thể bỏ qua advice; gọi qua Spring-managed proxy và test HTTP/service bean thực.

### 6.2. Dependencies cho Gradle

Đây là phần `dependencies` trong một project đã có Spring Boot Gradle plugin, Java 17+, dependency management:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
    implementation 'org.springframework.boot:spring-boot-starter-security'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
    testImplementation 'io.projectreactor:reactor-test'
}
~~~

Không thêm `spring-boot-starter-web` (Servlet MVC) vào bài demo nếu không chủ đích chọn stack MVC. Reactor Test dùng `StepVerifier`; `WebTestClient` được Spring WebFlux/Test cung cấp. Với Maven/Gradle, phải quản lý đúng version Spring Boot/Security (ở đây là 3.x/6.5.x tương thích). Kiểm `./gradlew dependencies` khi thấy mismatch trong classpath; source snippets là Java 17.

### 6.3. Cách tự chạy và thử HTTP

Khởi động từ thư mục project đã cấu hình Spring Boot:

~~~bash
./gradlew bootRun
~~~

Windows dùng `gradlew.bat bootRun`. GET demo với HTTP Basic (chỉ môi trường học tập):

~~~bash
curl --user alice:demo http://localhost:8080/api/tenants/alpha/documents/7
curl --user bob:demo http://localhost:8080/api/tenants/beta/documents/7
curl --user bob:demo http://localhost:8080/api/tenants/alpha/documents/7
curl --user viewer:demo http://localhost:8080/api/tenants/alpha/documents/7
~~~

Dự kiến:
- Alice đọc alpha/7 ⇒ 200, title `ALPHA:Budget`.
- Bob đọc beta/7 ⇒ 200, title `BETA:Budget`.
- Bob chọn alpha ⇒ 403 (đã authenticated nhưng thiếu membership).
- Viewer có membership alpha nhưng thiếu feature authority ⇒ 403.
- Anonymous thiếu authentication ⇒ HTTP Basic entry point thường trả 401.
- Alice chọn alpha với document ID 9 không có trong alpha ⇒ 404.
- Không có route ngoài `/api/tenants/**` được cấp quyền.

`curl --user` trong demo có thể gửi Basic qua HTTP local; **production phải dùng HTTPS**, không dùng HTTP Basic/plain password theo mẫu để triển khai thật.

## 7. Điều gì xảy ra khi Subscribe?

Hãy theo dõi Bob request `/api/tenants/beta/documents/7`:

~~~text
1. WebFlux Security authenticates Bob for request.
2. Controller invokes service proxy DocumentService.read("beta", 7L).
3. Reactive before-method interceptor recognizes @TenantRead.
4. Spring passes Mono<Authentication> bound to subscriber's context.
5. TenantReadAuthorizationManager validates:
   - exactly 2 args: String tenant, Long docId > 0
   - authenticated actor
   - document:read authority
   - Bob is a reader of beta
6. Manager emits AuthorizationDecision(true).
7. Service Publisher proceeds; store query uses DocKey("beta",7).
8. Response is BETA:Budget; alpha never used for lookup.
~~~

Manager không được tự subscribe bằng `subscribe()` để “chạy kiểm quyền trước”: điều đó tách authorization khỏi request publisher và tạo race/cancel behavior khó kiểm soát. Trả `Mono<AuthorizationDecision>` để framework compose trực tiếp. Reactive code nên tránh side effects ngoài reactive operator; lấy identity tại đúng subscriber, không dựa vào static ThreadLocal.

### 7.1. GRANT, DENY, ABSTAIN và ERROR

| Kịch bản | Manager trong demo trả gì? | Ý nghĩa |
| --- | --- | --- |
| Authenticated Alice, authority read, tenant alpha | `AuthorizationDecision(true)` | Có thể cho Publisher tiếp tục |
| Bob yêu cầu tenant alpha | `AuthorizationDecision(false)` | Deny |
| Anonymous hoặc `Mono.empty()` auth | `AuthorizationDecision(false)` | Deny |
| Tenant null/sai grammar, id null/âm, signature khác | `AuthorizationDecision(false)` | Deny |
| Membership repository trả `Mono.empty()` | `AuthorizationDecision(false)` | Deny, không abstain |
| Membership repository error | `AuthorizationDecision(false)` | Fail closed; cần metrics riêng |
| Custom manager trả `Mono.empty()` trực tiếp | **Abstain** | Không có quyết định; không dùng cho tenant gate bắt buộc |
| Custom manager trả `Mono.error(...)` | Error | Không phải ALLOW; cần map/propagate theo contract |

Nếu policy yêu cầu auditing mọi lỗi PIP, đừng dùng `onErrorReturn(DENY)` im lặng: đổi sang `onErrorResume(error -> { metrics...; return Mono.just(DENY); })` và không log secret/request content. Không gọi `onErrorReturn(new AuthorizationDecision(true))` trong bất cứ nhánh nào.

### 7.2. Vì sao @PreAuthorize và @TenantRead không giống hệt?

`@PreAuthorize` là annotation biểu thức được Spring Security built-in manager xử lý. `@TenantRead` là marker do ứng dụng định nghĩa, và `AuthorizationManagerBeforeReactiveMethodInterceptor` riêng chạy cho marker đó. Không coi hai annotation tương đương về tất cả semantics: ordering, failure handling, post-authorization và audit cần được xác định trong thực tế.

Nếu dùng **cả** `@PreAuthorize` và `@TenantRead` trên một method, nhiều advisors có thể chạy. Đối với điều kiện bắt buộc, cần kiểm test rằng tất cả được enforce trước khi protected side effect thực thi; tránh condition abstain hoặc order chưa hiểu. Một thiết kế đơn giản với một custom marker hoặc một policy service gọi từ SpEL giúp giảm chồng chéo.

## 8. Kiểm thử tích hợp WebFlux bằng WebTestClient

Dùng `@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)`, client gửi HTTP Basic và đi qua WebFlux security + Spring method AOP. Tạo `src/test/java/demo/reactive/TenantMethodSecurityApplicationTest.java`:

~~~java
package demo.reactive;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.reactive.server.WebTestClient;

@SpringBootTest(
        webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class TenantMethodSecurityApplicationTest {
    @Autowired WebTestClient client;

    @Test
    void aliceReadsAlpha() {
        client.get()
                .uri("/api/tenants/alpha/documents/7")
                .headers(h -> h.setBasicAuth("alice", "demo"))
                .exchange()
                .expectStatus().isOk()
                .expectBody()
                .jsonPath("$.tenant").isEqualTo("alpha")
                .jsonPath("$.title").isEqualTo("ALPHA:Budget");
    }

    @Test
    void bobReadsBetaWithSameIdButDifferentValue() {
        client.get()
                .uri("/api/tenants/beta/documents/7")
                .headers(h -> h.setBasicAuth("bob", "demo"))
                .exchange()
                .expectStatus().isOk()
                .expectBody()
                .jsonPath("$.tenant").isEqualTo("beta")
                .jsonPath("$.title").isEqualTo("BETA:Budget");
    }

    @Test
    void bobCannotSelectAlpha() {
        client.get()
                .uri("/api/tenants/alpha/documents/7")
                .headers(h -> h.setBasicAuth("bob", "demo"))
                .exchange()
                .expectStatus().isForbidden();
    }

    @Test
    void viewerCannotReadDespiteAlphaMembership() {
        client.get()
                .uri("/api/tenants/alpha/documents/7")
                .headers(h -> h.setBasicAuth("viewer", "demo"))
                .exchange()
                .expectStatus().isForbidden();
    }

    @Test
    void aliceCannotReadDocumentMissingInAlpha() {
        client.get()
                .uri("/api/tenants/alpha/documents/999")
                .headers(h -> h.setBasicAuth("alice", "demo"))
                .exchange()
                .expectStatus().isNotFound();
    }

    @Test
    void anonymousCannotAccessMethod() {
        client.get()
                .uri("/api/tenants/alpha/documents/7")
                .exchange()
                .expectStatus().isUnauthorized();
    }
}
~~~

`WebTestClient` ở RANDOM_PORT tương tác qua HTTP với running reactive test server (khác `MockMvc` cho Servlet). Với những bản Boot/test runner có auto-configuration khác, có thể dùng `@AutoConfigureWebTestClient` và binding phù hợp. Trạng thái 403/404 có thể tùy error handling tùy biến, nhưng **nội dung cross-tenant tuyệt đối không được xuất hiện**.

### 8.1. StepVerifier kiểm trực tiếp custom manager

Có thể unit test mà không start server. Dùng Mockito mock `MethodInvocation` và `StepVerifier`:

~~~java
// Trích đoạn test khi có Spring Security/Mockito/Reactor Test.
// Imports cần: MethodInvocation, TestingAuthenticationToken hoặc
// UsernamePasswordAuthenticationToken, SimpleGrantedAuthority,
// StepVerifier, Mockito.mock/when, assertTrue/assertFalse.

MethodInvocation invocation = mock(MethodInvocation.class);
when(invocation.getArguments())
        .thenReturn(new Object[] {"alpha", 7L});

Authentication alice =
        UsernamePasswordAuthenticationToken.authenticated(
                "alice", "unused",
                java.util.List.of(
                        new SimpleGrantedAuthority("document:read")));

TenantReadAuthorizationManager manager =
        new TenantReadAuthorizationManager(new TenantMemberships());

StepVerifier.create(manager.check(Mono.just(alice), invocation))
        .assertNext(decision -> assertTrue(decision.isGranted()))
        .verifyComplete();

StepVerifier.create(manager.check(Mono.empty(), invocation))
        .assertNext(decision -> assertFalse(decision.isGranted()))
        .verifyComplete();
~~~

Đây là trích đoạn trong method test, không phải file Java đầy đủ: cần static imports `org.mockito.Mockito.mock`/`when`, `org.junit.jupiter.api.Assertions.assertTrue/assertFalse`, types từ Spring Security và Reactor. Nên bổ sung cases `args=[]`, wrong type, negative ID, missing authority, wrong tenant, membership error và incomplete source. Với Mockito mock, `MethodInvocation#getArguments()` là nơi test cung cấp đúng object array; không tạo HTTP request.

### 8.2. Kiểm Reactor Context trực tiếp qua service proxy

Trong một test có Spring application context, có thể gọi `DocumentService` được `@Autowired` và gắn authentication vào Reactor Context:

~~~java
// Trích đoạn trong JUnit với service là Spring proxy:
Authentication alice =
        UsernamePasswordAuthenticationToken.authenticated(
            "alice", "unused",
            java.util.List.of(
                new SimpleGrantedAuthority("document:read")));

StepVerifier.create(
        documentService.read("alpha", 7L)
            .contextWrite(
                ReactiveSecurityContextHolder.withAuthentication(alice)))
    .expectNextMatches(view ->
            view.title().equals("ALPHA:Budget"))
    .verifyComplete();
~~~

Nếu test dùng `new DocumentService(store)` hoặc self-invocation, proxy advisor không được áp, nên kết quả test không chứng minh method security. Dùng `@Autowired DocumentService` để đảm bảo AOP. Một test quan trọng khác gắn Bob nhưng gọi `read("alpha",7L)`: `StepVerifier.expectError(AccessDeniedException.class)` (hoặc subtype tùy version) chứng minh reactive DENY.

### 8.3. Mutation tests để bảo vệ test suite

Cố ý bỏ:
- Annotation `@TenantRead` trên `DocumentService.read` ⇒ Bob có thể đọc alpha khi HTTP gate chỉ yêu cầu authenticated; test `bobCannotSelectAlpha` phải đỏ.
- `memberships.canRead(...)` ⇒ Bob alpha sẽ được GRANT; test phải đỏ.
- Predicate tenant của `DocumentStore` ⇒ ID trùng tenant có thể lộ; test cùng ID ở hai tenant phải đỏ.
- `defaultIfEmpty(DENY)` trong manager ⇒ unauthenticated/empty auth có thể đi theo abstain; unit test nên đỏ.
- Rule feature authority ⇒ viewer có membership alpha có thể được READ; test phải đỏ.

Đây là kiểm chất lượng negative tests, không phải thay đổi được phép trong hệ thống thật.

## 9. Java 17 độc lập: giả lập MethodInvocation và quyết định

Trong JDK thuần không có Reactor, Spring Security hay AOP `MethodInvocation`. Chương trình này mô phỏng **dữ liệu giống một invocation** bằng record và kiểm GRANT/DENY để luyện tư duy. Nó **không phải implementation ReactiveAuthorizationManager thật**, không thể thay code Spring ở phần 6.

Lưu `ReactiveMethodPolicyDemo.java`:

~~~java
import java.util.Map;
import java.util.Set;

public class ReactiveMethodPolicyDemo {
    record Actor(String name, Set<String> authorities,
                 Set<String> tenants) {}
    record Invocation(String methodName, String tenant, long docId) {}

    static final Map<String, Set<Long>> DOCUMENTS = Map.of(
            "alpha", Set.of(7L, 8L),
            "beta", Set.of(7L));

    static String check(Actor actor, Invocation call) {
        if (actor == null) {
            return "DENY_AUTH";
        }
        if (call == null || !"read".equals(call.methodName())
                || call.tenant() == null || call.docId() <= 0) {
            return "DENY_INVOCATION";
        }
        if (!actor.authorities().contains("document:read")) {
            return "DENY_FEATURE";
        }
        if (!actor.tenants().contains(call.tenant())) {
            return "DENY_TENANT";
        }
        if (!DOCUMENTS.getOrDefault(
                call.tenant(), Set.of()).contains(call.docId())) {
            return "NOT_FOUND";
        }
        return "GRANT";
    }

    public static void main(String[] args) {
        Actor alice = new Actor(
                "alice", Set.of("document:read"), Set.of("alpha"));
        Actor bob = new Actor(
                "bob", Set.of("document:read"), Set.of("beta"));
        Actor viewer = new Actor(
                "viewer", Set.of("profile:read"), Set.of("alpha"));

        System.out.println("alice-alpha7=" +
                check(alice, new Invocation("read", "alpha", 7L)));
        System.out.println("bob-beta7=" +
                check(bob, new Invocation("read", "beta", 7L)));
        System.out.println("bob-alpha7=" +
                check(bob, new Invocation("read", "alpha", 7L)));
        System.out.println("viewer-alpha7=" +
                check(viewer, new Invocation("read", "alpha", 7L)));
        System.out.println("alice-alpha999=" +
                check(alice, new Invocation("read", "alpha", 999L)));
        System.out.println("alice-write=" +
                check(alice, new Invocation("write", "alpha", 7L)));
        System.out.println("missing-auth=" +
                check(null, new Invocation("read", "alpha", 7L)));
        System.out.println("missing-tenant=" +
                check(alice, new Invocation("read", null, 7L)));
    }
}
~~~

Chạy bằng JDK 17:

~~~bash
javac --release 17 ReactiveMethodPolicyDemo.java
java ReactiveMethodPolicyDemo
~~~

**stdout chính xác:**

~~~text
alice-alpha7=GRANT
bob-beta7=GRANT
bob-alpha7=DENY_TENANT
viewer-alpha7=DENY_FEATURE
alice-alpha999=NOT_FOUND
alice-write=DENY_INVOCATION
missing-auth=DENY_AUTH
missing-tenant=DENY_INVOCATION
~~~

Chương trình minh họa rằng method name, arguments và actor là các thành phần riêng cần kiểm, song trong reactive thực tế `Authentication` do framework đưa bằng `Mono` và dữ liệu membership có thể được lấy bất đồng bộ.

## 10. Khi nào cần MethodInvocationResult và post-authorization?

Before method authorization dùng `MethodInvocation` để xem **method + arguments + authenticated actor** trước khi kết quả được trả. Với rule “chỉ owner thật sự được thấy record”, có khi cần đọc resource metadata trước khi quyết định hoặc áp post-authorization trên object trả ra.

Spring Security cung cấp `AuthorizationManagerAfterReactiveMethodInterceptor` và generic `ReactiveAuthorizationManager<MethodInvocationResult>` cho hậu kiểm dựa trên giá trị đã tính; `@PostAuthorize` là cơ chế tiện hơn cho nhiều use case. Tuy nhiên:
- Không thực hiện protected side effect rồi mới kiểm quyền ở `@PostAuthorize`. Dùng before authorization/transaction guards cho DELETE, thanh toán, external API call.
- Hậu kiểm output không sửa sai việc repository đã đọc quá rộng hoặc ghi log nhạy cảm trước deny.
- Với `Flux` trả hàng nghìn phần tử, lọc/kiểm từng object cần chiến lược rõ về paging, total count và backpressure; đừng để một phần tử tenant khác được emit trước khi bị chặn.
- Post-authorization có thể trả error khi không hợp lệ; test cũng phải chắc chắn không emit dữ liệu cross-tenant.
- Nếu manager trước cần resource owner, cân nhắc một trusted reactive PIP query theo tenant + resource id, không lấy owner do client khai.

## 11. Phạm vi transaction, tenant và async

### 11.1. Tenant trong argument chỉ là selector

Method `read("beta", 7L)` có tenant argument beta nhưng Alice có thể không là member beta. Manager phải kiểm membership của Alice trong beta, không chỉ validate string. Nếu role phụ thuộc tenant, không dùng global `ROLE_ADMIN` của alpha để mở beta. Dữ liệu của resource phải có tenant ID đúng trong DB; mọi read/update/delete chỉ theo trusted tenant scope.

### 11.2. Cùng ID khác tenant

Khi alpha:7 và beta:7 cùng tồn tại, cache key chỉ `doc:7` hoặc repository global `findById(7)` có thể trộn giá trị. Dùng `(tenant,id)` cho cache, read, write và invalidation; nếu có ACL/user-specific response, cần thêm actor/action/permission versions hoặc thực hiện authorization mỗi lần.

### 11.3. Vai trò của R2DBC

Trong WebFlux, một reactive repository/R2DBC query phải bao gồm tenant predicate ở SQL hoặc database RLS khi có. `Mono.defer` trên in-memory map trong demo chỉ để minh họa nonblocking subscription, không tự biến blocking JPA call thành nonblocking. Nếu truy cập blocking DB driver, sử dụng `boundedElastic` với contract nhất quán hoặc chuyển sang R2DBC; đo hiệu năng và đảm bảo transaction context.

### 11.4. Race giữa check và use

t1 manager xác minh Bob thuộc beta; t2 membership/ACL bị thu hồi; t3 service ghi dữ liệu. Với WRITE/Delete hoặc tài nguyên nhạy cảm, cần query dưới transaction, optimistic locking/version/conditional write, policy revision và invalidate quyền theo freshness SLA. Không giả rằng ALLOW lúc subscription đầu là quyền tồn tại vĩnh viễn cho stream kéo dài.

### 11.5. Reactive Security Context và scheduler

Reactor Context thường theo subscription khi `publishOn`/`subscribeOn` nếu dùng Reactor operators đúng, nhưng custom ThreadLocal/bridge sang non-Reactor API có thể mất hoặc giữ state. Không dùng `MODE_INHERITABLETHREADLOCAL` với thread pool như mẹo giải quyết. Khi tích hợp callback/async non-Reactor, truyền explicit verified identity/tenant hoặc dùng context propagation được kiểm chứng, và dọn state trong `finally`.

### 11.6. Authentication Mono phải là cold/được compose

Manager không tự `subscribe()` vào authMono. Nếu cần role từ PIP:

~~~java
return authentication.flatMap(auth ->
        memberships.canRead(auth.getName(), tenant)
                .map(AuthorizationDecision::new))
    .defaultIfEmpty(new AuthorizationDecision(false));
~~~

Đây là trích đoạn nằm trong phương thức `check` có biến `tenant` đã validate. Không làm:

~~~java
authentication.subscribe(auth -> callExternalPdp(auth));
return Mono.just(new AuthorizationDecision(true)); // sai nghiêm trọng
~~~

Cách sai fire-and-forget rồi cấp quyền trước khi PDP trả; còn làm mất cancel/error propagation.

## 12. Test matrix cho reactive MethodInvocation

| Tình huống | Kỳ vọng |
| --- | --- |
| Alice có authority read và membership alpha | GRANT alpha resource |
| Bob chỉ member beta, muốn alpha | DENY, không query resource alpha |
| Viewer member alpha nhưng thiếu feature authority | DENY |
| Anonymous/auth Mono empty | DENY |
| Method signature không đúng 2 args | DENY |
| Tenant null/sai grammar hoặc document ID không hợp lệ | DENY |
| Membership Mono.empty() | DENY chứ không ABSTAIN |
| Membership service lỗi | DENY/error closed, có metrics |
| Alpha và beta có document ID 7 | Không lẫn kết quả |
| Resource ID ở ngoài tenant | Không tiết lộ dữ liệu, thường 404 |
| Manager trả Mono.empty() trực tiếp | Test behavior abstain, không dùng làm deny |
| Manager bị bỏ annotation/pointcut | Negative integration test phải đỏ |
| Method trả Mono và Flux | Security áp trên subscription, không eager side effect |
| Service self-invocation | Test phát hiện proxy bypass |
| Context thay bằng Alice→Bob qua two subscriptions | Quyết định theo từng Authentication |
| Scheduler switch | Reactor Context không bị lẫn ThreadLocal |
| `.block()` trong pipeline | Detect nonblocking violation (BlockHound nếu dùng) |
| Membership revoke giữa hai subscriptions | Freshness policy được thực thi |
| Cached ALLOW thiếu tenant/principal/action | Test phát hiện leak |
| PostAuthorize on already completed external side effect | Phải chuyển guard sang trước |
| Streaming Flux có phần tử tenant khác | Không được emit dữ liệu trái quyền |
| Test StepVerifier gọi Spring proxy | Đúng vs tự `new` không có advisor |
| HTTP Basic anonymous | 401 theo entrypoint |
| Custom 403 handler/anti-enumeration | Đúng API contract, không lộ record |

### 12.1. Concurrency và double subscription

Một cold `Mono` có thể được subscribe nhiều lần. Nếu policy PIP đọc membership ở mỗi subscription, kết quả có thể thay đổi theo thời điểm và Authentication context. Nếu bạn gọi `.cache()` trên quyết định mà không ràng principal/tenant/action/version, một lần GRANT có thể được share cho request khác. Đặc biệt, không tạo global `static Mono<AuthorizationDecision> cachedGrant` khi decision phụ thuộc user.

Khi retry publisher, cần biết quyết định đã chạy lại hay business operation bị retry; đừng dùng retry thiếu giới hạn hoặc side-effect không idempotent. Monitor cancellations/error signals để không rò resources.

## 13. Các lỗi phổ biến

### Lỗi 1 — Dùng Servlet interface
`AuthorizationManager<MethodInvocation>` với `Supplier<Authentication>` không tự thay `ReactiveAuthorizationManager<MethodInvocation>` trong WebFlux. Chọn đúng stack và import.

### Lỗi 2 — Nhầm API method giữa 6.5 và 7.x
Ở 6.5 custom manager implements `check(Mono<Authentication>,MethodInvocation)`; Spring 7 chuyển sang contract `authorize`. Không sao chép một chữ ký `check(Supplier<Authentication>, MethodInvocation)` trông giống tài liệu bị lệch phiên bản: đó là imperative signature.

### Lỗi 3 — Dùng SecurityContextHolder thread-local
Reactor Context không đồng nghĩa ThreadLocal khi có scheduler và callback. Lấy Authentication Mono do framework truyền.

### Lỗi 4 — Gọi block()
Blocking call trong event-loop làm latency/memory/throughput xấu, có thể deadlock. Trả publisher reactive và compose `flatMap`.

### Lỗi 5 — Return Mono.empty() khi bắt buộc DENY
Abstain không phải deny tường minh. `defaultIfEmpty(DENY)` khi thiếu authentication/PIP result.

### Lỗi 6 — PermitAll khi PIP lỗi
`onErrorReturn(new AuthorizationDecision(true))` làm fail open. Dùng DENY/appropriate error và logging/metrics riêng.

### Lỗi 7 — Tin tenantId trong method args là quyền
Caller có thể sửa route/path. Membership của authenticated principal phải được tra ở server, resource query tenant-scoped.

### Lỗi 8 — Dùng userId do client truyền thay Authentication
Method `read(String userId,...)` không chứng minh caller là userId. Principal phải lấy từ verified Authentication.

### Lỗi 9 — Gắn advisor cho mọi method
Pointcut quá rộng khiến method không liên quan bị deny hoặc rule bị áp sai. Dùng marker annotation cụ thể và test mọi signature.

### Lỗi 10 — Gắn @PreAuthorize và custom annotation mà không xét ordering
Một advisor có thể chạy ngoài dự kiến hoặc bỏ qua protected side effects. Kiểm behavior qua proxy thực và chọn boundary đơn giản.

### Lỗi 11 — Self-invocation
`this.read(...)` có thể bypass AOP. Gọi qua Spring-managed bean, refactor service hoặc dùng mô hình phù hợp.

### Lỗi 12 — Truy vấn dữ liệu global sau GRANT
Manager grant membership beta không cho phép query alpha record ID 7. Repository luôn lọc tenant.

### Lỗi 13 — Cache grant theo ID
Cache key phải có tenant, actor, action, resource và revisions liên quan; quyền nhạy cảm thường không cache ALLOW.

### Lỗi 14 — PostAuthorize cho side-effect không thể đảo
Hậu kiểm xảy ra quá muộn nếu DB write/publish event đã thực thi. Pre-authorization và transaction guard bắt buộc.

### Lỗi 15 — Test chỉ unit manager không có proxy
Có thể manager đúng nhưng advisor chưa được đăng ký hoặc annotation thiếu. Cần WebTestClient và StepVerifier trên bean proxy.

### Lỗi 16 — JPA blocking trong reactive service
Chỉ bao trong `Mono.just(...)` không biến blocking I/O thành async. Dùng R2DBC/reactive driver hoặc offload có kiểm soát.

### Lỗi 17 — Chia sẻ một Mono cached grant qua users
Publisher có thể bị replay cho subscriber khác; nếu chứa decision theo principal thì leak quyền. Không memoize authorization toàn cục.

### Lỗi 18 — Tưởng method security áp trên non-Publisher bất kỳ
Spring reactive method security yêu cầu return type reactive được hỗ trợ để tích hợp với Reactor Context; hãy dùng `Mono`/`Flux` (hoặc Kotlin coroutine ở phiên bản hỗ trợ) và test đúng.

## 14. Bài tập tự luyện

**Câu 1:** Vì sao `ReactiveAuthorizationManager<MethodInvocation>` khác `ReactiveAuthorizationManager<AuthorizationContext>`?

**Đáp án:** Cái đầu bảo vệ method invocation (arguments/method target), cái sau dùng reactive HTTP request authorization. Generic type phải khớp interceptor/context nhận.

**Câu 2:** Manager nhận `Mono.empty()` cho Authentication và trả `Mono.empty()`. Có chắc bị deny không?

**Đáp án:** Không nên mặc định. Trả `AuthorizationDecision(false)` trong rule bắt buộc để fail closed, thử hành vi interceptor version cụ thể.

**Câu 3:** Service trả `Mono.just(repositoryBlocking.findById(...))` có thực sự không blocking không?

**Đáp án:** Không. `repositoryBlocking.findById` chạy ngay khi biểu thức Java được đánh giá để tạo Mono, trước khi subscribe, và còn block event-loop nếu bị gọi trong pipeline. Dùng reactive driver hoặc offload có kiểm soát.

**Câu 4:** Bob có `document:read` nhưng chỉ là member beta. Bob đổi `tenant=alpha` và `id=7`. Có được đọc Alpha:Budget không?

**Đáp án:** Không. Custom manager kiểm membership Bob/alpha, trả DENY trước khi service gửi dữ liệu; repository còn có tenant-scoped query.

**Câu 5:** Vì sao dùng `getArguments()` không đủ để xác định principal?

**Đáp án:** Method args là input của caller, có thể chứa userId tự khai. Verified principal phải lấy từ `Mono<Authentication>` của Spring Security.

**Câu 6:** Có nên gọi `authentication.subscribe(...)` rồi trả GRANT trước không?

**Đáp án:** Không. Fire-and-forget khiến authorization không nằm trong reactive chain, result/exception/cancel không được await và có race mở quyền.

**Câu 7:** Khi nào dùng custom annotation/manager thay @PreAuthorize?

**Đáp án:** Khi policy Java phức tạp, nhiều method cần cùng decision và muốn test/audit manager riêng. Với role đơn giản, `@PreAuthorize` ngắn, dễ bảo trì hơn.

**Câu 8:** Một request đã được ALLOW, nhưng ACL bị thu hồi trước DB WRITE. Cần làm gì?

**Đáp án:** Revalidate policy/state theo consistency model, dùng transaction/locking/conditional SQL version guard; không xem một ALLOW cũ là quyền vĩnh viễn.

## 15. Checklist triển khai

- [ ] Dùng Spring Boot/WebFlux và Spring Security phiên bản tương thích, phân biệt `check` và `authorize` theo Javadoc.
- [ ] Bật `@EnableWebFluxSecurity` và `@EnableReactiveMethodSecurity(useAuthorizationManager=true)`.
- [ ] Method public của Spring bean trả `Mono`/`Flux`; marker `@TenantRead` thực sự trúng pointcut.
- [ ] Advisor dùng `AuthorizationManagerBeforeReactiveMethodInterceptor` với generic `MethodInvocation`, không nhầm `AuthorizationContext`.
- [ ] Policy đọc `Mono<Authentication>`; không đọc thread-local/userId từ client làm identity.
- [ ] Validate invocation args, tenant grammar, ID và source membership.
- [ ] Authentication/Membership missing/error ⇒ explicit DENY, không abstain/fail open.
- [ ] Không block, không subscribe() thủ công; PIP/DB connector thực sự reactive.
- [ ] Repository/cache/DB query có tenant scope, ownership/ACL nếu nghiệp vụ yêu cầu.
- [ ] Test 200/401/403/404, cùng document ID khác tenant, user đổi tenant, expired role/revoke.
- [ ] Kiểm Spring proxy/self-invocation, context propagation, repeated subscriptions và advisor ordering.
- [ ] Bảo vệ audit logs, không in token/PII, phân biệt policy-denied với unavailable.
- [ ] Có transaction/freshness controls cho protected WRITE/DELETE.
- [ ] WebTestClient + StepVerifier chạy với context/version thật trước khi production.

## 16. Kết luận

`ReactiveAuthorizationManager<MethodInvocation>` là điểm nối giữa **method-level Java context** và **asynchronous, subscriber-scoped authentication**. `MethodInvocation` cho biết *đang gọi method nào với tham số nào*; `Mono<Authentication>` cho biết *actor đã được xác thực là ai trong subscription này*; một PIP/reactive repository cho biết *actor có quyền gì đối với tenant/resource đó*. Chỉ khi những bằng chứng bắt buộc cùng hợp lệ, manager mới phát `AuthorizationDecision(true)`. Missing/invalid state cần DENY tường minh.

Luồng an toàn:

~~~text
Spring reactive request/context
  -> @TenantRead pointcut
  -> AuthorizationManagerBeforeReactiveMethodInterceptor
  -> ReactiveAuthorizationManager<MethodInvocation>
       -> validated args + Mono<Authentication>
       -> reactive membership/action PIP
       -> GRANT or explicit DENY
  -> tenant-scoped Mono/Flux business publisher
  -> optional object ACL/response policy
  -> safe response and audit
~~~

**Tự đánh giá:** nếu Bob thuộc beta và cùng Document ID 7 cũng tồn tại ở alpha, có con đường nào qua method args, AOP proxy, cache, Reactor Context hoặc repository khiến Bob đọc được Alpha:Budget không? Nếu có, ranh giới reactive method security chưa được thiết lập đủ.

## Tài liệu tham khảo chính thức

- [Spring Security 6.5 – Reactive Method Security](https://docs.spring.io/spring-security/reference/6.5/reactive/authorization/method.html): `@EnableReactiveMethodSecurity`, annotation advice, custom `ReactiveAuthorizationManager<MethodInvocation>` và Reactor Context.
- [Spring Security 6.5 – ReactiveAuthorizationManager Javadoc](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/authorization/ReactiveAuthorizationManager.html): `check`/`authorize` và `Mono<Authentication>`; tra đúng minor version.
- [Spring Security 6.5 – AuthorizationManagerBeforeReactiveMethodInterceptor Javadoc](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/authorization/method/AuthorizationManagerBeforeReactiveMethodInterceptor.html): constructor Pointcut/manager và before-method advice.
- [Spring Security 6.5 – PreAuthorizeReactiveAuthorizationManager Javadoc](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/authorization/method/PreAuthorizeReactiveAuthorizationManager.html): reactive SpEL built-in.
- [Spring Security – Reactive SecurityContextHolder](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/core/context/ReactiveSecurityContextHolder.html): Reactor subscriber context.
- [Spring Security – Testing Reactive Method Security](https://docs.spring.io/spring-security/reference/reactive/test/method.html): reactive method test and security context.
- [Spring Framework – AnnotationMatchingPointcut Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/aop/support/annotation/AnnotationMatchingPointcut.html): method annotation pointcuts.
- [Reactor – Context](https://projectreactor.io/docs/core/release/reference/advancedFeatures/context.html): Context, subscriber-scoped data.
- [Reactor Test – StepVerifier](https://projectreactor.io/docs/test/release/reference/): kiểm thử Publisher/expectNext/expectError.
