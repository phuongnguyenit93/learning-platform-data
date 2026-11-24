# Short-lived credential — Cấp phát và vận hành credential ngắn hạn cho service

Một service xử lý hóa đơn cần gọi API lưu trữ để lấy tệp PDF. Trước đây, nhóm phát triển tạo một access key tĩnh, đặt vào biến môi trường rồi dùng chung cho mọi bản triển khai. Key tồn tại nhiều tháng, được sao chép qua pipeline, máy developer và log debug. Khi một container bị compromise, attacker có thể dùng key ở bất kỳ nơi nào mà key còn hiệu lực.

Một thiết kế tốt hơn xác minh danh tính của workload đang chạy, sau đó cấp một credential có thời hạn ngắn, quyền giới hạn và audience cụ thể. Service dùng credential để gọi đúng API, tự làm mới trước khi hết hạn và nhận credential mới khi workload được triển khai lại. Nếu credential bị lộ, khoảng thời gian có thể sử dụng bị giới hạn; nếu workload bị thu hồi, hệ thống có cơ chế chặn việc cấp mới hoặc vô hiệu hóa credential theo policy.

**Short-lived credential** là credential có thời hạn hiệu lực ngắn, được cấp cho một principal và một mục đích cụ thể. Nó có thể là access token, chứng chỉ client, JWT-SVID/X509-SVID, signed assertion hoặc credential tạm do Security Token Service (STS) cấp. Thời hạn ngắn giúp giảm cửa sổ lạm dụng, nhưng chỉ hiệu quả khi credential được ràng buộc đúng workload, audience, scope, thời điểm, khóa và chính sách thu hồi.

Trong module **SECURITY_AUTHENTICATION_FUNDAMENTALS**, bài học này kết nối service identity, credential, token, chứng chỉ, ranh giới tin cậy và quản lý vòng đời. Người học sẽ biết cách cấp phát credential ngắn hạn cho workload, xác minh nguồn danh tính, chọn token hoặc certificate, giới hạn quyền, cache và refresh an toàn, xử lý rotation/revocation, và tránh biến credential tạm thành một bí mật dài hạn mới.

## 1. Short-lived credential giải quyết vấn đề gì?

Credential dài hạn thường được tạo một lần rồi phân phối tới nhiều môi trường. Chúng dễ bị sao chép, khó kiểm kê, khó xoay vòng và thường có phạm vi quyền rộng hơn nhu cầu của từng workload. Credential ngắn hạn giảm thời gian attacker có thể sử dụng một giá trị bị lộ và cho phép hệ thống cấp quyền theo trạng thái hiện tại của workload.

| Credential | Ví dụ | Vòng đời thường thấy |
| --- | --- | --- |
| Static API key | Key lưu trong secret store hoặc environment | Có thể tồn tại nhiều tháng cho đến khi rotate |
| OAuth access token | Token từ authorization server/STS | Phút đến khoảng một giờ tùy policy |
| Client certificate | X.509 certificate dùng cho mTLS | Giờ, ngày hoặc khoảng thời gian ngắn theo PKI |
| SPIFFE SVID | X.509-SVID hoặc JWT-SVID cho workload | Thường ngắn hạn và được tự động gia hạn |
| Cloud temporary credentials | STS role credentials cho workload | Có thời hạn theo policy của cloud provider |
| Signed client assertion | JWT ký bằng private key để xác thực client | Chỉ dùng trong cửa sổ rất ngắn |

Thời hạn không phải đặc tính duy nhất. Một token sống 5 phút nhưng có quyền quản trị toàn hệ thống và có thể dùng từ bất kỳ máy nào vẫn có rủi ro lớn. Một certificate sống 24 giờ nhưng private key được bảo vệ trong HSM, chỉ dùng cho một workload và có thể revoke có thể phù hợp hơn trong một số môi trường.

### 1.1. Mục tiêu bảo mật

- Credential được cấp cho workload đã được xác minh qua một nguồn danh tính tin cậy.
- Credential chỉ dùng cho audience/service đã định, không dùng chung xuyên hệ thống.
- Scope, role và quyền tối thiểu theo nhiệm vụ.
- Thời hạn ngắn, có refresh/rotation tự động và có giới hạn.
- Secret/private key không bị đóng gói trong image, source code hoặc log.
- Credential bị đánh cắp không thể dễ dàng dùng lại từ workload khác nếu có sender-constraining.
- Workload bị xóa, đổi trạng thái hoặc rời khỏi trust domain không được tiếp tục nhận credential.
- Có audit cho issuance, renewal, denial, revocation và sử dụng credential.

## 2. Workload identity và credential là hai lớp khác nhau

Trước khi cấp credential, hệ thống phải biết workload nào đang yêu cầu. **Workload identity** xác định service, job, container, VM hoặc process; **credential** là bằng chứng được cấp để workload chứng minh identity hoặc được phép gọi tài nguyên.

Ví dụ:

- Workload identity: `spiffe://prod.example.org/ns/billing/sa/invoice-worker`
- Credential: access token có audience `https://files.example.org` và scope `invoice.read`
- Khóa: private key được giữ trong workload hoặc phần cứng bảo vệ
- Trust source: orchestrator, cloud metadata identity, node attestation hoặc SPIFFE Workload API

Không nên nhầm tên service do process tự khai với danh tính đã được xác minh. Một container có thể gửi header `X-Service-Name: billing` nhưng header đó không chứng minh nó thực sự là billing service.

### 2.1. Nguồn danh tính workload

| Nguồn | Cách xác minh | Rủi ro cần kiểm soát |
| --- | --- | --- |
| Cloud instance/workload identity | Metadata service, instance identity document hoặc federation với STS | SSRF tới metadata endpoint, quyền role quá rộng |
| Kubernetes service account | Projected service account token có audience và pod/service account binding | Token mặc định được mount quá rộng, RBAC sai, token bị copy |
| SPIFFE/SPIRE | Node/workload attestation và trust domain | Selector quá rộng, node compromise, registration entry sai |
| Client certificate | CA/trust bundle, SAN và certificate policy | Private key bị lộ, CA trust quá rộng, revocation chậm |
| CI/CD workload federation | OIDC assertion từ pipeline identity provider | Trust condition quá rộng, branch/repository không được ràng buộc |
| Hardware-backed attestation | TPM/TEE hoặc thiết bị được quản trị chứng minh trạng thái | Attestation freshness, firmware và trust root |

Nguồn identity cần có ranh giới tin cậy rõ ràng: ai phát hành, ai có quyền tạo workload, claim nào được tin, cách thu hồi và cách audit. Không dùng claim do workload tự khai thay cho attestation hoặc metadata đã được xác thực.

### 2.2. Bootstrap trust và vấn đề “secret zero”

Workload cần một cách ban đầu để lấy credential đầu tiên. Nếu bootstrap bằng một static secret dài hạn nằm trong image hoặc environment, hệ thống chỉ chuyển rủi ro từ credential chính sang bootstrap secret.

Ưu tiên:

- Instance identity hoặc workload identity được nền tảng cấp sẵn.
- Projected service account token có audience và TTL ngắn.
- Node attestation hoặc SPIFFE Workload API.
- OIDC federation từ CI/CD với issuer, subject và audience được allowlist.
- Hardware-backed key hoặc certificate bootstrap khi phù hợp.

Nếu buộc phải dùng bootstrap secret, giới hạn quyền, gắn với một workload, lưu trong secret manager, xoay vòng và có kế hoạch loại bỏ. Không chia sẻ một bootstrap key giữa môi trường dev, staging và production.

## 3. Vòng đời cấp phát credential ngắn hạn

Một quy trình chuẩn có thể gồm:

~~~mermaid
sequenceDiagram
    participant W as Workload
    participant I as Identity source / attestor
    participant S as STS / credential issuer
    participant R as Resource API
    W->>I: Chứng minh workload identity
    I-->>W: Identity assertion có audience/expiry
    W->>S: Gửi assertion và yêu cầu credential
    S->>S: Xác minh issuer, subject, audience, policy
    S-->>W: Short-lived token/certificate
    W->>R: Gọi API bằng credential
    R->>R: Xác minh issuer, audience, expiry, scope/binding
    R-->>W: Kết quả theo quyền được cấp
    W->>S: Renew trước khi hết hạn
    S-->>W: Credential mới nếu workload còn hợp lệ
~~~

Các bước quan trọng:

1. Workload được khởi chạy trong môi trường có identity source đáng tin.
2. Workload lấy identity assertion hoặc chứng minh possession của khóa.
3. Issuer xác minh subject, issuer, audience, attestation, tenant và policy.
4. Issuer cấp credential có TTL, scope, audience và subject cụ thể.
5. Workload dùng credential qua TLS/mTLS để gọi resource server.
6. Resource server xác minh credential và authorization độc lập.
7. Workload refresh/rotate trước khi hết hạn bằng identity source ban đầu.
8. Khi workload bị thu hồi, issuer ngừng cấp mới và resource server áp dụng revocation policy.

Credential issuance không phải authorization cuối cùng. Resource server vẫn cần kiểm tra account/workload state, scope, tenant, resource ownership và policy của hành động.

## 4. Các dạng short-lived credential

### 4.1. OAuth 2.0 client credentials access token

Service-to-service API thường dùng OAuth 2.0 Client Credentials Grant khi một workload gọi tài nguyên bằng danh tính của chính nó, không đại diện người dùng cuối. Client xác thực với authorization server, yêu cầu token cho resource/audience và scope cụ thể.

Client authentication có thể dùng:

- Client secret, nếu được bảo vệ tốt và có vòng đời ngắn/rotation.
- `private_key_jwt`, trong đó client ký assertion bằng private key.
- Mutual TLS client authentication.
- Workload identity federation hoặc cơ chế platform identity.

