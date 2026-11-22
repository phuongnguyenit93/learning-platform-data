# Gọi dịch vụ quyền bất đồng bộ trong quyết định Reactive

## 1. Vấn đề và mục tiêu

Trong ứng dụng Spring WebFlux, một quyết định phân quyền không phải lúc nào cũng chỉ là `hasRole("USER")`. Ví dụ khi đọc `Document#42`, ứng dụng có thể phải hỏi một **dịch vụ quyền (PDP/permission service)** nằm ở mạng nội bộ, truy vấn ACL qua R2DBC, hoặc đánh giá chính sách theo tenant, chủ sở hữu và trạng thái hồ sơ. Kết quả chỉ đến **sau một I/O bất đồng bộ**.

Với **Reactive Method Security**, không nên `block()` để chờ kết quả. Spring Security phiên bản 6.5, ở chế độ `AuthorizationManager`, cho phép một bean được gọi trong `@PreAuthorize` trả `Mono<Boolean>`. Framework đưa publisher quyết định vào reactive authorization pipeline, từ chối khi kết quả là `false`, và chỉ cho phép thao tác nghiệp vụ khi quyết định phù hợp.

Mục tiêu sau bài học, thuộc nhóm **Method security Reactive** của Spring Security Authorization:

1. Biết khi nào dùng `@EnableReactiveMethodSecurity`, `@PreAuthorize` và custom bean trả `Mono<Boolean>`.
2. Lấy authentication từ `ReactiveSecurityContextHolder` (Reactor Context), không dựa vào ThreadLocal truyền thống.
3. Kết hợp lời gọi quyền bất đồng bộ bằng `flatMap`, không vô tình tạo `Mono<Mono<Boolean>>`.
4. Định nghĩa rõ `true`, `false`, `Mono.empty()`, lỗi remote, timeout và fail-closed.
5. Không chặn Netty event loop bằng `block()`, không tự `subscribe()` để chạy tách luồng quyết định.
6. Kiểm tra actor, authority, tenant, resource type/ID, owner và trạng thái khi gọi PDP.
7. Bảo vệ cả phía dữ liệu: preauthorization không thay transaction, tenant filter và recheck khi ghi.
8. Test bằng Java 17+, JUnit 5, Spring context thật và `StepVerifier`: allow/deny, grant/revoke, lỗi/timeout, hai tenant có cùng ID và người có cùng username.

**Giới hạn:** project chạy được ở mục 7 mô phỏng PDP bằng `Mono.delay` và dữ liệu trong `ConcurrentHashMap`; nó **không** tự kiểm thử HTTP networking, WebClient, R2DBC hay PostgreSQL. Các mảnh code dùng WebClient/R2DBC ở phần production được ghi rõ là fragment.

## 2. Reactive method authorization nằm ở đâu?

```text
Caller -> Spring-managed bean proxy
   |
   | service.read("TENANT_A", 42) : Mono<String>
   v
@EnableReactiveMethodSecurity / @PreAuthorize
   |
   | SpEL: @authz.canRead(#tenant, #id)
   v
AsyncPolicy.canRead(...)
   |
   +-- ReactiveSecurityContextHolder.getContext()
   |      -> Authentication -> stable subject + tenant + authorities
   |      -> sai principal/tenant/action => DENY
   |
   +-- RemotePermissionService.check(...) : Mono<Boolean>
          |
          +-- true  -> subscription của business publisher
          +-- false -> access denied; không xử lý dữ liệu
          +-- empty -> explicit DENY
          +-- error/timeout -> explicit DENY hoặc error contract an toàn
```

Trong WebFlux, Reactor Context chứa thông tin SecurityContext cho publisher được subscribe. Các bước I/O có thể chuyển sang thread khác, vì vậy gọi `SecurityContextHolder.getContext()` trong ThreadLocal có thể lấy sai context hoặc không có auth.

| Công nghệ | Điểm mở rộng | Đối tượng được bảo vệ |
| --- | --- | --- |
| Reactive **method** security | `@EnableReactiveMethodSecurity`, `@PreAuthorize` | Spring-managed service method trả `Mono`/`Flux` |
| WebFlux **HTTP** authorization | `ServerHttpSecurity.authorizeExchange` và `ReactiveAuthorizationManager<AuthorizationContext>` | `ServerWebExchange`, HTTP path/method |
| Servlet method security | `@EnableMethodSecurity`, `AuthorizationManager<MethodInvocation>` | Imperative method invocation |

**Không lẫn:** annotation có tên gần giống nhau nhưng reactive method security cần đúng interceptor, Reactor Context và Publisher. HTTP filter có thể chặn request nhưng không tự bảo vệ job/consumer gọi thẳng service.

## 3. Cách gọi một bean quyền trả `Mono<Boolean>`

Spring Security 6.5 hỗ trợ:

```java
@PreAuthorize("@authz.canRead(#tenant, #id)")
public Mono<String> read(
        @P("tenant") String tenant,
        @P("id") long id) {
    return repository.read(tenant, id);
}
```

- Bean Spring tên **`authz`** có public method `canRead(String,long)` trả `Mono<Boolean>`.
- `@P` là `org.springframework.security.access.method.P`: SpEL có thể lấy `#tenant` và `#id` dù compiler không bật `-parameters`.
- Service được tạo bằng `@Bean` hoặc `@Component` và được gọi **qua proxy**.
- Khi trả `false`, Spring Security phát ra một lỗi phân quyền (thường là `AccessDeniedException`/subclass).
- Nên đặt side effects bên trong publisher lười (`Mono.defer`, reactive repository) và có kiểm tra nghiệp vụ tại nơi ghi.
- `@EnableReactiveMethodSecurity` trong Spring Security 6.x mặc định chọn AuthorizationManager; tài liệu chế độ legacy chỉ cho Boolean đồng bộ không nên áp dụng máy móc sang cơ chế mới.

Bean policy minh họa:

```java
public Mono<Boolean> canRead(String tenant, long id) {
    return ReactiveSecurityContextHolder.getContext()
        .map(SecurityContext::getAuthentication)
        .flatMap(auth -> {
            // Validate auth, authority, tenant trước khi gọi remote.
            return remotePermissions.check(auth, tenant, id, "READ");
        })
        .defaultIfEmpty(false)
        .timeout(Duration.ofMillis(300))
        .onErrorReturn(false);
}
```

