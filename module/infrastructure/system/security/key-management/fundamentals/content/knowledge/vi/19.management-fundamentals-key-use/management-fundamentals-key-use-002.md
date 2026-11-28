# Encryption key chỉ dùng để encrypt — Giới hạn mục đích và quyền sử dụng khóa mã hóa

## 1. “Encryption key chỉ dùng để encrypt” nghĩa là gì?

**Encryption key chỉ dùng để encrypt** là nguyên tắc thiết kế trong đó **khóa được cấp cho đúng mục đích mã hóa** và **chủ thể thực hiện thao tác ghi/mã hóa không được mặc nhiên có quyền giải mã, ký số, bọc khóa, dẫn xuất khóa hoặc thay đổi chính sách quản trị**. Cụm từ này cần được giải thích theo **loại thuật toán, thuộc tính key, quyền của principal và ranh giới thực thi** để tránh nhầm lẫn.

Ví dụ, một dịch vụ thu thập dữ liệu (*ingestion writer*) chỉ cần **mã hóa** bản ghi trước khi lưu. Một dịch vụ kiểm toán có thẩm quyền (*authorized reader*) mới được **giải mã**. Việc giới hạn writer ở thao tác `Encrypt` giúp giảm phạm vi thiệt hại nếu credential của writer bị chiếm.

**Nhưng với khóa đối xứng AES, cùng một khóa về mặt mật mã có thể thực hiện cả encryption và decryption.** Vì vậy “AES key chỉ encrypt” thường là **chính sách sử dụng trong KMS/HSM/API/IAM**, **không phải** đặc tính toán học của AES khiến người giữ **raw key bytes** không thể decrypt.

Với **mật mã bất đối xứng**, một thiết kế khác là **recipient public key dùng để encrypt**, còn **private key dùng để decrypt**. Người có public key có thể tạo ciphertext nhưng không thể giải mã bằng chính public key trong giả định bảo mật của thuật toán đúng. Tuy nhiên, **public key phải được xác thực đúng recipient**, và chính public-key encryption không chứng minh được danh tính người gửi.

Trong mô-đun **SECURITY_KEY_MANAGEMENT_FUNDAMENTALS**, chủ đề thuộc chương **Key use (Sử dụng khóa)** và kết nối với toàn bộ vòng đời **tạo, cấp phát, lưu trữ, sử dụng, xoay vòng, thu hồi, hủy khóa**, cùng AES-GCM, RSA-OAEP, ECDH/HPKE, chữ ký số, KMS/HSM, envelope encryption, IAM, dual control và kiểm toán.

> **Nguyên tắc quan trọng:** **Tách quyền `Encrypt` khỏi `Decrypt` là một kiểm soát truy cập.** Nó chỉ có hiệu lực khi chủ thể không thể lấy raw key, gọi API giải mã bằng đường khác, tự sửa policy hoặc dùng lại credential có quyền rộng hơn.

### Mục tiêu học tập

Sau bài này, người học có thể:

1. Phân biệt **key purpose**, **key usage**, **operation authorization** và **khả năng toán học của khóa**.
2. Giải thích **vì sao AES encryption-only cần enforcement**, còn public/private encryption cho phép tách quyền bằng hai vật liệu khóa khác nhau.
3. Thiết kế writer chỉ encrypt, reader decrypt có kiểm soát, kết hợp KMS/HSM và dữ liệu mã hóa.
4. Áp dụng **AES-GCM, nonce, AAD, authentication tag** đúng khi triển khai.
5. Tách **DEK** với **KEK**, phân biệt `Encrypt/Decrypt` và `Wrap/Unwrap`.
6. Không dùng encryption key bừa bãi để **HMAC, ký số, ECDH hoặc dẫn xuất khóa**.
7. Xây dựng policy, audit, negative test và quy trình rotation/incident response.

## 2. Ba cách hiểu khác nhau của “chỉ encrypt”

| Cách hiểu | Ví dụ | Phải hiểu chính xác |
| --- | --- | --- |
| **Key purpose**: chỉ phục vụ mã hóa dữ liệu | DEK được phân loại `DATA_ENCRYPTION` | Không dùng chung raw material cho HMAC, signing hoặc key wrapping trái chính sách |
| **Permission**: principal chỉ được gọi `Encrypt` | `ingest-service` có quyền KMS `Encrypt`, không có `Decrypt` | **Cùng key** có thể vẫn được principal đọc khác decrypt |
| **Key attribute / cryptographic role** | PKCS#11 secret key có `CKA_ENCRYPT=true`, `CKA_DECRYPT=false` | Token có thể chặn operation; nếu raw key lọt ra, ràng buộc attribute không còn bảo vệ bản sao |
| **Public-key encryption** | RSA-OAEP public key dùng encrypt, private key dùng decrypt | Sự phân tách dựa trên **hai thành phần khóa**, nhưng còn phải kiểm tra trust, padding và scope |
| **Write-only business workflow** | Pipeline chỉ nhận và mã hóa dữ liệu | Không nhất thiết bản thân key chỉ có một operation; kiểm soát thêm cả quyền dữ liệu và IAM |

**Một mô tả “encrypt-only” mà không nói rõ thuộc lớp nào là chưa đủ để đánh giá an ninh.**

### Một câu hỏi thử rất hữu ích

**Nếu attacker có toàn bộ credential và quyền của service writer, họ có thể đọc lại plaintext lịch sử không?**

- Nếu chỉ được `Encrypt` bằng **public key đã xác thực** và không có private key, khả năng giải mã bằng public key không tồn tại theo cơ chế đúng.
- Nếu chỉ được gọi **KMS Encrypt** nhưng không được `Decrypt`, không được lấy plaintext DEK và không tự sửa policy, ranh giới quyền có thể bảo vệ.
- Nếu writer giữ **raw AES key trong process**, attacker có thể dùng chính key đó để decrypt dữ liệu thu được, dù interface của service chỉ expose hàm `encrypt()`.

Đây là cách đánh giá **boundary thực**, không chỉ đọc tên role hoặc class.

## 3. Key purpose khác key operation

**Key purpose** trả lời: *Khóa này được tạo và chấp thuận để bảo vệ loại tài sản nào, theo giao thức nào?*

**Key operation** trả lời: *Một principal cụ thể được gọi phép toán nào trên key đó?*

Một DEK dùng AES-GCM có thể có purpose `INVOICE_DATA_ENCRYPTION`. Các operation được quản lý riêng:

~~~text
Key resource: billing-dek-v7
Purpose: encrypt invoice data at rest
Algorithm: AES-256-GCM

Writer:
    Encrypt = ALLOW
    Decrypt = DENY
    ChangePolicy = DENY
    ExportRaw = DENY

Reader được phê duyệt:
    Encrypt = DENY hoặc hạn chế theo nhiệm vụ
    Decrypt = ALLOW theo tenant/data scope
    ChangePolicy = DENY

Key custodian:
    Activate/Rotate theo workflow
    Encrypt/Decrypt dữ liệu nghiệp vụ = không mặc định được cấp
~~~

**Bảng trên là chính sách khái niệm**, không phải cấu hình chạy trực tiếp của một cloud KMS nào. Trong thực tế, **một số KMS không chạy AES-GCM trực tiếp trên DEK mà ứng dụng đang giữ**; phân quyền phải được thực thi ở đúng nơi thao tác xảy ra.

### Hai câu hỏi kiểm tra

1. **Một encryption key có thể được dùng để decrypt không?** Với **khóa đối xứng AES**, về mặt toán học là có. Quyền thực hiện có thể bị giới hạn bởi thiết bị/API.
2. **Một encryption key có nên được dùng để ký số không?** Thông thường **không**; ký số và mã hóa có mục đích, thuật toán, chứng cứ và vòng đời khác nhau. Cần dùng khóa riêng theo giao thức.

## 4. Mô hình thực tế: encryption-only writer, decryption-only reader

Một kiến trúc dữ liệu lưu trữ có thể phân tách **luồng ghi** và **luồng đọc bí mật**.

~~~mermaid
flowchart TD
    Producer[Nguồn dữ liệu] --> Writer[Ingestion writer]
    Writer --> WP[Policy: chỉ Encrypt]
    WP --> Crypto[KMS/HSM hoặc encryption gateway]
    Crypto --> DB[(Ciphertext + key metadata)]
    DB --> Reader[Reader được ủy quyền]
    Reader --> RP[Policy: Decrypt theo scope]
    RP --> Crypto
    RP --> Audit[Business and key-access audit]
    WP --> Audit
    Crypto --> Audit
    Bad[Writer bị chiếm quyền] --> WP
    WP -->|Decrypt bị từ chối| Deny[Không tiết lộ plaintext lịch sử qua KMS]
~~~

### Điều tách quyền giúp đạt được

- Credential writer bị lộ **không tự cấp đường KMS `Decrypt`**.
- Sai sót của ingest service khó trực tiếp biến thành **truy xuất dữ liệu lưu trữ** qua key API.
- Quyền đọc dữ liệu có thể yêu cầu authentication, authorization theo tenant, business approval và audit riêng.
- Tác vụ **rotate key, sửa IAM hoặc hủy key** được tách khỏi cả writer và reader.

