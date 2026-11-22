# Kết hợp tenant, subject, role và tài nguyên khi quyết định quyền

## 1. Vấn đề: role hợp lệ chưa chắc cấp quyền trên đúng dữ liệu

Ứng dụng Spring Security nhiều tenant thường bắt đầu với `ROLE_READER`, `ROLE_EDITOR` hoặc `ROLE_ADMIN`. Nhưng role có thể chỉ có hiệu lực trong một tổ chức (tenant) nhất định; cùng người dùng có thể là EDITOR ở tenant north, READER ở tenant south và không có membership ở tenant east. Mỗi tài liệu lại có tenant, owner, trạng thái và quyền chia sẻ khác nhau.

Giả sử Alice là EDITOR ở north, READER ở south. Document #42 nằm tại south, owner là Bob, Alice chỉ được cấp READ. Khi Alice gọi WRITE trên document 42, hệ thống phải DENY. Không thể dựa vào role EDITOR của north để ghi dữ liệu ở south.

**Quyết định đúng phải kết hợp ít nhất bốn chiều: tenant, subject, role và resource**, đồng thời phân biệt action READ/WRITE/DELETE/SHARE và các business constraints. Mỗi chiều bổ sung một ranh giới khác: chọn đúng tenant, nhận diện đúng actor, xác định quyền chức năng theo tenant và xác minh tài nguyên cụ thể.

Mục tiêu bài này:
- Mô hình hóa input quyết định quyền đa tenant với dữ liệu tin cậy.
- Tránh nhầm tenant trong URL/header với membership đã xác minh.
- Tránh nhầm subject ID trùng giữa các issuer.
- Tách role theo tenant khỏi permission trên từng object.
- Dùng Spring Security và Spring Data JPA để bảo vệ service/query, kể cả các đường non-HTTP.
- Biết cách fail closed, xử lý exception, cache, thay đổi quyền và kiểm thử các tình huống đối kháng.

## 2. Công thức khái niệm cho một quyết định

Mô hình:

~~~text
Request:
  subject = verified identity (issuer + subject id)
  tenant  = requested workspace / organization
  action  = DOCUMENT_READ | DOCUMENT_WRITE | DOCUMENT_DELETE
  object  = document id and actual database attributes
  context = current time, delegation, device or business state

Decision:
  ALLOW only when every mandatory guard is satisfied.
~~~

Một công thức điển hình cho document riêng:

~~~text
ALLOW =
    authenticated(subject)
    AND tenantIsTrustedAndActive(tenant)
    AND activeMember(subject, tenant)
    AND tenantRoleAllows(subject, tenant, action)
    AND resource.id == requestedId
    AND resource.tenantId == tenant
    AND (
        isOwner(subject, resource)
        OR hasValidObjectGrant(subject, resource, action)
        OR approvedTenantAdminException(subject, tenant, resource, action)
    )
    AND resourceStateAllows(action)
~~~

Đây là **đặc tả logic**, không phải method Java hay biểu thức SpEL có sẵn. Tùy sản phẩm có thể cho phép public resource hoặc global support, nhưng phải viết **chính sách riêng** và kiểm tra đầy đủ, không thêm một nhánh `OR isAdmin` rộng để bỏ qua tenant/resource.

Phải phân biệt:
1. **Chức năng:** Actor có quyền DOCUMENT_WRITE trong tenant north không?
2. **Đối tượng:** Actor có quyền WRITE trên Document #42 thuộc north không?
3. **Trạng thái:** Document #42 có đang bị khóa hoặc legal hold không?

Đáp án true ở câu 1 không tự làm câu 2 và câu 3 true.

## 3. Nguồn dữ liệu nào được tin?

| Chiều | Ví dụ | Nguồn hợp lệ | Không được coi là bằng chứng |
|---|---|---|---|
| Subject | issuer + sub | Authentication/JWT đã xác thực, identity provider đáng tin | `userId` trong JSON body |
| Tenant | north | Tenant target đối chiếu với membership server-side/claim đã xác thực | Header `X-Tenant-Id` tự khai |
| Role | EDITOR trong north | Role mapping được gắn tenant, active và còn hiệu lực | Global `ROLE_EDITOR` khi nó thật ra thuộc south |
| Action | DOCUMENT_WRITE | Use case/endpoint định nghĩa thao tác cần kiểm | Action string do client chọn rồi mặc nhiên tin |
| Resource | document id 42, tenant north | DB query scoped, ACL và trạng thái từ server | `owner=true`/`resourceTenant=north` trong payload |
| Context | thời gian, project, classification | Server clock, trusted gateway/domain policy | Thời gian/clearance do client tự khai |

Tenant ID trong path, query hoặc header có thể giúp chọn **mục tiêu**, nhưng không xác minh quyền vào tenant đó. Chỉ sau khi kiểm tra membership/entitlement đáng tin mới có thể dùng tenant để route DB/schema hay query dữ liệu.

Subject phải lấy từ authentication đã xác minh. Nếu một background job gọi service không có user token, nó cần workload identity với phạm vi và policy rõ; không được tự dùng user ID cố định để giả mạo một tenant admin.

## 4. Authentication không thay resource authorization

Spring Security authentication pipeline có thể:
- Xác minh chữ ký, issuer, audience, expiry và những điều kiện khác của JWT.
- Tạo `Authentication` chứa principal và authorities.
- Lưu authentication trong `SecurityContext` đối với request hiện hành.

Tuy nhiên, một JWT hợp lệ không tự chứng minh user sở hữu Document #42 hoặc vẫn còn membership ở tenant south. Quyền đối tượng có thể đổi sau lúc token được phát; role trong token cũng có thể bị thu hồi.

