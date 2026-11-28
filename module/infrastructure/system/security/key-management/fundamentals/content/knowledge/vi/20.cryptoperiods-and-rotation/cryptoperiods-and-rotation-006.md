# Rotation khi thuật toán suy yếu – Chuyển đổi khóa, thuật toán và dữ liệu mật mã an toàn

**Rotation khi thuật toán suy yếu** là quá trình **đánh giá lại độ an toàn của một thuật toán, chế độ vận hành, giao thức, độ dài khóa hoặc tham số mật mã đang sử dụng; ngừng phát sinh tác vụ mới theo cấu hình không còn đạt yêu cầu; và chuyển khóa, dữ liệu, chữ ký, chứng chỉ cùng các bên sử dụng sang cấu hình được phê duyệt**. Đây không đơn giản là thay một key ID. Nếu thuật toán bảo vệ dữ liệu **không còn đủ an toàn**, chỉ sinh một khóa mới **cùng thuật toán yếu** có thể không giải quyết được rủi ro gốc.

Trong chương **Cryptoperiod và rotation** của module **SECURITY_KEY_MANAGEMENT_FUNDAMENTALS**, chủ đề này liên kết toàn bộ vòng đời **tạo → cấp phát → lưu trữ → sử dụng → xoay vòng → thu hồi → hủy khóa** với mật mã đối xứng, bất đối xứng, chữ ký số, KMS/HSM, envelope encryption, phân quyền, kiểm toán và khôi phục dữ liệu.

> **Ghi nhớ trước tiên:** **Đổi khóa (key rotation)**, **đổi thuật toán hoặc giao thức (algorithm/protocol migration)** và **chuyển dữ liệu/chữ ký lịch sử (cryptographic migration)** là ba công việc liên quan nhưng **không tương đương**. Nếu điểm yếu nằm ở AES mode, hash chữ ký, key exchange, key wrapping hoặc một protocol suite, **key mới nhưng cấu hình cũ** có thể vẫn yếu. Ngược lại, **đổi thuật toán cho dữ liệu mới** chưa làm ciphertext hoặc chữ ký lịch sử tự trở nên an toàn.

## 1. “Thuật toán suy yếu” nghĩa là gì?

Trong quản lý khóa, thuật toán hoặc cấu hình mật mã được xem là **không còn đáp ứng mức bảo vệ cần thiết** khi có một hay nhiều yếu tố:

1. **Phân tích mật mã mới:** có kỹ thuật tấn công làm giảm đáng kể biên an toàn so với giả định thiết kế.
2. **Độ dài khóa/nhóm tham số không còn phù hợp:** ví dụ một cấu hình khóa bất đối xứng quá ngắn so với security strength mong muốn.
3. **Collision/preimage/forgery risk:** hàm băm, MAC hoặc chữ ký có thuộc tính yếu đối với **mục đích đang dùng**.
4. **Mode hoặc giao thức triển khai sai:** dùng ECB, lặp nonce GCM, padding oracle, key/IV reuse, xác thực peer thiếu hoặc algorithm downgrade.
5. **Cơ chế bị ngừng hỗ trợ/deprecate:** tiêu chuẩn nội bộ, hệ sinh thái hoặc thư viện đã thay chính sách; cần kế hoạch thay thế dựa trên bằng chứng.
6. **Thay đổi mô hình đe dọa:** dữ liệu cần bí mật trong thời gian dài hoặc cần chống khả năng tấn công mới; một cấu hình từng hợp lý không còn đạt mục tiêu.
7. **Khả năng triển khai và vận hành:** thư viện/hardware không còn cập nhật bảo mật, provider KMS/HSM không thể bảo đảm đúng key usage hoặc parameter constraints.

**Phải phân biệt “thuật toán suy yếu” với “khóa bị lộ”.** Một thuật toán có thể còn mạnh nhưng raw key bị đánh cắp; lúc đó cần rotation/revocation vì **key compromise**. Ngược lại, một khóa chưa từng bị lộ vẫn có thể cần migration vì **thuật toán hoặc cách dùng khóa không còn đủ an toàn**.

### 1.1. Cryptoperiod và thời điểm phải đổi

**Cryptoperiod** là khoảng thời gian vật liệu khóa được phép sử dụng cho một hoặc nhiều thao tác theo chính sách. Có thể phân biệt:

- **Originator-usage period:** khoảng cho phép tạo ciphertext, chữ ký hoặc MAC **mới**.
- **Recipient-usage period:** khoảng cho phép giải mã hoặc xác minh **dữ liệu đã tạo trước đó**, với giới hạn và chính sách riêng.
- **Validity/trust period:** khoảng mà chứng chỉ, public-key binding, issuer hoặc key version được chấp nhận trong một ngữ cảnh nhất định.
- **Retention period:** thời gian phải giữ ciphertext, chữ ký, evidence và backup; **không tự bằng** cryptoperiod cho phép ký/mã hóa mới.

Nếu một thuật toán suy yếu, có thể cần **kết thúc originator usage ngay**, nhưng **chưa được xóa mọi khóa cũ** khi dữ liệu hợp lệ vẫn phải được đọc để migration hoặc phục hồi. Quyền legacy read phải được **khoanh vùng, theo thời hạn, được giám sát và giảm dần**.

### 1.2. “Còn giải mã được” không đồng nghĩa “còn an toàn”

Một bản mã dùng thuật toán yếu có thể vẫn giải mã chính xác. Điều đó chỉ chứng minh hệ thống còn đường xử lý dữ liệu, **không chứng minh dữ liệu còn bí mật trước đối thủ**.

Một chữ ký được tạo dưới thuật toán suy yếu có thể vẫn cho kết quả `Verify=true`. Điều đó không tự chứng minh **nguồn gốc, tính toàn vẹn và giá trị tin cậy hiện tại** theo chính sách mới. Cần phân biệt **xác minh toán học**, **thời điểm ký**, **trạng thái thu hồi** và **bằng chứng độc lập**.

## 2. Những ví dụ để hiểu đúng nguyên nhân suy yếu

| Tình huống | Thuộc tính bị ảnh hưởng | Hướng chuyển đổi cần đánh giá |
| --- | --- | --- |
| **DES hoặc một cấu hình khóa đối xứng quá ngắn** | Khó khăn của brute force không còn đạt mục tiêu. | Chuyển sang AEAD/key strength được phê duyệt, re-encrypt dữ liệu còn nhạy cảm. |
| **RC4 hoặc một cipher/mode đã bị loại khỏi profile bảo mật** | Tính bí mật hoặc cách dùng theo giao thức không đáp ứng mục tiêu. | Loại khỏi new encryption/protocol negotiation, migrate ciphertext hoặc traffic. |
| **AES-ECB cho dữ liệu có cấu trúc** | Lộ mẫu dữ liệu; không có xác thực. | Mã hóa lại bằng AEAD có nonce/AAD đúng. |
| **AES-GCM bị reuse nonce dưới cùng key** | Có thể phá confidentiality/integrity; vấn đề nằm ở cách sử dụng. | Chặn đường phát sinh nonce lỗi, dùng DEK mới và đánh giá re-encryption, dữ liệu đã ảnh hưởng. |
| **SHA-1 khi dùng cho chữ ký đòi hỏi collision resistance** | Bài toán collision có thể ảnh hưởng tính toàn vẹn/chữ ký. | Chuyển profile chữ ký/hàm băm phù hợp; đánh giá lại chữ ký lịch sử. |
| **RSA với modulus hoặc padding/profile không còn được chấp thuận** | Security strength hoặc an toàn của sơ đồ ký/mã hóa. | Tạo key pair mới, chuyển sơ đồ được duyệt, cập nhật verifier/certificates. |
| **Key exchange không xác thực peer** | MITM/identity-misbinding, dù primitive trao đổi có thể mạnh. | Dùng TLS/mTLS hoặc AKE được đánh giá, xác thực danh tính và transcript. |
| **Một TLS cipher suite/protocol bị loại khỏi policy** | An toàn phiên và negotiation. | Cập nhật endpoint + client, disable suite cũ, quản lý session/tickets. |
| **KDF/password hashing cấu hình quá yếu** | Dò mật khẩu ngoại tuyến dễ hơn. | Tăng work factor hoặc chuyển scheme được duyệt khi xác thực/reset. |
| **Key wrapping scheme không còn đủ an toàn** | Tính bí mật/toàn vẹn của DEK khi được bọc. | Re-wrap DEK bằng cơ chế được duyệt và xác minh dữ liệu phụ thuộc. |

**Các ví dụ là tình huống thiết kế**, không phải tuyên bố mọi tên thuật toán trong bảng đều luôn bị cấm ở mọi mục đích hay ở mọi thời điểm. Ví dụ **SHA-1 có nhiều mục đích sử dụng**, và kết luận về chữ ký số không được tự suy rộng sang mọi ứng dụng của hash. **AES-128 không tự được coi là hỏng**, và **AES-GCM không hỏng chỉ vì người triển khai cần kiểm soát nonce**. Hãy đánh giá chính xác **algorithm + parameters + mode + implementation + usage + threat model**.

### 2.1. Trường hợp cần đổi thuật toán ngay, không chỉ đổi key

**Ví dụ 1 – ECB:** Dữ liệu hóa đơn đang dùng AES-ECB. Tạo một khóa AES khác nhưng tiếp tục dùng ECB **không loại bỏ việc lộ mẫu**. Cần chuyển sang cơ chế mã hóa có xác thực như AES-GCM theo chính sách, đồng thời xác định format, nonce/tag và AAD.

**Ví dụ 2 – chữ ký dựa trên profile hash không còn được chấp thuận:** Tạo RSA key mới nhưng **tiếp tục dùng scheme/hash cũ** có thể vẫn sai. Cần đổi **cả key profile và signature scheme/hash**, rồi nâng cấp verifier/trust.

**Ví dụ 3 – nonce reuse:** Thuật toán AES-GCM có thể phù hợp, nhưng cách sinh nonce vi phạm yêu cầu duy nhất theo key. Phải **sửa cơ chế nonce, ngừng dùng DEK bị ảnh hưởng cho mã hóa mới**, đánh giá exposure và chuyển dữ liệu theo rủi ro. Chỉ thay ciphertext metadata hoặc tăng key size **không chữa bản mã đã tạo với nonce lặp**.

**Ví dụ 4 – giao thức key exchange chưa xác thực:** Đổi từ một nhóm ECDH sang nhóm khác nhưng vẫn không ràng buộc danh tính peer thì **MITM vẫn có thể xảy ra**. Cần sửa giao thức xác thực và key schedule, không chỉ thay elliptic curve.

## 3. Phân loại nguồn cảnh báo và đưa ra quyết định có căn cứ

Một sự kiện khởi phát rotation có thể là:

- Báo cáo phân tích mật mã được chuyên gia hoặc tổ chức chuẩn hóa đánh giá.
- Thay đổi policy/chuẩn kỹ thuật áp dụng cho hệ thống.
- Lỗ hổng trong **implementation hoặc thư viện**, có thể cần vá và rotate key tùy dạng lộ.
- Thay đổi loại dữ liệu và thời hạn bí mật cần bảo vệ.
- Audit phát hiện mode/nonce/key usage sai.
- Yêu cầu từ nhà cung cấp KMS/HSM/PKI hoặc thay đổi tính năng/chứng nhận trong **phạm vi cụ thể**.
- Sự cố credential/key bị lộ hoặc nghi bị lộ.

