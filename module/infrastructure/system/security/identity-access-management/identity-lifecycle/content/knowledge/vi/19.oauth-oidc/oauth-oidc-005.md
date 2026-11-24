# Resource server trong OAuth 2.0 và OIDC: bảo vệ API và thực thi quyền truy cập

> **Chương:** OAuth và OIDC  
> **Bài:** Resource server  
> **Module:** `SECURITY_IDENTITY_ACCESS_MANAGEMENT_IDENTITY_LIFECYCLE`  
> **Bối cảnh:** Quản lý vòng đời danh tính theo **Joiner–Mover–Leaver (JML)**, từ xác minh và tạo tài khoản đến cấp, điều chỉnh và thu hồi quyền. Nội dung liên kết **IdP, SSO, SCIM, RBAC/ABAC, tài khoản dịch vụ, kiểm toán** và giảm quyền truy cập tồn dư.

## 1. Resource server là gì?

Giả sử nhân viên Mai đăng nhập ứng dụng quản lý hóa đơn. Mai nhìn thấy giao diện web và muốn tải danh sách hóa đơn của chi nhánh Hà Nội. Trình duyệt hoặc backend của ứng dụng có thể gọi API `GET /invoices`. Để đáp ứng yêu cầu, API cần trả lời ít nhất hai câu hỏi:

1. Yêu cầu có mang **bằng chứng ủy quyền hợp lệ dành cho API này** hay không?
2. Chủ thể trong bằng chứng đó **có được phép xem các hóa đơn cụ thể đang yêu cầu** hay không?

Trong **OAuth 2.0**, *Resource Server (RS)* là máy chủ lưu trữ hoặc cung cấp **tài nguyên được bảo vệ (protected resources)**, có khả năng tiếp nhận và kiểm tra access token để xử lý yêu cầu phù hợp. Trong thực tế, RS thường là một HTTP API, nhưng khái niệm không bị giới hạn ở một loại phần mềm duy nhất.

**Resource server không phải nơi mặc định xác thực mật khẩu, tạo ID token, đăng ký người dùng hay phát hành access token.** Các trách nhiệm đó thuộc những thành phần khác, chẳng hạn Authorization Server (AS), Identity Provider (IdP) hoặc hệ thống IAM/provisioning, tùy kiến trúc.

Ví dụ:

- `billing-api` là RS cung cấp hóa đơn.
- `reporting-api` là RS cung cấp báo cáo.
- Authorization Server phát hành access token cho client được phép gọi API.
- RS kiểm tra token **đúng issuer, audience, loại token, thời hạn và điều kiện sử dụng**, rồi kiểm tra **quyền trên hành động và tài nguyên thực tế**.

Một token hợp lệ chỉ là đầu vào cho quyết định. Không phải mọi token có chữ ký đúng đều được phép gọi mọi API, và không phải mọi người dùng có quyền `invoice.read` đều được xem tất cả hóa đơn.

## 2. Phân biệt Resource Server với các thành phần OAuth/OIDC khác

| Thành phần | Trách nhiệm chính | Không nên nhầm với |
|---|---|---|
| **Resource Owner** | Chủ thể có thẩm quyền đối với việc cho phép truy cập tài nguyên theo mô hình OAuth | Không luôn là người đang trực tiếp gọi API |
| **Client** | Ứng dụng yêu cầu hoặc dùng token để truy cập RS | Không đương nhiên là Resource Owner |
| **Authorization Server (AS)** | Xác thực client/điều kiện phù hợp, xử lý authorization grant, phát hành token | Không tự động là API lưu toàn bộ dữ liệu nghiệp vụ |
| **Identity Provider (IdP)** | Xác thực danh tính và cung cấp kết quả xác thực, thường qua OIDC/SAML | Không thay kiểm soát quyền trên từng hóa đơn |
| **OpenID Connect Relying Party (RP)** | Client dùng OIDC để xác thực người dùng | Không được dùng ID token như access token API |
| **Resource Server (RS)** | Nhận access token và bảo vệ endpoint/dữ liệu | Không tự phát token chỉ bằng việc kiểm tra JWT |
| **Identity Governance / Provisioning** | Quản lý user, group, role và quyền theo JML, có thể dùng SCIM/API | Không đồng nghĩa giao thức OAuth để gọi resource |
| **Policy Decision Point / Policy Enforcement Point** | Ra quyết định / thực thi authorization, có thể nằm trong API, gateway hoặc dịch vụ policy | Không nhất thiết là hai sản phẩm tách rời |

Trong OIDC, một Authorization Server có hỗ trợ OIDC cũng đóng vai trò **OpenID Provider (OP)** khi phát hành thông tin xác thực danh tính theo giao thức. Nhưng một RS có thể phục vụ API không hề dùng OIDC, ví dụ API được gọi qua OAuth Client Credentials.

### 2.1. OAuth chủ yếu giải quyết ủy quyền, OIDC bổ sung danh tính

- **OAuth 2.0:** định nghĩa khung ủy quyền để một client nhận và sử dụng access token gọi resource theo phạm vi được phép.
- **OIDC:** lớp định danh xây trên OAuth 2.0, bổ sung ID token và các quy tắc xác thực user.
- **RS:** thường quan tâm **access token** và policy truy cập của API; không nên lấy ID token của OIDC để thay thế access token.

OAuth không tự chứng minh một người dùng đã hoàn tất MFA theo mức mong muốn. Nếu quyết định API cần ngữ cảnh xác thực, phải có hợp đồng tin cậy về nguồn và cách truyền/kiểm tra dữ liệu đó, thay vì tự đọc một trường từ trình duyệt.

## 3. Luồng truy cập một Resource Server

Giả sử ứng dụng CRM có client `crm-web`, Authorization Server `login.corp.example` và API `crm-api`.

~~~mermaid
sequenceDiagram
    participant U as Người dùng
    participant C as Client / CRM Web
    participant AS as Authorization Server / IdP
    participant RS as Resource Server / CRM API
    U->>C: Mở CRM và yêu cầu xem ticket
    C->>AS: Bắt đầu OAuth/OIDC flow được hỗ trợ
    AS->>U: Xác thực và kiểm tra điều kiện truy cập
    U-->>AS: Hoàn tất phương thức được yêu cầu
    AS-->>C: Authorization result
    C->>AS: Đổi authorization code kèm bằng chứng thích hợp
    AS-->>C: Access token dành cho CRM API
    C->>RS: GET /tickets kèm access token
    RS->>RS: Xác minh token, audience, thời hạn và policy
    RS->>RS: Kiểm tra quyền trên từng ticket/tenant
    RS-->>C: 200 dữ liệu được phép hoặc 401/403
~~~

Đây là mô hình **Authorization Code Flow** đơn giản hóa; trong triển khai công khai, PKCE và các biện pháp bảo vệ flow khác phải theo cấu hình phù hợp. Token có thể được lưu và gửi bởi backend-for-frontend (BFF) thay vì trực tiếp ở trình duyệt, tùy kiến trúc.

### 3.1. Luồng client credentials

Không phải lúc nào RS cũng phục vụ yêu cầu đại diện một người dùng. Một ứng dụng định kỳ `invoice-sync` có thể dùng **Client Credentials Grant** để xin token với quyền máy–máy. AS cấp token cho client/workload theo trust và policy; RS phải nhận biết đây là **application principal**, không giả định có nhân viên đang thao tác.

~~~mermaid
sequenceDiagram
    participant W as Workload / Invoice Sync
    participant AS as Authorization Server
    participant RS as Resource Server
    W->>AS: Token request với client authentication hợp lệ
    AS->>AS: Xác minh client, scopes, audience và policy
    AS-->>W: Access token cho billing-api
    W->>RS: GET /export với access token
    RS->>RS: Xác minh token và app-only permissions
    RS-->>W: Dữ liệu đúng phạm vi hoặc từ chối