### Điều tách quyền không tự đạt được

- Writer bị chiếm có thể **ghi dữ liệu giả** hoặc mã hóa payload độc hại.
- Nếu writer thấy **plaintext mới trước khi encrypt**, attacker có thể đọc nội dung đó tại thời điểm nhập liệu.
- Nếu service giữ **raw AES key hoặc DEK trong RAM**, attacker có thể lấy key và dùng ngoài API.
- Nếu writer có thể sửa IAM, key policy, grants hoặc code của decryption service, kiểm soát có thể bị bypass.
- Nếu attacker có bản sao plaintext/ciphertext từ nơi khác, ranh giới encryption-only không loại bỏ sự cố đó.

**Encryption-only giảm quyền theo nhiệm vụ; nó không đồng nghĩa mọi dữ liệu đi qua writer đều bí mật đối với writer.**

## 5. Khóa đối xứng AES: cùng vật liệu có thể encrypt và decrypt

Với **AES**, secret key là cùng một chuỗi bit mà hai thuật toán **encryption và decryption** sử dụng. Khi dùng mode AEAD như AES-GCM:

~~~text
(ciphertext, tag) = AES-GCM-Encrypt(K, nonce, AAD, plaintext)
plaintext = AES-GCM-Decrypt-Verify(K, nonce, AAD, ciphertext, tag)
~~~

**Cùng một K** được dùng ở cả hai chiều. Có thể cấu hình policy để một principal **không được gọi Decrypt** nhưng nếu principal biết raw K, họ có thể đưa bytes đó vào thư viện AES khác để giải mã.

### 5.1. Phân quyền đúng lớp

| Nơi giữ key | Encrypt-only được cưỡng chế bằng gì? | Nguy cơ |
| --- | --- | --- |
| **Managed KMS** giữ material | IAM/key policy chỉ cho writer `Encrypt`, không `Decrypt` | Role có thể tự nâng quyền hoặc có API khác |
| **HSM/PKCS#11** giữ material | Key usage attributes và token role/session/policy | Token policy hoặc admin có thể bị lạm dụng |
| **Encryption service** giữ raw key | Gateway chỉ expose Encrypt + IAM/host isolation | Nếu service bị chiếm, raw key có thể bị trích xuất |
| **Ứng dụng JVM giữ `SecretKey` raw/extractable** | Chỉ là interface/code convention | Không phải ranh giới bảo vệ mạnh trước process compromise |
| **Client tự mã hóa bằng raw DEK** | Quyền bên ngoài có thể hạn chế cấp key | Khi DEK đã cấp, KMS không kiểm soát việc sử dụng offline |

### 5.2. Key usage attribute không có hiệu lực ngoài boundary

Trong token PKCS#11, một key có thể được đặt **`CKA_ENCRYPT=true` và `CKA_DECRYPT=false`**. Khi token thực thi đúng policy, nó sẽ từ chối decrypt qua key object đó.

Nhưng nếu **raw key material** được export hoặc từng tồn tại ở bên ngoài, attributes trên token **không cấm** một chương trình khác dùng raw bytes để decrypt. Do đó, cần kết hợp **non-exportability, nguồn tạo key, IAM, kiểm soát backup và kiểm toán**.

### 5.3. Không đặt AES key ở client nếu cần hạn chế decrypt

Một mobile app hoặc browser được phát **raw AES key** có thể giải mã bất kỳ ciphertext tương ứng mà nó truy cập được, bất kể UI chỉ hiển thị nút Encrypt. Nếu muốn **người gửi chỉ mã hóa mà không giải mã dữ liệu đã gửi**, mô hình **public-key encryption** thường phù hợp hơn.

## 6. Bất đối xứng: public key encrypt, private key decrypt

Với cơ chế **public-key encryption** đúng, người gửi sử dụng **public key của recipient** để mã hóa hoặc encapsulate secret; recipient sử dụng **private key tương ứng** để giải mã hoặc decapsulate.

~~~mermaid
sequenceDiagram
    participant S as Sender
    participant PKI as Nguồn public key tin cậy
    participant R as Recipient private-key boundary
    S->>PKI: Lấy public key/certificate của recipient
    PKI-->>S: Public key + chứng cứ trust
    S->>S: Verify identity, key usage, algorithm
    S->>S: Encrypt hoặc encapsulate bằng public key
    S->>R: Ciphertext + metadata đã xác thực theo protocol
    R->>R: Private key Decrypt/Decapsulate
    R-->>R: Giải mã dữ liệu theo policy
~~~

### Ví dụ

Một biểu mẫu có thể dùng **public encryption key của bộ phận tiếp nhận** để tạo encrypted package. Người gửi giữ public key nên **không thể dùng nó để decrypt** theo scheme được chọn; chỉ recipient có private key mới đọc được.

**Nhưng người gửi thường biết plaintext mình đang nhập.** “Không có quyền decrypt” không có nghĩa họ không biết nội dung đã gửi.

### Điều bắt buộc để không mã hóa cho attacker

- Public key phải gắn với **đúng danh tính recipient**.
- Xác minh certificate chain/trust, key fingerprint, key usage và trạng thái khi áp dụng.
- Không lấy một public key chưa xác thực từ HTTP endpoint do attacker điều khiển.
- Cơ chế mã hóa phải dùng **padding/KEM và thông số chuẩn**, không phải “RSA tự chế”.
- Nếu cần **xác thực sender** hoặc chống replay, thêm chữ ký số, xác thực phiên/giao thức và sequence policy thích hợp.

**Public-key encryption tự nó không chứng minh ai là người gửi ciphertext.** Bất kỳ ai có public key cũng có thể mã hóa.

## 7. RSA-OAEP, HPKE và hybrid encryption

### 7.1. RSA-OAEP

**RSA-OAEP** là padding/scheme mã hóa bất đối xứng dùng cho thông điệp **ngắn** như một content encryption key. Nó có giới hạn độ dài input theo kích thước modulus và hash.

Ví dụ, với RSA-3072 và SHA-256, độ dài plaintext tối đa theo OAEP là:

~~~text
k - 2*hLen - 2
= 384 - 2*32 - 2
= 318 byte
~~~

Do vậy **không dùng RSA-OAEP trực tiếp để mã hóa file lớn hoặc toàn bộ database**. Thường dùng một **hybrid design**: public-key scheme bảo vệ DEK; DEK dùng AES-GCM mã hóa dữ liệu.

### 7.2. HPKE và các cơ chế KEM

**HPKE (Hybrid Public Key Encryption)** kết hợp cơ chế KEM, KDF và AEAD theo các suite đã định nghĩa. Sender có thể mã hóa cho recipient public key; recipient dùng private key để khôi phục secret và giải mã payload.

Điểm quan trọng: dùng **thư viện và giao thức chuẩn**, chú ý suite, context, identity binding, authenticated mode nếu cần và key validation. Không ghép ECDH + HKDF + AES-GCM tùy tiện rồi gọi là HPKE.

### 7.3. Forward secrecy không tự xuất hiện

Khi mã hóa bằng **recipient static public key**, nếu private key tương ứng bị lộ trong tương lai và attacker giữ ciphertext lịch sử, họ có thể có khả năng giải mã lịch sử tùy scheme. **Encryption-only của sender không tự bảo đảm forward secrecy.**

Forward secrecy cần **giao thức key agreement có ephemeral secrets** và cách xóa/quản lý những secrets đó đúng, chẳng hạn giao thức truyền tải hiện đại đã được thiết kế cho mục tiêu này.

## 8. “Chỉ dùng để encrypt” không đồng nghĩa “không cần integrity”

Một encryption key có mục đích mã hóa dữ liệu nên được dùng với **một scheme có bảo vệ integrity/authenticity phù hợp**. Chỉ che giấu plaintext mà không phát hiện thay đổi ciphertext có thể khiến hệ thống chấp nhận dữ liệu bị sửa.

### Ưu tiên AEAD

**AES-GCM** kết hợp mã hóa và kiểm tra authentication tag. Thuật toán dùng cùng một key cho cơ chế AEAD hoàn chỉnh; điều đó **không có nghĩa đang dùng AES key làm một HMAC key độc lập**.

~~~text
Encrypt:
    (ciphertext, tag) = AEAD.Encrypt(K_enc, nonce, AAD, plaintext)

Decrypt:
    plaintext = AEAD.DecryptAndVerify(K_enc, nonce, AAD, ciphertext, tag)
    nếu tag sai -> từ chối
~~~

### Authenticated encryption không phải chữ ký số

Tag AEAD chứng minh dữ liệu **được tạo bởi một bên biết cùng symmetric key** trong mô hình bảo mật của scheme. Nó không cung cấp **non-repudiation** hoặc danh tính người ký như chữ ký số bất đối xứng.

Nếu nhiều service có cùng raw AES key, một service biết key có thể tạo ciphertext/tag mới; ứng dụng không được xem tag là chữ ký của một service cụ thể mà không có kiểm soát danh tính riêng.

## 9. Nonce, IV và giới hạn dùng AES-GCM

