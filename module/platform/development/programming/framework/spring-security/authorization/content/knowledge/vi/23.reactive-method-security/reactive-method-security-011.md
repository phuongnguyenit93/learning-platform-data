# Ranh giới giữa bảo vệ phương thức và bảo vệ dữ liệu phát ra trong Spring Security Reactive

## 1. Bài toán: cho phép gọi hàm chưa chắc được phép nhận từng bản ghi

Giả sử Alice được sử dụng chức năng xem tài liệu. API WebFlux gọi một service trả về `Flux<DocumentView>` chứa nhiều tài liệu. Annotation sau kiểm tra được một điều kiện **ở cấp phương thức**:

```java
@PreAuthorize("hasAuthority('document:read')")
public Flux<DocumentView> listDocuments() {
    return documentRepository.findAll()
        .map(DocumentView::from);
}
```

Alice có authority `document:read` nên lời gọi có thể vượt qua rào chắn. Nhưng `findAll()` có thể phát cả tài liệu thuộc Bob hoặc tenant khác. **Được phép thực thi phương thức** không có nghĩa **mọi giá trị phương thức phát ra** đều được phép gửi cho caller.

Đây là ranh giới cốt lõi của bài học thuộc chủ đề **Method security Reactive**:

- **Invocation authorization:** có được gọi phương thức `listDocuments` hay không?
- **Result authorization:** giá trị được trả về có được tiết lộ cho caller hay không?
- **Per-element authorization:** mỗi phần tử của `Flux` có phù hợp quyền của caller không?
- **Data-source authorization:** chính database/search/file store chỉ lựa chọn dữ liệu caller được phép nhìn thấy hay chưa?
- **Output authorization:** dữ liệu thực sự rời ứng dụng qua HTTP body, SSE, WebSocket hay một sink khác có được giới hạn đúng không?

Năm lớp trên có liên quan nhưng **không thể tự thay thế nhau**. Spring Security cung cấp `@PreAuthorize`, `@PostAuthorize`, `@PostFilter` và các reactive method interceptors; ứng dụng vẫn cần thiết kế truy vấn theo tenant, object-level permission, field-level projection, bảo mật streaming và kiểm thử việc **không có dữ liệu trái quyền được phát ra**.

### Kết quả cần đạt

Sau bài này, người học có thể:

1. Nêu rõ điều gì được và không được bảo vệ bởi `@PreAuthorize` với `Mono` và `Flux`.
2. Phân biệt `@PostAuthorize`, `@PostFilter`, `Flux.filterWhen` và lọc ngay trong SQL.
3. Giải thích thời điểm method invocation, subscription, emission và HTTP serialization.
4. Thiết kế REST detail, list, search, pagination và streaming theo đúng phạm vi dữ liệu được đọc.
5. Biết vì sao hậu kiểm không phù hợp để bảo vệ thao tác ghi đã có side effect.
6. Giữ `Authentication`/tenant trong Reactor Context, tránh bypass Spring AOP proxy.
7. Kiểm thử số lượng, nội dung, thứ tự, lỗi và dữ liệu nhạy cảm của từng phần tử phát ra.
8. Chạy ví dụ Java 17 độc lập minh họa phương thức được phép nhưng tập dữ liệu trả ra vẫn cần lọc.

## 2. Đặc thù Reactive: phương thức trả Publisher chứ chưa chắc đã chạy I/O

Trong Reactor, `Mono<T>` biểu diễn tối đa một giá trị còn `Flux<T>` biểu diễn 0..N giá trị. Nhiều Publisher là **cold**: việc tạo và trả `Flux` không đồng nghĩa truy vấn DB đã chạy; truy vấn thường chạy khi subscriber đăng ký.

Sơ đồ khái niệm:

```text
HTTP request đã xác thực
        |
        v
Spring-managed service proxy
        |
        v
@PreAuthorize -> kiểm tra có thể gọi method?
        |
   DENY +---> không cho thực hiện pipeline bảo vệ
        |
      ALLOW
        |
        v
Service trả Mono<T> / Flux<T>
        |
        v
Subscriber bắt đầu nhận dữ liệu
        |
        v
DB / remote source phát các item
        |
        +--> @PostAuthorize / @PostFilter / operator app (nếu có)
        |
        v
DTO serialization / HTTP response / SSE
```

Đây là mô hình tư duy, **không phải biểu đồ thứ tự AOP chính xác đến mọi signal trên mọi phiên bản**. Cấu hình và kiểu return quyết định chính xác việc kiểm tra reactive được ghép vào publisher như thế nào. Các khẳng định cần kiểm thử ở mức integration thay vì phỏng đoán rằng code trong method đã chạy toàn bộ trước khi annotation được đánh giá.

### Phân biệt bốn mốc

| Mốc | Ý nghĩa | Điều dễ nhầm |
| --- | --- | --- |
| **Invocation** | Gọi method qua Spring proxy | Không đồng nghĩa đã có dữ liệu từ DB |
| **Publisher assembly** | Xây chuỗi operator và return Publisher | Một số tác vụ ngoài Publisher có thể chạy ngay |
| **Subscription / request demand** | Framework subscribe và yêu cầu phần tử | I/O cold Publisher thường bắt đầu |
| **Emission / serialization** | Item được gửi tới subscriber/HTTP body | Item đã gửi thì không thể "thu hồi" khỏi client |

Với `Flux` dài hoặc SSE, có thể có **nhiều giây hoặc nhiều phút** giữa item đầu và item cuối. Quyền của caller có thể bị thu hồi trong khoảng này. Một lần cho phép ở đầu stream không mặc định có nghĩa các phần tử tương lai vẫn hợp lệ theo yêu cầu nghiệp vụ.

### Ví dụ một bug từ Publisher assembly

```java
public Mono<Document> wrong(Long id) {
    auditRepository.saveBlocking("READ_ATTEMPT"); // chạy đồng bộ ngay
    return documents.findById(id);
}
```

Đây là **anti-pattern**: side effect xảy ra khi method body chạy, không nằm trong nguồn reactive để được transaction/cancellation quản lý. Không nghĩ chỉ vì method trả `Mono` thì tất cả code của nó sẽ tự chờ subscription. Với WebFlux, blocking call còn có thể làm nghẽn event loop.

## 3. Các cơ chế được Spring Security cung cấp

Tài liệu Spring Security Reactive mô tả method security dựa vào `ReactiveSecurityContextHolder`, Reactor Context và Spring AOP. Trong các dòng Spring Security hỗ trợ, có thể bật:

```java
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.method.configuration.EnableReactiveMethodSecurity;

@Configuration
@EnableReactiveMethodSecurity(useAuthorizationManager = true)
public class ReactiveMethodSecurityConfig {
}
```

**Điều kiện:** project đang dùng dependency Spring Security phù hợp với API này. Tài liệu chính thức nêu `useAuthorizationManager=true` được hỗ trợ từ Spring Security 5.8. Với phiên bản cụ thể, đọc Javadoc và chạy compile tests; một số API/cú pháp customization có khác biệt giữa 6.x và 7.x.

Các annotation chính:

| Annotation | Tầng kiểm soát | Phạm vi điển hình |
| --- | --- | --- |
| `@PreAuthorize` | Trước khi cho phép tiến vào invocation/pipeline | Principal có role/action/permission cần thiết |
| `@PostAuthorize` | Hậu kiểm đối với kết quả method | Quyền trên đối tượng trả về, ví dụ owner |
| `@PreFilter` | Lọc các phần tử trong input được hỗ trợ | Một batch input có thể chứa object không hợp lệ |
| `@PostFilter` | Lọc phần tử trong tập kết quả được hỗ trợ | Bỏ những item caller không được xem |
| Policy reactive trong service | Chủ động quyết định lúc chạy Publisher | Phức hợp membership, ACL, time, tenant, trạng thái |
| Repository scoped query | Ràng buộc ngay khi đọc DB | Chỉ lấy dữ liệu thuộc scope và đủ quyền |
| Response DTO | Bảo vệ thuộc tính phát ra | Không tiết lộ trường nội bộ nhạy cảm |

**Cần phân biệt:** `@PreAuthorize` dùng để cho phép gọi method, còn `@PostFilter` theo hợp đồng filtering có mục đích lọc các item; **đừng coi `@PostAuthorize` là cách tự động phân trang/lọc mọi phần tử trong Flux**. Reactive interceptor implementations có hỗ trợ theo phiên bản, nhưng phải viết integration test cho **đúng kiểu return (`Mono`, `Flux`, collection) và annotation** mà dự án đang dùng.

Tài liệu Spring Security gần đây liệt kê `AuthorizationManagerBeforeReactiveMethodInterceptor`, `AuthorizationManagerAfterReactiveMethodInterceptor` và `PostFilterAuthorizationReactiveMethodInterceptor` khi bật mode AuthorizationManager. Điều đó khẳng định có cơ chế, nhưng **không đảm bảo một biểu thức cụ thể đã phù hợp domain/tenant**.

### Khi nào nên dùng gì?

