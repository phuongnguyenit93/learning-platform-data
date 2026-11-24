# Access token trong OAuth 2.0, OIDC và IAM Identity Lifecycle

## 1. Access token là gì?

**Access token** là thông tin xác thực ủy quyền được **Authorization Server (AS)** cấp cho một client để truy cập tài nguyên được bảo vệ tại **Resource Server (RS)**, trong phạm vi và điều kiện mà hệ thống chấp nhận. Trong OAuth 2.0, token là công cụ để client trình bày quyền truy cập mà không cần gửi trực tiếp mật khẩu người dùng cho từng API.

Ví dụ, Lan đăng nhập vào cổng doanh nghiệp qua Identity Provider (IdP). Ứng dụng bảng điều khiển được cấp một access token cho API báo cáo. Khi gọi API, ứng dụng trình token; API kiểm tra token có do nguồn tin cậy phát hành, dành cho đúng API, còn hiệu lực và đủ quyền cho thao tác hay không.

**Access token không phải mật khẩu, không phải hồ sơ danh tính, không phải một vai trò RBAC, và cũng không phải bằng chứng độc lập rằng người dùng đã được identity proofing.** Nó là một credential có thời hạn để thực hiện một phạm vi truy cập. Đối với bearer token, bất kỳ bên nào nắm token còn hợp lệ đều có nguy cơ sử dụng token trong phạm vi được cấp.

Bài thuộc chương **OAuth và OIDC** của mô-đun **SECURITY_IDENTITY_ACCESS_MANAGEMENT_IDENTITY_LIFECYCLE**. Nội dung liên hệ access token với **Joiner–Mover–Leaver (JML)**, xác minh và enrollment, **IdP/SSO, SCIM provisioning, RBAC/ABAC, service account, kiểm toán** và nguy cơ **quyền truy cập tồn dư** sau khi thay đổi quan hệ công việc.

### Những câu hỏi cốt lõi

1. **Ai cấp token?** Authorization server/issuer có thuộc danh sách tin cậy không?
2. **Cấp cho ai?** Client nào nhận token và có/không có người dùng đứng sau?
3. **Dùng ở đâu?** Resource server/audience nào được phép chấp nhận?
4. **Dùng để làm gì?** Scope, entitlement và điều kiện nghiệp vụ nào được áp dụng?
5. **Có hiệu lực khi nào?** Thời gian hết hạn, trạng thái thu hồi và quy tắc phiên ra sao?
6. **Ai có thể sử dụng?** Token là bearer hay ràng buộc với khóa/chứng chỉ của bên sử dụng?
7. **Khi JML thay đổi, truy cập có còn hợp lệ không?** Các phiên và token đã phát phải được xử lý thế nào?

## 2. Các vai trò trong OAuth 2.0 và ranh giới tin cậy

OAuth 2.0 tách một số vai trò, không đồng nhất chúng với một máy chủ duy nhất:

| Vai trò | Chức năng | Ví dụ trong doanh nghiệp |
|---|---|---|
| **Resource Owner** | Chủ thể có quyền cho phép truy cập tài nguyên, theo mô hình grant phù hợp | Nhân viên hoặc chủ sở hữu dữ liệu, tùy kịch bản |
| **Client** | Ứng dụng xin token và sử dụng token gọi API | Web frontend với backend, mobile app, batch job |
| **Authorization Server** | Xác thực/áp chính sách và phát token theo grant hợp lệ | Nền tảng IAM/IdP có OAuth server |
| **Resource Server** | API hoặc dịch vụ kiểm tra token và quyền | API nhân sự, CRM, billing, gateway |
| **Identity Provider / OpenID Provider** | Xác thực danh tính và có thể cung cấp OIDC ID token | Hệ thống SSO doanh nghiệp |

Một nhà cung cấp có thể đồng thời là IdP và authorization server, nhưng đây là **vai trò logic khác nhau**. Một access token của API nhân sự **không mặc nhiên hợp lệ** với API tài chính, kể cả cả hai ứng dụng đều dùng chung IdP.

~~~mermaid
flowchart LR
    H[HRIS / JML] --> IAM[IAM / IGA]
    IAM --> AS[IdP / Authorization Server]
    U[Người dùng] --> C[Client App]
    C -->|Xin token qua grant| AS
    AS -->|Access token| C
    C -->|Access token + API request| RS[Resource Server]
    RS -->|Xác minh token và policy| POL[RBAC / ABAC / trạng thái]
    IAM --> PROV[SCIM / Provisioning]
    PROV --> RS
    RS --> LOG[Audit / Reconciliation]
    AS --> LOG
~~~

**Luồng access token và luồng provisioning là hai cơ chế khác nhau.** OAuth chuyển quyền truy cập theo phiên/token; SCIM hoặc connector tạo/cập nhật/vô hiệu hóa account và group ở hệ thống đích. Thành công một phía không chứng minh phía còn lại đã hoàn tất.

## 3. Access token khác ID token, refresh token và session cookie

Trong hệ sinh thái OAuth 2.0 / OpenID Connect (OIDC), một người dùng có thể gặp nhiều đối tượng gọi chung là “token”, nhưng mỗi đối tượng có mục đích và đối tượng nhận khác nhau.

| Đối tượng | Người nhận/sử dụng chính | Mục đích | Không nên làm |
|---|---|---|---|
| **Access token** | **Resource Server** / API | Cho phép truy cập tài nguyên theo scope và policy | Dùng như bằng chứng đăng nhập dành cho RP khi không có OIDC validation |
| **OIDC ID token** | **Relying Party (OIDC client)** | Chuyển thông tin về sự kiện xác thực và subject | Gửi làm bearer access token cho API |
| **Refresh token** | Client được cấp hợp lệ | Yêu cầu access token mới khi chính sách cho phép | Gửi đến resource server như API credential |
| **Session cookie** | Trình duyệt và ứng dụng/IdP | Duy trì phiên theo chính sách cục bộ | Coi cookie ứng dụng và phiên IdP luôn cùng sống/chết |
| **API key** | Tích hợp cụ thể | Bí mật truy cập theo cơ chế riêng | Mặc nhiên xem là OAuth access token hoặc tự động hết hạn theo JML |
| **SAML assertion** | SAML Service Provider | Federation kết quả xác thực và thuộc tính | Trình trực tiếp cho OAuth API như bearer token nếu không có thiết kế chuyển đổi hợp lệ |

**OIDC không đồng nghĩa access token là ID token.** Khi một client dùng OIDC để đăng nhập, **ID token dành cho client**; còn API cần access token được phát **cho chính API đó** với policy tương ứng. Không được suy diễn an toàn chỉ từ việc hai token đều có hình thức JWT.

### Một ví dụ nhận nhầm token

Ứng dụng A nhận ID token có audience là client A. Nếu API B chỉ kiểm tra chữ ký của cùng issuer rồi chấp nhận ID token đó, API B đã bỏ qua **mục đích và audience**. Kẻ có ID token có thể sử dụng nó sai nơi nhận. Resource server cần xác minh **token dùng cho tài nguyên này**, không đơn thuần “do IdP ký”.

## 4. Access token được phát hành bằng cách nào?

Client không tự tạo token hợp lệ cho API chỉ bằng cách sinh một chuỗi. Nó phải đi qua **authorization grant** và được authorization server chấp nhận. Loại grant phụ thuộc việc có người dùng hay không và đặc điểm ứng dụng.

### 4.1. Authorization Code Flow với PKCE

Đối với nhiều ứng dụng có người dùng tương tác, **Authorization Code Flow với PKCE** là phương pháp được ưu tiên trong thiết kế OAuth hiện đại. Tóm tắt:

