# Certificate enrollment trong Machine identity và IAM Identity Lifecycle

## 1. Certificate enrollment là gì?

**Certificate enrollment** là quá trình **đăng ký yêu cầu, xác minh danh tính và quyền được cấp, rồi nhận chứng thư số (digital certificate)** cho một thực thể như máy chủ, dịch vụ, thiết bị, ứng dụng hoặc workload. Trong hệ sinh thái **Public Key Infrastructure (PKI)**, chứng thư thường theo định dạng **X.509**, liên kết một **public key** với **thông tin danh tính và phạm vi sử dụng** dưới chữ ký của một **Certification Authority (CA)**.

Ví dụ, dịch vụ **payments-api** cần chứng thư để thực hiện **mutual TLS (mTLS)** với **orders-api**. Khi enrollment, payments-api hoặc một thành phần được ủy quyền tạo cặp khóa, gửi yêu cầu chứa public key, chứng minh quyền đại diện cho danh tính dịch vụ, và nhận certificate có **SAN/EKU/validity** phù hợp. Khóa riêng được giữ an toàn; dịch vụ dùng certificate và private key để chứng minh danh tính trong quá trình bắt tay TLS.

**Enrollment không phải hành động “tự ký một certificate” và cũng không phải chỉ tải file .crt về máy.** Giá trị bảo mật đến từ **chuỗi tin cậy**: nguồn định danh, chứng minh quyền sở hữu khóa, xác minh quyền được đăng ký, policy CA, cấp phát, phân phối, kiểm tra và thu hồi.

Bài này thuộc chương **Machine identity** của mô-đun **SECURITY_IDENTITY_ACCESS_MANAGEMENT_IDENTITY_LIFECYCLE**. Mô-đun tìm hiểu quản lý vòng đời danh tính theo **Joiner–Mover–Leaver (JML)**, từ xác minh, tạo tài khoản, cấp quyền tới rà soát và thu hồi khi thay đổi vai trò; liên hệ **IdP, SSO, SCIM, RBAC/ABAC, tài khoản dịch vụ, audit** và giảm **quyền truy cập tồn dư**. Với machine identity, vòng đời của thiết bị/workload cần được quản lý riêng nhưng phải liên kết với **người/đội chịu trách nhiệm** và sự kiện JML có liên quan.

### Mục tiêu học tập

Sau khi học, bạn có thể:

1. Phân biệt **enrollment, issuance, deployment, renewal, rekey và revocation**.
2. Giải thích vai trò **CA, RA, CSR, private key, certificate chain, trust anchor** và các thành phần tự động hóa.
3. Mô tả kiểm soát **identity proofing, key possession, attestation và authorization** trước khi cấp.
4. So sánh **ACME, EST, SCEP và CMP** ở mức mục đích, tin cậy và giới hạn.
5. Hiểu cách certificate được sử dụng trong **TLS/mTLS, service mesh, Kubernetes, IoT và workload identity**.
6. Quản lý **SAN, Key Usage, EKU, validity, key protection, rotation và revocation**.
7. Gắn certificate lifecycle với **Joiner–Mover–Leaver** của owner và **Create–Change–Retire** của máy/workload.
8. Thiết kế **audit, reconciliation, monitoring, tests và runbook** để chứng minh certificate cũ không tiếp tục được sử dụng trái chính sách.

## 2. Certificate khác machine identity, key và account thế nào?

| Khái niệm | Vai trò | Ví dụ | Điều không tự chứng minh |
|---|---|---|---|
| **Machine identity** | Danh tính logic hoặc vật lý của máy/workload | service:payments-api, device:pos-014 | Máy có quyền gọi mọi API |
| **Account / principal** | Đối tượng mà IAM hoặc ứng dụng nhận diện | Kubernetes ServiceAccount, cloud service principal | Private key được bảo vệ tốt |
| **Public/private key pair** | Vật liệu mật mã dùng ký/trao đổi khóa theo thuật toán | ECDSA P-256 key pair | Public key thuộc đúng máy |
| **CSR** | Yêu cầu chứng thư mang public key và dữ liệu đăng ký | PKCS#10 request | CA chắc chắn sẽ cấp đúng tên xin |
| **Certificate** | Khẳng định có chữ ký liên kết public key và thông tin danh tính | X.509 với DNS SAN | Chủ thể còn được phép làm mọi action |
| **Certificate chain** | Chuỗi chứng thư hỗ trợ kiểm chứng issuer | Leaf → Intermediate → Root | Root phù hợp với mọi mục đích |
| **Trust anchor** | Điểm tin cậy được cấu hình độc lập | Root CA trong trust store | Certificate bất kỳ của root đều được phép |
| **Entitlement / permission** | Quyền thực hiện action trên resource | queue.publish trên payment-events | Khóa và certificate còn nguyên vẹn |
| **Session / access token** | Chứng cứ phiên hoặc API có thời hạn | TLS session, OAuth access token | Quyền không đổi sau Mover/Leaver |

**Certificate là một phương tiện chứng minh danh tính dựa trên public key**, không phải toàn bộ identity lifecycle. Một máy có certificate hợp lệ về chữ ký vẫn có thể đã bị **retire, mất quyền hoặc bị xâm nhập**; resource server phải áp chính sách authorization và trạng thái hiện hành.

### Một tên, nhiều danh tính

Một workload có thể có nhiều instance/pod và nhiều certificate được rotate trong thời gian giao nhau. Ngược lại, một server có thể chạy nhiều workload với mức tin cậy khác nhau; không nên cho tất cả dùng **cùng private key và cùng quyền global admin** chỉ vì chúng nằm trên một VM.

## 3. PKI và các vai trò trong enrollment

**PKI** là tập hợp công nghệ, quy trình, con người và policy quản lý certificate và khóa.

| Thành phần | Trách nhiệm |
|---|---|
| **Subject / certificate applicant** | Máy, dịch vụ hoặc tổ chức cần certificate |
| **Key pair holder** | Thành phần thực sự giữ và sử dụng private key |
| **Enrollment client / agent** | Tạo CSR, gửi yêu cầu, nhận và triển khai chứng thư |
| **Registration Authority (RA)** | Kiểm điều kiện, danh tính và thẩm quyền đăng ký khi mô hình có RA |
| **Certification Authority (CA)** | Ký và phát hành chứng thư theo policy/profile |
| **Certificate policy / template** | Giới hạn tên, thuật toán, KU/EKU, TTL, cấp quyền enrollment |
| **Trust store / relying party** | Định nghĩa CA/issuer nào được tin để kiểm chứng |
| **Revocation service** | Công bố CRL hoặc OCSP khi kiến trúc dùng |
| **Inventory / Certificate Lifecycle Manager (CLM)** | Theo dõi owner, target, expiry, triển khai, rotation và bằng chứng |
| **IAM/IGA, workload registry** | Nguồn identity, owner, approval và desired authorization state |

Một tổ chức có thể gộp RA vào CA hoặc dùng managed CA. Tuy vậy, cần phân biệt **quyền được yêu cầu certificate** và **quyền được CA ký certificate**; một enrollment API có thể tự động hóa nhưng vẫn phải có chính sách phát hành rõ ràng.

### Kiến trúc khái quát

~~~mermaid
flowchart TD
    REG[Identity / Device / Workload Registry] --> RA[Registration / Policy Evaluation]
    W[Machine or Workload] --> KEY[Local Key Generation]
    KEY --> CSR[CSR with Public Key]
    CSR --> ENROLL[Enrollment Client / Protocol]
    ENROLL --> RA
    RA --> CA[CA: Policy and Certificate Signing]
    CA --> CERT[Issued X.509 Certificate]
    CERT --> DEPLOY[Deployment / Secure Installation]
    DEPLOY --> TLS[TLS / mTLS Resource Server]
    TLS --> AUTH[RBAC / ABAC / Resource Authorization]
    CA --> AUDIT[Audit and Inventory]
    DEPLOY --> AUDIT
    AUTH --> AUDIT
    AUDIT --> ROTATE[Renew / Rekey / Revoke / Reconcile]
~~~

**Một certificate đã được ký không đồng nghĩa đã được triển khai**, và một certificate đã triển khai không đồng nghĩa mọi client tin đúng CA. Kiểm tra phát hành, triển khai, xác minh trust và quyền nghiệp vụ là những lớp riêng.

## 4. Certificate enrollment được dùng ở đâu?

| Trường hợp | Đối tượng được chứng thực | Kiểm soát cần thiết |
|---|---|---|
| **TLS server** | Domain/service endpoint | DNS/IP SAN đúng, serverAuth EKU khi áp dụng |
| **mTLS client** | Workload gọi API nội bộ | clientAuth EKU, identity mapping, action scope |
| **Service mesh** | Microservice identity | Trust domain, SVID/certificate rotation, policy service-to-service |
| **Kubernetes webhook** | Endpoint của webhook | Server identity và CA bundle phù hợp |
| **IoT/edge device** | Thiết bị duy nhất | Device ID, bootstrap identity, hardware key |
| **VPN/network device** | Gateway, router, client thiết bị | Enrollment authorization, certificate profile |
| **Database TLS** | Server hoặc database client | Peer validation, role mapping và key isolation |
| **Code signing** | Publisher/build pipeline | Signing-specific policy, key custody, artifact provenance |
| **Email signing/encryption** | Mail identity | Email address validation và EKU khi áp dụng |
| **Internal API gateway** | Gateway/service client | mTLS, peer SAN, runtime authorization |

Không nên dùng **cùng certificate/key pair** cho tất cả mục đích nếu profile, mức rủi ro hoặc owner khác nhau. Một certificate **serverAuth** không tự cấp quyền client đăng nhập database; ứng dụng phải kiểm **usage, identity và policy** phù hợp.

## 5. Certificate lifecycle: enrollment chỉ là một giai đoạn

Vòng đời thường gồm:

1. **Discover / Register:** ghi danh tính máy, owner, nguồn tin cậy và tài nguyên.
2. **Authorize enrollment:** kiểm máy/workload đủ điều kiện xin loại certificate nào.
3. **Generate key:** tạo private/public key theo policy và bảo vệ private key.
4. **Create CSR / request:** chứng minh possession, khai danh tính cần chứng nhận.
5. **Validate and Issue:** RA/CA kiểm request rồi ký certificate.
6. **Distribute / Install:** chuyển certificate/chain tới nơi dùng mà không làm lộ key.
7. **Activate / Verify:** kiểm TLS/mTLS và authorization thực tế.
8. **Renew / Rekey:** cấp certificate mới hoặc thay cả khóa trước khi hết hạn.
9. **Revoke / Suspend when supported:** xử lý compromise, thay owner hoặc retire.
10. **Retire / Reconcile:** gỡ trust, role, credential và xác minh không còn truy cập.

