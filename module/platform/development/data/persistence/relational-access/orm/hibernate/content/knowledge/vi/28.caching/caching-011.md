# Giữ đúng phân tách dữ liệu theo tổ chức và quyền truy cập khi dùng bộ nhớ đệm Hibernate ORM

Trong ứng dụng nhiều khách hàng doanh nghiệp, mỗi tổ chức (*organization/tenant*) thường có dữ liệu độc lập, trong khi nhiều người dùng thuộc cùng tổ chức có các vai trò và quyền truy cập khác nhau. Khi chưa dùng cache, ứng dụng có thể dựa vào điều kiện `WHERE organization_id = ...` hoặc cơ chế multi-tenancy của Hibernate để giới hạn dữ liệu. Sau khi bật bộ nhớ đệm, một câu hỏi bảo mật mới xuất hiện:

**Có thể nào dữ liệu của tổ chức A được trả cho tổ chức B, hoặc một người dùng không có quyền được xem entity đã lưu trong cache từ lần truy cập hợp lệ trước đó?**

Rủi ro có thật nếu ứng dụng tự xây cache key chỉ bằng ID, đặt cache ở tầng service mà quên phạm vi người dùng, tái sử dụng Session sai tenant, hoặc coi dữ liệu đã nằm trong Hibernate cache là đã được kiểm tra quyền. Tuy nhiên, cũng không nên kết luận rằng Hibernate second-level cache mặc định luôn trộn tenant: **khi dùng Hibernate multi-tenancy đúng cách, các cache key của Hibernate có cơ chế mang tenant identifier để phân tách identity giữa tenant**. Vấn đề thường nằm ở cách cấu hình/boundary và những tầng cache, truy vấn, quyền truy cập ngoài cơ chế ấy.

Bài học giải thích:

- Sự khác nhau giữa **tenant isolation** và **authorization** (RBAC, ACL, ABAC).
- Persistence context/first-level cache, second-level cache và query cache nhìn nhận identity như thế nào.
- Hibernate multi-tenancy, `@TenantId`, tenant resolver và việc khóa tenant vào Session.
- Thiết kế khóa cache cho DTO, quyền và kết quả truy vấn ngoài Hibernate.
- Xử lý thay đổi role, membership, permission, soft delete và dữ liệu được revoke.
- Query filter, native SQL, entity association, background jobs, asynchronous tasks.
- Chiến lược cache invalidation, transaction, test chống cross-tenant leakage và vận hành an toàn.

Nguyên tắc xuyên suốt: **cache là cơ chế tăng tốc truy cập dữ liệu; nó không phải ranh giới cấp quyền. Quy tắc tổ chức và quyền truy cập phải được bảo đảm độc lập với việc cache hit hay miss.**

---

## 1. Hai kiểu phân tách thường xuất hiện trong ứng dụng

Giả sử một SaaS quản lý tài liệu có các tổ chức:

```text
Rental SaaS
|
+-- Organization A
|   +-- User Alice: ADMIN
|   +-- User Bob: VIEWER
|   +-- Document A-101 (PUBLIC_TO_ORG)
|   +-- Document A-102 (ADMIN_ONLY)
|
+-- Organization B
    +-- User Carol: ADMIN
    +-- Document B-101
```

Có hai câu hỏi riêng:

1. **Tenant isolation:** Một truy vấn của Organization A có nhìn thấy `Document B-101` không? Đáp án phải là không, ngay cả khi hai tài liệu dùng cùng một mã ID nội bộ trong hai database khác nhau.
2. **Authorization:** Bob thuộc Organization A có xem được `Document A-102` không? Đáp án cũng phải là không nếu chỉ ADMIN được xem.

Một ứng dụng có thể phân tách tenant rất tốt nhưng vẫn lộ tài liệu riêng tư giữa hai người dùng **cùng tenant**. Ngược lại, kiểm tra ACL từng document đúng nhưng quên giới hạn tenant ở repository cũng có thể làm lộ dữ liệu giữa các tổ chức.

### 1.1. Ba phạm vi nhận diện

| Phạm vi | Ví dụ | Điều cần bảo đảm |
|---|---|---|
| **Tenant/organization** | `org-a`, `org-b` | Không đọc/ghi dữ liệu của tenant khác |
| **Actor/principal** | User Alice, Bob | Danh tính đã được xác thực, gắn với tenant phù hợp |
| **Resource permission** | Bob có `document:read` với A-101 | Quyết định cấp quyền phù hợp resource, action và ngữ cảnh |

Không gộp chúng vào một thuộc tính như `userId` duy nhất nếu domain cần quyền theo role/group/document hoặc nhiều organization memberships.

### 1.2. Quyền có thể thay đổi nhanh hơn dữ liệu

Một Document có thể giữ nội dung không đổi nhiều tháng, nhưng Bob bị thu hồi quyền xem ngay hôm nay. Cache nội dung có thời gian sống một giờ không có nghĩa Bob vẫn được xem trong một giờ nữa.

**Dữ liệu được cache lâu và quyết định cấp quyền có thời hạn hiệu lực khác nhau**. Đây là điểm cần thiết kế rõ, đặc biệt khi cho phép chuyển tenant, đổi vai trò và revoke user.

## 2. Cache của Hibernate hoạt động ở những tầng nào?

Hibernate ORM có ít nhất hai loại cache liên quan trực tiếp:

- **First-level cache (L1) / Persistence Context:** gắn với một `Session` hoặc `EntityManager`; giữ các managed entities, identity map và trạng thái phục vụ dirty checking.
- **Second-level cache (L2):** tùy cấu hình, giữ trạng thái entity/collection giữa các Session/EntityManager trong cùng `SessionFactory`.
- **Query cache:** tùy cấu hình, lưu kết quả những query được đánh dấu cacheable; phải phối hợp với cơ chế cập nhật timestamps/query spaces và L2 tùy dạng kết quả.

Ứng dụng còn có thể dùng:

- Spring Cache (`@Cacheable`).
- Redis, Memcached hoặc in-process Caffeine.
- Cache authorization của chính sách/quyền trong service.
- HTTP response cache, CDN, reverse proxy.
- Client-side cache hoặc offline storage.

Các cache ngoài Hibernate **không tự nhận cơ chế tenant isolation của Hibernate**.

### 2.1. Sơ đồ đường truy cập

```text
HTTP request
    |
    v
Authentication + tenant resolution
    |
    v
Authorization / policy decision
    |
    v
Application service / repository
    |
    +--> Application cache (Redis / Spring Cache)
    |       key do ứng dụng thiết kế
    |
    v
Hibernate Session / EntityManager
    |
    +--> L1 Persistence Context
    |       identity trong context hiện tại
    |
    +--> L2 entity / collection cache
    |       provider key theo mapping / tenant
    |
    +--> Query cache (nếu bật + cacheable)
    |
    v
SQL với tenant / permission restrictions
    |
    v
Database
```

Mỗi mũi tên là một chỗ cần xem xét: cache hit ở tầng trên có thể trả object mà **không chạy repository query** vốn từng kiểm tra tenant và permission.

## 3. First-level cache: identity của entity trong một Session

Trong cùng `EntityManager`, Hibernate thường giữ một managed instance cho mỗi entity key:

```java
Document first = em.find(Document.class, documentId);
Document second = em.find(Document.class, documentId);

System.out.println(first == second); // Thông thường true.
```

Kết quả `find` thứ hai có thể lấy từ L1, không tạo SQL SELECT mới. Điều này giúp tăng hiệu năng và bảo đảm identity consistency trong một persistence context.

### 3.1. Vì sao L1 cần ranh giới tenant chặt?

Một Session được tạo trong ngữ cảnh tenant A **không nên được chuyển thành Session của tenant B giữa chừng**.

Ví dụ pattern sai về kiến trúc:

```java
// Ý tưởng sai: một EntityManager dài hạn dùng cho mọi request.
EntityManager sharedEntityManager = factory.createEntityManager();

handleRequestFromOrgA(sharedEntityManager);
setCurrentTenant("org-b");
handleRequestFromOrgB(sharedEntityManager);
```

Ngoài vấn đề thread-safety (EntityManager không được chia sẻ đồng thời giữa các request), identity map đã chứa entity của tenant A. Đổi biến tenant bên ngoài không làm những object đó tự biến mất hoặc biến thành entity của B.

**Không đổi tenant identifier của một Session đang hoạt động để phục vụ người dùng khác.**

### 3.2. Cách tốt hơn

- Xác định tenant từ authenticated request/context.
- Tạo `EntityManager`/Session trong đúng phạm vi tenant.
- Sử dụng theo một transaction/request có kiểm soát.
- Đóng hoặc giải phóng context sau unit of work.
- Không chia sẻ EntityManager instance giữa threads hoặc users.

Ví dụ khái niệm:

```text
Request Alice, org-a -> Session A -> Persistence Context A
Request Carol, org-b -> Session B -> Persistence Context B

Không có:
    Session global được tái sử dụng và đổi org liên tục.
```

### 3.3. Không nhầm L1 cache với dữ liệu authorization

Ngay cả trong Session tenant A, managed `Document` có thể thuộc nhóm ADMIN_ONLY. Hibernate không biết Bob đang là VIEWER chỉ vì object đã nằm trong L1.

Service vẫn cần kiểm tra Bob có quyền đọc Document tương ứng trong **ngữ cảnh request hiện tại**.

## 4. Second-level cache: tenant là một phần của entity identity khi Hibernate multi-tenancy được cấu hình đúng

Hibernate L2 cache lưu state của entity theo những khóa do Hibernate/cache access strategy tạo. Trong cơ chế multi-tenancy của Hibernate, khóa cache thường bao gồm:

- Entity type/entity name.
- Entity identifier.
- Tenant identifier được gắn vào Session.
- Những thành phần nội bộ cần thiết của cache key theo version/region.

Ví dụ khái niệm:

```text
Tenant org-a:
    Document(id=101) -> "Nội dung của A"

Tenant org-b:
    Document(id=101) -> "Nội dung của B"

Hibernate L2 cache keys (minh họa):
    (Document, 101, org-a) -> state A
    (Document, 101, org-b) -> state B
```

Nếu cấu hình multi-tenancy và provider hoạt động đúng, hai entity cùng ID ở hai tenant vẫn là **hai cache entries khác nhau**.

### 4.1. Không nên tự suy luận từ key ví dụ

Cấu trúc key thực tế là chi tiết triển khai phụ thuộc Hibernate version, cache region/provider và cấu hình. Ứng dụng không nên tự đọc/ghi trực tiếp L2 cache theo các key tự chế như trên.