Ưu tiên cơ chế bất đối xứng hoặc federation khi nền tảng hỗ trợ, vì tránh phân phối một shared secret cho nhiều nơi. Client Credentials không nên được dùng để giả lập user delegation; nếu service cần hành động thay mặt user, dùng flow/token exchange có subject delegation và policy rõ ràng.

### 4.2. JWT access token và opaque token

| Loại | Cách resource server xác minh | Ưu điểm | Trade-off |
| --- | --- | --- | --- |
| JWT access token | Xác minh chữ ký, issuer, audience, expiry và claims | Xác minh cục bộ, giảm phụ thuộc introspection | Revocation tức thời khó hơn; claim cũ tồn tại đến hết hạn |
| Opaque access token | Gọi introspection hoặc tra cứu state phía server | Có thể vô hiệu hóa tập trung và cập nhật policy nhanh | Phụ thuộc availability/latency của authorization server hoặc cache |

JWT không tự chống replay. Một bearer JWT bị đánh cắp vẫn có thể được dùng đến khi hết hạn hoặc bị từ chối bằng cơ chế bổ sung. Claim `jti` chỉ là ID token; nó chỉ chống replay nếu resource server thực sự lưu và kiểm tra trạng thái đã dùng trong phạm vi thích hợp. Với access token dùng cho nhiều request, việc dùng lại là hành vi bình thường; sender-constraining giúp token chỉ dùng được cùng khóa/chứng chỉ của workload.

### 4.3. Client certificate và mTLS

Workload có thể nhận certificate X.509 ngắn hạn để xác thực ở tầng TLS. Resource server kiểm tra chain tới CA tin cậy, validity, SAN/URI identity, EKU/key usage và policy. mTLS chứng minh peer nắm private key tương ứng; server vẫn cần ánh xạ certificate identity tới service principal và kiểm tra authorization.

Private key nên được tạo và giữ trong workload hoặc phần cứng bảo vệ; certificate không phải secret, private key mới là tài sản nhạy cảm. Không chia sẻ cùng một private key cho nhiều service vì làm mất khả năng phân biệt và thu hồi theo workload.

### 4.4. SPIFFE SVID

SPIFFE định nghĩa workload identity theo trust domain và cung cấp SVID (SPIFFE Verifiable Identity Document). Hai dạng thường gặp:

- X.509-SVID: certificate có URI SAN biểu diễn SPIFFE ID, thường dùng mTLS.
- JWT-SVID: JWT được ký, có audience và expiry; phù hợp một số giao tiếp không thể dùng mTLS.

SVID thường có thời hạn ngắn và được cấp lại qua SPIFFE Workload API khi workload còn đáp ứng attestation. Verifier cần kiểm tra trust bundle, SPIFFE ID, audience (với JWT-SVID), expiry và policy. Không chấp nhận JWT-SVID chỉ vì chữ ký hợp lệ nếu audience hoặc trust domain sai.

### 4.5. Cloud STS credentials

Cloud provider có thể cấp temporary access key/secret/session token cho workload sau khi xác minh instance, service account hoặc federated identity. Những credential này cần:

- Gắn với role cụ thể và trust policy.
- Có session duration tối thiểu đáp ứng công việc.
- Có quyền tối thiểu và resource condition.
- Không được ghi vào image, source hoặc log.
- Được refresh qua metadata/identity endpoint bảo vệ.
- Có thể thu hồi hoặc chặn cấp mới khi workload/role bị compromise.

Không cho phép workload tùy ý chọn role hoặc subject. Trust policy phải ràng buộc issuer, subject, audience, repository/branch, namespace/service account hoặc các claim cần thiết.

## 5. Claims và ràng buộc credential

Một access token có thể chứa các claim:

| Claim | Ý nghĩa | Kiểm tra |
| --- | --- | --- |
| `iss` | Issuer đã phát token | Phải thuộc issuer/trust configuration |
| `sub` | Subject/workload principal | Ánh xạ tới service identity đã biết |
| `aud` | Resource hoặc service được phép nhận | Phải khớp audience của API |
| `exp` | Hết hạn | Từ chối sau expiry, có clock skew nhỏ |
| `nbf` | Chưa có hiệu lực trước thời điểm này | Kiểm tra theo clock policy |
| `iat` | Thời điểm phát hành | Dùng đánh giá tuổi token và policy |
| `jti` | Token identifier | Hữu ích cho audit/denylist nếu có state |
| `scope / roles` | Quyền được cấp | Kiểm tra least privilege và resource policy |
| `client_id` | Client đã yêu cầu token | Kiểm tra client registration/policy |
| `tenant` | Phạm vi tổ chức | Kiểm tra tenant isolation |
| `cnf` | Confirmation key/certificate binding | Xác minh proof-of-possession nếu token sender-constrained |

Không tự thêm claim tùy tiện rồi tin claim đó ở resource server. Issuer phải ký token, resource server phải có schema và policy rõ. Không đưa PII hoặc secret vào token nếu không cần; JWT thường có thể được đọc bởi holder dù chữ ký không thể giả mạo.

