# Giữ điều kiện phân quyền và phạm vi sở hữu trong mọi truy vấn JPA

Trong ứng dụng sử dụng Java Persistence API (JPA), việc xác thực người dùng chỉ trả lời câu hỏi **ai đang gửi yêu cầu**. Câu hỏi tiếp theo quan trọng hơn đối với dữ liệu: **người đó được phép đọc, cập nhật hoặc xóa chính xác những bản ghi nào?** Nếu một repository truy vấn theo ID nhưng quên kiểm tra tenant, chủ sở hữu hoặc quyền thành viên, ứng dụng có thể trả đúng entity về mặt kỹ thuật nhưng lại trả **sai dữ liệu về mặt bảo mật**.

Ví dụ, người dùng A gọi:

```http
GET /api/documents/9876
Authorization: Bearer <access-token>
```

Nếu service chỉ thực hiện:

```java
Document document = em.find(Document.class, 9876L);
```

thì JPA tìm theo primary key, **không tự biết** người gọi có quyền xem Document 9876 hay không. Việc đổi ID trong URL để xem tài liệu của người khác là một dạng **Broken Object Level Authorization (BOLA)**, còn gọi là **Insecure Direct Object Reference (IDOR)** trong nhiều tài liệu bảo mật.

Bài học thuộc chương **Bảo mật dữ liệu** của chủ đề **Data Persistence Relational Access ORM JPA**, với mục tiêu xây một quy tắc xuyên suốt:

> Mỗi truy vấn và thao tác ghi phải được ràng buộc bởi **phạm vi dữ liệu đáng tin cậy**: tenant, chủ sở hữu, quyền chia sẻ, quyền trên project, trạng thái bản ghi và các chính sách nghiệp vụ liên quan. Không có truy vấn nào được phép bỏ qua điều kiện bắt buộc chỉ vì nó nằm trong một method mới, dùng một API khác hoặc chạy trong tác vụ nền.

Phạm vi bài học gồm JPQL, Criteria API, Spring Data JPA, `find`/`getReference`, entity relationships, aggregate và pagination, count/exists, bulk UPDATE/DELETE, native SQL, caches, authorization cho write operations, database Row-Level Security (RLS), cách kiểm thử và vận hành.

---

## 1. Xác thực không đồng nghĩa phân quyền trên từng bản ghi

Giả sử hệ thống quản lý tài liệu của nhiều doanh nghiệp (tenant). Mỗi tài liệu có:

- `tenantId`: không gian dữ liệu của doanh nghiệp.
- `ownerId`: người tạo/chủ sở hữu trực tiếp.
- `projectId`: project chứa tài liệu.
- `deletedAt`: thời điểm soft delete, nếu có.
- `status`: trạng thái nghiệp vụ.
- `version`: phục vụ optimistic locking.

Một người dùng đăng nhập hợp lệ vẫn không nhất thiết được đọc mọi tài liệu trong cùng tenant.

### 1.1. Ba lớp điều kiện

| Lớp | Câu hỏi | Ví dụ |
|---|---|---|
| Authentication | Ai gửi request? | User 501 đã xác thực |
| Tenant isolation | Request thuộc không gian dữ liệu nào? | Tenant 42 |
| Object-level authorization | User có quyền với row này không? | Owner, project member hoặc tenant admin |

Cả ba cùng cần đúng. Một `@PreAuthorize("isAuthenticated()")` không thay predicate giới hạn row.

### 1.2. Chủ sở hữu và tenant là hai khái niệm khác nhau

Một user có thể sở hữu nhiều documents trong tenant; cũng có thể xem documents thuộc user khác nếu được chia sẻ. Ngược lại, một admin tenant chỉ được xem dữ liệu thuộc tenant mà họ có quyền quản trị, không tự có quyền với tất cả tenants.

### 1.3. Một row thường có nhiều điều kiện bắt buộc

Ví dụ:

```sql
WHERE d.tenant_id = :tenant_id
  AND d.deleted_at IS NULL
  AND (
       d.owner_id = :actor_id
       OR EXISTS (
            SELECT 1
            FROM project_membership m
            WHERE m.tenant_id = d.tenant_id
              AND m.project_id = d.project_id
              AND m.user_id = :actor_id
              AND m.active = TRUE
       )
  )
```

Trong ví dụ này, `tenant_id` và `deleted_at` là **ràng buộc bắt buộc**; các lựa chọn owner/project member được nhóm trong ngoặc để không vô tình mở rộng sang tenant khác.

---

## 2. Mô hình dữ liệu xuyên suốt bài học

Entity `Document`:

```java
package com.example.docs.domain;

import jakarta.persistence.*;
import java.time.Instant;

@Entity
@Table(
    name = "document",
    indexes = {
        @Index(
            name = "ix_document_tenant_owner",
            columnList = "tenant_id, owner_id"
        ),
        @Index(
            name = "ix_document_tenant_project",
            columnList = "tenant_id, project_id"
        )
    }
)
public class Document {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(
        name = "tenant_id",
        nullable = false,
        updatable = false
    )
    private Long tenantId;

    @Column(name = "owner_id", nullable = false)
    private Long ownerId;

    @Column(name = "project_id", nullable = false)
    private Long projectId;

    @Column(nullable = false, length = 250)
    private String title;

    @Column(name = "deleted_at")
    private Instant deletedAt;

    @Version
    private long version;

    protected Document() {}

    public Long getId() { return id; }
    public Long getTenantId() { return tenantId; }
    public Long getOwnerId() { return ownerId; }
    public Long getProjectId() { return projectId; }
    public String getTitle() { return title; }
    public Instant getDeletedAt() { return deletedAt; }

    public void rename(String newTitle) {
        if (newTitle == null || newTitle.isBlank()) {
            throw new IllegalArgumentException(
                "Document title is required"
            );
        }
        this.title = newTitle.strip();
    }

    public void softDelete(Instant now) {
        if (deletedAt == null) {
            deletedAt = now;
        }
    }
}
```

Entity membership:

```java
@Entity
@Table(
    name = "project_membership",
    uniqueConstraints = @UniqueConstraint(
        name = "uk_project_member",
        columnNames = {
            "tenant_id", "project_id", "user_id"
        }
    )
)
public class ProjectMembership {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(name = "tenant_id", nullable = false)
    private Long tenantId;

    @Column(name = "project_id", nullable = false)
    private Long projectId;

    @Column(name = "user_id", nullable = false)
    private Long userId;

    @Column(nullable = false)
    private boolean active;

    @Enumerated(EnumType.STRING)
    @Column(nullable = false)
    private ProjectRole role;

    protected ProjectMembership() {}
}

public enum ProjectRole {
    VIEWER, EDITOR, ADMIN
}
```

Ví dụ sử dụng cột `projectId` dạng scalar để tập trung vào security predicates. Một ứng dụng khác có thể dùng `@ManyToOne Project project`; **việc ánh xạ association không tự bảo đảm tenant của hai entity trùng nhau**.

### 2.1. Không tạo entity mà thiếu tenant trong write path

Tenant ID phải được service gán từ authenticated context. Không dùng một tenant ID bất kỳ do client cung cấp mà chưa xác minh.

### 2.2. Owner không nên tùy tiện đổi

Chuyển quyền sở hữu cần một command riêng, policy và audit. Không cho request DTO tự bind vào entity và tùy ý ghi `ownerId`.

---

## 3. AccessScope là dữ liệu từ nguồn đáng tin

Một cấu trúc truyền xuống repository:

```java
public record AccessScope(
    long tenantId,
    long actorId,
    boolean tenantAdmin
) {
    public AccessScope {
        if (tenantId <= 0 || actorId <= 0) {
            throw new IllegalArgumentException(
                "Invalid access scope"
            );
        }
    }
}
```

`AccessScope` phải được tạo tại security boundary từ principal đã xác thực và authorization service đáng tin.

### 3.1. Sai: Lấy phạm vi trực tiếp từ query string

```java
@GetMapping("/documents")
public List<Document> list(
        @RequestParam long tenantId,
        @RequestParam long ownerId) {

    return repository.findByTenantAndOwner(
        tenantId, ownerId
    );
}
```

Nếu không kiểm chứng, caller chỉ cần đổi parameters để xem dữ liệu của người khác.

### 3.2. Hướng đúng

Controller/service dựng scope từ authenticated principal:

```java
AccessScope scope =
    accessScopeResolver.fromAuthenticatedPrincipal();
```

Sau đó:

```java
documentService.listVisible(scope, filter);
```

Resolver phải kiểm tra active tenant, membership, quyền quản trị và account status theo hệ thống thực tế. Bài viết không giả định mọi JWT claim có thể được tin vô điều kiện sau khi xác minh chữ ký; việc xử lý tenant switching, revocation và policy freshness cần được thiết kế.

### 3.3. Tenant-admin là vai trò có phạm vi

`tenantAdmin = true` phải nghĩa là **admin của `scope.tenantId`**, không phải một boolean “superuser xem mọi tenant”. Predicate `tenantId = :tenantId` vẫn luôn có mặt.

---

## 4. Định nghĩa hợp đồng phân quyền của Document

Ví dụ một chính sách đọc:

> Trong tenant T, user U xem được Document D khi D chưa bị xóa, và U là owner của D, hoặc U là active member của project chứa D, hoặc U là admin của tenant T.

Viết bằng logic:

```text
canRead(D, S)
    = (D.tenantId = S.tenantId)
    AND (D.deletedAt IS NULL)
    AND (
         D.ownerId = S.actorId
         OR activeProjectMember(D.projectId, S.actorId, S.tenantId)
         OR S.tenantAdmin
    )
```

Một chính sách ghi có thể chặt hơn:

```text
canEdit(D, S)
    = sameTenant(D, S)
    AND notDeleted(D)
    AND (
         owner(D, S)
         OR projectEditorOrAdmin(D, S)
         OR tenantAdmin(S)
    )
```

### 4.1. Quyền đọc không tự suy ra quyền sửa

Một project member với role `VIEWER` có thể xem nhưng không được `rename`/soft delete. Nếu repository chỉ dùng một predicate `visibleTo` cho tất cả operations, write path có thể mở quyền quá mức.

### 4.2. Policy phải được đặt tên theo hành động

Các phương thức như `findReadableById`, `findEditableById`, `countReadable`, `softDeleteEditable` dễ review hơn một generic `findByIdAndTenant` được caller tự hiểu là đã phân quyền.

### 4.3. Mặc định từ chối

Nếu thiếu scope, role chưa xác minh, membership không tồn tại hoặc status không được phép, kết quả phải là **không cấp quyền**. Tránh fallback sang query toàn bộ dữ liệu.

