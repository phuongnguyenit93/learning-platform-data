# Domain object authorization trong Spring Security Method Security

## 1. Domain object authorization là gì?

**Domain object authorization** (phân quyền trên đối tượng nghiệp vụ) là việc kiểm tra **một chủ thể có được thực hiện một hành động cụ thể trên một đối tượng dữ liệu cụ thể hay không**. Ví dụ: người dùng có được đọc đơn hàng số 42, phê duyệt hóa đơn 77, tải tài liệu của dự án A hoặc sửa một bản ghi thuộc tenant khác hay không.

Trong hệ thống OAuth 2.0/OIDC, **access token** có thể chứng minh client được cấp scope **orders.read**, và Spring Security có thể ánh xạ scope thành **SCOPE_orders.read**. Tuy nhiên, scope này chỉ trả lời một phần câu hỏi: **được phép gọi loại chức năng nào**. Nó không tự trả lời **được phép đọc đơn hàng nào**.

Ví dụ:

~~~http
GET /api/orders/42 HTTP/1.1
Host: orders.example.test
Authorization: Bearer <VALID_ACCESS_TOKEN>
~~~

Giả sử token hợp lệ, có **SCOPE_orders.read**, nhưng đơn hàng 42 thuộc người dùng hoặc tổ chức khác. API vẫn phải **từ chối truy cập**, dù token đã được xác thực và scope hợp lệ.

Mục tiêu của bài học:

- Phân biệt **authentication, scope/role authorization và domain object authorization**.
- Hiểu lỗi **Broken Object Level Authorization (BOLA)**, thường gắn với **Insecure Direct Object Reference (IDOR)**.
- Thiết kế policy dựa trên **principal, hành động, tài nguyên, tenant và quan hệ nghiệp vụ**.
- Thực thi policy trong **Spring Security Method Security**, bao gồm **@PreAuthorize**, **@PostAuthorize**, **@PreFilter**, **@PostFilter** và **hasPermission**.
- Sử dụng **query scoping** và **transaction** để tránh đọc quá nhiều dữ liệu, lộ danh sách hay lỗi tranh chấp trạng thái.
- Liên kết phân quyền với **JWT/opaque access token, issuer, audience, scope, thu hồi và phòng chống token bị đánh cắp**.
- Xây dựng kiểm thử cho cả **HTTP, service method, repository, multi-tenant và concurrency**.

> Nguyên tắc trọng tâm: **Quyền gọi một endpoint không đồng nghĩa quyền thao tác trên mọi đối tượng mà endpoint có thể nhận diện.**

## 2. Các tầng kiểm tra bảo mật cần đi cùng nhau

Một API thường có ít nhất bốn tầng:

| Tầng | Câu hỏi | Ví dụ |
|---|---|---|
| **Authentication** | Ai hoặc client nào đang gọi? Credential có hợp lệ? | JWT ký đúng, issuer tin cậy, chưa hết hạn |
| **Token-level authorization** | Token được phát hành cho API và quyền nào? | aud=orders-api, scope=orders.read |
| **Function-level authorization** | Chủ thể được gọi hành động này không? | Có SCOPE_orders.approve hoặc vai trò approver |
| **Object-level authorization** | Đối tượng cụ thể có nằm trong phạm vi chủ thể được phép? | Order 42 thuộc tenant A và người gọi có quyền duyệt order 42 |

Ngoài ra còn **business invariants**: order đã giao thì không được hủy; hóa đơn quá hạn phê duyệt phải qua quy trình đặc biệt. Những điều kiện này có thể nằm chung trong một domain policy nhưng cần được phân biệt rõ với xác thực danh tính.

~~~mermaid
flowchart TD
    A[HTTP request + access token] --> B{Token hợp lệ về chữ ký hoặc introspection?}
    B -- Không --> X[401 Unauthorized]
    B -- Có --> C{Đúng issuer, audience, token type, thời hạn?}
    C -- Không --> X
    C -- Có --> D[Chuyển claims thành Authentication/authorities]
    D --> E{Được gọi hành động này?}
    E -- Không --> Y[403 Forbidden]
    E -- Có --> F[Tra đối tượng trong đúng tenant/phạm vi]
    F --> G{Có quan hệ/quyền trên đối tượng?}
    G -- Không --> Z[Từ chối hoặc trả 404 theo chính sách]
    G -- Có --> H{Trạng thái nghiệp vụ cho phép?}
    H -- Không --> I[Trả lỗi nghiệp vụ phù hợp]
    H -- Có --> J[Thực hiện thao tác và ghi audit]
~~~

**Spring Security Method Security** phù hợp để thực thi những quy tắc gần service/domain, tránh chỉ đặt logic ở controller. Tuy nhiên, annotation không tự bảo vệ mọi truy vấn SQL hoặc mọi luồng gọi nội bộ: code cần bảo đảm **mọi đường truy cập dữ liệu** tuân theo policy.

## 3. BOLA/IDOR: vì sao kiểm tra scope vẫn có thể thất bại?

Một mẫu lỗi phổ biến:

~~~java
@RestController
class OrderController {
    private final OrderRepository orderRepository;

    @GetMapping("/api/orders/{id}")
    @PreAuthorize("hasAuthority('SCOPE_orders.read')")
    Order get(@PathVariable UUID id) {
        return orderRepository.findById(id).orElseThrow();
    }
}
~~~

Đoạn code là ví dụ **cố ý thiếu bảo vệ**, không được sử dụng trong production. Nó chỉ kiểm tra caller có scope **orders.read**, rồi lấy order theo ID bất kỳ. Nếu người dùng A thay ID của đơn hàng mình bằng ID thuộc người dùng B, API có thể trả về dữ liệu của B.

~~~text
Người dùng A:
  tenant = tenant-a
  subject = user-a
  scope = orders.read

Order 100:
  tenant = tenant-a
  owner  = user-a       -> Có thể đọc

Order 101:
  tenant = tenant-a
  owner  = user-b       -> Không nhất thiết được đọc

Order 200:
  tenant = tenant-b
  owner  = user-c       -> Không được đọc nếu không có ủy quyền rõ ràng
~~~

**BOLA** xuất hiện khi API không kiểm tra quyền ở mức từng đối tượng. **IDOR** mô tả tình huống API để caller tham chiếu trực tiếp đến một đối tượng (bằng ID, path, document key...) nhưng không thực thi đúng kiểm soát truy cập. Hai thuật ngữ liên quan chặt chẽ, dù phạm vi phân loại không hoàn toàn giống nhau.

Điều cần hiểu đúng:

- **UUID không đoán được không phải phân quyền.** ID có thể lộ qua URL, log, tài liệu, lịch sử trình duyệt hoặc liên kết được chia sẻ.
- **JWT hợp lệ không chứng minh quyền sở hữu object.**
- **Có ROLE_ADMIN ở một ứng dụng khác không cho phép làm admin tại API hiện tại.**
- **Ẩn nút trong giao diện không bảo vệ API**; caller có thể gửi HTTP request trực tiếp.
- **Kiểm tra quyền chỉ khi GET** là thiếu; PATCH, DELETE, export, download, bulk update và các luồng job cũng phải được kiểm soát.

## 4. Mô hình policy: ai, làm gì, đối tượng nào, trong điều kiện nào?

Một domain authorization decision có thể được biểu diễn:

~~~text
decision = permit(
    subject,
    action,
    resource,
    environment,
    trustedPolicies
)
~~~

### 4.1. Subject: người gọi đã xác thực

Subject có thể là:

- Người dùng đăng nhập qua OAuth/OIDC với **iss**, **sub**, tenant và các authorities.
- Service account dùng **client_credentials** grant; thường không có “người dùng sở hữu đơn” theo nghĩa thông thường.
- Một hệ thống tự động thực hiện tác vụ được ủy quyền, mang danh tính dịch vụ và ngữ cảnh delegation rõ ràng.
- Một admin đang thực hiện chức năng quản trị có kiểm soát, được giám sát bằng audit.

Không lấy subject từ tham số do caller tự khai:

~~~http
GET /api/orders/42?userId=owner-of-order-42
Authorization: Bearer <TOKEN_OF_SOMEONE_ELSE>
~~~

Giá trị **userId** trong query có thể là tham số lọc hay dữ liệu nghiệp vụ, nhưng **không được tự động thay danh tính đã xác thực**. Principal phải được dẫn xuất từ SecurityContext và claims/metadata đã xác minh hoặc từ một cơ chế delegation tin cậy.

### 4.2. Action: hoạt động được phép

Một policy nên dùng hành động rõ ràng:

~~~text
order:read
order:create
order:update
order:cancel
order:approve
order:export
order:delete
~~~

**Scope** có thể giới hạn client được phép gọi hành động; **role/permission** có thể mô tả chức trách người dùng; **object policy** quyết định hành động với đối tượng cụ thể.