### 5.1. Audience và token confusion

Token dành cho service A không được chấp nhận ở service B chỉ vì cùng issuer ký. Kiểm tra audience chính xác, tránh wildcard quá rộng và tránh dùng cùng một token cho nhiều resource không liên quan.

Nếu service A cần gọi service B, cấp token có audience B hoặc dùng token exchange theo policy. Không chuyển tiếp token có audience A tới B rồi hy vọng B tự hiểu. Ràng buộc audience giúp giảm confused deputy và token substitution.

### 5.2. Scope và authorization

Scope nên biểu diễn quyền tối thiểu, chẳng hạn `invoice.read` thay vì quyền quản trị chung. Resource server cần kiểm tra object-level authorization: token có scope đọc hóa đơn không có nghĩa được đọc mọi tenant hoặc mọi hóa đơn.

Scope là một phần policy, không phải thay thế kiểm tra tenant, ownership, state và business rules. Không cho client tự gửi scope rộng hơn registration hoặc quyền workload được phép.

## 6. Thời hạn credential: ngắn bao nhiêu là phù hợp?

TTL quá dài làm tăng cửa sổ lạm dụng nếu credential bị lộ. TTL quá ngắn gây nhiều lần refresh, phụ thuộc issuer, tăng tải và tạo outage khi credential service không sẵn sàng.

Chọn TTL dựa trên:

- Giá trị và độ nhạy của tài nguyên.
- Quyền của workload và khả năng gây thiệt hại.
- Mức độ bảo vệ private key/token cache.
- Khả năng refresh tự động và availability của issuer.
- Clock skew, network latency và độ trễ giữa các region.
- Nhu cầu xử lý khẩn cấp khi compromise.
- Khả năng revoke hoặc introspect credential.

| Loại workload | Cách chọn TTL |
| --- | --- |
| Job ngắn chạy vài phút | Credential có TTL bao phủ job và biên retry nhỏ; không cần token sống nhiều giờ |
| Service online liên tục | TTL ngắn vừa đủ, refresh tự động trước expiry và có jitter |
| Admin automation | TTL rất ngắn, scope hẹp, approval/step-up cho thao tác nhạy cảm |
| Batch processing dài | Renew định kỳ; mỗi lần cấp lại vẫn kiểm tra workload identity và policy |
| Cross-region service | Tính clock skew và network delay, không nới TTL vô hạn để bù lỗi |
| Workload offline/air-gapped | Cần threat model riêng; credential dài hơn có thể không tránh được nhưng phải giới hạn quyền và có kế hoạch rotation |

Không có một TTL chuẩn dùng cho mọi dịch vụ. Mục tiêu là giảm thời gian lạm dụng trong khi vẫn duy trì khả năng vận hành.

### 6.1. Clock skew và thời điểm refresh

Workload không nên đợi đến đúng giây expiry mới refresh. Refresh sớm với biên an toàn và jitter để tránh hàng nghìn instance cùng gọi issuer một lúc. Resource server có thể cho clock skew nhỏ nhưng không được chấp nhận token quá hạn dài để che lỗi đồng bộ.

### 6.2. Refresh không đồng nghĩa credential dài hạn

Refresh token hoặc credential bootstrap có thể sống lâu hơn access token. Nếu refresh token có quyền cấp token mới mà không cần attestation lại, nó trở thành một credential dài hạn có giá trị cao. Cần:

- Bảo vệ refresh credential như secret quan trọng.
- Ràng buộc với client/workload và sender key nếu có thể.
- Giới hạn quyền và rotation/reuse detection.
- Có idle/absolute lifetime.
- Thu hồi khi workload bị disable, secret bị lộ hoặc trust policy đổi.
- Ưu tiên lấy credential mới qua workload identity source thay vì lưu refresh token lâu dài trong ứng dụng.

## 7. Credential caching và refresh an toàn

Cache token giúp tránh gọi issuer ở mọi request, nhưng cache sai có thể làm token dùng nhầm audience, scope hoặc tenant.

### 7.1. Cache key

Cache key nên bao gồm ít nhất:

- Workload principal hoặc client identity.
- Issuer/authorization server.
- Audience/resource.
- Scope hoặc quyền yêu cầu.
- Tenant/realm.
- Sender-constraining key/certificate identity nếu áp dụng.

Không cache chỉ theo tên service hoặc một biến currentToken toàn cục nếu service gọi nhiều resource. Token có scope/audience khác nhau không thể thay thế nhau.

### 7.2. Refresh sớm và single-flight

- Refresh trước expiry với safety margin.
- Thêm random jitter để tránh thundering herd.
- Dùng single-flight/lock để nhiều thread không cùng refresh một cache entry.
- Giữ token cũ chỉ đến khi hết hạn hoặc bị revoke; không dùng token quá hạn khi issuer lỗi.
- Nếu refresh thất bại do lỗi tạm thời, retry có backoff và jitter.
- Nếu issuer trả invalid_grant/identity revoked, xóa credential và ngừng request tới resource.
- Không trả token ra log hoặc exception.