~~~

Không dùng tài khoản cá nhân của nhân viên cùng OTP/MFA tương tác để cho job tự chạy. Workload nên có principal, credential/trust, owner và vòng đời riêng.

## 4. Resource server nhận những loại token nào?

### 4.1. Access token

**Access token** là credential client xuất trình cho RS khi truy cập tài nguyên được bảo vệ. AS định nghĩa định dạng và các quy tắc xác minh; RS phải dựa vào hợp đồng integration chính thức.

Token có thể là:

- **Opaque/reference token:** chuỗi không có ý nghĩa tự giải mã tại RS; RS thường dùng token introspection hoặc cơ chế xác minh đã được thiết lập.
- **JWT access token:** token chứa claims có chữ ký và được RS kiểm tra theo profile/hợp đồng của AS.
- **Sender-constrained token:** token bị ràng buộc với một khóa/chứng chỉ của client như DPoP hoặc mutual TLS, nếu cả AS và RS hỗ trợ.

Không mặc định rằng chuỗi có ba đoạn phân cách bằng dấu chấm là **đủ tin cậy**. Token cần được xác minh đầy đủ và đúng loại.

### 4.2. ID token trong OIDC

**ID token** chứng minh sự kiện xác thực user cho client/RP được chỉ định theo OIDC. ID token thường có audience là **client ID**. RS không nên chấp nhận ID token để gọi API chỉ vì nó có chữ ký từ cùng IdP.

| Loại token | Bên nhận chính | Mục đích |
|---|---|---|
| **ID token** | OIDC client/RP | Thông tin và kết quả xác thực user |
| **Access token** | Resource Server/API có audience thích hợp | Quyền truy cập tài nguyên được bảo vệ |
| **Refresh token** | Client tương tác với Authorization Server theo policy | Xin access token mới; thường không gửi cho RS |

API phải từ chối ID token dùng sai mục đích, kể cả khi token chứa email, tên người dùng hoặc nhóm.

### 4.3. Access token không nhất thiết là JWT

OAuth 2.0 không yêu cầu mọi access token đều có định dạng JWT. Một số nền tảng dùng token tham chiếu; đó không phải lỗi thiết kế. Quan trọng là RS có cách **xác nhận tính hợp lệ, mục đích sử dụng, chủ thể, quyền và trạng thái** đáng tin cậy.

## 5. Bearer token và việc bảo vệ token trên đường truyền

Với **bearer token**, bất kỳ bên nào sở hữu token hợp lệ đều có thể sử dụng nó trong phạm vi chính sách cho đến khi token hết hạn/bị thu hồi, trừ khi có các biện pháp ràng buộc bổ sung.

Ví dụ HTTP đơn giản:

~~~http
GET /v1/invoices/INV-2048 HTTP/1.1
Host: billing-api.example
Authorization: Bearer <access-token>
Accept: application/json
~~~

Chuỗi `<access-token>` là chỗ giữ chỗ, không phải token thật. Yêu cầu phải dùng **HTTPS/TLS** và biện pháp bảo vệ phù hợp; không đặt token trong URL query để tránh lộ qua log, lịch sử trình duyệt hoặc header tham chiếu.

Các nguyên tắc:

- Không ghi token thô trong log, exception, tracing, analytics hoặc ảnh chụp lỗi.
- Không cấp token cho client không có quyền hoặc audience không phù hợp.
- Hạn chế scope, thời hạn và quyền trong token theo nhu cầu.
- Không truyền access token tùy tiện cho một dịch vụ downstream chỉ vì “cùng nội bộ”.
- Không dựa vào Base64 decode của JWT để kết luận token đã được xác minh.
- Khi dùng token sender-constrained, RS còn phải kiểm tra **bằng chứng sở hữu khóa** theo profile, không chỉ kiểm tra signature của access token.

### 5.1. Không lấy token từ nhiều vị trí không kiểm soát

Theo kiểu truyền bearer token qua HTTP, header `Authorization: Bearer` là lựa chọn phổ biến. Tránh cho phép đồng thời token từ header, cookie, URL và trường body một cách tùy tiện vì sẽ khó xác định token nào được ưu tiên và tăng nguy cơ rò rỉ.

Nếu gateway hoặc BFF chuyển danh tính sang backend, phải thiết kế lại trust boundary: backend chỉ tin **thông tin đã được gateway xác thực qua kênh nội bộ bảo vệ**, không tin header `X-User-Role: admin` mà client Internet tự đặt.

## 6. JWT access token: Resource server cần xác minh những gì?

Giả sử Authorization Server phát hành **JWT access token** theo một hợp đồng/profile rõ ràng. Payload minh họa:

~~~json
{
  "iss": "https://login.corp.example/tenant-a",
  "sub": "employee-1042",
  "aud": "https://api.corp.example/billing",
  "exp": 1795400400,
  "iat": 1795400100,
  "nbf": 1795400100,
  "jti": "jwt-access-2026-2048",
  "client_id": "billing-web",
  "scope": "invoice.read invoice.approve",
  "tenant_id": "tenant-a"
}
~~~

Đây là dữ liệu **giả lập** để giải thích claims, không phải access token có giá trị và cũng không biểu diễn mọi claim bắt buộc của một profile cụ thể.

### 6.1. Danh sách kiểm tra tối thiểu

1. **Thuật toán chữ ký:** chỉ chấp nhận thuật toán được AS và RS cấu hình cho loại token đó; từ chối `alg=none` hoặc thuật toán bất ngờ.
2. **Chữ ký:** xác minh bằng khóa tin cậy được phân phối qua cấu hình/metadata/JWKS của issuer đã phê duyệt; không tự tin một URL khóa do input token tùy ý dẫn tới.
3. **Issuer (`iss`):** khớp issuer được phép của đúng môi trường/tenant. Cùng một vendor không có nghĩa mọi tenant đều đáng tin.
4. **Audience (`aud`):** phải chứa định danh RS/API phù hợp theo hợp đồng; không chấp nhận token phát cho API khác.
5. **Thời hạn (`exp`, `nbf` và quy tắc thời gian):** token đang trong khoảng hợp lệ, chỉ cho phép clock skew có kiểm soát.
6. **Loại token/profile:** phân biệt JWT access token với ID token hoặc JWT dùng mục đích khác; nếu có `typ`, chỉ diễn giải theo profile được chấp thuận.
7. **Subject và client:** giải thích `sub`, `client_id` hoặc claims tương ứng theo ngữ nghĩa issuer, phân biệt delegated user và app-only.
8. **Scopes/permissions:** chỉ dùng claims đã xác minh, có ngữ nghĩa được hợp đồng hóa và phù hợp action.
9. **Tenant/resource constraints:** kiểm tra tenant, region, owner và điều kiện đối với tài nguyên được yêu cầu.
10. **Token binding:** nếu token sender-constrained, kiểm tra DPoP/mTLS proof hoặc chứng chỉ theo cơ chế cấu hình.

**Không phải tất cả claims minh họa đều bắt buộc có trong mọi access token**, và một số hệ thống dùng `scp`, `roles` hoặc claims riêng thay cho `scope`. Đừng tự áp dụng ngữ nghĩa của một provider lên provider khác.

### 6.2. Cảnh giác token substitution và algorithm confusion

Một hệ thống có thể dùng cùng IdP phát hành ID token cho web client và access token cho API. Nếu RS chỉ kiểm tra chữ ký mà bỏ qua audience, token dành cho client khác có thể bị dùng sai mục đích. Đây là **token substitution**.

