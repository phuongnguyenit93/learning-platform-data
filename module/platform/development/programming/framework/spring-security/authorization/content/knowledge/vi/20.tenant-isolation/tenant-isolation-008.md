# Khóa cache chứa tenant để tránh lẫn quyền hoặc kết quả

> **Chủ đề:** Spring Security – authorization · **Nhóm:** Cách ly tenant. Trong một ứng dụng phục vụ nhiều khách hàng, cache là một đường truy cập dữ liệu **thực sự**, không chỉ là tối ưu hiệu năng. Một khóa cache không chứa tenant hoặc không chứa các yếu tố định hình quyền có thể khiến user ở tenant B nhận dữ liệu hay kết quả phân quyền của tenant A. Bài này trình bày mô hình khóa, ranh giới kiểm tra authorization, Spring Cache `@Cacheable`/`@CacheEvict`, Redis/cache phân tán, các cơ chế invalidation và kiểm thử chống cross-tenant leakage. Ví dụ chính hướng tới Java 17+, Spring Boot 3.x, Spring Framework 6.x, Spring Security 6.x; các chi tiết có thể khác ở Spring Boot 4/Spring Framework 7 nên cần đối chiếu version runtime.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Giải thích vì sao **hai resource có cùng ID nhưng khác tenant** tuyệt đối không được dùng chung cache entry.
2. Tách cache **dữ liệu**, **kết quả truy vấn**, **kết quả phép kiểm quyền** và **authentication/membership context**; xây khóa đúng cho từng loại.
3. Hiểu thuật toán key mặc định của Spring Cache và khi nào `@Cacheable(key = "...")` vô tình bỏ tenant.
4. Lấy tenant từ **nguồn đã được xác minh**, không từ header/path/JWT claim chưa kiểm tra; xây cache key có cấu trúc, không đụng collision do nối chuỗi.
5. Bảo đảm authentication và tenant authorization **vẫn thực thi trên cache hit**, kể cả khi cache trả giá trị mà không chạy method body.
6. Thiết kế eviction, TTL, cache versioning, revoke/grant handling, read-your-writes và tương quan giữa DB commit với invalidation.
7. Viết integration test có hai tenant dùng cùng document ID; test user đổi active tenant, bị thu hồi membership, có role khác nhau ở từng tenant và update không làm rò dữ liệu.
8. Tìm lỗi do `ThreadLocal`, `SecurityContext`, `@Async`, distributed Redis cache, serialization, cache warmup, batch jobs và logging.
9. Áp dụng chiến lược fail closed cho permission-decision cache thay vì lưu `allowed=true` vô hạn hoặc tái sử dụng trên principal khác.

## 2. Vấn đề: cache hit có thể thành một lỗi phân quyền

Giả sử platform SaaS có dữ liệu:

~~~text
Tenant alpha:
  Document id=7
  title="ALPHA:Budget"
  allowed users: Alice

Tenant beta:
  Document id=7
  title="BETA:Budget"
  allowed users: Bob
~~~

Ứng dụng có service:

~~~java
// PHẢN VÍ DỤ: key chỉ là documentId.
@Cacheable(cacheNames = "document", key = "#p0")
public Document loadById(Long documentId) {
    return repository.findById(documentId).orElseThrow();
}
~~~

Đây là mã trích đoạn không đủ lớp Spring/JPA. Luồng có thể xảy ra:

~~~text
Alice, tenant=alpha, GET /documents/7
  cache key = "document::7"
  miss -> DB trả ALPHA:Budget -> cache["7"] = ALPHA:Budget

Bob, tenant=beta, GET /documents/7
  cache key = "document::7"
  hit -> cache trả ALPHA:Budget
  method body không được chạy nữa
  -> Bob có nguy cơ thấy dữ liệu alpha!
~~~

Ngay cả khi repository có một tenant filter trong thân method, cache hit có thể **trả trước khi method chạy**, nên việc bảo vệ tenant chỉ đặt trong thân một method đã cache là chưa đủ đối với những đường gọi không có lớp authorization bên ngoài.

**Quy tắc cơ bản:** cache là một phần của **đường đọc dữ liệu cần authorization**. Cache không được là lối tắt bỏ qua tenant membership, permission check hoặc tenant-scoped repository.

## 3. Định nghĩa: một khóa cache phản ánh điều gì?

Một key tốt phải xác định duy nhất **giá trị được phép tái sử dụng** theo các chiều ảnh hưởng đến nội dung/quyền. Với raw document chung trong tenant, key tối thiểu có dạng:

~~~text
cache name      = tenantDocument
logical key     = {tenantId, documentId}
example         = tenantDocument::alpha:7
another tenant  = tenantDocument::beta:7
~~~

Nếu hai tenant có cùng `documentId=7`, chúng vẫn là **hai khóa khác nhau**.

Với dữ liệu cần phân biệt theo bản dịch, phiên bản, trạng thái, vùng dữ liệu hoặc loại resource, bổ sung:

~~~text
{namespace, schemaVersion, tenantId, resourceType, resourceId,
 locale?, projection?, filter?, page?, consistencyVersion?}
~~~

Không phải càng dài càng an toàn. Mỗi chiều phải dựa trên việc **cùng key có thực sự đồng nghĩa cùng kết quả được phép chia sẻ** hay không.

### 3.1. Bốn nhóm cache cần suy nghĩ khác nhau

| Loại cache | Ví dụ dữ liệu | Thành phần key ít nhất | Lưu ý bảo mật |
| --- | --- | --- | --- |
| **Dữ liệu resource chung trong tenant** | Document metadata chưa personalization | tenantId + documentId + type/schemaVersion | Vẫn authorize caller trước khi trả |
| **Kết quả danh sách/truy vấn** | Tìm document đã lọc | tenantId + canonical filters + sort + page + projection | Tránh trộn search result/total count giữa tenant |
| **Kết quả người dùng nhìn thấy** | “My documents”, redacted DTO | tenantId + principalId + action/view + query parameters | Nếu role/ACL thay đổi phải invalidate/re-check; cache output có thể tiết lộ thông tin |
| **Kết quả authorization** | `canRead(user, doc) = true` | tenantId + principalId + target type/id + action + security/policy revisions | Rất nhạy cảm; có thể **không cache** là lựa chọn an toàn nhất |

Không dùng một cache name `"result"` cho cả document raw, list export và permission boolean nếu schema key/value khác nhau. Nên phân loại namespace và TTL; đặt tên rõ `tenantDocumentById`, `tenantSearchPage`, `permissionDecision`...

### 3.2. Tenant trong key phải là tenant đã xác minh

Một request có header:

~~~http
GET /api/documents/7
X-Tenant-ID: beta
Authorization: Bearer [token của Alice]
~~~

Không có nghĩa Alice được đọc beta. Cần xác thực principal, kiểm tra membership active, quyền action trong tenant, sau đó mới tạo **trusted tenant context**. Cache key chỉ dựa trên `X-Tenant-ID` không thay việc authorization, và đôi khi cho phép một attacker chủ động “mượn” partition của tenant khác.

Tối ưu đúng:

~~~text
requestedTenantId (untrusted)
   -> membership/action verification
   -> authorizedTenantId (trusted)
   -> tenant-scoped cache key
   -> data lookup/cache
   -> object-level/response policy nếu có
~~~

Khi tenant trong JWT, phải validate chữ ký/issuer/audience/expiry theo security config, rồi kiểm tra claim có nghĩa gì trong ứng dụng: tenant selection claim không đương nhiên cấp quyền mọi document của tenant đó.

## 4. Spring Cache tạo key mặc định thế nào?

Với `@EnableCaching`, Spring Framework dùng `CacheInterceptor`/`CacheOperationSource` để áp cache cho Spring-managed bean qua proxy/advice. Với generator mặc định trong Spring Framework 6.x, key dựa trên **tham số được truyền vào method**:

| Số tham số | Key mặc định (khái niệm) |
| --- | --- |
| 0 | `SimpleKey.EMPTY` |
| 1 | Chính tham số đó |
| Nhiều hơn 1 | `SimpleKey` chứa mọi tham số, giữ ngữ nghĩa `equals/hashCode` |

Ví dụ:

~~~java
@Cacheable("tenantDocument")
Document load(String tenantId, Long documentId) { ... }
~~~

Nếu gọi `load("alpha",7L)` và `load("beta",7L)`, key mặc định thường phân biệt do tham số tenant khác nhau. Nhưng có hai bẫy:

**Bẫy A: method không nhận tenant.**

~~~java
@Cacheable("tenantDocument")
Document load(Long id) {
    // Tenant được đọc ngầm từ ThreadLocal ở trong body.
    return repository.findWithinTenant(TenantContext.get(), id);
}
~~~

Key mặc định chỉ nhận `id`. Hai request alpha/beta cùng id collision; Spring không tự đoán có một ThreadLocal ngoài signature.