**Không tự parse claim chưa xác thực để ra quyết định.** Một claim như `tenant="north"` trong JWT chỉ đáng tin sau khi pipeline xác minh token và ứng dụng biết claim đó có ý nghĩa gì. Thậm chí claim đã được ký vẫn có thể mô tả tenant mặc định, chứ không phải membership của mọi tenant mà người dùng muốn truy cập.

Có hai khái niệm cần giữ riêng:
- Tenant/issuer dùng để **chọn cách xác thực** token trong Resource Server.
- Tenant dùng để **xác định quyền và dữ liệu** của resource được yêu cầu.

Một issuer có thể quản lý nhiều tenant, và tenant có thể sử dụng nhiều issuer theo kiến trúc. Không suy luận hai giá trị luôn bằng nhau.

## 5. Subject ID phải được đặt trong namespace issuer

Claim `sub` có thể unique trong một issuer nhưng không unique giữa nhiều issuer:

~~~text
iss=https://idp-a.example, sub=123 --> Alice
iss=https://idp-b.example, sub=123 --> Bob
~~~

Nếu bảng membership hoặc ACL chỉ dùng `subject_id="123"`, Bob có nguy cơ nhận nhầm quyền của Alice. Hãy dùng khóa như:

~~~text
SubjectKey(
  issuer = "https://idp-a.example",
  subject = "123"
)
~~~

Hoặc map cặp issuer/subject đã xác minh sang một internal actor ID globally unique. Mã Java 17 mô tả value object:

~~~java
public record SubjectKey(String issuer, String subject) {
    public SubjectKey {
        if (issuer == null || issuer.isBlank()
                || subject == null || subject.isBlank()) {
            throw new IllegalArgumentException("Invalid subject identity");
        }
    }
}
~~~

**Lưu ý:** constructor validate null/rỗng, **không tự xác minh issuer**. Tầng nhận token phải xác thực issuer và mapping danh tính trước khi tạo subject key được policy tin cậy.

Email/name không nên được sử dụng như khóa chủ thể nếu có khả năng thay đổi, tái sử dụng hoặc trùng giữa issuer. Nếu cần account linking, việc liên kết hai subject phải có quy trình xác minh và audit riêng.

## 6. Tenant selection khác tenant membership

Một request:

~~~text
GET /tenants/north/documents/42
X-Workspace: north
~~~

cho thấy client chọn tenant north. Nó **không chứng minh** actor đang là member north.

Luồng xử lý:
1. Xác thực caller, lấy issuer+subject key đáng tin.
2. Xác định tenant được yêu cầu từ route hoặc một context hợp lệ.
3. Tra tenant tồn tại và active.
4. Kiểm tra membership/entitlement của actor trong tenant này, còn hiệu lực.
5. Lấy role trong **chính tenant ấy**.
6. Truy vấn Document #42 với tenant filter và kiểm tra object permission.
7. Chỉ sau kết quả ALLOW mới trả dữ liệu hoặc mutate.

Mô hình bảng:

~~~text
tenant_memberships(
    subject_key,
    tenant_id,
    role_code,
    status,
    valid_from,
    valid_until
)
~~~

Nếu một subject có nhiều role trong một tenant, có thể lưu nhiều hàng hoặc bảng membership_role riêng. Phải quy định hết hạn, suspended, revoked, project membership và cách role được cập nhật.

Khi request không có tenant, một endpoint bắt buộc tenant nên trả lỗi/deny; không tự chọn tenant đầu tiên rồi coi như quyền. Một ứng dụng dùng server-side “current tenant” cần xác minh current tenant được chọn trước đó và vẫn hợp lệ, nhất là khi user đã bị thu hồi membership.

## 7. Role phải được scope theo tenant

| Subject | Tenant | Role | DOCUMENT_READ | DOCUMENT_WRITE |
|---|---|---|---|---|
| Alice | north | EDITOR | Có | Có |
| Alice | south | READER | Có | Không |
| Bob | north | READER | Có | Không |
| Chi | south | TENANT_ADMIN | Có | Có |

Role trong bảng là **chính sách ví dụ**, không phải enum được Spring Security tự định nghĩa. Một editor có thể bị cấm WRITE một object vì object không chia sẻ hoặc đang locked.

Các cách tổ chức role:
- **DB mapping per tenant:** query `(subject, tenant)`, lọc active/expiry.
- **Claim scoped per tenant:** token chứa danh sách membership có tenant ID, được xác minh và có chính sách revoke/TTL rõ.
- **Authorities theo current tenant:** chuyển đổi role thành authorities khi currentTenant đã xác minh; phải ngăn dùng cho tenant khác.

Không dùng một `ROLE_TENANT_ADMIN` toàn cục để mở mọi tenant nếu quyền thật sự chỉ có hiệu lực ở south. Cần phân biệt `TENANT_ADMIN` với global support/system admin, và định nghĩa quyền break-glass riêng.

Một role chứa tên tenant như `TENANT_north_EDITOR` có thể là cách encoding, nhưng không tự thay membership validation hay object permission; chuỗi đó cũng có thể làm số authorities rất lớn khi user tham gia nhiều workspace.

## 8. Role gate và object gate phải cùng đúng

Một thiết kế cho tài liệu riêng:

~~~text
tenantRoleAllows(action)
AND resource.tenantId == verifiedTenant
AND (
  subjectIsOwner(resource)
  OR activeObjectGrant(subject, resource, action)
  OR approvedTenantAdminRule
)
AND resourceStateAllows(action)
~~~

Ví dụ:
- Alice EDITOR north, là owner Document north #42, status ACTIVE → WRITE có thể ALLOW.
- Alice EDITOR north, không phải owner của Document #43 và không được share → WRITE DENY.
- Bob READER north, được grant READ trên Document #43 → READ ALLOW, WRITE DENY.
- Chi TENANT_ADMIN south → không thể READ document north nếu không có cross-tenant policy đặc biệt.
- Alice có grant WRITE nhưng document LOCKED → DENY do business constraint.