1. Client tạo yêu cầu authorization với client ID, redirect URI đã đăng ký, scope phù hợp, **state** và **PKCE code challenge**.
2. Trình duyệt đến authorization server; người dùng xác thực, thực hiện MFA hoặc nhận màn hình consent khi cần.
3. Authorization server trả **authorization code** ngắn hạn về redirect URI hợp lệ.
4. Client gửi code và **code verifier** tương ứng đến token endpoint; client bí mật còn cần xác thực theo kiểu client tương ứng nếu áp dụng.
5. Authorization server kiểm tra grant, client, redirect URI, PKCE và policy rồi cấp access token cho resource được phép.
6. Client dùng access token gọi đúng resource server; API kiểm tra token và quyền truy cập.
7. Access token hết hạn hoặc bị thu hồi theo cơ chế hỗ trợ; client có thể lấy token mới bằng quy trình hợp lệ.

~~~mermaid
sequenceDiagram
    participant U as Người dùng
    participant C as Client App
    participant AS as Authorization Server
    participant RS as Resource Server
    U->>C: Mở ứng dụng
    C-->>U: Redirect với state và PKCE challenge
    U->>AS: Yêu cầu authorization
    AS->>AS: Xác thực, MFA và chính sách
    AS-->>U: Authorization code + state
    U->>C: Callback trên redirect URI hợp lệ
    C->>AS: Token request: code + code_verifier
    AS-->>C: Access token và dữ liệu liên quan
    C->>RS: API request + access token
    RS->>RS: Verify token, audience, scope và policy
    RS-->>C: Kết quả theo quyền
~~~

**PKCE không thay thế kiểm tra state, redirect URI, issuer hoặc việc bảo vệ token sau khi cấp.** Nó chủ yếu giúp ràng buộc authorization code với client khởi tạo. Với ứng dụng public client, không nên cố coi một client secret nhúng trong mã mobile hoặc JavaScript là bí mật an toàn.

### 4.2. Client Credentials Grant cho máy–máy

Một batch job hoặc backend có thể lấy token **đại diện cho chính client** bằng **client credentials**, nếu authorization server cho phép và client được xác thực phù hợp. Không có người dùng tương tác trong grant này; vì vậy đừng gán tùy tiện một employee ID làm chủ thể chỉ vì nhân viên đó quản lý job.

~~~mermaid
sequenceDiagram
    participant W as Workload / Client
    participant AS as Authorization Server
    participant API as Resource Server
    W->>AS: Client credentials được xác thực
    AS-->>W: Access token cho API và scope được duyệt
    W->>API: Authorization bearer hoặc proof phù hợp
    API->>API: Validate token và chính sách workload
    API-->>W: Kết quả API
~~~

Trong nhiều triển khai **client credentials không có refresh token**; khi access token hết hạn, workload tiếp tục xác thực client để xin token mới. Không nên coi token của workload là “phiên SSO của nhân viên”.

### 4.3. Những grant và mô hình khác

**Token exchange**, **device authorization** hoặc các luồng uỷ quyền thích hợp có thể được dùng trong kiến trúc phân tán. Tuy nhiên, **mỗi token mới cần có audience, scope, chủ thể và nguồn gốc uỷ quyền rõ ràng**. Không truyền access token dành cho API A trực tiếp qua mọi service khác nếu API đó không phải audience được phép.

Các kiểu triển khai cũ như **Implicit Grant** hoặc **Resource Owner Password Credentials** không nên được chọn làm mặc định cho hệ thống mới; chúng có những hạn chế bảo mật quan trọng và không phù hợp với thực hành an toàn hiện đại.

## 5. Bearer token và sender-constrained token

### 5.1. Bearer token

Với **bearer access token**, một bên trình đúng token còn hợp lệ có thể yêu cầu quyền trong phạm vi token. API không nhất thiết biết token đến từ đúng tiến trình ban đầu được cấp.

Ví dụ HTTP minh họa:

~~~http
GET /api/v1/reports/quarterly HTTP/1.1
Host: reports.example.org
Authorization: Bearer <REDACTED_ACCESS_TOKEN>
Accept: application/json
~~~

Giá trị token thực không được đưa vào tài liệu, ảnh chụp, ticket hoặc log. **HTTPS/TLS** giúp bảo vệ token trên đường truyền, nhưng không ngăn token bị lấy từ browser storage, log, máy chủ hoặc endpoint đã bị chiếm.

### 5.2. Sender-constrained token

Một **sender-constrained access token** được liên kết với một khóa hoặc chứng chỉ, nên resource server yêu cầu cả **token** lẫn **bằng chứng bên trình token đang nắm khóa thích hợp**.

Hai cơ chế thường được nhắc tới:

| Cơ chế | Ý tưởng | Điều kiện vận hành |
|---|---|---|
| **mTLS sender-constrained tokens** | Ràng buộc access token với chứng chỉ client tại kênh TLS | Client và API/gateway phải quản lý TLS client certificates, kiểm tra binding |
| **DPoP – Demonstration of Proof-of-Possession** | Client ký proof bằng khóa bất đối xứng, API xác minh proof và binding của token | Cần xử lý phương thức/URI, thời gian, replay, nonce khi áp dụng và key binding |

DPoP thường gồm một proof JWT có ràng buộc đến **HTTP method/URI**, thời điểm, định danh chống phát lại và dấu vết token (tùy ngữ cảnh), chứ không phải chỉ gắn một header bất kỳ. API phải **thực sự xác minh** proof, token binding và điều kiện replay; có DPoP header nhưng bỏ kiểm tra không tăng bảo mật.

**Sender constraint giúp giảm rủi ro phát lại token bị đánh cắp**, nhưng không ngăn hoàn toàn mã độc có thể ra lệnh cho client hợp lệ ký proof hoặc sử dụng phiên đang hoạt động. Việc lưu và bảo vệ khóa client vẫn là vấn đề quan trọng.

## 6. JWT access token và opaque access token

OAuth 2.0 **không bắt buộc mọi access token có hình thức JWT**. Token có thể được phát ở dạng opaque hoặc dạng có cấu trúc. Resource server phải hiểu và xử lý theo **hợp đồng của issuer**, không đoán chỉ từ dấu chấm trong chuỗi.

| Tiêu chí | JWT access token | Opaque access token |
|---|---|---|
| Hình thức | Chuỗi có cấu trúc, thường là JWT đã ký | Chuỗi không mang ý nghĩa trực tiếp với resource server |
| Cách kiểm tra | Có thể xác minh cục bộ chữ ký và claim theo trust config | Thường dùng token introspection hoặc backend tra cứu tin cậy |
| Ưu điểm | Ít phụ thuộc truy vấn runtime nếu đủ dữ liệu để quyết định | Dễ tập trung trạng thái hiệu lực/thu hồi tại AS |
| Rủi ro | Token còn hợp lệ về chữ ký dù trạng thái nhân sự đã đổi, nếu không có kiểm soát bổ sung | Introspection/cache/đường truyền trở thành phụ thuộc vận hành |
| Thu hồi | Thường cần TTL ngắn, danh sách chặn, kiểm tra trạng thái hoặc cơ chế tương đương | AS có thể cho active=false, nhưng RS phải tra/cập nhật theo policy |
| Độ lộ dữ liệu | Payload JWT dạng mã hóa Base64URL thường đọc được nếu không có JWE | Token opaque không công khai claim cho client, nhưng vẫn là secret |

**JWT được ký (JWS) không có nghĩa payload được mã hóa bí mật.** Phần payload có thể được đọc nếu sở hữu token. Không nhét dữ liệu nhân sự nhạy cảm, secrets hoặc danh sách quyền quá chi tiết vào access token chỉ vì đã có chữ ký.

