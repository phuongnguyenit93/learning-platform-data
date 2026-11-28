# Key tách khỏi ciphertext (Tách khóa mật mã khỏi dữ liệu đã mã hóa)

## 1. Vì sao phải tách khóa khỏi ciphertext?

**Ciphertext (bản mã)** là dữ liệu đã được biến đổi bằng thuật toán mã hóa. **Key (khóa mật mã)** là yếu tố bí mật quyết định ai có thể giải mã hoặc thực hiện phép toán mật mã tương ứng. Nếu ứng dụng lưu **plaintext encryption key** ngay cùng bản mã, dưới cùng quyền đọc và cùng bản sao lưu, thì một lần rò dữ liệu có thể làm lộ **cả ciphertext và khả năng giải mã**.

Ví dụ thiết kế sai:

~~~json
{
  "documentId": "invoice-901",
  "ciphertext": "BASE64_CIPHERTEXT",
  "aesKeyPlaintextBase64": "BASE64_SECRET_KEY",
  "nonce": "BASE64_NONCE"
}
~~~

**Base64 là encoding, không phải cơ chế giữ bí mật.** Người đọc được bản ghi có thể lấy key rõ và dùng nó giải mã.

Thiết kế đúng tạo **ranh giới bảo mật độc lập**: quyền đọc ciphertext **không mặc nhiên cho phép lấy plaintext key hoặc gọi dịch vụ giải mã**. Thông thường, bản mã được lưu trong database/object storage, còn vật liệu khóa quan trọng được bảo vệ bởi **KMS/HSM** hoặc miền lưu trữ bí mật có IAM, audit, rotation và recovery tách biệt.

Trong chương **Key storage** thuộc module **SECURITY_KEY_MANAGEMENT_FUNDAMENTALS**, nguyên tắc này liên hệ đến toàn bộ vòng đời **tạo, cấp phát, lưu, sử dụng, xoay vòng, thu hồi và hủy khóa**, cùng mật mã đối xứng/bất đối xứng, chữ ký số, DEK/KEK, envelope encryption, quyền truy cập và kiểm toán.

**Ý chính:** “Key tách khỏi ciphertext” nói về **phân tách bí mật và quyền dùng khóa**, không nhất thiết là mọi byte liên quan đến khóa đều phải nằm ở thiết bị vật lý khác.

## 2. Phân biệt plaintext key, wrapped key và metadata

| Thành phần | Ý nghĩa | Có thể lưu cạnh ciphertext? |
|---|---|---|
| **Plaintext DEK** | Khóa dùng trực tiếp mã hóa/giải mã dữ liệu | **Không nên lưu bền vững** cùng bản mã dưới cùng quyền đọc |
| **Plaintext KEK** | Khóa bảo vệ/bọc các DEK | **Không**; bảo vệ riêng trong KMS/HSM hoặc cơ chế tương đương |
| **Encrypted/wrapped DEK** | Bản DEK đã được bọc dưới KEK | **Có thể**, nếu wrap và key policy an toàn |
| **Ciphertext** | Bản mã dữ liệu | Có; đối tượng chính của storage |
| **Nonce/IV** | Tham số thuật toán; với AES-GCM phải duy nhất dưới cùng key | Thường có; không mặc định là bí mật |
| **Authentication tag** | Giá trị xác thực của AEAD | Có; bắt buộc verify khi Decrypt |
| **AAD** | Dữ liệu được xác thực nhưng không được mã hóa | Có nếu không chứa bí mật và encoding ổn định |
| **Key ID/material version** | Tham chiếu xác định khóa cần dùng | Có thể; không phải secret hay proof of authorization |
| **Algorithm/format version** | Cho reader biết định dạng | Có, nhưng chỉ dùng các algorithm đã được cho phép |
| **Public verification key/certificate** | Công khai theo trust policy để Verify | Có thể; **private signing key** vẫn phải được bảo vệ riêng |

> **Ngoại lệ quan trọng không được hiểu sai:** Trong **envelope encryption**, việc đặt **encrypted DEK** cạnh ciphertext là thiết kế thường gặp và hợp lệ. Bí mật cần được bảo vệ riêng là **DEK dạng rõ và KEK/khả năng unwrap**.

Một bản ghi lưu trữ có thể như sau:

~~~text
DATA STORE
+-------------------------------------------------+
| tenant / document ID                            |
| ciphertext + GCM tag                            |
| nonce + AAD schema version                      |
| encryptedDEK + KEK keyRef / material version    |
+-------------------------------------------------+

KMS/HSM / SEPARATE KEY TRUST BOUNDARY
+-------------------------------------------------+
| KEK / protected key material                    |
| IAM, key policy, grants, approved operations    |
| key lifecycle, audit, recovery                  |
+-------------------------------------------------+
~~~

Ứng dụng được ủy quyền có thể xử lý plaintext DEK **tạm thời trong RAM** khi thuật toán yêu cầu; không vì thế mà được phép log DEK hoặc lưu bền vững dạng rõ cạnh ciphertext.

## 3. Threat model: tách khóa bảo vệ trước những sự cố nào?

| Tình huống | Nếu ciphertext và plaintext key cùng quyền | Nếu encrypted DEK + KMS/KEK tách biệt |
|---|---|---|
| Database dump bị lộ | Có thể giải mã trực tiếp | Người có dump chưa tự có quyền unwrap DEK |
| Storage backup bị đánh cắp | Có thể chứa cả key và dữ liệu | Backup chứa bản mã/DEK đã bọc, vẫn cần KEK |
| SQL read-only credential bị lộ | Quyền SELECT có thể tương đương giải mã | Quyền đọc DB không đồng nghĩa quyền KMS |
| Application credential có quyền KMS Decrypt bị chiếm | Có thể giải mã | **Vẫn nguy hiểm**: KMS có thể thành decryption oracle |
| Process memory/heap dump bị lộ | Có thể lấy secret rõ | DEK ngắn hạn trong RAM vẫn có nguy cơ, cần hạn chế |
| Key policy/grant bị thay trái phép | Không có bảo vệ độc lập | Ranh giới KMS có thể bị phá bởi IAM/policy misuse |
| Backup recovery key bị lộ | Có thể mở dữ liệu diện rộng | Phải quản lý riêng recovery key và bản sao |

### 3.1. Tách key không phải biện pháp bảo vệ tuyệt đối

Nếu attacker chiếm **application process** vừa đọc được ciphertext vừa được KMS cho phép Unwrap, attacker có thể lấy plaintext qua API mà **không cần export KEK**. Khi đó cần:

- Business authorization theo user, tenant, object trước khi giải mã.
- KMS IAM/key policy giới hạn theo workload, key, region, purpose.
- Tách quyền KMS key administration và data-plane Decrypt/Unwrap.
- Audit cả thao tác KMS lẫn truy cập dữ liệu; phát hiện hành vi bất thường.
- Hạn chế phạm vi một service có thể giải mã, giảm blast radius.
- Bảo vệ workload identity, token, logs, snapshots và endpoints.

**Để khóa ở KMS giảm một số đường lộ key material; nó không loại bỏ quyền lực của những principal được cấp quyền thực hiện phép toán mật mã.**

### 3.2. Ba mục tiêu cần kiểm tra

- **Confidentiality:** chỉ có bản mã và metadata có đủ lấy plaintext không?
- **Integrity:** một attacker có thể tráo encrypted DEK, keyRef, nonce, AAD hoặc ciphertext mà không bị phát hiện không?
- **Availability:** khi KEK tạm không dùng được hoặc bị hủy, dữ liệu hợp lệ có còn khả năng khôi phục theo chính sách không?

Thiết kế chỉ chú ý bí mật mà hủy KEK khi còn encrypted DEK/backup có thể dẫn tới **mất dữ liệu không thể khôi phục**.

## 4. Các anti-pattern lưu trữ thường gặp

### 4.1. Lưu AES key dạng rõ trong bảng dữ liệu

~~~sql
-- ANTI-PATTERN: Không áp dụng cho hệ thống production.
CREATE TABLE encrypted_documents_bad (
    document_id VARCHAR(120) PRIMARY KEY,
    ciphertext BYTEA NOT NULL,
    nonce BYTEA NOT NULL,
    plaintext_aes_key BYTEA NOT NULL
);
~~~

Nếu tài khoản đọc bảng bị lộ, kẻ tấn công có thể có cả plaintext key và dữ liệu cần giải mã.

### 4.2. Hai file cạnh nhau, cùng quyền và cùng backup

~~~text
/exports/q4/
  report.enc
  report.key
~~~

**Tách tên file không đồng nghĩa tách miền bảo mật** nếu cả hai được đọc hoặc backup bởi cùng identity.

### 4.3. Hard-code key trong source hoặc container image