- **Trước khi gọi:** yêu cầu user đã authenticated và có authority chức năng (`@PreAuthorize`).
- **Một đối tượng:** kiểm tra ID/tenant ở query và có thể hậu kiểm owner/ACL với `@PostAuthorize` như lớp bổ sung.
- **Danh sách lớn:** query DB đã giới hạn quyền **trước khi phân trang**, thay vì tải mọi object rồi `@PostFilter`.
- **Danh sách nhỏ đã nằm trong memory:** `@PostFilter` có thể hữu ích nếu tương thích return type/version.
- **Flux lâu dài:** xét từng item/nhóm item và yêu cầu về revoke, cancellation, error/partial response.
- **Mutation:** pre-check + conditional database update/transaction; không dựa vào `@PostAuthorize` để ngăn side effects.

## 4. Câu hỏi quan trọng: đang bảo vệ phương thức hay từng item?

Đoạn sau thể hiện đúng **coarse-grained permission** nhưng thiếu data authorization:

```java
@PreAuthorize("hasAuthority('document:read')")
public Flux<DocumentView> allDocuments() {
    return documents.findAll()
        .map(this::toView);
}
```

Nếu `findAll()` phát 100 bản ghi của nhiều tenant, phép kiểm tra role không loại bản ghi nào. Một principal có `document:read` chỉ có quyền dùng chức năng đọc theo policy — không nhất thiết sở hữu/được chia sẻ mọi document.

Thêm `@PreAuthorize("hasRole('ADMIN')")` có thể chặn những user không phải ADMIN, nhưng nếu ADMIN chỉ có thẩm quyền **trong tenant A** thì vẫn có nguy cơ rò tenant B.

Cần mô hình quyết định:

```text
canView(subject, document, READ, context) =
    authenticated(subject)
    AND accountActive(subject)
    AND memberOf(subject, verifiedTenant)
    AND hasTenantAction(subject, verifiedTenant, READ)
    AND document.tenantId == verifiedTenant
    AND document.active
    AND (owner(subject, document) OR activeReadGrant(subject, document))
```

Một màn hình danh sách phải trả **chỉ các document thỏa phép toán này**, không chỉ có `document:read` trong danh sách authorities.

### Subject và resource facts phải đáng tin

- Subject lấy từ `Authentication` đã xác minh, không từ `X-User-Id` do client gửi.
- Tenant chọn trong URL/header là **selector**, phải xác minh membership trước khi dùng.
- Owner/tenant/status của Document lấy từ database hoặc nguồn resource tin cậy, không từ JSON client.
- Share grants phải kiểm tra đúng recipient, object, action, thời hạn và revoke.
- Nếu một điều kiện bắt buộc không xác minh được, **không cấp quyền** chỉ vì upstream service timeout.

## 5. @PreAuthorize trong reactive service: bảo vệ cửa vào

Một cấu hình HTTP coarse-grained:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.web.server.SecurityWebFilterChain;

@Configuration
@EnableWebFluxSecurity
class HttpSecurityConfig {
    @Bean
    SecurityWebFilterChain apiChain(ServerHttpSecurity http) {
        return http
            .authorizeExchange(exchanges -> exchanges
                .pathMatchers("/api/documents/**").authenticated()
                .anyExchange().denyAll()
            )
            .build();
    }
}
```

Đây là **config fragment** cho WebFlux, chưa cấu hình JWT/HTTP Basic/CSRF/CORS, cần nối authentication cơ chế của dự án. `authenticated()` ở đây chỉ là coarse rule ở HTTP layer.

Service:

```java
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.stereotype.Service;
import reactor.core.publisher.Flux;

@Service
class DocumentService {
    private final DocumentRepository repository;

    DocumentService(DocumentRepository repository) {
        this.repository = repository;
    }

    @PreAuthorize("hasAuthority('document:read')")
    Flux<DocumentView> listDocuments() {
        return repository.findAll()
            .map(d -> new DocumentView(d.getId(), d.getTitle()));
    }
}
```

**Đây là ví dụ cố ý thiếu kiểm tra data scope**, không được đưa nguyên vào production. Cần entity/repository/DTO, và method có thể phải `public` tùy cách proxy/đường gọi; ở code trên method package-private dễ phụ thuộc class/proxy behavior, vì vậy phiên bản service an toàn bên dưới dùng method `public` rõ ràng.

### Hậu quả của hiểu nhầm

Nếu QA chỉ kiểm tra:

```text
Anonymous -> 401
Alice có document:read -> 200
Bob không có document:read -> 403
```

thì có thể endpoint vẫn rò Document của tenant khác trong body `200`. Test chính xác phải kiểm tra **danh sách IDs, tenant IDs, field projection và những dữ liệu không xuất hiện**. Chỉ assert status không đủ.

## 6. @PostAuthorize: hậu kiểm một đối tượng, nhưng đừng dùng để bảo vệ write

Với một object đơn như `Mono<DocumentView>`, có thể định nghĩa thêm hậu kiểm:

```java
import org.springframework.security.access.prepost.PostAuthorize;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.stereotype.Service;
import reactor.core.publisher.Mono;

@Service
public class OwnedDocumentService {
    private final DocumentRepository documents;

    public OwnedDocumentService(DocumentRepository documents) {
        this.documents = documents;
    }

    @PreAuthorize("hasAuthority('document:read')")
    @PostAuthorize("returnObject.ownerSubjectId == authentication.name")
    public Mono<DocumentView> read(Long documentId) {
        return documents.findById(documentId)
            .map(d -> new DocumentView(
                d.getId(), d.getTenantId(),
                d.getOwnerSubjectId(), d.getTitle()));
    }
}
```

**Thành phần Spring minh họa**: cần entity, repository, DTO và cấu hình reactive method security, và `DocumentView` phải có property `ownerSubjectId` được SpEL truy cập theo mapping thực. Với record, accessor/mapping phải được kiểm thử; trong dự án có thể dùng getter JavaBean hoặc bean policy. Nếu `authentication.name` không trùng ID nội bộ, biểu thức owner sẽ sai; nên map subject ID rõ ràng.

Ý nghĩa mong muốn: chỉ trả object nếu owner là caller. Nhưng vẫn tồn tại ba vấn đề:

1. **Repository đã tải object trước hậu kiểm.** Điều này có thể cần thiết để đọc owner, song dữ liệu không nên bị ghi log, cache shared hoặc gửi ra sink khác trước khi kiểm tra.
2. **Thiếu tenant scope.** Một owner trùng ID/issuer string hoặc một document thuộc tenant khác có thể đi qua nếu logic quá đơn giản.
3. **Side effects.** Hậu kiểm không hoàn tác các hành động đã xảy ra trước đó, đặc biệt INSERT/UPDATE/DELETE, event, email hoặc storage upload.

Cách chắc chắn hơn cho detail là query **đúng tenant + owner/ACL** ngay từ repository, chỉ map sang DTO sau khi quyền được chứng minh. `@PostAuthorize` có thể đóng vai defense in depth cho kết quả nhưng **không nên là hàng rào duy nhất** cho data-access nhạy cảm.

### Anti-pattern: ghi trước, hậu kiểm sau

```java
@PostAuthorize("returnObject.ownerSubjectId == authentication.name")
public Mono<DocumentView> changeTitle(
        Long documentId, String newTitle) {
    return repository.updateTitle(documentId, newTitle)
        .map(this::toView);
}
```

Nếu update đã commit hoặc event đã phát trong upstream, hậu kiểm thất bại **không có nghĩa** database tự rollback. Việc reactive chain có transaction hay không phụ thuộc boundaries/isolation thực tế; không dựa vào annotation để ngăn một write trái quyền.

**Đúng hướng:** xác minh quyền **trước mutation**, và giữ điều kiện bảo mật trong lệnh cập nhật/transaction khi có race.

## 7. @PostFilter: lọc tập kết quả, không phải query optimizer

`@PostFilter` định nghĩa biểu thức cho từng phần tử được xem xét. Trong reactive method-security mode mới, Spring Security có `PostFilterAuthorizationReactiveMethodInterceptor`; behavior cụ thể với `Flux`/collection cần kiểm tra theo phiên bản runtime.

Ví dụ ý tưởng:

```java
import org.springframework.security.access.prepost.PostFilter;
import org.springframework.security.access.prepost.PreAuthorize;
import reactor.core.publisher.Flux;