---

## 5. Sai lầm: Chỉ kiểm tra tại controller

Ví dụ:

```java
@PreAuthorize("isAuthenticated()")
@GetMapping("/documents/{id}")
public DocumentDto get(@PathVariable long id) {
    return mapper.toDto(repository.findById(id));
}
```

Đây là authentication gate, không phải row-level authorization.

### 5.1. “Đã đăng nhập” chưa đủ

Một user có thể đổi ID thành document của người khác và vẫn vượt qua `isAuthenticated()`.

### 5.2. Endpoint mới thường quên check cũ

Một `GET /documents/{id}/download`, export worker hoặc endpoint dùng `POST /search` có thể gọi repository trực tiếp. Nếu security chỉ nằm ở một controller method, đường mới dễ bypass.

### 5.3. Tầng bảo vệ bền vững

- Security layer xác minh principal và active tenant.
- Application service định nghĩa action-specific policy.
- Repository áp security predicates **trong query**.
- Database constraints/RLS hỗ trợ defense in depth khi khả thi.
- Tests xác nhận cả positive và negative access.

Không có một annotation tự động thay thế mọi lớp.

---

## 6. JPQL: Tra cứu một Document theo ID với điều kiện sở hữu

Nếu policy chỉ cho owner đọc:

```java
public Optional<Document> findOwnedDocument(
        long documentId,
        AccessScope scope) {

    List<Document> results = em.createQuery(
            """
            SELECT d FROM Document d
            WHERE d.id = :documentId
              AND d.tenantId = :tenantId
              AND d.ownerId = :actorId
              AND d.deletedAt IS NULL
            """,
            Document.class
        )
        .setParameter("documentId", documentId)
        .setParameter("tenantId", scope.tenantId())
        .setParameter("actorId", scope.actorId())
        .getResultList();

    return results.stream().findFirst();
}
```

Không có result được diễn đạt là `Optional.empty()`, tránh làm lộ liệu ID đó có tồn tại trong tenant khác hay không.

### 6.1. Không tra ID không scope rồi mới kiểm tra

Sai:

```java
Document document = em.find(Document.class, id);
assertCanRead(document, scope);
```

Việc tải row vượt scope có thể đưa dữ liệu trái quyền vào persistence context, metrics, logging, entity listeners hoặc mapping code trước khi check hoàn tất. Với simple read, predicate scoped ngay trong DB an toàn và tiết kiệm hơn.

### 6.2. Không bỏ `tenantId` vì đã check owner

Một owner ID có thể chỉ unique trong một tenant, hoặc user có nhiều tenant. Điều kiện tenant vẫn là policy boundary độc lập.

### 6.3. Không bỏ `deletedAt IS NULL`

Soft-deleted document có thể không được phép truy cập qua API bình thường, kể cả người dùng còn là owner.

---

## 7. JPQL: Đọc theo owner hoặc membership

Khi project member cũng được đọc:

```java
public Optional<Document> findReadableById(
        long documentId,
        AccessScope scope) {

    String jpql = """
        SELECT d FROM Document d
        WHERE d.id = :documentId
          AND d.tenantId = :tenantId
          AND d.deletedAt IS NULL
          AND (
               d.ownerId = :actorId
               OR EXISTS (
                    SELECT m.id
                    FROM ProjectMembership m
                    WHERE m.tenantId = d.tenantId
                      AND m.projectId = d.projectId
                      AND m.userId = :actorId
                      AND m.active = true
               )
               OR :tenantAdmin = true
          )
        """;

    List<Document> results = em.createQuery(
            jpql, Document.class
        )
        .setParameter("documentId", documentId)
        .setParameter("tenantId", scope.tenantId())
        .setParameter("actorId", scope.actorId())
        .setParameter(
            "tenantAdmin",
            scope.tenantAdmin()
        )
        .getResultList();

    return results.stream().findFirst();
}
```

### 7.1. Parenthesize OR predicates

Trong JPQL, `AND` có độ ưu tiên khác `OR`. Các dấu ngoặc ở trên bảo đảm:

```text
tenant AND notDeleted AND (owner OR member OR admin)
```

thay vì một biểu thức có nhánh membership/admin vượt ra khỏi tenant check.

### 7.2. EXISTS tránh nhân kết quả

Một project có thể có nhiều memberships hoặc role records. `EXISTS` diễn đạt “có ít nhất một membership hợp lệ”, thường dễ kiểm soát cardinality hơn `JOIN` vào ACL table rồi lọc.

### 7.3. Correlate tenant của membership và document

Chỉ kiểm tra `m.projectId = d.projectId` có thể sai nếu project IDs không globally unique hoặc dữ liệu cross-tenant bất thường. Cùng tenant phải được bảo đảm ở cả query và database model.

### 7.4. Admin vẫn có tenant scope

Nhánh `OR :tenantAdmin = true` chỉ nằm trong nhóm action permission, bên ngoài vẫn bắt buộc `d.tenantId = :tenantId`.

---

## 8. Lỗi dấu ngoặc AND/OR tạo lỗ hổng dữ liệu

Sai:

```sql
WHERE d.tenant_id = :tenantId
  AND d.owner_id = :actorId
   OR d.visibility = 'PUBLIC'
```

Logic thực tế:

```text
(tenant match AND owner match)
OR public document ở bất kỳ tenant nào
```

Nếu `PUBLIC` chỉ có nghĩa “công khai trong tenant”, query đã sai.

Đúng:

```sql
WHERE d.tenant_id = :tenantId
  AND (
       d.owner_id = :actorId
       OR d.visibility = 'PUBLIC'
  )
```

### 8.1. Đừng thêm một OR cuối câu mà quên security predicate

Một filter keyword như `(title LIKE ... OR body LIKE ...)` cần được bọc trong cùng một nhóm, rồi `AND` với mandatory scope.

### 8.2. Test riêng từng nhánh OR

Một query có nhiều đường cấp quyền phải được test từng nhánh owner, member, admin, public, và cả cases cross-tenant với branch tương tự.

### 8.3. Security invariant là phép AND bên ngoài

Tư duy an toàn:

```text
mandatoryScope AND (allowedWaysToAccess) AND optionalFilters
```

Không để một optional filter hoặc role branch vô tình OR với toàn bộ mandatoryScope.

---

## 9. Tìm kiếm động: Không được để filter người dùng thay security scope

Ví dụ API nhận:

```json
{
  "keyword": "contract",
  "status": "DRAFT",
  "ownerId": 999
}
```

`ownerId` nếu là filter nghiệp vụ **không được** thay `scope.actorId()` hoặc `scope.tenantId()`.

### 9.1. Hai loại predicate

| Loại | Nguồn | Có được bỏ qua? |
|---|---|---|
| Mandatory authorization predicate | Server-side authenticated scope + ACL | Không |
| Optional business predicate | Request filter đã validate | Có, theo yêu cầu tìm kiếm |
| Sorting/pagination | Request, đã allowlist/cap | Có, không thay scope |
| Soft-delete/status policy | Business/security policy | Chỉ thay theo action được phép |

### 9.2. Không sửa AccessScope từ request DTO

Sai:

```java
AccessScope scope = new AccessScope(
    request.tenantId(),
    request.ownerId(),
    request.isAdmin()
);
```

Những fields đó có thể do client tự chọn. Dùng resolver từ trusted security context; những fields trong request chỉ là filters trong phạm vi đã được phép.

### 9.3. Optional owner filter phải nằm sau authorization

Ví dụ muốn xem documents của user 999, caller chỉ được thấy những documents mà chính caller có quyền đọc; việc filter theo 999 không cấp thêm quyền.

---

## 10. Criteria API: Tách predicate bắt buộc thành một hàm

Với JPA Criteria, có thể xây policy theo typed `Predicate`.

```java
public final class DocumentSecurityPredicates {

    private DocumentSecurityPredicates() {}

    public static Predicate readable(
            CriteriaBuilder cb,
            CriteriaQuery<?> query,
            Root<Document> document,
            AccessScope scope) {

        Subquery<Long> membership =
            query.subquery(Long.class);

        Root<ProjectMembership> member =
            membership.from(ProjectMembership.class);

        membership.select(member.get("id"))
            .where(
                cb.equal(
                    member.get("tenantId"),
                    document.get("tenantId")
                ),
                cb.equal(
                    member.get("projectId"),
                    document.get("projectId")
                ),
                cb.equal(
                    member.get("userId"),
                    scope.actorId()
                ),
                cb.isTrue(member.get("active"))
            );

        Predicate tenant = cb.equal(
            document.get("tenantId"),
            scope.tenantId()
        );

        Predicate notDeleted = cb.isNull(
            document.get("deletedAt")
        );

        Predicate allowed;

        if (scope.tenantAdmin()) {
            allowed = cb.conjunction();
        } else {
            allowed = cb.or(
                cb.equal(
                    document.get("ownerId"),
                    scope.actorId()
                ),
                cb.exists(membership)
            );
        }

        return cb.and(
            tenant,
            notDeleted,
            allowed
        );
    }
}
```

### 10.1. Tại sao dùng `cb.and` bên ngoài?

Để điều kiện tenant và not-deleted luôn được giữ, bất kể policy phía trong cấp quyền theo owner/membership/admin.

### 10.2. `cb.conjunction()` là true predicate

Trong nhánh verified tenant admin, action permission là true nhưng vẫn giữ tenant/soft-delete predicates. Không thay toàn bộ security predicate bằng `cb.conjunction()`.

### 10.3. `Subquery` dùng root của truy vấn hiện tại

Không tạo Predicate/Root một lần rồi cố dùng lại giữa hai CriteriaQueries khác nhau; chúng gắn với query tree tương ứng.

### 10.4. Tên và mối liên hệ policy phải rõ

`readable()` không nên được dùng cho delete/update nếu edit permission khác read permission. Hãy có `editable()` riêng.

---

## 11. Criteria API: Search với security và optional filters

Ví dụ search title:

```java
public List<Document> searchReadable(
        AccessScope scope,
        String keyword,
        int limit) {

    CriteriaBuilder cb = em.getCriteriaBuilder();

    CriteriaQuery<Document> cq =
        cb.createQuery(Document.class);

    Root<Document> d = cq.from(Document.class);

    Predicate security =
        DocumentSecurityPredicates.readable(
            cb, cq, d, scope
        );

    List<Predicate> all = new ArrayList<>();
    all.add(security);

    if (keyword != null && !keyword.isBlank()) {
        String escaped = escapeLike(
            keyword.strip().toLowerCase(Locale.ROOT)
        );

        all.add(
            cb.like(
                cb.lower(d.get("title")),
                "%" + escaped + "%",
                '\\'
            )
        );
    }

    cq.select(d)
      .where(all.toArray(Predicate[]::new))
      .orderBy(
          cb.desc(d.get("id"))
      );

    return em.createQuery(cq)
        .setMaxResults(Math.min(
            Math.max(limit, 1), 100
        ))
        .getResultList();
}
```

