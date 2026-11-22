# Người dùng có nhiều tenant và chuyển ngữ cảnh làm việc

## 1. Bài toán: một danh tính, nhiều không gian làm việc

Một ứng dụng SaaS có thể cho một người dùng tham gia nhiều tổ chức hoặc không gian làm việc (*tenant*). Ví dụ Alice có tài khoản duy nhất nhưng giữ những quyền khác nhau:

| Người dùng | Tenant | Vai trò trong tenant | Quyền điển hình |
| --- | --- | --- | --- |
| Alice | `tenant-a` | EDITOR | Xem, tạo và sửa tài liệu của A |
| Alice | `tenant-b` | VIEWER | Chỉ xem tài liệu được phép trong B |
| Bob | `tenant-b` | ADMIN | Quản lý thành viên và dữ liệu B |
| Alice | `tenant-c` | Không là thành viên | Không được truy cập C |

Khi Alice chọn "Workspace B", đây **không phải việc biến Alice thành người dùng mới**. Danh tính đã xác thực vẫn là Alice, nhưng các thao tác từ thời điểm đó phải được đánh giá **trong phạm vi tenant B** và quyền VIEWER của Alice ở B, không dùng quyền EDITOR của Alice ở A.

Một request mẫu:

```http
GET /api/tenants/tenant-b/documents/42
Authorization: Bearer <access-token-cua-alice>
```

Máy chủ phải trả lời độc lập ba câu hỏi:

1. **Ai gọi?** Token/session hợp lệ chứng minh caller là Alice.
2. **Tenant được yêu cầu là gì, Alice có được sử dụng nó không?** `tenant-b` chỉ là selector của request; server phải xác minh Alice còn là member hợp lệ ở B.
3. **Trong B, Alice có quyền READ trên Document 42 không?** Kiểm tra tenant-scoped role/permission, resource ownership, ACL và trạng thái dữ liệu thật.

**Điểm cốt lõi:** một tenant ID trong URL, header, JWT hoặc session **không tự trở thành bằng chứng phân quyền**. Nó phải được ràng buộc với subject đã xác thực và một membership/authorization policy đáng tin cậy.

### Mục tiêu học tập

Sau bài này có thể:

- Phân biệt principal, danh sách membership, tenant đang chọn và quyền trên resource.
- Thiết kế việc chọn/chuyển tenant qua route, header, server session hoặc token một cách có chủ đích.
- Không để role của tenant A "rò" sang tenant B.
- Bảo vệ truy vấn và ghi bằng tenant scope, cả khi cache/async/transaction được sử dụng.
- Hiểu khác biệt giữa **multi-issuer authentication** của Spring Security Resource Server với **active workspace** của một user.
- Xây policy/service mẫu bằng Java 17+ và Spring Security.
- Kiểm thử chuyển tenant giữa nhiều tab, thu hồi membership, concurrent requests, cache và kết nối database tái sử dụng.

## 2. Năm khái niệm cần tách rời

| Khái niệm | Ví dụ | Nguồn sự thật |
| --- | --- | --- |
| `subjectId` / principal | Alice, ID nội bộ `u-101` | Authentication/IdP đã xác minh |
| Tenant | `tenant-a`, `tenant-b` | Registry tenant của hệ thống |
| Membership | Alice thuộc A, B; không thuộc C | Database/dịch vụ membership tin cậy |
| Active/selected tenant | Request hiện muốn làm việc ở B | Selector do UI gửi, **sau đó được server xác minh** |
| Tenant-scoped permission | Alice có WRITE_DOCUMENT ở A, READ_DOCUMENT ở B | Membership/role/ACL/policy áp dụng trong tenant đã xác minh |

Nên hình dung:

```text
               Authenticated subject: alice
                          |
                          v
          Tenant memberships từ nguồn tin cậy
             /           |           \
         tenant-a     tenant-b     tenant-c
         EDITOR       VIEWER       không có
            |            |
            +------ lựa chọn ------+
                          |
                          v
             Selected tenant cho request
                          |
                          v
               Verify membership còn hiệu lực
                          |
                          v
                Tenant-scoped permissions
                          |
                          v
               Authorize action + resource
                          |
                          v
               DB query có tenant boundary
```

**Sai lầm thường thấy:** đưa `ROLE_ADMIN` vào `Authentication.getAuthorities()` vì Alice là admin ở A rồi dùng `hasRole('ADMIN')` khi Alice làm việc ở B. Role đó thiếu tenant scope và có thể làm Alice trở thành admin cả ở B.

Có thể biểu diễn quyền theo tenant bằng membership ở database, hoặc các authority có namespace và contract rõ như `TENANT_A:DOCUMENT_WRITE`. Tuy nhiên, không nên tin chuỗi quyền từ browser, và không bỏ kiểm tra scope của resource. Đa phần nghiệp vụ cần một `TenantAccessPolicy` hiểu **subject + tenant + action**, thay vì chỉ nhìn global authorities.

## 3. Threat model: chuyển tenant là một điểm phân quyền nhạy cảm

Những cuộc tấn công hoặc lỗi triển khai điển hình:

1. User sửa `/tenants/tenant-a` thành `/tenants/tenant-c` rồi server sử dụng ID mới mà không xác minh membership.
2. Header `X-Tenant-Id` được dùng thẳng làm tenant ở repository, khiến user tự giả là tenant khác.
3. Session lưu `activeTenant=tenant-b` nhưng sau khi Alice bị xóa khỏi B, server vẫn tin session cũ.
4. JWT có danh sách tenant hợp lệ ở thời điểm phát token; quyền membership bị thu hồi sau đó nhưng token chưa hết hạn.
5. Role ADMIN của A được dùng để gọi thao tác ADMIN ở B.
6. Cache lấy dữ liệu theo `documentId` mà thiếu tenant, trả bản ghi của tenant khác.
7. Một tab chuyển tenant A → B làm các request ở tab khác âm thầm chạy dưới B.
8. Tenant context đặt vào static field hoặc ThreadLocal không được clear, bị tái sử dụng ở request tiếp theo.
9. Một entity đã được load trong JPA/Hibernate session của A nhưng ứng dụng đổi tenant trên cùng persistence context rồi đọc/ghi như thể đang ở B.
10. Job, message consumer hoặc executor không khôi phục đúng tenant context và quyền của tác nhân.
11. SQL native/bulk update không có tenant predicate, dù query repository thông thường có.
12. Một service quản trị "cross-tenant" dùng DB credential quá rộng, vô tình cho request user thường chạy không có scope.

**Nhiệm vụ bảo mật:** với mọi thao tác tenant-scoped, phải có bằng chứng đã xác minh **actor được phép thực hiện action trong tenant được chọn**, đồng thời resource thật thuộc tenant tương ứng. Tính khó đoán của tenant ID, việc giấu tên tenant trong URL và lựa chọn mặc định trên frontend đều không phải authorization.

## 4. Phân biệt hai nghĩa của “multi-tenancy” trong Spring Security

Spring Security OAuth2 Resource Server có tài liệu **OAuth2 Resource Server Multi-tenancy** về việc một resource server xác minh bearer token từ **nhiều issuer/authorization server**, chẳng hạn issuer A và issuer B. Nó hỗ trợ lựa chọn `AuthenticationManager` theo issuer tin cậy qua `JwtIssuerAuthenticationManagerResolver`.

Ví dụ minh họa theo tài liệu:

```java
JwtIssuerAuthenticationManagerResolver resolver =
    JwtIssuerAuthenticationManagerResolver.fromTrustedIssuers(
        "https://idp.example.test/issuer-a",
        "https://idp.example.test/issuer-b"
    );

http.oauth2ResourceServer(oauth2 ->
    oauth2.authenticationManagerResolver(resolver));
```

Đây là **cấu hình thành phần** cho ứng dụng Spring Security Resource Server, cần imports, dependency JWT, filter chain và cấu hình authorization thật. Các URL `example.test` là địa chỉ minh họa không dùng cho hệ thống thực.

Mục tiêu của resolver: **token được cấp bởi issuer nào, ai có quyền xác minh chữ ký/claims cho token đó?** Nó **không tự trả lời** Alice có được chuyển từ workspace A sang B hay không trong một hệ thống dùng **cùng một issuer**.

