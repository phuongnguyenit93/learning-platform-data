# Xác thực giữa service (Service-to-service API authentication)

> **Chương:** Authentication trong API  
> **Module:** SECURITY_AUTHENTICATION_FUNDAMENTALS — tìm hiểu nguyên lý xác thực danh tính từ credential, mật khẩu, MFA, passkey và chứng chỉ đến token, phiên, liên kết danh tính và khôi phục tài khoản. Người học biết mô hình hóa ranh giới tin cậy, phòng chống phishing, replay, lạm dụng đăng nhập và thiết kế luồng xác thực an toàn.
>
> **Trọng tâm:** Thiết kế cách một service chứng minh danh tính khi gọi API của service khác; sử dụng workload identity, OAuth 2.0 client credentials, access token, client authentication và cơ chế ràng buộc token; xác minh token và áp dụng authorization theo audience, scope, resource, tenant; quản lý credential, rotation, revocation, delegation và giám sát trong môi trường phân tán.

## Mục tiêu học tập

Sau bài này, người học có thể:

1. Phân biệt danh tính service, xác thực client tại Authorization Server và xác minh access token tại API.
2. Mô tả luồng OAuth 2.0 Client Credentials và giải thích vì sao nó phù hợp với service hoạt động thay mặt chính nó.
3. So sánh client secret, private_key_jwt, mTLS, workload identity federation và API key.
4. Thiết kế access token có audience và scope phù hợp; phân biệt token opaque với JWT.
5. Xác minh chữ ký, issuer, audience, thời hạn, loại token và các claim theo profile được thống nhất.
6. Áp dụng authorization theo service, action, resource và tenant thay vì chỉ tin rằng client đã xác thực.
7. Phân biệt service-to-service tự thân với service gọi thay mặt người dùng; sử dụng token exchange hoặc delegation khi cần.
8. Quản lý secret, key, certificate, token cache, rotation, revocation và sự cố compromise.
9. Kiểm thử token sai issuer/audience/scope, replay, confused deputy, credential leakage và các tình huống lỗi trong hệ thống phân tán.

## 1. Xác thực giữa service là gì?

**Service-to-service authentication** là quá trình một workload chứng minh danh tính của nó với một service/API khác trước khi được xử lý request. Workload có thể là backend application, worker, scheduled job, API gateway, integration service hoặc workload chạy trong container/VM.

Ví dụ trong một nền tảng học tập:

- Order Service gọi Payment API để tạo payment intent.
- Enrollment Service gọi Course API để kiểm tra quyền ghi danh.
- Notification Worker gọi Messaging API để gửi thông báo.
- Reporting Service gọi Analytics API để lấy dữ liệu theo tenant.

API đích cần biết caller là workload nào và request có được phép thực hiện hay không. Chỉ dựa vào IP nội bộ, tên pod hoặc việc request đến từ cùng một network không đủ để xác minh danh tính.

### Ba câu hỏi phải trả lời

1. **Ai đang gọi?** Service nào, thuộc issuer/trust domain nào, môi trường và tenant nào?
2. **Bằng chứng có hợp lệ không?** Credential/token/chứng chỉ có được cấp bởi nguồn tin cậy, còn hiệu lực và đúng audience không?
3. **Được phép làm gì?** Service có quyền gọi endpoint/action này trên resource và tenant cụ thể không?

Xác thực và authorization là hai quyết định liên quan nhưng khác nhau. Một service có danh tính hợp lệ vẫn có thể không được phép gọi thao tác hoàn tiền hoặc đọc dữ liệu của tenant khác.

## 2. Phân biệt các lớp xác thực API

| Lớp | Câu hỏi | Ví dụ |
| --- | --- | --- |
| **Workload identity** | Process/service nào đang chạy? | SPIFFE ID, cloud workload identity, service account. |
| **Client authentication** | Client chứng minh danh tính với Authorization Server ra sao? | client_secret_basic, private_key_jwt, mTLS. |
| **Token issuance** | Authorization Server cấp quyền truy cập nào? | Access token cho Payment API với scope hẹp. |
| **Token validation** | API đích kiểm tra token có hợp lệ cho mình không? | Signature/introspection, iss, aud, exp. |
| **Authorization** | Caller được thao tác gì trên resource nào? | Chỉ tạo payment intent cho order thuộc tenant đã cấp. |
| **Delegation** | Service đang gọi thay mặt actor nào? | Token exchange hoặc on-behalf-of flow. |

### Một flow có thể có nhiều danh tính

Khi Order Service gọi Payment API thay mặt học viên, có thể tồn tại:

- Workload identity: Order Service.
- Client identity tại Authorization Server: OAuth client đại diện Order Service.
- Subject: học viên khởi tạo đơn.
- Actor: Order Service thực hiện request thay mặt học viên.
- Resource server: Payment API.

Không gộp các danh tính này vào một trường user hoặc client duy nhất. Nếu hệ thống cần biết cả workload lẫn người dùng, token và request context phải thể hiện delegation theo cách được xác minh.

## 3. Các mô hình service authentication phổ biến

| Mô hình | Bằng chứng | Phù hợp khi | Giới hạn chính |
| --- | --- | --- | --- |
| OAuth 2.0 Client Credentials | Client authentication tại Authorization Server và access token. | Service gọi API thay mặt chính nó. | Cần quản lý client credential và token policy. |
| Private key JWT | JWT assertion được ký bằng private key của client. | Client có thể bảo vệ private key và cần tránh shared secret. | Cần quản lý key, audience, assertion expiry và replay. |
| mTLS | Client certificate và proof of private key trong TLS. | Cần xác thực workload ở tầng kết nối hoặc certificate-bound token. | PKI, trust bundle, rotation và TLS termination phức tạp. |
| Workload identity federation | Danh tính từ cloud/orchestrator được đổi lấy credential/token ngắn hạn. | Workload chạy trên cloud hoặc platform có identity provider. | Cần cấu hình trust relationship và claim mapping chính xác. |
| API key | Secret hoặc key identifier do API provider cấp. | Integration đơn giản hoặc hệ thống legacy có scope giới hạn. | Thường là bearer/shared secret, dễ lộ và khó biểu diễn delegation. |
| Signed request / HMAC | Chữ ký hoặc MAC ràng buộc request. | API có giao thức ký request riêng hoặc webhook. | Cần canonicalization, key lifecycle, nonce/timestamp và replay store. |