Với AES-GCM, **nonce không được lặp lại dưới cùng một key**. Không phải nonce phải bí mật; yêu cầu quan trọng là **không tái sử dụng cặp (key, nonce)** trong những lần mã hóa khác nhau.

### 9.1. Nonce 96 bit

Nonce 96 bit là kích thước thông dụng trong GCM. Có thể dùng:

- **Counter/sequence** với cơ chế cấp phát không trùng giữa writer, node, region và restore.
- **Nonce ngẫu nhiên 96 bit** từ CSPRNG theo hạn mức sử dụng và đánh giá xác suất va chạm.
- Cơ chế cấp phát đã được xác định bởi protocol/library.

Random nonce **không bảo đảm tuyệt đối không trùng**. Với rất nhiều lần encryption cùng key, cần xét **birthday bound**, hạn mức use và phương án rotate.

### 9.2. Encryption-only service vẫn có thể phá GCM

Một service chỉ được `Encrypt` nhưng dùng **nonce cố định `000...0`** dưới cùng AES key có thể làm mất bảo mật ngay cả khi không có quyền decrypt.

**IAM không thay thế sử dụng thuật toán đúng**. Ngoài permission, hệ thống cần kiểm soát **nonce generation, AAD, key rotation và tests**.

### 9.3. Không tái sử dụng key/nonce khi retry

Nếu retry là **cùng một ciphertext bất biến** và chỉ gửi lại bản đã được tạo, đó khác với việc **mã hóa một plaintext khác bằng cùng nonce**. Hệ thống phải quản lý idempotency, không tự “khóa nonce bằng request ID” nếu request ID có thể trùng hoặc metadata thay đổi.

### 9.4. AAD ràng buộc ngữ cảnh

AAD có thể chứa **tenant, record ID, schema version, key version và business domain** dưới cách mã hóa chính tắc. Bên decrypt phải dùng **chính xác AAD** đã dùng khi encrypt để xác minh tag.

AAD **không được mã hóa**, vì vậy không đặt plaintext nhạy cảm vào AAD trừ khi chính sách cho phép dữ liệu đó lộ dưới dạng metadata.

## 10. Key-use policy: những operation phải tách biệt

Không nên đặt mọi operation trên một principal chỉ vì các API cùng nằm trong một KMS/HSM.

| Operation | Mục đích | Principal có thể được cấp |
| --- | --- | --- |
| `Encrypt` | Tạo ciphertext mới | Writer đã xác thực |
| `Decrypt` | Giải mã dữ liệu cũ hoặc mới | Reader với data scope được kiểm soát |
| `GenerateDataKey` | Xin một DEK mới, có thể trả plaintext DEK | Encryption service với threat model chấp nhận raw DEK |
| `GenerateDataKeyWithoutPlaintext` hoặc tương đương | Tạo DEK dưới dạng được bảo vệ | Workflow cần handle/wrapped key, tùy provider |
| `Wrap` | Bảo vệ key bằng KEK | Key-management gateway |
| `Unwrap` | Khôi phục key được bọc | Reader/recovery được cấp quyền |
| `Sign` | Tạo chữ ký số | Signing service theo business approval |
| `Verify` | Kiểm tra chữ ký | Verifier dùng public key |
| `GenerateMac`/`VerifyMac` | Tạo/kiểm tra HMAC | Workload đúng protocol, secret scope |
| `DeriveKey` | Sinh subkey theo KDF/context | Giao thức hoặc key-schedule service |
| `Export`, `Import` | Di chuyển vật liệu key | Custodian/workflow có phê duyệt |
| `Rotate`, `Disable`, `Destroy` | Quản trị vòng đời | Role quản trị với approval phù hợp |
| `ChangePolicy`, `CreateGrant` | Thay quyền và trust boundary | Security/control plane được giám sát |

**Tên operation mang tính khái niệm**; API, key usage classification và khả năng đặt quyền khác nhau theo provider. Một số managed KMS chỉ có key type **`ENCRYPT_DECRYPT`**, rồi **IAM riêng** quyết định principal nào được gọi operation nào.

### Cấp quyền đúng API chưa đủ

Một principal có thể bị từ chối `Decrypt` nhưng vẫn có đường lộ nếu được phép:

- `Export` raw key hoặc lấy key backup.
- `GenerateDataKey` và nhận plaintext key dùng chung cho nhiều record.
- Sửa policy, tạo grants, thay IAM trust.
- Đọc process memory của gateway đang giữ DEK.
- Gọi một service khác có quyền decrypt mà không có business authorization.

Vì vậy chính sách cần đánh giá **tổng hợp quyền trực tiếp và gián tiếp**.

## 11. PKCS#11 và HSM: gắn allowed operations vào key object

**PKCS#11** là một giao diện thường dùng với HSM/token, cho phép giới hạn operation thông qua thuộc tính đối tượng và cơ chế thiết bị hỗ trợ.

### Các thuộc tính liên quan

| Thuộc tính | Ý nghĩa khái niệm |
| --- | --- |
| `CKA_ENCRYPT` | Cho phép dùng key object để encrypt qua token |
| `CKA_DECRYPT` | Cho phép dùng key object để decrypt qua token |
| `CKA_SIGN` | Cho phép ký khi key/algorithm hỗ trợ |
| `CKA_VERIFY` | Cho phép verify khi phù hợp |
| `CKA_WRAP` | Cho phép wrap key khác |
| `CKA_UNWRAP` | Cho phép unwrap key |
| `CKA_DERIVE` | Cho phép dẫn xuất khóa |
| `CKA_SENSITIVE` | Hạn chế truy vấn giá trị nhạy cảm |
| `CKA_EXTRACTABLE` | Liên quan khả năng xuất/wrap key material |
| `CKA_ID`/`CKA_LABEL` | Định danh/tìm kiếm object, không phải chính sách authorization đầy đủ |

### Một cấu hình logic

~~~text
AES encryption key object in HSM:
    CKA_ENCRYPT = true
    CKA_DECRYPT = false
    CKA_WRAP = false
    CKA_UNWRAP = false
    CKA_SIGN = false
    CKA_EXTRACTABLE = false

Reader cần decrypt:
    Dùng key object / principal / policy riêng
    theo thiết kế hỗ trợ của token.
~~~

**Đây là ví dụ khái niệm**, không phải cấu hình áp dụng được nguyên văn trên mọi HSM. Một số token có rules về việc tạo, sao chép, thay đổi attributes hoặc phân tách object/key material.

### Lưu ý quan trọng về cùng AES key

Nếu một key object chỉ `CKA_ENCRYPT=true` và `CKA_DECRYPT=false`, token có thể không cho reader decrypt bằng **chính object** đó. Với dữ liệu cần đọc lại, thiết kế phải có **đường decrypt được ủy quyền** từ đầu: object/policy phù hợp, decrypt service được phép hoặc một kiến trúc public-key/hybrid khác.

**Không tự nhân bản raw AES material** để tạo “decrypt object” rồi làm lộ secret, trừ khi thiết bị và chính sách hỗ trợ một cơ chế nội bộ có bảo đảm tương ứng. Cần thiết kế theo khả năng HSM và mục tiêu non-exportable.

### Non-exportable là điều kiện bổ sung

`CKA_ENCRYPT=true` chỉ nói một operation được phép; nó **không đủ chứng minh raw key không thể xuất**. Xác minh `CKA_EXTRACTABLE`, `CKA_SENSITIVE`, provenance, wrapping mechanism và chính sách thiết bị.

## 12. Managed KMS: ENCRYPT_DECRYPT key usage không đồng nghĩa mọi principal có Decrypt

Nhiều managed KMS có một key resource dùng cho tác vụ mã hóa/giải mã đối xứng. Ở lớp quản lý key, nó có thể được phân loại **symmetric encryption key**, **encryption/decryption key** hoặc có key usage kiểu **`ENCRYPT_DECRYPT`**.

Điều đó **không có nghĩa** một service được gọi `Encrypt` mặc nhiên được gọi `Decrypt`.

### Mô hình giả định

~~~yaml
# POLICY MINH HỌA, không phải cú pháp IAM của một cloud provider.
keyId: "billing-kek-v4"
keyPurpose: "DATA_KEY_PROTECTION"
materialOrigin: "KMS_GENERATED"
keyState: "ACTIVE"
policies:
  - principal: "billing-ingest-prod"
    allowOperations: ["Encrypt"]
    denyOperations: ["Decrypt", "Export", "ChangePolicy", "CreateGrant"]
  - principal: "billing-reader-prod"
    allowOperations: ["Decrypt"]
    denyOperations: ["Export", "ChangePolicy", "CreateGrant"]
  - principal: "billing-key-admin"
    allowOperations: ["Describe", "RequestRotation"]
    denyOperations: ["Encrypt", "Decrypt", "Export"]
securityControls:
  policyChangesRequireIndependentApproval: true
  auditAllKeyUse: true
  enforceTenantScopeInApplication: true
~~~

**Chỉ dùng sơ đồ này để hiểu cách tách quyền.** KMS có thể hỗ trợ những operation và condition khác; phải viết policy đúng cú pháp provider, xác minh deny boundaries, key policy, resource/role trust và kiểm thử gọi API thật.