Một helper minh họa để escape `%`, `_` và `\` của SQL LIKE:

```java
private static String escapeLike(String raw) {
    return raw
        .replace("\\", "\\\\")
        .replace("%", "\\%")
        .replace("_", "\\_");
}
```

Cú pháp escape thực tế có thể cần kiểm tra với dialect/provider và collation. Đây chỉ là một filter keyword: quan trọng là **security luôn được thêm trước optional business predicates**, không phụ thuộc request có keyword hay không.

### 11.1. Không dùng `where()` hai lần để cộng dồn

Sai:

```java
cq.where(security);
cq.where(keywordPredicate); // Ghi đè restriction cũ.
```

`CriteriaQuery.where(...)` thiết lập restrictions cho query; lần gọi sau có thể thay restriction trước. Đúng là gom tất cả vào một `cb.and(...)`/một lần `where(...)`.

### 11.2. Optional filter không được biến thành OR ngoài cùng

Sai:

```java
cq.where(cb.or(security, keywordPredicate));
```

Query sẽ trả row khớp keyword **dù không được cấp quyền**, nếu keywordPredicate true.

### 11.3. Giới hạn paging

Kể cả query đã an toàn, unbounded result set có thể gây DoS hoặc leak volumes quá lớn. Kiểm soát max page size và các trường được sort/filter.

---

## 12. Spring Data JPA Specification: Chỉ mở rộng trong scope

Với `JpaSpecificationExecutor<Document>`, có thể định nghĩa một Specification cho phạm vi mandatory.

```java
public final class DocumentSpecs {

    private DocumentSpecs() {}

    public static Specification<Document> ownedInTenant(
            AccessScope scope) {

        return (root, query, cb) -> cb.and(
            cb.equal(
                root.get("tenantId"),
                scope.tenantId()
            ),
            cb.equal(
                root.get("ownerId"),
                scope.actorId()
            ),
            cb.isNull(
                root.get("deletedAt")
            )
        );
    }

    public static Specification<Document> titleContains(
            String keyword) {

        return (root, query, cb) -> {
            if (keyword == null || keyword.isBlank()) {
                return cb.conjunction();
            }

            return cb.like(
                cb.lower(root.get("title")),
                "%" + keyword.toLowerCase(Locale.ROOT) + "%"
            );
        };
    }
}
```

Sử dụng:

```java
Specification<Document> spec =
    Specification.where(
        DocumentSpecs.ownedInTenant(scope)
    ).and(
        DocumentSpecs.titleContains(keyword)
    );

Page<Document> page =
    documentRepository.findAll(
        spec,
        pageable
    );
```

**Lưu ý:** Các API cách tạo/combine `Specification` và khả năng nullable specifications có khác biệt theo Spring Data JPA version. Ví dụ diễn đạt mô hình kết hợp; cần dùng API có mặt trong project thực tế.

### 12.1. Specification không tự là một security boundary

Nếu repository vẫn public `findAll()`, `findById()` hoặc `findAll(otherSpec)`, một developer có thể bỏ quên scope. An toàn hơn khi service chỉ expose các methods có policy bắt buộc và không đưa raw repository trực tiếp cho controller.

### 12.2. Không cho caller truyền một Specification thay thế security

Thiết kế:

```java
findAll(userProvidedSpec)
```

không an toàn nếu caller có thể tùy chọn bỏ mandatory spec. Security phải do server compose từ verified scope.

### 12.3. `and` khác `or`

Dùng:

```text
securitySpec AND businessFilterSpec
```

Không dùng:

```text
securitySpec OR businessFilterSpec
```

### 12.4. Query count cũng phải scoped

Spring Data có thể tạo count query phục vụ pagination. Cần kiểm tra mọi overload/custom count specification đều giữ mandatory tenant/owner conditions; không chỉ data query.

---

## 13. Đóng gói repository để giảm nguy cơ quên scope

Một interface được thiết kế theo use case:

```java
public interface DocumentAccessRepository {

    Optional<Document> findReadableById(
        long documentId,
        AccessScope scope
    );

    Optional<Document> findEditableById(
        long documentId,
        AccessScope scope
    );

    Page<Document> searchReadable(
        AccessScope scope,
        DocumentSearchFilter filter,
        Pageable pageable
    );

    long countReadable(
        AccessScope scope,
        DocumentSearchFilter filter
    );
}
```

### 13.1. API bắt scope từ caller đáng tin

Methods yêu cầu `AccessScope`, không có `findAllDocumentsForEveryone()` được expose rộng rãi.

### 13.2. Không phải lúc nào cũng cần tự viết toàn bộ JPA repository

Spring Data repository có thể là implementation detail phía trong adapter. Application service chỉ được gọi abstraction có policy; quyền truy cập raw `EntityManager`/`JpaRepository` nên bị giới hạn về kiến trúc và code review.

### 13.3. Method name phải phản ánh action

`findReadableById` và `findEditableById` khác nhau dù cùng sử dụng `Document` entity.

### 13.4. Không tin method name nếu implementation thiếu predicate

Tên có chữ `Secure` hoặc `Authorized` không tự bảo đảm SQL đúng. Integration tests và query inspection vẫn cần thiết.

---

## 14. findById và EntityManager.find không tự lọc theo owner

```java
Document document =
    em.find(Document.class, documentId);
```

JPA `find` dựa trên entity primary key. Nếu business policy đòi `tenantId`/owner, method này **không tự thêm điều kiện** theo chuẩn JPA.

### 14.1. Không lấy authorization từ primary key

Một ID tăng dần hoặc UUID chỉ là identifier. ID càng khó đoán có thể giảm khả năng enumeration nhưng không thay kiểm tra quyền.

### 14.2. Khi nào find vẫn có thể được dùng?

Nếu application đã có một security layer khác được chứng minh bảo đảm object authorization trước operation, hoặc database RLS ngăn row không được phép, `find` có thể phù hợp trong một số design. Nhưng phải hiểu cache, tenant scope và transaction boundaries; không mặc định `find` là secure.

### 14.3. `getReference` không cấp quyền

```java
Document ref =
    em.getReference(Document.class, documentId);
```

Reference/proxy có thể chưa query database ngay. Việc có một reference không xác nhận entity tồn tại hay caller được phép dùng nó.

### 14.4. Tốt hơn: query scoped theo ID

```java
SELECT d FROM Document d
WHERE d.id = :id
  AND d.tenantId = :tenantId
  AND d.ownerId = :actorId
  AND d.deletedAt IS NULL
```

Nếu không có row, trả kết quả không tìm thấy trong scope mà không tiết lộ có một document ở nơi khác hay không.

---

## 15. `exists` và `count` cũng là truy vấn dữ liệu nhạy cảm

Một API:

```http
GET /documents/9876/exists
```

có thể làm lộ liệu document của người khác có tồn tại hay không.

Sai:

```java
boolean exists = repository.existsById(id);
```

nếu API cần existence **trong phạm vi caller**.

Đúng về nguyên tắc:

```java
Long count = em.createQuery(
        """
        SELECT COUNT(d)
        FROM Document d
        WHERE d.id = :id
          AND d.tenantId = :tenantId
          AND d.ownerId = :actorId
          AND d.deletedAt IS NULL
        """,
        Long.class
    )
    .setParameter("id", id)
    .setParameter("tenantId", scope.tenantId())
    .setParameter("actorId", scope.actorId())
    .getSingleResult();

boolean visible = count > 0;
```

### 15.1. Count có thể leak thông tin tổng hợp

Trả “tenant có 25.000 documents” cho member chỉ được xem 30 documents là một dạng information disclosure dù không trả raw rows.

### 15.2. Data query và count query phải dùng cùng scope

Nếu danh sách trả 20 documents nhưng `totalElements` đếm 1 triệu toàn hệ thống, API đã lộ dữ liệu. Chênh lệch cũng khiến pagination không chính xác.

### 15.3. Không dùng unscoped exists để quyết định HTTP 403/404 tùy tiện

Tra existence ngoài quyền có thể tạo observable difference. Chính sách nên quyết định khi nào che resource existence; nhiều APIs trả 404 cho ID ngoài scope.

---

## 16. Pagination: Phải lọc quyền trước khi phân trang

Sai về thứ tự xử lý:

```java
List<Document> all =
    repository.findAll(pageable).getContent();

return all.stream()
    .filter(d -> canRead(d, scope))
    .toList();
```

### 16.1. Vì sao lọc sau khi page sai?

- Đã đọc dữ liệu không được phép vào memory.
- Page có thể chỉ còn 2 items dù còn nhiều documents hợp lệ ở page sau.
- Tổng số rows/count có thể tiết lộ tài liệu ngoài quyền.
- Sorting/relevance có thể bị ảnh hưởng bởi documents bị loại.
- Latency tăng và các entity listeners/lazy loads có thể nhìn thấy dữ liệu ngoài phạm vi.

### 16.2. Đúng: Scope trong WHERE rồi LIMIT/OFFSET

```sql
SELECT d.*
FROM document d
WHERE d.tenant_id = :tenant_id
  AND d.owner_id = :actor_id
  AND d.deleted_at IS NULL
ORDER BY d.id DESC
LIMIT :limit OFFSET :offset;
```

### 16.3. Keyset pagination cũng phải scoped

```sql
WHERE d.tenant_id = :tenant_id
  AND d.owner_id = :actor_id
  AND d.deleted_at IS NULL
  AND d.id < :cursor_id
ORDER BY d.id DESC
LIMIT :limit;
```

Cursor chứa ID không biến thành quyền; mọi page tiếp tục phải có mandatory scope.

### 16.4. Sort allowlist

Không cho user sort theo arbitrary entity path như `owner.passwordHash`, `internalRiskScore` hoặc unauthorized relationship. Sort field phải được cho phép theo API contract và quyền.

---

## 17. Project memberships, sharing và quyền theo vai trò

Trong bài, quyền đọc là owner **hoặc** active project member. Quyền sửa có thể cần editor/admin:

```java
String jpql = """
    SELECT d FROM Document d
    WHERE d.id = :id
      AND d.tenantId = :tenantId
      AND d.deletedAt IS NULL
      AND (
           d.ownerId = :actorId
           OR EXISTS (
               SELECT m.id
               FROM ProjectMembership m
               WHERE m.tenantId = d.tenantId
                 AND m.projectId = d.projectId
                 AND m.userId = :actorId
                 AND m.active = true
                 AND m.role IN :roles
           )
           OR :tenantAdmin = true
      )
    """;
