# Nhầm lẫn giữa xác thực thành công và quyền truy cập đối tượng

> **Chương:** Tấn công JWT  
> **Phạm vi:** Security – JSON Web Token (JWT), thuộc module SECURITY_TOKEN_SECURITY_JWT. Nội dung áp dụng cho API và hệ thống quản lý tài nguyên nói chung, độc lập với ngôn ngữ lập trình hoặc framework.

## 1. Vấn đề: token hợp lệ nhưng đối tượng không thuộc quyền truy cập

Một API có thể xác minh JWT hoàn toàn chính xác: chữ ký hợp lệ, issuer được tin cậy, audience dành cho API hiện tại, token chưa hết hạn và có scope cho phép gọi chức năng tương ứng. Tuy nhiên, request vẫn có thể truy cập dữ liệu của người khác nếu API không kiểm tra quyền trên đối tượng cụ thể.

Ví dụ, Alice có access token hợp lệ với scope `invoice:read`. Cô ấy được phép gọi chức năng đọc hóa đơn. Request sau trả về hóa đơn của Alice:

~~~http
GET /api/invoices/inv-1001 HTTP/1.1
Authorization: Bearer <alice-access-token>
~~~

Alice thay ID trong request:

~~~http
GET /api/invoices/inv-2002 HTTP/1.1
Authorization: Bearer <alice-access-token>
~~~

Nếu `inv-2002` thuộc Bob nhưng API chỉ xác minh JWT rồi truy vấn hóa đơn theo ID, Alice có thể đọc dữ liệu của Bob bằng chính token hợp lệ của mình.

Đây là **Broken Object Level Authorization (BOLA)**. Lỗi nằm ở quyết định cho phép truy cập đối tượng, không nhất thiết nằm ở cơ chế xác minh JWT.

**Nguyên tắc:** xác thực người gọi và xác minh token là bước xác định principal. Sau đó, với từng thao tác, hệ thống phải quyết định principal đó có quyền thực hiện hành động trên đúng đối tượng được yêu cầu hay không.

## 2. Phân biệt Authentication và Object-Level Authorization

Hai bước trả lời hai câu hỏi khác nhau:

| Khía cạnh | Authentication | Object-Level Authorization |
|---|---|---|
| Câu hỏi | Ai đang gửi request? | Người đó có được thực hiện hành động trên đối tượng này không? |
| Đầu vào chính | Credential, chữ ký, issuer, thời hạn, audience, sender proof nếu có | Principal, hành động, đối tượng, tenant, quan hệ và ngữ cảnh |
| Kết quả | Principal đã được xác minh hoặc request không hợp lệ | Cho phép hoặc từ chối thao tác cụ thể |
| Ví dụ | JWT đại diện cho `user-123` đã được xác minh | `user-123` có được đọc `invoice-2002` không? |
| Phạm vi | Danh tính và tính hợp lệ của credential | Quyền trên từng tài nguyên và hành động |

~~~mermaid
flowchart TD
    A["Request + JWT"] --> B["Xác minh chữ ký, iss, aud, exp và token type"]
    B -->|"Không hợp lệ"| X["Từ chối authentication"]
    B -->|"Hợp lệ"| C["Tạo principal đã xác minh"]
    C --> D["Xác định object và action được yêu cầu"]
    D --> E["Đánh giá tenant, ownership, relationship và context"]
    E -->|"Deny"| Y["Từ chối request"]
    E -->|"Allow"| Z["Thực hiện thao tác trong phạm vi được phép"]
~~~

Một JWT có thể chứa các claims như:

~~~json
{
  "iss": "https://identity.example.test",
  "sub": "user-123",
  "aud": "billing-api",
  "scope": "invoice:read invoice:approve",
  "exp": 1800000300
}
~~~

Sau khi xác minh token, API có thể kết luận token do issuer được tin cậy phát hành, principal là `user-123`, token dành cho `billing-api`, có scope được khai báo và còn trong thời hạn hiệu lực.

Nhưng các thông tin đó chưa trả lời:

- Hóa đơn được yêu cầu có thuộc tenant mà user đang hoạt động không?
- User có phải chủ sở hữu, người được chia sẻ hoặc người phụ trách hóa đơn không?
- User có quyền đọc nhưng có được quyền duyệt hoặc xóa hóa đơn không?
- Quan hệ giữa user và hóa đơn còn hiệu lực tại thời điểm request không?
- Hóa đơn có đang ở trạng thái cho phép thao tác không?

Do đó, xác minh JWT thành công không được dùng thay cho object-level authorization.

## 3. BOLA, IDOR và các lỗi kiểm soát truy cập liên quan

### 3.1. BOLA là gì?

OWASP API Security Top 10 xếp **API1:2023 – Broken Object Level Authorization** là một rủi ro API riêng. Lỗi xảy ra khi API nhận ID của đối tượng từ request nhưng không xác minh người gọi có quyền thực hiện hành động trên đối tượng đó.

ID có thể là số tuần tự, UUID/GUID, chuỗi ngẫu nhiên, tên tài nguyên, slug, account number, invoice number, VIN hoặc document key. ID có thể nằm trong path, query, header, cookie hoặc request body.

Không có loại ID nào tự động bảo đảm quyền truy cập. UUID khó đoán có thể làm giảm khả năng phát hiện đối tượng, nhưng không thay thế kiểm tra quyền.

