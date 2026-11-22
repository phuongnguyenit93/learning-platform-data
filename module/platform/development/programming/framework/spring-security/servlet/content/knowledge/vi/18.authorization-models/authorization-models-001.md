# GrantedAuthority, vai trò và quyền thao tác trong mô hình nghiệp vụ

> **Phạm vi:** Spring Security **Servlet** 6.x, Java 17+, phân quyền dựa trên `Authentication.getAuthorities()`. Bài giải thích cách `GrantedAuthority` biểu diễn **vai trò (role)** và **quyền thao tác (permission)**, cách thiết kế bảng ánh xạ vai trò → quyền, xử lý tiền tố `ROLE_`, phân quyền ở URL và service với `@PreAuthorize`, và ranh giới giữa quyền thao tác với quyền sở hữu dữ liệu. Một ứng dụng Spring Boot 3.3.5 chạy được minh họa cả GET và POST được bảo vệ bằng CSRF.

## 1. Bài toán nghiệp vụ: “người dùng là ai” khác “người dùng được làm gì”

Giả sử hệ thống quản lý đơn hàng có các nhóm nhân sự:

- **Nhân viên vận hành:** xem đơn hàng, nhưng không tự động được phê duyệt.
- **Người phê duyệt:** có thể xem và duyệt đơn.
- **Kiểm toán viên:** xem báo cáo kiểm toán, không mặc nhiên duyệt đơn.
- **Quản trị viên:** quản lý cấu hình nhạy cảm và có thể được cấp các quyền thao tác cần thiết.
- **Nhân viên được ủy quyền tạm thời:** tuy giữ vai trò nhân viên, được cấp thêm quyền duyệt trong phạm vi hợp lệ.

Nếu chỉ hỏi “user đã đăng nhập chưa?” thì mọi người đều có thể làm cùng một việc, không đúng chính sách. Nếu chỉ hỏi “có role ADMIN không?” thì các thao tác thường ngày như xem đơn, duyệt đơn hay xem audit lại bị trộn vào một vai trò quá rộng.

Tách các lớp khái niệm:

```text
Identity / Authentication
  "Tài khoản đã được kiểm chứng là ai?"
             |
             v
Role / Nhóm trách nhiệm
  "Người này thuộc nhóm công việc nào?"
             |
             v
Permission / Quyền thao tác
  "Người này được phép thực hiện hành động nào?"
             |
             v
Resource-level policy / Quyền theo đối tượng
  "Có được làm hành động này trên CHÍNH đơn hàng #42 không?"
             |
             v
Domain invariant
  "Đơn #42 có đang ở trạng thái hợp lệ để phê duyệt không?"
```

Spring Security đưa các role và permission ở tầng ứng dụng vào `Collection<? extends GrantedAuthority>` của `Authentication`, sau đó các authorization rules so sánh chúng. Để kiểm tra chủ sở hữu, chi nhánh, tenant hoặc trạng thái đơn hàng, ứng dụng còn cần logic nghiệp vụ dựa trên **dữ liệu server đáng tin cậy**.

**Bốn câu hỏi phải trả lời riêng:** danh tính là ai, role là gì, có permission gì, có quyền trên resource cụ thể này không. Tránh gộp tất cả thành một `isAdmin` Boolean.

## 2. GrantedAuthority chính xác là gì?

`GrantedAuthority` là interface của Spring Security đại diện cho **một quyền/đặc tính phân quyền đã được cấp** cho `Authentication`. Ở mô hình thường gặp, mỗi authority là một chuỗi.

```java
package org.springframework.security.core;

import java.io.Serializable;

public interface GrantedAuthority extends Serializable {
    String getAuthority();
}
```

Trên đây là chữ ký cô đọng của interface để học khái niệm; Spring Security đã định nghĩa sẵn, **không tạo lại file này trong dự án**.

Implementation phổ biến:

```java
import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.core.authority.SimpleGrantedAuthority;

GrantedAuthority role = new SimpleGrantedAuthority("ROLE_STAFF");
GrantedAuthority permission = new SimpleGrantedAuthority("ORDER_READ");

System.out.println(role.getAuthority());
System.out.println(permission.getAuthority());
```

Kết quả khi chạy fragment trong một chương trình Java có đúng các imports và classpath:

```text
ROLE_STAFF
ORDER_READ
```

**`SimpleGrantedAuthority` không có cờ riêng** để nói “đây là role” hoặc “đây là permission”. Cả hai đều là `GrantedAuthority` chứa một chuỗi. Sự khác biệt đến từ **quy ước đặt tên và quy tắc ứng dụng**. `ROLE_STAFF` thường được xem là vai trò vì tiền tố `ROLE_`; `ORDER_READ` là quyền thao tác do nhóm phát triển định nghĩa.

Có implementation `GrantedAuthority` phức tạp có thể không biểu diễn bằng chuỗi duy nhất và `getAuthority()` có thể trả `null`. Khi dùng `hasAuthority("...")` với `SimpleGrantedAuthority`, hãy dựa trên chuỗi không null và **so khớp chính xác**, không giả định mọi authority tùy chỉnh đều có semantics giống nhau.

### Authority nằm ở đâu?

Sau một lần authentication thành công, `Authentication` thường có:

- `getPrincipal()`: danh tính, chẳng hạn `UserDetails` hoặc principal từ token.
- `getAuthorities()`: tập `GrantedAuthority` đã được gán/mapping theo nguồn tin cậy.
- `getCredentials()`: dữ liệu xác thực (có thể đã được xóa để bảo mật).
- `isAuthenticated()`: trạng thái xác thực.

```java
Authentication authentication =
        SecurityContextHolder.getContext().getAuthentication();

if (authentication != null) {
    for (GrantedAuthority authority : authentication.getAuthorities()) {
        System.out.println(authority.getAuthority());
    }
}
```

Đây là **fragment Java** cần imports tương ứng. Trong ứng dụng thật không nên ghi toàn bộ `Authentication`, credentials hay thông tin cá nhân vào log. Việc xem danh sách authorities có thể hữu ích trong development nhưng phải kiểm soát hiển thị khi có dữ liệu nhạy cảm.

**Ai cấp `GrantedAuthority`?** `UserDetailsService`, authentication provider, JWT/OIDC claims converter hoặc mapping do hệ thống tin cậy thực hiện. Client **không được tự gửi `roles=["ROLE_ADMIN"]` để server coi đó là quyền hợp lệ**.

## 3. Role, permission và resource policy khác nhau ra sao?

| Khái niệm | Ví dụ | Ý nghĩa | Có đủ để cho phép hành động không? |
| --- | --- | --- | --- |
| **Role** | `ROLE_STAFF`, `ROLE_APPROVER` | Vai trò công việc hoặc nhóm trách nhiệm | Chưa chắc; cần biết role có quyền gì |
| **Permission** | `ORDER_READ`, `ORDER_APPROVE`, `AUDIT_READ` | Khả năng thực hiện một loại thao tác | Chưa chắc; có thể còn ràng buộc resource |
| **Resource ownership** | User là người phụ trách order `42` | Quyền gắn với đối tượng cụ thể | Cần kiểm tra từ nguồn dữ liệu tin cậy |
| **Tenant scope** | User thuộc tenant `acme` | Biên giới dữ liệu đa khách hàng | Phải ràng buộc với dữ liệu request và principal |
| **Domain state** | Đơn hàng ở trạng thái `PENDING` | Tiền điều kiện của hành động | Không thay cho permission |
| **Authentication** | User đã đăng nhập | Xác nhận danh tính | Không tự động cấp mọi quyền |

