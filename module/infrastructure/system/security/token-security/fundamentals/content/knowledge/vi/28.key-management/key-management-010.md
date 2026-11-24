# Backup và recovery key

## 1. Vì sao sao lưu khóa mật mã khó hơn sao lưu cơ sở dữ liệu?

Trong chương **Key management** của module **SECURITY_TOKEN_SECURITY_FUNDAMENTALS**, bài học này tập trung vào **backup và recovery key**: bảo vệ khả năng khôi phục việc ký, xác minh, mã hóa và giải mã token khi gặp mất thiết bị, hỏng hạ tầng hoặc sự cố vận hành, **mà không tạo thêm những bản sao bí mật dễ bị đánh cắp**.

Ví dụ: Authorization Server (AS) của Shop sử dụng private key **K1** để ký JWT access token; các Resource Server (RS) lấy public key từ JWKS để kiểm tra token. Một ngày, vùng dữ liệu chứa dịch vụ ký gặp sự cố.

~~~text
Authorization Server (region A) ----[KMS Sign K1]----> JWT access token
              |
              +----[JWKS: public K1]----> Orders API / Billing API

Region A gặp sự cố:
    Cần phát hành token mới ở region B.
    Cần duy trì khả năng xác minh token cũ hợp lệ.
    Không được khôi phục một K1 đã bị thu hồi vì compromise.
    Không được để backup chứa plaintext private key lộ cho nhiều người.
~~~

Nếu đội vận hành **không có cách khôi phục khả năng ký**, toàn bộ login hoặc token issuance có thể ngừng hoạt động. Nhưng nếu tạo file `private-key.pem` rồi lưu vào nhiều ổ đĩa, email và backup chung, đội vận hành đã **mở rộng bề mặt tấn công**: ai đọc được backup có thể sở hữu private key, giả token và phá vỡ mô hình tin cậy.

Điểm mấu chốt:

> **Key backup không phải sao chép bí mật càng nhiều càng tốt; đó là thiết kế khả năng phục hồi được giới hạn, kiểm soát, kiểm thử và bảo đảm khóa bị compromise không bao giờ được tin trở lại.**

### 1.1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Phân biệt **key availability**, **key confidentiality**, **key integrity**, **key provenance**, **rotation** và **revocation**.
2. Xác định loại khóa cần backup, loại chỉ cần tái tạo, và loại **không thể/không nên export**.
3. Phân biệt **public JWK**, **private signing key**, **HMAC secret**, **JWE encryption key**, **KEK/DEK**, **mTLS/DPoP client key** và secret của OAuth clients.
4. Thiết kế sao lưu bằng **KMS/HSM-native backup**, key wrapping, access control, separation of duties, dual control và threshold approval khi thích hợp.
5. Hiểu các tham số **RPO**, **RTO**, consistency của key registry, key version và trust metadata.
6. Khôi phục vùng/thiết bị mà không vô tình **hồi sinh khóa đã bị thu hồi** hoặc **làm mất khả năng giải mã dữ liệu lịch sử**.
7. Triển khai luồng Java/Spring minh họa cho encryption envelope, signing và recovery state.
8. Kiểm tra các tình huống restore thất bại, backup bị đánh cắp, key bị xóa vĩnh viễn và JWT/JWKS cache chưa đồng bộ.

## 2. Ba thuộc tính cần bảo vệ cùng lúc

Sao lưu khóa phải đáp ứng cả ba thuộc tính:

| Thuộc tính | Câu hỏi | Nếu sai |
|---|---|---|
| **Confidentiality** | Ai có thể đọc hoặc sử dụng key material, kể cả qua bản backup? | Attacker có thể ký token giả hoặc giải mã thông tin bí mật |
| **Integrity / provenance** | Khóa khôi phục có đúng key/version, mục đích, issuer và nguồn tin cậy? | Hệ thống có thể dùng key giả, key cũ, key thuộc issuer khác |
| **Availability / recoverability** | Khi KMS/HSM/region lỗi, có phục hồi dịch vụ trong mục tiêu đã định không? | Token issuance, login, giải mã dữ liệu hoặc xử lý nghiệp vụ có thể gián đoạn |

**Không có tính sẵn sàng bằng mọi giá.** Nếu private signing key K1 đã lộ, khôi phục từ backup rồi tiếp tục ký K1 để “khỏi downtime” là hành vi nguy hiểm, dù đạt RTO.

### 2.1. Bản sao khóa và khả năng sử dụng khóa là hai thứ khác nhau

Một hệ thống KMS/HSM có thể thiết kế khóa **non-exportable**. Khi đó:

- Ứng dụng **không thấy private key bytes**, chỉ gọi KMS `Sign`/`Decrypt`.
- Khả năng khôi phục có thể dựa trên **native HSM cluster replication/backup**, restore key handles, import key material theo policy, hoặc **chuyển sang khóa mới**.
- Backup có thể chứa **wrapped key material** chỉ mở được bằng HSM/kho khóa khác được kiểm soát, không phải PEM plaintext.
- Một region DR có thể dùng **key replica** hay key riêng theo dịch vụ của nhà cung cấp; tính năng cụ thể phải kiểm theo provider.

Ngược lại, **HMAC secret** hoặc private key phần mềm có thể nằm dạng bytes trong secret manager; trường hợp đó cần kiểm soát nhiều bản sao hơn.

### 2.2. Backup không tự động bằng replication

| Cơ chế | Mục tiêu | Giới hạn |
|---|---|---|
| **HA replication** | Dịch vụ tiếp tục khi một node hỏng | Lỗi thao tác xóa/compromise có thể lan sang replica |
| **Versioned backup** | Khôi phục trạng thái trước lỗi vận hành | Snapshot cũ có thể thiếu revocations mới |
| **Offline/immutable backup** | Chống sửa/xóa hàng loạt, ransomware | Nếu secret backup lộ vẫn gây compromise |
| **HSM/KMS-native recovery** | Phục hồi khả năng sử dụng key theo chính sách | Phụ thuộc key origin, exportability và giới hạn provider |
| **Key rotation** | Chuyển nghiệp vụ sang key mới | Không tự mở được ciphertext chỉ giải mã bằng key cũ |
| **Key revocation/distrust** | Ngừng chấp nhận key không đáng tin | Có thể làm JWT hợp lệ cũ bị từ chối; không phải thao tác restore |

Replication không thay backup có version/immutable policy; backup không thay một chiến lược HA có RTO ngắn.

## 3. Phân loại khóa trước khi quyết định backup

### 3.1. Cùng là “key” nhưng cần recovery khác nhau

| Loại khóa/secret | Thường dùng cho | Cần backup hay có thể cấp mới? | Hậu quả nếu mất |
|---|---|---|---|
| **AS/OP signing private key** | Ký JWT access/ID token | Phụ thuộc chính sách và khả năng chuyển ký sang key mới | Không ký tiếp bằng key cũ; token cũ vẫn có thể verify bằng public key |
| **Public JWK/JWKS** | RS/RP verify token | Có thể tái tạo từ public key/cert đáng tin; backup registry/version hữu ích | Verifiers có thể mất đường lấy key |
| **HMAC signing secret** | HS256/cookie/MAC | Cần bảo vệ như bí mật có khả năng mint/forgery | Mất thì không xác minh MAC cũ nếu secret không khôi phục |
| **JWE/private decryption key** | Giải mã token hoặc dữ liệu lưu trữ | Cần kế hoạch bảo tồn hoặc re-encrypt; rất quan trọng nếu ciphertext còn tồn tại | Có thể mất dữ liệu mã hóa không thể khôi phục |
| **KEK / wrapping key** | Bọc DEK hoặc private keys | Cực kỳ quan trọng với dữ liệu ciphertext còn cần sử dụng | DEKs bị bọc có thể không mở được |
| **DEK** | Mã hóa dữ liệu cụ thể | Thường được backup dưới dạng wrapped, không plaintext | Ciphertext tương ứng không giải mã được |
| **OAuth client secret** | Xác thực confidential client | Có thể rotate/cấp mới; cần kế hoạch triển khai đồng bộ | Client không xác thực được hoặc secret bị lộ |
| **Client `private_key_jwt` key** | Ký client assertion | Có thể cấp cặp key mới theo registration | Client auth gián đoạn nếu AS chưa tin key mới |
| **DPoP holder private key** | Proof-of-possession của client | Thường nên ràng buộc thiết bị, **không export** tùy platform | Client có thể cần cấp mới và reauthorize/rebind token |
| **mTLS private key** | Client auth/token binding | Có thể cấp chứng chỉ/key mới; HSM backup nếu yêu cầu | Client auth lỗi cho tới khi thay key/cert |
| **TLS server key** | Xác thực server | Có thể cấp cert/key mới, triển khai lại trust | Endpoint HTTPS có thể gián đoạn |
| **Opaque token DB reference/state** | Kiểm token qua lookup/introspection | Backup authoritative data/state phù hợp | Token hiện hữu có thể không được nhận, session/grant state mất |
| **Refresh token verifier/hash store** | AS kiểm refresh/rotation/family | Backup dữ liệu + security state an toàn | Không xác minh refresh hoặc có nguy cơ hồi sinh token đã revoke |

**Không có quy tắc “tất cả private keys đều phải export ra một file backup”.** Với khóa tạm thời hoặc device-bound, **cấp mới và yêu cầu reauthentication** có thể an toàn hơn cố khôi phục khóa.

### 3.2. Phân biệt signing và decryption khi mất key

**Signing key bị mất** khi private key chưa lộ: AS có thể tạo K2, phát token mới bằng K2, để RS kiểm token cũ bằng K1_public cho tới expiry theo **planned recovery policy**.

~~~text
K1_private bị mất, không bị nghi compromise:
    AS không ký token mới bằng K1.
    RS vẫn có K1_public và còn được tin.
    AS chuyển sang K2.
    Tokens K1 hợp lệ có thể tiếp tục được verify đến exp.
~~~

**Decryption key bị mất** là vấn đề khác:

~~~text
C1 = Encrypt(Kenc1, data).
Kenc1 bị mất vĩnh viễn.
Không còn bất kỳ copy/key recovery path hợp lệ.

=> Dữ liệu từ C1 có thể không thể giải mã.
~~~

Vì vậy với encryption-at-rest, key backup/recovery thường là một phần **bắt buộc của data durability plan**; với JWT signing ngắn hạn, lựa chọn cấp signer mới có thể phù hợp hơn.

### 3.3. Chỉ lưu public key không cho phép khôi phục khả năng ký

Public JWKS gồm `kty`, `n`, `e` hoặc tọa độ EC/OKP là dữ liệu xác minh. Nó không đủ để tái tạo private key:

~~~text
Public K1  -> xác minh chữ ký.
Private K1 -> tạo chữ ký.

Public K1 không thể "restore" Private K1 trong thuật toán an toàn.
~~~

Nếu tổ chức cần khôi phục **đúng private signing key**, phải dựa vào KMS/HSM-native recovery hoặc bản sao key được bảo vệ trước đó. Không mô tả việc tải JWKS public như một backup hoàn chỉnh cho signer.

## 4. Thiết kế mục tiêu recovery theo rủi ro

### 4.1. RPO và RTO cho key management

- **RPO (Recovery Point Objective):** thời điểm dữ liệu/trạng thái key registry, grants, revocations và metadata có thể bị mất tối đa khi khôi phục.
- **RTO (Recovery Time Objective):** khoảng thời gian tối đa mục tiêu để phục hồi khả năng phục vụ được yêu cầu (ký token, verify, decrypt...) sau sự cố.

Ví dụ nội bộ *minh họa*, không phải tiêu chuẩn bắt buộc:

~~~text
Issuer signing service:
    RTO = 15 phút.
    K1 private non-exportable, dùng KMS có DR replication.
    Nếu K1 unavailable, cho phép activate K2.

Encryption keys cho dữ liệu giao dịch:
    RPO = 0 đối với key-version mapping đã commit.
    Nếu mất mapping -> có thể không tìm được key để mở dữ liệu.

Security revocation state:
    Không chấp nhận mất sự kiện K1 COMPROMISED đã commit.
    Restore phải replay security tombstones trước khi online.
~~~

RPO “0” đòi hỏi kiến trúc đủ mạnh để thực hiện, không phải chỉ ghi vào runbook. Có thể cần transactionally consistent key metadata và durable replication.

### 4.2. Mục tiêu phục hồi theo chức năng

| Chức năng | Tính liên tục cần thiết | Phương án |
|---|---|---|
| **Verify JWT đã phát** | RS cần trust public key đang hợp lệ | Trusted JWKS cache/replica và security trust state |
| **Sign JWT mới** | AS cần signer hợp lệ | KMS failover hoặc key K2 đã phân phối public trước |
| **Decrypt JWE/dữ liệu cũ** | KMS cần đúng decryption key version | Wrapped key backup, retention đến hết ciphertext lifetime |
| **Refresh token** | AS cần grant/family store nhất quán | Backup DB, rotation/revocation replay |
| **Client assertion/mTLS** | AS/client phải đồng bộ key/cert mới | Dual-key overlap theo rotation policy |
| **Incident containment** | RS không được re-trust key lộ | Security epochs/tombstones tồn tại qua DR |

### 4.3. Xác định loại thảm họa

Không thiết kế recovery chỉ cho “một VM chết”. Cần xem:

1. Mất một instance AS hoặc RS.
2. Một Availability Zone/region KMS ngừng phục vụ.
3. Xóa nhầm key alias/metadata.
4. Xóa hẳn key material hoặc KMS scheduled deletion hoàn tất.
5. Ransomware/insider sửa backup, credential và trust registry.
6. Xâm nhập signing role nhưng key bytes không export.
7. Lộ private key trong backup cũ.
8. Cross-region replication đưa state ACTIVE cũ ghi đè REVOKED.
9. Restore dữ liệu ciphertext mà **không restore key version tương ứng**.
10. KMS/HSM vendor/service outage kéo dài.

Mỗi kịch bản có các recovery steps và blast radius khác nhau; một hướng dẫn chung “khôi phục file key” không giải quyết hết.

## 5. Mô hình envelope encryption: backup ciphertext và wrapped key

Với dữ liệu mã hóa, một cấu trúc phổ biến là **envelope encryption**:

~~~text
                               +-------------------+
                               | KMS/HSM: KEK K1   |
                               +---------+---------+
                                         |
                                         | Wrap DEK D1
                                         v
                                   Wrapped DEK W1

      Plaintext order record
                |
                v
   Random DEK D1 + AEAD Encrypt  ------> Ciphertext C1

 Backup artifact:
     ciphertext C1
     wrapped DEK W1
     key reference/version K1
     encryption algorithm/nonce/tag/metadata
     integrity/provenance metadata
~~~

**DEK (Data Encryption Key)** dùng để mã hóa dữ liệu. **KEK (Key Encryption Key)** dùng để bảo vệ DEK, thường qua KMS `Encrypt/Decrypt` hoặc `WrapKey/UnwrapKey` theo capability nhà cung cấp.

