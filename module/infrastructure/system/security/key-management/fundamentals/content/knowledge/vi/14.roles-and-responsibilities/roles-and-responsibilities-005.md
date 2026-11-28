# Application owner — Chủ sở hữu ứng dụng trong quản lý khóa mật mã

## 1. Application owner là ai?

**Application owner (chủ sở hữu ứng dụng)** là cá nhân hoặc vai trò tổ chức chịu **trách nhiệm giải trình (accountable)** về một ứng dụng trong suốt quá trình thiết kế, phát triển, triển khai, vận hành và ngừng sử dụng. Trong **quản lý khóa mật mã**, application owner phải bảo đảm ứng dụng **sử dụng khóa đúng mục đích, đúng phạm vi, đúng quyền, theo chính sách đã được phê duyệt**, và có khả năng ứng phó khi khóa cần xoay vòng, thu hồi hoặc hủy.

Ví dụ, một dịch vụ Java quản lý đơn hàng dùng AES-GCM để bảo vệ địa chỉ khách hàng, KMS để bọc khóa dữ liệu, TLS để bảo vệ kết nối và chữ ký số để xác thực sự kiện gửi sang đối tác. Application owner của dịch vụ Orders **không nhất thiết tự giữ các private key hoặc raw DEK**. Tuy nhiên, họ phải biết khóa nào đang bảo vệ dữ liệu gì, workload nào được dùng chúng, ai chịu trách nhiệm vận hành, và điều gì sẽ xảy ra khi một khóa không còn đáng tin.

Trong chương **Vai trò và trách nhiệm** của mô-đun **SECURITY_KEY_MANAGEMENT_FUNDAMENTALS**, application owner là cầu nối giữa **nhu cầu nghiệp vụ, thiết kế hệ thống, chính sách an ninh và hoạt động quản lý khóa** trong toàn bộ vòng đời: **tạo, cấp phát, lưu trữ, sử dụng, xoay vòng, thu hồi và hủy**. Các trách nhiệm này liên quan mật mã đối xứng, bất đối xứng, chữ ký số, KMS/HSM, envelope encryption, kiểm soát truy cập và kiểm toán.

> **Điểm cốt lõi:** **Chịu trách nhiệm về một ứng dụng không đồng nghĩa được phép làm mọi việc với khóa của ứng dụng đó.** Application owner có quyền yêu cầu, kiểm tra và điều phối theo thẩm quyền nhưng không mặc nhiên được xuất private signing key, tự thay key policy hoặc tự phê duyệt hành động hủy khóa nhạy cảm.

### 1.1. Application owner khác workload identity

**Application owner** là vai trò chịu trách nhiệm quản trị và rủi ro. **Workload identity** là danh tính kỹ thuật của một process/service account được xác thực khi gọi KMS/HSM. Một người chịu trách nhiệm dịch vụ không đồng nghĩa với danh tính có quyền Decrypt của mọi tenant.

Phải phân biệt:

| Khái niệm | Chức năng chính |
| --- | --- |
| **Application owner** | Chịu trách nhiệm ứng dụng đáp ứng yêu cầu nghiệp vụ và an ninh |
| **Service/product owner** | Có thể trùng application owner tùy tổ chức; tập trung chất lượng dịch vụ/sản phẩm |
| **Key owner / custodian** | Chịu trách nhiệm chính sách hoặc quản trị vật liệu khóa theo phân công |
| **Workload identity** | Principal kỹ thuật để KMS/IAM xác thực và cấp quyền thao tác |
| **Data owner** | Quyết định phân loại, lưu giữ và các mục đích sử dụng dữ liệu |

Không tạo một nhóm IAM rộng tên **application-owner** rồi cho phép mọi thành viên xuất/giải mã tất cả các khóa. **Quyền thực thi phải gắn với nhiệm vụ, operation, tài nguyên và môi trường**.

## 2. Những trách nhiệm cốt lõi của application owner

Application owner phải chuyển chính sách chung thành **yêu cầu, kiểm soát và bằng chứng** cụ thể cho ứng dụng.

1. **Xác định nhu cầu bảo vệ:** Phối hợp Data owner/Security xác định dữ liệu và thông điệp cần tính bí mật, toàn vẹn, xác thực và khả năng kiểm chứng lâu dài.
2. **Chỉ định key purpose:** Phân biệt khóa Encrypt/Decrypt, Wrap/Unwrap, Sign/Verify, MAC key, pepper, traffic keys và private/public key.
3. **Duy trì key inventory:** Biết key ID/version, owner, thuật toán, environment, tenant, KMS reference, key state và tài sản phụ thuộc.
4. **Đảm bảo tích hợp đúng:** Ứng dụng dùng API mật mã đã được thẩm định; không hardcode khóa, không ghi raw secret, không bỏ qua xác minh tag hoặc chữ ký.
5. **Phối hợp quyền sử dụng:** Yêu cầu và rà soát IAM grants, service identities, role separation và chính sách KMS/HSM.
6. **Thiết kế rotation/revocation:** Có kế hoạch thay khóa, tương thích phiên bản, di chuyển ciphertext, cập nhật JWKS/truststore và xử lý cache.
7. **Chuẩn bị incident response:** Xác định blast radius của DEK, KEK, signing/MAC key và đường cô lập khẩn cấp.
8. **Bảo đảm monitoring và audit:** Ghi key ID, principal, operation, kết quả và lịch sử thay đổi mà không ghi key bytes.
9. **Đảm bảo DR và khôi phục:** Kiểm thử các kịch bản mất KMS, phục hồi backup và khóa cũ không còn khả dụng.
10. **Quản trị kết thúc vòng đời:** Xác nhận dữ liệu còn phải giữ, chuyển giao owner, thu hồi grants và chỉ hủy khóa sau khi hết phụ thuộc.

### 2.1. Những quyết định không được tự ý vượt thẩm quyền

- **Chuẩn thuật toán và ngoại lệ mật mã:** Cần Security hoặc hội đồng phù hợp phê duyệt; không chọn thuật toán lỗi thời chỉ để tránh sửa code.
- **Lưu giữ và xóa dữ liệu:** Thuộc thẩm quyền của Data owner và các yêu cầu pháp lý/chính sách áp dụng.
- **Export raw key, thay KMS policy, destroy key:** Do quyền và quy trình đã được phân tách; application owner không mặc định được tự làm.
- **Chỉ huy sự cố tổ chức:** Thuộc Incident Response/Security theo quy trình; AO cung cấp phụ thuộc và triển khai biện pháp cho ứng dụng.
- **Cho phép một user đọc tài nguyên:** Vẫn phải có authorization theo user/tenant/record. Có quyền KMS Decrypt không tự cấp quyền nghiệp vụ.

Application owner là **người chịu trách nhiệm bảo đảm các lớp hoạt động cùng nhau**, không nhất thiết là người thực hiện từng thao tác kỹ thuật.

## 3. Bản đồ các vai trò cần phối hợp

