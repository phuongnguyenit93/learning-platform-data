# Service-to-service auth – xác thực giữa các dịch vụ trong vòng đời danh tính IAM

## Mục tiêu học tập

Sau bài học, người học có thể:

- Giải thích **service-to-service authentication (S2S auth)** và vì sao hệ thống cần định danh, xác thực và phân quyền cho **workload identity** thay vì chỉ cho người dùng.
- Phân biệt **authentication, authorization, token issuance, token validation, transport encryption, identity provisioning** và **accountability** trong một lời gọi service-to-service.
- Lựa chọn cơ chế phù hợp giữa **OAuth 2.0 client credentials, token exchange, workload identity federation, mutual TLS (mTLS), chứng chỉ máy và SPIFFE/SPIRE** dựa trên trust boundary.
- Kiểm tra **issuer, subject/client identity, audience, scope, signature/key, thời hạn, tenant, token binding và authorization policy** ở phía API nhận yêu cầu.
- Hiểu các rủi ro như **service impersonation, secret leakage, token replay, confused deputy, cross-tenant access, stale credentials, lateral movement và đặc quyền tồn dư**.
- Liên hệ **Kubernetes ServiceAccount, cloud managed identity, service mesh, Java/Spring Security**, CI/CD và hệ quản lý bí mật với vòng đời danh tính.
- Thiết kế **owner, purpose, inventory, creation, rotation, revocation, decommission, audit và reconciliation** cho non-human identities.
- Áp dụng **Joiner–Mover–Leaver**, IdP/SSO, SCIM, RBAC/ABAC và quản trị account người dùng vào hệ sinh thái dịch vụ mà không đồng nhất người dùng với workload.

## 1. Service-to-service auth là gì?

**Service-to-service authentication** là quá trình **dịch vụ nhận yêu cầu xác minh danh tính của dịch vụ hoặc workload gửi yêu cầu**, để quyết định liệu nó có thực sự là một thực thể được tin cậy trong môi trường đang giao tiếp hay không.

Ví dụ, hệ thống thương mại điện tử có các thành phần:

- **Order Service** tạo đơn và cần hỏi **Inventory Service** liệu còn hàng.
- **Payment Service** cần cập nhật trạng thái thanh toán ở **Order Service**.
- **Reporting Job** đọc dữ liệu từ **Data API** để tổng hợp báo cáo.
- **CI/CD Pipeline** gọi **Deployment API** để phát hành ứng dụng.
- **Identity Provisioning Connector** gọi **SaaS Administration API** để tạo, cập nhật và thu hồi tài khoản.

Một request dạng:

~~~text
Order Service --[authenticated API call]--> Inventory Service
~~~

đặt ra ít nhất bốn câu hỏi:

1. **Ai gửi?** Có thực là Order Service chạy ở môi trường được tin cậy không?
2. **Đến đúng ai?** Order Service có xác minh đúng Inventory Service, tránh gửi token/dữ liệu cho kẻ giả mạo không?
3. **Được làm gì?** Quyền chỉ đọc tồn kho hay cũng được điều chỉnh số lượng?
4. **Có còn hợp lệ?** Danh tính, credential, policy, môi trường và quan hệ owner của workload còn được phép hoạt động không?

**Xác thực thành công không tự đồng nghĩa được phân quyền.** Một workload có danh tính hợp lệ vẫn phải bị từ chối nếu gọi API sai action, sai tenant, sai audience hoặc vượt mục đích nghiệp vụ.

Trong module **SECURITY_IDENTITY_ACCESS_MANAGEMENT_IDENTITY_LIFECYCLE**, S2S auth liên quan trực tiếp tới **vòng đời non-human identity** song song với Joiner–Mover–Leaver của con người. **IdP/SSO** chủ yếu phục vụ xác thực người dùng và liên kết danh tính, **OAuth 2.0/mTLS/workload federation** có thể bảo vệ trao đổi giữa máy, **RBAC/ABAC/PBAC** xác định quyền dịch vụ, còn **SCIM/API và reconciliation** giúp quản lý trạng thái thực của các quyền và account ở hệ thống đích.

### 1.1. Ví dụ sai và đúng

~~~text
KHÔNG AN TOÀN:
  Inventory API mở trong mạng nội bộ.
  Chỉ cần IP thuộc subnet ứng dụng là được sửa tồn kho.
  Mọi service dùng chung một static API key không hết hạn.

AN TOÀN HƠN:
  Order Service có workload identity riêng.
  Inventory API xác minh token/certificate của caller.
  Token chỉ hướng tới Inventory API, scope phù hợp.
  Quyền điều chỉnh tồn kho yêu cầu policy/approval riêng.
  Credential ngắn hạn, luân chuyển và có owner.
  Audit ghi caller, action, resource, decision và kết quả.
~~~

Đây là mô hình tư duy, không phải một thiết kế bắt buộc duy nhất cho mọi nền tảng.

## 2. Human identity và service identity khác nhau như thế nào?

| Khía cạnh | Human identity | Service/workload identity |
| --- | --- | --- |
| **Chủ thể** | Nhân viên, nhà thầu, đối tác | Ứng dụng, container, job, pipeline, máy chủ, function |
| **Nguồn khởi tạo** | HRIS, hợp đồng, identity proofing | Workload registry, deployment controller, cloud IAM, platform inventory |
| **Cách xác thực** | Passkey, MFA, SSO, session | mTLS certificate, OAuth client credentials, workload assertion/token |
| **Thời gian sống** | Theo quan hệ làm việc | Từ vài phút đến vòng đời ứng dụng/dự án |
| **Owner** | Người dùng/manager/sponsor | Đội vận hành, owner kỹ thuật và đôi khi resource owner riêng |
| **Rủi ro nổi bật** | Account takeover, role creep sau Mover/Leaver | Secret lộ, workload bị giả mạo, token replay, quyền mồ côi |
| **Luồng thu hồi** | Disable account, gỡ group, revoke session | Decommission principal, revoke trust/credential/role, stop workload |
| **Bằng chứng** | Login, approval, identityId | Principal ID, deployment/job ID, audience, artifact, request trace |
| **Yếu tố thay đổi** | Joiner/Mover/Leaver nhân sự | Workload create/migrate/retire và Mover/Leaver của owner |
| **Quản trị quyền** | IGA, RBAC/ABAC, access review | IAM/PBAC, machine-identity inventory, access review, secret lifecycle |

### 2.1. Một dịch vụ không nhất thiết tương ứng một account

Một ứng dụng có thể chạy nhiều instance, mỗi instance có chứng thực ngắn hạn từ cùng một **logical workload identity**. Ngược lại, một ứng dụng có thể dùng nhiều danh tính cho các mục đích khác nhau: đọc database, gửi message, gọi cloud API.

Cần phân biệt:

- **Application/service name:** tên logic của dịch vụ, ví dụ `order-service`.
- **Workload principal ID:** danh tính được hệ cấp quyền công nhận, ví dụ workload trong namespace production.
- **Runtime instance identity:** một pod/VM/process cụ thể với credential phát trong thời gian ngắn.
- **Client registration:** client OAuth được authorization server nhận diện.
- **Human owner:** đội hoặc cá nhân chịu trách nhiệm lifecycle và thay đổi quyền.

Không dùng tên hiển thị hoặc hostname làm bằng chứng duy nhất của danh tính.

### 2.2. Service account không phải account dùng chung của nhân viên

Không nên đăng nhập vào production bằng một tài khoản dịch vụ chỉ vì nó có quyền cao. Interactive privileged access có PAM/MFA/JIT và human attribution riêng; service identity phải được quản lý theo mục đích của workload.

## 3. Authentication, authorization và encryption là ba lớp riêng

| Lớp | Câu hỏi | Ví dụ |
| --- | --- | --- |
| **Peer authentication** | Kết nối thực sự tới đúng server/client? | TLS server verification, mTLS |
| **Caller/workload authentication** | Request gắn với principal nào? | OAuth access token hoặc mTLS client certificate |
| **Authorization** | Principal có quyền làm action trên resource này? | Scope + RBAC/ABAC/tenant policy |
| **Confidentiality/integrity in transit** | Dữ liệu có bị nghe lén/sửa trên đường truyền? | TLS được cấu hình đúng |
| **Credential issuance** | Ai cấp secret, cert hoặc token, dựa vào cơ sở nào? | Workload identity provider, CA, authorization server |
| **Revocation/lifecycle** | Khi workload/người sở hữu thay đổi, quyền có bị gỡ? | IAM revoke, certificate expiry, trust-policy update |
| **Audit/accountability** | Có truy ra principal và hành động không? | Request log, trace ID, caller identity, authorization decision |

**HTTPS/TLS chỉ bảo mật đường truyền và xác thực phía server nếu được kiểm đúng**. Nó không mặc định chứng minh caller là Order Service. Ngược lại, một Bearer token hợp lệ không tự bảo đảm caller kiểm tra server TLS đúng hoặc được quyền đọc đối tượng bất kỳ.

### 3.1. Không mặc định mạng nội bộ là vùng tin cậy tuyệt đối

Một pod hoặc VM bị chiếm có thể gọi nhiều dịch vụ nội bộ. Nếu API dựa duy nhất vào IP/subnet hoặc header `X-Service-Name` không được bảo vệ, attacker có thể giả làm thành phần khác.

S2S authentication nên tồn tại ở **trust boundary phù hợp**, kể cả trong mạng nội bộ, đặc biệt với API quản trị, dữ liệu nhạy cảm, multi-tenant và cross-account/cloud.

## 4. Kiến trúc tham chiếu service-to-service

~~~mermaid
flowchart LR
    CI["CI/CD + workload registry"] --> ID["Identity issuance / attestation"]
    OWN["Service owner / IAM governance"] --> ID
    ID --> AS["Authorization server / Identity provider"]
    ID --> CA["Certificate authority / SPIFFE control plane"]
    A["Service A: caller"] --> TOKEN["Short-lived token / certificate"]
    AS --> TOKEN
    CA --> TOKEN
    TOKEN --> A
    A -->|"TLS, identity proof, API request"| PEP["Service B: API gateway / PEP"]
    PEP --> PDP["PDP: policy RBAC/ABAC/PBAC"]
    PIP["Identity, tenant, resource, approvals"] --> PDP
    PDP --> PEP
    PEP --> DATA["Protected resource/action"]
    PEP --> LOG["Audit, metrics, trace"]
    ID --> LOG
    LOG --> REC["Reconciliation & lifecycle"]
~~~

Sơ đồ mô tả **vai trò logic**, không phải yêu cầu tất cả dịch vụ phải dùng đồng thời OAuth và mTLS. Một nền tảng có thể dùng **mTLS-only**, **OAuth-only trên TLS**, **workload federation** hoặc kết hợp.

### 4.1. Nguồn thẩm quyền quan trọng

- **Workload inventory/registry:** workload này có thực, owner nào, purpose gì, chạy ở môi trường nào.
- **Identity issuer/trust anchor:** ai được cấp certificate/token, dựa trên bằng chứng gì.
- **Resource owner:** API/data owner cho phép những scopes/actions nào.
- **Policy source:** ai định nghĩa RBAC/ABAC và phiên bản đang active.
- **Runtime verifier/PEP:** nơi kiểm request và chặn thao tác.
- **Observed target permissions:** role/ACL/trust tồn tại thật trong API/cloud/SaaS.

### 4.2. “Có credential” không đồng nghĩa “được triển khai đúng”

