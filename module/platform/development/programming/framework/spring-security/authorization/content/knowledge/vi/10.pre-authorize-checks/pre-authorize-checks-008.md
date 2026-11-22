# Kết hợp role với quyền sở hữu tài nguyên

## 1. Bài toán: cùng role nhưng không cùng quyền trên một object

Trong Spring Security, một người dùng có thể có role hoặc permission hợp lệ mà vẫn **không được phép** đọc, sửa, xóa một tài nguyên cụ thể. Role mô tả trách nhiệm và quyền chức năng; quyền sở hữu mô tả quan hệ giữa **một principal** và **một bản ghi**.

Giả sử hệ thống tài liệu có:

- Alice là chủ sở hữu tài liệu 42 trong tenant A; có quyền `document:read` và `document:update`.
- Bob cũng có `document:read`, thuộc tenant A, nhưng không sở hữu tài liệu 42.
- Carol là quản trị viên tenant A, có `ROLE_TENANT_ADMIN` và quyền `document:read`.
- David là quản trị viên tenant B, có cùng tên role và permission như Carol.

Nếu service chỉ kiểm tra:

```java
@PreAuthorize("hasAuthority('document:read')")
public DocumentView read(UUID documentId) {
    // ...
}
```

thì cả bốn người có thể vượt qua **kiểm tra quyền chức năng**, dù Bob chưa được chia sẻ tài liệu, và David thuộc tenant khác. Nếu code phía dưới dùng `findById(documentId)` không giới hạn tenant/owner, đây là nguy cơ Broken Object Level Authorization (BOLA), còn được gọi là IDOR trong nhiều ngữ cảnh.

Giải pháp là kết hợp nhiều loại điều kiện **trước khi phương thức thực thi**:

```text
ALLOW_READ(document, actor) =
   authenticated
   AND activeAccount
   AND has(document:read)
   AND sameTenant(actor, document)
   AND (
        isOwner(actor, document)
        OR hasValidReadShare(actor, document)
        OR isTenantAdmin(actor)
   )
```

Điều kiện `sameTenant` được áp dụng cho **mọi nhánh trong ngoặc**. Vì thế David không thể đọc tài liệu tenant A chỉ nhờ có role admin của tenant B. Nếu hệ thống có global admin thực sự, ngoại lệ ấy phải được định nghĩa riêng với kiểm soát tăng cường, không được vô tình xuất hiện qua một phép OR.

**Mục tiêu của bài:** hiểu role/authority, ownership, tenant và trạng thái; viết `@PreAuthorize` an toàn; tách logic policy bean; xử lý TOCTOU khi dữ liệu thay đổi; và kiểm thử cả các trường hợp bị từ chối.

### Sơ đồ các lớp bảo vệ

```text
HTTP API / Web / GraphQL / Job
              |
              v
    Authentication đã xác minh
              |
              v
      @PreAuthorize
       role / authority
       + object policy
              |
          +---+---+
          |       |
         DENY    ALLOW
                  |
                  v
           Service method
                  |
                  v
           Repository / DB
        tenant-scoped query
        conditional update
        version / transaction
```

Request matcher ở tầng HTTP giúp phân loại đường dẫn/hành động. Method security gắn policy với một use case được gọi từ nhiều entrypoint. Repository và transaction tiếp tục bảo vệ dữ liệu tại thời điểm thực thi. Không lớp nào được giả định thay thế toàn bộ lớp còn lại.

## 2. Khái niệm: role, permission, owner, tenant và ACL

### 2.1. Role / authority

Một role như `ROLE_USER`, `ROLE_EDITOR` hoặc `ROLE_TENANT_ADMIN` thường xác định chức năng mà user được giao. Trong Spring Security, role được biểu diễn bằng `GrantedAuthority`; theo tiền tố mặc định:

```java
hasRole('ADMIN')                  // yêu cầu ROLE_ADMIN
hasRole('TENANT_ADMIN')           // yêu cầu ROLE_TENANT_ADMIN
hasAuthority('ROLE_TENANT_ADMIN') // tên authority chính xác
hasAuthority('document:read')     // permission chính xác
```

Đừng tự suy ra `SCOPE_documents.read` trong JWT giống với `document:read`. Việc chuyển đổi scope/claim sang authority phải được thiết kế rõ và dựa vào token đã xác minh issuer, signature, audience và thời hạn.

**Role hierarchy** có thể mở rộng tập authority có thể đạt tới: ví dụ `ROLE_ADMIN > ROLE_EDITOR`. Nhưng role hierarchy không biết document nào của Alice và cũng không biết membership tenant của Carol. Phải kết hợp với quan hệ tài nguyên thật.

### 2.2. Ownership

Ownership thường được mô tả bằng một trường trong DB:

```text
documents.owner_id == verifiedActor.userId
```

Tùy hệ thống, ownership có thể phức tạp: tài liệu thuộc một team, nhiều người đồng sở hữu, owner được chuyển giao, tài nguyên thuộc tổ chức, hoặc quyền được ủy quyền có thời hạn. Vì vậy điều kiện quyền theo object cần phản ánh **mô hình dữ liệu** chứ không chỉ so `authentication.name` với một chuỗi do client gửi.

Một user có thể là owner nhưng tài khoản inactive, đã bị thu hồi quyền, hoặc document bị khóa. Owner không nhất thiết có toàn bộ quyền read, edit, approve, delete; đây là quyết định chính sách.

### 2.3. Tenant / organization / project

Tenant là ranh giới phạm vi dữ liệu. Khi principal thuộc nhiều tenant, ứng dụng có thể cho phép chọn “tenant hiện hành”, nhưng phải **xác minh membership** trước khi dùng lựa chọn đó để truy vấn.

Ví dụ admin tenant A không mặc nhiên quản lý tenant B. Tên role giống nhau không đủ diễn đạt scope. Có thể cần tenant-scoped grants, mapping theo tổ chức hoặc policy server-side kiểm tra membership.

### 2.4. Sharing và ACL

Một document có thể được chia sẻ cho Bob bằng ACL:

```text
document=42, recipient=bob, permission=READ, expiresAt=...
```

Chia sẻ quyền đọc không đồng nghĩa được sửa hoặc xóa. ACL cần kiểm tra trạng thái revoke, thời hạn, tenant và nguồn người cấp quyền. Không dùng Boolean `shared=true` do client tự khai để thay thế việc tra bảng chia sẻ.

### 2.5. Trạng thái tài nguyên

Tài liệu `DRAFT` có thể được chỉnh sửa, nhưng `APPROVED` hoặc `LOCKED` không được sửa dù người gọi là owner/admin. Đây là **business invariant**, không phải authority cố định.

