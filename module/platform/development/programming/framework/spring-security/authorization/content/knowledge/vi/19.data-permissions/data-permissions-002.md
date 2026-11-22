# Truy vấn theo ID kết hợp chủ sở hữu hoặc phạm vi được phép

## 1. Mục tiêu: ID xác định mục tiêu, không chứng minh quyền

Trong ứng dụng Spring Security, một request như `GET /documents/42` chỉ cho biết đối tượng đang được yêu cầu. Nếu service gọi `findById(42)` rồi trả entity, một người dùng có thể đoán hoặc thay ID để truy cập tài liệu của người khác. Đây là dạng **Broken Object Level Authorization (BOLA)**, thường có biểu hiện IDOR.

Với dữ liệu riêng, câu hỏi không phải chỉ là “document 42 có tồn tại không?”, mà là **document 42 có nằm trong tập tài nguyên mà actor hiện tại được phép truy cập không?**. Một truy vấn có predicate quyền giúp biểu diễn điều đó ngay ở tầng dữ liệu:

~~~sql
SELECT d.*
FROM documents d
WHERE d.id = :requested_id
  AND d.tenant_id = :verified_tenant
  AND d.owner_user_id = :verified_actor;
~~~

Khi có chia sẻ hoặc quyền theo nhóm, phần owner có thể mở rộng thành `(owner OR valid share OR verified project membership)`. Tuy nhiên, các điều kiện bắt buộc về ID, tenant, trạng thái dữ liệu và authority hành động không được rơi khỏi phạm vi áp dụng.

**Bất biến thiết kế:** một request truy vấn theo ID chỉ có thể trả về đúng object được hỏi **và** thuộc phạm vi người gọi được phép. Biết hoặc đoán đúng ID không đủ. Nếu thiếu xác thực, tenant, owner hoặc bằng chứng cấp quyền bắt buộc, hệ thống phải từ chối, không dùng dữ liệu client tự khai làm mặc định.

Bài Knowledge này trình bày mô hình truy vấn owner-only, mở rộng bằng share/ACL/nhóm, cú pháp Spring Data JPA, khác biệt READ/WRITE/DELETE, atomic conditional update, xử lý 404/403, concurrency, pagination, ví dụ Java 17 và ma trận kiểm thử.

## 2. Phân biệt các lớp quyền

| Lớp | Ví dụ | Vì sao chưa đủ một mình? |
|---|---|---|
| Authentication | Actor là An, đã xác thực | An vẫn có thể đoán ID tài liệu của Bình |
| Function-level authority | `document:read` | Cho phép gọi chức năng đọc, không cho đọc mọi document |
| Tenant scope | Actor thuộc tenant north | Trong north có nhiều owner và nhóm |
| Ownership | `document.ownerUserId = an` | Đủ cho policy owner-only, nhưng không biểu diễn chia sẻ |
| Object grant/ACL | Bình có READ với document 42 | Phải kiểm tra đúng object, action, tenant và hiệu lực |
| Project membership | An có quyền READ trong project của tài liệu | Membership có thể bị thu hồi hoặc bị hạn chế |
| Business state | Document không bị embargo/legal hold | Điều kiện trạng thái không tự theo authority hoặc owner |

Một đặc tả phổ biến:

~~~text
ALLOW_READ =
  isAuthenticated(actor)
  AND hasAuthority(actor, "document:read")
  AND resource.id == requestedId
  AND resource.tenantId == actor.verifiedTenant
  AND (
      resource.ownerId == actor.id
      OR validShare(actor, resource, READ)
      OR validProjectScope(actor, resource, READ)
  )
  AND resource.isReadable()
~~~

Đây là **logic khái niệm**, không phải đoạn Java độc lập. Điểm quyết định là `ID AND tenant AND (owner OR allowedScope)`, không phải `ID AND tenant AND owner OR allowedScope`.

Cần thiết kế riêng nếu một super-admin thực sự được phép vượt scope nào đó. Một flag `isAdmin=true` gửi từ request không phải bằng chứng được cấp quyền.

## 3. Mẫu nguy hiểm: tìm được object là trả ngay

~~~java
@GetMapping("/documents/{id}")
public DocumentDto view(@PathVariable Long id) {
    return mapper.toDto(repository.findById(id).orElseThrow());
}
~~~

Mã tích hợp Spring MVC trên **không có bảo vệ theo object**. Một HTTP rule `authenticated()` hoặc `hasAuthority('document:read')` chưa kiểm tra owner hay tenant.

Một kiểu khác:

~~~java
Document document = repository.findById(id).orElseThrow();
if (!actor.userId().equals(document.getOwnerUserId())) {
    throw new AccessDeniedException("Forbidden");
}
return mapper.toDto(document);
~~~

Kiểm tra owner sau khi load có thể đúng nếu guard được thực thi chặt, nhưng dữ liệu ngoài phạm vi đã được lấy vào persistence context, và các đường code khác dễ quên guard. Query scoped có những lợi ích rõ ràng: lọc ngay tại database, không trả object ngoài quyền cho caller, code repository thể hiện ý định, dễ kiểm thử sai ID/tenant/owner và dễ mở rộng list.

Không có nghĩa mọi ứng dụng đều bắt buộc một câu SQL duy nhất cho mọi chính sách phức tạp. Khi policy cần tính toán bên ngoài DB, vẫn phải tổ chức service authorization an toàn; nhưng đối với owner và quyền theo bảng quan hệ, query scoped thường là giải pháp mạnh và dễ review.