```

Parameter:

```java
.setParameter(
    "roles",
    List.of(ProjectRole.EDITOR, ProjectRole.ADMIN)
)
```

### 17.1. Read và write roles khác nhau

`VIEWER` không nên được dùng để thay owner cho một UPDATE. Đừng tái sử dụng một method `findVisible` rồi mặc định mọi visible entity đều mutable.

### 17.2. Membership có thể hết hiệu lực

Một active flag, expiry time hoặc revocation version phải nằm trong policy theo design. Query chỉ kiểm tra `m.active=true` nếu application đã định nghĩa trạng thái này có nghĩa là quyền còn hiệu lực.

### 17.3. Project membership và tenant ID

Membership của Project thuộc tenant khác không được phép cấp quyền cho Document hiện tại. Tương quan `m.tenantId = d.tenantId` là rào bảo vệ quan trọng.

### 17.4. Tenant-admin đặc biệt

Admin role chỉ được chấp nhận sau verification ở server; không tin một boolean gửi từ client.

---

## 18. Group sharing và ACL nhiều nguồn

Một hệ thống lớn có thể cho quyền qua:

- Trực tiếp owner.
- Project membership.
- Team/group membership.
- Direct user share grants.
- Organization unit.
- Tenant admin.
- Resource classification/visibility policy.
- Time-limited access grants.

Hợp đồng có thể là:

```text
sameTenant
AND notDeleted
AND resourceClassificationAllowed
AND (
    owner
    OR projectMember
    OR directShare
    OR groupShare
    OR tenantAdmin
)
```

### 18.1. Không ghép các nguồn grant bằng OR ngoài tenant scope

Mỗi nhánh grant chỉ mở quyền **bên trong** tenant và trạng thái của resource phù hợp.

### 18.2. Đừng chỉ kiểm tra role name

Role như `ADMIN` phải đi kèm scope của role. User là ADMIN project X không tự được sửa document ở project Y.

### 18.3. Deny rules có độ ưu tiên riêng

Nếu hệ thống có explicit deny, legal hold hoặc restricted classification, policy có thể cần `AND NOT denied`. Một OR grant chung không đủ để biểu diễn priority của deny.

### 18.4. ACL động ảnh hưởng query complexity

Nhiều `EXISTS` clauses có thể tốn CPU/index work. Có thể tối ưu qua indexes, materialized permission views hoặc authorized resource sets, nhưng phải có cơ chế invalidation khi ACL đổi.

---

## 19. Search projection/DTO cũng phải scoped

Không phải chỉ entity query mới nhạy cảm. Một DTO projection vẫn có thể lộ titles, metadata hoặc owner identities:

```java
public record DocumentSummary(
    Long id,
    String title,
    Long ownerId
) {}
```

JPQL:

```java
List<DocumentSummary> summaries =
    em.createQuery(
        """
        SELECT new com.example.docs.api.DocumentSummary(
            d.id, d.title, d.ownerId
        )
        FROM Document d
        WHERE d.tenantId = :tenantId
          AND d.deletedAt IS NULL
          AND d.ownerId = :actorId
        ORDER BY d.id DESC
        """,
        DocumentSummary.class
    )
    .setParameter("tenantId", scope.tenantId())
    .setParameter("actorId", scope.actorId())
    .getResultList();
```

### 19.1. DTO không phải cơ chế cấp quyền

Chỉ trả ít fields hơn có thể giảm lộ dữ liệu, nhưng không sửa lỗi truy vấn row ngoài quyền.

### 19.2. Aggregate projections cũng phải scoped

`SELECT d.status, COUNT(d)` phải áp đúng tenant/ACL predicates trước GROUP BY, nếu không thống kê có thể tiết lộ dữ liệu người khác.

### 19.3. Query streams cũng phải scoped

`getResultStream()` không biến một query thiếu WHERE thành an toàn. Stream còn có vấn đề resource lifecycle trong transaction.

---

## 20. JOIN associations có thể làm rò rỉ dữ liệu bên liên quan

Giả sử Document có association:

```java
@ManyToOne(fetch = FetchType.LAZY)
private Project project;
```

Một query:

```java
SELECT d FROM Document d
JOIN FETCH d.project
WHERE d.tenantId = :tenantId
```

chỉ scope Document tenant, nhưng project association có thể trỏ sai tenant nếu database không bảo vệ relationship integrity. Khi serialize DTO, thông tin Project khác tenant có thể bị lộ.

### 20.1. Cross-tenant relationship cần bảo vệ ở write path

Khi gán `Document.project`, service phải xác minh Project thuộc đúng tenant. Không dùng:

```java
em.getReference(Project.class, request.projectId());
```

mà không xác thực tenant và quyền tương ứng.

### 20.2. FK không mặc định ràng buộc tenant

Foreign key `document.project_id REFERENCES project(id)` bảo vệ project ID tồn tại, **không tự yêu cầu** `document.tenant_id = project.tenant_id`.

### 20.3. Composite foreign key là defense in depth

Ở DB hỗ trợ:

```sql
ALTER TABLE project
ADD CONSTRAINT uk_project_tenant_id
UNIQUE (tenant_id, id);

ALTER TABLE document
ADD CONSTRAINT fk_document_project_tenant
FOREIGN KEY (tenant_id, project_id)
REFERENCES project (tenant_id, id);
```

Điều này chống Document tham chiếu Project của tenant khác khi các cột map đúng, bổ sung cho service authorization.

### 20.4. FK chỉ xác nhận consistency, không xác nhận permission

Project cùng tenant chưa chắc user có quyền tạo Document trong Project đó. Cần kiểm tra membership/role riêng.

---

## 21. Lazy loading không tự chạy lại policy của endpoint

Một entity đã được load có thể chứa lazy associations. Khi gọi:

```java
document.getComments().size();
```

provider có thể thực hiện query bổ sung để load Comments. Đừng mặc định mỗi lazy load đều áp lại object-level authorization theo cùng policy ban đầu.

### 21.1. Parent visible không đồng nghĩa mọi children visible

Một Comment có thể có visibility riêng, moderation status, private attachment hoặc author-only flag. Hợp đồng của `Document.comments` phải định nghĩa liệu tất cả comments có thuộc cùng scope hay cần filter riêng.

### 21.2. DTO hoặc repository query cho children

Thay vì serialize entity graph tùy ý, query:

```sql
WHERE comment.document_id = :document_id
  AND comment.tenant_id = :tenant_id
  AND ...child-specific access conditions...
```

### 21.3. Open Session in View không là security control

Giữ persistence context mở trong view có thể cho phép lazy loading trong serialization, nhưng không bảo đảm authorization cho mọi association và có thể dẫn đến query ngoài dự kiến.

### 21.4. Avoid leaking through debug/toString

Entity `toString()` hoặc log serialization tự truy cập lazy associations có thể đưa dữ liệu ngoài scope vào logs. Giới hạn logged fields, tránh tự động duyệt graphs.

---

## 22. Cập nhật bản ghi: Kiểm tra quyền trong transaction ghi

Một service:

```java
@Service
public class DocumentCommandService {

    private final DocumentAccessRepository repository;

    public DocumentCommandService(
            DocumentAccessRepository repository) {
        this.repository = repository;
    }

    @Transactional
    public void rename(
            long documentId,
            String title,
            AccessScope scope) {

        Document document =
            repository.findEditableById(documentId, scope)
                .orElseThrow(
                    () -> new DocumentNotFoundException()
                );

        document.rename(title);
    }
}
```

`findEditableById` phải áp **write authorization predicate**, không chỉ tenant.

### 22.1. Đừng để caller tải Document bằng unscoped findById

Một controller không nên được phép thay đổi managed entity tùy ý rồi trông chờ service sau đó chặn. Write path nên sở hữu toàn bộ transaction và permission checks.

### 22.2. Chuyển owner là một command riêng

Nếu business cho phép transfer ownership:

```text
canTransferOwner = owner/admin policy + target user in tenant
```

Không cho generic `PATCH /documents/{id}` tự bind `ownerId` từ payload.

### 22.3. Soft delete vẫn là write operation

Một user được đọc Document không mặc định có quyền soft-delete nó. Cần `findDeletableById`/`canDelete` với policy riêng.

---

## 23. Race condition khi quyền bị thu hồi

Timeline:

```text
Tx A                              Tx B
--------------------------------  ------------------------------
A kiểm tra user còn EDITOR
                                  Admin thu hồi membership
                                  COMMIT
A sửa Document
A COMMIT
```

Tùy transaction isolation, locking và policy, A có thể commit sau khi quyền đã bị thu hồi.

### 23.1. Cần định nghĩa semantics của revocation

- Quyền chỉ cần hợp lệ **ở thời điểm command bắt đầu**?
- Hay phải còn hiệu lực **tại thời điểm ghi/commit**?
- Có yêu cầu thu hồi gần tức thì?
- Có external systems nhận cached grants?

Không thể bảo đảm mọi semantics chỉ bằng một `SELECT` trước `UPDATE`.

### 23.2. Các biện pháp tùy yêu cầu

- Lock row membership và/or document trong transaction.
- Conditional DML có authorization predicates trong cùng statement.
- Optimistic policy version hoặc grant version.
- Serializable isolation/DB RLS tùy workload.
- Revocation events để invalidate permission caches.
- Chấp nhận một bounded revocation propagation window nếu được policy cho phép.

### 23.3. @Version chỉ bảo vệ entity version

`@Version` trên Document phát hiện concurrent writes lên Document, nhưng không tự phát hiện membership bị thu hồi ở bảng khác.

---

## 24. Bulk UPDATE là điểm bỏ sót phân quyền phổ biến

JPQL bulk DML:

```java
int changed = em.createQuery(
        """
        UPDATE Document d
        SET d.deletedAt = :now
        WHERE d.tenantId = :tenantId
          AND d.ownerId = :actorId
          AND d.deletedAt IS NULL
          AND d.id IN :ids
        """
    )
    .setParameter("now", Instant.now())
    .setParameter("tenantId", scope.tenantId())
    .setParameter("actorId", scope.actorId())
    .setParameter("ids", ids)
    .executeUpdate();
