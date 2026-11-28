# Provisioning key cho service: Cấp phát khóa mật mã an toàn cho workload

Một nền tảng thanh toán có **Billing Service** cần ký hóa đơn, **Customer Data Service** cần mã hóa hồ sơ và **Webhook Service** cần tạo HMAC để xác thực thông điệp gửi đối tác. Nhóm vận hành có thể tạo ba khóa tốt bằng KMS/HSM, nhưng câu hỏi tiếp theo mới quyết định mức độ an toàn: **cấp khóa cho từng service bằng cách nào, service chứng minh danh tính ra sao, được phép dùng khóa vào việc gì và ai có quyền thay đổi các quyền đó?**

Nếu đội phát triển gửi private signing key qua email, đặt KEK trong biến môi trường chung của tất cả pod hoặc chép một HMAC secret vào repository, thuật toán mật mã vẫn có thể đúng nhưng **quy trình phân phối khóa đã phá vỡ ranh giới tin cậy**. Ngược lại, nếu mỗi service nhận một **key reference/handle**, tự chứng minh workload identity và chỉ được gọi đúng phép toán mật mã trong KMS/HSM, tổ chức có thể giảm nhu cầu phân phối raw key material.

**Provisioning key cho service** là quá trình **đăng ký, xác thực, phê duyệt, cấu hình quyền, cấp hoặc cho phép sử dụng key material/key reference và xác minh service thực sự vận hành trong phạm vi được duyệt**. Đây không chỉ là “copy secret vào ứng dụng”. Nó bao gồm **trust bootstrap**, **workload identity**, **key generation**, **key purpose**, **distribution mode**, **access policy**, **lifecycle**, **audit** và **recovery**.

Trong chương **Key distribution** của mô-đun **SECURITY_KEY_MANAGEMENT_FUNDAMENTALS**, nội dung kết nối vòng đời khóa từ **tạo, cấp phát, lưu trữ, sử dụng, xoay vòng, thu hồi đến hủy** với mật mã đối xứng, bất đối xứng, chữ ký số, KMS/HSM, envelope encryption và kiểm soát truy cập. Một quy trình provisioning tốt phải đồng thời đáp ứng **bí mật, toàn vẹn, tính xác thực, khả năng sẵn sàng, cô lập tenant** và **khả năng chứng minh ai đã được cấp quyền gì tại thời điểm nào**.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

1. Phân biệt **key provisioning**, **key distribution**, **key enrollment**, **key authorization**, **key material export**, **key handle** và **key activation**.
2. Chọn cách cấp khóa phù hợp cho **AES-GCM DEK**, **KEK**, **HMAC secret**, **private signing key**, **mTLS private key/certificate** và **public verification key**.
3. Giải thích chuỗi **workload identity → authenticated request → policy check → key reference/cryptographic use → audit**.
4. Thiết kế quy trình có **owner, purpose, environment, tenant, key ID/version, algorithm, cryptoperiod, exportability, approvals và grants**.
5. Sử dụng **KMS/HSM, secrets manager, PKI, workload identity, TLS/mTLS** mà không mặc định raw secret luôn phải đi qua ứng dụng.
6. Phân tích rủi ro **bootstrap credential, confused deputy, cấp quyền quá rộng, long-lived secrets, cache, CI/CD, container và token compromise**.
7. Lập kế hoạch **rotation/re-provisioning, revoke, offboarding, failover/DR, backup và audit** mà không làm mất dữ liệu cũ.
8. Đọc và điều chỉnh một ví dụ **Java 17** kiểm tra chính sách cấp phát và phạm vi sử dụng khóa, nhận biết giới hạn giữa demo và enforcement thực.

## 2. Provisioning không đồng nghĩa phân phối raw key

Giả sử **Billing Service** cần dùng private key Ed25519 để ký hóa đơn. Có hai lựa chọn:

~~~text
HƯỚNG RỦI RO CAO:
Admin xuất private key PEM
    -> gửi qua chat/email
    -> developer chép vào config/CI
    -> app load PrivateKey và ký trong JVM

HƯỚNG ƯU TIÊN KHI ĐƯỢC PROVIDER HỖ TRỢ:
Admin/KMS operator tạo private key non-exportable trong HSM
    -> cấp role SIGN cho identity của Billing Service
    -> service gọi HSM/KMS.Sign(keyId, message)
    -> nhận chữ ký, KHÔNG nhận private key bytes
~~~

Hướng thứ hai **provision quyền sử dụng khóa**, không cần **provision bản sao private key**. Tuy nhiên, KMS/HSM Sign API vẫn có thể bị lạm dụng như **signing oracle** nếu service có quyền ký tùy ý mà không có kiểm tra nghiệp vụ. **Non-exportable không thay thế authorization**.

### 2.1. Thuật ngữ cần phân biệt

| Thuật ngữ | Ý nghĩa | Ví dụ |
|---|---|---|
| **Key generation** | Sinh vật liệu khóa bằng CSPRNG/provider hoặc thiết bị phù hợp | KMS tạo KEK hoặc DEK ngẫu nhiên |
| **Key enrollment/registration** | Gắn khóa hoặc requester với danh tính, owner, metadata và trust chain | Đăng ký public key/certificate, key ID |
| **Key provisioning** | Chuẩn bị đủ khóa, quyền, cấu hình và trạng thái để service dùng | Gán KMS grant và key reference cho workload |
| **Key distribution** | Truyền bản mã/secret/reference/certificate tới nơi cần | Trả wrapped DEK hoặc cấp certificate chain |
| **Key activation** | Chuyển key sang trạng thái được phép dùng theo policy | Cho phép Sign hoặc Encrypt mới từ T0 |
| **Key usage authorization** | Kiểm tra ai được gọi phép toán nào trên key nào | Billing chỉ được Sign, không Decrypt |
| **Key export** | Đưa raw key material ra khỏi ranh giới đang quản lý | Xuất AES key bytes hoặc private key PEM |
| **Key wrapping** | Bảo vệ một khóa bằng KEK hoặc key-protection mechanism | Wrapped DEK lưu cùng ciphertext |
| **Key reference/handle** | Tham chiếu key material được provider giữ | KMS key resource ID, HSM object handle |
| **Key rotation/re-provisioning** | Thay key material, version, grant hoặc consumer config theo policy | Chuyển signing key v3 sang v4 |
| **Key revocation/deprovisioning** | Chặn quyền hoặc key use theo phạm vi | Gỡ grant của service bị chiếm |

**Key ID và public key có thể được phân phối rộng hơn key material bí mật**, nhưng **toàn vẹn và nguồn tin cậy của chúng vẫn quan trọng**. Một public key bị thay bằng key của attacker có thể khiến dữ liệu được mã hóa tới nhầm người nhận hoặc chữ ký giả được chấp nhận.

### 2.2. Những gì service thật sự cần

Thay vì hỏi “service cần file khóa nào?”, hãy hỏi:

1. **Service cần thực hiện operation gì?** Encrypt, Decrypt, Wrap, Unwrap, Sign, Verify, GenerateMac, DeriveKey hay xác thực mTLS.
2. **Operation phải xảy ra ở đâu?** Trong HSM/KMS, crypto gateway, sidecar hay JVM của workload?
3. **Có bắt buộc cấp raw secret không?** Nếu provider cho phép Sign/Unwrap mà không xuất private key/KEK, ưu tiên handle.
4. **Secret có scope bao nhiêu?** Một record, một batch, một service, một tenant, một môi trường hay nhiều bên nhận?
5. **Ai có thể thu hồi và xoay vòng?** Key owner, Security administrator, platform operator, service owner; có phải hai người phê duyệt?
6. **Dữ liệu cũ cần giữ lại bao lâu?** Ciphertext hoặc chữ ký đã phát phải tiếp tục Decrypt/Verify theo lifecycle nào?

Một service chỉ **Verify chữ ký** thường chỉ cần **public verification key/certificate đáng tin cậy**, không cần private signing key. Một service chỉ **mã hóa dữ liệu mới** không nên mặc nhiên có quyền giải mã toàn bộ dữ liệu lịch sử.

## 3. Các mô hình provisioning chính

| Mô hình | Service nhận gì? | Ví dụ sử dụng | Rủi ro và lưu ý |
|---|---|---|---|
| **Opaque key handle + operation API** | Key ID/handle, IAM grant và crypto result | HSM Sign, KMS Wrap/Unwrap | Raw key thường không xuất; vẫn có nguy cơ API misuse |
| **Wrapped DEK / encrypted key blob** | Ciphertext của key cùng metadata | Envelope encryption cho file/record | Phải có Unwrap quyền hợp lệ; raw DEK có thể xuất khi dùng |
| **Ephemeral plaintext DEK** | Raw DEK tồn tại ngắn trong memory | Local AES-GCM với DEK do KMS cấp | Cache, heap dump, logs, TTL, nonce và scope |
| **Secrets manager delivery** | HMAC/API secret hoặc password tại runtime | Webhook HMAC signing, legacy integration | App có raw secret; rotation/lease/access log cần thiết |
| **PKI certificate enrollment** | Certificate chain; private key có thể ở workload hoặc HSM | mTLS, TLS client certificate | Không gửi private key theo kênh của certificate trừ khi có quy trình được duyệt |
| **Public key distribution** | Public key/JWKS/certificate và key ID | Verify Ed25519/JWT, RSA recipient encryption | Không bí mật nhưng cần authenticity, issuer/recipient trust |
| **Key import/BYOK/HYOK** | Wrapped/imported material hoặc external key use theo provider | Tuân thủ/chủ quyền khóa | Import policy, transport key, exportability và recovery khác nhau |
| **Derived key provisioning** | Derived key theo tenant/purpose hoặc key handle | HKDF per-service/per-tenant | Root/PRK phải được bảo vệ, info/context không nhập nhằng |

**Không có một lựa chọn duy nhất luôn đúng.** Chẳng hạn một **HMAC key** cần được đưa vào local JVM nếu service dùng JCA Mac trực tiếp và provider không hỗ trợ HMAC operation qua handle. Khi đó trọng tâm là **phân phối an toàn, giảm lifetime, quản lý phiên bản, tránh log và rotation**. Với private signing key có giá trị cao, HSM/KMS Sign thường hấp dẫn hơn vì không cần cấp raw private key cho mỗi instance.

### 3.1. Phân phối khóa đối xứng: DEK và HMAC

- **DEK** có thể do KMS sinh, bọc bằng KEK rồi đưa vào envelope; khi cần local AES-GCM, service được ủy quyền nhận plaintext DEK **trong memory tạm**, không lưu vĩnh viễn cạnh ciphertext.
- **HMAC key** là secret dùng chung cho bên tạo và bên xác minh MAC. Mọi bên biết key có thể tạo tag hợp lệ; không có tính **non-repudiation** như chữ ký số. Chỉ cấp cho principals cần GenerateMac/VerifyMac.
- **KEK/root key** bảo vệ khóa khác, thường có blast radius lớn; tránh phân phối raw material khi có thể thực hiện Wrap/Unwrap trong KMS/HSM.
- **KDF root** nếu xuất cho nhiều service có thể cho phép các service đó dẫn xuất quá nhiều khóa. Ưu tiên provider/boundary cấp **derived key theo tenant/purpose** và hạn chế DeriveKey.

### 3.2. Phân phối khóa bất đối xứng

- **Private signing key:** ưu tiên tạo/giữ trong HSM hoặc KMS khi phù hợp, cấp **Sign permission** cho workload.
- **Public verification key:** phân phối qua JWKS/certificate/trust store đúng issuer và key ID (kid); không tự tin khóa được lấy từ URL không đáng tin trong token.
- **Private key cho mTLS:** lý tưởng được tạo trong workload/HSM/agent được ủy quyền, private key không rời ranh giới đó; CSR được ký bởi CA theo enrollment policy.
- **Public encryption key của recipient:** phải xác thực recipient identity trước khi RSA-OAEP/HPKE bảo vệ DEK; mã hóa tới public key của attacker vẫn có thể “thành công” về mật mã.

**KMS/HSM không mặc nhiên hỗ trợ mọi đường ký, giải mã, import/export và sinh certificate.** Phải kiểm tra API, key type, key usage, non-exportability và key lifecycle thật của provider.

## 4. Trust bootstrap: Service chứng minh danh tính bằng cách nào?

**Vấn đề con gà–quả trứng:** để lấy secret một cách an toàn, service phải có một **danh tính/credential** đủ tin cậy. Nếu mọi service được phát một “bootstrap master key” cố định trong image để gọi KMS, tổ chức chỉ chuyển điểm yếu từ DEK sang bootstrap key.

### 4.1. Từ workload identity đến KMS permission