| Vai trò | Trách nhiệm tiêu biểu | Điểm phối hợp với application owner |
| --- | --- | --- |
| **Application owner (AO)** | Quản trị kiểm soát khóa, phụ thuộc, rủi ro và vòng đời ở phạm vi ứng dụng | Chịu trách nhiệm nghiệm thu và tiếp tục bảo vệ hệ thống |
| **Data owner (DO)** | Phân loại dữ liệu, retention, legal hold và quyết định mục đích sử dụng | Xác nhận miền dữ liệu, thời hạn giữ và yêu cầu crypto-erasure |
| **Security/Cryptography (SEC)** | Tiêu chuẩn thuật toán, policy, threat model, đánh giá ngoại lệ | Review crypto design, kiểm soát compromise và yêu cầu chứng cứ |
| **Key custodian / KMS-HSM team (KC)** | Tạo và quản lý key resources, bảo vệ HSM, backup/rotation mechanisms | Cấp khóa, áp dụng disable/rotation/delete được phê duyệt |
| **IAM/Identity team (IAM)** | Workload identities, roles, grants, revoke session | Thi hành least privilege và tách quyền |
| **Developers / Technical lead (DEV)** | Code JCA/JCE, AEAD, Verify, test và xử lý lỗi | Triển khai thiết kế vào ứng dụng |
| **SRE / Operations (OPS)** | Triển khai, quan sát, DR, backup, rollout, rollback | Đảm bảo key version/cache và khả năng phục hồi |
| **Incident Response (IR)** | Điều phối sự cố, containment, điều tra và hậu quả | Nhận dependency map và kế hoạch thay key ở ứng dụng |
| **Audit / Compliance (AUD)** | Xác minh evidence và quy trình theo chính sách | Đối soát thay đổi, quyền và hoạt động kiểm toán |

**Tên chức danh có thể khác nhau** theo tổ chức. Một người có thể kiêm nhiều chức năng ở nhóm nhỏ, nhưng vẫn phải xem xét **xung đột lợi ích** và có review độc lập cho thao tác nhạy cảm.

### 3.1. Mỗi ứng dụng phải có owner liên hệ được

Inventory không nên chỉ ghi **Backend Team** rồi không có ai quyết định khi khóa bị lộ lúc nửa đêm. Cần có **owner chính, người thay thế/on-call, kênh escalation, lịch review** và quy trình cập nhật khi thay nhân sự.

## 4. RACI cho vòng đời khóa mật mã

**RACI** gồm **Responsible (R)** — thực hiện, **Accountable (A)** — chịu trách nhiệm quyết định, **Consulted (C)** — tham vấn, và **Informed (I)** — được thông báo.

Ví dụ phân công bên dưới cần được điều chỉnh theo quy chế; mỗi dòng có **một A chính**, không có nghĩa những phê duyệt liên ngành khác tự biến mất.

| Hoạt động | AO | DO | SEC | KC/IAM | DEV/OPS |
| --- | :---: | :---: | :---: | :---: | :---: |
| Xác định key purpose và yêu cầu ứng dụng | **A** | C | C | C | R |
| Phân loại dữ liệu và retention | C | **A** | C | I | R |
| Phê duyệt thuật toán/ngoại lệ mật mã | R | C | **A** | C | C |
| Đề xuất/cấp key resource đã duyệt | **A** | C | C | R | I |
| IAM grants cho workload của ứng dụng | **A** | I | C | R | C |
| Triển khai mã hóa/ký và kiểm thử | **A** | I | C | C | R |
| Inventory và dependency map | **A** | C | C | C | R |
| Rotation khóa ứng dụng | **A** | C | C | R | R |
| Incident response cấp tổ chức | R | C | **A** | R | R |
| Quyết định xóa dữ liệu nghiệp vụ | C | **A** | C | C | R |
| Thực thi destroy key đã phê duyệt | R | C | C | **A** | R |
| Đối soát chứng cứ bảo mật ứng dụng | R | C | **A** | C | C |

Với production KEK/root hoặc private signing key, nên áp dụng **separation of duties**: người đề xuất không tự phê duyệt/thi hành mọi bước; KMS admin không tự ra quyết định retention; developer không mặc nhiên có quyền Export hoặc Destroy. Nếu có **break-glass**, cần kiểm soát phạm vi, thời hạn, audit và hậu kiểm.

## 5. Quyết định quan trọng trước khi ứng dụng tạo khóa

Một ứng dụng cần có **key design record**: hồ sơ xác định **dữ liệu, mục tiêu bảo vệ, thuật toán, phạm vi khóa, cách phân phối, quyền sử dụng và phương án sự cố**. Application owner chịu trách nhiệm bảo đảm hồ sơ được thống nhất với các bên có thẩm quyền.

### 5.1. Mục tiêu bảo vệ xác định primitive

| Nhu cầu của ứng dụng | Cơ chế có thể phù hợp | Điều AO cần kiểm tra |
| --- | --- | --- |
| Mã hóa dữ liệu nhạy cảm trong database | AEAD như **AES-GCM**, DEK/KEK | Ai được đọc, nonce, AAD, key versions, retention, backup |
| Xác thực webhook đối tác | **HMAC** hoặc chữ ký số theo quan hệ tin cậy | Canonical bytes, key ID, chống replay, phạm vi secret |
| Ký hóa đơn hoặc báo cáo | **Chữ ký số** với private signing key được bảo vệ | Người ký, chính sách Verify, chứng chỉ và lịch sử chữ ký |
| Giao tiếp giữa Java microservices | **TLS 1.3/mTLS** khi cần | Truststore, endpoint identity, cert rotation, quyền API |
| Bảo vệ mật khẩu | **Argon2id/scrypt/PBKDF2** phù hợp với salt; pepper nếu có yêu cầu | Không lưu plaintext; KDF cost, salt, pepper rotation |
| Chuyển bí mật/DEK cho đối tác | KMS wrapping, HPKE hoặc giao thức được thẩm định | Xác thực người nhận, key usage, quyền và khả năng khôi phục |

**Application owner không tự viết thuật toán mật mã.** Họ cần yêu cầu sử dụng primitive/giao thức đúng và triển khai qua thư viện/provider đã được thẩm định. Ví dụ, SHA-256(password) không trở thành password hashing an toàn chỉ vì hệ thống dùng HTTPS.

### 5.2. Phạm vi sử dụng và blast radius

Trước khi tạo key, cần xác định:

1. **Một khóa bảo vệ bao nhiêu tài sản?** Theo tenant, hồ sơ, file, môi trường hay phiên?
2. **Ai được phép gọi operation nào?** Encrypt, Decrypt, Sign, Verify, Wrap, Unwrap và GenerateMac cần phân biệt.
3. **Khóa nằm ở đâu?** KMS managed key, HSM, secret manager, wrapped DEK hay ephemeral session memory?
4. **Miền nào được tin cậy?** Production, staging, DR, vùng, tài khoản cloud, tenant và service identity?
5. **Khóa cũ còn cần cho lịch sử bao lâu?** Ciphertext, chữ ký, token, bản sao lưu, nghĩa vụ audit?
6. **Nếu key bị compromise?** Có thể chặn dùng, thay key, tìm ciphertext và xác định khách hàng ảnh hưởng trong thời gian phù hợp không?

