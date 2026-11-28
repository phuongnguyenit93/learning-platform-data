# Kiểm tra key sau generation: xác minh khóa mật mã trước khi đưa vào sử dụng

## 1. Một khóa được tạo thành công đã đủ an toàn chưa?

Giả sử một dịch vụ Java yêu cầu KMS tạo **AES-256 key** để bảo vệ dữ liệu thanh toán. API trả về mã định danh và trạng thái thành công. Nhóm vận hành lập tức đưa key vào production. Sau đó mới phát hiện:

- Key được sinh trong **tài khoản hoặc region thử nghiệm**, không phải môi trường production dự kiến.
- Key có thuộc tính **exportable** dù chính sách yêu cầu không xuất được vật liệu khóa.
- Key được tạo cho **Encrypt/Decrypt**, nhưng ứng dụng cần một **KEK dùng Wrap/Unwrap** với semantics khác.
- Nhóm service account được cấp **Decrypt** rộng hơn quyền nghiệp vụ.
- Private signing key được sinh đúng thuật toán, nhưng public verification key đã lưu không tương ứng.
- Khóa bị trùng **key ID/alias** trong registry, khiến ứng dụng chọn một key cũ.
- Một bản backup chưa được kiểm tra có thể làm mất khả năng khôi phục ciphertext về sau.

Như vậy, **generation thành công không đồng nghĩa khóa đã sẵn sàng được sử dụng**.

**Kiểm tra key sau generation (post-generation key validation)** là chuỗi bước xác minh khóa vừa được sinh có **đúng loại, đúng tham số, đúng mục đích, đúng ranh giới quản lý, hoạt động mật mã nhất quán và có cấu hình vòng đời/kiểm soát truy cập** trước khi kích hoạt cho nghiệp vụ.

Điểm quan trọng:

> Một phép thử Encrypt/Decrypt hoặc Sign/Verify thành công chỉ chứng minh **một số tính chất chức năng**, không tự chứng minh **khóa có entropy đủ tốt, được tạo trong HSM đúng cấu hình, không bị sao chép, non-exportable thật hoặc an toàn trước mọi kiểu tấn công**.

Trong module **SECURITY_KEY_MANAGEMENT_FUNDAMENTALS**, bài này nằm ở chương **Key generation**, nối khâu sinh khóa với **key inventory, phân quyền, KMS/HSM, envelope encryption, cryptoperiod, rotation, revocation, destruction và audit**.

### Mục tiêu học tập

Sau bài này, bạn có thể:

1. Phân biệt **generation success, structural validation, functional validation và operational acceptance**.
2. Xây dựng checklist kiểm tra một khóa mới theo **key type, algorithm, size, curve, usage, exportability, state và purpose**.
3. Hiểu **nguồn entropy/CSPRNG, provenance, self-test, pairwise consistency test và health checks**; biết giới hạn suy luận từ một mẫu khóa.
4. Kiểm tra đúng **cặp public/private key** với chữ ký số hoặc phép thỏa thuận khóa được kiểm soát.
5. Nhận diện rủi ro **invalid public key, wrong curve, low-order point, key mismatch và key substitution**.
6. Kiểm tra thao tác thử với **AES-GCM, HMAC, KEK wrapping, chữ ký số, X25519/ECDH** mà không đưa dữ liệu production vào test.
7. Xác nhận khóa **KMS/HSM non-exportable** bằng metadata/attestation/challenge phù hợp thay vì yêu cầu xuất raw key.
8. Thiết kế **acceptance gates** trước khi chuyển khóa sang ACTIVE, gắn owner/custodian, IAM, key ID/version và audit evidence.
9. Hiểu cách **quarantine, revoke, regenerate** khi một bài kiểm tra thất bại, tránh dùng khóa nghi vấn.
10. Đọc và áp dụng ví dụ **Java 17** minh họa kiểm tra khóa đối xứng, Ed25519 và X25519.

## 2. Kiểm tra key sau generation nằm ở đâu trong key lifecycle?

Quy trình khái niệm:

~~~mermaid
flowchart LR
    REQ["Yêu cầu tạo khóa + approved policy"] --> GEN["Generate/Import trong ranh giới tin cậy"]
    GEN --> P["Post-generation validation"]
    P --> DEC{"Qua acceptance gates?"}
    DEC -->|"Không"| Q["Quarantine / disable / investigate"]
    Q --> RET["Regenerate hoặc khắc phục có phê duyệt"]
    RET --> GEN
    DEC -->|"Có"| REG["Register key ID/version, owner, custodian"]
    REG --> IAM["Cấp IAM/usage hẹp + Activate"]
    IAM --> USE["Use key: Encrypt / Sign / Wrap..."]
    USE --> LIFE["Audit, review, rotate, revoke, destroy"]
~~~

**Tách "generated" khỏi "active"** giúp tránh khóa chưa được xác minh đã bị ứng dụng sử dụng. Một số KMS tạo khóa ở trạng thái Enabled ngay; nếu hệ thống cần acceptance gate, phải dùng **quy trình cấp quyền/alias routing/key policy** để không cho workload production sử dụng trước khi hoàn tất, thay vì giả định mọi provider có native state “PENDING_VALIDATION”.

### 2.1. Ba lớp kiểm tra

| Lớp | Câu hỏi | Ví dụ |
| --- | --- | --- |
| **Structural/parameter validation** | Khóa có đúng định dạng, loại, thuật toán, kích cỡ và thuộc tính? | AES 256-bit, RSA public exponent hợp lệ theo profile, X25519 đúng type, exportability |
| **Cryptographic functional validation** | Vật liệu khóa/cặp khóa hoạt động nhất quán trong thuật toán dự kiến? | AES-GCM encrypt/decrypt và reject tag sai; Ed25519 sign/verify; ECDH hai bên nhận cùng secret |
| **Operational/governance acceptance** | Khóa có đúng nơi quản lý, purpose, IAM, metadata, lifecycle và evidence? | KMS key ID/region, key policy, owner/custodian, rotation, audit, recovery |

**Một lớp không thay thế hai lớp còn lại.** Có khóa AES đúng 32 byte và round-trip AES-GCM thành công nhưng sinh bằng **mật khẩu hard-code**. Có khóa HSM sinh đúng chuẩn nhưng quyền Sign mở cho nhiều workload không liên quan.

### 2.2. Các phép kiểm tra cần được thực hiện ở đâu?

- **Ngay trong cryptographic module/provider:** self-tests, RNG health tests, pairwise consistency tests theo đặc tả/module thích hợp; ứng dụng không nên tự mô phỏng một chứng nhận an toàn.
- **Tại key creation service:** kiểm tra request profile, tenant, key type, exportability, key usage, provider response.
- **Tại KMS/HSM control plane:** metadata, state, IAM/key policy, HSM partition, audit, attestation nếu hỗ trợ.
- **Tại ứng dụng Java:** phép thử chức năng bằng **test messages**, định dạng key và policy gate; không yêu cầu lấy raw material không cần thiết.
- **Tại security governance:** owner/custodian, phê duyệt, inventory, recovery, review và incident plan.

## 3. Phân biệt key material, key reference và evidence

Trong một HSM/KMS hiện đại, **khóa có thể không xuất được**. Ứng dụng nhận **key reference** (ID, ARN/resource name, alias, handle) và gọi thao tác qua API; nó không nhận raw private key/KEK.

| Đối tượng | Minh họa | Nên kiểm tra bằng gì? |
| --- | --- | --- |
| **Raw symmetric key** | Byte bí mật của AES/HMAC trong runtime demo | Độ dài nếu được phép truy cập; test primitive |
| **Private key non-exportable** | HSM signing key | Key attributes + Sign challenge có kiểm soát; Verify bằng public key tin cậy |
| **Public key** | DER/X.509 encoded Ed25519/RSA/EC | Parse theo thuật toán/profile, kiểm tra trust, constraints |
| **Key pair reference** | Private signing handle + public key material | Pairwise consistency/challenge + mapping key ID |
| **KMS key reference** | ID/alias/version/region/provider | Describe key, key policy, grant, state và source metadata |
| **Wrapped DEK** | DEK bọc bằng KEK | KMS/context test có quyền, kiểm tra format/version |
| **Key inventory record** | Owner/custodian/purpose/state/cryptoperiod | Đối soát với trạng thái thực tế |
| **Attestation/evidence** | Metadata được ký hoặc audit provider | Verify provenance, chain, freshness, scope |

### 3.1. Key ID không phải bằng chứng khóa đúng

Nếu ứng dụng để client tự gửi `keyId` rồi tin rằng “có ID nghĩa là được dùng”, attacker có thể thử các key IDs không thuộc tenant/purpose của mình.

Key ID/alias cần được **ánh xạ từ trusted registry hoặc configuration**; khi review phải xác minh **phiên bản vật liệu khóa thực sự** liên quan, nhất là sau rotation hoặc khi alias chuyển sang key mới.

### 3.2. Public key có thể công khai nhưng không mặc nhiên đáng tin