### 7.3. Stale credential

Không dùng stale token vô thời hạn chỉ vì credential issuer tạm lỗi. Có thể tiếp tục dùng credential hiện tại nếu nó vẫn còn hiệu lực và policy cho phép; sau expiry phải fail closed đối với thao tác nhạy cảm. Với tác vụ đọc ít rủi ro, hệ thống có thể có degraded mode được policy phê duyệt, nhưng phải có giới hạn và audit.

## 8. Rotation, revocation và compromise

Credential ngắn hạn giảm cửa sổ sử dụng, nhưng không loại bỏ nhu cầu thu hồi. Attacker có thể dùng credential ngay trong thời gian nó còn hợp lệ; private key hoặc workload identity có thể đã bị compromise.

### 8.1. Rotation

Rotation là cấp credential mới trước khi credential cũ hết hạn:

1. Workload xác minh lại identity hoặc chứng minh possession của key.
2. Issuer phát certificate/token mới.
3. Workload cập nhật cache/connection pool an toàn.
4. Resource server chấp nhận credential mới theo trust policy.
5. Credential cũ hết hạn hoặc bị revoke sau overlap window phù hợp.

Với certificate, cần tránh thay private key nhưng không cập nhật trust chain, hoặc thay certificate trước khi mọi client/server nhận trust bundle mới. Với signing keys của issuer, dùng key ID, publish JWKS mới, có overlap và giữ key cũ trong thời gian token hợp lệ còn cần verify.

### 8.2. Revocation

Cách revoke tùy credential:

- Opaque token: introspection có thể trả inactive ngay khi state được cập nhật.
- JWT access token: dùng TTL ngắn, token version, denylist, introspection hoặc policy epoch khi cần revoke nhanh.
- mTLS certificate: CRL/OCSP, denylist serial/SAN hoặc trust bundle update theo kiến trúc.
- SPIFFE SVID: ngừng cấp mới, thu hồi/loại khỏi bundle hoặc policy và đóng connection theo mức cần thiết.
- Cloud STS credentials: disable role/session hoặc revoke session theo cơ chế provider hỗ trợ.

Short TTL không bảo đảm revoke tức thời. Nếu một token JWT còn hiệu lực 10 phút, resource server xác minh offline có thể tiếp tục chấp nhận token trong thời gian đó nếu không có denylist hoặc policy update.

### 8.3. Compromise response

Khi nghi ngờ workload bị compromise:

1. Xác định principal, token/certificate serial, key ID và resource đã truy cập.
2. Ngừng cấp credential mới cho workload hoặc identity bị ảnh hưởng.
3. Revoke token/session hoặc certificate theo khả năng của issuer/resource server.
4. Isolate workload/node/pod và bảo toàn forensic evidence.
5. Rotate private key, service secret và các credential downstream bị lộ.
6. Kiểm tra token exchange, delegation, role assignment và dữ liệu đã truy cập.
7. Khôi phục workload từ image/config tin cậy và attestation lại.
8. Theo dõi credential issuance và access sau containment.

Không chỉ rotate token nếu private key hoặc nguồn attestation vẫn bị attacker kiểm soát; attacker có thể tiếp tục xin credential mới.

## 9. Sender-constrained credential và proof of possession

Bearer token có thể được dùng bởi bất kỳ ai sở hữu chuỗi token. Nếu token bị lộ, attacker có thể gửi nó từ máy khác trong thời gian hiệu lực. Sender-constrained token gắn token với một khóa hoặc certificate mà client phải chứng minh đang sở hữu.

### mTLS certificate-bound token

Authorization server có thể gắn access token với thumbprint của client certificate. Resource server kiểm tra token và xác minh certificate trong TLS connection tương ứng. Token bị copy sang máy khác không đủ nếu attacker không có private key của certificate.

### DPoP

Demonstrating Proof of Possession (DPoP) dùng một key pair của client và proof JWT cho từng request. Resource server kiểm tra proof, method, URI, thời điểm, nonce khi áp dụng và binding với access token. DPoP giảm rủi ro token bị dùng lại độc lập, nhưng implementation cần xử lý replay của proof JWT và không được tin các claim chưa xác minh.

### Giới hạn

- Nếu private key bị lộ cùng token, sender-constraining mất tác dụng.
- Key phải được bảo vệ và có vòng đời/rotation.
- Proxy hoặc TLS termination phải chuyển identity proof theo kiến trúc tin cậy; không tin header do client tự gửi.
- Resource server phải kiểm tra binding thực sự, không chỉ thấy claim cnf.
- Workload identity và key binding phải được quản lý cùng nhau.

## 10. Service identity không phải user delegation

Một service có thể gọi API bằng identity riêng của nó hoặc thay mặt một người dùng. Hai trường hợp có ý nghĩa bảo mật khác nhau:

| Mô hình | Subject | Quyền được đánh giá |
| --- | --- | --- |
| Service-to-service | Workload/service principal | Quyền của service trên resource |
| User-delegated | User subject cùng client/service actor | Quyền user và quyền được ủy quyền cho service |
| On-behalf-of/token exchange | Token mới phản ánh delegation được issuer cho phép | Audience, actor, subject, scope và policy delegation |

Không dùng client credentials để giả vờ có danh tính người dùng. Không cho service nhận token của một user rồi chuyển nguyên token tới mọi downstream service. Dùng token exchange hoặc delegation flow được thiết kế rõ, giới hạn audience và scope cho từng hop.

Đây là cách giảm confused deputy: service chỉ nhận quyền cần thiết cho tác vụ, biết đang hành động với tư cách ai và không thể tự nâng quyền bằng cách chuyển token sang resource khác.

## 11. Java/Spring: lấy và cache access token ngắn hạn

Ví dụ sau mô tả abstraction cho một service gọi API khác. Trong Spring Security thực tế, có thể dùng OAuth2 Client với Client Credentials và cấu hình client authentication phù hợp như private_key_jwt hoặc mTLS. Không tự triển khai token protocol bằng cách ghép chuỗi thủ công trong production.

~~~java
record TokenRequest(
    String issuer,
    String clientId,
    String audience,
    Set<String> scopes,
    String tenant
) {}

record AccessCredential(
    String value,
    Instant expiresAt,
    String audience,
    Set<String> scopes
) {}

class WorkloadCredentialProvider {
    private final TokenIssuerClient issuerClient;
    private final WorkloadIdentitySource identitySource;
    private final ConcurrentMap<TokenCacheKey, AccessCredential> cache;
    private final Clock clock;

    AccessCredential get(TokenRequest request) {
        TokenCacheKey key = TokenCacheKey.from(request, identitySource.identity());
        AccessCredential current = cache.get(key);

        if (current != null && isUsable(current)) {
            return current;
        }

        return refreshSingleFlight(key, () -> {
            WorkloadAssertion assertion =
                identitySource.createAssertion(request.audience());

            AccessCredential fresh = issuerClient.exchange(
                request,
                assertion
            );

            validateIssuedCredential(fresh, request);
            cache.put(key, fresh);
            return fresh;
        });
    }

    private boolean isUsable(AccessCredential credential) {
        Instant refreshBefore = credential.expiresAt()
            .minusSeconds(refreshMarginWithJitter());
        return clock.instant().isBefore(refreshBefore);
    }

    private void validateIssuedCredential(
            AccessCredential credential,
            TokenRequest request) {
        if (!credential.audience().equals(request.audience())) {
            throw new SecurityException("Unexpected token audience");
        }
        if (!credential.scopes().containsAll(request.scopes())) {
            throw new SecurityException("Token scope is insufficient");
        }
        if (!clock.instant().isBefore(credential.expiresAt())) {
            throw new SecurityException("Issuer returned expired credential");
        }
    }
}
~~~

Đây là pseudocode; trong triển khai thực tế:

- Cache key phải bao gồm issuer, principal, tenant, audience, scope và key binding.
- Single-flight phải được triển khai bằng cơ chế thread-safe/distributed phù hợp với topology.
- Không cache token lâu hơn expiry và không dùng stale token sau khi hết hạn.
- Không log access token hoặc assertion.
- Identity source phải xác minh workload; không nhận service name từ input không tin cậy.
- Token issuer cần kiểm tra trust policy, subject, audience, attestation và quyền được cấp.
- Resource server vẫn phải xác minh chữ ký/issuer/audience/expiry/scope hoặc introspection.
- Dùng TLS và mTLS/DPoP khi cần sender-constraining.

### 11.1. Kiểm tra JWT access token ở resource server

~~~java
ValidatedPrincipal validateAccessToken(String compactJwt) {
    Jwt jwt = jwtDecoder.decode(compactJwt); // signature + allowed algorithms

    requireTrustedIssuer(jwt.getIssuer());
    requireAudience(jwt, expectedAudience);
    requireNotExpired(jwt, clock.instant(), allowedClockSkew);
    requireNotBeforeIfPresent(jwt, clock.instant(), allowedClockSkew);
    requireExpectedClientAndTenant(jwt);
    requireAllowedScopes(jwt, requiredScopes);
    requireSenderBindingIfConfigured(jwt, currentTlsPeerOrDpopProof);

    return principalMapper.fromValidatedClaims(jwt);
}
~~~

Decoder phải dùng allowlist thuật toán, key set/issuer đã cấu hình và kiểm tra claim theo protocol. Không tự chọn thuật toán từ header token rồi chấp nhận mọi loại; không coi decode JSON là verify chữ ký. Với opaque token, thay bước decode bằng introspection/state lookup có cache và timeout phù hợp.

## 12. Observability, audit và privacy