Không chọn một DEK chung cho mọi tenant chỉ để giảm số bản ghi key mà không đánh giá rủi ro. Ngược lại, dùng một DEK cho mỗi record có thể tăng chi phí metadata; cần cân đối **blast radius, hiệu năng, khả năng rotation và crypto-erasure**.

### 5.3. Những yêu cầu kỹ thuật cần được nghiệm thu

Application owner phối hợp Security/DEV để kiểm tra:

- AES-GCM dùng **nonce/IV đúng mode, không lặp dưới cùng DEK**; tag và AAD được xác minh trước khi trả plaintext.
- HMAC được tính trên **byte đã canonical hóa chính xác** và thông tin cần ràng buộc; có chính sách chống replay.
- Chữ ký số Verify bằng **public key có nguồn tin cậy**, không phải key bất kỳ gắn cùng payload.
- DH/ECDH được thực hiện trong **authenticated key establishment** với KDF và ràng buộc transcript theo giao thức.
- Không dùng chung một key tùy tiện cho mã hóa, MAC, signing hoặc các môi trường độc lập.
- Không bỏ qua xác minh chứng chỉ, signature hoặc authentication tag khi hệ thống lỗi.
- Định dạng dữ liệu mã hóa có **key ID/version, algorithm policy, IV, ciphertext/tag và wrapped DEK** phù hợp.

## 6. Key inventory: application owner phải biết chính xác những khóa nào tồn tại

**Không thể rotate/revoke/destroy một khóa an toàn nếu không biết những dữ liệu hoặc dịch vụ nào phụ thuộc nó.** Inventory của ứng dụng nên chứa **metadata và tham chiếu**, không phải vật liệu khóa bí mật.

| Trường inventory | Ví dụ | Ý nghĩa |
| --- | --- | --- |
| **applicationId / owner / on-call** | orders-service / orders-platform | Người chịu trách nhiệm và cách liên hệ |
| **key ID / version / alias** | orders-dek-v3 / 3 / orders-active | Xác định vật liệu qua rotation; alias không thay key ID |
| **key type / purpose** | symmetric / encrypt-order | Không dùng key sai chức năng |
| **algorithm / policy** | AES-256-GCM / nonce-v2 | Hỗ trợ review và migration |
| **environment / tenant / region** | production / tenant-a / primary-region | Ranh giới quyền và phạm vi sự cố |
| **KMS/HSM reference** | approved key resource | Liên kết kho quản lý và chính sách |
| **parent/child relationship** | KEK → wrapped DEK → ciphertext | Xác định blast radius khi KEK/root bị lộ |
| **lifecycle/security status** | active / retired / compromised | Phân biệt sử dụng bình thường và sự cố |
| **created/activated/retired time** | các mốc UTC | Lập kế hoạch rotation và điều tra |
| **IAM principal / usage policy** | orders-prod-service | Rà soát quyền thực tế |
| **retention / recovery owner** | data-policy-v2 / data-owner | Không hủy khi còn nghĩa vụ khôi phục |
| **audit/change reference** | CHG-2026-421 | Truy vết phê duyệt và biến động |

### 6.1. Ví dụ metadata quản trị khóa

~~~yaml
# Chỉ minh họa metadata nội bộ, không phải cấu hình KMS có sẵn.
applicationId: orders-service
applicationOwner: orders-platform
onCallTeam: orders-oncall
environment: production
keyRecords:
  - keyId: orders-dek-v3
    version: 3
    purpose: encrypt-order-pii
    algorithm: AES-256-GCM
    tenantScope: tenant-a
    wrappedBy: orders-kek-prod-v2
    storageType: application-envelope
    lifecycleState: active
    changeReference: CHG-2026-421
  - keyId: orders-signing-v2
    version: 2
    purpose: sign-order-event
    algorithm: Ed25519
    storageType: managed-hsm
    verificationKeySource: trusted-signing-registry
    lifecycleState: active
controls:
  prohibitRawKeyInLogs: true
  requireLeastPrivilege: true
  requireRotationRunbook: true
  requireCrossEnvironmentApproval: true
~~~

Trong nhiều kiến trúc, **DEK không tương ứng với một KMS key resource riêng**. KMS có thể quản lý KEK còn DEK được sinh và dùng tạm trong ứng dụng, sau đó lưu ở dạng wrapped. AO phải hiểu đúng ánh xạ **logical key ID, key material và key resource** để không đoán sai dữ liệu phụ thuộc.

### 6.2. Inventory phải được đối soát với thực tế

Một bản ghi Active trong database không bảo đảm key còn được KMS chấp nhận; một key Retired cũng có thể vẫn được workload cũ sử dụng vì cache.

AO cần phối hợp rà soát định kỳ:

- Key resources/versions và trạng thái KMS/HSM.
- IAM grants và workload identities được phép.
- Các ciphertext/wrapped DEK còn tham chiếu key version cũ.
- Chứng chỉ/JWKS/truststore hoặc verifier còn chấp nhận signer cũ.
- Backup, DR, replica và nghĩa vụ retention.

Các phát hiện quan trọng: **orphan key, không có owner, quyền thừa, key trạng thái mâu thuẫn hoặc raw secret nằm sai môi trường**. Không quét raw key để làm inventory.

## 7. Trách nhiệm của Application owner theo từng giai đoạn vòng đời

| Giai đoạn | Việc AO phải bảo đảm | Chứng cứ phù hợp |
| --- | --- | --- |
| **Generation** | Đúng algorithm, purpose, entropy, KMS/HSM và miền sử dụng | Design review, key ID/version, approval |
| **Provisioning** | Đúng workload/tenant/environment và đúng thao tác IAM | KMS policy, role/grant và deployment change |
| **Storage** | Không hardcode/log bí mật; backup và DR có bảo vệ | Secret scanning, storage architecture, inventory |
| **Usage** | Đúng AEAD/AAD/nonce, Verify, authorization và error handling | Code review, integration test và audit |
| **Rotation** | Có runbook, khả năng đọc version cũ và kế hoạch migration | Migration plan, tỷ lệ dữ liệu chuyển, test |
| **Revocation** | Chặn key không còn tin cậy tại nơi dùng/xác minh | Incident ID, negative tests, propagation evidence |
| **Destruction** | Hết phụ thuộc, retention cho phép, phê duyệt chính xác | Inventory, approval, KMS/HSM destruction evidence |
| **Monitoring/review** | Theo dõi key usage, quyền, drift và rủi ro tồn đọng | Review report, alerts, audit logs |