```

Đây là **owner-only soft delete** minh họa, không áp policy editor membership. Nếu command cho phép editor xóa, cần predicate tương ứng; không dùng owner-only query rồi giả định đã triển khai toàn bộ business policy.

### 24.1. Mandatory predicates phải nằm trực tiếp trong bulk WHERE

Sai:

```java
UPDATE Document d
SET d.deletedAt = :now
WHERE d.id IN :ids
```

Caller có thể đưa IDs của tenant/owner khác. Một lần gọi có thể ảnh hưởng hàng loạt rows ngoài quyền.

### 24.2. Bulk DML bỏ qua per-entity lifecycle

JPQL bulk update/delete không đi qua các entity callbacks/dirty checking theo từng managed entity như mutation thông thường. Đừng dựa vào `@PreUpdate`, `@PreRemove` hoặc `@Version` mặc định để đảm bảo authorization/optimistic lock cho bulk DML.

### 24.3. Persistence context có thể stale

Bulk update không tự đồng bộ các managed entity instances đang nằm trong persistence context. Cần thiết kế flush/clear hoặc scope riêng, tránh đọc lại dữ liệu stale.

### 24.4. Kiểm soát affected row count

`executeUpdate()` trả số rows/entities bị ảnh hưởng theo provider semantics. Nếu client yêu cầu xóa 5 documents nhưng chỉ 3 rows đủ quyền, phải định nghĩa contract: partial success, all-or-nothing hoặc `404/403`. Không silently báo đã xóa cả 5.

---

## 25. Bulk DELETE có cùng rủi ro

Sai:

```java
em.createQuery(
    "DELETE FROM Document d WHERE d.id IN :ids"
).setParameter("ids", ids)
 .executeUpdate();
```

Đúng hơn cho owner-only policy:

```java
em.createQuery(
    """
    DELETE FROM Document d
    WHERE d.tenantId = :tenantId
      AND d.ownerId = :actorId
      AND d.id IN :ids
    """
)
.setParameter("tenantId", scope.tenantId())
.setParameter("actorId", scope.actorId())
.setParameter("ids", ids)
.executeUpdate();
```

### 25.1. Không đổi hard delete/soft delete semantics tùy tiện

Nếu dữ liệu có retention/audit/soft-delete policy, hard DELETE có thể không được phép ngay cả owner. Hãy xem action policy trước khi chọn SQL.

### 25.2. Cascades khác per-entity remove

Bulk DELETE không mặc định thực hiện JPA per-entity cascades/lifecycle callbacks. Foreign key constraints và DB cascades có semantics khác, cần thiết kế riêng.

### 25.3. Dynamic native bulk SQL nguy hiểm hơn

Một native SQL được xây bằng cách nối chuỗi từ request có thể vừa thiếu authorization predicates vừa có SQL injection risk. Dùng bind parameters và kiểm soát identifiers/allowlists.

---

## 26. Native SQL phải áp phạm vi thủ công

JPQL/Criteria object mappings không tự đảm bảo native SQL hiểu Java-side `@Filter` hoặc application policy.

Sai:

```java
em.createNativeQuery(
    "SELECT * FROM document WHERE id = ?"
);
```

Đúng về tenant/owner scope:

```java
List<?> rows = em.createNativeQuery(
        """
        SELECT id, title
        FROM document
        WHERE id = :id
          AND tenant_id = :tenantId
          AND owner_id = :actorId
          AND deleted_at IS NULL
        """
    )
    .setParameter("id", documentId)
    .setParameter("tenantId", scope.tenantId())
    .setParameter("actorId", scope.actorId())
    .getResultList();
```

### 26.1. Native query không thừa hưởng mọi provider filter

Hibernate filters/soft-delete extensions có thể không áp vào arbitrary native SQL. Nếu bảo mật dựa vào chúng, native query là điểm cần review kỹ.

### 26.2. SQL injection khác authorization omission

Bind parameters ngăn chèn SQL qua values, nhưng query vẫn có thể thiếu tenant predicate. Một câu SQL parametrized hoàn hảo vẫn có thể trả dữ liệu ngoài quyền.

### 26.3. Dynamic table/column names

Identifier SQL thường không bind như values; nếu cần dynamic sort/field, dùng allowlist constants và không nối raw user text.

---

## 27. SQL report, aggregate và export phải giữ scope

Một endpoint báo cáo:

```sql
SELECT d.status, COUNT(*)
FROM document d
WHERE d.tenant_id = :tenantId
  AND d.owner_id = :actorId
  AND d.deleted_at IS NULL
GROUP BY d.status;
```

Nếu bỏ owner/membership logic, ngay cả khi chỉ trả counts, dữ liệu của user khác có thể bị lộ.

### 27.1. Tổng doanh thu/số lượng cũng là dữ liệu

Một analyst không được xem private customers không có nghĩa được xem aggregation toàn tenant nếu policy không cho phép.

### 27.2. Export thường nguy hiểm hơn màn hình list

Một CSV export endpoint hoặc scheduled reporting job có thể đọc hàng triệu records. Không được bỏ scope vì chạy batch hoặc “nội bộ”.

### 27.3. Background workers phải có service identity rõ

Scheduled job không có end-user principal vẫn cần một `JobAccessScope` hoặc explicit service-account role, với mục đích và quyền được định nghĩa. Không fallback sang “không có user thì query tất cả”.

### 27.4. Admin reports khác user reports

Nếu business thật sự cho tenant admin xem thống kê toàn tenant, query cần tenant predicate và verified admin authority. Không reuse unscoped SQL toàn database.

---

## 28. Insert/create cũng cần kiểm tra quyền

Security không chỉ là SELECT/UPDATE/DELETE. Khi tạo Document:

```java
@Transactional
public Long create(
        CreateDocumentCommand command,
        AccessScope scope) {

    Project project = projectRepository
        .findCreatableProjectById(
            command.projectId(),
            scope
        )
        .orElseThrow(
            () -> new ProjectNotFoundException()
        );

    Document doc = documentFactory.create(
        scope.tenantId(),
        scope.actorId(),
        project,
        command.title()
    );

    em.persist(doc);
    return doc.getId();
}
```

### 28.1. Chỉ lấy tenant/owner từ scope

Không nhận `tenantId`/`ownerId` tùy ý từ user request làm nguồn authoritative. Với admin tạo thay user khác, cần command/action policy riêng.

### 28.2. Chỉ cho liên kết đến parent đủ quyền

Project tồn tại không có nghĩa caller được tạo tài liệu trong project đó. Query `findCreatableProjectById` phải kiểm tra tenant và quyền tạo.

### 28.3. DB FK và NOT NULL không xác minh quyền

Một valid project ID vẫn có thể thuộc user/tenant khác. Schema constraints bảo vệ quan hệ dữ liệu, còn authorization predicate bảo vệ hành động.

---

## 29. Mass assignment: Đừng merge DTO thành entity tùy ý

Sai:

```java
Document detached = objectMapper.convertValue(
    requestBody,
    Document.class
);

em.merge(detached);
```

Nếu DTO có thể chứa `ownerId`, `tenantId`, `deletedAt`, `version` hoặc `status`, caller có thể thử sửa những fields nhạy cảm. Ngoài ra, `merge` có semantics copy state vào managed entity, không phải một phép kiểm tra phân quyền.

### 29.1. Dùng command DTO với allowlisted fields

```java
public record RenameDocumentCommand(
    String title
) {}
```

Service load **editable entity within scope**, rồi gọi:

```java
document.rename(command.title());
```

### 29.2. Không để HTTP serialization quyết định persistence state

Entity JPA không nên tự được expose như public PATCH schema. Domain method bảo vệ invariant và repository enforce authorization.

### 29.3. Version phải được xử lý có chủ đích

Nếu API hỗ trợ optimistic concurrency bằng version hoặc ETag, server phải kiểm tra theo policy; không cho client tự set `@Version` rồi tin JPA sẽ bảo vệ đúng.

---

## 30. Optimistic locking và điều kiện phân quyền là hai lớp khác

```java
@Version
private long version;
```

`@Version` giúp phát hiện concurrent updates trên Document. Nhưng nó không tự kiểm tra tenant/owner.

### 30.1. Một update có thể đúng version nhưng sai owner

Nếu application load Document ngoài scope, version hợp lệ không biến thao tác thành authorized.

### 30.2. Permission revocation cũng không tự đổi Document.version

Membership bị xóa có thể không thay Document row. Một optimistic update trên Document không mặc định phát hiện quyền đã bị thu hồi.

### 30.3. Nếu cần atomic authorization tại thời điểm ghi

Có thể cần:
- Query/conditional UPDATE với đầy đủ security predicates.
- DB RLS WITH CHECK.
- Lock membership/Document phù hợp.
- Version/grant revision.
- Isolation level hoặc workflow policy được thiết kế.

Không có một `@Version` annotation giải quyết tất cả.

---

## 31. Soft delete và trạng thái nghiệp vụ

Thông thường:

```sql
AND d.deleted_at IS NULL
```

là một phần của visibility scope.

Nhưng một màn hình “Thùng rác” có thể cần đọc documents đã xóa mà owner vẫn có quyền.

### 31.1. Đặt action-specific policy

- `findReadable`: chưa xóa.
- `findTrashForOwner`: đã xóa, owner trong tenant.
- `findRestorable`: đã xóa và user có quyền restore.
- `findForAudit`: quyền audit đặc biệt, tenant scoped.

### 31.2. Đừng truyền boolean bỏ filter từ client mà không kiểm tra

Sai:

```java
if (!request.includeDeleted()) {
    predicate.add(notDeleted);
}
```

nếu bất kỳ caller nào cũng được bật `includeDeleted=true` để xem records bị ẩn. Chỉ service action có quyền mới được thay policy.

### 31.3. Các visibility flags khác

`DRAFT`, `PRIVATE`, `ARCHIVED`, `LEGAL_HOLD`, `CONFIDENTIAL` có thể thay quyền đọc/sửa/xóa. Một generic soft-delete predicate chưa đủ cho toàn bộ business policy.

---

## 32. Hibernate filters, multi-tenancy và soft-delete extensions

Một số Hibernate versions hỗ trợ `@Filter`, session filters, multi-tenant discriminator hoặc SQL restrictions.

Ví dụ ý tưởng provider-specific:

```java
@FilterDef(
    name = "tenantFilter",
    parameters = @ParamDef(
        name = "tenantId",
        type = Long.class
    )
)
@Filter(
    name = "tenantFilter",
    condition = "tenant_id = :tenantId"
)
```

Cách dùng cụ thể, annotation imports và cấu hình `@ParamDef` phụ thuộc Hibernate version; đây không phải Jakarta Persistence standard annotation.

### 32.1. Filter bị quên enable

Nếu yêu cầu gọi:

```java
session.enableFilter("tenantFilter")
    .setParameter("tenantId", scope.tenantId());