Điều cần đảm bảo về thiết kế là: **tenant identifier chính xác phải gắn vào mọi Session được sử dụng trong multi-tenant access**, và mọi custom cache nằm ngoài Hibernate phải có namespace tương ứng.

### 4.2. Hibernate không thể bảo vệ tenant bị khai báo sai

Nếu request org-a vô tình được mở với tenant ID org-b, Hibernate sẽ vận hành theo tenant ID **được cung cấp cho Session**. Nó không có khả năng đoán ý định đúng từ user JWT nếu application resolver đưa sai ID.

Tương tự, nếu ứng dụng không bật cơ chế tenant-aware mapping, mà chỉ dùng một column `organizationId` bình thường rồi tự viết `where` ở mọi nơi, không thể mặc định cache key của entity L2 sẽ thêm organization ID vào identity.

### 4.3. Key theo ID khi dùng shared table thủ công

Một schema single-table:

```sql
CREATE TABLE documents (
    id BIGINT PRIMARY KEY,
    organization_id VARCHAR(64) NOT NULL,
    title VARCHAR(200) NOT NULL
);
```

Nếu ID là **primary key toàn cục**, cùng một ID không thể xuất hiện cho hai tổ chức trong bảng này. Khi ấy L2 entity state theo ID có thể đúng ở mức identity dữ liệu.

Nhưng **identity đúng không đồng nghĩa authorization đúng**: việc entity có `organizationId="org-b"` vẫn không nên được trả cho org-a nếu có code gọi `find(Document.class, id)` rồi bỏ qua kiểm tra scope.

Nếu ID chỉ unique **bên trong từng tenant**, cần schema/composite key/tenant-aware mapping tương ứng. Không tạo hai row trùng ID trong một bảng với PK chỉ gồm `id`.

## 5. Những mô hình multi-tenancy thường gặp

Có ba kiểu triển khai phổ biến về mặt kiến trúc:

| Mô hình | Lưu trữ | Đặc điểm |
|---|---|---|
| **Database per tenant** | Mỗi tenant một database | Cách ly vật lý mạnh, vận hành connection/migration phức tạp |
| **Schema per tenant** | Cùng database, schema khác nhau | Cần chuyển schema/connection đúng tenant |
| **Shared schema + tenant discriminator** | Nhiều tenant chung bảng, thêm `tenant_id` | Triển khai tập trung, cần lọc tenant nghiêm ngặt |

Hibernate hỗ trợ nhiều chiến lược qua các API multi-tenancy theo phiên bản. Với ứng dụng dùng Hibernate 6+, có thể dùng `@TenantId` cho một số mô hình discriminator-based multi-tenancy; database/schema separation có thể dùng `MultiTenantConnectionProvider` và tenant resolver.

### 5.1. Không tự áp nguyên cấu hình một chiến lược sang chiến lược khác

- Database-per-tenant cần định tuyến connection tới database đúng.
- Schema-per-tenant cần schema/current_schema đúng cho connection.
- Shared-table discriminator cần predicate tenant đúng trong câu SQL và mapping.
- Các tầng cache phải phù hợp cách Hibernate nhìn tenant identity.

Đổi cấu hình multi-tenancy là một thay đổi kiến trúc persistence, cần integration tests trên đường đọc **và** ghi.

## 6. @TenantId: ví dụ tenant discriminator của Hibernate

Trong những phiên bản Hibernate ORM hỗ trợ `org.hibernate.annotations.TenantId`, entity có thể khai báo thuộc tính tenant:

```java
import jakarta.persistence.*;
import org.hibernate.annotations.TenantId;

@Entity
@Table(name = "documents")
public class Document {

    @Id
    @GeneratedValue(strategy = GenerationType.SEQUENCE)
    private Long id;

    @TenantId
    @Column(name = "tenant_id", nullable = false)
    private String tenantId;

    @Column(nullable = false)
    private String title;

    @Column(nullable = false)
    private String classification;

    protected Document() {}

    public Long getId() {
        return id;
    }

    public String getTenantId() {
        return tenantId;
    }

    public String getTitle() {
        return title;
    }
}
```

Ở cơ chế này, Hibernate dùng tenant identifier gắn với Session để quản lý thuộc tính tenant và lọc truy vấn phù hợp theo mapping.

**`@TenantId` là tính năng Hibernate**, không phải annotation JPA portable. Cần kiểm tra đúng phiên bản Hibernate ORM, Jakarta Persistence và tài liệu mapping của nhánh ứng dụng đang dùng.

### 6.1. Không nhận tenant ID từ một header tùy ý rồi tin ngay

Sai về trust boundary:

```java
// Không nên lấy header bất kỳ làm tenant đáng tin.
String tenant = request.getHeader("X-Tenant-Id");
```

Header có thể bị người dùng sửa. Tenant context phải đến từ identity đã được xác thực và **membership/tenant-selection đã được authorization**.

Nếu một user có thể là thành viên của nhiều tổ chức, client có thể yêu cầu một org cụ thể, nhưng server phải kiểm tra user đang là thành viên hợp lệ và có quyền vào org đó trước khi tạo Session.

### 6.2. Resolver ví dụ

Hibernate có `CurrentTenantIdentifierResolver` ở những phiên bản phù hợp:

```java
import org.hibernate.context.spi.CurrentTenantIdentifierResolver;

public final class AuthenticatedTenantResolver
        implements CurrentTenantIdentifierResolver<String> {

    private final VerifiedTenantContext context;

    public AuthenticatedTenantResolver(
            VerifiedTenantContext context) {
        this.context = context;
    }

    @Override
    public String resolveCurrentTenantIdentifier() {
        return context.requireAuthorizedTenantId();
    }

    @Override
    public boolean validateExistingCurrentSessions() {
        return true;
    }
}
```

`VerifiedTenantContext` là abstraction minh họa của ứng dụng; nó phải cung cấp tenant đã được xác minh từ authentication/authorization layer. Không nên dùng `ThreadLocal` toàn cục không cleanup như một giải pháp đầy đủ cho async/reactive execution.

Cách đăng ký resolver có thể qua Hibernate bootstrap/configuration, ví dụ property cấu hình tương ứng với `hibernate.tenant_identifier_resolver`; kiểm tra API và hệ thống DI của phiên bản thực tế.

### 6.3. Tenant ID phải ổn định trong vòng đời Session

Nếu một user chuyển từ Organization A sang Organization B giữa một request, ứng dụng không nên tiếp tục dùng EntityManager cũ và chỉ sửa biến context.

Một cách an toàn:

1. Kết thúc unit of work của org A.
2. Kiểm tra user được chọn org B.
3. Mở một persistence context/transaction phù hợp với org B.
4. Thực hiện query trong context mới.

Đối với connection pooling, không để schema/current tenant database context bị rò sang request kế tiếp do connection không được reset đúng.

## 7. Nếu dùng organizationId bình thường thay vì multi-tenancy tự động

Nhiều ứng dụng không dùng `@TenantId` mà tự ánh xạ:

```java
@Entity
@Table(name = "documents")
public class Document {

    @Id
    private Long id;

    @Column(name = "organization_id", nullable = false)
    private UUID organizationId;

    private String title;
}
```

Trong mô hình này, Hibernate hiểu `organizationId` là một thuộc tính thông thường.

Query an toàn cần scope rõ:

```java
public Optional<Document> findInOrganization(
        UUID orgId,
        Long documentId) {

    return em.createQuery("""
        select d
        from Document d
        where d.id = :id
          and d.organizationId = :orgId
        """, Document.class)
        .setParameter("id", documentId)
        .setParameter("orgId", orgId)
        .getResultStream()
        .findFirst();
}
```

Đây là ví dụ 0..1 theo primary key. `getResultStream().findFirst()` không thay thế unique constraint nếu query không thật sự bị khóa bởi PK.

### 7.1. Cẩn thận với find(id)

```java
Document document = em.find(Document.class, documentId);
```

Nếu Hibernate không được cấu hình để tự áp tenant restriction, `find` theo ID có thể tìm resource bất kể `organizationId`. Người dùng biết một ID của tenant khác có thể khai thác **Insecure Direct Object Reference (IDOR)** nếu service trả kết quả mà không kiểm tra.

Vì vậy:

- Dùng query scoped `where id = :id and organizationId = :orgId`.
- Hoặc dùng tenant-aware mapping/Session đã kiểm chứng.
- Kết hợp authorization ở service khi resource có ACL riêng.
- Không coi “ID khó đoán” là kiểm soát bảo mật.

### 7.2. Không giả định annotation filter tự áp mọi đường truy cập

`@Filter` hoặc `@SQLRestriction` có thể giúp hạn chế visibility theo mapping/Session trong các phiên bản Hibernate. Nhưng cần kiểm tra chúng có ảnh hưởng thế nào đến `find`, association, HQL mutation và native SQL.

**Không dùng một annotation như lời cam kết duy nhất rằng mọi query đường vòng đều tenant-safe.** Thiết kế security boundary và integration tests theo từng API thực tế.

## 8. Authorization khác tenant identity

Giả sử Document#101 thuộc org A nhưng chỉ ADMIN được xem.

```text
Tenant check:
    Document.organizationId == currentOrganization

Permission check:
    action = READ_DOCUMENT
    actor = Bob
    resource = Document#101
    requiredRole = ADMIN

Bob là VIEWER -> DENY
```

Nếu `Document#101` đã được Hibernate L2 cache vì Alice vừa đọc, Bob đọc lại cùng entity trong org A có thể hit cache state rất nhanh. Điều này **không tự tạo permission check**.

### 8.1. L2 cache lưu entity state, không lưu “quyết định được xem”

Hibernate cache không biết toàn bộ quy tắc IAM/RBAC/ABAC của ứng dụng:

- Vai trò user hiện tại.
- Nhóm/project membership.
- Resource ACL được thay đổi.
- Chính sách thời gian/địa điểm.
- Quyền được ủy quyền tạm thời.
- Data classification và policy mới.

Vì vậy repository/service phải thực thi authorization **cho request hiện tại**, kể cả khi lấy được entity từ cache.

### 8.2. Kiểm tra tenant và quyền ở service

Ví dụ minh họa:

```java
@Transactional(readOnly = true)
public DocumentDto getDocument(
        AuthenticatedPrincipal principal,
        UUID requestedOrgId,
        Long documentId) {

    tenantAccess.requireMembership(
        principal,
        requestedOrgId
    );

    Document document = documentRepository
        .findInOrganization(requestedOrgId, documentId)
        .orElseThrow(DocumentNotFoundException::new);

    documentPolicy.requireCanRead(
        principal,
        document
    );

    return documentMapper.toDto(document);
}
```

Các abstraction `AuthenticatedPrincipal`, `tenantAccess`, `documentPolicy` và DTO là thành phần ứng dụng, không phải API JPA có sẵn.

Ở đây có **hai bước riêng**:

1. Scope resource vào tenant đã được phép.
2. Kiểm tra quyền thao tác của actor đối với resource.

Nếu hệ thống cố tình trả 404 thay vì 403 để giảm lộ sự tồn tại của resource, cần áp dụng chính sách đó nhất quán ở API layer; không bỏ qua authorization trong repository.

## 9. Cache key: dữ liệu của ai, quyền của ai?

Ở cache do ứng dụng tự tạo, key thiếu scope là nguyên nhân phổ biến gây lộ dữ liệu.

Ví dụ nguy hiểm:

```java
@Cacheable(cacheNames = "documentDetail", key = "#documentId")
public DocumentDto getDocument(Long documentId) {
    ...
}
```

Nếu `documentId` không duy nhất giữa tenants hoặc DTO được dựng theo quyền user, cache có thể trả dữ liệu sai:

```text
Cache key = 101

Org A request -> cache Document A-101
Org B request -> hit key 101 -> nhận A-101
```

### 9.1. Chọn key theo phạm vi phụ thuộc của dữ liệu

Với cached DTO phụ thuộc org và ID:

```text
document:org-a:101
document:org-b:101
```

Với DTO đã được redacted/filtered theo actor:

```text
document-view:org-a:user-bob:101:permission-v7
```

Tuy nhiên, đưa user ID và permission version vào key là một lựa chọn, **không có nghĩa mọi hệ thống đều nên cache user-specific views**. Nếu quyền thay đổi nhanh, tốt hơn là cache dữ liệu không nhạy với quyền và kiểm tra authorization lại mỗi lần.

### 9.2. Không lưu key chỉ bằng giá trị client gửi

Nếu key dùng `orgId` do client khai báo mà chưa xác minh, người dùng có thể yêu cầu key của org khác. Việc key có org prefix không ngăn truy cập trái phép nếu API trả cache entry trước khi xác thực membership.

Đúng hơn:

```text
Authenticated request
     |
     v
Resolve & authorize effective org
     |
     v
Build key from verified effective org
     |
     v
Check cache
     |
     v
Authorize resource/action appropriately
     |
     v
Return permitted response
```

## 10. Các mô hình cache key cần phân biệt

| Dữ liệu cache | Scope tối thiểu cần xét | Vì sao |
|---|---|---|
| Entity Hibernate L2 trong multi-tenancy chuẩn | Tenant-aware Hibernate entity identity | Hibernate quản lý key; không tự đặt chuỗi |
| DTO chung trong một tổ chức | Verified org ID + resource ID + representation version | Tránh trùng key và thay đổi schema DTO |
| Danh sách tài liệu của một org | Org ID + filter/sort/page + policy scope | Tránh lấy list từ org/điều kiện khác |
| Dashboard theo user | Org ID + user ID + query params + permission state | Kết quả có thể phụ thuộc actor |
| Permission decision | Actor ID + org ID + action + resource + policy version | Quyền có thể được revoke |
| Role/membership | Org ID + user ID + membership version hoặc invalidation | Membership biến đổi |
| Negative lookup (“không tìm thấy”) | Org ID + resource/lookup scope | Không dùng negative cache toàn cục cho ID trùng tenant |
| HTTP response | Authenticated scope, private headers hoặc no-store | CDN/browser không biết RBAC nếu key thiếu |
| Product catalog công khai | Có thể global nếu thực sự public, immutable/scope rõ | Không cần user key khi không chứa dữ liệu riêng tư |

Key cần bao gồm **mọi tham số thay đổi giá trị trả về**. Ví dụ list query có sort/filters/page; nếu cache chỉ dùng org ID, response ở trang 1 có thể bị trả ở trang 2.

### 10.1. Không lưu bí mật trực tiếp trong key/log

Không đưa access token, mật khẩu, raw session cookie, nhạy cảm PII vào key cache hoặc log. Nếu cần định danh actor, dùng internal ID ổn định và giới hạn visibility của cache infrastructure.

### 10.2. Namespace và version

Một key ứng dụng có thể theo cấu trúc:

```text
rental:v3:tenant:{tenantId}:document:{documentId}
```

Version hữu ích khi đổi cấu trúc serialization, nhưng không thay thế tenant isolation hay invalidation permission.

## 11. Cache tại application service: thứ tự kiểm tra rất quan trọng

Một service có `@Cacheable` có thể bỏ qua thực thi body khi cache hit. Vì thế nếu kiểm tra authorization **bên trong method body được cache**, request sau có thể không chạy kiểm tra ấy.

Ví dụ sai về ý tưởng:

```java
@Cacheable(cacheNames = "documents", key = "#id")
public DocumentDto loadDocument(Long id) {
    policy.requireCanRead(currentUser(), id);
    return repository.loadDto(id);
}
```

Một lần cache hit có thể trả DTO mà không gọi `policy.requireCanRead(...)` trong body nữa.

### 11.1. Tách authorization khỏi method được cache

Một cấu trúc rõ:

```java
public DocumentDto getForUser(
        Principal principal,
        UUID organizationId,
        Long documentId) {

    membership.requireActive(
        principal,
        organizationId
    );

    policy.requireCanRead(
        principal,
        organizationId,
        documentId
    );

    return documentContentCache.load(
        organizationId,
        documentId
    );
}
```

Method cache chỉ chứa dữ liệu không phân biệt user:

```java
@Cacheable(
    cacheNames = "documentContent",
    key = "#organizationId.toString() + ':' + #documentId"
)
public DocumentDto load(
        UUID organizationId,
        Long documentId) {
    return repository.loadSharedDto(
        organizationId,
        documentId
    );
}
```

**Lưu ý:** Ví dụ chỉ an toàn nếu `DocumentDto` được phép chia sẻ cho mọi user **sau khi** policy check thành công và không chứa field khác nhau theo user/role. Nếu DTO có dữ liệu phải redaction, phải cache representation có scope phù hợp hoặc tạo authorized view sau cache.

### 11.2. Spring AOP và self-invocation

Với Spring proxy-based caching, method trong cùng bean tự gọi method `@Cacheable` có thể không đi qua cache proxy. Điều này chủ yếu là correctness/performance issue; nhưng thiết kế security không được dựa vào việc “proxy có chạy hay không” để bảo đảm quyền.

Kiểm soát authorization ở service boundary có thể kiểm thử độc lập với cache hit/miss.

## 12. Query cache: query giống nhau chưa chắc có cùng quyền

Hibernate query cache không đơn thuần là một map từ chuỗi HQL sang kết quả. Nó có key/metadata liên quan query, parameters, pagination, filter state, query spaces và tenant context tùy version.

Trong multi-tenancy được cấu hình đúng, Hibernate cần tách kết quả query theo tenant identifier. Tuy nhiên, **đừng suy ra Hibernate hiểu các chính sách ACL tùy biến bên ngoài query**.

Ví dụ query:

```java
List<Document> docs = em.createQuery("""
    select d
    from Document d
    where d.status = 'ACTIVE'
    order by d.id
    """, Document.class)
    .setHint("org.hibernate.cacheable", true)
    .getResultList();
```

Nếu không có tenant-aware mapping hoặc predicate tenant rõ, query cache có thể cache một tập kết quả không đúng scope ngay từ lần đầu. Không có cache key nào sửa được một query thiếu điều kiện bảo mật.

### 12.1. Cacheable query cần đúng predicate

Với shared-table manual scoping:

```java
List<Document> docs = em.createQuery("""
    select d
    from Document d
    where d.organizationId = :orgId
      and d.status = 'ACTIVE'
    order by d.id
    """, Document.class)
    .setParameter("orgId", authorizedOrgId)
    .setHint("org.hibernate.cacheable", true)
    .getResultList();
```

Trong ví dụ, `authorizedOrgId` phải đến từ tenant context đã được xác minh. Parameter organization tham gia semantics query và thường là thành phần query cache key do Hibernate quản lý.

### 12.2. User permission không có trong query thì query cache không thể biết

Nếu query chỉ lọc organization và status mà policy yêu cầu document-level ACL, query trả tất cả documents của org — dù Hibernate query cache hoạt động đúng.

Để đảm bảo authorization:

- Thêm ACL predicate vào query nếu thích hợp.
- Hoặc lấy candidate IDs rồi kiểm tra chính sách cho user trước khi trả.
- Hoặc tách cache dữ liệu khỏi policy evaluation như phần trước.

Đối với dữ liệu nhạy cảm, nên **tránh query cache user-specific** nếu không chứng minh được key, dependency và invalidation của permission state.

### 12.3. Query cache và thay đổi quyền

Giả sử query cacheable lọc tài liệu theo join ACL:

```sql
select d
from Document d
join d.permissions p
where p.user.id = :userId
  and p.canRead = true
```

Câu query phụ thuộc row permission. Khi permission đổi:

- Nếu thay đổi qua Hibernate trong mapping/query spaces được theo dõi, cơ chế invalidation của Hibernate có thể làm query cache stale entry không còn hợp lệ.
- Nếu ACL thay đổi bằng external SQL, Redis, IAM service hoặc provider khác, Hibernate query cache không nhất thiết nhận được thông báo.
- Nếu policy phụ thuộc claim/token bên ngoài DB, query cache không tự hiểu claim đã bị revoke.

Không nên giả định TTL hay Hibernate cache invalidation bao phủ mọi nguồn quyền truy cập.

## 13. Query cache và L2 cache không tương đương

Một query cache có thể lưu kết quả định danh/row data để phục vụ truy vấn, trong khi L2 entity cache có thể lưu entity state. Chi tiết phụ thuộc Hibernate version và query projection.

Ví dụ:

```text
Query cache:
    "Danh sách document ACTIVE của org-a"
       -> [Document ID 101, 102, 103]

L2 cache:
    Document (org-a, 101) -> state
    Document (org-a, 102) -> state
    Document (org-a, 103) -> state
```

Ngay cả khi query result được cache, entity có thể còn cần tải state từ L2 hoặc database. Cache query không có nghĩa mọi entity đều đã có trong L2.