Đây là **fragment**: `remotePermissions` và các điều kiện xác thực cần được triển khai. Ví dụ Java đầy đủ ở mục 7 cung cấp validation và fail-closed.

### 3.1. Vì sao `flatMap` thay vì `map`?

```java
// SAI về kiểu: Mono<Mono<Boolean>>.
Mono<Mono<Boolean>> nested =
    actorPublisher.map(actor -> remote.check(actor));

// ĐÚNG: Mono<Boolean>, Spring Security đánh giá được.
Mono<Boolean> decision =
    actorPublisher.flatMap(actor -> remote.check(actor));
```

Các biến `actorPublisher` và `remote` chỉ minh họa toán tử. Một `Mono<Boolean>` không phải Boolean đã có; không được làm:

```java
// PHẢN VÍ DỤ: blocking trong reactive authorization path.
boolean allow = remote.check(actor).block();

// PHẢN VÍ DỤ: subscribe thủ công, sau đó trả ALLOW trước.
remote.check(actor).subscribe(result -> audit(result));
return Mono.just(true);
```

**Đúng:** trả toàn bộ publisher để framework chịu trách nhiệm subscription, error và Reactor Context.

### 3.2. `empty`, lỗi và timeout

| Tín hiệu từ PDP | Diễn giải an toàn trong ví dụ |
| --- | --- |
| `Mono.just(true)` | PDP cho phép, sau khi đã xác minh scope/action |
| `Mono.just(false)` | PDP từ chối |
| `Mono.empty()` | Không có rule hoặc resource; **explicit DENY** với `defaultIfEmpty(false)` |
| `Mono.error(...)` | PDP lỗi; **fail closed**, không tự cấp quyền |
| `Mono.never()` | PDP treo; dùng `timeout` và fail closed |
| Cancellation | Không tiếp tục tự chạy bằng `subscribe()`; upstream xử lý hủy theo reactive semantics |

Tài liệu Spring Security mô tả `Mono.empty()` từ custom authorization bean có thể được xem là **abstain**. Để không biến "không biết" thành ALLOW vô tình, project này chủ động chuyển empty của **remote service** thành `false` trước khi trả lên method authorization. Nếu viết custom `ReactiveAuthorizationManager` hoặc nhiều managers kết hợp, phải xác định semantics abstain rõ ràng.

`timeout(Duration.ofMillis(100)).onErrorReturn(false)` là **demo**. Production có thể chuyển sự cố PDP thành 503 và alert thay vì báo 403; điểm bất biến là **không fail-open**. Tránh cache ALLOW quá lâu khiến quyền bị thu hồi mà kết quả cũ vẫn được dùng.

## 4. Thiết kế decision: không chỉ `username` và `documentId`

Một chính sách đủ an toàn thường có:

```text
actor    = tenant + issuer + stable subject
action   = READ | WRITE | DELETE | APPROVE | EXPORT
resource = tenant + resource type + ID
context  = trạng thái + owner + mức nhạy cảm + policy revision
```

Ví dụ:

| Tenant | ID | Username | Issuer/subject owner | Status | Body |
| --- | ---: | --- | --- | --- | --- |
| TENANT_A | 42 | alex | `issuer-1/sub-a` | DRAFT | A draft 42 |
| TENANT_B | 42 | alex | `issuer-1/sub-b` | DRAFT | B draft 42 |
| TENANT_A | 43 | publisher | `issuer-1/editor` | PUBLISHED | A public 43 |

Cả hai tài khoản tên **alex**, ID tài liệu đều **42**, nhưng tenant và subject khác nhau. Nếu PDP chỉ nhận `username="alex", documentId=42`, quyền có thể bị áp dụng chéo tenant.

**Chính sách ví dụ:**

- `READ`: cần authority `DOC_READ`, đúng tenant, remote grant READ; DRAFT chỉ owner có issuer+subject khớp, PUBLISHED được đọc khi có grant.
- `WRITE`: cần `DOC_WRITE`, đúng tenant, remote grant WRITE, đúng owner, state DRAFT.
- Caller tự chọn tenant khác trong tham số method **không làm đổi membership**, phải bị từ chối trước khi remote được gọi.
- Không có grant, không có document hoặc mất PDP đều dẫn tới DENY.
- Cùng subject nhưng issuer khác hoặc cùng username nhưng subject khác không tự thừa hưởng quyền.

**Ranh giới trust:** identity nên đến từ JWT/OIDC đã được xác minh chữ ký, issuer, audience, lifetime và tenant membership. Dữ liệu test Java tự tạo principal **chỉ giả lập bước authentication đã hoàn thành**; không được biến chuỗi `X-User`, `X-Tenant`, `subject` do client tự khai thành trusted Authentication.

## 5. Gọi dịch vụ quyền qua WebClient và R2DBC

### 5.1. WebClient

Ví dụ request/response gửi PDP nội bộ:

```json
{
  "actor": {
    "tenant": "TENANT_A",
    "issuer": "https://idp.example.test",
    "subject": "sub-a"
  },
  "action": "READ",
  "resource": {
    "tenant": "TENANT_A",
    "type": "Document",
    "id": 42
  }
}
```

```json
{"allowed":true,"policyVersion":17}
```

Một implementation fragment (không độc lập, vì cần `webClient`, DTO, bean):

```java
public Mono<Boolean> check(DecisionRequest request) {
    return webClient.post()
        .uri("/internal/decisions")
        .bodyValue(request)
        .retrieve()
        .bodyToMono(DecisionResponse.class)
        .map(DecisionResponse::allowed)
        .defaultIfEmpty(false)
        .timeout(Duration.ofMillis(300));
}
```

Tầng gọi nên cung cấp `onErrorReturn(false)`/error contract, metrics và log không chứa token. Đừng cho user tự chọn URL PDP hoặc tự đưa kết quả `allowed` vào request. Dùng service-to-service authentication, TLS/mTLS, network ACL và schema validation. Với 4xx/5xx, WebClient có thể phát lỗi Publisher; **không diễn giải HTTP 200 nhưng không có body là ALLOW**.

