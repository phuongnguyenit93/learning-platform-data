# Ngăn giả mạo ownerId, tenantId hoặc thuộc tính quyền trong request với Spring Security

## 1. Bài toán thực tế và mục tiêu bảo vệ

Giả sử ứng dụng SaaS lưu tài liệu theo tổ chức (tenant). Mỗi tài liệu có `id`, `tenantId`, `ownerId`, `title`, `content`, trạng thái và metadata quyền. Alice đăng nhập ở tổ chức `org-a` và được sửa tài liệu `d1` của chính mình. Một client gửi:

```http
PATCH /api/tenants/org-a/documents/d1 HTTP/1.1
Authorization: Bearer <valid-token-for-alice>
Content-Type: application/json

{
  "title": "Tên mới",
  "ownerId": "bob",
  "tenantId": "org-b",
  "isAdmin": true,
  "roles": ["ROLE_ADMIN"],
  "permissions": ["document:delete:any"]
}
```

**Vấn đề không phải token của Alice có hợp lệ hay không.** Token có thể hợp lệ, nhưng các trường `ownerId`, `tenantId`, `isAdmin`, `roles` và `permissions` trong request đều do client kiểm soát. Nếu backend chép những giá trị ấy vào JPA entity hoặc dùng chúng làm căn cứ quyết định quyền, Alice có thể chuyển quyền sở hữu, đưa tài liệu sang tenant khác hoặc tự nâng quyền.

Một biến thể khác còn nguy hiểm hơn:

```http
PATCH /api/tenants/org-a/documents/d2 HTTP/1.1
Authorization: Bearer <valid-token-for-alice>
Content-Type: application/json

{
  "title": "Thay đổi tài liệu của Bob",
  "ownerId": "alice"
}
```

Ở đây `d2` **thật sự thuộc Bob**. Nếu policy chỉ so sánh `request.ownerId == authentication.name`, biểu thức có thể trả true vì Alice chủ động điền tên mình vào body. Nhưng việc user nói “tôi là owner” không tạo ra quyền owner.

**Mục tiêu bài học:** xây một ranh giới tin cậy nhất quán, trong đó:

1. Danh tính người gọi được lấy từ **authentication đã được server xác minh**, không lấy từ JSON hoặc header tùy ý.
2. `ownerId` và `tenantId` hiện hành của tài liệu được lấy từ **bản ghi nguồn tin cậy trong database**, không lấy từ payload muốn cập nhật.
3. Tenant được client chọn là **đối tượng yêu cầu**; quyền thành viên tenant được server kiểm chứng.
4. Request DTO chỉ chứa các trường thực sự được phép chỉnh sửa.
5. `@PreAuthorize` kiểm tra **role/authority + ownership/tenant/ACL** trước service method; service/database vẫn bảo đảm invariant tại thời điểm ghi.
6. Quyền quản trị và chuyển owner/tenant là **use case riêng** có authorization, validation và audit riêng.
7. Regression tests xác minh không rò dữ liệu, không ghi trái phép, không nâng quyền dù client thay ID, thêm field lạ hoặc dùng token hợp lệ của tenant khác.

Bài này thuộc phần **Kiểm tra trước phương thức** của Spring Security authorization, trọng tâm là `@PreAuthorize` và policy bean; các lớp DTO, persistence, transaction và test được trình bày như cơ chế phối hợp, không thay thế method security.

## 2. Mô hình đe dọa: ba dạng nhầm ranh giới tin cậy

### 2.1. Broken Object Level Authorization (BOLA/IDOR)

Một user được gọi endpoint, nhưng lại thao tác trên **đối tượng không thuộc quyền của mình** bằng cách đổi ID ở path, query hoặc payload:

```http
GET /api/documents/d1       # Tài liệu của Alice
GET /api/documents/d2       # Thay d1 thành tài liệu của Bob
```

`hasAuthority('document:read')` chỉ chứng minh caller có quyền dùng **chức năng đọc tài liệu**, không chứng minh caller có quyền đọc **d2**. OWASP API1:2023 gọi đây là *Broken Object Level Authorization*. UUID khó đoán không thay thế việc kiểm tra owner, tenant hoặc ACL.

### 2.2. Broken Object Property Level Authorization / mass assignment

Client gửi thêm những thuộc tính không được quyền sửa:

```json
{
  "displayName": "Alice",
  "role": "ADMIN",
  "emailVerified": true,
  "accountLocked": false
}
```

Nếu controller deserialize trực tiếp thành entity tài khoản và gọi `save`, những thuộc tính nhạy cảm có thể thay đổi. OWASP API3:2023 đề cập *Broken Object Property Level Authorization*, bao gồm nguy cơ mass assignment. Phải kiểm soát **thuộc tính nào được đọc/ghi bởi mỗi endpoint**, không chỉ đối tượng nào được truy cập.

### 2.3. Tenant confusion / cross-tenant access

Một SaaS có tenant `org-a` và `org-b`. User là thành viên org-a nhưng thử:

```http
GET /api/tenants/org-b/documents/d9
X-Tenant-Id: org-b
```

Path/header chứa tenant ID là **selector do client đề xuất**, không phải bằng chứng người gọi thuộc tenant. Nếu repository chỉ `findById(d9)` rồi trả luôn dữ liệu, tài liệu giữa tổ chức có thể bị lộ.

**Ba phép hỏi khác nhau:** “đúng user?”, “đúng object?”, “đúng property/action?” Tất cả đều cần trả lời dựa trên server-side facts.

## 3. Bảng phân loại nguồn dữ liệu: cái gì có thể tin?

| Nguồn | Client có điều khiển? | Có thể dùng làm authority/owner/tenant thật? |
| --- | --- | --- |
| JSON `ownerId`, `tenantId`, `roles`, `isAdmin` | Có | **Không** |
| URL path variable `/tenants/{tenantId}` | Có | Chỉ là scope được yêu cầu; cần kiểm membership |
| Query `?userId=...` | Có | Chỉ là target ID; không phải caller identity |
| Header `X-User-Id` hoặc `X-Role` từ public client | Có | **Không** |
| Hidden form field, React state, localStorage | Có | **Không** |
| Cookie session ID | Client gửi, server xác minh session | Identity lấy từ session đã xác thực, không từ text client tự khai |
| JWT Bearer có signature/issuer/audience/expiry được kiểm chứng | Client mang token nhưng không được tự sửa claims hợp lệ | Có thể lấy trusted subject/claims, **vẫn cần membership và revocation policy** |
| `Authentication` được Spring Security xác thực | Do server-side security chain xây dựng | Nguồn danh tính/authorities, cần hiểu mapping |
| Bản ghi `documents.owner_id`, `documents.tenant_id` trong DB | Server quản lý | Nguồn sự thật của ownership/scope hiện tại |
| Bảng `tenant_memberships` / ACL server | Server quản lý | Nguồn sự thật của membership và quyền theo đối tượng |
| Dữ liệu kiểm tra quyền từ trusted authorization service | Server xác minh qua kênh tin cậy | Có thể dùng theo hợp đồng và độ mới dữ liệu |

**Nguyên tắc vàng:** **client được phép chọn đối tượng cần thao tác, nhưng không được tự chứng nhận mình có quyền trên đối tượng đó**.

### 3.1. “Token có ký số” không tự chứng minh quyền trên mọi bản ghi

JWT hợp lệ chỉ chứng minh các claims được issuer chấp nhận tại thời điểm cấp và còn hợp lệ theo quy tắc xác minh. Nó không tự cho user quyền trên một `documentId` bất kỳ. Token cũng có thể chứa claim `tenant` cũ hoặc role đã bị thu hồi nếu hệ thống chưa có cơ chế làm mới/revocation.

Kiểm tra issuer, audience, signature, expiry, subject mapping và nguồn authority. Với thao tác nhạy cảm hoặc multi-tenant thay đổi nhanh, kiểm tra membership/resource policy ở nguồn tin cậy tại thời điểm hành động.

### 3.2. Reverse proxy trusted headers cần ranh giới riêng

Một gateway nội bộ có thể đưa ID đã xác thực qua header, nhưng chỉ tin header ấy khi gateway **đã xác minh identity**, kết nối backend không cho client truy cập trực tiếp, và gateway **xóa/ghi đè** mọi header do client tự đưa cùng tên. Không áp dụng sơ đồ trust này cho `X-User-Id` từ browser bình thường.

## 4. Sai lầm điển hình: tự so sánh thuộc tính client gửi

### 4.1. Anti-pattern #1: so sánh ownerId trong body

```java
@PreAuthorize("#request.ownerId == authentication.name")
public void update(DocumentUpdateRequest request) {
    documentRepository.save(mapper.toEntity(request));
}
```

**Sai về logic:** `request.ownerId` đến từ client, không phải chủ sở hữu được xác minh ở DB. Alice có thể đưa `ownerId = alice` trong body để hợp thức hóa thao tác trên tài liệu Bob. `authentication.name` đáng tin hơn chỉ khi đã được ánh xạ từ authentication hợp lệ, nhưng **phía đối chiếu vẫn không đáng tin**.