**Không ra quyết định chỉ từ tên thuật toán trong một headline.** Cần xác minh **phiên bản thư viện, tham số, môi trường, mục đích, loại dữ liệu và bằng chứng khai thác** trước khi ấn định phạm vi migration.

### 3.1. Ma trận đánh giá ưu tiên

| Yếu tố | Câu hỏi | Ảnh hưởng đến ưu tiên |
| --- | --- | --- |
| **Khả năng tấn công thực tế** | Có kỹ thuật khả thi, công cụ công khai hoặc exploitation đang diễn ra? | Càng cao càng cần containment gấp. |
| **Thuộc tính bị ảnh hưởng** | Confidentiality, integrity, authenticity hay availability? | Quyết định re-encrypt, re-sign, revoke hoặc protocol migration. |
| **Lượng dữ liệu và blast radius** | Một DEK cho một file hay một KEK bọc hàng triệu DEK? | Quy mô inventory, migration và response. |
| **Thời gian dữ liệu phải bí mật** | Dữ liệu vài ngày hay nhiều năm? | Long-lived data có thể cần chuyển sớm hơn. |
| **Đường tấn công** | Attacker có ciphertext, public key, session traffic, logs hoặc token? | Định mức rủi ro với dữ liệu lịch sử. |
| **Control bù trừ** | HSM, IAM, network isolation, trusted timestamp có tác dụng thực tế nào? | Có thể giảm phạm vi, không phủ nhận yếu điểm thuật toán. |
| **Sự phụ thuộc và khả năng rollback** | Consumer/backup/SDK có hiểu format mới không? | Quyết định staging, canary, dual-read. |
| **Yêu cầu pháp lý/hợp đồng** | Profile bảo mật nào bắt buộc và đến thời điểm nào? | Cần đối chiếu tài liệu áp dụng hiện hành. |
| **Khả năng chuyển đổi** | Còn bản gốc để re-encrypt/re-sign, có API KMS hỗ trợ không? | Chọn phương án migration thực thi được. |

**Không tự tạo “điểm CVSS cho thuật toán”** hoặc khẳng định một thời hạn cố định áp dụng cho mọi loại khóa. Security owner nên ghi **quyết định, bằng chứng, exception/expiration và người duyệt** theo từng key family.

### 3.2. Phân biệt suy yếu với compromise

| Dạng sự cố | Khóa cũ có thể chưa bị lộ? | Việc thường phải làm |
| --- | --- | --- |
| Thuật toán/mode yếu | **Có.** | Ngừng new operations yếu và chuyển format/algorithm; đánh giá dữ liệu lịch sử. |
| Raw DEK/KEK/private key bị lộ | **Không thể coi còn bí mật.** | Revoke/rotate material, điều tra dữ liệu/chữ ký bị ảnh hưởng. |
| Credential có quyền KMS bị lộ | Key material có thể vẫn ở trong KMS. | Thu hồi credential/grants, kiểm audit Sign/Decrypt/Unwrap đã xảy ra. |
| Sai trust/public-key binding | Không nhất thiết raw private key bị lộ. | Sửa issuer/trust registry, revoke key mapping và rà soát event được Verify. |
| Thư viện có lỗi xử lý ciphertext | Tùy lỗi và exploitation. | Vá implementation, thử dữ liệu, rotate/migrate theo tác động cụ thể. |

Việc một key **non-exportable trong HSM** không cứu được dữ liệu nếu **chính primitive/mode sử dụng nó không đủ an toàn**. Non-exportability và thuật toán là **những lớp kiểm soát khác nhau**.

## 4. Tư duy crypto-agility: phải thay được cả khóa lẫn cơ chế

**Crypto-agility** là khả năng **nhận diện, cấu hình, thay thế, triển khai, xác minh và loại bỏ** các primitive/parameters/protocol suites theo chính sách mà không phải viết lại toàn bộ hệ thống.

Một thiết kế crypto-agile có:

1. **Inventory các thuật toán**, key usages, key families và dữ liệu phụ thuộc.
2. **Policy profile** có version, allowed-for-new-write, allowed-for-legacy-read và deny states.
3. **Envelope/message formats có version** và **metadata được xác thực**.
4. **Pluggable provider adapters** nhưng không cho caller chọn arbitrary thuật toán.
5. **Cơ chế rollout**: new-write cutover, compatibility window, batch migration, canary và rollback **không tái mở cấu hình yếu cho new writes**.
6. **KMS/HSM key custody** tách khỏi application-specific crypto; key lifecycle được kiểm soát.
7. **Audit/metric** theo algorithm suite, key version, operation, outcome và policy.
8. **Backup/DR tests** để chứng minh dữ liệu cũ/mới còn đọc được theo quyền được phê duyệt.

**Agility không đồng nghĩa để client gửi header `algorithm=anything` và ứng dụng tự chạy.** Algorithm negotiation phải dựa trên **allowlist đã được thiết lập từ phía tin cậy**, tránh **downgrade** hoặc algorithm-confusion attacks.

### 4.1. Profile phải bao gồm những gì?

~~~yaml
# Minh họa policy schema, không phải chuẩn của một KMS.
profileId: "billing-data-crypto-v2"
purpose: "BILLING_DATA_ENCRYPTION"
cryptographicDomain: "production"
newWrite:
  format: "envelope-v2"
  dataAlgorithm: "AES-256-GCM"
  noncePolicy: "unique-per-key"
  tagBits: 128
  keyOrigin: "approved-KMS"
legacyRead:
  allowedFormats:
    - "envelope-v1"
  requiresApproval: true
  boundedMigrationWindow: true
deny:
  newWriteFormats:
    - "envelope-v1"
  allowUntrustedAlgorithmSelection: false
audit:
  redactRawKeyMaterial: true
~~~

**Không phải mọi trường có thể enforce trong KMS.** Một số là trách nhiệm ứng dụng, KMS policy, repository/build gate hoặc công cụ kiểm tra dữ liệu. Cần kiểm tra hành vi runtime, không chỉ xem YAML.

### 4.2. Version của thuật toán khác version của key

| Trường | Ý nghĩa |
| --- | --- |
| **formatVersion** | Cách encode metadata, nonce, ciphertext, tag, AAD, wrapped DEK. |
| **algorithmSuiteId** | Tập thuật toán/mode/parameters được phép. |
| **keyId/keyVersion** | Key material cụ thể dùng để bảo vệ dữ liệu/chữ ký. |
| **kekRef / wrappingVersion** | KEK và sơ đồ wrap bảo vệ DEK. |
| **schemaVersion** | Cách diễn giải tenant/object/purpose và dữ liệu nghiệp vụ. |
| **policyVersion** | Quyết định cho phép/deny tại thời điểm dùng. |
| **revision** | Số phiên bản bản ghi để CAS/migration đồng thời. |

**Đừng dùng một trường `version=v2` mơ hồ cho tất cả.** Có thể đổi KEK mà giữ DEK và algorithm suite; có thể đổi algorithm suite và DEK cùng lúc; có thể re-sign artifact mà nội dung nghiệp vụ không đổi. Mỗi chiều tiến hóa có mục đích riêng.

## 5. Tìm mọi nơi đang dùng thuật toán yếu

Rotation khi thuật toán suy yếu chỉ hiệu quả nếu biết **key nào, dữ liệu nào, bên nhận nào và phiên bản nào** còn phụ thuộc.

### 5.1. Crypto inventory theo lớp

~~~text
Application / workflow
  |-- USES --> algorithm suite + parameters + library/provider
  |-- CALLS --> KMS/HSM key object/version + purpose/usage
  |-- CREATES --> DEK / session key / signing key / HMAC key
  |-- PRODUCES --> ciphertext / MAC / signature / certificate / token
  |-- CONSUMED_BY --> service / mobile client / partner / archive
  |-- BACKED_UP_IN --> snapshots / object storage / DR region
  |-- TRUSTED_BY --> PKI / JWKS / certificate chains / verifier rules
~~~

**Key inventory riêng lẻ không đủ nếu thiếu algorithm inventory**. Một key object có thể được dùng đúng quyền KMS nhưng ứng dụng vẫn dùng dữ liệu đầu ra trong một mode sai. Với private signing key, cần biết **hash/signature scheme**, không chỉ RSA/EC key type.

### 5.2. Những nguồn cần rà soát

- Source/config và các đường gọi crypto library **trong phạm vi được giao cho đội vận hành**.
- KMS/HSM key metadata: type, origin, key usage, state, version, policy và grants.
- Certificate inventory và public key trust: issuers, algorithms, validity, revocation.
- JWT/JWS signing profiles, JWKS `kid`, allowed algorithms và consumer caches.
- TLS terminators, client libraries, gateways, service mesh và cipher/protocol policy.
- Database ciphertext schemas, wrapped DEK, nonce/tag, AAD/encryption context.
- Password verifier schemes/work factors, MAC/HMAC implementations, PSK inventory.
- Object store, offline archive, backups, snapshots, migration queues, recovery regions.
- Third-party consumers, mobile apps, firmware hoặc long-lived clients có khả năng cập nhật chậm.
- Audit logs và release artifacts cần xác minh tính toàn vẹn lịch sử.

**Không cần export raw KEK/private key từ KMS chỉ để đoán đang dùng thuật toán nào.** Hãy dùng metadata có thẩm quyền, key registry, SDK contracts và logs đã phân loại.

### 5.3. Dependency graph để chọn đúng hành động

~~~mermaid
flowchart TD
    ALG["Data algorithm suite v1 suy yếu"] --> CT["Ciphertexts tạo bởi v1"]
    CT --> DEK["DEK-A / DEK-B"]
    DEK --> WRAP["Wrapped DEKs"]
    WRAP --> KEK["KEK production"]
    CT --> BACKUP["Archives, replicas, snapshots"]
    SIGN["Signature scheme v1 suy yếu"] --> ART["Signed events / artifacts"]
    ART --> VERIFY["Ledger, clients, partners"]
    VERIFY --> TRUST["PKI, JWKS, certificates"]
    ALG --> PLAN["Migrate data crypto format"]
    SIGN --> SIGNPLAN["Migrate signer + verifier policy"]
~~~

**Sai lầm thường gặp:** thấy KEK trong inventory rồi chỉ rotate KEK dù điểm yếu nằm ở **AES-ECB khi DEK mã hóa dữ liệu**. Khi đó re-wrap DEK dưới KEK mới không thay **ciphertext yếu**. Phải đặt đúng cạnh quan hệ **ENCRYPTS, WRAPS, SIGNS, VERIFIES** trong đồ thị để quyết định.

## 6. Xác định loại migration theo lớp bị suy yếu