Một client có OAuth secret vẫn có thể dùng nó từ máy bên ngoài nếu secret bị lộ, trừ khi có sender constraint, môi trường/trust policy và giám sát phù hợp. Việc cấp credential phải gắn với **workload hợp lệ**, không chỉ với người đã nộp đơn xin secret.

## 5. Vòng đời của một lời gọi S2S

~~~mermaid
sequenceDiagram
    autonumber
    participant A as Service A
    participant W as Workload identity provider
    participant AS as Authorization server
    participant B as Service B / PEP
    participant P as Policy/PIP
    participant AUD as Audit

    A->>W: Chứng minh workload context
    W-->>A: Workload credential/assertion
    A->>AS: Xin access token cho Service B
    AS->>AS: Verify client/workload and granted scope
    AS-->>A: Short-lived access token
    A->>B: TLS + bearer/PoP token + resource request
    B->>B: Verify TLS/token issuer/audience/expiry/key
    B->>P: Evaluate caller, action, resource, tenant
    P-->>B: PERMIT / DENY + obligations
    B->>AUD: Identity + decision + outcome
    alt PERMIT và obligations đạt
        B-->>A: Protected API result
    else DENY / invalid credential
        B-->>A: Reject theo API contract
    end
~~~

Đây là ví dụ **token-based authentication**. Trong mô hình mTLS-only, bước lấy OAuth token có thể không xuất hiện; trong mô hình token exchange có thêm bước thay đổi token.

### 5.1. Ai là caller trong log?

Cần lưu **authenticated workload principal** (được xác minh từ token/certificate), không chỉ `User-Agent`, `X-Service-Name` hoặc một giá trị header do caller tự khai. Nếu yêu cầu có human delegation, cần thêm **on-behalf-of subject** với ràng buộc riêng.

## 6. OAuth 2.0 client credentials grant

**Client credentials** là một cơ chế trong OAuth 2.0 để một client được xác thực xin **access token đại diện cho quyền của chính client** khi truy cập API, thường phù hợp cho **machine-to-machine / daemon / batch job** không yêu cầu người dùng tương tác.

### 6.1. Luồng minh họa

~~~text
Service A -> Authorization Server:
  POST /oauth2/token
  grant_type=client_credentials
  scope=inventory.read

  Client phải được xác thực bằng cơ chế server hỗ trợ
  như private_key_jwt, mTLS client auth hoặc client secret.

Authorization Server -> Service A:
  access_token = opaque-or-JWT
  token_type = Bearer
  expires_in = 300

Service A -> Inventory API:
  Authorization: Bearer <access_token>

Inventory API:
  Verify token, issuer, audience, expiry, scope
  Evaluate resource/action/tenant policy
~~~

Đây là request mô tả, không phải hướng dẫn copy-paste cho một authorization server cụ thể. Scope, audience parameter, client-authentication mechanism và response fields tùy profile/provider.

### 6.2. Các điểm bảo mật cốt lõi

- Mỗi client có **client identity ổn định** và owner, purpose, environment.
- Client được cấp **chính xác scopes cần dùng**, không cấp toàn bộ API.
- Token **ngắn hạn, đúng audience** và được lưu ở bộ nhớ an toàn nếu có thể.
- Token endpoint bảo vệ **client authentication** và rate limiting.
- API nhận token tự kiểm **issuer, audience, signature/active status, expiry, scopes/roles**.
- Không đưa client secret/token vào log, URL, telemetry hoặc image container.
- Token cache phải tôn trọng thời hạn và không chia sẻ token giữa các tenant/audience.
- Khi workload retire, revoke client/trust/grants và kiểm credential đang còn hiệu lực.

### 6.3. Client credentials không phải OIDC login của nhân viên

**OpenID Connect (OIDC)** bổ sung lớp xác thực người dùng với ID token. Trong S2S client credentials, thành phần quan trọng thông thường là **OAuth access token** để gọi resource server. **Không dùng ID token thay access token**, và không coi `sub` của workload giống một người dùng đã SSO.

### 6.4. Tránh nhét client secret vào ứng dụng

Trong một số nền tảng, static client secret vẫn được hỗ trợ. Tuy nhiên nếu có **private_key_jwt, workload identity federation, mTLS hoặc managed identity** phù hợp, có thể giảm việc phân phối bí mật tĩnh.

Việc lựa chọn phụ thuộc vào threat model và khả năng nhà cung cấp, không có phương thức duy nhất tốt nhất trong mọi hệ thống.

## 7. OAuth access token: JWT, opaque và introspection

Một access token có thể là **JWT** có chữ ký hoặc một **chuỗi opaque** cần tra trạng thái qua authorization server/introspection. Không được suy đoán token là JWT chỉ vì nó có ba phần dạng dấu chấm trong mọi trường hợp.

### 7.1. JWT access token minh họa

~~~json
{
  "iss": "https://identity.example.invalid/",
  "sub": "workload:orders-prod",
  "aud": "https://inventory.example.invalid",
  "iat": 1795380000,
  "nbf": 1795380000,
  "exp": 1795380300,
  "scope": "inventory.read",
  "client_id": "orders-service-prod",
  "tenant": "tenant-a",
  "jti": "token-instance-illustrative"
}
~~~

JSON này chỉ minh họa **claims**, không phải JWT có chữ ký, và timestamp cũng là dữ liệu ví dụ. Tên claim và ngữ nghĩa phụ thuộc token profile/provider. **Không tự tin bất kỳ claim nào chỉ vì client gửi JSON có tên giống chuẩn.**

### 7.2. Kiểm tra token phía API

| Kiểm tra | Vì sao cần |
| --- | --- |
| **Token integrity/signature** | Ngăn token bị sửa hoặc giả mạo |
| **Trusted issuer (`iss`)** | Chỉ nhận token từ issuer đã cấu hình |
| **Expected audience (`aud`)** | Chặn token phát cho API khác bị tái sử dụng |
| **Expiry/validity (`exp`, `nbf`)** | Chặn token quá hạn hoặc chưa có hiệu lực |
| **Algorithm/key policy** | Không chấp nhận thuật toán yếu, `none` hay key do untrusted header chỉ định |
| **Client/principal identity** | Gắn token với workload ID được cấp quyền |
| **Authorized scope/action** | Quyền token phải đủ nhưng không thay resource-level policy |
| **Tenant/environment** | Chặn token cross-tenant hoặc từ staging sang production |
| **Sender constraint, nếu có** | Ràng buộc token với khóa/chứng chỉ phù hợp |
| **Revocation/freshness** | Xử lý token bị thu hồi/credential stale theo risk |
| **Authorization policy** | Kiểm action, resource owner, classification, SoD và approvals |

**Signature hợp lệ chỉ chứng minh token do khóa tin cậy ký và dữ liệu không bị thay đổi.** Nó **không tự chứng minh caller có quyền** thực hiện thao tác bất kỳ.

### 7.3. JWKS và key rotation

Với JWT ký bằng khóa bất đối xứng, API thường lấy public keys từ **JWKS của issuer đã cấu hình**. Cần:

- Không tải JWKS từ URL do request/`jku` untrusted đưa vào.
- Giới hạn thuật toán và key type được phép.
- Cache key với TTL/refresh strategy và giới hạn network.
- Hỗ trợ chuyển khóa có overlap có kiểm soát.
- Xử lý key compromise theo runbook (không dùng cache vô hạn).
- Không để tất cả service rơi vào trạng thái PERMIT khi không thể xác minh khóa.

### 7.4. Opaque token và introspection

Với opaque token, resource server có thể gọi introspection endpoint được tin cậy để kiểm **active status, audience, scope, subject và metadata**. Điều này hỗ trợ kiểm trạng thái tập trung, nhưng tăng phụ thuộc vào authorization server/độ trễ.

Không có một lựa chọn mặc định tuyệt đối giữa JWT và opaque: cần cân nhắc **availability, revocation, cache, privacy, latency và độ nhạy quyền**.

## 8. Token exchange và on-behalf-of

Một lời gọi A → B → C có thể diễn ra **thay mặt người dùng** hoặc **thay mặt một workload khác**. Nếu B chuyển nguyên token của A/khách hàng sang C, có thể tạo **token replay, audience mismatch hoặc confused deputy**.

### 8.1. Phân biệt các ngữ cảnh

- **App-only:** B gọi C với quyền của riêng B, không mang danh tính người dùng.
- **Delegated/on-behalf-of:** B được phép gọi C vì một người dùng đã ủy quyền theo policy.
- **Service chaining:** A gọi B, B gọi C; B cần chứng minh thẩm quyền cho C.
- **Impersonation:** một hệ được phép đại diện cho chủ thể khác theo cơ chế đặc biệt; phải kiểm soát chặt.

**OAuth 2.0 Token Exchange (RFC 8693)** là một cơ chế có thể dùng để đổi token phù hợp audience/subject/actor, nhưng cách provider hỗ trợ và ràng buộc delegation tùy triển khai.

### 8.2. Mô hình minh họa

~~~text
User -> API A:
  User token aud = API-A

API A -> Authorization Server:
  Token exchange, resource/audience = API-B,
  subject/actor context theo policy

Authorization Server -> API A:
  Downstream token aud = API-B, scope tối thiểu

API A -> API B:
  Downstream token

API B:
  Verify token and delegation chain/policy
~~~

**API B không nên chấp nhận token dành cho API A**, dù issuer và chữ ký đều hợp lệ. Một token exchange hợp lệ cũng không tự mở rộng quyền của user/actor vượt policy.

### 8.3. Confused deputy

**Confused deputy** xảy ra khi một dịch vụ có quyền cao bị một caller quyền thấp lợi dụng để thực hiện hành động không được phép.

Ví dụ A có quyền đọc file bất kỳ từ object store, nhưng user chỉ được xem file thuộc tenant-a. Nếu A bỏ qua tenant/resource authorization và chỉ dùng quyền dịch vụ của mình để đọc object của tenant-b, S2S authentication của A với object store **vẫn có thể hoàn toàn thành công nhưng hệ thống có lỗ hổng phân quyền**.

Cần ràng buộc **actor, target resource, audience, tenant, action và ngữ cảnh ủy quyền**, không dựa duy nhất vào service credential mạnh.

## 9. mTLS – xác thực hai chiều bằng chứng chỉ

**Mutual TLS (mTLS)** là biến thể TLS trong đó **client cũng xuất trình chứng chỉ** cho server kiểm tra (ngoài chứng chỉ server). Khi được cấu hình đúng, hai phía có thể xác thực **peer identity** ở tầng kết nối.

~~~mermaid
sequenceDiagram
    autonumber
    participant A as Service A
    participant B as Service B
    A->>B: TLS ClientHello
    B-->>A: Server certificate + client certificate request
    A->>A: Verify server certificate, name and trust
    A->>B: Client certificate + proof of private key possession
    B->>B: Verify client certificate, trust, name/identity and policy
    Note over A,B: Thiết lập kênh TLS đã xác thực hai chiều
    A->>B: Application request
    B->>B: Map peer identity -> API authorization
    B-->>A: Response / DENY
~~~

Sơ đồ đơn giản hóa TLS handshake và có thể khác nhau theo phiên bản TLS/library. **mTLS không tự cấp permission ứng dụng**. Phía nhận vẫn cần ánh xạ SAN/identity sang workload principal rồi kiểm action/resource.

### 9.1. Bảo vệ danh tính chứng chỉ