Ví dụ quy tắc phê duyệt:

```text
ALLOW_APPROVE(orderId, user) =
    user is authenticated
    AND user has authority ORDER_APPROVE
    AND order belongs to an allowed tenant/business unit
    AND user is permitted to approve this specific order
    AND order.status == PENDING
```

Ở đây `ORDER_APPROVE` là **quyền chức năng**; tenant, owner/assignee và trạng thái đơn là **điều kiện nghiệp vụ theo dữ liệu**. Không nên chỉ thêm `ROLE_ADMIN` rồi bỏ qua đối chiếu tenant nếu sản phẩm có yêu cầu tách tenant.

### RBAC và permission-based access

- **RBAC (Role-Based Access Control):** phân quyền dựa trên vai trò. “Auditor có quyền đọc audit”. Thường người dùng gắn role, role chứa tập permission.
- **Permission-based:** rule kiểm tra quyền thao tác, ví dụ `hasAuthority("ORDER_APPROVE")`, không cần quan tâm user đến từ role nào. Một permission có thể được cấp bởi nhiều role hoặc ủy quyền trực tiếp.
- **ABAC / policy theo thuộc tính:** kết hợp vai trò/quyền với thuộc tính người dùng, tài nguyên, tổ chức, thời gian, trạng thái. Đây không phải loại `GrantedAuthority` tự động xử lý; cần authorization manager hoặc domain service phù hợp.

Thiết kế thực tế thường **kết hợp**: dùng role để quản trị nhóm người dùng, dịch role thành các permission rõ nghĩa, rồi bảo vệ endpoint/service bằng permission và kiểm tra scope/resource sâu hơn.

## 4. Tiền tố ROLE_: quy ước nhỏ nhưng ảnh hưởng lớn

Spring Security thường dùng quy ước role có tiền tố `ROLE_`. Các biểu thức:

```java
// Ba ví dụ fragment trong authorizeHttpRequests:
auth.requestMatchers("/admin").hasRole("ADMIN");
auth.requestMatchers("/admin-by-authority").hasAuthority("ROLE_ADMIN");
auth.requestMatchers("/orders").hasAuthority("ORDER_READ");
```

Với **role prefix mặc định**, hai rule đầu cùng yêu cầu authority chuỗi `ROLE_ADMIN`, còn rule thứ ba yêu cầu `ORDER_READ`.

| Rule | Chuỗi GrantedAuthority kỳ vọng |
| --- | --- |
| `hasRole("ADMIN")` | `ROLE_ADMIN` |
| `hasAuthority("ROLE_ADMIN")` | `ROLE_ADMIN` |
| `hasAuthority("ADMIN")` | `ADMIN` |
| `hasAuthority("ORDER_READ")` | `ORDER_READ` |
| `hasRole("ORDER_READ")` | `ROLE_ORDER_READ`, **không giống** `ORDER_READ` |

Lỗi phổ biến: user store lưu `ADMIN`, nhưng code dùng `hasRole("ADMIN")`; kết quả là 403 vì framework tìm `ROLE_ADMIN`. Hoặc developer viết `hasAuthority("ADMIN")` trong khi `User.withUsername(...).roles("ADMIN")` tạo `ROLE_ADMIN`.

### roles() và authorities() trong User builder

```java
// Fragment - hai cách diễn đạt khác nhau:
UserDetails fromRoles = User.withUsername("mai")
        .password("{noop}local-only")
        .roles("STAFF")
        .build();

UserDetails fromAuthorities = User.withUsername("mai")
        .password("{noop}local-only")
        .authorities("ROLE_STAFF", "ORDER_READ")
        .build();
```

- `.roles("STAFF")` tạo authority `ROLE_STAFF` theo convention của builder.
- `.authorities("ROLE_STAFF","ORDER_READ")` thêm **chính xác** hai chuỗi được truyền.
- `.roles("ROLE_STAFF")` thường là cách dùng sai vì `.roles()` không mong đầu vào đã có prefix `ROLE_`.
- Mật khẩu `{noop}local-only` ở fragment chỉ giải thích cú pháp builder; ứng dụng mẫu chạy ở mục 9 sử dụng BCrypt. **Không lưu mật khẩu plaintext/`{noop}` ở production.**

**Có thể tùy chỉnh role prefix** ở một số điểm cấu hình/authorization infrastructure, nhưng không tự giả định mọi API, method security và third-party integration sử dụng prefix đã đổi giống nhau. Nếu thay prefix mặc định, kiểm thử nhất quán cả URL rules, method rules và token converters. Một cách đơn giản để giảm nhầm lẫn là dùng `hasAuthority("ROLE_ADMIN")` hoặc dùng `hasRole("ADMIN")` theo quy ước và lưu `ROLE_ADMIN` thống nhất.

## 5. Thiết kế danh mục quyền thao tác theo nghiệp vụ

Tên permission tốt nên biểu đạt **resource/action**, ổn định và không phụ thuộc giao diện:

| Permission | Ý nghĩa | API/operation tiêu biểu |
| --- | --- | --- |
| `ORDER_READ` | Đọc thông tin đơn | `GET /api/orders/{id}` |
| `ORDER_CREATE` | Tạo đơn mới | `POST /api/orders` |
| `ORDER_UPDATE` | Sửa thông tin đơn | `PUT /api/orders/{id}` |
| `ORDER_APPROVE` | Phê duyệt đơn | `POST /api/orders/{id}/approve` |
| `ORDER_CANCEL` | Hủy đơn | `POST /api/orders/{id}/cancel` |
| `AUDIT_READ` | Đọc dấu vết kiểm toán | `GET /api/audit` |
| `REPORT_EXPORT` | Xuất báo cáo | `POST /api/reports/export` |
| `USER_MANAGE` | Quản lý tài khoản | Endpoint quản trị người dùng |

**Không nhầm HTTP method với quyền nghiệp vụ.** `POST` chỉ nói yêu cầu có thể tạo/tác động đến state, không tự xác định “đây là approve”. `ORDER_APPROVE` thể hiện hành động được phép; mapping HTTP route đến permission là chính sách ứng dụng.

Dùng tên nhất quán như `RESOURCE_ACTION` và có tài liệu mô tả nghĩa. Tránh:

- `CAN_DO_EVERYTHING` không có phạm vi rõ ràng.
- `BUTTON_APPROVE_VISIBLE` phụ thuộc chi tiết UI.
- Một permission quá rộng `ORDER_WRITE` bao gồm cả sửa, xóa, hoàn tiền và duyệt.
- Gắn hành động chuyển tiền hoặc thay thông tin nhạy cảm vào role admin mà không có bước kiểm soát cần thiết.
- Nhét tenant ID hoặc order ID vào tên authority cho mọi resource, tạo số lượng authority không kiểm soát; với quyền theo resource động, kiểm tra server-side sẽ phù hợp hơn.

### Phân quyền backend khác ẩn/hiện nút trên frontend