Không mặc định `WRITE` gồm `DELETE` hoặc `SHARE`; permission hierarchy cần được viết rõ. Object grant cũng không đương nhiên cho phép gọi API quản trị tenant.

## 9. Tài nguyên cần được tra bằng ID **và** tenant

Document có thể có:

~~~text
Document {
  id,
  tenantId,
  ownerSubjectKey,
  projectId,
  classification,
  status,
  version
}
~~~

Cùng ID local 42 có thể xuất hiện ở nhiều tenant; nếu ID global unique, vẫn cần tenant scope để tránh truy vấn sai quyền.

Query owner-only an toàn:

~~~sql
SELECT d.id, d.title, d.status
FROM documents d
WHERE d.id = :document_id
  AND d.tenant_id = :verified_tenant
  AND d.owner_subject_key = :verified_subject;
~~~

**Chỉ ID trong URL không phải bằng chứng được phép truy cập.** Không trả trực tiếp `repository.findById(id)` cho bất kỳ user nào có `document:read`. Đó là lỗi BOLA/IDOR nếu thiếu object authorization.

Nếu request body có `ownerId`, `tenantId` hoặc `isAdmin`, server phải xác minh chúng với DB và identity; đừng dùng client metadata làm nguồn quyền.

## 10. Chia sẻ theo object: tenant AND (owner OR grant)

Một bảng grant đơn giản:

~~~text
document_grants(
    tenant_id,
    document_id,
    subject_key,
    permission,
    expires_at,
    revoked_at
)
~~~

Câu SQL cho READ:

~~~sql
SELECT d.*
FROM documents d
WHERE d.id = :id
  AND d.tenant_id = :tenant
  AND d.status = 'ACTIVE'
  AND (
      d.owner_subject_key = :subject
      OR EXISTS (
          SELECT 1 FROM document_grants g
          WHERE g.tenant_id = d.tenant_id
            AND g.document_id = d.id
            AND g.subject_key = :subject
            AND g.permission = 'READ'
            AND g.revoked_at IS NULL
            AND (g.expires_at IS NULL OR g.expires_at > :now)
      )
  );
~~~

Chú ý:
- `d.id`, `d.tenant_id` và status **ở ngoài ngoặc OR**; áp dụng cho mọi nhánh quyền.
- Grant phải khớp đúng tenant, ID, subject, permission và hiệu lực.
- `EXISTS` trả lời có grant hợp lệ hay không, tránh nhân bản row.
- `:now` lấy từ server clock.
- Role/action gate ở service vẫn bắt buộc. Câu SQL trên giải object scope, **không tự biết role của actor trong tenant**.

Một lỗi ưu tiên toán tử:

~~~sql
WHERE d.id = :id AND d.tenant_id = :tenant
  AND d.owner_subject_key = :subject
  OR EXISTS (SELECT 1 FROM document_grants g
             WHERE g.document_id = d.id
               AND g.subject_key = :subject)
~~~

Vì `AND` mạnh hơn `OR`, nhánh share có thể bỏ qua ID và tenant. Test phải có share trên resource khác và một resource cùng ID ở tenant khác để phát hiện.

## 11. Spring Data JPA: derived query theo actor và tenant

Với entity `Document` có properties `id`, `tenantId`, `ownerSubjectKey`:

~~~java
import java.util.Optional;
import org.springframework.data.jpa.repository.JpaRepository;

public interface DocumentRepository extends JpaRepository<Document, Long> {
    Optional<Document> findByIdAndTenantIdAndOwnerSubjectKey(
            Long id, String tenantId, String subjectKey);
}
~~~

Đây là **snippet tích hợp Spring Data JPA**, không phải Java standalone; entity và persistence config phải có thật. Spring Data JPA xây predicate theo tên property.

Đối với object share READ, JPQL:

~~~java
import java.time.Instant;
import java.util.Optional;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;

public interface ReadableDocumentRepository
        extends JpaRepository<Document, Long> {

    @Query("""
        select d from Document d
        where d.id = :id
          and d.tenantId = :tenant
          and d.status = 'ACTIVE'
          and (
              d.ownerSubjectKey = :subject
              or exists (
                  select g.id from DocumentGrant g
                  where g.document = d
                    and g.tenantId = :tenant
                    and g.subjectKey = :subject
                    and g.permission = 'READ'
                    and g.revokedAt is null
                    and (g.expiresAt is null or g.expiresAt > :now)
              )
          )
        """)
    Optional<Document> findVisibleById(
            @Param("id") Long id,
            @Param("tenant") String tenant,
            @Param("subject") String subject,
            @Param("now") Instant now);
}
~~~

Mã giả định `DocumentGrant` có relation `document` và các properties đúng tên; trong production, FK/constraint cũng phải ngăn grant tham chiếu sai tenant. `@Query` JPQL dùng entity properties, không dùng tên cột raw SQL.

Repository nhận các chuỗi tenant/subject; việc bảo đảm đó là **chuỗi đã xác minh** là trách nhiệm của service/resolver. Nếu policy cần WRITE/DELETE, phải dùng predicate cho **đúng action**, không reuse query READ.

## 12. Tổ chức service boundary theo Spring Security

Một service có thể kiểm tra:
- Authentication được xác minh.
- Actor có active membership tại tenant target.
- Role tại tenant target cho phép DOCUMENT_READ.
- Document có đúng tenant, owner/share permission và trạng thái phù hợp.

Ví dụ tích hợp:

~~~java
import java.time.Clock;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.security.access.AccessDeniedException;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class DocumentQueryService {
    private final TenantActorResolver actors;
    private final TenantRolePolicy roles;
    private final ReadableDocumentRepository documents;
    private final Clock clock;
    private final DocumentMapper mapper;

    public DocumentQueryService(
            TenantActorResolver actors, TenantRolePolicy roles,
            ReadableDocumentRepository documents,
            Clock clock, DocumentMapper mapper) {
        this.actors = actors;
        this.roles = roles;
        this.documents = documents;
        this.clock = clock;
        this.mapper = mapper;
    }

    @PreAuthorize("isAuthenticated()")
    @Transactional(readOnly = true)
    public DocumentView read(String requestedTenant, Long id) {
        VerifiedTenantActor actor = actors.requireMember(requestedTenant);

        if (id == null || id <= 0
                || !roles.allows(actor.subjectKey(),
                        actor.tenantId(), "DOCUMENT_READ")) {
            throw new AccessDeniedException("Document access denied");
        }

        Document document = documents.findVisibleById(
                id, actor.tenantId(), actor.subjectKey(),
                clock.instant()
        ).orElseThrow(ResourceNotFoundException::new);

        return mapper.toView(document);
    }
}
~~~

Đây là **code tích hợp**, các kiểu `TenantActorResolver`, `TenantRolePolicy`, `VerifiedTenantActor`, `DocumentMapper`, `DocumentView`, `ResourceNotFoundException` và entity `Document` do ứng dụng cung cấp.

`actors.requireMember` phải lấy issuer/subject từ authenticated principal và kiểm tra tenant active membership; nó **không được** chỉ gói chuỗi `requestedTenant` thành một “verified actor”. `roles.allows` phải tra role trong **actor.tenantId()**, không role global vô điều kiện.

`@EnableMethodSecurity` phải bật. Lời gọi phải qua Spring-managed proxy để `@PreAuthorize` và transaction advice phát huy tác dụng; self-invocation có thể bypass annotation trong proxy mode. Với resource-level policy, một cách dễ bảo trì là giữ kiểm tra quan trọng trong service và query scoped để các entrypoint khác cùng được bảo vệ.

## 13. Dùng @PreAuthorize cho policy bean khi cần

Một cách khác:

~~~java
@PreAuthorize(
    "isAuthenticated() and " +
    "@documentAccess.canRead(authentication, #tenantId, #documentId)")
public DocumentView read(String tenantId, Long documentId) {
    return documentService.readInVerifiedScope(tenantId, documentId);
}
~~~

Mã này là snippet tích hợp, không có đầy đủ class/import. Bean `documentAccess` cần:
1. Xác minh authentication/issuer/subject.
2. Xác minh membership/role của actor trong `tenantId`.
3. Tra document theo ID + tenant, rồi kiểm tra owner/share/status.
4. Trả true chỉ khi đủ bằng chứng.

Cần để ý SpEL tìm tên tham số: thường dùng compiler `-parameters`, `@P` hoặc cấu hình tương ứng. Một unit test bean trả true không chứng minh service method proxy đã gọi bean.

Hơn nữa, check tại `@PreAuthorize` rồi update ID trần ở method body có thể xảy ra TOCTOU khi owner/grant đổi; cần transaction, conditional UPDATE hoặc recheck tại ranh giới mutation.

## 14. HTTP filter chỉ là lớp đầu

Một cấu hình Servlet:

~~~java
@Bean
SecurityFilterChain security(HttpSecurity http) throws Exception {
    http.authorizeHttpRequests(auth -> auth
        .requestMatchers("/tenants/*/documents/**").authenticated()
        .anyRequest().denyAll());
    return http.build();
}
~~~

Đây là **snippet cấu hình Spring**, không phải chương trình Java độc lập. Nó yêu cầu authentication ở endpoint, chưa xác minh user là member tenant trong URL, có role phù hợp hay có ACL trên document.

Spring Security HTTP có các lựa chọn `hasAuthority(...)`, `hasRole(...)` và `.access(AuthorizationManager<RequestAuthorizationContext>)` để kiểm tra ở request level, nhưng query/resource policy thường thuộc service boundary. Đừng tưởng bất kỳ `AuthorizationManager<String>` tự động tương thích với `RequestAuthorizationContext`.

Một kiến trúc rõ ràng:

~~~text
HTTP / message / job adapter
     |
     v
Authentication + trusted subject
     |
     v
Tenant membership + tenant role
     |
     v
Resource-specific scope / ACL / business rule
     |
     v
Query / action / DTO / commit
~~~

HTTP SecurityFilterChain không tự bảo vệ code gọi từ scheduler, message consumer, CLI hoặc direct internal service. Những entrypoint này phải đi qua cùng policy hoặc dùng service identity với contract riêng.

## 15. Nhiều JWT issuer: allowlist trước khi xác thực

Spring Security Resource Server multi-tenancy có `JwtIssuerAuthenticationManagerResolver`. Ví dụ từ tài liệu chính thức:

~~~java
JwtIssuerAuthenticationManagerResolver resolver =
        JwtIssuerAuthenticationManagerResolver.fromTrustedIssuers(
                "https://idp.example.com/realm-a",
                "https://idp.example.com/realm-b");

http.oauth2ResourceServer(oauth2 ->
        oauth2.authenticationManagerResolver(resolver));
~~~

Đây là snippet tích hợp; cần Spring Security Resource Server, các imports, cấu hình `HttpSecurity` và issuer production đã được cấu hình thực. Domain ở ví dụ chỉ để minh họa.

**Điều cần nhớ:**
- Chỉ tin issuer được allowlist. Không tạo AuthenticationManager/decoder cho issuer bất kỳ do client cung cấp.
- JWT phải được xác minh chữ ký, issuer, audience, expiration, token validity theo cấu hình ứng dụng.
- Sau validation, subject key cần bao gồm issuer hoặc map đến internal principal bền vững.
- Issuer xác thực **không đồng nghĩa** tenant data scope; không tự lấy issuer làm tenant resource.
- Role claim trong một issuer có thể được tổ chức theo tenant. Không gộp mọi role của tất cả tenant thành global authorities.
- Khi dynamic tenant/issuer onboarding, quy trình đăng ký issuer phải có nguồn tin cậy, không chỉ `iss` tự khai.