~~~mermaid
stateDiagram-v2
    [*] --> Discovered
    Discovered --> Eligible: Identity and owner verified
    Eligible --> Requested: CSR / enrollment request
    Requested --> Rejected: Policy or proofing failed
    Requested --> Issued: CA signed certificate
    Issued --> Deployed: Installed certificate and chain
    Deployed --> Active: Trust and authorization verified
    Active --> Renewing: Before expiry / policy event
    Renewing --> Active: New certificate deployed
    Active --> Revoked: Compromise / security decision
    Active --> Expired: Validity ended
    Active --> Retired: Workload / device retired
    Revoked --> Retired: Cleanup and readback
    Expired --> Retired: Cleanup
    Retired --> [*]
~~~

Đây là **mô hình vận hành minh họa**, không phải một state machine bắt buộc của X.509. **Certificate không tự bị xóa khỏi mọi máy** khi trạng thái trong inventory đổi; hệ thống tiêu thụ certificate phải thực thi xác thực và thu hồi theo khả năng của mình.

## 6. Enrollment khác issuance, renewal, rekey và revocation

| Thuật ngữ | Ý nghĩa | Điểm cần nhớ |
|---|---|---|
| **Enrollment** | Quy trình xin và nhận certificate theo trust/policy | Có xác minh, request và kết quả |
| **Issuance** | CA phát hành và ký chứng thư | Không đồng nghĩa certificate đã cài |
| **Provisioning/Deployment** | Đưa certificate/chain hoặc tham chiếu key đến workload | Không nên gửi private key qua kênh không bảo vệ |
| **Renewal** | Lấy certificate mới khi certificate cũ sắp hết hạn | Có thể dùng cùng key hoặc key mới theo policy |
| **Rekey** | Thay private/public key pair | Nên cân nhắc khi rotate và bắt buộc khi nghi compromise |
| **Revocation** | Thông báo certificate không còn được tin trước NotAfter | Phải xét cách relying party kiểm CRL/OCSP |
| **Expiration** | Certificate hết thời gian hiệu lực | Không chứng minh key đã bị xóa |
| **Replacement** | Chuyển workload sang certificate/key mới | Cần kế hoạch giao nhau và rollback an toàn |
| **Retirement** | Đóng danh tính hoặc quan hệ được chứng nhận | Xử lý luôn role, token, session, trust và audit |

**Renewal không nhất thiết tương đương rekey.** Một số công cụ cho renew trên cùng private key, nhưng với chính sách giảm thời gian lộ khóa, tổ chức có thể yêu cầu sinh khóa mới khi renew. Khi đã nghi private key bị lộ, chỉ renew chứng thư dùng lại khóa đó **không giải quyết rủi ro**.

## 7. Xác minh danh tính trước khi cấp certificate

Khâu **identity proofing/registration** xác định **machine/workload nào được phép yêu cầu tên và mục đích sử dụng nào**.

Nguồn bằng chứng có thể gồm:

- Asset inventory hoặc CMDB với ID thiết bị ổn định.
- Workload registry, service owner và deployment nguồn.
- MDM/device management và trạng thái quản lý.
- Kubernetes ServiceAccount, pod/node attestation.
- Cloud instance identity hoặc managed identity.
- Factory-installed identity/initial device certificate trong IoT.
- Chủ sở hữu domain và khả năng chứng minh domain control.
- Approval từ owner/Security cho certificate privileged hoặc đặc biệt.

### Phân biệt các loại xác minh

**Domain validation (DV)** trong TLS public Web PKI chứng minh quyền kiểm soát tên miền theo phương pháp CA sử dụng; nó **không tự chứng minh nhân viên hay workload cụ thể là ai**, cũng không chứng minh dịch vụ an toàn.

Với **internal mTLS**, xác minh cần khớp workload ID, trust domain và owner theo policy. Với **device identity**, có thể cần serial/device enrollment, TPM/secure element hoặc quy trình nhập kho. **Các loại certificate có mức chứng thực và chính sách phát hành khác nhau.**

### Câu hỏi trước khi cho enrollment

1. **Ai** đang gửi request và dùng kênh xác thực nào?
2. **Subject và SAN** dự kiến có đúng danh tính máy không?
3. **Ai có thẩm quyền** phê duyệt danh tính và loại certificate này?
4. **Khóa riêng được sinh và giữ ở đâu**?
5. **Certificate dùng để làm gì**: server TLS, client mTLS, ký code?
6. **Phạm vi trust**: CA public, private PKI, cluster hoặc trust domain nào?
7. **Thời hạn tối đa, renewal và revocation** được vận hành ra sao?
8. **Nếu máy bị retire hoặc owner Leaver**, ai dừng enrollment và thu hồi?

## 8. Proof of possession khác authorization to enroll

**Proof of possession (PoP)** cho thấy bên gửi yêu cầu có quyền sử dụng private key tương ứng với public key trong request, thường thông qua chữ ký trên CSR. Tuy nhiên, PoP **không chứng minh requester được phép nhận danh tính yêu cầu**.

Ví dụ một kẻ tấn công có thể tạo key pair mới và CSR có **DNS SAN=payments-api.production.example.org**. Chữ ký CSR hợp lệ chỉ chứng minh attacker sở hữu private key tương ứng; **CA vẫn phải từ chối** nếu requester không có quyền đối với tên đó.

### Mô hình hai chốt kiểm soát

~~~text
(1) Proof-of-possession:
    CSR signature validates against requested public key.

(2) Enrollment authorization:
    Authenticated caller is allowed to obtain
    this subject/SAN, certificate profile and lifetime.
~~~

Nếu CA chỉ kiểm CSR signature mà không kiểm nguồn định danh và quyền cấp chứng thư, attacker có thể tạo certificate giả mạo service hợp lệ trong trust domain.

### Khi nào attestation giúp ích?

TPM, secure enclave hoặc runtime attestation có thể bổ sung chứng cứ rằng khóa được tạo/giữ trong phần cứng hoặc workload có thuộc tính nền tảng cụ thể. Nhưng **attestation phải được xác minh theo trust chain và policy**; một câu tự khai “tôi dùng TPM” không đủ.

## 9. Private key generation và bảo vệ khóa

**Private key là bí mật quan trọng nhất** của chứng thư dựa trên cặp khóa. Certificate và public key có thể được công khai trong giới hạn phù hợp; private key phải chỉ được dùng bởi chủ thể được phép.

### Các lựa chọn lưu khóa

| Cơ chế | Ưu điểm | Rủi ro/giới hạn |
|---|---|---|
| **HSM** | Kiểm soát khóa tập trung hoặc chuyên dụng; có thể không xuất được | Chi phí, availability và tích hợp |
| **TPM / Secure Element** | Ràng buộc khóa với thiết bị/phần cứng | Migration và thay thế thiết bị cần kế hoạch |
| **Cloud KMS / Managed HSM** | Policy, audit và managed key operations | Quyền KMS và trust vào cloud |
| **OS key store** | Tích hợp permission và service identity | Host compromise có thể lạm dụng khóa |
| **File trên disk mã hóa/quyền chặt** | Đơn giản, hỗ trợ nhiều ứng dụng | Copy/backup/log nhầm hoặc quyền file sai |
| **Kubernetes Secret** | Được điều phối bởi Kubernetes | Không mặc nhiên bảo đảm key không lộ; cần RBAC/encryption/access control |

### Quy tắc quản trị khóa

1. **Tạo khóa trong môi trường được phép**, ưu tiên non-exportable khi use case và nền tảng hỗ trợ.
2. Dùng **thuật toán và key size theo policy hiện hành**, ví dụ RSA hoặc ECDSA có tham số được phê duyệt.
3. Không dùng cùng một private key cho nhiều workload có trust khác nhau.
4. Không đặt private key trong Git, container image, ticket, CI artifact hoặc log.
5. Hạn chế account/service nào có quyền đọc hoặc ký bằng key.
6. Bảo vệ backup và phục hồi khóa theo rủi ro, không sao chép bừa bãi.
7. Cấu hình rotation/renewal và xử lý key compromise.
8. Khi workload retire, xóa/vô hiệu key theo năng lực phương tiện lưu trữ và kiểm chứng.

**Mã hóa key trên disk không giúp nhiều nếu attacker đã kiểm soát process có quyền giải mã và dùng key.** Cần kết hợp runtime isolation, IAM policy, attestation và audit.

## 10. CSR và PKCS#10

**Certificate Signing Request (CSR)** thường được biểu diễn theo **PKCS#10**. CSR chứa public key cùng thông tin/requested extensions, và được ký bởi private key tương ứng để hỗ trợ xác minh PoP.

Ví dụ nội dung logic:

~~~text
CSR:
  publicKey: <public key of service>
  subject: CN=payments-api
  requestedSubjectAltName:
    DNS:payments-api.payments.svc.cluster.local
  signature: Sign(privateKey, certificationRequestInfo)
~~~

CSR **không phải certificate đã được CA ký**. Trường SAN trong CSR là một **yêu cầu**, CA phải kiểm quyền dùng tên trước khi đưa vào chứng thư. CA có thể bỏ qua hoặc điều chỉnh các extension theo profile.

### Ví dụ tạo khóa và CSR bằng OpenSSL

~~~bash
# Ví dụ vận hành minh họa: sinh private key EC P-256
openssl genpkey -algorithm EC -pkeyopt ec_paramgen_curve:P-256 \
  -out payments-api.key

# Tạo CSR và đề xuất SAN; CA phải xác minh SAN độc lập
openssl req -new \
  -key payments-api.key \
  -subj "/CN=payments-api" \
  -addext "subjectAltName=DNS:payments-api.payments.svc.cluster.local" \
  -out payments-api.csr

# Kiểm nội dung CSR; không xuất private key ra màn hình
openssl req -in payments-api.csr -noout -text
~~~

Lệnh là **ví dụ để hiểu định dạng**, không phải quy trình production hoàn chỉnh. Tính sẵn có của option phụ thuộc phiên bản OpenSSL. Tệp **payments-api.key** phải được bảo vệ bằng quyền file, thư mục và cơ chế secret phù hợp; không đưa lên Git hay gửi cho CA. CA chỉ cần public key/CSR và bằng chứng thẩm quyền, không cần private key.

### Một lỗi cần tránh

**Không dùng CSR như bằng chứng danh tính hoàn chỉnh**. Một attacker có thể tự tạo CSR với CN giống service khác; chính sách CA/RA mới xác định chủ thể có được phép dùng SAN đó hay không.

