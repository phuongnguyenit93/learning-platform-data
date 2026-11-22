# Phối hợp @PreAuthorize với @PostAuthorize trên cùng nghiệp vụ trong Spring Security

## 1. Bài toán: được phép đọc loại dữ liệu nhưng chưa chắc được xem bản ghi cụ thể

Giả sử một dịch vụ tài liệu đa người dùng có endpoint `GET /api/documents/{id}`. Alice được cấp authority `document:read` và có quyền đọc các tài liệu thuộc mình. Bob cũng có `document:read` nhưng chỉ được đọc tài liệu của Bob. Một HTTP request của Alice dùng ID tài liệu Bob:

```http
GET /api/documents/doc-bob HTTP/1.1
Authorization: Bearer <valid-token-for-alice>
```

Ở đây phải trả lời **hai câu hỏi khác nhau**:

1. **Trước khi chạy service:** người gọi có được sử dụng *chức năng đọc tài liệu* không?
2. **Sau khi service lấy tài liệu:** bản ghi thực sự được tìm thấy có thuộc phạm vi mà người gọi được đọc không?

Trong Spring Security method security, một cách diễn đạt có chủ đích là:

```java
@PreAuthorize("hasAuthority('document:read')")
@PostAuthorize("returnObject.ownerId == authentication.name")
public DocumentView readDocument(String documentId) {
    return documentRepository.loadView(documentId);
}
```

Đây là **fragment** minh họa, cần `DocumentView` có property `ownerId`, một repository và service Spring-managed. `@PreAuthorize` kiểm tra permission **trước** khi thân method chạy. `@PostAuthorize` kiểm tra kết quả `returnObject` **sau** khi thân method đã chạy nhưng trước khi kết quả được trả ra cho caller thông qua proxy, theo cơ chế interceptor mặc định.

Mục tiêu bài học:

- Hiểu thứ tự và tác động của hai annotation khi cùng gắn một method.
- Viết biểu thức `@PreAuthorize` kiểm tra role/authority, trạng thái login, tham số đáng tin.
- Viết `@PostAuthorize` kiểm tra `returnObject`, ownership, tenant và policy dựa trên **giá trị trả về thực tế**.
- Biết tại sao hai annotation có ý nghĩa **AND** trong kết quả cuối, nhưng **không** chạy đồng thời và **không** thay thế nhau.
- Phân biệt kiểm soát dữ liệu đọc với các tác vụ ghi/xóa/phát event có side effect.
- Tránh rủi ro `null`, `Optional`, `List`, proxy/self-invocation, error response, async và thứ tự transaction.
- Xây unit/integration tests để chứng minh cả **trước method**, **sau method**, **không rò kết quả**, **không ghi trái phép**.
- Chọn cấu trúc an toàn hơn khi có quyền theo từng đối tượng hoặc tenant.

**Phạm vi:** Spring Security Servlet/Spring MVC, Java 17+, `@EnableMethodSecurity`, JUnit 5, Spring Security Test. Một số ví dụ Spring là fragment tích hợp; bài có thêm chương trình Java 17 độc lập mô phỏng thứ tự pre/body/post để tự chạy mà không cần Maven.

## 2. Hai lớp authorization trong cùng một method invocation

### 2.1. Sơ đồ thực thi

Spring Security hiện đại tạo hai method interceptors riêng, do đó một lời gọi qua Spring AOP proxy thường có diễn tiến:

```text
Caller (controller hoặc bean khác)
        │
        ▼
Spring-managed proxy
        │
        ├─ @PreAuthorize expression
        │    ├─ DENY → method body KHÔNG chạy
        │    └─ ALLOW
        │          │
        │          ▼
        │      Method body
        │          ├─ ném exception → xử lý exception,
        │          │                   không có returnObject bình thường
        │          └─ trả DocumentView
        │                  │
        │                  ▼
        └──────── @PostAuthorize expression
                     ├─ DENY → chặn return value
                     └─ ALLOW → caller nhận DocumentView
```

Tên triển khai cụ thể theo tài liệu Spring Security:

- `AuthorizationManagerBeforeMethodInterceptor` sử dụng `PreAuthorizeAuthorizationManager` cho `@PreAuthorize`.
- `AuthorizationManagerAfterMethodInterceptor` sử dụng `PostAuthorizeAuthorizationManager` cho `@PostAuthorize`.
- Cả hai thường sử dụng một `MethodSecurityExpressionHandler` xây `EvaluationContext` để đánh giá SpEL.

Đây là sơ đồ giản lược, **không** hứa thứ tự của mọi custom AOP advisor, transaction interceptor, logging filter hoặc distributed aspect. Điểm quan trọng là **pre-check có thể chặn trước body**, còn **post-check đánh giá kết quả sau body**.

### 2.2. Truth table quan trọng nhất

Gọi `P` là kết quả pre-check; `Q` là kết quả post-check đối với result đã tạo.

| P trước method | Có chạy method body? | Q sau method | Caller nhận return value? |
| --- | --- | --- | --- |
| DENY | **Không** | Không đánh giá theo luồng bình thường | Không |
| ALLOW | **Có** | DENY | Không; body đã chạy |
| ALLOW | **Có** | ALLOW | Có |
| ALLOW | Có, nhưng body ném exception | Không có kết quả trả về bình thường để kiểm | Caller nhận exception theo xử lý framework |

Việc viết hai annotation có thể được hiểu là **P AND Q** ở mức *authorization cuối cùng*, nhưng không phải `P && Q` được tính trước body. Đặc biệt, khi Q sai, **không có cơ chế tự động quay ngược thời gian** để hoàn tác mọi side effect trong body.

### 2.3. Vì sao hai annotations không ghi đè nhau?

Trong Spring Security 6.x/7.x, mỗi annotation có pointcut/interceptor riêng; khi cả `@PreAuthorize` và `@PostAuthorize` áp dụng, Spring Security xử lý lần lượt. **Cả hai điều kiện đều phải đạt** để kết quả được trả theo đường thông thường.

Ví dụ:

```java
@PreAuthorize("hasRole('AUDITOR')")
@PostAuthorize("returnObject.classification != 'SECRET'")
public ReportView readReport(String id) { /* ... */ }
```

Một AUDITOR có thể vượt qua `@PreAuthorize` nhưng vẫn bị từ chối nếu report thực được đánh dấu SECRET. Ngược lại, một user không có ROLE_AUDITOR không được chạy body dù report là PUBLIC.

**Chú ý:** hai annotation ở **cùng loại** không được lặp trên một method (`@PreAuthorize` hai lần hoặc `@PostAuthorize` hai lần). Muốn kết hợp nhiều điều kiện trước hoặc sau, sử dụng SpEL `and`/`or` trong một annotation, hoặc gọi bean policy.

## 3. Bật method security và phân biệt với security ở HTTP

### 3.1. Kích hoạt @PreAuthorize và @PostAuthorize

Trong Spring Security hiện đại, sử dụng:

```java
package com.example.security;

import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;

@Configuration
@EnableMethodSecurity
public class MethodSecurityConfiguration {
}
```

`@EnableMethodSecurity` bật hỗ trợ pre/post annotations theo mặc định. Chỉ khai báo `spring-boot-starter-security` **không tự bảo đảm** hai annotation trên service được thực thi. Ở dự án cũ dùng `@EnableGlobalMethodSecurity(prePostEnabled=true)`, xem hướng dẫn migration tương ứng với Spring Security version đang dùng.

### 3.2. HTTP authorization vẫn là lớp độc lập

Ví dụ Servlet filter chain fragment:

```java
http.authorizeHttpRequests(auth -> auth
    .requestMatchers(HttpMethod.GET, "/api/public/**").permitAll()
    .requestMatchers(HttpMethod.GET, "/api/documents/**")
        .authenticated()
    .requestMatchers("/api/admin/**").hasRole("ADMIN")
    .anyRequest().denyAll()
);
```

Một user authenticated có thể đi qua HTTP rule cho GET documents, nhưng service vẫn yêu cầu `document:read` và owner/tenant. Nếu HTTP matcher đã `denyAll()`, `@PreAuthorize("permitAll")` không mở lại URL ấy.

Ngược lại, method security bảo vệ lời gọi từ **các bean khác** hoặc background use case nếu invocation đi qua Spring proxy; nó không thay thế kiểm soát HTTP, CSRF, session/token validation, CORS hoặc rate limits.

### 3.3. Các trường hợp cần test độc lập

- HTTP chặn trước service: body và hai method expressions có thể không được gọi.
- HTTP cho qua, `@PreAuthorize` chặn: body không chạy.
- HTTP cho qua, pre allow, post deny: body chạy nhưng kết quả bị chặn.
- HTTP + pre + post allow: caller nhận kết quả.
- Bean khác gọi service qua proxy (không có HTTP): method security vẫn cần enforcement và Authentication phù hợp.