Frontend có thể ẩn nút “Approve” khi user không có `ORDER_APPROVE`, nhưng ẩn nút **không phải authorization**. Client có thể tự gửi request `POST`. Backend phải kiểm tra permission ở tầng HTTP hoặc service và áp dụng điều kiện nghiệp vụ với order cụ thể.

Một UI có thể gọi endpoint `GET /api/me` để hiển thị quyền của user, nhưng dữ liệu phản hồi chỉ dành cho trải nghiệm, không phải nơi cấp quyền. Nguồn truth là authentication/authorization phía server và policy có thể thay đổi theo thời gian.

## 6. Role → Permission: một mô hình dễ bảo trì

Ví dụ ánh xạ role với permission:

| Vai trò | Các permission thường được cấp |
| --- | --- |
| `ROLE_STAFF` | `ORDER_READ`, có thể `ORDER_UPDATE` trong phạm vi được giao |
| `ROLE_APPROVER` | `ORDER_READ`, `ORDER_APPROVE` |
| `ROLE_AUDITOR` | `AUDIT_READ` |
| `ROLE_ADMIN` | `ORDER_READ`, `ORDER_APPROVE`, `AUDIT_READ`, và các quyền thực sự được duyệt |
| Ủy quyền bổ sung cho một user | Permission riêng có thời hạn/phạm vi, không nhất thiết đổi role gốc |

Đây là **thiết kế mẫu**, không phải Spring Security tự biết `ROLE_APPROVER` kéo theo `ORDER_APPROVE`. Nếu `Authentication` chỉ chứa `ROLE_APPROVER`, rule `hasAuthority("ORDER_APPROVE")` **không tự thành công**. Hệ thống phải:

1. Lưu một bảng role–permission ở database hoặc cấu hình nguồn tin cậy.
2. Khi user được xác thực, tổng hợp các permission từ roles và quyền trực tiếp.
3. Chuyển kết quả thành `GrantedAuthority` thực tế của `Authentication`.
4. Áp dụng `hasAuthority(...)` hoặc `@PreAuthorize(...)` ở server.
5. Có chính sách làm mới/thu hồi authorities khi role/permission thay đổi.

Mô hình dữ liệu quan hệ tham khảo:

```text
users(id, username, password_hash, active)
roles(id, code)                          -- STAFF, APPROVER, AUDITOR
permissions(id, code)                   -- ORDER_READ, ORDER_APPROVE
user_roles(user_id, role_id)
role_permissions(role_id, permission_id)
user_permissions(user_id, permission_id, expires_at)  -- tùy nhu cầu

Một user có thể có nhiều roles.
Một role có thể có nhiều permissions.
Một permission có thể đến từ nhiều roles.
Quyền trực tiếp có thể cần expires_at và audit.
```

Lược đồ trên là **minh họa mô hình**, không phải migration SQL hoàn chỉnh. Production cần unique constraints, khóa ngoại, tenant scoping, phân quyền thay đổi role, audit và xử lý thu hồi. Đặc biệt, **quyền cấp quyền** phải được bảo vệ chặt để không trở thành lối leo thang đặc quyền.

### Tại điểm nào map roles thành authorities?

Tùy cách authentication:

- **Username/password + UserDetailsService:** sau khi tìm user và đọc role/permissions từ database, trả `UserDetails` có authorities được cấp.
- **OIDC/OAuth2 login:** xác minh danh tính trước, sau đó map claims/groups từ nguồn đáng tin sang authorities ứng dụng; không tin claim chưa được kiểm chứng.
- **JWT resource server:** decoder/validator phải xác minh chữ ký, issuer, audience, expiry trước khi converter chuyển scopes/roles thành authorities.
- **External authorization service:** có thể dùng một `AuthorizationManager` hỏi policy service ở mỗi request; cần kiểm soát latency, cache, fail-closed, kiểm toán và dữ liệu tin cậy.

Đừng đưa quyền từ JWT chưa kiểm chứng hoặc HTTP header tùy ý vào `Authentication`. Với JWT scope, Spring Security Resource Server thường dùng tiền tố `SCOPE_` cho scopes, khác với convention `ROLE_`; điều này cần được mapping có chủ đích.

## 7. Phân quyền URL và phân quyền method/service

Spring Security Servlet cho phép bảo vệ HTTP routes bằng:

```java
http.authorizeHttpRequests(auth -> auth
        .requestMatchers(HttpMethod.GET, "/api/orders/{id}")
            .hasAuthority("ORDER_READ")
        .requestMatchers(HttpMethod.POST, "/api/orders/{id}/approve")
            .hasAuthority("ORDER_APPROVE")
        .requestMatchers(HttpMethod.GET, "/api/admin/health")
            .hasRole("ADMIN")
        .anyRequest().denyAll());
```

Đây là **fragment** trong một `SecurityFilterChain`. Khi URL khớp rule, `AuthorizationFilter` đánh giá `Authentication.getAuthorities()`. `hasAuthority` so chuỗi chính xác; `hasRole` theo convention role prefix.

**Tại sao thêm method security?** Trong ứng dụng lớn, service có thể được gọi từ HTTP controller, background job, GraphQL handler hoặc code khác. Nếu hành động duyệt đơn chỉ bảo vệ ở URL, một entrypoint khác gọi service có thể vượt qua chính sách. Khi bật `@EnableMethodSecurity`, đặt `@PreAuthorize` ở method xử lý nghiệp vụ là một lớp kiểm tra hữu ích:

```java
@PreAuthorize("hasAuthority('ORDER_APPROVE')")
public OrderView approve(long id) {
    // Logic domain cần kiểm tra trạng thái và ownership trong service.
}
```

Fragment chỉ minh họa annotation; method chạy được trong service đầy đủ ở mục 9. Một `@PreAuthorize` trên Spring bean được gọi **qua proxy Spring**; tự gọi method trong cùng object (`this.approve(...)`) có thể bỏ qua proxy và không kích hoạt method-security advice. Dùng service bean từ controller hoặc kiến trúc phù hợp.

### Quy tắc nhiều lớp không nên mâu thuẫn

Nếu URL yêu cầu `ORDER_APPROVE`, method cũng yêu cầu `ORDER_APPROVE`, sự lặp lại là **defense in depth**. Nhưng nếu URL cấp rộng hơn service thì request đi qua filter nhưng vẫn bị method chặn (thường 403 với user authenticated). Cần test HTTP và method-level policy đồng bộ, tránh thông điệp lỗi mơ hồ.

Nếu method security được dùng cho service không có HTTP request, hãy hiểu authentication context cần được cung cấp an toàn trong tác vụ đó. Không cho background job tự nhận admin quyền không kiểm soát để “tránh 403”.

## 8. Quyền thao tác chưa đủ: kiểm tra resource và tenant

Giả sử user có `ORDER_READ` nhưng chỉ được xem đơn thuộc chi nhánh của mình:

```text
HTTP GET /api/orders/42
    |
    v
Authentication chứa ORDER_READ
    |
    v
HTTP authorization cho qua
    |
    v
OrderService kiểm tra orderId=42
    |
    +-- Tải đơn thật từ database
    +-- Xác định tenant/branch/owner của đơn
    +-- So với phạm vi quyền tin cậy của user
    |
    +-- Đúng: trả dữ liệu
    +-- Sai: từ chối (403) hoặc 404 theo chính sách tiết lộ resource
```