| Lớp yếu | Thao tác chính | Việc không đủ |
| --- | --- | --- |
| **Data cipher/mode/parameters** | Tạo DEK phù hợp, giải mã theo đường legacy được phép, **re-encrypt dữ liệu** dưới AEAD/format mới. | Chỉ re-wrap cùng DEK hoặc đổi key ID. |
| **Key wrapping algorithm/KEK profile** | Re-wrap DEK bằng **wrap mechanism/KEK phù hợp**, đồng thời đánh giá DEK exposure. | Đổi alias KEK mà không cập nhật blob khi provider yêu cầu. |
| **Signature scheme/hash/key strength** | Tạo signing key/profile mới, công bố trust, chuyển Sign; xem khả năng re-sign/đánh giá chữ ký cũ. | Chỉ đổi `kid` hoặc thay public-key URL. |
| **MAC scheme/PSK** | Rotate secret và đổi MAC construction/profile, cập nhật tất cả bên sử dụng. | Chỉ đổi secret nhưng tiếp tục protocol lỗi. |
| **Password verifier/KDF** | Chuyển password hashing/KDF policy, rehash ở thời điểm có mật khẩu hợp lệ hoặc reset. | “Giải mã” password hash hoặc đổi salt trong metadata. |
| **TLS/transport key exchange** | Nâng giao thức/cipher policy, cập nhật endpoints/clients, vô hiệu hóa suite yếu. | Chỉ rotate certificate nhưng giữ protocol suite lỗi. |
| **PKI/certificate/trust** | Cấp lại chứng chỉ/signers và thay verifier acceptance theo policy. | Chỉ sửa server mà không cập nhật client trust. |
| **KMS/HSM implementation** | Patch/upgrade/replace provider, rotate affected keys nếu cần, kiểm attest/restore. | Chỉ cập nhật app dependency nếu key custody đã bị ảnh hưởng. |

Một hệ thống có thể cần **nhiều nhánh đồng thời**. Ví dụ một TLS certificate dùng key strength yếu và endpoint còn cho phép protocol cũ: cần **key/certificate transition** lẫn **protocol/cipher suite transition**.

### 6.1. Không suy “re-wrap” là “re-encrypt”

Trong envelope encryption:

~~~text
Data layer:
  C1 = Encrypt_Data(legacy-algorithm, DEK-A, plaintext)

Wrapping layer:
  W1 = Wrap(KEK-v1, DEK-A)

Sau chỉ đổi KEK:
  W2 = Wrap(KEK-v2, DEK-A)
  C1 vẫn dùng legacy algorithm + DEK-A

Sau đổi data cipher:
  DEK-B = GenerateFreshKey()
  C2 = AEAD_Encrypt(approved-algorithm, DEK-B, plaintext)
  W2-B = Wrap(approved-KEK, DEK-B)
~~~

Nếu **lớp wrapping** yếu, re-wrap có thể là trọng tâm; nếu **lớp data encryption** yếu, phải đổi **data ciphertext format/mode**. Nếu **DEK/KEK đã lộ**, cần đánh giá compromise độc lập vì các bản copy cũ có thể đã rời miền kiểm soát.

## 7. Runbook tổng quát cho rotation do thuật toán suy yếu

~~~mermaid
flowchart TD
    NOTICE["Phát hiện thuật toán/profile suy yếu"] --> TRIAGE["Threat analysis + security decision"]
    TRIAGE --> INV["Inventory key, algorithms, data, consumers, backups"]
    INV --> PROFILE["Phê duyệt replacement suite + key usage + trust"]
    PROFILE --> PREP["KMS/HSM new key, IAM, versioned format, DR"]
    PREP --> CANARY["Canary / compatibility tests / production read-path"]
    CANARY --> SWITCH["Chỉ tạo dữ liệu/chữ ký mới bằng suite mới"]
    SWITCH --> MIGRATE["Migration lịch sử theo loại: re-encrypt / re-wrap / re-sign"]
    MIGRATE --> VERIFY["Đối soát integrity, authenticity, versions và audit"]
    VERIFY --> LEFT{"Còn dependency cần legacy?"}
    LEFT -->|Có| RESTRICT["Giới hạn legacy read/verify có phê duyệt"]
    RESTRICT --> MIGRATE
    LEFT -->|Không| REVOKE["Retire legacy usage và thu hồi quyền"]
    REVOKE --> DESTROY["Key destruction/retention theo approval"]
~~~

### 7.1. Bước A – Quyết định và tạm khóa đường phát sinh mới

- Xác định chính xác **algorithm/profile, usage, key family và dữ liệu** có nguy cơ.
- Lập **threat assessment**: mức nghiêm trọng, đường tấn công, dữ liệu cần bảo mật lâu dài, thứ tự ưu tiên.
- Nếu điểm yếu cấp bách, **ngừng ngay các thao tác phát sinh ciphertext/chữ ký mới** bằng cấu hình đó theo quyết định có thẩm quyền.
- Đừng để cấu hình runtime `ALLOW_WEAK_ALGORITHM=true` trở thành bypass vĩnh viễn.
- Duy trì **read-only path tạm** khi cần phục hồi dữ liệu, nhưng phải scope, audit và có lịch sunset.
- Đặt **owner, approval ID, policy version và tiêu chí hoàn tất**.

**Không hủy private key/KEK cũ ngay** nếu cần giải mã dữ liệu lịch sử hoặc phục vụ điều tra. Việc thu hồi **quyền new-write** và hủy **vật liệu khóa** là hai bước khác nhau.

### 7.2. Bước B – Chọn replacement có cơ sở

Một replacement cần được đánh giá theo:

1. **Security strength** phù hợp lifetime của dữ liệu và threat model.
2. **Algorithm/mode/parameters** được chính sách, tiêu chuẩn và provider hỗ trợ.
3. **Nonce, IV, salt, tag, padding và context rules** đúng.
4. **Algorithm/key separation** giữa encrypt, wrap, sign, MAC và key agreement.
5. **KMS/HSM compatibility** với key type, usage, non-exportability và audit.
6. **Interoperability** với clients, DB schemas, certificates, consumers và archive.
7. **Migration/DR:** có thể đọc dữ liệu cũ, ghi dữ liệu mới và phục hồi từ backup.
8. **Performance/quota/latency** và tác động production.
9. **Deprecation plan** để loại bỏ đường cũ sau một thời hạn cụ thể.

**Đừng tự thiết kế thuật toán lai, padding hay KDF mới** chỉ để né giới hạn một SDK. Dùng **profile được đánh giá** và tài liệu/provider contract chính thức.

### 7.3. Bước C – Chuẩn bị key mới và format mới

- Tạo **DEK/KEK/signing key mới** khi loại migration yêu cầu.
- Gắn **key ID, cryptographic domain, usage, owner, policy/algorithm versions và successor/predecessor**.
- Cấu hình **workload identity/IAM** theo least privilege, không hard-code raw material.
- Thêm **format version** và schema AAD/encryption context có khả năng kiểm thử.
- Cập nhật **readers/verifiers trước hoặc đồng thời với writers** theo thứ tự bảo toàn khả năng tương thích.
- Tạo **test vectors và negative tests bằng dữ liệu/key thử**, không copy key production.
- Lập canary, metrics, rollback **không quay lại new writes yếu**.

### 7.4. Bước D – Cutover: new-write mới, legacy-read có thời hạn

Đối với mã hóa dữ liệu:

~~~text
Từ thời điểm cutover:
  Encrypt mới --> format v2 + approved AEAD + DEK v2
  Decrypt v2 --> policy v2 + AEAD verify
  Decrypt v1 --> legacy reader được giới hạn + migration path
  Encrypt v1 --> DENIED

Sau migration/sunset:
  Encrypt mới --> chỉ v2
  Decrypt v1 --> DENIED hoặc archive quarantine theo policy
~~~

Không tự động **“thử v2 thất bại thì thử v1 với mọi input”**. Fallback kiểu đó có thể trở thành **downgrade oracle**. Format cũ phải được nhận diện từ **metadata đáng tin và schema rõ ràng**, được cho phép bởi policy, không phải do client tự yêu cầu.

### 7.5. Bước E – Migrate và xác minh

- Migrate theo **batch nhỏ, checkpoint bền vững, giới hạn concurrency/quota**.
- Dùng **CAS/transaction** để tránh ghi đè record đã thay trong lúc worker xử lý.
- Verify **new AEAD tag, integrity và business invariants**, không chỉ kiểm mã hóa có output.
- Nếu legacy mode **không bảo đảm integrity**, phải tìm **bằng chứng độc lập** hoặc cách xác minh thích hợp; không mặc định plaintext sau Decrypt là đáng tin.
- Đối soát **live DB, archive, snapshots, backups, queues, replicas và caches**.
- Ghi event **operation/outcome/reasonCode/keyRef/algorithmVersion**, không log raw key/plaintext.
- Cập nhật status theo **thực tế dữ liệu đã migrate**, không chỉ worker đã chạy xong.

### 7.6. Bước F – Retire và destroy

- Dừng cấp phép tạo dữ liệu/chữ ký mới bằng algorithm legacy.
- Thu hồi temporary grants và quyền legacy usage không còn cần.
- Thông báo consumers, kiểm revoked/trust state và old-key read policy.
- Kiểm **DR restore** với key/format mới và phạm vi dữ liệu lịch sử.
- Chỉ hủy key material sau **dependency scan, retention/legal hold, approval** và xác minh recovery requirements.
- Ghi lại rủi ro lịch sử **không thể đảo ngược**, đặc biệt nếu ciphertext đã bị attacker thu thập trước khi migrate.

## 8. Dữ liệu at rest: cách chuyển từ cipher/mode yếu sang AEAD

Dữ liệu mã hóa at rest thường gồm **ciphertext, key reference, IV/nonce, tag, metadata/AAD và wrapped DEK**. Cần phân biệt:

- **Data encryption mode**: cách DEK bảo vệ plaintext.
- **Key wrapping scheme**: cách KEK bảo vệ DEK.
- **Transport**: cách bản ghi được di chuyển giữa các dịch vụ.
- **Trust/authorization**: principal nào có thể đọc/giải mã object.

### 8.1. Định dạng bản ghi có version

~~~yaml
# Mẫu minh họa; không chứa key hoặc dữ liệu thật.
formatVersion: "billing-envelope-v2"
securityDomain: "production"
tenantRef: "tenant-A"
objectRef: "invoice-123"
dataAlgorithmSuite: "AES-256-GCM"
dataKeyRef: "dek-invoice-123-v2"
wrapping:
  kekRef: "kms://production/billing/kek-v4"
  wrappingFormat: "provider-approved"
  wrappedDek: "<encoded-encrypted-data-key>"
nonce: "<encoded-96-bit-nonce>"
ciphertextWithTag: "<encoded-ciphertext-and-tag>"
recordRevision: 72
~~~

Một record v1 có thể có **format khác và không có tag**; đừng ép nó thành v2 bằng cách đổi `formatVersion` rồi giữ nguyên bytes ciphertext.

### 8.2. AAD phải ràng buộc đúng đối tượng

Ví dụ với AES-GCM:

~~~text
AAD:
  formatVersion  = billing-envelope-v2
  securityDomain = production
  tenant         = tenant-A
  object         = invoice-123
  purpose        = billing-invoice
  dataKeyRef     = dek-invoice-123-v2