Một hệ thống có thể kết hợp nhiều lớp. Ví dụ, workload dùng mTLS để xác thực kết nối, OAuth access token để mang audience/scope và policy engine để quyết định quyền theo resource.

## 4. OAuth 2.0 Client Credentials Grant

Client Credentials Grant được định nghĩa trong OAuth 2.0 cho confidential client cần lấy access token để truy cập resource server bằng quyền của chính client. Flow này không có người dùng tương tác trong authorization request.

### Khi nào dùng?

- Background worker cần gọi API nội bộ.
- Service cần đọc dữ liệu hoặc thực hiện tác vụ trong phạm vi quyền của chính nó.
- Scheduled job chạy theo service identity.
- Integration backend đã được đăng ký với Authorization Server.

Không dùng Client Credentials để giả lập đăng nhập người dùng. Token thường đại diện client/service; nếu nghiệp vụ cần hành động thay mặt người dùng, phải có mô hình delegation được cấp và kiểm tra riêng.

### Luồng tổng quát

~~~mermaid
sequenceDiagram
    autonumber
    participant W as Workload / Client
    participant AS as Authorization Server
    participant API as Resource Server
    W->>AS: Token request + client authentication
    AS->>AS: Xác minh client, trạng thái và policy
    AS-->>W: Access token + expires_in
    W->>API: API request + Bearer access token
    API->>API: Xác minh token và authorization
    API-->>W: Response theo quyền được cấp
~~~

### Token request minh họa

~~~http
POST /oauth2/token HTTP/1.1
Host: id.example.edu
Content-Type: application/x-www-form-urlencoded
Authorization: Basic <client-credentials>

grant_type=client_credentials&scope=payments.intent.create
~~~

Ví dụ chỉ minh họa cấu trúc. Client phải dùng token endpoint và phương thức xác thực được đăng ký với Authorization Server. Không gửi client secret trong query string hoặc ghi credential vào log.

### Token response minh họa

~~~json
{
  "access_token": "<opaque-or-jwt-access-token>",
  "token_type": "Bearer",
  "expires_in": 300,
  "scope": "payments.intent.create"
}
~~~

expires_in và scope thực tế do Authorization Server quyết định theo client registration và policy. Client phải sử dụng scope được cấp trong response, không giả định mọi scope đã yêu cầu đều được chấp nhận.

### Điều kiện quan trọng

- Client phải là confidential client và có cách bảo vệ credential phù hợp.
- Token chỉ có quyền cần thiết và audience đúng API đích.
- Access token có thời hạn hợp lý, không dùng vô thời hạn.
- API đích vẫn xác minh token và authorization.
- Client credential không được đưa vào browser/mobile app public như một secret có thể giữ kín.

## 5. Client authentication tại Authorization Server

Client Credentials Grant chỉ là loại grant. Client vẫn phải chứng minh danh tính với token endpoint theo một phương thức được đăng ký.

### Client secret

Các phương thức có thể gồm:

- **client_secret_basic:** gửi client ID/secret qua HTTP Basic trên TLS.
- **client_secret_post:** gửi credential trong form body; thường nên tránh nếu phương thức khác phù hợp vì dễ bị log hoặc xử lý sai.
- Secret được cấp riêng cho từng client và môi trường.

Secret phải được lưu trong secret manager hoặc cơ chế bảo vệ tương đương. Không đặt secret trong source code, image, file cấu hình commit vào Git, URL hoặc log.

### Private key JWT

Client tạo JWT assertion và ký bằng private key của mình. Authorization Server xác minh chữ ký bằng public key đã đăng ký.

Các claim thường cần theo profile, ví dụ:

- iss: client identifier.
- sub: client identifier.
- aud: token endpoint hoặc audience được Authorization Server yêu cầu.
- iat: thời điểm tạo.
- exp: thời hạn ngắn.
- jti: identifier duy nhất để hỗ trợ chống replay.

JWT assertion phải có thời hạn ngắn, audience đúng và được xử lý theo quy tắc one-time/replay của Authorization Server. Không dùng một assertion dài hạn hoặc phát lại vô hạn.

### mTLS client authentication

Client chứng minh quyền giữ private key của certificate trong TLS handshake với token endpoint. Authorization Server ánh xạ certificate sang OAuth client đã đăng ký.

mTLS client authentication là một cách xác thực client ở token endpoint. Nó cũng có thể được dùng để ràng buộc access token với certificate theo RFC 8705. Chỉ bật TLS hai chiều ở network mà không có mapping client identity và policy rõ ràng là chưa đủ.

### Chọn phương thức

| Điều kiện | Lựa chọn có thể phù hợp |
| --- | --- |
| Secret manager và client registration đơn giản | Client secret có rotation ngắn hạn. |
| Có PKI/key management và muốn tránh shared secret | private_key_jwt. |
| Có workload certificate lifecycle tốt | mTLS client authentication. |
| Cloud platform có workload identity provider | Federation/exchange lấy token ngắn hạn. |

Không có phương thức nào tự động an toàn nếu private key, secret, issuer metadata hoặc client registration bị quản lý yếu.

## 6. Workload identity và federation

Workload identity là danh tính được gán cho service đang chạy, thường dựa trên môi trường thực thi và thuộc tính được platform xác minh.

Nguồn có thể gồm:

- Kubernetes service account.
- Cloud workload identity.
- VM instance identity.
- SPIFFE/SPIRE.
- Managed identity của cloud provider.
- Certificate do internal CA cấp.

### Vì sao nên dùng workload identity?

Một service có thể lấy credential ngắn hạn dựa trên danh tính runtime mà không cần nhúng secret dài hạn vào image hoặc source code. Authorization Server hoặc identity broker xác minh assertion của platform rồi cấp token cho API.

