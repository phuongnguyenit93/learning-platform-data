# Đọc dữ liệu quyền bằng API không chặn luồng trong Spring Security WebFlux

## 1. Bài toán: authorization cần đọc database hoặc dịch vụ khác

Trong ứng dụng Spring WebFlux, việc quyết định có cho Alice đọc `Document 42` hay không thường không chỉ phụ thuộc authority sẵn có trong JWT. Ứng dụng có thể phải đọc thêm:

- Membership của Alice trong tenant hiện tại.
- Vai trò READ/EDITOR được cấp cho Alice **trong chính tenant đó**.
- Tenant, owner, project và trạng thái của Document 42 từ database.
- Bản ghi ACL hoặc share grant còn hiệu lực, chưa bị thu hồi.
- Quyền được cấp bởi một dịch vụ authorization riêng.
- Trạng thái account bị đình chỉ, policy version hoặc điều kiện nghiệp vụ.

Nếu các dữ liệu ấy nằm trong database hoặc HTTP service, kiểm tra quyền trở thành một bước I/O. Đặt `jdbcTemplate.query(...)` hoặc `webClient...block()` trong authorization WebFlux có thể chặn thread xử lý sự kiện, làm giảm throughput và tăng latency cho cả những request khác.

Cách tiếp cận phù hợp là **trả một Publisher** như `Mono<Boolean>` hoặc `Mono<AuthorizationResult>`, dùng R2DBC hoặc WebClient để đọc quyền **không chặn luồng**, rồi chỉ cho request đi tiếp **sau khi đã nhận được quyết định**.

Đề bài này thuộc phần **HTTP trên WebFlux**: trọng tâm là nguồn dữ liệu quyền bất đồng bộ và cách nối nó với Spring Security Reactive, không phải việc thay toàn bộ nghiệp vụ bằng "async" một cách hình thức.

### Mục tiêu

Sau bài này có thể:

1. Giải thích non-blocking I/O khác với chạy JDBC trên một thread pool.
2. Đọc membership, ACL hoặc owner bằng R2DBC với `Mono`/`Flux`.
3. Tích hợp kiểm tra từ DB/remote policy service vào `ReactiveAuthorizationManager`.
4. Không nhầm `Mono.empty()`, `Mono.just(false)` và `Mono.error(...)`.
5. Xử lý timeout, lỗi dependency, cancellation và stale cache theo nguyên tắc **fail closed**.
6. Giữ đúng identity, tenant và resource scope trong chuỗi Reactor.
7. Dùng `WebTestClient` và `StepVerifier` để kiểm tra cả bảo mật lẫn tính bất đồng bộ.
8. Chạy một ví dụ Java 17 độc lập minh họa ghép các bước kiểm tra bất đồng bộ.

## 2. Non-blocking là gì, và không phải là gì?

Một luồng đơn giản:

```text
Request HTTP
   |
   v
Xác thực JWT/session -> Authentication
   |
   v
Reactive authorization manager
   |
   +--> đọc membership (R2DBC) ----+
   |                               |
   +--> đọc resource/owner --------+--> ALLOW/DENY
   |                               |
   +--> đọc grant hoặc WebClient --+
                                   |
                                   v
                         Cho phép hoặc chặn service
```

**Không chặn luồng** nghĩa là trong lúc chờ DB hoặc mạng, thread xử lý của Reactor/Netty không bị giữ bởi một lệnh đợi đồng bộ. Operation được biểu diễn như một pipeline và chỉ tiếp tục khi Publisher phát kết quả hoặc error.

Các khái niệm:

| Cơ chế | Đặc điểm | Phù hợp với WebFlux authorization? |
| --- | --- | --- |
| `Mono<Boolean>` | Phát 0 hoặc 1 kết quả bất đồng bộ | Có, khi xử lý đúng empty/error |
| `Mono<AuthorizationResult>` | Quyết định reactive của Spring Security phiên bản phù hợp | Có |
| `Flux<Grant>` | Có thể phát nhiều grant/record | Có, nhưng thường phải gom thành một quyết định |
| `ReactiveCrudRepository` / R2DBC | I/O database qua driver reactive | Có, nếu driver và thao tác thật non-blocking |
| `WebClient` | HTTP client reactive | Có, nếu không gọi `block()` |
| `JdbcTemplate` / JPA repository | I/O database đồng bộ/blocking | Không nên gọi trực tiếp trong reactive security pipeline |
| `RestTemplate` hoặc HTTP client blocking | Giữ thread khi chờ response | Không nên gọi trực tiếp trên event loop |
| `publishOn(boundedElastic())` quanh JDBC | Offload blocking sang pool khác | Giải pháp cầu nối có giới hạn, **không biến JDBC thành non-blocking I/O** |
| `CompletableFuture.join()` / `Future.get()` | Chặn thread chờ kết quả | Không gọi trong WebFlux request/event loop |

**Phân biệt:** chạy một tác vụ blocking trên `Schedulers.boundedElastic()` có thể tránh chặn Netty event loop, nhưng vẫn tiêu thụ thread khác và có giới hạn thread/queue. Khi có driver và endpoint reactive thực sự, ưu tiên R2DBC và WebClient. Nếu đang di chuyển từ JPA/JDBC, phải quyết định rõ phương án chuyển đổi, bulkhead, concurrency limit và giám sát.

### Reactive không tự động bằng an toàn

Đoạn mã sau trông có vẻ reactive nhưng vẫn chặn:

```java
Mono<Boolean> allowed = Mono.just(
    permissionJdbcRepository.existsByUserAndDocument(userId, documentId)
);
```

`permissionJdbcRepository.exists...` chạy **ngay khi tạo Mono**, trước khi subscribe. `Mono.just(...)` không biến công việc blocking thành non-blocking.

Một anti-pattern khác:

```java
boolean allowed = reactiveGrantRepository
    .existsByDocumentIdAndSubjectId(documentId, subjectId)
    .block();
```

`block()` chờ đồng bộ, nguy hiểm nếu được gọi trên Reactor event-loop. Ở các thread non-blocking, Reactor có thể phát hiện và ném lỗi; ở nơi khác vẫn có thể làm cạn thread và gây nghẽn tải.

## 3. Đường đi của một request được bảo vệ trong WebFlux

Với HTTP request:

```http
GET /api/tenants/tenant-a/documents/42
Authorization: Bearer <access-token-da-xac-minh>
```

Sơ đồ logic:

```text
WebFilterChainProxy / SecurityWebFilterChain
               |
               v
Authentication WebFilter / JWT validation
               |
               v
authorizeExchange().pathMatchers(...).access(reactiveManager)
               |
               v
ReactiveAuthorizationManager<AuthorizationContext>
               |
               +-- Authentication từ Publisher
               +-- path variable tenantId/documentId
               +-- trusted subject/tenant membership
               +-- DB facts / ACL / grant qua R2DBC hoặc WebClient
               |
               v
AuthorizationResult GRANT / DENY
               |
          +----+----+
          |         |
         GRANT     DENY
          |         |
          v         v
     Handler      Chặn, mapping
     Service      theo security entry point
          |
          v
  Tenant-scoped data access
```

Chữ `tenant-a` trong URL là **tenant được yêu cầu**, không phải bằng chứng Alice có membership trong tenant A. Nó phải được kiểm tra đối chiếu với authenticated subject và dữ liệu server-side trước khi truy vấn hoặc cho phép.

**Một request chỉ được xử lý tiếp khi authorization hoàn tất.** Chỉ việc tạo `Mono<Boolean>` mà không nối vào pipeline hoặc tự `subscribe()` rồi bỏ qua kết quả không bảo vệ được request.

## 4. Ba tín hiệu của Reactor: value, empty và error

Một `Mono<Boolean>` có thể có ba dạng:

```text
Mono.just(true)   -> có quyết định cho phép
Mono.just(false)  -> có quyết định từ chối
Mono.empty()      -> không có giá trị/quyết định
Mono.error(e)     -> có lỗi; chưa quyết định được
```

Những tín hiệu này không tương đương nhau.

**Chính sách an toàn ở boundary:**

- `true` → ALLOW **chỉ** khi toàn bộ bằng chứng được xác minh.
- `false` → DENY.
- `empty` → mặc định DENY hoặc quy tắc abstain được thiết kế cẩn thận; không được tự biến empty thành allow.
- `error` → **không cho phép**; có thể trả lỗi 5xx/503 nếu dependency gặp sự cố, và ghi metric/log nội bộ.
- Timeout → **không cho phép**; không tự bypass policy để giảm latency.

Ví dụ:

```java
Mono<Boolean> strictDecision =
    grants.hasActiveReadGrant(subjectId, documentId)
        .defaultIfEmpty(false);
```

Nếu repository không phát record, kết quả là `false`.

**Tránh:**

```java
Mono<Boolean> unsafe =
    grants.hasActiveReadGrant(subjectId, documentId)
        .onErrorReturn(true); // Cấm: lỗi DB lại mở quyền.
```

Và tránh `switchIfEmpty(Mono.just(true))` hoặc `onErrorResume(e -> Mono.just(true))`. Dù áp lực availability cao, lỗi hệ thống phân quyền không được biến thành cửa hậu ALLOW.

