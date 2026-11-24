# Policy evaluation tại Resource Server

Khi một API nhận **access token** có chữ ký hợp lệ, điều đó **chưa đủ** để cho phép yêu cầu. Token có thể được phát hành bởi đúng **Authorization Server**, chưa hết hạn và dành cho API này, nhưng người gọi vẫn có thể không được quyền xem hóa đơn của khách hàng khác, thay đổi đơn hàng đã chốt hoặc truy cập dữ liệu thuộc tenant khác. Quyết định cuối cùng thuộc về **Resource Server**: tại đây hệ thống đánh giá chính sách phân quyền (**policy evaluation**) đối với **hành động, tài nguyên và ngữ cảnh cụ thể**.

Bài học nằm trong chương **Authorization** của module SECURITY_TOKEN_SECURITY_FUNDAMENTALS. Nội dung kết nối mô hình tin cậy của token với OAuth 2.0/OIDC, JWT và opaque token, các claim như *iss*, *aud*, *scope*, thời hạn token, cùng quyền nghiệp vụ luôn thay đổi trong hệ thống thực tế.

Sau bài này, bạn sẽ có thể:

- Phân biệt **token validation** (token có hợp lệ, đáng tin không?) với **authorization policy evaluation** (yêu cầu này có được phép không?).
- Xác định dữ liệu Resource Server phải dùng để ra quyết định: danh tính/chủ thể, client, scope, tài nguyên, quan hệ sở hữu, tenant, trạng thái nghiệp vụ và ngữ cảnh.
- Hiểu **Policy Enforcement Point (PEP)**, **Policy Decision Point (PDP)**, vai trò của API gateway và chính sách tại tầng dịch vụ.
- Thiết kế ví dụ phân quyền cho một API đa tenant, xử lý **401/403/404**, kiểm thử trường hợp bị từ chối và cân bằng giữa cache với độ mới của quyền.

## 1. Token hợp lệ và được phép truy cập là hai câu hỏi khác nhau

Giả sử một ứng dụng quản lý hóa đơn có endpoint:

~~~http
GET /tenants/t-17/invoices/inv-900 HTTP/1.1
Host: billing.example.org
Authorization: Bearer <access_token>
~~~

Ở đây, hóa đơn *inv-900* thuộc tenant *t-17*. Token có thể cho biết người gọi là tài khoản *user-42* và được cấp scope *invoices:read*. Nhưng chỉ dựa vào token, API **chưa biết** người này còn là thành viên tenant hay không, có vai trò được phép đọc hóa đơn hay không, và hóa đơn thực tế có thuộc tenant đó hay không.

Hai lớp quyết định:

| Lớp | Câu hỏi | Ví dụ dữ liệu cần kiểm tra | Kết quả |
|---|---|---|---|
| **Xác thực token (token validation)** | Đây có phải access token đáng tin và có hiệu lực cho API? | Chữ ký hoặc introspection, *iss*, *aud*, *exp*, *nbf*, loại token | Xác lập principal/claims tin cậy hoặc từ chối |
| **Đánh giá chính sách (policy evaluation)** | Principal này được làm hành động này trên tài nguyên này, trong điều kiện này không? | Scope, membership, role, ownership, trạng thái hóa đơn, tenant, thời điểm | Permit/Deny, có thể kèm các điều kiện thực thi |

Một **scope hợp lệ không phải quyền truy cập vô điều kiện**. Scope thường biểu thị mức quyền mà client đã được cấp hoặc giới hạn quyền dùng access token, chẳng hạn *invoices:read*. Quyền thực tế thường là **giao** giữa quyền đã cấp trong token và chính sách hiện hành của Resource Server.

Có thể diễn đạt ở mức khái niệm:

~~~text
Permit = valid_access_token
         AND correct_audience
         AND scope_allows_action
         AND current_subject_entitlement
         AND resource_policy_allows_action
         AND applicable_context_constraints
~~~