~~~mermaid
flowchart TD
    W["Workload đang chạy"] --> P["Platform identity / attestation"]
    P --> B["Identity broker / STS"]
    B --> V["Xác minh issuer, subject và claims"]
    V --> T["Cấp token ngắn hạn cho audience"]
    T --> API["Resource API"]
    API --> A["Validate token và authorization"]
~~~

### Federation cần ràng buộc chính xác

- Chỉ tin issuer đã cấu hình.
- Kiểm tra subject/service account/workload attributes theo allowlist.
- Giới hạn audience để assertion không bị dùng ở broker/API khác.
- Kiểm tra thời hạn và chữ ký.
- Không cho phép mọi pod trong cluster nhận cùng quyền.
- Tách trust theo environment, tenant và workload role.
- Có quy trình khi cloud identity, node hoặc control plane bị compromise.

Không coi tên namespace hoặc label do workload tự khai là bằng chứng nếu platform không xác minh chúng.

## 7. Access token là gì và token đại diện cho điều gì?

Access token là credential được Authorization Server phát hành để client truy cập resource server trong phạm vi được cấp. Token có thể opaque hoặc self-contained JWT.

Với Client Credentials, token thường đại diện client/service. Các claim và cách biểu diễn subject phụ thuộc issuer và profile. Không được giả định mọi access token có cùng schema.

### Token nên giới hạn theo

- **Issuer:** bên phát hành được API tin cậy.
- **Audience:** API/resource server dự định nhận token.
- **Scope/permission:** thao tác được phép.
- **Subject/client:** principal mà token đại diện.
- **Expiration:** thời gian token có thể được chấp nhận.
- **Tenant/resource context:** phạm vi dữ liệu nếu kiến trúc sử dụng.
- **Sender constraint:** ràng buộc token với certificate hoặc proof-of-possession khi cần.

Một token dành cho Reporting API không được mặc nhiên chấp nhận ở Payment API. Audience restriction giảm nguy cơ token bị dùng nhầm ở service khác.

### Không dùng ID token để gọi API

OIDC ID token được phát hành cho client để truyền thông tin về authentication event và subject trong login flow. Access token dành cho resource server. API không nên chấp nhận ID token thay access token chỉ vì cả hai đều là JWT.

## 8. JWT access token: xác minh đúng profile

JWT là định dạng token có thể được xác minh bằng chữ ký hoặc MAC theo profile. Decode payload không có nghĩa token đáng tin.

Resource server cần xác minh tối thiểu theo hợp đồng issuer:

1. Chữ ký bằng key thuộc issuer đã cấu hình.
2. Algorithm nằm trong allowlist; không tin lựa chọn algorithm tùy tiện từ header.
3. iss khớp chính xác issuer được tin cậy.
4. aud chứa đúng identifier của API này.
5. exp chưa hết hạn và nbf đã có hiệu lực nếu có.
6. iat nằm trong giới hạn hợp lý theo policy.
7. Token type/profile phù hợp với access token mà API chấp nhận.
8. Scope/permission đủ cho action.
9. Các claim bắt buộc theo profile nội bộ có mặt và đúng kiểu.
10. Token không bị revoke hoặc denylist nếu kiến trúc yêu cầu kiểm tra trạng thái.

Nếu sử dụng JWT Access Token Profile theo RFC 9068, resource server cần tuân thủ các yêu cầu profile tương ứng, gồm typ và claim semantics. Với issuer khác, phải theo metadata và contract đã thống nhất thay vì áp giả định chung.

### JWKS và key rotation

Authorization Server thường công bố public signing keys qua JWKS endpoint. Resource server nên:

- Cấu hình issuer và JWKS URI từ nguồn tin cậy.
- Cache key theo policy và hỗ trợ key rotation.
- Khi gặp kid chưa biết, refresh JWKS có giới hạn để tránh request storm.
- Không tự tải jku hoặc x5u tùy ý từ token header.
- Không chấp nhận key hoặc issuer do token tự chỉ định.
- Có kế hoạch overlap key cũ/mới trong thời gian token cũ còn hợp lệ.

### Pseudocode xác minh

~~~text
token = extract_bearer_token(request)

claims = verify_signature_using_trusted_issuer_keys(token)
require_exact_issuer(claims.iss)
require_expected_audience(claims.aud, this_api)
require_valid_time(claims.exp, claims.nbf, allowed_clock_skew)
require_expected_access_token_profile(token.header, claims)
principal = map_client_or_subject(claims)
require_scope_for_action(principal, claims.scope, request.action)
require_tenant_and_resource_access(principal, claims, request.resource)
continue_request()
~~~

Đây là pseudocode. Production cần thư viện JWT/OAuth đã được kiểm chứng, xử lý lỗi nhất quán và không tự viết thuật toán mật mã.

## 9. Opaque token và introspection

Opaque token không công khai claim để resource server tự giải mã. API gửi token tới introspection endpoint của Authorization Server hoặc gateway được tin cậy để hỏi token có active hay không và nhận metadata theo policy.

### Ưu điểm

- Resource server không cần biết cấu trúc nội bộ của token.
- Authorization Server có thể phản ánh trạng thái revoke nhanh hơn.
- Có thể tập trung logic token validity và metadata.
- Token không để lộ claim trực tiếp cho client chỉ từ nội dung token.

### Giới hạn

- Mỗi lần introspection thêm network dependency và latency.
- Authorization Server outage có thể ảnh hưởng API.
- Cache introspection có thể làm chậm hiệu lực revoke.
- Resource server phải xác thực với introspection endpoint.

### Cache policy

Cache active result cần TTL phù hợp với mức nhạy cảm và yêu cầu revoke. Không cache active quá lâu nếu token có thể bị compromise hoặc thu hồi khẩn cấp. Khi introspection unavailable, hành vi fail-open/fail-closed phải được định nghĩa theo loại API và hậu quả.

## 10. Authorization: scope không thay thế kiểm tra resource

