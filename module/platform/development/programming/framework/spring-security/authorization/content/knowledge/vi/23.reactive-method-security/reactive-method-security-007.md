# Kết quả rỗng, tín hiệu lỗi và ngữ nghĩa từ chối trong Reactive Method Security

## 1. Cùng là “không có kết quả” nhưng không cùng ý nghĩa

Một ứng dụng Spring WebFlux có hai luồng bất đồng bộ khác nhau:

1. **Luồng ra quyết định quyền** cho `@PreAuthorize`, `@PostAuthorize` hoặc custom `ReactiveAuthorizationManager`.
2. **Luồng dữ liệu** từ repository/service trả tài liệu hay danh sách cho người dùng.

Ở luồng quyết định:

```java
Mono.just(true)  // Explicit ALLOW.
Mono.just(false) // Explicit DENY.
Mono.empty()     // Không phát quyết định: có thể là ABSTAIN.
Mono.error(ex)   // Lỗi đánh giá, KHÔNG phải một quyết định.
```

Ở luồng dữ liệu:

```java
Mono.just(doc) // Có một tài liệu.
Mono.empty()   // Không có tài liệu được emit.
Mono.error(ex) // Truy vấn hoặc pipeline gặp lỗi.
Flux.empty()   // Danh sách có 0 phần tử.
```

**Không được đánh đồng** `Mono.empty()` của policy với `Mono.empty()` của repository. Spring Security 6.5 ghi rõ một bean được gọi bởi biểu thức method authorization có thể trả `Mono.empty()` để biểu đạt *abstain*: **không đưa ra quyết định quyền**. Nó không phải `Mono.just(false)`, và cách nhiều quyết định được kết hợp phụ thuộc vào cấu hình interceptor/manager.

Nếu quy tắc của API là **“chỉ cho phép khi có quyết định ALLOW tường minh”**, bạn phải chuẩn hóa mọi abstain, lỗi và timeout thành **DENY tường minh** ở ranh giới policy:

```java
return remoteDecision
    .timeout(Duration.ofMillis(300))
    .onErrorResume(error -> Mono.just(false))
    .defaultIfEmpty(false);
```

Đây là **đoạn minh họa**, cần các imports và một `Mono<Boolean> remoteDecision` hợp lệ. Câu trả lời cuối chỉ là `true` hoặc `false`. Hãy ghi lại nguyên nhân lỗi trong metrics/log riêng; không sử dụng `onErrorReturn(true)` như fallback.

### Bốn câu hỏi cần tách

- **Có quyền gọi operation này không?** → Method Security; quyết định allow/deny.
- **Có resource trong phạm vi đã xác minh không?** → repository; có thể empty/not-found.
- **Có item nào trong một list được phép đọc không?** → `Flux.empty()` có thể hợp lệ.
- **Policy service hoặc database có đang lỗi không?** → `onError`; không tự suy luận allow hoặc “không tìm thấy”.

Mục tiêu bài học: hiểu Reactor signal semantics; xử lý abstain/error trong `@PreAuthorize`/`@PostAuthorize`; tránh fail-open; phân biệt 401/403/404/503/200 []; kiểm thử bằng StepVerifier và WebTestClient; xây một demo Java 17/Spring Boot 3.5.6.

## 2. Reactor signal: value, complete, error

Một `Mono<T>` thông thường có ba dạng kết thúc:

```text
Mono.just(value)
  onSubscribe -> onNext(value) -> onComplete

Mono.empty()
  onSubscribe -> onComplete

Mono.error(exception)
  onSubscribe -> onError(exception)
```

`onNext` và `onError` không tương đương. `Mono.empty()` không phát một value null; theo hợp đồng Reactor, `Mono.just(null)` không hợp lệ. Nếu một giá trị nullable cần chuyển thành Mono, dùng `Mono.justOrEmpty(value)`, rồi **quyết định nghiệp vụ** xem kết quả empty có ý nghĩa gì.

`Flux<T>` có thể phát nhiều `onNext` rồi `onComplete` hoặc `onError`. Khi một Flux đã stream vài tài liệu ra HTTP rồi gặp error, những bytes đã gửi **không tự được thu hồi**.

### 2.1. Ma trận theo luồng

| Luồng | Signal | Ý nghĩa | Hành vi khuyến nghị |
|---|---|---|---|
| `Mono<Boolean>` authorization | `true` | Allow tường minh | Cho qua nếu guard khác pass |
| `Mono<Boolean>` authorization | `false` | Deny tường minh | Chặn trước method |
| `Mono<Boolean>` authorization | Empty | Abstain/không có quyết định | Map false trong policy yêu cầu explicit allow |
| `Mono<Boolean>` authorization | Error | PDP/logic unavailable | Không allow; map deny hoặc propagate lỗi fail-closed |
| `Mono<Document>` data | Document | Một record được emit | Chỉ trả khi authorization đã pass |
| `Mono<Document>` data | Empty | Không emit record | 404 hoặc empty response theo API contract |
| `Mono<Document>` data | Error | Lỗi data/pipeline | 5xx/đúng error handler, không tự gọi là not found |
| `Flux<Document>` data | Empty | 0 phần tử | Thường 200 [] nếu đã có quyền LIST |
| `Flux<Document>` data | Error sau một số items | Luồng không thành công | Cẩn thận rò dữ liệu streaming |

**Kết luận:** Ký hiệu `empty` mô tả **hình thức tín hiệu**, không tự mang ý nghĩa của bất kỳ HTTP status hay authorization decision nào.

## 3. ABSTAIN không phải DENY

Spring Security Reactive Method Security sử dụng `ReactiveSecurityContextHolder` để lấy Authentication từ Reactor Context; `@EnableReactiveMethodSecurity` bật các reactive method interceptors. Ở Spring Security 6.5, bean được gọi từ SpEL có thể trả `Boolean` hoặc `Mono<Boolean>`; `Mono.empty()` có thể biểu đạt **abstain**.

```java
@Component("policy")
public class Policy {
    public Mono<Boolean> decide(Long documentId) {
        if (documentId == null) {
            return Mono.empty(); // Không quyết định.
        }
        return Mono.just(documentId == 101L);
    }
}

@PreAuthorize("@policy.decide(#documentId)")
public Mono<Document> read(
        @P("documentId") Long documentId) {
    // ...
}
```

Đây là **mẫu minh họa**, không phải class độc lập chạy được. `Mono.empty()` trong expression/manager không được dùng như “deny chắc chắn”. Nếu chính sách ở ứng dụng là bắt buộc explicit allow thì phải dùng:

```java
public Mono<Boolean> strictDecision(Mono<Boolean> source) {
    return source
        .timeout(Duration.ofMillis(300))
        .onErrorResume(error -> Mono.just(false))
        .defaultIfEmpty(false);
}
```

Khi đó:
- `Mono.just(true)` → emit true.
- `Mono.just(false)` → emit false.
- `Mono.empty()` → emit false.
- `Mono.error(ex)` → emit false.
- `Mono.never()` → timeout → emit false.

Không dùng một **OR combiner** vô tình cấp quyền khi một mandatory policy abstain. Nếu có nhiều advisors, hãy định nghĩa rõ điều kiện nào là bắt buộc: tenant membership, resource owner/share, classification, MFA và role admin có scope. Kết hợp phải tương thích nguyên tắc **deny by default**.

