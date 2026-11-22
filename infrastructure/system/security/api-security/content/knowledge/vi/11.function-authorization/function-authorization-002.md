# Phân quyền method và endpoint quản trị

Một API có thể xác thực người gọi chính xác nhưng vẫn cho phép họ thực hiện hành động vượt quyền nếu server chỉ kiểm tra đăng nhập hoặc chỉ ẩn nút chức năng trên giao diện. Đặc biệt, endpoint quản trị thường có khả năng đọc dữ liệu diện rộng, thay đổi cấu hình, quản lý tài khoản, cấp quyền hoặc thực hiện thao tác có ảnh hưởng lớn. Vì vậy, cần kiểm soát quyền ở cả **HTTP method/endpoint** và **method nghiệp vụ phía server**.

Trong phạm vi `SECURITY_API_SECURITY`, phân quyền phải được thiết kế theo từng endpoint, đối tượng dữ liệu và luồng nghiệp vụ. Một quyền như `admin:access` hoặc vai trò `ADMIN` không nên trở thành giấy phép chung cho mọi thao tác quản trị. API cần xác định rõ actor được gọi action nào, trên nhóm tài nguyên nào, trong tenant nào và ở trạng thái nghiệp vụ nào.

## 1. Authentication và function authorization là hai quyết định khác nhau

Authentication trả lời câu hỏi danh tính của caller là ai. Function authorization trả lời caller có được phép thực hiện chức năng cụ thể hay không.

Ví dụ, một nhân viên đã đăng nhập có thể được phép xem danh sách đơn hàng nhưng không được hoàn tiền. Một service account có thể gọi API đồng bộ kho nhưng không được tạo tài khoản quản trị. Một quản trị viên tenant có thể quản lý người dùng trong tenant của mình nhưng không được thay đổi cấu hình toàn hệ thống.

Do đó, kiểm tra `authenticated()` chỉ chứng minh request có principal hợp lệ. Nó không thay thế kiểm tra quyền như `orders:read`, `orders:refund`, `users:disable` hoặc `system:config:update`.

| Lớp kiểm soát | Câu hỏi | Ví dụ |
|---|---|---|
| Authentication | Ai đang gọi? | User, service account hoặc client đã xác thực |
| Function authorization | Được gọi chức năng nào? | Được phép `invoice:approve` |
| Object authorization | Được thao tác trên bản ghi nào? | Chỉ hóa đơn thuộc tenant được phân công |
| Property authorization | Được đọc/sửa field nào? | Được sửa `displayName`, không được sửa `role` |
| Workflow authorization | Được thực hiện lúc nào? | Chỉ capture payment sau khi order đã approved |

Các lớp này phải phối hợp. Có quyền gọi `invoice:approve` không có nghĩa actor được duyệt mọi hóa đơn; có quyền truy cập endpoint quản trị cũng không có nghĩa mọi field trong response đều được phép xem.

## 2. Ánh xạ HTTP method sang quyền nghiệp vụ

HTTP method mô tả loại thao tác ở tầng giao thức. API thường dùng các method sau:

| HTTP method | Ý nghĩa thường gặp | Quyền nghiệp vụ có thể ánh xạ |
|---|---|---|
| `GET` | Đọc representation | `resource:read` |
| `HEAD` | Đọc metadata/headers của representation | Thường cùng quyền đọc với `GET` |
| `POST` | Tạo tài nguyên hoặc thực hiện command | `resource:create` hoặc quyền action cụ thể |
| `PUT` | Thay thế representation | `resource:update` |
| `PATCH` | Cập nhật một phần representation | `resource:update` và quyền trên từng field |
| `DELETE` | Xóa hoặc vô hiệu hóa tài nguyên | `resource:delete` hoặc `resource:disable` |
| `OPTIONS` | Khám phá khả năng giao tiếp/preflight CORS | Không phải quyền đọc/sửa dữ liệu |

Đây là ánh xạ tham khảo, không phải quy tắc cứng. `POST` có thể thực hiện nhiều action khác nhau như `approve`, `refund`, `revoke`, `rotate-key` hoặc `export`; không nên gộp tất cả vào quyền `resource:create`. Tương tự, `DELETE` có thể là thao tác thu hồi mềm, hủy giao dịch hoặc xóa vĩnh viễn với mức rủi ro khác nhau.

