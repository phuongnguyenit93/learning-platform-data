# Cách ly dữ liệu hai tenant và kiểm thử thay đổi định danh

## 1. Mục tiêu và tình huống thực hành

Trong ứng dụng SaaS sử dụng Spring Security, **xác thực thành công chưa có nghĩa là người gọi được truy cập mọi dữ liệu**. Một người dùng thuộc tenant A có thể có `ROLE_ADMIN` hoặc `SCOPE_documents.read` hợp lệ nhưng vẫn **không được đọc tài liệu tenant B**. Lỗi kiểm soát đối tượng (Broken Object Level Authorization/IDOR) thường xuất hiện khi code chỉ xét user đã đăng nhập, chỉ kiểm role/scope chức năng, hoặc dùng `tenantId` từ URL/header/body mà không xác minh nó có thuộc phạm vi của principal hiện tại.

Bài thực hành này tạo hai tenant có dữ liệu trùng mã, chuyển đổi danh tính người gọi và chọn tenant, rồi thử cả đường hợp lệ lẫn cố ý vượt ranh giới. Điểm khó là kiểm được **thực thể đã truy cập và tác động trong database**, không chỉ kiểm status HTTP. Hành vi an toàn phải giữ nguyên khi thay đổi `Authentication` từ Alice sang Bob, khi một người có nhiều tenant được chọn tenant khác, khi quyền membership bị thu hồi và khi thread/session/cache được tái sử dụng.

**Mục tiêu đầu ra:**

1. Dựng fixture **hai tenant A/B** với cùng một local document ID nhưng nội dung khác nhau để phát hiện thiếu tenant predicate.
2. Phân biệt **authenticated identity (issuer + subject)**, **tenant được chọn**, **membership/role trong tenant** và **permission trên tài nguyên**.
3. Viết route, service và repository chỉ dùng tenant context **đã xác minh**, không dùng trực tiếp tenant do client khai báo làm thẩm quyền.
4. Kiểm thử **identity switching**: đổi access token/principal giữa các request, chọn tenant khác hợp lệ và bất hợp lệ, đổi quyền membership sau đăng nhập, đăng xuất/đăng nhập lại.
5. Bao phủ đọc, ghi, xóa, liệt kê, tìm kiếm, bulk/export, quan hệ cha-con, cache và job nền để tránh lộ dữ liệu phụ.
6. Có ma trận allow/deny, positive control, kiểm trạng thái DB trước–sau, kiểm boundary ở JWT, MVC, service và repository.

**Phạm vi:** ví dụ áp dụng cho Spring Boot 3+ / Spring Security 6.x/7.x ở Servlet stack; ý tưởng tenant-isolation độc lập phiên bản. Các snippet Spring là mảnh tích hợp cần bean/repository của ứng dụng thật. Chương trình Java 17 độc lập ở mục 10 chạy không cần Spring để kiểm logic bất biến.

## 2. Thiết lập mô hình hai tenant

Một tenant là ranh giới dữ liệu và chính sách. Ở mô hình shared database, mỗi bản ghi thuộc tenant nào phải được xác định đáng tin cậy; tenant không nhất thiết đồng nghĩa user, organization hay subdomain. Người dùng có thể thuộc nhiều tenant, có role khác nhau ở từng tenant hoặc tạm mất membership.

| Thực thể | Tenant A | Tenant B |
| --- | --- | --- |
| Người dùng thường | `alice` là thành viên A | `bob` là thành viên B |
| Thành viên của cả hai | `casey` là thành viên A | `casey` cũng là thành viên B |
| Quản trị viên theo tenant | `admin-a` có `TENANT_ADMIN` **ở A** | Không có role nào ở B |
| Tài liệu trùng local ID | `D-7`: `"alpha-secret"`, owner Alice | `D-7`: `"bravo-secret"`, owner Bob |
| Tài liệu khác | `A-9` | `B-9` |
| Dự án liên quan | `P-1` của A | `P-1` của B, ID trùng nhưng khác bản ghi |

Chọn cùng mã `D-7` ở hai tenant **có chủ đích**: nếu repository dùng `findById("D-7")` mà không scope theo tenant, test có thể vô tình đọc/ghi bản ghi không mong đợi. ID toàn cục UUID vẫn cần authorization, nhưng local ID trùng giúp lỗi lộ ra nhanh hơn.

Giả định permission chức năng:

- `documents.read`: được thử đọc/list/search tài liệu trong tenant và trên đối tượng mình có quyền.
- `documents.write`: được thử tạo/sửa tài liệu hợp lệ trong tenant.
- `documents.delete`: được thử xóa tài liệu hợp lệ trong tenant.
- `documents.export`: được thử xuất các tài liệu được phép, không phải mọi dữ liệu toàn hệ thống.
- `TENANT_ADMIN`: role quản trị **chỉ trong tenant đã được gán**, không phải `SUPER_ADMIN` toàn cục.
- Người được chia sẻ tài liệu có thể xem theo ACL; membership **chưa chắc đủ** nếu hệ thống còn hạn chế theo owner/team/project.

Định nghĩa quyết định quyền tối thiểu:

~~~text
ALLOW(actor, action, requestedTenant, resource)
  = authenticatedAndTrusted(actor)
  AND hasFunctionalPermission(actor, action)
  AND activeMembership(actor, requestedTenant, action)
  AND resource.tenantId == requestedTenant
  AND objectPolicyAllows(actor, action, resource)
~~~

Với `CREATE` chưa có resource, thay điều kiện resource bằng parent/container tenant đã xác minh và kiểm toàn bộ references đầu vào. Với hoạt động hệ thống xuyên tenant, phải định nghĩa service principal và scope riêng, không tự bỏ qua những điều kiện bên trên.

## 3. Danh tính thực thi không phải là tenant được chọn

### 3.1. Authentication: ai đang gọi?

Trong resource server JWT, identity nên có khóa ổn định theo hợp đồng, ví dụ `(issuer, sub)`: cùng `sub=alice` do hai issuer khác nhau phát **không tự** đồng nghĩa cùng một user nội bộ. Spring Security cần kiểm token signature, thời hạn, issuer và **audience của API này** theo cấu hình; một chuỗi JWT đã decode hoặc `X-User-Id` do client gửi không phải authentication hợp lệ.

`JwtAuthenticationToken#getName()` mặc định thường dựa trên `sub`, nhưng custom `JwtAuthenticationConverter` có thể chọn một claim tên khác. Khi triển khai hãy quyết định nguồn `PrincipalRef` một cách tường minh và đồng nhất (issuer + stable subject/internal user ID), không dựa vào email/display name vì chúng có thể đổi hoặc trùng.