### Phân biệt "không tìm thấy" với "DB hỏng"

Repository `find...` trả `Mono.empty()` vì không có membership là trạng thái quyền **không được chứng minh** → DENY. Một lỗi kết nối R2DBC hay remote PDP timeout là lỗi hạ tầng; **cũng không cấp quyền**, nhưng có thể cần HTTP 503/5xx, alert, circuit breaker và retry có kiểm soát. Không nên nuốt mọi exception thành 403 làm mất observability và khiến nhóm vận hành tưởng tất cả user đều tự nhiên mất quyền.

## 5. R2DBC: đọc membership/ACL bằng database API reactive

Spring Data R2DBC hỗ trợ repository reactive qua `ReactiveCrudRepository<T, ID>`, `R2dbcEntityTemplate` và `DatabaseClient`. Chúng xây trên R2DBC driver phù hợp; cần **đúng driver, connection factory, transaction manager và dependency** của database.

Ví dụ một hệ thống dùng bảng:

```text
tenant_memberships(
    tenant_id, subject_id, active, can_read_documents
)

documents(
    id, tenant_id, owner_subject_id, deleted, title
)

document_share_grants(
    document_id, tenant_id, recipient_subject_id,
    permission, valid_from, expires_at, revoked_at
)
```

Đây là **schema khái niệm**, không phải schema Spring Security mặc định. Với Spring Data R2DBC, entity thường dùng `org.springframework.data.annotation.Id` và `org.springframework.data.relational.core.mapping.Table`, không dùng mặc định các annotation JPA `jakarta.persistence.Entity`.

### Repository membership

```java
import org.springframework.data.repository.reactive.ReactiveCrudRepository;
import reactor.core.publisher.Mono;

public interface TenantMembershipRepository
        extends ReactiveCrudRepository<TenantMembership, Long> {

    Mono<Boolean>
    existsByTenantIdAndSubjectIdAndActiveTrueAndCanReadDocumentsTrue(
        String tenantId,
        String subjectId
    );
}
```

Đây là interface **ứng dụng Spring Data R2DBC**, cần entity `TenantMembership` có các property tương ứng và repository scanning/connection factory hợp lệ. Nó không blocking và trả một `Mono<Boolean>`. Trong domain nhiều roles, permission `canReadDocuments` có thể được tính bằng join/role mapping khác; ý tưởng vẫn là **read permission theo đúng tenant**.

### Repository kiểm tra tài nguyên có thuộc đúng owner/tenant

```java
import org.springframework.data.repository.reactive.ReactiveCrudRepository;
import reactor.core.publisher.Mono;

public interface DocumentRepository
        extends ReactiveCrudRepository<Document, Long> {

    Mono<Boolean>
    existsByIdAndTenantIdAndOwnerSubjectIdAndDeletedFalse(
        Long documentId,
        String tenantId,
        String ownerSubjectId
    );

    Mono<Document> findByIdAndTenantIdAndDeletedFalse(
        Long documentId,
        String tenantId
    );
}
```

Khi policy yêu cầu chỉ owner được READ, có thể dùng query `existsBy...` thay vì tải nguyên object rồi kiểm tra ở Java. Dù dùng cách nào, phải giữ **tenantId và ID** cùng một predicate để tránh BOLA/IDOR. Với share grant, thêm chính sách kiểm tra grant đang hiệu lực; không mặc định một user có READ ở tenant là được xem mọi document private.

### Dữ liệu có thể biến động

Membership, ACL, owner và trạng thái document có thể bị sửa hoặc thu hồi. JWT còn hạn không bảo đảm các dữ liệu này vẫn như lúc token được cấp. Kiến trúc phải xác định mức độ mới (`freshness`), cache invalidation và thời điểm được phép đánh giá quyền.

## 6. Reactive policy: nối các truy vấn bằng flatMap thay vì block

Giả sử một policy **chỉ cho phép owner đọc**, sau khi kiểm tra authority chức năng và membership tenant:

```java
import org.springframework.security.core.Authentication;
import org.springframework.stereotype.Component;
import reactor.core.publisher.Mono;

@Component
public class ReactiveDocumentPolicy {
    private final TenantMembershipRepository memberships;
    private final DocumentRepository documents;
    private final SubjectResolver subjects;

    public ReactiveDocumentPolicy(
            TenantMembershipRepository memberships,
            DocumentRepository documents,
            SubjectResolver subjects) {
        this.memberships = memberships;
        this.documents = documents;
        this.subjects = subjects;
    }

    public Mono<Boolean> canRead(
            Authentication authentication,
            String requestedTenantId,
            Long documentId) {

        if (authentication == null
                || requestedTenantId == null
                || requestedTenantId.isBlank()
                || documentId == null || documentId <= 0L) {
            return Mono.just(false);
        }

        // SubjectResolver do ứng dụng tự viết và phải từ chối anonymous.
        return subjects.requireVerifiedSubject(authentication)
            .filter(subject ->
                subject.active()
                && subject.authorities().contains("document:read"))
            .flatMap(subject ->
                memberships
                    .existsByTenantIdAndSubjectIdAndActiveTrueAndCanReadDocumentsTrue(
                        requestedTenantId, subject.subjectId())
                    .flatMap(memberCanRead -> {
                        if (!memberCanRead) {
                            return Mono.just(false);
                        }
                        return documents
                            .existsByIdAndTenantIdAndOwnerSubjectIdAndDeletedFalse(
                                documentId, requestedTenantId,
                                subject.subjectId());
                    }))
            .defaultIfEmpty(false);
    }
}
```

**Giải thích:**

- `SubjectResolver` và `VerifiedSubject` là các type do ứng dụng triển khai. `requireVerifiedSubject(...)` phải lấy subject ổn định/identity từ Authentication **đã xác minh**, từ chối anonymous và trạng thái không đáng tin, đồng thời trả `Mono<VerifiedSubject>`.
- `requestedTenantId` đến từ path chỉ là selector. Query membership xác minh subject có READ trong tenant đó; một user có WRITE ở tenant A không tự có READ ở B.
- `flatMap` nối I/O tuần tự: chỉ khi membership cho phép mới query document.
- `defaultIfEmpty(false)` khiến subject không có hoặc publisher không phát kết quả thành DENY.
- Không có `block()` hay `subscribe()` thủ công.
- Lỗi DB không được biến thành true; code trên giữ error đi lên để xử lý an toàn ở boundary.
- Ví dụ owner-only không xử lý share grants hoặc field-level permissions, cần mở rộng theo domain.

**Đây là class thành phần ứng dụng, không phải một file Java chạy độc lập.** Nó cần `SubjectResolver`, domain entities, repositories, R2DBC driver/schema và cấu hình Spring. Khi dùng production, không bind `VerifiedSubject` từ request body; phải có service tạo subject từ Authentication và membership/trust context thực.

### Vì sao không tự subscribe trong policy?

Sai:

```java
public boolean canReadWrong(
        String tenantId, String subjectId) {
    memberships.existsByTenantIdAndSubjectIdAndActiveTrueAndCanReadDocumentsTrue(
        tenantId, subjectId
    ).subscribe(allowed -> {
        // Quá muộn: method đã return trước khi có kết quả.
        logAuthorization(allowed);
    });
    return true; // Cấm: fail open.
}
```

`subscribe()` tạo một luồng xử lý riêng, **không nối quyết định** vào filter chain. Khi method trả true, request có thể được cho qua trước khi DB phản hồi. `subscribe()` còn có thể làm mất context/cancellation/audit và gây side effects không kiểm soát.

Trong Spring WebFlux, trả chính Publisher để framework subscribe và quản lý vòng đời, error và cancellation.

## 7. Tích hợp với ReactiveAuthorizationManager<AuthorizationContext>

Spring Security WebFlux cung cấp `ReactiveAuthorizationManager<T>`; với `authorizeExchange().access(...)`, context thường là `AuthorizationContext` chứa `ServerWebExchange` và các path variables đã trích xuất.

**Chú ý API theo version:** Trong Spring Security 7.0+, interface `ReactiveAuthorizationManager<T>` có method chính `authorize(Mono<Authentication>, T)` trả `Mono<AuthorizationResult>`; `AuthorizationDecision` là một implementation của `AuthorizationResult`. Ở các dòng 6.x, một số API `check(...)` và kiểu kết quả có thể khác. **Kiểm tra dependency/Javadoc của dự án** trước khi copy đúng chữ ký này.

Ví dụ Spring Security **7.x**:

```java
import org.springframework.security.authentication.AnonymousAuthenticationToken;
import org.springframework.security.authorization.AuthorizationDecision;
import org.springframework.security.authorization.AuthorizationResult;
import org.springframework.security.authorization.ReactiveAuthorizationManager;
import org.springframework.security.core.Authentication;
import org.springframework.security.web.server.authorization.AuthorizationContext;
import org.springframework.stereotype.Component;
import reactor.core.publisher.Mono;

@Component
public class DocumentReadAuthorizationManager
        implements ReactiveAuthorizationManager<AuthorizationContext> {

    private final ReactiveDocumentPolicy policy;

    public DocumentReadAuthorizationManager(ReactiveDocumentPolicy policy) {
        this.policy = policy;
    }

    @Override
    public Mono<AuthorizationResult> authorize(
            Mono<Authentication> authentication,
            AuthorizationContext context) {

        String tenant = context.getVariables().get("tenantId");
        String rawId = context.getVariables().get("documentId");
        Long id = parseId(rawId);

        if (tenant == null || tenant.isBlank() || id == null) {
            return Mono.just(new AuthorizationDecision(false));
        }

        return authentication
            .filter(auth ->
                auth.isAuthenticated()
                && !(auth instanceof AnonymousAuthenticationToken))
            .flatMap(auth -> policy.canRead(auth, tenant, id))
            .map(granted ->
                (AuthorizationResult) new AuthorizationDecision(granted))
            .defaultIfEmpty(new AuthorizationDecision(false));
    }

    private static Long parseId(String value) {
        if (value == null) {
            return null;
        }
        try {
            long id = Long.parseLong(value);
            return id > 0 ? id : null;
        } catch (NumberFormatException invalid) {
            return null;
        }
    }
}
```

**Vì sao ép kiểu trong `map`?** `AuthorizationDecision` triển khai `AuthorizationResult`. Trên API 7.x, method phải trả `Mono<AuthorizationResult>`, còn generic của Reactor là bất biến: `Mono<AuthorizationDecision>` không tự gán thành `Mono<AuthorizationResult>`. Viết `(AuthorizationResult) new AuthorizationDecision(granted)` làm kiểu trả phù hợp.

**Mặc định deny:**

- Thiếu path variable/ID không parse được → DENY.
- Không có Authentication phát ra từ Mono → DENY.
- Anonymous hoặc không authenticated → DENY.
- Repository không tìm thấy subject/membership/document → false → DENY.
- Error DB/WebClient → **không ALLOW**. Nếu không có handler chuyển lỗi, nó sẽ đi theo error flow; ứng dụng cần cấu hình an toàn HTTP error response và metrics.

Không nên biến `Authentication.isAuthenticated()` thành bằng chứng duy nhất là user đã đăng nhập; `AnonymousAuthenticationToken` có thể cần được phân biệt, và `SubjectResolver` vẫn phải xác minh principal type/issuer/status thực sự.

### Cấu hình WebFlux HTTP

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.web.server.SecurityWebFilterChain;

@Configuration
@EnableWebFluxSecurity
public class ReactiveHttpSecurityConfig {

    @Bean
    SecurityWebFilterChain apiSecurity(
            ServerHttpSecurity http,
            DocumentReadAuthorizationManager documentRead) {

        return http
            .authorizeExchange(exchanges -> exchanges
                .pathMatchers(
                    HttpMethod.GET,
                    "/api/tenants/{tenantId}/documents/{documentId}"
                ).access(documentRead)
                .anyExchange().denyAll()
            )
            .oauth2ResourceServer(oauth2 -> oauth2
                .jwt(Customizer.withDefaults())
            )
            .build();
    }
}
```

Đây là **class cấu hình Spring Security 7.x mang tính minh họa**. Cần JWT decoder/issuer/audience validation, controller phù hợp và các endpoints của ứng dụng. `anyExchange().denyAll()` nghĩa là các route khác chưa được khai báo sẽ bị từ chối. Nếu ứng dụng có health/public endpoints, thêm những rule hẹp theo API contract và bảo vệ kỹ management endpoints.

**Quan trọng:** `authorizeExchange` chỉ định authorization **trong một chain đã được chọn**. Nếu ứng dụng có nhiều `SecurityWebFilterChain`, cần xem `securityMatcher(...)` và `@Order`; request vào chain khác thì custom manager của ví dụ này sẽ không được gọi. Chain đầu khớp sẽ được dùng, không chạy thử các chain sau khi DENY.

### Những gì còn phải bảo vệ

Dù custom manager cho READ đã cho phép, handler và service vẫn phải dùng truy vấn **tenant-scoped**. Nếu controller gọi `documentRepository.findById(documentId)` mà không kiểm tra tenant, một race/call-path khác có thể đọc dữ liệu ngoài phạm vi. Đừng coi request-level policy là bảo vệ duy nhất, nhất là với GraphQL, jobs, SSE và internal service calls.

## 8. Thiết kế API không chặn luồng cho data-access

Không phải mọi dữ liệu đều ở repository có derived query. Khi rule phức tạp, dùng `DatabaseClient` cho SQL ràng buộc rõ:

```java
import org.springframework.r2dbc.core.DatabaseClient;
import reactor.core.publisher.Mono;

public class DocumentOwnerPermissionQuery {
    private final DatabaseClient db;

    public DocumentOwnerPermissionQuery(DatabaseClient db) {
        this.db = db;
    }

    public Mono<Boolean> canOwnerRead(
            String tenantId, String subjectId, long docId) {
        return db.sql("""
                SELECT EXISTS (
                    SELECT 1
                    FROM documents d
                    JOIN tenant_memberships m
                      ON m.tenant_id = d.tenant_id
                     AND m.subject_id = :subject
                    WHERE d.id = :id
                      AND d.tenant_id = :tenant
                      AND d.owner_subject_id = :subject
                      AND d.deleted = FALSE
                      AND m.active = TRUE
                      AND m.can_read_documents = TRUE
                ) AS allowed
                """)
            .bind("id", docId)
            .bind("tenant", tenantId)
            .bind("subject", subjectId)
            .map((row, metadata) ->
                Boolean.TRUE.equals(row.get("allowed", Boolean.class)))
            .one()
            .defaultIfEmpty(false);
    }
}
```

Đoạn này dùng **PostgreSQL-style SQL** và Spring R2DBC `DatabaseClient`, cần cấu hình DB/schema thật. Một số database/dialect có cú pháp boolean, `EXISTS` và aliases khác nhau. Tất cả parameters được **bind**, không nối `tenantId` hay subject input vào chuỗi SQL.

Ưu điểm của một truy vấn:

- Xét membership và owner/resource trong cùng SQL statement.
- Giảm số vòng đọc I/O.
- Không tạo khoảng trống giữa việc đọc membership rồi đọc resource ở hai statement tách biệt.
- Không tải các field nhạy cảm không cần thiết chỉ để quyết định READ.

**Giới hạn:** một statement không tự giải quyết mọi race khi membership bị revoke trong transaction khác hoặc khi dữ liệu đã được streaming. Cần định nghĩa nhất quán quyền theo thời điểm và isolation nếu nghiệp vụ đòi SLA chặt.

### Truy vấn có share grant

Một policy READ cho owner **hoặc** người có grant có thể biểu diễn logic:

```sql
SELECT EXISTS (
    SELECT 1
    FROM documents d
    JOIN tenant_memberships m
      ON m.tenant_id = d.tenant_id
     AND m.subject_id = :subject
    WHERE d.id = :id
      AND d.tenant_id = :tenant
      AND d.deleted = FALSE
      AND m.active = TRUE
      AND m.can_read_documents = TRUE
      AND (
        d.owner_subject_id = :subject
        OR EXISTS (
            SELECT 1
            FROM document_share_grants g
            WHERE g.document_id = d.id
              AND g.tenant_id = d.tenant_id
              AND g.recipient_subject_id = :subject
              AND g.permission = 'READ'
              AND g.revoked_at IS NULL
              AND g.valid_from <= :now_utc
              AND g.expires_at > :now_utc
        )
      )
) AS allowed;
```

Đây là **SQL logic** của một ứng dụng có sharing grants; cần schema, foreign keys, query plan, index và các điều kiện resource/business state. `:now_utc` đến từ server/DB clock được xác định rõ. Grant hết hạn đúng tại `expires_at` do điều kiện `now < expires_at`.

**Không** tin rằng JPA entity annotations tự hoạt động trong R2DBC, hoặc R2DBC tự mang Spring ACL `AclService` vào luồng reactive. Nếu ACL store chỉ có API blocking, phải tính phương án query chuyển đổi hoặc adapter giới hạn thread thích hợp.

## 9. Đọc quyền từ dịch vụ bên ngoài bằng WebClient

Một số tổ chức có **remote authorization service/PDP** thay vì lưu mọi membership/ACL trong application database.

Luồng:

```text
Spring WebFlux request
   |
   v
Reactive authorization manager
   |
   v
WebClient -> internal policy service (non-blocking)
   |
   v
ALLOW / DENY / dependency error
   |
   v
PEP enforce -> application handler
```

Ví dụ contract tự thiết kế:

```json
{
  "subjectId": "u-101",
  "tenantId": "tenant-a",
  "resourceType": "Document",
  "resourceId": "42",
  "action": "READ",
  "policyVersion": "document-policy-v3"
}
```

Các trường trên phải do **backend xây từ dữ liệu đáng tin**, không lấy nguyên JSON do người dùng không có quyền gửi vào PDP. Remote service phải xác thực ứng dụng gọi nó (mTLS/service credentials), validate input schema và có authority để quyết định.

### WebClient trả Mono, không block

```java
import java.time.Duration;
import org.springframework.http.MediaType;
import org.springframework.web.reactive.function.client.WebClient;
import reactor.core.publisher.Mono;

public class RemotePermissionClient {

    public record CheckRequest(
        String subjectId,
        String tenantId,
        String resourceType,
        String resourceId,
        String action
    ) {}