### 13.1. Entity key đúng không sửa query sai

Nếu HQL query của org A sai và lấy IDs của org B, Hibernate L2 có thể trả entity state phù hợp với identity; điều đó không biến resource thành “được phép truy cập”.

**Scope phải được bảo đảm từ query/policy trước khi dữ liệu trở thành kết quả cho user.**

### 13.2. Query cache có thể không mang lợi ích với dữ liệu thay đổi nhiều

Nếu document list thay đổi liên tục, query cache invalidation thường xuyên có thể làm hit rate thấp và tốn thêm memory/metadata. Với list user-specific có ACL biến động, chi phí vận hành và rủi ro stale permissions có thể lớn hơn lợi ích.

Hãy đo thực tế và chọn cache query có semantics ổn định.

## 14. Filter và Session state trong Hibernate

Hibernate có `@FilterDef`, `@Filter` và API `Session.enableFilter(...)` ở các phiên bản hỗ trợ.

Ví dụ về ý tưởng:

```java
Session session = em.unwrap(Session.class);

session.enableFilter("visibleDocuments")
       .setParameter("organizationId", authorizedOrgId);
```

Entity mapping phải định nghĩa filter tương ứng; cú pháp annotation và khai báo parameter type phụ thuộc phiên bản Hibernate nên cần xem tài liệu nhánh đang sử dụng.

### 14.1. Rủi ro khi bật filter muộn

Nếu entity đã được load vào L1 **trước khi bật filter**, việc bật filter không tự xóa object đã managed hoặc bảo đảm mọi direct identity lookup đều được lọc.

```text
Session:
    load Document#9
    enableFilter(...)
    find(Document#9)  -> có thể nhận object đã managed
```

Vì vậy, không dùng việc bật/tắt filter trong một Session đang phục vụ nhiều identity contexts như một biện pháp chuyển tổ chức hoặc role an toàn.

### 14.2. Filter thay đổi không đồng nghĩa role authorization thay đổi

Một filter có thể giới hạn `organization_id` hoặc `deleted=false`. Nhưng quyền chi tiết theo actor/group có thể phải giải quyết ở service/repository và cache ngoài ORM.

Nếu filter parameter chứa user ID hoặc role ID, phải kiểm tra query cache key và invalidation khi membership đổi, không chỉ nhận định “Hibernate đã cache theo query”.

### 14.3. Native SQL thường là đường khác

Native SQL do ứng dụng viết hoặc chạy từ công cụ khác có thể không tự áp Hibernate entity filters và tenant predicates như HQL/Criteria.

Ví dụ native SQL thiếu scope:

```sql
SELECT *
FROM documents
WHERE id = :documentId;
```

Với shared-table manual scoping, nên có predicate:

```sql
SELECT *
FROM documents
WHERE organization_id = :authorizedOrgId
  AND id = :documentId;
```

Với database row-level security (RLS), còn cần bảo đảm session-level database security context được đặt/reset đúng trên pooled connections.

## 15. Entity associations cũng phải được cách ly

Giả sử Document thuộc Organization và có nhiều Comments:

```java
@Entity
public class Comment {

    @Id
    private Long id;

    @ManyToOne(fetch = FetchType.LAZY)
    private Document document;

    private String text;
}
```

Một query trực tiếp Document có thể tenant-safe, nhưng association đến Comment có thể:

- Trỏ nhầm entity khác tenant nếu schema cho phép.
- Chứa bản ghi soft-deleted.
- Chứa comment riêng tư chỉ tác giả/moderator được xem.
- Được cache thành collection trước khi quyền thay đổi.

Không nên suy luận “đã qua một root Document có quyền” nghĩa **mọi field và child association** đều được phép hiển thị.

### 15.1. FK có tenant awareness

Với shared table, một thiết kế database mạnh có thể dùng composite unique/FK kết hợp tenant:

```sql
CREATE TABLE documents (
    id BIGINT NOT NULL,
    organization_id UUID NOT NULL,
    title VARCHAR(200) NOT NULL,
    PRIMARY KEY (organization_id, id)
);

CREATE TABLE comments (
    id BIGINT NOT NULL,
    organization_id UUID NOT NULL,
    document_id BIGINT NOT NULL,
    text VARCHAR(4000) NOT NULL,
    PRIMARY KEY (organization_id, id),
    FOREIGN KEY (organization_id, document_id)
        REFERENCES documents (organization_id, id)
);
```

Schema này minh họa ràng buộc rằng Comment của org A không thể tham chiếu Document của org B qua FK ghép đúng.

Mapping JPA của composite identity/FK cần được thiết kế tương ứng; không chỉ thêm schema rồi mong Hibernate tự map.

### 15.2. Cache collections theo tenant

Hibernate collection cache có identity gắn với role/owner và tenant context trong cấu hình multi-tenancy phù hợp. Nhưng nếu một collection chứa dữ liệu được phân quyền theo **user cụ thể**, việc cache collection chung cho toàn tenant có thể không phản ánh ACL từng actor.

Cần phân biệt:

- Collection entity association mang ý nghĩa dữ liệu domain.
- Danh sách những phần tử mà user hiện tại **được phép xem**.

Danh sách thứ hai là một **authorized view**, không nhất thiết trùng collection cache.

### 15.3. Không serialize toàn bộ entity graph vào cache DTO chung

Một DTO được map từ entity graph có thể chứa embedded permission, comments, private fields. Nếu cache theo org+ID rồi cho mọi user hit, có thể rò dữ liệu dù bản thân Document entity được quyền đọc.

Áp field-level/row-level redaction theo actor sau khi đã lấy dữ liệu chung, hoặc cache theo scope quyền rõ ràng với invalidation đáng tin.

## 16. RBAC, ACL và ABAC tác động tới cache thế nào?

### 16.1. RBAC — role-based access control

Ví dụ:

- ADMIN xem mọi Document trong org.
- EDITOR xem và sửa Document trong project được giao.
- VIEWER chỉ xem tài liệu public-to-org.

Nếu cache view theo role, vẫn phải biết:

- User hiện thuộc role nào?
- Role có quyền phụ thuộc project/group không?
- Policy có thay đổi từ lần cache trước không?

Một key `orgId + roleName` có thể chưa đủ nếu hai VIEWER có project permissions khác nhau.

### 16.2. ACL — Access Control List

Ví dụ Document có `document_permissions`:

```text
(document_id, user_id, permission)
(101, Alice, READ)
(101, Alice, WRITE)
(101, Bob, READ)
```

Cache document content theo org+document ID có thể phù hợp nếu authorization luôn được kiểm tra trước trả dữ liệu. Cache một danh sách “documents visible to Bob” cần invalidation khi ACL của Bob thay đổi.

### 16.3. ABAC — Attribute-based Access Control

Policy phụ thuộc attributes như:

- Department.
- Classification.
- Project status.
- Employee contract.
- Địa điểm/thiết bị/thời gian.
- Risk score.

Có những attributes thay đổi thường xuyên. Cache permission decision với TTL dài có thể nguy hiểm hơn cache entity state. Một số policy đòi re-evaluate mỗi request hoặc phải dùng epoch/version có thể invalidated ngay.

### 16.4. Đừng dùng role là tenant identifier

Tenant identifier giải quyết **phạm vi tổ chức**, role giải quyết **mức quyền trong tổ chức**. Không biến `tenantId = "admin"` hoặc tạo một tenant riêng cho mỗi role để thay thế authorization, trừ khi kiến trúc thật sự thiết kế isolation domain độc lập như thế.

## 17. Cache quyết định cấp quyền: khi nào có thể dùng?

Giả sử service kiểm tra:

```java
boolean allowed = policy.canRead(
    principal,
    orgId,
    documentId
);
```

Nếu kiểm tra tốn thời gian, có thể cache quyết định. Nhưng đây là cache **nhạy cảm bảo mật**.

Một permission cache key minh họa:

```text
authz:
    orgId=org-a:
    principalId=bob:
    action=read:
    resourceId=doc-101:
    policyVersion=42
```

### 17.1. Bảo đảm đầy đủ dependencies

Một permission decision có thể phụ thuộc:

- User status (active/disabled).
- Org membership.
- Group memberships.
- Assigned roles.
- Document owner/classification.
- Explicit allow/deny ACL.
- Policy definition.
- Risk/context request.

Nếu key hoặc invalidation không bao quát các dependencies quan trọng, cache có thể giữ quyết định “allow” sau khi quyền bị revoke.

### 17.2. TTL không bảo đảm revoke ngay

Giả sử TTL là 10 phút, admin thu hồi quyền lúc 09:00:

```text
08:59 -> canRead(Bob, Doc) = true -> cache "allow"
09:00 -> admin revokes permission in DB
09:01 -> cached "allow" vẫn tồn tại nếu chưa invalidate
```

Nếu policy yêu cầu revoke có hiệu lực tức thì hoặc gần tức thì, TTL 10 phút là không phù hợp.

Lựa chọn:

- Invalidate chính xác theo principal/resource khi quyền đổi.
- Tăng `permissionVersion`/security epoch và đưa vào key.
- Cache với TTL rất ngắn cộng event invalidation, nếu mức trễ chấp nhận.
- Không cache kết quả “allow” cho thao tác nhạy cảm, luôn kiểm tra source of truth.
- Dùng centralized authorization service với contract staleness rõ.

### 17.3. Negative caching cũng cần xem xét

Cache “DENY” có thể khiến user vừa được cấp quyền vẫn không thể truy cập trong một thời gian. Đây chủ yếu là availability/UX issue, nhưng cũng ảnh hưởng correctness.

Không thiết kế invalidation chỉ cho revoke mà quên grant, group join/leave và resource policy change.

## 18. Khi role hoặc membership thay đổi, cache nào cần bị ảnh hưởng?

Giả sử Bob được đổi từ ADMIN thành VIEWER. Những lớp dữ liệu liên quan có thể bao gồm:

| Dữ liệu đang cache | Có cần invalidate/đánh giá lại? | Lý do |
|---|---|---|
| Document entity L2 state không có field quyền theo user | Có thể giữ | Nội dung entity không đổi, nhưng authz phải đánh giá lại |
| Permission decision `canEdit(Bob, Doc)` | Có | Role vừa đổi |
| User dashboard DTO đã redacted theo role | Có | View theo quyền đã khác |
| Query result “admin-only docs for Bob” | Có | Membership/role thay đổi |
| Session/JWT chứa claim role cũ | Cần chiến lược token/version/revoke | Claim có thể stale ngoài Hibernate |
| CDN response được cache private data | Phải bảo đảm không phục vụ lại sai actor | Có thể cần purge/no-store |
| Redis list “documents Bob can read” | Có | Danh sách phụ thuộc ACL/role |

