# Post-compromise rotation (Xoay vòng khóa sau khi bị xâm phạm)

## 1. Post-compromise rotation là gì?

**Post-compromise rotation** là quá trình thay thế các khóa mật mã, credentials và trust material có thể đã bị lộ hoặc bị sử dụng trái phép, sau khi một sự cố an ninh được phát hiện. Mục tiêu là **chấm dứt khả năng tiếp tục lạm dụng material cũ, thiết lập một miền tin cậy mới và phục hồi hoạt động với khóa mới đã được xác minh**.

Một lần đổi key alias hoặc tạo version mới trong KMS chưa chắc đã hoàn tất post-compromise rotation. Nếu attacker vẫn giữ plaintext DEK, private signing key, HMAC secret, cloud token hoặc quyền tự cấp grants, họ có thể tiếp tục giải mã, giả mạo chữ ký/MAC hoặc lấy lại quyền sau khi hệ thống tưởng đã đổi khóa.

Ví dụ: một DEK AES-GCM bị in vào CI log. Đội vận hành rotate KEK và rewrap encrypted DEK dưới KEK mới. Tuy nhiên attacker đã tải plaintext DEK từ log nên vẫn có thể giải mã các ciphertext cũ. **Để xử lý đúng, phải đánh giá thay DEK và re-encrypt dữ liệu chịu ảnh hưởng**, đồng thời xử lý mọi bản sao và quyền đã dẫn tới việc lộ khóa.

Trong module **SECURITY_KEY_MANAGEMENT_FUNDAMENTALS**, bài học **Post-compromise rotation** thuộc chương **Revocation và compromise**, kết nối:

- Vòng đời khóa: tạo, cấp phát, lưu trữ, sử dụng, rotation, revocation và destruction.
- Khóa đối xứng, khóa bất đối xứng, chữ ký số, HMAC/PSK.
- KMS/HSM, envelope encryption, DEK/KEK và key wrapping.
- IAM, workload identity, trust anchors, certificates và key inventory.
- Incident response, backup/DR, audit, kiểm thử và quản trị cryptoperiod.

**Nguyên tắc cốt lõi:** Chỉ rotate sau khi đã hiểu **attacker có thể kiểm soát điều gì, material nào đã lộ, dữ liệu nào phụ thuộc và control plane nào còn đáng tin**. Khóa mới phải được tạo và phân phối từ một môi trường đã được khôi phục niềm tin; nếu attacker còn kiểm soát môi trường đó, họ có thể đánh cắp cả khóa mới.

## 2. Mục tiêu và các giai đoạn sau compromise

Post-compromise rotation nằm trong quy trình incident response rộng hơn:

| Giai đoạn | Mục tiêu | Ví dụ |
|---|---|---|
| **Containment** | Chặn attacker tiếp tục hoạt động | Cô lập host, revoke token/session, deny KMS grants |
| **Eradication** | Loại bỏ persistence và nguyên nhân xâm nhập | Làm sạch/rebuild workload, vá lỗ hổng, thay credentials bị lộ |
| **Recovery** | Khôi phục dịch vụ trong miền tin cậy mới | Provision key mới, cutover producers/consumers, restore dữ liệu |
| **Post-compromise rotation** | Thay material/trust đã bị ảnh hưởng | Rotate DEK/KEK/signing/HMAC keys, certificates và service credentials |
| **Validation/monitoring** | Chứng minh attacker không còn đường quay lại | Negative tests, audit, old-key-use detection, DR exercise |

Rotation có thể diễn ra song song với containment, nhưng **không được cấp khóa mới qua một đường truyền hoặc endpoint mà attacker còn kiểm soát**. Trong sự cố đang diễn ra, thứ tự chính xác do incident commander và key owner quyết định theo mức nguy hiểm, khả năng giữ dịch vụ và bằng chứng.

### 2.1. Rotation không thay thế eradication

Nếu attacker vẫn có quyền sửa pipeline, đọc secret manager hoặc assume role đặc quyền, họ có thể lấy khóa mới ngay khi hệ thống cấp. Vì vậy cần xử lý **persistence, compromised identities, deployment path, endpoints và control plane** cùng với key rotation.

### 2.2. Recovery không có nghĩa bật lại toàn bộ quyền cũ

Môi trường sau sự cố nên bắt đầu với **identity mới hoặc đã được xác minh, least privilege, key policy được rà soát, secrets mới và audit độc lập**. Không phục hồi nguyên trạng một role hoặc token chỉ vì snapshot cấu hình cũ tiện sử dụng.

## 3. Phân biệt loại compromise trước khi chọn rotation

Không phải mọi incident đều làm lộ raw key bytes. Cần phân loại chính xác:

| Loại sự cố | Điều có thể bị kiểm soát | Hành động trọng tâm |
|---|---|---|
| **Credential compromise** | Password, PAT, cloud access key, OAuth token | Revoke/rotate credential, kiểm tra quyền đã dùng |
| **Identity/workload compromise** | IAM role, service account, instance/pod identity | Cô lập workload, revoke sessions/grants, rebuild identity |
| **KMS/HSM API misuse** | Sign/Decrypt/Unwrap/GenerateDataKey operations | Chặn principal, điều tra output và business actions |
| **Plaintext DEK exposure** | Khóa mã hóa dữ liệu trực tiếp | DEK mới và đánh giá re-encryption |
| **Plaintext KEK exposure** | Có thể unwrap encrypted DEKs | KEK mới, dependency inventory, đánh giá DEKs đã lộ |
| **Private signing key exposure** | Có thể ký ngoài KMS/HSM | Key pair mới và cập nhật verifier trust |
| **HMAC/PSK exposure** | Có thể tạo MAC hoặc xác thực peer giả | Secret mới, chuyển producers/verifiers, reject old |
| **Certificate/CA compromise** | Có thể giả danh identity trong trust domain | PKI recovery, trust-anchor/certificate rollout |
| **Recovery share compromise** | Có thể tham gia khôi phục key theo threshold | Thu hồi custodian, re-share/reconstitute theo scheme |
| **Nonce/algorithm misuse** | Bảo đảm mật mã bị vi phạm dù raw key chưa lộ | Stop affected key use, thay key/migrate ciphertext |
| **Unknown scope** | Chưa biết attacker đã lấy được gì | Containment rộng có kiểm soát, preserve evidence, điều tra |

### 3.1. “Không export key” không chứng minh “không lộ dữ liệu”

KMS có thể giữ KEK non-exportable nhưng trả **plaintext DEK** từ GenerateDataKey/Decrypt cho ứng dụng. Nếu principal bị chiếm có quyền gọi API và output bị thu thập, DEK có thể đã lộ mà KEK vẫn an toàn trong HSM.

### 3.2. “Có quyền Sign” cũng là một dạng khả năng compromise

Private key có thể không rời HSM, nhưng attacker có thể dùng HSM như **signing oracle**. Khi đó phải điều tra chữ ký đã tạo, input/approval và quyền gọi Sign. Thay key material không tự xử lý những chữ ký giả đã được phát hành.

## 4. Exposure assessment: xác định thứ gì phải thay

Quyết định rotation nên dựa trên **khả năng attacker biết, sao chép hoặc sử dụng material**, thay vì chỉ dựa vào tên alert hoặc chức danh của principal.

### 4.1. Những câu hỏi bắt buộc

- Attacker có **raw key bytes** hay chỉ có quyền gọi một API?
- Key có exportable không? Có plaintext output từ KMS SDK, HSM, application hoặc secret manager không?
- Credential nào có thể cấp lại quyền sau khi revoke?
- Attacker có thể thay **key policy, grants, trust store, CI/CD pipeline hoặc secret provisioning** không?
- Ciphertext, encrypted DEK, backups, logs hoặc key shares nào attacker đã tải?
- Có thể xác định key material/version thật hay chỉ có alias/reference?
- Có những consumers/offline regions nào vẫn dùng key cũ?
- Logs có bao phủ đầy đủ operation và time window không?
- Có derived keys hoặc credentials được tạo từ secret cha đã lộ không?
- Có thể dựng lại môi trường sạch trước khi provision material mới không?

### 4.2. Mức độ bằng chứng

| Trạng thái | Ý nghĩa | Cách dùng trong quyết định |
|---|---|---|
| **Confirmed exposed** | Có bằng chứng material/credential đã tới principal không được phép | Thực hiện replacement theo incident policy |
| **Potentially exposed** | Đường lộ tồn tại, không thể loại trừ việc attacker đã lấy | Đánh giá theo mức nhạy cảm và blast radius; thường xử lý thận trọng |
| **Misuse suspected** | Có hành vi bất thường nhưng chưa chứng minh raw material lộ | Contain, kiểm tra operations và outputs trước khi quyết định phạm vi |
| **No evidence with adequate coverage** | Có logging/controls đủ để hỗ trợ kết luận giới hạn | Có thể chỉ revoke quyền nếu policy/threat model chấp nhận |
| **Unknown due to evidence gap** | Logging hoặc inventory không đủ | Không gọi đây là “không compromise”; ghi residual uncertainty |

### 4.3. Phân biệt key ID với key material

Hai key IDs có thể tham chiếu cùng bytes được import; đổi alias không tạo khóa độc lập. Ngược lại, một alias có thể trỏ tới material version mới theo provider. Inventory cần **provider key identity, material version/provenance và usage** để tránh rotate nhầm hoặc bỏ sót.

## 5. Root of trust và clean recovery environment

Khóa mới chỉ có giá trị nếu được tạo, phê duyệt, lưu trữ và phân phối từ một **miền kiểm soát mà attacker không còn chi phối**.