**Opaque không có nghĩa tự động an toàn hơn**: token vẫn phải khó đoán, được bảo vệ và kiểm tra đúng issuer/resource, trạng thái và quyền.

### JWT access token profile

Trong một số hệ thống, có thể dùng **JWT Profile for OAuth 2.0 Access Tokens** để thống nhất cấu trúc và yêu cầu xử lý. Tuy nhiên, claim bắt buộc/tuỳ chọn phải đối chiếu đúng **profile, phiên bản chuẩn và hợp đồng phát hành**; không phải access token nào có JWT cũng tự tuân thủ một profile cụ thể.

## 7. Đọc cấu trúc một JWT access token

Một JWT thường có **header, payload và signature** dưới dạng Base64URL được phân tách bằng dấu chấm. Chỉ decode header/payload **không phải xác minh token**. Resource server cần xác minh chữ ký với thuật toán và khóa từ nguồn tin cậy, sau đó kiểm tra claim và policy.

Một **payload minh họa** cho access token có cấu trúc:

~~~json
{
  "iss": "https://id.example.org",
  "sub": "person-2046",
  "aud": "https://api.reports.example.org",
  "exp": 1795403100,
  "iat": 1795402500,
  "nbf": 1795402500,
  "client_id": "reports-web",
  "jti": "token-a61b",
  "scope": "reports:read"
}
~~~

Đây là **JSON minh họa claim**, không phải token được ký, không có giá trị truy cập và **không khẳng định mọi issuer đều dùng schema này**.

| Claim | Ý nghĩa thường gặp | Kiểm tra cần thiết |
|---|---|---|
| **iss** | Issuer / nguồn phát token | Phải khớp issuer được cấu hình tin cậy |
| **sub** | Subject / chủ thể, tùy grant | Gắn với account/quan hệ đúng, hoặc đại diện client trong máy–máy theo profile |
| **aud** | Audience / tài nguyên nhận token | Phải chứa đúng API này, tránh token dùng nhầm nơi |
| **exp** | Thời điểm hết hạn | Từ chối khi quá hạn theo chính sách clock skew |
| **nbf** | Không dùng trước thời điểm | Từ chối khi chưa có hiệu lực |
| **iat** | Thời điểm phát hành | Có thể dùng kiểm tra bất thường, giới hạn tuổi token theo policy |
| **scope** | Những phạm vi uỷ quyền được cấp | Không phải bằng chứng duy nhất đủ quyền thao tác mọi đối tượng |
| **client_id** | Client đã nhận token, nếu profile cung cấp | Kiểm tra trong policy khi cần, không suy từ subject |
| **jti** | ID token dùng cho truy vết/chống replay hoặc denylist theo thiết kế | Không mặc nhiên tồn tại hoặc được mọi API xử lý |
| **cnf** | Xác nhận binding tới khóa/chứng chỉ nếu có | Cần kiểm tra proof thực tế, không chỉ đọc claim |

Một số issuer dùng **scp, roles, permissions** hoặc claim tùy chỉnh. Không được tự coi mọi claim có chữ *roles* là quyền đáng tin nếu chưa có **schema và nguồn phát được phê duyệt**.

### Điều không nên ghi vào token

Tránh nhúng **mật khẩu, refresh token, secret, hình ảnh giấy tờ, dữ liệu sức khỏe, lý do chấm dứt hợp đồng, dữ liệu sinh trắc** hoặc metadata nhân sự không cần cho quyết định API. Với các nhu cầu khác, có thể cung cấp thông tin qua API nội bộ có kiểm soát thay vì phát tán cùng mọi request.

## 8. Resource Server phải xác minh access token thế nào?

Đây là bước quan trọng nhất của bài học: **chỉ có token chưa đủ để cho phép thao tác**.

### 8.1. Chuỗi kiểm tra điển hình với JWT

1. **Xác định issuer đáng tin từ cấu hình phía server**, không nhận tùy ý từ header/payload không được tin.
2. **Kiểm tra định dạng và giới hạn kích thước** để ngăn payload bất thường.
3. **Xác minh chữ ký** bằng thuật toán và khóa công khai tương ứng, từ JWKS/metadata có trust binding, với xử lý key rotation.
4. **Chặn thuật toán không được cho phép**, tránh nhầm HS/RS hoặc dùng thuật toán none do dữ liệu đầu vào điều khiển.
5. **Kiểm tra token type/profile** khi hệ thống phân biệt access token với ID token (chẳng hạn header typ theo profile phù hợp).
6. **Xác minh iss và aud**, bảo đảm token được phát từ nguồn tin cậy và dành cho API nhận.
7. **Xác minh exp và nbf**, xử lý clock skew trong biên hạn được chấp nhận.
8. **Kiểm tra scope, client và subject** theo tài nguyên và policy; xác minh trạng thái lifecycle nếu yêu cầu.
9. **Với sender-constrained token**, kiểm tra bằng chứng sở hữu khóa/chứng chỉ và binding tương ứng.
10. **Kiểm tra authorization theo request**, bao gồm tenant, resource ownership, RBAC/ABAC, phê duyệt, time-bound access, SoD và rủi ro.
11. **Ghi audit metadata** không chứa token thô rồi trả kết quả thích hợp.

### Giả mã minh họa

~~~text
function authorizeApiRequest(request):
    token = extractAuthorizationCredential(request)

    if token is absent:
        return UNAUTHENTICATED

    verified = accessTokenVerifier.verify(
        token,
        trustedIssuers = configuredIssuers,
        expectedAudience = thisResourceServer,
        allowedAlgorithms = configuredAlgorithms
    )

    if verified is invalid or verified.expired:
        return UNAUTHENTICATED

    if verified.senderConstrained:
        if not validateProofAndBinding(request, verified):
            return UNAUTHENTICATED

    identity = resolveTrustedSubject(verified)
    if not lifecyclePolicyAccepts(identity, verified.client):
        return FORBIDDEN

    if not authorizationPolicyAllows(
        identity,
        verified.scopes,
        request.tenant,
        request.resource,
        request.action,
        request.context
    ):
        return FORBIDDEN

    return ALLOW
~~~

Đây là **giả mã về nguyên tắc**, không phải middleware bảo mật hoàn chỉnh. Triển khai thực tế cần thư viện được bảo trì, xử lý revocation/introspection, trust policy, rate limiting, cache nhất quán và chống lỗi phân tách tenant.

### 8.2. API gateway và backend phải thống nhất tin cậy

API gateway có thể xác minh token và chuyển **ngữ cảnh đã được xác thực** xuống backend. Nhưng backend không được tin một header do người ngoài tự tạo như user-id hoặc role. Kênh gateway → backend phải được bảo vệ và có cơ chế tin cậy nội bộ phù hợp. Nếu API backend có thể được gọi bỏ qua gateway thì phải tự kiểm tra hoặc chặn đường truy cập đó.

### 8.3. Lỗi authentication và authorization

- **401 Unauthorized** thường cho biết thiếu/không có bằng chứng xác thực hợp lệ.
- **403 Forbidden** thường cho biết có danh tính/phiên phù hợp nhưng không được phép thực hiện thao tác.

Không nên trả quá nhiều chi tiết về token, danh sách role hay cấu hình issuer trong response cho client không tin cậy.

## 9. Opaque token và token introspection

Khi access token là opaque, resource server không thể xác minh claim chỉ bằng cách decode. Nó thường hỏi **authorization server** qua endpoint **token introspection** theo quan hệ tin cậy.