~~~

**AAD là dữ liệu được xác thực nhưng không mã hóa**, không nên chứa secret/PII nhạy cảm nếu metadata sẽ đi vào logs. Trong một số KMS, **encryption context** còn xuất hiện trong provider audit.

**AAD/context không thay application authorization.** Nếu một service có quyền `DecryptDataKey` rộng, ứng dụng vẫn phải xác minh **user/workload có quyền truy cập đúng tenant/object**.

### 8.3. Khi legacy không có authentication tag

Một mode mã hóa legacy có thể không bảo đảm tính toàn vẹn của plaintext. Việc `Decrypt` trả về chuỗi có vẻ hợp lệ **không chứng minh dữ liệu chưa bị sửa**.

Hướng xử lý:

- Tìm **MAC/chữ ký độc lập** có nguồn gốc đáng tin, bản backup sạch hoặc checksum tham chiếu có bảo vệ.
- So sánh invariants nghiệp vụ, provenance và nguồn dữ liệu chuẩn nếu có.
- Đưa dữ liệu **không thể xác thực** vào **quarantine/manual review** hoặc một quy trình chấp nhận rủi ro có thẩm quyền.
- Không tự động ký lại hoặc gắn AEAD tag mới cho dữ liệu có thể đã bị attacker sửa rồi gọi đó là dữ liệu đáng tin.

**Re-encryption không hồi phục tính toàn vẹn lịch sử đã mất.** Nó bảo vệ plaintext **kể từ thời điểm mới**, không chứng minh quá khứ.

## 9. Đối với key wrapping và KMS/HSM

Nếu suy yếu xảy ra ở **sơ đồ bọc DEK** chứ không phải data cipher, có thể dùng **re-wrap DEK** để chuyển lớp bảo vệ.

### 9.1. Khi re-wrap là đúng lớp

~~~text
Dữ liệu:
  C = AES-GCM(DEK-A, plaintext, nonce, AAD)   // vẫn đáp ứng policy

Lớp bọc cũ:
  W1 = LegacyWrap(KEK-1, DEK-A)

Lớp bọc mới:
  W2 = ApprovedWrap(KEK-2, DEK-A)

Sau migration:
  C không đổi, DEK-A không đổi, wrapped DEK/KEK metadata đổi.
~~~

Phương án này hợp lý khi **data cipher/DEK còn an toàn** và migration nhắm đến **wrapping layer**. Nhưng cần đánh giá wrapped DEK cũ đã bị ai lấy, mức an toàn/integrity của legacy wrapping và khả năng DEK đã bị unwrap.

### 9.2. KMS-native rewrap ưu tiên khi hỗ trợ

Một số KMS/HSM cung cấp cơ chế re-encrypt/rewrap hoặc key transfer **bên trong miền bảo vệ**. Ưu điểm là worker không cần nhận raw DEK về RAM. Tuy nhiên **không phải provider nào cũng có cùng API, cross-region hoặc cross-account capability**.

Nếu provider không hỗ trợ, có thể phải dùng secure unwrap+wrap workflow trong ranh giới đã được phê duyệt, hoặc **re-encrypt data** theo thiết kế. Không xuất non-exportable KEK/private key thành plaintext chỉ để “làm cho migration chạy”.

### 9.3. Key origin và non-exportable

**KMS/HSM non-exportable** là chính sách bảo vệ vật liệu khóa, **không phải bằng chứng thuật toán được dùng với nó còn an toàn**. Một key được sinh/nhập với profile cũ có thể cần replacement ngay cả khi không bao giờ xuất raw key.

Khi tạo key mới phải kiểm:

- Source entropy/DRBG/CSPRNG và provenance.
- Key type, algorithm/usage/strength, provider compatibility.
- IAM key policy, grants, owner và separation of duties.
- Backup/recovery, import/BYOK và khả năng migrate ciphertext.
- Key version/alias history; không coi `current` là vật liệu bất biến.
- Audit Sign/Decrypt/Unwrap và quyền schedule deletion.

## 10. Chữ ký số và PKI khi scheme/hash suy yếu

Chữ ký số khác encryption. Dữ liệu có thể được ký bằng private key **không xuất khỏi HSM**, nhưng việc xác minh phụ thuộc **public-key binding, issuer, signature scheme/hash, timestamp và trust policy**.

### 10.1. Chuyển signer và verifier đúng thứ tự

~~~mermaid
sequenceDiagram
    participant Sec as Security/key owner
    participant KMS as KMS/HSM
    participant Signer as Payment Service
    participant Reg as PKI/JWKS/trust registry
    participant Verify as Ledger Service
    Sec->>KMS: Tạo signing key S2 và profile mới
    KMS-->>Reg: Public key/certificate qua approval
    Reg->>Verify: Phân phối trust mapping S2 có xác thực
    Verify->>Verify: Kiểm issuer/audience/algorithm/version
    Sec->>Signer: Chỉ Sign mới bằng S2/profile mới
    Signer->>Verify: Event có signature profile mới
    Verify->>Verify: Verify chữ ký + authorization + chống replay
~~~

Trình tự **publish/prepare verifiers trước cutover signer** giúp tránh làm hệ thống từ chối toàn bộ event hợp lệ. Nếu điểm yếu rất nghiêm trọng, có thể phải **ngừng ký hoặc từ chối profile cũ sớm hơn**, theo quyết định incident/security owner.

### 10.2. Re-sign dữ liệu lịch sử có nghĩa gì?

Có trường hợp **artifact, release manifest, contract, giao dịch hoặc log bằng chứng** đã được ký bằng profile cũ. Không thể đơn giản thay bytes signature trong bản ghi và giả vờ chữ ký mới tồn tại từ ngày ban đầu.

Phương án tùy giá trị pháp lý/nghiệp vụ:

1. **Giữ chữ ký gốc** như bằng chứng lịch sử, kèm provenance và trạng thái thuật toán tại thời điểm ký.
2. **Thêm chữ ký mới** trên **artifact/content được xác minh từ nguồn độc lập**, không tự ghi đè chữ ký cũ.
3. Dùng **trusted timestamp/evidence renewal** theo tiêu chuẩn và chính sách phù hợp nếu cần xác thực dài hạn.
4. Nếu không xác thực được nội dung gốc, **không “rửa” dữ liệu đã có thể bị sửa bằng chữ ký mới**.
5. Chuyển verifier trust/acceptance theo **issuer, audience, key usage, algorithm, key status và thời gian**.

**Verify toán học hợp lệ không tự chứng minh nghiệp vụ được phép**. Ledger vẫn phải kiểm replay/idempotency, event ID, tenant và policy ở thời điểm xử lý.

### 10.3. Hash collision khác hash preimage

Nếu một chữ ký số dùng hash có **collision resistance suy yếu**, rủi ro phụ thuộc khả năng tạo hai nội dung cho cùng digest và các điều kiện của sơ đồ chữ ký. Không nên tự kết luận mọi hash đều bị phá về mọi thuộc tính.

Nếu dữ liệu được ghi nhận chỉ bằng **hash không có authentication**, kẻ tấn công có thể thay cả dữ liệu lẫn hash khi kiểm soát storage. Chuyển sang SHA-2/SHA-3 có thể là một phần của giải pháp, nhưng vẫn cần **signed/MACed provenance hoặc nguồn tham chiếu tin cậy**.

### 10.4. PKI/certificate migration

Một profile ký yếu có thể liên quan:

- Chứng chỉ được phát hành dưới thuật toán/chữ ký cũ.
- Root/intermediate trust hoặc key strength cần thay.
- Public-key registry/JWKS và consumer caches.
- Signed releases và artifact verification.
- Revocation/CRL/OCSP theo mô hình triển khai.
- Chữ ký lịch sử cần timestamp/evidence và retention.

**Đổi certificate nhưng giữ private key hoặc scheme không còn đạt yêu cầu có thể chưa đủ**. Ngược lại, khi chỉ CA chain thay vì key material yếu, hướng migration có thể khác; cần phân biệt đúng tài sản bị ảnh hưởng.

## 11. HMAC, MAC, KDF và password storage

### 11.1. MAC scheme hoặc shared secret

Nếu một ứng dụng dùng MAC scheme không còn đáp ứng yêu cầu:

- Tạo **MAC key mới** với entropy và key usage phù hợp.
- Chuyển sang **MAC construction/profile** được chấp thuận, không chỉ đổi secret.
- Cập nhật cả producer và verifier; hạn chế acceptance của MAC cũ.
- Ghi **version/domain/purpose** vào metadata được xác thực.
- Xem xét các message/token đã được xác minh bởi profile cũ và chống replay.

**HMAC key không được tái sử dụng như AES key hoặc password pepper** chỉ vì cùng là secret dạng bytes.

### 11.2. Password hash không phải ciphertext

Mật khẩu thường phải được lưu bằng **password hashing/KDF chuyên dụng** với salt, work factor và chính sách phù hợp, không phải encrypt hoặc hash nhanh đơn giản.

Nếu password verifier scheme/work factor quá yếu:

- **Không thể giải mã password hash** để sinh hash mới, vì hash một chiều không lưu plaintext.
- Có thể **rehash khi người dùng đăng nhập thành công** và ứng dụng có mật khẩu rõ trong RAM tạm theo đường xác thực hợp lệ.
- Nếu cần thay ngay vì nguy cơ nghiêm trọng, có thể dùng **reset credentials/forced re-enrollment** theo chính sách.
- Thông tin về **salt, scheme, work factor và version** phải được lưu để xác minh/verifier update.
- Nếu pepper/credential bị lộ, đánh giá rotation và tác động như một sự cố secret riêng.

Các thuật toán như **Argon2id, scrypt hoặc PBKDF2** cần chọn theo môi trường, khả năng thư viện, profile bảo mật và work factor đã được phê duyệt. **Java 17 JCA không có triển khai Argon2id chuẩn trong thư viện nền**, nên không tự tuyên bố `SecretKeyFactory` nào đó hỗ trợ Argon2id nếu không có provider bổ sung.

### 11.3. KDF cho khóa phiên và key establishment

Khi thay key agreement/suite, cần cập nhật **KDF/key schedule, peer authentication, transcript binding và key confirmation** của giao thức tương ứng. Không tự tạo giải pháp bằng cách nối `sharedSecret + nonce` rồi hash và cho rằng đã thay TLS hoặc AKE được đánh giá.

## 12. TLS, session keys và giao thức khi bộ thuật toán bị loại bỏ

Một số rủi ro nằm ở **giao thức và đàm phán tham số**, không ở KMS key object.

### 12.1. Những thành phần cần xem cùng nhau

- TLS protocol versions và cipher suites/algorithm negotiation.
- Key exchange/authentication mechanisms và certificate identities.
- Session ticket/resumption policies và lifetime.
- Client compatibility, service mesh, reverse proxy, gateways và mobile clients.
- Server certificate key type/length, signature algorithm và validity.
- Peer identity verification, hostname validation và mTLS trust.
- Audit/telemetry của những kết nối vẫn dùng legacy profile.