### 3.2. IDOR là gì?

**Insecure Direct Object Reference (IDOR)** mô tả tình huống ứng dụng cho phép người dùng thay đổi tham chiếu đến đối tượng và truy cập đối tượng không được phép.

~~~text
GET /api/documents/1001
GET /api/documents/1002
GET /api/documents/1003
~~~

Nếu API không ràng buộc document với principal hiện tại, người dùng có thể thay ID để đọc, sửa hoặc xóa tài liệu của người khác.

IDOR thường được dùng để mô tả cách khai thác qua tham chiếu đối tượng trực tiếp. BOLA nhấn mạnh lỗi thiếu kiểm soát quyền ở cấp đối tượng trong API. Hai khái niệm có vùng giao nhau; BOLA không chỉ giới hạn ở IDOR kiểu số tuần tự.

### 3.3. Phân biệt BOLA, BFLA và BOPLA

| Loại lỗi | Kiểm soát bị thiếu | Ví dụ |
|---|---|---|
| **BOLA – Broken Object Level Authorization** | Không kiểm tra quyền trên đối tượng cụ thể | Alice có thể đọc hóa đơn của Bob bằng cách đổi invoice ID. |
| **BFLA – Broken Function Level Authorization** | Không kiểm tra quyền gọi chức năng | User thường gọi được endpoint chỉ dành cho quản trị viên. |
| **BOPLA – Broken Object Property Level Authorization** | Không kiểm tra quyền đọc/sửa từng thuộc tính | User sửa `owner_id`, `tenant_id`, `approved` hoặc đọc trường nội bộ không được phép. |

Một request có thể mắc nhiều loại lỗi cùng lúc. Ví dụ, user không được phép duyệt hóa đơn của tenant khác có thể khai thác cả quyền chức năng và quyền đối tượng. Cần xác định chính xác lớp kiểm soát bị thiếu để thiết kế kiểm thử và biện pháp khắc phục.

### 3.4. Horizontal và vertical privilege escalation

- **Horizontal privilege escalation:** Alice truy cập hoặc sửa tài nguyên của Bob dù hai người có cùng vai trò.
- **Vertical privilege escalation:** user thường thực hiện thao tác hoặc truy cập tài nguyên chỉ dành cho vai trò cao hơn.

BOLA thường thể hiện dưới dạng horizontal escalation. Tuy nhiên, nếu ID do người dùng điều khiển ánh xạ đến đối tượng đặc quyền hoặc đối tượng quản trị, hậu quả có thể trở thành vertical escalation.

## 4. Cách khai thác khi API nhầm xác thực thành quyền truy cập đối tượng

### 4.1. Thay đổi ID trong path

~~~http
GET /api/accounts/acc-1001
Authorization: Bearer <valid-token>
~~~

Kẻ tấn công thay `acc-1001` thành `acc-2002`. Nếu API chỉ xác minh JWT rồi truy vấn theo ID, dữ liệu tài khoản khác có thể bị trả về.

### 4.2. Thay đổi ID trong query

~~~http
GET /api/transactions?account_id=acc-2002
Authorization: Bearer <valid-token>
~~~

API có thể kiểm tra token hợp lệ nhưng không kiểm tra user có quan hệ với `acc-2002`.

### 4.3. Thay đổi ID trong request body

~~~http
PATCH /api/profile
Authorization: Bearer <valid-token>
Content-Type: application/json

{
  "profile_id": "profile-of-another-user",
  "display_name": "Updated name"
}
~~~

Nếu backend tin `profile_id` do client gửi và không ràng buộc đối tượng với principal đã xác minh, user có thể sửa hồ sơ của người khác.

### 4.4. Lạm dụng endpoint danh sách hoặc tìm kiếm

Không phải BOLA chỉ xuất hiện ở endpoint đọc một bản ghi. Một API có thể kiểm tra quyền ở endpoint chi tiết nhưng bỏ sót ở danh sách hóa đơn, tìm kiếm khách hàng, bộ lọc theo tenant/project, báo cáo tổng hợp, export CSV/PDF, endpoint đếm số lượng, thống kê hoặc tải file.

Ví dụ, endpoint `/api/invoices/{id}` đã được bảo vệ nhưng `/api/invoices?customer_id=...` không lọc theo quyền của user. Kẻ tấn công có thể lấy dữ liệu hàng loạt qua endpoint danh sách.

### 4.5. ID lồng nhau không bảo đảm quan hệ cha-con

~~~http
GET /api/teams/team-A/documents/doc-900
Authorization: Bearer <valid-token>
~~~

API cần xác minh cả hai điều kiện:

1. Principal có quyền truy cập `team-A`.
2. `doc-900` thực sự thuộc `team-A` và principal có quyền thực hiện hành động trên document đó.

Không được chỉ kiểm tra quyền với team rồi tin mọi document ID nằm trong path. Cũng không được chỉ kiểm tra document ID mà bỏ qua quan hệ với team được chỉ định.

### 4.6. GraphQL và batch request

Một GraphQL API có thể cung cấp object theo ID thông qua query, mutation hoặc danh sách ID. Việc kiểm tra ở một resolver không bảo đảm mọi đường truy cập khác đều an toàn.

Tương tự, batch endpoint có thể nhận:

~~~json
{
  "document_ids": [
    "doc-100",
    "doc-200",
    "doc-300"
  ]
}
~~~