Ví dụ token JSON mô tả **claim minh họa** (không phải JWT ký thật):

~~~json
{
  "iss": "https://login.example.test",
  "aud": ["documents-api"],
  "sub": "alice",
  "scope": "documents.read documents.write",
  "tenant_id": "A"
}
~~~

Trong trường hợp token đã ký hợp lệ, claim `tenant_id=A` có thể dùng để biểu diễn tenant mặc định **nếu contract của issuer như vậy**. Nhưng một claim hợp lệ không luôn phản ánh membership hiện hành sau khi bị thu hồi; tùy mức rủi ro, service phải kiểm lại membership tại server, token expiry/refresh/revocation hoặc phiên bản quyền.

### 3.2. Tenant selection: đang làm việc trong phạm vi nào?

Có thể chọn tenant bằng `/api/tenants/{tenantId}/...`, subdomain hoặc `X-Tenant-Id`. Tất cả chỉ là **selector**; không phải bằng chứng rằng người dùng thuộc tenant đó. Bộ kiểm chuẩn:

1. Lấy actor từ `Authentication`/JWT đã được framework xác minh.
2. Nhận `requestedTenant` từ URL/header hoặc từ lựa chọn ứng dụng.
3. Tra **active membership/role/permission** của actor trên đúng tenant được chọn.
4. Xây `VerifiedTenantContext(actorId, tenantId, allowedActions)` ở phía server; context không được client tự xây và không được tự chứa quyền chưa kiểm chứng.
5. Dùng `tenantId` đã xác minh trong **mọi truy vấn**, khóa cache, file path, quan hệ dữ liệu và job.
6. Khi đổi tenant, kiểm lại membership; không giữ một context A từ request cũ rồi áp cho request B.

Nếu Casey thuộc A và B, việc chuyển từ A sang B **có thể hợp lệ** sau khi kiểm membership. Nếu Alice chỉ thuộc A, thay `X-Tenant-Id` từ A sang B **không** biến cô ấy thành thành viên B. Nếu Alice có `ROLE_TENANT_ADMIN` ở A, role đó không cấp quyền cho B.

### 3.3. Kiểm thử “thay đổi định danh” là gì?

Có **ít nhất ba trục thay đổi** cần tách riêng:

| Trục | Ví dụ | Quyết định đúng |
| --- | --- | --- |
| **Đổi principal** | Request 1 token Alice, request 2 token Bob | Request 2 chỉ có quyền Bob; không dính principal/tenant của Alice |
| **Cùng principal, đổi tenant** | Casey từ A sang B; Alice thử từ A sang B | Casey được chuyển theo membership B; Alice bị từ chối |
| **Danh tính/quan hệ thay đổi theo thời gian** | Alice bị khóa; Casey mất membership B; email đổi | Quyền cập nhật theo policy, không dùng dữ liệu/cached authority cũ vô hạn |

Còn một kiểu tấn công khác: sửa chuỗi `sub` hoặc `tenant_id` trong JWT để mạo danh. Với token được ký, sửa payload không ký lại đúng khóa issuer phải bị authentication layer từ chối (thường 401). Test bằng `jwt()` MockMvc với `sub=bob` chỉ **mô phỏng request của Bob**; nó không chứng minh một attacker đã sửa được token của Alice.

## 4. Threat model: các chỗ rò dữ liệu chéo tenant

### 4.1. Đọc trực tiếp tài liệu bằng ID (IDOR/BOLA)

Sai:

~~~java
// Sai: cùng local ID có thể tồn tại ở hai tenant.
Document doc = repository.findById(documentId).orElseThrow();
return mapper.toDto(doc);
~~~

Đúng ở mô hình shared-table:

~~~java
Document doc = repository
    .findByTenantIdAndDocumentId(verifiedTenant, documentId)
    .orElseThrow(NotFoundException::new);
policy.requireCanRead(verifiedActor, doc);
return mapper.toDto(doc);
~~~

`verifiedTenant` được ràng buộc từ identity/membership, không phải đọc trực tiếp `request.getHeader("X-Tenant-Id")` mà bỏ bước xác minh. Nếu repository dùng primary key tổng hợp `(tenantId, documentId)` thì lookup cũng phải dùng đủ hai thành phần.

### 4.2. Chỉ kiểm `hasRole`/`hasAuthority` nhưng quên object policy

~~~java
// Sai nếu ROLE_ADMIN chỉ là quyền quản trị theo tenant.
@PreAuthorize("hasRole('ADMIN')")
public Document read(String documentId) {
    return repository.findById(documentId).orElseThrow();
}
~~~

Một actor có role quản trị trong A có thể truy cập record của B nếu không có tenant predicate. Cần kết hợp functional authority, membership tenant và object-level authorization. `ROLE_ADMIN` toàn cục nếu tồn tại phải có contract/capability đặc biệt, ghi audit và kiểm riêng.

### 4.3. Danh sách và tìm kiếm không scope

`GET /documents?tenant=B`, search full text, autocomplete, count, pagination, sort và facets đều có thể rò số lượng/tên file dù GET từng document bị bảo vệ. Query cần đưa tenant predicate **vào DB/search backend**, không lấy toàn bộ rồi filter trong Java sau đó. Áp dụng với `SELECT COUNT(*)`, exports, result caching và joins.

### 4.4. Ghi/di chuyển liên tenant qua DTO

Client gửi body:

~~~json
{
  "title": "updated",
  "tenantId": "B",
  "ownerId": "bob",
  "projectId": "P-1"
}
~~~

Nếu backend map JSON tự động vào entity bằng setter rồi `save(entity)`, Alice có thể cố thay tenant/owner hoặc gắn project P-1 của B. Thiết kế DTO chỉ cho các field được phép sửa; tenant là immutable hoặc được đổi qua một **workflow transfer** với kiểm quyền ở cả nguồn/đích; mọi foreign key tới project/customer/invoice phải được kiểm tenant đích.

### 4.5. Repository/cache/storage/job bỏ qua tenant

Một cache key `document:D-7` là không đủ nếu ID trùng; phải dùng `tenant:A:document:D-7` hoặc key gồm tenant + principal/action/version khi response phụ thuộc quyền user. File `exports/J-100.csv` không thể được tải chỉ vì client biết `jobId`; kiểm owner/tenant lúc download. Queue message mang `tenantId=B` không tự chứng minh runner được quyền B; re-establish policy ở consumer.

### 4.6. Thread/session đổi principal nhưng context còn cũ