~~~mermaid
sequenceDiagram
    participant C as Client
    participant RS as Resource Server
    participant AS as Authorization Server
    C->>RS: API request + opaque access token
    RS->>AS: Token introspection (client được xác thực)
    AS->>AS: Kiểm tra hiệu lực và thuộc tính token
    AS-->>RS: Trạng thái active và metadata được phép
    RS->>RS: Audience, scope, lifecycle và RBAC/ABAC
    RS-->>C: Kết quả API
~~~

Phản hồi minh họa từ introspection, chỉ để giải thích cấu trúc:

~~~json
{
  "active": true,
  "client_id": "reports-web",
  "token_type": "Bearer",
  "scope": "reports:read",
  "sub": "person-2046",
  "aud": "https://api.reports.example.org",
  "exp": 1795403100
}
~~~

**active=true không tự có nghĩa mọi thao tác đều được phép.** RS còn phải xem audience, scope và quyền nghiệp vụ. Kênh introspection phải có cơ chế xác thực/ủy quyền client, TLS, bảo vệ dữ liệu và giới hạn truy cập tương ứng.

### Caching introspection

Để giảm độ trễ, RS có thể cache kết quả introspection theo chính sách. Đổi lại, **cache làm chậm phản ánh thu hồi**. Với hệ thống nhạy cảm, cần cân nhắc TTL cache, khả năng vô hiệu cache theo sự kiện và yêu cầu cắt quyền khi Leaver. Không thể cùng lúc giả định cache kéo dài hàng giờ và bảo đảm thu hồi ngay tức thì mà không có một cơ chế cập nhật khác.

### Khi AS không khả dụng

Thiết kế phải quyết định **fail closed** hay cách xử lý thay thế dựa trên rủi ro và tính chất ứng dụng. Không được mặc định cho phép mọi request chỉ vì introspection endpoint tạm lỗi.

## 10. Scope, audience, roles và ABAC là các chiều khác nhau

**Scope** diễn tả phạm vi uỷ quyền cấp cho client, ví dụ quyền đọc báo cáo hoặc gửi yêu cầu tới một API. **Audience** chỉ API/tài nguyên nhận token. **Role** thể hiện nhóm quyền nghiệp vụ theo **RBAC**. **ABAC** xét thuộc tính danh tính, tài nguyên và ngữ cảnh.

### Ví dụ

Một token dành cho API báo cáo có:

- audience: reports-api;
- scope: reports:read;
- subject: Lan;
- client: reporting-web.

Lan gửi yêu cầu đọc báo cáo của **phòng Finance**. API vẫn phải kiểm tra **Lan hiện có quyền với báo cáo thuộc Finance hay không**, không chỉ thấy scope reports:read. Nếu Lan là nhân viên bộ phận Sales, scope cho phép chức năng đọc API nhưng **không mặc nhiên cho phép truy cập dữ liệu của Finance**.

| Lớp kiểm soát | Câu hỏi | Ví dụ |
|---|---|---|
| **Audience** | Token được phát cho đúng API này? | reports-api |
| **Scope** | Client được phép làm loại thao tác nào? | reports:read |
| **Identity/lifecycle** | Chủ thể còn quan hệ hợp lệ? | ACTIVE |
| **RBAC** | Chủ thể có vai trò phù hợp? | Finance-Reader |
| **ABAC** | Thuộc tính và ngữ cảnh cho phép? | department=Finance, recordOwner |
| **Resource ownership** | Có được truy cập đối tượng cụ thể? | Báo cáo của đơn vị được phân quyền |
| **SoD/approval** | Có mâu thuẫn phân tách nhiệm vụ hoặc thiếu duyệt? | Không tự phê duyệt giao dịch do chính mình tạo |

**Không nên dùng một scope cực rộng cho mọi API** chỉ vì tiện tích hợp. Điều này làm tăng tác động nếu token bị lộ. Nên yêu cầu token với **scope và audience hẹp**, phân quyền tối thiểu, giới hạn thời hạn và gắn với client phù hợp.

### Tham số resource

Trong OAuth, các triển khai hỗ trợ **Resource Indicators** có thể cho client chỉ định tài nguyên mục tiêu khi xin token. Điều này giúp AS phát token cho đúng audience. Việc AS có hỗ trợ tính năng hay không phải kiểm tra tài liệu/sản phẩm; không tự giả định mọi token endpoint chấp nhận tham số giống nhau.

## 11. Thời hạn token và rủi ro quyền truy cập tồn dư

**Access token thường có hạn sử dụng**. Thời hạn ngắn giúp giới hạn khoảng thời gian token bị đánh cắp hoặc bị giữ lại sau sự kiện JML. Tuy nhiên token ngắn **không thay cho thu hồi** khi yêu cầu cắt truy cập nhanh.

### Vòng đời điển hình

~~~mermaid
stateDiagram-v2
    [*] --> Requested: Client xin token
    Requested --> Issued: Grant và policy hợp lệ
    Requested --> Denied: Không đủ điều kiện
    Issued --> Active: RS chấp nhận token
    Active --> Expired: Quá hạn exp
    Active --> Revoked: AS/RS đánh dấu không được chấp nhận
    Active --> BlockedByPolicy: Lifecycle/permission thay đổi
    Active --> Active: Request hợp lệ tiếp theo
    Expired --> [*]
    Revoked --> [*]
    BlockedByPolicy --> [*]
    Denied --> [*]
~~~

**Lưu ý:** JWT tự chứa vẫn có thể **xác minh chữ ký và còn exp hợp lệ** dù AS đã ghi nhận thu hồi, nếu RS chỉ kiểm tra chữ ký/exp mà không có cơ chế cập nhật. Sơ đồ biểu diễn trạng thái **khả năng chấp nhận theo chính sách**, không có nghĩa mọi hệ thống đều hỗ trợ revocation tức thì.

### Các mốc cần quan sát

- **issuedAt / iat:** thời điểm token được cấp.
- **notBefore / nbf:** thời điểm token bắt đầu được sử dụng, nếu có.
- **expiresAt / exp:** mốc hết hạn.
- **revokedAt:** thời điểm AS/RS ghi nhận thu hồi theo cơ chế triển khai.
- **lastAcceptedAt:** thời điểm RS thực tế chấp nhận token gần nhất nếu logging phù hợp.
- **effectiveAt của Leaver:** mốc mà tổ chức yêu cầu chấm dứt truy cập.

Khoảng thời gian từ **effectiveAt** đến **lần chấp nhận cuối cùng** hoặc đến khi các resource server xác minh đã chặn là một tín hiệu hữu ích cho rủi ro tồn dư, trong giới hạn quan sát của hệ thống.

### Không có một TTL phù hợp cho mọi dịch vụ

API tài chính, thao tác đặc quyền, truy cập dữ liệu nhạy cảm và API đọc thông tin ít rủi ro có thể yêu cầu TTL và cơ chế kiểm tra khác nhau. Cần đánh đổi giữa **rủi ro, hiệu năng, trải nghiệm và khả năng thu hồi**. Không khẳng định một giá trị như 5 hay 60 phút là chuẩn bắt buộc chung.

## 12. Thu hồi access token và những giới hạn cần hiểu

**Revocation** là quyết định làm token không còn được chấp nhận. Trong OAuth có cơ chế **token revocation endpoint** khi được hỗ trợ; cách phát hiện và thực thi quyết định tới resource server phụ thuộc kiến trúc.