## 4. Cấp đơn giản nhất: ID + tenant + owner

Schema minh họa:

~~~sql
CREATE TABLE documents (
    id            BIGINT PRIMARY KEY,
    tenant_id     VARCHAR(64) NOT NULL,
    owner_user_id VARCHAR(128) NOT NULL,
    title         VARCHAR(255) NOT NULL,
    status        VARCHAR(32) NOT NULL,
    version       BIGINT NOT NULL DEFAULT 0
);

CREATE INDEX idx_documents_tenant_owner
    ON documents (tenant_id, owner_user_id, id);
~~~

Nếu ID chỉ duy nhất **trong từng tenant** thay vì globally unique, phải dùng primary/unique key và truy vấn phù hợp như `(tenant_id, id)`; không mặc định `id` đơn độc xác định đúng một document toàn hệ thống.

Truy vấn owner-only:

~~~sql
SELECT d.id, d.tenant_id, d.owner_user_id, d.title
FROM documents d
WHERE d.id = :id
  AND d.tenant_id = :tenant
  AND d.owner_user_id = :actor;
~~~

Actor An ở tenant north yêu cầu document của Bình cũng nằm ở north: không có dòng. An yêu cầu document của tenant south: không có dòng. Khi không có dữ liệu, service chưa thể kết luận document không tồn tại trên toàn DB; chỉ biết **không hiện diện trong tập actor được phép nhìn thấy**.

Tuyệt đối không lấy `:actor` hoặc `:tenant` từ payload do client khai rồi coi là identity. Chúng phải đến từ security context hoặc một tầng resolver xác thực đáng tin.

### Spring Data derived query

Nếu entity Java có các property `id`, `tenantId`, `ownerUserId`:

~~~java
import java.util.Optional;
import org.springframework.data.jpa.repository.JpaRepository;

public interface DocumentRepository extends JpaRepository<Document, Long> {

    Optional<Document> findByIdAndTenantIdAndOwnerUserId(
            Long id, String tenantId, String ownerUserId);
}
~~~

Spring Data JPA xây predicate dựa trên tên property và các từ khóa `And`. `Optional.empty()` thay cho việc lấy object không thuộc scope.

Lưu ý phương thức `findById` kế thừa từ repository là method định danh được xử lý đặc biệt. Đừng cố override nó để thêm quyền rồi kỳ vọng mọi caller tự động nhận cùng scope; tạo method scoped có tên và contract riêng rõ ràng.

## 5. Bắt buộc dùng actor đã xác thực

Một kiểu dữ liệu để truyền scope qua service:

~~~java
public record VerifiedActor(String userId, String tenantId) {
    public VerifiedActor {
        if (userId == null || userId.isBlank()
                || tenantId == null || tenantId.isBlank()) {
            throw new IllegalArgumentException("Missing actor identity");
        }
    }
}
~~~

**Tên VerifiedActor không làm dữ liệu trở nên đáng tin.** Chỉ lớp hạ tầng được kiểm soát mới được dựng record này từ authentication/session/JWT đã xác minh issuer, audience, signature và các ràng buộc cần thiết. Không dựng từ `request.userId()` hoặc `request.tenantId()` rồi truyền vào repository như thể nó đã được xác thực.

Mẫu service owner-only:

~~~java
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class DocumentQueryService {
    private final DocumentRepository repository;
    private final CurrentActorResolver actorResolver;
    private final DocumentMapper mapper;

    public DocumentQueryService(DocumentRepository repository,
            CurrentActorResolver actorResolver, DocumentMapper mapper) {
        this.repository = repository;
        this.actorResolver = actorResolver;
        this.mapper = mapper;
    }

    @PreAuthorize("isAuthenticated() and hasAuthority('document:read')")
    @Transactional(readOnly = true)
    public DocumentDto readOwned(Long id) {
        VerifiedActor actor = actorResolver.requireCurrentActor();

        if (id == null || id <= 0) {
            throw new IllegalArgumentException("Invalid ID");
        }

        Document document = repository
                .findByIdAndTenantIdAndOwnerUserId(
                        id, actor.tenantId(), actor.userId())
                .orElseThrow(ResourceNotFoundException::new);
        return mapper.toDto(document);
    }
}
~~~

Đây là **snippet dự án Spring**, chưa phải file Java 17 độc lập: cần các kiểu `Document`, `CurrentActorResolver`, `DocumentMapper`, `DocumentDto` và exception thuộc ứng dụng.

Ba lớp bảo vệ:
1. `@PreAuthorize` kiểm tra authority hành động trước phần thân method **khi lời gọi đi qua Spring-managed proxy** và method security đã bật.
2. `CurrentActorResolver` lấy user/tenant đã xác minh, không nhận lựa chọn scope từ body.
3. Repository chỉ trả object đúng ID, tenant và owner; service chỉ map object đã qua query.

`@Transactional(readOnly=true)` diễn đạt giao dịch đọc và có thể tối ưu truy vấn, **không tự cấp hay giới hạn quyền**. Với HTTP controller, hãy giữ adapter mỏng và gọi chính use case bean này.

## 6. Thêm quyền chia sẻ: ID + tenant + (owner OR grant)

Khi document cho phép chia sẻ, một bảng grant có thể đủ:

~~~sql
CREATE TABLE document_grants (
    id              BIGINT PRIMARY KEY,
    document_id     BIGINT NOT NULL,
    grantee_user_id VARCHAR(128) NOT NULL,
    permission      VARCHAR(30) NOT NULL,
    revoked_at      TIMESTAMP NULL,
    expires_at      TIMESTAMP NULL,
    FOREIGN KEY (document_id) REFERENCES documents(id)
);