~~~java
// ANTI-PATTERN: chỉ minh họa lỗi, không dùng production.
final byte[] key = new byte[32]; // Nếu là secret cố định trong source.
~~~

Source, image, CI artifact, release bundle hoặc heap dump có thể tạo nhiều bản sao ngoài kiểm soát. Chuyển hard-coded secret sang environment variable có thể cải thiện triển khai, nhưng chưa giải quyết hết quyền đọc process, runtime injection, logging và backup.

### 4.4. Master password cạnh ciphertext

~~~text
encryptedDEK = Encrypt(DEK, localMasterSecret)
localMasterSecret = một chuỗi đặt cùng config/storage backup
~~~

Dù DEK đã được bọc trên danh nghĩa, nếu secret dùng để unwrap nằm cùng miền quyền, separation vẫn yếu.

### 4.5. Sinh DEK từ tenant ID hoặc từ khóa

**SHA-256(tenantId)**, hostname, timestamp, password phổ biến hoặc chuỗi tên ứng dụng không tạo DEK có entropy cao. Dù không lưu key cạnh bản mã, đối thủ vẫn có thể **tính lại key** khi biết quy luật. **Key storage an toàn không bù được key generation yếu**.

## 5. Ranh giới kiến trúc: data plane, key plane và business authorization

Một kiến trúc KMS thường phân chia:

- **Data plane:** ứng dụng và database/object storage xử lý ciphertext, metadata, encrypted DEK và quyền truy cập dữ liệu.
- **Key control plane:** KMS/HSM, key policy, grants, trạng thái key, rotation, revocation, backup.
- **Business authorization plane:** ứng dụng xác định user/tenant có được xem object cụ thể không.
- **Audit plane:** hệ thống ghi logs có bảo vệ, có thể được quản trị độc lập.

~~~mermaid
flowchart LR
    U["User / workload"] --> A["Application: authn + tenant authz"]
    A --> D["Storage: ciphertext + wrapped DEK"]
    A --> K["KMS/HSM: KEK + IAM"]
    K --> A
    O["Data/key owners"] --> P["Policy + approval"]
    P --> K
    L["Independent audit"] --> E["KMS and app events"]
    K --> E
    A --> E
~~~

### 5.1. Phân tách quyền quan trọng hơn đặt ở hai máy

Nếu storage admin cũng có quyền **ChangeKeyPolicy/GrantDecrypt** và đọc ciphertext, một tài khoản có thể chiếm cả hai lớp. Kiểm tra **effective IAM permissions**, group membership, role assumption, cross-account grants, quyền thay đổi policy và audit sinks.

Có thể tách cloud account/project, operator, role và backup policy để giảm rủi ro, nhưng **cùng một super-admin có toàn quyền đối với hai account** vẫn cần kiểm soát bù trừ.

## 6. Envelope encryption: nguyên lý và luồng ghi

Envelope encryption dùng:

- **DEK (Data Encryption Key)** để mã hóa dữ liệu bằng AEAD, ví dụ AES-GCM.
- **KEK (Key Encryption Key)** để bảo vệ DEK bằng key wrap/encryption thích hợp.
- **Encrypted DEK** có thể lưu cạnh ciphertext.
- **Key reference/material version** chỉ tới KEK thích hợp khi cần phục hồi.

Biểu thức khái niệm:

\[
(C,T) = \mathrm{AEAD\_Encrypt}(DEK,N,P,A)
\]

\[
E_{DEK} = \mathrm{Wrap}_{KEK}(DEK,\mathrm{context})
\]

Trong đó \(P\) là plaintext, \(N\) là nonce, \(C\) là ciphertext, \(T\) là tag, \(A\) là AAD. Ký hiệu Wrap không hàm ý mọi KMS sử dụng cùng thuật toán hoặc API.

### 6.1. Luồng mã hóa

~~~mermaid
sequenceDiagram
    participant A as App được ủy quyền
    participant K as KMS/HSM
    participant S as Data storage
    A->>A: Authn + business authorization
    A->>K: GenerateDataKey hoặc cơ chế tương đương
    K-->>A: Plaintext DEK tạm + encrypted DEK nếu API hỗ trợ
    A->>A: AES-GCM encrypt, nonce/AAD theo policy
    A->>S: Ciphertext + tag + nonce + encrypted DEK + keyRef
    A->>A: Giảm thời gian giữ plaintext DEK
~~~

Nếu KMS **trả plaintext DEK**, nó tồn tại tạm trong process và cần bảo vệ khỏi log, memory dump, swap, crash report và lỗi cleanup. Một số provider/thiết kế cho phép **phép toán trong HSM hoặc client có key handle mà không xuất key rõ**.

### 6.2. Luồng giải mã

~~~mermaid
sequenceDiagram
    participant A as Authorized reader
    participant S as Data storage
    participant K as KMS/HSM
    A->>A: Kiểm tra quyền user/tenant/object
    A->>S: Read encrypted record
    S-->>A: Ciphertext, tag, nonce, encrypted DEK, keyRef
    A->>A: Kiểm tra format, keyRef và binding
    A->>K: Unwrap encrypted DEK với context được phép
    K-->>A: Plaintext DEK tạm nếu API cho phép
    A->>A: AES-GCM Decrypt + verify tag/AAD
    A-->>A: Chỉ cung cấp plaintext khi xác thực thành công
~~~

**Không trả plaintext trước khi AEAD tag được xác thực**. Với streaming decryption, chỉ sử dụng dữ liệu đã được xác thực theo giao thức/thư viện phù hợp.

### 6.3. KMS API không giống nhau

Tên **GenerateDataKey** chỉ có ở những provider hỗ trợ. Những KMS/HSM khác có API Generate, Encrypt/Decrypt, Wrap/Unwrap hoặc chỉ cho xử lý key trong miền phần cứng. Thiết kế phải dựa trên **capability thực tế**, không suy rằng mọi KEK đều exportable hay mọi hệ thống cho phép plaintext DEK rời provider.

## 7. Định dạng bản ghi ciphertext an toàn

Bản ghi dữ liệu cần đủ metadata cho giải mã lâu dài nhưng **không chứa plaintext DEK hoặc KEK**:

~~~json
{
  "formatVersion": 2,
  "algorithm": "AES-256-GCM",
  "keyRef": "kms/prod/orders-kek",
  "materialVersion": "v7",
  "encryptedDek": "BASE64_WRAPPED_DEK",
  "nonce": "BASE64_96_BIT_NONCE",
  "ciphertextAndTag": "BASE64_CIPHERTEXT_TAG",
  "tenantId": "tenant-42",
  "objectId": "invoice-901",
  "aadVersion": 2
}
~~~

Đây là **schema minh họa**, không phải API chuẩn của mọi provider.

| Trường | Tại sao cần | Kiểm soát |
|---|---|---|
| formatVersion | Hỗ trợ schema/key rotation | Không chấp nhận downgrade thuật toán |
| algorithm | Chọn AEAD đúng | Chỉ từ allowlist được duyệt |
| keyRef/materialVersion | Tìm KEK thích hợp | Ràng buộc scope; không cho caller tùy ý chọn key |
| encryptedDek | Chứa DEK đã bọc | Kiểm tra integrity/context theo cơ chế wrap |
| nonce/IV | AEAD decryption | GCM phải không trùng dưới từng DEK |
| ciphertext/tag | Dữ liệu và bằng chứng xác thực | Tag bắt buộc được xác minh |
| tenant/object | Liên kết nghiệp vụ | Kiểm tra từ nguồn đáng tin, ràng buộc AAD |
| aadVersion | Đảm bảo tái tạo đúng AAD | Canonical encoding nhất quán |

**Nonce và tag không phải plaintext key.** Trong AES-GCM chúng thường được lưu cạnh ciphertext. Nonce không cần bí mật, nhưng uniqueness dưới mỗi key là bắt buộc; tag không được bỏ qua.

### 7.1. Metadata không được tự quyết định quyền

Một attacker có thể sửa keyRef, tenantId hoặc algorithm trong bản ghi. Hệ thống phải:

1. Kiểm tra keyRef/tenant với **identity và object ownership**.
2. Dùng AAD để xác thực những trường liên quan theo schema.
3. Nếu provider hỗ trợ, ràng buộc encrypted DEK với **KMS encryption context**.
4. Kiểm tra **algorithm/formatVersion allowlist**, không chấp nhận downgrade.
5. Từ chối bản ghi có tag sai; không fallback về chế độ mã hóa yếu.

**AAD là dữ liệu được xác thực nhưng không được mã hóa.** AAD không thay business authorization, không làm thông tin công khai thành secret.

## 8. Key reference, alias và quyền Decrypt

Một key ID như:

~~~text
kms/prod/region-x/orders-kek
~~~