| Kiểu token | Cơ chế thực thi thu hồi có thể dùng | Giới hạn |
|---|---|---|
| **Opaque + introspection** | AS báo active=false, RS kiểm tra lại | Cache introspection gây độ trễ |
| **JWT tự chứa** | TTL ngắn, denylist theo ID, lookup trạng thái chủ thể, API gateway, event-driven policy | Chỉ kiểm chữ ký và exp thì không biết quyết định thu hồi mới |
| **Sender-constrained** | Thu hồi token và/hoặc khóa/chứng chỉ ràng buộc | Token binding không tự thay thế lifecycle policy |
| **Refresh token** | Thu hồi ở AS, rotation/reuse detection khi áp dụng | Access token đã cấp có thể vẫn hợp lệ đến khi RS ngăn |
| **App session** | Hủy session/cookie ở RP hoặc thông báo logout | Không tự thu hồi mọi API token độc lập |

### Phân biệt các thao tác

1. **Ngừng cấp token mới:** AS không phát access token mới cho subject/client.
2. **Thu hồi refresh token:** ngăn client tiếp tục làm mới phiên/token theo policy.
3. **Thu hồi access token hiện có:** RS phải nhận được hoặc tự tra được trạng thái thu hồi.
4. **Hủy phiên SSO/ứng dụng:** ảnh hưởng tương tác người dùng, không đồng nhất với mọi API credential.
5. **Thu hồi entitlement hoặc account:** cập nhật RBAC/ABAC, SCIM/API và account thực tế ở đích.
6. **Thu hồi credential máy:** xóa/luân chuyển API key, certificate hoặc client secret có liên quan.

**Chỉ khóa tài khoản IdP không bảo đảm access token tự chứa đã phát lập tức ngừng hoạt động.** Nếu tổ chức cần cắt quyền khẩn cấp, phải thiết kế thêm kiểm soát tại RS/gateway hoặc cơ chế xác thực trạng thái gần thời gian thực.

### Logout và token

Khi người dùng bấm “đăng xuất”, ứng dụng có thể xóa session của mình và chấm dứt quyền dùng refresh token. Nhưng một **access token đã bị sao chép trước đó** có thể vẫn dùng được nếu RS chưa có cơ chế chặn. Không coi thông báo logout đã gửi là bằng chứng mọi access token đã bị vô hiệu.

## 13. Bảo vệ access token trong truyền và lưu trữ

Access token là **credential nhạy cảm**. Dù ở định dạng JWT hay opaque, không nên xuất hiện trong log phổ thông, URL, analytics, email, tài liệu vận hành hoặc mã nguồn.

### Trên đường truyền

- Dùng **HTTPS/TLS** đúng cấu hình ở client, AS, gateway và RS.
- Gửi bearer token trong **Authorization header** theo cơ chế phù hợp, thay vì đặt trong URL query string.
- Chặn việc token bị lộ qua **Referer, browser history, reverse proxy access logs, crash reports** và hệ thống giám sát.
- Không trả token thô trong thông báo lỗi hoặc ticket.
- Không chuyển access token của một audience sang dịch vụ khác ngoài hợp đồng uỷ quyền; nếu cần gọi nhiều API, dùng cơ chế cấp token thích hợp.

### Ở trình duyệt/web app

Ứng dụng browser là môi trường chịu rủi ro **XSS, extension độc hại, thiết bị bị chiếm** và rò rỉ dữ liệu qua thư viện bên thứ ba. Không nên mặc định lưu bearer access token dài hạn trong **localStorage** như một quy tắc chung.

**Backend-for-Frontend (BFF)** có thể giúp giữ access/refresh token ở phía server và để browser sử dụng cookie phiên được bảo vệ. Nếu là SPA không có backend, cần áp dụng mô hình OAuth dành cho browser-based apps, PKCE, TTL, kiểm soát script/XSS và cơ chế lưu token phù hợp với rủi ro; không khẳng định một cơ chế client-side duy nhất là an toàn tuyệt đối.

### Ở mobile và backend

- Dùng **OS secure storage/keystore** khi phù hợp cho ứng dụng di động.
- Với backend, giữ token và client secret trong vùng nhớ/kho secret có kiểm soát; tránh log môi trường và dump dữ liệu nhạy cảm.
- Giới hạn quyền và thời hạn; tách token theo môi trường, ứng dụng và audience.
- Khi dịch vụ tự động cần truy cập, ưu tiên **workload identity, credential ngắn hạn và secret manager** thay cho token tĩnh không rõ owner.
- Khi có nguy cơ token lộ, thu hồi theo khả năng, rà soát session/client/permission và điều tra dấu vết sử dụng.

### Điều access token không chứng minh

Token mạnh không chứng minh endpoint sạch malware, thao tác không bị lừa, user còn trong tổ chức hay request có quyền vào dữ liệu cụ thể. Bảo vệ token là cần thiết nhưng **authorization ở resource server** vẫn phải độc lập.

## 14. Access token phối hợp với IdP, SSO và SCIM thế nào?

Trong IAM, ba chức năng hay bị nhầm là:

- **SSO/OIDC:** IdP xác thực người dùng và cho phép ứng dụng tạo phiên theo federation.
- **OAuth access token:** client được uỷ quyền truy cập API/resource server theo phạm vi.
- **SCIM provisioning:** tạo/cập nhật/vô hiệu hóa user/group và dữ liệu định danh ở hệ thống đích.

### Ví dụ

Lan đăng nhập SSO thành công vào portal. Portal cần đọc báo cáo qua một API. Nó nhận access token hợp lệ cho reports-api và gọi API. Cùng lúc, IAM dùng SCIM đồng bộ nhóm Finance-Reader vào hệ thống báo cáo.

Nếu **SSO thành công** nhưng SCIM chưa cấp nhóm, API có thể trả **403** do chưa đủ quyền. Nếu **SCIM cấp nhóm thành công** nhưng access token sai audience hoặc đã hết hạn, API có thể trả **401**. Nếu cả hai đều đúng nhưng Lan yêu cầu báo cáo của đơn vị khác, chính sách ABAC vẫn có thể từ chối.

### Các lớp phải đánh giá riêng

| Lớp | Kết quả cần kiểm tra |
|---|---|
| **Identity proofing** | Đã xác minh đúng người và nguồn theo mức cần thiết |
| **Enrollment** | Tài khoản/authenticator được liên kết đúng |
| **Authentication** | Phiên xác thực phù hợp, MFA/step-up khi cần |
| **OAuth issuance** | Token cấp đúng client, audience, scope, hạn |
| **Resource server validation** | Token hợp lệ, thuộc nguồn tin cậy, đúng mục đích |
| **RBAC/ABAC** | Người/ứng dụng được thao tác trên tài nguyên cụ thể |
| **SCIM/provisioning** | Account, group và entitlement đích đạt desired state |
| **Reconciliation** | Quan sát thực tế không còn quyền/thông tin dư |

**Không sử dụng một claim do client tự cung cấp như isAdmin=true để thay thế nguồn RBAC/ABAC.** Nếu AS đưa quyền vào token, RS vẫn cần trust contract, audience phù hợp và chiến lược cập nhật quyền khi trạng thái thay đổi.

## 15. Access token trong Joiner: cấp đúng người và đúng thời điểm

### 15.1. Quy trình hợp lệ

1. **HRIS phát sự kiện Joiner** với personId/relationshipId và effectiveAt.
2. **IAM/IGA xác minh nguồn**, đối chiếu danh tính, hoàn thành proofing/enrollment theo chính sách.
3. **IdP/AS chuẩn bị account và policy**; không mở quyền vượt thời điểm hoặc điều kiện đã duyệt.
4. **Người mới đăng ký MFA/security key** hoặc phương thức xác thực được chấp nhận.
5. **Ứng dụng nhận kết quả xác thực qua SSO**, sau đó yêu cầu access token cho đúng API/scope cần thiết.
6. **AS đánh giá subject/client và policy** trước khi phát token.
7. **RS kiểm tra token và quyền**, không chỉ token tồn tại.
8. **SCIM/API connector đối soát account và group** tại hệ thống đích, xử lý sai lệch.