Ví dụ: người gọi có **SCOPE_orders.approve** và **ROLE_FINANCE_APPROVER** nhưng hóa đơn thuộc tenant khác vẫn phải bị từ chối, trừ khi có delegation được xác minh.

### 4.3. Resource: đối tượng và thuộc tính đáng tin cậy

Resource có thể có:

~~~text
Order {
  id = 42
  tenantId = tenant-a
  ownerId = user-b
  projectId = project-7
  status = PENDING_APPROVAL
  amount = 500000
}
~~~

Những thuộc tính dùng cho phân quyền phải được lấy từ **nguồn dữ liệu authoritative**. Không tin bản sao object do client gửi nếu client có thể thay **tenantId, ownerId, projectId**.

### 4.4. Environment: điều kiện ngữ cảnh

Có thể bao gồm:

- Thời gian hiệu lực delegation hoặc quyền chia sẻ.
- Trạng thái tài khoản, tình trạng khóa hoặc nghỉ việc.
- Mức xác thực hiện tại, yêu cầu step-up/MFA cho tác vụ nhạy cảm.
- Phạm vi môi trường production/staging.
- Trạng thái nghiệp vụ của order/document.

IP address, User-Agent hoặc vị trí mạng có thể hỗ trợ risk scoring nhưng không nên được xem là bằng chứng sở hữu object duy nhất.

### 4.5. RBAC, ABAC và ReBAC

| Mô hình | Điều kiện chính | Khi phù hợp |
|---|---|---|
| **RBAC** | Role của subject | Các chức năng có quyền tương đối cố định |
| **ABAC** | Thuộc tính subject, object, action và environment | Multi-tenant, điều kiện amount/status/department |
| **ReBAC** | Quan hệ giữa subject và object hoặc nhóm/tổ chức | Chia sẻ tài liệu, membership dự án, cấp quyền qua tổ chức |
| **ACL** | Danh sách subject/group có quyền với object | Chia sẻ object cụ thể hoặc quyền ngoại lệ |

Một hệ thống có thể dùng nhiều mô hình. Ví dụ policy “được sửa tài liệu nếu có scope documents.write, người dùng là owner **hoặc** có membership EDITOR trong workspace, tài liệu chưa bị khóa” là sự phối hợp role, quan hệ và thuộc tính.

## 5. Nguồn danh tính tin cậy từ JWT và opaque token

### 5.1. JWT access token

Resource server có thể nhận JWT như:

~~~json
{
  "iss": "https://identity.example.test/tenant-a",
  "sub": "user-42",
  "aud": ["orders-api"],
  "scope": "orders.read orders.approve",
  "client_id": "portal-app",
  "tenant_id": "tenant-a",
  "iat": 1795400000,
  "exp": 1795400300
}
~~~

Chỉ sau khi **JwtDecoder** xác minh chữ ký, **issuer**, **audience**, exp/nbf, loại token và chính sách khác, ứng dụng mới nên diễn giải claims thành danh tính/quyền.

Trong Spring Security, scope thường được ánh xạ thành các **GrantedAuthority** có tiền tố **SCOPE_**, ví dụ **SCOPE_orders.read**.

**Quan trọng:** **sub** có phạm vi theo **issuer**; nếu nhận token từ nhiều AS, hai giá trị sub giống nhau không chắc là cùng người. Khóa ánh xạ tài khoản ngoài hệ thống nên xét cặp **(iss, sub)** hoặc một internal ID đã liên kết an toàn.

Claim **tenant_id** chỉ đáng tin nếu **AS tin cậy cấp nó theo chính sách được kiểm soát**. Đừng coi mọi custom claim đều có cùng mức đảm bảo; một claim do người dùng tự sửa trong profile không nên được phép tạo quyền quản trị.

### 5.2. Opaque access token

Với opaque access token, API thường gọi **introspection endpoint** đáng tin cậy. Phản hồi có thể chứa **active**, subject, scope và các metadata khác. Tuy nhiên **active=true chưa đồng nghĩa** quyền thao tác với order cụ thể.

RS vẫn cần:

1. Chắc chắn hỏi **đúng AS** và sử dụng kênh/xác thực introspection phù hợp.
2. Kiểm tra token dành cho API/resource hiện tại bằng audience/resource binding phù hợp.
3. Xác định subject/client và authorities theo chính sách.
4. Áp dụng domain object authorization từ database/quan hệ nghiệp vụ.

Nếu introspection cache kết quả active, quyền bị thu hồi có thể chưa phản ánh tới API trước khi TTL cache hết hạn. Điều này cần được tính đến khi quản lý quyền nhạy cảm.

### 5.3. ID token và refresh token không dùng để gọi API

**OIDC ID token** dành cho OIDC client xác minh sự kiện đăng nhập; **refresh token** dành cho token endpoint để xin token mới. Resource server phải đòi **access token** đúng issuer/audience/type. Không được nhận ID token có trường email và roles rồi cho truy cập order chỉ vì JWT hợp lệ.

**Sender-constrained access token** như DPoP/mTLS vẫn cần các kiểm tra bằng chứng sở hữu khóa/chứng chỉ ngoài chữ ký JWT; domain authorization diễn ra **sau** các kiểm tra xác thực token đó. Nó không thay thế kiểm soát theo tenant, object và quan hệ.

## 6. Spring Method Security hoạt động như thế nào?

Spring Security hỗ trợ thực thi policy ở mức phương thức, thường qua **AOP interception/proxy**. Có thể kích hoạt bằng:

~~~java
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;

@Configuration
@EnableMethodSecurity
public class MethodSecurityConfig {
}
~~~

Với cấu hình Spring Security hiện đại, **@EnableMethodSecurity** hỗ trợ **@PreAuthorize**, **@PostAuthorize**, **@PreFilter**, **@PostFilter** theo cấu hình pre/post được bật. Nên kiểm tra tài liệu phiên bản đang chạy nếu tổ chức sử dụng cấu hình tùy biến.

**@PreAuthorize** đánh giá biểu thức trước khi phương thức thực thi. Ví dụ:

~~~java
@PreAuthorize("hasAuthority('SCOPE_orders.read')")
public OrderDto getOrder(UUID orderId) {
    // ...
}
~~~

Điều này bảo vệ **loại hành động**, nhưng chưa kiểm tra owner/tenant của **orderId**. Cần thêm domain guard ở service hoặc query scoping.

### 6.1. Proxy, lời gọi nội bộ và các lối đi vòng

Method Security dựa trên proxy trong cấu hình phổ biến. Vì vậy:

- Gọi một public method được bảo vệ **qua Spring proxy** thì interceptor có cơ hội chạy.
- **Self-invocation**: một method trong cùng object gọi trực tiếp method được annotate có thể **bỏ qua proxy**, khiến annotation không được áp dụng.
- Một object tự tạo bằng **new** ngoài Spring container có thể không được intercept.
- Private/final methods và kiểu proxy có thể làm annotation không được áp dụng như mong đợi; cần kiểm tra tương thích proxy, visibility và phiên bản.
- Một đường truy cập khác như batch job, message consumer hay scheduled task có thể gọi repository/domain mà **không đi qua service method đã bảo vệ**.

Giải pháp là đặt policy ở ranh giới domain/service rõ ràng, tổ chức bean gọi qua proxy khi dựa vào Method Security và **kiểm thử đường đi thực tế**. Không coi annotation là thay thế cho toàn bộ thiết kế truy cập dữ liệu.

### 6.2. Cách lấy parameter trong SpEL

Một biểu thức dùng **#orderId** phụ thuộc vào việc Spring có thể xác định tên tham số từ metadata/biên dịch hay annotation phù hợp:

~~~java
@PreAuthorize("@orderAccess.canRead(authentication, #orderId)")
public OrderDto getOrder(UUID orderId) {
    // ...
}
~~~

Nếu runtime không có thông tin tên tham số, expression có thể không nhận được **#orderId**. Với Java, cần biên dịch có parameter metadata phù hợp hoặc dùng annotation tham số mà Method Security hỗ trợ, và **kiểm thử chính xác biểu thức**. Đừng xử lý lỗi parameter binding bằng cách thay thế kiểm tra owner/tenant bằng điều kiện luôn đúng.

## 7. Cách 1: policy bean được gọi từ @PreAuthorize

Spring Security cho phép gọi một Spring bean trong expression. Ví dụ áp dụng policy cho method đọc order:

~~~java
@Service
public class OrderService {
    private final OrderRepository repository;

    public OrderService(OrderRepository repository) {
        this.repository = repository;
    }

    @PreAuthorize(
        "hasAuthority('SCOPE_orders.read') " +
        "and @orderAccess.canRead(authentication, #orderId)"
    )
    public OrderDto getOrder(UUID orderId) {
        return OrderDto.from(
            repository.findById(orderId).orElseThrow()
        );
    }
}
~~~

Policy bean:

~~~java
@Component("orderAccess")
public class OrderAccess {
    private final OrderRepository repository;
    private final ActorResolver actors;