## 11. Subject, Subject Alternative Name và identity mapping

**Subject Alternative Name (SAN)** là extension quan trọng để biểu diễn danh tính mà TLS hoặc ứng dụng sẽ kiểm tra:

- **DNS SAN:** tên miền hoặc hostname.
- **IP SAN:** địa chỉ IP khi kiểm định danh theo IP.
- **URI SAN:** định danh URI, ví dụ SPIFFE ID.
- Các dạng SAN khác có thể phù hợp use case và profile.

### Ví dụ

| Certificate use case | SAN được cân nhắc | Quy tắc kiểm |
|---|---|---|
| Public HTTPS | DNS:api.example.org | Xác minh hostname theo TLS và CA trust |
| Internal TLS | DNS:payments-api.payments.svc.cluster.local | Chỉ cấp nếu owner/service được phép tên |
| SPIFFE workload | URI:spiffe://prod.example.org/ns/payments/sa/payments-api | Kiểm trust domain và SPIFFE ID đầy đủ |
| Network appliance | IP:192.0.2.10 hoặc DNS cụ thể | Xác minh asset/owner và địa chỉ được quản lý |
| Multi-name service | Nhiều DNS SAN đã được phê duyệt | Kiểm từng tên và phạm vi cấp |

**CN không nên được dùng thay DNS SAN cho hostname verification trong TLS hiện đại.** Cách kiểm identity tùy giao thức và client. Với SPIFFE, việc đặt URI SAN chỉ có ý nghĩa khi **bên nhận tin issuer/trust domain và đối chiếu URI với policy**.

### Tránh cấp wildcard quá rộng

Chứng thư chứa **DNS:*.example.org** có thể phù hợp một trường hợp quản lý domain nhưng mở rộng blast radius nếu private key lộ. Không tự động cấp wildcard cho mọi workload. Một danh tính URI/SPIFFE có wildcard trong policy cũng cần review chặt.

### Danh tính logic và instance

Dịch vụ có thể giữ một logical service identity nhưng mỗi instance nhận certificate riêng. Điều đó giúp rotation và containment, với điều kiện CA/PEP có thể liên kết instance hợp lệ với identity logic mà không cho container khác giả mạo.

## 12. Key Usage (KU), Extended Key Usage (EKU) và certificate profile

**X.509 certificate extensions** giúp relying party và ứng dụng hiểu mục đích sử dụng của certificate.

| Extension | Ví dụ | Ý nghĩa |
|---|---|---|
| **Basic Constraints** | CA=true/false | Phân biệt certificate của CA với leaf theo profile |
| **Key Usage (KU)** | digitalSignature, keyEncipherment, keyCertSign | Giới hạn mục đích dùng khóa theo thuật toán |
| **Extended Key Usage (EKU)** | serverAuth, clientAuth | Mục đích xác thực TLS server/client |
| **Subject Alternative Name** | DNS/IP/URI | Định danh đối tượng |
| **Validity** | NotBefore/NotAfter | Khoảng thời gian certificate có hiệu lực |
| **Subject Key Identifier / Authority Key Identifier** | Key identifiers | Hỗ trợ xây dựng/kiểm tra chain |
| **Certificate Policies** | Policy OID | Biểu diễn policy nếu hệ sinh thái dùng |
| **CRL Distribution Points / AIA** | Revocation/issuer metadata | Gợi ý nơi lấy thông tin chuỗi/revocation khi áp dụng |

**EKU và KU không tự tạo permission nghiệp vụ**. Certificate có **clientAuth** không nghĩa client được phép dùng **database.admin** hoặc **payment.refund**. Resource server vẫn phải có **RBAC/ABAC/PBAC**, object-level authorization và ranh giới tenant.

### Certificate profile là một sản phẩm quản trị

Mỗi profile nên có:

- Chủ thể/nhóm máy nào được enrollment.
- Loại certificate: TLS server, mTLS client, device, code signing.
- Các SAN hợp lệ và cách chứng minh quyền sở hữu.
- Thuật toán, key size, KU/EKU, basic constraints.
- Validity tối đa và renewal window.
- Có yêu cầu **hardware-backed key/attestation** không.
- CA hierarchy/trust domain.
- Approval route, audit và cơ chế thu hồi.

**Không cho enrollment client tự chọn CA=true hoặc keyCertSign để biến leaf thành CA** nếu policy không cho phép.

## 13. Thẩm định và phát hành certificate ở CA/RA

Sau khi nhận CSR, CA/RA phải xác minh ít nhất:

1. CSR đúng định dạng và **chữ ký CSR hợp lệ**.
2. Requester đã **authenticated** bằng cơ chế enrollment phù hợp.
3. **Subject/SAN** thuộc phạm vi mà requester được phép đăng ký.
4. **Certificate profile** đúng use case và issuer.
5. Thuật toán, public key và key size được chấp thuận.
6. **KU/EKU, CA=false, validity, naming constraints** không vi phạm policy.
7. Certificate lifetime không vượt giới hạn CA/template/quan hệ.
8. Nếu cần, owner/Security/asset registry/attestation đã đạt.
9. Serial number, audit request ID và kết quả phát hành được lưu.
10. Thông tin trong certificate được CA **tự xây từ policy**, không sao chép mọi extension do client đề xuất.

### Kết quả cần phân biệt

| Kết quả | Ý nghĩa |
|---|---|
| **REQUESTED** | CSR đã được gửi |
| **PENDING_VALIDATION** | Chờ proofing/approval/challenge |
| **REJECTED** | Không phù hợp policy hoặc validation thất bại |
| **ISSUED** | CA đã ký certificate |
| **DELIVERED** | Enrollment client đã nhận certificate/chain |
| **DEPLOYED** | Workload đã cài/tham chiếu certificate |
| **VERIFIED_ACTIVE** | Client/peer xác thực thành công theo scope |
| **REVOKED / EXPIRED** | Không nên tiếp tục tin certificate theo policy |

**ISSUED không đồng nghĩa DEPLOYED**, và **DEPLOYED không đồng nghĩa runtime authorization đúng**. Phải kiểm cả tên peer, chain và hành động.

## 14. ACME: tự động enrollment cho certificate

**Automatic Certificate Management Environment (ACME)** là giao thức tiêu chuẩn hóa để tự động hóa chứng minh quyền kiểm soát định danh theo cơ chế hỗ trợ, yêu cầu, phát hành và gia hạn certificate. ACME thường được sử dụng trong **TLS Web PKI** và cũng có triển khai cho môi trường private PKI.

### Luồng ACME khái quát

~~~mermaid
sequenceDiagram
    participant C as ACME Client
    participant S as ACME Server / CA
    participant CH as Challenge Validation
    C->>S: Tạo/đăng ký account và newOrder
    S-->>C: Authorizations / challenges
    C->>CH: Chuẩn bị bằng chứng kiểm soát tên
    S->>CH: Validate challenge
    CH-->>S: Kết quả
    C->>S: Finalize order bằng CSR
    S->>S: Kiểm policy, SAN và ký certificate
    S-->>C: Certificate / chain URL
    C->>S: Tải certificate và triển khai
~~~

### Challenge phổ biến

| Challenge | Bằng chứng điển hình | Lưu ý |
|---|---|---|
| **HTTP-01** | Đặt nội dung challenge tại HTTP endpoint theo yêu cầu giao thức | Phụ thuộc khả năng truy cập tên miền qua HTTP |
| **DNS-01** | Tạo TXT record phục vụ validation | Quyền DNS API rất nhạy cảm; có thể dùng cho wildcard |
| **TLS-ALPN-01** | Trình certificate/ALPN validation chuyên biệt | Cần hỗ trợ TLS endpoint và ALPN |
| **External Account Binding (EAB)** | Gắn ACME account với tư cách do CA xác nhận khi dùng | Không tự cấp quyền SAN nếu CA không kiểm chính sách |

**ACME domain challenge chủ yếu chứng minh domain control theo challenge**, không tự chứng minh một pod hay một nhân viên có quyền quản trị production. CA nội bộ vẫn cần chính sách kiểm workload/owner hoặc cơ chế binding bổ sung nếu dùng ACME cho danh tính máy đặc thù.

### Account key khác certificate private key

ACME thường có **account key** để xác thực thao tác account/order và **private key của certificate** được yêu cầu. Hai vai trò khóa khác nhau; nếu account key lộ, attacker có thể lợi dụng khả năng đặt yêu cầu theo các authorizations/challenges mà account/CA cho phép. Bảo vệ cả hai.

## 15. EST: Enrollment over Secure Transport

**Enrollment over Secure Transport (EST)** là giao thức enrollment dựa trên HTTPS/TLS, được thiết kế cho các hệ sinh thái muốn bootstrap trust, lấy thông tin CA, yêu cầu hoặc đăng ký lại certificate.

Một số thao tác tiêu biểu gồm:

- **Get CA certificates:** lấy thông tin certificate của CA theo giao thức.
- **CSR attributes:** server cho biết thuộc tính CSR cần thiết.
- **Simple enrollment:** gửi CSR xin chứng thư.
- **Simple reenrollment:** đăng ký lại khi có certificate/authorization phù hợp.
- **Server-side key generation:** một số triển khai/mở rộng hỗ trợ cơ chế liên quan nhưng phải xét bảo vệ khóa chặt chẽ.

### Điểm mạnh

- Có thể kết hợp **TLS client authentication** hoặc cơ chế enrollment authentication được hệ thống chấp thuận.
- Phù hợp triển khai **device/enterprise certificate enrollment** có quy trình bootstrap.
- Có cơ sở để kiểm tra policy trên server và phát hành theo profile.
- Có thể hỗ trợ đổi certificate theo vòng đời thiết bị.

### Những hạn chế

- **HTTPS server certificate hợp lệ không tự chứng minh client được đăng ký danh tính tùy ý**.
- Bootstrap trust là một vấn đề riêng: client cần biết **tin CA/EST server nào** trước khi gửi thông tin nhạy cảm.
- Khả năng hỗ trợ cụ thể khác nhau theo thiết bị và sản phẩm.
- Không đồng nhất việc lấy CA certificates với việc tự động cho root CA vào trust store mà không xác minh.

**EST và ACME cùng có thể tự động enrollment**, nhưng cơ chế chứng minh quyền và use case phổ biến khác nhau. Chọn theo khả năng client, trust model và chính sách kiểm identity.

## 16. SCEP: enrollment trong hệ sinh thái thiết bị

**Simple Certificate Enrollment Protocol (SCEP)** xuất hiện nhiều ở thiết bị mạng, MDM và các môi trường cần enrollment certificate bằng cơ chế có tính tương thích rộng.