Nếu backup giữ `C1 + W1` nhưng **mất hoàn toàn K1**, dữ liệu có thể không đọc lại được. Nếu backup giữ DEK **plaintext**, người đọc backup có thể giải mã C1 mà không cần KMS: confidentiality thất bại.

### 5.1. Dữ liệu phải đi cùng metadata phiên bản

Ví dụ cấu trúc backup manifest minh họa:

~~~json
{
  "backup_id": "backup-2026-11-23T0300Z",
  "dataset": "orders-db",
  "encryption": {
    "content_algorithm": "AES-256-GCM",
    "key_reference": "kms://orders-prod/kek/v7",
    "wrapped_dek_format": "provider-defined",
    "dek_scope": "per-object-or-batch",
    "nonce_tag_stored_with_ciphertext": true
  },
  "snapshot": {
    "database_checkpoint": "orders-log-seq-1844",
    "key_registry_checkpoint": 1057,
    "security_policy_checkpoint": 2092
  },
  "integrity": {
    "manifest_signature_reference": "backup-signing-key-v3"
  }
}
~~~

Đây là schema nội bộ minh họa, **không phải chuẩn backup/KMS**. Manifest **không chứa plaintext DEK/KEK**, thông tin credentials hay material bí mật. `key_reference` phải được giải quyết từ registry đáng tin, không cho một manifest không xác minh chọn URL tùy ý để tải key.

### 5.2. Vì sao bản backup ciphertext phải lưu thông tin thuật toán?

Sau vài năm, hệ thống có thể đã chuyển từ encryption profile E1 sang E2. Nếu chỉ lưu ciphertext mà quên:

- Algorithm/key mode/profile.
- Version của key và wrapped DEK.
- Nonce/IV, authentication tag và associated data đúng profile.
- Encoding/format/schema và encryption context.

thì recovery có thể **không giải mã được** dù key material còn nguyên. Metadata cần có integrity/authenticity để tránh attacker thay key reference hoặc algorithm rồi gây lỗi/đánh cắp dữ liệu.

### 5.3. Nonce/IV không phải secret nhưng phải đúng

Với AEAD như AES-GCM, nonce thường không cần giữ bí mật nhưng phải tuân thủ yêu cầu **không tái sử dụng nonce dưới cùng key** cho các lần mã hóa riêng biệt. Khi restore backup, đừng reset counter/nonce generator khiến DEK D1 và nonce cũ bị sử dụng lại trong encryption traffic mới.

Phương án an toàn có thể là **fresh random DEK** cho mỗi object/batch phù hợp thiết kế, nonce sinh đúng chuẩn của crypto library và lưu kèm ciphertext. Tuyệt đối không tự viết AES hoặc dùng ECB để “dễ backup”.

### 5.4. Rewrap và re-encrypt khác nhau

**Rewrap:** DEK giữ nguyên, chỉ thay KEK bảo vệ nó.

~~~text
W1 = Wrap(KEK1, DEK1)
W2 = Wrap(KEK2, DEK1)

Ciphertext C1 = Encrypt(DEK1, data) không đổi.
~~~

**Re-encrypt:** nội dung được giải mã và mã hóa lại bằng DEK hoặc thuật toán mới.

~~~text
data = Decrypt(DEK1, C1)
C2 = Encrypt(DEK2, data)
~~~

Rewrap thường có chi phí thấp hơn re-encrypt dữ liệu lớn, nhưng nếu **DEK1 cũng bị lộ**, chỉ rewrap DEK1 bằng KEK2 **không bảo vệ được dữ liệu trước attacker đã có DEK1**. Khi đó có thể cần re-encrypt bằng DEK2 và đánh giá dữ liệu đã lộ.

### 5.5. Không để recovery script xuất plaintext key ra log

Sai:

~~~text
restore.sh:
    echo "Restored DEK = <SENSITIVE_MATERIAL>"
    print all KMS decrypt response
    write keys to world-readable temp directory
~~~

Đúng hướng:

- Dùng KMS/HSM/secret-manager APIs và SDK có kiểm soát.
- Tránh debug logging, traces chứa request/response bí mật.
- Tối thiểu hóa thời gian key material ở memory nếu buộc phải có.
- Hạn chế temporary files, core dumps và swap khi thích hợp.
- Truy cập theo workload identity, phân quyền và audit.
- Xóa/retire key copies không còn cần thiết theo policy, **không tự khẳng định secure erase vật lý** trên mọi ổ/backup cloud.

## 6. KMS/HSM-native backup và khả năng restore

**KMS/HSM thường có chính sách export/replication/backup riêng**, không phải cứ là key management service thì `exportPrivateKey()` luôn tồn tại.

### 6.1. Non-exportable key và recovery options

| Mô hình | Cách khôi phục khả thi | Lưu ý |
|---|---|---|
| **Cloud KMS managed non-exportable key** | Provider-managed redundancy, multi-region key replication hoặc chuyển sang key mới | Xác minh hỗ trợ theo key origin, loại key, region và service |
| **HSM cluster** | Vendor-approved secure backup/restore, backup HSM, quorum/unseal workflow | Có thể cần thiết bị/firmware/quorum tương thích |
| **Imported key material** | Restore/import lại key material theo hợp đồng KMS | Cần backup wrapped/import material an toàn từ trước; quản lý expiration |
| **Software private key trong vault** | Encrypted versioned backup của vault + master unseal/recovery design | Mất master key có thể mất toàn bộ secret vault |
| **Ephemeral session/DPoP key** | Tạo cặp key mới, rebind/re-authorize | Xuất/backup private key có thể phá device-binding security model |
| **Public JWKS** | Khôi phục trusted public key registry/issuer metadata | Chỉ verify được; không lấy lại private key từ JWKS |

**Không hứa “khôi phục cùng key identifier/private material” nếu provider chỉ cho tạo một key mới.** Khi tạo key mới, phải cập nhật issuer/JWKS/cert trust, token issuance và ciphertext re-encryption/rekey khi liên quan.

### 6.2. Backup cần thiết ngay cả khi HSM có HA?

HSM HA giúp sống sót khi node hỏng, nhưng không nhất thiết bảo vệ khỏi:

- Người có thẩm quyền xóa key ở cả cluster.
- Sai key policy được triển khai đồng loạt.
- Key replication mang theo trạng thái xóa lỗi.
- Corruption/version mismatch của metadata.
- Vùng dữ liệu/thiết bị/administrator domain cùng mất.
- Ransomware chiếm quyền control plane.

Thiết kế thường cần **HA + tamper-resistant backup + offsite/isolated recovery path**, nhưng phải tính threat model: backup private key ngoài HSM có thể **tăng** rủi ro. Nếu provider-native HSM backup đủ và không cho export, **không tạo bản PEM thủ công để “dự phòng”**.

### 6.3. Dual control và separation of duties

Một operator không nên có toàn bộ các quyền:

~~~text
Create/export private key
Modify backup access policy
Download backup
Disable audit
Restore key as ACTIVE
Publish trusted JWKS
~~~

Có thể tách:

| Vai trò | Quyền điển hình |
|---|---|
| **Key Custodian** | Quản lý lifecycle dưới phê duyệt; không tự đọc dữ liệu nghiệp vụ |
| **Backup Operator** | Chạy backup/restore job qua workload identity, không đọc plaintext key |
| **Security Approver** | Phê duyệt emergency restore và key-trust changes |
| **Service Signer** | Được dùng key cụ thể cho `Sign`, không export/disable/publish |
| **Auditor** | Xem logs và trạng thái; không thay key material |
| **RS Verifier** | Chỉ có public trust information; không có quyền ký |

Các quyền thực tế phụ thuộc nền tảng, nhưng nguyên tắc là **least privilege** và khả năng kiểm soát thay đổi mà không giao toàn quyền cho một actor.

### 6.4. Threshold approval và Shamir Secret Sharing

Trong một số quy trình HSM/unseal, có thể dùng **M-of-N quorum**: cần sự chấp thuận hoặc các key shares từ ít nhất M trong N custodians.

~~~text
Ví dụ 3-of-5:
    5 custodians giữ các shares độc lập.
    Ít nhất 3 custodians phải tham gia nghi thức được phê duyệt.
    1 hoặc 2 shares đơn lẻ không đủ phục hồi bí mật.
~~~

**Không tự triển khai Shamir Secret Sharing bằng code ứng dụng cho production.** Nếu có nhu cầu, ưu tiên cơ chế được provider/HSM/vault hỗ trợ và đánh giá về authenticity, share provenance, storage, tampering và kinh nghiệm vận hành. Threshold chỉ giải quyết **một nhóm rủi ro**: nếu attacker chiếm được quorum hoặc HSM signer API, vẫn có thể xảy ra compromise.

Quorum không thay **backup testing**: nếu các shares đã lỗi/hết khả dụng hoặc không tương thích HSM mới, recovery sẽ thất bại.

### 6.5. Key wrapping trong backup

Một cấu trúc đáng tin có thể là:

~~~text
K1_private key material (trong HSM A)
    |
    | HSM-native protected export / wrapping theo policy
    v
Encrypted backup blob B1
    |
    +--> Offsite immutable storage
    +--> Audit và retention
    |
Recovery:
    Approved quorum
        -> compatible HSM B
        -> authenticated import/unwrap
        -> key usage restrictions re-applied
        -> verification tests trước khi activate
~~~

**Cần xác minh cơ chế wrapping có được phép/được hỗ trợ**. Không giả định wrapped blob B1 an toàn nếu wrapping key/master backup nằm cùng bucket mà cùng người có thể đọc cả hai.

### 6.6. Kiểm tra nguồn và tính toàn vẹn bản backup

Nếu attacker thay một backup key hoặc manifest bằng public/private key của họ, hệ thống restore có thể vô tình cho key giả vào trust root. Do đó:

- Backup artifacts được mã hóa khi cần và **xác thực tính toàn vẹn**.
- Manifest có nguồn ký/attestation đáng tin phù hợp.
- Key identity/fingerprint, purpose, issuer, algorithm và version được kiểm trước activate.
- Recovery environment và bootstrap trust **không lấy khóa xác minh manifest từ chính manifest chưa tin**.
- Mọi thao tác restore có audit, phê duyệt và rollback/quarantine an toàn.

Đừng tin checksum không ký lấy từ cùng bucket có thể bị attacker sửa là đủ chống malicious substitution; checksum hữu ích phát hiện lỗi bit, **không nhất thiết chứng minh nguồn gốc**.

## 7. Key registry và versioning là thành phần của backup

Key material một mình có thể vô dụng nếu không biết:

~~~text
issuer / tenant / environment / owner
key purpose: JWT_SIGN, JWE_DECRYPT, DEK_WRAP, CLIENT_AUTH...
algorithm và key type
key ID / public fingerprint
createdAt / activatedAt / retiredAt / expiresAt
KMS/HSM key reference, key version
public JWKS publication state
who may use key for Sign/Decrypt
revocation/compromise status
security policy generation
ciphertext references và retention horizon
~~~

### 7.1. Vì sao không restore metadata kiểu “last write wins”?

~~~text
10:00  Key K1 ACTIVE, security_version=11.
10:10  Security đánh dấu K1 COMPROMISED, version=12.
10:12  AS/RS đã chặn K1.
10:15  DR restore snapshot 09:55, K1 ACTIVE version=11.
~~~

Nếu code restore ghi đè version=12 bằng version=11, key đã bị đánh cắp **được tin trở lại**. Đây là lỗ hổng **security state resurrection**.

**Bất biến:** một key material đã được đánh dấu compromised/revoked theo nguồn authoritative **không trở lại trusted chỉ nhờ backup cũ**. Có thể tạo key mới và chạy reauthorization/rotation hợp lệ, nhưng không tự mở lại K1.

### 7.2. Backup checkpoint cho dữ liệu và key registry

Ví dụ:

~~~text
DB data snapshot       at LSN 5100
Key registry snapshot  at version 110
Security deny state    at version 118

Disaster recovery:
    restore data + key metadata
    replay security events 111..118
    ensure no key/grant tombstones lost
    only then mark service READY
~~~

Các checkpoint phải được thiết kế phù hợp database/event bus thật; không giả định ba snapshots độc lập cùng thời gian sẽ tự tạo một transaction nhất quán. Có thể cần consistent snapshots, write-ahead log hoặc authoritative recovery journal.

### 7.3. Không xóa key cũ khi còn ciphertext phụ thuộc vào nó

Trước khi retire/delete KEK hoặc DEK cần tra:

- Bao nhiêu ciphertext/data backups còn dùng key version đó?
- Retention/legal hold của dữ liệu bao lâu?
- Đã rewrap/re-encrypt toàn bộ thành công và được kiểm chứng chưa?
- Có offline archives, analytics snapshots, replicas hay disaster copies chưa chuyển?
- Có dữ liệu chỉ mở được bằng key đó mà vẫn cần khôi phục sau nhiều năm?

**Key lifetime và data lifetime không luôn bằng nhau.** Với encryption key, xóa key quá sớm có thể làm mất dữ liệu không thể phục hồi, cho dù backup database đầy đủ.

### 7.4. Cảnh báo: key deletion đôi khi không thể đảo ngược

Một số KMS có thời gian chờ xóa, một số key material khi xóa hẳn **không thể khôi phục**; behavior phụ thuộc provider và key origin. Không viết runbook “cứ chạy delete rồi restore nếu cần” khi không có guarantee từ provider.

Với signing key, không nên xóa K1_private trước khi hiểu khả năng rollback/issuance; nhưng nếu compromised, **không giữ K1 trusted** chỉ để có đường rollback tiện lợi.

## 8. Quy trình phục hồi signing key khi KMS/HSM hoặc region mất khả dụng

Giả sử K1 là private signing key JWT của AS, được giữ trong một KMS ở region A. Sự cố làm region A không còn phục vụ ký.

### 8.1. Không có dấu hiệu compromise: ưu tiên tính liên tục có kiểm soát

Hai chiến lược:

**A. Khôi phục cùng signing key K1** thông qua native HSM/KMS HA hoặc một replica được cấp quyền trước, nếu nhà cung cấp cho phép và key material vẫn đáng tin.

**B. Chuyển sang key K2 mới** khi K1 không thể sử dụng, sau khi publish K2 public và bảo đảm RS/RP biết key mới.

~~~mermaid
sequenceDiagram
    participant O as Incident / DR Operator
    participant AS as Authorization Server
    participant R as Key Registry
    participant K as KMS Region B
    participant J as JWKS Service
    participant S as Resource Servers
    O->>R: Kiểm tra K1 status và recovery policy
    R-->>O: K1 unavailable, NOT compromised
    O->>K: Dùng recovered K1 nếu hỗ trợ, hoặc tạo K2 mới
    K-->>R: Key reference + public fingerprint
    R->>J: Publish trusted public key theo version
    J-->>S: RS tải/cập nhật trusted JWKS
    O->>AS: Cho phép signer được phê duyệt ở region B
    AS->>K: Sign access token
    K-->>AS: Signature
    AS-->>S: JWT từ key hợp lệ
    S->>S: Verify issuer, aud, alg, key trust, exp, policy