~~~mermaid
flowchart TD
    A["Compromised environment"] --> B["Containment + preserve evidence"]
    B --> C["Eradicate persistence / rebuild trusted control plane"]
    C --> D["Verify IdP, IAM, CI/CD, KMS/HSM admin paths"]
    D --> E["Establish clean recovery identities"]
    E --> F["Generate replacement material in trusted boundary"]
    F --> G["Provision to authorized consumers"]
    G --> H["Verify cutover, deny old material, monitor"]
~~~

### 5.1. Những thành phần cần xác minh trước khi tạo key mới

- **IdP/MFA:** administrator accounts, federation trust, recovery codes và sessions.
- **Cloud IAM:** root/admin roles, AssumeRole, PassRole, CreateGrant, policy mutation.
- **CI/CD:** runners, deployment keys, build artifacts, pipeline definitions và signing jobs.
- **KMS/HSM:** operator accounts, key policies, grants, quorum, audit destinations.
- **Secret manager:** master credentials, access policies, replication và cached secrets.
- **PKI/trust:** CA, certificate issuance, JWKS publication và trust-store update permissions.
- **Endpoints:** clean images, EDR posture, malware persistence và access paths.
- **Backup/DR:** source snapshots, restore identities, offline copies và key recovery.

### 5.2. Không tạo khóa mới trên máy còn bị kiểm soát

Nếu attacker có quyền root trên host tạo key hoặc sửa SDK/runtime, họ có thể lấy plaintext key ngay khi sinh. Với key nhạy cảm, ưu tiên **KMS/HSM generation non-exportable**, clean build, verified workload identity và separation of duties.

### 5.3. Trust anchor compromise cần recovery riêng

Nếu root CA, IdP federation root, signing trust root hoặc KMS administrator domain bị chiếm, chỉ rotate leaf keys không đủ. Cần **khôi phục trust hierarchy**, phân phối trust anchors mới qua kênh độc lập, cập nhật verifiers và xử lý credentials được phát hành trong thời gian compromise.

## 6. Thứ tự rotation theo dependency, không theo một danh sách cố định

Một trình tự thường dùng là:

1. **Contain compromised access:** revoke identities, tokens, sessions, grants và quyền tự cấp lại.
2. **Khôi phục control plane/root of trust:** IdP, IAM, CI/CD, KMS/HSM administration và audit.
3. **Thay credentials dùng để quản lý/provision key:** service account, deployment credentials, API tokens, operator identities.
4. **Thay trust/identity material bị compromise:** CA, signing keys, mTLS client certificates, JWKS.
5. **Thay data-protection keys:** KEK/DEK/HMAC theo exposure và dependency.
6. **Cutover producers/consumers:** xác minh key version, old-key acceptance và caches.
7. **Re-encrypt/rewrap và khôi phục dữ liệu:** theo đúng loại key và mức lộ.
8. **Retire/destroy material cũ:** chỉ sau dependency, retention và DR clearance.

Đây là **mẫu tham chiếu**, không phải thứ tự bắt buộc trong mọi incident. Ví dụ private signing key đang bị dùng để phát token giả có thể cần revoke trust ngay; không chờ toàn bộ CI cleanup xong. Incident commander phải cân bằng **ngăn attacker tiếp tục hoạt động** và **tránh cấp key mới vào môi trường còn bị chiếm**.

### 6.1. Dependency graph quan trọng hơn thứ tự tuyến tính

Một DEK có thể phụ thuộc vào KEK; service dùng KMS phụ thuộc IAM/workload identity; verifier phụ thuộc CA/JWKS; recovery phụ thuộc custodian quorum. Thay một node nhưng không thay các trust dependencies của nó có thể để lại đường attacker quay lại.

## 7. Kế hoạch theo loại key material

| Tài sản bị ảnh hưởng | Replacement thường cần đánh giá | Việc không đủ |
|---|---|---|
| Cloud/API credential | Credential mới, identity/session mới | Chỉ đổi alias KMS |
| DEK plaintext đã lộ | DEK mới và re-encrypt dữ liệu có nguy cơ | Rewrap DEK cũ |
| KEK plaintext đã lộ | KEK mới, rewrap DEKs và đánh giá DEK exposure | Disable KMS key rồi kết luận mọi blob an toàn |
| HMAC/PSK | Secret mới, rollout và reject old | Chỉ revoke một user |
| Private signing key | Key pair mới, revoke old trust và xử lý signatures/tokens | Chỉ DisableSign tại HSM |
| TLS/mTLS private key | Key pair/certificate mới, cập nhật trust và session | Chỉ xóa file trên một host |
| CA/trust anchor | PKI hierarchy/trust recovery | Chỉ rotate leaf certificate |
| Recovery share | Custodian/share reconstitution theo scheme | Chỉ disable account |
| Nonce misuse | Key mới, ngừng Encrypt cũ, đánh giá re-encrypt | Sửa nonce metadata hoặc rewrap KEK |

### 7.1. Không phải mọi credential đều là encryption key

API token, PAT, SSH key, workload identity và certificate private key có thể mở đường đến KMS hoặc dữ liệu. Chúng cần replacement/revocation riêng, sau đó đánh giá **những key operations đã được thực hiện bằng credential đó**.

## 8. Rotation sau khi DEK bị lộ

**DEK (Data Encryption Key)** là vật liệu trực tiếp mã hóa payload. Nếu plaintext DEK đã lộ, attacker có thể giải mã những ciphertext họ đã thu thập mà không cần truy cập KMS.

### 8.1. Luồng xử lý

1. Xác định DEK material/version, thuật toán và toàn bộ object/tenant/backup phụ thuộc.
2. Chặn producer tiếp tục Encrypt mới dưới DEK bị compromise.
3. Tạo DEK mới bằng KMS/CSPRNG trong clean environment.
4. Xác thực quyền truy cập dữ liệu, **Decrypt và Verify** bản ghi cũ theo quy trình được duyệt.
5. Re-encrypt plaintext bằng DEK mới, nonce mới và AAD đúng.
6. Wrap DEK mới dưới KEK hợp lệ; cập nhật envelope metadata bằng transaction/CAS.
7. Kiểm tra ciphertext/tag/AAD, tenant/object binding và read-after-write.
8. Chuyển consumers và backup jobs sang version mới.
9. Theo dõi old DEK usage; retire/destroy theo dependency và retention.
10. Báo cáo rõ dữ liệu có thể đã bị attacker đọc trước thời điểm migration.

### 8.2. Rewrap không đủ khi DEK đã lộ

~~~mermaid
flowchart LR
    A["Ciphertext cũ"] --> B["DEK-A đã lộ"]
    C["Wrapped DEK-A"] --> D["KEK-v1"]
    D --> E["Rewrap sang KEK-v2"]
    E --> F["Wrapped DEK-A mới"]
    B --> G["Attacker vẫn giữ DEK-A"]
    G --> H["Vẫn có thể giải mã ciphertext cũ"]
~~~

Rewrap thay cách bọc, **không thay bytes DEK-A**. Nếu attacker đã copy DEK-A, họ vẫn giữ khả năng giải mã ciphertext cũ.

### 8.3. Migration cần tính đến dữ liệu lịch sử

Không phải mọi bản sao dữ liệu đều còn trong database hiện tại. Kiểm kê object versions, archive, snapshots, replicas, exports, backups và dữ liệu đã gửi tới consumers. Re-encrypt dữ liệu live nhưng bỏ qua archive có thể để lại ciphertext cũ vẫn đọc được bằng DEK bị lộ.

### 8.4. Không bỏ AEAD verification để cứu dữ liệu

Nếu tag/AAD không hợp lệ, không trả plaintext chưa xác thực. Cần điều tra corruption/tampering và dùng bản sao backup đáng tin hoặc recovery procedure đã được đánh giá.

## 9. Rotation sau khi KEK bị lộ

**KEK (Key Encryption Key)** thường bảo vệ nhiều DEKs. Khi raw KEK bị lộ, attacker có thể dùng nó để Unwrap những encrypted DEK blobs tương ứng mà họ đã thu thập.

### 9.1. Phản ứng

- Chặn các hoạt động Wrap mới và quyền principal bị compromise.
- Tạo KEK mới trong KMS/HSM đã được xác minh sạch.
- Rewrap DEKs còn cần sử dụng dưới KEK mới, cập nhật keyRef/material version.
- Kiểm kê encrypted DEK blobs mà attacker có thể đã lấy trong quá khứ.
- Đánh giá DEKs có thể đã bị attacker unwrap offline.
- Nếu DEKs có thể đã lộ, thực hiện DEK replacement/re-encryption theo scope.
- Test Decrypt/restore trên archive và DR trước khi retire key cũ.

### 9.2. Rewrap đủ trong trường hợp nào?

Nếu sự cố chỉ là **planned KEK migration** và không có dấu hiệu KEK/DEK bị lộ, rewrap có thể giữ nguyên DEK và ciphertext. Nhưng khi raw KEK đã bị sao chép, không thể giả định encrypted DEK blobs cũ còn bí mật đối với attacker.

### 9.3. KEK không phải một cách thay DEK

KEK-v2 không tạo nonce namespace mới cho DEK-A. Nếu payload vẫn dùng DEK-A, nonce state, usage count và cryptoperiod của DEK-A vẫn được giữ.

## 10. Rotation HMAC/PSK sau compromise