Nếu một singleton bean giữ `currentUser` trong field, một thread pool không clear `SecurityContextHolder`, hoặc một mutable `TenantContext` `ThreadLocal` không dọn trong `finally`, request Bob có thể vô tình dùng tenant A/identity Alice. Spring Security filter chain thông thường quản lý context của mỗi request, nhưng custom filter/cache/asynchronous code vẫn phải đảm bảo lifecycle. Test **thứ tự A→B→A**, cùng pool và sau exception, không chỉ test A và B mỗi người trong một test riêng biệt.

## 5. Kiến trúc kiểm soát theo lớp

~~~mermaid
flowchart TD
  A[HTTP: token + tenant selector + resource ID] --> B[Spring Security: validate JWT, issuer, audience]
  B --> C{Đã xác thực?}
  C -->|Không| X[401 hoặc lỗi authentication tương đương]
  C -->|Có| D[PrincipalRef: issuer + stable subject]
  D --> E[Kiểm functional scope/role]
  E --> F{Actor là thành viên tenant được chọn?}
  F -->|Không| Y[403 hoặc 404 thống nhất theo policy]
  F -->|Có| G[VerifiedTenantContext]
  G --> H[Service kiểm object action/ACL]
  H --> I[Repository query có tenant predicate]
  I --> J{Record thuộc tenant và policy cho phép?}
  J -->|Không| Z[403/404, không side effect]
  J -->|Có| K[Trả dữ liệu hoặc transaction ghi giới hạn tenant]
~~~

Các tầng bảo vệ:

- **SecurityFilterChain**: bảo đảm request API được authenticated và có policy chức năng; route không tự `permitAll` vì khớp sai path.
- **Method security**: `@PreAuthorize` kiểm authority chức năng, có thể gọi policy bean dựa trên tham số. Bật `@EnableMethodSecurity`. Method phải đi qua Spring proxy, tránh self-invocation bypass.
- **Tenant membership service**: xác nhận actor, tenant, quyền hiện hành từ nguồn tin cậy; role theo tenant không được chuyển thành role global.
- **Domain/object policy**: quyền sở hữu, ACL, trạng thái tài liệu, project membership và action. Dữ liệu đầu vào do client chọn không được thay nguồn sự thật.
- **Persistence/DB**: truy vấn bắt buộc có tenant scope; có thể thêm composite keys, foreign keys theo tenant, RLS, tách schema/DB khi cần defense in depth.
- **Output layers**: response, cache, event, search index, export, object storage và log đều giữ tenant boundary.

Không có một annotation duy nhất bảo đảm mọi lớp. Đặc biệt, `@PreAuthorize("hasAuthority('SCOPE_documents.read')")` chỉ xác nhận scope có trong `Authentication`, **không** tự xác minh user thuộc A/B hay record thuộc tenant nào.

## 6. Spring Security: mẫu thiết kế để thử trực tiếp

Các đoạn dưới là **mảnh Java tích hợp Spring Security Servlet**, không phải một project biên dịch độc lập. Cần các bean `JwtDecoder`, `IdentityResolver`, `TenantMembershipService`, `DocumentRepository`, `DocumentPolicy` và DTO/controller thực. Ví dụ dùng `@AuthenticationPrincipal Jwt` cho resource server JWT; nếu app dùng session/OIDC, thay identity resolver tương ứng nhưng giữ các invariant.

### 6.1. Bảo vệ request entrypoint

~~~java
@Configuration
@EnableMethodSecurity
class DocumentSecurityConfig {
    @Bean
    SecurityFilterChain documentsSecurity(HttpSecurity http)
            throws Exception {
        http.authorizeHttpRequests(auth -> auth
            .requestMatchers("/api/tenants/**").authenticated()
            .anyRequest().denyAll()
        ).oauth2ResourceServer(oauth2 ->
            oauth2.jwt(Customizer.withDefaults())
        );
        return http.build();
    }
}
~~~

Bổ sung import `@Configuration`, `@EnableMethodSecurity`, `@Bean`, `SecurityFilterChain`, `HttpSecurity` và `Customizer`. Ứng dụng phải cấu hình JWT decoder và validators phù hợp cho `issuer`/`audience`. Với CSRF, cấu hình theo hình thức authentication: bearer-token API không dùng cookie/session có threat model khác cookie-auth; **không tắt CSRF toàn hệ thống chỉ để test POST dễ hơn**. Rule `authenticated()` chỉ làm cửa vào; service bên dưới buộc phải kiểm tenant/action/object. Với các route khác, `denyAll` là default thận trọng trong ví dụ.

### 6.2. Controller: tenant path là yêu cầu, không phải quyền

~~~java
@RestController
@RequestMapping("/api/tenants/{tenantId}/documents")
class DocumentController {
    private final DocumentService documents;

    DocumentController(DocumentService documents) {
        this.documents = documents;
    }

    @GetMapping("/{documentId}")
    DocumentView get(@AuthenticationPrincipal Jwt jwt,
                     @PathVariable String tenantId,
                     @PathVariable String documentId) {
        return documents.read(jwt, tenantId, documentId);
    }

    @PatchMapping("/{documentId}")
    DocumentView rename(@AuthenticationPrincipal Jwt jwt,
                        @PathVariable String tenantId,
                        @PathVariable String documentId,
                        @RequestBody RenameDocument request) {
        return documents.rename(jwt, tenantId, documentId, request.title());
    }
}

record RenameDocument(String title) {}
~~~

Controller **không** chấp nhận `requestedBy`, `role`, `ownerId`, `tenantId` tùy ý từ JSON body làm thẩm quyền. URL `tenantId` là selector; muốn vào B phải thông qua membership/policy. `@AuthenticationPrincipal Jwt` chỉ có sau khi authentication JWT hợp lệ trong pipeline.

### 6.3. Service: actor và tenant được kiểm trước lookup

~~~java
@Service
class DocumentService {
    private final IdentityResolver identities;
    private final TenantMembershipService memberships;
    private final DocumentRepository repository;
    private final DocumentPolicy policy;

    DocumentService(IdentityResolver identities,
                    TenantMembershipService memberships,
                    DocumentRepository repository,
                    DocumentPolicy policy) {
        this.identities = identities;
        this.memberships = memberships;
        this.repository = repository;
        this.policy = policy;
    }

    @Transactional(readOnly = true)
    @PreAuthorize("hasAuthority('SCOPE_documents.read')")
    public DocumentView read(Jwt verifiedJwt, String tenantId, String id) {
        PrincipalRef actor = identities.fromVerifiedJwt(verifiedJwt);
        memberships.requireActive(actor, tenantId, "documents.read");

        Document doc = repository.findByTenantIdAndDocumentId(tenantId, id)
            .orElseThrow(NotFoundException::new);

        policy.requireCanRead(actor, tenantId, doc);
        return DocumentView.from(doc);
    }