là **tham chiếu**, không phải plaintext key hay giấy phép giải mã. Muốn sử dụng KMS, caller vẫn cần quyền phù hợp, và muốn xem business data phải được ứng dụng kiểm tra quyền.

### 8.1. Alias không luôn chỉ một vật liệu duy nhất

Alias có thể trỏ sang KEK mới sau rotation. Bản ghi ciphertext lịch sử phải chứa **metadata đủ để giải mã với key/version chính xác**, theo cách provider thực sự quản lý version. Không suy rằng alias “latest” luôn phù hợp cho mọi encrypted DEK cũ.

### 8.2. Key ID không bí mật nhưng vẫn là metadata nhạy cảm

Key reference có thể tiết lộ account/tenant/kiến trúc; cần giới hạn khả năng xem trong logs/dashboard theo chính sách, nhưng **che giấu key ID không thay bảo vệ key material hoặc IAM**.

## 9. Tách vật lý và tách mật mã

| Cách làm | Lợi ích | Giới hạn |
|---|---|---|
| Plaintext key và ciphertext cùng database/file | Dễ viết demo | Chỉ một lần rò storage đã có thể giải mã |
| Key dạng rõ ở secret store khác nhưng cùng quyền admin/backup | Có thêm ACL riêng | Một identity vẫn có thể nắm cả key và data |
| Encrypted DEK cạnh ciphertext, KEK trong KMS/HSM | Ranh giới key riêng, IAM/audit và rotation | Service có quyền Unwrap vẫn phải được bảo vệ |
| Crypto operations trong HSM, không export key | Thu hẹp khả năng lộ key bytes | Không ngăn lạm dụng API Sign/Decrypt |
| Client-side key không nằm trên server | Server compromise chưa mặc nhiên lấy key | Recovery, client compromise, key distribution phức tạp |

**Khoảng cách vật lý chỉ hữu ích khi quyền và miền tin cậy cũng khác nhau.**

### 9.1. Client-side encryption

Trong kiến trúc E2EE phù hợp, server chỉ có bản mã còn key được quản lý ở client. Nhưng client endpoint vẫn có thể bị chiếm, key recovery và key sharing cần protocol bảo mật, và server không thể xử lý plaintext thông thường. **Không gọi một hệ thống là zero-knowledge nếu server vẫn có quyền lấy DEK rõ qua API hoặc secret store**.

## 10. IAM và separation of duties

| Vai trò | Quyền phù hợp | Quyền không mặc nhiên cần |
|---|---|---|
| Storage reader | Đọc ciphertext và encrypted DEK theo dataset | KMS Decrypt/Unwrap rộng |
| Encrypt workload | GenerateDataKey/Wrap/Encrypt theo key scope | DeleteKey/ChangeKeyPolicy |
| Decrypt workload | Decrypt/Unwrap đúng tenant và object policy | Tự cấp grants hoặc sửa key policy |
| KMS operator | Rotate, state management theo approval | Xem plaintext business data |
| IAM admin | Quản lý identities/roles có kiểm soát | Dùng quyền KMS giải mã tùy ý |
| Data/key owner | Purpose, retention và quyết định lifecycle | Trực tiếp truy cập mọi private key |
| Auditor | Xem usage/changes và chứng cứ | Decrypt/Sign hoặc sửa logs |

**Effective permissions** quan trọng hơn tên role. Một user không có Decrypt trực tiếp nhưng có thể **tự sửa IAM/key policy hoặc AssumeRole** để lấy Decrypt vẫn có một đường vượt SoD.

### 10.1. Quyền của workload khác quyền của end user

Service có quyền KMS Decrypt **không chứng minh** end user được xem hồ sơ cụ thể. Thứ tự đúng: xác thực user → kiểm tra tenant/object/biz policy → đọc encrypted record → KMS unwrap theo workload IAM → AEAD verify → chỉ trả plaintext khi hợp lệ → audit.

Đừng biến dịch vụ thành **decryption oracle** bằng API nhận encryptedDek/keyRef tùy ý rồi gọi KMS mà không kiểm tra quyền dữ liệu.

## 11. Multi-tenant: AAD, encryption context và confused deputy

Một ứng dụng đa tenant có thể dùng KEK riêng theo tenant/domain để giảm blast radius, hoặc KEK chung với kiểm soát context/IAM đủ chặt nếu thiết kế cho phép.

Ví dụ rủi ro: user tenant A gửi ciphertext/encrypted DEK của tenant B. Nếu app có quyền KMS Unwrap cả hai và không kiểm tra ownership, service có thể giải mã sai tenant.

Các biện pháp:

- Kiểm tra object ownership/authorization từ danh tính đáng tin.
- Ràng buộc tenant/object/format version với **AAD** của ciphertext.
- Ràng buộc encrypted DEK với KMS **encryption context** khi API hỗ trợ.
- Không tin tenantId/keyRef chỉ vì client tự gửi.
- Phân tách key scope và grants khi phù hợp; audit cross-tenant denied requests.

### 11.1. Encryption context không mặc nhiên bí mật

Nhiều KMS ghi context vào audit. Không đặt password, access token, PII hoặc secret vào context nếu provider không bảo vệ nó như dữ liệu bí mật.

**KMS encryption context** và **AAD của data AES-GCM** là hai phạm vi độc lập; phải tự thiết kế liên hệ giữa chúng, không suy rằng một bên tự xác thực bên kia.
### 11.2. Canonical AAD

Nếu Encrypt dùng các byte:

~~~text
tenant=42|object=901|version=2
~~~

mà Decrypt đổi thứ tự trường, authentication tag sẽ không khớp. Cần **encoding byte-level có schema và version**, không nối những giá trị không kiểm soát bằng dấu phân tách mơ hồ. Khi dùng JSON, chỉ coi canonical nếu có quy tắc chuẩn hóa cụ thể.

## 12. Java 17: thiết kế envelope encryption mà không lưu key rõ cùng ciphertext

Ví dụ dưới đây minh họa kiến trúc **Java JCA + KMS abstraction**. Application yêu cầu một key service sinh DEK, mã hóa dữ liệu bằng AES-GCM, rồi **chỉ lưu encrypted DEK** và metadata. Không có implementation KMS giả dùng plaintext KEK trong cùng database, vì như vậy dễ tạo hiểu nhầm rằng một demo key store cũng có ranh giới bảo mật như KMS thật.

**Lưu ý:** Mã này là **mẫu service có thể biên dịch bằng Java 17** khi được ghép vào file Java phù hợp, nhưng interface **KeyService chưa có implementation**. Trong production, cần SDK/cloud KMS/HSM hoặc thư viện được đánh giá thực sự thực hiện GenerateDataKey/Unwrap với IAM, auditing và encryption context. Không được tự tạo KEK hard-code để thay thế.

~~~java
import java.nio.ByteBuffer;
import java.nio.charset.StandardCharsets;
import java.security.SecureRandom;
import java.util.Arrays;
import java.util.Map;

import javax.crypto.Cipher;
import javax.crypto.spec.GCMParameterSpec;
import javax.crypto.spec.SecretKeySpec;

public final class EnvelopeStorageService {
    private static final SecureRandom RNG = new SecureRandom();
    private static final int GCM_NONCE_BYTES = 12;
    private static final int GCM_TAG_BITS = 128;
    private static final int FORMAT_VERSION = 2;

    // KeyService do SDK KMS/HSM thật triển khai.
    // KEK không được trả dưới dạng plaintext cho ứng dụng.
    public interface KeyService {
        GeneratedDataKey generateDataKey(
            String kekRef, Map<String, String> context
        ) throws Exception;

        byte[] unwrapDataKey(
            String kekRef, byte[] encryptedDek,
            Map<String, String> context
        ) throws Exception;
    }

    // Plaintext DEK chỉ dùng tạm, không lưu bền vững.
    public record GeneratedDataKey(
        byte[] plaintextDek,
        byte[] encryptedDek
    ) {}

    // Đối tượng lưu ở database/object store:
    // KHÔNG có plaintext DEK/KEK.
    public record EncryptedRecord(
        int formatVersion,
        String algorithm,
        String kekRef,
        String tenantId,
        String objectId,
        byte[] encryptedDek,
        byte[] nonce,
        byte[] ciphertextAndTag
    ) {}

    private static Map<String, String> context(
            String tenantId, String objectId) {
        return Map.of(
            "purpose", "document-encryption",
            "tenant", tenantId,
            "object", objectId
        );
    }

    // Định dạng AAD length-prefixed có version,
    // tránh nhập nhằng khi ghép chuỗi.
    private static byte[] aad(
            String tenantId, String objectId) {
        byte[] tenant = tenantId.getBytes(StandardCharsets.UTF_8);
        byte[] object = objectId.getBytes(StandardCharsets.UTF_8);

        return ByteBuffer.allocate(
            1 + 4 + tenant.length + 4 + object.length
        ).put((byte) FORMAT_VERSION)
         .putInt(tenant.length)
         .put(tenant)
         .putInt(object.length)
         .put(object)
         .array();
    }