Mỗi đối tượng phải được kiểm tra quyền riêng. Không được giả định cả batch đều thuộc cùng một user chỉ vì request được xác thực một lần.

## 5. Những claims JWT nào có thể hỗ trợ authorization?

JWT cung cấp thông tin về principal và ngữ cảnh cấp token. Một số claims có thể hỗ trợ policy, nhưng không tự tạo quyền trên mọi đối tượng.

| Claim | Ý nghĩa | Giới hạn khi kiểm tra object-level authorization |
|---|---|---|
| `iss` | Issuer phát hành token | Xác định nguồn tin cậy, không xác định quyền trên đối tượng. |
| `sub` | Subject được token đại diện | Định danh principal; không chứng minh principal sở hữu mọi object. |
| `aud` | Recipient/resource server dự kiến | Giới hạn nơi token được sử dụng, không xác định object nào được truy cập. |
| `scope` | Phạm vi quyền được cấp | Thường biểu diễn quyền ở mức API/action; vẫn cần kiểm tra đối tượng. |
| `roles` | Vai trò của principal theo profile | Vai trò không tự chứng minh quan hệ với một bản ghi cụ thể. |
| `tenant_id` | Tenant context theo profile của hệ thống | Không chứng minh user vẫn là thành viên active hoặc object thuộc tenant đó. |
| `groups` | Nhóm hoặc đơn vị mà principal thuộc về | Cần xác minh ý nghĩa, độ mới và quan hệ với object. |
| `exp`, `nbf`, `iat` | Thông tin thời gian | Kiểm soát thời hạn token, không kiểm tra quyền trên object. |
| `jti` | Định danh token | Hỗ trợ nhận diện/revocation token; không phải object permission. |
| `cnf` | Thông tin sender constraint trong profile phù hợp | Ràng buộc người gửi token, không thay thế authorization trên object. |

### 5.1. `sub` không đồng nghĩa với `owner_id`

Một lỗi thường gặp là chỉ so sánh subject trong token với owner ID của object:

~~~text
token.sub == object.owner_id
~~~

Điều kiện này có thể là một phần của policy, nhưng không đủ cho mọi mô hình chia sẻ hoặc phân quyền. Cần phân biệt hai miền định danh:

- `sub` định danh principal.
- `object_id` định danh tài nguyên.

Ngay cả khi object có trường `owner_id`, so sánh owner với subject chỉ giải quyết trường hợp quyền chỉ dành cho chủ sở hữu. Một tài nguyên có thể được chia sẻ cho nhiều người, được quản lý bởi nhóm, được giao cho nhân viên phụ trách hoặc có quyền theo quan hệ tổ chức. OWASP cũng lưu ý rằng chỉ so sánh user ID trong JWT với ID parameter không đủ để khắc phục BOLA.

Policy cần mô tả quan hệ thực tế thay vì giả định mọi quyền đều dựa trên quyền sở hữu trực tiếp.

### 5.2. Scope không phải quyền sở hữu đối tượng

~~~json
{
  "sub": "alice",
  "scope": "invoice:read"
}
~~~

Scope cho biết token có quyền yêu cầu chức năng đọc hóa đơn theo profile. Nó không có nghĩa Alice được đọc tất cả hóa đơn trong hệ thống.

Quyết định cuối cùng cần kết hợp hành động `invoice:read`, đối tượng hóa đơn cụ thể, tenant và quan hệ của Alice với hóa đơn, policy hiện tại và trạng thái tài nguyên.

### 5.3. Claim tenant có thể cũ

~~~json
{
  "sub": "user-123",
  "tenant_id": "tenant-A",
  "exp": 1800000300
}
~~~

Sau khi token được phát hành, user bị loại khỏi tenant-A nhưng token vẫn còn hạn. Nếu API chỉ tin `tenant_id` trong JWT, user có thể tiếp tục truy cập dữ liệu tenant-A đến khi token hết hạn.

Với membership hoặc quyền có thể thay đổi nhanh, cần xem xét:

- Tra cứu membership hiện tại.
- Token version/security version.
- Introspection hoặc cơ chế revocation.
- Access token có thời hạn phù hợp.
- Policy kiểm tra trạng thái hiện tại cho thao tác nhạy cảm.

Không sử dụng claim tenant như một chứng cứ bất biến nếu membership có thể bị thu hồi trong thời hạn token.

### 5.4. Claims phải đến từ nguồn tin cậy

Chỉ sử dụng claims sau khi JWT đã được xác minh theo đúng profile. Không lấy `sub`, `tenant_id`, `roles` hoặc `scope` từ request body/header do client tự gửi để thay thế claims đã xác minh.

Cũng cần kiểm tra issuer, audience, loại token và quy tắc phân biệt token. Một ID Token, access token hoặc JWT tùy chỉnh có thể có cấu trúc tương tự nhưng mục đích khác nhau.

## 6. Mô hình quyết định quyền trên một đối tượng

Một quyết định object-level authorization nên xét ít nhất năm thành phần:

| Thành phần | Câu hỏi | Ví dụ |
|---|---|---|
| **Subject** | Ai đang yêu cầu? | User Alice, service Orders, administrator của tenant. |
| **Action** | Đang làm gì? | Read, update, approve, delete, export. |
| **Object** | Tài nguyên cụ thể nào? | Invoice 2002, document 900, account 12. |
| **Relationship/Attributes** | Principal có quan hệ hoặc thuộc tính nào với object? | Owner, member, assignee, viewer, tenant membership. |
| **Context** | Điều kiện môi trường/nghiệp vụ nào áp dụng? | Trạng thái object, thời gian, mức rủi ro, approval state. |