Scope thường biểu diễn quyền ở mức API/action, ví dụ:

- enrollment.read
- enrollment.write
- payments.intent.create
- payments.refund
- reports.export

Scope không tự xác định service được truy cập mọi record hoặc tenant. Resource server còn phải kiểm tra:

- Principal có được phép truy cập tenant này không?
- Resource có thuộc tenant/owner hợp lệ không?
- Action có phù hợp trạng thái nghiệp vụ không?
- Có giới hạn amount, quota hoặc transaction risk không?
- Request có đang dùng quyền delegated đúng actor không?

### Ví dụ policy

| Workload principal | Scope | Resource condition | Kết quả |
| --- | --- | --- | --- |
| order-service | payments.intent.create | Order thuộc tenant đã cấp | Allow |
| order-service | payments.refund | Không có quyền refund | Deny |
| reporting-service | reports.read | Tenant nằm trong allowlist | Allow |
| notification-worker | notifications.send | Chỉ message đã được tạo bởi workflow tin cậy | Allow |
| unknown-client | payments.* | Bất kỳ | Deny |

Dùng deny-by-default. Không cấp scope admin, internal hoặc all cho tiện triển khai nếu không có lý do và kiểm soát rõ.

## 11. Service tự thân và service gọi thay mặt người dùng

Đây là khác biệt quan trọng trong thiết kế API.

### Service tự thân (machine-to-machine)

Order Service gọi Payment API để thực hiện công việc trong quyền của chính Order Service. Client Credentials thường phù hợp. Token đại diện service principal và chỉ có scope đã được cấp.

### Service thay mặt người dùng (delegation)

Một người dùng đăng nhập vào Learning Platform, sau đó Learning API gọi Enrollment API thay mặt người đó. Không nên lấy client credentials của Learning API rồi coi mọi request đều có cùng quyền người dùng.

Cần một mô hình delegation:

- Subject: người dùng được đại diện.
- Actor/client: service thực hiện lời gọi.
- Audience: API đích.
- Scope/permission: quyền được ủy quyền.
- Context: tenant, transaction, authentication assurance nếu nghiệp vụ cần.

### Token exchange

OAuth 2.0 Token Exchange (RFC 8693) cho phép đổi một token đầu vào lấy token phù hợp với audience, scope hoặc delegation context khác theo policy của Authorization Server.

~~~mermaid
sequenceDiagram
    autonumber
    participant User as Người dùng
    participant A as Learning API
    participant AS as Authorization Server
    participant B as Enrollment API
    User->>A: Request với access token dành cho Learning API
    A->>AS: Token exchange / delegation request
    AS->>AS: Xác minh subject, actor, audience và policy
    AS-->>A: Token mới dành cho Enrollment API
    A->>B: Request với token audience Enrollment API
    B->>B: Xác minh token và quyền delegated
    B-->>A: Kết quả
~~~

Không chuyển tiếp cùng một bearer token tới mọi downstream service. Token nên có audience phù hợp với API nhận; nếu cần delegation, token exchange phải giữ đúng subject/actor và không nâng quyền ngoài policy.

## 12. API key: khi nào dùng và giới hạn

API key thường là secret được cấp cho một integration hoặc client để gọi API. Nó đơn giản nhưng có một số giới hạn:

- Thường là bearer secret: ai có key có thể sử dụng.
- Thường tồn tại lâu hơn access token.
- Có thể không có audience, scope hoặc delegation chi tiết.
- Dễ bị lộ qua source code, browser, mobile app, URL hoặc log.
- Rotation/revocation có thể thủ công và chậm.
- Khó phân biệt người dùng cuối với service gọi API.

Nếu vẫn dùng API key:

- Cấp key riêng cho từng integration, môi trường và tenant.
- Lưu server-side dưới dạng hash hoặc verifier phù hợp; chỉ hiển thị secret một lần.
- Dùng key ID công khai để tra cứu record, không dùng secret làm identifier.
- Gắn scope, quota, expiry và owner.
- Không gửi key qua URL/query string.
- Bảo vệ bằng TLS và secret manager.
- Có overlap rotation, revoke khẩn cấp và last-used telemetry.
- Không cấp key quyền quản trị mặc định.
- Cân nhắc thay bằng OAuth client credentials hoặc workload identity khi hệ thống trưởng thành.

API key không nên được dùng như password của service account không có lifecycle.

## 13. mTLS, DPoP và sender-constrained token

Bearer token có thể được sử dụng bởi bất kỳ bên nào nắm giữ token. Nếu token bị đánh cắp, attacker có thể gọi API trong phạm vi token cho phép cho đến khi token hết hạn hoặc bị chặn.

Sender-constrained token ràng buộc token với một private key hoặc certificate để token bị đánh cắp riêng lẻ khó sử dụng hơn.

### Certificate-bound access token

RFC 8705 mô tả OAuth mTLS client authentication và certificate-bound access token. Token có thể chứa confirmation claim tham chiếu certificate thumbprint; resource server so sánh binding với certificate trên kết nối TLS đã xác minh.

### DPoP

DPoP (RFC 9449) dùng proof JWT do client ký cho HTTP request. Proof ràng buộc với method, URI, thời điểm và identifier; tùy flow còn có thể ràng buộc access token. Resource server kiểm tra proof và phát hiện replay theo policy.

### Chọn cơ chế

| Cơ chế | Ràng buộc | Điểm cần vận hành |
| --- | --- | --- |
| Bearer token | Không ràng buộc sender bằng mặc định. | TTL, audience, scope, secure storage, revocation. |
| mTLS-bound token | Certificate của TLS client. | PKI, certificate rotation, TLS termination và thumbprint validation. |
| DPoP-bound token | Proof-of-possession từ client key cho request. | Key lifecycle, htm/htu, jti, nonce và replay detection. |

Không dùng DPoP hoặc mTLS như lý do bỏ qua issuer, audience, scope và authorization. Nếu private key bị lộ cùng token, rủi ro vẫn tồn tại.