Trong một controller thông thường, `AccessDeniedException` có thể được `ExceptionTranslationFilter` chuyển thành 403 hoặc authentication entry-point response. Ngoài HTTP, caller phải tự xử lý exception theo contract của tác vụ.

## 4. @PreAuthorize: cổng trước thân method

### 4.1. Role và authority

```java
@PreAuthorize("hasRole('ADMIN')")
public AdminDashboard dashboard() { /* ... */ }

@PreAuthorize("hasAuthority('document:read')")
public DocumentView read(String id) { /* ... */ }

@PreAuthorize("hasAnyAuthority('document:read', 'document:manage')")
public DocumentView preview(String id) { /* ... */ }
```

Theo convention mặc định, `hasRole('ADMIN')` yêu cầu `ROLE_ADMIN`; `hasAuthority('document:read')` kiểm chuỗi permission chính xác. `hasAnyAuthority` là OR, không phải AND.

Với JWT, `scope=documents.read` có thể được converter mặc định thành `SCOPE_documents.read`, **không tự bằng** `document:read`. Mapping authority phải được thực hiện và kiểm thử ở nguồn xác thực, không sửa bằng cách thay mọi rule thành permitAll.

### 4.2. isAuthenticated không đồng nghĩa isFullyAuthenticated

```java
@PreAuthorize(
    "isAuthenticated() and hasAuthority('document:read')"
)
```

`isAuthenticated()` loại trừ anonymous theo `AuthenticationTrustResolver`, nhưng có thể chấp nhận authentication kiểu remember-me. Nếu nghiệp vụ yêu cầu đăng nhập đầy đủ:

```java
@PreAuthorize(
    "isFullyAuthenticated() and hasAuthority('payment:approve')"
)
```

`isFullyAuthenticated()` loại trừ anonymous và remember-me, **không** tự chứng minh MFA, xác thực lại gần đây hoặc mức assurance cụ thể. Các yêu cầu đó cần policy bổ sung dựa trên nguồn identity tin cậy.

### 4.3. Tham số method là selector, không là bằng chứng quyền

```java
@PreAuthorize(
    "hasAuthority('document:read') and " +
    "@readPolicy.mayRequest(authentication, #documentId)"
)
public DocumentView read(String documentId) { /* ... */ }
```

`#documentId` đến từ caller và có thể bị thay. `@readPolicy` phải kiểm membership/tenant/ownership trong DB hoặc nguồn tin cậy; không chấp nhận một `ownerId` do client tự khai. Với tên tham số Java, bật compiler `-parameters` hoặc dùng `@P` nếu cần.

### 4.4. Pre-check có thể đọc DB nhưng vẫn không biết result cuối

`@PreAuthorize` nhìn thấy invocation và arguments, không có `returnObject` vì method chưa thực thi. Nếu object-level policy cần chủ sở hữu thực từ DB, có thể gọi service/repository trong pre-check. Nhưng:
- Phép kiểm có thể tăng số query.
- Resource có thể thay đổi giữa pre-check và body (TOCTOU).
- Nếu không có transaction/locking phù hợp, một pre-check đúng không tự bảo đảm quyền ở thời điểm mutation.
- Nếu result do một hệ thống khác trả về hoặc query mapping phức tạp, post-check có thể có giá trị defense in depth — **đặc biệt cho read-only methods**.

## 5. @PostAuthorize: cổng trên kết quả thực được trả

### 5.1. returnObject là giá trị trả về bình thường

```java
@PostAuthorize("returnObject.ownerId == authentication.name")
public DocumentView findDocument(String id) { /* ... */ }
```

Biểu thức tham chiếu đối tượng đã được body tạo hoặc nạp. Spring Security có thể truy cập property `ownerId` thông qua getter JavaBean `getOwnerId()` của `DocumentView`.

Không giả định result là entity giống request. Một method trả `DocumentSummary` chỉ có `title` và `id` thì `returnObject.ownerId` có thể không tồn tại. Phải thiết kế return type/policy theo loại dữ liệu thực, tránh lỗi SpEL bất ngờ.

### 5.2. Null-safe expression

Nếu method có thể trả `null`, viết:

```java
@PostAuthorize(
    "returnObject != null and " +
    "returnObject.ownerId == authentication.name"
)
public DocumentView findOrNull(String id) { /* ... */ }
```

`and` theo SpEL giúp không truy cập ownerId nếu returnObject null. Với expression này, `null` gây deny; **đó là quyết định policy**, không phải framework tự chọn trả 404. Khi không tìm thấy, thường nên ném exception domain như `DocumentNotFoundException` hoặc trả result khác có contract rõ, rồi test exception mapping riêng.

Nếu return type là `Optional<DocumentView>`, `returnObject` là **Optional** (hoặc wrapper tương ứng) tại điểm expression; đừng mặc định nó có `ownerId` trực tiếp. Dùng policy bean hiểu đúng return type, hoặc cấu trúc method trả một view thông thường và xử lý absence trước đó.

### 5.3. Post-check không phải redaction

`@PostAuthorize` thường quyết định cho phép hoặc từ chối **toàn bộ giá trị trả về**. Nó không tự xóa field `internalNote`, `accessToken` hoặc `salary` khỏi object hợp lệ. Với dữ liệu cần che trường, tạo response DTO allowlist hoặc dùng policy đặc biệt cho từng property.

Nó cũng không tự lọc từng item của danh sách. Method trả `List<DocumentView>` mà expression kiểm `returnObject.ownerId` là sai type. Với collection, ưu tiên **query scoped theo principal/tenant**; chỉ dùng `@PostFilter` hoặc custom filtering khi có lý do và đã đánh giá hiệu năng/security.

### 5.4. Dùng bean policy cho logic hậu kiểm nhiều điều kiện

```java
@PreAuthorize("hasAuthority('document:read')")
@PostAuthorize(
    "@documentReadPolicy.canReturn(authentication, returnObject)"
)
public DocumentView find(String documentId) { /* ... */ }
```

Ví dụ `@documentReadPolicy` là một Spring bean tự viết; method `canReturn` phải kiểm null, verified actor identity, tenant, ACL và trạng thái object. Không tin `returnObject.tenantId` nếu dữ liệu ấy bị lấy từ JSON client mà chưa đi qua nguồn tin cậy.

### 5.5. Kết quả được tính rồi mới bị chặn

Khi `@PostAuthorize` deny, caller không nhận giá trị bình thường thông qua proxy. **Nhưng** method có thể đã:
- Gọi DB để đọc dữ liệu.
- Tải file/object từ storage.
- Ghi log chứa dữ liệu nhạy cảm.
- Đẩy object vào shared cache.
- Gọi API khác có side effect.
- Tăng counter, gửi metric hoặc phát sự kiện.

Vì vậy phải tránh log/emit/cache thông tin nhạy cảm trước khi xác minh có quyền, kể cả nếu HTTP cuối cùng trả 403. Kết quả chặn ở sau body **không đủ** để bảo vệ những đường quan sát bên trong hệ thống.

## 6. Thiết kế nghiệp vụ đọc: kết hợp permission và ownership

### 6.1. Dữ liệu minh họa

Một kho tài liệu có:

| ID | Tenant thực | Owner thực | Tên |
| --- | --- | --- | --- |
| `doc-a` | `org-1` | `alice` | Draft of Alice |
| `doc-b` | `org-1` | `bob` | Review of Bob |
| `doc-c` | `org-2` | `carol` | Private of Carol |

Alice và Bob có `document:read`, nhưng quyền đọc từng document còn tùy owner, membership/ACL. Đổi `doc-a` thành `doc-b` trong URL không được làm Alice đọc được tài liệu Bob. Đây là vấn đề BOLA/IDOR: role/permission chức năng không tự cấp quyền trên object tùy ý.

### 6.2. Service tối giản dùng hai annotation

Tạo `DocumentView.java` trong một dự án Spring Boot/Java 17:

```java
package com.example.demo;

public final class DocumentView {

    private final String id;
    private final String ownerId;
    private final String title;

    public DocumentView(String id, String ownerId, String title) {
        this.id = id;
        this.ownerId = ownerId;
        this.title = title;
    }

    public String getId() {
        return id;
    }

    public String getOwnerId() {
        return ownerId;
    }

    public String getTitle() {
        return title;
    }
}
```

Tạo `DocumentReadService.java`:

```java
package com.example.demo;

import java.util.Map;
import java.util.NoSuchElementException;
import java.util.concurrent.atomic.AtomicInteger;

import org.springframework.security.access.prepost.PostAuthorize;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.stereotype.Service;

@Service
public class DocumentReadService {

    private final Map<String, DocumentView> docs = Map.of(
            "doc-a", new DocumentView(
                    "doc-a", "alice", "Draft of Alice"),
            "doc-b", new DocumentView(
                    "doc-b", "bob", "Review of Bob"));

    // Chỉ để minh họa thứ tự thực thi trong bài test.
    private final AtomicInteger bodyCalls = new AtomicInteger();

    @PreAuthorize("hasAuthority('document:read')")
    @PostAuthorize(
            "returnObject != null and " +
            "returnObject.ownerId == authentication.name"
    )
    public DocumentView read(String id) {
        bodyCalls.incrementAndGet();
        DocumentView view = docs.get(id);
        if (view == null) {
            throw new NoSuchElementException("Document not found");
        }
        return view;
    }

    public int getBodyCallsForTest() {
        return bodyCalls.get();
    }
}
```

Class này **có thể biên dịch trong một project Spring Boot** có Spring Context/Spring Security và method security. Nó không phải chương trình `javac` độc lập, vì có annotations/dependencies Spring.

Ý nghĩa hai annotation:

1. `@PreAuthorize`: user phải có direct/effective authority `document:read` trước khi code trong `read` chạy.
2. `@PostAuthorize`: result có ownerId bằng `authentication.name` mới được trả qua proxy.
3. User thiếu permission: `bodyCalls` không tăng.
4. User có permission nhưng request `doc-b` khi là Alice: `bodyCalls` **đã tăng**, nhưng result bị chặn.
5. User Alice đọc `doc-a`: cả pre và post allow.
6. Không tồn tại ID: method ném `NoSuchElementException`; vì không có kết quả bình thường, nên xử lý bằng exception mapping/domain contract, không coi đó là một lần post authorization pass/deny.

**Giới hạn cố ý của demo:** `authentication.name` được dùng làm user ID để dễ hiểu. Trong production, `getName()` có thể là username, email, JWT `sub` hoặc định danh tùy converter. Nếu ownerId của DB là UUID nội bộ, phải ánh xạ principal sang user ID đáng tin; đừng so sánh hai loại ID không cùng semantics.

### 6.3. Vì sao service demo chỉ nên đọc?

Nó chỉ lấy `Map` in-memory và tăng counter để test. Đây là một lựa chọn thích hợp cho minh họa hậu kiểm. Nếu đổi `read` thành `delete`, body có thể xóa tài liệu trước khi `@PostAuthorize` biết owner của kết quả; đó là thiết kế sai cho nghiệp vụ ghi.

Trong hệ thống thật, truy vấn documents nên được **scope theo tenant/owner/ACL ngay tại repository**, rồi hậu kiểm làm lớp bổ sung nếu cần. Không dùng một query toàn bộ dữ liệu nhạy cảm rồi dựa hoàn toàn vào post-check để bảo vệ mọi đường vận hành nội bộ.

## 7. Production: policy bean phân biệt actor, tenant và object thật

### 7.1. Không tin ownerId/tenantId do client khai

Một request có thể gửi:

```http
GET /api/tenants/org-1/documents/doc-b
X-User-Id: alice
X-Tenant-Id: org-1
```

Header/path values là dữ liệu client có thể kiểm soát. Không so:

```java
@PostAuthorize(
    "returnObject.ownerId == #ownerIdFromRequest"
)
```

vì client có thể chọn cả request ownerId. **Nguồn chủ sở hữu thực** phải đến từ dữ liệu server đã được load/verify; **nguồn identity** phải đến từ authentication đã được xác minh.

### 7.2. Bean policy hậu kiểm

Mẫu kiến trúc:

```java
package com.example.documents.security;

import org.springframework.security.core.Authentication;
import org.springframework.stereotype.Component;

@Component("documentReadPolicy")
public class DocumentReadPolicy {

    private final ActorIdentityResolver identityResolver;
    private final TenantMembershipRepository memberships;

    public DocumentReadPolicy(
            ActorIdentityResolver identityResolver,
            TenantMembershipRepository memberships) {
        this.identityResolver = identityResolver;
        this.memberships = memberships;
    }

    public boolean canReturn(
            Authentication authentication,
            DocumentView view) {

        if (authentication == null || view == null) {
            return false;
        }

        String actorId =
                identityResolver.requireTrustedActorId(authentication);

        String tenantId = view.getTenantId();
        if (!memberships.isActiveMember(actorId, tenantId)) {
            return false;
        }

        boolean owns = actorId.equals(view.getOwnerId());
        boolean shared = memberships.hasDocumentReadGrant(
                actorId, tenantId, view.getId());

        return owns || shared;
    }
}
```

**Fragment kiến trúc:** class `DocumentView` ở đây phải có thêm `getTenantId()`, và project phải tự tạo `ActorIdentityResolver`/`TenantMembershipRepository` với repository logic tin cậy. Các tên method `requireTrustedActorId`, `isActiveMember`, `hasDocumentReadGrant` không phải API có sẵn của Spring Security. Nếu identity resolver gặp token/subject mapping không hợp lệ, phải fail closed.

Nếu có quyền đọc cross-tenant thật, hãy định nghĩa chính sách riêng với scope/audit, không chỉ có một `ROLE_ADMIN` toàn cục rồi bỏ qua tenant.

### 7.3. Pre-check trước truy vấn và post-check sau truy vấn

Một thiết kế:

```java
@PreAuthorize(
    "isAuthenticated() and " +
    "hasAuthority('document:read') and " +
    "@tenantPolicy.isMember(authentication, #tenantId)"
)
@PostAuthorize(
    "@documentReadPolicy.canReturn(authentication, returnObject)"
)
public DocumentView read(
        String tenantId,
        String documentId) {

    return repository.findViewByIdAndTenantId(
            documentId, tenantId).orElseThrow(
                () -> new DocumentNotFoundException(documentId));
}
```

Đây là fragment với các policy/repository/exception class do ứng dụng tự viết. Pre-check xác minh caller có permission đọc và membership tenant được yêu cầu. Repository scope theo `tenantId`, hậu kiểm xác minh **object trả về** thuộc quyền. Trong production, hãy thêm negative tests cho cả hai lớp; không chỉ test user “happy path”.

### 7.4. Nếu repository đã scope đúng, post-check vẫn hữu ích không?

Có thể hữu ích như **defense in depth**: phát hiện sai join/filter/mapper, hoặc dữ liệu được load từ nhiều nguồn. Nhưng nếu query đã có ràng buộc owner/tenant chắc chắn, thêm một post-check gọi lại DB có thể tăng độ trễ và complexity mà ít lợi ích. Quyết định dựa trên threat model và chi phí kiểm thử, không cố gắn hai annotation cho mọi method.

Nếu hậu kiểm có query mới trong DB, dữ liệu có thể đổi giữa lúc method load và policy kiểm (TOCTOU). Với thao tác đọc, cần hiểu consistency của transaction/snapshot; không coi hai lần đọc ở hai thời điểm là một kiểm tra nguyên tử.

## 8. Không dùng @PostAuthorize làm rào chắn duy nhất cho write/delete

### 8.1. Anti-pattern: xóa rồi mới kiểm owner

```java
@PreAuthorize("hasAuthority('document:delete')")
@PostAuthorize(
    "returnObject.ownerId == authentication.name"
)
public DocumentView deleteAndReturn(String id) {

    Document entity = repository.findById(id).orElseThrow();
    repository.delete(entity);
    return mapper.toView(entity);
}
```

**Anti-pattern** này nguy hiểm: `repository.delete(entity)` đã được gọi **trước** khi post-check quyết định owner. Nếu request của Alice nhắm tài liệu Bob, body có thể đã xóa dữ liệu. `@PostAuthorize` từ chối trả object nhưng không bảo đảm DB đã được khôi phục.

Không lấy việc HTTP cuối cùng trả 403 làm bằng chứng không có thay đổi. Thậm chí nếu một transaction cụ thể rollback, email/queue/external API/file deletion có thể đã xảy ra hoặc không được rollback.

### 8.2. @Transactional không phải “phép màu undo”

Spring Security docs đặc biệt cảnh báo việc đặt `@PostAuthorize` trên method ghi DB. Nếu method có `@Transactional` và `@PostAuthorize`, kết quả rollback/commit còn phụ thuộc **thứ tự AOP interceptors**, transaction boundary, exception propagation, loại transaction manager và side effects ngoài DB.

Có cấu hình mà deny sau method khiến transaction rollback, nhưng **không được dựa vào điều đó** nếu chưa có test end-to-end với đúng Spring version và persistence technology. Quan trọng hơn, message broker/HTTP call/notification không nằm trong cùng transaction DB thường **không thể** được tự rollback.