Có thể biểu diễn quyết định:

~~~text
allow(subject, action, object, context) =
    authenticated(subject)
    AND action_allowed_for_subject(subject, action)
    AND object_belongs_to_allowed_tenant(subject, object)
    AND relationship_allows(subject, action, object)
    AND object_state_allows(action, object)
    AND context_policy_allows(subject, action, object, context)
~~~

Đây là mô hình khái niệm. Mỗi hệ thống cần xác định điều kiện thực tế và thứ tự đánh giá phù hợp.

### 6.1. RBAC, ABAC và ReBAC

- **RBAC (Role-Based Access Control):** quyết định dựa trên vai trò, ví dụ `invoice-reader` hoặc `tenant-admin`.
- **ABAC (Attribute-Based Access Control):** quyết định dựa trên thuộc tính của subject, object và môi trường, ví dụ tenant, mức phân loại dữ liệu, trạng thái hóa đơn, thời gian.
- **ReBAC (Relationship-Based Access Control):** quyết định dựa trên quan hệ giữa principal và object, ví dụ owner, collaborator, project member hoặc assigned reviewer.

RBAC hữu ích cho quyền chức năng và vai trò chung. ABAC/ReBAC thường cần thiết khi quyền phụ thuộc object, tenant, chia sẻ hoặc quan hệ nghiệp vụ. Các mô hình có thể được kết hợp.

### 6.2. Policy Decision Point và Policy Enforcement Point

Trong kiến trúc có policy tập trung:

- **Policy Decision Point (PDP):** đánh giá policy và trả kết quả cho một yêu cầu cụ thể.
- **Policy Enforcement Point (PEP):** bảo đảm thao tác chỉ tiếp tục khi PDP cho phép.
- **Policy Information Point (PIP):** cung cấp thuộc tính/quan hệ cần cho quyết định.
- **Policy Administration Point (PAP):** quản lý policy.

Dù policy được đánh giá ở một dịch vụ riêng, thành phần thực hiện truy cập dữ liệu vẫn phải bảo đảm kết quả được áp dụng. Không được gọi PDP rồi bỏ qua kết quả hoặc để một đường truy cập khác không đi qua enforcement point.

## 7. Những thao tác phải kiểm tra object-level authorization

Bất kỳ thao tác nào truy cập đối tượng theo dữ liệu do client cung cấp đều cần kiểm tra quyền.

| Thao tác | Ví dụ | Kiểm tra cần thiết |
|---|---|---|
| Read | `GET /invoices/{id}` | Có được xem invoice cụ thể không? |
| Update | `PATCH /invoices/{id}` | Có được sửa các trường được yêu cầu không? |
| Delete | `DELETE /documents/{id}` | Có được xóa document cụ thể không? |
| Approve | `POST /invoices/{id}/approve` | Có quyền duyệt invoice ở trạng thái hiện tại không? |
| Download | `GET /files/{id}/download` | Có quyền truy cập file và phiên bản này không? |
| Share | `POST /documents/{id}/shares` | Có quyền chia sẻ object và cấp quyền cho recipient không? |
| Export | `POST /reports/{id}/export` | Có quyền xuất dữ liệu trong report không? |
| List/Search | `GET /invoices?customer_id=...` | Kết quả và metadata có được giới hạn theo quyền không? |
| Bulk | `POST /documents/bulk-delete` | Mọi object trong danh sách có được phép xử lý không? |
| Nested resource | `/teams/{teamId}/documents/{docId}` | Cả quan hệ cha-con và quyền trên document có hợp lệ không? |

Không chỉ kiểm tra endpoint chi tiết. Tất cả đường đi đến cùng tài nguyên phải tuân thủ cùng policy.

## 8. Phòng chống BOLA trong hệ thống dùng JWT

### 8.1. Xác minh JWT trước, rồi tạo principal đáng tin cậy

Trước khi kiểm tra quyền đối tượng:

1. Xác minh chữ ký hoặc cơ chế xác thực token theo profile.
2. Kiểm tra issuer, audience, thời hạn và token type.
3. Xác định subject và các claims được tin cậy.
4. Xác minh sender constraint nếu token yêu cầu.
5. Tạo principal nội bộ từ dữ liệu đã xác minh.

Không dùng principal chưa được xác minh để tra cứu dữ liệu nhạy cảm hoặc thực hiện quyết định authorization.

### 8.2. Ràng buộc truy vấn với principal và tenant

Thay vì truy vấn object chỉ theo ID:

~~~text
object = repository.find_by_id(request.object_id)
~~~

hãy giới hạn việc truy xuất theo ngữ cảnh quyền:

~~~text
object = repository.find_accessible_object(
    object_id = request.object_id,
    tenant_id = principal.active_tenant,
    subject_id = principal.subject_id
)
~~~

Đây là ví dụ khái niệm. Với quan hệ chia sẻ hoặc phân công phức tạp, truy vấn cần xét ACL, membership hoặc policy tương ứng.