| Điều kiện | Nguồn đáng tin | Phạm vi |
| --- | --- | --- |
| `ROLE_TENANT_ADMIN` | Authentication/authority mapper đã xác minh | Vai trò chức năng theo tenant |
| `document:read` | GrantedAuthority đã xác minh | Quyền đọc loại tài nguyên |
| `ownerId` | DB/domain model | Tài liệu cụ thể |
| `tenantId` | Membership + record trong DB | Ranh giới phạm vi |
| `sharePermission` | ACL/DB của ứng dụng | Quan hệ chia sẻ theo object |
| `status` / `version` | DB tại thời điểm xử lý | Tính hợp lệ và cạnh tranh dữ liệu |

## 3. Viết biểu thức đúng: AND, OR và dấu ngoặc

### 3.1. Trường hợp sai phổ biến

```java
@PreAuthorize(
    "hasRole('TENANT_ADMIN') or " +
    "@documentPolicy.isOwner(authentication, #documentId)"
)
```

Biểu thức này có thể cho phép **mọi người có ROLE_TENANT_ADMIN** vượt qua chốt owner, kể cả admin của tenant khác, nếu không có guard khác. Nó cũng có thể bỏ yêu cầu `document:read` hoặc trạng thái tài khoản.

Một lỗi khác:

```text
(has(document:read) AND sameTenant AND isOwner)
OR has(ROLE_TENANT_ADMIN)
```

Nhánh admin đứng ngoài tenant constraint. Nếu không có lý do nghiệp vụ đặc biệt, đây là cơ chế nâng quyền ngoài ý định.

### 3.2. Điều kiện đúng theo mục tiêu đã chọn

```text
has(document:read)
AND sameTenant
AND (isOwner OR sharedRead OR isTenantAdmin)
```

Với phép cập nhật:

```text
has(document:update)
AND sameTenant
AND (isOwner OR isTenantEditor)
AND document.status == DRAFT
```

Các dấu ngoặc làm rõ phạm vi của OR, còn tenant/permission/status là điều kiện chung. **Lựa chọn nhánh role cho admin không được làm mất các điều kiện chung.**

### 3.3. Khi admin được miễn permission chức năng?

Một tổ chức có thể yêu cầu admin được xem tài liệu trong tenant dù chưa có `document:read`. Khi đó chính sách phải diễn đạt ngoại lệ:

```text
sameTenant
AND (
      (has(document:read) AND (isOwner OR sharedRead))
      OR
      (has(ROLE_TENANT_ADMIN) AND adminReadAllowed)
    )
```

Trong đó `adminReadAllowed` là quy tắc cụ thể: có thể xét loại tài liệu, MFA/step-up, case support, audit, thời hạn hoặc hạn mức. Không nên biến role admin thành “cửa sau” trong mọi policy.

Một **global admin** nếu được phép vượt tenant phải là một cơ chế riêng, có điều kiện tăng cường và log, không được tạo ngầm bởi role tên ADMIN.

### 3.4. Bảng quyết định

| Người gọi | document:read | Cùng tenant | Owner/share | Tenant admin | Cho phép đọc? |
| --- | --- | --- | --- | --- | --- |
| Alice, owner | Có | Có | Có | Không | Có |
| Bob, được share | Có | Có | Có | Không | Có |
| User thường, không share | Có | Có | Không | Không | Không |
| Carol, admin tenant A | Có | Có | Không | Có | Có |
| David, admin tenant B | Có | **Không** | Không | Có | **Không** |
| Alice, quyền read đã bị thu hồi | Không | Có | Có | Không | **Không** |
| User thuộc tenant khác nhưng giả owner | Có | **Không** | Có (giả) | Không | **Không** |
| Anonymous | Không | Không | Không | Không | Không |

Đừng chỉ test hai dòng ALLOW; các dòng DENY là điều kiện thiết yếu để chứng minh không có lỗi OR hoặc thiếu tenant guard.

## 4. Dùng @PreAuthorize để chặn trước lời gọi service

### 4.1. Bật method security

Trong Spring Security Servlet 6.x, có thể khai báo:

```java
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;

@Configuration
@EnableMethodSecurity
public class MethodSecurityConfiguration {
}
```

`@EnableMethodSecurity` kích hoạt `@PreAuthorize`/`@PostAuthorize`/`@PreFilter`/`@PostFilter` theo mặc định. Chỉ cài Spring Security Starter không tự bật chốt method. `@Secured` và các annotation JSR-250 cần cờ riêng nếu dùng.

Khi một lời gọi đi qua Spring AOP proxy tới method có `@PreAuthorize`, interceptor dùng `Authentication` và tham số method để đánh giá biểu thức. Nếu denied, phương thức không được chạy qua đường intercepted đó.

### 4.2. Mẫu biểu thức tách permission và object policy

```java
@PreAuthorize(
    "hasAuthority('document:read') and " +
    "@documentPolicy.canRead(authentication, #documentId)"
)
public DocumentView readDocument(UUID documentId) {
    // ...
}
```

Các phần:

- `hasAuthority('document:read')` yêu cầu quyền chức năng.
- `@documentPolicy` là Spring bean tên `documentPolicy`.
- `authentication` là `Authentication` trong method-security evaluation context.
- `#documentId` tham chiếu argument method được bind theo tên.
- `canRead` kiểm tra owner/share/admin **trong tenant đã xác minh**.

Chỉ dùng một biểu thức ngắn ở annotation, còn logic dữ liệu đặt ở Java policy bean dễ unit test. Đây là **code minh họa tích hợp**, chưa phải chương trình Java standalone.

### 4.3. Đọc và sửa nên là hai policy riêng

```java
@PreAuthorize(
    "hasAuthority('document:read') and " +
    "@documentPolicy.canRead(authentication, #documentId)"
)
public DocumentView readDocument(UUID documentId) { ... }

@PreAuthorize(
    "hasAuthority('document:update') and " +
    "@documentPolicy.canEdit(authentication, #documentId)"
)
public void renameDocument(UUID documentId, String newName) { ... }
```

Được share READ không tự cho quyền UPDATE. Người có UPDATE nhưng document đã LOCKED cũng cần bị chặn. Với delete, approve, export, share hoặc transfer ownership, nên có policy riêng theo rủi ro.

### 4.4. Bind tham số SpEL chắc chắn

Spring Security có thể lấy tên tham số từ compiler flag `-parameters`, Spring Security `@P` hoặc một số metadata phù hợp. Ví dụ không phụ thuộc tên argument Java:

```java
import org.springframework.security.access.method.P;

@PreAuthorize(
    "hasAuthority('document:read') and " +
    "@documentPolicy.canRead(authentication, #documentId)"
)
public DocumentView readDocument(@P("documentId") UUID id) {
    return repository.readScoped(id);
}
```