### 4.2. Anti-pattern #2: lấy tenantId từ body làm lệnh thay tenant

```java
public void updateDocument(String id, DocumentPatch request) {
    Document doc = repository.findById(id).orElseThrow();
    doc.setTenantId(request.tenantId());
    doc.setOwnerId(request.ownerId());
    doc.setTitle(request.title());
}
```

Code này biến việc sửa title thành chức năng chuyển tài liệu giữa tổ chức và thay owner. Một user có permission chỉnh title có thể được cấp quyền chuyển tài sản giữa tenant ngoài ý muốn.

### 4.3. Anti-pattern #3: client định nghĩa principal roles

```java
if (request.isAdmin()) {
    account.setAdmin(true);
}
```

hoặc:

```java
authentication = new UsernamePasswordAuthenticationToken(
        request.username(), null, request.authorities());
```

Các thuộc tính quyền client gửi không được tự chuyển thành `GrantedAuthority`. Quyền phải đến từ cơ chế xác thực/cấp quyền do server kiểm soát. Token/session hợp lệ cũng không làm field `isAdmin` trong JSON trở nên tin cậy.

### 4.4. Anti-pattern #4: suy quyền từ UI

Ẩn nút “Delete” trong React hoặc disable input `ownerId` không bảo vệ endpoint. Client có thể gọi HTTP trực tiếp, sửa DevTools request, dùng REST client hoặc tự script. UI là trải nghiệm; security enforcement nằm ở server.

### 4.5. Anti-pattern #5: chỉ kiểm role tổng quát

```java
@PreAuthorize("hasRole('USER')")
public DocumentView get(String id) {
    return repository.findById(id).map(mapper::toView).orElseThrow();
}
```

Có `ROLE_USER` không chứng minh user đọc được **mọi document**. Để tránh BOLA/IDOR, cần lookup/authorization theo tenant, owner hoặc ACL, không chỉ role chức năng.

## 5. Định nghĩa policy theo danh tính và dữ liệu server

### 5.1. Invariant cho tài liệu

Mô hình giả định:

```text
Document:
  id         = định danh tài liệu
  tenantId   = tenant đang sở hữu tài liệu (server-managed)
  ownerId    = user đang sở hữu tài liệu (server-managed)
  title      = nội dung user có thể chỉnh theo use case
  body       = nội dung user có thể chỉnh theo use case
  status     = trạng thái workflow (server-managed)
  version    = số phiên bản optimistic locking
```

Viết rõ điều kiện cho thao tác EDIT:

```text
ALLOW_EDIT(actor, target) =
    actor authenticated
    AND actor has "document:edit" authority
    AND actor is active member of target.tenantId
    AND target belongs to selected tenant scope
    AND target.status allows editing
    AND (
        target.ownerId == actor.userId
        OR actor has vetted "document:edit:any" within tenant
    )
```

Đây là **pseudo-policy nghiệp vụ**, không phải API của Spring. Hệ thống có thể bổ sung ACL, group membership, security label, phân tách trách nhiệm và approval workflow.

### 5.2. Giữ tách biệt các loại quyền

| Kiểm tra | Nguồn sự thật | Ví dụ |
| --- | --- | --- |
| Identity | Authenticated principal | Alice có user ID `u1` |
| Functional authority | Trusted mapped GrantedAuthority | `document:edit` |
| Membership | DB/verified membership service | u1 thuộc org-a và đang active |
| Ownership | Bản ghi document trong DB | d1.ownerId = u1 |
| Tenant boundary | Bản ghi document + selected tenant được kiểm | d1.tenantId = org-a |
| State | Bản ghi và policy | d1.status = DRAFT |
| Special privilege | Server-side policy + scope | `document:edit:any` chỉ trong org-a |

Những phép kiểm này phải tách để tránh cấp “role ADMIN” ở tenant này rồi dùng trên tenant khác. Một hệ thống có global admin thật sự cần định nghĩa **quyền cross-tenant rõ ràng** và audit riêng, không lấy vai trò “ADMIN” chung làm dấu hiệu đủ cho mọi trường hợp.

### 5.3. Tại sao chọn đối tượng rồi xác minh?

Một request `PATCH /documents/d2` có thể dùng ID d2 do client cung cấp để **tìm target**. Nhưng sau khi tìm, backend phải kiểm tài liệu thực đang thuộc tenant/owner nào. Không thay bằng phép so sánh giữa hai tham số đều do client tự nhập:

```java
// SAI: cả hai đối số có thể do client điều khiển.
return request.tenantId().equals(pathTenantId);
```

Thỏa điều kiện đó chỉ chứng minh hai chuỗi client gửi giống nhau, không chứng minh quyền tenant.

## 6. Chọn API contract không cho sửa metadata bảo mật

### 6.1. Dùng DTO allowlist với Java record

Ví dụ Java 17+:

```java
package com.example.documents.api;

import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Size;

public record CreateDocumentRequest(
        @NotBlank @Size(max = 200) String title,
        @NotBlank String body) {
}
```

DTO tạo tài liệu **không** nhận `ownerId`, `tenantId` hoặc `roles`. Controller lấy actor từ authentication, tenant từ selector được kiểm tra membership và set các thuộc tính quản lý bằng server code.

DTO cập nhật cũng nên hẹp:

```java
package com.example.documents.api;

import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Size;

public record UpdateDocumentRequest(
        @NotBlank @Size(max = 200) String title,
        @NotBlank String body) {
}
```

Hai class này là **mã tích hợp vào Spring Boot project**, không phải chương trình Java độc lập khi thiếu Jakarta Validation dependency. Chỉ chứa field mà người gọi bình thường có quyền yêu cầu thay đổi.

### 6.2. Ví dụ request hợp lệ

```http
PATCH /api/tenants/org-a/documents/d1 HTTP/1.1
Content-Type: application/json
Authorization: Bearer <alice-token>

{
  "title": "Hướng dẫn cập nhật",
  "body": "Nội dung đã sửa"
}
```

Server tự xác định:

```text
actorId    = identity resolved from verified Authentication
tenantId   = verified selected tenant + target document tenant
ownerId    = current document.ownerId from database
authorities = verified Authentication / trusted permission service
```

Không cho client quyết định các trường đó qua PATCH bình thường.

### 6.3. Unknown JSON properties: reject hay ignore?

Với body chứa thêm `isAdmin` hoặc `ownerId`, hai chiến lược hợp lệ nếu thực hiện nhất quán:

1. **Reject unknown fields** (ví dụ HTTP 400): contract rõ và dễ phát hiện client gửi field ngoài schema.
2. **Ignore unknown fields**: chỉ bind các trường allowlisted trong DTO và chứng minh qua test không có side effect lên metadata bảo mật.

**Chú ý:** Spring/Jackson behavior với unknown fields phụ thuộc cấu hình `ObjectMapper`/Spring Boot, không thể mặc định coi mọi request field lạ sẽ trả 400. `@Valid` chỉ kiểm tra ràng buộc dữ liệu của những field đã bind; **không** là cơ chế phòng mass assignment nếu DTO/entity đã mở những field nhạy cảm.

### 6.4. Đừng dùng DTO gồm mọi field rồi chỉ “bỏ qua” ở UI

Một DTO như:

```java
public record UpdateDocumentRequest(
        String title,
        String body,
        String ownerId,
        String tenantId,
        boolean isAdmin) {
}
```

làm các field nhạy cảm xuất hiện ở boundary không cần thiết, dễ bị ai đó dùng sau này qua `BeanUtils.copyProperties` hoặc mapper. Thiết kế DTO tối thiểu để compiler và code review hỗ trợ bảo vệ, không phải dựa vào lời hứa “controller hiện tại sẽ không dùng field đó”.

## 7. Lấy identity từ Spring Security, không lấy từ request body

### 7.1. Controller nhận Authentication do framework cung cấp

Ví dụ fragment Spring MVC:

```java
@RestController
@RequestMapping("/api/tenants/{tenantId}/documents")
public class DocumentController {

    private final DocumentApplicationService service;

    public DocumentController(DocumentApplicationService service) {
        this.service = service;
    }

    @PatchMapping("/{documentId}")
    public DocumentView update(
            @PathVariable String tenantId,
            @PathVariable String documentId,
            @Valid @RequestBody UpdateDocumentRequest request) {

        // Không nhận ownerId/role/isAdmin từ request.
        return service.update(tenantId, documentId, request);
    }
}
```

Đây là **fragment**: các class `DocumentApplicationService`, `DocumentView` và imports/framework context phải được project cung cấp. Điều quan trọng: controller chỉ chuyển **target selector** và **editable fields**, không tạo actor từ JSON.

Trong service/policy, lấy current authentication:

```java
Authentication authentication =
        SecurityContextHolder.getContext().getAuthentication();
```

Authentication này do security chain thiết lập sau khi xác thực, **không** được tạo bằng các trường quyền từ client. Đối với async job, cần có service identity/delegation đáng tin và propagation đúng; không tự đặt `ROLE_ADMIN` tùy ý chỉ để job hoạt động.