Hai trường hợp khác nhau:

| Kiến trúc | Quyết định ở tầng Authentication | Quyết định ở tầng tenant authorization |
| --- | --- | --- |
| Một IdP, một user có membership nhiều tenant | Xác minh token/session của Alice | Alice có membership và quyền gì trong tenant được chọn |
| Nhiều IdP/issuer | Chọn issuer/AuthenticationManager **được tin cậy** để xác minh token | Từ identity đã xác minh, ánh xạ vào tenant và policy dữ liệu |
| Cùng tenant nhưng nhiều workspace | Identity có thể không đổi | Scope workspace/project có thể còn hẹp hơn tenant |

**Cảnh báo:** không tạo `JwtDecoder` hoặc `AuthenticationManager` cho **issuer bất kỳ do request tự khai**. Tài liệu Spring Security yêu cầu issuer phải đến từ danh sách/registry **đáng tin cậy**. Claim `iss` trước khi xác thực chữ ký chỉ là dữ liệu để chọn phương pháp xác minh trong phạm vi đã được cho phép, không phải bằng chứng chủ thể được phép truy cập một tenant.

## 5. Chọn active tenant bằng cách nào?

Không có một cơ chế phù hợp với mọi ứng dụng. Bốn hướng thường dùng:

| Cơ chế | Cách biểu diễn tenant đang chọn | Ưu điểm | Rủi ro và điều kiện |
| --- | --- | --- | --- |
| **Tenant trong URL** | `/api/tenants/{tenantId}/...` | Rõ trên mỗi request; nhiều tab có thể độc lập | Mọi endpoint phải validate membership và resource tenant |
| **Tenant trong header** | `X-Tenant-Id: tenant-b` | Không cần lặp ID trong path | Header do client đổi được; cần middleware/server policy kiểm tra |
| **Active tenant trong server session** | `session.activeTenant=tenant-b` | UI có khái niệm "chuyển workspace" tự nhiên | Nhiều tab cùng session tranh nhau; session cũ sau revoke; CSRF |
| **Tenant trong access token** | Claim `tenant_id=tenant-b` đã được issuer xác minh | Token mang scope rõ; API stateless | Phải **reissue token** khi switch; token cũ vẫn có thể hiệu lực đến expiration nếu không có revocation/version |

**Khuyến nghị thiết kế:** đối với ứng dụng nhiều tab, nhiều request đồng thời hoặc nhiều API clients, dùng **tenant selector tường minh trên mỗi request** (ví dụ path) thường giảm trạng thái ẩn. Với ứng dụng truyền thống dựa trên session, active tenant trong session vẫn có thể phù hợp nếu đã xác định hành vi nhiều tab và luôn kiểm tra membership ở server.

Nếu hai nguồn selector cùng tồn tại, ví dụ path `tenant-a` nhưng header `tenant-b`, **đừng chọn ngẫu nhiên một giá trị**. Nên reject mismatch, hoặc ghi rõ nguồn nào là canonical và loại bỏ nguồn kia. Lỗi dùng tenant ở header cho SQL nhưng dùng tenant ở URL cho policy có thể dẫn đến truy cập chéo.

### Không dùng tenant mặc định tùy tiện

User chưa chọn tenant và có hai memberships A, B. Không nên âm thầm chọn tenant đầu tiên trong một collection không có thứ tự, hoặc fallback sang `"public"`/`"default"` khi thiếu context. Hành vi hợp lý:

- Trả danh sách các tenant caller **được phép thấy**.
- Yêu cầu user chọn, hoặc chọn một "last used" chỉ sau khi **xác minh lại** membership.
- Thiếu tenant selector ở endpoint tenant-scoped → lỗi có kiểm soát, không chạy query unscoped.
- Không thuộc tenant được yêu cầu → từ chối; không cấp quyền qua fallback.

## 6. Luồng chuyển tenant an toàn

Giả sử Alice đang ở A và chọn B trên UI.

```text
1. Browser: POST /api/me/active-tenant {"tenantId":"tenant-b"}
                       |
                       v
2. Authenticate Alice từ cookie/session/JWT đã kiểm chứng
                       |
                       v
3. Validate tenant-b là tenant được phép chọn
                       |
                       v
4. Verify current membership Alice -> tenant-b = ACTIVE
                       |
                       v
5. Trả metadata/permissions/tenant context của B
   (hoặc lưu activeTenant vào session, hoặc phát token mới
    tùy kiến trúc được chọn)
                       |
                       v
6. Browser reset data state của A, gắn tenant-b cho request mới
                       |
                       v
7. MỖI request kế tiếp vẫn authorize actor + tenant-b + action + resource
```

Bước 4 không chỉ kiểm tra tenant B tồn tại. Nó phải xác minh **Alice thuộc B** và trạng thái membership/tenant còn hiệu lực. Nếu quyền của Alice ở B là VIEWER, các màn hình và API WRITE của B phải bị từ chối, cho dù A từng cấp EDITOR.

**Switch tenant không phải đăng nhập lại** nếu chỉ thay lựa chọn workspace trong cùng danh tính. Nhưng nếu tenant B yêu cầu MFA cao hơn, step-up authentication, chấp thuận điều khoản hoặc chứng chỉ riêng, cần thực hiện workflow tương ứng trước khi cấp quyền nhạy cảm. Đừng lấy việc user đã login ở A làm bằng chứng đáp ứng chính sách B.

### Hành vi khi chuyển thành công

Nên trả về một cấu trúc rõ ràng, ví dụ:

```json
{
  "tenantId": "tenant-b",
  "displayName": "Workspace B",
  "membershipStatus": "ACTIVE",
  "permissions": ["document:read"],
  "membershipVersion": 12
}
```

Đây là **response minh họa**, không phải API Spring Security có sẵn. Frontend có thể dùng permissions để bật/tắt chức năng, nhưng **server** vẫn phải quyết định và không được tin một field permissions do frontend gửi ngược lại.

Nếu không có quyền vào tenant B, có thể dùng `403 Forbidden` hoặc `404 Not Found` nếu chính sách che giấu sự tồn tại tenant. Mã 401 dành cho caller chưa được xác thực. Mỗi endpoint phải có error contract nhất quán; đừng vô tình tiết lộ danh sách tenant của khách hàng qua message lỗi chi tiết.

## 7. Role và authority phải được hiểu trong **tenant đã xác minh**

Giả sử Alice là EDITOR tại A và VIEWER tại B. Một check sau là nguy hiểm nếu authority được cấp theo toàn bộ memberships của Alice:

```java
@PreAuthorize("hasRole('EDITOR')")
public void editDocument(Long documentId) {
    // ...
}
```

Nếu `ROLE_EDITOR` được đưa vào Authentication vì Alice là EDITOR ở A, check trên **không biết** document đang ở B. Nó có thể cho phép edit trái tenant.

Có ba thiết kế thường gặp:

1. **Policy tenant-aware**: `tenantPolicy.can(authentication, tenantId, action)` tra membership trong tenant được yêu cầu.
2. **Authority namespaced có kiểm soát**: biểu diễn quyền theo tenant/permission rõ ràng; vẫn cần đối chiếu resource tenant và tránh xây chuỗi role từ dữ liệu client chưa validate.
3. **Access token tenant-bound**: server/IdP phát token mới chỉ đại diện scope của tenant đã chọn, có `aud`/`iss`/expiry phù hợp; API không chấp nhận token B để truy cập dữ liệu A.

Đối với ứng dụng dynamic memberships, policy tenant-aware tại request time giúp xử lý revoke kịp thời hơn một claim quyền bất biến trong JWT dài hạn. Dù dùng cách nào, **đừng nới role global** thành tenant admin chỉ vì user làm admin ở một nơi khác.

### Policy có hai cấp

```text
canAccess(subject, tenant, "document:read")
    AND
canReadResource(subject, tenant, documentId)
```

Cấp một: membership/role trong tenant. Cấp hai: quyền trên đối tượng cụ thể (owner, project, ACL, share grant, classification, status). VIEWER của B chưa chắc được xem mọi Document ở B nếu còn ACL ở project hay tài liệu.

## 8. Ví dụ Spring Boot: kiểm tra tenant theo từng request

