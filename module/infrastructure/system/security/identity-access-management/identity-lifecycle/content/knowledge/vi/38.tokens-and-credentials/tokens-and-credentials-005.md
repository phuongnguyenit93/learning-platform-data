# Credential vault trong quản lý Token, Credential và vòng đời danh tính IAM

## 1. Credential vault là gì?

**Credential vault** là hệ thống hoặc dịch vụ chuyên dụng để **lưu giữ, bảo vệ, kiểm soát việc truy xuất, cấp phát, xoay vòng, thu hồi và kiểm toán thông tin xác thực bí mật**. Những bí mật được quản lý có thể gồm **mật khẩu của service account, API key, OAuth client secret, refresh token, private key, signing key và credential truy cập database hoặc hạ tầng**. Tùy sản phẩm, vault còn có thể **phát hành credential tạm thời** thay vì chỉ lưu một secret cố định.

Ví dụ, dịch vụ **payments-api** phải ghi giao dịch vào database **payments-db**. Một cách thiếu an toàn là lưu username/password database trong Git, container image hoặc cấu hình dùng chung của nhiều đội. Với credential vault, ứng dụng **xác thực danh tính workload**, được kiểm tra chính sách và chỉ nhận credential có phạm vi cho đúng database. Vault ghi audit về sự kiện cấp bí mật; hệ thống quản trị có quy trình **rotation, expiry và revocation**.

**Credential vault không phải là nơi lưu tất cả quyền truy cập dưới dạng một file mã hóa.** Khả năng lưu secret không tự tạo **least privilege**, không tự chứng minh client có quyền đọc secret, và không tự bảo đảm credential đã bị thu hồi tại hệ thống đích.

Bài thuộc chương **Token và credential** của mô-đun **SECURITY_IDENTITY_ACCESS_MANAGEMENT_IDENTITY_LIFECYCLE**. Mô-đun tìm hiểu vòng đời danh tính theo **Joiner–Mover–Leaver (JML)**, từ xác minh, tạo tài khoản, cấp quyền đến rà soát và thu hồi khi thay đổi vai trò; liên kết **IdP, SSO, SCIM, RBAC/ABAC, tài khoản dịch vụ, kiểm toán** và giảm **quyền truy cập tồn dư**. Với vault, cần quản trị **cả người được quyền thao tác vault** lẫn **workload dùng credential**.

### Mục tiêu học tập

Sau bài này, người học cần có thể:

1. Giải thích credential vault và phân biệt **secret, credential, token, key, certificate và entitlement**.
2. Mô tả **vault architecture, encryption, identity authentication, policy evaluation, secret delivery và audit**.
3. Thiết kế quyền đọc/cấp/đổi secret theo **least privilege, RBAC/ABAC/PBAC, tenant và environment**.
4. Phân biệt **static secrets**, **dynamic credentials**, **leased secrets** và **short-lived tokens**.
5. Hiểu giới hạn của **rotation, revoke, cache, session và token đã phát**.
6. Tích hợp vault với **Kubernetes, CI/CD, cloud, PKI, PAM/JIT, IdP/SSO và SCIM**.
7. Quản lý **owner, service identity và Joiner–Mover–Leaver** mà không làm gián đoạn workload hợp lệ.
8. Thiết kế **audit, backup, disaster recovery, reconciliation, test và incident runbook**.

## 2. Phân biệt secret, credential, token, key và quyền truy cập

| Khái niệm | Ý nghĩa | Ví dụ | Không nên hiểu nhầm |
|---|---|---|---|
| **Secret** | Dữ liệu bí mật cần bảo vệ | DB password, signing private key | Mọi secret đều là password |
| **Credential** | Bằng chứng dùng để xác thực hoặc chứng minh quyền kiểm soát | API key, certificate + private key | Có credential là được mọi quyền |
| **Access token** | Chứng cứ dùng khi gọi resource server | OAuth token cho payments API | Token có thể dùng với mọi audience |
| **Refresh token** | Credential giúp client xin access token mới khi được phép | Refresh token của integration | Chỉ xóa bản local là đã revoke |
| **Private key** | Vật liệu mật mã bí mật | Khóa mTLS hoặc private-key JWT | Certificate công khai cũng phải giấu như private key |
| **Certificate** | Chứng thư liên kết public key với danh tính | X.509 TLS leaf certificate | Certificate tự cấp authorization nghiệp vụ |
| **Entitlement** | Quyền thực hiện action trên resource | payments.write của tenant A | Đã cấp vault read là đã cấp DB write |
| **Vault access token** | Credential dùng để gọi vault | Token hoặc workload-auth session | Có thể an toàn để ghi vào log |
| **Lease** | Thời hạn và metadata quản lý secret/credential được phát | DB credential 30 phút | Hết lease là target luôn vô hiệu ngay |
| **Identity** | Đối tượng người/workload được nhận diện | person-2046, service:payments-api | Username/email luôn là ID bất biến |

**Vault có thể bảo vệ một credential nhưng không phải nguồn sự thật duy nhất của authorization.** Ví dụ vault chứa khóa API của một SaaS; chính SaaS mới quyết định khóa đó còn active và được làm gì. Muốn thu hồi thật, phải **revoke tại SaaS và đối soát**.

### Mật khẩu đăng nhập của người dùng có nên đưa vào vault?

Thông thường **không lưu mật khẩu người dùng theo dạng có thể giải mã** để phục vụ đăng nhập ứng dụng. Hệ thống authentication nên sử dụng cơ chế lưu **password verifier được băm và bảo vệ phù hợp**, hoặc passwordless/federation. Credential vault phù hợp cho **technical secret cần dùng lại bởi workload** hoặc **privileged credential được quản lý theo chính sách**, không phải lý do để ứng dụng lưu lại mật khẩu thật của mọi nhân viên.

## 3. Vì sao cần credential vault thay vì file cấu hình?

Một cấu hình thiếu kiểm soát có thể có:

~~~yaml
# VÍ DỤ PHẢN DIỆN: không áp dụng cho production.
payments:
  db:
    username: shared-admin
    password: EXAMPLE-INSECURE-PLACEHOLDER
  thirdPartyApiKey: EXAMPLE-PLAINTEXT-PLACEHOLDER
~~~

Nếu các giá trị thật được đưa vào Git hoặc image, chúng có thể lan tới **branch, fork, build cache, CI logs, backup, developer workstation và container registry**. Sau khi xóa khỏi phiên bản mới, lịch sử và bản sao vẫn có thể còn.

### Vault giải quyết được những vấn đề nào?

- **Tập trung quản lý vòng đời** của secret trong phạm vi được định nghĩa.
- **Mã hóa và giới hạn quyền đọc** theo danh tính người/workload.
- **Audit:** ai yêu cầu secret nào, vào thời điểm nào và theo policy nào.
- **Rotation và versioning** cho những secret mà backend hỗ trợ.
- **Cấp credential theo nhu cầu** thay vì dùng một key toàn tổ chức.
- **Tách environment/tenant** để giảm bán kính ảnh hưởng khi lộ.
- **Thu hồi và incident response** có nơi điều phối rõ.
- **Secret inventory và ownership** phục vụ access review/JML.

### Điều vault không tự chữa

Một ứng dụng được phép đọc secret **có thể làm lộ secret qua bug hoặc bị xâm nhập**. Vault cũng không thể sửa một role database cấp **DROP ALL TABLES** khi nhu cầu chỉ cần SELECT. Bảo mật cần kết hợp **workload identity, target permissions, network isolation, key protection, monitoring và runtime authorization**.

## 4. Các mục tiêu bảo mật của credential vault

| Thuộc tính | Yêu cầu | Ví dụ thất bại |
|---|---|---|
| **Confidentiality** | Chỉ principal được phép đọc secret | Developer đọc production key ngoài nhiệm vụ |
| **Integrity** | Không sửa secret/policy trái phép | Attacker thay payment gateway key |
| **Availability** | Ứng dụng hợp lệ lấy credential khi cần | Vault outage làm toàn bộ service không kết nối DB |
| **Authentication** | Xác minh ai đang gọi vault | Chỉ tin header x-workload-name client tự khai |
| **Authorization** | Kiểm quyền trên secret path/action/version | Được đọc dev nhưng lại đọc prod |
| **Accountability** | Có audit đủ để điều tra | Shared root token khiến không biết ai lấy secret |
| **Lifecycle control** | Tạo, rotate, revoke, retire đúng thời điểm | Secret cũ còn dùng sau Leaver |
| **Least privilege** | Credential được cấp đúng scope và TTL | Một key global admin dùng cho mọi service |
| **Recoverability** | Có kế hoạch backup/DR có kiểm soát | Không thể phục hồi unseal/recovery keys |
| **Verifiability** | Đối soát quyền tại đích, không chỉ vault | Đã xóa entry nhưng API key vẫn hoạt động |

Bảo mật vault cần cân bằng **availability và revocation**. Tăng cache quá lâu giúp vượt outage nhưng có thể kéo dài thời gian lộ credential; giảm TTL cực ngắn mà không có refresh/retry có thể gây ngừng hệ thống.

## 5. Kiến trúc tổng quát của credential vault

~~~mermaid
flowchart TD
    HR[HRIS / Contract / JML] --> IAM[IAM / IGA / Policy]
    REG[Workload / Asset Registry] --> IAM
    APP[Application / CI Job / Human Admin] --> AUTH[Vault Authentication]
    IDP[IdP / Workload Issuer] --> AUTH
    AUTH --> PDP[Policy Evaluation]
    IAM --> PDP
    PDP -->|Permit| VAULT[Secret Engine / Credential Vault]
    PDP -->|Deny| DENY[Access Denied]
    VAULT --> STORE[(Encrypted Secret Storage)]
    VAULT --> KMS[KMS / HSM / Seal Keys]
    VAULT --> TARGET[Database / Cloud / SaaS / PKI]
    VAULT --> AUDIT[Audit and Metrics]
    TARGET --> OBS[Target Readback / Reconciliation]
    OBS --> IAM
    AUDIT --> IAM
~~~

Đây là **mô hình tham khảo**, không phải mô tả bắt buộc của một sản phẩm. Một triển khai có thể có nhiều secret engines, clusters, HSM, KMS, token issuers, proxies hoặc policy evaluation points.

### Ba ranh giới không được nhầm

1. **Ai được gọi vault?** Xác thực bằng human SSO/MFA hoặc workload identity đáng tin.
2. **Được thao tác secret nào?** Vault policy, path/resource scope, action và điều kiện.
3. **Credential lấy ra cho phép làm gì?** Quyền ở **database, cloud, SaaS, API hoặc target**.

**Vault Permit read secret không chứng minh target Permit mọi action.** Và **vault Deny mới** không tự vô hiệu secret đã được client lấy trước đó.

## 6. Credential vault khác KMS, HSM, password manager và IdP