## 16. Một actor nhiều tenant: tránh current tenant global

Một người có thể chuyển tenant liên tục. Các cách:
- Tenant target trong route, mỗi request xác minh membership.
- Session server giữ currentTenant có kiểm tra khi chuyển.
- Token ngắn hạn chỉ scope một tenant và được phát lại khi đổi context.

Không lưu một biến static như:

~~~java
static String currentTenant = "north";
~~~

và dùng nó cho mọi request; biến static chia sẻ giữa user và thread. `ThreadLocal` tenant context cũng không tự chứng minh quyền; nếu dùng phải set từ nguồn đáng tin và clear trong `finally` ở mọi đường thoát, test với connection pool/async.

Khi database per tenant hoặc schema per tenant, routing phải dựa vào tenant đã xác minh. Không ghép tên schema trực tiếp từ header chưa kiểm tra vào SQL hay query string.

## 17. Khi project/group cũng cấp quyền

Một tài liệu có thể thuộc project mà actor là member có quyền READ:

~~~sql
SELECT d.*
FROM documents d
WHERE d.id = :id
  AND d.tenant_id = :tenant
  AND (
      d.owner_subject_key = :subject
      OR EXISTS (
          SELECT 1
          FROM project_memberships m
          WHERE m.project_id = d.project_id
            AND m.tenant_id = d.tenant_id
            AND m.subject_key = :subject
            AND m.role_code IN ('PROJECT_VIEWER','PROJECT_EDITOR')
            AND m.status = 'ACTIVE'
      )
  );
~~~

Đây là mô hình domain SQL, không phải bảng mặc định Spring Security. Query phải thêm business constraints nếu document không kế thừa quyền project hoặc thuộc classification đặc biệt. Với WRITE, đòi role project thích hợp; không sao chép nguyên predicate READ.

Khi group membership thay đổi, các grant dựa trên nhóm phải mất hiệu lực theo SLA rõ. Nếu membership được cache trong JWT, quyền có thể stale cho tới expiry; cần cơ chế revoke/recheck cho thao tác nhạy cảm.

## 18. Resource state và explicit deny

Một số policy ví dụ:
- Owner có READ/WRITE nhưng không DELETE khi document đang trong legal hold.
- Tenant admin được đọc tài liệu bình thường, nhưng SECRET yêu cầu clearance độc lập.
- Project viewer chỉ đọc tài liệu kế thừa quyền từ project.
- Share WRITE được cấp có expiry; sau expiry không cho ghi.
- Resource ARCHIVED cấm thay đổi nhưng vẫn có thể READ.

Hãy thể hiện điều kiện bắt buộc **bên ngoài** các nhánh `owner OR grant OR admin`:

~~~text
ALLOW =
  tenantValid
  AND roleAllowsAction
  AND resourceTenantMatches
  AND resourceStateAllowsAction
  AND (owner OR directGrant OR approvedAdminRule)
~~~

Đừng viết `owner OR (grant AND resourceStateAllows)` nếu owner cũng phải bị chặn khi locked. Một `OR globalAdmin` ngoài cả expression có thể bỏ qua tenant, resource ID, status và MFA khi không được chủ đích cho phép.

Với Spring ACL, semantics `ACE` grant/deny và inheritance phải được test theo evaluator. Không suy luận “deny luôn thắng” cho mọi implementation tùy chỉnh mà chưa xem contract.

## 19. Public data và cross-tenant sharing là ngoại lệ có kiểm soát

Một số ứng dụng có tài liệu PUBLIC hoặc shared link cho bên ngoài tenant. Đây là use case hợp lệ nhưng phải có policy riêng:
- Resource được chủ động đánh dấu public/published.
- Không mặc định public nếu owner, tenant hoặc ACL null.
- Share link có token ngẫu nhiên đủ entropy, expiry, revoke và scope READ cụ thể.
- Client không được chỉ truyền `isPublic=true` để mở tài liệu.
- Truy cập từ tenant khác cần khả năng/capability hợp lệ chứ không phải bỏ tenant predicate toàn hệ.

Một global support role cũng là ngoại lệ: đòi entitlement được quản trị, thời hạn, reason code, audit, và có thể cần xác thực mạnh. Không nhầm TENANT_ADMIN với SYSTEM_ADMIN.

## 20. Fail closed khi thiếu một chiều

| Thành phần thiếu/sai | Hành vi đúng |
|---|---|
| Authentication | Không cấp, challenge/deny |
| Issuer hoặc subject ID không xác minh được | Không cấp |
| Tenant request không hợp lệ | Không tự chọn scope rộng |
| Membership tenant bị thu hồi/hết hạn | DENY |
| Role không cho phép action | DENY |
| Object thuộc tenant khác | DENY hoặc 404 theo API |
| Object grant không tồn tại/hết hạn/revoked | DENY |
| Owner field null trái schema | Không suy luận public |
| Business state LOCKED | DENY thao tác bị khóa |
| ACL backend timeout/không trả quyết định | Không thực hiện; báo lỗi kỹ thuật hoặc deny có kiểm soát |
| Permission cache miss | Tra nguồn tin cậy hoặc deny, không assume allow |

Một anti-pattern SQL:

~~~sql
WHERE id = :id
  AND (:tenant IS NULL OR tenant_id = :tenant)
  AND (:subject IS NULL OR owner_subject_key = :subject)
~~~

Nếu tenant/subject null, security guard biến thành optional filter, dễ trả dữ liệu quá phạm vi. Với data authorization, scope **không optional**.

Custom `AuthorizationManager` có thể dùng `null` cho abstain; **abstain không phải negative decision**. Với rule bắt buộc, tránh trả null khi không có membership/ACL, trừ khi composition đã được thiết kế/test để fail closed.

## 21. API response và tránh rò rỉ tenant