### 2.1. Phân quyền theo action cụ thể

Với API nghiệp vụ, tên quyền nên phản ánh hành động mà người dùng hiểu được:

```text
orders:read
orders:create
orders:update
orders:cancel
orders:refund
users:read
users:disable
users:role:assign
api-keys:create
api-keys:revoke
system:config:read
system:config:update
```

Một endpoint `POST /api/orders/{id}/refund` có thể yêu cầu `orders:refund`; không nên chỉ yêu cầu `orders:write` nếu quyền đó bao gồm nhiều hành động không tương đương. Quyền càng cụ thể thì càng dễ review, audit và cấp theo nguyên tắc least privilege.

### 2.2. Không suy quyền chỉ từ method

Không phải mọi `POST` đều là tạo mới và không phải mọi `GET` đều vô hại. Ví dụ:

- `POST /api/invoices/{id}/approve` là command phê duyệt.
- `POST /api/payments/{id}/refund` có thể làm phát sinh chuyển tiền.
- `GET /api/admin/export` có thể trả về dữ liệu cá nhân diện rộng.
- `GET /api/reports/run` có thể khởi chạy tác vụ tốn tài nguyên nếu API thiết kế sai ngữ nghĩa.

Vì vậy, cần ánh xạ route và method đến quyền nghiệp vụ cụ thể. Không cấp quyền chỉ dựa vào việc request là `GET`, `POST` hay `DELETE`.

## 3. Thiết kế ma trận quyền cho endpoint

Trước khi viết security matcher, hãy lập danh mục endpoint và quyền cần có. Một ma trận cơ bản:

| Endpoint | Method | Action | Permission | Kiểm tra bổ sung |
|---|---|---|---|---|
| `/api/orders` | `GET` | Liệt kê đơn hàng | `orders:read` | Scope theo tenant, pagination limit |
| `/api/orders` | `POST` | Tạo đơn hàng | `orders:create` | Validation, quota và owner lấy từ principal |
| `/api/orders/{id}` | `PATCH` | Cập nhật đơn hàng | `orders:update` | Object ownership và allowlist field |
| `/api/orders/{id}/cancel` | `POST` | Hủy đơn hàng | `orders:cancel` | Chỉ hủy ở trạng thái cho phép |
| `/api/payments/{id}/refund` | `POST` | Hoàn tiền | `payments:refund` | Object scope, hạn mức, step-up và idempotency |
| `/api/admin/users` | `GET` | Liệt kê user quản trị | `admin:users:read` | Tenant/admin scope và lọc field |
| `/api/admin/users/{id}/disable` | `POST` | Vô hiệu hóa user | `admin:users:disable` | Kiểm tra target, tách nhiệm vụ và audit |
| `/api/admin/keys/{id}/revoke` | `POST` | Thu hồi API key | `admin:keys:revoke` | Owner, trạng thái key và cache invalidation |
| `/api/admin/system-config` | `PATCH` | Sửa cấu hình hệ thống | `admin:system-config:update` | Step-up authentication, allowlist và audit |

Ma trận cần được review cùng chủ sở hữu nghiệp vụ. Đối với mỗi endpoint, ghi rõ:

- Principal nào được phép gọi: user, service account hay admin.
- Permission cần có và nguồn cấp permission.
- Object/tenant scope áp dụng.
- Field nào có thể đọc hoặc ghi.
- Trạng thái workflow và điều kiện trước khi thực hiện.
- Side effect, mức độ nhạy cảm và yêu cầu audit.

Nếu endpoint không có trong ma trận hoặc chưa có policy rõ ràng, mặc định từ chối cho đến khi được phân loại. Đây là cách tránh endpoint mới vô tình kế thừa quyền quá rộng từ matcher tổng quát.

## 4. Bảo vệ endpoint quản trị

Endpoint quản trị thường có blast radius lớn. Một lỗi phân quyền nhỏ có thể cho phép attacker tạo admin mới, tắt tài khoản, đọc dữ liệu của nhiều tenant, thay cấu hình bảo mật hoặc thu hồi credential của workload.