HMAC key hoặc PSK dùng chung thường được sao chép tới nhiều producers/verifiers. Khi secret bị lộ, attacker có thể tạo MAC hợp lệ ngoài hệ thống.

### 10.1. Quy trình cutover

1. Xác định tất cả producers, verifiers, tenants, partners và environments đã biết secret cũ.
2. Generate secret mới bằng CSPRNG/KMS/secret manager phù hợp.
3. Gán key version/purpose và provision qua authenticated channel.
4. Chuyển producers sang tạo MAC với secret mới.
5. Xác minh verifiers đã nhận version mới và kiểm tra đúng key ID.
6. Ngừng chấp nhận secret cũ theo incident severity; không dual-verify vô hạn.
7. Điều tra request/MAC/replay trong incident window.
8. Revoke/retire old secret và rà soát backups, logs, CI artifacts.

### 10.2. Rotation không thay anti-replay

Một request có MAC hợp lệ dưới secret cũ có thể bị replay. Protocol cần timestamp/challenge/sequence/operation ID và state phù hợp. Sau compromise, phải xử lý cả **secret authenticity** và **business requests đã có thể bị giả mạo**.

### 10.3. Tách secret để giảm blast radius

Không dùng một PSK cho toàn bộ services, partners và tenants. Tách theo purpose, environment, peer và tenant để sự cố một bên không buộc rotate toàn bộ miền tin cậy.

## 11. Rotation private signing key và khôi phục verifier trust

Nếu private signing key đã bị sao chép, attacker có thể ký bên ngoài HSM/KMS. Post-compromise rotation phải xử lý **signer lẫn verifiers**.

### 11.1. Các bước

- Dừng Sign mới dưới key cũ và revoke principal/credentials bị chiếm.
- Tạo key pair mới trong HSM/KMS hoặc miền bảo vệ phù hợp.
- Cập nhật signing service, key ID/kid và approval policy.
- Phân phối public key/certificate/JWKS mới từ issuer/trust source đáng tin.
- Làm verifiers ngừng chấp nhận old compromised key theo policy.
- Kiểm tra cache, token TTL, offline verifiers và federation.
- Điều tra signatures/tokens phát hành trong incident window.
- Giữ public verification history cần cho audit/pháp lý theo policy, nhưng không cho old key Sign mới.

### 11.2. JWT/JWKS

Đổi kid nhưng giữ private key bytes không phải rotation. Xóa old JWK khỏi một endpoint không chứng minh mọi verifier đã refresh. Cần xác minh **issuer, audience, algorithm allowlist, cache expiry, token revocation và effective verifier trust**.

### 11.3. HSM non-exportable nhưng Sign API bị lạm dụng

Nếu private key chưa export nhưng attacker có thể gọi Sign tùy ý, cần điều tra các input/digests/chứng từ đã ký, phê duyệt và quyền business. Có thể cần key mới hoặc trust update theo mức độ, nhưng **vấn đề không chỉ là raw key exposure**.

## 12. Rotation certificate, CA và trust anchors

Certificate là một phần của trust system. Nếu chỉ một client certificate bị lộ, thay leaf certificate có thể đủ; nếu **CA hoặc trust distribution** bị compromise, phạm vi cần lớn hơn.

| Thành phần | Xử lý sau compromise |
|---|---|
| TLS server private key | Tạo key pair/certificate mới, deploy và kiểm tra clients |
| mTLS client private key | Tạo credential mới, revoke cert cũ và cập nhật authorization |
| Intermediate CA | Đánh giá chain, revoke/replace CA và cập nhật trust stores |
| Root CA/trust anchor | PKI recovery theo ceremony độc lập, phân phối trust mới |
| JWKS issuer key | Signing key rotation, verifier trust/cache update |
| SSH CA | Rotate CA key, revoke certs, cập nhật trust và principals |

### 12.1. Revoke certificate không xóa private key

Certificate revocation có thể khiến verifier từ chối credential theo policy, nhưng không xóa private key đã bị copy. Nếu attacker giữ private key, họ có thể tiếp tục thử impersonation ở những clients chưa nhận revoke.

### 12.2. Trust propagation

CRL/OCSP, certificate caches, JWKS caches, pinned public keys, service mesh và offline devices có thể cập nhật khác thời điểm. Phải đo **effective trust** tại verifiers, không chỉ trạng thái CA/provider.

### 12.3. Root compromise cần kênh phân phối độc lập

Nếu kênh phát hành certificate hoặc trust store đã bị kiểm soát, dùng chính kênh đó để gửi trust anchor mới có thể khiến attacker tráo key một lần nữa. Cần recovery channel và approval độc lập theo PKI policy.

## 13. Rotation workload identities, API credentials và service secrets

Compromise của cloud access key, PAT, OAuth client secret hoặc workload token có thể là **đường vào** để attacker gọi KMS/secret manager. Các credentials này phải được thay trong control plane đã làm sạch.

### 13.1. Những việc cần làm

1. Xác định credential bị lộ và mọi identity/session được tạo từ nó.
2. Revoke token/session cũ, role assumption và quyền phát hành credential mới.
3. Kiểm tra attacker có sửa IAM, deployment manifest, service account hoặc secret manager policy không.
4. Tạo workload identity/credential mới theo cơ chế được quản lý.
5. Cấp đúng scope và operation; không cấp quyền Decrypt/Sign rộng chỉ để migration thuận tiện.
6. Cập nhật producers, consumers, CI jobs, scheduled tasks và offline agents.
7. Chứng minh credential cũ bị từ chối và không còn đường refresh/reissue.
8. Điều tra các KMS/API operations đã được thực hiện dưới identity cũ.

### 13.2. Đừng nhầm credential mới với key material mới

Đổi cloud API key không thay DEK/KEK. Nhưng credential cũ có thể đã được dùng để lấy plaintext DEKs, sửa grants hoặc đọc secrets khác. Cần lần theo **operation outputs và quyền bắc cầu**, không dừng ở việc credential đã revoke.

### 13.3. Secret trong CI/CD cần xử lý cả pipeline

Nếu attacker kiểm soát runner hoặc pipeline definition, họ có thể lấy secret mới trong lần deploy tiếp theo. Rebuild runners, kiểm tra repository protection, signing provenance, environment approvals và artifact retention trước khi đưa credentials mới vào pipeline.

## 14. KMS/HSM rotation sau compromise

KMS/HSM là miền bảo vệ key material, nhưng sự cố có thể tác động đến **material, API permissions, administrative control hoặc audit** theo những cách khác nhau.

### 14.1. Bốn trường hợp cần phân biệt

| Sự cố | Phản ứng trọng tâm |
|---|---|
| **Principal có quyền Decrypt bị chiếm** | Revoke identity/grants, điều tra DEKs/plaintext data đã trả |
| **KEK raw material bị lộ** | KEK mới, đánh giá wrapped DEKs attacker đã thu thập, thay DEKs khi cần |
| **KeyAdmin/control plane bị chiếm** | Khôi phục IAM/KMS administration, grants, policy, audit và recovery roles |
| **HSM/quorum/recovery domain bị compromise** | Incident PKI/HSM riêng, reconstitute/rekey và xác minh root of trust |

### 14.2. Không chỉ dựa vào trạng thái Enabled/Disabled

Provider state không nói hết tình trạng ứng dụng. Một key có thể Disabled nhưng raw material đã export vẫn tồn tại; ngược lại key Enabled nhưng principal bị revoke có thể không còn được phép gọi. Cần kiểm tra **provider key state, effective policy, grants, sessions, application caches và material provenance**.

### 14.3. KMS automatic rotation không tự rotate mọi DEK

Một số provider hỗ trợ rotation cho key encryption key hoặc managed key. Ứng dụng có thể vẫn lưu encrypted DEKs được bọc bằng material version cũ, hoặc tự dùng DEKs đã Generate từ lâu. Cần phân biệt **KEK material rotation, DEK replacement, rewrap và payload re-encryption**.

### 14.4. Audit domain cũng có thể bị compromise

Nếu attacker có quyền xóa log hoặc thay audit sink, cần khôi phục **independent logging/retention** và đánh giá khoảng thời gian thiếu bằng chứng. Không coi “không có event” là “không có operation” khi log coverage đã bị phá.

## 15. Recovery shares, backup keys và key ceremony

Recovery share hoặc backup key có thể cho phép tái tạo quyền kiểm soát master material. Khi share holder, custodian hoặc nơi lưu backup bị compromise, cần đánh giá **threshold, số bản sao, quorum và mọi đường khôi phục**.

### 15.1. Các bước xử lý

- Xác định scheme và threshold thực tế; không suy luận từ số lượng người được ghi trong danh sách.
- Thu hồi smartcard, operator credential và quyền tham gia ceremony của custodian bị ảnh hưởng.
- Kiểm kê share copies, escrow, backup media và bản sao ngoại tuyến.
- Re-share/reconstitute hoặc thay master material theo khả năng của scheme và policy.
- Đảm bảo số custodians hợp lệ còn đủ để phục hồi; không làm mất availability.
- Diễn tập recovery với approvers độc lập và audit.
- Không tạo plaintext master key để bàn giao qua email, wiki hoặc ticket.

### 15.2. Re-share và rekey khác nhau

Một threshold scheme có thể hỗ trợ **refresh/re-share** để thay đổi các shares/custodians mà vẫn đại diện cho cùng secret, tùy scheme. Nếu chính master secret đã lộ, re-share cùng secret **không làm secret cũ trở lại bí mật**; phải đánh giá tạo master material mới và chuyển dependencies.

### 15.3. Backup cần được đánh giá như một đường key distribution