## 14. Token propagation qua nhiều service

Một request có thể đi qua API Gateway, Order Service, Pricing Service, Payment Service và Audit Service. Mỗi hop cần nhận đúng identity và quyền cần thiết.

### Anti-pattern: forward token cho mọi nơi

Một access token có audience cho Gateway hoặc Order API bị chuyển tiếp tới mọi downstream service. Điều này mở rộng phạm vi sử dụng token và làm tăng blast radius khi token bị lộ.

### Cách thiết kế tốt hơn

- Mỗi API kiểm tra audience của chính nó.
- Dùng token exchange để lấy token dành cho downstream audience khi cần.
- Giữ subject và actor delegation rõ ràng.
- Không tăng scope khi đổi token.
- Truyền correlation ID riêng để trace, không dùng correlation ID như credential.
- Nếu gateway terminate mTLS, backend chỉ tin identity propagation từ gateway đã xác thực và có integrity.
- Hạn chế service nào được phép gọi service nào.

~~~mermaid
flowchart TD
    C["Caller workload"] --> A["Authorization Server"]
    A --> T1["Token: audience Order API"]
    T1 --> O["Order API"]
    O --> X["Token exchange theo policy"]
    X --> T2["Token: audience Payment API"]
    T2 --> P["Payment API"]
    O --> AU["Audit API"]
    P --> AU
~~~

Không phải mọi hop đều cần token exchange. Có thể dùng service identity và policy nội bộ nếu kiến trúc xác định rõ trust boundary; điều quan trọng là không để token có quyền rộng bị phát tán không kiểm soát.

## 15. Credential, token cache và rotation

### Client credential lifecycle

- Mỗi workload/client có identity riêng.
- Credential không dùng chung giữa dev, test và production.
- Secret/private key được lưu trong secret manager, HSM hoặc platform identity agent phù hợp.
- Quyền đọc secret chỉ cấp cho process cần dùng.
- Theo dõi last-used, expiry, owner và môi trường.
- Có quy trình rotate, overlap và revoke.
- Credential của workload đã decommission phải bị thu hồi.

### Token cache

Token có thể được cache để giảm tải token endpoint. Cache key cần bao gồm những yếu tố làm thay đổi token, ví dụ client identity, audience/resource, scope, tenant và sender-binding context.

Không dùng một token cache entry cho hai client hoặc hai audience khác nhau. Không cache token quá thời hạn và không trả token đã revoke nếu kiến trúc có trạng thái revoke tức thời.

### Rotation

1. Cấp credential mới.
2. Cập nhật workload/secret provider.
3. Lấy token mới và kiểm tra API.
4. Drain hoặc chuyển các instance cũ.
5. Revoke credential cũ sau thời gian overlap đã định.
6. Xác minh không còn workload sử dụng credential cũ.

Không xoay secret bằng cách ghi đè đồng loạt mà không biết replica nào đã nhận cấu hình mới.

## 16. Revocation, expiry và xử lý compromise

Access token ngắn hạn giúp giới hạn thời gian token bị lộ có thể được sử dụng. Nhưng expiry không phải biện pháp duy nhất.

### Opaque token

Có thể revoke tại Authorization Server và kiểm tra qua introspection. Hiệu lực revoke phụ thuộc cache và khả năng kết nối resource server.

### JWT access token

Resource server có thể xác minh cục bộ tới exp. Để thu hồi sớm có thể cần:

- Denylist theo jti hoặc token reference.
- Subject/client version.
- Introspection hoặc trạng thái online.
- Token TTL ngắn.
- Event-driven cache invalidation.
- Sender-constrained token.

### Khi client credential bị compromise

1. Xác định client, key/secret, workload, audience và tenant ảnh hưởng.
2. Disable hoặc revoke credential bị lộ.
3. Revoke token/grant liên quan theo khả năng.
4. Chặn client principal tại API trong thời gian containment.
5. Phát hành credential mới qua provisioning authority tin cậy.
6. Kiểm tra log token issuance, API access và các hành động đã thực hiện.
7. Thu hẹp scope/audience hoặc sửa policy nếu quyền quá rộng.
8. Theo dõi sau rotation và ghi audit incident.

Chỉ đổi client secret mà vẫn chấp nhận token đã cấp cho attacker có thể chưa đủ. Phải đánh giá token lifetime, revocation design và resource server behavior.

## 17. Ranh giới tin cậy ở API Gateway và service mesh

Gateway có thể xác minh access token ở edge, nhưng backend cần hiểu chính xác điều gì đã được gateway xác minh và điều gì backend phải tự kiểm tra.

### Mô hình gateway

- Gateway xác minh token, audience và policy ở edge.
- Gateway kết nối backend bằng mTLS.
- Backend xác thực gateway ở hop nội bộ.
- Identity/context đã xác minh được truyền bằng token hoặc metadata có integrity.
- Backend vẫn kiểm tra authorization nghiệp vụ cho resource/action nếu nó sở hữu logic đó.

### Rủi ro

- Backend có thể bị gọi trực tiếp và bỏ qua gateway.
- Header identity do client gửi không bị xóa.
- Gateway kiểm tra token nhưng không truyền audience/subject context đúng.
- Backend tin mọi request từ gateway và không kiểm tra tenant/resource.
- Service mesh mTLS được bật nhưng authorization policy quá rộng.

Không dùng IP allowlist hoặc network location thay cho workload authentication. Network policy và mTLS bổ trợ nhau; authorization vẫn cần kiểm soát ở tầng API.

## 18. Triển khai trong Java và Spring Security

### 18.1 Cấu hình OAuth2 client credentials

Ví dụ cấu hình Spring Boot cho một service client:

~~~yaml
spring:
  security:
    oauth2:
      client:
        registration:
          enrollment-api:
            provider: internal-idp
            client-id: learning-api
            client-secret: CLIENT_SECRET_FROM_SECRET_MANAGER
            authorization-grant-type: client_credentials
            client-authentication-method: client_secret_basic
            scope:
              - enrollment.read
        provider:
          internal-idp:
            token-uri: https://id.example.edu/oauth2/token