Cần kiểm:

- Chuỗi chứng chỉ đến CA/trust bundle được phép.
- Thời gian hiệu lực, chính sách certificate, key usage/EKU phù hợp.
- Tên server hoặc danh tính peer mong đợi được xác minh đúng.
- SAN URI/DNS hoặc namespace identity được phép; không chỉ kiểm CA mà chấp nhận mọi certificate CA ký.
- Private key được bảo vệ, không chia sẻ trên nhiều workload không tương đương.
- Cơ chế rotation/revocation hoặc short-lived cert được kiểm thử.
- Không để proxy/sidecar cho phép kết nối plaintext bypass.

### 9.2. Tại sao không chỉ kiểm “certificate signed by our CA”?

Một CA nội bộ có thể cấp certificate cho nhiều workload. Nếu Inventory API chấp nhận **mọi chứng chỉ** do CA ký mà không kiểm caller ID, một workload ít quyền có thể truy cập như service đáng tin.

**Trust anchor** chứng minh nguồn cấp credential, còn **authorization policy** phải kiểm identity được cấp quyền tới resource cụ thể.

### 9.3. TLS termination và proxy headers

Nếu mTLS kết thúc ở ingress/sidecar, backend có thể không tự thấy client certificate. Trong kiến trúc này:

- Chỉ tin forwarded identity từ **proxy được xác minh và có kênh bảo vệ**.
- Không để client bên ngoài tự gửi `X-Client-Cert`, `X-Authenticated-Workload` rồi backend tin.
- Cần có đường backend chỉ nhận từ trusted proxy hoặc cơ chế xác thực tương đương.
- Audit rõ **peer identity tại proxy** và **workload identity được chuyển đến PEP**.
- Kiểm bypass trực tiếp vào backend không qua proxy.

## 10. SPIFFE và SPIRE cho workload identity

**SPIFFE** đưa ra mô hình định danh workload độc lập hạ tầng, thường dùng **SPIFFE ID** dạng URI để biểu diễn danh tính trong trust domain. **SPIRE** là một triển khai giúp chứng thực node/workload và cấp danh tính/credential theo mô hình này.

Ví dụ minh họa:

~~~text
spiffe://example.internal/ns/orders/sa/order-api
spiffe://example.internal/ns/inventory/sa/inventory-api
~~~

Đây chỉ là **SPIFFE ID minh họa**. Cấu trúc path cụ thể phụ thuộc registration/configuration; không nên suy luận tự động rằng mọi SPIFFE ID phải có `/ns/.../sa/...`.

### 10.1. Các thành phần khái niệm

- **Trust domain:** miền tin cậy tạo ranh giới cấp identity.
- **Workload attestation:** chứng minh một workload/runtime có đủ điều kiện nhận identity.
- **SVID:** credential mang danh tính SPIFFE; có thể là **X.509-SVID** hoặc **JWT-SVID** theo use case.
- **Workload API:** giao diện phân phối credential ngắn hạn tới workload được cấp.
- **Trust bundle:** khóa/chứng chỉ để xác minh peer identity.
- **Registration/selector:** ánh xạ thuộc tính môi trường tới workload ID.

### 10.2. Lợi ích và giới hạn

- Giảm việc cấu hình password riêng cho mỗi service.
- Hỗ trợ identity nhất quán qua pod/container/VM theo thiết kế.
- Credential ngắn hạn và rotation tự động có thể giảm phơi lộ dài hạn.
- mTLS cùng SPIFFE ID có thể tạo identity rõ tại service mesh.

Nhưng:

- **Workload attestation** có thể bị lạm dụng nếu selector hoặc runtime boundary sai.
- CA/trust bundle bị chiếm có tác động lớn.
- Credential được cấp đúng không đồng nghĩa policy API đúng.
- Trust giữa hai domain cần cấu hình federation rõ ràng; không mặc định tin mọi trust domain.
- Cần xử lý node compromise, privilege escalation, certificate/token renewal và service retirement.

**SPIFFE/SPIRE không tự thay thế IGA, owner approval, authorization hoặc audit.**

## 11. Kubernetes ServiceAccount và workload identity

Kubernetes cung cấp **ServiceAccount** làm danh tính trong cụm. Pod có thể nhận **projected service account token** với audience/thời hạn theo cơ chế hỗ trợ; quyền với Kubernetes API được quản lý bởi RBAC, còn quyền gọi hệ ngoài phụ thuộc vào federation và target IAM.

### 11.1. Các lớp khác nhau

~~~text
Kubernetes ServiceAccount:
  namespace = payments
  name = settlement-worker

Kubernetes RBAC:
  được phép làm gì với Kubernetes API?

External cloud/API federation:
  issuer + service account subject + audience
  -> mapped external workload principal
  -> target IAM roles/scopes
~~~

**Có Kubernetes ServiceAccount không tự đồng nghĩa được phép truy cập cloud storage, database hoặc mọi dịch vụ ngoài cluster.**

### 11.2. Những điều nên bảo vệ

- Mỗi workload/namespace dùng ServiceAccount theo nhu cầu, tránh dùng `default` chung cho nhiều thành phần rủi ro khác nhau.
- Giới hạn permissions RBAC, đặc biệt các verb nhạy cảm và việc truy cập `secrets`.
- Không tự mount service account token ở pod **không cần** gọi Kubernetes API hoặc external federation; xem xét `automountServiceAccountToken`.
- Hạn chế ai có quyền tạo pod, chọn serviceAccountName hoặc đọc token được mount.
- Kết nối tới cloud IAM phải ràng buộc issuer, subject, audience, namespace/service account và môi trường.
- Tránh cấp role cloud quá rộng cho cả namespace mà không cân nhắc workload attestation.
- Kiểm vòng đời khi pod/ServiceAccount bị xóa: **external IAM role/trust có được thu hồi không?**

### 11.3. Kẻ tấn công chiếm pod

Nếu pod bị chiếm, attacker có thể sử dụng **credential mà pod đã được cấp**, dù credential ngắn hạn. Do đó:

- Workload identity là cơ sở attribution, **không ngăn malware sử dụng quyền hợp lệ trong thời gian còn sống**.
- Áp least privilege, image/runtime hardening, network policy, egress controls, resource authorization và giám sát.
- Token ngắn hạn giảm thời gian khai thác về sau nhưng không tự chặn hành vi tức thời.
- Thu hồi cần tính tới external access tokens đã phát, cache và token exchange.

## 12. Cloud managed identity và workload identity federation

Cloud thường có cơ chế **managed identity, instance/service role hoặc workload identity federation** để workload nhận token theo chứng thực môi trường mà không cần lưu credential lâu dài trong code.

### 12.1. Nguyên tắc

~~~text
Runtime được cloud/platform chứng thực
  -> Yêu cầu token có audience/resource cụ thể
  -> Platform/authorization server phát short-lived token
  -> Workload gọi API với token đó
  -> API kiểm identity và IAM policy
~~~

Phương thức cụ thể khác nhau giữa các nhà cung cấp; phải làm theo tài liệu của nền tảng để xác định các điều kiện issuer, audience, subject/trust, token lifetimes và role assignment.

### 12.2. Không biến metadata endpoint thành đường cấp quyền không kiểm soát

Một số cloud runtime cấp token qua endpoint metadata/agent. Nếu ứng dụng dễ bị **SSRF**, process bị chiếm hoặc có các thành phần cùng chia sẻ môi trường quyền cao, kẻ tấn công có thể truy xuất hoặc lạm dụng credential.

Cần:

- Cơ chế bảo vệ metadata endpoint được nền tảng hỗ trợ.
- Hardening process/container và quyền gọi metadata.
- Least privilege cho role/workload.
- Phân đoạn trust giữa các tenant và môi trường.
- Giám sát hành vi API bất thường.
- Không phát token cho audience không cần thiết.

### 12.3. Federation không có nghĩa tin toàn bộ CI/CD provider

Một trust policy chỉ kiểm issuer nhưng chấp nhận mọi repository/branch/job của provider có thể mở quyền cloud rộng cho workload không đúng. Cần ràng buộc **subject/claims đã xác minh, repository/project, environment, branch/ref hoặc deployment context** tùy provider hỗ trợ và risk.

Khi pipeline bị đổi chủ, repository chuyển organization hoặc dự án decommission, IAM phải xem lại **federated trust và role assignments**, không chỉ xóa một secret khỏi CI/CD.

## 13. Service mesh và sidecar identity

Một **service mesh** có thể hỗ trợ mTLS, cấp workload certificates, chính sách traffic và telemetry giữa service instances. Điều này giúp nhất quán hóa transport security, nhưng cần nhìn rõ các giới hạn.

### 13.1. Các ranh giới thường bị bỏ sót

- Sidecar xử lý mTLS, nhưng ứng dụng backend vẫn có endpoint mở nếu kết nối không qua sidecar.
- Policy mesh cho phép service A gọi B nhưng **không biết A đang đọc record của tenant nào**.
- Traffic egress đến SaaS bên ngoài có thể không được bao phủ bởi mTLS mesh.
- Một số đường admin, cronjob, WebSocket hoặc asynchronous messages có thể cần kiểm riêng.
- Hệ thống cấp certificate mesh có thể trở thành critical trust component.
- “Strict mTLS” trong một namespace không tự chứng minh backend đã enforce **business authorization**.

### 13.2. Defense in depth

Một mô hình thường hữu ích:

1. **Mesh/network layer:** xác thực workload peer, encryption, giới hạn mạng.
2. **Gateway/API layer:** kiểm token/audience, rate limit, policy và tenant routing.
3. **Application/business PEP:** kiểm action/resource/owner và domain-specific constraints.
4. **Data layer:** row-level/tenant isolation và database permissions phù hợp.
5. **Audit/reconciliation:** đối soát identity, policy, truy cập thật.

Không buộc mọi lớp lặp cùng logic nếu gây lỗi, nhưng phải rõ **lớp nào chịu trách nhiệm ngăn bypass**.

## 14. Static secret, client certificate và token ngắn hạn

| Cơ chế | Ưu điểm | Rủi ro và điều kiện |
| --- | --- | --- |
| **Static API key** | Tích hợp đơn giản ở hệ legacy | Dễ sao chép, khó attribution, thường thiếu audience/expiry |
| **Client secret OAuth** | Được nhiều IdP hỗ trợ | Cần secret store, rotation, tránh leak qua logs/code |
| **Private-key JWT client auth** | Không gửi shared secret trực tiếp mỗi lần lấy token | Bảo vệ private key, replay controls, key registration/rotation |
| **mTLS certificate** | Xác thực peer mạnh khi kiểm đúng chain/identity | PKI, renewal, trust policy và kết nối proxy |
| **Short-lived JWT access token** | Kiểm offline nhanh, scope/audience rõ nếu profile đủ | Replay tới khi hết hạn, key/JWKS caching, revocation khó hơn |
| **Opaque token + introspection** | Có thể kiểm active status tập trung | Phụ thuộc availability/latency của introspection |
| **Managed/workload identity** | Giảm credential tĩnh trong ứng dụng | Phụ thuộc runtime attestation, cloud/platform trust và role mapping |
| **SPIFFE X.509-SVID** | Danh tính workload và mTLS theo trust domain | Phải quản lý CA, attestation, workload API và authorization |

Một hệ có thể kết hợp chúng, ví dụ **mTLS client authentication ở token endpoint** rồi phát **sender-constrained access token** để gọi API.