Nếu HRIS đã tạo tài khoản trước ngày bắt đầu, AS vẫn có thể cần **chặn cấp token hoặc chặn API truy cập** đến effectiveAt. Việc một object người dùng tồn tại ở IdP chưa chứng minh người đó đã được phép xử lý dữ liệu.

### 15.2. Tránh cấp token cho nhầm account

Email và username có thể trùng hoặc đổi. Token cho người dùng phải được gắn với identity đáng tin theo issuer/subject mapping; khi một người mới có cùng email với nhân viên cũ, RS/ứng dụng không được kế thừa quyền chỉ vì email giống.

### 15.3. Thông báo hoàn tất

Thông báo “đã kích hoạt” nên dựa trên trạng thái **account và quyền đã được xác minh**, không phải chỉ dựa trên AS đã trả một access token. Một token có scope hẹp vẫn không bảo đảm ứng dụng đã có mọi entitlement cần thiết cho công việc.

## 16. Access token trong Mover: nguy cơ quyền cũ còn hiệu lực

**Mover** là sự kiện nhân viên đổi vai trò, bộ phận, hợp đồng hoặc phạm vi truy cập. Nó có thể làm thay đổi RBAC/ABAC, scope được cấp cho client và điều kiện MFA.

### Vấn đề token đã phát trước thay đổi

Giả sử Lan có role Sales-Exporter, đã được cấp JWT access token với claim quyền xuất dữ liệu, exp còn 30 phút. Sau đó Lan chuyển sang Finance và quyền Sales-Exporter bị thu hồi ở IAM.

Nếu API chỉ kiểm tra chữ ký/exp và chấp nhận **role cũ được nhúng trong token**, Lan có thể tiếp tục xuất dữ liệu trong khoảng token còn hạn. Đây là một dạng **privilege lag**.

### Hướng giảm thiểu

- Tính lại desired state từ nguồn có thẩm quyền và phê duyệt; thu hồi quyền cũ thay vì chỉ cộng quyền mới.
- Hạn chế scope/TTL cho API nhạy cảm, tránh token có quyền rộng kéo dài.
- Với hành động rủi ro cao, kiểm tra **trạng thái quyền hiện hành** ở RS/policy engine thay vì chỉ tin role claim cũ.
- Nếu dùng introspection, điều chỉnh cache/thu hồi để phản ánh thay đổi đúng hạn.
- Cân nhắc thu hồi token/session khi thay đổi vai trò nhạy cảm theo chính sách.
- Kiểm tra cả **direct grants, group membership, phiên SSO, local account và client token** có liên quan.
- Áp điều kiện **step-up/MFA mạnh hơn** trước quyền mới khi cần.
- Đối soát quyền thực tế trên ứng dụng và ghi thời gian quyền cũ còn hiệu lực nếu có.

**Tăng mức MFA hoặc tạo access token mới không tự xóa quyền cũ ở hệ thống đích.** Mover cần cả cập nhật uỷ quyền và thu hồi đúng phạm vi.

## 17. Access token trong Leaver: cắt truy cập thực sự

**Leaver** là thời điểm rủi ro từ token tồn dư trở nên rõ rệt: người dùng không còn quan hệ hợp lệ nhưng token được cấp trước đó có thể vẫn hoạt động. Cần phân biệt **ngừng cấp mới** và **làm mất hiệu lực credential đã cấp**.

### Runbook Leaver theo lớp

| Lớp | Hành động | Bằng chứng cần có |
|---|---|---|
| HRIS/IAM | Xác minh sự kiện nghỉ, effectiveAt, identity và quan hệ | Nguồn có thẩm quyền, version, timestamp |
| IdP/AS | Disable/hạn chế account và **ngừng cấp token mới** cho quan hệ đã hết | Chính sách cấp token/identity state |
| Refresh token | Thu hồi khả năng xin access token mới | Trạng thái revocation/rotation tại AS |
| Access token | Chặn token còn hiệu lực qua RS/gateway, introspection, denylist hoặc TTL phù hợp | Đã xác minh RS không chấp nhận trái policy |
| SSO/app session | Hủy các session và token ứng dụng theo khả năng | Session state của từng RP/SP |
| SCIM/API | Deactivate account, thu hồi nhóm và quyền ở đích | Readback tài khoản và entitlement |
| API key/SSH key | Thu hồi credential độc lập OAuth | Danh sách key/token tại hệ thống đích |
| VPN/cloud/PAM | Chặn kết nối/role đặc quyền | Trạng thái thực tế tại hệ thống đích |
| Service account liên quan | Chuyển owner, rà soát/luân chuyển secret người nghỉ có thể biết | Owner mới, secret state, quyền được duyệt |
| Audit/reconciliation | Ghi sai lệch, thời gian và ngoại lệ còn mở | Ticket, evidence, owner, deadline |

### Ví dụ token còn hiệu lực sau khi khóa IdP

- **17:00:** HRIS cho Leaver có hiệu lực.
- **17:00:05:** IdP khóa người dùng; AS không cấp access token mới.
- **17:01:** Một JWT phát lúc 16:55 vẫn có exp là 17:25.
- **17:02:** Nếu API chỉ kiểm chữ ký/exp, nó có thể chấp nhận JWT này dù quan hệ công việc đã hết.
- **17:03:** RS kiểm tra lifecycle hoặc nhận sự kiện revocation; các request tiếp theo được chặn theo cơ chế triển khai.
- **17:05:** Các phiên ứng dụng và credential độc lập được thu hồi, hệ thống tiếp tục đối soát.

Những mốc trên là **ví dụ giả định**, không phải bảo đảm SLA. Trường hợp API có yêu cầu cắt truy cập khẩn cấp phải dùng cơ chế giảm thiểu phù hợp ngay; không chấp nhận chờ token hết hạn nếu mức rủi ro không cho phép.

### Đừng coi logout là deprovision

Logout ở IdP có thể không chấm dứt access token API đã sao chép hoặc phiên của ứng dụng khác. **Leaver hoàn tất** phải được đánh giá theo **toàn bộ đường truy cập trong phạm vi**, bao gồm OAuth và cả những credential không dùng OAuth.

## 18. Máy–máy, service account và workload identity

Một access token có thể đại diện cho **client/workload**, không phải người dùng. Trong client credentials, subject hoặc trường nhận diện được trình bày theo profile của issuer; không nên giả lập một employee subject khi không có người dùng được ủy quyền cụ thể.

### Nguyên tắc thiết kế

- Mỗi dịch vụ/ứng dụng nên có **client identity** và owner kỹ thuật được quản lý.
- Cấp **scope và audience tối thiểu**; không dùng token chung để gọi mọi API trong tổ chức.
- Ưu tiên **client authentication mạnh** hoặc workload identity/federation phù hợp thay cho client secret tĩnh dài hạn khi có thể.
- Bảo vệ khóa/chứng chỉ/secret trong **secret manager hoặc hạ tầng đáng tin**; không nhúng vào source code hoặc CI logs.
- Giới hạn tuổi access token và bảo vệ refresh token nếu có loại grant cho phép; không giả định client credentials luôn dùng refresh token.
- Gắn vòng đời token với **workload/service registry**, không chỉ HRIS.
- Khi workload ngừng, thu hồi client permission và credential; khi owner nghỉ, **chuyển owner và rà soát secret** thay vì xóa mù quáng một workload production.
- Đối soát token/client không còn mục đích, quyền cloud và API key tồn dư.

### Token exchange và confused deputy