**Khuyến nghị:** kiểm object permission **trước mutation**; ràng buộc thêm ở DB transaction/conditional update. `@PostAuthorize` trên write không thay thế thiết kế đúng quyền và atomicity.

### 8.3. Tách read/check và mutate

Một thiết kế dễ audit hơn:

```java
@PreAuthorize(
    "hasAuthority('document:delete') and " +
    "@documentPolicy.canDelete(authentication, #id)"
)
@Transactional
public void delete(String id) {

    String actorId = actorResolver.requireCurrentActorId();

    Document entity = repository.findByIdWithLock(id)
            .orElseThrow(() -> new DocumentNotFoundException(id));

    // Re-check khi giữ lock/trong transaction.
    documentPolicy.requireMayDelete(actorId, entity);
    repository.delete(entity);
}
```

**Fragment kiến trúc** cần `documentPolicy`/`repository`/`actorResolver` và lock semantics do ứng dụng triển khai. `findByIdWithLock` không phải method mặc định của `JpaRepository`; cần khai báo query/locking phù hợp. Việc pre-check trên ID và re-check với entity hiện hành giảm rủi ro TOCTOU; lưu ý tính chất transaction và xử lý event sau commit.

### 8.4. Guarded update ở DB khi chính sách phù hợp

Với thao tác owner-only update, có thể dùng câu SQL có điều kiện:

```sql
UPDATE documents
SET title = :new_title,
    version = version + 1
WHERE id = :document_id
  AND tenant_id = :trusted_tenant_id
  AND owner_id = :trusted_actor_id
  AND status = 'DRAFT'
  AND version = :expected_version;
```

Giá trị `trusted_actor_id` lấy từ verified Authentication mapping, tenant từ membership đã xác minh, ID/version từ request chỉ là selectors/concurrency tokens. Kiểm số hàng cập nhật: **0** nghĩa là không khớp/không được phép/xung đột version; không retry bằng `WHERE id=:id` đơn thuần. Với quyền edit:any cần policy/câu update riêng có scope rõ.

Phương án này không phải yêu cầu bắt buộc cho mọi use case; nó minh họa cách **gắn điều kiện quyền với write** thay vì đợi kiểm result sau khi side effect xảy ra.

## 9. Cân nhắc @PostAuthorize theo loại return value

### 9.1. Một DTO được load từ DB

Đây là trường hợp tự nhiên:

```java
@PostAuthorize(
    "returnObject != null and " +
    "@documentReadPolicy.canReturn(authentication, returnObject)"
)
public DocumentView findOne(String id) { /* read only */ }
```

Policy bean hiểu fields thật của DTO. Nếu `id` không tồn tại, quyết định 404/exception theo contract API, không lạm dụng null post-deny làm response 404 tự động.

### 9.2. Optional<DocumentView>

```java
@PostAuthorize("returnObject.ownerId == authentication.name")
public Optional<DocumentView> findOptional(String id) { /* ... */ }
```

**Không nên dùng nguyên expression này.** `returnObject` là giá trị trả về thực tế ở method boundary; với return type `Optional<DocumentView>`, không được mặc định truy cập `ownerId` như thể đó là `DocumentView`.

Nếu business vẫn muốn Optional, cần một policy bean hiểu `Optional` và cho kết quả rõ với empty/present, hoặc tách method trả `DocumentView` đã resolve và xử lý không tìm thấy bên trong. Chọn phương án đọc rõ, ít rủi ro SpEL type errors.

### 9.3. List, Page, Stream, Map

Không nên lặp hậu kiểm từng row bằng cách fetch **toàn bộ tenant data** rồi mới lọc, vì:
- Lộ dữ liệu trước post-policy ở heap/logs.
- Pagination/count có thể tiết lộ số record không thuộc quyền.
- N+1 queries và memory overload.
- Return type collection không có `ownerId` đơn lẻ.
- Stream có thể lazy, dữ liệu được truy xuất sau khi method returns.

**Ưu tiên:** repository query/filter được scope theo actor/tenant/ACL, chỉ trả bản ghi được phép và thiết kế pagination/count phù hợp. `@PostFilter` có công dụng riêng nhưng **không** thay pagination-safe, DB-level object filtering cho tập dữ liệu lớn.

### 9.4. Asynchronous và reactive return types

Một method trả `CompletableFuture<DocumentView>` hoặc reactive `Mono<DocumentView>` có ngữ nghĩa return value/wrapper và thời điểm chạy khác việc trả một `DocumentView` đồng bộ. **Không** suy rằng `@PostAuthorize("returnObject.ownerId == ...")` tự kiểm tra kết quả *bên trong* future/stream theo cùng cách.

Spring Security có các cơ chế tích hợp khác nhau cho Servlet, method security và reactive; với async/reactive phải dùng API authorization phù hợp và test trên đúng version, executor/Reactor context. Nếu worker chạy trên thread khác, `SecurityContextHolder` mặc định dựa trên ThreadLocal không tự truyền qua mọi `Executor`.

### 9.5. Tránh dùng entity sống lâu làm returnObject

JPA entity có lazy associations, bidirectional graphs và fields nhạy cảm. SpEL truy cập property có thể trigger query ngoài transaction/lúc session đóng, hoặc serialize toàn bộ entity trước khi kiểm owner. **Ưu tiên immutable response DTO** với các fields cần cho policy và API, đồng thời tránh giấu các thao tác DB trong getter.

## 10. Security context và trust: so sánh đúng identity/tenant

### 10.1. authentication.name có phải owner ID?

Không phải lúc nào cũng vậy. `Authentication.getName()` phụ thuộc form login, JWT converter, OAuth2 principal và custom authentication. Nếu database lưu `ownerId` là UUID nội bộ còn authentication name là email, biểu thức:

```java
@PostAuthorize("returnObject.ownerId == authentication.name")
```

sẽ không chính xác về semantics. Thiết kế `ActorIdentityResolver` map verified issuer + subject sang stable user ID, rồi policy bean kiểm tra:

```java
@PostAuthorize(
    "@documentReadPolicy.canReturn(authentication, returnObject)"
)
```

**Tuyệt đối không** lấy userId từ `X-User-Id` hoặc body client gửi để thay authentication đã xác thực.

### 10.2. Tenant ID trong path là selector, không là chứng cứ

`GET /tenants/org-2/documents/doc-c` không có nghĩa caller thuộc org-2. Pre-check phải kiểm membership/permission cho tenant đang chọn, còn post-check phải xác nhận document thật thuộc tenant đó. Không chỉ so `#pathTenantId == #bodyTenantId` vì cả hai đều client-controlled.

### 10.3. JWT role/scope có thể stale

Một token đã ký có thể chứa scope hợp lệ tại lúc phát hành nhưng đã lỗi thời sau khi user rời tenant hoặc bị thu hồi quyền. `hasAuthority` thường kiểm authorities đã được converter đưa vào Authentication; nó không tự đọc lại DB mọi lần. Với action nhạy cảm, policy bean cần kiểm membership/ACL hiện hành và có revocation/TTL strategy phù hợp.

### 10.4. Role hierarchy làm thay đổi pre-check

Nếu có `ROLE_ADMIN > ROLE_READER` trong `RoleHierarchy` và method expression handler được cấu hình dùng graph ấy, `hasRole('READER')` có thể true với user chỉ có direct `ROLE_ADMIN`. Nhưng hierarchy chỉ bao hàm chức năng/authority được định nghĩa, **không** biết dữ liệu thuộc tenant nào. Post-check theo object vẫn cần thiết nếu người quản trị không có quyền cross-tenant không giới hạn.

### 10.5. Không dựa vào client-chosen returnObject

Post-check chỉ đáng tin khi result là dữ liệu do service/repository/server tạo hoặc xác minh, không phải một object chỉ được echo từ JSON do caller gửi. Nếu method làm:

```java
public DocumentView echo(DocumentView untrusted) {
    return untrusted;
}
```

thì `returnObject.ownerId == authentication.name` chỉ xác nhận một field client có thể tự đặt. Phải tra owner/tenant từ server-side data hoặc trusted policy service.

## 11. 403, 404, thông tin rò rỉ và trải nghiệm API

### 11.1. Khi post-check deny, caller nhận gì?

Ở cấu hình mặc định, Spring Security thường ném `AccessDeniedException` từ method interceptor. Với HTTP request qua SecurityFilterChain, exception handling có thể chuyển thành 403 hoặc authentication entry point redirect/401 tùy trạng thái user và cấu hình. Không có bảo đảm rằng method return object “được trả ra rồi browser mới giấu”; **caller bị chặn trước khi nhận return value bình thường** qua proxy.

Trong code không chạy qua HTTP, cần xử lý exception theo hợp đồng: scheduled job, queue consumer, gRPC layer hay test service có thể thấy exception Java.