Credential ngắn hạn cần được theo dõi xuyên suốt issuance, refresh và use, nhưng log không được trở thành nơi lưu credential.

### Sự kiện nên ghi

| Event | Dữ liệu cần |
| --- | --- |
| Credential issued | Principal ref, issuer, audience, scope, TTL, key ID, policy version |
| Credential renewed | Principal ref, credential family/serial reference, outcome, expiry |
| Credential denied | Reason code, subject/client ref, issuer, timestamp |
| Authentication success | Workload principal, target service, method/binding |
| Authorization denied | Principal, resource ref, action, scope/policy reason |
| Credential revoked | Principal, token/certificate reference, actor, reason |
| Attestation failure | Node/workload reference, trust policy version, reason |
| Rotation | Old/new key or certificate reference, overlap window, result |

Không ghi raw access token, refresh token, private key, client secret, JWT assertion hoặc toàn bộ certificate private material. Certificate public có thể cần lưu serial/fingerprint; tránh log PII không cần thiết. Dùng correlation ID và pseudonymous principal reference.

### Metrics vận hành

- Issuance success/failure và latency theo issuer/tenant.
- Token/certificate age tại thời điểm sử dụng.
- Refresh rate, refresh failure, expired credential request.
- Credential cache hit/miss và concurrent refresh count.
- Audience/scope mismatch và sender-binding failure.
- Revocation propagation delay.
- Attestation failure và workload identity drift.
- Credential issuance tăng đột biến hoặc workload lạ xin scope đặc quyền.

Alert khi workload liên tục xin credential mới, TTL bất thường, audience rộng hoặc một principal gọi resource ngoài baseline. Không chỉ giám sát login; cần giám sát cả cấp credential và sử dụng credential.

## 13. Những lỗi thiết kế thường gặp

| Lỗi | Hậu quả | Cải thiện |
| --- | --- | --- |
| Static secret nằm trong container image | Mọi bản image có cùng bí mật; khó revoke riêng workload | Workload identity và credential issuance động |
| Token ngắn hạn nhưng scope quá rộng | Attacker có quyền lớn trong cửa sổ ngắn | Least privilege, audience và resource policy |
| Cùng token dùng cho nhiều service | Token substitution và confused deputy | Audience riêng hoặc token exchange |
| JWT chỉ decode mà không verify chữ ký | Attacker tự tạo claim | Trusted issuer, algorithm allowlist và signature validation |
| Không kiểm tra audience | Token của service A được dùng tại service B | Exact audience validation |
| Cache token chỉ theo service name | Token sai tenant/scope/audience bị dùng nhầm | Cache key đầy đủ |
| Refresh cùng lúc từ hàng nghìn instance | Thundering herd làm issuer quá tải | Jitter, single-flight, backoff |
| Dùng token quá hạn khi issuer lỗi | Credential hết hiệu lực vẫn được gửi | Fail closed sau expiry, degraded mode có policy |
| Không có revocation plan | Token bị lộ vẫn dùng đến expiry | Introspection, denylist, short TTL, key/cert revocation |
| Private key dùng chung | Không xác định và revoke đúng workload | Key riêng cho workload, HSM/TPM khi phù hợp |
| Bootstrap secret sống lâu | Rủi ro cũ chỉ chuyển sang secret khác | Federation/attestation, bootstrap TTL và rotation |
| Tin service name do client khai | Workload giả danh service khác | Xác minh identity source |
| Không phân biệt service identity và user delegation | Service có thể hành động vượt quyền | Token exchange/delegation policy |
| Không giám sát issuance | Attacker xin credential mới liên tục | Audit và anomaly detection cho issuance |
| Tắt anti-replay khi cache lỗi | Token/assertion có thể bị phát lại | Fail closed hoặc retry với challenge mới |

## 14. Ma trận kiểm thử short-lived credential

