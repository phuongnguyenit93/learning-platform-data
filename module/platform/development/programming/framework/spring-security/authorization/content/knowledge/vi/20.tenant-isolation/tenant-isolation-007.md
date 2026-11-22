# Áp dụng điều kiện tenant tại repository và truy vấn dữ liệu

## 1. Vấn đề: xác thực đúng người nhưng trả dữ liệu sai tenant

Một hệ thống SaaS phục vụ nhiều tổ chức dùng chung database. Mỗi tài liệu có `tenant_id`; một người được phép đọc tài liệu thuộc tenant mà mình là thành viên. Ví dụ:

| ID tài liệu | Tenant | Owner | Tiêu đề |
| ---: | --- | --- | --- |
| 11 | `T1` | `u-alice` | Alpha |
| 12 | `T1` | `u-bob` | Beta |
| 13 | `T2` | `u-carol` | Gamma |
| 14 | `T1` | `u-alice` | Locked |

Alice thuộc `T1`, Carol thuộc `T2`. Nếu repository dùng:

```java
documentRepository.findById(13L);
```

mà service không có bảo vệ khác, Alice có thể đọc tài liệu của Carol chỉ bằng cách đoán ID `13`. `@PreAuthorize("hasAuthority('document:read')")` **không sửa được lỗi đó**, vì nó kiểm tra quyền chức năng chứ không tự thêm `tenant_id = 'T1'` vào SQL.

Lỗi này là một dạng **Broken Object Level Authorization (BOLA/IDOR)** và **cross-tenant data leakage**. Nó không chỉ ảnh hưởng phương thức xem một tài liệu: `findAll`, tìm kiếm, pagination, `COUNT`, `EXISTS`, JOIN, aggregation, export, update và delete đều có thể tạo đường truy cập hoặc thay đổi dữ liệu ngoài tenant.

Bài Knowledge này thuộc **Spring Security – authorization**, nhóm **Cách ly tenant**. Trọng tâm: **áp dụng điều kiện tenant ngay tại repository và truy vấn dữ liệu**, thay vì lấy quá nhiều hàng rồi lọc trong Java hoặc tin `tenantId` từ request.

Sau bài học, bạn sẽ:

1. Phân biệt authentication, functional authorization, **tenant membership** và object-level authorization.
2. Xác định **trusted tenant scope** từ identity đã được xác minh.
3. Viết SQL/JPQL luôn chứa tenant predicate cho **một đối tượng, danh sách, tìm kiếm, COUNT, EXISTS, UPDATE, DELETE**.
4. Dùng Spring Data JPA derived queries, `@Query`, `@Modifying`, paging và version check đúng cách.
5. Viết ví dụ **Java 17 + Spring Boot 3.5.8 + Spring Security + Spring Data JPA + H2** có thể chạy độc lập.
6. Kiểm thử rằng Alice không nhìn thấy tài liệu tenant T2, Carol không nhìn thấy tenant T1; cùng tenant vẫn cần owner/permission cho thao tác ghi.
7. Phòng lỗi thường gặp khi JOIN, `OR`, native SQL, cache, async, tenant-local ID và lazy loading.
8. Hiểu vai trò **Row-Level Security (RLS)** của PostgreSQL như defense-in-depth, cùng giới hạn của nó.
9. Thiết kế fail closed, an toàn với transaction, locking, data migration và quyền được thu hồi.

**Định đề cần giữ:** mọi dữ liệu đưa đến caller hoặc thay đổi bởi caller phải thuộc **phạm vi tenant được server xác minh** và thỏa quyền nghiệp vụ bổ sung. Điều kiện tenant là một ranh giới bảo mật bắt buộc, không phải chỉ là bộ lọc giao diện.

## 2. Ba lớp quyền độc lập

Một câu trả lời `canRead(document)` thường là phép AND:

```text
canRead(actor, doc) =
    authenticated(actor)
    AND hasAuthority(actor, "document:read")
    AND isActiveMember(actor, doc.tenantId)
    AND objectPolicyAllows(actor, doc)
```

Trong demo, để làm rõ tenant filtering, quy tắc `READ` là mọi thành viên đã được xác minh thuộc tenant tương ứng và có authority `document:read` đều có thể xem tài liệu trong tenant. Quy tắc `WRITE` nghiêm hơn: ngoài đúng tenant, caller phải là `ownerId` và tài liệu còn `DRAFT`.

Một tổ chức thực tế có thể cần thêm ACL, vai trò theo project, cấp độ bảo mật, status hoặc share permissions. **Tenant predicate là điều kiện cần, không phải điều kiện đủ cho mọi dữ liệu.**

| Lớp | Câu hỏi | Cơ chế ví dụ |
| --- | --- | --- |
| Xác thực | Caller thực sự là ai? | JWT/OIDC/session được kiểm chứng |
| Quyền chức năng | Caller được dùng API đọc/sửa không? | `@PreAuthorize("hasAuthority(...)")` |
| Tenant scope | Caller đang ở tenant nào, có membership không? | Server directory hoặc verified tenant claim |
| Quyền trên object | Được đọc/ghi bản ghi cụ thể không? | `tenant_id` + owner/ACL/state |
| Quyền trên field | Có được sửa `ownerId`, `tenantId`, `state` không? | DTO allowlist và domain service |
| Bảo vệ tầng DB | Query lỡ thiếu tenant thì sao? | Repository contract, test, có thể PostgreSQL RLS |

**Không dùng quyền chức năng thay tenant scope.** `ROLE_EDITOR` hoặc `document:read` không tự nói người ấy thuộc mọi tổ chức.

## 3. Tenant ID phải đến từ nguồn đáng tin

Một endpoint có thể nhận:

```http
GET /api/documents/13?tenantId=T2
Authorization: Bearer <token-cua-alice>
```

Nếu backend dùng trực tiếp query parameter:

```java
repository.findByIdAndTenantId(id, requestedTenantId);
```

thì điều kiện `tenant_id` **có mặt về mặt cú pháp** nhưng vẫn sai về bảo mật: Alice có thể yêu cầu `T2`. Tenant predicate chỉ có giá trị khi **giá trị tenant được xác minh**.

### 3.1. Mô hình một tenant đang hoạt động

Ứng dụng có thể lấy tenant từ:

- `Authentication` đã được xác minh, nếu token có claim tenant đáng tin và policy cho phép.
- Server-side membership directory: từ `subject` của token map tới các tenant được phép.
- Tenant được chọn qua URL/header, **sau khi** kiểm tra membership và trạng thái active trong database/server.
- Session server-side có active tenant đã được xác thực.

Một mô hình đơn giản cho bài học:

```text
Authentication.getName() -> UserDirectory (server)
  alice -> userId=u-alice, tenantId=T1
  bob   -> userId=u-bob,   tenantId=T1
  carol -> userId=u-carol, tenantId=T2
```

`tenantId` trong request body, query, cookie hoặc custom header **không tự đáng tin**. Nếu user thuộc nhiều tenant, cần verify quyền chuyển active tenant; chỉ sau đó truyền trusted tenant vào truy vấn.

### 3.2. Không lẫn identity của user và tenant

`ownerId` xác định chủ bản ghi. `tenantId` xác định phạm vi tổ chức. Một owner có thể được chuyển sang user khác cùng tenant mà không cần chuyển tenant; ngược lại, một migration tenant có thể ảnh hưởng file storage, khóa mã hóa, index, ACL và tài nguyên liên quan.

Đừng đổi `tenant_id` thông qua API cập nhật chung; dùng workflow chuyển tenant riêng có kiểm tra và audit. Repository update dành cho sửa tiêu đề không được tự set tenant từ client.

### 3.3. Fail closed khi không có tenant đáng tin

Nếu không có `Authentication`, token anonymous, user bị khóa hoặc không có tenant hợp lệ, **từ chối**, không dùng tenant mặc định.

```java
// MẢNH CODE minh họa cách KHÔNG làm:
String tenant = currentTenantOrNull();
return tenant == null
    ? repository.findAll()             // nguy hiểm: bỏ tenant filter
    : repository.findByTenantId(tenant);
```

Chính sách an toàn là từ chối hoặc trả tập rỗng theo contract khi không có tenant, chứ không tự mở ra toàn bộ bảng.

## 4. Đặt điều kiện tenant ở **SQL trước khi trả dữ liệu**

### 4.1. Đọc một bản ghi

Không an toàn:

```sql
SELECT id, tenant_id, owner_id, title
FROM documents
WHERE id = :id;
```

Cách nên dùng:

```sql
SELECT id, tenant_id, owner_id, title
FROM documents
WHERE id = :id
  AND tenant_id = :trustedTenant;
```

Ở đây `:id` và `:trustedTenant` là named parameters, được bind qua thư viện truy vấn, không nối string. Nếu không có hàng, API có thể trả `404` để không tiết lộ tài liệu khác tenant có tồn tại.

### 4.2. Danh sách và tìm kiếm