Một public key hợp lệ về cú pháp không tự chứng minh đó là **khóa của đối tác đúng danh tính**. Attacker có thể tự sinh cặp khóa, xuất public key và trả về kết quả Verify=true với chữ ký của họ.

Cần thêm **nguồn trust**: certificate/PKI, JWKS endpoint đã được cấu hình, registry có integrity, fingerprint được phân phối đáng tin hoặc quy trình pinning khi phù hợp.

## 4. Kiểm tra trước tiên: yêu cầu sinh khóa có đúng profile?

Một lớp kiểm tra rất sớm là xác nhận **request tạo key** khớp chính sách, chứ không phải đợi nhận kết quả rồi mới đoán.

### 4.1. Các trường cần có trong request/profile

- **Key type:** symmetric, asymmetric signing, asymmetric key agreement, MAC, KEK, root.
- **Algorithm/primitive:** AES, HMAC-SHA256, Ed25519, X25519, RSA-PSS, curve profile...
- **Key size/parameters:** số bit, curve, exponent, mode/profile được phép.
- **Purpose/key usage:** Encrypt/Decrypt, Sign/Verify, Wrap/Unwrap, Derive.
- **Environment/tenant/data class:** production, staging, đối tác, phạm vi dữ liệu.
- **Origin:** generated in KMS/HSM, imported material, on-device generation.
- **Exportability:** policy cho phép xuất, chỉ wrap, hay non-exportable.
- **Lifecycle:** activation date, cryptoperiod, rotation schedule, revocation policy.
- **Ownership:** key owner, custodian, service principal, approval record.
- **Recovery:** backup, replication, escrow/quorum hoặc intentionally ephemeral.
- **Audit:** key ID/version, creation request ID, creator/approver và policy version.

### 4.2. Policy profile ví dụ

~~~yaml
policyProfileId: billing-dek-generation-v2
environment: production
purpose: invoice-content-encryption
keyClass: DEK
algorithm: AES
keyLengthBits: 256
usage:
  - ENCRYPT
  - DECRYPT
materialOrigin: APPROVED_CSPRNG_OR_KMS
keyStorageModel: ENVELOPE_WITH_APPROVED_KEK
requireUniqueNoncePerKey: true
aadSchemaVersion: invoice-aad-v1
ownerRole: billing-platform
custodianRole: crypto-operations
requireKeyIdAndVersion: true
requireCreationAuditEvidence: true
requireFunctionalSanityTest: true
activationRequires:
  - approved-policy-mapping
  - key-reference-confirmation
  - key-usage-authorization
  - audit-evidence
~~~

Đây là **mẫu chính sách giả định**; không phải lệnh gọi KMS thật hoặc yêu cầu rằng mọi DEK đều có cùng cách sinh/kích thước. **AES-128** và **AES-256** đều có ứng dụng hợp lệ tùy threat model và profile.

### 4.3. Không tin response mà bỏ qua context

Nếu creation request nhằm tạo signing key của **release service production**, response phải được đối chiếu với:

~~~text
expected:
    algorithm = Ed25519
    purpose = release-signature
    environment = production
    storage = approved HSM partition
    exportability = non-exportable
    signer principal scope = release pipeline only

observed:
    thuật toán, key reference, provider, partition,
    attributes, allowed operations, owner/approval
~~~

Một response có trạng thái `SUCCESS` nhưng thuật toán/usage/exportability khác expected là **validation failure**, không phải “cảnh báo để xử lý sau”.

## 5. Nguồn sinh khóa và entropy: điều gì kiểm chứng được?

### 5.1. CSPRNG và entropy là yêu cầu nguồn gốc, không phải “trông ngẫu nhiên”

**Cryptographically Secure Pseudo-Random Number Generator (CSPRNG)** được dùng để sinh vật liệu bí mật hoặc seed theo thiết kế được phê duyệt.

Các thuộc tính cần có:

- Seed/key material được lấy từ **nguồn entropy phù hợp**, không dựa vào timestamp, username hay giá trị dễ đoán.
- RNG/DRBG được sử dụng đúng cách và theo cấu hình/validation module thích hợp.
- Không dùng `java.util.Random` để tạo khóa bí mật.
- Không hard-code seed của `SecureRandom` bằng chuỗi cố định cho production.
- Không “tăng độ dài” secret yếu bằng `SHA-256(secret)` rồi coi entropy đã tăng.
- Kiểm soát môi trường, snapshot/VM cloning, lỗi RNG initialization theo threat model.

**Không có phép kiểm tra thống kê đơn lẻ trên một khóa 256 bit có thể chứng minh key có 256 bit entropy.** Một chuỗi toàn ký tự trông phức tạp vẫn có thể được tạo hoàn toàn dự đoán được từ seed cứng.

### 5.2. Sau generation nên kiểm tra RNG bằng cách nào?

| Phương án | Có giá trị gì? | Không chứng minh được gì? |
| --- | --- | --- |
| Kiểm tra **nguồn key generation** và provider | Xác minh đường tạo khóa dùng CSPRNG/HSM đã duyệt | Không tự chứng minh mọi triển khai/provider đều hoàn hảo |
| Kiểm tra phiên bản, cấu hình, FIPS validation khi có yêu cầu | Biết phạm vi module/thuật toán/operating mode được đánh giá | Không có nghĩa mọi ứng dụng dùng module đều an toàn |
| RNG health tests theo thiết kế module | Phát hiện một số lỗi nguồn entropy/DRBG | Không phải bằng chứng tuyệt đối chống backdoor/seed compromise |
| Pairwise consistency tests | Phát hiện sự không khớp một số cặp khóa và thao tác | Không đo entropy hoặc bảo đảm secret không bị sao chép |
| Kiểm tra trùng key trong registry/trên luồng phát hành | Có thể phát hiện lỗi hiếm hoặc import trùng | Không thể chứng minh độ ngẫu nhiên khi không thấy trùng |
| Test chức năng Encrypt/Sign | Xác nhận primitive hoạt động trong một đường sử dụng | Không chứng minh seed mạnh |

Nếu một HSM/KMS đã quản lý key generation và self-tests trong ranh giới đã được đánh giá, ứng dụng **không nên bắt buộc xuất raw key** để tự tính histogram hoặc thử kiểm tra randomness. Hãy xác minh **cấu hình, provenance và evidence** từ nhà cung cấp theo phạm vi yêu cầu.

### 5.3. Known-answer test không dùng để kiểm tra một khóa ngẫu nhiên

**Known-answer test (KAT)** dùng input/key/test vector **đã biết** để kiểm tra implementation cho ra output kỳ vọng. Đây là **test của thuật toán/provider**.

**Pairwise consistency test (PCT)** kiểm tra cặp private/public key có thực hiện đúng chức năng tương ứng, ví dụ **ký bằng private và Verify bằng public**, hoặc **key agreement có cùng kết quả giữa hai phía** theo giao thức.

Không nên gộp:

- KAT: một bộ test vector có kết quả định trước.
- PCT: kiểm tra sự nhất quán của một cặp khóa được sinh.
- RNG health test: kiểm tra điều kiện vận hành RNG theo thiết kế.
- Key validation: xác minh thuộc tính và điều kiện để key được dùng.
- Security audit: đánh giá tổng thể threat model/IAM/provenance/lifecycle.

Một HSM có thể thực hiện tests nội bộ theo chuẩn áp dụng; **không tái tạo một cơ chế chứng nhận** bằng vài đoạn code thử.

## 6. Structural validation theo từng loại khóa

### 6.1. AES/DEK đối xứng

Những điều kiện thường gặp:

- **Key algorithm/type** đúng AES.
- Key length thuộc tập profile cho phép, thường 128/192/256 bit trong AES; không nhận key length tùy ý.
- Secret được **sinh từ CSPRNG/KMS**, không phải password thô.
- Đúng **usage** và key state, không được dùng DEK làm signing key/KEK nếu policy không cho phép.
- Nếu raw key được phép hiện diện ở JVM, thời gian tồn tại phải ngắn và tránh log/dump.
- Với **AES-GCM**, key length hợp lệ vẫn chưa đủ: **nonce uniqueness, AAD, tag handling, usage limits** phải được thiết kế ngay từ đầu.

**Lưu ý:** `SecretKey.getEncoded()` có thể trả `null` với key non-exportable. Điều này **không phải lỗi** nếu policy yêu cầu key nằm trong HSM. Hãy kiểm tra attribute qua provider thay vì coi việc không xuất được là không hợp lệ.

### 6.2. HMAC/MAC key

- Secret có đủ entropy theo profile và độ dài phù hợp.
- Key được gắn với `HmacSHA256` hoặc thuật toán MAC đã duyệt.
- Mục đích dùng khóa được tách khỏi khóa AES/KEK/root.
- Kiểm tra API có thực sự cho **GenerateMac/VerifyMac**, hay cấp raw HMAC secret cho mọi verifier.
- Một kiểm tra chức năng có thể dùng **test message**, tạo MAC và xác minh trên đường xử lý được cho phép.
- Nếu VerifyMac được cung cấp qua HSM, không cố xuất HMAC key chỉ để tự tính tag tại ứng dụng.

