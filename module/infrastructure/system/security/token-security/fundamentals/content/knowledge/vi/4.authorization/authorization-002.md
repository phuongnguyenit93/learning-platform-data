# Role, permission, scope và claim

## Mục tiêu học tập

Sau bài học này, bạn có thể:

- Phân biệt **role**, **permission**, **scope** và **claim** trong các hệ thống xác thực, phân quyền và OAuth 2.0/OIDC.
- Giải thích ai quản lý từng khái niệm, khái niệm nào có thể xuất hiện trong token và Resource Server phải diễn giải chúng như thế nào.
- Kết hợp token hợp lệ, scope, quyền hiện hành và ngữ cảnh tài nguyên khi ra quyết định truy cập.
- Tránh các lỗi phổ biến như nhầm role với scope, dùng ID token để gọi API, bỏ qua audience hoặc cho phép truy cập chéo tenant.
- Nhận diện tác động của việc thay đổi role, permission và chính sách khi JWT đã phát hành vẫn chưa hết hạn.

## 1. Bốn khái niệm giải quyết bốn câu hỏi khác nhau

Một hệ thống có thể phát hành access token cho ứng dụng quản lý đơn hàng. Khi API nhận yêu cầu **đọc đơn hàng #123**, việc chỉ thấy chuỗi “manager” hoặc “orders:read” trong token chưa đủ để tự quyết định cho phép.

Hãy tách bốn câu hỏi:

1. **Role — Chủ thể giữ vai trò gì trong một phạm vi tổ chức hoặc nghiệp vụ?** Ví dụ: nhân viên hỗ trợ, quản lý đơn hàng, quản trị viên của tenant A.
2. **Permission — Chủ thể được phép thực hiện hành động nào trên loại tài nguyên hoặc tài nguyên cụ thể?** Ví dụ: xem đơn hàng, sửa trạng thái đơn hàng, hoàn tiền.
3. **Scope — Client được cấp phạm vi truy cập OAuth nào khi gọi API?** Ví dụ: “orders:read”, “orders:write”. Scope giới hạn quyền sử dụng access token; bản thân nó không thay thế chính sách nội bộ của API.
4. **Claim — Token hoặc phản hồi từ một thành phần đáng tin cậy đang khẳng định thuộc tính nào?** Ví dụ: issuer, subject, audience, thời gian hết hạn, scope đã cấp, hoặc một thuộc tính role theo hợp đồng riêng.

**Role và permission** mô tả mô hình phân quyền của hệ thống. **Scope** mô tả phạm vi quyền truy cập được ủy quyền/cấp cho client theo hợp đồng OAuth. **Claim** là một cặp tên–giá trị biểu diễn thông tin, có thể chứa scope hoặc role nhưng không mặc nhiên là quyết định cấp quyền.

Một cách hiểu hữu ích là: **role thường giúp quản lý permission; scope giới hạn những gì client có thể yêu cầu; claim chuyên chở thông tin; Resource Server quyết định quyền truy cập cuối cùng đối với tài nguyên.**

## 2. Role: vai trò nghiệp vụ, không phải quyền phổ quát

**Role (vai trò)** thường là một nhóm trách nhiệm được tổ chức định nghĩa để gán cho người dùng hoặc principal. Trong mô hình **Role-Based Access Control (RBAC)**, các permission được liên kết với role, sau đó role được gán cho chủ thể.

Ví dụ với hệ thống đơn hàng:

| Role | Permission có thể được gán | Ý nghĩa trong nghiệp vụ |
| --- | --- | --- |
| **order_viewer** | order:read | Xem các đơn hàng thuộc phạm vi được phân công. |
| **order_editor** | order:read, order:update | Xem và cập nhật đơn hàng được phép quản lý. |
| **order_manager** | order:read, order:update, order:approve | Duyệt thao tác trong bộ phận hoặc tenant được giao. |
| **security_auditor** | audit:read | Xem nhật ký theo phạm vi kiểm toán. |

Bảng trên là **chính sách minh họa**, không phải quyền mặc định của một chuẩn token. Ứng dụng có thể đặt tên role và permission theo cách khác.