Nếu một điều kiện bắt buộc không được chứng minh hoặc dữ liệu phân quyền không đáng tin, hệ thống nên **mặc định từ chối** (*deny by default*). Công thức chỉ mô tả các nhóm điều kiện; từng hệ thống cần định nghĩa chính xác policy, cách xử lý thiếu dữ liệu và thứ tự thực thi.

### OAuth 2.0/OIDC đặt ranh giới ở đâu?

- **Authorization Server** xác thực hoặc kiểm tra ủy quyền theo flow, cấp access token và quyết định phạm vi token được cấp.
- **Resource Server** nhận access token và phải kiểm tra token dành cho mình, sau đó **tự thực thi chính sách bảo vệ tài nguyên**.
- **Client** là ứng dụng mang token. Client không thể tự tuyên bố mình được phép chỉ vì UI đã ẩn/hiện một nút.
- **OpenID Connect** cấp ID token phục vụ xác thực danh tính với client. **Không dùng ID token thay access token** để truy cập API.

Trong flow **client credentials**, principal có thể đại diện cho một dịch vụ hoặc một client, **không có người dùng cuối**. Policy phải phân biệt quyền của client máy với quyền của người dùng, tránh mặc nhiên diễn giải mọi giá trị *sub* là một tài khoản người dùng đang đăng nhập.

## 2. Quy trình đánh giá chính sách tại Resource Server

~~~mermaid
sequenceDiagram
    actor Caller as Client
    participant API as Resource Server / PEP
    participant Auth as Token verifier
    participant Store as Data/Entitlement store
    participant PDP as Policy Decision Point
    Caller->>API: Request + access token
    API->>Auth: Validate token and audience
    alt Token invalid
        Auth-->>API: Reject
        API-->>Caller: 401 Unauthorized
    else Token valid
        Auth-->>API: Trusted principal + claims
        API->>Store: Load resource and current entitlements
        Store-->>API: Resource, tenant, membership, status
        API->>PDP: Evaluate subject, action, resource, context
        PDP-->>API: Permit or Deny
        alt Permit
            API-->>Caller: Authorized result
        else Deny
            API-->>Caller: 403 Forbidden or policy-approved 404
        end
    end
~~~

Quy trình thường gồm:

1. **Chuẩn hóa request và xác định hành động**: ví dụ HTTP GET ở endpoint hóa đơn tương ứng action *invoice.read*. Không chỉ dựa vào URL: service phải biết thao tác nghiệp vụ nào thực sự được yêu cầu.
2. **Xác minh access token**: Resource Server xác nhận issuer đã tin cậy, audience đúng, loại token, hiệu lực thời gian, chữ ký và thuật toán (với JWT), hoặc kiểm tra trạng thái qua nguồn introspection đáng tin (với opaque token).
3. **Tạo principal từ dữ liệu đã được xác minh**: xác định user/service và client, các scope/claims liên quan. Không coi claims chỉ vừa giải mã Base64url là đáng tin trước khi kiểm tra chữ ký và những điều kiện hợp lệ.
4. **Nạp thông tin tài nguyên và quyền hiện hành**: ví dụ tenant sở hữu hóa đơn, tư cách thành viên, role, quan hệ sở hữu và trạng thái khóa/sửa của hóa đơn từ dữ liệu server kiểm soát.
5. **Đánh giá policy**: kết hợp token scopes, chính sách vai trò/thuộc tính/quan hệ, ràng buộc nghiệp vụ và ngữ cảnh. Trả về quyết định rõ ràng.
6. **Thực thi quyết định trong đúng điểm truy cập**: chỉ truy vấn dữ liệu nhạy cảm, trả kết quả hoặc thực hiện side effect khi đã được phép. Với cập nhật dữ liệu, bảo đảm điều kiện quyền không trở nên sai giữa lúc kiểm tra và lúc ghi.

Sơ đồ trên tách PEP/PDP để minh họa vai trò. Trên thực tế, PEP và PDP có thể là **cùng một ứng dụng**; không bắt buộc phát sinh HTTP call sang dịch vụ PDP cho mỗi request.

## 3. Policy được đánh giá dựa trên những dữ liệu nào?

