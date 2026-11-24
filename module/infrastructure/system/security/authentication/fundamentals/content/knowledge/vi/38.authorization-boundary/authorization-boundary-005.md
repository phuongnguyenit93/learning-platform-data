# Scope mapping — Ánh xạ phạm vi truy cập

## Mục tiêu học tập

Một ứng dụng quản lý đơn hàng có thể nhận access token với scope **orders:read**. Scope này cho biết client được cấp quyền đọc dữ liệu đơn hàng theo hợp đồng của API. Nhưng nó không có nghĩa người dùng được xem mọi đơn hàng trong mọi tenant, cũng không có nghĩa client được sửa, hủy hoặc hoàn tiền đơn hàng. Backend vẫn phải xác định principal, hành động, tài nguyên, tenant và các điều kiện nghiệp vụ trước khi cho phép truy cập.

**Scope mapping (ánh xạ phạm vi truy cập)** là quá trình chuyển các scope được cấp trong một credential hoặc request thành các quyền nghiệp vụ có ý nghĩa trong hệ thống, sau đó áp dụng các quyền đó tại ranh giới bảo vệ. Mapping phải xác định scope nào cho phép hành động nào, trên loại tài nguyên nào, trong audience/tenant nào và dưới những điều kiện nào. Nó cũng phải quy định cách xử lý scope không biết, scope cũ, scope rộng và các quyền bị thu hồi.

Scope thường là một tín hiệu quyền ở mức coarse-grained. Trong OAuth 2.0, authorization server cấp access token với một tập scope cho client; resource server kiểm tra token và quyết định request có nằm trong phạm vi được cấp hay không. Scope không tự thay thế role, permission, ownership check hoặc authorization policy theo ngữ cảnh.

Bài học thuộc chương **Authorization boundary** của mô-đun **SECURITY_AUTHENTICATION_FUNDAMENTALS**. Mô-đun tìm hiểu nguyên lý xác thực danh tính từ credential, mật khẩu, MFA, passkey và chứng chỉ đến token, phiên, liên kết danh tính và khôi phục tài khoản. Scope mapping nối kết quả xác thực và token với quyền truy cập cụ thể, giúp hệ thống duy trì ranh giới tin cậy giữa client, principal, API và tài nguyên.

Sau bài học, bạn có thể:

- Phân biệt scope, role, permission, claim, audience, resource và authorization policy.
- Giải thích scope trong OAuth 2.0 và cách OIDC scopes phục vụ yêu cầu claims.
- Thiết kế namespace scope rõ ràng theo resource và action.
- Ánh xạ scope bên ngoài thành permission nội bộ mà không trao quyền vượt quá policy.
- Kết hợp scope với subject, tenant, ownership, role và thuộc tính tài nguyên.
- Kiểm tra token tại resource server và xác định đúng enforcement point.
- Ngăn scope escalation, wildcard abuse, confused deputy và cross-tenant access.
- Quản lý scope versioning, consent, delegation, service-to-service và revocation.
- Xây dựng Java policy model, bảng mapping và bộ kiểm thử authorization.

## 1. Scope mapping giải quyết vấn đề gì?

Một access token có thể mang một tập scope như **orders:read payments:approve**. Các chuỗi này cần được hiểu thống nhất giữa authorization server, client, API gateway và backend. Nếu mỗi service tự diễn giải scope theo cách riêng, một scope có thể vô tình cấp quyền rộng hơn dự kiến hoặc bị từ chối không nhất quán.

Scope mapping trả lời các câu hỏi:

- Scope này được cấp bởi issuer nào và dành cho audience nào?
- Scope cho phép action nào: read, create, update, delete, approve hay export?
- Action áp dụng trên resource type nào?
- Quyền có giới hạn theo tenant, account, project hoặc owner không?
- Có cần role, relationship hoặc thuộc tính bổ sung không?
- Scope được yêu cầu có thực sự được authorization server cấp không?
- Scope không biết hoặc đã deprecated sẽ được xử lý thế nào?
- Khi permission bị thu hồi, các token/session hiện có còn được chấp nhận trong bao lâu?

### Ví dụ: scope đọc đơn hàng

Giả sử access token có scope **orders:read**.

Mapping có thể cho phép permission nội bộ **ORDER_READ**, nhưng policy vẫn yêu cầu:

- Token được phát hành bởi issuer tin cậy.
- Audience bao gồm API đơn hàng.
- Subject là người dùng hoặc service principal hợp lệ.
- Subject thuộc tenant đang truy vấn.
- Người dùng có quyền xem đơn hàng theo role hoặc quan hệ owner.
- Đơn hàng không nằm trong trạng thái bị giới hạn theo quy định nghiệp vụ.

Vì vậy, scope chỉ là một đầu vào của quyết định. Không được chuyển trực tiếp chuỗi scope thành quyền xem mọi bản ghi trong database.

### Ranh giới tin cậy

Scope mapping thường đi qua nhiều thành phần:

```text
Client -> Authorization Server -> Access Token -> API Gateway / Resource Server
      -> Internal Permission -> Resource Policy -> Data
```

Mỗi ranh giới phải xác minh dữ liệu đến từ nguồn có thẩm quyền. Browser không được tự khai scope; API không được tin role gửi trong request body; backend không được coi một token hợp lệ cho API A là token hợp lệ cho API B.

## 2. Phân biệt scope, role, permission, claim và audience

Các thuật ngữ này thường xuất hiện cùng nhau nhưng mang ý nghĩa khác nhau.