Thông thường:
- **401/challenge** nếu chưa xác thực.
- **403** nếu đã xác thực nhưng thiếu quyền chức năng hoặc policy từ chối và việc tiết lộ phù hợp.
- **404** cho resource không có trong tập actor được phép xem, tránh xác nhận document khác tenant có tồn tại.
- **5xx/503** khi permission/backend không khả dụng, không thực hiện side effect.

Đây là lựa chọn thiết kế API, không phải mã HTTP Spring tự động gán cho mọi exception. `ExceptionTranslationFilter` xử lý các exception bảo mật trong phạm vi thích hợp; lỗi hạ tầng cần exception mapping riêng.

Không gọi lại `findById(id)` không scoped chỉ để trả thông báo “document thuộc tenant south, owner Bob”; chính thông báo đó có thể rò thông tin. Audit nội bộ nên ghi subject đã xác minh, tenant, action, ID ở mức cho phép, result, policy version và correlation ID; không log raw token/ACL/content ngoài quyền.

## 22. Java 17 độc lập: quyết định đủ bốn chiều

Chương trình sau chạy bằng JDK 17 không cần Spring. Nó mô hình hóa **subject được namespace theo issuer**, role theo tenant, object owner, grant READ theo document/action, trạng thái locked và từ chối mặc định.

Tạo file `TenantDecisionDemo.java`:

~~~java
import java.util.Set;
import java.util.stream.Collectors;

public class TenantDecisionDemo {
    enum Role { READER, EDITOR, TENANT_ADMIN }
    enum Action { READ, WRITE, DELETE }

    record Membership(String tenant, Role role) { }

    record Actor(
            String issuer, String subject,
            Set<Membership> memberships) {
        String key() { return issuer + "|" + subject; }
    }

    record Document(
            long id, String tenant, String ownerKey, boolean locked) { }

    record Grant(
            String tenant, long documentId,
            String subjectKey, Action action) { }

    static boolean roleAllows(Role role, Action action) {
        return switch (role) {
            case READER -> action == Action.READ;
            case EDITOR -> action == Action.READ || action == Action.WRITE;
            case TENANT_ADMIN -> true;
        };
    }

    static boolean allowed(
            Actor actor, Document document,
            Action action, Set<Grant> grants) {

        if (actor == null || document == null || action == null
                || grants == null || actor.memberships() == null
                || actor.issuer() == null || actor.issuer().isBlank()
                || actor.subject() == null || actor.subject().isBlank()
                || document.id() <= 0
                || document.tenant() == null || document.tenant().isBlank()
                || document.ownerKey() == null) {
            return false;
        }

        Set<Role> roles = actor.memberships().stream()
                .filter(m -> m != null
                        && document.tenant().equals(m.tenant()))
                .map(Membership::role)
                .filter(r -> r != null)
                .collect(Collectors.toSet());

        if (roles.stream().noneMatch(r -> roleAllows(r, action))) {
            return false;
        }

        if (document.locked() && action != Action.READ) {
            return false;
        }

        boolean owner = document.ownerKey().equals(actor.key());
        boolean admin = roles.contains(Role.TENANT_ADMIN);
        boolean shared = grants.contains(new Grant(
                document.tenant(), document.id(), actor.key(), action));

        return owner || admin || shared;
    }

    public static void main(String[] args) {
        Document document =
                new Document(42, "north", "issuerA|an", false);
        Document locked =
                new Document(43, "north", "issuerA|an", true);

        Actor an = new Actor("issuerA", "an",
                Set.of(new Membership("north", Role.EDITOR)));
        Actor binh = new Actor("issuerA", "binh",
                Set.of(new Membership("north", Role.READER)));
        Actor chi = new Actor("issuerA", "chi",
                Set.of(new Membership("north", Role.EDITOR)));
        Actor southAdmin = new Actor("issuerA", "admin",
                Set.of(new Membership("south", Role.TENANT_ADMIN)));
        Actor otherIssuerAn = new Actor("issuerB", "an",
                Set.of(new Membership("north", Role.EDITOR)));

        Set<Grant> grants = Set.of(
                new Grant("north", 42, "issuerA|binh", Action.READ));

        System.out.println("owner-write="
                + allowed(an, document, Action.WRITE, grants));
        System.out.println("shared-read="
                + allowed(binh, document, Action.READ, grants));
        System.out.println("shared-write="
                + allowed(binh, document, Action.WRITE, grants));
        System.out.println("unshared-editor="
                + allowed(chi, document, Action.WRITE, grants));
        System.out.println("other-tenant-admin="
                + allowed(southAdmin, document, Action.READ, grants));
        System.out.println("same-sub-other-issuer="
                + allowed(otherIssuerAn, document, Action.WRITE, grants));
        System.out.println("locked-owner-write="
                + allowed(an, locked, Action.WRITE, grants));
        System.out.println("after-revoke-read="
                + allowed(binh, document, Action.READ, Set.of()));
        System.out.println("missing-actor="
                + allowed(null, document, Action.READ, grants));
    }
}
~~~

Chạy:

~~~bash
javac TenantDecisionDemo.java
java TenantDecisionDemo
~~~

Stdout chính xác:

~~~text
owner-write=true
shared-read=true
shared-write=false
unshared-editor=false
other-tenant-admin=false
same-sub-other-issuer=false
locked-owner-write=false
after-revoke-read=false
missing-actor=false
~~~

Đọc kết quả:
- An là owner và EDITOR tại north, nên WRITE khi document ACTIVE/không locked.
- Bình được share READ, có role READER tại north; WRITE vẫn bị chặn.
- Chi có EDITOR nhưng không phải owner và không có grant nên không sửa document của An.
- Tenant admin south không có role tương ứng trong north.
- `issuerB|an` khác `issuerA|an` dù cùng `sub="an"`.
- Document bị locked chặn WRITE của cả owner trong policy ví dụ.
- Revoke grant hoặc thiếu actor đều DENY.