**Không cho client tự chọn “weak fallback” để kết nối bằng mọi giá.** Việc hỗ trợ legacy protocol cần có **exception riêng, mốc kết thúc, segmentation và monitoring**, nếu policy cho phép. Một số trường hợp không được chấp nhận fallback dù ảnh hưởng availability.

### 12.2. Thay certificate không sửa cipher suite yếu

Nếu endpoint vẫn cho phép protocol/suite không được chấp thuận, việc tạo certificate mới **chưa loại bỏ đường đàm phán yếu**. Ngược lại, tắt suite nhưng không cập nhật các client hợp lệ có thể gây outage. Phải **khảo sát client inventory, rollout canary và kiểm thử negative negotiation**.

### 12.3. Forward secrecy và dữ liệu lịch sử

Một AKE có forward secrecy theo thiết kế có thể giới hạn hậu quả của **lộ long-term key ở thời điểm sau**, nhưng không cứu được **session key đã trực tiếp bị lộ** và không thay thế việc xác thực peer.

Nếu một traffic capture cũ đã được thu thập dưới bộ tham số yếu, nâng TLS hôm nay **không thể khiến ciphertext cũ đã bị đối thủ lưu lại trở nên an toàn hơn**. Đánh giá dữ liệu lịch sử phải tính đến khả năng **harvest-now-decrypt-later** với dữ liệu cần giữ bí mật dài hạn.

## 13. Yếu tố mật mã hậu lượng tử và kế hoạch dài hạn

Một lý do phải thiết kế crypto-agility là **khả năng thay đổi mô hình đe dọa**, bao gồm tiến bộ về tính toán lượng tử. Tác động khác nhau giữa các họ thuật toán:

- Các sơ đồ **public-key agreement/encryption và signature** dựa vào những bài toán toán học nhất định có rủi ro khác với symmetric encryption.
- **Dữ liệu có thời hạn bí mật dài** cần đánh giá nguy cơ đối thủ **thu thập ciphertext hôm nay, giải mã về sau**.
- **AES, hash, HMAC** và các primitive đối xứng không được đánh giá giống RSA/ECDH/EdDSA; không suy rằng mọi thuật toán đều “hỏng như nhau”.
- Các họ thuật toán như **ML-KEM** cho key establishment và **ML-DSA** cho chữ ký là những ví dụ cần được đánh giá trong kế hoạch nâng cấp phù hợp với tiêu chuẩn/hệ sinh thái áp dụng.
- **Hybrid key establishment**, certificate/trust distribution và algorithm negotiation phải theo **profile được đánh giá**, không tự ghép primitive bằng mã tự viết.

**Không nên tự tuyên bố một lịch bắt buộc chuyển hậu lượng tử áp dụng cho mọi tổ chức**. Phải theo policy, chuẩn và yêu cầu hiện hành được tổ chức áp dụng, cũng như khả năng provider và dữ liệu cần bảo vệ.

**Crypto-agility có giá trị ngay cả trước khi chuyển hậu lượng tử**: một hệ thống lưu rõ key usage, algorithm suite, format version, consumer inventory và migration path sẽ dễ đáp ứng nhiều loại cảnh báo hơn.

## 14. Java 17: điều phối chuyển ciphertext legacy sang AES-GCM mới

Ví dụ này minh họa **migration coordinator** chuyển một **record cũ có format không còn được phép dùng cho mã hóa mới** sang bản mã **AES-256-GCM với DEK mới do KMS cung cấp**.

Điểm bảo mật quan trọng:

- **Không viết lại hoặc mô phỏng thuật toán legacy yếu** trong demo. Giao diện `ApprovedLegacyReader` phải do hệ thống có quyền thực hiện, với một **bằng chứng integrity/provenance độc lập** nếu mode cũ không xác thực dữ liệu.
- **Không dùng raw key cố định**: `KmsDataKeyPort` cấp DEK dùng một lần và wrapped DEK dưới KEK mới theo provider.
- Chỉ nhận **format legacy cụ thể đã được policy duyệt**, không cho người gửi tự nhập tên thuật toán.
- Kiểm tra **trusted workload identity, tenant/object authorization và approved KMS key reference**.
- Mã hóa mới dùng **AES-GCM + nonce ngẫu nhiên 96 bit + AAD ổn định**, đồng thời dùng **CAS** cập nhật ciphertext, wrapped DEK, nonce/tag và format **nguyên tử**.
- Nếu không kiểm chứng được integrity/provenance của dữ liệu cũ, **quarantine**, không “mã hóa lại rồi coi dữ liệu đã sạch”.

**Giới hạn:** đây là Java 17 *khung điều phối có thể biên dịch*, không phải migration tool production. KMS adapter, legacy reader, authorization, DB store, evidence system và audit đều cần triển khai theo môi trường thật. Demo cố ý **không cung cấp đường decrypt weak algorithm** để tránh nhầm nó là cơ chế được khuyến nghị cho new operations.

~~~java
import java.io.ByteArrayOutputStream;
import java.io.DataOutputStream;
import java.nio.charset.StandardCharsets;
import java.security.SecureRandom;
import java.util.Arrays;
import java.util.Map;
import java.util.Objects;
import javax.crypto.Cipher;
import javax.crypto.spec.GCMParameterSpec;
import javax.crypto.spec.SecretKeySpec;

public final class WeakAlgorithmRotationCoordinator {
    private static final SecureRandom RANDOM = new SecureRandom();
    private static final String OLD_FORMAT = "billing-envelope-v1";
    private static final String NEW_FORMAT = "billing-envelope-v2";
    private static final String NEW_PURPOSE = "billing-invoice";
    private static final int DEK_BYTES = 32;   // AES-256
    private static final int NONCE_BYTES = 12; // 96-bit AES-GCM nonce
    private static final int TAG_BITS = 128;

    enum Result { MIGRATED, ALREADY_MODERN, CONFLICT }

    // Metadata của nguồn cũ được đọc từ kho đã xác thực.
    // Không cho external caller tự chọn thuật toán hay keyRef.
    record LegacyRecord(
            String recordId, String tenantRef, String securityDomain,
            String format, byte[] oldCiphertext,
            long revision) {}

    // LegacyReader chỉ được sử dụng trong migration window
    // và phải có đường kiểm tra integrity/provenance đã duyệt.
    record VerifiedLegacyPlaintext(
            byte[] bytes, boolean independentIntegrityVerified,
            String trustedEvidenceRef) {}

    interface ApprovedLegacyReader {
        VerifiedLegacyPlaintext readAndVerify(
                LegacyRecord record) throws Exception;
    }

    interface TrustedContext {
        // Trả danh tính workload được nền tảng xác thực,
        // không lấy từ HTTP header do người gọi tự đặt.
        String currentMigrationPrincipal();
        void requireMigrationPermission(
                String principal, String tenant, String recordId);
    }

    interface KeyRegistry {
        // Canonical/approved key reference cho production domain.
        String activeApprovedKek(String securityDomain);
        void requireAllowedDomainAndKey(
                String principal, String domain, String keyRef);
    }

    record DataKey(
            byte[] plaintextDek, byte[] wrappedDek,
            String effectiveKeyRef) {}

    interface KmsDataKeyPort {
        // Provider/KMS IAM bảo đảm origin, usage, policy;
        // adapter phải cấp DEK tươi cho mỗi lần encrypt.
        DataKey generateDataKey(
                String approvedKekRef, Map<String, String> context)
                throws Exception;
    }

    record ModernRecord(
            String recordId, String tenantRef, String securityDomain,
            String format, String dataAlgorithm, String kekRef,
            byte[] wrappedDek, byte[] nonce,
            byte[] ciphertextWithTag, long revision,
            String legacyEvidenceRef) {}

    interface Store {
        LegacyRecord load(String recordId);
        // Một transaction CAS: check record ID/tenant/domain/format/
        // old revision, sau đó thay tất cả metadata+ciphertext.
        boolean compareAndSwap(
                LegacyRecord observed, ModernRecord replacement);
    }

    private final TrustedContext context;
    private final KeyRegistry registry;
    private final KmsDataKeyPort kms;
    private final ApprovedLegacyReader legacyReader;
    private final Store store;

    public WeakAlgorithmRotationCoordinator(
            TrustedContext context, KeyRegistry registry,
            KmsDataKeyPort kms, ApprovedLegacyReader legacyReader,
            Store store) {
        this.context = Objects.requireNonNull(context);
        this.registry = Objects.requireNonNull(registry);
        this.kms = Objects.requireNonNull(kms);
        this.legacyReader = Objects.requireNonNull(legacyReader);
        this.store = Objects.requireNonNull(store);
    }

    private static byte[] aad(
            String domain, String tenant, String recordId)
            throws Exception {
        // Đóng gói xác định: từng field có prefix độ dài.
        ByteArrayOutputStream bytes = new ByteArrayOutputStream();
        DataOutputStream out = new DataOutputStream(bytes);
        for (String field : new String[] {
                NEW_FORMAT, domain, NEW_PURPOSE, tenant, recordId }) {
            byte[] value = field.getBytes(StandardCharsets.UTF_8);
            out.writeInt(value.length);
            out.write(value);
        }
        out.flush();
        return bytes.toByteArray();
    }

    private static Map<String, String> wrappingContext(
            String domain, String tenant, String recordId) {
        // KMS context thường KHÔNG phải dữ liệu bí mật;
        // không đưa plaintext hoặc PII nhạy cảm vào log/context.
        return Map.of(
                "domain", domain,
                "purpose", "billing-dek-wrap-v2",
                "tenant", tenant,
                "object", recordId);
    }