| Khái niệm | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| **Scope** | Phạm vi quyền được cấp cho client hoặc token theo một hợp đồng | orders:read |
| **Permission** | Quyền cụ thể trong mô hình authorization nội bộ | ORDER_READ trên một đơn hàng |
| **Role** | Tập hợp quyền gắn với người dùng hoặc nhóm trong một miền | ORDER_SUPPORT_AGENT |
| **Claim** | Thuộc tính được issuer khẳng định về subject hoặc token | sub, tenant_id, email |
| **Audience (aud)** | Bên nhận được phép sử dụng token | https://api.example.test/orders |
| **Resource** | Đối tượng hoặc dữ liệu mà action tác động tới | Đơn hàng ord-42 |
| **Policy** | Quy tắc kết hợp principal, action, resource và context để ra quyết định | Agent chỉ xem đơn hàng thuộc queue của mình |
| **Relationship** | Mối quan hệ giữa principal và resource | Người tạo là owner của đơn hàng |

### Scope không phải role

Role thường mô tả chức năng của principal trong một tổ chức hoặc ứng dụng. Scope thường mô tả quyền mà một client/token được phép sử dụng trong một giao thức hoặc API.

Ví dụ, một nhân viên có role **FINANCE_APPROVER**, nhưng một mobile client chỉ được cấp scope **payments:read**. Client đó không thể phê duyệt thanh toán chỉ vì người dùng có role approver. Ngược lại, token có scope **payments:approve** cũng không tự chứng minh người dùng có role approver cho khoản thanh toán cụ thể.

Một quyết định có thể yêu cầu đồng thời:

- Token có scope **payments:approve**.
- Principal có role **FINANCE_APPROVER**.
- Principal thuộc tenant sở hữu payment.
- Payment đang ở trạng thái **PENDING_APPROVAL**.
- Principal không phải người tạo payment nếu policy yêu cầu separation of duties.
- Step-up authentication còn mới nếu hành động nhạy cảm.

### Scope không phải claim

Scope nói về quyền được cấp; claim mô tả một thuộc tính. Ví dụ **tenant_id** là claim có thể giúp giới hạn dữ liệu theo tenant. Không nên đặt **admin=true** trong claim rồi coi đó là permission mà không kiểm tra nguồn phát hành, audience, freshness và policy.

### Scope không phải audience

Một token có thể có scope phù hợp nhưng được phát hành cho API khác. Resource server phải xác minh audience. Scope **orders:read** trong token dành cho API analytics không tự động được dùng tại API quản trị đơn hàng.

### Scope không phải consent

Việc người dùng đồng ý cấp quyền cho một client là một phần của authorization grant. Consent không thay thế kiểm tra scope trong token hoặc policy tại resource server. Khi consent bị thu hồi, authorization server cần áp dụng cơ chế revoke/expiry phù hợp để quyền đã cấp không tiếp tục tồn tại vượt policy.

## 3. Scope trong OAuth 2.0 và OpenID Connect

OAuth 2.0 sử dụng scope để biểu diễn phạm vi quyền mà client yêu cầu và authorization server cấp. Giá trị scope là chuỗi phân tách bằng dấu cách theo quy tắc giao thức; ý nghĩa của từng scope phụ thuộc authorization server và resource server đã thống nhất.

### Requested scope và granted scope

Client có thể yêu cầu:

```text
scope=orders:read orders:write payments:approve
```

Authorization server có thể chỉ cấp một tập con, ví dụ **orders:read**. Resource server phải kiểm tra tập scope thực sự được cấp trong access token, không dựa vào scope client đã yêu cầu hoặc scope lưu ở frontend.

Một số authorization server có thể từ chối yêu cầu, yêu cầu consent, áp dụng policy hoặc thu hẹp scope. Client cần xử lý kết quả thực tế. Không tự giả định rằng mọi scope được yêu cầu đều được cấp.

### OIDC scopes

OpenID Connect định nghĩa các scope như **openid**, **profile**, **email**, **address** và **phone** để yêu cầu thông tin nhận dạng/claims theo profile. Chúng không mặc nhiên là permission cho API nghiệp vụ.

- **openid** cho biết authorization request là một OIDC authentication request.
- **profile** yêu cầu các claim hồ sơ được định nghĩa trong OIDC.
- **email** yêu cầu các claim liên quan email.
- **address** và **phone** yêu cầu các claim tương ứng khi được hỗ trợ.

Một ứng dụng không nên suy ra quyền **orders:read** chỉ vì ID token có **profile** hoặc **email**. API nghiệp vụ cần access token và permission/scope theo hợp đồng của resource server.

### Access token và ID token

- Access token được cấp để gọi resource server theo audience/scope tương ứng.
- ID token là assertion dành cho OIDC client về kết quả authentication và subject.
- Không dùng ID token làm bearer token gọi API chỉ vì nó là JWT.
- Kiểm tra **iss**, **aud**, chữ ký, thời hạn và các claim bắt buộc theo loại token.
- Nếu access token opaque, resource server có thể cần introspection hoặc cơ chế kiểm tra được authorization server định nghĩa.

### Scope format và namespace

Một scope nên có tên ổn định, dễ đọc và gắn với miền nghiệp vụ. Ví dụ:

| Scope | Ý nghĩa dự kiến |
| --- | --- |
| orders:read | Đọc thông tin đơn hàng |
| orders:create | Tạo đơn hàng |
| orders:update | Cập nhật trường được phép |
| orders:cancel | Hủy đơn hàng theo policy |
| payments:read | Xem payment |
| payments:approve | Phê duyệt payment |
| users:profile:read | Đọc hồ sơ người dùng theo phạm vi |
| audit:events:read | Đọc audit event được phép |
| keys:rotate | Khởi tạo rotation key trong scope được cấp |

Tên scope là hợp đồng giữa issuer và resource server. Không nên đổi nghĩa của scope cũ trong khi token cũ còn hiệu lực. Khi thay đổi semantics, tạo scope mới hoặc version mapping, rồi migration có kiểm soát.

## 4. Thiết kế taxonomy scope