Các đoạn sau là **thành phần của một ứng dụng Java 17+ với Spring Boot, Spring Security 6.x/7.x và Spring Data JPA**. Chúng không phải một file chạy độc lập bằng `javac`; entity, schema, migrations, authentication mapping và một số interface ứng dụng cần được triển khai theo dự án.

### 8.1. Model của tenant scope đã được xác minh

```java
public enum TenantAction {
    DOCUMENT_READ,
    DOCUMENT_CREATE,
    DOCUMENT_WRITE,
    MEMBER_MANAGE
}

public record VerifiedTenantScope(
    String subjectId,
    String tenantId,
    java.util.Set<TenantAction> actions
) {
    public boolean can(TenantAction action) {
        return actions != null && actions.contains(action);
    }
}
```

`VerifiedTenantScope` chỉ được tạo **ở server sau khi kiểm tra**, không deserialise trực tiếp từ request body. `subjectId` nên là ID ổn định của subject từ authenticated principal; tên hiển thị hoặc email có thể thay đổi và không luôn duy nhất giữa issuer.

### 8.2. Membership repository

```java
import java.util.Optional;
import org.springframework.data.jpa.repository.JpaRepository;

public interface TenantMembershipRepository
        extends JpaRepository<TenantMembership, Long> {

    Optional<TenantMembership>
        findByTenantIdAndSubjectIdAndActiveTrue(
            String tenantId, String subjectId);
}
```

Mẫu giả định entity `TenantMembership` có `tenantId`, `subjectId`, `active` và một tập permission hoặc role đáng tin. Trong database nên có uniqueness/constraints cho cặp tenant + subject (hoặc thêm issuer identity nếu nhiều IdP) theo domain. Nếu role được lưu qua relationship hoặc mapping riêng, repository nên lấy quyền tương ứng **đúng tenant**, không gộp quyền của mọi tenant.

### 8.3. Resolver subject từ Authentication

Đừng mặc định mọi kiểu `Authentication.getName()` đều là subject ID nội bộ. Với JWT Resource Server mặc định, name thường dựa trên `sub`; với SAML/OIDC/custom Authentication, mapping có thể khác. Định nghĩa một hợp đồng riêng:

```java
import org.springframework.security.core.Authentication;

public interface SubjectIdResolver {
    String requireSubjectId(Authentication authentication);
}
```

Implementation phải từ chối `null`, anonymous, principal chưa xác thực và identity không thuộc issuer được tin; nếu nhiều issuer, cần có namespace như `issuer + subject` để tránh hai subject khác issuer trùng string. Không cho browser khai `subjectId` rồi lấy nó làm actor.

### 8.4. TenantAccessPolicy: chọn tenant không đồng nghĩa được phép

```java
import java.util.EnumSet;
import java.util.Set;

import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.core.Authentication;
import org.springframework.stereotype.Service;

@Service("tenantAccess")
public class TenantAccessPolicy {
    private final TenantMembershipRepository memberships;
    private final SubjectIdResolver subjects;

    public TenantAccessPolicy(
            TenantMembershipRepository memberships,
            SubjectIdResolver subjects) {
        this.memberships = memberships;
        this.subjects = subjects;
    }

    public VerifiedTenantScope requireScope(
            Authentication authentication, String requestedTenant) {

        String subject = subjects.requireSubjectId(authentication);
        if (requestedTenant == null || requestedTenant.isBlank()) {
            throw new AccessDeniedException("Tenant is required");
        }

        TenantMembership member = memberships
            .findByTenantIdAndSubjectIdAndActiveTrue(
                requestedTenant, subject)
            .orElseThrow(() -> new AccessDeniedException(
                "Tenant is not available"));

        // Ví dụ: entity chỉ xuất ra những quyền của membership này.
        Set<TenantAction> actions =
            EnumSet.copyOf(member.getTenantActions());

        return new VerifiedTenantScope(
            subject, member.getTenantId(), Set.copyOf(actions));
    }

    public boolean can(
            Authentication authentication,
            String requestedTenant,
            TenantAction action) {
        try {
            return requireScope(
                authentication, requestedTenant).can(action);
        } catch (AccessDeniedException denied) {
            return false;
        }
    }
}
```

**Giới hạn và yêu cầu hoàn thiện:**

- `TenantMembership` và `getTenantActions()` là entity/method ứng dụng. Đảm bảo dữ liệu action được đọc từ nguồn server, không từ JSON.
- `EnumSet.copyOf(...)` nhận collection rỗng có thể tạo `IllegalArgumentException` khi không biết enum type. Để ví dụ hoàn chỉnh hơn, nên dùng `EnumSet.noneOf(TenantAction.class)` rồi `addAll(...)` hoặc bảo đảm membership luôn có ít nhất một action. Xem phiên bản an toàn dưới đây.
- `requireScope` từ chối tenant không hợp lệ. Không fallback sang tenant khác nếu caller không có membership.
- `can` chỉ chuyển lỗi **authorization denial** thành `false`. Không catch mọi `Exception` để nuốt lỗi database/outage thành "không có tenant"; lỗi hạ tầng phải được phân loại/giám sát.
- `SubjectIdResolver` phải xử lý anonymous và identity issuer namespace đúng, nếu không `Authentication.isAuthenticated()` riêng lẻ chưa đủ.

Phiên bản xử lý cả tập permission rỗng:

```java
EnumSet<TenantAction> allowed =
    EnumSet.noneOf(TenantAction.class);
allowed.addAll(member.getTenantActions());

return new VerifiedTenantScope(
    subject, member.getTenantId(), Set.copyOf(allowed));
```

Khi triển khai thật, dùng đoạn an toàn này để **thay** dòng khởi tạo `EnumSet.copyOf(...)` trong phương thức trên. Ví dụ trên cố ý chỉ rõ vấn đề dễ gặp khi membership tồn tại nhưng chưa có quyền nào.

### 8.5. Service truy vấn dữ liệu theo tenant

```java
import java.util.List;

import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.security.core.Authentication;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class DocumentReadService {
    private final TenantAccessPolicy tenants;
    private final DocumentRepository documents;

    public DocumentReadService(
            TenantAccessPolicy tenants,
            DocumentRepository documents) {
        this.tenants = tenants;
        this.documents = documents;
    }

    @PreAuthorize("isAuthenticated()")
    @Transactional(readOnly = true)
    public List<DocumentView> list(
            Authentication authentication, String selectedTenant) {

        VerifiedTenantScope scope =
            tenants.requireScope(authentication, selectedTenant);

        if (!scope.can(TenantAction.DOCUMENT_READ)) {
            throw new org.springframework.security.access.AccessDeniedException(
                "Document read is not permitted");
        }

        // Tenant lấy từ scope vừa xác minh, không từ một static field.
        return documents
            .findByTenantIdAndDeletedFalse(scope.tenantId())
            .stream()
            .map(d -> new DocumentView(d.getId(), d.getTitle()))
            .toList();
    }

    public record DocumentView(Long id, String title) {}
}
```

Đây là **class trong ứng dụng**, cần repository `findByTenantIdAndDeletedFalse(...)`, entity `Document` và mapping JPA thật. Service làm hai việc quan trọng: kiểm tra action **trong chính tenant đang chọn** và query với tenant ID từ `VerifiedTenantScope`.

Với dữ liệu cần ACL theo từng Document, phải thêm điều kiện owner/ACL/share grant cho từng đối tượng **trước khi trả list và trước khi tính count/pagination**. Việc là VIEWER trong B không có nghĩa được đọc tất cả document trong B nếu product vẫn có object-level permissions.

**Vì sao kiểm tra membership trong thân service?** `@PreAuthorize` theo cấu hình AOP phổ biến có thể chạy **trước** transaction advice của cùng method. Với membership phải nhất quán với transaction/query, kiểm tra tại service transaction là cách dễ kiểm soát; dù vậy `@Transactional(readOnly=true)` không tự bảo đảm snapshot/serializable hoặc thu hồi quyền tức thì dưới mọi isolation.

### 8.6. Controller dùng tenant path rõ ràng

```java
import java.util.List;
import org.springframework.security.core.Authentication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/tenants/{tenantId}/documents")
public class DocumentController {
    private final DocumentReadService service;

    public DocumentController(DocumentReadService service) {
        this.service = service;
    }

    @GetMapping
    public List<DocumentReadService.DocumentView> list(
            @PathVariable String tenantId,
            Authentication authentication) {
        return service.list(authentication, tenantId);
    }
}
```