@PreAuthorize("hasAuthority('document:read')")
@PostFilter(
    "filterObject.ownerSubjectId == authentication.name"
)
public Flux<DocumentView> myOwnedDocuments() {
    return repository.findAll()
        .map(this::toView);
}
```

Đây là **method fragment** cần nằm trong Spring-managed service, có imports/DTO/repository và `@EnableReactiveMethodSecurity(useAuthorizationManager=true)` tương thích. Test `Flux` output để chắc chắn annotation được áp đúng, không giả định từ ví dụ Servlet. Với role/ACL thực tế, biểu thức **chỉ so owner** còn thiếu tenant, membership, share grants, trạng thái object.

### Hạn chế nghiêm trọng của hậu lọc

Giả sử database có 1.000.000 tài liệu, nhưng Alice chỉ xem được 10.

Nếu load toàn bộ rồi lọc:

```text
DB -> 1.000.000 rows -> JVM / Flux -> filter -> 10 rows
```

Điều đó:

- Tạo I/O, CPU và memory cost không cần thiết.
- Có thể đưa dữ liệu không có quyền đến tầng application, logs, metrics hoặc cache trước khi filter.
- Tạo N+1 query nếu mỗi item lại tra ACL riêng.
- Với `LIMIT 20` được áp **trước** filter, có thể chỉ còn 0–2 item sau lọc dù page có nhiều object hợp lệ ở phía sau.
- Pagination count/totalElements có thể lộ số tài liệu không được phép.
- Sort/aggregation/search facets có thể thống kê dữ liệu ngoài scope.
- Không giải quyết per-field redaction.
- Khi nguồn là stream dài, việc lọc per-item vẫn tiêu tốn bandwidth upstream.

**Kết luận:** `@PostFilter` là **hàng rào bổ sung** cho một số tập dữ liệu nhỏ, không phải cách thay thế tenant/owner/ACL predicates ở tầng database.

## 8. Bộ ba hướng thiết kế cho Mono, Flux và dữ liệu lớn

| Kiểu kết quả | Cách kiểm soát chính | Lớp bổ sung phù hợp |
| --- | --- | --- |
| `Mono<Document>` theo ID | Query bằng resource ID + verified tenant + owner/ACL | `@PreAuthorize`, `@PostAuthorize` hoặc service policy |
| `Flux<Document>` list | Query đã lọc quyền trước pagination | `@PreAuthorize`, kiểm tra per-element nơi cần |
| `Flux<Event>` SSE dài | Định nghĩa policy lúc subscribe và mỗi emission nếu cần | Cancellation/revoke signal, bounded cache |
| `Flux<ByteBuffer>` download | Chặn **trước khi bắt đầu gửi** file | Quota/expiry/rate limiting và stream-time policy |
| `Mono<PageDto>` | COUNT và SELECT đều có predicate quyền | Kiểm DTO/fields, total count |
| `Mono<CommandResult>` write | Pre-check + conditional SQL mutation | Transaction, optimistic/pessimistic locking |
| Message/WebSocket output | Authorization ở message/service layer | Recheck khi scope/token/grant đổi |

Không có một annotation xử lý hoàn hảo mọi loại stream. Quyền trên object có thể cố định trong một request hoặc có thể thay đổi từng giây tùy nghiệp vụ.

## 9. Reactive repository: lọc quyền ngay trong SQL/R2DBC

Giả sử bảng:

```text
tenant_memberships(
  tenant_id, subject_id, active, can_read_documents
)
documents(
  id, tenant_id, owner_subject_id, title, deleted, classification
)
document_share_grants(
  id, document_id, tenant_id, recipient_subject_id,
  permission, valid_from, expires_at, revoked_at
)
```

Một repository Spring Data R2DBC:

```java
import org.springframework.data.repository.reactive.ReactiveCrudRepository;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

public interface DocumentRepository
        extends ReactiveCrudRepository<DocumentEntity, Long> {

    Flux<DocumentEntity>
    findByTenantIdAndOwnerSubjectIdAndDeletedFalseOrderByIdAsc(
        String tenantId, String ownerSubjectId);

    Mono<DocumentEntity>
    findByIdAndTenantIdAndDeletedFalse(
        Long id, String tenantId);
}
```

Đây là **repository fragment** cần entity R2DBC `DocumentEntity` với các property tương ứng, connection factory và schema. `findByIdAndTenantIdAndDeletedFalse` chỉ thực hiện **tenant isolation**, chưa kiểm tra caller là owner nếu repository dùng trực tiếp từ mọi nơi. Domain service phải ràng buộc owner/ACL.

Một predicate tương đương cho owner list:

```sql
SELECT id, tenant_id, owner_subject_id, title
FROM documents
WHERE tenant_id = :verified_tenant
  AND owner_subject_id = :authenticated_subject
  AND deleted = FALSE
ORDER BY id;
```

**Quan trọng:** cả `:verified_tenant` và `:authenticated_subject` phải được tạo từ nguồn đã xác minh, truyền dưới dạng bind parameters. Client đổi `tenantId` trong path không được tự có quyền trên tenant mới.

### Khi có share grants

Một câu SQL có thể chọn cả tài liệu được chia sẻ READ còn hiệu lực:

```sql
SELECT d.id, d.tenant_id, d.owner_subject_id, d.title
FROM documents d
JOIN tenant_memberships m
  ON m.tenant_id = d.tenant_id
 AND m.subject_id = :subject
WHERE d.tenant_id = :verified_tenant
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
ORDER BY d.id
LIMIT :page_size OFFSET :offset;
```

Đây là **SQL logic**, không phải schema/framework được tạo tự động. Cần điều kiện `classification`/project/owner state nếu nghiệp vụ có, và đảm bảo unique membership hoặc xử lý duplicate rows. `:now_utc` lấy từ nguồn thời gian được tin cậy; mốc hết hạn không bao gồm vì dùng `expires_at > now`.

**Không dùng SQL query này để suy ra mọi user có membership READ đều được thấy toàn bộ tenant.** Nhánh cuối vẫn giới hạn owner hoặc share grant. Nếu product có folder-level ACL/group relationships, thêm các nhánh đó theo policy có kiểm soát.

### COUNT cũng phải dùng cùng predicate

```sql
SELECT COUNT(*)
FROM documents d
JOIN tenant_memberships m
  ON m.tenant_id = d.tenant_id
 AND m.subject_id = :subject
WHERE d.tenant_id = :verified_tenant
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
  );
```

Một list có 10 item hợp lệ nhưng totalElements=10.000.000 (toàn tenant) vẫn có thể tiết lộ thông tin. Query COUNT và query SELECT cần **cùng một scope policy**. Nếu hai query tách transaction, dữ liệu có thể đổi giữa hai thời điểm; ứng dụng phải chấp nhận/định nghĩa snapshot consistency phù hợp, không giả định count luôn bằng số bản ghi hiện tại.

## 10. Một service Reactive kiểm soát cả invocation lẫn data

Các đoạn sau là **thành phần Spring Boot WebFlux + Spring Security + R2DBC**, không phải một chương trình `javac` độc lập. Các bean `VerifiedSubjectService`, `TenantPermissionService`, `DocumentEntity` và `DocumentRepository` phải được ứng dụng cung cấp theo contract.

Một service kết hợp:

```java
import org.springframework.security.access.method.P;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.security.core.context.ReactiveSecurityContextHolder;
import org.springframework.stereotype.Service;
import reactor.core.publisher.Flux;

@Service
public class TenantDocumentReadService {
    private final VerifiedSubjectService subjects;
    private final TenantPermissionService tenantPermissions;
    private final DocumentRepository documents;

    public TenantDocumentReadService(
            VerifiedSubjectService subjects,
            TenantPermissionService tenantPermissions,
            DocumentRepository documents) {
        this.subjects = subjects;
        this.tenantPermissions = tenantPermissions;
        this.documents = documents;
    }

    @PreAuthorize("hasAuthority('document:read')")
    public Flux<DocumentView> listOwned(
            @P("tenantId") String tenantId) {

        return ReactiveSecurityContextHolder.getContext()
            .flatMap(ctx ->
                subjects.fromTrustedAuthentication(
                    ctx.getAuthentication()))
            .flatMapMany(subject ->
                tenantPermissions
                    .canReadTenant(
                        subject.subjectId(), tenantId)
                    .flatMapMany(allowed -> {
                        if (!allowed) {
                            return Flux.error(
                                new org.springframework.security.access.AccessDeniedException(
                                    "Tenant read denied"));
                        }

                        return documents
                            .findByTenantIdAndOwnerSubjectIdAndDeletedFalseOrderByIdAsc(
                                tenantId, subject.subjectId())
                            .map(doc -> new DocumentView(
                                doc.getId(), doc.getTitle()));
                    }))
            .switchIfEmpty(Flux.error(
                new org.springframework.security.access.AccessDeniedException(
                    "Missing trusted subject")));
    }