Một bản backup raw KEK không được bảo vệ có thể làm vô hiệu kiểm soát non-exportable ở KMS chính. Kiểm tra encryption-at-rest, access, custody, media copies, restore permissions và thời điểm backup được tạo.

## 16. Derived keys và key hierarchy: thay cả chuỗi khi parent secret bị lộ

Một hệ thống có thể dẫn xuất nhiều keys từ **master secret, root key hoặc KDF input**. Nếu material cha bị lộ, các keys con được dẫn xuất từ nó có thể cũng bị tính toán lại.

~~~mermaid
flowchart TD
    R["Root/master secret bị lộ"] --> KDF["KDF / key derivation"]
    KDF --> A["DEK-A"]
    KDF --> B["HMAC key-B"]
    KDF --> C["Signing seed-C"]
    A --> D["Encrypted dataset A"]
    B --> E["Webhook authentication"]
    C --> F["Signing identity"]
~~~

### 16.1. Không chỉ rotate một child key rồi giữ parent bị lộ

Nếu attacker có parent secret và biết derivation context, họ có thể tái tạo child keys. Cần:

1. Thay root/master secret bằng material mới được tạo trong clean environment.
2. Xác định derivation labels, salt, context, algorithm và version.
3. Dẫn xuất child keys mới với **domain separation** rõ ràng.
4. Cập nhật mọi consumers/producers theo key version mới.
5. Re-encrypt/replace data hoặc trust tương ứng theo child key type.
6. Chặn parent/child version cũ theo usage policy.
7. Audit và test để bảo đảm không còn service tự dẫn xuất từ old root.

### 16.2. Domain separation không cứu parent đã lộ

Label khác nhau giúp tránh dùng nhầm key giữa các mục đích, nhưng không làm child key bí mật nếu attacker biết **parent secret** và toàn bộ đầu vào derivation cần thiết.

### 16.3. Không suy diễn mọi key trong hệ thống đều bị lộ

Chỉ các keys thực sự được dẫn xuất hoặc có quan hệ phụ thuộc vào compromised material mới nằm trong phạm vi trực tiếp. Key độc lập được generate riêng có thể không bị ảnh hưởng, nhưng vẫn cần xem credential/control plane chung có thể truy cập chúng hay không.

## 17. Nonce reuse, algorithm compromise và lỗi cryptographic operation

Post-compromise rotation cũng cần xử lý sự cố **vi phạm security assumptions**, ngay cả khi raw key không bị đánh cắp.

### 17.1. AES-GCM nonce reuse

Nếu cùng DEK và nonce được dùng cho nhiều Encrypt operations, confidentiality và integrity có thể bị suy yếu. Hướng xử lý:

- Chặn Encrypt mới dưới DEK material bị ảnh hưởng.
- Xác định key material thật và các cặp nonce/operations đã trùng.
- Kiểm tra multiwriter, counter rollback, retry và snapshot restore.
- Generate DEK mới và chuyển producers.
- Đánh giá re-encrypt dữ liệu cũ, khả năng lộ plaintext và giả mạo.
- Không reset nonce counter chỉ vì KEK/alias đổi.

### 17.2. Thuật toán hoặc protocol bị downgrade

Nếu attacker ép hệ thống dùng suite yếu hoặc parser chấp nhận legacy format không an toàn, chỉ rotate key nhưng vẫn cho downgrade không giải quyết nguyên nhân. Cần:

- Cập nhật algorithm allowlist và protocol policy.
- Loại bỏ fallback không an toàn.
- Migrate ciphertext sang suite mới bằng workflow xác thực.
- Giữ reader lịch sử có kiểm soát nếu cần, nhưng không cho Encrypt mới theo suite bị cấm.
- Kiểm thử rejection của unknown version, duplicate fields và downgrade attempts.

### 17.3. Không thay nonce/AAD bằng tay

Nonce, tag, ciphertext và AAD là một phần của record AEAD. Không sửa một trường rồi giữ nguyên phần còn lại để “làm cho record hợp lệ”. Cần **Decrypt/Verify bản gốc hợp lệ rồi Encrypt lại** với material và metadata mới; nếu bản gốc không verify, phải dùng recovery/evidence path đã được phê duyệt.

## 18. Re-encryption, rewrap và migration consistency

Ba thao tác thường bị nhầm:

| Thao tác | Thay đổi gì? | Payload ciphertext đổi? |
|---|---|---|
| **Rewrap DEK** | Wrapped DEK/KEK reference/context | Thường không |
| **Rotate DEK** | Tạo material data key mới | Có khi dữ liệu được mã hóa lại |
| **Re-encrypt payload** | Decrypt/Verify rồi Encrypt lại dưới key/nonce mới | Có |

### 18.1. Quy trình migration an toàn

1. Lập danh sách objects và dependency snapshot theo **key material version**.
2. Chọn operation ID và target key version cho từng batch.
3. Đọc ciphertext + nonce + tag + AAD + encrypted DEK từ revision nhất quán.
4. Xác thực authorization và **Decrypt/Verify** bản gốc.
5. Encrypt bằng DEK mới, nonce mới, AAD schema đã chọn.
6. Wrap DEK mới, cập nhật metadata bằng **transaction/CAS**.
7. Đọc lại record và xác minh Decrypt/Verify bằng reader production-equivalent.
8. Ghi migration status và reconcile các batch timeout/partial failure.
9. Chỉ đánh dấu old dependency cleared sau khi backups/archives/replicas được xử lý.

### 18.2. Tránh dual-write không nhất quán

Nếu cập nhật ciphertext nhưng không cập nhật encrypted DEK/nonce/tag cùng revision, reader có thể lấy **ciphertext mới + wrapped DEK cũ** hoặc ngược lại. Dùng immutable revision, atomic manifest hoặc protocol transaction phù hợp.

### 18.3. Retry không được mã hóa lại bằng nonce đã dùng

Nếu storage timeout sau khi đã persist ciphertext, đọc lại theo operation ID trước. Có thể resend chính record bất biến; nếu phải thực hiện Encrypt mới dưới cùng DEK thì cấp nonce chưa từng dùng. Không cấp lại counter đã reserve.

### 18.4. Chunked/streaming data

Với chunk encryption, cần xác minh mọi chunks, nonce uniqueness, thứ tự, tổng số chunk và authenticated manifest. Re-encrypt một phần nhưng giữ manifest cũ có thể tạo stream không nhất quán hoặc cho phép truncate/reorder.

## 19. Old-key policy sau compromise

Sau khi thay material, phải quyết định **old key còn được phép làm gì**. Không dùng một trạng thái “old key” duy nhất cho mọi loại key.

| Key type | New operations | Historical operations |
|---|---|---|
| **DEK đã lộ** | Chặn Encrypt mới | Decrypt migration chỉ khi cần, trong scope kiểm soát; đánh giá dữ liệu đã lộ |
| **KEK đã lộ** | Chặn Wrap/Unwrap mới theo incident policy | Có thể cần controlled migration; không coi old wrapped blobs an toàn trước attacker |
| **HMAC/PSK đã lộ** | Không tạo MAC mới | Verifier nên reject old secret theo cutoff phù hợp |
| **Signing private key đã lộ** | Chặn Sign mới | Public-key history/verification xử lý theo trust và incident policy |
| **TLS/mTLS credential** | Ngừng handshake mới với old credential | Existing sessions/cache cần terminate/expire theo policy |
| **Certificate/CA** | Ngừng cấp/accept theo trust policy mới | Historical validation có thể cần archive evidence |
| **Recovery share** | Ngừng quorum participation của share cũ | Giữ evidence/custody theo retention, không dùng lại |

### 19.1. Decrypt-only có thể là một trạng thái migration tạm

Với DEK cũ không còn được phép Encrypt, có thể cần quyền Decrypt hạn chế để chuyển dữ liệu. Nếu DEK đã bị lộ, quyền Decrypt vẫn cần được kiểm soát vì có thể mở rộng data exposure. Đặt **principal, dataset, time window, audit và shutdown deadline** rõ ràng.

### 19.2. Không duy trì old-key compatibility vô hạn

Compatibility window kéo dài làm attacker có thêm thời gian dùng secret cũ. Cần theo dõi old-key usage và có cutoff được phê duyệt. Nếu key compromise đã xác nhận, ưu tiên từ chối old key; ngoại lệ phải ghi residual risk và giới hạn chặt.

## 20. Cutover, cache invalidation và kiểm soát attacker quay lại

Rotation chỉ thành công khi **mọi producer, consumer, verifier và recovery path** dùng đúng trạng thái mới.

### 20.1. Các điểm cần kiểm tra

- JVM/native memory, DEK cache, HMAC secret cache và signing agents.
- Kubernetes secrets, sidecars, service mesh, environment variables.
- CI/CD runners, deployment manifests, build artifacts và scheduled jobs.
- JWKS/certificate caches, trust stores, pinned public keys.
- Queue/DLQ, offline clients, batch workers và mobile devices.
- Multi-region KMS replicas, backup restore images và disaster recovery roles.
- Automation có quyền tự tạo credential/grant mới.

### 20.2. Key epoch và monotonic version

Một consumer nên biết **key version/epoch được phép hiện tại**. Khi nhận message cũ sau cutover, nó không tự động kích hoạt old material. Version state cần được bảo vệ khỏi rollback/replay và lấy từ nguồn tin cậy.

### 20.3. Không coi restart là xóa secret