```

mà một code path quên enable, dữ liệu có thể bị lộ. Đây là lý do session filter một mình không phải mặc định một security boundary đủ mạnh.

### 32.2. Không mặc định filter áp cho mọi đường truy cập

EntityManager.find, direct ID load, associations, native SQL, bulk DML và cached entities có thể có behavior khác nhau tùy Hibernate/provider version và filter features. Phải kiểm thử cụ thể.

### 32.3. `@Where`/SQL restrictions không biểu diễn mọi ACL động

Một static SQL restriction như `deleted=false` không biết actor đang xác thực, membership còn hiệu lực hoặc request action là read hay write.

### 32.4. Defense in depth

Provider filters có thể giảm repeated conditions nhưng application phải có policy kiến trúc và tests. Với yêu cầu isolation cao, database RLS hoặc database/schema-per-tenant có thể tăng bảo vệ khi thiết kế đúng.

---

## 33. Database Row-Level Security (RLS)

Một số databases, ví dụ PostgreSQL, cho phép policy ở database hạn chế rows cho SELECT/INSERT/UPDATE/DELETE.

Ví dụ **chỉ minh họa owner-only policy** trên bảng `document`:

```sql
ALTER TABLE document
ENABLE ROW LEVEL SECURITY;

CREATE POLICY doc_owner_policy
ON document
USING (
    tenant_id =
        current_setting('app.tenant_id', true)::bigint
    AND owner_id =
        current_setting('app.actor_id', true)::bigint
)
WITH CHECK (
    tenant_id =
        current_setting('app.tenant_id', true)::bigint
    AND owner_id =
        current_setting('app.actor_id', true)::bigint
);
```

Policy này chỉ phù hợp với model **owner-only**. Nếu ứng dụng cho project members được xem/sửa, RLS cần bổ sung ACL logic tương ứng; không copy owner-only policy rồi coi đã hỗ trợ shared documents.

### 33.1. `USING` và `WITH CHECK`

Trong PostgreSQL RLS:
- `USING` giới hạn rows có thể thấy/nhắm tới theo operation.
- `WITH CHECK` giới hạn giá trị mới được ghi qua INSERT/UPDATE theo policy.

Việc một user có thể thấy row không đồng nghĩa được đổi tenant/owner của row.

### 33.2. Thiết lập context theo transaction

Một thiết kế có thể dùng transaction-local settings:

```sql
SELECT set_config('app.tenant_id', '42', true);
SELECT set_config('app.actor_id', '501', true);
```

Đặt trong transaction trên **chính DB session/connection** thực hiện query. Tham số `true` của `set_config` trong PostgreSQL biểu thị local to current transaction.

### 33.3. Connection pool và session contamination

Nếu dùng session-level variables mà không reset, connection reuse có thể khiến tenant context cũ rò sang request mới. Transaction-local context/connection lifecycle cần được kiểm chứng nghiêm ngặt.

### 33.4. Quyền bypass RLS

PostgreSQL có các role/superuser/table-owner behaviors có thể bypass RLS tùy cấu hình. Runtime application role không nên là privileged role có thể bỏ qua policy; kiểm tra quyền DB và các tùy chọn như FORCE ROW LEVEL SECURITY khi cần.

### 33.5. RLS không tự giải quyết mọi authorization

Policy với membership/subquery, cache, cross-tenant FK, service-account jobs, SECURITY DEFINER functions hoặc reporting queries vẫn cần thiết kế cẩn thận. RLS là một lớp bảo vệ mạnh nhưng không thay threat modeling và tests.

---

## 34. Multi-tenancy strategies: Database/schema/row

Các mô hình phổ biến:

| Mô hình | Phân tách dữ liệu | Điều kiện bảo mật cần chú ý |
|---|---|---|
| Database per tenant | DB riêng | Tenant routing credentials, cross-DB access |
| Schema per tenant | Schema riêng | Search path/schema routing, pool isolation |
| Shared table + tenant_id | Rows chung bảng | Bắt buộc tenant predicate/RLS/composite FKs |

### 34.1. Row-level tenancy cần WHERE rõ

Với shared tables, tenant condition là ranh giới bắt buộc ở mọi query và write.

### 34.2. Schema-per-tenant vẫn cần owner ACL

Tách schema không tự hạn chế user A đọc Document của user B trong cùng tenant.

### 34.3. Database-per-tenant vẫn có routing risk

Một request routed nhầm database tenant khác có thể lộ dữ liệu lớn. Tenant resolution/auth cần bảo đảm cả lựa chọn datasource.

### 34.4. Không trộn tenant contexts trong cùng persistence context

Một EntityManager/session sống quá lâu và chuyển tenant context giữa chừng có thể chứa managed/cached entities của scope trước. Thiết kế transaction/request scoping phù hợp, không đổi tenant session tùy tiện.

---

## 35. Caches và phạm vi sở hữu

JPA L1 cache trong EntityManager được khóa theo entity identity; L2/query cache tùy provider/config. Chúng không phải authorization engine.

### 35.1. Query theo ID có thể trả managed entity đã load

Nếu entity ngoài scope đã có trong persistence context, `em.find()` có thể trả từ L1 mà không phát SQL mới. Không thể dựa vào DB predicate nếu bạn không chạy scoped query.

### 35.2. Shared L2 cache cần tenant-aware identity

Trong hệ thống multi-tenancy, provider phải cấu hình cache keys/tenant discrimination đúng. Một cache tự viết kiểu `Map<Long,Document>` có thể bị collision nếu cùng ID xuất hiện ở nhiều tenants.

### 35.3. Cache kết quả access decision cần invalidation

Nếu quyền bị thu hồi, cached `canEdit=true` có thể không còn hợp lệ. Định nghĩa TTL, event invalidation, grant revision hoặc strong consistency theo SLA.

### 35.4. HTTP/application cache cũng cần scope

Cache key chỉ gồm `documentId` có thể trả dữ liệu của user khác. Thêm tenant/scope/policy version hoặc chỉ cache dữ liệu có phân quyền được kiểm tra lại.

### 35.5. Không cache raw entity rồi dùng lại giữa users

Managed entities không thread-safe và không phải DTO security-safe. Dữ liệu đưa ra bên ngoài nên được map theo field-level policy của caller.

---

## 36. Field-level authorization khác row-level authorization

Dù user có quyền đọc Document, họ chưa chắc có quyền xem:

- Internal review notes.
- Owner email.
- Confidential legal attachments.
- Private audit events.
- Financial metadata.
- Security classification.

### 36.1. Query row scoped là điều kiện cần, chưa đủ

Một DTO projection phải chỉ chọn fields caller được phép xem.

### 36.2. Không `SELECT d` rồi serialize mọi getter

JPA entity có thể chứa associations và basic fields nhạy cảm. Dùng DTOs/resolvers có allowlist; không serialize arbitrary entity graphs.

### 36.3. Field-level policy có thể ảnh hưởng count/search

Nếu caller không được xem `internalStatus`, có thể họ cũng không được filter/sort theo nó, vì response count/order có thể tiết lộ thông tin.

---

## 37. Sắp xếp, filter và SQL injection

Đầu vào:

```json
{
  "sortBy": "title",
  "sortDirection": "asc"
}
```

Một allowlist:

```java
private static final Set<String> ALLOWED_SORTS =
    Set.of("id", "title", "createdAt");
```

### 37.1. Không nối thẳng identifier từ client

Sai:

```java
String jpql = "SELECT d FROM Document d ORDER BY d."
    + request.sortBy();
```

Dù các giá trị field thường không bind như parameters, dynamic path phải được whitelist và kiểm tra theo metadata.

### 37.2. Parameterize values

```java
query.setParameter("tenantId", scope.tenantId());
```

Không nối tenantId hoặc keyword vào JPQL string tùy ý.

### 37.3. Injection khác thiếu authorization

Một query dùng parameters đúng có thể vẫn thiếu tenant predicate. Và một query có tenant predicate đúng vẫn có thể bị injection nếu raw inputs được nối vào SQL.

### 37.4. Whitelist sort không thay row scope

Sort hợp lệ vẫn phải áp dụng sau khi đã lọc dữ liệu được phép đọc.

---

## 38. Test IDOR/BOLA theo cặp user/tenant

Một test fixture nên có tối thiểu:

```text
Tenant T1:
    User A: owner Document D1
    User B: owner Document D2
    User A: viewer Project P3 (Document D3 của B)

Tenant T2:
    User C: owner Document D4

Soft deleted:
    Document D5 thuộc A
```

Cần kiểm tra:

| Caller | Resource | Hành động | Kỳ vọng |
|---|---|---|---|
| A/T1 | D1 | READ | Cho phép |
| A/T1 | D2 | READ | Từ chối nếu không shared |
| A/T1 | D3 | READ | Cho phép nếu membership active |
| A/T1 | D3 | EDIT | Từ chối nếu role VIEWER |
| A/T1 | D4/T2 | READ | Từ chối |
| A/T1 | D5 deleted | READ normal | Từ chối |
| Admin T1 | D1/D2 | READ | Theo tenant-admin policy |
| Admin T1 | D4/T2 | READ | Từ chối |
| Anonymous | Bất kỳ | READ | Từ chối |
| B/T1 | D1 | UPDATE | Từ chối nếu không editor/owner |

### 38.1. Test với IDs hợp lệ của người khác

Không chỉ test random ID không tồn tại. Phải test **ID thực sự tồn tại** nhưng ngoài quyền của caller.

### 38.2. Test cả count/exists

Một endpoint trả `false`/`0` cho ngoài scope thường đúng hơn việc tiết lộ entity có tồn tại nhưng bị cấm, tùy API policy.

### 38.3. Test read và write riêng

Cùng user có thể đọc được D3 nhưng không edit. Nếu chỉ test GET, lỗ hổng PATCH/DELETE vẫn tồn tại.

---

## 39. Test mọi query path, không chỉ một endpoint

Một bảng coverage:

| Query path | Test phải có |
|---|---|
| `findReadableById` | ID ngoài tenant/owner |
| Search/list | Không lộ documents không được xem |
| Count/exists | Không lộ số lượng ngoài quyền |
| Pagination | total/page scoped |
| DTO projection | Row và field đều scoped |
| Export CSV | Không lộ dữ liệu cross-tenant |
| Aggregate dashboard | Scope ở GROUP BY source rows |
| Lazy association | Child-specific visibility |
| Bulk update | Không sửa unauthorized rows |
| Bulk delete | Không xóa unauthorized rows |
| Native SQL | Explicit tenant/owner filters |
| Scheduled job | Service-account scope |
| Cache hit | Không bypass permission check |
| Permission revoke | Cached grants không vượt SLA |
| Create with Project ID | Không liên kết Project ngoài scope |
| Transfer owner | Action-specific policy |
| Soft delete/restore | Đúng lifecycle/action scope |

### 39.1. Query mới phải có negative test

Khi thêm repository method mới, hãy thêm test user A không thể xem/chỉnh row của B hoặc tenant T2, kể cả khi client đoán được ID.

### 39.2. Test SQL behavior trên provider thật

Mocks không chứng minh JPQL WHERE/EXISTS/Criteria thực sự lọc đúng. Integration tests với database cùng dialect giúp phát hiện lỗi predicate, query join và RLS.

### 39.3. Tests không thay review policy

Một test fixture chưa bao quát grant/deny combinations có thể không phát hiện bug. Có thể dùng property-based tests/matrix tests cho nhiều tổ hợp role/tenant/owner.

---

## 40. Test case đặc biệt: OR predicate precedence

Giả sử user A/T1 là viewer của Project P1; user C/T2 cũng là member của Project P1 có trùng numeric project ID.

Một query sai:

```sql
WHERE d.tenant_id = 1
  AND d.owner_id = 501
   OR EXISTS (SELECT 1 FROM memberships ...)