    public record DocumentView(Long id, String title) {}
}
```

**Ý nghĩa từng lớp:**

- `@PreAuthorize` yêu cầu authority chức năng. Nó không tự chọn tenant.
- `ReactiveSecurityContextHolder` đọc Authentication được WebFlux Security gắn vào Reactor Context.
- `VerifiedSubjectService` phải xác minh authenticated principal type, account status và subject ID, không tin request-supplied userId.
- `tenantPermissions.canReadTenant(...)` trả `Mono<Boolean>` dựa trên membership đáng tin, không blocking.
- Nếu membership false, service dừng trước khi query document.
- Repository nhận tenant và owner đã xác minh, không dùng `findAll()`.
- DTO chỉ gồm ID và title. Không serialize nguyên JPA/R2DBC entity có confidential fields.

**Đây là owner-only policy**. Nếu người được share có quyền READ, thay truy vấn owner-only bằng truy vấn ACL/share cùng phạm vi, không xóa điều kiện tenant. Với Spring Security version khác, syntax của expression/SpEL và reactive method security có thể cần điều chỉnh; chạy integration tests.

### Đừng để đường gọi phụ bỏ qua service

Nếu Controller A dùng `TenantDocumentReadService` nhưng GraphQL resolver B gọi thẳng `DocumentRepository.findAll()`, annotation ở A không giúp gì cho B. Đưa domain authorization vào những service/API có contract rõ, và hạn chế việc controller/worker truy repository chưa được scope.

### Không truyền Authentication như một tham số do client có thể sửa

Khi method nhận `Authentication` argument từ Spring-managed controller, đó có thể là đối tượng đã xác thực. Nhưng một public service API nhận `String currentUserId` từ caller bất kỳ không tự đáng tin. Một cách bảo vệ là service tự resolve subject từ trusted context hoặc yêu cầu một type `VerifiedSubject` bất biến chỉ có thể tạo bởi trusted adapter.

## 11. Lọc per-item trong Flux bằng filterWhen

Có những nguồn dữ liệu không thể áp đầy đủ ACL vào một SQL query, ví dụ index/search từ hệ thống khác hoặc streaming events từ nhiều nguồn. Khi đó phải áp **per-element check trước khi phát tới consumer**.

Một pipeline minh họa:

```java
public Flux<DocumentView> listFromSearch(
        VerifiedSubject subject, String verifiedTenant) {

    return searchIndex.queryDocuments(verifiedTenant)
        .filterWhen(doc -> accessPolicy
            .canRead(subject, doc.id(), verifiedTenant))
        .map(doc -> new DocumentView(
            doc.id(), doc.title()));
}
```

`Flux.filterWhen(...)` nhận một async predicate (Publisher Boolean). Đoạn này là **fragment** cần bean `searchIndex`, `accessPolicy`, DTO và Reactor. `canRead` cần trả `Mono<Boolean>`, đọc từ nguồn quyền đáng tin, hạn chế concurrency/timeout; nếu Publisher empty, không được coi là allow. Test phiên bản Reactor thực và failure semantics.

**Rủi ro vẫn còn:** search index đã tìm tài liệu không được phép; kết quả trung gian có thể ảnh hưởng ranking, totalCount, facets, logs hoặc các cache trước filter. Vì thế per-item filter là **defense in depth**, không thay thế bảo mật ngay trong search query khi backend có thể áp scope.

### concatMap cho pipeline cần thứ tự và điều kiện rõ

```java
return searchIndex.queryDocuments(verifiedTenant)
    .concatMap(doc ->
        accessPolicy.canRead(subject, doc.id(), verifiedTenant)
            .flatMap(allowed ->
                allowed
                    ? Mono.just(new DocumentView(
                        doc.id(), doc.title()))
                    : Mono.empty()
            )
            .defaultIfEmpty(null)
    );
```

**Đoạn trên là anti-pattern có chủ đích:** Reactor không chấp nhận giá trị `null` trong `Mono.defaultIfEmpty(null)`. Không được copy. Để làm đúng, **bỏ hẳn `defaultIfEmpty(null)`**; `Mono.empty()` đơn giản sẽ bỏ item không được phép:

```java
return searchIndex.queryDocuments(verifiedTenant)
    .concatMap(doc ->
        accessPolicy.canRead(subject, doc.id(), verifiedTenant)
            .defaultIfEmpty(false)
            .flatMap(allowed -> allowed
                ? Mono.just(new DocumentView(doc.id(), doc.title()))
                : Mono.empty())
    );
```

`concatMap` giữ thứ tự các item và giới hạn việc xử lý tuần tự theo thiết kế; phù hợp khi cần quyết định từng item một nhưng có thể tốn latency. Nếu dùng `flatMap(..., concurrency)` để tăng throughput, hãy áp backpressure và xem consistency; không để bắn hàng nghìn truy vấn permission song song không kiểm soát.

### Policy cho list: filter hay error?

Có hai hợp đồng khác nhau:

- **List/search:** có thể bỏ qua item không được phép và trả các item còn lại. Nếu **toàn bộ tenant không được phép** thì thường DENY cả list thay vì trả list trống dễ gây hiểu nhầm.
- **Detail by ID:** không nên im lặng biến một object forbidden thành một list rỗng; trả 403 hoặc 404 trung tính theo API contract, không tiết lộ owner/tenant.
- **Streaming secret bytes:** không được chuyển các chunk không hợp lệ thành `Mono.empty()` mà không giải quyết file-level permission; phải kiểm tra file **trước khi mở stream**.

Không trộn mọi trường hợp thành một `filterWhen(...)` chung mà chưa định nghĩa semantics.

## 12. Thứ tự filter, map và side effects bên trong pipeline

Giả sử source trả entity có cả `privateNotes`, `apiToken` và `title`.

Không nên:

```java
return documents.findAll()
    .doOnNext(doc -> auditLog.info("{}", doc))
    .map(doc -> new PublicDocumentView(
        doc.getTitle(), doc.getPrivateNotes()))
    .filterWhen(view -> policy.canRead(actor, view.id()));
```

Đây là **anti-pattern** minh họa: code vừa có nguy cơ log entity nhạy cảm, vừa đưa privateNotes vào DTO trước khi kiểm tra quyền. `PublicDocumentView`/`view.id()` là pseudocode thể hiện lỗi, không phải class hoàn chỉnh.

Nên thiết kế:

```text
Source query already scoped
   -> verify relevant authorization facts
   -> construct minimal permitted DTO
   -> emit to caller
   -> audit outcome without leaking raw content