    public record CheckResponse(
        boolean allowed,
        String policyVersion
    ) {}

    private final WebClient client;

    public RemotePermissionClient(WebClient client) {
        this.client = client;
    }

    public Mono<Boolean> canReadDocument(
            String verifiedSubject,
            String verifiedTenant,
            String documentId) {

        CheckRequest request = new CheckRequest(
            verifiedSubject, verifiedTenant,
            "Document", documentId, "READ"
        );

        return client.post()
            .uri("/internal/authorize")
            .contentType(MediaType.APPLICATION_JSON)
            .bodyValue(request)
            .retrieve()
            .bodyToMono(CheckResponse.class)
            .map(CheckResponse::allowed)
            .defaultIfEmpty(false)
            .timeout(Duration.ofMillis(400));
    }
}
```

Đây là **component Spring WebClient**; để chạy thực tế cần bean `WebClient` trỏ đến service được tin cậy, TLS/authentication, timeout/connect/read budgets, registry và API contract. Thời hạn 400 ms chỉ là **ví dụ vận hành**, không phải hằng số được Spring Security quy định.

**Theo mặc định**, `retrieve()` biến nhiều HTTP 4xx/5xx thành error. `timeout(...)` cũng đưa error khi vượt thời hạn. Điều đó là có chủ đích: **error không được coi là ALLOW**. Cần xử lý phân biệt reject hợp lệ, unauthorized caller của PDP, outage, malformed response và audit ở boundary; không nối `onErrorReturn(true)`.

### Tin cậy kết quả remote PDP

Response `{"allowed":true}` chỉ đáng tin nếu:

- Đã xác thực đúng service nhận/trao đổi thông tin.
- TLS/network trust và token audience phù hợp.
- Câu trả lời tương ứng **đúng subject, resource, action, tenant** của request.
- Policy version/release được phép cho action đó.
- Data snapshot/freshness đáp ứng yêu cầu.
- Không có response mix-up do cache key hoặc retry.
- Trường bắt buộc không bị missing/parse sai.

Nếu API response được cache, không dùng key chỉ có `resourceId`; cần subject/tenant/action/version và trạng thái ACL liên quan. Một ALLOW cho Alice đọc Document 42 không thể được tái sử dụng cho Bob.

## 10. Timeout, retry và xử lý lỗi theo fail closed

Một dependency authorization bị chậm có thể làm chậm **toàn bộ request**, nên timeout/bulkhead là cần thiết. Nhưng timeout phải được xử lý an toàn.

| Tình huống | Quyết định cho request | Hành động vận hành |
| --- | --- | --- |
| Membership active, permission đúng, resource trong tenant | ALLOW | Xử lý nghiệp vụ |
| Không có membership | DENY | 403/404 theo policy |
| Grant revoked/expired | DENY | Không trả dữ liệu |
| Remote PDP trả explicit DENY | DENY | Audit phù hợp |
| Remote PDP trả empty/unknown payload | DENY | Metric bất thường |
| R2DBC/remote PDP timeout | **Không ALLOW** | 503/5xx hoặc DENY an toàn, alert |
| DB connection error | **Không ALLOW** | Circuit breaker/observability |
| JWT không hợp lệ | Không có Authentication hợp lệ | Auth challenge/401 |
| Resource ngoài tenant | DENY hoặc 404 trung tính | Không lộ metadata tenant khác |
| Policy version không kiểm chứng được | DENY | Dừng rollout/incident response |

### Ví dụ pattern xử lý lỗi rõ ràng

```java
return remotePermissions.canReadDocument(
        subjectId, tenantId, documentId)
    .defaultIfEmpty(false)
    .onErrorResume(error -> {
        authorizationMetrics.recordDependencyFailure(error);
        return Mono.error(
            new AuthorizationDependencyUnavailableException(error)
        );
    });
```

Đây là **fragment**: metric collector và exception là types ứng dụng; cần mapping exception thành HTTP 503/5xx không chứa secrets. **Không cấp quyền** trong error branch.

Nếu một hệ thống chủ động muốn trả `AuthorizationDecision(false)` thay vì 503, vẫn phải ghi lý do *DEPENDENCY_UNAVAILABLE* riêng trong audit; tránh trộn “user không có quyền” với “hệ thống không thể kiểm tra”.

### Retry có giới hạn

Retry có thể có ích cho lỗi mạng tạm thời nhưng không được:

- Retry vô hạn khi mọi request đang chờ authorization.
- Retry 403/explicit DENY từ PDP.
- Retry quá thời gian request cho phép.
- Gửi lại credential/attributes tới host không đáng tin.
- Làm thay đổi dữ liệu ngoài ý muốn nếu endpoint PDP không thật sự read-only.

Có thể dùng `retryWhen(Retry.backoff(...).filter(...))` với **loại lỗi** và ngân sách thời gian rõ ràng. Không coi retry là thay thế cho circuit breaker và health monitoring.

### Connection pool và backpressure

R2DBC/WebClient vẫn cần giới hạn số connection, số request đang chờ, kích thước response và concurrency. Một Publisher non-blocking có thể tạo **hàng nghìn I/O đồng thời** nếu request traffic không được kiểm soát. Nên theo dõi queue depth, pool saturation, timeouts, p95/p99 của quyết định và resource limits.

## 11. Reactor Context và Authentication: không dựa vào ThreadLocal tùy tiện

Spring Security reactive dùng `ReactiveSecurityContextHolder` với Reactor Context. Nhiều ứng dụng Servlet/JPA quen đọc `SecurityContextHolder.getContext()` trên thread hiện tại; trong WebFlux, execution có thể đổi thread qua `publishOn` hoặc I/O callback.

Một cách truy cập context reactive:

```java
import org.springframework.security.core.context.ReactiveSecurityContextHolder;
import org.springframework.security.core.context.SecurityContext;
import org.springframework.security.core.Authentication;
import reactor.core.publisher.Mono;

Mono<Authentication> currentAuthentication =
    ReactiveSecurityContextHolder.getContext()
        .map(SecurityContext::getAuthentication);
```

Trong WebFlux Security, context thường đã được Spring Security thiết lập cho pipeline request. Với mã authorization ở request level, **ưu tiên Mono Authentication được Spring Security truyền vào** `ReactiveAuthorizationManager` thay vì tự tìm lại context qua biến global.

### ContextWrite trong unit test

```java
Mono<String> subject = ReactiveSecurityContextHolder
    .getContext()
    .map(ctx -> ctx.getAuthentication().getName());

Mono<String> result = subject.contextWrite(
    ReactiveSecurityContextHolder.withAuthentication(auth)
);
```

Đây là **fragment**, cần biến `auth` là Authentication fixture thực hoặc test authentication. `contextWrite` gắn Reactor context cho subscription, không biến `SecurityContextHolder` Servlet thành nguồn tin cậy.

**Sai lầm:** giữ `activeTenant` trong một static mutable field hoặc ThreadLocal không clear rồi dùng nó để query R2DBC. Khi nhiều request/tenant đồng thời, context có thể bị trộn. Hãy truyền một `VerifiedTenantScope`/`tenantId` bất biến qua các method sau khi verify membership.

### Ranh giới async khác

Nếu code nhảy sang `CompletableFuture`, executor tùy biến, callback của thư viện khác hoặc message queue, **không mặc định** Reactor context được chuyển tự động. Phải có cách truyền/khôi phục principal và tenant scope đúng, và tái kiểm tra quyền khi tác vụ thực thi sau khi membership có thể đã bị thu hồi.

## 12. Ghép nhiều nguồn quyền không chặn: AND, OR và short-circuit

Một chính sách có thể là:

```text
authenticated
AND account ACTIVE
AND tenant membership ACTIVE
AND document.tenant == tenant đã xác minh
AND document không deleted
AND có authority READ
AND (owner OR share READ grant chưa revoke/chưa hết hạn)
```

**AND với điều kiện bắt buộc** phải bao bọc **OR của các đường cấp quyền**. Không viết:

```text
owner OR membership OR activeShare
```

vì một user là owner ở tenant khác có thể vượt tenant boundary, hoặc membership đơn thuần bị nhầm với quyền trên từng tài liệu.

### Chạy nối tiếp

```java
return memberships.canReadTenant(subject, tenant)
    .flatMap(canTenantRead -> {
        if (!canTenantRead) {
            return Mono.just(false);
        }
        return documents.findVisibleByIdAndTenant(id, tenant)
            .flatMap(doc ->
                subject.equals(doc.ownerSubjectId())
                    ? Mono.just(true)
                    : grants.hasActiveReadGrant(
                        subject, tenant, id, clock.instant()))
            .defaultIfEmpty(false);
    })
    .defaultIfEmpty(false);