| Kịch bản | Kết quả mong đợi |
| --- | --- |
| Workload hợp lệ xin token đúng audience | Issuer cấp credential với scope và TTL theo policy |
| Workload tự khai service name khác | Không được cấp identity của service khác |
| OIDC assertion có issuer không tin cậy | Từ chối |
| Assertion có subject/branch/namespace ngoài trust policy | Từ chối |
| Assertion có audience sai | Từ chối |
| Token JWT có chữ ký sai hoặc thuật toán ngoài allowlist | Từ chối |
| Token JWT có issuer không tin cậy | Từ chối |
| Token có audience của service A gửi tới service B | Từ chối |
| Token hết hạn hoặc chưa tới nbf | Từ chối theo clock policy |
| Token có scope thiếu | Authorization denied |
| Token có scope rộng ngoài client registration | Issuer không cấp hoặc resource policy từ chối |
| Bearer token bị copy sang workload khác | Sender-constrained check từ chối nếu binding được bật |
| mTLS certificate hết hạn hoặc SAN sai | TLS/identity validation thất bại |
| Certificate private key dùng chung giữa nhiều workload | Kiểm thử inventory phát hiện shared key |
| SPIFFE JWT-SVID có audience sai | Verifier từ chối |
| SPIFFE workload bị xóa registration | Không nhận SVID mới; credential cũ bị xử lý theo revocation policy |
| Cloud role trust policy cho subject khác | STS từ chối |
| Refresh token bị reuse hoặc client identity thay đổi | Rotation/reuse policy phát hiện và thu hồi phù hợp |
| Nhiều thread refresh cùng lúc | Single-flight tránh tạo burst token |
| Nhiều instance refresh cùng lúc | Jitter/distributed coordination giảm thundering herd |
| Issuer tạm unavailable trước expiry | Retry có backoff; token hiện tại chỉ dùng khi còn hợp lệ |
| Issuer unavailable sau expiry | Không dùng token quá hạn cho thao tác nhạy cảm |
| Workload bị disable trong khi đang hoạt động | Ngừng cấp mới và áp dụng revocation/containment |
| JWT signing key rotate | JWKS overlap cho phép verify token hợp lệ trong thời gian chuyển tiếp |
| Raw token xuất hiện trong log | Redaction/security test phát hiện và chặn |
| Credential issuance tăng bất thường | Alert theo principal, audience, scope và rate |
| Service cần gọi downstream thay mặt user | Dùng delegation/token exchange đúng policy, không giả client credentials |

### Tình huống thực hành

Một nền tảng chạy 300 replica của service billing. Mỗi replica đọc API key tĩnh từ environment để gọi file service và database. Key có quyền đọc/ghi mọi bucket và sống 180 ngày. Khi key sắp hết hạn, toàn bộ replica tự refresh cùng lúc. File service chỉ kiểm tra chữ ký JWT mà không kiểm tra audience. Nhóm vận hành phát hiện một token dùng được từ một pod khác trong cùng cluster.

**Yêu cầu:** thiết kế lại service authentication.

**Hướng phân tích:**

1. Xác định workload identity cho từng service account/namespace hoặc workload role; không tin tên service do client gửi.
2. Dùng workload identity federation hoặc STS để cấp access token ngắn hạn cho billing, với audience riêng của file service và scope chỉ đọc/ghi đúng bucket cần thiết.
3. Nếu hạ tầng hỗ trợ, dùng mTLS/SPIFFE SVID hoặc token sender-constrained để token bị copy sang pod khác không đủ dùng.
4. File service xác minh issuer, audience, expiry, scope, tenant và sender binding; chữ ký hợp lệ một mình không đủ.
5. Cache theo principal/audience/scope, refresh sớm có jitter và single-flight; không để 300 replica đồng loạt refresh.
6. Tách credential cho database và file service; không dùng một token đa audience hoặc quyền wildcard.
7. Có revocation/incident path: disable workload identity, ngừng cấp token, revoke credential và kiểm tra access log.
8. Theo dõi issuance, renewal, token age, scope và resource access; không log token hoặc private key.

## 15. Câu hỏi tự kiểm tra

1. **Short-lived credential giảm rủi ro gì?** Giảm thời gian một credential bị lộ có thể được sử dụng, nếu TTL và revocation được thực thi đúng.
2. **Workload identity khác credential thế nào?** Identity xác định workload; credential là bằng chứng được cấp để workload chứng minh identity hoặc truy cập resource.
3. **Vì sao token ngắn hạn vẫn có thể nguy hiểm?** Bearer token bị đánh cắp vẫn dùng được đến expiry; scope rộng và thiếu sender binding làm tăng tác động.
4. **Vì sao cần audience?** Ngăn token của một resource/service bị dùng ở resource khác.
5. **JWT có tự chống replay không?** Không. Chữ ký và expiry không ngăn bearer token bị dùng lại; cần sender-constraining hoặc state phù hợp.
6. **Khi nào dùng mTLS/SPIFFE SVID?** Khi service-to-service cần identity ở tầng kết nối, certificate ngắn hạn và trust domain rõ.
7. **Vì sao refresh token có thể là credential dài hạn?** Nó có thể cấp access token mới; phải bảo vệ, ràng buộc, rotation và revoke như secret có giá trị cao.
8. **Khi issuer unavailable, có nên dùng token hết hạn không?** Không cho thao tác nhạy cảm; chỉ tiếp tục credential còn hiệu lực theo policy và có fallback được phê duyệt.
9. **Service gọi downstream thay mặt user cần gì?** Delegation hoặc token exchange có subject/actor, audience và scope được ràng buộc; không dùng client credentials để giả user.

**Ghi nhớ:** Credential ngắn hạn chỉ an toàn khi được cấp cho workload đã xác minh, có audience và scope hẹp, TTL phù hợp, cache đúng ngữ cảnh và refresh có kiểm soát. Kết hợp workload identity, STS/federation, mTLS hoặc SVID khi phù hợp; xác minh issuer/audience/expiry/binding ở resource server; có rotation, revocation và audit. Đừng để static bootstrap secret, refresh token hoặc private key trở thành một credential dài hạn mới.