### 7.2. authentication.name có luôn là userId nội bộ?

**Không.** Với form login, `getName()` thường là username; với JWT, có thể là `sub` hoặc principal name được converter cấu hình; với OAuth2/custom principal có thể là tên khác. Nếu database lưu `ownerId` bằng UUID, so sánh UUID với email/username sẽ sai.

Định nghĩa một `ActorResolver` chịu trách nhiệm ánh xạ authentication đã được xác minh sang **stable internal actor ID**:

```java
public interface ActorResolver {
    Actor requireCurrentActor();
}

// Pseudocode contract do dự án định nghĩa:
public record Actor(String userId, String selectedTenantId) {}
```

Trong implementation, lấy dữ liệu từ authentication đã được tin cậy, mapping theo issuer/subject và bảng user identity. Không để request controller truyền tuỳ ý `new Actor(request.ownerId(), request.tenantId())`.

### 7.3. Với JWT Resource Server

Ví dụ ở controller khi dùng JWT:

```java
@GetMapping("/me")
public UserProfile me(@AuthenticationPrincipal Jwt jwt) {
    String verifiedSubject = jwt.getSubject();

    // Map issuer + subject sang user ID nội bộ bằng service tin cậy.
    return profileService.loadForVerifiedSubject(verifiedSubject);
}
```

Đây là fragment yêu cầu Spring Security OAuth2 Resource Server và `Jwt`. Bản thân chữ `sub` không bắt buộc là DB ID và có thể trùng giữa issuers; khi có multi-issuer, mapping cần ràng buộc issuer/audience và dựa vào token **đã được verifier kiểm tra**. Đừng lấy chuỗi `sub` do client gửi riêng ở JSON làm nguồn principal.

### 7.4. JWT claims như tenantId hoặc roles không phải giấy thông hành vĩnh viễn

JWT có thể chứa tenant/roles được ký nhưng còn phản ánh **trạng thái tại lúc cấp token**. Nếu user vừa rời tenant hoặc bị thu hồi quyền, token cũ có thể còn hiệu lực đến lúc expiry nếu hệ thống không có kiểm soát bổ sung.

Với thao tác nhạy cảm, dựa vào active membership/ACL ở database hoặc trusted policy service. Nếu dùng scoped token với tenant claim, phải kiểm:
- token được xác thực bởi issuer đã tin;
- tenant claim phù hợp với target resource;
- user có membership/quyền hiệu lực đúng tenant;
- business policy quyết định action có được phép không.

### 7.5. Header tenant là selector, không phải source of truth

`X-Tenant-Id: org-b` có thể giúp chọn tenant trong giao diện multi-tenant. Nhưng client không được tự biến mình thành member org-b bằng header đó. Treat selected tenant like `documentId`: một tham số yêu cầu phải được **so với server-side membership và target resource**.

## 8. @PreAuthorize kiểm tra trước method bằng policy bean

### 8.1. Bật method security

Trong Spring Security Servlet hiện đại:

```java
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;

@Configuration
@EnableMethodSecurity
public class MethodSecurityConfiguration {
}
```

`@EnableMethodSecurity` bật support `@PreAuthorize` theo mặc định. Spring Boot starter security không tự bật method-level rules. Annotation chỉ được thực thi khi invocation đi qua Spring-managed proxy/method interceptor phù hợp.

### 8.2. Anti-pattern: kiểm hai field đều từ client

```java
@PreAuthorize(
    "#request.ownerId == authentication.name and " +
    "#request.tenantId == #tenantId"
)
public void update(String tenantId, UpdateRequest request) { /* ... */ }
```

Biểu thức này **không hề tra owner/tenant thật của document**. Alice có thể gửi `ownerId=alice` và `tenantId=org-a` trong body để qua, trong khi path `documentId` chỉ tới record Bob hoặc record org-b.

### 8.3. Thay bằng trusted service policy

Một policy đúng về ý nghĩa:

```java
@PreAuthorize(
    "isAuthenticated() and " +
    "hasAuthority('document:edit') and " +
    "@documentAccess.canEdit(authentication, #tenantId, #documentId)"
)
public DocumentView update(
        String tenantId,
        String documentId,
        UpdateDocumentRequest request) {
    // ...
}
```

Trong expression:
- `authentication` lấy từ method-security expression context.
- `tenantId` và `documentId` là **target selectors không đáng tin**, phải được policy xác minh.
- `@documentAccess` là bean ứng dụng tự viết, không phải method có sẵn của Spring.
- `canEdit` phải lấy **current owner/tenant/status/ACL** từ DB và verified actor, không lấy owner từ request.
- `hasAuthority('document:edit')` kiểm functional permission; bean xử lý object-level policy.

Đừng suy rằng permission `document:edit` của tenant A được dùng toàn cục; nếu authorities có tenant scope, policy phải diễn đạt và kiểm đúng scope.

### 8.4. Một policy bean đơn giản, fail-closed

```java
package com.example.documents.security;

import org.springframework.security.core.Authentication;
import org.springframework.stereotype.Component;

@Component("documentAccess")
public class DocumentAccessPolicy {

    private final ActorResolver actorResolver;
    private final TenantMembershipRepository memberships;
    private final DocumentRepository documents;

    public DocumentAccessPolicy(
            ActorResolver actorResolver,
            TenantMembershipRepository memberships,
            DocumentRepository documents) {
        this.actorResolver = actorResolver;
        this.memberships = memberships;
        this.documents = documents;
    }

    public boolean canEdit(
            Authentication authentication,
            String tenantId,
            String documentId) {

        if (authentication == null || tenantId == null
                || documentId == null || tenantId.isBlank()
                || documentId.isBlank()) {
            return false;
        }

        // ActorResolver phải ánh xạ verified Authentication
        // sang user ID nội bộ; không lấy userId từ request.
        String actorId = actorResolver.requireUserId(authentication);

        if (!memberships.isActiveMember(actorId, tenantId)) {
            return false;
        }

        var target = documents.findByIdAndTenantId(
                documentId, tenantId);
        if (target.isEmpty()) {
            return false;
        }

        var document = target.get();
        if (!document.canBeEditedInCurrentStatus()) {
            return false;
        }

        boolean owns = actorId.equals(document.getOwnerId());
        boolean delegated = memberships.hasDocumentEditAnyGrant(
                actorId, tenantId);

        return owns || delegated;
    }
}
```

**Đây là class tích hợp/kiến trúc, không biên dịch độc lập** nếu chưa có `ActorResolver`, `TenantMembershipRepository`, `DocumentRepository`, `Document` và imports tương ứng. Methods `isActiveMember`, `hasDocumentEditAnyGrant`, `findByIdAndTenantId`, `canBeEditedInCurrentStatus` là hợp đồng **ứng dụng phải tự triển khai** dựa trên dữ liệu tin cậy.

**Quan trọng:** `ActorResolver.requireUserId` có thể ném exception khi token/subject mapping invalid; policy/exception translation phải fail-closed. Với policy cần xử lý cross-tenant, hãy dùng scope/quyền riêng chứ không trả `true` do thấy role ADMIN không ràng buộc tenant.

### 8.5. Tên tham số trong SpEL

`#tenantId` và `#documentId` chỉ hoạt động nếu Spring Security discover được tên tham số trong compiled code (ví dụ compiler `-parameters` hoặc annotation `@P`):

```java
import org.springframework.security.access.method.P;

@PreAuthorize(
    "@documentAccess.canEdit(authentication, #tenant, #target)"
)
public DocumentView update(
        @P("tenant") String tenantId,
        @P("target") String documentId,
        UpdateDocumentRequest request) {
    // ...
}
```

Ví dụ là **fragment**. Nếu expression không thấy parameter, có thể ném lỗi hoặc đánh giá sai; kiểm tra qua integration tests, không chỉnh biểu thức thành `permitAll` để “sửa”.

## 9. Pre-check không đủ nếu dữ liệu có thể thay đổi giữa lúc check và ghi

### 9.1. TOCTOU: time of check vs time of use

Giả sử:

```text
T0: canEdit đọc d1.ownerId=alice => cho phép.
T1: Một admin chuyển d1.ownerId=bob.
T2: Service của Alice ghi d1.title sau khi được cho phép ở T0.
```

Nếu quyền chỉ được kiểm ở `@PreAuthorize` trước transaction/body, phép kiểm có thể bị “lỗi thời” khi data thay đổi. Đây là dạng *time-of-check-to-time-of-use*.

**Giải pháp:** giữ `@PreAuthorize` như cổng đầu, đồng thời:
- Nạp target lại trong transaction có ràng buộc tenant.
- Tái kiểm owner/ACL/status ngay trước mutation.
- Dùng optimistic locking (`@Version`), pessimistic lock hoặc **guarded SQL update** theo tính chất use case.
- Đảm bảo thao tác ghi và điều kiện quyền có cùng transaction/isolation phù hợp.

Không nghĩ rằng chỉ thêm `@Transactional` là luôn loại mọi race: method-security advice và transaction interceptor có thể chạy theo thứ tự; giữa hai lần đọc vẫn có concurrency tùy isolation. Với hành động nhạy cảm, kiểm tra điều kiện ở câu lệnh ghi thường mạnh hơn.