```

**Fragment:** các method `canReadTenant`, `findVisibleByIdAndTenant` và `hasActiveReadGrant` là service ứng dụng; cần xác minh chúng không blocking, áp đúng tenant và action. Phần này tránh query resource/ACL nếu membership đã bị deny.

### Chạy song song khi phù hợp

`Mono.zip(...)` hoặc `Mono.zipWhen(...)` có thể ghép các truy vấn độc lập để giảm latency, nhưng không chạy grant query sớm nếu kết quả là thông tin nhạy cảm của một tenant **chưa được xác minh**. Parallelism không phải lý do nới trust boundary.

Ví dụ: sau khi đã xác minh member, có thể đọc một số facts không phụ thuộc nhau; nếu nguồn dữ liệu cần transaction snapshot nhất quán, chạy song song trên nhiều connection còn có thể làm **mất** tính nhất quán dự định. Chọn pipeline dựa vào policy và transaction model, không chỉ dựa benchmark tốc độ.

### Tránh collectList trên toàn bộ tập grant

Đừng làm:

```java
return grants.findAllByTenantId(tenant)
    .collectList()
    .map(list -> list.stream().anyMatch(...));
```

Đây là anti-pattern: đọc mọi grant của tenant vào memory trước khi quyết định một Document ID. Nên query `existsBy...` hoặc `DatabaseClient` với predicate tenant/document/recipient/permission/time và index phù hợp. `Flux` có thể phát hàng triệu row và backpressure giúp điều phối demand, nhưng không biện minh cho query quyền quá rộng.

## 13. Đọc quyền trong transaction và tránh TOCTOU

Ví dụ:

```text
T1: canEdit(alice, doc42) -> true
T2: admin revoke quyền EDIT của Alice
T1: update Document 42
```

Không chặn luồng **không giải quyết** race này. Một quyết định từ R2DBC được đọc trước DB update vẫn có thể trở nên cũ. `@Transactional` với reactive transaction manager không tự làm mọi query serializable nếu isolation mặc định.

Những cách bảo vệ:

- Đặt check quyền và mutation bên trong cùng reactive transaction khi nghiệp vụ yêu cầu.
- Với update, dùng câu SQL có `WHERE id=:id AND tenant_id=:tenant AND owner_id=:subject AND status='DRAFT'` và kiểm tra row count.
- Dùng version/optimistic locking hoặc row locks có chủ đích nếu quyền có thể bị thu hồi đồng thời.
- Với ACL riêng bảng, ràng buộc grant trong câu UPDATE/transaction hoặc chọn isolation phù hợp.
- Xác định policy về thời điểm: được phép tại lúc request bắt đầu, lúc statement chạy hay lúc commit?
- Không gửi external side effects trước khi transaction thành công; dùng outbox/after-commit phù hợp.

### Reactive transaction không phải ThreadLocal transaction

Spring reactive transactions sử dụng Reactor context để truyền transactional resources. Một ví dụ với `TransactionalOperator`:

```java
import org.springframework.transaction.reactive.TransactionalOperator;
import reactor.core.publisher.Mono;

public Mono<UpdateOutcome> updateTitle(
        String subject,
        String tenant,
        long documentId,
        String title) {

    return permissionQuery.canEdit(subject, tenant, documentId)
        .flatMap(allowed -> {
            if (!allowed) {
                return Mono.error(
                    new org.springframework.security.access.AccessDeniedException(
                        "Document update denied"));
            }
            return documentWriteRepository
                .updateTitleIfAuthorized(
                    subject, tenant, documentId, title)
                .map(rows -> rows == 1
                    ? UpdateOutcome.UPDATED
                    : UpdateOutcome.NOT_UPDATED);
        })
        .as(transactionalOperator::transactional);
}
```

Đây là **method fragment**: `transactionalOperator`, repositories, `UpdateOutcome` và permission model là thành phần ứng dụng. `updateTitleIfAuthorized` phải có điều kiện authorization sát lệnh ghi; nếu chỉ dùng update theo ID, kiểm tra trước transaction có thể bị stale. `TransactionalOperator` phải dùng đúng `ReactiveTransactionManager` tương thích với connection factory/store. Transaction một database không mặc nhiên bao remote PDP và email/object storage.

### @PreAuthorize trong reactive method security

Spring Security cũng có `@EnableReactiveMethodSecurity`; các method reactive trả `Mono`/`Flux` có thể được bảo vệ bằng SpEL:

```java
@PreAuthorize(
    "hasAuthority('document:read') and " +
    "@documentPermission.canRead(authentication, #tenantId, #documentId)"
)
public Mono<DocumentView> read(
        String tenantId, Long documentId) {
    // ...
}
```

**Đây là fragment**, cần bean `documentPermission` hỗ trợ reactive decision theo khả năng của Spring Security version được chọn, `@EnableReactiveMethodSecurity(useAuthorizationManager=true)` trong các dòng phù hợp và method được gọi qua Spring-managed proxy. Tài liệu Spring Security reactive method security mô tả hỗ trợ `Mono<Boolean>` từ bean SpEL trong mode AuthorizationManager. Đừng gọi `block()` bên trong bean chỉ để trả `boolean`.

Một thay thế đơn giản là để service trả:

```java
return permission.canRead(authentication, tenantId, documentId)
    .flatMap(allowed -> allowed
        ? documents.findByIdAndTenantIdAndDeletedFalse(
              documentId, tenantId)
        : Mono.error(new AccessDeniedException("Forbidden")));
```

Khi dùng service-level composition, cần bảo đảm **tất cả đường gọi** đi qua nó và dữ liệu được truy vấn tenant-scoped; không chỉ bảo vệ một controller rồi để worker/GraphQL gọi repository trực tiếp.

## 14. Khác biệt giữa "deny" và "not found"

Trong API đa tenant, `GET /tenants/A/documents/42` có thể gặp:

- User không có token → authentication failure, thường 401/challenge.
- Token hợp lệ nhưng user thiếu authority READ → thường 403.
- User không thuộc tenant A → 403 hoặc 404 trung tính theo contract.
- Document 42 không tồn tại trong A → 404.
- Document 42 thuộc tenant B → cũng nên **không lộ** sự tồn tại B, có thể 404.
- Permission DB/PDP đang outage → 503/5xx không lộ dữ liệu, **không ALLOW**.

Có thể chọn 404 để che giấu resource existence cho người không được phép biết, nhưng cần nhất quán. Không mặc định rằng `ReactiveAuthorizationManager` tự tạo HTTP 404 cho mọi DENY; ánh xạ exception/status cần cấu hình theo API contract.

Bên trong policy, nên dùng reason code riêng cho audit (ví dụ `NOT_MEMBER`, `NOT_OWNER`, `REVOKED`, `DEPENDENCY_FAILURE`) nhưng không gửi owner/tenant/private resource facts trong response.

## 15. Dùng blocking store tạm thời: phương án di trú có giới hạn

Nhiều dự án đã có `JpaRepository`/`JdbcTemplate` và không thể thay ngay bằng R2DBC. Có thể **offload blocking**:

```java
import reactor.core.publisher.Mono;
import reactor.core.scheduler.Schedulers;

Mono<Boolean> allowed =
    Mono.fromCallable(() ->
        blockingGrantRepository.hasReadPermission(
            subjectId, tenantId, documentId))
        .subscribeOn(Schedulers.boundedElastic());
