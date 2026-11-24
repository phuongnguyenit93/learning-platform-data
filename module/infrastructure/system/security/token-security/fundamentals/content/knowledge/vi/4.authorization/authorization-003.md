# Authorization theo resource và action

## 1. Bài toán: một token hợp lệ chưa có nghĩa được làm mọi việc

Trong chương **Authorization** của module **SECURITY_TOKEN_SECURITY_FUNDAMENTALS**, chúng ta cần đi từ câu hỏi "token này có đáng tin không?" đến câu hỏi chính xác hơn: **chủ thể nào được phép thực hiện hành động nào trên tài nguyên nào, trong ngữ cảnh nào?**

Hệ thống bảo mật token phải phân biệt JWT và opaque token, access token và refresh token, kiểm tra issuer, audience, scope, vòng đời phát hành và thu hồi. Tuy nhiên, ngay cả khi toàn bộ việc xác minh access token đều đúng, API vẫn có thể làm lộ dữ liệu hoặc cho sửa nhầm đối tượng nếu bỏ qua **authorization theo resource và action**.

Ví dụ, Alice đăng nhập và có access token hợp lệ với scope `documents:read`. Hai request sau phải có kết quả khác nhau:

~~~http
GET /api/documents/doc-201 HTTP/1.1
Host: documents.example.com
Authorization: Bearer <ALICE_ACCESS_TOKEN>
~~~

~~~http
GET /api/documents/doc-901 HTTP/1.1
Host: documents.example.com
Authorization: Bearer <ALICE_ACCESS_TOKEN>
~~~

Giả sử `doc-201` thuộc dự án Alice được phép xem, còn `doc-901` thuộc tenant khác và không được chia sẻ. Request đầu có thể được **ALLOW**, request thứ hai phải **DENY**. Việc thay ID không làm access token mất chữ ký hoặc hết hạn; điểm khác biệt là **quyền trên resource cụ thể**.

Một mô hình tư duy:

~~~text
authorize(
    principal,      // ai yêu cầu?
    action,         // muốn thực hiện hành động gì?
    resource,       // đối tượng nghiệp vụ nào?
    context         // tenant, trạng thái, quan hệ, môi trường ...
) -> ALLOW | DENY
~~~

| Đầu vào | Ví dụ | Cần làm rõ |
|---|---|---|
| **Principal** | Người dùng Alice, service account báo cáo | Danh tính và loại chủ thể có được xác thực đáng tin cậy không? |
| **Action** | `document:read`, `document:update`, `document:delete`, `document:share` | Thao tác nghiệp vụ và tác động phụ thực tế là gì? |
| **Resource** | `doc-201`, một hóa đơn, tài khoản ngân hàng, đơn hàng | Đối tượng thuộc ai, tenant nào, chịu policy nào? |
| **Context** | Project membership, trạng thái DRAFT, legal hold, thời điểm | Điều kiện động nào giới hạn hành động? |
| **Decision** | ALLOW, DENY | Đã có đủ bằng chứng tin cậy để cho phép chưa? |

**Quy tắc mặc định: không chứng minh được quyền thì từ chối.** Việc đã xác thực không mặc nhiên cấp quyền với mọi resource.

> **Phân biệt:** Trong OAuth 2.0, *resource server* là API được access token dùng để truy cập, ví dụ Documents API. *Resource* trong bài này chủ yếu là **đối tượng nghiệp vụ** mà API quản lý, chẳng hạn một tài liệu. Claim `aud` thường ràng buộc token với API nhận token; nó không tự chứng minh quyền đọc từng tài liệu.

## 2. Ba câu hỏi liên tiếp: authentication, token validation, authorization

**Authentication** xác định danh tính người dùng, service account hoặc workload. Trong OpenID Connect (OIDC), client có thể nhận ID token để biết kết quả đăng nhập; resource server thường nhận **access token** khi client gọi API.

**Token validation** kiểm tra access token có được phát hành và sử dụng đúng cách hay không:

1. Token đến từ **issuer** đã được cấu hình tin cậy; với JWT, kiểm tra chữ ký, thuật toán và khóa phù hợp; với opaque token, kiểm tra qua introspection hoặc cơ chế xác minh đáng tin cậy.
2. `aud` chỉ **resource server hiện tại**, token đúng loại; không lấy ID token làm access token.
3. Token còn hiệu lực theo `exp`, `nbf` và thông tin trạng thái/thu hồi nếu áp dụng.
4. Token có các scope/permissions mà API đòi hỏi cho nhóm hành động.

**Authorization** quyết định principal đã xác thực có được thực hiện **action trên chính resource yêu cầu** hay không. Quyết định có thể phải đọc owner, tenant, membership hoặc trạng thái từ dữ liệu nghiệp vụ hiện tại.

~~~mermaid
flowchart TD
    A[Client gửi request và access token] --> B{Token hợp lệ cho API?}
    B -- Không --> C[401 hoặc lỗi invalid_token]
    B -- Có --> D{Scope cho action phù hợp?}
    D -- Không --> E[403 hoặc insufficient_scope]
    D -- Có --> F[Đọc resource và thuộc tính tin cậy]
    F --> G{Principal có quyền với resource và context?}
    G -- Không --> H[403 hoặc 404 theo chính sách]
    G -- Có --> I[Thực thi action với điều kiện quyền còn hiệu lực]
~~~