Role thường cần thêm **ngữ cảnh gán**. Một người có role **order_manager** ở tenant A không tự động là quản lý đơn hàng ở tenant B. Tương tự, vai trò quản lý ở dự án X không đồng nghĩa được sửa dữ liệu của dự án Y.

Ví dụ:

~~~text
user-42
  ├─ tenant-blue  : order_manager
  └─ tenant-green : order_viewer
~~~

Nếu API chỉ nhìn thấy claim **roles: ["order_manager"]** mà không biết role được gán trong tenant nào, nó có nguy cơ cấp quyền rộng hơn dự kiến.

Cần phân biệt **role** với **group**: group thường dùng để tổ chức thành viên; role diễn tả trách nhiệm hoặc quyền nghiệp vụ. Một hệ thống có thể ánh xạ group sang role, nhưng không nên mặc nhiên coi tên group bất kỳ là quyền truy cập.

Role cũng **không tự nhiên là thuộc tính chuẩn của mọi OAuth access token**. Nếu issuer phát hành role trong JWT, tên claim, cấu trúc, ý nghĩa và phạm vi của role phải được định nghĩa rõ trong hợp đồng giữa issuer và Resource Server.

## 3. Permission: hành động được phép trên tài nguyên

**Permission (quyền)** biểu diễn điều chủ thể có thể làm trong chính sách ứng dụng. Một permission có thể đặt tên theo hành động và loại tài nguyên:

~~~text
order:read
order:update
order:approve
refund:create
audit:read
~~~

Trong hệ thống thực, **permission gắn với chính sách và ngữ cảnh**. “order:read” thường chưa giải quyết được việc có được đọc một đơn hàng cụ thể hay không. Ngoài permission chung, API có thể cần kiểm tra:

- Chủ thể có thuộc tenant sở hữu đơn hàng không?
- Đơn hàng có nằm trong bộ phận hoặc danh sách được phân công không?
- Đơn hàng đang ở trạng thái cho phép cập nhật hay không?
- Có quy tắc tách biệt nhiệm vụ, chẳng hạn người tạo không được tự duyệt không?
- Tài khoản hiện tại có bị khóa, tạm ngưng hoặc bị rút quyền không?

Chính sách có thể kết hợp **RBAC** (role), **ABAC** (thuộc tính của chủ thể, tài nguyên, ngữ cảnh), và **ReBAC** (quan hệ như sở hữu, được phân công, cùng nhóm). Đây là các cách tổ chức quyết định truy cập; không phụ thuộc token được biểu diễn dưới dạng JWT hay opaque token.

Một phép kiểm tra thường có dạng:

~~~text
allowed =
    account_is_active
    AND subject_has_permission("order:read", tenant="tenant-blue")
    AND subject_can_access(order_123)
    AND business_conditions_allow_read
~~~

Phải hiểu permission theo đúng phạm vi. Permission “order:read” dành cho tenant blue không được tự mở rộng sang tenant green, cho dù mã permission có cùng tên.

### Role và permission liên quan thế nào?

Một role có thể gán nhiều permission; một permission có thể xuất hiện ở nhiều role. Có thể quản lý thông qua một bảng ánh xạ:

~~~text
role_permissions:
  order_viewer  -> { order:read }
  order_editor  -> { order:read, order:update }
  order_manager -> { order:read, order:update, order:approve }
~~~

Tuy nhiên, **role không phải bản sao bất biến của permission**: quản trị viên có thể sửa ánh xạ role → permission, thu hồi role đã gán hoặc thêm điều kiện nghiệp vụ. Vì vậy hệ thống cần quy định cách đồng bộ/cache chính sách và thời điểm thay đổi có hiệu lực.

## 4. Scope: giới hạn quyền truy cập OAuth đã cấp cho client

Trong OAuth 2.0, **scope** là một hoặc nhiều chuỗi biểu thị phạm vi truy cập mà client yêu cầu và được Authorization Server chấp thuận. Theo RFC 6749, scope có thể được biểu diễn thành danh sách các chuỗi phân tách bằng dấu cách, còn giá trị và ý nghĩa của từng scope do hệ thống xác định.

Ví dụ:

~~~text
scope = "orders:read orders:write"
~~~