Taxonomy là hệ thống quy tắc đặt tên và phân cấp scope. Một taxonomy tốt giúp client hiểu quyền, reviewer đánh giá consent và resource server mapping nhất quán.

### Thành phần tên scope

Có thể dùng cấu trúc:

```text
<resource-domain>:<action>
<resource-domain>:<subresource>:<action>
```

Ví dụ:

- **orders:read**
- **orders:items:read**
- **payments:approve**
- **identity:credentials:revoke**
- **projects:members:invite**

Scope nên mô tả action có ý nghĩa. Tránh tên mơ hồ như **manage**, **full**, **power**, **user** nếu không có định nghĩa chính xác. Nếu cần scope rộng, hãy nêu rõ phạm vi và giới hạn.

### Quy tắc đặt tên

- Dùng namespace theo resource domain.
- Dùng action verb có semantics ổn định.
- Phân biệt read, create, update, delete, approve, export và administer.
- Không gộp nhiều quyền nhạy cảm vào một scope tổng quát nếu client không cần tất cả.
- Không đặt scope theo tên màn hình UI; API và policy mới là ranh giới thực.
- Tránh scope phụ thuộc implementation như **db:select**.
- Định nghĩa rõ scope có áp dụng cho collection, object, tenant hay toàn tổ chức.
- Có owner và version cho taxonomy.
- Dùng tên nhất quán giữa authorization server, API docs, gateway và service.

### Wildcard và scope tổng quát

Các giá trị như **admin:\***, **\***, **all** hoặc **resource:manage** có thể tiện, nhưng dễ tạo quyền vượt mức. Nếu hỗ trợ wildcard, cần định nghĩa chính xác:

- Wildcard mở rộng tới những action nào?
- Có bao gồm action mới được thêm trong tương lai không?
- Có bao gồm resource nhạy cảm hoặc cross-tenant không?
- Ai có quyền cấp wildcard?
- Có cần approval/step-up không?
- Token được cấp wildcard có lifetime ngắn hơn không?

Một wildcard động có thể khiến client tự nhận quyền mới mà không có consent mới. Với hệ thống nhạy cảm, ưu tiên scope tường minh và mapping có version.

## 5. Từ scope bên ngoài đến permission nội bộ

Scope trong access token là một phần của giao thức bên ngoài. Ứng dụng nên ánh xạ nó vào permission nội bộ có semantics rõ ràng, thay vì để mọi service tự so sánh chuỗi scope.

### Mapping table

Ví dụ cho API đơn hàng và thanh toán:

| External scope | Internal permission | Action | Resource type | Điều kiện bổ sung |
| --- | --- | --- | --- | --- |
| orders:read | ORDER_READ | READ | Order | Tenant match và ownership/role |
| orders:create | ORDER_CREATE | CREATE | Order | Customer account active |
| orders:update | ORDER_UPDATE | UPDATE | Order | Chỉ trường cho phép, trạng thái hợp lệ |
| orders:cancel | ORDER_CANCEL | CANCEL | Order | Order chưa giao hoặc theo policy |
| payments:read | PAYMENT_READ | READ | Payment | Tenant và data classification |
| payments:approve | PAYMENT_APPROVE | APPROVE | Payment | Role approver, separation of duties, step-up |
| audit:events:read | AUDIT_READ | READ | AuditEvent | Security/audit role và giới hạn retention |

Mapping là quan hệ có chủ đích. Một scope có thể ánh xạ tới permission coarse-grained; policy nội bộ tiếp tục áp dụng điều kiện. Một permission có thể yêu cầu nhiều scope hoặc role; không nên giả định mapping luôn là một-một.

### Mapping theo hướng ít quyền hơn

Nếu token có scope **orders:read**, không suy ra **orders:update**. Nếu token có **payments:read**, không suy ra **payments:approve**. Không dùng prefix match kiểu kiểm tra chuỗi bắt đầu bằng **orders** vì nó có thể coi **orders:admin** hoặc **orders:read-all** là quyền hợp lệ ngoài dự kiến.

Tốt nhất parse scope thành tập token chính xác, so khớp theo mapping allowlist và từ chối scope không biết ở các quyết định có ảnh hưởng quyền. Scope unknown không được tự động ánh xạ thành permission rộng.

### Một scope có thể không đủ

Scope **orders:read** có thể cho phép gọi endpoint đọc đơn hàng, nhưng policy cần giới hạn từng bản ghi. Ví dụ:

- Customer chỉ đọc đơn hàng của mình.
- Support agent đọc đơn hàng thuộc queue được phân công.
- Auditor đọc dữ liệu trong tenant được cấp.
- Service analytics đọc dữ liệu đã được lọc hoặc ẩn danh.

Mapping chỉ xác định permission candidate. Policy quyết định candidate có áp dụng cho resource cụ thể hay không.

## 6. Mô hình quyết định: principal, action, resource và context

Authorization thường có thể biểu diễn dưới dạng:

```text
Decision = Policy(Principal, Action, Resource, Context)
```

Trong đó:

- **Principal:** user, service, workload hoặc delegated actor đã được xác thực.
- **Action:** hành động đang yêu cầu, ví dụ READ, APPROVE, EXPORT.
- **Resource:** object cụ thể và loại resource.
- **Context:** tenant, ownership, trạng thái, thời gian, risk, device, assurance hoặc transaction state.
- **Policy:** quy tắc quyết định ALLOW hoặc DENY.

Scope có thể là một thuộc tính của authorization context. Role, relationship và resource attribute là các đầu vào khác.

### Ví dụ quyết định

Một request đọc đơn hàng có thể được cho phép khi:

1. Access token hợp lệ, issuer và audience đúng.
2. Token chứa scope **orders:read**.
3. Subject có quyền truy cập tenant được yêu cầu.
4. Order thuộc tenant đó.
5. Subject là owner hoặc có role support được phép xem.
6. Order không bị giới hạn bởi policy bảo mật.
7. Không có trạng thái account suspension hoặc deny rule.