Đây là ranh giới quan trọng để ngăn **IDOR/BOLA (Broken Object Level Authorization)**. `hasAuthority("ORDER_READ")` chỉ biết người dùng có một loại quyền; nó **không biết** đơn 42 thuộc tenant nào, khách hàng nào hoặc đã bị khóa dữ liệu hay chưa.

Một cách diễn đạt policy:

```text
CAN_READ_ORDER(authentication, orderId) =
    hasAuthority(authentication, "ORDER_READ")
    AND orderRepository.findById(orderId).tenantId
        IN trustedAllowedTenants(authentication)
```

Đây là pseudo-code, không phải cú pháp Spring Expression Language hoàn chỉnh. Trong code thật, chỉ sử dụng `tenantId` lấy từ principal/permission store/server-side memberships; không dùng riêng `X-Tenant-Id` do client tự khai để quyết định quyền.

### Custom bean trong @PreAuthorize

Một pattern có thể dùng:

```java
// Fragment minh họa ý tưởng, yêu cầu bean orderPolicy thật:
@PreAuthorize("hasAuthority('ORDER_READ') and @orderPolicy.canRead(authentication, #id)")
public OrderDetails loadOrder(long id) {
    return repository.findDetails(id);
}
```

`orderPolicy.canRead`, `OrderDetails` và `repository` là phần ứng dụng cần triển khai. Phải đảm bảo Spring Security có thể resolve tên tham số method `id` (hoặc dùng annotation `@P("id")`/cấu hình metadata khi cần), kiểm tra ownership bằng dữ liệu server và không mắc lỗi N+1 query.

**Đối với thao tác ghi**, cần xét thêm domain invariant: order phải ở trạng thái `PENDING`, user không được tự duyệt đơn do chính mình tạo nếu có chính sách separation of duties, có thể cần two-person approval. Một check ở HTTP filter không thể tự đảm bảo trạng thái tài nguyên vẫn hợp lệ tới lúc transaction commit.

### TOCTOU: quyền và trạng thái có thể đổi

Trong môi trường đồng thời, order status hoặc người phụ trách có thể đổi sau khi authorization filter đã check. Dùng transaction, optimistic locking, conditional update (ví dụ chỉ update khi status còn PENDING), và kiểm tra domain-level trong service để tránh **time-of-check/time-of-use**. `GrantedAuthority` không tự khóa database record.

## 9. Ví dụ chạy được: Java 17 + Spring Security 6 + Spring Boot 3.3.5

Ứng dụng Servlet dưới đây dùng HTTP Basic để dễ kiểm tra identity/authorities và có POST phê duyệt đơn. **Để không dạy sai về CSRF**, demo giữ CSRF protection ngay cả với Basic, và cung cấp endpoint GET cấp token để HTTP client có thể gọi POST kèm cookie + header CSRF hợp lệ.

### Endpoints và policy

| Method + URL | HTTP authorization | Service authorization | Kết quả |
| --- | --- | --- | --- |
| `GET /api/hello` | `permitAll()` | Không cần | Public message |
| `GET /api/csrf` | `permitAll()` | Không cần | CSRF token cho POST |
| `GET /api/me` | `authenticated()` | Không cần | User + danh sách authorities |
| `GET /api/orders/{id}` | `ORDER_READ` | `ORDER_READ` | Order data |
| `POST /api/orders/{id}/approve` | `ORDER_APPROVE` | `ORDER_APPROVE` | Chuyển trạng thái đơn demo |
| `GET /api/audit` | `AUDIT_READ` | Không cần | Audit demo message |
| `GET /api/admin/health` | `ROLE_ADMIN` qua `hasRole("ADMIN")` | Không cần | Admin-only message |

### User và authorities trong demo

| Username | Password demo | GrantedAuthority |
| --- | --- | --- |
| `mai` | `demo123` | `ROLE_STAFF`, `ORDER_READ` |
| `an` | `demo123` | `ROLE_APPROVER`, `ORDER_READ`, `ORDER_APPROVE` |
| `linh` | `demo123` | `ROLE_STAFF`, `ORDER_READ`, `ORDER_APPROVE` |
| `binh` | `demo123` | `ROLE_AUDITOR`, `AUDIT_READ` |
| `root` | `demo123` | `ROLE_ADMIN`, `ORDER_READ`, `ORDER_APPROVE`, `AUDIT_READ` |
| `guest` | `demo123` | `ROLE_GUEST` |

Người dùng `linh` minh họa **một user mang role STAFF nhưng được cấp thêm permission ORDER_APPROVE**. Vì rule kiểm tra permission, user này được phê duyệt dù không mang `ROLE_APPROVER`. Ứng dụng thực tế phải có quản trị/ghi log/giới hạn thời hạn cho việc ủy quyền như vậy.

### 9.1. Cấu trúc dự án

```text
authorities-demo/
├── pom.xml
├── src/main/java/example/authorities/
│   ├── AuthoritiesApplication.java
│   ├── SecurityConfig.java
│   ├── OrderService.java
│   └── ApiController.java
└── src/test/java/example/authorities/
    └── AuthorizationRulesTest.java
```

### 9.2. pom.xml

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.5</version>
        <relativePath/>
    </parent>
    <groupId>example</groupId>
    <artifactId>authorities-demo</artifactId>
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
```

### 9.3. AuthoritiesApplication.java

```java
package example.authorities;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class AuthoritiesApplication {
    public static void main(String[] args) {
        SpringApplication.run(AuthoritiesApplication.class, args);
    }
}
```

### 9.4. SecurityConfig.java

```java
package example.authorities;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configuration.EnableWebSecurity;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.csrf.CookieCsrfTokenRepository;
import org.springframework.security.web.savedrequest.NullRequestCache;

