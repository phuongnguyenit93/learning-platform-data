# Subject và định danh principal

## Mục tiêu học tập

Sau bài học này, bạn có thể:

- Giải thích **subject (sub)** là gì, vì sao một định danh trong token không tự chứng minh quyền truy cập và không nhất thiết đại diện cho người dùng.
- Phân biệt **subject**, **principal**, **user/account**, **client**, **actor** và **tenant** trong hệ thống OAuth 2.0/OpenID Connect (OIDC).
- Nhận diện sự cần thiết của khóa định danh **(issuer, subject)** và cách ánh xạ an toàn sang principal nội bộ.
- Hiểu sự khác nhau giữa subject trong ID token OIDC, access token của người dùng và access token của dịch vụ.
- Thiết kế các bước kiểm tra token, xác định principal, kiểm tra quyền hiện hành và phòng tránh nhầm danh tính giữa issuer/tenant.

## 1. Vì sao một chuỗi sub chưa trả lời đầy đủ câu hỏi “ai?”

Một ứng dụng nhận token có payload minh họa:

~~~json
{
  "iss": "https://identity.example.test",
  "sub": "account-42",
  "aud": "orders-api",
  "scope": "orders:read",
  "exp": 1730000900
}
~~~

Đây chỉ là **payload JSON giả lập**, chưa phải JWT hoàn chỉnh và không chứa định danh người dùng thật.

Khi Resource Server thấy **sub = account-42**, nó cần trả lời nhiều câu hỏi hơn là chỉ đọc một chuỗi:

1. Token do **issuer (iss)** nào phát hành, có đáng tin và dành cho API hiện tại không?
2. **sub** trong loại token này chỉ một người dùng, ứng dụng hay một thực thể khác?
3. Subject được ánh xạ thành **principal nội bộ** nào và account đó có còn hoạt động không?
4. Yêu cầu đang nhắm đến tài nguyên của **tenant** nào?
5. Principal đó có quyền thực hiện hành động cụ thể **tại thời điểm này** không?

Nếu bỏ qua các câu hỏi đó, một token có chữ ký hợp lệ vẫn có thể bị dùng sai mục đích hoặc bị ánh xạ tới sai tài khoản.

> **Nguyên tắc:** Subject là thông tin định danh được bên phát hành khẳng định trong một phạm vi nhất định. Principal là thực thể mà ứng dụng đã nhận diện và dùng trong ngữ cảnh xử lý. Cả hai đều chưa thay thế quyết định phân quyền.

## 2. Phân biệt subject, principal và những thực thể liên quan

| Khái niệm | Ý nghĩa | Ví dụ | Sai lầm cần tránh |
| --- | --- | --- | --- |
| **Subject** | Chủ thể mà token hoặc một assertion đang nói đến theo ngữ nghĩa của issuer. | subject: user-42 | Coi chuỗi này là duy nhất trên toàn Internet. |
| **Issuer** | Thành phần phát hành và chịu trách nhiệm về claims. | https://idp-a.example.test | Bỏ qua issuer khi tra cứu user. |
| **Principal** | Thực thể được hệ thống nhận diện trong ngữ cảnh xác thực. | UserPrincipal(id=781) | Cấp quyền chỉ vì biết username hay subject. |
| **Account** | Bản ghi tài khoản mà ứng dụng/IAM quản lý. | internal user 781 | Đồng nhất account nội bộ với external subject không qua mapping. |
| **Client** | Ứng dụng yêu cầu và sử dụng quyền truy cập. | dashboard-client | Coi client và người dùng là một. |
| **Actor** | Thành phần thực hiện hành động, có thể khác chủ thể mà hành động được ủy quyền thay mặt. | orders-worker acting for user | Không ghi nhận chuỗi ủy quyền trong audit. |
| **Tenant** | Phạm vi tổ chức/dữ liệu nơi chính sách áp dụng. | tenant-blue | Dùng role ở tenant A để thao tác tenant B. |

Trong một framework, đối tượng tên **Principal** có thể chứa internal user ID, loại principal, các thuộc tính từ phiên/identity và ngữ cảnh xác thực. Nó không nhất thiết có cấu trúc giống JWT và không nhất thiết là một người tự nhiên.