### 14.1. Không tạo ranking phổ quát

Không thể nói mọi API đều “mTLS tốt hơn OAuth” hoặc ngược lại. mTLS nhận diện peer ở tầng kết nối; OAuth token thường biểu diễn audience/scopes/delegation ở tầng API. Thiết kế dựa trên **threat model, hệ sinh thái, kết nối qua proxy, khả năng rotate, authorization granularity và operational complexity**.

## 15. Bearer token và proof-of-possession

**Bearer token** có tính chất quan trọng: **ai giữ token có thể sử dụng nó** trong phạm vi mà resource server chấp nhận, trừ khi có các ràng buộc bổ sung.

Một access token bị rò rỉ qua log/trace hoặc máy bị chiếm có thể bị replay trước khi hết hạn.

### 15.1. Sender-constrained token

Một số hệ hỗ trợ **token binding/sender constraint**, ví dụ:

- **OAuth mTLS certificate-bound access token:** resource server kiểm token ràng buộc với client certificate tương ứng.
- **DPoP (Demonstrating Proof-of-Possession):** client chứng minh sở hữu khóa gắn token bằng proof phù hợp HTTP request; cần kiểm method, URL, time/jti/replay controls và các ràng buộc của profile.

Cơ chế cụ thể phụ thuộc provider, client và API. Không nên tự phát minh claim binding rồi coi là chuẩn.

### 15.2. Sender constraint vẫn có giới hạn

Nếu attacker chiếm **cả workload process và private key**, nó có thể dùng token ngay trong môi trường đó. Sender constraint giảm một số kịch bản **token exfiltration/replay từ nơi khác**, không thay thế runtime hardening và least privilege.

## 16. Authorization: service được phép làm gì?

Một dịch vụ đã xác thực thường có **quyền riêng**; không nên cấp wildcard chỉ vì nó là thành phần nội bộ.

### 16.1. Mẫu policy RBAC/ABAC/PBAC

~~~text
PERMIT inventory.stock.read WHEN
    caller.workloadId == "orders-prod"
    AND caller.environment == "production"
    AND caller.token.audience == "inventory-api"
    AND caller.hasScope("inventory.read")
    AND caller.tenantId == resource.tenantId
    AND NOT caller.securityBlocked
    AND resource.lifecycleStatus == "ACTIVE"
ELSE DENY
~~~

Mã giả minh họa. Những thuộc tính `workloadId`, environment, scope, tenant phải từ **credential/trust source đã xác minh hoặc trusted context**, không từ header/body untrusted.

### 16.2. Role riêng cho read và write

| Principal | Quyền được phép | Không nên có |
| --- | --- | --- |
| `orders-prod` | `inventory.read` trên tenant được gán | `inventory.admin` hoặc sửa tồn kho không được duyệt |
| `settlement-prod` | `payment.status.write` trên đơn hợp lệ | Xuất dữ liệu khách hàng toàn hệ |
| `reporting-batch` | `aggregate.read` trong kỳ báo cáo | `user.role.grant` |
| `deploy-pipeline` | `deployment.create` trên environment được duyệt | `secret.admin` toàn organization |
| `identity-provisioner` | `user.create/update/disable` trên ứng dụng trong scope | Tự cấp superadmin hoặc xóa audit |

### 16.3. Tenant isolation

Một workload có token cho tenant-a **không được tự yêu cầu `tenant=b` trong URL rồi truy cập dữ liệu tenant-b**. Backend PEP phải xác định allowed tenant set từ policy/ownership đáng tin và kiểm resource thật.

**Client credentials token có scope rộng ở API không tự quyết định entitlement theo từng tenant.**

### 16.4. Service owner không tự là resource owner

Đội vận hành Order Service có thể kiểm soát deployment của Order, nhưng không tự có quyền cấp cho mình API export mọi dữ liệu Finance. Cần **resource owner approval** và policy quản trị phân quyền tương ứng.

## 17. Các trường hợp S2S không dùng HTTP

Service-to-service auth còn xuất hiện trong **message queue, event streaming, database connections, gRPC, file transfer và batch protocols**.

### 17.1. Message broker

~~~text
Publisher -> Broker -> Topic -> Consumer
~~~

Cần phân biệt:

- **Producer authentication:** ai được publish topic?
- **Producer authorization:** được publish event nào, tenant nào?
- **Consumer authentication:** consumer group/workload nào được subscribe?
- **Consumer authorization:** được đọc topic/partition/scope nào?
- **Message authenticity:** consumer có tin nguồn event qua broker không?
- **Replay/idempotency:** event cũ có gây action đặc quyền mới không?
- **Dead-letter/retry:** authorization decision phải được kiểm theo trạng thái hiện hành nếu event tác động quyền.

Một message broker kiểm được producer connection không tự bảo đảm **nội dung event không mạo danh người dùng** hoặc không có consumer misuse.

### 17.2. gRPC

gRPC thường dùng TLS/mTLS và metadata cho token hoặc identity. Nếu proxy chuyển identity tới backend, phải bảo vệ metadata tương tự HTTP headers.

### 17.3. Database

Một service có thể đăng nhập database bằng **managed identity, certificate hoặc database account**. Ngoài authentication, database roles/row-level policies cần giới hạn tables, schemas, tenant và thao tác; không cấp quyền DBA cho application bình thường.

### 17.4. Batch và file transfer

Automation SFTP hoặc ETL cũng có service identity, key lifecycle, source/destination authorization, logging, owner và expiry. Không mặc định rằng vì không có REST API nên không cần xác thực S2S.

## 18. Ví dụ Java/Spring Security: bảo vệ resource server

Trong Java, một API dùng **Spring Security OAuth 2.0 Resource Server** có thể xác minh access token từ authorization server được tin cậy. Ví dụ sau chỉ trình bày **sườn thiết kế**, không phải một ứng dụng độc lập đầy đủ.

### 18.1. Xác thực token trước khi vào nghiệp vụ

~~~java
// Ví dụ theo hướng Spring Security hiện đại.
// Cần cấu hình issuer/JWK, validator và dependency tương thích.
@Configuration
@EnableWebSecurity
@EnableMethodSecurity
class InventoryApiSecurity {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {
        http
            .authorizeHttpRequests(requests -> requests
                .requestMatchers("/actuator/health").permitAll()
                .anyRequest().authenticated()
            )
            .oauth2ResourceServer(resource -> resource
                .jwt(Customizer.withDefaults())
            );
        return http.build();
    }
}
~~~

Ví dụ này yêu cầu API có danh tính đã xác thực, **chưa đủ để bảo đảm đúng audience, scopes, tenant và quyền trên resource**. Phải cấu hình `JwtDecoder`/validator thích hợp; không coi `.authenticated()` là “được phép mọi API”.

### 18.2. Kiểm issuer và audience rõ ràng

~~~java
// Các import/bean bổ sung tùy phiên bản Spring Security.
@Bean
JwtDecoder jwtDecoder(
        @Value("${security.trusted-issuer}") String issuer,
        @Value("${security.inventory-audience}") String audience) {

    NimbusJwtDecoder decoder = JwtDecoders.fromIssuerLocation(issuer);

    OAuth2TokenValidator<Jwt> defaultChecks =
        JwtValidators.createDefaultWithIssuer(issuer);

    OAuth2TokenValidator<Jwt> audienceCheck = jwt ->
        jwt.getAudience().contains(audience)
            ? OAuth2TokenValidatorResult.success()
            : OAuth2TokenValidatorResult.failure(
                new OAuth2Error(
                    "invalid_token",
                    "Unexpected access token audience",
                    null
                )
            );

    decoder.setJwtValidator(
        new DelegatingOAuth2TokenValidator<>(
            defaultChecks,
            audienceCheck
        )
    );
    return decoder;
}
~~~

Đoạn mã hướng dẫn cơ chế **issuer, signature/key, thời gian và audience**; phải kiểm phiên bản thư viện và **JWT access-token profile thực tế**. Với opaque token cần dùng phương thức introspection phù hợp thay vì JWT decoder.

### 18.3. Phân quyền theo service, action và tenant

~~~java
@Service
class InventoryQueryService {

    @PreAuthorize(
        "@servicePolicy.canReadInventory(authentication, #tenantId)"
    )
    public InventoryReport readStock(String tenantId, String sku) {
        // Truy vấn dữ liệu phải ràng buộc đúng tenant được cho phép.
        return inventoryRepository.findReport(tenantId, sku);
    }
}
~~~

Bean `servicePolicy` và các type dữ liệu chỉ mang tính minh họa. Việc kiểm `tenantId` từ request không đủ; cần **so với allowed tenants lấy từ danh tính và policy đã xác minh**, đồng thời query database đúng scope.

### 18.4. Lỗi phổ biến trong Java resource server

- Chỉ kiểm JWT signature rồi cho phép mọi action.
- Chấp nhận token đúng issuer nhưng **audience dành cho API khác**.
- Không giới hạn scopes hoặc ánh xạ `scope` thành role admin quá rộng.
- Tin `X-Caller-Service` thay vì principal đã xác thực.
- Chỉ kiểm route ở HTTP layer, nhưng background job gọi business method trực tiếp.
- Để method security bị bypass qua self-invocation hoặc đường gọi khác.
- Dùng cùng secret trong test/prod.
- Log raw bearer token để debug.
- Chỉ kiểm user claim trong delegated call nhưng bỏ qua **actor workload**.

**API cần có PEP ở mọi đường thực thi nhạy cảm**, không chỉ API controller thông thường.

## 19. Java/Spring: xin token outbound đúng cách

Với một Java service gọi API khác, có thể dùng **Spring Security OAuth2 Client**, credential provider hoặc workload identity SDK theo nền tảng.

### 19.1. Luồng khái niệm

~~~text
Outbound request chuẩn:
  1. Xác định target API và required scope.
  2. Client resolver chọn đúng client registration/workload identity.
  3. Lấy token từ nguồn tin cậy cho đúng audience/resource.
  4. Kiểm token có còn hạn; cache có kiểm soát nếu hỗ trợ.
  5. Gọi HTTPS API tới server identity được xác minh.
  6. Không đưa token vào URL, log hoặc exception.
  7. Xử lý 401/403, timeout và retry theo policy.
~~~

### 19.2. Pseudocode client Java

~~~java
// PSEUDOCODE: CredentialProvider/AuthorizedToken là abstraction minh họa.
class InventoryClient {
    private final CredentialProvider credentials;
    private final HttpClient client;

    InventoryResponse fetchStock(String tenantId, String sku) {
        AuthorizedToken token = credentials.forAudienceAndScope(
            "inventory-api",
            "inventory.read"
        );

        URI endpoint = trustedInventoryUri(tenantId, sku);

        return client.get(endpoint)
            .bearerAuth(token.value())
            .withTlsServerVerification()
            .executeAndDecode(InventoryResponse.class);
    }
}
~~~

Các method như `.bearerAuth()` hoặc `.withTlsServerVerification()` là **pseudocode**, không đại diện cho một Java HTTP client cụ thể. Triển khai thực tế cần framework/SDK có hỗ trợ token acquisition và TLS đúng cách.

### 19.3. Quy tắc outbound quan trọng