@Configuration
@EnableWebSecurity
@EnableMethodSecurity
public class SecurityConfig {

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    UserDetailsService users(PasswordEncoder encoder) {
        String hash = encoder.encode("demo123");

        return new InMemoryUserDetailsManager(
                User.withUsername("mai").password(hash)
                        .authorities("ROLE_STAFF", "ORDER_READ").build(),
                User.withUsername("an").password(hash)
                        .authorities("ROLE_APPROVER",
                                "ORDER_READ", "ORDER_APPROVE").build(),
                User.withUsername("linh").password(hash)
                        .authorities("ROLE_STAFF",
                                "ORDER_READ", "ORDER_APPROVE").build(),
                User.withUsername("binh").password(hash)
                        .authorities("ROLE_AUDITOR", "AUDIT_READ").build(),
                User.withUsername("root").password(hash)
                        .authorities("ROLE_ADMIN", "ORDER_READ",
                                "ORDER_APPROVE", "AUDIT_READ").build(),
                User.withUsername("guest").password(hash)
                        .authorities("ROLE_GUEST").build()
        );
    }

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
        http.authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET, "/api/hello").permitAll()
                .requestMatchers(HttpMethod.GET, "/api/csrf").permitAll()
                .requestMatchers(HttpMethod.GET, "/api/me").authenticated()
                .requestMatchers(HttpMethod.GET, "/api/orders/{id}")
                        .hasAuthority("ORDER_READ")
                .requestMatchers(HttpMethod.POST, "/api/orders/{id}/approve")
                        .hasAuthority("ORDER_APPROVE")
                .requestMatchers(HttpMethod.GET, "/api/audit")
                        .hasAuthority("AUDIT_READ")
                .requestMatchers(HttpMethod.GET, "/api/admin/health")
                        .hasRole("ADMIN")
                .anyRequest().denyAll()
        );

        http.httpBasic(Customizer.withDefaults());

        // Identity lấy từ credentials của request, không dựa vào web session.
        http.sessionManagement(session -> session
                .sessionCreationPolicy(SessionCreationPolicy.STATELESS));
        http.requestCache(cache ->
                cache.requestCache(new NullRequestCache()));

        // Không tắt CSRF cho HTTP Basic: browser có thể cache credentials.
        // Cookie lưu CSRF token; client lấy token từ GET /api/csrf,
        // rồi gửi cookie + header X-XSRF-TOKEN khi POST.
        http.csrf(csrf -> csrf.csrfTokenRepository(
                new CookieCsrfTokenRepository()));

        return http.build();
    }
}
```

**Đọc code:**

1. `@EnableMethodSecurity` cho phép Spring áp dụng `@PreAuthorize` trên service bean.
2. `UserDetailsService` trả cả role authorities (`ROLE_...`) lẫn operation permissions. Dùng một hash BCrypt cho các account demo là hợp lệ về mặt so password, nhưng tài khoản thật phải có password riêng, hash được lưu bền vững, và tuân thủ chính sách mật khẩu.
3. `hasAuthority("ORDER_APPROVE")` kiểm tra permission **chính xác**, không tự suy ra từ `ROLE_APPROVER`.
4. `hasRole("ADMIN")` dùng prefix `ROLE_` mặc định và chỉ cho phép account `root` ở đường dẫn quản trị demo.
5. `STATELESS` không lấy `SecurityContext` từ HTTP session; HTTP Basic dùng credentials mỗi request. Nó **không có nghĩa controller khác không thể tạo `HttpSession`**.
6. `CookieCsrfTokenRepository` là **cơ chế lưu CSRF token**, độc lập với việc lưu `SecurityContext`. Vì app demo có POST thay đổi trạng thái và Basic credentials có thể được browser tự gửi, ta giữ CSRF.
7. `NullRequestCache` hợp với API không dùng redirect trở lại form login. `anyRequest().denyAll()` là fail closed cho URL không định nghĩa.
8. Phần demo không có role hierarchy tự động và không có cơ sở dữ liệu thực: từng user được khai báo authorities cụ thể để thấy rõ policy.

### 9.5. OrderService.java

```java
package example.authorities;

import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;

import org.springframework.http.HttpStatus;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.stereotype.Service;
import org.springframework.web.server.ResponseStatusException;

@Service
public class OrderService {

    private final Map<Long, OrderView> orders = new ConcurrentHashMap<>();

    public OrderService() {
        orders.put(42L, new OrderView(42L, "PENDING"));
        orders.put(43L, new OrderView(43L, "PENDING"));
    }

    @PreAuthorize("hasAuthority('ORDER_READ')")
    public OrderView get(long id) {
        OrderView order = orders.get(id);
        if (order == null) {
            throw new ResponseStatusException(
                    HttpStatus.NOT_FOUND, "Order not found");
        }
        return order;
    }

    @PreAuthorize("hasAuthority('ORDER_APPROVE')")
    public OrderView approve(long id) {
        OrderView updated = orders.computeIfPresent(
                id, (key, oldValue) -> new OrderView(key, "APPROVED"));
        if (updated == null) {
            throw new ResponseStatusException(
                    HttpStatus.NOT_FOUND, "Order not found");
        }
        return updated;
    }

    public record OrderView(long id, String status) {
    }
}
```

**Giải thích:** Đây là kho đơn hàng **in-memory chỉ phục vụ thực hành**. `ConcurrentHashMap` giúp request demo cập nhật object tương đối an toàn trong một tiến trình; code **không kiểm tra tenant, người phụ trách, separation of duties hoặc các chuyển trạng thái phức tạp**. Production cần database, transaction và policy theo resource như mục 8. `@PreAuthorize` trên service là một lớp bảo vệ nữa: nếu một entrypoint khác gọi service qua Spring bean, rule permission vẫn được áp dụng.

Ở demo, `approve` chuyển cả đơn đã APPROVED thành APPROVED (idempotent ở mức trạng thái); production có thể từ chối phê duyệt lại, ghi audit và yêu cầu xác nhận nghiệp vụ.

### 9.6. ApiController.java

```java
package example.authorities;

import java.util.List;
import jakarta.servlet.http.HttpServletRequest;

import org.springframework.security.core.Authentication;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.web.csrf.CsrfToken;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class ApiController {

    private final OrderService orderService;

    public ApiController(OrderService orderService) {
        this.orderService = orderService;
    }

    @GetMapping("/api/hello")
    public String hello() {
        return "hello:public";
    }

    @GetMapping("/api/csrf")
    public String csrf(HttpServletRequest request) {
        CsrfToken token = (CsrfToken) request.getAttribute(
                CsrfToken.class.getName());
        if (token == null) {
            throw new IllegalStateException("CSRF token unavailable");
        }
        return token.getToken();
    }

    @GetMapping("/api/me")
    public MeView me(Authentication auth) {
        List<String> authorities = auth.getAuthorities().stream()
                .map(GrantedAuthority::getAuthority)
                .sorted()
                .toList();
        return new MeView(auth.getName(), authorities);
    }

    @GetMapping("/api/orders/{id}")
    public OrderService.OrderView order(@PathVariable long id) {
        return orderService.get(id);
    }

    @PostMapping("/api/orders/{id}/approve")
    public OrderService.OrderView approve(@PathVariable long id) {
        return orderService.approve(id);
    }

    @GetMapping("/api/audit")
    public String audit() {
        return "audit:ok";
    }

    @GetMapping("/api/admin/health")
    public String adminHealth() {
        return "admin:ok";
    }

    public record MeView(String user, List<String> authorities) {
    }
}
```

`GET /api/me` xuất danh sách authority có sắp xếp để dễ xem permission trong lab. Ở production, không nên công khai danh sách chi tiết quyền nhạy cảm nếu không có yêu cầu sản phẩm; endpoint này yêu cầu `authenticated()` và phải tuân theo chính sách API.

`GET /api/csrf` đọc CsrfToken từ request attribute do Spring Security cung cấp. Đọc `getToken()` sẽ khiến token được materialize trong flow, cho phép cookie repository gửi CSRF cookie tương ứng. Nếu thay request handler/token repository ở Spring Security, cần test lại cách lấy/gửi token.

### 9.7. Chạy project

Dùng JDK 17+, Maven 3.9+ trong thư mục có `pom.xml`:

```bash
mvn test
mvn spring-boot:run
```

Với cấu hình mặc định, ứng dụng lắng nghe tại `http://localhost:8080`. Lệnh curl bên dưới dành cho **localhost**; triển khai thật dùng **HTTPS**, bởi HTTP Basic gửi credentials có thể khôi phục từ Base64 và cookie CSRF không phải cơ chế mã hóa network.

## 10. Thực hành quyền READ, APPROVE, AUDIT và ROLE_ADMIN

### 10.1. Public endpoint

```bash
curl -s http://localhost:8080/api/hello
```

Body kỳ vọng:

```text
hello:public
```