### 11.2. 403 vs 404 và anti-enumeration

Nếu `doc-a` không tồn tại trả 404, còn `doc-b` thuộc Bob trả 403, Alice có thể phân biệt “ID có tồn tại hay không”. Tùy threat model, điều này có thể lộ thông tin. Có thể thiết kế **scoped repository lookup** trả 404 cho đối tượng không thuộc phạm vi caller, và kiểm thêm policy trong service.

Không trả ownerId, tenantId hay metadata của object bị từ chối trong error body. Log phù hợp có thể giữ correlation ID và reason đã phân loại, tránh ghi raw token/PII hoặc nội dung nhạy cảm.

### 11.3. Exception translation không bảo vệ side effects

Khi HTTP 403 là do `@PostAuthorize`, method body vẫn có thể đã chạy. Việc chuyển exception thành response không undo DB write, message đã gửi hoặc external API call. Kiểm tra event/audit/DB trong test, không chỉ `status().isForbidden()`.

### 11.4. Không “sửa” 403 bằng permitAll

Nếu pre-check từ chối vì thiếu permission hoặc post-check từ chối vì sai owner, giải quyết từ nguồn authority, policy object hoặc dữ liệu fixture. Không thay `@PreAuthorize` bằng `permitAll`/xóa `@PostAuthorize` để dashboard hiển thị thành công: cách đó có thể tạo BOLA trên object bất kỳ.

## 12. AOP proxy, class-level annotations và các giới hạn của cùng nghiệp vụ

### 12.1. Self-invocation có thể bỏ qua cả pre và post

```java
@Service
public class UnsafeDocumentService {

    public DocumentView outer(String id) {
        return inner(id); // this.inner(id), bypass proxy.
    }

    @PreAuthorize("hasAuthority('document:read')")
    @PostAuthorize("returnObject.ownerId == authentication.name")
    public DocumentView inner(String id) {
        return repository.loadView(id);
    }
}
```

**Anti-pattern:** `outer` gọi nội bộ `inner` trên cùng instance; trong Spring AOP proxy model thông thường, annotation trên inner có thể **không được intercept**. Cả pre và post có thể bị bypass. Giải pháp là tách inner thành Spring-managed service khác, inject proxy và gọi qua bean boundary; đồng thời thực hiện owner/tenant checks ở domain layer cần thiết.

### 12.2. Private/final/non-Spring methods

Method không được Spring AOP advice, object khởi tạo bằng `new`, private methods hoặc final/proxy-incompatible methods không tạo một boundary đáng tin cho annotations. Với Kotlin/Java hãy kiểm proxy strategy và cách framework xử lý method/interface. Nếu dùng AspectJ weaving thay vì proxy thì behavior khác; test trên cấu hình runtime thực.

### 12.3. Annotation class và method

`@PreAuthorize` trên class đặt rule chung, có thể được method-level `@PreAuthorize` ghi đè theo cơ chế annotation resolution. `@PostAuthorize` ở method là **loại annotation khác** nên có thể cùng tham gia với class-level pre-rule. Không tự hiểu method-level post-check sẽ hủy pre-check ở class.

Với annotations kế thừa từ nhiều interfaces hoặc meta-annotations, Spring Security có thể phát hiện xung đột; nên đặt rule rõ trên concrete method và test startup/invocation.

### 12.4. Nhiều advisors hoạt động độc lập

Khi `@EnableMethodSecurity` bật `@PreAuthorize`, `@PostAuthorize` cùng các advisors khác (`@Secured` hoặc JSR-250 khi được kích hoạt), chúng không tự hợp nhất thành một “quyết định duy nhất trước body”. Spring Security docs mô tả các annotation kiểm nối tiếp và có thể được hiểu là AND về kết quả cho phép. Mỗi layer có thời điểm tương ứng.

Đừng trông vào thứ tự ngẫu nhiên của custom AOP advisors để “lách” policy; nếu cần ordering chính xác, dùng config chính thức và tests.

### 12.5. Method có @PreAuthorize được gọi từ @Async

Trong Servlet stack, SecurityContextHolder mặc định dùng ThreadLocal. Nếu invocation được đưa sang raw executor không có context propagation, method pre/post có thể không thấy Authentication của request. Cần context-aware executor hoặc service identity/tác vụ ủy quyền rõ ràng.

Cũng không nên mặc định một `@PostAuthorize` thực thi ở thread nào khi dùng `CompletableFuture` hay reactive wrappers mà chưa test API cụ thể; giá trị trả về tại proxy có thể là wrapper chứ không phải payload hoàn tất.

## 13. Kiểm thử với JUnit 5 và Spring Security Test

### 13.1. Test không chỉ assert ALLOW, mà đo body invocation

Với `DocumentReadService` ở mục 6, một test context tối thiểu:

```java
@SpringBootTest
class DocumentReadSecurityTest {

    @Autowired
    DocumentReadService service;

    @Test
    @WithMockUser(username = "alice",
                  authorities = "document:read")
    void ownerCanReadHerDocument() {
        DocumentView view = service.read("doc-a");

        assertThat(view.getOwnerId()).isEqualTo("alice");
        assertThat(view.getTitle()).isEqualTo("Draft of Alice");
    }

    @Test
    @WithMockUser(username = "alice",
                  authorities = "document:read")
    void readPermissionDoesNotGrantBobsDocument() {
        int before = service.getBodyCallsForTest();

        assertThatThrownBy(() -> service.read("doc-b"))
            .isInstanceOf(AccessDeniedException.class);

        assertThat(service.getBodyCallsForTest())
            .isEqualTo(before + 1);
    }

    @Test
    @WithMockUser(username = "alice",
                  authorities = "document:write")
    void missingReadPermissionBlocksBeforeBody() {
        int before = service.getBodyCallsForTest();

        assertThatThrownBy(() -> service.read("doc-a"))
            .isInstanceOf(AccessDeniedException.class);

        assertThat(service.getBodyCallsForTest()).isEqualTo(before);
    }
}
```

Đây là **test-class fragment** cần imports JUnit, Spring Boot Test, Spring Security Test, AssertJ, `AccessDeniedException` và cấu hình `@EnableMethodSecurity`. Nếu test chạy song song trên cùng singleton, `bodyCalls` có thể tăng bởi test khác: nên chạy tuần tự/fixture riêng, hoặc spy/mock method với verification ổn định. Các assertion không phụ thuộc thứ tự test nhưng phụ thuộc không có request đồng thời khác trong khoảng đo.

**Điểm cần chứng minh:**
- Test owner được phép đọc result.
- Test sai owner: **body đã chạy**, nhưng post-check deny.
- Test thiếu authority: **body không chạy**, pre-check deny.

Nếu chỉ test status 403, bạn có thể không biết đang bị HTTP filter, pre-check, post-check hay CSRF chặn.

### 13.2. @WithMockUser tạo direct authorities

```java
@WithMockUser(roles = "USER")
```

thường cấp `ROLE_USER`, còn:

```java
@WithMockUser(authorities = "document:read")
```

cấp chính xác chuỗi permission `document:read`. Nếu test `hasAuthority('document:read')`, dùng fixture quyền trực tiếp đúng hoặc graph role hierarchy thật; không kỳ vọng `ROLE_ADMIN` tự có `document:read` khi chưa có mapping.

`@WithMockUser` không kiểm JWT signature, issuer, scope converter hoặc session persistence production. Cần integration test bằng token/session thật hoặc security test support tương ứng.

### 13.3. Anonymous và wrong-role tests

```java
@Test
@WithAnonymousUser
void anonymousCannotRead() {
    assertThatThrownBy(() -> service.read("doc-a"))
        .isInstanceOf(AccessDeniedException.class);
}
```

Mẫu này chỉ khẳng định method pre-check theo fixture anonymous; nếu có HTTP controller, guest có thể nhận 401/redirect thay vì 403. Thêm test một user có `ROLE_ADMIN` nhưng không có `document:read` để xác định policy có chủ đích cấp quyền theo permission chứ không phải tự động cấp mọi quyền cho admin.

### 13.4. Test result null và không tìm thấy

Với implementation mẫu, `read("missing")` ném `NoSuchElementException` **sau khi qua pre-check nhưng trước khi có result bình thường**. Test phân biệt:
- User thiếu permission + ID missing: thường bị pre-check deny trước khi lookup.
- User có permission + ID missing: method ném not found.
- User có permission + ID tồn tại nhưng sai owner: post-check deny.

Có sự khác biệt giữa HTTP 404/403 có thể làm lộ tồn tại object; quyết định API contract theo anti-enumeration và test riêng.

### 13.5. Test đúng Spring proxy

Đừng dùng:

```java
var service = new DocumentReadService();
service.read("doc-b");
```