### 3.1. Đừng nuốt exception thành abstain

```java
// PHẢN VÍ DỤ nguy hiểm trên decision stream.
return pdp.check(user, document)
    .onErrorComplete();
```

`onErrorComplete()` làm lỗi biến thành complete không có value. Trên authorization stream, kết quả đó có thể trở thành **ABSTAIN**, không phải explicit deny.

Phản ví dụ còn nghiêm trọng hơn:

```java
// PHẢN VÍ DỤ: FAIL-OPEN.
return pdp.check(user, document)
    .onErrorReturn(true)
    .defaultIfEmpty(true);
```

Nếu PDP mất kết nối hoặc không có rule, mã trả **true**. Không thể coi đây là một cách duy trì availability an toàn cho tài liệu nhạy cảm.

### 3.2. Không để exception phá hủy observability

Adapter bảo mật có thể fail-closed và vẫn quan sát được nguyên nhân:

```java
return pdp.check(user, document)
    .timeout(Duration.ofMillis(300))
    .doOnError(error -> log.warn(
        "PDP unavailable for resourceId={}", document.id(), error))
    .onErrorResume(error -> Mono.just(false))
    .defaultIfEmpty(false);
```

`doOnError` chỉ quan sát/log; `onErrorResume` mới thay luồng error bằng quyết định DENY. Production nên phân loại `POLICY_DENY`, `POLICY_ABSTAIN`, `POLICY_TIMEOUT`, `POLICY_ERROR` và tránh ghi tokens/nội dung tài liệu nhạy cảm.

## 4. Thời điểm @PreAuthorize và @PostAuthorize

`@PreAuthorize` kiểm tra **trước khi target method thực thi**. `@PostAuthorize` kiểm tra trên **kết quả sau method** và trước khi cho caller nhận kết quả (với publishers, quyết định theo giá trị được emit). Chúng không tương đương về side effects.

```text
Subscriber
    |
    v
@PreAuthorize
    | false -> deny/error, target không chạy
    | empty -> abstain; đừng dùng để enforce deny
    | error -> failure; phải fail-closed
    v allow
Target Mono/Flux
    | value -> @PostAuthorize(returnObject)
    | empty -> không có Doc để kiểm tra owner
    | error -> lỗi data/pipeline
    v
Caller nhận dữ liệu / 403 / 404 / 5xx theo contract
```

Đây là **sơ đồ logic**. Chi tiết xử lý empty và result phụ thuộc return type, interceptor và Spring Security version; không suy diễn rằng post-check chắc chắn được chạy cho một publisher không emit value.

### 4.1. Read-only có thể sử dụng post-check

```java
@PreAuthorize("@guard.canEnter(authentication, #tenant, #id)")
@PostAuthorize(
    "@guard.canReadReturned(authentication, returnObject)"
)
public Mono<Document> inspect(
        @P("tenant") String tenant,
        @P("id") Long id) {
    return repository.fetch(tenant, id);
}
```

`canEnter` chặn sai tenant trước fetch. `canReadReturned` kiểm tra owner/share trên document **thật** được emit. Nếu post-deny, caller không được thấy document, nhưng repository **có thể đã đọc**. Đây là lý do không dùng riêng `@PostAuthorize` để giảm truy cập backend hoặc bảo vệ mutation.

### 4.2. Mutation phải được pre-check

```java
@PreAuthorize("@guard.canEdit(authentication, #tenant, #id)")
public Mono<Document> rename(
        @P("tenant") String tenant,
        @P("id") Long id, String title) {
    return Mono.defer(() -> repository.rename(tenant, id, title));
}
```

Nếu policy deny, không được đi tới logic ghi. Với database thật, tiếp tục dùng guarded update, tenant predicate, optimistic locking và transaction. **Không** dùng `@PostAuthorize` làm nơi duy nhất quyết định quyền đối với DELETE, chuyển owner, gửi email hoặc publish event: deny sau side effect không tự rollback.

### 4.3. Empty data không thay quyền

Với một read đã vượt pre-check, repository vẫn có thể trả `Mono.empty()` do record vừa bị xóa hoặc query không có match. Mapping hợp lý của lookup:

```java
return repository.findVisibleByTenantAndId(tenant, id)
    .switchIfEmpty(Mono.error(
        new ResponseStatusException(HttpStatus.NOT_FOUND)));
```

Mẫu trên cần code repository/imports để chạy. Trả 404 **sau khi bảo vệ scope** không giống tạo `Mono.empty()` ở policy rồi coi user không đủ quyền.

### 4.4. List rỗng không phải Forbidden

```java
@PreAuthorize("@guard.canList(authentication, #tenant)")
public Flux<Document> list(String tenant) {
    return repository.findVisibleDocuments(tenant);
}
```

Nếu user có quyền LIST nhưng không có tài liệu nào có quyền READ, `Flux.empty()` là kết quả hợp lệ, thường HTTP **200 []**. Ngược lại, nếu user thiếu quyền LIST, `@PreAuthorize` deny và thường trả 403.

## 5. Mapping đến HTTP: 401, 403, 404, 503, 200 []

| Sự kiện | Trạng thái thường gặp | Điều cần phân biệt |
|---|---|---|
| Anonymous vào endpoint yêu cầu login | 401 (HTTP Basic/Bearer) hoặc redirect | Authentication chưa hoàn tất |
| Authenticated bị deny bởi method | 403 | Có principal nhưng thiếu quyền |
| Record absent sau lookup trong scope hợp lệ | 404 | Data empty |
| Cross-tenant ID | 403 hoặc 404 có chủ đích | Chặn enumeration nhất quán |
| PDP timeout/unavailable | 403 fail-closed hoặc 503 fail-closed | Không trả nội dung; ghi metrics lỗi |
| Database failure | 5xx | Không giả làm “không tìm thấy” |
| LIST đã được phép nhưng không có item | 200 [] | Zero result, không phải deny |
| POST bị CSRF filter chặn | 403 | Không đồng nghĩa method policy đã deny |

`ExceptionTranslationWebFilter` và custom handlers có ảnh hưởng đến HTTP status. **Không thể quy mọi tín hiệu lỗi về 403** mà vẫn giữ đúng semantics. Trong demo, PDP error được chuyển thành false nên Spring Security trả 403; hệ thống production có thể chọn 503 để client hiểu availability bị ảnh hưởng nhưng vẫn không cho access.

## 6. Code demo Java 17, Spring Boot 3.5.6, Spring Security 6.5.x

Một dự án WebFlux có `DecisionGateway` mô phỏng PDP trả đủ **true**, **false**, **Mono.empty()** và **Mono.error()**; `DocumentGate` normalize thành explicit Boolean. Dùng `@PreAuthorize` cho READ/EDIT, kết hợp `@PostAuthorize` cho endpoint INSPECT read-only. Dùng `WebTestClient` kiểm tra HTTP và `StepVerifier` kiểm tra chính xác tín hiệu Mono.

### 6.1. Cây thư mục