```sql
SELECT id, tenant_id, owner_id, title
FROM documents
WHERE tenant_id = :trustedTenant
  AND state = 'DRAFT'
  AND LOWER(title) LIKE :normalizedSearchPattern
ORDER BY id
LIMIT :pageSize OFFSET :offset;
```

Bảng `documents` phải có `tenant_id` trong predicate trước khi database phân trang. Search pattern phải được tạo có escaping theo DB nếu cần tìm ký tự `%` hoặc `_` như dữ liệu thuần; bind parameters bảo vệ SQL injection nhưng không tự bảo đảm semantics của wildcard.

### 4.3. COUNT, EXISTS và aggregation cũng phải lọc tenant

```sql
SELECT COUNT(*)
FROM documents
WHERE tenant_id = :trustedTenant
  AND state = 'DRAFT';
```

```sql
SELECT CASE WHEN COUNT(*) > 0 THEN TRUE ELSE FALSE END
FROM documents
WHERE id = :id
  AND tenant_id = :trustedTenant;
```

```sql
SELECT state, COUNT(*) AS total
FROM documents
WHERE tenant_id = :trustedTenant
GROUP BY state;
```

Nếu API trả đúng các hàng của T1 nhưng `totalElements` hoặc dashboard lại đếm toàn hệ thống, nó vẫn có thể làm lộ metadata và gây sai pagination. **Tất cả query liên quan cùng chức năng phải dùng cùng tenant policy.**

### 4.4. Ghi và xóa cũng cần tenant guard

```sql
UPDATE documents
SET title = :newTitle
WHERE id = :id
  AND tenant_id = :trustedTenant
  AND owner_id = :trustedActor
  AND state = 'DRAFT';
```

```sql
DELETE FROM documents
WHERE id = :id
  AND tenant_id = :trustedTenant
  AND owner_id = :trustedActor;
```

Sau `UPDATE` hoặc `DELETE`, kiểm tra số hàng ảnh hưởng. **0 hàng** có thể nghĩa là không tồn tại, sai tenant, không phải owner, sai trạng thái hoặc thay đổi đồng thời; tránh tiết lộ chi tiết cho caller chưa có quyền. Với thao tác quan trọng còn cần transaction, version/lock và policy field-level.

## 5. Spring Data JPA: các mẫu repository cơ bản

Một Spring Data repository có thể tạo query tự động bằng tên method:

```java
// MẢNH CODE minh họa trong một JpaRepository.
Optional<DocumentEntity> findByIdAndTenantId(
    Long id, String tenantId);

Page<DocumentEntity> findByTenantIdAndState(
    String tenantId, DocumentState state, Pageable pageable);

long countByTenantIdAndState(
    String tenantId, DocumentState state);
```

Tên `findByIdAndTenantId` giúp ràng buộc cả ID và tenant. Tương tự, `Page` chứa tenant predicate ngay trong query lấy rows và query count được suy ra; phải kiểm tra điều kiện thực tế với custom `@Query`/joins khi phức tạp.

**Nhưng repository không tự bảo vệ giá trị `tenantId`.** Mọi method phải nhận trusted tenant từ service/directory, không từ client chưa kiểm chứng.

### 5.1. Tránh `findById`/`findAll` được thừa kế nhưng không có scope

`JpaRepository<T, ID>` có những method tiện lợi như `findById`, `findAll`, `findAllById`, `deleteById`, `findAll(Pageable)` và `count()`. Chúng **không tự thêm tenant predicate**.

Nếu để controller/service gọi tùy ý các method đó, một lập trình viên có thể vô tình bỏ qua policy. Với codebase lớn, cân nhắc:

- Chỉ expose các method tenant-scoped qua **application data-access service**.
- Dùng interface `Repository<T, ID>` tùy chỉnh chỉ khai báo những truy vấn được phép dùng.
- Tách internal admin repository khỏi repository cho request thông thường, và chặn quyền admin thật sự.
- Kiểm thử kiến trúc hoặc static analysis để phát hiện service nhạy cảm gọi unscoped repository methods.
- Dùng PostgreSQL RLS hoặc một DB isolation control khác làm defense-in-depth.

Trong demo bên dưới dùng `JpaRepository` cho đơn giản, **nhưng application service chỉ gọi những method có tenant predicate**. Tests được phép inspect unscoped data bằng repository vì chúng chạy ở ngữ cảnh kiểm chứng nội bộ; đó không phải API cần cho caller.

### 5.2. JPQL với `@Query`

Khi derived method dài hoặc có ACL/share, có thể khai báo:

```java
@Query("""
    select d from DocumentEntity d
    where d.tenantId = :tenantId
      and d.state = :state
      and (d.ownerId = :userId or d.isPublicWithinTenant = true)
    order by d.id
    """)
List<DocumentEntity> findVisible(
    @Param("tenantId") String tenantId,
    @Param("state") DocumentState state,
    @Param("userId") String userId);
```

**Mảnh code minh họa:** field `isPublicWithinTenant` không tồn tại trong entity demo, chỉ để diễn giải một policy mở rộng. Predicate tenant nằm **ngoài và bao phủ toàn bộ điều kiện OR**.

Câu lệnh nguy hiểm:

```sql
WHERE d.tenant_id = :tenant
  AND d.owner_id = :actor
   OR d.public = TRUE
```

Do ưu tiên `AND` trước `OR`, nhánh `d.public = TRUE` có thể trả tài liệu của **tenant khác**. Đúng hơn:

```sql
WHERE d.tenant_id = :tenant
  AND (d.owner_id = :actor OR d.public = TRUE)
```

Khi review repository, đặc biệt kiểm tra **mọi nhánh OR phải vẫn nằm dưới tenant predicate**.

### 5.3. Specifications và Criteria API

Nếu truy vấn có nhiều filter động, một specification tenant-scoped:

```java
// MẢNH CODE khi DocumentRepository implements JpaSpecificationExecutor.
static Specification<DocumentEntity> inTenant(String tenantId) {
    return (root, query, cb) ->
        cb.equal(root.get("tenantId"), tenantId);
}
```

Kết hợp điều kiện:

```java
Specification<DocumentEntity> spec =
    inTenant(trustedTenant)
    .and((root, query, cb) ->
        cb.equal(root.get("state"), DocumentState.DRAFT));

Page<DocumentEntity> page = repository.findAll(spec, pageable);
```

Chú ý: `Specification` chỉ bảo vệ khi caller **luôn** kết hợp tenant spec. Tránh expose một phương thức `findAll(specFromClient)` nếu spec do client điều khiển có thể bỏ tenant. Nên áp tenant constraint ở lớp truy vấn nội bộ cố định rồi mới kết hợp những filter tùy chọn.

### 5.4. Native SQL và JDBC

Với `@Query(nativeQuery=true)` hoặc `JdbcTemplate`, ORM không tự thêm tenant predicate. Viết tenant condition trực tiếp, bind tham số an toàn và kiểm thử cả truy vấn count riêng.

```java
// MẢNH CODE với NamedParameterJdbcTemplate:
var sql = """
    select id, tenant_id, title
    from documents
    where tenant_id = :tenant
      and id = :id
    """;

var params = Map.of(
    "tenant", trustedTenant,
    "id", requestedId
);

List<DocumentView> rows = namedJdbc.query(sql, params, rowMapper);
```

Không xây SQL bằng `"where tenant_id='" + clientTenant + "'"` vì vừa thiếu kiểm chứng tenant vừa dễ phát sinh SQL injection.

## 6. Ví dụ có thể chạy: Spring Boot 3.5.8 + Java 17 + JPA + H2

Demo minh họa tenant guard **ngay trong Spring Data repository** và Method Security ở service.

**Chính sách demo:**

- Tài khoản được xác thực và có `document:read` được xem các tài liệu trong tenant do server xác định.
- `alice`/`bob` ở T1, `carol` ở T2.
- Chỉ owner với `document:write` trong đúng tenant mới được đổi tiêu đề một tài liệu `DRAFT`.
- `UPDATE` kiểm tra `id`, `tenantId`, `ownerId`, `state` và `version` trong **cùng một JPQL DML statement**.
- Request không được tự chọn `tenantId`/`ownerId` để bypass policy.
- Danh sách có pagination/count tenant-scoped, chỉ trả `DocumentView` thay vì entity.
- Nếu ID khác tenant, `view` trả `404` để không xác nhận đối tượng ngoài phạm vi có tồn tại.
- Dùng H2 in-memory và data seed bằng `schema.sql`/`data.sql`. Khi dùng PostgreSQL/MySQL production cần migration/index và database-specific tests.

### 6.1. Cấu trúc thư mục

```text
tenant-repository-demo/
├── settings.gradle
├── build.gradle
└── src/
    ├── main/
    │   ├── java/demo/
    │   │   ├── TenantRepositoryApplication.java
    │   │   ├── DocumentState.java
    │   │   ├── DocumentEntity.java
    │   │   ├── DocumentRepository.java
    │   │   ├── ActorDirectory.java
    │   │   ├── DocumentView.java
    │   │   └── DocumentService.java
    │   └── resources/
    │       ├── application.properties
    │       ├── schema.sql
    │       └── data.sql
    └── test/java/demo/
        └── TenantRepositorySecurityTest.java
```