- Chọn token cho **đúng API**; không dùng một global token cho mọi downstream.
- Không gửi Authorization header qua redirect tới host không nằm trong allowlist.
- Bảo vệ token khỏi accidental logging, URL/query, metrics và memory dumps khi khả thi.
- Retry request có side effect chỉ khi **idempotency** được thiết kế.
- Nếu client credential/token bị revoke, **không fallback** sang một service account chia sẻ có quyền rộng hơn.
- Gắn traceId/requestId nhưng không coi traceId là chứng cứ danh tính.
- Validate TLS hostname/certificate; không disable certificate validation để sửa lỗi kết nối.

## 20. Identity issuance, secret store và certificate lifecycle

Credential S2S phải được cấp **cho đúng workload, từ nguồn có thẩm quyền**, với cơ chế tạo, phân phối, luân chuyển và thu hồi rõ.

### 20.1. Vòng đời credential

~~~mermaid
stateDiagram-v2
    [*] --> REQUESTED
    REQUESTED --> ATTESTING: Verify workload and owner
    ATTESTING --> DENIED: Policy/attestation fail
    ATTESTING --> ISSUED: Valid workload and scope
    ISSUED --> ACTIVE: Loaded by expected runtime
    ACTIVE --> RENEWING: Before expiration
    RENEWING --> ACTIVE: New credential validated
    ACTIVE --> REVOKED: Compromise/decommission
    ACTIVE --> EXPIRED: Time limit reached
    EXPIRED --> [*]
    REVOKED --> [*]
    DENIED --> [*]
~~~

Trạng thái là mô hình logic, không phải tiêu chuẩn của mọi certificate authority hoặc token issuer.

### 20.2. Cấp và phân phối credential

- Định danh workload từ **platform attestation, cloud identity hoặc client registration** đáng tin.
- Không dùng tên service trong request JSON làm bằng chứng workload thật.
- Hạn chế người có thể tạo client secret, sign assertion, đăng ký certificate hoặc role.
- Giữ private keys/secret trong KMS, vault, keystore hoặc cơ chế nền tảng phù hợp.
- Không đóng secret vào source repository, image container, file cấu hình công khai hoặc CI build logs.
- Tách production, staging, development và các trust domains.
- Ghi issuer, principal, owner, purpose, target audience, permissions và expiry.
- Có **rotation overlap** hợp lý để tránh outage khi thay khóa/chứng chỉ.
- Theo dõi credential chưa dùng, quá lâu không rotate, hoặc cấp ra ngoài nền tảng được phép.

### 20.3. Rotation không đồng nghĩa revoke hết mọi token

Nếu OAuth client secret đã rotate, những **access token phát trước đó** có thể còn hợp lệ đến expiry hoặc bị thu hồi theo cơ chế riêng. Tương tự, certificate cũ có thể còn trong cache/trust nếu chưa hết hạn hoặc chưa bị ngừng chấp nhận.

Cần quản trị **client secret, private key, certificate, trust bundle, access token và session** như những đối tượng liên quan nhưng không đồng nhất.

### 20.4. Key compromise

Khi phát hiện private key hoặc client secret bị lộ:

1. Xác định scope và workload nào dùng credential.
2. Tạo alert/incident, bảo vệ evidence.
3. Chặn hoặc giới hạn principal/credential theo khả năng.
4. Rotate/reissue, cập nhật trust, kiểm audience và role assignments.
5. Kiểm các token đã phát còn được chấp nhận không.
6. Điều tra API access/privilege changes và lateral movement.
7. Khôi phục khả dụng có kiểm soát và theo dõi hậu sự cố.

Không vội xóa mọi evidence hoặc chỉ đổi một secret rồi đóng incident khi còn **token/role tồn dư**.

## 21. Failure modes: khi issuer, verifier hoặc PKI gặp sự cố

Một hệ S2S production phải cân nhắc **bảo mật và availability** khi không cấp/kiểm credential được.

| Sự cố | Nguy cơ | Hướng xử lý |
| --- | --- | --- |
| **Authorization server outage** | Không lấy token mới | Cache token còn hiệu lực theo policy; retry có giới hạn |
| **JWKS endpoint unreachable** | Không cập nhật khóa xác minh | Cache trusted keys theo TTL và policy; không tự bỏ verify |
| **PIP/entitlement service lỗi** | Thiếu thuộc tính để quyết định | Deny/indeterminate cho hành động nhạy cảm theo policy |
| **Certificate renewal lỗi** | Hết hạn, kết nối thất bại | Alert sớm, kiểm pipeline và overlap có kiểm soát |
| **Trust bundle mismatch** | Peer hợp lệ bị từ chối hoặc sai trust | Quản lý version/rollout/rollback an toàn |
| **Clock skew** | Token/cert bị nhận quá sớm hoặc quá hạn | Đồng bộ thời gian, leeway nhỏ có kiểm soát |
| **Workload identity endpoint lỗi** | Không lấy credential runtime | Sửa issuer/agent, không hardcode bypass |
| **Proxy identity headers bị spoof** | Caller giả mạo workload khác | Chỉ nhận từ trusted proxy với network/trust boundary |
| **Token introspection timeout** | Không xác định active status | Fail-safe theo rủi ro, không PERMIT vô điều kiện |
| **Trust policy rollout lệch phiên bản** | Một region còn tin principal đã revoke | Theo dõi convergence, block nhạy cảm khi cần |

### 21.1. Fail closed không phải tắt bừa toàn doanh nghiệp

Với API chứa dữ liệu đặc biệt nhạy cảm, khi không thể xác minh caller, hành động thường phải bị chặn. Với một số hệ có yêu cầu an toàn vận hành cao, tổ chức có thể thiết kế **phương án khẩn cấp bù kiểm soát** riêng.

Điểm quan trọng: **không tự động PERMIT** vì token service hoặc PDP không khả dụng. Phải có runbook, owner và điều kiện risk cụ thể.

### 21.2. Tránh dependency vòng tròn

Nếu service A cần token để gọi authorization server, nhưng authorization server lại phụ thuộc A để phát token, hệ thống có thể không khởi động được sau outage. Cần xét bootstrapping, root of trust và failure domains.

## 22. Service identity inventory và governance

IAM không thể quản lý vòng đời service identity nếu không biết **những principal nào tồn tại và được dùng để làm gì**.

### 22.1. Inventory gợi ý

| Trường | Ví dụ | Ý nghĩa |
| --- | --- | --- |
| **principalId** | `workload:orders-prod` | Định danh duy nhất trong issuer/trust domain |
| **principalType** | `WORKLOAD` | Khác HUMAN |
| **issuer/trustDomain** | `cluster-prod` | Nguồn cấp danh tính |
| **application/serviceId** | `order-service` | Workload logic |
| **environment** | `production` | Phân vùng |
| **ownerTeam** | `commerce-platform` | Người chịu trách nhiệm |
| **technicalOwnerIdentityId** | `person-501` | Liên kết owner với JML |
| **resourceOwner** | `inventory-platform` | Bên quản lý API/secret đích |
| **purpose** | `read stock before checkout` | Lý do nghiệp vụ |
| **allowedAudience** | `inventory-api` | Chặn token reuse |
| **approvedScopes** | `inventory.read` | Quyền |
| **credentialTypes** | `workload-federation` | Cơ chế xác thực |
| **createdAt/lastUsedAt** | Timestamp | Vòng đời, xem xét unused |
| **credentialExpiry** | Theo credential thực | Cảnh báo rotation |
| **decommissionAt** | Theo project | Thu hồi đúng lúc |
| **riskTier/classification** | `MEDIUM` | Chính sách kiểm soát |
| **approvalRefs** | Ticket/decision | Truy vết |
| **observedPrincipals** | Account/role ở API/cloud | Reconciliation |

### 22.2. Một service có thể có nhiều trust relationships

Ví dụ `orders-prod` gọi Inventory API, gửi message tới Kafka và đọc secret từ cloud. Có thể cần **ba tập role/credential khác nhau**, không dùng một key với quyền cả ba nếu có cách phân tách phù hợp.

### 22.3. Owner là con người có JML, principal thì có lifecycle riêng

Khi technical owner nghỉ việc, workload có thể vẫn phải chạy. Phải **thu hồi quyền người cũ, chuyển ownership và rà trust/secret**, không xóa workload sản xuất theo phản xạ. Khi ứng dụng được retire, phải thu hồi **chính workload principal và các role phụ thuộc**.

## 23. Joiner: bổ nhiệm người quản trị service identity

**Joiner** trong HRIS thường là sự kiện một nhân viên bắt đầu làm việc. Nó **không trực tiếp tạo quyền production cho workload**, nhưng ảnh hưởng những người có thể quản lý service principals.

### 23.1. Khi người mới gia nhập platform team

1. Identity proofing và HRIS xác nhận identityId, workerType, effectiveAt.
2. IdP/SSO provision account nhân sự, MFA/passkey và role phù hợp.
3. IAM/IGA xác định eligibility quản trị **client registrations, KMS, vault và cloud trust policies**.
4. Resource owner/security phê duyệt quyền nhạy cảm và áp SoD.
5. Nhân viên được cấp quyền tạo hoặc rotate workload credentials khi thực sự cần.
6. Có audit theo **human identity** cho thay đổi service identity.
7. Workload vẫn dùng **machine principal riêng**, không dùng user token của nhân viên làm credential lâu dài.
8. Reconciliation xác minh không có user privilege hoặc client secret cấp sớm ngoài quy trình.

### 23.2. Người mới tạo một workload

Việc một người tạo repository/pipeline mới không tự tạo quyền cloud admin. Cần **workload registration, owner, business purpose, target scopes, environment và approval** trước khi cấp trust/role.

### 23.3. Preboarding không phải service admin

Một người có SSO account trước `employment effectiveAt` không tự có quyền xem vault secrets hoặc tạo client với privilege production.

## 24. Mover: ownership và quyền workload khi nhân viên chuyển vai trò

**Mover** có thể đổi owner kỹ thuật, team, project, repository hoặc deployment pipeline. Những thay đổi này có thể làm **trust policy và credentials** không còn phù hợp.

### 24.1. Tình huống

~~~text
Trước:
  Technical owner A thuộc platform-team
  A có quyền tạo client credentials / xem vault
  Workload orders-prod có role inventory.read

Sau Mover:
  A sang finance-team
  Owner workload chuyển tới platform-team/B
  Orders service vẫn cần inventory.read

Yêu cầu:
  - Thu hồi quyền quản trị service identity của A
  - Bàn giao owner, approval, rotation responsibility
  - Kiểm credential từng được A truy cập
  - Workload orders-prod tiếp tục chạy trong scope được duyệt
~~~

### 24.2. Không nhầm Mover của owner với quyền workload

Service có thể vẫn cần quyền gọi Inventory API. **Không tự revoke mọi permission của service vì một người Mover**, nếu điều đó gây outage không cần thiết. Nhưng cũng không để owner cũ giữ quyền tạo key, sửa trust hoặc nâng role.

### 24.3. Khi workload được di chuyển môi trường

Một workload chuyển từ on-premises sang Kubernetes hoặc từ cluster dev sang prod là **workload identity migration**, không chỉ Mover nhân sự. Cần:

- Cấp principal/trust phù hợp môi trường mới.
- Bảo đảm quyền external API chỉ thuộc tenant/environment được duyệt.
- Chuyển credential ngắn hạn, không copy static secret sang prod tùy tiện.
- Xác minh một khoảng rollout đồng thời không làm mở quyền quá rộng.
- Gỡ trust/role cũ sau cutover và reconciliation.
- Kiểm logs, audit caller IDs và credential usage ở môi trường cũ.