~~~mermaid
sequenceDiagram
    participant Deploy as Deployment/Orchestrator
    participant Svc as Service instance
    participant IdP as Workload Identity Provider
    participant Gate as Policy/KMS gateway
    participant KMS as KMS/HSM
    participant Audit as Audit
    Deploy->>Svc: Khởi chạy bằng workload identity được gắn
    Svc->>IdP: Xin credential ngắn hạn / assertion
    IdP-->>Svc: Token có issuer, audience, subject, expiry
    Svc->>Gate: Authenticated request + keyRef + action + context
    Gate->>Gate: Validate issuer/audience/expiry, principal, tenant, policy
    Gate->>KMS: Operation được phép trên keyId/version
    KMS-->>Gate: Handle/result hoặc DEK theo provider contract
    Gate->>Audit: principal, keyRef/version, action, decision, requestId
    Gate-->>Svc: Key reference/result, không log raw material
~~~

Một chuỗi **workload identity** có thể dựa trên cloud service identity/metadata endpoint, OIDC workload federation, mTLS client certificate, SPIFFE/SPIRE hoặc cơ chế khác. **Tên công nghệ không thay thế quy trình xác minh**: token phải được kiểm tra **issuer, audience, subject, expiry, chữ ký, phạm vi quyền** và những điều kiện policy thực sự được hỗ trợ.

### 4.2. Một identity cho mỗi service không có nghĩa một credential cho mọi instance

Phân biệt:

- **Logical service identity:** ví dụ payments/billing-sign, owner và purpose nghiệp vụ.
- **Workload instance identity:** pod/task/VM cụ thể, namespace, cluster, version, trust domain và thời gian tồn tại.
- **Credential phiên:** token hoặc client certificate có TTL, được cấp/renew theo policy và bị thu hồi khi workload rời hệ thống.
- **Application authorization:** người dùng cuối có quyền với hóa đơn/record nào, độc lập với việc Billing Service có quyền gọi KMS Sign.

Một workload có role KMS đúng vẫn có thể bị lợi dụng làm **confused deputy** nếu endpoint nhận tenantId/keyId của caller và thực thi Unwrap/Sign mà không kiểm tra quyền nghiệp vụ.

### 4.3. Nguyên tắc xử lý bootstrap secret

1. **Không bake long-lived KMS credential** hoặc private key vào container image, Git, unit test fixture hay CI artifacts.
2. Ưu tiên **identity gắn với workload tại runtime**, short-lived credential và quyền scope hẹp.
3. Nếu phải dùng bootstrap certificate/token, có **issuer, audience, TTL, rotation, revocation và enrollment control**.
4. Chỉ tin **identity claims từ nguồn đã xác thực**; không coi một HTTP header do caller tự đặt là bằng chứng.
5. Giới hạn quyền của bootstrap credential: có thể **xin session/attested identity** hoặc một key operation cụ thể, không mặc nhiên Export/Destroy/ManagePolicy.
6. Bảo vệ metadata endpoint, token exchange và service account credentials trước SSRF/RCE theo kiến trúc.
7. Audit **quyền cấp danh tính** và **quyền được cấp với key**, không dùng chung một tài khoản admin cho provisioning và dữ liệu.

**Attestation** có thể củng cố rằng workload chạy ở môi trường được đo lường/được chấp thuận, nhưng phải kiểm tra **phạm vi chứng thực, trust roots, freshness, mã ứng dụng, phiên bản và khả năng replay**. Không suy rằng có hardware attestation là service không thể bị lạm dụng sau khi được cấp quyền.

## 5. Chính sách Provisioning: Cần đủ điều kiện trước khi cấp

Một request provisioning không nên chỉ là “cho service-X dùng key-Y”. Cần mô tả tường minh:

~~~text
requesterIdentity = Service/workload đã được xác thực
keyFamily         = Key logical group / owner
keyId + version   = Immutable provider reference nếu thao tác với key đã có
operation         = WRAP | UNWRAP | ENCRYPT | DECRYPT | SIGN | ...
purpose           = BUSINESS_SIGNATURE | CUSTOMER_DATA | WEBHOOK_MAC | ...
tenant            = Tenant được xác thực
environment       = production | staging | ...
keyState          = ACTIVE | ... theo provider policy
deliveryMode      = HANDLE | WRAPPED_KEY | EPHEMERAL_SECRET | PUBLIC_CERT
ttl/cryptoperiod  = Thời hạn quyền và vật liệu khác nhau
approvals         = Key owner / Security approver nếu rủi ro cao
audit             = Request ID, policy version, outcome và evidence
~~~

### 5.1. Phân quyền operations và ranh giới service

| Service/vai trò | Các quyền hợp lý theo nhu cầu | Những quyền cần tránh mặc định |
|---|---|---|
| **Billing signing service** | Sign bằng signing key được chỉ định sau business approval | ExportPrivateKey, DecryptAll, DestroyKey, ManagePolicy |
| **Customer Data writer** | GenerateDataKey/Wrap và Encrypt payload record được phép | Unwrap tất cả EDK lịch sử, ExportKEK |
| **Customer Data reader** | Unwrap/Decrypt DEK theo tenant/record được phép | Unwrap cross-tenant, CreateGrant |
| **Webhook service** | Lấy/ dùng HMAC secret đúng đối tác và version | Secret của đối tác khác, HMAC root toàn tổ chức |
| **mTLS workload** | Enroll/renew certificate cho đúng identity | Issue certificate cho subject tùy ý |
| **Security administrator** | Review/change policy, grants, suspend/rotate theo quyền | Mặc nhiên có Sign/Decrypt/raw key material |
| **Independent auditor** | Read inventory, policy revision, audit events | Export, Sign, Decrypt, sửa/xóa audit |

**Quản lý khóa và sử dụng khóa cần tách quyền.** Một Security administrator có khả năng thay grants nên có approval, change control và monitoring; nếu người đó tự cấp quyền Decrypt/Sign cho chính mình không bị phát hiện, ranh giới KMS/HSM có thể bị lạm dụng dù private key non-exportable.

### 5.2. Pseudo-policy minh họa

~~~yaml
policyId: service-key-provisioning-v1
environment: production
defaultDecision: DENY
keyFamilies:
  billing-signing:
    owner: BILLING_SECURITY_OWNER
    algorithm: Ed25519
    purpose: BILLING_SIGNATURE
    storage: APPROVED_HSM
    rawPrivateKeyExport: DENY
    allowedConsumers: [billing-service]
    allowedActions: [SIGN]
    delivery: KEY_HANDLE
  customer-data:
    owner: CUSTOMER_DATA_OWNER
    algorithm: AES-256-GCM
    purpose: ENVELOPE_ENCRYPTION
    kekStorage: APPROVED_KMS
    allowedConsumers: [customer-writer, customer-reader]
    grants:
      customer-writer: [GENERATE_DATA_KEY, WRAP]
      customer-reader: [UNWRAP]
    tenantBinding: REQUIRED
    delivery: WRAPPED_DEK_AND_APPROVED_EPHEMERAL_USE
approvals:
  changeKeyPolicy: INDEPENDENT_SECURITY_REVIEW
  exportRawKEK: DENY
  breakGlass: APPROVED_LIMITED_TTL_AUDITED
audit:
  logKeyIdVersion: true
  logPlaintextKey: false
~~~

Đây là **pseudo-policy cho mục đích học tập**, không phải cấu hình có thể nạp trực tiếp vào AWS KMS, Google Cloud KMS, Azure Key Vault hoặc PKCS#11. Các thuộc tính như DELIVERY, tenantBinding hay WRAP phải được **ánh xạ đúng với API và key policy thực tế**. Cần xác minh liệu provider hỗ trợ GenerateDataKey, Sign, non-exportability, encryption context hoặc conditional grant cụ thể hay không.

### 5.3. Ranh giới approve và execute

~~~mermaid
flowchart TD
    A["Service owner đề nghị: purpose, tenant, key, action"] --> B["Key owner xác nhận nhu cầu nghiệp vụ"]
    B --> C["Security review: policy, SoD, exportability"]
    C --> D{"Được phê duyệt?"}
    D -->|"Không"| DENY["Deny + audit reason"]
    D -->|"Có"| E["Provision qua automation/approved operator"]
    E --> F["KMS/HSM/PKI/secrets manager enforcement"]
    F --> G["Positive và negative tests"]
    G --> H["Key inventory + audit evidence"]
~~~

Với rủi ro cao như **ExportKey, ChangeKeyPolicy, DestroyKey hoặc cấp quyền Unwrap hàng loạt**, nên có **separation of duties/dual control** theo chính sách. Quyền **khẩn cấp** có thể có quy trình nhanh hơn nhưng cần scope, TTL, approval hoặc hậu kiểm được định nghĩa trước; không dùng shared root key làm lối tắt khi gặp sự cố.

## 6. Runbook provisioning cho service mới

Một quy trình production tốt phải tách **phê duyệt trên control plane** khỏi **phép toán mật mã trên data plane**. Trình tự dưới đây áp dụng cho workload mới hoặc workload được cấp thêm purpose; với key/certificate đã tồn tại, một số bước là kiểm tra và ánh xạ thay vì tạo mới.

### 6.1. Giai đoạn 1: Xác minh nhu cầu và owner

1. **Service owner** mở request có service ID, application, môi trường, tenant, owner/on-call và nhu cầu Encrypt/Decrypt/Sign/MAC.
2. **Key owner** xác nhận **đối tượng dữ liệu, mục đích, mức độ nhạy cảm, phạm vi record và thời hạn**; không chấp thuận một quyền Decrypt toàn bộ production chỉ vì team cần một API.
3. **Security administrator** chọn key class, thuật toán, provider, nơi lưu material, exportability, quyền tối thiểu và kiểm soát rủi ro.
4. **IAM/Platform team** xác minh workload identity đã được cấp từ nguồn tin cậy, không dùng tài khoản cá nhân của người triển khai.
5. **Key custodian/KMS operator** kiểm tra HSM partition/KMS resource, phân tách environments, backup/DR và key lifecycle.

**Nếu service chưa có identity đáng tin, chưa nên phân phối secret**. Việc gửi một master API key qua chat để service “tự đăng ký” không tạo được xác thực nguồn gốc workload; nó chuyển rủi ro sang người biết bootstrap secret.

### 6.2. Giai đoạn 2: Tạo hoặc lựa chọn key material

- Với **private signing key**: tạo khóa non-exportable trong HSM/KMS được phê duyệt khi thích hợp; lưu key handle/ID, thuật toán, public verification key và owner.
- Với **KEK**: tạo key family theo tenant/environment/purpose; ràng buộc key policy và key version, không chuyển raw KEK tới mọi service.
- Với **DEK**: sinh per-record/object/batch theo security design, bọc bằng KEK nếu lưu lâu; không lưu plaintext DEK cùng ciphertext.
- Với **HMAC secret**: tạo từ CSPRNG được phê duyệt hoặc qua provider key generation; lưu trong secrets manager/KMS và cấp cho đúng service/đối tác.
- Với **mTLS credential**: tạo key pair tại endpoint/HSM/agent nếu khả thi, gửi CSR để CA ký sau khi xác minh subject/SAN; nhận certificate chain qua kênh tin cậy.
- Với **public verification key/JWKS**: công bố qua endpoint hoặc trust store được xác thực, có key ID/version và chính sách chấp nhận khóa cũ.

Không coi **key identifier khó đoán** là yếu tố bí mật. Key ID có thể xuất hiện trong ciphertext envelope, token headers hoặc audit; **quyền IAM và policy** mới quyết định khả năng sử dụng key.

### 6.3. Giai đoạn 3: Cấp policy và phương tiện sử dụng

~~~mermaid
sequenceDiagram
    participant O as Service owner
    participant S as Security / Key owner
    participant P as Provisioning automation
    participant K as KMS/HSM/PKI
    participant W as Service workload
    participant A as Audit/Inventory
    O->>S: Request(key purpose, principal, tenant, environment, TTL)
    S->>S: Kiểm tra ownership, SoD, risk, approver
    S->>P: Approved request + policy revision
    P->>K: Create/resolve key, set usage + grants
    K-->>P: Key handle/version, policy outcome
    P->>A: Approval, actor, keyRef, grants, timestamp
    P-->>W: Key reference và discovery metadata
    W->>K: Authenticated Sign/Wrap/Unwrap request
    K-->>W: Authorized crypto result
    W->>A: Operation metadata; không log raw key
~~~