Đây là hai scope độc lập. Không được suy diễn rằng **orders:write** bao hàm **orders:read** nếu hợp đồng API không định nghĩa điều đó.

Một ví dụ luồng cấp quyền:

1. Ứng dụng quản lý đơn hàng đề nghị các scope **orders:read** và **orders:write**.
2. Authorization Server xét cấu hình client, chủ thể (nếu có), sự đồng ý/chính sách tổ chức và chỉ cấp những scope được phép.
3. Client nhận access token với scope được cấp, có thể ít hơn scope đề nghị.
4. Resource Server kiểm tra access token thuộc đúng issuer, audience và còn hiệu lực; sau đó kiểm tra scope cần cho endpoint.
5. Resource Server vẫn kiểm tra permission và chính sách trên đơn hàng cụ thể nếu nghiệp vụ yêu cầu.

**Scope là điều kiện giới hạn ở lớp OAuth**, không phải bằng chứng rằng người dùng được quyền làm mọi hành động trong phạm vi tên scope. Ví dụ, client có **orders:write** nhưng chủ thể chỉ có permission đọc đơn hàng thì thao tác sửa vẫn phải bị từ chối.

Ngược lại, chủ thể có role quản lý và permission duyệt đơn hàng nhưng client chỉ được cấp scope **orders:read** thì client này không được thực hiện thao tác duyệt qua access token đó.

Đừng đồng nhất tất cả scope với thao tác API. Trong OIDC, các giá trị như **openid** có ý nghĩa trong quy trình yêu cầu xác thực; **offline_access** liên quan yêu cầu khả năng truy cập ngoại tuyến theo điều kiện giao thức/chính sách. Chúng không mặc nhiên cho phép truy cập dữ liệu đơn hàng.

**Scope và permission có thể có tên giống nhau nhưng vẫn thuộc hai lớp khác nhau.** Việc đặt cùng tên chỉ thuận tiện nếu hệ thống có hợp đồng rõ ràng và không bỏ qua quyết định phân quyền hiện hành.

## 5. Claim: thông tin được khẳng định, phải kiểm tra nguồn và mục đích

**Claim** là một thông tin có tên và giá trị. Trong JWT, claims nằm trong payload; trong OAuth introspection, Authorization Server có thể trả về những trường cung cấp thông tin và trạng thái token. Ý nghĩa và mức độ tin cậy phụ thuộc loại token, issuer, audience và giao thức.

Access token dạng JWT có thể có payload minh họa:

~~~json
{
  "iss": "https://identity.example.test",
  "sub": "user-42",
  "aud": "orders-api",
  "client_id": "dashboard-app",
  "scope": "orders:read orders:write",
  "tenant_id": "tenant-blue",
  "roles": ["order_manager"],
  "iat": 1730000000,
  "exp": 1730000900,
  "jti": "example-token-id-1"
}
~~~

Đây là **payload minh họa**, không phải JWT đầy đủ. Đặc biệt, **tenant_id** và **roles** là ví dụ claim theo hợp đồng riêng; không phải mọi issuer đều dùng những tên này, và JSON mẫu không đồng nghĩa role đã được xác nhận trong tenant khác.

| Claim hoặc thông tin | Dùng để hiểu điều gì? | Lưu ý khi kiểm tra |
| --- | --- | --- |
| **iss** | Issuer phát hành token. | Chỉ tin issuer nằm trong cấu hình được chấp nhận. |
| **sub** | Chủ thể mà token đề cập. | Không đồng nhất trong mọi flow với một người dùng; client credentials có thể đại diện cho ứng dụng/dịch vụ. |
| **aud** | Đối tượng nhận token. | Resource Server phải xác minh token dành cho chính API mình. |
| **client_id** | Client liên quan đến token, khi profile/issuer cung cấp. | Không tự suy ra quyền người dùng từ quyền của client. |
| **scope** | Phạm vi truy cập OAuth đã cấp, theo hợp đồng của issuer. | Cần kiểm tra từng scope chính xác, không dùng tìm chuỗi con hoặc đoán quan hệ bao hàm. |
| **roles**, **permissions**, **tenant_id** | Thuộc tính hoặc thông tin quyền nghiệp vụ nếu issuer có quy ước cấp. | Claim riêng cần schema, nguồn dữ liệu, quy tắc cập nhật và phạm vi rõ ràng. |
| **exp**, **nbf**, **iat** | Thời điểm hết hạn, bắt đầu hiệu lực, phát hành. | Thời hạn còn hiệu lực không đảm bảo quyền chưa thay đổi. |
| **jti** | Định danh token nếu có. | Chỉ hỗ trợ đối chiếu/thu hồi/phát hiện lạm dụng khi có hệ thống theo dõi tương ứng. |