Có thể kiểm tra quyền ở tầng policy sau khi tìm được object, hoặc đưa điều kiện quyền vào truy vấn dữ liệu. Điều quan trọng là không trả hoặc thay đổi object trước khi quyền đã được xác minh.

### 8.3. Kiểm tra quyền cho đúng hành động

Quyền đọc không tự động bao gồm quyền sửa, xóa hoặc duyệt.

| Quan hệ của user với invoice | Read | Update | Approve | Delete |
|---|---:|---:|---:|---:|
| Owner | Có | Có thể | Không mặc định | Theo policy |
| Viewer được chia sẻ | Có | Không | Không | Không |
| Assigned approver | Có | Không mặc định | Có khi đúng trạng thái | Không |
| Tenant administrator | Theo policy tenant | Theo policy tenant | Theo policy tenant | Theo policy tenant |
| Người ngoài tenant | Không | Không | Không | Không |

Ma trận này chỉ là ví dụ. Quyền thực tế phụ thuộc quy tắc nghiệp vụ và phân tách nhiệm vụ của hệ thống.

### 8.4. Không tin ID hoặc ownership do client cung cấp

Các trường như `owner_id`, `user_id`, `tenant_id`, `organization_id`, `created_by`, `approved_by` và `is_admin` không được tự động tin khi nhận từ request body.

Thông thường, server phải lấy subject và tenant context từ principal đã xác minh, rồi tự xác định object và quan hệ hợp lệ. Nếu nghiệp vụ cho phép chuyển quyền sở hữu hoặc chuyển tenant, đó phải là một thao tác riêng có policy và audit rõ ràng.

### 8.5. Deny by default

Nếu policy không có quy tắc cho phép rõ ràng, từ chối truy cập.

Không được coi các trường hợp sau là mặc định cho phép:

- Không tìm thấy ACL.
- Không xác định được tenant.
- PDP timeout hoặc không trả kết quả.
- Object không có owner.
- Quan hệ chia sẻ đã hết hạn.
- Trạng thái tài nguyên không rõ.
- Một claim cần thiết bị thiếu hoặc không hợp lệ.

Hành vi khi policy service không khả dụng phải được xác định trước. Với dữ liệu nhạy cảm, không thể kiểm tra quyền thì không nên tiếp tục thao tác.

### 8.6. ID khó đoán chỉ là lớp bổ sung

Dùng UUID hoặc ID ngẫu nhiên giúp giảm khả năng dò tìm đối tượng. Tuy nhiên, nếu API không kiểm tra quyền, người có được ID qua email, link chia sẻ, log hoặc nguồn khác vẫn có thể truy cập object.

Không dùng tính bí mật của ID làm authorization. Nếu dùng signed reference hoặc capability URL, cần coi nó là credential có phạm vi và thời hạn rõ ràng, bảo vệ khỏi rò rỉ và replay; nó không tự thay thế policy khi người dùng có danh tính và quyền động.

## 9. Ví dụ: API đọc hóa đơn

### 9.1. Cách xử lý dễ mắc BOLA

~~~text
function get_invoice(request):
    principal = verify_jwt(request.authorization_header)

    require_scope(principal, "invoice:read")

    invoice = invoice_repository.find_by_id(request.path.invoice_id)

    if invoice is null:
        return not_found()

    return invoice
~~~

Vấn đề: JWT được xác minh, scope `invoice:read` được kiểm tra, nhưng invoice chỉ được truy vấn theo ID. Không có kiểm tra tenant, ownership, sharing hoặc assignment. Alice có thể đổi ID để truy cập hóa đơn của Bob.

### 9.2. Cách xử lý có kiểm soát object-level authorization

~~~text
function get_invoice(request):
    principal = verify_access_token(request.authorization_header)

    require_expected_issuer(principal.issuer)
    require_expected_audience(principal.audience, "billing-api")
    require_scope(principal, "invoice:read")

    invoice = invoice_repository.find_by_id(request.path.invoice_id)

    if invoice is null:
        return not_found()

    decision = authorization_policy.evaluate(
        subject = principal,
        action = "invoice:read",
        object = invoice,
        context = {
            "active_tenant": principal.active_tenant,
            "request_time": current_time()
        }
    )

    if decision != "ALLOW":
        return access_denied_or_not_found()

    return project_invoice_fields(principal, invoice)
~~~

Luồng này tách rõ:

1. Xác minh token và principal.
2. Kiểm tra quyền chức năng/scope.
3. Tìm object.
4. Đánh giá quyền trên object cụ thể.
5. Chỉ trả dữ liệu sau khi quyết định cho phép.
6. Chỉ trả các trường được phép theo policy.

Trong hệ thống lớn, truy vấn có thể được giới hạn ngay từ đầu theo tenant và quan hệ được phép để tránh truy xuất hoặc xử lý dữ liệu ngoài phạm vi. Dù chọn cách nào, quyết định authorization phải được áp dụng trước khi dữ liệu được trả về hoặc thay đổi.

## 10. Bảo vệ thao tác ghi và tránh TOCTOU

### 10.1. Kiểm tra quyền trước khi cập nhật

Với thao tác update, không nên chỉ xác minh quyền đọc object rồi mặc định cho phép sửa.