**Giới hạn:** Đây là mô phỏng in-memory, không có JWT validation, database, transaction, role expiry, ACL inheritance hay cache. Mã domain thật phải cấp actor/membership/grant từ nguồn đã xác minh và xác định policy revocation.

## 23. Đồng bộ quyền theo thời điểm dùng: TOCTOU

Một quyết định role/ACL đúng tại T1 có thể không đúng T2:

~~~text
T1: Alice có EDITOR north, có grant WRITE document 42.
T2: Admin thu hồi membership/grant hoặc chuyển document tenant.
T3: Alice dùng quyết định cache cũ để UPDATE document 42.
~~~

Với owner-only, có thể dùng guarded UPDATE:

~~~sql
UPDATE documents
SET title = :new_title,
    version = version + 1
WHERE id = :id
  AND tenant_id = :verified_tenant
  AND owner_subject_key = :verified_subject
  AND status = 'ACTIVE'
  AND version = :expected_version;
~~~

Kiểm tra affected rows: 1 thường là một record cập nhật; 0 là không có record nào thỏa đồng thời ID/tenant/owner/status/version, **không được trả success**.

Với quyền ở bảng `document_grants` khác hoặc remote policy service, cần đọc/khóa/version/recheck phù hợp theo consistency yêu cầu. `@Transactional` không tự bao trùm service ngoài DB. `@Version` trên document cũng không tự tăng khi một grant ở bảng khác bị thu hồi. Test interleaving có khóa/latch thật để chứng minh đường UPDATE/DELETE không dùng quyền cũ ngoài contract.

## 24. Cache, token stale và revoke

Một permission cache nên key theo đủ các chiều, ví dụ:

~~~text
(issuer, subject, tenant, resourceType, resourceId,
 action, policyVersion)
~~~

Đây là **mô hình minh họa**, không phải class API Spring. Tùy domain còn cần group/ACL revision, resource state, token expiry và context khác. Một cache chỉ theo `resourceId` hay `subject` rất nguy hiểm trong multi-tenant/multi-issuer.

Các sự kiện có thể cần invalidation:
- User rời tenant, bị suspend hoặc hạ role.
- Thay đổi owner, project membership hoặc tenant của resource.
- Grant được cấp/thu hồi, document bị locked.
- Chính sách business hoặc issuer trust thay đổi.
- Session/token bị revoke.

Nếu JWT có role cũ và còn hạn, không thể hứa quyền bị thu hồi tức thì khi hệ chỉ dựa vào token. Xác định **revocation SLA**, TTL, revision check và hành động nào phải đánh giá lại quyền ở nguồn đáng tin.

Cache miss hoặc permission backend timeout không được biến thành ALLOW; xử lý fail closed và báo lỗi vận hành phù hợp.

## 25. Cách ly tenant ở database và đường non-HTTP

Các kiến trúc phổ biến:
- Shared DB/shared schema, mỗi row có tenant ID và mọi query scoped.
- Shared DB/separate schemas, datasource/schema routing theo tenant đáng tin.
- Database per tenant, routing, migration và cache isolation tương ứng.
- Database Row-Level Security (RLS) làm lớp bảo vệ sâu khi cấu hình đúng.

Dù chọn kiến trúc nào:
- Validate membership trước khi route datasource/schema.
- Resource tenant được lấy từ DB, không client body.
- Owner/grant subject namespace đúng issuer.
- Permission theo action, không dùng một boolean `canAccess` mơ hồ.
- Cache/search index/list/count/export/download giữ cùng tenant scope.
- Connection pool/session context được reset đúng giữa request nếu dùng RLS/schema routing.

Một lỗi điển hình: detail API scoped, nhưng export job gọi `findAllByStatus("ACTIVE")` và trả dữ liệu mọi tenant. Bảo vệ phải tồn tại ở service/repository và các đường chạy asynchronous/message/batch, không chỉ trên controller HTTP.

## 26. Kiểm thử ma trận tenant, subject, role và resource

| Tình huống | Kỳ vọng |
|---|---|
| Owner, đúng tenant, role cho phép, trạng thái hợp lệ | ALLOW |
| User đúng role nhưng không owner, không grant | DENY |
| User là EDITOR tenant A, resource thuộc B | DENY |
| User READER tại B nhưng yêu cầu WRITE | DENY |
| User READER B có grant READ đúng object | READ ALLOW |
| Role TENANT_ADMIN của A, document B | DENY |
| Hai issuer trùng subject string | Không nhầm actor |
| Role/membership bị revoked/expired | DENY theo SLA |
| Resource đổi tenant/owner | Không truy cập qua scope cũ |
| Grant chỉ READ, caller yêu cầu DELETE | DENY |
| Grant khác document ID | Không cấp quyền cho object đang hỏi |
| Grant expired, revoked hoặc sai tenant | DENY |
| Document LOCKED, owner yêu cầu WRITE | DENY |
| Không có authentication/tenant/subject | Không cấp |
| Permission backend null/timeout | Không side effect |
| SQL OR đặt sai ngoặc | Test phải bắt được rò khác ID/tenant |
| Global support có capability hợp lệ | Chỉ theo scope/time/audit đã thiết kế |

Cần **integration test** với Spring Security thật:
1. HTTP SecurityFilterChain có matcher/fallback phù hợp.
2. `@EnableMethodSecurity` được bật, service được gọi qua Spring-managed proxy.
3. Principal của test có issuer + subject + tenant membership theo contract; `@WithMockUser` mặc định không tạo custom tenant claim.
4. JPA query xác minh tenant và resource ID; không phụ thuộc DTO client.
5. Test tenant-local ID trùng nhau, subject ID trùng khác issuer.
6. Role, ACL, owner, project và resource status cho kết quả độc lập đúng.
7. Grant/role bị revoke không tạo cache ALLOW ngoài SLA.
8. List/count/search/export/download dùng cùng scope với detail.
9. WRITE/DELETE denied không thay đổi database, event hoặc file.
10. Message worker/direct service invocation cũng đi qua policy hợp lệ.