Restart có thể giải phóng một số memory, nhưng không xóa bản sao ở logs, snapshots, backup, CI artifacts hoặc attacker endpoint. Cache invalidation phải là một phần của workflow, nhưng không thay material rotation khi key đã lộ.

### 20.4. Monitor old-key use

Sau cutover, cảnh báo nếu:

- Có producer Encrypt/Sign/MAC mới dưới old key.
- Có consumer dùng old token/certificate/role.
- Có KMS Unwrap/Decrypt dưới old key ngoài migration principal.
- Verifier còn chấp nhận old signing/HMAC key.
- Backup/DR job cố khởi động với secret version cũ.
- Có credential mới được phát hành từ pipeline chưa được rebuild.

## 21. Runbook post-compromise rotation

Runbook cần biến đánh giá incident thành các hành động **có owner, approval, trạng thái và bằng chứng**. Không coi một lần gọi API thành công là hoàn tất.

~~~mermaid
flowchart TD
    A["Incident confirmed / suspected"] --> B["Contain access and preserve evidence"]
    B --> C["Rebuild or verify clean control plane"]
    C --> D["Inventory keys, identities and dependencies"]
    D --> E["Classify exposure by material and operation"]
    E --> F["Approve replacement scope and migration plan"]
    F --> G["Generate new material in trusted boundary"]
    G --> H["Provision and cut over consumers"]
    H --> I["Re-encrypt / rewrap / update trust as needed"]
    I --> J["Verify positive and negative paths"]
    J --> K["Retire old use; clear dependencies"]
    K --> L["Monitor, document residual risk and close"]
~~~

### 21.1. Nhận incident và containment

- Ghi **incident ID, time window, principal, key references, environment và severity**.
- Cô lập compromised endpoint/workload, revoke sessions/tokens và chặn quyền tự cấp lại.
- Revoke KMS grants, IAM roles và credentials theo phạm vi được phê duyệt.
- Nếu key operation đang bị lạm dụng, dừng operation cụ thể hoặc disable key theo provider semantics và blast-radius review.
- Bảo toàn audit, logs và forensic evidence trước khi thay đổi có thể làm mất dữ liệu điều tra.

### 21.2. Khôi phục control plane sạch

- Xác minh IdP/admin identities, MFA/recovery methods và federation trust.
- Rebuild CI/CD runners, deployment agents và secret provisioning path nếu bị kiểm soát.
- Xác minh KMS/HSM administrators, quorum, grants, key policies và audit sink.
- Kiểm tra trust anchors, CA/JWKS publication và service identity issuance.
- Thiết lập recovery principals mới có least privilege và independent approval.

### 21.3. Xác định replacement scope

Mỗi key/credential cần có record quyết định:

| Trường | Nội dung cần ghi |
|---|---|
| **Asset identity** | Key ID/material version/credential reference thực |
| **Exposure state** | Confirmed, potentially exposed, misuse suspected, evidence gap |
| **Dependencies** | Consumers, ciphertexts, encrypted DEKs, backups, verifiers |
| **Required action** | Revoke, replace, rewrap, re-encrypt, trust update hoặc no material rotation |
| **Owner/approver** | Người chịu trách nhiệm và người duyệt độc lập |
| **Cutover target** | Version mới, deadline, regions và consumers |
| **Verification** | Positive/negative tests, restore test, provider readback |
| **Residual risk** | Data đã có thể lộ, offline consumers, evidence gaps |

### 21.4. Generate và provision replacement

- Generate key material mới trong KMS/HSM hoặc clean environment đã được xác minh.
- Ghi key origin, algorithm, usage, key version, owner và cryptoperiod.
- Provision wrapped key/credential qua authenticated channel, đúng recipient identity và purpose.
- Không copy raw secret vào chat, email, issue tracker, CI variable không được quản lý hoặc shell history.
- Tách người request, approver, executor và auditor theo SoD.

### 21.5. Cutover và retirement

- Chuyển producers trước hay consumers trước tùy protocol; định nghĩa compatibility window rõ.
- Verify consumer nhận đúng material/version, context và scope.
- Chặn new operations bằng old key theo policy.
- Reconcile các operations timeout/partial failure.
- Xử lý offline clients, regions, queue replay và backup jobs.
- Retire/destroy old material chỉ khi dependency và recovery criteria đạt.

## 22. Java 17: lập kế hoạch rotation sau compromise

Ví dụ dưới đây là **planner thuần**, phân loại tài sản và tạo danh sách review/actions. Nó không gọi KMS, không tự revoke principal, không generate raw key và không destroy material. Production cần kết nối incident inventory, approval service, provider SDK và audit độc lập.

~~~java
import java.util.EnumSet;
import java.util.Objects;
import java.util.Set;

public final class PostCompromiseRotationPlanner {
    public enum AssetType {
        ACCESS_CREDENTIAL,
        DATA_ENCRYPTION_KEY,
        KEY_ENCRYPTION_KEY,
        SHARED_HMAC_SECRET,
        PRIVATE_SIGNING_KEY,
        CERTIFICATE_OR_CA,
        RECOVERY_SHARE,
        DERIVED_ROOT_SECRET
    }

    public enum Exposure {
        ACCESS_MISUSE_SUSPECTED,
        MATERIAL_POTENTIALLY_EXPOSED,
        MATERIAL_CONFIRMED_EXPOSED
    }

    public enum Action {
        REVOKE_IDENTITIES_AND_SESSIONS,
        CONTAIN_COMPROMISED_WORKLOAD,
        VERIFY_CLEAN_CONTROL_PLANE,
        PRESERVE_EVIDENCE,
        INVENTORY_DEPENDENCIES,
        ASSESS_EFFECTIVE_PERMISSIONS,
        REPLACE_ACCESS_CREDENTIAL,
        ASSESS_NEW_DEK_AND_REENCRYPT,
        ASSESS_NEW_KEK_AND_REWRAP,
        ASSESS_DEPENDENT_DEKS,
        REPLACE_SHARED_SECRET,
        REPLACE_SIGNING_KEY_AND_UPDATE_TRUST,
        REBUILD_PKI_TRUST,
        RECONSTITUTE_RECOVERY_SHARES,
        ROTATE_ROOT_AND_DERIVED_KEYS,
        CUT_OVER_CONSUMERS,
        INVALIDATE_CACHES,
        VERIFY_OLD_KEY_DENIED,
        VERIFY_NEW_KEY_AND_RESTORE,
        REQUIRE_INDEPENDENT_APPROVAL
    }

    public record IncidentAsset(
        String incidentId,
        AssetType assetType,
        Exposure exposure
    ) {}

    public record RotationPlan(
        String incidentId,
        Set<Action> actions,
        boolean materialReplacementReviewRequired
    ) {}

    public static RotationPlan plan(IncidentAsset item) {
        Objects.requireNonNull(item);
        Objects.requireNonNull(item.incidentId());
        Objects.requireNonNull(item.assetType());
        Objects.requireNonNull(item.exposure());

        if (item.incidentId().isBlank()) {
            throw new IllegalArgumentException("Missing incident ID");
        }

        EnumSet<Action> actions = EnumSet.of(
            Action.REVOKE_IDENTITIES_AND_SESSIONS,
            Action.CONTAIN_COMPROMISED_WORKLOAD,
            Action.VERIFY_CLEAN_CONTROL_PLANE,
            Action.PRESERVE_EVIDENCE,
            Action.INVENTORY_DEPENDENCIES,
            Action.ASSESS_EFFECTIVE_PERMISSIONS,
            Action.CUT_OVER_CONSUMERS,
            Action.INVALIDATE_CACHES,
            Action.VERIFY_OLD_KEY_DENIED
        );

        boolean materialRisk =
            item.exposure() != Exposure.ACCESS_MISUSE_SUSPECTED;

        switch (item.assetType()) {
            case ACCESS_CREDENTIAL ->
                actions.add(Action.REPLACE_ACCESS_CREDENTIAL);

            case DATA_ENCRYPTION_KEY -> {
                if (materialRisk) {
                    actions.add(Action.ASSESS_NEW_DEK_AND_REENCRYPT);
                    actions.add(Action.VERIFY_NEW_KEY_AND_RESTORE);
                }
            }

            case KEY_ENCRYPTION_KEY -> {
                if (materialRisk) {
                    actions.add(Action.ASSESS_NEW_KEK_AND_REWRAP);
                    actions.add(Action.ASSESS_DEPENDENT_DEKS);
                    actions.add(Action.VERIFY_NEW_KEY_AND_RESTORE);
                }
            }

            case SHARED_HMAC_SECRET -> {
                if (materialRisk) {
                    actions.add(Action.REPLACE_SHARED_SECRET);
                }
            }

            case PRIVATE_SIGNING_KEY -> {
                if (materialRisk) {
                    actions.add(
                        Action.REPLACE_SIGNING_KEY_AND_UPDATE_TRUST);
                }
            }

            case CERTIFICATE_OR_CA -> {
                if (materialRisk) {
                    actions.add(Action.REBUILD_PKI_TRUST);
                }
            }

            case RECOVERY_SHARE -> {
                if (materialRisk) {
                    actions.add(Action.RECONSTITUTE_RECOVERY_SHARES);
                    actions.add(Action.VERIFY_NEW_KEY_AND_RESTORE);
                }
            }

            case DERIVED_ROOT_SECRET -> {
                if (materialRisk) {
                    actions.add(Action.ROTATE_ROOT_AND_DERIVED_KEYS);
                    actions.add(Action.VERIFY_NEW_KEY_AND_RESTORE);
                }
            }
        }

        if (materialRisk) {
            actions.add(Action.REQUIRE_INDEPENDENT_APPROVAL);
        }

        return new RotationPlan(
            item.incidentId(),
            Set.copyOf(actions),
            materialRisk
        );
    }