    public static EncryptedRecord encrypt(
            KeyService kms,
            String kekRef,
            String tenantId,
            String objectId,
            byte[] plaintext) throws Exception {

        if (kms == null || kekRef == null
                || tenantId == null || objectId == null
                || plaintext == null) {
            throw new IllegalArgumentException("Missing input");
        }

        GeneratedDataKey dataKey =
            kms.generateDataKey(
                kekRef, context(tenantId, objectId));

        if (dataKey == null
                || dataKey.plaintextDek() == null
                || dataKey.plaintextDek().length != 32
                || dataKey.encryptedDek() == null
                || dataKey.encryptedDek().length == 0) {
            throw new IllegalStateException(
                "Unexpected KMS data-key response");
        }

        byte[] nonce = new byte[GCM_NONCE_BYTES];
        RNG.nextBytes(nonce);

        try {
            Cipher cipher = Cipher.getInstance(
                "AES/GCM/NoPadding");
            cipher.init(
                Cipher.ENCRYPT_MODE,
                new SecretKeySpec(dataKey.plaintextDek(), "AES"),
                new GCMParameterSpec(GCM_TAG_BITS, nonce)
            );
            cipher.updateAAD(aad(tenantId, objectId));
            byte[] ciphertextAndTag = cipher.doFinal(plaintext);

            // Chỉ wrapped DEK, ciphertext và metadata được lưu.
            return new EncryptedRecord(
                FORMAT_VERSION,
                "AES-256-GCM",
                kekRef,
                tenantId,
                objectId,
                dataKey.encryptedDek().clone(),
                nonce,
                ciphertextAndTag
            );
        } finally {
            // Best effort đối với mảng ta kiểm soát; JCE có
            // thể giữ bản sao khác trong bộ nhớ.
            Arrays.fill(dataKey.plaintextDek(), (byte) 0);
        }
    }

    public static byte[] decrypt(
            KeyService kms,
            EncryptedRecord record,
            String authorizedTenantId,
            String authorizedObjectId
    ) throws Exception {

        // BẮT BUỘC: tầng service phải xác thực danh tính
        // và kiểm tra user có quyền đọc object này.
        if (kms == null || record == null
                || !authorizedTenantId.equals(record.tenantId())
                || !authorizedObjectId.equals(record.objectId())) {
            throw new SecurityException("Object scope mismatch");
        }

        if (record.formatVersion() != FORMAT_VERSION
                || !"AES-256-GCM".equals(record.algorithm())
                || record.nonce() == null
                || record.nonce().length != GCM_NONCE_BYTES
                || record.ciphertextAndTag() == null
                || record.ciphertextAndTag().length < 16
                || record.encryptedDek() == null
                || record.encryptedDek().length == 0) {
            throw new SecurityException("Invalid record format");
        }

        // Production: còn phải ràng buộc keyRef với policy,
        // tenant, owner và allowlist của ứng dụng.
        byte[] plaintextDek = kms.unwrapDataKey(
            record.kekRef(),
            record.encryptedDek(),
            context(record.tenantId(), record.objectId())
        );

        if (plaintextDek == null || plaintextDek.length != 32) {
            throw new SecurityException("Invalid DEK");
        }

        try {
            Cipher cipher = Cipher.getInstance(
                "AES/GCM/NoPadding");
            cipher.init(
                Cipher.DECRYPT_MODE,
                new SecretKeySpec(plaintextDek, "AES"),
                new GCMParameterSpec(
                    GCM_TAG_BITS, record.nonce())
            );
            cipher.updateAAD(
                aad(record.tenantId(), record.objectId())
            );
            // Nếu tag sai, doFinal ném exception;
            // không được trả plaintext chưa xác thực.
            return cipher.doFinal(record.ciphertextAndTag());
        } finally {
            Arrays.fill(plaintextDek, (byte) 0);
        }
    }
}
~~~

### 12.1. Giải thích ranh giới bảo mật của ví dụ

**Application có thể nhận plaintext DEK tạm**, nhưng không nhận KEK rõ. **Storage chỉ giữ encrypted DEK** và ciphertext; một database reader không thể lấy plaintext DEK chỉ từ bản ghi nếu KMS unwrap được bảo vệ đúng.

**Lớp KeyService chịu trách nhiệm bảo vệ KEK**: key origin, crypto API, IAM grants, encryption context, logging và rotation phải đúng provider. Bản mẫu không thể mô phỏng hoặc chứng minh toàn bộ yêu cầu đó.

### 12.2. Những gì production cần bổ sung

- Xác thực **principal và quyền trên tenant/object** trước khi gọi decrypt; tên tham số authorizedTenantId chưa tự tạo ra authorization.
- **Key reference allowlist và ownership binding**; không cho attacker chọn một KEK ngoài scope.
- Giới hạn **kích thước plaintext, ciphertext, metadata và KMS response** để chống resource exhaustion.
- Định dạng lưu trữ **immutable/versioned**, keyMaterialVersion và mã hóa serialization an toàn.
- **Nonce strategy toàn hệ thống**: ví dụ mỗi object một DEK mới hoặc cơ chế nonce không trùng đã được thiết kế cho multiwriter/restore.
- Kiểm soát **JVM heap dump, swap, logs, tracing và memory lifetime**; Arrays.fill chỉ cố gắng xóa mảng do code sở hữu, không bảo đảm xóa mọi bản sao nội bộ JCE.
- KMS context API thật có thể yêu cầu format/syntax khác; chính sách nào dùng context phải được kiểm thử hai chiều.
- **Idempotency và retry** của GenerateDataKey/Encrypt: không vô tình làm thay keyRef/nonce làm ghi sai record.
- **Quotas, timeouts, cancellation và fail-safe** khi KMS không sẵn sàng; không fallback sang key hard-code.
- **Authentication errors** không được làm lộ ciphertext data hoặc thông tin giúp đoán tenant qua thông báo chi tiết.
- **Observability**: audit KMS và ứng dụng qua correlation ID nhưng không lưu plaintext DEK hoặc bản rõ dữ liệu.

### 12.3. Ranh giới của AES-GCM 96-bit nonce

12-byte nonce ngẫu nhiên trong ví dụ là cách minh họa đơn giản, có xác suất trùng thấp ở số lượng bản ghi vừa phải. Tuy nhiên, **AES-GCM yêu cầu duy nhất nonce dưới cùng DEK**. Ở hệ thống có nhiều writer, lượng lớn bản ghi hoặc clone VM, phải xây dựng chiến lược đáp ứng yêu cầu uniqueness và usage limits.

Nếu **mỗi object có DEK được sinh độc lập**, nguy cơ trùng nonce dưới cùng key giảm theo mô hình; nhưng điều này không cho phép coi nonce là optional hoặc bỏ qua phân tích generator/khối lượng dữ liệu.

## 13. Khóa trong RAM, cache và secret manager

Tách key khỏi storage bền vững chưa giải quyết mọi bản sao **plaintext key trong runtime**.

### 13.1. Plaintext DEK trong JVM

Với Java, DEK có thể xuất hiện trong:

- Mảng byte do KMS SDK trả về.
- Đối tượng SecretKey/SecretKeySpec hoặc native crypto provider.
- Heap dump, diagnostic traces, crash reporting, swap hoặc runtime snapshots.
- Buffer khi serialize/logging nhầm.
- Cache DEK hoặc connection/session state.

Kiểm soát cần thiết:

1. Chỉ giải bọc key **sau khi quyền dữ liệu đã được kiểm tra**.
2. Giảm phạm vi hàm và thời gian sống của DEK.
3. Tránh giữ DEK toàn cục/static cho nhiều tenant hoặc toàn bộ đời ứng dụng.
4. Không đưa key bytes vào String, logs, exception messages, telemetry hoặc tracing.
5. Cân nhắc API/key handle không xuất plaintext khi phù hợp.
6. Cấu hình heap dump, crash reports và debug quyền hạn chế ở production.
7. Xóa best-effort những mảng byte code kiểm soát, không tuyên bố zeroization tuyệt đối trong JVM.

### 13.2. Caching plaintext DEK có nên không?

Cache có thể giảm latency/chi phí gọi KMS, nhưng tạo **bản sao secret tồn tại lâu hơn** và tăng tác động nếu process bị chiếm. Nếu cần data-key caching:

- Thiết kế theo **scope** (tenant, dataset, key version), TTL, maximum uses/bytes.
- Có kích hoạt **invalidate khi revoke/rotate** và khi worker mất trust.
- Giới hạn quyền đọc cache; không chia sẻ plaintext DEK bừa bãi giữa microservices.
- Không để cache tồn tại vô hạn hoặc ghi xuống disk/swap theo cách không kiểm soát.
- Đánh giá khả năng provider/SDK cung cấp caching với giới hạn rõ.