~~~

Đây là cấu hình minh họa. Secret phải được inject từ secret manager hoặc environment được bảo vệ; chuỗi placeholder không phải secret thật. Trong production có thể chọn private_key_jwt hoặc mTLS nếu Authorization Server hỗ trợ.

Client nên dùng OAuth2AuthorizedClientManager hoặc cơ chế tương đương để lấy và cache token theo registration/audience/scope; không tự gọi token endpoint ở mỗi request nếu không cần.

### 18.2 Resource Server xác minh JWT

Ví dụ cấu hình Spring Security:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.oauth2.jwt.JwtDecoder;
import org.springframework.security.oauth2.jwt.JwtValidators;
import org.springframework.security.oauth2.jwt.NimbusJwtDecoder;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class ApiSecurityConfiguration {

    @Bean
    JwtDecoder jwtDecoder() {
        String issuer = "https://id.example.edu";
        String jwkSetUri = "https://id.example.edu/.well-known/jwks.json";

        NimbusJwtDecoder decoder = NimbusJwtDecoder
                .withJwkSetUri(jwkSetUri)
                .build();

        decoder.setJwtValidator(
                JwtValidators.createDefaultWithIssuer(issuer)
        );

        return decoder;
    }

    @Bean
    SecurityFilterChain apiSecurity(HttpSecurity http) throws Exception {
        return http
                .authorizeHttpRequests(auth -> auth
                        .requestMatchers("/internal/reports/**")
                        .hasAuthority("SCOPE_reports.read")
                        .requestMatchers("/internal/payments/**")
                        .hasAuthority("SCOPE_payments.intent.create")
                        .anyRequest()
                        .authenticated()
                )
                .oauth2ResourceServer(oauth -> oauth.jwt(jwt -> { }))
                .build();
    }
}
~~~

Ví dụ cần bổ sung audience validation theo API và mapping claim theo token profile thực tế. Chỉ kiểm tra issuer và chữ ký chưa đủ nếu token được phát cho một API khác. Spring Security có thể dùng custom OAuth2TokenValidator hoặc decoder configuration để kiểm tra audience, thời hạn và claim policy.

Không tắt CSRF theo thói quen cho mọi ứng dụng; API stateless dùng bearer token trong Authorization header có thể có threat model khác với browser session/cookie authentication. Cấu hình phải theo cách credential được truyền và kiến trúc endpoint.

### 18.3 Authorization trong service layer

Không chỉ bảo vệ URL. Service layer cần kiểm tra tenant/resource/action:

~~~java
public PaymentIntent createIntent(
        ApiPrincipal principal,
        Order order
) {
    if (!principal.hasAuthority("payments.intent.create")) {
        throw new AccessDeniedException("Insufficient permission");
    }

    if (!principal.allowedTenants().contains(order.tenantId())) {
        throw new AccessDeniedException("Tenant access denied");
    }

    return paymentRepository.createIntent(order);
}
~~~

Đây là ví dụ mô hình. Principal phải được tạo từ token đã xác minh hoặc identity context có integrity; không nhận danh sách tenant/authority từ request body.

## 19. Lỗi thiết kế và mối đe dọa thường gặp

| Rủi ro | Cách xảy ra | Biện pháp |
| --- | --- | --- |
| **Shared client secret** | Nhiều service dùng chung một credential. | Client identity riêng theo workload/environment. |
| **Secret trong source/image** | Credential bị lộ qua Git, artifact hoặc container layer. | Secret manager, key protection và rotation. |
| **Overbroad audience** | Token được chấp nhận ở nhiều API không liên quan. | Audience riêng cho resource server. |
| **Overprivileged scope** | Client được cấp quyền rộng hơn nhiệm vụ. | Least privilege và scope/action policy. |
| **ID token accepted as access token** | API chấp nhận token sai mục đích. | Kiểm tra token type/profile và audience. |
| **JWT decode without validation** | API chỉ base64-decode payload. | Xác minh chữ ký, issuer, audience, time và claims. |
| **Algorithm confusion** | API tin thuật toán do token header chọn. | Allowlist thuật toán và key type theo issuer. |
| **JWKS key confusion** | API tải key từ URL do token tự khai. | Chỉ dùng JWKS URI cấu hình từ issuer tin cậy. |
| **Token forwarding** | Bearer token bị chuyển tiếp tới API không phải audience. | Token exchange hoặc token audience riêng. |
| **Confused deputy** | Service có quyền rộng bị lừa thực hiện hành động cho caller không đủ quyền. | Giữ actor/subject context, authorization và resource binding. |
| **API key leakage** | Key nằm trong URL, browser, log hoặc repository. | Không dùng key trong URL; scope, hash, rotate và revoke. |
| **Replay/bearer theft** | Token bị sao chép và dùng lại. | TTL, TLS, mTLS/DPoP binding và revoke. |
| **Gateway trust bypass** | Backend bị gọi trực tiếp hoặc tin header giả. | Network policy, mTLS hop, header sanitization và backend validation. |
| **Tenant confusion** | Token hợp lệ bị dùng trên tenant khác. | Tenant/resource authorization ở API. |
| **Stale token cache** | Client tiếp tục dùng token hết hạn hoặc đã revoke. | Cache theo context, expiry và invalidation policy. |
| **Client credential rotation gap** | Replica cũ vẫn dùng secret/key đã retire. | Overlap có thời hạn, rollout quan sát được và revoke xác nhận. |
| **Token endpoint abuse** | Client credential bị dùng để xin token liên tục. | Rate limit, anomaly detection và client disable. |
| **No incident revocation** | Secret bị lộ nhưng API vẫn tin token/identity cũ. | Emergency deny, revoke token/grant và điều tra. |

## 20. Giám sát và vận hành

### Telemetry hữu ích