### 9.2. Guarded SQL update cho owner-only operation

Ví dụ PostgreSQL/SQL minh họa:

```sql
UPDATE documents
SET title = :new_title,
    version = version + 1
WHERE id = :document_id
  AND tenant_id = :authorized_tenant_id
  AND owner_id = :trusted_actor_id
  AND status = 'DRAFT'
  AND version = :expected_version;
```

Các tham số phải được bound bằng prepared statement/JPA query, **không nối raw SQL từ request**. Đặc biệt `trusted_actor_id` lấy từ authentication identity resolver, `authorized_tenant_id` đã được kiểm membership, còn `owner_id` trong DB là điều kiện bảo vệ.

**Ý nghĩa kết quả:**
- Affected rows = 1 → điều kiện tại thời điểm update đạt; mutation xảy ra.
- Affected rows = 0 → không có record phù hợp/khác tenant/khác owner/status/version cũ; không được mặc định update lại bằng `WHERE id=:id` đơn thuần.

Đây chỉ là mẫu cho **owner-only editing**; quyền `document:edit:any` cần nhánh policy/câu lệnh riêng có scope và audit. Không mở rộng câu SQL thành `OR :isAdminFromBody`.

### 9.3. @Version và ghi đè đồng thời

Một JPA entity có:

```java
@Version
private long version;
```

cho phép optimistic locking phát hiện xung đột cập nhật dữ liệu. Nhưng **`@Version` không tự chứng minh quyền owner/tenant**. Cần kết hợp version với policy scoping và cập nhật đúng nguồn quyền. Nếu yêu cầu atomic membership + mutation ở mức mạnh, cân nhắc transaction locks, security checks trong DB hoặc quy trình nhất quán tương ứng hạ tầng.

### 9.4. Không dùng @PostAuthorize để “kiểm sau khi xóa”

```java
@PostAuthorize("returnObject.ownerId == authentication.name")
public Document deleteAndReturn(String id) {
    return repository.deleteById(id);
}
```

Đây là **anti-pattern ý tưởng**, và `deleteById` thực tế có return type khác tùy repository. Vấn đề chính: `@PostAuthorize` đánh giá sau method body, nên một write/delete có thể **đã xảy ra**. Tài liệu Spring Security cảnh báo `@PostAuthorize` không phù hợp để làm hàng rào duy nhất cho method ghi database.

Dùng `@PreAuthorize` và kiểm transaction/DB tại thời điểm mutation. `@PostAuthorize` có thể thích hợp ở một số read methods, nhưng với multi-tenant vẫn nên truy vấn **theo scope** trước khi tạo response.

## 10. Service update: diễn đạt hai lớp kiểm soát rõ ràng

### 10.1. Fragment service có kiểm tra trước và trong transaction

```java
package com.example.documents.service;

import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class DocumentApplicationService {

    private final DocumentRepository documents;
    private final ActorResolver actorResolver;
    private final TenantMembershipRepository memberships;

    public DocumentApplicationService(
            DocumentRepository documents,
            ActorResolver actorResolver,
            TenantMembershipRepository memberships) {
        this.documents = documents;
        this.actorResolver = actorResolver;
        this.memberships = memberships;
    }

    @Transactional
    @PreAuthorize(
        "isAuthenticated() and " +
        "hasAuthority('document:edit') and " +
        "@documentAccess.canEdit(authentication, #tenantId, #documentId)"
    )
    public DocumentView update(
            String tenantId,
            String documentId,
            UpdateDocumentRequest request) {

        String actorId = actorResolver.requireCurrentUserId();
        // tenantId là selector; membership phải đọc từ DB.
        if (!memberships.isActiveMember(actorId, tenantId)) {
            throw new AccessDeniedException("Access denied");
        }

        var document = documents.findByIdAndTenantId(
                documentId, tenantId).orElseThrow(
                    () -> new DocumentNotFoundException(documentId));

        if (!document.canBeEditedInCurrentStatus()) {
            throw new AccessDeniedException("Access denied");
        }

        boolean owns = actorId.equals(document.getOwnerId());
        boolean delegated = memberships.hasDocumentEditAnyGrant(
                actorId, tenantId);
        if (!owns && !delegated) {
            throw new AccessDeniedException("Access denied");
        }

        // Chỉ map trường cho phép.
        document.setTitle(request.title());
        document.setBody(request.body());

        // ownerId, tenantId, role/ACL và status không bị map.
        return new DocumentView(
                document.getId(),
                document.getTitle(),
                document.getBody());
    }
}
```

**Fragment Spring Boot/JPA** này cần application classes/repository/entities, imports cho DTO/view và exception `DocumentNotFoundException`. `ActorResolver.requireCurrentUserId()` phải đọc current verified authentication, không nhận userId từ body. Với transaction JPA, dirty checking có thể lưu changed title/body; nếu repository không phải JPA hoặc không managed entity, cần save/flush theo contract của persistence layer.

**Chưa giải quyết mọi race:** phần re-check giúp bảo vệ khi method thực thi, nhưng nếu ownership có thể đổi đồng thời ngay sau re-check, cần lock, version hoặc guarded write như mục 9. API cập nhật phải có test về concurrency nếu quyền sở hữu có thể thay đổi trong lúc request chạy.

### 10.2. Tại sao lookup theo cả id và tenant?

`findByIdAndTenantId(documentId, tenantId)` tạo một hàng rào bổ sung: document ID của org-b không bị lấy ra như một target hợp lệ trong org-a. Tuy nhiên, lookup theo tenant **không đủ** nếu Alice và Bob đều trong org-a nhưng Alice không được sửa tài liệu Bob. Còn phải kiểm owner/ACL.

### 10.3. Đừng để response chứa metadata ngoài quyền xem

Ngay cả khi user được đổi title/body, họ có thể không được xem các thuộc tính nhạy cảm `internalRiskScore`, `auditApprovers`, `tokens`. Response DTO nên whitelist các trường trả về, không serialize toàn bộ entity JPA mặc định.

Đây là phòng **broken object property level authorization khi đọc**; không chỉ là xử lý mass assignment khi ghi.

## 11. Tạo tài nguyên: owner và tenant được set phía server

### 11.1. Luồng create an toàn

```text
Client:
  POST /api/tenants/org-a/documents
  body = { "title": "...", "body": "..." }

Controller:
  parse DTO, validate editable fields

Security:
  authenticated + document:create

Application service:
  actorId = trusted Authentication mapping
  check active membership in org-a
  document.tenantId = org-a
  document.ownerId = actorId
  document.status = DRAFT
  document.roles/ACL = server policy
  save with tenant constraints
```

### 11.2. Fragment @PreAuthorize cho create

```java
@PreAuthorize(
    "isAuthenticated() and " +
    "hasAuthority('document:create') and " +
    "@tenantAccess.canCreate(authentication, #tenantId)"
)
@Transactional
public DocumentView create(
        String tenantId,
        CreateDocumentRequest request) {

    String actorId = actorResolver.requireCurrentUserId();
    tenantAccess.requireActiveMember(actorId, tenantId);

    Document created = new Document();
    created.setTenantId(tenantId);
    created.setOwnerId(actorId);
    created.setStatus(DocumentStatus.DRAFT);
    created.setTitle(request.title());
    created.setBody(request.body());

    return mapper.toView(repository.save(created));
}
```

Đây là **fragment** cần bean `tenantAccess` và dependencies do ứng dụng định nghĩa, cùng hợp đồng entity/mapper. Dù tenantId xuất hiện trên path và được dùng để set entity, **nó đã được xác minh membership và policy**; đó là khác biệt quyết định với việc lấy tenantId raw từ body mà không kiểm.

### 11.3. Không để create trả chủ sở hữu do client tự khai

Nếu request gửi thêm:

```json
{
  "title": "Tài liệu mới",
  "body": "Nội dung",
  "ownerId": "admin",
  "tenantId": "org-b",
  "isAdmin": true
}
```

hệ thống nên từ chối unknown fields theo contract hoặc bỏ qua chúng khi bind DTO; tuyệt đối không tạo tài liệu với owner/tenant từ các trường đó. Test DB sau create phải khẳng định:
- owner = trusted actor;
- tenant = tenant đã xác minh;
- status = trạng thái default server;
- role/ACL không bị nâng;
- các user khác không được tự lấy quyền chỉ nhờ gửi field lạ.

## 12. Tenant selection và active membership

### 12.1. Multi-tenant không chỉ là role USER/ADMIN

Một người có thể:

```text
Alice:
  org-a: EDITOR
  org-b: VIEWER
```

Nếu backend chỉ có global `ROLE_EDITOR`, Alice có thể bị cấp khả năng sửa tài liệu org-b nhầm. Cần mô hình **authority theo tenant** hoặc kiểm membership/role trong tenant tại policy.

Ví dụ policy:

```text
canEdit(actor, tenant, document) =
  activeMembership(actor, tenant)
  AND membershipRole(actor, tenant) includes EDITOR
  AND document.tenantId == tenant
  AND (document.ownerId == actor OR tenantGrant allows editAll)
```