Trong kiến trúc nhiều service, có thể cần đổi token cho một audience khác theo một cơ chế **token exchange** được thiết kế và chấp nhận. Không đơn giản **chuyển tiếp bearer token** từ service A tới B rồi cho B dùng với mọi tài nguyên khác. Quy tắc audience, sự ủy quyền giữa các thành phần và chủ thể đang được đại diện phải rõ để tránh **confused deputy** và leo thang đặc quyền.

## 19. Rủi ro bảo mật thường gặp và cách phòng ngừa

| Sai lầm hoặc tấn công | Hậu quả | Biện pháp |
|---|---|---|
| API chấp nhận ID token thay access token | Token dùng sai đối tượng nhận | Phân biệt token type, audience và profile |
| Chỉ decode JWT, không verify signature | Có thể chấp nhận payload giả | Kiểm tra chữ ký, thuật toán và khóa tin cậy |
| Không kiểm tra audience | Dùng token API A trên API B | Enforce đúng aud/resource |
| Tin issuer/JWKS URL do attacker đưa | Chấp nhận khóa từ nguồn không tin | Trust issuer được cấu hình và key rotation kiểm soát |
| Token bị lộ qua URL/log | Attacker replay bearer token | Header phù hợp, TLS, redaction, token protection |
| JWT chứa PII nhạy cảm | Ai có token có thể đọc payload | Tối thiểu hóa claim, không coi JWS là mã hóa |
| Access token sống quá lâu | Quyền tồn dư sau Mover/Leaver | TTL phù hợp, revocation/state checks |
| Refresh token không được bảo vệ | Có thể xin token mới kéo dài | Bảo vệ, rotation/revocation phù hợp |
| Scope rộng vượt nhu cầu | Gia tăng tác động khi token lộ | Least privilege và resource-specific tokens |
| Chỉ kiểm tra scope | Truy cập dữ liệu thuộc người khác/tenant khác | Object-level RBAC/ABAC, tenant isolation |
| DPoP/mTLS chỉ kiểm header | Không có proof-of-possession thật | Kiểm proof, binding, replay, key ownership |
| Introspection cache quá lâu | Thu hồi không phản ánh kịp | Giới hạn cache, invalidation, policy rủi ro |
| Chỉ disable IdP lúc Leaver | JWT/session/API key vẫn có thể dùng | Thu hồi đa lớp và readback tại RS |
| Tái dùng token qua nhiều service | Sai audience hoặc confused deputy | Audience restriction, token exchange có kiểm soát |
| Token của bot không owner | Không ai thu hồi hoặc luân chuyển | Registry, owner, kỳ review và loại bỏ khi ngừng |
| Replay job JML cũ | Mở lại quyền đã thu hồi | Version/fencing, kiểm tra trạng thái nguồn |

Tấn công **token substitution/mix-up** cũng có thể xảy ra khi ứng dụng cho phép token từ nhiều issuer hoặc tenant mà không ràng buộc đúng ngữ cảnh. Cần kiểm tra **nguồn phát hành, audience, client/subject, tenant và giao thức** theo hợp đồng của từng API.

## 20. Kiểm toán và giám sát access token

### Dữ liệu nên ghi

Không nên log giá trị token nguyên vẹn. Có thể ghi metadata đủ để truy vết:

- **Sự kiện cấp token:** issuer, client ID, subject/workload ID, audience, scope, iat/exp, policy/version.
- **Yêu cầu API:** resource server, operation, correlation ID, kết quả authorization, token identifier đã được xử lý an toàn nếu có.
- **Sự kiện từ chối:** sai audience, issuer, exp, signature, scope, lifecycle, sender proof hoặc policy.
- **Sự kiện thu hồi:** actor có thẩm quyền, thời điểm, loại token/credential, trạng thái phát đến RS.
- **JML:** person/relationship ID, effectiveAt, policy thay đổi, connector deprovision và kết quả readback.
- **Ngoại lệ:** API chưa hỗ trợ immediate revoke, cache TTL, owner, biện pháp bù trừ và deadline.

Token ID, claim và subject có thể là **dữ liệu nhạy cảm hoặc mang tính liên kết hành vi**. Bảo vệ log theo phân quyền và thời hạn lưu giữ, chỉ ghi mức cần thiết. Không đưa access token, refresh token, client secret, private key hoặc cookie phiên vào SIEM, analytics, ticket hay screenshot phổ thông.

### Các chỉ số hữu ích

| Chỉ số | Diễn giải |
|---|---|
| **Token validation failure rate** | Lỗi signature, issuer, audience, expiry và định dạng |
| **Insufficient-scope/authorization denials** | Tỷ lệ bị từ chối vì quyền/tenant/resource |
| **Expired/revoked token acceptance incidents** | Sự cố token không nên được chấp nhận nhưng vẫn được dùng |
| **Effective-to-block latency** | Từ mốc Leaver/Mover cần chặn đến khi RS xác minh ngăn truy cập |
| **Access token TTL distribution** | Tuổi token theo client, resource và mức nhạy cảm |
| **Introspection latency/cache age** | Ảnh hưởng hiệu năng và độ trễ phản ánh thu hồi |
| **Residual token-related access** | Truy cập sau khi quan hệ hoặc quyền hết hiệu lực |
| **Refresh token reuse alerts** | Dấu hiệu lộ/chiếm refresh token nếu cơ chế hỗ trợ |
| **Unknown-owner OAuth clients** | Client/workload identity thiếu owner hoặc phê duyệt |
| **Audience/scope overbreadth** | Token có phạm vi rộng hơn nhu cầu tích hợp |
| **Token revocation coverage** | Tỷ lệ API có cơ chế chặn token đã thu hồi theo yêu cầu |
| **Audit/reconciliation coverage** | API, principal và credential có thể kiểm tra thực tế |

Không công bố “đã thu hồi 100% access token” chỉ vì AS đã nhận lệnh revocation. Nếu RS chưa có bằng chứng ngừng chấp nhận token hoặc vẫn còn local credentials, phải ghi rõ **giới hạn khả năng quan sát**.

## 21. Runbook xử lý sự cố access token

Khi một API tiếp tục cho phép truy cập không mong muốn hoặc một client báo lỗi token:

### Bước 1 — Xác định lớp lỗi

- **Không lấy được token:** kiểm tra OAuth grant, client authentication, redirect URI, PKCE, scope yêu cầu và chính sách AS.
- **Lấy token được nhưng API trả 401:** kiểm tra hạn, issuer, signature, audience, token type và sender proof.
- **API trả 403:** kiểm tra scope, RBAC/ABAC, tenant, object ownership và lifecycle.
- **Leaver vẫn gọi API thành công:** kiểm tra AS đã ngừng cấp mới chưa, token cũ là JWT hay opaque, revocation được RS thực thi chưa và cache/token/session nào còn.

### Bước 2 — Lấy chứng cứ đúng và tối thiểu

Thu thập **client ID, issuer, audience, resource, correlation ID, token ID đã ẩn/biến đổi thích hợp, issued/expiry time, policy version, lifecycle state và HTTP status**. Không yêu cầu người dùng dán nguyên access token vào ticket hoặc chat.

### Bước 3 — Kiểm tra trạng thái nguồn và quyền

Đối chiếu HRIS/relationship, IGA approval, role mapping, resource policy, trạng thái user/client và các sự kiện Mover/Leaver mới nhất. Không replay quyền cũ để “sửa 403” nếu thực ra quyền đã bị thu hồi đúng.

### Bước 4 — Chọn biện pháp