Tương tự, RS không nên để giá trị `alg`, `kid`, `jku` hoặc URL bất kỳ do token mang theo quyết định một cách không kiểm soát nguồn khóa tin cậy. JWKS phải được lấy từ cấu hình đã xác minh của issuer, có chính sách rotation, caching và xử lý khóa không nhận diện được.

### 6.3. Phân biệt `sub` trong token user và app-only

Với delegated user access, `sub` có thể định danh user theo issuer. Với client credentials, tùy authorization server/profile, `sub` có thể đại diện client hoặc một chủ thể kỹ thuật. **Không được suy ra `sub` luôn là employee ID**.

Để tránh cấp sai quyền, API nên định nghĩa rõ:

- Token nào có user context được AS xác nhận?
- Token nào là app-only?
- Scope/role nào dành cho người dùng và scope/role nào dành cho workload?
- Có được phép impersonation/delegation không và có bằng chứng ủy quyền riêng không?

Không lấy email hoặc tên hiển thị làm identity key để kiểm tra quyền trên database.

## 7. Opaque token và token introspection

Với **opaque access token**, RS thường không tự xác minh bằng chữ ký JWT. Nó cần sử dụng **token introspection** hoặc kênh kiểm tra mà authorization server hỗ trợ và được cấu hình.

Trong mô hình introspection (ví dụ OAuth 2.0 Token Introspection), RS xác thực với AS theo cơ chế được phê duyệt, hỏi trạng thái token và nhận thông tin phù hợp.

Ví dụ phản hồi introspection **minh họa**:

~~~json
{
  "active": true,
  "client_id": "billing-web",
  "sub": "employee-1042",
  "scope": "invoice.read",
  "aud": "https://api.corp.example/billing",
  "iss": "https://login.corp.example/tenant-a",
  "exp": 1795400400
}
~~~

Không coi `active=true` là quyết định cho phép mọi thao tác. RS vẫn cần kiểm tra audience, scope, tenant, user/account state hoặc điều kiện cần thiết theo contract, và thực thi authorization tại tài nguyên.

### 7.1. Phản hồi introspection không phải dữ liệu từ client

RS chỉ tin phản hồi đến từ endpoint introspection được cấu hình qua kênh bảo vệ và có **client authentication/authorization** đúng. Không cho phép caller tự gửi JSON `{"active":true}` hoặc chọn endpoint introspection tùy ý.

### 7.2. Caching và giới hạn thu hồi

Introspection có thể cần request mạng mỗi lần hoặc kết quả được cache có hạn. Điều này tạo đánh đổi:

- **Không cache:** có thể cập nhật trạng thái nhanh hơn nhưng tăng độ trễ/phụ thuộc mạng.
- **Cache có TTL ngắn:** giảm tải, nhưng token đã bị thu hồi có thể còn được chấp nhận đến hết TTL cache.
- **Cache quá lâu:** làm tăng cửa sổ quyền tồn dư sau Mover/Leaver.

Quyết định cache nên dựa trên mức rủi ro tài nguyên, thời hạn token, hợp đồng AS và cơ chế xử lý sự cố. Khi introspection không khả dụng, API nhạy cảm không nên mặc định cho phép mọi token chưa được xác minh (*fail-open*).

### 7.3. JWT offline verification cũng có giới hạn

JWT có thể được RS xác minh cục bộ mà không cần hỏi AS mỗi request. Nhưng chữ ký và `exp` hợp lệ **không cho biết** user vừa nghỉ việc hay quyền vừa bị thu hồi, trừ khi RS có thêm cơ chế kiểm tra trạng thái, danh sách thu hồi, token ngắn hạn hoặc policy tái đánh giá phù hợp.

**JWT vs opaque token không phải cuộc so sánh “cái nào an toàn tuyệt đối”.** Lựa chọn phải đi cùng chiến lược revocation, session, latency, caching và điều kiện authorization.

## 8. Sender-constrained access token: DPoP và mutual TLS

Bearer token có rủi ro bị dùng lại nếu bị đánh cắp. Một số kiến trúc hỗ trợ **sender-constrained tokens**: token ràng buộc với bằng chứng client sở hữu một khóa.

### 8.1. DPoP (Demonstrating Proof of Possession)

Với DPoP, client tạo bằng chứng dạng JWT được ký bằng khóa riêng của mình và gửi kèm yêu cầu. Access token có thể chứa thông tin ràng buộc với public key, ví dụ `cnf.jkt`, theo hợp đồng profile.

Resource server phải kiểm tra phù hợp:

- DPoP proof có chữ ký đúng với khóa được công bố trong proof.
- Token được ràng buộc với public key/thumbprint tương ứng.
- HTTP method và URI đích phù hợp, dựa theo thông tin trong proof.
- Thời điểm, giá trị nhận diện proof và chống replay (ví dụ `jti`, `iat`, nonce khi áp dụng).
- Ràng buộc access token với proof theo yêu cầu của profile (như `ath` khi cần).

**Chỉ thấy header `DPoP` không đủ** để nói token có proof-of-possession. Phải xác minh toàn bộ quan hệ giữa proof, access token và request.

### 8.2. Mutual TLS (mTLS)

Với mTLS sender-constrained access token, token có thể ràng buộc với chứng chỉ client theo profile thích hợp, ví dụ thông tin xác nhận `cnf.x5t#S256`. RS phải xác minh kết nối mTLS/chứng chỉ và quan hệ binding với token.

Nếu TLS chấm dứt tại reverse proxy, phải thiết kế cách truyền chứng cứ chứng chỉ đến RS qua **kênh nội bộ đáng tin**, không tin header chứng chỉ do Internet client tự khai. Khả năng hỗ trợ mTLS giữa gateway, mesh và app cần được xác minh theo deployment.

### 8.3. Bảo vệ thêm nhưng không thay quyền

Token sender-constrained giúp giảm một số rủi ro sử dụng token bị đánh cắp. Nó **không** biến một client thành admin, không sửa lỗi IDOR/BOLA và không tự thu hồi quyền sai. Scope, tenant, role và quyền tài nguyên vẫn phải được kiểm tra.

## 9. Scope, role và quyền trên từng đối tượng

Resource server phải phân biệt **phạm vi ủy quyền ở access token** với **quyền nghiệp vụ trên tài nguyên thực**.

Ví dụ scope `invoice.read` cho biết client được phép yêu cầu chức năng đọc hóa đơn theo chính sách. Nó **không tự chứng minh** user có quyền đọc hóa đơn của mọi chi nhánh hoặc mọi khách hàng.

| Lớp kiểm soát | Câu hỏi | Ví dụ |
|---|---|---|
| Token validity | Credential dành cho API này có hợp lệ không? | `iss`, signature, `aud`, `exp` |
| Coarse-grained scope | Client/token có được gọi loại chức năng này? | `invoice.read` |
| RBAC | Principal có role nghiệp vụ cần thiết không? | `billing.viewer` |
| ABAC | Thuộc tính subject, object, action, environment có phù hợp không? | `principal.region == invoice.region` |
| Object-level authorization | User/client có quyền với **hóa đơn cụ thể** không? | `invoice.tenantId == principal.tenantId` |
| SoD / transaction controls | Có xung đột giữa tạo và phê duyệt không? | Không tự duyệt khoản đã tạo |
| Auth assurance / step-up | Thao tác có yêu cầu MFA đủ mạnh/mới không? | Duyệt khoản nhạy cảm |
| Device / context | Thiết bị, mạng hoặc rủi ro có thỏa policy không? | Managed + compliant nếu policy yêu cầu |