### Các điểm cần biết

- SCEP có các thông điệp yêu cầu/chấp thuận và tương tác với CA/RA tùy triển khai.
- Một số hệ thống dùng **challenge password/one-time credential** làm cơ chế xác minh thẩm quyền enrollment.
- Một số thiết bị hoặc nền tảng chỉ hỗ trợ tập profile/thuật toán nhất định.
- Khả năng renew, key protection và phê duyệt phụ thuộc cách triển khai.
- Certificate issuance vẫn phải kiểm **đúng thiết bị, subject/SAN, KU/EKU và owner**, không chỉ thấy một challenge hợp lệ.

### Nguy cơ challenge dùng chung

Nếu nhiều thiết bị dùng **một challenge cố định hoặc dễ đoán**, attacker có thể xin certificate với danh tính không được phép, đặc biệt nếu CA không ràng buộc challenge với asset/subject/TTL. Nên ưu tiên **credential ngắn hạn, duy nhất hoặc attestation** khi sản phẩm hỗ trợ, và ghi nhận lần sử dụng.

**SCEP không nên bị đánh giá chỉ bằng tên giao thức**: cấu hình CA, enrollment authorization, profile và bảo vệ khóa quyết định mức an toàn thực tế.

## 17. CMP: Certificate Management Protocol

**Certificate Management Protocol (CMP)** cung cấp cơ chế quản lý certificate theo PKI, bao gồm các quy trình về request, certification, key update, revocation và những thông điệp quản trị khác theo mô hình triển khai.

### Điểm cần nhớ

- CMP có cấu trúc message và bảo vệ trao đổi phức tạp hơn một form CSR đơn giản.
- Có thể phù hợp với **PKI doanh nghiệp, viễn thông, thiết bị** hoặc hệ thống yêu cầu vòng đời đầy đủ.
- Việc tích hợp phụ thuộc vào **CA/RA product và client support**.
- Policy CA vẫn phải kiểm danh tính, thẩm quyền, profile và mục đích.
- Không coi việc hỗ trợ revocation request là chứng minh mọi relying party lập tức từ chối certificate.

### Các giao thức có thể cùng tồn tại

Một tổ chức có thể sử dụng:

- **ACME** cho web servers.
- **EST hoặc SCEP** cho thiết bị mạng/MDM.
- **CMP** cho hệ sinh thái PKI chuyên biệt.
- **SPIFFE/SPIRE Workload API** cho cấp SVID của workloads.
- **Vendor-specific API** cho một số CA hoặc hardware key manager.

**Không có một giao thức duy nhất phù hợp mọi đối tượng máy.** Cần chọn theo trust/bootstrap, key storage, identity proofing, automation, time-to-revoke và khả năng của endpoint.

## 18. So sánh ACME, EST, SCEP và CMP

| Tiêu chí | ACME | EST | SCEP | CMP |
|---|---|---|---|---|
| **Mục đích nổi bật** | Certificate issuance/renewal tự động | Enrollment qua HTTPS/TLS | Enrollment thiết bị/MDM tương thích | PKI certificate management |
| **Bootstrap/trust** | ACME account và authorization/challenge theo CA | TLS trust và cơ chế client enrollment | Challenge/RA policy tùy thiết kế | Message protection, PKI trust theo profile |
| **Request** | Order, authorization, CSR | CSR qua enrollment endpoint | Enrollment messages/CSR | PKI management messages |
| **Điều kiện danh tính** | Challenge hoặc CA policy mở rộng | Client auth/RA/CA policy | Device/MDM/challenge và CA policy | PKI management policy |
| **Automation** | Rất phổ biến cho web TLS | Phù hợp enterprise/device | Phổ biến ở một số device stacks | Khả năng phong phú nhưng tích hợp phức tạp |
| **Định danh workload Kubernetes** | Cần cơ chế ràng buộc bổ sung khi dùng | Cần broker/attestation riêng | Không tự chứng thực pod | Cần tích hợp trust platform |
| **Revocation/rotation** | Phụ thuộc CA/client và cơ chế liên quan | Hỗ trợ enrollment lại; revoke tùy hệ sinh thái | Phụ thuộc triển khai | Có các quy trình quản lý/revocation |
| **Rủi ro** | Lộ DNS API/account key, challenge cấp sai | Trust bootstrap và client auth sai | Challenge quá rộng/dùng chung | Policy/message authentication sai |

Bảng là **định hướng kiến trúc**, không phải so sánh độ an toàn tuyệt đối của các phiên bản và sản phẩm. Với bất kỳ giao thức nào, một **CA cấp certificate quá rộng theo tên xin của client** vẫn là lỗ hổng enrollment authorization.

## 19. Certificate issuance và kiểm tra certificate chain

Một certificate leaf được xác minh thông qua **chain**:

~~~text
Leaf Certificate: payments-api
    signed by
Intermediate CA: Internal Services CA
    signed by
Root CA: Enterprise Root CA
    trusted independently by
Relying Party Trust Store
~~~

### Những kiểm tra quan trọng

1. **Chữ ký và chain construction** từ leaf tới trust anchor được cấu hình.
2. Thời gian **NotBefore/NotAfter** hợp lệ theo clock.
3. **Basic Constraints, KU/EKU, keyCertSign và path constraints** của CA chain.
4. Certificate leaf có **SAN/identity** đúng target.
5. **Policy OID, name constraints** và các ràng buộc khác khi áp dụng.
6. Certificate còn đáp ứng chính sách **revocation** của ứng dụng.
7. Thuật toán và độ mạnh khóa còn được chấp nhận.
8. Đúng **trust domain/tenant/environment**, không chỉ một root CA quá rộng.
9. Đúng **mục đích** của peer: serverAuth/clientAuth/code signing.
10. Runtime authorization vẫn kiểm **resource/action và trạng thái workload**.

### Certificate chain không phải authorization chain

Certificate chain chứng minh một **khẳng định khóa/danh tính** được phát hành từ nguồn CA tin cậy; nó không tự cấp **permissions business**. Nếu một service có client certificate hợp lệ trong cùng trust domain nhưng không thuộc nhóm được phép gọi **payment.refund**, resource server vẫn phải Deny.

### Root rotation

Khi thay Root CA hoặc Intermediate CA, cần kế hoạch **trust bundle distribution, cross-signing khi phù hợp, dual trust window, testing và cleanup**. Không bỏ trust anchor cũ quá sớm gây outage, nhưng cũng không giữ root cũ vô hạn nếu nó đã bị compromise.

## 20. Kubernetes và cert-manager: tự động hóa nhưng vẫn có ranh giới quyền

Trong Kubernetes, công cụ như **cert-manager** có thể điều phối yêu cầu, cấp và gia hạn certificate từ những **Issuer/ClusterIssuer** hoặc CA được cấu hình. Đối tượng **Certificate** mô tả certificate mong muốn, secret đích và những thuộc tính cần thiết theo khả năng triển khai.

### Ví dụ minh họa Kubernetes Certificate

~~~yaml
apiVersion: cert-manager.io/v1
kind: Certificate
metadata:
  name: payments-api-tls
  namespace: payments
spec:
  secretName: payments-api-tls
  duration: 2160h
  renewBefore: 360h
  dnsNames:
    - payments-api.payments.svc.cluster.local
  issuerRef:
    name: internal-services-issuer
    kind: Issuer
~~~

**Đây là manifest minh họa**, không phải bảo đảm tương thích với mọi cụm. **duration 2160h** và **renewBefore 360h** chỉ là ví dụ, phải áp policy TTL phù hợp. Tên issuer, DNS và điều kiện security phải được định nghĩa trong cluster.

### Bốn ranh giới phải kiểm

- **Ai được tạo/sửa Certificate** trong namespace?
- **Ai được chọn Issuer/ClusterIssuer** và request SAN?
- **Issuer có thực sự ràng buộc quyền với SAN/namespace/service owner** không?
- **Ai được đọc Secret/private key** và thay deployment để dùng nó?

### Nguy cơ thường gặp

Nếu mọi namespace đều có quyền xin certificate từ **ClusterIssuer** tin cậy mà không có issuer policy/ràng buộc tên, một workload có thể xin SAN của dịch vụ khác. Cần kiểm soát bằng RBAC, admission policy, approver policy hoặc cơ chế quản trị phù hợp.

**cert-manager không tự chứng minh mọi pod được phép mang tên SAN yêu cầu**. Automation và authorization của enrollment là hai trách nhiệm cần thiết kế riêng.

## 21. SPIFFE/SPIRE: workload certificate enrollment khác CA truyền thống thế nào?

**SPIFFE** định nghĩa mô hình danh tính workload. Một **SPIFFE ID** có thể có dạng:

~~~text
spiffe://prod.example.org/ns/payments/sa/payments-api
~~~

**SPIRE** là một triển khai hỗ trợ **registration, node/workload attestation và cấp SVID** (SPIFFE Verifiable Identity Document). Với **X.509-SVID**, certificate mang SPIFFE ID trong **URI SAN**, thường được sử dụng cho **mTLS giữa workloads**.

### Luồng cấp X.509-SVID

~~~mermaid
flowchart LR
    POD[Workload Process] --> AG[SPIRE Agent / Workload API]
    AG --> AT[Node and Workload Attestation]
    AT --> REG[Registration Entry / SPIRE Server]
    REG --> SVID[X.509-SVID + Trust Bundle]
    SVID --> TLS[mTLS Handshake]
    TLS --> AUTH[Service Authorization Policy]
~~~

### Khác biệt cốt lõi

- Workload nhận SVID dựa trên **attestation/registration**, không chỉ gửi CSR gõ tên tùy ý.
- Credential thường **ngắn hạn** và được agent/Workload API làm mới.
- **Trust domain và SPIFFE ID** phải được relying party kiểm đúng.
- **SVID không tự cung cấp authorization policy**: service cần quyết định peer nào được gọi action nào.
- **Khi workload retire**, ngừng cấp SVID mới và xử lý kết nối hoặc cert cũ theo khả năng hệ thống.
- Federation nhiều trust domain yêu cầu quản trị **trust bundles** riêng, không tin mọi SPIFFE URI có tên giống nhau.

### Phân biệt certificate profile

**X.509-SVID không tự tương đương certificate DNS cho browser/public Web PKI**. Nó có semantics nhận dạng dựa trên SPIFFE ID và trust domain; dùng sai trust store/mục đích có thể gây nhầm identity.

## 22. Device enrollment, TPM và secure element

Với thiết bị vật lý, enrollment thường bắt đầu từ **device identity đã có từ nhà máy hoặc giai đoạn quản trị đầu tiên**.