| Vấn đề | Biện pháp thích hợp |
|---|---|
| Token hết hạn | Lấy token mới qua grant hợp lệ; không bỏ kiểm tra exp |
| Sai audience/issuer | Cấu hình đúng resource/issuer và xin token thích hợp |
| Sai scope | Đánh giá quyền cần thiết, chỉ phê duyệt phạm vi tối thiểu |
| Chữ ký/kid lỗi do rotation | Sửa nguồn JWKS/trust/cache; không tắt verify |
| Opaque introspection lỗi | Khắc phục AS/kết nối và áp fail behavior theo risk |
| Token bị lộ | Thu hồi, kiểm tra khả năng sử dụng lại và điều tra log |
| JWT vẫn sống sau Leaver | Chặn tại RS/gateway hoặc policy trạng thái; xử lý phiên/credential khác |
| Role claim cũ sau Mover | Cập nhật policy, thu hồi token nếu cần, giảm TTL/cache và readback |
| Workload owner đã Leaver | Chuyển owner, thu hồi/quay vòng secret và kiểm tra scope |

### Bước 5 — Đối soát và đóng

Xác minh **request hợp lệ vẫn chạy** và **request không còn thẩm quyền bị từ chối** ở API đúng scope. Ghi lại trạng thái token/phiên/quyền, thời điểm kiểm tra và giới hạn còn tồn tại. Nếu chưa thể chặn đường truy cập rủi ro, mở incident với owner, SLA và biện pháp bù trừ; không chỉ kết luận “AS trả success”.

## 22. Tình huống xuyên suốt: access token qua Joiner, Mover và Leaver

Giả sử **Minh** gia nhập nhóm bán hàng, dùng cổng SSO và một API báo cáo.

**Joiner — Ngày bắt đầu:** HRIS phát sự kiện với identity ID bền vững và ngày hiệu lực. IAM kiểm tra proofing/enrollment, IdP cho Minh đăng nhập bằng MFA. Client báo cáo xin access token qua Authorization Code Flow với PKCE. AS chỉ cấp token sau khi chính sách cho phép. Resource server kiểm tra audience, scope và quyền Sales-Reader hiện hành, không chỉ dựa vào chữ ký.

**Đang làm việc:** Minh dùng API đọc báo cáo thuộc đơn vị Sales. Token sống trong thời gian ngắn theo chính sách; refresh token nếu có được client giữ đúng cách. Khi client gọi báo cáo của Finance, API từ chối vì RBAC/ABAC không cho phép, dù token có scope báo cáo đọc.

**Mover — Chuyển sang Finance:** HRIS phát thay đổi vai trò. IAM thu hồi nhóm Sales không còn hợp lệ, cấp nhóm Finance sau phê duyệt. Một access token cũ của Minh vẫn còn hạn và mang claim Sales. API nhạy cảm phải kiểm tra trạng thái quyền hiện hành hoặc cơ chế thu hồi thích hợp để không cho Minh tiếp tục truy cập dữ liệu Sales ngoài phạm vi. Việc cấp token Finance mới **không tự hủy token cũ**.

**Phát hiện token lộ:** Monitoring phát hiện token của Minh bị chép vào log của một dịch vụ. Security xử lý theo phạm vi token: thu hồi hoặc chặn việc sử dụng tại RS, xoá/cô lập log chứa bí mật theo quy trình, kiểm tra request bất thường và đánh giá refresh token, client secret, session có liên quan. Không chỉ thay mật khẩu rồi coi đã xử lý xong.

**Leaver — Ngày nghỉ có hiệu lực:** AS ngừng cấp token mới cho Minh; refresh token được thu hồi. Resource server phải chặn các access token còn hạn bằng cơ chế phù hợp, đặc biệt API tài chính. IAM đồng thời deactivate account qua SCIM và xử lý local session/token/API key ở ứng dụng. Reconciliation xác minh quyền thực tế đã hết. Nếu một hệ thống legacy không kiểm tra revocation tức thời, workflow vẫn ghi ngoại lệ và áp biện pháp giảm thiểu theo rủi ro.

**Rejoiner — Quan hệ mới:** Minh quay lại ở bộ phận khác. Account linking phải xác minh quan hệ mới và quyền mới, không hồi sinh access token, client grant hoặc session cũ. Identity có thể giữ khóa lịch sử nhưng quyền được cấp theo chính sách hiện tại.

Bài học rút ra: **access token là bằng chứng uỷ quyền có phạm vi và thời gian; vòng đời của nó phải phụ thuộc vào quyền và quan hệ danh tính hiện hành, không chỉ vào thời gian exp hoặc trạng thái một ứng dụng SSO**.

## 23. Checklist triển khai access token an toàn trong IAM

1. **Mục đích rõ:** đã phân biệt access token cho resource server với OIDC ID token cho relying party và refresh token cho client chưa?
2. **Nguồn tin cậy:** resource server có issuer/JWKS/introspection configuration được cố định và kiểm soát thay đổi không?
3. **Chữ ký/profile:** JWT được verify chữ ký, thuật toán, token type và key rotation đúng không, thay vì chỉ decode payload?
4. **Audience:** token có được cấp và chỉ chấp nhận ở đúng API/resource không?
5. **Scope:** token có phạm vi hẹp và phù hợp grant/client, không mặc định quyền rộng không?
6. **Thời gian:** exp/nbf/iat được xử lý đúng với đồng hồ và TTL theo rủi ro không?
7. **Người dùng/tenant:** subject/client/tenant được liên kết đúng identity, không suy chỉ bằng email/username không?
8. **Authorization:** API có áp RBAC/ABAC, quyền trên đối tượng, SoD và lifecycle ngoài kiểm tra token không?
9. **Bearer security:** token được truyền qua TLS và header phù hợp, không lộ URL/log/analytics/chat?
10. **Sender constraint:** nếu dùng mTLS/DPoP, RS có kiểm proof và key binding thật không?
11. **Grant:** client tương tác dùng luồng hiện đại như Authorization Code+PKCE; workload dùng grant phù hợp, không dùng password người thật cho bot?
12. **Introspection:** opaque token có được introspect qua kênh tin cậy, quản lý cache/expiry/revocation không?
13. **Refresh token:** có bảo vệ, rotation/revocation và xử lý hành vi bất thường theo khả năng không?
14. **Session:** đã phân biệt logout IdP, app session và access token còn hạn chưa?
15. **Joiner:** token chỉ cấp khi danh tính, enrollment và điều kiện quan hệ có hiệu lực đã đạt?
16. **Mover:** quyền cũ và token/cached claims được thu hồi hoặc kiểm tra lại theo mức rủi ro?
17. **Leaver:** AS ngừng cấp mới, RS ngừng chấp nhận token còn thẩm quyền cũ, SCIM/API và credential độc lập đã được xử lý?
18. **Non-human:** service/client credentials có owner, registry, scope, hạn, xoay vòng và thu hồi khi workload ngừng?
19. **Quan sát:** log có correlation ID, không chứa token thô và đủ để đo độ trễ thu hồi?
20. **Đối soát:** đã chứng minh trạng thái thực tế của API/account/credential và ghi rõ khoảng trống coverage chưa?

### Ghi nhớ

**OAuth access token là credential để client truy cập đúng resource server trong phạm vi uỷ quyền nhất định; không phải OIDC ID token và không tự chứng minh người dùng được phép làm mọi việc.** Resource server phải xác minh **issuer, audience, chữ ký hoặc trạng thái introspection, thời gian, scope, trạng thái chủ thể và RBAC/ABAC**. Bearer token cần được bảo vệ như bí mật; DPoP hoặc mTLS có thể bổ sung sender constraint nhưng không thay thế kiểm soát quyền. Trong **Joiner–Mover–Leaver**, phải quản lý **phát hành, thời hạn, làm mới, thu hồi và đối soát** cùng với IdP/SSO, SCIM, phiên ứng dụng và credential máy để ngăn **quyền truy cập tồn dư**.