~~~

Nếu phải tạo K2, **đừng bắt đầu ký bằng K2 trong khi mọi RS còn chỉ biết K1**, trừ khi có failover/introspection strategy được phê duyệt. Có thể dẫn đến token mới hợp lệ nhưng API trả 401 vì chưa nhận public K2.

### 8.2. Token ký bằng K1 cũ có còn hợp lệ?

Nếu K1 không bị compromise và chính sách vẫn cho phép:

~~~text
K1_private unavailable:  AS không ký mới bằng K1.
K1_public trusted:       RS có thể tiếp tục verify JWT K1 cũ.
Token exp:              RS phải từ chối khi đã hết hạn.
Business authorization: tiếp tục kiểm resource/action/tenant.
~~~

**Không cần** restore private K1 chỉ để verify những token đã ký: public K1 có thể đủ. Điều này giúp giảm nhu cầu sao chép private signing material ra nhiều nơi.

### 8.3. Nếu private K1 bị mất vĩnh viễn

Nếu K1 ký JWT access tokens ngắn hạn nhưng không bảo vệ dữ liệu cần giải mã, có thể:

1. Tạo K2 mới.
2. Publish K2 public đúng issuer/algorithm.
3. Chuyển issuance sang K2.
4. Giữ public K1 cho đến lúc những JWT K1 hợp lệ cũ hết hạn, nếu không nghi lộ.
5. Thu hồi/từ chối tokens K1 sớm theo policy nếu cần.

Không tự kết luận user database, refresh grant store hay các KEK/JWE keys cũng mất chỉ vì K1_private mất; chúng có thể độc lập.

### 8.4. Nếu nghi compromise: tuyệt đối không coi backup K1 là phương án phục hồi trust

Một backup K1 từ tuần trước chứa **cùng private key K1**. Dù backup được tạo trước khi bị lộ, khôi phục nó không làm attacker mất bản copy.

~~~text
K1 compromised
    -> Stop Sign K1
    -> Emergency distrust K1 at RS/RP
    -> Create genuinely new K2
    -> Migrate sessions/grants according to policy
    -> Do not use "older K1 backup" as trusted recovery key
~~~

Một backup cryptographically intact chỉ chứng minh **bytes không đổi**; không chứng minh bí mật vẫn an toàn sau khi đã được sao chép ra ngoài.

### 8.5. Điều kiện cho failover issuer

Nếu chuyển AS sang region B, phải kiểm:

- **Issuer identifier `iss`** có còn đúng theo token contract? Không tự đổi `iss` chỉ vì host/region đổi.
- JWKS metadata/`jwks_uri` được duy trì từ nguồn tin cậy.
- Signing algorithm, `kid`, `typ` và token profile tương thích.
- Audience/scope/client registration/grant state được khôi phục nhất quán.
- KMS key policy ở B không cấp quyền Sign cho principal trái phép.
- Event/revocation/security epochs được đồng bộ trước khi B nhận token issuance.
- Các RPs/RS trong nhiều region có đường tới trusted public key/trust state.

**Issuer và region không phải luôn cùng khái niệm.** Việc thay issuer có thể yêu cầu đăng ký trust mới ở các clients/RS, không chỉ sửa DNS.

## 9. Key recovery cho dữ liệu mã hóa: sống còn của ciphertext

JWT signing key có thể cấp mới, nhưng data encryption key bị mất có thể làm dữ liệu không thể đọc. Trong hệ thống có orders, invoices, PII hoặc secrets mã hóa lâu dài, backup cần bao phủ **toàn bộ chuỗi mở khóa**.

### 9.1. Chuỗi phụ thuộc khóa

~~~text
Root / HSM master recovery secret
                |
                v
          KEK version K7
                |
          unwrap DEK D101
                |
        decrypt data backup C101
                |
             Plaintext
~~~

Nếu thiếu **bất cứ thành phần không thể thay thế** nào, việc có backup ciphertext không bảo đảm recoverability.

Ví dụ:

| Bản backup có | Thiếu | Hệ quả |
|---|---|---|
| DB snapshot `C101` | DEK/KEK mapping | Không biết dùng khóa nào hoặc không giải mã được |
| Wrapped DEK `W101` | KEK K7 và không có recovery path | Không unwrap được D101 |
| KEK K7 | Authentication tag/nonce của C101 | Decrypt/verification thất bại |
| C101 + W101 + K7 | Encryption context/AAD cần thiết | AEAD authentication có thể thất bại |
| C101 + tất cả keys | DB schema/index version cần thiết | Data parsing/application recovery có thể thất bại |

### 9.2. Restore phải xác minh tính toàn vẹn, không chỉ “decrypt được”

Nếu dùng AEAD đúng cách, việc decrypt xác minh tag cho biết ciphertext/AAD không bị sửa theo key/profile đó. Nhưng **không thay**:

- Backup artifact integrity/provenance.
- Key registry trust.
- Data snapshot consistency.
- Authorization policy về ai được phục hồi/đọc plaintext.
- Anti-rollback của bản ghi nghiệp vụ và security state.

Một backup đã bị attacker sửa **trước khi mã hóa/tạo signature** có thể vẫn decrypt được; phải có audit và nguồn dữ liệu tin cậy.

### 9.3. Key version retention

Nếu có các ciphertext:

~~~text
Orders 2024 -> KEK v3
Orders 2025 -> KEK v5
Orders 2026 -> KEK v7
~~~

thì xóa KEK v3 chỉ vì đã có v7 là sai nếu **Orders 2024 vẫn cần khôi phục**. Cần một **key dependency inventory** liên kết key version với những dữ liệu/backups phụ thuộc.

Có thể chủ động rewrap/re-encrypt để retire key cũ, nhưng phải kiểm:

1. Mọi object/archive đã được xử lý chưa?
2. Ciphertext cũ còn ở cold storage/DR?
3. Kết quả decrypt ở key mới đã được kiểm?
4. Thời gian retention/legal hold đã hết?
5. Có cần chứng minh cryptographic erasure cho dữ liệu cũ?

### 9.4. Cryptographic erasure và backup recovery có thể xung đột

**Cryptographic erasure** có thể chủ động hủy khả năng giải mã dữ liệu bằng cách hủy key material cần thiết. Nếu tổ chức vừa hứa xóa dữ liệu bằng hủy key, vừa giữ **bản backup giải mã được vô thời hạn**, hai cam kết có thể mâu thuẫn.

Cần xác định:

- Keys/backups nào phải bị hủy để đáp ứng chính sách xóa dữ liệu.
- Những key nào phải giữ vì legal hold/retention.
- Khả năng khôi phục có bị hạn chế sau deletion deadline.
- Kiểm chứng deletion policy có áp cả backup/replica/archive.

Không coi xóa một key alias hoặc entry trong key registry là xóa vĩnh viễn nếu vật liệu khóa vẫn có bản sao giải mã được.

### 9.5. Recovery test không nhất thiết cần dữ liệu production

Dùng **synthetic ciphertext fixture** mã hóa bằng key test/policy giống production, rồi:

1. Backup manifest + wrapped DEK + ciphertext.
2. Chuyển sang isolated DR environment.
3. Kiểm quorum/identity/permission.
4. Unwrap/decrypt và xác minh tags/expected digest.
5. Kiểm key version và audit events.
6. Bảo đảm không xuất plaintext/DEK vào logs.

Nếu cần diễn tập với dữ liệu thực, phải có authorization, masking và data handling controls tương xứng, không mặc nhiên xuất production plaintext ra laptop cá nhân.

## 10. Backup cho OAuth grant, opaque token và refresh token state

Phạm vi module không chỉ có JWT signing. AS còn lưu các **authorization grants, refresh-token rotations, token families, user sessions và revocation status**.

### 10.1. Tại sao restore token store cũ có thể gây lỗ hổng?

~~~text
10:00  Refresh token R1 ACTIVE.
10:05  Alice dùng R1, AS phát R2 và đánh dấu R1 USED.
10:06  Security phát hiện reuse, revoke cả family F1.
10:10  AS DR restore backup từ 09:59.
        Family F1 lại ACTIVE; R1 chưa từng USED trong snapshot.
~~~

Nếu AS cho refresh từ R1 sau restore, hệ thống đã **hồi sinh credential đáng lẽ không hợp lệ**. Không chỉ mất tính nhất quán: đó là **security rollback**.

### 10.2. Cần backup những dữ liệu state nào?

| Trạng thái | Lý do cần giữ/khôi phục |
|---|---|
| Client registrations và auth methods | Chặn cấp token cho client không hợp lệ |
| Authorization grant / subject / tenant bindings | Không tự cấp lại quyền từ snapshot quá hạn |
| Refresh-token family ACTIVE/USED/REVOKED | Không chấp nhận token đã rotation hoặc reuse |
| Revoked token IDs (`jti`) / denylist | Chặn JWT còn hạn đã bị thu hồi |
| Subject/session/client security epochs | Không hồi sinh phiên hoặc client bị khóa |
| Issuer signing-key trust status | Không nhận lại K1 đã COMPROMISED |
| Consent/authorization policy state | Không cấp quyền dựa vào consent/role đã bị rút |
| OIDC logout/session references | Không nhầm session cũ với session đang hoạt động |
| Audit/security event checkpoints | Phục hồi lịch sử và tái phát security events khi cần |

Điều này không có nghĩa **mọi bearer token phải được lưu plaintext**. Với opaque random tokens và refresh tokens, thường nên lưu **hash/HMAC verifier** thích hợp, mã hóa state nhạy cảm khi cần và bảo vệ backup ở mức database/secret management.

### 10.3. Restore theo checkpoint nhưng phải replay revocations

Một giải pháp:

~~~text
Backup snapshot at S100
        |
        v
Restore grants/session/key metadata
        |
        v
Replay authoritative journal events S101..S150
    - R1 USED
    - F1 REVOKED
    - User U3 DISABLED
    - Key K1 COMPROMISED
        |
        v
Verify security high-watermark >= S150
        |
        v
AS token endpoint enabled
~~~

**Không bật token issuance** nếu chưa biết nó sẽ không chấp nhận grants/refresh tokens từng bị revoke. Nếu không thể phục hồi trạng thái đáng tin, một phương án an toàn có thể là **invalidate grants/force reauthentication** trong phạm vi rủi ro thay vì fail-open bằng snapshot cũ.

### 10.4. Opaque access tokens và introspection sau restore

RS sử dụng introspection có thể đang cache `active=true` trong khi AS restore token store. Nếu AS sau restore trả trạng thái **cũ** hoặc thiếu entry, RS có thể không đồng nhất.

Phải quy định:

- Consistency của authoritative state sau recovery.
- Positive cache TTL/hard freshness bound.
- Invalidation event khi revoke/restore grants.
- Response khi AS không xác định được trạng thái (không tự `active=true`).
- Token expiry và audience validation không bị bỏ qua.

**HTTP 200 từ endpoint phục hồi hoặc `/revoke` không phải bằng chứng mọi Resource Server đã hội tụ.**

## 11. Multi-region recovery và các trạng thái không được ghi đè

Một AS có thể hoạt động tại region A (primary) và region B (DR). Key material và trust policy có thể được replication bằng những cơ chế **khác nhau**.

### 11.1. Đừng nhầm key replica với full disaster recovery

Một KMS key ở B có thể đã sẵn sàng ký, nhưng:

~~~text
KMS Region B:         K2 signing key AVAILABLE
AS Region B:          Token issuance service RUNNING
Grant DB Region B:    Replica chậm 3 phút
Revocation journal:   Chưa replay User U1 DISABLED
Client registrations: Chưa nhận client X SUSPENDED
RS Region B:          JWKS có K2 nhưng policy vẫn cũ
~~~

**Không thể coi region B đã an toàn** chỉ vì KMS trả chữ ký thành công. Issuance và verification phải dựa trên **grant/client/subject/trust state** đủ mới.

### 11.2. Một luồng DR an toàn

~~~mermaid
flowchart TD
    A[Region A unavailable] --> B[Incident authority xác định recovery mode]
    B --> C[Kiểm provenance và tình trạng key K1]
    C --> D{K1 trusted và recoverable?}
    D -- Có --> E[Activate permitted K1 replica theo chính sách]
    D -- Không hoặc compromised --> F[Create/activate genuinely new K2]
    E --> G[Restore metadata + replay security journal]
    F --> G
    G --> H{Key/grant/client revocation state đủ mới?}
    H -- Không --> I[Fail closed, reconcile hoặc force reauthorization]
    H -- Có --> J[Publish trusted JWKS + verify RS readiness]
    J --> K[Canary sign + token validation tests]
    K --> L{Issuer/audience/alg/policy đúng?}
    L -- Không --> I
    L -- Có --> M[Enable controlled traffic]
    M --> N[Monitor RTO, lag, key usage và incidents]
~~~

Một số bước có thể chạy song song, nhưng phải giữ bất biến: **không phát token từ grant đã bị revoke và không cho verifier re-trust key bị compromise**.

### 11.3. Multi-region key constraints phụ thuộc provider

Không giả định:

- Mọi KMS hỗ trợ **replicate cùng private key material** sang region khác.
- Imported keys có thể được clone/replicate như provider-managed keys.
- HSM cluster có thể restore mọi key type trên firmware/provider khác.
- `keyId`/ARN/alias giữ nguyên khi cross-region restore.
- Key được disable ở A sẽ tự disable ở B tức thì.
- KMS alias đổi nhưng mọi ứng dụng cache alias sẽ nhận ngay.

Runbook cần ghi rõ những khả năng **đã thử nghiệm trên provider thực** (key origin, algorithm, region, API, IAM, lifecycle). Nếu không có hỗ trợ phục hồi cùng key, chuẩn bị **new-key failover path**.

### 11.4. Region B không được ghi đè revocation trong region A

Ví dụ hai bản key registry:

~~~text
Region A:
    issuer=login.example.com
    key=K1
    securityVersion=32
    status=COMPROMISED

Region B stale:
    issuer=login.example.com
    key=K1
    securityVersion=31
    status=ACTIVE
~~~

Không sử dụng **last-write-wins dựa trên timestamp của hai máy** khiến status ACTIVE v31 ghi đè COMPROMISED v32. Dùng authoritative monotonically increasing policy version, durable tombstone, conflict resolution an toàn và fail closed khi state chưa đủ mới.

### 11.5. Cách khôi phục các token hợp lệ cũ

Một JWT ký bằng K1 có thể vẫn hợp lệ khi private K1 bị mất nhưng **không compromise**:

~~~text
RS:
    vẫn cần K1_public để verify JWT K1 trong thời gian còn hạn.
    vẫn phải kiểm issuer, aud, exp, nbf, typ, alg, scope.
    vẫn phải kiểm quyền resource/action/tenant.

AS:
    nếu không có K1_private, phát token mới bằng K2.
~~~