### KMS thường không biết quyền truy cập bản ghi nghiệp vụ

KMS có thể biết role được `Decrypt` trên KEK, nhưng không nhất thiết biết role đó **được đọc hóa đơn của tenant nào**. Ứng dụng cần kiểm tra **user identity, data ownership, tenant scope, record authorization và AAD/encryption context**.

Một khóa encryption-only **không thay thế authorization của dữ liệu**.

## 13. Envelope encryption: DEK encrypt dữ liệu, KEK bảo vệ DEK

Trong **envelope encryption**:

- **DEK** (*Data Encryption Key*) trực tiếp mã hóa plaintext, ví dụ bằng **AES-GCM**.
- **KEK** (*Key Encryption Key*) bọc/giải bọc DEK, thường được bảo vệ tại KMS/HSM.

~~~mermaid
flowchart LR
    Data[Plaintext record] --> Enc[AES-GCM Encrypt với DEK]
    DEK[DEK ngẫu nhiên] --> Enc
    Enc --> Store[(Ciphertext, nonce, tag, AAD profile)]
    DEK --> Wrap[Wrap DEK]
    KEK[KEK trong KMS/HSM] --> Wrap
    Wrap --> Store
    Store --> Reader[Authorized reader]
    Reader --> Unwrap[KMS/HSM Unwrap DEK theo policy]
    Unwrap --> Dec[AES-GCM Decrypt + verify tag]
    Dec --> Output[Plaintext được phép trả về]
~~~

### Phân biệt operation trong envelope encryption

| Khóa | Mục đích | Operation đúng | Không nên trộn |
| --- | --- | --- | --- |
| **DEK** | Mã hóa/giải mã data ciphertext | AES-GCM Encrypt/Decrypt, theo boundary và principal được phép | Không dùng cùng raw key cho HMAC/signing hoặc bọc DEK khác |
| **KEK** | Bảo vệ DEK | Wrap/Unwrap hoặc provider API tương đương | Không dùng như DEK chung cho mọi bản ghi |
| **Signing key** | Ký tài liệu/ciphertext/manifest theo policy | Sign | Không dùng cùng vật liệu làm DEK/KEK |
| **HMAC key** | Xác thực thông điệp | Generate/Verify MAC | Không dùng raw DEK trực tiếp |
| **Agreement key** | Thiết lập shared secret | ECDH/Derive theo giao thức | Không dùng như signing hoặc storage DEK tùy tiện |

### Vì sao “writer chỉ Encrypt” có thể là hiểu lầm ở envelope encryption?

Nếu writer gọi `GenerateDataKey` và nhận **raw DEK plaintext** trong JVM để AES-GCM encrypt, nó **về mặt mật mã có thể decrypt ciphertext khác dùng cùng DEK** nếu lấy được ciphertext và key bytes.

Lúc này chính sách **KMS Encrypt-only** đối với KEK **không tự đảm bảo** writer không có khả năng giải mã offline bằng raw DEK mà KMS đã trả.

Muốn ranh giới mạnh hơn, có thể cân nhắc:

- **Mã hóa trực tiếp bên trong KMS/HSM hoặc encryption gateway** không trao raw DEK cho writer, khi API/dung lượng/chi phí hỗ trợ.
- **DEK riêng cho mỗi object**, hạn chế lifetime và access path, để giảm phạm vi một DEK bị lộ.
- **Public-key/hybrid encryption**, writer chỉ có public key, private key ở reader boundary.
- Tách **key handling service** khỏi writer và chặn khả năng truy xuất key, memory và APIs ngoài mục đích.

**Chọn giải pháp theo threat model**, không coi DEK tạm ở app là luôn sai hoặc luôn an toàn.

## 14. Khi nào cần public-key write-only thay vì symmetric KMS policy?

Một số use case cần **bên gửi không có quyền truy xuất plaintext lịch sử ngay cả khi bị chiếm sau khi gửi**.

### Use case: gửi dữ liệu tới đơn vị kiểm toán

Bộ phận tiếp nhận duy trì **private decryption key trong HSM**. Các điểm tiếp nhận chỉ có **public key đã xác thực** để tạo encrypted report. Khi một endpoint ingest bị chiếm, attacker không có private key để decrypt các encrypted reports lưu trước đó.

### Điều kiện cần

- Public key có **nguồn gốc đáng tin**.
- Scheme RSA-OAEP/hybrid hoặc HPKE phù hợp, không “raw RSA”.
- Ciphertext được ràng buộc **recipient ID, context và version** theo giao thức.
- Có chính sách **rotate private decryption key và giữ khả năng decrypt lịch sử**.
- Có thể cần xác thực sender/anti-replay riêng.
- Nơi ingest không giữ plaintext quá lâu và không được cấp quyền gọi một decryption oracle.

### Ranh giới vẫn có thể bị phá

Nếu ingest service được phép gọi **API `Decrypt` hộ** qua một service khác, kẻ tấn công vẫn có thể truy vấn dữ liệu. Tách public/private key chỉ là **một lớp**, cần chặn đường gián tiếp và kiểm soát authorization nghiệp vụ.

## 15. Java 11+: demo tách đường encrypt và decrypt bằng AES-GCM

Ví dụ sau minh họa **hai vai trò logic**:

- `EncryptionWriter` chỉ cung cấp API `encrypt()`.
- `AuthorizedReader` chỉ cung cấp API `decrypt()`.
- Cùng một AES key được dùng ở hai chiều **về mặt mật mã**, nhưng được truyền cho hai object ở tầng demo để giải thích sự khác nhau giữa **interface và enforcement**.
- AAD ràng buộc `tenantId`, `recordId` và `keyVersion`.
- Một negative test cho biết metadata sai làm **GCM tag fail**.

**Cảnh báo:** Mã chạy trong **cùng JVM** nên không tạo separation of duties thật trước đối thủ chiếm process. Production phải chuyển boundary sang **KMS/HSM/encryption service** với IAM thực thi và key material được bảo vệ.

~~~java
import java.io.ByteArrayOutputStream;
import java.io.DataOutputStream;
import java.nio.charset.StandardCharsets;
import java.security.GeneralSecurityException;
import java.security.SecureRandom;
import javax.crypto.AEADBadTagException;
import javax.crypto.Cipher;
import javax.crypto.KeyGenerator;
import javax.crypto.SecretKey;
import javax.crypto.spec.GCMParameterSpec;

public final class EncryptOnlyKeyUseDemo {
    private static final SecureRandom RNG = new SecureRandom();
    private static final int GCM_NONCE_BYTES = 12;
    private static final int GCM_TAG_BITS = 128;

    static final class Envelope {
        final String tenantId;
        final String recordId;
        final String keyVersion;
        final byte[] nonce;
        final byte[] ciphertextAndTag;

        Envelope(String tenantId, String recordId, String keyVersion,
                 byte[] nonce, byte[] ciphertextAndTag) {
            this.tenantId = tenantId;
            this.recordId = recordId;
            this.keyVersion = keyVersion;
            this.nonce = nonce.clone();
            this.ciphertextAndTag = ciphertextAndTag.clone();
        }
    }

    // Length-prefix encoding: tránh nhập nhằng "ab"+"c" / "a"+"bc".
    static void writeField(DataOutputStream out, String text)
            throws java.io.IOException {
        byte[] utf8 = text.getBytes(StandardCharsets.UTF_8);
        out.writeInt(utf8.length);
        out.write(utf8);
    }

    static byte[] aad(String tenant, String record, String version)
            throws java.io.IOException {
        ByteArrayOutputStream bytes = new ByteArrayOutputStream();
        DataOutputStream out = new DataOutputStream(bytes);
        writeField(out, "invoice-data-aead/v1");
        writeField(out, tenant);
        writeField(out, record);
        writeField(out, version);
        out.flush();
        return bytes.toByteArray();
    }

    static SecretKey newAes256Key() throws GeneralSecurityException {
        KeyGenerator generator = KeyGenerator.getInstance("AES");
        generator.init(256, RNG);
        return generator.generateKey();
    }

    // Đường writer chỉ có operation Encrypt trong public API.
    static final class EncryptionWriter {
        private final SecretKey key;
        private final String keyVersion;

        EncryptionWriter(SecretKey key, String keyVersion) {
            this.key = key;
            this.keyVersion = keyVersion;
        }

        Envelope encrypt(String tenantId, String recordId, byte[] data)
                throws Exception {
            byte[] nonce = new byte[GCM_NONCE_BYTES];
            RNG.nextBytes(nonce);

            Cipher cipher = Cipher.getInstance("AES/GCM/NoPadding");
            cipher.init(Cipher.ENCRYPT_MODE, key,
                    new GCMParameterSpec(GCM_TAG_BITS, nonce));
            cipher.updateAAD(aad(tenantId, recordId, keyVersion));
            byte[] encrypted = cipher.doFinal(data);

            return new Envelope(tenantId, recordId,
                    keyVersion, nonce, encrypted);
        }
    }

    // Đường reader chỉ có operation Decrypt trong public API.
    static final class AuthorizedReader {
        private final SecretKey key;