**Một KMS operation bị deny không tự xóa DEK đã cache trong ứng dụng.** Quản lý cache là một phần quan trọng khi có incident.

### 13.3. Secret manager phù hợp cho loại secret nào?

Một secret manager có thể hữu ích cho **HMAC secret, API credential, database secret và một số khóa ứng dụng**, nếu có IAM, versioning, rotation, audit. Nhưng không nên mặc định **chứa plaintext KEK trong secret manager** tương đương với bảo vệ KEK trong KMS/HSM ở mọi mô hình. Cần đánh giá ranh giới, exportability, API access, backups và người quản trị.

Nếu ứng dụng buộc phải lấy secret rõ, đó vẫn là một **plaintext exposure point** cần quản lý.

## 14. Tách private signing key khỏi tài liệu và chữ ký

Nguyên tắc “key tách khỏi ciphertext” có một **phiên bản tương ứng trong chữ ký số**: private signing key phải được bảo vệ riêng với tài liệu, digest, chữ ký và public verification key.

~~~mermaid
flowchart LR
    D["Document / digest"] --> A["Authorized signing service"]
    B["Business approval"] --> A
    A --> H["HSM/KMS Sign với private key"]
    H --> S["Signature"]
    S --> R["Document + signature + key ID + certificate"]
    P["Public key / trust store"] --> V["Verifier"]
    R --> V
~~~

- **Private key:** không nên nằm trong tài liệu, database chứa chứng từ hoặc logs.
- **Signature:** không phải private key; có thể được lưu cùng tài liệu.
- **Public key/certificate:** có thể phân phối công khai qua một **trust channel đáng tin**.
- **Key ID:** hỗ trợ verifier chọn đúng public key; không phải bằng chứng danh tính.
- **HSM Sign:** hạn chế việc xuất private key nhưng không tự bảo đảm nội dung ký đã được business approver duyệt.

### 14.1. Không gộp Sign và business approval

Nếu một service có quyền HSM Sign và API cho phép ký dữ liệu tùy ý, kẻ chiếm service có thể tạo chữ ký **hợp lệ về toán học** cho chứng từ trái phép. Cần ràng buộc approval với **nội dung/digest, người duyệt, tenant, mục đích, key version và thời hạn**.

### 14.2. Private key bị lộ cần xử lý trust

Disable private key trong HSM **không ngăn** người đã lấy bản sao private key tạo chữ ký ở bên ngoài. Phải update verifier/JWKS/trust store, xử lý certificate revocation và đánh giá chữ ký lịch sử theo policy.

### 14.3. Public key có thể lưu với tài liệu nhưng trust vẫn độc lập

Một tài liệu có thể chứa public key đi kèm để tiện xác minh, nhưng nếu verifier **tự tin public key do tài liệu cung cấp**, attacker có thể tự ký rồi nhúng key của mình. Verifier phải có **nguồn xác thực danh tính người ký** độc lập với tài liệu không đáng tin.

## 15. Backup, archive và disaster recovery

Một lỗi hay gặp là tách plaintext key khỏi database chính nhưng **bản backup tập trung lại chứa cả ciphertext và bản sao key rõ**. Khi đó boundary chỉ tồn tại ở đường vận hành chính, không tồn tại trong DR.

### 15.1. Cần kiểm kê cả ba loại dữ liệu

1. **Ciphertext/encrypted DEK backups:** các bản sao đã mã hóa được lưu dài hạn.
2. **KEK/key-material backup hoặc recovery capability:** cơ chế khôi phục key có quyền giải mã.
3. **Metadata và configuration:** key references, key versions, policies, trust/credential settings.

Nếu mất cả **KEK và recovery path**, một encrypted DEK có thể không còn giải bọc được dù database backup đầy đủ.

### 15.2. Phân tách backup và recovery authority

| Backup design | Nguy cơ | Kiểm soát |
|---|---|---|
| DB snapshot và plaintext KEK backup cùng bucket | Một lần rò bucket có cả key và ciphertext | Không giữ plaintext KEK cạnh dữ liệu; phân tách scope |
| KEK chỉ có một bản duy nhất, không có recovery policy | KMS outage/destruction có thể làm mất dữ liệu | DR plan theo provider, multi-region nếu hỗ trợ |
| Recovery keys do một operator nắm toàn bộ | Lạm dụng đường khôi phục | Dual control/split knowledge khi phù hợp, audit |
| Encrypted DEK được sao lưu nhưng keyRef/version bị mất | Không biết KEK cần unwrap | Backup metadata schema và key inventory |
| Cross-region replication không đồng bộ key availability | Bản mã có nhưng KEK không phục vụ | Test restore theo vùng, version và IAM |

### 15.3. Diễn tập restore có ý nghĩa hơn nhìn trạng thái backup thành công

Một bài test restore nên chứng minh:

- Có thể tìm bản ghi, encrypted DEK và đúng key reference/material version.
- KMS/HSM ở khu vực dự phòng có **key material hoặc cơ chế hợp lệ** để unwrap.
- IAM grants cho recovery principal được phê duyệt, không mở quyền mặc định.
- AAD, nonce, tag và format version được phục dựng chính xác.
- Dữ liệu sau restore có **integrity** và đúng tenant/object.
- Không sao chép plaintext KEK/DEK sang công cụ hỗ trợ thiếu kiểm soát.
- Audit ghi nhận recovery operation, actor và quyết định.

**Backup thành công không đồng nghĩa restore sẽ thành công** nếu key material đã bị hủy hoặc quyền KMS không còn hợp lệ.

## 16. Rotation của KEK và DEK khi key tách khỏi ciphertext

### 16.1. Rotation KEK theo kế hoạch

Với envelope encryption, có thể chuyển từ KEK v1 sang v2:

1. Generate KEK v2 trong KMS/HSM, đặt key policy và owner đúng.
2. Sử dụng KEK v2 để wrap **DEK mới**.
3. Với DEK cũ, **unwrap/rewrap** theo cơ chế được phê duyệt nếu cần.
4. Cập nhật encrypted DEK/keyRef/materialVersion đúng cách.
5. Verify decrypt dữ liệu cũ/backup và ngăn producer dùng KEK v1 cho thao tác mới.
6. Retire KEK v1, chỉ giữ usage lịch sử có giới hạn nếu còn phụ thuộc.
7. Hủy khi inventory/retention/restore đã được xác nhận.

**Nếu DEK chưa lộ**, rewrap DEK có thể đủ cho rotation KEK theo kế hoạch, không nhất thiết phải mã hóa lại toàn bộ dữ liệu.

### 16.2. Rotation DEK

Đổi DEK thường đòi hỏi **re-encrypt dữ liệu** với DEK mới, nonce/tag/AAD mới theo thiết kế. Chỉ đổi encrypted DEK bọc bên ngoài **không làm thay DEK** đang mã hóa ciphertext.

### 16.3. Khi khóa bị lộ, kế hoạch khác rotation thường

Nếu plaintext DEK bị lộ, chỉ rewrap nó dưới KEK mới **không** khắc phục bản sao DEK đối thủ đã có. Cần đánh giá **thay DEK và re-encrypt dữ liệu**, cùng thiệt hại có thể đã xảy ra.

Nếu plaintext KEK bị lộ, đối thủ có thể có KEK và những encrypted DEK đã lấy từ trước; chỉ rewrap ở thời điểm sau có thể không bảo vệ được dữ liệu lịch sử mà đối thủ đã sao chép. Phải xác định blast radius và thay các DEK trong phạm vi có nguy cơ.

### 16.4. Tránh delete key trước khi migrate

KMS state PENDING_DELETION không đồng nghĩa đã hủy thật. Không được đặt DESTROYED khi provider chưa xác nhận hủy hoặc khi encrypted DEK/backup vẫn phụ thuộc. Tách key khỏi data store tạo **khả năng hủy key có kiểm soát**, nhưng cũng tạo **rủi ro mất data vĩnh viễn nếu hủy nhầm**.

## 17. Crypto-shredding: hủy key để làm dữ liệu không thể đọc

**Crypto-shredding** là cách làm dữ liệu mã hóa không thể khôi phục bằng việc hủy **vật liệu khóa duy nhất còn cho phép giải mã**, thay vì nhất thiết ghi đè từng byte ciphertext.

Cơ chế này chỉ có cơ sở khi:

- Dữ liệu được mã hóa với DEK/KEK có nguồn và thuật toán thích hợp.
- Không còn **bản sao plaintext key**, plaintext data hoặc đường recovery hợp lệ khác.
- Không có KEK/DEK dự phòng, exported key hoặc cache đang phục vụ giải mã ngoài phạm vi hủy.
- Mọi encrypted DEK trong backup cần xử lý đều nằm trong phạm vi chính sách.
- Key scope không bao trùm dữ liệu cần giữ của tenant/đối tượng khác.
- Provider/backup controls có bằng chứng phù hợp về việc hủy key material.

**Không hủy một KEK dùng chung để xóa dữ liệu của một tenant nếu KEK vẫn bảo vệ DEK của tenant khác**. Có thể cần DEK riêng theo object/tenant và quy trình hủy đúng scope.

### 17.1. Chỉ xóa key reference không phải crypto-shredding

Nếu registry xóa keyRef nhưng KEK còn hoạt động, key material hoặc bản sao có thể vẫn giải mã được. Việc hủy phải diễn ra **tại miền thực sự bảo vệ vật liệu**, có xác nhận và audit.

### 17.2. Bản sao key đã rò không thể bị thu hồi từ xa

Disable/Delete ở KMS không thể xóa KEK/DEK mà kẻ tấn công đã tải xuống. Crypto-shredding không đảo ngược confidentiality loss đã xảy ra.

## 18. Multi-region, replicated storage và key availability

Khi ciphertext được replicated sang region khác, cần hỏi **đường giải mã ở region đích có khả dụng và đúng policy không?**

- Provider có hỗ trợ multi-region key, replica key hoặc import/recovery không?
- Key ID/version và encryption context có tương thích?
- Có grants/IAM riêng cho DR role và workload theo vùng?
- Khóa cũ bị disable/revoked ở một vùng có đồng bộ hiệu lực theo thiết kế không?
- Storage snapshot và encrypted DEK có được copy đầy đủ metadata?
- Nếu một KMS region không sẵn sàng, hệ thống fail-safe hay tự mở fallback không được duyệt?

**Không copy plaintext KEK giữa vùng bằng một script tự viết chỉ để sửa lỗi DR.** Nếu cần high availability, dùng mô hình key replication/recovery được provider hỗ trợ và đã được kiểm chứng, cùng SoD/audit phù hợp.

### 18.1. Eventual consistency và cache

Khi Rotate/Revoke, ứng dụng có thể còn cache DEK hoặc alias mapping cũ. Cần theo dõi:

- Writer còn dùng key version cũ?
- Reader có thể xử lý encrypted DEK lịch sử đúng policy?
- Key/material version và operation revision có được cập nhật không?
- Cache nào phải invalidate, có service nào offline?
- Provider đã thực sự chặn thao tác ở mọi đường thực thi chưa?

Không coi update registry hoặc event ACK là bằng chứng mọi client đã chuyển.

## 19. Logging, audit và forensic evidence

Tách key khỏi ciphertext cần có **bằng chứng chứng minh** quyền được sử dụng đúng cách, không chỉ một sơ đồ kiến trúc.

Một event minh họa:

~~~json
{
  "eventType": "KMS_DATA_KEY_UNWRAP",
  "operationId": "crypto-op-901",
  "keyRef": "kms/prod/orders-kek",
  "keyMaterialVersion": "v7",
  "actor": "orders-service-prod",
  "tenantRef": "tenant-42",
  "objectRef": "invoice-901",
  "reason": "AUTHORIZED_READ",
  "providerResult": "SUCCESS",
  "occurredAt": "2026-11-28T04:00:00Z"
}
~~~

Đây là định dạng minh họa, không phải payload mặc định của mọi KMS. Tùy nhu cầu riêng tư, object/tenant references có thể cần pseudonymization hoặc hạn chế người đọc logs.

### 19.1. Audit nên cho phép trả lời

1. Ai tạo/activate/rotate/revoke KEK và DEK?
2. Ai được cấp quyền Unwrap/Decrypt và vì sao?
3. Có những lần gọi KMS từ principal, region, workload hoặc tenant bất thường không?
4. KeyRef/material version đã dùng để giải mã đối tượng nào?
5. Có policy/grants thay đổi gần thời điểm sự cố không?
6. Các bản sao plaintext key có thể tồn tại ở đâu (cache/heap/log/backup)?
7. Khi hủy khóa, có bằng chứng provider và dependency clearance không?
8. Khi restore, KMS đã được sử dụng theo đúng quyền DR chưa?

### 19.2. Những gì không nên ghi

**Không log plaintext DEK/KEK, private signing key, HMAC secret, seed RNG, bearer token còn hiệu lực hoặc plaintext nhạy cảm** để debug. Một log chứa key rõ có thể phá toàn bộ phân tách lưu trữ dù kiến trúc KMS đúng.

### 19.3. Nhật ký phải được bảo vệ độc lập

Nếu một KMS operator có thể tự Decrypt dữ liệu rồi xóa các sự kiện KMS, audit không còn bảo đảm truy vết. Cần separation of duties, retention, logging coverage, giám sát và ranh giới kiểm soát phù hợp. Không kết luận “không có Decrypt trái phép” chỉ vì **không thấy log** nếu log collection chưa đủ phạm vi.


## 20. Chuyển đổi hệ thống cũ đang lưu plaintext key cạnh ciphertext

Giả sử một ứng dụng từng lưu AES key dạng rõ trong cùng database với ciphertext. Chỉ bổ sung cột encryptedDek rồi xóa cột key rõ **không tự chứng minh dữ liệu đã an toàn**:

- Backup, replica, WAL, archive và log cũ có thể vẫn giữ plaintext key.
- DEK có thể đã bị copy sang CI, image, file export hoặc một dịch vụ khác.
- Nếu cùng key được dùng mã hóa nhiều bản ghi, blast radius lớn.
- Chuyển sai nonce/AAD/keyRef có thể làm mất khả năng giải mã.
- Credentials của đường legacy có thể vẫn cho phép lấy key rõ.

### 20.1. Migration playbook

~~~mermaid
flowchart TD
    A["Inventory data, key sources, backups"] --> B["Đánh giá old key exposure"]
    B --> C["Dựng KMS/KEK, IAM, owner, audit"]
    C --> D["Chuẩn bị schema + key version"]
    D --> E{"Plaintext DEK cũ có nguy cơ lộ?"}
    E -->|Không, có evidence| F["Wrap old DEK dưới KEK theo policy"]
    E -->|Có hoặc chưa rõ| G["Generate new DEK + re-encrypt"]
    F --> H["Verify metadata/tag/AAD"]
    G --> H
    H --> I["Test decrypt và restore"]
    I --> J["Cutover readers/writers, chặn legacy"]
    J --> K["Xử lý bản sao plaintext key theo retention"]
    K --> L["Audit, monitor, incident review"]
~~~

Quy trình vận hành:

1. **Kiểm kê** bảng, object, backups, key format, tenant, readers/writers, cache và IAM.
2. **Phân loại material cũ:** nếu key có thể đã lộ hoặc sinh yếu, phải đánh giá **replace DEK và re-encrypt**, không chỉ wrap lại.
3. **Thiết lập KMS/HSM** với KEK sinh an toàn, owner, key usage, non-exportability khi hỗ trợ, IAM và audit.
4. **Thiết kế schema v2** có encrypted DEK, nonce/tag, keyRef/version và AAD version.
5. **Migration theo batch** có idempotency, checkpoint, kiểm tra AEAD tag và tránh ghi đè bản ghi vừa cập nhật.
6. **Kiểm thử** readback, integrity, backup restore, multi-tenant authorization và các consumer cũ.
7. **Cutover** toàn bộ writer/readers; không phát sinh ciphertext mới theo format cũ.
8. **Dọn đường plaintext key** ở DB, CI, source, config, cache/log/backup theo chính sách lưu giữ.
9. **Ghi nhận residual risk:** ciphertext đã bị giải mã trước migration không thể được “giữ bí mật trở lại” chỉ bằng đổi key.

### 20.2. Concurrent writes và retry

Nếu ứng dụng vẫn ghi trong khi migration, cần quản lý revision/optimistic locking, format version và key version. Một chiến lược **dual-read, single-write** có thể giảm rủi ro, nhưng phải tránh ghi trộn hai format mà không biết record thuộc version nào. Retry encryption không được tái sử dụng nonce dưới cùng DEK.

**Không sửa code production về lại plaintext key vì KMS đang lỗi.** Nếu KMS không đáp ứng, hệ thống cần fail-safe hoặc cơ chế dự phòng được phê duyệt từ trước.

## 21. Case study A: database backup bị đánh cắp

Một nền tảng thanh toán lưu hồ sơ bằng envelope encryption:

- Mỗi object có random DEK, dữ liệu được mã hóa bằng AES-GCM.
- Encrypted DEK, ciphertext, nonce và tag được backup cùng nhau.
- KEK ở KMS, không có plaintext KEK trong snapshot.
- Database backup reader không được cấp quyền KMS Decrypt.
- KMS usage được audit và gắn với workload identity.