    @Transactional
    @PreAuthorize("hasAuthority('SCOPE_documents.write')")
    public DocumentView rename(Jwt verifiedJwt, String tenantId,
                               String id, String newTitle) {
        PrincipalRef actor = identities.fromVerifiedJwt(verifiedJwt);
        memberships.requireActive(actor, tenantId, "documents.write");

        Document doc = repository.findByTenantIdAndDocumentId(tenantId, id)
            .orElseThrow(NotFoundException::new);
        policy.requireCanRename(actor, tenantId, doc);

        doc.renameTitle(newTitle); // Không cho đổi tenantId qua request.
        return DocumentView.from(doc);
    }
}
~~~

Đây là **khung nghiệp vụ**, các lớp tên `PrincipalRef`, `IdentityResolver`, `TenantMembershipService`, `DocumentPolicy`, `DocumentView` và `NotFoundException` cần hiện thực theo project. `Document#renameTitle` phải validate input và nằm trong transaction; JPA dirty checking có thể persist trong transaction nếu entity managed. `identities.fromVerifiedJwt` chỉ nhận JWT đã qua pipeline; trong test không tự tạo raw token chưa kiểm signature rồi gọi service ở production.

**Lưu ý quan trọng:** `@PreAuthorize` đánh giá `Authentication` hiện hành từ `SecurityContext`, không tin biến `verifiedJwt` chỉ vì nó được truyền vào method. Nếu một collaborator gọi method qua bean proxy dưới một principal khác, controller/service phải giữ identity nhất quán; test tích hợp phải kiểm thực tế. Không gọi `this.rename(...)` nếu kỳ vọng AOP method security chạy.

Để hạn chế TOCTOU khi membership/owner đổi đồng thời với write, dự án nhạy cảm có thể dùng truy vấn `UPDATE ... WHERE tenant_id = ... AND ...` với version/ACL predicate, khóa phù hợp, DB RLS và xác nhận số bản ghi bị cập nhật. Không thể chỉ dựa vào kiểm membership một lần trước một transaction dài rồi coi quyền vĩnh viễn hợp lệ.

### 6.4. Repository và ràng buộc cơ sở dữ liệu

Ví dụ shared-table có local ID trong tenant:

~~~sql
CREATE TABLE tenant_documents (
    tenant_id   VARCHAR(80) NOT NULL,
    document_id VARCHAR(80) NOT NULL,
    owner_id    VARCHAR(120) NOT NULL,
    project_id  VARCHAR(80),
    title       VARCHAR(255) NOT NULL,
    version     BIGINT NOT NULL DEFAULT 0,
    PRIMARY KEY (tenant_id, document_id)
);

CREATE INDEX idx_tenant_documents_owner
    ON tenant_documents (tenant_id, owner_id);
~~~

Khóa tổng hợp ngăn đè lên bản ghi tenant khác có cùng `document_id`. Nếu bảng `projects` cũng khóa theo `(tenant_id, project_id)`, một foreign key tổng hợp có thể giúp ngăn liên kết tài liệu A với dự án B:

~~~sql
-- Giả định projects có PRIMARY KEY (tenant_id, project_id).
ALTER TABLE tenant_documents
ADD CONSTRAINT fk_tenant_documents_project
FOREIGN KEY (tenant_id, project_id)
REFERENCES projects (tenant_id, project_id);
~~~

Nếu cơ sở dữ liệu dùng surrogate UUID toàn cục, vẫn cần tenant predicate và composite index/constraint cho mọi quan hệ trong phạm vi tenant; uniqueness của UUID **không** thay thế authorization.

Truy vấn được scope:

~~~sql
SELECT d.tenant_id, d.document_id, d.title, d.owner_id
FROM tenant_documents AS d
WHERE d.tenant_id = :authorizedTenant
  AND d.document_id = :documentId;
~~~

Ghi có ràng buộc đồng thời tenant và version:

~~~sql
UPDATE tenant_documents
SET title = :newTitle, version = version + 1
WHERE tenant_id = :authorizedTenant
  AND document_id = :documentId
  AND version = :expectedVersion;
~~~

Kiểm số dòng cập nhật bằng `1` trước khi báo thành công; số `0` có thể là không tồn tại, sai tenant hoặc xung đột version, cần xử lý theo error contract. Dù tenant predicate được đưa vào SQL, nguồn `:authorizedTenant` phải là context **đã xác minh** từ membership/policy. Với owner-only editing, query/update phải thêm điều kiện owner/ACL thực sự theo thiết kế.

### 6.5. PostgreSQL Row Level Security và tách DB

Có ba mô hình phổ biến: DB riêng, schema riêng, bảng dùng chung có `tenant_id`. Không có mô hình nào tự an toàn nếu ứng dụng dùng quyền DB quá rộng. Với PostgreSQL RLS, một ví dụ policy khái niệm:

~~~sql
ALTER TABLE tenant_documents ENABLE ROW LEVEL SECURITY;

CREATE POLICY tenant_scope ON tenant_documents
USING (
    tenant_id = current_setting('app.current_tenant', true)
)
WITH CHECK (
    tenant_id = current_setting('app.current_tenant', true)
);
~~~

Cấu hình này đòi hỏi ứng dụng đặt `app.current_tenant` **sau khi** đã xác minh identity/membership, trong transaction phù hợp. Nếu dùng pool, **ưu tiên transaction-local setting** (như `SET LOCAL` hoặc `set_config(..., true)` trong transaction) để context không dính qua connection tiếp theo. Đảm bảo role DB cho request thường không là superuser và không có `BYPASSRLS`; table owner có thể vượt RLS nếu không `FORCE ROW LEVEL SECURITY`. Policy cần được kiểm riêng cho `SELECT/INSERT/UPDATE/DELETE` và mọi tenant-owned table. RLS là defense in depth, không thay authorization HTTP/service.

## 7. Ma trận kiểm thử tích hợp hai tenant

Thống nhất baseline fixture và status theo hợp đồng: chưa xác thực hoặc token invalid thường `401`; authenticated nhưng thiếu authority/membership thường `403`; nhiều API trả `404` cho resource ngoài scope để không làm lộ sự tồn tại. **Chọn một cách nhất quán** và viết test assert behavior; đừng vừa `403` vừa `404` tùy tiện theo tenant ID khiến attacker suy ra resource tồn tại.