- Client/workload identity và issuer.
- Token audience, scope hoặc permission đã được cấp (không log token).
- Token issuance success/failure và grant type.
- API request principal, resource, action, tenant và authorization result.
- Credential/key version hoặc certificate fingerprint đã pseudonymize nếu cần.
- Token age, expiry, cache hit/miss và introspection result.
- Unknown client, invalid signature, wrong issuer/audience và scope denial.
- Rotation/revocation event và propagation lag.

Không ghi access token, refresh token, client secret, private key hoặc assertion nguyên vẹn. Nếu cần correlation, dùng request ID và token identifier đã bảo vệ theo policy.

### Alert nên có

- Một client xin token với tốc độ bất thường.
- Client credential được sử dụng từ workload/environment lạ.
- Token có audience hoặc scope khác baseline.
- Tỷ lệ wrong-audience/invalid-signature tăng.
- Service gọi endpoint ngoài allowlist.
- Client secret/key sắp hết hạn hoặc rotation bị trễ.
- Token được sử dụng sau khi client bị disable.
- Nhiều tenant bị truy cập bởi cùng workload ngoài policy.

### Runbook khi service identity bị compromise

- Xác định workload, client ID, credential version, token family và API đã truy cập.
- Disable/revoke credential và token/grant liên quan.
- Áp deny rule tạm thời tại resource server nếu cần containment nhanh.
- Cấp credential mới qua trusted provisioning flow.
- Kiểm tra token cache và các replica đang chạy.
- Điều tra dữ liệu đã đọc/ghi và delegation chain.
- Xác minh quyền, audience và scope đã cấp có vượt quá nhu cầu không.
- Khôi phục traffic có kiểm soát và theo dõi hành vi sau sự cố.

## 21. Ví dụ thực tế: Learning Platform

Learning Platform có Learning API, Enrollment Service, Payment API và Reporting Service. Các service chạy trên cluster, dùng Authorization Server nội bộ.

### Order/Enrollment gọi API bằng client credentials

1. Enrollment Service chạy với workload identity đã được platform xác minh.
2. Service xác thực với Authorization Server bằng private_key_jwt hoặc client credential được quản lý.
3. Authorization Server kiểm tra client registration, trạng thái workload, scope và policy.
4. Server cấp access token ngắn hạn có audience Enrollment API.
5. Enrollment Service gọi API với bearer token; có thể bổ sung mTLS để xác thực workload ở tầng kết nối.
6. Enrollment API xác minh chữ ký/issuer/audience/time/token profile.
7. API ánh xạ principal, kiểm tra scope và tenant/resource.
8. Request được cho phép hoặc từ chối theo policy; audit ghi principal và action.

### Learning API gọi Enrollment thay mặt học viên

1. Học viên có access token dành cho Learning API.
2. Learning API không chuyển token đó thẳng tới mọi downstream service.
3. Learning API gửi token exchange request tới Authorization Server theo policy delegation.
4. Authorization Server xác minh subject, actor, audience và scope.
5. Server cấp token mới dành cho Enrollment API với quyền hẹp.
6. Enrollment API xác minh token, actor/subject và tenant.
7. API kiểm tra học viên có quyền ghi danh khóa học cụ thể không.

### Credential bị lộ

Nếu client secret của Reporting Service bị lộ:

- Security team disable client credential và revoke grant/token theo khả năng.
- Reporting API từ chối principal hoặc token liên quan trong thời gian containment.
- Credential mới được cấp sau khi workload được làm sạch.
- Team rà soát báo cáo đã export và tenant đã truy cập.
- Scope của Reporting Service được thu hẹp nếu phát hiện quyền quá rộng.

## 22. Kiểm thử service-to-service authentication

| Kịch bản | Cách kiểm tra | Kết quả mong đợi |
| --- | --- | --- |
| Client credentials hợp lệ | Dùng client đã đăng ký xin token đúng scope. | AS cấp token theo policy. |
| Client secret sai | Dùng credential sai trong môi trường test. | Token endpoint từ chối, không cấp token. |
| Client đã disable | Xin token bằng client bị disable. | AS từ chối. |
| private_key_jwt sai chữ ký | Gửi assertion không khớp public key. | AS từ chối. |
| Assertion replay | Gửi lại assertion/jti đã dùng. | AS từ chối hoặc phát hiện replay theo policy. |
| Assertion sai audience | Dùng audience không phải token endpoint. | AS từ chối. |
| Workload identity sai | Dùng subject/service account ngoài allowlist. | Federation/broker không cấp token. |
| JWT sai issuer | Dùng token từ issuer không tin cậy. | Resource server từ chối. |
| JWT sai audience | Dùng token dành cho API khác. | Resource server từ chối. |
| JWT hết hạn | Dùng token quá exp. | Resource server từ chối. |
| JWT chưa có hiệu lực | Dùng token có nbf trong tương lai ngoài clock skew. | Resource server từ chối. |
| JWT sai algorithm/key | Dùng thuật toán hoặc key không được policy cho phép. | Resource server từ chối. |
| ID token gửi tới API | Dùng ID token thay access token. | Resource server từ chối theo token profile/audience. |
| Scope thiếu | Token hợp lệ nhưng thiếu permission. | Authentication thành công; authorization từ chối action. |
| Tenant mismatch | Token principal hợp lệ nhưng resource thuộc tenant khác. | API từ chối truy cập resource. |
| Opaque token inactive | Introspect token đã revoke/hết hạn. | API từ chối. |
| Introspection outage | Làm AS không phản hồi. | Hành vi cache/fail policy đúng theo mức rủi ro. |
| JWKS rotation | Đổi signing key và cấp token bằng key mới. | API cập nhật key; token hợp lệ được xác minh, key cũ retire đúng lúc. |
| Unknown kid flood | Gửi token với nhiều kid không tồn tại. | JWKS refresh được giới hạn, không gây request storm. |
| Token forwarding | Gửi token audience Order API tới Payment API. | Payment API từ chối. |
| Token exchange scope escalation | Yêu cầu scope cao hơn quyền subject/actor. | AS từ chối hoặc cấp scope hẹp theo policy. |
| API key rotation | Dùng key cũ sau khi revoke. | API từ chối; key mới hoạt động. |
| Bearer token replay | Dùng lại token bị đánh cắp trong lab. | Kết quả theo TTL/binding/revocation design; sender constraint được kiểm tra nếu bật. |
| Gateway header spoofing | Gửi header giả chứa service identity. | Gateway xóa/ghi đè; backend không tin caller trực tiếp. |
| Cross-service authorization | Service có token hợp lệ gọi action ngoài allowlist. | API từ chối. |
| Client credential leak drill | Revoke credential và phát hành mới. | Token issuance cũ bị chặn theo SLA; workload mới hoạt động. |
| Token cache separation | Hai client/audience yêu cầu token song song. | Không dùng nhầm token giữa client, tenant hoặc audience. |
| Logging review | Kiểm tra application, proxy và audit logs. | Không có raw token, secret, private key hoặc assertion. |