### 4.1. Tách quyền quản trị theo chức năng

Không nên dùng một quyền `ADMIN` duy nhất cho mọi thao tác. Có thể chia thành:

| Permission | Phạm vi |
|---|---|
| `admin:users:read` | Xem metadata tài khoản trong phạm vi được quản lý |
| `admin:users:create` | Tạo tài khoản theo chính sách |
| `admin:users:disable` | Vô hiệu hóa tài khoản |
| `admin:users:role:assign` | Gán hoặc thu hồi vai trò |
| `admin:keys:create` | Phát hành API key |
| `admin:keys:revoke` | Thu hồi API key |
| `admin:audit:read` | Xem audit log trong phạm vi |
| `admin:system-config:update` | Thay đổi cấu hình hệ thống |

Các permission có thể được nhóm thành role để thuận tiện cấp phát, nhưng quyết định cuối cùng ở API vẫn nên dựa trên quyền cụ thể và phạm vi tài nguyên. Một role `TENANT_ADMIN` không tự động có quyền trên tenant khác hoặc trên cấu hình toàn hệ thống.

### 4.2. Tách tenant administration và platform administration

Hệ thống multi-tenant cần phân biệt quản trị một tenant với quản trị toàn nền tảng:

- **Tenant administrator:** quản lý người dùng, cấu hình và dữ liệu trong tenant được cấp.
- **Platform administrator:** quản lý chức năng vận hành toàn hệ thống theo quyền được cấp riêng.
- **Support/operator:** có thể xem thông tin giới hạn để hỗ trợ, nhưng không mặc nhiên được sửa dữ liệu khách hàng.
- **Service account:** chỉ gọi các endpoint cần cho workload, không được sử dụng endpoint quản trị người dùng nếu không có use case rõ ràng.

Tenant ID phải được lấy từ principal hoặc context tin cậy của server. Không dùng `tenantId` trong request body làm căn cứ duy nhất để quyết định phạm vi quản trị. Nếu platform administrator cần truy cập xuyên tenant, hành động đó phải có permission rõ ràng, audit đầy đủ và có thể yêu cầu xác minh bổ sung.

### 4.3. Tăng cường xác thực cho thao tác nhạy cảm

Với thao tác như cấp quyền admin, thay signing key, thu hồi API key diện rộng, thay cấu hình network hoặc xuất dữ liệu nhạy cảm, có thể yêu cầu:

- MFA hoặc step-up authentication gần thời điểm thao tác.
- Re-authentication nếu phiên đã tồn tại lâu.
- Approval bởi người thứ hai theo nguyên tắc dual control.
- Giới hạn phạm vi, số lượng và thời gian hiệu lực của thao tác.
- Idempotency key để tránh thực hiện trùng khi client retry.
- Audit event ghi actor, target, action, lý do và kết quả.

Các kiểm soát này bổ sung cho function authorization. MFA thành công không có nghĩa actor được phép thực hiện mọi chức năng quản trị.

### 4.4. Bảo vệ management plane

Nếu kiến trúc có management plane riêng, hãy tách endpoint quản trị khỏi API công khai bằng host, gateway, network segment hoặc security chain phù hợp. Có thể bổ sung private network, VPN, mTLS, IP allowlist hoặc workload identity.

Kiểm soát mạng chỉ là lớp bổ sung. Một request đến từ mạng nội bộ vẫn phải xác thực và phân quyền. Không mặc định mọi request từ IP nội bộ đều là admin; môi trường cloud, proxy, NAT và workload bị xâm nhập đều có thể làm giả cảm giác tin cậy này.

## 5. Phân quyền ở HTTP request layer

Tầng HTTP là nơi đầu tiên có thể chặn request theo route và method. Đây là lớp phù hợp để áp dụng permission tổng quát trước khi request vào controller.

Ví dụ minh họa với Spring Security:

```java
@Configuration
@EnableWebSecurity
class ApiSecurityConfiguration {

    @Bean
    SecurityFilterChain apiSecurity(HttpSecurity http) throws Exception {
        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET, "/api/admin/**")
                    .hasAuthority("admin:read")
                .requestMatchers(HttpMethod.HEAD, "/api/admin/**")
                    .hasAuthority("admin:read")
                .requestMatchers(HttpMethod.POST, "/api/admin/**")
                    .hasAuthority("admin:command")
                .requestMatchers(HttpMethod.PUT, "/api/admin/**")
                    .hasAuthority("admin:update")
                .requestMatchers(HttpMethod.PATCH, "/api/admin/**")
                    .hasAuthority("admin:update")
                .requestMatchers(HttpMethod.DELETE, "/api/admin/**")
                    .hasAuthority("admin:delete")
                .requestMatchers("/api/admin/**").denyAll()
                .requestMatchers("/api/public/**").permitAll()
                .anyRequest().authenticated()
            )
            .build();
    }
}
```

Đây là ví dụ về cách tổ chức matcher theo method. Trong hệ thống thực tế, nên dùng permission cụ thể hơn theo từng nhóm endpoint thay vì một quyền chung như `admin:command`. Các matcher cụ thể phải được đặt trước matcher fallback; `/api/admin/**` cuối cùng dùng `denyAll()` để method hoặc route chưa được khai báo không tự động được phép chỉ vì caller đã đăng nhập.

Ví dụ này cũng cần cấu hình authentication mechanism, CORS, CSRF và session theo loại client của ứng dụng. Không sao chép nguyên trạng cấu hình vào production nếu chưa xác định các yếu tố đó.

### 5.1. Vì sao cần fallback denyAll cho admin route?

Giả sử hôm nay có các matcher cho GET và POST. Tháng sau developer thêm endpoint `PATCH /api/admin/tenants/{id}/limits` nhưng quên thêm rule. Nếu cấu hình cuối cùng chỉ là `anyRequest().authenticated()`, một user đã đăng nhập có thể đi qua lớp request authorization.

Fallback `denyAll()` trong vùng admin giúp endpoint/method chưa được phân loại bị từ chối. Khi bổ sung chức năng mới, developer phải khai báo permission rõ ràng trước khi endpoint hoạt động.

### 5.2. HEAD, OPTIONS và method override

Không bỏ qua các method ít được chú ý:

- `HEAD` thường tương đương `GET` nhưng chỉ trả headers. Nếu headers chứa metadata nhạy cảm, vẫn cần quyền đọc tương ứng.
- `OPTIONS` thường được dùng cho CORS preflight. Cấu hình CORS cần cho phép preflight hợp lệ mà không vô tình cho phép đọc hoặc thay đổi dữ liệu.
- Một số framework/proxy hỗ trợ `X-HTTP-Method-Override` hoặc `_method`. Nếu bật, phải xác định method hiệu lực trước khi phân quyền; nếu không cần, nên tắt để giảm khác biệt giữa method mà gateway kiểm tra và method mà ứng dụng thực thi.
- WebDAV hoặc method mở rộng cần được phân loại rõ; không để method lạ đi vào handler có quyền rộng.

CORS không phải authorization. CORS chủ yếu kiểm soát việc trình duyệt cho JavaScript ở origin khác đọc response; curl, mobile app hoặc server khác không bị CORS bảo vệ. Một request bị CORS chặn ở browser vẫn có thể được gửi trực tiếp đến API.

### 5.3. HTTP method không thay thế kiểm tra trong service

Request matcher có thể kiểm tra quyền tổng quát theo route, nhưng service phải kiểm tra quyền trên object và điều kiện nghiệp vụ. Ví dụ `orders:update` không chứng minh actor được sửa đơn hàng cụ thể; `admin:users:disable` không cho phép vô hiệu hóa tài khoản thuộc platform khác.

Tách hai lớp giúp giảm rủi ro khi cùng một service method được gọi từ REST controller, GraphQL resolver, scheduled job hoặc message consumer. Mỗi đường gọi cần có principal/service identity và policy phù hợp.

## 6. Phân quyền ở method nghiệp vụ

Method-level authorization bảo vệ chức năng tại nơi thực hiện nghiệp vụ. Nó hữu ích khi nhiều controller hoặc entry point gọi chung một service method.

Ví dụ:

```java
@Service
public class AdminUserService {

    @PreAuthorize("hasAuthority('admin:users:disable')")
    @Transactional
    public void disableUser(UUID targetUserId, CurrentActor actor) {
        User target = userRepository.findByIdAndTenantId(
                targetUserId,
                actor.tenantId())
            .orElseThrow(UserNotFoundException::new);

        adminPolicy.requireCanDisable(actor, target);
        target.disable(actor.userId());
    }
}
```

`@PreAuthorize` kiểm tra quyền gọi chức năng. Truy vấn theo tenant và `adminPolicy` kiểm tra phạm vi object và quy tắc cụ thể. Service không lấy tenant tùy ý từ client. Nếu actor có thể disable một số loại user nhưng không được disable platform owner, policy phải thể hiện rõ ngoại lệ đó.

### 6.1. Bật method security

Với Spring Security, cần bật method security bằng `@EnableMethodSecurity` ở cấu hình phù hợp:

```java
@Configuration
@EnableMethodSecurity
class MethodSecurityConfiguration {
}
```

Nếu chưa bật method security, annotation `@PreAuthorize` có thể không được thực thi như mong đợi. Cần có integration test chứng minh một caller thiếu authority thực sự bị chặn khi gọi service qua Spring proxy.

### 6.2. Những giới hạn của proxy-based method security

Trong cấu hình Spring proxy thông thường, method security được áp dụng khi lời gọi đi qua proxy. Một số lỗi thường gặp:

- **Self-invocation:** method trong cùng object gọi trực tiếp method khác có `@PreAuthorize`; lời gọi nội bộ có thể không đi qua proxy nên annotation không chạy.
- **Visibility:** method private hoặc cách gọi không được proxy hỗ trợ có thể không được bảo vệ như kỳ vọng, tùy loại proxy và phiên bản framework.
- **Tạo object thủ công:** service được tạo bằng `new` thay vì dependency injection nên không có security proxy.
- **Async/background:** công việc chạy ở thread khác có thể không mang SecurityContext; không mặc định principal của request ban đầu tự xuất hiện ở worker.
- **Test gọi trực tiếp:** unit test tạo service bằng constructor có thể bỏ qua toàn bộ method security.

Giải pháp là tổ chức service boundary rõ, gọi qua bean được quản lý, kiểm tra principal/context khi chuyển sang async, và test qua application context. Không dựa vào annotation nếu đường thực thi có thể bypass proxy.

### 6.3. Không chỉ dựa vào role cấp cao

`hasRole('ADMIN')` thường chỉ kiểm tra một authority tổng quát. Với endpoint quản trị, permission cụ thể giúp dễ phân tách trách nhiệm:

```java
@PreAuthorize("hasAuthority('admin:keys:revoke')")
public void revokeApiKey(UUID keyId, CurrentActor actor) {
    // Kiểm tra tenant/owner, trạng thái key, audit và cache invalidation.
}
```

Nếu tổ chức vẫn dùng role, nên ánh xạ role sang permission ở một nơi được quản trị và kiểm thử. Tránh rải điều kiện `role == ADMIN` trong nhiều controller/service vì policy sẽ khó đồng bộ và khó audit.

## 7. Bảo vệ action quản trị có side effect

Một số endpoint quản trị có tác động lớn hơn thao tác CRUD thông thường. Cần mô hình hóa action riêng và kiểm tra điều kiện trước khi tạo side effect.

| Action | Rủi ro | Kiểm soát bổ sung |
|---|---|---|
| Gán role hoặc quyền admin | Leo thang đặc quyền | Dual control, step-up, cấm tự nâng quyền nếu policy yêu cầu |
| Disable user | Khóa nhầm hoặc phá vỡ dịch vụ | Kiểm tra target, lý do, audit và quy trình khôi phục |
| Revoke API key | Gián đoạn integration | Xác định owner, key scope và SLA cache invalidation |
| Rotate signing key | Làm token hợp lệ bị từ chối hoặc mở cửa cho khóa giả | Quy trình key management, overlap và phê duyệt |
| Export dữ liệu | Rò rỉ dữ liệu diện rộng | Scope, field filtering, quota, watermark/audit khi phù hợp |
| Update system config | Thay đổi bảo mật toàn nền tảng | Allowlist field, validation, versioning và rollback |
| Refund payment | Thất thoát tài chính | Object permission, hạn mức, idempotency và trạng thái workflow |