### Dòng đời minh họa

1. Thiết bị được đưa vào **asset registry** với serial/asset ID và owner.
2. Nền tảng quản lý xác minh **bootstrap identity** và trạng thái thiết bị.
3. Thiết bị sinh key trong **TPM hoặc secure element** nếu có.
4. Enrollment client tạo CSR/PoP và bằng chứng attestation khi yêu cầu.
5. RA/CA xác minh device ID, profile và quyền xin SAN/subject.
6. CA cấp certificate thời hạn phù hợp.
7. Thiết bị cài certificate/trust chain để dùng trong mTLS hoặc truy cập mạng.
8. Rotation/renewal theo chính sách, có cảnh báo trước expiry.
9. Khi thất lạc/thải loại, ngừng cấp mới, thu hồi certificate và quyền đích.

### Chứng minh phần cứng không phải chứng minh người sở hữu

TPM có thể giúp ràng buộc khóa với một thiết bị, nhưng **không tự xác định thiết bị đó thuộc doanh nghiệp/tenant nào hoặc có được phép dùng service nào**. Phải kết hợp asset registry, owner, device posture và authorization.

### Bootstrap trust

Thiết bị mới chưa có certificate sản xuất có thể dùng **manufacturer identity, enrollment credential một lần, network bootstrap hoặc chính sách nhà máy**. Đây là giai đoạn rủi ro cao: cần tránh **bootstrap token chung cho mọi thiết bị**, credential dễ đoán và quá trình tự gắn serial không có kiểm tra.

## 23. Bootstrap và Zero Trust cho thiết bị/máy mới

Trước khi enrollment, một thiết bị có thể **chưa được trust trong mạng**. Một bootstrap an toàn phải trả lời:

- Thiết bị có chứng cứ **đúng phần cứng hoặc deployment** không?
- Chứng cứ do **vendor/enterprise/platform** nào phát hành?
- Owner đã phê duyệt thiết bị tham gia tenant/nhóm nào?
- Mã bootstrap chỉ dùng cho **một thiết bị/một mục đích** hay có thể replay?
- Thiết bị có biết **CA/RA endpoint** hợp lệ để tránh man-in-the-middle?
- Có yêu cầu **mạng hạn chế, staging, MDM enrollment** trước khi mở truy cập production?
- Có chính sách khi thiết bị được bán/chuyển owner/retire không?

Một số mô hình như **Bootstrapping Remote Secure Key Infrastructure (BRSKI)** được thiết kế cho bootstrap thiết bị có chứng cứ ban đầu và quá trình chuyển trust. Khi lựa chọn cần xét **hỗ trợ thiết bị và vendor ecosystem**; không xem việc thiết bị khai serial là proofing đủ.

**Zero Trust không có nghĩa không dùng PKI.** Nó yêu cầu **không mặc định tin** chỉ vì máy ở một subnet hoặc có certificate bất kỳ. Mỗi truy cập còn cần danh tính, ngữ cảnh, quyền và trạng thái thiết bị phù hợp.

## 24. TLS/mTLS: certificate được sử dụng và kiểm tra thế nào?

**TLS** dùng certificate server để hỗ trợ xác thực peer; **mTLS** yêu cầu phía client cũng cung cấp bằng chứng certificate theo cấu hình.

### Ví dụ flow mTLS

~~~mermaid
sequenceDiagram
    participant A as Service A
    participant B as Service B
    participant CA as Trust / Validation
    A->>B: TLS ClientHello
    B-->>A: Server certificate and handshake data
    A->>CA: Verify server chain, name, purpose, validity
    CA-->>A: Valid or reject
    B->>A: Request client certificate
    A-->>B: Client certificate and proof of private key
    B->>CA: Verify client chain, SAN, EKU, trust policy
    CA-->>B: Valid or reject
    A->>B: Protected application request
    B->>B: Authorize peer, action and resource
    B-->>A: Permit/Deny and response
~~~

Sơ đồ là **mô hình khái niệm**, không mô tả đầy đủ thứ tự mọi thông điệp TLS 1.3 hoặc mọi thư viện. Kết quả kiểm certificate vẫn phải kết hợp với **application authorization**.

### Đừng dừng ở TLS handshake thành công

Một peer mTLS hợp lệ có thể được phép gọi **GET /metrics** nhưng không được **POST /payments/refund**. Application cần kiểm:

~~~text
permit if
    peer.certificateChainValidated
    and peer.identity == "service:orders-api"
    and peer.certificatePurposeAllowsClientAuth
    and action == "payments.create"
    and resource.tenantId in peer.approvedTenants
    and serviceRegistry[peer.identity].status == ACTIVE
    and not violatesMandatoryPolicy
else deny
~~~

Đây là **giả mã**, không phải cú pháp một policy engine cụ thể. **Certificate clientAuth không được dùng làm global admin pass**.

### Khi sử dụng reverse proxy/service mesh

Nếu proxy kiểm mTLS rồi truyền peer identity cho backend, backend chỉ được tin **metadata/header đã được bảo vệ trong trust boundary**. Không nhận header **X-Client-Cert** hoặc **X-Spiffe-Id** từ kết nối Internet như bằng chứng danh tính mà không có cơ chế xác minh.

## 25. Renewal automation và cửa sổ gia hạn

Certificate có hạn **NotAfter**. Nếu không tự động gia hạn, hệ thống có thể gặp outage khi certificate hết hạn; nếu gia hạn vô điều kiện cho máy đã retire, lại tạo **quyền tồn dư**.

### Quy trình renewal an toàn

1. Inventory xác định certificate sắp hết hạn theo owner, issuer và criticality.
2. Scheduler chọn renewal window có **thời gian dự phòng** cho retry và rollout.
3. Enrollment client kiểm danh tính/authorization hiện hành.
4. Sinh CSR mới, có thể **rekey** theo policy.
5. CA kiểm lại profile, SAN và tư cách requester.
6. Nhận certificate/chain mới rồi kiểm đúng identity, validity, EKU và issuer.
7. Triển khai **atomic hoặc staged**, tránh file nửa chừng.
8. Reload/restart ứng dụng theo cách giảm downtime.
9. Kiểm kết nối TLS/mTLS và authorization mới.
10. Dọn certificate/key cũ sau cửa sổ giao nhau có kiểm soát.
11. Ghi audit và đối soát inventory với **certificate thực đang được phục vụ**.

### Renewal khác revalidation

Một CA có thể hỗ trợ **reenrollment** đơn giản dựa trên certificate cũ; nhưng khi asset đã **Mover, retire, mất owner hoặc SAN đổi**, quy trình vẫn cần kiểm theo nguồn hiện hành. Không dùng certificate cũ làm giấy phép gia hạn vĩnh viễn cho mọi tên khác.

### Cửa sổ giao nhau

Khi đổi certificate/key, một số client cần thời gian để nhận **trust bundle/CA chain** mới. Có thể duy trì hai certificate trong một khoảng được quản trị, nhưng **không để key cũ tồn tại mãi**. Nếu key bị compromise, không nên duy trì overlap theo lịch thông thường.

## 26. Rotation: thay khóa, issuer hoặc trust anchor

Các thay đổi có thể khác nhau:

| Loại rotation | Nội dung | Cần lưu ý |
|---|---|---|
| **Leaf certificate renewal** | Cấp certificate mới cho cùng subject/key hoặc key mới | TTL và SAN/identity |
| **Key rotation / rekey** | Sinh private/public key mới | Không làm lộ key và xoá quyền dùng key cũ |
| **Intermediate CA rotation** | Thay issuer/chain trung gian | Trust chain, chain selection, rollout |
| **Root CA rotation** | Thay trust anchor | Phân phối trust bundle, dual trust, cleanup |
| **Algorithm migration** | RSA → ECDSA hoặc thay thuật toán | Tương thích client, crypto policy |
| **Service identity rename** | Đổi DNS/SPIFFE ID hoặc trust domain | Map đúng workload, thu hồi identity cũ |
| **Owner/team change** | Chuyển trách nhiệm quản trị certificate | Rà soát quyền renew/revoke và secret access |

### Một bẫy: thay chứng thư nhưng giữ private key đã lộ

Nếu private key bị lộ, attacker có thể tiếp tục chứng minh possession của nó cho tới khi mọi relying party ngừng chấp nhận. **Cấp certificate mới trên cùng private key không loại bỏ khả năng giả mạo**. Cần **rekey, revoke/deny key/certificate cũ, kiểm session và cập nhật trust policy** theo khả năng hệ thống.

### Một bẫy khác: thay root mà quên máy legacy

Một client không được cập nhật trust store có thể mất kết nối, còn client giữ root cũ vô hạn có thể tiếp tục tin CA đã nghỉ. Cần theo dõi **tỷ lệ rollout, active chains và negative validation tests**.

## 27. Revocation: CRL, OCSP và giới hạn thực tế

**Certificate revocation** biểu thị certificate không còn được tin **trước NotAfter** vì key compromise, mis-issuance, thiết bị thất lạc, thay đổi ownership hoặc retire.

### Các cơ chế phổ biến

- **Certificate Revocation List (CRL):** danh sách chứng thư bị thu hồi được CA phát hành/ký; relying party tải và kiểm theo chính sách.
- **Online Certificate Status Protocol (OCSP):** cung cấp thông tin trạng thái chứng thư; client/server có thể sử dụng theo cấu hình.
- **OCSP stapling:** server cung cấp response phù hợp trong quá trình TLS để giảm truy vấn trực tiếp của client khi được hỗ trợ.
- **Short-lived certificates:** giảm thời gian phơi nhiễm nếu không dựa hoàn toàn vào kiểm revocation trực tuyến.
- **Authorization-side deny:** resource server từ chối workload/credential dù certificate có thể còn hợp lệ về mặt chữ ký.

### Ba ranh giới quan trọng

1. **Revocation request được CA chấp nhận** không có nghĩa CRL/OCSP đã cập nhật ngay tới mọi client.
2. **CRL/OCSP có thông tin revoked** không có nghĩa mọi relying party đều kiểm hoặc kiểm theo chính sách fail-closed.
3. **Certificate revoked** không tự đóng tất cả **TLS connection đã thiết lập hoặc session ứng dụng**.

Khi xảy ra compromise nghiêm trọng, có thể cần **chặn ngay ở gateway/PEP, ngừng issuance, ngắt session và thay key**, không chỉ gửi lệnh revoke.

### CRL/OCSP và privacy/availability

Relying party có thể cần quyết định hành vi khi revocation endpoint không khả dụng. **Fail-open/fail-closed phải được xác định theo mức rủi ro và khả năng phục vụ**, không tự mặc định một chiến lược cho mọi hệ thống. Với một số môi trường short-lived mTLS, kiến trúc có thể dùng TTL rất ngắn cộng trust/authorization controls thay vì phụ thuộc revocation online trong mỗi request.