```

Nếu cần nhiều levels READ (public metadata vs confidential content), sử dụng DTO/projection riêng theo permission; không tin rằng lọc nguyên document là đủ. Một `filter` bảo vệ **item**, nhưng không tự bảo vệ **field**.

### Reactor operator không tự giữ kết quả được phép

`map(...)` chỉ biến đổi dữ liệu, `filter(...)` chỉ lọc theo predicate, `doOnNext(...)` có side effects, `cache()` có thể giữ lại kết quả. Các operator này không tự biết danh tính hay tenant của request. Policy phải dùng trusted subject/resource/context.

## 13. @PostAuthorize và @PostFilter khác nhau ở điều gì?

| Tình huống | @PostAuthorize | @PostFilter / per-item policy |
| --- | --- | --- |
| `Mono<Document>` một đối tượng | Thường phù hợp hậu kiểm owner nếu cần | Không cần lọc collection |
| `Flux<Document>` nhiều item | Không coi là auto-filter tùy ý từng phần tử | Dùng cơ chế filter được hỗ trợ và test |
| Một item không có quyền trong list | Có thể cần deny toàn bộ theo policy | Có thể bỏ riêng item nếu list contract cho phép |
| 10.000 item đầu nguồn | Hậu kiểm có thể chạm dữ liệu sau tải | Vẫn đắt nếu lọc sau DB; nên query pushdown |
| Write/save đã có side effect | **Không nên** làm hàng rào duy nhất | Không giải quyết write authorization |
| SSE long-lived | Một hậu kiểm không phải re-authorization vô hạn | Có thể xét per-item + revoke signal |
| Pagination COUNT | Không tự sửa total/count | Không tự sửa COUNT đã tính ở DB |
| DTO private field | Không tự redaction | Không tự redaction field nếu chỉ filter item |

**Điểm tinh tế:** `@PostAuthorize` trên một returned object có thể chặn không trả chính object đó. Nhưng nếu một upstream đã gửi email, ghi cache, trigger job hoặc lưu file **trước** lúc kiểm tra, không có bảo đảm những tác động ấy bị hoàn tác.

Với `Flux`, đừng dùng quan sát “HTTP trả 403 khi user thiếu quyền” để suy ra mọi item đã được lọc. Cần test một stream có **nhiều item thuộc owner/tenant khác nhau**.

## 14. HTTP output: đã gửi bytes thì không thể thu hồi

Trong một HTTP response thông thường, framework có thể buffer dữ liệu rồi serialize. Nhưng với Flux streaming, JSON streaming, SSE hoặc file download, HTTP headers/body có thể đã được commit trước khi một item muộn bị từ chối.

Ví dụ:

```text
t0: request GET /events, method-level authorization ALLOW
t1: event #1 được phép -> gửi ra client
t2: event #2 được phép -> gửi ra client
t3: membership của Alice bị revoke
t4: event #3 cần quyền mới -> DENY/error
```

Tại t4, server có thể **chấm dứt stream** hoặc gửi sự kiện báo lỗi theo protocol, nhưng **không thể rút lại event #1/#2**. Nếu response đã gửi status/headers, không mặc định có thể đổi thành HTTP 403 cho phần đã phát. Đây là lý do test streaming phải kiểm tra **emitted sequence và termination signal**, không chỉ status.

### Hai chính sách revoke khác nhau

1. **Authorize at subscribe:** một lần xác minh lúc bắt đầu stream, sau đó cho stream kéo dài. Phù hợp nếu nghiệp vụ công nhận snapshot/session lease trong thời hạn cụ thể.
2. **Authorize per emission/period:** kiểm tra lại grant/membership mỗi item hoặc mỗi khoảng; phù hợp với stream nhạy cảm, nhưng tốn I/O và vẫn có độ trễ giữa revoke/next check.

Không có một chính sách mặc định phù hợp cho mọi loại stream. Cần xác định SLA revoke, cache freshness, event frequency, chi phí PDP và điều kiện kết thúc connection.

### Một pipeline kiểm tra quyền cho từng event

```java
public Flux<EventDto> subscribeEvents(
        VerifiedSubject subject, String tenantId) {

    return eventSource.forTenant(tenantId)
        .concatMap(event ->
            permission.canSeeEvent(
                subject, tenantId, event.resourceId())
                .flatMap(allowed -> allowed
                    ? Mono.just(new EventDto(
                        event.id(), event.type(), event.payloadSummary()))
                    : Mono.error(
                        new org.springframework.security.access.AccessDeniedException(
                            "Event permission revoked")))
        );
}
```

Đây là **component fragment**, cần event source, policy, DTO và resource scoped values. Nó chọn **terminate khi gặp item không có quyền**. Một ứng dụng khác có thể chọn bỏ item đó rồi tiếp tục; quyết định cần rõ. Dù chọn cách nào, dùng source đã scope theo tenant, không mở stream tất cả tenants rồi lọc ở bước cuối.

### SSE/WebSocket/GraphQL

- **SSE**: một HTTP subscription có thể phát nhiều events; cần xem cả permission khi subscribe lẫn từng event.
- **WebSocket**: HTTP handshake được bảo vệ không tự bảo vệ mọi message/room/channel; message-level authorization phải được triển khai.
- **GraphQL**: route thường chỉ là `/graphql`; quyền trên từng resolver/resource/field không thể suy ra chỉ từ route authentication.
- **File download**: kiểm tra **toàn file** trước khi cấp presigned URL hoặc bắt đầu phát bytes. Nếu URL presigned đã phát và còn hạn, revoke trong database không tự xóa khả năng tải của URL.
- **Export async**: quyền khi yêu cầu export, khi job đọc dữ liệu và khi user tải file thành phẩm có thể cần policy ở cả ba điểm.

## 15. HTTP security không thay service/domain security

Trong WebFlux, một `SecurityWebFilterChain` có thể bắt buộc authentication:

```java
http.authorizeExchange(exchanges -> exchanges
    .pathMatchers("/api/**").authenticated()
    .anyExchange().denyAll()
);
```

Rule này không tự kiểm tra Document 42 thuộc tenant nào. Mặt khác, `@PreAuthorize` ở service cũng có thể bị bypass nếu:

- Một GraphQL resolver gọi repository trực tiếp.
- Một worker/batch dùng service khác không qua annotated method.
- Một method trong cùng bean gọi `this.securedMethod()` khiến self-invocation bypass Spring AOP proxy.
- Ứng dụng tạo instance bằng `new` thay vì Spring-managed bean.
- Một custom `WebFilter` hoặc route mới vào chain khác do `@Order`/matcher.
- Code tách sang `CompletableFuture` hoặc callback không có Reactor SecurityContext mà policy dùng fallback subject khác.

**Phòng vệ nhiều lớp:** xác thực/route guard ở HTTP, domain action policy ở service, tenant+ACL predicate ở repository/DB, DTO projection ở output, và tests bao phủ các đường gọi khác nhau.

## 16. Reactor Context, authentication và tenant scope

Spring Security reactive dùng `ReactiveSecurityContextHolder` dựa trên Reactor Context; nó khác mô hình chỉ dựa vào `ThreadLocal` trên Servlet.

Ví dụ đọc Authentication trong publisher:

```java
import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.ReactiveSecurityContextHolder;
import reactor.core.publisher.Mono;

Mono<Authentication> authMono =
    ReactiveSecurityContextHolder.getContext()
        .map(ctx -> ctx.getAuthentication());
```

Trong WebFlux app bật Spring Security, context được thiết lập trên reactive chain theo authenticated request. Tuy nhiên **không nên** hiểu `Authentication.getName()` luôn là stable subject ID: OAuth2/JWT, OIDC và nhiều issuer cần mapping rõ.

### ContextWrite trong test

```java
import org.springframework.security.authentication.TestingAuthenticationToken;
import org.springframework.security.core.context.ReactiveSecurityContextHolder;

var auth = new TestingAuthenticationToken(
    "alice", "unused", "document:read");

Mono<String> result =
    ReactiveSecurityContextHolder.getContext()
        .map(ctx -> ctx.getAuthentication().getName())
        .contextWrite(
            ReactiveSecurityContextHolder.withAuthentication(auth));
```

Đây là **test fragment**, cần types/imports/context phù hợp. Khi chạy, người dùng có thể kiểm tra publisher phát `"alice"` với StepVerifier. Nhưng `TestingAuthenticationToken` không đại diện JWT verification thực, chỉ dùng trong unit/integration test có chủ đích.

### Tenant selector không phải authorization

Nếu path là `/tenants/tenant-b/documents`, giá trị `tenant-b` do client chọn. Đọc membership của Alice trong B trước khi query, không dùng tenant B trực tiếp như bằng chứng. Đừng lưu active tenant trong một `static` mutable field hoặc ThreadLocal không được clear giữa request; nhiều subscriber có thể dùng nhiều thread/tenant cùng lúc.

Một `VerifiedTenantScope` bất biến nên chứa subject, tenant và quyền đã kiểm tra, hoặc service policy phải lấy tenant membership từ nguồn đáng tin tại thời điểm thao tác.

## 17. Empty, error và cancellation: không vô tình fail open

Một `Mono<Boolean>` có thể phát:

```text
Mono.just(true)  -> explicit ALLOW khi đủ bằng chứng
Mono.just(false) -> explicit DENY
Mono.empty()     -> không có kết quả
Mono.error(e)    -> lỗi kiểm tra quyền
```

**Không được biến empty/error thành true.** Khi thiếu membership hoặc document, policy cần deny hoặc response không lộ resource. Khi DB/PDP timeout, vẫn **không cấp quyền**, nhưng thường cần HTTP 503/5xx và metric lỗi hạ tầng thay vì coi tất cả user không có permission.

Ví dụ:

```java
return permission.canRead(subject, resourceId)
    .defaultIfEmpty(false);
```

Và không:

```java
return permission.canRead(subject, resourceId)
    .onErrorReturn(true); // Sai: outage mở quyền.
```

### Cancellation giữa pipeline

Subscriber cancel có thể ngăn thêm các item được nhận, nhưng **không tự hoàn tác**:

- SQL update đã commit.
- Email/event đã gửi.
- Một item đã được HTTP serialize.
- File đã được ghi vào storage.
- Background task tách subscription riêng.

Do đó không có “hậu kiểm rồi cancel” nào đảm bảo undo mọi side effect. Authorization cho mutation phải nằm trước thao tác hoặc là điều kiện nguyên tử của thao tác.

## 18. Ranh giới giữa pre-check và mutation

Một race:

```text
T1: @PreAuthorize EDIT -> ALLOW
T2: admin revoke quyền EDIT của Alice
T1: SQL UPDATE docs SET ...
```

Annotation trước method có thể chạy **trước** transactional advice của method, và dữ liệu authorization có thể thay đổi sau check. Một `@Transactional` đơn lẻ với isolation mặc định không tự bảo đảm tuyệt đối về revoke.

Một SQL UPDATE có điều kiện:

```sql
UPDATE documents
SET title = :new_title
WHERE id = :document_id
  AND tenant_id = :verified_tenant
  AND owner_subject_id = :authenticated_subject
  AND deleted = FALSE
  AND status = 'DRAFT';
```

Nếu domain cho edit bằng ACL, thêm điều kiện EXISTS kiểm tra ACL **trong statement hoặc transaction** phù hợp. Kiểm tra số rows updated; zero row không được coi thành success và không được tiết lộ resource existence tùy API contract.

### Reactive TransactionalOperator

```java
import org.springframework.transaction.reactive.TransactionalOperator;
import reactor.core.publisher.Mono;