CREATE INDEX idx_document_grant_read
    ON document_grants (document_id, grantee_user_id, permission);
~~~

Đây là schema minh họa. Trong hệ multi-tenant, bảo đảm khóa ngoại/ràng buộc hoặc business guard không thể gắn grant sai tenant. Một sản phẩm chỉ có grant READ đơn giản chưa nhất thiết phải triển khai toàn bộ Spring Security ACL module.

Truy vấn:

~~~sql
SELECT d.*
FROM documents d
WHERE d.id = :id
  AND d.tenant_id = :verified_tenant
  AND (
      d.owner_user_id = :verified_actor
      OR EXISTS (
          SELECT 1
          FROM document_grants g
          WHERE g.document_id = d.id
            AND g.grantee_user_id = :verified_actor
            AND g.permission = 'READ'
            AND g.revoked_at IS NULL
            AND (g.expires_at IS NULL OR g.expires_at > :now)
      )
  );
~~~

Đọc điều kiện từ ngoài vào:
- `d.id=:id` áp dụng cho mọi nhánh quyền.
- `d.tenant_id=:verified_tenant` cũng áp dụng cho cả owner và share.
- Trong ngoặc, owner **hoặc** có grant READ hợp lệ.
- `EXISTS` không nhân bản document nếu có nhiều grant.
- Thời hạn grant được tính bằng đồng hồ server, không dùng tham số thời gian do client tự khai.
- Quyền READ không tự đồng nghĩa WRITE/DELETE; nếu business định nghĩa permission hierarchy phải biểu diễn tường minh.

Grant phải gắn với đúng object, actor, hành động và hiệu lực; không chỉ kiểm tra actor đã từng có một quyền trên *bất kỳ* document nào.

## 7. Spring Data JPA @Query với EXISTS

Giả định entity `DocumentGrant` có property `document` liên kết `Document`, `granteeUserId`, `permission`, `revokedAt` và `expiresAt`:

~~~java
import java.time.Instant;
import java.util.Optional;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;

public interface DocumentRepository extends JpaRepository<Document, Long> {

    @Query("""
        select d
        from Document d
        where d.id = :id
          and d.tenantId = :tenant
          and (
              d.ownerUserId = :actor
              or exists (
                  select g.id from DocumentGrant g
                  where g.document = d
                    and g.granteeUserId = :actor
                    and g.permission = 'READ'
                    and g.revokedAt is null
                    and (g.expiresAt is null or g.expiresAt > :now)
              )
          )
        """)
    Optional<Document> findReadableById(
            @Param("id") Long id,
            @Param("tenant") String tenant,
            @Param("actor") String actor,
            @Param("now") Instant now);
}
~~~

JPQL dùng **tên entity/property Java**, không phải table/column name. Trong dự án thật, mapping của `DocumentGrant.document` và các property phải có thật, phương thức trả `Optional`, các tham số dùng `@Param` nhất quán. Đây là snippet tích hợp với JPA, không phải Java standalone.

Service gọi:

~~~java
@PreAuthorize("isAuthenticated() and hasAuthority('document:read')")
@Transactional(readOnly = true)
public DocumentDto readVisible(Long id) {
    VerifiedActor actor = actorResolver.requireCurrentActor();
    if (id == null || id <= 0) {
        throw new IllegalArgumentException("Invalid ID");
    }
    Document d = repository.findReadableById(
            id, actor.tenantId(), actor.userId(), clock.instant())
            .orElseThrow(ResourceNotFoundException::new);
    return mapper.toDto(d);
}
~~~

Snippet giả định service đã được inject `clock: Clock`, `repository`, `actorResolver` và `mapper`. Dùng đồng hồ server rõ ràng giúp test grant hết hạn dễ hơn. `EXISTS` thích hợp cho detail vì ta chỉ cần biết có grant phù hợp hay không; dùng JOIN có thể nhân bản dòng khi nhiều grant và cần chú ý DISTINCT/count.

## 8. Dấu ngoặc OR là một phần của cơ chế bảo mật

Đoạn sai:

~~~sql
WHERE d.id = :id
  AND d.tenant_id = :tenant
  AND d.owner_user_id = :actor
  OR EXISTS (
      SELECT 1 FROM document_grants g
      WHERE g.document_id = d.id
        AND g.grantee_user_id = :actor
  )
~~~

Do `AND` ưu tiên hơn `OR`, điều kiện tương đương:

~~~text
(id=requested AND tenant=verified AND owner=actor)
OR (hasSomeGrantForActorOnThisRow)
~~~

Nhánh share không còn ràng buộc ID hoặc tenant. Query trả về có thể gồm document **khác ID được hỏi**, thậm chí khác tenant nếu dữ liệu grant và các guard không đủ.

Đoạn đúng:

~~~sql
WHERE d.id = :id
  AND d.tenant_id = :tenant
  AND (
      d.owner_user_id = :actor
      OR EXISTS (...)
  )
~~~

Với một nhánh admin, điều kiện hợp lý có thể là:

~~~text
id AND verifiedTenant AND
    (owner OR validShare OR trustedTenantAdminPermission)
~~~

Không viết `id AND tenant OR admin`, vì admin branch sẽ bỏ luôn rào cản ID và tenant. Cờ admin phải do security context/policy service xác định, không lấy từ request như `?admin=true`.