## 28. Reconciliation: inventory khác trạng thái certificate thực tế

**Certificate Lifecycle Management (CLM)** cần so sánh:

- **Desired state:** certificate/identity nào được phép tồn tại, do owner nào quản lý, profile và TTL nào.
- **Issued state:** CA đã phát những certificate nào.
- **Deployed state:** workload nào đang phục vụ hoặc trình certificate nào.
- **Runtime accepted state:** relying party có chấp nhận và cho thực hiện action không.

| Sai lệch | Ví dụ | Hướng xử lý |
|---|---|---|
| **ISSUED_NOT_DEPLOYED** | CA phát cert mới nhưng service vẫn dùng cert cũ | Kiểm deploy/reload |
| **DEPLOYED_EXPIRED** | Endpoint vẫn trình NotAfter đã qua | Renewal/rollback có kiểm soát |
| **UNKNOWN_CERTIFICATE** | Endpoint trình cert không có trong inventory | Điều tra issuer/owner |
| **WRONG_SAN/EKU** | Certificate cho sai service hoặc purpose | Reissue đúng profile, revoke sai |
| **ORPHAN_CERTIFICATE** | Không owner hoặc workload đã retire | Review, chặn cấp mới và cleanup |
| **REVOKED_BUT_ACCEPTED** | Target vẫn cho mTLS hoặc action | Chặn tại PEP, kiểm revocation/cache |
| **STALE_PRIVATE_KEY** | Key cũ vẫn tồn tại sau rotation | Xóa/vô hiệu và kiểm nơi copy |
| **DUPLICATE_IDENTITY** | Nhiều workload khác nhau dùng một key | Tách identity và đánh giá rủi ro |
| **TRUST_ANCHOR_DRIFT** | Một nhóm client vẫn tin root cũ | Trust store rollout và tests |
| **UNAUTHORIZED_REENROLLMENT** | Workload retire vẫn được CA cấp cert mới | Sửa policy, source version và revoke |
| **MISMATCHED_ACCOUNT** | Cert được map vào wrong service principal | Xác minh immutable ID/registry |
| **CERT_VALID_BUT_ACCESS_WRONG** | Chain hợp lệ nhưng API permit sai tenant | Sửa RBAC/ABAC và target enforcement |

**HTTP 200 từ enrollment endpoint chỉ có nghĩa một thao tác đã được xử lý theo giao thức.** Nó không chứng minh chứng thư được cài đúng hoặc không còn quyền tồn dư sau revocation.

## 29. Machine identity và vòng đời Joiner–Mover–Leaver

Máy không phải nhân viên, nhưng **người/nhóm chịu trách nhiệm**, approval và credential quản trị của nó có thể thay đổi theo JML.

### Joiner — người phụ trách mới

- HRIS xác minh quan hệ nhân viên và account IdP.
- IAM cấp quyền quản lý **certificate inventory/CA enrollment** theo nhiệm vụ, không phải quyền ký CA tùy ý.
- Owner mới được gắn với machine/workload registry nếu hợp lệ.
- Phân biệt **human admin privilege** với certificate/private key của workload.
- Nếu cấp quyền **approve certificate enrollment**, cần SoD và MFA theo rủi ro.

### Mover — đổi đội/vai trò/tenant

- Gỡ quyền cá nhân của owner cũ trên CA, secret manager và deployment.
- Cập nhật owner/sponsor mới và certificate approval route.
- Rà soát certificate profile/SAN/tenant nếu workload thực sự di chuyển.
- Thu hồi credential hoặc key mà người cũ không còn nên dùng.
- Kiểm group mapping ở CA, IdP và ứng dụng đích.
- Không tự tăng quyền production enrollment do một role job mới.

### Leaver — người phụ trách nghỉ việc

- Thu hồi **human access** vào CA/RA, vault, CI/CD, MDM, Kubernetes và issuer policy.
- Kiểm xem người nghỉ có thể biết/đã sao chép **private key, enrollment token hoặc account key** không.
- Chuyển owner của machine identity nếu workload/device vẫn cần vận hành.
- Rotate/rekey khi rủi ro yêu cầu; không xóa bừa service production.
- Tắt các luồng enrollment do người cũ sở hữu/được ủy quyền trái policy.
- Rà soát các certificate direct-grant không nằm trong registry.

### Rejoiner

Một nhân viên quay lại làm việc **không được tự khôi phục quyền quản trị CA/vault** dựa trên role lịch sử. Mọi quyền phải xét quan hệ hiện hành và approved role mới.

**Human Leaver không đồng nghĩa workload Retire.** Quyền người cũ phải được cắt, còn certificate/service hợp lệ có thể cần hoạt động dưới owner mới và review/rotation phù hợp.

## 30. Machine lifecycle: Create–Activate–Change–Retire

Một thiết bị hoặc workload có vòng đời kỹ thuật riêng:

| Giai đoạn | Hoạt động enrollment liên quan | Kiểm soát |
|---|---|---|
| **Discover/Register** | Gắn asset/workload ID với owner và trust domain | Không cấp cho ID vô chủ |
| **Provision/Bootstrap** | Chứng minh identity ban đầu, tạo key | Không dùng shared enrollment secret |
| **Enroll/Activate** | CSR, CA issuance, deploy, verify | Subject/SAN/profile/approval |
| **Operate** | mTLS/TLS, audit, periodic review | RBAC/ABAC, key protection, TTL |
| **Scale/Redeploy** | Cấp cert cho instance mới | Workload attestation, namespace trust |
| **Move/Change** | Thay owner, tenant, SAN hoặc service role | Re-evaluate và rekey khi cần |
| **Suspend** | Phát hiện compromise hoặc không đạt compliance | Dừng cấp mới và chặn truy cập |
| **Retire** | Revoke/deprovision/clean key và account | Readback, negative action test |
| **Reenroll after recovery** | Tạo khóa/cert mới có căn cứ | Không tự hồi sinh identity bị cấm |

### Race condition nguy hiểm

- 10:00 workload bị đánh dấu **RETIRED**.
- 10:01 hệ thống gỡ role và revoke certificate.
- 10:02 renewal job cũ chạy lại với snapshot trước retire.
- 10:03 CA cấp certificate mới cho identity đã nghỉ.

Nếu không có **source version, generation/fencing hoặc revalidation** khi issuance, hệ thống có thể tái cấp danh tính không hợp lệ. **Chặn enrollment mới phải dựa trên state hiện hành**, không chỉ danh sách request cũ.

### Thu hồi account không tự thu hồi certificate

Nếu thiết bị đã có private key/certificate, xóa account ở IdP/SCIM không có nghĩa TLS client certificate tự ngừng được chấp nhận. Relying party cần kiểm revocation/trust/identity state hoặc cơ chế chặn phù hợp.

## 31. Certificate enrollment và IdP, SSO, SCIM, RBAC/ABAC

### IdP/SSO cho con người

IdP/SSO xác thực nhân viên quản trị CA/RA, certificate inventory và MDM. **MFA/step-up** có thể bắt buộc khi approve enrollment cho certificate đặc quyền hoặc sửa trust policy.

Tuy nhiên, workload không nên phải đăng nhập bằng **mật khẩu/cookie SSO của một nhân viên** để xin certificate. Nó cần machine credential, attestation hoặc token enrollment riêng được quản trị.

### SCIM và account provisioning

SCIM thường quản lý **User/Group** trong ứng dụng doanh nghiệp; có thể giúp đồng bộ nhóm người được quyền quản lý certificate service hoặc technical user khi SaaS hỗ trợ. Nhưng **SCIM User/Group không phải giao thức PKI enrollment**, không tự tạo CSR hoặc phát SVID. Cần dùng CA/RA, ACME/EST/SCEP/CMP hoặc API đặc thù.

### RBAC/ABAC/PBAC

Một certificate có thể được map thành **service principal** ở API, nhưng quyền action cần dựa trên policy:

~~~text
permit if
    certificate.chainTrusted
    and certificate.nameOrUriMatchesExpectedIdentity
    and certificate.purposeAllowed
    and identityRegistry[serviceId].status == ACTIVE
    and action in identityRegistry[serviceId].approvedActions
    and resource.tenantId in identityRegistry[serviceId].approvedTenants
    and noMandatoryDeny
else deny
~~~

Giả mã trên **không thay thế TLS library**: việc kiểm certificate chain, SAN, EKU, revocation và algorithm phải do stack bảo mật phù hợp thực hiện. Policy nghiệp vụ kiểm thêm **action/resource/context**.

### Phân tách quyền quản trị

Quyền **enroll certificate**, **approve certificate**, **change CA profile**, **issue subordinate CA** và **modify trust store** là các quyền khác nhau. Tổ chức cần cân nhắc **SoD** để ngăn một người vừa mở rộng policy vừa tự cấp CA cấp dưới mà không có kiểm soát độc lập.

## 32. Threat model: tấn công vào enrollment và certificate lifecycle

| Rủi ro | Ví dụ | Kiểm soát |
|---|---|---|
| **CSR giả mạo SAN** | Xin certificate cho service khác | SAN authorization, owner/attestation |
| **Key compromise** | Private key bị lộ từ pod/image | HSM/TPM, least privilege, rekey/revoke |
| **Mis-issuance** | CA cấp clientAuth/CA=true sai profile | CA templates, approval, audit |
| **Shared enrollment secret** | Nhiều thiết bị dùng cùng challenge | Unique one-time credential, binding, TTL |
| **ACME DNS API compromise** | Attacker kiểm soát DNS-01 challenge | Scoped DNS credential, audit, rotation |
| **CA/RA takeover** | Issuer bị chiếm cấp cert tùy ý | HSM, SoD, monitoring, incident response |
| **Rogue Intermediate CA** | Cấp certificate ngoài policy | Root governance, constraints, trust inventory |
| **Subject collision** | Hai workload dùng cùng tên và key | Stable ID, namespace/trust domain |
| **Weak cryptography** | Key size/algorithm không còn đạt policy | Algorithm policy và renewal migration |
| **Wrong EKU/KU** | Server cert được dùng làm client auth sai | Certificate profile và verifier |
| **Revocation ignored** | Client không kiểm CRL/OCSP/state | Runtime enforcement và negative tests |
| **Expired-but-deployed** | Service ngừng hoạt động vì hết hạn | Monitoring và renewal automation |
| **Trust store poisoning** | Client tin CA không được duyệt | Bundle approval và rollout integrity |
| **Compromised enrollment agent** | Agent xin nhiều certificate trái scope | Agent identity và quyền hẹp |
| **Token replay** | Enrollment token bị copy | PoP, TTL, binding và anti-replay |
| **Cross-tenant confusion** | Cert tenant A truy cập tenant B | Tenant-aware mapping và ABAC |
| **Stale renewal** | Job cũ tái cấp cert sau retire | Version/fencing, revalidate |
| **Wrong target deployment** | Cert/privkey cài sang service khác | Secure distribution, identity checks |
| **SSRF/metadata abuse** | Lấy bootstrap credential qua metadata | SSRF defense, metadata access control |
| **Logging secrets** | Private key bị đưa vào ticket/log | Secret scanning, redaction, incident handling |
| **Unowned inventory** | Certificate không ai chịu trách nhiệm | Owner review, expiry, discovery |
| **Break-glass abuse** | Dùng quyền CA khẩn cấp như quyền thường | Vault, alert, dual control, post-review |