public Mono<Boolean> rename(
        VerifiedSubject actor,
        long documentId,
        String newTitle) {

    return writeRepository
        .renameIfAuthorized(
            actor.subjectId(), actor.tenantId(),
            documentId, newTitle)
        .map(affectedRows -> affectedRows == 1L)
        .as(transactionalOperator::transactional);
}
```

**Fragment minh họa**: cần `TransactionalOperator` cấu hình đúng ReactiveTransactionManager, `writeRepository` có update tenant/owner/ACL/status được bind, kiểu dữ liệu affectedRows phù hợp driver (đoạn trên giả định long); không có controller/DTO. Nếu method trả false, service cần map thành outcome từ chối/không tìm thấy; không trả `200 OK` khi update không xảy ra.

Reactive transaction sử dụng Reactor Context cho resource binding. Nó không tự bao HTTP remote PDP và email/file storage trong cùng ACID transaction. Nếu nghiệp vụ có side effects ngoài DB, cân nhắc outbox/compensating strategy sau commit.

### Không dùng @PostAuthorize như rollback manager

Ngay cả khi reactive method-security trả error sau khi một item đã được tạo, không có bảo đảm toàn bộ transaction, cache, storage và external effects đã bị rollback. Phải review **thứ tự transaction advisor và security advisor** cùng integration tests, không chỉ trông vào annotation.

## 19. Pagination: nơi hậu lọc thường sai nghiệp vụ

Giả sử query lấy page 1 với `LIMIT 10` từ 100 documents, nhưng Alice chỉ xem được 5 documents ở các vị trí 20–30.

Cách sai:

```text
DB: ORDER BY created_at LIMIT 10 OFFSET 0
   -> 10 documents (đều không thuộc Alice)
@...PostFilter:
   -> 0 documents
API response:
   items=[]
   totalElements=100
```

Alice thấy một page trống và total=100 dù có dữ liệu hợp lệ ở page khác. Nếu UI tin rằng page trống nghĩa hết dữ liệu, Alice không bao giờ thấy 5 documents có quyền. Đồng thời totalElements=100 có thể rò số lượng document của người khác.

Cách đúng:

```text
DB: WHERE tenant=verifiedTenant
    AND (owner=alice OR active ACL/share grant)
    AND deleted=false
    ORDER BY created_at DESC, id DESC
    LIMIT 10
   -> chỉ những documents Alice được phép
COUNT:
   -> cùng tenant/ACL predicate
API:
   -> items & totalElements thuộc phạm vi Alice
```

Đặt điều kiện authorization vào query trước khi LIMIT/OFFSET hoặc dùng cursor/keyset pagination với predicate quyền. Chỉ tách policy thành per-item filtering khi nguồn dữ liệu thật sự không hỗ trợ pushdown, và phải định nghĩa lại semantics pagination/count một cách chính xác.

### Search, aggregation và facets

Ngay cả khi item body đã lọc, search result metadata có thể lộ:

- Total hits.
- Facet counts theo status/project.
- Search snippets từ tài liệu không được phép.
- Autocomplete suggestions.
- Ranking hoặc sort keys dựa vào dữ liệu bí mật.
- File names và owner identifiers.

Data authorization phải áp dụng **trước khi sinh metadata** khi có thể, không chỉ một `Flux.filter(...)` sau khi kết quả search đã được tính.

## 20. @PostFilter có hỗ trợ mọi kiểu trả về không?

Không nên suy ra từ Java Servlet examples rằng mọi reactive return type đều có cùng behavior. Tài liệu Reactive Method Security ở Spring Security mới xác nhận sự tồn tại của `PostFilterAuthorizationReactiveMethodInterceptor` và pre/post annotations, nhưng để đưa một mã production cụ thể vào vận hành, cần đối chiếu:

1. Spring Security runtime version.
2. `@EnableReactiveMethodSecurity` configuration và mode AuthorizationManager.
3. Return type thực: `Flux<T>`, `Mono<T>`, `Mono<List<T>>`, collection, Kotlin coroutine/Flow.
4. Annotation/SpEL property naming trên DTO/record.
5. Hành vi đối với empty, null, error và nhiều item.
6. Kết quả AOP proxy có thực sự wrap Publisher không.
7. Interaction với transaction, caching và serialization.

Một phép thử phù hợp:

```text
Given Flux(Doc1 owner=alice, Doc2 owner=bob, Doc3 tenant=B)
When Alice gọi method qua Spring proxy
Then emitted IDs chỉ chứa Doc1
And Doc2/Doc3 không xuất hiện trong subscriber signals
And không có side effects với Doc2/Doc3
```

Nên coi `@PostFilter` là **công cụ có điều kiện**, còn **repository scoped query** là cách chủ động giảm dữ liệu trái quyền ngay từ nguồn.

## 21. Một ví dụ Java 17 chạy độc lập: method ALLOW nhưng item vẫn cần lọc

Ví dụ sau **không dùng Spring Security hoặc Reactor** vì hai thư viện cần dependency ngoài JDK. Nó sử dụng Java 17 `CompletableFuture` để mô phỏng lời gọi bất đồng bộ và so sánh ba tầng: (1) quyền gọi method, (2) lọc owner-only sai vì thiếu tenant, (3) lọc đủ tenant, owner và trạng thái trước khi phát kết quả.

Không chạy `join()` trong WebFlux event loop. Ở file độc lập có `main`, `join()` chỉ dùng để in kết quả theo thứ tự xác định.

Lưu file `ReactiveEmissionBoundaryDemo.java`:

```java
import java.util.List;
import java.util.Set;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CompletionStage;

public class ReactiveEmissionBoundaryDemo {

    enum Action { READ, WRITE }

    record Actor(
        String id,
        String tenant,
        Set<Action> actions,
        boolean active
    ) {}

    record Document(
        int id,
        String tenant,
        String owner,
        boolean deleted
    ) {}

    private static final List<Document> ALL = List.of(
        new Document(1, "tenant-a", "alice", false),
        new Document(2, "tenant-a", "bob", false),
        new Document(3, "tenant-b", "alice", false),
        new Document(4, "tenant-a", "alice", true),
        new Document(5, "tenant-a", "alice", false)
    );

    static boolean canInvoke(Actor actor, Action action) {
        return actor != null
            && actor.active()
            && actor.actions().contains(action);
    }

    static List<Integer> naiveOwnerOnly(
            Actor actor, List<Document> source) {
        return source.stream()
            .filter(doc -> doc.owner().equals(actor.id()))
            .map(Document::id)
            .toList();
    }

    static List<Integer> safeVisible(
            Actor actor, List<Document> source) {
        return source.stream()
            .filter(doc -> doc.tenant().equals(actor.tenant()))
            .filter(doc -> !doc.deleted())
            .filter(doc -> doc.owner().equals(actor.id()))
            .map(Document::id)
            .toList();
    }

    static CompletionStage<List<Integer>> emittedReadIds(Actor actor) {
        if (!canInvoke(actor, Action.READ)) {
            return CompletableFuture.completedFuture(List.of());
        }

        // Mô phỏng một nguồn async đã đọc xong. Không phải R2DBC.
        return CompletableFuture.completedFuture(ALL)
            .thenApply(rows -> safeVisible(actor, rows));
    }

    public static void main(String[] args) {
        Actor alice = new Actor(
            "alice", "tenant-a", Set.of(Action.READ), true);
        Actor bob = new Actor(
            "bob", "tenant-a", Set.of(Action.READ), true);
        Actor carol = new Actor(
            "carol", "tenant-b", Set.of(), true);

        System.out.println("Alice method READ: "
            + canInvoke(alice, Action.READ));
        System.out.println("Unscoped source size: " + ALL.size());
        System.out.println("Naive owner-only IDs: "
            + naiveOwnerOnly(alice, ALL));
        System.out.println("Safe emitted Alice IDs: "
            + emittedReadIds(alice).toCompletableFuture().join());
        System.out.println("Safe emitted Bob IDs: "
            + emittedReadIds(bob).toCompletableFuture().join());
        System.out.println("Carol method READ: "
            + canInvoke(carol, Action.READ));
        System.out.println("Carol emitted IDs: "
            + emittedReadIds(carol).toCompletableFuture().join());
        System.out.println("Alice method WRITE: "
            + canInvoke(alice, Action.WRITE));
    }
}
```

Lệnh biên dịch/chạy:

```bash
javac ReactiveEmissionBoundaryDemo.java
java ReactiveEmissionBoundaryDemo
```

Stdout chính xác trên Java 17+:

```text
Alice method READ: true
Unscoped source size: 5
Naive owner-only IDs: [1, 3, 4, 5]
Safe emitted Alice IDs: [1, 5]
Safe emitted Bob IDs: [2]
Carol method READ: false
Carol emitted IDs: []
Alice method WRITE: false
```

**Nhận xét:**

- Alice được gọi READ, nhưng nguồn ban đầu có **5** records, gồm tài liệu của Bob, tenant B và tài liệu deleted.
- Hậu lọc đơn giản theo owner sẽ sai: `Doc3` thuộc tenant B và `Doc4` đã deleted vẫn lọt.
- Bộ lọc đầy đủ chỉ phát IDs `[1, 5]`.
- Bob có READ nhưng chỉ nhận ID `2`; Carol không có authority READ nên không nhận item.
- Alice không có WRITE; quyền đọc không biến thành quyền sửa.

**Giới hạn minh bạch:** `CompletableFuture.completedFuture(ALL)` không tạo I/O thật, và `safeVisible(...)` vẫn lọc **sau khi đã materialize 5 documents**. Nó giải thích ranh giới logic, **không** phải một triển khai DB pushdown. Trong production, để giảm rủi ro và tải, thay nguồn `ALL` bằng **query R2DBC đã có predicates** trước khi có Publisher items.

## 22. WebTestClient: kiểm tra đúng dữ liệu được trả, không chỉ HTTP status

Một integration test WebFlux cần Spring Security WebFilter chain và service proxy được load từ application context.

Ví dụ thiết lập:

```java
import org.junit.jupiter.api.BeforeEach;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.context.ApplicationContext;
import org.springframework.test.web.reactive.server.WebTestClient;