        AuthorizedReader(SecretKey key) {
            this.key = key;
        }

        byte[] decrypt(Envelope envelope) throws Exception {
            Cipher cipher = Cipher.getInstance("AES/GCM/NoPadding");
            cipher.init(Cipher.DECRYPT_MODE, key,
                    new GCMParameterSpec(GCM_TAG_BITS, envelope.nonce));
            cipher.updateAAD(aad(envelope.tenantId,
                    envelope.recordId, envelope.keyVersion));
            // GCM tag được xác minh trong doFinal().
            return cipher.doFinal(envelope.ciphertextAndTag);
        }
    }

    public static void main(String[] args) throws Exception {
        SecretKey aes = newAes256Key();

        EncryptionWriter writer = new EncryptionWriter(aes, "dek-v1");
        AuthorizedReader reader = new AuthorizedReader(aes);

        byte[] plain = "invoice-data-for-training"
                .getBytes(StandardCharsets.UTF_8);

        Envelope stored = writer.encrypt("tenant-a", "invoice-1", plain);
        byte[] restored = reader.decrypt(stored);

        System.out.println("Encryption succeeded: "
                + (stored.ciphertextAndTag.length > 0));
        System.out.println("Authorized read matches: "
                + java.security.MessageDigest.isEqual(plain, restored));

        Envelope tamperedTenant = new Envelope(
                "tenant-b", stored.recordId, stored.keyVersion,
                stored.nonce, stored.ciphertextAndTag);

        try {
            reader.decrypt(tamperedTenant);
            throw new AssertionError("Wrong AAD must be rejected");
        } catch (AEADBadTagException expected) {
            System.out.println("Wrong tenant AAD: rejected");
        }

        // Demo không in raw key, plaintext hay ciphertext.
        // Production: KMS/HSM, key ID, IAM, key inventory, audit, rotation.
    }
}
~~~

**Kết quả minh họa:**

~~~text
Encryption succeeded: true
Authorized read matches: true
Wrong tenant AAD: rejected
~~~

### Những điều demo thể hiện

1. Có thể tổ chức code theo **các operation được cấp cho từng vai trò**.
2. **AES vẫn cần cùng key material khi decrypt** theo thuật toán.
3. **GCM tag** phát hiện metadata AAD bị thay đổi.
4. **Nonce** được tạo mới cho từng lần encrypt trong ví dụ.
5. Không cần in raw key để kiểm tra chức năng.

### Những điều demo không bảo đảm

- Không có **KMS-backed key isolation**: cả writer và reader giữ tham chiếu tới cùng raw key trong một JVM.
- `private final SecretKey` và việc thiếu hàm `decrypt()` trong class writer **không phải rào cản với attacker có quyền điều khiển JVM hoặc đọc bộ nhớ**.
- Không có tenant authorization ngoài AAD, điều kiện nonce toàn hệ thống, idempotency, DB transactions hoặc audit.
- Nonce ngẫu nhiên 96 bit **không bảo đảm tuyệt đối không va chạm**; production phải đánh giá giới hạn dùng key.
- `MessageDigest.isEqual` trên hai bản plaintext test **không chứng minh** tính an toàn RNG hoặc khả năng bảo vệ private key.
- Chưa có `KEK`, wrapped DEK hay key version lookup trong KMS.
- Không có key rotation, cache clearing, restore/DR và incident workflow.

**Giá trị của ví dụ nằm ở phân tách giao diện và ngữ nghĩa; ranh giới bảo mật cần được thiết kế ở hạ tầng thật.**

## 16. Java 11+: public-key encrypt-only với RSA-OAEP

Nếu yêu cầu là **sender không có private decrypt key**, public-key encryption cho thấy sự phân tách rõ ràng hơn.

Ví dụ Java dưới đây dùng **RSA-OAEP với SHA-256/MGF1-SHA-256** để mã hóa một đoạn dữ liệu **ngắn** bằng public key, rồi chỉ recipient giữ private key mới giải mã được. Demo sinh key pair trong một JVM để dễ chạy; trong production, private key phải nằm trong **recipient boundary**, không được truyền vào sender.

~~~java
import java.nio.charset.StandardCharsets;
import java.security.KeyPair;
import java.security.KeyPairGenerator;
import java.security.SecureRandom;
import java.security.spec.MGF1ParameterSpec;
import javax.crypto.Cipher;
import javax.crypto.spec.OAEPParameterSpec;
import javax.crypto.spec.PSource;

public final class RsaPublicEncryptOnlyDemo {

    public static void main(String[] args) throws Exception {
        SecureRandom rng = new SecureRandom();

        // Chỉ mô phỏng provisioning tại recipient.
        KeyPairGenerator kg = KeyPairGenerator.getInstance("RSA");
        kg.initialize(3072, rng);
        KeyPair recipient = kg.generateKeyPair();

        OAEPParameterSpec oaep = new OAEPParameterSpec(
                "SHA-256", "MGF1", MGF1ParameterSpec.SHA256,
                PSource.PSpecified.DEFAULT);

        byte[] shortSecret = "training-demo-key"
                .getBytes(StandardCharsets.UTF_8);

        // Sender CHỈ cần public key đáng tin của recipient.
        Cipher senderCipher = Cipher.getInstance("RSA/ECB/OAEPPadding");
        senderCipher.init(Cipher.ENCRYPT_MODE,
                recipient.getPublic(), oaep, rng);
        byte[] encrypted = senderCipher.doFinal(shortSecret);

        // Recipient dùng private key, không gửi private key cho sender.
        Cipher recipientCipher = Cipher.getInstance("RSA/ECB/OAEPPadding");
        recipientCipher.init(Cipher.DECRYPT_MODE,
                recipient.getPrivate(), oaep);
        byte[] recovered = recipientCipher.doFinal(encrypted);

        System.out.println("Ciphertext created: " + (encrypted.length > 0));
        System.out.println("Recipient decrypted: "
                + java.security.MessageDigest.isEqual(
                        shortSecret, recovered));

        // Không in private key hoặc plaintext.
        // Production: verify recipient public key/cert fingerprint,
        // KMS/HSM private key, hybrid encryption, IAM và audit.
    }
}
~~~

**Kết quả minh họa:**

~~~text
Ciphertext created: true
Recipient decrypted: true
~~~

### Giới hạn quan trọng

- **RSA-OAEP chỉ dùng cho payload ngắn**; thường dùng để bọc DEK, rồi mã hóa dữ liệu bằng AES-GCM. Không dùng RSA trực tiếp cho file lớn.
- Provider phải hỗ trợ chính xác `RSA/ECB/OAEPPadding` và **OAEPParameterSpec**; chữ `ECB` trong transformation là thành phần định danh JCA, không có nghĩa dùng RSA như AES-ECB.
- Demo sinh **public/private key trong một process**, nên chỉ minh họa thuật toán, không có sự cô lập người gửi/người nhận thật.
- **Sender authentication và replay protection không tự có** từ RSA-OAEP.
- Phải kiểm tra **đúng public key recipient** qua chứng thư/trust/fingerprint được phê duyệt.
- Private decryption key có thể cần HSM/KMS, key-usage restriction, rotation và backup.
- Không dùng **cùng RSA key pair** cho cả RSA-OAEP encryption và chữ ký số nếu không có thiết kế, chính sách và phân tích giao thức phù hợp; nên **tách key pair theo purpose**.

## 17. Tách encryption key khỏi signing, MAC và agreement keys

Một lỗi phổ biến là lấy cùng secret hoặc cùng asymmetric key pair và dùng cho nhiều chức năng vì thư viện kỹ thuật cho phép.

| Mục đích | Khóa thích hợp | Vì sao không dùng chung bừa bãi |
| --- | --- | --- |
| Mã hóa dữ liệu tại rest | AES-GCM DEK | Purpose/nonce/cryptoperiod và quyền riêng |
| Bọc DEK | KEK/AES-KW hoặc provider scheme | Ranh giới key-management khác dữ liệu |
| Ký hóa đơn/chứng thư | ECDSA, RSA-PSS, Ed25519 signing key | Chữ ký có semantic và trust riêng |
| Xác thực webhook | HMAC key riêng | Secret shared, không phải AEAD tag cho data-at-rest |
| Thỏa thuận khóa | ECDH/X25519 agreement key | Derive shared secret; cần peer authentication/KDF |
| Token encryption | Scheme AEAD/hybrid đã định nghĩa | Token issuer/audience/trust và metadata riêng |
| Password hashing | Argon2id/scrypt/PBKDF2 tùy policy | Không dùng raw AES key hoặc hash mật khẩu trực tiếp |

### AES-GCM tag có cho phép dùng HMAC key chung không?

Không nên tự lấy **AES encryption key** và dùng raw bytes đó làm HMAC secret. AES-GCM đã cung cấp authenticated encryption theo scheme của nó; nếu hệ thống cần **MAC độc lập** cho một giao thức khác, tạo key khác hoặc **dẫn xuất subkey có domain separation** từ master phù hợp theo KDF chuẩn.

### ECDSA/ECDH