## 25. Leaver: thu hồi quyền người quản trị và credential tồn dư

**Leaver** của người từng quản lý service identities tạo rủi ro **bí mật đã biết, quyền chỉnh trust policy và service account owner không còn hiện hành**.

### 25.1. Những việc cần xử lý

- Gỡ account người cũ khỏi IAM admin, cloud IAM, KMS/vault, client registration manager và CI/CD permissions.
- Kiểm những workload credentials người cũ đã được phép xem, tải, copy hoặc mint.
- Rotate/rekey/revoke theo rủi ro, không đổi bừa gây outage mà không có phương án.
- Thu hồi quyền sửa OIDC federation trust, SPIFFE registration, Kubernetes ServiceAccount binding.
- Chuyển owner, responder và alert routing.
- Kiểm token, session và access keys cá nhân còn hiệu lực.
- Reconcile observed entitlements của cả **human principal** và **workload principal**.
- Lưu audit lịch sử của service owner để điều tra, không xóa cùng account.

### 25.2. Service account kỹ thuật không tự mất khi IdP disable người cũ

Ví dụ:

~~~text
18:00 HRIS: A trở thành Leaver
18:01 IdP: A disabled
18:05 A không đăng nhập vào IAM portal nữa

NHƯNG:
  client-secret đã từng copy vẫn còn giá trị
  workload client vẫn có role read.secret
  CI pipeline dùng token do service account phát
~~~

Kết quả offboarding của A **chưa đủ** nếu còn đường dùng credential gắn với khả năng A từng kiểm soát. Cần đánh giá và thu hồi phù hợp, đồng thời không gián đoạn workload hợp lệ.

### 25.3. Khi service principal nghỉ vòng đời

Nếu chính project/ứng dụng kết thúc, cần **decommission workload identity**, gỡ OAuth client, trust, cert issuance, cloud IAM role, K8s ServiceAccount bindings, DB accounts, secrets và mạng/ACL. Không chỉ dừng pod rồi để principal tồn tại vô hạn.

## 26. Workload Join–Change–Retire lifecycle

Bên cạnh JML nhân sự, có thể mô hình hóa vòng đời riêng cho non-human identities:

~~~mermaid
flowchart TD
    REQ["Register workload + owner/purpose"] --> CHECK["Verify identity proof, risk and approvals"]
    CHECK --> ISSUE["Issue principal/credential"]
    ISSUE --> ACTIVE["Operate with limited scope"]
    ACTIVE --> CHANGE["Change deployment/owner/scopes"]
    CHANGE --> REVIEW["Reapprove changes and rotate trust"]
    REVIEW --> ACTIVE
    ACTIVE --> RETIRE["Project retired or workload removed"]
    RETIRE --> REVOKE["Revoke clients, tokens/trust, keys, roles"]
    REVOKE --> RECON["Readback target access / reconciliation"]
    RECON --> Q{"Any residual access?"}
    Q -->|"Yes"| EX["Exception + remediation owner"]
    Q -->|"No"| DONE["Close identity lifecycle + archive audit"]
    EX --> RECON
~~~

### 26.1. Phân biệt trạng thái

| Trạng thái | Ý nghĩa |
| --- | --- |
| **REGISTERED** | Principal/workload được ghi nhận |
| **APPROVED** | Owner/policy đã duyệt phạm vi |
| **PROVISIONED** | Issuer/target đã tạo credential/trust |
| **ACTIVE** | Workload đang sử dụng quyền trong hạn |
| **SUSPENDED** | Không được phép dùng tạm thời |
| **ROTATING** | Credential/trust chuyển giao có kiểm soát |
| **DECOMMISSIONING** | Đang gỡ quyền và account |
| **REVOKED** | Nguồn đã xử lý thu hồi |
| **VERIFIED_REMOVED** | Đích xác nhận không còn quyền hiệu lực trong scope |
| **EXCEPTION** | Không thể xác minh hoặc còn residual access |

**Đã gửi lệnh revoke khác với đã ngăn effective access.** Một external SaaS có thể vẫn chấp nhận token đã phát hoặc giữ local role cho đến khi đồng bộ.

## 27. Delegation và service-to-service on behalf of user

Có hệ thống cần thực hiện nghiệp vụ **thay mặt một người dùng**, ví dụ employee dùng portal để xem báo cáo, service A gọi service B để truy xuất thông tin.

### 27.1. Hai chủ thể phải được phân biệt

~~~text
Human subject:
  person-1042
  từ một login SSO/OIDC được xác thực

Workload actor:
  portal-service-prod
  được xác thực với identity riêng

Action:
  report.read on resource-811

Authorization:
  subject có quyền đọc báo cáo đó?
  workload có quyền gọi reporting API?
  tenant/resource có phù hợp cả hai không?
~~~

Không được chỉ kiểm quyền của service rồi bỏ qua quyền người dùng, cũng không bỏ qua workload authentication chỉ vì user token hợp lệ.

### 27.2. Không truyền user ID bằng header đơn giản

Nếu API B tin `X-User-Id=person-1042` do service A tự gửi mà không có delegated token/trusted proxy contract, một service bị chiếm có thể mạo danh bất kỳ người dùng nào.

Cần dùng **delegation mechanism được issuer/PDP chấp nhận**, cùng token audience/scope hoặc decision context được ký/bảo vệ và audit.

### 27.3. Khi user Mover/Leaver giữa workflow

Một background job bắt đầu khi user ACTIVE, nhưng đến lúc thực thi người đó đã Leaver. Nếu job còn quyền thực hiện thao tác nhạy cảm **nhân danh user**, cần có policy quyết định tính hợp lệ theo current state, approval và nghiệp vụ.

Không mặc định rằng mọi job phải hủy khi người yêu cầu nghỉ việc: có tác vụ hệ thống được doanh nghiệp chấp thuận cần tiếp tục do service owner. Nhưng **quyền được ủy quyền cá nhân** không nên được tái sử dụng mãi sau khi căn cứ đã hết.

## 28. IdP/SSO, SCIM và service-to-service auth

### 28.1. Khác nhau ở vai trò

| Thành phần | Có thể tham gia thế nào? | Không tự làm được |
| --- | --- | --- |
| **IdP/SSO** | Xác thực user, phát token hoặc quản trị client theo nền tảng | Tự cho máy quyền mọi API khi user login thành công |
| **OAuth authorization server** | Xác thực client, phát access token theo grant | Thực thi row-level permission của resource nếu API bỏ qua PEP |
| **SCIM** | Provision/deprovision một số users/groups tại SaaS | Cấp/thu hồi mọi workload certificates/tokens ở mọi hệ |
| **Cloud/K8s identity provider** | Cấp runtime workload credentials | Xác nhận business owner/approval nếu không tích hợp governance |
| **RBAC/ABAC/PBAC** | Định nghĩa quyền theo principal, action/resource/context | Tự xoay vòng secret khi principal bị revoke |
| **PAM/secrets manager** | Bảo vệ credential và privileged workflows | Tự chứng minh token cũ ở target đã hết hiệu lực |
| **Reconciliation** | So desired/observed/effective access | Thay thế mọi runtime enforcement |

### 28.2. Không gán SCIM khả năng không có

Một số nền tảng có cơ chế provisioning service principals riêng; SCIM hỗ trợ schema/endpoint nhất định thường thiên về users/groups. Không được mặc định rằng **SCIM disable user** sẽ thu hồi OAuth client, workload identity, X.509 certificate hoặc cloud role.

Cần inventory từng connector và khả năng **create/update/disable/revoke/verify** thực tế của hệ thống đích.

### 28.3. Federation và SSO không có cùng nghĩa

SSO dành cho người dùng thường giảm số lần đăng nhập. **Workload identity federation** cho phép một hệ tin identity assertion của workload từ trust domain khác để cấp credential theo policy. Dù cùng dùng khái niệm token/federation, **luồng cấp quyền và vòng đời** không giống nhau.

## 29. Audit: chứng minh caller, quyền và kết quả

Một audit event tốt giúp trả lời:

- Workload nào thực sự gọi API?
- Credential/token được phát bởi issuer nào, cho audience nào?
- Request thực hiện action gì trên resource và tenant nào?
- Authorization decision là PERMIT/DENY/INDETERMINATE? Theo policy version nào?
- Thao tác thật có commit thành công không?
- Ai là owner của workload, được cấp quyền vì approval nào?
- Nếu gọi on behalf of user, human subject và actor quan hệ thế nào?
- Khi có incident, có thể truy nguyên về deploy/job/artifact nào không?

### 29.1. Mẫu event minh họa

~~~json
{
  "eventId": "s2s-req-7742",
  "traceId": "trace-20261123-77",
  "callerPrincipalId": "workload:orders-prod",
  "callerType": "WORKLOAD",
  "issuerRef": "trusted-workload-issuer",
  "clientId": "orders-service-prod",
  "audience": "inventory-api",
  "grantedScopes": ["inventory.read"],
  "tokenRef": "nonsecret-token-correlation-ref",
  "targetService": "inventory-api",
  "action": "inventory.stock.read",
  "resourceRef": "sku-412",
  "tenantRef": "tenant-a",
  "ownerTeam": "commerce-platform",
  "policyRevision": "inventory-access-v9",
  "decision": "PERMIT",
  "enforcementOutcome": "EXECUTED",
  "evaluatedAt": "2026-11-23T10:15:00+07:00"
}
~~~

Đây là JSON minh họa, không phải schema chuẩn. Giá trị `tokenRef` phải là **tham chiếu không có khả năng dùng để xác thực**, không phải raw token, secret hay một chuỗi có thể replay.

### 29.2. Decision khác execution

~~~text
Authentication = SUCCESS
Authorization  = DENY
Business action = NOT_EXECUTED
~~~

Và:

~~~text
Authentication = SUCCESS
Authorization  = PERMIT
Database write = FAILED
Business action = NOT_COMMITTED
~~~

Không gom `authenticated=true` hoặc `PERMIT` thành **thao tác đã thực hiện thành công**.

### 29.3. Chống rò rỉ qua log

Không ghi:

- Bearer access/refresh token.
- Client secret, private key, session cookie.
- Full signed assertion có thể dùng lại nếu không cần.
- Thông tin secret store, customer data hoặc PII không phục vụ điều tra.

Ghi **principalId, token fingerprint/tham chiếu an toàn, issuer, audience, outcome và correlation ID** nếu đủ; áp retention/encryption, quyền xem log và SoD.

## 30. Reconciliation: phát hiện quyền service tồn dư

**Reconciliation** so **desired state** từ owner/policy với **observed state** tại authorization server, cloud IAM, K8s, SaaS và API resource; với quyền rủi ro cao cần kiểm **effective access**.

### 30.1. Ba lớp trạng thái

~~~text
DESIRED:
  Workload orders-prod còn ACTIVE, owner commerce-platform.
  Only inventory.read on tenant-a.
  Credential/trust limited to production environment.

OBSERVED:
  OAuth client active with inventory.read + inventory.write.
  Old client secret still enabled.
  K8s ServiceAccount for retired staging deployment still exists.

EFFECTIVE:
  Staging credential có còn lấy token production?
  Inventory API có cho inventory.write?
  Token cũ có được chấp nhận sau revoke?
~~~

### 30.2. Phân loại drift