Trong code review, vẽ cây logic hoặc viết test đối kháng để chứng minh mỗi nhánh OR đều ở dưới các điều kiện bắt buộc.

## 9. Quyền theo project, nhóm hoặc tổ chức

Nếu tài liệu thuộc một project mà người dùng có quyền READ, phạm vi có thể được xác định qua membership:

~~~sql
SELECT d.*
FROM documents d
WHERE d.id = :id
  AND d.tenant_id = :tenant
  AND (
      d.owner_user_id = :actor
      OR EXISTS (
          SELECT 1 FROM project_memberships m
          WHERE m.project_id = d.project_id
            AND m.tenant_id = d.tenant_id
            AND m.user_id = :actor
            AND m.can_read_documents = TRUE
            AND m.revoked_at IS NULL
      )
  );
~~~

Bảng `project_memberships` là domain model minh họa, không phải bảng Spring mặc định. Quy tắc membership phải được xác minh tại thời điểm truy vấn, không nhận một danh sách project ID tự khai trong request rồi coi đó là quyền.

Nếu project có role như VIEWER/EDITOR nhưng một document bị legal hold hoặc confidential override, cần thêm business predicate. Khi mô hình nhóm lồng nhiều cấp và quan hệ phức tạp, có thể dùng ACL hoặc policy engine/ReBAC, nhưng vẫn giữ ranh giới tenant và ID rõ ràng.

Cần thống nhất: nếu actor rời project, cache membership có bao lâu để cập nhật? Một token có project role cũ có thể làm quyết định stale; phải có expiry/revocation phù hợp rủi ro.

## 10. Quyền public là một nhánh chính sách tường minh

Có thể cho phép tài liệu được công khai qua cờ được quản lý:

~~~sql
AND (
    d.owner_user_id = :actor
    OR EXISTS (...validShare...)
    OR d.visibility = 'PUBLIC'
)
~~~

Nhưng một tài liệu public có thể vẫn bị giới hạn bởi status PUBLISHED, expiry hoặc ràng buộc tenant. Nếu sản phẩm cho phép public cross-tenant, phải thiết kế ranh giới riêng, không tự thêm `OR visibility='PUBLIC'` vào mọi truy vấn private.

**Không đồng nhất null với public.** Các anti-pattern như `owner_user_id IS NULL` hoặc `tenant_id IS NULL` làm điều kiện public có thể biến lỗi dữ liệu thành truy cập mở.

Shared link qua token bí mật cũng là một chính sách khác: token cần đủ entropy, expiry, revoke và bảo vệ replay theo yêu cầu; một chuỗi do client gửi không tự có quyền nếu chưa được xác minh.

## 11. 404, 403 và tránh rò rỉ sự tồn tại tài nguyên

Khi `findReadableById` trả empty, có thể do:
- ID không tồn tại.
- ID tồn tại ngoài tenant.
- ID thuộc tenant nhưng actor không phải owner.
- Không có share hợp lệ.
- Share hết hạn/bị thu hồi.
- Trạng thái document không cho phép đọc.

Với API dữ liệu riêng, thường có thể trả **404** cho tài nguyên ngoài tập được phép nhìn thấy để không xác nhận sự tồn tại của ID. `403` phù hợp nếu policy chủ đích từ chối và việc tiết lộ đối tượng/nhóm không gây rủi ro; yêu cầu chuẩn hóa có thể khác nhau giữa các sản phẩm.

Các trường hợp thường gặp:
- Chưa xác thực → 401/challenge hoặc login redirect tùy authentication stack.
- Thiếu authority chức năng → 403.
- ID không tìm thấy trong **scope được phép** → 404.
- Database/permission backend lỗi → lỗi hạ tầng phù hợp (thường 5xx), **không thực hiện hành động**.

Đừng chạy lại `repository.findById(id)` không scoped để trả cho user một message “document tồn tại nhưng thuộc Bình”, vì chính câu trả lời đó đã tiết lộ dữ liệu.

Nếu vận hành cần biết vì sao bị từ chối, ghi audit với actor/correlation ID và reason code an toàn; không đẩy owner/tenant hoặc thông tin nội dung chưa được phép ra API response.

## 12. Query khi READ không đồng nghĩa quyền WRITE

Một user có grant READ không được tự động quyền sửa. Đừng dùng `findReadableById` trong service ghi rồi gọi `document.rename(...)`.

Với owner-only WRITE:

~~~java
@PreAuthorize("isAuthenticated() and hasAuthority('document:write')")
@Transactional
public void renameOwned(Long id, String newTitle) {
    VerifiedActor actor = actorResolver.requireCurrentActor();

    if (newTitle == null || newTitle.isBlank()) {
        throw new IllegalArgumentException("Invalid title");
    }

    Document d = repository.findByIdAndTenantIdAndOwnerUserId(
            id, actor.tenantId(), actor.userId())
            .orElseThrow(ResourceNotFoundException::new);

    d.rename(newTitle);
}
~~~

Đây là snippet tích hợp Spring/JPA. `Document.rename` là logic domain, JPA dirty checking dựa trên entity managed trong transaction. Nếu non-owner được grant WRITE, hãy tạo query/policy **cho WRITE** tương tự, không reuse predicate permission READ.

Ngoài object policy, có thể phải kiểm tra status LOCKED, DRAFT hoặc quyền của người được ủy quyền, kể cả khi owner.

## 13. UPDATE có điều kiện: kiểm tra quyền cùng câu lệnh ghi