Có MAC hợp lệ không chứng minh thông điệp **mới**; cần anti-replay nếu use case yêu cầu.

### 6.3. KEK và wrapping key

Một KEK phải có đúng **wrapping algorithm/key class** và ranh giới lưu trữ. Các câu hỏi:

- Đây là **KEK** hay DEK? Có dùng sai KEK để mã hóa hàng triệu bản ghi trực tiếp không?
- Cơ chế Wrap/Unwrap có **kiểm tra tính toàn vẹn** phù hợp?
- Có dùng AES-KW/KWP, AEAD wrapping hoặc KMS API được phê duyệt?
- Có `key ID/version, encryption context, purpose` cho wrapped DEK?
- KEK có non-exportable khi chính sách yêu cầu?
- Có thể **recovery/rotate** mà không mất khả năng mở wrapped DEKs lịch sử?

Không dùng **AES-ECB** tự chế để bọc DEK. Không thử Wrap/Unwrap trên raw **production DEK** từ một hệ thống khác ngoài luồng đã phê duyệt.

### 6.4. Cặp RSA

Đối với RSA, review profile thường gồm:

- Key pair thuộc thuật toán RSA phù hợp và được sinh từ provider đáng tin.
- **Modulus size** đạt ngưỡng tối thiểu của profile hiện hành, không tự chọn giá trị thấp cho tiện.
- Public exponent hợp lệ theo policy (một lựa chọn thông dụng là **65537**); không xem con số này thay các kiểm tra khác.
- Định dạng public key/credential đúng; key version và usage rõ.
- Nếu dùng **RSA-PSS để Sign**, phải cấu hình đúng hash/MGF/salt theo profile.
- Nếu dùng **RSA-OAEP để encrypt/wrap**, phải chọn hash/MGF/label phù hợp và tuân thủ giới hạn kích thước input.
- Dùng **private-public PCT** với operation dự kiến theo quyền cho phép, không suy luận từ việc modulus có độ dài đúng.

**RSA-PSS không phải RSA-OAEP.** Cùng thuật toán nền RSA nhưng mục đích và tham số khác nhau; key usage cần được thiết kế/giới hạn.

### 6.5. Cặp EC/ECDSA và Ed25519

- **Curve/key type** khớp profile; không coi mọi EC public point là hợp lệ trên mọi curve.
- Public key được parse và xác thực **đúng format, domain parameters, point validity** theo yêu cầu thuật toán.
- Private key/ public key có thực sự là một cặp tương ứng?
- Private signing key không xuất được nếu policy yêu cầu.
- Một **challenge signature** trên test payload giúp kiểm tra đường Sign/Verify.
- Public verification key phải được gắn với **key ID, issuer, purpose và trust** đúng.

Với **Ed25519**, có thể sinh cặp bằng JCA trong môi trường demo và thử Sign/Verify. Điều này **không tự chứng minh nguồn seed bí mật đủ ngẫu nhiên**. Việc Verify thành công với public key không tin cậy cũng **không chứng minh danh tính**.

### 6.6. X25519/ECDH key agreement

Với X25519:

- Key type `X25519` phải đúng mục đích agreement, không dùng làm signing key.
- Provider/giao thức phải xử lý **invalid/low-order public inputs** theo yêu cầu của thuật toán.
- X25519 xử lý u-coordinate theo quy tắc của thuật toán; không áp dụng mù quáng validation cho ECDSA curves sang X25519.
- Shared secret **toàn zero** phải bị từ chối ở nơi giao thức yêu cầu; không dùng nó để sinh traffic key.
- Shared secret là **input cho KDF/key schedule**, không dùng thẳng làm AES key.
- **Authentication** của peer và transcript là điều kiện chống MITM, riêng ECDH không có.
- Phân biệt **static vs ephemeral private key** và cryptoperiod/forward secrecy thực tế.

Với ECDH trên các Weierstrass curves như P-256, public point validation và domain parameters có những quy tắc **khác** X25519. Nên sử dụng **provider/giao thức đã được phân tích** thay vì tự viết parse/kiểm tra điểm.

## 7. Functional validation: nên thử gì và không nên thử gì?

Sau khi metadata đúng, một số phép kiểm tra chức năng giúp phát hiện **sai cặp khóa, key mapping, provider configuration hoặc key operation path**.

### 7.1. Ma trận test phù hợp

| Key type / use case | Sanity test có thể phù hợp | Điểm phải cẩn thận |
| --- | --- | --- |
| AES-GCM DEK local demo | Encrypt test payload, Decrypt đúng AAD, sửa tag thì phải reject | Không dùng nonce trùng với key production; không log plaintext/key |
| HMAC-SHA256 | Tạo MAC của test message, kiểm tra tag đúng và sửa thông điệp phải fail | Không gửi secret cho verifier không được phép |
| Ed25519 signing pair | Sign challenge, Verify với public key từ trusted key reference, sửa message thì fail | Phải có quyền Sign thử, audit, không ký payload nghiệp vụ giả |
| RSA-PSS signing pair | Sign/Verify với PSS parameters đúng profile | Không fallback sang PKCS#1 v1.5 nếu profile không cho |
| X25519 agreement demo | Hai bên agreement tạo cùng shared secret, kiểm tra non-zero | Không dùng shared secret thô làm traffic key |
| KEK Wrap/Unwrap | Wrap/Unwrap **test DEK** bằng key ID/context được phép | Tránh trả/export test DEK nếu policy không cho; audit |
| KMS asymmetric decrypt key | Encrypt với public key hợp lệ, Decrypt test ciphertext qua KMS khi được phép | Chỉ dùng key có usage Decrypt, không thay Sign |
| Root/HSM master key | Self-test/attestation và key attributes từ HSM | **Không** yêu cầu xuất master key để self-test tại app |
| Ephemeral session key | Provider/protocol handshakes và test fixtures | Không lưu lâu session secret để “kiểm tra” |

### 7.2. Kiểm tra kết quả âm (negative tests)

Không chỉ thử phép toán đúng. Nếu phạm vi cho phép và có dữ liệu giả:

- AES-GCM: sai **AAD**, sửa **ciphertext** hoặc **tag** phải bị từ chối.
- Sign/Verify: sửa message hoặc dùng public key khác phải Verify=false.
- HMAC: sửa message hoặc tag phải xác minh thất bại.
- KMS: workload không có quyền phải nhận **AccessDenied**, không tự rơi về local key.
- KMS context: sai tenant/purpose phải fail nếu policy/provider enforce điều kiện đó.
- Alias/key version: không được âm thầm chọn key sai vì ID không rõ.
- Lifecycle: key **disabled/retired** phải từ chối operation mới bị cấm.

**Negative test không được triển khai bằng cách cố ý phá ciphertext production hoặc liên tục dò key ID ngoài phạm vi**. Dùng test key, sandbox hoặc test input được phê duyệt.

### 7.3. Tách “key generation validation” khỏi protocol test

Một cặp X25519 mới có thể có private/public hợp lệ nhưng việc đưa nó vào protocol **không có xác thực peer** vẫn cho phép MITM. Một Ed25519 pair ký đúng nhưng ứng dụng không kiểm tra `issuer` và `audience` vẫn chấp nhận token giả về mặt nghiệp vụ.

Do đó phải giữ hai tầng:

- **Validate key material/operation**: khóa có đúng và hoạt động được?
- **Validate application protocol**: khóa dùng đúng danh tính, đúng thông điệp, chống replay và đúng authorization không?

## 8. Pairwise consistency test (PCT) và public-key validation

### 8.1. PCT cho signing key pair

~~~mermaid
sequenceDiagram
    participant G as Key generation service
    participant H as HSM/KMS or JCA provider
    participant V as Independent verifier
    participant I as Key inventory/audit
    G->>H: Generate signing key pair theo approved profile
    H-->>G: Key ID + public key + attributes
    G->>G: Tạo test challenge không nhạy cảm
    G->>H: Sign(challenge) theo quyền test
    H-->>G: Signature
    G->>V: Public key từ key reference + challenge + signature
    V-->>G: Verify true/false
    G->>I: Chỉ ghi key ID, algorithm, result và evidence
    Note over G,H: Không export private key
~~~

Nếu Verify=false, có thể là:

- Public key không đi cùng private key đang được dùng.
- Key alias/version trỏ nhầm.
- Algorithm/signature parameters không nhất quán.
- Challenge bytes bị biến đổi do encoding/serialization.
- HSM/KMS trả signature format khác verifier kỳ vọng.
- Public key/trust mapping bị thay trái phép.

**PCT thất bại cần điều tra và không kích hoạt khóa.** Không tự “thử đại tất cả public keys” rồi chọn cái Verify được nếu không có registry và proof of identity.

### 8.2. Public-key structural validation và trust là hai thứ riêng