    public OrderAccess(
            OrderRepository repository,
            ActorResolver actors) {
        this.repository = repository;
        this.actors = actors;
    }

    public boolean canRead(
            Authentication authentication,
            UUID orderId) {
        Actor actor = actors.fromTrustedAuthentication(authentication);
        return repository.existsReadableById(
            orderId,
            actor.tenantId(),
            actor.subjectId()
        );
    }
}
~~~

Các kiểu **ActorResolver**, **Actor**, **OrderRepository** và **OrderDto** ở trên là **domain abstractions minh họa**, không phải classes mặc định của Spring. Chúng cần được triển khai theo database và hợp đồng danh tính thực tế. Hàm **existsReadableById** phải tính đủ owner, delegation và quan hệ membership theo policy.

Ý nghĩa:

1. **hasAuthority** đòi scope cấp chức năng đọc.
2. **orderAccess.canRead** xác định subject có quyền đọc **orderId cụ thể**.
3. Method được gọi chỉ nếu cả hai điều kiện đúng.

### 7.1. Điểm yếu của cách kiểm tra trước rồi đọc lại

Mẫu trên có thể **truy vấn hai lần**:

~~~text
T1: existsReadableById(orderId, tenant, actor) -> true
T2: quyền chia sẻ hoặc owner thay đổi
T3: findById(orderId) -> trả object theo trạng thái mới
~~~

Đây là rủi ro **time-of-check/time-of-use (TOCTOU)**: kiểm tra quyền và thực hiện thao tác có thể dựa trên hai snapshot khác nhau. Với dữ liệu nhạy cảm hoặc cập nhật trạng thái, nên ưu tiên **query scoping trong cùng giao dịch**, điều kiện cập nhật atomically, hoặc locking/consistency mechanism phù hợp.

Ngoài ra, method bên trong đang dùng **findById không có tenant filter**, nên nếu có logic khác vô tình bỏ annotation, dữ liệu có thể lộ. Phương án an toàn hơn là **truy xuất object trong phạm vi đã được phép ngay từ repository**, như phần tiếp theo.

## 8. Cách 2: query scoping và domain policy trong transaction

Đối với domain object authorization, cách mạnh hơn là **không truy xuất object ngoài phạm vi được phép** ngay từ truy vấn.

### 8.1. Truy xuất một order được phép đọc

Pseudocode Java/Spring:

~~~java
@Service
public class OrderService {
    private final OrderRepository orders;
    private final ActorResolver actors;

    @PreAuthorize("hasAuthority('SCOPE_orders.read')")
    @Transactional(readOnly = true)
    public OrderDto read(
            UUID orderId,
            Authentication authentication) {

        Actor actor = actors.fromTrustedAuthentication(authentication);

        Order order = orders.findReadableById(
                orderId,
                actor.tenantId(),
                actor.subjectId()
            )
            .orElseThrow(() -> new NotFoundException("Order not found"));

        return OrderDto.from(order);
    }
}
~~~

Trong ví dụ này, **query scoping** nằm trong **findReadableById**. Repository phải bảo đảm trả dữ liệu chỉ khi subject có quyền, không chỉ so khớp tenant một cách hình thức.

SQL minh họa cho policy “owner hoặc thành viên có quyền đọc dự án”:

~~~sql
SELECT o.*
FROM orders o
WHERE o.id = :order_id
  AND o.tenant_id = :trusted_tenant_id
  AND (
      o.owner_id = :trusted_subject_id
      OR EXISTS (
          SELECT 1
          FROM project_memberships pm
          WHERE pm.project_id = o.project_id
            AND pm.tenant_id = o.tenant_id
            AND pm.user_id = :trusted_subject_id
            AND pm.can_read_orders = TRUE
            AND pm.revoked_at IS NULL
      )
  );
~~~

Đây là SQL **mô hình hóa policy**, cần điều chỉnh schema/DB engine, group membership, expiry, trạng thái tài khoản và authorization của sản phẩm. Hai tham số **trusted_tenant_id** và **trusted_subject_id** phải lấy từ principal đã xác thực hoặc internal mapping, **không** từ query parameter do caller tự quyết.

Lợi ích:

- Object trái quyền **không được trả về từ repository**.
- Hạn chế lộ dữ liệu do các bước DTO mapping/serialization/cache được gọi trước khi check.
- Dễ áp dụng cho danh sách có phân trang bằng cùng điều kiện truy vấn.
- Có thể dùng transaction/locking để gắn kiểm tra với thao tác dữ liệu.

### 8.2. Vì sao đôi khi trả 404 thay vì 403?

Với object không thuộc phạm vi của caller, API có thể chọn **404 Not Found** để không tiết lộ object có tồn tại trong tenant khác. Đây là quyết định **thiết kế giao thức/kinh doanh**, không phải một “mẹo” thay authorization.

- **401:** token thiếu hoặc không hợp lệ cho endpoint protected.
- **403:** principal đã xác thực nhưng bị từ chối vì không có quyền.
- **404:** có thể dùng để tránh tiết lộ sự tồn tại của object mà caller không được phép xem, áp dụng nhất quán.

Dù trả 403 hay 404, **không được truy xuất/trả body nhạy cảm** trước khi quyết định. Nên tránh phân biệt object không tồn tại với object không được phép qua response time/error details một cách không cần thiết; vẫn cần audit đầy đủ ở phía server.

### 8.3. Vì sao repository filter không thay toàn bộ policy?

Repository filter tốt cho những điều kiện có thể biểu diễn bằng SQL (tenant, owner, membership, status). Nhưng một số policy cần:

- Thời hạn delegation hoặc role cấp qua service khác.
- Quy tắc phân tách nhiệm vụ (người tạo không được phê duyệt chính mình).
- Đòi hỏi MFA gần đây hoặc step-up authentication.
- Ràng buộc nghiệp vụ phức tạp sau khi tải aggregate.

Các điều kiện đó cần kiểm tra bổ sung ở domain/service **trong ranh giới transaction thích hợp**, không chỉ dựa vào WHERE tenant_id.

## 9. Bảo vệ thao tác thay đổi dữ liệu (write authorization)

Mẫu chỉ kiểm tra ở controller hoặc chỉ lọc GET thường bỏ sót những đường **UPDATE/DELETE/APPROVE**.

Một thao tác phê duyệt order có thể cần:

- Access token có **SCOPE_orders.approve**.
- Principal có role/permission approver được AS/identity system tin cậy cấp.
- Order thuộc tenant được phép.
- Caller có quan hệ approver với project hoặc bộ phận.
- Caller không phải người đã tạo order (separation of duties).
- Order đang ở trạng thái **PENDING**.
- Giá trị đơn hàng không vượt hạn mức phê duyệt của caller.

~~~mermaid
flowchart TD
    A[Approve order ID] --> B{Đủ scope và permission chức năng?}
    B -- Không --> X[403]
    B -- Có --> C[Load order trong đúng tenant có lock/transaction]
    C --> D{Được phép với đối tượng?}
    D -- Không --> X
    D -- Có --> E{Trạng thái và hạn mức hợp lệ?}
    E -- Không --> Y[Lỗi nghiệp vụ phù hợp]
    E -- Có --> F[Chuyển trạng thái và lưu cùng transaction]
~~~

Pseudocode:

~~~java
@Service
public class OrderApprovalService {
    private final OrderRepository orders;
    private final ActorResolver actors;
    private final OrderPolicy policy;

    @PreAuthorize(
        "hasAuthority('SCOPE_orders.approve') " +
        "and hasAuthority('PERM_orders.approve')"
    )
    @Transactional
    public void approve(
            UUID orderId,
            Authentication authentication) {

        Actor actor = actors.fromTrustedAuthentication(authentication);

        Order order = orders.findForUpdateByIdAndTenantId(
                orderId, actor.tenantId()
            )
            .orElseThrow(() -> new NotFoundException("Order not found"));

        if (!policy.canApprove(actor, order)) {
            throw new AccessDeniedException("Not permitted");
        }

        order.approve(actor.subjectId());
        orders.save(order);
    }
}
~~~

Đây là **pseudocode định hướng**, còn thiếu imports, constructors và domain classes. Hàm **findForUpdateByIdAndTenantId** hàm ý thao tác đọc có locking/consistency phù hợp với database, không phải method chuẩn của Spring Data có sẵn. Nếu policy cần kiểm tra membership từ bảng khác, cần bảo đảm chính các trạng thái liên quan có tính nhất quán thích hợp, không chỉ lock hàng order.

### 9.1. Chống TOCTOU khi permission thay đổi

Ngay cả transaction cũng không tự bảo đảm toàn bộ quan hệ membership không đổi nếu dữ liệu quyền nằm ở bảng/service khác, hoặc transaction isolation không phù hợp. Có thể cần:

- Khóa hoặc version của object và những quan hệ quyền liên quan.
- Optimistic locking cho bản ghi trạng thái quan trọng.
- Conditional update theo tenant, owner, status và version.
- Thiết kế quyết định quyền ở một policy/authorization service có tính nhất quán rõ ràng.
- Kiểm soát external authorization service failure: **không mặc định cho phép** khi không xác minh được quyền.