| Drift | Ví dụ | Hành động |
| --- | --- | --- |
| **ORPHANED_WORKLOAD** | Principal không có owner còn ACTIVE | Gán owner/triage, giới hạn và revoke theo risk |
| **EXTRA_SCOPE** | Client được `inventory.write` ngoài approval | Gỡ grant, kiểm abuse |
| **TRUST_POLICY_DRIFT** | Trust chấp nhận mọi repo/provider | Thu hẹp issuer/subject/audience |
| **CREDENTIAL_RESIDUAL** | Secret cũ còn hiệu lực sau rotation | Revoke và kiểm token |
| **ENVIRONMENT_CROSSOVER** | Staging principal có quyền prod | Chặn trust và role |
| **TOKEN_RESIDUAL** | Token đã phát còn hoạt động sau decommission | Xem TTL/introspection/session strategy |
| **OWNER_GAP** | Service owner Leaver chưa bàn giao | Chuyển owner, rà custody |
| **UNEXPECTED_AUDIENCE** | Token dùng được ở API không đúng đích | Sửa verifier/policy |
| **AUTHN_BYPASS** | Endpoint chỉ tin spoofed header | Sửa PEP/trusted proxy |
| **AUDIT_GAP** | API không ghi principal/decision | Bổ sung telemetry |
| **UNKNOWN** | Không đọc được API trạng thái | Exception, không tự đánh dấu MATCH |

### 30.3. Không tự “sửa drift” bằng cấp thêm quyền

Nếu observed role không khớp desired do dữ liệu nguồn còn mâu thuẫn, không tự bổ sung wildcard permission để service “hoạt động lại”. Hãy xác minh **owner, source of truth, resource scope và approval**, rồi quyết định remediation an toàn.

### 30.4. Chặn quyền trước khi gỡ kỹ thuật hoàn toàn

Nếu connector chưa revoke role kịp, **resource PEP** có thể dùng blocklist/trust-policy change hoặc deny khẩn cấp nếu kiến trúc cho phép. Tuy nhiên phải xác minh không còn đường bypass qua token/cache hoặc API khác.

## 31. Incident response: khi một workload bị chiếm quyền

### 31.1. Dấu hiệu

- Token/secret xuất hiện trong repository hoặc CI logs.
- Service B thấy caller identity gọi action không nằm trong purpose.
- Token cho prod được dùng từ môi trường lạ.
- Tần suất truy xuất dữ liệu hoặc cloud API bất thường.
- Có dấu hiệu replay token/certificate từ hai runtime khác nhau.
- Service đã retire nhưng vẫn gọi API.
- Key rotation hoặc trust bundle bị thay mà không có approval.

### 31.2. Quy trình phản ứng

1. Ghi nhận incident, caller principal, issuer, audience, targets và thời gian.
2. Xác định owner và phạm vi những API/tenant chịu ảnh hưởng.
3. **Contain**: chặn principal/token/certificate/trust hoặc giảm role theo khả năng.
4. Đánh giá tác động tới availability; sử dụng fallback đã được phê duyệt nếu cần.
5. Rotate/reissue secret/cert/token trust; kiểm key và session/token cũ.
6. Rà event logs, deployment records, artifact provenance và hành động được thực thi.
7. Kiểm lateral movement, cấp role mới, tạo service account phụ và thay đổi network.
8. Rebuild workload từ nguồn đáng tin, sửa lỗ hổng SSRF/attestation/secret leakage.
9. Reconcile desired/observed/effective access.
10. Đóng incident với evidence và action items, không chỉ khi HTTP requests trở lại bình thường.

### 31.3. Không gắn toàn bộ hành vi với một developer

Một workload principal do nhiều người deploy và nhiều automation kích hoạt. Audit cần phân biệt **service principal thực hiện request**, **pipeline/run khởi động workload**, **người approve deploy** và **owner chịu trách nhiệm**. Không suy ra developer cuối cùng commit code là actor trực tiếp của mọi API call.

## 32. Case study: Order Service gọi Inventory và Payment

Giả sử hệ thống có:

- **Order API** nhận yêu cầu người dùng qua OIDC SSO.
- **Inventory API** giữ tồn kho của nhiều tenant.
- **Payment API** xử lý nghiệp vụ nhạy cảm.
- **Kubernetes** chạy các service, cloud IAM dùng workload identity federation.
- **IGA/CI/CD** quản lý owner, môi trường, thay đổi quyền và audit.

### 32.1. Trạng thái ban đầu

~~~text
orders-prod principal:
  namespace = commerce-prod
  authorized audience = inventory-api
  scope = inventory.read
  tenants = tenant-a

payments-prod principal:
  audience = payment-api
  scope = settlement.status.update
  dedicated owner/payment approval

orders-staging principal:
  environment = staging
  NO production Inventory API permission
~~~

### 32.2. Request hợp lệ

1. Order Service xác thực bằng workload identity.
2. Lấy access token cho Inventory API đúng audience/scopes.
3. Kết nối qua TLS hoặc mTLS theo môi trường.
4. Inventory xác minh token/peer identity và tenant-bound policy.
5. Inventory trả tồn kho đúng tenant.
6. Audit ghi workload principal, resource, action và outcome.

### 32.3. Cross-tenant attack

Pod orders-prod bị chiếm và cố đọc `tenant-b`. Dù token hợp lệ, **PEP của Inventory phải DENY** vì tenant-b nằm ngoài quyền của workload và/hoặc người dùng được ủy quyền.

**Kết quả cần kiểm:** không có dữ liệu tenant-b trả về; audit chứa authenticated caller và DENY reason; không chỉ báo token valid.

### 32.4. Token substitution

Attacker lấy token của Order dành cho Inventory và gửi sang Payment. Payment phải từ chối do **audience mismatch** và thiếu scope, ngay cả khi issuer/signature hợp lệ.

### 32.5. Mover của technical owner

Nhân viên phụ trách Order chuyển sang đội khác. Workload Order vẫn cần gọi Inventory nhưng người cũ không còn quyền tạo secret, thay trust hay đăng ký client. IAM bàn giao owner, rà credential đã từng được tiếp cận và verify role assignments.

### 32.6. Retire staging workload

Project staging bị đóng. K8s pod bị xóa, nhưng external client OAuth/trust policy vẫn tồn tại. Reconciliation phát hiện principal mồ côi và hoàn tất revoke. **Dừng pod không đủ để xóa quyền S2S**.

### 32.7. Chuỗi điều tra

Khi Inventory thấy request bất thường, SOC tương quan:

~~~text
authenticated workload identity
 -> client registration / trust
 -> namespace, deployment, job/run
 -> cloud API and Inventory audit
 -> tenant/resource action
 -> resource policy
 -> service owner and incident timeline
~~~

Nhờ đó phân biệt truy cập hợp lệ, token replay và misconfiguration.

## 33. Ma trận kiểm thử bảo mật service-to-service

| Ca kiểm thử | Điều kiện | Kỳ vọng |
| --- | --- | --- |
| Token đúng issuer/audience/scope | Workload hợp lệ, resource đúng | PERMIT nếu business policy cũng cho phép |
| Token hết hạn | `exp` đã qua | Reject authentication |
| Token chưa hiệu lực | `nbf` ở tương lai | Reject theo time policy |
| Token sai issuer | Issuer ngoài allowlist | Reject |
| Token sai audience | Token API-A gửi API-B | Reject |
| Token giả chữ ký | Signature bị thay | Reject |
| JWT `alg=none` | Không chữ ký trong profile yêu cầu ký | Reject |
| JWKS URL từ untrusted header | Caller cố chỉ tới khóa của mình | Không tải/trust |
| Scope read dùng cho write | `inventory.read` gọi update | DENY |
| Tenant-a đọc tenant-b | Caller/subject không có quyền | DENY |
| Header spoof | `X-Service-Name=admin` | Không thay trusted identity |
| Client secret bị lộ | Credential bị dùng từ nơi không mong muốn | Alert, contain, rotate theo policy |
| Static secret đã revoke | Token endpoint nhận secret cũ | Reject client auth |
| Token đã phát trước revoke | Vẫn còn unexpired | Theo revocation/TTL policy, kiểm residual |
| mTLS cert từ CA tin cậy nhưng workload sai | Caller không thuộc allowlist | DENY authorization |
| mTLS cert hết hạn | Không còn valid | Reject TLS/peer |
| Server TLS hostname mismatch | Client gọi endpoint giả | Fail connection |
| TLS verification disabled | Client bị MITM trong test | Test fail, sửa config |
| Wrong trust domain | SPIFFE ID domain khác | Không tự chấp nhận |
| K8s default ServiceAccount | Pod không cần API access | Không cấp quyền rộng/mount không cần |
| K8s pod bị chiếm | Token runtime bị lạm dụng | Least privilege, detect, contain |
| Staging principal gọi prod | Environment mismatch | Reject |
| CI federation issuer đúng nhưng repo sai | Claim không nằm trong trust policy | Reject |
| Cloud metadata SSRF | App cố lấy token ngoài scope | Hardening, policy và alert |
| Delegated human token sai audience | A chuyển nguyên token cho B | Reject |
| User Leaver nhưng async job vẫn chạy nhân danh user | Relationship không còn hợp lệ | Revalidate delegation theo policy |
| Owner Leaver | Workload vẫn ACTIVE, admin quyền cũ còn | Thu hồi human quyền; quản lý workload độc lập |
| Workload retired | Client registration vẫn active | Phát hiện và revoke |
| Introspection timeout | Không xác định token active | Fail-safe theo risk |
| PDP/PIP outage | Không biết tenant/role | Không tự permit quyền nhạy cảm |
| Key rotation | Public keys cũ/mới overlap hợp lệ | Không outage nhưng không nhận key bị revoke |
| Bỏ qua gateway/mesh | Gọi backend trực tiếp | Chặn hoặc enforce tại backend |
| Background job bypass HTTP controller | Business method dùng trực tiếp | Policy vẫn enforce |
| Replay message event | Event cũ kích hoạt grant | Idempotency/state version guard |
| Service identity orphan | Không có owner vẫn có role | Exception, triage và revoke |
| Resource owner không approve write | Client xin scope write | Không cấp/không thực thi |

### 33.1. End-to-end test cần chứng minh điều gì?

~~~text
Workload registered and approved
 -> issuer attests correct runtime
 -> credential/token minted with expected audience/scope
 -> TLS/mTLS peer verified
 -> API PEP authenticates correct workload
 -> PDP checks resource/tenant/action
 -> target allows or rejects actual operation
 -> audit correlates actor, owner, decision, outcome
 -> decommission revokes trust/credential/role
 -> readback verifies no residual effective access
~~~

Đừng chỉ test rằng service A gọi API B nhận HTTP 200. **Negative tests** về audience, tenant, credential, role và retirement mới chứng minh được ranh giới bảo vệ.

## 34. KPI và quan sát vận hành