Quyền action phải được kiểm tra trước side effect. Nếu một thao tác gọi service ngoài hoặc publish message, cần bảo đảm quyết định authorization và cập nhật trạng thái có tính nhất quán phù hợp. Một response `403` sau khi đã gửi lệnh thanh toán không thể hoàn tác side effect đó.

### 7.1. Tách nhiệm vụ và dual control

Với thao tác có rủi ro cao, người tạo yêu cầu và người phê duyệt có thể phải là hai actor khác nhau. Policy cần kiểm tra cả hai danh tính và trạng thái phê duyệt; không chỉ kiểm tra người phê duyệt có role admin.

Ví dụ, thao tác thay đổi signing key có thể đi qua các trạng thái `REQUESTED`, `APPROVED`, `SCHEDULED`, `APPLIED` và `VERIFIED`. Mỗi chuyển trạng thái có permission riêng và audit event. Không cho phép gọi trực tiếp endpoint `apply` để bỏ qua bước approve.

### 7.2. CSRF và endpoint quản trị dùng cookie

Nếu browser gửi session cookie tự động, endpoint quản trị có thể chịu rủi ro CSRF. Cần cấu hình CSRF protection phù hợp, SameSite cookie, kiểm tra origin/referer theo kiến trúc và tránh dùng GET cho thao tác thay đổi dữ liệu.

Nếu API dùng bearer token được client chủ động gắn vào header, mô hình CSRF khác với cookie tự động, nhưng vẫn cần bảo vệ token khỏi XSS và rò rỉ. Không tắt CSRF một cách máy móc chỉ vì endpoint trả JSON hoặc có prefix `/api`.

## 8. Quy tắc thiết kế endpoint quản trị an toàn

### 8.1. Đặt route rõ ràng, không dựa vào tên route để bảo vệ

Prefix `/admin` giúp phân loại và review, nhưng tự nó không tạo bảo mật. Endpoint `POST /api/admin/users/{id}/disable` vẫn phải có authentication, permission, object scope, validation và audit.

Tránh các route mơ hồ như:

```text
POST /api/users/{id}/action?action=disable
POST /api/system/execute
GET  /api/admin/run?command=export
```

Các route command tổng quát dễ gom nhiều hành động có mức rủi ro khác nhau vào một policy. Nên biểu diễn action cụ thể trong route hoặc command type đã được allowlist, sau đó ánh xạ đến permission riêng.

### 8.2. Không tin dữ liệu quyền từ request

Không nhận `role`, `isAdmin`, `permission`, `tenantId` hoặc `actorId` từ body rồi dùng trực tiếp để cấp quyền. Danh tính và authority phải đến từ security context đã xác thực hoặc nguồn quản trị đáng tin cậy. Target ID trong request chỉ là tham chiếu cần kiểm tra.

Request DTO cần allowlist field được phép sửa. Ví dụ endpoint thay display name không được bind toàn bộ JSON vào entity user có cả `role`, `enabled`, `tenantId` và `passwordHash`.

### 8.3. Phân trang, export và bulk action

Endpoint quản trị thường có thể trả nhiều bản ghi hoặc tác động nhiều đối tượng. Cần giới hạn:

- Số phần tử tối đa trong một trang hoặc bulk request.
- Số lượng object mà một actor có thể xử lý trong một khoảng thời gian.
- Field được phép export và tenant/data scope.
- Thời gian chạy, kích thước file và số job đồng thời.
- Quyền đọc operation status và file kết quả sau khi job bất đồng bộ hoàn tất.

Với bulk request, kiểm tra quyền cho từng object hoặc thực hiện truy vấn có scope bảo đảm toàn bộ tập phần tử thuộc phạm vi. Không kiểm tra phần tử đầu rồi tin cả danh sách.

## 9. Kết hợp với gateway và service-to-service

API gateway có thể chặn một số route quản trị, xác minh token, áp dụng rate limit hoặc giới hạn network. Tuy nhiên, gateway thường không có đầy đủ ngữ cảnh về object, field và workflow. Service đích vẫn phải kiểm tra quyền nghiệp vụ.