`tenantId` trong URL chỉ là **đề nghị chọn tenant**. Service vẫn gọi `tenantAccess.requireScope(authentication, tenantId)`. Không chuyển sang `findAll()` rồi filter tenant ở controller; khi có pagination, count và lazy relationships, cách đó vừa tốn tài nguyên vừa có nguy cơ lộ dữ liệu.

### 8.7. Chú ý cấu hình @EnableMethodSecurity

```java
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;

@Configuration
@EnableMethodSecurity
public class MethodSecurityConfiguration {}
```

Nếu dùng `@PreAuthorize`, cần bật method security và gọi service qua **Spring-managed proxy**. Lời gọi `this.securedMethod()` nội bộ cùng bean trong chế độ proxy có thể bypass advice; những truy vấn scoped ở repository/domain giúp tạo lớp bảo vệ bổ sung. Không đặt logic then chốt **chỉ** trong controller nếu service còn được gọi từ async/job hoặc bean khác.

## 9. Chuyển ngữ cảnh trong phiên có trạng thái

Với ứng dụng dùng cookie + server-side `HttpSession`, UI có thể gọi:

```http
POST /api/me/active-tenant
Content-Type: application/json
Cookie: JSESSIONID=<session>

{"tenantId":"tenant-b"}
```

Controller mẫu:

```java
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpSession;

import org.springframework.http.ResponseEntity;
import org.springframework.security.core.Authentication;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class ActiveTenantController {
    private final TenantAccessPolicy tenantAccess;

    public ActiveTenantController(TenantAccessPolicy tenantAccess) {
        this.tenantAccess = tenantAccess;
    }

    public record SelectTenantRequest(String tenantId) {}

    @PostMapping("/api/me/active-tenant")
    public ResponseEntity<Void> select(
            @RequestBody SelectTenantRequest command,
            Authentication authentication,
            HttpServletRequest request) {

        if (command == null || command.tenantId() == null) {
            return ResponseEntity.badRequest().build();
        }

        VerifiedTenantScope verified =
            tenantAccess.requireScope(authentication, command.tenantId());

        HttpSession session = request.getSession(false);
        if (session == null) {
            return ResponseEntity.status(401).build();
        }

        session.setAttribute("ACTIVE_TENANT_ID", verified.tenantId());
        return ResponseEntity.noContent().build();
    }
}
```

Đây là **session-based fragment**, cần HTTP security và CSRF configuration đúng. **Không vô hiệu CSRF bảo vệ cho một POST dùng cookie chỉ để switch tenant**: kẻ tấn công có thể điều hướng trạng thái làm việc qua CSRF dù chưa đọc được dữ liệu. Cookie `SameSite`/`Secure` và CSRF token theo Spring Security vẫn cần được xem xét theo cơ chế authentication thực.

Quan trọng hơn, ở request tiếp theo:

```text
selectedTenant = session.getAttribute("ACTIVE_TENANT_ID")
verifiedScope = tenantAccess.requireScope(authentication, selectedTenant)
executeService(verifiedScope)
```

**Phải xác minh lại membership.** Session attribute là *lựa chọn*, không phải một authorization grant tồn tại mãi. Nếu Alice bị xóa khỏi B sau khi chuyển, request mới không được tiếp tục truy cập chỉ vì session vẫn chứa B.

### Nhiều tab trong cùng session

Nếu tab 1 đang ở A, tab 2 bấm chuyển sang B và ghi `session.activeTenant=B`, một request đang phát sinh từ tab 1 có thể chạy dưới B. Đây là một dạng **hidden mutable context** nguy hiểm.

Các lựa chọn:

- Ưu tiên **tenantId trong mỗi API route** để hai tab độc lập.
- Nếu dùng active tenant session-wide, UI phải thể hiện tenant hiện tại rõ và xử lý đồng bộ giữa tab; request nên mang context version/tenant ID để phát hiện stale UI.
- Có thể lưu active workspace theo tab bằng token/tab context riêng, nhưng phải có cơ chế xác minh server-side; không tin localStorage/tab ID như quyền.
- Với thao tác ghi, yêu cầu tenant scope explicit và/hoặc kiểm tra `expectedTenant` tránh update nhầm B khi người dùng tưởng đang sửa A.

Với công cụ có nghiệp vụ nhạy cảm, UX "đổi tenant" cũng là một thao tác cần thiết kế, không chỉ thay một dropdown.

## 10. API stateless: chuyển tenant bằng cách chọn lại request hoặc phát token mới

Khi frontend gọi resource server bằng bearer JWT và không dùng server session, endpoint `POST /switch-tenant` **không thể** tự làm mọi request sau đó có tenant mới nếu không có cơ chế lưu/chuyển context.

Có hai hướng rõ ràng:

### 10.1. Giữ identity token, gửi tenant mỗi request

```http
GET /api/tenants/tenant-a/documents
Authorization: Bearer <jwt-cua-alice>
```

Sau khi UI chuyển B:

```http
GET /api/tenants/tenant-b/documents
Authorization: Bearer <cung-jwt-cua-alice>
```

Resource server vẫn xác thực JWT rồi **xác minh Alice là member B trên từng request**. Đây là cách phù hợp khi token chỉ chứng minh identity/authority nền, còn membership biến động được lấy từ dữ liệu server.

### 10.2. Token gắn tenant

Authorization server có thể cấp access token mới sau khi đã xác minh Alice được chọn B:

```json
{
  "sub": "u-101",
  "tenant_id": "tenant-b",
  "scope": "document:read",
  "exp": 1799999999
}
```

JSON trên chỉ minh họa claims; trong JWT thật cần issuer, audience, chữ ký và các validation bắt buộc theo kiến trúc. **Client không được tự sửa payload claim `tenant_id`** rồi mong token còn hợp lệ. Token mới phải được phát bởi bên có quyền và resource server phải xác minh issuer, signature, `aud`, `exp`, `nbf` và tenant scope.

Nếu token cũ cho A vẫn chưa hết hạn, hệ thống phải quyết định:

- Token A có được tiếp tục dùng ở tab khác không?
- Switch tenant có revoke token A không?
- Membership bị revoke cần có hiệu lực ngay hay chấp nhận độ trễ tới token expiration?
- Resource server có tra membership/permission version mỗi request không?

Đặc biệt, **claim tenant và danh sách role trong JWT có thể cũ** sau khi membership bị thay đổi. JWT hợp lệ về chữ ký chưa chắc grant resource vẫn hợp lệ về nghiệp vụ.

### Khi nào cần audience/issuer theo tenant?

Nếu A và B có authorization server khác nhau, Spring Security có thể dùng `JwtIssuerAuthenticationManagerResolver` với trusted issuers. Nếu chỉ là hai workspace trong cùng tổ chức và cùng IdP, không cần tạo hai issuer giả. **Xác minh token** và **chọn active workspace** là hai vấn đề riêng.

## 11. Tenant-specific AuthorizationManager và @PreAuthorize

Đôi khi chính sách phức tạp hơn một đoạn `if` trong service. Có thể tập trung vào bean policy:

```java
@PreAuthorize(
    "@tenantAccess.can(authentication, #tenantId, " +
    "T(com.example.security.TenantAction).DOCUMENT_READ)"
)
public List<DocumentView> list(
        @P("tenantId") String tenantId) {
    // Đọc dữ liệu có điều kiện tenant tại repository.
}
```

Đây là **method fragment**, giả định `com.example.security.TenantAction` là package thực và `TenantAccessPolicy.can(...)` đã triển khai. Cần import `org.springframework.security.access.method.P` và bật `@EnableMethodSecurity`. Khi copy vào project khác phải thay package path cho enum.

Với kiến trúc nhiều nhóm hành động, có thể tự viết `AuthorizationManager<MethodInvocation>` hay `AuthorizationManager<RequestAuthorizationContext>` để phân giải tenant/permission. Tuy nhiên tên generic không làm mọi dữ liệu tự đáng tin: `RequestAuthorizationContext.getVariables()` lấy tenant từ matcher và `MethodInvocation.getArguments()` lấy tenant từ caller; cả hai đều chỉ là **selector** để policy verify.