import static org.springframework.security.test.web.reactive.server
    .SecurityMockServerConfigurers.springSecurity;

class DocumentHttpSecurityTest {
    @Autowired ApplicationContext applicationContext;
    WebTestClient client;

    @BeforeEach
    void setup() {
        client = WebTestClient.bindToApplicationContext(applicationContext)
            .apply(springSecurity())
            .configureClient()
            .build();
    }
}
```

Đây là **test class fragment**: cần test context/runner annotation (`@SpringBootTest` hoặc cấu hình phù hợp), controllers/services, `spring-security-test`, repositories fixtures và dependency WebFlux. Nếu chỉ `bindToController(new Controller())` mà không có security chain, test có thể bỏ qua method/security filters.

### Kiểm tra body IDs

```java
import static org.springframework.security.test.web.reactive.server
    .SecurityMockServerConfigurers.mockJwt;

client.mutateWith(mockJwt()
        .jwt(jwt -> jwt.subject("alice"))
        .authorities(
            new SimpleGrantedAuthority("document:read")))
    .get()
    .uri("/api/tenants/tenant-a/documents")
    .exchange()
    .expectStatus().isOk()
    .expectBodyList(DocumentView.class)
    .hasSize(2);
```

Đây là **fragment**: `SimpleGrantedAuthority`, `DocumentView` và fixtures phải định nghĩa; test đang kỳ vọng Alice có đúng hai bản ghi. Ngoài số lượng, cần extract body và kiểm tra **IDs chính xác**, đảm bảo ID của Bob/tenant B/deleted **không xuất hiện**. `mockJwt` không kiểm chứng signature/issuer/audience của token thật; phải có test decoder thật khi muốn xác minh authentication boundary.

### Một trường hợp nguy hiểm

Test chỉ nhìn:

```java
.expectStatus().isOk();
```

có thể PASS kể cả response chứa 100 tài liệu ngoài scope. Kiểm thử authorization dữ liệu luôn cần **assert body content và dữ liệu vắng mặt**, không chỉ status.

## 23. StepVerifier: kiểm tra các tín hiệu Publisher

Với Reactor Test:

```java
import reactor.test.StepVerifier;

StepVerifier.create(
    documentService.listOwned("tenant-a")
)
    .expectNextMatches(doc -> doc.id().equals(1L))
    .expectNextMatches(doc -> doc.id().equals(5L))
    .verifyComplete();
```

Đây là **test fragment**, cần một Spring-managed service thật, `DocumentView.id()` kiểu Long, Authentication trong Reactor Context (hoặc test security support), fixtures. Quan trọng là không có item khác xen vào.

### Kiểm tra tín hiệu deny

```java
StepVerifier.create(securedService.listOwned("tenant-c"))
    .expectError(
        org.springframework.security.access.AccessDeniedException.class)
    .verify();
```

Kỳ vọng này đúng khi service chọn **error** cho tenant không có membership. Nếu API contract chọn 404 hoặc empty list, test tương ứng nhưng không bao giờ cấp quyền. Không quy mọi trường hợp unauthorized thành empty mà chưa xác định ranh giới thông tin cần che giấu.

### Kiểm tra Publisher không phát một giá trị trái quyền

```java
StepVerifier.create(
    Flux.just(
        new Doc(1, "alice"),
        new Doc(2, "bob"),
        new Doc(3, "alice")
    ).filter(doc -> "alice".equals(doc.owner()))
)
    .expectNextMatches(doc -> doc.id() == 1)
    .expectNextMatches(doc -> doc.id() == 3)
    .verifyComplete();
```

Đây là **Reactor unit test fragment**: cần `Doc` record, `Flux`, JUnit context. Nó minh họa kiểm tra từng emission nhưng **không kiểm thử Spring Security interceptor**, vì chỉ dùng `filter`. Để test `@PostFilter`/`@PostAuthorize` thực sự, gọi Spring bean có annotation.

### Reactive SecurityContext trong test

```java
var authentication = new TestingAuthenticationToken(
    "alice", "unused", "document:read");

StepVerifier.create(
    securedService.listOwned("tenant-a")
        .contextWrite(
            ReactiveSecurityContextHolder
                .withAuthentication(authentication))
)
    .expectNextCount(2)
    .verifyComplete();
```

Đây là **fragment**; cần imports TestAuthentication/Reactor và service fixture phù hợp. `expectNextCount(2)` chỉ xác minh số lượng; thêm assertions trên từng item để chống rò ID ngoài scope.

### Test source subscription/side effects

Cần chứng minh khi PRE DENY thì:

- Repository/source không được subscribe ngoài ý muốn.
- Không có SQL mutation.
- Không gửi email/event.
- Không cấp presigned URL.
- Không cache raw entity.
- Không phát bất cứ item nào tới downstream.

Dùng `doOnSubscribe`/mock subscriber counters hoặc integration mocks để kiểm tra. Đồng thời test post-check denial xảy ra **sau khi** read source có thể đã chạy; điều này xác nhận không thể dùng hậu kiểm để bảo vệ side effect.

## 24. Ma trận kiểm thử tối thiểu

| Điều kiện | Invocation | Item/data outcome cần bảo vệ |
| --- | --- | --- |
| Anonymous gọi READ | DENY | Không có item |
| Alice không có `document:read` | DENY | Không có item |
| Alice có authority READ, owner Doc1 cùng tenant | ALLOW | Doc1 được phát |
| Alice có authority READ, Doc2 của Bob | ALLOW với list | Doc2 **không** được phát |
| Alice có authority READ ở A, Doc3 thuộc B | ALLOW với list A | Doc3 **không** được phát |
| Alice owner Doc4 đã deleted | ALLOW với list A | Doc4 **không** được phát |
| User B có READ, thay URL tenant=A | Không có verified membership | Không phát tài liệu A |
| Share READ còn hiệu lực trên Doc5 | ALLOW theo domain policy | Chỉ Doc5 và field được phép |
| Share READ hết hạn hoặc revoke | Chưa chắc method-level chặn | Doc5 không xuất hiện |
| READ grant nhưng gọi EDIT | DENY ở action | Không ghi dữ liệu |
| List có 10 object hợp lệ trong 1000 | ALLOW | Pagination/count chỉ theo 10 object có quyền |
| SSE phát 2 events rồi revoke | Định nghĩa per-stream policy | Không phát event trái quyền tiếp theo theo SLA |
| Flux item thứ 3 denied sau 2 item đã gửi | Đã có partial response | Không giả định đổi HTTP status về 403 sau commit |
| DB permission timeout | Không có bằng chứng quyền | Không ALLOW; error/5xx theo contract |
| Remote PDP trả `Mono.empty()` | Không có decision | Không ALLOW |
| SecurityContext mất khi đổi scheduler | Không xác minh được caller | DENY, không fallback user admin |
| Service được gọi từ GraphQL/worker | HTTP guard có thể không chạy | Domain policy vẫn bắt buộc |
| @PreAuthorize bị bypass do self-invocation | Có thể bỏ qua interceptor | Query/data layer vẫn cần scope |
| Cache Flux/Mono dùng chung nhiều actor | Rủi ro cross-user leak | Cache key theo actor/tenant/action/version hoặc không cache |
| Field privateNotes trong DocumentView | List item có thể hợp lệ | Không phát field khi thiếu field-level authority |

Ngoài matrix, test endpoint detail/batch/search/export/download theo đúng đường đi mà production sử dụng. Với data leak, sự vắng mặt của một record/field thường quan trọng hơn việc một request trả 200.

## 25. Performance: đừng biến per-item authorization thành N+1

Một list 1000 items, mỗi item gọi `canRead` để query ACL một lần, có thể tạo 1000 I/O operations dù không blocking. Non-blocking giúp dùng thread tốt hơn nhưng **không làm số query biến mất**.

Ưu tiên:

1. **Predicate pushdown**: SQL/search filter owner, tenant, ACL ngay ở nguồn.
2. **Batch fetch**: lấy ACL/resource facts cho một nhóm ID đã được xác minh.
3. **Pre-check coarse action**: chặn request rõ ràng không có authority trước khi query lớn.
4. **Limited concurrency**: nếu phải `filterWhen`/`flatMap`, giới hạn số permission lookups đồng thời.
5. **Backpressure**: không collect toàn bộ Flux nếu chỉ cần vài phần tử.
6. **Cache có scope**: key subject/tenant/resource/action/policy version/ACL epoch và invalidation.
7. **Observability**: p50/p95/p99 latency, query count, denied item count, cache hit safety, source errors, streaming cancellation.
8. **DTO projection ở DB**: không đưa password hash, tokens hoặc tài liệu mật vào object được mang qua application khi không cần.
9. **Tách COUNT và list cùng predicate**: tránh thông tin thống kê ngoài scope.
10. **Revocation semantics rõ ràng**: không cache ALLOW vượt share expiry hoặc SLA revoke.

### Flux.cache() không hiểu quyền

Nếu một singleton service giữ lại Publisher đã được tạo theo Alice:

```java
private final Flux<DocumentView> cachedResult =
    rawDocuments.findAll().map(this::toView).cache();