Private EC key có thể có biểu diễn toán học tương tự giữa ECDSA và ECDH, nhưng **key usage và mô hình đe dọa khác nhau**. Trong thiết kế mới nên sinh **key pair riêng** cho signing và agreement. Không dựa vào khả năng gọi API để suy ra key reuse là an toàn.

### KDF không biến master yếu thành mạnh

Nếu dùng HKDF để dẫn xuất `K_encrypt` và `K_mac`, master phải có entropy phù hợp và `info` phải tách miền không mơ hồ. **Lộ master** có thể ảnh hưởng tất cả subkeys; không gọi các subkeys đó là độc lập tuyệt đối về mặt thông tin.

## 18. Thiết kế chính sách quyền truy cập trong production

### Bốn nhóm principal gợi ý

| Principal | Cho phép | Từ chối / kiểm soát đặc biệt |
| --- | --- | --- |
| **Ingestion writer** | Encrypt dữ liệu mới trong scope | Decrypt, Export, ChangePolicy, CreateGrant |
| **Authorized reader** | Decrypt sau business authorization | Export raw key, sửa IAM, ký số ngoài purpose |
| **Key custodian** | Generate/Rotate/Activate theo approval | Dùng DEK giải mã dữ liệu nghiệp vụ ngoài nhiệm vụ |
| **Security approver/auditor** | Review, approve hoặc đọc log | Raw key và mọi cryptographic use không cần thiết |
| **Migration worker** | Quyền legacy decrypt và encrypt mới **tạm thời** | Quyền vĩnh viễn mọi tenant hoặc admin |
| **Incident responder** | Suspend/revoke trong giới hạn runbook | Resume compromised key tùy ý |

### Policy tối thiểu phải kiểm tra

1. **Principal ↔ key ID/version:** không cấp rộng cho mọi key chỉ vì cùng account.
2. **Operation:** Encrypt/Decrypt/Wrap/Unwrap/Sign/Derive tách biệt theo purpose.
3. **Environment và tenant:** production và staging không dùng chung raw secret trái chính sách.
4. **Data scope:** business API kiểm tra quyền người dùng cuối, không chỉ KMS principal.
5. **Key state:** pre-activation/suspended/deactivated không được new-use trái policy.
6. **Rate/quota/time:** hạn chế lạm dụng và bảo vệ availability.
7. **Credential issuance:** service identity và grant phải có TTL, rotation, không hard-code.
8. **Indirect privilege:** không cho writer tự sửa IAM/trust role/policy để mở Decrypt.
9. **Audit và alert:** cả allow/deny lẫn policy changes đều có bằng chứng.
10. **Backup/export:** không cấp quyền khiến raw key bị lấy ra từ đường khác.

### Negative test trước deployment

~~~text
Request:
    principal = ingestion-writer
    key = billing-key-v4
    operation = Encrypt
Expected:
    ALLOW theo đúng purpose và scope

Request:
    principal = ingestion-writer
    key = billing-key-v4
    operation = Decrypt
Expected:
    DENY

Request:
    principal = ingestion-writer
    key = billing-key-v4
    operation = CreateGrant(Decrypt -> itself)
Expected:
    DENY

Request:
    principal = staging-writer
    key = production-key
    operation = Encrypt
Expected:
    DENY

Request:
    principal = reader
    key = suspended-key
    operation = Decrypt
Expected:
    DENY hoặc xử lý theo ngoại lệ được duyệt
~~~

**Để chứng minh enforcement thật**, chạy integration tests ở **KMS/HSM/provider và API gateway**, không chỉ unit test một hàm if-else.

## 19. Key lifecycle: encrypt-only thay đổi ra sao khi rotate?

“Chỉ encrypt” không phải policy bất biến cho mọi giai đoạn. Khi key đến hạn hoặc bị compromise, cần có trạng thái **đúng cho new use và legacy use**.

| Giai đoạn | Encrypt mới | Decrypt dữ liệu cũ | Kiểm soát |
| --- | --- | --- | --- |
| **Pre-activation** | Chưa được phép | Chưa cần hoặc bị chặn | Kiểm tra nguồn key, IAM, thuật toán, test |
| **Active** | Theo writer policy | Theo reader policy | Nonce/AAD/usage limits, audit |
| **Rotation cutover** | Chỉ key mới v2 | v1/v2 theo metadata | Reader-first, writer fencing |
| **Deactivated v1** | **Không new encrypt bằng v1** | Có thể decrypt-only trong retention | Phạm vi hẹp, không tạo bản mã mới |
| **Suspended** | Bị chặn theo policy | Có thể bị chặn toàn bộ tùy sản phẩm | Incident/availability plan |
| **Compromised** | Không dùng key cũ cho bảo vệ mới | Legacy theo ứng cứu đặc biệt nếu cần | Thay key, đánh giá dữ liệu bị lộ |
| **Destroyed** | Không | Không | Chỉ sau dependency/backup checks |

### Đọc lại dữ liệu sau rotation

Một reader cần biết **key ID/material version** mã hóa từng ciphertext. Không dùng alias trỏ “latest key” để thử giải mã bừa bãi dữ liệu lịch sử.

### Rewrap và re-encrypt

- **KEK rotation / rewrap DEK:** thay khóa bọc, thường **không thay DEK hoặc ciphertext dữ liệu**.
- **DEK rotation / re-encrypt data:** thay khóa trực tiếp mã hóa, cần **decrypt–verify rồi encrypt lại** dưới DEK mới và nonce/AAD mới.

Nếu **raw DEK cũ đã lộ**, chỉ rewrap dưới KEK mới **không khôi phục tính bí mật**. Phải đánh giá re-encrypt và dữ liệu/backup đã bị sao chép.

### Không xóa old key quá sớm

Dữ liệu archive và backup có thể vẫn cần key v1. Trước khi destroy, kiểm tra **wrapped DEKs, ciphertext, retention, legal hold và restore drills**. “Writer đã ngừng encrypt bằng v1” **không có nghĩa** v1 đã hết phụ thuộc.

## 20. KMS/HSM audit và điểm mù raw DEK

Kiểm toán phải chứng minh **ai dùng key nào, operation nào và kết quả thực tế**, chứ không chỉ có trạng thái “policy allow”.

### Event mẫu

~~~yaml
schemaVersion: "1"
eventType: "KEY_USE_DECISION_AND_EXECUTION"
requestId: "req-2030-0642"
principal: "billing-ingestion-prod"
key:
  id: "billing-dek-v7"
  version: "v7"
  purpose: "INVOICE_DATA_ENCRYPTION"
operation: "Encrypt"
environment: "production"
tenantScopeReference: "tenant-ref-7"
authorization:
  decision: "ALLOW"
  policyRevision: "policy-v12"
execution:
  providerResult: "SUCCESS"
  providerEventReference: "kms-provider-request-ref"
observedAtUtc: "2030-06-02T10:00:00Z"
~~~

Đây là **mẫu học thuật**, không phải schema KMS dùng chung. Trong các provider thực tế, một sự kiện app `Encrypt` bằng DEK có thể **không có provider event tương ứng**, nếu ứng dụng giữ raw DEK và tự chạy AES-GCM trong JVM.

### Ba lớp audit cần đối chiếu

1. **Ứng dụng:** business request, tenant/data scope, key version, decision và outcome.
2. **IAM/control plane:** policy/key state, grants, approvals, thay đổi role hoặc alias.
3. **KMS/HSM:** cryptographic operation, key reference, principal và provider result khi tính năng log hỗ trợ.

### Điểm mù cache

Một lần `Unwrap` từ KMS có thể phục vụ **nhiều lần local Decrypt**, nếu DEK được cache. Ngược lại, **0 lượt KMS Decrypt trong hôm nay không chứng minh 0 dữ liệu đã giải mã**.

Cần theo dõi **ứng dụng và data-access logs** mà không ghi raw key, plaintext, token, HSM PIN hoặc nội dung bí mật.

### Chống lộ qua log

Không log `SecretKey.getEncoded()`, raw DEK/KEK, plaintext, full HTTP request chứa secret, crash dump hoặc authentication credential. Dùng **key ID, key version, principal, purpose, request ID, policy revision và reason code** với retention/quyền truy cập phù hợp.

## 21. Những cuộc tấn công cần threat model

### 21.1. Quyền Encrypt bị lạm dụng để tạo dữ liệu giả

Attacker có credential writer, không thể Decrypt nhưng vẫn có thể đưa **payload sai** vào hệ thống. AEAD tag cho biết ciphertext được tạo bằng đúng key, **không nói nội dung đã được business owner phê duyệt**.

Biện pháp: **input validation, authentication, authorization, chống replay, quota, audit và xử lý dữ liệu phía reader**.

### 21.2. Decrypt oracle qua endpoint khác

Writer bị cấm KMS `Decrypt` nhưng có thể gọi một API “preview invoice” không kiểm tra tenant. Đây là **bypass qua ứng dụng**, không phải lỗi của AES.

Biện pháp: kiểm tra authorization trên mọi đường đọc, không để decryption endpoint trả dữ liệu rộng.

### 21.3. Self-escalation qua IAM