    public Result migrateOne(String trustedRecordId)
            throws Exception {
        String principal = context.currentMigrationPrincipal();
        if (principal == null || principal.isBlank()
                || trustedRecordId == null || trustedRecordId.isBlank()) {
            throw new SecurityException("Missing migration identity");
        }

        LegacyRecord row = store.load(trustedRecordId);
        if (row == null || row.format() == null
                || !trustedRecordId.equals(row.recordId())
                || row.tenantRef() == null || row.tenantRef().isBlank()
                || row.securityDomain() == null
                || row.securityDomain().isBlank()) {
            throw new SecurityException("Unknown record/format");
        }

        context.requireMigrationPermission(
                principal, row.tenantRef(), row.recordId());

        if (NEW_FORMAT.equals(row.format())) {
            return Result.ALREADY_MODERN;
        }
        if (!OLD_FORMAT.equals(row.format())
                || row.oldCiphertext() == null
                || row.oldCiphertext().length == 0) {
            throw new SecurityException("Unapproved legacy record");
        }

        String kekRef = registry.activeApprovedKek(
                row.securityDomain());
        if (kekRef == null || kekRef.isBlank()) {
            throw new SecurityException("No approved KEK");
        }
        registry.requireAllowedDomainAndKey(
                principal, row.securityDomain(), kekRef);

        // Legacy reader phải kiểm bằng chứng độc lập: chữ ký/MAC,
        // dữ liệu chuẩn hoặc nguồn integrity đã được phê duyệt.
        VerifiedLegacyPlaintext verified =
                legacyReader.readAndVerify(row);
        byte[] plaintext =
                verified == null ? null : verified.bytes();
        byte[] dek = null;
        try {
            if (plaintext == null
                    || !verified.independentIntegrityVerified()
                    || verified.trustedEvidenceRef() == null
                    || verified.trustedEvidenceRef().isBlank()) {
                throw new SecurityException(
                        "Unverified legacy data; quarantine");
            }

            DataKey generated = kms.generateDataKey(
                    kekRef, wrappingContext(
                            row.securityDomain(),
                            row.tenantRef(), row.recordId()));
            dek = generated == null ? null : generated.plaintextDek();

            if (dek == null || dek.length != DEK_BYTES
                    || generated.wrappedDek() == null
                    || generated.wrappedDek().length == 0
                    || !kekRef.equals(generated.effectiveKeyRef())) {
                throw new SecurityException("Invalid KMS data key");
            }

            // Giả định adapter sinh DEK mới mỗi lần migrate.
            byte[] nonce = new byte[NONCE_BYTES];
            RANDOM.nextBytes(nonce);
            Cipher cipher = Cipher.getInstance("AES/GCM/NoPadding");
            cipher.init(Cipher.ENCRYPT_MODE,
                    new SecretKeySpec(dek, "AES"),
                    new GCMParameterSpec(TAG_BITS, nonce));
            cipher.updateAAD(aad(
                    row.securityDomain(),
                    row.tenantRef(), row.recordId()));
            byte[] ciphertextWithTag = cipher.doFinal(plaintext);

            ModernRecord replacement = new ModernRecord(
                    row.recordId(), row.tenantRef(),
                    row.securityDomain(), NEW_FORMAT,
                    "AES-256-GCM", kekRef,
                    generated.wrappedDek().clone(),
                    nonce, ciphertextWithTag, row.revision() + 1,
                    verified.trustedEvidenceRef());

            // CAS thay tất cả trường liên quan cùng một transaction.
            boolean changed = store.compareAndSwap(row, replacement);
            return changed ? Result.MIGRATED : Result.CONFLICT;
        } finally {
            if (dek != null) Arrays.fill(dek, (byte) 0);
            // Chỉ xóa mảng plaintext nếu worker sở hữu nó.
            // Demo quy định legacyReader trả mảng riêng cho caller.
            if (plaintext != null) Arrays.fill(plaintext, (byte) 0);
        }
    }

    // Không có main hoặc fake KMS key cố định: việc triển khai
    // adapter phải dùng SDK KMS/HSM và policy đã phê duyệt.
}
~~~

### 14.1. Những điểm code cố ý kiểm tra

1. **Phân biệt format v1/v2:** không chọn thuật toán bằng giá trị bất kỳ do client gửi.
2. **Authorization trước crypto:** workflow phải có quyền trên tenant/record và domain.
3. **Legacy read được bao trong interface hạn chế:** không lan thuật toán yếu vào new-write path.
4. **Evidence bắt buộc:** nếu plaintext từ v1 không có bằng chứng integrity/provenance độc lập, migration **fail closed/quarantine**.
5. **Key mới từ KMS:** `generateDataKey` cung cấp DEK tạm và wrapped DEK, không hard-code raw key.
6. **KMS effective key ID phải đúng:** tránh cấp DEK dưới một KEK ngoài domain đã duyệt.
7. **AES-GCM mới:** nonce mới, tag 128 bit, AAD ràng buộc format/domain/tenant/record.
8. **CAS nguyên tử:** không để ciphertext v2 và wrapped DEK v1 hoặc ngược lại.
9. **Không log key/secret:** chỉ nên lưu metadata và event outcome ở audit implementation.
10. **Zeroization best-effort:** chỉ giảm thời gian giữ bytes trong mảng sở hữu; JVM/SDK có thể có bản sao khác.

### 14.2. Những điều phải bổ sung trước production

- `ApprovedLegacyReader` phải có **hợp đồng integrity thực sự**; nếu legacy ciphertext không có authenticated integrity, tìm independent trusted data provenance hoặc đường manual approval, **không đặt `independentIntegrityVerified=true` theo mặc định**.
- `Store` phải triển khai **transaction/CAS thật**, kiểm record ID, tenant, domain, format và revision; không dùng check-then-put trong hai thao tác riêng.
- `ModernRecord` và `DataKey` chứa `byte[]`, không tự deep immutable. Cần clone ở boundary và quản lý plaintext memory lifecycle.
- `KeyRegistry` phải xác minh **canonical KMS key/account/type/usage**, không tin alias hoặc tag tự khai.
- `TrustedContext` phải dựa trên platform identity/approval, không lấy từ user-supplied `ENV` hay HTTP header.
- Schema thật cần lưu đúng **key versions, algorithm parameters, nonce/tag, wrapped DEK format, AAD definition và provider encryption context**.
- Có thể cần **read-back verify bằng AES-GCM** từ dữ liệu vừa ghi và một đường đối soát byte-level được phê duyệt.
- Nếu `LegacyRecord` đã bị migrate bởi worker khác, `Store.load` có thể trả record v2; interface thực tế nên mô hình hóa **union type cho record versions** thay vì ép v2 vào `LegacyRecord`. Ở đây `ALREADY_MODERN` chỉ minh họa ý tưởng idempotency.
- Không có **rate limiting, retry/backoff, KMS quota, checkpoint, dead-letter queue, monitoring, DR drill, approvals hoặc dry-run**.
- Không có mã nguồn **legacy decrypt** hoặc khả năng sửa lỗi thuật toán cũ; đây là lựa chọn chủ động để không biến bài học thành hướng dẫn tiếp tục triển khai primitive yếu.

### 14.3. Nếu không còn đường xác minh legacy plaintext?

Một số thuật toán/mode yếu không cung cấp authentication. Nếu không có MAC/chữ ký đáng tin hoặc bản gốc có thể đối chiếu, **không nên âm thầm coi Decrypt thành công là integrity đã được xác minh**.

Có thể lựa chọn:

- Chuyển dữ liệu vào **quarantine** để đối chiếu thủ công hoặc với authoritative source.
- Phân loại nguồn dữ liệu theo rủi ro; có một **exception được phê duyệt** khi migration bắt buộc và chứng minh được giới hạn.
- Khi không có đủ bằng chứng, **ghi nhận tính không chắc chắn của dữ liệu lịch sử**; mã hóa lại không sửa được việc attacker có thể đã sửa dữ liệu trước đó.
- Nếu dữ liệu không cần giữ, xem xét retention/destruction theo quyền và legal hold thay vì migration bằng mọi giá.

## 15. Tính nguyên tử, idempotency và cạnh tranh khi migration

### 15.1. Vì sao cần CAS?

Giả sử worker đọc record v1 ở revision 12; trong lúc worker giải mã và mã hóa lại, một yêu cầu hợp lệ đã cập nhật nội dung object sang revision 13. Nếu worker ghi đè vô điều kiện, có thể **mất cập nhật** hoặc trả ciphertext chứa dữ liệu cũ nhưng metadata mới.

Cập nhật phải có điều kiện trên **record ID, tenant/domain, revision, format**:

~~~sql
-- Pseudocode SQL; tất cả tham số được bind, không nối chuỗi SQL.
UPDATE encrypted_object
SET format_version = :new_format,
    algorithm_suite = :new_algorithm,
    kek_ref = :new_kek_ref,
    wrapped_dek = :new_wrapped_dek,
    nonce = :new_nonce,
    ciphertext_with_tag = :new_ciphertext_with_tag,
    legacy_evidence_ref = :trusted_evidence_ref,
    revision = revision + 1
WHERE id = :record_id
  AND tenant_ref = :trusted_tenant_ref
  AND cryptographic_domain = :trusted_domain
  AND format_version = :expected_old_format
  AND revision = :expected_revision;
~~~

Nếu số hàng cập nhật **bằng 0**, phải **đọc lại** và xác định record đã được migrate, bị sửa hay bị xóa. Không retry mù với một kết quả mã hóa cũ.

### 15.2. Không có transaction chung giữa KMS và DB

KMS GenerateDataKey có thể thành công nhưng ghi DB fail. Worker có thể tạo một DEK/blob mới ở lần retry theo policy, miễn là **không ghi bản cập nhật không nhất quán**.

Do đó cần:

- **Idempotency key/checkpoint** cho từng record và migration plan.
- Đường retry phân biệt **KMS timeout/throttling**, **AccessDenied**, **invalid context**, **legacy integrity failure** và **DB CAS conflict**.
- Không log raw DEK, plaintext hoặc wrapped key blob khi dead-letter.
- Giới hạn concurrency và khả năng đọc dữ liệu online.
- Cơ chế **pause/resume/abort** mà không mở lại new writes yếu.

### 15.3. Dual-read có điều kiện, không phải downgrade

**Dual-read** là reader có thể hiểu **định dạng v1 và v2**, nhưng lựa chọn dựa trên **trusted record format + policy**. Nó không có nghĩa application sẽ thử mọi thuật toán cho tới khi ra plaintext.

**Single-write v2** là nguyên tắc an toàn: sau cutover, mọi writer phải tạo **ciphertext v2**, kể cả khi record đầu vào là v1 và reader có legacy support.

**Không đặt `legacy-read` vĩnh viễn**. Cần sunset date, exception owner và giám sát số lượt đọc v1 còn lại.

## 16. Backup, DR, cryptoperiod và việc hủy key cũ

Đổi thuật toán có thể tạo tình huống:

- Live DB đã dùng v2, nhưng **snapshot cũ chứa v1 ciphertext**.
- Key rotation đã chuyển KEK, nhưng backup chỉ có wrapped DEK dưới KEK cũ.
- DR region có data snapshot mới nhưng thiếu KMS material/key object tương ứng.
- Verifier production đã ngừng tin chữ ký v1, trong khi artifact archive cần xác minh sự kiện lịch sử.
- HSM backup/imported key material có policy phục hồi khác khóa provider-generated.

### 16.1. Bốn câu hỏi trước khi retire

1. **Dữ liệu nào còn cần thuật toán/key v1 để đọc?** Gồm archive, cold storage, backup, queues, caches và replica.
2. **Có thể migration những bản đó không?** Nếu không, có một **legacy decrypt service cô lập, theo hạn và phê duyệt** không?
3. **RPO/RTO còn đáp ứng không?** Khôi phục có đầy đủ key versions, nonce/tag, AAD/context và trust state mới không?
4. **Destroy có gây mất dữ liệu không thể đảo ngược?** Quyết định có được data/security owner phê duyệt và ghi bằng chứng không?

### 16.2. Restore drill phải kiểm dữ liệu, không chỉ key tồn tại

Một test chỉ xác nhận KMS `DescribeKey` trả `ENABLED` **không chứng minh bản mã có thể giải mã và xác thực**.

Cần dùng dữ liệu đại diện được phép:

- Restore snapshot v1 và v2 theo từng điểm.
- Kiểm reader/verifier nhận đúng format/profile và trạng thái key.
- Giải mã dữ liệu với quyền hợp lệ, xác minh AEAD tag và business invariants.
- Kiểm current revocation/algorithm policy không bị **rollback từ snapshot cũ**.
- Thu hồi các quyền KMS/DR tạm và ghi audit.