### 9.2. Không tin ownerId/tenantId khi tạo hoặc sửa object

Request như:

~~~json
{
  "title": "New order",
  "tenantId": "tenant-b",
  "ownerId": "some-other-user"
}
~~~

không được khiến server tạo record thuộc tenant B chỉ vì JSON chứa chuỗi đó. Nếu subject chỉ được phép tạo trong tenant A, server phải xác định owner/tenant từ **trusted principal + policy**, hoặc kiểm tra rõ delegation hợp lệ khi client yêu cầu thay người khác.

Đối với PATCH/PUT, không cho phép caller sửa **ownerId, tenantId, approvalStatus, accessControlList** ngoài các workflow phân quyền đã định. Mass assignment của trường quyền có thể là đường đi vòng domain object authorization.

## 10. @PostAuthorize: kiểm tra object sau khi phương thức trả về

**@PostAuthorize** cho phép kiểm tra đối tượng kết quả của phương thức qua biến **returnObject** trong Spring Expression Language. Ví dụ về một phương thức **chỉ đọc**:

~~~java
@PostAuthorize(
    "returnObject == null " +
    "or @documentPolicy.canRead(authentication, returnObject)"
)
public DocumentDto readDocument(UUID documentId) {
    return documentRepository.findById(documentId)
        .map(DocumentDto::from)
        .orElse(null);
}
~~~

**@documentPolicy** là bean tự xây dựng và phải đánh giá đúng issuer/subject/tenant, owner, membership, thời hạn sharing và chính sách domain. Đoạn code không phải giải pháp hoàn chỉnh; ví dụ trả null chỉ minh họa biểu thức returnObject, còn production nên có chiến lược xử lý not found và denied rõ ràng.

Quá trình logic:

~~~text
Caller
  -> Method được chạy, trả object
  -> Method Security kiểm tra returnObject
  -> Nếu không được phép: ném AccessDeniedException
  -> Nếu được phép: trả object cho caller
~~~

### 10.1. Giới hạn của @PostAuthorize

- **Phương thức đã chạy trước khi policy được kiểm tra**. Nó có thể đã gọi DB, service khác hoặc tạo log chứa dữ liệu.
- Không dùng **@PostAuthorize làm biện pháp duy nhất cho thao tác ghi** như chuyển tiền, phê duyệt, gửi email, xóa tệp: tác dụng phụ có thể đã xảy ra trước khi bị từ chối.
- Nếu đối tượng được cache, publish event, gửi đến hệ thống khác hoặc log trước khi expression đánh giá, đã có nguy cơ lộ dữ liệu.
- Nếu method trả dữ liệu rất lớn, toàn bộ object có thể đã được tải/serialize nội bộ gây chi phí và tăng bề mặt lộ dữ liệu.
- Nếu policy phụ thuộc vào trạng thái DB, trạng thái có thể đổi giữa lúc load và lúc check.

**Ưu tiên:** kiểm tra phân quyền trước hoặc **thực hiện truy vấn có scope ngay từ repository**. Dùng @PostAuthorize chủ yếu như lớp bảo vệ bổ sung cho **read-only method** có đầu ra nhỏ, khi mô hình và performance cho phép.

### 10.2. Khi nào nên kiểm tra bằng object thay vì ID?

Một policy có thể yêu cầu nhiều thuộc tính của object, ví dụ **classification**, **owner**, **project**, **status**, **document ACL**. Việc đưa object thật đã được load vào policy giúp kiểm tra đầy đủ hơn việc chỉ so ID.

Nhưng logic vẫn phải được đặt trong ranh giới tin cậy: object được tải từ database authoritative, không phải object do client tự gửi; các thay đổi stateful cần thực thi cùng transaction/lock phù hợp.

## 11. @PreFilter, @PostFilter và vấn đề danh sách

Spring Security Method Security có **@PreFilter** và **@PostFilter** để lọc các phần tử của collection phù hợp chính sách.

Ví dụ đọc một tập tài liệu nhỏ:

~~~java
@PostFilter("@documentPolicy.canRead(authentication, filterObject)")
public List<DocumentDto> recentDocuments() {
    // Chỉ minh họa một tập nhỏ đã được tải từ nguồn tin cậy.
    return repository.findRecentDocuments();
}
~~~

**filterObject** là biến expression đại diện cho từng phần tử đang được lọc. Cú pháp và loại collection được hỗ trợ phụ thuộc vào API/phiên bản; hãy kiểm thử với chính kiểu trả về của method.

Đối với input collection:

~~~java
@PreFilter(
    value = "@documentPolicy.canUpdate(authentication, filterObject)",
    filterTarget = "documents"
)
public void updateMany(List<Document> documents) {
    // Chỉ phù hợp nếu policy chủ đích bỏ qua object không được phép.
}
~~~

### 11.1. Vì sao không nên dùng @PostFilter cho mọi danh sách?

Giả sử API trả về 10.000 hóa đơn của toàn hệ thống rồi PostFilter giữ lại 12 hóa đơn thuộc caller:

- Dữ liệu trái quyền vẫn đã được **đọc vào bộ nhớ**.
- Truy vấn có thể tiêu tốn CPU/RAM lớn dù caller chỉ được xem rất ít.
- **Pagination sai:** lọc sau phân trang có thể khiến trang trả ít phần tử, total count hoặc thứ tự chứa thông tin từ tenant khác.
- Thống kê, export hoặc aggregation có thể bị tính từ dữ liệu chưa được lọc.
- Rủi ro log/cache/serialization dữ liệu trung gian ngoài chủ đích.

Do đó với danh sách lớn, **lọc trong truy vấn** là lựa chọn chính. @PostFilter chỉ thích hợp cho tập nhỏ hoặc một lớp phòng vệ phụ đã được cân nhắc rõ.

### 11.2. Khi nào @PreFilter có thể nguy hiểm?

Nếu phương thức dự kiến **từ chối toàn bộ batch** khi có một phần tử không đủ quyền, nhưng @PreFilter chỉ loại bớt phần tử rồi xử lý phần còn lại, caller có thể nhận thành công một phần ngoài hợp đồng nghiệp vụ. Ví dụ thanh toán batch có thể yêu cầu **all-or-nothing**.

Cần xác định rõ policy:

- **All-or-nothing:** kiểm tra mọi phần tử và từ chối toàn bộ nếu có một phần tử không được phép.
- **Partial processing:** chỉ xử lý phần tử hợp lệ, nhưng API phải trả rõ phần nào thành công/thất bại và không làm lộ thông tin phần tử không được phép.

Không dùng lọc collection như một cách “lặng lẽ bỏ qua lỗi” khi hệ thống tài chính yêu cầu atomicity.

## 12. hasPermission và PermissionEvaluator

Spring Security hỗ trợ biểu thức **hasPermission** nếu cấu hình **PermissionEvaluator** phù hợp. Nó cho phép biểu diễn policy theo **object + permission**:

~~~java
@PreAuthorize("hasPermission(#orderId, 'Order', 'read')")
public OrderDto readOrder(UUID orderId) {
    // ...
}
~~~

Có hai cách kiểm tra thường gặp:

1. Truyền **object** đã có: hasPermission(object, 'read').
2. Truyền **object ID và type**: hasPermission(id, 'Order', 'read').

**Default PermissionEvaluator không tự biết ownership hoặc ACL của hệ thống.** Cần tự triển khai đúng policy, repository và quản lý principal.

### 12.1. Ví dụ lớp triển khai PermissionEvaluator

~~~java
import java.io.Serializable;
import org.springframework.security.access.PermissionEvaluator;
import org.springframework.security.core.Authentication;

public final class OrderPermissionEvaluator
        implements PermissionEvaluator {

    private final OrderRepository orders;
    private final ActorResolver actors;

    public OrderPermissionEvaluator(
            OrderRepository orders,
            ActorResolver actors) {
        this.orders = orders;
        this.actors = actors;
    }

    @Override
    public boolean hasPermission(
            Authentication auth,
            Object target,
            Object permission) {

        if (auth == null || !(target instanceof Order order)) {
            return false;
        }

        Actor actor = actors.fromTrustedAuthentication(auth);

        if ("read".equals(permission)) {
            return canRead(actor, order);
        }
        if ("approve".equals(permission)) {
            return canApprove(actor, order);
        }
        return false;
    }

    @Override
    public boolean hasPermission(
            Authentication auth,
            Serializable targetId,
            String targetType,
            Object permission) {

        if (auth == null || !"Order".equals(targetType)
                || !(targetId instanceof UUID)) {
            return false;
        }

        Actor actor = actors.fromTrustedAuthentication(auth);
        UUID orderId = (UUID) targetId;

        if ("read".equals(permission)) {
            return orders.existsReadableById(
                orderId, actor.tenantId(), actor.subjectId()
            );
        }
        return false;
    }

    private boolean canRead(Actor actor, Order order) {
        // Domain policy: tenant, owner, membership, delegation...
        return actor.tenantId().equals(order.tenantId())
            && actor.subjectId().equals(order.ownerId());
    }

    private boolean canApprove(Actor actor, Order order) {
        // Đây mới là ví dụ đơn giản, cần policy thực tế.
        return canRead(actor, order) && order.isPending();
    }
}
~~~