| ID | Principal / membership | Request hoặc thao tác | Kỳ vọng | Tác động DB |
| --- | --- | --- | --- | --- |
| T01 | Alice → A | `GET /tenants/A/documents/D-7` | 200, body `alpha-secret` | Không đổi |
| T02 | Bob → B | `GET /tenants/B/documents/D-7` | 200, body `bravo-secret` | Không đổi |
| T03 | Alice → A | `GET /tenants/B/documents/D-7` | Deny (403/404 theo contract) | Không lộ B |
| T04 | Bob → B | `GET /tenants/A/documents/D-7` | Deny | Không lộ A |
| T05 | Alice, role admin ở A | Xóa hoặc liệt kê tài liệu B | Deny | B không đổi |
| T06 | Casey → A và B | Chọn A, rồi B | 200 với đúng data tương ứng | Không trộn cache/context |
| T07 | Casey bị thu hồi membership B | Chọn B với token cũ | Deny theo revocation policy | Không lộ B |
| T08 | Alice có read, thiếu write | PATCH/DELETE trong A | Deny | A không đổi |
| T09 | Alice có write A | PATCH document A với body `tenantId=B` | Không đổi tenant; từ chối field hoặc bỏ qua theo contract | B không đổi |
| T10 | Alice có write A | POST A tham chiếu `projectId=P-1` chỉ thuộc B | Deny / validation error | Không tạo cross-tenant relation |
| T11 | Alice → A | `GET /tenants/A/documents`, search, count, export | Chỉ trả record A được phép | Không lộ metadata B |
| T12 | Request trước Alice, request sau Bob | Dùng cùng pool / session sau switch chính danh | Kết quả request sau là của Bob | Không dùng tenant A còn sót |
| T13 | Token JWT bị sửa `sub`/`tenant_id` nhưng signature invalid | Gọi API | 401 tại authentication | Không truy vấn dữ liệu |
| T14 | Kẻ dùng token đúng chữ ký nhưng sai issuer/audience | Gọi API | 401 theo validation contract | Không truy vấn dữ liệu |
| T15 | User biết object ID của B / download URL B | GET, bulk, download | Deny | Không có side effect |
| T16 | Tenant B có cùng `D-7` với A | Update/Delete A `D-7` | Chỉ bản ghi A thay đổi | B `D-7` nguyên vẹn |

Nếu B dùng ID khác A, một repository không scope `findById` đôi khi vẫn pass mọi test. Vì vậy fixture **trùng local ID** là một test quan trọng; đồng thời thêm ID chỉ có ở B để kiểm enumeration/IDOR.

## 8. Test MockMvc: thay principal theo từng request

Spring Security Test cung cấp `jwt()` cho các bài kiểm request authorization trên JWT principal. Nó tạo mock `Jwt` và `Authentication`, không cần ký token thật. Test sau giả định project đã có route `GET /api/tenants/{tenantId}/documents/{documentId}`, fixture/bean membership và controller từ mục 6.

~~~java
@SpringBootTest
@AutoConfigureMockMvc
class TwoTenantHttpIsolationTest {
    @Autowired MockMvc mvc;

    @Test
    void switchingIdentityMustNotLeakOtherTenant() throws Exception {
        mvc.perform(get("/api/tenants/A/documents/D-7")
                .with(jwt().jwt(j -> j
                    .subject("alice").claim("scope", "documents.read"))))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.tenantId").value("A"));

        mvc.perform(get("/api/tenants/B/documents/D-7")
                .with(jwt().jwt(j -> j
                    .subject("alice").claim("scope", "documents.read"))))
            .andExpect(status().isForbidden());

        // Request tiếp theo có principal khác, không dùng context Alice cũ.
        mvc.perform(get("/api/tenants/B/documents/D-7")
                .with(jwt().jwt(j -> j
                    .subject("bob").claim("scope", "documents.read"))))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.tenantId").value("B"));

        mvc.perform(get("/api/tenants/A/documents/D-7")
                .with(jwt().jwt(j -> j
                    .subject("bob").claim("scope", "documents.read"))))
            .andExpect(status().isForbidden());
    }
}
~~~

Đây là **khung integration test**, không phải class biên dịch độc lập. Các import chính gồm JUnit `@Test`; Spring Boot Test `@SpringBootTest` và `@AutoConfigureMockMvc`; Spring `@Autowired`/`MockMvc`; static `get`, `jwt`, `status`, `jsonPath`. Test giả định unauthorized-membership trả **403** và JSON có trường `tenantId`. Nếu app chủ đích trả 404 ngoài scope, đổi assertion theo hợp đồng và vẫn test không lộ B.

**Giới hạn của `jwt()`:** nó chèn một `JwtAuthenticationToken` giả để kiểm authorization. Nó có thể chạy phần xử lý claims/authorities của test support nhưng **không kiểm chứng signature, issuer, audience bằng production `JwtDecoder`**; còn nếu test dùng `.authorities(...)` thì đang đặt quyền trực tiếp và có thể bỏ qua custom converter runtime. Cần test tách riêng token validator và converter (hoặc dùng signed JWT fixture + test decoder) để khẳng định con đường authentication thật hoạt động.

### Tránh test “đổi token giả” thành test “mạo danh thành công”

Ở trên, request có `sub=bob` trong `jwt()` được hiểu là **Bob đã xác thực** trong bài test. Điều này **không có nghĩa** Alice có thể gửi body `{"sub":"bob"}` hoặc sửa token đang ký thành Bob. Hãy có hai loại test:

- **Identity switching hợp pháp:** Bob thật đăng nhập/được cấp token Bob, request sau kiểm theo Bob.
- **Forgery/spoofing:** client gắn `X-User-Id:bob`, sửa JWT payload sai chữ ký, thêm JSON field `owner=bob` hoặc dùng token sai audience; backend từ chối hoặc bỏ qua mọi giá trị không đáng tin.

Nếu ứng dụng dùng session cookie thay JWT, test logout/login lại với session rotation và context replacement; cùng session cũ không được dùng principal đã sign out. Với ứng dụng stateless, không dùng một singleton field `currentTenant` hoặc một `ThreadLocal` không clear để cache tenant của request trước.

## 9. Unit/integration/E2E: những assertion phải có

### 9.1. Unit test tenant policy

Tách `hasMembership(actor, tenant)`, `hasScope(actor, action)`, `objectPolicy(actor, doc)` thành các decision được kiểm độc lập. Cases bắt buộc: no membership, membership inactive, role A không ở B, user bị disabled, owner B, document không tồn tại, token thiếu permission, Casey chọn được B nhưng không có quyền trên record cá nhân của Bob nếu ACL không cấp.

Đừng mock `membershipService.requireActive(...)` luôn trả thành công trong chính test được gọi là “tenant isolation”; như vậy đã bỏ qua đối tượng cần chứng minh. Có thể dùng fake repository với dataset rõ để unit test, rồi integration test với database thật để xác nhận scope query.

### 9.2. Integration test với database thật