Một quyết định đủ rõ thường được mô hình hóa theo **subject – action – resource – context**, đồng thời có thông tin về client và scope:

| Nhóm dữ liệu | Ví dụ | Nguồn nên tin và lưu ý |
|---|---|---|
| **Subject (chủ thể)** | User ID, service account, trạng thái tài khoản | Danh tính từ token đã xác minh; trạng thái hiện hành có thể cần tra kho người dùng |
| **Client** | Client ID, loại ứng dụng, dịch vụ gọi | Claim hoặc ngữ cảnh đã kiểm chứng; phân biệt token người dùng với token máy |
| **Action (hành động)** | *invoice.read*, *invoice.approve*, *invoice.export* | Được ánh xạ từ endpoint/nghiệp vụ ở server, không để client tự chọn mức quyền |
| **Resource (tài nguyên)** | ID, tenant sở hữu, chủ tạo, trạng thái hóa đơn | Từ database/trusted service; không chỉ lấy thuộc tính từ request body |
| **Token grant** | Audience, scopes, loại token, thời hạn | JWT đã xác minh hoặc introspection từ Authorization Server tin cậy |
| **Quan hệ/quyền hiện hành** | Membership đang hoạt động, vai trò kế toán, ownership, ủy quyền | Kho phân quyền tin cậy; chú ý hiệu lực cập nhật/thu hồi |
| **Context (ngữ cảnh)** | Thời điểm, phương thức xác thực, mức rủi ro, trạng thái quy trình | Nguồn đáng tin; không trực tiếp tin IP/header tự khai khi chưa qua proxy đáng tin |

### Những claim không thể tự biến thành quyền hiện hành

Giả sử JWT được phát hành lúc 09:00 có role *ACCOUNTANT* và hạn 30 phút. Đến 09:05, quản trị viên gỡ vai trò kế toán. Nếu API chỉ kiểm tra chữ ký và role lưu trong JWT, đến 09:30 token vẫn có thể chứa role cũ. Khi cần **thu hồi quyền ngay**, Resource Server phải có cách kiểm tra chính sách hiện hành, phiên bản quyền hoặc trạng thái thu hồi; hoặc sử dụng token sống ngắn với độ trễ được chấp nhận rõ ràng.

Tương tự, claim *tenant_id* có thể hỗ trợ giới hạn phạm vi nhưng **không thay thế** việc kiểm tra hóa đơn thực sự thuộc tenant nào và subject còn quyền trong tenant đó. Tham số *tenantId* trong đường dẫn là **đầu vào không đáng tin** cho đến khi so sánh với dữ liệu server.

## 4. RBAC, ABAC và ReBAC trong cùng một chính sách

Resource Server có thể kết hợp nhiều cách biểu diễn quyền:

| Mô hình | Ý tưởng | Ví dụ | Giới hạn khi dùng một mình |
|---|---|---|---|
| **RBAC** (Role-Based Access Control) | Gán quyền theo vai trò | *ACCOUNTANT* được xem hóa đơn trong tenant mà họ đang tham gia | Có role chưa chắc chứng minh hóa đơn thuộc tenant đó |
| **ABAC** (Attribute-Based Access Control) | Quyết định theo thuộc tính của chủ thể, tài nguyên và ngữ cảnh | Chỉ cho phép duyệt khi hóa đơn ở trạng thái *PENDING* và số tiền dưới hạn mức | Thuộc tính phải được lấy từ nguồn đủ tin và đủ mới |
| **ReBAC** (Relationship-Based Access Control) | Quyền dựa trên quan hệ | Người tạo được xem hóa đơn của mình, người quản lý xem hóa đơn của nhóm | Quan hệ phải được xác định đúng ngữ cảnh/tenant |

Ba mô hình có thể cùng xuất hiện. Ví dụ để cho phép xem hóa đơn:

~~~text
token có scope invoices:read
AND subject còn là thành viên của tenant sở hữu hóa đơn
AND (
      role trong tenant là ACCOUNTANT hoặc AUDITOR
      OR subject là người tạo hóa đơn
    )