Ví dụ một public key RSA có đúng DER và modulus hợp lệ chưa có nghĩa nó thuộc **bank.example**. Cần xác minh **certificate chain/hostname/pinning/JWKS issuer** theo chính sách.

Trong key establishment, public key của đối tác còn phải phù hợp với **curve, subgroup/low-order validation và protocol**. Một public key sai format có thể bị từ chối **trước khi** dùng private key để tính shared secret.

### 8.3. Không trích public/private key để so byte

Trong nhiều lược đồ, public key có thể được dẫn xuất từ private key, nhưng việc so sánh không nên buộc private key rời HSM. Hãy dùng **supported PCT, attested key attributes hoặc test challenge**. Không in private key PEM hoặc seed để debug.

### 8.4. PCT không thay entropy assessment

Hai khóa được sinh từ seed dự đoán được vẫn có thể hoàn toàn **nhất quán** và Sign/Verify thành công. PCT chỉ kiểm tra tính tương ứng/chức năng của cặp trong phạm vi bài test.

## 9. Kiểm tra key trong KMS/HSM: không xuất secret

### 9.1. Tối thiểu xác minh control-plane metadata

| Nhóm | Trường/điều kiện cần đối chiếu |
| --- | --- |
| **Identity** | Provider, account/project, region, partition, key ID, alias, version |
| **Origin** | Generated in approved KMS/HSM hoặc imported theo approval |
| **Key type** | Symmetric, HMAC, asymmetric signing/encryption/agreement |
| **Algorithm** | Curve, key size, permitted signing/encryption scheme |
| **Usage** | Allowed operations đúng purpose; không dư Decrypt/Sign |
| **Exportability** | Non-exportable hoặc export policy phù hợp |
| **State** | Enabled/Active theo điều kiện activation; chưa scheduled deletion sai |
| **Lifecycle** | Activation/cryptoperiod, rotation, revocation, recovery, destruction |
| **IAM/grants** | Workload identity đúng key/action/environment, SoD |
| **Audit** | Creation event, key attribute changes, test operations, approval evidence |

Key attributes có thể khác theo nhà cung cấp. **Không giả định một API DescribeKey chung trả đủ exportability hoặc key material provenance** cho mọi KMS/HSM. Khi chứng minh compliance, cần nêu **provider-specific source và giới hạn**.

### 9.2. HSM/KMS attestation (nếu nền tảng hỗ trợ)

Một số nền tảng hỗ trợ **attestation** cho khóa hoặc thiết bị. Khi sử dụng:

1. Kiểm tra **attestation identity, certificate chain và trust root** phù hợp.
2. Kiểm tra **freshness/challenge/nonce** nếu cơ chế hỗ trợ.
3. Đối chiếu **key ID hoặc public key, algorithm, attributes, device/partition**.
4. Kiểm tra bằng chứng được tạo trong **đúng security boundary** dự kiến.
5. Xác nhận version/firmware/module policy theo yêu cầu hệ thống.
6. Ghi evidence reference, thời điểm, verification result; không đưa raw secret vào audit.

Attestation **phụ thuộc khả năng nhà cung cấp** và semantics của statement. Một tờ chứng nhận HSM hoặc chữ “FIPS” trên sản phẩm **không tự bảo đảm mỗi cấu hình key và IAM cụ thể đã đạt mọi tiêu chí**.

### 9.3. Key non-exportable cần được đánh giá đúng

**Non-exportable** nghĩa là key material không thể được xuất dưới hình thức bị cấm qua interface, theo tính năng và ranh giới được bảo đảm. Nhưng:

- Caller có quyền KMS **Sign** có thể tạo chữ ký trên payload trái phép.
- Caller có quyền **Unwrap** có thể nhận plaintext DEK nếu mô hình cho phép.
- Key administrator có quyền thay policy/grants có thể mở rộng khả năng dùng khóa.
- Backup/recovery có thể tạo đường truy cập khác với API thường.
- Một HSM đúng chuẩn vẫn cần IAM, audit và business authorization.

**Kiểm tra khóa sau sinh phải bao gồm quyền sử dụng và quyền quản trị**, không chỉ key strength.

### 9.4. Tự kiểm tra quyền tối thiểu

Trước khi đưa key vào production, các test quyền có thể xác nhận:

~~~text
production writer:
  ALLOW Encrypt hoặc GenerateDataKey trong phạm vi cần
  DENY Sign, Export, ChangeKeyPolicy

production reader:
  ALLOW Decrypt/Unwrap đúng key và context
  DENY Export, Destroy, Sign

security auditor:
  ALLOW đọc metadata/audit theo policy
  DENY Decrypt, Sign, Unwrap

key custodian:
  ALLOW công việc quản trị được duyệt
  DENY Decrypt/Sign nếu không có nhiệm vụ riêng
~~~

Không kiểm tra bằng cách thử gọi với **principal thực sự không được ủy quyền** trong production. Sử dụng test identity và key scope được cho phép, phối hợp cùng IAM review và audit.

## 10. Kiểm tra key đối với envelope encryption

Một hệ thống dùng **DEK** để mã hóa dữ liệu và **KEK trong KMS** để wrap DEK.

~~~mermaid
flowchart TD
    P["Yêu cầu tạo DEK/KEK"] --> K["KMS tạo hoặc cung cấp key material"]
    K --> M["Validate key metadata, purpose, usage, state"]
    M --> TEST["Controlled functional test"]
    TEST --> DEC{"Tất cả gates PASS?"}
    DEC -->|"Không"| Q["Quarantine / no production traffic"]
    DEC -->|"Có"| REG["Record key ID/version + owner/custodian"]
    REG --> DEK["Generate test DEK / Wrap với KEK"]
    DEK --> AEAD["AES-GCM Encrypt test data: nonce + AAD + tag"]
    AEAD --> UN["Authorized Unwrap + Decrypt + verify"]
    UN --> EVD["Audit: metadata + outcome, không raw secret"]
~~~

### 10.1. Cần xác nhận những gì?

- **Key ID/KEK version** trỏ đúng môi trường, không dùng alias sai.
- **Key purpose** là wrap/unwrap DEKs, không tự mở quyền Decrypt dữ liệu khác.
- **DEK** được sinh mạnh và có identity/version đủ truy vết nếu cần.
- **Wrapped DEK** được lưu với key reference và encryption context cần thiết.
- **AES-GCM data package** lưu nonce, tag và AAD format/schema version.
- **Unwrap** với context sai phải bị từ chối khi provider policy/binding yêu cầu.
- **Decrypt** với AAD tenant/record sai phải fail, không “thử bỏ AAD”.
- **Key destroy/rotation** không làm mất dữ liệu backup cũ chưa migration.

### 10.2. KMS encryption context khác AAD của dữ liệu

Ví dụ:

~~~json
{
  "service": "billing",
  "purpose": "wrap-invoice-dek",
  "environment": "production",
  "tenant": "tenant-A"
}
~~~

Một số KMS dùng **encryption context** như AAD trong quá trình mã hóa/wrap DEK. Nhưng dữ liệu được ứng dụng mã hóa bằng AES-GCM có thể dùng **AAD khác**: tenant ID, invoice ID, schema version.

Khi validation, phải kiểm tra **cả hai lớp trong giới hạn kiến trúc**. Không dùng context do client tự khai làm bằng chứng principal đã được phân quyền với tenant đó.

### 10.3. Thử khả năng khôi phục mà không tạo rủi ro mới

Một test tốt nên dùng **DEK test** và payload vô hại, không sử dụng dữ liệu thật để tiện kiểm. Nếu muốn xác minh backup phục hồi, dùng **restore rehearsal trong môi trường kiểm soát** với quyền và evidence riêng.

Một KEK đã được KMS tạo và Wrap test DEK thành công **không tự bảo đảm nó còn tồn tại sau một sự cố region/HSM**. Cần review recovery/backup/replication theo provider và cryptoperiod.

## 11. Java 17: kiểm tra khóa AES-GCM, Ed25519 và X25519

Ví dụ sau có thể biên dịch và chạy bằng JDK 17 với các provider mặc định phù hợp. Nó minh họa **khóa sinh trong JVM cho mục đích học tập**, gồm:

1. Kiểm tra key algorithm và độ dài AES từ local `KeyGenerator`.
2. Thử **AES-GCM** encrypt/decrypt với AAD, kiểm tra tag khi bị sửa.
3. Kiểm tra **Ed25519 key pair** bằng Sign/Verify và negative test.
4. Kiểm tra **X25519 key agreement** của hai cặp ephemeral dùng trong test, shared secrets phải khớp và không toàn zero.
5. In **kết quả PASS**, không in raw keys/shared secrets.

**Giới hạn quan trọng:** khóa AES trong demo được phép truy cập dưới dạng `getEncoded()` vì nó là khóa local. Với key HSM non-exportable, `getEncoded()` có thể trả `null`; production phải thay kiểm tra trực tiếp bằng **metadata/attestation/KMS operation**. Hai keypairs X25519 trong test chỉ minh họa agreement; không xác thực peer hay xây dựng TLS.