**Xác thực (authentication)** giúp nhận diện thực thể và xác minh bằng chứng. **Phân quyền (authorization)** quyết định thực thể đó được làm gì đối với tài nguyên nào. Một subject đã được xác minh vẫn cần qua bước phân quyền.

## 3. sub trong JWT: phạm vi duy nhất và cách so sánh

Theo RFC 7519, claim **sub** xác định subject mà JWT đề cập. Giá trị **sub** là một chuỗi, với yêu cầu duy nhất theo phạm vi của issuer hoặc một phạm vi toàn cục được thiết kế rõ. Không thể suy ra một subject ngắn như **42** chỉ tồn tại cho một người trên mọi nhà cung cấp danh tính.

Hai issuer có thể phát hành:

~~~text
Issuer A:
    iss = https://idp-a.example.test
    sub = 42

Issuer B:
    iss = https://idp-b.example.test
    sub = 42
~~~

Hai subject này **không mặc nhiên cùng một người**.

Vì vậy, với hệ thống tin cậy nhiều issuer, một khóa ánh xạ thường được xây dựng từ:

~~~text
externalIdentityKey = (verifiedIssuer, verifiedSubject)

(idp-a.example.test, 42)  -> internalPrincipalId = 781
(idp-b.example.test, 42)  -> internalPrincipalId = 994
~~~

**(iss, sub)** là cơ sở định danh phù hợp, nhưng chỉ được sử dụng sau khi token được xác minh theo đúng loại/profile. API còn phải kiểm tra audience, thời hạn và bối cảnh cần thiết; không được coi cặp này là giấy phép truy cập.

### Subject là giá trị opaque đối với ứng dụng nhận token

Trong phần lớn tích hợp, ứng dụng không cần biết issuer tạo subject bằng thuật toán nào. Tránh:

- Chuyển chuỗi **0042** thành số **42**, làm mất các ký tự có ý nghĩa.
- Tự chuyển toàn bộ subject sang chữ thường hoặc cắt khoảng trắng khi hợp đồng không cho phép.
- Tách subject theo dấu gạch ngang để suy đoán mã phòng ban, tenant hoặc vai trò.
- Giả định subject có dạng email luôn là email hiện tại hoặc đã được xác minh.
- Coi cấu trúc có vẻ giống UUID là dấu hiệu một token đáng tin.
- Dùng chuỗi subject client tự truyền trong query/header thay cho subject của token đã được xác minh.

Khi so khớp định danh, cần tuân thủ kiểu dữ liệu và quy tắc so sánh của issuer/profile. Hai giá trị nhìn gần giống nhau chưa chắc cùng một subject.

## 4. Trong OIDC, sub là định danh End-User được cấp cho client

Trong OpenID Connect, **ID token** được OpenID Provider phát hành cho **relying party/client** để cung cấp thông tin về sự kiện xác thực và End-User.

Ví dụ:

~~~json
{
  "iss": "https://login.example.test",
  "sub": "opaque-user-p9D2",
  "aud": "dashboard-client",
  "iat": 1730000000,
  "exp": 1730000900,
  "auth_time": 1729999950
}
~~~

Đây là payload ID token minh họa, không phải token hoàn chỉnh.

**iss** xác định OpenID Provider, **sub** xác định End-User theo issuer, **aud** là client nhận ID token, **iat** là thời điểm phát hành. Claim **auth_time**, nếu có, chỉ thời điểm xác thực người dùng; không đồng nghĩa với thời điểm token được phát hành.

Vì audience của ID token thường là **client**, Resource Server không được chấp nhận ID token thay access token chỉ vì cả hai cùng chứa **sub**, **iss** hoặc email. API phải yêu cầu access token đúng loại, đúng issuer và đúng audience.

### Public và pairwise subject identifier

OIDC phân biệt hai cách phát hành subject identifier:

| Kiểu | Đặc điểm | Hệ quả thiết kế |
| --- | --- | --- |
| **Public subject identifier** | Cùng End-User có thể nhận cùng subject từ một issuer tại nhiều client. | Các client có thể liên kết dữ liệu theo subject khi chia sẻ thông tin. |
| **Pairwise subject identifier** | Identifier được tính theo **sector identifier** của relying party. | Các sector khác nhau thường thấy subject khác nhau dù là cùng End-User. |