```text
reactive-decision-demo/
  pom.xml
  src/main/java/com/example/decision/
    DecisionApplication.java
    SecurityConfig.java
    Document.java
    DocumentCatalog.java
    DecisionGateway.java
    SimulatedDecisionGateway.java
    DocumentGate.java
    DocumentService.java
    DocumentController.java
  src/test/java/com/example/decision/
    ReactiveDecisionTest.java
```

### 6.2. pom.xml

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
  <modelVersion>4.0.0</modelVersion>
  <parent>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-parent</artifactId>
    <version>3.5.6</version>
    <relativePath/>
  </parent>
  <groupId>com.example</groupId>
  <artifactId>reactive-decision-demo</artifactId>
  <version>1.0.0</version>
  <properties><java.version>17</java.version></properties>
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
  <build><plugins><plugin>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-maven-plugin</artifactId>
  </plugin></plugins></build>
</project>
```

Chỉ có starter WebFlux, **không** thêm Servlet MVC starter. Spring Boot quản lý version Spring Security tương ứng. Các tests dùng `mockUser`/`@WithMockUser`, không xác minh JWT/password thật.

### 6.3. Application và SecurityConfig

**`src/main/java/com/example/decision/DecisionApplication.java`**

```java
package com.example.decision;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class DecisionApplication {
    public static void main(String[] args) {
        SpringApplication.run(DecisionApplication.class, args);
    }
}
```

**`src/main/java/com/example/decision/SecurityConfig.java`**

```java
package com.example.decision;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.method.configuration.EnableReactiveMethodSecurity;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.web.server.SecurityWebFilterChain;

@Configuration
@EnableWebFluxSecurity
@EnableReactiveMethodSecurity
public class SecurityConfig {
    @Bean
    SecurityWebFilterChain security(ServerHttpSecurity http) {
        return http
            .authorizeExchange(ex -> ex
                .pathMatchers("/api/tenants/**").authenticated()
                .anyExchange().denyAll()
            )
            .httpBasic(Customizer.withDefaults())
            .build();
    }
}
```

HTTP chain buộc authenticated; service-level annotations quyết định quyền tenant/object. CSRF vẫn bật mặc định, nên test PUT có `csrf()`.

### 6.4. Document record

**`src/main/java/com/example/decision/Document.java`**

```java
package com.example.decision;

public record Document(
    Long id, String tenant, String owner,
    String state, String title) {}
```

### 6.5. DocumentCatalog: dữ liệu canonical, đếm fetch/update

**`src/main/java/com/example/decision/DocumentCatalog.java`**

```java
package com.example.decision;

import java.util.Comparator;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.ConcurrentMap;
import java.util.concurrent.atomic.AtomicInteger;
import org.springframework.stereotype.Repository;
import reactor.core.publisher.Mono;

@Repository
public class DocumentCatalog {
    private final ConcurrentMap<Long, Document> docs =
        new ConcurrentHashMap<>();

    private final Map<String, Set<String>> members = Map.of(
        "t1", Set.of("alice","bob","manager"),
        "t2", Set.of("carol","dave")
    );

    private final Set<String> adminBindings = Set.of(
        "t1:manager"
    );

    private final Set<String> viewers = Set.of("101:bob");
    private final AtomicInteger fetched = new AtomicInteger();
    private final AtomicInteger updated = new AtomicInteger();

    public DocumentCatalog() {
        reset();
    }

    public synchronized void reset() {
        docs.clear();
        docs.put(101L, new Document(
            101L,"t1","alice","ACTIVE","Owner memo"));
        docs.put(102L, new Document(
            102L,"t1","alice","ACTIVE","Private plan"));
        docs.put(103L, new Document(
            103L,"t1","alice","ACTIVE","ABSTAIN example"));
        docs.put(104L, new Document(
            104L,"t1","alice","ACTIVE","ERROR example"));
        docs.put(105L, new Document(
            105L,"t1","alice","ACTIVE","DENY example"));
        docs.put(106L, new Document(
            106L,"t1","alice","ACTIVE","ALLOW example"));
        docs.put(107L, new Document(
            107L,"t1","alice","ARCHIVED","Old report"));
        docs.put(201L, new Document(
            201L,"t2","carol","ACTIVE","South report"));
        fetched.set(0);
        updated.set(0);
    }

    public Document peek(Long id) {
        return id == null ? null : docs.get(id);
    }

    public boolean member(String tenant, String user) {
        Set<String> users = members.get(tenant);
        return users != null && user != null
            && users.contains(user);
    }

    public boolean adminBinding(String tenant, String user) {
        return tenant != null && user != null
            && adminBindings.contains(tenant + ":" + user);
    }

    public boolean viewer(Long id, String user) {
        return id != null && user != null
            && viewers.contains(id + ":" + user);
    }

    public List<Document> forTenant(String tenant) {
        return docs.values().stream()
            .filter(doc -> doc.tenant().equals(tenant))
            .sorted(Comparator.comparing(Document::id))
            .toList();
    }

    public Mono<Document> fetch(String tenant, Long id) {
        return Mono.defer(() -> {
            fetched.incrementAndGet();
            Document doc = peek(id);
            return doc != null && doc.tenant().equals(tenant)
                ? Mono.just(doc) : Mono.empty();
        });
    }

    public synchronized Document rename(
            String tenant, Long id, String title) {
        Document old = peek(id);
        if (old == null
                || !old.tenant().equals(tenant)
                || !"ACTIVE".equals(old.state())) {
            return null;
        }
        Document changed = new Document(
            id, old.tenant(), old.owner(), old.state(), title);
        docs.put(id, changed);
        updated.incrementAndGet();
        return changed;
    }

    public int fetchedCount() { return fetched.get(); }
    public int updatedCount() { return updated.get(); }
}
```

Dữ liệu seed:
- Alice/Bob/manager thuộc tenant t1; Carol/Dave thuộc t2.
- Bob được VIEWER Document#101, nhưng không được đọc Document#102.
- Document#103 nhận PDP **ABSTAIN**, #104 **ERROR**, #105 **DENY**, #106 **ALLOW**.
- Document#107 ARCHIVED; chỉ kiểm tra canonical data cũng đủ deny.
- Document#201 thuộc tenant t2.
- `fetchedCount` cho biết body của read/inspect được subscribe bao nhiêu lần.
- `updatedCount` chứng minh mutation không xảy ra khi pre-check deny.

Tất cả là fixture in-memory; production cần data store có tenant-qualified query, transaction và consistency guarantees.

### 6.6. DecisionGateway với bốn loại tín hiệu

**`src/main/java/com/example/decision/DecisionGateway.java`**

```java
package com.example.decision;

import reactor.core.publisher.Mono;

public interface DecisionGateway {
    Mono<Boolean> check(
        String principal, String action, Document doc);
}
```

**`src/main/java/com/example/decision/SimulatedDecisionGateway.java`**

```java
package com.example.decision;

import org.springframework.stereotype.Component;
import reactor.core.publisher.Mono;