**Lưu ý:** Các class **OrderRepository**, **Actor**, **ActorResolver**, **Order** là mô hình ứng dụng giả định. Cần import **UUID**, tự triển khai constructor/domain classes và cấu hình expression handler. **canApprove** được minh họa đơn giản; trong nhiều nghiệp vụ người tạo đơn **không được tự phê duyệt**, vì vậy production cần rule khác.

### 12.2. Gắn PermissionEvaluator vào Method Security

Một cách cấu hình cho Spring Security hỗ trợ **MethodSecurityExpressionHandler**:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.access.PermissionEvaluator;
import org.springframework.security.access.expression.method.DefaultMethodSecurityExpressionHandler;
import org.springframework.security.access.expression.method.MethodSecurityExpressionHandler;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;

@Configuration
@EnableMethodSecurity
class MethodSecurityConfiguration {

    @Bean
    static MethodSecurityExpressionHandler methodSecurityExpressionHandler(
            PermissionEvaluator evaluator) {

        DefaultMethodSecurityExpressionHandler handler =
            new DefaultMethodSecurityExpressionHandler();

        handler.setPermissionEvaluator(evaluator);
        return handler;
    }
}
~~~

Đoạn cấu hình thể hiện cách đăng ký expression handler và giả định có bean **PermissionEvaluator** do ứng dụng cung cấp. Tùy phiên bản Spring Security, lifecycle tạo handler và điểm mở rộng có thể khác; cần kiểm tra tài liệu ứng với phiên bản hiện dùng. Với policy đơn giản, dùng **@policyBean.method(authentication, id)** thường dễ đọc, debug và test hơn.

### 12.3. Những giới hạn của PermissionEvaluator

- Một lời gọi hasPermission có thể tạo **một truy vấn DB**. Với danh sách nhiều phần tử, dễ tạo lỗi **N+1 queries**.
- Policy có thể bị gọi ngoài transaction mong muốn.
- Trả về true/false không tự thực hiện **query scoping** cho danh sách.
- Nếu nhận **Object** từ dữ liệu client gửi, cần xác định object có nguồn tin cậy trước khi dùng thuộc tính của nó.
- Việc dùng hasPermission với ID vẫn phải xử lý **concurrency và TOCTOU** khi method sau đó đọc/ghi object.
- **Exception hoặc policy service unavailable** không nên mặc định biến thành allow.

## 13. Truy vấn danh sách, phân trang, tìm kiếm và export

**BOLA không chỉ xảy ra với /{id}.** Danh sách và tìm kiếm cũng có thể lộ dữ liệu ngoài phạm vi người dùng.

### 13.1. Query scoping cho danh sách

Ví dụ SQL:

~~~sql
SELECT o.*
FROM orders o
WHERE o.tenant_id = :trusted_tenant_id
  AND (
      o.owner_id = :trusted_subject_id
      OR EXISTS (
          SELECT 1
          FROM project_memberships pm
          WHERE pm.tenant_id = o.tenant_id
            AND pm.project_id = o.project_id
            AND pm.user_id = :trusted_subject_id
            AND pm.can_read_orders = TRUE
            AND pm.revoked_at IS NULL
      )
  )
ORDER BY o.created_at DESC, o.id DESC
LIMIT :page_size OFFSET :offset;
~~~

Cùng **điều kiện authorization** phải được áp dụng cho:

- Query nội dung từng trang.
- Query **COUNT(*)** dùng tính total elements/pages.
- Query **sort/filter/search**.
- Query **aggregate** như tổng số đơn, tổng giá trị và báo cáo.
- Export CSV/PDF, background jobs, email report và search index.
- Truy vấn join sang tài nguyên phụ; không chỉ bảo vệ bảng chính.

Nếu query trang có tenant filter nhưng query count không có, response vẫn có thể **lộ số lượng object của tenant khác**. Nếu filter ở Java sau phân trang, kết quả có thể ít phần tử, bỏ sót bản ghi hợp lệ và gây metadata sai.

### 13.2. Search index và cache

Khi tìm kiếm qua Elasticsearch/OpenSearch hoặc cache kết quả:

- Truy vấn index phải mang điều kiện tenant/ACL hoặc filter phía service bảo đảm không xuất object không được phép.
- Kiểm tra quyền ở thời điểm **trả kết quả**, không chỉ lúc indexing vì ACL có thể thay đổi.
- Cache một list hoặc object cần key chứa **ngữ cảnh principal/tenant/policy** phù hợp; không cache kết quả của tenant A rồi phục vụ cho B.
- Dữ liệu được chia sẻ theo thời hạn cần có cơ chế invalidation khi revoke.
- Không gửi raw query đã chứa credential hoặc claims nhạy cảm vào search telemetry.

### 13.3. Bulk operations

Với API như:

~~~http
POST /api/orders/bulk-cancel
Content-Type: application/json
Authorization: Bearer <ACCESS_TOKEN>

{"ids": ["id-1", "id-2", "id-3"]}
~~~

Server không chỉ đòi **SCOPE_orders.cancel**, mà còn phải kiểm tra **quyền trên từng order ID**, trạng thái, hạn mức và ràng buộc batch. Không cho phép “một trong ba đơn hợp lệ” làm điều kiện để hủy toàn bộ ba đơn. Quyết định all-or-nothing hay partial phải được đặc tả và kiểm thử.

## 14. Multi-tenant, tổ chức và các quan hệ chia sẻ

### 14.1. Tenant isolation là điều kiện cần nhưng chưa đủ

Nếu subject thuộc **tenant A**, query **WHERE tenant_id=A** ngăn truy cập tenant B. Tuy nhiên hai người cùng tenant A vẫn có thể có quyền khác nhau theo owner/project/department.

~~~text
Tenant A:
  user-1: MEMBER project-X
  user-2: ADMIN project-Y
  Order-X: thuộc project-X
  Order-Y: thuộc project-Y
~~~

Một policy “cùng tenant là xem được tất cả” có thể quá rộng. Tùy sản phẩm, chỉ project members hoặc người nhận delegation mới được xem.

### 14.2. Quan hệ chia sẻ cần được biểu diễn rõ

Ví dụ ReBAC:

~~~text
User u-42
   |
   +-- member of project P với role EDITOR
          |
          +-- project P owns Document D
                    |
                    +-- allowed: read, update
                    +-- denied: delete unless OWNER
~~~

Dữ liệu quan hệ có thể lưu trong bảng **project_memberships**, **document_permissions**, hoặc một graph authorization service. Cần kiểm tra:

- Membership có còn active?
- Quyền cho chính object hay được kế thừa từ parent?
- Delegation có thời hạn và chỉ dành cho một action?
- Một principal có thể đồng thời thuộc nhiều tenant không?
- Khi chuyển tenant trong UI, token/session có được phép chuyển ngữ cảnh hay phải xác thực lại?
- Các quyền chia sẻ từ bên ngoài tổ chức có được đánh dấu và kiểm toán không?

### 14.3. Nhiều issuer và account linking

Giả sử:

~~~text
Issuer A: sub = 123
Issuer B: sub = 123
~~~

Hai subject này **không mặc nhiên là cùng một người**. Trong database, nếu dùng chỉ **sub=123** làm key ownership, một token từ issuer B có thể bị ánh xạ nhầm sang dữ liệu của issuer A.

Nên gắn danh tính ngoài hệ thống với cặp **(issuer, subject)** hoặc một internal account ID được tạo qua **account linking đáng tin cậy**. Không nối tài khoản chỉ theo email trùng nhau nếu chưa có xác thực/đồng ý và quy tắc tin cậy phù hợp.

### 14.4. Service account và delegated access

Với grant **client_credentials**, access token thường đại diện cho **client** chứ không phải người dùng. Policy “order.ownerId == token.sub” có thể vô nghĩa.

Đối với service account:

- Xác định client identity và những tenant/resource mà client được phép phục vụ.
- Dùng scope/audience cho service, kèm danh sách delegation hoặc tenant allowlist đáng tin cậy.
- Không cho phép service tự khai **on_behalf_of=user-admin** trong body rồi lấy quyền người dùng nếu không có protocol delegation được bảo vệ.
- Khi gọi downstream service, bảo đảm không biến một access token có audience cho API A thành credential hợp lệ tại API B.

Đây là rủi ro **confused deputy**: một service có quyền mạnh bị caller ít quyền lợi dụng để truy cập đối tượng mà caller không được phép.

## 15. Các luồng ngoài HTTP vẫn cần domain authorization