    public static void main(String[] args) {
        var incident = new IncidentAsset(
            "ir-2026-118",
            AssetType.DATA_ENCRYPTION_KEY,
            Exposure.MATERIAL_CONFIRMED_EXPOSED
        );

        var plan = plan(incident);
        System.out.println(plan.incidentId());
        System.out.println(plan.actions());
        // Chỉ in action metadata, không in key bytes hoặc tokens.
    }
}
~~~

### 22.1. Giới hạn của planner

- Nó không xác minh bằng chứng compromise; Exposure phải đến từ incident assessment đáng tin.
- Một incident thực tế có thể liên quan nhiều asset types và dependency chains cùng lúc.
- Nó không biết semantics của từng KMS/HSM, provider key state hoặc certificate revocation.
- Nó không tự đảm bảo clean control plane, IAM least privilege hay SoD.
- Nó không thực hiện rewrap/re-encrypt hoặc kiểm tra dữ liệu đã bị attacker đọc.
- Kết quả là **kế hoạch cần review**, không phải lệnh tự động chạy mọi action.

Production orchestration cần **incident/action IDs, idempotency, approval, provider readback, reconciliation, audit, kill switch và safety guard**. Đặc biệt không cấp quyền DestroyKey cho planner chỉ để “hoàn tất” một rotation.

## 23. Workflow state, idempotency và concurrency

Post-compromise rotation có thể kéo dài nhiều giờ/ngày, có nhiều teams và consumers. Cần state machine để không nhầm **đã tạo key mới** với **đã cutover toàn bộ**.

~~~mermaid
stateDiagram-v2
    [*] --> CONTAINED: Access paths blocked
    CONTAINED --> TRUST_RECOVERY: Control plane verified
    TRUST_RECOVERY --> SCOPED: Assets and dependencies mapped
    SCOPED --> APPROVED: Replacement plan approved
    APPROVED --> MATERIAL_READY: New material generated
    MATERIAL_READY --> DISTRIBUTING: Provision to consumers
    DISTRIBUTING --> MIGRATING: Rewrap/re-encrypt/trust update
    MIGRATING --> VERIFYING: Cutover checks
    VERIFYING --> RETIRING: All required consumers verified
    RETIRING --> MONITORING: Old operations denied
    MONITORING --> CLOSED: Residual risk accepted
    CLOSED --> [*]
~~~

### 23.1. Trạng thái phải phản ánh điều gì đã thực sự xảy ra?

- **CONTAINED:** compromised paths đã bị chặn và có readback.
- **TRUST_RECOVERY:** identity/control plane mới đã được xác minh.
- **SCOPED:** inventory/dependency graph đủ để ra quyết định.
- **APPROVED:** owner và approver độc lập duyệt replacement scope.
- **MATERIAL_READY:** provider đã tạo material mới và key policy đúng.
- **DISTRIBUTING:** consumers đang nhận version mới.
- **MIGRATING:** rewrap/re-encrypt/trust changes đang diễn ra.
- **VERIFYING:** positive/negative tests, data integrity và DR restore.
- **RETIRING:** old material không còn new use; dependencies được clearance.
- **MONITORING/CLOSED:** phát hiện persistence/old-key use và ghi residual risk.

### 23.2. Retry và event duplication

1. Dùng incident ID và action ID ổn định.
2. Trước khi chạy lại, đọc provider state và operation status.
3. Nếu API timeout, reconcile; không giả định operation chưa thực hiện.
4. Không tạo nhiều replacement keys vì webhook được gửi lặp.
5. Không đổi alias trong lúc consumer đang resolve mà thiếu version pinning.
6. Dùng CAS/immutable revision cho envelope migration.
7. Chỉ đánh dấu batch complete khi có **read-after-write verification**.

### 23.3. Tránh hai rotation workers tranh cùng một key

Một worker có thể đang rewrap DEKs trong khi worker khác bắt đầu re-encrypt. Cần lock/lease hoặc state transition có revision/fencing; stale worker không được ghi đè metadata mới. Mọi thao tác phải idempotent hoặc có reconciliation cụ thể.

## 24. Backup, DR và historical data sau compromise

Backup thường là nơi còn **ciphertext, encrypted DEK và key references cũ**. Rotation chưa hoàn tất nếu production dùng key mới nhưng archive/DR vẫn không thể phục hồi hoặc vẫn dựa vào material bị compromise.

### 24.1. Dependency inventory

~~~text
Compromised KEK-v1
   |
   +-- Wrapped DEKs for live objects
   +-- Encrypted DEKs in object versions
   +-- Database snapshots
   +-- Offline archives / legal retention
   +-- DR replicas and recovery media
   +-- Offline batch consumers
~~~

Với DEK compromise, thay DEK và re-encrypt payload cũng phải xét **mọi bản sao ciphertext**. Nếu chỉ re-encrypt live records, backup cũ có thể vẫn giải mã được bằng DEK bị lộ.

### 24.2. Restore test phải sử dụng đường khôi phục thật

1. Restore ciphertext, nonce, tag, AAD schema và encrypted DEK từ backup.
2. Dùng recovery principal được phê duyệt trong clean DR environment.
3. Unwrap bằng key version đúng; xác minh trusted tenant/object scope.
4. Decrypt/Verify payload bằng reader tương thích.
5. Kiểm tra ứng dụng không dùng lại old credentials hoặc old Encrypt key.
6. Xác minh audit, access controls và key availability.
7. Ghi rõ backup generations nào đã migrate và generations nào còn pending.

### 24.3. Không hủy key cũ chỉ vì production đã cutover

Old key có thể còn cần để đọc backup, archive hoặc historical signatures. Nếu key cũ bị compromise, vẫn phải quản lý rủi ro của việc giữ lại: giới hạn Decrypt, cô lập recovery, re-encrypt archive và deadline. Nhưng Destroy quá sớm có thể làm mất dữ liệu hợp lệ.

### 24.4. Crypto-shredding sau compromise

Destroy material trong KMS không thể xóa raw copies attacker đã lấy. Crypto-shredding chỉ có ý nghĩa với **mọi bản sao/recovery path thuộc phạm vi kiểm soát** và cần evidence provider. Không dùng việc xóa keyRef khỏi database làm bằng chứng.

## 25. Audit, evidence và post-rotation monitoring

Mỗi replacement cần truy vết được **vì sao thay, ai duyệt, material nào mới, consumer nào đã chuyển và key cũ còn được dùng ở đâu**.

### 25.1. Audit record minh họa

~~~json
{
  "incidentId": "ir-2026-118",
  "actionId": "rotate-dek-batch-042",
  "action": "REENCRYPT_WITH_NEW_DEK",
  "assetRef": "orders/dek-material-v12",
  "replacementRef": "orders/dek-material-v13",
  "scopeRef": "tenant-42/orders-2026",
  "requestedBy": "rotation-worker-prod",
  "approvedBy": "security-approver-17",
  "sourceRevision": 91,
  "targetRevision": 92,
  "result": "VERIFIED",
  "verifiedAt": "2026-11-28T04:10:00Z"
}
~~~

Đây là schema minh họa, không phải format chuẩn của mọi KMS. Không ghi plaintext DEK/KEK, private key, HMAC secret, bearer token hoặc dữ liệu nghiệp vụ nhạy cảm.

### 25.2. Evidence cần giữ

- Incident report, scope, time window và confidence assessment.
- Principal/session/grants đã revoke cùng provider readback.
- Key inventory và dependency snapshot trước migration.
- Approval, action IDs, key references/material versions mới.
- KMS/HSM operation records, consumer cutover và negative tests.
- Rewrap/re-encryption coverage, integrity checks và restore results.
- Old-key-use metrics, pending consumers, exceptions và deadline.
- Residual data exposure, evidence gaps và risk owner.

### 25.3. Monitoring sau rotation

Theo dõi tối thiểu:

- Old key vẫn được dùng để Encrypt/Sign/MAC/Wrap mới.
- Old credentials/roles/sessions tiếp tục được chấp nhận.
- Old JWKS/certificate/HMAC key vẫn được verifier tin.
- Unwrap/Decrypt dưới old KEK ngoài migration role.
- Consumer/region chưa nhận key epoch mới.
- New credentials bị đọc từ CI/logs hoặc có hoạt động bất thường.
- Re-encryption job thất bại, revision conflict hoặc backup không restore.
- Attacker persistence xuất hiện lại qua pipeline, endpoint hoặc identity.

### 25.4. Không đóng incident chỉ vì số lượng keys đã rotate đạt 100%

Có thể đã thay tất cả keys trong inventory nhưng attacker vẫn giữ **persistence**, có quyền tạo credentials mới hoặc control trust distribution. Closure phải dựa trên **eradication, effective deny, clean control plane, data/trust recovery và residual risk**, không chỉ số lượng key versions.

## 26. Case studies: các kiểu post-compromise rotation thường gặp

### 26.1. Case A — DEK bị lộ trong CI log

Một pipeline in plaintext DEK vào log và log được giữ trong artifact storage. Attacker đã có thể tải log cùng ciphertext từ object storage.

**Phản ứng:**