@Component
public class SimulatedDecisionGateway implements DecisionGateway {
    @Override
    public Mono<Boolean> check(
            String principal, String action, Document doc) {
        return switch (doc.id().intValue()) {
            case 103 -> Mono.empty(); // ABSTAIN.
            case 104 -> Mono.error(
                new IllegalStateException("PDP unavailable"));
            case 105 -> Mono.just(false); // DENY.
            default -> Mono.just(true);   // ALLOW.
        };
    }
}
```

Đây là **PDP mô phỏng**, không phải HTTP client của OPA/OpenFGA. Điều cần học là **trạng thái thực của publisher**. Một remote PDP thật cần xác thực request giữa services, schema response, timeout, caching và audit.

### 6.7. DocumentGate: policy fail-closed

**`src/main/java/com/example/decision/DocumentGate.java`**

```java
package com.example.decision;

import java.time.Duration;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.security.authentication.AuthenticationTrustResolver;
import org.springframework.security.authentication.AuthenticationTrustResolverImpl;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.stereotype.Component;
import reactor.core.publisher.Mono;

@Component("gate")
public class DocumentGate {
    private static final Logger LOG =
        LoggerFactory.getLogger(DocumentGate.class);

    private final DocumentCatalog catalog;
    private final DecisionGateway gateway;
    private final AuthenticationTrustResolver trust =
        new AuthenticationTrustResolverImpl();

    public DocumentGate(
            DocumentCatalog catalog, DecisionGateway gateway) {
        this.catalog = catalog;
        this.gateway = gateway;
    }

    private static boolean authority(
            Authentication auth, String required) {
        if (auth == null) return false;
        for (GrantedAuthority a : auth.getAuthorities()) {
            if (required.equals(a.getAuthority())) return true;
        }
        return false;
    }

    private boolean authenticated(Authentication auth) {
        return auth != null
            && auth.isAuthenticated()
            && !trust.isAnonymous(auth);
    }

    private boolean admin(Authentication auth, String tenant) {
        return authority(auth, "ROLE_TENANT_ADMIN")
            && catalog.adminBinding(tenant, auth.getName());
    }

    // Canonical tenant, membership and resource state.
    public boolean canEnter(
            Authentication auth, String tenant, Long id) {
        if (!authenticated(auth)
                || tenant == null || tenant.isBlank()) {
            return false;
        }
        Document doc = catalog.peek(id);
        return doc != null
            && tenant.equals(doc.tenant())
            && "ACTIVE".equals(doc.state())
            && catalog.member(tenant, auth.getName());
    }

    private boolean localRead(Authentication auth, Document doc) {
        return auth.getName().equals(doc.owner())
            || catalog.viewer(doc.id(), auth.getName())
            || admin(auth, doc.tenant());
    }

    private Mono<Boolean> remote(
            Authentication auth, Document doc, String action) {
        return Mono.defer(() ->
                gateway.check(auth.getName(), action, doc))
            .timeout(Duration.ofMillis(300))
            .doOnError(error -> LOG.warn(
                "Decision error action={} id={}",
                action, doc.id(), error))
            .onErrorResume(error -> Mono.just(false))
            .defaultIfEmpty(false);
    }

    public Mono<Boolean> canRead(
            Authentication auth, String tenant, Long id) {
        if (!canEnter(auth, tenant, id)) {
            return Mono.just(false);
        }
        Document doc = catalog.peek(id);
        if (!localRead(auth, doc)) {
            return Mono.just(false);
        }
        return remote(auth, doc, "read");
    }

    public Mono<Boolean> canReadReturned(
            Authentication auth, Document doc) {
        if (doc == null
                || !canEnter(auth, doc.tenant(), doc.id())) {
            return Mono.just(false);
        }
        Document current = catalog.peek(doc.id());
        if (current == null || !current.equals(doc)
                || !localRead(auth, doc)) {
            return Mono.just(false);
        }
        return remote(auth, doc, "read");
    }

    public Mono<Boolean> canEdit(
            Authentication auth, String tenant, Long id) {
        if (!canEnter(auth, tenant, id)) {
            return Mono.just(false);
        }
        Document doc = catalog.peek(id);
        boolean editorOwner =
            auth.getName().equals(doc.owner())
            && authority(auth, "ROLE_EDITOR");
        if (!editorOwner && !admin(auth, tenant)) {
            return Mono.just(false);
        }
        return remote(auth, doc, "edit");
    }

    public boolean canList(
            Authentication auth, String tenant) {
        return authenticated(auth)
            && tenant != null
            && catalog.member(tenant, auth.getName())
            && (authority(auth, "ROLE_READER")
                || admin(auth, tenant));
    }
}
```

Điểm quan trọng:
1. Client truyền tenant trong URL nhưng `canEnter` xác nhận lại record/tenant canonical và server membership.
2. READ còn cần owner/share/tenant-scoped admin.
3. `remote` dùng `defaultIfEmpty(false)` cho ABSTAIN.
4. `onErrorResume(...false)` cho ERROR, kể cả timeout do `timeout(...)`.
5. Không có `block()`, `onErrorReturn(true)` hay `defaultIfEmpty(true)`.
6. Các method được SpEL gọi trả **explicit true/false** hoặc `Mono<Boolean>` luôn emit boolean; không cố ý phát abstain ra interceptor.
7. `canReadReturned` kiểm tra đúng giá trị được trả về, đồng thời đối chiếu snapshot canonical.
8. `canList` tách quyền liệt kê khỏi quyền trên mỗi item.

Trong production, logging phải có correlation ID, policy version và reason category. Không trả stacktrace, JWT, owner data hay thông tin nội bộ của PDP cho client. Dùng non-blocking client cho remote policy và R2DBC cho data access nếu ứng dụng có lưu lượng reactive lớn.

### 6.8. Service: pre-deny, post-deny, empty data

**`src/main/java/com/example/decision/DocumentService.java`**

```java
package com.example.decision;

import org.springframework.http.HttpStatus;
import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.access.method.P;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.security.access.prepost.PostAuthorize;
import org.springframework.security.core.context.ReactiveSecurityContextHolder;
import org.springframework.stereotype.Service;
import org.springframework.web.server.ResponseStatusException;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

@Service
public class DocumentService {
    private final DocumentCatalog catalog;
    private final DocumentGate gate;

    public DocumentService(
            DocumentCatalog catalog, DocumentGate gate) {
        this.catalog = catalog;
        this.gate = gate;
    }

    @PreAuthorize("@gate.canRead(authentication, #tenant, #id)")
    public Mono<Document> read(
            @P("tenant") String tenant, @P("id") Long id) {
        return catalog.fetch(tenant, id)
            .switchIfEmpty(Mono.error(
                new ResponseStatusException(
                    HttpStatus.NOT_FOUND, "Document not found")));
    }

    // Read-only: pre-check scope, then post-check emitted value.
    @PreAuthorize("@gate.canEnter(authentication, #tenant, #id)")
    @PostAuthorize(
        "@gate.canReadReturned(authentication, returnObject)")
    public Mono<Document> inspect(
            @P("tenant") String tenant, @P("id") Long id) {
        return catalog.fetch(tenant, id)
            .switchIfEmpty(Mono.error(
                new ResponseStatusException(
                    HttpStatus.NOT_FOUND, "Document not found")));
    }

    private Flux<Document> visible(String tenant) {
        return ReactiveSecurityContextHolder.getContext()
            .flatMapMany(context ->
                Flux.fromIterable(catalog.forTenant(tenant))
                    .filterWhen(doc -> gate.canRead(
                        context.getAuthentication(),
                        tenant, doc.id())));
    }