- Seed A `D-7` và B `D-7` có nội dung phân biệt, đồng thời A-9/B-9 để bắt filter sai.
- Trước mỗi test, ghi snapshot DB hoặc dùng transaction rollback có chủ đích; tránh một test đổi state làm test sau phụ thuộc thứ tự.
- Với PATCH Alice A, assert chỉ `tenant=A,id=D-7` đổi; `tenant=B,id=D-7` giữ nguyên title/version/owner/ACL.
- Với DELETE trái phép, assert **row count, soft-delete flag, audit/event/outbox** không bị đổi; response 403 đơn lẻ chưa đủ.
- Search/filter/count/export/bulk phải trả chính xác **tập ID A** hoặc tài liệu được ACL cho phép; không chỉ kiểm `results.size()`, vì tập dữ liệu của A và B có thể cùng kích thước.
- Với join `tenant_documents.project_id`, seed `P-1` ở cả A/B và kiểm foreign key/tenant condition, nếu thiếu có thể join nhầm project B.
- Dùng database thực sự tương thích production (ví dụ PostgreSQL nếu dựa vào RLS); H2 không thể chứng minh policy RLS của PostgreSQL.

### 9.3. Test thay đổi danh tính trong cùng phiên/cùng pool

Một test nên đi theo chuỗi, không chỉ hai test riêng độc lập:

~~~text
1. Alice (A) đọc A/D-7 -> alpha-secret
2. Alice cố chọn B -> DENY
3. Bob (B) đọc B/D-7 -> bravo-secret
4. Bob cố chọn A -> DENY
5. Casey chọn A -> alpha-secret
6. Casey chọn B -> bravo-secret
7. Thu hồi membership B của Casey; Casey chọn B -> DENY
8. Cấp lại membership B (qua quy trình server); Casey chọn B -> bravo-secret
9. Alice còn A, đổi token/đăng nhập Bob; request sau -> chỉ dữ liệu Bob
~~~

Để kiểm thread pooling và `ThreadLocal` tenant context, dùng executor thực có ít worker để tạo reuse, chạy A→B→A và chạy một task ném exception giữa chừng; assert tenant/Authentication được set và restore/clear ở đúng lifecycle. Dùng `CountDownLatch`/`Future.get(timeout)` để test deterministic, không dựa vào `Thread.sleep`. Mặc định Spring Security quản lý context mỗi request, nhưng custom `TenantContextHolder` hoặc asynchronous handoff phải test riêng.

### 9.4. Test token và nguồn identity

- Tạo bearer token thật được ký bởi test issuer/JWK và hợp lệ với API; test `iss`, `aud`, `exp`, signature và `sub`. Thử token sai chữ ký/sai audience và assert 401.
- Kiểm JWT claim mapper: `scope` thường tạo `SCOPE_...`, không tự tạo role global từ `tenantId`. Role A và role B phải phân biệt theo dữ liệu phía server nếu dùng role theo tenant.
- Với token cũ sau khi membership bị thu hồi, xác định hệ thống revalidate ngay hay theo TTL/token lifetime đã phê duyệt; test theo yêu cầu cụ thể chứ không giả định mọi JWT đã ký đều được kiểm revocation tức thời.
- Nếu user thay email nhưng `issuer+sub` giữ nguyên, không làm mất quyền nhầm; nếu hai issuer phát cùng `sub`, không nhập làm một principal nếu không có federation mapping rõ.

### 9.5. Test cả side channel, cache, async và tải file

Ngay cả khi GET detail đã chặn, cross-tenant leak có thể ở:

- `GET /documents/count` và search suggestions; tên file, tổng số, trang đầu/cuối, `ETag`, lastModified, error message.
- Cache `@Cacheable(key = "#documentId")` thiếu tenant làm A/B dùng cùng cached record; key phải xét tenant và những yếu tố policy cần thiết.
- Export queued job tạo file dưới service principal rộng, nhưng requester không được export tenant B; kiểm submit, run và download.
- Signed URL có thời hạn/đối tượng đúng nhưng bị chia sẻ? Phải kiểm quyền trước khi phát URL và chính sách revoke phù hợp mức nhạy cảm.
- Batch API nhận danh sách gồm A/D-7 và B/D-7; một item trái phép không được âm thầm thực hiện. Định nghĩa all-or-nothing hoặc per-item failures rõ và kiểm side effects.
- WebSocket/SSE subscription, events, search indexes, object storage, backups và logs đều giữ tenant association; log thường dùng để debug không được chứa nội dung bí mật của B cho user A.

## 10. Java 17 độc lập: test hai tenant và chuyển principal

Chương trình sau mô phỏng policy và data store bằng Java 17+ (không cần Spring hoặc database). Nó mô phỏng một principal đã được xác thực với `issuer` và `subject`; **không xử lý chữ ký JWT**, do đó không được dùng constructor `Principal` như một API authentication production. Trọng tâm là mọi lời gọi đều truyền actor/tenant và kiểm membership, functional permission, và composite key trước khi đọc/ghi.

Lưu thành `TwoTenantIsolationDemo.java` rồi chạy:

~~~bash
javac TwoTenantIsolationDemo.java
java TwoTenantIsolationDemo
~~~

Toàn bộ mã:

~~~java
import java.util.*;

public class TwoTenantIsolationDemo {
    record Principal(String issuer, String sub, Set<String> scopes) {}
    record Key(String tenant, String id) {}

    static final class Denied extends RuntimeException {}
    static final class NotFound extends RuntimeException {}

    static final class Store {
        private final String issuer = "https://login.example.test";
        private final Map<String, Set<String>> memberships = new HashMap<>();
        private final Map<Key, String> documents = new HashMap<>();

        void setMembership(String subject, Set<String> tenantIds) {
            memberships.put(subject, Set.copyOf(tenantIds));
        }

        void put(String tenant, String id, String value) {
            documents.put(new Key(tenant, id), value);
        }

        private void require(Principal actor, String tenant, String scope) {
            if (actor == null
                    || !issuer.equals(actor.issuer())
                    || !actor.scopes().contains(scope)
                    || !memberships.getOrDefault(actor.sub(), Set.of())
                        .contains(tenant)) {
                throw new Denied();
            }
        }

        String read(Principal actor, String tenant, String id) {
            require(actor, tenant, "documents.read");
            String value = documents.get(new Key(tenant, id));
            if (value == null) throw new NotFound();
            return value;
        }

        void rename(Principal actor, String tenant, String id, String title) {
            require(actor, tenant, "documents.write");
            Key key = new Key(tenant, id);
            if (!documents.containsKey(key)) throw new NotFound();
            documents.put(key, title);
        }
    }

