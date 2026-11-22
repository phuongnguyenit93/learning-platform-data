# PermissionEvaluator cho quyền thao tác trên từng đối tượng trong Spring Security Servlet

## 1. Vì sao chỉ kiểm tra role là chưa đủ?

Một ứng dụng quản lý tài liệu thường có endpoint:

~~~http
GET /api/documents/123 HTTP/1.1
Authorization: Basic ...
~~~

Giả sử alice và bob đều có `ROLE_USER`. Quy tắc HTTP:

~~~java
.requestMatchers("/api/documents/**").hasRole("USER")
~~~

cho biết người gọi là một USER, **không trả lời được tài liệu 123 thuộc ai, nằm trong tenant nào, đã khóa hay chưa và người dùng có quyền đọc/sửa tài liệu cụ thể đó không**.

Đây là sự khác nhau giữa:

- **Role-based access control (RBAC)**: kiểm tra vai trò chung như `ROLE_USER` hoặc `ROLE_ADMIN`.
- **Permission trên từng resource (object-level authorization)**: kiểm tra hành động `read`, `write`, `delete`, `approve`... đối với **một đối tượng cụ thể**.
- **Ownership/tenant policy**: kiểm tra resource thực sự thuộc principal, nhóm, tổ chức, project hay tenant được phép.
- **Contextual policy**: xét thêm trạng thái tài liệu, thời gian, phê duyệt, MFA, separation of duties hoặc các điều kiện nghiệp vụ khác.

Spring Security có interface **`PermissionEvaluator`** để hỗ trợ các biểu thức `hasPermission(...)` trong method-security expressions. Nó cho phép ứng dụng quyết định dựa trên **Authentication + resource (hoặc ID/type) + permission**, thay vì chỉ nhìn role của người dùng.

Mục tiêu bài học:

1. Hiểu chính xác hai overload của `PermissionEvaluator` và lúc nào được gọi.
2. Biết cách xây policy dựa trên **dữ liệu resource đáng tin từ server**, không tin thông tin owner/tenant do client tự gửi.
3. Nối custom evaluator vào `@PreAuthorize`/`@PostAuthorize` qua `MethodSecurityExpressionHandler`, tránh tưởng rằng chỉ khai báo một bean là đủ ở mọi cấu hình.
4. Viết test cho ownership, same-tenant, cross-tenant, trạng thái locked, hành động được phép và bị từ chối.
5. Hiểu giới hạn về performance, truy vấn N+1, race condition/TOCTOU, CSRF và sự khác nhau giữa 401, 403, 404.
6. Áp dụng ví dụ Java 17+ / Spring Boot 3.3.13 / Spring Security 6 cho **Servlet stack**.

**Thông điệp trọng tâm:** `PermissionEvaluator` là **điểm mở rộng ra quyết định authorization**, không phải cơ sở dữ liệu quyền, không phải authentication provider và không tự bảo vệ toàn bộ đường truy cập dữ liệu.

## 2. PermissionEvaluator trong luồng Spring Security

Luồng khái niệm:

~~~text
Browser / API client
        |
        v
Servlet filters: Basic / Session / Bearer authentication
        |
        v
Authentication đã được xác minh
        |
        v