Một số nhà cung cấp dùng **scp** thay cho hoặc bên cạnh **scope**, hay mô hình claim riêng cho nhóm/vai trò. Định dạng **chuỗi cách nhau bởi khoảng trắng** và **mảng JSON** không được coi là tương đương nếu chưa có quy ước. API phải xử lý chính xác dạng được issuer cam kết, không tự diễn giải các tên trường gần giống nhau.

### Claim đúng về chữ ký vẫn có thể đã cũ

JWT có chữ ký hợp lệ chứng minh payload không bị sửa đổi trái phép sau khi ký bởi khóa được chấp nhận. Nó **không có cơ chế tự cập nhật** khi:

- Nhân viên bị chuyển phòng ban hoặc mất role;
- Permission của role bị sửa;
- Một tenant bị khóa hoặc gỡ quyền sử dụng sản phẩm;
- Chủ sở hữu đơn hàng thay đổi;
- Quyết định ủy quyền bị hủy hoặc phiên bị thu hồi.

Do đó, nếu tổ chức yêu cầu hiệu lực thu hồi nhanh, cần cơ chế **kiểm tra quyền hiện hành**, introspection/trạng thái phiên, danh sách thu hồi, token thời hạn ngắn hoặc sự kết hợp phù hợp. Mức độ chấp nhận độ trễ cần được quy định bằng chính sách, không ngầm hiểu rằng mọi JWT đều phản ánh quyền mới nhất.

## 6. Bảng so sánh nhanh

| Khái niệm | Câu hỏi trả lời | Ai thường định nghĩa/quản lý? | Thường được dùng ở đâu? | Ví dụ |
| --- | --- | --- | --- | --- |
| **Role** | Chủ thể giữ trách nhiệm gì? | Ứng dụng, IAM, quản trị tổ chức/tenant. | RBAC, chính sách nghiệp vụ. | order_manager của tenant-blue |
| **Permission** | Được làm hành động gì với tài nguyên nào? | Chủ sở hữu nghiệp vụ, policy engine, ứng dụng. | Ra quyết định phân quyền cuối cùng. | order:approve trên đơn hàng được giao |
| **Scope** | Client được cấp phạm vi OAuth nào? | Authorization Server cùng hợp đồng API. | Cấp access token, gateway và Resource Server. | orders:read |
| **Claim** | Token/ngữ cảnh đáng tin đang khẳng định thuộc tính gì? | Issuer hoặc nguồn cung cấp thông tin theo giao thức. | Xác minh token và đầu vào quyết định truy cập. | sub=user-42, aud=orders-api |

Không thể thay thế hoàn toàn một cột bằng cột khác. Một **permission** có thể được xác định từ nhiều **role** và điều kiện động; một **scope** có thể giới hạn client mà không đại diện chính xác cho role của người dùng; một **claim** có thể mô tả role nhưng cũng có thể chỉ mô tả issuer hoặc thời gian.

## 7. Luồng ra quyết định của API: từ token đến tài nguyên

Giả sử người dùng **user-42** thuộc hai tenant:

- Ở **tenant-blue**, người dùng có role **order_manager**.
- Ở **tenant-green**, người dùng chỉ có role **order_viewer**.

Ứng dụng dashboard nhận access token có audience **orders-api** và scope **orders:read orders:write**. Người dùng yêu cầu cập nhật đơn hàng #123 thuộc **tenant-green**.