Một số hệ thống kết hợp các bước thành một PDP/policy engine, nhưng vẫn cần phân biệt logic. Scope có thể là điều kiện cần để đi tới quyết định trên tài liệu; nó **không phải bằng chứng Alice sở hữu mọi tài liệu**.

## 3. Ví dụ xuyên suốt: hệ thống tài liệu đa tenant

Giả sử có nền tảng quản lý tài liệu:

| Đối tượng | Thuộc tính |
|---|---|
| **Alice** | `sub=alice-123`, thành viên `tenant-A`, chủ sở hữu `doc-201` |
| **Bob** | `sub=bob-456`, editor dự án Alpha của `tenant-A` |
| **Carol** | `sub=carol-789`, viewer dự án Alpha của `tenant-A` |
| **Mallory** | Thành viên `tenant-B`, không có quyền tại `tenant-A` |
| **doc-201** | Tài liệu dự án Alpha, `tenant-A`, owner Alice, trạng thái `DRAFT` |
| **doc-901** | Tài liệu `tenant-B`, không chia sẻ sang `tenant-A` |
| **Documents API** | `https://documents.example.com`, API bảo vệ các tài liệu |

Policy minh họa:

- Owner được xem, sửa và chia sẻ tài liệu của mình khi trạng thái và chính sách tổ chức cho phép.
- Editor của dự án được đọc và sửa tài liệu dự án khi tài liệu còn `DRAFT`.
- Viewer của dự án chỉ được đọc.
- Xóa là action riêng, chỉ owner hoặc vai trò xóa hợp lệ được thực hiện, và bị chặn khi tài liệu đang chịu **legal hold**.
- Principal của tenant khác không được truy cập nếu không có ủy quyền hoặc chia sẻ liên tenant hợp lệ.

### 3.1. Ma trận quyết định theo resource và action

| Principal | Action | Resource | Context | Decision |
|---|---|---|---|---|
| Alice | `document:read` | doc-201 | Là owner | **ALLOW** |
| Bob | `document:update` | doc-201 | Editor dự án Alpha, trạng thái DRAFT | **ALLOW** |
| Carol | `document:read` | doc-201 | Viewer dự án Alpha | **ALLOW** |
| Carol | `document:update` | doc-201 | Không có quyền sửa | **DENY** |
| Alice | `document:read` | doc-901 | Thuộc tenant-B, không được chia sẻ | **DENY** |
| Alice | `document:delete` | doc-201 | Tài liệu đang bị legal hold | **DENY** |
| Mallory | `document:update` | doc-201 | Không có quyền tại tenant-A | **DENY** |

**Một principal có thể được phép làm action A trên resource X nhưng không được làm action B trên X hoặc action A trên Y.** Ngay cả owner cũng không nhất thiết được bỏ qua hạn chế nghiệp vụ.

### 3.2. Action là khả năng nghiệp vụ, không chỉ là HTTP verb

| Endpoint ví dụ | Action/policy tương ứng | Ghi chú |
|---|---|---|
| `GET /documents/{id}` | `document:read` | Quyền xem nội dung |
| `PATCH /documents/{id}` | `document:update` | Quyền sửa nội dung/metadata có thể tách riêng |
| `DELETE /documents/{id}` | `document:delete` | Quyền xóa, chú ý legal hold |
| `POST /documents/{id}/share` | `document:share` | Có thể thay đổi quyền của người khác |
| `POST /documents/{id}/publish` | `document:publish` | Thay đổi phạm vi công bố |
| `GET /documents?project=alpha` | `document:list` và `document:read` trên từng phần tử | Không lộ các bản ghi ngoài quyền |
| `POST /documents/export` | `document:export` và quyền đọc từng mục | Xuất hàng loạt thường nhạy cảm hơn đọc một mục |

Một endpoint POST có thể gây nhiều tác động. Ví dụ `share` vừa ghi quan hệ quyền, vừa gửi lời mời. Không nên đồng nhất mọi hành động trong endpoint với một quyền `write` chung nếu rủi ro khác nhau.

## 4. Claims nào có ích, claims nào không đủ?

Ví dụ payload **JWT access token minh họa**:

~~~json
{
  "iss": "https://login.example.com/realms/company",
  "sub": "alice-123",
  "aud": ["https://documents.example.com"],
  "client_id": "documents-web",
  "scope": "documents:read documents:write",
  "tenant_id": "tenant-A",
  "iat": 1790000000,
  "exp": 1790000900,
  "jti": "token-001"
}
~~~

Đây chỉ là JSON đã diễn giải để học; **không phải JWT hoàn chỉnh có chữ ký**. `tenant_id` là claim tùy biến, ý nghĩa của nó phải được issuer và hợp đồng token xác định. `client_id` có thể có trong JWT access token theo profile tương ứng; không phải token nào cũng có cùng cấu trúc.