### Không tự xây tên authority từ input chưa được xác minh

Một mẫu rủi ro:

```java
String required = "TENANT_" + tenantId + "_ADMIN";
return authentication.getAuthorities().stream()
    .anyMatch(a -> a.getAuthority().equals(required));
```

Nếu `tenantId` không được validate, hoặc authority được gán không có contract xác minh tenant/role, phép nối chuỗi dễ dẫn đến nhầm phạm vi. Ngay cả khi authority namespaced hợp lệ, vẫn phải xác minh resource thực thuộc tenant đó.

Phương án policy bean với membership database cho phép ứng dụng định nghĩa rõ actor, tenant, action và resource, không phụ thuộc việc code ở controller tự hiểu chính xác format authority.

## 12. Tenant isolation tại tầng truy vấn dữ liệu

**Không đủ nếu chỉ trả đúng tenant trong giao diện.** Repository, ORM và database phải bảo đảm những lệnh đọc/ghi chỉ chạm dữ liệu thuộc scope đã xác minh.

Ví dụ shared table có cột `tenant_id`:

```sql
SELECT id, title
FROM documents
WHERE tenant_id = :verified_tenant_id
  AND deleted = FALSE
ORDER BY id;
```

Đối với detail:

```sql
SELECT id, title, owner_id
FROM documents
WHERE id = :document_id
  AND tenant_id = :verified_tenant_id
  AND deleted = FALSE;
```

Đối với update:

```sql
UPDATE documents
SET title = :new_title
WHERE id = :document_id
  AND tenant_id = :verified_tenant_id
  AND owner_id = :authenticated_subject_id
  AND deleted = FALSE;
```

Các câu SQL này dùng placeholder **đã bind bằng prepared statement**, không nối trực tiếp chuỗi tenant vào SQL. Những điều kiện owner chỉ là **mẫu policy**; nếu tài liệu chia sẻ/ACL, cần điều chỉnh mà vẫn giữ tenant isolation. Khi update ảnh hưởng 0 row, không cấp quyền và không mặc định nói ID có tồn tại hay không.

**Lưu ý:** tenant predicate bảo vệ tenant boundary, nhưng *không* thay quyền cấp đối tượng trong cùng tenant. Một user VIEWER ở B không tự được đọc tài liệu private của Bob trong B.

### Filter và bulk/native query

Các cơ chế filter của ORM có thể hỗ trợ giảm code lặp, nhưng cần đánh giá đường bypass như native SQL, bulk JPQL, JDBC template, stored procedure, data export, admin report, search index và repository mới thêm. Không giả định một Hibernate filter riêng lẻ sẽ tự bảo vệ mọi thao tác.

Các truy vấn count/pagination/search cũng phải có tenant predicate **trước** việc phân trang, không phải load tất cả dữ liệu rồi filter Java. Phần thống kê có thể làm lộ số lượng tài liệu của tenant khác ngay cả khi endpoint detail đã được bảo vệ.

## 13. Database Row-Level Security và tenant setting

Ở database hỗ trợ **Row-Level Security (RLS)** như PostgreSQL, có thể có lớp bảo vệ bổ sung, bên cạnh policy Spring Security.

Ví dụ DDL **minh họa cho bảng shared-table**:

```sql
ALTER TABLE documents ENABLE ROW LEVEL SECURITY;

CREATE POLICY documents_tenant_policy
ON documents
FOR ALL
TO app_tenant_role
USING (
    tenant_id = current_setting('app.tenant_id', true)
)
WITH CHECK (
    tenant_id = current_setting('app.tenant_id', true)
);
```

Đây là SQL PostgreSQL mẫu. Cần xem thêm quyền table, schema, chính sách owner/BYPASSRLS/superuser, `FORCE ROW LEVEL SECURITY` khi cần, các table liên quan và kiểm thử deployment thực. Một role có `BYPASSRLS` hoặc superuser **không được dùng** làm role cho request tenant thông thường.

Bên trong transaction, ứng dụng có thể đặt context tenant **transaction-local** bằng cách tương đương:

```sql
SELECT set_config('app.tenant_id', :verified_tenant_id, true);
```

Đối số `true` nghĩa là setting ở phạm vi transaction. `:verified_tenant_id` là tham số đã được server xác minh, phải được bind đúng cách; đây **không phải** giá trị copy từ header chưa kiểm tra. Nếu chưa thiết lập context hoặc value là null, predicate cần mặc định không cho thấy dữ liệu.

### Vì sao không dùng SET session-wide tùy tiện?

Trong connection pool:

```text
Request Alice / tenant-a
  -> connection #5: SET tenant = A
  -> trả connection vào pool

Request Bob / tenant-b
  -> nhận lại connection #5
  -> quên reset tenant
  -> SQL có thể chạy dưới A -> cross-tenant leak
```

Transaction-local setting như `set_config(..., true)` cùng quy trình bắt đầu transaction, và việc luôn thiết lập scope ở mỗi transaction, giúp giảm nguy cơ rò context qua pooled connections. Vẫn cần test connection reuse, transaction boundaries, read-only queries, nested operations và tất cả role DB thật.

**RLS không thay Authentication:** nếu application set `app.tenant_id` dựa trên user-provided header mà không verify membership, RLS chỉ thực thi **tenant sai mà app đã chọn**. Đúng trình tự là Authenticate → Verify tenant → Set DB context → Query dưới role bị giới hạn.

## 14. Hibernate multi-tenancy và giới hạn khi chuyển tenant

Hibernate có hỗ trợ đa tenant theo mô hình phù hợp với version, như database/schema separation hoặc phân biệt tenant trong dữ liệu. Interface `CurrentTenantIdentifierResolver<T>` cung cấp:

```java
T resolveCurrentTenantIdentifier();
boolean validateExistingCurrentSessions();
```

Javadoc mô tả resolver được Hibernate dùng để xác định tenant cho session hiện tại/phiên mới theo mô hình cấu hình. `validateExistingCurrentSessions()` có thể yêu cầu kiểm tra tenant của current session đã bind có khớp resolver hay không; nó **không tự đổi tenant trên session đã tồn tại**.

Một điểm dễ sai:

```text
Mở EntityManager/Session cho tenant-a
          |
          v
Đổi tenant context trong thread sang tenant-b
          |
          v
Dùng lại EntityManager/Session đang mở
          |
          v
KHÔNG được mặc định session đã đổi sang tenant-b
```

Với Hibernate, session/first-level persistence context có vòng đời gắn với tenant tại lúc mở hoặc ràng buộc. Khi user switch active tenant, request/transaction/session **mới** phải dùng đúng scope; không giữ entity managed của A rồi đổi context sang B trong cùng persistence context.

### Không dùng static mutable currentTenant

```java
public static String activeTenant = "tenant-a"; // KHÔNG AN TOÀN
```

Một singleton/static field có thể khiến tenant của request này ghi đè tenant request khác. Nếu dùng request-scoped context hoặc ThreadLocal, phải bảo đảm dữ liệu chỉ được đặt **sau verify** và clear bằng `try/finally` khi request kết thúc; không leak qua thread pool, async hoặc request dispatch khác.

**Quan trọng:** `SecurityContextHolder` mặc định dựa trên thread-local trong nhiều ứng dụng Servlet; nó không tự là một tenant selector. Một request-level `VerifiedTenantScope` nên là **đối tượng bất biến rõ ràng** được chuyển vào service, không chỉ dựa vào trạng thái toàn cục.

## 15. ThreadLocal, @Async, queue và microservices

Ứng dụng có thể xác minh tenant đúng trong controller nhưng đánh mất context khi:

- Chạy `@Async` hoặc `CompletableFuture`.
- Gửi message vào Kafka/RabbitMQ.
- Tạo scheduled job, retry hoặc saga.
- Gọi service khác bằng HTTP/gRPC.
- Dùng Reactor/WebFlux (context propagation khác thread-local truyền thống).

Tài liệu Spring Security về concurrency cung cấp `DelegatingSecurityContextExecutor` và những wrapper tương ứng để truyền SecurityContext vào thread khác. Nhưng **truyền SecurityContext không đồng nghĩa truyền tenant business scope** nếu nó được lưu trong một ThreadLocal riêng. Cả hai cần cơ chế an toàn.