Một token có `scope=invoice.read` không đủ để tải `/invoices/{id}` nếu object thuộc tenant khác. Nếu API bỏ kiểm tra object-level, có nguy cơ **Broken Object Level Authorization (BOLA/IDOR)**.

### 9.1. Authorization thực thi tại RS hoặc tầng tin cậy phù hợp

Có thể dùng gateway kiểm tra token và scope đầu vào; song RS vẫn phải có bảo đảm rằng **quyền trên tài nguyên cụ thể** được kiểm tra. Nếu chính sách nằm tại một dịch vụ trung tâm, RS phải truyền đủ thông tin và nhận quyết định đáng tin, không tự tin rằng gateway đã biết chính xác mọi dữ liệu nghiệp vụ.

### 9.2. Scope không đồng nghĩa đã có consent cho mọi dữ liệu

Trong OAuth, authorization grant/consent theo client và policy không tự tạo quyền trên một hồ sơ mà resource owner/đơn vị nghiệp vụ không cho phép. API cần kết hợp token scopes với entitlement, ownership và ràng buộc tổ chức.

## 10. Ví dụ xử lý request tại Resource Server

Giả sử API có endpoint `GET /v1/invoices/{invoiceId}`. Chúng ta cần kiểm tra token và quyền tại hóa đơn được yêu cầu.

~~~text
function getInvoice(request):
    token = extractExpectedAccessToken(request)

    proof = verifyTokenWithConfiguredIssuer(token)

    if not proof.valid:
        return HTTP_401_UNAUTHORIZED

    if not proof.isAccessTokenFor("billing-api"):
        return HTTP_401_UNAUTHORIZED

    if not proof.scopeAllows("invoice.read"):
        return HTTP_403_FORBIDDEN

    principal = resolveTrustedPrincipal(proof)
    if not principal.isActive:
        return HTTP_403_FORBIDDEN

    invoice = loadInvoiceFromProtectedStore(request.invoiceId)
    if invoice is NONE:
        return HTTP_404_NOT_FOUND

    if invoice.tenantId != principal.tenantId:
        return DENY_WITH_NON_DISCLOSING_RESPONSE

    if not policyAllows(principal, "invoice.read", invoice, request.context):
        return HTTP_403_FORBIDDEN

    return HTTP_200_WITH_ALLOWED_INVOICE_FIELDS(invoice)
~~~

Đây là **pseudocode đào tạo**, không phải code production. Trong thực tế:

- Đừng trả ra dữ liệu object trước khi kiểm tra tenant/owner.
- Không tin `tenantId` hoặc `role` do client tự nhập nếu chưa đối chiếu nguồn tin cậy.
- Với tài nguyên không thuộc quyền, có thể dùng 404 để tránh tiết lộ sự tồn tại theo chính sách, nhưng phải nhất quán và chống suy luận qua mã lỗi/thời gian.
- Đối với quyền cao, có thể cần dữ liệu trạng thái mới hơn token claims hoặc xác thực bổ sung.
- Việc kiểm tra proof của DPoP/mTLS, token type và thông tin phiên phải nằm trong `verifyTokenWithConfiguredIssuer` theo hợp đồng thật.

### 10.1. Tại sao phải kiểm tra mỗi request?

Kẻ tấn công có thể bỏ qua giao diện web và gọi API trực tiếp. Ẩn nút “Approve” không có giá trị bảo vệ nếu endpoint `POST /invoices/approve` không thực thi policy phía server.

Một authorization middleware có thể hỗ trợ kiểm tra chung, nhưng kiểm tra **invoice.owner/tenant/SoD** thường cần dữ liệu nghiệp vụ của endpoint. Tính đúng của quyền không được phụ thuộc vào việc user có đi qua màn hình giao diện nào.

## 11. HTTP 401 và 403: trả lỗi đúng khi truy cập bị chặn

Resource Server dùng mã HTTP để thể hiện điều kiện lỗi, không làm lộ thông tin nhạy cảm.

| Tình huống | Mã thường dùng | Ý nghĩa |
|---|---:|---|
| Không có credential truy cập phù hợp | **401 Unauthorized** | Cần cơ chế xác thực/ủy quyền truy cập hợp lệ |
| Access token không hợp lệ hoặc hết hạn | **401** | Token không thể được chấp nhận |
| Token hợp lệ nhưng thiếu scope cần thiết | **403 Forbidden** | Có credential nhưng không đủ quyền |
| Token hợp lệ nhưng principal không được phép xem object | **403** hoặc **404** theo chính sách | Từ chối quyền và cân nhắc không tiết lộ object |
| Endpoint tồn tại nhưng caller bị cấm theo policy | **403** | Quyền nghiệp vụ không đủ |

Với bearer token theo profile tương ứng, RS có thể trả `WWW-Authenticate`:

~~~http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer realm="billing-api", error="invalid_token"
Content-Type: application/json

{"error":"unauthorized"}
~~~

Khi thiếu scope, ví dụ minh họa:

~~~http
HTTP/1.1 403 Forbidden
WWW-Authenticate: Bearer realm="billing-api", error="insufficient_scope", scope="invoice.approve"
Content-Type: application/json

{"error":"forbidden"}
~~~

Chỉ sử dụng `WWW-Authenticate`, mã và thuộc tính theo hợp đồng/giao thức được hỗ trợ. Không đưa token, chi tiết chính sách nội bộ hay dữ liệu người dùng vào thông báo lỗi công khai. **401 trong HTTP có tên lịch sử “Unauthorized” nhưng thường có nghĩa credential xác thực truy cập chưa hợp lệ**; 403 biểu thị không đủ quyền.

## 12. Resource Server, API Gateway và hệ thống microservices

Một hệ thống lớn có thể gồm nhiều Resource Server, ví dụ `billing-api`, `customer-api`, `reporting-api`. Gateway có thể xác minh một số điều kiện chung nhưng phải xác định ranh giới tin cậy.

~~~mermaid
flowchart LR
    C[Client] --> G[API Gateway / Edge]
    G --> B[Billing Resource Server]
    G --> R[Reporting Resource Server]
    B --> P[Policy / IAM data]
    R --> P
    B --> DB1[(Billing records)]
    R --> DB2[(Reports)]
    AS[Authorization Server / IdP] -->|JWKS / introspection / policy contract| G
    AS -->|Issuer config / token validation| B
    AS -->|Issuer config / token validation| R
~~~

### 12.1. Gateway không thay kiểm tra ở backend một cách mặc định

Nếu gateway chỉ biết `scope=invoice.read`, nó không nhất thiết biết hóa đơn thuộc tenant nào. Backend cần tiếp tục kiểm tra quyền object-level, hoặc sử dụng một cơ chế policy đáng tin đã được chứng minh bao quát dữ liệu đó.

Nếu backend tin header `X-Authenticated-User` từ gateway, cần bảo đảm:

- Không có đường Internet gọi trực tiếp backend để chèn header giả.
- Gateway loại bỏ hoặc viết lại header do client tự gửi.
- Kênh gateway–backend có xác thực và bảo vệ toàn vẹn.
- Backend kiểm tra danh tính gateway, scope của thông tin chuyển tiếp và giới hạn tin cậy.

### 12.2. Không chuyển tiếp token nguyên trạng sang mọi API

Token phát cho `billing-api` không nên được `reporting-api` chấp nhận chỉ vì cùng issuer. Các API phải có audience và quyền riêng. Khi backend A cần gọi backend B, hãy chọn thiết kế phù hợp:

- Token dành riêng cho API B qua cơ chế OAuth tương thích.
- OAuth token exchange hoặc on-behalf-of flow khi AS hỗ trợ và có quyền ủy quyền rõ.
- Client credentials của workload A nếu hành động thuộc trách nhiệm riêng của ứng dụng.
- Giới hạn lại quyền/scope tại API B và tránh truyền danh tính user không có căn cứ.

Không làm “đường tắt” bằng cách tắt kiểm tra audience.

### 12.3. Resource indicators và audience hạn chế

Một số hệ thống hỗ trợ **resource indicators** để client yêu cầu access token cho một RS cụ thể. Thiết kế nên tránh token “dùng được khắp nơi” khi API có ranh giới dữ liệu và mức rủi ro khác nhau. Việc sử dụng `resource` parameter hay audience cụ thể phải theo hỗ trợ của AS.

## 13. Multi-tenant Resource Server

Một RS có thể phục vụ nhiều công ty hoặc tenant. Đây là nơi dễ xảy ra rò rỉ dữ liệu dù token hợp lệ.

Ví dụ `billing-api` phục vụ `tenant-A` và `tenant-B`. Một user thuộc `tenant-A` có scope `invoice.read` không được xem `tenant-B` bằng cách đổi invoice ID trong URL.

Các yêu cầu chính:

1. Token được phát bởi issuer/tenant nằm trong danh sách được cho phép.
2. Account hoặc service principal được liên kết với tenant đúng theo nguồn có thẩm quyền.
3. Đường dẫn, query, header `tenantId` do client cung cấp được đối chiếu, không tự tin.
4. Repository/database query áp dụng tenant filtering có kiểm soát và không cho bypass.
5. Role/entitlement phải gắn với tenant/resource phù hợp, không dùng một role `admin` không namespace cho mọi tenant.
6. Nếu có B2B federation, external group không tự thành quyền quản trị nội bộ.
7. Audit ghi lại cả principal, tenant được yêu cầu và tenant thực tế của resource theo chính sách bảo vệ dữ liệu.

### 13.1. Tránh nhầm cùng `sub` giữa issuer

Hai issuer có thể cùng phát `sub=123`. Resource server hoặc dịch vụ ánh xạ danh tính cần phân biệt theo **`(trusted issuer, subject)`**, không nối hồ sơ chỉ bằng `sub`, email hoặc tên hiển thị.

### 13.2. Không lấy role từ một token không đúng audience

Ngay cả role/grant từ một issuer đáng tin cũng có thể có ý nghĩa khác nhau giữa API. RS cần **hợp đồng claims/permission riêng**. Claim `roles=["admin"]` dành cho portal A không nên được hiểu là quyền admin trên billing API B.

## 14. Resource Server trong Joiner lifecycle

Trong Joiner, nhân viên mới phải được xác minh, tạo account, cấp đúng quyền và có thể truy cập API sau ngày hiệu lực.

Một luồng minh họa:

1. **Nguồn có thẩm quyền** tạo employee identity với ID ổn định, trạng thái và ngày bắt đầu.
2. **IdP/AS** đăng ký danh tính và cấu hình cơ chế xác thực (SSO/MFA phù hợp).
3. **IAM/IG** tính group, role và entitlement theo công việc, tenant và người duyệt.
4. **SCIM/API provisioning** có thể tạo account/đồng bộ nhóm sang hệ thống đích, nếu sản phẩm hỗ trợ.
5. **Authorization Server** chỉ phát access token với audience/scope phù hợp theo policy, không cấp một token quyền cao mặc định.
6. **Resource Server** kiểm tra token và cả quyền nghiệp vụ/tài nguyên khi có request.
7. **Đối soát** xác minh user được phép gọi đúng API hợp lệ và bị từ chối các endpoint/tenant ngoài quyền.
8. **Audit** lưu sự kiện Joiner, approval, thời điểm hiệu lực và kết quả kiểm tra.

**Không nhầm SCIM và OAuth:** SCIM chủ yếu giúp đồng bộ tài khoản/nhóm; OAuth access token dùng khi truy cập RS. Một account mới được tạo qua SCIM không đồng nghĩa user đã có quyền đọc mọi bản ghi trên API.

### 14.1. Tài khoản được tạo trước ngày vào làm

Có thể chuẩn bị account và chính sách trước ngày bắt đầu, nhưng **RS hoặc nguồn policy phải bảo đảm access chỉ có hiệu lực đúng thời điểm**. Nếu token được phát sớm hoặc role được đồng bộ sớm, API nhạy cảm cần xem điều kiện ngày hiệu lực theo thiết kế.

## 15. Resource Server trong Mover lifecycle

Mover xảy ra khi user đổi vị trí, phạm vi, quyền duyệt hoặc team. Một quyền cũ có thể không còn hợp lệ trong khi user vẫn active.

Ví dụ, nhân viên An chuyển từ chi nhánh Hà Nội sang Đà Nẵng:

| Thuộc tính/quyền | Trước Mover | Sau Mover được duyệt | RS cần bảo đảm |
|---|---|---|---|
| `region` | HN | DN | Không cho đọc hóa đơn HN nếu không còn quyền |
| `invoice.read` | Có | Có | Scope có thể giữ nhưng object-level filter phải thay |
| `invoice.approve` | Có | Không | Từ chối endpoint duyệt ở API |
| `accountStatus` | ACTIVE | ACTIVE | Không khóa toàn bộ tài khoản nếu vẫn làm việc |
| Phiên/token cũ | Có thể chứa claim HN/approve | Không còn hợp lệ cho quyền cũ | Làm mới/thu hồi hoặc kiểm tra policy mới theo thiết kế |

Nếu RS dựa hoàn toàn vào JWT sống nhiều giờ có `region=HN`, user có thể tiếp tục xem dữ liệu cũ cho đến khi token hết hạn. Đây là **quyền truy cập tồn dư sau Mover**.

Các biện pháp thường cân nhắc:

- Token thời hạn ngắn theo rủi ro.
- Kiểm tra entitlement/trạng thái hiện tại tại RS hoặc Policy Decision Point đối với thao tác nhạy cảm.
- Introspection hoặc event-driven invalidation nếu kiến trúc hỗ trợ.
- Cơ chế phiên/revocation phù hợp với AS và gateway.
- Đối soát trạng thái trên API và target sau khi entitlement được thay đổi.

### 15.1. Quyền hiệu lực không chỉ nằm trong scope

Nếu scope `invoice.read` không thay đổi khi user chuyển chi nhánh, **điều kiện tenant/region phải được kiểm tra ở backend**. Token không mang region không nhất thiết sai; RS có thể lấy thuộc tính quyền từ nguồn đáng tin khác. Vấn đề là nguồn và độ mới của policy, không chỉ cấu trúc claims.

### 15.2. Step-up khi Mover sang vai trò nhạy cảm

Khi nhân viên được giao quyền duyệt thanh toán, RS có thể cần bằng chứng **mức xác thực cao hơn** hoặc **lần xác thực đủ mới**. Điều kiện này nên được IdP/AS hỗ trợ theo hợp đồng rõ; RS không tự biến một HTTP header do client đặt thành chứng nhận MFA.

**Có token hợp lệ + scope duyệt chưa chắc đủ:** phải thỏa role, hạn mức, SoD, tenant, thời điểm hiệu lực và assurance yêu cầu.

## 16. Resource Server trong Leaver lifecycle và thu hồi token

Khi nhân viên nghỉ, tổ chức thường muốn chấm dứt quyền truy cập càng sát thời điểm hiệu lực càng tốt theo rủi ro. Nhưng các thành phần có thể độc lập:

- IdP/AS ngăn xác thực và phát token mới.
- SCIM/API ngừng account và gỡ group/role tại ứng dụng.
- RS có thể vẫn nhận **access token đã phát hành**.
- SaaS có thể giữ session cục bộ.
- Workload hoặc API key từng do nhân viên quản lý có thể tiếp tục tồn tại.

### 16.1. Vấn đề “token còn hạn”

Giả sử Bình có JWT access token hết hạn 17:30; Bình nghỉ việc lúc 17:00. Nếu RS chỉ kiểm tra chữ ký và `exp`, token có thể còn được chấp nhận trong khoảng đến 17:30 dù account đã bị disable ở IdP.

Điều này không chứng minh RS làm sai một profile JWT, mà là **thiết kế lifecycle chưa đáp ứng thời gian thu hồi quyền mong muốn** nếu chính sách yêu cầu chặn ngay.

Giải pháp tùy nền tảng gồm:

- Access token ngắn hạn với TTL tương xứng rủi ro.
- Introspection hoặc revocation/status checks đối với API nhạy cảm.
- Kiểm tra trạng thái account/entitlement hiện hành trong authorization.
- Token binding để giảm khả năng tái sử dụng token bị đánh cắp.
- Chấm dứt session và refresh token nhằm chặn tạo credential mới.
- Cơ chế khóa khẩn cấp hoặc containment tại gateway/API khi có sự cố.

### 16.2. Không nhầm các trạng thái

| Trạng thái | Điều đã đạt | Điều chưa tự bảo đảm |
|---|---|---|
| `IDP_DISABLED` | Đường xác thực/cấp token mới qua IdP được chặn theo cấu hình | Access token, session hoặc local login cũ đã mất hiệu lực |
| `SCIM_USER_INACTIVE` | Account đích đã được cập nhật theo provider | Tất cả session/API key/role local đã thu hồi |
| `REFRESH_TOKEN_REVOKED` | Client không dùng refresh token bị thu hồi để lấy token mới | Access token cũ đã hết hạn |
| `JWT_EXPIRED` | JWT đó không còn hợp lệ theo `exp` | Mọi credential khác đã hết |
| `RESOURCE_ACCESS_DENIED` | Một thử nghiệm được RS chặn | Mọi endpoint/tenant/đường credential khác cũng bị chặn |
| `VERIFIED_DEPROVISIONED` | Có bằng chứng trạng thái các target theo tiêu chí đóng | Chỉ đúng với phạm vi và thời điểm kiểm tra đã định nghĩa |

### 16.3. Deprovisioning thất bại ở RS

Khi IAM gửi lệnh gỡ role nhưng backend vẫn cho phép thao tác, cần điều tra:

1. RS đang dùng token cũ có claim quyền trước Mover/Leaver?
2. Quyền còn từ một group lồng nhau hoặc direct grant?
3. Policy cache có TTL quá dài?
4. API đang thiếu kiểm tra status hoặc object-level permission?
5. Connector SCIM có cập nhật đúng account ID không?
6. Một client khác đang dùng service account/API key độc lập?
7. Gateway đã cập nhật nhưng service nội bộ có đường bypass?

Không đóng ticket chỉ vì lệnh revoke trả HTTP 200. Readback và kiểm thử quyền trên tài nguyên phải phù hợp mức rủi ro và quyền thực hiện.

## 17. Service account, workload và app-only access

Một Resource Server có thể nhận access token không đại diện cho người dùng tương tác. Với **Client Credentials**, token biểu diễn quyền đã được AS cấp cho client/service principal theo hợp đồng.

Ví dụ một job `report-generator` cần quyền đọc thống kê:

| Thành phần | Ví dụ minh họa | Kiểm soát |
|---|---|---|
| Workload principal | `svc-report-generator-prod` | Owner rõ, không dùng chung tài khoản nhân viên |
| Authorization method | Client Credentials + client authentication mạnh | Secret/khóa/chứng chỉ/federation được bảo vệ |
| Target audience | `reporting-api` | Không dùng token cho billing API |
| Scope | `report.aggregate.read` | Chỉ cho chức năng cần thiết |
| Allowed dataset | Tenant/report đã duyệt | API kiểm tra tài nguyên thực |
| Credential lifecycle | Rotation/expiry/revoke | Không giữ secret tĩnh vô thời hạn |
| Audit | Client ID và workload context | Không gắn nhầm thành hành động của nhân viên |

### 17.1. Không nhầm client authentication với xác thực user

Một client có thể chứng minh danh tính bằng mTLS, private-key JWT hoặc cơ chế client authentication khác. Điều đó không chứng minh có một người dùng đã qua MFA. Nếu API được gọi theo **delegated user**, cần flow và claims phù hợp, không tự biến app-only token thành user token.

### 17.2. Không tự nâng quyền từ danh tính dịch vụ

Một service principal có quyền `report.aggregate.read` không nên được phép gọi endpoint `user.delete` chỉ vì nó hoạt động trong cùng cluster. Least privilege cần áp dụng cả với **máy với máy**.

### 17.3. JML cho workload

- **Joiner:** đăng ký principal, owner, audience, scope, trust và giới hạn credential.
- **Mover:** dịch vụ đổi môi trường/API/owner, đánh giá quyền cũ và quyền mới, tránh chồng lấn quá hạn.
- **Leaver:** thu hồi secret/khóa, access grants, trust bindings, client registration và role; xác minh ở AS và RS.

Khi một kỹ sư nghỉ việc, không xóa mọi workload đang chạy chỉ vì họ từng là owner. Tổ chức cần **bàn giao ownership**, thu hồi credential cá nhân và xử lý service principal theo nhu cầu nghiệp vụ.

## 18. Vận hành: hiệu năng, JWKS, introspection và lỗi phụ thuộc

Resource Server phải bảo vệ API nhưng cũng phải duy trì khả năng phục vụ ổn định.

### 18.1. JWKS rotation và caching

Với JWT, AS thường công bố khóa công khai qua JWKS theo hợp đồng. RS cần:

- Pin issuer và nguồn JWKS hợp lệ theo cấu hình.
- Cache khóa có giới hạn và làm mới theo chính sách.
- Xử lý `kid` mới an toàn khi AS luân chuyển khóa.
- Không cho header từ token đưa RS đến URL JWKS không được tin.
- Có cơ chế loại khóa hết hạn/thu hồi, tránh giữ trust quá lâu.
- Giám sát lỗi xác minh chữ ký sau khi rotation.

Nếu khóa mới chưa được phân phối, RS có thể từ chối token hợp lệ tạm thời. Cần rollout có kế hoạch giữa AS và RS; **không giải quyết bằng việc tắt chữ ký**.

### 18.2. Introspection và sự cố mạng

Khi introspection bị gián đoạn:

- Tách lỗi xác thực token khỏi lỗi kết nối AS để log/giám sát.
- Áp dụng timeout, circuit breaker/retry có giới hạn và quota phù hợp.
- Đặt mức cache TTL dựa trên chính sách; không tự kéo dài hạn token.
- Với tài nguyên nhạy cảm, không cho token chưa xác minh đi qua chỉ để giữ “uptime”.
- Trả lỗi máy chủ/thử lại khi hệ thống không thể xác minh, thay vì công bố token chắc chắn sai nếu bằng chứng không đủ.

### 18.3. Độ mới của policy

Ngay cả khi JWT hợp lệ, dữ liệu quyền có thể chậm thay đổi. Mỗi quyết định cần xác định chính sách lấy từ đâu và được cache bao lâu.

Ví dụ, API quản trị production có thể yêu cầu kiểm tra role/approval gần thời điểm thao tác, trong khi endpoint đọc bản tin nội bộ dùng thông tin session/cache theo khoảng thời gian dài hơn. Không có TTL duy nhất phù hợp mọi tài nguyên.