~~~

Để **duyệt** hóa đơn, ngoài scope *invoices:approve*, có thể còn yêu cầu role *APPROVER*, hóa đơn ở trạng thái *PENDING* và không cho phép người tạo tự duyệt. Đây là **policy nghiệp vụ** do Resource Server thực thi; Authorization Server không thể suy ra đầy đủ từ một scope chung.

**Nguyên tắc đặc quyền tối thiểu:** scope đặt một giới hạn có tính giao thức và cấp quyền, trong khi các role/attribute/relationship đặt điều kiện cụ thể theo tài nguyên. Không suy diễn rằng một scope như *invoices:read* cấp quyền đọc **mọi** hóa đơn trong hệ thống.

## 5. Ví dụ xuyên suốt: Policy evaluation cho API hóa đơn nhiều tenant

### 5.1. Thiết kế policy rõ ràng

Giả sử dịch vụ *billing-api* có hai hành động:

| Hành động | Điều kiện token | Điều kiện dữ liệu hiện hành |
|---|---|---|
| **invoice.read** | Access token dành cho *billing-api* có scope *invoices:read* | Hóa đơn thuộc tenant chỉ định; subject là thành viên đang hoạt động; có role *ACCOUNTANT*/*AUDITOR* hoặc là người tạo hóa đơn |
| **invoice.approve** | Token dành cho *billing-api* có scope *invoices:approve* | Subject là thành viên đang hoạt động, role *APPROVER*, hóa đơn thuộc tenant, trạng thái *PENDING*, subject không phải người tạo |

Giả sử issuer là *https://auth.example.org*. Một payload JWT chỉ để minh họa:

~~~json
{
  "iss": "https://auth.example.org",
  "sub": "user-42",
  "aud": "billing-api",
  "scope": "invoices:read invoices:approve",
  "exp": 1900000000
}
~~~

Đây chỉ là **nội dung minh họa claims**, không phải JWT có thể sử dụng. Resource Server phải kiểm tra chữ ký, issuer, audience, hiệu lực và chính sách thu hồi phù hợp trước khi dùng claims làm đầu vào cho quyết định phân quyền. Chuỗi scope gồm các quyền cách nhau bởi dấu cách trong profile thường gặp; parsing và yêu cầu scope cần theo hợp đồng API thực tế.

Xét các yêu cầu sau:

| Tình huống | Token | Dữ liệu tại server | Quyết định |
|---|---|---|---|
| User-42 đọc hóa đơn của tenant T17 | Token hợp lệ, có *invoices:read* | Membership T17 đang hoạt động, role *ACCOUNTANT* | **Permit** |
| User-42 đọc hóa đơn của tenant T99 | Token hợp lệ, có *invoices:read* | Không có membership T99 | **Deny** |
| User-42 duyệt hóa đơn T17 | Có *invoices:approve* | Role *APPROVER*, nhưng user-42 là người tạo | **Deny** |
| User-42 đọc hóa đơn T17 sau khi bị xóa membership | Token còn hạn, có *invoices:read* | Membership đã bị thu hồi | **Deny** nếu policy kiểm tra trạng thái hiện hành |
| Token dành cho *reports-api* gọi *billing-api* | Có scope giống nhau | Audience không khớp | **Reject token** trước khi đánh giá quyền |
| Service A dùng client credentials | Token hợp lệ dành cho *billing-api* | Policy chỉ cho phép user có membership | **Deny** trừ khi có policy riêng cho machine principal |

Những trường hợp trên cho thấy chính sách phải xử lý **cả mức token và mức tài nguyên**. Thậm chí hai yêu cầu sử dụng cùng một token có thể nhận kết quả khác nhau vì đối tượng hoặc trạng thái đã thay đổi.

### 5.2. Pseudocode kiểm tra đọc hóa đơn

~~~text
handleGetInvoice(request):
    token = extractBearerToken(request)

    # Dùng thư viện/gateway cấu hình sẵn để xác minh đầy đủ
    principal = validateAccessToken(
        token,
        trustedIssuer = "https://auth.example.org",
        expectedAudience = "billing-api",
        allowedAlgorithms = configuredAlgorithms,
        requiredTokenType = "access_token"
    )
    if principal is invalid:
        return 401

    if principal.kind != "user":
        return 403
    if not principal.hasScope("invoices:read"):
        return 403

    routeTenant = request.path.tenantId
    invoiceId = request.path.invoiceId

    # Không trả về hóa đơn ở tenant khác dù ID đoán đúng
    invoice = repository.findByIdAndTenant(invoiceId, routeTenant)
    if invoice is missing:
        return 404

    membership = membershipStore.findActive(
        principal.userId, invoice.tenantId
    )
    if membership is missing:
        return 404  # Chính sách có thể che giấu sự tồn tại

    permitted = membership.role in ["ACCOUNTANT", "AUDITOR"]
                or invoice.createdBy == principal.userId
    if not permitted:
        return 403

    return 200, projectAllowedInvoiceFields(invoice, principal)
~~~

Pseudocode này cố ý tách **xác minh access token**, **nạp dữ liệu hiện hành** và **thực thi policy**. Trong ứng dụng thật, cần thư viện bảo mật uy tín xử lý JWT/introspection, chữ ký, các profile token và ngoại lệ; không tự viết bộ giải mã/chữ ký. Phép tra cứu dữ liệu phải an toàn trước truy vấn sai tenant và không làm lộ dữ liệu trong log/exception.

Điểm then chốt:

- User không thể đổi *tenantId* trên URL để đi sang tenant khác chỉ vì có scope.
- Client không được gửi *role=ADMIN* trong request rồi yêu cầu API tin role đó.
- Kết quả được lọc bằng *projectAllowedInvoiceFields* nếu các trường dữ liệu có quyền hiển thị khác nhau. Được xem hóa đơn **không nhất thiết** được xem mọi trường nhạy cảm của hóa đơn.
- Có thể trả **404** thay vì **403** nhằm che giấu sự tồn tại của tài nguyên. Cần áp dụng nhất quán và tránh biến phản hồi hoặc thời gian xử lý thành kênh rò rỉ thông tin.

### 5.3. Ghi dữ liệu đòi hỏi tránh khoảng hở kiểm tra–sử dụng

Với một hành động như duyệt hóa đơn, policy có thể yêu cầu trạng thái *PENDING*. Nếu kiểm tra quyền rồi chờ một luồng khác thay đổi dữ liệu trước khi cập nhật, quyết định ban đầu có thể đã lỗi thời. Đây là vấn đề **time-of-check to time-of-use (TOCTOU)**.

Một cách triển khai đáng cân nhắc là thực hiện kiểm tra điều kiện trạng thái và thay đổi dữ liệu trong **cùng transaction** và ràng buộc điều kiện ngay trong câu lệnh cập nhật:

~~~sql
UPDATE invoices
SET status = 'APPROVED'
WHERE id = :invoice_id
  AND tenant_id = :tenant_id
  AND status = 'PENDING'
  AND created_by <> :approver_id;
~~~

**Lưu ý:** câu lệnh trên **không tự thực hiện toàn bộ authorization**. Trước đó hệ thống vẫn phải xác minh token, scope và membership/role; trong transaction cần bảo đảm entitlement hiện hành theo mức nhất quán đã chọn. Ví dụ SQL chỉ cho thấy cách ràng buộc đồng thời các điều kiện bất biến, tenant và trạng thái để tránh cập nhật một tài nguyên không còn phù hợp. Nếu affected rows bằng 0, không nên báo duyệt thành công.

## 6. PEP, PDP và vị trí đặt kiểm soát quyền

- **PEP – Policy Enforcement Point:** vị trí chặn hoặc cho phép thao tác theo quyết định chính sách. Có thể nằm ở gateway, middleware, controller hoặc tầng service; phải ngăn được truy cập dữ liệu và side effect nếu quyết định là Deny.
- **PDP – Policy Decision Point:** nơi áp dụng rules lên subject, action, resource, context và đưa ra quyết định. Có thể là một hàm trong ứng dụng, thư viện policy hoặc dịch vụ policy tập trung.
- **Policy Information Point (PIP):** nguồn thuộc tính cho PDP, ví dụ dữ liệu membership/role, ownership và trạng thái tài nguyên.
- **Policy Administration Point (PAP):** nơi quản lý/vận hành phiên bản policy và quy trình thay đổi quyền; không nhất thiết là một dịch vụ riêng.

~~~mermaid
flowchart LR
    C["Client"] --> G["Gateway / coarse PEP"]
    G --> API["Billing API / resource PEP"]
    API --> PDP["Policy decision logic / PDP"]
    PDP --> PIP["Membership, invoice, context / PIP"]
    PDP -->|Permit or Deny| API
    API --> DB["Protected data / operation"]
~~~

**Gateway** có thể xác minh token, audience, scope ở mức endpoint và chặn yêu cầu sớm. Tuy vậy, gateway thường **không biết** invoice thuộc tenant nào hoặc ai tạo ra nó. Policy về sở hữu, quyền theo tenant, trạng thái đơn hàng hoặc dữ liệu theo từng bản ghi cần được thực thi tại nơi có **ngữ cảnh nghiệp vụ đáng tin**.

Nếu PDP được tách thành dịch vụ dùng chung, API vẫn là PEP và phải chịu trách nhiệm **thi hành** kết quả. Quyết định từ PDP phải gắn với đúng subject, action, resource, tenant và ngữ cảnh đầu vào; tránh tái dùng một kết quả Permit cho một hóa đơn hoặc subject khác. Khi PDP không thể trả kết quả hợp lệ, thao tác nhạy cảm nên **từ chối theo chính sách đã định** thay vì mặc định cho phép.

## 7. JWT, opaque token, cache và độ mới của quyền

Resource Server có thể xác thực các kiểu access token khác nhau:

| Cơ chế | Bước xác minh token | Ảnh hưởng đến policy evaluation |
|---|---|---|
| **JWT tự chứa, có chữ ký** | Kiểm chữ ký, issuer, audience, thời hạn, loại token, các điều kiện bảo mật | Claims sẵn có tại chỗ nhưng membership, ownership và quyền hiện hành vẫn có thể cần tra dữ liệu |
| **Opaque token** | Introspection hoặc tra trạng thái ở nguồn tin cậy | Có thể nhận trạng thái *active*, scope và claims được trả về; vẫn phải áp dụng policy trên tài nguyên |
| **JWT + kiểm tra thu hồi** | Xác minh token và kiểm thêm denylist/epoch/trạng thái theo chính sách | Giảm cửa sổ tồn tại quyền lỗi thời nhưng tăng phụ thuộc vào trạng thái và cache |

Với access token tự chứa, **không có lời hứa rằng role trong JWT phản ánh quyền hiện tại** đến từng giây. Nếu role hoặc membership được copy vào token khi cấp, Resource Server phải quyết định mức độ “cũ” có thể chấp nhận. Các chiến lược gồm:

1. **Tra quyền hiện hành ở Resource Server** cho thao tác nhạy cảm, ví dụ duyệt thanh toán, xem dữ liệu cá nhân hoặc quản lý quyền.
2. **Token sống ngắn** để hạn chế thời gian claims cũ còn hiệu lực; chỉ thích hợp khi chấp nhận được độ trễ thu hồi theo thời hạn token.
3. **Version/epoch quyền** hoặc trạng thái phiên được kiểm tra tại API khi cần khả năng thu hồi nhanh; đánh đổi chi phí tra cứu.
4. **Cache decision/entitlement** với key đầy đủ (subject, client khi cần, action, resource, tenant, phiên bản policy...), TTL ngắn và cơ chế invalidation. Cache làm giảm tải nhưng có thể giữ Permit cũ sau khi quyền bị thu hồi.

Không nên cache kết quả **Permit cho toàn bộ endpoint** chỉ dựa vào *sub* hoặc *scope* vì các tài nguyên cùng endpoint có thể có quyền khác nhau. Với cache, cần cân nhắc cả thay đổi ở **tài nguyên** (tenant, chủ sở hữu, trạng thái), **chủ thể** (bị khóa, role bị gỡ) và **policy** (quy tắc mới), không chỉ thời điểm hết hạn JWT.

**Introspection không loại bỏ policy evaluation.** Một opaque token *active=true* chứng minh token vẫn có hiệu lực theo Authorization Server, không tự cho phép đọc mọi tài nguyên. Ngược lại, cache introspection có thể tạo khoảng trễ thu hồi tương tự cache JWT claims, dù nguồn kiểm tra là tập trung.

## 8. Phản hồi HTTP và cách tránh rò rỉ thông tin

Với API dùng Bearer token, phân biệt lỗi theo **nguồn quyết định**:

| Trường hợp | Phản hồi thường gặp | Lý do |
|---|---|---|
| Thiếu token, sai chữ ký, hết hạn, sai issuer/audience hoặc token không chấp nhận được | **401 Unauthorized** | Chưa có thông tin xác thực hợp lệ cho tài nguyên |
| Token hợp lệ nhưng thiếu scope bắt buộc | **403 Forbidden** | Thiếu quyền đã cấp; có thể dùng Bearer challenge với *insufficient_scope* theo chuẩn liên quan |
| Token hợp lệ, đủ scope nhưng không đủ role/membership/quyền trên bản ghi | **403 Forbidden** | Policy nghiệp vụ từ chối |
| Tài nguyên không tồn tại hoặc policy cố ý che giấu tồn tại | **404 Not Found** | Tránh tiết lộ tài nguyên mà người gọi không được biết, khi áp dụng nhất quán |

Ví dụ phản hồi cho token không hợp lệ:

~~~http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer realm="billing-api", error="invalid_token"
~~~

Ví dụ từ chối do scope không đủ:

~~~http
HTTP/1.1 403 Forbidden
WWW-Authenticate: Bearer realm="billing-api", error="insufficient_scope"
~~~

Thông điệp gửi client không nên tiết lộ thông tin nhạy cảm về membership, tenant, tài nguyên bị che giấu hoặc các quy tắc nội bộ. Bên phía server nên ghi nhận đủ thông tin phục vụ audit, ví dụ **principal ID đã xác minh, client, action, resource ID phù hợp, policy version, kết quả và reason code**, nhưng không ghi nguyên access token, refresh token, mật khẩu hoặc khóa.

Lưu ý **401** không có nghĩa là người dùng cần “đăng nhập lại” trong mọi trường hợp; có thể token sai audience hoặc client dùng sai loại token. Và **403** không đồng nghĩa UI có thể quyết định cho phép nếu API đã từ chối.

## 9. Những lỗi thiết kế thường gặp

1. **Chỉ kiểm chữ ký JWT rồi cho phép mọi request.** Token hợp lệ mới qua bước xác thực token; còn audience, scope, quyền trên tài nguyên và trạng thái hiện hành.
2. **Lấy role/tenant từ request body hoặc query parameter làm nguồn sự thật.** Client có thể sửa dữ liệu này. Chỉ dùng làm bộ lọc/yêu cầu rồi đối chiếu dữ liệu đáng tin.
3. **Coi mọi bearer token có scope giống nhau là tương đương.** Phải xác minh issuer, audience, token type và ngữ cảnh ủy quyền; API không được nhận ID token hoặc token cấp cho API khác.
4. **Coi scope là toàn bộ phân quyền nghiệp vụ.** Scope *invoices:read* không xác nhận quyền với từng invoice, tenant hay trường dữ liệu.
5. **Chỉ đặt policy ở gateway.** Gateway không đủ dữ liệu để thực hiện object-level authorization; service cần chặn tại điểm truy cập tài nguyên.
6. **Trả về dữ liệu trước rồi mới kiểm quyền.** Điều này làm rò rỉ qua response, log, background job hoặc thông điệp sự kiện dù controller cuối cùng trả 403.
7. **Cache Permit quá lâu hoặc key cache không có resource/tenant.** Khi membership hay policy đổi, có thể tiếp tục cho truy cập trái phép.
8. **Fail open khi PDP, JWKS, introspection hoặc kho membership lỗi.** Không được bỏ qua kiểm tra quan trọng chỉ để request tiếp tục chạy; cần chính sách xử lý lỗi rõ và ưu tiên không lộ tài nguyên.
9. **Chỉ kiểm quyền lúc tạo yêu cầu bất đồng bộ.** Worker xử lý job sau đó phải nhận được ngữ cảnh ủy quyền đáng tin hoặc đánh giá lại quyền theo policy đã thiết kế; không dựa vào user ID tự khai trong payload.
10. **Bỏ qua giao dịch khi cập nhật tài nguyên.** Trạng thái/quan hệ có thể đổi giữa lúc kiểm tra và ghi; ràng buộc điều kiện cập nhật, transaction hoặc locking khi cần.

### Các tình huống kiểm thử tối thiểu

Hãy kiểm thử cả đường **Permit** và các đường **Deny** độc lập: không token, token hết hạn, issuer/audience sai, thiếu scope, quyền đã bị gỡ nhưng token chưa hết hạn, role đúng nhưng sai tenant, thuộc tenant nhưng sai owner, resource đã đổi trạng thái, service token dùng nhầm policy user, resource không tồn tại, PDP/entitlement store lỗi, cache chưa được invalidated sau thu hồi quyền.

Một test có ý nghĩa cần đi từ request đến dữ liệu/tác dụng cuối cùng và xác nhận **không có tác dụng phụ** khi policy từ chối, không chỉ kiểm tra một hàm trả về boolean.

## 10. Câu hỏi ôn tập và nguyên tắc ghi nhớ

**1. JWT có chữ ký đúng, chưa hết hạn và chứa scope đọc. Vì sao API vẫn trả 403?** Vì quyền có thể phụ thuộc vào membership, role, tenant, ownership hoặc trạng thái tài nguyên. Token validation và policy evaluation là hai bước độc lập.

**2. Resource Server có thể ủy quyền toàn bộ cho Authorization Server không?** Authorization Server quyết định token được cấp theo giao thức và chính sách cấp quyền; Resource Server vẫn chịu trách nhiệm thực thi quyết định truy cập tài nguyên cụ thể. Có thể dùng PDP tập trung, nhưng PEP tại điểm truy cập vẫn phải thi hành kết quả.

**3. Tại sao claim role trong JWT có thể không đủ?** Claim phản ánh thời điểm phát hành; role/membership có thể đã bị thay đổi. Nếu yêu cầu cập nhật tức thì, cần trạng thái hiện hành hoặc cơ chế thu hồi.

**4. Vì sao policy phải quan tâm tới audience?** Một access token được cấp cho API khác không được dùng để đi vòng qua ranh giới tin cậy của API hiện tại dù có scope trùng tên.

**5. Opaque access token với kết quả introspection active=true có tự động cho phép đọc hóa đơn không?** Không. API vẫn phải xác định action và kiểm quyền trên hóa đơn cụ thể.

**6. Khi nào 404 có thể thay 403?** Khi chính sách muốn che giấu sự tồn tại tài nguyên mà người gọi không được phép biết, miễn xử lý nhất quán và không tạo kênh rò rỉ thông tin khác.

**Ghi nhớ:** **Access token là đầu vào xác thực và giới hạn quyền, còn Resource Server là nơi thực thi quyền truy cập cuối cùng cho tài nguyên.** Một quyết định đáng tin phải kết hợp token đã xác minh, audience/scope, subject/client, action, tài nguyên, quyền hiện hành và ngữ cảnh; mặc định từ chối khi thiếu bằng chứng. Thiết kế policy đúng còn phải đặt kiểm soát ở đúng điểm, xử lý thu hồi/cache và kiểm chứng bằng các tình huống quyền bị từ chối.