### 5.2. R2DBC

Một fragment SQL reactive:

```java
return databaseClient.sql("""
    SELECT allowed
    FROM permission_rules
    WHERE tenant_id = :tenant
      AND actor_issuer = :issuer
      AND actor_subject = :subject
      AND action = :action
      AND resource_id = :id
""")
    .bind("tenant", actor.tenant())
    .bind("issuer", actor.issuer())
    .bind("subject", actor.subject())
    .bind("action", action)
    .bind("id", id)
    .map((row, meta) -> row.get("allowed", Boolean.class))
    .one()
    .defaultIfEmpty(false);
```

Đây chỉ là phần lookup grant, **chưa đủ object owner/status, tenant RLS và workflow**. R2DBC/reactive client là cách thích hợp với event-loop. `Mono.just(jdbcTemplate.queryForObject(...))` là **phản ví dụ blocking**, không tự biến JDBC thành I/O bất đồng bộ.

### 5.3. Sự cố và điều tiết tải

- **Timeout:** đặt giới hạn riêng cho PDP và tổng request; không chờ vô hạn.
- **Retry:** chỉ có chủ đích với idempotent decision lookup, có backoff/jitter, giới hạn số lần; không retry một DENY hợp lệ.
- **Circuit breaker:** khi PDP outage, không fallback true; phân biệt lỗi hệ thống với deny trong audit/metrics.
- **Concurrency:** khi kiểm tra quyền cho từng item trong `Flux`, tránh không giới hạn `flatMap`; batching hoặc filter ngay trong query dữ liệu thường hiệu quả hơn.
- **Cache:** key phải có tenant, actor issuer/sub, action, resource type/ID và policy revision; invalidate sau grant/revoke.
- **Observability:** theo dõi latency, timeout, error, deny, policy version; tránh ghi raw JWT, PII và chi tiết ACL vào response.

## 6. Reactive SecurityContext, AOP và side effects

### 6.1. Context theo subscriber

Trong test hoặc code không dùng WebFlux HTTP filter:

```java
Mono<String> result = securedService.read("TENANT_A", 42L)
    .contextWrite(
        ReactiveSecurityContextHolder.withAuthentication(auth));
```

`auth` ở đây là `Authentication` đã tạo trong test. `contextWrite` gắn context **cho subscription**; khi dùng `StepVerifier.create(result)`, Spring method security và policy bean nhìn thấy principal tương ứng.

Không lấy `SecurityContextHolder.getContext().getAuthentication()` như nguồn chính trong Reactor, vì reactive pipeline có thể đổi thread. Không tạo một shared `Mono` rồi `.cache()` quyết định authority giữa các actor nếu key/context không được phân biệt; có thể vô tình chia sẻ ALLOW.

### 6.2. Proxy và lazy business publisher

```java
@PreAuthorize("@authz.canWrite(#tenant,#id)")
public Mono<String> write(String tenant, long id, String body) {
    return Mono.defer(() -> {
        // Chỉ được subscribe sau khi preauthorization cho phép.
        return repository.write(tenant, id, body);
    });
}
```

Fragment trên giả định repository reactive. `@PreAuthorize` chỉ hoạt động trên method Spring-managed được gọi qua AOP proxy; `this.write(...)` nội bộ cùng target có thể bỏ interceptor.

Đặt side effect trước khi tạo Mono là sai:

```java
public Mono<String> unsafeWrite(...) {
    jdbcTemplate.update(...); // Đồng bộ trước subscription.
    return Mono.just("done");
}
```

Đoạn này chỉ là **phản ví dụ**, không phải Java class hoàn chỉnh. Với operation rủi ro cao, ngay cả preauthorization đúng cũng không thay thế **recheck owner/state/version trong transaction khi ghi**, bởi quyền hoặc trạng thái có thể thay đổi sau khi PDP trả allow (TOCTOU).

### 6.3. Reactive `Flux`

`@PreAuthorize` có thể bảo vệ lời gọi đến service trả `Flux<T>`, nhưng quyết định ban đầu **không bảo đảm mọi item** trong `Flux` đều được phép trả ra. Với list/export, cần query theo tenant và object-level permission, hạn chế số RPC PDP. `@PostFilter` không phải phương án thay thế pagination hoặc row-level query security trên dữ liệu lớn.

## 7. Dự án tự chứa Java 17+ và JUnit 5

Mẫu này dùng **`@EnableReactiveMethodSecurity` thực**, bean SpEL `@authz` trả `Mono<Boolean>`, asynchronous `RemotePermissions` và `StepVerifier`; không khởi chạy HTTP server, không cần database, không dùng Testcontainers. Kiểm thử sự khác nhau giữa hai tenant có cùng ID/username, mỗi phép đánh giá quyền async, grant/revoke, timeout, exception và source `Mono.empty()`.

### 7.1. Cấu trúc

```text
reactive-async-authz/
├── settings.gradle
├── build.gradle
└── src/test/java/demo/AsyncReactiveAuthorizationTest.java
```

`settings.gradle`:

```groovy
rootProject.name = 'reactive-async-authz'
```

`build.gradle`:

```groovy
plugins { id 'java' }

repositories { mavenCentral() }

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

dependencies {
    testImplementation platform(
        'org.springframework.boot:spring-boot-dependencies:3.5.0'
    )
    testImplementation 'org.springframework.boot:spring-boot-starter-security'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'io.projectreactor:reactor-core'
    testImplementation 'io.projectreactor:reactor-test'
    testRuntimeOnly 'org.junit.platform:junit-platform-launcher'
}

tasks.named('test', Test) {
    useJUnitPlatform()
}
```

**Tệp mã Java duy nhất:** `src/test/java/demo/AsyncReactiveAuthorizationTest.java`.