### 6.2. Gradle và cấu hình SQL initialization

**`settings.gradle`:**

```groovy
rootProject.name = 'tenant-repository-demo'
```

**`build.gradle`:**

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.5.8'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'demo'
version = '1.0.0'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.boot:spring-boot-starter-data-jpa'

    runtimeOnly 'com.h2database:h2'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

`spring-boot-starter-data-jpa` cung cấp JPA, Spring Data repository và transaction manager tương ứng; H2 là DB embedded phục vụ demo. Ví dụ không dùng Spring MVC nên không cần starter-web.

**`src/main/resources/application.properties`:**

```properties
spring.jpa.hibernate.ddl-auto=none
spring.sql.init.mode=always
spring.jpa.open-in-view=false
```

Ta **tự tạo schema** bằng `schema.sql` và seed bằng `data.sql`, nên tắt Hibernate DDL auto. Không nên cho Hibernate DDL auto tự thay schema production; ở production thường dùng Flyway/Liquibase.

### 6.3. Tạo bảng có tenant và index

**`src/main/resources/schema.sql`:**

```sql
CREATE TABLE documents (
    id BIGINT PRIMARY KEY,
    tenant_id VARCHAR(40) NOT NULL,
    owner_id VARCHAR(64) NOT NULL,
    state VARCHAR(30) NOT NULL,
    title VARCHAR(150) NOT NULL,
    version BIGINT NOT NULL
);

CREATE INDEX idx_documents_tenant_state_id
    ON documents (tenant_id, state, id);

CREATE INDEX idx_documents_tenant_owner
    ON documents (tenant_id, owner_id, id);
```

**`src/main/resources/data.sql`:**

```sql
INSERT INTO documents (
    id, tenant_id, owner_id, state, title, version
) VALUES
    (11, 'T1', 'u-alice', 'DRAFT', 'Alpha', 1),
    (12, 'T1', 'u-bob',   'DRAFT', 'Beta',  1),
    (13, 'T2', 'u-carol', 'DRAFT', 'Gamma', 1),
    (14, 'T1', 'u-alice', 'APPROVED', 'Locked', 1);
```

`id` trong demo là global ID, giúp tránh hai tenant dùng cùng `Document#11`. Nếu sản phẩm dùng **tenant-local ID**, hãy thiết kế composite key `(tenant_id, local_id)` hoặc một globally unique surrogate ID, rồi dùng tenant guard nhất quán trên mọi bảng liên kết, ACL và cache.

### 6.4. State enum

**`src/main/java/demo/DocumentState.java`:**

```java
package demo;

public enum DocumentState {
    DRAFT,
    APPROVED
}
```

### 6.5. JPA entity: có tenant nhưng không nhận từ client

**`src/main/java/demo/DocumentEntity.java`:**

```java
package demo;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.EnumType;
import jakarta.persistence.Enumerated;
import jakarta.persistence.Id;
import jakarta.persistence.Table;
import jakarta.persistence.Version;

@Entity
@Table(name = "documents")
public class DocumentEntity {

    @Id
    @Column(name = "id")
    private Long id;

    @Column(name = "tenant_id", nullable = false)
    private String tenantId;

    @Column(name = "owner_id", nullable = false)
    private String ownerId;

    @Enumerated(EnumType.STRING)
    @Column(name = "state", nullable = false)
    private DocumentState state;

    @Column(name = "title", nullable = false)
    private String title;

    @Version
    @Column(name = "version", nullable = false)
    private long version;

    protected DocumentEntity() {
    }

    public Long getId() {
        return id;
    }

    public String getTenantId() {
        return tenantId;
    }

    public String getOwnerId() {
        return ownerId;
    }

    public DocumentState getState() {
        return state;
    }

    public String getTitle() {
        return title;
    }

    public long getVersion() {
        return version;
    }
}
```

Entity không có setter public và không được dùng làm `@RequestBody`. Nhưng **không có setter không tự bảo vệ toàn ứng dụng**: ORM vẫn nạp các field bằng reflection; các service khác có thể thực hiện bulk JPQL/SQL. Quyền được thực thi bởi repository contract, service policy và DB controls.

`@Version` hữu ích với optimistic locking khi cập nhật entity managed. Với JPQL bulk `UPDATE`, JPA provider **không tự áp version increment/check như một managed-entity update**, nên repository ở phần sau đưa `version` và `version+1` vào câu lệnh rõ ràng.

### 6.6. Repository: tenant predicate cho đọc, page, count và write

**`src/main/java/demo/DocumentRepository.java`:**

```java
package demo;

import java.util.Optional;

import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Modifying;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;

public interface DocumentRepository
        extends JpaRepository<DocumentEntity, Long> {

    // Luôn tra theo ID + tenant; không dùng findById unscoped ở service.
    Optional<DocumentEntity> findByIdAndTenantId(
        Long id,
        String tenantId
    );

    // Cả data query và count query của Page đều theo tenant/state.
    Page<DocumentEntity> findByTenantIdAndState(
        String tenantId,
        DocumentState state,
        Pageable pageable
    );

    long countByTenantIdAndState(
        String tenantId,
        DocumentState state
    );

    // Bulk update cần explicit tenant/owner/state/version policy.
    @Modifying(flushAutomatically = true, clearAutomatically = true)
    @Query("""
        update DocumentEntity d
        set d.title = :title,
            d.version = d.version + 1
        where d.id = :id
          and d.tenantId = :tenantId
          and d.ownerId = :ownerId
          and d.state = :state
          and d.version = :expectedVersion
        """)
    int changeTitleIfOwner(
        @Param("id") Long id,
        @Param("tenantId") String tenantId,
        @Param("ownerId") String ownerId,
        @Param("state") DocumentState state,
        @Param("expectedVersion") long expectedVersion,
        @Param("title") String title
    );
}
```

**Giải thích từng method:**

- `findByIdAndTenantId`: không nhìn thấy ID ở tenant khác, dù ID có thực trong DB.
- `findByTenantIdAndState`: trả `Page` có tenant trong predicate; count query của repository cũng được suy ra từ điều kiện tenant + state.
- `countByTenantIdAndState`: dashboard/metadata không đếm lẫn tenant.
- `changeTitleIfOwner`: chỉ cập nhật khi **đúng tenant, đúng owner, đúng trạng thái và đúng phiên bản**. Trả số row affected, service từ chối nếu khác `1`.
- `@Modifying`: báo Spring Data đây là JPQL DML, không phải `SELECT`. `flushAutomatically/clearAutomatically` giúp kiểm soát persistence context quanh bulk update, nhưng **có thể flush/clear những entity khác đang được quản lý**; phải cân nhắc transaction thật.
- Bulk update không tự gọi lifecycle callbacks của từng JPA entity và không áp version check tự động; câu lệnh tự tăng/check `version` là chủ đích.

**Cảnh báo:** interface kế thừa `JpaRepository` vẫn có `findAll()` và `findById()` không scoped. Việc demo không gọi những method ấy trong **application service** không có nghĩa mọi nơi trong codebase bị ngăn dùng. Với production, thiết kế một **tenant-aware repository facade** hoặc interface hẹp và thêm architecture tests.

### 6.7. Trusted actor directory

**`src/main/java/demo/ActorDirectory.java`:**

```java
package demo;

import java.util.Map;

import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.authentication.AuthenticationTrustResolver;
import org.springframework.security.authentication.AuthenticationTrustResolverImpl;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.stereotype.Component;

record Actor(String userId, String tenantId) {
}

@Component
public class ActorDirectory {

    private final Map<String, Actor> actors = Map.of(
        "alice", new Actor("u-alice", "T1"),
        "bob",   new Actor("u-bob", "T1"),
        "carol", new Actor("u-carol", "T2")
    );

    private final AuthenticationTrustResolver trustResolver =
        new AuthenticationTrustResolverImpl();

    public Actor requireCurrent() {
        Authentication authentication =
            SecurityContextHolder.getContext().getAuthentication();

        if (authentication == null
                || !authentication.isAuthenticated()
                || trustResolver.isAnonymous(authentication)) {
            throw new AccessDeniedException("No trusted user");
        }

        Actor actor = actors.get(authentication.getName());
        if (actor == null) {
            throw new AccessDeniedException("No trusted tenant");
        }

        return actor;
    }
}
```

`Actor` chỉ dùng trong server. Trong production, từ JWT/OIDC nên ánh xạ stable subject ID và issuer/membership, không tùy tiện tin `getName()` là unique toàn hệ thống nếu username trùng giữa tenants. Với user đa tenant, cần policy lựa chọn active tenant có xác minh membership.

Đặc biệt, `AnonymousAuthenticationToken` có thể có `isAuthenticated() == true`; `AuthenticationTrustResolver` giúp tránh nhầm anonymous với principal thực.