### 21.1. Điều gì được bảo vệ?

Attacker có database snapshot **chưa có DEK rõ và chưa tự có khả năng unwrap**. Điều này làm giảm rủi ro so với việc lưu plaintext key trong bản backup.

Nhưng khi điều tra không được chỉ kết luận “AES-256 nên không rò dữ liệu”. Phải kiểm tra:

1. Snapshot có chứa bảng/log plaintext hoặc DEK từ debug không?
2. Có key material/backup key ở cùng nơi bị lấy không?
3. Có bị lộ IAM credentials cho phép Unwrap không?
4. Key generation/nonce/algorithm có an toàn không?
5. Metadata trong snapshot có tiết lộ PII hoặc thông tin nhạy cảm khác không?
6. Audit coverage đủ để xác định lời gọi KMS bất thường không?

### 21.2. Nếu cả application principal bị chiếm

Người tấn công có thể gọi KMS Unwrap/Decrypt qua principal. Cần cô lập credential/grants, điều tra những encrypted DEK hoặc dữ liệu đã được truy xuất, kiểm tra audit và cân nhắc thay key/re-encrypt theo phạm vi.

**Tách key khỏi storage làm giảm một nhóm rủi ro, không loại bỏ sự cố combined storage + KMS access compromise.**

## 22. Case study B: cross-tenant decryption oracle

Một ứng dụng đa tenant lưu các bản ghi:

~~~text
tenant=alpha / object=invoice-123
encryptedDEK=...
ciphertext=...
keyRef=shared-kek
~~~

API lỗi cho phép client tự gửi **encryptedDEK, keyRef, ciphertext** rồi server gọi KMS Unwrap bằng role có quyền trên mọi tenant.

**Vấn đề:** key material tách khỏi database nhưng server lại làm **decryption oracle** nếu không xác thực ownership của dữ liệu.

### 22.1. Thiết kế sửa lỗi

1. Xác thực user và lấy tenant từ identity đã kiểm chứng.
2. Xác thực quyền đọc object theo dữ liệu nội bộ được quản lý.
3. Đọc encrypted DEK/keyRef từ record đã được xác định, không tin request tùy ý.
4. Ràng buộc tenant/object/format/purpose trong **AAD** và kiểm tra tag.
5. Ràng buộc KMS encryption context nếu provider hỗ trợ.
6. Tách IAM key scopes/grants theo tenant/domain hoặc policy đã duyệt.
7. Audit cross-tenant denied attempts và calls KMS không hợp lệ.
8. Kiểm thử xem principal có thể đổi keyRef để bypass được không.

**Shared KEK không tự sai**, nhưng có thể tăng blast radius và làm crypto-shredding theo tenant khó hơn. Phải đánh giá mô hình chia sẻ theo loại dữ liệu và yêu cầu xóa.

## 23. Case study C: backup còn ciphertext nhưng KEK đã bị hủy

Một nhóm vận hành đã backup **ciphertext và encrypted DEK** đầy đủ. Sau đó KEK v1 bị ScheduleDelete rồi hủy thật vì “đã rotation sang v2”. Nhiều archive vẫn chỉ có DEK được bọc bằng KEK v1.

Khi khôi phục:

~~~text
Restore database backup: SUCCESS
Read encrypted DEK: SUCCESS
KMS Unwrap dưới KEK v1: FAIL (key material no longer exists)
Recover plaintext: FAIL
~~~

**Bài học:** backup dữ liệu và backup/recovery capability của key là **hai phần của cùng thiết kế khôi phục**.

Trước khi hủy KEK:

- Inventory encrypted DEK/object/archive/backup phụ thuộc.
- Rewrap DEK thích hợp qua KEK mới khi còn quyền và vật liệu.
- Xác minh restore thật bằng quyền DR đã được duyệt.
- Kiểm tra cryptoperiod: **originator-use period** có thể đã hết trong khi **recipient-use period** vẫn cần cho Decrypt/Unwrap lịch sử.
- Đừng nhầm ScheduleDelete với destroyed; theo dõi provider confirmation.
- Không copy plaintext KEK bằng script thủ công sang nơi thiếu kiểm soát chỉ để “giữ backup”.

Nếu một KEK ngẫu nhiên đã bị hủy và không còn recovery path, không thể đơn giản dùng hash của keyRef để tạo lại vật liệu giống cũ.

## 24. Ma trận kiểm thử việc tách key khỏi ciphertext

| Tình huống kiểm thử | Kết quả mong đợi |
|---|---|
| Đọc record ở database | Chỉ ciphertext, encrypted DEK và metadata; không có plaintext DEK/KEK |
| Read-only DB principal gọi KMS Unwrap | Bị IAM/key policy từ chối |
| KMS operator cố đọc dữ liệu nghiệp vụ ngoài quyền | Bị storage/business authorization từ chối |
| Encrypt workload gọi ScheduleDelete hoặc ChangeKeyPolicy | Bị chặn và audit |
| Kẻ tấn công sửa ciphertext một byte | AES-GCM tag verification thất bại |
| Sửa authentication tag | Không trả plaintext |
| Sửa tenantId/objectId đã gắn AAD | Tag sai hoặc business authz từ chối |
| Tráo encrypted DEK của tenant khác | KMS context hoặc business scope từ chối |
| Đổi keyRef sang KEK ngoài scope | IAM/key policy/allowlist chặn |
| Chuyển algorithm sang giá trị không trong allowlist | Từ chối; không fallback sang encryption yếu |
| Nonce trùng dưới cùng DEK | Test/design phát hiện hoặc ngăn |
| Multiwriter/multi-region | Không trùng nonce, ghi key version chính xác |
| KMS quota/outage | Fail-safe, không chuyển qua hard-coded master key |
| Retry encryption sau timeout | Không ghi record lệch nonce, DEK, keyRef hay ciphertext |
| Plaintext DEK trong logs/heap dump | Security controls giảm khả năng lộ, cảnh báo nếu bị log |
| DEK cache sau revoke | Cache invalidation/usage policy có hiệu lực |
| KEK rotate, DEK chưa lộ | Rewrap và restore test pass |
| DEK đã lộ nhưng chỉ rewrap | Review yêu cầu đánh giá replace DEK/re-encrypt |
| KEK v1 còn encrypted DEK trong archive | Destruction guard từ chối |
| Backup khác region | Có key access/recovery phù hợp và verify decrypt |
| Private signing key xuất hiện trong tài liệu | Thiết kế bị từ chối |
| Verifier tin public key tùy ý đính kèm tài liệu | Trust policy ngăn |
| KMS key disabled nhưng client còn cache DEK | Phát hiện cache còn khả năng dùng |
| DeleteKey chỉ mới được lên lịch | Không gắn DESTROYED cho tới khi provider xác nhận |
| Audit key usage | Có actor/keyRef/version/result, không chứa plaintext secret |
| Migration từ plaintext key column | Có bằng chứng backup, schema, readback, IAM, cutover |
| Crypto-shred tenant A khi KEK shared nhiều tenant | Không hủy key làm ảnh hưởng tenant B |

Kiểm thử cần có **negative access tests**, không chỉ round-trip Encrypt/Decrypt. Một phép giải mã thành công không chứng minh IAM, KMS, metadata binding, backup và separation đủ mạnh.

## 25. Những sai lầm thường gặp