| Trường | Giúp biết điều gì sau khi xác minh | Không tự bảo đảm điều gì |
|---|---|---|
| `iss` | Issuer chịu trách nhiệm phát hành | Issuer đáng tin thì mọi tài liệu đều được phép |
| `sub` | Principal được token mô tả trong phạm vi issuer | Principal sở hữu document ID trong URL |
| `aud` | API/token recipient hợp lệ | Mọi action trên API đều được phép |
| `scope` | Phạm vi quyền được cấp cho token | Mọi tài liệu đều có thể đọc/sửa |
| `client_id` | Client được cấp token theo profile | Client chính là người dùng hoặc có toàn quyền người dùng |
| `tenant_id` | Tenant do issuer khẳng định theo hợp đồng | Document trong request chắc chắn thuộc tenant đó |
| `exp`, `nbf`, `iat` | Điều kiện thời gian | Membership và quyền nghiệp vụ chưa từng thay đổi |
| `jti` | Định danh token khi có | Token mặc nhiên chống replay hoặc đã được kiểm tra thu hồi |

**Không sử dụng chuỗi payload JWT chưa kiểm tra chữ ký để quyết định quyền.** API phải xác minh issuer, chữ ký/active, audience, loại token, thời gian và scope trước khi tin vào claims. Không nên tải khóa xác thực theo JWKS URL tùy ý do token chưa được xác minh cung cấp.

### 4.1. Định danh có phạm vi issuer

Nếu hệ thống hỗ trợ nhiều issuer, hai token cùng `sub=alice-123` nhưng khác `iss` **không bảo đảm cùng một người**. Khóa principal có thể dựa trên cặp `(iss, sub)` và các giới hạn tenant theo thiết kế. Email, tên hiển thị hoặc `userId` do client gửi không phải bằng chứng cấp quyền tương đương.

### 4.2. Access token, ID token và refresh token có mục đích khác nhau

| Loại token | Nơi sử dụng | Vai trò với authorization resource/action |
|---|---|---|
| **Access token** | Client gửi tới resource server đúng audience | API xác minh token và dùng claims đáng tin làm đầu vào policy |
| **ID token (OIDC)** | Client nhận để xác minh thông tin đăng nhập | Không thay access token để gọi Documents API |
| **Refresh token** | Client gửi đến token endpoint của Authorization Server | Xin access token mới; không chứng minh quyền trên document |

JWT và opaque token là hai cách **biểu diễn/kiểm tra credential**. JWT có thể xác minh cục bộ bằng khóa tin cậy; opaque token thường cần introspection. Dù cách kiểm tra nào, quyết định theo resource/action vẫn thuộc trách nhiệm của API hoặc thành phần policy được API tin cậy.

## 5. Mô hình RBAC, ABAC, ReBAC và cách kết hợp

### 5.1. RBAC — quyền theo vai trò có phạm vi

Role-Based Access Control (RBAC) gán quyền cho role, rồi gán role cho principal. Ví dụ: editor có quyền cập nhật tài liệu trong **dự án cụ thể**.

~~~text
Sai:
    hasRole("ADMIN") -> cho sửa mọi tài liệu

Rõ ràng hơn:
    hasRoleInProject(principal, "EDITOR", document.projectId)
    AND document.state == "DRAFT"
~~~

Role `ADMIN` của tenant-A không tự trở thành role `ADMIN` trên tenant-B. Nếu một người có nhiều vai trò ở nhiều tổ chức, policy phải kiểm tra **vai trò đó có hiệu lực đối với tài nguyên hiện tại hay không**.

### 5.2. ABAC — quyền theo thuộc tính

Attribute-Based Access Control (ABAC) sử dụng thuộc tính của principal, resource, action và ngữ cảnh:

~~~text
ALLOW document:update
IF  principal.tenant được phép truy cập document.tenant
AND principal có quyền editor trên document.project
AND document.state == "DRAFT"
AND document.locked == false
~~~

ABAC hữu ích khi quyền phụ thuộc trạng thái động. Khi tài liệu chuyển từ DRAFT sang PUBLISHED, token của Bob có thể còn hạn nhưng thao tác cập nhật bị từ chối theo trạng thái mới.

### 5.3. ReBAC — quyền theo quan hệ

Relationship-Based Access Control (ReBAC) dựa trên quan hệ như sở hữu, thành viên dự án hoặc chia sẻ:

~~~text
document:doc-201 --owned_by--> user:alice-123
document:doc-201 --in_project--> project:alpha
project:alpha     --editor--> user:bob-456
project:alpha     --viewer--> user:carol-789
~~~

Khi Bob rời dự án Alpha, quyền sửa có thể mất dù access token còn sống. Nếu API cache membership hoặc quyết định quyền, cần thiết kế cách vô hiệu hóa phù hợp.

### 5.4. Policy kết hợp

Trong thực tế, một policy có thể kết hợp:

~~~text
ALLOW UPDATE(document)
IF  principal hợp lệ trong tenant của document
AND (
       principal là owner
       OR principal là editor của project chứa document
    )
AND document.state == DRAFT
AND document.locked == false
AND access token được cấp scope phù hợp cho API này
~~~

**RBAC trả lời khả năng theo role; ReBAC trả lời quan hệ với resource; ABAC kiểm tra các điều kiện bổ sung.** Không mô hình nào thay thế được việc thực thi kiểm tra đúng vị trí.

## 6. Kiến trúc thực thi: PEP, PDP và PIP

Một cách tổ chức dễ kiểm soát là:

- **PEP (Policy Enforcement Point):** nơi chặn request và thực thi quyết định, thường là endpoint/service/repository.
- **PDP (Policy Decision Point):** nơi đánh giá `(principal, action, resource, context)` để trả ALLOW hoặc DENY.
- **PIP (Policy Information Point):** nơi cung cấp owner, tenant, membership, trạng thái tài liệu và dữ liệu quyền đáng tin cậy.
- **Authorization Server/Issuer:** bên cấp token; thường không biết ngay mọi trạng thái của từng resource nghiệp vụ.