**Provisioning automation** là principal kỹ thuật đặc quyền; nó cũng cần **least privilege, approval validation, idempotency, audit, credential rotation và giới hạn khả năng cấp quyền cho chính mình**. Không chấp nhận tình huống hệ thống phê duyệt trả lời “ALLOW” nhưng provider vẫn cho phép caller bypass bằng trực tiếp gọi API.

### 6.4. Giai đoạn 4: Kiểm thử trước khi kích hoạt chính thức

| Kiểm tra | Kết quả mong đợi |
|---|---|
| Đúng workload identity, đúng tenant, đúng action | **ALLOW** theo policy |
| Workload khác cùng cluster nhưng khác service identity | **DENY** nếu chưa được cấp quyền |
| Service dùng key của tenant khác | **DENY**, kể cả biết key ID |
| Billing Service thử ExportPrivateKey hoặc Decrypt | **DENY** |
| Customer writer thử Unwrap toàn bộ lịch sử | **DENY** nếu chỉ được cấp Write/Wrap |
| Security admin thử Sign hóa đơn | **DENY mặc định** |
| Service gọi với key state Suspended/Disabled | **DENY** theo contract của provider |
| Token sai audience/issuer/expiry | **DENY** trước khi tới KMS |
| Lỗi key ID/version hoặc AAD | **DENY/crypto authentication failure**; không trả secret |
| Service restart/redeploy/scale | Có thể xin lại quyền hợp lệ bằng workload identity, không cần hardcode |

**Một positive test thành công không đủ chứng minh least privilege.** Phải có **negative tests** trên đúng key operations, direct API path, tenant boundaries và trạng thái key.

### 6.5. Giai đoạn 5: Hoàn tất và giám sát

Đăng ký **key inventory**: owner, service, tenant, purpose, algorithm, key reference/version, provider, allowed operations, lifecycle, expiration/cryptoperiod, rotation owner, dependencies, approvals và audit references. Theo dõi cấp quyền trong suốt vòng đời, không chỉ tại ngày onboarding.

Lệnh provisioning có thể thành công ở control plane nhưng policy chưa đồng bộ tới mọi region/partition/session. Ghi nhận **requestedAt, appliedAt, effectiveAt** khi provider hỗ trợ; định nghĩa quy trình đối soát và cửa sổ propagation. Không đổi ticket sang “hoàn tất” chỉ dựa trên mã HTTP 200.

## 7. Cấp DEK cho service thực hiện envelope encryption

### 7.1. Luồng ghi dữ liệu

Giả sử **Customer Data Writer** dùng AES-GCM với DEK cho từng invoice, còn KEK được quản lý tại KMS.

~~~mermaid
sequenceDiagram
    participant C as Business caller
    participant W as Customer Writer
    participant IAM as Identity/Policy
    participant KMS as KMS giữ KEK
    participant DB as Encrypted database
    C->>W: Create invoice thuộc tenant được ủy quyền
    W->>IAM: Kiểm tra owner, tenant, purpose
    IAM-->>W: Resource authorization passed
    W->>KMS: GenerateDataKey / approved key-protection request
    KMS-->>W: Plaintext DEK tạm + wrapped DEK
    W->>W: AES-GCM Encrypt với DEK, nonce mới, content AAD
    W->>DB: Ciphertext, tag, nonce, EDK, KEK keyRef/version
    W->>W: Cleanup DEK buffer best effort
~~~

Một số KMS có **GenerateDataKey** tạo plaintext DEK và encrypted blob; một số chỉ có **Wrap/Unwrap** hoặc làm crypto trong ranh giới provider. Đây là **pattern khái niệm**, không phải contract chung của mọi dịch vụ. Chọn đúng API và ranh giới raw material thực sự.

Database có thể lưu **EDK (encrypted DEK)** cạnh ciphertext, nhưng **không lưu plaintext DEK**. Nếu service dùng local AES-GCM, DEK tạm hiện diện trong RAM. Cần giới hạn **TTL, số bản sao, cache, heap/core dump, log redaction và quyền truy cập process**.

### 7.2. Luồng đọc dữ liệu

~~~text
Authenticated principal yêu cầu record-123
     |
     v
Ứng dụng kiểm tra quyền đối với record + tenant
     |
     v
Load envelope có content ciphertext, nonce, EDK, keyRef/version
     |
     v
Validate schema + immutable key reference + key purpose
     |
     v
KMS Unwrap/Decrypt EDK theo IAM/context đã xác thực
     |
     v
DEK plaintext tồn tại tạm thời trong crypto boundary
     |
     v
AES-GCM Verify tag / Decrypt với content AAD
     |
     v
Trả dữ liệu được phép, cleanup raw DEK best effort
~~~

**AES-GCM AAD không thay thế kiểm tra quyền.** Nếu service được cấp quyền KMS Unwrap toàn tenant nhưng endpoint tin tenant ID do caller tự gửi, service có thể trở thành **confused deputy**. Tenant phải được ràng buộc với danh tính được xác thực và quyền đọc record.

### 7.3. Phiên bản khóa, alias và AAD

Một envelope tốt cần lưu **key ID/version thực sự dùng**, không chỉ alias “current-key” có thể đổi mục tiêu khi rotate. Cần phân biệt:

| Metadata | Vai trò |
|---|---|
| **Content DEK ID/version** | Định danh vật liệu mã hóa payload |
| **KEK key ID/version** | Chọn đúng khóa Unwrap EDK lịch sử |
| **Content algorithm/nonce/tag** | Giải mã và xác thực payload |
| **Wrap algorithm/params** | Unwrap EDK đúng cơ chế |
| **Tenant/record/content AAD** | Binding nội dung với context |
| **Wrapping context** | Binding EDK với recipient/KEK và context riêng |
| **Envelope revision** | Ngăn migration ghi đè dữ liệu mới; hỗ trợ chống rollback khi thiết kế yêu cầu |

Nếu **KEK version nằm trong content AAD**, việc chỉ rewrap EDK dưới KEK mới có thể làm content tag không khớp. Thiết kế nên xác định ranh giới **content AAD bất biến** và **wrapping context có thể đổi khi rewrap**, đồng thời bảo vệ integrity phù hợp cho cả hai.

### 7.4. Nonce và quy mô nhiều instance

AES-GCM yêu cầu nonce **không bị tái sử dụng với cùng một key** khi Encrypt. Có hai phạm vi:

1. **Content nonce:** theo từng DEK, trên tất cả operation/replica dùng DEK đó.
2. **Wrapping nonce** nếu dùng AES-GCM để bảo vệ DEK: theo từng KEK, trên toàn bộ service/instance/region cùng Wrap.

Một nonce 96 bit được sinh ngẫu nhiên bằng CSPRNG **không bảo đảm xác suất trùng bằng 0**; cần giới hạn số lượt dùng theo thiết kế. Nếu dùng counter/structured nonce, phải tránh counter reset sau restart, snapshot rollback hoặc hai instance cùng prefix. Với **AES-KW/AES-KWP**, tuân thủ tham số và mode riêng, không gán mô hình nonce của AES-GCM sang key-wrap algorithm khác.

### 7.5. Quyền dùng KEK không đồng nghĩa quyền biết KEK

Một workload có thể nhận **KMS grant Unwrap** nhưng không bao giờ được export raw KEK. Tương tự, **Billing Service** có thể có quyền Sign mà không biết private signing key. Điều này giới hạn vùng chứa raw material nhưng **không ngăn lạm dụng phép toán** nếu workload bị chiếm; cần IAM, rate controls, audit và authorization theo nghiệp vụ.

## 8. Provisioning private key và certificate cho mTLS service

Mô hình này có một điểm khác biệt quan trọng: **certificate thường là public**, nhưng **private key tương ứng tuyệt đối không nên được coi là dữ liệu public**.

### 8.1. Một quy trình certificate enrollment

~~~mermaid
sequenceDiagram
    participant W as Service instance / agent
    participant ID as Workload identity issuer
    participant CA as Approved CA
    participant V as Gateway / peer
    W->>W: Sinh keypair tại boundary được duyệt
    W->>ID: Xin identity assertion có hạn
    ID-->>W: Verified workload claim
    W->>CA: CSR + proof of possession + identity assertion
    CA->>CA: Validate subject/SAN, policy, lifetime
    CA-->>W: Certificate chain, expiry, serial
    W->>V: TLS/mTLS handshake với certificate + proof
    V->>V: Validate chain, SAN/identity, validity, revocation policy
    V-->>W: Authenticated channel
~~~

CSR không làm CA tự biết requester có quyền chọn bất kỳ SAN nào. **CA/enrollment gateway phải kiểm tra subject/SAN theo workload identity đáng tin**. Một CSR được ký bằng private key chứng minh người yêu cầu đang sở hữu hoặc điều khiển private key tương ứng, **không chứng minh tự động danh tính nghiệp vụ**.

### 8.2. Private key nên được tạo ở đâu?

Các cách hợp lý tùy mức rủi ro:

- Sinh keypair trong **workload/agent** rồi bảo vệ private key bằng filesystem ACL, runtime controls và secret lifecycle.
- Sinh/giữ private key trong **HSM/TPM/PKCS#11 provider** khi workload có thể dùng key handle.
- Với hệ thống legacy buộc phải phân phối **PKCS#12/PEM**, bảo vệ file và key-protection password riêng, giới hạn quyền nhận, TTL/rotation và không đưa vào image/Git.

Một **PKCS#12 đã được mã hóa** vẫn cần bảo vệ **password cùng các bản sao của file**. Nếu cả file và password được đặt cạnh nhau với cùng quyền đọc, host compromise có thể mở cả hai. Không coi base64 của PEM là mã hóa.

### 8.3. Kiểm tra certificate đúng trust domain

Không chỉ xem certificate “được một CA ký”. Peer phải kiểm tra **chain, validity, key usage/EKU, SAN/expected workload identity, issuer/trust domain và revocation policy**. Certificate bị lộ không tương đương private key bị lộ; nếu private key bị lộ, cần **revoke/rotate cert**, xử lý session và xác minh nơi verifier lấy trạng thái mới.

**mTLS bảo vệ và xác thực kênh giữa hai đầu**, không tự bảo đảm rằng một endpoint được phép truy cập mọi record, mọi KEK hoặc mọi API. Authorization sau xác thực vẫn phải dựa trên identity, purpose và resource.

## 9. Provisioning HMAC secret và khóa dùng chung cho đối tác

Webhook sender và receiver thường dùng **HMAC-SHA-256** để xác thực payload:

~~~text
Sender:
    tag = HMAC(keyVersion.v3, canonicalMessage)

Receiver:
    lookup keyVersion.v3 từ secret store
    verify tag theo constant-time comparison
    kiểm tra timestamp/nonce/id để chống replay
~~~

Khi cấp key cho hai bên, hãy xác định **ai được biết secret, nơi lưu và đường thay version**, vì mọi bên biết HMAC secret đều có thể tạo một tag hợp lệ. Nếu nhiều consumer cùng dùng một secret, compromise của một consumer có thể ảnh hưởng toàn bộ nhóm.

### 9.1. Các bước cấp HMAC secret

1. Xác thực **đối tác/consumer identity** và approve mục đích webhook.
2. Tạo secret có entropy đủ qua CSPRNG hoặc secrets manager/KMS.
3. Tách secret theo **environment, tenant/partner và purpose**.
4. Truyền qua **kênh được xác thực và mã hóa** hoặc cơ chế provider secret delivery; nếu có out-of-band enrollment, phải xác thực recipient.
5. Bên nhận lưu secret trong secret store/KMS, không source code hoặc log.
6. Gắn **key ID/version**, thời hạn chấp nhận, timestamp/nonce cho anti-replay và quy trình rotate.
7. Khi rotate, cho phép overlap cũ/mới **có giới hạn** nếu giao thức yêu cầu, rồi từ chối secret cũ; không mặc định overlap vô hạn.
8. Audit lần cấp/đọc/rotate/revoke, không log chính secret.

**HMAC không phải chữ ký số bất đối xứng.** Khi hai bên biết cùng key, bên nhận cũng có thể tự tạo một MAC; không dùng HMAC làm bằng chứng non-repudiation giữa các bên độc lập.

### 9.2. Secrets manager và runtime injection

Secret manager có thể trả secret qua API, sidecar/agent, tệp runtime được bảo vệ hoặc cơ chế mount khác. **Không có hình thức nào tự bảo đảm tránh raw secret trong RAM của ứng dụng**. Nếu app dùng HMAC local, nó phải có secret hoặc key handle đúng provider.