### 18.4. Clock skew và time validation

Một độ lệch đồng hồ nhỏ có thể cần được cho phép theo policy khi kiểm tra `exp`/`nbf`, nhưng không được mở cửa sổ lớn đến mức token hết hạn vẫn được chấp nhận quá lâu. Hệ thống phải đồng bộ thời gian và giám sát bất thường.

## 19. Kiểm toán và observability của Resource Server

Một RS cần có thể giải thích **vì sao cho phép hoặc từ chối một request** mà không làm lộ token/dữ liệu nhạy cảm.

| Trường/nhóm | Công dụng | Lưu ý |
|---|---|---|
| Correlation/request ID | Ghép request qua client, gateway, API và IAM | Không dùng token làm ID |
| API/resource/action | Xác định thao tác được yêu cầu | Tránh log payload dữ liệu nhạy cảm |
| Trusted issuer, audience | Theo dõi nguồn credential và API nhận | Không ghi dữ liệu user không cần thiết |
| Principal ID / client ID | Truy dấu user/app đúng loại | Dùng định danh chuẩn hoặc pseudonym theo policy |
| Token reference / `jti` khi phù hợp | Hỗ trợ điều tra và revoke theo thiết kế | Không log access token nguyên dạng |
| Policy version | Giải thích RBAC/ABAC/SoD đã xét | Cần versioning có owner |
| Decision/result | ALLOW, DENY, STEP_UP hoặc lỗi xác minh | Phân biệt 401/403, policy denial, system failure |
| Tenant/resource scope | Phát hiện truy cập chéo tenant | Giảm log dữ liệu cá nhân theo mục đích |
| Auth context/device risk | Giải thích yêu cầu bảo đảm | Chỉ từ nguồn đã tin cậy và cần thiết |
| Lifecycle event | Liên hệ với Joiner/Mover/Leaver | Phát hiện truy cập sau thời điểm kết thúc |

Ví dụ JSON **minh họa**, không phải schema chuẩn:

~~~json
{
  "requestId": "req-billing-2026-0005",
  "resourceServer": "billing-api",
  "action": "invoice.read",
  "resourceRef": "invoice-ref-2048",
  "trustedIssuer": "corp-tenant-a",
  "audience": "billing-api",
  "principalType": "USER",
  "principalRef": "employee-1042",
  "tenantRef": "tenant-a",
  "authorizationPolicy": "billing-rbac-abac-v8",
  "lifecycleState": "ACTIVE",
  "decision": "ALLOW",
  "verifiedAt": "2026-11-23T09:00:00+07:00",
  "correlationId": "IAM-ACCESS-5005"
}
~~~

Nếu request bị từ chối do JWT không hợp lệ, có thể log một mã lỗi phân loại **mà không** ghi token, public claim không cần thiết hoặc mật khẩu. Audit phải có cơ chế bảo vệ quyền xem/chỉnh sửa, retention và phát hiện can thiệp phù hợp.

### 19.1. Những chỉ số đáng theo dõi

- Tỷ lệ 401 do thiếu/sai token, phân biệt lỗi tích hợp và hành vi bất thường.
- Tỷ lệ 403 thiếu scope/role/tenant, theo endpoint và mức rủi ro.
- Số request dùng token có audience sai hoặc issuer chưa được phê duyệt.
- Độ trễ xác minh JWT/introspection và tỷ lệ lỗi phụ thuộc AS/JWKS.
- Request nhạy cảm sau sự kiện Mover/Leaver, so với quyền kỳ vọng tại thời điểm đó.
- Số kết quả authorization từ cache đã quá độ mới chính sách.
- Số service principal/API token không có owner hoặc đã quá hạn.
- Tỷ lệ đối soát deprovisioning tại RS thành công có bằng chứng.

Không coi mọi 401/403 là tấn công. Chúng cũng có thể phát sinh từ user không được cấp quyền hợp lệ, token đã hết hạn bình thường hoặc cấu hình ứng dụng chưa đúng.

## 20. Những lỗi bảo mật phổ biến tại Resource Server

| Lỗi thiết kế | Ví dụ | Cách phòng tránh |
|---|---|---|
| Chấp nhận ID token như API access token | Web client gửi ID token để đọc hóa đơn | Phân biệt loại token và audience, xác minh profile |
| Bỏ kiểm tra audience | Token của CRM được dùng gọi billing API | API kiểm tra `aud` chính xác |
| Tin mọi issuer cùng vendor | Tenant bên ngoài phát JWT hợp lệ | Allowlist issuer/tenant cụ thể |
| Decode JWT mà không verify | Dùng claim `role=admin` chưa kiểm chữ ký | Thư viện xác minh đáng tin và cấu hình algorithm/key |
| Tin claims từ client | Header `X-Role: admin` | Trust boundary bảo vệ, không lấy quyền từ client tự khai |
| Chỉ kiểm tra scope | `invoice.read` cho phép xem hóa đơn mọi tenant | Object-level authorization theo tenant/owner |
| Chỉ ẩn nút UI | API approve không có authorization | Enforcement tại server/API |
| Token quá dài hạn | Mover đã thu quyền nhưng JWT cũ còn nhiều giờ | TTL phù hợp, revocation/status checks theo rủi ro |
| Introspection fail-open | AS lỗi mạng → cho phép mọi bearer token | Fail-closed cho tài nguyên được bảo vệ |
| Dùng group/role đã lỗi thời | IdP gỡ group nhưng RS vẫn tin cache cũ | Policy freshness, readback và kiểm soát phiên |
| Bỏ qua DPoP/mTLS proof | Chấp nhận sender-constrained token như bearer thường | Verify binding và proof/chứng chỉ |
| Truyền token qua URL/log | Log proxy chứa access token | Authorization header/TLS, che dữ liệu |
| Tự chuyển tiếp token nhiều API | Billing token đi đến reporting API | Audience riêng, token exchange khi được phép |
| App-only token được xem như user token | Service identity có “user admin” role | Phân biệt principal type và scopes |
| Quên quyền cũ sau Leaver | API vẫn cho truy cập bằng token/session cũ | Deprovisioning và kiểm tra quyền hiệu lực |

### 20.1. Một token không phải chứng chỉ “đáng tin mãi”

RS phải biết token có còn phù hợp **tại thời điểm request**. Signature hợp lệ không chứng minh người dùng hiện active, môi trường vẫn compliant, role chưa thu hồi hay dữ liệu yêu cầu thuộc quyền.

### 20.2. Authorization phải chống cả thiếu quyền và vượt quyền

Từ chối toàn bộ request hợp lệ gây gián đoạn; cho phép request vượt quyền gây rò rỉ. Kiểm thử nên bao phủ cả hai hướng: **positive tests** cho hành vi đúng và **negative tests** cho token/quyền sai.

## 21. Case study: API hóa đơn qua ba giai đoạn JML

### 21.1. Joiner — được phép đọc hóa đơn Hà Nội

Nhân viên Mai gia nhập bộ phận kế toán chi nhánh Hà Nội. HRIS xác nhận identity và ngày hiệu lực. IAM/IdP cấp account, xác thực phù hợp và role `billing.viewer` trong tenant của công ty.

Khi Mai dùng web client gọi `GET /v1/invoices/INV-HN-01`:

1. AS phát access token với audience `billing-api` và scope `invoice.read` theo policy.
2. RS xác minh token hợp lệ, issuer/tenant được chấp nhận, thời hạn và binding nếu có.
3. RS kiểm tra `billing.viewer`, tenant và region của hóa đơn.
4. API chỉ trả những trường dữ liệu Mai được phép xem.