Đừng chỉ assert HTTP 403. Kiểm tra state sau request, audit, cache và số record trả về để chứng minh không có rò dữ liệu.

## 27. Những lỗi thường gặp

**1. Dùng role ADMIN toàn cục cho tenant admin.** Quyền cục bộ mở sang tenant khác. **Sửa:** role gắn tenant, global capability riêng.

**2. Tin X-Tenant-Id là membership.** Client có thể đổi tenant. **Sửa:** validate target tenant với membership đáng tin.

**3. Chỉ dùng sub không có issuer namespace.** Trùng subject giữa identity providers. **Sửa:** validated issuer+subject hoặc internal principal.

**4. Chỉ kiểm tra role mà bỏ owner/ACL.** Một EDITOR sửa object của người khác. **Sửa:** object permission riêng.

**5. Role hợp lệ nhưng resource tenant khác.** Truy cập chéo tenant. **Sửa:** query ID AND tenant.

**6. Share READ được dùng cho WRITE.** Quyền thấp mở mutation. **Sửa:** action-specific policy.

**7. SQL AND/OR thiếu ngoặc.** Nhánh grant bỏ qua tenant/ID. **Sửa:** mọi mandatory guards ở ngoài OR.

**8. Tenant/subject null làm optional SQL filter.** Rộng phạm vi khi thiếu identity. **Sửa:** required scope, fail closed.

**9. Cache chỉ theo document ID.** ALLOW của tenant/subject khác bị dùng lại. **Sửa:** complete key + invalidation.

**10. Chỉ bảo vệ HTTP, quên job/export.** Service không có data authorization. **Sửa:** policy ở service/query boundary.

**11. JWT còn hạn nên coi membership chưa đổi.** Token stale sau revoke. **Sửa:** TTL/revision/recheck theo risk.

**12. Tưởng @Transactional tự giải quyết mọi permission race.** ACL backend bên ngoài vẫn có thể thay đổi. **Sửa:** consistency protocol hoặc guarded mutation.

**13. Cho phép khi permission service lỗi.** Fail-open. **Sửa:** không thực thi action nếu không xác minh đủ quyền.

**14. Tự suy luận public khi owner/ACL null.** Dữ liệu lỗi biến thành truy cập công khai. **Sửa:** explicit public policy.

## 28. Checklist thiết kế trước khi merge

- [ ] Subject được xác thực; có issuer namespace nếu cần.
- [ ] Tenant target được so với active membership, không chỉ header/path.
- [ ] Role/action được scope theo tenant, không nhầm TENANT_ADMIN với global admin.
- [ ] Resource ID, tenant, owner, trạng thái lấy từ nguồn server đáng tin.
- [ ] Role gate và object gate đều có hiệu lực.
- [ ] READ/WRITE/DELETE/SHARE dùng permission riêng.
- [ ] SQL/JPQL có ràng buộc ID + tenant + (owner OR grant) đúng dấu ngoặc.
- [ ] Grant hết hạn/revoked, group role stale và tenant move đều được test.
- [ ] Thiếu authentication/membership/ACL/backend lỗi đều fail closed.
- [ ] Không tin `userId`, `ownerId`, `tenantId` hoặc `isAdmin` do client khai.
- [ ] Method security chạy qua proxy, policy dùng được từ non-HTTP entrypoint.
- [ ] List/count/export/download và cache tách tenant đúng cách.
- [ ] Side effect được guarded và test không xảy ra khi denied.
- [ ] Có cache invalidation/revocation SLA và audit không lộ token.
- [ ] Có test ID trùng giữa tenant, sub trùng giữa issuer và role khác nhau giữa tenant.
- [ ] Quyền global/public/cross-tenant là ngoại lệ có scope và audit rõ.

**Kết luận:** Hãy ra quyết định trên **đúng subject đã xác thực**, **đúng tenant mà subject được phép tham gia**, **role hỗ trợ action tại tenant đó**, và **tài nguyên cụ thể với owner/ACL/trạng thái hiện hành**. Spring Security cung cấp authentication và framework interception; ứng dụng phải cung cấp tenant membership, role scoping, object policy, query guard và kiểm thử để không mở quyền chéo tenant.

## Tài liệu tham khảo

- [Spring Security – Method Security](https://docs.spring.io/spring-security/reference/servlet/authorization/method-security.html): `@EnableMethodSecurity`, `@PreAuthorize`, method interceptor và policy beans.
- [Spring Security – Authorize HttpServletRequests](https://docs.spring.io/spring-security/reference/servlet/authorization/authorize-http-requests.html): request authorization, `AuthorizationManager`, `hasAuthority`.
- [Spring Security – Authorization Architecture](https://docs.spring.io/spring-security/reference/servlet/authorization/architecture.html): manager decisions và các ranh giới.
- [Spring Security – OAuth 2.0 Resource Server Multi-tenancy](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/multitenancy.html): issuer resolver, trusted issuers và multi-tenant authentication.
- [Spring Security – OAuth 2.0 Resource Server JWT](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html): JWT verification và issuer validation.
- [Spring Data JPA – JPA Query Methods](https://docs.spring.io/spring-data/jpa/reference/jpa/query-methods.html): derived queries, `@Query` và parameter binding.
- [Spring Security – Domain Object Security (ACLs)](https://docs.spring.io/spring-security/reference/servlet/authorization/acls.html): quyền trên từng object.
- [OWASP API Security Top 10 (2023) – BOLA](https://owasp.org/API-Security/editions/2023/en/0xa1-broken-object-level-authorization/): chống truy cập dữ liệu theo object ID trái quyền.