Nếu K1 đã COMPROMISED, **không tiếp tục tin K1 để tránh lỗi login**, trừ khi một risk decision đặc biệt cho phép trong giới hạn được kiểm soát—mặc định emergency là distrust và chấp nhận tác động người dùng cần reauthentication.

### 11.6. JWKS service cũng cần khôi phục

Nếu JWKS endpoint/JWKS metadata bị hỏng hoặc mất:

1. Phục hồi cấu hình issuer và public JWKS từ **registry đáng tin**.
2. Kiểm key fingerprints, key use, algorithm, issuer và policy versions.
3. Không tự động công bố public key của signing key đã bị COMPROMISED.
4. Duy trì tương thích với token còn hạn khi key vẫn trusted.
5. Quản lý CDN/cache headers và invalidation khi emergency.
6. Kiểm các RS/RP verifiers đã cập nhật; không đánh đồng JWKS HTTP 200 với verifier readiness.

Public JWKS không chứa private signing key; việc khôi phục website JWKS và khả năng **ký** JWT là hai công việc khác nhau.

## 12. Recovery và trust: phân biệt key loss với key compromise

Hai sự cố có thể cùng biểu hiện “AS không ký được” nhưng phương án đúng khác hẳn:

| Vấn đề | Mô hình tin cậy | Phương án điển hình |
|---|---|---|
| **HSM tạm offline, key không lộ** | K1 vẫn trusted | Failover K1 hoặc chuyển K2; giữ K1 public khi cần verify |
| **Private key bị xóa vĩnh viễn, không lộ** | K1 public vẫn có thể trusted | Sinh K2 mới; tùy token TTL và dữ liệu encryption |
| **Private signing K1 bị lộ** | K1 không còn đáng tin | Disable signer + distrust K1 ở mọi RS/RP + K2 mới |
| **KMS Sign permission bị attacker chiếm** | Signing capability bị mất kiểm soát | Thu hồi IAM, điều tra chữ ký, cân nhắc distrust/rotate |
| **JWKS publisher bị chiếm** | Public trust source bị xâm nhập | Khôi phục trust registry, loại khóa giả, validate clients |
| **Decryption KEK bị mất** | Dữ liệu có thể không giải mã được | Restore compatible secure KEK hoặc re-encrypt trước khi key mất |
| **Decryption KEK bị lộ** | Confidentiality của dữ liệu có thể mất | Rotate, rewrap/re-encrypt khi cần, điều tra dữ liệu đã bị lộ |

### 12.1. Khôi phục bản backup K1 cũ sau compromise không xóa hậu quả

~~~text
T0: Backup K1 được tạo, hoàn toàn intact.
T1: K1_private bị attacker copy.
T2: Security biết K1 compromised.
T3: Operator restore backup từ T0.
~~~

**K1_private tại T3 vẫn là cùng vật liệu mà attacker đã có.** Không có khái niệm “phiên bản private key trước khi bị lộ” làm attacker mất quyền ký. Chỉ key mới, security controls mới và distrust cũ mới giảm khả năng forge tiếp.

### 12.2. Backup độc lập khỏi signing capability bị chiếm

Nếu cùng IAM role có quyền:

~~~text
KMS:Sign(K1)
Backup:GetObject(all private key archives)
KMS:Decrypt(all wrapped key backups)
KeyRegistry:MarkTrusted(any key)
~~~

attacker chiếm role đó có thể thao túng toàn bộ recovery path. Phải tách **signing workload**, **backup storage**, **restore approval**, **key registry publication** và **audit controls**.

### 12.3. Không “fail open” khi không xác minh được key trust

Một RS startup chưa lấy được current key trust policy:

~~~text
Local snapshot: K1 ACTIVE v11.
Authoritative policy: UNKNOWN vì network partition.
~~~

Nếu action nhạy cảm yêu cầu freshness tối đa 30 giây nhưng snapshot đã 5 phút, RS không nên ALLOW JWT K1 theo snapshot này. Có thể:

- Truy vấn nguồn state khác đáng tin.
- Chỉ tiếp tục phục vụ public endpoints không yêu cầu token.
- Trả lỗi tạm thời/fail closed cho API nhạy cảm.
- Cô lập traffic tới region chưa hội tụ.

Hành vi phải được định nghĩa trước theo threat model. Không tự biến “không thể kiểm trạng thái” thành “khóa chắc chắn còn đáng tin”.

## 13. Key shares, restore credentials và backup bootstrap

Một rủi ro khó nhận thấy là **vòng phụ thuộc vòng tròn**:

~~~text
Backup key material nằm trong encrypted object storage.
Key giải mã backup nằm trong secret vault.
Secret vault chỉ mở được bằng KMS đang hỏng.
KMS recovery credentials lại lưu trong cùng secret vault.
~~~

Trong thực tế, không thể phục hồi vì mọi bước phụ thuộc hệ thống đang mất.

### 13.1. Thiết kế recovery chain không vòng lặp

Một kế hoạch cần tài liệu hóa:

- Recovery authority và identity khi primary IdP unavailable.
- Secure offline/quorum credential để mở recovery environment.
- HSM/KMS backup key hoặc vendor-native recovery path.
- Key registry trust anchor/public verification material cho backup manifests.
- Network/host/firmware/region prerequisites.
- Cách xác thực restore operators và ghi audit khi security infrastructure suy giảm.

Một mô hình:

~~~text
Quorum / privileged recovery identities
          |
          v
Isolated recovery KMS/HSM
          |
          +--> Unwrap/restore required keys
          |
          +--> Verify signed backup manifest
          |
          +--> Restore service metadata/state
          |
          +--> Reconcile security tombstones
          |
          v
Production service readiness
~~~

Không lưu toàn bộ yếu tố **quorum recovery** trong cùng một password manager/account có khả năng bị chiếm đồng thời. Lựa chọn kỹ thuật cụ thể cần cân bằng số người, khả năng mất share và quy trình hoạt động khi thiên tai.

### 13.2. Recovery credentials cũng cần rotation và kiểm thử

Những credentials cho restore lâu không dùng có nguy cơ:

- Hết hạn/mất người giữ.
- Được cấp quyền sai sau IAM migration.
- Tồn tại trong runbook plaintext.
- Đã bị copy, nhưng không có audit.
- Phụ thuộc thiết bị HSM/firmware không còn sẵn có.

Cần diễn tập **quorum** định kỳ, xác minh shares còn truy cập được và thử restore bằng cách an toàn; không cần trích xuất actual private production keys để kiểm toán đơn giản.

### 13.3. Recoverability không phải khả năng người vận hành nhìn thấy key bytes

Mục tiêu là **dịch vụ có thể tiếp tục thực hiện Sign/Decrypt hợp lệ**, không phải operator nhận được PEM của private key. Native HSM restore hoặc key-generation failover có thể đạt mục tiêu mà **không cần export plaintext key material**.

### 13.4. Quorum có thể hạn chế khôi phục trái phép

Ví dụ hai cấp phê duyệt:

~~~text
Backup restore request
    -> Backup Operator tạo request.
    -> Security Approver A xác thực incident/recovery target.
    -> Security Approver B xác nhận key fingerprint/purpose.
    -> HSM/KMS enforce quorum hoặc workflow được kiểm toán.
    -> Restore chỉ vào isolated DR environment.
    -> Key ACTIVE chỉ sau validation và approval.
~~~

Không dùng quy trình approval trên email làm biện pháp duy nhất nếu người có quyền cloud administrator vẫn có thể tải secret và bypass hoàn toàn mọi quy định; cần **technical enforcement** khi khả thi.

## 14. Backup metadata và secret handling trong OAuth/OIDC

Một OP/AS giữ nhiều secret ngoài issuer signing key:

- OIDC client secrets và token-endpoint authentication configuration.
- `private_key_jwt` client public registrations và mTLS trust chain.
- Refresh token hashes/family/grants.
- PKCE request state/authorization codes (thường ngắn hạn, không cần restore).
- Session/cookie signing hoặc encryption secrets.
- Token exchange policies, subject/actor mappings.
- Key trust/revocation lists và security events.

### 14.1. Không nên restore mọi ephemeral credential

Một **authorization code** được phát trong Authorization Code flow thường ngắn hạn và **single-use**. Khi AS crash, khôi phục những code cũ từ backup có thể tạo nguy cơ replay nếu trạng thái “đã dùng” không nhất quán.

Một chiến lược an toàn có thể là **làm mất hiệu lực các authorization codes/pending requests cũ**, yêu cầu client bắt đầu flow mới. Đây thường là tradeoff UX chấp nhận được để bảo vệ security invariants.

### 14.2. Refresh token cần đồng bộ với family status

Không tự khôi phục R1 về ACTIVE nếu nó đã USED/REVOKED. Nếu family state không thể tái tạo đủ tin cậy, **force reauthentication/re-consent khi cần** có thể an toàn hơn cho AS cấp token mới từ trạng thái thiếu.

### 14.3. Public OAuth client keys cũng là metadata quan trọng

Nếu `private_key_jwt` client đã rotate từ C1 sang C2 mà restore registration cũ chỉ có C1:

~~~text
Client đã chuyển C2_private.
AS DR chỉ tin C1_public.
=> Client C2 không thể xác thực.
~~~

Không khắc phục bằng cách vô điều kiện trust bất kỳ JWK client tự gửi trong request. Cần restore registration đúng version, trusted JWKS/client metadata và xác thực quy trình key rollover.

### 14.4. Backup của session cookie secrets

Một ứng dụng dùng signing/encryption secret cho session cookies có thể:

- Mất khả năng xác minh cookies cũ khi secret biến mất; user phải login lại.
- Có thể phải giữ secret cũ trong planned rotation cho tới khi sessions hết hạn.
- Nếu secret bị lộ, phải **ngừng tin** secret và invalidate sessions theo policy.

Không giữ compromised cookie secret chỉ để giảm số lần user đăng nhập lại, và không nhầm cookie/session recovery với JWT AS signing key recovery.

## 15. Java: envelope encryption và khôi phục dữ liệu với KMS

Phần này minh họa cách ứng dụng **mã hóa dữ liệu bằng DEK**, để **KMS bảo vệ DEK**. API của KMS thay đổi theo provider; dưới đây là **pseudocode kết hợp Java Cryptography Architecture (JCA)**, không phải implementation production hoàn chỉnh.

### 15.1. Luồng mã hóa

~~~java
// Pseudocode dùng các class ứng dụng chưa định nghĩa.
// KmsClient / EncryptedRecord / BackupStore là abstractions minh họa.
EncryptedRecord encryptRecord(
        byte[] plaintext,
        String recordId,
        KmsClient kms,
        SecureRandom random) throws Exception {

    // Một DEK AES-256 mới cho record hoặc nhóm record theo thiết kế.
    byte[] dek = new byte[32];
    random.nextBytes(dek);

    // IV 96-bit cho AES-GCM. Phải bảo đảm không tái sử dụng
    // nonce với cùng key trong phạm vi sử dụng.
    byte[] iv = new byte[12];
    random.nextBytes(iv);

    byte[] aad = ("record:v1:" + recordId)
        .getBytes(StandardCharsets.UTF_8);

    try {
        Cipher cipher = Cipher.getInstance("AES/GCM/NoPadding");
        cipher.init(
            Cipher.ENCRYPT_MODE,
            new SecretKeySpec(dek, "AES"),
            new GCMParameterSpec(128, iv));
        cipher.updateAAD(aad);
        byte[] ciphertextAndTag = cipher.doFinal(plaintext);

        // KMS wrap/encrypt DEK bằng KEK có purpose/key version được policy cho phép.
        KmsWrappedKey wrapped = kms.wrapDataKey(
            "kms://orders-prod/kek/v7",
            dek,
            "orders-record:" + recordId);

        return new EncryptedRecord(
            recordId,
            "AES-256-GCM",
            "kms://orders-prod/kek/v7",
            wrapped.blob(),
            iv,
            ciphertextAndTag,
            1 // encryption schema version
        );
    } finally {
        Arrays.fill(dek, (byte) 0);
    }
}
~~~

Trong code thật, cần imports `java.security.SecureRandom`, `java.nio.charset.StandardCharsets`, `java.util.Arrays`, `javax.crypto.Cipher`, `javax.crypto.spec.SecretKeySpec`, `javax.crypto.spec.GCMParameterSpec` và các types ứng dụng. `SecureRandom` được khởi tạo qua một CSPRNG phù hợp runtime.

**Giới hạn cần nắm:**

- `KmsClient` là abstraction minh họa; mỗi KMS có cơ chế **GenerateDataKey, Encrypt/Decrypt hoặc Wrap/Unwrap** khác nhau và encryption context/AAD khác nhau.
- Nonce ngẫu nhiên 96-bit có xác suất collision tăng theo số lần mã hóa **với cùng key**; cần nonce strategy theo lượng traffic/profile. Dùng fresh DEK cho từng object giúp giới hạn phạm vi, nhưng vẫn phải thiết kế cẩn thận.
- Java `SecretKeySpec`, cipher/provider và heap có thể giữ bản sao DEK; `Arrays.fill` chỉ giảm rủi ro trong một buffer, **không bảo đảm xóa mọi bản sao khỏi memory**.
- Ciphertext cần lưu kèm IV, tag, wrapped DEK, key reference và schema/AAD version.
- Không ghi `plaintext`, `dek`, raw wrapped responses chứa metadata nhạy cảm vào logs.
- KMS wrap phải dùng **trusted key reference**, không lấy tùy ý từ input HTTP.

### 15.2. Recovery/decrypt

~~~java
// Pseudocode minh họa, record phải được xác thực/ủy quyền trước khi decrypt.
byte[] decryptRecord(
        EncryptedRecord record,
        AuthorizedRecoveryContext context,
        KmsClient kms) throws Exception {

    recoveryPolicy.requireCanDecrypt(
        context, record.recordId());
    keyRegistry.requireTrustedEncryptionKeyReference(
        record.kekReference(),
        record.schemaVersion());

    byte[] dek = kms.unwrapDataKey(
        record.kekReference(),
        record.wrappedDek(),
        "orders-record:" + record.recordId());

    try {
        Cipher cipher = Cipher.getInstance("AES/GCM/NoPadding");
        cipher.init(
            Cipher.DECRYPT_MODE,
            new SecretKeySpec(dek, "AES"),
            new GCMParameterSpec(128, record.iv()));
        cipher.updateAAD(
            ("record:v1:" + record.recordId())
                .getBytes(StandardCharsets.UTF_8));

        // GCM authentication phải PASS; nếu sai phải fail,
        // không trả về partial plaintext hoặc bỏ verify.
        return cipher.doFinal(record.ciphertextAndTag());
    } finally {
        Arrays.fill(dek, (byte) 0);
    }
}
~~~

**Quan trọng:** Trước khi gọi decrypt, user/service phải đủ quyền **theo action, resource và tenant**. Backup/recovery key không đồng nghĩa admin được đọc mọi plaintext; application authorization và các quy định dữ liệu vẫn phải áp dụng.

### 15.3. Không catch mọi lỗi crypto rồi trả dữ liệu mặc định