    @PreAuthorize("@gate.canList(authentication, #tenant)")
    public Flux<Document> list(@P("tenant") String tenant) {
        return visible(tenant);
    }

    @PreAuthorize("@gate.canList(authentication, #tenant)")
    public Mono<Document> lookup(
            @P("tenant") String tenant, String title) {
        return visible(tenant)
            .filter(doc -> doc.title().equals(title))
            .next();
    }

    // Mutations must have a pre-check, not only a post-check.
    @PreAuthorize("@gate.canEdit(authentication, #tenant, #id)")
    public Mono<Document> rename(
            @P("tenant") String tenant,
            @P("id") Long id, String title) {
        return Mono.defer(() -> {
            if (title == null || title.isBlank()) {
                return Mono.error(new ResponseStatusException(
                    HttpStatus.BAD_REQUEST, "Title required"));
            }
            Document changed = catalog.rename(tenant, id, title);
            if (changed == null) {
                return Mono.error(
                    new AccessDeniedException("Resource changed"));
            }
            return Mono.just(changed);
        });
    }
}
```

**Từ code:**
- `read` với Doc#103/104/105 bị **pre-deny**, `fetch` không chạy. `fetchedCount==0`.
- `inspect` với Bob trên Doc#102 vượt scope pre-check, đã fetch doc, nhưng post-deny do không có READ permission. `fetchedCount==1` và caller vẫn nhận 403.
- `list` của Dave t2 với ROLE_READER không có item nào được phép: `Flux.empty()`, controller có thể trả 200 [].
- `lookup` đã authorized nhưng không tìm thấy title trong tập visible: `Mono.empty()`. Controller chuyển thành 404.
- `rename` chỉ thực thi logic ghi sau pre-check; nếu PDP abstain/error, `updatedCount==0`.

**Giới hạn:** `visible(...)` dùng `filterWhen` trên toàn bộ tài liệu trong RAM và có thể tạo nhiều PDP calls. Với database lớn, phải filter permission tại query/batch, trước pagination/count; demo này chỉ minh họa semantics.

### 6.9. Controller: mapping kết quả dữ liệu

**`src/main/java/com/example/decision/DocumentController.java`**

```java
package com.example.decision;

import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PutMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ResponseStatusException;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

@RestController
@RequestMapping("/api/tenants")
public class DocumentController {
    public record RenameBody(String title) {}

    private final DocumentService service;

    public DocumentController(DocumentService service) {
        this.service = service;
    }

    @GetMapping("/{tenant}/docs/{id}")
    public Mono<Document> read(
            @PathVariable String tenant, @PathVariable Long id) {
        return service.read(tenant, id);
    }

    @GetMapping("/{tenant}/docs/{id}/inspect")
    public Mono<Document> inspect(
            @PathVariable String tenant, @PathVariable Long id) {
        return service.inspect(tenant, id);
    }

    @GetMapping("/{tenant}/docs")
    public Flux<Document> list(@PathVariable String tenant) {
        return service.list(tenant);
    }

    @GetMapping("/{tenant}/lookup")
    public Mono<Document> lookup(
            @PathVariable String tenant,
            @RequestParam String title) {
        return service.lookup(tenant, title)
            .switchIfEmpty(Mono.error(new ResponseStatusException(
                HttpStatus.NOT_FOUND, "No visible document")));
    }

    @PutMapping("/{tenant}/docs/{id}")
    public Mono<Document> rename(
            @PathVariable String tenant,
            @PathVariable Long id,
            @RequestBody RenameBody input) {
        return service.rename(tenant, id, input.title());
    }
}
```

Không lấy owner hay quyền edit từ body. Endpoint `lookup` chỉ trả 404 sau khi `@PreAuthorize` kiểm tra quyền LIST. Endpoint GET `docs/{id}` có thể trả 403 cho ID khác tenant theo chính sách demo; production có thể thống nhất 404 để giảm enumeration.

## 7. JUnit, WebTestClient và StepVerifier kiểm tra từng tín hiệu

**`src/test/java/com/example/decision/ReactiveDecisionTest.java`**

```java
package com.example.decision;

import java.util.List;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.ApplicationContext;
import org.springframework.http.MediaType;
import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.test.context.support.WithMockUser;
import org.springframework.test.web.reactive.server.WebTestClient;
import reactor.test.StepVerifier;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.springSecurity;
import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.mockUser;
import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.csrf;

@SpringBootTest
class ReactiveDecisionTest {
    @Autowired ApplicationContext context;
    @Autowired DocumentCatalog catalog;
    @Autowired DocumentGate gate;
    @Autowired DecisionGateway gateway;
    @Autowired DocumentService service;

    private WebTestClient client;

    @BeforeEach
    void setup() {
        catalog.reset();
        client = WebTestClient.bindToApplicationContext(context)
            .apply(springSecurity())
            .configureClient()
            .build();
    }

    private static String path(String tenant, long id) {
        return "/api/tenants/" + tenant + "/docs/" + id;
    }

    private WebTestClient as(String username, String... roles) {
        String[] actual = roles.length == 0
            ? new String[]{"USER"} : roles;
        return client.mutateWith(mockUser(username).roles(actual));
    }

    private WebTestClient asCsrf(
            String username, String... roles) {
        return as(username, roles).mutateWith(csrf());
    }

    private static Authentication alice() {
        return UsernamePasswordAuthenticationToken.authenticated(
            "alice", "n/a",
            List.of(new SimpleGrantedAuthority("ROLE_USER")));
    }

    @Test
    void anonymousReadGets401() {
        client.get().uri(path("t1",101))
            .exchange().expectStatus().isUnauthorized();
    }

    @Test
    void ownerWithAllowReadsDocument() {
        as("alice").get().uri(path("t1",101))
            .exchange().expectStatus().isOk()
            .expectBody()
            .jsonPath("$.title").isEqualTo("Owner memo");
        assertEquals(1, catalog.fetchedCount());
    }

    @Test
    void sharedViewerReadsDocument() {
        as("bob").get().uri(path("t1",101))
            .exchange().expectStatus().isOk();
    }

    @Test
    void crossTenantRequestDeniedBeforeFetch() {
        as("alice").get().uri(path("t2",201))
            .exchange().expectStatus().isForbidden();
        assertEquals(0, catalog.fetchedCount());
    }

    @Test
    void forgedTenantPathDeniedBeforeFetch() {
        as("alice").get().uri(path("t1",201))
            .exchange().expectStatus().isForbidden();
        assertEquals(0, catalog.fetchedCount());
    }

    @Test
    void archivedDocumentDeniedBeforeFetch() {
        as("alice").get().uri(path("t1",107))
            .exchange().expectStatus().isForbidden();
        assertEquals(0, catalog.fetchedCount());
    }

    @Test
    void unknownDocumentDeniedBeforeFetch() {
        as("alice").get().uri(path("t1",999))
            .exchange().expectStatus().isForbidden();
        assertEquals(0, catalog.fetchedCount());
    }

    @Test
    void abstainBecomesDenyBeforeFetch() {
        as("alice").get().uri(path("t1",103))
            .exchange().expectStatus().isForbidden();
        assertEquals(0, catalog.fetchedCount());
    }