```

Điều này:

- Trì hoãn lời gọi blocking đến lúc subscribe.
- Chuyển công việc sang scheduler dành cho blocking workloads.
- Tránh trực tiếp giữ Netty event loop trong lúc JDBC chờ.
- **Không biến JDBC thành API non-blocking**: vẫn có thread chờ I/O.
- Cần cấu hình pool/bulkhead/timeout và metrics.

Không lạm dụng `boundedElastic()` để che tất cả vấn đề hiệu năng. Nếu một request gọi nhiều blocking stores, thread/queue vẫn có thể cạn dưới tải cao. Với JPA transaction/entity manager, phải đánh giá context/transaction boundaries riêng; không chuyển operations qua threads tùy ý trong cùng persistence context.

**Không:** `Mono.just(blockingCall())` vì blocking call chạy trước khi Mono được tạo. Và cũng không: `blockingRepository...block()` bởi repository blocking vốn không có Mono cần block; sai bản chất.

## 16. Cache quyết định quyền trong hệ thống reactive

Caching có thể giảm số lần đọc DB/PDP, nhưng quyền thường **thay đổi nhanh**.

Phân biệt:

| Loại cache | Rủi ro |
| --- | --- |
| Cache membership | User đã bị revoke nhưng còn được dùng quyền cũ |
| Cache document facts | Owner/tenant/status đã đổi |
| Cache share grant | Grant đã hết hạn hoặc revoke |
| Cache remote policy decision | Bob có thể dùng ALLOW của Alice |
| Cache HTTP response | Tài liệu riêng tư được phục vụ cho user khác |

### Cache key đúng chiều

Một key kiểu `doc42:READ` là sai nếu chỉ có documentId/action. Tối thiểu cần xét:

```text
authenticatedSubjectId
| verifiedTenantId
| resourceType
| resourceId
| action
| relevantPolicyVersion
| membershipOrAclVersion
| contextRestrictions
```

Thực tế key có thể dùng hash/namespace không lộ PII. Nhưng **mọi chiều ảnh hưởng quyền** phải được thể hiện hoặc recheck khi đọc cache.

Với share grant có thời gian sống:

```text
positiveCacheTTL <= min(
    configuredTTL,
    expiresAt - currentServerInstant,
    allowedRevocationStalenessBudget
)
```

Ngay cả như vậy, chỉ TTL không bảo đảm revoke ngay khi user bấm "Stop sharing"; cần invalidation/event/version hoặc truy nguồn sự thật. **Không** hứa revoke ≤1 giây nếu cache ALLOW giữ 5 phút mà không recheck.

### Reactor Mono.cache() không tự biết principal

`mono.cache()` memoize result trên **chính publisher instance**. Nếu một service singleton giữ lại `Mono<Boolean>` đã được tạo cho Alice và dùng nó cho Bob, cache có thể trả ALLOW của Alice.

Vì vậy không gắn `cache()` lên một Publisher authorization được chia sẻ giữa nhiều subject/request, trừ khi key/ownership và thời hạn được thiết kế đúng. Giữa các subscription của cùng một operation có thể có trường hợp reuse hợp lý; **đừng đánh đồng Publisher cache với cache phân quyền đa người dùng**.

## 17. WebClient: request context, cancellation và token forwarding

Khi application gọi dịch vụ permission bằng WebClient, cần quyết định:

- Dùng **service credential** cho một internal PDP đáng tin.
- Hoặc dùng **token exchange/on-behalf-of** nếu hạ tầng yêu cầu caller delegated identity.
- Xác minh audience/scope của token được forward; không gửi bearer token của người dùng sang dịch vụ không cần nó.
- Gửi subject/tenant/resource/action dưới contract server-to-server có xác thực.
- Thiết lập timeout kết nối và tổng budget đọc.
- Hạn chế kích thước response và số concurrent requests.
- Có logic hủy hoặc bỏ qua kết quả khi client cancel; không gây side effects trong bước kiểm tra.

Nếu browser ngắt kết nối, cancellation có thể truyền xuống Publisher và remote request tùy implementation; nhưng **không coi cancellation là quyết định ALLOW** hoặc giả định mọi external side effect đều được hủy. Authorization nên là bước **read-only**, idempotent khi có thể.

### Side effects trong doOnNext

`doOnNext(...)` phù hợp cho telemetry nhẹ, nhưng không nên dùng nó để ghi ACL, thay owner hay gửi notification trong lúc chỉ hỏi canRead. Một kiểm tra quyền lặp/retry có thể phát sinh side effects nhiều lần.

## 18. Debug reactive chain: khi nào truy vấn thật sự chạy?

Trong Reactor, nhiều Publisher là **cold**: tạo pipeline không nhất thiết chạy I/O ngay. I/O diễn ra khi có subscription.

Ví dụ:

```java
Mono<Boolean> pipeline = repository.existsById(42L)
    .doOnSubscribe(s -> log.debug("authorization query subscribed"));

return pipeline;
```

Đây là fragment minh họa. Với Repository R2DBC, Spring/Reactor điều khiển subscription khi HTTP chain cần quyết định. Không gọi `pipeline.subscribe()` chỉ để "khởi động trước" rồi trả một Publisher khác.

Khi debug:

1. Có thật `ReactiveAuthorizationManager` đã được gọi cho route không?
2. `Mono<Authentication>` có phát Authentication hợp lệ không?
3. `flatMap` có được subscribe hay đã short-circuit ở filter?
4. Path variables có đúng `tenantId` và `documentId`?
5. Membership query có dùng tenant từ server-confirmed context không?
6. Khi `Mono.empty()`, policy có chuyển DENY không?
7. Exception ở R2DBC/WebClient có bị nuốt thành true không?
8. Có tác vụ blocking trong event loop không?
9. Có cache ALLOW của subject khác không?
10. WebTestClient có chạy Spring Security WebFilter chain thật không?

Log nên chứa request ID, subject đã verify (nếu privacy cho phép), tenant ID, resource type/action, decision/reason và latency, nhưng **không log nguyên JWT, password, cookie, body tài liệu hoặc SQL params nhạy cảm**.

## 19. Java 17 độc lập: mô phỏng pipeline quyết định bất đồng bộ

Ví dụ dưới đây không sử dụng Spring Security hoặc R2DBC vì các thư viện đó cần dependency ngoài JDK. Nó dùng `CompletableFuture` để minh họa **không lấy kết quả sớm**, nối các bước kiểm tra membership và tài nguyên bằng `thenCompose`, mặc định deny khi thiếu quyền và giữ ranh giới tenant.

Trong ứng dụng WebFlux thật, thay `CompletableFuture` bằng `Mono` của R2DBC/WebClient; **không gọi `join()` hoặc `get()` trên event loop**. Trong `main` của chương trình độc lập, dùng `join()` để in stdout xác định sau khi mọi tác vụ hoàn tất, không phải mẫu cho HTTP handler.

Lưu file `AsyncPermissionDemo.java`:

```java
import java.util.Map;
import java.util.Set;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CompletionStage;

public class AsyncPermissionDemo {

    record Actor(
        String subjectId,
        String tenantId,
        Set<String> authorities,
        boolean active
    ) {}

    record Document(
        long id,
        String tenantId,
        String ownerId,
        boolean deleted
    ) {}

    record Membership(
        String subjectId,
        String tenantId,
        boolean canRead
    ) {}

    private final Map<String, Membership> memberships = Map.of(
        "alice|tenant-a",
            new Membership("alice", "tenant-a", true),
        "bob|tenant-a",
            new Membership("bob", "tenant-a", true),
        "carol|tenant-b",
            new Membership("carol", "tenant-b", true)
    );

    private final Map<Long, Document> documents = Map.of(
        42L, new Document(42, "tenant-a", "alice", false),
        77L, new Document(77, "tenant-b", "carol", false),
        90L, new Document(90, "tenant-a", "alice", true)
    );

    // Mô phỏng API bất đồng bộ: không cung cấp bằng chứng -> false.
    CompletionStage<Boolean> hasMembership(Actor actor) {
        Membership member = memberships.get(
            actor.subjectId() + "|" + actor.tenantId());
        return CompletableFuture.completedFuture(
            member != null && member.canRead()
                && member.tenantId().equals(actor.tenantId()));
    }

    CompletionStage<Boolean> isVisibleOwner(Actor actor, long documentId) {
        Document doc = documents.get(documentId);
        return CompletableFuture.completedFuture(
            doc != null && !doc.deleted()
                && doc.tenantId().equals(actor.tenantId())
                && doc.ownerId().equals(actor.subjectId()));
    }

    CompletionStage<String> authorizeRead(
            Actor actor, long documentId) {
        if (actor == null || !actor.active()
                || !actor.authorities().contains("document:read")) {
            return CompletableFuture.completedFuture("DENY");
        }

        return hasMembership(actor)
            .thenCompose(isMember -> {
                if (!isMember) {
                    return CompletableFuture.completedFuture(false);
                }
                return isVisibleOwner(actor, documentId);
            })
            .thenApply(granted -> granted ? "ALLOW" : "DENY")
            .exceptionally(error -> "DENY");
    }

    public static void main(String[] args) {
        AsyncPermissionDemo demo = new AsyncPermissionDemo();

        Actor alice = new Actor(
            "alice", "tenant-a",
            Set.of("document:read"), true);
        Actor bob = new Actor(
            "bob", "tenant-a",
            Set.of("document:read"), true);
        Actor carol = new Actor(
            "carol", "tenant-b",
            Set.of("document:read"), true);
        Actor guest = new Actor(
            "guest", "tenant-a", Set.of(), true);
        Actor inactive = new Actor(
            "alice", "tenant-a",
            Set.of("document:read"), false);

        // Chỉ main của chương trình Java độc lập đợi để in theo thứ tự.
        System.out.println("Alice owns 42: "
            + demo.authorizeRead(alice, 42).toCompletableFuture().join());
        System.out.println("Bob same tenant, not owner: "
            + demo.authorizeRead(bob, 42).toCompletableFuture().join());
        System.out.println("Alice cross tenant 77: "
            + demo.authorizeRead(alice, 77).toCompletableFuture().join());
        System.out.println("Carol owns 77: "
            + demo.authorizeRead(carol, 77).toCompletableFuture().join());
        System.out.println("Alice deleted 90: "
            + demo.authorizeRead(alice, 90).toCompletableFuture().join());
        System.out.println("Guest no authority: "
            + demo.authorizeRead(guest, 42).toCompletableFuture().join());
        System.out.println("Inactive Alice: "
            + demo.authorizeRead(inactive, 42).toCompletableFuture().join());
    }
}
```

Biên dịch và chạy bằng JDK 17 trở lên:

```bash
javac AsyncPermissionDemo.java
java AsyncPermissionDemo
```

Stdout chính xác:

```text
Alice owns 42: ALLOW
Bob same tenant, not owner: DENY
Alice cross tenant 77: DENY
Carol owns 77: ALLOW
Alice deleted 90: DENY
Guest no authority: DENY
Inactive Alice: DENY
```

Giải thích:

- Alice có authority, membership tenant A, owner của Document 42 và document chưa deleted → ALLOW.
- Bob có quyền chức năng READ và cùng tenant nhưng không sở hữu Document 42, không có share grant trong mô hình → DENY.
- Alice không thể đọc Document 77 thuộc tenant B dù biết ID.
- Carol sở hữu Document 77 trong tenant B và có membership, nên ALLOW.
- Tài liệu deleted, actor thiếu authority hoặc inactive bị DENY.
- `thenCompose` chờ kết quả membership trước khi yêu cầu kiểm tra owner. `exceptionally(...)` trong demo chọn DENY để mô tả fail closed; production phải ghi và phân loại lỗi hạ tầng, không chỉ nuốt mọi exception.

**Giới hạn đặc biệt:** `CompletableFuture.completedFuture(...)` trong ví dụ mô phỏng nguồn đã có sẵn trong memory, **không chứng minh một database driver đang non-blocking**. Muốn kiểm thử I/O thật, dùng R2DBC hoặc WebClient và công cụ giám sát event loop. Ví dụ cũng cố ý mô hình **owner-only**; khi có ACL/share grants, phải bổ sung đúng điều kiện.

## 20. Kiểm thử với StepVerifier

`StepVerifier` trong `reactor-test` giúp kiểm tra giá trị, completion, error và thời gian theo pipeline thực.

Ví dụ unit test policy trả deny:

```java
import reactor.test.StepVerifier;