**Bẫy B: key tùy chỉnh đã loại tenant.**

~~~java
@Cacheable(cacheNames = "tenantDocument", key = "#p1")
Document load(String tenantId, Long id) { ... }
~~~

Có hai tham số nhưng custom key chỉ dùng `id`. Key mặc định không còn cứu bạn: `@Cacheable.key` thay thế logic sinh key.

### 4.1. SpEL đúng cho khóa tenant và ID

~~~java
@Cacheable(
    cacheNames = "tenantDocument",
    key = "#p0 + ':' + #p1"
)
Document load(String trustedTenant, Long documentId) {
    return repository.findByTenantIdAndId(
            trustedTenant, documentId).orElseThrow();
}
~~~

`#p0` là đối số thứ nhất, `#p1` là đối số thứ hai. Viết `#p0`/`#p1` tránh phụ thuộc vào tên tham số được giữ khi compile với `-parameters`. Đây là trích đoạn: method trong Spring bean/proxy, tenant đã được xác minh ở lớp gọi, repository có tenant predicate.

Nếu tenant là ID tự do có thể chứa `:` hoặc nhiều trường là string tự do, nối chuỗi đơn giản có thể dẫn tới **collision**:

~~~text
tenant="a:b", documentId="7" -> "a:b:7"
tenant="a",   documentId="b:7" -> "a:b:7"
~~~

Hãy dùng ID tenant có grammar chặt, ID document kiểu Long/UUID canonical, hoặc dùng cấu trúc `SimpleKey`/record/encoding có độ dài/escape rõ. Có thể dùng:

~~~java
// Trong mã Java có Spring Cache dependency:
var key = new org.springframework.cache.interceptor.SimpleKey(
        tenantId, "Document", documentId);
~~~

Khi dùng key dạng object với Redis, cần **kiểm tra serializer/key conversion**. Một object `SimpleKey` của local cache không đương nhiên có biểu diễn Redis an toàn/ổn định khi đổi serializer, Java version hoặc ngôn ngữ khác. Đặt key format thành contract có version nếu nhiều instance đọc cùng cache.

### 4.2. KeyGenerator tùy chỉnh

Khi nhiều method cùng dùng quy ước tenant, có thể tạo một `KeyGenerator`:

~~~java
// Trích đoạn config trong Spring project.
@Bean("tenantAwareKeyGenerator")
KeyGenerator tenantAwareKeyGenerator() {
    return (target, method, params) -> {
        if (params.length < 2
                || !(params[0] instanceof String tenant)
                || !(params[1] instanceof Long id)) {
            throw new IllegalArgumentException(
                    "Expected trusted tenant and Long id");
        }

        // Namespace method/resource type tránh collision giữa các cache.
        return new SimpleKey(
                "v2", target.getClass().getName(),
                method.getName(), tenant, id);
    };
}
~~~

Imports chính: `org.springframework.cache.interceptor.KeyGenerator` và `org.springframework.cache.interceptor.SimpleKey`, `org.springframework.context.annotation.Bean`. Dùng:

~~~java
@Cacheable(cacheNames = "tenantDocument",
           keyGenerator = "tenantAwareKeyGenerator")
Document load(String trustedTenant, Long id) {
    return repository.findByTenantIdAndId(
            trustedTenant, id).orElseThrow();
}
~~~

**Không khai báo cả `key` và `keyGenerator` trên cùng annotation**: chúng là hai cách cấu hình thay thế nhau. Với ví dụ này, Spring có thể dùng proxy class cho `target`; nếu muốn namespace ổn định qua nâng version/proxy, dùng một resource type explicit thay cho `target.getClass().getName()`. Đặt key generator là **quy ước đã kiểm thử**, không phải phép chứng minh caller có membership.

## 5. Cache hit không được vượt qua authorization

### 5.1. Vì sao đặt @PreAuthorize và @Cacheable chung method cần thận trọng?

Một method có thể đồng thời có:

~~~java
@PreAuthorize("hasPermission(#p1, 'Document', 'read')")
@Cacheable(cacheNames = "tenantDocument", key = "#p0 + ':' + #p1")
public Document read(String tenantId, Long id) {
    return repository.findByTenantIdAndId(tenantId,id).orElseThrow();
}
~~~

Đoạn này là **phản ví dụ kiến trúc**: security expression chỉ kiểm tra quyền theo ID, không bảo đảm type/id gắn tenant; hơn nữa cả caching và method security dùng Spring AOP advisors, thứ tự interception cần được xác định và kiểm thử. Nếu advice cache trả thẳng trên hit trước khi security advice chạy, có thể làm mất bước kiểm quyền trên hit. Không khẳng định một thứ tự advisors mặc định duy nhất bất kể Spring version/config.

Đặc biệt, method body không được chạy trên cache hit, nên kiểm tra tenant/owner/role đặt **chỉ trong method body** có thể bị bỏ qua.

### 5.2. Cấu trúc khuyến nghị: service kiểm quyền ở bên ngoài, cache reader ở bean khác

~~~text
HTTP/controller
    |
    v
DocumentService (bean A):
  @PreAuthorize("hasAuthority('document:read')")
  verify membership + tenant-specific read permission
  -> CachedDocumentReader (bean B):
       @Cacheable(key = trustedTenant + ':' + documentId)
       query scoped tenant/id on miss
  -> optional owner/ACL/classification check
  -> return authorized response
~~~

Lợi ích:
- Mọi lời gọi tới `DocumentService` kiểm tra security trước khi gọi cached reader.
- `CachedDocumentReader` chỉ cache **raw document scoped tenant**, không chứa quyết định phân quyền per-user.
- Trên cache hit, body của reader có thể không chạy, nhưng outer `DocumentService` vẫn chạy và bảo vệ tenant/authority.
- Nếu có object-specific ACL, check trong outer service **sau khi lấy object** hoặc trong policy gắn với resource, không cache kết quả owner-specific như public data.
- Đặt các method ở **hai Spring beans khác nhau** để proxy caching được gọi thật; self-invocation `this.load(...)` có thể bypass caching/authorization tùy cấu hình.

**Không gọi trực tiếp cached reader từ controller hoặc job mà bỏ qua security boundary.** Hạn chế exposure của cached reader, tổ chức module/package rõ, audit các call sites. Dù cached reader dùng tenant scoped key, caller không có quyền không được tự gọi nó với tenant khác.

### 5.3. Cấm ngầm tin cache key thay authz

Khóa `tenant=beta:id=7` chỉ ngăn collision. Nó **không** chứng minh caller hiện tại thuộc beta. Một attacker là Alice có thể đoán tenant beta và ID 7, nên nếu endpoint gọi cache trực tiếp mà không check membership, dữ liệu vẫn có thể bị trả ra. Phải có hai rào chắn độc lập: **kiểm quyền trước dữ liệu** và **cache partition đúng tenant**.

## 6. Ví dụ Spring Boot hoàn chỉnh: hai tenant cùng document ID

Ứng dụng dưới đây minh họa:
- Cùng `id=7`, alpha có `ALPHA:Budget` và beta có `BETA:Budget`.
- Alice có global `document:read`/`document:write` nhưng tenant alpha được READ/WRITE, beta chỉ READ.
- Bob được READ trong beta và không thuộc alpha.
- Viewer không có feature read.
- Service xác minh tenant-specific permission **trước** khi gọi cache reader.
- Spring Cache dùng key `tenant:id` và eviction cho đúng tenant khi update.
- In-memory store có key dạng record `DocKey(tenant,id)`; không có JPA/DB thật trong demo.

Lưu vào `src/main/java/demo/cache/TenantCacheApplication.java` trong một Spring Boot 3.x project Java 17+:

~~~java
package demo.cache;

import java.util.Map;
import java.util.Optional;
import java.util.Set;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.ConcurrentMap;
import java.util.concurrent.atomic.AtomicInteger;

import jakarta.validation.Valid;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Size;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.cache.CacheManager;
import org.springframework.cache.annotation.CacheEvict;
import org.springframework.cache.annotation.Cacheable;
import org.springframework.cache.annotation.EnableCaching;
import org.springframework.cache.concurrent.ConcurrentMapCacheManager;
import org.springframework.context.annotation.Bean;
import org.springframework.http.HttpStatus;
import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.security.authentication.AnonymousAuthenticationToken;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.stereotype.Component;
import org.springframework.stereotype.Service;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PatchMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ResponseStatusException;

@SpringBootApplication
@EnableCaching
@EnableMethodSecurity
public class TenantCacheApplication {
    public static void main(String[] args) {
        SpringApplication.run(TenantCacheApplication.class, args);
    }

    @Bean
    CacheManager cacheManager() {
        // Demo local. Production Redis/Caffeine cần TTL/size/serializer rõ.
        return new ConcurrentMapCacheManager("tenantDocument");
    }

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {
        return http
                .authorizeHttpRequests(auth -> auth
                        .requestMatchers("/api/tenants/**")
                            .authenticated()
                        .anyRequest().denyAll())
                .httpBasic(Customizer.withDefaults())
                .build();
        // Không disable CSRF bừa bãi. PATCH trong test dùng csrf().
    }