```

Đây là **anti-pattern** cho dữ liệu user-specific: cache có thể giữ raw data và tái sử dụng qua nhiều subscriber. Đừng dùng `Flux.cache()` như một authorization cache đa người dùng không có key/expiry/invalidation. Với response nhạy cảm, phải đánh giá cả browser/CDN cache và file/object storage.

## 26. Lỗi thường gặp

| Sai lầm | Hậu quả | Hướng sửa |
| --- | --- | --- |
| Nghĩ `@PreAuthorize('document:read')` lọc từng item Flux | Rò dữ liệu Bob/tenant khác | Data-scoped query hoặc per-element policy |
| Chỉ test 401/403/200 | Rò response body không bị phát hiện | Assert IDs, fields, count và absence |
| Dùng `findAll()` rồi `@PostFilter` toàn kho | I/O khổng lồ, pagination sai | Query ACL/tenant trước LIMIT |
| Lọc owner nhưng quên tenant | Cross-tenant leak | Điều kiện subject+tenant+action+resource |
| Lọc item nhưng không lọc private fields | Field-level data leak | DTO/projection per permission |
| Dùng @PostAuthorize cho write | Side effects có thể đã commit | Pre-check + conditional update/transaction |
| Nghĩ @PostAuthorize tự thu hồi SSE bytes đã phát | Client đã nhận dữ liệu | Recheck per event + terminate/lease semantics |
| Đếm toàn bộ DB rồi lọc list | Lộ totalElements | COUNT cùng predicate |
| `Mono.empty()` hoặc dependency error được coi là allow | Fail-open | Default deny/5xx |
| Tự `subscribe()` ngoài pipeline để "check sau" | Request có thể đi tiếp trước decision | Compose Publisher vào security chain |
| `block()` trong reactive policy | Chặn event loop | R2DBC/WebClient/Mono composition |
| Method gọi `this.read()` nội bộ | Bypass AOP proxy | Call qua Spring bean + scoped data query |
| Service khởi tạo bằng `new` | Annotation không được intercept | Dùng Spring-managed bean |
| Cho raw tenant header đi thẳng DB | IDOR/BOLA | Verify membership, trusted tenant scope |
| Cache `Flux` theo singleton | Cross-user replay | Cache theo subject/tenant hoặc tránh |
| Dùng `onErrorContinue` để bỏ mọi lỗi quyền | Che dependency failure, khó audit | Phân loại errors, không cấp quyền |
| Cho response body streaming rồi sau đó mới check | Có partial leakage | Verify trước emission và định nghĩa terminate |
| Test mockJwt để kết luận JWT signature an toàn | Mock bỏ qua decoder | Test Resource Server với token thật |
| Lọc sau search facets | Rò metadata/count | Filter tại search/index nguồn |
| Không test multi-item @PostFilter | Không biết annotation có thực thi đúng | StepVerifier qua Spring proxy |
| Thiếu ACL version khi cache | Dùng ALLOW sau revoke | Cache key/invalidation/freshness |
| Chỉ bảo vệ HTTP layer | GraphQL, job, worker bỏ qua | Service/domain/DB policy |
| Dùng status 404 để chứng minh không rò dữ liệu | Metadata/stream vẫn có thể bị lộ | Kiểm toàn body, timings, logs, side effects |

## 27. Checklist để review code Reactive Method Security

1. Method trả `Mono` hay `Flux`? Hệ thống có subscription/streaming dài không?
2. `@EnableReactiveMethodSecurity` bật đúng version/mode chưa?
3. Service có được gọi qua Spring proxy, không qua `this.`/`new`?
4. `@PreAuthorize` kiểm tra **action chức năng** hay nhầm là kiểm tra mọi object?
5. Caller/tenant có được xác minh từ nguồn đáng tin không?
6. Repository có lọc đúng resource type, tenant, owner/ACL, status trước khi đọc?
7. Nếu dùng `@PostAuthorize`, đã kiểm tra source side effects và version behavior chưa?
8. Nếu dùng `@PostFilter`, đã test từng item `Flux` với nhiều owner/tenant chưa?
9. Có dùng `filterWhen`/`concatMap` để kiểm tra item không; xử lý empty/error thế nào?
10. Data đã được log, cache, gửi events hoặc serialize **trước** policy check chưa?
11. Response DTO có loại bỏ các trường không được phép không?
12. Pagination, COUNT, search facets và export có cùng authorization predicates không?
13. Mutation có kiểm tra quyền sát lệnh DB update, transaction và row count chưa?
14. Stream có chính sách cho revoke/expiry giữa chừng không?
15. Nếu response đã commit, app xử lý denial muộn thế nào?
16. Có test nguồn cold/hot, cancellation, cache replay và multiple subscribers không?
17. Có tránh `block()`, blocking JDBC trong event loop và `subscribe()` thủ công không?
18. Authentication có theo Reactor Context khi đổi scheduler không?
19. Có test direct service calls ngoài HTTP chain không?
20. Cache có key actor/tenant/action/resource/version và invalidate khi revoke không?
21. Lỗi DB/PDP có không ALLOW và được giám sát đúng không?
22. Có StepVerifier/WebTestClient với **nội dung cụ thể** thay vì chỉ status không?
23. Test negative có các item thuộc người khác, tenant khác, deleted, expired, confidential không?
24. Có test limit/offset/cursor pagination và count bị lộ không?
25. Kết quả đã được kiểm tra trên chính Spring Security version trong production chưa?

**Kết luận:** Trong Spring Security Reactive, bảo vệ **quyền gọi phương thức** là điều kiện cần nhưng **không đủ** để bảo vệ **dữ liệu phát ra từ `Mono`/`Flux`**. `@PreAuthorize` chặn lời gọi không hợp lệ; `@PostAuthorize` và `@PostFilter` giúp hậu kiểm/lọc trong phạm vi được hỗ trợ; còn thiết kế vững chắc phải **giới hạn dữ liệu tại nguồn**, kiểm tra item/field trước emission, xử lý streaming/revocation, tránh side effects trước hậu kiểm và test chính xác những phần tử **không bao giờ được phép tới client**.

## Tài liệu tham khảo

- [Spring Security — EnableReactiveMethodSecurity](https://docs.spring.io/spring-security/reference/reactive/authorization/method.html): Reactor Context, `@EnableReactiveMethodSecurity`, `@PreAuthorize`/`@PostAuthorize`/`@PreFilter`/`@PostFilter`, reactive interceptors.
- [Spring Security API — PostFilterAuthorizationReactiveMethodInterceptor](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/authorization/method/PostFilterAuthorizationReactiveMethodInterceptor.html): interceptor hậu lọc trong reactive method security.
- [Spring Security API — PostAuthorizeReactiveAuthorizationManager](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/authorization/method/PostAuthorizeReactiveAuthorizationManager.html): đánh giá hậu kiểm và `MethodInvocationResult`.
- [Spring Security — Reactive HTTP Authorization](https://docs.spring.io/spring-security/reference/reactive/authorization/authorize-http-requests.html): điểm cưỡng chế HTTP và `authorizeExchange`.
- [Spring Security — Reactive Security Context](https://docs.spring.io/spring-security/reference/reactive/authorization/method.html): cơ chế `ReactiveSecurityContextHolder` và SecurityContext trong Reactor.
- [Spring Security — Reactive Testing](https://docs.spring.io/spring-security/reference/reactive/test/web/setup.html): tích hợp `WebTestClient` và Spring Security chain.
- [Spring Security — Reactive OAuth2/JWT Testing](https://docs.spring.io/spring-security/reference/reactive/test/web/oauth2.html): `mockJwt` và giới hạn của test mock.
- [Spring Data R2DBC — Reference](https://docs.spring.io/spring-data/relational/reference/r2dbc.html): repository/data access reactive và query predicates.
- [Spring Framework — Reactive Transactions](https://docs.spring.io/spring-framework/reference/data-access/transaction/programmatic.html): `TransactionalOperator` và reactive transaction boundary.
- [Project Reactor — Reference](https://projectreactor.io/docs/core/release/reference/): `Flux`, `Mono`, `filterWhen`, `concatMap`, Context, backpressure, error/cancellation và testing.
- [OWASP — Authorization Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Authorization_Cheat_Sheet.html): least privilege, deny by default và kiểm tra object level.
- [OWASP — Insecure Direct Object Reference Prevention](https://cheatsheetseries.owasp.org/cheatsheets/Insecure_Direct_Object_Reference_Prevention_Cheat_Sheet.html): quyền trên từng ID và truy vấn dữ liệu theo scope.