StepVerifier.create(
    reactiveDocumentPolicy.canRead(authAlice, "tenant-b", 42L)
)
    .expectNext(false)
    .verifyComplete();
```

Đây là **JUnit fragment**: cần `authAlice`, repositories/subject resolver test doubles và `reactor-test`. Test phải có fixtures phân biệt tenant A/B, owner khác nhau và authority cụ thể.

### Kiểm tra empty

```java
Mono<Boolean> noMembership = Mono.empty();

StepVerifier.create(noMembership.defaultIfEmpty(false))
    .expectNext(false)
    .verifyComplete();
```

### Kiểm tra error

```java
Mono<Boolean> dbFailed =
    Mono.error(new IllegalStateException("R2DBC unavailable"));

StepVerifier.create(dbFailed)
    .expectError(IllegalStateException.class)
    .verify();
```

Ở tầng policy có thể để error đi lên; tại HTTP boundary phải bảo đảm request **không được xử lý như ALLOW**. Test 503/5xx hay denial theo contract tương ứng.

### Virtual time và timeout

Với nguồn delay mẫu:

```java
import java.time.Duration;
import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;

StepVerifier.withVirtualTime(() ->
    Mono.delay(Duration.ofSeconds(10))
        .map(n -> true)
        .timeout(Duration.ofSeconds(2))
)
    .expectSubscription()
    .thenAwait(Duration.ofSeconds(2))
    .expectError(java.util.concurrent.TimeoutException.class)
    .verify();