### 7.1. Tạo và cấp phát: sử dụng nguồn ngẫu nhiên mật mã

Khóa AES/HMAC phải được sinh bằng **CSPRNG/KMS/HSM** phù hợp, không bằng timestamp, java.util.Random hoặc chuỗi hardcode. Private signing key nên được giữ trong ranh giới bảo vệ thích hợp, có thể **non-exportable** nếu mô hình yêu cầu.

AO nên yêu cầu **cấp quyền sử dụng API** thay vì chuyển raw key giữa các máy; nhưng phải kiểm tra giới hạn API thực tế. KMS không nhất thiết hỗ trợ mọi loại HMAC/ECDH/KEM hay các tính năng export/import giống nhau.

### 7.2. Sử dụng: KMS không thay application authorization

Workload có quyền KMS Decrypt **không đồng nghĩa** người dùng có quyền đọc mọi hóa đơn. Ngoài KMS policy, ứng dụng phải kiểm tra **user/tenant/resource/action**; với AEAD, AAD/encryption context phải ràng buộc ngữ cảnh đáng tin cậy khi cần.

Không dùng một key chung cho Encrypt/Sign/GenerateMac không có cơ chế tách mục đích đúng chuẩn. Không tự giảm chế độ mã hóa hoặc bỏ xác thực tag khi gặp lỗi provider.

## 8. Application owner tại ranh giới KMS/HSM

~~~mermaid
flowchart TD
    AO["Application owner<br/>Purpose + inventory + lifecycle"]
    SEC["Security + Data owner<br/>Standards + retention + exceptions"]
    IAM["IAM / Workload identity<br/>Authorized principals"]
    KMS["KMS/HSM<br/>Key material + policy + audit"]
    APP["Ứng dụng Java<br/>Encrypt/Decrypt/Sign/Verify"]
    DATA["Data store<br/>Ciphertext + wrapped DEK"]
    AO --> SEC
    AO --> IAM
    AO --> APP
    SEC --> KMS
    IAM --> KMS
    APP -->|"Approved cryptographic APIs"| KMS
    APP --> DATA
    KMS -->|"Protected operations"| APP
~~~

Application owner phải biết đội KMS/HSM trả lời được các câu hỏi:

1. Khóa được giữ ở **managed KMS, dedicated HSM hay secret manager**? Có non-exportable không?
2. Ai được **Encrypt/Decrypt/Sign/Unwrap**, ai được **Create/Disable/ChangePolicy/Delete**?
3. KMS rotation thực sự làm gì? Thay key material, rewrap DEK hay chỉ đổi alias/version?
4. Audit ghi những operation nào, log ở đâu và giữ bao lâu?
5. Key được sao lưu hoặc replicate như thế nào và khôi phục DR ra sao?
6. Khi key bị compromised, có thể revoke principal và chặn API trong bao lâu? Raw key đã xuất có còn bản sao?
7. Khi hủy key, trạng thái nào là **scheduled/pending**, trạng thái nào đã **executed và verified**?

### 8.1. Non-exportable không chặn mọi lạm dụng

Nếu private signing key nằm trong HSM và không được export nhưng workload có quyền **Sign** bị chiếm, attacker vẫn có thể yêu cầu HSM ký thông điệp giả. AO phải phối hợp **kiểm soát nội dung được ký, quyền Sign theo principal, logging và phát hiện bất thường**.

### 8.2. Kiểm soát quyền theo môi trường

Production, staging và test nên dùng **key material và IAM roles tách biệt**. Không cấp test workload quyền Unwrap production KEK chỉ để làm integration test. Nếu phải chuyển dữ liệu, thực hiện quy trình được phép **sanitize/tokenize hoặc re-encrypt** dưới khóa môi trường đích.

DR có thể là bản phục hồi production và cần quyền truy cập key production theo kiến trúc được phê duyệt, nhưng điều đó **không tạo quyền mặc định cho sandbox/test**.

## 9. Envelope encryption: những quyết định AO cần đưa ra

**Envelope encryption** là thiết kế mà **DEK mã hóa trực tiếp dữ liệu**, còn **KEK bảo vệ DEK**. Application owner phải xác định ranh giới DEK, retention và cách lưu metadata để ứng dụng vận hành an toàn.

~~~mermaid
sequenceDiagram
    participant APP as Java Application
    participant KMS as KMS/HSM
    participant STORE as Data Store
    Note over APP: AO quy định tenant, purpose và data scope
    APP->>KMS: GenerateDataKey theo IAM/KMS policy
    KMS-->>APP: Plaintext DEK tạm + wrapped DEK
    APP->>APP: AES-GCM với IV mới và AAD
    APP->>STORE: Ciphertext/tag, IV, wrapped DEK, key ID/version
    APP->>STORE: Đọc bản ghi
    STORE-->>APP: Envelope + metadata
    APP->>APP: Kiểm tra quyền đọc dữ liệu/tenant
    APP->>KMS: Unwrap DEK theo quyền
    KMS-->>APP: DEK tạm nếu policy cho phép
    APP->>APP: Verify tag/AAD rồi giải mã
~~~

### 9.1. Chọn phạm vi DEK

| Chiến lược | Ưu điểm | Đánh đổi cần đánh giá |
| --- | --- | --- |
| Một DEK cho nhiều bản ghi trong ngân sách an toàn | Đơn giản hóa số lượng key references | Cần giới hạn nonce/usage, blast radius lớn hơn |
| DEK riêng theo tenant | Cô lập tenant, thuận lợi khi ngừng dịch vụ/xóa dữ liệu | Nhiều wrapped keys, inventory và rotation phức tạp |
| DEK riêng theo file/đối tượng | Giảm độ hạt xâm phạm, hỗ trợ crypto-erasure | Tăng metadata, chi phí unwrap và kiểm soát phục hồi |
| KMS mã hóa trực tiếp thông điệp nhỏ | Hạn chế plaintext key ở ứng dụng nếu API phù hợp | Giới hạn kích thước, chi phí và độ trễ của API |

AO không chỉ tối ưu số lượng khóa ít nhất. Quyết định phải xét **Data owner, multi-tenant, retention, performance, nonce AES-GCM và DR**.

### 9.2. Rewrap và re-encrypt khác nhau

- **Rewrap**: Bọc cùng DEK dưới KEK mới. Có thể phù hợp với **rotation KEK định kỳ** khi DEK vẫn an toàn.
- **Re-encrypt**: Giải mã trong ranh giới được phép, rồi mã hóa dữ liệu bằng **DEK mới**.
- Nếu **raw DEK đã bị lộ**, chỉ rewrap chính DEK cũ **không khôi phục tính bí mật của dữ liệu**; phải đánh giá re-encrypt và hậu quả dữ liệu đã bị sao chép.
- Nếu chỉ đổi KEK mà tiếp tục dùng DEK cũ, **ngân sách nonce/IV của DEK không được đặt lại**.

### 9.3. Bản sao lưu và dữ liệu lịch sử