```java
package demo;

import java.security.Principal;
import java.time.Duration;
import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.concurrent.atomic.AtomicInteger;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.aop.support.AopUtils;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.access.method.P;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.config.annotation.method.configuration.EnableReactiveMethodSecurity;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.authority.AuthorityUtils;
import org.springframework.security.core.context.ReactiveSecurityContextHolder;
import org.springframework.security.core.context.SecurityContext;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;

import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;

import static org.assertj.core.api.Assertions.assertThat;

@SpringJUnitConfig(AsyncReactiveAuthorizationTest.Config.class)
public class AsyncReactiveAuthorizationTest {

    private static final String ISSUER = "https://idp.example.test";

    public record Actor(
        String tenant, String issuer, String subject, String username
    ) implements Principal {
        @Override public String getName() { return username; }
    }

    public record Resource(String tenant, long id) {}

    public record Doc(
        String tenant, long id, String ownerIssuer,
        String ownerSub, String status, String body
    ) {}

    public record Grant(
        Resource resource, String issuer, String subject,
        String action
    ) {}

    static final Actor ALICE =
        new Actor("TENANT_A", ISSUER, "sub-a", "alex");

    static final Actor BOB =
        new Actor("TENANT_B", ISSUER, "sub-b", "alex");

    static final Actor OTHER =
        new Actor("TENANT_A", ISSUER, "sub-other", "alex");

    static final Actor OTHER_ISSUER =
        new Actor("TENANT_A", "https://idp-other.test",
                  "sub-a", "alex");

    public static class Docs {
        private final Map<Resource, Doc> rows =
            new ConcurrentHashMap<>();

        void reset() {
            rows.clear();
            rows.put(new Resource("TENANT_A", 42L),
                new Doc("TENANT_A", 42L, ISSUER, "sub-a",
                    "DRAFT", "A private 42"));
            rows.put(new Resource("TENANT_B", 42L),
                new Doc("TENANT_B", 42L, ISSUER, "sub-b",
                    "DRAFT", "B private 42"));
            rows.put(new Resource("TENANT_A", 43L),
                new Doc("TENANT_A", 43L, ISSUER, "publisher",
                    "PUBLISHED", "A public 43"));
        }

        Doc find(String tenant, long id) {
            return rows.get(new Resource(tenant, id));
        }

        Mono<String> read(String tenant, long id) {
            return Mono.defer(() -> {
                Doc found = find(tenant, id);
                return found == null
                    ? Mono.error(new AccessDeniedException(
                        "Not visible"))
                    : Mono.just(found.body());
            });
        }

        Mono<String> write(
                String tenant, long id, Actor actor, String body) {
            return Mono.defer(() -> {
                AtomicBoolean changed = new AtomicBoolean();
                rows.computeIfPresent(
                    new Resource(tenant, id), (key, old) -> {
                        boolean owner =
                            actor.tenant().equals(old.tenant())
                            && actor.issuer().equals(old.ownerIssuer())
                            && actor.subject().equals(old.ownerSub());
                        if (!owner || !"DRAFT".equals(old.status())) {
                            return old;
                        }
                        changed.set(true);
                        return new Doc(
                            old.tenant(), old.id(), old.ownerIssuer(),
                            old.ownerSub(), old.status(), body);
                    });

                return changed.get()
                    ? Mono.just(body)
                    : Mono.error(new AccessDeniedException(
                        "Not owner or no longer draft"));
            });
        }

        void publish(String tenant, long id) {
            rows.computeIfPresent(
                new Resource(tenant, id),
                (key, old) -> new Doc(
                    old.tenant(), old.id(), old.ownerIssuer(),
                    old.ownerSub(), "PUBLISHED", old.body()));
        }
    }

    public static class RemotePermissions {
        private final Docs docs;
        private final Map<Grant, Boolean> grants =
            new ConcurrentHashMap<>();
        private final AtomicInteger calls = new AtomicInteger();
        private final AtomicBoolean available =
            new AtomicBoolean(true);
        private final AtomicBoolean hang =
            new AtomicBoolean(false);

        RemotePermissions(Docs docs) { this.docs = docs; }

        void reset() {
            grants.clear();
            calls.set(0);
            available.set(true);
            hang.set(false);
            grant("TENANT_A", 42L, ALICE, "READ");
            grant("TENANT_A", 42L, ALICE, "WRITE");
            grant("TENANT_B", 42L, BOB, "READ");
            grant("TENANT_B", 42L, BOB, "WRITE");
            grant("TENANT_A", 43L, ALICE, "READ");
        }

        private Grant key(
                String tenant, long id, Actor actor, String action) {
            return new Grant(
                new Resource(tenant, id),
                actor.issuer(), actor.subject(), action);
        }

        void grant(String tenant, long id, Actor actor, String action) {
            grants.put(key(tenant, id, actor, action), true);
        }

        void revoke(String tenant, long id, Actor actor, String action) {
            grants.remove(key(tenant, id, actor, action));
        }

        int calls() { return calls.get(); }
        void outage(boolean state) { available.set(!state); }
        void stall(boolean state) { hang.set(state); }

        Mono<Boolean> check(
                Actor actor, String tenant, long id, String action) {
            return Mono.defer(() -> {
                calls.incrementAndGet();

                if (hang.get()) {
                    return Mono.<Boolean>never();
                }

                // Delay chạy qua Reactor scheduler: PDP bất đồng bộ.
                return Mono.delay(Duration.ofMillis(5))
                    .flatMap(ignored -> {
                        if (!available.get()) {
                            return Mono.<Boolean>error(
                                new IllegalStateException(
                                    "Remote PDP unavailable"));
                        }
                        Doc doc = docs.find(tenant, id);
                        if (doc == null) {
                            // Không tìm thấy rule/resource:
                            // wrapper policy phải chuyển empty -> deny.
                            return Mono.<Boolean>empty();
                        }

                        boolean owner =
                            actor.tenant().equals(doc.tenant())
                            && actor.issuer().equals(doc.ownerIssuer())
                            && actor.subject().equals(doc.ownerSub());

                        boolean scopeAllowed =
                            "READ".equals(action)
                                ? "PUBLISHED".equals(doc.status()) || owner
                                : "WRITE".equals(action)
                                    && owner
                                    && "DRAFT".equals(doc.status());

                        boolean granted = Boolean.TRUE.equals(
                            grants.get(key(tenant, id, actor, action)));

                        return Mono.just(granted && scopeAllowed);
                    });
            });
        }
    }

    public static class AsyncPolicy {
        private final RemotePermissions remote;

        AsyncPolicy(RemotePermissions remote) { this.remote = remote; }

        public Mono<Boolean> canRead(String tenant, long id) {
            return can(tenant, id, "READ");
        }

        public Mono<Boolean> canWrite(String tenant, long id) {
            return can(tenant, id, "WRITE");
        }

        private Mono<Boolean> can(
                String tenant, long id, String action) {
            return ReactiveSecurityContextHolder.getContext()
                .map(SecurityContext::getAuthentication)
                .flatMap(auth -> {
                    if (auth == null || !auth.isAuthenticated()
                        || !(auth.getPrincipal() instanceof Actor actor)
                        || tenant == null || tenant.isBlank()
                        || !tenant.equals(actor.tenant())
                        || actor.issuer() == null
                        || actor.issuer().isBlank()
                        || actor.subject() == null
                        || actor.subject().isBlank()
                        || id <= 0) {
                        return Mono.just(false);
                    }

                    String needed = "DOC_" + action;
                    boolean hasAuthority =
                        auth.getAuthorities().stream()
                            .anyMatch(a ->
                                needed.equals(a.getAuthority()));

                    if (!hasAuthority) {
                        return Mono.just(false);
                    }

                    return remote.check(actor, tenant, id, action)
                        .timeout(Duration.ofMillis(100))
                        .defaultIfEmpty(false)
                        .onErrorReturn(false);
                })
                .defaultIfEmpty(false);
        }
    }

    public static class Probe {
        private final AtomicInteger reads = new AtomicInteger();
        private final AtomicInteger writes = new AtomicInteger();

        void read() { reads.incrementAndGet(); }
        void write() { writes.incrementAndGet(); }
        int reads() { return reads.get(); }
        int writes() { return writes.get(); }
        void reset() { reads.set(0); writes.set(0); }
    }

    public static class DocumentService {
        private final Docs docs;
        private final Probe probe;

        DocumentService(Docs docs, Probe probe) {
            this.docs = docs;
            this.probe = probe;
        }

        @PreAuthorize("@authz.canRead(#tenant, #id)")
        public Mono<String> read(
                @P("tenant") String tenant,
                @P("id") long id) {
            return Mono.defer(() -> {
                probe.read();
                return docs.read(tenant, id);
            });
        }

        @PreAuthorize("@authz.canWrite(#tenant, #id)")
        public Mono<String> write(
                @P("tenant") String tenant,
                @P("id") long id, String body) {
            return Mono.defer(() -> {
                probe.write();
                return ReactiveSecurityContextHolder.getContext()
                    .map(SecurityContext::getAuthentication)
                    .map(auth -> (Actor) auth.getPrincipal())
                    .flatMap(actor ->
                        docs.write(tenant, id, actor, body));
            });
        }
    }

    @Configuration(proxyBeanMethods = false)
    @EnableReactiveMethodSecurity
    public static class Config {
        @Bean Docs docs() {
            return new Docs();
        }

        @Bean RemotePermissions remotePermissions(Docs docs) {
            return new RemotePermissions(docs);
        }

        @Bean("authz")
        AsyncPolicy asyncPolicy(RemotePermissions remote) {
            return new AsyncPolicy(remote);
        }

        @Bean Probe probe() {
            return new Probe();
        }

        @Bean DocumentService documentService(
                Docs docs, Probe probe) {
            return new DocumentService(docs, probe);
        }
    }

    @Autowired Docs docs;
    @Autowired RemotePermissions remote;
    @Autowired DocumentService service;
    @Autowired Probe probe;

    private static <T> Mono<T> as(
            Actor actor, Mono<T> source, String... authorities) {
        Authentication auth =
            new UsernamePasswordAuthenticationToken(
                actor, "test-only",
                AuthorityUtils.createAuthorityList(authorities));

        return source.contextWrite(
            ReactiveSecurityContextHolder.withAuthentication(auth));
    }

    private static <T> Mono<T> asString(
            String name, Mono<T> source, String... authorities) {
        Authentication auth =
            new UsernamePasswordAuthenticationToken(
                name, "test-only",
                AuthorityUtils.createAuthorityList(authorities));

        return source.contextWrite(
            ReactiveSecurityContextHolder.withAuthentication(auth));
    }

    @BeforeEach
    void reset() {
        docs.reset();
        remote.reset();
        probe.reset();
    }

    @Test
    void springAopReallyProtectsTheService() {
        assertThat(AopUtils.isAopProxy(service)).isTrue();
    }

    @Test
    void aliceReadsA42AfterAsyncPermission() {
        StepVerifier.create(as(
            ALICE, service.read("TENANT_A", 42L), "DOC_READ"))
            .expectNext("A private 42")
            .verifyComplete();

        assertThat(remote.calls()).isEqualTo(1);
        assertThat(probe.reads()).isEqualTo(1);
    }

    @Test
    void bobReadsB42WithTheSameLocalId() {
        StepVerifier.create(as(
            BOB, service.read("TENANT_B", 42L), "DOC_READ"))
            .expectNext("B private 42")
            .verifyComplete();

        assertThat(docs.find("TENANT_A", 42L).body())
            .isEqualTo("A private 42");
    }

    @Test
    void twoActorsHaveSameUsernameButDifferentIdentity() {
        assertThat(ALICE.getName()).isEqualTo(BOB.getName());
        assertThat(ALICE.subject()).isNotEqualTo(BOB.subject());
    }

    @Test
    void aliceCannotUseTenantBAsMethodArgument() {
        StepVerifier.create(as(
            ALICE, service.read("TENANT_B", 42L), "DOC_READ"))
            .expectError(AccessDeniedException.class)
            .verify();

        assertThat(remote.calls()).isZero();
        assertThat(probe.reads()).isZero();
    }

    @Test
    void bobCannotUseTenantAAsMethodArgument() {
        StepVerifier.create(as(
            BOB, service.read("TENANT_A", 42L), "DOC_READ"))
            .expectError(AccessDeniedException.class)
            .verify();
        assertThat(remote.calls()).isZero();
    }

    @Test
    void wrongAuthorityDeniesBeforeRemoteCall() {
        StepVerifier.create(as(
            ALICE, service.read("TENANT_A", 42L), "DOC_WRITE"))
            .expectError(AccessDeniedException.class)
            .verify();

        assertThat(remote.calls()).isZero();
        assertThat(probe.reads()).isZero();
    }

    @Test
    void sameNameDifferentSubjectCannotUseDraftEvenIfGranted() {
        remote.grant("TENANT_A", 42L, OTHER, "READ");

        StepVerifier.create(as(
            OTHER, service.read("TENANT_A", 42L), "DOC_READ"))
            .expectError(AccessDeniedException.class)
            .verify();

        assertThat(probe.reads()).isZero();
    }

    @Test
    void sameSubjectDifferentIssuerCannotImpersonateOwner() {
        remote.grant("TENANT_A", 42L, OTHER_ISSUER, "READ");

        StepVerifier.create(as(
            OTHER_ISSUER,
            service.read("TENANT_A", 42L), "DOC_READ"))
            .expectError(AccessDeniedException.class)
            .verify();
    }

    @Test
    void withoutRemoteGrantPublishedDocumentIsStillDenied() {
        StepVerifier.create(as(
            OTHER, service.read("TENANT_A", 43L), "DOC_READ"))
            .expectError(AccessDeniedException.class)
            .verify();
        assertThat(remote.calls()).isEqualTo(1);
    }

    @Test
    void grantIsObservedOnNextAsyncDecision() {
        StepVerifier.create(as(
            OTHER, service.read("TENANT_A", 43L), "DOC_READ"))
            .expectError(AccessDeniedException.class)
            .verify();

        remote.grant("TENANT_A", 43L, OTHER, "READ");

        StepVerifier.create(as(
            OTHER, service.read("TENANT_A", 43L), "DOC_READ"))
            .expectNext("A public 43")
            .verifyComplete();

        assertThat(remote.calls()).isEqualTo(2);
    }

    @Test
    void revokeIsObservedWithoutCachingOldAllow() {
        StepVerifier.create(as(
            ALICE, service.read("TENANT_A", 42L), "DOC_READ"))
            .expectNext("A private 42")
            .verifyComplete();

        remote.revoke("TENANT_A", 42L, ALICE, "READ");

        StepVerifier.create(as(
            ALICE, service.read("TENANT_A", 42L), "DOC_READ"))
            .expectError(AccessDeniedException.class)
            .verify();

        assertThat(remote.calls()).isEqualTo(2);
        assertThat(probe.reads()).isEqualTo(1);
    }

    @Test
    void emptyRemoteResultForMissingDocumentFailsClosed() {
        StepVerifier.create(as(
            ALICE, service.read("TENANT_A", 999L), "DOC_READ"))
            .expectError(AccessDeniedException.class)
            .verify();
        assertThat(probe.reads()).isZero();
    }

    @Test
    void remoteOutageFailsClosed() {
        remote.outage(true);

        StepVerifier.create(as(
            ALICE, service.read("TENANT_A", 42L), "DOC_READ"))
            .expectError(AccessDeniedException.class)
            .verify();

        assertThat(remote.calls()).isEqualTo(1);
        assertThat(probe.reads()).isZero();
    }

    @Test
    void remoteTimeoutFailsClosed() {
        remote.stall(true);

        StepVerifier.create(as(
            ALICE, service.read("TENANT_A", 42L), "DOC_READ"))
            .expectError(AccessDeniedException.class)
            .verify();

        assertThat(remote.calls()).isEqualTo(1);
        assertThat(probe.reads()).isZero();
    }

    @Test
    void plainUsernamePrincipalCannotBorrowAuthorization() {
        StepVerifier.create(asString(
            "alex", service.read("TENANT_A", 42L), "DOC_READ"))
            .expectError(AccessDeniedException.class)
            .verify();

        assertThat(remote.calls()).isZero();
    }

    @Test
    void workStartsOnlyAfterSubscription() {
        Mono<String> pipeline = as(
            ALICE, service.read("TENANT_A", 42L), "DOC_READ");

        assertThat(remote.calls()).isZero();
        assertThat(probe.reads()).isZero();

        StepVerifier.create(pipeline)
            .expectNext("A private 42")
            .verifyComplete();

        assertThat(remote.calls()).isEqualTo(1);
    }

    @Test
    void secondSubscriptionReevaluatesRevokedPolicy() {
        Mono<String> secured = as(
            ALICE, service.read("TENANT_A", 42L), "DOC_READ");

        StepVerifier.create(secured)
            .expectNext("A private 42")
            .verifyComplete();

        remote.revoke("TENANT_A", 42L, ALICE, "READ");

        StepVerifier.create(secured)
            .expectError(AccessDeniedException.class)
            .verify();

        assertThat(remote.calls()).isEqualTo(2);
    }

    @Test
    void aliceWritesOnlyTenantADraft() {
        StepVerifier.create(as(
            ALICE,
            service.write("TENANT_A", 42L, "Modified A"),
            "DOC_WRITE"))
            .expectNext("Modified A")
            .verifyComplete();

        assertThat(docs.find("TENANT_A", 42L).body())
            .isEqualTo("Modified A");
        assertThat(docs.find("TENANT_B", 42L).body())
            .isEqualTo("B private 42");
        assertThat(probe.writes()).isEqualTo(1);
    }

    @Test
    void bobWritesOnlyTenantBDraft() {
        StepVerifier.create(as(
            BOB,
            service.write("TENANT_B", 42L, "Modified B"),
            "DOC_WRITE"))
            .expectNext("Modified B")
            .verifyComplete();

        assertThat(docs.find("TENANT_A", 42L).body())
            .isEqualTo("A private 42");
        assertThat(docs.find("TENANT_B", 42L).body())
            .isEqualTo("Modified B");
    }

    @Test
    void readPermissionDoesNotGrantWriteMethod() {
        StepVerifier.create(as(
            ALICE,
            service.write("TENANT_A", 42L, "Forbidden"),
            "DOC_READ"))
            .expectError(AccessDeniedException.class)
            .verify();

        assertThat(remote.calls()).isZero();
        assertThat(probe.writes()).isZero();
    }

    @Test
    void publishedDocumentCannotBeChangedEvenByFormerOwner() {
        docs.publish("TENANT_A", 42L);

        StepVerifier.create(as(
            ALICE,
            service.write("TENANT_A", 42L, "Forbidden"),
            "DOC_WRITE"))
            .expectError(AccessDeniedException.class)
            .verify();

        assertThat(docs.find("TENANT_A", 42L).body())
            .isEqualTo("A private 42");
        assertThat(probe.writes()).isZero();
    }
}
```