~~~mermaid
sequenceDiagram
    participant U as Người dùng
    participant C as Dashboard client
    participant AS as Authorization Server
    participant API as Orders API
    participant POL as Policy / dữ liệu nghiệp vụ

    U->>C: Đăng nhập và dùng dashboard
    C->>AS: Yêu cầu access token với scope
    AS-->>C: Access token có scope được cấp
    C->>API: PUT /orders/123 + Bearer token
    API->>API: Kiểm loại token, issuer, audience, thời hạn, chữ ký/trạng thái
    API->>API: Kiểm scope orders:write
    API->>POL: Kiểm permission và tenant của đơn hàng #123
    POL-->>API: User chỉ có role order_viewer tại tenant-green
    API-->>C: 403 Forbidden
~~~

Ở đây, token có thể **hoàn toàn hợp lệ** và scope **orders:write** cũng có thể tồn tại. Tuy nhiên, **permission của user-42 trong tenant-green** không cho phép cập nhật đơn hàng. API phải từ chối.

Nếu đơn hàng #123 thuộc tenant-blue, kết quả còn tùy role có permission **order:update**, các điều kiện nghiệp vụ và quyền tại thời điểm yêu cầu. Role order_manager chỉ là một đầu vào; không nên chấp nhận mọi thao tác chỉ dựa vào chữ “manager”.

Có thể biểu diễn điều kiện cho phép như sau:

~~~text
ALLOW when all conditions hold:
  1. access token được xác minh và dành cho orders-api
  2. access token còn hiệu lực và chưa bị từ chối bởi cơ chế thu hồi áp dụng
  3. scope đã cấp đáp ứng scope endpoint yêu cầu
  4. principal hiện tại có permission tương ứng tại tenant của tài nguyên
  5. chính sách tài nguyên và điều kiện nghiệp vụ đều cho phép
Otherwise: DENY
~~~

Đây là một mô hình **kết hợp nhiều lớp điều kiện**. Một số hệ thống có thêm giới hạn theo địa điểm, thời gian, mức độ xác thực hoặc quan hệ giữa người dùng và tài nguyên. Chính sách cụ thể tùy sản phẩm, nhưng các điều kiện phải được triển khai ở nơi thực sự bảo vệ tài nguyên.

## 8. Pseudocode cho kiểm tra role, permission, scope và claim

Ví dụ dưới đây là **mã giả mô tả**, không phải triển khai thư viện JWT hoặc policy engine production:

~~~text
function updateOrder(request, orderId, update):
    token = extractAccessToken(request)
    principal = verifyAccessToken(
        token,
        trustedIssuer = "https://identity.example.test",
        requiredAudience = "orders-api",
        allowedAlgorithms = configuredAlgorithms
    )
    if principal.invalidOrExpired:
        return HTTP_401

    grantedScopes = parseScopesAccordingToIssuerContract(principal)
    if not grantedScopes.containsExactly("orders:write"):
        return HTTP_403

    order = orderRepository.find(orderId)
    if order is absent:
        return HTTP_404

    policyContext = {
        subject: principal.subject,
        client: principal.clientId,
        tenant: order.tenantId,
        action: "order:update",
        resource: order,
        currentTime: clock.now()
    }

    if not accountDirectory.isActive(principal.subject):
        return HTTP_403

    if not policyEngine.isAllowed(policyContext):
        return HTTP_403

    orderRepository.updateIfBusinessRulesAllow(order, update)
    return HTTP_200
~~~

Các điểm thiết kế quan trọng:

- **verifyAccessToken** phải kiểm tra signature/issuer/audience/time theo đúng profile, hoặc tra cứu trạng thái opaque token qua kênh tin cậy. Không tự nhận token bất kỳ có payload JSON là access token hợp lệ.
- **parseScopesAccordingToIssuerContract** chỉ đọc scope đã cấp và kiểm tra **phần tử chính xác**. Ví dụ, “orders:readall” không được khớp nhầm với “orders:read”.
- **order.tenantId** lấy từ dữ liệu server đáng tin, không chỉ dựa vào tenantId do client tự đưa trong URL/header rồi coi là sự thật.
- **policyEngine.isAllowed** quyết định theo vai trò/permission **trong đúng tenant** và điều kiện nghiệp vụ đang có hiệu lực. Nếu dùng role/permission từ claim, phải biết chúng được issuer chứng thực, có đúng scope tổ chức và còn mới theo chính sách không.
- Nếu dùng cache quyền, cần định nghĩa **TTL và vô hiệu hóa cache** để đáp ứng yêu cầu thu hồi. API không được tự cho phép mọi yêu cầu khi policy store không khả dụng nếu chưa có chính sách xử lý lỗi được thiết kế rõ.
- Đoạn mã giả không nêu chi tiết concurrency, phân quyền từng field, chống race condition hay audit log; triển khai thực tế cần xử lý các yêu cầu đó theo nghiệp vụ.