~~~java
import java.nio.charset.StandardCharsets;
import java.security.KeyPair;
import java.security.KeyPairGenerator;
import java.security.MessageDigest;
import java.security.SecureRandom;
import java.security.Signature;
import java.util.Arrays;
import javax.crypto.AEADBadTagException;
import javax.crypto.Cipher;
import javax.crypto.KeyAgreement;
import javax.crypto.KeyGenerator;
import javax.crypto.SecretKey;
import javax.crypto.spec.GCMParameterSpec;

public final class PostGenerationKeyValidationDemo {
    private static final SecureRandom RNG = new SecureRandom();
    private static final int GCM_NONCE_BYTES = 12;
    private static final int GCM_TAG_BITS = 128;

    private static void require(boolean condition, String problem) {
        if (!condition) {
            throw new IllegalStateException(
                "Key validation failed: " + problem);
        }
    }

    private static void validateLocalAesKey(SecretKey key)
            throws Exception {

        require("AES".equalsIgnoreCase(key.getAlgorithm()),
            "Key must be AES");

        // Chỉ dành cho KEY LOCAL EXPORTABLE của ví dụ.
        // Không dùng getEncoded() để thử xuất khóa HSM.
        byte[] encoded = key.getEncoded();
        require(encoded != null, "Demo key must be locally encodable");
        try {
            require(encoded.length == 32, "AES-256 requires 32 bytes");
        } finally {
            Arrays.fill(encoded, (byte) 0);
        }

        byte[] nonce = new byte[GCM_NONCE_BYTES];
        RNG.nextBytes(nonce);  // Nonce mới cho lần encrypt thử này.

        byte[] aad = "test|tenant-A|record-154"
            .getBytes(StandardCharsets.UTF_8);
        byte[] plaintext = "non-sensitive-demo-data"
            .getBytes(StandardCharsets.UTF_8);

        Cipher enc = Cipher.getInstance("AES/GCM/NoPadding");
        enc.init(Cipher.ENCRYPT_MODE, key,
            new GCMParameterSpec(GCM_TAG_BITS, nonce));
        enc.updateAAD(aad);
        byte[] ciphertextAndTag = enc.doFinal(plaintext);

        Cipher dec = Cipher.getInstance("AES/GCM/NoPadding");
        dec.init(Cipher.DECRYPT_MODE, key,
            new GCMParameterSpec(GCM_TAG_BITS, nonce));
        dec.updateAAD(aad);

        byte[] restored = dec.doFinal(ciphertextAndTag);
        require(MessageDigest.isEqual(plaintext, restored),
            "AES-GCM round trip mismatch");

        // Negative test: sửa tag và bảo đảm bị từ chối.
        byte[] modified = ciphertextAndTag.clone();
        modified[modified.length - 1] ^= 1;

        Cipher bad = Cipher.getInstance("AES/GCM/NoPadding");
        bad.init(Cipher.DECRYPT_MODE, key,
            new GCMParameterSpec(GCM_TAG_BITS, nonce));
        bad.updateAAD(aad);

        boolean rejected = false;
        try {
            bad.doFinal(modified);
        } catch (AEADBadTagException expected) {
            rejected = true;
        }
        require(rejected, "GCM must reject modified tag");

        System.out.println("AES-256-GCM: PASS");
    }

    private static void validateEd25519(KeyPair pair)
            throws Exception {

        // Một số provider trả getAlgorithm() = "EdDSA" cho
        // Ed25519; kiểm tra interface + named parameters thay vì
        // so sánh chuỗi algorithm theo cách phụ thuộc provider.
        require(pair.getPublic()
                    instanceof java.security.interfaces.EdECPublicKey
                && pair.getPrivate()
                    instanceof java.security.interfaces.EdECPrivateKey,
            "Expected EdEC public/private key interfaces");

        var pub = (java.security.interfaces.EdECPublicKey)
            pair.getPublic();
        var priv = (java.security.interfaces.EdECPrivateKey)
            pair.getPrivate();
        require("Ed25519".equals(pub.getParams().getName())
                && "Ed25519".equals(priv.getParams().getName()),
            "Unexpected EdDSA named parameter set");

        byte[] challenge = new byte[32];
        RNG.nextBytes(challenge);

        Signature signer = Signature.getInstance("Ed25519");
        signer.initSign(pair.getPrivate());
        signer.update(challenge);
        byte[] signature = signer.sign();

        Signature verifier = Signature.getInstance("Ed25519");
        verifier.initVerify(pair.getPublic());
        verifier.update(challenge);
        require(verifier.verify(signature),
            "Sign/Verify pairwise check failed");

        byte[] changed = challenge.clone();
        changed[0] ^= 1;

        Signature wrongMessage = Signature.getInstance("Ed25519");
        wrongMessage.initVerify(pair.getPublic());
        wrongMessage.update(changed);
        require(!wrongMessage.verify(signature),
            "Modified challenge unexpectedly verified");

        System.out.println("Ed25519 pairwise check: PASS");
    }

    private static byte[] agree(
            java.security.PrivateKey ownPrivate,
            java.security.PublicKey peerPublic)
            throws Exception {

        KeyAgreement agreement = KeyAgreement.getInstance("X25519");
        agreement.init(ownPrivate);
        agreement.doPhase(peerPublic, true);
        return agreement.generateSecret();
    }

    private static boolean allZero(byte[] secret) {
        int acc = 0;
        for (byte value : secret) {
            acc |= value & 0xff;
        }
        return acc == 0;
    }

    private static void validateX25519Agreement(
            KeyPair alice, KeyPair bob) throws Exception {

        byte[] aliceSecret = agree(
            alice.getPrivate(), bob.getPublic());
        byte[] bobSecret = agree(
            bob.getPrivate(), alice.getPublic());

        try {
            require(aliceSecret.length == 32,
                "Unexpected X25519 secret size");
            require(!allZero(aliceSecret),
                "Invalid all-zero shared secret");
            require(MessageDigest.isEqual(aliceSecret, bobSecret),
                "X25519 shared secrets do not match");
        } finally {
            Arrays.fill(aliceSecret, (byte) 0);
            Arrays.fill(bobSecret, (byte) 0);
        }

        System.out.println("X25519 key agreement check: PASS");
    }

    public static void main(String[] args) throws Exception {
        KeyGenerator aes = KeyGenerator.getInstance("AES");
        aes.init(256, RNG);
        SecretKey demoAes = aes.generateKey();
        validateLocalAesKey(demoAes);

        KeyPairGenerator signing =
            KeyPairGenerator.getInstance("Ed25519");
        KeyPair demoSigner = signing.generateKeyPair();
        validateEd25519(demoSigner);

        KeyPairGenerator x25519 =
            KeyPairGenerator.getInstance("X25519");
        KeyPair alice = x25519.generateKeyPair();
        KeyPair bob = x25519.generateKeyPair();
        validateX25519Agreement(alice, bob);

        System.out.println(
            "All demo functional checks passed.");
    }
}
~~~

Kết quả dự kiến:

~~~text
AES-256-GCM: PASS
Ed25519 pairwise check: PASS
X25519 key agreement check: PASS
All demo functional checks passed.
~~~

### 11.1. Giải thích chi tiết các điểm an toàn

1. **JCA/JCE chuẩn:** code dùng `KeyGenerator`, `Cipher`, `Signature`, `KeyAgreement`; không tự viết AES/Ed25519/X25519.
2. **AES key length:** kiểm tra 32 byte cho profile AES-256 của ví dụ. Với các profile khác cần thay expected size.
3. **Không giả định khóa production phải exportable:** test `getEncoded()` chỉ áp dụng local demo.
4. **GCM nonce:** sinh nonce riêng cho lần Encrypt thử. Việc lặp phép thử trên cùng key production cần chiến lược nonce và hạn mức, không được chỉ chạy lại cùng nonce/test vector.
5. **AAD:** dùng trước `doFinal` ở cả Encrypt/Decrypt, bảo đảm byte tham chiếu đồng nhất.
6. **Tag verification:** sửa authentication tag làm `AEADBadTagException`; không dùng plaintext nếu xác thực thất bại.
7. **Ed25519 PCT:** private Sign và public Verify trên challenge, kể cả negative test với message bị sửa.
8. **X25519 consistency:** hai bên tính shared secret; so sánh kết quả và từ chối all-zero trong demo.
9. **Shared secret handling:** byte arrays được xóa best-effort; tuy nhiên JVM/provider vẫn có thể giữ bản sao ngoài tầm kiểm soát.
10. **Test data không nhạy cảm:** không đưa plaintext production vào test hoặc logs.
11. **No credential dumps:** kết quả chỉ là PASS, không in raw AES key, Ed25519 private material hoặc ECDH secrets.
12. **Fail closed:** bất kỳ phép thử nào fail đều ném exception; không kích hoạt key production từ kết quả mơ hồ.

### 11.2. Điều demo KHÔNG chứng minh