~~~text
function update_invoice(request):
    principal = verify_access_token(request.authorization_header)
    require_scope(principal, "invoice:write")

    invoice = invoice_repository.find_by_id(request.path.invoice_id)

    require_authorized(
        principal,
        action = "invoice:update",
        object = invoice
    )

    allowed_changes = validate_allowed_invoice_fields(
        request.body,
        principal,
        invoice
    )

    invoice_repository.update(invoice.id, allowed_changes)
~~~

`allowed_changes` cần được tạo từ danh sách trường được phép thay đổi. Không bind toàn bộ request body vào object rồi cho client sửa `owner_id`, `tenant_id`, `approval_status` hoặc các thuộc tính kiểm soát bảo mật.

### 10.2. TOCTOU: quyền có thể thay đổi giữa kiểm tra và sử dụng

TOCTOU (Time-of-Check to Time-of-Use) xảy ra khi hệ thống kiểm tra quyền ở một thời điểm, nhưng object hoặc quan hệ thay đổi trước khi thao tác thực sự hoàn tất.

Ví dụ:

1. Alice được chia sẻ quyền sửa tài liệu.
2. API kiểm tra Alice có quyền.
3. Quản trị viên thu hồi quyền chia sẻ.
4. API tiếp tục ghi dữ liệu dựa trên kết quả kiểm tra cũ.

Với thao tác nhạy cảm, cần giảm khoảng cách giữa authorization check và mutation:

- Thực hiện kiểm tra và cập nhật trong cùng transaction khi có thể.
- Dùng điều kiện version/optimistic concurrency.
- Kiểm tra lại trạng thái quan hệ hoặc policy khi commit nếu cần.
- Đưa điều kiện tenant/owner/ACL vào câu lệnh cập nhật có điều kiện.
- Không dùng quyết định cache quá lâu cho quyền có thể bị thu hồi.

~~~text
UPDATE invoices
SET status = "approved", version = version + 1
WHERE id = :invoice_id
  AND tenant_id = :active_tenant
  AND assigned_approver_id = :principal_id
  AND status = "pending"
  AND version = :expected_version
~~~

Câu lệnh trên chỉ là minh họa. Policy thực tế có thể phức tạp hơn và cần transaction phù hợp. Mục tiêu là bảo đảm điều kiện authorization và trạng thái nghiệp vụ vẫn đúng tại thời điểm thay đổi.

## 11. Những tình huống dễ bỏ sót

### 11.1. List, search, pagination và aggregation

Với endpoint danh sách, cần giới hạn tập dữ liệu trước khi tính kết quả:

- Chỉ trả object mà principal có quyền xem.
- Tổng số kết quả phải được tính trên tập object được phép.
- Facet, aggregation và thống kê không được tiết lộ dữ liệu ngoài phạm vi.
- Cursor pagination phải gắn với ngữ cảnh truy vấn và policy.
- Export phải sử dụng cùng điều kiện authorization với endpoint đọc.

Không chỉ ẩn object khỏi response sau khi lấy toàn bộ dữ liệu. Cách đó có thể làm rò rỉ count, thứ tự, thời gian xử lý hoặc metadata của đối tượng không được phép.

### 11.2. Bulk operations

Nếu request có nhiều ID:

~~~json
{
  "invoice_ids": ["inv-1", "inv-2", "inv-3"],
  "action": "archive"
}
~~~

Hệ thống phải kiểm tra quyền trên từng invoice. Cần xác định rõ semantics:

- **All-or-nothing:** nếu một object không được phép, từ chối toàn bộ batch.
- **Per-item result:** trả kết quả riêng cho từng object nhưng không tiết lộ quá nhiều thông tin về object không thuộc quyền.

Không được xử lý tất cả ID chỉ vì principal có scope chung `invoice:archive`.

### 11.3. Nested resources

~~~text
/organizations/{orgId}/projects/{projectId}/documents/{documentId}
~~~

Cần xác minh principal có quyền trong organization, project có thuộc organization được chỉ định, document có thuộc project đó và principal có quyền trên document cho hành động cụ thể không.

Không tin quan hệ cha-con chỉ vì client gửi đúng cả ba ID.

### 11.4. File, ảnh và static resources

BOLA có thể xảy ra ngoài API JSON: file download endpoint, object storage key, ảnh riêng tư, tài liệu export, file đính kèm hoặc static resource được phân phối qua CDN.

Nếu API cấp URL tải file có chữ ký, URL đó hoạt động như một capability/bearer credential trong phạm vi và thời hạn được thiết kế. Cần giới hạn object, quyền, thời hạn, khả năng sử dụng lại và rò rỉ URL. Không để bucket hoặc storage object riêng tư trở thành public chỉ vì API đã xác minh JWT trước đó.

### 11.5. Background jobs và message queues

Một request có thể tạo công việc xử lý bất đồng bộ:

1. User yêu cầu export report.
2. API xác minh JWT và tạo job.
3. Worker xử lý job sau vài phút.
4. Trong thời gian chờ, quyền của user hoặc quyền truy cập report có thể bị thu hồi.

Job cần lưu actor/tenant và authorization context đủ để kiểm toán, nhưng không nên lưu raw bearer token nếu không cần. Khi thực thi, worker cần kiểm tra lại trạng thái quyền theo policy của tác vụ và thời điểm xử lý.

### 11.6. Multi-tenant

Trong hệ thống nhiều tenant, mọi truy vấn object cần ràng buộc tenant theo principal và policy hiện tại.

~~~http
GET /api/invoices?tenant_id=tenant-B
Authorization: Bearer <token-for-tenant-A>
~~~