    @Bean
    UserDetailsService users() {
        return new InMemoryUserDetailsManager(
                User.withUsername("alice")
                    .password("{noop}demo")
                    .authorities("document:read", "document:write")
                    .build(),
                User.withUsername("bob")
                    .password("{noop}demo")
                    .authorities("document:read")
                    .build(),
                User.withUsername("viewer")
                    .password("{noop}demo")
                    .authorities("profile:read")
                    .build());
    }
}

// DTO chỉ dùng cho demo; không chứa secrets/ACL riêng per-user.
record Document(long id, String tenantId, String title) {}
record DocKey(String tenant, long id) {}
record RenameRequest(@NotBlank @Size(max = 180) String title) {}

@Component
class TenantMemberships {
    private final Map<String, Map<String, Set<String>>> rights = Map.of(
            "alice", Map.of(
                    "alpha", Set.of("read", "write"),
                    "beta", Set.of("read")),
            "bob", Map.of(
                    "beta", Set.of("read")),
            "viewer", Map.of(
                    "alpha", Set.of("read")));

    void requireAction(Authentication auth, String tenant, String action) {
        if (auth == null || !auth.isAuthenticated()
                || auth instanceof AnonymousAuthenticationToken
                || tenant == null
                || !tenant.matches("[a-z][a-z0-9-]{0,31}")
                || !rights.getOrDefault(auth.getName(), Map.of())
                    .getOrDefault(tenant, Set.of()).contains(action)) {
            throw new AccessDeniedException("Tenant/action denied");
        }
    }
}

@Component
class DocumentStore {
    private final ConcurrentMap<DocKey, Document> records =
            new ConcurrentHashMap<>(Map.of(
                new DocKey("alpha", 7L),
                    new Document(7L, "alpha", "ALPHA:Budget"),
                new DocKey("beta", 7L),
                    new Document(7L, "beta", "BETA:Budget"),
                new DocKey("alpha", 8L),
                    new Document(8L, "alpha", "ALPHA:Plan")));

    private final ConcurrentMap<DocKey, AtomicInteger> reads =
            new ConcurrentHashMap<>();

    Document findRequired(String trustedTenant, Long id) {
        DocKey key = new DocKey(trustedTenant, id);
        reads.computeIfAbsent(key, ignored -> new AtomicInteger())
             .incrementAndGet();
        Document found = records.get(key);
        if (found == null) {
            throw new ResponseStatusException(HttpStatus.NOT_FOUND);
        }
        return found;
    }

    Document rename(String trustedTenant, Long id, String newTitle) {
        DocKey key = new DocKey(trustedTenant, id);
        Document updated = records.computeIfPresent(key,
                (ignored, oldValue) -> new Document(
                        oldValue.id(), oldValue.tenantId(), newTitle));
        if (updated == null) {
            throw new ResponseStatusException(HttpStatus.NOT_FOUND);
        }
        return updated;
    }

    int storeReads(String tenant, long id) {
        AtomicInteger n = reads.get(new DocKey(tenant, id));
        return n == null ? 0 : n.get();
    }
}

// Bean B: CHỈ cache dữ liệu theo tenant đã xác minh.
// Không đặt kiểm tra quyền trong body có thể bị bỏ qua khi cache hit.
@Component
class CachedDocumentReader {
    private final DocumentStore store;

    CachedDocumentReader(DocumentStore store) {
        this.store = store;
    }

    @Cacheable(cacheNames = "tenantDocument",
               key = "#p0 + ':' + #p1")
    public Document load(String trustedTenant, Long id) {
        return store.findRequired(trustedTenant, id);
    }
}

// Bean C: update scoped, evict đúng entry sau khi method thành công.
// Đây là in-memory demo, không có DB transaction hay outbox.
@Component
class DocumentWriter {
    private final DocumentStore store;

    DocumentWriter(DocumentStore store) {
        this.store = store;
    }

    @CacheEvict(cacheNames = "tenantDocument",
                key = "#p0 + ':' + #p1")
    public Document rename(String trustedTenant, Long id, String title) {
        return store.rename(trustedTenant, id, title);
    }
}

// Bean A: Security boundary được gọi từ HTTP/job/integration tests.
@Service
class DocumentService {
    private final TenantMemberships memberships;
    private final CachedDocumentReader reader;
    private final DocumentWriter writer;

    DocumentService(TenantMemberships memberships,
                    CachedDocumentReader reader,
                    DocumentWriter writer) {
        this.memberships = memberships;
        this.reader = reader;
        this.writer = writer;
    }

    private Authentication actor() {
        return SecurityContextHolder.getContext().getAuthentication();
    }

    @PreAuthorize("hasAuthority('document:read')")
    public Document read(String tenant, Long id) {
        memberships.requireAction(actor(), tenant, "read");
        // Bản ghi được lấy theo tenant ngay cả khi cache miss.
        Document doc = reader.load(tenant, id);
        // Khi cần owner/ACL: kiểm tra thêm ở đây, trên MỌI cache hit.
        return doc;
    }

    @PreAuthorize("hasAuthority('document:write')")
    public Document rename(String tenant, Long id, RenameRequest request) {
        memberships.requireAction(actor(), tenant, "write");
        return writer.rename(tenant, id, request.title());
    }
}

@RestController
@RequestMapping("/api/tenants/{tenantId}/documents")
class DocumentController {
    private final DocumentService service;

    DocumentController(DocumentService service) {
        this.service = service;
    }

    @GetMapping("/{id}")
    Document read(@PathVariable("tenantId") String tenant,
                  @PathVariable("id") Long id) {
        return service.read(tenant, id);
    }

    @PatchMapping("/{id}")
    Document rename(@PathVariable("tenantId") String tenant,
                    @PathVariable("id") Long id,
                    @Valid @RequestBody RenameRequest request) {
        return service.rename(tenant, id, request);
    }
}
~~~

### 6.1. Dependencies

Trong Spring Boot 3.x project đã cấu hình plugin/dependency management và Java 17+, thêm:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.boot:spring-boot-starter-validation'
    implementation 'org.springframework.boot:spring-boot-starter-cache'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}
~~~

Đây chỉ là phần `dependencies`, không phải `build.gradle` hoàn chỉnh. Mẫu dùng `ConcurrentMapCacheManager` nên không cần Redis server. Password `{noop}` chỉ cho học tập; production cần password encoder an toàn. Nếu dự án có Spring Boot 4.x, kiểm tra starter cache/security/test tương ứng trước khi copy.

### 6.2. Trường hợp thực tế

| Principal | Tenant chọn | Global authority | Tenant action | Document ID 7 | Kết quả |
| --- | --- | --- | --- | --- | --- |
| Alice | alpha | read | read | alpha ID 7 | 200, `ALPHA:Budget` |
| Alice | beta | read | read | beta ID 7 | 200, `BETA:Budget` |
| Bob | beta | read | read | beta ID 7 | 200, `BETA:Budget` |
| Bob | alpha | read | không có membership | alpha ID 7 | 403 |
| Viewer | alpha | không có `document:read` | read | alpha ID 7 | 403 |
| Alice | beta | write | beta chỉ read | beta ID 7 | PATCH 403 |
| Alice | alpha | write | alpha write | alpha ID 7 | PATCH 200, đúng một entry bị evict |
| Anonymous | alpha | chưa xác thực | chưa có | alpha ID 7 | Thường 401 với HTTP Basic |

**Lưu ý:** Demo chỉ có action membership, chưa kiểm owner/ACL trên từng document. Với ứng dụng thật, `read()`/`rename()` phải gọi thêm object authorization theo dữ liệu đáng tin, và không cache quyết định per-user như raw document chung.

### 6.3. Giá trị cache nằm đâu trong đường gọi?

~~~text
GET /api/tenants/beta/documents/7
  -> HTTP authentication (Bob)
  -> DocumentService.read("beta",7)
       @PreAuthorize read global
       TenantMemberships.requireAction(Bob,beta,read)
       -> CachedDocumentReader.load("beta",7)
            key="beta:7"
            HIT? return cached beta Document
            MISS? DocumentStore finds (beta,7)
       -> optional object ACL check
       -> response BETA:Budget
~~~

Với một request Bob→alpha, `requireAction` dừng trước `CachedDocumentReader`, kể cả cache đang có `alpha:7` do Alice đã warm. **Có entry trong cache không phải vé truy cập**.

## 7. Integration tests: cùng ID nhưng khác tenant, eviction và revoke

Tạo `src/test/java/demo/cache/TenantCacheApplicationTest.java`:

~~~java
package demo.cache;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.annotation.DirtiesContext;
import org.springframework.test.web.servlet.MockMvc;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.springframework.security.test.web.servlet.request
        .SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.security.test.web.servlet.request
        .SecurityMockMvcRequestPostProcessors.httpBasic;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders
        .get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders
        .patch;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers
        .jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers
        .status;

@SpringBootTest
@AutoConfigureMockMvc
@DirtiesContext(classMode = DirtiesContext.ClassMode.AFTER_EACH_TEST_METHOD)
class TenantCacheApplicationTest {
    @Autowired MockMvc mvc;
    @Autowired DocumentStore store;

    @Test
    void sameIdInTwoTenantsNeverSharesValue() throws Exception {
        mvc.perform(get("/api/tenants/alpha/documents/7")
                    .with(httpBasic("alice", "demo")))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.title").value("ALPHA:Budget"));

        mvc.perform(get("/api/tenants/beta/documents/7")
                    .with(httpBasic("alice", "demo")))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.title").value("BETA:Budget"));

        // Lần thứ hai phải hit đúng key, không gọi store thêm.
        mvc.perform(get("/api/tenants/alpha/documents/7")
                    .with(httpBasic("alice", "demo")))
                .andExpect(jsonPath("$.title").value("ALPHA:Budget"));

        assertEquals(1, store.storeReads("alpha", 7L));
        assertEquals(1, store.storeReads("beta", 7L));
    }

    @Test
    void unauthorizedUserCannotReadHotCacheEntry() throws Exception {
        // Alice làm nóng cache của alpha.
        mvc.perform(get("/api/tenants/alpha/documents/7")
                    .with(httpBasic("alice", "demo")))
                .andExpect(status().isOk());

        // Bob có quyền read global nhưng KHÔNG thuộc alpha.
        mvc.perform(get("/api/tenants/alpha/documents/7")
                    .with(httpBasic("bob", "demo")))
                .andExpect(status().isForbidden());

        assertEquals(1, store.storeReads("alpha", 7L));
    }