`@P("documentId")` cho phép expression dùng `#documentId` dù argument trong Java tên `id`. Mã fragment này cần repository/bean/domain type thật, không tự chạy bằng `javac`. Nếu dùng tên Java trực tiếp, bật và kiểm tra `-parameters` trong bản build production.

### 4.5. Đừng gọi DB ba lần chỉ để kiểm một tài liệu

Biểu thức dài:

```java
@PreAuthorize(
    "@documentPolicy.sameTenant(authentication, #documentId) and " +
    "@documentPolicy.isOwner(authentication, #documentId) and " +
    "@documentPolicy.isEditable(#documentId)"
)
```

có thể khiến ba phương thức cùng tra DB và nhìn thấy những trạng thái khác nhau. Nếu thêm nhánh admin OR, độ phức tạp càng tăng. Hợp lý hơn:

```java
@PreAuthorize(
    "hasAuthority('document:update') and " +
    "@documentPolicy.canEdit(authentication, #documentId)"
)
```

Bean policy đọc một access projection phù hợp rồi kết hợp mọi điều kiện. Dù vậy, pre-check vẫn không khóa tài nguyên đến lúc cập nhật DB; cần transactional guard.

## 5. Thiết kế một policy bean an toàn

### 5.1. Đầu vào không được tin từ client

Request:

```http
PUT /api/documents/42 HTTP/1.1
Content-Type: application/json
X-User-Id: alice
X-Tenant-Id: tenant-A

{"ownerId":"alice","tenantId":"tenant-A","title":"changed"}
```

**Không có dòng nào ở trên chứng minh caller là Alice hoặc thuộc tenant A.** Header và body có thể được sửa bởi client. Nếu controller copy ownerId vào request attribute rồi policy đọc attribute ấy, nguồn dữ liệu vẫn chưa được xác thực.

Identity đến từ token/session/IdP đã xác minh, được chuyển thành `Authentication`. Nếu tenant được chọn từ request, hãy kiểm membership theo principal đã được xác minh và dùng tenant context server-side phù hợp.

### 5.2. Access facts và actor context

Một dự án có thể định nghĩa:

```java
record VerifiedActor(
    String userId, String tenantId,
    boolean active, Set<String> authorities
) {}

record DocumentAccessFacts(
    UUID id, String tenantId, String ownerId,
    Set<String> sharedReaders, String status, long version
) {}
```

Đây là **kiểu miền minh họa**. Cần implement `ActorResolver` theo hệ xác thực và `DocumentAccessRepository` theo database thật. Tên `VerifiedActor` chỉ hợp lý khi nó được tạo sau các bước xác minh danh tính/tenant, không chỉ gán tên theo request header.

### 5.3. Một policy bean với hai phương thức độc lập

Ví dụ **khung mã tích hợp Spring Boot 3 / Spring Security 6.x**, dùng interfaces do dự án triển khai:

```java
import java.util.Optional;
import java.util.UUID;
import org.springframework.security.core.Authentication;
import org.springframework.stereotype.Component;

@Component("documentPolicy")
public class DocumentPolicy {

    private final ActorResolver actors;
    private final DocumentAccessRepository documents;

    public DocumentPolicy(
            ActorResolver actors,
            DocumentAccessRepository documents) {
        this.actors = actors;
        this.documents = documents;
    }

    public boolean canRead(
            Authentication authentication, UUID documentId) {
        if (documentId == null) {
            return false;
        }

        Optional<VerifiedActor> resolved =
            actors.resolveVerified(authentication);

        if (resolved.isEmpty() || !resolved.get().active()) {
            return false;
        }

        VerifiedActor actor = resolved.get();
        Optional<DocumentAccessFacts> facts =
            documents.findAccessFacts(
                documentId, actor.tenantId()
            );
        if (facts.isEmpty()) {
            return false;
        }

        DocumentAccessFacts doc = facts.get();
        boolean owner =
            actor.userId().equals(doc.ownerId());
        boolean shared =
            doc.sharedReaders() != null
            && doc.sharedReaders().contains(actor.userId());
        boolean admin =
            actor.authorities() != null
            && actor.authorities()
                .contains("ROLE_TENANT_ADMIN");

        // Quyền document:read nằm ở @PreAuthorize.
        // Tenant đã được ràng buộc trong repository query.
        return owner || shared || admin;
    }

    public boolean canEdit(
            Authentication authentication, UUID documentId) {
        if (documentId == null) {
            return false;
        }

        Optional<VerifiedActor> resolved =
            actors.resolveVerified(authentication);
        if (resolved.isEmpty() || !resolved.get().active()) {
            return false;
        }

        VerifiedActor actor = resolved.get();
        Optional<DocumentAccessFacts> facts =
            documents.findAccessFacts(
                documentId, actor.tenantId()
            );
        if (facts.isEmpty()) {
            return false;
        }

        DocumentAccessFacts doc = facts.get();
        boolean owner =
            actor.userId().equals(doc.ownerId());
        boolean editor =
            actor.authorities() != null
            && actor.authorities()
                .contains("ROLE_TENANT_EDITOR");

        return "DRAFT".equals(doc.status())
            && (owner || editor);
    }
}
```

Để triển khai thật:

1. `ActorResolver.resolveVerified(...)` phải từ chối anonymous/inactive/unknown principal và xác minh tenant membership. Không chỉ đọc `authentication.getName()` rồi tin tên đó là user ID toàn cục duy nhất nếu app có nhiều realm/issuer.
2. `findAccessFacts(documentId, actor.tenantId())` phải truy vấn **cả ID lẫn tenant đã xác minh**, không dùng tenant do client gửi.
3. `sharedReaders` cần lấy từ ACL/bảng share còn hiệu lực; ví dụ rút gọn không mô tả expiry/revoke để code dễ theo dõi.
4. Mọi role cấp bởi bộ xác thực phải có phạm vi đúng; `ROLE_TENANT_ADMIN` không thể đại diện mọi tenant.
5. `canEdit` còn yêu cầu `document:update` ở annotation, trong khi đọc cần `document:read`.
6. Dù policy có một snapshot, thao tác ghi vẫn cần điều kiện DB để chống data race.

### 5.4. Không có record, không có quyền

Nếu `documents.findAccessFacts(...)` trả empty vì ID không tồn tại, tenant sai hoặc ACL không phù hợp, policy phải từ chối. Không “fallback allow” khi DB timeout, thiếu context hoặc membership lookup thất bại. Có thể trả 403 hoặc 404 ra HTTP theo threat model, nhưng bên trong không được cấp quyền khi không chứng minh được điều kiện.

### 5.5. Scoped query cho đọc

Ví dụ SQL ý tưởng:

```sql
SELECT id, tenant_id, owner_id, status, version
FROM documents
WHERE id = :documentId
  AND tenant_id = :verifiedTenantId;
```

Với list/search/export, đưa cả owner/share/admin scope xuống query thay vì đọc tất cả record rồi lọc ở Java:

```sql
SELECT d.id, d.title
FROM documents d
WHERE d.tenant_id = :verifiedTenant
  AND (
       d.owner_id = :verifiedUser
       OR EXISTS (
           SELECT 1
           FROM document_shares s
           WHERE s.document_id = d.id
             AND s.recipient_id = :verifiedUser
             AND s.permission = 'READ'
             AND s.revoked_at IS NULL
       )
       OR :verifiedTenantAdmin = TRUE
  );
```

`verifiedTenant`, `verifiedUser`, `verifiedTenantAdmin` lấy từ server đã kiểm chứng. Câu SQL chỉ là mô hình minh họa; cú pháp/schema thực tế tùy DB. Quyền chức năng vẫn phải được kiểm tra ở service. Đừng dùng một parameter boolean `isAdmin` do client cung cấp.

## 6. Tích hợp vào service, tránh bỏ qua chốt method

### 6.1. Service dùng @PreAuthorize

```java
import java.util.UUID;
import org.springframework.security.access.method.P;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.stereotype.Service;

@Service
public class DocumentService {

    private final DocumentRepository repository;

    public DocumentService(DocumentRepository repository) {
        this.repository = repository;
    }

    @PreAuthorize(
        "hasAuthority('document:read') and " +
        "@documentPolicy.canRead(authentication, #documentId)"
    )
    public DocumentView read(@P("documentId") UUID id) {
        // Repository phải dùng server-verified tenant scope.
        return repository.readScoped(id);
    }

    @PreAuthorize(
        "hasAuthority('document:update') and " +
        "@documentPolicy.canEdit(authentication, #documentId)"
    )
    public void rename(
            @P("documentId") UUID id, String newName) {
        // Thực tế dùng UPDATE có điều kiện tenant/status/version.
        repository.renameConditionally(id, newName);
    }
}
```

Đây là **mã khung**, chưa đầy đủ vì `DocumentRepository` và domain types cần được cài đặt. Các phương thức repository phải tiếp nhận hoặc tự lấy verified tenant đúng cách; `readScoped(id)` không được trở thành `findById(id)` không ràng buộc và phó mặc hết cho annotation.

### 6.2. Self-invocation là lối vòng thường gặp

```java
@Service
class BulkDocumentService {

    public void renameAll(List<UUID> ids) {
        for (UUID id : ids) {
            renameOne(id); // this.renameOne(...) nội bộ
        }
    }

    @PreAuthorize(
        "@documentPolicy.canEdit(authentication, #id)"
    )
    public void renameOne(UUID id) {
        // Thay đổi dữ liệu nhạy cảm
    }
}
```

Trong chế độ Spring AOP proxy phổ biến, lời gọi nội bộ cùng instance có thể **không đi qua proxy**, khiến `@PreAuthorize` bị bỏ qua. Cần thiết kế service boundary rõ, gọi qua Spring-managed bean có advice, và vẫn có check/constraint tại tầng dữ liệu. Annotation ở private method hoặc object tạo bằng `new` không phải chốt proxy đáng tin.

### 6.3. Class-level override không phải AND

```java
@PreAuthorize("hasAuthority('document:read')")
@Service
class DocumentQueryService {

    public DocumentView get(UUID id) { ... }

    @PreAuthorize("hasRole('TENANT_ADMIN')")
    public List<DocumentView> auditAll() { ... }
}
```

Khi method có `@PreAuthorize` riêng, nó có thể **override** rule cùng loại ở class. Đừng kỳ vọng `auditAll()` phải thỏa cả role admin lẫn document:read chỉ vì class có annotation. Nếu cần cả hai, viết một expression `and` hoặc dùng một policy bean tổng hợp.

Không gắn hai `@PreAuthorize` khác nhau lên cùng method và mong framework tự tạo phép AND. Spring Security không hỗ trợ lặp annotation cùng loại theo cách đó.

## 7. TOCTOU: authorization trước method và trạng thái khi ghi

### 7.1. Một race condition điển hình

Lúc 10:00:00.100, `@documentPolicy.canEdit(...)` kiểm tra:

```text
document=42
tenant=T1
owner=alice
status=DRAFT
version=7
ALLOW
```

Ngay sau đó, một giao dịch khác chuyển tài liệu thành `APPROVED` hoặc chuyển owner với version 8. Service update của Alice thực thi sau bước kiểm tra. Nếu DB UPDATE chỉ theo ID, dữ liệu có thể bị thay đổi dù trạng thái/quyền không còn phù hợp.

Đây là **Time Of Check To Time Of Use (TOCTOU)**. `@PreAuthorize` chặn lời gọi trước method, nhưng **không tự khóa hàng DB hoặc bảo đảm quyền vẫn đúng đến khi commit**.

### 7.2. Conditional update

Một mẫu SQL minh họa:

```sql
UPDATE documents
SET title = :newTitle,
    version = version + 1
WHERE id = :documentId
  AND tenant_id = :verifiedTenant
  AND version = :expectedVersion
  AND status = 'DRAFT'
  AND (
      owner_id = :verifiedUser
      OR :verifiedTenantEditor = TRUE
  );
```

Đánh giá số dòng bị tác động:

- 1: điều kiện ở thời điểm UPDATE đáp ứng và dữ liệu được thay đổi.
- 0: record vắng mặt, ngoài tenant, không đúng owner/editor, trạng thái không còn DRAFT hoặc version đã đổi.
- Không được diễn giải 0 là “vẫn cho phép vì pre-check trước đó pass”.

Với sharing, role động hoặc membership bị thu hồi, có thể cần query/lock/transaction nhất quán thêm. Cờ `verifiedTenantEditor` là giá trị server-side, không lấy trực tiếp từ request.

### 7.3. Chính sách đọc khác chính sách ghi

Với read-only method, có thể không cần khóa tài nguyên; nhưng vẫn phải scope dữ liệu. Với delete/payment/approve/transfer owner, check trước method là một **lớp cần có nhưng chưa đủ**. Phải kiểm invariants transaction, idempotency khi retry và tính hợp lệ của side effects. Ví dụ đã check owner khi request bắt đầu nhưng trước khi ghi owner bị chuyển sang người khác, UPDATE cần guard hiện hành.

### 7.4. Quyền thay đổi khi tác vụ chạy lâu

Một job export được tạo khi user còn quyền có thể chạy 15 phút sau khi permission bị thu hồi. Quyết định kiểm lại quyền lúc chạy hay chấp nhận snapshot có thời hạn là policy nghiệp vụ. `@PreAuthorize` trên HTTP method tạo job không tự bảo vệ worker hay URL tải file. Service/data policy và mô hình principal/tenant của background job cần được thiết kế độc lập.

## 8. Chương trình Java 17 chạy độc lập: role, owner và tenant