### 6.8. DTO response: không trả nguyên entity khi không cần

**`src/main/java/demo/DocumentView.java`:**

```java
package demo;

public record DocumentView(
        Long id,
        String title,
        String state,
        long version) {

    public static DocumentView from(DocumentEntity d) {
        return new DocumentView(
            d.getId(),
            d.getTitle(),
            d.getState().name(),
            d.getVersion()
        );
    }
}
```

`DocumentView` không chứa `ownerId`/`tenantId` hay field bí mật không cần đưa ra client. Tùy API có thể trả tenant label cho người quản trị, nhưng không nên tự serialize mọi association và ACL metadata.

### 6.9. Service: authority + tenant-scoped repository + owner guard

**`src/main/java/demo/DocumentService.java`:**

```java
package demo;

import org.springframework.data.domain.Page;
import org.springframework.data.domain.PageRequest;
import org.springframework.data.domain.Sort;
import org.springframework.http.HttpStatus;
import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.web.server.ResponseStatusException;

@Service
public class DocumentService {

    private final DocumentRepository repository;
    private final ActorDirectory directory;

    public DocumentService(
            DocumentRepository repository,
            ActorDirectory directory) {
        this.repository = repository;
        this.directory = directory;
    }

    @PreAuthorize("hasAuthority('document:read')")
    @Transactional(readOnly = true)
    public DocumentView view(Long id) {
        Actor actor = directory.requireCurrent();

        DocumentEntity document = repository
            .findByIdAndTenantId(id, actor.tenantId())
            .orElseThrow(() -> new ResponseStatusException(
                HttpStatus.NOT_FOUND, "Document unavailable"));

        return DocumentView.from(document);
    }

    @PreAuthorize("hasAuthority('document:read')")
    @Transactional(readOnly = true)
    public Page<DocumentView> listDraft(int page, int size) {
        Actor actor = directory.requireCurrent();

        if (page < 0 || size < 1 || size > 100) {
            throw new IllegalArgumentException("Invalid page");
        }

        var pageable = PageRequest.of(
            page,
            size,
            Sort.by(Sort.Direction.ASC, "id")
        );

        return repository
            .findByTenantIdAndState(
                actor.tenantId(),
                DocumentState.DRAFT,
                pageable
            )
            .map(DocumentView::from);
    }

    @PreAuthorize("hasAuthority('document:write')")
    @Transactional
    public DocumentView changeTitle(
            Long id, String newTitle, long expectedVersion) {

        Actor actor = directory.requireCurrent();

        if (newTitle == null || newTitle.isBlank()
                || newTitle.length() > 150) {
            throw new IllegalArgumentException("Invalid title");
        }

        // Một JPQL update có đủ tenant/owner/state/version predicates.
        int changed = repository.changeTitleIfOwner(
            id,
            actor.tenantId(),
            actor.userId(),
            DocumentState.DRAFT,
            expectedVersion,
            newTitle
        );

        if (changed != 1) {
            // Không tiết lộ ID tồn tại ở tenant khác hay ai là owner.
            throw new AccessDeniedException(
                "Document cannot be updated"
            );
        }

        return repository
            .findByIdAndTenantId(id, actor.tenantId())
            .map(DocumentView::from)
            .orElseThrow(() -> new IllegalStateException(
                "Updated document was not found"));
    }
}
```

**Tại sao tenant predicate xuất hiện hai lần ở lệnh ghi?** Lần thứ nhất trong `UPDATE` để ràng buộc quyền **ngay tại thời điểm mutation**; lần sau ở `SELECT` để chỉ đọc lại bản ghi trong tenant được xác minh. Nếu chỉ đặt tenant trong lời gọi read trước rồi dùng unscoped update sau, có thể tạo TOCTOU hoặc sửa sai tài nguyên khi code thay đổi.

`@PreAuthorize` yêu cầu authority, còn `ActorDirectory` và repository bảo vệ tenant. **Authority và tenant là phép AND**, không phải OR. Với write, `ownerId` và `state` tăng thêm độ chặt.

**HTTP status của `ResponseStatusException`** chỉ thể hiện khi method được gọi qua MVC/controller với exception resolver; trong demo CLI, chúng ta bắt exception và in `NOT_FOUND`. Cùng một đường này có thể trả 404 cho ID không tồn tại hoặc khác tenant, hạn chế enumeration.

`DocumentService` là bean do Spring quản lý nên Method Security và `@Transactional` được áp dụng khi caller đi qua proxy. Đừng gọi `this.changeTitle(...)` từ cùng bean rồi mặc định rằng annotation sẽ được intercept.

### 6.10. Bootstrap và kịch bản chạy

**`src/main/java/demo/TenantRepositoryApplication.java`:**

```java
package demo;

import java.util.Arrays;
import java.util.List;

import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Profile;
import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.core.context.SecurityContext;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.web.server.ResponseStatusException;

@SpringBootApplication
@EnableMethodSecurity
public class TenantRepositoryApplication {

    public static void main(String[] args) {
        SpringApplication.run(TenantRepositoryApplication.class, args);
    }

    @Bean
    @Profile("!test")
    CommandLineRunner scenario(DocumentService documents) {
        return args -> {
            try {
                login("alice", "document:read", "document:write");
                var aliceDrafts = documents.listDraft(0, 10);
                System.out.println("ALICE_DRAFT_IDS: "
                    + ids(aliceDrafts));
                System.out.println("ALICE_DRAFT_TOTAL: "
                    + aliceDrafts.getTotalElements());

                notFound("ALICE_READ_13", () -> documents.view(13L));

                System.out.println("ALICE_UPDATE_11: "
                    + documents.changeTitle(
                        11L, "Alpha revised", 1L).title());

                login("bob", "document:read", "document:write");
                System.out.println("BOB_DRAFT_IDS: "
                    + ids(documents.listDraft(0, 10)));
                denied("BOB_UPDATE_11", () ->
                    documents.changeTitle(11L, "Stolen", 2L));

                login("carol", "document:read", "document:write");
                System.out.println("CAROL_DRAFT_IDS: "
                    + ids(documents.listDraft(0, 10)));
                notFound("CAROL_READ_11", () -> documents.view(11L));

                login("alice", "document:write");
                denied("ALICE_WITHOUT_READ", () ->
                    documents.listDraft(0, 10));

                login("alice", "document:read");
                var finalRow = documents.view(11L);
                System.out.println("FINAL_TITLE_11: "
                    + finalRow.title());
                System.out.println("FINAL_VERSION_11: "
                    + finalRow.version());
            } finally {
                SecurityContextHolder.clearContext();
            }
        };
    }

    private static List<Long> ids(
            org.springframework.data.domain.Page<DocumentView> page) {
        return page.getContent().stream()
            .map(DocumentView::id)
            .toList();
    }

    private static void login(
            String username, String... authorities) {

        var grants = Arrays.stream(authorities)
            .map(SimpleGrantedAuthority::new)
            .toList();

        var auth = new UsernamePasswordAuthenticationToken(
            username, "demo-only", grants);

        SecurityContext context =
            SecurityContextHolder.createEmptyContext();
        context.setAuthentication(auth);
        SecurityContextHolder.setContext(context);
    }

    private static void denied(String label, Runnable operation) {
        try {
            operation.run();
            System.out.println(label + ": UNEXPECTED_ALLOW");
        } catch (AccessDeniedException expected) {
            System.out.println(label + ": DENIED");
        }
    }

    private static void notFound(
            String label, Runnable operation) {
        try {
            operation.run();
            System.out.println(label + ": UNEXPECTED_ALLOW");
        } catch (ResponseStatusException expected) {
            System.out.println(label + ": NOT_FOUND");
        }
    }
}
```

`@EnableMethodSecurity` bật `@PreAuthorize`. Ví dụ không có web controller; nó gọi Spring-managed service từ `CommandLineRunner`.

**Cảnh báo:** `UsernamePasswordAuthenticationToken` với username và authorities được tự dựng chỉ dùng để **mô phỏng CLI/test**. Production phải xác minh token/credentials bằng Spring Security filter/provider. Không dùng đoạn `login(...)` như endpoint cho client tự chọn user hoặc role.

### 6.11. Chạy và đối chiếu output

Trong thư mục dự án, với Gradle Wrapper:

```bash
./gradlew bootRun
```

PowerShell:

```bash
.\gradlew.bat bootRun
```

Nếu dự án chưa có Gradle Wrapper, cài Gradle phù hợp hoặc tạo Wrapper trước rồi chạy. Bỏ qua log của Spring Boot/Gradle, các dòng `System.out.println` của chương trình được dự kiến như sau:

```text
ALICE_DRAFT_IDS: [11, 12]
ALICE_DRAFT_TOTAL: 2
ALICE_READ_13: NOT_FOUND
ALICE_UPDATE_11: Alpha revised
BOB_DRAFT_IDS: [11, 12]
BOB_UPDATE_11: DENIED
CAROL_DRAFT_IDS: [13]
CAROL_READ_11: NOT_FOUND
ALICE_WITHOUT_READ: DENIED
FINAL_TITLE_11: Alpha revised
FINAL_VERSION_11: 2
```