| Cách nhận secret | Điểm mạnh | Bề mặt rủi ro |
|---|---|---|
| **Runtime API với workload identity** | Không bake static secret, audit mỗi lần cấp theo khả năng provider | Token bị chiếm, process memory, cache, KMS/vault outage |
| **Protected runtime file/volume** | Dễ cho thư viện legacy, có thể atomic update | ACL, file snapshot, process đọc nhầm, stale secret |
| **Environment variable** | Dễ cấu hình | Process diagnostics, crash reports, subprocess, config dumps |
| **CI/CD injection lúc build** | Dễ với deployment cũ | Secret có thể nằm trong artifact/image/build logs |
| **Hardcode trong source/image** | Không có lợi ích security thực sự | Clone, fork, CI logs, image registries, history |

Ưu tiên **cấp tại runtime** và quản lý rotation thay vì đưa bí mật từ build pipeline vào image. Khi một cơ chế buộc dùng environment variable hoặc file, cần threat model, kiểm soát host/process, log redaction và **không xem đây là bảo mật tương đương HSM**.

## 10. Kênh phân phối và xác thực người nhận

**Transport security** và **key protection** giải quyết các lớp khác nhau:

| Kiểm soát | Bảo vệ điều gì? | Không bảo đảm |
|---|---|---|
| **TLS** | Bí mật và toàn vẹn dữ liệu truyền tới endpoint đã xác thực | Endpoint thật có được phép sử dụng raw key hay không |
| **mTLS** | Thêm xác thực client/workload qua certificate | Client có quyền Encrypt/Sign/Unwrap mọi key |
| **KMS key policy/IAM** | Kiểm soát operations theo principal/key/context | Raw DEK đã xuất không bị copy ngoài KMS |
| **Key wrapping/envelope** | Bảo vệ DEK ở storage/bên nhận theo KEK | Caller được phép đọc record hoặc plaintext đã xuất |
| **PKI/trust store** | Tin cậy public key/certificate theo identity | Private key của recipient không thể bị lộ |
| **Audit/monitoring** | Phát hiện, truy vết và review cấp phát/sử dụng | Tự ngăn mọi hành vi sai trong thời gian thực |

Không nên **gửi raw key qua kênh TLS tới bất kỳ endpoint nào được nhập bằng URL của caller**. TLS bảo vệ kênh tới **endpoint đã kết nối**, nhưng nếu địa chỉ hoặc public key là của attacker thì bí mật vẫn đến sai người. Cần **service discovery, identity allowlist, certificate validation, recipient authorization và trust chain**.

### 10.1. Không dùng một secret dài hạn làm giải pháp cho mọi lỗi bootstrap

Một ví dụ sai:

~~~text
Tất cả workload có biến môi trường BOOTSTRAP_MASTER_TOKEN.
Workload gửi token tới crypto gateway.
Gateway trả bất kỳ KEK/DEK/private key nào được yêu cầu.
~~~

Một lần lộ token làm mất ranh giới giữa services. Hệ thống đúng hơn dùng **workload identity riêng**, role theo key purpose, **audience-bound short-lived tokens**, giới hạn tenant/resource và default-deny. Nếu service cần được enroll lần đầu, phải có cách **xác minh danh tính nguồn triển khai** hoặc approval của owner, không tự chấp nhận metadata tùy ý.

### 10.2. Public key không cần giữ bí mật nhưng vẫn phải xác thực

Với JWT/JWKS hoặc RSA recipient encryption, public key có thể công bố, nhưng phải giới hạn **issuer/recipient và nguồn phân phối**. Đặc biệt, không nên để untrusted JWT header tự quyết định URL tải key hoặc thuật toán chấp nhận; cần **algorithm allowlist, trust anchor, key ID/issuer binding**.

### 10.3. Multi-region/multi-cluster provisioning

Provisioning cho hai region có thể cần một **logical key family** nhưng KMS resource IDs, rotation semantics và backup/replica khác nhau. Không giả định hai key cùng alias đều có **cùng key bytes**. Metadata cần nêu provider scope, region/partition và version thực; dữ liệu mã hóa ở region A phải có **đường decrypt được phê duyệt** ở region B, được thử bằng bản ghi lịch sử.

Nếu cần chuyển key material qua vùng, dùng **provider-supported replication, secure import/wrapping hoặc DR workflow**, không export raw KEK qua tập tin tạm và chat. Kiểm soát cũng cần xét data residency và compliance áp dụng.

## 11. Java 17: Kiểm tra chính sách trước khi provision quyền dùng khóa

Ví dụ sau tập trung vào **quyết định provisioning** thay vì tạo raw private key. Nó mô hình hóa bốn hình thức cấp phát:

- **KEY_HANDLE**: Billing Service chỉ được gọi Sign bằng private key mà provider quản lý.
- **WRAPPED_DEK**: Customer Data Service được Wrap hoặc Unwrap theo nhu cầu riêng; KEK không xuất raw material.
- **RUNTIME_SECRET**: Webhook Service được dùng secret HMAC trong boundary được phê duyệt, có key version.
- **PUBLIC_VERIFY_KEY**: Verifier chỉ nhận public verification key đáng tin, không nhận private key.

Một **ProvisioningPolicy** kiểm tra workload identity đã được xác thực, issuer/audience/expiry *giả lập*, environment, tenant, key state, purpose/operation, allowed consumers và delivery mode. Một **GrantApprovalPolicy** kiểm tra request cấp quyền rủi ro cao có **ticket và người duyệt độc lập**, tránh tự phê duyệt.

**Giới hạn:** Đây là demo **metadata/policy**, không phải IdP, KMS, HSM hoặc CA thực. Các boolean về xác thực được tạo trực tiếp trong chương trình chỉ để kiểm tra logic; **không bao giờ nhận chúng từ HTTP body làm bằng chứng an ninh**. Một quyết định ALLOW ở đây **không tự tạo IAM grant**, không chứng minh raw key non-exportable và không ngăn direct API bypass nếu provider policy cho phép.

~~~java
import java.util.Set;

public final class ServiceKeyProvisioningDemo {
    enum Delivery {
        KEY_HANDLE, WRAPPED_DEK,
        RUNTIME_SECRET, PUBLIC_VERIFY_KEY
    }

    enum KeyState {
        ACTIVE, DECRYPT_ONLY, SUSPENDED, DESTROYED
    }

    enum Operation {
        SIGN, WRAP, UNWRAP, GENERATE_MAC, VERIFY,
        EXPORT_PRIVATE_KEY, CHANGE_POLICY, DESTROY_KEY
    }

    enum Purpose {
        BILLING_SIGNATURE, ENVELOPE_DEK_PROTECTION,
        WEBHOOK_MAC, PUBLIC_SIGNATURE_VERIFY
    }

    record WorkloadIdentity(
            String serviceId,
            String tenantId,
            String environment,
            boolean issuerTrusted,
            boolean audienceMatched,
            boolean credentialValid) {
        WorkloadIdentity {
            if (serviceId == null || serviceId.isBlank()
                    || tenantId == null || tenantId.isBlank()
                    || environment == null || environment.isBlank()) {
                throw new IllegalArgumentException(
                        "Invalid workload identity metadata");
            }
        }
    }

    record KeyPolicy(
            String keyId,
            int version,
            String tenantId,
            String environment,
            Purpose purpose,
            Delivery delivery,
            KeyState state,
            Set<String> allowedServices,
            Set<Operation> allowedOperations,
            boolean rawPrivateExportAllowed) {
        KeyPolicy {
            if (keyId == null || keyId.isBlank() || version < 1
                    || tenantId == null || tenantId.isBlank()
                    || environment == null || environment.isBlank()
                    || purpose == null || delivery == null
                    || state == null || allowedServices == null
                    || allowedOperations == null) {
                throw new IllegalArgumentException(
                        "Invalid key policy");
            }
            allowedServices = Set.copyOf(allowedServices);
            allowedOperations = Set.copyOf(allowedOperations);
        }
    }

    record ProvisionRequest(
            WorkloadIdentity caller,
            KeyPolicy key,
            Operation operation,
            Delivery requestedDelivery,
            boolean businessResourceAuthorized) {}

    record Decision(boolean allowed, String reason) {}

    static boolean purposeMatches(
            Purpose purpose, Operation operation, Delivery delivery) {
        return switch (purpose) {
            case BILLING_SIGNATURE ->
                    delivery == Delivery.KEY_HANDLE
                    && operation == Operation.SIGN;
            case ENVELOPE_DEK_PROTECTION ->
                    delivery == Delivery.WRAPPED_DEK
                    && (operation == Operation.WRAP
                        || operation == Operation.UNWRAP);
            case WEBHOOK_MAC ->
                    delivery == Delivery.RUNTIME_SECRET
                    && operation == Operation.GENERATE_MAC;
            case PUBLIC_SIGNATURE_VERIFY ->
                    delivery == Delivery.PUBLIC_VERIFY_KEY
                    && operation == Operation.VERIFY;
        };
    }

    static Decision authorizeProvisioning(ProvisionRequest request) {
        if (request == null || request.caller() == null
                || request.key() == null || request.operation() == null
                || request.requestedDelivery() == null) {
            return new Decision(false, "INVALID_REQUEST");
        }

        WorkloadIdentity caller = request.caller();
        KeyPolicy key = request.key();

        // Những cờ này trong demo phải được thay bằng IdP validation
        // và IAM/resource authorization thực tế khi triển khai.
        if (!caller.issuerTrusted()
                || !caller.audienceMatched()
                || !caller.credentialValid()) {
            return new Decision(false, "WORKLOAD_IDENTITY_DENIED");
        }
        if (!caller.tenantId().equals(key.tenantId())
                || !caller.environment().equals(key.environment())
                || !request.businessResourceAuthorized()) {
            return new Decision(false, "SCOPE_OR_RESOURCE_DENIED");
        }
        if (!key.allowedServices().contains(caller.serviceId())) {
            return new Decision(false, "SERVICE_NOT_ALLOWED");
        }
        if (key.state() == KeyState.SUSPENDED
                || key.state() == KeyState.DESTROYED) {
            return new Decision(false, "KEY_NOT_USABLE");
        }
        if (key.state() == KeyState.DECRYPT_ONLY
                && request.operation() != Operation.UNWRAP
                && request.operation() != Operation.VERIFY) {
            return new Decision(false, "HISTORICAL_USE_ONLY");
        }
        if (!key.allowedOperations().contains(request.operation())) {
            return new Decision(false, "OPERATION_NOT_GRANTED");
        }
        if (key.delivery() != request.requestedDelivery()
                || !purposeMatches(
                        key.purpose(), request.operation(),
                        request.requestedDelivery())) {
            return new Decision(false, "KEY_PURPOSE_OR_DELIVERY_MISMATCH");
        }
        if (key.purpose() == Purpose.BILLING_SIGNATURE
                && key.rawPrivateExportAllowed()) {
            return new Decision(false, "PRIVATE_EXPORT_POLICY_DENIED");
        }
        // Kiểm tra này không phải lệnh KMS/PKI và không có raw key.
        return new Decision(true, "PROVISIONING_POLICY_ALLOWED");
    }

    record GrantChange(
            String requesterId,
            String approverId,
            String ticketId,
            boolean ownerApproved,
            boolean securityApproved) {}

    static Decision reviewHighRiskGrant(GrantChange change) {
        if (change == null
                || change.requesterId() == null
                || change.approverId() == null
                || change.ticketId() == null
                || change.ticketId().isBlank()) {
            return new Decision(false, "APPROVAL_EVIDENCE_MISSING");
        }
        if (change.requesterId().equals(change.approverId())) {
            return new Decision(false, "SELF_APPROVAL_DENIED");
        }
        if (!change.ownerApproved() || !change.securityApproved()) {
            return new Decision(false, "INDEPENDENT_REVIEW_REQUIRED");
        }
        return new Decision(true, "READY_FOR_APPROVED_AUTOMATION");
    }

    static void show(String label, Decision decision) {
        System.out.println(label + ": " + decision.allowed()
                + " / " + decision.reason());
    }