Một thay đổi role **không nhất thiết làm Document entity state cũ trong L2 sai**, nhưng có thể làm một số **cached authorized views** sai ngay lập tức.

### 18.1. Sửa đúng tầng

Nếu permission policy đổi, evict toàn bộ L2 `Document` chưa chắc giải quyết vấn đề: nếu Spring Cache đang giữ một response “Bob is admin”, response ấy vẫn có thể được trả.

Ngược lại, clear quyền cache mà query repository thiếu tenant predicate vẫn không ngăn cross-tenant lookup.

**Inval­i­da­tion phải nhắm vào đúng loại dữ liệu và dependency.**

## 19. Dữ liệu stale trong L1, L2 và permission cache

Ba dạng stale cần phân biệt:

1. **Entity stale:** Nội dung document trong object/cache khác DB.
2. **Query stale:** Danh sách document không còn phản ánh status/ACL mới.
3. **Permission stale:** Quyết định “được xem” không còn đúng sau revoke.

Ví dụ:

```text
T0: Doc content = "A"; Bob canRead = true
T1: cache Doc content = "A"
T2: Alice updates Doc content to "B"
T3: Admin revokes Bob's access
T4: Bob requests Doc
```

Một thiết kế đúng ở T4 phải bảo đảm:

- Bob bị chặn bởi authorization mới, **bất kể content cache đang chứa "A" hay "B"**.
- Nếu Alice truy cập, content version/freshness theo consistency contract ứng dụng.
- Không dùng một cache invalidation duy nhất như câu trả lời cho cả hai vấn đề.

### 19.1. Read-after-write consistency

Một service vừa cập nhật Document và đọc lại trong cùng transaction có thể thấy managed state mới trong L1, nhưng các request khác có thể thấy nội dung cũ từ cache nếu invalidation không nhất quán.

Hibernate hỗ trợ nhiều concurrency strategies cho L2 cache; cần chọn theo dữ liệu có được update không và isolation cần đạt. Dù cache coherence tốt, authorization vẫn là bài toán riêng.

### 19.2. Long-lived Session và permission revoke

Nếu Session mở rất lâu, object có thể đã được load trước khi quyền bị revoke. Service không nên hiểu “object đã trong Session” là được phép dùng vĩnh viễn.

Đối với operation nhạy cảm, cần kiểm tra quyền hiện tại hoặc security epoch; cân nhắc giảm lifespan của Session. Hibernate Session không phải nơi lưu trữ quyền truy cập dài hạn.

## 20. Cache concurrency strategies và giới hạn bảo mật

Hibernate L2 cache có các concurrency strategies/tùy chọn mapping như:

- `READ_ONLY`.
- `NONSTRICT_READ_WRITE`.
- `READ_WRITE`.
- `TRANSACTIONAL` nếu cache provider hỗ trợ.

Những strategy này chủ yếu liên quan **tính nhất quán dữ liệu entity/cache khi có update**, không phải authorization theo user.

### 20.1. READ_ONLY không có nghĩa public

Một Document ít thay đổi có thể dùng READ_ONLY cache nếu dữ liệu thực sự immutable theo mapping, nhưng vẫn có thể là ADMIN_ONLY. Không vì cache read-only mà cho mọi user đọc.

### 20.2. NONSTRICT_READ_WRITE có cửa sổ stale

Dữ liệu có thể bị stale ngắn hạn theo contract concurrency strategy. Với dữ liệu công khai hoặc ít nhạy, điều này có thể chấp nhận. Với quyết định quyền truy cập, **đừng lấy strategy entity cache làm mô hình revoke**.

### 20.3. TRANSACTIONAL phụ thuộc provider

Một cache provider hỗ trợ transactional semantics không tự biết các giao dịch bên ngoài như IAM service, message bus, hay thay đổi JWT. Cần thiết kế consistency xuyên hệ thống riêng.

## 21. Soft delete và phân tách dữ liệu

Nhiều ứng dụng đánh dấu bản ghi bị xóa:

```java
private Instant deletedAt;
```

Query:

```java
List<Document> docs = em.createQuery("""
    select d
    from Document d
    where d.organizationId = :orgId
      and d.deletedAt is null
    """, Document.class)
    .setParameter("orgId", orgId)
    .getResultList();
```

Nếu một Document bị soft-delete, không chỉ entity state mà cả cached list/DTO/permission views có thể phải được invalidated.

### 21.1. Query cache cũ có thể giữ IDs của deleted items

Hibernate query cache có cơ chế invalidation dựa trên tracked query spaces khi updates do Hibernate quản lý. Nhưng native SQL/external writers, customized cache hoặc application-level list cache có thể không được đồng bộ.

Không dùng cached document list mà bỏ qua check soft delete nếu đối tượng có thể đã bị xóa.

### 21.2. Direct ID lookup và soft delete

Một code path dùng `em.find(Document.class, id)` trong manual soft-delete model có thể lấy entity có `deletedAt != null` nếu không có restriction đúng. Cache hit càng làm việc bỏ qua predicate dễ bị giấu khỏi SQL logs.

Tầng service/repository phải thống nhất chính sách “deleted resources không thể truy cập” qua mọi path.

### 21.3. Hibernate @SoftDelete là tính năng theo version

Hibernate hỗ trợ mapping soft delete chuyên biệt ở các phiên bản nhất định; các phiên bản cũ có thể dùng `@SQLDelete`, `@Where` hoặc `@Filter`.

Tính năng mapping có hỗ trợ query direct lookup, association, bulk HQL, L2 cache và native SQL thế nào cần kiểm thử theo đúng version. Không mặc định mọi loại mutation và cache đều tuân một cách hoàn hảo nếu không có test.

## 22. Bulk HQL/Criteria DML và cache isolation

Bulk DML có thể cập nhật nhiều rows mà không đi qua dirty checking từng entity.

Ví dụ:

```java
int updated = em.createQuery("""
    update Document d
    set d.status = 'ARCHIVED'
    where d.organizationId = :orgId
      and d.status = 'EXPIRED'
    """)
    .setParameter("orgId", authorizedOrgId)
    .executeUpdate();
```

Cần nhớ:

- Bulk DML không tự refresh các managed entities đang trong L1.
- L2/query cache có cơ chế invalidation riêng khi Hibernate biết query spaces, tùy version/strategy.
- `@Version` có thể không tăng tự động như entity lifecycle update.
- Entity listeners/callbacks không chạy per-row.
- Nếu mutation ảnh hưởng visibility, application caches/authorized views cần được invalidated tương ứng.

### 22.1. Đừng dựa vào SQL WHERE của SELECT để scope UPDATE/DELETE

Một query SELECT có tenant predicate không có nghĩa một bulk UPDATE viết riêng cũng có predicate ấy. Cần xác minh tenant restriction được Hibernate áp dụng đúng cho **bulk DML path**, hoặc đưa predicate tenant tường minh khi dùng manual scoping.

Ví dụ dangerous HQL:

```sql
update Document d
set d.status = 'ARCHIVED'
where d.status = 'EXPIRED'
```

Nếu không dùng tenant-aware Hibernate mechanism phù hợp và dữ liệu chung bảng, câu query này có thể ảnh hưởng nhiều tổ chức.

### 22.2. Clear không phải security invalidation

`em.clear()` xóa state managed trong một EntityManager, không xóa:

- Redis/Spring Cache entries.
- L2 cache ở mọi SessionFactory.
- Browser/CDN caches.
- Permission decisions ngoài database.

Mỗi tầng cần invalidation riêng dựa trên contract.

## 23. Native SQL, scheduled jobs và external writes

Background jobs thường chạy mà không có HTTP request principal. Điều này làm tenant context resolution phức tạp hơn:

```text
Job: archive all expired documents

Question:
    Chạy cho tenant nào?
    Có quyền xử lý mọi tenant không?
    Session/connection đang gắn tenant nào?
    Cập nhật cache sau job thế nào?
```

### 23.1. Tránh fallback tenant mặc định không được kiểm soát

Nếu resolver không tìm thấy tenant rồi trả “default” hoặc dùng tenant cuối cùng trong ThreadLocal, job có thể ghi dữ liệu sai tổ chức.

Với job tenant-scoped:

- Truyền tenant ID như một tham số job được xác thực/ủy quyền.
- Mở Session/transaction cho tenant đó.
- Xử lý và đóng trước khi chuyển tenant.
- Ghi metrics/audit gắn tenant.
- Không reuse EntityManager cũ giữa tenants.

Với job cross-tenant do hệ thống quản trị, phải có **privileged execution mode** được thiết kế riêng và kiểm toán, không lách bằng cách tắt filter trong một Session người dùng.

### 23.2. Async propagation

`ThreadLocal` từ web request không tự đi qua mọi `@Async`, executor hoặc reactive context. Tenant ID hoặc principal có thể bị mất, thừa hưởng sai từ thread pooled hoặc còn giá trị cũ.

Một API tốt nhận explicit verified tenant context hoặc dùng propagation được framework hỗ trợ và có cleanup rõ; tuyệt đối không dùng giá trị tenant còn sót từ request trước.

### 23.3. JDBC direct writes

Nếu một job chạy JDBC UPDATE trực tiếp, Hibernate cache/permission cache có thể không nhận được sự kiện thay đổi.

Tùy yêu cầu, hãy:

- Evict cache entries/regions tương ứng.
- Cập nhật authorization version.
- Phát domain/data change events sau commit qua outbox/CDC.
- Hoặc cấm external writers thay đổi dữ liệu mà không đi qua đồng bộ cache được thiết kế.

## 24. Database row-level security như tuyến phòng thủ bổ sung

Một số database (ví dụ PostgreSQL) hỗ trợ **Row-Level Security (RLS)**. Nó cho phép DB áp policy theo identity/tenant context cho queries.

Ví dụ ý tưởng PostgreSQL:

```sql
CREATE POLICY document_tenant_policy
ON documents
USING (
    organization_id = current_setting(
        'app.current_organization',
        true
    )::uuid
);
```

Đây là ví dụ khái niệm; triển khai production cần `ENABLE ROW LEVEL SECURITY`, xác định policy INSERT/UPDATE (WITH CHECK), roles/BYPASSRLS, owner behavior, câu lệnh `SET LOCAL`, connection lifecycle, error nếu context chưa có, và migration/testing thích hợp.