Một phương án owner-only là làm UPDATE với predicate `ID + tenant + owner + version` trong cùng câu lệnh. Spring Data JPA:

~~~java
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Modifying;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;

public interface DocumentWriteRepository
        extends JpaRepository<Document, Long> {

    @Modifying
    @Query("""
        update Document d
           set d.title = :title,
               d.version = d.version + 1
         where d.id = :id
           and d.tenantId = :tenant
           and d.ownerUserId = :actor
           and d.version = :expectedVersion
        """)
    int renameOwnedIfVersionMatches(
            @Param("id") Long id,
            @Param("tenant") String tenant,
            @Param("actor") String actor,
            @Param("title") String title,
            @Param("expectedVersion") long expectedVersion);
}
~~~

Giả định `Document.version` là numeric version và property map phù hợp. Đây là **code repository tích hợp**, cần chạy trong transaction ghi ở service.

- Return `int` biểu diễn số row bị update.
- `1` cho biết có một document thỏa toàn bộ điều kiện.
- `0` có thể là không có ID, sai tenant/owner hoặc version cũ; không coi là thành công.
- `>1` là bất thường với ID unique, cần xử lý lỗi/query integrity.
- JPQL bulk update không tự áp dụng optimistic-lock checking và lifecycle callbacks như một managed entity update; ví dụ chủ động dùng `d.version = :expectedVersion` và `d.version = d.version+1`.
- `@Modifying` chỉ có tác dụng với query method khai báo `@Query`; bulk query có thể để entities đang managed ở trạng thái stale. Không bật `clearAutomatically` tùy tiện nếu persistence context có thay đổi chưa flush.

Ở service:

~~~java
int updated = writeRepository.renameOwnedIfVersionMatches(
        id, actor.tenantId(), actor.userId(), title, expectedVersion);

if (updated != 1) {
    throw new ResourceNotFoundOrConflictException();
}
~~~

Exception ở đây là kiểu ứng dụng. Để trả chính xác 404/409 mà không rò dữ liệu, cần policy riêng: `0` không tự chứng minh chỉ có stale version. Quan trọng là không trả 204 success khi không có row nào được đổi.

## 14. WRITE được chia sẻ phải có predicate riêng

Khi policy cho người được grant WRITE sửa document:

~~~sql
UPDATE documents
SET title = :title
WHERE id = :id
  AND tenant_id = :tenant
  AND (
      owner_user_id = :actor
      OR EXISTS (
          SELECT 1 FROM document_grants g
          WHERE g.document_id = documents.id
            AND g.grantee_user_id = :actor
            AND g.permission = 'WRITE'
            AND g.revoked_at IS NULL
            AND (g.expires_at IS NULL OR g.expires_at > :now)
      )
  );
~~~

Đây là SQL minh họa, có thể cần điều chỉnh tên bảng/kiểu tham số/alias theo database dialect thực tế. Nếu cần optimistic concurrency, thêm version guard/increment.

Không bao giờ dùng `permission='READ'` cho UPDATE chỉ vì user có thể mở trang chỉnh sửa. Nếu WRITE bao hàm READ theo business contract, hãy xác định rõ chiều kế thừa; không mặc định DELETE/SHARE cũng theo WRITE.

Nếu permission được lưu ở một service ACL ngoài DB, không thể dùng cùng `EXISTS` SQL trừ khi có permission index trong DB. Khi đó cần service guard trước mutation, transactional consistency/capability expiry và một cơ chế fail-closed khi permission backend không khả dụng.

## 15. TOCTOU: giữa kiểm tra và thực hiện

Time-of-check/time-of-use:
~~~text
T1: user có quyền WRITE document 42
T2: admin thu hồi grant
T3: user cập nhật document 42
~~~

Nếu kiểm tra ở T1 nhưng update ở T3 qua `save(entity)` không scoped, rủi ro quyền bị thu hồi giữa hai thời điểm.

Một câu UPDATE với `EXISTS` permission trong cùng DB rút ngắn khoảng cách check–write, song isolation và các transaction đồng thời vẫn cần được đánh giá. Nếu quyền nằm ngoài database, cache hoặc IAM service, điều kiện này khó hơn.

Giải pháp tùy mức rủi ro:
1. Kiểm tra quyền sát thời điểm ghi và cùng transaction phù hợp.
2. Dùng conditional UPDATE với scoped predicate, expected version hoặc locking khi cần.
3. Đảm bảo grant/revoke có cơ chế invalidation và audit đúng.
4. Với tác vụ cực nhạy cảm, xác minh lại trước khi side effect không thể rollback hoặc dùng capability có expiry/revocation cụ thể.
5. Không nuốt `AccessDeniedException` rồi cho transaction tiếp tục commit các thay đổi khác.

`@Transactional` không phải authorization, cũng không tự đảm bảo mọi thứ nhất quán nếu có external permission service; chọn isolation/ràng buộc theo hậu quả thực tế.

## 16. Xóa theo ID phải có DELETE policy

Đoạn `repository.deleteById(id)` gọi từ endpoint nhận ID bất kỳ là nguy hiểm nếu không có guard. DELETE có thể cần:
- Authority `document:delete`.
- ID, tenant, owner hoặc explicit DELETE grant.
- Kiểm tra legal hold, lifecycle, retention.
- Transaction/cascade/outbox/file cleanup, invalidate ACL/cache.
- Audit người thực hiện.