**Certificate có chữ ký hợp lệ không có nghĩa hành động của một peer là hợp lệ.** Threat model phải bao phủ **enrollment, key custody, trust chain, runtime authorization và post-revocation behavior**.

## 33. Audit, inventory và chỉ số giám sát certificate enrollment

### Audit event nên có

- **MachineRegistered:** asset/workload ID, owner, trust domain.
- **EnrollmentRequested:** requester/agent, CSR fingerprint, SAN, profile, requestId.
- **IdentityValidated:** nguồn proofing/attestation, policy version, result.
- **EnrollmentApproved/Rejected:** actor, reason, approver authority.
- **KeyGenerated:** loại key storage, không ghi private key.
- **CertificateIssued:** issuer, serial, fingerprint, SAN, KU/EKU, NotBefore/NotAfter.
- **CertificateDelivered/Deployed:** target, deployment version, observed certificate.
- **TLSIdentityValidated:** relying party, peer identity, decision, mục đích.
- **RenewalRequested/Completed:** old/new serial, rekey indicator.
- **RevocationRequested/Published:** reason, observed revocation state.
- **IdentityRetired:** workload/device status, owner, cleanup evidence.
- **ReconciliationFinding:** sai lệch, risk, owner, deadline, verifiedAt.

### Ví dụ event JSON

~~~json
{
  "eventId": "cert-enroll-20261123-041",
  "requestId": "enroll-payments-7182",
  "machineIdentityId": "service:payments-api",
  "ownerTeamId": "payments-platform",
  "issuerId": "internal-services-ca",
  "certificateSerial": "00A18F7C",
  "certificateFingerprintSha256": "example-fingerprint-not-real",
  "san": ["DNS:payments-api.payments.svc.cluster.local"],
  "intendedUsage": ["TLS_SERVER"],
  "notBefore": "2026-11-23T03:00:00Z",
  "notAfter": "2026-12-23T03:00:00Z",
  "policyVersion": "internal-tls-v4",
  "status": "ISSUED",
  "correlationId": "corr-4d27"
}
~~~

Đây là **schema audit minh họa**, không phải chuẩn API CA. Không ghi **private key, bearer token, challenge secret, recovery key hoặc CSR chứa thông tin nhạy cảm không cần thiết** vào log công khai. Fingerprint có thể dùng làm dấu vết certificate, không phải authorization credential.

### Metrics hữu ích

| Metric | Đo lường | Lưu ý |
|---|---|---|
| **Certificate inventory coverage** | Tỷ lệ workload/device có certificate được quản lý | Discovery có thể thiếu endpoints legacy |
| **Certificates expiring soon** | Số cert dưới ngưỡng expiry cảnh báo | Ưu tiên theo criticality |
| **Renewal success rate** | Tỷ lệ gia hạn và triển khai thành công | CA issued không đủ; cần deployed |
| **Time to deploy/activate** | Thời gian từ issuance tới handshake hợp lệ | Phát hiện lỗi rollout |
| **Certificate age / TTL** | Phân bố validity theo profile | TTL ngắn cần automation tốt |
| **Certificates with unknown owner** | Chứng thư không có owner | Rủi ro thiếu trách nhiệm |
| **Wrong SAN/EKU findings** | Sai danh tính/mục đích | Enrollment policy gaps |
| **Long-lived/exportable private keys** | Key có rủi ro tồn tại lâu | Ưu tiên cải thiện key custody |
| **Revoked-but-accepted findings** | Certificate đã revoke vẫn dùng được | Rủi ro runtime trust |
| **Retired-but-issued certificates** | CA tiếp tục cấp cert sau retire | Source-of-truth/fencing lỗi |
| **Unapproved CA/trust anchor count** | Trust store drift | Có thể tạo đường giả mạo |
| **Orphan renewal jobs** | Job còn chạy sau đổi owner/retire | Nguy cơ reissuance |
| **Human owner JML handoff backlog** | Cert chưa chuyển owner khi nhân viên rời | Cần governance |
| **CA/RA approval exceptions** | Ngoại lệ cấp certificate đặc biệt | Phải có reason, owner và expiry |
| **End-to-end negative validation coverage** | Tỷ lệ cert sai identity/role bị Deny | Đánh giá kiểm soát thực thi |

**Tỷ lệ cấp certificate thành công cao không tự chứng minh PKI an toàn**; chỉ số phải bao gồm **cấp đúng tên/đúng người, triển khai đúng mục đích và từ chối sau hết hiệu lực**.

## 34. Kiểm thử Certificate enrollment và vận hành

| Test case | Tình huống | Kết quả mong đợi |
|---|---|---|
| **CSR hợp lệ** | Key/CSR đúng policy, requester được phép SAN | CA có thể cấp sau đầy đủ kiểm tra |
| **CSR signature sai** | PoP không hợp lệ | Reject |
| **Requester không thuộc owner** | Xin SAN của service khác | Deny |
| **Wildcard trái policy** | Xin tên rộng hơn quyền | Deny hoặc yêu cầu scope khác |
| **Wrong EKU** | Client xin CA cert hoặc clientAuth trái profile | Deny |
| **Weak key** | Thuật toán/key size ngoài policy | Reject |
| **Expired enrollment credential** | Bootstrap token quá hạn | Deny |
| **Replay challenge** | One-time token bị dùng lại | Deny theo cơ chế |
| **ACME challenge failed** | Không chứng minh domain control | Không issue |
| **Certificate đã ký nhưng chưa deploy** | Agent lỗi sau issuance | Không báo deployment success |
| **Wrong chain** | Endpoint phục vụ intermediate sai | Handshake/check chain thất bại |
| **Wrong hostname** | DNS SAN không khớp endpoint | Client reject |
| **Wrong SPIFFE trust domain** | Peer ID có path đúng nhưng domain sai | Deny |
| **Wrong client EKU** | Server certificate dùng để clientAuth | Reject khi profile/validator yêu cầu |
| **Certificate expired** | NotAfter đã qua | Reject |
| **Certificate revoked** | CRL/OCSP hoặc identity state không còn hợp lệ | Deny theo policy |
| **CA revocation service down** | Không lấy được trạng thái | Hành vi theo risk policy đã thiết kế |
| **mTLS peer đúng nhưng action sai** | orders-api gọi payment.refund ngoài quyền | 403/Deny |
| **Tenant mismatch** | Cert tenant A gọi resource tenant B | Deny |
| **Rotation overlap** | Old/new certificate cùng tồn tại ngắn | Đảm bảo không outage và cleanup |
| **Compromised key** | Key bị lộ, cấp cert mới cùng key | Không coi là đã khắc phục |
| **Intermediate/root rotation** | Trust bundle đang chuyển | Test legacy clients và deny root cũ sau cutover |
| **Kubernetes role quá rộng** | Namespace bất kỳ xin SAN của service khác | Deny qua issuer policy |
| **Device lost** | Device bị đánh dấu thất lạc | Ngừng enrollment và thu hồi/quarantine |
| **Owner Leaver** | Owner nghỉ nhưng service còn chạy | Gỡ quyền human, chuyển owner, review key |
| **Machine Retired** | Renewal job cũ chạy sau retire | Deny bằng current state/version |
| **Connector timeout** | CA đã cấp cert nhưng response mất | Readback trước retry |
| **Duplicate certificate** | Nhiều cert cùng identity không rõ owner | Inventory/finding |
| **Audit secret leakage** | Enrollment log chứa private key | Test phải phát hiện/chặn |
| **Runtime stale session** | Cert bị thu hồi nhưng TLS session còn hoạt động | Xử lý session/PEP theo yêu cầu |
| **Reconciliation** | Target phục vụ cert khác inventory | Finding với owner và SLA |

### Những tầng test nên có

1. **CA profile unit tests:** SAN, KU/EKU, validity, basic constraints và key policy.
2. **Enrollment protocol tests:** ACME challenge, EST/SCEP/CMP auth và error cases khi dùng.
3. **Attestation/bootstrap tests:** device/workload identity, unauthorized names.
4. **Integration tests:** CA/RA, IAM, MDM, Kubernetes, CI/CD và target deployment.
5. **TLS/mTLS tests:** chain, name, purpose, expiry, revocation và trust domain.
6. **Authorization tests:** certificate hợp lệ nhưng action/resource sai phải Deny.
7. **Rotation tests:** overlap, reload, dual trust và key deletion.
8. **Concurrency tests:** retire cạnh tranh với renewal, stale job.
9. **Failure injection:** 429, 5xx, timeout, CA unavailable, CRL/OCSP outage.
10. **Audit/privacy tests:** trace request–issue–deploy–revoke nhưng không lộ key.

**Test chỉ xác minh OpenSSL đọc được certificate chưa đủ**. Cần chứng minh **client tin đúng danh tính, backend áp đúng quyền và certificate không còn được chấp nhận khi căn cứ hết**.

## 35. Runbook: lỗi enrollment, TLS và thu hồi

### A. Enrollment bị từ chối

1. Lấy **requestId, machine identity, owner, SAN, profile và issuer**.
2. Kiểm máy/workload còn ở trạng thái **ACTIVE/ELIGIBLE** và đúng quan hệ/tenant.
3. Kiểm CSR signature, public key algorithm, key size và SAN đề xuất.
4. Kiểm enrollment client authentication/attestation/challenge.
5. Xem CA/RA policy và reason code, tránh sửa bằng cách bỏ kiểm tên.
6. Kiểm approval bắt buộc và thời hạn certificate.
7. Không yêu cầu người dùng gửi private key vào ticket để debug.

### B. Issued nhưng TLS handshake lỗi