Ví dụ một người dùng trong hệ thống cấp pairwise identifier:

~~~text
Issuer: https://login.example.test

Sector A: app-a.example.test  -> sub = pairwise-7xA
Sector B: app-b.example.test  -> sub = pairwise-9Qk
~~~

Việc hai giá trị sub khác nhau **không chứng minh hai người dùng khác nhau**. Cũng không được ghép chúng thành một chỉ bằng cách đoán cấu trúc chuỗi. OIDC định nghĩa sự ổn định và không tái gán subject trong phạm vi issuer; quy tắc pairwise phục vụ hạn chế liên kết danh tính giữa các sector.

### UserInfo phải khớp sub với ID token

OIDC cho phép lấy thêm claims từ **UserInfo endpoint**. Client phải đối chiếu **sub** trả về từ UserInfo với **sub** của ID token đã được xác minh. Nếu không khớp, thông tin UserInfo không được dùng cho phiên đó. Việc so khớp này ngăn trộn dữ liệu của hai người dùng hoặc hai phiên khác nhau.

**Email, name và picture** từ UserInfo là dữ liệu hồ sơ, không thay thế subject đã được xác minh.

## 5. sub trong access token: người dùng hay dịch vụ?

OAuth 2.0 giải quyết việc ủy quyền cho client gọi tài nguyên. Access token có thể được cấp trong nhiều luồng; vì thế Resource Server không nên có giả định rằng **mọi sub đều là người đăng nhập bằng trình duyệt**.

### Trường hợp A: truy cập thay mặt người dùng

Một dashboard được ủy quyền đọc đơn hàng của người dùng:

~~~json
{
  "iss": "https://auth.example.test",
  "sub": "person-42",
  "client_id": "dashboard-client",
  "aud": "orders-api",
  "scope": "orders:read",
  "exp": 1730000900
}
~~~

Theo hợp đồng của JWT access token được minh họa, **sub** xác định người dùng/resource owner và **client_id** xác định ứng dụng được cấp quyền. Hai thực thể này khác nhau.

Ngay cả khi người dùng có permission cập nhật đơn hàng, một client chỉ nhận scope **orders:read** cũng không được thực hiện thao tác ghi qua token đó.

### Trường hợp B: client credentials, không có người dùng cuối

Một worker tự động đồng bộ dữ liệu nhận access token theo quyền của chính ứng dụng:

~~~json
{
  "iss": "https://auth.example.test",
  "sub": "nightly-sync-service",
  "client_id": "nightly-sync-service",
  "aud": "inventory-api",
  "scope": "inventory:sync",
  "exp": 1730000900
}
~~~

Đây là ví dụ theo **profile access token cụ thể**. Trong RFC 9068 (JWT Profile for OAuth 2.0 Access Tokens), subject của access token cấp theo client credentials có thể tương ứng với định danh client theo yêu cầu profile. Các hệ thống/profiles khác có thể có quy tắc riêng; phải dựa vào hợp đồng issuer để hiểu **sub**.

Lỗi nguy hiểm là triển khai chung:

~~~text
user = loadUserById(token.sub)
authorizeUsingUserRoles(user)
~~~

Nếu token thực tế đại diện một workload, API có thể ánh xạ nhầm sang user có ID trùng tên. Cần nhận diện loại principal và cách cấp token trước khi quyết định quyền.

### Trường hợp C: ứng dụng hoặc dịch vụ hành động thay mặt chủ thể

Trong kiến trúc nhiều service, có thể tồn tại đồng thời:

~~~text
End-User        = nhân viên A
OAuth Client    = dashboard-client
Calling Service = orders-worker
Target API      = billing-api
Action          = tạo yêu cầu hoàn tiền
~~~

Người dùng, client và service là **những thực thể khác nhau**. Nếu hệ thống hỗ trợ token exchange/delegation, hợp đồng token có thể mô tả quan hệ subject–actor. Không được tự đoán chuỗi ủy quyền dựa vào sub hoặc do client nói “tôi hành động thay A”. Chỉ tin các thuộc tính được xác minh theo profile ủy quyền tương ứng.