~~~mermaid
sequenceDiagram
    actor U as Alice
    participant C as documents-web
    participant API as Documents API / PEP
    participant PDP as Document Policy / PDP
    participant DB as Document & Permissions / PIP
    U->>C: Yêu cầu sửa doc-201
    C->>API: PATCH /documents/doc-201 + access token
    API->>API: Xác minh token, issuer, audience, scope
    API->>DB: Lấy metadata, ownership và membership
    DB-->>API: tenant, owner, project, state, permissions
    API->>PDP: authorize(Alice, UPDATE, doc-201, context)
    PDP-->>API: ALLOW hoặc DENY
    alt ALLOW
        API->>DB: Cập nhật có điều kiện theo policy/trạng thái
        DB-->>API: Kết quả ghi
        API-->>C: 200/204 thành công
    else DENY
        API-->>C: 403/404 theo chính sách
    end
    C-->>U: Hiển thị kết quả
~~~

Với **JWT access token**, API thường xác minh chữ ký và claims bằng khóa tin cậy đã cấu hình. Với **opaque access token**, có thể cần introspection đến Authorization Server và chính sách cache trạng thái tương ứng. Đây là bước xác thực credential trước khi lấy principal vào PDP.

### 6.1. Phải cưỡng chế quyền trên mọi đường vào dữ liệu

Chỉ kiểm tra ở API Gateway thường chưa đủ, vì gateway có thể không biết chủ sở hữu tài liệu, trạng thái hiện tại hoặc quan hệ chia sẻ. Documents API phải cưỡng chế quyền gần nơi truy cập dữ liệu.

Các đường vào cần bao phủ: lấy theo ID; danh sách; tìm kiếm; export; attachment/download; bulk update; GraphQL resolver; background job; gRPC; webhook; endpoint legacy; tác vụ quản trị. **Ẩn nút trên UI, kiểm tra CORS hay dùng ID khó đoán không thay thế authorization phía server.**

### 6.2. Dùng giao diện chính sách thống nhất

Thay vì mỗi controller tự kiểm tra role theo cách khác nhau, có thể tổ chức giao diện:

~~~text
PolicyDecision authorize(
    VerifiedPrincipal principal,
    DocumentAction action,
    DocumentResource resource,
    RequestContext context
)
~~~

Các kiểu trên là kiến trúc minh họa. Dù chính sách được đặt trong cùng ứng dụng hoặc dịch vụ riêng, PEP cần áp dụng **deny-by-default** và không bỏ qua quyết định khi PDP/PIP lỗi hoặc không có đủ thông tin. Kết quả ALLOW ở một API cũng không tự cho phép mọi API downstream bỏ kiểm tra audience và quyền của mình.

## 7. Java/Spring Security: triển khai theo từng lớp

Các đoạn sau là mã **minh họa kiến trúc**. `VerifiedPrincipal`, `DocumentPolicy`, `DocumentRepository` và `PolicyDecision` là kiểu do ứng dụng tự định nghĩa, không phải API sẵn có của Spring Security.

### 7.1. Bước 1: giới hạn action bằng scope

Khi Spring Security OAuth2 Resource Server được cấu hình phù hợp, request có thể được xác thực thành `Authentication` với authorities từ access token. Ví dụ:

~~~java
// Cần bật method security, cấu hình JWT/opaque token validation
// và ánh xạ scope thành SCOPE_documents:write phù hợp.
@PreAuthorize("hasAuthority('SCOPE_documents:write')")
@PatchMapping("/api/documents/{id}")
public DocumentDto update(
        @PathVariable String id,
        @RequestBody UpdateDocumentRequest request,
        Authentication authentication) {

    VerifiedPrincipal caller =
        principalFactory.fromVerifiedAuthentication(authentication);
    return documentService.update(caller, id, request);
}
~~~

`SCOPE_documents:write` là cách ánh xạ scope thường gặp, phụ thuộc converter/configuration. Với JWT, **phải kiểm tra audience của Documents API** bằng cấu hình/validator phù hợp, không mặc định rằng chỉ khai báo `issuer-uri` đã thực hiện mọi điều kiện cần thiết. Method security kiểm tra điều kiện chung, chưa kiểm tra Alice có quyền sửa `doc-201` không.

### 7.2. Bước 2: tải resource thực từ nguồn đáng tin

~~~java
// Pseudocode minh họa: documentPolicy dùng dữ liệu server-side.
DocumentDto update(
        VerifiedPrincipal caller,
        String documentId,
        UpdateDocumentRequest request) {

    Document document = documentRepository.findById(documentId)
        .orElseThrow(NotFoundException::new);

    PolicyDecision decision =
        documentPolicy.authorize(caller, DocumentAction.UPDATE, document);

    if (!decision.allowed()) {
        throw new ForbiddenException();
    }

    return documentRepository.updateAuthorized(
        caller,
        document,
        request
    );
}
~~~

**Không lấy `ownerId`, `tenantId`, `role` từ body để tự cấp quyền.** Resource ID cũng là dữ liệu không đáng tin về mặt quyền; API chỉ dùng nó để tìm đối tượng rồi đối chiếu quyền đã xác minh. Cách xử lý not found/forbidden phải tránh tiết lộ thông tin tenant khác.