1. Dừng pipeline gây log secret và bảo toàn evidence.
2. Revoke CI credentials, access token và quyền đọc artifact bất thường.
3. Xác minh runner/pipeline/control plane sạch trước khi cấp key mới.
4. Xác định DEK material, objects, backups và thời gian exposure.
5. Generate DEK mới, dừng Encrypt dưới DEK cũ.
6. Re-encrypt payload đã xác định, cập nhật encrypted DEK/nonce/tag/AAD theo revision.
7. Kiểm tra archive và snapshots, không chỉ dữ liệu live.
8. Đánh giá data breach: attacker có thể đã giải mã dữ liệu trước migration.
9. Bổ sung secret redaction, scanning và test ngăn in key bytes.

**Bài học:** KEK non-exportable không bảo vệ plaintext DEK đã xuất ra CI log.

### 26.2. Case B — KEK bị sao chép cùng encrypted DEK backups

Một backup operator có bản sao raw KEK và tải encrypted DEK blobs của nhiều tenant. KMS account sau đó đã revoke nhưng attacker giữ cả hai loại material.

**Phản ứng:**

1. Cô lập backup access và revoke operator credentials/quorum.
2. Khôi phục clean KMS/HSM administration, audit và recovery identities.
3. Generate KEK mới và rewrap DEKs còn hợp lệ.
4. Đánh giá encrypted DEK blobs attacker đã lấy: họ có thể unwrap bằng KEK cũ.
5. Xác định DEKs có khả năng đã bị lộ và re-encrypt dữ liệu tương ứng bằng DEKs mới.
6. Restore test trên archive/DR; ghi generations đã migrate.
7. Retire old KEK sau dependency/retention review, không giả định Disable đã xóa bản copy attacker.

**Bài học:** Khi attacker giữ cả KEK lẫn wrapped DEK, chỉ rewrap hiện tại không bảo vệ các bản blob cũ đã bị thu thập.

### 26.3. Case C — private signing key bị lấy, verifier vẫn cache public key cũ

Private key JWT đã bị sao chép khỏi build server. Signer được thay key nhưng các verifiers nhiều vùng vẫn giữ old JWKS trong cache.

**Phản ứng:**

1. Cô lập build server, thay deployment credentials và rebuild runner.
2. Generate signing key pair mới trong HSM/KMS.
3. Cập nhật issuer và public JWKS qua trust channel sạch.
4. Thu hồi old trust theo incident severity, không chỉ xóa một entry.
5. Kiểm tra verifier cache, offline services, token lifetime và active sessions.
6. Phát hiện/đánh giá token giả đã phát hành trong incident window.
7. Test old compromised kid bị từ chối ở mọi verifier cần thiết.
8. Giữ public verification evidence lịch sử theo policy.

**Bài học:** Rotation private key chưa xong nếu verifiers vẫn tin old public key.

### 26.4. Case D — attacker kiểm soát CI/CD và lấy được cả key mới sau rotation

Đội vận hành phát hiện cloud credential bị lộ, revoke token và rotate API secrets. Tuy nhiên CI runner vẫn bị attacker kiểm soát; trong lần deploy tiếp theo, attacker đọc secret mới từ environment variables.

**Phản ứng:**

1. Không cấp thêm replacement secret vào runner đang bị compromise.
2. Cô lập runner, revoke runner identity và deployment credentials.
3. Kiểm tra pipeline definitions, repository permissions, artifacts và build provenance.
4. Rebuild CI/CD từ image/definition sạch, bảo vệ approvals và signing.
5. Tạo lại service identities/credentials từ clean control plane.
6. Rotate những secrets đã bị attacker đọc ở lần deploy sau.
7. Xác minh không còn persistence, self-hosted runner hoặc token cache.
8. Theo dõi credential issuance và secret reads sau recovery.

**Bài học:** Nếu không eradication persistence, post-compromise rotation có thể chỉ cung cấp cho attacker một bộ secret mới.

## 27. Ma trận kiểm thử post-compromise rotation

| Tình huống | Kết quả mong đợi |
|---|---|
| DEK plaintext bị lộ | Có DEK mới và re-encryption assessment cho mọi ciphertext phụ thuộc |
| Chỉ đổi KEK alias | Không được báo là DEK rotation |
| KEK bị lộ cùng wrapped DEKs | Đánh giá DEKs attacker có thể unwrap offline |
| Rewrap DEK đã lộ | Không được coi là khắc phục hoàn chỉnh |
| KMS principal bị chiếm nhưng key non-exportable | Revoke access và điều tra Decrypt/Sign outputs |
| Private signing key bị sao chép | New key pair và old verifier trust bị xử lý |
| Đổi kid nhưng giữ private bytes | Test phát hiện không phải rotation thực |
| Verifier cache old JWKS | Cutover test chưa đạt |
| HMAC shared secret bị lộ | New version và old-key acceptance cutoff |
| Verifier dual-accept old secret vô hạn | Policy test fail |
| CA/trust anchor bị compromise | PKI recovery và trust-store rollout được thực hiện |
| Recovery share bị lộ | Quorum/custodian reconstitution review |
| Parent KDF secret bị lộ | Derived child keys được inventory và thay theo dependency |
| Credential bị rotate nhưng CI runner vẫn bị chiếm | Clean runner/control plane chưa đạt |
| Attacker có CreateGrant/ChangeKeyPolicy | Self-escalation bị chặn |
| New key được tạo trên compromised host | Security review từ chối provisioning |
| New key distribution qua plaintext channel | Negative test từ chối |
| AES-GCM nonce reuse | Stop Encrypt cũ và re-encryption assessment |
| KEK rewrap nhưng DEK giữ nguyên | Nonce/usage state của DEK không reset |
| Migration timeout sau write | Reconcile operation/revision, không tạo ciphertext mơ hồ |
| Concurrent rotation workers | CAS/fencing ngăn stale metadata overwrite |
| Old producer tiếp tục Encrypt | Old-key-use alert và deny policy hoạt động |
| Old signing key vẫn được tin ở một region | Trust propagation test phát hiện |
| Offline consumer reconnect | Epoch/version guard ngăn hồi sinh old material |
| Backup archive còn wrapped DEK cũ | Dependency inventory/restore path được ghi rõ |
| Destroy old KEK trước DR restore | Destruction guard chặn |
| Re-encryption live data nhưng bỏ snapshots | Coverage test phát hiện dữ liệu cũ còn |
| New secret xuất hiện trong logs | Secret scanning/redaction cảnh báo |
| Duplicate incident webhook | Workflow idempotent, không tạo nhiều replacements |
| KMS timeout khi Generate/Disable | Readback/reconciliation xác định provider state |
| Audit sink bị attacker sửa | Independent audit source phát hiện evidence gap |
| Negative test principal cũ vẫn Decrypt/Sign được | Rotation chưa verified |
| Positive test workload mới Decrypt sai tenant | Authorization/AAD/context chặn |
| Re-encryption hoàn tất sau khi data đã bị đọc | Residual exposure vẫn được báo cáo |
| Chỉ có key version mới, không có consumer evidence | Không được đánh dấu cutover hoàn tất |

### 27.1. Positive và negative tests phải đi cùng nhau

- **Positive:** workload hợp lệ dùng key mới đúng tenant/object/purpose; decrypt/verify dữ liệu đã migrate; backup restore thành công.
- **Negative:** principal cũ bị từ chối; old signing/HMAC key không còn được tin theo policy; stale worker không thể Encrypt; keyRef/tenant giả bị từ chối.
- **Operational:** retry, failover, multi-region, cache invalidation, audit và reconciliation đều được thử.
- **Security:** test attacker còn giữ raw key có thể làm gì với ciphertext cũ, để báo cáo residual risk chính xác.

## 28. Những sai lầm thường gặp sau compromise

| Sai lầm | Hậu quả | Cách sửa |
|---|---|---|
| Rotate trước khi loại bỏ attacker persistence | Attacker lấy được key mới | Eradicate/rebuild control plane trước provisioning |
| Chỉ revoke IAM, bỏ qua raw key copies | Attacker dùng key offline | Exposure assessment và material replacement |
| Rewrap DEK đã bị lộ | DEK cũ vẫn giải mã ciphertext | DEK mới và re-encrypt theo scope |
| Rotate KEK rồi tuyên bố mọi DEK đã đổi | Payload vẫn dùng DEK cũ | Theo dõi DEK material version riêng |
| Chỉ đổi kid của signing key | Private key bytes cũ vẫn dùng được | Generate key pair mới |
| Chỉ xóa JWKS entry | Verifiers còn cache old public key | Trust propagation và cache verification |
| Giữ old HMAC key cho legacy vô thời hạn | Attacker tiếp tục tạo MAC | Cutoff có thời hạn theo incident severity |
| Disable KMS nhưng bỏ qua app DEK cache | Consumer vẫn dùng plaintext key | Cache invalidation/terminate workloads |
| Chỉ re-encrypt live data | Archive/backup cũ vẫn mở được | Dependency inventory và archive migration |
| Destroy KEK trước restore test | Mất dữ liệu không phục hồi được | Dependency clearance và DR verification |
| Tin non-exportable nghĩa không có data exposure | API Decrypt có thể đã trả plaintext DEK | Audit operations và outputs |
| Không thay credential dùng để provision keys | Attacker tái chiếm quyền | Rotate identity, CI/CD và secret manager credentials |
| Tạo key mới trong môi trường bị chiếm | Attacker lấy ngay material mới | Clean recovery environment |
| Không kiểm tra parent/derived keys | Child keys vẫn tái tạo được | Root/derivation dependency rotation |
| Đổi nonce trong metadata cũ | AEAD tag fail hoặc tạo hiểu nhầm an toàn | Decrypt/Verify và re-encrypt đúng |
| Reset nonce sau KEK rotation | AES-GCM reuse dưới DEK cũ | Nonce state theo DEK material |
| Không có CAS/idempotency | Partial writes hoặc stale worker phá envelope | Immutable revision/reconciliation |
| Chỉ xem KMS API 2xx là hoàn tất | Consumers/verifiers chưa cutover | Readback, positive/negative tests |
| Không giám sát old-key use | Old material tiếp tục hoạt động | Metrics/alerts và deny policy |
| Không giữ evidence | Không điều tra được phạm vi | Independent audit/retention |
| Nói re-encrypt làm dữ liệu đã lộ trở lại bí mật | Đánh giá incident sai | Ghi residual exposure trung thực |
| Xóa keyRef gọi là crypto-shredding | Raw key/backup có thể còn | Provider destruction evidence và recovery review |
| Rotate mọi thứ không phân biệt scope | Downtime, mất dữ liệu, tăng rủi ro migration | Exposure-based plan và owner approval |