Nếu một điều kiện bắt buộc không đạt, từ chối. Không được bỏ qua tenant check chỉ vì token có scope phù hợp.

### Deny by default

Mọi action/resource chưa có mapping hoặc policy tường minh phải bị từ chối. Unknown scope, unknown action, missing tenant hoặc missing resource context không được chuyển thành quyền mặc định. Khi policy engine lỗi hoặc không thể lấy dữ liệu bắt buộc, hành động nhạy cảm nên fail closed theo threat model.

## 7. Kết hợp scope với RBAC và ABAC

Scope mapping thường kết hợp với các mô hình authorization khác.

### RBAC — Role-Based Access Control

RBAC gán role cho principal và ánh xạ role thành permissions.

Ví dụ:

- **ORDER_CUSTOMER** có **ORDER_READ_OWN**, **ORDER_CREATE**.
- **ORDER_SUPPORT** có **ORDER_READ_ASSIGNED**, **ORDER_UPDATE_CASE**.
- **FINANCE_APPROVER** có **PAYMENT_READ**, **PAYMENT_APPROVE**.

Scope từ token có thể giới hạn những permission mà client được phép sử dụng. Quyết định cuối cùng là giao của các điều kiện bắt buộc: scope được cấp, role của principal và policy của resource.

### ABAC — Attribute-Based Access Control

ABAC sử dụng thuộc tính của subject, resource, action và environment.

Ví dụ policy:

- Subject tenant bằng resource tenant.
- Subject department bằng resource department.
- Payment amount dưới ngưỡng mà role được phép duyệt.
- Resource status là PENDING.
- Authentication assurance đủ mạnh và còn mới.
- Request đến từ workload identity được cấp cho service cụ thể.

Scope không nên nhúng mọi thuộc tính này vào tên. Dùng scope để biểu diễn quyền coarse-grained; dùng policy/attributes để giới hạn ngữ cảnh.

### Relationship-based access

Một số hệ thống cần quan hệ như owner, member, manager, assigned agent hoặc parent-child. Scope **documents:read** chỉ cho biết client có thể yêu cầu đọc tài liệu; relationship check xác định principal có quan hệ hợp lệ với tài liệu cụ thể hay không.

### Giao của các ràng buộc

Một mô hình dễ kiểm tra:

```text
ALLOW =
    valid_token
    AND correct_audience
    AND required_scope
    AND principal_permission
    AND resource_policy
    AND tenant_boundary
    AND account_active
```

Đây là công thức minh họa. Một policy có thể có các điều kiện bổ sung hoặc deny rule ưu tiên. Cần ghi rõ thứ tự đánh giá và nguồn dữ liệu đáng tin cho từng điều kiện.

## 8. Kiểm tra access token tại resource server

Scope mapping chỉ đáng tin nếu resource server xác minh đúng token. Không đọc scope từ header tùy ý hoặc từ payload JWT chưa xác minh.

### Với JWT access token

Resource server cần kiểm tra theo profile:

- Chữ ký bằng key/issuer được tin cậy.
- **iss** đúng issuer đã cấu hình.
- **aud** chứa resource server/API hiện tại.
- **exp**, **nbf** và thời gian hợp lệ có xét clock skew có giới hạn.
- **scope** hoặc **scp** theo định dạng mà issuer đã thống nhất.
- **client_id**/**azp** hoặc thông tin client nếu policy yêu cầu.
- **sub** và tenant/actor claims có nguồn tin cậy.
- Token type/profile đúng; không dùng ID token thay access token.
- Các claim bắt buộc có mặt và có kiểu dữ liệu đúng.

Không chấp nhận thuật toán chữ ký do token tự chọn ngoài allowlist. Không lấy JWKS URL từ token; dùng issuer metadata/configuration đã tin cậy.

### Với opaque access token

Resource server có thể dùng introspection endpoint hoặc cơ chế server-side khác để xác minh token active, audience, scope và subject. Introspection response cũng phải được xác thực theo cấu hình và bảo vệ kênh.

### Scope parsing

Một số issuer đặt scope trong claim **scope** dưới dạng chuỗi phân tách bằng dấu cách; một số profile có thể dùng claim **scp** hoặc cấu trúc khác. Resource server cần một adapter theo issuer, không đoán bằng cách parse tùy tiện.

Không chấp nhận duplicate/ambiguous scope token nếu parser và issuer không định nghĩa semantics. Chuẩn hóa encoding, whitespace và case theo hợp đồng; không tự đổi hoa/thường nếu scope phân biệt case.

### Token hợp lệ không có nghĩa request được phép

Token có thể hợp lệ về chữ ký/thời gian nhưng thiếu scope, sai tenant hoặc subject không có quyền với resource. Authentication/token validation và authorization phải là các bước phân biệt, có log reason code phù hợp mà không làm lộ dữ liệu.

## 9. Audience, resource indicator và confused deputy

Một token được cấp cho resource server cụ thể. Nếu API A nhận token dành cho API B, token có thể bị dùng sai trust boundary nếu audience không được kiểm tra.

### Audience

- Issuer xác định token được phát hành bởi ai.
- Audience xác định token dành cho ai.
- Scope xác định phạm vi quyền được cấp trong ngữ cảnh đó.
- Subject/actor xác định token đại diện cho ai hoặc workload nào.

Không dùng scope thay cho audience. **orders:read** trong token dành cho API reporting không mặc nhiên có hiệu lực ở API payment.

### Confused deputy

Confused deputy xảy ra khi một service có quyền rộng bị client thuyết phục dùng quyền của chính service đó vượt quá quyền client được cấp.

Ví dụ, API gateway có credential nội bộ để gọi billing service. Client chỉ có scope **invoices:read**, nhưng gateway nhận request refund và dùng credential service-level để thực hiện mà không kiểm tra quyền của caller. Billing service nhìn thấy gateway có quyền refund và không biết caller ban đầu thiếu quyền.

Kiểm soát:

- Propagate identity/delegation context đã xác minh.
- Dùng token exchange/on-behalf-of theo profile khi cần.
- Giữ audience và scope riêng cho từng service.
- Backend kiểm tra actor và subject, không chỉ service identity.
- Không chuyển tiếp token tới audience không liên quan.
- Giới hạn service credential theo action tối thiểu.
- Audit cả caller gốc lẫn service thực hiện hành động.

## 10. Tenant boundary và resource-level scope

Trong SaaS multi-tenant, scope thường không đủ để xác định dữ liệu tenant nào được truy cập.

### Tenant binding

Có thể lấy tenant từ claim do issuer tin cậy cấp, từ membership store hoặc từ context đã xác minh. Không tin tenant ID do browser gửi nếu không kiểm tra membership và resource ownership.

Khi xử lý request:

1. Xác định subject từ token đã xác minh.
2. Xác định tenant context từ nguồn tin cậy.
3. Kiểm tra subject có membership/relationship hợp lệ với tenant.
4. Kiểm tra resource thuộc tenant đó.
5. Áp dụng scope và permission.
6. Từ chối nếu tenant path, claim và resource ownership không khớp.

### Không nhúng tenant vào scope tùy tiện

Scope như **tenant:t1:orders:read** có thể gây bùng nổ số lượng scope và khó quản lý khi membership thay đổi. Chỉ dùng tenant-scoped scope nếu giao thức/kiến trúc thực sự cần; thông thường scope mô tả action, còn tenant context được kiểm tra riêng.

### Resource-level authorization

Một scope có thể mở endpoint nhưng không cấp quyền cho mọi object. Ví dụ **documents:read** cho phép client gọi API đọc tài liệu; policy vẫn kiểm tra document ID có thuộc workspace mà principal là member không. Tránh IDOR bằng cách không chỉ kiểm tra scope ở controller rồi truy vấn object theo ID không ràng buộc tenant.

## 11. Scope, delegation và service-to-service

Một client có thể đại diện người dùng, hoặc một service có thể gọi service khác. Cần giữ rõ ai là actor và ai là subject.

### Delegated access

Khi client gọi API thay mặt user:

- Token cần audience đúng resource server.
- Scope phản ánh quyền delegated đã được cấp cho client.
- Subject claim xác định user nếu token profile hỗ trợ.
- Client identity xác định ứng dụng đang gọi.
- Policy có thể giới hạn quyền bởi cả user và client.
- Không cấp scope rộng hơn quyền user được phép delegate theo policy.

Ví dụ: user có quyền đọc và sửa đơn hàng, nhưng ứng dụng mobile chỉ được consent **orders:read**. Token của mobile không nên nhận **orders:update**.

### Client credentials / workload identity

Với service-to-service, subject có thể là workload/service principal thay vì người dùng. Scope cần gắn với workload identity, audience và purpose cụ thể.

Ví dụ, invoice-worker chỉ cần **invoices:read** và **invoices:mark-paid** trong một workflow được kiểm soát. Không cấp **admin:\*** chỉ vì worker chạy trong private network.

### Token exchange và on-behalf-of

Khi một service cần gọi service khác, token exchange có thể tạo token mới với audience/scope hẹp hơn. Service nhận token phải xác minh issuer, audience, subject, actor/delegation chain và scope. Không chỉ forward token ban đầu qua mọi microservice.

### Delegation chain

Audit nên phân biệt:

- User/subject khởi tạo.
- Client/application gọi đầu tiên.
- Service trung gian.
- Workload thực thi cuối cùng.
- Scope/permission đã được cấp và dùng.
- Resource/tenant bị tác động.

Điều này giúp điều tra confused deputy và xác định service nào đã dùng quyền vượt quá phạm vi caller.

## 12. Consent, scope reduction và quyền tối thiểu

Authorization server thường có thể cấp ít scope hơn tập client yêu cầu. Scope reduction là một biện pháp quan trọng để giới hạn quyền.

### Nguyên tắc cấp scope

- Client chỉ yêu cầu scope cần thiết cho tính năng đang dùng.
- Authorization server kiểm tra client registration, user consent và policy.
- Scope được cấp là giao của yêu cầu, consent, client permission và policy.
- Scope nhạy cảm cần consent rõ, admin approval hoặc step-up tùy use case.
- Scope không còn dùng nên được bỏ khỏi client registration.
- Token có lifetime và audience phù hợp.
- Khi consent hoặc grant bị thu hồi, áp dụng revocation/session policy tương ứng.

### Incremental authorization

Một ứng dụng có thể chỉ yêu cầu **orders:read** khi người dùng xem đơn hàng. Khi họ bật tính năng phê duyệt thanh toán, ứng dụng mới yêu cầu **payments:approve** với consent/approval bổ sung.

Không yêu cầu toàn bộ scope lúc đăng nhập đầu tiên nếu user chưa cần. Điều này giảm quyền được cấp, giảm tác động khi token bị lộ và giúp người dùng hiểu vì sao ứng dụng cần quyền.

### Không dùng scope làm giao diện quyền duy nhất

Giao diện consent cần mô tả hành động thực tế bằng ngôn ngữ người dùng, không chỉ hiển thị chuỗi kỹ thuật như **payments:approve**. Nhưng nội dung hiển thị phải khớp semantics của mapping và policy. Không nói “chỉ xem” nếu scope cho phép export hoặc sửa dữ liệu.

## 13. Versioning, deprecation và migration

Scope là hợp đồng dài hạn giữa issuer và resource server. Đổi nghĩa scope có thể làm token cũ mang quyền ngoài dự kiến.

### Khi cần thay đổi

- Thêm action mới hoặc resource type mới.
- Thu hẹp phạm vi của scope hiện tại.
- Chia scope tổng quát thành nhiều scope nhỏ.
- Đổi tên namespace.
- Tách quyền user-facing và service-to-service.
- Thay đổi semantics consent hoặc policy.

### Chiến lược migration

1. Định nghĩa scope mới với semantics rõ.
2. Cập nhật authorization server để cấp scope mới.
3. Cập nhật client yêu cầu scope mới theo incremental authorization.
4. Cập nhật resource server mapping và test.
5. Trong giai đoạn chuyển tiếp, xử lý scope cũ theo mapping cũ đã đóng băng.
6. Theo dõi usage của scope cũ.
7. Ngừng cấp scope cũ.
8. Chờ token cũ hết hạn hoặc revoke grant theo policy.
9. Xóa mapping cũ khi không còn token/client phụ thuộc.
10. Cập nhật tài liệu và consent UI.

Không âm thầm ánh xạ scope cũ sang quyền mới rộng hơn. Nếu semantics thay đổi đáng kể, tạo scope mới và yêu cầu grant mới.

### Unknown scope

Unknown scope có thể xuất hiện do typo, issuer mismatch, version drift hoặc attacker cố đưa giá trị lạ. Resource server không được tự suy ra quyền từ prefix hoặc gần giống tên. Ghi nhận reason code và từ chối quyền không được mapping.

## 14. Enforcement point và kiến trúc kiểm tra quyền

Scope mapping có thể được thực hiện tại API gateway, service hoặc authorization service. Cần chọn enforcement point rõ ràng và tránh khoảng trống giữa các lớp.

### API gateway

Gateway phù hợp để:

- Xác minh token cơ bản.
- Kiểm tra audience và scope coarse-grained.
- Rate limit và route request.
- Loại bỏ header identity do client tự gửi.
- Propagate context đã xác minh tới backend qua kênh tin cậy.

Gateway thường không có đủ dữ liệu để quyết định ownership hoặc trạng thái nghiệp vụ của từng object. Không dừng authorization ở gateway nếu backend truy cập resource theo ID.

### Service layer

Service hiểu action và resource cụ thể nên có thể áp dụng policy như owner, tenant, workflow state, separation of duties và amount threshold. Với dữ liệu nhạy cảm, service nên kiểm tra điều kiện quan trọng tại nơi thực thi.

### Central policy decision point

Một Policy Decision Point (PDP) có thể đánh giá policy tập trung; Policy Enforcement Point (PEP) ở gateway/service thực thi ALLOW/DENY. Dù dùng PDP tập trung, service vẫn phải cung cấp context đã xác minh và fail-safe khi policy decision không khả dụng.

### Không tin header nội bộ từ client

Các header như **X-User-Role**, **X-Tenant-Id**, **X-Permissions** có thể bị client giả mạo nếu gateway không xóa và tái tạo từ nguồn tin cậy. Chỉ backend-to-backend channel đã xác thực mới được phép truyền context; tốt hơn dùng token/assertion có chữ ký hoặc metadata từ trusted middleware.

## 15. Java: ánh xạ scope thành permission nội bộ

Ví dụ sau minh họa mapping allowlist. Scope phải lấy từ access token đã được xác minh; code không tự xác minh JWT, issuer, audience hoặc chữ ký.

```java
import java.util.Arrays;
import java.util.Map;
import java.util.Set;
import java.util.stream.Collectors;

enum Permission {
    ORDER_READ,
    ORDER_CREATE,
    ORDER_UPDATE,
    ORDER_CANCEL,
    PAYMENT_READ,
    PAYMENT_APPROVE
}

final class ScopeMapper {
    private static final Map<String, Set<Permission>> MAPPING = Map.of(
            "orders:read", Set.of(Permission.ORDER_READ),
            "orders:create", Set.of(Permission.ORDER_CREATE),
            "orders:update", Set.of(Permission.ORDER_UPDATE),
            "orders:cancel", Set.of(Permission.ORDER_CANCEL),
            "payments:read", Set.of(Permission.PAYMENT_READ),
            "payments:approve", Set.of(Permission.PAYMENT_APPROVE)
    );

    private ScopeMapper() {}

    static Set<Permission> mapGrantedScopes(String scopeClaim) {
        if (scopeClaim == null || scopeClaim.isBlank()) {
            return Set.of();
        }

        Set<String> granted = Arrays.stream(scopeClaim.trim().split("\\s+"))
                .collect(Collectors.toUnmodifiableSet());

        Set<String> unknown = granted.stream()
                .filter(scope -> !MAPPING.containsKey(scope))
                .collect(Collectors.toUnmodifiableSet());
        if (!unknown.isEmpty()) {
            throw new IllegalArgumentException("Unknown scope: " + unknown);
        }

        return granted.stream()
                .flatMap(scope -> MAPPING.get(scope).stream())
                .collect(Collectors.toUnmodifiableSet());
    }

    static boolean hasPermission(
            Set<Permission> permissions,
            Permission required) {
        return permissions != null && permissions.contains(required);
    }
}
```

Đây là mapper minh họa. Trong production, nên phát hiện và ghi nhận unknown scope thay vì âm thầm bỏ qua mà không có telemetry; không biến unknown scope thành quyền. Mapping cần được version hóa và gắn với issuer/audience vì cùng chuỗi scope có thể mang semantics khác giữa hai authorization server.

### Kiểm tra resource và tenant

```java
record PrincipalContext(
        String subjectId,
        String tenantId,
        Set<Permission> permissions,
        Set<String> roles,
        boolean accountActive
) {}

record OrderResource(
        String orderId,
        String tenantId,
        String ownerSubjectId,
        String status
) {}

final class OrderAuthorization {

    static boolean canRead(
            PrincipalContext principal,
            OrderResource order) {

        if (principal == null || order == null
                || principal.subjectId() == null
                || principal.tenantId() == null
                || order.tenantId() == null
                || !principal.accountActive()
                || principal.permissions() == null
                || !principal.permissions().contains(Permission.ORDER_READ)) {
            return false;
        }

        if (!principal.tenantId().equals(order.tenantId())) {
            return false;
        }

        boolean isOwner = order.ownerSubjectId() != null
                && principal.subjectId().equals(order.ownerSubjectId());

        boolean isSupport = principal.roles() != null
                && principal.roles().contains("ORDER_SUPPORT");

        return isOwner || isSupport;
    }
}
```

Ví dụ minh họa điều kiện scope-derived permission, tenant và relationship. Production cần xử lý null/identifier validation đầy đủ, kiểm tra role từ nguồn tin cậy, giới hạn support theo assignment/tenant và tránh truy vấn object trước khi áp dụng tenant filter. Không dùng dữ liệu role hoặc tenant do client gửi để tạo PrincipalContext.

### Mapping cấu hình minh họa

```yaml
mappingVersion: "2026-01"
issuer: "https://identity.example.test"
audience: "https://api.example.test/orders"
scopes:
  orders:read:
    permissions:
      - ORDER_READ
    constraints:
      - tenant_membership
      - resource_ownership_or_support_assignment
  orders:create:
    permissions:
      - ORDER_CREATE
    constraints:
      - tenant_membership
      - account_active
  payments:approve:
    permissions:
      - PAYMENT_APPROVE
    constraints:
      - finance_approver_role
      - payment_pending
      - separation_of_duties
      - recent_step_up
unknownScopePolicy: "DENY_AND_AUDIT"
```

Đây là schema minh họa, không phải cấu hình chuẩn của OAuth. Parser phải validate schema, issuer/audience và policy version khi khởi động; cấu hình lỗi hoặc thiếu mapping cho action nhạy cảm phải khiến service không khởi động ở trạng thái fail-open.

## 16. Lỗi triển khai thường gặp

| Lỗi | Hậu quả | Cách phòng tránh |
| --- | --- | --- |
| Coi scope là role | Client có scope bị hiểu nhầm là user có vai trò nghiệp vụ | Kiểm tra scope và role độc lập |
| Tin scope client đã yêu cầu | Quyền chưa được cấp vẫn được sử dụng | Chỉ đọc granted scope từ access token đã xác minh |
| Không kiểm tra audience | Token dành cho API khác bị dùng sai nơi | Validate aud theo resource server |
| Dùng ID token gọi API | Nhầm assertion cho client với access token | Dùng access token đúng audience |
| Prefix matching scope | orders:admin vô tình được chấp nhận như orders:read | Parse và exact match allowlist |
| Wildcard mở rộng động | Scope cũ nhận quyền mới ngoài consent | Wildcard tường minh, version và approval |
| Scope read cho phép mọi object | IDOR hoặc cross-tenant data exposure | Ownership, relationship và tenant checks |
| Tin tenant từ request body | Attacker đổi tenant ID | Lấy tenant từ trusted context và kiểm tra membership |
| Scope mapping khác nhau giữa service | Quyền không nhất quán | Mapping registry/version và shared tests |
| Unknown scope bị ánh xạ mặc định | Quyền vượt dự kiến | Deny unknown và audit |
| Scope cũ đổi nghĩa | Token đang tồn tại có quyền mới | Freeze semantics, version và migration |
| Gateway kiểm tra nhưng backend không kiểm tra resource | Request dùng object ID khác tenant | Enforcement tại service nơi truy cập resource |
| Service dùng credential rộng thay quyền caller | Confused deputy | Delegation context, token exchange và least privilege |
| Header role/permission từ client | Principal giả mạo quyền | Strip header và dựng context từ token/IdP tin cậy |
| Không phân biệt user và workload subject | Service được hưởng quyền người dùng hoặc ngược lại | Principal type và policy riêng |
| Consent không được phản ánh | Client giữ quyền không còn cần | Incremental authorization và grant revocation |
| Token refresh làm scope tăng | Quyền tăng mà không có grant/policy mới | Chỉ cấp scope theo authorization server policy |
| PDP outage nhưng service cho phép | Bypass authorization khi policy lỗi | Fail closed cho action nhạy cảm |
| Log token đầy đủ | Lộ bearer credential | Log reason code, token reference và metadata tối thiểu |

## 17. Bảng kiểm thử scope mapping

| Trường hợp | Đầu vào/thao tác | Kết quả mong đợi |
| --- | --- | --- |
| Scope được cấp chính xác | Token có orders:read, audience đúng | Map thành ORDER_READ |
| Scope chỉ được yêu cầu | Client yêu cầu orders:update nhưng token chỉ có read | Update bị từ chối |
| Unknown scope | Token có orders:root chưa được mapping | Không tạo permission; audit |
| Prefix gần giống | orders:reader thay cho orders:read | Exact match thất bại |
| Scope sai audience | Token đúng scope nhưng aud dành cho API khác | Resource server từ chối |
| ID token dùng làm access token | Gửi ID token tới orders API | Từ chối theo token profile/audience |
| Token sai issuer | Token do issuer không tin cậy phát hành | Từ chối |
| Token hết hạn | exp đã qua | Từ chối |
| Thiếu scope | Token không có scope cần cho action | 403/deny theo API contract |
| Read không suy ra update | Token chỉ có orders:read | Update bị từ chối |
| Scope và role không khớp | Có payments:approve nhưng không có finance role | Từ chối |
| Role nhưng thiếu scope | User là finance approver, client chỉ có payments:read | Approve bị từ chối |
| Tenant mismatch | Token/subject thuộc tenant A, resource thuộc B | Từ chối, không rò dữ liệu |
| Ownership mismatch | Customer đọc order của user khác trong cùng tenant | Từ chối |
| Support assignment | Support đọc order ngoài queue được giao | Từ chối |
| Payment state invalid | Approve payment đã SETTLED | Từ chối |
| Separation of duties | Người tạo payment tự phê duyệt | Từ chối |
| Step-up cũ | Token scope đúng nhưng assurance quá cũ | Yêu cầu step-up hoặc deny |
| Wildcard scope | Token có orders:* khi policy không cho wildcard | Từ chối |
| Scope deprecation | Token cũ dùng scope đã ngừng cấp | Hành vi theo migration policy, không mở rộng quyền |
| Consent revoked | Grant bị thu hồi | Token/session bị xử lý theo revocation policy |
| Client delegation | Client chỉ được read dù user có update | Token chỉ cấp read |
| Confused deputy | Gateway dùng service credential rộng cho action caller không được phép | Backend từ chối |
| Header giả mạo | Client gửi X-User-Role: ADMIN | Header bị loại bỏ/không được tin |
| Workload scope | Worker gọi API ngoài audience hoặc purpose | Từ chối |
| Mapping config lỗi | Thiếu permission mapping cho action nhạy cảm | Service fail startup hoặc deny |
| PDP unavailable | Policy engine không phản hồi | Fail closed theo risk policy |
| Cross-service consistency | Hai service xử lý cùng scope | Cùng mapping version và semantics |
| Audit review | Kiểm tra log authorization | Có subject/client/action/resource/reason, không có token thô |

Ngoài unit test, cần integration test với authorization server, API gateway, resource server, token introspection/JWKS, tenant store, role directory, PDP và nhiều service. Kiểm tra cả positive và negative case; các test cross-tenant, scope escalation, confused deputy và IDOR cần là điều kiện phát hành.

## 18. Checklist thiết kế scope mapping

Trước khi phát hành API hoặc thay đổi scope, hãy trả lời:

1. **Contract:** Scope này thuộc issuer và audience nào? Semantics có được tài liệu hóa không?
2. **Action:** Nó cho phép hành động nào? Có phân biệt read/create/update/delete/approve/export không?
3. **Resource:** Áp dụng cho collection hay object? Có giới hạn loại tài nguyên không?
4. **Principal:** Token đại diện user, client hay workload? Actor/delegation chain được giữ thế nào?
5. **Grant:** Scope được yêu cầu hay thực sự được cấp? Consent và client policy được kiểm tra ở đâu?
6. **Mapping:** External scope ánh xạ sang permission nội bộ nào? Mapping có exact match và version không?
7. **Constraints:** Có cần role, ownership, relationship, tenant, status hoặc step-up không?
8. **Audience:** Resource server có xác minh đúng aud và token profile không?
9. **Enforcement:** Gateway và service chia trách nhiệm ra sao? Object-level check ở đâu?
10. **Unknown values:** Unknown scope/action/claim được xử lý thế nào?
11. **Wildcard:** Có wildcard không? Ai cấp và nó mở rộng tới quyền nào?
12. **Delegation:** Service trung gian có thể dùng quyền vượt caller không?
13. **Lifecycle:** Scope deprecation, grant revocation và token expiry được quản lý ra sao?
14. **Failure:** PDP, introspection hoặc role store lỗi thì hành động nào fail closed?
15. **Audit:** Log có đủ principal/client/action/resource/tenant/reason mà không lộ token không?
16. **Testing:** Có test scope escalation, IDOR, cross-tenant, role mismatch và confused deputy không?

## 19. Bài tập vận dụng

Một nền tảng SaaS có API đơn hàng, thanh toán và hồ sơ người dùng. Authorization server cấp token cho ứng dụng mobile với scope **orders:read**, **orders:write**, **payments:read**, **profile**. Backend hiện kiểm tra scope bắt đầu bằng **orders** để cho phép cả GET, PUT và DELETE. Một số endpoint chỉ kiểm tra role từ header **X-User-Role** do gateway chuyển tiếp. Tenant ID được lấy từ query parameter. Gateway có service credential cho payment API với quyền approve rộng.

**Yêu cầu:**

1. Chỉ ra các lỗi scope mapping, audience, tenant và trust boundary trong thiết kế hiện tại.
2. Định nghĩa taxonomy scope tách read/create/update/cancel và payment approval.
3. Xây mapping table từ scope sang permission nội bộ và điều kiện policy.
4. Thiết kế token validation với issuer, audience, expiry, scope và principal type.
5. Mô tả cách kết hợp scope với role, ownership, tenant membership và trạng thái resource.
6. Thiết kế delegation để gateway không dùng quyền approve của chính nó thay cho caller.
7. Đề xuất migration khỏi prefix matching và header role không đáng tin.
8. Viết test cho unknown scope, scope chỉ được request, cross-tenant, role mismatch, IDOR và confused deputy.
9. Đề xuất audit event để truy vết client, user, gateway và service thực hiện hành động.

**Gợi ý tự đánh giá:** orders:read không thể suy ra update hoặc delete. OIDC profile là scope yêu cầu claims, không phải permission đọc mọi hồ sơ. Tenant ID từ query phải được kiểm tra với membership và resource. Gateway có service credential rộng cần giữ delegation context và kiểm tra quyền caller trước khi thực thi.

---

**Điểm cần nhớ:** Scope mapping là bước chuyển **scope đã được cấp** thành permission nội bộ trong một trust boundary xác định. Scope không thay role, ownership, tenant, audience hoặc policy. Một quyết định an toàn cần xác minh token, ánh xạ exact-match theo issuer/audience/version, kết hợp principal và resource context, rồi áp dụng deny-by-default tại service thực sự truy cập dữ liệu.