**Replication không tự thay backup độc lập** nếu xóa nhầm, compromise hoặc policy sai được nhân sang replica.

### 16.3. Crypto-shredding khác migration

**Crypto-shredding** nhằm làm dữ liệu mã hóa **không còn đường giải mã** bằng cách loại bỏ vật liệu khóa cần thiết trong phạm vi kiểm soát. Migration nhằm **tiếp tục đọc dữ liệu bằng profile an toàn hơn**.

**Không thể gọi migration thành công là crypto-shredding** nếu bản sao DEK/KEK cũ còn ở HSM backup, logs hoặc ngoài tổ chức. Cũng không nên destroy key cũ khi backup còn cần đọc theo retention.

## 17. IAM, KMS policy, phân tách trách nhiệm và audit

### 17.1. Ai có quyền làm gì?

| Vai trò | Nên được phép | Không nên có mặc định |
| --- | --- | --- |
| **Application writer** | Encrypt/Sign mới bằng profile/key active được duyệt. | Ghi bằng algorithm legacy sau cutover, chỉnh policy. |
| **Legacy migration reader** | Decrypt v1 trong scope đã phê duyệt, ngắn hạn. | Export KEK, Sign tuỳ ý, đọc mọi tenant. |
| **KMS/HSM operator** | Quản lý key lifecycle/backup theo approved plan. | Truy cập plaintext nghiệp vụ không cần thiết. |
| **Security/crypto owner** | Phê duyệt replacement, exception, sunset và incident response. | Tự bypass audit/quorum. |
| **Data owner** | Phân loại dữ liệu, retention, migration order và ngoại lệ. | Tự chọn thuật toán ngoài security policy. |
| **SRE/DR** | Canary, metrics, restore test và rollback ứng dụng đúng quy định. | Tự re-enable primitive đã bị cấm. |
| **Auditor/SOC** | Đọc evidence và policy history đã phân quyền. | Raw DEK, private key, recovery shares. |

**Break-glass** phải được giới hạn theo key refs, operations, domain, TTL, approvals và audit; không tạo tài khoản `kms:*` vô hạn chỉ để “chạy migration cho nhanh”.

### 17.2. Mẫu audit không chứa key

~~~json
{
  "eventType": "CRYPTO_ALGORITHM_MIGRATION",
  "service": "billing-service",
  "cryptographicDomain": "production",
  "recordRef": "opaque-invoice-ref",
  "sourceFormat": "billing-envelope-v1",
  "targetFormat": "billing-envelope-v2",
  "sourceAlgorithmSuiteRef": "legacy-data-profile",
  "targetAlgorithmSuiteRef": "AES-256-GCM",
  "targetKekRef": "billing-kek-v4",
  "operation": "MIGRATE_ENCRYPTED_RECORD",
  "outcome": "MIGRATED",
  "policyVersion": "crypto-policy-v7",
  "approvalRef": "approved-change-ref",
  "correlationId": "opaque-request-id"
}
~~~

**Không log** plaintext, raw DEK/KEK, signing private key, seed, token, HSM recovery shares hoặc KMS response nguyên khối. Algorithm/key references và tenant IDs cũng là metadata cần kiểm soát quyền truy cập.

### 17.3. Những chỉ số cần theo dõi

- Số **new writes** còn dùng algorithm suite cũ **sau cutover**: mục tiêu là không còn.
- Tỷ lệ record/ciphertext theo v1/v2, bao gồm archive và backups.
- Số lượt **legacy Decrypt/Verify** theo principal, key ID và policy exception.
- Migration success, quarantine, DB CAS conflict, invalid tag và independent provenance failures.
- KMS quota/throttling/AccessDenied và key policy changes.
- Verifier nào còn chấp nhận chữ ký/thuật toán bị retire ngoài policy.
- Số client/TLS sessions còn đàm phán legacy suites.
- Restore drill RPO/RTO và key version coverage.
- Phần trăm old-key dependencies đã được loại bỏ có bằng chứng.
- Các lần **algorithm downgrade** bị chặn ở gateway và data reader.

Một report “100% jobs processed” không bằng “100% data migrated” nếu có **quarantine, snapshot chưa scan hoặc consumer chưa nâng cấp**.

## 18. Những trường hợp khó và cách xử lý

### 18.1. Không có plaintext gốc hoặc legacy key

Nếu mất key cần giải mã v1, **tạo key v2 mới không thể tự giải mã ciphertext v1**. Chỉ có thể dùng recovery/backup hợp lệ hoặc chấp nhận mất khả năng truy cập theo quyết định data owner.

Nếu còn key nhưng ciphertext legacy không thể xác minh, cần **provenance check/quarantine**, không tự đổi metadata để hợp thức hóa.

### 18.2. Third-party client không nâng cấp kịp

Một partner/mobile client có thể chỉ hiểu suite v1:

- Phân loại dữ liệu/giao thức có thể bị ảnh hưởng.
- Cung cấp **compatibility plan** nếu security policy cho phép, với segmentation và thời hạn.
- Thông báo sunset, triển khai phiên bản mới, đo adoption.
- Không cho bất kỳ client nào **downgrade toàn bộ hệ thống** chỉ vì hỗ trợ legacy.
- Nếu không thể tương thích an toàn, **từ chối kết nối/operation cũ** theo quyết định có thẩm quyền.

### 18.3. Key rotation và algorithm migration đồng thời

Có thể cần thay **data suite, DEK, KEK, certificate/signing key và format** trong cùng chương trình. Rủi ro là **không thể xác định lớp nào gây lỗi**.

Thiết kế theo **các mốc kiểm chứng độc lập**, ví dụ:

1. Chuẩn bị read v1/v2 và metadata schema.
2. Tạo KMS KEK/DEK mới cho v2 và key usage policy.
3. Canary new-write v2; verify read v2.
4. Migrate một batch nhỏ từ v1, đối soát integrity và performance.
5. Tăng phạm vi migration, tách lỗi KMS/DB/format/legacy integrity.
6. Tắt new-write v1; kết thúc legacy-read khi data/DR cho phép.
7. Retire/hủy key cũ theo dependency/retention.

**Đừng đổi quá nhiều lớp cùng lúc mà không có rollback/diagnostic**. Nhưng nếu primitive có rủi ro khẩn cấp, phải ưu tiên containment và chấp nhận thay đổi nhanh theo quyết định sự cố.

### 18.4. Không đồng bộ algorithm policy giữa signer và verifier

Signer chuyển S2 nhưng verifier còn cho phép algorithm yếu do cache. Hoặc verifier đã cấm S1 trước khi client có S2 và gây outage.

Giải pháp:

- Dùng **signed/trusted key metadata** với issuer, audience, algorithm, version, validity/revocation.
- Rollout verifier readiness trước new Sign khi mức rủi ro cho phép.
- Theo dõi chữ ký yếu còn được chấp nhận, không chỉ số lần Sign.
- Audit trust updates và chống rollback.
- Phân biệt **Verify lịch sử** có điều kiện với **chấp nhận giao dịch mới**.

### 18.5. Thay key trong HSM nhưng không đổi protocol

Một HSM có thể bảo vệ RSA key rất tốt, nhưng ứng dụng vẫn có thể dùng một **padding scheme hoặc signature profile** không được chấp thuận. KMS/HSM custody **không thay validation của thuật toán và context**.

Ngược lại, một cipher mode mới mạnh cũng không an toàn nếu private signing key hoặc KEK bị export ra log/build artifact. Migration phải xem **toàn bộ chuỗi kiểm soát**.

## 19. Tình huống thực tế: Billing, Payment và Ledger

Giả sử nền tảng có:

- **Billing Service:** lưu invoice ciphertext với envelope encryption.
- **Payment Service:** ký event thanh toán và release artifacts.
- **Ledger Service:** Verify chữ ký và ghi sổ theo quyền, chống replay.

### 19.1. Billing: từ format mã hóa cũ sang AEAD v2

Trước khi đổi:

~~~text
format-v1:
  Ciphertext: legacy-mode( DEK-A, invoice )
  Wrapped DEK-A: dưới KEK-v3
  Metadata: thiếu authenticated AAD hoặc verification evidence

format-v2:
  Ciphertext + tag: AES-256-GCM( DEK-B, invoice, nonce, AAD )
  Wrapped DEK-B: dưới KEK-v4
  Metadata: format, suite, keyRef/version, domain, tenant, object
~~~

**Bài toán chính không phải KEK-v3 “hết hạn”**, mà là **data cipher/profile v1 không còn đáp ứng policy**. Chỉ re-wrap DEK-A dưới KEK-v4 không đủ. Billing cần:

1. Chặn v1 new writes.
2. Bảo đảm v2 readers và registry được triển khai.
3. Đọc v1 qua reader hạn chế; xác minh provenance dữ liệu cũ.
4. Tạo DEK-B, AES-GCM encrypt với AAD v2 và metadata mới.
5. CAS cập nhật record, kiểm tag/consistency.
6. Đối soát backups/archives; chỉ retire legacy key khi không còn dependency hợp lệ.

Nếu dữ liệu v1 đã bị attacker đọc trước migration, **chuyển sang v2 không thu hồi thông tin đã lộ**.

### 19.2. Payment: thay profile chữ ký cũ

Payment dùng một signature profile cũ không còn được phê duyệt. Việc cần làm:

1. Tạo **signing key S2** trong KMS/HSM với scheme được duyệt.
2. Đăng ký trusted public key/certificate S2 cùng issuer, audience, key usage và version.
3. Đảm bảo Ledger/partners có khả năng Verify profile mới.
4. Chuyển new Sign sang S2, theo dõi những event còn ký bằng profile cũ.
5. Đánh giá signed artifacts lịch sử với provenance và policy thời gian, xem có cần re-sign/evidence renewal.
6. Thu hồi quyền Sign bằng S1 và xử lý verifier trust phù hợp.

**Chữ ký mới trên event không được tự tuyên bố rằng event đó đã được ký bằng thuật toán mới từ thời điểm trước migration.** Giữ history và evidence đúng.

### 19.3. Ledger: Verify không chỉ là toán học

Ledger phải kiểm tra:

- Key từ **trusted issuer/registry** đúng.
- Signature scheme/algorithm thuộc **allowlist hiện tại**.
- `kid`, key usage, issuer, audience, tenant, cryptographic domain và status.
- Signature bytes trên canonical event đúng.
- Event ID, authorization và replay/idempotency.
- Chính sách riêng với historical events và valid timestamps khi thuật toán cũ không còn an toàn.

Một `Verify=true` trên public key bất kỳ attacker cung cấp **không chứng minh Payment Service là bên ký**.

### 19.4. Cùng một chương trình, ba đối tượng migration

| Dịch vụ | Điểm yếu | Công việc thực sự |
| --- | --- | --- |
| **Billing** | Data cipher/profile cũ. | Data re-encryption, DEK successor và envelope schema. |
| **Payment** | Signature/hash/key profile cũ. | New signing key/algorithm, public trust distribution và legacy signature policy. |
| **Ledger** | Verifier còn tin profile cũ ngoài chính sách. | Trust/verification rule migration và audit historical acceptance. |