### 24.1. RLS không tự bảo vệ cache nằm trước database

Nếu application cache trả DTO trực tiếp mà không đánh DB, policy RLS không chạy trong request đó.

Vì vậy, **RLS giúp phòng thủ SQL path**, nhưng API/service/cache vẫn phải bảo đảm authorization và cache key phù hợp.

### 24.2. Pooled connections cần reset context

Nếu connection được dùng cho org A rồi trả pool, request org B không được thừa hưởng `app.current_organization=org-a`.

Dùng transaction-local settings (`SET LOCAL`) hoặc một cơ chế đảm bảo reset/restore đúng trên mọi path, kể cả exception, theo hướng dẫn DB/provider. Kiểm thử trên pool thật thay vì chỉ chạy connection đơn lẻ.

## 25. Lựa chọn cache theo mức độ nhạy cảm

Không phải entity nào cũng nên cache theo cùng cách.

| Loại dữ liệu | Chiến lược thường phù hợp |
|---|---|
| Reference data public, immutable | Cache lâu, có namespace/version rõ |
| Product catalog riêng org, ít đổi | Tenant-aware L2 hoặc DTO cache theo org |
| Document nội bộ có ACL | Cache entity content nếu phù hợp; kiểm tra quyền mỗi request |
| Authorized document list theo user | Tránh cache dài hoặc cần permission-version/invalidation |
| User permission decision | Có thể không cache, hoặc TTL rất ngắn + revoke-driven invalidation |
| Financial record nhạy cảm | Ưu tiên correctness/authorization, chỉ cache khi threat model rõ |
| One-time token, secret, credential | Không lưu raw secret trong cache rộng; xác định nguyên tắc bảo mật riêng |
| Audit/event log | Thường cần consistency và kiểm soát access; cân nhắc cache read-only theo scope |

### 25.1. Không phải cứ bật L2 là tăng tốc

L2 hiệu quả khi cùng entity được đọc lặp lại giữa các Sessions và cơ chế invalidation đủ rẻ. Với dữ liệu liên tục thay đổi, L2 có thể tạo overhead và cache churn.

Với tenant data có số lượng rất lớn nhưng mỗi row chỉ đọc một lần, L2 có thể chiếm memory vô ích. Hãy đo hit rate theo tenant và entity region.

### 25.2. Cache budget theo tổ chức

Một tenant lớn có thể chiếm phần lớn cache, đẩy hot data của các tenant nhỏ ra. Đây là vấn đề **fairness và performance isolation**, khác với rò rỉ bảo mật, nhưng cũng quan trọng với SaaS.

Có thể cân nhắc:

- Cache region/namespace theo loại dữ liệu.
- TTL/size/eviction policy.
- Quota/per-tenant budgeting trong custom cache.
- Metrics cache hit/miss/eviction theo tenant (tránh high-cardinality labels quá lớn).
- Giới hạn query cache user-specific có nhiều keys.

## 26. Hibernate CacheMode và query hints

Hibernate có API/configuration liên quan cache usage như `CacheMode`, `@Cache`, `@Cacheable`, query cache hints và RegionFactory.

Ví dụ đánh dấu entity được cache ở L2 theo Hibernate:

```java
import org.hibernate.annotations.Cache;
import org.hibernate.annotations.CacheConcurrencyStrategy;

@Entity
@Cache(
    usage = CacheConcurrencyStrategy.READ_WRITE,
    region = "document-entities"
)
public class Document {
    // ...
}
```

Ví dụ query hint cacheable:

```java
List<Document> docs = em.createQuery("""
    select d from Document d
    where d.organizationId = :orgId
    """, Document.class)
    .setParameter("orgId", authorizedOrgId)
    .setHint("org.hibernate.cacheable", true)
    .getResultList();
```

Các ví dụ đòi Hibernate cache provider/configuration phù hợp; tên hint/property có thể khác theo version.

### 26.1. CacheMode không thay authorization

Việc bật `CacheMode.GET` hoặc tắt query cache không tự bảo vệ resource nếu repository thiếu org predicate và service thiếu policy.

### 26.2. Test cả cache enabled và disabled

Một lỗi bảo mật bị che khi cache disabled nhưng xuất hiện khi cache enabled thường nằm ở caching boundaries hoặc key scoping. Ngược lại, nếu test chỉ chạy cache hit mà không kiểm tra SQL path, có thể bỏ sót query thiếu tenant restriction.

## 27. Thiết kế repository an toàn cho manual org-scoping

Với ứng dụng không dùng Hibernate tenant discriminator tự động, một repository pattern có thể chủ động đưa `organizationId` vào mọi query quan trọng.

Ví dụ:

```java
public interface DocumentReader {
    Optional<Document> findVisibleCandidate(
        UUID organizationId,
        Long documentId
    );
}
```

Implementation:

```java
@Repository
public class JpaDocumentReader implements DocumentReader {

    @PersistenceContext
    private EntityManager em;

    @Override
    public Optional<Document> findVisibleCandidate(
            UUID organizationId,
            Long documentId) {

        List<Document> results = em.createQuery("""
            select d
            from Document d
            where d.id = :documentId
              and d.organizationId = :organizationId
              and d.deletedAt is null
            """, Document.class)
            .setParameter("documentId", documentId)
            .setParameter("organizationId", organizationId)
            .setMaxResults(2)
            .getResultList();

        if (results.size() > 1) {
            throw new IllegalStateException(
                "Document identity is not unique"
            );
        }

        return results.stream().findFirst();
    }
}
```

Ví dụ giả định `Document` có `organizationId` và `deletedAt`. `setMaxResults(2)` hữu ích để phát hiện cardinality nếu schema cho phép nhiều logical IDs; nếu `id` đã là PK toàn cục, có thể đơn giản hơn.

### 27.1. Không để controller gọi EntityManager trực tiếp

Khi mỗi controller tự viết HQL, khả năng quên tenant predicate cao. Đóng gói scoped repository và authorization service giúp giảm bề mặt lỗi.

### 27.2. Một repository scoped không thay resource policy

`findVisibleCandidate` chỉ tìm resource trong organization và không soft-deleted. Nó chưa nhất thiết kiểm tra document-level ACL. Service phải phân biệt “candidate in scope” và “authorized for action”.

### 27.3. Repository phải có mutation methods scoped

Không chỉ SELECT:

```java
int changed = em.createQuery("""
    update Document d
    set d.title = :title
    where d.id = :id
      and d.organizationId = :orgId
    """)
    .setParameter("title", newTitle)
    .setParameter("id", documentId)
    .setParameter("orgId", authorizedOrgId)
    .executeUpdate();
```

Đối với UPDATE/DELETE, còn cần policy action WRITE/DELETE, versioning, callbacks và cache invalidation. Query có org predicate đúng chỉ giải quyết tenant scope, chưa đủ authorization.

## 28. Cache authorization ở đâu trong service?

Một use case update document:

```java
@Transactional
public void renameDocument(
        AuthenticatedPrincipal principal,
        UUID organizationId,
        Long documentId,
        String newTitle) {

    tenantAccess.requireMembership(
        principal,
        organizationId
    );

    Document doc = documentRepository
        .findInOrganization(organizationId, documentId)
        .orElseThrow(DocumentNotFoundException::new);

    documentPolicy.requireCanEdit(
        principal,
        doc
    );

    doc.rename(newTitle);
}
```

Nếu dùng Hibernate dirty checking, update đi qua entity lifecycle và cache synchronization theo mapping. Nếu dùng bulk HQL/Criteria, phải thiết kế thêm optimistic locking, callback/audit và invalidation.

### 28.1. Không kiểm tra quyền sau khi đã sửa object

Nếu service đổi field rồi mới gọi policy, có thể xảy ra trường hợp exception bị bắt không đúng hoặc transaction tiếp tục commit thay đổi trái phép.

Cấu trúc an toàn: xác minh membership và permission trước mutation, transaction rollback đúng nếu có lỗi, và kiểm tra concurrency/row-level invariant phù hợp.

### 28.2. Quyền không được áp bằng cách sửa chính cached entity

Đừng làm:

```java
Document doc = em.find(Document.class, id);

// Sai: dùng field trên entity để ghi quyết định riêng cho user.
doc.setCanEditForCurrentUser(policy.canEdit(user, doc));
```

Nếu `canEditForCurrentUser` là property persistent, thao tác ấy có thể ghi dữ liệu của user hiện tại vào entity dùng chung, dẫn tới sai permission cho user khác.

Permission flags nên nằm trong DTO/view model user-specific, không được lưu như thuộc tính chung của entity trừ khi domain thực sự mô hình hóa nó.

## 29. DTO projection và cache: giới hạn dữ liệu trả về

Một query DTO:

```java
public record DocumentSummary(
    Long id,
    String title,
    String classification
) {}
```

Có thể tạo:

```java
List<DocumentSummary> summaries = em.createQuery("""
    select new com.example.DocumentSummary(
        d.id, d.title, d.classification
    )
    from Document d
    where d.organizationId = :orgId
    """, DocumentSummary.class)
    .setParameter("orgId", authorizedOrgId)
    .getResultList();
```

Nhưng nếu `classification = "CONFIDENTIAL"` yêu cầu ADMIN, DTO projection chưa tự loại row đó. Nếu `title` cũng nhạy cảm, một DTO cache chung tenant có thể lộ thông tin chỉ từ list view.

### 29.1. Hai mẫu thiết kế

**Mẫu A — data-first, authorize-before-return:**

1. Cache entity/DTO chung theo org+ID.
2. Kiểm tra permission ở service.
3. Map/redact fields theo actor.
4. Trả user-specific response; không cache chung response ấy.

**Mẫu B — query policy-aware:**

1. Truy vấn chỉ những document mà actor được phép đọc.
2. Dùng ACL/role predicates và tenant restriction.
3. Nếu cache kết quả, phải có key + invalidation theo actor/policy.
4. Đảm bảo quyền cập nhật ở external IAM cũng được phản ánh.

Mẫu nào phù hợp tùy tần suất ACL thay đổi, độ nhạy, số lượng document và query performance.

### 29.2. Không serialize JPA entity trực tiếp

Trả entity nguyên vẹn qua REST JSON có thể:

- Tải lazy associations ngoài ý định.
- Gặp `LazyInitializationException`.
- Rò field nội bộ mà DTO không định xuất.
- Serialize user/tenant associations.
- Truy vấn N+1 không kiểm soát.

DTO theo API contract và chính sách field-level authorization là lựa chọn dễ bảo vệ hơn.