Không có Basic header vẫn 200 do rule `permitAll()`. Tuy nhiên nếu client **chủ động gửi** Basic credentials sai ngay cả đến URL public, authentication filter vẫn có thể thử và gây 401 trước rule authorization.

### 10.2. Không có credentials tới endpoint cần login

```bash
curl -s -o /dev/null -w '%{http_code}\n' \
  http://localhost:8080/api/me
```

Kết quả kỳ vọng:

```text
401
```

Đây là **authentication thiếu**, chưa phải user đã xác thực mà thiếu permission.

### 10.3. User mai có ORDER_READ

```bash
curl -s -u mai:demo123 http://localhost:8080/api/orders/42
```

Body JSON kỳ vọng trước khi phê duyệt đơn:

```json
{"id":42,"status":"PENDING"}
```

`mai` có `ORDER_READ`, nên cả HTTP rule và `OrderService.get` đều cho phép. `mai` không có `ORDER_APPROVE`; không được gọi thành công endpoint duyệt.

### 10.4. Xem authorities của một user

```bash
curl -s -u linh:demo123 http://localhost:8080/api/me
```

Body JSON dự kiến:

```json
{"user":"linh","authorities":["ORDER_APPROVE","ORDER_READ","ROLE_STAFF"]}
```

Danh sách đã sắp xếp theo chuỗi. Trường hợp này minh họa permission trực tiếp `ORDER_APPROVE` được cấp cho role STAFF của user `linh` trong demo; không phải Spring Security tự suy ra permission từ `ROLE_STAFF`.

### 10.5. POST cần CSRF token đúng

Với CSRF protection trong project, lệnh sau **không** đủ:

```bash
curl -i -u an:demo123 -X POST \
  http://localhost:8080/api/orders/42/approve
```

Thiếu CSRF token, phản hồi thường **403** trước khi HTTP/method authorization cho phép thao tác.

Lấy token **và** lưu cookie bằng một request cùng origin:

```bash
csrf_token="$(curl -fsS -c csrf-cookies.txt \
  http://localhost:8080/api/csrf)"
```

Gửi cùng cookie và token qua header:

```bash
curl -i -u an:demo123 -b csrf-cookies.txt \
  -H "X-XSRF-TOKEN: $csrf_token" \
  -X POST http://localhost:8080/api/orders/42/approve
```

Response dự kiến có status **200** và body JSON:

```json
{"id":42,"status":"APPROVED"}
```

**Vì sao phải dùng token do `/api/csrf` trả?** Spring Security 6 mặc định có cơ chế bảo vệ CSRF token khỏi BREACH/masking. Token lấy từ `CsrfToken.getToken()` trong request có thể khác biểu diễn raw lưu ở cookie. Đừng đơn giản giả định có thể đọc `XSRF-TOKEN` cookie rồi gửi nguyên giá trị đó qua header với mọi request handler/config; hãy dùng đúng contract cấp token và test. Ví dụ được thiết kế để curl cùng origin lưu cookie và gửi lại token phản hồi.

### 10.6. User mai không thể approve dù CSRF hợp lệ

```bash
curl -s -o /dev/null -w '%{http_code}\n' \
  -u mai:demo123 -b csrf-cookies.txt \
  -H "X-XSRF-TOKEN: $csrf_token" \
  -X POST http://localhost:8080/api/orders/43/approve
```

Kỳ vọng:

```text
403
```

Lần này CSRF hợp lệ nhưng `Authentication` không có `ORDER_APPROVE`. **Không xử lý bằng cách tắt CSRF**: vấn đề là chính sách permission, không phải request validation.

### 10.7. User linh có ROLE_STAFF nhưng được cấp permission approve riêng

```bash
curl -s -u linh:demo123 -b csrf-cookies.txt \
  -H "X-XSRF-TOKEN: $csrf_token" \
  -X POST http://localhost:8080/api/orders/43/approve
```

Kỳ vọng:

```json
{"id":43,"status":"APPROVED"}
```

Dù `linh` không có `ROLE_APPROVER`, người này có `ORDER_APPROVE` theo danh sách authorities, nên URL và service-level checks đều cho phép. Ví dụ cho thấy lợi ích của việc **bảo vệ operation bằng permission cụ thể**, thay vì buộc mọi người dùng cần duyệt phải đổi vai trò công việc chính.

### 10.8. Auditor được đọc audit, không được xem orders theo quyền mặc định của demo

```bash
curl -s -u binh:demo123 http://localhost:8080/api/audit

curl -s -o /dev/null -w '%{http_code}\n' \
  -u binh:demo123 http://localhost:8080/api/orders/42
```

Kỳ vọng hai outputs:

```text
audit:ok
403
```

`binh` có `ROLE_AUDITOR` và `AUDIT_READ`, nhưng **không** có `ORDER_READ`. Role auditor không tự đồng nghĩa quyền đọc mọi dữ liệu.

### 10.9. hasRole("ADMIN") kiểm tra tiền tố ROLE_

```bash
curl -s -u root:demo123 http://localhost:8080/api/admin/health

curl -s -o /dev/null -w '%{http_code}\n' \
  -u an:demo123 http://localhost:8080/api/admin/health
```

Kỳ vọng:

```text
admin:ok
403
```

`root` có `ROLE_ADMIN`, còn `an` dù có `ORDER_APPROVE` vẫn không có role ADMIN. Trong trường hợp cần phân quyền quản trị, dùng cả permission cụ thể và kiểm soát phạm vi để tránh một role siêu rộng.

### 10.10. Tổng hợp ma trận phân quyền

| User | GET order | POST approve (CSRF hợp lệ) | GET audit | GET admin |
| --- | --- | --- | --- | --- |
| Anonymous | 401 | 401 hoặc 403 nếu thiếu CSRF | 401 | 401 |
| `mai` | 200 | **403** | 403 | 403 |
| `an` | 200 | **200** | 403 | 403 |
| `linh` | 200 | **200** | 403 | 403 |
| `binh` | **403** | **403** | 200 | 403 |
| `root` | 200 | 200 | 200 | 200 |
| `guest` | 403 | 403 | 403 | 403 |

Bảng giả định URL tồn tại và POST có CSRF hợp lệ. Khi thiếu CSRF, request POST có thể nhận 403 **trước khi** authorization. Body của response 200 có thể khác nếu trạng thái order demo đã được thay đổi bởi request trước; khởi động lại app để reset in-memory state.

## 11. Kiểm thử tự động bằng Spring Security Test

Project `pom.xml` đã bao gồm `spring-boot-starter-test` và `spring-security-test`. Tạo file:

```text
src/test/java/example/authorities/AuthorizationRulesTest.java
```

Nội dung:

```java
package example.authorities;

import static org.springframework.security.test.web.servlet.request
        .SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.security.test.web.servlet.request
        .SecurityMockMvcRequestPostProcessors.user;
import static org.springframework.test.web.servlet.request
        .MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request
        .MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result
        .MockMvcResultMatchers.status;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.test.web.servlet.MockMvc;

@SpringBootTest
@AutoConfigureMockMvc
class AuthorizationRulesTest {

    @Autowired
    MockMvc mvc;

    @Test
    void staffCanReadButCannotApprove() throws Exception {
        mvc.perform(get("/api/orders/42").with(user("mai")
                .authorities(new SimpleGrantedAuthority("ORDER_READ"))))
                .andExpect(status().isOk());

        mvc.perform(post("/api/orders/42/approve")
                .with(csrf())
                .with(user("mai").authorities(
                        new SimpleGrantedAuthority("ORDER_READ"))))
                .andExpect(status().isForbidden());
    }

    @Test
    void approverCanApproveWhenCsrfIsValid() throws Exception {
        mvc.perform(post("/api/orders/42/approve")
                .with(csrf())
                .with(user("an").authorities(
                        new SimpleGrantedAuthority("ORDER_APPROVE"))))
                .andExpect(status().isOk());
    }

    @Test
    void adminRoleIsSeparateFromOperationPermission() throws Exception {
        mvc.perform(get("/api/admin/health")
                .with(user("root").roles("ADMIN")))
                .andExpect(status().isOk());

        mvc.perform(get("/api/admin/health")
                .with(user("an").authorities(
                        new SimpleGrantedAuthority("ORDER_APPROVE"))))
                .andExpect(status().isForbidden());
    }

    @Test
    void postWithoutCsrfIsDeniedEvenWithPermission() throws Exception {
        mvc.perform(post("/api/orders/42/approve")
                .with(user("an").authorities(
                        new SimpleGrantedAuthority("ORDER_APPROVE"))))
                .andExpect(status().isForbidden());
    }
}
```

Chạy:

```bash
mvn test
```

**Điều test đang xác nhận:** Các yêu cầu có `Authentication` mock với authorities xác định trước được đưa qua security filters và service method interceptor. `with(user(...))` **không** kiểm thử password trong `UserDetailsService`; để test authentication end-to-end, bổ sung tests dùng HTTP Basic headers thật. Đây là kiểm thử **authorization policy** được tách khỏi bước kiểm tra mật khẩu.

Một điểm cần lưu ý: nếu test method thực thi song song và cùng sửa order 42, status có thể ảnh hưởng data assertions. Bộ test trên chỉ kiểm tra HTTP status, không phụ thuộc order còn PENDING hay đã APPROVED. Khi cần test domain transition, reset database/in-memory state hoặc dùng các fixture độc lập.

### Dấu hiệu cần bắt trong regression test

- `ROLE_STAFF` không được tự phê duyệt nếu thiếu `ORDER_APPROVE`.
- `ROLE_APPROVER` không có permission thì **không** đủ, trừ khi mapper đã cấp permission.
- `ROLE_ADMIN` không tự có mọi permission nếu không map.
- `AUDIT_READ` không kéo theo `ORDER_READ`.
- URL đọc cần `ORDER_READ`; POST approve cần `ORDER_APPROVE` và CSRF thích hợp.
- Method-level `@PreAuthorize` áp dụng kể cả khi controller được đổi tên hoặc có entrypoint mới.

## 12. Role hierarchy, inheritance và ủy quyền

Có hệ thống muốn admin “kế thừa” quyền staff. Spring Security hỗ trợ khái niệm **role hierarchy** trong các cấu hình thích hợp, nhưng **không tự suy ra** `ROLE_ADMIN` chứa mọi role. Nếu muốn inheritance, phải **định nghĩa rõ** và kiểm tra cách role hierarchy được tích hợp vào authorization ở cả URL/method.

```text
Minh họa chính sách kế thừa (không phải DSL bắt buộc):
ROLE_ADMIN > ROLE_APPROVER > ROLE_STAFF
```

Cẩn trọng: role hierarchy có thể làm phát sinh quyền không chủ định. Ví dụ auditor theo chính sách separation-of-duties **không nên** mặc định kế thừa quyền approve. Trên hệ thống lớn, mapping **role → permissions** minh bạch dễ audit hơn việc tạo một đồ thị hierarchy có cạnh khó thấy.

### Cấp quyền trực tiếp và tạm thời

Một nhân viên được ủy quyền duyệt đơn trong một tuần nên có bản ghi đủ:

- Ai cấp và ai duyệt việc cấp quyền?
- Permission nào và scope nào (chi nhánh, tenant, giá trị đơn tối đa)?
- Thời điểm có hiệu lực và hết hạn?
- Có cần approval hai người cho giao dịch nhạy cảm không?
- Khi thu hồi, bao lâu quyền biến mất khỏi session, JWT hoặc cache?

Đừng chỉ thêm `ORDER_APPROVE` vào JWT sống 30 ngày rồi nghĩ thu hồi trong DB lập tức làm JWT đã phát hành mất quyền. Với token tự chứa, authorities là một snapshot tại thời điểm phát hành, trừ khi ứng dụng có kiểm tra quyền động/revocation riêng.

## 13. Session, JWT và thời điểm cập nhật quyền

Quyền được thay đổi trong database **không bảo đảm** mọi request đang dùng session/token cũ sẽ thấy ngay thay đổi.

| Authentication mode | Authority thường đến từ đâu | Rủi ro stale permissions |
| --- | --- | --- |
| Username/password với HTTP Basic cho mỗi request | UserDetailsService/provider kiểm tra credentials | Có thể stale nếu user cache/map chưa cập nhật |
| Form login + session | Authentication lưu trong SecurityContext của session | Role thay đổi sau login nhưng context cũ vẫn có authorities cũ |
| JWT access token | Claims đã được ký ở lúc phát hành/mapping | Token còn hạn vẫn chứa claim snapshot cũ |
| OIDC login | IdP claims/authorities mapping theo login/refresh | Quyền trong session/login có thể cũ |
| Dynamic policy service | Tra cứu quyền mỗi lần hoặc qua cache | Đổi quyền có thể trễ theo TTL/cache invalidation |

Để giảm rủi ro: chọn short-lived tokens phù hợp, revoke/expire session khi quyền nhạy cảm đổi, hỗ trợ token introspection hoặc kiểm tra động ở service cho hành động quan trọng, và có chính sách cache invalidation.

**Quan trọng:** `hasAuthority("ORDER_APPROVE")` không tự thực hiện một database query để hỏi xem permission vừa bị thu hồi hay chưa; nó thường đánh giá `Authentication.getAuthorities()` **đang có**. Đảm bảo cách cập nhật authentication/claims phản ánh yêu cầu thu hồi của hệ thống.

## 14. Các lỗi và lỗ hổng thường gặp