**Giải thích kết quả:**

- Alice và Bob cùng tenant T1 thấy tài liệu `11`, `12` ở trạng thái `DRAFT`, tổng 2. Tài liệu `14` đã `APPROVED` nên không nằm trong danh sách Draft.
- Tài liệu `13` thuộc T2; Alice không thể đọc dù biết ID 13.
- Alice là owner của tài liệu 11, đúng tenant, authority và expectedVersion 1 nên cập nhật thành công; version 1 -> 2.
- Bob thuộc **cùng tenant** nhưng **không phải owner** của tài liệu 11. Lệnh cập nhật bị từ chối dù expectedVersion 2 đúng.
- Carol thuộc T2, chỉ thấy tài liệu 13; không đọc được tài liệu 11 của T1.
- Alice thiếu authority `document:read` ở lần cuối trước khi in kết quả; Method Security từ chối dù directory vẫn ghi nhận cô thuộc T1.
- Sau khi khôi phục authority đọc, service đọc bản ghi 11; title là `Alpha revised`, version 2.

**Các dòng trên là kết quả dự kiến từ source code, không phải khẳng định đã chạy chương trình ở môi trường này.** Kết quả phụ thuộc việc Spring Boot/H2 khởi tạo được schema và Method Security proxy thực thi đúng.

## 7. Integration test: chứng minh không có dữ liệu chéo tenant

**`src/test/java/demo/TenantRepositorySecurityTest.java`:**

```java
package demo;

import java.util.List;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.data.domain.Page;
import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.test.context.support.WithAnonymousUser;
import org.springframework.security.test.context.support.WithMockUser;
import org.springframework.test.annotation.DirtiesContext;
import org.springframework.test.context.ActiveProfiles;
import org.springframework.web.server.ResponseStatusException;

@SpringBootTest
@ActiveProfiles("test")
@DirtiesContext(classMode =
    DirtiesContext.ClassMode.AFTER_EACH_TEST_METHOD)
class TenantRepositorySecurityTest {

    @Autowired
    DocumentService service;

    @Autowired
    DocumentRepository repository;

    private static List<Long> ids(Page<DocumentView> page) {
        return page.getContent().stream()
            .map(DocumentView::id).toList();
    }

    @Test
    @WithMockUser(
        username = "alice",
        authorities = {"document:read", "document:write"}
    )
    void listAndCountApplyTenantBeforePagination() {
        Page<DocumentView> first = service.listDraft(0, 1);
        Page<DocumentView> second = service.listDraft(1, 1);

        assertEquals(List.of(11L), ids(first));
        assertEquals(List.of(12L), ids(second));
        assertEquals(2L, first.getTotalElements());
        assertEquals(2L, second.getTotalElements());
        assertEquals(2L, repository.countByTenantIdAndState(
            "T1", DocumentState.DRAFT));
    }

    @Test
    @WithMockUser(username = "carol", authorities = "document:read")
    void tenantT2CannotViewT1() {
        assertEquals(List.of(13L), ids(service.listDraft(0, 10)));
        assertEquals("Gamma", service.view(13L).title());

        assertThrows(
            ResponseStatusException.class,
            () -> service.view(11L));
        assertTrue(repository.findByIdAndTenantId(11L, "T2").isEmpty());
    }

    @Test
    @WithMockUser(username = "alice", authorities = "document:read")
    void tenantT1CannotViewT2EvenWithKnownId() {
        assertThrows(
            ResponseStatusException.class,
            () -> service.view(13L));

        assertTrue(repository.findByIdAndTenantId(13L, "T1").isEmpty());
    }

    @Test
    @WithMockUser(username = "bob", authorities = "document:write")
    void sameTenantIsNotEnoughToEditNonOwnerRecord() {
        DocumentEntity before = repository.findById(11L).orElseThrow();

        assertThrows(
            AccessDeniedException.class,
            () -> service.changeTitle(11L, "Stolen", 1L));

        DocumentEntity after = repository.findById(11L).orElseThrow();
        assertEquals(before.getTitle(), after.getTitle());
        assertEquals(before.getVersion(), after.getVersion());
        assertEquals("T1", after.getTenantId());
        assertEquals("u-alice", after.getOwnerId());
    }

    @Test
    @WithMockUser(username = "alice", authorities = "document:write")
    void validOwnerUpdateKeepsTenantAndIncrementsVersion() {
        DocumentView updated =
            service.changeTitle(11L, "Revised", 1L);

        assertEquals("Revised", updated.title());
        assertEquals(2L, updated.version());

        DocumentEntity stored = repository.findById(11L).orElseThrow();
        assertEquals("T1", stored.getTenantId());
        assertEquals("u-alice", stored.getOwnerId());
        assertEquals("Revised", stored.getTitle());
        assertEquals(2L, stored.getVersion());
    }

    @Test
    @WithMockUser(username = "alice", authorities = "document:write")
    void staleVersionCannotOverwrite() {
        assertThrows(
            AccessDeniedException.class,
            () -> service.changeTitle(11L, "Wrong", 99L));

        DocumentEntity stored = repository.findById(11L).orElseThrow();
        assertEquals("Alpha", stored.getTitle());
        assertEquals(1L, stored.getVersion());
    }

    @Test
    @WithMockUser(username = "alice", authorities = "document:read")
    void readAuthorityDoesNotGrantWrite() {
        assertThrows(
            AccessDeniedException.class,
            () -> service.changeTitle(11L, "Wrong", 1L));
    }

    @Test
    @WithMockUser(username = "ghost", authorities = "document:read")
    void missingTrustedTenantFailsClosed() {
        assertThrows(
            AccessDeniedException.class,
            () -> service.listDraft(0, 10));
    }

    @Test
    @WithAnonymousUser
    void anonymousIsDenied() {
        assertThrows(
            AccessDeniedException.class,
            () -> service.listDraft(0, 10));
    }
}
```

Chạy:

```bash
./gradlew test
```

**Vì sao dùng `@SpringBootTest`?** Test khởi tạo ApplicationContext, Spring Data repository, H2, `@EnableMethodSecurity`, Spring AOP proxies và transaction manager. `@WithMockUser` cung cấp authentication cho lời gọi test; `@ActiveProfiles("test")` vô hiệu hóa CLI runner. `@DirtiesContext` đảm bảo mỗi test có dữ liệu seed lại từ đầu.

**Lưu ý:** test trực tiếp gọi `repository.findById(...)` **chỉ để đọc trạng thái DB làm bằng chứng** sau khi request bị từ chối. Ở production, service phục vụ caller không được sử dụng unscoped repository methods như vậy.

### 7.1. Ma trận kiểm chứng

| Caller và authority | Hành động | Kỳ vọng | Điều kiện quyết định |
| --- | --- | --- | --- |
| Alice/T1 + `document:read` | Liệt kê Draft | IDs 11, 12; count 2 | Tenant T1 + state DRAFT |
| Alice/T1 + `document:read` | Đọc ID 13 (T2) | Không tìm thấy theo scope | `id AND tenant_id` |
| Carol/T2 + `document:read` | Liệt kê Draft | Chỉ ID 13 | Tenant T2 |
| Carol/T2 + `document:read` | Đọc ID 11 (T1) | Không tìm thấy theo scope | `id AND tenant_id` |
| Bob/T1 + `document:write` | Sửa ID 11 của Alice | Từ chối | Tenant đúng nhưng owner sai |
| Alice/T1 + `document:write` | Sửa ID 11, version 1 | Thành công, version 2 | Tenant + owner + state + version |
| Alice/T1 + `document:write` | Sửa ID 11 với version 99 | Từ chối | Stale version |
| Alice/T1 chỉ có `document:read` | Sửa ID 11 | Từ chối | Function-level authority |
| Ghost không có directory tenant | Liệt kê | Từ chối | Fail closed |
| Anonymous | Liệt kê | Từ chối | Method Security |

Chỉ assert HTTP 403/404 là chưa đủ trong ứng dụng web. Với thao tác ghi, hãy đọc lại DB để xác nhận `tenantId`, `ownerId`, title, version và ACL/grants không bị thay đổi trái phép.

## 8. JOIN, subquery và quan hệ giữa những bảng nhiều tenant

### 8.1. JOIN phải bảo vệ cả bảng liên kết

Giả sử có bảng `projects` và `documents.project_id`. Query yếu:

```sql
SELECT d.id, d.title
FROM documents d
JOIN projects p ON p.id = d.project_id
WHERE d.tenant_id = :tenant;
```

Nếu database hoặc application có dữ liệu quan hệ sai, JOIN có thể ghép document của T1 với project của T2. An toàn hơn:

```sql
SELECT d.id, d.title
FROM documents d
JOIN projects p
  ON p.id = d.project_id
 AND p.tenant_id = d.tenant_id
WHERE d.tenant_id = :trustedTenant
  AND p.tenant_id = :trustedTenant;
```