- **Không chứng minh entropy của RNG/seed**: kể cả Sign/Verify và Encrypt/Decrypt hoàn hảo vẫn có thể xuất hiện nếu seed yếu.
- Không xác minh **KMS/HSM attestation, module validation, firmware, hardware boundary**.
- Không cấu hình **IAM/KeyPolicy/grants**, chủ sở hữu, custodian, key state hoặc audit.
- Không xác thực **danh tính đối tác** trong X25519; key agreement test không thay authenticated TLS 1.3.
- Không tạo **HKDF traffic keys**, không có một protocol trao đổi khóa đầy đủ.
- Không xác minh **các quy tắc chống replay**, công bố public key và trust store.
- Không kiểm tra **nhiều instance dùng chung DEK** tránh nonce reuse.
- Không mô phỏng **key backup/restore/rotation** hoặc alias versioning.
- Không bảo đảm **wipe tuyệt đối** raw key trong JVM.
- Không kiểm chứng rằng provider dùng crypto module đáp ứng một bộ tiêu chuẩn cụ thể.

**Đừng biến đoạn demo thành "security certification".** Nó là bài thực hành về **functional acceptance tests** và một phần quan sát giới hạn của kiểm tra khóa.

## 12. Nâng lên production: quy trình nghiệm thu khóa không xuất được

Với **KMS/HSM key non-exportable**, quy trình phải khác local demo.

### 12.1. Ví dụ signing key production

~~~mermaid
sequenceDiagram
    participant O as Key owner / security approver
    participant S as Key provisioning service
    participant H as Approved KMS/HSM
    participant T as Trusted verifier
    participant I as Key inventory/audit
    O->>S: Approved request + signing profile
    S->>H: CreateKey(algorithm, usage, attributes)
    H-->>S: Key reference + public key + metadata
    S->>S: Verify provider, region, key state, usage, exportability
    S->>H: Sign(test challenge) nếu policy cho phép
    H-->>S: Test signature
    S->>T: Verify challenge với bound public key
    T-->>S: PCT result
    S->>I: Record metadata + approvals + test evidence
    S-->>O: Ready for controlled activation
    Note over S,H: Private key không rời KMS/HSM
~~~

**Không tự động gọi Sign với một signing key đang được workload nghiệp vụ sử dụng** nếu chưa có quyền test hoặc có rủi ro tạo một chữ ký bên ngoài mục đích. Dùng **challenge rõ namespace** và ghi audit; với provider tích hợp self-test nội bộ có thể sử dụng evidence từ self-test thay vì yêu cầu app tự gọi.

### 12.2. Ví dụ KEK production

- Xác nhận `keyClass=KEK`, algorithm, key state và **wrap/unwrap** được phép.
- Xác nhận **key non-exportable**, provider/location đúng.
- Dùng **test DEK riêng** trong luồng được phê duyệt.
- Wrap test DEK với context đúng, unwrap lại trong môi trường thử.
- Sai context/không có IAM quyền phải bị từ chối nếu policy/provider enforce.
- Không xuất key material KEK; không ghi test DEK vào audit.
- Chỉ kích hoạt production sau khi inventory, backup/recovery policy, owner/custodian, version và grants được kiểm tra.

### 12.3. Kết quả test có thể là “not applicable”

Không phải mọi key đều có ý nghĩa chạy **Sign/Verify** hoặc **Encrypt/Decrypt**:

- HMAC key không phải signing private key Ed25519.
- Root key chỉ nên dùng **DeriveKey** qua HSM; có thể không có raw key visibility.
- Ephemeral TLS keys được quản lý bởi protocol/provider, không phải inventory dài hạn.
- Public verification key không có private key bên verifier để làm PCT.
- Imported public key cần **validation/trust** hơn là “Encrypt thử” tùy use case.

Nếu test không áp dụng, ghi `NOT_APPLICABLE` kèm lý do, **không ép dùng sai purpose chỉ để hoàn thành checklist**.
## 13. Acceptance gate trước khi đưa key vào sử dụng

Không nên chuyển trực tiếp từ "KMS CreateKey thành công" sang "ứng dụng production được phép dùng khóa". Một quy trình nghiệm thu cần chặn key chưa đạt yêu cầu, có thể gồm sáu cổng:

~~~mermaid
flowchart TD
    A["Key created + reference"] --> P{"Approved algorithm/profile?"}
    P -->|"Không"| Q["Quarantine, không route production traffic"]
    P -->|"Có"| O{"Origin, storage, exportability?"}
    O -->|"Không"| Q
    O -->|"Có"| S{"Key type, attributes, usage?"}
    S -->|"Không"| Q
    S -->|"Có"| F{"PCT/functional test phù hợp?"}
    F -->|"Không"| Q
    F -->|"Có"| G{"IAM, owner/custodian, recovery?"}
    G -->|"Không"| Q
    G -->|"Có"| E{"Evidence và approval đầy đủ?"}
    E -->|"Không"| Q
    E -->|"Có"| ACT["Controlled activation + audit"]
    Q --> X["Investigate, regenerate hoặc retest theo policy"]
~~~

| Gate | Kiểm tra chính | Evidence cần thiết |
| --- | --- | --- |
| **Policy/profile** | Key class, algorithm, size, environment, purpose | Approved request và profile version |
| **Provenance** | Approved CSPRNG/KMS/HSM, origin, location và non-exportability | Provider metadata/attestation nếu hỗ trợ |
| **Structure** | Curve, usage, key ID/version/alias, public/private mapping | Key attributes, structural validation |
| **Function** | Thử đúng operation, PCT và negative tests khi thích hợp | Functional test record, key reference |
| **Governance** | IAM least privilege, owner/custodian, cryptoperiod, backup | Key inventory, IAM snapshot, runbook |
| **Activation** | Approval, evidence integrity và routing policy | Change ticket, decision/audit record |

**Các trạng thái workflow** có thể gồm `PENDING_VALIDATION`, `VALIDATING`, `READY_FOR_APPROVAL`, `ACTIVE`, `QUARANTINED`, `REJECTED`. Đây là **trạng thái tầng quản trị**, không phải tên native bắt buộc của mọi KMS. Nếu provider tạo key ở trạng thái Enabled ngay, phải dùng **key policy/alias routing/quy trình cấp quyền** để chặn workload dùng khóa chưa được nghiệm thu.

**Không tự chuyển PASS khi thiếu bằng chứng.** Dùng `INSUFFICIENT_EVIDENCE` cho nguồn chưa đủ tin cậy, `NOT_EVALUATED` cho chưa kiểm tra và `NOT_APPLICABLE` có lý do cho test không phù hợp. Với ephemeral TLS keys, backup có thể không nên tồn tại; với KEK phục vụ backup dài hạn, recovery là một điều kiện trọng yếu.

## 14. Đăng ký key inventory sau validation

Một khóa vừa sinh cần được gắn trách nhiệm vận hành trước khi dùng:

~~~yaml
keyId: kms-billing-kek-production-example
keyVersion: v1
environment: production
keyClass: KEK
algorithmProfile: approved-kek-v2
purpose: wrap-invoice-deks
storageRef: "kms://example-account/region/opaque-id"
origin: APPROVED_KMS
nonExportableRequired: true
ownerTeam: billing-platform
custodianTeam: crypto-operations
allowedOperations: [WRAP, UNWRAP]
lifecycleState: PENDING_VALIDATION
cryptoperiodPolicyRef: "policy/key-cryptoperiod"
recoveryPolicyRef: "policy/billing-recovery"
validationEvidenceRef: "evidence://post-generation-check"
activationApprovalRef: "change://key-activation"
~~~

Ví dụ này chỉ chứa metadata giả định; **không ghi raw DEK/KEK/private key, HMAC secret, password hoặc recovery shares vào inventory**.

### 14.1. Key ID không đồng nghĩa key material duy nhất

- Key ID/alias có thể giúp chọn khóa, nhưng **không tự chứng minh entropy hoặc uniqueness của vật liệu**.
- Alias có thể đổi đích khi rotate, phải bảo vệ quyền thay alias và cập nhật cache.
- Public key hợp lệ phải gắn đúng private key reference **và** trust identity.
- Nếu import/replicate key theo thiết kế, cùng key material có thể cố ý xuất hiện ở các security boundaries đã phê duyệt; cần policy rõ.
- Inventory cần khớp trạng thái thật của provider, không chỉ các giá trị do người dùng tự điền.

### 14.2. Owner/custodian

**Key owner** xác định nghiệp vụ và mức rủi ro; **key custodian** tổ chức bảo quản, rotation/recovery và chứng cứ. KMS/HSM admin thực thi thay đổi có quyền hạn; security reviewer đối soát độc lập. Với key nhạy cảm, không để một principal tự tạo key, tự cấp Decrypt, tự ghi PASS và tự xóa audit.

## 15. Kiểm tra quyền KMS/HSM trước activation