### 7.2. Chạy và hiểu kết quả

Trong thư mục project:

```bash
gradle test --tests demo.AsyncReactiveAuthorizationTest
```

Với Gradle Wrapper, dùng `./gradlew test --tests demo.AsyncReactiveAuthorizationTest` (Linux/macOS) hoặc `gradlew.bat test --tests demo.AsyncReactiveAuthorizationTest` (Windows).

**Kỳ vọng:** 22 test JUnit thành công và Gradle báo `BUILD SUCCESSFUL` trong môi trường tương thích. Đây là **kết quả dự kiến theo mã**, không phải stdout ghi nhận từ một lần chạy thực tế. Xem báo cáo `build/reports/tests/test/index.html`.

| Nhóm kiểm thử | Điều cần chứng minh |
| --- | --- |
| Spring AOP | `@PreAuthorize` áp trên Spring-managed service |
| Allow A/B cùng ID 42 | Đúng tenant; cùng username không đồng nghĩa cùng identity |
| Sai tenant/authority | Deny **trước** remote request/body |
| Same-name/different subject hoặc issuer | Không mượn owner grant |
| Published không grant | Vẫn bị deny |
| Grant/revoke | Lần quyết định kế tiếp thấy quyền mới khi không cache |
| Unknown resource | Remote trả empty, policy deny |
| PDP error hoặc timeout | Fail closed |
| Untrusted string principal | Không tạo identity chỉ từ username |
| Cold Publisher | Không gọi remote/body trước subscription |
| Subscription thứ hai | Đánh giá lại, không memoize quyết định cũ |
| WRITE | Chỉ thay đúng tenant, owner và DRAFT |
| Chỉ READ | Không thể WRITE |
| PUBLISHED | Không được sửa dù từng là owner |