AO phải kiểm tra backup/snapshot còn tham chiếu key ID nào, khả năng phục hồi KMS/HSM tại DR, và trạng thái revoked có thể bị hồi sinh sau restore không. Không hủy KEK hoặc DEK chỉ vì mọi request hiện tại đã chuyển v2 nếu **backup vẫn cần v1 để đọc dữ liệu hợp lệ**.

## 10. Java 17: policy gate được thiết kế theo trách nhiệm của AO

Ví dụ dưới đây minh họa một **lớp kiểm tra metadata trước khi gọi KMS**. Application owner xác định yêu cầu và bảo đảm triển khai; không phải người duyệt từng request Encrypt/Decrypt.

Giả định: **WorkloadIdentity** do hạ tầng xác thực cung cấp, **KeyRecord** đến từ inventory có quyền ghi được bảo vệ. Mã **không thay IAM/KMS policy** và không dùng raw key.

~~~java
import java.time.Instant;
import java.util.Objects;
import java.util.Set;

public final class ApplicationKeyPolicyDemo {
    enum Operation { ENCRYPT, DECRYPT, WRAP, UNWRAP, SIGN, VERIFY, GENERATE_MAC }
    enum State { PRE_ACTIVE, ACTIVE, RETIRED, SUSPENDED, REVOKED, DESTROYED }

    record WorkloadIdentity(
            String principalId,
            String environment,
            Set<String> allowedTenants,
            Set<Operation> allowedOperations
    ) {}

    record KeyRecord(
            String keyId,
            int version,
            String applicationOwnerId,
            String environment,
            String tenantScope,
            String purpose,
            State state,
            Set<Operation> permittedOperations
    ) {}

    record PolicySnapshot(String policyVersion, Instant validUntil) {}

    static boolean isAllowed(
            WorkloadIdentity workload,
            KeyRecord key,
            PolicySnapshot policy,
            String requestedTenant,
            String expectedPurpose,
            Operation operation,
            Instant now
    ) {
        if (workload == null || key == null || policy == null ||
                requestedTenant == null || expectedPurpose == null ||
                operation == null || now == null) {
            return false;
        }

        if (policy.policyVersion() == null ||
                policy.policyVersion().isBlank() ||
                policy.validUntil() == null ||
                !now.isBefore(policy.validUntil())) {
            return false; // Policy snapshot hết hạn: từ chối.
        }

        if (workload.principalId() == null ||
                workload.principalId().isBlank() ||
                key.keyId() == null || key.keyId().isBlank() ||
                key.version() < 1 || key.state() != State.ACTIVE ||
                key.applicationOwnerId() == null ||
                key.applicationOwnerId().isBlank()) {
            return false;
        }

        if (!Objects.equals(workload.environment(), key.environment()) ||
                !Objects.equals(requestedTenant, key.tenantScope()) ||
                !Objects.equals(expectedPurpose, key.purpose())) {
            return false;
        }

        return workload.allowedTenants() != null &&
                workload.allowedTenants().contains(requestedTenant) &&
                workload.allowedOperations() != null &&
                workload.allowedOperations().contains(operation) &&
                key.permittedOperations() != null &&
                key.permittedOperations().contains(operation);
    }

    public static void main(String[] args) {
        Instant now = Instant.parse("2026-11-28T00:00:00Z");
        var workload = new WorkloadIdentity(
                "orders-prod-service", "production",
                Set.of("tenant-a"),
                Set.of(Operation.ENCRYPT, Operation.DECRYPT)
        );
        var snapshot = new PolicySnapshot(
                "orders-key-policy-v2", now.plusSeconds(120));
        var active = new KeyRecord(
                "orders-dek-v3", 3, "orders-platform",
                "production", "tenant-a", "encrypt-order-pii",
                State.ACTIVE,
                Set.of(Operation.ENCRYPT, Operation.DECRYPT)
        );
        var revoked = new KeyRecord(
                "orders-dek-v2", 2, "orders-platform",
                "production", "tenant-a", "encrypt-order-pii",
                State.REVOKED,
                Set.of(Operation.ENCRYPT, Operation.DECRYPT)
        );

        System.out.println("Active key allowed: " +
                isAllowed(workload, active, snapshot, "tenant-a",
                        "encrypt-order-pii", Operation.ENCRYPT, now));
        System.out.println("Revoked key allowed: " +
                isAllowed(workload, revoked, snapshot, "tenant-a",
                        "encrypt-order-pii", Operation.ENCRYPT, now));
        System.out.println("Wrong tenant allowed: " +
                isAllowed(workload, active, snapshot, "tenant-b",
                        "encrypt-order-pii", Operation.DECRYPT, now));
    }
}
~~~

Kết quả mong đợi:

~~~text
Active key allowed: true
Revoked key allowed: false
Wrong tenant allowed: false
~~~

### 10.1. Những giới hạn bảo mật của ví dụ

1. **Nguồn dữ liệu:** Nếu client sửa được KeyRecord thành ACTIVE hoặc tự nhận workload production, gate trở nên vô nghĩa; identity và registry phải được xác thực.
2. **Quyền nghiệp vụ:** Kiểm tra tenant chưa chứng minh người dùng có quyền xem đơn hàng cụ thể. Vẫn cần record-level authorization.
3. **Policy freshness:** Snapshot còn hạn không chắc đã nhận **revocation event mới nhất**; cần invalidation và/hoặc revocation epoch.
4. **KMS policy:** Sau khi gate trả true, IAM/KMS/HSM vẫn phải kiểm tra đúng resource, operation và encryption context.
5. **Race condition:** Key có thể bị thu hồi giữa lúc kiểm tra và lúc gọi KMS; enforcement phải có ở nơi thực thi, không chỉ trong Java.
6. **Đường khôi phục:** Dữ liệu mã hóa bằng key retired có thể cần Decrypt theo quy trình khôi phục đặc biệt; không mở chung mọi key state cho tất cả request.
7. **Owner metadata:** Trường applicationOwnerId phục vụ accountability, **không tự cấp quyền** cho principal đang gọi.

## 11. Rotation: trách nhiệm của AO trước, trong và sau khi thay khóa

Một lần rotation có thể làm gián đoạn cả hệ thống nếu các dịch vụ không dùng đúng key ID/version. Application owner phải chuẩn bị **runbook, dữ liệu phụ thuộc, phương án tương thích và tiêu chí kiểm thử**.

### 11.1. Runbook cho planned rotation