    @Test
    void errorBecomesDenyBeforeFetch() {
        as("alice").get().uri(path("t1",104))
            .exchange().expectStatus().isForbidden();
        assertEquals(0, catalog.fetchedCount());
    }

    @Test
    void explicitDenyBeforeFetch() {
        as("alice").get().uri(path("t1",105))
            .exchange().expectStatus().isForbidden();
        assertEquals(0, catalog.fetchedCount());
    }

    @Test
    void explicitAllowPermitsFetch() {
        as("alice").get().uri(path("t1",106))
            .exchange().expectStatus().isOk();
        assertEquals(1, catalog.fetchedCount());
    }

    @Test
    void missingShareDeniedAtPreCheck() {
        as("bob").get().uri(path("t1",102))
            .exchange().expectStatus().isForbidden();
        assertEquals(0, catalog.fetchedCount());
    }

    @Test
    void postDeniedAfterFetch() {
        as("bob").get().uri(path("t1",102)+"/inspect")
            .exchange().expectStatus().isForbidden();
        assertEquals(1, catalog.fetchedCount());
    }

    @Test
    void postAllowsSharedViewer() {
        as("bob").get().uri(path("t1",101)+"/inspect")
            .exchange().expectStatus().isOk();
        assertEquals(1, catalog.fetchedCount());
    }

    @Test
    void postAbstainFailsClosedAfterFetch() {
        as("alice").get().uri(path("t1",103)+"/inspect")
            .exchange().expectStatus().isForbidden();
        assertEquals(1, catalog.fetchedCount());
    }

    @Test
    void postErrorFailsClosedAfterFetch() {
        as("alice").get().uri(path("t1",104)+"/inspect")
            .exchange().expectStatus().isForbidden();
        assertEquals(1, catalog.fetchedCount());
    }

    @Test
    void fakeAdminRoleWithoutTenantBindingDenied() {
        as("bob","TENANT_ADMIN")
            .get().uri(path("t1",102))
            .exchange().expectStatus().isForbidden();
    }

    @Test
    void boundAdminReadsOwnTenant() {
        as("manager","TENANT_ADMIN")
            .get().uri(path("t1",102))
            .exchange().expectStatus().isOk();
    }

    @Test
    void boundAdminCannotCrossTenant() {
        as("manager","TENANT_ADMIN")
            .get().uri(path("t2",201))
            .exchange().expectStatus().isForbidden();
    }

    @Test
    void listWithoutRoleIsForbidden() {
        as("bob").get().uri("/api/tenants/t1/docs")
            .exchange().expectStatus().isForbidden();
    }

    @Test
    void listFiltersUnreadableDocuments() {
        as("bob","READER").get().uri("/api/tenants/t1/docs")
            .exchange().expectStatus().isOk()
            .expectBody()
            .jsonPath("$[0].id").isEqualTo(101)
            .jsonPath("$[1]").doesNotExist();
    }

    @Test
    void emptyFluxIsNotForbidden() {
        as("dave","READER").get().uri("/api/tenants/t2/docs")
            .exchange().expectStatus().isOk()
            .expectBody().json("[]");
    }

    @Test
    void allowedLookupButEmptyMonoBecomes404() {
        as("dave","READER")
            .get().uri("/api/tenants/t2/lookup?title=missing")
            .exchange().expectStatus().isNotFound();
    }

    @Test
    void listPermissionMissingDoesNotMeanEmpty() {
        as("dave").get().uri("/api/tenants/t2/docs")
            .exchange().expectStatus().isForbidden();
    }

    @Test
    void ownerEditorCanRenameWithCsrf() {
        asCsrf("alice","EDITOR")
            .put().uri(path("t1",101))
            .contentType(MediaType.APPLICATION_JSON)
            .bodyValue("{\"title\":\"Updated\"}")
            .exchange().expectStatus().isOk();
        assertEquals(1, catalog.updatedCount());
    }

    @Test
    void noEditRolePreventsMutation() {
        asCsrf("alice").put().uri(path("t1",101))
            .contentType(MediaType.APPLICATION_JSON)
            .bodyValue("{\"title\":\"Denied\"}")
            .exchange().expectStatus().isForbidden();
        assertEquals(0, catalog.updatedCount());
    }

    @Test
    void viewerCannotEditEvenWithRole() {
        asCsrf("bob","EDITOR").put().uri(path("t1",101))
            .contentType(MediaType.APPLICATION_JSON)
            .bodyValue("{\"title\":\"Denied\"}")
            .exchange().expectStatus().isForbidden();
        assertEquals(0, catalog.updatedCount());
    }

    @Test
    void abstainBeforeEditNeverWrites() {
        asCsrf("alice","EDITOR").put().uri(path("t1",103))
            .contentType(MediaType.APPLICATION_JSON)
            .bodyValue("{\"title\":\"Denied\"}")
            .exchange().expectStatus().isForbidden();
        assertEquals(0, catalog.updatedCount());
    }

    @Test
    void errorBeforeEditNeverWrites() {
        asCsrf("alice","EDITOR").put().uri(path("t1",104))
            .contentType(MediaType.APPLICATION_JSON)
            .bodyValue("{\"title\":\"Denied\"}")
            .exchange().expectStatus().isForbidden();
        assertEquals(0, catalog.updatedCount());
    }

    @Test
    void csrfBlocksOtherwiseAllowedMutation() {
        as("alice","EDITOR").put().uri(path("t1",101))
            .contentType(MediaType.APPLICATION_JSON)
            .bodyValue("{\"title\":\"Denied\"}")
            .exchange().expectStatus().isForbidden();
        assertEquals(0, catalog.updatedCount());
    }

    @Test
    void rawAbstainPublisherHasNoValue() {
        StepVerifier.create(
            gateway.check("alice","read",catalog.peek(103L)))
            .verifyComplete();
    }

    @Test
    void rawErrorPublisherEmitsError() {
        StepVerifier.create(
            gateway.check("alice","read",catalog.peek(104L)))
            .expectError(IllegalStateException.class)
            .verify();
    }

    @Test
    void normalizedAbstainYieldsFalse() {
        StepVerifier.create(gate.canRead(alice(),"t1",103L))
            .expectNext(false).verifyComplete();
    }

    @Test
    void normalizedErrorYieldsFalse() {
        StepVerifier.create(gate.canRead(alice(),"t1",104L))
            .expectNext(false).verifyComplete();
    }

    @Test
    void normalizedExplicitDenyYieldsFalse() {
        StepVerifier.create(gate.canRead(alice(),"t1",105L))
            .expectNext(false).verifyComplete();
    }

    @Test
    void normalizedAllowYieldsTrue() {
        StepVerifier.create(gate.canRead(alice(),"t1",106L))
            .expectNext(true).verifyComplete();
    }

    @Test
    @WithMockUser(username = "bob")
    void directServicePostDenyEmitsAccessDenied() {
        StepVerifier.create(service.inspect("t1",102L))
            .expectError(AccessDeniedException.class)
            .verify();
    }