Principal không có `Decrypt` nhưng có thể sửa key policy hoặc tạo grant cho chính mình. Biện pháp: **deny/permission boundary**, role separation, dual control khi cần và audit thay đổi quyền.

### 21.4. Raw key xuất hiện trong RAM

Khi ứng dụng giữ raw AES key, attacker chiếm process có thể trích xuất secret. Tên class `EncryptOnlyKeyManager` không tạo boundary chống memory extraction.

Biện pháp: **HSM/KMS cryptographic boundary**, key non-exportability khi phù hợp, hạn chế plaintext DEK, process hardening và cache policy.

### 21.5. Nonce reuse trong GCM

Attacker không cần quyền Decrypt nếu các lần mã hóa vi phạm nonce uniqueness. Biện pháp: nonce allocation đúng, usage limits và tests multi-instance/restart/snapshot.

### 21.6. Public-key substitution

Sender nhận public encryption key do attacker cung cấp rồi mã hóa cho attacker. Biện pháp: **certificate/trust validation**, pinning khi phù hợp, authenticated discovery và key version.

### 21.7. Lộ private decryption key

Một recipient private key bị sao chép có thể ảnh hưởng ciphertext lịch sử tùy scheme. Biện pháp: bảo vệ khóa, rotate, ứng cứu, lifecycle và khi cần dùng giao thức có forward secrecy.

## 22. Dual control và vai trò trong key use

Không phải mỗi lần `Encrypt` đều cần hai approver. Nếu hệ thống ghi hàng triệu bản ghi, việc bắt hai nhân viên duyệt từng AES-GCM operation thường **không phù hợp**.

Dual control thích hợp hơn cho:

- Tạo/kích hoạt **root KEK** hoặc key material rủi ro cao.
- **Đổi policy/grant** khiến writer có thể Decrypt hoặc Export.
- Xuất/import private key hoặc KEK nhạy cảm.
- Mở đường **recovery decrypt** ngoài quy trình thường ngày.
- Rotate hoặc Destroy key có ảnh hưởng rộng.
- Khôi phục key sau compromise hoặc hủy dữ liệu không đảo ngược.

### Mẫu RACI khái niệm

| Hành động | Key owner | Custodian | Security approver | Workload | Auditor |
| --- | --- | --- | --- | --- | --- |
| Chọn purpose/key type | **A** | C | C | I | I |
| Tạo key/hạn chế usage | A theo policy | **R** | C | I | I |
| Encrypt dữ liệu mới | I | I | I | **R** | I |
| Decrypt dữ liệu nhạy cảm | A theo business rule | I | C | **R theo quyền** | I |
| Mở thêm quyền Decrypt | **A** | R | **C/Approval độc lập** | I | I |
| Rotate/hủy key | **A** | **R** | C/Approval | I | I |
| Đối soát logs | I | C | C | I | **R** |

**R/A/C/I chỉ biểu thị trách nhiệm**, không trực tiếp cấu hình IAM. Phải kiểm soát cả **quyền sửa chính sách và audit** để một người không tự cấp, sử dụng rồi xóa bằng chứng.

## 23. Case study: ingestion service không được đọc hóa đơn lịch sử

### Bối cảnh

`billing-ingestion` nhận dữ liệu hóa đơn mới. Yêu cầu:

- Mã hóa trước khi lưu.
- Không cho ingestion principal đọc lại hóa đơn lịch sử.
- `billing-reader` chỉ giải mã hóa đơn thuộc tenant được phép.
- `key-custodian` quản lý key nhưng không được tùy tiện xem plaintext.
- Sau rotation vẫn đọc được dữ liệu cũ.

### Thiết kế A — Symmetric key trong KMS

1. Tạo key resource phục vụ purpose bảo vệ dữ liệu hoặc DEK, theo sản phẩm.
2. Cấp writer **Encrypt-only operation**, chặn `Decrypt` và self-escalation.
3. Cấp reader **Decrypt** theo IAM nhưng vẫn kiểm tra **business data access**.
4. Lưu ciphertext + key ID/version + nonce/AAD/tag theo API/scheme.
5. Audit writer `Encrypt`, reader `Decrypt`, policy changes và key lifecycle.

**Điều kiện:** Không cấp cho writer raw DEK dùng để decrypt offline nếu mục tiêu là ngăn writer giải mã. Nếu API trả plaintext DEK cho writer, cần đánh giá lại threat model hoặc chọn mô hình khác.

### Thiết kế B — Public-key hybrid

1. Recipient tạo asymmetric encryption key pair trong boundary được bảo vệ.
2. Writer nhận **public key đã xác thực** của recipient.
3. Writer tạo DEK tươi, mã hóa record bằng AEAD và **bọc DEK cho recipient** bằng scheme hybrid chuẩn.
4. Recipient giữ private key để unwrap/decapsulate DEK và giải mã data.
5. Gắn metadata recipient, key version, tenant và AAD; audit tại cả writer và reader.

**Lưu ý:** Writer vẫn có plaintext dữ liệu **đang gửi** và DEK tươi ngay lúc tạo ciphertext, nhưng sau đó không có private recipient key để giải mã ciphertext lịch sử nếu đã xử lý đúng secret lifecycle. Không mặc nhiên coi public-key encryption là authorization người gửi.

### So sánh

| Tiêu chí | Symmetric KMS Encrypt-only | Public-key hybrid |
| --- | --- | --- |
| Key trực tiếp encrypt | Secret trong KMS hoặc DEK theo thiết kế | DEK ngẫu nhiên; public key bảo vệ DEK |
| Writer cần private/secret key? | Tùy API; **không nên nhận raw key nếu yêu cầu write-only mạnh** | Chỉ cần public recipient key (ngoài DEK tạm) |
| Reader decrypt | KMS/HSM hoặc unwrap DEK theo quyền | Private recipient key + unwrap DEK |
| Risk root admin | Có thể sửa KMS/IAM | Có thể lộ private key/trust nếu quản trị sai |
| Phù hợp | Workflow đồng nhất trong hệ thống KMS có enforcement | Gửi cho recipient độc lập, write-only client/endpoint |
| Khó khăn | Quyền API, dữ liệu lớn, cache/raw DEK | Trust public key, hybrid package, key rotation |

## 24. Case study: lộ credential writer và đường vòng `GenerateDataKey`

### Tình huống

Một ứng dụng được cấu hình “Encrypt-only” trong IAM nhưng lại có quyền **`GenerateDataKey` trả raw DEK**. Workload giữ một **DEK per tenant** trong cache để giảm chi phí. Credential của workload bị lấy.

### Phân tích

- Nếu attacker có thể nhận raw DEK per tenant hoặc đọc cache, họ có thể **decrypt ciphertext** tương ứng bằng AES-GCM ở ngoài KMS.
- KMS policy chặn `Decrypt` trên KEK **không vô hiệu** raw DEK mà attacker đang giữ.
- `DisableKey` ở KMS có thể chặn unwrap mới nhưng **không xóa DEK đã ra client**.
- Nếu raw DEK đã bị lộ, chỉ **rewrap** cùng DEK dưới KEK khác không khôi phục bí mật.

### Hành động cần thực hiện

1. Thu hồi credential và đánh giá quyền `GenerateDataKey`, grants, cache và các API đường vòng.
2. Kiểm tra audit KMS/HSM, application logs và data access; **đừng suy ra 0 KMS Decrypt là 0 local Decrypt**.
3. Liệt kê ciphertext/records phụ thuộc những DEK có thể bị lộ.
4. Sinh DEK mới bằng nguồn an toàn; cân nhắc **re-encrypt** dữ liệu theo phạm vi.
5. Xác định có cần thay KEK hoặc master hay không từ nguyên nhân gốc.
6. Chỉnh kiến trúc: **per-object DEK, TTL/cache policy, gateway/HSM boundary hoặc public-key hybrid** theo threat model.
7. Giữ key cũ phục vụ legacy restore chỉ khi policy/retention/incident response cho phép.

**Bài học:** Encrypt-only là **tập hợp quyền và ranh giới sử dụng vật liệu khóa**, không phải một nhãn IAM đơn lẻ.

## 25. Case study: rotation và nguy cơ mất dữ liệu khi “encrypt-only tuyệt đối”

### Bối cảnh

Một nhóm triển khai AES key `billing-v1` với HSM object chỉ cho `Encrypt`, chặn mọi `Decrypt`, sau đó mã hóa dữ liệu và không thiết kế đường reader/decrypt hợp pháp.

Khi cần khôi phục dữ liệu lưu trữ, nhóm nhận ra **không có chủ thể hoặc key object hợp lệ để decrypt**. HSM đang thực thi policy đúng, nhưng **kiến trúc quản lý khóa không bảo đảm recoverability**.

### Điều cần thiết kế từ đầu

- Có hay không nhu cầu đọc lại plaintext?
- Ai là authorized reader, dùng key resource/object và operation nào?
- Có thể cấu hình `Decrypt` cho principal khác mà không cấp raw key ra ngoài không?
- Có đường recovery/backup được phê duyệt nếu HSM lỗi?
- Khi rotation, còn ciphertext/backup phiên bản cũ không?
- Có retention/legal hold ngăn destroy key không?