Chương trình không cần Spring và không giả lập JWT/session. Nó mô phỏng chính xác predicate của bài để có thể thử bằng JDK 17+:

- Đọc khi active, có `document:read`, cùng tenant, và owner hoặc được share hoặc tenant admin.
- Sửa khi active, có `document:update`, cùng tenant, không locked, và owner hoặc tenant admin.
- Admin tenant khác không vượt scope.
- Owner thiếu permission không tự đọc được.
- Dữ liệu null/không tồn tại mặc định bị từ chối.

Lưu file `DocumentRoleOwnershipDemo.java`:

```java
import java.util.Set;

public class DocumentRoleOwnershipDemo {

    record Actor(
        String id, String tenant, Set<String> grants,
        boolean active
    ) {}

    record Document(
        String id, String tenant, String owner,
        Set<String> readers, boolean locked
    ) {}

    static boolean has(Actor actor, String permission) {
        return actor != null && actor.active()
            && actor.grants() != null
            && actor.grants().contains(permission);
    }

    static boolean sameTenant(Actor actor, Document doc) {
        return actor != null && doc != null
            && actor.tenant() != null
            && actor.tenant().equals(doc.tenant());
    }

    static boolean owner(Actor actor, Document doc) {
        return actor != null && doc != null
            && actor.id() != null
            && actor.id().equals(doc.owner());
    }

    static boolean shared(Actor actor, Document doc) {
        return actor != null && doc != null
            && actor.id() != null
            && doc.readers() != null
            && doc.readers().contains(actor.id());
    }

    static boolean tenantAdmin(Actor actor) {
        return has(actor, "ROLE_TENANT_ADMIN");
    }

    static boolean canRead(Actor actor, Document doc) {
        return doc != null
            && has(actor, "document:read")
            && sameTenant(actor, doc)
            && (owner(actor, doc) || shared(actor, doc)
                || tenantAdmin(actor));
    }

    static boolean canEdit(Actor actor, Document doc) {
        return doc != null
            && has(actor, "document:update")
            && sameTenant(actor, doc)
            && !doc.locked()
            && (owner(actor, doc) || tenantAdmin(actor));
    }

    static void show(String label, boolean result) {
        System.out.println(label + ": " + result);
    }

    public static void main(String[] args) {
        Actor alice = new Actor(
            "alice", "T1",
            Set.of("document:read", "document:update"), true
        );
        Actor bob = new Actor(
            "bob", "T1",
            Set.of("document:read"), true
        );
        Actor admin = new Actor(
            "maria", "T1",
            Set.of("ROLE_TENANT_ADMIN", "document:read",
                   "document:update"), true
        );
        Actor remoteAdmin = new Actor(
            "max", "T2",
            Set.of("ROLE_TENANT_ADMIN", "document:read",
                   "document:update"), true
        );
        Actor ownerNoRead = new Actor(
            "alice", "T1", Set.of("document:update"), true
        );
        Actor adminNoRead = new Actor(
            "maria", "T1", Set.of("ROLE_TENANT_ADMIN"), true
        );
        Actor inactive = new Actor(
            "alice", "T1",
            Set.of("document:read", "document:update"), false
        );
        Actor auditor = new Actor(
            "auditor", "T1", Set.of("document:read"), true
        );

        Document doc = new Document(
            "d1", "T1", "alice", Set.of("bob"), false
        );
        Document locked = new Document(
            "d2", "T1", "alice", Set.of(), true
        );
        Document foreignDoc = new Document(
            "d3", "T2", "foreignOwner", Set.of(), false
        );

        show("alice reads owned", canRead(alice, doc));
        show("alice edits owned", canEdit(alice, doc));
        show("bob reads shared", canRead(bob, doc));
        show("bob edits shared", canEdit(bob, doc));
        show("admin reads same tenant", canRead(admin, doc));
        show("admin edits same tenant", canEdit(admin, doc));
        show("remote admin reads", canRead(remoteAdmin, doc));
        show("remote admin edits", canEdit(remoteAdmin, doc));
        show("alice reads foreign", canRead(alice, foreignDoc));
        show("owner missing read", canRead(ownerNoRead, doc));
        show("admin missing read", canRead(adminNoRead, doc));
        show("inactive owner reads", canRead(inactive, doc));
        show("unshared auditor reads", canRead(auditor, locked));
        show("admin edits locked", canEdit(admin, locked));
        show("owner edits locked", canEdit(alice, locked));
        show("missing document", canRead(alice, null));
        show("missing actor", canRead(null, doc));
    }
}
```

Chạy:

```bash
javac DocumentRoleOwnershipDemo.java
java DocumentRoleOwnershipDemo
```

Stdout được thiết kế như sau:

```text
alice reads owned: true
alice edits owned: true
bob reads shared: true
bob edits shared: false
admin reads same tenant: true
admin edits same tenant: true
remote admin reads: false
remote admin edits: false
alice reads foreign: false
owner missing read: false
admin missing read: false
inactive owner reads: false
unshared auditor reads: false
admin edits locked: false
owner edits locked: false
missing document: false
missing actor: false
```

Giải thích:

1. Alice có read/update và sở hữu tài liệu chưa khóa: hai hành động hợp lệ.
2. Bob có read và được share READ, nhưng không có UPDATE; đọc true, sửa false.
3. Maria có role admin và permission tương ứng **trong tenant T1**; đọc/sửa được document T1 không cần owner.
4. Max cũng là tenant admin nhưng thuộc tenant T2, nên hai hành động trên document T1 đều false.
5. Owner thiếu `document:read` hoặc admin không có read permission cũng không đọc được vì policy mẫu bắt buộc cả permission và quan hệ.
6. Inactive owner bị từ chối dù `id` đúng.
7. Auditor có read permission nhưng không owner/share/admin: false.
8. LOCKED từ chối update của cả owner và admin.
9. Thiếu actor/document: deny mặc định.

Đoạn Java standalone dùng record và Set, không có Spring AOP hay kiểm tra JWT thật. Nếu biến `grants` được tạo từ client header trong ứng dụng thật, tính an toàn mất ngay; nó chỉ là tập authorities **giả lập đã được xác minh** trong mô hình học tập.

## 9. @PostAuthorize, PermissionEvaluator và authorization manager

### 9.1. So sánh trước/sau method

Spring Security hỗ trợ:

```java
@PreAuthorize("hasAuthority('document:read')")
@PostAuthorize("returnObject.owner == authentication.name")
public DocumentView readDocument(UUID id) {
    // Load record để trả về.
}
```

Chốt trước yêu cầu permission; chốt sau kiểm tra owner dựa trên return object. Nhưng method đã thực thi trước khi `@PostAuthorize` đánh giá:

- Với thao tác đọc thuần, nó có thể là một lớp phòng vệ bổ sung.
- Với thao tác ghi/thanh toán/gửi email, deny sau method có thể quá muộn.
- `returnObject` null/collection hoặc cấu trúc proxy cần biểu thức khác.
- Điều kiện owner đơn thuần vẫn thiếu tenant, sharing và admin role nếu nghiệp vụ yêu cầu.

Vì thế mục tiêu của bài này là kết hợp quyền và ownership **trước lời gọi** bằng `@PreAuthorize` và policy bean, đồng thời enforce data constraints khi thực thi.

### 9.2. hasPermission

Một alternative:

```java
@PreAuthorize(
    "hasAuthority('document:read') and " +
    "hasPermission(#documentId, 'Document', 'read')"
)
```

`hasPermission` là hook cho một `PermissionEvaluator` được cấu hình. Nó **không tự biết schema DB hoặc owner/tenant** nếu chưa có implementation. Với hệ thống dùng Spring Security ACL, cách tiếp cận này có thể hữu ích nhưng cần thiết kế cache, sharing và scoping cẩn thận. Nếu nhu cầu chủ yếu là so owner + tenant, một policy bean typed thường dễ bắt đầu.

### 9.3. Custom AuthorizationManager

Dự án lớn có thể triển khai authorization manager riêng để tái sử dụng logic không phụ thuộc SpEL dài. Cần gắn đúng manager/interceptor theo version, xử lý `Authentication`, role hierarchy, kết quả deny/abstain và test. Dù vậy custom manager cũng không tự xác minh dữ liệu object: vẫn cần repository, tenant guard và transaction.

## 10. HTTP và method security phối hợp thế nào?

Một cấu hình HTTP minh họa:

```java
@Configuration
public class HttpSecurityRules {

    @Bean
    SecurityFilterChain chain(HttpSecurity http) throws Exception {
        http.authorizeHttpRequests(auth -> auth
            .requestMatchers(HttpMethod.GET, "/api/documents/**")
                .hasAuthority("document:read")
            .requestMatchers(HttpMethod.PUT, "/api/documents/**")
                .hasAuthority("document:update")
            .anyRequest().denyAll()
        );
        return http.build();
    }
}
```

Đây là **fragment tích hợp**, cần imports, authentication mechanism, CSRF/CORS config và controller thật. HTTP quyết định quyền theo method/path; không biết nội dung `documents.owner_id`. `@PreAuthorize` ở service kiểm tra object. Repository tiếp tục scope query/UPDATE.

Một số trường hợp:

| Trạng thái | HTTP | Method | Repository |
| --- | --- | --- | --- |
| Thiếu document:read gọi GET | Từ chối sớm | Có thể không chạy | Không đọc |
| Có read nhưng sai tenant | Có thể cho qua | canRead false | Scoped query không thấy |
| Read đúng tenant nhưng không owner/share/admin | Có thể cho qua | canRead false | Không trả object |
| Admin tenant A đọc document tenant A | Cho qua | canRead true | Có record scoped |
| Admin tenant B đọc document tenant A | Có thể cho qua | canRead false | Không tìm thấy scoped |
| Edit document LOCKED | Có update | canEdit false | UPDATE status guard |
| Owner đổi sau pre-check | Từng cho qua | Snapshot cũ | UPDATE guard phải từ chối |

Đừng xem một HTTP 403 là bằng chứng chắc chắn của method policy: nó có thể do CSRF, token, HTTP rule hoặc interceptor khác. Test cần cô lập tầng đang chặn.

## 11. Kiểm thử bằng Spring Security Test

### 11.1. Unit test policy bean

Tạo fixture actor và document cho các ca:

- Owner có permission;
- Owner thiếu permission;
- Shared read, shared edit không được cấp;
- Same-tenant stranger;
- Tenant admin cùng tenant;
- Tenant admin khác tenant;
- Anonymous/inactive;
- ID không tồn tại;
- Trạng thái LOCKED;
- Share bị revoke, role bị thu hồi;
- Owner/tenant đổi giữa check và ghi.

Mock `ActorResolver` cùng `DocumentAccessRepository`, assert policy gọi repository với **verified tenant**, không lấy tenant từ request. Quan trọng là kiểm tra cả dữ liệu không bị lộ hoặc không có side effect khi denied.

### 11.2. Test Spring bean có @PreAuthorize

Test tích hợp được đặt trong Spring context có `@EnableMethodSecurity`, service thật và fixture actor:

```java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.test.context.support.WithMockUser;

import java.util.UUID;
import static org.junit.jupiter.api.Assertions.*;

@SpringBootTest
class DocumentMethodSecurityTest {

    @Autowired
    DocumentService documents;

    @Test
    @WithMockUser(
        username = "alice",
        authorities = {"document:read"}
    )
    void ownerCanRead() {
        UUID ownedId = UUID.fromString(
            "00000000-0000-0000-0000-000000000042");
        // Fixture định nghĩa Alice tenant A, owner của ownedId.
        assertNotNull(documents.read(ownedId));
    }

    @Test
    @WithMockUser(
        username = "bob",
        authorities = {"document:read"}
    )
    void strangerCannotRead() {
        UUID ownedId = UUID.fromString(
            "00000000-0000-0000-0000-000000000042");
        assertThrows(
            AccessDeniedException.class,
            () -> documents.read(ownedId)
        );
    }
}
```

Đây là **mã test khung**, cần Spring beans, entity fixtures và `ActorResolver` tương thích với user mock. `@WithMockUser` chỉ tạo principal test; nó không chứng minh JWT signature, user membership thực hoặc role mapper của production. Với JWT, cần test riêng decoder và authority conversion.

### 11.3. Test đúng lý do từ chối

Nếu REST GET trả 403 có thể do HTTP authority; nếu PUT trả 403 có thể do CSRF trước khi tới service. Khi muốn test **quyền theo owner** của method, cần fixture cho HTTP/authentication/CSRF để request có thể tới service, hoặc test trực tiếp bean đã proxy.

Với POST/PUT/DELETE trong ứng dụng cookie/session, gửi CSRF token hợp lệ khi đang test authorization; dành một ca riêng kiểm tra CSRF thiếu token. Với bearer-only API, phải xác nhận kiến trúc không dùng cookie authentication ngoài ý định.

### 11.4. Negative tests là tiêu chí hoàn thành

Một suite bảo mật tối thiểu nên chứng minh:

1. Alice owner được đọc document cùng tenant.
2. Bob có read permission nhưng không owner/share vẫn bị deny.
3. Carol tenant admin cùng tenant được đọc nếu có permission.
4. David tenant admin khác tenant bị deny.
5. Alice owner nhưng read permission đã bị thu hồi bị deny.
6. Shared READ không cho sửa.
7. EDIT khi status LOCKED bị deny.
8. Anonymous/inactive bị deny.
9. API gửi ownerId hoặc tenantId giả không làm thay đổi kết quả.
10. Stale version khiến DB UPDATE tác động 0 row.
11. Service lời gọi qua Spring proxy thật có interceptor.
12. Job/GraphQL/messaging không bypass policy và query constraints.