Sai:

~~~java
// SAI: không dùng trong hệ thống thật.
try {
    return decryptRecord(record);
} catch (Exception ignored) {
    return new byte[0]; // giả như plaintext rỗng hợp lệ
}
~~~

Nếu tag AEAD không hợp lệ, key mismatch hoặc backup bị sửa, phải **báo lỗi có kiểm soát**, audit category, không coi đó là một dữ liệu nghiệp vụ hợp lệ. Không log plaintext hoặc DEK để debug.

### 15.4. Test decryption sau recovery

Một kiểm thử tốt:

~~~text
Create synthetic plaintext fixture.
Encrypt bằng DEK D1 và KEK v7.
Backup C1 + wrapped DEK + IV/tag + manifest.
Restore trusted KEK v7/compatible HSM.
Decrypt C1 với đúng AAD.
Compare expected plaintext/test digest.
Thử sai key/version/AAD/tag -> phải FAIL.
~~~

**Không dùng dữ liệu production thật** trong demo/code sample; dùng test key/fixture và isolated DR environment.

## 16. Java/Spring Security: phục hồi issuer signing service

Một Java Authorization Server có thể ký JWT qua KMS/HSM hoặc một JOSE/JWT library nhận signing key. Nội dung này là **thiết kế phục hồi**, không khuyến khích tự viết JWS signing từ đầu.

### 16.1. Chọn signer đúng issuer và trạng thái

~~~java
// Pseudocode, KHÔNG phải API Spring Authorization Server có sẵn.
SignedAccessToken issueToken(
        VerifiedAuthorizationGrant grant,
        TrustedIssuer issuer,
        KeyRegistry keys,
        KmsSigner signer) {

    grantPolicy.requireActiveAndAllowed(grant);
    keyRecoveryPolicy.requireSecurityJournalFresh();

    SigningKeyRef key = keys.requireActiveSigner(
        issuer.id(),
        "JWT_ACCESS_TOKEN");

    keyRecoveryPolicy.requireNotCompromised(key);
    keyRecoveryPolicy.requireSigningAllowed(key, issuer);

    JwtClaims claims = claimFactory.buildBoundClaims(
        grant, issuer, clock.instant());

    return joseEncoder.signWithTrustedKms(
        claims,
        "at+jwt",
        issuer.allowedAlgorithm(),
        key,
        signer);
}
~~~

**Không bỏ kiểm grant** khi AS failover vì đã có KMS Sign ở region DR. Một key K2 hợp lệ có thể ký token sai quyền nếu grant/subject/client metadata chưa đồng bộ.

### 16.2. Key registry và Spring Resource Server

Resource Server thường xác minh JWT access token dựa trên issuer/JWKS:

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://login.example.com
~~~

Đây chỉ là cấu hình khởi điểm. Ứng dụng còn cần **expected audience validation**, token type/algorithm policy và business authorization, ngoài **security trust state** khi key compromise/DR xảy ra.

### 16.3. Custom validator cho khung bảo vệ bổ sung

~~~java
import org.springframework.security.oauth2.core.DelegatingOAuth2TokenValidator;
import org.springframework.security.oauth2.core.OAuth2Error;
import org.springframework.security.oauth2.core.OAuth2TokenValidator;
import org.springframework.security.oauth2.core.OAuth2TokenValidatorResult;
import org.springframework.security.oauth2.jose.jws.SignatureAlgorithm;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.jwt.JwtDecoder;
import org.springframework.security.oauth2.jwt.JwtValidators;
import org.springframework.security.oauth2.jwt.NimbusJwtDecoder;

// Pseudocode cấu hình gọn trong một @Configuration của Spring.
@Bean
JwtDecoder ordersJwtDecoder(EmergencyKeyTrustPolicy trust) {
    String issuer = "https://login.example.com";
    String jwks = "https://login.example.com/.well-known/jwks.json";

    NimbusJwtDecoder decoder = NimbusJwtDecoder
        .withJwkSetUri(jwks)
        .jwsAlgorithm(SignatureAlgorithm.RS256)
        .build();

    OAuth2TokenValidator<Jwt> audience = jwt -> {
        if (jwt.getAudience().contains("https://orders.example.com")) {
            return OAuth2TokenValidatorResult.success();
        }
        return OAuth2TokenValidatorResult.failure(
            new OAuth2Error("invalid_token", "Wrong audience", null));
    };

    OAuth2TokenValidator<Jwt> emergencyPolicy = jwt -> {
        // Đây là lớp phụ: trust state phải đến từ authoritative source.
        // Không chỉ block 'kid'; key resolver còn phải loại key material
        // K1 đã COMPROMISED, kể cả nếu có alias khác.
        if (!trust.isFreshEnough()
                || trust.isBlockedByIssuerAndKid(
                    issuer, String.valueOf(jwt.getHeaders().get("kid")))) {
            return OAuth2TokenValidatorResult.failure(
                new OAuth2Error("invalid_token", "Key not trusted", null));
        }
        return OAuth2TokenValidatorResult.success();
    };

    decoder.setJwtValidator(new DelegatingOAuth2TokenValidator<>(
        JwtValidators.createDefaultWithIssuer(issuer),
        audience,
        emergencyPolicy));
    return decoder;
}
~~~

`EmergencyKeyTrustPolicy` là interface **do ứng dụng định nghĩa**; mã minh họa không tự thay đổi key resolver/JWKS cache. Một **blocklist `kid` đơn thuần không ngăn** mọi trường hợp reuse cùng key material dưới alias khác hoặc verifier cấu hình sai; cần trusted public-key fingerprint policy trong actual verification path.

### 16.4. Key K1 bị mất không đồng nghĩa RS phải xóa K1 public

Nếu K1 private không còn ở AS nhưng **không bị nghi lộ**, RS có thể giữ K1 public tới khi JWT K1 hợp lệ hết hạn. Nếu K1 **COMPROMISED**, RS phải ngừng tin K1 theo security response. Đây là hai lifecycle paths khác nhau.

### 16.5. Issuer key set phải có readiness gate

Trước khi AS ở DR bắt đầu phát token bằng K2:

~~~text
K2 signer usable at KMS?                YES
Key K2 ACTIVE and trusted by issuer?    YES
JWKS K2 published from trusted source?  YES
Selected RS/RPs ready to verify K2?     YES / rollout policy
Grant/revocation state sufficiently new? YES
K1 compromised key still trusted?       NO, nếu K1 compromised
~~~

Nếu còn `UNKNOWN`, hệ thống phải áp một kế hoạch controlled rollout/limited availability thay vì cấp token từ trạng thái không nhất quán và tự tuyên bố “recovered”.

## 17. SQL: lưu metadata, lifecycle và security tombstone

Không lưu raw private key trong bảng key registry. Ví dụ:

~~~sql
CREATE TABLE cryptographic_keys (
    issuer_id VARCHAR(256) NOT NULL,
    key_fingerprint VARCHAR(256) NOT NULL,
    key_id VARCHAR(128) NOT NULL,
    key_purpose VARCHAR(64) NOT NULL,
    algorithm VARCHAR(32) NOT NULL,
    kms_reference VARCHAR(512),
    lifecycle_state VARCHAR(32) NOT NULL,
    activated_at TIMESTAMP NULL,
    retired_at TIMESTAMP NULL,
    blocked_at TIMESTAMP NULL,
    security_version BIGINT NOT NULL,
    PRIMARY KEY (issuer_id, key_fingerprint)
);

CREATE TABLE key_backup_manifests (
    backup_id VARCHAR(128) PRIMARY KEY,
    issuer_or_dataset_id VARCHAR(256) NOT NULL,
    key_fingerprint VARCHAR(256) NOT NULL,
    encrypted_blob_reference VARCHAR(1024),
    manifest_integrity_ref VARCHAR(512) NOT NULL,
    created_at TIMESTAMP NOT NULL,
    expires_at TIMESTAMP NULL,
    recovery_policy_version BIGINT NOT NULL
);

CREATE TABLE key_security_events (
    event_id VARCHAR(128) PRIMARY KEY,
    issuer_id VARCHAR(256) NOT NULL,
    key_fingerprint VARCHAR(256) NOT NULL,
    security_version BIGINT NOT NULL,
    event_type VARCHAR(64) NOT NULL,
    occurred_at TIMESTAMP NOT NULL
);
~~~

Schema **minh họa**; production cần tenant/purpose constraints, indexes, referential integrity, ownership, key origin, backup encryption policies và audit. `encrypted_blob_reference` là reference tới protected blob, **không phải private key PEM plaintext**.

### 17.1. Restore metadata phải chống rollback

~~~sql
-- Pseudocode: không dùng UPDATE thiếu authorization/transaction/version.
UPDATE cryptographic_keys
SET lifecycle_state = :trusted_state,
    security_version = :incoming_version
WHERE issuer_id = :issuer
  AND key_fingerprint = :fingerprint
  AND security_version < :incoming_version
  AND lifecycle_state <> 'COMPROMISED';
~~~

Đây là **một điều kiện minh họa, không phải kiểm soát đủ**: nếu registry mới restore hoàn toàn mất tombstone `COMPROMISED`, clause đó không cứu được. Cần **authoritative, append-only/monotonic security journal** được phục hồi trước khi cho phép trust, và state machine chỉ cho phép transitions đã được phê duyệt.

### 17.2. Một event revoke/key block không được biến mất trong restore

~~~text
security event:
    eventId=evt-991
    issuer=login-prod
    fingerprint=K1
    type=KEY_COMPROMISED
    version=43

Restore snapshot:
    K1 ACTIVE version=42

Reconciliation:
    replay evt-991
    K1 COMPROMISED version=43
    forbid ACTIVE from stale snapshot
~~~

Event IDs và security versions cần được xác thực, chỉ những publishers có thẩm quyền mới được tạo event, và consumer phải hỗ trợ duplicate/out-of-order replay.

### 17.3. Bảo vệ kết quả restore

Một database restore có thể hoàn tất nhưng **dịch vụ không nên phục vụ** cho tới khi:

- Verified backup integrity và trusted metadata.
- Key purpose/issuer/fingerprint match.
- Đã replay key compromise/revocation state.
- Đã so khớp required key versions với ciphertext references.
- Authorization policy và client grants đủ mới.
- RS/AS trust state/signer readiness đạt.
- Recovery event được audit/phê duyệt.

Không dùng lệnh `UPDATE all keys SET status='ACTIVE'` để “khởi động lại cho nhanh”.

## 18. Threat model: bản backup có thể trở thành nơi làm lộ khóa

Backup giúp recoverability nhưng thường tồn tại **lâu hơn production node** và được nhiều hệ thống vận hành chạm tới. Điều này khiến backup trở thành mục tiêu hấp dẫn.

| Mối đe dọa/lỗi | Hậu quả | Kiểm soát |
|---|---|---|
| **Plaintext PEM nằm trong backup chung** | Bên có quyền đọc backup có khả năng ký giả JWT | Non-exportable KMS/HSM hoặc encrypted/wrapped backup |
| **Wrapping key nằm cùng bucket** | Attacker lấy cả ciphertext backup và key giải mã | Tách trust domains, IAM/quorum |
| **CI artifact chứa private key** | Ai có quyền tải image/log có thể lấy key | Secret scanning, no-export pipeline |
| **Restore trong shared staging** | Private production key bị lộ cho dev/test | Isolated DR environment, no production secret import |
| **Một operator có mọi quyền** | Insider hoặc bị chiếm account có thể trích xuất và trust key giả | Dual control, least privilege, technical separation |
| **Backup manifest bị sửa** | Restore sai key/issuer/algorithm hoặc key của attacker | Integrity/authenticity verification và trusted registry |
| **Key version mapping mất** | Không tìm được key để giải mã ciphertext | Versioned backup manifest + metadata snapshot |
| **Mất KEK nhưng giữ ciphertext** | Dữ liệu không thể giải mã | Secure KEK recovery hoặc rewrap trước key retirement |
| **Xóa key quá sớm** | Archive/backup cũ thành dữ liệu vô dụng | Key dependency inventory, retention/hold checks |
| **Nonce reuse sau restore** | Với AEAD như GCM, có thể gây nguy cơ nghiêm trọng | Fresh DEKs/nonce strategy, không reset counter sai |
| **RPO thiếu security events** | R1 USED/REVOKED hoặc K1 COMPROMISED thành ACTIVE | Replay authoritative journal, fail closed |
| **Restore stale JWKS** | Verifier re-trust key đã bị lộ | Monotonic trust tombstones và readiness |
| **KMS replication chậm** | Region DR thiếu key hoặc status revoke mới | Replication SLO và simulation outage |
| **Thay alias trỏ key cũ** | Service vô tình sử dụng compromised material | Fingerprint/key material checking |
| **Backup bị xóa/ransomware** | Không còn recovery path | Immutable/offline copies, access segregation |
| **Backup encryption key cũng mất** | Không giải mã được cả backup | Bootstrap/quorum and independent recovery |
| **Unseal shares mất/quá hạn** | HSM/vault không thể khôi phục | Threshold custody và định kỳ restore rehearsal |
| **Backups tồn tại quá retention** | Tăng privacy/key leak exposure | Lifecycle retention và verified disposal |
| **Restore bỏ kiểm policy** | Operator dùng quyền recovery để lấy plaintext trái phép | RBAC/ABAC, approval, audit, isolated use |
| **Cùng key staging và production** | Leak môi trường thấp làm hại production | Key separation by environment |
| **KMS Sign role bị chiếm** | Attacker ký giả dù key không export | IAM, Sign audit, capability containment |
| **Secret key để trong support ticket** | Thêm bản sao dài hạn không kiểm soát | Redaction và incident evidence vault |
| **JWKS publisher bị chiếm** | Attacker đưa public key mới vào trusted set | Config signing/change control/issuer binding |
| **Disaster recovery diễn tập bằng key thật** | Test trở thành kênh export key production | Synthetic fixture và provider-native attestation |
| **Server clock/metadata sai** | Key activated/retired thời điểm không đúng | Trusted time/version ordering, không dựa chỉ timestamps |

### 18.1. Tampering: backup decrypt được vẫn chưa chắc đáng tin

Nếu attacker kiểm được một backup trước khi nó được ký/niêm phong, họ có thể thay đổi dữ liệu và chạy lại công cụ encryption trong một quy trình đã bị chiếm. Lúc restore, **AEAD tag hợp lệ** vẫn không chứng minh dữ liệu nghiệp vụ không bị attacker chỉnh từ trước.

Do đó recovery cần:

- Security-audited backup creation pipeline.
- Signed/attested manifest có trust anchor độc lập.
- Object storage version/immutability khi phù hợp.
- Separation giữa người có quyền thay backups và người được phê duyệt restore.
- Snapshot consistency và đối chiếu các nghiệp vụ quan trọng.

### 18.2. Availability không thay thế confidentiality

Sai:

~~~text
K1 private đang ở HSM.
Để phòng HSM chết:
    export K1_private thành PEM plaintext,
    lưu vào shared drive,
    cho 30 nhân viên truy cập để khôi phục nhanh.