    @Test
    void updateEvictsOnlyMatchingTenantAndId() throws Exception {
        mvc.perform(get("/api/tenants/alpha/documents/7")
                    .with(httpBasic("alice", "demo")))
                .andExpect(status().isOk());
        mvc.perform(get("/api/tenants/beta/documents/7")
                    .with(httpBasic("alice", "demo")))
                .andExpect(status().isOk());

        mvc.perform(patch("/api/tenants/alpha/documents/7")
                    .with(httpBasic("alice", "demo"))
                    .with(csrf())
                    .contentType(MediaType.APPLICATION_JSON)
                    .content("{\"title\":\"ALPHA:Revised\"}"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.title").value("ALPHA:Revised"));

        mvc.perform(get("/api/tenants/alpha/documents/7")
                    .with(httpBasic("alice", "demo")))
                .andExpect(jsonPath("$.title").value("ALPHA:Revised"));

        mvc.perform(get("/api/tenants/beta/documents/7")
                    .with(httpBasic("alice", "demo")))
                .andExpect(jsonPath("$.title").value("BETA:Budget"));

        assertEquals(2, store.storeReads("alpha", 7L));
        assertEquals(1, store.storeReads("beta", 7L));
    }

    @Test
    void readPermissionIsTenantScopedEvenWhenGlobalWriteExists()
            throws Exception {
        // Alice có global document:write nhưng beta chỉ cho READ.
        mvc.perform(patch("/api/tenants/beta/documents/7")
                    .with(httpBasic("alice", "demo"))
                    .with(csrf())
                    .contentType(MediaType.APPLICATION_JSON)
                    .content("{\"title\":\"Forbidden\"}"))
                .andExpect(status().isForbidden());

        mvc.perform(get("/api/tenants/beta/documents/7")
                    .with(httpBasic("alice", "demo")))
                .andExpect(jsonPath("$.title").value("BETA:Budget"));
    }

    @Test
    void missingGlobalReadAuthorityIsDenied() throws Exception {
        mvc.perform(get("/api/tenants/alpha/documents/7")
                    .with(httpBasic("viewer", "demo")))
                .andExpect(status().isForbidden());
    }

    @Test
    void anonymousCannotUseCachedData() throws Exception {
        mvc.perform(get("/api/tenants/alpha/documents/7"))
                .andExpect(status().isUnauthorized());
    }
}
~~~

**Diễn giải:** `@DirtiesContext` tạo lại application context sau mỗi test trong mẫu để tránh dữ liệu/cache thay đổi từ test khác; đối với test suite lớn, có thể thay bằng fixture reset an toàn hoặc cache cleanup cụ thể. Assertions về `storeReads` chứng minh lần thứ hai dùng đúng tenant key và eviction đúng phân vùng. Test Bob truy alpha sau khi Alice warm cache là regression test cực kỳ quan trọng: nếu chỉ thử **cache miss**, có thể không phát hiện bypass khi có cache hit.

### 7.1. Các test cần bổ sung ngoài demo

- User alpha và beta cùng ID nhưng dữ liệu có phiên bản, locale, redaction khác nhau.
- User có global feature read nhưng tenant membership bị thu hồi **sau khi cache đã được warm**.
- Một user là ADMIN của alpha nhưng VIEWER của beta; `WRITE beta` luôn deny.
- API search, pagination, counts, recommendation và file download dùng cache key có tenant và đủ query dimensions.
- Concurrent update và read: cache invalidation gần transaction commit, không tái đưa stale entry sau revoke.
- Nhiều app instances dùng Redis, cùng namespace, serializer key version, pub/sub invalidation.
- Request tenant ID không hợp lệ hoặc chứa delimiter/Unicode gây collision: không được chia entry.
- Scope async/messaging/batch không giữ tenant context của task trước.
- Đổi owner/ACL/feature flags hoặc tenant status: hiệu lực revocation phù hợp SLA.
- Migration sang cache backend mới: không thể đọc legacy key thiếu tenant.

## 8. Key cho authorization decision phải chặt hơn key dữ liệu

Câu hỏi `canRead(Bob, Document 7)` trả `true` hôm nay **không** thể dùng lại cho Alice hoặc tenant khác. Nếu ứng dụng thật sự cần cache decision, hãy mô hình key:

~~~text
decision:v4:
  tenant=beta
  actor=user-52
  resourceType=Document
  resourceId=7
  action=READ
  policyVersion=2026-11
  aclRevision=119
  membershipRevision=57
  resourceStateVersion=4
~~~

Đây là **schema ý tưởng**, không phải format Redis bắt buộc. Ngoài tenant, phải có:
- Principal ID ổn định, không chỉ username display.
- Action/permission chính xác (READ, WRITE, DELETE khác nhau).
- Resource type + ID; Document 7 khác Invoice 7.
- Policy/ACL/role membership revisions có thể kiểm chứng, hoặc invalidation đáng tin; không tự giả lập version không tồn tại.
- Các biến policy khác thật sự ảnh hưởng kết quả, ví dụ tenant ACTIVE/SUSPENDED, owner, classification, time, delegation expiry, client context nếu được dùng.

**Cách đơn giản thường an toàn hơn:** không cache **ALLOW** decision đối với tài nguyên nhạy cảm hoặc quyền hay thay đổi. Cache raw/resource data theo tenant, nhưng **authorization được kiểm lại tại mỗi request** bằng các nguồn hiện hành. Nếu có cache decision, thiết kế revocation guarantee, TTL rất ngắn theo threat model, invalidation trên các thay đổi liên quan và fail closed khi version không xác minh được.

### 8.1. Tại sao TTL 5 phút không phải lời giải đủ?

Nếu Alice rời tenant beta ngay sau khi cached `allowed=true`, TTL 5 phút có thể cho cô ấy tiếp tục truy cập trong phần còn lại của window. Với dữ liệu nội bộ nhạy cảm, chấp nhận window đó phải là quyết định risk/legal/product được ghi rõ; không tự xem “5 phút là ngắn” rồi bỏ qua revoke.

Đặc biệt:
- Revocation của membership có thể cần invalidate **hàng nghìn decision keys** liên quan actor/tenant.
- ACL parent sửa có thể ảnh hưởng descendants và nhiều principals; chỉ evict một object ID không đủ.
- Role hierarchy/permission mapping thay đổi cũng làm decision cache stale.
- Nếu token chứa role claim cũ, cache disable không tự xử lý freshness; thiết kế token lifetime/revocation song song.

### 8.2. Cache DENY cũng có hệ quả

Cache `false` lâu có thể làm user vừa được cấp quyền vẫn bị từ chối. Đây thường là lỗi khả dụng hơn là leak, nhưng có thể phá luồng nghiệp vụ, gây support escalation. Không phân biệt cache GRANT và DENY rồi áp TTL giống nhau nếu SLA grant/revoke khác nhau. Kết quả `UNKNOWN`, exception policy service, “không load được ACL” **không được** cache như GRANT.

### 8.3. Cache principal roles là một loại decision cache

Nếu lưu `Set<GrantedAuthority>` của Alice mà không có tenant, rồi dùng nó cho cả alpha/beta, role alpha có thể mở quyền beta. Cache membership/roles theo `{tenant,principal,scope,version}` với invalidation hoặc freshness check. Nếu provider trả danh sách memberships toàn cục, caller vẫn phải chọn tenant và action đúng — cache toàn bộ list không tự là authorized tenant context.

## 9. Danh sách, tìm kiếm và phân trang: key không chỉ tenant:id

Cache một query:

~~~java
@Cacheable(cacheNames = "tenantSearch",
           key = "#p0 + ':' + #p1")
List<Document> search(String tenant, String query) { ... }
~~~

có thể thiếu `page`, `size`, `sort`, `status`, `projection`, `locale`, `author` hoặc `permissionView` nếu chúng ảnh hưởng output. Một key tốt phải canonical hóa query:

~~~text
tenantSearch:v3:
  tenant=alpha
  filter={status:ACTIVE,tag:budget}
  sort=createdAt:desc,id:asc
  page=2
  size=20
  view=viewer
  locale=vi-VN
~~~

Ví dụ này chỉ mô tả **các trường**, không phải code sinh chuỗi production. Với JSON/dictionary, chuẩn hóa thứ tự field và kiểu dữ liệu; không dựa vào `Map.toString()` khi output khác thứ tự tùy runtime. Nếu kết quả đã được ACL-filter **theo user**, bổ sung principal/action/permission versions hoặc không cache ở tầng cross-user.

### 9.1. Không lấy top N toàn tenant rồi filter mỗi user sau mà tưởng an toàn

Nếu cache chứa danh sách cả tenant với nội dung nhạy cảm, có thể dùng lại cho user chỉ có quyền xem một phần. Có thể:
1. Cache metadata đã scoping tenant nhưng **chưa chứa dữ liệu cấm**, và thực hiện object-level filtering mỗi request; hoặc
2. Query/paginate đã áp ACL trong DB/search engine, cache kết quả user-scoped với invalidation đầy đủ; hoặc
3. Không cache khi chi phí bảo mật/độ phức tạp vượt lợi ích.

Tính đúng pagination và tổng số bản ghi cũng là yêu cầu: cache list trước rồi lọc sau có thể làm sai count và vô tình tiết lộ sự tồn tại documents qua thời gian xử lý, highlights hoặc metadata.

### 9.2. Negative caching

Một record không tìm thấy trong tenant alpha có thể **có tồn tại trong beta**. Không cache `NOT_FOUND(id=7)` toàn cục. Nếu negative caching được dùng, key vẫn phải chứa tenant và đủ scope; TTL ngắn, không dùng lỗi hạ tầng làm “not found” vĩnh viễn.

### 9.3. Feature flag và response personalization

Nếu response phụ thuộc plan, entitlement, feature flag, field-level redaction, locale hoặc AB test, key phải thể hiện những khác biệt **được phép dùng chung**. Nếu không, response full cho admin có thể bị tái sử dụng cho viewer cùng tenant. Cache raw data rồi redaction **sau** cache có thể giảm số chiều key, nhưng raw data ở Redis phải được bảo vệ tốt và mọi consumer phải enforce redaction.

## 10. Invalidation: đúng tenant, đúng ID, đúng thời điểm

Key tenant đúng giải quyết **cross-tenant collision**, chưa đảm bảo freshness sau update/revoke.

### 10.1. Sửa Document phải evict đúng một partition

~~~java
@CacheEvict(
    cacheNames = "tenantDocument",
    key = "#p0 + ':' + #p1")
public void rename(String trustedTenant, Long id, String title) {
    repository.renameWhereTenantMatches(
            trustedTenant, id, title);
}
~~~

Đây là trích đoạn chưa có transaction/row-count/error handling. Với shared DB, phải dùng `WHERE tenant_id = :trustedTenant AND id = :id`; nếu 0 rows, xử lý NOT_FOUND/conflict, không coi thành công rồi evict chung key của tenant khác.

**Không làm:**

~~~java
@CacheEvict(cacheNames = "tenantDocument", key = "#p1")
public void rename(String tenant, Long id, String title) { ... }
~~~

Nếu cache đang dùng `tenant:id` thì evict bằng `id` sẽ không trúng entry cũ; dữ liệu stale tiếp tục tồn tại. Cũng tránh `allEntries=true` trên mọi update nếu không cần: vừa gây stampede, vừa dễ gây lỗi availability và mất isolation ở những cache khác khi namespace chung.

### 10.2. Eviction và transaction commit

Với DB transaction:
- `@CacheEvict` thường chạy theo thời điểm của cache advice, không tự cam kết “chỉ xóa khi DB đã commit” với mọi cấu hình.
- Evict **trước commit** có thể cho request khác đọc dữ liệu cũ rồi **tái điền cache** ngay trước khi transaction commit.
- Evict **sau commit** giảm một số race, nhưng publisher có thể thất bại hoặc cache replica chưa nhận invalidation.
- Dùng `TransactionAwareCacheManagerProxy` hoặc transaction-aware cache decorator khi phù hợp và kiểm tra chính xác semantics; với phân tán/rủi ro cao có thể dùng outbox + versioned keys.
- Nếu update gồm nhiều objects, đảm bảo nhóm events/evictions đúng tenant/type/id và policyVersion.

Một timeline race:

~~~text
t1: transaction update alpha:7 -> ALPHA:Revised (chưa commit)
t2: evict cache alpha:7 sớm
t3: concurrent reader query DB thấy ALPHA:Old (snapshot cũ)
t4: reader cache ALPHA:Old
t5: transaction commit ALPHA:Revised
t6: cache hit ALPHA:Old dù DB đã commit
~~~

Tùy consistency SLA, giải pháp gồm after-commit invalidation, version/tag trong cache key, optimistic lock version và coalescing update events. Không dùng TTL như thay thế duy nhất cho một revocation cần tức thì.

### 10.3. Thu hồi tenant membership khác sửa document

Khi user bị xóa khỏi tenant, **không nhất thiết phải evict raw document cache** nếu mọi caller vẫn đi qua membership check bên ngoài. Dữ liệu cache của tenant đó vẫn dùng được cho các user hợp lệ, còn user bị thu hồi bị chặn trước hit. Tuy nhiên:
- Mọi decision cache/role cache của user đó phải bị invalidate hoặc revalidate.
- Pre-signed URLs, active sessions, long-running jobs có thể cần revoke riêng.
- Nếu cache lưu **personalized response** đã dành cho user, phải evict entry user/tenant tương ứng.
- Nếu ngữ cảnh/cache có kiểm quyền chỉ ở miss, phải sửa cấu trúc — không chỉ evict một lần.

### 10.4. Tenant offboarding và migration

Khi tenant bị disable/delete:
- Ngăn mọi request/job mới ở authorization boundary.
- Invalidate hoặc xóa namespace cache tenant theo retention/security policy; không dùng data cache như nguồn duy nhất của lifecycle state.
- Xử lý dữ liệu ở object storage, CDN, vector/search indexes, analytics và browser/client caches, không chỉ Redis.
- Khi tenant ID được tái sử dụng (nên tránh), cache cũ có thể bị “hồi sinh” vào tenant mới. Dùng stable never-reused tenant identity và namespace version.

## 11. Redis / distributed cache: key schema là một hợp đồng

Ở local `ConcurrentMapCacheManager`, key `SimpleKey` là Java object có `equals/hashCode`. Với Redis, key được serialize thành bytes; khi nhiều app instances, nhiều versions hoặc ngôn ngữ cùng đọc, **key format phải ổn định, không va chạm và có migration strategy**.

### 11.1. Tên cache và key prefix

Spring Data Redis cache thường prefix keys theo tên cache (ví dụ dạng khái niệm `cacheName::logicalKey`, phụ thuộc configuration). Tên cache phải phân biệt:
- Env/deployment: production khác staging nếu vô tình dùng chung Redis.
- Service/resource type: `docByTenant` khác `invoiceByTenant`.
- Schema/key version: `v3` khi đổi serialization/fields.
- Tenant identifier tin cậy, canonical.
- Resource/query ID.

Ví dụ:

~~~text
prod:document:v3::alpha|7
prod:document:v3::beta|7
prod:perm:v2::alpha|alice|Document|7|READ|aclRev=20
~~~

Đây là convention tham khảo, không khẳng định Redis Cache Manager tự sinh chính xác chuỗi này. Nếu dùng delimiter, validate/escape/length-prefix thành phần. Tránh nhét secrets (JWT, access token, email nhạy cảm) nguyên văn vào key vì Redis keys có thể xuất hiện trong monitoring, logs và metrics.

### 11.2. Cache key có tenant không đồng nghĩa Redis IAM đã cách ly tenant

Một Redis instance dùng chung có thể cho service account quyền đọc mọi namespace. Nếu threat model đòi cô lập tenant mạnh, cân nhắc Redis ACL/user-per-service, namespaces/databases/instances riêng, encryption at rest/in transit, network segmentation và hạn chế lệnh `KEYS`/`SCAN` với operator không có quyền. Key tenant giúp tránh **lỗi ứng dụng trộn giá trị**, không cung cấp ranh giới cryptographic hoặc storage-level isolation tự động.

### 11.3. Serialization và object type

Không tin một JSON cached object chỉ vì key đúng tenant. Có thể có:
- Stale schema: thêm/xóa trường nhưng old data được deserialize sai.
- Poisoned value từ service khác có quyền ghi Redis.
- Custom serializer có rủi ro deserialization/gadget nếu nhận dữ liệu không tin cậy.
- Key collisions khi nhiều teams chia cache name/ID nhưng lưu value type khác.

Dùng typed serializers an toàn, versioned payload, hạn chế polymorphic deserialization không kiểm soát, kiểm tra owner/resource tenant khi cần và tách namespace theo domain.

### 11.4. TTL, eviction và stampede

TTL cần bám business và threat model. Cache vài phút cho metadata ít nhạy cảm có thể chấp nhận; cache `allowed=true` vài phút sau revocation có thể không. Phải tách:
- Data TTL.
- Membership/role freshness.
- ACL decision TTL.
- Negative-cache TTL.
- Tenant suspension/revocation freshness.

Với nhiều app nodes, eviction có thể xảy ra đồng thời; request storm sau invalidate cần backpressure/load control, có thể dùng cache `sync=true` hoặc local single-flight nếu backend hỗ trợ, và kiểm thử. Không biến cache unavailable thành “allow all”; nếu cache fail, quay về trusted DB/policy theo contract, hoặc fail closed với tác vụ nhạy cảm.

## 12. @Async, thread reuse và cache context

Một thiết kế dùng:

~~~java
@Cacheable(cacheNames = "document", key = "#p0")
public Document load(Long id) {
    String tenant = TenantContextHolder.get();
    return repository.findByTenantIdAndId(tenant,id).orElseThrow();
}
~~~

có ba vấn đề:
1. Tenant không ở method args, nên default key không thể phân biệt.
2. Method body có thể bị bỏ qua khi hit, nên `TenantContextHolder.get()` không chắc được gọi.
3. `ThreadLocal` của servlet/async executor có thể bị bỏ sót/giữ lại qua worker reuse.

**Tốt hơn:** truyền một `trustedTenantId` explicit vào service và cached method, tạo key từ argument; chỉ tạo trustedTenantId sau membership/action check. Đối với `@Async`, capture context theo task, thiết lập trong worker và cleanup trong `finally`; không serialize toàn bộ `SecurityContext` vào queue rồi coi là quyền còn hiệu lực vĩnh viễn.

### 12.1. Nested calls và self-invocation

`@Cacheable` và `@PreAuthorize` dựa vào Spring proxy ở cấu hình thông thường. `this.cachedRead(...)` từ cùng bean có thể bỏ qua cache advice; `this.securedRead(...)` có thể bỏ qua security advice. Việc tách bean cho security boundary và cache data loader giúp test rõ hơn, nhưng cũng cần **không expose loader như API không bảo vệ**.

### 12.2. WebFlux/Reactor khác ThreadLocal Servlet

Trong Reactive WebFlux, security context dùng Reactor `Context` thay vì dựa hoàn toàn vào `ThreadLocal`. Khi dùng `Mono.cache()` hoặc `Flux.cache()` chia sẻ publisher, phải phân biệt dữ liệu thuộc tenant/user nào và scope của mỗi subscription; không share một cached reactive stream đã personalize cho Alice sang Bob. Thiết kế context-aware reactive caching riêng thay vì sao chép nguyên mẫu `SecurityContextHolder` của Servlet vào reactive pipeline.

## 13. Java 17 độc lập: quan sát collision và sửa key

Chương trình này **biên dịch/chạy chỉ với JDK 17**, không dùng Spring. Nó cố tình mô phỏng một “cache sai” dùng riêng ID và một “cache đúng” dùng composite key dạng record `(tenant,resourceType,id)`. Dữ liệu nguồn có cùng ID 7 ở alpha và beta.

Lưu thành `TenantCacheKeyDemo.java`:

~~~java
import java.util.HashMap;
import java.util.Map;

public class TenantCacheKeyDemo {
    record CacheKey(String tenant, String kind, long id) {}

    static final Map<CacheKey, String> DATABASE = new HashMap<>(Map.of(
            new CacheKey("alpha", "Document", 7L), "ALPHA-7",
            new CacheKey("beta", "Document", 7L), "BETA-7"));

    static final Map<Long, String> BAD_CACHE = new HashMap<>();
    static final Map<CacheKey, String> GOOD_CACHE = new HashMap<>();

    static String unsafeRead(String tenant, long id) {
        return BAD_CACHE.computeIfAbsent(id, ignored ->
                DATABASE.get(new CacheKey(tenant, "Document", id)));
    }

    static String scopedRead(String tenant, long id) {
        CacheKey key = new CacheKey(tenant, "Document", id);
        return GOOD_CACHE.computeIfAbsent(key, DATABASE::get);
    }

    public static void main(String[] args) {
        System.out.println("unsafe-alpha=" + unsafeRead("alpha", 7));
        System.out.println("unsafe-beta=" + unsafeRead("beta", 7));

        System.out.println("safe-alpha=" + scopedRead("alpha", 7));
        System.out.println("safe-beta=" + scopedRead("beta", 7));

        CacheKey alphaKey = new CacheKey("alpha", "Document", 7L);
        DATABASE.put(alphaKey, "ALPHA-7-V2");
        GOOD_CACHE.remove(alphaKey);

        System.out.println("after-update-alpha=" + scopedRead("alpha", 7));
        System.out.println("beta-still=" + scopedRead("beta", 7));
        System.out.println("good-entries=" + GOOD_CACHE.size());
    }
}
~~~

Chạy:

~~~bash
javac --release 17 TenantCacheKeyDemo.java
java TenantCacheKeyDemo
~~~

**stdout chính xác:**

~~~text
unsafe-alpha=ALPHA-7
unsafe-beta=ALPHA-7
safe-alpha=ALPHA-7
safe-beta=BETA-7
after-update-alpha=ALPHA-7-V2
beta-still=BETA-7
good-entries=2
~~~

Giải thích:
- `BAD_CACHE` chỉ có key Long `7`, nên khi alpha warm trước, beta bị trả nội dung alpha.
- `GOOD_CACHE` dùng record `CacheKey(tenant,kind,id)`, Java tự sinh `equals/hashCode` dựa trên các thành phần, nên hai tenant khác nhau không collision.
- Sau khi đổi nguồn dữ liệu alpha và evict đúng key alpha, beta vẫn giữ dữ liệu đúng.
- Demo này chỉ minh họa **partition data**; nó không thực hiện xác thực/membership/ACL. Production phải authorize caller trước khi gọi cache, không cho client điều khiển key rồi đọc tự do.

### 13.1. Vì sao key record có lợi?

Một record immutable như `CacheKey` tránh quên một trường trong `equals/hashCode`, giảm collision so với nối chuỗi thiếu escape. Dù vậy:
- Nếu serialize key sang Redis, cần quy định format ổn định giữa versions.
- Nếu `tenant` có thể null, tạo key null dễ gây “global” tenant không chủ đích; validate upstream.
- Nếu quyền phụ thuộc user/action, record chỉ gồm tenant/id **chưa đủ** cho permission decision cache.
- Nếu cùng ID ở Document và Invoice, `kind` ngăn cross-resource collision.
- Không dùng `hashCode()` một mình làm key persistent vì hash collisions và độ ổn định phiên bản.

## 14. Quy trình sửa một cache key thiếu tenant trong hệ thống đang chạy

Không chỉ sửa annotation rồi deploy: **legacy cache entries** vẫn có thể tồn tại và một service cũ còn đọc sai key.

### Bước 1 — Khoanh vùng cache paths

Tìm mọi chỗ:
- `@Cacheable`, `@CachePut`, `@CacheEvict`, `@Caching`, `CacheManager.getCache(...)`, RedisTemplate direct calls.
- Dữ liệu get/list/search/export, permission decision, user role, ACL and tenant lookup.
- CDN/browser/HTTP cache, API gateway cache, GraphQL DataLoader, search index query cache.
- Background jobs, webhook, report generation, object storage presigned URLs.

Không chỉ tìm đúng string `tenantDocument` trong một repository; nhiều nơi đặt cache name khác nhau cho cùng dữ liệu.

### Bước 2 — Phân loại entry

Với từng cache:
1. Entry có thể dùng chung giữa users trong tenant không?
2. Có bị redaction/ACL/personification theo principal không?
3. Có chứa tài nguyên khác tenant nếu key collision không?
4. Có time-sensitive policy (revoke, suspend, plan, expiresAt) không?
5. Source of truth và đường cache invalidation là gì?

### Bước 3 — Định nghĩa key schema mới

Chẳng hạn:

~~~text
legacy: document::7
new:    document:v3::tenant=alpha|type=Document|id=7
        document:v3::tenant=beta|type=Document|id=7
~~~

Validate/encode từng segment, version namespace; nếu cần migration “read old then rewrite new”, **không tái dùng old value không có bằng chứng tenant**, vì nó có thể đã chứa tài nguyên của tenant khác. Tốt hơn cold-start cache mới từ nguồn dữ liệu đã scoping và xóa namespace cũ theo kế hoạch.

### Bước 4 — Sửa cả GET, PUT và EVICT

Đổi key generator của một phương thức read nhưng quên eviction/update sẽ tạo stale entry. Tất cả read, write, delete, retry, prewarm, refresh job phải cùng một contract về key name/fields/encoding.

### Bước 5 — Triển khai theo chiến lược an toàn

- Chặn hoặc hạn chế service version cũ đọc cache dùng key thiếu tenant.
- Deploy namespace v mới và kiểm tra cache hit/miss/error theo tenant.
- Warm bằng per-tenant queries từ trusted DB, không copy entry legacy sang.
- Giám sát cross-tenant anomaly, stale results, role/permission revocation lag.
- Có rollback strategy không khôi phục key schema unsafe.
- Document key schema ownership để team khác không “tối ưu” bỏ tenant lại.

## 15. Kiểm thử ngoài happy path

| Test case | Kỳ vọng |
| --- | --- |
| Alpha Document ID 7; Beta Document ID 7 | Hai keys, hai giá trị khác nhau |
| Warm alpha rồi Bob beta đọc ID 7 | Không trả dữ liệu alpha |
| Bob beta request `/alpha/7` sau warm alpha | 403/404 policy, không cache leak |
| User không có `document:read`, cache đã warm | DENY, không bypass trên hit |
| Alice có READ beta, WRITE alpha | Global write không cho UPDATE beta |
| Revoked tenant membership sau khi warm | DENY ngay/freshness theo SLA, không reuse decision |
| Two principals same tenant, different ACL | Cached raw object có thể chung; personalized output không chung nếu quyền khác |
| ID trùng giữa Document và Invoice | Cache key type phân biệt |
| Query cùng tenant, khác page/sort/filter | Khác key |
| Query with locale/projection khác | Key hoặc output policy đúng |
| NULL/unknown tenant | Fail closed, không dùng default/global tenant |
| Tenant ID chứa delimiter/Unicode không hợp lệ | Reject hoặc canonical encode, không collision |
| PATCH alpha:7 | Evict alpha:7, beta:7 không đổi |
| DB mutation rollback | Không làm cache chứa value chưa commit |
| Concurrent reader và writer | Không tái cache data cũ sau commit quá freshness SLA |
| ACL/role change | Decision cache invalidated/revalidated |
| Negative-cache NotFound alpha:7 | Không làm beta:7 thành NotFound |
| Redis restart/serializer upgrade | Không đọc sai legacy keys/schema |
| Multi-instance cache invalidation | Tất cả nodes theo consistency contract |
| `@Async` thread reused | Không mang tenant của task trước |
| RLS/session tenant setting đổi | Không làm cache key dùng tenant cũ |
| Tenant deleted/suspended | Không trả stale cached data cho actor bị chặn |
| Export/search/CDN/browser cache | Tenant/resource/user scope đúng |
| Audit log | Trusted tenant, principal, action, cache hit/miss; không log token/PII |

### 15.1. Mutation tests giúp kiểm chứng test suite

Cố ý thay:

~~~java
@Cacheable(cacheNames = "tenantDocument", key = "#p1")
~~~

thay cho `key = "#p0 + ':' + #p1"`. Test `sameIdInTwoTenantsNeverSharesValue` phải **đỏ** hoặc trả sai value. Đó là dấu hiệu kiểm thử bắt được cross-tenant cache collision.

Sau đó xóa `memberships.requireAction(...)` khỏi service: test `unauthorizedUserCannotReadHotCacheEntry` phải đỏ. Xóa `@CacheEvict` khỏi writer: test `updateEvictsOnlyMatchingTenantAndId` phải đỏ. Nếu ba thay đổi này không làm test đỏ, suite chưa thực sự bảo vệ boundary.

### 15.2. Không chỉ assert status 200

Một GET trả 200 cho beta không có nghĩa đúng. Cần assert `tenantId`/`title`/owner/allowed fields của **đúng tenant**. Với dữ liệu nhạy cảm, negative test nên kiểm tra response body không chứa chuỗi đặc trưng của tenant khác, cache operations được namespace đúng và DB query có predicate tenant.

## 16. Những lỗi phổ biến cần tránh

### Lỗi 1 — Key chỉ dùng resource ID

`id=7` có thể tồn tại ở nhiều tenant. Dùng `(tenant,type,id)` cho dữ liệu resource, không dùng `id` độc lập.

### Lỗi 2 — Coi tên cache là tenant namespace

`@Cacheable("document")` chỉ đặt tên cache; nếu cache phục vụ toàn ứng dụng mà key thiếu tenant, entry vẫn có thể va nhau. Phải đưa tenant vào key (hoặc có cache riêng per tenant với lifecycle/chính sách rõ, không dynamic cache name không kiểm soát).

### Lỗi 3 — Đọc tenant từ ThreadLocal nhưng method args chỉ có id

Spring default key generator chỉ thấy parameters. Đưa trusted tenant vào signature hoặc custom key generator có contract đáng tin; đừng phụ thuộc tenant context mơ hồ.

### Lỗi 4 — Client tự chọn tenant rồi trở thành “trusted”

Header/path/JWT chưa validate không phải authorization. Tenant phải được xác minh với principal, membership, action và trạng thái tenant ACTIVE trước khi dùng.

### Lỗi 5 — Có tenant trong key nên bỏ membership check

Key chỉ chống collision, không chứng minh caller có quyền. Giữ security boundary luôn chạy trên hit.

### Lỗi 6 — @Cacheable và @PreAuthorize cùng method là chắc chắn an toàn

Thứ tự Spring AOP advisors/config có thể ảnh hưởng. Ưu tiên hai bean tách biệt, security ngoài cache và test cache hit với user không có quyền.

### Lỗi 7 — Cache result theo tenant khi output đã personalize

Admin và viewer cùng tenant có field-level redaction khác nhau. Hoặc cache raw data để redact mỗi request, hoặc thêm principal/view/action/policy version vào key, tránh share response full.

### Lỗi 8 — Cache `allowed=true` theo documentId

User, tenant, action, ACL, role/version/expiry đều có thể đổi. Nếu cần cache decision, có key đầy đủ và invalidation; với tài nguyên nhạy cảm, không cache allow là lựa chọn đáng ưu tiên.

### Lỗi 9 — Evict bằng key khác key dùng để read

Read dùng `alpha:7` nhưng evict dùng `7` hoặc `beta:7`. Cache stale và có thể rò quyền khi ownership đổi. Dùng cùng factory/key contract cho GET, mutation, refresh và job.

### Lỗi 10 — Invalidate trước DB commit rồi cho reader tái warm dữ liệu cũ

Cache có thể chứa dữ liệu cũ sau commit. Dùng after-commit invalidation/versioning theo consistency SLA, test race conditions.

### Lỗi 11 — Tenant role bị revoke nhưng cache ALLOW còn dài

Cache TTL không tự theo revocation. Dùng revision/invalidation hoặc kiểm quyền hiện hành ở outer service; xác định hard/soft revocation SLA rõ.

### Lỗi 12 — Redis key chứa token hoặc PII

Key thường xuất hiện trong scan/log/metric, có thể bị lộ. Dùng stable opaque IDs, namespace rõ và quyền truy cập/cache encryption phù hợp.

### Lỗi 13 — Migration giữ nguyên legacy key thiếu tenant

Dữ liệu cache cũ có thể đã sai. Version namespace, cold-start từ source trusted, không fallback sang old shared key.

### Lỗi 14 — Dùng Spring cache object key mà không kiểm Redis serializer

Key string hóa có thể thay đổi sau nâng version/giữa services. Chọn contract định dạng key và serializer an toàn, test multi-instance.

### Lỗi 15 — Dữ liệu tenant ở cache đúng nhưng repository miss truy vấn toàn DB

Cache miss vẫn có thể leak. Repository luôn có tenant predicate (và ACL scope nếu cần); cache không thay source-of-truth isolation.

### Lỗi 16 — Async job dùng tenant của request trước

Thread pool/context propagation và connection pooling có thể rò tenant. Dùng explicit trusted tenant parameters, cleanup trong finally, kiểm lại policy ở worker khi cần.

### Lỗi 17 — Không kiểm soát cache của list/search/export

Raw query, pagination, sort, projection, user ACL và negative hits đều cần key dimension phù hợp; không chỉ sửa single-document cache.

### Lỗi 18 — Lạm dụng `allEntries=true` cho mọi update

Xóa cache quá rộng, gây thundering herd và phá availability. Có thể dùng khi migration/tenant purge có chủ đích, nhưng thường nên evict theo key hoặc version namespace.

## 17. Checklist triển khai trước production

| Nhóm | Câu hỏi phải trả lời |
| --- | --- |
| Source of truth | Tenant/owner/permission lấy từ đâu, đã verify chưa? |
| Entrypoint | Mọi HTTP/job/queue đều dùng security boundary? |
| Key fields | Đúng tenant, type, ID, query dimensions, view/user/action? |
| Canonicalization | IDs/encoding/escaping/length có tránh collision? |
| Spring caching | `@EnableCaching`, proxy call, `#p0` và default keys đúng? |
| Spring Security | `@EnableMethodSecurity`, test grant/deny trên cache hit? |
| Storage scope | Cache miss query luôn `WHERE tenant_id = ?`? |
| ACL | Object-level policy có chạy trên hit không? |
| Role freshness | Cache membership/decision có revoke SLA/invalidation? |
| Cache write paths | `@CacheEvict`/`@CachePut`/manual Redis dùng cùng key contract? |
| Transactions | Eviction so DB commit có race? Có after-commit/versioning? |
| Multi-instance | Redis serializer/prefix, invalidation/restart theo consistency? |
| Async | Context không leak qua reused worker? |
| Search/export | Pagination/filter/projection/identity scoped? |
| Security ops | No secret in keys/logs, cache IAM/TLS/encryption đúng? |
| Migration | Không reuse legacy cache entry thiếu tenant? |
| Testing | Same ID 2 tenants, warm-cache unauthorized access, update/evict, revoke, concurrency? |
| Monitoring | Cross-tenant anomalies, cache hit/miss, invalidation delay, stale read alerts? |

## 18. Bài tập tự luyện

**Câu 1 — Mặc định đã an toàn chưa?** Method `load(String tenant, Long id)` dùng `@Cacheable("tenantDocument")` không khai báo `key`. Hai tenant alpha/beta cùng ID 7 có bị collision do default key không?

**Đáp án:** Với Spring Framework 6.x mặc định dùng tất cả tham số tạo `SimpleKey(tenant,id)`, nên hai cặp này thường phân biệt. Nhưng vẫn phải validate tenant, check membership trước cache hit và không đổi annotation thành `key="#p1"`. Nếu method chỉ nhận `id` rồi lấy tenant từ ThreadLocal, default key không đủ.

**Câu 2 — Có tenant trong key là xong?** Bob không thuộc alpha nhưng đoán đúng `alpha:7`. Có entry cached. Bob được đọc không?

**Đáp án:** Không. Cache key partition không phải authorization. Outer service phải check Authentication, tenant membership, action và ACL trước khi trả raw data.

**Câu 3 — User đổi role sau khi cache warm?** Alice không còn là admin tenant alpha. Redis có cached `canDelete(alice, Document 7)=true`. Có được dùng tới hết TTL không?

**Đáp án:** Chỉ nếu risk model chủ động cho phép freshness window đó; với dữ liệu nhạy cảm, phải invalidate/re-check ngay theo SLA hoặc không cache privileged ALLOW. Key phải gồm tenant, principal, action, resource và policy/ACL/membership versions nếu dùng revisions thực.

**Câu 4 — Vì sao @CacheEvict không trúng?** Read key là `alpha:7`, method update dùng `@CacheEvict(key="#p1")`. Kết quả?

**Đáp án:** Evict `7` khác key `alpha:7`, nên stale entry còn nguyên. Sửa eviction dùng cùng factory/key expression và test update→read.

**Câu 5 — Tại sao phải test cùng ID ở hai tenant?** Nếu alpha Document 7 và beta Document 8, key chỉ dựa trên ID có thể vẫn cho test xanh. Chuyện gì xảy ra trong production?

**Đáp án:** Khi ID trùng xuyên tenant, cache collision làm dữ liệu bị tráo. Dùng fixture **cùng ID khác tenant** là cách chủ động phơi bày lỗi.

**Câu 6 — Response personalized có được cache theo tenant?** Hai user cùng alpha, Alice thấy salary, Bob bị redact salary. Nếu key chỉ có `alpha:employee-7`, rủi ro?

**Đáp án:** Bob có thể nhận bản full của Alice. Cache raw record theo tenant nếu có kiểm quyền/redaction **sau cache trên mỗi request**, hoặc cache view per principal/permission/revision; tránh lưu dữ liệu nhạy cảm vào cache dùng chung không kiểm soát.

**Câu 7 — Evict sớm trong transaction có nguy hiểm?** Transaction cập nhật DB nhưng chưa commit; cache bị evict, reader khác thấy DB cũ và cache lại; sau commit vẫn trả dữ liệu cũ. Giải pháp?

**Đáp án:** Dùng after-commit invalidation/versioned keys/transaction-aware cache strategy phù hợp; kiểm chứng bằng test race và xác định consistency SLA. Chỉ có TTL không đảm bảo vừa commit là thấy mới.

**Câu 8 — Redis cache name có phải phân quyền?** Redis key `tenant=alpha:id=7`, nhưng app role có quyền GET mọi key. Có nghĩa tenant đã được cách ly ở storage không?

**Đáp án:** Không. Namespacing tránh lỗi logic, nhưng storage-level isolation cần Redis ACL/IAM/network/TLS và thiết kế tách instances phù hợp nếu threat model yêu cầu.

## 19. Tổng kết

**Khóa cache phải phản ánh đúng phạm vi tái sử dụng dữ liệu và quyền**:

~~~text
Authentication + trusted tenant/action membership
              |
              v
      Secure application service
              |
              v
     (tenant, resource type, ID, ...)
              |
              +-- HIT: đúng tenant + vẫn authorize caller
              |
              +-- MISS: repository query scoped tenant
              |
              v
      optional object ACL + safe response
~~~

Cốt lõi:
- Cache chung không tự hiểu tenant; key phải chứa **trusted tenant** và các chiều ảnh hưởng output.
- Spring default key chỉ dựa vào **arguments**; `key` tùy chỉnh có thể làm mất tenant dù signature đầy đủ.
- Dữ liệu tenant-scoped có thể dùng chung trong cùng tenant, nhưng quyền và response personalized cần scope theo **principal/action/policy revisions** hoặc không cache.
- Security boundary phải chạy **trên cả cache hit lẫn miss**. Tách bean để kiểm tra rõ thứ tự proxy/AOP.
- Mọi đường read/update/evict, DB query, Redis key migration và async context phải có tenant nhất quán.
- TTL không thay thế revocation/invalidation đối với quyền nhạy cảm; đo lường freshness và kiểm thử thay đổi giữa các requests.

**Câu hỏi kiểm tra sau cùng:** “Nếu Bob chỉ thuộc tenant beta, nhưng cache alpha đang có Document 7 do Alice vừa warm, Bob có thể nhận byte nào của alpha qua bất kỳ controller, service, Redis API, list/search/export hay background job nào không?” Nếu câu trả lời có thể là có, cache chưa được đặt đúng bên trong ranh giới authorization.

## Tài liệu chính thức

- [Spring Framework – Declarative Annotation-based Caching](https://docs.spring.io/spring-framework/reference/integration/cache/annotations.html): `@Cacheable`, `@CachePut`, `@CacheEvict`, default `SimpleKeyGenerator`, SpEL `#p0`/`#p1`, `KeyGenerator`, `unless`.
- [Spring Framework – Cache Abstraction](https://docs.spring.io/spring-framework/reference/integration/cache.html): CacheManager, proxy behavior, cache providers và concurrency.
- [Spring Framework – Cache Transaction Support](https://docs.spring.io/spring-framework/reference/integration/cache/strategies.html): transaction-aware cache manager, provider behaviors và cache configuration.
- [Spring Security – Method Security](https://docs.spring.io/spring-security/reference/servlet/authorization/method-security.html): `@EnableMethodSecurity`, `@PreAuthorize`, Spring AOP proxy và advisor ordering.
- [Spring Security – Authorize HttpServletRequests](https://docs.spring.io/spring-security/reference/servlet/authorization/authorize-http-requests.html): request-level authorization, authentication và `AuthorizationManager`.
- [Spring Security – Testing with MockMvc](https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/index.html): HTTP security test và post-processors `httpBasic`, `csrf`.
- [Spring Data Redis – Caching](https://docs.spring.io/spring-data/redis/reference/redis/redis-cache.html): `RedisCacheManager`, key prefix, TTL, cache configuration và writers.