rồi kết luận annotations không hoạt động. Object tạo bằng `new` không phải Spring proxied bean. Test phải inject `DocumentReadService` từ application context hoặc tạo context method-security phù hợp; bảo đảm `@EnableMethodSecurity` và Spring AOP active. Một **negative canary** giúp phát hiện nếu annotation processing bị tắt.

### 13.6. Test policy bean và multi-tenant

Với `@documentReadPolicy.canReturn(...)`:
1. Actor của org-1 đọc doc org-1 do mình sở hữu → allow.
2. Actor của org-1 đọc doc org-1 của người khác, không có share/ACL → deny.
3. Actor org-1 đọc doc org-2 → deny, dù ID hợp lệ.
4. Actor không còn membership/permission → deny.
5. Actor có document:read nhưng view null → fail closed.
6. Actor có share grant hợp lệ cho doc cụ thể → allow.
7. Token/admin scope ở tenant A không tự mở tenant B.
8. Đổi owner giữa pre-check và post-check → logic theo trạng thái đáng tin; xét consistency/race.

Unit-test policy bean bằng repository giả cho decision matrix; integration test với Spring proxy để chắc chắn annotation gọi đúng bean trên runtime.

## 14. MockMvc: bảo vệ đầu ra HTTP và không rò dữ liệu

### 14.1. Endpoint gọi service qua bean

Controller fragment:

```java
@RestController
@RequestMapping("/api/documents")
public class DocumentController {

    private final DocumentReadService service;

    public DocumentController(DocumentReadService service) {
        this.service = service;
    }

    @GetMapping("/{id}")
    public DocumentView find(@PathVariable String id) {
        return service.read(id);
    }
}
```

Đây là **fragment Spring MVC**; với SecurityFilterChain phù hợp và default exception translation, denied result không được serialize thành JSON thành công.

### 14.2. MockMvc result-denied test

```java
@Test
@WithMockUser(username = "alice",
              authorities = "document:read")
void cannotDownloadBobsDocument() throws Exception {
    mockMvc.perform(get("/api/documents/doc-b"))
            .andExpect(status().isForbidden());
}
```

Kỳ vọng 403 áp dụng khi mock request qua SecurityFilterChain thật, có handler, pre-check pass, post-check deny, và không có custom exception handler đổi status. Nếu dùng `@WebMvcTest`, phải import service/method-security configuration đúng; nếu không, test slice có thể bỏ sót interceptor và cho kết luận sai.

### 14.3. Không chỉ xem HTTP status

Kiểm thêm:

- JSON body của response deny **không chứa** `Review of Bob`/ownerId/tenantId nhạy cảm.
- Middleware tracing/logging không ghi serialized result bị deny.
- Cache response/cdn không lưu result của Bob dưới key dùng chung với Alice.
- Repository/business logs không đưa confidential content vào log trước post-check.
- Nếu một method có side effect, test rằng denied request **không** thay đổi DB, không gửi event/email; nếu không đạt, phải redesign sang pre-check.

### 14.4. 403 không bảo đảm chính là PostAuthorize

Trước khi dùng body invocation counter để chứng minh post-check, cần kiểm:
- HTTP rule cho principal test đi qua.
- `hasAuthority('document:read')` thực sự pass.
- Method invocation đến proxied bean.
- Method body trả được `DocumentView`.
- Policy hậu kiểm mới là nơi deny.

Nếu thiếu CSRF ở request POST, hoặc HTTP matcher deny sớm, 403 không chứng minh `@PostAuthorize` hoạt động.

### 14.5. Test actual authentication mapping

Với JWT Resource Server, test một token đã được kiểm signature/audience/issuer hoặc test converter bằng support chuẩn. Đảm bảo authority `document:read` thực được tạo; `@WithMockUser` chỉ chứng minh policy giả lập. Kiểm logout/revocation/tenant membership theo threat model của sản phẩm.

## 15. Ví dụ Java 17 độc lập: minh họa pre → body → post

Chương trình dưới đây **không dùng Spring**. Nó mô phỏng ba giai đoạn để thấy rõ:
- pre-check không đạt → không truy xuất tài liệu;
- pre-check đạt, nhưng owner không khớp → dữ liệu đã được đọc nội bộ, result bị deny;
- cả hai đạt → được nhận nội dung;
- nếu không tìm thấy → xử lý kết quả “not found” riêng;
- Java chỉ trả các nhãn demo, không phải HTTP status hoặc exception Spring.

Tạo file `PrePostAuthorizationDemo.java`:

```java
import java.util.Map;
import java.util.Set;

public class PrePostAuthorizationDemo {

    record Caller(String name, Set<String> authorities) {}
    record Document(String id, String owner, String title) {}

    private static final Map<String, Document> DOCUMENTS = Map.of(
            "doc-a", new Document(
                    "doc-a", "alice", "Draft of Alice"),
            "doc-b", new Document(
                    "doc-b", "bob", "Review of Bob")
    );

    private static int bodyCalls;

    private static boolean preCheck(Caller caller) {
        return caller != null
                && caller.authorities().contains("document:read");
    }

    private static Document methodBody(String id) {
        bodyCalls++;
        return DOCUMENTS.get(id);
    }

    private static boolean postCheck(
            Caller caller, Document returned) {
        return returned != null
                && returned.owner().equals(caller.name());
    }

    private static String read(Caller caller, String id) {
        if (!preCheck(caller)) {
            return "PRE_DENY";
        }

        Document returned = methodBody(id);
        if (returned == null) {
            return "NOT_FOUND";
        }

        if (!postCheck(caller, returned)) {
            return "POST_DENY";
        }
        return "ALLOW:" + returned.title();
    }

    private static void show(
            String label, Caller caller, String id) {
        int before = bodyCalls;
        String result = read(caller, id);
        int bodyDelta = bodyCalls - before;
        System.out.println(label + "=" + result
                + ";bodyCalls=" + bodyDelta);
    }

    public static void main(String[] args) {
        Caller alice = new Caller(
                "alice", Set.of("document:read"));
        Caller bob = new Caller(
                "bob", Set.of("document:read"));
        Caller writerOnly = new Caller(
                "alice", Set.of("document:write"));
        Caller adminOnly = new Caller(
                "admin", Set.of("ROLE_ADMIN"));

        show("alice-own", alice, "doc-a");
        show("alice-bob", alice, "doc-b");
        show("bob-own", bob, "doc-b");
        show("bob-alice", bob, "doc-a");
        show("alice-writer-only", writerOnly, "doc-a");
        show("admin-without-read", adminOnly, "doc-a");
        show("alice-missing", alice, "missing");
        show("anonymous", null, "doc-a");

        System.out.println("total-body-calls=" + bodyCalls);
    }
}
```

Biên dịch và chạy bằng JDK 17+:

```bash
javac PrePostAuthorizationDemo.java
java PrePostAuthorizationDemo
```

**Stdout xác định theo luồng đồng bộ trong chương trình:**

```text
alice-own=ALLOW:Draft of Alice;bodyCalls=1
alice-bob=POST_DENY;bodyCalls=1
bob-own=ALLOW:Review of Bob;bodyCalls=1
bob-alice=POST_DENY;bodyCalls=1
alice-writer-only=PRE_DENY;bodyCalls=0
admin-without-read=PRE_DENY;bodyCalls=0
alice-missing=NOT_FOUND;bodyCalls=1
anonymous=PRE_DENY;bodyCalls=0
total-body-calls=5
```

### 15.1. Giải thích kết quả

- Alice đọc `doc-a`: permission và owner đều khớp → cho phép.
- Alice đọc `doc-b`: permission đạt, body được gọi, nhưng owner là Bob → post deny.
- Bob đọc `doc-b` và `doc-a` cho kết quả đối xứng.
- Alice chỉ có `document:write`: pre deny → body không chạy.
- Admin có `ROLE_ADMIN` nhưng không được cấp `document:read` hoặc mapping/hierarchy → pre deny theo policy demo. **Không giả định ADMIN mặc nhiên có mọi permission.**
- ID missing: pre đạt và body chạy, nhưng không có record; demo trả NOT_FOUND. Trong Spring thật, có thể ném exception domain để HTTP trả 404.
- Caller null: pre deny, body không chạy.
- Tổng `bodyCalls=5` vì bốn lần Alice/Bob có read permission và một lần tìm ID thiếu, đúng theo flow.

### 15.2. Giới hạn của chương trình

- Không có Spring `@PreAuthorize`/`@PostAuthorize`/SpEL/proxy.
- Không có Servlet filter, HTTP status, JWT validation, session hoặc CSRF.
- Không có database, transaction, ORM, tenant scope, ACL hay audit.
- Dùng `Map` immutable in-memory; body chỉ đọc, không ghi dữ liệu.
- Các nhãn PRE_DENY/POST_DENY do bài tự đặt, **không** là loại `AuthorizationResult` hay HTTP code có sẵn.
- Mục tiêu duy nhất là làm rõ việc hậu kiểm xảy ra **sau** khi method body được gọi.