```

Đây là test mẫu kiểm tra Reactor timeout bằng virtual scheduler; không dùng `Thread.sleep`. Với HTTP client/DB driver thực, cần integration test riêng; virtual time không thể thay thế socket, connection pool hay network timing tests.

### Test không gọi resource query sau membership deny

Có thể dùng mock/spy repository và verify `documents.exists...` **không được gọi** khi membership trả false. Điều này giúp phát hiện một policy đọc tài nguyên ngoài tenant trước khi xác minh membership, có nguy cơ leak qua timing/logs hoặc làm quá tải I/O.

## 21. WebTestClient: kiểm tra filter chain thực

Chỉ test trực tiếp `ReactiveDocumentPolicy.canRead(...)` chưa đủ. Có thể policy đúng nhưng:

- `SecurityWebFilterChain` không được đăng ký hoặc matcher không khớp.
- Endpoint mới không dùng `access(documentRead)`.
- Rule `permitAll` ở trước đã bắt toàn bộ `/api/**`.
- Một chain rộng có `@Order` cao hơn làm chain chứa policy không được chọn.
- Controller khác gọi repository trực tiếp.
- JWT authority mapping không có `document:read`.
- Path variable `documentId` parse sai hoặc thiếu `tenantId`.

Dùng `WebTestClient` với Spring Security WebFilter chain thật.

### Thiết lập trong application context

```java
import org.junit.jupiter.api.BeforeEach;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.context.ApplicationContext;
import org.springframework.test.web.reactive.server.WebTestClient;

import static org.springframework.security.test.web.reactive.server
    .SecurityMockServerConfigurers.springSecurity;

public class DocumentAuthorizationIntegrationTest {
    @Autowired ApplicationContext context;
    WebTestClient client;

    @BeforeEach
    void setup() {
        client = WebTestClient.bindToApplicationContext(context)
            .apply(springSecurity())
            .configureClient()
            .build();
    }
}
```

Đây là **test class fragment**, cần Spring test context, controllers, repositories và `spring-security-test` thực sự được load. Nếu dùng `@SpringBootTest` có server thật, có thể dùng `WebTestClient` được auto-configure cho web environment phù hợp.

### Mock JWT để test authorization logic

```java
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import static org.springframework.security.test.web.reactive.server
    .SecurityMockServerConfigurers.mockJwt;

client.mutateWith(mockJwt().authorities(
        new SimpleGrantedAuthority("document:read")))
    .get()
    .uri("/api/tenants/tenant-a/documents/42")
    .exchange()
    .expectStatus().isOk();
```

**Fragment:** test kỳ vọng 200 **chỉ khi** có controller/handler thật, subject mapping đúng, membership+owner/ACL fixture cho phép và JWT mock được chuyển thành identity mà `SubjectResolver` hiểu. Với mockJwt, Authentication/subject có thể khác user internal ID, cần set claim `sub` phù hợp.

`mockJwt()` **không chứng minh** chữ ký, issuer, audience hay `exp` thật được decoder xác minh. Cần thêm integration test Resource Server với JWT/decoder thật cho nhóm đó.

### Test deny không đọc dữ liệu

Khi user thiếu quyền, ngoài status 403/404 còn phải assert:

- Không trả body tài liệu nhạy cảm.
- Không gọi downstream controller/service action bị bảo vệ nếu denial ở filter.
- Không phát email/event hay ghi DB.
- Không có presigned URL được cấp.
- Không có cache response của user khác.
- Không có exception body lộ tenant/owner/SQL.

## 22. Ma trận kiểm thử tối thiểu

| Actor | Tenant được yêu cầu | Document | Data permission | Kỳ vọng |
| --- | --- | --- | --- | --- |
| Alice | A | Doc42, Alice là owner | Membership active, READ | ALLOW |
| Bob | A | Doc42, Bob không phải owner | Membership active, không share | DENY |
| Carol | B | Doc42 thuộc A | Có READ ở B | DENY |
| Alice | C | Doc42 thuộc A | Không membership C | DENY |
| Alice | A | Doc42 | Membership revoked | DENY |
| Alice | A | Doc42 | Đúng authority, resource deleted | DENY |
| Guest | A | Doc42 | Không authenticated | DENY |
| Alice | A | Doc42 | Không `document:read` authority | DENY |
| Alice | A | Doc42 | Grant READ hết hạn, không owner | DENY |
| Alice | A | Doc42 | Grant revoked, không owner | DENY |
| Alice | A | Doc42 | R2DBC timeout | Không ALLOW; error/5xx theo policy |
| Alice | A | Doc42 | Remote PDP trả empty/malformed | Không ALLOW |
| Alice | A | Doc42 | Cache ALLOW của Bob | Không reuse dữ liệu của Bob |
| Alice | A | Doc42 | JWT signature/issuer sai | Authentication failure |
| Alice | A | Doc42 | Hai request concurrent trên một event loop | Không blocking/deadlock |
| Alice | A | Doc42 | DB connection pool cạn | Không fail-open, metric/timeout |
| Alice | A | Doc42 | Tenant ID bị đổi trong path | Xác minh membership lại |
| Alice | A | Doc42 | Service trực tiếp ngoài HTTP | Policy ở service/data không bypass |

Cần test cả **từng action** READ/EDIT/DELETE/EXPORT, không giả định việc được READ sẽ cho phép mọi thao tác. Với WRITE, transaction và conditional update là hàng rào quan trọng chống race sau pre-check.

## 23. Hiệu năng và độ bền khi tải lớn

### Chi phí một quyết định

Một pipeline nhiều bước:

```text
JWT parsing (local)
  -> membership query (R2DBC)
  -> document query (R2DBC)
  -> share grant query (R2DBC)
  -> remote PDP WebClient
  -> business query
```

Ngay cả khi từng bước non-blocking, tổng latency có thể cao. Tùy policy nên:

1. Thực hiện coarse checks sớm (authentication, authority).
2. Dùng một truy vấn `EXISTS` có điều kiện tenant/ACL nếu có thể.
3. Index các khóa `tenant_id, subject_id, document_id, permission` phù hợp.
4. Tránh N+1 queries khi danh sách có nhiều object.
5. Batch decisions với PIP/PDP nếu dữ liệu cho phép và security semantics rõ.
6. Ghi đo p50/p95/p99 của authorization, không chỉ thời gian controller.
7. Giới hạn concurrency, connection pool và response size.
8. Có timeout và circuit breaker cho remote PDP, **không fail-open**.
9. Cache an toàn với invalidation khi quyền đổi.
10. Thường xuyên chạy load test/cancellation test với nhiều user/tenant.

### Một truy vấn cho một batch object

Nếu UI hiển thị 200 documents, không nhất thiết gọi 200 lần `canRead`, mỗi lần 2–3 query riêng. Có thể xây một query tenant-scoped trả **chỉ các document được phép đọc** rồi phân trang trên tập đã lọc; hoặc bulk fetch ACL/facts trong một operation. Khi pagination, filter authorization **trước khi tính count/page**.

**Rủi ro:** load toàn bộ documents của tenant rồi `filter` trong Java sau pagination có thể làm lộ số lượng, giảm hiệu năng, bỏ sót object đã lọc và tạo inconsistent counts.

### Reactive không thay thế giới hạn nguồn lực

Trong WebFlux, `flatMap` có thể tạo concurrency lớn. `flatMap(mapper, concurrency)`, `concatMap` hoặc bounded concurrency có thể giúp điều tiết batch, nhưng không phải rule "càng nhiều request cùng lúc càng tốt". Kiểm tra DB pool, CPU dùng để verify JWT và remote PDP capacity.

## 24. Lỗi thường gặp và cách sửa

| Sai lầm | Rủi ro | Cách sửa |
| --- | --- | --- |
| Gọi `.block()` trong custom authorization | Chặn event loop, giảm throughput | Trả `Mono<AuthorizationResult>`/`Mono<Boolean>` |
| Bọc JDBC bằng `Mono.just(...)` | Blocking xảy ra trước subscribe | R2DBC hoặc `fromCallable(...).subscribeOn(boundedElastic())` nếu di trú |
| Tự `subscribe()` rồi trả true | Quyền chưa đọc xong đã ALLOW | Nối publisher vào manager bằng `flatMap`/`map` |
| Dùng `subscribeOn(boundedElastic())` và gọi nó "non-blocking DB" | Hiểu nhầm năng lực hệ thống | Phân biệt offload blocking và native R2DBC |
| `Mono.empty()` được coi như true | Không có permission vẫn allow | `defaultIfEmpty(false)` ở boundary |
| `onErrorReturn(true)` cho lỗi PDP | Fail-open | Deny/5xx, audit dependency failure |
| Catch mọi DB exception rồi trả "user không có quyền" | Mất observability | Phân loại lỗi hạ tầng và denial |
| Chỉ đọc `Authentication.getAuthorities()` | Không biết owner, tenant, grant | Query object/membership server-side |
| Tin `tenantId` trong URL/header | Client tự đổi tenant | Xác minh membership trước khi query |
| Dùng `findById` rộng rồi trả dữ liệu | BOLA/IDOR | Tenant-scoped repository + policy |
| Share grant READ dùng cho EDIT | Leo thang quyền | Action-specific permission |
| TTL JWT được xem là TTL ACL | Grant revoked vẫn sống | Đọc grant current state hoặc versioned cache |
| Cache `Mono<Boolean>` ở singleton không có key | Dùng ALLOW của user khác | Cache theo identity/tenant/action/resource/version hoặc không cache |
| Dùng `Flux.collectList()` mọi ACL | Memory cao, N+1 | Scoped `exists`/SQL và index |
| Gọi remote PDP bằng `RestTemplate` trực tiếp | Blocking HTTP | `WebClient` với timeout |
| Forward raw user JWT tới mọi service | Lộ credential | Service-to-service auth / token exchange đúng audience |
| Policy remote trả ALLOW nhưng resource/tenant không khớp | Cross-tenant access | Verify input/result context, data-scoped query |
| Đặt quyền chỉ ở HTTP matcher | Worker/GraphQL bypass | Policy ở service/domain và DB |
| Dùng Reactor `ThreadLocal` tenant cũ | Context lẫn giữa request | VerifiedTenantScope bất biến, Reactor Context có kiểm soát |
| `@PreAuthorize` reactive bean gọi blocking | Nghẽn reactor | Bean trả reactive result, không `block()` |
| `@PostAuthorize` cho write | Side effects có thể đã xảy ra | Precheck + conditional mutation |
| Chỉ unit test mockJwt rồi cho rằng signature verified | Test thiếu decoder/issuer/audience | JWT integration tests |
| Không test timeout/empty/cancellation | Quyền bị cấp sai ở failure mode | Negative/failure-injection tests |
| Không test connection pool/event loop | Non-blocking giả tạo | Load tests, metrics, BlockHound khi phù hợp |

## 25. Checklist triển khai non-blocking authorization

1. **Nguồn permission thật là gì?** Membership, ACL, owner, share grant hay remote PDP?
2. **I/O API thực sự reactive chưa?** R2DBC/WebClient hay JDBC được bọc mỏng?
3. **Có `.block()`, `Future.get()`, `join()` trong đường HTTP không?** Loại bỏ.
4. **Authentication được truyền thế nào?** Mono từ security filter hoặc Reactor Context, không ThreadLocal mơ hồ.
5. **Tenant ID có được xác minh membership trước khi dùng không?**
6. **Resource đúng ID/type/tenant/status được lấy từ server chưa?**
7. **Action READ/EDIT/DELETE/EXPORT có phân biệt rõ không?**
8. **Empty có mặc định deny không?** Không coi missing evidence là success.
9. **Error/timeout có fail closed và alert không?**
10. **WebClient có service authentication, đúng audience và TLS không?**
11. **Có cancellation, timeouts, pool limits và bulkheads không?**
12. **Cache có key subject/tenant/resource/action/policy/version không?**
13. **Revocation/expiry có hiệu lực theo SLA không?**
14. **Database query có tenant predicate và index phù hợp không?**
15. **Mutation có chống TOCTOU/transaction strategy phù hợp không?**
16. **Có bảo vệ service trực tiếp ngoài HTTP không?**
17. **`ReactiveAuthorizationManager` dùng đúng API của Spring Security version chưa?**
18. **Đã test `Mono.empty`, `Mono.error` và timeout chưa?**
19. **`WebTestClient` có filter chain thật không?**
20. **Có test cross-tenant, role bleed, JWT invalid, cache stale, bulk access không?**
21. **Theo dõi p95/p99 authorization latency và pool saturation chưa?**
22. **Có log audit an toàn không lộ JWT, secret hoặc dữ liệu tài liệu không?**

**Kết luận:** Trong Spring Security WebFlux, quyền nằm ở DB hoặc dịch vụ bên ngoài phải được đọc và kết hợp **bằng một pipeline reactive mà filter chain thực sự chờ quyết định**. Sử dụng R2DBC, `WebClient`, `Mono`, `ReactiveAuthorizationManager` và Reactor Context theo cách không blocking; bảo đảm quyền có phạm vi subject–tenant–resource–action, kết quả empty/error **không cấp quyền**, và kiểm thử cả chức năng lẫn failure modes. Non-blocking giúp dùng tài nguyên hiệu quả hơn, **không tự tạo authorization đúng** nếu đầu vào/tenant/object policy hoặc consistency sai.

## Tài liệu tham khảo chính thức

- [Spring Security — Reactive Authorize ServerHttpRequest](https://docs.spring.io/spring-security/reference/7.0/reactive/authorization/authorize-http-requests.html): `authorizeExchange`, `access(...)`, custom ReactiveAuthorizationManager.
- [Spring Security — EnableReactiveMethodSecurity](https://docs.spring.io/spring-security/reference/7.0/reactive/authorization/method.html): Reactor Context, `@EnableReactiveMethodSecurity` và bean trả `Mono<Boolean>`.
- [Spring Security API — ReactiveAuthorizationManager](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/authorization/ReactiveAuthorizationManager.html): `authorize(Mono<Authentication>, T)` và kiểu `AuthorizationResult`.
- [Spring Security API — AuthorizationDecision](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/authorization/AuthorizationDecision.html): kết quả GRANT/DENY, `isGranted`.
- [Spring Security — Reactive WebTestClient Integration](https://docs.spring.io/spring-security/reference/reactive/test/web/setup.html): tích hợp filter chain vào WebTestClient.
- [Spring Security — Reactive OAuth2/JWT Test](https://docs.spring.io/spring-security/reference/reactive/test/web/oauth2.html): `mockJwt`, phân biệt mock với JWT decoder thật.
- [Spring Data R2DBC — Repositories](https://docs.spring.io/spring-data/relational/reference/r2dbc/repositories.html): `ReactiveCrudRepository`, query methods và `StepVerifier`.
- [Spring Data R2DBC — Reference Guide](https://docs.spring.io/spring-data/relational/reference/r2dbc.html): R2DBC query/mapping/transactions.
- [Spring Framework — WebClient retrieve](https://docs.spring.io/spring-framework/reference/web/webflux-webclient/client-retrieve.html): `retrieve`, `bodyToMono` và xử lý 4xx/5xx.
- [Spring Framework — Reactive Transactions](https://docs.spring.io/spring-framework/reference/data-access/transaction/programmatic.html): `TransactionalOperator` và reactive transaction boundaries.
- [Project Reactor — Reference Guide](https://projectreactor.io/docs/core/release/reference/): `Mono`/`Flux`, schedulers, error handling, context, timeout và `StepVerifier`.
- [OWASP — Authorization Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Authorization_Cheat_Sheet.html): deny by default, least privilege và object-level authorization.
- [OWASP API Security — Broken Object Level Authorization](https://api-security.owasp.org/editions/2023/en/0xa1-broken-object-level-authorization/): kiểm tra quyền trên mỗi object ID.