Một hướng là load entity qua query **được phép xóa**, check trạng thái rồi remove managed entity. Hướng khác là conditional DELETE theo `WHERE id AND tenant AND owner/version`, kiểm tra row count và xử lý lifecycle theo đặc tính DB.

Bulk JPQL delete có thể bỏ qua entity callbacks và semantics cascade kiểu managed remove. Nếu tài liệu có attachments/audit/outbox, đừng chọn bulk delete chỉ vì ít câu SQL hơn.

## 17. Null hoặc scope thiếu: không làm guard thành optional

Một anti-pattern phổ biến ở form tìm kiếm:

~~~sql
WHERE d.id = :id
  AND (:tenant IS NULL OR d.tenant_id = :tenant)
  AND (:actor IS NULL OR d.owner_user_id = :actor)
~~~

Đây là cách viết optional filters có thể phù hợp cho giao diện admin được bảo vệ riêng, nhưng **không** phù hợp làm authorization guard cho user data. Khi actor/tenant null, predicate mất hiệu lực và có thể trả bất kỳ record nào khớp ID.

Với data authorization, những scope bắt buộc phải là **required**:
- Không có actor → deny/challenge, không “all users”.
- Không có tenant → deny, không dùng tenant mặc định.
- Owner không tồn tại → không tự công khai document.
- Permission backend lỗi/null → không cấp quyền, xử lý lỗi có kiểm soát.
- Resource ID không hợp lệ → validate input trước query.
- Header/body tự khai owner/tenant → không thay danh tính đã xác thực.

SQL NULL có ba trạng thái logic; không dựa vào hành vi `NULL = NULL` làm policy chính. Validate rõ và giữ predicate an toàn.

## 18. Java 17 độc lập: kiểm tra ID + tenant + (owner OR share)

Ví dụ sau **chạy bằng JDK 17 trở lên, không cần Spring**. Nó mô phỏng kết quả một truy vấn scoped: mỗi document phải khớp ID, tenant, rồi mới kiểm tra owner hoặc danh sách grant. Trong production, share phải lấy từ cơ sở dữ liệu hoặc policy đáng tin, không từ client.

Tạo file `ScopedLookupDemo.java`:

~~~java
import java.util.List;
import java.util.Optional;
import java.util.Set;

public class ScopedLookupDemo {
    record Actor(String id, String tenant, Set<Long> sharedIds) { }
    record Document(long id, String tenant, String owner, String title) { }

    static Optional<Document> findReadable(
            List<Document> docs, Actor actor, long requestedId) {

        if (actor == null || requestedId <= 0
                || actor.id() == null || actor.id().isBlank()
                || actor.tenant() == null || actor.tenant().isBlank()
                || actor.sharedIds() == null) {
            return Optional.empty();
        }

        return docs.stream()
                .filter(d -> d.id() == requestedId)
                .filter(d -> d.tenant().equals(actor.tenant()))
                .filter(d -> d.owner().equals(actor.id())
                        || actor.sharedIds().contains(d.id()))
                .findFirst();
    }

    static String lookup(List<Document> docs, Actor actor, long id) {
        return findReadable(docs, actor, id)
                .map(Document::title)
                .orElse("NOT_FOUND");
    }

    public static void main(String[] args) {
        List<Document> docs = List.of(
                new Document(1, "south", "thao", "SouthSecret"),
                new Document(1, "north", "an", "NorthDraft"),
                new Document(2, "north", "chi", "SharedReport"),
                new Document(3, "north", "chi", "PrivateNote"),
                new Document(4, "south", "thao", "SouthOnly")
        );
        Actor an = new Actor("an", "north", Set.of(2L));
        Actor afterRevoke = new Actor("an", "north", Set.of());

        System.out.println("owner=" + lookup(docs, an, 1L));
        System.out.println("shared=" + lookup(docs, an, 2L));
        System.out.println("unshared=" + lookup(docs, an, 3L));
        System.out.println("wrong-tenant=" + lookup(docs, an, 4L));
        System.out.println("missing-actor=" + lookup(docs, null, 1L));
        System.out.println("after-revoke="
                + lookup(docs, afterRevoke, 2L));
    }
}
~~~

Lệnh:

~~~bash
javac ScopedLookupDemo.java
java ScopedLookupDemo
~~~

Stdout chính xác:

~~~text
owner=NorthDraft
shared=SharedReport
unshared=NOT_FOUND
wrong-tenant=NOT_FOUND
missing-actor=NOT_FOUND
after-revoke=NOT_FOUND
~~~

Document ID 1 xuất hiện ở cả south và north. Mặc dù `SouthSecret` xuất hiện trước trong list, predicate tenant vẫn chọn đúng `NorthDraft`. An được READ document 2 nhờ share; document 3 không chia sẻ, ID 4 ở tenant khác, thiếu actor hoặc grant bị thu hồi đều không trả dữ liệu.

Demo dùng list/stream để minh họa logic, không xác minh actor/tenant, không có persistence, concurrency hoặc grant expiry. Ứng dụng thật phải lấy ID actor/tenant từ nguồn xác thực và dùng database query để lọc trước khi load/serialize.

## 19. Vì sao lọc tại query tốt hơn @PostFilter cho detail/list?

Method security có `@PreAuthorize`, `@PostAuthorize`, `@PreFilter` và `@PostFilter`, nhưng không phương thức nào tự thêm `tenant_id=:tenant AND owner_id=:actor` vào mọi repository query.