## 30. HTTP response cache và CDN

Các tầng cache bên ngoài JVM không hiểu Hibernate tenant key.

Ví dụ API:

```http
GET /api/documents/101
Authorization: Bearer ...
```

Nếu CDN/cache proxy lưu response dưới URL duy nhất `/api/documents/101` rồi trả cho user khác, dữ liệu có thể bị lộ dù Hibernate L2 tenant-safe.

### 30.1. Đối với phản hồi riêng tư

Thường cân nhắc:

```http
Cache-Control: private, no-store
```

Đây là lựa chọn bảo thủ cho thông tin nhạy cảm; kiểm tra semantics caching HTTP và policy ứng dụng. Nếu có nhu cầu cache client-side, có thể dùng `private` với quy định freshness phù hợp thay vì `no-store`, nhưng phải hiểu dữ liệu người dùng trên shared devices.

### 30.2. Không dựa vào Vary: Authorization một cách mù quáng

CDN/reverse proxy có behavior cache keys và header handling khác nhau. Một số cache không lưu authenticated responses mặc định, một số có thể được cấu hình override. Cần kiểm tra cấu hình thực tế, không suy luận toàn bộ authorization header luôn là một phần key.

### 30.3. Browser/client cache sau logout

Nếu dữ liệu nhạy cảm được cache phía client, logout hoặc chuyển org cần chính sách xóa state local, query caches của frontend và pagination results. Một backend tenant-safe vẫn có thể hiển thị dữ liệu org cũ trong UI nếu client state không được reset.

## 31. Chuyển organization trong cùng tài khoản

Một user có thể là thành viên nhiều org và có UI chọn “Current organization”.

Khi chuyển từ org A sang org B:

1. Server xác minh membership của org B.
2. Tạo context/transaction mới gắn tenant B.
3. Không tái sử dụng `EntityManager` chứa entities của A.
4. Xóa hoặc phân namespace application/frontend caches theo org.
5. Làm mới dữ liệu trang/list và permission state.
6. Bảo đảm background requests đang chạy từ org A không ghi đè response của org B.

### 31.1. Race condition ở frontend

Ví dụ:

```text
T0: UI ở org A, gọi fetch /documents
T1: user chuyển sang org B
T2: UI gọi fetch /documents cho B
T3: response A đến sau B
T4: UI ghi response A vào danh sách hiện tại
```

Đây không phải lỗi Hibernate, nhưng kết quả vẫn là **data isolation bị phá ở tầng hiển thị**.

Client cần key theo org/actor và bỏ qua stale responses khi active org thay đổi, ví dụ hủy request hoặc so sánh request scope trước khi render.

### 31.2. Server không dùng mutable global currentOrg

Một biến static hoặc singleton giữ current org cuối cùng sẽ gây race giữa requests/threads. Tenant context cần được scope theo request/transaction/async execution và validate chặt.

## 32. Permission revocation qua message/event

Khi admin thu hồi quyền, nhiều hệ thống phát event:

```text
PermissionRevoked {
    organizationId,
    principalId,
    resourceId,
    action,
    version
}
```

Các service/cache subscribers có thể:

- Xóa permission decisions liên quan.
- Tăng security epoch để bỏ cache keys cũ.
- Purge user-specific document lists/DTOs.
- Cập nhật local caches.
- Giới hạn sử dụng old session/token theo policy.

### 32.1. Pub/sub không tự bảo đảm delivery

Nếu message mất hoặc consumer down, cache có thể stale. Với yêu cầu revoke nghiêm ngặt, cần thiết kế:

- Durable outbox/stream.
- Retry và idempotency.
- Version-based checks với source of truth.
- TTL như cơ chế dự phòng, không phải bảo đảm duy nhất.
- Fail-closed behavior khi không thể xác minh quyền cho thao tác nhạy cảm.

### 32.2. Invalidation phải xảy ra đúng lúc

Nếu cập nhật ACL trong transaction DB nhưng phát event **trước commit**, subscriber có thể invalidate cache rồi sau đó request khác lại cache quyền cũ trước khi commit.

Nếu transaction rollback, invalidation không gây leak trực tiếp nhưng có thể tạo hiệu ứng không cần thiết. Một thiết kế vững là ghi event/outbox trong transaction và phát sau commit khi dữ liệu đã bền vững.

## 33. Threat model: những đường rò dữ liệu thường gặp

| Rủi ro | Nguyên nhân | Biện pháp chính |
|---|---|---|
| Cross-tenant cache hit | App cache key chỉ dùng entity ID | Key theo tenant đã xác minh |
| Cross-tenant Session reuse | Session được dùng lại khi đổi org | Session/transaction riêng cho từng tenant |
| Incorrect tenant resolver | Tin header chưa được xác thực | Resolve từ authenticated + authorized context |
| Unauthorized same-tenant read | L2 hit rồi bỏ qua ACL | Check authorization mỗi request |
| Stale allow after revoke | Permission cache TTL quá dài | Invalidate/version hoặc không cache allow |
| Cached admin DTO cho viewer | DTO user-specific cache theo org | Tách cache data khỏi authorized view |
| Unscoped find(id) | Manual tenant model không áp WHERE | Scoped repository/tenant-aware mapping |
| Native SQL bypass | Thiếu org predicate/filter/RLS | Scope native queries + DB policy |
| User-specific query cache stale | ACL thay đổi ngoài Hibernate | Invalidate, policy-version, cache strategy |
| Soft-deleted row vẫn hiện | Cached list/lookup cũ | Visibility checks và invalidation |
| Wrong org in async job | Tenant context không propagate/cleanup | Explicit verified tenant context |
| Connection schema leak | Pool reuse connection chưa reset | Correct tenant connection provider/cleanup |
| Foreign-key cross-tenant link | FK không gắn tenant | Composite tenant-aware FK |
| Frontend shows previous org data | Client cache key/state không reset | Namespace theo org và chặn stale response |
| CDN caches private response | Response cache key không phân principal | Private/no-store, CDN policy |
| Cache keys reveal secrets | Raw token/PII trong key/log | Internal identifiers, masking, limited access |

Security incident có thể đến từ **một trong nhiều tầng**, không chỉ “Hibernate cache”.

## 34. Kiểm thử cross-tenant với trùng identifier

Một test quan trọng cho multi-tenancy database/schema-per-tenant là cho hai tenant có **cùng ID** nhưng dữ liệu khác:

```text
Tenant org-a: Document#42 -> "Alpha"
Tenant org-b: Document#42 -> "Beta"
```

Test:

1. Mở Session tenant A.
2. Load Document#42 để làm nóng L2 cache.
3. Đóng Session A.
4. Mở Session tenant B.
5. Load Document#42.
6. Xác nhận tên `Beta`, không phải `Alpha`.
7. Đảo thứ tự (B trước A) và kiểm tra.
8. Lặp lại khi cache enabled/disabled.

Với shared table ID là global PK, không thể có hai rows trùng ID trong cùng bảng. Trong trường hợp đó, test nên dùng hai IDs và xác nhận lookup trái tenant bị từ chối, kể cả khi L2 đã warm.

### 34.1. Dùng EntityManager/Session mới thật sự

Nếu test chỉ đổi biến tenant rồi dùng lại một EntityManager, nó đang kiểm thử một pattern sử dụng sai. Để kiểm tra tenant cache isolation, cần mỗi lần mở đúng Session/tenant context tương ứng.

### 34.2. Warm cả query cache

Chạy query cacheable ở org A rồi query tương tự ở org B, xác nhận B không nhận list IDs/DTOs của A. Test cả filter parameters, pagination, sort và cache invalidation khi data được cập nhật.

### 34.3. Dùng database production-like

Với schema switching, RLS, SQL dialect hoặc transaction isolation, H2/in-memory DB có thể không tái hiện được behavior production. Test quan trọng nên chạy trên DB engine/version gần thực tế, cùng cache provider/cấu hình nếu có thể.

## 35. Kiểm thử quyền khi cache đã nóng

Giả sử:

- Alice là ADMIN, Bob là VIEWER.
- Document A-101 chỉ ADMIN được xem.

Test:

1. Alice truy cập A-101 và làm nóng L2/cache DTO.
2. Bob truy cập A-101.
3. Kỳ vọng Bob bị từ chối, không nhận DTO.
4. Alice truy cập lại, kết quả vẫn hợp lệ.
5. Đổi Bob thành ADMIN, kiểm tra grant có hiệu lực.
6. Thu hồi ADMIN của Bob, kiểm tra revoke có hiệu lực theo SLA.
7. Test khi DB/cache hit/miss và event invalidation bị delay.

**Đừng chỉ test Bob lúc cache lạnh.** Nhiều lỗi xuất hiện khi cache hit bỏ qua permission check trong method body.

### 35.1. Test ACL trên cùng org

Tenant isolation không đủ. Tạo hai users cùng org với quyền khác nhau trên một resource, vì đây là trường hợp Hibernate tenant cache key giống nhau nhưng authorization decision khác nhau.

### 35.2. Test nhiều org memberships

User thuộc cả org A và B, role ở mỗi org khác nhau. Xác nhận:

- Role của A không được dùng cho B.
- Cache quyền phải chứa org scope.
- Chuyển org tạo đúng query context.
- Session A không được dùng để đọc B.
- Client cache không render stale list của A sau chuyển B.

### 35.3. Test concurrent access

Hai requests song song với tenant A và B có thể phát hiện lỗi global variable/ThreadLocal cleanup mà test tuần tự không tìm ra.

Thử cả async jobs và thread pool reuse, nhất là khi tenant resolver phụ thuộc request context.

## 36. Kiểm thử mutation và permission cache invalidation

Một test workflow:

```text
1. User Bob có quyền READ Doc#42.
2. Gọi API -> cache allowed result.
3. Admin revoke READ trong transaction.
4. Commit.
5. Đợi/chạy cơ chế invalidation đúng contract.
6. Bob gọi API lần nữa.
7. Phải DENY trong giới hạn thời gian bảo đảm.
```

Nếu business yêu cầu revoke ngay, test không được chấp nhận một khoảng cache stale không có SLA rõ.

Tương tự cho:

- Grant quyền.
- Disable user.
- Xóa org membership.
- Thay role.
- Đổi classification của document.
- Soft delete document.
- Đổi owner của resource.
- Update tenant mapping.
- Bulk DML hoặc external IAM sync.

### 36.1. Test cache provider thực tế

Mocks thường không tái hiện:

- Distributed cache TTL/eviction.
- Race khi invalidation và read đồng thời.
- Partition/network failure.
- Cache key serialization.
- Multiple instances cùng truy cập.
- Query-cache timestamps.

Security-critical paths nên có một số integration tests chạy với cache provider/version thực tế.

## 37. Monitoring, logging và audit

Một hệ thống multi-tenant có cache cần quan sát các yếu tố:

- L2 cache hit/miss/evictions theo region.
- Query cache hit/miss và invalidations.
- Redis/Caffeine hit rate và memory.
- Cache key cardinality.
- Authorization allow/deny metrics.
- Tenant resolver failures.
- Suspicious cross-tenant access attempts.
- Permission revocation propagation lag.
- Stale permission cache incidents.
- Data exposure alerts và audit trails.

### 37.1. Không đưa dữ liệu bí mật vào metrics labels

Tenant ID có thể có hàng triệu giá trị. Gắn tất cả tenant IDs vào Prometheus labels có thể gây high-cardinality metrics quá lớn và tiết lộ identifiers.

Thường nên đo tổng theo cache region, tier, class of tenant hoặc sampling có kiểm soát. Audit events có thể giữ tenant/resource IDs nhưng phải có access controls.

### 37.2. Log authorization denial có kiểm soát

Để điều tra IDOR/cross-tenant access, có thể log correlation ID, actor ID, effective org ID, resource ID và action theo chính sách privacy, không in document content hoặc raw access token.

### 37.3. Trace cache hit không được coi là quyền

Log `CACHE_HIT document:42` có thể phục vụ performance debugging nhưng không chứng minh `AUTHZ_ALLOW`. Hai sự kiện cần được phân biệt trong observability.

## 38. Quy trình thiết kế cache an toàn cho dữ liệu tổ chức

Trước khi bật hoặc mở rộng cache, hãy trả lời:

1. Dữ liệu này là public, tenant-private hay user-private?
2. Tenant identifier được xác minh từ nguồn nào?
3. Organization membership được kiểm tra ở đâu?
4. Session/EntityManager được tạo và kết thúc theo tenant nào?
5. Có khả năng dùng lại Session qua nhiều tenants hoặc threads không?
6. Đang dùng `@TenantId`/multi-tenancy thật hay chỉ field `organizationId` thủ công?
7. L2 entity cache key có gắn tenant theo config hiện tại không?
8. Có custom Redis/Spring Cache key thiếu org/user/query parameters không?
9. Có một cache hit nào bỏ qua policy check trong method body không?
10. Resource authorization là RBAC, ACL hay ABAC?
11. Authorized DTO có bị cache như dữ liệu dùng chung không?
12. Role/membership/ACL đổi thì cache nào cần invalidate?
13. Revoke permission phải có hiệu lực trong bao lâu?
14. Có fallback khi invalidation event mất không?
15. Query cache có chứa user-dependent predicate và invalidation đúng không?
16. Direct `find`/association/native SQL/bulk DML có đi qua tenant restrictions không?
17. Có soft delete hoặc data classification ảnh hưởng visibility không?
18. Có DB-level FK tenant-aware hoặc RLS làm defense-in-depth không?
19. Background job và async tasks xác định tenant bằng cách nào?
20. HTTP/CDN/frontend caches có thể phục vụ dữ liệu của org trước không?
21. Test đã thử tenant A/B với same-ID, cache nóng, role revoke và concurrent requests chưa?
22. Có monitoring/audit phát hiện violations và đo propagation lag không?

Nếu bất kỳ câu nào chưa được xác định, việc bật cache mới cho dữ liệu nhạy cảm có thể làm tăng bề mặt lỗi bảo mật.

## 39. Bài tập thực hành

### Bài 1: Cache key theo ID

```java
@Cacheable(cacheNames = "doc", key = "#id")
DocumentDto get(Long id);
```

**Câu hỏi:** Tại sao key này có thể sai trong ứng dụng multi-tenant?

**Giải thích:** Nếu ID chỉ unique trong từng tenant, key trùng sẽ trả dữ liệu tenant khác. Ngay cả khi ID global unique, nếu DTO phụ thuộc permissions/user, key vẫn thiếu scope quyền. Dùng key từ effective authorized tenant và những dependency cần thiết, hoặc không cache authorized view.

### Bài 2: Second-level cache có tenant ID

Tenant A và B cùng có Document#42 trong database riêng. Hibernate multi-tenancy được cấu hình đúng, mỗi request dùng Session tenant tương ứng.

**Câu hỏi:** Có nên mặc định L2 entry của A ghi đè entry B?

**Giải thích:** Không. Hibernate multi-tenancy chuẩn có cơ chế tenant-aware cache identity. Tuy nhiên, cần integration test đúng version/cache provider và bảo đảm resolver luôn đưa đúng tenant. App-level caches không tự có bảo vệ này.

### Bài 3: Bob bị revoke

Alice đọc Document rồi cache entity L2. Bob từng có READ nhưng vừa bị thu hồi.

**Câu hỏi:** Xóa L2 Document cache có phải giải pháp đầy đủ?

**Giải thích:** Không. Lỗi chính là decision cache hoặc authorization flow stale/bỏ qua check. Phải đánh giá lại quyền hoặc invalidate decision/authorized views đúng scope. Có thể không cần xóa entity state L2 nếu nội dung không đổi.

### Bài 4: Tenant header

Client gửi `X-Tenant-Id: org-admin`. Backend gắn thẳng header này vào Hibernate Session.

**Câu hỏi:** Điều gì sai?

**Giải thích:** Header chưa được xác minh. User có thể chọn org khác. Server phải xác thực identity và kiểm tra membership/quyền chọn tenant trước khi tạo Session.

### Bài 5: @Cacheable authorization inside

Một method `@Cacheable` kiểm tra ACL bên trong body rồi trả DTO.

**Câu hỏi:** Cache hit có chạy lại ACL check không?

**Giải thích:** Thông thường không nếu cache proxy trả cached result mà bỏ qua body. Đặt authorization ở boundary luôn được thực thi trước cache lookup, hoặc thiết kế user-scoped cache/permission invalidation với policy rõ.

### Bài 6: Query cache list theo quyền

Một query Hibernate cacheable trả danh sách tài liệu được phép xem theo ACL trong DB. Sau đó ACL bị sửa qua JDBC tool ngoài Hibernate.

**Câu hỏi:** Có chắc query cache được invalidate?

**Giải thích:** Không. External writer có thể không được Hibernate theo dõi. Cần cơ chế invalidation/event hoặc tránh cache kết quả permission-sensitive.

### Bài 7: Background job

Job import chạy `@Async`, tenant được lưu trong ThreadLocal của HTTP request.

**Câu hỏi:** Có chắc async worker nhận đúng tenant?

**Giải thích:** Không. Thread context có thể không được propagate, hoặc thread pooled còn giá trị cũ nếu cleanup sai. Truyền verified tenant context tường minh và đảm bảo lifecycle/cleanup.

### Bài 8: RLS và Redis

Database đã bật PostgreSQL RLS. API trả Document DTO trực tiếp từ Redis trước khi query database.

**Câu hỏi:** RLS có chạy và bảo vệ lần trả cached DTO này không?

**Giải thích:** Không. Cache hit có thể bỏ qua database. API phải kiểm tra authorization và key scoping độc lập.

## 40. Ghi nhớ

- **Tenant isolation và authorization là hai bài toán khác nhau.** Cách ly tổ chức đúng chưa đảm bảo từng user trong cùng tổ chức được xem đúng dữ liệu.
- **Hibernate L1 cache** gắn với Session/EntityManager; không tái sử dụng Session giữa user/tenant hoặc threads, không đổi tenant giữa vòng đời Session.
- **Hibernate L2 cache** có tenant-aware cache identity trong cấu hình multi-tenancy phù hợp; không nhầm với custom cache chỉ keyed bằng ID.
- **Tenant resolver phải lấy tenant từ authenticated/authorized context**, không tin raw HTTP header hoặc global mutable variable.
- **`@TenantId`** là tính năng Hibernate theo version; nếu chỉ có field `organizationId` thường, phải bảo đảm scoped queries/authorization thủ công hoặc cơ chế được kiểm chứng.
- **Entity cache hit không có nghĩa actor được phép xem.** Always enforce resource/action policy at service boundary.
- **App cache keys** phải thể hiện effective tenant và mọi dependency làm thay đổi result, bao gồm filter/sort/page và user/permission state nếu caching authorized views.
- **`@Cacheable` có thể bỏ qua method body khi cache hit**, nên đừng đặt kiểm tra authorization duy nhất bên trong body được cache.
- **Query cache** không tự biết IAM policies, external ACL changes hoặc application-level permission; caching ACL-dependent query đòi invalidation và versioning rõ.
- **Cơ chế revoke** phải có SLA: TTL dài không phù hợp nếu quyền cần bị thu hồi tức thì. Dùng event/version/short TTL hoặc recheck source of truth theo threat model.
- **L2/cache coherence và quyền truy cập là những lớp khác nhau.** Evict entity không tự làm permission decision đúng.
- **Native SQL, bulk DML, filters, soft delete và background jobs** đều cần kiểm tra tenant scoping trên đúng execution path.
- **FK kết hợp tenant và database RLS** có thể tăng defense-in-depth, nhưng RLS không bảo vệ cache ở tầng trên.
- **HTTP/CDN/frontend caches** cũng phải theo org/user scope hoặc không cache private responses.
- **Test cache nóng, same-ID cross-tenant, cùng org khác role, permission revoke, concurrent requests và async context** để phát hiện lỗi chỉ xuất hiện khi dùng cache.
- **Monitoring** cần phân biệt cache hit/miss với authorization allow/deny, tránh ghi sensitive content vào logs/metrics.

**Kết luận:** Bộ nhớ đệm có thể giúp Hibernate giảm SQL và tăng tốc ứng dụng multi-tenant, nhưng cũng mở thêm những đường trả dữ liệu không đi qua truy vấn SQL vốn đang thực thi phạm vi tenant/ACL. Thiết kế đúng cần bảo đảm **tenant context cố định, Hibernate cache identity phù hợp, custom cache keys được phân namespace, authorization được đánh giá độc lập với cache hit và các thay đổi quyền có chính sách invalidation rõ**. Khi mỗi tầng đều giữ đúng ranh giới trách nhiệm của nó, ứng dụng có thể tận dụng cache mà vẫn bảo vệ dữ liệu của từng tổ chức và người dùng.