### 7.3. Vì sao dự án là reactive thật?

`RemotePermissions.check` chạy bên trong `Mono.defer`, sau đó dùng `Mono.delay(Duration.ofMillis(5))`; tức là chính sách **không trả ngay boolean trên thread gọi method**. `AsyncPolicy` kết hợp kết quả bằng `flatMap` rồi `timeout` và `defaultIfEmpty(false)`.

`contextWrite(ReactiveSecurityContextHolder.withAuthentication(...))` gắn principal cho subscription; `@PreAuthorize` gọi bean `authz` từ ApplicationContext. `Probe` đặt bên trong `Mono.defer` của business service để test negative path không có tác động nghiệp vụ. `Docs.write` dùng composite key tenant+ID và kiểm tra owner/state khi mutate; không dựa vào `getName()` vì hai actor đều tên alex.

**Giới hạn:** không test latency/transport TLS của WebClient, không có database transaction, không test stale policy cache giữa nhiều node, không xử lý refresh token hay revoke JWT. Với thao tác WRITE thực, **authorization ở thời điểm commit** có thể cần kiểm tra version/grant lần nữa nếu yêu cầu bảo mật không cho phép stale decision in-flight.

## 8. Các tình huống nâng cao và lỗi thường gặp

### 8.1. `Flux` và số lượng RPC