1. **Lý do và phạm vi:** Rotation định kỳ, usage limit, thuật toán cũ, thay owner hay sự cố an ninh?
2. **Kiểm kê:** v1/v2, wrapped DEK, ciphertext, signer, webhook consumer, JWKS cache và backup.
3. **Chuẩn bị v2:** KMS/HSM cấp khóa mới, IAM và policy được review, key ID/version nhất quán.
4. **Triển khai đọc/xác minh trước:** Các consumer có thể đọc/Verify phiên bản mới theo trust source.
5. **Chuyển ghi/ký mới:** Encrypt/Sign/GenerateMac bằng v2 tại mốc thống nhất.
6. **Migration:** Rewrap/re-encrypt khi cần, giữ data integrity và thử restore.
7. **Theo dõi:** Lỗi Verify/Decrypt, số bản ghi dùng v1, instance/cache và đối tác chưa cập nhật.
8. **Ngừng v1 theo chính sách:** Bảo đảm không còn giao dịch mới dùng v1; cho phép lịch sử có kiểm soát nếu cần.
9. **Retire/destroy khi đủ điều kiện:** Xác minh retention và backup/DR trước khi xóa vật liệu khóa.

### 11.2. Emergency revocation khác rotation bình thường

Trong rotation bình thường, bên nhận có thể chấp nhận v1 và v2 trong một cửa sổ kiểm soát. **Nếu v1 đã bị compromised**, cửa sổ chấp nhận v1 kéo dài có thể cho phép giả mạo webhook/token hoặc đọc dữ liệu trái phép. AO phải phối hợp IR/Security đánh giá **ngừng tin v1 sớm**, không áp dụng máy móc kế hoạch chồng lấn.

### 11.3. Rollback không được hồi sinh key cũ

Nếu ứng dụng đã bắt đầu ghi ciphertext bằng v2 nhưng bản deploy cũ chỉ đọc được v1, rollback sẽ gây lỗi. Cần chuẩn bị **compatibility đọc trước khi chuyển ghi**. Nếu v1 đã revoked, rollback phải giữ **chính sách từ chối v1**, dù code cũ có logic fallback.

## 12. Incident response: application owner cung cấp điều gì?

Khi nghi khóa bị lộ, application owner phải phối hợp Incident Response bằng **sơ đồ phụ thuộc, khả năng cô lập và kịch bản bảo vệ dữ liệu**.

~~~mermaid
flowchart TD
    ALERT["Phát hiện key exposure hoặc KMS API abuse"] --> IR["IR phân loại và quyết định containment"]
    IR --> AO["AO cung cấp inventory và owner contacts"]
    AO --> SCOPE["Xác định key version, service, tenant,<br/>ciphertext, token, backup và time window"]
    SCOPE --> BLOCK["Chặn quyền và thao tác nguy hiểm<br/>trên IAM/KMS/ứng dụng"]
    BLOCK --> NEW["Tạo key mới, cập nhật quyền và metadata"]
    NEW --> MOVE["Rewrap, re-encrypt, cập nhật trust<br/>hoặc password reset theo loại khóa"]
    MOVE --> TEST{"Negative tests, data integrity<br/>và cache/DR đều đạt?"}
    TEST -->|"Chưa"| SCOPE
    TEST -->|"Đạt"| CLOSE["Retire/destroy có phê duyệt<br/>Ghi audit và rủi ro tồn dư"]
~~~

### 12.1. Những câu hỏi AO phải trả lời khi có cảnh báo

- Khóa nào: **ID, version, type, purpose, algorithm, environment, owner**?
- Dữ liệu nào: **ciphertext, wrapped DEK, backups, tenants, tokens, signatures, messages**?
- Đối thủ có khả năng lấy **raw key**, chỉ **lạm dụng API**, hay đánh tráo **public verification key**?
- Quyền nào cần chặn: Encrypt, Sign, GenerateMac, Unwrap, Export, policy-admin?
- Có thể dừng ghi mới mà vẫn bảo vệ việc phục hồi dữ liệu hợp lệ không?
- KMS/clients/cache đã nhận trạng thái mới? Có **negative test** chứng minh không còn dùng key bị cấm?
- Cần báo cho ai: Data owner, đối tác, đơn vị hỗ trợ, đội IR hoặc bộ phận compliance?

### 12.2. Phản ứng khác nhau theo loại khóa

| Sự cố | Điều AO cần hỗ trợ |
| --- | --- |
| **DEK lộ dạng rõ** | Dừng Encrypt v1, xác định ciphertext, DEK mới và kế hoạch re-encrypt |
| **KEK/root key bị lộ** | Kiểm kê wrapped DEK/khóa con, phân loại blast radius và migration |
| **Private signing key bị lộ** | Chặn Sign, cập nhật chứng chỉ/JWKS, đánh giá chữ ký và token |
| **MAC key bị lộ** | Thay bí mật cho các bên, ngừng chấp nhận key cũ, kiểm tra replay/giao dịch |
| **Pepper bị lộ** | Đánh giá password hashes, migrate/reset, vẫn dùng password KDF phù hợp |
| **KMS principal bị chiếm** | Thu hồi IAM/session/grants, điều tra API output; chưa mặc định raw key đã bị lấy |
| **Nonce GCM bị tái sử dụng** | Ngừng dùng DEK liên quan, xác định ciphertext và sửa nonce policy |

**Thay khóa không thể xóa dữ liệu kẻ tấn công đã sao chép trước đó.** AO phải cung cấp đánh giá tác động nghiệp vụ; IR, Security và Data owner xử lý thông báo, nghĩa vụ pháp lý và quyết định giảm thiểu theo thẩm quyền.

## 13. Handover, ngừng ứng dụng và hủy khóa

Khi ứng dụng được chuyển giao, sáp nhập hoặc ngừng hoạt động, application owner cần bảo đảm **không có khóa vô chủ và không có dữ liệu hợp lệ bị mất vì xóa key quá sớm**.

### 13.1. Chuyển giao ownership

1. Bàn giao **key inventory**, key IDs/versions, owners, KMS/HSM references và dependency map.
2. Xác nhận nhóm nhận bàn giao có quyền và runbook phục vụ **rotation, certificate renewal, revocation và incident response**.
3. Rà soát IAM grants, service accounts, CI/CD secrets và quyền nhân sự cũ; thu hồi quyền không còn nhu cầu.
4. Kiểm tra backup/DR và khả năng Verify/Decrypt dữ liệu lịch sử theo retention.
5. Cập nhật on-call/escalation, contacts, audit ownership và hồ sơ ngoại lệ.
6. Đối soát với KMS/IAM thực tế, không chỉ sửa trường owner trong tài liệu.

### 13.2. Điều kiện trước khi Destroy

AO phải có bằng chứng rằng:

- Không còn **ciphertext hoặc wrapped DEK cần đọc** bằng key dự kiến hủy.
- Không còn **chữ ký, MAC tag, tài liệu hoặc token** cần xác minh bằng vật liệu tương ứng theo chính sách.
- **Data owner** đã xử lý thời hạn giữ dữ liệu và legal hold.
- Backup, DR, replica và secret caches có đường xử lý bản sao rõ ràng.
- Workloads và đối tác đã chuyển sang khóa mới, các quyền cũ đã được thu hồi.
- Phê duyệt độc lập được thực hiện theo quy định và kết quả KMS/HSM có bằng chứng.