## 16. Một số tình huống nâng cao và lựa chọn kiến trúc

### 16.1. @PreAuthorize và @PostAuthorize có luôn cần đi đôi?

Không. Nếu `findByIdAndOwnerId(id, actorId)` đã bảo đảm object scope bằng trusted identity và service chỉ trả DTO được phép, `@PreAuthorize("hasAuthority('document:read')")` cùng kiểm tra trong repository có thể đủ. Post-check thêm là defense in depth tùy business.

Ngược lại, một method đọc có output phụ thuộc nhiều điều kiện sau khi load có thể hưởng lợi từ `@PostAuthorize`, miễn không có side effect và dữ liệu chưa bị phát tán ở nội bộ trước check.

**Đừng áp dụng hai annotation như một khuôn bắt buộc cho mọi method**. Hãy chọn theo thời điểm thông tin đáng tin có sẵn và rủi ro của việc chạy body.

### 16.2. Pre-check dựa trên object ID có đủ không?

Nếu policy `canRead(authentication, #id)` đã tra owner/tenant thật từ DB, nó có thể từ chối từ trước; như vậy body không phải load dữ liệu nhạy cảm trái phép. Nhưng nếu status/ownership thay đổi sau pre-check, body có thể đọc trạng thái mới; post-check hoặc scoped query/transaction consistency có thể hỗ trợ. Với write, vẫn phải kiểm tại lúc mutation.

### 16.3. Post-check trên dữ liệu từ cache

Nếu body đọc từ cache dùng chung, giá trị có thể thuộc người khác nếu cache key thiếu tenant/actor. Post-check có thể deny trả cho caller nhưng cache vẫn chứa object đã được tải/ghi sai chỗ, và một path khác không có post-check có thể lộ.

Thiết kế cache key theo tenant/object/policy visibility hoặc cache dữ liệu thô chỉ tại vùng trusted, rồi kiểm quyền **trước** khi phơi response. Không xem `@PostAuthorize` là cách chữa mọi cache isolation bug.

### 16.4. Custom denied-result handling

Spring Security phiên bản mới có cơ chế như `@HandleAuthorizationDenied` và `MethodAuthorizationDeniedHandler` để thay đổi hành vi khi deny. Đây là **hành vi opt-in/version-specific**, không phải mặc định. Nếu dự án dùng return-null/masked-result handler, test phải xác minh:
- Object thật không bị lộ.
- Không vô tình biến post-deny thành trả cả object.
- Caller có signal/response đúng contract.
- Custom handler không che logging/audit của lần từ chối.

Không lấy cơ chế masking làm lý do để cho một write operation chạy trước khi kiểm quyền.

### 16.5. PostFilter và AuthorizeReturnObject khác PostAuthorize

- `@PostAuthorize`: đánh giá cả **return value** sau method và cho/không cho trả giá trị.
- `@PostFilter`: dùng để lọc phần tử collection theo expression; có hệ quả với dữ liệu đã load/pagination và không nên thay scoped DB query.
- `@AuthorizeReturnObject` (cơ chế hiện đại): có thể proxy đối tượng trả về để áp method security lên member/getter của object; không phải alias của `@PostAuthorize`.

Những API này có ranh giới và version requirements khác nhau. Bài này tập trung vào **phối hợp pre + post check trên một lời gọi method**; khi cần field-level redaction hoặc collection filtering, chọn cơ chế đúng và kiểm thử riêng.

### 16.6. Object authorization qua permission evaluator

Một số dự án dùng `hasPermission(#id, 'Document', 'read')` với `PermissionEvaluator`/ACL service trong `@PreAuthorize`. Cách này có thể kiểm object-level permission **trước body**, tránh chỉ dựa vào post-check. Nó cần PermissionEvaluator được cấu hình và source dữ liệu tin cậy, không phải function có sẵn trả đúng với mọi ứng dụng.

Ví dụ fragment:

```java
@PreAuthorize(
    "hasAuthority('document:read') and " +
    "hasPermission(#id, 'Document', 'read')"
)
public DocumentView read(String id) { /* ... */ }
```

Nếu lookup dùng ID duy nhất nhưng tài nguyên có tenant scope, evaluator vẫn phải kiểm tenant/ACL; không dựa vào role “USER” cho mọi object.

## 17. Bảng lỗi thường gặp và cách sửa

| Hiện tượng | Nguyên nhân thường gặp | Hướng xử lý |
| --- | --- | --- |
| @PreAuthorize và @PostAuthorize đều có nhưng method không bị chặn | Chưa bật method security hoặc không gọi qua proxy | `@EnableMethodSecurity`, test bean được inject |
| Cứ đủ document:read là đọc được document Bob | Thiếu object-level rule hoặc post không chạy | Test owner/tenant, xác minh interceptor |
| HTTP 403 nhưng DB đã xóa tài liệu | Post-check deny sau write | Chuyển quyền về pre/service/DB guarded write |
| @Transactional được cho là luôn rollback post-deny | Advisor ordering và side effects phức tạp | Redesign write; test transaction thực |
| SpEL `returnObject.ownerId` lỗi | Return type không có ownerId, null/Optional | Chọn đúng property và guard null; policy bean |
| @PreAuthorize không biết returnObject | Result chưa tồn tại trước body | Dùng tham số/DB policy ở pre, result ở post |
| @PostAuthorize không thấy method parameter | Chưa có tên `#id`/thiếu discovery | Bật `-parameters` hoặc `@P` |
| @WithMockUser ADMIN bị deny | Role không tự map permission | Cấp/mapping đúng authority, test RoleHierarchy |
| Principal name khác UUID ownerId | So sánh hai loại ID khác nhau | Actor resolver tin cậy |
| Chỉ kiểm pathTenantId và bodyTenantId | Hai chuỗi đều client-controlled | Đọc membership và tenant thực của record |
| Sai owner bị deny nhưng audit log chứa dữ liệu của Bob | Body log trước post-check | Không log dữ liệu nhạy cảm; pre-scope query |
| Test 403 pass khi không có method security | 403 do HTTP/CSRF | Test direct service proxy và bodyCalls |
| @PostAuthorize trên Optional/List không hoạt động | returnObject là wrapper/collection | Dùng policy đúng kiểu, scoped DB query |
| self-invocation không áp annotation | Spring AOP proxy bị bypass | Tách service boundary hoặc AspectJ/test |
| JWT resource server có scope nhưng SpEL không thấy | Authority prefix `SCOPE_`/mapping khác | Test JwtAuthenticationConverter |
| Background task thiếu context | ThreadLocal không tự đi theo raw executor | Context-aware executor/service identity |
| Guest vào được service nhưng HTTP route 401 | HTTP SecurityFilterChain yêu cầu auth | Review HTTP và method layers riêng |
| User xem một số field mật dù post-check allow | PostAuthorize không mask từng field | Response DTO allowlist/field policy |
| Denied post-check trả masked value bất ngờ | Custom denied handler/version behavior | Test custom handler và không rò result |
| Error 403 tiết lộ object có tồn tại | 403 vs 404 khác nhau với foreign ID | Scoped lookup, anti-enumeration contract |
| Owner đổi giữa lúc check và use | TOCTOU | Transaction/locking/guarded update |
| Method body ném exception nhưng test đòi post result | Không có return result bình thường | Test exception path riêng |

### Quy trình gỡ lỗi bảy bước

1. Xác minh user/principal/authorities thực tế (không in raw token).
2. Xác minh Spring method security đã bật, service là Spring-managed proxy.
3. Phân loại lỗi do HTTP filter, pre-check, body exception hay post-check.
4. Nếu pre bị từ chối, kiểm role/permission và actor/parameter policy.
5. Nếu post từ chối, kiểm result type/null/ownerId/tenant và policy bean.
6. Nếu là thao tác ghi, kiểm ngay database/side effects, không chỉ response.
7. Test đúng runtime Spring/SecurityFilterChain, không chỉ class Java tự khởi tạo.

## 18. Checklist kiến trúc, kiểm thử và câu hỏi tự đánh giá

### 18.1. Checklist trước khi đưa vào sản phẩm

**Cấu hình**
- [ ] `@EnableMethodSecurity` thực sự kích hoạt cả pre/post advisors.
- [ ] Method được gọi qua Spring-managed proxy, không qua `this.inner()`.
- [ ] `@PreAuthorize` kiểm permission/role theo nguồn Authentication tin cậy.
- [ ] `@PostAuthorize` kiểm đúng kiểu result có dữ liệu ownership/tenant cần thiết.
- [ ] Dùng `authentication.name` chỉ khi đúng với internal actor ID; nếu không, có ActorResolver.
- [ ] DTO return không lộ các trường không được phép đọc.
- [ ] HTTP matcher/authentication/CSRF được kiểm tra độc lập với method security.