API phải xác định tenant context hợp lệ từ principal/session hoặc lựa chọn tenant đã được xác minh, rồi kiểm tra membership và quyền hiện tại.

Không chỉ lọc ở UI. Tenant isolation phải được thực thi ở server và tầng truy cập dữ liệu phù hợp.

### 11.7. Admin và quyền hỗ trợ

Vai trò `admin` có thể có phạm vi toàn hệ thống, một tenant hoặc một nhóm tài nguyên. Không suy ra mọi admin đều được truy cập mọi object.

Cần xác định global administrator hay tenant administrator, quyền quản trị có giới hạn theo tenant không, có cần lý do hỗ trợ hoặc ticket, có yêu cầu step-up authentication hoặc approval hai người, và có audit riêng cho truy cập đặc quyền không.

Quyền hỗ trợ/impersonation phải có policy riêng và không được làm mờ danh tính actor thực hiện thao tác.

## 12. Cache và các quyết định authorization

Cache có thể vô tình chia sẻ dữ liệu hoặc quyết định quyền giữa các principal.

### 12.1. Cache response

Nếu cache key chỉ dựa trên URL:

~~~text
GET /api/invoices/inv-2002
~~~

response được tạo cho Alice có thể bị trả cho Bob nếu cache không phân biệt ngữ cảnh truy cập.

Cần xem xét cache key theo subject/principal, tenant, object và action, policy/version hoặc authorization context khi cần, cùng các thuộc tính ảnh hưởng đến response.

Không cache response riêng tư trong shared cache nếu không có cơ chế partition và kiểm soát phù hợp. Với dữ liệu nhạy cảm, có thể cần `Cache-Control: private` hoặc `no-store` tùy kiến trúc.

### 12.2. Cache policy decision

Nếu quyền được cache:

- TTL phải phù hợp với tốc độ thay đổi membership/ACL.
- Có invalidation khi quyền bị thu hồi.
- Không dùng decision của user A cho user B.
- Không dùng quyết định của tenant A cho tenant B.
- Kiểm tra version của object và policy.
- Có fallback rõ ràng khi cache hoặc policy service không khả dụng.

Quyền truy cập có thể thay đổi trong thời hạn JWT. Vì vậy, token hợp lệ không bảo đảm một quyết định authorization được cache từ trước vẫn còn đúng.

## 13. Xử lý lỗi và logging

### 13.1. HTTP 403 hay 404?

Có thể sử dụng:

- `403 Forbidden` khi muốn thể hiện principal đã được xác thực nhưng không có quyền.
- `404 Not Found` khi policy yêu cầu che giấu sự tồn tại của object đối với người không được phép.

Việc chọn status code phụ thuộc threat model và API contract. Tuy nhiên, dùng `404` không thay thế authorization check. Cả hai trường hợp đều phải bảo đảm không trả dữ liệu hoặc thực hiện side effect trái phép.

Cần tránh để response body, kích thước, thời gian hoặc metadata tiết lộ object có tồn tại hay không khi chính sách yêu cầu che giấu.

### 13.2. Log sự kiện authorization

Có thể ghi request/correlation ID, principal ID đã xác minh, issuer hoặc client identity cần thiết, action được yêu cầu, object type và định danh nội bộ đã được kiểm soát, tenant context, kết quả allow/deny, reason code nội bộ, policy/version và thời điểm quyết định.

Không ghi raw JWT, refresh token, private data hoặc toàn bộ object vào log chỉ để điều tra BOLA.

Log cần hỗ trợ phát hiện một principal thử nhiều object ID, user liên tục truy cập object ngoài tenant, nhiều request bị từ chối trên endpoint nhạy cảm, thay đổi ID trong bulk/nested route hoặc hành vi đọc dữ liệu bất thường.

Không kết luận tấn công chỉ từ một lỗi 403/404; người dùng có thể truy cập nhầm link hoặc dữ liệu đã bị xóa. Cần kết hợp tần suất, pattern và ngữ cảnh.

## 14. Kiểm thử BOLA

### 14.1. Kiểm thử với nhiều principal

Tối thiểu cần có:

- Alice: owner của object A.
- Bob: owner của object B.
- Carol: viewer được chia sẻ object A.
- Admin: administrator có phạm vi tenant xác định.
- User từ tenant khác.

Với mỗi principal, thử truy cập object của chính mình, object được chia sẻ và object không thuộc quyền.

Không thể đánh giá BOLA chỉ bằng một token và một tài khoản. Cần kiểm thử chéo principal để phát hiện lỗi horizontal authorization.

### 14.2. Ma trận kiểm thử cơ bản

| Principal | Object | Action | Kết quả mong đợi |
|---|---|---|---|
| Alice | Invoice A thuộc Alice | Read | Cho phép nếu policy cho phép. |
| Alice | Invoice B thuộc Bob | Read | Từ chối. |
| Alice | Invoice A thuộc Alice | Approve | Chỉ cho phép nếu Alice có quyền duyệt và trạng thái phù hợp. |
| Carol | Invoice A được chia sẻ chỉ đọc | Read | Cho phép. |
| Carol | Invoice A được chia sẻ chỉ đọc | Update | Từ chối. |
| Bob | Document A thuộc tenant khác | Download | Từ chối. |
| Tenant admin A | Object thuộc tenant A | Read | Theo policy tenant admin. |
| Tenant admin A | Object thuộc tenant B | Delete | Từ chối nếu không có quyền cross-tenant được cấp rõ ràng. |
| Alice | Batch gồm A và B | Bulk update | Theo semantics batch; không cập nhật B trái phép. |
| Alice | Nested document không thuộc project được chỉ định | Read | Từ chối. |