Khi một method trả `Flux<Document>`, preauthorize có thể quyết định có được gọi **chức năng LIST** không; nó không tự thay thế object-level filtering. Đừng gửi 50.000 RPC PDP đồng thời cho 50.000 item. Dùng repository có predicate tenant/ACL, batch policy lookup hoặc `flatMap(..., boundedConcurrency)` với backpressure.

### 8.2. Caching và revocation

Permission cache phải phân biệt `(tenant, issuer, subject, action, type, resourceId, policyVersion)`. Một cached ALLOW còn sống sau revoke có thể tạo cửa sổ stale permission. TTL không đảm bảo thu hồi tức thì; cần invalidate sau commit, đánh dấu revision và phân phối event cho mọi node. Với WRITE/DELETE/APPROVE nhạy cảm, cân nhắc recheck tại nơi ghi.

### 8.3. Failure domain và đánh dấu lỗi

Không đồng nhất `false` với mọi lỗi PDP trong metric: nên có `decision=DENY`, `reason=not_granted` và `reason=pdp_unavailable` ở audit nội bộ (không tiết lộ policy cho client). Nếu PDP timeout, có thể trả 503 thay vì 403 theo contract, nhưng **không được cho phép thực hiện thao tác**.

### 8.4. Cancellation, retry và side effects

Khi client hủy subscription, `Mono` có thể phát cancellation về upstream. Remote HTTP có thể vẫn đã xử lý request; gọi quyết định phải idempotent. `retryWhen` cần giới hạn, không retry denial; không dùng `subscribe()` tách khỏi request để “chạy nền” một kiểm tra quyền rồi cho phép body.

### 8.5. AOP proxy và self-invocation

`@PreAuthorize` áp trên bean do Spring quản lý. Nếu gọi `new DocumentService(...)`, bạn có thể không nhận AOP proxy. Tương tự `this.write(...)` trong cùng target có thể bypass proxy advice; tách service boundary và test đường gọi thực.

### 8.6. HTTP security không thay method security

Một API có thể chặn `GET /documents/42` ở `SecurityWebFilterChain`, nhưng scheduled job/message consumer gọi service trực tiếp không đi qua HTTP filters. Method security bổ sung lớp bảo vệ dưới HTTP. Ở phía khác, method authorization không tự kiểm soát route CSRF/CORS/HTTP authentication entry point.

## 9. Bảng lỗi và hướng xử lý

