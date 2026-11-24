# Key storage

Một hệ thống OAuth 2.0/OpenID Connect có **Authorization Server (AS)** ký access token bằng `RS256`, ba **Resource Server (RS)** kiểm chữ ký và một ứng dụng `shop-bff` xác thực client bằng private key. Tất cả đều “dùng khóa”, nhưng **không nên cùng lưu hoặc cùng được phép sử dụng một private key**.

Ví dụ, nếu private signing key của AS bị đưa vào cấu hình `orders-api` cho tiện kiểm JWT, kẻ xâm nhập RS có thể lấy khóa và **ký token giả như AS**. Thực ra, RS chỉ cần **public key của AS** để xác minh JWT. Private key nên được bảo vệ ở trust boundary của signer, lý tưởng là không cần xuất ra khỏi KMS/HSM nếu cơ chế ký hỗ trợ. Tương tự, một HMAC secret dùng ký `HS256` phải là bí mật đối với mọi bên không được quyền tạo MAC; việc chia secret cho RS làm verifier đồng thời có khả năng tạo chữ ký hợp lệ.

**Key storage** không chỉ là câu hỏi “đặt file `.pem` ở đâu?”. Đó là việc kiểm soát **ai có thể tạo, đọc, sử dụng, sao lưu, xoay vòng và hủy khóa; trạng thái nào được phép; khóa xuất hiện trong RAM/log/backup ở đâu; và điều gì xảy ra khi khóa bị lộ**.

Bài thuộc chương **Key management** của module **SECURITY_TOKEN_SECURITY_FUNDAMENTALS**. Trong bối cảnh mô hình tin cậy và vòng đời token bảo mật, nội dung liên hệ JWT và opaque token, access/refresh token, xác thực–phân quyền OAuth 2.0/OIDC, các claims `iss`/`aud`/`scope`, phát hành, lưu trữ và thu hồi token cũng như phòng chống đánh cắp hoặc phát lại. Phạm vi trọng tâm là **lưu trữ và quyền sử dụng cryptographic keys**, không đồng nhất nó với lưu trữ bearer tokens.

> **Nguyên tắc xuyên suốt:** Khóa nào phải giữ bí mật thì chỉ cấp quyền **sử dụng tối thiểu** cho workload cần nó; nếu có thể, workload **gọi dịch vụ ký/giải mã mà không lấy raw key material**. Public verification key thì có thể phân phối, nhưng phải kiểm nguồn tin cậy và không nhầm với private/symmetric key.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

1. Phân biệt **private signing key**, **symmetric HMAC key**, **encryption key**, **key-encryption key**, public verification key, OAuth client key và secret dùng truy cập dịch vụ.
2. Giải thích vì sao nơi lưu key phải phù hợp **vai trò signer, verifier, encryptor/decryptor, client và sender-constrained token holder**.
3. Đánh giá ưu/nhược điểm khi lưu key trong file PEM/PKCS#12, environment variable, Secret Manager, KMS, HSM và các secure stores của nền tảng.
4. Trình bày cách **non-exportable key**, IAM/least privilege, workload identity, audit và network isolation giảm hậu quả xâm nhập.
5. Thiết kế **envelope encryption** với KEK/DEK, AEAD/AAD, key version và kiểm soát quyền giải mã.
6. Nhận diện rủi ro **secret zero**, secret injection, logs, core dump, container image, CI/CD và backup.
7. Quản lý vòng đời: generate → activate → rotate → verify-only/decrypt-only → retire/destroy, bao gồm trường hợp compromise.
8. Phân biệt **key rotation** với **token revocation**, tránh hiểu nhầm việc đổi khóa tự vô hiệu mọi bearer token hoặc refresh token.
9. Áp dụng Java JCA/KeyStore và các mẫu tích hợp KMS/HSM/Spring trong phạm vi ví dụ an toàn.
10. Xây dựng negative tests và incident playbook cho key leakage, IAM escalation, JWKS xuất nhầm khóa bí mật, backup restore và cross-environment access.

## 2. Key storage bảo vệ điều gì?

### 2.1. Một hệ thống có nhiều loại “khóa”

| Loại | Ai sở hữu | Dùng để làm gì? | Mức độ bí mật |
|---|---|---|---|
| **AS private signing key** | Authorization Server/OP | Ký JWS access token, ID token theo profile. | **Bí mật cao**; RS không cần nhận raw key. |
| **AS public verification key** | Công bố bởi issuer | RS/OIDC Client kiểm chữ ký đúng issuer. | **Công khai**, nhưng phải tin đúng nguồn/issuer. |
| **HS256 HMAC secret** | Signer và verifiers được cấu hình | Tạo/kiểm MAC của JWS. | **Bí mật**; bất kỳ holder nào có thể tạo MAC. |
| **JWE private decryption key** | Recipient được chỉ định | Giải mã key/content cho JWE. | **Bí mật**, không nhất thiết thuộc AS. |
| **AES/AEAD data encryption key (DEK)** | Service/encryption component | Mã hóa một nhóm bản ghi/dữ liệu. | **Bí mật**, có thể dùng key theo đối tượng/phạm vi. |
| **Key encryption key (KEK)** | KMS/HSM hoặc key hierarchy | Bọc/giải bọc DEK. | **Bí mật**, nên giới hạn export/use. |
| **OAuth client private key** | Confidential OAuth client | Ký `private_key_jwt` client assertion. | **Bí mật của client**, không phải AS issuer key. |
| **Client secret** | Confidential OAuth client/AS registration | Client authentication theo phương thức cho phép. | **Bí mật**, không phải JWT public key. |
| **DPoP private key** | Token holder/client | Ký proof ràng buộc access token với key. | **Bí mật của holder**; lưu khác nhau tùy web/mobile/server. |
| **mTLS private key** | Workload/thiết bị client | TLS client authentication/certificate-bound token. | **Bí mật**, thường được bảo vệ trong OS store/HSM/TPM. |
| **Public JWK/JWKS** | Issuer/client theo profile | Phân phối public keys để verify. | Chỉ chứa **public parameters**. |

Ngoài ra còn có password, API key và raw bearer token; chúng cũng là **secrets**, nhưng **không phải mọi secret đều là cryptographic key**. Cơ chế quản lý tương đồng về quyền truy cập và redaction, nhưng format, thuật toán và vòng đời khác.

### 2.2. Key có ba trạng thái phơi lộ cần xét

~~~text
At rest:
  disk, keystore, database, object storage, backup, CI artifact

In transit:
  secret injection, service-to-service calls, KMS API, operator access

In use:
  process memory, heap, native provider, crypto API, core dump, logs
~~~

“Đã mã hóa key trên ổ đĩa” chỉ giải quyết **một phần at-rest risk**. Nếu ứng dụng phải đọc raw key để ký, key vẫn có thể xuất hiện trong RAM; nếu workload bị xâm nhập, attacker có thể gọi signer thay cho ứng dụng ngay cả khi private key **không xuất được**.

### 2.3. Mục tiêu bảo mật cần đo được

- **Confidentiality:** private/symmetric key không lộ cho đối tượng không có quyền.
- **Integrity:** key material, metadata `kid`/version, policies và mappings không bị thay trái phép.
- **Availability:** RS vẫn verify được token hợp lệ khi rotate; signer/KEK không bị một điểm lỗi gây gián đoạn ngoài SLA.
- **Least privilege:** verifier không có quyền ký, service A không có quyền giải mã dữ liệu B.
- **Auditability:** có thể truy vết ai sử dụng/đổi policy/rotate key mà không log raw key.
- **Recoverability:** có backup/restore đủ để khôi phục khả năng decrypt dữ liệu cần giữ mà không sao chép key trái phép.
- **Containment:** khi key bị compromise, biết được blast radius và có phương án cutoff/reissue/reencrypt.

## 3. Mô hình tin cậy: private key nằm ở đâu?

### 3.1. Ký JWT với KMS/HSM, không phân private key cho RS

~~~mermaid
sequenceDiagram
    autonumber
    participant C as OAuth Client
    participant AS as Authorization Server
    participant POL as Grant and Scope Policy
    participant KMS as KMS/HSM Signing Key
    participant RS as Orders Resource Server
    participant JWKS as Trusted Issuer JWKS

    C->>AS: Token request under valid grant
    AS->>POL: Check client, subject, consent, scope, audience
    POL-->>AS: Approved claims and token profile
    AS->>KMS: Sign exact JWS input using key reference
    KMS-->>AS: Signature, not private key bytes
    AS-->>C: Signed JWT access token
    C->>RS: Authorization Bearer JWT
    RS->>JWKS: Resolve trusted public key by issuer/kid
    RS->>RS: Verify signature, iss, aud, exp, scope, tenant
    RS-->>C: Authorized result or denial
~~~

Mẫu **sign-by-reference** tránh việc AS application tải raw private key. Nhưng KMS chỉ kiểm quyền **workload được phép gọi Sign**, không tự xác định user có quyền `orders:read`. Nếu AS bị tấn công, attacker có thể lợi dụng quyền ký hợp pháp của workload. Vì thế phải bảo vệ **cả authorization policy trước khi ký** lẫn key usage IAM.

### 3.2. Sai thiết kế: verifier giữ issuer private key

~~~text
AS:
  PRIVATE_RSA_KEY=...

orders-api:
  PRIVATE_RSA_KEY=...     # Không cần để verify

payments-api:
  PRIVATE_RSA_KEY=...     # Mở rộng vùng lộ khóa
~~~

Một RS thường chỉ cần:

~~~text
TRUSTED_ISSUER=https://login.example.com
TRUSTED_JWKS_URI=https://login.example.com/oauth2/jwks
EXPECTED_AUDIENCE=orders-api
ALLOWED_JWS_ALGORITHMS=RS256
~~~

`JWKS_URI` chỉ được lấy từ **issuer metadata/configuration đáng tin**; không theo URL `jku`/`x5u` do token của attacker khai báo.

### 3.3. HMAC thay đổi trust boundary

Với `HS256`, verifier cần shared secret và về mặt crypto cũng **có thể tạo MAC hợp lệ**. HMAC secret lưu trong Secret Manager không loại bỏ việc các RS được phép đọc secret có quyền tạo MAC.

~~~text
AS signs HS256 with key K
RS-1 verifies HS256 with key K
RS-2 verifies HS256 with key K

Compromise RS-1 + disclosure of K
    -> attacker may forge signatures accepted by RS-2
~~~

Có thể tách key theo audience/trust domain hoặc dùng chữ ký bất đối xứng để RS chỉ giữ public key. Đừng phát `HS256` secret vào mobile/public browser app vì nó không thể giữ bí mật trước người dùng thiết bị.

### 3.4. Crypto trust không thay token authorization

RS kiểm signature đúng bằng trusted public key vẫn phải xác minh:

- `iss` chính xác, `aud` dành cho RS, `exp`/`nbf` còn hợp lệ.
- `typ`/token purpose (access token khác OIDC ID token và client assertion).
- `scope` và quyền được cấp cho user/service.
- Tenant membership, object ownership/ACL và trạng thái nghiệp vụ.
- Revocation/state/sender binding nếu profile yêu cầu.

**Một private key được giữ an toàn vẫn có thể ký token có claims sai nếu AS issuance policy có lỗi.**

## 4. Phân loại tài sản và đe dọa trước khi chọn nơi lưu

### 4.1. Inventory cần có

~~~yaml
# Inventory minh họa; không phải format chuẩn chung.
keyRecord:
  keyRef: as-jwt-signing-2026-11
  ownerService: authorization-server
  environment: production
  purpose: JWT_JWS_SIGN
  algorithm: RS256
  allowedOperations: [SIGN]
  publicVerifierDistribution: TRUSTED_JWKS
  storageClass: MANAGED_HSM_KMS
  exportPolicy: NON_EXPORTABLE
  resourceScopes: [issuer-main]
  createdAt: "2026-11-23T00:00:00Z"
  nextRotationReviewAt: "2027-02-23T00:00:00Z"
  lifecycleState: ACTIVE
  contactRole: security-platform
~~~

Ngày và thời hạn là **ví dụ**; cryptoperiod phải xác định theo security policy/thuật toán/rủi ro. Các trường `keyRef`, `storageClass` và `contactRole` không phải trường JWK hay OAuth RFC bắt buộc.

### 4.2. Các đe dọa quan trọng

| Đe dọa | Đường khai thác | Điều cần bảo vệ |
|---|---|---|
| Code repository leak | Commit PEM, `.env`, test fixture thật. | Scanner, protected review, key rotation và history exposure. |
| Container image leak | Key/secret được bake bằng Docker build arg/layer. | Runtime injection và image scanning. |
| CI/CD compromise | Pipeline đọc production private key hoặc in secret ra console. | Workload IAM tách, masked output, short-lived credentials. |
| Runtime takeover | Attacker chạy lệnh dưới service identity, gọi `Sign`. | Least privilege, sandbox/network isolation, abuse detection. |
| Database/backup compromise | Raw keys hoặc wrapped DEKs bị sao chép. | Key separation, encryption at rest và backup access. |
| Secret Manager policy sai | Một service đọc secret của mọi môi trường. | RBAC, namespace/tenant boundary, audit. |
| KMS/HSM misuse | Quyền `Sign`/`Decrypt` quá rộng hoặc dùng sai key. | Key-level IAM, encryption context, explicit operations. |
| Memory dump/crash | Raw key trong Java heap, log exceptions. | Hạn chế export, diagnostic controls, memory handling. |
| Admin/insider misuse | Quản trị viên xuất/rotate/delete key không kiểm soát. | Dual control khi cần, approvals, separation of duties. |
| JWKS mispublication | Private JWK `d` hoặc symmetric `oct` key trong public JWKS. | Public-key projection, automated tests và incident response. |
| Ransomware/availability loss | Xóa KEK hoặc khóa signing trước khi migrate. | Recovery plan, protected backups, key retirement plan. |