```

có thể trả D4/T2.

### 40.1. Kỳ vọng

Không bao giờ có cross-tenant result, **kể cả membership subquery trả true**.

### 40.2. Test cho branch admin

Tenant admin T1 chỉ được xem T1. Đừng test admin bằng một database có duy nhất T1; cần seed T2.

### 40.3. Test combination với keyword

Một keyword matches D4/T2 không được làm D4 xuất hiện chỉ vì optional filter được OR sai.

---

## 41. Test tác động của permission revocation

Các scenarios:

1. A có quyền EDITOR; update thành công.
2. Membership bị đổi sang VIEWER; update mới bị chặn.
3. Membership inactive; read mới bị chặn.
4. Cache được làm mới theo policy.
5. Một transaction đã bắt đầu trước revocation: hành vi theo consistency contract đã định.
6. User đổi active tenant trong session: persistence context/cache không rò scope cũ.
7. Admin T1 mất quyền admin: subsequent queries bị chặn.

### 41.1. Không test chỉ bằng mock boolean role

Cần validate membership store/query, transaction boundary và cache behavior thực tế.

### 41.2. Cần xác định SLA revoke

Nếu quy định “quyền bị thu hồi có hiệu lực ngay lập tức”, cached permissions với TTL dài có thể vi phạm; cần strategy phiên bản quyền/transaction consistency phù hợp.

---

## 42. Review truy vấn tĩnh và dynamic

Khi code review một query, hỏi:

1. Đây là query của actor nào?
2. Tenant ID đến từ nguồn đáng tin nào?
3. Action là READ/EDIT/DELETE/EXPORT/ADMIN?
4. Mandatory predicates có ở SQL/JPQL root không?
5. Các nhánh OR có nằm **trong** tenant restriction không?
6. Có EXISTS/ACL join và ràng buộc cùng tenant không?
7. Có soft-delete/status/classification policy không?
8. Count/query totals có scoped cùng data query không?
9. Entity relationships có thể đưa dữ liệu khác tenant vào graph không?
10. Có `find`/`getReference` direct ID load không?
11. Có bulk DML hoặc native SQL bỏ provider filters không?
12. Có cache làm policy stale hoặc cross-tenant không?
13. Có code path background/job mà thiếu principal không?
14. Có DTO field lộ thông tin ngoài quyền không?
15. Có negative tests cho same tenant/different owner và cross tenant không?

### 42.1. Không dựa vào tên method

`findSecureDocuments` chỉ là tên. Predicate và proof tests mới có giá trị.

### 42.2. Không “fix” thiếu permission bằng UI hiding

Ẩn nút Edit trên frontend là UX, không chặn HTTP request tự gửi. Backend phải bảo vệ query/mutation.

---

## 43. Giám sát và audit truy cập

Các security events nên ghi nhận theo policy:

- Actor/tenant/request correlation ID.
- Action: document read, edit, delete, download.
- Resource ID hoặc safe reference.
- Allow/deny decision và lý do đã được phân loại.
- Version/policy revision nếu phù hợp.
- Command outcome và transaction status.
- Không ghi raw secret/PII ngoài nhu cầu audit.

### 43.1. Đừng log entity graph

Một denied access path không nên in toàn Document hoặc relations ra logs, vì đó cũng là data leak.

### 43.2. Dấu hiệu bất thường

- Nhiều request đổi liên tục sequential IDs.
- Tăng đột biến 404/denied accesses.
- Truy vấn/export quy mô bất thường.
- Nhiều cross-tenant attempts.
- RLS denials hoặc query count mismatch.

### 43.3. Audit không thay authorization

Log một truy cập sai sau khi dữ liệu đã trả không phải cơ chế chặn. Security condition phải được enforce trước/đồng thời với data access.

---

## 44. Performance của predicates bắt buộc

Áp `tenantId`/owner/membership trong mọi query có chi phí nhất định, nhưng bỏ chúng vì hiệu năng là sai ưu tiên.

### 44.1. Index theo query patterns

Ví dụ:

```sql
CREATE INDEX ix_document_tenant_owner_live
ON document (tenant_id, owner_id, id);
```

Nếu DB hỗ trợ partial indexes:

```sql
CREATE INDEX ix_document_live_tenant_owner
ON document (tenant_id, owner_id, id)
WHERE deleted_at IS NULL;
```

Cú pháp và hiệu năng tùy database; đây chỉ là ví dụ PostgreSQL-like.

### 44.2. Index membership lookup

```sql
CREATE INDEX ix_membership_read
ON project_membership (
    tenant_id, project_id, user_id, active
);
```

Có thể tạo composite/partial indexes phù hợp với role/expiry policy; đo SQL EXPLAIN thay vì chỉ tăng indexes.

### 44.3. EXISTS có thể hiệu quả hơn join trong một số use case

Nếu chỉ cần kiểm tra tồn tại grant, EXISTS tránh một số duplicate rows do joins. Nhưng planner, indexes và data distributions quyết định performance thực.

### 44.4. Caching permission results có trade-off

Cache có thể giảm query cost nhưng phải có revocation/invalidation contract. Không hy sinh quyền truy cập chỉ để giảm DB queries.

---

## 45. Kiến trúc repository: Bảo mật theo thiết kế

Một flow nên được tổ chức như sau:

```text
HTTP/Job/Event
     |
     v
Authentication + trusted tenant resolution
     |
     v
AccessScope (actor, tenant, verified roles)
     |
     v
Application service (action-specific policy)
     |
     v
Scoped repository query
     |
     +-- mandatory tenant predicate
     +-- mandatory owner/ACL predicate
     +-- soft-delete/classification constraints
     +-- optional business filters (AND)
     |
     v
Database (+ constraints/RLS khi có)
     |
     v