### Giải pháp với background task

Một command nội bộ có thể chứa:

```json
{
  "tenantId": "tenant-b",
  "documentId": 42,
  "requestedAction": "GENERATE_REPORT",
  "requestedBy": "u-101",
  "correlationId": "req-123"
}
```

Đây là message minh họa. Consumer **không được xem `tenantId` trong message như bằng chứng authorization** nếu nguồn message không tin cậy. Cần xác thực/ủy quyền producer hoặc broker path, và thiết kế service identity, tenant scope, hành động được phép.

Với job chạy trễ, membership của `requestedBy` có thể đã bị revoke. Nếu policy yêu cầu quyền **vẫn còn hiện tại** lúc consumer thực thi, hãy recheck; nếu job là một lệnh đã được phê duyệt và cam kết trước đó, cần authorization contract riêng, được audit và giới hạn phạm vi. Không có đáp án chung cho mọi workflow.

### Retry, idempotency và dead-letter

- Idempotency key nên có tenant scope (ví dụ `tenant + operation + key`) để không va chạm và không trộn kết quả giữa tenant.
- Dead-letter queue có thể chứa dữ liệu/IDs tenant; chỉ service/admin có scope phù hợp mới xem được.
- Metrics và tracing có thể ghi tenant ID đã verify, nhưng không nhúng token/secret hoặc thông tin cá nhân nhạy cảm.
- Quotas/rate limits cần cả per-tenant lẫn global limits để tránh *noisy neighbor*.

Nếu một background service được phép làm việc nhiều tenant, quyền ấy phải được cấp **rõ ràng cho service principal**, không mô phỏng bằng cách đặt tenant context null rồi bỏ qua filter.

## 16. Cache, HTTP response, storage và search phải tách tenant

Một người có quyền ở A và B không được nhận lại dữ liệu A khi đang yêu cầu B chỉ vì cùng một document ID hoặc query string.

### Cache key

Sai:

```text
document:42
document-list:page=1
policy:alice:READ
```

Đúng hơn với dữ liệu tenant-scoped:

```text
document:tenant-b:42
document-list:tenant-b:alice:page=1:filters-hash
policy:tenant-b:alice:42:READ:membership-version
```

Các key trên là minh họa; không bắt buộc lộ tenant ID dạng string nếu có namespace/key builder an toàn. Key còn cần permission/resource status/locale hoặc version tùy dữ liệu. **Key đúng vẫn không thay quyền**: phải authorize trước khi đọc protected cache entry, và invalidate khi membership/role/ACL thay đổi.

### HTTP và frontend cache

Khi UI chuyển từ A sang B:

- Hủy hoặc gắn nhãn những request đang chạy dưới A; không để response A đến muộn hiển thị trong màn hình B.
- Reset tenant-specific stores, query caches, selected rows, search filters, upload queues và websocket subscriptions.
- Query key frontend cần tenant, ví dụ `["documents", tenantId, page]`.
- Không dùng localStorage chứa `activeTenant` làm nguồn quyền; nó chỉ là sở thích/lựa chọn.
- Tenant-scoped responses nhạy cảm không được nằm trong shared CDN cache theo URL thiếu tenant/user scope.
- Khi tab A và tab B cùng hoạt động, tránh session-global active tenant làm API dùng tenant ẩn.

### Object storage

Đường dẫn như `tenant-a/files/invoice.pdf` không tự là chứng chỉ quyền. Trước khi phục vụ file hoặc phát presigned URL, server phải kiểm tra **exact object + tenant + action**. Nếu URL đã ký còn hạn sau khi user switch hoặc bị revoke membership, phải hiểu giới hạn của cơ chế thu hồi URL đã phát.

### Search, analytics và exports

Elasticsearch, warehouse, read replica, reports, CSV export và async indexers cần cùng tenant boundary. Một export tạo dưới quyền A không được tải bằng context B chỉ vì link ID trùng hoặc job ghi vào storage chung. Tenant isolation cần có ở cả **data plane** và **control plane**.

## 17. Chuyển tenant giữa những request đang xử lý

Giả sử tab 1 bắt đầu cập nhật tài liệu ở A, trong lúc tab 2 chuyển tenant sang B:

```text
T1: request UPDATE /tenants/A/documents/10 bắt đầu
T2: user chọn tenant B
T1: transaction vẫn đang xử lý
T2: request GET /tenants/B/documents bắt đầu
```

Nếu active tenant gắn với từng request và đã verify, T1 tiếp tục theo scope A, T2 theo B; hai request có thể đồng thời hợp lệ nếu user còn membership ở cả hai.

Nếu active tenant chỉ là một biến session chung và request T1 tra session **nhiều lần trong quá trình xử lý**, một phần của T1 có thể bất ngờ dùng B. Vì thế:

1. Resolve tenant một lần tại ranh giới request.
2. Verify membership/action.
3. Tạo `VerifiedTenantScope` bất biến cho request/transaction.
4. Dùng scope đó xuyên suốt nghiệp vụ và database.
5. Không đổi scope trong cùng transaction.
6. Nếu cần chặn request cũ sau switch, thiết kế `contextVersion`/epoch và reject rõ thay vì để context tự biến đổi.

**Không có quy tắc mặc định rằng switch phải hủy mọi request cũ.** Với nhiều tab, cho phép request A và B đồng thời có thể hoàn toàn đúng. Điều phải tránh là **một request âm thầm thay đổi tenant giữa chừng** hoặc vượt quyền membership hiện tại.

### Token cũ sau khi membership bị xóa

Nếu membership của Alice tại B bị thu hồi, một token có claim B còn sống có thể tiếp tục được xác thực về mặt cryptographic. Chính sách có thể yêu cầu:

- Check membership mỗi request; hoặc
- Token B hạn ngắn + revocation/version; hoặc
- Introspection/authorization service cập nhật; hoặc
- Từ chối token theo policy epoch mới.

Đừng chỉ xóa B khỏi dropdown của frontend; API phải từ chối B ngay khi SLA revoke yêu cầu.

## 18. Java 17 chạy độc lập: một user có quyền khác nhau ở hai tenant

Chương trình sau **không dùng Spring Security**. Nó mô phỏng tư duy **request chọn tenant → xác minh membership → kiểm tra action → kiểm tra tenant của tài nguyên → thực thi**, và cho thấy hai tab có thể gửi request với hai tenant khác nhau mà không cần một biến `activeTenant` toàn cục.

Lưu file `MultiTenantSwitchDemo.java`:

```java
import java.util.HashMap;
import java.util.Map;
import java.util.Set;

public class MultiTenantSwitchDemo {
    record Membership(
        String subject, String tenant, Set<String> actions, boolean active
    ) {}

    record Document(
        long id, String tenant, String title
    ) {}

    private static final Map<String, Membership> MEMBERS = Map.of(
        "alice|tenant-a",
            new Membership("alice", "tenant-a",
                Set.of("READ", "WRITE"), true),
        "alice|tenant-b",
            new Membership("alice", "tenant-b",
                Set.of("READ"), true),
        "alice|tenant-c",
            new Membership("alice", "tenant-c",
                Set.of("READ"), false),
        "bob|tenant-b",
            new Membership("bob", "tenant-b",
                Set.of("READ", "WRITE"), true)
    );

    private static final Map<Long, Document> DOCUMENTS = new HashMap<>(
        Map.of(
            10L, new Document(10L, "tenant-a", "A-plan"),
            20L, new Document(20L, "tenant-b", "B-budget")
        )
    );

    static Membership verify(String subject, String selectedTenant) {
        if (subject == null || selectedTenant == null) {
            return null;
        }
        Membership membership =
            MEMBERS.get(subject + "|" + selectedTenant);
        return membership != null && membership.active()
            ? membership : null;
    }

    static String read(String subject, String selectedTenant, long id) {
        Membership context = verify(subject, selectedTenant);
        if (context == null) {
            return "403 Tenant forbidden";
        }
        if (!context.actions().contains("READ")) {
            return "403 Action forbidden";
        }
        Document document = DOCUMENTS.get(id);
        if (document == null
                || !document.tenant().equals(context.tenant())) {
            return "404 Not Found";
        }
        return "200 " + document.title();
    }

    static String updateTitle(
            String subject, String selectedTenant,
            long id, String newTitle) {
        Membership context = verify(subject, selectedTenant);
        if (context == null) {
            return "403 Tenant forbidden";
        }
        if (!context.actions().contains("WRITE")) {
            return "403 Action forbidden";
        }
        Document document = DOCUMENTS.get(id);
        if (document == null
                || !document.tenant().equals(context.tenant())) {
            return "404 Not Found";
        }
        DOCUMENTS.put(
            id, new Document(id, document.tenant(), newTitle)
        );
        return "204 Updated";
    }

    public static void main(String[] args) {
        System.out.println("Alice A read 10: "
            + read("alice", "tenant-a", 10));
        System.out.println("Alice A read B20: "
            + read("alice", "tenant-a", 20));
        System.out.println("Alice B read 20: "
            + read("alice", "tenant-b", 20));
        System.out.println("Alice B write 20: "
            + updateTitle("alice", "tenant-b", 20, "Bad change"));
        System.out.println("Alice B read A10: "
            + read("alice", "tenant-b", 10));
        System.out.println("Alice C inactive: "
            + read("alice", "tenant-c", 20));
        System.out.println("Bob B write 20: "
            + updateTitle("bob", "tenant-b", 20, "B-updated"));
        System.out.println("Alice B sees updated: "
            + read("alice", "tenant-b", 20));
        System.out.println("Alice A still reads 10: "
            + read("alice", "tenant-a", 10));
    }
}
```