### Khi giải pháp đúng là một chiều

Một vài hệ thống có mục tiêu **không đọc lại dữ liệu**, ví dụ thu thập hash hoặc bằng chứng không thể đảo ngược. Khi ấy **encryption có khả năng giải mã tồn tại** có thể không đúng yêu cầu; cân nhắc cơ chế **hash, password hashing hoặc secure one-way transformation** phù hợp, thay vì tạo một AES key rồi cố cấm mọi Decrypt.

**Mã hóa một chiều và hàm băm một chiều là hai primitive khác nhau.** Không dùng encryption chỉ vì muốn không ai có quyền đọc lại nếu business requirement thật là **không tồn tại chức năng khôi phục plaintext**.

## 26. Những sai lầm phổ biến

| Sai lầm | Hậu quả | Cách xử lý |
| --- | --- | --- |
| Nghĩ AES key đã gắn `Encrypt-only` thì raw key không decrypt được | Sai bản chất symmetric cryptography | Cưỡng chế tại KMS/HSM, bảo vệ raw material |
| Cấp writer quyền `GenerateDataKey` trả plaintext nhưng tuyên bố writer không thể decrypt | Raw DEK cho phép decrypt offline | Thay boundary/API hoặc giảm scope cache |
| Dùng chung AES key cho HMAC và wrapping | Trộn purpose, tăng blast radius | Khóa riêng hoặc KDF chuẩn tách miền |
| Coi AEAD tag như chữ ký số | Không chứng minh một signer riêng biệt | Signing key/service riêng nếu cần |
| Chỉ restrict method Java | Attacker chiếm JVM có thể đọc SecretKey | KMS/HSM/OS boundary và IAM |
| Dùng lại nonce AES-GCM | Mất confidentiality/integrity | Nonce uniqueness và usage limits |
| Cấp role Encrypt nhưng cho tự sửa IAM | Quyền Decrypt có thể được tự mở | Deny self-escalation, SoD |
| Không kiểm tra quyền đọc dữ liệu ở ứng dụng | KMS Decrypt hợp lệ nhưng sai tenant | Business authorization + AAD |
| Không verify public key recipient | Mã hóa dữ liệu cho attacker | PKI/trust/fingerprint |
| Dùng RSA-OAEP để mã hóa file lớn | Sai giới hạn thuật toán | Hybrid AES-GCM + key encapsulation/wrapping |
| Dùng cùng RSA pair cho sign/encrypt không kiểm soát | Trộn protocol/key usage | Tách cặp theo purpose |
| Dùng ECDH mà không xác thực peer | MITM | AKE chuẩn, peer identity/trust |
| Tin KMS `ENCRYPT_DECRYPT` đồng nghĩa mọi principal được Decrypt | Đọc sai mô hình provider | IAM/key policy trên operation |
| Không xét `CKA_EXTRACTABLE` | Key có thể rời HSM | Attributes + provenance + backup audit |
| Tắt Decrypt mọi nơi rồi không thể restore | Mất dữ liệu do thiết kế | Reader/recovery path được phê duyệt |
| New writer vẫn dùng key v1 sau cutover | Rotation không hoàn tất | Fencing, key version audit |
| Hủy old key ngay khi writer ngừng Encrypt | Archive/backup không đọc được | Dependency/restore checks |
| Rewrap DEK đã lộ rồi tuyên bố an toàn | Raw DEK vẫn decrypt dữ liệu | Thay DEK, re-encrypt và ứng cứu |
| Disable KEK nhưng quên cached DEK | Có thể vẫn local decrypt | Cache policy và containment |
| Không log deny | Không thấy quét quyền/sai config | Provider + app deny audit |
| Cho phép fallback xuống key test khi KMS lỗi | Fail-open | HA, error handling, không dùng key ngoài policy |
| Dùng alias mới nhưng vật liệu không đổi | Không thực hiện key rotation | Verify key material version/provenance |
| Không xác định purpose và cryptoperiod | Key được dùng quá lâu hoặc sai chức năng | Inventory, owner, policy, review |

## 27. Checklist triển khai Encrypt-only key use trong production

1. **Mục đích:** “Chỉ encrypt” đang nghĩa key purpose, principal permission, HSM attribute hay public-key role?
2. **Data requirements:** Dữ liệu có cần decrypt/restore không, ai có quyền và theo policy nào?
3. **Algorithm:** Dùng AEAD đối xứng hay public-key/hybrid phù hợp kích thước và mô hình trust?
4. **Key provenance:** Key được sinh từ CSPRNG/DRBG/KMS/HSM phù hợp, tách với signing/HMAC/wrapping keys?
5. **Key scope:** Mỗi tenant/object/service/environment có material và key usage đáp ứng blast radius?
6. **Writer principal:** Chỉ được gọi `Encrypt` đúng key và scope; không được `Decrypt`, `Export`, `ChangePolicy` hoặc tự cấp grant?
7. **Raw material:** Writer có nhận hoặc cache plaintext DEK không? Nếu có, còn đúng mục tiêu write-only mạnh không?
8. **Reader principal:** Được `Decrypt` đúng dữ liệu, phải qua business authorization và logging?
9. **KMS usage:** Đã phân biệt loại key `ENCRYPT_DECRYPT` với quyền **operation-specific IAM**?
10. **HSM attributes:** `CKA_ENCRYPT`, `CKA_DECRYPT`, `CKA_EXTRACTABLE`, `CKA_SENSITIVE` và supported mechanisms đã được xác minh?
11. **Trust boundary:** KMS/HSM/non-exportable có thực thi đúng; process memory, backups và role admin được xét?
12. **Public-key trust:** Recipient public key/certificate được xác thực và cập nhật theo key version?
13. **GCM nonce:** Có bảo đảm không lặp dưới cùng key giữa writer, region, restart và DR?
14. **AAD:** Domain, tenant, record ID và key version được ràng buộc canonical, không lộ metadata nhạy cảm ngoài chính sách?
15. **Tag verification:** Reader chỉ trả plaintext sau khi GCM authentication tag hợp lệ?
16. **Key separation:** Không dùng raw encryption key cho signing, HMAC, ECDH hoặc KEK ngoài policy?
17. **DEK/KEK:** Nếu envelope encryption, hiểu rõ **DEK Encrypt/Decrypt** và **KEK Wrap/Unwrap**?
18. **Indirect permissions:** Admin, CI/CD, credential manager, policy edit, key export và backup có thể bypass Encrypt-only không?
19. **Dual control:** Các thay đổi key policy/export/recovery/destroy rủi ro cao cần hai approver khi thích hợp?
20. **Pre-activation:** Key mới chưa được dùng production trước khi IAM, algorithm, backup và tests đạt?
21. **Rotation:** Reader-first, writer chỉ new key, legacy decrypt đúng key version và không fallback ngoài policy?
22. **Key compromise:** Có runbook khi lộ raw DEK, KEK, master, decryption private key hoặc credential?
23. **Backup/DR:** Đã thử restore ciphertext lịch sử; không hủy key cũ khi còn phụ thuộc?
24. **Audit:** App/policy/provider events ghi actor, operation, key/version, purpose, allow/deny và result mà không lộ raw keys?
25. **Negative tests:** Writer gọi Decrypt/Export/CreateGrant bị chặn; sai tenant, suspended key và nonce lỗi được phát hiện?
26. **Availability:** Có phương án HSM/KMS outage, rate limit, queue/retry, không fail-open sang key không được duyệt?
27. **Policy review:** Owner/custodian/security/auditor định kỳ rà soát grants và mọi đường dùng key ngoài mục đích?
28. **Câu hỏi cuối:** Khi writer bị chiếm, **bằng đường nào attacker có thể lấy raw key hoặc gọi decryption oracle?** Đã kiểm tra và chặn mọi đường đó chưa?

## 28. Kết luận

**Encryption key chỉ dùng để encrypt** là một nguyên tắc về **giới hạn mục đích và quyền sử dụng khóa**, không phải lời khẳng định mọi khóa mã hóa đều bất khả thi về mặt toán học đối với phép giải mã. Với **AES**, cùng raw secret có thể encrypt và decrypt; cần **KMS/HSM, IAM, non-exportability, key attributes, business authorization và audit** để tách operation của các principal. Với **public-key encryption**, sender có thể dùng **public key đã xác thực** để mã hóa, còn private key được bảo vệ tại recipient để giải mã.

Thiết kế an toàn phải phân tách **DEK mã hóa dữ liệu** với **KEK bảo vệ DEK**, cũng như signing, HMAC và agreement keys. Dù writer chỉ được Encrypt, hệ thống vẫn phải xử lý **nonce AES-GCM, AAD, tag, input validation, replay, key version, rotation và dữ liệu lịch sử**. Khi xuất raw DEK cho ứng dụng, quyền Encrypt-only của KMS **không tự ngăn giải mã offline**. Chỉ khi xem xét **đúng trust boundary, quyền trực tiếp/gián tiếp, cache, backup, IAM và quy trình khôi phục**, tổ chức mới có thể nói rằng một writer thực sự **không có khả năng truy cập trái phép plaintext lịch sử**.