## 29. Câu hỏi tự kiểm tra

**Câu 1. Post-compromise rotation khác rotation theo lịch ở điểm nào?**

**Trả lời:** Nó được kích hoạt bởi sự cố hoặc nghi ngờ compromise, cần containment, exposure assessment, clean recovery environment và xác minh attacker không còn khả năng dùng material cũ.

**Câu 2. Vì sao không nên rotate ngay trên máy có thể vẫn bị attacker kiểm soát?**

**Trả lời:** Attacker có thể lấy khóa mới ngay lúc sinh hoặc lúc provision. Cần khôi phục root of trust và control plane sạch trước.

**Câu 3. Revoke KMS grant có thu hồi plaintext DEK đã bị copy không?**

**Trả lời:** Không. Grant chỉ kiểm soát operation trong KMS; bản DEK attacker giữ có thể giải mã ciphertext offline.

**Câu 4. DEK đã lộ thì rewrap dưới KEK mới có đủ không?**

**Trả lời:** Không. Phải đánh giá DEK mới và re-encrypt dữ liệu; rewrap không đổi plaintext DEK bytes.

**Câu 5. KEK bị lộ thì tại sao cần kiểm tra encrypted DEK blobs cũ?**

**Trả lời:** Attacker có thể đã thu thập cả KEK và wrapped DEKs, sau đó unwrap offline kể cả khi KMS đã revoke quyền.

**Câu 6. KMS non-exportable có loại bỏ rủi ro dữ liệu bị lộ không?**

**Trả lời:** Không. Decrypt/GenerateDataKey có thể trả plaintext DEK; Sign API cũng có thể bị lạm dụng như oracle.

**Câu 7. Tại sao đổi kid không phải rotation signing key?**

**Trả lời:** kid chỉ là identifier; nếu private key bytes không đổi, attacker vẫn có thể ký bằng material cũ.

**Câu 8. Khi private signing key bị lộ, vì sao phải cập nhật verifier?**

**Trả lời:** Verifier vẫn có thể tin public key cũ và chấp nhận chữ ký giả. Cần trust revocation/rollout, cache và token policy.

**Câu 9. HMAC secret bị lộ có thể xử lý bằng cách disable tài khoản người biết secret không?**

**Trả lời:** Không đủ. Người đó có thể giữ bản sao secret và tạo MAC ngoài hệ thống; cần new secret và ngừng chấp nhận old key.

**Câu 10. Nếu root secret dùng KDF để sinh nhiều child keys bị lộ, cần làm gì?**

**Trả lời:** Inventory derivation tree, thay root material và dẫn xuất/cutover child keys mới theo domain separation; xử lý data/trust tương ứng.

**Câu 11. Tại sao cần clean CI/CD trước khi cấp secret mới?**

**Trả lời:** Runner hoặc pipeline bị chiếm có thể đọc lại credentials mới trong lần deploy tiếp theo.

**Câu 12. Có thể giữ old DEK để Decrypt lịch sử sau compromise không?**

**Trả lời:** Có thể cần một migration path được giới hạn và audit, nhưng không cho Encrypt mới; nếu DEK lộ, phải đánh giá dữ liệu lịch sử đã bị đọc và re-encrypt.

**Câu 13. KEK rotation có reset nonce state của DEK không?**

**Trả lời:** Không. Rewrap chỉ thay lớp bọc; DEK bytes vẫn giữ nguyên.

**Câu 14. Vì sao backup/DR phải nằm trong rotation scope?**

**Trả lời:** Archive có thể chứa ciphertext/encrypted DEKs cũ; bỏ sót chúng có thể để attacker giải mã hoặc khiến tổ chức không restore được.

**Câu 15. Re-encrypt có làm attacker quên plaintext đã lấy không?**

**Trả lời:** Không. Nó bảo vệ trạng thái tương lai, không thu hồi dữ liệu đã bị sao chép hoặc suy ra.

**Câu 16. Vì sao không chỉ dùng số lượng key versions để xác định hoàn tất?**

**Trả lời:** Consumers, verifiers, cache, offline regions và control plane có thể vẫn dùng old material; cần effective cutover evidence.

**Câu 17. Một certificate bị revoke tại CA có bảo đảm mọi client ngừng tin ngay không?**

**Trả lời:** Không mặc nhiên. Client có thể cache hoặc không kiểm tra revocation; cần xác minh effective trust tại verifiers.

**Câu 18. Khi nào rewrap DEK có thể đủ?**

**Trả lời:** Trong planned KEK migration khi DEK không bị compromise và threat model cho phép giữ nguyên payload key; không đủ khi plaintext DEK đã lộ.

**Câu 19. Tại sao rotation workflow cần idempotency và CAS?**

**Trả lời:** Để tránh duplicate alerts, retry và concurrent workers tạo nhiều keys hoặc ghi đè envelope revision sai.

**Câu 20. Điều kiện nào cho phép đóng post-compromise rotation?**

**Trả lời:** Attacker persistence đã được xử lý, clean control plane được xác minh, replacement đã cutover, old-key use bị chặn, dữ liệu/DR được kiểm thử và residual risk được owner chấp nhận.

## 30. Checklist triển khai Post-compromise rotation

Trước khi đóng workflow, xác nhận:

- **Incident:** incident ID, severity, time window, principal và key material liên quan đã được ghi?
- **Containment:** sessions, tokens, IAM roles, KMS grants và self-escalation paths đã bị chặn?
- **Eradication:** endpoint, CI/CD, secret provisioning và control plane đã được xác minh sạch?
- **Root of trust:** IdP, IAM, KMS/HSM admin, CA/JWKS, audit sink và recovery roles còn đáng tin?
- **Exposure:** phân biệt raw key exposure, API misuse, credential compromise và evidence gaps?
- **Inventory:** key material/version, derived keys, consumers, ciphertexts, backups và trust dependencies được liệt kê?
- **DEK:** nếu plaintext DEK lộ, đã đánh giá DEK mới, re-encryption và archive copies?
- **KEK:** nếu KEK lộ, đã đánh giá wrapped DEKs attacker có thể đã thu thập và khả năng DEK đã bị unwrap?
- **HMAC/PSK:** secret mới đã provision, producers/verifiers cutover và old acceptance cutoff?
- **Signing:** private key mới, verifier trust/JWKS/certificate, cache và historical signatures được xử lý?
- **PKI:** CA/trust anchor compromise có recovery path và channel phân phối độc lập?
- **Recovery shares:** custodians/quorum/share copies đã được xử lý và restore test đạt?
- **Derived keys:** parent/root secret compromise đã được lan truyền qua derivation dependency graph?
- **Nonce/AEAD:** key/nonce state, tag/AAD và algorithm policy đúng; không reset nonce khi chỉ rewrap KEK?
- **Migration:** rewrap/re-encrypt phân biệt rõ; CAS, idempotency và read-after-write verification hoạt động?
- **Consumers:** mọi producers, readers, regions, queues, offline jobs và verifiers đã chuyển version?
- **Cache:** plaintext keys, tokens, sessions, sidecars và runtime caches được invalidated/limited?
- **Old material:** new Encrypt/Sign/MAC/Wrap dưới old key bị chặn; historical use được giới hạn và audit?
- **Backup/DR:** archive, snapshots, replicas và recovery principals đã được kiểm thử Decrypt/Restore thật?
- **Audit:** action IDs, approvals, provider outcomes, key refs/versions và evidence được bảo vệ độc lập?
- **Monitoring:** old-key-use, stale credentials, persistence, failed migration và verifier cache được theo dõi?
- **Residual risk:** data đã có thể bị attacker đọc, evidence gaps và exceptions được ghi rõ?
- **Destruction:** không Destroy material trước dependency/retention/restore clearance và provider confirmation?
- **Closure:** có owner, approver, negative/positive test results, monitoring plan và post-incident review?

**Ghi nhớ:** **Post-compromise rotation** không chỉ là tạo một version key mới. Phải **loại bỏ đường attacker quay lại, khôi phục root of trust, xác định chính xác material và dữ liệu đã bị ảnh hưởng, thay đúng DEK/KEK/signing/HMAC/credentials, cutover mọi consumer và xử lý old-key acceptance**. **Rewrap không cứu DEK đã lộ; đổi kid không cứu private key đã copy; revoke IAM không xóa raw key; và rotation trong CI/CD còn bị chiếm chỉ giúp attacker lấy secret mới.** Kết hợp **KMS/HSM, envelope encryption, IAM, SoD, key inventory, audit, backup/DR, idempotent migration và negative tests** để phục hồi một miền tin cậy mới có thể kiểm chứng.