### 4.3. Một hệ thống có nhiều trust domains

Không dùng chung một khóa bí mật cho **dev, staging, production** chỉ để test dễ hơn. Cũng không dùng một KEK cho mọi tenant/resource nếu blast radius không đáp ứng yêu cầu. Nhưng **key per tenant** tạo thêm số lượng, IAM/JWKS cache, backup và rotation complexity; chọn theo risk model thay vì mặc định càng nhiều keys càng an toàn.

## 5. Các lựa chọn key storage

| Nơi lưu | Ưu điểm | Rủi ro/hạn chế | Thích hợp khi |
|---|---|---|---|
| **Hardcode trong source** | Không có lợi ích bảo mật đáng kể. | Repo, package, history, CI và binary dễ lộ. | **Không dùng cho secrets production.** |
| **Plain PEM trên local disk** | Tương thích rộng, dễ chạy. | File permissions, image/snapshot/backup leak; app đọc raw key. | Lab hoặc môi trường có threat control chặt. |
| **Encrypted PKCS#12/KeyStore file** | Bảo vệ at rest bằng password; chuẩn tích hợp JCA. | Password vẫn cần bảo vệ; runtime có thể lấy private key. | Legacy/on-prem hoặc giải pháp không có KMS. |
| **Environment variable** | Runtime injection tiện lợi, không commit file. | Process env, crash diagnostics, child processes, operator debug. | Secret injection được kiểm soát, không là vault tự thân. |
| **Mounted secret file/volume** | Có ACL và có thể cập nhật từ secret provider. | Pod/node compromise, đọc raw bytes, mount snapshots. | Workloads có secret delivery controller tốt. |
| **OS Keychain/DPAPI/TPM-backed store** | Có thể bind với user/device/hardware. | Tùy hệ điều hành, exportability và API semantics. | Client/mobile/desktop/device identities. |
| **Secret Manager/Vault** | Phiên bản secret, ACL, audit, rotation, delivery. | App có `read secret` vẫn thấy raw material; dependency availability. | OAuth client secrets, HMAC keys, passwords, private keys nếu cần export. |
| **Cloud KMS / managed key service** | Operation-based `Sign`/`Decrypt`, key-level IAM/audit; có loại key không xuất được. | Provider constraints, quotas, latency, network dependency. | AS signing, KEK/wrapping, encryption workloads. |
| **HSM/PKCS#11** | Key generation/use trong boundary được bảo vệ, non-exportable options. | Vận hành phức tạp, HA/backup và driver/provider integration. | High-value issuer keys, regulated workloads. |

**Không có một lựa chọn thắng cho mọi key.** Public verification key thường **không cần Secret Manager**; một RSA private issuer key nên có bảo vệ mạnh hơn một public TLS certificate, còn một refresh token store có yêu cầu khác với key store.

## 6. KMS, HSM và “non-exportable” nghĩa là gì?

### 6.1. Operation-based access

Thay vì:

~~~text
AS -> GET /secrets/private-signing-key -> raw PKCS8 bytes
AS -> local Signature.sign(...)
~~~

có thể dùng:

~~~text
AS -> KMS.Sign(keyRef, algorithm, message-or-digest)
KMS -> signature bytes
AS -> build JWS compact token
~~~

Khi khóa **non-exportable** trong boundary provider/HSM, ứng dụng không cần thấy raw private key. Tuy nhiên:

- Khả năng non-exportable phụ thuộc **key class, HSM/KMS provider, import/export setting**; không mặc định mọi key trong “KMS” đều không xuất được.
- **`Sign` có thể bị lạm dụng** nếu workload bị compromise; IAM và AS issuance authorization vẫn phải bảo vệ.
- KMS có quotas, latency, network outages và key disabled/deleted states; cần capacity/resilience plan.
- Provider có thể nhận **raw message hoặc digest**, đòi chỉ định thuật toán chuẩn. **Không hash hai lần hoặc tự ghép JWS sai signing input**.
- `Verify` của RS thường chỉ cần public key/JWKS, không nên cấp RS quyền `Sign` trong KMS.

### 6.2. HSM/PKCS#11 và Java

Một HSM có thể cung cấp **PKCS#11 interface** để ứng dụng gọi ký qua Java security provider. Tùy mô hình, `PrivateKey` trong Java có thể là **handle tới non-extractable key**, không phải PEM bytes. Không gọi `getEncoded()` rồi mong luôn nhận key material.

Phải kiểm:

1. Provider/KMS/HSM hỗ trợ đúng JWS algorithm và key format.
2. Authentication/PIN/session policy không bị hardcode.
3. Failover, key labels/IDs, concurrency, throttling và token/session pool.
4. Key backup/HA theo chính sách của thiết bị (không sao chép private key thô bằng tay).
5. Logging không tiết lộ PIN, key handle có quyền cao hoặc plaintext nhạy cảm.
6. Signing operations được phép cho **issuer workload**, không phải mọi process trên host.

### 6.3. KMS key policy và encryption context

Với các API mã hóa/giải mã hỗ trợ **encryption context/AAD**:

~~~json
{
  "service": "authorization-server",
  "environment": "production",
  "purpose": "wrap-token-store-dek",
  "tenant_ref": "tenant-beta"
}
~~~

AAD/encryption context phải **khớp khi decrypt** và có thể hỗ trợ IAM policy theo context. Nó **không được mã hóa**, vì thế không đặt raw PII/token/private secrets ở đó. Context phải được xác thực bởi ứng dụng, **không lấy tenant_id tự khai trong request làm cơ sở duy nhất**.

### 6.4. HSM không làm private key hết quan trọng

Ngay cả khi key không xuất được, một attacker có quyền gọi `Sign` nhiều lần có thể yêu cầu tạo token chữ ký hợp lệ. Cần:

- Authorization policy trước khi ký.
- IAM cho từng key và từng operation.
- Bảo vệ workload identity, network endpoint và request provenance.
- Giới hạn/giám sát signing rate, đối chiếu token issuance với grants.
- Alert khi workload không được phép gọi signer.
- Kế hoạch revoke/disallow key khi signer bị misuse.

## 7. Secret Manager: lưu raw secret có kiểm soát

### 7.1. Chọn đúng loại dữ liệu

Secret Manager/Vault thường phù hợp để lưu:

- `client_secret` của confidential OAuth client khi không có phương thức tốt hơn.
- **HMAC HS256 secret** khi thiết kế yêu cầu shared secret.
- Password/PIN mở encrypted keystore hoặc credentials cho dịch vụ ngoài.
- Private key **chỉ khi** thư viện cần raw bytes và rủi ro export được chấp nhận.
- Secret bootstrap tạm thời, certificate chain/private-key pair khi hệ thống PKI/provider yêu cầu.

Nếu có thể ký bằng non-exportable key từ KMS/HSM, **đừng tải private key raw chỉ vì Secret Manager có chức năng lưu secret**.

### 7.2. Runtime delivery không được đưa vào image

Sai:

~~~dockerfile
# KHÔNG LÀM VỚI PRODUCTION KEYS
COPY production-private-key.pem /app/key.pem
ENV JWT_HMAC_SECRET=real-production-secret
~~~

Mẫu kiến trúc tốt hơn:

~~~text
Workload starts under verified service identity
    -> authenticates to Secret Manager or KMS
    -> receives only allowed secret/operation
    -> uses short-lived credentials or non-exportable key operation
    -> audits access without logging secret
~~~

Runtime environment variables/mounted files là **delivery mechanisms**, không phải nơi lưu đáng tin duy nhất. Một attacker đủ quyền trong process/container vẫn có thể đọc chúng.

### 7.3. Secret versioning, rotation và cache

- Gắn `secret-version` với key material để tránh lấy nhầm khi rollout.
- Quy định **activation time**, thời hạn cache và cách đổi version.
- Không ghi secret values vào exception, tracing, shell history hoặc config dump.
- Khi rotate secret dùng chung, triển khai **bounded overlap** giữa signer và verifiers; xóa version cũ sau khi không còn cần.
- Nếu secret bị lộ, không giữ old version để “giảm lỗi”; xử lý emergency cutoff theo risk.
- Tách secrets theo environment, workload và tenant nếu threat model yêu cầu.

### 7.4. Secret Manager có được biết private key không?

Nếu dùng secret store kiểu **raw key upload**, provider/storage layer có thể nắm key bytes dưới dạng được mã hóa theo mô hình của họ; workload được `read` có thể lấy key. Điều đó khác **non-exportable HSM signing key** mà workload chỉ gọi `Sign`. Đánh giá trust model nhà cung cấp, nhân sự vận hành, audit, export controls và compliance yêu cầu.

## 8. PEM, PKCS#12 và Java KeyStore: lưu file an toàn đến mức nào?

Một file keystore có thể là lựa chọn thực tế cho hệ thống legacy hoặc môi trường on-prem, nhưng cần hiểu **file-based encryption không phải HSM**.

### 8.1. Public certificate khác private key file

~~~text
server-certificate.pem
  -----BEGIN CERTIFICATE-----
  ...
  -----END CERTIFICATE-----

server-private-key.pem
  -----BEGIN PRIVATE KEY-----
  ...
  -----END PRIVATE KEY-----
~~~