Method security có thể giúp bảo vệ public service methods, nhưng policy cần bao phủ mọi đường xử lý object:

- REST controllers, GraphQL resolvers, gRPC handlers.
- Background jobs, scheduled tasks và message consumers.
- Export/import pipelines và báo cáo.
- Administrative consoles, support tools và batch migrations.
- Các API nội bộ nhận requests từ service khác.
- WebSocket hoặc long-lived connections nếu có.

Không phải mọi luồng có một **SecurityContext** của người dùng như request HTTP. Trong async processing, ThreadLocal SecurityContext có thể **không tự truyền sang thread khác**. Nếu job làm việc theo danh tính được ủy quyền:

1. Xác định rõ **actor/service principal** và phạm vi quyền tại thời điểm lập lịch.
2. Truyền **authorization context tối thiểu** qua kênh tin cậy hoặc tái xác minh ở lúc thực thi.
3. Xác thực lại những quyền có thể bị thu hồi trước khi thao tác nhạy cảm.
4. Ghi audit actor gốc và service thực thi.
5. Không tự giả mạo SecurityContext như ROLE_ADMIN để bỏ qua policy.

Với Spring, có các cơ chế truyền SecurityContext cho tác vụ được quản lý, nhưng dùng chúng không thay việc đánh giá quyền tại thời điểm xử lý và không biến một worker job thành actor có toàn quyền.

## 16. Token bị đánh cắp, replay và thu hồi ảnh hưởng object policy ra sao?

Một **bearer access token** hợp lệ có thể bị bên khác sử dụng lại khi bị đánh cắp. Domain object authorization **giới hạn phạm vi những object có thể bị truy cập**, nhưng không tự chứng minh request đến từ đúng chủ sở hữu token.

Ví dụ token có scope **orders.read** của user-42 bị lộ:

- Nếu API có object policy, attacker có thể chỉ đọc những order user-42 được phép đọc.
- Nếu API thiếu object policy, attacker có thể đọc thêm nhiều order không thuộc user-42.
- Nhưng dù có object policy hoàn chỉnh, attacker vẫn có thể **đọc order hợp lệ của user-42** bằng token bị đánh cắp.

Vì vậy vẫn cần các lớp khác:

| Lớp bảo vệ | Vấn đề giải quyết |
|---|---|
| TLS/HTTPS | Giảm rủi ro token bị chặn trên đường truyền |
| Access token lifetime ngắn | Giảm thời gian token bị lộ còn sử dụng được |
| Audience và scope tối thiểu | Giới hạn API và chức năng có thể gọi |
| Domain object authorization | Giới hạn object theo principal/tenant/quan hệ |
| Revocation/denylist/introspection | Có thể chặn token sớm theo khả năng triển khai |
| DPoP hoặc mTLS binding | Giảm khả năng sử dụng token bị lộ nếu không có khóa/chứng chỉ |
| Refresh token rotation/sender-constraining | Hạn chế reuse credential dùng để xin token mới |
| Audit và anomaly detection | Hỗ trợ phát hiện/điều tra và thu hồi |

**DPoP/mTLS không thay domain policy**: chứng minh quyền giữ khóa cũng không cho phép client đọc object trái quyền. Ngược lại, domain policy không thay xác minh DPoP proof (htm, htu, iat, jti, ath, binding) hay chứng chỉ mTLS khi hệ thống phát hành sender-constrained token.

### 16.1. Role/ACL thay đổi trong khi JWT còn hạn

Một JWT có thể chứa roles được xác nhận tại thời điểm phát hành. Nếu quyền bị thu hồi sau đó nhưng JWT chưa hết hạn, resource server kiểm tra offline có thể tiếp tục tin roles cũ.

Đối với quyền object nhạy cảm:

- Cân nhắc lưu và kiểm tra **membership/ACL hiện hành ở database** tại thời điểm request.
- Giới hạn thời gian sống access token.
- Khi cần phản ứng nhanh, dùng revocation/denylist hoặc tham vấn policy service.
- Không cache kết quả authorize quá lâu sau khi quyền bị thay đổi.
- Với tác vụ có tác động cao, yêu cầu step-up/re-authentication và quyết định quyền dựa trên trạng thái mới.

Cần định nghĩa mục tiêu nhất quán cho sản phẩm: một số nội dung công khai có thể chấp nhận TTL cache, còn phê duyệt thanh toán không nên dựa vào quyền cũ nhiều phút sau khi đã bị thu hồi.

### 16.2. Trường hợp policy service không khả dụng

Nếu một request cần kiểm tra quyền tại ACL service mà service này timeout, ứng dụng **không được mặc định cho phép** vì “cần duy trì availability”. Nó có thể từ chối an toàn hoặc trả lỗi dịch vụ, có retry và cảnh báo phù hợp. Không nên biến tình huống không xác minh được quyền thành **200 OK**.
## 17. Quy tắc xử lý lỗi, che giấu dữ liệu và audit

Đối với một API nhận access token, nên tách lỗi xác thực với lỗi phân quyền:

| Tình huống | Phản hồi điển hình | Ghi chú |
|---|---|---|
| Không có access token ở endpoint protected | **401 Unauthorized** | Có thể kèm WWW-Authenticate: Bearer |
| Token sai chữ ký/issuer/audience hoặc hết hạn | **401**, thường invalid_token | Không chuyển token không hợp lệ vào object policy |
| Token hợp lệ nhưng thiếu scope để gọi chức năng | **403 Forbidden** | Có thể là insufficient_scope |
| Có scope nhưng không có quyền trên object | **403** hoặc **404** theo chính sách | Không tiết lộ dữ liệu/quan hệ trái quyền |
| Object không tồn tại | **404 Not Found** | Có thể dùng cùng cách phản hồi với object không được phép |
| Actor có quyền nhưng object ở trạng thái không cho phép hành động | Lỗi nghiệp vụ phù hợp, ví dụ **409 Conflict** | Không nên mặc định coi mọi lỗi trạng thái là 403 |
| ACL service không khả dụng | Lỗi vận hành phù hợp, fail closed | Không được “cho qua” vì timeout |

Không nên cung cấp cho caller trái quyền các thông báo như:

~~~json
{
  "error": "access_denied",
  "detail": "Order 42 exists but belongs to VIP tenant B",
  "ownerEmail": "victim@example.test"
}
~~~

Phản hồi trên làm lộ thông tin ngay cả khi HTTP status là 403. Thay vào đó, dùng thông báo chung phù hợp chính sách, còn log nội bộ chứa đủ **mã sự kiện** để hỗ trợ điều tra.

### 17.1. Audit decision mà không lộ token

Một audit event hữu ích có thể chứa:

~~~json
{
  "event": "domain_authorization_denied",
  "requestId": "req-456",
  "action": "order:approve",
  "resourceType": "Order",
  "resourceId": "42",
  "issuerId": "issuer-internal-a",
  "actorId": "internal-account-18",
  "tenantId": "tenant-a",
  "reasonCode": "NOT_PROJECT_APPROVER"
}
~~~

Đây là **ví dụ cấu trúc log**, không phải chuẩn bắt buộc. Trường dữ liệu cần tuân thủ chính sách bảo vệ thông tin của hệ thống. Nếu raw object ID hoặc actor ID nhạy cảm, dùng định danh nội bộ/pseudonym phù hợp và hạn chế người có quyền xem log.

**Không ghi raw JWT, opaque access token, refresh token, Authorization header, private key, PKCE verifier hoặc toàn bộ claims chưa được lọc** vào log. Nếu log một giá trị từ token chưa xác thực, phải giới hạn độ dài/ký tự để tránh log injection.

Các sự kiện cần phân biệt:

- **authentication_failed**: credential không hợp lệ.
- **function_scope_denied**: thiếu scope hoặc authority.
- **domain_object_denied**: đã xác thực, có thể có scope nhưng bị policy từ chối.
- **cross_tenant_access_attempt**: đối tượng thuộc tenant ngoài phạm vi.
- **delegation_expired** hoặc **acl_revoked**: quan hệ quyền không còn active.
- **policy_store_unavailable**: không thể xác minh quyền.
- **domain_action_completed**: thao tác được phép và đã hoàn tất.

Đừng coi mọi lần 404 là tấn công. Một người dùng có thể nhấn liên kết cũ hoặc dùng object đã xóa. Phát hiện bất thường cần tính đến tần suất, mẫu request và bối cảnh.

## 18. Kiểm thử domain object authorization

**Điểm quan trọng nhất:** test không chỉ kiểm tra quyền của người dùng trên **object của chính họ**, mà phải có **negative cases với object nằm ngoài quyền**, trong khi access token và scope vẫn hoàn toàn hợp lệ. Chính những trường hợp đó phát hiện BOLA.

### 18.1. Ma trận end-to-end