### 7.3. Bước 3: policy đánh giá action/resource/context

~~~java
// Pseudocode: các helper là thành phần policy của ứng dụng.
PolicyDecision authorize(
        VerifiedPrincipal caller,
        DocumentAction action,
        Document document) {

    if (!identityPolicy.acceptedIssuer(caller.issuer())) {
        return PolicyDecision.deny("issuer");
    }
    if (!tenantPolicy.mayAccess(caller, document.tenantId())) {
        return PolicyDecision.deny("tenant");
    }

    boolean owner = ownershipPolicy.isOwner(caller, document);
    boolean editor = membershipPolicy.isEditor(caller, document.projectId());
    boolean viewer = membershipPolicy.isViewer(caller, document.projectId());

    return switch (action) {
        case READ ->
            (owner || editor || viewer)
                ? PolicyDecision.allow()
                : PolicyDecision.deny("read");

        case UPDATE ->
            (document.isDraft() && !document.isLocked() && (owner || editor))
                ? PolicyDecision.allow()
                : PolicyDecision.deny("update");

        case DELETE ->
            (owner && caller.hasPermission("document:delete")
                   && !document.isOnLegalHold())
                ? PolicyDecision.allow()
                : PolicyDecision.deny("delete");

        case SHARE ->
            (owner && sharePolicy.canShare(caller, document))
                ? PolicyDecision.allow()
                : PolicyDecision.deny("share");
    };
}
~~~

Ví dụ giả định validation của **scope cho action** đã được xử lý riêng và các helper có dữ liệu tin cậy. Đây không phải policy chung cho mọi sản phẩm: role quản trị, external collaborator, quy tắc chia sẻ, phiên bản tài liệu và quyền theo tổ chức cần được thiết kế theo nghiệp vụ. Action chưa được định nghĩa phải bị từ chối; tránh trường hợp thêm endpoint mới nhưng vô tình tái sử dụng quyền quá rộng.

### 7.4. TOCTOU: trạng thái thay đổi giữa kiểm tra và ghi

Giả sử `doc-201` là DRAFT khi bước authorize chạy, nhưng một transaction khác publish tài liệu trước khi update. Nếu API vẫn ghi bằng quyết định cũ, policy "chỉ sửa bản DRAFT" bị phá vỡ.

Các cách xử lý:

- Dùng transaction và locking thích hợp.
- Dùng **optimistic locking** với `version`, xử lý conflict và đánh giá lại policy khi thử lại.
- Ràng buộc tenant, ownership, trạng thái và version vào thao tác ghi nguyên tử.
- Khi policy phụ thuộc dịch vụ quyền bên ngoài, xác định ranh giới nhất quán và cách xử lý lúc PIP không sẵn sàng.

Ví dụ SQL minh họa phép cập nhật có điều kiện:

~~~sql
UPDATE documents
SET title = :new_title,
    version = version + 1
WHERE id = :document_id
  AND tenant_id = :authorized_tenant_id
  AND state = 'DRAFT'
  AND locked = FALSE
  AND version = :expected_version
  AND (
      owner_principal_id = :verified_principal_id
      OR EXISTS (
          SELECT 1
          FROM project_members pm
          WHERE pm.project_id = documents.project_id
            AND pm.principal_id = :verified_principal_id
            AND pm.role = 'EDITOR'
            AND pm.active = TRUE
      )
  );
~~~

`:authorized_tenant_id` và `:verified_principal_id` phải được dẫn xuất từ danh tính và chính sách đáng tin, không lấy trực tiếp từ body. Câu SQL chỉ minh họa một policy đơn giản, chưa xét tất cả biến thể phân quyền. Nếu số hàng được cập nhật bằng 0, thao tác không được thực hiện; API cần xử lý xung đột/từ chối mà không làm lộ dữ liệu ngoài quyền.

## 8. Danh sách, tìm kiếm, phân trang và bulk action

Authorization theo resource không chỉ áp dụng cho `GET /documents/{id}`. Một endpoint danh sách có thể làm lộ hàng trăm bản ghi nếu nó chỉ kiểm tra `documents:read` rồi gửi tất cả dữ liệu cho frontend lọc.

### 8.1. Lọc trước khi phân trang

Sai:

~~~text
SELECT * FROM documents;
trả kết quả về client;
frontend chỉ hiển thị các document của tenant hiện tại.
~~~

Lúc này dữ liệu đã bị chuyển tới client. Quyền nên được áp dụng trong truy vấn hoặc bằng cơ chế lọc server-side được thiết kế đúng.

~~~sql
SELECT d.id, d.title, d.state
FROM documents d
WHERE d.tenant_id = :authorized_tenant_id
  AND (
      d.owner_principal_id = :verified_principal_id
      OR EXISTS (
          SELECT 1
          FROM project_members pm
          WHERE pm.project_id = d.project_id
            AND pm.principal_id = :verified_principal_id
            AND pm.active = TRUE
      )
  )
ORDER BY d.id
LIMIT :page_size OFFSET :page_offset;
~~~

Đây là truy vấn tối giản, chưa mô hình hóa mọi kiểu chia sẻ/role/issuer. Tên, số lượng bản ghi, tổng số trang, facet tìm kiếm, gợi ý và thumbnail cũng có thể là **thông tin cần phân quyền**. Nên áp dụng bộ lọc quyền trước khi tính tổng và phân trang.