HTTP authorization, ví dụ /api/**.authenticated()
        |
        v
Spring MVC Controller
        |
        v
Spring-managed Service Proxy
        |
        v
@PreAuthorize("hasPermission(#p0, 'Document', 'read')")
        |
        +--> MethodSecurityExpressionHandler
        |         |
        |         v
        |     PermissionEvaluator.hasPermission(
        |       Authentication, targetId, targetType, permission)
        |         |
        |         +--> Tenant membership server-side
        |         +--> Document metadata owner, tenant, locked
        |         +--> Decision: true / false
        |
        +-- true  -> Service method chạy
        |
        +-- false -> AccessDeniedException -> HTTP 403 thường gặp
~~~

`@PreAuthorize` chạy qua Spring method-security interceptor trước method body. `PermissionEvaluator` trả giá trị `boolean` cho điều kiện cụ thể. Nếu biểu thức từ chối, method không chạy theo flow thông thường. HTTP response phụ thuộc `ExceptionTranslationFilter`, `AuthenticationEntryPoint`, `AccessDeniedHandler` và loại authentication.

**Ví dụ khác:** `@PostAuthorize("hasPermission(returnObject, 'read')")` kiểm quyền dựa trên object **sau khi method đã tạo kết quả**. Điều đó tiện cho một số use case nhưng có nhược điểm: service có thể đã tải dữ liệu ngoài quyền, gọi API khác, ghi log hoặc thực hiện side effects trước khi policy từ chối.

Đối với dữ liệu nhạy cảm, **ưu tiên giới hạn truy vấn theo user/tenant và kiểm tra trước khi thao tác**. Dùng PermissionEvaluator như lớp policy bổ sung, không phải phép màu ngăn mọi dữ liệu vượt phạm vi được tải vào memory.

## 3. Giao diện PermissionEvaluator: hai overload quan trọng

Trong Spring Security, interface có hai phương thức chính:

~~~java
package org.springframework.security.access;

import java.io.Serializable;
import org.springframework.security.core.Authentication;

public interface PermissionEvaluator {
    boolean hasPermission(
        Authentication authentication,
        Object targetDomainObject,
        Object permission
    );

    boolean hasPermission(
        Authentication authentication,
        Serializable targetId,
        String targetType,
        Object permission
    );
}
~~~

Đoạn trên tái hiện **chữ ký phương thức trọng tâm để giải thích**, không phải bản copy đầy đủ source/framework. Cả hai overload trả về `boolean`. Framework gọi overload nào phụ thuộc biểu thức SpEL được sử dụng.

### 3.1. Overload nhận đối tượng thật

~~~java
hasPermission(Authentication authentication,
              Object targetDomainObject,
              Object permission)
~~~

Ví dụ trong expression:

~~~java
@PreAuthorize("hasPermission(#p0, 'read')")
public Document preview(Document document) {
    // ...
}
~~~

- `authentication`: danh tính đã được xác thực theo security context.
- `targetDomainObject`: đối tượng được truyền vào method, ví dụ `Document`.
- `permission`: hành động yêu cầu, ví dụ chuỗi `"read"`.
- Evaluator có thể lấy metadata của đối tượng, query policy service hoặc so quyền theo resource ID.

**Cẩn trọng về độ tin cậy:** Nếu một REST controller nhận JSON chứa `owner="alice"` rồi tạo một `Document` do client khai báo, evaluator **không được tin** field owner đó là owner thật trong database. Nên dùng entity đã tải từ nguồn tin cậy hoặc **chỉ dùng ID của object làm khóa để truy vấn bản ghi canonical phía server**.

Một target object có thể `null` hoặc không đúng type: policy nên **fail closed** (trả false), không dùng `permitAll` làm fallback. Trường hợp target đã được tải trước khi kiểm quyền vẫn có chi phí và có thể tạo rủi ro data exposure trong service.

### 3.2. Overload nhận ID và loại đối tượng

~~~java
hasPermission(Authentication authentication,
              Serializable targetId,
              String targetType,
              Object permission)
~~~

Ví dụ:

~~~java
@PreAuthorize("hasPermission(#p0, 'Document', 'read')")
public Document read(long documentId) {
    // ...
}
~~~

Ở đây:

- `#p0` tham chiếu tham số thứ nhất, ở Java là `long documentId`; khi đi qua SpEL nó được boxed thành `Long`, một kiểu `Serializable`.
- `'Document'` là **tên loại resource do ứng dụng quy ước**, không tự động là tên entity SQL/table, class Java hay tên URL.
- `'read'` là permission yêu cầu. Bạn phải tự định nghĩa chính xác nó có nghĩa gì.
- Evaluator dùng ID/type và Authentication để tìm metadata/rights từ nguồn server.

**Ưu thế:** service có thể kiểm quyền **trước khi method body đọc resource**. Tuy nhiên evaluator vẫn có thể phải đọc metadata, và nếu sau đó method query lại mà owner/status đổi giữa chừng thì cần tránh **time-of-check-to-time-of-use (TOCTOU)**; phần 11 sẽ trình bày.

### 3.3. Hai biểu thức gọi hai overload khác nhau

| Expression | Overload | Tình huống |
| --- | --- | --- |
| `hasPermission(#document, 'read')` | Nhận object | Đã có object đáng tin |
| `hasPermission(returnObject, 'read')` | Nhận object | Kiểm tra sau khi method trả object |
| `hasPermission(#id, 'Document', 'read')` | Nhận ID + type | Chỉ có ID trước method |
| `hasPermission(#p0, 'Document', 'write')` | Nhận ID + type | Kiểm tra quyền sửa resource theo ID |
| `hasPermission(#id, 'Document', 'delete')` | Nhận ID + type | Kiểm tra quyền xóa nếu policy hỗ trợ |

Lưu ý chữ hoa/thường của `targetType` và `permission` do **ứng dụng định nghĩa**. Nếu chỉ hỗ trợ `"Document"`, `"read"`, `"write"`, thì một yêu cầu `"DOCUMENT"` hoặc `"READ"` nên bị từ chối, trừ khi bạn có quy tắc chuẩn hóa rõ ràng. Không suy đoán permission string từ tên controller một cách tự động.

## 4. PermissionEvaluator khác hasRole, hasAuthority và AuthorizationManager ra sao?

| Cơ chế | Thông tin chủ yếu | Phù hợp với |
| --- | --- | --- |
| `hasRole("ADMIN")` | Authority `ROLE_ADMIN` mặc định | Quyền chức năng/tuyến quản trị |
| `hasAuthority("document:read")` | Exact authority string | Quyền hành động chung |
| `hasPermission(#id, 'Document', 'read')` | Authentication + loại + ID + data policy | Quyền với **đối tượng cụ thể** |
| Custom `AuthorizationManager` | Authentication + context do manager chọn | HTTP/method policy phức tạp |
| Database row-level security | Identity/tenant context ở DB | Bảo vệ tập dữ liệu và query tại nguồn |
| Service/domain policy | Membership, owner, workflow, tenant, state | Invariants nghiệp vụ chi tiết |

Một user có `document:read` **không tự có quyền đọc mọi tài liệu** nếu hệ thống cần owner/tenant kiểm tra theo object. Ngược lại, user là owner của document không có nghĩa họ được thao tác `delete`/`approve` khi workflow không cho phép.

`PermissionEvaluator` thường được dùng **bên trong expression-based method authorization**. Nó không tự biến mọi `.requestMatchers(...).hasRole(...)` thành object-level checks, và không tự chạy nếu caller không đi qua method-security proxy.

Trong hệ thống nhiều entry point (MVC, batch, scheduler, message consumer), phương thức service là một nơi hợp lý để đặt policy; nhưng nếu ai đó truy cập repository trực tiếp từ endpoint khác, annotation trên service cũ **không bảo vệ đường đi mới**.

## 5. Thiết kế policy theo resource thực và tenant đáng tin

Giả sử có các tài liệu:

| ID | Tenant | Owner | Trạng thái |
| --- | --- | --- | --- |
| 1 | tenant-a | alice | draft, chưa khóa |
| 2 | tenant-a | bob | draft, chưa khóa |
| 3 | tenant-b | charlie | draft, chưa khóa |
| 4 | tenant-a | bob | locked |

Và user đã xác thực:

| User | Tenant membership server-side | Role |
| --- | --- | --- |
| alice | tenant-a | ROLE_USER |
| bob | tenant-a | ROLE_USER |
| manager | tenant-a | ROLE_MANAGER |
| charlie | tenant-b | ROLE_USER |

Chính sách demo:

1. **`read`**: user chỉ được đọc tài liệu trong **tenant của mình**, và phải là **owner** hoặc có `ROLE_MANAGER` trong tenant đó.
2. **`write`**: chỉ **owner cùng tenant** được đổi tiêu đề khi tài liệu **chưa locked**; MANAGER không tự có quyền sửa mọi document.
3. **Các permission khác** như `delete`, `approve`, `share`: **deny** vì demo không định nghĩa.
4. User chưa được xác thực, không thuộc tenant nào, ID không tồn tại, target type không hợp lệ, target null hoặc expression permission không hỗ trợ: **deny**.
5. Field `owner`/`tenant` đáng tin phải đến từ **store hoặc database** của server, không đến từ JSON, HTTP header, query string hoặc cookie client tự gán.

Với chính sách này:

~~~text
alice, read doc 1 -> ALLOW (tenant-a, owner)
alice, read doc 2 -> DENY  (không phải owner, không là manager)
manager, read doc 2 -> ALLOW (tenant-a, ROLE_MANAGER)
manager, read doc 3 -> DENY  (tenant-b, khác tenant)
charlie, read doc 3 -> ALLOW (tenant-b, owner)
alice, write doc 1 -> ALLOW (owner, chưa locked)
bob, write doc 4 -> DENY  (locked)
manager, write doc 1 -> DENY (không phải owner)
alice, delete doc 1 -> DENY (permission không được hỗ trợ)
~~~

Sơ đồ policy:

~~~text
Authentication đã được xác minh
             |
             v
Xác định tenant từ membership server-side
             |
             v
Tải metadata của resource từ store đáng tin
             |
             +-- Không có resource? -> DENY
             +-- Không có membership? -> DENY
             +-- Khác tenant? -> DENY
             |
             v
Hành động "read"?
             +-- owner hoặc manager trong tenant -> ALLOW
             +-- còn lại -> DENY
             |
Hành động "write"?
             +-- owner và chưa locked -> ALLOW
             +-- còn lại -> DENY
             |
Hành động không biết? -> DENY
~~~

Đây là policy của ví dụ, **không phải luật chung của Spring Security**. Một ứng dụng thật có thể cần người duyệt, project membership, role theo tenant, separation of duties, MFA, legal hold, ACL hoặc quyền được ủy quyền theo thời gian.

## 6. Chuẩn hóa Authentication, ID, type và permission

### 6.1. Authentication cần đến từ cơ chế đáng tin

Spring Security có thể tạo `Authentication` từ form login, HTTP Basic, session, JWT resource server hoặc một provider khác. Evaluator nên dựa vào **principal đã được framework xác minh**.

Không viết:

~~~java
// Sai về ý tưởng bảo mật: X-User do người gọi tự đặt.
String user = request.getHeader("X-User");
boolean allow = document.owner().equals(user);
~~~

Header request không phải bằng chứng authentication, trừ khi hạ tầng đã xác minh và thiết kế trust boundary/identity assertion riêng một cách nghiêm ngặt. Cũng không dùng `?isOwner=true`, `?tenantId=tenant-a`, `X-Role: ADMIN` để tự cấp quyền.

### 6.2. ID không đồng nghĩa quyền

Một ID `123` chỉ định **resource cần kiểm tra**, không chứng minh user có quyền với nó. Kiểm tra `existsById(id)` rồi cho phép mọi authenticated user là sai nếu dữ liệu có owner/tenant.

Tránh nối thẳng ID từ input thành SQL; dùng Spring Data, prepared statements/parameters, query builder hoặc phương thức repository đã được scope. `targetType` cần so sánh bằng whitelist, tránh dùng Reflection để load class tùy ý chỉ vì client gửi tên type.

### 6.3. Unknown permission fail closed

Nếu evaluator chỉ hỗ trợ `read`/`write`, yêu cầu `delete` phải trả false. Không dùng:

~~~java
default -> true; // Sai: hành động chưa biết thành permit!
~~~

Nếu quyền trở thành mã động (enum, action metadata), chuẩn hóa một lần và test mọi hành động, kể cả empty string/null/case mismatch. Chỉ cho phép **những permission đã được policy công nhận**.

### 6.4. Anonymous Authentication

Trong servlet chain, anonymous request có thể được biểu diễn bằng `AnonymousAuthenticationToken` với flag authenticated tùy framework, nên không chỉ dựa vào `authentication.isAuthenticated()` mà kết luận đây là user thật. Có thể dùng `AuthenticationTrustResolver` hoặc phân biệt anonymous token, tùy policy.

Nếu method chỉ dành cho người đã đăng nhập, thêm `@PreAuthorize("isAuthenticated() and hasPermission(...)")` cho rõ ý định, đồng thời cấu hình HTTP authentication entry point. Ví dụ hoàn chỉnh sẽ từ chối anonymous ở URL `/api/**` và evaluator cũng fail closed với anonymous.

## 7. Nối PermissionEvaluator vào method security đúng cách

### 7.1. Bật method security

~~~java
@Configuration
@EnableMethodSecurity
public class SecurityConfig {
    // ...
}
~~~

Snippet này chỉ mang ý nghĩa cấu hình; cần Java imports và các beans thực tế. `@EnableMethodSecurity` mặc định bật khả năng xử lý `@PreAuthorize`/`@PostAuthorize`.

Đừng nhầm `@EnableWebSecurity` hoặc `SecurityFilterChain` với việc bật toàn bộ method security. HTTP URL authorization và method authorization là hai lớp riêng.

### 7.2. Đăng ký evaluator cho expression handler

Ví dụ cấu hình tường minh:

~~~java
@Bean
static MethodSecurityExpressionHandler methodSecurityExpressionHandler(
        PermissionEvaluator permissionEvaluator) {

    DefaultMethodSecurityExpressionHandler handler =
        new DefaultMethodSecurityExpressionHandler();
    handler.setPermissionEvaluator(permissionEvaluator);
    return handler;
}
~~~

Snippet nằm trong class `@Configuration`, yêu cầu imports:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.security.access.PermissionEvaluator;
import org.springframework.security.access.expression.method.DefaultMethodSecurityExpressionHandler;
import org.springframework.security.access.expression.method.MethodSecurityExpressionHandler;
~~~

Hàm `static @Bean` là một pattern Spring Security sử dụng khi muốn cung cấp expression handler sớm trong quá trình khởi tạo method-security infrastructure. Nếu ứng dụng đã có bean `MethodSecurityExpressionHandler` tùy biến, **cấu hình evaluator trên bean đó** thay vì tạo hai handlers cạnh tranh.

**Không giả định chỉ cần `@Component PermissionEvaluator` là mọi expression handler đều tự dùng implementation tùy biến.** Phải test overload được gọi và kết quả trên method proxy. API/auto-configuration có thể khác giữa phiên bản, nên ví dụ khai báo handler **rõ ràng**.

### 7.3. Dùng @PreAuthorize với ID

~~~java
@PreAuthorize("hasPermission(#p0, 'Document', 'read')")
public Document read(long id) {
    return repository.findById(id).orElseThrow();
}
~~~

Snippet không độc lập: cần service bean, repository, Document và imports. `#p0` là tham số đầu tiên trong lời gọi method, tránh lệ thuộc metadata tên tham số. Biểu thức gọi overload **ID + type + permission**, đánh giá **trước method body**.

Nếu evaluator trả false, service không vào method body. Tuy nhiên evaluator có thể đã query metadata; muốn đảm bảo không lộ và tránh TOCTOU thì thiết kế query của service vẫn phải scope đúng.

### 7.4. Dùng @PreAuthorize với object

~~~java
@PreAuthorize("hasPermission(#p0, 'read')")
public Document viewLoaded(Document document) {
    return document;
}
~~~

Dạng này gọi overload **target object**. Chỉ dùng khi document là object **đáng tin do server tải**, hoặc evaluator **đọc lại dữ liệu canonical từ server theo ID**. Nếu input là DTO do client tự nhập, đừng kiểm `document.owner == authentication.name` rồi cho phép dữ liệu nhạy cảm.

### 7.5. Dùng @PostAuthorize với returnObject

~~~java
@PostAuthorize("hasPermission(returnObject, 'read')")
public Document readThenCheck(long id) {
    return repository.findById(id).orElseThrow();
}
~~~

Snippet trên kiểm quyền **sau** khi method đã đọc kết quả. Có thể hữu ích khi không biết resource trước khi method chạy, nhưng dữ liệu đã đi vào memory; logs/events/side effects trước đó **không được hoàn tác**. Khi có cách kiểm bằng ID/type trước method, ưu tiên preauthorization và query scoped.

**Không dùng `@PostAuthorize` cho thao tác có side effects quan trọng** rồi hy vọng exception sẽ rollback mọi thứ; transaction/event/outbox/remote call có thể đã thực hiện. Hãy kiểm quyền trước write và đảm bảo kiểm tra nhất quán trong transaction.

## 8. Thực thi object-level authorization cho REST API

Một API thông thường có:

~~~text
GET    /api/documents/{id}        -> read
PUT    /api/documents/{id}/title  -> write
DELETE /api/documents/{id}        -> delete
POST   /api/documents/{id}/share  -> share
~~~

HTTP security có thể yêu cầu authentication cho cả `/api/**`, nhưng method security quyết định **mỗi resource**. Nếu user A có `ROLE_USER`, chưa thể suy ra user đó có thể xóa document B.

Với request:

~~~http
PUT /api/documents/1/title HTTP/1.1
Content-Type: application/json
Authorization: Basic ...

{"title":"Bản cập nhật"}
~~~

Một flow an toàn:

1. Authentication provider xác minh user.
2. CSRF filter xử lý token khi ứng dụng dùng cơ chế thuộc phạm vi CSRF protection (demo giữ CSRF bật).
3. Method-security proxy gọi `hasPermission(1L, "Document", "write")`.
4. Evaluator xác định tenant/owner/locked theo **store phía server**.
5. Service cập nhật với **điều kiện quyền được kiểm lại trong thao tác ghi**, tránh TOCTOU.
6. Chỉ trả về DTO phù hợp, tránh phơi bày metadata nhạy cảm.

**Phân biệt 401 và 403:** người chưa được xác thực thường nhận 401 với HTTP Basic, còn user đã xác thực nhưng không có quyền thường nhận 403. Với form login, anonymous có thể nhận redirect 302. Nếu thiếu CSRF token ở PUT, có thể nhận 403 **trước khi PermissionEvaluator chạy**. Không phân tích mọi 403 như lỗi của hasPermission.

### 8.1. Trả 403 hay 404?

Khi user không có quyền với document hoặc ID không tồn tại, sản phẩm có thể chọn:
- **403 Forbidden**: phản ánh rõ thiếu quyền theo hợp đồng API.
- **404 Not Found**: tránh tiết lộ tài nguyên có tồn tại hay không cho người không được phép.

Cả hai có trade-off. Bài demo cố tình trả **403** cho ID không tồn tại khi kiểm bằng ID vì evaluator trả false; đây là **quyết định minh họa**, không phải Spring Security bắt buộc dùng 403 cho mọi trường hợp. Dù chọn 404, vẫn phải không lộ dữ liệu qua timing, error body, count, log hoặc side channel theo mức đe dọa thực tế.

### 8.2. Đừng lấy role global để bỏ qua tenant

Một rule kiểu “nếu ADMIN thì luôn true” có thể khiến quản trị viên tenant A đọc tài liệu tenant B. Nếu hệ thống là multi-tenant, hãy kiểm **tenant membership trước**, sau đó mới xét owner, manager hoặc quyền đặc biệt **trong tenant**. “Super admin cross-tenant” nếu thật sự cần phải là một policy riêng được bảo vệ và audit nghiêm ngặt.

## 9. Project Java 17+ hoàn chỉnh: Spring Boot 3.3.13, Security 6, HTTP Basic

Project này xây **PermissionEvaluator thực** cho tài liệu và cấu hình expression handler **tường minh**. Nó có cả hai overload, demo `@PreAuthorize` bằng ID và object, thêm một ví dụ `@PostAuthorize` để so sánh thời điểm.

### 9.1. Phạm vi ví dụ

- **Dữ liệu server-side:** 4 tài liệu nhỏ trong `DocumentStore`, có tenant, owner, title và locked.
- **TenantDirectory:** ánh xạ người dùng → tenant ở server; không nhận tenant từ header.
- **Evaluator:** hỗ trợ `Document/read` và `Document/write`; unknown permission hoặc type trả false.
- **HTTP:** `GET /health` public, `/api/**` authenticated, mọi đường khác deny.
- **Method service:** đọc theo ID, đọc theo object đáng tin, đọc rồi post-check, đổi title qua PUT.
- **Kiểm thử:** anonymous 401, owner được đọc, manager cùng tenant được đọc, cross-tenant bị chặn, user không phải owner bị chặn write, locked không được write, missing CSRF 403, unknown action fail closed.
- **Defense in depth:** thao tác rename kiểm lại owner/tenant/locked trong synchronized store. Với database thật cần atomic conditional UPDATE.
- **Giới hạn:** không có database, session replication, ACL persistence, audit trail, distributed locking hoặc UI; mật khẩu demo chỉ dùng local. **Không deploy nguyên trạng production.**

### 9.2. Cây file

~~~text
permission-evaluator-demo/
├── pom.xml
└── src/
    ├── main/
    │   └── java/com/example/permissiondemo/
    │       ├── PermissionDemoApplication.java
    │       ├── SecurityConfig.java
    │       ├── TenantDirectory.java
    │       ├── DocumentStore.java
    │       ├── DocumentPermissionEvaluator.java
    │       ├── DocumentService.java
    │       └── DocumentController.java
    └── test/
        └── java/com/example/permissiondemo/
            └── PermissionEvaluatorTests.java
~~~

**`pom.xml`**

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.13</version>
        <relativePath/>
    </parent>
    <groupId>com.example</groupId>
    <artifactId>permission-evaluator-demo</artifactId>
    <version>1.0.0</version>
    <properties>
        <java.version>17</java.version>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-web</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-security</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
        </dependency>
        <dependency>
            <groupId>org.springframework.security</groupId>
            <artifactId>spring-security-test</artifactId>
            <scope>test</scope>
        </dependency>
    </dependencies>
    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
~~~

**`src/main/java/com/example/permissiondemo/PermissionDemoApplication.java`**

~~~java
package com.example.permissiondemo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class PermissionDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(PermissionDemoApplication.class, args);
    }
}
~~~

### 9.3. SecurityConfig: HTTP và method expression handler

**`src/main/java/com/example/permissiondemo/SecurityConfig.java`**

~~~java
package com.example.permissiondemo;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.access.PermissionEvaluator;
import org.springframework.security.access.expression.method.DefaultMethodSecurityExpressionHandler;
import org.springframework.security.access.expression.method.MethodSecurityExpressionHandler;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
@EnableMethodSecurity
public class SecurityConfig {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {
        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/health").permitAll()
                .requestMatchers("/api/**").authenticated()
                .anyRequest().denyAll()
            )
            .httpBasic(Customizer.withDefaults())
            // Không tắt CSRF: PUT /api/** cần token trong demo.
            .build();
    }

    @Bean
    static MethodSecurityExpressionHandler methodSecurityExpressionHandler(
            PermissionEvaluator permissionEvaluator) {
        DefaultMethodSecurityExpressionHandler handler =
            new DefaultMethodSecurityExpressionHandler();
        handler.setPermissionEvaluator(permissionEvaluator);
        return handler;
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder(10);
    }

    @Bean
    UserDetailsService userDetailsService(PasswordEncoder encoder) {
        String hash = encoder.encode("demo-pass");

        return new InMemoryUserDetailsManager(
            User.withUsername("alice")
                .password(hash)
                .roles("USER")
                .build(),
            User.withUsername("bob")
                .password(hash)
                .roles("USER")
                .build(),
            User.withUsername("manager")
                .password(hash)
                .roles("MANAGER")
                .build(),
            User.withUsername("charlie")
                .password(hash)
                .roles("USER")
                .build()
        );
    }
}
~~~

**Giải thích:**

1. `@EnableMethodSecurity` bật `@PreAuthorize`/`@PostAuthorize` cho Spring-managed beans qua method-security infrastructure.
2. Static `@Bean MethodSecurityExpressionHandler` cấu hình **chính instance evaluator** dùng trong expressions, không chỉ đăng ký một Component rồi hy vọng auto-wiring.
3. HTTP filter chain chỉ đảm bảo `/api/**` đã authenticated. **Quyền với từng Document** được kiểm ở service.
4. HTTP Basic dùng trong test để dễ phân biệt 401/403; password `demo-pass` không được dùng thật.
5. CSRF mặc định vẫn bật trong Servlet. Với các GET test không cần token, nhưng PUT dùng `.with(csrf())`.

### 9.4. TenantDirectory: membership đáng tin từ server

**`src/main/java/com/example/permissiondemo/TenantDirectory.java`**

~~~java
package com.example.permissiondemo;

import java.util.Map;
import org.springframework.stereotype.Component;

@Component
public class TenantDirectory {

    private final Map<String, String> tenantByUsername = Map.of(
        "alice", "tenant-a",
        "bob", "tenant-a",
        "manager", "tenant-a",
        "charlie", "tenant-b"
    );

    public String tenantFor(String username) {
        return tenantByUsername.get(username);
    }
}
~~~

Ở production, membership thường đến từ database, identity service hoặc claims **đã được token verifier xác minh**, có thể gồm nhiều tenant, nhóm và quyền trong từng tenant. Demo chỉ dùng một tenant/user. Không thay method này bằng `request.getHeader("X-Tenant")` rồi tin client.

### 9.5. DocumentStore: metadata canonical và update guarded

**`src/main/java/com/example/permissiondemo/DocumentStore.java`**

~~~java
package com.example.permissiondemo;

import java.util.HashMap;
import java.util.Map;
import java.util.Objects;
import java.util.Optional;

import org.springframework.security.access.AccessDeniedException;
import org.springframework.stereotype.Component;

@Component
public class DocumentStore {

    public record Doc(
        long id,
        String tenantId,
        String owner,
        String title,
        boolean locked
    ) {
    }

    private final Map<Long, Doc> docs = new HashMap<>(Map.of(
        1L, new Doc(1L, "tenant-a", "alice", "Design", false),
        2L, new Doc(2L, "tenant-a", "bob", "Finance", false),
        3L, new Doc(3L, "tenant-b", "charlie", "Legal", false),
        4L, new Doc(4L, "tenant-a", "bob", "Frozen", true)
    ));

    public synchronized Optional<Doc> find(long id) {
        return Optional.ofNullable(docs.get(id));
    }

    public synchronized Doc renameIfOwnedAndUnlocked(
            long id,
            String authenticatedUser,
            String trustedTenant,
            String newTitle) {

        Doc current = docs.get(id);

        if (current == null
                || !Objects.equals(current.tenantId(), trustedTenant)
                || !Objects.equals(current.owner(), authenticatedUser)
                || current.locked()) {
            throw new AccessDeniedException("Document operation not allowed");
        }

        Doc updated = new Doc(
            current.id(),
            current.tenantId(),
            current.owner(),
            newTitle,
            current.locked()
        );
        docs.put(id, updated);
        return updated;
    }
}
~~~

Synchronized demo cho thao tác đọc/ghi nhất quán trong **một JVM**, không thay transaction isolation/locking trong database. Điều kiện owner/tenant/locked được kiểm **bên trong chính thao tác update**, tránh chỉ dựa vào một preauthorization check xảy ra trước đó.

Store không cung cấp API sửa owner/tenant/locked từ request, nên các dữ liệu policy là server-controlled. Trong production có thể có cập nhật owner/membership đồng thời trên nhiều instance; cần DB transaction hoặc atomic conditional UPDATE và xử lý quyền theo dữ liệu tại thời điểm write.

### 9.6. DocumentPermissionEvaluator: hai overload và deny by default

**`src/main/java/com/example/permissiondemo/DocumentPermissionEvaluator.java`**

~~~java
package com.example.permissiondemo;

import java.io.Serializable;
import java.util.Objects;

import org.springframework.security.access.PermissionEvaluator;
import org.springframework.security.authentication.AnonymousAuthenticationToken;
import org.springframework.security.core.Authentication;
import org.springframework.stereotype.Component;

import com.example.permissiondemo.DocumentStore.Doc;

@Component
public class DocumentPermissionEvaluator implements PermissionEvaluator {

    private final DocumentStore store;
    private final TenantDirectory tenants;

    public DocumentPermissionEvaluator(
            DocumentStore store,
            TenantDirectory tenants) {
        this.store = store;
        this.tenants = tenants;
    }

    @Override
    public boolean hasPermission(
            Authentication authentication,
            Object targetDomainObject,
            Object permission) {

        if (!(targetDomainObject instanceof Doc doc)) {
            return false;
        }

        // Không tin owner/tenant từ object đầu vào: chỉ lấy ID,
        // rồi đọc lại bản canonical từ server-side store.
        return permitted(authentication, doc.id(), permission);
    }

    @Override
    public boolean hasPermission(
            Authentication authentication,
            Serializable targetId,
            String targetType,
            Object permission) {

        if (!"Document".equals(targetType)
                || !(targetId instanceof Long id)) {
            return false;
        }

        return permitted(authentication, id, permission);
    }

    private boolean permitted(
            Authentication authentication,
            long documentId,
            Object permission) {

        if (authentication == null
                || !authentication.isAuthenticated()
                || authentication instanceof AnonymousAuthenticationToken) {
            return false;
        }

        String trustedTenant = tenants.tenantFor(authentication.getName());
        if (trustedTenant == null) {
            return false;
        }

        Doc doc = store.find(documentId).orElse(null);
        if (doc == null
                || !Objects.equals(doc.tenantId(), trustedTenant)) {
            return false;
        }

        boolean owner = authentication.getName().equals(doc.owner());
        boolean manager = authentication.getAuthorities().stream()
            .anyMatch(a -> "ROLE_MANAGER".equals(a.getAuthority()));

        if ("read".equals(permission)) {
            return owner || manager;
        }

        if ("write".equals(permission)) {
            return owner && !doc.locked();
        }

        return false; // Unknown action -> deny.
    }
}
~~~

**Giải thích chi tiết:**

- `hasPermission(auth, Object, permission)` chỉ nhận `Doc`; object khác/null → false.
- Dù client tạo Doc giả, code **không tin owner/tenant của object được truyền vào**; nó tra bản canonical theo ID trong DocumentStore.
- `hasPermission(auth, Serializable, targetType, permission)` chỉ cho `targetType = "Document"` và ID Java `Long`; loại khác → false.
- `authentication.isAuthenticated()` chưa đủ để nhận biết anonymous; code còn loại `AnonymousAuthenticationToken`. Với policy production có thể dùng `AuthenticationTrustResolver` cho các trạng thái đặc biệt.
- Tenant lấy từ `TenantDirectory`, không từ header/query của client. Cross-tenant bị từ chối **trước** khi xét manager.
- Manager được đọc từ authority đáng tin trong `Authentication`, không phải từ `X-Role` hoặc một field JSON.
- `"read"` và `"write"` là hai hành động duy nhất được support. `"delete"`, `"approve"`, `null`, mọi biến thể không khai báo đều trả false.
- Để tránh mở quyền khi có lỗi store, hệ thống thật cần chiến lược xử lý lỗi rõ ràng. **Không bắt mọi database exception rồi trả true**; nếu hạ tầng lỗi có thể fail closed và ghi cảnh báo an toàn.
- Evaluator này **không cache toàn cục các quyết định theo ID mà bỏ user/tenant/permission**, vì điều đó có thể tạo lỗ hổng quyền chéo.

**Lưu ý về targetId:** Ở demo, `#p0` có kiểu `long` nên được boxed thành `Long`. Nếu project dùng `UUID` hoặc String ID, thay kiểm tra type và repository lookup tương ứng; không tự ép mọi giá trị sang Long bằng cách làm tròn số.

### 9.7. DocumentService: kiểm quyền trước đọc, object overload và post-check

**`src/main/java/com/example/permissiondemo/DocumentService.java`**

~~~java
package com.example.permissiondemo;

import org.springframework.http.HttpStatus;
import org.springframework.security.access.prepost.PostAuthorize;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.stereotype.Service;
import org.springframework.web.server.ResponseStatusException;

import com.example.permissiondemo.DocumentStore.Doc;

@Service
public class DocumentService {

    private final DocumentStore store;
    private final TenantDirectory tenants;

    public DocumentService(DocumentStore store, TenantDirectory tenants) {
        this.store = store;
        this.tenants = tenants;
    }

    @PreAuthorize("hasPermission(#p0, 'Document', 'read')")
    public Doc read(long id) {
        return store.find(id).orElseThrow();
    }

    @PreAuthorize("hasPermission(#p0, 'read')")
    public Doc readServerLoaded(Doc document) {
        // Lấy bản canonical, không trả object giả từ client.
        return store.find(document.id()).orElseThrow();
    }

    @PostAuthorize("hasPermission(returnObject, 'read')")
    public Doc readPostChecked(long id) {
        // Chỉ demo: method ĐÃ đọc trước khi PostAuthorize đánh giá.
        return store.find(id).orElseThrow();
    }

    @PreAuthorize("hasPermission(#p0, 'Document', 'write')")
    public Doc rename(long id, String newTitle) {
        if (newTitle == null
                || newTitle.isBlank()
                || newTitle.length() > 80) {
            throw new ResponseStatusException(
                HttpStatus.BAD_REQUEST, "Invalid title");
        }

        Authentication authentication =
            SecurityContextHolder.getContext().getAuthentication();

        String actor = authentication.getName();
        String tenant = tenants.tenantFor(actor);

        // Kiểm lại owner/tenant/locked trong mutation.
        return store.renameIfOwnedAndUnlocked(
            id, actor, tenant, newTitle);
    }
}
~~~

Điểm quan trọng:

1. `read(id)`: ID overload kiểm quyền **trước** khi method body đọc tài liệu.
2. `readServerLoaded(Doc)`: object overload kiểm quyền. Dữ liệu canonical được tải từ store; method không tin field của object client tự khai.
3. `readPostChecked(id)`: object overload qua `returnObject` nhưng chạy **sau** khi đã tải. Chỉ dùng để học, không coi là cách chống đọc nhầm dữ liệu trong mọi ngữ cảnh.
4. `rename(id, title)`: ID overload kiểm `write` trước khi cập nhật, sau đó store **kiểm lại** quyền khi mutation xảy ra.
5. Nếu ID không tồn tại, `@PreAuthorize` trả deny và method body không chạy. `orElseThrow()` là đường phòng thủ đơn giản trong demo; với service production cần exception mapping nhất quán theo hợp đồng.
6. `SecurityContextHolder` được dùng bên trong service để lấy actor thật của lời gọi qua Spring Security. Với async/non-web callers, phải có propagation đúng; không tự copy context không có cleanup.

### 9.8. DocumentController: mapping HTTP và dữ liệu vào

**`src/main/java/com/example/permissiondemo/DocumentController.java`**

~~~java
package com.example.permissiondemo;

import java.util.Map;

import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PutMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ResponseStatusException;

import com.example.permissiondemo.DocumentStore.Doc;

@RestController
public class DocumentController {

    private final DocumentService service;
    private final DocumentStore store;

    public DocumentController(
            DocumentService service,
            DocumentStore store) {
        this.service = service;
        this.store = store;
    }

    @GetMapping("/health")
    public Map<String, String> health() {
        return Map.of("status", "ok");
    }

    @GetMapping("/api/documents/{id}")
    public Doc read(@PathVariable long id) {
        return service.read(id);
    }

    @GetMapping("/api/documents/{id}/object")
    public Doc readObject(@PathVariable long id) {
        // Chỉ minh họa object-overload: dữ liệu từ store server.
        Doc canonical = store.find(id)
            .orElseThrow(() -> new ResponseStatusException(
                HttpStatus.NOT_FOUND, "Not found"));
        return service.readServerLoaded(canonical);
    }

    @GetMapping("/api/documents/{id}/post")
    public Doc readPost(@PathVariable long id) {
        return service.readPostChecked(id);
    }

    public record RenameRequest(String title) {
    }

    @PutMapping("/api/documents/{id}/title")
    public Doc rename(
            @PathVariable long id,
            @RequestBody RenameRequest request) {
        return service.rename(id, request.title());
    }
}
~~~

Controller gọi `DocumentService` thông qua **Spring-managed dependency**. Annotation method security chạy trên service proxy; tránh self-invocation `this.securedMethod()` trong cùng bean.

Với `/object`, controller **đã tải object trước method-security check**. Ví dụ này chỉ để thấy overload nhận object; production thường ưu tiên ID overload/query scoped để tránh fetch dữ liệu nhạy cảm trước authorization. Nếu giữ object overload, không log/serialize/phát event từ canonical object trước khi policy cho phép.

Trong demo, DTO `RenameRequest` chỉ có title; client **không được quyền thay owner/tenant/locked**. Nếu controller nhận entity từ body và save trực tiếp, attacker có thể thử mass assignment; cần DTO riêng, validation và mapping những field được phép.

### 9.9. MockMvc integration tests: quyền từng document, tenant, locked, CSRF

**`src/test/java/com/example/permissiondemo/PermissionEvaluatorTests.java`**

~~~java
package com.example.permissiondemo;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.security.access.PermissionEvaluator;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.test.web.servlet.MockMvc;

import java.util.List;

import static org.assertj.core.api.Assertions.assertThat;
import static org.springframework.security.test.web.servlet.request
    .SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.security.test.web.servlet.request
    .SecurityMockMvcRequestPostProcessors.httpBasic;
import static org.springframework.test.web.servlet.request
    .MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request
    .MockMvcRequestBuilders.put;
import static org.springframework.test.web.servlet.result
    .MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result
    .MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class PermissionEvaluatorTests {

    @Autowired
    MockMvc mvc;

    @Autowired
    PermissionEvaluator evaluator;

    @Test
    void publicHealthAndAnonymousProtectedRequest() throws Exception {
        mvc.perform(get("/health"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.status").value("ok"));

        mvc.perform(get("/api/documents/1"))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void ownerReadsOwnDocumentButNotOthers() throws Exception {
        mvc.perform(get("/api/documents/1")
                .with(httpBasic("alice", "demo-pass")))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.owner").value("alice"));

        mvc.perform(get("/api/documents/2")
                .with(httpBasic("alice", "demo-pass")))
            .andExpect(status().isForbidden());

        mvc.perform(get("/api/documents/2")
                .with(httpBasic("bob", "demo-pass")))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.owner").value("bob"));
    }

    @Test
    void managerReadsSameTenantButNotAnotherTenant() throws Exception {
        mvc.perform(get("/api/documents/1")
                .with(httpBasic("manager", "demo-pass")))
            .andExpect(status().isOk());

        mvc.perform(get("/api/documents/2")
                .with(httpBasic("manager", "demo-pass")))
            .andExpect(status().isOk());

        mvc.perform(get("/api/documents/3")
                .with(httpBasic("manager", "demo-pass")))
            .andExpect(status().isForbidden());

        mvc.perform(get("/api/documents/3")
                .with(httpBasic("charlie", "demo-pass")))
            .andExpect(status().isOk());
    }

    @Test
    void objectOverloadAndPostAuthorizeUseSamePolicy() throws Exception {
        mvc.perform(get("/api/documents/1/object")
                .with(httpBasic("alice", "demo-pass")))
            .andExpect(status().isOk());

        mvc.perform(get("/api/documents/1/object")
                .with(httpBasic("bob", "demo-pass")))
            .andExpect(status().isForbidden());

        mvc.perform(get("/api/documents/1/post")
                .with(httpBasic("alice", "demo-pass")))
            .andExpect(status().isOk());

        mvc.perform(get("/api/documents/1/post")
                .with(httpBasic("bob", "demo-pass")))
            .andExpect(status().isForbidden());
    }

    @Test
    void ownerMayRenameUnlockedDocument() throws Exception {
        mvc.perform(put("/api/documents/1/title")
                .with(httpBasic("alice", "demo-pass"))
                .with(csrf())
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"title\":\"Revised\"}"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.title").value("Revised"));
    }

    @Test
    void writeDeniedForNonOwnerManagerAndLockedDocument()
            throws Exception {
        mvc.perform(put("/api/documents/1/title")
                .with(httpBasic("bob", "demo-pass"))
                .with(csrf())
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"title\":\"Not allowed\"}"))
            .andExpect(status().isForbidden());

        mvc.perform(put("/api/documents/1/title")
                .with(httpBasic("manager", "demo-pass"))
                .with(csrf())
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"title\":\"Not allowed\"}"))
            .andExpect(status().isForbidden());

        mvc.perform(put("/api/documents/4/title")
                .with(httpBasic("bob", "demo-pass"))
                .with(csrf())
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"title\":\"Locked\"}"))
            .andExpect(status().isForbidden());
    }

    @Test
    void csrfIsIndependentOfWritePermission() throws Exception {
        mvc.perform(put("/api/documents/1/title")
                .with(httpBasic("alice", "demo-pass"))
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"title\":\"No CSRF\"}"))
            .andExpect(status().isForbidden());
    }

    @Test
    void missingDocumentAndUnlistedRouteAreDenied()
            throws Exception {
        mvc.perform(get("/api/documents/999")
                .with(httpBasic("alice", "demo-pass")))
            .andExpect(status().isForbidden());

        mvc.perform(get("/unlisted")
                .with(httpBasic("alice", "demo-pass")))
            .andExpect(status().isForbidden());
    }

    @Test
    void unknownPermissionAndWrongTypeFailClosed() {
        var alice = new UsernamePasswordAuthenticationToken(
            "alice",
            "unused",
            List.of(new SimpleGrantedAuthority("ROLE_USER"))
        );

        assertThat(evaluator.hasPermission(
            alice, 1L, "Document", "delete")).isFalse();

        assertThat(evaluator.hasPermission(
            alice, 1L, "Unknown", "read")).isFalse();

        assertThat(evaluator.hasPermission(
            alice, (Object) null, "read")).isFalse();

        assertThat(evaluator.hasPermission(
            alice, 3L, "Document", "read")).isFalse();
    }
}
~~~

**Tại sao test đáng tin hơn kiểm một dòng code?**

- Test đi qua HTTP authentication/Servlet security và **method proxy** thực sự, phát hiện lỗi quên `@EnableMethodSecurity` hoặc expression handler không được nối.
- Kiểm thử cả **allow** và **deny**, đặc biệt tài liệu cùng tenant khác owner và tài liệu khác tenant.
- Kiểm tra manager không có quyền write dù được đọc tài liệu cùng tenant.
- Tài liệu locked bị deny write ngay cả khi caller là owner.
- Kiểm tra hai overload: ID trong `read` và object trong `readObject`; `@PostAuthorize` cũng dùng overload object.
- Phân biệt **403 vì thiếu permission** với **403 vì CSRF** trên PUT.
- Permission/type không khai báo đều trả false.
- Không dùng `@WithMockUser` để làm giả toàn bộ quá trình xác minh password ở HTTP tests: `httpBasic(...)` đưa credentials qua filter chain.
- Dữ liệu test chỉ đổi **title** của document 1, không đổi tenant/owner/locked nên các kiểm quyền khác vẫn ổn dù test chạy theo thứ tự không cố định. Với DB test thật nên rollback/seed per test để bảo đảm độc lập mạnh hơn.

### 9.10. Chạy Maven và curl

Yêu cầu **JDK 17+, Maven** và khả năng tải dependencies lần đầu:

~~~bash
mvn test
mvn spring-boot:run
~~~

**Kết quả mong đợi:** Spring context được tạo, các tests pass, Maven in `BUILD SUCCESS` nếu file và môi trường đúng. Nội dung này mô tả cách tự chạy; **chưa thực thi Maven ở đây**.

Trong terminal khác:

~~~bash
curl -i http://localhost:8080/health
# Dự kiến 200 {"status":"ok"}

curl -i http://localhost:8080/api/documents/1
# Dự kiến 401 với HTTP Basic challenge

curl -i -u alice:demo-pass http://localhost:8080/api/documents/1
# Dự kiến 200, JSON document 1 thuộc alice

curl -i -u alice:demo-pass http://localhost:8080/api/documents/2
# Dự kiến 403

curl -i -u manager:demo-pass http://localhost:8080/api/documents/2
# Dự kiến 200 vì manager cùng tenant

curl -i -u manager:demo-pass http://localhost:8080/api/documents/3
# Dự kiến 403 vì khác tenant

curl -i -u bob:demo-pass http://localhost:8080/api/documents/4
# Dự kiến 200 khi READ, nhưng WRITE bị khóa

curl -i -u alice:demo-pass http://localhost:8080/api/documents/999
# Dự kiến 403 theo policy fail-closed của demo
~~~

Không thử PUT rồi kết luận 403 do PermissionEvaluator nếu request chưa gửi CSRF token hợp lệ. MockMvc có `with(csrf())` để kiểm soát chính xác tình huống này. Để gọi PUT qua curl khi CSRF bật, phải lấy token theo `CsrfTokenRepository` và cookie/session context được ứng dụng cấu hình; demo này không chủ động xuất CSRF token cho curl client.

**An toàn thực tế:** HTTP Basic dùng Base64, **không mã hóa credentials**. Chỉ dùng HTTP trên localhost cho học tập, không đưa user/password demo ra Internet. Trong môi trường thật dùng HTTPS, credentials được quản lý an toàn và validation/rate limiting/audit.

## 10. Định nghĩa permission và thống nhất biểu thức

### 10.1. Đừng để permission string phân tán

Nếu code có `'read'`, `'READ'`, `'view'` cho cùng hành động mà không có chuẩn chung, policy dễ bị sai hoặc mở quá mức. Với hệ thống nhiều modules, cân nhắc định nghĩa enum/constant permission rồi ánh xạ chuẩn:

~~~java
public enum DocumentPermission {
    READ, WRITE, SHARE, DELETE
}
~~~

Đây là snippet độc lập (đặt trong file `DocumentPermission.java` nếu đưa vào project), không cần cho demo string literal. Một evaluator hỗ trợ enum sẽ phải kiểm kiểu permission và xử lý rõ action chưa hỗ trợ. **Không** cast mù hoặc mặc định true khi enum mới được thêm.

### 10.2. Role và permission không đồng nghĩa

`hasRole("MANAGER")` mặc định kiểm `ROLE_MANAGER`; permission `read` đối với tài liệu 123 lại là **quyết định có ngữ cảnh resource**. Một manager được xem mọi tài liệu trong tenant có thể không được sửa, không được xem cross-tenant và không được export PII. Sự khác nhau này nên được lưu trong test và tài liệu chính sách.

### 10.3. Named-argument SpEL

Nếu bạn dùng:

~~~java
@PreAuthorize("hasPermission(#documentId, 'Document', 'read')")
~~~

thì tên `documentId` phải có thể được Spring Security đọc đúng (ví dụ metadata `-parameters` của Java compiler hoặc cấu hình liên quan). Dùng `#p0` tránh phụ thuộc tên parameter trong ví dụ, nhưng làm biểu thức kém mô tả hơn. Trong code production, có thể dùng tên tham số rõ ràng khi build đảm bảo metadata, kèm integration test.

### 10.4. Null target và ID format

Target object có thể null; ID có thể sai kiểu (Long vs UUID vs String). Hãy xác định type contract rõ ràng. Với tài liệu có UUID, evaluator cần dùng `UUID` làm ID và repository cần tránh ID enumeration/guessing nếu resource nhạy cảm; **UUID không thay authorization**. Nếu ID không tồn tại, default deny hoặc 404 theo API policy đã thống nhất.

## 11. Performance, database và TOCTOU

### 11.1. N+1 authorization queries

Nếu một endpoint trả 1.000 tài liệu rồi gọi `hasPermission(document, 'read')` cho từng cái, evaluator có thể query metadata/membership 1.000 lần. Kết quả là **N+1 queries**, latency cao và dễ làm kiệt DB pool.

Giải pháp:

- Với list/search, dùng **repository query đã scope** theo tenant/owner/ACL.
- Tải permission metadata theo batch khi thật sự cần.
- Dùng projection/DTO chỉ có field cần kiểm.
- Cân nhắc query EXISTS hoặc join với membership/ACL.
- Chỉ kiểm individual resource ID ở method khi endpoint xử lý **một** tài liệu hoặc batch nhỏ có kiểm soát.

### 11.2. Query scoped trước pagination

Một query ý tưởng:

~~~sql
SELECT d.id, d.tenant_id, d.owner_id, d.title, d.locked
FROM documents d
WHERE d.tenant_id = :trustedTenantId
  AND (d.owner_id = :principalId OR :hasTenantManagerRole = TRUE)
  AND d.deleted = FALSE
ORDER BY d.id DESC
LIMIT :limit OFFSET :offset;
~~~

Named parameters phải được bind an toàn từ **server-validated principal và tenant membership**, không nối SQL từ client. Một điều kiện manager boolean đáng tin phải được tính từ quyền có phạm vi tenant; không đưa `?isManager=true` từ request trực tiếp vào query.

**Quan trọng:** áp filter quyền ở SQL **trước** khi LIMIT/OFFSET và count. Không lấy 100.000 records rồi lọc với `@PostFilter` hoặc gọi hasPermission từng record để cuối cùng trả 20 records — như vậy DB/network/JVM đã chịu chi phí lớn, và pagination/total count có thể sai.

### 11.3. Tối ưu cho object ID

Khi kiểm một ID, query có thể thực hiện:

~~~sql
SELECT d.id, d.tenant_id, d.owner_id, d.locked
FROM documents d
WHERE d.id = :documentId;
~~~

Sau đó evaluator quyết định theo owner/tenant/status. Nhưng nếu phải thực hiện mutation, **đừng tách “kiểm quyền” và “cập nhật” quá xa** về mặt transaction; quyền có thể thay đổi giữa hai thời điểm. Lệnh UPDATE nên bao gồm cả các điều kiện bảo vệ khi có thể:

~~~sql
UPDATE documents
SET title = :title
WHERE id = :documentId
  AND tenant_id = :trustedTenantId
  AND owner_id = :principalId
  AND locked = FALSE;
~~~

Kiểm `affectedRows == 1` để xác định thao tác đã được thực hiện đúng điều kiện. Với policy phức tạp cần thêm ACL/permission join, transaction isolation/locks hoặc service authorization atomically. **Kiểm ở evaluator trước method chưa đủ để loại bỏ TOCTOU**.

### 11.4. Caching authorization decision

Cache tùy tiện theo `documentId` là lỗi nặng: alice được read doc 1, cache true, rồi bob gọi doc 1 có thể nhận lại true nếu key chỉ là ID. Nếu thật sự cache decision, key phải có **principal, tenant, resource ID/version, action, policy version** và expiry/revocation phù hợp.

Trong nhiều trường hợp chi phí và rủi ro invalidation lớn hơn lợi ích cache; một truy vấn indexed theo user/tenant/resource là lựa chọn dễ đúng hơn. Khi quyền thay đổi, đừng giữ stale decisions vô thời hạn.

### 11.5. Side effects của @PostAuthorize

`@PostAuthorize` chạy sau method body, nên nếu method viết DB/gửi message hoặc gọi remote API, việc throw AccessDeniedException **không chắc hoàn tác mọi side effect**. Với write methods, ưu tiên authorization trước và kiểm tra trong mutation transaction.

### 11.6. Quyền thay đổi trong lúc request đang chạy

Owner, tenant membership, lock status và ACL có thể thay đổi. Cần quyết định:
- Quyền phải đúng tại thời điểm request bắt đầu hay tại thời điểm commit?
- Giao dịch có yêu cầu consistency/locking không?
- Nếu quyền bị thu hồi trong session/token đang sống, policy có bị stale?
- Có cần audit “ai được phép tại thời điểm nào” không?

Ví dụ in-memory cố ý kiểm lại trong synchronized mutation nhưng chỉ hoạt động trong một JVM; production với nhiều replicas phải dùng cơ chế DB/distributed phù hợp.

## 12. Thông báo lỗi, privacy và audit

### 12.1. Không tiết lộ dữ liệu khi deny

Nếu bob gọi `GET /api/documents/1`, response 403/404 không nên chứa owner email, title hoặc nội dung tài liệu. Không dùng một exception message như “Tài liệu Design của alice không thuộc bạn” nếu bob chưa có quyền biết tài liệu ấy tồn tại. Logging server-side cần kiểm soát quyền đọc, retention và redaction.

### 12.2. Audit có ích nhưng không log secrets

Khi từ chối quyền, có thể log:
- Thời điểm, caller ID đã xác minh, tenant ID.
- Resource type/ID đã được xử lý phù hợp với chính sách privacy.
- Action `read/write`, policy version và decision deny/allow.
- Request correlation ID.

Tránh log Authorization header, Bearer token, session cookie, password, nguyên body có PII. Cân nhắc chỉ log deny, aggregate metrics và sampling tùy khối lượng; đừng tạo log flooding/DoS.

### 12.3. Khi evaluator/service không truy cập được database

Lỗi hạ tầng không nên biến thành `permitAll`. Cũng không nên bắt mọi exception rồi luôn trả 403 nếu điều đó che giấu sự cố quan trọng. Thiết kế fault policy rõ ràng: fail closed cho data access, trả 5xx thích hợp khi service bị lỗi, ghi log có kiểm soát và báo alert; tuyệt đối không trả dữ liệu nhạy cảm như một fallback.

### 12.4. Đừng chuyển chính sách sang frontend

Ẩn nút “Sửa” trong UI theo role là cải thiện trải nghiệm, **không phải enforcement**. Client có thể gọi HTTP trực tiếp. Quyền resource phải được server kiểm; API Gateway/HTTP rule và service/DB policy cần nhất quán.

## 13. Các lỗi thường gặp khi triển khai PermissionEvaluator

| Lỗi | Hệ quả | Cách sửa |
| --- | --- | --- |
| Chỉ dùng `hasRole('USER')` cho `/documents/{id}` | User A có thể truy cập tài liệu B | Object-level permission check |
| Chỉ tạo bean PermissionEvaluator, không cấu hình expression handler | `hasPermission` có thể không gọi evaluator muốn dùng | Nối handler tường minh và test |
| Quên `@EnableMethodSecurity` | @PreAuthorize/@PostAuthorize không được áp dụng | Bật và kiểm qua Spring proxy |
| Gọi method annotated bằng `this.read(...)` cùng bean | Self-invocation có thể bypass proxy | Tách bean, gọi qua injected service |
| Đọc `owner` từ body JSON để xác minh ownership | Client tự giả owner | Đọc canonical resource server-side |
| Lấy tenant từ header `X-Tenant` không xác minh | Lộ chéo tenant | Tenant membership đáng tin |
| Cho manager bypass trước khi kiểm tenant | Manager tenant A xem tenant B | Kiểm tenant trước role |
| `default -> true` cho permission lạ | Hành động mới được cấp quyền ngầm | Deny unknown permissions |
| Không xử lý null target/unknown type | NPE hoặc mở quyền | Validate rồi fail closed |
| ID lookup không giới hạn type | Nhầm bảng/resource, rủi ro type confusion | Whitelist targetType |
| Trả 403 trước khi CSRF được kiểm soát trong test | Không biết 403 do đâu | Test với và không với `csrf()` |
| Chỉ kiểm quyền trước UPDATE, không kiểm lại khi ghi | TOCTOU nếu dữ liệu thay đổi | Atomic conditional UPDATE/transaction |
| Gọi evaluator cho từng record của list rất lớn | N+1 queries, quá tải DB | Scope query tại DB + pagination |
| Cache kết quả theo documentId duy nhất | Quyền alice có thể cấp cho bob | Key/expiry/version đúng, hoặc bỏ cache |
| Dùng @PostAuthorize cho write rồi chờ rollback | Side effect đã xảy ra | Preauthorization + policy trong mutation |
| Test chỉ admin happy path, không cross-tenant/locked | Bỏ lọt leo thang quyền | Negative test matrix |
| Nuốt lỗi DB rồi cho phép truy cập | Fail open | Fail closed, error handling và alert |
| Nhầm object overload với ID overload | Method expression không đúng policy | Test cả hai chữ ký |

## 14. Ma trận kiểm thử cần có ở production

Với cùng chính sách của project demo:

| Caller | read #1 (alice/a) | read #2 (bob/a) | read #3 (charlie/b) | write #1 | write #4 locked |
| --- | --- | --- | --- | --- | --- |
| alice / tenant-a | 200 | 403 | 403 | cho phép nếu CSRF hợp lệ | 403 |
| bob / tenant-a | 403 | 200 | 403 | 403 | 403 |
| manager / tenant-a | 200 | 200 | 403 | 403 | 403 |
| charlie / tenant-b | 403 | 403 | 200 | 403 | 403 |
| Anonymous | 401 | 401 | 401 | 401 hoặc CSRF 403 | 401 hoặc CSRF 403 |

Đối với **GET** của demo, anonymous vào `/api/**` nhận 401 khi dùng Basic. Đối với **PUT**, CSRF có thể xử lý trước HTTP authentication/authorization, nên một request anonymous thiếu CSRF có thể nhận 403 thay vì 401. Bảng ghi rõ điều kiện đó để tránh test viết giả định quá mức.

Ngoài các hàng trên, cần:
- ID không tồn tại.
- Target object null/wrong type.
- Permission sai chữ hoa/thường hoặc chưa khai báo.
- User có role đúng nhưng **khác tenant**.
- Resource locked, deleted, archived hoặc đang chờ duyệt.
- Revoked membership/owner changed giữa request và commit.
- Multiple identities/roles trong một tenant.
- Bad/missing JWT/session và session timeout.
- Các đường gọi khác ngoài controller (scheduler, messaging).
- Race khi nhiều request cùng update một object.
- Pagination, batch list/export và kiểm quyền theo tập lớn.
- Log và error body không tiết lộ dữ liệu chưa được phép.
- Method-security proxy có chạy đúng trên bean thực, không bypass qua self-invocation.

## 15. Tình huống nâng cao

### 15.1. Có cần ACL framework không?

Spring Security còn có các thành phần liên quan ACL (access control lists) cho quyền per-object trong một số stack/phiên bản. `PermissionEvaluator` là interface để bạn tùy biến; bạn **không bắt buộc phải cài Spring Security ACL** để dùng `hasPermission`. Với hệ thống cần chia sẻ tài liệu từng user/team, một ACL/permission table có thể phù hợp, nhưng phải quản lý migrations, indexes, revoke, tenant scope và semantics permission.

### 15.2. RoleHierarchy có thay PermissionEvaluator không?

Không. `RoleHierarchy` mô tả **vai trò nào bao gồm vai trò nào**, ví dụ ADMIN > MANAGER > USER tại các điểm kiểm được cấu hình. `PermissionEvaluator` quyết định **user hiện tại có được làm action X trên object Y không**. Chúng có thể kết hợp: evaluator dùng authority đã được mở rộng hoặc một policy service riêng, nhưng phải cấu hình nhất quán, không tự coi ADMIN mặc định có mọi permission trên mọi tenant.

### 15.3. JWT claims có cần mapping thành GrantedAuthorities?

Nếu API dùng JWT, resource server phải xác minh token và ánh xạ scopes/roles thành authorities đáng tin. Evaluator có thể xét thêm tenant membership từ DB. Không chấp nhận payload JWT chưa xác minh hoặc trường role nằm trong một HTTP header tự khai. JWT có thể chứa quyền stale sau khi role bị thu hồi; cần chiến lược token expiry, revocation hoặc policy lookup tại thời điểm request.

### 15.4. Permission object là chuỗi hay enum?

Interface chấp nhận `Object permission` nên bạn có thể dùng chuỗi hoặc enum theo chính sách. Với SpEL `'read'` là String. Nếu dùng enum, cần expression tham chiếu đúng enum constant và kiểm type. Đừng implicit convert một object lạ thành chuỗi rồi cho phép action sai; test strictness.

### 15.5. Khi nào chọn custom AuthorizationManager thay vì PermissionEvaluator?

Khi policy dùng toàn bộ request context (HTTP method, route, request attributes), bạn có thể dùng custom `AuthorizationManager<RequestAuthorizationContext>`. Khi policy gắn với method arguments hoặc returnObject qua SpEL, `PermissionEvaluator` là một lựa chọn tự nhiên.

Một service policy thuần Java có thể được gọi từ cả hai cơ chế, giúp giảm duplicate logic. Nên đặt quyết định owner/tenant/state trong domain policy được test độc lập thay vì duplicate trong controller, evaluator, gateway, repository.

### 15.6. Filter tập lớn có dùng hasPermission từng phần tử được không?

Ví dụ `@PostFilter("hasPermission(filterObject, 'read')")` có thể lọc một collection nhỏ sau method. Nhưng với hàng chục nghìn/hàng triệu records, làm vậy dễ tạo N+1 permission lookups và page/count sai. **Đưa điều kiện quyền vào query trước khi phân trang**, hoặc dùng bulk permission lookup với thiết kế rõ ràng, không lấy toàn bảng rồi postfilter.

## 16. Checklist triển khai

1. Định nghĩa actions `read/write/delete/approve` và semantics rõ ràng theo object type.
2. Tách role/global authority và quyền resource-level theo owner/tenant/workflow.
3. Kiểm Authentication qua provider/token verifier đáng tin; không tin header client tự khai.
4. Thiết lập `@EnableMethodSecurity` và expression handler thực sự dùng custom PermissionEvaluator.
5. Phân biệt overload object và ID/type, test đúng chữ ký, null, unknown type/permission.
6. Chỉ dựa trên canonical resource/tenant membership từ server.
7. Dùng `@PreAuthorize`/query scoped để tránh đọc dữ liệu ngoài quyền nếu có thể.
8. Không xem `@PostAuthorize` là cơ chế hoàn tác side effects.
9. Với update/delete, kiểm điều kiện quyền trong chính transaction hoặc atomic SQL.
10. Kiểm CSRF riêng với cookie-based requests; phân biệt 401, 403, 404 theo mechanism.
11. Kiểm thử owner, non-owner, manager same tenant, manager cross tenant, locked, missing ID.
12. Kiểm tra self-invocation, final/private method và các entry point ngoài MVC.
13. Tối ưu query theo tenant/owner/ACL, tránh N+1 trên list lớn.
14. Không cache quyền thiếu principal/tenant/action và policy/resource version.
15. Audit cẩn thận, không lộ tokens, session IDs, mật khẩu hoặc metadata resource chưa được phép.
16. Khi quyền thay đổi, có chiến lược invalidation/re-authentication và kiểm tra multi-instance.

## 17. Câu hỏi tự kiểm tra

**Câu 1. `PermissionEvaluator` dùng để làm gì?**

Trả lời: là điểm mở rộng đánh giá quyền của một Authentication trên đối tượng cụ thể hoặc ID/type cho một hành động; thường qua SpEL `hasPermission` trong method security.

**Câu 2. Hai overload khác nhau thế nào?**

Trả lời: một overload nhận target object, overload kia nhận `Serializable targetId` + `String targetType`. Biểu thức hai hay ba đối số của `hasPermission` (không kể Authentication nội bộ) xác định overload tương ứng.

**Câu 3. `hasPermission(#p0, 'Document', 'read')` sẽ gọi overload nào?**

Trả lời: overload ID/type/action. Nếu tham số đầu tiên là long, evaluator thường nhận boxed Long.

**Câu 4. Vì sao không nên tin owner field trên JSON client?**

Trả lời: client có thể tự sửa field, khiến policy cấp quyền sai. Phải đọc owner/tenant canonical từ DB hoặc trusted store.

**Câu 5. Một manager tenant A có được đọc mọi document tenant B không?**

Trả lời: không theo policy demo. Tenant membership được kiểm trước role; role manager có phạm vi tenant.

**Câu 6. Khi evaluator trả false trước method, method body có chạy không?**

Trả lời: không trong lời gọi được method-security proxy kiểm soát bởi `@PreAuthorize`. Nếu self-invocation bypass proxy, annotation có thể không chạy.

**Câu 7. `@PostAuthorize` có bảo vệ DB khỏi việc đọc dữ liệu trước check không?**

Trả lời: không. Method body đã chạy; chỉ sau đó expression dựa trên `returnObject` mới được đánh giá.

**Câu 8. Có `@Component PermissionEvaluator` đã đủ chưa?**

Trả lời: không nên giả định. Phải xác minh expression handler có dùng evaluator đó và có bật method security; project demo nối bằng static `@Bean MethodSecurityExpressionHandler`.

**Câu 9. Vì sao unknown permission cần deny by default?**

Trả lời: nếu một hành động mới tự được permit, có thể tạo privilege escalation không được thiết kế/review.

**Câu 10. Vì sao HTTP role check không thay object authorization?**

Trả lời: role xác nhận chức năng chung, không biết owner/tenant/locked của từng resource ID.

**Câu 11. Tại sao thiếu CSRF trên PUT có thể nhận 403 dù evaluator cho phép write?**

Trả lời: CSRF filter có thể chặn trước khi method security chạy. Hai lớp bảo vệ độc lập.

**Câu 12. Vì sao PermissionEvaluator có thể tạo N+1 queries?**

Trả lời: khi gọi evaluator cho từng phần tử của list, mỗi lần có thể query metadata/ACL riêng; cần scope query, batch lookup và pagination đúng.

**Câu 13. TOCTOU là gì trong object authorization?**

Trả lời: quyền được kiểm ở thời điểm trước, còn owner/tenant/locked có thể thay đổi trước lúc ghi. Cần transaction, lock hoặc conditional UPDATE kiểm lại điều kiện khi mutation thực hiện.

**Câu 14. Trả 403 hay 404 cho ID không tồn tại?**

Trả lời: phụ thuộc hợp đồng và chính sách hạn chế tiết lộ thông tin; demo dùng 403 theo fail-closed evaluator, production có thể dùng 404 nhất quán.

**Câu 15. PermissionEvaluator có tự thu hồi JWT/session khi role bị đổi không?**

Trả lời: không. Cần token/session expiry, revocation, policy lookup hoặc cơ chế bảo đảm quyền mới có hiệu lực.

**Câu 16. Nếu frontend ẩn nút Delete, backend đã an toàn chưa?**

Trả lời: chưa. Client có thể tự gọi API. Server vẫn phải đánh giá quyền delete trên resource cụ thể và không cho phép permission không khai báo.

**Câu 17. Nếu muốn phân quyền theo tenant và owner trên hàng triệu records, có nên postfilter mọi record bằng hasPermission không?**

Trả lời: không. Dùng query/database row-level restrictions đã scope, count và pagination theo tập có quyền; method permission checks chỉ là lớp bổ sung.

**Ghi nhớ:** **`PermissionEvaluator` biến `hasPermission` thành kiểm tra quyền thao tác trên từng resource. Hai overload nhận object hoặc ID/type; cả hai phải dựa trên Authentication đã xác minh và dữ liệu resource/tenant đáng tin. Kết nối đúng với method-security handler, mặc định deny khi không xác định, kiểm lại trong mutation và dùng query scoped cho dữ liệu lớn.**