**Pending deletion không đồng nghĩa destroyed.** Nếu key đã từng lộ, hủy key material tại KMS cũng không thu hồi được bản sao do đối thủ giữ.

## 14. Environment, DR và yêu cầu khả dụng của ứng dụng

Application owner phải ngăn dev/test/staging trở thành đường truy cập production:

- Dùng **DEK/KEK, HMAC key, private signing key và pepper riêng** cho các môi trường độc lập theo policy.
- Không cấp test principal quyền Decrypt prod KEK để làm test tiện lợi.
- Nếu cần dữ liệu production trong test, phối hợp Data owner và Security để **ẩn danh/chuyển đổi dữ liệu và re-encrypt** theo mục đích được phép.
- Không tin environment, tenant và key ID do HTTP client tự khai báo để quyết định quyền.
- DR có thể là bản phục hồi production và cần đường truy cập khóa được thiết kế đặc biệt; đó **không phải quyền mặc định của mọi môi trường non-prod**.

### 14.1. KMS/HSM outage: không được fallback về cách không an toàn

Khi KMS không sẵn sàng:

1. **Fail closed** với thao tác không thể đảm bảo mã hóa/xác minh hoặc key usage đúng chính sách.
2. Báo owner/on-call, thu thập số liệu lỗi theo key ID/operation không tiết lộ raw key.
3. Sử dụng HA/DR đã được phê duyệt; **không bật plaintext, DEK hardcode hoặc tắt Verify/tag** để dịch vụ tiếp tục chạy.
4. Xác minh key versions, IAM grants và dữ liệu sau phục hồi.
5. Đối soát lại cache và aliases để không sử dụng key revoked/compromised.

Application owner cần đặt **mục tiêu availability và recovery** ngay từ thiết kế, cùng với kiểm thử định kỳ. Một ứng dụng quan trọng không nên chỉ phát hiện mình mất khả năng giải mã dữ liệu khi KMS gặp sự cố thật.

### 14.2. Những chỉ số nên theo dõi

| Chỉ số | Tại sao hữu ích? |
| --- | --- |
| **Inventory coverage** | Tỷ lệ key resources và wrapped DEK có owner/purpose/version rõ |
| **Excess permissions** | Quyền IAM/KMS thừa hoặc cross-environment cần xử lý |
| **Key rotation age** | Khóa sắp vượt policy usage/time hoặc đã chậm thay |
| **Legacy version usage** | Mức sử dụng key cũ sau mốc chuyển đổi |
| **Decrypt/Verify failure rate** | Phát hiện lỗi phiên bản, AAD, trust source hoặc sự cố tích hợp |
| **Revocation propagation lag** | Độ trễ từ quyết định đến khi workload/verifier thực sự từ chối |
| **Unowned keys** | Khóa tồn tại nhưng không có người phụ trách |
| **DR restore success** | Khả năng phục hồi đúng dữ liệu và đúng quyền trong môi trường dự phòng |
| **Incident containment time** | Tốc độ chặn việc lạm dụng khóa |

## 15. Case study: Application owner của Payments Service

Một hệ thống Java microservices bao gồm:

- **Payments Service** mã hóa token thanh toán bằng AES-GCM và lưu dữ liệu trong database.
- **KMS** quản lý KEK production, còn DEK được tạo/giải bọc theo thiết kế envelope encryption.
- **Webhook Service** dùng HMAC để xác thực yêu cầu đối tác.
- **Identity Service** phát hành JWT ký bằng private key trong HSM.
- **Data owner** quyết định thời hạn giữ dữ liệu tài chính.
- **OPS/SRE** vận hành nhiều instance và một vùng DR.

### 15.1. Trong giai đoạn thiết kế

Application owner của Payments:

1. Phối hợp Data owner phân loại dữ liệu và phạm vi mã hóa.
2. Quyết định mô hình DEK theo tenant hoặc nhóm dữ liệu, chính sách IV/nonce và AAD.
3. Đề nghị KC/IAM cấp production KEK và thao tác đúng cho workload, tách khỏi staging.
4. Yêu cầu ciphertext lưu **key ID/version, IV, tag, wrapped DEK** theo format rõ ràng.
5. Phối hợp Webhook Service dùng **MAC key riêng theo environment/đối tác** và kiểm tra timestamp/request ID.
6. Đảm bảo JWT verifier có **issuer/trust source tin cậy**, kiểm tra signature và các claim nghiệp vụ.
7. Đặt test cho lỗi KMS, key rotation, cache cũ, nonce reuse, sai AAD, restore backup và dữ liệu khác tenant.

### 15.2. Trong một lần rotate KEK

KMS team đề xuất đổi KEK production v1 sang v2. Application owner cần kiểm tra:

- Những wrapped DEK và bản backup nào còn phụ thuộc KEK v1?
- Có thể **rewrap** DEK an toàn mà không cần re-encrypt payload hay không?
- Các instance đã biết sử dụng đúng key ID/version mới chưa?
- Dữ liệu mới và cũ vẫn đọc được sau rollout? DR có thể phục hồi từ backup không?
- Có yêu cầu Unwrap nào vẫn sử dụng KEK cũ sau mốc ngừng dùng?

AO **không nên nghiệm thu rotation chỉ vì một API của KMS báo tạo key mới thành công**; cần bằng chứng kiểm thử end-to-end và đối soát phụ thuộc.

### 15.3. Khi có sự cố lộ raw DEK

Một crash dump của Payments Service chứa raw DEK v1 và bị truy cập trái phép. Kế hoạch ứng phó:

1. AO cung cấp key ID, tenant/ciphertext và thời gian dùng v1 cho Incident Response.
2. IR/Security điều phối containment; IAM/KMS và OPS ngừng Encrypt mới bằng DEK v1.
3. DEV/OPS triển khai DEK mới, **re-encrypt** dữ liệu liên quan theo kế hoạch đã duyệt.
4. AO/Data owner đánh giá những dữ liệu có thể bị đọc và tác động nghiệp vụ.
5. Kiểm tra backup, bản ciphertext cũ và các bản sao DEK; **hủy DEK v1 trong KMS không lấy lại bản sao kẻ tấn công đã giữ**.
6. Lưu incident evidence và khắc phục nguồn tạo crash dump hoặc cách xử lý bí mật.

### 15.4. Test case phục vụ nghiệm thu

| Kiểm thử | Kết quả mong đợi |
| --- | --- |
| Dev workload yêu cầu Decrypt bằng prod KEK | Bị policy ứng dụng và IAM/KMS từ chối |
| Client đổi tenant trong request | Không vượt record-level authorization và AAD/context |
| AES-GCM tag hoặc AAD bị sửa | Không trả plaintext |
| Principal bị revoke thử Sign/Unwrap | Bị từ chối tại KMS/HSM, có audit |
| Rotation KEK với dữ liệu còn cần lưu | Giải mã được đúng bản ghi theo key version |
| DEK v1 bị compromise | Dừng Encrypt mới, chuyển sang DEK khác và đánh giá re-encrypt |
| API verifier còn cache khóa ký JWT bị revoke | Từ chối token không còn được tin theo chính sách |
| Restore snapshot DR cũ | Không làm sống lại grants hoặc key state bị revoked |
| Destroy key khi còn dữ liệu retention | Bị chặn bởi inventory/approval workflow |