### 8.2. Bulk update/export cần xét từng đối tượng

Với `POST /documents/bulk-delete` chứa 100 document ID:

1. Kiểm tra caller có quyền thực hiện loại action bulk/delete.
2. Tải resource và dữ liệu quyền từ nguồn tin cậy cho từng ID.
3. Đánh giá action `document:delete` theo từng principal-resource-context.
4. Xác định rõ giao dịch **all-or-nothing** hoặc **partial success**.
5. Không để lỗi/response làm lộ dữ liệu của resource ngoài quyền.

`document:export` nên có policy riêng với giới hạn số lượng/dữ liệu khi cần. Job bất đồng bộ phải giữ được ngữ cảnh người yêu cầu và đánh giá lại quyền ở thời điểm thực thi theo chính sách, tránh âm thầm dùng service account toàn quyền cho mọi yêu cầu.

## 9. Multi-tenant và delegation giữa các dịch vụ

### 9.1. Tenant ID từ URL không phải bằng chứng quyền

~~~http
GET /api/tenants/tenant-B/documents/doc-901 HTTP/1.1
Host: documents.example.com
Authorization: Bearer <TOKEN_OF_TENANT_A_USER>
~~~

`tenant-B` và `doc-901` có thể do client thay đổi. API cần kiểm tra principal có quyền tại tenant-B và có quyền với `doc-901`. Role `ADMIN` thuộc tenant-A không tự có giá trị ở tenant-B.

Ngược lại, một người có thể được cấp quyền ở nhiều tenant hợp lệ. Policy không nên chỉ so sánh máy móc hai chuỗi tenant; phải xét membership, phạm vi ủy quyền và tenant đang được chọn theo hợp đồng ứng dụng.

### 9.2. Client credentials không phải quyền của người dùng

Giả sử Report Service có service token với scope `documents:read:all`. Alice yêu cầu Report Service xuất `doc-901` thuộc tenant-B. Nếu service dùng token quyền rộng để đọc tài liệu mà không xét Alice có được quyền đọc `doc-901` hay không, đó có thể là **confused deputy**.

Hai mô hình cần tách rõ:

- **Application permission:** tác vụ nội bộ dùng quyền của service account, thường qua client credentials.
- **Delegated permission:** dịch vụ hành động thay mặt user hoặc actor khác với phạm vi được cấp.

Giải pháp có thể gồm kiểm tra quyền user ở deputy, giới hạn service token theo tenant/mục đích, và dùng **OAuth 2.0 Token Exchange (RFC 8693)** hoặc on-behalf-of nếu issuer hỗ trợ để cấp token downstream đúng `aud`, scope và ngữ cảnh delegation. Resource server đích vẫn phải kiểm tra quyền trên resource. Không chuyển tiếp token của Report Service cho Documents API nếu audience sai.

### 9.3. Ngữ cảnh quyền phải có nguồn tin cậy

Không tin tự động vào `X-User-Id`, `X-Tenant-Id`, `X-Role` hoặc JSON do caller gửi. Nếu hệ thống có kênh truyền identity context nội bộ, cần ràng buộc danh tính của dịch vụ truyền, tính toàn vẹn thông điệp và hợp đồng authorization. Nhãn "internal" hoặc kết nối cùng mạng không tự chứng minh dữ liệu header đáng tin.

## 10. Vòng đời token và thay đổi quyền nghiệp vụ

Bob có thể bị loại khỏi dự án Alpha trong khi access token vẫn còn hạn 10 phút và chứa `scope=documents:write`. Nếu API chỉ dựa vào scope, Bob vẫn có thể sửa `doc-201` trái với membership hiện tại.

Cần phân biệt:

- **Token validity:** token còn hạn, đúng issuer, aud, scope, chưa bị thu hồi theo cơ chế hệ thống.
- **Business authorization:** quan hệ sở hữu, chia sẻ, role theo dự án, tenant, trạng thái document và chính sách hiện tại.

Thay đổi quyền nghiệp vụ không nhất thiết làm JWT access token mất hiệu lực ngay; JWT được xác minh offline thường có thể tiếp tục được nhận tới hết hạn nếu không có thêm cơ chế kiểm tra trạng thái. Opaque token qua introspection có thể phản ánh thu hồi sớm hơn, nhưng phụ thuộc cache và cách issuer triển khai. **Thu hồi refresh token** giúp hạn chế xin token mới, không tự xóa tức thì mọi access token đã cấp.

Để giảm rủi ro token bị đánh cắp hoặc phát lại, hệ thống nên có TLS, bảo vệ nơi lưu trữ, hạn chế scope/audience/thời hạn, không log bearer token, dùng refresh token rotation và sender-constrained access token (như DPoP hoặc mTLS) khi phù hợp. Các biện pháp đó **không thay thế** policy theo resource/action.

### 10.1. Cache authorization đúng ngữ cảnh

Sai:

~~~text
cache["alice-123"] = ALLOW
~~~

Một quyết định của Alice với `doc-201` có thể bị tái sử dụng sai cho `doc-901` hoặc action `delete`.

Khóa logic phải tính đến ít nhất các chiều phù hợp:

~~~text
(issuer, subject, client, tenant, action, resource, policyVersion, context)
~~~