| Sai lầm | Tác động | Cách sửa |
|---|---|---|
| Plaintext AES key cạnh ciphertext | Lộ dữ liệu đồng thời lộ key | Wrapped DEK + KEK trong miền bảo vệ riêng |
| Cho rằng encrypted DEK cũng phải tách vật lý | Làm phức tạp storage không cần thiết | Hiểu envelope encryption đúng |
| Base64 key rồi gọi là encrypted | Key không được che giấu | Key wrap/AEAD được đánh giá |
| Plaintext KEK ở cùng backup | Mất ranh giới bảo mật | Key backup/recovery riêng |
| Key trong source hoặc image | Secret bị sao chép vào nhiều artifact | Generate/provision qua KMS/vault phù hợp |
| Hai file nhưng cùng ACL/admin | Một credential vẫn đọc cả hai | Tách quyền và effective permissions |
| Chỉ tách DB với KMS nhưng IAM mở rộng | KMS có thể bị lạm dụng như oracle | Least privilege/SoD/monitoring |
| Dùng keyRef làm token phân quyền | Cho người dùng gọi key ngoài phạm vi | Business authorization + KMS policy |
| Tin tenantId do client gửi | Cross-tenant decrypt | Xác thực principal và object ownership |
| Không gắn metadata vào AAD/context | Có thể tráo dữ liệu | AAD canonical + KMS context nếu hỗ trợ |
| Dùng nonce GCM cố định/lặp | Phá confidentiality/integrity | Unique nonce dưới DEK |
| Bỏ qua tag verification | Chấp nhận dữ liệu bị sửa | AEAD verify trước khi trả plaintext |
| Cache DEK không giới hạn | Tăng plaintext key exposure | TTL/scope/usage bounds + revoke handling |
| Log DEK trong debug | Làm lộ secret ngoài KMS | Log metadata, key version và operation IDs |
| Rotate alias nhưng không đổi material | Không giảm nguy cơ vật liệu lộ | Generate material mới và cutover |
| Rewrap DEK đã bị lộ | Không khắc phục bản sao DEK | Thay DEK/re-encrypt theo incident |
| Hủy KEK trước khi di chuyển encrypted DEK | Mất dữ liệu lịch sử | Dependency inventory + restore |
| Chỉ backup ciphertext | Không có đường unwrap khi DR | Data + key recovery được thiết kế cùng nhau |
| Chỉ lưu alias/latest keyRef | Không biết key version lịch sử | Version metadata đúng provider |
| Xóa public signing key cùng private key | Mất bằng chứng xác minh lịch sử | Giữ public key/certificate theo policy |
| Public key đi cùng tài liệu được tin ngay | Attacker tự ký rồi tự nêu key | Trust chain/issuer authorization |
| Nhầm deletion scheduled với destruction | Báo sai tình trạng key | Provider readback + audit |

## 26. Câu hỏi tự kiểm tra

**Câu 1. Key tách khỏi ciphertext có nghĩa encrypted DEK không được lưu cùng bản mã?**

**Trả lời:** Không. Wrapped/encrypted DEK có thể lưu cạnh ciphertext; plaintext DEK/KEK và đường Unwrap phải được bảo vệ bằng miền tin cậy riêng.

**Câu 2. Vì sao Base64 không bảo vệ AES key?**

**Trả lời:** Base64 chỉ encoding. Ai có chuỗi đều có thể decode về byte key.

**Câu 3. Nếu database backup bị lộ mà KEK ở KMS, có chắc không lộ dữ liệu?**

**Trả lời:** Không chắc tuyệt đối. Cần xác minh không có plaintext ở các cột/log khác, không lộ key/credentials, và cơ chế mã hóa/IAM đúng. Nhưng người chỉ có ciphertext/encrypted DEK thường chưa đủ để unwrap.

**Câu 4. KMS non-exportable có ngăn API misuse không?**

**Trả lời:** Không. Principal có quyền Unwrap/Decrypt vẫn có thể yêu cầu KMS xử lý dữ liệu trái phép.

**Câu 5. Nonce/tag có cần giữ bí mật như DEK không?**

**Trả lời:** Thường không. Nonce phải duy nhất dưới từng DEK trong AES-GCM; tag phải được verify.

**Câu 6. Key ID có phải mật khẩu để mở ciphertext không?**

**Trả lời:** Không. Key ID là tham chiếu; IAM và business authorization quyết định quyền.

**Câu 7. Tại sao AAD không thay thế kiểm tra người dùng được quyền đọc object?**

**Trả lời:** AAD bảo vệ tính toàn vẹn của metadata được ràng buộc; nó không xác định người dùng có quyền với dữ liệu hay không.

**Câu 8. KMS encryption context có giống AAD của ciphertext dữ liệu không?**

**Trả lời:** Không tự động. Chúng có thể thuộc hai phép toán khác nhau; ứng dụng cần thiết kế ràng buộc rõ.

**Câu 9. Vì sao kiểm tra effective permissions quan trọng hơn tên role?**

**Trả lời:** Một người không có Decrypt trực tiếp vẫn có thể tự cấp quyền qua ChangeKeyPolicy/CreateGrant/AssumeRole nếu thiếu kiểm soát.

**Câu 10. KEK rotate theo kế hoạch có cần mã hóa lại toàn bộ dữ liệu không?**

**Trả lời:** Không nhất thiết. Nếu DEK chưa lộ, rewrap DEK có thể phù hợp.

**Câu 11. Nếu plaintext DEK đã lộ, rewrap có đủ không?**

**Trả lời:** Không. Kẻ có DEK vẫn có thể giải mã ciphertext cũ; phải đánh giá thay DEK/re-encrypt và dữ liệu đã bị lộ.

**Câu 12. Có thể hủy KEK cũ ngay khi alias chuyển sang version mới không?**

**Trả lời:** Không. Encrypted DEK/backups lịch sử có thể vẫn phụ thuộc KEK cũ.

**Câu 13. Chỉ tách key và ciphertext thành hai file có đủ?**

**Trả lời:** Không nếu cùng quyền đọc/backup/admin. Cần ranh giới về authorization và bảo vệ key material.

**Câu 14. Private signing key có thể lưu trong tài liệu cạnh chữ ký không?**

**Trả lời:** Không nên. Chữ ký và public key có thể kèm tài liệu, private key phải được giữ trong miền bảo vệ riêng.

**Câu 15. Vì sao public key đính kèm tài liệu không tự chứng minh signer đáng tin?**

**Trả lời:** Kẻ tấn công có thể tự tạo key pair và tự ký. Verifier cần nguồn danh tính/trust độc lập.

**Câu 16. Arrays.fill có đảm bảo mọi bản sao plaintext DEK trong JVM biến mất không?**

**Trả lời:** Không. Thư viện/provider hoặc heap có thể giữ bản sao; xóa mảng chỉ là best-effort.

**Câu 17. Khi nào crypto-shredding có cơ sở làm bản mã không thể giải mã?**

**Trả lời:** Khi vật liệu cần để giải mã đã được hủy thật và không có bản sao/recovery path/plaintext ngoài phạm vi. Nếu đối thủ đã lấy key, không thể hủy bản sao đó từ xa.

## 27. Checklist triển khai và ghi nhớ

Trước khi khẳng định hệ thống **tách key khỏi ciphertext** an toàn, hãy kiểm tra:

- **Inventory:** biết dataset, ciphertext, encrypted DEK, backup, key ID/version, owner và tenant?
- **Storage:** không lưu plaintext DEK/KEK cạnh ciphertext dưới cùng quyền đọc, backup hoặc log?
- **Envelope:** wrapped DEK được bọc đúng cơ chế và KEK bảo vệ trong KMS/HSM hoặc miền tin cậy riêng?
- **Key generation:** DEK/KEK được sinh bằng CSPRNG/KMS, không lấy từ từ khóa/tenant ID dễ đoán?
- **IAM:** storage reader không tự Unwrap; KMS operator không tự có quyền đọc business data?
- **Effective permissions:** đã đánh giá AssumeRole, CreateGrant, ChangeKeyPolicy và self-escalation?
- **Business authz:** đã xác minh user/tenant/object trước khi gọi KMS Decrypt?
- **Metadata integrity:** keyRef, version, algorithm, tenant, object và purpose được kiểm tra/AAD binding đúng?
- **AEAD:** nonce GCM duy nhất dưới DEK, tag luôn được verify, AAD schema/version ổn định?
- **Runtime:** plaintext DEK ngắn hạn, không log, không cache tùy tiện, heap dumps/snapshots được bảo vệ?
- **Audit:** có actor, result, keyRef/version, KMS operation và correlation ID mà không có key bytes?
- **Backup/DR:** encrypted DEK và key recovery đều có, restore thật đã được thử?
- **Rotation:** có thể phân biệt KEK rewrap và DEK re-encrypt, key material/version đúng?
- **Revocation:** KMS/IAM deny, DEK cache invalidation và trust propagation (nếu là signing key) hoạt động?
- **Multi-tenant:** kiểm tra cross-tenant oracle, shared KEK blast radius và encryption context?
- **Migration:** đã xử lý đường legacy plaintext key, bản sao backups và residual risk?
- **Destruction:** không hủy KEK khi còn encrypted DEK phụ thuộc; có provider confirmation thực tế?
- **Testing:** negative IAM, tamper AAD/tag, KMS outage, retry, nonce, multi-region và rollback được kiểm tra?

**Ghi nhớ:** **Key tách khỏi ciphertext** là nguyên tắc đặt **bí mật mật mã và quyền dùng khóa** sau một ranh giới bảo vệ khác với nơi lưu dữ liệu. Trong **envelope encryption**, ciphertext có thể lưu cùng **encrypted DEK, nonce, tag và key reference**, nhưng **plaintext DEK/KEK không được lộ chỉ vì một principal có quyền đọc storage**. Để tách khóa thực sự có ý nghĩa, cần phối hợp **KMS/HSM, IAM, business authorization, AEAD/AAD, key inventory, backup/restore, rotation, revocation, destruction và audit** trong toàn bộ vòng đời khóa.