    static void denied(Runnable action) {
        try {
            action.run();
        } catch (Denied expected) {
            return;
        }
        throw new AssertionError("Expected access denial");
    }

    public static void main(String[] args) {
        String issuer = "https://login.example.test";
        Principal alice = new Principal(
            issuer, "alice", Set.of("documents.read", "documents.write"));
        Principal bob = new Principal(
            issuer, "bob", Set.of("documents.read"));
        Principal casey = new Principal(
            issuer, "casey", Set.of("documents.read"));

        Store store = new Store();
        store.setMembership("alice", Set.of("A"));
        store.setMembership("bob", Set.of("B"));
        store.setMembership("casey", Set.of("A", "B"));
        store.put("A", "D-7", "alpha-secret");
        store.put("B", "D-7", "bravo-secret");

        System.out.println("Alice/A=" + store.read(alice, "A", "D-7"));
        System.out.println("Bob/B=" + store.read(bob, "B", "D-7"));

        denied(() -> store.read(alice, "B", "D-7"));
        System.out.println("DENY Alice/B");
        denied(() -> store.read(bob, "A", "D-7"));
        System.out.println("DENY Bob/A");

        System.out.println("Casey/A=" + store.read(casey, "A", "D-7"));
        System.out.println("Casey/B=" + store.read(casey, "B", "D-7"));

        store.setMembership("casey", Set.of("A"));
        denied(() -> store.read(casey, "B", "D-7"));
        System.out.println("DENY Casey/B after revoke");

        // Thực thi tuần tự với principal khác: không có context cũ.
        System.out.println("Switch-to-Bob=" + store.read(bob, "B", "D-7"));

        denied(() -> store.rename(alice, "B", "D-7", "tampered"));
        System.out.println("DENY Alice write B");

        store.rename(alice, "A", "D-7", "alpha-v2");
        System.out.println("Updated A=" + store.read(alice, "A", "D-7"));
        System.out.println("Unchanged B=" + store.read(bob, "B", "D-7"));
    }
}
~~~

Stdout mong đợi:

~~~text
Alice/A=alpha-secret
Bob/B=bravo-secret
DENY Alice/B
DENY Bob/A
Casey/A=alpha-secret
Casey/B=bravo-secret
DENY Casey/B after revoke
Switch-to-Bob=bravo-secret
DENY Alice write B
Updated A=alpha-v2
Unchanged B=bravo-secret
~~~

Dòng `Unchanged B=bravo-secret` quan trọng hơn một response 403: nó chứng minh thao tác sửa của Alice chỉ tác động A. Khi membership của Casey bị xóa, token/identity mô phỏng của Casey không thay nhưng policy vẫn từ chối B, nhấn mạnh kiểm membership hiện hành. Trong production, cần authenticating principal, DB transactions, object ACL, multi-tenant cache, audit và test JWT thật như các mục trên.

## 11. Kịch bản tạo/sửa/xóa/tìm kiếm/xuất dữ liệu và kiểm bất biến

### 11.1. CREATE

Alice gọi `POST /api/tenants/A/documents` với `projectId=P-1` và payload chứa `tenantId=B`. Server phải dùng tenant A đã xác minh, không tin `tenantId` trong body. Nếu client cung cấp `ownerId=bob` hoặc `projectId` thuộc B, phải áp policy role/ownership và foreign key tenant. Sau request, assert A tạo đúng một record, B không thêm record; kiểm audit owner/tenant.

### 11.2. UPDATE / PATCH

Đổi title A/D-7 dưới principal Alice, rồi thử đổi title B/D-7 bằng cách thay path/header/body. Assert B document content/version không đổi. Nếu update nhiều field hoặc bulk update, policy phải chặn thay `tenant_id`/`owner_id`/`project_id` ngoài quy trình được phép. Ghi có version predicate tránh concurrent overwrite; scope quyền tại lúc ghi phải được áp dụng theo transaction/risk model.

### 11.3. DELETE

Alice có `documents.delete` ở A có thể xóa A record theo object policy, không được xóa B record cùng ID. Test cả hard delete, soft-delete field, cascade relations, audit/outbox event và file attachments. Không chấp nhận chỉ assert HTTP 403 nếu một delete background job đã được enqueue hoặc event xóa đã phát trước khi bị từ chối.

### 11.4. SEARCH / LIST / COUNT

Với A chứa 2 document, B chứa 3 document, Alice search `"report"` phải thấy đúng A được phép. Thử offset, cursor, filter, sort, totalElements/totalPages, faceted counts và autocomplete. Không trộn A/B rồi trả `totalElements=5` dù `content` chỉ có 2 dòng; metadata cũng là dữ liệu của tenant khác.

### 11.5. EXPORT / DOWNLOAD

Alice yêu cầu export A: job có `requestedBy=Alice`, `authorizedTenant=A` và filter đã được duyệt. Worker chạy bằng service identity nhưng kiểm lại quyền Alice/tenant A trước khi query; các hàng trong CSV/Excel/JSON chỉ thuộc A, không thêm B vì service có DB quyền rộng. Khi download, tiếp tục xác minh actor và object output. Signed URL và cache files có scope/expiry phù hợp; tenant B không thể biết ID rồi lấy file của A.

### 11.6. Quan hệ dữ liệu

Document A/D-7 tham chiếu `projectId=P-1` phải resolve **A/P-1**, không phải B/P-1. Với join, luôn scope cả hai bảng hoặc dùng composite foreign keys. Với cross-tenant sharing hợp lệ, dùng entity `ShareGrant`/`AccessPolicy` explicit cho phép **chính xác object và action**, không xóa tenant boundary của mọi query. Role quản trị tại A không mặc định là quản trị tại B.

## 12. Quy trình chạy bài thực hành trong dự án thật

1. **Khai báo hợp đồng:** định nghĩa issuer/audience, principal key, tenant selector, membership lifecycle, role theo tenant và chính sách 401/403/404; ghi quyền functional và object cần thiết cho từng endpoint.
2. **Tạo database fixture:** A/B cùng `D-7`, khác title và owner; Casey ở cả A/B; admin A không thuộc B; A-9/B-9; cùng `P-1` ở hai tenant để bắt lỗi join.
3. **Bật security chain/method security:** xác thực request, scope đúng, `@EnableMethodSecurity`, service kiểm membership và ACL; endpoint chưa khai báo phải fail closed.
4. **Ràng buộc persistence:** mọi query, count, update, delete, join và export dùng tenant context đã xác minh; composite keys/FK/RLS nếu phù hợp kiến trúc.
5. **Chạy positive matrix:** Alice→A; Bob→B; Casey→A/B. Xác minh nội dung đúng bằng field khác nhau, không chỉ status hoặc số kết quả.
6. **Chạy negative matrix:** Alice→B, Bob→A, admin A→B, scope thiếu, forged header/body, sai issuer/audience, token/permission revoked, project reference B, bulk mixed IDs.
7. **Chạy identity switch:** A→B→A trên cùng test/worker pool và logout/login session nếu áp dụng; test sau exception và cache key riêng.
8. **So DB/side effects:** snapshot của B trước thử nghiệm Alice, sau từng write/deny xác minh giữ nguyên bản ghi, version, soft-delete flag, audit, queue, export artifact.
9. **Kiểm các điểm phụ:** search/count, event, cache, file URL, logs, async; cùng một API vẫn có thể leak qua đường khác.
10. **Gắn vào CI:** regression suite chạy với database và auth stack phù hợp; mọi thay đổi converter, membership, multi-tenant repository, role hierarchy hoặc cache phải chạy lại isolation tests.