Tùy mô hình, còn phải xét membership version, trạng thái tài liệu, loại principal hoặc delegation. Cần TTL/invalidation theo yêu cầu an toàn; đặc biệt các thay đổi như thu hồi quyền, khóa tài khoản hoặc legal hold phải được phản ánh trong khoảng thời gian chấp nhận được.

## 11. HTTP status và thông tin lỗi

| Tình huống | Kết quả thông dụng |
|---|---|
| Không có token khi API yêu cầu bearer | **401 Unauthorized** và challenge phù hợp |
| Token không hợp lệ, hết hạn, sai issuer/audience | **401 Unauthorized** hoặc lỗi `invalid_token` theo RFC 6750 |
| Token hợp lệ nhưng thiếu scope | **403 Forbidden** hoặc `insufficient_scope` theo giao thức |
| Token có scope nhưng không đủ quyền trên `doc-901` | **403 Forbidden** hoặc **404 Not Found** nếu cần che sự tồn tại |
| Resource không tồn tại | **404 Not Found** |
| Tài liệu đã đổi version/state trong lúc cập nhật | Xử lý conflict/điều kiện theo thiết kế API, không thực hiện cập nhật trái policy |

Tên HTTP `401 Unauthorized` có tính lịch sử; nó thường thể hiện yêu cầu xác thực credential hợp lệ. Phản hồi lỗi nên hạn chế tiết lộ owner, tenant hoặc dữ liệu của resource mà caller không được phép xem.

## 12. Checklist kiểm thử authorization theo resource và action

| Trường hợp | Kỳ vọng |
|---|---|
| Alice đọc tài liệu của mình bằng token đúng audience/scope | ALLOW nếu các điều kiện khác đạt |
| Carol có quyền viewer nhưng thử cập nhật tài liệu | DENY |
| Alice thay document ID trong URL sang tài liệu tenant khác | DENY, không lộ nội dung ngoài quyền |
| Bob là editor nhưng tài liệu đã PUBLISHED | DENY với action chỉ cho sửa DRAFT |
| Owner thử xóa tài liệu đang legal hold | DENY |
| Client gửi `"role":"admin"` trong JSON body | Không mở rộng quyền |
| JWT có chữ ký hợp lệ nhưng `aud` là Payments API | Từ chối trước khi dùng claims |
| Client gửi ID token thay access token | Từ chối |
| List/search chứa bản ghi ngoài quyền | Không trả dữ liệu, count, metadata ngoài quyền |
| Bulk-delete có cả ID được phép và không được phép | Xử lý đúng chính sách all-or-nothing/partial success |
| Membership bị thu hồi khi token còn hạn | Quyền đổi theo policy và ràng buộc cache đã định |
| Hai issuer cùng cấp `sub=alice-123` | Không nhập nhầm hai danh tính |
| Hai request đồng thời làm đổi state và update | Không vượt policy do race/TOCTOU |
| Service token quyền rộng xử lý ID do user chỉ định | Không bỏ qua quyền của user trên resource |

Chỉ kiểm thử happy path của owner không đủ. Cần thử **cùng action với nhiều resource, cùng resource với nhiều principal và nhiều action**, đặc biệt khi khác tenant hoặc quyền thay đổi theo thời gian.

### 12.1. Audit và quan sát

Với các quyết định quan trọng, log có thể ghi `traceId`, issuer/principal ID được bảo vệ phù hợp, client, loại principal, tenant, action, resource ID, policy version, quyết định và trạng thái phản hồi. Không ghi raw access token, refresh token hoặc header Authorization. Audit giúp phát hiện lỗi như truy cập chéo tenant, hành động quyền cao do endpoint công khai khởi phát và policy cho phép nhầm.

## 13. Những lỗi thiết kế cần tránh

| Lỗi | Vì sao nguy hiểm | Sửa theo nguyên tắc |
|---|---|---|
| Chỉ kiểm tra authenticated | Mọi người đăng nhập có thể thử tài nguyên của người khác | Xét principal + action + resource + context |
| Coi scope đọc là quyền đọc mọi bản ghi | BOLA/IDOR | Kiểm tra ownership, sharing, tenant |
| Role `ADMIN` không phạm vi | Admin tenant/dự án này có thể tác động tenant/dự án khác | Gắn role với ranh giới và action |
| Tin tenant/owner/role trong request | Client tự khai quyền | Lấy từ nguồn danh tính và dữ liệu quyền tin cậy |
| Chỉ ẩn tính năng trên UI | API vẫn có thể bị gọi trực tiếp | Enforcement server-side |
| Chỉ kiểm tra endpoint theo ID | List, export, attachment, bulk còn rò dữ liệu | Bảo vệ mọi đường vào |
| Dùng policy ALLOW đã cũ khi dữ liệu đổi | TOCTOU, thay đổi membership hoặc legal hold | Ghi có điều kiện, version, transaction, invalidation |
| Tin service token nội bộ là đủ | Dịch vụ có thể thành confused deputy | Kiểm tra caller, hạn chế quyền, bảo vệ delegation |
| Chỉ decode JWT | Claims có thể bị giả mạo | Validation đầy đủ chữ ký/issuer/audience/thời hạn |
| Cache quyền theo mỗi user | Nhầm action/resource/tenant | Cache theo context và cơ chế thu hồi |

## 14. Câu hỏi tự ôn