| Chỉ số | Ý nghĩa | Điều cần tránh |
| --- | --- | --- |
| **Workload identity ownership coverage** | Tỷ lệ principal có owner được xác minh | Đếm hostname như owner |
| **Static credential exposure** | Số secrets dài hạn hoặc bị đưa vào code/log | Coi chỉ cần vault là hết rủi ro |
| **Credential rotation/renewal success** | Cấp/đổi khóa đúng hạn, không outage | Chỉ đo số job đã chạy |
| **S2S authentication failure rate** | Lỗi issuer/audience/cert/exp, theo nguyên nhân | Gộp thành lỗi 500 khó điều tra |
| **Unauthorized action denial rate** | Request vượt policy bị chặn | Coi mọi DENY là lỗi hệ thống |
| **Wrong-audience token incidents** | Token dùng cho API không đúng | Bỏ qua audience validation |
| **Cross-tenant policy violations** | Lượt truy cập sai tenant bị phát hiện | Không kiểm resource-level authorization |
| **Residual client/trust count** | Client, cert, secret còn sau retire | Chỉ xóa pod |
| **Privilege drift** | Permission quan sát rộng hơn desired | Tự cấp wildcard để chữa lỗi |
| **Orphaned principals** | Workload không còn owner/purpose | Để tồn tại vô hạn |
| **Revocation-to-enforcement latency** | Thời gian tới khi API thật sự chặn quyền | Chỉ đo revoke request gửi đi |
| **Token/key compromise detection** | Thời gian phát hiện credential sử dụng bất thường | Thiếu audit actor/audience |
| **AuthZ audit completeness** | Có principal, resource, decision, outcome | Log raw bearer token |
| **Federation trust policy coverage** | Trust chỉ cho đúng issuer/subject/environment | Tin toàn bộ CI provider |
| **API PEP coverage** | Endpoint/job nhạy cảm đều kiểm quyền | Chỉ bảo vệ ingress HTTP |

KPI nên phân đoạn theo **production, data classification, tenant, owner và risk tier**, không dùng một con số chung che mất principal nhạy cảm.

## 35. Checklist triển khai service-to-service auth

| Câu hỏi kiểm tra | Bằng chứng mong đợi |
| --- | --- |
| Workload có định danh ổn định riêng với user? | Principal registry, issuer/sub |
| Owner/purpose/environment đã được xác minh? | Inventory và approval refs |
| Mỗi API có trust boundary được mô tả? | Architecture, threat model |
| Client có xác thực đúng token endpoint/issuer? | Client credential settings |
| API kiểm chữ ký/token active và issuer? | JWT/introspection tests |
| API kiểm `aud` đúng riêng cho API? | Audience validation |
| Có kiểm scope/action/resource và tenant? | RBAC/ABAC/PBAC tests |
| Có chặn ID token làm access token? | Negative test |
| Server TLS được xác minh hostname/CA? | TLS config và test |
| Nếu dùng mTLS, có kiểm SAN/trust domain? | Certificate policy |
| Sidecar/proxy identity header có được bảo vệ? | Network isolation, backend auth |
| JWKS có lấy từ trusted issuer và cache hợp lý? | Key rotation test |
| Có xử lý issuer/PDP/PIP outage fail-safe? | Fault test và runbook |
| Có short-lived token/cert nếu phù hợp? | Expiry, renewal config |
| Có rotation/revocation không gây credential tồn dư? | Lifecycle evidence |
| Static secrets có được giữ ngoài code/log? | Secrets management review |
| CI/CD federation ràng buộc repo/environment? | Trust policy tests |
| K8s ServiceAccount có scope tối thiểu? | RBAC và pod token mount audit |
| Managed identity không rộng quyền do shared runtime? | Cloud IAM review |
| Có chặn cross-tenant và staging→prod? | Negative authorization tests |
| Có chống confused deputy trong delegated call? | Token exchange/actor tests |
| Client tokens không bị đưa vào redirect không tin cậy? | HTTP client tests |
| Async event có trusted producer và replay controls? | Broker ACLs, idempotency |
| Database/service accounts có role hẹp? | DB grants, readback |
| Có quy trình khi owner Mover/Leaver? | Human JML + custody review |
| Có quy trình khi workload migrate/decommission? | Principal/role revoke workflow |
| Có quản lý service principals nằm ngoài SCIM? | Inventory và native connectors |
| Có audit caller, action, resource, decision, outcome? | Logs/traces với privacy controls |
| Có phát hiện workload principal mồ côi? | Reconciliation dashboard |
| Có đo effective access sau revoke/rotation? | End-to-end verification |
| Có incident runbook cho compromised token/key? | Tested response playbook |
| Có kiểm các endpoint/background jobs bypass PEP? | Coverage tests |

## 36. Những nhầm lẫn thường gặp

1. **“Trong mạng nội bộ thì không cần xác thực dịch vụ.”** Workload bị chiếm vẫn có thể lateral movement.
2. **“HTTPS chứng minh service gọi là ai.”** TLS thông thường chứng minh server identity; caller cần cơ chế riêng.
3. **“JWT có chữ ký đúng thì quyền nào cũng hợp lệ.”** Vẫn cần audience, scope, tenant và resource authorization.
4. **“Token issuer đúng là đủ.”** Token phát cho API khác không được dùng thay.
5. **“Có OAuth client credentials là đang xác thực người dùng.”** Đây thường là quyền của client/workload.
6. **“ID token OIDC có thể dùng gọi API bất kỳ.”** Resource server cần đúng access token/profile.
7. **“Một client secret dùng cho mọi microservice sẽ dễ quản trị hơn.”** Làm mất isolation và tăng blast radius.
8. **“mTLS certificate từ CA tin cậy cho phép mọi API action.”** Cần kiểm peer identity và policy ứng dụng.
9. **“SPIFFE/SPIRE tự thay thế RBAC/ABAC.”** Chúng cung cấp identity/credential, không tự quyết định quyền nghiệp vụ.
10. **“Service mesh strict mTLS bảo vệ mọi route.”** Backend/egress/side channel vẫn phải kiểm.
11. **“Kubernetes ServiceAccount tự có quyền cloud.”** Quyền ngoài cluster cần federation/target IAM riêng.
12. **“Cloud managed identity nghĩa không có rủi ro credential.”** Pod/process bị chiếm vẫn lạm dụng quyền được cấp.
13. **“Token ngắn hạn không bao giờ bị replay.”** Bearer token vẫn có thể bị dùng trước expiry.
14. **“Sender-constrained token chặn cả attacker chiếm private key.”** Không bảo vệ hoàn toàn khi key/process bị chiếm.
15. **“SCIM disable user sẽ gỡ mọi service principal.”** Workload identity có lifecycle riêng.
16. **“Một người Leaver là workload do họ tạo phải xóa ngay.”** Cần thu hồi quyền người cũ và bàn giao service có mục đích hợp lệ.
17. **“Rotate client secret thì mọi access token lập tức hết hiệu lực.”** Phụ thuộc token validation/revocation.
18. **“Worker đã xóa pod là client OAuth không còn.”** Trust, roles và secrets có thể tồn tại.
19. **“Forward header X-User-Id là đã ủy quyền on-behalf-of.”** Cần delegated identity/trusted context.
20. **“AuthN thành công nghĩa xử lý thành công.”** Authorization và business operation là hai bước độc lập.
21. **“Dịch vụ A có quyền cao có thể làm mọi việc thay user.”** Confused deputy phải được ngăn tại PEP.
22. **“Không có người đăng nhập nên workload không cần audit.”** Owner, principal, pipeline và API action vẫn cần truy vết.
23. **“Mọi request từ cùng IP là cùng service.”** IP không phải danh tính ổn định.
24. **“Không truy được PIP thì cứ PERMIT để giữ availability.”** Cần fail-safe theo risk.
25. **“Cấp permission qua IGA là đủ, không cần readback.”** Reconciliation phải kiểm observed và effective access.

## 37. Câu hỏi tự đánh giá

1. S2S authentication khác user SSO và resource authorization ở những điểm nào?
2. Workload principal ID, service name, runtime instance và owner team khác nhau thế nào?
3. Vì sao một HTTPS connection không tự xác thực caller?
4. OAuth 2.0 client credentials grant thường dùng trong trường hợp nào?
5. Access token khác ID token OIDC ở mục đích sử dụng như thế nào?
6. API cần kiểm những yếu tố nào của JWT access token trước khi xử lý?
7. Vì sao chỉ kiểm issuer mà bỏ qua audience là nguy hiểm?
8. JWT signature hợp lệ có đồng nghĩa được phép truy cập dữ liệu tenant-b không?
9. So sánh JWT offline validation và opaque-token introspection theo khả dụng/revocation.
10. mTLS xác thực được điều gì, còn điều gì phải kiểm ở tầng ứng dụng?
11. Vì sao một certificate từ CA nội bộ vẫn có thể không được phép gọi API nhạy cảm?
12. SPIFFE ID, SVID và workload attestation liên quan nhau thế nào?
13. Kubernetes ServiceAccount có tự cấp quyền truy cập cloud object storage không?
14. Workload identity federation cần kiểm những claims nào để giới hạn CI/CD?
15. Vì sao token ngắn hạn không loại bỏ rủi ro SSRF hoặc pod compromise?
16. Sender-constrained token giảm được loại replay nào?
17. Confused deputy có thể xảy ra ở chuỗi A → B → C như thế nào?
18. Vì sao không nên truyền user identity qua header không được bảo vệ?
19. Java resource server chỉ dùng `.authenticated()` có đủ an toàn không?
20. Trong Mover của service owner, việc nào cần thu hồi và việc nào có thể tiếp tục?
21. Trong Leaver của người từng giữ client secret, vì sao IdP disabled chưa đủ?
22. Vì sao sau khi retire workload phải gỡ trust/roles/token chứ không chỉ dừng pod?
23. SCIM có nhất thiết quản lý được mọi workload principal không?
24. Audit sự kiện S2S nên lưu những trường nào và phải tránh dữ liệu gì?
25. Phân biệt DESIRED, OBSERVED và EFFECTIVE permissions cho service identities.
26. Khi authorization server hoặc JWKS không khả dụng, API nên xử lý ra sao?
27. Nêu ba negative tests cho audience mismatch, cross-tenant access và stale credential.
28. Khi suspect compromised workload, thứ tự các bước containment và recovery hợp lý là gì?
29. Tại sao một backend job bypass HTTP gateway vẫn phải enforce policy?
30. Những KPI nào chứng minh service identity lifecycle có ít quyền tồn dư?

## 38. Ghi nhớ

**Service-to-service auth** là cơ chế **xác thực danh tính của các workload khi chúng gọi API, message broker, database hoặc dịch vụ khác**. Một thiết kế đúng cần đồng thời **xác minh peer/caller, bảo vệ kênh truyền, kiểm token/certificate đúng issuer–audience–time–trust, áp policy cho action/resource/tenant và lưu audit có thể truy vết**. Các phương án như **OAuth 2.0 client credentials, token exchange, mTLS, SPIFFE/SPIRE, Kubernetes ServiceAccount và cloud workload identity federation** cung cấp những khả năng khác nhau; **không cơ chế nào tự thay thế hoàn toàn authorization hoặc lifecycle governance**.

Trong quản lý danh tính **Joiner–Mover–Leaver**, con người thay đổi vai trò và quyền quản trị **service identity**, còn workload có vòng đời **register–issue–operate–rotate–retire** riêng. **IdP/SSO** phục vụ người dùng và trust issuer, **SCIM/API** có thể quản trị một phần tài khoản/entitlement, **RBAC/ABAC/PBAC và PEP** kiểm quyền hiện hành, còn **reconciliation** xác minh credential, trust, role và quyền thực tế sau thay đổi. **Đừng nhầm token còn hợp lệ với quyền hợp lệ, dừng workload với thu hồi principal, hay owner Leaver với việc có thể xóa ngay dịch vụ production.** Mục tiêu là **đúng workload, đúng target, đúng action, đúng thời điểm, có owner và có bằng chứng rằng quyền không còn tồn dư khi nhu cầu kết thúc**.