| Thành phần | Trọng tâm | Quan hệ với credential vault |
|---|---|---|
| **Credential vault/Secrets manager** | Quản lý secret, policy, delivery, rotation, lease, audit | Trung tâm vòng đời bí mật |
| **KMS** | Quản lý khóa mã hóa và thao tác cryptographic | Có thể bảo vệ master/wrapping keys của vault |
| **HSM** | Thiết bị/ranh giới bảo vệ và thực thi thao tác khóa | Có thể giữ khóa nền tảng, không nhất thiết lưu mọi API key |
| **Password manager** | Quản lý mật khẩu người dùng/nhóm | Thường tập trung credential cần con người truy xuất |
| **PAM vault** | Bảo vệ credential đặc quyền và phiên quản trị | Có thể là một dạng credential vault với session control |
| **IdP/SSO** | Xác thực danh tính/federation | Cấp assertion cho vault, không lưu mọi DB password |
| **STS/Token service** | Cấp token/credential tạm từ trust policy | Có thể tích hợp hoặc thay thế static secret |
| **PKI/CA** | Cấp, ký và quản lý chứng thư | Vault có thể chứa private key hoặc tích hợp PKI engine |
| **IAM/IGA** | Quản lý danh tính, entitlement, review và JML | Quyết định ai/workload được quyền với vault |

### Mã hóa dữ liệu không đồng nghĩa quản lý secret

Một KMS có thể mã hóa file cấu hình, nhưng nếu ứng dụng giải mã file rồi cấp **cùng một admin password** cho mọi pod, vấn đề **chung credential và thiếu lifecycle** vẫn tồn tại.

### Secret manager và password manager có thể giao nhau

Một tổ chức có thể dùng password vault cho break-glass admin, đồng thời dùng secrets manager cho workload API tokens. Cần xác định **mục đích, audience, quyền thao tác, audit và cơ chế rotation** cho từng loại thay vì giả định một công cụ là nguồn sự thật của tất cả.

## 7. Phân loại những secret cần quản lý

| Secret/credential | Đối tượng sử dụng | Yêu cầu đặc thù |
|---|---|---|
| **Database password** | Service hoặc DBA | Role hẹp, đổi mật khẩu và cập nhật pool |
| **Cloud access key** | Workload legacy | Ưu tiên migration sang federation/role tạm |
| **OAuth client secret** | Confidential client | Cấp cho đúng client, rotation và revoke tại AS |
| **OAuth refresh token** | App/connector có cấp phép | Bảo vệ rotation/reuse detection và token family |
| **SaaS API key/PAT** | Integration/bot | Scope, owner, expiry/revoke tại vendor |
| **SSH private key** | Automation/admin | Key custody, authorized_keys/cert expiry |
| **TLS private key** | Web server/mTLS workload | CA issuance, rotation, certificate chain |
| **Code-signing private key** | Release pipeline | Ký artifact, key protection/SoD |
| **Encryption key/wrapping key** | Data encryption service | KMS/HSM separation và key policy |
| **PAM root/admin password** | Privileged session | Checkout approval, rotation, session audit |
| **Webhook signing secret** | Service integration | Xác minh request, rotation dual-key window |
| **Device bootstrap credential** | Device enrollment | One-time/bound credentials, expiry |
| **Service account token** | Kubernetes/workload | Audience, projected/short-lived tokens |
| **Secret-less configuration** | App dùng managed identity | Không nhất thiết cần lưu static password |

**Không phải mọi giá trị môi trường đều là secret.** Port, timeout hay endpoint public không cần đặt trong vault chỉ để tăng độ phức tạp. Nhưng phải đánh giá cả **các giá trị có thể được dùng để chứng thực hoặc giải mã dữ liệu**.

## 8. Secret inventory và metadata có thẩm quyền

Một hệ thống vận hành cần biết **secret thuộc ai, phục vụ việc gì và ở target nào**, không chỉ có một path chứa bytes.

~~~json
{
  "secretId": "secret:payments-db-writer",
  "vaultPath": "teams/payments/prod/db/writer",
  "ownerTeamId": "payments-platform",
  "consumerWorkloadIds": ["service:payments-api"],
  "targetSystem": "payments-db",
  "environment": "production",
  "tenantId": "org-vn",
  "secretType": "DATABASE_CREDENTIAL",
  "lifecycleState": "ACTIVE",
  "riskTier": "HIGH",
  "rotationPolicyRef": "db-prod-rotation-v3",
  "lastRotatedAt": "2026-11-23T02:00:00Z",
  "nextReviewAt": "2027-01-15T00:00:00Z",
  "sourceVersion": 7
}
~~~

Đây là **schema metadata minh họa**, không phải chuẩn định dạng của một vault cụ thể. Không đặt raw password hoặc private key trong catalog.

### Metadata nên có

- **Secret ID** ổn định, path và namespace.
- **Owner team / sponsor**, quan hệ trách nhiệm và escalation.
- **Target service** và tài khoản/role mà credential kiểm soát.
- **Consumer identities** cụ thể; không chỉ một nhóm “all-services”.
- **Environment, tenant, region và data classification**.
- **Credential type**, mức đặc quyền và mục đích.
- **Expiry/rotation, revocation method và dependency**.
- **Source of truth và source version**.
- **Audit policy, access review frequency**.
- **Status**: proposed, active, suspended, retiring, retired.

### Owner không có nghĩa được đọc raw secret

Có thể **owner team** được quyền review policy và request rotation mà không có quyền trực tiếp đọc private key production. Điều này giúp phân tách nhiệm vụ và giảm rủi ro.

## 9. Xác thực với vault: human, workload và machine

Trước khi được vault cấp credential, client phải chứng minh danh tính.

| Chủ thể | Phương thức điển hình | Điều phải kiểm tra |
|---|---|---|
| **Nhân viên quản trị** | IdP/SSO + MFA | Subject, group, auth context, current employment |
| **CI/CD job** | OIDC job assertion/federation | Issuer, repository, environment, ref/workflow, audience |
| **Kubernetes workload** | ServiceAccount bound token/identity federation | Cluster/issuer, namespace, workload, audience |
| **Cloud VM/serverless** | Managed/instance identity | Nền tảng phát chứng cứ, workload role binding |
| **mTLS client** | Certificate/identity attestation | Trust chain, SAN/SPIFFE ID, EKU và validity |
| **Legacy app** | AppRole/secret-based bootstrap theo sản phẩm | Bảo vệ bootstrap credential, TTL, binding, rotation |
| **Thiết bị** | Device certificate/attestation | Asset, owner, trust domain và trạng thái |

### Bootstrap problem

Một câu hỏi khó là: **ứng dụng lấy credential đầu tiên để truy cập vault từ đâu?** Nếu phải lưu một **vault root token dài hạn trong Git**, hệ thống chỉ di chuyển vấn đề bảo mật.

Cách tốt hơn khi được hỗ trợ là dùng **workload identity do platform chứng thực** để lấy token vault ngắn hạn. Nếu bắt buộc dùng bootstrap secret, nên quản lý kênh cấp phát, one-time/bound usage, TTL, rotation và bảo vệ tốt hơn credential đích.

### Đăng nhập không tự cho quyền đọc secret

Một nhân viên được IdP xác thực đúng không có nghĩa được đọc mọi secret trong vault. Vault còn phải kiểm **authorization trên path/action và trạng thái JML**.

## 10. Vault authorization: least privilege theo action và resource

Một vault có thể có những thao tác khác nhau:

- **Read** secret hoặc credential response.
- **List** metadata/path nếu được phép.
- **Create/Update** phiên bản hoặc cấu hình.
- **Delete/Destroy** version, theo mô hình triển khai.
- **Generate** dynamic credential.
- **Renew/Revoke** lease/token nếu được cấp quyền.
- **Manage policy/auth method**.
- **Rotate** secret hoặc cấu hình backend role.
- **Audit/administrative operations**.

**Không nên gom read, write, policy admin và audit-admin vào một quyền chung** chỉ vì người dùng “quản lý service”.

### Ma trận policy minh họa

| Principal | Path/scope | Quyền | Điều kiện |
|---|---|---|---|
| **payments-api prod** | payments/prod/db/writer | Generate/Read cần thiết | Workload identity + prod |
| **reports-job prod** | reports/prod/storage/reader | Read/Generate | Không có quyền payments |
| **Payments owner** | payments/prod metadata | List/Review/Request rotation | Human SSO + MFA |
| **Security approver** | Privileged secret policy | Approve exception | Không tự checkout ngoài SoD |
| **Vault operator** | Platform health/HA | Operate | Không mặc nhiên đọc secret content |
| **Auditor** | Redacted audit events | Read audit | Không đọc raw credential |
| **CI staging** | payments/staging/deploy | Read limited | Không được truy cập production |

### Policy tham khảo, không phải cú pháp sản phẩm

~~~yaml
policyId: payments-prod-db-read-v2
subject:
  workloadId: service:payments-api
  environment: production
resource:
  namespace: teams/payments
  path: prod/db/writer
actions:
  - generateCredential
conditions:
  ownerTeamActive: true
  workloadState: ACTIVE
  audience: vault.production.example.org
  maxLeaseSeconds: 1800
denyIf:
  - crossTenant
  - suspendedOrRetired
~~~

**Policy trên là mô hình khái niệm**. Cần ánh xạ sang cú pháp thật và kiểm những điều kiện được engine thực thi; ghi **ownerTeamActive** trong YAML mà không có PIP/PEP kiểm thì không có tác dụng bảo mật.

## 11. Namespace, path, môi trường và tenant isolation

Một path có cấu trúc làm rõ quyền sở hữu và phạm vi:

~~~text
org-vn/
  teams/
    payments/
      prod/db/writer
      prod/api/webhook-signing
      staging/db/reader
    analytics/
      prod/reports/storage-reader
~~~

### Quy tắc đặt namespace

1. Tách **production, staging, development** theo policy và trust boundaries.
2. Tách **tenant/customer** nếu rủi ro hoặc nghĩa vụ đòi hỏi.
3. Tách **service purpose**; không dùng một credential cho nhiều workload khác chức năng.
4. Gắn **owner** và lifecycle metadata, không chỉ folder.
5. Tránh path tùy tiện chứa email, credential hoặc PII không cần thiết.
6. Không dựa vào tên path để xác thực principal; vẫn phải kiểm **vault policy**.
7. Kiểm **wildcard/prefix access** thật sự có thể dẫn tới path nào.
8. Kiểm **list permission** vì đôi khi chỉ thấy tên secret đã là thông tin nhạy cảm.

### Ví dụ lỗi