### 14.3. Kiểm thử các đường truy cập khác nhau

- Thay ID trong path, query, header và body.
- Dùng ID tuần tự, UUID và ID ngẫu nhiên.
- Thử GET, POST, PATCH, PUT, DELETE và download.
- Thử list, search, count, aggregation và export.
- Thử bulk request và GraphQL query/mutation.
- Thử nested resources và object storage.
- Thử background job sau khi quyền bị thu hồi.
- Thử cùng object qua nhiều endpoint và service.
- Thử cache response sau khi user khác truy cập.
- Thử token còn hạn sau khi tenant membership hoặc ACL bị thu hồi.
- Thử thiếu claim, claim sai issuer hoặc tenant context không hợp lệ.

### 14.4. Kiểm thử không có side effect

Khi authorization thất bại, xác minh không có bản ghi bị cập nhật, file bị xóa/tải lên, message được phát đi, job được tạo, email/thanh toán/webhook được kích hoạt, cache chứa dữ liệu trái phép hoặc thông tin nhạy cảm bị trả trong error response.

## 15. Checklist phòng chống BOLA

- [ ] JWT được xác minh đúng issuer, audience, thời hạn và token type.
- [ ] Principal chỉ được tạo từ claims đã xác minh.
- [ ] Authentication được tách biệt với object-level authorization.
- [ ] Mọi endpoint dùng object ID từ client đều kiểm tra quyền trên object.
- [ ] Kiểm tra riêng từng action: read, update, delete, approve, export, download.
- [ ] Quyền được ràng buộc theo tenant, ownership, ACL hoặc relationship.
- [ ] Không tin `owner_id`, `tenant_id` hoặc role do client gửi.
- [ ] Không dùng UUID hoặc ID khó đoán làm cơ chế authorization.
- [ ] Có deny-by-default khi policy không cho phép hoặc không xác định được.
- [ ] List/search/count/export chỉ xử lý object trong phạm vi được phép.
- [ ] Bulk request kiểm tra từng object.
- [ ] Nested resource xác minh cả quan hệ cha-con.
- [ ] GraphQL, file, static resource và background job có kiểm tra riêng.
- [ ] Cache phân biệt principal/tenant và có invalidation khi policy thay đổi.
- [ ] Kiểm soát TOCTOU cho thao tác nhạy cảm.
- [ ] Có audit/log authorization an toàn.
- [ ] Có kiểm thử chéo nhiều user, tenant, role và relationship.
- [ ] Có regression test cho mọi lỗi BOLA đã phát hiện.

## 16. Câu hỏi tự kiểm tra

1. Vì sao JWT có chữ ký hợp lệ vẫn có thể được dùng để truy cập hóa đơn của người khác?
2. Authentication khác object-level authorization ở điểm nào?
3. BOLA và IDOR có quan hệ như thế nào?
4. BOLA khác BFLA và BOPLA ra sao?
5. Vì sao so sánh `sub` với `owner_id` không giải quyết được mọi trường hợp?
6. Scope `invoice:read` có đủ để cho phép đọc mọi invoice không? Vì sao?
7. Vì sao UUID không thể thay thế authorization?
8. Một API nested resource cần xác minh những quan hệ nào?
9. Làm thế nào để bảo vệ list, search, pagination và bulk operation?
10. TOCTOU có thể làm mất hiệu lực của một quyết định authorization như thế nào?
11. Cache có thể gây rò rỉ dữ liệu giữa hai principal ra sao?
12. Cần kiểm thử gì sau khi quyền tenant hoặc ACL bị thu hồi nhưng JWT vẫn còn hạn?

## 17. Tài liệu tham khảo

- [OWASP API Security Top 10 – API1:2023 Broken Object Level Authorization](https://api-security.owasp.org/editions/2023/en/0xa1-broken-object-level-authorization/): BOLA, thay đổi object ID, tác động và biện pháp phòng chống.
- [OWASP Authorization Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Authorization_Cheat_Sheet.html): deny by default, validate permissions on every request, least privilege, ABAC/ReBAC và kiểm tra ID đối tượng.
- [OWASP Insecure Direct Object Reference Prevention Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Insecure_Direct_Object_Reference_Prevention_Cheat_Sheet.html): ngăn truy cập đối tượng qua tham chiếu do người dùng kiểm soát.
- [CWE-639 – Authorization Bypass Through User-Controlled Key](https://cwe.mitre.org/data/definitions/639.html): truy cập dữ liệu của người khác bằng cách thay đổi khóa định danh đối tượng.
- [RFC 7519 – JSON Web Token (JWT)](https://www.rfc-editor.org/rfc/rfc7519.html): ý nghĩa các registered claims như `iss`, `sub`, `aud`, `exp`, `nbf` và `jti`.
- [NIST SP 800-162 – Guide to Attribute Based Access Control (ABAC)](https://csrc.nist.gov/pubs/sp/800/162/upd2/final): mô hình authorization dựa trên thuộc tính của subject, object, operation và environment.