## 23. Checklist thiết kế

- [ ] Đã xác định service principal và workload identity cho từng caller.
- [ ] Đã phân biệt client authentication, access-token validation và authorization.
- [ ] Client Credentials chỉ dùng cho service hoạt động thay mặt chính nó.
- [ ] Delegation/on-behalf-of có subject, actor, audience và scope rõ.
- [ ] Client secret/private key/certificate được lưu trong secret manager hoặc platform identity provider.
- [ ] Không nhúng shared secret vào source, image, browser, URL hoặc log.
- [ ] Client registration riêng theo workload, tenant và environment khi cần.
- [ ] Access token có audience đúng API và scope tối thiểu.
- [ ] API không chấp nhận ID token thay access token.
- [ ] JWT được xác minh chữ ký, issuer, audience, time, type/profile và claim cần thiết.
- [ ] JWKS key rotation và unknown kid refresh có giới hạn.
- [ ] Opaque token introspection có cache/fail policy rõ.
- [ ] Authorization kiểm tra service, action, resource và tenant.
- [ ] Token không bị forward tới API ngoài audience; dùng token exchange khi cần.
- [ ] Có bảo vệ replay/sender constraint phù hợp cho token và request nhạy cảm.
- [ ] API key nếu còn dùng có scope, expiry, hash, owner, rotation và revocation.
- [ ] Token cache tách theo client, audience, scope, tenant và binding context.
- [ ] Có quy trình credential rotation/revocation và incident response.
- [ ] Gateway/mesh identity propagation có integrity và không có bypass path.
- [ ] Telemetry không ghi token/secret và có alert cho hành vi client bất thường.
- [ ] Có test wrong issuer/audience, expired token, scope, tenant, replay, delegation và key rotation.

## 24. Tự kiểm tra

**Câu 1.** Client Credentials Grant phù hợp khi nào?

**Đáp án:** Khi confidential client/service truy cập API bằng quyền của chính nó, không đại diện một người dùng đang tương tác. Nếu cần user delegation, phải dùng flow/context phù hợp.

**Câu 2.** Client authentication tại token endpoint có đồng nghĩa API đã authorization request không?

**Đáp án:** Không. Client authentication chứng minh client với Authorization Server. Resource server vẫn xác minh access token và kiểm tra quyền trên resource/action.

**Câu 3.** Vì sao access token cần audience?

**Đáp án:** Audience giới hạn API/resource server dự định nhận token. Token dành cho một API không nên được chấp nhận ở API khác.

**Câu 4.** API có nên chấp nhận ID token để gọi endpoint không?

**Đáp án:** Không. ID token dành cho client trong OIDC authentication flow; access token dành cho resource server theo token profile.

**Câu 5.** Decode JWT payload có đủ để xác minh token không?

**Đáp án:** Không. Cần xác minh chữ ký bằng key tin cậy, issuer, audience, thời hạn, loại token và claim theo profile.

**Câu 6.** mTLS và OAuth access token giải quyết cùng một việc không?

**Đáp án:** Không hoàn toàn. mTLS xác thực peer ở tầng kết nối; access token mang quyền và context cho API. Có thể kết hợp cả hai.

**Câu 7.** Khi nào cần token exchange?

**Đáp án:** Khi service cần token mới cho downstream audience hoặc cần thể hiện delegation subject/actor theo policy, thay vì chuyển tiếp bearer token có audience không phù hợp.

**Câu 8.** Vì sao không nên dùng một client secret cho mọi service?

**Đáp án:** Shared secret làm mất khả năng phân biệt principal và tăng blast radius. Mỗi workload cần credential riêng để giới hạn quyền, rotation và điều tra.

**Câu 9.** Scope có đủ để bảo vệ dữ liệu đa tenant không?

**Đáp án:** Không. Scope biểu diễn quyền ở mức API/action; resource server vẫn phải kiểm tra tenant, ownership và trạng thái resource.

**Câu 10.** Khi client credential bị lộ, chỉ rotate secret đã đủ chưa?

**Đáp án:** Chưa chắc. Cần revoke token/grant liên quan, chặn principal, kiểm tra token cache và hoạt động đã thực hiện, cấp credential mới và rà soát quyền đã cấp.

## Ghi nhớ

**Xác thực giữa service** cần chứng minh workload/client nào đang gọi API, token được phát hành cho resource nào và caller được phép thực hiện hành động gì. OAuth 2.0 Client Credentials phù hợp với service hoạt động thay mặt chính nó; private_key_jwt, mTLS và workload identity federation là các lựa chọn xác thực client. API đích phải xác minh access token theo issuer, audience, thời hạn và profile, rồi authorization theo scope, resource và tenant.

Nếu service gọi thay mặt người dùng, phải giữ rõ subject/actor và dùng delegation hoặc token exchange theo policy; không forward bearer token tới mọi downstream API. Quản lý credential riêng cho từng workload, token ngắn hạn, audience hẹp, rotation/revocation, cache có ngữ cảnh, sender constraint và telemetry an toàn. **Danh tính service hợp lệ chỉ là điểm bắt đầu; mọi API vẫn phải kiểm tra quyền của request cụ thể trước khi thực hiện nghiệp vụ.**