Role hierarchy nếu có phải được áp dụng trong **scope tương ứng**, không đơn giản biến EDITOR org-a thành EDITOR toàn hệ thống.

### 12.2. Query path vs selected tenant

```http
GET /api/tenants/org-b/documents/d9
```

`org-b` chỉ là tenant mà client yêu cầu. Policy phải xác minh Alice có quyền org-b và document `d9` thực thuộc org-b. Không dùng `X-Tenant-Id` từ client để thay thế kiểm lookup.

### 12.3. Tránh tenant ID từ header ghi đè tenantId của row

Một interceptor có thể đặt “current tenant context” từ header. Nếu repository tự thêm tenant filter nhưng context đó được set từ header **không kiểm membership**, việc lọc theo tenant trở thành một cơ chế do user tùy ý điều khiển.

Nếu dùng `TenantContext`/Hibernate filters:
1. Chỉ set sau khi authentication/membership hợp lệ.
2. Dọn context đúng khi thread pool tái sử dụng.
3. Có test fallback/đường async/background jobs.
4. Không dùng nó như hàng rào duy nhất, đặc biệt cho raw SQL, native queries hoặc đường bypass filter.
5. Với row-level security DB, set session variables bằng nguồn tin cậy và kiểm scope của connection pool.

### 12.4. Gắn quyền object trước khi trả dữ liệu

Ngay cả read-only GET cũng cần kiểm scope. Không gọi `findAll()` rồi lọc trong frontend theo tenant; không serialize entity khác tenant trước rồi hy vọng browser ẩn trường. Lọc và authorize ở backend/database trước khi trả response.

## 13. Đổi chủ sở hữu, chuyển tenant và gán role là use case đặc quyền riêng

### 13.1. Tách endpoint và DTO

Không cho user update bình thường gửi `ownerId`. Nếu có chức năng **transfer ownership**:

```http
POST /api/tenants/org-a/documents/d1/transfer-owner
Content-Type: application/json
Authorization: Bearer <trusted-token>

{ "newOwnerId": "u9" }
```

Một DTO riêng:

```java
public record TransferOwnerRequest(String newOwnerId) {}
```

**Dù DTO có field `newOwnerId`, nó vẫn chỉ là target selector**. Policy phải xác minh:

- Actor có quyền `document:transfer-owner` trong tenant này.
- Tài liệu thật thuộc tenant đang xử lý.
- New owner tồn tại và là active member đủ điều kiện của tenant.
- Workflow/quy tắc chấp thuận cho phép chuyển.
- Tính nhất quán và audit trên transaction.

Tương tự, “chuyển tenant” có thể ảnh hưởng ownership, ACL, billing, retention và data residency. Không biến thao tác đó thành `PATCH tenantId` ngầm.

### 13.2. Gán role không thuộc profile update

```http
PATCH /api/users/u1/profile
{ "displayName": "Alice", "roles": ["ROLE_ADMIN"] }
```

Endpoint profile chỉ nên cập nhật display name/fields tương ứng. Gán role cần use case riêng:

```http
POST /api/admin/tenants/org-a/users/u1/grants
{ "permission": "document:review" }
```

Nó phải xác minh actor được phép cấp **đúng permission**, không cho cấp cao hơn quyền delegable, kiểm target user/tenant, SoD, approvals, expiry và audit. `hasRole('ADMIN')` đơn lẻ có thể chưa đủ trong SaaS đa tenant hoặc permission delegation nhạy cảm.

### 13.3. Bảo vệ trước privilege escalation

Nếu user chỉ có `users:manage-basic`, không nên được cấp `ROLE_SUPER_ADMIN` cho bản thân hoặc đồng nghiệp. Một mẫu policy:

```text
ALLOW_GRANT(actor, target, grant) =
  actor has "user:grant:manage" in target tenant
  AND grant in actor.allowedDelegableGrants
  AND target is eligible in target tenant
  AND (actor != target OR explicit self-grant allowed)
  AND approval / separation-of-duties rules satisfied
```

Chính sách này là **pseudocode nghiệp vụ**. Danh sách `allowedDelegableGrants` phải do backend/DB/policy service đáng tin quản lý, không được lấy từ payload request.

## 14. Spring MVC binding: DTO, @ModelAttribute và Jackson

### 14.1. @RequestBody JSON và @ModelAttribute form data khác nhau

- `@RequestBody` thường bind JSON/XML qua `HttpMessageConverter` (thường Jackson cho JSON).
- `@ModelAttribute` dùng Spring `WebDataBinder` để bind form/query/path/header data vào model object theo rules.
- Cả hai đều phải tránh bind trực tiếp vào entity chứa `ownerId`, `tenantId`, `roles`, `balance`, `locked`.

Spring Framework reference khuyến nghị dùng object được thiết kế riêng cho web binding, hoặc constructor binding; nếu dùng property binding, cấu hình **allowedFields** chặt.

### 14.2. Dùng @InitBinder với allowlist khi phải bind form object

```java
@InitBinder("profileForm")
public void initBinder(WebDataBinder binder) {
    binder.setAllowedFields("displayName", "timezone");
}

@PostMapping("/profile")
public String updateProfile(
        @ModelAttribute("profileForm") ProfileForm form) {
    // Không cho client bind role, isAdmin, ownerId.
    // Vẫn cần authorization trên user profile.
    return "redirect:/profile";
}
```

Đây là **fragment MVC** với `ProfileForm` ứng dụng tự định nghĩa, không phải code độc lập. `allowedFields` giảm surface của binder nhưng không thay kiểm authorization trên profile đích. Nếu dùng constructor binding, kiểm tra cả constructor parameters và DTO schema.

### 14.3. Không dùng BeanUtils.copyProperties bừa bãi

```java
// Anti-pattern khi request có field không nên ghi:
BeanUtils.copyProperties(request, persistentUser);
```

Nếu request chứa field `roles` hoặc `isAdmin` và object có setter tương ứng, helper generic có thể vô tình chuyển giá trị nhạy cảm. Một allowlist explicit:

```java
user.setDisplayName(request.displayName());
user.setTimeZone(request.timeZone());
```

giúp reviewer thấy rõ chính xác thuộc tính nào được phép sửa. Mapper code generation cũng phải được cấu hình chỉ map trường hợp lệ; đừng coi MapStruct hay reflection mapper tự biết permission của người gọi.

### 14.4. Bean Validation không phải authorization

`@NotBlank`, `@Size`, `@Email` chỉ giúp validate định dạng/giới hạn dữ liệu. Một `@Valid` DTO có `ownerId` hợp lệ theo định dạng **vẫn** là field client có thể giả mạo. Cần phân tách:
- validation: dữ liệu có hợp lệ về syntax không?
- authentication: caller là ai?
- authorization: caller có được chỉnh tài nguyên/thuộc tính này không?
- domain invariant: trạng thái sau update có hợp lệ không?

## 15. Kiểm thử: làm sao chứng minh không thể giả mạo?

### 15.1. Ma trận tối thiểu

Giả sử:
- Alice thuộc org-a, sở hữu `d1` và có `document:edit`.
- Bob thuộc org-a, sở hữu `d2`.
- Mallory thuộc org-b, sở hữu `d3`.
- Editor tổ chức có `document:edit:any` trong org-a.
- Viewer có `document:read`, không có `document:edit`.

| Tình huống | Request | Kỳ vọng |
| --- | --- | --- |
| Alice sửa title d1 | Đúng tenant + permission + owner | ALLOW, title được cập nhật |
| Alice thêm `ownerId=bob` vào JSON sửa d1 | Extra sensitive field | REJECT hoặc IGNORE; owner DB không đổi |
| Alice thêm `isAdmin=true`, `roles=[ADMIN]` | Extra permission fields | Không được nâng quyền |
| Alice sửa d2 của Bob và khai `ownerId=alice` | Object-level forgery | DENY, d2 không đổi |
| Alice sửa d3 trong org-b | Cross-tenant | DENY/NOT_FOUND, d3 không đổi |
| Alice đổi path tenant sang org-b | Forged selected tenant | DENY vì không có membership |
| Bob sửa tài liệu của Bob | Đúng quyền | ALLOW |
| Viewer sửa tài liệu của mình | Thiếu functional permission | DENY |
| User có edit:any org-a sửa d2 | Có quyền có scope | ALLOW trong org-a, không tự mở org-b |
| Admin của org-a đổi role trong org-b | Sai scope | DENY |
| Alice chuyển owner bằng PATCH title | Không phải transfer endpoint | Không đổi owner |
| Alice thử cấp ROLE_ADMIN qua profile | Mass assignment | Không đổi authorities |
| Alice sửa d1 sau khi bị rời org-a | Revoked membership | DENY nếu policy yêu cầu active membership |
| Alice sửa d1 sau khi owner đổi thành Bob | Stale ownership | DENY với policy thực tại thời điểm ghi |
| Một request gửi documentId d2 không thuộc scope | Direct object reference | Không leak nội dung d2 |
| Test chỉ @WithMockUser(roles=ADMIN) | Fixture quá quyền | Không chứng minh user thường bị chặn |