~~~

Giải pháp này có thể giảm RTO khi HSM lỗi nhưng **mở rộng signing capability** ra 30 identities. Cần HSM-native recovery hoặc encrypted/wrapped backup với quorum, không đánh đổi toàn bộ trust model để giảm vài phút downtime.

### 18.3. Backup key bị lộ là một **key compromise incident**

Nếu một bản backup chứa K1_private bị đánh cắp, hãy coi **K1 đã có khả năng bị compromise**, kể cả production KMS vẫn healthy:

1. Xác định key material/fingerprint và trust domains.
2. Ngừng sử dụng K1 cho issuance theo incident policy.
3. Distrust public K1 ở RS/RP nếu signer bị compromise.
4. Tạo K2 thật sự mới, cập nhật JWKS/trust state.
5. Điều tra token giả, grants, sessions và API accesses.
6. Chặn nguyên nhân leak từ backup/restore pipeline.

Đừng chỉ “đổi password của backup storage” vì attacker có thể đã mang private bytes đi.

## 19. Giám sát và audit khả năng khôi phục

### 19.1. Đo recoverability mà không giải mã secrets tùy tiện

| Chỉ số | Mục đích |
|---|---|
| `backup_creation_success_by_key_purpose` | Có bản backup mới theo scope không? |
| `backup_manifest_verification_failures` | Có artifact bị hỏng/tampered không? |
| `latest_recovery_test_age` | Bao lâu chưa diễn tập restore? |
| `kms_key_availability_by_region` | KMS/HSM signer/decryptor có đủ region không? |
| `key_registry_checkpoint_lag` | Metadata version có chậm so với ciphertext không? |
| `security_journal_replay_lag` | Khi DR, các revocation events còn thiếu bao nhiêu? |
| `key_trust_policy_version_by_rs` | RS có nhận security tombstones mới nhất không? |
| `unexpected_kms_sign_decrypt_calls` | Có người/role dùng key bất thường không? |
| `retired_key_still_needed_for_ciphertext` | Có xóa nhầm key version cần archive không? |
| `recovery_rto_observed` | Mất bao lâu để phục hồi dịch vụ trong diễn tập? |
| `recovery_rpo_observed` | Có bao nhiêu state sau snapshot chưa phục hồi? |
| `unauthorized_restore_attempts` | Có truy cập recovery path trái policy không? |

Không để metrics chỉ ghi `backup_success=true` mà không kiểm **restore/decrypt/verify**; bản backup không thể khôi phục có giá trị thấp.

### 19.2. Audit metadata nên chứa gì?

~~~text
backupId / restoreRequestId
issuerId hoặc datasetId
keyFingerprint (public, không phải private bytes)
keyPurpose / keyVersion / kmsReference
initiatorIdentity / approvers
approvalPolicyVersion
sourceRegion / targetRegion
backupSnapshotCheckpoint
securityJournalHighWatermark
restoredKeyStatus / trustPolicyVersion
integrityVerificationResult
syntheticCanaryVerificationResult
createdAt / restoredAt / readinessAt
~~~

Không ghi:

~~~text
Private signing key material
HMAC signing secret
KEK/DEK plaintext
HSM unseal shares
KMS access tokens/credentials
Refresh/access/ID tokens raw
Session cookies
Ciphertext chứa dữ liệu nhạy cảm trong logs
~~~

Key fingerprints, KMS references, user/tenant IDs và timeline vận hành vẫn có thể nhạy cảm. Cần hạn chế retention và quyền xem theo nhu cầu.

### 19.3. Phân biệt các trạng thái backup và recovery

~~~text
BACKUP_CREATED       File/blob đã được ghi.
BACKUP_VERIFIED      Integrity/provenance kiểm PASS.
RESTORE_STARTED      Quy trình khôi phục đã bắt đầu.
KEY_RECOVERED        Key/capability đã sẵn sàng theo policy.
METADATA_RECONCILED Security journal và mapping nhất quán.
SIGNER_READY         Có thể ký token đúng issuer/profile.
DECRYPT_CANARY_PASS  Có thể đọc ciphertext fixture phù hợp.
RS_TRUST_READY       Các RS quan trọng xác minh/từ chối đúng keys.
RECOVERY_COMPLETE    Các mục tiêu service đã được kiểm và phê duyệt.
~~~

Các tên là **nội bộ minh họa**, không phải chuẩn OAuth. `BACKUP_CREATED` **không tương đương** `RECOVERY_COMPLETE`.

### 19.4. Recovery success phải được kiểm trên những hệ thống thực thi

Một KMS `Sign` trả về chữ ký không bảo đảm:

- RS/RP đã biết public K2.
- RS kiểm đúng issuer/audience/token type.
- Grant state không bị rollback.
- Ciphertext cũ decrypt được.
- Key đã bị COMPROMISED không được trust nữa.

Do đó, cần kiểm từ AS tới RS, từ encryption service tới data restore và từ security journal tới access decisions.

## 20. Các anti-pattern cần loại bỏ

### 20.1. Backup toàn bộ secrets vào một ZIP không mã hóa

~~~text
secrets-backup.zip
    signing-private.pem
    hmac-secret.txt
    kms-root-credential.json
    oauth-clients.csv
    refresh-tokens.csv
~~~

Đây là một **single point of mass compromise**. Không tạo phương pháp phục hồi cho toàn hệ thống bằng một file mà một identity có thể tải xuống.

### 20.2. Tự sửa status `COMPROMISED -> ACTIVE`

Key K1 bị lộ, nhưng operator thấy restore script lỗi vì key không ACTIVE nên chỉnh DB để “test”. Hành vi này **khôi phục trust của khóa đã bị tấn công**. Cần tạo K2 và thực hiện migration hợp lệ, không đảo security tombstone.

### 20.3. Chỉ backup private key, không backup client/grant/trust state

Signing K1 chạy được, nhưng client registrations và refresh family bị rollback, khiến AS có thể cấp token từ consent/role/grant cũ. Key backup phải phối hợp **identity authorization data consistency**.

### 20.4. Chỉ backup ciphertext, không lưu key version

Có hàng trăm TB backup nhưng không biết dùng KEK version nào để unwrap DEKs. Đây là mất recoverability dù backup blobs đều còn.

### 20.5. Coi same-name KMS alias là same-key

Sau restore, alias `jwt-signing-current` có thể trỏ tới **K2 chứ không phải K1**. Nên kiểm key ID/material fingerprint và purpose, không coi alias/name là cryptographic identity.

### 20.6. Tin tất cả key trong restored JWKS

JWKS backup từ trước sự cố có K1 public, nhưng K1 đã compromise. Restore không được công bố lại K1 như trusted nếu security registry đã block.

### 20.7. Quên phạm vi key ngoài JWT

Hệ thống token còn có client assertion keys, mTLS certs, DPoP holder keys, JWE keys, refresh-token state và cookie secrets. Phục hồi mỗi private JWT signer có thể không đủ để user login, client auth hoặc decrypt dữ liệu.

### 20.8. Thử restore lần đầu trong sự cố thật

Backup chưa từng được giải mã/verify trong DR environment có thể thiếu shares, wrong firmware, wrong key origin hoặc dependencies. **Diễn tập có kiểm soát** là yêu cầu của recoverability, không phải phần tùy chọn hoàn toàn.

## 21. Ma trận kiểm thử backup, key recovery và security invariants

**Test “file backup tồn tại” là chưa đủ.** Cần xác minh confidentiality, integrity, recoverability và việc security decisions vẫn được giữ sau restore.

### 21.1. Key lifecycle và backup provenance

| Tình huống | Kết quả phải đạt |
|---|---|
| KMS/HSM tạo signing key theo policy | Key có purpose/issuer/algorithm, không export khi policy cấm |
| RS cố export private signer | Bị từ chối; RS chỉ nhận public trust info |
| Backup job không có quyền Decrypt/Sign | Không thể mở hoặc dùng secret trái permission |
| Một operator cố tự approve restore | Quorum/approval policy từ chối |
| Backup manifest chữ ký không hợp lệ | Restore dừng, không activate key |
| Artifact backup bị sửa một byte | Integrity check phát hiện; không tiếp tục |
| KMS key reference trong manifest trỏ issuer khác | Key registry policy từ chối |
| Restore K1 signing key vào staging rộng quyền | Chính sách ngăn production key exposure |
| Restore backup thiếu wrapping key/HSM prerequisites | Trả failure có kiểm soát, không cho bypass security |
| Backup đã hết retention policy | Xử lý theo retention/hold, không dùng lại tự động |
| Key `COMPROMISED` còn trong backup cũ | Không trở lại trusted/ACTIVE |
| Public JWK được backup/đăng JWKS | Có thể public; không chứa private fields `d`/`p`/`q` |
| Secret HMAC nằm trong log backup | Test bảo mật fail |
| Backup kiểm soát bởi cùng account có quyền Sign và Decrypt tất cả | Phát hiện separation-of-duties violation |

### 21.2. Encryption và wrapped DEK

| Tình huống | Kết quả phải đạt |
|---|---|
| C1 + wrapped DEK + đúng KEK v7 | Decrypt và verify AEAD thành công |
| Ciphertext bị sửa | AEAD tag verification thất bại |
| Authentication tag thiếu hoặc sai | Không trả plaintext |
| IV/nonce sai | Decrypt thất bại |
| AAD/context sai | Decrypt thất bại |
| Key version sai/không tồn tại | Fail closed, không dùng key khác bừa |
| Key K7 vẫn cần cho archive | Cleanup không xóa K7 trước dependency clearance |
| Rewrap KEK v7 -> v8 | Dữ liệu test vẫn decrypt đúng dưới v8 |
| DEK bị nghi lộ | Rewrap đơn thuần không được coi là đủ; đánh giá re-encrypt |
| Restore backup chứa cipher algorithm legacy | Có migration/allowlist đúng, không tự hạ crypto |
| KMS Decrypt lỗi/network partition | Không xuất dữ liệu giả; lỗi được audit |
| Data snapshot và key registry ở hai checkpoints không tương thích | Không đánh dấu recovery complete |
| Encryption counter/nonce state restore cũ | Không tái sử dụng nonce dưới cùng key |
| Key đã cryptographically erased | Không hứa decrypt lại nếu không còn key/recovery path |

### 21.3. AS/RS JWT và JWKS

| Tình huống | Kết quả phải đạt |
|---|---|
| K1 private unavailable, không compromise | K2 issuance hoạt động; K1 public token cũ được verify nếu còn trusted |
| K1 private compromised, backup intact | Restore không cho ký/trust K1 |
| K2 tạo mới nhưng `kid` trùng | Fingerprint/key material binding không nhầm K1 và K2 |
| K2 đã publish, RS có cache cũ | Rollout/fallback policy xử lý RS chưa nhận K2 |
| AS K2 ký JWT đúng issuer/audience | RS verify chữ ký đúng, còn kiểm business policy |
| JWT K1 `exp` còn hạn nhưng K1 bị BLOCKED | RS từ chối theo key trust |
| JWT K1 `iat` giả trước thời điểm compromise | Không bypass emergency distrust |
| K1 nằm trong JWKS backup cũ | Reconciliation không re-trust K1 |
| `alg=none` hoặc thuật toán không đăng ký | RS từ chối |
| JWT `jku` trỏ URL ngoài issuer trust | RS không fetch/trust arbitrary key source |
| JWT K2 có audience dành API khác | RS từ chối |
| JWT K2 có scope nhưng order thuộc tenant khác | Resource policy từ chối |
| RS mới scale-out chưa load trust tombstones | Readiness/fail-closed trước khi nhận traffic nhạy cảm |
| KMS Sign role compromise | IAM được thu hồi, audit và key trust response đúng |

### 21.4. OAuth/OIDC grant, refresh, client keys

| Tình huống | Kết quả phải đạt |
|---|---|
| R1 đã USED trước DB backup restore | AS không nhận R1 như ACTIVE |
| Refresh family F1 đã REVOKED sau snapshot | F1 vẫn REVOKED sau journal replay |
| User U1 disabled sau snapshot | AS/RS áp security epoch mới |
| Client registration C1 đã bị vô hiệu | AS không cấp token từ registration cũ |
| OIDC ID token signing K1 bị compromise | RP trust policy chặn forged ID token K1 |
| `private_key_jwt` client đã rotate C1->C2 | AS restore đúng public client key version |
| mTLS client certificate bị revoke | Không tự trust cert cũ khi restore metadata |
| DPoP holder key bị mất trên thiết bị | Rebind/re-authorize theo policy, không export key khác để chia sẻ |
| Authorization code đã single-use trước restore | Không phát token lần hai từ snapshot cũ |
| PKCE request state đã hết hạn | Không khôi phục thành authorization hợp lệ |
| Opaque token introspection sau restore | Active state nhất quán với grant/token revocation |
| JWT access còn hạn nhưng grant bị revoke | RS áp revocation policy theo SLO nếu cam kết chặn sớm |

### 21.5. Disaster recovery và chaos

| Test | Kết quả mong muốn |
|---|---|
| Region A KMS offline | Failover/key replacement trong RTO, không cho ký sai issuer |
| Region A data center mất toàn bộ | Recovery chain không vòng lặp tới hệ thống đã mất |
| Một backup custodian không sẵn sàng | Quorum có thể khôi phục theo chính sách hoặc fail rõ |
| Security journal replay bị tạm dừng | Không bật AS issuance với state stale |
| Region B nhận snapshot ACTIVE v11 sau BLOCKED v12 | Không hồi sinh key/grant |
| Broker out-of-order/duplicate events | Idempotent, version không giảm |
| CDN/JWKS cache giữ K1 compromised | Policy block K1 ở RS; propagation được giám sát |
| Restore key registry thiếu `keyPurpose` | Không activate key tùy ý |
| Restore HSM trên firmware không tương thích | Phát hiện trong diễn tập trước sự cố |
| Backup vật lý bị mất/bị đánh cắp | Khả năng restore và confidentiality đáp ứng policy |
| Backup storage bị ransomware xóa | Immutable/offsite recovery path vẫn sẵn sàng |
| Backup restore từ 30 ngày trước | Revocation/policy journal không bị lùi 30 ngày |
| Failover issuer đổi DNS/host | `iss` và trusted metadata không tự sai |
| K2 mới chưa có trong RS JWKS | Rollout/fail mode không silently accept token không verify |
| RS mất kết nối key-trust source | Freshness deadline và fail-closed theo risk policy |
| Recovery chạy thành công nhưng audit tắt | Không đánh dấu hoàn tất nếu security policy yêu cầu audit |

### 21.6. Tiêu chí kiểm thử thực chất

Một bài DR drill nên trả lời bằng bằng chứng:

1. **Ai** thực hiện restore, đã có approval/quorum đúng không?
2. **Khóa nào** được restore/tái tạo, fingerprint và purpose có đúng không?
3. **Dữ liệu nào** decrypt được và những dữ liệu nào không nên được mở?
4. **JWT nào** được RS/RP chấp nhận hoặc từ chối sau recovery?
5. **Security events** nào đã xảy ra sau snapshot và đã replay đầy đủ chưa?
6. **Client/grant/refresh family** có còn trạng thái chính xác không?
7. **RTO/RPO** thực đo có đạt mục tiêu không?
8. Logs/test artifacts có chứa raw keys hoặc production tokens không?

Không dùng một lần thử trên một server để kết luận mọi node/region đều an toàn. Cần các bài test cho **bootstrap, stale cache, region partition, restore từ bản snapshot cũ và compromised key tombstones**.

## 22. Tình huống tự suy luận

### Tình huống A — Có backup database nhưng không có KEK

Đội vận hành có bản backup Orders DB đầy đủ, gồm ciphertext và wrapped DEKs, nhưng KEK v7 đã bị xóa hẳn và không có recovery path.

**Câu hỏi:** Có thể khôi phục dữ liệu không?

**Trả lời:** Có thể **không**. Wrapped DEKs cần KEK v7 để unwrap; backup ciphertext và metadata không tự tái tạo được key material. Phải xác định khả năng provider-native recovery trước khi hứa khôi phục.

### Tình huống B — Private signing key bị mất, nhưng không lộ

AS mất K1_private, RS còn K1_public và access tokens còn hạn 10 phút.

**Câu hỏi:** Có bắt buộc khôi phục K1_private để RS tiếp tục verify không?

**Trả lời:** Không. Public K1 đủ để kiểm chữ ký token cũ nếu K1 vẫn trusted. AS có thể sinh K2 mới và chuyển issuance; cần publish K2 public tới RS trước hoặc theo rollout policy.

### Tình huống C — Private signing key đã bị lộ

K1_private bị tải khỏi backup storage. Operator muốn restore K1 từ bản backup tuần trước vì bản đó có integrity signature hợp lệ.

**Câu hỏi:** Cách này có làm K1 an toàn trở lại?

**Trả lời:** Không. Bản backup chứa **cùng K1 material** mà attacker có thể đã sao chép. Phải ngừng trust K1, sinh K2 mới và bảo vệ backup pipeline.

### Tình huống D — JWKS đã đổi nhưng RS cache cũ

AS ký K2 và công bố JWKS mới; Orders API giữ K1_public trong local cache.

**Câu hỏi:** Khi K1 bị compromise, đã hoàn tất recovery chưa?

**Trả lời:** Chưa. Orders API vẫn có thể chấp nhận JWT giả ký K1 nếu không có key distrust control. Cần invalidate/override trust state và kiểm từng verifier.

### Tình huống E — Chỉ thay `kid`

AS đổi `kid` của key signer, nhưng KMS reference vẫn trỏ cùng private bytes K1.

**Câu hỏi:** Đây có phải key rotation?

**Trả lời:** Không. Cryptographic identity vẫn là K1. Cần sinh key material mới và kiểm public fingerprint, không tin alias/kid như bằng chứng rotation.

### Tình huống F — Một operator có quyền backup và restore tất cả

Administrator có thể export keys, tải backup, xóa audit, đổi JWKS và đánh dấu key ACTIVE.

**Câu hỏi:** Rủi ro gì?

**Trả lời:** Insider hoặc account compromise có thể đánh cắp ký giả hoặc cài key attacker vào trusted set mà khó phát hiện. Áp separation of duties, quorum, IAM least privilege và audit độc lập.

### Tình huống G — Non-exportable HSM key

K1 được tạo non-exportable. Một script đề xuất `exportPrivateKey()` để làm backup DR.

**Câu hỏi:** Có nên phá chính sách để xuất PEM?

**Trả lời:** Không. Cần xem provider-native HSM recovery/replication hoặc new-key failover. Mục tiêu recovery là khả năng ký/giải mã được kiểm soát, không phải người vận hành nhận bytes bí mật.

### Tình huống H — Multi-region key replica có nhưng grant store stale

Region B ký JWT được bằng K2, nhưng client X đã bị disable tại A và B chưa biết.

**Câu hỏi:** AS có nên bắt đầu phát token ngay?

**Trả lời:** Không nếu grant/client policy chưa đủ mới. Signing capability không chứng minh authorization state hợp lệ. Cần security journal replay/reconciliation và issuance readiness gate.

### Tình huống I — R1 bị USED rồi restore về ACTIVE

Alice đã refresh R1 thành R2. DR restore snapshot cũ cho rằng R1 ACTIVE.

**Câu hỏi:** Lỗi nằm ở đâu?

**Trả lời:** Restore làm lùi refresh family state, tạo nguy cơ replay. Phải replay rotation/security events hoặc invalidate grants không thể phục hồi nhất quán.

### Tình huống J — Security chặn K1 sau snapshot

Backup key registry lúc 09:00 chứa `K1 ACTIVE version=10`. Lúc 10:00 K1 bị lộ và `BLOCKED version=11`. Lúc 11:00 restore bản 09:00.

**Câu hỏi:** Có thể bật API với K1 ACTIVE không?

**Trả lời:** Không. Phải replay authoritative tombstone v11 và chứng minh RS/AS chặn K1 trước readiness.

### Tình huống K — Thiếu AAD của ciphertext

Ciphertext AES-GCM C1 và KEK đều còn, nhưng app đổi quy tắc AAD mà không lưu encryption schema version.

**Câu hỏi:** Vì sao decrypt fail?

**Trả lời:** AEAD authentication yêu cầu đúng AAD. Metadata/version là một phần recovery artifact; không được bỏ xác minh tag để “cứu dữ liệu”.

### Tình huống L — Rewrap sau khi DEK đã lộ

DEK D1 bị attacker copy. Team chỉ rewrap D1 từ KEK1 sang KEK2 và tuyên bố dữ liệu an toàn.

**Câu hỏi:** Có đúng không?

**Trả lời:** Không. D1 vẫn là DEK attacker có; rewrap không xóa năng lực giải mã dữ liệu mã hóa bằng D1. Cần đánh giá re-encrypt bằng D2 và dữ liệu đã bị truy cập.

### Tình huống M — Key v3 cũ còn dùng bởi archive

Orders DB mới đều dùng KEK v7. Một archive năm 2024 vẫn bọc DEK bằng KEK v3.

**Câu hỏi:** Có thể xóa v3 vì đã “rotate xong” không?

**Trả lời:** Chưa nếu archive còn cần recover. Cần key dependency inventory và rewrap/re-encrypt/verified recovery trước khi retire/delete v3.

### Tình huống N — Không thể đăng nhập vào DR vì IdP chính đã chết

KMS recovery approvals cần login qua IdP production, nhưng IdP là thành phần đang phải khôi phục.

**Câu hỏi:** Thiếu gì?

**Trả lời:** Recovery bootstrap có vòng phụ thuộc. Cần một identity/quorum recovery path độc lập, được bảo vệ, có audit và diễn tập định kỳ.

### Tình huống O — HSM unseal shares bị mất

HSM dùng M-of-N shares, nhưng nhiều người giữ share đã nghỉ việc, các shares còn lại không đủ quorum.

**Câu hỏi:** Có thể gọi backup là recoverable không?

**Trả lời:** Không nếu nghi thức khôi phục không thể hoàn tất. Cần custody rotation, succession policy, periodic quorum rehearsal và contingency theo HSM/vendor.

### Tình huống P — Public JWK được chia sẻ cho RS

Orders API nhận JWKS chứa RSA `n`, `e`, `kid`.

**Câu hỏi:** Có phải rò private key?

**Trả lời:** Không. Public verification keys chủ đích được phân phối. Nhưng cần kiểm public JWKS không chứa private fields hoặc bị attacker thay bằng key giả.

### Tình huống Q — Sao lưu refresh token plaintext

Backup operator xuất CSV chứa toàn bộ refresh tokens thô để “dễ khôi phục”.

**Câu hỏi:** Rủi ro gì?

**Trả lời:** Bất kỳ người đọc backup có thể có bearer credentials để xin token mới trong giới hạn AS. Thiết kế nên backup verified token store/hash/HMAC, grant family state và bảo vệ như bí mật; không cần xuất raw tokens.

### Tình huống R — Backup file intact nhưng đã bị attacker thay trước lúc ký

Một backup decrypt đúng và signature của pipeline hợp lệ, nhưng pipeline đã bị chiếm trước khi snapshot được tạo.

**Câu hỏi:** Có thể khẳng định dữ liệu chưa bị sửa không?

**Trả lời:** Không hoàn toàn. Chữ ký chứng minh dữ liệu đi qua pipeline/khóa ký tương ứng, không chứng minh pipeline chưa bị chiếm. Cần audit và independent provenance/consistency checks.

### Tình huống S — Backup nonce counter reset

Ứng dụng AES-GCM dùng cùng DEK và counter IV; sau restore, counter quay lại giá trị cũ.

**Câu hỏi:** Nguy cơ?

**Trả lời:** Tái sử dụng nonce với cùng key là lỗi mật mã nghiêm trọng. Recovery phải bảo toàn nonce uniqueness hoặc đổi sang DEK mới/nonce strategy an toàn.

### Tình huống T — Client DPoP key bị mất

Ứng dụng native lưu DPoP private key trong hardware-backed keystore non-exportable. Thiết bị reset, private key biến mất.

**Câu hỏi:** Có nên giữ một bản plaintext DPoP key ở server để restore?

**Trả lời:** Thường không phù hợp mục tiêu device-bound. Có thể tạo key mới và reauthorize/rebind tokens, tùy mobile security policy. Server có thể quản lý recovery UX mà không giữ private device key.

### Tình huống U — Client `private_key_jwt` đã rotate

Client giữ C2_private mới; AS DR restore registration cũ chỉ chứa C1_public.

**Câu hỏi:** Có nên để client đính kèm public C2 tùy ý vào assertion để AS tin không?

**Trả lời:** Không. AS phải khôi phục trusted client registration/JWKS binding hoặc thực hiện key update qua một quy trình xác thực riêng.

### Tình huống V — Key wrapping backup bị lộ nhưng wrapping key còn an toàn

Attacker lấy wrapped DEK blobs và ciphertext, chưa có KEK/KMS Decrypt access.

**Câu hỏi:** Có chắc dữ liệu đã lộ plaintext không?

**Trả lời:** Không thể khẳng định chỉ từ blobs đã bị sao chép; encryption bảo vệ confidentiality nếu triển khai đúng và KEK chưa bị lộ. Tuy nhiên cần điều tra permissions/algorithms/context, metadata leakage và đánh giá rủi ro lâu dài.

### Tình huống W — Key backup leak qua SIEM

Restore tool log toàn bộ KMS decrypt response. SIEM có nhiều người đọc hơn HSM.

**Câu hỏi:** Cách xử lý?

**Trả lời:** Dừng/log redaction, coi key material có nguy cơ compromise, rotate/distrust theo loại key, đánh giá bản sao trong retention và harden logging pipeline.

### Tình huống X — Backup có nhưng chưa bao giờ restore thử

Đội vận hành thấy backup jobs trả SUCCESS suốt 12 tháng nhưng lần diễn tập phát hiện HSM firmware mới không hỗ trợ restore blob cũ.

**Câu hỏi:** Lỗi trong chỉ số nào?

**Trả lời:** Đã nhầm backup creation thành recoverability. Cần định kỳ restore tests trên môi trường/cấu hình tương thích, kiểm cryptographic canaries và RTO/RPO.

### Tình huống Y — Cryptographic erasure và backup xung đột

Hệ thống tuyên bố xóa dữ liệu bằng cách hủy DEK, nhưng bản backup cũ vẫn chứa DEK plaintext có thể giải mã được.

**Câu hỏi:** Đã xóa mật mã thật chưa?

**Trả lời:** Chưa đạt mục tiêu nếu key copies vẫn cho phép giải mã. Cần data/key backup retention và destruction policy nhất quán, xét legal hold và nghĩa vụ liên quan.

### Tình huống Z — Khôi phục key bằng bản copy từ production bị chiếm

AS host bị attacker chiếm, đội vận hành lấy file private key từ host đó và import vào DR.

**Câu hỏi:** Vấn đề?

**Trả lời:** Không có trust provenance và key có thể đã bị sao chép. Cần nguồn backup/recovery đáng tin, isolate compromised host, tạo key mới nếu không chứng minh được K1 còn bí mật, và đánh giá key trust ở RS.

## 23. Playbook: khôi phục key management sau thảm họa

Playbook này tách **disaster recovery** và **security incident containment**. Hai sự cố có thể diễn ra đồng thời, nhưng không được để yêu cầu khôi phục nhanh làm biến khóa đã lộ thành trusted.

### 23.1. Bước 1 — Xác định mục tiêu, phạm vi và tính chất sự cố

Hỏi:

1. Mất **availability** của KMS/HSM hay có bằng chứng **compromise**?
2. Khóa bị ảnh hưởng là signing, decryption/KEK, HMAC, client auth, DPoP/mTLS hay session secret?
3. Những issuers, audiences, ciphertext datasets, clients, RPs/RS nào phụ thuộc khóa?
4. RTO/RPO và security freshness SLO cần đạt là gì?
5. Key material đã export được chưa? Ai có quyền Sign/Decrypt/Restore?
6. Backup/quorum/HSM recovery prerequisites có còn hoạt động?

Một ma trận quyết định:

| Sự cố | Ưu tiên |
|---|---|
| KMS region offline, không compromise | Failover hoặc tạo key mới, giữ trust đúng |
| Signing key lộ qua backup | Contain signing capability, distrust key, tạo key mới |
| Encryption KEK bị mất | Bảo toàn ciphertext và tìm recovery path; không xóa bản backup còn dùng |
| Encryption KEK bị lộ | Đánh giá confidentiality, rotate/rewrap/re-encrypt khi phù hợp |
| Token/grant store rollback | Chặn issuance, replay security state hoặc invalidate grants |
| JWKS publisher bị chiếm | Khôi phục trusted metadata và kiểm RS/RP trust |

### 23.2. Bước 2 — Cô lập môi trường khôi phục

- Dùng recovery infrastructure đã được phê duyệt, hardening, network segmentation và logging.
- Xác thực operator qua một path còn hoạt động nếu primary IdP không khả dụng.
- Bắt buộc approvals/quorum khi loại khóa và mức độ rủi ro yêu cầu.
- Không cấp quyền public hoặc rộng hơn production cho backup storage.
- Không restore production private keys vào laptop/shared developer environment.
- Không copy nguyên raw private key vào support ticket, chat hoặc command history.

### 23.3. Bước 3 — Xác minh nguồn backup và phiên bản

~~~text
verifyBackup():
    identify expected backup by trusted registry
    verify manifest signature/attestation from trusted root
    verify artifact digest and encryption metadata
    match key purpose, issuer, algorithm, fingerprint
    verify backup age against RPO
    check key compromise/revocation tombstones
    verify wrapped blob compatible with recovery HSM/KMS
    document operator approval and audit correlation
~~~