| Vai trò | Có thể cần | Không mặc định cần |
| --- | --- | --- |
| Billing writer | Encrypt/GenerateDataKey cho tenant được phép | Decrypt toàn bộ lịch sử, Sign, Destroy |
| Billing reader | Decrypt/Unwrap đúng key và bản ghi | CreateGrant, Export |
| Release signer | Sign đúng signing key/payload profile | Đọc raw private key hoặc thay trust |
| Signature verifier | Verify với public key tin cậy | Private signing key |
| Custodian | Quản trị key lifecycle theo ticket | Decrypt/Sign mọi nội dung |
| Auditor | Read-only key metadata và audit | Unwrap/Sign/Export |
| Recovery operator | Restore qua approval/quorum theo scope | Quyền break-glass vô hạn |

Kiểm tra **effective permissions**, không chỉ khai báo trực tiếp: group inheritance, assumed role, resource policy, grants, các điều kiện IAM và cross-account paths tùy nền tảng. Role có **CreateGrant/ChangePolicy** có thể tự nâng quyền Decrypt/Sign nên cũng phải review.

Một KMS trả Decrypt thành công **không chứng minh người dùng được phép đọc hóa đơn thuộc tenant khác**. KMS encryption context có thể ràng buộc wrapped DEK, nhưng **AAD của AES-GCM trên dữ liệu** và **business authorization principal–tenant–resource** vẫn phải có riêng.

## 16. Khi kiểm tra thất bại: quarantine và xử lý đúng nguyên nhân

~~~mermaid
flowchart TD
    F["Validation FAIL"] --> B["Block activation + preserve evidence"]
    B --> D{"Phân loại lỗi"}
    D -->|"Wrong size/curve/exportability"| R["Regenerate nếu không sửa an toàn được"]
    D -->|"Pairwise/crypto failure"| C["Investigate key mapping, provider, params"]
    D -->|"Weak RNG/provenance"| I["Security incident assessment"]
    D -->|"IAM/grants quá rộng"| G["Constrain grants + retest effective permissions"]
    D -->|"Backup/evidence thiếu"| E["Recovery test / gather evidence"]
    R --> T["Rerun all required gates"]
    C --> T
    I --> T
    G --> T
    E --> T
    T --> A{"Đạt và được phê duyệt?"}
    A -->|"Không"| Q["Remain quarantined"]
    A -->|"Có"| X["Controlled activation"]
~~~

| Kết quả không đạt | Điều có thể sai | Phản ứng phù hợp |
| --- | --- | --- |
| AES key length sai | Key profile/request không đúng | Không dùng, tạo lại đúng profile |
| Signing PCT fail | Public/private mismatch, alias/version, signature params | Quarantine và đối chiếu source/format |
| X25519 all-zero/invalid input | Public key hoặc phép agreement không hợp lệ | Reject, kiểm tra provider/protocol |
| GCM tag bị sửa nhưng Decrypt vẫn trả plaintext | Fail-open hoặc lỗi primitive | Dừng triển khai, sửa API usage |
| RNG/seed có thể dự đoán | Key material có nguy cơ bị đoán | Điều tra, regenerate; re-encrypt nếu key đã dùng |
| KEK exportable trái policy | Lưu trữ/security boundary sai | Tạo lại ở nơi đúng, xem xét có lộ vật liệu không |
| KMS Decrypt/Unwrap grant quá rộng | Key usage compromise tiềm năng | Giới hạn IAM, audit, retest |
| Alias sai tenant/environment | Key substitution/cross-tenant risk | Sửa trusted mapping, đánh giá dữ liệu đã dùng |
| Không có owner/custodian | Thiếu người chịu trách nhiệm | Bổ sung trước approval |
| Thiếu recovery/restore evidence | Dữ liệu có thể không khôi phục về sau | Giữ ở trạng thái chưa nghiệm thu khi cần |
| Attestation/evidence không hợp lệ | Không chứng minh được thuộc tính cần thiết | Không coi là PASS |

**Regenerate** thường thích hợp khi thuật toán/curve sai, seed yếu, raw key đã lộ hoặc thuộc tính bất biến như non-exportability không đáp ứng. Nhưng nếu key đã dùng để mã hóa dữ liệu, không tự hủy key cũ: phải kiểm tra wrapped DEKs, ciphertext, backup, signatures và retention. Đổi KEK mà vẫn dùng **DEK đã lộ** không làm dữ liệu cũ trở lại bí mật.

## 17. Audit và evidence cho key acceptance

Một bản ghi nghiệm thu giả định:

~~~json
{
  "validationRunId": "post-keygen-example-2026",
  "keyReference": "kms://example/key/opaque-id",
  "profileVersion": "billing-kek-profile-v2",
  "validationTime": "2026-11-28T03:00:00Z",
  "results": {
    "keyTypeAndUsage": "PASS",
    "providerAndOrigin": "PASS",
    "exportability": "PASS",
    "functionalTest": "PASS",
    "pairwiseConsistency": "NOT_APPLICABLE",
    "iamGrants": "PASS",
    "recoveryPlan": "PASS"
  },
  "ownerRole": "billing-platform",
  "custodianRole": "crypto-operations",
  "evidenceRef": "evidence-store://immutable/result",
  "approvalRef": "change/key-activation-example",
  "decision": "READY_FOR_APPROVAL",
  "containsRawKeyMaterial": false
}
~~~

Một chuỗi `"PASS"` do bất kỳ app nào tự ghi không đủ: phải xác minh **source, time, scope, integrity, actor và approval**. Audit nên ghi **key ID/version, key attributes đã cho phép công bố, action, result, policy version và evidence references**.

**Không log:** raw KEK/DEK, private signing key, MAC key, recovery shares, ECDH shared secrets, TLS traffic keys, password/token hay plaintext nhạy cảm. Metadata key IDs và tenant references cũng phải được bảo vệ theo rủi ro.

Bằng chứng từ KMS/HSM và workflow phê duyệt nên được bảo vệ chống sửa/xóa trái phép; key administrator không nên đồng thời có quyền xóa mọi audit logs.

### 17.1. Kiểm tra không kết thúc khi activation

Sau khi key ACTIVE, cần:

- Giám sát changes của key attributes, IAM/grants, alias/version và trust store.
- Kiểm tra cryptoperiod, giới hạn số lần dùng, nonce strategy, rotation.
- Rà soát owner/custodian và quyền service accounts.
- Phát hiện bất thường Sign/Decrypt/Unwrap/Derive.
- Test backup/restore theo retention.
- Có runbook thu hồi, rekey, rewrap/re-encrypt và destroy.
- Điều tra nếu provider/module hoặc tiêu chuẩn liên quan thay đổi.

**PASS ở ngày generation không chứng minh trạng thái an toàn suốt vòng đời.**

## 18. Tình huống A: signing key đúng thuật toán nhưng public key không khớp

ReleaseService sinh private signing key Ed25519 trong HSM, gắn alias mới `release-v4`. Nhưng registry phân phối public key `release-v3` với nhãn v4. PCT Sign(challenge) bằng v4 rồi Verify bằng public key đang công bố trả false.

Hành động:

1. **Quarantine** việc route Sign production tới v4.
2. Kiểm tra key ID/version, alias và public fingerprint từ nguồn đáng tin.
3. Xác minh challenge bytes, format chữ ký và parameters.
4. Sửa registry qua approval, không tự thử mọi public key rồi chọn khóa bất kỳ Verify được.
5. Chạy lại PCT, negative tests và trust distribution checks.
6. Giữ public v3 cho Verify lịch sử khi chính sách yêu cầu.

Với KMS non-exportable, **không xuất raw private key** để đối chiếu. PCT giúp phát hiện mismatch; **trust identity** vẫn cần xác minh độc lập.

## 19. Tình huống B: key AES-256 hợp lệ về độ dài nhưng seed yếu

Một helper tạo AES key bằng `SHA-256(timestamp + machineId)`. Key có đúng 32 byte, AES-GCM test thành công và tag sửa bị từ chối. Nhưng attacker có thể tái tạo key nếu đoán được inputs.

Điều này chứng minh **functional test không đo entropy**. Cần:

- Thay helper bằng CSPRNG/KMS/HSM approved path.
- Kiểm tra các services và backups đã sử dụng key yếu.
- Tạo DEK mới, re-encrypt khi đã mã hóa dữ liệu và rủi ro chấp nhận không còn.
- Không coi bọc key yếu trong KEK mạnh là tăng entropy cho DEK.
- Bổ sung code review/static checks cho đường sinh khóa.

## 20. Tình huống C: KEK non-exportable nhưng Unwrap quá rộng

KMS sinh KEK đúng thuật toán và đánh dấu non-exportable. Phép Wrap/Unwrap test thành công. Tuy nhiên, role `reporting-worker` có thể Unwrap DEKs trên nhiều tenant dù nó không cần đọc dữ liệu.

Đây là **operational acceptance failure**. Khóa có thể đúng toán học nhưng sai quyền. Phải giảm grants, kiểm tra đường AssumeRole/CreateGrant, chạy negative IAM tests trong phạm vi được phép, xem usage logs và phân quyền nghiệp vụ. Nếu key chưa bị lạm dụng và vẫn đúng boundary, **không nhất thiết phải regenerate**; quyết định dựa vào điều tra và policy.