| Triệu chứng | Nguyên nhân thường gặp | Cách sửa |
| --- | --- | --- |
| `Mono<Boolean>` không được đánh giá đúng | Dùng reactive legacy config/SpEL operator ép kiểu | Kiểm tra `@EnableReactiveMethodSecurity` dùng AuthorizationManager; bean trả đúng Mono |
| Exception vì blocked thread | `.block()` trong WebFlux/event-loop | Gọi client reactive và return publisher |
| Quyền chưa xong nhưng body đã chạy | `.subscribe()` thủ công rồi trả ALLOW | `flatMap` vào một publisher quyết định |
| Có `Mono<Mono<Boolean>>` | Dùng `map` cho async callback | Đổi sang `flatMap` |
| Test không thấy Authentication | Thiếu Reactor Context | Gắn `contextWrite(withAuthentication(...))` |
| Cùng username dùng chung quyền | Dùng `getName()` làm identity duy nhất | Dùng issuer/sub/tenant |
| A đọc tài liệu B cùng ID | Remote lookup chỉ theo ID | Tenant+type+ID và membership check |
| Không có rule nhưng được allow | `Mono.empty` mang semantics không rõ | `defaultIfEmpty(false)` trong policy |
| Mất PDP vẫn đọc được | Fallback true hoặc cached ALLOW lâu | Fail-closed, cache revision/invalidation |
| Tất cả request treo | Không timeout | Timeout + circuit breaker + metrics |
| WRITE chạy khi không có authority | Authority gate thiếu | Check trước remote, negative tests |
| `@PreAuthorize` bị bỏ qua | Bean không qua Spring proxy/self-invocation | Đăng ký bean và test AOP proxy |
| Test PASS dù body chạy khi deny | Chỉ assert exception | Probe + assert state không đổi |
| Source có JDBC blocking | `Mono.just(jdbc...)` vẫn blocking | R2DBC hoặc offload có kiểm soát |
| In-flight write sau revoke | TOCTOU | Transaction/conditional update và recheck grant/version |
| `Flux` quá nhiều PDP requests | `flatMap` không giới hạn | Batching, concurrency cap, query filtering |

## 10. Checklist thực hành

- [ ] Reactive method security đã bật; service trả Publisher và được gọi qua Spring AOP proxy.
- [ ] Bean `@authz` trả `Mono<Boolean>` với async calls dùng `flatMap`, không `block()`.
- [ ] Authentication lấy từ Reactor Context; identity/tenant được xác thực và xử lý khi thiếu context.
- [ ] Authority action được kiểm tra trước remote I/O; READ/WRITE/EXPORT không suy ra nhau.
- [ ] PDP request chứa tenant + stable subject + resource type/ID + action; không tin tenant/subject từ header.
- [ ] Không có rule, resource missing, timeout, error => deny hoặc error contract fail closed.
- [ ] Có giới hạn timeout, retry, concurrency, circuit breaker và metrics/audit riêng cho lỗi PDP.
- [ ] Cache quyết định có TTL, key đầy đủ, invalidate khi quyền thay đổi.
- [ ] Nghiệp vụ dùng tenant-scoped repository; ghi cập nhật owner/state/version theo transaction.
- [ ] Test grant/revoke, same ID/different tenant, same name/different subject/issuer, lỗi/empty/hang PDP.
- [ ] Không dùng `.subscribe()` thủ công để làm decision, không giả định một lần ALLOW là quyền vĩnh viễn.
- [ ] Với Flux/list/export, kiểm soát cả từng bản ghi và số lượng RPC.
- [ ] Test Java chạy thật trước deploy và kiểm tra behavior Spring Security version cụ thể.

## 11. Bài tập

1. Thay `RemotePermissions` bằng `WebClient` đến một mock PDP, kiểm tra 200 allow/deny, 404 empty, 503 error, delay quá timeout.
2. Thêm `APPROVE` và phân tách nhiệm vụ: maker không được tự duyệt dù có `DOC_APPROVE`.
3. Thay `Docs` bằng PostgreSQL R2DBC với composite key tenant+id, thêm optimistic version cho WRITE.
4. Thêm cache theo actor/tenant/action/resource/version; viết test revoke sau ALLOW đã cache.
5. Dùng StepVerifier với hai principal khác nhau cho **cùng một publisher** và xác minh quyết định không dùng chung context.
6. Dùng source PDP trả `Mono.never()` rồi cấu hình timeout theo SLO, phân biệt 403 và 503 trong API.
7. Viết `Flux<Document>` cho LIST có tenant filter và giới hạn concurrency của quyền từng phần tử.
8. Chứng minh `this.write(...)` self-invocation có thể bypass Spring AOP, sau đó sửa thiết kế bằng service boundary.

## 12. Kết luận

Một quyết định **Reactive Method Security** có thể gọi dịch vụ quyền bất đồng bộ bằng cách để bean trong `@PreAuthorize` trả về `Mono<Boolean>`. Spring Security tích hợp publisher quyết định với quá trình subscribe, dùng Reactor Context để mang Authentication và từ chối trước thao tác nghiệp vụ khi policy không cho phép.

```java
@PreAuthorize("@authz.canRead(#tenant, #id)")
public Mono<String> read(
        @P("tenant") String tenant,
        @P("id") long id) {
    return documentRepository.read(tenant, id);
}
```

Không biến `Mono` thành `boolean` bằng `block()`, không tách subscription bằng `subscribe()`, và không coi empty/error/timeout là ALLOW. Cần ràng buộc đầy đủ **actor + tenant + action + resource + state**, kết hợp transaction/conditional update ở nơi thực hiện side effect. Mã test trong bài mô phỏng PDP async và trình bày các kết quả dự kiến; hãy chạy Gradle tests trên môi trường thực trước khi dùng trong production.

## Tài liệu tham khảo chính thức

- Spring Security 6.5 — Reactive Method Security và custom SpEL bean trả `Mono<Boolean>`: https://docs.spring.io/spring-security/reference/6.5/reactive/authorization/method.html
- Spring Security 6.5 — Reactive `PreAuthorizeReactiveAuthorizationManager`: https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/authorization/method/PreAuthorizeReactiveAuthorizationManager.html
- Project Reactor — Context: https://projectreactor.io/docs/core/release/reference/advancedFeatures/context.html
- Project Reactor — Operator choice: https://projectreactor.io/docs/core/release/reference/apdx-operatorChoice.html
- Spring Security 6.5 — Reactive HTTP Authorization (khác method): https://docs.spring.io/spring-security/reference/6.5/reactive/authorization/authorize-http-requests.html
- OWASP API1:2023 — Broken Object Level Authorization: https://owasp.org/API-Security/editions/2023/en/0xa1-broken-object-level-authorization/