    @Test
    @WithMockUser(username = "alice")
    void directServicePreDenyEmitsAccessDenied() {
        StepVerifier.create(service.read("t1",103L))
            .expectError(AccessDeniedException.class)
            .verify();
        assertEquals(0, catalog.fetchedCount());
    }
}
```

Chạy từ thư mục chứa `pom.xml`:

```bash
mvn test
```

**Kết quả kỳ vọng từ mã nguồn:** các test kiểm tra chính xác allow/deny/abstain/error, HTTP 401/403/404/200 [], pre-vs-post fetch, và không ghi dữ liệu khi pre-deny. Đây là **bộ test được soạn và kiểm tra nội dung, chưa thực thi Maven**; chỉ xem các assertions là kết quả thật sau khi chạy trong môi trường có dependency tương ứng.

Các test dùng `WebTestClient.bindToApplicationContext(...).apply(springSecurity())` nên đi qua WebFlux filters; `mockUser` cung cấp principal giả. `StepVerifier.verifyComplete()` trên raw `Mono.empty()` chỉ chứng minh publisher complete không phát value; `expectNext(false)` chứng minh adapter **emit một quyết định deny tường minh**; `expectError(...)` chứng minh có error signal. Đây là ba trạng thái khác nhau, không thể thay lẫn.

## 8. Phân tích những kết quả quan trọng

### 8.1. Tại sao Doc#103 bị deny trước fetch?

Với Alice:
- Authentication hợp lệ; membership t1 đúng; document ACTIVE và Alice owner.
- Gateway trả `Mono.empty()` (ABSTAIN).
- `DocumentGate.remote` dùng `defaultIfEmpty(false)`.
- `@PreAuthorize` nhận false → ngăn target service.
- HTTP trả 403, `fetchedCount==0`.

Nếu xóa `defaultIfEmpty(false)`, ứng dụng có thể trở lại semantics abstain của interceptor. Không dựa vào hành vi đó để enforce deny.

### 8.2. Tại sao Doc#104 cũng bị deny trước fetch?

Gateway ném `IllegalStateException("PDP unavailable")` qua `Mono.error`. `doOnError` ghi metric/log; `onErrorResume(...Mono.just(false))` giữ fail-closed. Request không nhận dữ liệu, nhưng hệ thống giám sát vẫn cần thấy đây là **PDP outage**, không phải permission policy cố ý deny.

### 8.3. Tại sao inspect Doc#102 được đọc rồi mới bị 403?

`inspect` chỉ pre-check tenant/state, nên Bob thuộc t1 vượt được giai đoạn đó. `catalog.fetch` emit Document#102, nhưng `@PostAuthorize` phát hiện Bob không owner/share/admin. Kết quả không được trả ra caller; counter fetched tăng. Đây là **tác dụng của post authorization**, không phải rollback.

### 8.4. Tại sao LIST Dave t2 trả 200 [] còn LOOKUP trả 404?

Dave có ROLE_READER và membership t2, nên được phép gọi cả hai operations. Nhưng Carol sở hữu Doc#201, Dave không được share; lọc per-object cho kết quả rỗng.
- `Flux.empty()` của LIST → JSON array rỗng, 200.
- `Mono.empty()` của LOOKUP → controller `switchIfEmpty(...NOT_FOUND)`, 404.
- Nếu Dave thiếu ROLE_READER → `@PreAuthorize` deny, 403.

Không được dùng `200 []` để thay cho mọi 403, hoặc dùng 403 thay cho mọi empty.

## 9. Production: tín hiệu lỗi, nhất quán và dữ liệu lớn

### 9.1. Truy vấn theo tenant và permission

Trong demo, catalog là RAM. Ở database thật, method cần tránh `findById(id)` khi nhiều tenant dùng chung dữ liệu. Mẫu SQL:

```sql
SELECT d.id, d.tenant_id, d.owner_id, d.state, d.title
FROM document d
WHERE d.id = :documentId
  AND d.tenant_id = :verifiedTenant
  AND d.state = 'ACTIVE';
```

Sau truy vấn tenant-qualified, vẫn cần owner/share/admin action permission. Với list lớn, đưa điều kiện READ vào query trước pagination và count, thay vì lấy tất cả rồi `Flux.filterWhen` gọi PDP từng record. Điều đó giảm N+1, tránh phân trang sai và giảm rò metadata.

### 9.2. Update có điều kiện

```sql
UPDATE document
SET title = :title
WHERE id = :documentId
  AND tenant_id = :verifiedTenant
  AND owner_id = :authenticatedPrincipal
  AND state = 'ACTIVE';