**Kỳ vọng về HTTP status:** có thể dùng 403 cho resource đã biết nhưng thiếu quyền, hoặc 404 để không tiết lộ object khác tenant, theo contract/anti-enumeration policy của ứng dụng. Kết quả quan trọng hơn mã cụ thể là **không đọc/ghi trái phép và không leak dữ liệu**. Nếu hệ thống chọn 404, không được trả metadata khác tenant trong error body.

### 15.2. MockMvc test owner bị giả mạo

Fragment trong Spring Boot test có `MockMvc`, `@WithMockUser`/authentication mapping test, repository fixture và CSRF handling:

```java
@Test
@WithMockUser(username = "alice",
        authorities = "document:edit")
void cannotEditBobsDocumentByForgingOwnerId() throws Exception {

    mockMvc.perform(patch("/api/tenants/org-a/documents/d2")
            .contentType(MediaType.APPLICATION_JSON)
            .content("""
                    {
                      "title": "Overwritten",
                      "body": "Bad change",
                      "ownerId": "alice"
                    }
                    """)
            .with(csrf()))
        .andExpect(status().isForbidden());

    assertThat(documentRepository.findById("d2").orElseThrow()
            .getTitle()).isEqualTo("Bob original");
}
```

**Điều kiện của fragment:** fixture `d2` thuộc Bob trong org-a, Alice có edit nhưng không edit:any, API contract **ignore** extra JSON fields và kiểm quyền trước write; nếu cấu hình reject unknown fields thì request có thể trả 400 sớm. Trong cả hai trường hợp, dữ liệu phải không đổi. Test không được “pass” chỉ vì JSON parser trả 400 rồi tưởng object policy đã được test; bổ sung một test **không có field lạ** vẫn sửa d2 trái phép và assert deny.

### 15.3. MockMvc test body có thể chứa field lạ nhưng không đổi metadata

```java
@Test
@WithMockUser(username = "alice",
        authorities = "document:edit")
void editableFieldsDoNotOverwriteOwnerOrTenant() throws Exception {

    mockMvc.perform(patch("/api/tenants/org-a/documents/d1")
            .contentType(MediaType.APPLICATION_JSON)
            .content("""
                    {
                      "title": "Safe update",
                      "body": "Content",
                      "ownerId": "bob",
                      "tenantId": "org-b",
                      "isAdmin": true
                    }
                    """)
            .with(csrf()))
        .andExpect(status().isOk());

    var saved = documentRepository.findById("d1").orElseThrow();
    assertThat(saved.getOwnerId()).isEqualTo("alice");
    assertThat(saved.getTenantId()).isEqualTo("org-a");
}
```

Đây là **fragment minh họa contract ignore-unknown-fields** và giả định controller trả 200, fixture + auth mapping đúng. Nếu ứng dụng chọn **reject unknown fields**, đổi expected thành 400 và assert mọi field không đổi; không phải sửa SecurityFilterChain để cho request qua. Phải kiểm `authorities` của Alice ở server không thay đổi, không chỉ entity owner/tenant.

### 15.4. Test path tenant bị giả mạo

```java
@Test
@WithMockUser(username = "alice",
        authorities = "document:edit")
void cannotUseAnotherTenantPath() throws Exception {

    mockMvc.perform(patch("/api/tenants/org-b/documents/d3")
            .contentType(MediaType.APPLICATION_JSON)
            .content("""
                    { "title": "Attempt", "body": "Attempt" }
                    """)
            .with(csrf()))
        .andExpect(status().isForbidden());

    assertThat(documentRepository.findById("d3").orElseThrow()
            .getTitle()).isEqualTo("Mallory original");
}
```

Một project có anti-enumeration chọn 404 cho trường hợp này thì test theo contract 404; quan trọng là d3 không đổi. Cần fixture `tenant_memberships` với Alice chỉ ở org-a.

### 15.5. Test service-level qua proxy

Unit test `DocumentAccessPolicy` có thể mock repo và trả:
- document tenant org-b khi selected org-a → false;
- doc org-a nhưng owner Bob, không edit:any → false;
- doc org-a owner Alice, active membership → true;
- actor thiếu membership → false;
- document locked → false.

Sau đó integration test `@PreAuthorize` trên **Spring-managed service bean** với `@EnableMethodSecurity`. Gọi trực tiếp `new DocumentApplicationService(...)` không kiểm được AOP interceptor; gọi `this.update(...)` từ trong cùng bean có thể bypass method security.

### 15.6. Kiểm thử no-side-effect và stale state

Với PATCH/DELETE, chỉ assert 403 là chưa đủ. Kiểm:
- Dữ liệu gốc không đổi (`title`, `ownerId`, `tenantId`, `status`, `version`).
- Không có event “DocumentUpdated” hoặc notification sai.
- Không tạo audit event giả là thao tác đã thành công.
- Không xuất bản thông tin document khác tenant trong response/log.
- Các trường `role`/`permissions` trong user record không đổi.
- Nếu cạnh tranh ownership/membership giữa check và write, guarded update trả 0 rows và transaction không ghi trái phép.

### 15.7. Kiểm thử authorization với token thật

`@WithMockUser` giúp test policy nhưng **không** kiểm JWT signature/issuer/audience/converter. Thêm integration tests dùng security config thực:
- Token hợp lệ của Alice.
- Token hợp lệ của Bob/Mallory.
- Token bị sửa payload/claim.
- Token từ issuer/audience không tin.
- Token hết hạn hoặc bị thu hồi theo hệ thống.
- Token có role tenant A nhưng gọi tenant B.
- Token cũ sau khi membership bị gỡ.

Đừng lưu token sản xuất trong test fixtures hoặc logs.

## 16. Java 17 độc lập: minh họa chống owner/tenant/role forgery

Chương trình bên dưới **không cần Spring**, dùng Java 17 để thấy rõ nguyên tắc. Nó mô phỏng server-side documents, actor có membership và authority đã được xác minh, request body là map **không đáng tin**. Chỉ đọc field `title` từ body; owner/tenant được lấy từ bản ghi server. Chính sách kiểm functional permission, membership, object tenant và owner/edit:any.

Đây là **mô hình học tập**, không phải Spring `SecurityContextHolder`, JWT verifier, persistence layer hoặc policy production. Nó không có transaction/concurrency/CSRF; các ràng buộc đó phải thêm ở code ứng dụng thật.

Tạo file `OwnerTenantForgeryDemo.java`:

```java
import java.util.HashMap;
import java.util.Map;
import java.util.Set;

public class OwnerTenantForgeryDemo {

    record Actor(
            String userId,
            Set<String> tenantMemberships,
            Set<String> authorities) {
    }

    static final class Document {
        final String id;
        final String tenantId;
        final String ownerId;
        String title;

        Document(String id, String tenantId, String ownerId, String title) {
            this.id = id;
            this.tenantId = tenantId;
            this.ownerId = ownerId;
            this.title = title;
        }
    }

    static String update(
            Map<String, Document> serverData,
            Actor actor,
            String selectedTenant,
            String documentId,
            Map<String, Object> untrustedBody) {

        if (actor == null
                || !actor.authorities().contains("document:edit")) {
            return "DENY_PERMISSION";
        }
        if (!actor.tenantMemberships().contains(selectedTenant)) {
            return "DENY_TENANT";
        }

        Document target = serverData.get(documentId);
        if (target == null || !target.tenantId.equals(selectedTenant)) {
            return "NOT_FOUND";
        }

        boolean isOwner = target.ownerId.equals(actor.userId());
        boolean mayEditAny =
                actor.authorities().contains("document:edit:any");

        if (!isOwner && !mayEditAny) {
            return "DENY_OWNER";
        }

        Object requestedTitle = untrustedBody.get("title");
        if (!(requestedTitle instanceof String title)
                || title.isBlank()) {
            return "BAD_TITLE";
        }

        // Chỉ trường title được cập nhật trong use case này.
        // ownerId, tenantId, isAdmin, roles từ body bị bỏ qua.
        target.title = title;
        return "UPDATED";
    }

    public static void main(String[] args) {
        Map<String, Document> db = new HashMap<>();
        db.put("d1", new Document(
                "d1", "org-a", "alice", "Original Alice"));
        db.put("d2", new Document(
                "d2", "org-a", "bob", "Original Bob"));
        db.put("d3", new Document(
                "d3", "org-b", "mallory", "Original Mallory"));

        Actor alice = new Actor(
                "alice",
                Set.of("org-a"),
                Set.of("document:edit"));

        Actor bob = new Actor(
                "bob",
                Set.of("org-a"),
                Set.of("document:edit"));

        Actor viewer = new Actor(
                "alice",
                Set.of("org-a"),
                Set.of("document:read"));

        Actor manager = new Actor(
                "manager",
                Set.of("org-a"),
                Set.of("document:edit", "document:edit:any"));

        Actor mallory = new Actor(
                "mallory",
                Set.of("org-b"),
                Set.of("document:edit"));

        Map<String, Object> forged = Map.of(
                "title", "Renamed by Alice",
                "ownerId", "bob",
                "tenantId", "org-b",
                "roles", Set.of("ROLE_ADMIN"),
                "isAdmin", true);

        System.out.println("alice-owned="
                + update(db, alice, "org-a", "d1", forged));
        System.out.println("owner-after-forgery="
                + db.get("d1").ownerId);
        System.out.println("tenant-after-forgery="
                + db.get("d1").tenantId);
        System.out.println("title-after-forgery="
                + db.get("d1").title);

        System.out.println("alice-edits-bob="
                + update(db, alice, "org-a", "d2",
                        Map.of("title", "Overwritten",
                                "ownerId", "alice")));

        System.out.println("alice-cross-tenant="
                + update(db, alice, "org-b", "d3",
                        Map.of("title", "Overwritten")));

        System.out.println("alice-id-cross-scope="
                + update(db, alice, "org-a", "d3",
                        Map.of("title", "Overwritten")));

        System.out.println("viewer-edits="
                + update(db, viewer, "org-a", "d1",
                        Map.of("title", "Not allowed")));

        System.out.println("bob-edits-own="
                + update(db, bob, "org-a", "d2",
                        Map.of("title", "Bob revision")));

        System.out.println("manager-edits-bob="
                + update(db, manager, "org-a", "d2",
                        Map.of("title", "Manager revision")));

        System.out.println("foreign-tenant-view="
                + update(db, mallory, "org-b", "d2",
                        Map.of("title", "Cross-scope")));

        System.out.println("bob-final-title="
                + db.get("d2").title);
    }
}
```