Với service-to-service:

- Dùng workload identity, mTLS hoặc OAuth client credentials phù hợp thay vì chia sẻ một admin API key cho nhiều service.
- Cấp audience và scope đúng service đích.
- Xác minh service identity ở resource server.
- Nếu cần truyền user context, xác minh nguồn phát hành và tính toàn vẹn của delegated context; không tin header `X-User-Id` do client tùy ý gửi.
- Phân biệt quyền của service với quyền của user được ủy quyền; ghi nhận cả hai trong audit.
- Worker nhận message cần xác minh producer, loại command, tenant và quyền thực hiện tại thời điểm xử lý.

Không mặc định request nội bộ là đáng tin. Một service bị xâm nhập hoặc một queue producer cấu hình sai có thể tạo request đến endpoint quản trị nếu service đích không tự bảo vệ.

## 10. HTTP response và audit khi bị từ chối

Response nên phản ánh đúng nguyên nhân ở mức thông tin caller được phép biết:

- `401 Unauthorized`: thiếu hoặc credential không hợp lệ.
- `403 Forbidden`: principal hợp lệ nhưng không có permission/action tương ứng.
- `404 Not Found`: có thể dùng để che giấu sự tồn tại của object ngoài phạm vi.
- `405 Method Not Allowed`: route có tồn tại nhưng method không được hỗ trợ; không dùng thay cho lỗi quyền.

Không trả stack trace, policy expression, danh sách admin, secret hoặc lý do nội bộ chi tiết. Đồng thời, log nội bộ cần đủ dữ liệu để điều tra:

- Actor/service identity và tenant.
- Route, method, action và target object ở dạng phù hợp.
- Permission cần thiết và kết quả quyết định allow/deny.
- Correlation ID, thời điểm, lý do nghiệp vụ và kết quả side effect.
- Người yêu cầu và người phê duyệt nếu có dual control.

Không ghi access token, API key, mật khẩu, dữ liệu thanh toán hoặc payload nhạy cảm. Audit log cần có quyền đọc hạn chế, retention rõ và khả năng phát hiện sửa đổi.

## 11. Kiểm thử phân quyền method và endpoint quản trị

Kiểm thử phải bao gồm cả quyền được phép và bị từ chối. Tạo ma trận theo principal, permission, tenant, HTTP method, endpoint, object và trạng thái.

| Tình huống | Kết quả mong đợi |
|---|---|
| Không có credential gọi admin endpoint | `401` |
| User đã đăng nhập nhưng không có admin permission | `403` hoặc `404` theo chính sách che giấu |
| User có `admin:users:read` gọi DELETE user | Bị từ chối |
| User có quyền read nhưng gọi export dữ liệu nhạy cảm | Bị từ chối nếu thiếu export permission |
| Method chưa khai báo trên `/api/admin/**` | Fallback deny; không tự động cho qua vì đã đăng nhập |
| HEAD trên endpoint nhạy cảm | Áp dụng quyền đọc tương ứng |
| OPTIONS preflight | Chỉ xử lý theo CORS policy; không cấp quyền cho request thực tế |
| Method override thay POST thành DELETE | Bị từ chối hoặc xử lý theo method hiệu lực đã được kiểm soát |
| Tenant admin truy cập user tenant khác | Bị từ chối hoặc che giấu object |
| Admin thiếu quyền field | Field không được đọc/sửa |
| Gọi service method qua controller | Method security được thực thi |
| Self-invocation hoặc async worker | Không có đường bypass policy; context được truyền/xác minh rõ |
| Request bị từ chối | Không có database write, message, email hoặc side effect |
| Hai actor cùng phê duyệt một action | Invariant dual control vẫn được giữ |
| Bulk request chứa một object ngoài phạm vi | Không xử lý trái phép object đó; semantics toàn bộ request được quy định rõ |

### 11.1. Các lớp kiểm thử nên có