```

Đây là mẫu SQL giới hạn owner; nếu có share EDITOR hay admin, thêm predicate đúng tenant/action. Kiểm tra affected-row count = 1 và version/transaction để giảm TOCTOU. `@PreAuthorize` không tự làm SQL atomic với quyết định PDP.

### 9.3. Không stream dữ liệu rồi mới kiểm tra

Nếu một `Flux<Document>` đã gửi 100 records qua HTTP rồi item thứ 101 gặp error, response có thể đã chứa 100 records. Do đó:
- Authorize operation trước stream.
- Filter/restrict source query để không đọc/emit dữ liệu vượt tenant.
- Đối với all-or-nothing, validate phạm vi trước khi stream và xem xét memory.
- Không dùng `onErrorContinue` tùy tiện để bỏ qua permission errors.
- Với remote PDP per-row, dùng batch checks/guarded SQL hoặc model đã review.

### 9.4. Transaction và side effects

`@PostAuthorize` trên một method trả `Mono` đã ghi DB không tự rollback email, webhook, message broker hay transaction. Write/delete phải dùng `@PreAuthorize`, guarded update, `ReactiveTransactionManager`/`TransactionalOperator` nếu dùng R2DBC, và transactional outbox nếu liên quan external events.

### 9.5. Timeout, retry và cache

Một PDP có thể trả `Mono.never()` nếu dependency treo. Không có timeout thì subscription có thể chờ vô hạn. Đặt timeout hữu hạn, retry có giới hạn, circuit breaker và alert. Với cache:
- Key có principal, tenant, resource, action, policy version.
- Xác định SLA revoke và invalidation.
- Cache cũ không tự tạo quyền sau khi membership bị thu hồi.
- Không dùng fallback allow khi hết hạn hoặc PDP down trừ khi security proof rất rõ.

### 9.6. Không block event-loop

Bean method authorization có thể trả `Mono<Boolean>`. Không gọi `block()` bên trong SpEL hoặc trên Reactor event-loop để ép lấy quyết định từ DB/HTTP. Dùng non-blocking clients, `timeout` và các publishers. Khi data source chỉ có JDBC blocking, thiết kế scheduler và thread pool có giới hạn hoặc chuyển R2DBC; không gọi blocking code vô điều kiện trên event-loop.

## 10. Lỗi thường gặp

| Sai lầm | Hậu quả | Sửa |
|---|---|---|
| PDP trả empty được coi là false chắc chắn | ABSTAIN bị hiểu nhầm | `defaultIfEmpty(false)` |
| PDP error được chuyển `onErrorComplete()` | Lỗi thành abstain | `onErrorResume(...false)` + audit |
| `onErrorReturn(true)` | Fail-open | Never allow on outage |
| HTTP 200 từ PDP = allow | Response thiếu `result`/`allowed` vẫn qua | Chỉ boolean true |
| Repository empty = access denied | Lẫn 404 với 403 | Contract rõ theo nguồn empty |
| `Flux.empty()` = user thiếu quyền LIST | Lẫn 200 [] với 403 | Authorize LIST trước |
| Nuốt DB error thành empty | Che outage và lỗi cache | Preserve 5xx signal |
| `@PostAuthorize` cho mutation | Side effect xảy ra trước deny | `@PreAuthorize` và guarded DML |
| Chỉ bảo vệ route HTTP | Object-level BOLA/IDOR | Tenant + owner/share action |
| Gọi `block()` trong policy | Tắc event-loop | Mono<Boolean> non-blocking |
| `Mono.never()` không timeout | Request treo | Bounded timeout |
| Retry vô hạn | PDP outage thành retry storm | Retry budget |
| `filterWhen` sau phân trang | N+1, sai page/count | SQL scope trước paging |
| Không xem Reactor Context | Sai/mất principal trên async | ReactiveSecurityContextHolder |
| Cache thiếu tenant/action/version | Quyền stale, cross-tenant | Cache key chuẩn và revoke invalidation |
| Chỉ test true/false | Không thấy lỗi abstain/error | Test 4 signals và pre/post counters |
| Coi post-deny là rollback | Update/email có thể đã chạy | Pre-check, transaction, outbox |

## 11. Checklist review

- [ ] Phân biệt rạch ròi **data empty**, **decision abstain** và **error signal**.
- [ ] `@EnableReactiveMethodSecurity` được bật, methods đi qua Spring proxy.
- [ ] Authentication lấy từ Reactor/Spring Security chứ không từ header tự khai.
- [ ] Remote decision contract chỉ cho ALLOW khi explicit true.
- [ ] `Mono.empty()`, error và timeout từ PDP thành deny rõ trong policy bắt buộc.
- [ ] Logs/metrics phân biệt policy deny, abstain, timeout và error.
- [ ] Không `defaultIfEmpty(true)`/`onErrorReturn(true)` trong đường quyền.
- [ ] `@PreAuthorize` trước write/delete và các external side effects.
- [ ] `@PostAuthorize` chỉ dùng khi được phép đọc result trước khi authorize trả ra.
- [ ] Empty result của lookup/list được map 404/200 [] theo business contract.
- [ ] HTTP 401/403/404/503 được test với đúng authentication mechanism.
- [ ] Tenant canonical, membership và owner/share đã được kiểm tra.
- [ ] Không query mọi tenant rồi lọc sau pagination.
- [ ] Có guarded DB update, affected-row checks và concurrency control.
- [ ] Có WebTestClient negative tests với role/tenant/CSRF.
- [ ] Có StepVerifier tests phân biệt value/empty/error/false.
- [ ] Test khi PDP mất kết nối, abstain, timeout, revoke quyền và cache stale.
- [ ] Không stream dữ liệu trái quyền trước khi kiểm tra.
- [ ] Không sử dụng blocking SDK trên WebFlux event-loop.

## 12. Câu hỏi tự kiểm tra

**1.** `Mono.empty()` từ bean policy có phải `Mono.just(false)` không?

**Đáp án:** Không. Spring Security 6.5 có thể hiểu là abstain. Nếu yêu cầu explicit allow, normalize empty → false.

**2.** `Mono.error(TimeoutException)` có đồng nghĩa một quyết định deny hợp lệ không?

**Đáp án:** Không, đó là failure signal. Hệ thống phải fail-closed nhưng vẫn ghi nhận đây là outage/timeout thay vì policy deny thông thường.

**3.** Vì sao `onErrorComplete()` là nguy hiểm trong decision stream?

**Đáp án:** Nó biến error thành empty/abstain, có thể bỏ qua bắt buộc deny trong một combiner không có rule explicit.

**4.** User có quyền LIST nhưng không có document phù hợp. Trả gì?

**Đáp án:** Thường 200 [], vì `Flux.empty()` sau khi đã authorize LIST là kết quả không có item.

**5.** Đọc một document trả `Mono.empty()` sau khi đã kiểm tra tenant/permission. Có thể trả 404 không?

**Đáp án:** Có, nếu API contract là not found. Không dùng kết quả này thay quyết định quyền của một user chưa được authorize.

**6.** Post-check bị deny sau khi repository đã fetch; có thể suy luận repository chưa đọc gì không?

**Đáp án:** Không. `@PostAuthorize` kiểm tra sau khi có result; dữ liệu có thể đã được đọc và tác dụng phụ trước đó không tự rollback.

**7.** `StepVerifier.verifyComplete()` với raw empty PDP và `expectNext(false).verifyComplete()` với normalized decision khác nhau thế nào?

**Đáp án:** Trường hợp đầu không emit giá trị; trường hợp hai emit explicit deny rồi hoàn tất. Đó là semantics khác nhau của Reactor.

## 13. Tài liệu chính thức

- [Spring Security 6.5 — EnableReactiveMethodSecurity](https://docs.spring.io/spring-security/reference/6.5/reactive/authorization/method.html): Reactor Context, `@PreAuthorize`/`@PostAuthorize`, bean trả `Mono<Boolean>` và `Mono.empty()` như abstain.
- [Spring Security 6.5 — Testing Reactive Method Security](https://docs.spring.io/spring-security/reference/6.5/reactive/test/method.html): `@WithMockUser`, `StepVerifier`.
- [Spring Security 6.5 — WebTestClient Setup](https://docs.spring.io/spring-security/reference/6.5/reactive/test/web/setup.html): `springSecurity()`, `bindToApplicationContext`.
- [Spring Security 6.5 — Reactive Testing Authentication](https://docs.spring.io/spring-security/reference/6.5/reactive/test/web/authentication.html): `mockUser`, role/authorities.
- [Spring Security 6.5 — Reactive Testing CSRF](https://docs.spring.io/spring-security/reference/6.5/reactive/test/web/csrf.html): `csrf()`.
- [Spring Security 6.5 — PostAuthorizeReactiveAuthorizationManager Javadoc](https://docs.spring.io/spring-security/site/docs/6.5.x/api/org/springframework/security/authorization/method/PostAuthorizeReactiveAuthorizationManager.html): after-method authorization manager.
- [Project Reactor — Handling Errors](https://projectreactor.io/docs/core/release/reference/coreFeatures/error-handling.html): `onErrorReturn`, `onErrorResume` và `onErrorComplete`.
- [Project Reactor — Testing](https://projectreactor.io/docs/test/release/reference/): `StepVerifier`, kiểm tra complete/error/value.
- [OWASP API Security Top 10 — BOLA](https://owasp.org/API-Security/editions/2023/en/0xa1-broken-object-level-authorization/): bảo vệ từng resource ID.

**Ghi nhớ:** Trong Reactive Method Security, **ABSTAIN không phải DENY**, **ERROR không phải một quyết định quyền**, và **empty data không phải tự động 403**. Chỉ cấp quyền khi có **explicit allow**, chuẩn hóa empty/error/timeout từ PDP thành fail-closed, bảo vệ mutation bằng `@PreAuthorize`, dùng `@PostAuthorize` đúng cho read-only results, và kiểm thử riêng từng signal bằng `StepVerifier` cùng các trạng thái HTTP qua `WebTestClient`.