Allowed DTO / result
```

### 45.1. Ít đường đi tắt hơn

Giới hạn việc controller gọi raw `EntityManager` trực tiếp hoặc dùng repository generic `findAll()` cho protected entities.

### 45.2. Default-deny

Nếu không có authenticated scope, không có role hoặc không xây được predicate bảo mật, fail closed. Không fallback sang unscoped query.

### 45.3. Service-account exceptions phải có policy

Một batch data migration có thể cần quyền vượt actor thông thường, nhưng đó phải là explicit privileged operation với audit và credential controls, không phải `if (user == null) skipFilter`.

---

## 46. Những anti-pattern điển hình

| Anti-pattern | Lỗ hổng | Hướng đúng |
|---|---|---|
| `findById(id)` trong user endpoint | IDOR/BOLA | Scoped query theo tenant/ACL |
| `@PreAuthorize("authenticated")` là đủ | Chưa kiểm object permission | Row-level authorization |
| Tenant/owner lấy từ request | Caller tự chọn scope | Server-resolved AccessScope |
| Query tenant-only cho private records | User cùng tenant đọc nhau | Owner/membership policy |
| `tenant AND owner OR public` | OR vượt tenant | `tenant AND (owner OR public)` |
| `where(security); where(filter)` | Criteria WHERE bị ghi đè | Một lần AND composition |
| Filter sau pagination | Đọc/lộ rows ngoài quyền, pages sai | WHERE trước LIMIT |
| Count toàn tenant cho user | Information leakage | Scoped count |
| `existsById` không scope | Lộ resource existence | Scoped exists |
| View permission dùng cho update | Viewer sửa tài liệu | Action-specific editable predicate |
| Bulk UPDATE theo `id IN` | Sửa unauthorized rows | Mandatory predicates trong DML |
| Native query không có tenant | Cross-tenant leak | Explicit scope/RLS |
| Hibernate filter bị quên enable | Bypass isolation | Defense-in-depth + tests |
| `getReference(Project,id)` khi create | Cross-tenant association | Validate project rights |
| FK chỉ theo project ID | Không ngăn cross-tenant link | Composite FK + service auth |
| Trả JPA entity trực tiếp | Field/lazy data leak | Authorized DTO |
| Cache key chỉ có documentId | Cross-user/tenant leak | Scope-aware cache |
| Role ADMIN không kiểm tenant | Privilege escalation | Scoped admin authority |
| Background job thiếu principal → all | Privilege escalation | Explicit service scope |
| Dùng UUID thay permission check | Guessability ≠ authorization | Verify object access |
| Xóa membership nhưng cache không invalid | Access tồn tại sau revoke | TTL/version/invalidation |
| Chỉ test random ID không tồn tại | Bỏ sót IDOR | Seed real unauthorized IDs |
| Chỉ giới hạn UI button | Backend vẫn bị gọi trực tiếp | Enforce server-side |

---

## 47. Bài tập thực hành

### Bài 1. `findById` có đủ không?

Controller nhận Document ID rồi gọi `em.find()`.

**Đáp án:** Không. JPA tìm theo PK, không tự áp tenant/owner ACL.

### Bài 2. Đổi ownerId trong URL

User A truyền `ownerId=B` vào list API.

**Đáp án:** Không dùng ownerId từ request làm scope. Nếu cho filter theo owner B, dữ liệu vẫn phải được AND với mandatory access policy của A.

### Bài 3. Tenant admin

Admin T1 yêu cầu Document T2.

**Đáp án:** Từ chối. Tenant admin chỉ có quyền trong tenant đã được xác minh.

### Bài 4. OR membership

Query `tenant=T1 AND owner=A OR activeMember`.

**Đáp án:** Sai precedence, có thể mở dữ liệu T2. Dùng `tenant=T1 AND (owner=A OR activeMember)`.

### Bài 5. Viewer muốn sửa

User có `VIEWER` role ở Project P.

**Đáp án:** Có thể đọc theo policy, không tự được edit. Dùng editable predicate với EDITOR/ADMIN.

### Bài 6. getResultList rồi lọc Java

**Đáp án:** Không nên. Row ngoài quyền đã được đọc và pagination/count sai. Scope trong SQL/JPQL.

### Bài 7. COUNT không scope

**Đáp án:** Có thể leak số lượng tài liệu của người khác. Count phải dùng cùng visibility predicate.

### Bài 8. EXISTS theo ID

**Đáp án:** Scoped exists, không dùng `existsById` trực tiếp trên protected endpoint nếu nó bỏ tenant/owner.

### Bài 9. DTO projection

**Đáp án:** Dù không trả entity, query phải có tenant/ACL predicates và field allowlist.

### Bài 10. Native SQL

**Đáp án:** Không tự được bảo vệ bởi Hibernate filters. Thêm scope rõ và cân nhắc RLS.

### Bài 11. Criteria.where hai lần

**Đáp án:** Lần sau có thể thay restrictions trước. Kết hợp `cb.and` trong một lần where.

### Bài 12. Spring Specification chỉ có keyword

**Đáp án:** Không đủ. Server phải AND mandatory scope spec với optional keyword spec.

### Bài 13. Soft-deleted document

**Đáp án:** API đọc bình thường phải loại bỏ nếu policy yêu cầu; restore/trash dùng action-specific policy.

### Bài 14. Project association cross tenant

Document T1 tham chiếu Project T2 nhưng FK theo project ID vẫn hợp lệ.

**Đáp án:** Cần service validation và composite FK `(tenant_id, project_id)` khi schema hỗ trợ.

### Bài 15. Lazy comments

User đọc Document hợp lệ, comments có private visibility.

**Đáp án:** Phải có child-specific authorization query/DTO. Parent access không tự cấp quyền cho mọi child.

### Bài 16. Bulk update 100 IDs

**Đáp án:** WHERE phải chứa tenant/owner/permission. Kiểm tra affected rows và bulk bypass lifecycle/version semantics.

### Bài 17. Dùng `@Version`

**Đáp án:** Chống concurrent updates theo entity, không thay tenant/owner authorization.

### Bài 18. Thu hồi membership

**Đáp án:** Cần rõ revocation consistency window; caches/transactions/locks có thể khiến quyền cũ còn hiệu lực trong một khoảng.

### Bài 19. Hibernate filter

**Đáp án:** Là vendor-specific, phải enable/cấu hình đúng và test từng query path; không mặc định native/bulk/find/caches đều được bảo vệ.

### Bài 20. RLS và connection pool

**Đáp án:** Tránh tenant context còn sót ở reused connection; dùng transaction-local settings/cấu hình đáng tin và role không bypass policy.

### Bài 21. Search theo confidential field

**Đáp án:** Row visibility không đảm bảo quyền xem/filter field nhạy cảm. Cần field-level authorization.

### Bài 22. Export CSV từ background job

**Đáp án:** Job phải có explicit service-account scope. Không fallback unscoped nếu thiếu user principal.

### Bài 23. Client thay tenantId trong body

**Đáp án:** Server dùng authenticated active tenant từ trusted source; body tenant ID chỉ được chấp nhận sau authorization.

### Bài 24. UUID không đoán được

**Đáp án:** Không làm IDOR biến mất. Phải kiểm object-level authorization.

### Bài 25. `@ManyToOne Project`

**Đáp án:** Association mapping không bảo đảm user có quyền và không tự bảo vệ cross-tenant link.

### Bài 26. Admin report

**Đáp án:** Admin có thể có quyền xem toàn tenant nếu policy cho phép, nhưng vẫn cần `tenantId` và field-level limits.

### Bài 27. Cache kết quả `canRead`

**Đáp án:** Cần TTL/invalidation/grant revision; revocation có thể làm cached result stale.

### Bài 28. Pagination trả page rỗng dù còn data

**Đáp án:** Có thể do lọc Java sau pagination. Đưa authorization vào database WHERE.

### Bài 29. Permission cho transfer owner

**Đáp án:** Cần explicit action, target tenant validation, audit; không mass-assign ownerId qua generic PATCH.

### Bài 30. Test negative case

**Đáp án:** Seed row ngoài quyền nhưng tồn tại thật, test READ/EDIT/DELETE/COUNT/EXPORT và cross-tenant, không chỉ ID ngẫu nhiên.

---

## 48. Checklist triển khai an toàn

1. Có xác định authentication principal đáng tin?
2. Có lấy active tenant từ server-side trusted resolver?
3. Mọi user-facing query có tenant predicate?
4. Mọi private data query có owner/ACL predicate?
5. Admin role có bị giới hạn theo tenant?
6. Read/write/delete/export có policy riêng?
7. Có mặc định deny nếu không có scope?
8. Các nhánh OR có được nhóm trong mandatory AND?
9. Optional filters không thay authorization predicates?
10. Criteria builder có tránh ghi đè `where()`?
11. Spring Specification có bắt buộc scope ở service/adapter?
12. `findById`/`find`/`getReference` có bị dùng trực tiếp cho protected data?
13. Exists/count/aggregate có cùng scope?
14. Pagination lọc trước OFFSET/LIMIT?
15. Sort/filter fields có allowlist?
16. DTO projection có giữ row và field-level permissions?
17. JOIN FETCH/lazy associations có child-specific policy?
18. Relationship create/update có kiểm tenant của target?
19. Có DB composite FKs khi phù hợp?
20. Soft-delete/archived/status conditions có được giữ đúng action?
21. Bulk UPDATE/DELETE có tenant/owner/ACL trong WHERE?
22. Bulk DML có xử lý persistence context stale và version implications?
23. Native SQL có scope hoặc DB RLS đáng tin?
24. Vendor filters có test đối với find, native, bulk, caches?
25. RLS app role không bypass policies?
26. Connection pool không rò tenant context?
27. Cache keys có tenant/scope và revocation policy?
28. Background jobs có explicit service identity?
29. Có kiểm race khi permission bị thu hồi?
30. `@Version` không bị coi là permission control?
31. Có tránh mass assignment tenantId/ownerId?
32. Có audit deny/grant decisions mà không log PII dư thừa?
33. Có indexes hỗ trợ tenant/owner/membership predicates?
34. Có negative tests same-tenant/different-owner?
35. Có negative tests cross-tenant cho mọi action?
36. Có test COUNT/page total không leak?
37. Có test export/report và background flows?
38. Có test policy sau membership revoke?
39. Có review mọi repository method mới?
40. Có xử lý incident khi phát hiện query không scoped?

---

## 49. Sơ đồ quyết định cho mọi truy vấn

```text
             Request / scheduled task / event
                           |
                           v
                  Có trusted identity?
                        /       \
                      Không      Có
                        |         |
                        v         v
                    DENY      Có tenant scope?
                                   /      \
                                 Không     Có
                                   |        |
                                   v        v
                                  DENY  Action READ/EDIT/DELETE?
                                            |
                                            v
                                     Chọn policy theo action
                                            |
                                            v
                                     Mandatory predicates
                                     tenant + owner/ACL
                                     + lifecycle/classification
                                            |
                                            v
                                     AND optional filters
                                            |
                                            v
                                  Query/JPA/SQL dưới DB scope
                                            |
                                            v
                                   Authorized rows + fields
                                            |
                                            v
                                   DTO / result / state change
```

Đối với create, cần thêm bước xác nhận parent/target association cùng tenant và caller có quyền tạo. Với bulk DML, security predicates phải nằm trong DML WHERE. Với reporting/count, cùng policy phải áp dụng trước aggregation.

---

## 50. Tổng kết

1. **Authentication không đồng nghĩa row-level authorization.** JPA `find`, `getReference` và generic repository methods không tự biết quyền của caller.
2. **Giữ tenant predicate là ranh giới bắt buộc** trong shared-table multi-tenancy, kể cả đối với tenant admin.
3. **Giữ owner/ACL predicate theo từng action**: READ khác EDIT, DELETE, RESTORE, EXPORT và ADMIN.
4. **Mandatory scope phải AND với optional business filters**; nhóm các nhánh OR trong ngoặc để không vượt tenant.
5. **Chỉ dùng trusted AccessScope từ authenticated server context**, không để client tự gửi tenant/owner/admin làm quyền.
6. **SELECT, COUNT, EXISTS, GROUP BY, DTO projections và pagination đều có thể leak thông tin** nếu scope không đồng nhất.
7. **Lọc ở database trước pagination**, không lấy row rộng rồi filter trong Java.
8. **Relationships và lazy loads có thể vượt phạm vi dữ liệu** nếu không kiểm tra quyền của target/children và tenant consistency.
9. **Bulk UPDATE/DELETE phải có security predicates trực tiếp**, không dựa vào entity callbacks hoặc optimistic locking mặc định.
10. **Native SQL và provider-specific filters cần review riêng**; không mặc định Hibernate filter áp mọi query path.
11. **DB Row-Level Security và composite foreign keys là defense in depth**, cần cấu hình role, connection/session scope và ACL đúng.
12. **Caches phải tenant-aware và permission-aware**, có policy invalidation khi quyền bị thu hồi.
13. **@Version không phải permission control**; revocation race cần consistency contract riêng.
14. **Tránh mass assignment**, chỉ expose command DTO allowlisted fields và mutate managed entity đã được load trong editable scope.
15. **Có negative integration tests cho user khác, tenant khác, count, bulk, export, associations và caches**.
16. **Bảo mật phải được thiết kế mặc định trong repository/service API** thay vì phụ thuộc mỗi developer nhớ thêm một WHERE.

Nguyên tắc cuối cùng: **đừng coi “truy vấn đúng entity” là “truy vấn đúng dữ liệu người dùng được phép thấy”**. Mọi đường truy cập phải trả lời hai câu hỏi trước khi đi tới database: **dữ liệu thuộc tenant nào, và actor được phép thực hiện hành động gì trên các rows nào?** Khi cả hai điều kiện luôn được đưa vào truy vấn hoặc được một database policy đáng tin cậy enforce, hệ thống JPA mới giảm thiểu được các lỗ hổng IDOR/BOLA, rò rỉ thống kê và cập nhật nhầm dữ liệu trong ứng dụng nhiều người dùng, nhiều doanh nghiệp.