**Policy**
- [ ] Tenant selector/path từ client được so với membership và target tenant thật.
- [ ] Owner/ACL được tra từ DB/trusted service, không dựa vào body ownerId.
- [ ] Permission chức năng và quyền trên từng object được tách rõ.
- [ ] Pre-check tránh chạy body cho user thiếu quyền.
- [ ] Post-check không được coi là hàng rào rollback cho write/delete.
- [ ] Side effects chỉ xảy ra sau authorization phù hợp và transaction/DB guards.
- [ ] Có anti-enumeration policy cho 403/404 của tài liệu ngoài phạm vi.

**Tests**
- [ ] Pre-deny → body không chạy.
- [ ] Post-deny → body đã chạy nhưng return result không lộ.
- [ ] Pre+post allow → trả đúng object.
- [ ] Missing record/null → xử lý exception hợp lệ, không crash SpEL.
- [ ] Anonymous, wrong role, wrong authority, stale JWT và tenant khác.
- [ ] Test HTTP và service proxy độc lập, kiểm CSRF nếu phương thức ghi.
- [ ] Test side effects không xảy ra khi lệnh ghi bị deny.
- [ ] Test concurrent ownership/membership changes nếu dữ liệu có thể đổi.
- [ ] Test list/page/Optional trả về đúng contract nếu sử dụng.
- [ ] Test trên Spring Security version thật và custom denied handlers nếu có.

### 18.2. Câu hỏi tự kiểm tra

**Câu 1.** Method có `@PreAuthorize` và `@PostAuthorize`. Đó là OR hay AND?

**Đáp án:** Hai phép kiểm được áp dụng nối tiếp và đều phải cho phép để return thành công, nên có thể xem là AND về kết quả. Nhưng post chỉ kiểm sau body, không phải cả hai cùng chạy trước body.

**Câu 2.** Pre-check từ chối thì body có chạy không?

**Đáp án:** Không theo method-security interception mặc định khi gọi qua proxy. Nếu thấy body vẫn chạy, kiểm tra proxy, method-security config và đường self-invocation.

**Câu 3.** Pre allow, body đã update DB, post deny. Có chắc rollback không?

**Đáp án:** Không. Transaction ordering và nguồn side effects quyết định; không được dùng post-check làm cơ chế bảo vệ write. Kiểm trước mutation và ràng buộc DB.

**Câu 4.** `returnObject` là gì?

**Đáp án:** Giá trị mà method thực trả về sau khi thực thi thành công, trước khi được trao cho caller qua proxy. Type phải khớp biểu thức SpEL hoặc được policy bean xử lý.

**Câu 5.** `returnObject.ownerId == authentication.name` có luôn xác minh đúng owner không?

**Đáp án:** Không. Cần ownerId từ dữ liệu server và authentication.name đúng loại internal actor ID; nếu không, dùng actor resolver + policy bean.

**Câu 6.** Vì sao không dùng `@PostAuthorize` để kiểm cuối cùng của lệnh gửi email?

**Đáp án:** Email có thể đã được gửi khi post-check thực thi và không thể thu hồi chỉ bằng việc ném AccessDeniedException. Cần pre-check và domain policy trước external side effect.

**Câu 7.** Một method trả `Optional<DocumentView>`. Có thể viết `returnObject.ownerId` như DocumentView thường không?

**Đáp án:** Không nên. Return value là wrapper, phải dùng policy hiểu Optional hoặc thay API contract. Test null/empty/present riêng.

**Câu 8.** @PostAuthorize deny có tự lọc dữ liệu bí mật khỏi shared cache/log không?

**Đáp án:** Không. Body đã chạy; tránh cache/log/emit dữ liệu chưa được xác minh quyền, dùng scoped queries và DTO allowlist.

**Câu 9.** User có `ROLE_ADMIN` có tự thỏa `hasAuthority('document:read')` không?

**Đáp án:** Không mặc định. Cần authority trực tiếp, mapping hoặc RoleHierarchy được handler áp dụng.

**Câu 10.** Vì sao test status 403 chưa đủ chứng minh post-check đang chạy?

**Đáp án:** 403 có thể do HTTP filter, CSRF hoặc pre-check. Cần test proxied service và đo body call/verification của policy.

**Câu 11.** Với data theo tenant, chỉ kiểm `returnObject.ownerId` đủ chưa?

**Đáp án:** Không nếu một owner có thể tham gia nhiều tenant, có ACL chia sẻ hoặc tenant boundary độc lập. Policy phải kiểm tenant, membership và object scope.

**Câu 12.** Method được gọi qua `this.method()` bên trong cùng bean có được cả pre/post bảo vệ không?

**Đáp án:** Có nguy cơ không trong Spring AOP proxy mode. Cần gọi qua bean proxy và bảo vệ service boundary đúng kiến trúc.

**Câu 13.** Tại sao `@PostAuthorize` không đồng nghĩa `@PostFilter`?

**Đáp án:** PostAuthorize kiểm toàn bộ result cho phép/deny. PostFilter cố lọc các phần tử của collection; không được coi hai cơ chế thay thế nhau.

**Câu 14.** Method read-only có thể dùng cả pre và post khi nào?

**Đáp án:** Khi pre kiểm permission/trạng thái trước khi truy vấn, còn post kiểm ownership/tenant thật chỉ xác định được từ kết quả; đảm bảo method không có side effects nhạy cảm và policy hoạt động trên trusted object.

**Câu 15.** @PreAuthorize đã kiểm quyền theo ID từ DB, có bắt buộc @PostAuthorize không?

**Đáp án:** Không. Nếu scoped query và policy đã đầy đủ, post có thể chỉ là defense in depth; cân nhắc tính nhất quán, chi phí query và threat model.

**Câu 16.** Bị 403 vì post-check, nên sửa bằng cách trả null thay exception chứ?

**Đáp án:** Chỉ khi API policy thiết kế explicit denied-result handling; phải kiểm khả năng rò dữ liệu và đảm bảo caller hiểu contract. Không sử dụng masking/null làm cách che bug phân quyền.

### 18.3. Tổng kết

**`@PreAuthorize` và `@PostAuthorize` bổ sung cho nhau nhưng không hoán đổi được.**

- `@PreAuthorize`: kiểm tra trước, không cho user thiếu quyền gọi vào method.
- `@PostAuthorize`: kiểm tra kết quả sau khi body đã chạy, có thể chặn việc trả object ngoài quyền.
- Kết hợp: cần **hai phép kiểm đều đạt** để nhận kết quả; tuy nhiên hậu kiểm không tự hoàn tác những gì method đã làm.
- Bảo vệ dữ liệu thực: xác minh identity và quyền chức năng từ Spring Security; owner, tenant, ACL từ dữ liệu server; mọi lệnh ghi nên có pre-check và invariant trong transaction/DB.
- Kiểm thử: phải có negative cases và chứng minh **body đã/không chạy**, **kết quả không lộ**, **side effect không xảy ra** đối với write.

## Tài liệu tham khảo

- Spring Security — Method Security, @PreAuthorize + @PostAuthorize sequence, AND semantics, returnObject và cảnh báo write/transaction: https://docs.spring.io/spring-security/reference/servlet/authorization/method-security.html
- Spring Security 6.5 — Method Security: https://docs.spring.io/spring-security/reference/6.5/servlet/authorization/method-security.html
- Spring Security 7.0 — Method Security: https://docs.spring.io/spring-security/reference/7.0/servlet/authorization/method-security.html
- Spring Security — Authorization Architecture, role và GrantedAuthority: https://docs.spring.io/spring-security/reference/servlet/authorization/architecture.html
- Spring Security — HTTP request authorization: https://docs.spring.io/spring-security/reference/servlet/authorization/authorize-http-requests.html
- Spring Security — SecurityContextHolder và Authentication: https://docs.spring.io/spring-security/reference/servlet/authentication/architecture.html
- Spring Security — Method security testing: https://docs.spring.io/spring-security/reference/servlet/test/method.html
- Spring Security — MockMvc: https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/index.html
- Spring Framework — Declarative Transaction Management và transaction advisor: https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative.html
- OWASP — Broken Object Level Authorization (API1:2023): https://owasp.org/API-Security/editions/2023/en/0xa1-broken-object-level-authorization/
- OWASP — Authorization Cheat Sheet: https://cheatsheetseries.owasp.org/cheatsheets/Authorization_Cheat_Sheet.html