Một policy cho tất cả workloads dưới **teams/payments/** quyền read bao gồm cả **payments/prod/admin/root-key** có thể vượt nhu cầu. Tên path không tự an toàn; quyền phải theo **resource scope và action cần thiết**.

### Tenant isolation nhiều lớp

Vault path policy không thay thế tenant isolation ở **database, API và cloud**. Một credential thuộc tenant A mà target vẫn chấp nhận cho dữ liệu tenant B là lỗi authorization ở đích, dù secret được lưu đúng path.

## 12. Encryption at rest, encryption in transit và envelope encryption

**Mã hóa khi lưu** bảo vệ dữ liệu trên storage trước các kiểu truy cập không có key thích hợp. **Mã hóa khi truyền** bảo vệ giao tiếp tới vault và target, thường qua TLS/mTLS.

### Mô hình envelope encryption

~~~mermaid
flowchart LR
    S[Plaintext secret trong vùng xử lý bảo vệ] --> ENC[Encrypt with Data Encryption Key]
    DEK[DEK] --> ENC
    ENC --> CT[(Encrypted secret blob)]
    DEK --> WRAP[Wrap DEK with KEK]
    KEK[KMS/HSM Key Encryption Key] --> WRAP
    WRAP --> WDEK[(Wrapped DEK)]
    CT --> REC[Stored record]
    WDEK --> REC
~~~

Trong mô hình này:

- **Data Encryption Key (DEK)** mã hóa secret.
- **Key Encryption Key (KEK)** bảo vệ DEK.
- **KMS/HSM** có thể quản lý KEK hoặc phép toán cần thiết.
- Vault thực thi policy/authn/audit trước khi giải mã/cấp dữ liệu.

Đây là sơ đồ khái niệm; thực tế mỗi sản phẩm có cách quản lý key, transaction và storage khác nhau.

### Những điều encryption không giải quyết

- Principal hợp lệ nhưng bị chiếm quyền đọc secret.
- Vault policy cho quá nhiều người đọc.
- Secret đã được gửi ra ứng dụng rồi bị ghi log.
- Password đã bị copy vào backup ngoài phạm vi.
- Credential còn active tại target sau khi vault xóa bản lưu.
- Vault root/admin token bị lộ.

**Encryption cần đi kèm authorization, secure delivery, audit và revocation**, không phải là bằng chứng độc lập rằng secret đã an toàn.

## 13. Key custody, unseal và recovery

Một số hệ thống vault cần **seal/unseal** hoặc cơ chế tương đương để kiểm soát lúc khóa nền tảng có thể dùng giải mã dữ liệu. Tùy sản phẩm, cách triển khai có thể dùng **KMS auto-unseal, HSM, recovery key hoặc nhiều share dưới sự quản trị độc lập**.

### Các nguyên tắc

- Không lưu toàn bộ **unseal/recovery material** cùng một nơi không được bảo vệ.
- Phân tách người có quyền quản trị hạ tầng và người có khả năng khôi phục khóa theo SoD khi cần.
- Có **thủ tục khôi phục được kiểm thử**, không chỉ backup dữ liệu mã hóa.
- Giảm số lần người vận hành nhìn thấy key material.
- Chặn log, screenshot, ticket chứa recovery material.
- Kiểm quyền sửa **KMS key policy, vault auth method và audit configuration**.
- Xác định cách xử lý khi mất KMS access, khóa bị disabled hoặc HSM unavailable.
- Dùng thay đổi có phê duyệt và audit cho thao tác ảnh hưởng trust root.

### Backup được dữ liệu chưa chắc khôi phục được vault

Nếu chỉ sao lưu encrypted storage mà mất **khóa giải mã hoặc cấu hình trust/auth**, backup có thể không dùng được. Ngược lại, sao lưu cả ciphertext và recovery keys ở cùng chỗ có thể làm tăng tác động khi bị xâm nhập.

**Quy trình backup/DR phải kiểm thử phục hồi end-to-end**, nhưng không được biến môi trường thử nghiệm thành nơi chứa bản sao production secrets không được bảo vệ.

## 14. Secret engine: lưu static secret và phát dynamic credential

Có hai hình thức thường gặp:

| Kiểu | Cách hoạt động | Rủi ro chính |
|---|---|---|
| **Static secret storage** | Vault lưu một secret hiện có và trả lại khi principal được phép | Secret bị copy, rotation phải cập nhật target |
| **Dynamic credential issuance** | Vault hoặc backend tạo credential mới theo request/role | Phụ thuộc target API, lease/revocation và capacity |
| **Brokered access** | Vault/PAM đứng giữa điều phối thao tác mà user không thấy mật khẩu | Broker/session control cần bảo vệ |
| **Cryptographic operation as a service** | Client yêu cầu sign/decrypt mà không được xuất key | Policy trên operation/key phải chặt |
| **PKI/Certificate issuance** | CA/engine cấp certificate ngắn hạn theo profile | Mis-issuance, trust và revocation behavior |
| **Token exchange/federation** | Dùng workload assertion để nhận credential đích | Issuer/subject/audience trust quá rộng |

### Ví dụ static credential

Service dùng một credential database được quản trị trong vault. Vault kiểm quyền đọc và cung cấp phiên bản hiện hành. Khi xoay vòng, hệ thống phải **đổi mật khẩu tại database** và bảo đảm service dùng phiên bản mới.

### Ví dụ dynamic credential

Khi service cần đọc database, vault có thể dùng quyền backend được ủy quyền để tạo **DB user/credential tạm**, giới hạn role và TTL rồi phát cho service. Khi lease hết, vault cố gắng thu hồi credential tại database theo cơ chế engine hỗ trợ.

**Dynamic không tự đồng nghĩa an toàn tuyệt đối**: nếu role tạm có quyền quá rộng, secret bị lộ hoặc revocation backend thất bại, rủi ro vẫn tồn tại.

## 15. Static credential lifecycle

Một static secret thường đi qua:

~~~mermaid
flowchart TD
    P[Propose credential] --> OWN[Owner, target, scope and policy]
    OWN --> CREATE[Generate securely / create at target]
    CREATE --> STORE[Store protected version in vault]
    STORE --> USE[Authenticated workload fetch]
    USE --> ROT[Scheduled or risk-triggered rotation]
    ROT --> DEPLOY[Update consumers / target]
    DEPLOY --> VERIFY[Verify active credential and old one denied]
    VERIFY --> USE
    USE --> RETIRE[Retire service / revoke access]
    RETIRE --> DISABLE[Disable credential at target]
    DISABLE --> CLEAN[Remove copies, cache, vault entry as appropriate]
~~~

### Những bước quan trọng

1. Xác định **target account/role**, không chỉ đặt tên secret trong vault.
2. Sinh credential theo policy, tránh giá trị dùng chung hoặc dễ đoán.
3. Ghi vault metadata và owner mà không lưu password trong ticket.
4. Chỉ principal được phép mới có **read**.
5. Dùng rotation có phương án **rollback không mở rộng quyền**.
6. Kiểm những consumer nào vẫn phụ thuộc credential cũ.
7. Khi retire, **disable/delete credential tại target** trước hoặc cùng kế hoạch cleanup.
8. Kiểm target Deny với credential cũ trong phạm vi test an toàn.

**Xóa một key khỏi vault không thể xóa bản copy trước đó ở pod, CI artifact hoặc backup**. Khi cần cắt quyền, phải thu hồi tại nơi xác thực credential.

## 16. Dynamic credentials và quyền hạn của service

Một dynamic secret engine có thể phát **username/password database có hạn**, hoặc cloud credentials theo vai trò được duyệt.

### Luồng điển hình

~~~mermaid
sequenceDiagram
    participant APP as payments-api
    participant ID as Workload Identity
    participant V as Credential Vault
    participant DB as Database
    APP->>ID: Lấy workload assertion đúng audience
    ID-->>APP: Assertion thời hạn ngắn
    APP->>V: Authenticate với assertion
    V->>V: Check subject, path, role, lifecycle
    APP->>V: Request DB credential cho payments role
    V->>DB: Create restricted temporary database principal
    DB-->>V: Credential / account metadata
    V-->>APP: Credential + lease metadata (protected channel)
    APP->>DB: Query được phép
    V->>DB: Revoke/expire credential theo lease policy
    DB-->>V: Revoke outcome
~~~

### Ưu điểm

- Tránh nhiều services cùng chia sẻ một DB password.
- **Per-workload/per-lease identity** cải thiện khả năng truy vết.
- Thu hẹp thời gian credential còn hữu dụng.
- Có thể cấp đúng role cần thiết.
- Giảm nhu cầu mang permanent secret trong deployment.

### Giới hạn

- **Backend role mapping** phải chính xác: user tạm không nên có DBA role nếu chỉ cần đọc.
- Số lượng user/connection tại database có giới hạn; cần kế hoạch capacity.
- Lease expiry không đảm bảo **query đang chạy hoặc connection pool** tự bị ngắt theo mọi sản phẩm.
- Nếu engine không revoke được do network/permission lỗi, target credential có thể tồn dư.
- Cần xử lý service restart, renewal và credential refresh mà không tạo outage dây chuyền.

**Dynamic credentials tốt nhất khi đi kèm per-target authorization, reliable revocation và readback**.

## 17. Lease, TTL, renewal và revocation

**Lease** là cơ chế ghi nhận quyền sử dụng một secret/credential do vault cấp, thường kèm **lease ID, expiration, renewable flag và policy**.

### Những mốc khác nhau

| Mốc | Ý nghĩa |
|---|---|
| **IssuedAt** | Credential được phát hoặc trả về |
| **Vault token expiry** | Token cho phép client gọi vault hết hiệu lực |
| **Secret lease expiry** | Lease của credential do engine quản lý hết |
| **Target account expiry** | Target không còn chấp nhận credential |
| **Consumer cache expiry** | Ứng dụng không được dùng bản cache nữa |
| **Application session expiry** | Phiên ứng dụng/TLS/DB connection hết |
| **Owner relationship expiry** | Chủ thể người/workload không còn căn cứ |

**Các mốc không nhất thiết trùng nhau.** Ví dụ vault lease đã hết lúc 10:00 nhưng target chưa xóa DB user vì connector lỗi; connection pool còn hoạt động. Không được chỉ đọc trạng thái lease và kết luận quyền đã mất.

### Thao tác renewal

Một service có thể xin gia hạn lease khi còn quyền và backend hỗ trợ. Hệ thống phải kiểm **workload lifecycle, identity version và policy hiện hành** trước khi gia hạn; không biến một lease thành quyền vô hạn nhờ refresh liên tục.

### Revocation

- Revoke **vault login token**: chặn client tiếp tục gọi vault.
- Revoke **lease**: yêu cầu secret engine xử lý credential đích.
- Revoke **target account/API key**: nơi xác thực sẽ từ chối credential.
- Terminate **sessions/connections**: chặn các phiên đã dùng credential.
- Revoke **entitlement**: giảm permission hoặc role mà credential khai thác được.

**Đây là những tác vụ khác nhau**, cần xác minh theo năng lực của từng hệ thống.

## 18. Luồng lấy credential an toàn cho workload

Một workload nên dùng danh tính được nền tảng xác minh để lấy credential tạm.

~~~text
1. Workload instance được deploy từ nguồn đã phê duyệt.
2. Platform/issuer cấp workload assertion đúng audience.
3. Workload trình assertion tới vault qua TLS.
4. Vault xác minh issuer, signature, subject, audience và validity.
5. Vault map identity vào policy được duyệt.
6. Workload chỉ yêu cầu secret/role đúng phạm vi.
7. Vault kiểm path/action/tenant/environment/lifecycle.
8. Vault trả credential theo kênh bảo vệ và ghi audit metadata.
9. Workload dùng credential ở target với RBAC/ABAC riêng.
10. Khi hết lease/retire/incident, thu hồi credential và kiểm target.
~~~

### Điều không nên làm

- Embed **root token** hoặc wildcard cloud admin key trong image.
- Dùng cùng vault credential cho mọi pod trong cluster.
- Chuyển **raw vault token** qua URL query parameter.
- In response chứa private key vào CI logs.
- Cache secret trong local file không có ownership/TTL.
- Trust identity từ header hoặc environment do client tự khai.
- Cấp vault read vào **prod/** cho pipeline chỉ chạy staging.

**Authentication của workload và authorization của secret là hai kiểm tra riêng**. Một ServiceAccount hợp lệ chưa chắc được đọc database credential của service khác.

## 19. Secure delivery: secret được đưa vào ứng dụng thế nào?

Vault phải đưa secret tới consumer, và đó là **ranh giới rủi ro cao**.

| Phương thức | Ưu điểm | Rủi ro/giới hạn |
|---|---|---|
| **API fetch on demand** | Lấy secret lúc cần, quản lý TTL/version | Token/client SDK và network phải được bảo vệ |
| **Ephemeral file/volume** | Ứng dụng đọc như file, dễ reload | Quyền file, lifecycle mount, cleanup |
| **Sidecar/agent** | Chuyển auth/renewal/templating ra agent | Sidecar compromise, shared volume và token trust |
| **Environment variable** | Đơn giản, hỗ trợ ứng dụng legacy | Có thể lộ qua debug/process inspection/dump |
| **Kubernetes Secret sync** | Nhiều app dùng sẵn cơ chế Kubernetes | Secret trở thành bản sao có lifecycle/permission riêng |
| **In-memory integration** | Hạn chế ghi đĩa | Memory dump, XSS/bug trong process vẫn có rủi ro |
| **Brokered operation** | Không xuất credential khi có thể | Broker phải enforce action/SoD và audit |

### Một đường đi thường hợp lý

Workload dùng identity của platform để auth vault → agent/SDK nhận credential có TTL → cung cấp cho process qua **kênh ít lộ nhất mà ứng dụng hỗ trợ** → app làm mới trước khi expiry → target revoke hoặc đổi quyền khi hết căn cứ.

### Không có “secret hoàn toàn vô hình” sau khi đã trả cho ứng dụng

Nếu process có thể đọc secret thì code chạy trong process, debugger đặc quyền hoặc attacker chiếm process có thể sử dụng/đánh cắp secret. Cần **hardening, runtime isolation, permission, egress control, detection và rotation**.

## 20. Vault và Kubernetes: ServiceAccount, CSI và Kubernetes Secret

Trong Kubernetes, workload có thể dùng **bound ServiceAccount token** hoặc workload identity federation để xác thực với vault.

### Những cách tích hợp phổ biến

- **Vault agent/sidecar** lấy secret rồi ghi vào shared volume được kiểm soát.
- **Secrets Store CSI Driver/provider** mount secrets từ external store dưới dạng volume theo khả năng provider.
- **External Secrets operator** đồng bộ secret vào Kubernetes Secret.
- **Application SDK** tự gọi vault khi cần.
- **Workload identity + STS** để giảm nhu cầu static bootstrap token.

### Sơ đồ

~~~mermaid
flowchart LR
    POD[Pod: payments-api] --> SA[Projected SA token]
    SA --> V[Vault Auth Method]
    V --> P[Scoped Vault Policy]
    P --> AGENT[Agent / CSI / SDK]
    AGENT --> APP[App Credential Use]
    APP --> DB[(Target Database)]
    K8S[Kubernetes API / RBAC] --> AGENT
~~~

### Đặc biệt cần kiểm

1. Kubernetes **ServiceAccount** nào gắn với pod, thuộc namespace/cluster nào?
2. Vault có kiểm **issuer, audience và subject** của token không?
3. Pod nào được phép mount secret volume?
4. Người có quyền **read Kubernetes Secret** có thể đọc bản sao credential không?
5. Có kiểm **at-rest encryption của etcd**, Kubernetes RBAC và audit khi dùng Secret không?
6. Reload/rotation từ external vault sang pod có được thực hiện đúng?
7. Khi pod bị xóa, **target credential có bị revoke** hay vẫn còn?
8. Workload staging có thể đọc secret production do policy wildcard không?
9. Admission policy có ngăn pod tùy ý gắn ServiceAccount privileged không?
10. Secret trong volume có bị backup/snapshot ngoài ý muốn không?

**Kubernetes Secret không tự tương đương credential vault hoàn chỉnh.** Nó là đối tượng dữ liệu nhạy cảm trong Kubernetes, có thể được mã hóa tại rest và kiểm bằng RBAC, nhưng yêu cầu rotation, ownership, external target revocation và audit bổ sung tùy hệ thống.

## 21. Vault trong CI/CD: tránh secrets trong pipeline logs

Pipeline thường cần token để **pull private dependencies, sign artifact hoặc deploy**. Đây là nơi có rủi ro lộ secret qua logs, build artifacts và runner.

### Mô hình kiểm soát

1. CI platform phát assertion cho **job identity** với claims đáng tin.
2. Vault kiểm **issuer, audience, repository, workflow, ref/environment** theo chính sách.
3. Job được cấp secret hoặc credential **chỉ cho bước cần dùng**.
4. TTL không vượt nhu cầu công việc.
5. Secret không bị in ra logs, set -x, exception stack hoặc upload vào artifact.
6. Runner được tách biệt giữa **trusted deploy jobs** và **untrusted pull requests**.
7. Sau job, credential hết hạn/được revoke theo target capability.
8. Audit liên kết request với pipeline/job/commit và actor có thẩm quyền.

### Ví dụ policy khái niệm cho deploy pipeline

~~~yaml
policyId: deploy-payments-prod
principal:
  issuer: https://ci.example.org/oidc
  subject: repo:example/payments:environment:production
  audience: vault.production.example.org
allowed:
  - action: generateCredential
    resource: teams/payments/prod/deploy
conditions:
  trustedEnvironment: production
  approvedWorkflow: deploy-payments
  ttlSecondsMax: 900
  changeApprovalRequired: true
~~~

Policy chỉ **minh họa**, không phải cú pháp của GitHub Actions, GitLab CI hoặc một sản phẩm vault. Thực tế phải xác minh claim nào **được issuer ký và bảo đảm**; không tin input workflow tự khai.

### Rủi ro đặc biệt của fork/PR

Một pull request không tin cậy có thể chạy code của attacker. Nếu job đó được phép lấy production credential, vault đã thành nơi cấp quyền cho code không đáng tin. **Phải chặn ở identity claim/trust policy và pipeline permission**, không chỉ ẩn secret khỏi log.

## 22. OAuth, OIDC và token trong credential vault

Một integration có thể dùng:

- **OAuth client secret** để xác thực confidential client.
- **Private-key JWT signing key** thay cho shared client secret khi phù hợp.
- **Refresh token** để xin access token mới.
- **Access token** ngắn hạn để gọi API.
- **OIDC ID token** trong login federation, thường không cần vault lưu như credential dùng chung.

### Phân biệt token cần lưu với token cần phát theo yêu cầu

| Loại | Chiến lược phù hợp theo use case |
|---|---|
| **OAuth client secret** | Lưu trong vault, rotate/revoke tại authorization server |
| **Private-key JWT key** | Giữ trong KMS/HSM/vault-backed signing khi có thể |
| **Refresh token** | Bảo vệ mạnh; rotation, reuse detection, revocation và client binding |
| **Access token** | TTL ngắn; cache có kiểm soát, không chia sẻ qua logs |
| **ID token** | RP validate đúng issuer/audience; không dùng như API bearer |
| **Vault access token** | TTL/scope riêng, không coi là app user token |

### Một ví dụ quan trọng

Vault xóa **refresh token của connector CRM**, nhưng authorization server chưa nhận revocation. Nếu attacker đã lấy bản sao trước đó, họ có thể tiếp tục xin access token mới **nếu AS vẫn chấp nhận token**.

Do đó **xóa bản lưu không phải revoke ở issuer**. Tương tự, thu hồi refresh token không tự làm mọi access token còn hạn mất giá trị ở resource server. Phải xét **token family, rotation, introspection, audience, expiry và resource-side authorization**.

### ID token khác access token

**OIDC ID token** chủ yếu dùng cho client xác minh authentication event; không nên gửi tới API như bearer credential tùy tiện. OAuth access token dùng cho resource server và vẫn phải kiểm **scope, audience và quyền trên từng resource**.

## 23. PKI, SSH và private keys trong vault

Credential vault có thể quản lý hoặc tích hợp với **Certificate Authority/PKI, KMS, HSM hoặc SSH certificate service**.

### Các phương án

| Use case | Cách tiếp cận | Điều phải kiểm |
|---|---|---|
| **TLS/mTLS private key** | Local non-exportable key, vault/KMS-backed key hoặc cert issuance | SAN/EKU, identity, key protection |
| **X.509 certificate** | CA phát certificate theo CSR/attestation | Enrollment authorization và expiry |
| **SSH automation** | SSH certificate ngắn hạn hoặc key pair được quản trị | Host/user principal, TTL, authorized role |
| **Code signing** | Private signing key trong HSM/KMS/vault-backed crypto | SoD, artifact provenance, audit |
| **Encryption key** | KMS/HSM/key engine | Key usage, version, rotation và access policy |

### Certificate không phải secret theo cùng nghĩa private key

Một certificate leaf thường chứa **public key và metadata**; private key đi kèm mới là bí mật cần bảo vệ đặc biệt. Không nên lưu private key sản xuất dưới dạng file tải lên tùy tiện nếu có thể sinh/giữ key trong phần cứng hoặc nơi sử dụng.

### PKI issuance khác secret fetch

Một workload có thể **gửi CSR** để nhận certificate mà **không cần đưa private key lên vault**. Cơ chế tốt hơn khi phù hợp là giữ private key tại workload/hardware và chỉ trao public key/CSR cho CA. Vault có thể quản lý policy, issuer và certificate lifecycle nhưng không nhất thiết phải nắm key của mọi service.

### Thu hồi

Khi certificate bị revoke, cần kiểm **CRL/OCSP hoặc trust/authorization controls**, cùng TLS connections đã thiết lập. Với SSH certificate, kiểm trusted CA/principals/expiry và phiên đang mở. **Xóa private key khỏi vault không tự ngắt mọi kết nối**.

## 24. Credential vault và PAM/JIT

**Privileged Access Management (PAM)** thường dùng credential vault để bảo vệ tài khoản đặc quyền và giới hạn phiên truy cập.

### Những chế độ điển hình

| Chế độ | Cách hoạt động | Mức phơi nhiễm credential |
|---|---|---|
| **Credential checkout** | Người dùng được duyệt lấy password/key trong thời gian hạn chế | Người dùng có thể nhìn thấy và copy |
| **Brokered session** | PAM dùng credential ở backend, user vào qua broker | Có thể giảm việc user thấy secret |
| **Password rotation after use** | Đổi credential sau checkout/session | Giảm khả năng dùng lại |
| **JIT/PIM activation** | Kích hoạt role có thời hạn theo policy | Có thể tránh standing credential |
| **Break-glass access** | Đường khẩn cấp được kiểm soát trước | Đòi alert, giới hạn và post-review |

### Phân tách nhiệm vụ

- Người **request** quyền không nên tự là người **approve** nếu SoD cấm.
- Người có quyền **edit vault policy** không mặc nhiên có quyền **read all secrets**.
- Người quản trị CA/root key không nên tự vượt kiểm soát phê duyệt.
- Security approver đánh giá risk/guardrail; resource owner xác minh nhu cầu.
- Auditor có thể xem **metadata/audit** mà không được lấy credential.

### Một phiên PAM đã đóng có nghĩa secret an toàn chưa?

Nếu password đã được user nhìn thấy hoặc copy trước đó, **chỉ đóng PAM session** không chứng minh password cũ không còn dùng được. Có thể cần **rotate/revoke target password**, đóng local SSH/RDP/DB sessions và xác minh quyền.

## 25. Break-glass: truy cập khẩn cấp khi vault/IdP không hoạt động

**Break-glass** là cơ chế dự phòng cho tình huống cần phục hồi hạ tầng nhưng đường đăng nhập thông thường bị lỗi.

### Những mục tiêu cần cân bằng

- **Có khả năng khôi phục** khi IdP, vault cluster hoặc network gặp sự cố.
- **Không tạo đường hậu cửa thường trực**.
- Có **owner, approver hoặc kiểm soát nhiều người** khi phù hợp.
- Có **thời hạn sử dụng, cảnh báo, audit và post-incident review**.
- Credential được bảo vệ, có quy trình rotation sau khi dùng.
- Được kiểm thử định kỳ trong điều kiện giả lập sự cố.

### Ví dụ

Vault production bị gián đoạn và cần khởi động lại thành phần lưu khóa. Nhóm Security đã thiết kế trước cơ chế **recovery credentials được quản trị riêng**. Người được ủy quyền thực hiện theo runbook, có ghi nhận actor và lý do. Khi dịch vụ phục hồi, nhóm **reconcile, rotate các credential đã lộ nếu cần, thu hồi quyền tạm và kiểm tra audit**.

**Không dùng một root token dán trong wiki công khai làm “break-glass”**. Cũng không để cơ chế khẩn cấp phụ thuộc hoàn toàn vào chính IdP/vault đang hỏng nếu mục tiêu là khôi phục khi các dịch vụ đó ngừng.

## 26. Rotation: không gián đoạn nhưng không giữ secret cũ vô hạn

**Rotation** là thay credential/secret theo lịch, khi owner thay đổi, nghi bị lộ hoặc theo chính sách.

### Một quy trình an toàn cho static database password

~~~mermaid
flowchart TD
    START[Rotation scheduled or risk-triggered] --> PRE[Verify target, owner, consumers]
    PRE --> CREATE[Create new credential / second account if supported]
    CREATE --> STORE[Store new version securely]
    STORE --> ROLL[Roll out to consumers]
    ROLL --> TEST[Test connectivity and required permissions]
    TEST -->|Pass| CUT[Disable old credential at target]
    TEST -->|Fail| FIX[Diagnose without logging secret]
    FIX --> ROLL
    CUT --> OBS[Readback / negative test old credential]
    OBS --> CLEAN[Expire old cache and controlled cleanup]
~~~

### Những điểm cần quyết định

1. Target có hỗ trợ **hai credential song song** không?
2. Nếu chỉ có một password, làm sao tránh outage giữa lúc target đổi và app reload?
3. Có **connection pool hoặc job lâu dài** còn dùng credential cũ không?
4. Secret mới có **đúng permission** như desired state, không vô tình rộng hơn?
5. Có kế hoạch rollback nhưng **không phục hồi credential đã bị compromise**?
6. Owner/Security có cần phê duyệt khi đổi production signing key?
7. Khi nào phải cắt credential cũ và kiểm nó không còn usable?
8. Có audit từ rotation event đến verification không?

### Rotation không đồng nghĩa revoke

Rotation có thể tạo **phiên bản mới** mà credential cũ vẫn đang active. Nếu cutover không có bước **disable/revoke tại target**, tồn tại đồng thời nhiều chìa khóa có thể làm tăng attack surface.

### Xoay vòng signing key

Với JWT signing keys hoặc certificate trust, cần **key identifier, distribution window, token TTL và verification behavior**. Không xóa public verification key ngay khi còn token hợp lệ cần xử lý; nhưng cũng không giữ private signing key cũ quá lâu hoặc tiếp tục ký bằng key đã compromise.

## 27. Secret versioning, rollback và concurrency

Một vault lưu static secret có thể giữ nhiều **versions** phục vụ rotation, recovery hoặc kiểm toán.

### Metadata cần phân biệt

- **Current version:** bản ứng dụng nên lấy.
- **Previous version:** bản trước, có thể còn cần trong cutover.
- **Disabled/deleted version:** vault không cho fetch theo policy.
- **Destroyed version:** dữ liệu phiên bản bị phá hủy nếu sản phẩm hỗ trợ.
- **Target state:** credential tương ứng có còn active ở database/SaaS không?
- **Consumer observed version:** phiên bản ứng dụng đã nhận và đang dùng.
- **Rotation generation:** mốc chống job cũ ghi đè phiên bản mới.

### Lỗi rollback nguy hiểm

- 09:00 phát hiện key cũ bị lộ, rotation sang version 8.
- 09:05 target thu hồi version 7.
- 09:10 một deployment rollback lấy **version 7** từ cache/backups.
- 09:11 app bị lỗi hoặc, tệ hơn, hệ thống được cấu hình lại để kích hoạt key cũ.

**Rollback application không được tự rollback security state**. Cần ràng buộc version, target revocation và policy trước khi tái triển khai.

### CAS/optimistic concurrency

Khi hai rotation jobs cùng cập nhật secret, nên có cơ chế **compare-and-set/version check** theo khả năng sản phẩm, tránh lost update hoặc đưa phiên bản cũ thành current.

## 28. Revocation: xóa secret khỏi vault chưa phải thu hồi credential

Khi thu hồi cần xác định **tại đâu credential được xác thực và quyền được thực thi**.

| Đối tượng thu hồi | Tác động | Những bước còn phải làm |
|---|---|---|
| **Vault token** | Không cho principal gọi vault với token đó | Kiểm secret đã lấy, lease đã phát |
| **Vault ACL/policy** | Ngăn các thao tác vault mới | Credential cũ ở target có thể còn |
| **Static API key entry** | Vault không trả key nữa | Revoke key tại SaaS/API issuer |
| **Database user/password** | Target từ chối login mới | Xử lý connection/session còn sống |
| **Dynamic lease** | Engine yêu cầu revoke target credential | Readback target thực tế, kiểm lỗi |
| **OAuth refresh token** | AS không cấp access token mới | Xử lý access token còn hạn |
| **OAuth access token** | RS phải từ chối theo cơ chế | Introspection/denylist/short TTL theo kiến trúc |
| **TLS/SSH private key** | Không còn phát/đọc key ở vault | Revoke certificate, trust/authorized_keys, session |
| **Cloud role** | Quyền hiện hành bị gỡ | Credential/session đã assume có thể còn hiệu lực |
| **Human vault entitlement** | Người không được lấy secret mới | Rotate những secret người đó có thể đã biết |

### Nguyên tắc đánh giá thành công

**Revocation success** phải dựa trên **observed access ở đích**, không chỉ task queue, API acknowledgment hoặc bản ghi vault.

Ví dụ, nhân viên đã Leaver từng đọc production API key. Dù vault policy bị gỡ ngay, bản sao key vẫn có thể dùng tới khi **SaaS issuer revoke key và resource server từ chối request**. Do vậy, **Leaver có thể kéo theo rotation và target revocation** theo rủi ro.

## 29. Vault và vòng đời Joiner–Mover–Leaver của người dùng

### Joiner

Khi một nhân viên gia nhập:

1. HRIS/contract source xác định **personId, relationshipId, department và effectiveAt**.
2. IdP/SSO và MFA được enrollment theo chính sách.
3. IAM cấp quyền **vault metadata/read/rotate** theo nhiệm vụ, không cấp root access mặc định.
4. Chỉ cho quyền production secret nếu có **business/security approval** cần thiết.
5. SoD kiểm xung đột **được xin/duyệt/đọc/chỉnh policy**.
6. Audit ghi việc cấp entitlement, không gửi secret qua email onboarding.

### Mover

Khi đổi vai trò/đội:

- Thu hồi quyền đối với namespace và secret cũ.
- Cập nhật ownership của secret nếu nhiệm vụ chuyển giao.
- Rà soát những secret người cũ có thể đã từng đọc.
- Nếu cần, **rotate target credentials** để chấm dứt khả năng dùng bản sao.
- Cấp quyền mới qua access request/approval hợp lệ.
- Không để role cũ và mới tích lũy thành quyền đọc cả hai miền production không cần thiết.

### Leaver

Khi quan hệ chấm dứt:

1. **Disable IdP/SSO**, ngừng quyền đăng nhập mới.
2. Revoke **vault sessions/tokens, policy grants và credential checkout** thuộc quan hệ cũ.
3. Xác định các production secrets mà người đó **có thể đã đọc hoặc xuất**.
4. Rotate/revoke tại **target** theo risk và khả năng, không chỉ xóa vault ACL.
5. Đóng PAM/JIT sessions, xử lý API key/SSH key đã cấp riêng.
6. Chuyển ownership và escalation cho hệ thống hợp lệ còn hoạt động.
7. Reconcile quyền còn tồn dư ở vault, ứng dụng, cloud và local systems.

### Rejoiner và nhiều quan hệ

Một người quay lại không tự lấy lại quyền đọc vault của quan hệ cũ, kể cả dùng cùng email. Cần dựa trên **stable personId và relationshipId mới**. Nếu một người có nhiều hợp đồng, permission phải gắn đúng căn cứ và không được lẫn giữa các tenant/quan hệ.

**Leaver của người quản trị không đồng nghĩa xóa toàn bộ secrets của service production**. Cần cắt quyền người đã rời, trong khi workload hợp lệ được duy trì dưới owner mới và credential được bảo vệ.

## 30. Workload lifecycle: Create–Change–Retire và owner handoff

**Workload identity** như microservice, bot, pipeline hoặc device có vòng đời kỹ thuật riêng:

| Sự kiện | Tác vụ ở vault | Tác vụ ở target |
|---|---|---|
| **Create/Register** | Gắn workload ID, owner, allowed paths | Tạo role hẹp, secret cần thiết |
| **Activate** | Cho phép auth từ issuer đáng tin và issue credential | Permit đúng action/resource |
| **Scale/Redeploy** | Token/lease ngắn hạn cho instance mới | Không mở quyền global vì scale |
| **Change scope** | Review policy, remove old path, versioning | Cập nhật target permissions |
| **Owner Mover** | Chuyển owner/approval route, review secret exposure | Xác minh workload còn cần quyền |
| **Owner Leaver** | Thu hồi human access và rotate khi cần | Không xóa bừa service đang chạy |
| **Suspend/Compromise** | Chặn token/lease issuance | Deny action rủi ro và revoke creds |
| **Retire** | Disable auth binding, stop renewal, cleanup versions | Drop account/revoke API keys, close sessions |
| **Recreate with new identity** | Enrollment và approval mới | Không tái sử dụng quyền mặc định của workload cũ |

### Sai lầm thường gặp

Workload đã **RETIRED** nhưng một automation job từ manifest cũ tiếp tục tạo **token vault mới** và tái cấp DB account. Cần kiểm **current source version, generation/fencing và idempotency** trước khi grant/renew.

### Quyền quản trị human khác quyền runtime workload

Một kỹ sư có thể là owner của payments-api nhưng không cần đọc raw production DB password. Workload có quyền tạo database credential, còn con người chỉ có quyền **review policy/rotate/diagnose** theo SoD.

## 31. IdP, SSO, SCIM và access review trong quản trị vault

### IdP/SSO

IdP xác thực người dùng quản trị vault, có thể truyền group và assurance. Nhưng **IdP session còn active không chứng minh user còn được đọc secret** sau Mover/Leaver. Vault cần cập nhật policy và chấm dứt sessions theo cơ chế được hỗ trợ.

### SCIM provisioning

SCIM đồng bộ **User/Group** với ứng dụng hỗ trợ. Một vault product có thể tích hợp nhóm/entitlement theo cơ chế riêng, nhưng **SCIM không phải giao thức quản lý bí mật hay revoke API keys ở mọi target**. Việc disable SCIM User ở SaaS không tự cắt vault token đã phát cho automation.

### Access request

Quyền đọc production secret có thể cần manager approval, resource owner approval và Security approval. Một yêu cầu hợp lệ nên ghi rõ **secret category, mục đích, phạm vi, thời hạn và cách thu hồi**.

### Access review

Định kỳ xác nhận:

- Ai còn quyền **read/list/write/rotate** secret?
- Những workload nào vẫn được cấp token/lease?
- Secret nào đã lâu không sử dụng hoặc thiếu owner?
- Có quyền root/wildcard hoặc cross-tenant không?
- Secret có bản sao ở local/CI/Kubernetes không?
- Các ngoại lệ access có còn hiệu lực?
- Credential đã bị retire ở vault nhưng vẫn active ở target không?

**Review decision RETAIN không được tái cấp vault access đã bị Leaver thu hồi**. Phải kiểm version và relationship hiện hành.

## 32. SoD, approval và chính sách ngoại lệ

Credential vault chứa những tài sản có thể mở quyền cao, nên cần phân tách nhiệm vụ phù hợp.

### Một số cặp quyền nhạy cảm

| Tổ hợp | Rủi ro | Kiểm soát |
|---|---|---|
| **editVaultPolicy + approveOwnPolicy** | Tự mở rộng quyền | Independent review/SoD |
| **manageKMSKey + disableAudit** | Che hành vi tác động khóa | Guardrails và audit bất biến |
| **checkoutRootCredential + approveOwnCheckout** | Tự truy cập root ngoài kiểm soát | PAM approval độc lập |
| **modifyTargetAccount + certifyOwnAccess** | Tự tạo và hợp thức hóa grant | Resource owner certification |
| **editCIWorkflow + readProdDeploySecret** | Code không tin cậy lấy secret | Trust-bound CI identity và SoD |
| **issueSigningKey + publishArtifact** | Bỏ qua kiểm soát release | Signing approval và provenance |

**Một tổ hợp chỉ là SoD conflict khi policy quy định theo scope và trách nhiệm tương ứng**. Không phải mọi cặp hành động gần nhau đều phải cấm tuyệt đối.

### Exception có kiểm soát

Một exception cần:

- **Risk owner/approver** hợp lệ.
- **Subject, secret scope, target action và thời hạn**.
- Lý do nghiệp vụ và vì sao không thể dùng giải pháp hẹp hơn.
- **Compensating controls**: session broker, dual control, enhanced audit, JIT.
- Cơ chế **automatic expiry/review**.
- Xác minh không vượt hard security guardrails.

**PENDING_EXCEPTION không được coi là APPROVED**. Và exception hết hạn không thể bị job cũ tự kéo dài chỉ vì secret vẫn tồn tại.

## 33. Audit: ai đọc secret và việc đó có tác động gì?

Một bản ghi audit vault hữu ích nên mô tả:

- **Actor identity**: personId hoặc workloadId và nhóm owner.
- **Authentication method** và assurance đủ để điều tra, không lưu raw credential.
- **Action**: read/list/generate/renew/revoke/modifyPolicy.
- **Secret ID/path**, namespace, tenant, version/role.
- **Lease metadata** hoặc operation reference khi phù hợp.
- **Policy version và decision** Permit/Deny.
- **Timestamp, correlation ID, origin metadata** theo privacy policy.
- **Target outcome** từ connector nếu có.
- **JML source event/version** khi revoke do Mover/Leaver.
- **Exception/approval reference** nếu được áp dụng.

### Event JSON minh họa

~~~json
{
  "eventId": "vault-audit-20261123-042",
  "eventType": "DynamicCredentialIssued",
  "principalId": "service:payments-api",
  "ownerTeamId": "payments-platform",
  "authenticationMethod": "WORKLOAD_OIDC",
  "secretRole": "payments-db-writer",
  "vaultPath": "teams/payments/prod/db/writer",
  "targetSystem": "payments-db",
  "tenantId": "org-vn",
  "leaseReference": "lease-audit-reference-not-a-token",
  "ttlSeconds": 1800,
  "policyVersion": "payments-db-access-v5",
  "decision": "PERMIT",
  "occurredAt": "2026-11-23T09:10:00+07:00",
  "correlationId": "corr-vault-2c19"
}
~~~

Đây là **schema minh họa**, không phải event chuẩn của một sản phẩm cụ thể. **leaseReference** không phải lease token có thể dùng làm bí mật. Audit không được chứa **raw password, API key, token, private key, one-time bootstrap material hoặc response body chứa secret**.

### Audit phải được bảo vệ

- Giới hạn quyền đọc và chỉnh log.
- Có tamper-evidence hoặc cơ chế chống sửa khi cần.
- Tránh cho một vault admin có thể **tắt audit mà không có dấu vết**.
- Retention theo yêu cầu, hạn chế PII.
- Đối soát audit với **target activity** để biết credential đã được dùng làm gì.

**Audit “vault đã trả secret” không đồng nghĩa target đã chấp nhận secret**, và cũng không chứng minh chỉ một process dùng bản copy đó sau khi lấy ra.

## 34. Threat model: các đường tấn công thường gặp

| Mối đe dọa | Biểu hiện | Kiểm soát |
|---|---|---|
| **Root token leakage** | Root token trong CI/log | Không embed, scoped auth, short TTL, incident rotation |
| **Wildcard ACL** | Một service đọc cả prod secrets | Path/action/tenant least privilege |
| **Auth method spoofing** | Client tự khai workload ID | Verify issuer/subject/audience/attestation |
| **Privilege escalation** | Read policy rồi sửa role để lấy secret | SoD, policy admin separation |
| **Secret exfiltration** | App in key vào log/artifact | Redaction, egress control, secret scanning |
| **Compromised workload** | Pod hợp lệ lấy secret để attacker dùng | Short-lived creds, runtime isolation, detection |
| **Static key reuse** | Nhiều apps dùng cùng key | Per-workload/per-target identity |
| **KMS key misuse** | Attacker sửa wrapping/key policy | KMS/HSM guardrails và audit |
| **Vault storage theft** | Copy encrypted storage + key access | Encryption/key separation, access control |
| **Snapshot/backup exposure** | Backup chứa plaintext/unseal key | Encrypted backups, scoped restore |
| **Secret version rollback** | App dùng lại compromised key | Generation/version checks |
| **Token replay** | Vault token/JWT được dùng lại | TTL, token binding khi hỗ trợ, detection |
| **SSRF/metadata abuse** | App lấy workload credential qua metadata | SSRF defense, platform metadata protection |
| **Cross-tenant read** | Identity tenant A lấy prod secret tenant B | Tenant-aware authorization |
| **Policy drift** | Role mới có quyền rộng hơn catalog | Reconciliation và policy tests |
| **Stale lease** | Vault báo expired, DB user vẫn active | Target readback và remediation |
| **Audit suppression** | Admin tắt audit để che checkout | Independent logging, SoD |
| **Untrusted CI code** | Fork PR dùng production credentials | Trust claims, environment approval |
| **Owner Leaver** | Người nghỉ còn bản sao key | Target rotation/revoke theo exposure risk |
| **Orphan secret** | Không owner, không ai chịu rotation | Inventory, ownership review, controlled retirement |

### Một secret bị lộ tạo hai câu hỏi riêng

1. **Credential có thể bị dùng để xác thực ở đâu?** Database, cloud, API, CA hay vault?
2. **Credential cho phép action gì trong phạm vi nào?** Read, write, admin, rotate, grant, export?

Phải xử lý **cả credential validity và target permissions**, không chỉ xóa bản sao đã thấy.

## 35. Backup, high availability và disaster recovery

Credential vault là hạ tầng nhạy cảm và thường có thể ảnh hưởng hàng loạt services.

### Kiến trúc vận hành cần xem xét

- **High availability** cho auth, policy, secret engine và storage.
- Cấu hình multi-zone/region hoặc DR theo RTO/RPO có phê duyệt.
- Đồng bộ/replication của dữ liệu bí mật với phạm vi và quyền truy cập rõ.
- Backup encryption và **quản lý khóa khôi phục độc lập**.
- Khả năng restore **policy/auth methods/metadata** phù hợp với secret data.
- Vault token/lease consistency sau failover.
- Quota/rate limit, retry/backoff tránh thác lỗi.
- Network segmentation và hạn chế privileged administration.
- Kiểm thử khôi phục trong môi trường bảo vệ, không lộ production secrets.

### Những câu hỏi DR quan trọng

1. Khi vault unreachable, workload **tiếp tục bằng credential đã cache được bao lâu**?
2. Nếu cache hết TTL, hệ thống fail-closed hay có break-glass đã được kiểm soát?
3. Khi restore snapshot cũ, có **khôi phục secret đã bị revoke** hoặc policy đã bị loại bỏ không?
4. Lease được phát trước failover có còn được quản lý/revoke đúng không?
5. Nếu KMS/HSM key không còn, backup có khả năng giải mã không?
6. Môi trường DR có được tin cậy để xử lý production credentials không?
7. Có test **Deny sau revocation** sau khi khôi phục không?

**Restore dữ liệu vault không được coi như rollback authorization state**. Hệ thống cần reconcile với source JML, credential issuer/target và rotation generation hiện hành trước khi cho truy cập.

## 36. Failure modes: khi vault hoặc target không khả dụng

| Sự cố | Tác động | Cách xử lý |
|---|---|---|
| **Vault down** | App không lấy secret mới | HA/DR, bounded cache, fail-safe behavior |
| **IdP down** | Human không đăng nhập vault | Recovery procedure được phê duyệt |
| **OIDC issuer outage** | Workload không lấy assertion | Retry/backoff, tránh shared root fallback |
| **Target API down lúc rotate** | Không đổi được credential | Giữ operation pending, readback sau |
| **Target revoke fails** | Credential trái policy còn usable | Finding, chặn target resource, escalate |
| **Lease refresh fails** | App có thể mất kết nối | Renewal jitter/backoff, restart-aware handling |
| **KMS disabled** | Vault không giải mã được dữ liệu | KMS policy, DR tests, security incident protocol |
| **Bad policy rollout** | Nhiều workloads bị Deny hoặc quá rộng | Versioned policy, canary và audit |
| **Certificate expires** | mTLS đến vault thất bại | Rotation/monitoring, không tắt TLS validation |
| **Secret cache stale** | App dùng credential cũ | Version check, refresh và forced invalidation |
| **Clock skew** | Token/lease bị coi hết hạn sai | Time synchronization và bounded skew |
| **Rate limit 429** | Retry storm | Backoff, circuit-breaker phù hợp |
| **Unknown outcome after timeout** | Không rõ credential đã tạo/revoke chưa | Idempotency và target readback |

### Cách xử lý khi chưa biết thao tác thành công chưa

Nếu vault gửi yêu cầu tạo DB user và mất kết nối trước khi có response, **không retry mù quáng** với tên user mới mỗi lần. Cần operation/correlation ID, kiểm target state, xác định có principal đã được tạo và xử lý kết quả không rõ theo runbook.

### Chống fallback nguy hiểm

Khi vault lỗi, không tự chuyển app sang **database superuser key có trong image**. Một fallback như vậy có thể biến sự cố availability thành vi phạm bảo mật nghiêm trọng.

## 37. Reconciliation: vault desired state so với target access

Một hệ thống có thể đồng thời có:

- **Desired secret state:** secret nào được phép tồn tại theo catalog/JML/policy.
- **Vault state:** version/token/lease/policy nào đang active.
- **Consumer state:** pod/job/app đang giữ bản copy/version nào.
- **Target state:** tài khoản, API key, role và session nào vẫn có hiệu lực.
- **Runtime observed access:** action nào còn được Permit.

~~~mermaid
flowchart TD
    DES[Desired State: IAM / Workload Registry] --> REC[Reconciliation Engine]
    VA[Vault: Paths / Versions / Leases] --> REC
    CONS[Consumers: Active Secret Versions] --> REC
    TAR[Target: DB / Cloud / SaaS / PKI] --> REC
    REC --> DIFF{Matches policy?}
    DIFF -->|Yes| VERIFIED[Verified]
    DIFF -->|No| FIND[Finding with owner, severity, SLA]
    FIND --> REM[Revoke / Rotate / Narrow / Investigate]
    REM --> REC
~~~

### Những loại sai lệch

| Finding | Ví dụ | Hành động |
|---|---|---|
| **ORPHAN_SECRET** | Không có owner còn active | Điều tra, chuyển owner hoặc retire |
| **OVERPRIVILEGED_VAULT_POLICY** | CI staging đọc prod credentials | Thu hẹp policy |
| **VAULT_TOKEN_AFTER_LEAVER** | Token thuộc người nghỉ còn được chấp nhận | Revoke token và kiểm secret exposure |
| **EXPIRED_LEASE_ACTIVE_TARGET** | DB user vẫn login sau lease expiry | Revoke ở DB, kiểm root cause |
| **REVOKED_KEY_STILL_ACCEPTED** | SaaS API key vẫn gọi được | Revoke tại issuer/target |
| **STALE_CONSUMER_VERSION** | Pod dùng version 4 sau rotation version 5 | Refresh/redeploy và deny old credential |
| **UNKNOWN_API_KEY** | Key active tại SaaS không nằm trong inventory | Owner mapping/incident |
| **CROSS_TENANT_SECRET** | Workload tenant A lấy secret tenant B | Chặn policy, review scope |
| **ROOT_TOKEN_UNTRACKED** | Token đặc quyền thiếu owner/audit | Incident/rotation/root governance |
| **CI_ARTIFACT_SECRET_COPY** | Raw token nằm trong artifact | Revoke và xóa bản sao, điều tra |
| **RESTORED_REVOKED_VERSION** | Snapshot cũ chứa secret đã rotate do compromise | Không tái kích hoạt target credential |
| **PAM_CHECKOUT_NOT_ROTATED** | Password dùng sau checkout còn nguyên | Rotation và session review |

**Không thể khẳng định reconciliation hoàn chỉnh nếu target API không cung cấp inventory/readback.** Phải ghi rõ coverage, độ tươi dữ liệu và compensating controls.

## 38. Chỉ số, cảnh báo và quản trị vận hành

| Chỉ số | Ý nghĩa | Điều cần tránh |
|---|---|---|
| **Secrets with valid owner** | Tỷ lệ secret có owner còn active | Gán owner hình thức |
| **Long-lived static credentials** | Số static keys không được thay định kỳ | Tăng TTL để giảm cảnh báo |
| **Dynamic credential adoption** | Mức sử dụng per-lease credentials | Không kiểm quyền role tạm |
| **Rotation success and verified cutover** | Secret mới được dùng, secret cũ bị Deny | Chỉ tính vault write success |
| **Outstanding revocation failures** | Những credential đích chưa cắt | Đóng finding theo tuổi ticket |
| **Expired lease target mismatches** | Khoảng trống lease và DB/cloud state | Tin metadata vault một mình |
| **Cross-environment access denies** | Chặn staging → prod | Không kiểm bypass khác |
| **Overprivileged policies** | Wildcard/root-like ACL | Chỉ đếm role name |
| **Unauthorized fetch attempts** | Dấu hiệu truy cập trái phép | Có thể do config sai, cần triage |
| **Owner JML handoff backlog** | Secret thiếu owner sau Mover/Leaver | Xóa service còn hợp lệ |
| **Secret exposure findings** | Lộ trong Git/log/backup | Không chỉ xóa file; phải revoke |
| **Time to revoke after Leaver** | Từ effectiveAt đến target Deny | Chỉ đo IdP disable |
| **Vault auth failure rate** | Workload/IdP trust lỗi | Không tắt auth để giảm lỗi |
| **Audit coverage** | Trace từ read/lease tới target action | Không log raw secret |
| **DR restore verification** | Có thể restore an toàn và giữ revocation | Restore bản sao secret cũ không kiểm |
| **Secrets without expiry/review** | Credential không có lifecycle | Không phải tất cả đều có cùng TTL |

### Chỉ số phải phản ánh rủi ro thật

Một dashboard có **100% secrets encrypted** chưa đủ nếu production root token được mọi service đọc. Cần kết hợp **coverage, least privilege, target revocation, audit, owner và negative tests**.

## 39. Kiểm thử credential vault và secret lifecycle

| Test case | Tình huống | Kết quả mong đợi |
|---|---|---|
| **Human SSO active** | Nhân viên đủ quyền và MFA | Chỉ được action/path được phép |
| **Human Leaver** | Quan hệ đã kết thúc | Không đăng nhập/đọc secret mới |
| **Workload OIDC valid** | Đúng issuer, subject, audience | Đi tiếp vault policy, không auto root |
| **Wrong audience** | Token dành API khác gửi vault | Deny |
| **Wrong namespace** | reports-job xin payments/prod | Deny |
| **Staging → production** | CI staging xin prod secret | Deny |
| **List vs Read** | Principal chỉ được list | Không đọc raw credential |
| **Policy admin != secret read** | Operator chỉnh health config | Không đọc bí mật nếu policy cấm |
| **Vault token expired** | Token đã quá TTL | Không cấp thêm secret |
| **Secret lease expired** | DB user hết hạn | Target thực sự từ chối login |
| **Rotation** | New credential đã deploy | Old credential không còn usable |
| **Version rollback** | Consumer rollback dùng key cũ | Không phục hồi credential bị compromise |
| **Revoke token only** | Raw API key đã bị copy | Target vẫn phải revoke key |
| **OAuth refresh reuse** | Refresh token đã rotate bị dùng lại | AS xử lý theft/revoke theo policy |
| **Kubernetes secret access** | Pod khác cố đọc secret volume | Deny theo RBAC/mount isolation |
| **Untrusted CI PR** | Fork job xin prod secret | Deny bằng trust claims |
| **Secret in logs** | App hoặc agent cố in token | Detection/redaction và incident handling |
| **Dynamic credential privilege** | DB role tạm có SELECT, thử DROP | Deny |
| **Multiple leases** | 2 services nhận DB creds riêng | Không dùng chung admin password |
| **Target revoke unavailable** | DB API lỗi trong lúc revoke | Finding OPEN và containment |
| **Vault store outage** | Secret lookup lỗi | Không fail-open cấp quyền root |
| **KMS unavailable** | Vault không unseal/unwrap | Recover theo DR, không bỏ encryption |
| **Backup restore** | Snapshot cũ chứa revoked version | Không tự tái cấp target privilege |
| **Owner Mover** | Quyền dev cũ còn trong vault | Revoke quyền cũ, không giữ wildcard |
| **Owner Leaver** | Service vẫn hợp lệ | Chuyển owner, rotate exposure, không xóa service bừa |
| **Workload Retire** | Renewal job cũ xin DB credential | Source version/fencing chặn issuance |
| **Concurrent rotation** | Hai jobs cập nhật cùng secret | CAS/version tránh lost update |
| **Secret path injection** | Client cố đổi path sang tenant khác | Server-side resource validation và policy |
| **PAM checkout** | User được duyệt xem password admin | Audit, TTL, rotate và revoke sau dùng |
| **Break-glass** | IdP/vault lỗi | Quy trình dự phòng được kiểm thử, post-review |
| **Runtime negative test** | Credential đã revoke được dùng lại | Target Deny |
| **Audit** | User/workload đọc secret | Log metadata đúng nhưng không chứa raw value |

### Các nhóm test cần có

1. **Authn tests:** IdP, workload issuer, mTLS và bootstrap.
2. **Policy tests:** path/action/tenant/environment, wildcard và SoD.
3. **Secret engine tests:** static/dynamic, lease, renewal, versioning.
4. **Target integration tests:** database, SaaS, cloud, PKI/PAM.
5. **JML tests:** Joiner, Mover, Leaver, Rejoiner, workload Retire.
6. **Concurrency/failure injection:** retry, timeout, parallel rotation, stale event.
7. **Adversarial tests:** SSRF, issuer spoofing, token replay, secret exfiltration.
8. **DR tests:** encrypted backup, key custody, secure restore.
9. **Negative authorization tests:** credential đúng chữ ký nhưng action sai phải Deny.
10. **Audit/reconciliation tests:** evidence đủ và không rò raw secret.

## 40. Runbook: vault lỗi, credential bị lộ và thu hồi không thành công

### A. Workload không lấy được secret

1. Xác minh workload còn **ACTIVE**, đúng owner và environment.
2. Kiểm issuer, audience, subject và expiry của workload assertion an toàn.
3. Kiểm vault auth method và identity-to-policy mapping.
4. Kiểm path/action/namespace/tenant có đúng không.
5. Kiểm vault availability, network, KMS/unseal và rate limits.
6. Kiểm lease quota/secret engine có lỗi target backend không.
7. Không chữa bằng cách dán root token vào environment hoặc nới wildcard ACL.
8. Ghi operation ID, trace và owner để xử lý.

### B. Vault trả credential nhưng target trả 401/403

1. Tách **credential invalid** khỏi **permission thiếu** ở target.
2. Kiểm credential version, lease expiry và target account state.
3. Kiểm database role, SaaS scope, cloud policy hoặc PKI trust.
4. Kiểm app có dùng cached credential cũ sau rotation không.
5. Kiểm environment/tenant/resource scope chính xác.
6. Nếu credential vừa bị revoke theo JML, không tự cấp lại bằng bản cũ.
7. Điều chỉnh đúng desired permission, rồi verify target.

### C. Một API key/DB password bị lộ

1. Xác định **secret ID, target issuer/account, scope và người/workload có thể đã đọc**.
2. **Chặn action rủi ro** tại target/PEP ngay khi khả thi.
3. Revoke/disable credential ở target; nếu cần, cấp credential thay thế có scope đúng.
4. Kiểm các bản copy trong logs, Git history, CI artifacts, backups và runtime.
5. Rotate các secrets liên quan khi có khả năng bị ảnh hưởng.
6. Revoke vault sessions/tokens nếu nguồn lộ liên quan.
7. Kiểm token/session/connection đã phát và khả năng credential cũ còn sống.
8. Audit hành vi trong cửa sổ rủi ro và đối soát.
9. Không đóng incident chỉ vì đã xóa secret khỏi Git/vault.

### D. Rotation làm ứng dụng mất kết nối

1. Xác định target đã đổi key/password tại thời điểm nào.
2. Kiểm current secret version, consumer cache và deployment rollout.
3. Kiểm connection pool, process reload hoặc SDK refresh.
4. Nếu cần cutover lại, dùng **quy trình an toàn đã duyệt**, không tự mở global admin.
5. Không quay về credential đã compromise.
6. Khôi phục service với credential hợp lệ có scope hẹp.
7. Sau khi ổn định, kiểm old credential Deny và cập nhật rotation runbook.

### E. Leaver vẫn có thể lấy hoặc dùng credential

1. Xác minh HRIS effectiveAt, relationshipId và nguồn JML mới nhất.
2. Revoke IdP/SSO session, vault token và policy grants theo quan hệ đã kết thúc.
3. Inventory secrets người đó từng có khả năng truy xuất.
4. Xác định **target API keys/passwords/private keys** cần rotate/revoke.
5. Chặn PAM/JIT sessions, SSH/PAT và local access.
6. Gỡ credential cache/bản sao theo khả năng; không chỉ đổi metadata vault.
7. Negative test các action có rủi ro trong phạm vi kiểm soát.
8. Mở finding có owner/SLA khi chưa cắt được access thật.

### F. Vault cần phục hồi từ backup

1. Bảo đảm môi trường restore đúng trust/security boundary.
2. Xác minh encrypted backup, KMS/HSM/recovery materials và quyền thao tác.
3. Kiểm policy/auth methods/secret metadata sau restore.
4. Reconcile source version hiện hành: JML, workload Retire, revoked secrets.
5. **Không phát lại token/lease hoặc key cũ** vượt chính sách hiện hành.
6. Kiểm target accounts, active sessions và duplicate dynamic principals.
7. Chạy positive/negative tests cho các role/tenant quan trọng.
8. Ghi post-recovery findings và điều chỉnh DR kế hoạch.

## 41. Tình huống xuyên suốt: payments-api, CI/CD và JML

Giả sử doanh nghiệp có **payments-api**, **reporting-batch** và pipeline **deploy-payments**, triển khai bằng Kubernetes và cloud. IAM quản lý nhân viên theo HRIS, IdP/SSO và SCIM; credential vault bảo vệ secrets và tạo database credentials tạm.

### Giai đoạn 1 — Đăng ký và cấp quyền baseline

Payments Platform đăng ký **service:payments-api**, owner team, môi trường production, database target và action cần thiết. Security phê duyệt policy **generate database writer credential** chỉ cho workload này. Reporting-batch có role **read-only** khác; pipeline deploy chỉ được role deploy có hạn.

### Giai đoạn 2 — Xác thực workload

Pod payments-api sử dụng **bound workload identity assertion** dành cho vault. Vault kiểm issuer, subject, audience và workload state; sau đó phát database credential có lease ngắn, chỉ cấp quyền INSERT/UPDATE phù hợp. Ứng dụng không lưu DB root password trong container image.

### Giai đoạn 3 — CI/CD được tách riêng

Pipeline deploy-payments xác thực bằng OIDC job identity. Chỉ một workflow production đã được phép mới có thể lấy deploy credential; fork PR không được đọc production secret dù chạy trong cùng tổ chức. Audit liên kết cấp credential với job ID, repository và change approval.

### Giai đoạn 4 — Nhân viên chuyển đội (Mover)

Kỹ sư Minh chuyển từ Payments sang Analytics. IAM gỡ quyền người Minh đối với production vault paths, CI secrets và approval. Payments-api vẫn hoạt động vì **service identity khác human identity**. Nhóm đánh giá secrets mà Minh từng có thể đọc và rotate khi rủi ro yêu cầu; owner registry được cập nhật.

### Giai đoạn 5 — Secret rotation

DB credential static của một integration legacy cần thay. Rotation job tạo version mới, cập nhật target và consumers, xác minh kết nối. Sau đó bản cũ bị disable tại database và negative test xác nhận không còn được chấp nhận. Nếu chỉ xóa bản cũ trong vault nhưng target vẫn chấp nhận, finding phải còn OPEN.

### Giai đoạn 6 — Sự cố lộ token

Một CI job ghi nhầm deploy token vào artifact. Security xác định issuer, scope và TTL, thu hồi token/role tại nơi xác thực theo khả năng, xóa artifact/bản sao và điều tra hành vi. **Ẩn dòng log sau đó không đủ**, vì token có thể đã được sao chép.

### Giai đoạn 7 — Leaver và owner handoff

Minh sau đó nghỉ việc. IdP chặn login, IAM revoke những vault tokens thuộc relationship của Minh, xử lý PAM và đánh giá secrets từng tiếp cận. Workload vẫn còn phục vụ khách hàng dưới owner team hợp lệ. **Không xóa database credentials của payments-api chỉ vì nhân viên nghỉ**, nhưng cũng không để Minh giữ bản sao key có thể dùng được.

### Giai đoạn 8 — Workload Retire

Reporting-batch được thay thế. Registry đánh dấu RETIRED; vault dừng cấp lease mới; IAM/target thu hồi DB users, cloud role và API keys cũ. Một queued job từ deployment cũ bị sourceVersion/fencing chặn. Reconciliation xác minh **credential đã cấp không còn cho phép action trái chính sách**.

### Kết luận tình huống

**Credential vault giúp tổ chức bảo vệ và điều phối bí mật**, nhưng chỉ an toàn khi gắn với **identity, owner, source-of-truth, least-privilege target permissions, rotation, revocation và quan sát runtime**. Vòng đời **con người** và **workload** cần được quản lý riêng nhưng liên kết chặt trong **Joiner–Mover–Leaver**.

## 42. Checklist triển khai Credential vault an toàn

1. **Khái niệm:** đã phân biệt vault, KMS/HSM, password manager và IdP?
2. **Inventory:** mỗi secret có owner, purpose, workload, target và risk tier?
3. **Scope:** namespace tách prod/dev/staging, tenant và resource nhạy cảm?
4. **Identity trust:** human SSO/MFA và workload issuer/subject/audience được kiểm?
5. **Bootstrap:** workload không cần mang root token dài hạn trong code/image?
6. **Vault RBAC/ABAC/PBAC:** path/action/version/scope đúng least privilege?
7. **SoD:** người yêu cầu, approve, policy admin và audit có được phân tách khi cần?
8. **Secret encryption:** dữ liệu at rest/in transit được bảo vệ theo policy?
9. **Key custody:** KMS/HSM/recovery/unseal material có owner và kiểm soát?
10. **Secret inventory:** metadata không chứa raw password/private key?
11. **Static secrets:** có rotation và target revocation thật, không chỉ version mới?
12. **Dynamic secrets:** role tạm có scope và TTL hợp lý, lease revoke được đối soát?
13. **Secret delivery:** API/sidecar/CSI/file/env được chọn theo threat model?
14. **Kubernetes:** ServiceAccount, volume, Kubernetes Secret/RBAC và etcd được kiểm?
15. **CI/CD:** OIDC trust policy không cho fork/PR hoặc staging lấy prod credential?
16. **Token:** OAuth client secret, refresh token và vault token có lifecycle riêng?
17. **PKI/SSH:** private key, certificate, signing/SSH credentials được bảo vệ và rotate?
18. **PAM/JIT:** privileged checkout/session có approval, expiry và audit?
19. **Break-glass:** có recovery path an toàn khi IdP/vault unavailable?
20. **Cache:** không giữ secret dài hơn cần thiết, có invalidation/cleanup?
21. **Target permissions:** database/cloud/SaaS role không rộng hơn mục đích?
22. **Rotation:** có dual credential/cutover khi hỗ trợ và negative test old key?
23. **Versioning:** không cho rollback kích hoạt lại credential đã compromise?
24. **Revocation:** revoke vault token khác revoke target API key/DB account?
25. **Joiner:** quyền human vault được cấp sau proofing/approval phù hợp?
26. **Mover:** gỡ namespace cũ, rà soát secret exposure và cấp role mới đúng scope?
27. **Leaver:** human vault access bị cắt, target secrets đã biết được rotate/revoke theo risk?
28. **Rejoiner:** quyền cũ không tự hồi sinh theo email/relationship lịch sử?
29. **Workload owner JML:** owner thay đổi mà không xóa bừa service còn hợp lệ?
30. **Workload Retire:** ngừng issuance, revoke leases, xóa target grants và verify?
31. **Concurrency:** sourceVersion/fencing/idempotency ngăn stale job regrant?
32. **Outage:** có HA/DR, fail-safe behavior và tránh fallback root secrets?
33. **Backup:** encrypted backups và key recovery được kiểm thử độc lập?
34. **Audit:** truy vết actor/path/decision/lease nhưng không ghi raw secrets?
35. **Privacy:** logs và metadata được giảm thiểu/giới hạn quyền truy cập?
36. **Metrics:** đo orphan, overprivileged, long-lived, revoke latency và coverage?
37. **Testing:** có test cross-tenant, replay, XSS/log leak, role và target denial?
38. **Reconciliation:** desired, vault, consumer và target access được đối chiếu?
39. **Incident response:** có runbook secret leak, credential rotation, PAM và DR?
40. **Closure:** chỉ kết luận hoàn tất khi **quyền thực tế bị thu hồi đúng** trong phạm vi xác minh?

### Ghi nhớ

**Credential vault là nền tảng bảo vệ và quản lý vòng đời bí mật dùng để xác thực, bao gồm passwords của dịch vụ, API keys, tokens và private keys.** Giá trị bảo mật đến từ **xác thực đúng human/workload, kiểm soát path/action theo least privilege, mã hóa, secret delivery an toàn, cấp credential tạm, rotation, audit và revocation có kiểm chứng**. **Vault token không phải access token của API; secret đã bị xóa trong vault không có nghĩa target đã từ chối credential cũ; hết lease không mặc nhiên chứng minh kết nối đã bị đóng.** Trong **IAM Identity Lifecycle**, quyền vault của con người phải theo **Joiner–Mover–Leaver**, còn secret và service account phải theo **Create–Change–Retire của workload**. Chỉ khi kết hợp **IdP/SSO, SCIM, RBAC/ABAC/PBAC, PAM/JIT, target authorization và reconciliation**, tổ chức mới hạn chế được **quyền truy cập tồn dư** sau thay đổi danh tính hoặc quyền.