## 16. Các anti-pattern thường gặp

| Cách làm sai | Rủi ro | Biện pháp |
| --- | --- | --- |
| “Đã có KMS nên không cần application owner.” | Không ai chịu trách nhiệm key purpose, dữ liệu và rotation | Chỉ định AO, key inventory và runbook |
| “AO phải được phép làm mọi việc với khóa.” | Lộ key, xung đột quyền, nguy cơ destroy nhầm | Separation of duties, least privilege, approval |
| Chỉ ghi owner trong tài liệu, không có on-call | Không ai xử lý sự cố ngoài giờ | Owner chính và backup/escalation rõ ràng |
| Không biết ciphertext phụ thuộc key nào | Rotation hoặc destroy gây mất dữ liệu | Inventory và key ID/version trong bản mã |
| Dùng chung KEK cho dev/test/prod | Sự cố non-prod ảnh hưởng production | Tách key material, IAM và môi trường |
| Xuất private key từ HSM để debug | Tăng phạm vi lộ bí mật | Dùng API Sign/Verify theo quyền và audit |
| Có quyền Decrypt KMS nên bỏ authorization | Lộ dữ liệu khác tenant/record | Kiểm tra user/tenant/resource/action |
| Bỏ qua tag hoặc signature khi gặp lỗi | Chấp nhận nội dung giả/sai | Fail closed và test đường lỗi |
| Lưu ciphertext mà không có key ID/version | Không truy xuất được sau rotation | Envelope format và migration rõ ràng |
| Rotate KEK rồi nghĩ đã thay DEK | DEK cũ và giới hạn nonce còn nguyên | Phân biệt rewrap với re-encrypt |
| Giữ key đã compromised để tương thích | Đối thủ tiếp tục khai thác key cũ | Emergency revocation và kế hoạch giảm gián đoạn |
| HSM non-exportable nên không cần giám sát | App bị chiếm vẫn gọi Sign/Unwrap | IAM, authorization và anomaly detection |
| Hủy key ngay khi ngừng app | Mất dữ liệu và chữ ký cần retention | Data owner approval, inventory và restore test |
| Ghi raw key vào log để điều tra | Khuếch đại sự cố tiết lộ secret | Log key ID, actor, operation, result, incident ID |
| Không đối soát inventory với KMS/IAM | Orphan keys, grants cũ, state bị lệch | Periodic reconciliation, review và audit |

## 17. Checklist dành cho Application owner

Trước khi nghiệm thu ứng dụng hoặc mỗi lần review an ninh, hãy xác minh:

1. **Ownership:** Có AO, người thay thế/on-call, key custodian và đường escalation?
2. **Data:** Data owner đã xác định phân loại, mục đích, thời hạn giữ và nghĩa vụ khôi phục?
3. **Purpose:** Mỗi key có key usage và thuật toán rõ, tránh dùng bí mật sai mục đích?
4. **Inventory:** Có key ID/version, environment, tenant, owner, KMS reference, state, dependency map?
5. **Generation:** Khóa sinh bằng CSPRNG/KMS/HSM phù hợp, không dùng RNG yếu hoặc hardcode?
6. **Storage:** Raw key/private key/pepper không ở Git, log, container image hoặc backup không được bảo vệ?
7. **Permissions:** Workload chỉ có quyền cần thiết; sử dụng, quản trị, export và destroy được phân tách?
8. **Data access:** Có authorization theo user/tenant/record và kiểm tra AEAD tag/signature trước khi dùng dữ liệu?
9. **Crypto parameters:** Nonce/IV, AAD, KDF, security strength và canonicalization được áp dụng đúng?
10. **Rotation:** Có runbook, tương thích key version cũ/mới, migration và rollback an toàn?
11. **Revocation:** Có thể ngừng dùng/trust key compromised ở KMS, app, PKI/JWKS và cache?
12. **Incident:** Có inventory, blast radius, IR contacts và negative tests để chứng minh containment?
13. **Availability:** KMS/HSM outage, backup restore và DR đã được thử nghiệm?
14. **Destruction:** Trước hủy đã xử lý ciphertext, wrapped DEK, chữ ký lịch sử, retention và các bản sao?
15. **Audit:** Có log key ID/version, principal, operation, kết quả và policy change mà không chứa raw secret?
16. **Review:** Có chu kỳ đối soát key grants, orphan keys, crypto exceptions và những thay đổi policy?
17. **Handover:** Khi đổi owner/ngừng app, các quyền, khóa và nghĩa vụ đã được chuyển giao hay thu hồi?

## 18. Ghi nhớ

- **Application owner chịu trách nhiệm giải trình về quản lý khóa của ứng dụng**, nhưng không tự động có quyền xuất hoặc sử dụng mọi key material.
- **Data owner, Security, KMS/HSM administrator, IAM, DEV, OPS và IR** có các thẩm quyền khác nhau. **RACI, least privilege, dual control và separation of duties** giúp giữ ranh giới rõ ràng.
- **Key inventory** là cơ sở để xác định khóa và dữ liệu phụ thuộc trong toàn bộ vòng đời; thiếu key ID/version, owner, purpose, environment và dependency map làm mọi thay đổi khó an toàn.
- **KMS/HSM hỗ trợ bảo vệ vật liệu khóa và thực thi quyền**, nhưng ứng dụng vẫn phải thực hiện **authorization nghiệp vụ, AAD, tag/signature verification và chống replay khi cần**.
- **Rewrap không phải re-encrypt**. Khi raw DEK bị lộ, chỉ đổi KEK không làm bản mã cũ bí mật trở lại.
- **Rotation, revocation và destruction** phải được kiểm tra ở nơi thực thi và trên backup/DR; chỉ đổi một nhãn trạng thái trong registry không đủ.
- **Trách nhiệm sở hữu phải đi kèm runbook, kiểm thử, audit và bằng chứng**, kể cả khi ứng dụng chuyển nhóm hoặc ngừng hoạt động.

Ba câu hỏi mà mỗi **Application owner** phải trả lời được là: **“Ứng dụng đang phụ thuộc những khóa nào?”, “Ai có quyền sử dụng và thay đổi chúng?”, “Nếu khóa bị lộ, phải thay hoặc bị hủy, chúng ta có thể chứng minh dữ liệu hợp lệ vẫn được bảo vệ và hệ thống được phục hồi an toàn không?”** Khi trả lời được bằng inventory, policy và kết quả kiểm thử thực tế, vai trò sở hữu mới trở thành một kiểm soát an ninh có hiệu lực.