Biên dịch và chạy trên JDK 17 trở lên:

```bash
javac MultiTenantSwitchDemo.java
java MultiTenantSwitchDemo
```

Stdout chính xác:

```text
Alice A read 10: 200 A-plan
Alice A read B20: 404 Not Found
Alice B read 20: 200 B-budget
Alice B write 20: 403 Action forbidden
Alice B read A10: 404 Not Found
Alice C inactive: 403 Tenant forbidden
Bob B write 20: 204 Updated
Alice B sees updated: 200 B-updated
Alice A still reads 10: 200 A-plan
```

Phân tích:

- Alice có READ+WRITE ở A nhưng chỉ READ ở B; quyền A **không** chuyển sang B.
- Khi Alice chọn A, Document 20 của B không thấy; khi chọn B, Document 10 của A cũng không thấy.
- Alice không ghi được B dù có WRITE ở A.
- Tenant C có membership inactive nên bị từ chối ngay ở bước chọn/verify.
- Bob được WRITE trong B và thay đổi đúng Document 20; Alice ở B vẫn đọc được nội dung mới do có READ.
- Một request cuối dùng lại A vẫn đọc được Document 10: **không có mutable global active tenant**.

**Giới hạn mô phỏng:** `Map`/`HashMap` không cung cấp transaction, đồng thời an toàn, tenant-aware DB role hay JWT. Demo cũng không kiểm tra ACL chi tiết trong cùng tenant. Trong production phải lấy subject từ Authentication, membership từ nguồn tin cậy và áp dụng tenant scope tại truy vấn/ghi trong transaction.

## 19. Kiểm thử quyền khi user chuyển giữa nhiều tenant

### 19.1. Fixture tối thiểu

Chuẩn bị dữ liệu đối chứng có tính bất đối xứng:

- Alice có EDITOR trong A và VIEWER trong B.
- Bob có ADMIN trong B, không có membership A.
- Carol có membership C đã bị vô hiệu.
- Document 10 thuộc A, Document 20 thuộc B, Document 30 private của một user khác trong A.
- Một Document cùng giá trị external ID tồn tại ở A và B nếu thiết kế dùng khóa ghép; không để query nhầm tenant.
- Hai request song song, một session đang mở nhiều tab.
- Một cache entry từng được sinh dưới quyền admin B.
- Một membership vừa bị revoke ở DB nhưng JWT/session vẫn còn hạn.

### 19.2. Ma trận authorization

| Actor | Selected tenant | Action/resource | Kỳ vọng |
| --- | --- | --- | --- |
| Alice | A | READ Document 10 của A | Cho phép nếu object policy thỏa |
| Alice | A | WRITE Document 10 của A | Cho phép nếu owner/ACL cũng thỏa |
| Alice | B | READ Document 20 của B | Cho phép nếu object policy thỏa |
| Alice | B | WRITE Document 20 của B | **Deny**, dù Alice là EDITOR ở A |
| Alice | C | Bất kỳ | **Deny**, C không có active membership |
| Bob | A | Bất kỳ | **Deny**, Bob không thuộc A |
| Bob | B | Quản lý thành viên B | Chỉ cho phép nếu role B cấp MEMBER_MANAGE |
| Alice | A | READ Document 20 của B | **Deny** và không trả dữ liệu B |
| Alice | B | READ Document 10 của A | **Deny** và không trả dữ liệu A |
| Alice | A | READ tài liệu private của user khác trong A | Theo object ACL, không chỉ membership |
| Unauthenticated | B | Bất kỳ | 401/challenge theo cấu hình |
| System service | Cross-tenant export | Chỉ khi có service scope và approval rõ |

### 19.3. Ma trận chuyển ngữ cảnh và consistency

| Tình huống | Điều cần xác minh |
| --- | --- |
| User chọn tenant không thuộc membership | Server từ chối, không fallback |
| User chuyển A → B → A | Quyền, dữ liệu và UI khôi phục đúng từng tenant |
| Hai tab chọn A và B đồng thời | Không trộn tenant khi dùng route explicit; nếu session-wide, behavior được định nghĩa |
| Membership B bị revoke sau switch | Request mới vào B bị từ chối theo SLA |
| Session vẫn lưu B sau revoke | Session không tự chứng minh quyền |
| JWT claim B còn hạn sau revoke | Authorization vẫn theo policy revocation đã công bố |
| Tenant bị suspended/archived | Từ chối theo tenant status, dù membership còn active |
| Token từ issuer lạ | Không tạo AuthenticationManager cho issuer bất kỳ |
| Role ADMIN của A, VIEWER của B | Không được dùng ADMIN của A trong B |
| Switch khi request UPDATE ở A đang chạy | Request không đổi tenant giữa transaction |
| Retry async job sau revoke | Recheck hoặc áp approved job policy rõ |
| Cache nóng từ tenant A | Không trả A khi caller đang ở B |
| Connection pool tái sử dụng giữa A/B | RLS/DB context không leak tenant |
| EntityManager đang mở cho A | Không rebind thành B trong cùng persistence context |
| Native SQL/bulk operation | Có tenant predicate/RLS, không bypass |
| Search/export/count/pagination | Chỉ lấy và đếm dữ liệu tenant được phép |
| CSRF vào endpoint switch session | Không đổi tenant qua request giả mạo |
| Tenant selector thiếu | Reject, không dùng tenant mặc định không đáng tin |

### 19.4. Test Spring Security thực

Dùng `@SpringBootTest`, `MockMvc` hoặc HTTP integration tests, `spring-security-test`, database test có A/B, và context Authentication phù hợp với production.

Kiểm tra đủ:

1. HTTP filter chain yêu cầu authentication đúng.
2. `TenantAccessPolicy` được gọi với **tenant ID được chọn từ request** và subject ID đã verify.
3. Repository query sử dụng **VerifiedTenantScope.tenantId**, không lấy raw header.
4. Response body không có dữ liệu/metadata của tenant khác.
5. Với write, assert database/event không thay đổi khi tenant hoặc action bị deny.
6. Với query pagination, assert count và page được scope đúng.
7. Với user cùng lúc nhiều membership, assert quyền theo tenant chính xác.
8. Với revoke membership giữa các requests, assert authorization không stale ngoài SLA.
9. Với session switch, test CSRF, cookie, multiple tabs và simultaneous requests.
10. Với async, test consumer/worker nhận đúng tenant và xác minh producer authorization.

**Bẫy test:** `@WithMockUser(username="alice")` có thể không tái hiện mapping subject từ JWT `sub` hoặc issuer namespace thật. Nếu production dùng JWT/OIDC/membership lookup, xây fixtures cùng kiểu Authentication hoặc kiểm thử với resource server thực để không có giả định sai.

### 19.5. Test DB RLS và connection reuse

Nếu dùng PostgreSQL RLS:

- Chạy test bằng **DB role production-like** không có `BYPASSRLS`.
- Assert cross-tenant SELECT/UPDATE/DELETE bị chặn.
- Assert các row INSERT có `tenant_id` khác context bị chặn bởi `WITH CHECK`.
- Mỗi transaction phải set đúng verified tenant ID.
- Dùng connection pool thật để test hai request A/B liên tiếp trên **cùng physical connection**.
- Không chỉ test repository method chuẩn; thử JDBC template, native SQL, bulk operation và các luồng truy vấn ngoài ORM.
- Inventory tất cả table tenant-owned có RLS policy đúng; table mới không tự an toàn.
- Nếu platform admin cần cross-tenant, dùng đường riêng được authorize/audit, không dùng credential bypass làm mặc định.

## 20. Lỗi thường gặp và cách sửa

| Lỗi | Vì sao sai | Sửa thế nào |
| --- | --- | --- |
| Coi `tenantId` từ header/path là quyền | Client có thể tự sửa selector | Verify subject membership và tenant status tại server |
| Lưu tenant vào static field | Request khác ghi đè scope | Dùng per-request verified context bất biến |
| ThreadLocal tenant không clear | Thread pool phục vụ request khác với context cũ | `try/finally` clear, test reuse; ưu tiên truyền explicit scope |
| Có ROLE_ADMIN ở A, dùng toàn cục | Privilege escalation sang B | Tenant-scoped permissions theo membership |
| Switch chỉ thay dropdown UI | Server có thể vẫn xử lý tenant cũ | Gắn tenant rõ trên request và verify |
| Session active tenant dùng như grant vĩnh viễn | Membership có thể revoke | Revalidate membership, policy version/cache invalidation |
| JWT tenant claim được coi không bao giờ stale | Token còn hạn sau revoke | Short TTL, version/introspection hoặc DB authorization |
| Bất cứ issuer nào cũng được tạo decoder động | Trust boundary bị điều khiển bởi client | Trusted issuer allowlist/registry |
| Query `findById` không tenant | IDOR/cross-tenant leakage | Tenant-scoped query và DB enforcement |
| Chỉ check tenant mà bỏ object owner/ACL | User cùng tenant có thể đọc tài liệu private | Kiểm tra cả resource permission |
| Hibernate Session A được giữ sau switch B | Persistence context vẫn gắn tenant cũ | New request/session/transaction đúng tenant |
| Session-local DB SET trên pooled connection | Tenant A có thể leak sang B | Transaction-local setting, reset và reuse tests |
| Dùng DB role `BYPASSRLS` cho request thông thường | RLS không bảo vệ | Dùng role least privilege không bypass |
| Cache key không có tenant | Dữ liệu A trả ở B | Key theo tenant và quyền; authorize trước cache hit |
| Frontend giữ response cũ khi chuyển tab | UI hiển thị tài liệu tenant cũ | Reset query cache, hủy/gắn nhãn requests |
| Async dùng tenant field từ message không xác minh | Worker bị lừa xử lý tenant khác | Authenticate producer path và reauthorize consumer |
| Dùng global idempotency key cho mọi tenant | Trùng lệnh/response giữa tenant | Key/namespace theo tenant và operation |
| Không test native SQL hoặc export | Đường bypass isolation | Kiểm thử tất cả đường data access |
| Fallback mặc định tenant khi thiếu context | Unscoped query hoặc lộ data | Fail closed, yêu cầu selector hợp lệ |
| Log raw tokens/claims hoặc dữ liệu tenant | Tiết lộ thông tin nhạy cảm | Audit subject/tenant đã verify, redact secrets |
| Chỉ test user có một tenant | Không phát hiện role bleed/switch bugs | Fixture A/B với quyền bất đối xứng và multi-tab tests |

## 21. Checklist review thiết kế chuyển workspace

Trước khi đưa chức năng nhiều tenant vào production, cần trả lời rõ:

1. **Subject được nhận diện thế nào?** Identity ổn định, có namespace issuer nếu cần.
2. **Tenant registry/membership nằm ở đâu?** Nguồn tin cậy, unique constraints, active/suspended states.
3. **Lựa chọn tenant ở đâu?** URL, header, server session hay token; chỉ một nguồn canonical.
4. **Khi thiếu tenant selector, hệ thống làm gì?** Không fallback thành tenant sai.
5. **Quyền được gắn với tenant nào?** Không dùng role global cho hành động tenant-scoped.
6. **Bảo vệ resource thế nào?** Owner/ACL cùng tenant, đúng action, không chỉ membership.
7. **Chuyển tenant có cần step-up authentication không?** Theo mức nhạy cảm tenant đích.
8. **Mỗi request có verify membership không?** Hoặc có revocation strategy đáp ứng SLA.
9. **Switch nhiều tab có rõ nghĩa không?** Tránh mutable session state gây nhầm.
10. **Transaction và EntityManager có giữ nguyên tenant scope không?** Không đổi giữa chừng.
11. **DB có tenant boundary thực không?** Query predicates, schema/database isolation hoặc RLS.
12. **Connection pool có leak context không?** Test re-use và transaction-local settings.
13. **Cache có phân vùng tenant không?** Data, authorization, session, frontend, CDN.
14. **Async và queue có context bảo mật hợp lệ không?** Service principal, producer auth, consumer recheck.
15. **Token/JWT có đúng issuer/audience/expiry không?** Không nhầm multi issuer với workspace membership.
16. **Offboarding/revoke có tác động đầy đủ không?** Token/session/cache/jobs/exports/storage.
17. **Admin cross-tenant được kiểm soát riêng không?** Least privilege, audit, approval.
18. **KPI/noisy-neighbor có giới hạn theo tenant không?** Rate limits, quotas, queues, connection pools.
19. **Tests có cả tenant A/B với roles khác nhau không?** Negative tests và concurrency.
20. **Audit có đủ truy dấu không?** Actor, verified tenant, action, resource, outcome và correlation ID.

**Kết luận:** Một người dùng có nhiều tenant không đồng nghĩa có **một tập quyền toàn cục**. Hãy giữ principal đã xác thực, membership theo tenant và tenant selector của request **tách biệt**; chỉ tạo `VerifiedTenantScope` sau khi xác minh, áp dụng quyền theo tenant ở service và ràng buộc **mọi truy vấn/ghi dữ liệu** vào scope đó. Chuyển workspace phải thay đổi **ngữ cảnh công việc được lựa chọn**, không được làm thay đổi danh tính, nâng quyền từ tenant khác hoặc để dữ liệu/caches/transactions vượt qua ranh giới tenant.

## Tài liệu tham khảo

- [Spring Security — OAuth2 Resource Server Multi-tenancy](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/multitenancy.html): nhiều issuer, `AuthenticationManagerResolver`, trusted issuers và propagation.
- [Spring Security — Method Security](https://docs.spring.io/spring-security/reference/servlet/authorization/method-security.html): `@EnableMethodSecurity`, `@PreAuthorize` và bean authorization.
- [Spring Security — Concurrency Support](https://docs.spring.io/spring-security/reference/servlet/integrations/concurrency.html): `SecurityContextHolder` và `DelegatingSecurityContextExecutor`.
- [Spring Security — OAuth2 Resource Server JWT](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html): JWT signature, issuer, expiry, principal mapping.
- [Hibernate ORM — CurrentTenantIdentifierResolver](https://docs.hibernate.org/orm/current/javadocs/org/hibernate/context/spi/CurrentTenantIdentifierResolver.html): xác định tenant cho session và `validateExistingCurrentSessions()`.
- [Hibernate ORM — User Guide: Multi-tenancy](https://docs.hibernate.org/orm/8.0/userguide/html_single/): tenant identifier, session lifetime và isolation theo Hibernate.
- [OWASP — Multi Tenant Security Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Multi_Tenant_Security_Cheat_Sheet.html): xác minh tenant từ server, data/cache/queue/storage isolation và kiểm thử connection reuse.
- [OWASP — Authorization Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Authorization_Cheat_Sheet.html): deny by default, least privilege và object-level authorization.
- [OWASP — Insecure Direct Object Reference Prevention](https://cheatsheetseries.owasp.org/cheatsheets/Insecure_Direct_Object_Reference_Prevention_Cheat_Sheet.html): yêu cầu kiểm tra quyền trên resource ID và scoped lookup.