- `@PreAuthorize` chặn authority/function trước khi gọi method; nếu cần object policy có thể gọi một policy bean. Lời gọi phải đi qua Spring proxy.
- `@PostAuthorize` đánh giá sau khi method chạy; với write, side effect có thể đã xảy ra.
- `@PostFilter` lọc collection sau khi dữ liệu đã được load; không phải SQL WHERE và có thể phá page/count.
- Query-time scoping khiến database chỉ trả row được phép, giúp detail/list/export và count bám cùng predicate.

Có thể kết hợp nhiều lớp: HTTP authentication, method authority, service trusted actor, scoped repository, domain ACL, database RLS nếu đã cấu hình. **Defense in depth** tốt hơn việc chỉ dựa vào một controller có annotation.

Nếu dùng RLS của PostgreSQL hoặc DB tương ứng, phải set/reset tenant/user context an toàn với connection pool và transaction, tránh rò context giữa request. Không mặc định RLS hoạt động chỉ vì schema có policy.

## 20. List, count và search cần cùng điều kiện quyền

Lỗi hay gặp:

~~~text
GET /documents/42 --> scoped, an toàn
GET /documents    --> findAll(), rò dữ liệu
GET /documents/export --> raw query, rò dữ liệu
GET /documents/count  --> đếm cả record ngoài quyền
~~~

Với list, dùng cùng predicate:

~~~sql
SELECT d.*
FROM documents d
WHERE d.tenant_id = :tenant
  AND (
      d.owner_user_id = :actor
      OR EXISTS (
          SELECT 1 FROM document_grants g
          WHERE g.document_id = d.id
            AND g.grantee_user_id = :actor
            AND g.permission = 'READ'
            AND g.revoked_at IS NULL
      )
  )
ORDER BY d.id
LIMIT :size OFFSET :offset;
~~~

Thực tế bổ sung expiry/status nếu chính sách yêu cầu. `countQuery` phải dùng **cùng điều kiện**; không lấy 20 bản ghi rồi lọc Java còn 3 và trả total count từ toàn DB.

Có thể tái sử dụng predicate qua `Specification`/Criteria API hoặc query builder được test, thay vì copy-paste SQL vào mỗi endpoint. Tối ưu index cho owner, tenant, grant, membership, dùng `EXPLAIN` trên DB thật. Không bỏ scope filter chỉ vì query chậm.

## 21. Vai trò của index và hiệu năng

- Với global PK, index `documents(id)` có thể đủ cho detail lookup rồi DB kiểm tra tenant/owner trên row.
- Với tenant-local key, unique/index `(tenant_id, id)` quan trọng.
- Với list theo owner, cân nhắc `(tenant_id, owner_user_id, id)`.
- Với grant, index theo `document_id, grantee_user_id, permission` và điều kiện revoked/expiry tùy workload.
- Với project membership, index theo project/user/tenant phù hợp.

`EXISTS` giúp tránh duplicate row do nhiều grants. Với dữ liệu lớn, dùng query plan và số liệu thực (latency, row count, cardinality) để chọn index. Đừng tạo index tùy tiện trên mọi cột mà không đo write cost.

Một permission service bên ngoài làm N+1 lookups cho mỗi document có thể quá chậm cho list; lúc đó cần batch policy hoặc authorized-view index với invalidation đúng. Hiệu năng không phải lý do được bỏ kiểm tra quyền.

## 22. Những tình huống chuyển trạng thái và đổi scope

Chuyển owner: owner cũ còn READ nhờ share không, owner mới có quyền nào, grants cũ có phải thu hồi? Chuyển tenant: cần quyền ở cả tenant nguồn và tenant đích, ACL/cache/grants và những membership cũ phải được chuyển hoặc thu hồi theo policy.

Không chỉ đổi `tenant_id` rồi giữ nguyên grant của người ngoài tenant khi business không cho phép. Với resource đã move, query scoped tenant cũ phải không còn trả dữ liệu sau khi thay đổi thành công. Đây là một sự kiện security, cần audit và test.

Xóa/restore/copy cũng có ảnh hưởng: một bản copy mới không nên tự tái sử dụng grant của object cũ nếu không được phép. Một ID bị tái sử dụng sau xóa có thể hồi sinh ACL/grants cũ nếu lifecycle không được quản lý.

## 23. Ma trận test truy vấn theo ID và phạm vi

| Trường hợp | Kỳ vọng |
|---|---|
| Owner cùng tenant, authority đúng | Có dữ liệu |
| Không phải owner, không có share | Không có dữ liệu |
| Đúng ID nhưng tenant khác | Không có dữ liệu |
| Hai tenant có ID cục bộ trùng | Trả đúng tài nguyên tenant actor, không rò tenant kia |
| Có grant READ đúng object | Có dữ liệu |
| Có READ nhưng gọi WRITE | Deny, không mutate |
| Grant khác object ID | Không trả nhầm object được grant |
| Grant expired/revoked | Không có dữ liệu |
| Đúng group nhưng membership bị thu hồi | Không có dữ liệu |
| Thiếu actor hoặc tenant | Không cấp |
| Sai authority chức năng | Method boundary từ chối |
| Dấu ngoặc OR sai | Test phải phát hiện rò object khác ID/tenant |
| Có user-controlled owner/tenant | Không được dùng thay verified scope |
| UPDATE owner-only sai scope | Row count 0, không đổi DB |
| UPDATE version stale | Row count 0 hoặc conflict theo contract |
| Permission backend outage | Không side effect |
| List/count/export | Scope giống detail |
| Direct service call/message consumer | Query/service authorization vẫn áp dụng |