1. Xác minh certificate thực được phục vụ có serial/fingerprint đúng.
2. Kiểm chain, trust anchor và intermediate certificates.
3. Kiểm SAN và peer name/trust domain.
4. Kiểm NotBefore/NotAfter, clock, KU/EKU và algorithm.
5. Với mTLS, kiểm cả client certificate và server certificate.
6. Kiểm key/certificate matching và ứng dụng đã reload certificate chưa.
7. Tách lỗi **TLS authentication** khỏi lỗi **HTTP 403 authorization**.

### C. Renewal thất bại trước expiry

1. Xác định expiry và mức rủi ro outage.
2. Kiểm CA/RA availability, quota, rate limit và enrollment credential.
3. Kiểm SAN/profile/owner có thay đổi khiến yêu cầu không còn hợp lệ.
4. Kiểm key storage/CSR generation và quyền filesystem.
5. Kiểm deploy/reload; tránh cấp liên tục chứng thư mà không cài.
6. Retry có backoff và readback nếu không biết CA đã issue hay chưa.
7. Escalate trước hạn với owner; không dùng certificate giả hoặc tắt validation để chữa cháy.

### D. Private key bị lộ hoặc certificate bị cấp sai

1. Xác định certificate serial, issuer, SAN, private key location và phạm vi.
2. Ưu tiên **chặn action nhạy cảm** tại gateway/PEP hoặc resource policy.
3. Ngừng issuance/renewal sai, vô hiệu enrollment credential bị lộ.
4. Thu hồi certificate theo CA/PKI policy và kiểm trạng thái công bố.
5. **Sinh key mới** trong môi trường tin cậy; không dùng lại key đã compromise.
6. Reissue certificate đúng owner/profile/SAN, rollout có kiểm soát.
7. Xử lý TLS sessions, OAuth tokens và credential liên quan.
8. Kiểm audit truy cập trong cửa sổ rủi ro, mở incident và finding khi cần.
9. Chỉ đóng khi có evidence rằng các đường dùng credential cũ đã bị chặn trong phạm vi xác minh.

### E. Máy đã Retired nhưng vẫn dùng certificate

1. Lấy source-of-truth, workload/device ID, effectiveAt và generation.
2. Dừng các renewal job cũ; chặn cấp certificate mới.
3. Thu hồi role, trust binding và credential hiện hành.
4. Kiểm CRL/OCSP/PEP thực tế ở các bên nhận.
5. Đóng TLS connections/session nếu rủi ro yêu cầu và nền tảng hỗ trợ.
6. Readback inventory, negative test theo resource/action.
7. Mở exception có owner/SLA nếu không thể cắt quyền ngay; không báo thành công giả.

## 36. Tình huống xuyên suốt: certificate enrollment trong hệ thống thanh toán

Giả sử doanh nghiệp có **payments-api** chạy trong Kubernetes, các **POS terminals** ở chi nhánh, một **CA nội bộ** và ứng dụng đối tác cần mTLS.

### Giai đoạn 1 — Đăng ký machine identity

Đội Platform đăng ký **service:payments-api** thuộc namespace payments, production trust domain và owner team Payments. Đội thiết bị đăng ký từng POS bằng **asset ID/serial, tenant và chi nhánh**. Không dùng chung một machine identity cho mọi pod và mọi POS nếu phạm vi truy cập khác nhau.

### Giai đoạn 2 — Enrollment của payments-api

Workload được runtime/SPIRE hoặc enrollment agent xác minh theo binding. Agent tạo key pair ở nơi được phép, xây CSR/SVID request với **đúng danh tính service**. CA/issuer chỉ cấp profile **mTLS client/server** thích hợp. Khi certificate được triển khai, orders-api xác thực trust domain và định danh peer, rồi vẫn kiểm **payments.create** theo tenant.

### Giai đoạn 3 — Enrollment của POS terminal

Một POS mới được nhập asset registry và owner chi nhánh. Thiết bị sinh key trong **TPM/secure element** khi có; enrollment qua giao thức device CA hỗ trợ. CA xác minh bootstrap identity, serial, tenant và device profile trước khi phát hành client certificate.

POS có certificate hợp lệ vẫn chỉ được gọi những API **device/payment operations** thuộc chi nhánh và tenant được gán. Không cho POS dùng API quản trị IAM.

### Giai đoạn 4 — Mover của chủ sở hữu

Kỹ sư phụ trách payments-api chuyển sang dự án khác. IAM thu hồi quyền người đó đối với **CA enrollment policy, Kubernetes secrets, production deployment và vault**; owner team mới được chỉ định. Certificate của payments-api hợp lệ vẫn được dùng nếu danh tính/phạm vi không đổi, nhưng Security phải đánh giá private key cũ và renewal permissions.

### Giai đoạn 5 — Certificate rotation

Certificate payments-api sắp hết hạn. Automation xác minh service vẫn ACTIVE và SAN không đổi, tạo CSR/key mới theo policy, CA cấp certificate, agent triển khai. Sau khi test handshake và authorization, key/certificate cũ được dọn theo cửa sổ an toàn.

### Giai đoạn 6 — Mất POS và thu hồi

Một POS bị thất lạc. MDM/asset registry chuyển device sang **LOST/SUSPENDED**, issuer ngừng cấp mới. CA xử lý revoke certificate; gateway chặn device identity và thu hồi quyền liên quan. Vì certificate cũ có thể còn được chấp nhận bởi client thiếu kiểm revocation, Security phải kiểm **runtime deny** và token/session độc lập trước khi đóng incident.

### Giai đoạn 7 — Service Retire

Doanh nghiệp thay payments-api bằng dịch vụ mới. Registry chuyển workload cũ sang RETIRED, automation ngừng renew; CA/PEP thu hồi certificate và role cũ. Những job enrollment chạy trễ bị source version/fencing chặn; target readback và negative test xác nhận workload cũ không thể gọi queue hoặc API.

### Bài học rút ra

**Certificate enrollment nối identity proofing, ownership, key possession, CA policy và thời hạn sử dụng thành một đường tin cậy có thể tự động hóa.** Nhưng chứng thư hợp lệ chỉ là **chứng cứ xác thực**: **RBAC/ABAC, runtime enforcement, revocation và reconciliation** mới chứng minh workload/thiết bị được phép hành động đúng phạm vi và ngừng được phép khi quan hệ kết thúc.

## 37. Checklist triển khai Certificate enrollment an toàn

1. **Đối tượng:** đã biết machine/workload/device ID, purpose, owner và trust domain?
2. **Phân biệt:** enrollment khác issuance, deployment, renewal, rekey và revocation?
3. **CA/RA:** issuer, approval authority và certificate policy được xác định?
4. **Proofing:** requester không thể tự xin SAN/subject của máy khác?
5. **PoP:** CSR signature/khóa công khai được kiểm đúng?
6. **Attestation:** khi yêu cầu, chứng cứ hardware/runtime lấy từ nguồn đáng tin?
7. **Key generation:** thuật toán và key size đáp ứng crypto policy hiện hành?
8. **Key custody:** HSM/TPM/KMS/OS store/file permissions phù hợp và có owner?
9. **Private key safety:** không lộ trong Git, image, CI log, ticket hoặc backup không bảo vệ?
10. **CSR:** extension client đề xuất được CA kiểm và áp template riêng?
11. **SAN:** DNS/IP/URI/SPIFFE ID thuộc đúng identity và tenant?
12. **KU/EKU:** certificate chỉ dùng đúng mục đích, leaf không có CA capability trái phép?
13. **Validity:** NotBefore/NotAfter và max TTL được quản lý?
14. **Trust:** root/intermediate/trust bundle và name constraints được kiểm ở relying party?
15. **ACME:** domain challenge/account key/DNS API được bảo vệ nếu sử dụng?
16. **EST/SCEP/CMP:** bootstrap/client auth/challenge và profile được xác minh khi dùng?
17. **Kubernetes:** Certificate/Issuer/Secret RBAC không cho mọi namespace mạo danh service?
18. **SPIFFE/SPIRE:** trust domain, workload attestation, SVID/agent rotation đúng?
19. **Device:** asset/serial/owner và hardware key được kiểm nếu use case yêu cầu?
20. **mTLS:** xác thực cả hai phía, peer identity map đúng application principal?
21. **Authorization:** certificate hợp lệ không tự mở permission trên mọi resource?
22. **Least privilege:** action/resource/environment/tenant scope bị giới hạn?
23. **SoD:** quyền enroll, approve, issue CA và modify policy được phân tách khi cần?
24. **Rotation:** có renew-before, rekey policy, overlap và reload an toàn?
25. **Trust rotation:** có kế hoạch root/intermediate cutover và legacy client tests?
26. **Revocation:** CRL/OCSP hoặc alternative enforcement phù hợp risk?
27. **Session:** certificate/key bị revoke không bị hiểu nhầm là mọi session đã đóng?
28. **JML human:** Joiner/Mover/Leaver của người quản trị CA/owner được xử lý?
29. **Machine lifecycle:** create, change, suspend, retire có trigger và current-state checks?
30. **Stale jobs:** renew/provision job cũ không thể tái cấp certificate sau retire?
31. **IdP/SSO/SCIM:** human permissions và machine enrollment được phân biệt?
32. **Audit:** có requestId, serial, fingerprint, owner, policy, observed deployment và outcome?
33. **Monitoring:** có cảnh báo expiry, wrong SAN/EKU, revoked-but-accepted?
34. **Tests:** signature đúng nhưng name/scope/tenant sai phải Deny?
35. **Reconciliation:** desired/issued/deployed/accepted states được đối chiếu?
36. **Incident:** có runbook key compromise, mis-issuance, trust outage, device loss?
37. **Closure:** chỉ kết luận hoàn tất khi quyền thực tế bị chặn đúng và có evidence?

### Ghi nhớ

**Certificate enrollment là quá trình xác minh và cấp chứng thư số để liên kết public key với danh tính máy/workload theo chính sách của PKI.** Một quy trình an toàn phải kết hợp **identity proofing, proof of possession, CA/RA authorization, CSR/PKCS#10, subject/SAN, KU/EKU, key protection, certificate chain, deployment, renewal, rekey và revocation**. Các giao thức **ACME, EST, SCEP, CMP** hoặc hệ sinh thái **SPIFFE/SPIRE** có thể tự động hóa những phần khác nhau, nhưng **không thay thế runtime authorization**. Trong **IAM Identity Lifecycle**, phải tách vòng đời **Create–Change–Retire của máy** khỏi **Joiner–Mover–Leaver của người chịu trách nhiệm**, ngăn job cũ tái cấp chứng thư sau khi retire và **xác minh hệ thống đích thực sự từ chối quyền truy cập tồn dư**.