## 6. Subject không thay thế role, permission, scope và audience

Giả sử access token đã xác minh chứa:

~~~json
{
  "iss": "https://auth.example.test",
  "sub": "person-42",
  "aud": "orders-api",
  "scope": "orders:read",
  "tenant_id": "tenant-blue",
  "roles": ["order_manager"],
  "exp": 1730000900
}
~~~

**tenant_id** và **roles** ở ví dụ này là các claim riêng theo hợp đồng issuer, không phải các claim chuẩn bắt buộc của mọi access token.

| Thông tin | Có thể dùng để làm gì? | Không tự chứng minh |
| --- | --- | --- |
| **sub** | Xác định chủ thể trong phạm vi issuer. | Được phép truy cập mọi bản ghi của chủ thể hoặc tenant. |
| **iss** | Kiểm tra nguồn phát hành. | Token dành cho chính API hiện tại. |
| **aud** | Kiểm tra API/đối tượng nhận. | Principal có permission nghiệp vụ. |
| **scope** | Kiểm tra phạm vi OAuth được cấp. | Chủ thể có quyền trên từng tài nguyên cụ thể. |
| **roles** | Đầu vào chính sách nếu hợp đồng có hỗ trợ. | Role còn hiệu lực và áp dụng cho mọi tenant. |
| **tenant_id** | Bổ sung ngữ cảnh tenant khi được xác minh đúng. | Tài nguyên được client yêu cầu thực sự thuộc tenant đó. |

Một quyết định truy cập phù hợp có thể là:

~~~text
ALLOW only if:
    token_is_valid_for_orders_api
    AND scope_contains_exactly("orders:read")
    AND subject_resolves_to_active_principal
    AND current_permission_allows("order:read", order.tenant)
    AND principal_can_access(order)
    AND business_policy_allows_read(order)
~~~

**Cả token hợp lệ lẫn subject ổn định đều không tự động cấp quyền.** Hệ thống phải kiểm tra quyền nghiệp vụ theo thời điểm và tài nguyên phù hợp.

## 7. Từ claim đến principal đã xác minh: các bước kiểm tra

Quy trình thực hiện cần phân biệt **dữ liệu từ request** với **ngữ cảnh đáng tin đã được server xác minh**.

~~~mermaid
sequenceDiagram
    participant C as Client
    participant API as Orders API
    participant AS as Issuer/Introspection
    participant DIR as Principal directory
    participant POL as Policy store

    C->>API: Request + access token
    API->>AS: Xác minh token theo profile (hoặc dùng khóa tin cậy cục bộ)
    AS-->>API: Claims và trạng thái được xác minh
    API->>API: Kiểm iss, aud, loại token, exp/nbf, scope
    API->>DIR: Resolve (verified iss, verified sub, principal type)
    DIR-->>API: Internal principal và trạng thái
    API->>POL: Kiểm quyền với tenant/tài nguyên
    POL-->>API: ALLOW hoặc DENY
    API-->>C: Phản hồi
~~~

Với JWT ký số, Resource Server có thể xác minh **cục bộ** bằng khóa và issuer tin cậy, không bắt buộc gửi RPC tới AS mỗi lần. Với opaque token, có thể cần introspection (RFC 7662). Sơ đồ mô tả trách nhiệm, không bắt buộc một triển khai cụ thể.

Các lớp:

1. **Token validation:** xác nhận chữ ký JWT hoặc introspection, issuer đáng tin, audience chính xác, loại token/profile, thuật toán/khóa và hiệu lực thời gian.
2. **Claim interpretation:** hiểu sub, client_id, scope và các claim đặc thù theo đúng loại token và luồng cấp.
3. **Principal resolution:** ánh xạ subject đã xác minh vào account/workload nội bộ, với principal type và trạng thái.
4. **Authorization:** kiểm tra scope, permission, tenant, quan hệ tài nguyên và điều kiện hiện hành.
5. **Audit:** ghi định danh/trạng thái cần thiết một cách có kiểm soát, không ghi nguyên văn bearer token.