Đây là **SQL minh họa cho schema có `project_id`**, không phải truy vấn runnable trong schema demo, vì demo không có bảng `projects`. Ở tầng dữ liệu, thiết kế **composite foreign key `(tenant_id, project_id)`** khi thích hợp để database cũng duy trì quan hệ cùng tenant.

### 8.2. Chia sẻ tài liệu trong tenant qua `EXISTS`

Một hệ thống có grant per-user:

```sql
SELECT d.id, d.title
FROM documents d
WHERE d.tenant_id = :trustedTenant
  AND (
       d.owner_id = :trustedUser
       OR EXISTS (
           SELECT 1
           FROM document_grants g
           WHERE g.document_id = d.id
             AND g.tenant_id = d.tenant_id
             AND g.grantee_id = :trustedUser
             AND g.permission = 'READ'
       )
  )
ORDER BY d.id;
```

Bảng `document_grants` là **mở rộng minh họa** không có trong demo JPA. Điều quan trọng là cả document và grant đều được ràng buộc tenant, không lấy grant ở tenant khác chỉ vì có ID trùng.

Nếu rule có **DENY overriding ALLOW**, role hierarchy, share expiration hoặc ACL inheritance, SQL `EXISTS READ` đơn giản **chưa chắc** phản ánh đủ policy. Với những chính sách ấy, cần model authorization service hoặc join/CTE phù hợp và contract tests so sánh kết quả.

### 8.3. Tránh duplicate khi JOIN nhiều grants

Một document có nhiều ACE hoặc nhiều tags có thể bị nhân bản khi JOIN. Nếu truy vấn trả `Page`, tổng số hàng có thể bị phóng đại và phân trang sai. Sử dụng `EXISTS` nếu chỉ cần kiểm tra có bản ghi liên quan, hoặc `DISTINCT`/count phù hợp với semantics thực tế.

Với query JPA có `JOIN FETCH` collection và pagination, ORM có thể phải xử lý phân trang khác với SQL kỳ vọng. Cần cân nhắc two-step fetch (page IDs tenant-scoped trước, fetch detail theo tập IDs và tenant) và xác minh count query riêng.

## 9. Phân trang, count, aggregation và cursor phải cùng tenant

### 9.1. Đừng nạp mọi tenant rồi lọc trong Java

Không an toàn:

```java
// Sai thiết kế: đọc quá rộng rồi lọc.
return repository.findAll(PageRequest.of(page, size))
    .map(DocumentEntity::getTenantId)
    .stream()
    .filter(tenantId::equals)
    .toList();
```

Nhược điểm:

- Data đã được nạp từ tenant khác trước khi filter.
- Trang `size=20` có thể chỉ còn 3 bản ghi thuộc tenant hiện tại.
- `totalElements` có thể tiết lộ tổng số tài liệu toàn hệ thống.
- Query DB và memory tốn tài nguyên không cần thiết.
- Một code path khác có thể serialize/log object trước khi filter.

Cách đúng là `findByTenantIdAndState(trustedTenant, state, pageable)` để DB filter **trước LIMIT/OFFSET**.

### 9.2. `Page` so với `Slice`

`Page` có thể chạy thêm count query để biết `totalElements`, nên count cũng phải tenant-scoped. `Slice` chỉ cần xác định có trang tiếp theo, có thể tránh count đắt. Với danh sách rất lớn, keyset pagination có thể tốt hơn OFFSET.

Dù chọn loại nào, **tenant predicate phải nằm trong truy vấn xác định next page**, và sort key phải ổn định (`created_at`, `id` có tie-breaker). Không cho client truyền raw SQL `ORDER BY` hoặc tên cột bất kỳ; chỉ dùng whitelist fields được phép sort.

### 9.3. Aggregation/export là đường rò dữ liệu thường bị quên

Ví dụ endpoint dashboard `groupByState`, CSV export, background reports hay GraphQL resolver đều phải áp tenant predicate. Tìm một method `count()` không có tenant có thể đơn giản, nhưng nó vẫn làm lộ tổng số tài liệu của tổ chức khác.

Cần test **cả số lượng và nội dung** ở mỗi tenant: không chỉ kiểm tra row đầu tiên mà quên các chỉ số phụ.

## 10. UPDATE, DELETE, bulk import và transaction

### 10.1. Đặt guard ngay trong DML

Một nguy cơ TOCTOU:

```text
1. findByIdAndTenantId(id, tenant)
2. kiểm tra owner
3. quyền/owner bị thay bởi transaction khác
4. updateById(id, title) KHÔNG còn tenant/owner guard
```

Vì vậy trong demo, JPQL `changeTitleIfOwner` có **tenant, owner, state, version trong chính lệnh UPDATE**. Nếu chính sách viết phụ thuộc bảng grants/ACL khác, cần conditional UPDATE phù hợp DB hoặc khóa và recheck quyền trong transaction mà grant/revoke cũng tuân thủ.

Một SQL cập nhật theo grant:

```sql
UPDATE documents
SET title = :newTitle,
    version = version + 1
WHERE id = :id
  AND tenant_id = :trustedTenant
  AND version = :expectedVersion
  AND EXISTS (
      SELECT 1
      FROM document_grants g
      WHERE g.document_id = documents.id
        AND g.tenant_id = documents.tenant_id
        AND g.grantee_id = :trustedUser
        AND g.permission = 'WRITE'
  );
```

**SQL này là minh họa**, không chạy với schema demo (không có grants) và cú pháp/lock semantics phụ thuộc DB. Một statement không tự đưa ra đảm bảo thu hồi quyền realtime giữa nhiều nguồn dữ liệu; cần xác định isolation và transaction protocol.

### 10.2. DELETE phải bảo vệ tenant và quan hệ

Không gọi `repository.deleteById(id)` trực tiếp từ endpoint user nếu ID có thể đến từ tenant khác. Thay bằng delete có điều kiện:

```java
@Modifying
@Query("""
    delete from DocumentEntity d
    where d.id = :id
      and d.tenantId = :tenantId
      and d.ownerId = :ownerId
    """)
int deleteOwned(
    @Param("id") Long id,
    @Param("tenantId") String tenantId,
    @Param("ownerId") String ownerId);
```

Đây là **mảnh code repository**, không phải method có trong demo đầy đủ. JPA bulk delete có thể bỏ qua entity lifecycle callbacks/cascades trong memory, nên nếu tài liệu có file storage hoặc ACL cần dọn dẹp, phải dùng workflow domain phù hợp và transaction/outbox.

### 10.3. INSERT không lấy tenant từ JSON tùy ý

Khi tạo tài liệu:

```java
// MẢNH CODE service:
Actor actor = directory.requireCurrent();

DocumentEntity newDocument = factory.create(
    actor.tenantId(),
    actor.userId(),
    command.title()
);
```

Tenant và owner được server quyết định. Nếu người dùng có nhiều tenant và chọn tenant từ UI, server phải kiểm tra membership **trước khi** tạo dữ liệu. DTO đầu vào chỉ nên chứa fields người dùng có quyền tạo.

### 10.4. @Version, transaction và grant thay đổi

`@Version` trên document giúp phát hiện cập nhật cạnh tranh **của document entity**, nhưng thay đổi ở bảng ACL/grants không tự tăng version đó. Nếu quyền được thu hồi lúc giữa bước kiểm tra và ghi, cần recheck/lock/authorization version đúng mô hình. Không dùng `@Transactional(readOnly=true)` cho DML; không dùng `@PostAuthorize` làm lớp chặn duy nhất cho lệnh đã có side effect.

## 11. Row-Level Security (PostgreSQL): defense-in-depth ở tầng DB

Nếu ứng dụng dùng PostgreSQL, **Row-Level Security (RLS)** có thể ràng buộc tenant ở mức database, giúp giảm tác động khi một câu query ứng dụng quên `tenant_id`. Đây là công cụ bổ sung mạnh nhưng phải cấu hình đúng **DB role, connection pool, session/transaction context và quyền bypass**.

### 11.1. Chính sách RLS minh họa

Với bảng `documents` có `tenant_id` dạng text/varchar:

```sql
ALTER TABLE documents ENABLE ROW LEVEL SECURITY;

CREATE POLICY documents_tenant_policy
ON documents
FOR ALL
USING (
    tenant_id = current_setting('app.tenant_id', true)
)
WITH CHECK (
    tenant_id = current_setting('app.tenant_id', true)
);

-- Có thể ép owner của bảng cũng chịu RLS.
ALTER TABLE documents FORCE ROW LEVEL SECURITY;
```

`USING` xét **hàng hiện tại được phép đọc/sửa/xóa**; `WITH CHECK` xét **hàng mới được phép insert/update**. Khi `app.tenant_id` chưa được đặt, `current_setting(..., true)` trả NULL và so sánh tenant thường không thành true (fail closed trong policy trên).