    public static void main(String[] args) {
        WorkloadIdentity billing = new WorkloadIdentity(
                "billing-service", "tenant-42", "production",
                true, true, true);

        WorkloadIdentity analytics = new WorkloadIdentity(
                "analytics-service", "tenant-42", "production",
                true, true, true);

        WorkloadIdentity otherTenant = new WorkloadIdentity(
                "billing-service", "tenant-OTHER", "production",
                true, true, true);

        WorkloadIdentity badAudience = new WorkloadIdentity(
                "billing-service", "tenant-42", "production",
                true, false, true);

        KeyPolicy signing = new KeyPolicy(
                "billing-sign", 3, "tenant-42", "production",
                Purpose.BILLING_SIGNATURE,
                Delivery.KEY_HANDLE, KeyState.ACTIVE,
                Set.of("billing-service"),
                Set.of(Operation.SIGN), false);

        show("Billing Sign via handle",
                authorizeProvisioning(new ProvisionRequest(
                        billing, signing, Operation.SIGN,
                        Delivery.KEY_HANDLE, true)));

        show("Analytics uses Billing key",
                authorizeProvisioning(new ProvisionRequest(
                        analytics, signing, Operation.SIGN,
                        Delivery.KEY_HANDLE, true)));

        show("Cross-tenant request",
                authorizeProvisioning(new ProvisionRequest(
                        otherTenant, signing, Operation.SIGN,
                        Delivery.KEY_HANDLE, true)));

        show("Wrong token audience",
                authorizeProvisioning(new ProvisionRequest(
                        badAudience, signing, Operation.SIGN,
                        Delivery.KEY_HANDLE, true)));

        show("Raw-key delivery instead of handle",
                authorizeProvisioning(new ProvisionRequest(
                        billing, signing, Operation.SIGN,
                        Delivery.RUNTIME_SECRET, true)));

        KeyPolicy suspended = new KeyPolicy(
                signing.keyId(), signing.version(),
                signing.tenantId(), signing.environment(),
                signing.purpose(), signing.delivery(),
                KeyState.SUSPENDED, signing.allowedServices(),
                signing.allowedOperations(), false);
        show("Suspended signing key",
                authorizeProvisioning(new ProvisionRequest(
                        billing, suspended, Operation.SIGN,
                        Delivery.KEY_HANDLE, true)));

        WorkloadIdentity customerReader = new WorkloadIdentity(
                "customer-reader", "tenant-42", "production",
                true, true, true);
        KeyPolicy kek = new KeyPolicy(
                "tenant-42-kek", 4, "tenant-42", "production",
                Purpose.ENVELOPE_DEK_PROTECTION,
                Delivery.WRAPPED_DEK, KeyState.ACTIVE,
                Set.of("customer-reader"),
                Set.of(Operation.UNWRAP), false);

        show("Customer reader Unwrap",
                authorizeProvisioning(new ProvisionRequest(
                        customerReader, kek, Operation.UNWRAP,
                        Delivery.WRAPPED_DEK, true)));
        show("Customer reader Wrap denied",
                authorizeProvisioning(new ProvisionRequest(
                        customerReader, kek, Operation.WRAP,
                        Delivery.WRAPPED_DEK, true)));

        show("Admin self-approval",
                reviewHighRiskGrant(new GrantChange(
                        "security-admin", "security-admin",
                        "SEC-123", true, true)));
        show("Independent approval",
                reviewHighRiskGrant(new GrantChange(
                        "requester-1", "owner-2",
                        "SEC-123", true, true)));
    }
}
~~~

Lưu thành **ServiceKeyProvisioningDemo.java** và chạy với **JDK 17+**:

~~~bash
javac ServiceKeyProvisioningDemo.java
java ServiceKeyProvisioningDemo
~~~

Kết quả dự kiến:

~~~text
Billing Sign via handle: true / PROVISIONING_POLICY_ALLOWED
Analytics uses Billing key: false / SERVICE_NOT_ALLOWED
Cross-tenant request: false / SCOPE_OR_RESOURCE_DENIED
Wrong token audience: false / WORKLOAD_IDENTITY_DENIED
Raw-key delivery instead of handle: false / KEY_PURPOSE_OR_DELIVERY_MISMATCH
Suspended signing key: false / KEY_NOT_USABLE
Customer reader Unwrap: true / PROVISIONING_POLICY_ALLOWED
Customer reader Wrap denied: false / OPERATION_NOT_GRANTED
Admin self-approval: false / SELF_APPROVAL_DENIED
Independent approval: true / READY_FOR_APPROVED_AUTOMATION
~~~

### 11.1. Vì sao policy kiểm tra cả operation lẫn delivery?

Một **private signing key** có thể được phép dùng với **SIGN** nhưng **không được phép xuất raw material**. Chỉ kiểm tra operation mà không kiểm tra hình thức provisioning có thể khiến một tool “cấp khóa” xuất private key PEM trong khi nghiệp vụ chỉ cần chữ ký.

Ngược lại, **HMAC secret runtime** có thể cần được cấp dưới dạng raw bytes cho một crypto provider local; khi đó phải kiểm soát **nơi chứa, bản sao, TTL, caller và rotation**. Việc raw material xuất hiện trong JVM **không đồng nghĩa root/KEK cũng được phép export**.

### 11.2. Giới hạn mô hình và cách sửa khi làm production

1. **Identity chưa được xác thực thật.** Các cờ trusted/audience/valid do caller khởi tạo; production phải kiểm tra token/certificate từ IdP với trust roots, thời gian, audience và revocation semantics đúng.
2. **Không có cryptographic operation.** Code không gọi Sign, Unwrap hoặc GenerateDataKey; nó chỉ trả quyết định metadata.
3. **Không có IAM thực.** Provider KMS/HSM/key gateway phải có policy **chặn trực tiếp**, kể cả khi service gọi bỏ qua application UI.
4. **Approval được giả lập.** Hai chuỗi requester/approver khác nhau không chứng minh hai người độc lập; cần trusted identities, signed approvals, ticket workflow, SoD và audit.
5. **Không có key generation/algorithm/size validation chi tiết.** Production cần allowlist algorithm, provider, key type/curve, entropy và cryptoperiod.
6. **Không có key version persistence hoặc alias resolution.** Dữ liệu lịch sử phải giữ resolved provider reference để có thể Decrypt/Verify.
7. **Không có tenant resource ownership thật.** businessResourceAuthorized là một boolean giả lập; phải lấy quyết định từ resource authorization layer đáng tin.
8. **Không có credential/cache revocation.** Key state được gắn trong object, chưa kiểm tra session, effective time, stale grants hoặc DEK đã cache.
9. **Không có server-side rewrap/mTLS enrollment.** Đây là workflow riêng có nhiều kiểm soát cryptographic/provider.
10. **Không có audit bền vững.** Chỉ in quyết định, không ghi event/ticket, provider outcome hay policy revision vào nơi bảo vệ.
11. **Không có retry, concurrency hoặc rollback.** Provisioning thật phải idempotent, transaction-aware và chống stale event cấp lại quyền.
12. **Không có giới hạn tốc độ/denial-of-service** hay kiểm soát việc gọi liên tục vào KMS.
13. **Không thể suy ra non-exportable từ boolean.** Phải xác minh attributes và API capabilities ở HSM/KMS thực tế.
14. **Không có đường dữ liệu encrypted envelope.** Demo này không phát hành DEK; khác với ví dụ AES-GCM/JCA phục vụ triển khai encryption thực.

**Kết luận của demo:** Quy trình **xác định đúng service, đúng key, đúng operation và đúng hình thức cấp quyền** là điều kiện cần để đưa mật mã vào production, nhưng **không đủ** nếu không có provider enforcement, authorization nghiệp vụ và audit.

## 12. Xoay vòng và cấp lại khóa cho service

Provisioning không phải thao tác chỉ xảy ra một lần khi service ra đời. Trong vòng đời, service có thể được deploy phiên bản mới, chuyển region, đổi owner, thay algorithm, bị thu hồi quyền hoặc cần thay key material. Cần phân biệt **đổi quyền**, **đổi credential** và **đổi material**.

### 12.1. Ma trận thay đổi theo loại khóa

| Đối tượng | Khi rotate/re-provision | Điều phải giữ hoặc thay |
|---|---|---|
| **Workload access token** | TTL/renewal, rotate credentials, scale/restart | Identity, issuer/audience, grants; revoke token cũ theo contract |
| **mTLS private key/certificate** | Certificate hết hạn, key compromise hoặc thay trust | Keypair/CSR, SAN, EKU, issuer, chain, session/renewal |
| **Private signing key** | Cryptoperiod, compromise, algorithm migration | Sign mới bằng version mới; public key/JWKS/certificate cũ có thể cần Verify lịch sử |
| **HMAC secret** | Leaver/partner change, compromise, cryptoperiod | Sender/receiver chuyển version, grace period ngắn và anti-replay |
| **KEK** | Theo cryptoperiod, security review hoặc compromise | Wrap mới dưới KEK mới; rewrap EDK cũ khi cần, giữ khả năng mở archive |
| **DEK** | Scope/usage/nonce limit hoặc raw DEK lộ | Sinh DEK mới; dữ liệu cũ muốn chuyển key phải re-encrypt |
| **KDF root** | Root compromise hoặc key hierarchy migration | Đánh giá toàn bộ derived keys; thay info label không sửa root lộ |
| **KMS grant/IAM role** | Thay team, purpose, tenant, workload owner, incident | Thu hồi scope cũ, cấp scope mới, kiểm tra stale sessions |

**Rotation của KEK khác rotation của DEK.** Nếu chỉ thay KEK và **rewrap cùng DEK**, ciphertext payload có thể giữ nguyên khi content AAD/format phù hợp. Nếu **DEK đã lộ**, chỉ rewrap sẽ không ngăn người biết DEK giải mã dữ liệu đã được mã hóa bởi DEK đó.

### 12.2. Quy trình thay signing key cho service

~~~text
Signing key v3 (ACTIVE)
    |
    +-- Provision v4 với private key mới trong KMS/HSM
    +-- Kiểm tra Sign bằng v4, Verify bằng public key v4
    +-- Công bố trust/JWKS/certificate v4 qua nguồn đáng tin
    +-- Chuyển Sign operation mới sang v4
    +-- Giữ v3 Verify-only khi policy và trust cho phép
    +-- Sau thời hạn phù hợp, retire/revoke v3
~~~

Với JWT, token mang **kid** thường cho verifier chọn public key tương ứng. Nhưng kid chỉ là định danh, không phải đường dẫn bất kỳ tới một key đáng tin. Verifier phải ràng buộc **issuer, algorithm allowlist, trust store, audience và token lifetime**; không chấp nhận key từ URL do attacker tùy ý đưa vào token header.

### 12.3. Quy trình xoay HMAC shared secret

Nếu Webhook Sender và Receiver dùng cùng HMAC key:

1. Tạo secret version mới độc lập từ CSPRNG/provider.
2. Provision cho **đúng receiver** qua kênh được xác thực, không đưa vào log hoặc chat.
3. Cho receiver biết key ID/version mới, kiểm tra signature canonicalization và anti-replay.
4. Chuyển Sender sang key mới tại mốc hiệu lực.
5. Nếu cần chấp nhận song song, giới hạn **cửa sổ grace** theo policy, tránh vô hạn.
6. Từ chối key cũ, thu hồi bản copy trong secrets manager, cache và consumers khi có khả năng.
7. Audit và kiểm tra vẫn có webhook hợp lệ chạy đúng version.

**Mất mát của HMAC key có thể khiến cả sender lẫn receiver tạo được tag**; không dùng HMAC để phân xử bên nào đã ký trong tranh chấp mà cần non-repudiation.

### 12.4. Thu hồi IAM khác hủy key material

Một service không còn cần **Sign** có thể bị thu hồi grant mà private key vẫn được giữ cho nhu cầu Verify lịch sử hoặc cho service khác có quyền hợp lệ. Một workload bị compromise có thể cần **revoke token/credential và restart instance**, nhưng không được tự động hủy KEK đang mở hàng triệu EDK khi chưa có dependency plan.

~~~mermaid
flowchart TD
    I["Phát hiện service/credential/key cần thay đổi"] --> E{"Điều gì bị ảnh hưởng?"}
    E -->|"Chỉ quyền principal"| G["Revoke grants/token/session"]
    E -->|"Shared secret/raw key lộ"| M["Thay key material theo phạm vi"]
    E -->|"Key hết cryptoperiod"| R["Rotate và migration theo policy"]
    G --> V["Xác minh data-plane denial"]
    M --> D["Re-encrypt/re-sign/rewrap khi cần"]
    R --> D
    D --> T["Test continuity, backup, trust, legacy data"]
    V --> A["Audit + inventory reconciliation"]
    T --> A
~~~

**Không có một lệnh “revoke key” chung cho mọi hệ thống.** KMS có thể có disable/schedule deletion, PKI có certificate revocation, JWT có session/token revocation, HMAC có secret rotation, và local DEK cached có lifetime riêng.

### 12.5. Provisioning sau nhân sự rời tổ chức

Nếu người quản trị hoặc developer từng biết **shared HMAC secret, HSM recovery share, raw KEK hoặc private key PEM**, việc disable SSO chỉ chặn một phần năng lực truy cập. Cần:

- Thu hồi IAM/KMS grants, sessions, PAT, SSH keys và provider accounts cá nhân.
- Chuyển **service owner**, automation credentials, HSM quorum/custodian và backup responsibilities.
- Rotate **shared secrets** mà người rời có thể còn biết.
- Đánh giá **raw-key exposure** để quyết định thay signing key, KEK, DEK hoặc KDF root tương ứng.
- Không disable bừa **machine identity hợp pháp** đang vận hành production; chuyển ownership rồi xác minh.
- Audit và bảo đảm provider hiệu lực theo thời gian, không chỉ request accepted.

## 13. Phân vai và RACI cho cấp phát khóa

Phân phối key material hoặc cấp quyền Sign/Unwrap phải được quản trị bởi nhiều vai trò với **separation of duties**.

| Vai trò | Trách nhiệm chính | Không nên mặc nhiên có quyền |
|---|---|---|
| **Service/application owner** | Đề xuất purpose, identity, dependencies, test workflow | Export root/KEK hoặc tự cấp production IAM |
| **Key owner/data owner** | Chấp thuận scope nghiệp vụ, tenant/data category, retention | Tự thay HSM key policy không qua kiểm soát |
| **Security administrator** | Security baseline, review IAM/exportability, approve policy | Đọc raw private key hay Decrypt dữ liệu khách hàng |
| **IAM/identity operator** | Provision workload identity, token/federation, roles | Tự ký tài liệu hoặc lấy DEK cho mọi tenant |
| **KMS/HSM operator** | Tạo/rotate/restore keys theo approval, duy trì provider | Sử dụng key data plane trái policy |
| **PKI/CA operator** | Enrollment, issuance, trust policy và revocation | Chấp nhận CSR với arbitrary SAN ngoài identity |
| **Crypto user/workload** | Sign/Encrypt/Decrypt/MAC trong scope được cấp | Manage grants, DestroyKey, Export raw KEK |
| **Independent auditor** | Đối soát approvals, key inventory, events và enforcement | Sửa audit hoặc thực hiện Sign/Decrypt |
| **Incident responder** | Cô lập credential/key, điều tra, phối hợp rotation | Giữ break-glass permission vô thời hạn |

RACI minh họa: **R** thực thi, **A** chịu trách nhiệm quyết định, **C** tham vấn, **I** nhận thông tin. **SO** = Service owner, **KO** = Key owner, **SA** = Security administrator, **OP** = IAM/KMS operator, **AU** = Auditor.

| Công việc | SO | KO | SA | OP | AU |
|---|---|---|---|---|---|
| Yêu cầu dùng key purpose mới | **R** | **A** | C | I | I |
| Chọn algorithm/crypto boundary | C | C | **A/R** | C | I |
| Xác minh workload identity | C | I | **A** | **R** | I |
| Tạo hoặc import key theo policy | I | C | **A** | **R** | I |
| Grant key operation cho workload | R | **A** | **R** | R | I |
| Sign/Encrypt/Unwrap trong nghiệp vụ | **A/R** | C | I | I | I |
| Rotate key và chuyển service | R | **A** | C | **R** | I |
| Thu hồi quyền sau sự cố | C | C | **A/R** | R | I |
| Hủy key sau dependency/retention review | C | **A** | **R** | R | C |
| Audit độc lập | I | I | C | C | **A/R** |

Một hàng có thể có nhiều R vì quá trình vận hành phân tán; RACI không trao quyền tự động. Tổ chức cần **approval workflow và IAM enforcement** để một principal không tự nâng quyền rồi tự che audit. Với thao tác nhạy cảm, có thể cần dual control/quorum và kiểm toán độc lập theo chính sách thực tế.

## 14. Tính sẵn sàng và khôi phục khi provisioning lỗi

### 14.1. KMS hoặc IdP tạm thời không sẵn sàng

~~~text
IdP không cấp credential?
    -> Không tự dùng một shared root token hardcode.
    -> Dùng session/identity cache nếu còn hiệu lực theo policy,
       hoặc fail closed/approved recovery route.

KMS không mở DEK?
    -> Không lưu plaintext KEK dự phòng cạnh database.
    -> Dùng DR/provider failover đã được phê duyệt.

Service có cached DEK còn TTL?
    -> Thực hiện theo key-use lease policy đã xác định trước.
    -> Không kéo dài TTL vô hạn chỉ vì KMS lỗi.

Certificate enrollment fail?
    -> Giữ cert cũ chỉ khi còn hợp lệ và policy cho phép.
    -> Không bỏ xác thực mTLS hoặc trust verification.
~~~

**Fail closed không có nghĩa bỏ qua thiết kế availability**. Có thể chuẩn bị HA, multi-region provider, secure backup, cached key-use leases có giới hạn, retry/backoff và recovery quorum; nhưng các lựa chọn phải được đánh giá trước về rủi ro raw material, trạng thái quyền và cryptoperiod.

### 14.2. Idempotency và sự kiện đến sai thứ tự

Một provisioning controller thường nhận sự kiện qua event bus:

~~~text
revision=10: GRANT service-X -> UNWRAP KEK-v3
revision=11: REVOKE service-X -> UNWRAP KEK-v3

Nếu consumer nhận revision 11 rồi lại nhận event revision 10:
    KHÔNG được re-GRANT sau khi đã REVOKE.
~~~

Cần **idempotency key, revision/desired state, stale-event rejection, reconcile loop và event audit**. Một webhook hoặc retry network không được tạo nhiều raw secret versions không kiểm soát hoặc cấp lại quyền đã thu hồi.

### 14.3. Positive/negative continuity checks

Sau mỗi key rotation/re-provisioning:

- **Service hợp lệ** vẫn có thể Sign/Encrypt/Decrypt/Unwrap theo mục đích.
- **Service bị thu hồi quyền** không còn gọi operation thành công theo effective time của provider.
- **Ciphertext lịch sử** vẫn có đúng EDK, KEK version và AAD để mở theo retention.
- **Chữ ký cũ** có thể Verify theo trust policy; key cũ không tiếp tục Sign mới nếu đã retire.
- **HMAC consumer** chấp nhận đúng version trong grace period và từ chối key cũ sau thời hạn.
- **Backup/DR** thử khôi phục đúng key material/handle và quyền, không chỉ sao chép metadata.

Một hệ thống chỉ đạt “không còn quyền” bằng cách phá hỏng toàn bộ dịch vụ hợp pháp **không phải provisioning/offboarding thành công**. Phải kiểm tra cả **security denial** và **business continuity**.

### 14.4. Backup và key escrow

Một private key/KMS KEK non-exportable có thể có **secure HSM backup/replication** tùy provider; “non-exportable cho ứng dụng” không tự đồng nghĩa “không có backup”. Quy trình cần xác định:

1. Backup có thể chứa **material, wrapped key hay chỉ metadata**?
2. Ai có quyền **Backup, Restore, Import, Export** và phê duyệt tương ứng?
3. Recovery có giữ **đúng key version và định danh** để mở dữ liệu cũ không?
4. Có **data residency**, retention và destruction policy cho backup không?
5. Đã thử DR bằng ciphertext/chữ ký lịch sử thật theo môi trường được phép chưa?

**Không tự chia raw KEK thành vài chuỗi rồi gọi là split knowledge.** Nếu cần secret sharing/threshold recovery, dùng cơ chế được kiểm chứng và provider contract.

## 15. Threat model: Các lỗi key provisioning điển hình

| Sai lầm | Tác động có thể xảy ra | Kiểm soát đề xuất |
|---|---|---|
| **Private signing key PEM gửi qua chat/email** | Secret có nhiều bản sao không kiểm soát; ký offline | Non-exportable signing key và Sign API khi phù hợp |
| **KEK/DEK hardcode trong repository** | Clone/build/image làm lộ raw key và lịch sử commit | KMS/HSM, wrapped DEK, runtime authorized provisioning |
| **Một credential KMS chung cho mọi service** | Compromise một service ảnh hưởng toàn hệ thống | Workload identity riêng, audience/scope, grants per purpose |
| **Trust bất kỳ JWT claim trong HTTP request** | Caller tự giả service/tenant và xin Unwrap | Validate issuer/signature/audience/expiry, authenticated identity |
| **Không kiểm tra audience của access token** | Token dùng cho service A bị replay sang KMS gateway | Audience-bound tokens, anti-replay/short TTL phù hợp |
| **Chỉ kiểm tra key ID mà không kiểm tra principal** | Biết key ref là có thể dùng key | IAM/key policy, application authorization, deny by default |
| **KMS permission theo resources toàn account** | Cross-tenant Unwrap hoặc Sign oracle | Granular scopes, key purpose, encryption context và audit |
| **Security admin tự tạo và tự duyệt grant** | Phá separation of duties, privilege escalation | Independent approval, privileged-access review |
| **Thay raw key cho service chỉ cần handle** | Phơi bày bí mật không cần thiết | Mode-aware provisioning và provider operation API |
| **Mọi workload chung HMAC secret** | Một workload lộ làm toàn bộ webhook bị giả | Secret per partner/purpose, versioning và rotation |
| **CSR chỉ cần được ký là cấp mọi SAN** | Mạo danh service khác bằng certificate hợp lệ | Issuer phải ràng buộc SAN với workload identity |
| **Tin public key từ URL do attacker đưa** | Mã hóa DEK tới recipient giả, Verify chữ ký giả | Authenticated trust anchors, issuer/key binding |
| **Dùng TLS nhưng không xác thực recipient identity** | Secret gửi tới endpoint sai dù kênh được mã hóa | Service discovery và authenticated destination policy |
| **Public key từ JWT header bất kỳ** | Key substitution/algorithm confusion | Fixed trusted JWKS/issuer, algorithm allowlist |
| **Gắn secret vào container image** | Registry/build cache chứa secret dài hạn | Runtime issuance và least privilege |
| **Key trong environment được coi là không thể lộ** | Config dump, process diagnostics, subprocess leak | Secret lifecycle, host controls, no-logging |
| **Tạo EDK nhưng lưu DEK bản rõ cạnh ciphertext** | Không còn tách lớp bảo vệ | Chỉ persist wrapped DEK, xóa raw DEK best effort |
| **Chỉ lưu alias current-key** | Rotate gây lỗi Decrypt dữ liệu cũ | Resolved immutable key ID/version trong envelope |
| **AES-GCM nonce trùng với cùng DEK/KEK** | Phá confidentiality và integrity | Nonce uniqueness theo key và toàn bộ instance |
| **A​AD được xây từ tenant do caller tự khai** | AAD hợp lệ nhưng authorization sai | Resource authorization trước Unwrap; canonical context |
| **KMS Disable nhưng quên DEK cache** | Workload vẫn Decrypt offline | TTL/invalidation, workload/session control |
| **Service-account token hết hạn nhưng fallback master key** | Bypass identity/authorization để tiếp tục chạy | Approved DR hoặc fail closed, không dùng hardcoded fallback |
| **Revoke xong có stale GRANT event tới trễ** | Quyền bị thu hồi được tự cấp lại | Policy revision, idempotency, reconcile desired state |
| **Secret rotation giữ bản cũ vô thời hạn** | Leaver/attacker vẫn có HMAC/API key hợp lệ | Bounded grace period, actual receiver deny |
| **Destroy KEK không rà dữ liệu lịch sử** | Mất khả năng giải mã archive/backup | Dependency inventory, restore drill trước Destroy |
| **Audit ghi full KMS response/raw secret** | Tạo thêm bản copy key trong telemetry | Chỉ log metadata, actor, key ID/version, outcome |
| **Không xử lý multi-region/key replica** | Region B dùng sai key material/version | Provider-supported replication, scoped key refs, DR tests |

### 15.1. Confused deputy trong cấp phát khóa

Một pattern lỗi:

~~~text
User A gọi:
    POST /decrypt {tenantId:"B", keyId:"tenant-B-KEK", recordId:"secret"}

CryptoService có KMS role Decrypt trên mọi tenant:
    tin keyId do caller gửi
    mở EDK của tenant B
    trả plaintext cho user A
~~~

KMS có thể kiểm tra **CryptoService được phép gọi API**, nhưng **không tự hiểu user A có quyền với record tenant B** nếu mô hình chỉ định danh CryptoService là principal. Cần **business authorization trước Unwrap**, ràng buộc tenant từ nguồn đáng tin, key policy scopes và audit per-user/request khi cần.

**Key handle không phải “vé truy cập” nếu ai biết handle cũng được phép dùng.** Handle chỉ tham chiếu material; điểm thực thi vẫn phải kiểm tra principal, action và context.

### 15.2. Khi key material đã được đưa ra ngoài

Nếu một service từng nhận **raw DEK, HMAC secret hoặc private key PEM**, việc thu hồi grants ở KMS có thể **không** thu hồi bản sao bên ngoài. Khi key material đã mất tin cậy, phải đánh giá:

- **HMAC:** thay shared secret, đồng bộ bên gửi/bên nhận, đóng grace period và chống replay.
- **Private signing key:** tạo keypair mới, revoke trust/certificate/JWKS theo nhu cầu, xử lý token/chữ ký.
- **DEK:** thay DEK và re-encrypt dữ liệu bị ảnh hưởng; rewrap bằng KEK mới không khôi phục bí mật của DEK cũ.
- **KEK/root:** đánh giá mọi wrapped/derived keys thuộc nhánh, thay material và migrate theo sự cố.
- **mTLS client private key:** revoke/rotate certificate và trust, xử lý session/credential tồn tại.

Nếu chỉ có **lộ quyền sử dụng KMS/HSM** nhưng raw key không export, vẫn cần điều tra **Sign/Decrypt/Unwrap events**: attacker có thể lạm dụng oracle để nhận plaintext/chữ ký mà không biết key bytes.

## 16. Audit, đối soát và phát hiện policy drift

### 16.1. Những sự kiện nên ghi

| Sự kiện | Metadata đáng ghi | Dữ liệu không nên ghi |
|---|---|---|
| **Enroll workload identity** | identity subject, issuer/trust domain, application owner, expiry | Bootstrap private key, full secret/token |
| **Request/CreateKey** | requester, owner, key ID/version, purpose, policy reference | Raw key material |
| **Approve provisioning** | approver, ticket, scope, before/after grants, effective time | Mật khẩu/hardware token secret |
| **Provision/Update grant** | principal, action, keyRef/version, provider outcome, revision | KMS plaintext response |
| **Secret read/lease** | workload identity, secret version, TTL, reason, result | Raw HMAC/API secret |
| **Sign/Decrypt/Unwrap** | principal, request ID, keyRef/version, tenant, success/failure | Plaintext, private key, raw DEK |
| **Rotate/Revoke** | key old/new version, actor, policy revision, impacted consumers | Raw KEK/DEK |
| **mTLS cert issue/revoke** | service SAN, serial, issuer, expiry, certificate status | Private key |
| **Backup/Restore/Destroy** | authorization, key dependencies, provider evidence, DR test ID | Recovery shares, root key bytes |
| **Break-glass** | actor, approvers, scope, expiry, incident ID, post-review | Emergency password hoặc secret |

Audit logs là tài sản có giá trị và có thể tiết lộ **tenant IDs, service topology, key IDs và thời gian gọi crypto API**; cần bảo vệ confidentiality/integrity, retention và quyền truy cập. **Không cho một principal vừa thay key policy vừa có thể xóa audit không để lại dấu vết**.

### 16.2. Key inventory nên liên kết những gì?

~~~text
Service identity:
    owner, tenant, environment, trust domain, role/grants

Key family/version:
    provider/partition, keyId, algorithm, purpose, state, exportability

Provisioning record:
    service -> key -> allowed operations -> delivery mode -> effectiveAt

Data dependency:
    key version -> wrapped DEKs -> ciphertext/archive
    private signing key version -> public key/JWKS/cert -> issued signatures

Recovery:
    backup/replica/quorum, approver, restoration test, retention
~~~

Inventory chỉ cần **metadata và references**, không phải nơi tập hợp raw KEK/private keys. Nếu tổ chức không có mapping **key ID/version ↔ service ↔ dữ liệu phụ thuộc**, sẽ khó xoay vòng, thu hồi grants hoặc chứng minh một key có thể destroy mà không ảnh hưởng dữ liệu cũ.

### 16.3. Các chỉ số vận hành

- Số service đang dùng **human credentials** hoặc shared root credential thay vì workload identity.
- Số key principals có quyền **Decrypt/Unwrap/Sign/Export/ManagePolicy rộng** ngoài phạm vi được phê duyệt.
- Tỷ lệ provisioning có **service owner, Key owner, approval, ticket, version và audit** đầy đủ.
- Số private signing keys production **có thể export** ngoài policy.
- Số secret/credential **đến hạn rotate** nhưng consumers chưa chuyển version.
- Số EDK còn phụ thuộc KEK retired và số signature cần public key cũ.
- Số lần **negative test** thất bại: cross-tenant access, expired token, wrong audience hoặc direct KMS API.
- Thời gian **revoke effective** theo provider và cache/lease còn hoạt động.
- Số cert mTLS sắp hết hạn, enrollment thất bại hoặc identity/SAN mismatch.
- Số **orphans**: service không có owner, key không có consumer, grants không có approved request.
- Kết quả **DR restore tests** với đúng key version và dữ liệu lịch sử.

**Không có alert không đồng nghĩa không có rủi ro.** KMS audit có thể không thấy private key đã export sang file trước đây hoặc DEK đang được dùng offline trong RAM. Cần kết hợp inventory, access review, runtime scanning và threat modeling.

## 17. Ứng phó sự cố provisioning: Hai trường hợp điển hình

### 17.1. Kịch bản A: Service credential bị lộ nhưng KEK không export

Một service account có quyền KMS Unwrap đã bị đánh cắp token. KEK vẫn non-exportable trong KMS.

**Runbook minh họa:**

1. **Xác thực incident:** xác định workload identity, token/role, key IDs, tenants, khoảng thời gian và nguồn alert.
2. **Cô lập quyền:** revoke sessions/credential/grants, ngăn cấp token mới bằng đường bị chiếm, cô lập workload/host nếu cần.
3. **Rà KMS audit:** những EDK/keys nào đã bị Unwrap, principal nào gọi, theo tenant/record nào; không tải raw DEK vào ticket.
4. **Đánh giá phạm vi:** attacker có thể đã nhận plaintext DEK hoặc dữ liệu; KEK non-exportable không có nghĩa dữ liệu chưa bị lộ.
5. **Cấp identity mới:** dùng workload identity và scopes tối thiểu, tránh quay về shared master key.
6. **Thay key material khi cần:** DEK đã lộ thì đánh giá re-encrypt; KEK chỉ cần rotation theo risk assessment và phụ thuộc.
7. **Kiểm thử:** principal cũ bị DENY, service hợp pháp với credential mới vẫn đọc dữ liệu đúng quyền.
8. **Audit và hậu kiểm:** cải thiện IAM, token TTL, resource authorization, detection và bootstrap controls.

### 17.2. Kịch bản B: Private signing key bị lộ qua pipeline

Billing Service trước đây nhận private key PEM thông qua CI/CD; một pipeline log đã vô tình chứa Base64 của PEM. Chỉ gỡ KMS Sign permission **không** vô hiệu hóa bản private key có thể đã bị sao chép.

**Runbook:**

1. Giới hạn log/artifact, bảo toàn chứng cứ trong phạm vi được kiểm soát.
2. Xác định private key version, chứng thư/public key liên quan, issuer và thời điểm lộ.
3. Tạo private key mới trong KMS/HSM theo policy; chỉ cấp Sign handle/permission cho Billing.
4. Chuyển signing mới sang version mới; cập nhật **JWKS/certificate/trust store** đúng quy trình.
5. Xác định token/chữ ký có thể bị giả, chặn key cũ khi cần và xem xét verification of historical signatures.
6. Thu hồi credential/CI permissions đã lộ, không gửi PEM mới qua kênh cũ.
7. Test đúng Billing Sign và các verifiers còn hoạt động; audit policy/incident events.

**Verify(signature, old public key)** vẫn có thể trả kết quả đúng về toán học dù private key đã bị lộ. Việc tin chữ ký phụ thuộc **issuer, thời điểm ký, trạng thái trust/revocation và chính sách nghiệp vụ**.

### 17.3. Khi hệ thống cấp phát không còn tin cậy

Một provisioning controller bị chiếm có thể tạo **unauthorized grants**, đổi alias/key policy, đăng ký certificate cho subject giả hoặc đọc shared secrets. Cần xem đây là **control-plane compromise**, không chỉ một secret lộ:

- Tạm ngăn hệ thống tự cấp quyền mới.
- Đối soát toàn bộ **policy/grants/roles/certificates/secret versions** đã tạo trong khoảng nghi vấn.
- Revoke credentials và quyền của controller; tạo credential mới từ trust root được phê duyệt.
- Thực hiện independent approval và kiểm tra tác động business continuity.
- Rà các key operations mà grants giả đã cho phép, đánh giá key material hoặc plaintext exposure.
- Khôi phục automation từ image/config được kiểm chứng, đối soát desired state và lập audit trail mới.

Không lập trình **break-glass tự động bypass mọi KMS policy** khi controller lỗi. Đường khẩn cấp phải có quyền scope hẹp, mốc hết hạn, audit và quy trình hậu kiểm.

## 18. Case study: Provisioning khóa cho nền tảng thanh toán nhiều tenant

Một tổ chức có bốn thành phần:

~~~text
Billing Service        -> Ký hóa đơn bằng Ed25519
Customer Data Writer   -> AES-GCM Encrypt, tạo DEK và wrapped DEK
Customer Data Reader   -> KMS Unwrap, AES-GCM Decrypt
Webhook Gateway        -> HMAC-SHA-256 theo partner

Identity               -> Workload federation / mTLS
KMS/HSM                -> Giữ KEK và signing private key
Secrets Manager        -> Secret HMAC với version/rotation
Key Inventory / Audit  -> Owner, policies, references, events
~~~

### 18.1. Cách triển khai yếu

Nhóm hạ tầng quyết định cấp một token KMS root cho cả bốn services, lưu nó trong shared environment variable. Họ export private signing key vào container image để giảm độ trễ và dùng một HMAC secret cho mọi đối tác.

**Rủi ro:**

1. Một service bị RCE có thể dùng credential chung để **Sign/Decrypt/Unwrap** ngoài purpose.
2. Bản private signing key trong image có thể bị lấy từ registry, CI cache và máy của developer.
3. HMAC secret chung khiến một đối tác bị compromise có thể ảnh hưởng những đối tác khác.
4. Không có **per-service identity và grants**, audit khó chỉ ra workload nào gây sự cố.
5. Nếu key IDs chỉ là alias động, rotation sẽ gây lỗi dữ liệu hoặc trust cho bản ghi/chữ ký cũ.
6. Thu hồi token chung khi sự cố có thể dừng cả nền tảng và không xóa raw key đã export.

### 18.2. Thiết kế lại theo các bước

**Bước 1 — Tách logical identities và owners.** Mỗi service có workload identity, environment, tenant, owner và on-call rõ. Không dùng tài khoản cá nhân để runtime sign/decrypt.

**Bước 2 — Phân loại các khóa.** Signing key là private key có mục đích Sign; tenant KEK chỉ Wrap/Unwrap; per-record DEK bảo vệ nội dung; HMAC secret riêng theo partner.

**Bước 3 — Chọn storage/delivery mode.** Private signing key tạo trong HSM/KMS non-exportable nếu provider phù hợp; KEK ở KMS/HSM; DEK được trả/unwrap tạm thời cho crypto layer; HMAC secret cấp qua secrets manager theo workload identity.

**Bước 4 — Cấp quyền theo purpose.** Billing chỉ Sign, Writer chỉ tạo/wrap DEK, Reader chỉ Unwrap đúng record/tenant, Webhook chỉ đọc HMAC secret của partner thuộc quyền. Không service nào tự có ChangePolicy/Destroy/Export.

**Bước 5 — Bảo vệ trust.** Public verification key/JWKS được gắn issuer/kid hợp lệ; mTLS SAN xác nhận workload; URL public key/crypto provider không đến từ untrusted request.

**Bước 6 — Envelope encryption.** Payload ciphertext chứa nonce/tag, EDK và immutable KEK key reference/version. Không lưu plaintext DEK; ràng buộc context và giới hạn nonce reuse.

**Bước 7 — Approvals và automation.** Key owner chấp thuận phạm vi nghiệp vụ, Security review quyền, platform automation triển khai theo revision; auditor không được tự Sign/Decrypt.

**Bước 8 — Rotation/DR.** Key versions cũ được giữ đúng lifecycle để Verify/Unwrap dữ liệu lịch sử; HMAC consumer có grace period hữu hạn; backup restore test với EDK thật trong môi trường được phê duyệt.

**Bước 9 — Kiểm thử.** Mỗi service chạy positive operation đúng quyền và negative operations trái purpose, khác tenant, raw export, token sai audience và key state disabled.

**Bước 10 — Monitoring.** Audit key usage, grants, credentials, policy changes, EDK dependencies và incidents; không log raw key hoặc decrypted customer data.

### 18.3. Một yêu cầu đặc biệt: Đối tác webhook mới

Một partner cần nhận webhook có HMAC. Workflow đúng:

1. Owner xác thực partner và phạm vi dữ liệu.
2. Security quyết định mỗi partner dùng một HMAC secret riêng, không dùng signing private key hoặc KEK.
3. Secrets manager tạo/ghi version mới và cấp qua kênh được xác thực cho đúng consumer.
4. Webhook Gateway tra version và tạo HMAC trên canonical message với timestamp, nonce/message ID để chống replay.
5. Receiver Verify bằng key đúng version; bên nhận không được tự lựa chọn endpoint tải secret từ untrusted headers.
6. Rotate theo cryptoperiod hoặc khi partner rời hệ thống, từ chối bản cũ sau cửa sổ chấp nhận.
7. Audit việc cấp/đọc/rotate, không in secret hoặc chữ ký kèm dữ liệu nhạy cảm vượt nhu cầu.

**Kết quả mong đợi:** Một sự cố ở Webhook Gateway không tự biến thành quyền lấy KEK khách hàng, một lỗi ở Customer Reader không tự thành quyền ký hóa đơn, và mỗi key family có owner, lifecycle, key ID/version cùng đường DR độc lập. Đây là kết quả của **key provisioning theo identity/purpose**, không chỉ của thuật toán AES hoặc Ed25519.

## 19. Checklist Provisioning key cho service trước production

1. **Identity:** Service có workload identity riêng, được issuer/trust domain tin cậy xác nhận, không dùng human/static root token?
2. **Bootstrap:** Đã kiểm tra issuer, audience, expiry, subject, claims và nơi nhận token/metadata?
3. **Owner:** Mỗi service, key family và grant có owner, on-call và người phê duyệt?
4. **Purpose:** Đã xác định Sign, Verify, Encrypt, Decrypt, Wrap, Unwrap, MAC hoặc DeriveKey đúng nhu cầu?
5. **Algorithm:** Key type, size/curve, CSPRNG, usage và provider được chấp thuận?
6. **Tenant/environment:** Tách production/staging, tenant và purpose, không shared key vượt trust boundary?
7. **Delivery mode:** Có thể cấp handle thay vì raw private key/KEK không; có lý do rõ nếu raw secret cần vào JVM?
8. **KMS/HSM storage:** Key attributes, non-exportability, backup/replication và provider contract đã được xác minh?
9. **No hardcode:** Không đặt raw key, token dài hạn hoặc PEM vào Git, container image, CI artifact hay log?
10. **Transport:** TLS/mTLS endpoint identity, recipient trust và service discovery được xác thực?
11. **PKI enrollment:** Certificate subject/SAN/EKU được ràng buộc với workload, private key được giữ đúng boundary?
12. **IAM/grants:** Quyền theo principal, operation, key ID/version, purpose, tenant, resource và TTL; default-deny?
13. **Business authorization:** Kiểm tra caller có quyền với record/tài liệu trước khi dùng Sign/Unwrap?
14. **Separation of duties:** Key admin, service owner, crypto user và auditor tách vai trò; high-risk grants có approval độc lập?
15. **Key reference:** Dữ liệu/chữ ký lịch sử giữ resolved key ID/version, không chỉ alias động?
16. **Envelope:** Wrapped DEK + payload ciphertext/nonce/tag được lưu đủ, không lưu plaintext DEK cạnh ciphertext?
17. **Nonce/AAD:** AES-GCM nonce không lặp với cùng DEK/KEK; AAD canonical và metadata được ràng buộc chính xác?
18. **Memory:** Raw DEK/HMAC secret có TTL/cache scope, giới hạn bản sao, dump/telemetry controls và cleanup best effort?
19. **HMAC:** Secret theo partner/purpose, có anti-replay, version và overlap/rotation hữu hạn?
20. **Public trust:** JWKS/certificate/public encryption key được lấy từ nguồn đáng tin, algorithm/issuer allowlist?
21. **Audit:** Có request, approver, actor, key ref/version, operation, outcome và effective time nhưng không log secret?
22. **Negative tests:** Đã kiểm tra sai service, tenant, audience, key state, purpose, delivery mode, raw export và direct API bypass?
23. **Rotation:** Có plan cho signing key, HMAC key, KEK, DEK, root KDF và session credentials, phân biệt rewrap/re-encrypt?
24. **Revocation:** Hiểu hiệu lực của IAM revoke, token/session TTL và plaintext DEK cached; không kết luận disable key là xóa mọi bản sao?
25. **Availability:** Có fail-closed/DR, retry/idempotency, stale-event handling, multi-region key mapping và continuity tests?
26. **Backup:** Có EDK, ciphertext, nonce/AAD format, key version, KMS recovery permissions và restore drill?
27. **Offboarding:** Human credential/leaver được thu hồi, service accounts chuyển owner, shared secrets được đánh giá rotation?
28. **Incident:** Có runbook khi controller bị chiếm, quyền Unwrap bị lạm dụng, raw DEK/HMAC/private key bị lộ?
29. **Drift:** Đã đối soát grants/policies/provider key states với inventory và approvals sau provisioning?
30. **Final review:** Quy trình bảo vệ cả dữ liệu và khả năng vận hành, không chỉ đạt một positive test hoặc API response 200?

### Câu hỏi tự kiểm tra

**Câu 1.** Provisioning private signing key cho Billing Service có bắt buộc gửi private key PEM vào service?

**Trả lời:** **Không.** Nếu provider hỗ trợ non-exportable key và Sign API, có thể chỉ cấp **workload identity, IAM grant và key handle**, để việc ký diễn ra trong HSM/KMS.

**Câu 2.** KMS giữ private key non-exportable thì Billing có tự động an toàn khỏi việc ký hóa đơn giả không?

**Trả lời:** **Không.** Workload có quyền Sign có thể bị biến thành signing oracle. Cần kiểm tra nghiệp vụ, purpose, rate/usage controls, IAM và audit.

**Câu 3.** Vì sao cần xác minh token audience khi service xin quyền dùng key?

**Trả lời:** Token hợp lệ nhưng dành cho **đích khác** không được mặc nhiên chấp nhận tại KMS gateway. Kiểm tra audience cùng issuer, subject, expiry và signature giúp giảm token replay/cross-service confusion.

**Câu 4.** Một service chỉ cần Verify JWT có cần được cấp private signing key của issuer không?

**Trả lời:** **Không.** Verifier cần public verification key/certificate từ nguồn đáng tin, issuer và thuật toán được cho phép. Phân phối private key cho verifier làm tăng blast radius không cần thiết.

**Câu 5.** Nếu có wrapped DEK trong database, service nào biết key ID cũng có quyền Unwrap chứ?

**Trả lời:** **Không.** Key ID và EDK không phải credential; KMS phải kiểm tra principal/key policy và ứng dụng phải kiểm tra quyền tenant/record trước Unwrap.

**Câu 6.** KMS giữ KEK non-exportable thì plaintext DEK chắc chắn không bao giờ có trong JVM?

**Trả lời:** **Không.** Một số KMS trả plaintext DEK cho ứng dụng thực hiện local AES-GCM. Cần kiểm soát lifetime, memory, logs và cache.

**Câu 7.** HMAC secret cấp cho cả sender và receiver có cung cấp non-repudiation như private/public digital signature không?

**Trả lời:** **Không.** Cả hai bên biết secret đều có thể tạo MAC hợp lệ. HMAC có thể xác thực thông điệp giữa các bên cùng secret nhưng không chứng minh riêng ai đã tạo nó.

**Câu 8.** Một CSR được ký bằng private key có tự chứng minh service được quyền mang SAN billing.prod không?

**Trả lời:** **Không.** CSR chứng minh sự sở hữu/điều khiển private key; CA phải xác minh subject/SAN dựa trên workload identity/approval.

**Câu 9.** Có thể dùng cùng một bootstrap master token trong container image cho mọi service nếu token được gửi qua TLS không?

**Trả lời:** **Không nên.** TLS không sửa rủi ro secret chung và long-lived; khi token lộ, nhiều services có thể bị ảnh hưởng. Ưu tiên workload identities riêng và short-lived credentials.

**Câu 10.** KEK rotate từ v3 sang v4 có nghĩa toàn bộ DEK và payload ciphertext đã được rotate chưa?

**Trả lời:** **Chưa.** Alias/key version mới chỉ ảnh hưởng operations theo policy. EDK cũ có thể vẫn dưới KEK-v3; rewrap cùng DEK không phải DEK rotation. Muốn đổi DEK cho dữ liệu cũ cần re-encrypt.

**Câu 11.** Thu hồi KMS Unwrap grant có xóa được plaintext DEK đã nằm trong cache của process không?

**Trả lời:** **Không.** Cached DEK còn có thể giải mã offline. Cần TTL, invalidation, xử lý workload/session và thay material theo incident scope nếu đã lộ.

**Câu 12.** Certificate mTLS còn hạn có đồng nghĩa service được phép truy cập mọi record không?

**Trả lời:** **Không.** mTLS chứng minh identity và bảo vệ kênh. Resource authorization, tenant/purpose và KMS grants vẫn là những lớp riêng.

**Câu 13.** Vì sao phải ghi immutable key ID/version trong envelope mà không chỉ dùng alias current?

**Trả lời:** Alias có thể đổi mục tiêu khi rotate. Ciphertext lịch sử cần resolve đúng material/version đã bọc DEK hoặc đã ký thông điệp.

**Câu 14.** KMS hết kết nối có nên mở fallback bằng một raw KEK đã chép vào config không?

**Trả lời:** **Không.** Đó là bypass ranh giới bảo vệ. Cần HA/DR đã phê duyệt, lease có giới hạn theo policy hoặc fail closed.

**Câu 15.** Provisioning API trả HTTP 200 có đủ để chứng minh service mới đã được cấp quyền chính xác không?

**Trả lời:** **Không.** Cần xác minh provider state, policy effective time, đúng key reference và positive/negative data-plane tests.

**Câu 16.** Có thể xóa KEK cũ ngay khi mọi service đã chuyển sang Wrap bằng KEK mới?

**Trả lời:** **Không.** Những EDK cũ, backup hoặc archive có thể vẫn cần KEK cũ để Unwrap. Phải kiểm tra dependency, rewrap/restore và retention trước khi Destroy.

**Câu 17.** Nếu provisioning controller bị chiếm nhưng raw KEK chưa export, có thể bỏ qua incident response không?

**Trả lời:** **Không.** Controller có thể tạo grants, thay key policy, phát certificate trái phép hoặc dùng KMS như oracle. Phải rà control-plane changes, data-plane usage và tác động dữ liệu.

**Câu 18.** Trong Java demo, một quyết định ALLOW có chứng minh KMS đã cấp đúng quyền và key non-exportable không?

**Trả lời:** **Không.** Demo kiểm tra metadata giả lập. Production cần IdP/IAM, KMS/HSM enforcement, audit, provider attributes và kiểm thử đường gọi thực.

## 20. Tổng kết

**Provisioning key cho service** là bài toán **đưa đúng năng lực mật mã tới đúng workload, đúng mục đích, đúng thời điểm và trong ranh giới tin cậy**, không đơn thuần truyền một tập tin secret. Các thiết kế ưu tiên **key handle, KMS/HSM Sign/Wrap/Unwrap, workload identity và quyền tối thiểu**, chỉ cấp raw material khi API/giao thức thực sự cần và có memory/rotation policy phù hợp.

Một thiết kế tốt cần kết hợp:

- **Trust bootstrap:** workload identity có nguồn xác thực, audience, TTL và khóa cấp credential không bị hardcode dùng chung.
- **Policy và approval:** service owner/Key owner/Security xác định purpose, key class, tenant, allowed operations, delivery mode và key state; kiểm tra SoD.
- **Cryptography:** DEK/KEK được tách đúng, public key đáng tin, mTLS enrollment xác thực SAN, HMAC secret theo partner, AES-GCM nonce và AAD đúng.
- **Vận hành:** key ID/version bất biến cho dữ liệu lịch sử, key inventory, audit, cache TTL, rotation/revocation, DR và xử lý sự cố.
- **Verification:** kiểm tra cả **ALLOW đúng nhu cầu** và **DENY ngoài phạm vi**, không coi một checkbox hoặc cấu hình YAML là security enforcement thực tế.

**Điểm cốt lõi:** Một service thường **không cần sở hữu raw private key hay KEK**; nó cần **được xác thực và cấp quyền thực hiện phép toán đã được phê duyệt**. Tách rõ **key material, key reference, workload identity, authorization, key lifecycle và audit** giúp hạn chế lộ khóa, ngăn lạm dụng KMS/HSM và duy trì khả năng giải mã, xác minh và khôi phục khi hệ thống phát triển.