### Vì sao không chỉ kiểm tra role trong controller?

Một kiểm tra đơn giản kiểu:

~~~text
if token.roles contains "admin":
    allow()
~~~

dễ bỏ sót vấn đề role thuộc tenant nào, còn hiệu lực không, người dùng được phép thao tác lên đối tượng nào, và client có scope phù hợp không. Điều kiện **admin** cũng phải được định nghĩa rõ: quản trị viên nội bộ toàn hệ thống khác với **tenant_admin** chỉ quản lý một tenant.

Trong ứng dụng nhiều tenant, một vai trò có thể cần được biểu diễn như **(subject, tenant, role)** hoặc trong policy store có cùng độ chính xác, thay vì chuỗi role toàn cục.

## 9. OAuth 2.0/OIDC và ranh giới tin cậy

Trong hệ thống OAuth 2.0/OIDC, cần phân biệt các thành phần:

- **Authorization Server** xác thực hoặc đánh giá ủy quyền theo luồng thích hợp, phát hành token và quyết định scope được cấp.
- **Client** nhận và sử dụng access token để gọi API; scope được cấp phụ thuộc chính sách chứ không đơn thuần là bất kỳ scope client yêu cầu.
- **Resource Server** xác minh access token dành cho mình rồi áp dụng scope và chính sách phân quyền lên tài nguyên.
- **Identity Provider / OpenID Provider** trong OIDC có thể cung cấp **ID token** về sự kiện xác thực cho client. ID token phục vụ đúng audience và mục đích của client; API **không dùng ID token thay access token**.

Với access token dạng JWT, Resource Server cần kiểm tra loại token/profile được hỗ trợ, issuer, audience, thời gian, chữ ký và thuật toán/key đáng tin. Với opaque token, Resource Server có thể dùng introspection (RFC 7662) để nhận trạng thái và thuộc tính token. Trong cả hai trường hợp, thông tin role/permission lấy từ token chỉ nên được chấp nhận theo **hợp đồng claim** rõ ràng.

### Một scope có ý nghĩa khác nhau theo client hoặc API?

Tên scope thường được định nghĩa theo hợp đồng Authorization Server–Resource Server. Nếu một tổ chức có nhiều API, việc dùng tên quá chung như **read** dễ gây nhầm lẫn. Cần đặt tên và kiểm tra audience đủ rõ để không vô tình dùng token của một API cho API khác.

Ví dụ, token có **aud=inventory-api** và **scope=orders:read** vẫn phải bị Orders API từ chối vì **audience không phù hợp**, bất kể chuỗi scope trông có vẻ đúng.

### Client credentials không phải đăng nhập người dùng

Trong luồng **client credentials**, access token thường đại diện cho quyền của ứng dụng/dịch vụ theo chính sách Authorization Server. Không nên giả định mọi **sub** trong access token đều là người dùng con người, hoặc mượn role của người dùng đang thao tác mà không có cơ chế ủy quyền rõ ràng.

Ví dụ, dịch vụ đồng bộ dữ liệu cần scope **orders:export** và permission dịch vụ ở một tenant cụ thể. Nếu có hành động nhân danh người dùng, chính sách phải phân biệt **người dùng**, **client** và **ngữ cảnh được ủy quyền**; không tự suy ra quyền rộng nhất từ bất kỳ claim nào.

## 10. Những tình huống dễ nhầm và cách đánh giá