Đây là **mảnh cấu hình PostgreSQL**, không phải SQL chạy trong H2 của demo. PostgreSQL table owner thường bypass RLS nếu không `FORCE`; **superuser và role có `BYPASSRLS` luôn có thể bypass**. Không chạy application bằng superuser/bypass role rồi nghĩ rằng policy bảo vệ mọi query.

### 11.2. Đưa tenant vào transaction DB đúng cách

Trong một transaction sau khi đã xác minh tenant, một ứng dụng PostgreSQL có thể đặt:

```sql
SELECT set_config('app.tenant_id', :trustedTenant, true);
```

Tham số cuối `true` đặt setting **local cho transaction**, giúp giảm nguy cơ connection pool giữ tenant context sang request khác. Dùng SQL parameter binding, không nối tenant vào chuỗi query.

Nhưng giải pháp này chỉ đáng tin khi:

- Mỗi DB transaction cần tenant đều được thiết lập context **trước câu query đầu tiên**.
- Tenant được xác minh từ server identity, không do client tự đặt.
- Connection pool không dùng setting `SESSION` tùy tiện hoặc bị rò sang request sau.
- Tất cả đường dùng DB (job, async, migration, admin) có policy riêng.
- App role không bypass RLS, và các function `SECURITY DEFINER` được review.
- Các bảng chứa dữ liệu tenant đều có policy, không chỉ bảng documents.
- Tests chạy bằng DB role giống production và kiểm chứng thiếu tenant là deny.

**RLS không thay thế quyền trên object hoặc field.** Một policy `tenant_id = current_setting(...)` vẫn cho người dùng xem mọi bản ghi trong tenant nếu ứng dụng không có owner/ACL rule bổ sung.

### 11.3. Truy vấn tenant vẫn nên explicit khi có RLS?

Thường có lợi khi giữ **repository tenant-scoped** để code biểu đạt rõ policy, hỗ trợ index/query plan, portability và unit/integration tests. RLS là một **hàng rào phòng thủ khác**; không nên dùng nó làm lý do bỏ kiểm tra authority/owner/status trong service. Chính sách ứng dụng và chính sách RLS phải được review để không mâu thuẫn hoặc mở quyền.

## 12. Tenant scope, cache và background jobs

### 12.1. Cache key không được thiếu tenant

Nếu cache dùng:

```text
key = documentId
```

mà ID chỉ unique trong từng tenant, T1.Document#11 và T2.Document#11 có thể dùng chung entry. Kể cả ID globally unique, response còn phụ thuộc quyền người gọi và policy đọc/field redaction.

Key điển hình cần cân nhắc:

```text
(tenantId, documentId, projection, policyVersion)
```

hoặc thêm `(principalId, action)` nếu cache kết quả đã được authorize theo người dùng. Không cache boolean `canRead(id)=true` cho toàn hệ thống mà thiếu user/tenant.

Cache invalidation cần chạy khi document đổi tenant, ACL/grant bị revoke, owner đổi, role membership thay đổi hoặc field-level policy đổi. TTL ngắn không đồng nghĩa thu hồi quyền tức thời.

### 12.2. ThreadLocal tenant context không tự truyền qua thread

Một số codebase dùng `TenantContextHolder` bằng `ThreadLocal`. Nếu không clear ở `finally`, request khác được phục vụ trên cùng thread có thể kế thừa tenant cũ; với `@Async`, tenant context còn có thể **không được truyền** sang thread mới.

Cách giảm rủi ro:

- Ưu tiên truyền **trusted tenant** tường minh từ application service sang repository method.
- Nếu buộc dùng context, thiết kế lifecycle set/clear chắc chắn và validate trước mỗi query.
- Với scheduled jobs, truyền scope tenant có chủ đích và dùng identity có quyền phù hợp.
- Với WebFlux/reactive, không suy rằng Servlet ThreadLocal áp dụng như cũ; dùng Reactor Context và các security facilities phù hợp.

### 12.3. Batch job chạy qua nhiều tenant

Một job báo cáo nội bộ có thể cần xử lý tất cả tenant, nhưng không nên dùng `findAll()` từ một API bình thường rồi “tạm bỏ tenant filter”. Thiết kế một luồng `TenantAdminJob` riêng, authz rõ ràng, phân trang theo tenant, audit lý do truy cập và giới hạn dữ liệu.

Một pattern:

```text
authorizedAdminJob
  -> list tenant IDs được phép xử lý
  -> for each tenant:
       verify job scope
       query repository theo đúng tenant ID
       xuất kết quả/metrics trong namespace tenant đó
```

Nếu business yêu cầu một báo cáo liên tenant, đó là **use case riêng** với authority riêng và kiểm soát truy cập dữ liệu tổng hợp.

## 13. Tenant-safe relationships và constraints

### 13.1. Global ID hoặc composite key

Hai mô hình phổ biến:

1. **Globally unique ID:** `documents.id` là global, `tenant_id` là ràng buộc độc lập. Dễ lookup bằng ID nhưng application vẫn phải filter tenant.
2. **Tenant-local ID:** cùng `id=11` tồn tại ở nhiều tenants. Khóa chính có thể là `(tenant_id, id)`; mọi JOIN, foreign key, cache và URL mapping phải dùng cả hai.

Với tenant-local ID, không dùng một `Map<Long, Document>` hoặc cache key là `id` đơn lẻ. Nên dùng key chứa tenant và tài liệu:

```java
record TenantDocumentKey(String tenantId, Long documentId) {
}
```

Trong JPA, có thể dùng `@EmbeddedId` hoặc `@IdClass` khi thực sự dùng composite primary key; query `findByIdAndTenantId` trong demo dùng globally unique `id`, không mặc định phù hợp mọi composite-key entity.

### 13.2. Foreign key cũng cần giữ tenant integrity

Một FK chỉ trỏ `documents.project_id -> projects.id` không tự bảo đảm document và project cùng tenant. Khi schema phù hợp, composite FK `(tenant_id, project_id)` có thể khóa bất biến này ở DB. Tùy product, có thể cho phép quan hệ cross-tenant có phê duyệt; khi đó cần model chia sẻ dữ liệu rõ ràng, không tạo join tùy tiện.

### 13.3. Unique constraint theo tenant

Ví dụ tên tài liệu hoặc mã khách hàng chỉ unique **trong tenant**, không phải toàn DB:

```sql
CREATE UNIQUE INDEX uq_documents_tenant_code
ON documents(tenant_id, business_code);
```

**SQL minh họa** cho schema có `business_code`, không tồn tại trong demo. Điều kiện unique theo tenant là data integrity, không phải tự động authorization. Một user vẫn phải được phép xem/sửa dữ liệu trong tenant mới được truy vấn code tương ứng.

## 14. Hiệu năng: tenant predicate còn là điều kiện tối ưu

Một query tenant-scoped giúp database có cơ hội tận dụng index:

```sql
CREATE INDEX idx_documents_tenant_state_id
ON documents(tenant_id, state, id);
```

Index `(tenant_id, state, id)` có ích cho danh sách `WHERE tenant_id=? AND state=? ORDER BY id` trong nhiều mô hình dữ liệu. Nhưng lựa chọn index phải dựa trên **EXPLAIN/ANALYZE, cardinality, kích thước tenant, phân bố status và workload**. Một tenant chiếm 90% bảng có thể có query plan khác hàng nghìn tenant nhỏ.

Với dataset lớn:

- Dùng pagination đúng phạm vi, tránh `findAll`/materialization vô hạn.
- Tránh N+1 qua associations sau khi đã tenant-filter root entity; lazy loading vẫn có thể sinh thêm queries.
- Nếu cần JOIN FETCH, kiểm tra ảnh hưởng tới pagination/count.
- Dùng projection/DTO cho dữ liệu cần thiết; không trả entity graph đầy đủ.
- Dùng tenant-aware caching với invalidation.
- Kiểm tra query plan của cả `SELECT` **và** `COUNT`.
- Không thêm một `OR tenant = ...` từ client có thể bypass index/policy.

**Khi tối ưu hóa, không bỏ tenant predicate vì thấy truy vấn chậm.** Nếu index chưa phù hợp, sửa index/partition/query shape thay vì bỏ ranh giới bảo mật.

## 15. Những lỗi thường gặp và cách chẩn đoán