Không kết luận đạt chỉ vì “các request thiếu token đều trả 401” hoặc “Alice đọc được A”. Hệ thống luôn deny cũng qua negative test; hệ thống đọc A đúng nhưng đồng thời lộ B trong count/search cũng chưa cách ly thành công. Cần positive/negative **cùng dataset** và kiểm side effects.

## 13. Lỗi thường gặp và cách khắc phục

| Sai sót | Dấu hiệu | Hướng khắc phục |
| --- | --- | --- |
| Tin `tenantId` trong header | Alice đổi header sang B và lấy B | Xem header là selector; tra membership theo authenticated principal |
| Query chỉ có `id` | A/B có `D-7` và đọc nhầm | Dùng `(tenantId, id)` trong query, index và quan hệ |
| Role admin không scope | `TENANT_ADMIN` của A quản trị được B | Role/permission luôn gắn tenant hoặc phạm vi rõ |
| Coi JWT `sub` do user gửi trong JSON là principal | Có thể tự mạo danh Bob | Lấy identity từ token/session đã xác thực; validate issuer/audience |
| Trộn tenant theo cache key `D-7` | Response B trả content A | Namespace cache theo tenant và actor/policy cần thiết |
| Chỉ kiểm route, không kiểm service | Đường scheduler/worker bỏ qua HTTP rule | Policy tại service/query boundary; explicit service identity |
| Dùng `findAll()` rồi filter Java | Count, logs, cache và memory có B | Filter tại DB/search, kiểm metadata |
| Test `jwt().authorities(...)` rồi coi như kiểm JWT production | Custom converter/issuer bị bypass | Kiểm riêng signed token/decoder/converter và request authorization |
| Chỉ test một user một tenant | Không phát hiện stale context khi switch | Chạy A→B→A cùng pool/session, cả exception path |
| Revoke membership nhưng cache không invalid | Casey vẫn đọc B | Policy freshness/TTL/revocation + regression |
| Cho update `tenantId` bằng DTO entity | Chuyển tài liệu A sang B trái phép | Immutable tenant; transfer workflow riêng, kiểm hai phía |
| `403` nhưng đã ghi DB | Policy chạy sau side effect | Authorize trước mutate, transaction/DB predicate và assert state |
| Dựa vào UUID khó đoán | IDOR vẫn tồn tại nếu lộ ID | Object-level authorization cho mọi thao tác |
| Signed export URL không gắn scope | Alice tải file Bob nhờ URL | Authorize phát URL/file, expiry và revoke phù hợp |

## 14. Checklist nghiệm thu cuối bài

- [ ] Có hai tenant thật với **cùng local ID** nhưng dữ liệu khác nhau; fixture được cô lập giữa test.
- [ ] Actor key dùng danh tính đã xác minh, không tin `sub`/`userId`/`tenantId` từ header/body.
- [ ] Role theo tenant không bị nâng thành quyền global; scope chức năng không thay thế membership/ACL.
- [ ] Alice→A, Bob→B, Casey→A/B đều đúng; Alice→B và Bob→A bị từ chối.
- [ ] Chuyển principal A→B→A không giữ sai `SecurityContext`/tenant context/cache.
- [ ] Thu hồi membership hoặc khóa account làm các thao tác kế tiếp bị từ chối theo freshness contract.
- [ ] Repository read/write/delete/query/count/join có tenant predicate hoặc isolation boundary tương đương.
- [ ] Client không sửa tenant/owner/foreign key ngoài policy; quan hệ A không bị nối vào project B.
- [ ] Negative request không làm đổi DB, cache, events, outbox, file/export hoặc audit side effect trái phép.
- [ ] Search/list/count/pagination/export/bulk/file download đều không lộ record hay metadata của tenant khác.
- [ ] Mỗi test deny có positive control đủ quyền và data đúng, không chỉ test hệ thống trả lỗi.
- [ ] JWT integration test phân biệt mock `jwt()` với token signed/issuer/audience thật; CSRF và status code được hiểu đúng.
- [ ] Worker nền có service identity rõ và policy theo requester/tenant; cache/connection pool/thread pool không làm dính tenant.
- [ ] Dữ liệu/log vận hành có tenant scope, không ghi raw token hoặc secret; bất thường cross-tenant được theo dõi an toàn.

**Kết luận:** Cách ly tenant là một **bất biến xuyên suốt** từ authenticated identity, tenant selection, role/membership, object policy, query đến kết quả. Một bài test hai tenant tốt phải chứng minh cả hai điều: **user trong phạm vi được phép thao tác thành công** và **không một thay đổi principal, tenant selector, ID, session hay quyền theo thời gian nào làm lộ hoặc thay đổi dữ liệu tenant khác**.

### Tài liệu tham khảo

- [Spring Security — Method Security](https://docs.spring.io/spring-security/reference/servlet/authorization/method-security.html): `@EnableMethodSecurity`, `@PreAuthorize` và yêu cầu gọi qua proxy Spring.
- [Spring Security — Testing OAuth 2.0 with MockMvc](https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/oauth2.html): `jwt()`, mock principal/claims/authorities và giới hạn của test authentication.
- [Spring Security — Authorize HTTP Requests](https://docs.spring.io/spring-security/reference/servlet/authorization/authorize-http-requests.html): `authorizeHttpRequests` và các manager cho URL.
- [OWASP — Multi Tenant Security Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Multi_Tenant_Security_Cheat_Sheet.html): ranh giới dữ liệu, xác minh tenant, cache/queue/storage và RLS.
- [OWASP — Insecure Direct Object Reference Prevention](https://cheatsheetseries.owasp.org/cheatsheets/Insecure_Direct_Object_Reference_Prevention_Cheat_Sheet.html): authorization trên đối tượng, tránh IDOR/BOLA khi thay ID.