### 11.5. Self-invocation và kiểm thử không qua HTTP

Nếu service tự gọi `this.rename()`, method-security interceptor có thể bị bypass. Vì vậy test một entrypoint có cùng cấu trúc lời gọi thật: REST controller → service bean, job → service bean, event consumer → service bean. Với tác vụ nền cần actor/service principal phù hợp; không tự truy cập `SecurityContextHolder` của một HTTP thread đã kết thúc.

**Chốt dữ liệu** vẫn là tuyến phòng vệ cuối nếu một caller bỏ qua service method.

## 12. Kỹ thuật trả 403 hay 404 và bảo vệ thông tin

Nếu client đọc một ID không tồn tại hoặc ngoài tenant, nhiều API chọn **404** để tránh để lộ tài liệu tồn tại. Nếu người gọi đã xác thực và thiếu quyền chức năng, có thể chọn **403**. Đây là quyết định ứng dụng/threat model, không phải đồng nghĩa 404 = không cần authorization.

- Không trả body chứa ownerId/tenantId/metadata của document bị chặn.
- Không có lỗi chi tiết tiết lộ một document khác tenant tồn tại.
- Log nội bộ có thể phân biệt NOT_FOUND, WRONG_TENANT, NOT_OWNER, MISSING_PERMISSION, LOCKED nhưng không lộ secret.
- Phân biệt 401 chưa xác thực với 403 thiếu quyền trong API phù hợp.
- Khi DB lỗi, không chuyển exception thành ALLOW hay tự gửi thông tin nhạy cảm trong 500 body.

## 13. Role và ownership trong các nghiệp vụ đặc biệt

### 13.1. Approve: owner có thể là người bị cấm

Trong quy trình hai người:

```text
CAN_APPROVE =
  has(document:approve)
  AND sameTenant
  AND assignedApprover
  AND document.creatorId != actor.id
  AND document.status == PENDING
```

Người tạo document **không được tự duyệt**, dù cũng là owner và có role mạnh. Đây là Separation of Duties (SoD). Ownership không luôn là quyền thêm vào: đôi khi nó là điều kiện **bị loại** cho tác vụ nhạy cảm.

### 13.2. Transfer owner và revoke sharing

Chuyển ownership làm thay đổi quan hệ quyền. Trong một transaction, cần kiểm tra actor có `document:transfer`, document thuộc tenant, owner hiện tại đúng, người nhận hợp lệ và record version đúng. Cập nhật owner rồi cập nhật ACL/caches/audit nhất quán; không tin owner mới từ payload là người dùng tồn tại và thuộc tenant nếu chưa verify.

Revoke share phải có hiệu lực theo yêu cầu nghiệp vụ, gồm cache và async download. Không chỉ đổi bảng ACL mà giữ file URL công khai vô thời hạn.

### 13.3. Export/list/search

Quyền đọc từng tài liệu không tự cho phép export tất cả. Có thể yêu cầu `document:export`, giới hạn trường dữ liệu, lượng kết quả, tenant và sharing scope. Query should use tenant/owner/ACL predicates **trước khi trả dữ liệu**, không lấy 10.000 record về bộ nhớ rồi mới gọi `canRead` từng object.

### 13.4. Global admin và break-glass

Nếu cần hỗ trợ truy cập cross-tenant khẩn cấp, nên có permission riêng, MFA, session step-up, lý do/ticket, time-limited access và audit độc lập. Không đưa ngoại lệ toàn cục vào biểu thức `hasRole('ADMIN') or isOwner` rồi âm thầm bypass tenant. Mọi override phải có chủ sở hữu chính sách và test giới hạn.

## 14. Lỗi phổ biến

| Lỗi | Hậu quả | Cách sửa |
| --- | --- | --- |
| Chỉ dùng hasRole('USER') | User đọc ID của người khác | Object policy theo ID |
| Chỉ dùng document:read | BOLA/IDOR | Thêm tenant và owner/share |
| Admin OR owner không ràng buộc tenant | Admin tenant B đọc tenant A | SameTenant là điều kiện chung |
| Tin ownerId/tenantId client gửi | Giả mạo dữ liệu quyền | Principal + DB đã verify |
| Role hierarchy coi như owner | Kế thừa authority sai thành object privilege | Tách hai loại quyền |
| Share READ cho phép UPDATE | Lạm quyền từ ACL | Phân biệt READ/WRITE |
| Chỉ kiểm tra isOwner | Admin/share case sai hoặc mất permission check | Chính sách canRead rõ |
| @PreAuthorize chưa bật | Annotation không được thực thi | @EnableMethodSecurity |
| #documentId không bind | Lỗi expression hoặc deny bất ngờ | @P / -parameters |
| Self-invocation | Bypass AOP interceptor | Bean/proxy boundary phù hợp |
| @PostAuthorize trên method ghi | Deny sau side effect | Pre-check + DB guard |
| Query không tenant-scoped | Đọc dữ liệu cross tenant | WHERE verifiedTenant |
| Pre-check rồi UPDATE theo ID | TOCTOU | Conditional update/version |
| N+1 kiểm tra ownership mỗi item | Kém hiệu năng/lộ memory | Query scoped |
| Role admin toàn cục ngoài ý định | Mở quyền quá rộng | Tenant-scoped roles |
| 403 được sửa bằng authenticated() | Bỏ quyền tài nguyên | Debug đúng tầng |
| Role/ACL bị revoke nhưng cache cũ | Quyền tồn tại quá lâu | TTL/revocation |
| Chỉ test happy path | Không bắt lỗi privilege escalation | Negative cases |
| Background job gọi repository trực tiếp | Bypass method security | Use case + data guard |
| Audit log chứa token/nội dung | Lộ thông tin nhạy cảm | Log tối thiểu + reason codes |

## 15. Quy trình áp dụng trong dự án

1. Xác định hành động: read, update, approve, delete, export hoặc transfer.
2. Xác định danh tính đáng tin: issuer/session/JWT, actor ID, tenant membership.
3. Xác định role/permission chức năng và phạm vi của chúng.
4. Xác định quan hệ tài nguyên: owner, share, assigned reviewer, trạng thái.
5. Viết predicate dạng logic trước code; đặt dấu ngoặc AND/OR rõ.
6. Lựa chọn nơi kiểm tra: HTTP rule, `@PreAuthorize`, policy bean và repository.
7. Lấy verified actor từ Authentication, không từ header hay body tùy ý.
8. Truy vấn access facts theo document ID **và verified tenant**.
9. Kiểm tra role + owner/share + trạng thái với default deny khi thiếu dữ liệu.
10. Với write, dùng transaction/conditional update/version guard.
11. Viết unit tests cho policy; integration tests qua proxy và HTTP.
12. Bổ sung negative cases: sai tenant, thiếu quyền, inactive, share revoke, locked.
13. Rà soát list/export và các entrypoint ngoài HTTP.
14. Thiết kế audit, TTL/cache và cơ chế thu hồi quyền.
15. Review thay đổi policy như thay đổi bảo mật, không phải refactor đơn giản.