## 21. Tình huống D: backup không còn KEK

Một hệ thống đã rotate KEK-v1 sang v2. Key-v2 được sinh đúng và functional test PASS. Nhóm vận hành lên lịch xóa KEK-v1 trong khi backup lịch sử còn chứa wrapped DEKs dưới v1.

**Backup checksum đúng không chứng minh khả năng giải mã.** Trước khi hủy v1 phải kiểm kê dependencies, tìm key version/context/AAD/nonce/tag, thử restore hoặc migration hợp lệ, có owner approval và lưu bằng chứng.

## 22. Checklist nghiệm thu khóa sau generation

1. Request có đúng approved policy/profile, mục đích, environment và tenant?
2. Key class, algorithm và allowed operations có phù hợp use case?
3. Key size, curve/domain parameters và key format đúng profile?
4. Nguồn generation là CSPRNG/DRBG/KMS/HSM đáng tin, không seed cố định?
5. Có xác minh provider, account, region, partition và origin?
6. Exportability/non-exportability đáp ứng policy?
7. Có quản lý key ID/version/alias và nguồn mapping đáng tin?
8. Public key có được kiểm tra format và trust identity riêng?
9. Với RSA, có kiểm tra modulus/exponent và PSS/OAEP usage phù hợp?
10. Với X25519/EC, có validation public input và điều kiện reject shared secret không hợp lệ?
11. Có thực hiện PCT hoặc test operation phù hợp, không thử sai key purpose?
12. AES-GCM test dùng nonce mới, AAD đúng và tag verification?
13. Negative tests sửa tag/AAD/message có fail-closed?
14. Có chiến lược không lặp nonce dưới cùng key cho multi-instance?
15. HMAC/KEK test không yêu cầu xuất secret trái policy?
16. Test payload dùng dữ liệu giả, không lấy production secrets?
17. Test kết quả không log raw keys, PRK hoặc shared secrets?
18. Key owner/custodian/approver được xác định rõ?
19. IAM/KMS key policy/grants có nguyên tắc least privilege và SoD?
20. Decrypt/Unwrap/Sign/Derive/Export được tách quyền phù hợp?
21. Có đối soát effective access, quyền gián tiếp và cross-account?
22. Có phân biệt KMS encryption context với AAD và business authorization?
23. Key inventory chứa metadata/approval/evidence refs nhưng không raw key?
24. Lifecycle state và cryptoperiod có được đặt trước activation?
25. Key đã được bật từ provider có bị chặn usage đến khi nghiệm thu xong?
26. Có rotation, revocation, emergency disable và destruction policy?
27. Có kế hoạch recovery phù hợp loại key, không backup ephemeral keys vô cớ?
28. Có test restore với KEK/version/context cho dữ liệu dài hạn?
29. Có evidence từ source có thẩm quyền và xác minh integrity?
30. Kết quả thiếu evidence được ghi rõ, không tự PASS?
31. Validation failure có quarantine/regenerate/retest runbook?
32. Raw key/DEK/private key không được xuất để “kiểm tra” trái policy?
33. Có audit key creation, validation, approval và activation?
34. Có review các metadata security-sensitive như trust store/public fingerprint?
35. Có kiểm tra phiên bản/alias sau rotation?
36. Có chính sách xử lý nếu RNG yếu hoặc key material đã lộ?
37. Có kiểm tra không xóa KEK khi backup còn phụ thuộc?
38. Có monitoring quyền KMS/HSM, key state và usage drift?
39. Có phân quyền nghiệp vụ theo tenant/resource tách khỏi IAM key?
40. Có xác định giới hạn những gì PCT/functional tests **không** chứng minh?

## 23. Câu hỏi tự kiểm tra

**Câu 1.** `CreateKey=SUCCESS` có nghĩa key an toàn để dùng production chưa?

**Đáp án:** Chưa. Cần kiểm tra **key type, algorithm/params, origin, storage, exportability, IAM, usage, owner/custodian, lifecycle, functional consistency và evidence/approval**.

**Câu 2.** AES key dài 32 byte và AES-GCM round-trip thành công có chứng minh 256 bit entropy không?

**Đáp án:** Không. Key có thể sinh từ seed đoán được. Phải đánh giá **CSPRNG/provider/provenance**, không suy luận entropy từ độ dài hoặc phép thử.

**Câu 3.** PCT khác KAT ra sao?

**Đáp án:** PCT kiểm tra **cặp khóa mới** nhất quán; KAT so thuật toán/provider với **test vector đã biết**. Cả hai không chứng minh mọi thuộc tính bảo mật.

**Câu 4.** Tại sao không dùng `getEncoded()` để kiểm tra raw KEK trong HSM?

**Đáp án:** Key có thể non-exportable theo policy. Dùng **metadata/attestation và operation thử được phép** thay vì phá ranh giới bảo vệ.

**Câu 5.** Ed25519 signature Verify=true với public key do client gửi đã chứng minh danh tính chưa?

**Đáp án:** Chưa. Public key phải được ràng buộc với **trusted issuer/PKI/JWKS/registry** phù hợp.

**Câu 6.** Vì sao X25519 shared secret all-zero cần bị từ chối?

**Đáp án:** Đó là trạng thái không hợp lệ theo xử lý X25519/protocol; không nên dùng shared secret đó để dẫn xuất traffic key. Còn cần authenticated handshake.

**Câu 7.** Có thể dùng cùng nonce cố định cho tất cả AES-GCM test encrypt dưới một DEK không?

**Đáp án:** Không. **Nonce reuse dưới cùng GCM key** có thể phá bí mật và toàn vẹn, kể cả payload chỉ dùng trong thử nghiệm.

**Câu 8.** Vì sao test sửa authentication tag hoặc AAD?

**Đáp án:** Để xác minh Decrypt **fail closed** khi xác thực thất bại, không trả plaintext chưa xác thực.

**Câu 9.** KEK non-exportable có bảo đảm workload không lạm dụng Unwrap/Decrypt không?

**Đáp án:** Không. Workload có thể gọi API để nhận DEK/plaintext. Cần IAM least privilege, giám sát và business authorization.

**Câu 10.** PCT giữa private signer v4 và public key đăng ký v4 fail. Có nên thử mọi public key cho tới khi Verify được?

**Đáp án:** Không. Phải quarantine và điều tra **key reference, alias, format, challenge bytes và trusted public key mapping**.

**Câu 11.** Functional test KEK Wrap/Unwrap PASS có chứng minh backup lịch sử khôi phục được không?

**Đáp án:** Chưa. Cần bảo đảm **KEK/version, wrapped DEK, ciphertext, context, AAD/nonce/tag và recovery access** rồi thử restore có kiểm soát.

**Câu 12.** Key được tạo sai curve nhưng chưa dùng thì nên làm gì?

**Đáp án:** Không activation; **regenerate** đúng approved profile khi thuộc tính không sửa an toàn được, đồng thời lưu audit.

**Câu 13.** Nếu DEK sinh từ nguồn yếu và được wrap dưới KEK mạnh, DEK có đủ entropy không?

**Đáp án:** Không. Wrapping không tăng entropy của DEK. Nếu đã dùng để mã hóa, cần đánh giá rekey/re-encrypt.

**Câu 14.** Vì sao không backup mọi ephemeral session keys?

**Đáp án:** Backup có thể phá mục tiêu **xóa ephemeral secrets/forward secrecy**; recovery policy phải theo key purpose.

**Câu 15.** Một JSON validation tự khai `PASS` không có evidence có đủ không?

**Đáp án:** Không. Cần kiểm tra nguồn, thời điểm, scope, integrity, người phê duyệt và kết quả thao tác thật.

**Câu 16.** Kiểm tra sau generation có thay access review, rotation hoặc incident response không?

**Đáp án:** Không. Key attributes, IAM, alias, trust, cryptoperiod và dữ liệu phụ thuộc có thể thay đổi sau activation; cần giám sát và quản lý liên tục.

## 24. Kết luận

**Kiểm tra key sau generation là cổng chuyển từ khóa đã được tạo sang khóa được phép sử dụng trong một phạm vi có kiểm soát.** Một key cần đáp ứng **thuật toán và thuộc tính đúng, nguồn sinh đủ tin cậy, cặp khóa/primitive hoạt động nhất quán, IAM/key usage, key ID/version, owner/custodian, cryptoperiod, recovery và audit**.

Trong Java, JCA/JCE có thể minh họa **AES-GCM round-trip/tag rejection, Ed25519 pairwise consistency và X25519 agreement**, nhưng không thay thế **entropy/provenance assessment, HSM/KMS attestation, trust binding, IAM effective permissions và thiết kế key lifecycle**.

**Generation thành công là điểm khởi đầu; khóa chỉ sẵn sàng khi các điều kiện nghiệm thu đúng mục đích có bằng chứng và được phê duyệt.**