| Dấu hiệu | Nguyên nhân hay gặp | Cách xử lý |
| --- | --- | --- |
| Có `ADMIN` nhưng `hasRole("ADMIN")` vẫn 403 | Thiếu tiền tố `ROLE_` | Lưu `ROLE_ADMIN` hoặc map prefix nhất quán |
| Có role STAFF nhưng `hasAuthority("ORDER_READ")` 403 | Framework không tự map role sang permission | Bổ sung mapping role–permission trong nguồn tin cậy |
| User bình thường vào được endpoint duyệt | Chỉ kiểm tra `authenticated()` hoặc `permitAll()` | Bảo vệ bằng permission cụ thể và method security |
| Auditor đọc được mọi tenant | Chỉ kiểm tra `AUDIT_READ`, không kiểm tra scope | Thêm tenant/resource policy server-side |
| Phân quyền tốt ở UI nhưng HTTP vẫn cho phép | Chỉ ẩn nút frontend | Áp dụng URL/service authorization ở backend |
| Token còn quyền sau khi DB đã thu hồi | Authorities trong session/JWT bị stale | Revoke/refresh/cache invalidation phù hợp |
| 401 khi chưa login | Không có authentication | Đây không phải lỗi cấp permission |
| 403 khi user đã login | Permission thiếu, CSRF hoặc policy resource deny | Kiểm tra thứ tự filters và decision |
| POST có quyền nhưng 403 | CSRF token thiếu/sai | Gửi token đúng hoặc thiết kế CSRF theo threat model |
| Quyền ghi bị bỏ qua khi gọi service trực tiếp | Chỉ bảo vệ controller/URL | Dùng `@PreAuthorize` trên service bean |
| `@PreAuthorize` không hoạt động trong self-invocation | Gọi method trong cùng object bypass proxy | Tách service và gọi qua Spring-managed proxy |
| Admin vô tình có tất cả quyền | Tự map `ROLE_ADMIN` thành `*` không kiểm soát | Explicit permissions và separation-of-duties |
| Quyền phụ thuộc data nhưng chỉ check role | Thiếu resource-level authorization | Tra cứu ownership/tenant/status server-side |

### Quy trình debug hợp lý

1. Request vào **đúng SecurityFilterChain** chưa? Nếu có nhiều chains, kiểm tra `securityMatcher` và `@Order`.
2. Xác minh authentication provider/decoder đã xác thực credentials, không tin trường user/role do client gửi.
3. Quan sát authorities **thực tế** của `Authentication` trong development (không log secrets).
4. So `hasRole` với `hasAuthority` và prefix `ROLE_`.
5. Xác định permission nào cần cho method/action và rule URL/method có nhất quán không.
6. Phân biệt 401 (thiếu authentication) với 403 (đã xác thực nhưng thiếu quyền hoặc CSRF).
7. Nếu policy theo resource, kiểm tra tenant/owner/order state từ database, không từ client.
8. Nếu permission vừa thay đổi, kiểm tra session/JWT/cache đã refresh chưa.
9. Bổ sung negative tests: user không có quyền, tenant khác, resource chưa đúng trạng thái, CSRF thiếu, role prefix sai.

Có thể bật log Spring Security khi phát triển:

```properties
logging.level.org.springframework.security=DEBUG
```

Không để logging raw `Authorization`, Basic credentials, JWT, session cookie, CSRF token hoặc dữ liệu nhạy cảm ở production. Chỉ ghi thông tin audit được phép: actor ID, permission/action, resource ID đã xử lý an toàn, decision, correlation ID.

## 15. Câu hỏi tự ôn

1. **`GrantedAuthority` có phải chỉ đại diện role không?** Không, có thể là role, permission hoặc một authority string khác do ứng dụng định nghĩa.
2. **`SimpleGrantedAuthority("ROLE_STAFF")` khác `SimpleGrantedAuthority("ORDER_READ")` ở Java type không?** Không, cả hai cùng class; khác semantics do convention.
3. **`hasRole("ADMIN")` thường kiểm tra chuỗi nào?** `ROLE_ADMIN`.
4. **`.roles("ADMIN")` và `.authorities("ADMIN")` tạo cùng authority không?** Không; builder `.roles()` thêm tiền tố `ROLE_`.
5. **Role APPROVER tự động suy ra ORDER_APPROVE không?** Không; cần role–permission mapping hoặc rule trực tiếp.
6. **`hasAuthority("ORDER_APPROVE")` có biết user được duyệt đơn 42 thuộc tenant khác không?** Không; cần kiểm tra resource/tenant.
7. **Có thể cấp ORDER_APPROVE trực tiếp cho ROLE_STAFF user không?** Có trong mô hình permission-based, nếu nghiệp vụ cho phép và có audit/scope.
8. **Frontend ẩn nút approve có thay thế backend authorization không?** Không.
9. **Có ORDER_READ thì POST approve được không?** Không nếu rule yêu cầu ORDER_APPROVE.
10. **Vì sao POST bị 403 dù có ORDER_APPROVE?** Có thể CSRF thiếu hoặc domain policy khác từ chối.
11. **`@PreAuthorize` có tự chạy khi self-invocation không?** Trong proxy-based method security thông thường, không; cần lời gọi qua proxy.
12. **Authorities trong JWT đã phát có thay đổi ngay khi DB cập nhật role không?** Không tự động; cần lifecycle/revocation/refresh phù hợp.
13. **Role hierarchy có tự xuất hiện nếu đặt ROLE_ADMIN không?** Không; phải cấu hình.
14. **Vì sao quyền trực tiếp nên có thời hạn?** Giúp giảm đặc quyền tồn tại lâu, hỗ trợ thu hồi và audit.
15. **Domain status PENDING có phải GrantedAuthority không?** Không; đó là trạng thái đối tượng cần kiểm tra ở service/database.

## 16. Checklist thiết kế phân quyền nghiệp vụ

- [ ] Định nghĩa role như nhóm trách nhiệm, permission như quyền thao tác cụ thể.
- [ ] Dùng `GrantedAuthority`/nguồn authority đáng tin cậy; không chấp nhận role do client tự khai.
- [ ] Chuẩn hóa `ROLE_` prefix và phân biệt `roles()`, `authorities()`, `hasRole()`, `hasAuthority()`.
- [ ] Mô tả role–permission mapping rõ ràng, audit được; không cho quyền mặc định vượt nhu cầu.
- [ ] Bảo vệ endpoint theo hành động (READ/CREATE/UPDATE/APPROVE/EXPORT...), không chỉ theo `authenticated()`.
- [ ] Dùng method security/service layer làm lớp bảo vệ cho hành động nghiệp vụ quan trọng.
- [ ] Phân quyền theo resource, tenant và owner bằng dữ liệu server-side, không chỉ authority string.
- [ ] Kiểm tra domain invariants/TOCTOU trong transaction, đặc biệt các hành động duyệt và hoàn tiền.
- [ ] Không dùng frontend button visibility làm bảo mật.
- [ ] Chọn lifecycle/cache invalidation để thu hồi quyền khi role/permission đổi.
- [ ] Thiết kế direct permission/temporary delegation có thời hạn và phạm vi, kiểm soát separation of duties.
- [ ] Đánh giá HTTPS/CSRF/cookie và authentication scheme, không tắt bảo vệ vì muốn demo POST dễ hơn.
- [ ] Test anonymous, sai credentials, đủ/thiếu permission, sai role prefix, thiếu CSRF và thao tác trên tenant khác.
- [ ] Tách chính sách quản trị `ROLE_ADMIN` với permission nghiệp vụ cụ thể; tránh quyền wildcard tràn lan.

**Kết luận:** `GrantedAuthority` là cách Spring Security biểu diễn **những quyền đã được cấp cho Authentication**. Role (`ROLE_STAFF`, `ROLE_ADMIN`) mô tả nhóm trách nhiệm, còn permission (`ORDER_READ`, `ORDER_APPROVE`, `AUDIT_READ`) mô tả **hành động được phép**. `hasRole`/`hasAuthority` đánh giá authority string hiện tại; để hệ thống an toàn, cần thêm **mapping role–permission tin cậy**, **service/method authorization**, **kiểm tra theo resource/tenant**, CSRF đúng mô hình client và **quy trình cập nhật/thu hồi quyền**.