Đặc biệt, **JWT payload chưa kiểm chữ ký chỉ là dữ liệu không đáng tin**; không thể dùng sub từ payload đó để tìm user và cấp quyền trước khi token hợp lệ.

## 8. Thiết kế mapping subject sang principal nội bộ

Khi tích hợp nhiều issuer, nên lưu định danh bên ngoài tách biệt với ID nghiệp vụ nội bộ:

~~~text
InternalPrincipal
    id: 781
    type: HUMAN_USER
    status: ACTIVE

ExternalIdentity
    issuer: https://idp-a.example.test
    subject: 42
    internal_principal_id: 781
    link_status: VERIFIED

TenantMembership
    internal_principal_id: 781
    tenant_id: tenant-blue
    role: order_manager
    status: ACTIVE
~~~

Các nguyên tắc:

- **ExternalIdentity** chỉ được tạo/liên kết qua quy trình xác minh issuer và subject.
- Một **internal principal ID ổn định** giúp ứng dụng không phụ thuộc username hoặc email có thể thay đổi.
- **Principal type** giúp tránh đối xử service token như tài khoản người dùng.
- **Membership theo tenant** nằm ở quan hệ/phân quyền rõ ràng thay vì suy luận từ chuỗi subject.
- Khi account bị khóa hoặc xóa, mapping phải được quản lý để chủ thể khác không kế thừa quyền/tài nguyên cũ.
- Nếu một principal được liên kết với nhiều external identities, từng liên kết phải được xác minh và lưu lịch sử cần thiết.

### Có nên dùng email làm khóa định danh?

Thông thường **không**. Email có thể đổi, được tái sử dụng, chưa được xác minh hoặc trùng giữa các issuer. Ví dụ:

~~~text
issuer = idp-a, sub = u-17, email = alex@example.test
issuer = idp-b, sub = u-91, email = alex@example.test
~~~

Không tự gộp hai subject thành một user chỉ vì email giống nhau, kể cả khi từng token chứa **email_verified**. Claim xác minh email có ý nghĩa trong phạm vi issuer và thời điểm xác minh; không tự chứng minh hai subject là cùng một chủ thể.

Một quy trình **account linking** cần sự xác minh phù hợp của các tài khoản tham gia và chính sách chống chiếm quyền.

## 9. Multi-tenant: cùng principal, quyền khác nhau theo tổ chức

Giả sử user-42 đã được ánh xạ đúng vào principal 781:

~~~text
principal 781
    tenant-blue  -> order_manager
    tenant-green -> order_viewer
~~~

Một yêu cầu cập nhật đơn hàng trong tenant-green đến API:

~~~http
PUT /tenants/tenant-green/orders/123 HTTP/1.1
Host: orders.example.test
Authorization: Bearer EXAMPLE_ACCESS_TOKEN
Content-Type: application/json

{"status": "approved"}
~~~

Ngay cả khi token có scope **orders:write**, principal chưa chắc có permission **order:update** tại tenant-green. API phải kiểm tra **tenant thật của đơn hàng** từ database/trạng thái server cùng role/permission ở đúng tenant.

Nếu chỉ kiểm sub và vai trò order_manager của tenant-blue rồi cho sửa đơn hàng thuộc tenant-green, hệ thống có thể mắc lỗi **Broken Object Level Authorization (BOLA/IDOR)**.

Tại bước authorization, cần phân biệt:

- Subject của token đã xác minh là ai?
- Principal nội bộ tương ứng có đang hoạt động không?
- Tenant của tài nguyên là tenant nào từ nguồn dữ liệu đáng tin?
- Principal có membership và permission hiện hành ở tenant đó không?
- Scope của token có cho phép client yêu cầu hành động đó không?
- Hành động có còn hợp lệ theo trạng thái nghiệp vụ không?

## 10. Pseudocode ánh xạ danh tính và phân quyền

Ví dụ dưới đây là **mã giả mô tả**. Triển khai thực tế cần thư viện/token validator được kiểm chứng và chính sách lỗi rõ ràng:

~~~text
function getOrder(request, orderId):
    rawToken = extractAccessToken(request)

    context = validateAccessToken(
        rawToken,
        trustedIssuers = configuredIssuerSet,
        requiredAudience = "orders-api",
        requiredTokenProfile = configuredAccessTokenProfile
    )

    if context.invalidOrExpired:
        return HTTP_401

    if not exactScopeMatch(context.scopes, "orders:read"):
        return HTTP_403

    key = {
        issuer: context.verifiedIssuer,
        subject: context.verifiedSubject
    }

    principal = principalDirectory.resolveIdentity(
        key,
        allowedPrincipalTypes = ["HUMAN_USER", "AUTHORIZED_SERVICE"]
    )

    if principal == null or not principal.active:
        return HTTP_403

    order = ordersRepository.find(orderId)
    if order == null:
        return HTTP_404

    if not policyEngine.allow(
        principal = principal,
        client = context.verifiedClientIdIfAvailable,
        action = "order:read",
        tenant = order.tenantId,
        resource = order
    ):
        return HTTP_403

    return HTTP_200(order.toAuthorizedView())
~~~

Điểm cần hiểu:

- **validateAccessToken** phải áp dụng hợp đồng issuer/audience, thuật toán/khóa tin cậy hoặc introspection, thời hạn và loại token. Không chọn thuật toán chỉ vì header do người gửi khai.
- **verifiedSubject** chỉ được lấy từ token đã xác minh. Nếu token/profile không có subject theo schema API yêu cầu, phải từ chối hoặc xử lý bằng hợp đồng riêng; không tự đoán danh tính.
- **resolveIdentity** không gộp các issuer chỉ vì sub giống nhau; cần xét loại principal đã xác minh.
- **order.tenantId** lấy từ dữ liệu server, không chỉ từ URL/header do client tự gửi.
- **policyEngine** xem xét trạng thái tài khoản và quyền hiện hành. Nếu cần kiểm trạng thái bị thu hồi, hệ thống phải thiết kế SLA phù hợp.
- Với hệ thống có policy store tập trung, lỗi mạng cần xử lý theo chính sách; API nhạy cảm không được tự động mở quyền chỉ vì thiếu thông tin.

## 11. Các lỗi bảo mật quanh subject và principal

| Lỗi | Hậu quả | Biện pháp |
| --- | --- | --- |
| Dùng sub làm khóa duy nhất, bỏ issuer. | Token từ issuer B có thể khớp account issuer A. | Khóa mapping theo issuer đã xác minh và subject. |
| Tin sub trước khi kiểm chữ ký hoặc trạng thái token. | Payload giả có thể gắn vào user đặc quyền. | Xác minh token theo profile trước khi đọc claims làm bằng chứng. |
| Cho ID token gọi Resource Server. | Nhầm audience và mục đích token. | API chỉ chấp nhận access token đúng loại/audience. |
| Nhầm client credentials sub thành end-user. | Token dịch vụ có thể dùng quyền tài khoản người dùng. | Phân biệt grant/profile, principal type và client. |
| Ghép user theo email giống nhau. | Account takeover hoặc liên kết sai chủ thể. | Account linking có xác minh độc lập. |
| Tái sử dụng internal ID cho account khác. | Chủ thể mới có thể kế thừa dữ liệu/quyền cũ. | Định danh nội bộ ổn định, chính sách xóa và lifecycle rõ ràng. |
| Áp role người dùng ở mọi tenant. | Truy cập chéo tổ chức. | Kiểm quyền trên tenant thật của tài nguyên. |
| Tin X-User-Id từ request công khai. | Client tự đặt danh tính bất kỳ. | Chỉ dùng ngữ cảnh xác thực từ thành phần proxy/gateway đáng tin, được bảo vệ. |
| Cache principal chỉ theo sub. | Kết quả từ issuer khác có thể bị dùng nhầm. | Cache key theo issuer, subject và ngữ cảnh cần thiết. |
| Ghi nguyên access token vào log. | Token bearer có thể bị lấy và dùng lại. | Che/redact token, chỉ ghi metadata đã xác minh cần thiết. |

### Token substitution và confused identity