Kiểm thử qua Spring Data repository và integration với database sản xuất tương đương; không chỉ assert HTTP status. Cần xác minh dữ liệu thực không bị đổi khi denied, số bản ghi trên page/count đúng và không có event/download nào lộ dữ liệu.

Ví dụ test có thể dùng `@SpringBootTest`/test slice tương ứng, custom principal cho tenant claim, Testcontainers nếu SQL dialect quan trọng. `@WithMockUser` đơn thuần không tự tạo tenant claim của ứng dụng. Test service qua Spring bean proxy thực, không chỉ object tạo bằng `new`, nếu dựa vào method security.

## 24. Lỗi phổ biến cần loại bỏ

**1. `findById` rồi return ngay.** Đúng ID không có nghĩa đúng quyền. Thay bằng query scoped hoặc kiểm tra object policy bắt buộc trước khi xuất dữ liệu.

**2. Tin `ownerId`/`tenantId` do client gửi.** Một user có thể giả chủ sở hữu. Lấy scope từ authentication đã xác minh.

**3. `AND/OR` không có ngoặc.** Nhánh share/admin có thể bỏ rào cản ID/tenant. Test với grant trên document khác và tenant khác.

**4. Reuse READ cho WRITE/DELETE.** Tên quyền phải đúng hành động, không suy luận WRITE khi có READ.

**5. Quyền share không check expiry/revoke.** Grant cũ trở thành quyền vĩnh viễn. Dùng thời gian server và trạng thái có hiệu lực.

**6. `(:tenant IS NULL OR ...)` trong security query.** Thiếu scope làm query rộng ra. Với actor/user data, scope là required.

**7. Trả 200/204 khi UPDATE ảnh hưởng 0 dòng.** Caller tưởng sửa thành công; kiểm tra row count và xử lý bảo mật/concurrency.

**8. Bulk update bỏ qua version/lifecycle.** Thiết kế version predicate và mutation, không giả định dirty checking áp dụng.

**9. Chỉ bảo vệ detail, quên list/export/count/download.** Mọi đường dữ liệu phải sử dụng cùng phạm vi.

**10. Chỉ dựa vào HTTP filter.** Message, async, scheduler và direct service call có thể không qua HTTP; service/query vẫn phải bảo vệ.

**11. `@PostFilter` thay SQL predicate.** Dữ liệu đã load, pagination/count sai. Query-time scoping khi có thể.

**12. ACL service không khả dụng thì cho qua.** Fail-open. Hãy dừng hành động và báo lỗi kiểm soát.

## 25. Checklist trước khi merge

- [ ] Query theo ID luôn ràng buộc tenant đã xác minh.
- [ ] Owner hoặc allowed scope được tính từ dữ liệu server, không từ request tự khai.
- [ ] Dấu ngoặc OR áp dụng bên trong điều kiện ID/tenant bắt buộc.
- [ ] Authority hành động và object permission được phân biệt.
- [ ] Share/grant gắn đúng object/action và còn hiệu lực.
- [ ] Thiếu actor/tenant/ACL/backend lỗi đều fail closed.
- [ ] Không serialize/log record ngoài quyền trước guard.
- [ ] READ/WRITE/DELETE có predicate phù hợp; không reuse nhầm.
- [ ] UPDATE/DELETE có row count, transaction và version guard theo yêu cầu.
- [ ] List/count/search/export/download dùng cùng scope policy.
- [ ] Có test sai ID, wrong owner, wrong tenant, expired/revoked grant và OR precedence.
- [ ] Method security được bật và lời gọi đi qua Spring proxy.
- [ ] Đã đánh giá performance/index và quyền khi resource chuyển owner/tenant.
- [ ] Mã lỗi 401/403/404/5xx không để lộ object ngoài quyền.

**Kết luận:** Đối với tài nguyên riêng, predicate `ID = requestedId AND tenant = verifiedTenant AND (owner = verifiedActor OR validAllowedScope)` là một lớp bảo vệ dữ liệu thiết yếu chống BOLA/IDOR. Kết hợp nó với authentication, method security, kiểm tra quyền theo hành động, transaction có điều kiện và kiểm thử xuyên các điểm vào để không chỉ bảo vệ một controller mà bảo vệ đúng mỗi object.

## Tài liệu tham khảo

- [Spring Data JPA – JPA Query Methods](https://docs.spring.io/spring-data/jpa/reference/jpa/query-methods.html): derived query, `@Query`, bind parameters, modifying queries.
- [Spring Data JPA – Query Methods Details](https://docs.spring.io/spring-data/jpa/reference/repositories/query-methods-details.html): cú pháp tên method và reserved methods.
- [Spring Data JPA – Modifying](https://docs.spring.io/spring-data/data-jpa/reference/api/java/org/springframework/data/jpa/repository/Modifying.html): bulk UPDATE/DELETE và persistence context.
- [Spring Security – Method Security](https://docs.spring.io/spring-security/reference/servlet/authorization/method-security.html): `@EnableMethodSecurity`, `@PreAuthorize` và interceptor.
- [OWASP API Security Top 10 (2023) – BOLA](https://owasp.org/API-Security/editions/2023/en/0xa1-broken-object-level-authorization/): phân quyền theo object ID.
- [PostgreSQL – Row Security Policies](https://www.postgresql.org/docs/current/ddl-rowsecurity.html): RLS bổ trợ nếu sử dụng PostgreSQL.