Biên dịch/chạy với **JDK 17 trở lên**:

```bash
javac OwnerTenantForgeryDemo.java
java OwnerTenantForgeryDemo
```

Stdout dự kiến:

```text
alice-owned=UPDATED
owner-after-forgery=alice
tenant-after-forgery=org-a
title-after-forgery=Renamed by Alice
alice-edits-bob=DENY_OWNER
alice-cross-tenant=DENY_TENANT
alice-id-cross-scope=NOT_FOUND
viewer-edits=DENY_PERMISSION
bob-edits-own=UPDATED
manager-edits-bob=UPDATED
foreign-tenant-view=NOT_FOUND
bob-final-title=Manager revision
```

### 16.1. Diễn giải

1. Body `forged` chứa `ownerId=bob`, `tenantId=org-b`, `ROLE_ADMIN`, `isAdmin=true`. Tuy nhiên, **server chỉ lấy title** để sửa; owner/tenant của d1 vẫn là Alice/org-a.
2. Alice chỉnh d2 của Bob nhưng tự khai `ownerId=alice` trong request vẫn bị `DENY_OWNER` vì policy so với **d2.ownerId lưu ở DB**.
3. Alice gọi tenant org-b bị `DENY_TENANT` do không phải thành viên.
4. Alice chọn org-a nhưng nhắm d3 thuộc org-b được `NOT_FOUND` theo scope, không làm lộ tài liệu.
5. Viewer không có `document:edit` nên bị `DENY_PERMISSION` dù giả định thuộc tenant.
6. Bob sửa chính d2 được phép; manager có `document:edit:any` **đã được server cấp** và membership org-a cũng có thể sửa d2.
7. Mallory không thể sửa d2 qua tenant org-b vì d2 thực thuộc org-a.
8. Dữ liệu cuối cùng cho d2 là “Manager revision”; không có lần cập nhật trái phép nào trong demo.

### 16.2. Giới hạn cần nhớ

- `Actor` ở demo là dữ liệu tin cậy do chương trình thiết lập; trong Spring phải lấy từ `Authentication`/policy service đã xác minh.
- `document:edit:any` trong demo chỉ có giá trị khi membership tenant khớp. Production cần scope và grant ở DB.
- Map body là dữ liệu tùy ý để minh họa mass assignment; controller thật nên dùng **DTO allowlist** thay vì `Map<String,Object>` tự do.
- HashMap demo không có lock, concurrency, durable data, business workflow, CSRF hoặc audit.
- Các chuỗi `DENY_OWNER`/`NOT_FOUND` là nhãn học tập, không tự tương ứng với HTTP status framework.
- Code demo không xác thực token hay áp dụng Spring `@PreAuthorize`; cần test Spring thật ở các phần trước.

## 17. Những lỗi phổ biến khi triển khai

| Lỗi | Vì sao nguy hiểm | Cách sửa |
| --- | --- | --- |
| `@PreAuthorize("#request.ownerId == authentication.name")` | request.ownerId có thể giả mạo | Tra current owner từ DB bằng documentId |
| `findById(id)` rồi check role USER | BOLA: cùng role vẫn có thể khác owner/tenant | Query theo tenant + ACL/owner |
| `BeanUtils.copyProperties(request, entity)` | Có thể copy field quyền, owner, tenant | DTO hẹp + explicit mapping |
| `@RequestBody UserEntity user` | Client có thể bind sensitive fields vào entity | Dùng Create/Update DTO riêng |
| `@Valid` trên entity được xem là đủ | Validation không phải authorization | Kiểm object/attribute/tenant scope |
| `ownerId`/`tenantId` từ body được tin | Client quyết định metadata bảo mật | Server tạo/duy trì các field đó |
| `X-Tenant-Id` được dùng không check membership | Dễ cross-tenant request | Xác minh active membership ở backend |
| `X-User-Id` từ browser được coi là principal | Header giả mạo danh tính | Dùng verified SecurityContext |
| JWT có `sub` là đủ để vào mọi document | Token identity không chứng minh object rights | Domain policy cho từng target |
| Global `ROLE_ADMIN` áp vào mọi tenant | Đặc quyền tràn sang tenant khác | Scope roles/grants theo tenant |
| Resource UUID khó đoán được coi là quyền | IDOR vẫn có thể bị khai thác khi ID lộ | Kiểm object-level authorization |
| `@PostAuthorize` trên method ghi/xóa | Check sau side effect | Pre-check + guarded/transaction write |
| Chỉ check trước transaction | TOCTOU khi owner/ACL thay đổi | Re-check, lock/version/conditional update |
| 403 nhưng DB vẫn bị sửa | Side effect xảy ra trước deny | Chặn trước mutation và assert no side effect |
| `@PreAuthorize` không chạy trong test | Chưa bật method security hoặc self-invocation | @EnableMethodSecurity + proxied bean |
| Service trả entity nguyên vẹn | Lộ security metadata/properties | Response DTO allowlist |
| User profile PATCH cho sửa roles | Privilege escalation | Admin grant use case riêng |
| Kiểm tenant ID trên URL == JSON | Hai giá trị cùng do client kiểm soát | So với membership + DB target tenant |
| Test chỉ dùng @WithMockUser ADMIN | Che lỗi dành cho user thường | Test Alice/Bob/Mallory/Viewer/tenant khác |
| Tenant filter dùng ThreadLocal không cleanup | Có thể rò tenant giữa pooled requests | Context lifecycle và scoped DB queries |
| Client-set isAdmin được cho vào JWT converter | Tự nâng authority | Converter chỉ nhận claims issuer đã kiểm |
| Gỡ role khỏi DB nhưng token cũ còn quyền | Stale claims | TTL, revocation, current policy checks |

### 17.1. Quy trình chẩn đoán khi xuất hiện 403/404 lạ

1. Xác định principal thật từ `Authentication` đã được xác minh (không log raw token).
2. Xác định functional authority, role prefix/claim converter.
3. Xác định target document ID từ request **chỉ như selector**.
4. Đọc current document tenant/owner/status từ database trong scope đúng.
5. Đọc active tenant membership và ACL/grants của actor.
6. Xác định `@PreAuthorize` có thực chạy qua proxy và đang gọi policy bean nào.
7. Xác định service có re-check/guarded write không.
8. Xác định 403 do method/HTTP/CSRF hay 404 do scoped lookup; không đoán từ status.
9. Test toàn bộ no-side-effects và response không tiết lộ dữ liệu ngoài quyền.
10. Nếu có cache/JWT/replica, xác minh dữ liệu quyền không bị stale.

**Không chữa lỗi bằng cách mở `permitAll()`, tắt CSRF hoặc cấp global ADMIN cho người dùng.**

## 18. Checklist triển khai, câu hỏi tự kiểm tra và kết luận

### 18.1. Checklist trước khi deploy

**Input và identity**
- [ ] Controller chỉ dùng DTO tạo/sửa có các trường user được phép thay đổi.
- [ ] Không bind trực tiếp request vào JPA entities chứa owner/tenant/role.
- [ ] Unknown fields được reject hoặc ignore có chủ đích; test quyết định đó.
- [ ] Authentication được Spring Security verify; actor ID mapping rõ và ổn định.
- [ ] Không tin `X-User-Id`, `X-Role`, `ownerId`, `isAdmin` từ public clients.
- [ ] JWT issuer/audience/signature/expiry/scope được kiểm theo version.