**Certificate/public key thường không phải bí mật.** `PRIVATE KEY` (kể cả encrypted PKCS#8) là vật liệu nhạy cảm. File `.p12`/`.pfx` thường chứa private key, certificate chain và các entries được bảo vệ bằng password.

Các chuỗi `...` chỉ minh họa. **Không đưa khóa thật vào tài liệu, ticket, commit, log hoặc chat công khai**.

### 8.2. File permissions và filesystem boundary

Với một private key cần nằm trên máy:

- Chỉ owner/service identity được quyền đọc file; không để world-readable.
- Dùng file/volume riêng, tránh đặt cùng static web root hoặc upload directory.
- Không lưu trong container image layer, Git LFS hoặc release artifact phát tán rộng.
- Bảo vệ disk snapshot, backup, swap/core dump, diagnostic bundle và access từ administrators.
- Dùng encryption-at-rest có quản lý khóa khác nếu threat model yêu cầu.
- Tránh symlink/file path injection nếu ứng dụng tải key theo path từ input.
- Đặt integrity checks và backup/restore policy để tránh attacker thay public/private key file.

`chmod 600` chỉ bảo vệ theo mô hình quyền POSIX trên một host; **không chặn root, container escape, backup operator hoặc process owner bị compromise**.

### 8.3. PKCS#12 và password phải được giữ riêng

Một keystore được mã hóa cần **passphrase để mở**. Nếu file `keystore.p12` và password cùng nằm trong source/image hoặc cùng một config công khai, lợi ích giảm đáng kể.

~~~text
Deployment:
  encrypted key store -> protected read-only runtime mount
  unlock passphrase   -> separate Secret Manager / workload policy
  service identity    -> authorized to read the mount and passphrase

Process:
  unlock keystore -> raw private key may enter application memory
~~~

Nếu ứng dụng đọc private key dưới dạng `PrivateKey` có thể export, đối tượng key vẫn có thể tồn tại trong Java heap/native memory; cần hạn chế dumps, logging và thời gian tồn tại.

### 8.4. Java KeyStore alias không phải authorization

`alias="issuer-signing"` chỉ giúp chọn entry trong keystore; **không tự chứng minh token issuer**, không phải key usage policy. Ứng dụng phải ràng buộc alias với mục đích và key fingerprint/config tin cậy. Tên entry do attacker cung cấp không được phép khiến code load khóa khác.

### 8.5. Khi nào nên rời file-based signing?

Cân nhắc chuyển sang KMS/HSM operation-based khi:

- Private signing key có quyền phát JWT được nhiều Resource Servers tin.
- Sự cố lộ key dẫn đến khả năng giả nhiều access tokens/ID tokens.
- Nhiều workloads đang copy cùng private key.
- Có yêu cầu non-exportable, IAM key-level hoặc audit signer operations.
- Rotation và thu hồi credentials cần triển khai nhanh/đa vùng.

**Không bỏ qua chi phí vận hành:** KMS/HSM dependency, network timeout, quota, disaster recovery và thuật toán supported phải được đánh giá trước.

## 9. Envelope encryption: không lưu DEK trần cạnh ciphertext

**Envelope encryption** là mô hình dùng **Data Encryption Key (DEK)** để mã hóa dữ liệu, còn **Key Encryption Key (KEK)** bảo vệ DEK (wrap hoặc encrypt). KEK thường có thể nằm trong KMS/HSM và không xuất ra.

### 9.1. Sơ đồ key hierarchy

~~~mermaid
flowchart TD
    A[Service identity authorized for encryption] --> B[KMS KEK reference]
    B --> C[Generate or wrap a fresh DEK]
    C --> D[Plaintext DEK used for AEAD]
    D --> E[Encrypt data with AES-GCM and unique nonce]
    E --> F[Store ciphertext, nonce, tag and wrapped DEK]
    F --> G[Later authorized decrypt request]
    G --> H[KMS unwrap DEK under key policy/context]
    H --> I[AEAD decrypt and authenticate data]
    I --> J[Use plaintext only within authorized scope]
~~~

Trong một triển khai cụ thể, KMS có thể **GenerateDataKey**, `Encrypt`/`Decrypt` hoặc `WrapKey`/`UnwrapKey` với API/thuật toán khác nhau. Mục tiêu là **không lưu plaintext DEK cùng bản ghi dữ liệu** và chỉ caller có quyền mới unwrap được.

### 9.2. Record minh họa

~~~json
{
  "record_id": "opaque-token-metadata-9841",
  "encryption": {
    "schema_version": 3,
    "algorithm": "AES-256-GCM",
    "kek_ref": "kms/prod/oauth-token-store/v3",
    "wrapped_dek": "BASE64_CIPHERTEXT_OF_DEK",
    "nonce": "BASE64_RANDOM_NONCE",
    "tag": "BASE64_AUTHENTICATION_TAG",
    "aad_context": {
      "service": "oauth-token-store",
      "environment": "production",
      "record_type": "token-metadata"
    }
  },
  "ciphertext": "BASE64_CIPHERTEXT"
}
~~~

Đây là **schema minh họa, không phải JWE/JWK chuẩn**. `wrapped_dek` là ciphertext chứa DEK, không phải raw key. `nonce` và `tag` có thể nằm cùng ciphertext vì không là bí mật; nhưng **nonce uniqueness** và authentication tag verification phải đúng.

### 9.3. Authenticated encryption và AAD

Với AES-GCM:

~~~text
ciphertext, tag = AES_GCM_Encrypt(DEK, nonce, plaintext, AAD)

plaintext = AES_GCM_Decrypt(DEK, nonce, ciphertext, tag, AAD)
    OR error if tag/context invalid
~~~

- `nonce` phải không lặp lại dưới cùng key theo scheme; reuse có thể phá bảo mật.
- `AAD` được xác thực nhưng **không mã hóa**. Có thể ràng buộc record ID, purpose/tenant context để phát hiện tráo ciphertext giữa bản ghi.
- `AAD`/key policy không được xây từ input giả mạo chưa xác thực.
- Không nuốt authentication failure và trả plaintext rỗng như success.
- Tránh nonce/tag/key size tùy biến ngoài library security contract.

### 9.4. Đừng dùng DEK của storage để ký JWT

KEK/DEK nhằm **bảo vệ dữ liệu lưu trữ**, không phải tự là JWS issuer signing keys. Dùng cùng key bytes để AES-GCM, HS256, session MAC và JWT signing làm khó phân tách quyền và blast radius. Tách **purpose** và key hierarchy, dùng KDF/domain separation đúng profile nếu một hệ thống yêu cầu derive nhiều subkeys.

### 9.5. Rotate KEK không nhất thiết phải reencrypt mọi data

Nếu DEK không đổi và chỉ KEK thay, có thể **rewrap DEK** dưới KEK mới, không cần mã hóa lại toàn bộ ciphertext. Tuy nhiên:

- Đánh giá KEK cũ đã compromise hay chưa.
- Nếu plaintext DEK đã lộ thì **chỉ rewrap không sửa được lỗ hổng**; cần DEK mới và reencrypt dữ liệu bị ảnh hưởng.
- KMS metadata/key reference phải version hóa để decrypt record cũ.
- Cần test restore từ backup với wrapped DEK, key versions và ciphertext đầy đủ.
- Rewrap theo batch phải idempotent, không khiến dữ liệu mất khả năng decrypt khi job dừng nửa chừng.

### 9.6. DEK trong RAM và caching

Một workload nhận plaintext DEK từ KMS vẫn có thể lộ key qua heap dump hoặc process compromise. Giới hạn thời gian cache/đối tượng sử dụng, không đưa DEK vào log, không giữ raw bytes trong global singleton vô thời hạn vì tiện. Nếu dự án có yêu cầu mạnh, cân nhắc encryption operation chỉ diễn ra trong hardware/trusted boundary phù hợp, hiểu latency/trade-off.

## 10. Secret zero: service mở kho khóa bằng gì?

Ngay cả khi key nằm trong Secret Manager/KMS, ứng dụng phải **xác thực** để gọi kho khóa. Nếu đặt một **static master password** trong source code để mở vault, đó là vấn đề **secret zero**: ta vừa dời bí mật từ nơi này sang nơi khác.

### 10.1. Bootstrap bằng workload identity

Mô hình thường được ưu tiên:

~~~mermaid
sequenceDiagram
    autonumber
    participant ORCH as Platform Identity Controller
    participant APP as Authorization Server Workload
    participant IAM as Identity and Authorization Service
    participant KMS as KMS / Secret Store
    ORCH-->>APP: Provide workload identity proof, short-lived
    APP->>IAM: Authenticate workload identity
    IAM-->>APP: Authorized short-lived identity/credentials
    APP->>KMS: Sign using permitted key reference
    KMS->>KMS: Check IAM, key policy and operation
    KMS-->>APP: Signature only
~~~

Workload identity có thể đến từ cloud instance/service accounts, Kubernetes federated OIDC identities, mTLS workload identities hoặc một trusted runtime theo nền tảng. **Cấu hình thực tế phải kiểm audience, issuer, service account, namespace, workload attributes và token lifetime**; không chỉ thấy “có JWT” là xác thực workload.

### 10.2. Các bootstrap patterns kém an toàn

~~~text
VAULT_ROOT_PASSWORD=permanent-root-password
KMS_ADMIN_API_KEY=hardcoded-in-repo
HSM_PIN=1234
KEYSTORE_PASSWORD=production-password-in-Dockerfile
~~~

Các credentials root/admin dài hạn nếu bị đưa vào image, log, repo hoặc ticket có thể mở toàn bộ kho khóa. Ưu tiên **short-lived scoped identity**, break-glass credentials có kiểm soát và tách operator/admin access khỏi ứng dụng thường ngày.

### 10.3. Kubernetes Secrets không tự là HSM

Kubernetes Secret có thể là delivery/config resource thuận tiện, nhưng:

- Base64 trong Kubernetes object **không phải encryption**.
- Cần bảo vệ etcd encryption, RBAC, audit và API server access.
- Pod có quyền mount secret hoặc read API có thể lấy raw secret.
- Secret volumes có thể bị copy vào dumps/backup.
- External Secrets/CSI driver có thể tích hợp Vault/KMS, nhưng phải kiểm trust/rotation/secret refresh.

Không gọi “đã đưa lên Kubernetes Secret” là hoàn tất key management.

### 10.4. Scope identity tới operation, không tới cả kho

Ví dụ policy mô tả:

~~~yaml
# Policy minh họa, không là IAM JSON dùng trực tiếp.
identity: workload/authorization-server/prod
allowed:
  - operation: SIGN
    keyRef: keys/prod/as-jwt-signing
  - operation: READ_PUBLIC_KEY
    keyRef: keys/prod/as-jwt-signing
denied:
  - operation: EXPORT_PRIVATE_KEY
  - operation: DELETE_KEY
  - operation: DECRYPT
    keyRef: keys/prod/payments-database
~~~

Đây là nguyên tắc **least privilege**, không phụ thuộc syntax của AWS/GCP/Azure/HSM cụ thể.

## 11. IAM và Separation of Duties: ai được sử dụng khóa?

### 11.1. Phân tách quyền theo workload

| Chủ thể | Quyền nên có | Quyền không nên có |
|---|---|---|
| **AS signer** | `Sign` bằng key issuer được chỉ định, đọc public metadata. | Export private key, admin/delete, decrypt tất cả databases. |
| **Orders RS** | Đọc trusted public JWKS, verify local. | `Sign` bằng AS issuer key, đọc HS256 secret của API khác. |
| **OAuth confidential client** | Dùng client private key/secret đã đăng ký. | Dùng AS issuer private signing key. |
| **Token metadata encryptor** | `Encrypt`/`GenerateDataKey` cho kho dữ liệu của mình. | Decrypt dữ liệu của service khác. |
| **Token metadata decryptor** | `Decrypt` được giới hạn context/records. | Thay key policy, export KEK/root key. |
| **Key rotation controller** | Create/version/activate theo workflow duyệt. | Tự cấp quyền đọc mọi secret cho chính mình. |
| **Security auditor** | Metadata/operation logs với RBAC. | Đọc raw private keys hoặc bearer tokens để “audit”. |
| **Break-glass operator** | Quyền khẩn cấp ngắn hạn, có approval/audit. | Quyền admin thường trực không giám sát. |

Một HSM/KMS có thể phân operation ở mức key object; **cấp quyền quản lý toàn bộ vault** chỉ để ứng dụng gọi Sign là quá rộng.

### 11.2. Authentication không đồng nghĩa authorization

Một service account có credential hợp lệ **không mặc nhiên** được decrypt mọi KEK. KMS phải kiểm resource/key policy, operations và context. Tương tự, OAuth client xác thực `private_key_jwt` thành công không có nghĩa client được cấp mọi `scope`; Authorization Server còn kiểm grant/consent/audience/user permissions.

### 11.3. Dual control và break-glass

Với khóa issuer giá trị cao, có thể dùng:

- Phê duyệt hai người cho key disable/delete/rotation nguy hiểm.
- Break-glass token ngắn hạn và bắt buộc ghi lý do/audit.
- IAM key policy được review/code-as-policy, không chỉnh tay âm thầm.
- Tách key admin, AS operator và security auditor.
- Alert khi `Sign` từ identity/vùng địa lý/giờ bất thường.
- Định kỳ test quyền **deny** của các RS và non-production workloads.

**Không coi multi-person approval là thay thế kỹ thuật khóa non-exportable/least privilege**; các lớp cần bổ sung nhau.

### 11.4. Tránh key IDs bị user điều khiển

Các API như:

~~~text
POST /sign?keyId=as-signing-prod
POST /decrypt?keyId=payments-root
~~~

rất nguy hiểm nếu key ID hoặc operation đến từ untrusted request mà backend **không kiểm mục đích**. Ứng dụng nên chọn keyRef từ trusted configuration/grant policy; không dùng `kid` của JWT, `tenant_id` trong body hoặc user email để điều khiển KMS key selection.

## 12. Key storage cho JWT signing: KeyStore, JWKS và rotation

### 12.1. Phân biệt nơi ký và nơi verify

~~~text
Authorization Server:
  private signing key -> KMS/HSM or protected keystore
  public signing key  -> trusted issuer JWKS

Resource Server:
  issuer JWKS public keys -> HTTPS cache with bounded lifetime
  no access to issuer private key
~~~

Với `RS256`/`PS256`/`ES256`/`EdDSA`, RS chỉ cần public key tương ứng. Với `HS256`, RS dùng shared secret và do đó có khả năng tạo MAC — đây là quyết định trust quan trọng.

### 12.2. Public JWKS không phải private vault

Một public JWK RSA thông thường:

~~~json
{
  "kty": "RSA",
  "kid": "as-signing-2026-11",
  "use": "sig",
  "alg": "RS256",
  "n": "EXAMPLE_PUBLIC_MODULUS_BASE64URL",
  "e": "AQAB"
}
~~~

`n` ở trên là **placeholder**. Public JWKS **không bao giờ** công bố RSA private `d`/`p`/`q`, EC/OKP private `d` hoặc JWK `kty=oct` kèm `k` là symmetric secret.

`kid` chỉ là **key selector**; RS phải tìm trong key set lấy từ trusted issuer, không fetch attacker `jku`/`x5u` hoặc load key file theo `kid`.

### 12.3. Rotation bình thường cần giữ old public key khi còn token

~~~text
T0:    Signer signs JWTs with private K1
T1:    Publish public K2 alongside public K1
T2:    Verify RS caches can resolve K2
T3:    AS signs new JWTs with private K2
T4:    K1 becomes verify-only; no new tokens signed with K1
T5:    Last authorized K1-signed JWT expires + safety margin
T6:    Remove public K1 from trusted JWKS; retire K1
~~~

Quy tắc giữ K1 chỉ áp dụng khi K1 **chưa bị compromise**. Nếu private K1 bị lộ, **không tiếp tục tin K1 chỉ để giữ trải nghiệm**, vì attacker có thể ký token giả. Emergency cutoff, revoke/deny/reissue theo playbook riêng.

### 12.4. KMS key version và JOSE `kid` phải có mapping rõ

`kid` trong JWT header có thể là identifier do AS chọn, **không nhất thiết giống physical KMS resource ID**. Một bảng mapping phía issuer có thể quản lý:

~~~text
JOSE kid "as-rsa-2026-11"
    -> KMS key reference "kms/prod/as-token-signing/version-7"
    -> public JWK fingerprint/alg=RS256
    -> lifecycle=ACTIVE
~~~

Không dùng input `kid` do client đưa để cấp quyền gọi arbitrary KMS key. Thay đổi mapping phải atomic, auditable và bảo đảm header `kid` tương ứng đúng private key được dùng.

### 12.5. Rotation key không tự thu hồi tất cả token

- Access JWT đã ký K1 **có thể còn hợp lệ** tới `exp` khi public K1 vẫn được trust.
- Refresh tokens thường do AS quản lý riêng; đổi signing key **không tự revoke refresh family**.
- OIDC ID token cho client và access JWT cho RS có audience/purpose khác nhau.
- Token bị đánh cắp vẫn có thể replay tới lúc RS từ chối; ký mới không tự cắt phiên cũ.
- Nếu cần revoke theo user/grant ngay, bổ sung state, denylist, opaque introspection hoặc short TTL theo threat model.

### 12.6. HMAC key rotation khó hơn public JWKS

Nếu `HS256` được dùng:

- Signer và tất cả verifiers cần có secret K2 trước khi phát token mới.
- Các verifiers có thể cần chấp nhận K1/K2 trong cửa sổ giới hạn.
- Secret K1 phải bị gỡ từ tất cả workloads/CI/secret versions sau retirement.
- Không công bố HMAC K2 qua public JWKS để “giải quyết rollout”.
- Lộ shared HMAC secret có thể cho phép token forgery; phải emergency rotate, không chờ hết TTL của token chỉ vì lịch.

## 13. Khóa của OAuth Client, mTLS, DPoP và người dùng cuối

### 13.1. `private_key_jwt`: khóa của client, không phải issuer

Một confidential client có thể dùng `private_key_jwt` để ký client assertion tại **token endpoint**. Client giữ private key của mình (KMS/HSM/keystore phù hợp), AS kiểm bằng public key đăng ký cho **đúng client_id**. Không dùng private signing key của issuer để xác thực mọi client, và không biến client assertion thành access token.

~~~text
shop-bff:
  client private key  -> signs client assertion
AS:
  registered shop-bff public key -> verifies assertion
AS issuer private key -> signs ID/access JWTs if authorized
RS:
  issuer public JWKS -> verifies access JWTs
~~~

### 13.2. `client_secret_jwt` và `client_secret_basic`

Nếu dùng client secret/shared secret:

- Secret phải ở confidential backend, không nhúng vào SPA/mobile/public browser.
- Lưu bằng Secret Manager/credential provider, giới hạn quyền, rotate theo registration.
- Không dùng client secret làm JWT issuer signing key hoặc AES data encryption key.
- Đừng để token endpoint/client log raw `Authorization: Basic` hoặc signed assertion.

### 13.3. mTLS private key và certificate

mTLS client private key có thể nằm trong HSM, TPM, OS credential store hoặc file keystore có ACL chặt. Certificate/public key có thể công bố; private key phải được bảo vệ. Khi TLS terminate ở gateway, backend không tự tin `X-Client-Cert` từ request ngoài; cần authenticated proxy channel và certificate identity binding đúng profile.

### 13.4. DPoP key ở browser/mobile/server

**DPoP** dùng private key của token holder để ký proof-of-possession, không phải issuer signing key.

| Môi trường | Lựa chọn key storage | Rủi ro cần xét |
|---|---|---|
| **Server/BFF** | KMS/HSM hoặc protected workload key store. | Workload compromise gọi Sign, replay proof, key rotation coordination. |
| **Mobile** | Android Keystore / Apple Secure Enclave/Keychain khi algorithm/profile hỗ trợ. | Device compromise, app/process access, exportability theo hardware. |
| **Browser SPA** | WebCrypto non-extractable `CryptoKey` khi hỗ trợ profile; BFF có thể giảm việc đưa token vào browser. | XSS vẫn có thể lợi dụng key để ký **khi code chạy trong origin**, non-extractable không ngăn mọi misuse. |
| **Desktop** | OS credential/TPM-backed store khi hỗ trợ. | Malware chạy dưới user/process identity, platform portability. |

Không hứa “non-extractable WebCrypto key” loại bỏ hoàn toàn XSS: attacker có script chạy trong origin có thể gọi crypto API theo quyền app.

### 13.5. Key rotation làm thay đổi token binding

Access token DPoP/mTLS đã bound với key/certificate K1 **không tự trở thành token bound với K2** khi client rotate. Client/AS cần cấp token mới hoặc reauthorize theo profile. RS phải kiểm proof/certificate binding đúng token, không “bỏ qua do K2 vừa được rotate”.

## 14. Cryptographic key storage khác với token storage

### 14.1. Tách ba nơi lưu

~~~text
Key store:
  AS private signing key, KEK, DEK, HMAC secrets, client signing keys

Token/grant store:
  opaque token fingerprint, subject, scope, audience, expiry, revoked_at
  refresh token family / rotation state / grants

Application session store:
  BFF session ID, CSRF state, authorized client reference, login session
~~~

Ba lớp có thể dùng công nghệ tương tự (database/Redis/KMS), nhưng **mục đích và quyền khác nhau**. Lưu raw refresh token vào Secret Manager không tự biến nó thành signer key; lưu private issuer key cùng bảng opaque token metadata có thể tăng blast radius nếu DB bị compromise.

### 14.2. Opaque token thường là random reference credential

Một opaque access token dùng CSPRNG có thể được lưu lookup bằng **SHA-256/HMAC fingerprint** thay vì raw token khi thiết kế phù hợp; server giữ grant/scope/expiry/revoked state. Nó **khác** lưu private signing key. Token còn active dù key store rotate nếu grant/token state không thay đổi.

### 14.3. JWT và access-token purpose

Nếu RS verify JWT qua public JWKS, RS **không cần truy cập private key**. Nó vẫn phải kiểm `iss`, `aud`, `exp`, `scope`, loại token và quyền tenant/object. Nếu dùng opaque access token, RS thường introspect AS theo RFC 7662; key storage lúc này chủ yếu bảo vệ **introspection caller credential, AS backend keys và encryption keys của token store**, không cần ép opaque token có JWS payload.

### 14.4. Refresh token theft không được chữa chỉ bằng key rotation

Refresh token bị lấy có thể cho attacker xin access tokens mới theo grant nếu không bị revoke hoặc bound. Đổi private signing key của AS **không thu hồi refresh family**. Cần refresh rotation/reuse detection, revocation (RFC 7009), short-lived access tokens, client authentication và token store security riêng.

### 14.5. Token logging và key logging đều phải chặn

Không log:

~~~text
Authorization: Bearer <raw access token>
refresh_token=<raw refresh token>
client_secret=<raw client secret>
private_key_pem=<raw signing key>
HSM_PIN=<raw pin>
KMS_EXPORT_KEY=<raw key>
Cookie: <session credential>
~~~

Đừng chỉ redaction các JWT có dấu chấm; **opaque tokens và random secrets không có cấu trúc** vẫn là credentials. Thực hiện log allowlist ở HTTP client/server middleware, APM và error handling.

## 15. Vòng đời khóa từ khởi tạo đến hủy

### 15.1. Trạng thái logic

~~~mermaid
stateDiagram-v2
    [*] --> GENERATED
    GENERATED --> STAGED: Protected storage and policy approved
    STAGED --> ACTIVE: Key allowed for new operations
    ACTIVE --> RETIRING: Stop new signatures or encryption
    RETIRING --> VERIFY_ONLY: Public verification still needed
    RETIRING --> DECRYPT_ONLY: Old ciphertext still needs key
    VERIFY_ONLY --> RETIRED: No accepted tokens require key
    DECRYPT_ONLY --> RETIRED: Rewrap or reencrypt completed
    RETIRED --> DESTROYED: Approved secure destruction
    ACTIVE --> COMPROMISED: Exposure or unauthorized operation
    STAGED --> COMPROMISED: Exposure before use
    COMPROMISED --> DISABLED: Emergency deny and replacement
    DISABLED --> DESTROYED: Approved final destruction
~~~

Các trạng thái là **mô hình quản trị**, không phải enums tiêu chuẩn của KMS/JWK. Không phải mọi key đi qua cả `VERIFY_ONLY` và `DECRYPT_ONLY`; điều đó phụ thuộc purpose. Ví dụ:

- JWS RSA private signing key dừng ký; public key có thể ở verify-only.
- KEK cũ có thể cần dùng để **unwrap/decrypt** DEKs của các bản ghi cũ.
- HMAC secret có thể tạm được phép kiểm tokens cũ, nhưng bản thân nó **vẫn là signing secret nếu bị lộ**; không gọi HMAC “verify-only” theo bảo đảm cryptographic.
- DPoP/mTLS key cũ có thể được ngừng dùng và tokens bound với nó cần phát lại.

### 15.2. Cryptoperiod và rotation triggers

Không có “cứ 30 ngày” là quy tắc đúng cho mọi khóa. Cryptoperiod cần dựa trên:

- Thuật toán/key strength và chuẩn áp dụng.
- Lượng dữ liệu hoặc số chữ ký/operations, provider limits.
- Kỹ thuật/chi phí rotation, số lượng RS và token TTL tối đa.
- Quy định quản trị, compliance và vòng đời certificates.
- Ảnh hưởng của compromise: issuer key khác key mã hóa một field.
- Khả năng kiểm toán, backup/restore và nhu cầu giữ dữ liệu lâu dài.
- Thu hồi key do incident, thay đổi quyền nhân sự hoặc phát hiện lộ secret.

Một chính sách có thể có **periodic review**, **scheduled rotation** và **emergency rotation** độc lập. Không chỉ rotate theo lịch rồi bỏ qua bất thường `Sign`/`Decrypt`.

### 15.3. Key state phải được kiểm ở thời điểm operation

~~~text
request to sign a new JWT:
    require key state == ACTIVE and operation SIGN allowed

request to verify a valid older JWT:
    require public key still trusted for token profile and issuer

request to decrypt old encrypted record:
    require KEK version authorized to unwrap and data access allowed

request to export private key:
    deny unless explicitly allowed by narrow, audited key policy
~~~

Một alias/`kid` có cùng tên nhưng key material mới sẽ tạo ambiguity trong logs/caches. **Key version phải không tái sử dụng tùy tiện**; nếu rotate, tạo key/version ID mới và mapping rõ.

### 15.4. Không “khôi phục ACTIVE” một khóa đã bị compromise

Private key K1 bị lộ không nên được đưa lại vào `ACTIVE` khi người vận hành đổi password keystore. Password mới **không khiến kẻ đã sao chép K1 mất bản sao**. Phải dùng key material mới, loại trust với K1 và đánh giá token/ciphertext liên quan.

## 16. Backup, phục hồi và tính sẵn sàng của key store

### 16.1. Mất khóa đôi khi nghiêm trọng hơn mất ciphertext

Nếu xóa nhầm KEK duy nhất giải bọc DEK của dữ liệu production, các backups ciphertext có thể **không giải mã được**. Vì vậy backup dữ liệu mà không có **khả năng phục hồi key versions và policies** không phải backup hoàn chỉnh.

Ngược lại, nếu backup private issuer signing key bằng file có thể copy và đặt ở storage công khai, availability được cải thiện nhưng confidentiality bị phá.

### 16.2. Phân biệt backup key và export raw key

Một số KMS/HSM hỗ trợ **provider-managed replication/backup**, HA clusters hoặc wrapped key backups mà **không cho raw key export**. Phải dùng cơ chế đúng key class/provider. Nếu non-exportable private key không thể mang ra ngoài, kiến trúc DR phải giải quyết **key availability** qua replica/cluster hoặc issuance service migration, không kỳ vọng sao chép PEM.

### 16.3. Hai chiến lược DR cho issuer signing key

| Chiến lược | Lợi ích | Rủi ro/đánh đổi |
|---|---|---|
| **Cùng logical signing key replicated trong managed HSM/KMS** | Failover có thể tiếp tục ký JWT xác minh bằng public key cũ. | Phụ thuộc provider replication, IAM và cách bảo vệ cùng key ở nhiều vùng. |
| **Key riêng ở DR region** | Tách key material và giới hạn blast radius theo vùng. | RS phải biết public JWKS của DR key; switch issuer signer/`kid`, prepublish, approval và recovery tests. |

Không thể bảo đảm phương án nào khả dụng ở mọi cloud/HSM. Cần kiểm rõ **key class, replication semantics, key availability SLO và legal/compliance constraints**.

### 16.4. Backup/restore encryption keys

Checklist DR:

1. Biết **KEK version** nào mở từng wrapped DEK và vùng/tenant của chúng.
2. Backup data ciphertext, wrapped DEK, nonce/tag, AAD context và metadata key reference.
3. Backup/preserve key policy mappings và access controls phù hợp.
4. Đánh giá RPO/RTO, multi-region replication và consistency của key state.
5. Test restore trong **môi trường test cô lập** với keys/records test.
6. Test khả năng decrypt bản ghi cũ sau khi rotate/re-wrap.
7. Kiểm accidental deletion/quarantine/disabled keys và cách phục hồi.
8. Không chép unwrapped DEKs/private KEKs vào ticket hoặc file log khi test.
9. Định nghĩa khi nào một key có thể **destroy an toàn** mà không mất dữ liệu cần giữ.
10. Audit restore operation, approval và identity đã dùng.

### 16.5. Khả năng xác minh JWT khi AS signer down

Với JWT được ký bất đối xứng, RS có thể tiếp tục **verify local bằng public JWKS cached** theo chính sách, dù KMS signer của AS tạm không sẵn sàng. Tuy nhiên client có thể không nhận access tokens mới/refresh được; đây là vấn đề availability ở **token issuance**, không phải private key cần đưa cho RS.

Không để RS tự ký access token bằng public key hoặc shared secret fallback trong lúc AS down.

## 17. Java 17: đọc PKCS#12 để hiểu giới hạn file keystore

Đoạn code sau minh họa **legacy/local keystore** cần mở bằng password. Nó không phải giải pháp ưu tiên cho issuer signing key rủi ro cao nếu KMS/HSM non-exportable sẵn có.

### 17.1. Đọc khóa theo alias cố định

~~~java
import java.io.IOException;
import java.io.InputStream;
import java.nio.file.Files;
import java.nio.file.Path;
import java.security.GeneralSecurityException;
import java.security.Key;
import java.security.KeyStore;
import java.security.PrivateKey;
import java.security.PublicKey;
import java.security.cert.Certificate;
import java.util.Objects;

public final class Pkcs12SignerStore {
    private Pkcs12SignerStore() {}

    public record SigningKey(
        PrivateKey privateKey,
        PublicKey publicKey
    ) {}

    public static SigningKey load(
            Path protectedPath,
            char[] storePassword,
            char[] entryPassword,
            String trustedAlias
    ) throws IOException, GeneralSecurityException {

        Objects.requireNonNull(protectedPath);
        Objects.requireNonNull(storePassword);
        Objects.requireNonNull(entryPassword);
        Objects.requireNonNull(trustedAlias);

        KeyStore keyStore = KeyStore.getInstance("PKCS12");
        try (InputStream input = Files.newInputStream(protectedPath)) {
            keyStore.load(input, storePassword);
        }

        Key entry = keyStore.getKey(trustedAlias, entryPassword);
        if (!(entry instanceof PrivateKey privateKey)) {
            throw new GeneralSecurityException(
                "Configured signing key unavailable"
            );
        }

        Certificate certificate =
            keyStore.getCertificate(trustedAlias);
        if (certificate == null) {
            throw new GeneralSecurityException(
                "Configured public certificate unavailable"
            );
        }

        return new SigningKey(
            privateKey,
            certificate.getPublicKey()
        );
    }
}
~~~

### 17.2. Không được hiểu nhầm tính an toàn của ví dụ

- `trustedAlias` phải đến từ **server-side trusted configuration**, không từ JWT `kid`/user input.
- Passwords được truyền vào dưới dạng `char[]` từ một secret provider riêng, **không hardcode** trong source/test logs; caller quản lý vòng đời và có thể `Arrays.fill` khi không cần nữa. JVM/providers có thể tạo bản sao nội bộ nên **không thể hứa xóa sạch mọi memory**.
- `Files.newInputStream` đọc keystore file; file ACL, mount, backups và password storage vẫn là trách nhiệm deployment.
- `getKey` trả `PrivateKey` vào application context. **Đây không phải non-exportable HSM usage**; key có thể tồn tại trong memory nếu provider hỗ trợ export.
- Tên file và alias không đủ chứng minh **issuer/kid/algorithm**. Cần kiểm key metadata và trust/policy trước khi dùng.
- Không đưa `privateKey.toString()`/`getEncoded()` vào logs hoặc diagnostics.
- Nếu keystore/file bị thay trái phép, ứng dụng có thể ký nhầm key. Bảo vệ integrity và xác minh public-key fingerprint/mapping.
- Đừng dùng mẫu trên trong browser/mobile hoặc cho RS chỉ cần public verify.

### 17.3. Ký bằng KMS/HSM thay vì load private key

Khi dùng operation-based key, abstraction nên đại diện **quyền ký bằng key reference**, không buộc mọi signer trả `PrivateKey`:

~~~java
public interface ExternalJwtSigner {
    // The implementation authenticates a workload to KMS/HSM.
    // It must enforce permitted issuer, algorithm, key and purpose.
    byte[] signJwsInput(byte[] exactJwsSigningInput)
        throws SigningUnavailableException;
}

public final class SigningUnavailableException extends Exception {
    public SigningUnavailableException(String message) {
        super(message);
    }
}
~~~

Đây là **hợp đồng minh họa**; adapter thực tế phải khai báo rõ algorithm như `RS256`/`PS256`, digest handling, raw-vs-prehashed input, signer permissions, key version/`kid` và JOSE signature encoding. Với ECDSA, provider có thể trả DER trong khi JWS ES256 yêu cầu raw `R || S`. **Không tự xây JWT bằng cách Base64 arbitrary signature nếu chưa biết chuẩn JOSE**; ưu tiên JOSE library/adapter có kiểm thử.

### 17.4. Xác minh không cần đọc private key

Ở RS, Spring Security có thể dùng public JWKS:

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://login.example.com
          jwk-set-uri: https://login.example.com/oauth2/jwks
~~~

Cấu hình chỉ minh họa **issuer và JWKS tin cậy** (metadata phải được kiểm đối chiếu theo deployment). Trong ứng dụng thực, cần thêm audience validator, token purpose/algorithm allowlist và API authorization. **Không nhúng private signing key trong `application.yml` của RS**.

## 18. Java JCA: AEAD cho data at rest và vai trò của KMS

Một ví dụ **AES-GCM** cho thấy cách dùng DEK sau khi được một trusted key provider cấp/unwrap. Đây là đoạn minh họa thao tác trên **dữ liệu**, không phải code tự tạo KEK hoặc thay thế KMS.

### 18.1. Mã hóa bằng DEK, nonce mới và AAD

~~~java
import java.security.SecureRandom;
import java.util.Arrays;
import javax.crypto.Cipher;
import javax.crypto.SecretKey;
import javax.crypto.spec.GCMParameterSpec;

public final class AesGcmRecordCipher {
    private static final SecureRandom RNG = new SecureRandom();
    private static final int NONCE_BYTES = 12;
    private static final int TAG_BITS = 128;

    private AesGcmRecordCipher() {}

    public record SealedRecord(
        byte[] nonce,
        byte[] ciphertextAndTag
    ) {}

    public static SealedRecord seal(
            SecretKey dek,
            byte[] plaintext,
            byte[] aad
    ) throws Exception {

        byte[] nonce = new byte[NONCE_BYTES];
        RNG.nextBytes(nonce);

        Cipher cipher = Cipher.getInstance("AES/GCM/NoPadding");
        cipher.init(
            Cipher.ENCRYPT_MODE,
            dek,
            new GCMParameterSpec(TAG_BITS, nonce)
        );

        if (aad != null) {
            cipher.updateAAD(aad);
        }

        byte[] ciphertextAndTag = cipher.doFinal(plaintext);
        return new SealedRecord(nonce, ciphertextAndTag);
    }

    public static byte[] open(
            SecretKey dek,
            SealedRecord record,
            byte[] expectedAad
    ) throws Exception {

        Cipher cipher = Cipher.getInstance("AES/GCM/NoPadding");
        cipher.init(
            Cipher.DECRYPT_MODE,
            dek,
            new GCMParameterSpec(TAG_BITS, record.nonce())
        );

        if (expectedAad != null) {
            cipher.updateAAD(expectedAad);
        }

        // Fails authentication on invalid key, AAD, nonce or tag.
        return cipher.doFinal(record.ciphertextAndTag());
    }
}
~~~

### 18.2. Ràng buộc bảo mật của code

- `dek` phải là **AES key được cấp bằng nguồn đáng tin**, không phải HMAC signer key hoặc password trực tiếp. Code không quản lý KEK, `wrapped_dek` hoặc quyền KMS.
- `nonce` 96-bit ngẫu nhiên từ CSPRNG có xác suất trùng nhỏ ở số bản ghi giới hạn, nhưng **không bảo đảm tuyệt đối duy nhất** khi dùng số lượng rất lớn dưới cùng key. Hệ thống phải quản lý hạn mức/nonce strategy theo chuẩn cho mỗi key, đặc biệt khi scale cao hoặc có nhiều writers.
- `ciphertextAndTag` là bytes theo Java AEAD convention; lưu cùng nonce và metadata version/AAD đúng schema.
- `AAD` phải được dựng từ **trusted record metadata**. Nếu record/tenant bị thay, decryption cần fail, không “thử lại với AAD rỗng”.
- Không bỏ exception authentication failure để trả plaintext giả; từ chối và audit lỗi theo mức phù hợp.
- `SecretKey`/plaintext có thể còn trong RAM; hạn chế lifetime, log, heap dump và không tin `Arrays.fill` sẽ xóa được mọi bản sao.
- Dùng library hoặc storage encryption service đã được bảo trì thay vì tự viết đầy đủ envelope framework nếu có lựa chọn thích hợp.
- AES-GCM encryption **không tạo JWT signature**, và không thay access-token validation.

### 18.3. Adapter envelope storage phải quản lý version

~~~text
encrypt(record):
    context = validated(service, environment, tenant, recordId)
    (plaintextDEK, wrappedDEK) = kms.generateDataKey(KEK, context)
    ciphertext = AEAD.encrypt(plaintextDEK, uniqueNonce, data, AAD=context)
    store(ciphertext, nonce, tag, wrappedDEK, KEKversion, context)
    limit plaintextDEK exposure

decrypt(record):
    verify caller may access record/tenant
    dek = kms.decryptWrappedKey(record.wrappedDEK,
                                record.KEKversion,
                                expectedContext)
    plaintext = AEAD.decrypt(dek, record.nonce,
                             record.ciphertext, expectedAAD)
    return plaintext only to authorized caller
~~~

`generateDataKey`/`decryptWrappedKey` là pseudocode; SDK cụ thể khác nhau. KMS có thể cung cấp trực tiếp ciphertext DEK và plaintext DEK. Quan trọng: **context, KEK version và rights kiểm trước giải mã**.

## 19. Spring/AS integration: cấu hình không được chứa raw signer key

### 19.1. Mô hình cấu hình đề xuất

~~~yaml
# MINH HỌA - không phải cấu hình auto-enable cho mọi Spring AS.
tokenSigning:
  issuer: https://login.example.com
  algorithm: RS256
  joseKeyId: as-signing-2026-11
  keyProvider: managed-kms
  keyReference: keys/prod/as-jwt-signing/v7
  allowRawPrivateKeyExport: false

  # Implementation must bind all these values to trusted config.
  expectedTokenProfiles:
    - access-jwt
    - oidc-id-token
~~~

Các thuộc tính `tokenSigning` là **policy/config minh họa**, không phải properties chuẩn có hiệu lực tự động của Spring Authorization Server. Cần custom signer/KMS adapter và cấu hình token generator/JWK source phù hợp phiên bản.

### 19.2. Signing policy ở AS

~~~text
Token endpoint validates grant/client/principal first
    -> derive issuer, audience, scope, claims from trusted policy
    -> choose active signer key from trusted server mapping
    -> build exact JWS header and signing input
    -> KMS/HSM signs under allowed operation
    -> return token, never private key
~~~

Không nhận `keyRef`/`alg` từ request browser hoặc `kid` do client tự chọn để điều khiển AS signing operations.

### 19.3. Resource Server phải độc lập quyền Sign

Các RS có thể dùng Spring `NimbusJwtDecoder` với issuer/JWKS public keys, thuật toán JWS allowlist và audience validation. Đừng cấu hình chung `PRIVATE_RSA_PEM` qua shared Helm chart cho cả AS lẫn RS chỉ để giảm số settings.

### 19.4. Thay key provider không phải thay OAuth grant semantics

Chuyển từ PKCS#12 sang KMS/HSM **không thay** `iss`/`aud`/`scope`/grant. Nhưng có thể thay public key/`kid` và signature provider details, do đó phải quản lý migration, JWKS overlap, JWT profiles và ảnh hưởng đến RS/OIDC Clients.

## 20. Quyền truy cập dữ liệu mã hóa và key management

### 20.1. Có ciphertext không có nghĩa được decrypt

Nếu database dump bị lộ nhưng KEK nằm ở KMS khác trust boundary, attacker có thể chưa giải mã được wrapped DEKs. Tuy nhiên nếu attacker cũng có workload identity với `Decrypt` toàn bộ records, data-at-rest encryption không còn bảo vệ. Thiết kế phải tách:

~~~text
Data access / SQL permission
KMS key operation permission
Record-level tenant/object authorization
Runtime identity and network boundary
~~~

Với một API decrypt:

1. Xác thực caller theo trust model.
2. Kiểm ownership/tenant/permissions trên record.
3. Chọn expected KEK/context theo trusted metadata.
4. Chỉ gọi KMS nếu policy cho phép.
5. Verify AEAD tag/AAD, không trả plaintext từ bản ghi không thuộc quyền.
6. Audit metadata cần thiết, không log plaintext/DEK/token.

### 20.2. Mã hóa không xóa rủi ro của administrators

DB admin có thể có toàn bộ ciphertext; KMS admin có thể thay key policy; deployment admin có thể cấp service quyền mới. Cần **separation of duties**, approvals và logs để không một tài khoản thông thường vừa đọc toàn bộ dữ liệu vừa cấp được mọi quyền decrypt.

### 20.3. Storage encryption không thay transport encryption

Ngay cả khi DEK/KEK được giữ an toàn, token hoặc plaintext vẫn có thể lộ **trên đường truyền** nếu ứng dụng gọi API không dùng TLS. Ngược lại TLS không bảo vệ dữ liệu **sau khi** HTTP request được ghi vào log. Bảo vệ đầy đủ cần at-rest, in-transit và in-use controls.

### 20.4. Cross-tenant rewrap phải giữ context

Nếu database migrate record từ tenant Beta sang Anpha, không được chỉ đổi `tenant_id` trong metadata rồi dùng một wrapped DEK cũ. Phải có authorization cho migration, xác minh dữ liệu, reencrypt/rewrap với AAD/context mới nếu scheme yêu cầu, audit actor và không cho service thường di chuyển ciphertext giữa tenants để bypass quyền.

## 21. Threat model: những lỗi key storage gây hậu quả lớn

| Lỗi hoặc tấn công | Vì sao nguy hiểm | Phòng vệ và xác minh |
|---|---|---|
| Private issuer key commit vào Git | Người có lịch sử repo có thể ký token giả. | Secret scanning/history review, emergency rotate; không chỉ xóa dòng hiện tại. |
| HMAC secret để trong browser/mobile | Client công khai có thể bị phân tích và trích secret. | Không dùng public client làm nơi giữ shared JWT signing secret. |
| Khóa AS nằm ở mọi Resource Server | Compromise RS trở thành issuer key compromise. | RS chỉ dùng trusted public verification key. |
| Public JWKS vô tình có `d` hoặc `kty=oct` | Private/symmetric secret bị công bố. | Automated tests bảo đảm chỉ public JWK fields. |
| JWT header `kid` dùng chọn KMS keyRef | Attacker có thể khiến signer/RS chọn key trái quyền. | Server-owned key mapping và JOSE key allowlist. |
| JWT `jku`/`x5u` được fetch tùy ý | SSRF, lấy attacker key, trust bypass. | Chỉ issuer-pinned JWKS/registered key sources. |
| KMS `Sign` được cấp cho mọi workload | Service bị chiếm tạo token giả. | Per-key/per-operation workload IAM, alerts. |
| KMS `Decrypt` cấp cho service đọc nhiều tenants | Có quyền unwrap DEK của dữ liệu ngoài phạm vi. | Encryption context, record-level auth và tenant-scoped policy. |
| Secret Manager policy quá rộng | Một service đọc secrets dev/staging/prod cùng lúc. | Environment/resource segmentation, deny tests. |
| Encrypted `.p12` và password cùng Docker image | Attacker lấy cả file lẫn password từ artifact. | Secret delivery tách biệt, production image không chứa secrets. |
| PEM file có quyền đọc rộng | User/container khác trích private key. | File ACL, mount isolation, backups và host hardening. |
| Log private key do debug `toString` | APM/log trở thành kho keys. | Log allowlist, diagnostics restrictions, canary secret tests. |
| Core dump/heap snapshot không bảo vệ | Raw key/DEK hiện diện trong process memory bị lấy. | Hạn chế dumps, RBAC, retention, non-exportable operations khi có thể. |
| Dùng same key cho AES và HS256 | Key-use confusion và blast radius liên giao thức. | Separate keys, supported KDF/domain separation nếu cần. |
| AES-GCM nonce lặp dưới cùng DEK | Confidentiality/integrity có thể bị phá. | Unique nonce strategy, key use limits, AEAD library. |
| Wrapped DEK lưu nhưng xóa KEK quá sớm | Không giải mã được dữ liệu lịch sử. | Key version mapping, retention và restore tests trước destroy. |
| Chỉ rotate KEK sau khi DEK lộ | Attacker vẫn có plaintext DEK cũ. | Reencrypt với DEK mới và điều tra bản ghi bị ảnh hưởng. |
| Private signing key K1 bị lộ nhưng giữ verify-only | Attacker tiếp tục phát chữ ký K1 hợp lệ. | Emergency deny key, invalidate token trust, reissue. |
| Public K1 bị xóa quá sớm khi rotate bình thường | JWT còn hạn bị RS từ chối hàng loạt. | Prepublish K2/overlap verify có giới hạn. |
| `kid` ngẫu nhiên kích JWKS refresh vô hạn | DoS issuer/RS hoặc vượt quota. | Bounded refresh, rate limits và fail-closed. |
| KMS outage dẫn đến fallback ký bằng key hardcoded | Bypass key custody và tăng lộ key. | Không có insecure signer fallback; controlled 503/availability policy. |
| Root Vault credential trong source | Attacker mở toàn bộ kho keys. | Workload identity, short-lived scoped auth, break-glass riêng. |
| KMS import key không đáp ứng export policy | Sai kỳ vọng non-exportable hoặc migration không thể thực hiện. | Kiểm vendor/key class, backup, export/deletion semantics. |
| Backup chứa plaintext private keys không bảo vệ | Cold backups trở thành bản sao key lâu dài. | Provider-managed backup/KEK, IAM, encryption, retention. |
| Restore key nhưng sai key version/context | Data decrypt fail hoặc mở nhầm ranh giới tenant. | Key version + AAD integrity + restore rehearsal. |
| AS gửi JWKS public key của attacker | Các RS tin một signer không phải issuer thật. | JWKS endpoint integrity, deployment approvals, key fingerprint monitoring. |
| XSS sử dụng DPoP `CryptoKey` non-extractable | Script độc hại vẫn gọi ký trong origin. | XSS/CSP defense, BFF khi phù hợp, token lifetime/PoP policy. |
| mTLS private key bị copy sang máy khác | Client impersonation nếu certificate còn trusted. | Non-exportable device/HSM key khi phù hợp, cert revoke/rotate. |
| Token được verify đúng nhưng sai audience | Key trust được dùng sai mục đích. | RS kiểm `iss`/`aud`/`typ`/`scope` và object ACL. |
| KMS signing endpoint cho user tự truyền raw claims | Kẻ có API access khiến AS ký token admin. | AS authorization policy trước ký, signer không public arbitrary input. |
| Thu hồi `client_secret` nhưng access/refresh tokens vẫn active | Cred leak có thể còn hậu quả, grant state tồn tại. | Rotation + revoke/assess grants/token families, không chỉ đổi secret. |

### 21.1. Mã hóa at rest không tự giải quyết runtime compromise

Nếu attacker đã chạy code dưới **chính service identity có quyền Decrypt**, họ có thể gọi KMS để giải mã, dù raw KEK không xuất được. KMS/HSM giảm **key exfiltration** và quản trị phạm vi sử dụng, nhưng không thay **application authorization**, workload integrity, network isolation và behavior monitoring.

### 21.2. “Không xuất được key” có thể vẫn bị dùng để ký sai

Khi attacker chiếm AS workload có quyền `Sign`:

~~~text
Attacker does not obtain raw private key bytes
But attacker may invoke permitted Sign API on unauthorized JWT content
    -> Forged access token signature from trusted issuer key
~~~

Vì vậy signer API không nên trực tiếp nhận payload chưa được policy xét từ HTTP client; issuance pipeline phải tính claims từ grant/client/principal tin cậy, và IAM có thể giới hạn service/keys/algorithms/rates.

### 21.3. Không sử dụng password làm trực tiếp AES/HMAC key

Một passphrase do người dùng nhập thường **không có entropy tương đương key ngẫu nhiên**. Nếu bài toán buộc derive key từ password, cần **password-based KDF đã được đánh giá**, salt/cost parameters đúng threat model; không dùng `SHA256(password)` trực tiếp làm master key cho mọi dữ liệu. Với issuer JWT signing, **dùng CSPRNG hoặc key generation provider**, không dùng password derivation tùy tiện.

## 22. Ứng cứu sự cố: key lộ, bị dùng sai hoặc không thể khôi phục

### 22.1. Tình huống A — Private JWT signer key lộ

Đội phát hiện một private RSA key K1 đã bị đính kèm vào CI artifact public. AS đang ký `RS256` access JWTs bằng K1; JWKS còn công bố public K1.

**Ứng cứu:**

1. **Containment:** chặn phát tán artifact/secret, không paste private key vào incident ticket; ghi nhận thời điểm/khoảng tiếp cận.
2. **Tạm khóa quyền nguy hiểm:** vô hiệu export/khóa lộ, kiểm KMS Sign activity và AS issuance có dấu hiệu bất thường.
3. **Phát key K2:** sinh pair mới, bảo vệ private key trong KMS/HSM theo policy; chuẩn bị public K2 trusted JWKS.
4. **Emergency cutoff K1:** RS phải ngừng tin K1 theo phương án đã kiểm thử; không giữ K1 verify-only như normal rotation nếu private key thực sự bị lộ.
5. **Reissue/reauthorize:** xử lý token hợp lệ K1 bị ảnh hưởng, cấp token K2 theo grants thật; áp state/denylist nếu cần và có thể.
6. **Đánh giá forgery:** kiểm audit token issuance, accesses lạ, scopes/audiences bất thường; RS không biết token K1 là “do AS thật” hay “attacker” nếu chỉ nhìn chữ ký.
7. **Kiểm mọi RS/OIDC Clients:** JWKS caches, regional verifiers, offline partners, gateway, mobile clients; đo thời gian cutoff thực tế.
8. **Khắc phục nguồn lộ:** sửa CI artifact policy, image scanning, file permissions, IAM, backups và rotation controls.
9. **Tài liệu hóa quyết định:** mức gián đoạn chấp nhận, incident timeline, user notification theo chính sách và yêu cầu áp dụng.

**Quan trọng:** Xóa private key khỏi artifact hôm nay **không vô hiệu các bản sao đã bị tải trước đó**. Revoke/rotate trust là yêu cầu bảo mật riêng.

### 22.2. Tình huống B — HMAC HS256 key lộ ở RS

Nếu một RS được phép đọc shared secret của AS và bị xâm nhập, kẻ tấn công có thể có khả năng tạo MAC hợp lệ. Phải xem **toàn bộ issuers/RS đang trust key đó**, không chỉ service bị xâm nhập.

Phản ứng có thể gồm: emergency rotate K2, cập nhật các verifiers trong controlled window, revoke/deny tokens K1 theo rủi ro, cắt RS compromise và xem xét chuyển **asymmetric signing** để RS không giữ signing secret nữa.

### 22.3. Tình huống C — Lộ KEK hay DEK?

| Bị lộ/mất | Hậu quả chính | Hướng xử lý |
|---|---|---|
| **Chỉ ciphertext + wrapped DEK** | Chưa đủ decrypt nếu KEK vẫn an toàn. | Kiểm access logs và separation; rotate nếu evidence compromise. |
| **Plaintext DEK** | Dữ liệu được mã hóa bằng DEK đó có thể bị đọc khi attacker có ciphertext. | Sinh DEK mới, reencrypt dữ liệu bị ảnh hưởng; rewrap KEK đơn thuần chưa đủ. |
| **KEK key material/capability `Decrypt`** | Có thể unwrap nhiều DEKs theo quyền/context. | Disable/rotate KEK hoặc IAM quyền, rewrap/re-encrypt theo blast radius, điều tra use logs. |
| **Private issuer signing key** | Có thể ký token giả được trusted verifiers chấp nhận. | Emergency trust cutoff, reissue/revoke, kiểm abuse. |
| **OAuth client private key** | Có thể giả client assertions, xin tokens theo grants/policy. | Rotate client registration key, revoke sessions/grants khi cần. |
| **mTLS/DPoP holder key** | Có thể tạo proof/certificate auth dưới identity holder. | Rotate key/cert, rebind tokens, revoke access tokens cũ theo profile. |
| **KMS data/key lost, not compromised** | Availability/khả năng decrypt hoặc ký mới bị ảnh hưởng. | DR/restore provider-managed backups, không tự tạo key cùng tên rồi mong decrypt được. |

### 22.4. Tình huống D — Key bị xóa hoặc disabled ngoài ý muốn

Nếu KEK bị disabled, có thể **không decrypt dữ liệu** dù ciphertext vẫn còn. Trước khi restore hoặc enable key, phải kiểm **lệnh disable do sự cố bảo mật hay vận hành**, vì một key bị disable do compromise không nên bật lại vô điều kiện.

Đường phục hồi phải có approval, khả năng xác định key version/record mapping và restore rehearsal. Nếu key đã **destroy vĩnh viễn** mà không có replica/backup phù hợp, dữ liệu mã hóa dưới key đó có thể **không khôi phục được**.

### 22.5. “Revoke token” khác “disable signer key”

- **RFC 7009 revocation:** yêu cầu thu hồi token/grant theo protocol AS.
- **Disable/retire signing key:** thay trust của mọi token sử dụng key đó tại verifiers.
- **Đổi OAuth client secret/private key:** thay phương thức client authentication cho các token requests tiếp theo.
- **Xóa BFF session cookie:** không nhất thiết revoke access/refresh tokens.
- **Thay KEK:** không trực tiếp sửa JWT signature hoặc thu hồi access token.

Những thao tác có blast radius khác nhau. **Không dùng emergency issuer-key revocation chỉ để logout một session đơn lẻ** nếu token/grant revocation phù hợp hơn.

## 23. Quan sát, audit và trách nhiệm vận hành

### 23.1. Audit event minh họa

~~~json
{
  "event": "crypto_key_operation",
  "operation": "SIGN",
  "service_identity": "workload/authorization-server/prod",
  "key_reference": "kms/prod/as-signing/v7",
  "jose_key_id": "as-signing-2026-11",
  "algorithm": "RS256",
  "issuer": "https://login.example.com",
  "result": "SUCCESS",
  "policy_version": "2026-11",
  "trace_id": "95b7b48ff42f4acf9b247fcf9421d522"
}
~~~

Đây là event mẫu, không phải log đầy đủ của provider. **Không log private key, plaintext DEK, ciphertext của secrets nhạy cảm, raw access token, client assertion hoặc full JWT payload**. `key_reference`/service identity có thể tiết lộ kiến trúc; giới hạn RBAC và retention.

### 23.2. Các nhóm sự kiện cần phân biệt

~~~text
KEY_CREATED
KEY_POLICY_CHANGED
KEY_ACTIVATED
KEY_ROTATION_STARTED
KEY_SIGN_OPERATION
KEY_DECRYPT_OPERATION
KEY_EXPORT_ATTEMPT_DENIED
KEY_DISABLED
KEY_COMPROMISE_SUSPECTED
KEY_DESTROY_REQUESTED
KEY_DESTROYED
KEY_RESTORED
KMS_AUTHORIZATION_DENIED
JWKS_PUBLIC_KEY_PUBLISHED
JWKS_KEY_RETIRED
SECRET_VERSION_READ
SECRET_VERSION_ROTATED
~~~

Một log `Sign` thành công **không tự xác nhận token issuance là hợp pháp**. Cần đối chiếu số lượng signing operations với số token được AS phát và các grants/authorization decisions hợp lệ; việc tương quan có thể dùng trace IDs/nội bộ có quyền, tránh lộ raw token.

### 23.3. Metrics không chứa raw key identifiers tùy ý

~~~text
kms_sign_requests_total{service,key_group,result}
kms_decrypt_requests_total{service,key_group,result}
kms_operation_latency_seconds{operation,key_group}
kms_permission_denied_total{service,operation}
issuer_key_rotation_phase{issuer,phase}
jwks_unknown_kid_total{issuer}
key_backup_restore_drill_total{result}
key_export_denied_total{key_group}
encrypted_record_decrypt_failure_total{service,reason}
~~~

Tên metric chỉ là ví dụ. Không đưa `kid` attacker kiểm soát, email, raw token, ciphertext hay UUID record tùy ý thành high-cardinality labels.

### 23.4. Alerts giá trị cao

- RS nhận quyền KMS `Sign` hoặc `Decrypt` sau IAM policy change.
- KMS `Sign` từ một identity lạ, ngoài lịch rollout hoặc tăng bất thường.
- Secret Manager `read` production signing secret bởi dev/staging workload.
- `KEY_EXPORT_ATTEMPT_DENIED` lặp lại.
- Public JWKS chứa private JWK fields hoặc symmetric `oct` material.
- JWKS `kid` không đồng bộ với active issuer signer, tăng 401 hàng loạt sau deploy.
- Mất KEK version/backup restore failure.
- Decrypt attempts cross-tenant hoặc AAD mismatch tăng đột ngột.
- KMS outage khiến token issuance không đáp ứng SLA.
- Token có chữ ký hợp lệ nhưng grants/scope không khớp policy.

Không suy luận ngay mỗi spike là tấn công; cần điều tra nguồn đáng tin, nhưng **không tắt signature/issuer/audience validation** chỉ để giảm cảnh báo.

### 23.5. Ownership và runbooks

Mỗi key quan trọng cần có **owner team, approved use, dependency map, cryptoperiod, key backup/recovery policy, rotation and incident runbooks**. Một khóa chưa rõ owner thường dẫn đến rotation bị trì hoãn, quyền đọc quá rộng và thiếu người chịu trách nhiệm khi compromise.

## 24. Ma trận kiểm thử key storage và trust boundary

### 24.1. Test fixtures

~~~text
Environment:
  production-like test only; no production private keys

Issuer:
  https://login.test.example
  JWT alg = RS256
  public JWKS contains test K1/K2 only

Workloads:
  AS-signing-service
  orders-resource-server
  payments-resource-server
  token-data-encryptor
  token-data-decryptor
  auditor-readonly

Keys:
  K1 = RSA issuer signing test key
  K2 = RSA rotation test key
  H1 = 256-bit random HMAC secret (test)
  KEK1 = test KMS wrapping key
  DEK1 = generated test AES key

Token:
  access JWT signed K1 for audience orders-api
  opaque refresh token stored in independent token store
~~~

**Không dùng key/credential của production để chạy tests**, cũng không copy PEM thật vào test source.

### 24.2. Storage, import/export, IAM tests

| Tình huống | Kết quả mong đợi |
|---|---|
| Public JWKS chỉ có RSA `n`/`e` | Có public metadata, **không private key**. |
| Public JWKS chứa RSA `d`/`p`/`q` | Deployment/security test fail. |
| Public JWKS chứa `kty=oct`/`k` | Deployment fail vì xuất HMAC secret. |
| Orders RS cố gọi `KMS.Sign` issuer key | Deny theo IAM; RS không là signer. |
| Payments RS cố `Decrypt` token-store DEK | Deny. |
| AS signer cố export non-exportable key | Deny hoặc operation unsupported theo provider/key class. |
| AS signer được `Sign` bằng đúng key | Operation thành công sau verified workload auth và policy. |
| Dev workload đọc production key | Deny. |
| Staging workload dùng prod signing key | Deny, môi trường cách ly. |
| Auditor cố đọc plaintext private key | Deny; chỉ metadata/audit được phép. |
| KeyStore password sai | Load thất bại; không log password. |
| PKCS#12 alias không tồn tại | Fail closed; không tự chọn key đầu tiên. |
| Runtime mount permission quá rộng | Security test phát hiện file readable bởi actor ngoài allowlist. |
| Secret nằm trong image layer | Secret scanning fail pipeline. |
| Secret nằm trong `.env` commit | Secret scanning fail, rotation khi lộ. |
| App log `privateKey.getEncoded()` | Canary secret test fail. |
| Heap/crash dump thu thập raw keys | Diagnostic policy phải chặn/kiểm soát access và retention. |
| Workload identity proof sai issuer/audience | IAM từ chối. |
| Service account bị thay namespace/tên | IAM không tự cấp quyền vì name giống. |
| Break-glass dùng ngoài thời hạn | Deny hoặc alert theo policy. |
| Key state `DISABLED` nhưng yêu cầu Sign | Deny. |
| Key destroyed, resource còn tham chiếu | Prevent destroy theo retention/approval hoặc phát hiện DR failure. |

### 24.3. Signing/JWKS/rotation tests

| Tình huống | Kết quả mong đợi |
|---|---|
| JWT K1 ký đúng, issuer/audience đúng | RS xác minh bằng trusted public K1, rồi áp authorization. |
| Token sửa `scope` sau ký | Chữ ký fail, từ chối. |
| JWT `alg=none` | Từ chối. |
| JWT `alg=HS256` tại RS256-only | Từ chối algorithm confusion. |
| JWT ký bằng attacker Kx | Không dùng Kx do token tự cung cấp. |
| `kid` lạ kèm `jku` attacker URL | Không fetch nguồn lạ, bounded refresh JWKS tin cậy. |
| JWT `aud=payments-api` tại Orders | Từ chối dù chữ ký đúng. |
| ID token `aud=shop-web` tại Orders | Từ chối wrong token purpose/audience. |
| Public K2 được publish trước signer switch | Mọi RS resolve được K2 trong policy window. |
| Signer chuyển private K2 | JWT mới có `kid=K2` và chữ ký đúng. |
| K1 verify-only bình thường, token chưa hết hạn | RS nhận token K1 đúng profile/policy. |
| K1 compromise và bị disabled | RS không tiếp tục tin K1 theo emergency policy. |
| JWKS outage, key unknown | Fail closed, không accept unverified JWT. |
| JWKS refresh storm | Có rate limit/bounded retries/caching. |
| Token được signer ký nhưng scope trái policy | AS issuance test fail; RS không bỏ object authorization. |

### 24.4. Envelope encryption, recovery tests

| Tình huống | Kết quả mong đợi |
|---|---|
| Encrypt rồi decrypt cùng DEK/AAD | Plaintext khôi phục đúng. |
| AAD bị thay | Authentication/tag verification fail. |
| Ciphertext/tag bị sửa | AEAD decrypt fail. |
| DEK/KEK sai version | Không decrypt, không fallback sang key khác tùy ý. |
| Token/tenant context khác | Không decrypt cross-tenant nếu AAD/key policy yêu cầu. |
| DEK được lưu raw cạnh ciphertext | Storage test fail. |
| Wrapped DEK/nonce/tag bị mất khi backup | Restore rehearsal fail, phát hiện trước production. |
| KEK rotation kiểu rewrap | Bản ghi cũ/ mới vẫn decrypt đúng key versions. |
| DEK compromise | Reencrypt bằng DEK mới, không chỉ rewrap. |
| KMS key disabled | Decrypt không chạy; xử lý outage/restore có approval. |
| KMS timeout khi decrypt | Không trả dữ liệu không xác thực, áp fail-closed. |
| Nonce reuse trong test fixture cùng key | Crypto policy test phát hiện nguy cơ. |
| Restore từ backup sang environment khác | Không tự cấp quyền dùng prod KEK ở staging. |
| Break-glass restore event | Có audit/approval trace. |
| Ciphertext restore nhưng KEK bị destroy | Báo mất khả năng decrypt, không giả success. |

### 24.5. Cross-purpose và incident tests

| Tình huống | Kết quả mong đợi |
|---|---|
| OAuth client key thử ký AS access JWT | RS không chấp nhận key không thuộc issuer JWKS. |
| AS key thử làm DPoP holder key | Không tự tạo binding hợp lệ cho client. |
| RS có public key nhưng cố ký JWT | Không thể ký hợp lệ bằng public-only material. |
| HMAC secret bị lộ cho RS ngoài phạm vi | Detect policy violation và áp rotation/containment. |
| Refresh token bị đánh cắp nhưng key vẫn an toàn | Grant/revocation playbook, không lạm dụng issuer key rotate. |
| Private signer key bị lộ | Emergency cutoff/reissue trên mọi RS/regions, đo propagation. |
| Client private key bị lộ | Client registration rotation và access/grant risk response. |
| DPoP key rotate | Tokens bound với old key không mặc định dùng được cùng new key. |
| mTLS cert bị thay ở proxy header ngoài | Không chấp nhận untrusted header như chứng minh cert. |
| Incident logs chứa raw key/token | Redaction test fail, bảo vệ log sinks. |

### 24.6. Pseudocode tổng hợp

~~~text
test "resource server is verifier only":
    publicKey = trustedIssuer.publicJwk("K1")
    assert ordersRS.canVerify(tokenSignedWithK1)
    assert ordersRS.iam.cannot("kms:Sign", issuerK1)
    assert ordersRS.secretStore.cannotRead("issuer-private-K1")

test "secret zero is not a permanent root credential":
    identity = platform.issueShortLivedWorkloadIdentity(asService)
    assert kms.authorizes(identity, "Sign", issuerK1)
    assert kms.denies(identity, "Decrypt", paymentsKEK)
    assert kms.denies(untrustedPodIdentity, "Sign", issuerK1)

test "envelope AEAD is bound to record context":
    sealed = encryptWithFreshDEK(
        plaintext=testData,
        aad={tenant:"beta", record:"42"},
        kek=KEK1
    )
    assert decrypt(sealed, sameAadAndAuthorizedIdentity) == testData
    assert decrypt(sealed, aad={tenant:"anpha", record:"42"}) fails

test "rotation keeps valid old tokens only when key safe":
    publishPublicK2()
    assert allRSResolveTrustedK2()
    switchSignerToK2()
    assert newTokensUseKidK2()
    retireK1AfterBoundedExpiryIfNotCompromised()

test "compromised signing key is not accepted":
    markK1Compromised()
    pushEmergencyKeyTrustCutoff(K1)
    assert everyRSRejectsNewTokenSignedByK1()
    assert legitimateUsersReauthorizeOrReceiveK2TokensByPolicy()
~~~

Pseudocode không chạy trực tiếp; integration tests thật phải dùng **KMS/Secret Manager test instance hoặc mocks có kiểm tra IAM, issuer/RS test endpoints, test keys và test data**. Đừng chạy bài kiểm thử emergency delete/disable đối với production key thật.

## 25. Bài tập tình huống và đáp án

### 25.1. Bài 1 — Resource Server cần key nào?

AS phát access JWT `RS256`; `orders-api` có nhiệm vụ kiểm token rồi trả danh sách đơn hàng. Đội vận hành dự định mount file `issuer-private-key.pem` vào cả AS và `orders-api` cho đồng bộ.

**Câu hỏi:** RS có thật sự cần private key? Nếu không, nên thay bằng gì?

**Đáp án:** **Không.** RS chỉ cần **trusted public key** từ issuer JWKS hoặc pinned verifying key set để kiểm chữ ký. Private key phải ở signer trust domain (KMS/HSM/protected AS keystore). RS vẫn phải kiểm issuer, audience, expiry, token purpose, scopes, tenant và object authorization.

### 25.2. Bài 2 — `HS256` secret nằm trong public JWKS

Một AS dùng HMAC `HS256` có cấu hình JWKS:

~~~json
{
  "keys": [
    {
      "kty": "oct",
      "kid": "shared-hs256",
      "alg": "HS256",
      "k": "SECRET_BASE64URL_MATERIAL_EXAMPLE"
    }
  ]
}
~~~

**Câu hỏi:** Đưa `k` lên public JWKS có an toàn không?

**Đáp án:** **Không.** Với `kty=oct`, `k` là **symmetric secret**. Nếu công bố, bất kỳ ai có thể dùng secret để tạo MAC hợp lệ theo key, có nguy cơ giả JWT. Dừng public exposure, rotate secret và đánh giá token đã phát. Nếu cần phân phối verification keys rộng, cân nhắc ký bất đối xứng, nơi JWKS chỉ chứa **public key**.

### 25.3. Bài 3 — Encrypted keystore và password cùng file cấu hình

~~~text
container image:
  /app/issuer.p12
  /app/application.yml:
      keyStorePassword: production-password
~~~

**Câu hỏi:** PKCS#12 được mã hóa bằng password đã đủ an toàn chưa?

**Đáp án:** Chưa. Người lấy được container image có cả file **và password**, có thể mở private key. Cần giữ key material ngoài image, bảo vệ secret delivery bằng workload identity/Secret Manager, file ACL, logs/backups; với high-value signing key cân nhắc KMS/HSM non-exportable.

### 25.4. Bài 4 — KMS giữ khóa không xuất được, AS bị chiếm

Private signing key không thể export khỏi HSM; attacker chiếm AS workload nhưng vẫn có IAM `Sign` trên key.

**Câu hỏi:** Attacker có thể giả token không?

**Đáp án:** **Có thể** nếu attacker điều khiển dữ liệu gửi vào signer và workload IAM cho phép ký. Non-exportable bảo vệ khỏi lấy raw key, **không ngăn misuse qua Sign API**. Phải bảo vệ AS issuance logic, least privilege IAM, workload identity, signing rate/audit và emergency cutoff.

### 25.5. Bài 5 — Rotate KEK sau khi DEK đã lộ

Token metadata database dùng AES-GCM với DEK1, DEK1 được wrap bởi KEK1. Attacker đã lấy cả **plaintext DEK1** và encrypted database snapshot. Đội vận hành chỉ wrap DEK1 bằng KEK2 rồi cho là an toàn.

**Câu hỏi:** Có đủ không?

**Đáp án:** **Không.** Attacker có DEK1 vẫn có thể giải mã ciphertext họ đã sao chép, dù DEK1 được wrap lại. Cần **DEK mới và reencrypt các dữ liệu bị ảnh hưởng**, xem xét data leakage/incident scope. Rewrap chỉ hữu ích khi đổi KEK mà DEK chưa compromise.

### 25.6. Bài 6 — Sao lưu ciphertext mà quên key versions

Hệ thống backup đầy đủ database ciphertext và wrapped DEKs, nhưng đã xóa KEK cũ vì nghĩ “khóa cũ đã nghỉ hưu”.

**Câu hỏi:** Dữ liệu có khôi phục được không?

**Đáp án:** Chưa chắc, thậm chí có thể **không thể khôi phục** nếu KEK/backup cần thiết đã bị destroy. Cần inventory key versions, retention/backup chính thức, rehearsal decrypt/restore, kiểm dữ liệu cũ được rewrap hoặc reencrypt đầy đủ trước khi hủy KEK.

### 25.7. Bài 7 — JWKS rotation gây lỗi 401 hàng loạt

AS phát JWT với `kid=K2` nhưng RS cache JWKS chỉ có K1. Đội đề xuất tạm bỏ signature verification.

**Câu hỏi:** Phản ứng đúng là gì?

**Đáp án:** Không bỏ verify. Sửa trình tự **prepublish public K2**, chuẩn bị verifiers, bounded JWKS refresh và canary rollout; nếu deployment đã lỗi, rollback signer theo **trusted key chưa compromise** hoặc tạm từ chối request/issuance theo policy. Không nhận attacker-provided key.

### 25.8. Bài 8 — HSM signer có thay OAuth scope policy?

AS nhận token request `scope=payments:refund` từ một client chỉ được `payments:read`. HSM trả chữ ký RS256 hợp lệ cho JWT có `payments:refund`.

**Câu hỏi:** Token đã được cấp đúng vì chữ ký hợp lệ chưa?

**Đáp án:** **Chưa.** Cryptographic Sign chỉ tạo chữ ký, không thay **authorization grant, client registration, consent, principal/tenant permission, resource policy**. AS phải chặn việc phát claims sai trước khi gọi signer. RS cũng phải kiểm quyền API hiện hành.

### 25.9. Bài 9 — Public client giữ khóa DPoP không xuất được

Một SPA tạo `CryptoKey` WebCrypto non-extractable để ký DPoP; ứng dụng bị XSS.

**Câu hỏi:** Attacker hoàn toàn không thể sử dụng DPoP key đúng không?

**Đáp án:** **Không đúng.** XSS có thể gọi `crypto.subtle.sign` qua script chạy trong origin với key handle mà nó truy cập được theo security context, dù không export raw private key. Cần XSS defense, token handling, short lifetime, proof validation và cân nhắc BFF khi phù hợp.

### 25.10. Bài 10 — JWT signer đã rotate, refresh token vẫn hoạt động

AS chuyển ký access JWT từ K1 sang K2. Một refresh token R1 vẫn active và có thể xin access token mới.

**Câu hỏi:** Đó có nhất thiết là lỗi?

**Đáp án:** **Không.** Signing key lifecycle và refresh grant lifecycle độc lập. Một refresh token hợp lệ có thể xin token mới ký K2 theo policy. Nếu R1 bị lộ/revoked hay grant bị thu hồi, AS phải chặn R1 riêng; đổi signing key **không tự sửa refresh-token theft**.

### 25.11. Bài 11 — Cùng tên `kid` trên issuer khác

Issuer A và B đều có JWK `kid="signing-01"`. Một RS nhận token Issuer B nhưng chỉ trust Issuer A.

**Câu hỏi:** RS có được thử mọi public key trên internet có cùng `kid` không?

**Đáp án:** Không. `kid` không có ý nghĩa toàn cục; phải **bind `iss` với trusted issuer configuration/JWKS** và kiểm signature/audience/profile. Token từ issuer ngoài allowlist phải bị từ chối.

### 25.12. Bài 12 — Key lưu an toàn nhưng access token log công khai

AS dùng HSM không xuất private key, nhưng API gateway log `Authorization: Bearer ...` vào hệ thống analytics mà nhiều người đọc.

**Câu hỏi:** Hệ thống token đã an toàn chưa?

**Đáp án:** Chưa. Key custody bảo vệ **khả năng tạo chữ ký**, không bảo vệ **bearer tokens đã cấp** khỏi bị replay nếu lộ. Cần redaction tại nguồn, TLS, secure token/session storage, TTL, scope/audience tối thiểu, sender constraints và revocation khi cần.

### 25.13. Bài 13 — Khóa AES-GCM 256 bit nhưng nonce bị lặp

Một dịch vụ dùng AES-256-GCM với DEK mạnh, nhưng khởi tạo nonce cố định 12 byte 0 cho mọi record.

**Câu hỏi:** Key strength có cứu được thiết kế không?

**Đáp án:** Không. **Nonce reuse dưới cùng key là lỗi nghiêm trọng** với AES-GCM, có thể làm mất confidentiality/integrity. Cần thư viện chuẩn, unique nonce strategy/key-use limits và đánh giá reencrypt/incident khi đã dùng sai.

### 25.14. Bài 14 — Quyết định nơi lưu theo mức độ rủi ro

Hãy đề xuất key storage cho bốn trường hợp:

| Trường hợp | Gợi ý thiết kế |
|---|---|
| AS ký JWT cho 20 RS và đối tác ngoài | KMS/HSM non-exportable private signing key nếu khả thi, JWKS chỉ public, IAM `Sign` nghiêm ngặt. |
| Backend confidential client dùng `private_key_jwt` | Workload-owned private key trong KMS/HSM hoặc protected keystore, registered public JWK tại AS. |
| Service mã hóa token metadata trong database | Envelope encryption với KMS KEK, per-context DEK/AEAD, wrapped DEK và key version. |
| Ứng dụng mobile dùng mTLS/DPoP holder key | Hardware/OS-backed key store khi profile hỗ trợ; vẫn xét malware/runtime misuse. |

Đây là **gợi ý kiến trúc**, không áp dụng cứng cho mọi cost/compliance/provider. Cần phân tích key export, availability, rotation, cryptoperiod và yêu cầu audit cụ thể.

## 26. Checklist triển khai key storage an toàn

- [ ] Đã lập inventory cryptographic keys/secrets, owner, purpose, algorithm, key version và lifecycle.
- [ ] Phân biệt AS private signing key, public JWKS, HMAC secret, JWE decryption key, KEK/DEK, OAuth client key và DPoP/mTLS holder key.
- [ ] Không lưu private signing key hoặc HMAC secret trong repository, frontend, mobile bundle hoặc container image.
- [ ] Không coi Base64 hoặc mã hóa keystore bằng password nằm chung image là key storage an toàn.
- [ ] Key material được sinh bằng CSPRNG/provider đạt chuẩn, với key size/curve/algorithm theo policy.
- [ ] Keys cho signing, encryption, client authentication và sender proof được tách theo purpose.
- [ ] HMAC secret có entropy đủ cao, được chia sẻ tối thiểu; mọi verifier giữ secret đều có khả năng tạo MAC.
- [ ] RS xác minh JWT bằng public issuer JWKS, **không** cần private issuer signing key.
- [ ] Public JWKS không chứa RSA/EC private fields hoặc `kty=oct` symmetric `k`.
- [ ] `kid` chỉ chọn key trong trusted issuer key set; không dùng `kid` làm path/URL/KMS keyRef không kiểm.
- [ ] Không tự fetch untrusted `jku`/`x5u`/embedded `jwk` từ JWT header.
- [ ] KMS/HSM private key non-exportable khi rủi ro/chi phí/compatibility cho phép.
- [ ] AS signer IAM chỉ có `Sign` trên đúng issuer key; không cấp `Export`/`Delete`/`Decrypt-any`.
- [ ] RS không có quyền `Sign` với issuer key; auditors chỉ đọc metadata/audit theo quyền.
- [ ] KMS/Secret Manager được truy cập bằng workload identity ngắn hạn, đúng issuer/audience/workload policy.
- [ ] Không dùng root password/API key hardcoded làm secret zero.
- [ ] KMS/HSM/Secret Manager key usage và policy changes có audit/alerts, không log raw keys.
- [ ] Runtime-mounted secrets/file keystore có ACL, isolation, backup và diagnostic protection.
- [ ] PKCS#12/KeyStore password lưu tách keystore file, không đặt trong Git/Dockerfile/log.
- [ ] App không log `getEncoded()`, private key PEM, HMAC key, DEK plaintext, HSM PIN hoặc client secret.
- [ ] Hạn chế memory/core dump/snapshot lộ raw key; hiểu non-exportable không ngăn `Sign` misuse.
- [ ] Với dữ liệu at rest, dùng AEAD chuẩn như AES-GCM, nonce an toàn và authentication tags.
- [ ] Envelope encryption tách KEK/DEK; lưu wrapped DEK/key version/AAD context, không lưu plaintext DEK cùng ciphertext.
- [ ] AAD/context được xác thực và ràng buộc đúng tenant/record; không tin arbitrary user input.
- [ ] Rotate KEK có kế hoạch rewrap; nếu DEK lộ, phải đánh giá reencrypt chứ không chỉ đổi KEK.
- [ ] Key cryptoperiod/rotation triggers phù hợp thuật toán, vận hành và rủi ro, không chỉ theo lịch cứng.
- [ ] JWT signing rotation có prepublish public K2, signer switch, bounded old-key verification và retire an toàn.
- [ ] Key K1 bị compromise phải có emergency trust cutoff/reissue, khác normal rotation.
- [ ] HMAC secret cũ bị xóa khỏi tất cả verifiers/CI/secret versions sau khi retire.
- [ ] Key version mapping không phụ thuộc input `kid` của client; mọi change có audit.
- [ ] Key backup/HA/DR tuân non-exportable policy; restore rehearsal kiểm decrypt dữ liệu cũ.
- [ ] Không xóa KEK khi còn wrapped DEKs/ciphertext chưa được migrate; không tin key name mới thay được raw key cũ.
- [ ] KMS outage có fail-closed behavior, quotas/latency/availability SLO, không insecure fallback signer.
- [ ] OAuth client private key/secret không bị nhầm với issuer key; client auth không tự cấp scope/consent.
- [ ] DPoP/mTLS key ở thiết bị/workload holder được bảo vệ; sender proof/binding vẫn được RS kiểm.
- [ ] Key rotation không bị nhầm với refresh token revocation, browser session logout hoặc consent withdrawal.
- [ ] Bảo vệ cả bearer access/refresh tokens và token/grant store riêng với cryptographic key store.
- [ ] RS vẫn kiểm `iss`, `aud`, `exp`, `scope`, token purpose, principal, tenant và object-level policy sau signature verification.
- [ ] Có alerts cho unexpected KMS Sign/Decrypt, policy changes, JWKS private key exposure, random `kid` storms và backup failures.
- [ ] Có positive/negative tests IAM, key export denial, cross-environment, JWKS, migration, outage, KEK/DEK, compromise và restore.
- [ ] Khi không xác thực được key source, token, workload IAM hoặc key state, hệ thống **fail closed**.

**Ghi nhớ:** **Key storage là quản lý ranh giới tin cậy, không chỉ là một nơi cất file.** Với chữ ký bất đối xứng, **AS giữ private signer key, RS chỉ cần public verification key**. Với `HS256`, mọi verifier giữ shared secret có thể tạo MAC hợp lệ. **KMS/HSM giúp hạn chế xuất key**, nhưng workload có quyền `Sign`/`Decrypt` vẫn phải được bảo vệ bởi IAM, policy và audit. **Envelope encryption** tách KEK/DEK, dùng AEAD và versioning để bảo vệ dữ liệu. Rotation phải tính token TTL/JWKS caches hoặc wrapped-key recovery; khi key lộ cần **emergency containment**, không nhầm với rotation định kỳ. Cuối cùng, chữ ký token đúng **không thay authorization, revocation, sender binding và chống token replay**.

## 27. Tài liệu chuẩn và tham khảo

- **NIST SP 800-57 Part 1 — Recommendation for Key Management:** key types, protection, cryptoperiod, key life cycle, compromise, backup và destruction.
- **NIST SP 800-57 Part 2 — Best Practices for Key Management Organizations:** roles, policy, responsibilities, key-management planning.
- **NIST SP 800-131A — Transitioning the Use of Cryptographic Algorithms and Key Lengths:** algorithm/key-strength transitions.
- **NIST SP 800-38D — Galois/Counter Mode (GCM) and GMAC:** AEAD nonce/IV, authentication tags và giới hạn sử dụng.
- **NIST SP 800-56C — Recommendation for Key-Derivation Methods in Key-Establishment Schemes:** KDF contexts cho các scheme liên quan.
- **RFC 7292 — PKCS #12: Personal Information Exchange Syntax:** encrypted keystore/private key và certificates.
- **OASIS PKCS #11 — Cryptographic Token Interface:** HSM/token key objects, operations, non-exportability attributes và sessions.
- **RFC 7515 — JSON Web Signature (JWS):** signing input, key usage và protected headers.
- **RFC 7516 — JSON Web Encryption (JWE):** key management, content encryption và authentication.
- **RFC 7517 — JSON Web Key (JWK):** `kty`, `kid`, `use`, `key_ops` và public/private JSON key fields.
- **RFC 7518 — JSON Web Algorithms (JWA):** HMAC, RSA, ECDSA, AES-GCM và JOSE key/algorithm parameters.
- **RFC 7519 — JSON Web Token (JWT):** issuer, subject, audience, expiry và JWT claims.
- **RFC 8725 — JSON Web Token Best Current Practices:** issuer/key trust, algorithm confusion, token substitution và cross-JWT confusion.
- **RFC 9068 — JWT Profile for OAuth 2.0 Access Tokens:** access JWT profile/`typ`, audience và Resource Server validation.
- **RFC 6749 — The OAuth 2.0 Authorization Framework:** client authentication, token grants, scopes, access/refresh token roles.
- **RFC 6750 — OAuth 2.0 Bearer Token Usage:** bearer theft/replay, TLS và resource-server challenge behavior.
- **RFC 9700 — Best Current Practice for OAuth 2.0 Security:** authorization security và token hardening.
- **RFC 7009 — OAuth 2.0 Token Revocation:** revocation endpoint và grant/token lifecycle.
- **RFC 7662 — OAuth 2.0 Token Introspection:** opaque token server-side metadata/state.
- **RFC 7523 — JWT Profile for OAuth 2.0 Client Authentication and Authorization Grants:** JWT client assertions và private-key usage.
- **RFC 8705 — OAuth 2.0 Mutual-TLS Client Authentication and Certificate-Bound Access Tokens:** mTLS client private key/certificate handling.
- **RFC 9449 — OAuth 2.0 Demonstrating Proof of Possession (DPoP):** holder keys, proof signatures và access-token binding.
- **OpenID Connect Core 1.0 / Discovery 1.0:** ID token validation, trusted OP metadata/JWKS và OIDC client/server keys.
- **OWASP Key Management Cheat Sheet:** key-generation/storage/rotation/use/backup và separation of duties.
- **OWASP Secrets Management Cheat Sheet:** secret zero, workload identity, vault access, rotation/audit.
- **OWASP Cryptographic Storage Cheat Sheet:** authenticated encryption, key protection, ciphertext/secret separation.
- **OWASP JSON Web Token Cheat Sheet:** token-signing keys, signature validation, storage và revocation.
- **Java Security Reference / Java Cryptography Architecture / Java KeyStore API:** `KeyStore`, `Signature`, `Cipher`, `Mac` và `SecureRandom` usage.
- **Spring Security Reference — OAuth2 Resource Server JWT:** issuer/JWKS/`NimbusJwtDecoder`, token validation và authority mapping.
- **Spring Authorization Server Reference:** OAuth/OIDC token generator, JWKSource, signing keys và server configuration.
- **Kubernetes Documentation — Secrets, RBAC và Encryption at Rest:** secret delivery threat model và control planes.