**Một chương trình “rotate all keys” không đủ mô tả** các công việc trên. Phải phân theo **thao tác, nguyên nhân, đối tượng và bằng chứng nghiệm thu**.

## 20. Sai lầm thường gặp

| Sai lầm | Hậu quả | Cách phòng ngừa |
| --- | --- | --- |
| Sinh khóa mới nhưng vẫn dùng mode yếu. | Vẫn gặp cùng lớp tấn công. | Đổi algorithm suite, format và kiểm implementation. |
| Re-wrap DEK khi điểm yếu ở data cipher. | Ciphertext yếu không thay đổi. | Re-encrypt dữ liệu bằng data algorithm/DEK mới. |
| Đổi tên `algorithm=v2` trong metadata. | Reader dùng sai bytes/parameters, integrity fail. | Chuyển ciphertext/schema thực sự, verify. |
| Coi mọi SHA-1 use case giống nhau. | Kết luận thiếu căn cứ hoặc bỏ sót mục đích quan trọng. | Đánh giá security property và purpose cụ thể. |
| Coi AES-GCM nonce reuse là lỗi của AES key size. | Không sửa nonce generation, tiếp tục có rủi ro. | Nonce uniqueness, key usage budgets và DEK rotation. |
| Giữ `Encrypt(v1)` như fallback vĩnh viễn. | Downgrade và technical debt kéo dài. | Single-write mới, legacy read có hạn và giám sát. |
| Thử mọi thuật toán khi Decrypt fail. | Downgrade oracle và giải mã sai ngữ cảnh. | Format/version đáng tin, allowlist và fail closed. |
| Không xác minh legacy plaintext. | Re-encrypt dữ liệu có thể đã bị sửa rồi coi là sạch. | Independent provenance, manual review/quarantine. |
| Chỉ đổi key, không đổi verifier/clients. | Chữ ký mới bị từ chối hoặc chữ ký yếu vẫn được tin. | Publish-before-switch và trust policy rollout. |
| Re-sign artifact bị sửa nhưng coi là bản gốc. | “Rửa” provenance giả và đánh lừa audit. | Nguồn nội dung đáng tin, ký thêm, giữ evidence. |
| Thay certificate nhưng vẫn cho TLS suite yếu. | Đường protocol cũ vẫn tồn tại. | Protocol/cipher negotiation tests và deprecation. |
| Đổi password hash bằng cách đổi salt trên metadata. | Password verifier trở nên sai, chưa tăng bảo mật. | Rehash khi có password hợp lệ hoặc reset. |
| Coi KMS non-exportable là đủ. | HSM vẫn có thể thực hiện scheme yếu hoặc rights bị lạm dụng. | Algorithm policy + IAM + crypto usage review. |
| Không lưu key/algorithm versions. | Không thể giải mã/verify lịch sử đáng tin. | Registry + format version + key lineage. |
| Gắn alias current trực tiếp vào AAD dễ thay. | Rotation làm tag AES-GCM fail. | Stable AAD và migration format đúng. |
| Cấp admin KMS cho migration worker. | Đường leo thang/Export/Destroy ngoài scope. | Least privilege, JIT và separation of duties. |
| Log KMS response để debug. | Plaintext DEK/credential rò qua observability. | Typed allowlist audit, no-secret logging. |
| Không dùng CAS khi migrate online. | Lệch ciphertext/wrapped DEK hoặc mất cập nhật. | Atomic update, revision, idempotency. |
| Không tính snapshot/archive/DR. | Hủy key cũ làm dữ liệu lịch sử không đọc được. | Dependency graph và restore drill. |
| Chỉ xem “100% jobs done”. | Bỏ qua failed/quarantined records hoặc dữ liệu ngoài live DB. | Reconcile theo inventory và coverage. |
| Coi rotation xóa được dữ liệu attacker từng đọc. | Đánh giá sai residual risk. | Phân tích history và khả năng đã bị lộ. |
| Chuyển thuật toán mới bằng thư viện chưa được kiểm tra. | Lỗi crypto khác, interop hoặc downtime. | Approved providers, test vectors, canary/rollback. |
| Kết luận một profile chuẩn ở mọi năm/đơn vị. | Sai tuân thủ hoặc quá hạn chuyển đổi. | Đối chiếu tiêu chuẩn/policy áp dụng tại thời điểm triển khai. |

## 21. Checklist trước khi tuyên bố rotation hoàn tất

1. **Trigger:** đã xác định thuật toán/profile nào suy yếu, vì sao và theo bằng chứng nào chưa?
2. **Scope:** cryptographic operation, key families, material versions và data inventory đã đủ chưa?
3. **Threat:** ảnh hưởng confidentiality/integrity/authenticity và dữ liệu lịch sử được phân tích chưa?
4. **Cryptoperiod:** đã tách new-write originator period và legacy-read recipient period chưa?
5. **Replacement:** suite/parameters/key length/mode được policy và provider chấp thuận chưa?
6. **Key origin:** key mới được sinh bằng CSPRNG/KMS/HSM phù hợp, đúng domain/usage và provenance chưa?
7. **IAM:** worker, application và KMS grants được giới hạn resource/operation/tenant chưa?
8. **Data format:** đã có version, authenticated metadata, nonce/tag, AAD và key reference đúng chưa?
9. **Binding:** algorithm và key ID được chọn từ trusted policy chứ không phải client string chưa?
10. **New-write cutover:** mọi writer đã dừng tạo ciphertext/chữ ký theo profile cũ chưa?
11. **Migration type:** biết cần **re-encrypt, re-wrap, re-sign, rehash hay protocol migration** chưa?
12. **Legacy integrity:** dữ liệu cũ có thể xác minh nguồn/provenance độc lập trước re-encrypt không?
13. **Concurrency:** có CAS/idempotency, error classification và checkpoint bền vững chưa?
14. **Verifier readiness:** clients/partners, PKI/JWKS và trust policy đã hỗ trợ profile mới chưa?
15. **Historical evidence:** chữ ký/artifact cũ có policy thời gian, timestamp/provenance và retention chưa?
16. **Password storage:** work factor/salt/KDF được chuyển bằng login/reset đúng, không “decrypt hash” chưa?
17. **TLS:** đã tắt suite/protocol yếu và kiểm client negotiation không fallback chưa?
18. **Operations:** migration latency, quotas, error budget và quan sát new writes yếu đã được giám sát chưa?
19. **Inventory coverage:** live, replicas, archives, snapshots, queues và backups đã được scan chưa?
20. **DR:** restore drill với key/algorithm versions cũ/mới và current revocation đã PASS chưa?
21. **No secrets in logs:** không ghi raw DEK/KEK/private key, token, seed, plaintext vào log/tracing/CI chưa?
22. **Retirement:** quyền legacy new-use đã revoke, read-only exceptions còn hạn và approvals chưa?
23. **Destruction:** mọi dependency đã được đánh giá trước hủy khóa cũ chưa?
24. **Residual risk:** dữ liệu/chữ ký có thể đã bị attacker khai thác trước cutover được ghi nhận chưa?
25. **Postmortem:** quy trình crypto-agility, inventory và phát hiện algorithm downgrade đã được cải thiện chưa?

## 22. Câu hỏi tự kiểm tra

1. **Rotation khi thuật toán suy yếu** khác **rotation định kỳ** và **key compromise** như thế nào?
2. Vì sao sinh một AES key mới nhưng tiếp tục dùng ECB không giải quyết được vấn đề?
3. **Cryptoperiod originator usage** khác **recipient usage** ra sao?
4. Khi nào cần **re-wrap DEK** và khi nào phải **re-encrypt ciphertext**?
5. Vì sao re-wrap cùng DEK không cứu được dữ liệu đã mã hóa dưới mode yếu?
6. Nếu raw DEK đã lộ nhưng thuật toán còn mạnh, điểm gì thay đổi trong kế hoạch?
7. Tại sao phải lưu riêng `algorithmSuiteId`, `formatVersion` và `keyVersion`?
8. Vì sao một verifier không nên thử mọi signature algorithm do token tự khai?
9. Một chữ ký lịch sử Verify được về toán học có đủ chứng minh sự kiện hiện tại đáng tin không?
10. Khi re-sign artifact, vì sao cần bảo toàn bằng chứng về bản gốc thay vì ghi đè chữ ký cũ?
11. Những điều kiện nào khiến một hash có collision risk ảnh hưởng chữ ký nhưng không thể suy rộng sang mọi ứng dụng hash?
12. Password hash yếu có thể nâng cấp bằng cách “giải mã hash” không?
13. Nếu KMS/HSM giữ private key non-exportable, điểm yếu của signature profile có tự biến mất không?
14. Vì sao TLS cipher suite migration không thể hoàn tất chỉ bằng việc cấp lại certificate?
15. **Forward secrecy** giúp gì và có cứu được session key đã trực tiếp bị lộ không?
16. Vì sao phải kiểm **independent integrity** trước khi re-encrypt dữ liệu legacy không có authentication tag?
17. Nếu KMS GenerateDataKey thành công nhưng DB CAS fail, có thể retry an toàn bằng cách nào?
18. Vì sao `legacy-read` phải có hạn và audit chứ không nên giữ vĩnh viễn?
19. Tại sao production-DR có thể cần key versions cũ ngay cả khi live DB đã dùng suite mới?
20. Khi chưa còn bản backup/key v1 để đọc data, tạo key v2 có khắc phục được không?
21. Một hệ thống muốn chuẩn bị cho migration hậu lượng tử cần những metadata/đường quản trị nào?
22. Khi Billing đổi data cipher, Payment đổi signature scheme và Ledger đổi verifier, tại sao không thể chỉ chạy “rotate all keys”?
23. Điều kiện nào cho thấy migration đã bao phủ cả **archive, snapshots và consumers**, không chỉ live DB?
24. Khi nào có thể destroy legacy key mà không phá khả năng khôi phục và retention?
25. Những metadata audit nào đủ điều tra nhưng không làm lộ secret?
26. Tại sao migration không thể thu hồi thông tin đã bị attacker lấy trước thời điểm cutover?

**Ghi nhớ:** **Rotation khi thuật toán suy yếu** đòi hỏi **nhận diện chính xác thuật toán/mode/giao thức hoặc tham số không còn phù hợp**, quyết định dựa trên threat model và **chuyển đúng lớp mật mã**: **re-encrypt dữ liệu** khi data cipher yếu; **re-wrap DEK** khi wrapping scheme/KEK cần thay và DEK còn an toàn; **re-sign/cập nhật trust** khi signature profile yếu; **rehash/reset** khi password verifier không đủ mạnh; hoặc **nâng protocol suite** khi TLS/AKE cần đổi. Thiết kế có **key inventory, versioned format, KMS/HSM custody, least-privilege IAM, cryptoperiod riêng cho new use và legacy read, CAS/idempotency, audit, backup/DR và sunset policy** mới giúp thay thuật toán mà không đánh mất dữ liệu hay để lại đường downgrade. Rotation **bảo vệ tốt hơn trong tương lai**, nhưng **không tự xóa được hậu quả của ciphertext/chữ ký đã bị tấn công trong quá khứ**.