**1. Alice có JWT đúng issuer, đúng audience, scope `documents:read`. Cô có thể dùng nó đọc mọi tài liệu trên Documents API không?**

Không. Các điều kiện trên cho phép tiến tới bước authorization, nhưng API vẫn phải quyết định quyền của Alice trên từng tài liệu.

**2. Bob là admin dự án Alpha nhưng muốn xóa tài liệu dự án Beta. Chỉ `hasRole("ADMIN")` có đủ không?**

Không. Role phải được kiểm tra đúng phạm vi; còn phải kiểm tra action xóa và các giới hạn như legal hold.

**3. Alice là chủ sở hữu tài liệu nhưng gửi token có audience dành cho API khác. Có nên bỏ qua audience vì cô có quyền đối với tài liệu?**

Không. Token phải hợp lệ **cho Documents API** trước khi dùng claims đánh giá quyền nghiệp vụ.

**4. Carol rời dự án Alpha, nhưng access token vẫn còn hạn. Chuyển từ JWT sang opaque token có tự động sửa tất cả quyền đọc không?**

Không. Introspection có thể giúp kiểm tra trạng thái token; quyền dự án vẫn cần được lấy từ nguồn đáng tin cậy hiện hành hoặc một cơ chế đồng bộ quyền đã định nghĩa.

**5. Report Service có token ứng dụng `documents:read:all`. Alice yêu cầu export tài liệu không thuộc quyền của cô. Report Service có được dùng token của mình để đáp ứng không?**

Không. Token của service chứng minh quyền kỹ thuật của service, không tự chứng minh yêu cầu của Alice là hợp lệ. Phải kiểm tra quyền Alice trên từng resource hoặc dùng luồng delegation được kiểm soát.

**6. Endpoint danh sách không trả nội dung ngoài quyền nhưng trả tổng count của cả tenant khác. Đã an toàn chưa?**

Chưa chắc. Count, facet, tên nhãn hoặc các metadata có thể tiết lộ thông tin và cần được lọc theo quyền.

**7. API authorize UPDATE khi tài liệu đang DRAFT, nhưng tài liệu bị publish trước lúc ghi. Cần xử lý thế nào?**

Dùng transaction/locking, optimistic version hoặc thao tác ghi có điều kiện để ngăn quyết định quyền cũ dẫn tới cập nhật trái policy.

## 15. Tóm tắt mô hình quyết định

Khi thiết kế endpoint, tự kiểm tra theo thứ tự:

1. **Ai gọi?** Xác thực credential và danh tính `(iss, sub)` hoặc principal dịch vụ.
2. **Token có dùng được tại API này không?** Xác minh chữ ký/active, issuer, audience, thời hạn, loại token, scope và trạng thái khi áp dụng.
3. **Action thực tế là gì?** Đọc, sửa, xóa, chia sẻ, công bố, xuất dữ liệu hoặc tác động phụ.
4. **Resource thực sự là gì?** Lấy owner, tenant, membership, trạng thái và hạn chế từ dữ liệu đáng tin cậy.
5. **Policy có ALLOW không?** Kết hợp RBAC, ABAC, ReBAC hoặc mô hình phù hợp; từ chối mặc định.
6. **Thực thi có giữ quyền không?** Bao phủ list/bulk/job và chống TOCTOU; lưu audit vừa đủ.

**Một access token hợp lệ trả lời API có thể tin credential và phạm vi cấp quyền ở mức nào; authorization theo resource và action trả lời principal này có được làm việc cụ thể với chính đối tượng đó ngay lúc này không.** Hai lớp phải đi cùng nhau trong toàn bộ mô hình tin cậy và vòng đời token.

## Tài liệu tham khảo

- [RFC 6749 — The OAuth 2.0 Authorization Framework](https://www.rfc-editor.org/rfc/rfc6749): các vai trò, scope và mô hình OAuth 2.0.
- [RFC 6750 — Bearer Token Usage](https://www.rfc-editor.org/rfc/rfc6750): sử dụng bearer access token, lỗi invalid_token và insufficient_scope.
- [RFC 9068 — JWT Profile for OAuth 2.0 Access Tokens](https://www.rfc-editor.org/rfc/rfc9068): issuer, audience và claims của JWT access token.
- [RFC 7662 — OAuth 2.0 Token Introspection](https://www.rfc-editor.org/rfc/rfc7662): trạng thái token qua introspection.
- [RFC 8725 — JSON Web Token Best Current Practices](https://www.rfc-editor.org/rfc/rfc8725): kiểm tra JWT an toàn.
- [RFC 8693 — OAuth 2.0 Token Exchange](https://www.rfc-editor.org/rfc/rfc8693): delegation và token exchange.
- [RFC 9700 — Best Current Practice for OAuth 2.0 Security](https://www.rfc-editor.org/rfc/rfc9700): thực hành bảo vệ vòng đời token.
- [OWASP API1:2023 Broken Object Level Authorization](https://owasp.org/API-Security/editions/2023/en/0xa1-broken-object-level-authorization/): lỗi phân quyền theo đối tượng.
- [OWASP API5:2023 Broken Function Level Authorization](https://owasp.org/API-Security/editions/2023/en/0xa5-broken-function-level-authorization/): lỗi phân quyền theo chức năng/action.
- [OWASP Authorization Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Authorization_Cheat_Sheet.html): least privilege, deny-by-default và kiểm tra quyền ở phía server.