**Token substitution** xảy ra khi một token hợp lệ ở một mục đích bị chấp nhận sai ở mục đích khác. Ví dụ, token có **aud=dashboard-client** không được coi là access token của **orders-api**, dù sub đúng và chữ ký có thể xác minh.

**Identity confusion** có thể xảy ra khi gateway, ứng dụng và cơ sở dữ liệu dùng các khóa khác nhau, chẳng hạn gateway kiểm issuer nhưng API cache user theo mỗi sub. Để tránh, mọi lớp phải thống nhất cấu trúc định danh và phạm vi tin cậy.

## 12. Vòng đời định danh khác với vòng đời quyền truy cập

Một subject có thể tồn tại ổn định nhiều năm, nhưng trạng thái và quyền của principal thay đổi thường xuyên:

1. Issuer cấp một subject cho tài khoản.
2. Ứng dụng ánh xạ subject vào principal và gán quyền theo tenant.
3. Quản trị viên rút role hoặc khóa account.
4. Access token đã phát hành vẫn có thể chưa đến hạn hết hiệu lực.
5. Resource Server phải thực thi chính sách thu hồi và kiểm quyền hiện hành theo yêu cầu rủi ro.

**Định danh ổn định không đồng nghĩa quyền truy cập vĩnh viễn.**

Khi dùng JWT tự xác minh ngoại tuyến, chữ ký hợp lệ không nói rằng role/permission trong token vẫn còn mới. Để khóa quyền nhanh, có thể dùng kiểm trạng thái principal, introspection, denylist hoặc cơ chế đồng bộ trạng thái. Opaque token cũng chịu độ trễ cache và mạng nếu dùng introspection.

Các tình huống cần quy tắc riêng:

- **Đổi email hoặc tên hiển thị:** không tự thay external subject mapping.
- **Migration giữa các issuer:** cần quy trình liên kết/tái định danh có xác minh, không gộp bằng email.
- **Vô hiệu account:** giữ mapping phục vụ audit khi phù hợp nhưng không cho principal đã vô hiệu tiếp tục dùng quyền.
- **Xóa dữ liệu người dùng:** không tái gán subject/internal ID khiến chủ thể mới được quyền với dữ liệu cũ.
- **Thiết bị/phiên bị chiếm quyền:** cần thu hồi refresh token/phiên và kiểm soát access token đang lưu hành theo chính sách.

## 13. Quyền riêng tư của subject

Một subject dạng chuỗi ngẫu nhiên vẫn có thể là **định danh có khả năng liên hệ tới người dùng**. Vì thế không nên coi việc không chứa email là đủ để chia sẻ subject rộng rãi.

- Hạn chế claims trong token theo nhu cầu thực; Orders API thường không cần ngày sinh hoặc địa chỉ.
- Tránh đưa email, số nhân viên hoặc các thông tin cá nhân nhạy cảm vào subject nếu có thể dùng định danh opaque ổn định.
- Với OIDC, **pairwise subject** giúp giảm khả năng các client khác sector liên kết dữ liệu chỉ qua sub.
- Kiểm soát quyền truy cập vào bảng external identity mapping, vì bảng này có thể liên kết nhiều danh tính của một người.
- Giảm xuất hiện subject trong URL, telemetry, log và bản export; chỉ ghi metadata cần thiết cho vận hành/audit.

Pairwise subject **không bảo đảm ẩn danh tuyệt đối**. Client có thể nối dữ liệu bằng những thuộc tính khác nếu nhận được; cần đánh giá toàn bộ luồng dữ liệu.

## 14. Bài tập vận dụng

Giả sử ba yêu cầu sau dùng access token đã được xác minh chữ ký, thời hạn và audience hợp lệ, nhưng có ngữ cảnh khác nhau:

**Tình huống A.**

~~~text
iss = https://idp-a.example.test
sub = 42
client_id = dashboard
~~~

**Tình huống B.**

~~~text
iss = https://idp-b.example.test
sub = 42
client_id = dashboard
~~~

**Tình huống C.**

~~~text
iss = https://idp-a.example.test
sub = nightly-sync-service
client_id = nightly-sync-service
grant = client_credentials theo profile issuer
~~~

Hãy đánh giá:

1. **A và B có chắc cùng người?** Không. Trùng sub nhưng khác issuer không đủ chứng minh cùng chủ thể.
2. **C có phải người dùng cuối?** Không nên giả định vậy. Theo mô hình client credentials minh họa, đây là principal dịch vụ/client và phải áp chính sách tương ứng.
3. **Nếu A có role manager ở tenant-blue, có được sửa đơn hàng tenant-green không?** Chỉ khi policy hiện hành cho phép; role ở một tenant không tự mở rộng sang tenant khác.
4. **Nếu B có email giống A, có thể tự hợp nhất hai account không?** Không. Cần liên kết danh tính đã được xác minh và chính sách riêng.
5. **Nếu sub đúng nhưng token hết hạn, API có thể cấp quyền không?** Không; token phải được chấp nhận trước khi dựng principal từ claims.

## 15. Checklist triển khai

Khi xây dựng hoặc review bảo mật token và định danh principal:

- **Nguồn token:** kiểm issuer, audience, loại/profile, hạn dùng và chữ ký/khóa tin cậy hoặc introspection.
- **Subject:** hiểu đúng ngữ nghĩa sub theo từng issuer, loại token và grant; không tự biến đổi chuỗi.
- **Khóa định danh:** ánh xạ theo issuer và subject, cộng ngữ cảnh được hợp đồng yêu cầu; có quy tắc migrate và không tái gán ID.
- **Principal type:** phân biệt user, service, client và actor/delegation khi cần.
- **OIDC:** kiểm ID token đúng audience client; khi dùng UserInfo phải so khớp sub; xem xét public/pairwise identifiers.
- **Liên kết account:** không tự gộp chỉ vì email, username hoặc số điện thoại giống nhau.
- **Multi-tenant:** xác định tenant tài nguyên từ nguồn server và kiểm role/permission hiện hành tại tenant đó.
- **Vòng đời:** account lock, thu hồi quyền và token/phiên có thời gian hiệu lực được định nghĩa.
- **Audit:** tránh ghi token nguyên văn, bảo vệ dữ liệu mapping, lưu truy vết đủ để phân tích sự cố.
- **Kiểm thử:** thử hai issuer cùng sub, leading-zero subject, ID token sai mục đích, service token giả user, đổi quyền giữa phiên và truy cập chéo tenant.

## Kết luận

**Subject (sub)** mô tả chủ thể theo issuer và ngữ nghĩa của token, còn **principal** là thực thể mà hệ thống xác định từ bằng chứng đã xác minh và dùng trong ngữ cảnh xử lý. Trong OIDC, sub của ID token nhận diện End-User với issuer và dành cho client. Trong access token OAuth 2.0, sub có thể đại diện người dùng hoặc dịch vụ tùy luồng và profile.

Để xử lý an toàn, Resource Server cần **xác minh token trước khi tin claims**, ánh xạ định danh bên ngoài bằng **(iss, sub)** trong phạm vi phù hợp, phân biệt loại principal, rồi kiểm scope, quyền hiện hành và tenant/tài nguyên thực. Định danh chính xác là điều kiện cần cho phân quyền, nhưng không thay thế chính sách truy cập.

### Tài liệu tham khảo

- [RFC 7519 — JSON Web Token (JWT), Section 4.1.2: Subject](https://www.rfc-editor.org/rfc/rfc7519#section-4.1.2)
- [RFC 8725 — JSON Web Token Best Current Practices](https://www.rfc-editor.org/rfc/rfc8725)
- [RFC 9068 — JWT Profile for OAuth 2.0 Access Tokens](https://www.rfc-editor.org/rfc/rfc9068)
- [RFC 6749 — The OAuth 2.0 Authorization Framework](https://www.rfc-editor.org/rfc/rfc6749)
- [RFC 7662 — OAuth 2.0 Token Introspection](https://www.rfc-editor.org/rfc/rfc7662)
- [OpenID Connect Core 1.0 — ID Token, Subject Identifier Types](https://openid.net/specs/openid-connect-core-1_0.html)
- [OpenID Connect Core 1.0 — UserInfo Response Validation](https://openid.net/specs/openid-connect-core-1_0.html#UserInfoResponse)