| Chủ thể/token | Đối tượng/thao tác | Kỳ vọng |
|---|---|---|
| User A, token hợp lệ, orders.read | Đọc order do A sở hữu | Cho phép |
| User A, token hợp lệ, orders.read | Đọc order của user B cùng tenant | Từ chối nếu policy không có delegation |
| User A, token hợp lệ, orders.read | Đọc order của tenant khác | Từ chối |
| User A, token hợp lệ, thiếu orders.read | Đọc order chính mình | 403 vì thiếu function scope |
| JWT sai chữ ký | Đọc bất kỳ order | 401 trước domain policy |
| JWT đúng chữ ký nhưng sai audience | Đọc order | 401 |
| JWT sai issuer | Đọc order | 401 |
| OIDC ID token thay access token | Đọc order | Bị từ chối theo token type/audience |
| Token hết hạn | Đọc order | 401 |
| User A có project membership READ | Đọc order của project được chia sẻ | Cho phép |
| User A có membership hết hạn | Đọc order cũ từng được chia sẻ | Từ chối |
| User A chỉ có quyền đọc | Cập nhật/xóa order | Từ chối |
| Approver khác người tạo, đủ scope | Duyệt order PENDING đúng tenant và hạn mức | Cho phép |
| Người tạo order | Tự duyệt khi policy cấm self-approval | Từ chối |
| Approver vượt hạn mức | Duyệt order lớn | Từ chối |
| Order đã APPROVED | Duyệt lại | Từ chối theo trạng thái nghiệp vụ |
| Client credentials token | Truy cập object ngoài tenant được ủy quyền | Từ chối |
| Token từ issuer B, cùng sub với issuer A | Đọc order của A | Từ chối, không trộn danh tính |
| User A | GET danh sách phân trang | Chỉ chứa object được phép; total count cũng được lọc |
| User A | Export CSV/báo cáo | Không chứa dữ liệu tenant/user khác |
| User A | Bulk update có một ID trái quyền | Xử lý theo policy all-or-nothing/partial đã thiết kế |
| Quyền chia sẻ bị thu hồi | Sử dụng object ngay sau revoke | Theo mục tiêu nhất quán/thu hồi đã thiết kế |
| ACL service bị timeout | Đọc object được bảo vệ | Không tự cấp quyền |
| Hai requests đồng thời update quyền/object | Quyết định nhất quán, không TOCTOU bypass |
| Gọi service được annotate từ method cùng bean | Đường gọi thực tế không bỏ qua policy |
| Job hoặc event consumer gọi repository | Vẫn kiểm tra actor/delegation phù hợp |

### 18.2. Unit test policy thuần nghiệp vụ

Một domain policy có thể được viết tách khỏi Spring Security, chỉ nhận những đối tượng đáng tin cậy:

~~~java
class OrderPolicy {
    boolean canRead(Actor actor, Order order) {
        boolean sameTenant =
            actor.tenantId().equals(order.tenantId());

        boolean owner =
            actor.subjectId().equals(order.ownerId());

        boolean member =
            actor.canReadProject(order.projectId());

        return sameTenant && (owner || member);
    }
}
~~~

Đây là ví dụ giản lược: **canReadProject** không nên dựa vào danh sách role do client gửi nếu dữ liệu đó không đáng tin cậy; quan hệ phải lấy từ nguồn đã xác minh hoặc DB/policy service.

JUnit test ý tưởng:

~~~java
@Test
void ownerCanReadWithinTenant() {
    assertTrue(policy.canRead(actorA, orderOwnedByA));
}

@Test
void cannotReadOtherTenantDespiteMatchingOwnerId() {
    assertFalse(policy.canRead(actorA, orderInOtherTenant));
}

@Test
void cannotReadPeerOrderWithoutMembership() {
    assertFalse(policy.canRead(actorA, peerOrder));
}

@Test
void membershipExpiredIsNotReadPermission() {
    assertFalse(policy.canRead(actorWithExpiredMembership, projectOrder));
}
~~~

Cần tạo fixtures đầy đủ và test thực tế cho các lớp domain. Ưu điểm là policy thuần nghiệp vụ dễ kiểm thử nhiều trạng thái và ít phụ thuộc vào HTTP framework.

### 18.3. Test Method Security thực sự được kích hoạt

Nếu một test tự gọi object khởi tạo bằng **new**, nó có thể **không đi qua Spring proxy**, nên @PreAuthorize không chạy. Để kiểm tra AOP:

1. Khởi tạo Spring test context có **@EnableMethodSecurity**.
2. Lấy bean service từ context thay vì tự khởi tạo nếu mục tiêu là test interception.
3. Cung cấp Authentication/authorities qua cơ chế test phù hợp.
4. Gọi method được bảo vệ qua bean/proxy, kiểm tra cho phép và **AccessDeniedException** khi thiếu quyền.
5. Thử đường **self-invocation**, controller, async consumer hoặc job nếu những đường đó tồn tại trong sản phẩm.

Một controller test dùng MockMvc và **jwt()** test post-processor có thể xác minh rằng rule **SCOPE_orders.read** hoạt động với Authentication giả lập, nhưng **không chứng minh JwtDecoder thật đã xác minh chữ ký, issuer, audience và token type**. Cần có integration test riêng gửi **JWT được ký bởi khóa thử nghiệm** qua resource server filter chain thực tế.

### 18.4. Integration test SQL/query scoping

Các ca nên chạy với schema/DB engine gần production:

- Query **findReadableById** không trả order của tenant khác, dù ID tồn tại.
- Khi cùng tenant có hai owner, chỉ trả order được phép.
- Membership được cấp/revoke trong DB làm thay đổi kết quả đúng theo chính sách.
- Query **COUNT(*)**, aggregate, sort và pagination dùng cùng scope.
- Khi quan hệ chia sẻ bị xóa, cache/search index không trả object đã mất quyền quá TTL policy cho phép.
- Khóa optimistic/pessimistic hoặc update có điều kiện ngăn thay đổi trạng thái khi quyền bị sửa đồng thời.

Nên có **test concurrency** hoặc kiểm tra isolation cho những thao tác giá trị cao, không chỉ test tuần tự.

## 19. Case study: API phê duyệt hóa đơn đa tenant

Một công ty cung cấp SaaS xử lý hóa đơn cho hai tenant:

~~~text
Tenant A:
  Employee Alice
  Approver Bình
  Invoice INV-A-101:
    createdBy = Alice
    amount = 8.000.000 VND
    status = PENDING

Tenant B:
  Approver Chi
  Invoice INV-B-202:
    amount = 4.000.000 VND
    status = PENDING
~~~

Chính sách:

1. Caller phải có access token hợp lệ, issuer tin cậy, audience **invoices-api**.
2. Token phải có **SCOPE_invoices.approve**.
3. Principal phải có permission **invoices.approve** hoặc membership approver đáng tin cậy.
4. Invoice phải thuộc tenant của principal hoặc có delegation xuyên tenant được phê duyệt.
5. Người phê duyệt **không được là người tạo invoice**.
6. Mức tiền không vượt **approvalLimit**.
7. Invoice phải ở trạng thái **PENDING**.
8. Quyết định và cập nhật phải nhất quán, ghi audit.

### 19.1. Quyết định cho từng request

| Request | Kết quả |
|---|---|
| Bình duyệt INV-A-101, đủ scope, hạn mức trên 8 triệu | Có thể cho phép nếu mọi điều kiện khác hợp lệ |
| Alice tự duyệt INV-A-101 | Từ chối do separation of duties |
| Chi duyệt INV-A-101 | Từ chối do khác tenant |
| Bình có scope đọc nhưng không có scope duyệt | 403 ở function-level |
| Bình duyệt invoice đã APPROVED | Từ chối theo business state |
| JWT của issuer không tin cậy khai vai trò approver | 401 trước domain policy |
| Client_credentials không có delegation tenant A | Từ chối dù client có scope chức năng |

### 19.2. Thiết kế service

~~~java
@PreAuthorize(
    "hasAuthority('SCOPE_invoices.approve') " +
    "and hasAuthority('PERM_invoices.approve')"
)
@Transactional
public void approveInvoice(
        UUID invoiceId,
        Authentication authentication) {

    Actor actor = actors.fromTrustedAuthentication(authentication);

    Invoice invoice = invoices.findForUpdateByIdAndTenantId(
            invoiceId, actor.tenantId())
        .orElseThrow(() -> new NotFoundException("Invoice not found"));

    invoicePolicy.requireCanApprove(actor, invoice);

    invoice.markApproved(actor.subjectId());
    invoices.save(invoice);
    audit.recordInvoiceApproved(actor, invoice);
}
~~~

Đây là **pseudocode nghiệp vụ** cần chỉnh theo database và framework của ứng dụng. Quyết định permission có thể được xác minh trong transaction; nếu **audit** là yêu cầu không thể mất, cần thiết kế outbox/event transaction phù hợp để không ghi nhận nhầm một hành động bị rollback.