| Tình huống | Điều dễ làm sai | Hành vi đúng |
| --- | --- | --- |
| User có role quản lý; client chỉ được cấp scope đọc. | Cho phép cập nhật vì role quản lý. | Từ chối cập nhật do thiếu scope **orders:write**. |
| Client có scope ghi; user chỉ có permission đọc. | Cho phép cập nhật vì token có scope ghi. | Từ chối do policy không cấp permission cập nhật. |
| User quản lý tenant A; đơn hàng thuộc tenant B. | Áp role manager toàn hệ thống. | Kiểm tra gán role/permission tại tenant B và quan hệ với đơn hàng. |
| JWT chứa role cũ sau khi quản trị viên rút quyền. | Chấp nhận role trong JWT đến exp mà không xét yêu cầu hiệu lực thu hồi. | Áp dụng kiểm tra trạng thái/chính sách, danh sách thu hồi hoặc độ trễ phù hợp với rủi ro. |
| ID token chứa role hoặc group. | Gửi ID token làm Bearer token cho Orders API. | API chỉ chấp nhận access token đúng loại/audience. |
| Token cấp cho Inventory API có scope cùng tên. | Chỉ so scope, bỏ qua audience. | Từ chối token sai audience. |
| Scope là chuỗi chứa “orders:readall”. | Dùng thao tác tìm chuỗi con “orders:read”. | Parse scope theo hợp đồng và so khớp từng giá trị chính xác. |
| Frontend ẩn nút “Approve”. | Cho rằng backend không cần kiểm tra quyền duyệt. | Backend kiểm tra permission và chính sách tại mỗi thao tác quan trọng. |

Một thiết kế chuẩn cần áp dụng **deny by default**: nếu không có dữ liệu hoặc chứng cứ đủ đáng tin để cấp quyền, API từ chối và ghi nhật ký phù hợp. Tránh log nguyên văn token vì token bearer có thể bị sử dụng lại nếu rò rỉ.

## 11. Thay đổi role, permission, scope và claim trong vòng đời token

Bốn khái niệm có tốc độ thay đổi khác nhau:

- **Role assignment** có thể đổi khi nhân viên chuyển nhóm hoặc rời tenant.
- **Permission mapping** có thể đổi khi quy định nội bộ được cập nhật.
- **Scope được cấp** gắn với token hoặc trạng thái ủy quyền, có thể thay đổi ở lần cấp mới hoặc bị giới hạn/thu hồi theo chính sách Authorization Server.
- **Claim trong JWT đã ký** thường không tự đổi cho đến khi phát hành token khác; claim từ introspection có thể phản ánh trạng thái gần hiện tại hơn nhưng vẫn bị ảnh hưởng bởi cache và khả năng đồng bộ.

Khi thiết kế chính sách, đừng chỉ hỏi “token hết hạn sau bao lâu?” mà còn hỏi:

1. Nếu rút role người dùng **ngay bây giờ**, yêu cầu mới phải bị từ chối chậm nhất sau bao lâu?
2. Nếu client mất quyền được cấp một scope, token cũ còn được dùng đến khi nào?
3. Nếu tenant bị khóa, Resource Server có tra cứu trạng thái tenant hiện hành không?
4. Nếu token bị đánh cắp hoặc phát lại, hệ thống có thể thu hồi/giới hạn cửa sổ lạm dụng bằng cách nào?

**Access token ngắn hạn** hạn chế cửa sổ rủi ro nhưng không bảo đảm thu hồi ngay. **Introspection**, **danh sách thu hồi**, **policy lookup** và **đồng bộ sự kiện quyền** đều có đánh đổi về hiệu năng, độ sẵn sàng và tính nhất quán. **Refresh token** chỉ để xin token mới trong điều kiện được phép; nó không phải quyền truy cập nghiệp vụ không giới hạn. Tùy nguy cơ đánh cắp token, hệ thống có thể áp dụng refresh token rotation, token ràng buộc bên gửi (DPoP/mTLS), bảo vệ nơi lưu trữ và theo dõi bất thường.

Điểm mấu chốt là giữ cho **thông tin cấp quyền tại Authorization Server** và **quyết định truy cập tại Resource Server** có hợp đồng nhất quán, với giới hạn độ trễ được chấp nhận rõ ràng.

## 12. Bài tập suy luận

Xét ba yêu cầu sau đối với Orders API. Giả sử tất cả access token đều có chữ ký hợp lệ, đúng issuer, đúng audience và chưa hết hạn:

**Tình huống A.** Client có scope **orders:read**; nhân viên có permission **order:read** ở tenant A; đơn hàng nằm tại tenant B.

**Tình huống B.** Client có scope **orders:write**; nhân viên là **order_viewer** và hiện chỉ có permission **order:read** ở đúng tenant của đơn hàng; yêu cầu là cập nhật trạng thái.

**Tình huống C.** Client có scope **orders:read**; nhân viên có permission **order:read** với đơn hàng; yêu cầu là xem chi tiết chính đơn hàng đó.

**Phân tích:** A phải bị từ chối nếu chính sách tenant không cho phép truy cập chéo. B phải bị từ chối vì thiếu permission cập nhật dù scope ghi đã được cấp. C có thể được cho phép **nếu** các điều kiện khác như tài khoản hoạt động, trạng thái tài nguyên và chính sách hiện hành đều thỏa mãn. Không tình huống nào chỉ dựa vào chữ ký token hoặc role để ra quyết định đầy đủ.

## 13. Checklist áp dụng vào hệ thống thực tế

Khi triển khai authorization cho API, hãy xác nhận:

- **Định nghĩa:** Có tài liệu hóa role, permission, scope, claim và quan hệ giữa chúng; các chuỗi riêng có định nghĩa đúng phạm vi tenant/tổ chức.
- **Nguồn tin cậy:** Resource Server xác minh issuer, audience, chữ ký hoặc introspection, thời hạn và loại access token đúng mục đích.
- **Scope:** Mỗi endpoint có điều kiện scope rõ ràng; parser xử lý chính xác định dạng claim do issuer cung cấp.
- **Permission:** API kiểm tra hành động lên tài nguyên thuộc tenant nào, do ai sở hữu và có điều kiện nghiệp vụ gì.
- **Quyền hiện hành:** Có cơ chế phản ánh thay đổi role/permission/thu hồi trong giới hạn thời gian đã định.
- **Quy trình kiểm thử:** Có kiểm thử thiếu scope, thiếu permission, role sai tenant, thay đổi quyền giữa phiên, audience sai, token hết hạn, ID token bị dùng sai mục đích và truy cập trực tiếp bằng ID của tài nguyên khác.
- **Vận hành:** Có audit log quyết định truy cập theo cách không lộ token; lỗi truy cập được trả theo chính sách HTTP thích hợp, thường **401** với token thiếu/không hợp lệ và **403** với yêu cầu đã xác thực nhưng không đủ quyền.

## Kết luận

**Role** mô tả vai trò của chủ thể trong tổ chức, **permission** diễn tả hành động được cho phép đối với tài nguyên, **scope** giới hạn quyền OAuth được cấp cho client, còn **claim** là thông tin được một nguồn tin cậy khẳng định và mang theo trong token hoặc phản hồi giao thức.

Chúng có quan hệ nhưng không thể đánh đồng. Một access token hợp lệ có scope phù hợp vẫn có thể không đủ quyền đọc hay sửa một tài nguyên cụ thể. Quyết định authorization an toàn kết hợp **kiểm tra token**, **giới hạn scope**, **permission theo role/ngữ cảnh hiện hành**, **chính sách của tài nguyên** và **vòng đời thu hồi quyền**.

### Tài liệu tham khảo

- [RFC 6749 — The OAuth 2.0 Authorization Framework, Section 3.3 Scope](https://www.rfc-editor.org/rfc/rfc6749#section-3.3)
- [RFC 6750 — OAuth 2.0 Bearer Token Usage](https://www.rfc-editor.org/rfc/rfc6750)
- [RFC 7662 — OAuth 2.0 Token Introspection](https://www.rfc-editor.org/rfc/rfc7662)
- [RFC 9068 — JSON Web Token (JWT) Profile for OAuth 2.0 Access Tokens](https://www.rfc-editor.org/rfc/rfc9068)
- [RFC 8725 — JSON Web Token Best Current Practices](https://www.rfc-editor.org/rfc/rfc8725)
- [OpenID Connect Core 1.0](https://openid.net/specs/openid-connect-core-1_0.html)