| Triệu chứng | Nguyên nhân | Cách sửa |
| --- | --- | --- |
| Alice đọc được Document#13 của T2 | `findById(id)` không có tenant | `findByIdAndTenantId(id, trustedTenant)` |
| Có tenant predicate nhưng client chọn được T2 | Tenant lấy từ query/header không verify | Lấy từ trusted membership directory |
| `findAll` trả tài liệu tất cả tenant | Unscoped inherited repository method | Tenant-scoped service/facade, query guard |
| `Page` chỉ có 3/20 item | Lọc tenant sau khi phân trang | Đặt tenant trong query DB trước LIMIT |
| `totalElements` đếm dữ liệu toàn hệ thống | Count query quên tenant | Count theo cùng tenant filter |
| JOIN trả dữ liệu của project tenant khác | JOIN chỉ theo ID | Kiểm tra tenant ở cả hai bảng, FK composite khi phù hợp |
| Nhánh OR trả tài liệu public ở tenant khác | Thiếu ngoặc quanh `owner OR public` | `tenant = ? AND (owner = ? OR public)` |
| Bob cùng tenant sửa tài liệu Alice | Tenant được coi là đủ cho WRITE | Kiểm tra owner/ACL/state trong DML |
| UPDATE trả thành công với ID tenant khác | DML chỉ có `WHERE id = ?` | `WHERE id AND tenant AND owner/version` |
| Không tìm thấy ID nhưng service fallback findAll | Fail-open | Deny/404, không bỏ scope |
| Token anonymous vẫn được nhận | Chỉ kiểm tra `isAuthenticated()` thô | AuthenticationTrustResolver/isAuthenticated expression |
| `@PreAuthorize` có nhưng data query sai | Authority không thêm tenant filter | Guard ngay tại repository |
| Cache lộ dữ liệu qua tenant | Key thiếu tenant/identity | Tenant-aware cache key và invalidation |
| Thread reuse giữ tenant trước | Tenant ThreadLocal không clear | Scope lifecycle và explicit tenant parameter |
| RLS không có tác dụng | App DB role là superuser/BYPASSRLS | Đúng DB role, FORCE nếu cần, tests |
| Tenant RLS setting rò qua pool | Dùng session setting không reset | Transaction-local context, connection tests |
| Test chỉ tenant T1 | Không phát hiện chéo tenant | Seed ít nhất T1+T2, positive/negative tests |
| Entity mới thêm field public mà query chưa đổi | Policy/DTO bị drift | Contract tests, review schema & API |
| Hệ thống dùng ID local nhưng cache chỉ theo ID | Collision giữa tenants | Composite key `(tenant, id)` |
| Bulk update bỏ qua JPA callbacks/version | `@Modifying` JPQL DML semantics | Explicit version predicate và transaction |
| Có RLS nhưng API vẫn leak count từ cache | Cache/report bypass DB RLS | Tenant scope cho mọi đường output |

### Checklist review một endpoint đa tenant

1. Xác định `Authentication` và user ID từ provider đã xác minh.
2. Xác định tenant scope/active tenant từ membership server và kiểm tra trạng thái.
3. Kiểm tra authority chức năng trước khi truy cập dữ liệu.
4. Với `findById`, bảo đảm SQL/JPQL có `id AND tenant`.
5. Với list/search, bảo đảm **mọi nhánh OR** nằm dưới tenant filter.
6. Với pagination/count/aggregation/export, dùng cùng tenant predicate.
7. Với JOIN/subquery, kiểm tra tenant của mọi bảng liên quan.
8. Với UPDATE/DELETE, đưa tenant và object/owner/version guard vào DML.
9. Không bind `tenantId` từ JSON/client chưa verify.
10. Không dùng inherited `findAll`/`deleteById` ở endpoint người dùng.
11. Kiểm tra response DTO, cache, background jobs và async context.
12. Seed ít nhất hai tenant trong integration test và assert cả dữ liệu **không được thấy**.
13. Với RLS, xác minh DB role không bypass và session tenant được set/reset đúng.
14. Với grant/ACL thay đổi đồng thời, xác định transaction, lock và recheck policy.

## 16. Bài tập tự kiểm tra

1. **`@PreAuthorize("hasAuthority('document:read')")` có tự thêm `tenant_id` vào SQL không?**  
   Không. Nó kiểm tra quyền chức năng; repository vẫn phải dùng tenant predicate.

2. **Vì sao `findByIdAndTenantId(id, request.getTenantId())` chưa đủ?**  
   Vì `tenantId` do client tự khai có thể là tenant của nạn nhân. Phải verify membership hoặc lấy trusted tenant từ server.

3. **Query nào đúng để lọc owner và public trong tenant?**  
   `WHERE tenant_id = :tenant AND (owner_id = :user OR public = TRUE)`. Không để OR vượt phạm vi tenant.

4. **Có thể dùng `findAll(pageable)` rồi lọc trong Java không?**  
   Không phù hợp cho API cách ly tenant: đọc quá rộng, sai phân trang/count và có nguy cơ lộ dữ liệu.

5. **Nếu chỉ muốn hiển thị tổng số DRAFT, query count cần gì?**  
   `WHERE tenant_id = :trustedTenant AND state='DRAFT'`.

6. **Tại sao cần tenant predicate trong lệnh UPDATE?**  
   Để DB không sửa tài liệu khác tenant dù caller biết ID hoặc có race sau khi pre-check.

7. **Bob ở T1 được quyền document:write, có tự sửa Document#11 của Alice không?**  
   Không trong policy demo. Điều kiện owner và state cũng cần đúng.

8. **Một JPQL bulk update có tự tăng `@Version` không?**  
   Không nên trông chờ điều đó. Demo tự đặt `d.version = d.version + 1` và `expectedVersion`.

9. **Điều gì xảy ra nếu một JOIN chỉ ghép `project_id` mà bỏ tenant?**  
   Có thể ghép nhầm quan hệ cross-tenant, nhất là khi dữ liệu/khóa ngoại không ngăn. Cần join/constraint cùng tenant.

10. **RLS của PostgreSQL có thay `@PreAuthorize` không?**  
    Không. RLS lọc hàng DB; vẫn cần quyền chức năng, object và field policy.

11. **Vì sao phải dùng transaction-local tenant context cho RLS?**  
    Vì pooled connections có thể được tái sử dụng giữa requests, setting session sai có thể rò tenant.

12. **Nếu ID chỉ unique trong từng tenant, cache key cần gì?**  
    Ít nhất tenant ID và local ID; nếu response tùy quyền, còn cần identity/policy scope.

13. **Làm sao test rằng Carol T2 không đọc được T1?**  
    Seed T1/T2, gọi service với `@WithMockUser(carol)` và assert lookup T1 bị deny/not found; kiểm tra list chỉ có ID T2.

14. **Một Page có tổng `2` nhưng chứa row từ tenant khác có an toàn không?**  
    Không. Cần assert **toàn bộ nội dung** thuộc đúng tenant và không có hàng bị cấm.

15. **Nếu application cần báo cáo toàn hệ thống thì có được bỏ tenant trong API thường?**  
    Không. Tạo luồng admin/job riêng với authority, scope, audit và query rõ mục đích.

## 17. Tài liệu chính thức

1. [Spring Data JPA — Query Methods](https://docs.spring.io/spring-data/jpa/reference/jpa/query-methods.html): derived queries, `@Query`, `@Param`, native queries và `@Modifying`.
2. [Spring Data JPA — Defining Query Methods](https://docs.spring.io/spring-data/jpa/reference/repositories/query-methods-details.html): reserved methods, `Pageable`, `Page`/`Slice`, sorting và đếm số bản ghi.
3. [Spring Data JPA — Specifications](https://docs.spring.io/spring-data/jpa/reference/jpa/specifications.html): kết hợp tenant predicate với criteria động.
4. [Spring Security — Method Security](https://docs.spring.io/spring-security/reference/servlet/authorization/method-security.html): `@EnableMethodSecurity`, `@PreAuthorize`, authentication và proxy.
5. [Spring Boot — SQL Databases](https://docs.spring.io/spring-boot/reference/data/sql.html): datasource, JPA/JDBC và SQL initialization.
6. [Spring Framework — Declarative Transactions](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/annotations.html): `@Transactional`, transaction boundaries, self-invocation và rollback.
7. [PostgreSQL — Row Security Policies](https://www.postgresql.org/docs/current/ddl-rowsecurity.html): RLS, ENABLE/FORCE, bypass, policy trên hàng.
8. [PostgreSQL — CREATE POLICY](https://www.postgresql.org/docs/current/sql-createpolicy.html): ngữ nghĩa `USING` và `WITH CHECK`.
9. [OWASP API Security — Broken Object Level Authorization](https://owasp.org/API-Security/editions/2023/en/0xa1-broken-object-level-authorization/): truy cập tài nguyên theo ID không đủ quyền.
10. [OWASP Cheat Sheet — Authorization](https://cheatsheetseries.owasp.org/cheatsheets/Authorization_Cheat_Sheet.html): deny by default, kiểm tra quyền cho mọi request và nguyên tắc đặc quyền tối thiểu.

**Kết luận:** cách ly tenant phải được thể hiện **trực tiếp trong repository và mọi truy vấn dữ liệu**. `tenant_id = :trustedTenant` chỉ có ý nghĩa nếu tenant được xác minh từ identity/membership phía server. Áp dụng điều kiện ấy cho `SELECT`, `Page`, `COUNT`, JOIN, `EXISTS`, `UPDATE`, `DELETE` và export; kết hợp thêm quyền chức năng, owner/ACL/state và ràng buộc version/transaction. Dùng integration tests với ít nhất hai tenants và, khi cần, PostgreSQL RLS để giảm rủi ro một query lỡ quên tenant.