**Vì sao tốt hơn kiểm tra ở frontend?** Bất kỳ client nào gọi service đều đi qua các điều kiện function-level và object-level. **Vì sao chưa tuyệt đối?** Còn phải bảo đảm method được gọi qua proxy, mọi đường ghi khác cũng có policy, transaction nhất quán và dữ liệu actor đến từ nguồn xác thực đúng.

## 20. Checklist thiết kế trước khi đưa vào production

1. **Credential:** Resource server chỉ chấp nhận **access token** phù hợp, không nhầm ID token/refresh token.
2. **Token validation:** Chữ ký/introspection, iss, aud, exp/nbf, token type và sender binding nếu áp dụng đều được kiểm tra.
3. **Actor:** Subject, issuer, tenant, client/delegation được xây từ nguồn tin cậy; không từ query/body người gọi.
4. **Action:** Scope/role/permission phân biệt rõ và áp dụng **least privilege**.
5. **Object:** Owner, tenant, project, ACL và trạng thái được đọc từ database/policy authoritative.
6. **Default deny:** Thiếu claim, thiếu membership, object không tìm thấy hoặc policy service lỗi không cấp quyền.
7. **Method interception:** @EnableMethodSecurity có hiệu lực; không bỏ qua qua self-invocation hoặc đường gọi ngoài proxy.
8. **Query scope:** GET one, list, count, search, export, aggregate và batch đều lọc cùng policy.
9. **Writes:** Kiểm tra quyền/trạng thái gần thao tác ghi trong transaction nhất quán; dùng locking/version nếu cần.
10. **Cache:** Cache key và invalidation gắn actor, issuer, tenant, object, quyền, phiên bản policy và TTL theo mô hình.
11. **Multi-tenant:** Không cho token tenant A sử dụng object tenant B, trừ delegation rõ ràng.
12. **Errors:** 401/403/404 được dùng nhất quán, không lộ sự tồn tại hoặc metadata nhạy cảm của object trái quyền.
13. **Audit:** Có sự kiện cho phép/từ chối quan trọng mà không ghi raw token/secret.
14. **Tests:** Bao phủ cross-user, cross-tenant, wrong issuer/aud, token type, scope thiếu, revoke, concurrent update và pagination.
15. **Operations:** Có khả năng phản ứng khi quyền bị thu hồi, token lộ hoặc ACL service gián đoạn.

Không nên xem checklist là một “cấu hình bật một lần rồi xong”; policy cần được kiểm soát khi thay đổi schema, roles, tenant structure, features và nguồn token.

## 21. Những ngộ nhận thường gặp

**“Có @PreAuthorize(hasAuthority) là không còn BOLA.”** Sai. Scope/role ở mức chức năng không tự kiểm tra quyền trên object.

**“UUID dài và không đoán được đủ để bảo vệ dữ liệu.”** Sai. UUID giúp giảm khả năng đoán, không thay authorization.

**“Backend chỉ cần kiểm tra tenant_id.”** Không luôn đúng. Trong cùng tenant, owner/project/ACL vẫn có thể giới hạn quyền.

**“@PostAuthorize sau method là đủ cho cả thao tác ghi.”** Sai. Side effects có thể đã xảy ra trước khi kiểm tra kết quả.

**“@PostFilter mọi danh sách sẽ an toàn và nhanh.”** Sai. Filter sau khi tải có thể gây lộ dữ liệu trung gian, sai pagination và N+1 queries.

**“Một method gọi method có @PreAuthorize trong cùng bean luôn được kiểm soát.”** Không đảm bảo ở proxy-based AOP; self-invocation có thể bỏ qua interceptor.

**“JWT do issuer tin cậy ký nghĩa mọi claim roles đều đáng tin cho mọi API.”** Sai. Cần kiểm tra audience, claim provenance, issuer-specific mapping và tenant context.

**“Người dùng đã đăng nhập nên có quyền truy cập bất kỳ object nào họ biết ID.”** Sai. Authentication không đồng nghĩa ownership.

**“Transaction luôn loại bỏ mọi TOCTOU.”** Không tự động nếu policy phụ thuộc bản ghi/nguồn khác và isolation không phù hợp.

**“Không có access token hợp lệ vẫn có thể trả 403 để đỡ tiết lộ.”** Không nên trộn lỗi authentication với domain authorization. Hãy xác định token hợp lệ trước khi xét object.

**“Đã có object policy thì bearer token bị đánh cắp vô hại.”** Sai. Kẻ giữ token vẫn có thể thực hiện những hành động mà principal hợp pháp được phép trong thời gian token còn active.

## 22. Câu hỏi tự kiểm tra

1. Domain object authorization khác function-level authorization như thế nào? Hãy dùng **SCOPE_orders.read** và order của người khác để giải thích.
2. BOLA/IDOR thường xảy ra ở đâu? Vì sao UUID không thay thế permission check?
3. Khi nào nên dùng **@PreAuthorize**, **@PostAuthorize** và **@PostFilter**? Nêu giới hạn của từng cơ chế.
4. Vì sao một policy bean kiểm tra existsReadableById rồi service gọi findById có thể gặp TOCTOU?
5. Query scoping cần được áp dụng ở những truy vấn nào ngoài GET /{id}?
6. Trong Spring proxy-based method security, self-invocation có nguy cơ gì?
7. Tại sao cần kiểm tra **issuer, audience, token type** trước khi biến claims thành Actor hoặc GrantedAuthority?
8. Khi có hai issuer cùng sub, làm sao tránh ánh xạ nhầm danh tính?
9. **PermissionEvaluator** có những overload nào và vì sao nó không thay thế truy vấn có scope?
10. Khi caller gửi một batch chứa object hợp lệ và trái quyền, API cần quyết định chính sách all-or-nothing ra sao?
11. Khi membership bị thu hồi nhưng JWT còn hạn, policy có thể cập nhật quyền kịp thời bằng cách nào?
12. Một service account dùng client_credentials khác gì với người dùng thông thường khi kiểm tra owner?
13. Với invoice approval, tại sao đủ scope nhưng tự duyệt hóa đơn của mình vẫn cần bị từ chối?
14. Vì sao Method Security test tạo service bằng **new** có thể không thực sự kiểm tra @PreAuthorize?
15. Làm sao chứng minh endpoint list và count không tiết lộ dữ liệu tenant khác?
16. Sender-constrained access token giúp chống vấn đề nào, và vì sao nó không tự cấp quyền trên object?
17. Khi policy service timeout, phản hồi an toàn phải bảo đảm điều gì?
18. Hãy đề xuất một integration test có hai request đồng thời làm thay đổi ACL và object để phát hiện race condition.

**Ghi nhớ:** **Domain object authorization** là kiểm tra **principal có quyền thực hiện action với resource cụ thể trong ngữ cảnh tenant, owner, membership, ACL và trạng thái nghiệp vụ hay không**. Trong Spring Security, dùng **Method Security** như một lớp thực thi rõ ràng, nhưng kết hợp với **query scoping, domain policy, transaction, khóa/phiên bản dữ liệu và kiểm thử negative cases**. Không quên các ranh giới token: **issuer, audience, JWT/opaque access token, scope, revocation và chống token bị đánh cắp/phát lại**.

## Tài liệu tham khảo

- **Spring Security Reference — Method Security:** @EnableMethodSecurity, @PreAuthorize, @PostAuthorize, @PreFilter, @PostFilter, hasPermission và interception.
- **Spring Security API — PermissionEvaluator và MethodSecurityExpressionHandler:** điểm mở rộng để xây permission checks.
- **Spring Security Reference — OAuth 2.0 Resource Server (JWT/Opaque):** Authentication, GrantedAuthority, issuer và token introspection.
- **OWASP API Security Top 10 (2023) — API1: Broken Object Level Authorization:** mẫu lỗi truy cập trái quyền vào đối tượng API.
- **OWASP API Security Top 10 (2023) — API5: Broken Function Level Authorization:** khác biệt giữa quyền gọi chức năng và quyền trên từng object.
- **OWASP Authorization Cheat Sheet:** least privilege, deny-by-default, kiểm tra quyền trên mọi request và test phân quyền.
- **CWE-639 — Authorization Bypass Through User-Controlled Key:** phân loại lỗi object reference do caller kiểm soát.
- **NIST SP 800-162 — Guide to Attribute Based Access Control (ABAC):** mô hình subject, object, action, environment và policy.
- **RFC 7519 — JSON Web Token (JWT):** iss, sub, aud và claims JWT.
- **RFC 7662 — OAuth 2.0 Token Introspection:** kiểm tra trạng thái opaque token.
- **RFC 9068 — JWT Profile for OAuth 2.0 Access Tokens:** giới hạn issuer, audience và loại token dành cho API.
- **RFC 9700 — Best Current Practice for OAuth 2.0 Security:** biện pháp bảo vệ access/refresh token và chống replay.
- **RFC 9449 — OAuth 2.0 Demonstrating Proof of Possession (DPoP):** giới hạn dùng lại access token khi bị lộ.