**Negative test:** đổi invoice ID sang hóa đơn Đà Nẵng phải bị từ chối hoặc không tiết lộ theo policy dù token không đổi.

### 21.2. Mover — chuyển sang Đà Nẵng

Mai chuyển chi nhánh. IAM cập nhật `region=DN`, role/group và quyền theo ngày hiệu lực, đồng thời thu hồi quyền Hà Nội.

Nếu token cũ vẫn chứa HN, RS phải áp dụng chiến lược đã thiết kế: token ngắn hạn, kiểm tra entitlement mới hoặc cơ chế invalidation/revocation. Không chỉ thêm group DN và để Mai xem cả hai chi nhánh mãi.

**Negative test:** token/phiên cũ không được tiếp tục mở dữ liệu HN trái chính sách sau thời điểm phải thu hồi theo SLA đã cam kết.

### 21.3. Leaver — kết thúc quyền trên API

Mai nghỉ việc. IdP khóa đăng nhập mới, provisioning engine vô hiệu hóa account ở ứng dụng đích, thu hồi group/role và xử lý session/credential.

RS phải có cơ chế chặn quyền sau thời điểm hiệu lực phù hợp risk policy; nếu chưa thể kiểm chứng ngay, workflow phản ánh `PENDING_VERIFICATION` hoặc `PARTIAL`, không đánh dấu hoàn tất.

**Negative test:** request dùng token còn hạn hoặc một phiên cũ vẫn phải bị xử lý theo chính sách Leaver, không được âm thầm giữ quyền chỉ vì signature JWT đúng.

### 21.4. Một workload vẫn hoạt động

Job `invoice-reporting-prod` phục vụ công ty có owner nghiệp vụ và service principal riêng. Khi Mai nghỉ việc, **không tự xóa service principal chỉ vì Mai từng quản lý job**. Cần bàn giao owner, thu hồi credential riêng của Mai và đánh giá vòng đời workload độc lập.

## 22. Ma trận kiểm thử cho Resource Server

| Tình huống | Kết quả cần kiểm tra |
|---|---|
| Không gửi access token | 401 hoặc xử lý theo hợp đồng bảo vệ endpoint |
| JWT giả mạo chữ ký | Từ chối |
| `alg`/key không được chấp thuận | Từ chối |
| Issuer lạ hoặc tenant ngoài allowlist | Từ chối |
| Audience của API khác | Từ chối |
| Gửi ID token thay access token | Từ chối |
| Token hết hạn hoặc chưa có hiệu lực | Từ chối |
| Token thiếu scope phù hợp | 403 |
| Có scope nhưng thiếu role | 403 |
| Có role nhưng truy cập hóa đơn khác tenant | Từ chối; không rò rỉ dữ liệu |
| User bị disable sau Leaver | Chặn theo policy thu hồi và thời hạn yêu cầu |
| Role bị hạ sau Mover | Không được thực hiện quyền cũ sau thời điểm cần thu hồi |
| Token app-only yêu cầu endpoint user-only | Từ chối nếu không hỗ trợ app-only |
| Token yêu cầu DPoP nhưng thiếu/sai proof | Từ chối theo profile DPoP |
| mTLS-bound token với chứng chỉ khác | Từ chối |
| Introspection trả `active=false` | Từ chối |
| Introspection/JWKS unavailable | Xử lý an toàn theo chính sách, không fail-open |
| Gateway đã xác minh nhưng backend bị gọi trực tiếp | Backend không tin header giả |
| Group/claim role không nhận diện được | Không tự cấp admin |
| SCIM đã gỡ user nhưng direct grant còn | Phát hiện/thu hồi đường quyền tồn dư |
| BFF gọi API downstream với audience sai | Không bỏ qua audience; chọn luồng token phù hợp |
| Token cũ mang tenant/region trước Mover | Không vượt quyền theo policy hiện hành |
| Scope hợp lệ, object thuộc quyền, account active | Cho phép đúng dữ liệu và audit phù hợp |

Thử nghiệm cần dùng tài khoản/test resource được cấp phép, không gửi token thật lên công cụ ghi log công khai. Với quyền dữ liệu nhạy cảm, test quyền nên kiểm tra **hành vi thực tế của API**, không chỉ inspection của token.

## 23. Checklist triển khai Resource Server

Khi xây dựng hoặc kiểm tra một API nhận OAuth access token:

1. **Xác định RS:** API nào đang bảo vệ tài nguyên gì, ai là owner và mức độ nhạy cảm?
2. **Định nghĩa trust:** chỉ issuer/tenant/authorization server nào được chấp nhận?
3. **Token type:** hỗ trợ JWT, opaque, bearer hay sender-constrained theo profile nào?
4. **Signature và keys:** JWT có xác minh thuật toán, chữ ký, issuer và JWKS từ nguồn tin cậy?
5. **Audience:** access token có đúng `aud` của API, không dùng ID token hoặc token dành cho API khác?
6. **Lifetime:** kiểm tra `exp`, `nbf`, độ lệch thời gian và trạng thái phù hợp?
7. **Introspection:** nếu dùng opaque token, kênh xác minh có bảo vệ, cache và retry an toàn?
8. **Proof-of-possession:** DPoP/mTLS có được kiểm tra đầy đủ khi token yêu cầu binding?
9. **Scopes:** API có mapping rõ hành động nào yêu cầu scope nào?
10. **RBAC/ABAC:** quyền trên tenant, region, object, owner, SoD có được xét ở server?
11. **Principal type:** phân biệt delegated user và app-only client, không gộp role?
12. **SSO/OIDC:** không dùng ID token làm token gọi API; auth context có hợp đồng rõ?
13. **SCIM:** có phân biệt provisioning tài khoản/nhóm với kiểm tra quyền runtime tại RS?
14. **Joiner:** role/entitlement có hiệu lực đúng thời điểm và có positive/negative tests?
15. **Mover:** quyền cũ, group, claim trong token/cache được xử lý và kiểm chứng?
16. **Leaver:** chặn đăng nhập mới, token/session còn hạn và quyền ở target theo SLA rủi ro?
17. **Backend/gateway:** không có đường bypass và không tin header do client giả mạo?
18. **Multi-tenant:** kiểm tra issuer namespace, tenant và object-level ownership?
19. **Workload:** service principal có audience/scope/owner, credential rotation và deprovision?
20. **Observability:** có metric 401/403, validation failures, stale policy, post-Leaver access?
21. **Audit:** không log token/secret; lưu event, policy version, kết quả authorization và correlation?
22. **Sự cố:** nếu AS/JWKS/introspection không khả dụng, có fail-safe và escalation phù hợp?
23. **Readback:** có thể xác minh quyền hiệu lực tại RS thay vì chỉ tin lệnh IAM đã gửi?

---

**Ghi nhớ:** **Resource Server là nơi bảo vệ tài nguyên và thực thi quyết định truy cập của API** trong OAuth 2.0. Nó phải xác minh access token đúng issuer, audience, thời hạn, kiểu token và bằng chứng ràng buộc nếu áp dụng; sau đó kiểm tra **scope kết hợp RBAC/ABAC và quyền trên tài nguyên thực tế**. OIDC giúp xác thực người dùng, SCIM giúp provisioning danh tính và nhóm, nhưng cả hai **không thay thế authorization tại RS**. Khi kết nối kiểm soát RS với **Joiner–Mover–Leaver**, cơ chế cập nhật/thu hồi token, session, quyền và audit/readback, hệ thống mới giảm được nguy cơ cấp quyền quá rộng và **quyền truy cập tồn dư**.