## 16. Bài tập và tự kiểm tra

### Bài tập 1 — Phân tích AND/OR

Một biểu thức đang dùng `hasRole('TENANT_ADMIN') or @policy.isOwner(authentication,#id)`. Hãy tạo test admin khác tenant, owner thiếu read, same-tenant stranger và shared reader. Viết lại predicate sao cho ranh giới tenant là điều kiện chung.

### Bài tập 2 — Java 17

Chạy `DocumentRoleOwnershipDemo.java`, đối chiếu 17 dòng stdout. Thêm actor có role TENANT_EDITOR và document thuộc tenant T2; giải thích điều kiện nào còn thiếu nếu chỉ kiểm role.

### Bài tập 3 — Policy bean

Cài đặt `DocumentPolicy.canRead(authentication,documentId)` dùng `ActorResolver` và query ID+tenant. Tạo Mock repository trả empty khi tenant sai; test actor cùng role nhưng khác tenant bị deny.

### Bài tập 4 — Update có điều kiện

Đặt document DRAFT version 7. Sau khi pre-check, một transaction khác chuyển APPROVED version 8. Thực hiện câu UPDATE có expectedVersion=7 và status DRAFT; chứng minh 0 row updated, không thay đổi dữ liệu.

### Bài tập 5 — Quyền share

Bob được chia sẻ READ, không WRITE. Thiết kế ACL với revoke/expiry; kiểm tra `canRead` và `canEdit` riêng. Sau khi revoke, Bob không đọc được, kể cả có `document:read` chức năng.

### Bài tập 6 — SoD

Alice tạo document và được chỉ định approve. Dù có `ROLE_TENANT_ADMIN` và `document:approve`, policy phải từ chối nếu yêu cầu người tạo khác người duyệt. Viết test với người khác được chỉ định, sai tenant và trạng thái APPROVED.

### Bài tập 7 — Integration test

Bật `@EnableMethodSecurity`, tạo service với `@PreAuthorize` và policy bean. Test qua Spring bean với principal có read permission và ownership. Tạo một caller self-invocation để thấy nguy cơ bỏ qua proxy; sửa thiết kế và test không còn đường vòng.

### Bài tập 8 — Cross-tenant export

Thiết kế query list/export chỉ trả tài liệu cùng tenant và thuộc owner/share/tenant-admin scope. Không dùng `findAll()` rồi Java filter. Test account tenant A không bao giờ xem metadata document tenant B dù cùng ID pattern.

### Tự kiểm tra

1. **Role có đủ để quyết định quyền đọc record không?** Không; cần object policy theo business model.
2. **Ownership khác authority ở đâu?** Authority áp cho loại hành động, ownership áp cho từng object.
3. **Vì sao admin tenant khác vẫn bị deny?** Role tenant-scoped không tự cho phép cross-tenant.
4. **Mẫu logic chính của bài?** Permission AND sameTenant AND (owner OR share OR admin), bổ sung trạng thái theo hành động.
5. **Có thể bỏ permission nếu owner?** Chỉ nếu nghiệp vụ chủ ý, không tự suy diễn.
6. **@PreAuthorize chạy lúc nào?** Trước thân method được Spring AOP intercept.
7. **@documentPolicy có nghĩa gì?** Bean Spring xử lý logic quyền tài nguyên.
8. **#documentId lấy từ đâu?** Tham số method được bind theo tên/@P/-parameters.
9. **Header X-User-Id có chứng minh owner?** Không.
10. **findById có bảo vệ tenant không?** Không nếu không có guard/query scope riêng.
11. **Vì sao pre-check chưa loại TOCTOU?** Quyền/owner/status có thể thay đổi trước DB UPDATE.
12. **@PostAuthorize thích hợp làm chốt duy nhất cho payment không?** Không, vì side effect có thể xảy ra trước deny.
13. **Một ROLE_TENANT_ADMIN có thể được miễn trạng thái LOCKED không?** Chỉ nếu chính sách nghiệp vụ tuyên bố rõ; mẫu bài này không cho.
14. **Tại sao negative tests quan trọng?** Chúng phát hiện OR sai, thiếu tenant và privilege escalation.
15. **403 có chứng minh chốt method chạy không?** Không; có thể do HTTP/CSRF hoặc chốt khác.
16. **Self-invocation có chắc chạy @PreAuthorize?** Không trong Spring proxy mode thông thường.
17. **Role hierarchy có biến user thành owner không?** Không.
18. **Job không qua HTTP chain có an toàn nhờ service annotation?** Chỉ khi gọi qua proxy và có actor/context phù hợp; data invariants vẫn cần.
19. **Có thể trả 404 thay 403 cho ngoài tenant không?** Có nếu thiết kế che tồn tại, nhưng không thay quyền kiểm tra.
20. **Điều kiện cơ bản cho update an toàn?** Permission + tenant + owner/editor + trạng thái + transaction/version guard.

**Ghi nhớ:** `@PreAuthorize` giúp kết hợp quyền chức năng với kiểm tra **chủ sở hữu hoặc quan hệ được phép đối với tài nguyên** trước khi code nghiệp vụ chạy. Hãy viết chính sách với tenant là ranh giới chung, không tin các trường owner/tenant do client tự gửi, không dùng role admin như một nhánh OR vượt mọi điều kiện, và kiểm tra lại những bất biến quan trọng tại DB khi ghi. Kết quả an toàn phải được chứng minh bằng test cho cả các trường hợp **được phép** và **bị từ chối**.

### Tài liệu tham khảo

- [Spring Security – Method Security, @PreAuthorize, tham số và bean expressions](https://docs.spring.io/spring-security/reference/servlet/authorization/method-security.html)
- [Spring Security 6.5 – Method Security](https://docs.spring.io/spring-security/reference/6.5/servlet/authorization/method-security.html)
- [Spring Security – Authorize HTTP Requests](https://docs.spring.io/spring-security/reference/servlet/authorization/authorize-http-requests.html)
- [Spring Security – Method Security Tests](https://docs.spring.io/spring-security/reference/servlet/test/method.html)
- [OWASP – API1:2023 Broken Object Level Authorization](https://owasp.org/API-Security/editions/2023/en/0xa1-broken-object-level-authorization/)