**Authorization**
- [ ] `@EnableMethodSecurity` đang hoạt động với `@PreAuthorize`.
- [ ] `hasAuthority`/`hasRole` chỉ là functional entry gate, không thay object policy.
- [ ] `@documentAccess` dùng current DB owner/tenant/membership/ACL.
- [ ] Path tenant selector được verify membership/target resource.
- [ ] Method được gọi qua Spring-managed proxy; có negative tests cho self-invocation.
- [ ] Không xem admin tenant A là admin tenant B.
- [ ] Permission chuyển owner, đổi tenant, cấp role là use case và grant riêng.
- [ ] Tất cả service call paths (HTTP, queue, cron, batch, GraphQL) có policy phù hợp.

**Persistence**
- [ ] Create đặt ownerId/tenantId/status ở server.
- [ ] Update chỉ map editable fields bằng allowlist.
- [ ] Scoped query có tenant + object-level checks.
- [ ] Có re-check/guarded update/optimistic locking khi ownership thay đổi đồng thời.
- [ ] Mọi DENY không gây side effect, kể cả queue events/audit business success.
- [ ] Response DTO không lộ field nội bộ ngoài quyền.

**Tests và vận hành**
- [ ] Test Alice own, Alice→Bob, Alice→tenant B, Viewer, scoped editor.
- [ ] Test thêm ownerId, tenantId, roles, isAdmin vào request.
- [ ] Test token hợp lệ nhưng ID thuộc người khác.
- [ ] Test role revoke, membership revoke, stale token.
- [ ] Test 400/403/404 theo contract và no-side-effects.
- [ ] Test concurrency khi quyền owner/tenant có thể thay đổi.
- [ ] Audit actor, target, action, tenant và outcome mà không log token/PII quá mức.
- [ ] Policy được code review và regression test trước khi triển khai.

### 18.2. Câu hỏi tự kiểm tra

**Câu 1.** Alice được xác thực thành công và có `document:edit`. Có được sửa mọi document không?

**Đáp án:** Không. Còn phải kiểm document thuộc tenant được phép, owner/ACL và trạng thái nghiệp vụ.

**Câu 2.** Body ghi `"ownerId":"alice"`, trùng `authentication.name`. Có chứng minh Alice là owner không?

**Đáp án:** Không. Client tự ghi ownerId. Phải lấy owner của target document từ DB hoặc nguồn server tin cậy.

**Câu 3.** Path `/tenants/org-b/...` có chứng minh user thuộc org-b không?

**Đáp án:** Không. Path chỉ chọn target scope. Kiểm active membership và resource tenant phía server.

**Câu 4.** Dùng UUID không đoán được thay cho ID số có đủ chống BOLA?

**Đáp án:** Không. ID có thể bị lộ qua log, URL, email, thông báo hay client; mỗi thao tác trên object cần authorization.

**Câu 5.** Vì sao dùng `UpdateDocumentRequest(title, body)` tốt hơn bind `DocumentEntity`?

**Đáp án:** DTO chỉ phơi ra các field cần sửa; không cho bind ownerId, tenantId, role, audit fields hoặc metadata nhạy cảm một cách vô ý.

**Câu 6.** `@Valid` có chặn việc user tự đặt role ADMIN trong entity không?

**Đáp án:** Không. Bean Validation chủ yếu kiểm cấu trúc/giá trị hợp lệ, không biết caller được sửa field nào. Cần DTO allowlist và authorization.

**Câu 7.** Có nên dùng `@PostAuthorize` làm kiểm quyền duy nhất sau khi delete dữ liệu?

**Đáp án:** Không. Method body có thể đã xóa trước khi check. Dùng pre-authorization và kiểm ở transaction/DB trước mutation.

**Câu 8.** Tại sao `@PreAuthorize` đã pass vẫn nên re-check trước write?

**Đáp án:** Owner/tenant/ACL/status có thể đổi giữa lúc kiểm và lúc ghi; cần tránh TOCTOU bằng scoped lookup, locking/version/guarded update tùy yêu cầu.

**Câu 9.** Một token JWT hợp lệ chứa role org-a có cho phép edit dữ liệu org-b không?

**Đáp án:** Không. Phải kiểm scope/membership và quyền theo resource/tenant, không biến role từ một tenant thành quyền toàn cục.

**Câu 10.** Lấy `authentication.name` luôn có phải UUID user trong DB?

**Đáp án:** Không. Nó tùy provider/converter và có thể là username/email/JWT subject. Cần mapping đáng tin tới stable internal actor ID.

**Câu 11.** Nếu API dùng unknown fields ignore, payload có `isAdmin=true` sẽ luôn an toàn?

**Đáp án:** Chỉ an toàn nếu DTO/mapper **thực sự không bao giờ dùng** field đó và test chứng minh DB/permissions không đổi. Có thể chọn reject unknown fields để contract chặt hơn.

**Câu 12.** User đổi tenantId trong JSON nhưng không đổi path. Backend chỉ check hai chuỗi path/body có khớp. Đủ chưa?

**Đáp án:** Chưa. Cả path và body đều client-controlled. Phải so với active membership và tenant thực của record.

**Câu 13.** Manager có quyền edit:any ở org-a nhưng muốn sửa d3 thuộc org-b. Có được không?

**Đáp án:** Không nếu grant chỉ có scope org-a; phải có quyền cross-tenant explicit và business approval phù hợp.

**Câu 14.** Chỉ test response status 403 có chứng minh dữ liệu không bị thay đổi?

**Đáp án:** Không. Cần assert DB, event queue và side effects không đổi; đôi khi code ghi rồi mới throw access denied.

**Câu 15.** Dùng custom `@documentAccess.canEdit(authentication,#tenantId,#documentId)` có đủ khi gọi service qua `this.update` không?

**Đáp án:** Không trong Spring AOP proxy bình thường; self-invocation có thể bỏ interceptor. Phải tổ chức service boundary/test proxy và giữ invariant trong service/DB.

**Câu 16.** Có thể gửi `X-User-Id` từ browser để chọn identity không?

**Đáp án:** Không. Chỉ một trusted gateway có boundary bảo đảm xác thực, overwrite header và chống bypass mới có thể cung cấp identity theo hợp đồng riêng; public client không được tự khai identity.

**Câu 17.** Khi business cho phép chuyển owner, có nên mở lại field `ownerId` trong PATCH title không?

**Đáp án:** Không. Dùng transfer-owner use case riêng với permission, target validation, workflow, transaction và audit.

**Câu 18.** Hệ thống có RoleHierarchy ADMIN > USER; phải kiểm owner/tenant nữa không?

**Đáp án:** Có. Hierarchy chỉ suy quyền chức năng nếu được cấu hình, không biết một bản ghi thuộc ai hoặc tenant nào.

### 18.3. Tóm tắt

Một API an toàn không tin `ownerId`, `tenantId` hoặc bất cứ trường quyền nào chỉ vì nó nằm trong request hoặc trùng một chuỗi quen thuộc. **Identity đến từ authentication đã kiểm chứng; ownership, tenant và ACL đến từ dữ liệu server; request chỉ mang selector và các trường được phép thay đổi.**

Dùng `@PreAuthorize` làm cổng **trước phương thức**, kết hợp `hasAuthority` với bean policy kiểm tra object. Để tránh BOLA, privilege escalation và race, đặt invariant vào service/transaction/database, sử dụng DTO hẹp và guarded updates khi cần. Test phải chứng minh **không đọc, không sửa và không nâng quyền** khi client giả mạo bất kỳ ID hoặc thuộc tính nhạy cảm nào.

## Nguồn tham khảo

- Spring Security — Method Security, `@PreAuthorize`, custom bean SpEL, method parameters và `@PostAuthorize` write caveat: https://docs.spring.io/spring-security/reference/servlet/authorization/method-security.html
- Spring Security — HTTP request authorization, `hasRole`/`hasAuthority`/`denyAll`: https://docs.spring.io/spring-security/reference/servlet/authorization/authorize-http-requests.html
- Spring Security — Authentication architecture và `SecurityContextHolder`: https://docs.spring.io/spring-security/reference/servlet/authentication/architecture.html
- Spring Security — OAuth2 Resource Server JWT: https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html
- Spring Framework — `@ModelAttribute` binding và `allowedFields`: https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/modelattrib-method-args.html
- OWASP API Security Top 10 — API1:2023 Broken Object Level Authorization: https://api-security.owasp.org/editions/2023/en/0xa1-broken-object-level-authorization/
- OWASP API Security Top 10 — API3:2023 Broken Object Property Level Authorization: https://api-security.owasp.org/editions/2023/en/0xa3-broken-object-property-level-authorization/
- OWASP Cheat Sheet Series — Mass Assignment: https://cheatsheetseries.owasp.org/cheatsheets/Mass_Assignment_Cheat_Sheet.html
- OWASP Cheat Sheet Series — Authorization: https://cheatsheetseries.owasp.org/cheatsheets/Authorization_Cheat_Sheet.html
- OWASP Cheat Sheet Series — IDOR Prevention: https://cheatsheetseries.owasp.org/cheatsheets/Insecure_Direct_Object_Reference_Prevention_Cheat_Sheet.html