- **Unit test cho policy:** kiểm tra permission, tenant, quan hệ object, field và trạng thái.
- **Integration test cho request matcher:** gọi qua Spring Security filter chain để xác minh method/route mapping.
- **Integration test cho method security:** gọi service qua Spring application context với principal có và không có authority.
- **Test endpoint inventory:** đối chiếu route thực tế với ma trận permission, phát hiện endpoint mới chưa được phân loại.
- **Negative test:** thử đổi HTTP method, path variant, method override, ID, tenant và payload.
- **Concurrency test:** kiểm tra dual control, idempotency và chuyển trạng thái khi có request đồng thời.
- **End-to-end test:** xác minh gateway, application và service nội bộ cùng áp dụng policy.

Test nên xác nhận cả status code, response schema, audit event và việc không có side effect khi bị từ chối. Một unit test cho biểu thức `hasAuthority` không đủ để chứng minh toàn bộ endpoint quản trị được bảo vệ.

## 12. Những lỗi triển khai thường gặp

| Lỗi | Hệ quả | Cách xử lý |
|---|---|---|
| Chỉ kiểm tra `authenticated()` | Mọi user đăng nhập có thể gọi chức năng quản trị | Permission cụ thể theo action |
| Ẩn nút admin ở frontend | Attacker gọi endpoint trực tiếp | Authorization ở server |
| Dùng một role `ADMIN` cho mọi việc | Quyền quá rộng, khó audit | Tách permission và phạm vi tenant |
| Chỉ bảo vệ GET/POST nhưng quên PATCH/DELETE/HEAD | Method khác có thể bypass | Ma trận đầy đủ và fallback deny |
| Matcher rộng đứng trước matcher cụ thể | Rule cụ thể không được áp dụng | Sắp xếp matcher theo độ cụ thể và test |
| Không có fallback deny cho admin route | Endpoint mới có thể được phép ngoài ý muốn | Deny-by-default |
| Dựa vào CORS để bảo vệ API | Client ngoài browser vẫn gọi được | Authorization server-side |
| `@PreAuthorize` chưa bật hoặc bị self-invocation | Method nghiệp vụ không được bảo vệ | Bật method security, kiểm soát proxy boundary và integration test |
| Chỉ tin gateway/network nội bộ | Request nội bộ bị xâm nhập có thể vượt quyền | Service đích tự xác thực và phân quyền |
| Kiểm tra quyền sau side effect | Hành động trái phép đã xảy ra | Authorize trước và bảo đảm transaction/workflow |

## 13. Checklist review method authorization và admin endpoint

- [ ] Mọi endpoint có trong inventory và được ánh xạ đến action/permission cụ thể.
- [ ] Authentication được tách khỏi function authorization.
- [ ] HTTP method được kiểm tra đầy đủ, gồm HEAD, OPTIONS, method mở rộng và method override nếu có.
- [ ] Admin route có fallback deny-by-default cho method/endpoint chưa khai báo.
- [ ] Quyền quản trị được chia theo action, tenant và phạm vi dữ liệu.
- [ ] Tenant administrator và platform administrator có ranh giới rõ.
- [ ] Object, field và workflow vẫn được kiểm tra trong service.
- [ ] Method security được bật và các đường gọi qua proxy/async được kiểm thử.
- [ ] Thao tác nhạy cảm có step-up, dual control, idempotency hoặc audit khi cần.
- [ ] Management plane/network restriction chỉ là lớp bổ sung, không thay authorization.
- [ ] CSRF được cấu hình phù hợp với cơ chế credential của browser client.
- [ ] Bulk/export có giới hạn object, field, kích thước, quota và thời gian.
- [ ] Service-to-service và worker có identity, audience/scope và policy riêng.
- [ ] Response từ chối không tiết lộ thông tin nội bộ; audit log đủ điều tra và không chứa secret.
- [ ] Test bao phủ method, endpoint, principal, tenant, object, field, workflow và side effect.

Phân quyền method và endpoint quản trị hiệu quả khi mỗi action có permission rõ, mọi đường vào đều được bảo vệ ở server và service vẫn kiểm tra object cùng điều kiện nghiệp vụ. Kết hợp ma trận endpoint, deny-by-default, method security, quyền quản trị tách biệt và kiểm thử qua toàn bộ request path giúp giảm nguy cơ leo thang đặc quyền và truy cập trái phép vào chức năng nhạy cảm.