Manifest integrity có thể sai hoặc backup được tạo từ pipeline đã bị compromise. Trường hợp nghi ngờ, không tự “bỏ qua verify để khôi phục trước”, mà chuyển sang incident/security approval có kiểm soát.

### 23.4. Bước 4 — Khôi phục khả năng sử dụng key

**Với signing key:**

- Khôi phục K1 bằng provider-native process **chỉ nếu K1 vẫn trusted**.
- Nếu không thể hoặc K1 đã compromise: tạo **K2 mới**, publish trusted public key, chuyển issuance.
- Kiểm RS/RP verifiers biết K2 và policy về K1.

**Với data encryption KEK/DEK:**

- Unwrap/recover trong HSM/KMS theo approval.
- Xác minh key version và ciphertext dependency.
- Test decrypt fixture/canary với đúng IV/AAD/tag.
- Không phát tán DEK plaintext ra file/log.
- Rewrap/re-encrypt theo migration policy sau khi recovery thành công.

**Với client/device keys:**

- Nếu non-exportable và bị mất, cấp mới, update registration/PKI/binding và yêu cầu reauthorization khi cần.
- Không tự lấy private key từ thiết bị khác để dùng chung nếu phá sender constraint.

### 23.5. Bước 5 — Restore security state *trước* khi bật cấp token

~~~text
DB/grant snapshot restored         YES
Latest revocation journal replay   YES
Refresh family USED/REVOKED        CONSISTENT
Client/subject disabled states     CONSISTENT
Key compromised tombstones         PRESERVED
Issuer/JWKS trust policy version   FRESH
OAuth client registrations         VERIFIED
Token endpoint issuance            ENABLE only after all gates
~~~

Nếu thiếu journal hoặc state không đáng tin, cân nhắc **force reauthentication/re-consent và invalidation** có phạm vi, không cho AS tiếp tục phát tokens từ snapshot thiếu security events.

### 23.6. Bước 6 — Kiểm tra end-to-end

1. KMS có thể ký/giải mã đúng key purpose?
2. JWT K2 đúng `iss`/`aud`/`alg`/`typ` được RS kiểm hợp lệ?
3. JWT K1 compromised bị từ chối ở **mọi** RS/RP liên quan?
4. Token có scope đúng nhưng resource khác tenant vẫn bị từ chối?
5. Ciphertext fixture decrypt thành công với key version đã restore?
6. Ciphertext/tag/AAD bị sửa được từ chối, không có fallback plaintext?
7. Refresh token R1 đã USED/REVOKED không thể đổi lại?
8. Key/client/subject security policy đã cập nhật mọi region?
9. Không có secret trong logs/traces và các test outputs?
10. Metrics báo RTO/RPO thực đo và những vùng chưa hội tụ?

Không được gọi **RECOVERY_COMPLETE** chỉ dựa vào một `KMS Sign OK` hoặc một HTTP 200 từ JWKS endpoint.

### 23.7. Bước 7 — Khôi phục lưu lượng có giám sát

Thực hiện canary rollout/throttle theo risk policy. Theo dõi:

- Token issuance failures và JWT verification rejects theo key version.
- Introspection/refresh failures không bình thường.
- KMS Sign/Decrypt rate theo principal/key/region.
- JWK cache trust policy/version lag.
- Data decrypt integrity/tag errors.
- Business authorization violations.
- Consumer events/revocation lag và stale regions.

Rollback phải là **rollback vận hành được phê duyệt**, không khôi phục trust với key COMPROMISED hoặc grants đã REVOKED.

### 23.8. Bước 8 — Hậu kiểm và phòng tái diễn

- Xác định vì sao backup/restore path thất bại hoặc làm lộ secret.
- Cập nhật threat model, RTO/RPO và key dependency inventory.
- Bảo vệ key origin, IAM, backup encryption, key policy và audit.
- Kiểm threshold custody và succession của approvers.
- Kiểm các ciphertext archives chưa chuyển key version.
- Tự động hóa test restore synthetic, key-trust canaries và security journal reconciliation.
- Xem xét retention/destruction của key backups theo mục đích và quy định.

**Recovery không chỉ phục hồi service availability; phải phục hồi đúng mô hình tin cậy và bảo đảm trạng thái bảo mật không bị lùi.**

## 24. Checklist production cho backup và recovery key

### 24.1. Thiết kế và phân loại

1. **Inventory:** biết mọi signing, verification, JWE, KEK, DEK, HMAC, client, DPoP/mTLS và session secrets.
2. **Purpose:** tách issuer/environment/key use/algorithm, không reuse key vô tình.
3. **Recoverability:** chọn backup, native HSM recovery, replication hoặc rekey/reauthorize theo loại khóa.
4. **Data lifetime:** xác định ciphertext/archives phụ thuộc key version nào trước khi retire.
5. **RTO/RPO:** đặt mục tiêu cụ thể cho signing, decryption, grants và security state.
6. **Threat model:** phân biệt key lost, key compromised, Sign abuse và JWKS publisher compromise.

### 24.2. Bảo vệ backup

7. **No raw export:** không lưu private key/KEK/DEK plaintext ngoài trust boundary khi không bắt buộc.
8. **Wrapping:** dùng KMS/HSM/provider-supported encryption/wrapping cho key backups.
9. **Separation:** backup blobs và recovery/wrapping credentials không đặt cùng quyền truy cập.
10. **Approvals:** technical quorum/dual control, tách backup operator và key custodian.
11. **Integrity:** signed/attested manifest, trusted key fingerprint/issuer/purpose, version/algorithm metadata.
12. **Isolation:** offsite/immutable storage và isolated DR test environment theo threat model.
13. **Audit:** mọi backup/export/restore/Sign/Decrypt được ghi metadata, không raw secret.
14. **Retention:** bảo vệ archive trong hạn, hủy keys/backups nhất quán với deletion/crypto-erasure policy.

### 24.3. Khôi phục an toàn

15. **Dependency chain:** có bootstrap identities/quorum/HSM/KMS recovery khi primary IdP offline.
16. **Compat:** provider/region/key origin/firmware/algorithm hỗ trợ restore thực tế.
17. **Metadata:** lưu key reference, fingerprint, encryption AAD/IV/tag, wrapped DEK và schema version.
18. **Anti-rollback:** không làm `COMPROMISED -> ACTIVE` hoặc `USED/REVOKED -> ACTIVE` từ snapshot cũ.
19. **Security journal:** replay authoritative revocations/events tới high-watermark trước readiness.
20. **Issuance:** AS chỉ ký với key trusted, grants/client/subject state đủ mới.
21. **JWKS:** publish trusted public keys, ngừng tin compromised material tại mọi RS/RP.
22. **Encryption:** kiểm decrypt synthetic canary với đúng key version/IV/AAD/tag.
23. **Multi-region:** đảm bảo region DR không fail-open hoặc giữ stale key trust quá freshness budget.
24. **Authorization:** RS tiếp tục kiểm audience, scope, principal/action/resource/tenant sau recovery.

### 24.4. Vận hành và kiểm thử

25. **Drills:** diễn tập restore định kỳ, gồm mất vùng, mất shares, cache stale và network partition.
26. **Canaries:** test JWT K1 reject/K2 accept khi emergency; test ciphertext/wrapped DEK decrypt.
27. **Chaos:** kiểm broker pause, event duplicate/out-of-order, restore snapshot cũ và fresh node bootstrap.
28. **Observability:** đo RTO/RPO thật, security journal lag, key-trust SLO và KMS abnormal usage.
29. **Failure mode:** khi key trust/state chưa xác minh, fail closed theo risk policy thay vì default ACTIVE.
30. **Incident response:** có playbook khi **backup itself leaks**, không chỉ khi production key host bị chiếm.

### 24.5. Sơ đồ quyết định nhanh

~~~mermaid
flowchart TD
    A[Cần phục hồi khả năng dùng khóa] --> B{Khóa bị nghi compromise?}
    B -- Có --> C[Không restore trust của key cũ]
    C --> D[Contain signing/decrypt capability + tạo key mới]
    D --> E[Distrust hoặc re-encrypt/rebind theo purpose]
    B -- Không --> F{Khóa dùng để làm gì?}
    F -- Sign JWT --> G[Native recovery hoặc signer K2 mới]
    F -- Decrypt ciphertext --> H[Restore KEK/DEK version cần thiết]
    F -- Client/device binding --> I[Restore có kiểm soát hoặc re-enroll/rebind]
    G --> J[Restore registry và security journal]
    H --> J
    I --> J
    E --> J
    J --> K{Trust state/grants/ciphertext dependencies đầy đủ?}
    K -- Không --> L[Fail closed hoặc quarantine recovery]
    K -- Có --> M[End-to-end crypto + auth tests]
    M --> N[Controlled rollout và audit]
~~~

### 24.6. Ghi nhớ trong một phút

~~~text
Backup:
    Có bản sao/dịch vụ recovery được bảo vệ.

Recovery:
    Có thể khôi phục đúng capability và trust state.

Signing key mất nhưng không compromise:
    Có thể ký tiếp bằng key mới; public key cũ vẫn verify khi hợp lệ.

Signing key compromised:
    Không khôi phục niềm tin chỉ vì bản backup cũ intact.

Encryption key/KEK mất:
    Ciphertext có thể không giải mã được dù database còn.

Wrapped DEK + ciphertext:
    Cần đúng KEK/version/AAD/nonce/tag và quyền decrypt.

Refresh/grant/key trust snapshot cũ:
    Phải replay security journal, không hồi sinh REVOKED/COMPROMISED.

KMS/HSM:
    Non-exportable tốt, nhưng Sign/Decrypt IAM role vẫn có thể bị chiếm.

Recovery complete:
    Phải chứng minh key, grants, RS/RP và dữ liệu đúng trạng thái.
~~~

**Kết luận:** **Backup và recovery key** là sự cân bằng giữa **khả năng phục hồi** và **giữ bí mật/đúng nguồn khóa**. Với issuer signing key, mất private key nhưng không bị compromise có thể giải quyết bằng signer mới và trusted public-key rotation; còn khi key đã bị lộ, restore bản copy cũ **không làm key an toàn trở lại**. Với JWE/KEK/DEK, không có recovery path có thể khiến ciphertext không thể đọc, dù dữ liệu đã được backup đầy đủ. Hệ thống OAuth/OIDC còn phải khôi phục **grants, refresh family, revocation journal, issuer metadata và RS trust** một cách nhất quán. Một kế hoạch tốt dùng KMS/HSM-native recovery hoặc wrapping phù hợp, key versioning, quorum và least privilege, kiểm thử restore định kỳ và **không bao giờ cho snapshot cũ hồi sinh một khóa đã COMPROMISED**.

## Tài liệu tham khảo

- [NIST SP 800-57 Part 1 Rev. 5 — Recommendation for Key Management](https://csrc.nist.gov/pubs/sp/800/57/pt1/r5/final): mục đích, vòng đời khóa, bảo vệ, recovery và compromise.
- [NIST SP 800-34 Rev. 1 — Contingency Planning Guide for Federal Information Systems](https://csrc.nist.gov/pubs/sp/800/34/r1/upd1/final): recovery planning, backup, kiểm thử và RTO/RPO.
- [NIST SP 800-38D — GCM and GMAC](https://csrc.nist.gov/pubs/sp/800/38/d/final): AES-GCM, IV/nonce, authentication tag và yêu cầu bảo mật.
- [NIST SP 800-38F — Methods for Key Wrapping](https://csrc.nist.gov/pubs/sp/800/38/f/final): key wrapping và bảo vệ key material.
- [FIPS 140-3 — Security Requirements for Cryptographic Modules](https://csrc.nist.gov/pubs/fips/140-3/final): yêu cầu đối với mô-đun mật mã, HSM/module security.
- [RFC 3394 — Advanced Encryption Standard (AES) Key Wrap Algorithm](https://www.rfc-editor.org/rfc/rfc3394): AES Key Wrap theo profile áp dụng.
- [RFC 5649 — AES Key Wrap with Padding](https://www.rfc-editor.org/rfc/rfc5649): key wrapping có padding.
- [RFC 7515 — JSON Web Signature (JWS)](https://www.rfc-editor.org/rfc/rfc7515): chữ ký và JOSE header.
- [RFC 7516 — JSON Web Encryption (JWE)](https://www.rfc-editor.org/rfc/rfc7516): mã hóa token và key management.
- [RFC 7517 — JSON Web Key (JWK)](https://www.rfc-editor.org/rfc/rfc7517): JWK/JWKS, public/private fields và key identifiers.
- [RFC 7519 — JSON Web Token (JWT)](https://www.rfc-editor.org/rfc/rfc7519): token claims, `exp`, `iat`, `jti` và JWT semantics.
- [RFC 7638 — JWK Thumbprint](https://www.rfc-editor.org/rfc/rfc7638): nhận diện public key material bằng thumbprint.
- [RFC 8725 — JSON Web Token Best Current Practices](https://www.rfc-editor.org/rfc/rfc8725): key/algorithm/issuer binding và validation.
- [RFC 9068 — JWT Profile for OAuth 2.0 Access Tokens](https://www.rfc-editor.org/rfc/rfc9068): JWT access token validation và audience.
- [RFC 6749 — OAuth 2.0 Authorization Framework](https://www.rfc-editor.org/rfc/rfc6749): AS, RS, grants, access/refresh tokens, client credentials.
- [RFC 9700 — OAuth 2.0 Security Best Current Practice](https://www.rfc-editor.org/rfc/rfc9700): bảo vệ token, refresh rotation và replay.
- [RFC 7009 — OAuth 2.0 Token Revocation](https://www.rfc-editor.org/rfc/rfc7009): thu hồi OAuth token/grant theo contract.
- [RFC 7662 — OAuth 2.0 Token Introspection](https://www.rfc-editor.org/rfc/rfc7662): opaque token state, introspection và cache.
- [RFC 9449 — OAuth 2.0 DPoP](https://www.rfc-editor.org/rfc/rfc9449): client holder private key và token binding.
- [RFC 8705 — OAuth 2.0 Mutual-TLS](https://www.rfc-editor.org/rfc/rfc8705): mTLS client authentication và certificate-bound tokens.
- [OpenID Connect Core 1.0](https://openid.net/specs/openid-connect-core-1_0.html): ID token, OP signing, issuer/subject và clients.
- [Spring Security Reference — OAuth 2.0 Resource Server JWT](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html): JWT decoder, trusted issuer và token validators.
- [Spring Authorization Server Reference](https://docs.spring.io/spring-authorization-server/reference/): token issuance, JWK management và grant lifecycle theo ứng dụng.
- [OWASP Key Management Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Key_Management_Cheat_Sheet.html): phân loại khóa, storage, backup, rotation và compromise.
- [OWASP Secrets Management Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Secrets_Management_Cheat_Sheet.html): secrets lifecycle, access control, backup và recovery.
- [OWASP Cryptographic Storage Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Cryptographic_Storage_Cheat_Sheet.html): algorithms, keys, encryption at rest và quản lý lifecycle.
